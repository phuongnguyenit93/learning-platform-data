# Đối tượng khả biến và thay đổi dữ liệu bên trong thuộc tính

## Mục tiêu bài học

Trong Java, một thuộc tính của `HttpSession` có thể chứa object, collection hoặc một cấu trúc dữ liệu lồng nhau. Khi object đó thay đổi sau khi được lấy ra khỏi session, ứng dụng cần hiểu sự khác nhau giữa việc thay đổi trạng thái trong bộ nhớ và việc thông báo cho session repository rằng thuộc tính đã thay đổi.

Sau bài học, bạn có thể:

- Phân biệt thay đổi object tại chỗ với việc gán lại thuộc tính session.
- Giải thích vì sao một thay đổi trên `List`, `Map` hoặc object lồng nhau có thể không được lưu vào Redis/JDBC.
- Hiểu vai trò của dirty tracking, `SaveMode` và `FlushMode` trong Spring Session.
- Chọn cách cập nhật dữ liệu phiên an toàn, dễ kiểm thử và phù hợp với nhiều instance.
- Nhận diện rủi ro khi nhiều request đồng thời sửa cùng một thuộc tính.

## 1. Thuộc tính session có thể chứa object khả biến

Servlet API cho phép lưu object vào `HttpSession` bằng `setAttribute` và lấy object đó bằng `getAttribute`.

Ví dụ, ứng dụng lưu một giỏ hàng:

~~~java
HttpSession session = request.getSession();

Cart cart = new Cart();
cart.addItem(new CartItem("BOOK-01", 2));

session.setAttribute("cart", cart);
~~~

Ở đây, `cart` là một object Java. Nó có thể chứa các field, một danh sách sản phẩm hoặc các object khác. Việc session lưu một object không làm object đó trở nên bất biến.

Một object **khả biến** (mutable object) là object có trạng thái có thể thay đổi sau khi được tạo. Ví dụ:

- `ArrayList` có thể thêm, xóa hoặc thay thế phần tử.
- `HashMap` có thể thêm hoặc sửa cặp key/value.
- Một lớp `Cart` có phương thức `addItem`, `removeItem` hoặc `changeQuantity`.
- Một object chứa `List` có thể giữ nguyên tham chiếu đến danh sách nhưng nội dung danh sách thay đổi.

Ngược lại, object **bất biến** (immutable object) không cho phép thay đổi trạng thái quan sát được sau khi tạo. Muốn có giá trị mới, chương trình tạo một object mới.

Ví dụ đơn giản:

~~~java
List<String> selectedProducts = new ArrayList<>();
selectedProducts.add("BOOK-01");

session.setAttribute("selectedProducts", selectedProducts);
~~~

Lúc này session giữ tham chiếu đến một `ArrayList`. Nếu code lấy danh sách ra và gọi `add`, chính object danh sách đó bị thay đổi.

## 2. Thay đổi object tại chỗ khác với gán lại thuộc tính

Xét đoạn code sau:

~~~java
@SuppressWarnings("unchecked")
List<String> products =
        (List<String>) session.getAttribute("selectedProducts");

products.add("BOOK-02");
~~~

Dòng `add` thay đổi nội dung object `List`. Đoạn code không gọi `session.setAttribute` lần nữa.

Về mặt Java, điều này hoàn toàn hợp lệ: biến `products` tham chiếu đến object đã được lưu trong thuộc tính session, và phương thức `add` sửa object đó. Nhưng việc object trong bộ nhớ đã đổi không đồng nghĩa repository bên ngoài đã nhận được thông báo để lưu thay đổi.

Điểm khác biệt quan trọng:

| Thao tác | Điều gì thay đổi? | Repository có thể nhận biết thế nào? |
|---|---|---|
| `list.add(value)` | Nội dung object `List` thay đổi | Có thể không nhận ra nếu chỉ theo dõi việc gán thuộc tính |
| `map.put(key, value)` | Nội dung object `Map` thay đổi | Có thể không nhận ra nếu không có tín hiệu cập nhật |
| `cart.setQuantity(3)` | Field bên trong `Cart` thay đổi | Có thể không nhận ra nếu `Cart` không được gán lại |
| `session.setAttribute("cart", cart)` | Thuộc tính được đặt lại | Session có thể đánh dấu thuộc tính đã thay đổi |
| `session.removeAttribute("cart")` | Thuộc tính bị xóa | Session có thể ghi nhận thao tác xóa |

Với session nằm trong bộ nhớ của một servlet container, tham chiếu object có thể tiếp tục tồn tại trong tiến trình và thay đổi tại chỗ thường vẫn được nhìn thấy trong các request sau của cùng session. Tuy nhiên, hành vi lưu trữ của container, thời điểm ghi ra đĩa hoặc cơ chế replication phụ thuộc sản phẩm và cấu hình.

Với Spring Session dùng Redis hoặc JDBC, dữ liệu phiên thường được đọc từ repository, biểu diễn trong một object session ở request hiện tại rồi được ghi trở lại theo cơ chế lưu của repository. Việc theo dõi thay đổi thuộc tính có thể dựa trên các thao tác với session API. Một thay đổi sâu bên trong object không nhất thiết tạo ra thao tác mà cơ chế theo dõi đó nhận biết được.

Vì vậy, không nên suy luận rằng một thay đổi đã được lưu chỉ vì chương trình đọc lại object trong cùng request và thấy giá trị mới.

## 3. Vì sao thay đổi lồng nhau dễ bị bỏ sót?

Một thuộc tính session không nhất thiết là một giá trị đơn giản. Nó có thể là object chứa nhiều tầng collection:

~~~java
class Cart {
    private List<CartItem> items = new ArrayList<>();

    public List<CartItem> getItems() {
        return items;
    }
}
~~~

Giả sử code thực hiện:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.getItems().get(0).setQuantity(4);
~~~

Trong đoạn này có thể xảy ra nhiều thay đổi lồng nhau:

1. Lấy thuộc tính `cart` từ session.
2. Lấy danh sách `items` bên trong `Cart`.
3. Lấy một `CartItem` từ danh sách.
4. Thay đổi field `quantity` của `CartItem`.

Không có lời gọi nào đặt lại thuộc tính `cart` trong session. Nếu repository chỉ đánh dấu thuộc tính khi `setAttribute` được gọi, thay đổi sâu bên trong `CartItem` có thể không được lưu.

Cùng vấn đề có thể xảy ra với:

- Thêm hoặc xóa phần tử trong collection lồng nhau.
- Sửa một value bên trong `Map`.
- Thay đổi object con được tham chiếu từ object cha.
- Sửa field của một entity hoặc DTO được giữ trong session.
- Thay đổi một mảng hoặc object ngày giờ khả biến.

### Tham chiếu nông và thay đổi sâu

Một phép gán biến Java thường sao chép giá trị tham chiếu, không sao chép toàn bộ object. Ví dụ:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
Cart anotherReference = cart;

anotherReference.getItems().clear();
~~~

`cart` và `anotherReference` cùng trỏ đến một object `Cart`. Gọi `clear` qua một biến làm danh sách bên trong object đó thay đổi; biến còn lại quan sát cùng trạng thái đã đổi.

Nếu tạo bản sao nông (shallow copy), object mới có thể vẫn dùng chung collection hoặc object con với object cũ:

~~~java
Cart copied = new Cart(cart.getItems());
~~~

Nếu constructor trên chỉ giữ nguyên tham chiếu danh sách, việc sửa danh sách trong `copied` vẫn tác động đến danh sách của `cart`. Muốn tách trạng thái, cần tạo bản sao phù hợp cho các thành phần lồng nhau hoặc dùng cấu trúc bất biến.

## 4. Spring Session theo dõi thay đổi thuộc tính như thế nào?

Spring Session cung cấp API tương thích với `HttpSession`, nhưng dữ liệu có thể được lưu qua repository dùng chung. Với các repository như Redis hoặc JDBC, Spring Session cần xác định thuộc tính nào được thêm, thay thế hoặc xóa để ghi dữ liệu phù hợp.

Một cơ chế phổ biến là **dirty tracking**: session ghi nhận những thuộc tính đã thay đổi thông qua các thao tác của session API. Khi lưu session, repository sử dụng thông tin này để quyết định dữ liệu nào cần ghi.

Ví dụ:

~~~java
Cart cart = (Cart) session.getAttribute("cart");
cart.addItem(new CartItem("BOOK-02", 1));

// Thông báo rõ thuộc tính cart đã được cập nhật.
session.setAttribute("cart", cart);
~~~

Lời gọi `setAttribute` sau khi sửa object là tín hiệu rõ ràng cho session rằng thuộc tính `cart` cần được xem là đã thay đổi.

Cách này đặc biệt hữu ích khi object khả biến đã được thay đổi tại chỗ. Dù vậy, việc gọi `setAttribute` không giải quyết mọi vấn đề về đồng thời hoặc tính nguyên tử; nó chỉ giúp biểu đạt rõ việc cập nhật thuộc tính.

### SaveMode

Spring Session có khái niệm `SaveMode` để quyết định thuộc tính nào được lưu khi session được ghi xuống repository. Các giá trị thường gặp gồm:

| SaveMode | Ý nghĩa khái quát |
|---|---|
| `ON_SET_ATTRIBUTE` | Lưu những thuộc tính đã được đặt hoặc đánh dấu thay đổi thông qua thao tác set |
| `ON_GET_ATTRIBUTE` | Lưu thuộc tính đã được đọc hoặc được đặt |
| `ALWAYS` | Lưu tất cả thuộc tính của session khi lưu session |

Cần đọc tài liệu của repository và phiên bản Spring Session đang dùng để xác định hành vi mặc định cũng như chi tiết triển khai.

Với `ON_SET_ATTRIBUTE`, việc chỉ sửa một object lồng nhau sau khi gọi `getAttribute` có thể không đủ để thuộc tính được ghi lại, vì không có thao tác `setAttribute`.

Với `ON_GET_ATTRIBUTE`, việc đọc thuộc tính cũng có thể làm thuộc tính đó được đưa vào tập cần lưu. Điều này có thể giúp một số thay đổi tại chỗ được ghi lại nếu thuộc tính đã được đọc trong request, nhưng cũng làm tăng số thuộc tính được ghi. Không nên dùng chế độ này như lý do để bỏ qua việc biểu đạt rõ cập nhật.

Với `ALWAYS`, repository có thể ghi mọi thuộc tính khi session được lưu. Cách này giảm phụ thuộc vào việc phát hiện thuộc tính nào đã đổi, nhưng có thể tăng chi phí serialize và ghi dữ liệu, nhất là khi session chứa object lớn.

`SaveMode` không biến các thao tác đọc-sửa-ghi thành giao dịch nguyên tử. Nó điều chỉnh phạm vi thuộc tính được ghi, không tự giải quyết xung đột giữa hai request.

### FlushMode

`FlushMode` quyết định thời điểm thay đổi session được đẩy xuống repository. Hai chế độ thường gặp là:

- `ON_SAVE`: gom các thay đổi trong quá trình xử lý request và ghi khi session được lưu, thường ở cuối request.
- `IMMEDIATE`: đẩy thay đổi xuống repository ngay khi có thể sau thao tác thay đổi.

Chế độ cụ thể, thời điểm flush và số lần ghi phụ thuộc repository và phiên bản. `FlushMode` trả lời câu hỏi *khi nào ghi*, còn `SaveMode` trả lời câu hỏi *ghi những thuộc tính nào*.

Ví dụ, ứng dụng có thể đánh dấu một thuộc tính đã thay đổi nhưng dữ liệu chưa được ghi xuống Redis ngay tại dòng `setAttribute` nếu đang dùng `ON_SAVE`. Request vẫn phải hoàn tất luồng lưu session theo tích hợp của Spring Session.

## 5. Cách cập nhật an toàn: tạo giá trị mới rồi setAttribute

Một cách dễ hiểu và dễ kiểm thử là lấy giá trị hiện tại, tạo trạng thái mới rồi đặt lại thuộc tính session.

Ví dụ với một lớp `Cart` có constructor sao chép:

~~~java
Cart current = (Cart) session.getAttribute("cart");

Cart updated = (current == null)
        ? new Cart()
        : new Cart(current);

updated.addItem(new CartItem("BOOK-02", 1));

session.setAttribute("cart", updated);
~~~

Điều quan trọng là constructor sao chép phải thực sự tạo trạng thái độc lập. Nếu chỉ sao chép tham chiếu đến collection nội bộ, object mới vẫn có thể chia sẻ dữ liệu khả biến với object cũ.

Một lựa chọn tốt hơn là thiết kế object phiên bất biến. Ví dụ sau dùng Java record và tạo một danh sách mới mỗi khi thêm sản phẩm:

~~~java
import java.util.ArrayList;
import java.util.List;

public record CartItem(String productId, int quantity) {
}

public record Cart(List<CartItem> items) {

    public Cart {
        items = List.copyOf(items);
    }

    public Cart add(CartItem item) {
        List<CartItem> next = new ArrayList<>(items);
        next.add(item);
        return new Cart(next);
    }
}
~~~

Cách sử dụng:

~~~java
Cart current = (Cart) session.getAttribute("cart");

if (current == null) {
    current = new Cart(List.of());
}

Cart updated = current.add(new CartItem("BOOK-02", 1));
session.setAttribute("cart", updated);
~~~

`Cart` mới chứa danh sách không thể sửa qua API collection thông thường. Phương thức `add` tạo danh sách mới, sau đó tạo một `Cart` mới. Lời gọi `setAttribute` làm rõ thuộc tính cần cập nhật.

Ví dụ sử dụng record yêu cầu Java 16 trở lên. Với Java cũ hơn, có thể dùng class thông thường nhưng vẫn giữ nguyên nguyên tắc: field nên là `final` khi có thể, không trả về collection khả biến trực tiếp và mỗi lần cập nhật tạo ra trạng thái mới.

### Nếu bắt buộc phải dùng object khả biến

Có những trường hợp thư viện hoặc mô hình hiện tại dùng object khả biến. Khi đó, có thể sửa object rồi gọi lại `setAttribute`:

~~~java
Cart cart = (Cart) session.getAttribute("cart");

if (cart == null) {
    cart = new Cart();
}

cart.addItem(new CartItem("BOOK-02", 1));

// Gọi lại để Spring Session ghi nhận thuộc tính đã được đặt.
session.setAttribute("cart", cart);
~~~

Cách này giúp session repository nhận biết thuộc tính đã được cập nhật theo cơ chế theo dõi của nó. Tuy nhiên, cần nhớ rằng `cart` vẫn là object khả biến. Code khác trong cùng request hoặc request đồng thời có thể thay đổi trạng thái mà không có sự cô lập cần thiết.

Nếu cấu trúc dữ liệu phức tạp, hãy cân nhắc tạo snapshot mới hoặc lưu dữ liệu nghiệp vụ bên ngoài session.

## 6. Không lưu object tùy tiện vào session

Một thuộc tính session được lưu trong Redis hoặc JDBC thường phải được serialize để truyền hoặc ghi vào kho lưu trữ. Vì thế, object lưu trong session cần đáp ứng yêu cầu của serializer đang cấu hình.

Nên ưu tiên:

- String, số, boolean và các kiểu giá trị đơn giản.
- DTO nhỏ, có cấu trúc ổn định.
- Collection có phần tử cũng serialize được.
- Object bất biến hoặc có quy tắc sao chép rõ ràng.

Cần thận trọng khi lưu:

- Entity ORM có lazy proxy hoặc quan hệ hai chiều phức tạp.
- Object giữ tham chiếu đến `HttpServletRequest`, `HttpServletResponse`, stream hoặc connection.
- Thread, executor, service bean hoặc object phụ thuộc vòng đời của một request.
- File lớn, ảnh hoặc dữ liệu nhị phân dung lượng cao.
- Object thay đổi cấu trúc thường xuyên giữa các lần triển khai.

Ví dụ, lưu một entity JPA trực tiếp có thể kéo theo proxy hoặc quan hệ chưa được tải. Khi request sau đọc object đã deserialize, persistence context ban đầu không còn tồn tại. Thay vì lưu entity, nên lưu ID hoặc DTO nhỏ rồi truy vấn dữ liệu nghiệp vụ khi cần.

### Tương thích khi triển khai nhiều instance

Khi nhiều instance dùng chung repository, mọi instance cần hiểu được định dạng dữ liệu session. Nếu một phiên bản ghi một kiểu object mới nhưng instance cũ không thể deserialize, request có thể lỗi khi đọc session.

Trong rolling deployment, nên duy trì tương thích ngược cho DTO trong thời gian các phiên bản cùng hoạt động. Có thể dùng các field đơn giản, thêm field theo hướng tương thích, hoặc lưu một cấu trúc dữ liệu có version để xử lý chuyển đổi khi cần.

## 7. Thay đổi object trong session không bảo đảm cập nhật đồng thời an toàn

Giả sử hai request cùng sử dụng một session và cùng đọc giỏ hàng có một sản phẩm:

~~~text
Ban đầu: cart = [BOOK-01]

Request A đọc cart
Request B đọc cart

Request A thêm BOOK-02
Request B thêm BOOK-03

Request A ghi cart = [BOOK-01, BOOK-02]
Request B ghi cart = [BOOK-01, BOOK-03]
~~~

Nếu hai request đọc hai snapshot giống nhau và lần lượt ghi toàn bộ thuộc tính, request ghi sau có thể ghi đè thay đổi của request ghi trước. Kết quả có thể mất `BOOK-02` hoặc `BOOK-03`. Đây là hiện tượng lost update.

Ngay cả khi mỗi request đều gọi `setAttribute`, điều đó không có nghĩa thao tác đọc-sửa-ghi được khóa hoặc thực hiện nguyên tử trên Redis/JDBC. Session repository dùng chung giúp nhiều instance truy cập cùng phiên, nhưng không tự biến mọi cập nhật object thành transaction.

Các hướng xử lý:

1. Giữ thuộc tính session nhỏ và tránh đặt dữ liệu nghiệp vụ có tần suất cập nhật cao vào một object session lớn.
2. Đối với giỏ hàng hoặc dữ liệu cần giữ mọi cập nhật, lưu dữ liệu ở repository nghiệp vụ có transaction, version hoặc thao tác nguyên tử thích hợp.
3. Dùng optimistic locking hoặc cơ chế kiểm tra version nếu kho dữ liệu hỗ trợ và nghiệp vụ yêu cầu.
4. Với thao tác cộng dồn, cân nhắc câu lệnh nguyên tử hoặc transaction ở nơi lưu dữ liệu nghiệp vụ.
5. Xác định rõ cách xử lý khi hai request cập nhật cùng lúc: từ chối một thao tác, thử lại, hợp nhất thay đổi hay chấp nhận quy tắc last-write-wins.

Không nên dựa vào `synchronized` trên object session trong một instance để bảo vệ dữ liệu dùng chung giữa nhiều instance. Khóa trong bộ nhớ của App A không tự đồng bộ với khóa trong App B.

## 8. Kiểm thử việc thay đổi thuộc tính khả biến

Kiểm thử chỉ xác nhận object thay đổi trong cùng request là chưa đủ. Cần kiểm tra trạng thái sau khi session được lưu và được đọc lại ở một request tiếp theo.

Một quy trình kiểm thử có thể gồm:

1. Tạo session và đặt thuộc tính chứa collection hoặc DTO.
2. Thực hiện request thay đổi object tại chỗ mà không gọi `setAttribute`.
3. Kết thúc request để Spring Session thực hiện cơ chế lưu.
4. Gửi request mới với cùng cookie session.
5. Đọc thuộc tính và xác minh thay đổi có hoặc không được giữ lại theo `SaveMode` đang cấu hình.
6. Lặp lại với cách cập nhật gọi `setAttribute`.
7. Kiểm thử với repository thật hoặc môi trường tích hợp tương đương cấu hình production.

Ví dụ test ở mức controller/service có thể minh họa sự khác nhau giữa hai cách cập nhật. Để xác minh hành vi lưu thực tế, cần dùng repository tương ứng; mock `HttpSession` đơn giản thường chỉ giữ tham chiếu object trong bộ nhớ và không mô phỏng serialization hay dirty tracking của Redis/JDBC.

Một ma trận kiểm thử hữu ích:

| Tình huống | Điều cần xác minh |
|---|---|
| Sửa object khả biến, không gọi `setAttribute` | Thuộc tính có được ghi theo SaveMode hiện tại không? |
| Sửa object rồi gọi `setAttribute` | Thay đổi có được đọc lại ở request tiếp theo không? |
| Dùng `ON_GET_ATTRIBUTE` | Thuộc tính được đọc có nằm trong tập thuộc tính cần lưu không? |
| Dùng `ALWAYS` | Tất cả thuộc tính có được ghi và chi phí ghi có chấp nhận được không? |
| Dùng `ON_SAVE` và `IMMEDIATE` | Thời điểm dữ liệu được đẩy xuống repository có đúng kỳ vọng không? |
| Hai request cập nhật đồng thời | Có mất cập nhật hoặc ghi đè dữ liệu không? |
| Nhiều instance cùng repository | Instance khác có deserialize và đọc đúng phiên bản dữ liệu không? |

Khi viết integration test, cần giữ cùng cookie hoặc Session ID giữa các request. Nếu mỗi request tạo một session mới, test sẽ không kiểm tra được tính liên tục của thuộc tính.

## 9. Ví dụ minh họa một endpoint cập nhật giỏ hàng

Ví dụ dưới đây dùng `HttpSession` và object bất biến để mỗi lần cập nhật tạo ra một giá trị mới. Đây là cách thể hiện rõ ý định cập nhật thuộc tính; trong hệ thống thực tế, giỏ hàng có thể cần được lưu trong cơ sở dữ liệu nghiệp vụ.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
public class CartController {

    @PostMapping("/cart/items")
    public Cart addItem(
            HttpServletRequest request,
            @RequestParam String productId,
            @RequestParam int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải lớn hơn 0");
        }

        HttpSession session = request.getSession();

        Cart current = (Cart) session.getAttribute("cart");
        if (current == null) {
            current = new Cart(List.of());
        }

        Cart updated = current.add(new CartItem(productId, quantity));

        // Đặt lại thuộc tính để session nhận biết thay đổi.
        session.setAttribute("cart", updated);

        return updated;
    }
}
~~~

Trong ví dụ này:

- Request tạo hoặc lấy session hiện tại.
- Ứng dụng lấy `Cart` từ thuộc tính `cart`.
- Nếu chưa có giỏ hàng, ứng dụng tạo một giá trị rỗng.
- Phương thức `add` tạo object mới.
- `setAttribute` đặt giá trị mới vào session.
- Repository Spring Session có thể lưu thuộc tính theo cấu hình SaveMode và FlushMode.

Endpoint này chỉ minh họa thao tác session. Ứng dụng thực tế còn phải kiểm tra sản phẩm tồn tại, quyền truy cập, giới hạn số lượng, giá và quy tắc nghiệp vụ. Không nên tin dữ liệu do client gửi chỉ vì nó được gắn với một session hợp lệ.

## 10. Checklist khi thiết kế thuộc tính session

Trước khi đưa một object vào session, hãy tự hỏi:

- Object có thể thay đổi sau khi được lưu không?
- Có collection hoặc object lồng nhau không?
- Code có gọi `setAttribute` sau khi cập nhật không?
- `SaveMode` đang dùng có nhận biết được loại thay đổi này không?
- `FlushMode` ghi dữ liệu vào thời điểm nào?
- Object có serialize được bằng cấu hình repository hiện tại không?
- Nhiều phiên bản ứng dụng có đọc được cùng định dạng object không?
- Nhiều request có thể cập nhật cùng thuộc tính đồng thời không?
- Dữ liệu có thực sự thuộc về ngữ cảnh phiên hay nên nằm trong kho nghiệp vụ?

## 11. Những nhầm lẫn thường gặp

**“Lấy object từ session rồi sửa field thì session chắc chắn tự lưu.”**  
Thay đổi tại chỗ có thể không được cơ chế dirty tracking nhận biết. Hãy gọi `setAttribute` sau khi cập nhật hoặc dùng object bất biến và đặt giá trị mới.

**“Gọi setAttribute là mọi thay đổi đều được ghi ngay xuống Redis.”**  
Thao tác này có thể đánh dấu thuộc tính cần lưu. Thời điểm ghi còn phụ thuộc `FlushMode`, repository và vòng đời request.

**“Dùng SaveMode.ALWAYS thì không còn lỗi đồng thời.”**  
Chế độ này có thể ghi mọi thuộc tính, nhưng không tự ngăn hai request ghi đè snapshot của nhau.

**“Tạo một object mới là đã sao chép độc lập.”**  
Nếu object mới giữ chung collection hoặc object con khả biến, thay đổi lồng nhau vẫn có thể ảnh hưởng cả hai.

**“Mock HttpSession là đủ để kiểm tra Redis Session.”**  
Mock không mô phỏng đầy đủ serialization, dirty tracking, TTL, flush và hành vi repository. Cần integration test với repository tương ứng cho các đặc tính đó.

## 12. Tự kiểm tra

1. Đối tượng khả biến là gì? Nêu hai ví dụ có thể lưu trong session.
2. Vì sao `list.add(...)` có thể không làm Spring Session ghi lại thuộc tính?
3. `setAttribute` có vai trò gì sau khi thay đổi một object khả biến?
4. `SaveMode.ON_SET_ATTRIBUTE` khác `SaveMode.ALWAYS` như thế nào?
5. `FlushMode` trả lời câu hỏi gì và khác `SaveMode` ở điểm nào?
6. Vì sao sao chép nông một object chứa `List` chưa chắc tạo ra trạng thái độc lập?
7. Vì sao hai request đồng thời cùng sửa giỏ hàng có thể gây lost update dù cả hai đều gọi `setAttribute`?
8. Cần kiểm tra điều gì trong integration test để xác nhận thay đổi đã được lưu và đọc lại qua request mới?

### Gợi ý trả lời

1. Object khả biến cho phép thay đổi trạng thái sau khi tạo; ví dụ `ArrayList` và một lớp `Cart` có phương thức `addItem`.
2. `list.add` chỉ sửa object được tham chiếu. Nếu repository theo dõi thao tác đặt thuộc tính, nó có thể không biết thuộc tính chứa danh sách đã đổi.
3. `setAttribute` thông báo rõ thuộc tính được cập nhật và giúp cơ chế theo dõi thay đổi của session đánh dấu thuộc tính cần lưu.
4. `ON_SET_ATTRIBUTE` tập trung vào thuộc tính đã được đặt hoặc đánh dấu thay đổi; `ALWAYS` lưu mọi thuộc tính khi session được lưu.
5. `FlushMode` quyết định thời điểm ghi; `SaveMode` quyết định phạm vi thuộc tính được ghi.
6. Bản sao nông có thể dùng chung danh sách hoặc object con với object ban đầu.
7. Mỗi request có thể đọc một snapshot cũ và ghi toàn bộ thuộc tính; lần ghi sau có thể ghi đè thay đổi của lần ghi trước.
8. Cần dùng cùng cookie session, kết thúc request ghi, gửi request mới và đọc lại thuộc tính từ repository thật với cấu hình SaveMode/FlushMode đang kiểm tra.

## Kết luận

Thuộc tính `HttpSession` có thể chứa object khả biến, nhưng sửa object trong bộ nhớ không phải lúc nào cũng đồng nghĩa Spring Session biết rằng thuộc tính cần được ghi lại. Với repository Redis hoặc JDBC, cần quan tâm cách dirty tracking nhận biết thay đổi, `SaveMode` chọn thuộc tính nào và `FlushMode` quyết định thời điểm lưu.

Cách cập nhật rõ ràng là tạo trạng thái mới, gọi `setAttribute` và ưu tiên object bất biến hoặc snapshot độc lập. Với object khả biến hiện có, hãy gọi lại `setAttribute` sau khi sửa và kiểm thử bằng request tiếp theo trên repository thực tế. Nếu dữ liệu cần cập nhật chính xác giữa nhiều request hoặc nhiều instance, hãy dùng cơ chế transaction, version hoặc thao tác nguyên tử ở tầng dữ liệu nghiệp vụ phù hợp.

