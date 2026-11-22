# Deconstruct record lồng nhau bằng Record Patterns trong Java 21

## 1. Deconstruction của nested record là gì?

**Deconstruction** là thao tác phân rã một đối tượng record thành các giá trị component của nó trong lúc **pattern matching**. Với **nested record pattern**, ta tiếp tục phân rã component là một record khác, theo nhiều tầng, mà không phải tự viết chuỗi gọi accessor ở từng tầng.

Ví dụ dữ liệu có cấu trúc:

```text
Order(id, customer)
           |
           +-- Customer(name, address)
                               |
                               +-- Address(city, point)
                                                   |
                                                   +-- Point(x, y)
```

Với Java 21, ta có thể kiểm tra và lấy toàn bộ các component trong cùng một biểu thức:

```java
if (value instanceof Order(
        String id,
        Customer(String name,
                Address(String city, Point(int x, int y))))) {
    System.out.println(id + ": " + name + " - " + city
            + " (" + x + ", " + y + ")");
}
```

Đây là **đoạn minh họa** sử dụng các record `Order`, `Customer`, `Address` và `Point` được định nghĩa đầy đủ ở phần ví dụ chạy được bên dưới.

Điểm quan trọng: Java chỉ đi vào thân `if` khi **toàn bộ pattern khớp**. Các biến `id`, `name`, `city`, `x` và `y` được bind theo giá trị component tương ứng. Ta không cần tự ép kiểu ở từng tầng.

**Mốc phiên bản:** Record Patterns thuộc **JEP 440**, chính thức trong **Java 21**. Khi dùng record pattern trong `switch`, tính năng tương ứng là Pattern Matching for switch (**JEP 441**), cũng chính thức từ Java 21. Không cần `--enable-preview`.

## 2. Cấu trúc record và thứ tự component

Giả sử khai báo:

```java
record Point(int x, int y) {}

record Address(String city, Point point) {}

record Customer(String name, Address address) {}

record Order(String id, Customer customer) {}
```

Các dòng trên là **các khai báo minh họa**, không phải bốn chương trình Java độc lập. Khi record pattern xuất hiện, **thứ tự và số lượng** pattern con phải khớp với component của record.

| Record | Component theo thứ tự | Pattern tương ứng |
|---|---|---|
| `Point` | `int x`, `int y` | `Point(int x, int y)` |
| `Address` | `String city`, `Point point` | `Address(String city, Point(int x, int y))` |
| `Customer` | `String name`, `Address address` | `Customer(String name, Address(String city, Point(int x, int y)))` |
| `Order` | `String id`, `Customer customer` | `Order(String id, Customer(String name, Address(String city, Point(int x, int y))))` |

Trong mỗi cặp ngoặc của record pattern, ta viết **một pattern cho mỗi component**, theo đúng thứ tự khai báo. Có thể dùng:

- **Type pattern:** `String name`, `int x`.
- **`var` pattern:** `var name`, `var x`, để trình biên dịch suy ra kiểu của component.
- **Record pattern lồng nhau:** `Address(String city, Point(int x, int y))`.

Ví dụ, `Order(String id, Customer(...))` cần hai component vì `Order` có hai component; không thể bỏ `id` bằng cách viết `Order(Customer(...))`. Nếu không dùng `id`, vẫn có thể đặt một biến có tên như `var ignoredId`. Trong Java 21, cú pháp unnamed pattern `_` còn là preview, nên bài này không dùng nó.

Không có cú pháp deconstruction assignment như `var (id, customer) = order;` trong Java 21. Ta phân rã thông qua **pattern matching**, chủ yếu với `instanceof` và `switch`.

## 3. Java thực hiện khớp record pattern lồng nhau như thế nào?

Với:

```java
Order(String id,
      Customer(String name,
               Address(String city, Point(int x, int y))))
```

Khái niệm khớp được hiểu theo thứ tự:

1. Giá trị đầu vào phải là một đối tượng `Order` **khác `null`**.
2. Component `id` được khớp với `String id`; component `customer` được khớp với `Customer(...)`.
3. `Customer(...)` đòi hỏi `customer` là một `Customer` **khác `null`**; tiếp tục phân rã `name` và `address`.
4. `Address(...)` đòi hỏi `address` khác `null`; tiếp tục phân rã `city` và `point`.
5. `Point(int x, int y)` đòi hỏi `point` là `Point` khác `null`, rồi bind hai tọa độ nguyên.
6. Nếu mọi pattern con đều khớp, toàn bộ pattern khớp và các biến có thể được sử dụng tại nơi trình biên dịch xác định khớp thành công.

Ở mức khái niệm, record pattern dùng các **component accessors** do record cung cấp (ví dụ `customer()`, `address()`, `point()`). Nó không thay đổi record, không tạo bản sao tự động và không cần hàm `deconstruct()` do người dùng viết.

Vì khớp diễn ra đệ quy, **chỉ một nested record component bị `null` là đủ để toàn bộ nested pattern không khớp**. Nhưng điều đó không đồng nghĩa với việc mọi component lá đều phải khác `null`.

## 4. Phân biệt nested record null và component lá null

Hãy so sánh bốn trường hợp:

| Input | Pattern `Order(..., Customer(..., Address(..., Point(...))))` | Lý do |
|---|---|---|
| `null` | Không khớp | Root record bằng `null` |
| `new Order("O1", null)` | Không khớp | Nested `Customer(...)` gặp `null` |
| `new Order("O2", new Customer("An", new Address("Hue", null)))` | Không khớp | Nested `Point(...)` gặp `null` |
| `new Order("O3", new Customer(null, new Address(null, new Point(0, 0))))` | **Khớp** | Mọi đối tượng record đều tồn tại; chỉ component `String` là `null` |

**Tại sao dòng cuối vẫn khớp?** Trong record pattern của Java 21, một type pattern trực tiếp có thể khớp `null` khi nó **unconditional đối với kiểu khai báo của component**. `String name` là unconditional đối với component khai báo `String name`; `String city` cũng vậy. Vì thế hai biến có thể được bind bằng `null`.

Ngược lại, **record pattern `Point(int x, int y)` không khớp `null`**, kể cả khi component `point` được khai báo là `Point`.

Nếu thay `Point(int x, int y)` bằng `var point` hoặc `Point point` trực tiếp trong danh sách component của `Address`, ta có thể bind `point == null` thay vì thất bại ở tầng đó:

```java
if (value instanceof Order(
        var id,
        Customer(var name, Address(var city, var point)))) {
    // customer và address chắc chắn là record khác null;
    // id, name, city, point vẫn có thể nhận null.
    System.out.println(point == null ? "Chưa có point" : point);
}
```

Đoạn trên dùng các record khai báo ở phần 2. Lưu ý: `instanceof Point p` ở cấp ngoài **không** khớp `null`; quy tắc null-matching của type pattern trực tiếp ở **component của record pattern** cần được phân biệt với type pattern thông thường ở selector.

## 5. Ví dụ Java 21 hoàn chỉnh: deconstruct nhiều tầng

Tạo tệp **`NestedRecordDeconstructionDemo.java`** với mã sau. Chương trình cho thấy ba cách sử dụng nested deconstruction:

- `inspect`: `instanceof` với cấu trúc bốn tầng, chỉ trả về chi tiết khi pattern đầy đủ.
- `route`: `switch` dùng nested pattern và `when` để phân loại; có nhánh fallback cho dữ liệu chưa đủ.
- `loose`: phân rã đến `Address` nhưng dùng `var point` để **chấp nhận point null**.

```java
public class NestedRecordDeconstructionDemo {
    record Point(int x, int y) {}
    record Address(String city, Point point) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer) {}

    static String inspect(Object value) {
        if (value instanceof Order(
                String id,
                Customer(String name,
                        Address(String city, Point(int x, int y))))) {
            return "DETAIL=" + id + "/" + name + "/" + city + "/" + x + "," + y;
        }
        return "NO_FULL_MATCH";
    }

    static String route(Object value) {
        return switch (value) {
            case null -> "NULL_ROOT";
            case Order(var id,
                       Customer(var name, Address(var city, Point(int x, int y))))
                    when city != null && !city.isBlank() && x >= 0 && y >= 0
                    -> "VALID_POINT";
            case Order(var id,
                       Customer(var name, Address(var city, Point(int x, int y))))
                    -> "HAS_POINT";
            case Order(var id, var customer) -> "INCOMPLETE";
            default -> "OTHER_TYPE";
        };
    }

    static String loose(Object value) {
        if (value instanceof Order(
                var id, Customer(var name, Address(var city, var point)))) {
            return "CITY=" + (city == null ? "<unknown>" : city)
                    + "; POINT_NULL=" + (point == null);
        }
        return "NO_ADDRESS";
    }

    static void show(String label, Object value) {
        System.out.println(label + " | " + inspect(value)
                + " | " + route(value) + " | " + loose(value));
    }

    public static void main(String[] args) {
        show("full", new Order("O1",
                new Customer("Lan", new Address("Hue", new Point(1, 2)))));
        show("leaf-null", new Order("O2",
                new Customer(null, new Address(null, new Point(0, 0)))));
        show("blank-city", new Order("O3",
                new Customer("An", new Address(" ", new Point(3, 4)))));
        show("point-null", new Order("O4",
                new Customer("Chi", new Address("Ha Noi", null))));
        show("address-null", new Order("O5", new Customer("Duc", null)));
        show("customer-null", new Order("O6", null));
        show("root-null", null);
        show("other-type", "text");
    }
}
```

Biên dịch và chạy trên **JDK 21 hoặc mới hơn**:

```bash
javac --release 21 NestedRecordDeconstructionDemo.java
java NestedRecordDeconstructionDemo
```

**Stdout chính xác:**

```text
full | DETAIL=O1/Lan/Hue/1,2 | VALID_POINT | CITY=Hue; POINT_NULL=false
leaf-null | DETAIL=O2/null/null/0,0 | HAS_POINT | CITY=<unknown>; POINT_NULL=false
blank-city | DETAIL=O3/An/ /3,4 | HAS_POINT | CITY= ; POINT_NULL=false
point-null | NO_FULL_MATCH | INCOMPLETE | CITY=Ha Noi; POINT_NULL=true
address-null | NO_FULL_MATCH | INCOMPLETE | NO_ADDRESS
customer-null | NO_FULL_MATCH | INCOMPLETE | NO_ADDRESS
root-null | NO_FULL_MATCH | NULL_ROOT | NO_ADDRESS
other-type | NO_FULL_MATCH | OTHER_TYPE | NO_ADDRESS
```

Cách đọc kết quả:

- **`full`:** toàn bộ nested pattern khớp. Điều kiện `when` đúng, nên `route` trả về `VALID_POINT`.
- **`leaf-null`:** `name` và `city` đều bằng `null`, nhưng các record `Order`, `Customer`, `Address` và `Point` đều tồn tại. `inspect` vẫn phân rã thành công; `route` trả về `HAS_POINT` vì `city != null` sai.
- **`blank-city`:** deconstruction thành công vì chuỗi một dấu cách vẫn là một giá trị `String`. Guard `!city.isBlank()` sai nên phân loại `HAS_POINT`.
- **`point-null`:** pattern yêu cầu `Point(...)` thất bại; pattern dùng `var point` ở `loose` vẫn khớp và nhận `point == null`.
- **`address-null` và `customer-null`:** nested record pattern thất bại tại tầng bị thiếu, nhưng `Order` vẫn tồn tại nên `route` chọn `INCOMPLETE`.
- **`root-null`:** `instanceof` cho `false`; `switch` chọn `case null`.
- **`other-type`:** `String` không phải `Order`; `default` xử lý.

Đây là dữ liệu demo nhằm làm rõ cơ chế pattern matching, không phải logic xác thực địa chỉ hay tọa độ thực tế.

## 6. Nested deconstruction trong switch và guard

`switch` giúp xử lý nhiều cấp độ khớp bằng các nhánh có thứ tự. Từ chương trình:

```java
return switch (value) {
    case null -> "NULL_ROOT";

    // Khớp toàn bộ nested records và đáp ứng điều kiện bổ sung.
    case Order(var id,
               Customer(var name, Address(var city, Point(int x, int y))))
            when city != null && !city.isBlank() && x >= 0 && y >= 0
            -> "VALID_POINT";

    // Vẫn có Point nhưng chưa đáp ứng guard.
    case Order(var id,
               Customer(var name, Address(var city, Point(int x, int y))))
            -> "HAS_POINT";

    // Order tồn tại nhưng bất kỳ nested record nào có thể thiếu.
    case Order(var id, var customer) -> "INCOMPLETE";

    default -> "OTHER_TYPE";
};
```

**Đoạn trên chỉ là thân biểu thức `switch` minh họa.** Phiên bản đầy đủ, biên dịch được nằm trong lớp ở mục 5.

Cần nhớ:

1. **Guard `when` được đánh giá sau khi pattern khớp.** Do đó ta chỉ kiểm tra `city.isBlank()` khi đã có biến `city`, đồng thời dùng `city != null` và `&&` để tránh lỗi khi city null.
2. **Nhánh có guard nằm trước nhánh cùng pattern không guard.** Nếu đảo thứ tự, nhánh cụ thể bị nhánh rộng hơn bao phủ (*dominance*), gây lỗi biên dịch.
3. **Nhánh nested cụ thể đứng trước nhánh `Order(var id, var customer)`.** Nhánh `Order(...)` rộng sẽ khớp cả khi `customer` hoặc những component sâu hơn bằng null; đặt nó trước có thể che các nhánh cụ thể.
4. **`case null` chỉ bắt selector null**, không tự bắt mọi nested component null. `default` trong kiểu `switch` này cũng không thay cho việc xử lý selector null tường minh.

Giả sử chỉ cần biết dữ liệu có đủ bốn tầng hay không, `instanceof` một nhánh thường dễ đọc hơn. Nếu cần quyết định theo nhiều mức độ đầy đủ, `switch` có thể cho luồng rõ ràng hơn.

## 7. Khi nào chọn var và khi nào chọn nested record pattern?

Hai câu lệnh sau xử lý khác nhau khi `Address.point() == null`:

```java
value instanceof Order(
    var id, Customer(var name, Address(var city, Point(int x, int y))))

value instanceof Order(
    var id, Customer(var name, Address(var city, var point)))
```

- Ở câu đầu, `Point(int x, int y)` buộc `point` là đối tượng record khác null; khi khớp, nhận ngay `x` và `y` dạng `int`.
- Ở câu sau, `var point` bind trực tiếp cả `null`; người viết code phải tự kiểm tra trước khi gọi `point.x()` hoặc `point.y()`.

Chọn **nested pattern** khi logic cần dữ liệu bên trong record và yêu cầu nó tồn tại. Chọn **type/var pattern trực tiếp** khi muốn giữ reference có thể null, hoặc khi không cần bóc cấu trúc sâu hơn.

Ta cũng có thể dừng ở tầng `Customer`:

```java
if (value instanceof Order(var id, Customer(var name, var address))) {
    // customer khác null; address có thể null.
    if (address != null) {
        System.out.println(address.city());
    }
}
```

Đoạn này minh họa thêm vào lớp `NestedRecordDeconstructionDemo` ở mục 5. Pattern chỉ phân rã tới mức logic đang cần. Deconstruct sâu nhất có thể không phải lúc nào cũng là lựa chọn tốt cho tính dễ đọc.

## 8. Scope, kiểu dữ liệu và lỗi biên dịch thường gặp

**Scope của pattern variables.** Các biến như `x`, `y` chỉ dùng được ở nơi trình biên dịch xác định pattern đã khớp, chẳng hạn thân `if`, biểu thức guard `when` và nhánh tương ứng trong `switch`. Không thể sử dụng chúng tùy ý sau một `if` nếu điều kiện có thể sai.

**Kiểu được kiểm tra khi biên dịch.** Nếu đổi thứ tự component hoặc dùng pattern không tương thích với kiểu component, trình biên dịch báo lỗi. Java dựa vào thứ tự và kiểu của record components, không dựa vào tên biến tự đặt trong pattern.

**Không có literal pattern cho component ở Java 21.** Không viết:

```java
// Không phải cú pháp record component pattern hợp lệ trong Java 21:
Order("O1", Customer("Lan", Address("Hue", Point(1, 2))))
```

Các chuỗi và số trên là *literals*, không phải component patterns. Nếu muốn kiểm tra giá trị cụ thể, bind các biến rồi dùng guard:

```java
case Order(var id, Customer(var name,
        Address(var city, Point(int x, int y))))
        when "O1".equals(id) && "Hue".equals(city) && x == 1 && y == 2
        -> "EXACT_MATCH";
```

Hai đoạn này chỉ có tính minh họa cú pháp; để chạy `case` cần đặt bên trong `switch` và cung cấp các nhánh còn lại phù hợp.

**Đừng nhầm với chuỗi accessor.** Biểu thức:

```java
order.customer().address().point().x()
```

có thể ném `NullPointerException` nếu một reference trung gian bằng null. Nested record pattern tương đương về mục đích **đọc cấu trúc khi đủ dữ liệu**, nhưng nhánh không khớp do nested record null chỉ làm pattern thất bại. Nếu domain cần trả lỗi đặc biệt khi thiếu tầng, hãy xử lý nhánh thiếu riêng; không xem pattern như cơ chế xác thực mọi invariant của record.

**Một lỗi khác là dereference leaf null.** `String city` trong record pattern vẫn có thể bind `null` khi khai báo component là `String`. Luôn kiểm tra trước khi gọi `city.length()`, `city.isBlank()` hoặc các phương thức tương tự.

## 9. Áp dụng trong code thực tế

Nested deconstruction hữu ích khi:

- Cần chọn nhánh xử lý dựa trên một cấu trúc dữ liệu lồng nhau, ví dụ event → payload record → metadata record.
- Muốn đọc một phần thông tin từ các record bất biến mà không viết chuỗi ép kiểu và truy cập accessor lặp lại.
- Cần phân biệt đối tượng đủ cấu trúc với đối tượng thiếu một số record ở bên trong.

Tuy nhiên, khi nested pattern quá dài hoặc lặp lại ở nhiều nơi, hãy cân nhắc một **phương thức domain** để đóng gói câu hỏi nghiệp vụ. Ví dụ, thay vì để nhiều caller hiểu `Order → Customer → Address → Point` để tính “đủ điều kiện”, nên chuyển quy tắc đó về đối tượng/policy sở hữu nó. Nested pattern vẫn phù hợp ở **ranh giới phân loại dữ liệu**, còn quyết định nghiệp vụ có thể nằm ở phương thức domain có tên rõ nghĩa.

Không cần ép mọi record thành một pattern nhiều tầng: nếu chỉ cần `id` thì `case Order(var id, var customer)` thường rõ hơn.

## 10. Bài tự kiểm tra

Giả sử dùng các record ở mục 5:

```java
Object input = new Order("T1", new Customer(null,
        new Address("Da Nang", null)));
```

1. `input instanceof Order(var id, Customer(var name, Address(var city, Point(int x, int y))))` trả về gì? **`false`**, vì `point` là `null` và `Point(...)` không khớp.
2. Nếu thay `Point(int x, int y)` bằng `var point` thì sao? **`true`**, với `name == null` và `point == null`. Các record `Order`, `Customer`, `Address` vẫn tồn tại.
3. `String name` có bắt buộc `name` khác null không? **Không.** Type pattern trực tiếp này unconditional đối với component kiểu `String`.
4. Muốn chỉ chấp nhận `city` không rỗng và `point` tồn tại, làm cách nào? **Dùng nested `Point(...)`** và thêm `when city != null && !city.isBlank()` hoặc điều kiện `&&` sau `instanceof`.
5. Nếu `Order.customer() == null`, có thể lấy `name` bằng pattern `Customer(var name, ...)` không? **Không**, vì nested record pattern `Customer(...)` không khớp null. Cần nhánh fallback hoặc binding `var customer` và tự xử lý null.

## Tổng kết

**Deconstruct record lồng nhau** cho phép Java 21 kiểm tra và phân rã nhiều tầng record trong một pattern: outer record phải khớp, từng nested record cũng phải khớp, sau đó mới bind các component sâu hơn. Một record pattern không nhận null ở chính vị trí nó đang phân rã, nhưng một type/`var` pattern trực tiếp cho component vẫn có thể bind null tùy vào kiểu khai báo.

Hãy dùng `instanceof` cho một kiểm tra cấu trúc, `switch` cho nhiều nhánh có thứ tự, và `when` để bổ sung điều kiện trên giá trị đã bind. Chỉ deconstruct đến độ sâu thực sự cần, xử lý null rõ ràng và giữ cú pháp thuộc Java 21 ổn định.

## Tài liệu tham khảo

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification, Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
