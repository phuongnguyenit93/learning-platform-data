# Chọn component cần lấy khi deconstruct record trong Java

## 1. Mục tiêu và phạm vi

Khi làm việc với `record`, một đối tượng có thể chứa nhiều component (thành phần dữ liệu), nhưng ta thường chỉ quan tâm đến một vài component. Ví dụ, `Point(int x, int y)` có hai tọa độ nhưng thao tác hiện tại chỉ cần `x`; `Order(long id, Customer customer, int quantity)` có nhiều thông tin nhưng luồng giao hàng chỉ cần tên thành phố trong `customer.address`.

**Chọn component cần lấy** là lựa chọn những giá trị cần *ràng buộc thành biến và sử dụng* khi deconstruct record. Ta cần phân biệt hai việc:

1. **Record pattern phải mô tả đủ vị trí component** theo đúng thứ tự khai báo của record; Java 21 không cho bỏ bớt vị trí trong dấu ngoặc.
2. **Ta không bắt buộc sử dụng mọi component đã khớp**. Có thể đặt tên biến tạm để bỏ qua giá trị không cần dùng (Java 21), hoặc dùng **unnamed pattern `_`** (Java 22 trở lên).

Từ **Java 21**, record patterns là tính năng chuẩn (JEP 440). Cú pháp `_` làm unnamed pattern được chuẩn hóa từ **Java 22** (JEP 456), nên phần ví dụ chính chạy với **Java 21+** và phần `_` được ghi riêng cho **Java 22+**.

Bài học tập trung vào chọn component qua `instanceof`, phân rã record nhiều cấp, kết hợp `switch` và `when`, trường hợp nullable, cách làm gọn code và lỗi thường gặp.

## 2. Một record pattern luôn theo đúng cấu trúc record

Cho record:

```java
record Point(int x, int y) {}
```

Muốn lấy riêng `x` từ một biến kiểu `Object`, ta viết trong Java 21:

```java
if (value instanceof Point(var x, var ignoredY)) {
    System.out.println("x=" + x);
}
```

- `Point(...)` yêu cầu `value` là một `Point` khác `null`.
- Vị trí thứ nhất tương ứng component `x` và biến pattern `x` được dùng.
- Vị trí thứ hai tương ứng component `y`. `ignoredY` vẫn là một biến hợp lệ, chỉ là ta không sử dụng nó trong thân `if`. Java không tự bỏ qua vị trí thứ hai chỉ vì mã không cần `y`.
- `var` cho compiler suy luận kiểu từ định nghĩa record: cả `x` và `ignoredY` đều có kiểu `int`.

**Không hợp lệ trong Java 21:**

```java
// Không biên dịch: Point khai báo 2 component, pattern chỉ có 1.
if (value instanceof Point(var x)) {
    System.out.println(x);
}
```

Cũng không có cú pháp lấy theo tên kiểu `Point(x = var x)`, không có toán tử deconstruction assignment `var (x, y) = point` trong Java 21. **Vị trí và thứ tự** các component do khai báo `record` quyết định.

Tên như `ignoredY` chỉ là quy ước cho người đọc, không phải từ khóa Java và không làm JVM tự động bỏ qua việc đánh giá component. Dùng tên nhất quán, chẳng hạn `unusedY` hoặc `ignoredQuantity`, khi dự án còn chạy Java 21.

## 3. Chọn mức phân rã: chỉ mở những lớp thực sự cần

Xét cấu trúc:

```java
record Address(String city, String street, String postalCode) {}
record Customer(String id, Address address) {}
record Order(long id, Customer customer, int quantity) {}
```

Nếu chỉ cần **mã đơn hàng**, không cần deconstruct `Customer` hoặc `Address`:

```java
if (obj instanceof Order(var id, var ignoredCustomer, var ignoredQuantity)) {
    System.out.println("Order #" + id);
}
```

Ta dùng một record pattern ở mức `Order`, đủ ba vị trí; component `customer` được giữ dưới dạng một biến nhưng không phân rã tiếp. Như vậy người đọc thấy rõ `id` là dữ liệu duy nhất mã cần dùng.

Nếu chỉ cần **thành phố giao hàng**, ta mở sâu tới `Address`:

```java
if (obj instanceof Order(
        var ignoredOrderId,
        Customer(
            var ignoredCustomerId,
            Address(var city, var ignoredStreet, var ignoredZip)),
        var ignoredQuantity)) {
    System.out.println(city);
}
```

Đọc từ ngoài vào trong:

1. `Order(...)` khớp đơn hàng có ba component; không dùng ID và số lượng.
2. `Customer(...)` khớp record khách hàng nằm trong component thứ hai của `Order`; không dùng ID khách hàng.
3. `Address(...)` khớp record địa chỉ trong component thứ hai của `Customer`.
4. Chỉ `city` được sử dụng. `street` và `postalCode` vẫn có vị trí pattern nhưng biến tương ứng không dùng.

Đây là **chọn component theo đường đi `Order → Customer → Address → city`**. Không cần tạo biến riêng cho toàn bộ `Order`, không cần ép kiểu nhiều lần và không cần gọi chuỗi accessor sau khi toàn bộ pattern khớp.

**Lưu ý về `null`:** Nếu `customer == null` hoặc `address == null`, nested record pattern `Customer(...)` hoặc `Address(...)` không khớp; mã chuyển sang `else`/đường đi không khớp. Nhưng nếu record `Address` tồn tại và riêng `city == null`, `var city` vẫn có thể nhận `null`. Chọn component không đồng nghĩa với kiểm tra mọi giá trị bên trong khác `null`.

## 4. Ví dụ Java 21 đầy đủ, chạy được

Tạo tệp **`SelectComponentDemo.java`**:

```java
public class SelectComponentDemo {
    record Point(int x, int y) {}
    record Address(String city, String street, String postalCode) {}
    record Customer(String id, Address address) {}
    record Order(long id, Customer customer, int quantity) {}

    static String cityOf(Object obj) {
        if (obj instanceof Order(var ignoredOrderId,
                Customer(var ignoredCustomerId,
                         Address(var city, var ignoredStreet, var ignoredZip)),
                var ignoredQuantity)) {
            return city == null ? "City missing" : city;
        }
        return "No address";
    }

    static String orderId(Object obj) {
        if (obj instanceof Order(var id, var ignoredCustomer, var ignoredQuantity)) {
            return "Order #" + id;
        }
        return "Not an order";
    }

    static String label(Object obj) {
        return switch (obj) {
            case null -> "No input";
            case Order(var ignoredId,
                    Customer(var ignoredCustomerId,
                            Address(var city, var ignoredStreet, var ignoredZip)),
                    var ignoredQuantity)
                    when city != null && !city.isBlank() -> "Ship to " + city;
            case Order(var ignoredId, var ignoredCustomer, var ignoredQuantity)
                    -> "Order without city";
            default -> "Not an order";
        };
    }

    static String pointX(Object obj) {
        if (obj instanceof Point(var x, var ignoredY)) {
            return "x=" + x;
        }
        return "Not a point";
    }

    public static void main(String[] args) {
        Object full = new Order(42L,
                new Customer("C01", new Address("Da Nang", "Tran Phu", "550000")), 3);
        Object noAddress = new Order(43L, new Customer("C02", null), 2);
        Object nullCity = new Order(44L,
                new Customer("C03", new Address(null, "Ngo Quyen", "100000")), 1);

        System.out.println(cityOf(full));
        System.out.println(cityOf(noAddress));
        System.out.println(cityOf(nullCity));
        System.out.println(orderId(noAddress));
        System.out.println(label(full));
        System.out.println(label(noAddress));
        System.out.println(label(nullCity));
        System.out.println(label(null));
        System.out.println(pointX(new Point(7, 9)));
    }
}
```

Chạy bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 SelectComponentDemo.java
java SelectComponentDemo
```

**Kết quả chính xác:**

```text
Da Nang
No address
City missing
Order #43
Ship to Da Nang
Order without city
Order without city
No input
x=7
```

Phân tích:

- `cityOf(full)` chỉ trả về component `city` của record `Address` lồng trong `Customer` và `Order`; tất cả pattern con cần thiết đều khớp.
- `cityOf(noAddress)` trả về `No address` vì component `Customer.address` bằng `null`, nên không thể khớp `Address(...)`.
- `cityOf(nullCity)` trả về `City missing`: bản thân `Address` tồn tại, pattern khớp, nhưng component `city` bằng `null`.
- `orderId(noAddress)` lấy mã `43` mà **không cần** record địa chỉ hợp lệ; tránh phân rã sâu hơn mục tiêu.
- `label(full)` sử dụng `switch`, chọn thành phố và kiểm tra thêm `when city != null && !city.isBlank()`.
- `label(noAddress)` và `label(nullCity)` cùng trả về `Order without city`, nhưng vì lý do khác nhau: trường hợp đầu không khớp nested `Address(...)`, trường hợp sau khớp pattern nhưng không thỏa `when`.
- `label(null)` có nhánh `case null` riêng; đây là xử lý giá trị selector của `switch` bằng `null`, khác với một component `null` ở trong record.
- `pointX` chỉ dùng `x` và không cần `y`, nhưng pattern vẫn khai báo đủ hai vị trí.

Ví dụ này cố ý viết tên `ignored...` để tương thích Java 21. Trong ví dụ sản xuất, có thể đặt biến ngắn hơn hoặc dùng unnamed patterns của Java 22 nếu project đã nâng JDK.

## 5. Dùng `switch`/`when` khi điều kiện dựa trên component được chọn

Trong `switch`, ta có thể lấy một component rồi viết guard `when` chỉ sử dụng biến ấy:

```java
// Đoạn minh họa đặt trong phương thức nhận Object obj;
// giả sử các record Order/Customer/Address đã được khai báo.
return switch (obj) {
    case Order(var id, Customer(var customerId,
            Address(var city, var street, var zip)), var quantity)
            when city != null && city.startsWith("Da") -> "Central";
    case Order(var id, var customer, var quantity) -> "Other order";
    default -> "Not an order";
};
```

Guard `when` chỉ chạy sau khi **toàn bộ nested pattern khớp**. Biến `city` được khai báo bởi pattern và có hiệu lực trong guard cùng phần xử lý nhánh ấy. Nếu không khớp record con, chương trình thử nhánh kế tiếp; không có cơ chế tự chèn kiểm tra `null` cho các lệnh trong nhánh đã khớp.

Đặt nhánh cụ thể có `when` **trước** nhánh `Order(...)` bao quát. Nếu đặt nhánh rộng lên trước, nhánh sau có thể bị che khuất và compiler báo lỗi dominated case label.

Với biểu thức `switch` trên giá trị kiểu `Object`, cần nhánh bao quát như `default` cho các giá trị không phải `Order`. Nếu selector có thể là `null`, xử lý riêng bằng `case null` hoặc theo hợp đồng đầu vào, vì `default` không tự biến `null` thành giá trị thông thường.

## 6. Java 22+: unnamed pattern `_` để bỏ qua component thật sự

Từ **Java 22**, JEP 456 cho phép dùng **unnamed pattern `_`** khi cấu trúc của component vẫn cần được khớp nhưng giá trị không cần ràng buộc thành biến.

Ví dụ chỉ lấy `x`:

```java
// Java 22 trở lên
if (obj instanceof Point(var x, _)) {
    System.out.println(x);
}
```

Tương đương về mục tiêu chọn dữ liệu với cách Java 21 `Point(var x, var ignoredY)`, nhưng `_` **không khai báo một biến có tên** nên không thể tham chiếu về sau.

Với record lồng nhau, ký hiệu `_` làm đường đi đến component cần chọn rõ hơn:

```java
// Java 22 trở lên; Order, Customer và Address như ở trên.
if (obj instanceof Order(_, Customer(_, Address(var city, _, _)), _)) {
    System.out.println(city);
}
```

Pattern vẫn có **đủ ba component của Order**, **hai component của Customer** và **ba component của Address**. `_` chỉ thay cho một component pattern ở vị trí tương ứng; nó **không xóa bớt vị trí** và không làm các record con được chỉ rõ tự động trở thành optional.

Đây là điểm rất quan trọng về phiên bản:

| Yêu cầu | Java 21 | Java 22 trở lên |
| --- | --- | --- |
| Lấy một component, giữ đủ số vị trí | `Point(var x, var ignoredY)` | `Point(var x, _)` |
| Chọn component ở nhiều cấp | `Order(var skipId, Customer(var skipId2, Address(var city, var skipStreet, var skipZip)), var skipQuantity)` | `Order(_, Customer(_, Address(var city, _, _)), _)` |
| Bỏ qua một vị trí mà không tạo tên biến | Chưa có `_` chuẩn | Dùng unnamed pattern `_` |
| Dùng `_` như một biến để in lại giá trị | Không hợp lệ | Không hợp lệ; `_` không có tên truy cập được |

**Không dán đoạn Java 22 dùng `_` vào tệp đang biên dịch bằng `javac --release 21`.** Nếu chưa nâng cấp Java, sử dụng `var ignored...`.

Dù dùng unnamed pattern, không nên coi đây là lệnh tối ưu hóa bảo đảm JVM không đọc hoặc không gọi accessor tương ứng. Ý nghĩa chính của `_` là thể hiện **không quan tâm tới giá trị** và tránh khai báo biến không sử dụng.

## 7. Khi nào nên chọn accessor thay cho record pattern?

Nếu đối tượng đã có kiểu record rõ ràng, chỉ cần một component ở cùng cấp, accessor trực tiếp thường đơn giản nhất:

```java
Point point = new Point(7, 9);
int x = point.x();
```

Không cần viết `if (point instanceof Point(var x, var y))` chỉ để đọc `x` khi `point` đã là một `Point`. Phân rã hữu ích hơn nếu ta cần **vừa kiểm tra cấu trúc/kiểu vừa trích giá trị**, hoặc cần chọn các nhánh khác nhau trong `switch`.

Với nhiều cấp và giá trị có thể `null`, ta có thể viết điều kiện accessor rõ ràng (đoạn đặt trong phương thức nhận `Order order`):

```java
if (order != null && order.customer() != null
        && order.customer().address() != null) {
    String city = order.customer().address().city();
    System.out.println(city == null ? "City missing" : city);
}
```

Cách này hữu ích khi cần xử lý lỗi null theo từng cấp, cần thêm thông tin về tình trạng dữ liệu hoặc khi phần còn lại của code đã làm việc với `Order`. Nested record pattern lại phù hợp khi chỉ quan tâm việc cấu trúc đầy đủ có khớp hay không và muốn giảm lặp chuỗi accessor.

Quy tắc thực hành: **deconstruct đến component thật sự cần; đừng phân rã sâu hơn nếu một giá trị record trung gian đã đủ cho bước xử lý tiếp theo**. Nếu pattern kéo dài qua nhiều dòng và chứa quá nhiều `ignored...`, cân nhắc phương thức phụ, accessor trực tiếp hoặc `_` trên Java 22+.

## 8. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `Point(var x)` | Sai số component: `Point` có hai component `x, y`. | Dùng `Point(var x, var ignoredY)` (Java 21) hoặc `Point(var x, _)` (Java 22+). |
| `Order(Customer(Address(var city)))` | Bỏ vị trí `id` và `quantity`, đồng thời bỏ component khác của `Customer`, `Address`. | Điền pattern cho **mọi vị trí**, dùng `var ignored...` hoặc `_` đúng phiên bản. |
| Đặt `Address(...)` vào vị trí ID của `Customer` | Record patterns dựa trên **thứ tự khai báo** chứ không dò tên component. | Đọc định nghĩa record và đặt `Address(...)` đúng vị trí thứ hai. |
| Dùng `_` khi project còn Java 21 | Unnamed patterns được chuẩn hóa từ Java 22. | Dùng biến `ignored...` hoặc nâng JDK/source level lên 22+. |
| Dùng giá trị `ignoredY` trong code nhưng kỳ vọng nó bị bỏ qua | Ở Java 21, tên ấy vẫn là biến hợp lệ; chỉ có quy ước “không dùng”. | Đặt tên rõ ý đồ. Với Java 22+, dùng `_` khi thật sự không cần tham chiếu. |
| Cho rằng `_` cho phép bỏ cả record con | `_` bỏ một **vị trí component**, còn `Address(...)` yêu cầu record con phải khớp. | Dùng `var address` hoặc `_` ở vị trí record con nếu **không cần** kiểm tra/phân rã nó. |
| Giả định `city` luôn khác `null` vì `Address(...)` đã khớp | Record `Address` khác `null` không bảo đảm component `city` khác `null`. | Kiểm tra `city != null` hoặc điều kiện nghiệp vụ tương ứng. |
| Gọi biến pattern ngoài vùng hiệu lực | Biến chỉ có hiệu lực nơi compiler biết pattern đã khớp. | Dùng biến trong nhánh `if`, guard `when` hoặc nhánh `case` phù hợp. |
| Dùng record pattern cho class thông thường | Record deconstruction hoạt động với `record`, không tự phân rã mọi class. | Dùng accessor/type pattern hoặc thiết kế record phù hợp. |

Một lưu ý về hiệu năng: việc viết nested patterns ngắn hơn không có nghĩa chắc chắn ít thao tác runtime hơn mọi phương án dùng accessor. Ưu tiên **tính đúng, rõ điều kiện khớp và khả năng đọc**; chỉ tối ưu sau khi có kết quả đo lường nếu thật sự cần.

## 9. Bài tập áp dụng: chọn đúng component, không lấy thừa

Cho:

```java
record Dimensions(int width, int height) {}
record Product(String sku, String name, Dimensions dimensions, double price) {}
record CartItem(Product product, int quantity) {}
```

**Yêu cầu A:** Từ `Object input`, chỉ lấy `sku` nếu `input` là `CartItem` có `Product`; không yêu cầu `dimensions` khác `null`.

Đáp án Java 21 (đặt trong một phương thức có `input`):

```java
if (input instanceof CartItem(
        Product(var sku, var ignoredName, var ignoredDimensions, var ignoredPrice),
        var ignoredQuantity)) {
    System.out.println(sku);
}
```

Ở đây `dimensions` được gắn vào một biến nhưng **không bị deconstruct thành `Dimensions(...)`**. Vì vậy nếu `Product.dimensions == null`, pattern `Product(...)` vẫn có thể khớp; chỉ `CartItem.product` cần là record `Product` khác `null`.

**Yêu cầu B:** Chỉ lấy chiều rộng khi cả `CartItem → Product → Dimensions` có cấu trúc hợp lệ.

Đáp án Java 21:

```java
if (input instanceof CartItem(
        Product(var ignoredSku, var ignoredName,
                Dimensions(var width, var ignoredHeight),
                var ignoredPrice),
        var ignoredQuantity)) {
    System.out.println(width);
}
```

Với `Dimensions == null`, pattern ở yêu cầu B **không khớp**, khác yêu cầu A. Sự khác biệt không nằm ở việc có sử dụng biến hay không, mà ở quyết định **có áp dụng record pattern tới cấp `Dimensions` hay không**.

Đáp án gọn hơn cho yêu cầu B trên Java 22+:

```java
if (input instanceof CartItem(
        Product(_, _, Dimensions(var width, _), _), _)) {
    System.out.println(width);
}
```

Những đoạn đáp án là đoạn mã minh họa sử dụng ba `record` đã khai báo phía trên; chương trình chạy độc lập đầy đủ nằm ở mục 4.

## 10. Ghi nhớ

- **Chọn component cần lấy** là chọn biến nào được ràng buộc và độ sâu deconstruction cần thiết; record pattern vẫn phải ghi **đủ số component, đúng thứ tự**.
- **Java 21:** dùng `var wanted` cho dữ liệu cần lấy và `var ignored...` cho các component không dùng. Có thể dừng tại một record con bằng `var child` thay vì phân rã tiếp.
- **Java 22+:** dùng **unnamed pattern `_`** để diễn đạt “không quan tâm component này” mà không đặt tên biến. Pattern `_` vẫn chiếm đúng một vị trí.
- **Null:** record con cần được phân rã mà bằng `null` sẽ làm nested record pattern không khớp; component ràng buộc bằng `var` vẫn có thể bằng `null`. Đừng bỏ qua kiểm tra cần thiết.
- **Thiết kế code:** khi đã có record typed và chỉ cần một giá trị, accessor có thể rõ ràng hơn; khi cần đồng thời kiểm tra cấu trúc và lấy dữ liệu, record pattern giúp diễn đạt ý định trực tiếp.

**Tài liệu tham khảo:** [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440), [JEP 456 — Unnamed Variables & Patterns (Java 22)](https://openjdk.org/jeps/456), [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
