# Giữ ngữ cảnh dữ liệu khi làm phẳng quan hệ cha con

Trong chương **Lọc và biến đổi phần tử** của **Java Stream API**, `flatMap` giúp chuyển một cấu trúc gồm nhiều đối tượng cha, mỗi cha chứa một tập đối tượng con, thành một luồng phần tử phẳng. Đây là thao tác thường gặp khi xử lý đơn hàng và dòng hàng, phòng ban và nhân viên, bài học và câu hỏi, hoặc một cấu trúc cây nhiều cấp.

Điểm dễ sai là **phần tử con thường không chứa đủ thông tin về cha**. Nếu chỉ lấy các phần tử con bằng `flatMap`, các bước phía sau có thể không còn biết dòng hàng thuộc đơn hàng nào, người nào thuộc phòng ban nào, hoặc bản ghi được tạo từ nhánh nào. Bài này trình bày cách **đính kèm ngữ cảnh cha ngay trong lúc làm phẳng**, chọn cấu trúc dữ liệu đầu ra phù hợp và kiểm soát các tình huống như danh sách con rỗng, lọc dữ liệu, trùng khóa, thứ tự và chi phí xử lý.

## 1. Bài toán: một cha có thể có nhiều con

Giả sử một hệ thống bán hàng lưu danh sách đơn hàng. Mỗi đơn hàng có mã đơn, mã khách hàng và nhiều dòng hàng; mỗi dòng hàng có mã sản phẩm, số lượng và đơn giá.

~~~text
Đơn O-100 (khách C-01)
  ├─ Bút  (PEN): 2 × 10.000
  └─ Sách (BOOK): 1 × 50.000

Đơn O-101 (khách C-02)
  └─ Bút  (PEN): 1 × 12.000

Đơn O-102 (khách C-03)
  └─ (không có dòng hàng)
~~~

Nếu cần xuất bảng các dòng hàng để báo cáo, ta muốn kết quả dạng:

| Mã đơn | Mã khách | Sản phẩm | Số lượng | Thành tiền |
| --- | --- | --- | ---: | ---: |
| O-100 | C-01 | PEN | 2 | 20.000 |
| O-100 | C-01 | BOOK | 1 | 50.000 |
| O-101 | C-02 | PEN | 1 | 12.000 |

Mỗi dòng của bảng là **một phần tử con kèm thông tin cha**. Ba đơn hàng tạo ra ba dòng đầu ra; đơn `O-102` không có dòng hàng nên không xuất hiện. Số lượng dòng đầu ra của thao tác làm phẳng là tổng số con của các cha, không phải số lượng cha.

Đây là điểm khác biệt quan trọng khi chuyển từ dữ liệu phân cấp sang bản ghi phẳng để lọc, nhóm, tính tổng, xuất CSV hoặc truyền qua một API.

## 2. Phân biệt `map` và `flatMap`

Cả `map` và `flatMap` đều là thao tác trung gian (*intermediate operation*) trong pipeline lazy. Tuy nhiên, kiểu kết quả khác nhau:

| Phép biến đổi | Hàm áp dụng cho mỗi cha | Kiểu đầu ra |
| --- | --- | --- |
| `map` | Cha → một giá trị, chẳng hạn một `List<Line>` hoặc `Stream<Line>` | `Stream<List<Line>>` hoặc `Stream<Stream<Line>>`: còn một tầng lồng |
| `flatMap` | Cha → một `Stream<Line>` gồm 0, 1 hoặc nhiều con | `Stream<Line>`: gộp các Stream con thành một luồng phẳng |
| `flatMap` giữ ngữ cảnh | Cha → một `Stream<Row>`, mỗi `Row` chứa thông tin cha và con | `Stream<Row>`: luồng phẳng vẫn biết nguồn gốc từng con |

Minh họa với các kiểu Java đơn giản:

~~~java
// Giả sử orders có kiểu List<Order> và mỗi Order có lines().
Stream<Stream<Line>> nested = orders.stream()
        .map(order -> order.lines().stream());

Stream<Line> flattened = orders.stream()
        .flatMap(order -> order.lines().stream());
~~~

Phiên bản `flattened` chỉ chứa `Line`. Nếu `Line` không tự mang `orderId`, ta đã bỏ mất quan hệ cha–con đối với các bước xử lý tiếp theo.

**Quy tắc thực hành:** Khi phần tử đầu ra cần biết cha của nó, hãy tạo một đối tượng kết quả kết hợp thông tin cha và con **bên trong hàm truyền cho `flatMap`**:

~~~java
orders.stream()
    .flatMap(order -> order.lines().stream()
        .map(line -> /* tạo kết quả từ cả order và line */));
~~~

Biến `order` được giữ trong *lexical scope* của lambda bên ngoài; lambda bên trong sử dụng nó để tạo mỗi bản ghi. Đây là cách giữ ngữ cảnh rõ ràng, không cần tìm ngược cha từ con sau khi đã làm phẳng.

## 3. Ví dụ đầy đủ: từ đơn hàng sang bản ghi có ngữ cảnh

Ví dụ sau dùng **Java 17+** để tận dụng `record` và `Stream.toList()`. Mỗi dòng đầu ra có `orderId`, `customerId`, thông tin sản phẩm và thành tiền.

~~~java
import java.math.BigDecimal;
import java.util.List;

public class OrderFlatteningDemo {

    record Line(String sku, int quantity, BigDecimal unitPrice) {}

    record Order(String id, String customerId, List<Line> lines) {}

    record LineRow(
            String orderId,
            String customerId,
            String sku,
            int quantity,
            BigDecimal amount
    ) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-100", "C-01", List.of(
                        new Line("PEN", 2, new BigDecimal("10000")),
                        new Line("BOOK", 1, new BigDecimal("50000"))
                )),
                new Order("O-101", "C-02", List.of(
                        new Line("PEN", 1, new BigDecimal("12000"))
                )),
                new Order("O-102", "C-03", List.of())
        );

        List<LineRow> rows = orders.stream()
                .flatMap(order -> order.lines().stream()
                        .map(line -> new LineRow(
                                order.id(),
                                order.customerId(),
                                line.sku(),
                                line.quantity(),
                                line.unitPrice().multiply(
                                        BigDecimal.valueOf(line.quantity())
                                )
                        )))
                .toList();

        rows.forEach(System.out::println);
    }
}
~~~

Kết quả:

~~~text
LineRow[orderId=O-100, customerId=C-01, sku=PEN, quantity=2, amount=20000]
LineRow[orderId=O-100, customerId=C-01, sku=BOOK, quantity=1, amount=50000]
LineRow[orderId=O-101, customerId=C-02, sku=PEN, quantity=1, amount=12000]
~~~

Đọc pipeline từ ngoài vào trong:

1. `orders.stream()` tạo Stream các đơn hàng.
2. Với mỗi `order`, `order.lines().stream()` tạo Stream những dòng hàng của đúng đơn đó.
3. `map(line -> new LineRow(...))` tạo **một đối tượng kết quả cho mỗi dòng hàng**, lấy dữ liệu từ cả `order` và `line`.
4. `flatMap` nối các Stream dòng kết quả thành một Stream duy nhất.
5. `toList()` là terminal operation, kích hoạt xử lý và thu kết quả vào danh sách.

Nhờ giữ `orderId` và `customerId` ngay lúc chuyển đổi, phần xử lý sau có thể nhóm theo đơn hàng hoặc khách hàng mà không cần tra cứu ngược một bảng khác. Dùng `BigDecimal` cho tiền giúp tránh các sai lệch làm tròn đặc trưng của số thực nhị phân khi tính toán tài chính.

> **Lưu ý phiên bản:** `record` được hỗ trợ chính thức từ Java 16 và `Stream.toList()` có từ Java 16. Trên Java 8–15, có thể thay các `record` bằng lớp DTO/POJO thông thường và thay `toList()` bằng `collect(Collectors.toList())`. Cách ghép `flatMap` + `map` để giữ ngữ cảnh không thay đổi.

## 4. Ba kiểu biểu diễn ngữ cảnh cha–con

Có nhiều cách thiết kế bản ghi đầu ra. Cách chọn tùy thuộc vào việc downstream thực sự cần sử dụng thông tin nào.

### 4.1. Sao chép các trường cần thiết vào một DTO phẳng

Như `LineRow` trong ví dụ trên:

~~~java
record LineRow(
        String orderId,
        String customerId,
        String sku,
        int quantity,
        BigDecimal amount
) {}
~~~

**Phù hợp khi** xuất báo cáo, gửi qua API, lưu snapshot hoặc chuyển dữ liệu giữa các tầng hệ thống. DTO thể hiện rõ hợp đồng dữ liệu và tránh việc phần xử lý sau phải biết mô hình đối tượng cha.

Ưu điểm là dễ kiểm soát trường nào được phép đưa ra ngoài; đổi lại, một số giá trị cha có thể được lặp lại trên nhiều bản ghi con. Nếu DTO chứa thông tin được tính toán, cần xác định thời điểm snapshot và tính nhất quán khi nguồn thay đổi.

### 4.2. Giữ tham chiếu cha và con trong một đối tượng

Khi đang xử lý nội bộ và cần nhiều thuộc tính của cả hai đối tượng, có thể giữ nguyên tham chiếu:

~~~java
record LineWithOrder(Order order, Line line) {}

List<LineWithOrder> pairs = orders.stream()
        .flatMap(order -> order.lines().stream()
                .map(line -> new LineWithOrder(order, line)))
        .toList();

// Ở bước sau vẫn truy cập được cả cha và con:
pairs.forEach(pair -> System.out.println(
        pair.order().id() + ": " + pair.line().sku()
));
~~~

Cách này tránh sao chép nhiều trường và thuận tiện khi logic nghiệp vụ còn cần đối tượng cha. Tuy nhiên, bản ghi kết quả **giữ tham chiếu đến toàn bộ cha**, có thể kéo theo đồ thị đối tượng lớn hơn, trạng thái có thể thay đổi và cả dữ liệu không cần thiết. Nếu `Order` là entity gắn với ORM, việc truyền entity ra khỏi phạm vi transaction còn có thể gây lỗi lazy loading hoặc làm rò rỉ chi tiết của tầng persistence.

### 4.3. Dùng cặp khóa–giá trị cho thao tác ngắn

Có thể sử dụng `Map.entry` (Java 9+):

~~~java
var pairs = orders.stream()
        .flatMap(order -> order.lines().stream()
                .map(line -> java.util.Map.entry(order.id(), line)))
        .toList();
~~~

Ở đây mỗi phần tử là `Map.Entry<String, Line>`; `getKey()` là mã đơn hàng, còn `getValue()` là dòng hàng. Đây chỉ là **cặp giá trị**, không phải một `Map` duy nhất. `Map.entry` không chấp nhận khóa hoặc giá trị `null`.

Cặp giá trị phù hợp với pipeline ngắn, ít trường; khi ngữ cảnh có nhiều thuộc tính hoặc cần tên trường rõ ràng, `record` hoặc DTO chuyên biệt thường dễ đọc và dễ bảo trì hơn.

## 5. Đặt `filter` đúng nơi để giữ ý nghĩa nghiệp vụ

Trong pipeline quan hệ cha–con, ta có thể lọc **cha**, lọc **con**, hoặc lọc theo điều kiện kết hợp cả hai:

~~~java
// Dựa trên ví dụ OrderFlatteningDemo ở trên:
List<LineRow> selected = orders.stream()
        .filter(order -> order.customerId().equals("C-01"))
        .flatMap(order -> order.lines().stream()
                .filter(line -> line.quantity() >= 2)
                .map(line -> new LineRow(
                        order.id(),
                        order.customerId(),
                        line.sku(),
                        line.quantity(),
                        line.unitPrice().multiply(
                                BigDecimal.valueOf(line.quantity())
                        )
                )))
        .toList();
~~~

Pipeline này chỉ duyệt dòng hàng của khách `C-01` và chỉ giữ dòng có số lượng ít nhất 2. Kết quả là dòng `PEN` thuộc đơn `O-100`.

Một số nguyên tắc khi đặt bộ lọc:

- **Lọc cha trước `flatMap`** nếu không cần xử lý bất kỳ con nào của cha không đạt điều kiện. Điều này giúp tránh tạo Stream con và DTO không cần thiết.
- **Lọc con trước `map` thành DTO** nếu điều kiện chỉ dựa trên dữ liệu con, như số lượng hoặc mã sản phẩm. Như vậy không phải tạo những DTO sau đó bị loại.
- **Lọc sau khi tạo DTO** khi điều kiện thực sự cần dữ liệu được tổng hợp từ cả cha và con hoặc kết quả tính toán của DTO.
- **Thứ tự không phải lúc nào cũng hoán đổi được**: lọc theo số lượng dòng hàng của một cha trước khi làm phẳng khác với lọc từng dòng hàng rồi đếm.

Lưu ý khi sử dụng `filter` với lambda có side effect: Stream API có thể tối ưu cách thực thi, đặc biệt trong một số terminal operation; không nên dùng side effect để lưu lại quan hệ cha–con. Hãy đưa ngữ cảnh vào chính giá trị đầu ra của `map`.

## 6. Cha không có con: điểm khác biệt giữa làm phẳng và giữ đủ danh sách cha

`flatMap` tạo **0 phần tử** khi hàm ánh xạ trả về Stream rỗng. Đó là lý do đơn `O-102` không xuất hiện trong bảng `LineRow`.

~~~java
List<LineRow> rows = orders.stream()
        .flatMap(order -> order.lines().stream()
                .map(line -> new LineRow(
                        order.id(),
                        order.customerId(),
                        line.sku(),
                        line.quantity(),
                        line.unitPrice().multiply(
                                BigDecimal.valueOf(line.quantity())
                        )
                )))
        .toList();

// rows không chứa bản ghi cho O-102.
~~~

Nếu nhiệm vụ là **một dòng báo cáo cho mỗi con**, hành vi này là đúng. Nếu yêu cầu là **một dòng cho mỗi cha, kể cả cha không có con**, không nên trông chờ `flatMap` tự tạo ra dòng cha rỗng.

Chẳng hạn, tính tổng tiền theo **từng đơn**, gồm cả đơn rỗng:

~~~java
import java.math.BigDecimal;
import java.util.List;

record OrderTotal(String orderId, BigDecimal amount) {}

List<OrderTotal> totals = orders.stream()
        .map(order -> new OrderTotal(
                order.id(),
                order.lines().stream()
                        .map(line -> line.unitPrice().multiply(
                                BigDecimal.valueOf(line.quantity())
                        ))
                        .reduce(BigDecimal.ZERO, BigDecimal::add)
        ))
        .toList();
~~~

Kết quả của `totals` bao gồm `O-100 = 70000`, `O-101 = 12000` và **`O-102 = 0`**. Ở đây `map` tạo đúng một `OrderTotal` cho mỗi đơn hàng; phép `reduce` bên trong trả về giá trị khởi tạo bằng 0 khi không có dòng hàng.

Nếu cần kết quả dạng mỗi cha xuất hiện ít nhất một lần như **left outer join** trong SQL, phải thiết kế biểu diễn riêng cho trường hợp không có con, ví dụ một dòng với `Optional<Line>` rỗng. Không nên tạo một `Line` giả với mã sản phẩm bất kỳ: dữ liệu giả dễ bị tính nhầm như một dòng hàng thực.

## 7. Từ danh sách phẳng trở lại nhóm theo cha

Một lợi ích của việc giữ mã cha trong mỗi DTO là có thể tính toán tiếp bằng các collector của Java Stream API.

Giả sử ta đang có `rows` kiểu `List<LineRow>` của ví dụ ban đầu:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> amountByOrder = rows.stream()
        .collect(Collectors.groupingBy(
                LineRow::orderId,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        LineRow::amount,
                        BigDecimal::add
                )
        ));

System.out.println(amountByOrder.get("O-100")); // 70000
System.out.println(amountByOrder.get("O-101")); // 12000
~~~

`groupingBy` nhóm các dòng theo `orderId` và `reducing` cộng thành tiền của từng dòng. Đây là quá trình **nhóm lại theo khóa** của dữ liệu đã làm phẳng; nó không khôi phục toàn bộ cấu trúc ban đầu nếu ta đã bỏ các trường khác.

Có hai giới hạn cần nhớ:

1. **Cha không có con không xuất hiện trong `rows`**, vì vậy `groupingBy` trên `rows` cũng không tự sinh khóa `O-102`. Nếu cần kết quả cho toàn bộ đơn, hãy tổng hợp trên danh sách `orders` như ví dụ `OrderTotal` hoặc bổ sung khóa rỗng một cách có chủ đích.
2. **Khóa phải nhận diện đúng cha.** Nếu `orderId` chỉ duy nhất trong phạm vi một cửa hàng hoặc tenant, nhóm riêng theo `orderId` có thể vô tình trộn dữ liệu. Hãy dùng khóa tổng hợp như `(tenantId, orderId)` khi nghiệp vụ yêu cầu.

Tương tự, có thể nhóm theo khách hàng hoặc sản phẩm nếu DTO đã chứa các trường tương ứng. Dùng `Collectors.groupingByConcurrent` để tối ưu song song chỉ phù hợp khi các ràng buộc về thứ tự, collector và khóa của bài toán được đáp ứng; bản thân việc nhóm dữ liệu không cho phép bỏ qua tính đúng đắn của khóa.

## 8. Làm phẳng nhiều tầng mà vẫn giữ đủ đường dẫn

Với dữ liệu có nhiều tầng, ví dụ công ty → phòng ban → nhân viên, cần quyết định phần dữ liệu tổ tiên nào vẫn có ích sau mỗi lần làm phẳng.

~~~text
Company
  └─ Department
       └─ Employee
~~~

Có thể lồng `flatMap` và dùng các biến cha ở phạm vi lambda bên ngoài:

~~~java
// Giả sử có Company::departments, Department::employees
// và các đối tượng đều có phương thức id().
record EmployeeRow(
        String companyId,
        String departmentId,
        String employeeId
) {}

List<EmployeeRow> people = companies.stream()
        .flatMap(company -> company.departments().stream()
                .flatMap(department -> department.employees().stream()
                        .map(employee -> new EmployeeRow(
                                company.id(),
                                department.id(),
                                employee.id()
                        ))))
        .toList();
~~~

Tại thời điểm tạo `EmployeeRow`, cả ba biến `company`, `department` và `employee` đều nằm trong phạm vi lambda nên ta giữ được đường dẫn đầy đủ. Tương tự, với đơn hàng → dòng hàng → thuộc tính bổ sung, có thể mang theo mã đơn, mã dòng và khóa của thuộc tính.

Mỗi tầng `flatMap` có thể làm mất cha không có con ở tầng tiếp theo. Đối với báo cáo cần thống kê đầy đủ tất cả cấp, nên cân nhắc giữ cấu trúc phân cấp hoặc tạo bảng kết quả với quy tắc rõ ràng cho nhánh rỗng.

## 9. Thứ tự, số lượng và danh tính phần tử đầu ra

Một số bất biến giúp kiểm tra kết quả làm phẳng:

**Số lượng.** Nếu không lọc, không bỏ phần tử và danh sách con không chứa `null`, tổng số dòng bằng:

~~~text
totalRows = sum(order.lines().size() for each order)
~~~

Với ví dụ đầu bài: `2 + 1 + 0 = 3`. Nếu thêm `filter`, số dòng chỉ bằng số phần tử con thỏa các điều kiện đã chọn.

**Thứ tự.** Với `List` là nguồn có encounter order, pipeline tuần tự gồm `flatMap` và `map` giữ thứ tự cha, đồng thời giữ thứ tự con trong mỗi cha. Nếu dùng nguồn không có thứ tự hoặc gọi `unordered()`, không nên phụ thuộc vào thứ tự đầu ra. Khi xử lý song song, `forEach` không bảo đảm thứ tự quan sát, còn các terminal operation có hợp đồng giữ encounter order như `toList()` vẫn có thể tạo danh sách theo thứ tự nguồn khi luồng có thứ tự.

**Danh tính.** Hai đơn có thể cùng sản phẩm `PEN`. Chỉ giữ `sku` không đủ để phân biệt hai dòng khác nhau. Nên giữ `orderId` và, nếu cần phân biệt nhiều dòng cùng `sku` trong một đơn, cần thêm `lineId` hoặc định danh ổn định của dòng hàng.

**Tính nhất quán.** Bản ghi DTO sao chép trường của cha tại thời điểm pipeline được thực thi; nếu cha và các danh sách con bị sửa đồng thời, kết quả có thể không nhất quán hoặc phát sinh lỗi như `ConcurrentModificationException`. Cần có snapshot hoặc cách kiểm soát đồng thời thích hợp thay vì sửa collection nguồn trong khi Stream đang duyệt.

## 10. Danh sách con `null`, phần tử con `null` và hợp đồng dữ liệu

Với mô hình Java tự thiết kế, nên thống nhất: **không có con được biểu diễn bằng danh sách rỗng**, thay vì `null`. Điều này giúp `order.lines().stream()` chạy an toàn.

Nếu dữ liệu cũ có thể trả về `null` cho toàn bộ danh sách con, hãy xử lý rõ ràng ngay tại biên:

~~~java
record LineWithOrder(Order order, Line line) {}

List<LineWithOrder> safeRows = orders.stream()
        .flatMap(order -> {
            List<Line> lines = order.lines();
            return (lines == null
                    ? java.util.stream.Stream.<Line>empty()
                    : lines.stream())
                    .map(line -> new LineWithOrder(order, line));
        })
        .toList();
~~~

Điều này quy ước `null` danh sách con là **không có dòng hàng**. Chỉ áp dụng khi hợp đồng dữ liệu thực sự cho phép cách hiểu đó. Nếu `null` là dấu hiệu dữ liệu hỏng, có thể thích hợp hơn khi kiểm tra và ném lỗi có thông tin cụ thể.

Nếu **bản thân một phần tử trong danh sách con là `null`**, việc gọi `line.sku()` sẽ lỗi. Không nên âm thầm thêm `filter(Objects::nonNull)` nếu việc mất dòng dữ liệu khiến báo cáo sai; hãy quyết định có loại bỏ, ghi nhận lỗi hay từ chối đầu vào theo yêu cầu nghiệp vụ.

Các record trong ví dụ là container dữ liệu gọn, nhưng mặc định chúng **không tự xác minh** giá trị hợp lệ. Đặc biệt, record chứa `List<Line>` không làm danh sách bên trong trở nên bất biến nếu caller truyền một danh sách mutable. Có thể dùng `List.copyOf(lines)` và kiểm tra dữ liệu trong constructor khi cần duy trì bất biến mạnh hơn.

## 11. Tối ưu và khả năng mở rộng

### 11.1. Luồng xử lý lazy nhưng terminal operation quyết định vật hóa

`flatMap` và `map` là các thao tác trung gian, nên không thu toàn bộ dòng kết quả ngay khi khai báo. Pipeline sẽ xử lý phần tử khi có terminal operation như `toList()`, `collect()`, `count()`, `reduce()` hoặc `forEach()`.

~~~java
long rowsCount = orders.stream()
        .flatMap(order -> order.lines().stream())
        .count();
~~~

Cách này đếm các dòng con mà không yêu cầu tạo danh sách DTO để lưu lại, dù JDK có thể tận dụng tối ưu hóa thích hợp với nguồn và pipeline. Nếu đích cuối chỉ là tổng hợp, cân nhắc collector hoặc phép toán trực tiếp thay vì `toList()` rồi lại duyệt kết quả.

Với nguồn dữ liệu rất lớn, `toList()` sẽ giữ toàn bộ các dòng đầu ra trong bộ nhớ. Dùng một pipeline có terminal operation phù hợp hoặc xử lý theo từng lô giúp giới hạn dung lượng kết quả đang nắm giữ.

### 11.2. Giữ lambda không có trạng thái chia sẻ

Một cạm bẫy là sử dụng biến ngoài có thể thay đổi để “nhớ” cha hiện tại:

~~~java
// Cách làm không an toàn, đặc biệt khi xử lý song song:
Order[] current = new Order[1];

orders.stream()
        .peek(order -> current[0] = order)
        .flatMap(order -> order.lines().stream())
        .map(line -> current[0].id() + ":" + line.sku())
        .toList();
~~~

Trong một số cách thực thi pipeline, đặc biệt song song, `current[0]` có thể bị cập nhật bởi thao tác với cha khác; hơn nữa side effect trong `peek` không phải cơ chế đáng tin cậy để lưu ngữ cảnh. Hãy thay bằng lambda lồng nhau, tạo DTO dựa trên **chính `order` của lượt hiện tại**.

Hàm thuần hoặc ít side effect cũng giúp việc xử lý song song và kiểm thử dễ dự đoán hơn.

### 11.3. `mapMulti` là một lựa chọn khi phù hợp (Java 16+)

`mapMulti` cho phép một phần tử đầu vào phát ra 0, 1 hoặc nhiều phần tử đầu ra thông qua một consumer, không cần tạo `Stream` con trong mỗi lần ánh xạ:

~~~java
record LineWithOrder(Order order, Line line) {}

List<LineWithOrder> rows = orders.stream()
        .<LineWithOrder>mapMulti((order, sink) -> {
            for (Line line : order.lines()) {
                sink.accept(new LineWithOrder(order, line));
            }
        })
        .toList();
~~~

`mapMulti` cũng giữ ngữ cảnh bằng cách đưa `order` vào mỗi phần tử kết quả. Dạng này có thể giảm chi phí tạo các Stream con trong một số trường hợp, nhưng `flatMap` thường dễ đọc hơn khi thao tác tự nhiên được biểu diễn bằng `stream()`. Hãy ưu tiên cách diễn đạt rõ ràng và chỉ tối ưu theo phép đo thực tế.

### 11.4. Quan hệ từ cơ sở dữ liệu và tài nguyên

Với JPA/Hibernate hoặc ORM tương tự, gọi `order.lines()` có thể kích hoạt truy vấn tải danh sách con. Duyệt rất nhiều đơn hàng có thể gây hiện tượng **N+1 query** hoặc lỗi truy cập lazy association ngoài transaction. Việc dùng `flatMap` không tự tối ưu truy vấn cơ sở dữ liệu.

Nếu cần làm phẳng lượng dữ liệu lớn, có thể xem xét query projection hoặc join tại database, fetch strategy/batch phù hợp và xử lý theo trang. Cần kiểm tra số lượng bản ghi trùng do join, khóa kết hợp và hành vi khi cha không có con. Tránh kéo cả đồ thị entity vào bộ nhớ chỉ để xuất vài trường.

Nếu Stream được tạo từ nguồn có tài nguyên như `Files.lines`, hãy tuân thủ vòng đời đóng tài nguyên bằng `try-with-resources`. Bản thân collection `List` thông thường không cần đóng. Dù `flatMap` có hợp đồng đóng Stream do mapper trả về khi đã xử lý, không nên dùng điều này để thay thế việc quản lý rõ ràng vòng đời nguồn I/O ở tầng tạo nguồn.

## 12. Các lỗi thường gặp và hướng sửa

| Dấu hiệu | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Không xác định được đơn hàng của một dòng con | `flatMap` trả trực tiếp `Line`, bỏ thông tin cha | Tạo `LineRow` hoặc `LineWithOrder` ngay bên trong lambda của `flatMap`. |
| Đơn rỗng biến mất khỏi báo cáo | `flatMap` trên danh sách rỗng tạo 0 dòng | Nếu cần giữ mọi đơn, tổng hợp từ Stream các cha hoặc định nghĩa biểu diễn cho cha không có con. |
| Hai dòng bị gộp thành một khi nhóm hoặc đưa vào Map | Khóa nhóm chỉ dùng `sku` hoặc `orderId` không đủ duy nhất | Xác định khóa nghiệp vụ, có thể cần `tenantId`, `orderId` và `lineId`. |
| Thứ tự thay đổi bất ngờ | Nguồn unordered hoặc terminal `forEach` trên Stream song song | Giữ encounter order theo hợp đồng của nguồn/terminal hoặc sắp xếp đầu ra bằng khóa rõ ràng. |
| Lỗi `NullPointerException` | `lines` hoặc phần tử con `null` | Chuẩn hóa collection rỗng; xác thực dữ liệu và xử lý `null` có chủ đích. |
| Bộ nhớ tăng mạnh | Tạo quá nhiều DTO hoặc giữ cả parent entity; materialize toàn bộ bằng `toList()` | Chỉ mang các trường cần thiết, tổng hợp trực tiếp, xử lý theo lô. |
| Kết quả sai khi chạy song song | Lưu cha hiện tại trong biến mutable bên ngoài | Đưa cha vào lambda lồng và tạo kết quả độc lập cho từng con. |
| Có nhiều truy vấn SQL bất ngờ | `order.lines()` tải association lazy cho từng đơn | Kiểm tra chiến lược truy vấn, projection và batch ở tầng persistence. |

## 13. Bài tập tự kiểm tra

### Bài 1. Nhận diện điểm làm mất ngữ cảnh

~~~java
List<Line> lines = orders.stream()
        .flatMap(order -> order.lines().stream())
        .toList();
~~~

**Câu hỏi:** Vì sao không thể chắc chắn suy ra `orderId` từ từng `Line` trong kết quả?

**Đáp án:** Vì kiểu `Line` trong mô hình không chứa `orderId`. Sau khi làm phẳng, không còn liên kết tường minh từ dòng con tới đối tượng `Order`. Cần tạo `LineRow(order.id(), ...)` hoặc `LineWithOrder(order, line)` khi biến `order` vẫn nằm trong scope lambda.

### Bài 2. Chọn `map` hay `flatMap`

**Yêu cầu:** Tạo một báo cáo gồm **một dòng tổng tiền cho mỗi đơn**, kể cả đơn không có dòng hàng.

**Đáp án:** Dùng `orders.stream().map(order -> new OrderTotal(...))`, và dùng `reduce(BigDecimal.ZERO, BigDecimal::add)` trên các dòng hàng của chính đơn đó. Nếu làm phẳng trước rồi nhóm lại, cần thêm bước bổ sung các đơn không có dòng hàng.

### Bài 3. Đếm số dòng và nhận diện khách hàng

Cho dữ liệu:

~~~text
O-1 / C-A: [PEN, BOOK]
O-2 / C-B: []
O-3 / C-A: [PEN]
~~~

**Câu hỏi:** `flatMap` giữ mã cha tạo mấy dòng? Nhóm theo khách `C-A` có mấy dòng?

**Đáp án:** Tổng cộng **3 dòng**: hai từ `O-1` và một từ `O-3`; khách `C-A` có **3 dòng**. Đơn `O-2` không tạo dòng, vì danh sách con rỗng.

### Bài 4. Thay thế biến trạng thái chia sẻ

**Yêu cầu:** Cần xuất `(departmentId, employeeId)` từ nhiều phòng ban trong pipeline chạy song song. Có nên dùng một biến `currentDepartmentId` bên ngoài rồi cập nhật khi duyệt từng phòng ban không?

**Đáp án:** Không. Biến ngoài có thể bị nhiều tác vụ cập nhật khiến mã phòng ban gắn sai nhân viên. Dùng:

~~~java
record EmployeeRef(String departmentId, String employeeId) {}

List<EmployeeRef> refs = departments.parallelStream()
        .flatMap(department -> department.employees().stream()
                .map(employee -> new EmployeeRef(
                        department.id(),
                        employee.id()
                )))
        .toList();
~~~

Dữ liệu ngữ cảnh được lấy trực tiếp từ biến `department` của đúng lượt ánh xạ, không dựa vào trạng thái dùng chung.

## 14. Ghi nhớ và áp dụng

- **Giữ ngữ cảnh ngay lúc làm phẳng:** `flatMap(parent -> children.stream().map(child -> result(parent, child)))` là mẫu cốt lõi.
- **Chọn cấu trúc đầu ra theo mục đích:** DTO phẳng cho báo cáo/API; cặp cha–con khi cần xử lý nội bộ; khóa tổng hợp khi cần nhóm hoặc nhận diện duy nhất.
- **Hiểu số lượng phần tử:** làm phẳng ra 0..N kết quả cho mỗi cha; cha rỗng biến mất trừ khi ứng dụng định nghĩa cách giữ lại.
- **Lọc và tổng hợp đúng cấp:** lọc cha trước `flatMap` khi có thể; dùng `map` trên cha nếu yêu cầu mỗi cha có một bản ghi kể cả không có con.
- **Tôn trọng hợp đồng pipeline:** lambda nên tránh trạng thái dùng chung; cân nhắc encounter order, null, chi phí vật hóa dữ liệu và cách nguồn dữ liệu được tải.

**Ý chính:** `flatMap` giải quyết việc *gộp* dữ liệu con vào một Stream, còn **định danh, ngữ cảnh và ý nghĩa nghiệp vụ của mối quan hệ cha–con** phải được thể hiện trong phần tử kết quả do bạn thiết kế. Khi giữ đủ ngữ cảnh từ đầu, các bước `filter`, `collect`, `groupingBy`, xử lý song song và xuất dữ liệu về sau sẽ rõ ràng, dễ kiểm chứng và ít gây nhầm lẫn hơn.
