# Phân rã đồ thị đối tượng theo cấu trúc record (Nested Record Patterns)

## 1. Mô hình tư duy: đi từ record ngoài vào record trong

Trong ứng dụng, dữ liệu thường được tổ chức thành nhiều đối tượng lồng nhau. Ví dụ, một đơn hàng chứa khách hàng, khách hàng chứa địa chỉ:

```text
Order(id, customer)
  └── Customer(name, address)
        └── Address(city, country)
```

Giả sử ba kiểu trên đều là Java `record`. Để lấy thành phố của khách hàng, cách truyền thống là lấy `Order.customer()`, tiếp tục `Customer.address()`, rồi `Address.city()`; mỗi mắt xích có thể cần kiểm tra `null`.

**Nested record patterns** (mẫu record lồng nhau) cho phép mô tả ngay hình dạng cần lấy và đặt tên cho các thành phần ở nhiều tầng trong **một lần so khớp**:

```java
if (value instanceof Order(
        var orderId,
        Customer(var customerName, Address(var city, var country)))) {
    // Tại đây có orderId, customerName, city, country.
}
```

Đọc từ ngoài vào trong: `value` phải là một `Order`; thành phần thứ hai của nó phải khớp mẫu `Customer(...)`; thành phần thứ hai của `Customer` phải khớp mẫu `Address(...)`. Khi toàn bộ mẫu thành công, các biến ở các tầng được ràng buộc và có thể dùng trong nhánh `if`. Đây là kiểm tra **kiểu record và cấu trúc thành phần được khai báo**, không phải cơ chế tìm thuộc tính theo tên như destructuring của JavaScript và cũng không phải phép duyệt đồ thị đối tượng tùy ý.

**Phiên bản:** Record classes được chuẩn hóa từ Java 16; **record patterns, bao gồm mẫu lồng nhau, là tính năng chính thức từ Java 21 (JEP 440)**. Các ví dụ bên dưới dùng JDK 21 trở lên, không cần `--enable-preview`.

## 2. Cấu trúc và cú pháp

Giả sử khai báo:

```java
record Address(String city, String country) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer) {}
```

Mẫu record có dạng `TênRecord(mẫu_thành_phần_1, mẫu_thành_phần_2, ...)`. Số lượng và **thứ tự** mẫu thành phần phải tương ứng với khai báo record. Chẳng hạn:

- `Order(var id, var customer)`: phân rã một tầng; `id` được suy ra kiểu `String`, `customer` được suy ra kiểu `Customer`.
- `Order(String id, Customer(var name, var address))`: phân rã hai tầng; thành phần khách hàng phải khớp một mẫu record `Customer`.
- `Order(String id, Customer(String name, Address(String city, String country)))`: phân rã ba tầng và ràng buộc trực tiếp bốn biến `id`, `name`, `city`, `country`.
- `var` trong danh sách thành phần yêu cầu trình biên dịch suy luận kiểu từ khai báo record, không khiến toàn bộ cấu trúc trở thành dữ liệu động.

Một mẫu có thể kết hợp *mẫu record* (`Address(...)`), *mẫu kiểu* (`String city`) và *mẫu suy luận* (`var city`). Không bắt buộc phải phân rã mọi tầng: có thể dừng ở `var address` khi chỉ muốn lấy đối tượng `Address`. Tuy nhiên, mỗi mẫu record vẫn phải liệt kê đủ vị trí thành phần; không thể viết `Address(var city)` nếu `Address` khai báo hai thành phần.

## 3. Trước và sau: truy cập thủ công so với mẫu lồng nhau

Với dữ liệu có kiểu ban đầu là `Object`, cách truy cập thủ công thường như sau (đoạn này giả sử ba record đã được khai báo ở trên):

```java
Object value = new Order("DH-01",
        new Customer("Lan", new Address("Đà Nẵng", "VN")));

if (value instanceof Order order) {
    Customer customer = order.customer();
    if (customer != null) {
        Address address = customer.address();
        if (address != null) {
            System.out.println(order.id() + " - " + customer.name()
                    + " - " + address.city());
        }
    }
}
```

Với nested record patterns, phép kiểm tra các record trên đường đi và việc trích các thành phần được biểu diễn cùng một chỗ:

```java
if (value instanceof Order(
        var id,
        Customer(var name, Address(var city, var country)))) {
    System.out.println(id + " - " + name + " - " + city);
}
```

Cả hai đều in `DH-01 - Lan - Đà Nẵng` với dữ liệu này. Phiên bản dùng mẫu ngắn hơn vì không cần tạo biến trung gian và gọi từng accessor trong phần thân. Mẫu cho người đọc biết rõ đường dữ liệu được yêu cầu. Nó phù hợp nhất khi bạn biết trước các kiểu record lồng nhau và chỉ cần lấy/kiểm tra vài giá trị từ cấu trúc đó.

## 4. Ví dụ hoàn chỉnh, chạy được trên Java 21+

Lưu đoạn sau vào tệp **`NestedGraphDemo.java`**. Các `record` khai báo bên trong lớp chỉ phục vụ ví dụ và có thể thay bằng record độc lập ở ứng dụng thực tế.

```java
public class NestedGraphDemo {
    record Address(String city, String country) {}
    record Customer(String name, Address address) {}
    record Order(String id, Customer customer) {}

    // Lấy dữ liệu qua đúng chuỗi Order -> Customer -> Address.
    static String describe(Object value) {
        if (value instanceof Order(
                String orderId,
                Customer(String customerName, Address(String city, String country)))) {
            return orderId + " | " + customerName + " | " + city + ", " + country;
        }
        return "Không khớp cấu trúc";
    }

    // Biến do pattern tạo ra dùng được ở vế phải của && khi pattern thành công.
    static String describeVn(Object value) {
        if (value instanceof Order(
                var id,
                Customer(var name, Address(var city, var country)))
                && "VN".equals(country)) {
            return name + " ở " + city + " (" + id + ")";
        }
        return "Không có địa chỉ VN";
    }

    // Xử lý lần lượt cấu trúc đầy đủ, thiếu địa chỉ, thiếu khách hàng.
    static String classify(Object value) {
        return switch (value) {
            case Order(var id, Customer(var name, Address(var city, var country))) ->
                    id + ": " + name + " @ " + city;
            case Order(var id, Customer(var name, var address)) ->
                    id + ": " + name + " chưa có địa chỉ";
            case Order(var id, var customer) ->
                    id + ": chưa có khách hàng";
            case null -> "Giá trị null";
            default -> "Không phải Order";
        };
    }

    public static void main(String[] args) {
        Object complete = new Order("DH-01",
                new Customer("Lan", new Address("Đà Nẵng", "VN")));
        Object missingAddress = new Order("DH-02",
                new Customer("Minh", null));

        System.out.println(describe(complete));
        System.out.println(describe(missingAddress));
        System.out.println(describe(null));
        System.out.println(describeVn(complete));
        System.out.println(classify(missingAddress));
        System.out.println(classify(null));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac -encoding UTF-8 --release 21 NestedGraphDemo.java
java NestedGraphDemo
```

Kết quả (với terminal hỗ trợ UTF-8):

```text
DH-01 | Lan | Đà Nẵng, VN
Không khớp cấu trúc
Không khớp cấu trúc
Lan ở Đà Nẵng (DH-01)
DH-02: Minh chưa có địa chỉ
Giá trị null
```

Ở `describe`, mẫu lồng nhau chỉ thành công khi có đủ ba record `Order`, `Customer` và `Address` theo quan hệ đã khai báo. Với `missingAddress`, `Customer` vẫn tồn tại nhưng thành phần `address` bằng `null`, nên mẫu record `Address(...)` không khớp; phương thức trả về thông báo dự phòng. Với đầu vào `null`, `instanceof` trả về `false`.

## 5. Quy tắc khớp và xử lý null

Có hai tình huống cần phân biệt:

**A. Một record con bằng `null`.** Giá trị `null` không khớp với **mẫu record**. Ví dụ:

```java
Order order = new Order("DH-02", new Customer("Minh", null));

boolean deepMatch = order instanceof Order(
        var id, Customer(var name, Address(var city, var country)));
// deepMatch == false: không có Address để phân rã.
```

**B. Một thành phần tham chiếu bằng `null`, nhưng mẫu cho thành phần đó là `var` (hoặc một mẫu kiểu khớp vô điều kiện với đúng kiểu đã khai báo).** Mẫu có thể vẫn thành công và biến có thể nhận `null`:

```java
Order order = new Order("DH-02", new Customer("Minh", null));

if (order instanceof Order(var id, Customer(var name, var address))) {
    // Nhánh này chạy; address == null.
    System.out.println(address == null); // true
}
```

Tương tự, `Address(String city, String country)` có thể ràng buộc một `city` bằng `null` nếu thành phần `city` được khai báo là `String`. **Đừng nhầm việc khớp record thành công với việc mọi trường đều khác null, không rỗng hoặc hợp lệ theo nghiệp vụ.** Có thể dùng điều kiện bổ sung, ví dụ `city != null && !city.isBlank()`, sau khi mẫu khớp.

Bảng tình huống cho mẫu sâu `Order(var id, Customer(var name, Address(var city, var country)))`:

| Giá trị đưa vào | Khớp mẫu sâu? | Lý do |
| --- | --- | --- |
| `Order` có `Customer` và `Address` | Có | Đủ ba record lồng nhau |
| `Order` có `Customer`, nhưng `address == null` | Không | `null` không khớp `Address(...)` |
| `Order` có `customer == null` | Không | `null` không khớp `Customer(...)` |
| `null` | Không | `null` không khớp mẫu record ngoài cùng |
| Đối tượng không thuộc kiểu `Order` | Không | Sai kiểu record ngoài cùng |

Record giúp mô tả các thành phần dữ liệu một cách rõ ràng, nhưng **không tự biến toàn bộ đồ thị thành bất biến sâu**. Nếu một thành phần là `List` hoặc một đối tượng có thể thay đổi, các giá trị được tham chiếu vẫn có thể thay đổi theo quy tắc của chính kiểu đó.

## 6. Kết hợp điều kiện và switch

### 6.1. Guard sau `instanceof`

Điều kiện sau `&&` chỉ được đánh giá khi mẫu ở vế trái khớp. Do đó biến `country` đã có giá trị trước khi so sánh:

```java
if (value instanceof Order(
        var id, Customer(var name, Address(var city, var country)))
        && "VN".equals(country)) {
    System.out.println(name + " - " + city);
}
```

Dùng `"VN".equals(country)` cũng tránh phát sinh `NullPointerException` khi `country` bằng `null`. Biến do mẫu tạo ra chỉ có phạm vi sử dụng ở nơi trình biên dịch bảo đảm mẫu đã khớp; không thể dùng `city` ở ngoài nhánh `if` theo cách tùy ý.

### 6.2. Nhiều dạng cấu trúc trong `switch`

`switch` pattern matching là tính năng chính thức của Java 21. Với nhiều khả năng của một đồ thị dữ liệu, hãy xếp nhánh **cụ thể trước, tổng quát sau**:

```java
return switch (value) {
    case Order(var id, Customer(var name, Address(var city, var country))) ->
            "Đủ địa chỉ: " + city;
    case Order(var id, Customer(var name, var address)) ->
            "Có khách hàng, chưa có địa chỉ";
    case Order(var id, var customer) ->
            "Không có khách hàng";
    case null -> "Không có đầu vào";
    default -> "Không phải đơn hàng";
};
```

Ở đây, nhánh 1 nhận đơn có `Address`; nhánh 2 nhận trường hợp `Customer` có `address == null`; nhánh 3 nhận đơn có `customer == null`. Nhánh `case null` xử lý đầu vào `null` một cách tường minh. Đưa mẫu rộng `Order(var id, var customer)` lên trước các mẫu cụ thể sẽ khiến các nhánh sau bị che phủ và có thể gây lỗi biên dịch do *dominance* (mẫu trước đã bao phủ mẫu sau). Đoạn mã `switch` này là một phần thân phương thức, giả sử các record và biến `value` đã được khai báo như ví dụ hoàn chỉnh ở mục 4.

## 7. Khi nào nên và không nên dùng

**Nên dùng** khi cấu trúc dữ liệu gồm các record có số tầng xác định; khi chỉ cần đọc một số trường sâu; hoặc khi nhiều nhánh nghiệp vụ tương ứng với các hình dạng record khác nhau. Mẫu lồng nhau đặc biệt rõ ràng ở `instanceof`, `switch`, xử lý sự kiện, mô hình dữ liệu và các kiểu record phân cấp.

**Không nên ép dùng** khi:
- Đồ thị chứa `List`, `Map` hoặc các nút có số lượng không cố định: record patterns không tự lặp qua phần tử của collection; cần vòng lặp, Stream hoặc thuật toán duyệt riêng.
- Quan hệ có chu trình hoặc độ sâu không biết trước: mẫu record chỉ mô tả một chuỗi lồng nhau hữu hạn tại thời điểm viết mã, không tự tìm đường đi trong đồ thị.
- Dữ liệu là POJO/class thông thường, không phải record: có thể dùng type pattern như `obj instanceof Customer customer` và gọi accessor/getter; không thể viết `Customer(...)` kiểu record pattern cho một class không phải record.
- Một biểu thức lồng quá nhiều tầng khiến cấu trúc khó đọc: tách bước theo các lớp nghiệp vụ hoặc dùng biến trung gian sẽ dễ bảo trì hơn.

## 8. Lỗi thường gặp và cách tự kiểm tra

1. **Nhầm tên trường với thứ tự thành phần.** `Address(var city, var country)` tương ứng đúng với `record Address(String city, String country)`. Nếu đảo thứ tự biến thì mã vẫn có thể biên dịch (vì cùng kiểu `String`) nhưng ý nghĩa dữ liệu bị đảo.
2. **Thiếu thành phần trong mẫu.** Với `Address` có hai thành phần, `Address(var city)` không hợp lệ. Hãy khai báo đủ vị trí; với vị trí không dùng, Java 21 ổn định có thể đặt tên `var ignoredCountry`. Cú pháp mẫu bỏ tên `_` vẫn là tính năng preview trong Java 21, nên đừng coi nó là cú pháp ổn định của Java 21.
3. **Cho rằng mẫu sâu tự bỏ qua null.** `Address(...)` sẽ không khớp khi `address` là `null`. Nếu muốn phân biệt trường hợp thiếu dữ liệu, thêm mẫu rộng hơn ở `switch` hoặc đọc `var address` rồi tự kiểm tra.
4. **Cho rằng bản thân dữ liệu được kiểm định.** Mẫu khớp kiểu và vị trí thành phần, không chứng minh `country` là mã quốc gia hợp lệ hay `city` có nội dung.
5. **Đặt mẫu rộng trước mẫu hẹp trong switch.** Mẫu rộng có thể chiếm tất cả trường hợp mà mẫu hẹp cần xử lý, dẫn đến lỗi dominance; ưu tiên kiểm tra hình dạng cụ thể trước.
6. **Dùng JDK không đúng phiên bản.** Với `javac` cũ hơn 21, mã record patterns có thể không được hỗ trợ chính thức. Dùng `java -version` và `javac -version` để xác nhận môi trường.

**Bài thực hành ngắn:**

- Tạo `new Order("DH-03", null)`. Dự đoán `describe` và `classify` từ ví dụ đầy đủ. Kết quả lần lượt là `Không khớp cấu trúc` và `DH-03: chưa có khách hàng`.
- Tạo đơn có địa chỉ `new Address(null, "VN")`. Mẫu sâu có khớp không? **Có**: thành phần `city` có thể được ràng buộc thành `null`. Muốn loại địa chỉ này, thêm điều kiện `city != null && !city.isBlank()` sau mẫu.
- Chuyển `Address` từ hai thành phần thành `record Address(String street, String city, String country)`. Hãy cập nhật tất cả mẫu `Address(...)` thành ba vị trí đúng thứ tự và sửa lời gọi hàm tạo tương ứng.

**Ghi nhớ:** Nested record patterns giúp **kiểm tra hình dạng record và phân rã các tầng dữ liệu trong một biểu thức**. Khả năng đọc được của mã đến từ việc đặt đúng cấu trúc, kiểm soát `null` ở từng nút record, giữ nhánh từ cụ thể đến tổng quát và chỉ dùng mẫu sâu tới mức thực sự cần thiết.

**Tham khảo:** [Oracle — Record Patterns (Java 21)](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
