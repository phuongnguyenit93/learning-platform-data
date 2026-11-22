# Kết hợp dữ liệu qua chỉ mục Map thay cho lặp lồng tốn kém

Trong chương **Mẫu xử lý dữ liệu thực tế** của **Java Stream API**, nhiều pipeline xử lý một danh sách và cần bổ sung dữ liệu từ danh sách khác. Chẳng hạn, từ mỗi đơn hàng ta cần lấy tên khách hàng; từ mỗi dòng bán hàng ta cần lấy thông tin sản phẩm; hoặc từ mỗi sự kiện ta cần gắn cấu hình dịch vụ. Đây là phép **kết hợp dữ liệu theo khóa** (*key-based join*).

Cách đơn giản nhất là tìm kiếm ở danh sách thứ hai cho từng phần tử của danh sách thứ nhất. Nhưng nếu có hàng trăm nghìn đơn hàng và hàng chục nghìn khách hàng, việc tìm kiếm lặp đi lặp lại có thể trở thành nút thắt. Một mẫu thiết kế hiệu quả hơn là **lập chỉ mục bằng `Map` một lần**, sau đó tra cứu theo khóa trong pipeline `map`, `filter` hoặc `flatMap`.

Bài này hướng dẫn cách cải thiện chi phí từ **O(N × M)** xuống **O(N + M)** *trung bình trong mô hình tra cứu hash*, đồng thời giữ đúng ngữ nghĩa của phép kết hợp: bản ghi thiếu khóa, khóa trùng, kết hợp một-một/một-nhiều, thứ tự kết quả và giới hạn bộ nhớ. Mục tiêu không chỉ là “chạy nhanh hơn” mà còn **không âm thầm bỏ mất hoặc ghép sai dữ liệu nghiệp vụ**.

## 1. Bài toán mẫu: đơn hàng và khách hàng

Giả sử có hai nguồn:

~~~java
record Customer(String id, String name) {}

record Order(
        String id,
        String customerId,
        java.math.BigDecimal amount
) {}
~~~

Dữ liệu:

~~~text
customers:
  C-01 -> An
  C-02 -> Bình
  C-03 -> Chi

orders:
  O-1 -> C-01, 100.00
  O-2 -> C-02,  50.00
  O-3 -> C-01,  20.00
  O-4 -> C-99,  35.00
~~~

Yêu cầu chính: với mỗi đơn hàng có khách hàng tương ứng, tạo bản ghi:

~~~text
(orderId, customerId, customerName, amount)
~~~

Đầu ra dự kiến cho phép kết hợp **inner join**:

~~~text
O-1 -> C-01 -> An    -> 100.00
O-2 -> C-02 -> Bình  -> 50.00
O-3 -> C-01 -> An    -> 20.00
~~~

Đơn `O-4` tham chiếu `C-99` không có trong danh sách khách hàng, nên không xuất hiện trong **inner join**. Tuy nhiên, trong báo cáo kiểm soát dữ liệu, chúng ta không được coi đơn đó là không tồn tại: cần có cách ghi nhận hoặc truy vấn riêng các bản ghi **không tìm thấy khóa**.

Vì `C-01` xuất hiện trong hai đơn, quan hệ ở chiều `Order -> Customer` là **nhiều-một**: nhiều đơn hàng cùng tham chiếu một khách hàng. Khi xây chỉ mục khách hàng, mỗi `customerId` phải tương ứng đúng một khách hàng theo hợp đồng.

## 2. Cách dễ viết nhưng tốn kém: tìm tuyến tính bên trong vòng lặp

Một triển khai tuần tự thường gặp:

~~~java
import java.util.ArrayList;
import java.util.List;

List<EnrichedOrder> result = new ArrayList<>();

for (Order order : orders) {
    for (Customer customer : customers) {
        if (customer.id().equals(order.customerId())) {
            result.add(new EnrichedOrder(
                    order.id(),
                    customer.id(),
                    customer.name(),
                    order.amount()
            ));
            break;
        }
    }
}
~~~

`EnrichedOrder` là record kết quả sẽ được khai báo trong chương trình hoàn chỉnh ở phần sau.

Vòng lặp ngoài duyệt `N` đơn hàng; vòng lặp trong có thể phải duyệt tới `M` khách hàng cho mỗi đơn. Nếu không tìm thấy khóa, nó thường phải xem hết toàn bộ danh sách khách hàng.

Một cách dùng Stream tương tự nhưng không cải thiện độ phức tạp:

~~~java
List<EnrichedOrder> joined = orders.stream()
        .flatMap(order -> customers.stream()
                .filter(c -> c.id().equals(order.customerId()))
                .limit(1)
                .map(c -> new EnrichedOrder(
                        order.id(), c.id(), c.name(), order.amount()))
        )
        .toList();
~~~

Đoạn này biểu đạt phép tìm kiếm bằng `flatMap`/`filter`, nhưng **vẫn tạo một lượt tìm kiếm trong `customers` cho từng đơn hàng**. Viết dạng khai báo không tự động biến thuật toán tìm kiếm tuyến tính thành tra cứu hiệu quả.

### Phân tích chi phí

Ký hiệu:

- `N`: số đơn hàng.
- `M`: số khách hàng.
- `K`: số bản ghi kết quả cần tạo.

Với vòng lặp lồng hoặc Stream lồng như trên:

- **Thời gian xấu nhất:** O(N × M) để tìm khách hàng.
- **Bộ nhớ bổ sung cho tra cứu:** gần O(1), chưa tính bộ nhớ giữ kết quả O(K).
- Nếu mỗi đơn hàng tìm thấy khách ở đầu danh sách, thời gian thực tế có thể nhỏ hơn; nhưng không có đảm bảo khi dữ liệu tăng hoặc thứ tự thay đổi.

Ví dụ `N = 200.000` đơn hàng, `M = 50.000` khách hàng có thể dẫn đến rất nhiều phép so sánh ID. Không nên kết luận “không đáng kể” chỉ vì bộ dữ liệu thử nghiệm vài chục dòng chạy nhanh.

## 3. Mẫu tối ưu: tạo chỉ mục Map một lần

Nếu mỗi khách hàng có `id` duy nhất, chuyển danh sách khách thành:

~~~text
Map<CustomerId, Customer>

"C-01" -> Customer("C-01", "An")
"C-02" -> Customer("C-02", "Bình")
"C-03" -> Customer("C-03", "Chi")
~~~

Có thể dùng `Collectors.toMap`:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Customer> customerById = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));
~~~

Giải thích:

1. `Customer::id` tạo khóa kiểu `String`.
2. `Function.identity()` giữ chính đối tượng `Customer` làm giá trị.
3. `collect(Collectors.toMap(...))` vật hóa chỉ mục `Map` **một lần**.
4. Mỗi đơn hàng sau đó chỉ cần `customerById.get(order.customerId())` để tìm thông tin khách.

Với một `HashMap` điển hình, thao tác `get` có độ phức tạp kỳ vọng O(1) khi `hashCode`/`equals` và phân bố khóa phù hợp. Vì vậy, chi phí tổng quát trở thành:

~~~text
Xây chỉ mục khách hàng: O(M) trung bình
Tra cứu cho N đơn:      O(N) trung bình
Tạo K kết quả:          O(K)

Tổng:                  O(M + N + K)
Bộ nhớ chỉ mục:         O(M)
~~~

Ở phép kết hợp nhiều-một mà mỗi đơn tạo tối đa một bản ghi, `K <= N`, nên thường viết ngắn là **O(M + N)** kỳ vọng. Đó không phải giới hạn thời gian tuyệt đối của mọi kiểu `Map`: hiệu quả phụ thuộc loại Map, hashing, va chạm và chi phí tính khóa.

**Đánh đổi quan trọng:** Ta sử dụng thêm bộ nhớ O(M) để giảm số lần quét danh sách khách hàng. Nếu danh sách bên phải không đủ nhỏ để giữ trong bộ nhớ, cần chiến lược khác như join tại cơ sở dữ liệu, xử lý theo lô hoặc external join.

## 4. Chương trình hoàn chỉnh với inner join, left join và anti join

Đoạn mã sau là một chương trình tự chứa cho **Java 17+**, sử dụng `record` và `Stream.toList()` (Java 16+). Lưu vào `MapJoinDemo.java` để thử nghiệm.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class MapJoinDemo {

    record Customer(String id, String name) {}

    record Order(String id, String customerId, BigDecimal amount) {}

    record EnrichedOrder(
            String orderId,
            String customerId,
            String customerName,
            BigDecimal amount
    ) {}

    record LeftJoinedOrder(Order order, Optional<Customer> customer) {}

    static Map<String, Customer> indexCustomers(
            List<Customer> customers) {

        return customers.stream()
                .collect(Collectors.toMap(
                        Customer::id,
                        Function.identity()
                ));
    }

    // Inner join: chỉ giữ đơn có khách hàng tương ứng.
    static List<EnrichedOrder> innerJoin(
            List<Order> orders,
            Map<String, Customer> customerById) {

        return orders.stream()
                .flatMap(order -> {
                    Customer customer =
                            customerById.get(order.customerId());

                    if (customer == null) {
                        return Stream.<EnrichedOrder>empty();
                    }

                    return Stream.of(new EnrichedOrder(
                            order.id(),
                            customer.id(),
                            customer.name(),
                            order.amount()
                    ));
                })
                .toList();
    }

    // Left join: giữ mọi đơn, kể cả đơn không có khách.
    static List<LeftJoinedOrder> leftJoin(
            List<Order> orders,
            Map<String, Customer> customerById) {

        return orders.stream()
                .map(order -> new LeftJoinedOrder(
                        order,
                        Optional.ofNullable(
                                customerById.get(order.customerId()))
                ))
                .toList();
    }

    // Anti join: chỉ lấy những đơn tham chiếu khách không tồn tại.
    static List<Order> unmatchedOrders(
            List<Order> orders,
            Map<String, Customer> customerById) {

        return orders.stream()
                .filter(order -> !customerById.containsKey(
                        order.customerId()))
                .toList();
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
                new Customer("C-01", "An"),
                new Customer("C-02", "Bình"),
                new Customer("C-03", "Chi")
        );

        List<Order> orders = List.of(
                new Order("O-1", "C-01", new BigDecimal("100.00")),
                new Order("O-2", "C-02", new BigDecimal("50.00")),
                new Order("O-3", "C-01", new BigDecimal("20.00")),
                new Order("O-4", "C-99", new BigDecimal("35.00"))
        );

        Map<String, Customer> customerById =
                indexCustomers(customers);

        List<EnrichedOrder> matched =
                innerJoin(orders, customerById);

        List<LeftJoinedOrder> allOrders =
                leftJoin(orders, customerById);

        List<Order> unmatched =
                unmatchedOrders(orders, customerById);

        System.out.println("Inner count: " + matched.size());
        // 3

        matched.forEach(item ->
                System.out.println(
                        item.orderId() + " -> " +
                        item.customerName() + ": " +
                        item.amount()
                ));

        System.out.println("Left count: " + allOrders.size());
        // 4

        System.out.println("Missing order IDs: " +
                unmatched.stream().map(Order::id).toList());
        // [O-4]

        System.out.println(
                allOrders.get(3).customer().isEmpty());
        // true: O-4 không tìm thấy C-99.
    }
}
~~~

Ví dụ minh họa `Optional<Customer>` ở bản ghi kết quả **để thể hiện rõ trạng thái có/không có khách**, thay vì dùng tên giả như `"UNKNOWN"` có thể trùng tên thật. Trong mô hình lưu trữ thực tế, cũng có thể dùng kiểu kết quả riêng thể hiện `Matched`/`Missing` hoặc cờ trạng thái cùng thông tin lỗi.

Chạy:

~~~bash
javac MapJoinDemo.java
java MapJoinDemo
~~~

Đầu ra quan trọng:

~~~text
Inner count: 3
O-1 -> An: 100.00
O-2 -> Bình: 50.00
O-3 -> An: 20.00
Left count: 4
Missing order IDs: [O-4]
true
~~~

Các thao tác `get` và `containsKey` trên `customerById` là **đọc chỉ mục**. Map được tạo xong trước khi Stream đơn hàng bắt đầu xử lý, không bị thêm/xóa khóa trong lúc join.

## 5. Ba loại join và chính sách bản ghi thiếu khóa

Kết hợp hai nguồn không có một ý nghĩa duy nhất. Cần định nghĩa loại join trước khi viết pipeline.

| Loại | Điều kiện đưa đơn hàng vào kết quả | Ví dụ với `O-4` |
| --- | --- | --- |
| **Inner join** | Có ít nhất một khách hàng phù hợp | Loại khỏi kết quả đã ghép |
| **Left join** | Giữ mọi đơn hàng; phần khách có thể thiếu | Giữ `O-4` và đánh dấu thiếu khách |
| **Anti join** | Không có khách hàng phù hợp | Chỉ giữ `O-4` trong danh sách kiểm tra |

### 5.1. Inner join: đừng che giấu dữ liệu lỗi

`innerJoin(...)` thích hợp khi chỉ cần các cặp đã ghép thành công. Nhưng nếu hệ thống yêu cầu báo cáo toàn bộ đơn hàng, `O-4` không được biến mất một cách im lặng.

Thiết kế an toàn là **xuất cả thống kê số lượng chưa ghép**, hoặc chạy thêm anti join trên cùng Map chỉ mục đã tạo. Điều này giúp phân biệt “không có dữ liệu đầu vào” với “có dữ liệu nhưng thiếu quan hệ”.

### 5.2. Left join: giữ một kết quả cho mỗi đơn

`leftJoin(...)` bảo toàn đúng số lượng và thứ tự của `orders` khi dùng nguồn `List` có encounter order và pipeline không thay đổi thứ tự. `Optional.empty()` biểu diễn thiếu dữ liệu quan hệ.

Không nên tự điền tên khách `"Không rõ"` trong logic tổng hợp rồi giả định đây là khách hàng có thật. Nếu giao diện cần nhãn hiển thị, hãy xử lý placeholder ở tầng trình bày.

### 5.3. Anti join: phát hiện dữ liệu mồ côi

~~~java
List<Order> missing = orders.stream()
        .filter(order -> !customerById.containsKey(
                order.customerId()))
        .toList();
~~~

Mẫu này là công cụ kiểm tra dữ liệu tham chiếu (*referential integrity*). Nó thường hữu ích trong ETL, migration, đồng bộ dữ liệu hoặc kiểm thử chất lượng nguồn.

Khi dùng `containsKey`, chúng ta phân biệt khóa **vắng mặt** với khóa có giá trị `null` ở các Map cho phép null. Bài này chủ động xây Map giá trị `Customer` không null, nên `get(...) == null` cũng tương ứng không có khách; nhưng `containsKey` thể hiện chính xác ý định kiểm tra sự tồn tại của khóa.

## 6. Khóa trùng: không thể lập chỉ mục duy nhất bằng cách bỏ qua dữ liệu

`Collectors.toMap(Customer::id, Function.identity())` **ném `IllegalStateException` khi có hai khách hàng cùng ID**:

~~~java
List<Customer> duplicated = List.of(
        new Customer("C-01", "An"),
        new Customer("C-01", "Anh")
);

// IllegalStateException: duplicate key
Map<String, Customer> invalidIndex = duplicated.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));
~~~

Điều này có thể là **đúng mong muốn** nếu `Customer.id` được quy định duy nhất. Ngoại lệ giúp phát hiện dữ liệu nguồn không tuân thủ hợp đồng thay vì âm thầm chọn một khách ngẫu nhiên.

### 6.1. Cần phân biệt xung đột và quan hệ một-nhiều

- Nếu mỗi ID phải là duy nhất: **báo lỗi hoặc loại bỏ dữ liệu không hợp lệ theo quy trình xác thực**.
- Nếu mỗi ID có thể ứng với nhiều phiên bản bản ghi: **định nghĩa quy tắc chọn bản ghi** dựa trên timestamp/version đáng tin cậy, hoặc giữ tất cả bằng `groupingBy`.
- Nếu khóa thực sự là cặp `(tenantId, customerId)`: **xây khóa ghép**, không xem hai khách ở hai tenant là một người.
- Nếu khóa được chuẩn hóa dẫn đến va chạm: **xác định cách giải quyết khóa trùng sau chuẩn hóa**, không ghi đè tùy tiện.

Có thể dùng overload ba tham số của `toMap` để gộp:

~~~java
Map<String, Customer> chosen = duplicated.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (first, next) -> first
        ));
~~~

Nhưng `(first, next) -> first` chỉ đúng khi nghiệp vụ cho phép **giữ phần tử đầu theo encounter order đã xác định**. Với nguồn không có thứ tự hoặc khi cần bản ghi mới nhất, cách này có thể trả dữ liệu sai. Đặc biệt không thêm merge function chỉ để “hết lỗi duplicate key” mà không kiểm tra mất dữ liệu.

### 6.2. Nếu cần phiên bản mới nhất, dùng tiêu chí quyết định ổn định

Giả sử có:

~~~java
import java.time.Instant;

record CustomerVersion(
        String id,
        String name,
        Instant updatedAt,
        long version
) {}
~~~

Chọn phiên bản theo `version` lớn hơn:

~~~java
Map<String, CustomerVersion> latestById =
        versions.stream()
                .collect(Collectors.toMap(
                        CustomerVersion::id,
                        Function.identity(),
                        (a, b) -> {
                            if (a.version() > b.version()) return a;
                            if (b.version() > a.version()) return b;
                            throw new IllegalStateException(
                                    "Conflicting versions for " + a.id());
                        }
                ));
~~~

Ví dụ giả định `versions` là collection các `CustomerVersion`. Quy tắc cố ý từ chối hai bản ghi có **cùng ID và cùng version**, thay vì lựa chọn tùy ý theo lịch thực thi. Trong một hệ thống khác, có thể dùng timestamp kèm tiêu chí phá hòa ổn định; chính sách luôn cần xuất phát từ nghiệp vụ.

## 7. Một-nhiều: dùng groupingBy để tạo chỉ mục danh sách

`toMap` với một giá trị cho mỗi khóa không giải quyết trực tiếp yêu cầu **mỗi khách có nhiều đơn hàng** nếu muốn giữ toàn bộ đơn.

Trong trường hợp cần tìm tất cả đơn của mỗi khách, đảo chiều chỉ mục:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> ordersByCustomerId = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));

System.out.println(ordersByCustomerId.get("C-01").size());
// 2
~~~

Ở đây, giá trị của Map là `List<Order>`, không phải một `Order` duy nhất. `groupingBy` giữ toàn bộ đơn có cùng `customerId`.

Giả sử ứng dụng cần lấy **mỗi khách cùng mọi đơn hàng** để xuất báo cáo. Có thể dùng:

~~~java
record CustomerOrder(Customer customer, Order order) {}

List<CustomerOrder> pairs = customers.stream()
        .flatMap(customer -> ordersByCustomerId
                .getOrDefault(customer.id(), List.of())
                .stream()
                .map(order -> new CustomerOrder(customer, order)))
        .toList();

System.out.println(pairs.size()); // 3
~~~

Dữ liệu ví dụ có ba đơn ghép được với khách hiện có. Khách `C-03` chưa có đơn nên không xuất hiện trong danh sách cặp; đơn `O-4` có khóa `C-99` không tìm thấy khách nên cũng không xuất hiện.

**Quan trọng về thứ tự:** Với pipeline trên, kết quả sắp theo thứ tự **khách hàng trước, đơn hàng trong từng nhóm sau** theo encounter order của nguồn đã dùng. Nó có thể khác thứ tự khi lấy `orders` làm nguồn ngoài. Nếu báo cáo yêu cầu đúng thứ tự đơn hàng gốc, hãy dùng `orders.stream()` cùng chỉ mục khách.

### Chi phí một-nhiều

Với `N` đơn hàng, `M` khách và `K` cặp được tạo, `groupingBy` thường xây chỉ mục trong O(N) trung bình; duyệt `M` khách cùng các nhóm của họ tạo O(M + K) công việc bổ sung. Tổng kỳ vọng **O(N + M + K)**, với bộ nhớ để giữ các danh sách nhóm O(N) cộng kết quả O(K).

Với quan hệ **nhiều-nhiều** có thể phát sinh rất nhiều cặp kết quả, `K` có thể rất lớn, thậm chí tương đương tích số lượng các phần tử ở một nhóm. Không có tối ưu Map nào loại bỏ được chi phí phải thực sự tạo và xử lý `K` cặp nếu nghiệp vụ đòi mọi kết hợp.

## 8. Khóa ghép: tenantId và customerId

Một nguyên nhân phổ biến làm sai join là dùng một khóa **chưa đủ thông tin định danh**. Ví dụ khách `C-01` có thể tồn tại ở nhiều tenant. Chỉ dùng `customerId` sẽ ghép chéo dữ liệu.

Từ Java 16, `record` là một cách tạo khóa ghép bất biến gọn:

~~~java
record CustomerKey(String tenantId, String customerId) {}

record TenantCustomer(
        String tenantId,
        String customerId,
        String name
) {}

record TenantOrder(
        String id,
        String tenantId,
        String customerId
) {}
~~~

Xây chỉ mục:

~~~java
Map<CustomerKey, TenantCustomer> byKey = tenantCustomers.stream()
        .collect(Collectors.toMap(
                c -> new CustomerKey(c.tenantId(), c.customerId()),
                Function.identity()
        ));
~~~

Tra cứu:

~~~java
List<String> names = tenantOrders.stream()
        .map(order -> byKey.get(
                new CustomerKey(order.tenantId(), order.customerId())))
        .filter(java.util.Objects::nonNull)
        .map(TenantCustomer::name)
        .toList();
~~~

`tenantCustomers` và `tenantOrders` là các collection tương ứng của hai record trên. `record` tự cung cấp `equals` và `hashCode` theo các thành phần, rất phù hợp với khóa Map **nếu các thành phần ổn định**.

Nếu hệ thống có các khóa mutable, việc thay đổi trường tham gia `equals`/`hashCode` sau khi thêm vào một `HashMap` có thể làm mất khả năng tra cứu đúng. Vì vậy, ưu tiên định danh bất biến.

## 9. Chuẩn hóa khóa: phải làm đối xứng ở hai phía

Dữ liệu đến từ hai hệ thống có thể dùng định dạng ID khác nhau:

~~~text
Nguồn khách: " c-01 "
Nguồn đơn:   "C-01"
~~~

Nếu nghiệp vụ công bố rằng chữ hoa/thường và khoảng trắng xung quanh không có ý nghĩa, chuẩn hóa khóa **cùng một cách** ở cả lúc xây Map và lúc tra cứu:

~~~java
import java.util.Locale;

static String canonicalId(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Missing customer ID");
    }

    String result = raw.trim().toUpperCase(Locale.ROOT);
    if (result.isEmpty()) {
        throw new IllegalArgumentException("Blank customer ID");
    }
    return result;
}
~~~

Index:

~~~java
Map<String, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                c -> canonicalId(c.id()),
                Function.identity()
        ));
~~~

Tra cứu:

~~~java
List<EnrichedOrder> joined = orders.stream()
        .flatMap(order -> {
            Customer customer = index.get(
                    canonicalId(order.customerId()));

            return customer == null
                    ? Stream.<EnrichedOrder>empty()
                    : Stream.of(new EnrichedOrder(
                            order.id(),
                            order.customerId(),
                            customer.name(),
                            order.amount()));
        })
        .toList();
~~~

Chuẩn hóa ID là **quyết định nghiệp vụ**, không phải mẹo tối ưu có thể áp dụng cho mọi dữ liệu. Một số định danh phân biệt chữ hoa/thường hoặc có dấu cách có ý nghĩa. Nếu chuẩn hóa làm hai ID trước đó khác nhau trở thành một, `toMap` có thể ném duplicate key — đó là dấu hiệu cần xử lý xung đột, không phải ngoại lệ nên che đi.

Với Unicode phức tạp, `trim`/`toUpperCase(Locale.ROOT)` cũng chưa phải chuẩn hóa tổng quát cho mọi ngôn ngữ hoặc chuẩn mã. Hãy dùng quy tắc canonicalization được hệ thống dữ liệu công bố.

## 10. Không biến null thành “khóa hợp lệ” một cách ngầm định

Phép join cần chính sách rõ cho trường hợp thiếu khóa:

- **Khóa `null` trong đơn hàng:** dữ liệu lỗi, đơn chưa gắn khách, hay một loại khách đặc biệt?
- **Khóa `null` trong bảng khách:** có được phép tồn tại một bản ghi không có ID?
- **Giá trị mapper trả `null`:** `Collectors.toMap` có hợp đồng không giống mọi Map tự tạo, và giá trị `null` thường khiến thao tác thu thập thất bại.
- **Không tìm thấy khóa trong Map:** một tình trạng dữ liệu khác với việc bản ghi nguồn là `null`.

Trong bài toán có ràng buộc toàn vẹn tham chiếu, nên xác thực khóa không rỗng:

~~~java
import java.util.Objects;

Map<String, Customer> customerById = customers.stream()
        .collect(Collectors.toMap(
                customer -> Objects.requireNonNull(
                        customer.id(), "Customer ID is required"),
                Function.identity()
        ));
~~~

Khi tra cứu:

~~~java
String id = Objects.requireNonNull(
        order.customerId(), "Order customerId is required");

Customer customer = customerById.get(id);
~~~

Không nên làm:

~~~java
String key = String.valueOf(order.customerId());
~~~

Nếu `customerId == null`, biểu thức trên trả chuỗi `"null"`; nó có thể trùng một ID thực và tạo phép ghép sai. Tương tự, thay null bằng chuỗi rỗng hoặc một tên khách mặc định chỉ hợp lệ khi có quy tắc nghiệp vụ riêng.

Nếu mục tiêu không phải từ chối dữ liệu, hãy ghi nhận các đơn thiếu ID vào **nhóm kiểm tra riêng**, không trộn chúng với đơn có ID nhưng không tìm thấy khách.

## 11. Kết hợp việc tra cứu với tính tổng, không cần lưu mọi cặp

Trong báo cáo doanh thu, đôi khi chỉ cần tổng tiền theo khách hàng đã xác thực, không cần một `List<EnrichedOrder>` cho từng đơn.

Từ cùng Map chỉ mục:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> revenueByCustomer = orders.stream()
        .filter(order -> customerById.containsKey(
                order.customerId()))
        .collect(Collectors.toMap(
                Order::customerId,
                Order::amount,
                BigDecimal::add
        ));
~~~

Ở đây:

- `filter` chỉ giữ đơn có ID khách được xác thực.
- `Order::customerId` tạo khóa tổng hợp.
- `Order::amount` tạo giá trị tiền.
- `BigDecimal::add` gộp những khoản có cùng khách **chính xác theo số học thập phân** nếu đầu vào đã được tạo từ chuỗi thập phân chính xác.
- Map kết quả chỉ giữ **một tổng tiền cho mỗi khóa**, không giữ mọi cặp join.

Với dữ liệu ví dụ:

~~~text
C-01 -> 120.00
C-02 ->  50.00
~~~

Đơn `O-4` không có khách tương ứng nên không tham gia báo cáo doanh thu theo khách **đã xác thực**. Nếu báo cáo tài chính yêu cầu tổng tất cả đơn, không được âm thầm loại `O-4`: phải cộng riêng nhóm chưa ghép hoặc báo lỗi chất lượng dữ liệu trước khi chốt báo cáo.

### Không làm tròn trong hàm gộp

Khi tổng hợp tiền bằng `BigDecimal`, chọn rõ **điểm làm tròn nghiệp vụ**. Nếu cần cộng chính xác toàn bộ các khoản rồi làm tròn tại cấp khách/hóa đơn, hãy giữ `BigDecimal::add` trong collector và áp dụng `setScale(scale, mode)` ở bước cuối. Làm tròn sau mỗi lần cộng có thể làm kết quả phụ thuộc thứ tự nhóm và gây khác biệt khi chuyển sang parallel stream.

## 12. Tạo chỉ mục một lần và tái sử dụng hợp lý

Một lỗi giảm hiệu quả là **xây lại Map cho từng đơn hàng**:

~~~java
// Rất tốn kém: xây lại toàn bộ Map trong mỗi lần map.
List<String> names = orders.stream()
        .map(order -> {
            Map<String, Customer> index = customers.stream()
                    .collect(Collectors.toMap(
                            Customer::id,
                            Function.identity()));
            Customer c = index.get(order.customerId());
            return c == null ? null : c.name();
        })
        .toList();
~~~

Cách này thậm chí có thể tốn **O(N × M)** thời gian và O(M) cấp phát Map lặp lại, không giải quyết nút thắt ban đầu.

Đặt index **ngoài** pipeline:

~~~java
Map<String, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));

List<String> names = orders.stream()
        .map(order -> index.get(order.customerId()))
        .filter(java.util.Objects::nonNull)
        .map(Customer::name)
        .toList();
~~~

Điều kiện tái sử dụng: dữ liệu khách hàng phải ổn định theo yêu cầu báo cáo. Nếu khách được cập nhật sau khi xây chỉ mục, Map không tự đồng bộ với danh sách nguồn.

- Nếu ứng dụng xử lý **snapshot**: tạo index mới mỗi lần lấy snapshot mới, hoặc gắn cache với version dữ liệu.
- Nếu ứng dụng xử lý **trạng thái sống** thay đổi liên tục: phải có cơ chế đồng bộ, invalidation hoặc truy vấn nguồn nhất quán.
- Nếu giá trị trong Map là đối tượng mutable: đọc index không bảo đảm các trường của đối tượng đó bất biến.

Không nên giữ `static Map` dùng mãi mà không có quy tắc cập nhật rõ, vì dữ liệu ghép có thể trở nên cũ dù phép tra cứu rất nhanh.

## 13. Thứ tự kết quả: Map index không phải nơi quyết định order

Nếu nguồn `orders` là `List` có thứ tự và dùng:

~~~java
List<EnrichedOrder> result = orders.stream()
        .flatMap(order -> {
            Customer customer = customerById.get(
                    order.customerId());

            if (customer == null) {
                return Stream.<EnrichedOrder>empty();
            }

            return Stream.of(new EnrichedOrder(
                    order.id(), customer.id(),
                    customer.name(), order.amount()));
        })
        .toList();
~~~

Kết quả `toList()` giữ thứ tự xuất hiện các đơn được ghép từ Stream có encounter order. **Việc HashMap không cam kết thứ tự duyệt khóa không làm mất thứ tự này**, vì pipeline duyệt `orders`, chỉ dùng Map để tra cứu.

Ngược lại:

~~~java
List<Customer> list = customerById.values().stream().toList();
~~~

Thứ tự của danh sách này phụ thuộc thứ tự duyệt của Map; với HashMap, không nên dựa vào thứ tự đó. Nếu cần xuất khách hàng theo ID, dùng `sorted(Comparator.comparing(Customer::id))`. Nếu cần thứ tự chèn của khóa Map, dùng `LinkedHashMap` có supplier phù hợp khi xây Map và duyệt theo hợp đồng của nó.

**Chọn thứ tự từ yêu cầu nghiệp vụ**, không từ quan sát tình cờ trong một lần chạy JDK.

## 14. Song song hóa: Map chỉ đọc an toàn hơn trạng thái dùng chung có ghi

Một Map chỉ mục được xây đầy đủ **trước** pipeline và không bị thay đổi trong khi chạy có thể được nhiều tác vụ đọc đồng thời phù hợp khi các giá trị cũng được sử dụng theo cách không can thiệp.

~~~java
Map<String, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));

List<EnrichedOrder> result = orders.parallelStream()
        .flatMap(order -> {
            Customer customer = index.get(order.customerId());

            if (customer == null) {
                return Stream.<EnrichedOrder>empty();
            }

            return Stream.of(new EnrichedOrder(
                    order.id(), customer.id(),
                    customer.name(), order.amount()));
        })
        .toList();
~~~

Trong ví dụ, mapper chỉ đọc `index` và tạo record mới; không thêm/xóa Map. Với `orders` là `List` có encounter order, `toList` vẫn giữ thứ tự đầu ra của các đơn đã ghép, dù việc xử lý các phần tử bên trong có thể diễn ra không theo thứ tự nguồn.

**Không làm như sau:**

~~~java
Map<String, Long> counts = new java.util.HashMap<>();

orders.parallelStream().forEach(order ->
        counts.merge(order.customerId(), 1L, Long::sum));
~~~

Các cập nhật đồng thời vào `HashMap` dùng chung **không an toàn**. Nếu cần tổng hợp số lượng theo khóa, dùng `Collectors.groupingBy(..., counting())` hoặc một collector đồng thời phù hợp:

~~~java
Map<String, Long> counts = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::customerId,
                Collectors.counting()
        ));
~~~

Không suy rằng `parallelStream()` chắc chắn nhanh hơn. Chi phí chia nguồn, cấp phát object, hashing và ghép kết quả có thể vượt lợi ích nếu dữ liệu nhỏ hoặc lambda nhẹ. Với tác vụ I/O hoặc gọi API ngoài, parallel stream còn cần xem xét giới hạn đồng thời, timeout và tính idempotent.

## 15. Dữ liệu lớn hơn bộ nhớ: không cố xây một HashMap khổng lồ

Mẫu index bằng Map phù hợp khi **phía được lập chỉ mục** có thể giữ trong bộ nhớ. Nếu cả hai phía có hàng trăm triệu bản ghi, một `HashMap` chứa mọi khách hàng có thể tiêu thụ quá nhiều heap.

Một số chiến lược thay thế:

| Bối cảnh | Hướng tiếp cận |
| --- | --- |
| Dữ liệu đang nằm trong cơ sở dữ liệu | Để hệ quản trị xử lý `JOIN`/index qua truy vấn, tránh tải toàn bộ bảng về JVM |
| Một bên nhỏ, một bên rất lớn | Xây Map cho bên nhỏ, stream bên lớn theo lô hoặc đọc tuần tự |
| Hai bên lớn hơn RAM | External hash join, sort-merge join hoặc công cụ xử lý dữ liệu phân tán |
| Dữ liệu đổi thường xuyên và cần nhất quán | Dùng transaction/snapshot hoặc cache có version/invalidation |
| Phải trả hàng triệu cặp kết quả | Xử lý/ghi đầu ra theo luồng, không bắt buộc `toList()` toàn bộ |
| Khóa có độ phân biệt thấp hoặc many-to-many | Ước lượng số cặp `K` trước; Map chỉ mục không ngăn kết quả bùng nổ |

### Ví dụ nguồn I/O lớn

Giả sử đầu vào đơn hàng được đọc từ tệp. Ta có thể xây chỉ mục khách hàng trong bộ nhớ một lần, sau đó đọc đơn hàng **từng dòng** trong `try-with-resources`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// parseOrder là hàm parser theo định dạng file cụ thể.
try (Stream<String> lines =
             Files.lines(Path.of("orders.txt"), StandardCharsets.UTF_8)) {

    long matchedCount = lines
            .map(line -> parseOrder(line))
            .filter(order -> customerById.containsKey(
                    order.customerId()))
            .count();

    System.out.println(matchedCount);
}
~~~

Đây là **mẫu minh họa kiến trúc**, không phải chương trình độc lập: cần định nghĩa `parseOrder` theo định dạng file thật và hợp đồng xử lý lỗi. Điểm chính là không cần gọi `Files.readAllLines(...)` rồi tạo `List` chứa mọi đơn. `count()` ở đây chỉ lưu một số đếm; nếu dùng `toList()` trên toàn bộ kết quả, bộ nhớ vẫn tăng theo số phần tử đầu ra.

Tài nguyên `Files.lines` phải được đóng; terminal operation `count` không tự gọi `close()`. Nếu nguồn có lỗi I/O lazy, phải báo lỗi rõ, không coi đó là dữ liệu “không ghép được”.

## 16. Đặc tính HashMap, bộ nhớ và tính đúng của khóa

### 16.1. O(1) là kỳ vọng, không phải luật tuyệt đối

Một `HashMap` phụ thuộc `hashCode` và `equals` của khóa. Với khóa phù hợp và tải hợp lý, `get` rất hiệu quả trung bình. Va chạm hash quá nhiều, tính hash tốn kém hoặc cách tổ chức dữ liệu bất thường có thể làm hiệu năng xấu đi.

Nếu dùng `TreeMap`, tra cứu theo khóa thường có chi phí O(log M), đổi lại có thứ tự khóa và comparator rõ ràng. Chọn Map theo **hợp đồng dữ liệu** và kết quả đo thực tế.

### 16.2. Không sửa khóa mutable

Với khóa là một object chứa những trường dùng cho `equals`/`hashCode`, sửa các trường đó sau khi đưa vào Map có thể làm `get` không tìm thấy mục ở vị trí hash cũ. Nên dùng `String`, số, enum, hoặc record với các thành phần ổn định.

### 16.3. Đừng suy rằng Map là snapshot sâu

~~~java
Map<String, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));
~~~

Map này giữ các **tham chiếu tới đối tượng Customer gốc**. Với record `Customer` có trường `String` bất biến, ví dụ minh họa an toàn; nhưng nếu giá trị là một class mutable, sửa class ở nơi khác sẽ làm thông tin được đọc qua Map thay đổi. `Map.copyOf(index)` chỉ làm cấu trúc Map không sửa đổi được, không sao chép sâu đối tượng giá trị.

### 16.4. Duplicate key có thể phá cả hiệu năng lẫn đúng đắn

Một Map chứa một giá trị cho mỗi khóa không thể tự diễn tả “mỗi khóa có nhiều người” nếu mã định danh không duy nhất. Lỗi không phải do Stream hay Map chậm, mà do **mô hình dữ liệu**. Chuyển sang `Map<K, List<V>>` qua `groupingBy`, hoặc sửa định nghĩa khóa duy nhất, trước khi tối ưu.

## 17. So sánh những cách viết và cách chọn

| Cách xử lý | Thời gian kỳ vọng | Bộ nhớ phụ | Phù hợp khi |
| --- | --- | --- | --- |
| Lặp lồng `for` | O(N × M) | O(1) ngoài kết quả | Dữ liệu nhỏ, logic so khớp phức tạp, không cần index |
| `orders.stream()` rồi `customers.stream().filter(...)` mỗi lượt | O(N × M) | O(1) ngoài kết quả | Cú pháp khai báo nhưng không giải quyết nút thắt tra cứu |
| `toMap` tạo chỉ mục khách rồi lookup | O(N + M + K) | O(M) cộng kết quả | Khóa khách duy nhất, phía khách vừa bộ nhớ |
| `groupingBy` tạo Map khóa → danh sách | O(N + M + K) với hai phía và đầu ra phù hợp | O(số phần tử được nhóm) cộng kết quả | Một khóa có nhiều bản ghi cần giữ |
| `TreeMap` làm chỉ mục | Thường O(M log M + N log M + K) | O(M) cộng kết quả | Cần thứ tự khóa hoặc lookup theo comparator |
| Join tại DB | Phụ thuộc engine, chỉ mục, kích thước, kế hoạch truy vấn | Tùy server/query | Dữ liệu vốn nằm trong DB, cần filter/join gần nguồn |

Không được quên chi phí tạo output `K`. Nếu kết quả là toàn bộ các cặp nhiều-nhiều trong một nhóm lớn, thời gian tạo output có thể chi phối kể cả khi index xây rất nhanh.

## 18. Kiểm thử tính đúng trước khi benchmark

Một phép tối ưu join có thể chạy nhanh hơn nhưng **làm biến mất các bản ghi không khớp** hoặc chọn sai khi khóa trùng. Vì vậy, cần kiểm tra tính tương đương với một thuật toán tham chiếu đơn giản trên dữ liệu nhỏ.

### 18.1. Các bất biến quan trọng

Với **mỗi Order có tối đa một Customer đúng khóa**:

~~~text
leftJoin.size() = orders.size()

innerJoin.size() + unmatchedOrders.size() = orders.size()

mọi EnrichedOrder có customerId hợp lệ
mọi EnrichedOrder thuộc một Order đầu vào
~~~

Với dữ liệu mẫu:

~~~text
orders.size() = 4
innerJoin.size() = 3
unmatchedOrders.size() = 1
leftJoin.size() = 4
~~~

Nếu bài toán cho phép nhiều Customer trên cùng khóa, các bất biến số lượng này **không còn đúng** cho join nhiều-nhiều; đó là lý do cần xác định quan hệ trước.

### 18.2. Test trường hợp biên

| Trường hợp | Kỳ vọng |
| --- | --- |
| Không có khách, có đơn | Inner join rỗng, anti join chứa mọi đơn, left join vẫn có đủ đơn |
| Có khách, không có đơn | Mọi kết quả lấy đơn làm nguồn đều rỗng |
| Một khách, nhiều đơn | Mỗi đơn được ghép đúng cùng khách |
| Khóa khách trùng khi hợp đồng yêu cầu duy nhất | Lập chỉ mục thất bại rõ ràng |
| Đơn tham chiếu ID vắng mặt | Được ghi nhận theo chính sách thiếu khóa |
| ID có `null` hoặc rỗng | Xử lý theo validation, không tự biến thành ID khác |
| Hai tenant có cùng customerId | Dùng khóa ghép để tránh ghép chéo |
| Khóa khác hoa/thường hoặc khoảng trắng | Chỉ chuẩn hóa nếu hợp đồng cho phép, áp dụng hai phía |
| Nguồn có thứ tự | Kết quả danh sách phải giữ thứ tự nếu pipeline có hợp đồng đó |
| Song song | Nội dung kết quả giữ đúng, không có ghi Map dùng chung |
| Dữ liệu cực lớn | Đo cả thời gian xây Map, heap và chi phí tạo output |

### 18.3. Test logic mẫu

Trong bối cảnh cùng lớp hoặc truy cập được các record của `MapJoinDemo`:

~~~java
Map<String, Customer> index =
        MapJoinDemo.indexCustomers(customers);

var inner = MapJoinDemo.innerJoin(orders, index);
var left = MapJoinDemo.leftJoin(orders, index);
var missing = MapJoinDemo.unmatchedOrders(orders, index);

if (inner.size() != 3 ||
        left.size() != 4 ||
        missing.size() != 1 ||
        !"O-4".equals(missing.get(0).id())) {
    throw new AssertionError("Join result does not match specification");
}
~~~

Với dữ liệu bất kỳ, kiểm tra thêm tính tương đương **theo khóa và số lượng cặp**, không chỉ so kích thước. Ví dụ hai bản ghi bị ghép nhầm vẫn có thể tạo đúng tổng số phần tử.

### 18.4. Benchmark có ý nghĩa

Để so sánh vòng lặp lồng với Map index, đo đủ:

1. Thời gian **xây Map**, không chỉ thời gian lookup.
2. Thời gian **tra cứu và tạo kết quả**, với cùng bộ dữ liệu và cùng chính sách join.
3. Bộ nhớ Map và bộ nhớ của kết quả đã vật hóa.
4. Trường hợp đơn hàng lặp ID khách nhiều lần; trường hợp phần lớn ID không tồn tại.
5. Chi phí warm-up/JIT và GC; sử dụng JMH khi cần đánh giá nghiêm túc.

Một phép đo duy nhất với `System.nanoTime()` trên 100 phần tử không đủ để kết luận tốc độ trong ứng dụng thực. Khi khối dữ liệu chỉ vài phần tử, overhead xây Map có thể lớn hơn lợi ích từ tra cứu.

## 19. Bài tập thực hành

### Bài 1 — Chuyển vòng lặp lồng sang tra cứu Map

Có `List<Product> products` và `List<OrderLine> lines`, mỗi `OrderLine` chứa `productId`, `quantity`, còn `Product` chứa `id`, `unitPrice`. Viết pipeline tính thành tiền với chi phí tra cứu O(M + N) trung bình.

**Gợi ý/đáp án:**

~~~java
Map<String, Product> productById = products.stream()
        .collect(Collectors.toMap(
                Product::id,
                Function.identity()
        ));

List<BigDecimal> amounts = lines.stream()
        .map(line -> {
            Product product = productById.get(line.productId());

            if (product == null) {
                throw new IllegalArgumentException(
                        "Unknown product: " + line.productId());
            }

            return product.unitPrice().multiply(
                    BigDecimal.valueOf(line.quantity()));
        })
        .toList();
~~~

Các record `Product` và `OrderLine` là giả định của bài tập; cần khai báo kiểu và trường tương ứng. Ví dụ chọn **báo lỗi khi thiếu sản phẩm** vì không thể tính thành tiền đúng nếu thiếu đơn giá.

### Bài 2 — Chọn đúng loại join

Từ dữ liệu khách và đơn ở phần 1:

- Báo cáo doanh thu chỉ gồm khách tồn tại: dùng gì?
- Danh sách kiểm soát các đơn không có khách: dùng gì?
- Bảng xuất tất cả đơn kèm thông tin khách nếu có: dùng gì?

**Đáp án:** Inner join hoặc tổng hợp có xác thực; anti join; left join tương ứng. Không dùng inner join cho bảng kiểm soát toàn bộ đơn vì nó làm biến mất `O-4`.

### Bài 3 — Xử lý trùng khóa

Nguồn có hai khách cùng ID `C-01`. Có nên thêm `(old, next) -> next` để loại ngoại lệ?

**Đáp án:** Chỉ khi nghiệp vụ đã cho phép chọn bản ghi được xử lý sau **và** thứ tự nguồn có ý nghĩa tương ứng. Nếu ID phải duy nhất, hãy để lỗi được báo ra. Nếu ID có nhiều phiên bản, cần tiêu chí version/timestamp và tie-breaker ổn định hoặc `groupingBy` để giữ các phiên bản.

### Bài 4 — Tính độ phức tạp

Có `N = 100.000` đơn và `M = 20.000` khách, mỗi đơn có đúng một khóa khách. So sánh độ phức tạp tìm kiếm tuyến tính lặp lại và cách tạo Map.

**Đáp án:** Vòng lặp lồng có giới hạn thời gian xấu nhất O(N × M); Map index hash có thời gian kỳ vọng O(M + N) để lập chỉ mục và tra cứu, cộng chi phí tạo kết quả O(K). Map tốn thêm O(M) bộ nhớ. Không suy ra số mili-giây cụ thể khi chưa đo.

### Bài 5 — Một khách có nhiều đơn

Cần xây `Map<String, List<Order>>` mà không mất đơn trùng khóa. Nên dùng `toMap(Order::customerId, Function.identity())` hay `groupingBy(Order::customerId)`?

**Đáp án:** `groupingBy(Order::customerId)`. `toMap` hai tham số ném duplicate key; merge chọn giữ một đơn sẽ làm mất dữ liệu.

### Bài 6 — Trường hợp khóa ghép

Hai tenant đều có khách ID `C-01`. Vì sao Map theo `customerId` không đủ?

**Đáp án:** Khóa không xác định duy nhất khách hàng toàn hệ thống. Dùng khóa ghép `(tenantId, customerId)`, ví dụ record `CustomerKey`, và xây/tra cứu cùng một kiểu khóa ở cả hai phía.

### Bài 7 — Kiểm tra parallel

Một người lập trình xây `HashMap` khách hàng, sau đó gọi `orders.parallelStream().map(order -> index.get(order.customerId()))`. Có bắt buộc đổi Map thành `ConcurrentHashMap` không?

**Đáp án:** Không nếu Map đã được xây xong, được công bố phù hợp và **chỉ được đọc** trong lúc xử lý; các giá trị cũng phải ổn định theo hợp đồng. `ConcurrentHashMap` cần thiết khi có yêu cầu cập nhật đồng thời được thiết kế rõ, không phải chỉ vì nhiều tác vụ cùng đọc.

### Bài 8 — Dữ liệu lớn

Vì sao `orders.stream().map(...).toList()` vẫn có thể gây thiếu bộ nhớ dù lookup Map đã tối ưu?

**Đáp án:** `toList()` giữ toàn bộ phần tử kết quả. Map tối ưu **chi phí tìm khóa**, không thay đổi số kết quả cần lưu. Khi đầu ra rất lớn, cần xử lý theo lô, ghi kết quả theo luồng hoặc chỉ tổng hợp các chỉ số cần thiết.

## 20. Ghi nhớ

- **Nhận diện vòng lặp lồng:** nếu mỗi phần tử của danh sách A lại quét danh sách B để tìm cùng khóa, hãy cân nhắc lập chỉ mục.
- **Tạo Map một lần, tra cứu nhiều lần:** với khóa duy nhất và Map hash phù hợp, chi phí kỳ vọng thường từ O(N × M) xuống O(N + M), đổi lấy O(M) bộ nhớ bổ sung.
- **Chọn đúng ngữ nghĩa join:** inner join bỏ bản ghi không khớp; left join giữ bản ghi bên trái; anti join tìm các bản ghi thiếu quan hệ.
- **Đừng che khóa trùng:** `toMap` hai tham số báo lỗi duplicate key; dùng merge function chỉ khi có chính sách chọn/gộp rõ, hoặc `groupingBy` để giữ nhiều giá trị.
- **Khóa phải đúng và ổn định:** xác định khóa duy nhất, khóa ghép, quy tắc chuẩn hóa, xử lý `null` và tránh key mutable.
- **Thứ tự đầu ra phụ thuộc pipeline:** tra cứu `HashMap` không làm mất encounter order của Stream đơn hàng; nhưng việc duyệt `HashMap.values()` không có thứ tự được cam kết.
- **Đọc Map khác với ghi Map:** một index chỉ đọc có thể được chia sẻ trong pipeline song song; đừng cập nhật `HashMap` dùng chung trong `parallelStream().forEach`.
- **Không giữ toàn bộ kết quả nếu không cần:** số khóa Map, số cặp join và việc gọi `toList()` vẫn có thể chiếm bộ nhớ lớn; với dữ liệu vượt RAM, chuyển sang DB join hoặc xử lý ngoài bộ nhớ.
- **Kiểm thử ngữ nghĩa trước khi tối ưu:** so số lượng kết quả, bản ghi không khớp, khóa trùng, tính đúng số tiền và mới benchmark.

**Ý chính:** Mẫu “**xây chỉ mục một lần rồi tra cứu Map theo khóa**” biến nhiều phép tìm tuyến tính lặp lại thành một pha chuẩn bị và nhiều lần tra cứu hiệu quả. Nhưng tối ưu thực sự chỉ thành công khi **không thay đổi số bản ghi phải giữ, không bỏ dữ liệu thiếu khóa một cách im lặng và không đánh đồng quan hệ một-một với một-nhiều**.
