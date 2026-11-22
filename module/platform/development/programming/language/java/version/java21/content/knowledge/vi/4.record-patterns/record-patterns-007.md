# Record pattern lồng nhau để duyệt cấu trúc dữ liệu nhiều tầng

Record pattern cho phép kiểm tra một giá trị có thuộc kiểu record mong muốn hay không, đồng thời lấy các thành phần của record vào biến ngay tại điểm kiểm tra. Khi một component cũng là record, ta có thể đặt một record pattern khác bên trong để phân rã nhiều tầng dữ liệu trong cùng một biểu thức.

Trong `JAVA_VERSION_JAVA21` (Java 21), Record Patterns đã là tính năng ổn định từ JEP 440. Chúng đặc biệt hữu ích khi mô hình nghiệp vụ được biểu diễn bằng các record lồng nhau, chẳng hạn sự kiện chứa đơn hàng, đơn hàng chứa khách hàng và khách hàng chứa địa chỉ. Mục tiêu là làm rõ cấu trúc đang xử lý, giảm các chuỗi gọi accessor và kiểm tra kiểu rời rạc.

## Mô hình dữ liệu nhiều tầng

Giả sử hệ thống nhận một sự kiện đơn hàng. Dữ liệu được chia thành các record nhỏ, mỗi record chịu trách nhiệm biểu diễn một khái niệm:

```java
import java.math.BigDecimal;
import java.time.Instant;

record Address(String city, String district) {}

record Customer(String name, Address address) {}

record Order(String code, Customer customer, BigDecimal total) {}

record OrderEvent(Order order, Instant occurredAt) {}
```

Các phương thức minh họa tiếp theo được đặt trong một class ứng dụng và sử dụng những record đã khai báo ở trên.

Quan hệ giữa các record có thể hình dung như sau:

```text
OrderEvent
├── order: Order
│   ├── code: String
│   ├── customer: Customer
│   │   ├── name: String
│   │   └── address: Address
│   │       ├── city: String
│   │       └── district: String
│   └── total: BigDecimal
└── occurredAt: Instant
```

Nếu chỉ dùng accessor, mã lấy thành phố của khách hàng sẽ đi qua nhiều cấp:

```java
static String cityOf(OrderEvent event) {
    return event.order().customer().address().city();
}
```

Cách này hoàn toàn hợp lệ và phù hợp khi chỉ cần một hoặc hai giá trị. Khi cần kiểm tra đồng thời cấu trúc, kiểu và nhiều component, record pattern lồng nhau giúp thể hiện điều kiện trong một mẫu thống nhất.

## Phân rã nhiều tầng bằng một record pattern

Ví dụ sau kiểm tra một giá trị đầu vào có phải `OrderEvent` với đầy đủ cấu trúc con cần dùng hay không:

```java
static String describe(Object value) {
    if (value instanceof OrderEvent(
            Order(
                    String orderCode,
                    Customer(
                            String customerName,
                            Address(String city, String district)),
                    BigDecimal total),
            Instant occurredAt)) {

        return "Đơn " + orderCode
                + " của " + customerName
                + " tại " + district + ", " + city
                + ", tổng tiền " + total
                + ", thời điểm " + occurredAt;
    }

    return "Giá trị không khớp cấu trúc OrderEvent cần xử lý";
}
```

Mẫu bên ngoài `OrderEvent(...)` kiểm tra kiểu record ngoài cùng. Component thứ nhất của nó được kiểm tra bằng `Order(...)`; trong `Order`, component khách hàng tiếp tục được kiểm tra bằng `Customer(...)`; địa chỉ lại được phân rã bằng `Address(...)`. Các biến `orderCode`, `customerName`, `city`, `district`, `total` và `occurredAt` chỉ được dùng trong nhánh mà toàn bộ mẫu đã khớp.

Thứ tự component trong pattern phải tương ứng chính xác với thứ tự khai báo component trong record. `Order` khai báo `code`, `customer`, `total`, vì vậy pattern cũng phải có ba component theo thứ tự đó. Record pattern không tra cứu component theo tên.

## Kết hợp các mức phân rã với var pattern

Khi đã biết kiểu component từ khai báo record, có thể dùng `var` để trình biên dịch suy ra kiểu biến được bind. Điều này làm pattern gọn hơn khi cấu trúc đã rõ:

```java
static void printOrder(Object value) {
    if (value instanceof OrderEvent(
            Order(
                    var orderCode,
                    Customer(var customerName,
                            Address(var city, var district)),
                    var total),
            var occurredAt)) {

        System.out.printf(
                "Đơn %s, khách %s, địa chỉ %s - %s, tổng %s, lúc %s%n",
                orderCode, customerName, district, city, total, occurredAt);
    }
}
```

`var` không có nghĩa là component bị chuyển thành `Object`; kiểu biến được suy ra từ kiểu component đã khai báo. Nếu muốn kiểm tra một component có kiểu cụ thể trước khi bind, có thể viết type pattern như `String city` hoặc `BigDecimal total` như ví dụ trước.

Không bắt buộc phải phân rã đến tận cùng. Có thể chỉ phân rã các cấp cần thiết và bind một record con thành biến để dùng accessor thông thường:

```java
if (value instanceof OrderEvent(
        Order(var orderCode, Customer(var customerName, Address address), var total),
        var occurredAt)) {

    String city = address.city();
    // Xử lý orderCode, customerName, total, occurredAt và city.
}
```

Cách chọn lọc này thường dễ đọc hơn nếu record con có nhiều component nhưng nghiệp vụ chỉ cần một vài giá trị. Hãy phân rã sâu khi việc thể hiện cấu trúc lồng nhau giúp điều kiện rõ hơn; nếu pattern trở nên quá dài, bind một record con rồi tiếp tục xử lý bằng accessor hoặc phương thức riêng.

## Dùng nested record pattern trong switch

Java 21 cũng hoàn thiện Pattern Matching for `switch` (JEP 441). Có thể kết hợp switch với nested record pattern để chọn hành động dựa trên cấu trúc của dữ liệu:

```java
static String route(Object value) {
    return switch (value) {
        case null -> "Không có sự kiện";

        case OrderEvent(
                Order(
                        String orderCode,
                        Customer(String customerName,
                                Address(String city, String district)),
                        BigDecimal total),
                Instant occurredAt) ->
                "Xử lý đơn " + orderCode
                        + " của " + customerName
                        + " tại " + district + ", " + city
                        + ", tổng " + total
                        + ", lúc " + occurredAt;

        default -> "Loại dữ liệu sự kiện chưa được hỗ trợ";
    };
}
```

`case null` xử lý riêng đầu vào `null`. Nhánh record pattern xử lý sự kiện có đúng cấu trúc đã mô tả; `default` tiếp nhận giá trị khác kiểu hoặc không khớp nested pattern. Với một hierarchy sealed và các nhánh đã bao phủ hết biến thể, có thể tận dụng kiểm tra tính đầy đủ của switch để phát hiện khi mô hình được mở rộng.

Pattern có thể đi kèm guard `when` nếu ngoài cấu trúc còn cần điều kiện nghiệp vụ. Ví dụ, sau khi đã bind `total`, có thể chỉ chọn nhánh dành cho đơn có tổng tiền dương:

```java
case OrderEvent(
        Order(var orderCode, var customer, BigDecimal total),
        var occurredAt) when total.signum() > 0 ->
        "Đơn hợp lệ về tổng tiền: " + orderCode;
```

Guard chỉ được đánh giá sau khi pattern khớp, vì vậy các biến được bind trong pattern có thể dùng trong điều kiện `when`. Hãy giữ guard ngắn và dễ đọc; điều kiện nghiệp vụ phức tạp nên được tách thành phương thức có tên rõ ràng.

## Pattern không tự duyệt List hoặc Map

Nested record pattern phân rã component của record. Nó không tự lặp qua `List`, `Set`, `Map`, mảng hoặc toàn bộ object graph. Nếu một record chứa collection, pattern có thể bind collection đó; chương trình vẫn phải duyệt collection bằng vòng lặp hoặc Stream API rồi áp dụng pattern cho từng phần tử khi cần.

```java
import java.util.List;

record OrderBatch(List<OrderEvent> events) {}

static void printBatch(Object value) {
    if (value instanceof OrderBatch(var events)) {
        for (Object event : events) {
            if (event instanceof OrderEvent(
                    Order(var code,
                            Customer(var name, Address(var city, var district)),
                            var total),
                    var occurredAt)) {

                System.out.printf("%s - %s - %s, %s - %s - %s%n",
                        code, name, district, city, total, occurredAt);
            }
        }
    }
}
```

Ở đây, pattern `OrderBatch(var events)` chỉ lấy collection `events`. Vòng `for` mới thực hiện việc duyệt từng phần tử; nested pattern trên từng `OrderEvent` mới phân rã cấu trúc record của phần tử đó. Nếu collection có kiểu phần tử cụ thể như `List<OrderEvent>`, có thể dùng kiểu đó trực tiếp trong vòng lặp thay vì `Object` và vẫn giữ record pattern ở nơi cần kiểm tra cấu trúc.

## Khi nào một nested pattern không khớp?

Record pattern chỉ khớp khi giá trị ở vị trí đó là instance của record được nêu và các component con khớp với pattern tương ứng. Một số tình huống thường gặp:

- Giá trị ngoài cùng là `null`: `instanceof` trả về `false`; trong switch, cần `case null` nếu muốn xử lý riêng thay vì để switch ném `NullPointerException`.
- Giá trị có kiểu khác record được yêu cầu: pattern không khớp và nhánh tiếp theo được xét.
- Một component cần khớp với nested record pattern nhưng giá trị component là `null` hoặc thuộc kiểu khác: nested pattern không khớp, nên toàn bộ pattern ngoài cũng không khớp.
- Số lượng hoặc thứ tự component trong pattern không phù hợp khai báo record: mã không biên dịch.

Nếu dữ liệu từ JSON, database hoặc dịch vụ ngoài có thể thiếu component, hãy xác định rõ hợp đồng nullability trước khi dùng nested pattern. Có thể bind component nullable ở một cấp rồi kiểm tra riêng, hoặc xác thực dữ liệu tại ranh giới chuyển đổi sang record. Đừng giả định nested pattern sẽ tự bỏ qua component `null`.

Record pattern lấy dữ liệu thông qua accessor của record. Vì vậy, accessor được viết tường minh nên giữ hành vi đơn giản, ổn định và không có side effect. Việc phân rã dữ liệu nên là thao tác đọc, không nên trở thành nơi kích hoạt truy vấn hoặc thay đổi trạng thái.

## Tránh lạm dụng pattern quá sâu

Nested pattern hữu ích khi cấu trúc dữ liệu có ý nghĩa rõ và độ sâu vừa phải. Một pattern dài với nhiều cấp lồng nhau có thể khiến người đọc khó nhận ra điều kiện quan trọng. Có thể áp dụng các nguyên tắc sau:

| Tình huống | Cách viết nên cân nhắc |
| --- | --- |
| Chỉ cần một vài component ở cấp ngoài | Dùng record pattern ở cấp ngoài và bind record con thành biến |
| Cần nhiều component từ hai hoặc ba cấp record | Dùng nested record pattern để thể hiện cấu trúc trong một chỗ |
| Pattern quá dài hoặc lặp lại ở nhiều nơi | Tách thành phương thức xử lý hoặc hàm chuyển đổi có tên rõ ràng |
| Dữ liệu có thể thiếu hoặc sai cấu trúc | Xác thực tại ranh giới đầu vào và xử lý null rõ ràng |
| Cần duyệt collection hoặc map | Dùng vòng lặp/Stream API, rồi áp dụng record pattern cho từng phần tử |

Không nên thay mọi lời gọi accessor bằng pattern. Nếu chỉ đọc `event.order().total()`, accessor trực tiếp thường đơn giản hơn. Pattern phát huy tác dụng khi việc kiểm tra kiểu và phân rã nhiều component cùng lúc làm cho logic rõ hơn.

## Phân biệt cú pháp ổn định với preview trong Java 21

Record Patterns được hoàn thiện trong Java 21, nên các ví dụ dùng `instanceof`, nested record pattern, `var` component pattern và Pattern Matching for `switch` ở trên không cần bật preview.

Java 21 có Unnamed Patterns and Variables ở trạng thái preview (JEP 443). Vì vậy, không dùng dấu gạch dưới `_` như một unnamed pattern trong mã yêu cầu cú pháp Java 21 ổn định. Nếu cần giữ lại một component nhưng không sử dụng, có thể đặt tên biến có ý nghĩa như `var ignoredTimestamp`; tốt hơn nữa, hãy cân nhắc bind record con thay vì phân rã những component không cần thiết. Nếu chủ động thử preview feature, phải bật `--enable-preview` cho đúng JDK và chấp nhận yêu cầu kiểm soát tương thích riêng.

## Quy trình áp dụng vào mô hình thực tế

1. **Xác định record gốc và các record con.** Kiểm tra thứ tự, kiểu dữ liệu và nullability của từng component trong mô hình.
2. **Liệt kê giá trị cần dùng.** Chỉ phân rã đến cấp cần thiết; giữ nguyên record con nếu phần còn lại có thể lấy bằng accessor.
3. **Chọn điểm kiểm tra.** Dùng `instanceof` khi cần một nhánh điều kiện; dùng `switch` khi có nhiều dạng dữ liệu hoặc nhiều hành động tương ứng.
4. **Xử lý dữ liệu không khớp.** Xác định rõ cách xử lý `null`, sai kiểu, component nullable và dữ liệu đầu vào chưa hợp lệ.
5. **Duyệt collection riêng.** Dùng vòng lặp hoặc Stream API cho cấu trúc tập hợp, rồi áp dụng pattern trên từng record.
6. **Giữ pattern dễ đọc.** Nếu pattern quá sâu hoặc lặp lại, tách phương thức và đặt tên cho thao tác xử lý.
7. **Biên dịch với mục tiêu Java 21.** Dùng JDK 21 hoặc cấu hình `--release 21` phù hợp để bảo đảm mã dựa trên cú pháp đã ổn định của phiên bản này.

Nested record patterns phù hợp khi dữ liệu đã được mô hình hóa thành các record lồng nhau và logic cần kiểm tra nhiều cấp cấu trúc trong cùng một điểm xử lý. Chúng giúp mã thể hiện rõ hình dạng dữ liệu và các giá trị được lấy ra. Hãy kết hợp chúng với accessor, vòng lặp và bước xác thực dữ liệu theo đúng vai trò của từng công cụ.
