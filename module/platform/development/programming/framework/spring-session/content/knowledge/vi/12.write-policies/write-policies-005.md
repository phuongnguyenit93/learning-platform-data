# Thay đổi trực tiếp một đối tượng đã lấy ra từ thuộc tính

Một thuộc tính trong `HttpSession` có thể chứa một object mutable như giỏ hàng, danh sách lựa chọn hoặc bộ lọc tìm kiếm. Khi gọi `getAttribute()`, ứng dụng nhận về tham chiếu tới object đó và có thể thay đổi nội dung của nó mà không gọi lại `setAttribute()`. Với Spring Session, cách thay đổi này cần được hiểu cùng `SaveMode` và `FlushMode`: repository phải biết thuộc tính nào cần lưu, rồi mới quyết định thời điểm ghi dữ liệu vào Redis hoặc JDBC.

Nếu repository chỉ lưu những thuộc tính được gán bằng `setAttribute()`, việc gọi `cart.add(product)` có thể chỉ thay đổi object trong bộ nhớ của request mà không đánh dấu thuộc tính là cần ghi. Kết quả là request kế tiếp hoặc instance khác đọc được giá trị cũ. Cách an toàn, dễ hiểu nhất là thay đổi object xong gọi lại `session.setAttribute()`; hoặc dùng object immutable và thay bằng instance mới. Nếu muốn cho phép mutate trực tiếp, cần chọn `SaveMode` phù hợp và hiểu tác động tới số lần ghi.

## 1. Tham chiếu object trong session và thay đổi bên trong object

`HttpSession` lưu các cặp tên thuộc tính và giá trị. Ví dụ:

```java
HttpSession session = request.getSession();
session.setAttribute("cart", new Cart());
```

Lệnh `setAttribute` gắn object `Cart` vào session. Ở request sau:

```java
Cart cart = (Cart) session.getAttribute("cart");
cart.add(product);
```

`getAttribute` trả về object `Cart` đang được giữ trong session context của request. `cart.add(product)` gọi method trên object; nó không gọi `HttpSession.setAttribute()`. Từ góc nhìn API session, không có thao tác gán hay xóa thuộc tính nào vừa diễn ra.

Điểm này khác với việc thay thế thuộc tính:

```java
Cart cart = (Cart) session.getAttribute("cart");
cart.add(product);
session.setAttribute("cart", cart);
```

Lệnh cuối thông báo rõ ràng cho session wrapper rằng thuộc tính `cart` đã được đặt lại. Với chính sách ghi chỉ theo `setAttribute`, đây là tín hiệu quan trọng để đánh dấu thuộc tính cần lưu.

Có thể mô tả sự khác nhau như sau:

```mermaid
flowchart TD
    A[getAttribute("cart")] --> B[Nhận tham chiếu Cart]
    B --> C[cart.add(product)]
    C --> D{Có gọi setAttribute?}
    D -->|Không| E[SaveMode có thể không đánh dấu thuộc tính]
    D -->|Có| F[Thuộc tính được đánh dấu cần lưu]
    E --> G[Có nguy cơ request sau đọc dữ liệu cũ]
    F --> H[Repository ghi theo FlushMode]
```

## 2. Vì sao thay đổi object không tự động được nhận biết?

Spring Session cần serialize session attributes để lưu vào Redis hoặc JDBC. Việc serialize thường diễn ra khi repository lưu phiên, nhưng repository còn phải quyết định thuộc tính nào cần đưa vào lần ghi đó. `SaveMode` điều khiển quyết định này.

Object mutable có thể thay đổi trạng thái nội bộ mà không tạo ra lời gọi nào tới `HttpSession`. Ví dụ `ArrayList.add()`, `HashMap.put()` hoặc `cart.setQuantity(...)` chỉ sửa object. Nếu chính sách save chỉ theo dõi các thao tác `setAttribute`, repository không biết nội dung object đã thay đổi.

Đây không phải lỗi riêng của Redis. Cùng vấn đề có thể xuất hiện với bất kỳ repository Spring Session nào áp dụng dirty tracking theo thao tác session. Kho dữ liệu có thể kết nối tốt, session vẫn tồn tại và request vẫn chạy thành công, nhưng một thuộc tính không được đánh dấu để lưu sẽ không được cập nhật như mong đợi.

Ví dụ tình huống:

1. Request A đọc giỏ hàng từ session. Giỏ có một sản phẩm.
2. Mã ứng dụng gọi `cart.add(secondProduct)`.
3. Ứng dụng không gọi `session.setAttribute("cart", cart)`.
4. Spring Session lưu phiên theo chính sách chỉ lưu thuộc tính đã được set.
5. Request B đọc session và vẫn thấy giỏ hàng cũ.

Khi điều tra, cần kiểm tra cả object mutation và `SaveMode`; chỉ nhìn thấy repository `save()` được gọi không đủ để kết luận mọi thuộc tính đã được serialize lại.

## 3. SaveMode quyết định thuộc tính nào được ghi

Spring Session cung cấp các lựa chọn `SaveMode` để cân bằng giữa tính tiện lợi và chi phí ghi dữ liệu. Tên enum và hành vi chi tiết cần đối chiếu phiên bản Spring Session đang dùng, nhưng các chế độ phổ biến có ý nghĩa sau:

| SaveMode | Thuộc tính được xem xét để lưu | Hệ quả với object mutable |
| --- | --- | --- |
| `ON_SET_ATTRIBUTE` | Thuộc tính đã được đặt qua `setAttribute` trong request | Mutate nội bộ mà không gọi lại `setAttribute` có thể không được lưu |
| `ON_GET_ATTRIBUTE` | Thuộc tính đã được đọc qua `getAttribute` trong request | Có thể lưu thay đổi sau khi đọc, kể cả khi mã không gọi lại `setAttribute` |
| `ALWAYS` | Tất cả thuộc tính của session khi lưu | Bắt được thay đổi nội bộ nhưng có thể serialize nhiều dữ liệu hơn |

`ON_SET_ATTRIBUTE` thường tiết kiệm ghi hơn khi ứng dụng thay thế thuộc tính một cách tường minh. Nó phù hợp với object immutable hoặc quy ước luôn gọi lại `setAttribute` sau khi sửa object mutable.

`ON_GET_ATTRIBUTE` hữu ích khi ứng dụng cần sửa trực tiếp object đã lấy ra. Việc đọc thuộc tính làm cho thuộc tính đó được đưa vào tập cần lưu trong lần lưu phiên. Tuy nhiên, mọi request chỉ đọc thuộc tính cũng có thể làm thuộc tính được lưu lại dù không có thay đổi. Điều này có thể tăng serialization, lượng ghi Redis/JDBC và tranh chấp khi nhiều request cùng cập nhật session.

`ALWAYS` lưu mọi thuộc tính khi session được lưu. Chế độ này đơn giản về mặt hành vi vì không phụ thuộc vào việc thuộc tính có được đọc hoặc set trong request hay không, nhưng có thể ghi lại object lớn hoặc nhiều thuộc tính không thay đổi. Với session có nhiều dữ liệu, chi phí CPU serialize, băng thông và I/O có thể tăng đáng kể.

Ví dụ cấu hình trong Spring Boot, nếu phiên bản đang dùng hỗ trợ các property này:

```yaml
spring:
  session:
    redis:
      save-mode: on-set-attribute
      flush-mode: on-save
```

Muốn hỗ trợ các thay đổi trực tiếp trên object đã đọc, có thể cân nhắc:

```yaml
spring:
  session:
    redis:
      save-mode: on-get-attribute
      flush-mode: on-save
```

Đây là ví dụ cho repository Redis; tên property và giá trị mặc định có thể thay đổi theo phiên bản Boot/Spring Session. Với JDBC hoặc repository khác, kiểm tra cấu hình tương ứng. Không đổi sang `ALWAYS` chỉ để che một lỗi cập nhật chưa rõ nguyên nhân; trước tiên xác định quy ước thay đổi thuộc tính của ứng dụng.

## 4. FlushMode quyết định thời điểm ghi

`SaveMode` trả lời câu hỏi “thuộc tính nào cần lưu?”, còn `FlushMode` trả lời “khi nào thay đổi được ghi vào repository?”. Hai chính sách độc lập và cần được hiểu cùng nhau.

| FlushMode | Thời điểm ghi điển hình | Tác động |
| --- | --- | --- |
| `ON_SAVE` | Khi Spring Session hoàn tất quy trình lưu phiên, thường ở cuối request | Cho phép gom thay đổi rồi lưu; request cần hoàn tất bước save |
| `IMMEDIATE` | Ghi ngay khi có thay đổi session mà repository nhận biết | Có thể giảm khoảng thời gian thay đổi chưa được gửi đi, nhưng tăng số lần ghi |

Điểm quan trọng: `IMMEDIATE` không tự phát hiện mọi thay đổi bên trong object Java. Nếu `SaveMode` không đánh dấu thuộc tính là dirty, việc đặt `FlushMode.IMMEDIATE` không biến một lời gọi `cart.add(product)` thành `setAttribute`. Flush mode chỉ quyết định thời điểm ghi những thay đổi mà session/repository đã nhận biết.

Với `ON_GET_ATTRIBUTE` kết hợp `IMMEDIATE`, cần cẩn thận về thứ tự: thao tác `getAttribute()` có thể đánh dấu và flush thuộc tính ngay tại thời điểm đọc, trước khi mã gọi `cart.add(product)`. Không nên dựa vào tổ hợp này để bảo đảm mutation sau lần đọc được ghi ngay. Cách chắc chắn hơn là gọi `setAttribute` sau khi mutate, hoặc dùng `ON_SAVE` để các thuộc tính đã đọc được lưu ở cuối request theo chính sách của repository.

Ví dụ cấu hình `ON_SAVE`:

```java
@EnableRedisHttpSession(
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE
)
class SessionConfig {
}
```

Annotation và thuộc tính cấu hình có thể khác theo phiên bản; trong Spring Boot auto-configuration, nên ưu tiên property được phiên bản hỗ trợ thay vì khai báo thêm cấu hình thủ công trùng lặp. Không khai báo đồng thời hai cấu hình repository hoặc hai `SessionRepositoryFilter` cho cùng ứng dụng.

## 5. Cách an toàn nhất: mutate xong gọi lại setAttribute

Nếu ứng dụng đang dùng `ON_SET_ATTRIBUTE`, quy ước dễ kiểm tra nhất là gọi lại `setAttribute` sau mọi thay đổi nội bộ của object.

```java
@PostMapping("/cart/items")
public String addItem(@RequestParam String productId,
                      HttpServletRequest request) {
    HttpSession session = request.getSession();

    Cart cart = (Cart) session.getAttribute("cart");
    if (cart == null) {
        cart = new Cart();
    }

    cart.add(productId);

    // Đánh dấu rõ thuộc tính cần lưu.
    session.setAttribute("cart", cart);

    return "redirect:/cart";
}
```

Lệnh `setAttribute` sau mutation làm rõ ý định và giúp hoạt động ổn định với chính sách `ON_SET_ATTRIBUTE`. Với `FlushMode.ON_SAVE`, repository ghi thay đổi khi request hoàn tất quy trình lưu. Với `IMMEDIATE`, thay đổi được gửi sớm theo hành vi của implementation.

Nếu thuộc tính chưa tồn tại, có thể khởi tạo object rồi set trực tiếp. Nếu xóa thuộc tính, dùng `removeAttribute("cart")`; không chỉ đặt một field bên trong object thành `null` nếu mục tiêu là loại bỏ cả thuộc tính khỏi session.

Đặt quy ước này trong service hoặc helper chuyên quản lý session thay vì để mỗi controller tự nhớ. Ví dụ một phương thức `updateCart` có thể đọc, mutate, rồi gọi `setAttribute` trong cùng một nơi. Điều này giảm khả năng một endpoint quên đánh dấu thay đổi.

## 6. Ưu tiên object immutable khi có thể

Object immutable không thay đổi trạng thái sau khi được tạo. Khi cần cập nhật, ứng dụng tạo object mới và gán lại thuộc tính session. Cách này làm thay đổi trở nên tường minh, hỗ trợ `ON_SET_ATTRIBUTE` và giảm rủi ro nhiều đoạn mã cùng sửa một object.

Ví dụ:

```java
public record Cart(List<String> productIds) {
    public Cart {
        productIds = List.copyOf(productIds);
    }

    public Cart add(String productId) {
        List<String> updated = new ArrayList<>(productIds);
        updated.add(productId);
        return new Cart(updated);
    }
}
```

Sử dụng:

```java
Cart current = (Cart) session.getAttribute("cart");
if (current == null) {
    current = new Cart(List.of());
}

Cart updated = current.add(productId);
session.setAttribute("cart", updated);
```

Record trong ví dụ là immutable ở mức cấu trúc nếu các thành phần bên trong cũng immutable. `List.copyOf` tạo danh sách không thể sửa qua tham chiếu trả về. Nếu lưu object qua serializer yêu cầu Java serialization, cần bảo đảm kiểu dữ liệu đáp ứng yêu cầu của serializer; record không tự động triển khai `Serializable` nếu ứng dụng dùng Java serialization.

Immutable object không giải quyết mọi vấn đề đồng thời: hai request vẫn có thể cùng đọc một phiên bản cũ rồi tạo hai phiên bản mới và ghi đè nhau. Tuy nhiên, immutable làm rõ dữ liệu đầu vào/đầu ra của thao tác cập nhật và tránh mutation âm thầm.

## 7. Khi nào dùng ON_GET_ATTRIBUTE hoặc ALWAYS?

Có trường hợp ứng dụng kế thừa mã cũ và nhiều nơi gọi `getAttribute()` rồi sửa object trực tiếp. Khi không thể sửa ngay mọi điểm sử dụng, `ON_GET_ATTRIBUTE` có thể giúp lưu các thuộc tính đã được đọc trong request. Tuy vậy, cần cân nhắc các tác động:

- Một request chỉ đọc giỏ hàng cũng có thể ghi lại giỏ hàng.
- Một request đọc nhiều thuộc tính có thể làm tăng số object được serialize.
- Nhiều request đồng thời cùng đọc rồi ghi thuộc tính có thể tăng nguy cơ last-write-wins.
- Với `FlushMode.IMMEDIATE`, thời điểm flush khi đọc có thể xảy ra trước mutation; cần kiểm thử cụ thể.

`ALWAYS` có thể hữu ích khi ứng dụng cần semantics đơn giản hoặc có nhiều code cũ sửa object trong session mà không thể kiểm soát truy cập. Đổi lại, mỗi lần lưu session có thể ghi toàn bộ attributes, kể cả dữ liệu lớn và không thay đổi. Trước khi chọn, đo kích thước session, thời gian serialize, số lần ghi và tải kho dữ liệu.

Không có một `SaveMode` tối ưu cho mọi ứng dụng. Nếu session chỉ chứa vài giá trị nhỏ và lưu lượng thấp, `ALWAYS` có thể chấp nhận được. Với ứng dụng lớn, nhiều thuộc tính hoặc nhiều request đồng thời, quy ước cập nhật tường minh thường dễ tối ưu và kiểm thử hơn.

## 8. Serialization và dữ liệu mutable

Spring Session phải chuyển thuộc tính thành dữ liệu lưu trữ. Với Redis, serializer được cấu hình sẽ encode/decode object; với JDBC, dữ liệu session được lưu theo schema và serialization strategy tương ứng. Việc mutate object trong request không đồng nghĩa Redis/JDBC đã thay đổi ngay lập tức: thay đổi chỉ tồn tại trong object đang được ứng dụng sử dụng cho đến khi repository serialize và ghi nó.

Một số nguyên tắc khi chọn object lưu trong session:

- Ưu tiên object nhỏ, cấu trúc ổn định và dễ serialize.
- Tránh lưu entity ORM đang gắn với persistence context, lazy proxy, JDBC connection, stream, thread hoặc object chứa tài nguyên không thể serialize.
- Tránh giữ cả object graph lớn khi chỉ cần ID và một vài trường hiển thị.
- Bảo đảm các instance đang chạy song song có thể deserialize dữ liệu do phiên bản ứng dụng khác ghi.
- Khi thay đổi class hoặc serializer, có kế hoạch tương thích với session cũ còn tồn tại trong Redis/JDBC.

Nếu deserialize thất bại, request có thể lỗi khi đọc session attribute dù Redis connection vẫn bình thường. Hãy phân biệt lỗi serialization với lỗi không tìm thấy session và lỗi kết nối kho dữ liệu.

## 9. Request đồng thời và nguy cơ mất cập nhật

`HttpSession` không phải cơ sở dữ liệu giao dịch. Hai request từ cùng trình duyệt có thể cùng đọc một object rồi thay đổi song song. Ví dụ:

1. Request A đọc giỏ hàng có số lượng 1.
2. Request B cũng đọc giỏ hàng có số lượng 1.
3. A thêm một sản phẩm và lưu giỏ có số lượng 2.
4. B thêm sản phẩm khác trên bản object cũ rồi lưu giỏ có số lượng 2.
5. Giá trị cuối có thể chỉ giữ thay đổi của B, làm mất thay đổi của A.

Đây là tình huống lost update. `SaveMode.ALWAYS` không tự hợp nhất hai object; nó chỉ bảo đảm thuộc tính được ghi. `ON_GET_ATTRIBUTE` cũng không cung cấp khóa hay version check. `FlushMode.IMMEDIATE` thay đổi thời điểm ghi, không biến hai thao tác thành transaction.

Với dữ liệu nghiệp vụ quan trọng như giỏ hàng cần tính tiền, số lượng tồn kho, hạn mức hoặc quyền, nên lưu trạng thái chính trong database/service có transaction và cơ chế concurrency control. Session chỉ nên giữ một ID, snapshot hiển thị hoặc trạng thái điều hướng ngắn hạn. Nếu buộc phải lưu mutable object trong session, cân nhắc khóa phù hợp hoặc version/compare-and-set ở tầng dữ liệu; không dựa vào đồng bộ của một instance vì request có thể tới instance khác.

## 10. Sự kiện thuộc tính và quan sát thay đổi

Servlet có các listener như `HttpSessionAttributeListener` để nhận thông báo khi thuộc tính được thêm, thay thế hoặc xóa qua API session. Việc gọi `cart.add(product)` chỉ thay đổi field bên trong object; nó không tự phát sự kiện `attributeAdded`, `attributeReplaced` hoặc `attributeRemoved` vì không có thao tác set/remove thuộc tính nào diễn ra.

Nếu ứng dụng cần audit thay đổi giỏ hàng hoặc đồng bộ cache, không dựa vào listener session để phát hiện mọi mutation bên trong object. Hãy phát domain event từ service thực hiện nghiệp vụ, hoặc dùng object immutable và một lệnh cập nhật rõ ràng để sự kiện được tạo tại đúng nơi thay đổi xảy ra.

Không ghi toàn bộ object session vào log để debug. Log tên thuộc tính, loại thao tác, correlation ID và kết quả tổng quát; tránh session ID, cookie, token hoặc dữ liệu cá nhân nhạy cảm.

## 11. Kiểm thử chính sách ghi

Kiểm thử cần xác minh dữ liệu sau một request mới, không chỉ kiểm tra object trong cùng request. Một bộ test hữu ích:

| Kịch bản | SaveMode | Điều cần xác minh |
| --- | --- | --- |
| Mutate object sau `getAttribute`, không gọi `setAttribute` | `ON_SET_ATTRIBUTE` | Thay đổi có thể không được lưu |
| Mutate object sau `getAttribute`, không gọi `setAttribute` | `ON_GET_ATTRIBUTE` + `ON_SAVE` | Thuộc tính đã đọc được lưu ở cuối request theo chính sách |
| Mutate object rồi gọi `setAttribute` | `ON_SET_ATTRIBUTE` | Thay đổi được đánh dấu để lưu |
| Request chỉ đọc thuộc tính | `ON_GET_ATTRIBUTE` | Thuộc tính có thể vẫn bị ghi dù không đổi |
| Lưu mọi thuộc tính | `ALWAYS` | Thuộc tính được ghi khi session save |
| Hai request cùng mutate | Mọi chế độ | Kiểm tra lost update và thứ tự ghi |
| Đổi serializer/class giữa phiên bản | Mọi chế độ | Kiểm tra deserialize dữ liệu session cũ |

Ví dụ kiểm thử tích hợp nên thực hiện qua HTTP:

1. Gửi request khởi tạo session và đặt `cart`.
2. Lưu cookie session từ response.
3. Gửi request cập nhật bằng cookie đó; mutate cart theo đúng trường hợp đang kiểm thử.
4. Gửi request mới với cùng cookie để đọc cart từ repository.
5. So sánh kết quả với kỳ vọng và kiểm tra Redis/JDBC nếu cần.

Với `ON_SET_ATTRIBUTE`, viết hai test riêng: một test mutate mà không set lại và một test mutate rồi set lại. Test này chứng minh quy ước của ứng dụng. Với `ON_GET_ATTRIBUTE`, thêm test chỉ đọc để đo việc thuộc tính được lưu lại ngoài dự kiến. Dùng Redis hoặc JDBC thật trong integration test để xác minh serialization và thời điểm ghi; mock repository chỉ xác minh logic service.

Để kiểm tra concurrency, gửi hai request đồng thời từ hai client dùng cùng cookie session, mỗi request cập nhật một phần khác nhau của object. Xác minh có mất cập nhật không. Nếu nghiệp vụ cần bảo toàn cả hai thay đổi, test phải chứng minh cơ chế đồng bộ/transaction ở tầng dữ liệu, không chỉ chứng minh một lần gọi `setAttribute` thành công.

## 12. Lỗi thường gặp và cách chẩn đoán

**Thay đổi object biến mất sau request.** Kiểm tra `SaveMode`. Nếu đang dùng `ON_SET_ATTRIBUTE`, tìm nơi mutate object và gọi lại `setAttribute` sau mutation. Xác nhận request đã hoàn tất bước save và không có exception serialization.

**Đã bật `FlushMode.IMMEDIATE` nhưng mutation vẫn mất.** Flush mode không tự phát hiện mutation bên trong object. Kiểm tra thuộc tính đã được đánh dấu dirty chưa; gọi `setAttribute` sau khi thay đổi hoặc chọn save mode phù hợp.

**Đổi sang `ON_GET_ATTRIBUTE` nhưng Redis ghi quá nhiều.** Các request đọc thuộc tính cũng có thể làm thuộc tính được lưu. Đo số lần ghi, kích thước object và số thuộc tính được truy cập; cân nhắc quay lại `ON_SET_ATTRIBUTE` và cập nhật mã để set lại sau mutation.

**Một request ghi đè thay đổi của request khác.** Kiểm tra request đồng thời cùng đọc snapshot cũ và lưu object mới. Session không tự merge collection hoặc object graph; chuyển dữ liệu quan trọng sang nơi có transaction hoặc concurrency control.

**Listener không ghi nhận thay đổi field trong object.** `HttpSessionAttributeListener` chỉ quan sát thao tác set/remove attribute, không quan sát method call bên trong object. Phát domain event tại service hoặc set lại attribute theo quy ước.

**Lỗi deserialize sau deploy.** Kiểm tra serializer, class version, kiểu object lưu trong session và khả năng tương thích giữa các instance trong rolling deployment. Giữ session attributes nhỏ và ổn định.

## 13. Quy trình chọn chính sách ghi

1. Liệt kê các session attributes và xác định loại nào mutable, loại nào immutable.
2. Tìm tất cả nơi gọi `getAttribute()` rồi sửa object mà không gọi `setAttribute()`.
3. Nếu có thể sửa mã, chuẩn hóa quy ước mutate xong set lại hoặc chuyển sang immutable object.
4. Dùng `ON_SET_ATTRIBUTE` khi thay đổi được đánh dấu tường minh và cần giảm ghi không cần thiết.
5. Cân nhắc `ON_GET_ATTRIBUTE` cho mã legacy cần lưu object đã đọc, nhưng đo chi phí và chọn `FlushMode` phù hợp.
6. Chỉ dùng `ALWAYS` khi chi phí ghi toàn bộ thuộc tính chấp nhận được và semantics đơn giản có giá trị rõ ràng.
7. Kiểm thử sau request mới, qua instance khác, với Redis/JDBC thật và trong tình huống request đồng thời.

Thay đổi trực tiếp một object đã lấy ra từ session là thao tác Java hợp lệ, nhưng repository chỉ lưu được thay đổi khi chính sách ghi nhận diện thuộc tính đó và flush theo đúng thời điểm. Gọi `setAttribute` sau mutation hoặc thay object bằng phiên bản immutable tạo ra ranh giới cập nhật rõ ràng; lựa chọn `SaveMode` và `FlushMode` cần đi kèm đo lường chi phí, kiểm thử serialization và kiểm soát request đồng thời.
