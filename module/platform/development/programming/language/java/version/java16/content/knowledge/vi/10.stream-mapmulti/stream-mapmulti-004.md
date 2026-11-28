# Chọn map, filter, flatMap hoặc mapMulti theo hình dạng đầu ra

Khi xây dựng Stream pipeline, hãy bắt đầu bằng câu hỏi: **mỗi phần tử đầu vào có thể tạo ra bao nhiêu phần tử đầu ra?** Câu trả lời thường cho biết nên dùng `map`, `filter`, `flatMap` hay `mapMulti`.

- Dùng `map` khi mỗi phần tử tạo đúng một giá trị tương ứng.
- Dùng `filter` khi chỉ cần giữ hoặc loại chính phần tử đó.
- Dùng `flatMap` khi mỗi phần tử được chuyển thành một Stream và các Stream con cần được làm phẳng.
- Dùng `mapMulti` khi cần phát trực tiếp không, một hoặc nhiều giá trị bằng Consumer, thường qua vòng lặp hoặc nhiều nhánh điều kiện.

Các phương thức này đều thuộc Stream API hiện hành. `mapMulti` được bổ sung từ Java 16 và vẫn hữu ích trong Java hiện đại khi mô hình phát kết quả phù hợp.

## 1. Xác định hình dạng đầu ra

Hãy nhìn vào quan hệ giữa một phần tử nguồn và kết quả mà nó đóng góp:

| Hình dạng đầu ra | Thao tác phù hợp | Ví dụ |
|---|---|---|
| Một đầu vào thành đúng một đầu ra | `map` | Chuyển tên thành chữ hoa |
| Một đầu vào thành không hoặc một đầu ra, giữ nguyên kiểu phần tử | `filter` | Chỉ giữ đơn hàng hợp lệ |
| Một đầu vào thành một Stream con, sau đó làm phẳng | `flatMap` | Mỗi khách hàng có một Stream đơn hàng |
| Một đầu vào phát không, một hoặc nhiều đầu ra qua Consumer | `mapMulti` | Duyệt các dòng hàng và phát SKU hợp lệ |

Sự khác biệt quan trọng là `map` và `filter` thể hiện các phép biến đổi đơn giản. `flatMap` và `mapMulti` xử lý trường hợp một phần tử nguồn có thể đóng góp nhiều phần tử vào Stream kết quả.

## 2. Dùng map cho quan hệ một-một

Chọn `map` khi mỗi phần tử nguồn luôn tạo ra đúng một giá trị đầu ra. Mapper trả về giá trị mới cho phần tử hiện tại.

Ví dụ chuyển tên người dùng thành chữ hoa:

```java
import java.util.List;

List<String> names = List.of("An", "Binh", "Chi");

List<String> normalizedNames = names.stream()
    .map(String::toUpperCase)
    .toList();
```

Kết quả:

```text
[AN, BINH, CHI]
```

Mỗi tên đóng góp chính xác một tên đã chuẩn hóa. Nếu mapper trả về `null`, Stream vẫn có một phần tử đầu ra có giá trị null; `map` không tự loại phần tử đó.

Dùng `map` khi có thể diễn đạt rõ phép chuyển đổi một giá trị thành một giá trị. Không cần dùng `mapMulti` chỉ để gọi Consumer đúng một lần cho mỗi phần tử.

## 3. Dùng filter khi chỉ giữ hoặc loại phần tử

Chọn `filter` khi phần tử nào thỏa điều kiện thì được giữ nguyên, phần tử không thỏa bị loại. Predicate trả về `true` hoặc `false`.

Ví dụ lấy các đơn hàng đã thanh toán:

```java
import java.util.List;

record Order(String id, boolean paid) {}

List<Order> orders = List.of(
    new Order("O-100", true),
    new Order("O-101", false),
    new Order("O-102", true)
);

List<Order> paidOrders = orders.stream()
    .filter(Order::paid)
    .toList();
```

Kết quả là hai đơn hàng `O-100` và `O-102`. Mỗi phần tử nguồn được giữ lại hoặc bị loại; `filter` không tạo một giá trị thay thế.

Nếu muốn vừa lọc vừa chuyển đổi kiểu hoặc nội dung, hãy kết hợp `filter` với `map`:

```java
List<String> paidOrderIds = orders.stream()
    .filter(Order::paid)
    .map(Order::id)
    .toList();
```

Pipeline này giữ các đơn đã thanh toán, sau đó chuyển mỗi đơn còn lại thành một mã đơn hàng. Cách tách này thường dễ đọc hơn việc dùng một mapper phát kết quả cho trường hợp chỉ có một kết quả.

## 4. Dùng flatMap khi mỗi phần tử tạo một Stream con

Chọn `flatMap` khi phép biến đổi tự nhiên trả về một Stream cho mỗi phần tử nguồn. `flatMap` lấy các phần tử từ từng Stream con và nối chúng thành một Stream kết quả.

Ví dụ, mỗi phòng ban có danh sách nhân viên. Ta muốn tạo một Stream chứa tất cả nhân viên:

```java
import java.util.List;

record Employee(String name) {}
record Department(String name, List<Employee> employees) {}

List<Department> departments = List.of(
    new Department("Engineering", List.of(
        new Employee("An"),
        new Employee("Binh")
    )),
    new Department("Support", List.of(
        new Employee("Chi")
    ))
);

List<Employee> allEmployees = departments.stream()
    .flatMap(department -> department.employees().stream())
    .toList();
```

Mỗi phòng ban tạo ra một Stream nhân viên. `flatMap` làm phẳng các Stream con đó thành một Stream nhân viên duy nhất. Phòng ban có danh sách rỗng đóng góp không nhân viên; phòng ban có một hoặc nhiều nhân viên đóng góp tương ứng số phần tử đó.

Có thể lọc dữ liệu con ngay trong Stream con:

```java
List<String> employeeNames = departments.stream()
    .flatMap(department -> department.employees().stream())
    .map(Employee::name)
    .filter(name -> !name.isBlank())
    .toList();
```

Dùng `flatMap` khi Stream con là cách biểu diễn tự nhiên của phép biến đổi, hoặc khi muốn tiếp tục sử dụng các thao tác Stream trên dữ liệu con.

## 5. Dùng mapMulti khi muốn phát trực tiếp kết quả

Chọn `mapMulti` khi mỗi phần tử nguồn có thể tạo ra không, một hoặc nhiều giá trị và logic phát kết quả phù hợp với vòng lặp hoặc các nhánh điều kiện.

Ví dụ, mỗi đơn hàng có nhiều dòng hàng. Ta chỉ muốn phát SKU của các dòng có số lượng dương:

```java
import java.util.List;

record LineItem(String sku, int quantity) {}
record OrderWithItems(String id, List<LineItem> items) {}

List<OrderWithItems> ordersWithItems = List.of(
    new OrderWithItems("O-200", List.of(
        new LineItem("BOOK-01", 2),
        new LineItem("PEN-02", 0)
    )),
    new OrderWithItems("O-201", List.of(
        new LineItem("BAG-03", 1),
        new LineItem("NOTE-04", 3)
    )),
    new OrderWithItems("O-202", List.of())
);

List<String> purchasedSkus = ordersWithItems.stream()
    .<String>mapMulti((order, consumer) -> {
        for (LineItem item : order.items()) {
            if (item.quantity() > 0) {
                consumer.accept(item.sku());
            }
        }
    })
    .toList();
```

Kết quả:

```text
[BOOK-01, BAG-03, NOTE-04]
```

Mapper duyệt các dòng hàng và gọi `consumer.accept` cho từng SKU hợp lệ. Dòng hàng có số lượng bằng không không phát kết quả; đơn hàng rỗng cũng không phát kết quả. Không cần tạo một Stream con riêng cho từng đơn hàng.

## 6. So sánh flatMap và mapMulti trên cùng dữ liệu

Cả `flatMap` và `mapMulti` đều có thể làm phẳng dữ liệu con. Với ví dụ đơn hàng ở trên, có thể dùng `flatMap` như sau:

```java
List<String> purchasedSkus = ordersWithItems.stream()
    .flatMap(order -> order.items().stream()
        .filter(item -> item.quantity() > 0)
        .map(LineItem::sku))
    .toList();
```

Hoặc dùng `mapMulti`:

```java
List<String> purchasedSkus = ordersWithItems.stream()
    .<String>mapMulti((order, consumer) -> {
        for (LineItem item : order.items()) {
            if (item.quantity() > 0) {
                consumer.accept(item.sku());
            }
        }
    })
    .toList();
```

Hai cách diễn đạt cùng quy tắc và cho kết quả giống nhau. Chọn theo cấu trúc logic:

- `flatMap` phù hợp khi mỗi phần tử dễ dàng được chuyển thành một Stream con và các phép lọc, chuyển đổi bên trong Stream con giúp mã rõ ràng.
- `mapMulti` phù hợp khi muốn duyệt dữ liệu con trực tiếp, có nhiều nhánh phát kết quả hoặc không cần xây dựng biểu thức Stream con.

Không nên kết luận rằng `mapMulti` luôn nhanh hơn `flatMap`. Chi phí thực tế phụ thuộc vào dữ liệu, số lượng kết quả, cách viết mapper và phiên bản JDK. Hãy chọn cách rõ ràng trước; chỉ tối ưu theo số đo khi hiệu năng thực sự là yêu cầu.

## 7. Dùng mapMulti cho trường hợp không hoặc một kết quả

`mapMulti` có thể phát không hoặc một giá trị, nhưng điều đó không có nghĩa nó luôn là lựa chọn tốt nhất.

Ví dụ chỉ phát tên người dùng nếu có dữ liệu:

```java
import java.util.List;

record UserProfile(String displayName) {}

List<UserProfile> profiles = List.of(
    new UserProfile("An"),
    new UserProfile(""),
    new UserProfile("Binh")
);

List<String> displayNames = profiles.stream()
    .<String>mapMulti((profile, consumer) -> {
        String name = profile.displayName();

        if (name != null && !name.isBlank()) {
            consumer.accept(name.trim());
        }
    })
    .toList();
```

Trường hợp này cũng có thể được diễn đạt bằng `map` kết hợp `filter`:

```java
List<String> displayNames = profiles.stream()
    .map(UserProfile::displayName)
    .filter(name -> name != null && !name.isBlank())
    .map(String::trim)
    .toList();
```

Nếu logic chỉ là chuyển một giá trị tùy chọn thành không hoặc một kết quả, cách dùng `map` và `filter` thường dễ hiểu hơn. Chọn `mapMulti` khi việc phát kết quả nằm trong một quy tắc xử lý lớn hơn hoặc có thể mở rộng thành nhiều kết quả.

## 8. Khi nào mapMulti không phải lựa chọn phù hợp?

Hãy tránh dùng `mapMulti` trong các tình huống sau nếu một thao tác Stream đơn giản hơn đã thể hiện chính xác ý định:

- Mỗi đầu vào luôn tạo đúng một đầu ra: dùng `map`.
- Chỉ cần giữ hoặc loại phần tử hiện tại: dùng `filter`.
- Mapper vốn trả về một Stream và các thao tác Stream con dễ đọc: dùng `flatMap`.
- Logic phát kết quả quá dài và làm pipeline khó hiểu: tách quy tắc nghiệp vụ thành phương thức riêng hoặc dùng một Stream con có cấu trúc rõ ràng.

`mapMulti` cũng không phải nơi để cập nhật collection dùng chung. Hãy phát dữ liệu bằng Consumer và dùng terminal operation hoặc collector để thu thập kết quả. Điều này đặc biệt quan trọng với parallel Stream, nơi mapper của nhiều phần tử nguồn có thể chạy đồng thời.

## 9. Chú ý kiểu dữ liệu đầu ra

Kiểu phần tử của Stream kết quả được xác định bởi kiểu `R` của `map`, `flatMap` hoặc `mapMulti`. Khi dùng `mapMulti`, nếu trình biên dịch không suy luận được kiểu đầu ra từ ngữ cảnh, có thể chỉ định kiểu tường minh:

```java
import java.util.List;

record SourceValue(boolean valid, String label) {}

List<SourceValue> source = List.of(
    new SourceValue(true, "active"),
    new SourceValue(false, "hidden")
);

List<String> labels = source.stream()
    .<String>mapMulti((value, consumer) -> {
        if (value.isValid()) {
            consumer.accept(value.label());
        }
    })
    .toList();
```

Với dữ liệu số nguyên thủy, Stream API có các biến thể `mapMultiToInt`, `mapMultiToLong` và `mapMultiToDouble`. Chúng phát giá trị qua `IntConsumer`, `LongConsumer` hoặc `DoubleConsumer` và trả về Stream chuyên biệt tương ứng. Hãy dùng các biến thể này khi kiểu kết quả phù hợp và các phép toán số học tiếp theo cần làm việc trực tiếp trên kiểu nguyên thủy.

## 10. Cây quyết định chọn thao tác

Có thể áp dụng thứ tự câu hỏi sau khi thiết kế pipeline:

```text
Mỗi phần tử nguồn cần tạo ra kết quả như thế nào?
             |
             +-- Luôn đúng một giá trị
             |       |
             |       +-- map
             |
             +-- Giữ hoặc loại chính phần tử đó
             |       |
             |       +-- filter
             |
             +-- Chuyển thành một Stream con
             |       |
             |       +-- flatMap
             |
             +-- Phát trực tiếp 0, 1 hoặc nhiều giá trị
                     |
                     +-- mapMulti
```

Đây là hướng dẫn lựa chọn thực tế, không phải quy tắc cứng. Một số trường hợp có thể viết bằng nhiều thao tác khác nhau. Hãy chọn cách biểu đạt đúng cấu trúc dữ liệu và dễ hiểu nhất đối với người bảo trì pipeline.

## 11. Ghi nhớ

- `map`: một phần tử nguồn tạo đúng một giá trị đầu ra.
- `filter`: giữ hoặc loại phần tử nguồn theo điều kiện.
- `flatMap`: chuyển mỗi phần tử thành Stream con rồi làm phẳng.
- `mapMulti`: phát không, một hoặc nhiều giá trị bằng Consumer.
- Dùng `mapMulti` khi vòng lặp hoặc các nhánh điều kiện mô tả logic phát kết quả tự nhiên.
- Không giả định `mapMulti` luôn nhanh hơn `flatMap`; đo hiệu năng nếu cần tối ưu.

Khi bắt đầu từ hình dạng đầu ra, ta thường chọn được đúng thao tác Stream ngay từ đầu. Pipeline nhờ đó ngắn gọn, dễ đọc và thể hiện rõ ý định xử lý dữ liệu.

