# Dispatch command bằng pattern switch – Case study Java 21

Khi một hệ thống nhận nhiều loại **command** (lệnh thay đổi trạng thái), nó cần quyết định lệnh nào được xử lý bởi nghiệp vụ nào. Một cách quen thuộc là viết nhiều `if (command instanceof ...)` và cast về từng lớp. Khi số lệnh tăng, mã điều phối dễ dài, thiếu nhánh, lặp kiểm tra kiểu và trộn logic kiểm tra dữ liệu với logic cập nhật trạng thái.

Trong **Java 21**, có thể thiết kế command như một **`sealed interface`** với các biến thể `record`, rồi dùng **pattern matching for `switch`** để thực hiện **dispatch** (điều phối). Compiler hỗ trợ kiểm tra tính **exhaustive** của `switch expression`: nếu thêm một loại command mới vào hệ phân cấp đóng mà quên xử lý trong dispatcher, quá trình biên dịch có thể phát hiện thiếu case.

Bài học này xây dựng một command dispatcher quản lý đơn hàng trong bộ nhớ với ba loại lệnh: **tạo đơn**, **cộng số lượng** và **hủy đơn**. Các ví dụ dùng Java 21+; `sealed` final từ Java 17, `record` final từ Java 16, còn **record patterns** và **pattern switch** final từ Java 21. Không cần `--enable-preview`.

## 1. Dispatch command là gì?

**Command** diễn đạt một yêu cầu thực hiện hành động, thường làm thay đổi trạng thái hệ thống. Ví dụ:

- `CreateOrder("O-1", 2)`: tạo đơn `O-1` với số lượng ban đầu là 2.
- `AddItems("O-1", 3)`: tăng số lượng của đơn `O-1` thêm 3.
- `CancelOrder("O-1")`: chuyển đơn sang trạng thái đã hủy.

**Dispatcher** là nơi nhận một command, xác định loại của nó rồi gọi đúng nghiệp vụ. Một luồng đơn giản:

```text
            Input / API / message consumer
                         |
                  kiểm tra kiểu
                         |
                      Command
                         |
                 dispatch(Command)
                         |
                 pattern switch
               /       |        \
        CreateOrder  AddItems  CancelOrder
            |          |          |
          create()     add()     cancel()
               \        |        /
                 Kết quả xử lý
                         |
                Response / logging
```

Nên phân biệt ba trách nhiệm:

1. **Transport/adapter** tiếp nhận đầu vào; nó có thể nhận `Object`, JSON, một message từ queue hoặc một request đã deserialize. Bài học không triển khai HTTP hay message broker.
2. **Dispatch** xác định loại command, kiểm tra các điều kiện cơ bản, rồi chọn handler.
3. **Business handler** kiểm tra trạng thái hiện tại và cập nhật dữ liệu theo đúng quy tắc nghiệp vụ.

Việc dùng pattern switch **không tự tạo giao dịch, không bảo đảm exactly-once và không tự đồng bộ đa luồng**. Những yêu cầu này thuộc về thiết kế lưu trữ, xử lý message và transaction.

### Command pattern và pattern switch có phải một thứ?

**Command Pattern** trong mẫu thiết kế GoF thường đóng gói một hành động vào một đối tượng, có thể chứa phương thức `execute()` và tham chiếu receiver. **Pattern switch** là một cấu trúc ngôn ngữ Java để khớp kiểu và cấu trúc dữ liệu.

Một command **không bắt buộc phải có `execute()`**. Trong case study, command chỉ là dữ liệu bất biến, còn hành động nằm trong dispatcher/handler. Đây là lựa chọn kiến trúc hợp lý cho một tập command đóng; nó không phải quy tắc bắt buộc cho mọi hệ thống Command Pattern.

## 2. Mô hình command đóng với sealed interface

Các biến thể của domain:

```java
sealed interface Command permits CreateOrder, AddItems, CancelOrder {}

record CreateOrder(String orderId, int quantity) implements Command {}
record AddItems(String orderId, int delta) implements Command {}
record CancelOrder(String orderId) implements Command {}
```

Đây là **các khai báo minh họa** thuộc cùng lớp trong chương trình hoàn chỉnh ở mục 9.

Ý nghĩa thiết kế:

- `Command` là kiểu cha của mọi lệnh dispatcher hỗ trợ.
- `permits` chỉ rõ ba subtype **được phép triển khai trực tiếp** `Command`.
- Các `record` triển khai `Command` là `final` ngầm định. Chúng giữ đúng dữ liệu cần cho mỗi lệnh và không có setter mặc định.
- `CreateOrder` có `quantity` là số lượng ban đầu; `AddItems` có `delta` là số lượng cần cộng; `CancelOrder` chỉ cần định danh đơn hàng.
- Một class ngoài danh sách `permits` không thể tự ý `implements Command`. Muốn thêm loại lệnh mới, phải thay đổi mô hình có chủ đích.

Vì tất cả subtype được phép đều là record cuối, tập biến thể của `Command` trong ví dụ là **đóng**. Đây là điều kiện thuận lợi để compiler xác định những case nào cần có trong một `switch` trên `Command`.

### Vì sao dùng record để mang command?

Command thường là **thông điệp biểu diễn ý định**: tên thao tác và các tham số. `record` tự cung cấp constructor, accessor như `orderId()`, `quantity()`, `delta()` và các phương thức `equals/hashCode/toString` theo dữ liệu thành phần.

```java
Command cmd = new CreateOrder("O-1", 2);
```

Không phải cast thủ công hoặc tạo cây kế thừa lớn để biểu diễn thông điệp này.

**Giới hạn:** record có tính bất biến nông (*shallow immutability*). Nếu component là một object mutable, trạng thái của object đó vẫn có thể bị thay đổi. Trong demo, các component chỉ gồm `String` và `int` nên đơn giản hơn.

### Command object có thể mang dữ liệu không hợp lệ

```java
new CreateOrder(null, 2);
new CreateOrder(" ", 2);
new CreateOrder("O-1", 0);
```

Những record trên **vẫn có thể được tạo** vì constructor mặc định của chúng chưa đặt điều kiện nghiệp vụ. Bài học cố ý kiểm tra chúng trong dispatcher để minh họa các guard `when`. Trong một hệ thống thực tế, có thể chọn kiểm tra sớm ở constructor hoặc ở lớp request validation; nhưng cần bảo đảm boundary vẫn xử lý đầu vào lỗi và contract phù hợp.

## 3. Record chứa trạng thái đơn hàng

Bên cạnh command, ta cần trạng thái hiện tại:

```java
record Order(String id, int quantity, boolean canceled) {}
```

`Order` **không triển khai `Command`**. Nó là dữ liệu domain, khác với thông điệp yêu cầu hành động.

Hệ thống minh họa lưu đơn hàng trong:

```java
private final Map<String, Order> orders = new LinkedHashMap<>();
```

Khi số lượng hoặc trạng thái thay đổi, code tạo **Order mới** rồi thay giá trị trong map, thay vì sửa component của record. Lựa chọn này giúp mỗi giá trị `Order` đã tạo không bị thay đổi tại chỗ.

Trong ví dụ, map chỉ sống trong bộ nhớ của một instance dispatcher. Nó không có persistence, không chia sẻ qua nhiều process và **không thread-safe** cho các thao tác cập nhật đồng thời. Khi áp dụng thực tế, cần kho dữ liệu, transaction hoặc cơ chế đồng bộ phù hợp.

## 4. Trọng tâm: dispatch bằng pattern switch

Dispatcher nhận `Command` và dùng `switch expression` trả một mã kết quả dạng `String`:

```java
String dispatch(Command command) {
    return switch (command) {
        case null -> "INVALID_COMMAND";

        case CreateOrder(var id, var quantity) when invalidId(id) ->
                "INVALID_ID";
        case CreateOrder(var id, var quantity) when quantity <= 0 ->
                "INVALID_QUANTITY";
        case CreateOrder(var id, var quantity) ->
                create(id, quantity);

        case AddItems(var id, var delta) when invalidId(id) ->
                "INVALID_ID";
        case AddItems(var id, var delta) when delta <= 0 ->
                "INVALID_QUANTITY";
        case AddItems(var id, var delta) ->
                add(id, delta);

        case CancelOrder(var id) when invalidId(id) ->
                "INVALID_ID";
        case CancelOrder(var id) ->
                cancel(id);
    };
}
```

Phương thức này cần các phương thức `invalidId/create/add/cancel` đã có trong chương trình đầy đủ.

### Tại sao case cụ thể có when đứng trước case chung?

Với `CreateOrder`, thứ tự là:

1. `CreateOrder(...) when invalidId(id)`: kiểm tra ID null hoặc toàn khoảng trắng.
2. `CreateOrder(...) when quantity <= 0`: kiểm tra số lượng không dương.
3. `CreateOrder(...)` không guard: chỉ còn trường hợp ID và số lượng đã qua các kiểm tra trước đó.

Khi record pattern khớp, các biến `id` và `quantity` đã được ràng buộc và có thể dùng trong `when`. Guard là điều kiện bổ sung cho case chứ không phải một loại command mới.

Nhánh không có `when` bao phủ **mọi** `CreateOrder` hợp lệ về cấu trúc. Nếu đặt nó lên đầu, các nhánh `CreateOrder` có guard phía sau bị **dominated**; compiler Java từ chối. Tương tự với `AddItems` và `CancelOrder`.

**Bảng thứ tự đúng:**

| Nhóm | Case kiểm tra trước | Case sau cùng của nhóm |
| --- | --- | --- |
| `CreateOrder` | ID không hợp lệ, số lượng không dương | `create(id, quantity)` |
| `AddItems` | ID không hợp lệ, lượng cộng không dương | `add(id, delta)` |
| `CancelOrder` | ID không hợp lệ | `cancel(id)` |

Nếu cả ID và số lượng cùng không hợp lệ, dispatcher ưu tiên trả `INVALID_ID` vì guard đó đứng trước. **Thứ tự case có thể thể hiện thứ tự ưu tiên báo lỗi nghiệp vụ**, không chỉ là chi tiết cú pháp.

### Vì sao dùng var trong record pattern?

Ví dụ `CreateOrder(var id, var quantity)` tách hai component của record:

- `id` có kiểu tĩnh `String`.
- `quantity` có kiểu tĩnh `int`.

`var` không tạo kiểu động. Compiler suy ra kiểu từ khai báo component của record. Quan trọng hơn, component `id` **có thể là null** vì record không cấm giá trị này. Do đó `invalidId(id)` phải xử lý null an toàn.

## 5. Null ở transport và null trong dispatcher

Một tình huống thường gặp: tầng nhận message không có bảo đảm kiểu tĩnh `Command`. Có thể chặn bằng type pattern và guard phủ định:

```java
String route(Object incoming) {
    if (!(incoming instanceof Command command)) {
        return "NOT_A_COMMAND";
    }
    return dispatch(command);
}
```

Đoạn này có hai điểm quan trọng:

1. `incoming instanceof Command command` trả `false` nếu đầu vào là `null` hoặc một object không triển khai `Command`. Sau nhánh phủ định `return`, `command` chắc chắn đã được ràng buộc, nên dùng được tại `dispatch(command)` (**flow scoping**).
2. `dispatch(null)` được xử lý riêng bởi `case null -> "INVALID_COMMAND"`. Vì `route` kiểm tra kiểu trước, `route(null)` trả `NOT_A_COMMAND`, còn gọi trực tiếp `dispatch(null)` trả `INVALID_COMMAND`.

Sự khác biệt này là **chính sách ở hai boundary khác nhau**, không phải lỗi Java. Trong sản phẩm thật, nên thống nhất error model nếu client yêu cầu cùng một thông điệp cho trường hợp null.

### Vì sao case null cần khai báo rõ?

Trong Java 21 pattern switch, một selector `null` không được tự động chuyển sang `default` hoặc các type patterns thông thường. Nếu không có `case null`, một `switch` dùng pattern mà nhận `null` thường ném `NullPointerException`.

`case null` giúp dispatcher trả mã lỗi dự đoán được thay vì ném exception ngoài ý muốn. Nếu hợp đồng yêu cầu từ chối null bằng exception, có thể dùng `Objects.requireNonNull` trước switch; chỉ cần ghi rõ lựa chọn.

### Null ở component khác null ở selector

`new CreateOrder(null, 2)` là một **Command không null**, nên case `CreateOrder(var id, var quantity)` vẫn có thể khớp và `id == null`. Case `null` không bắt tình huống này. Bởi vậy cần guard `invalidId(id)` cho component.

Một kiểm tra ID an toàn:

```java
private static boolean invalidId(String id) {
    return id == null || id.isBlank();
}
```

Toán tử `||` đánh giá ngắn mạch; khi `id == null` đúng, `id.isBlank()` không được gọi. Đảo thành `id.isBlank() || id == null` có thể gây `NullPointerException`.

## 6. Điều phối khác với xử lý nghiệp vụ

Sau khi xác định loại command và dữ liệu cơ bản hợp lệ, dispatcher gọi các phương thức xử lý nhỏ.

### CreateOrder: tạo mới có kiểm tra trùng

```java
private String create(String id, int quantity) {
    if (orders.containsKey(id)) {
        return "ALREADY_EXISTS";
    }
    orders.put(id, new Order(id, quantity, false));
    return "CREATED " + id + " qty=" + quantity;
}
```

`CreateOrder("O-1",2)` tạo đơn có số lượng 2, chưa hủy. Lần gọi lặp `CreateOrder("O-1",3)` trả `ALREADY_EXISTS` và **không** thay đơn cũ.

Đây là quy tắc chống tạo trùng đơn giản trong bộ nhớ. Nó **không** tương đương cơ chế idempotency hoàn chỉnh khi xử lý retry qua mạng hoặc nhiều replica; xem mục 12.

### AddItems: kiểm tra tồn tại, trạng thái và overflow

```java
private String add(String id, int delta) {
    Order previous = orders.get(id);
    if (previous == null) {
        return "NOT_FOUND";
    }
    if (previous.canceled()) {
        return "ORDER_CANCELED";
    }

    final int newQuantity;
    try {
        newQuantity = Math.addExact(previous.quantity(), delta);
    } catch (ArithmeticException overflow) {
        return "QUANTITY_OVERFLOW";
    }

    orders.put(id, new Order(id, newQuantity, false));
    return "UPDATED " + id + " qty=" + newQuantity;
}
```

Mọi command `AddItems` đã qua guard `delta > 0` trong dispatcher. Handler vẫn cần kiểm tra **trạng thái hiện có**: không được cộng vào đơn không tồn tại hoặc đã hủy.

`Math.addExact` phát hiện tràn `int`. Nếu `Integer.MAX_VALUE + 1` được thực hiện bằng phép cộng `int` thông thường, Java sẽ wrap thành số âm; trong domain số lượng đơn, kết quả đó không hợp lệ. Handler bắt đúng `ArithmeticException` từ phép cộng và trả `QUANTITY_OVERFLOW`; **map không bị cập nhật** khi overflow.

### CancelOrder: xử lý lệnh lặp

```java
private String cancel(String id) {
    Order previous = orders.get(id);
    if (previous == null) {
        return "NOT_FOUND";
    }
    if (previous.canceled()) {
        return "ALREADY_CANCELED";
    }
    orders.put(id, new Order(id, previous.quantity(), true));
    return "CANCELED " + id;
}
```

Hủy đơn đã hủy lần nữa trả `ALREADY_CANCELED`, không làm thay đổi số lượng hay trạng thái.

**Cần phân biệt:** kết quả trả lần đầu `CANCELED` và lần thứ hai `ALREADY_CANCELED` khác nhau, dù **hiệu ứng trạng thái** của việc thực hiện lại không thay đổi. Một API đòi hỏi *cùng response* cho lệnh retry có thể cần lưu kết quả theo command ID để phát lại đúng response ban đầu.

## 7. Query nên tách khỏi tập command thay đổi trạng thái

Dispatcher trong bài chỉ hỗ trợ **ba loại lệnh ghi**. Để kiểm tra kết quả, ta dùng một phương thức đọc riêng:

```java
String snapshot(String id) {
    if (invalidId(id)) {
        return "INVALID_ID";
    }
    Order order = orders.get(id);
    if (order == null) {
        return "NOT_FOUND";
    }
    return "ORDER " + order.id()
            + " qty=" + order.quantity()
            + " status=" + (order.canceled() ? "CANCELED" : "ACTIVE");
}
```

Đây là **truy vấn trạng thái**, không phải command làm thay đổi trạng thái. Việc đặt `snapshot` ngoài `Command` giúp phân biệt rõ **write model** với **read/query operation**.

Trong hệ thống áp dụng CQRS, command và query có thể đi qua hai handler/dispatcher khác nhau hoặc mô hình đọc khác nhau. Case study này chỉ minh họa sự tách biệt căn bản, không triển khai toàn bộ kiến trúc CQRS hay event sourcing.

## 8. Luồng xử lý và kết quả kỳ vọng

Sau khi tạo một instance dispatcher mới, một kịch bản thông thường:

| Lần gọi | Kết quả | Trạng thái sau lệnh |
| --- | --- | --- |
| `CreateOrder("O-1",2)` | `CREATED O-1 qty=2` | O-1 active, quantity 2 |
| `CreateOrder("O-1",3)` | `ALREADY_EXISTS` | Vẫn quantity 2 |
| `AddItems("O-1",3)` | `UPDATED O-1 qty=5` | O-1 active, quantity 5 |
| `CancelOrder("O-1")` | `CANCELED O-1` | O-1 canceled, quantity 5 |
| `CancelOrder("O-1")` lần hai | `ALREADY_CANCELED` | Không thay đổi |
| `AddItems("O-1",1)` | `ORDER_CANCELED` | Không thay đổi |

Bộ kiểm thử cũng bao gồm:

- `null` ở tầng transport và `null` ở đầu vào dispatcher.
- Command có `orderId == null` hoặc chỉ chứa khoảng trắng.
- Số lượng bằng 0, lượng cộng âm.
- Cộng vào đơn chưa tồn tại, hủy đơn chưa tồn tại.
- Tạo một đơn `MAX` với `Integer.MAX_VALUE`, sau đó cộng thêm 1 và kiểm tra **không bị thay đổi trạng thái** do overflow.

Các trường hợp này có giá trị hơn chỉ gọi một happy path, vì chúng xác nhận **thứ tự guard**, **ràng buộc trạng thái**, **hành vi retry đơn giản** và **giữ nguyên dữ liệu khi lỗi**.

## 9. Chương trình Java 21 đầy đủ và đã chạy kiểm chứng

Lưu nguyên văn nội dung sau trong tệp **`CommandDispatchDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public final class CommandDispatchDemo {
    sealed interface Command permits CreateOrder, AddItems, CancelOrder {}
    record CreateOrder(String orderId, int quantity) implements Command {}
    record AddItems(String orderId, int delta) implements Command {}
    record CancelOrder(String orderId) implements Command {}
    record Order(String id, int quantity, boolean canceled) {}

    private final Map<String, Order> orders = new LinkedHashMap<>();
    private static int checks;

    private static boolean invalidId(String id) {
        return id == null || id.isBlank();
    }

    String route(Object incoming) {
        if (!(incoming instanceof Command command)) {
            return "NOT_A_COMMAND";
        }
        return dispatch(command);
    }

    String dispatch(Command command) {
        return switch (command) {
            case null -> "INVALID_COMMAND";

            case CreateOrder(var id, var quantity) when invalidId(id) ->
                    "INVALID_ID";
            case CreateOrder(var id, var quantity) when quantity <= 0 ->
                    "INVALID_QUANTITY";
            case CreateOrder(var id, var quantity) ->
                    create(id, quantity);

            case AddItems(var id, var delta) when invalidId(id) ->
                    "INVALID_ID";
            case AddItems(var id, var delta) when delta <= 0 ->
                    "INVALID_QUANTITY";
            case AddItems(var id, var delta) ->
                    add(id, delta);

            case CancelOrder(var id) when invalidId(id) ->
                    "INVALID_ID";
            case CancelOrder(var id) ->
                    cancel(id);
        };
    }

    private String create(String id, int quantity) {
        if (orders.containsKey(id)) {
            return "ALREADY_EXISTS";
        }
        orders.put(id, new Order(id, quantity, false));
        return "CREATED " + id + " qty=" + quantity;
    }

    private String add(String id, int delta) {
        Order previous = orders.get(id);
        if (previous == null) {
            return "NOT_FOUND";
        }
        if (previous.canceled()) {
            return "ORDER_CANCELED";
        }

        final int newQuantity;
        try {
            newQuantity = Math.addExact(previous.quantity(), delta);
        } catch (ArithmeticException overflow) {
            return "QUANTITY_OVERFLOW";
        }

        orders.put(id, new Order(id, newQuantity, false));
        return "UPDATED " + id + " qty=" + newQuantity;
    }

    private String cancel(String id) {
        Order previous = orders.get(id);
        if (previous == null) {
            return "NOT_FOUND";
        }
        if (previous.canceled()) {
            return "ALREADY_CANCELED";
        }
        orders.put(id, new Order(id, previous.quantity(), true));
        return "CANCELED " + id;
    }

    String snapshot(String id) {
        if (invalidId(id)) {
            return "INVALID_ID";
        }
        Order order = orders.get(id);
        if (order == null) {
            return "NOT_FOUND";
        }
        return "ORDER " + order.id()
                + " qty=" + order.quantity()
                + " status=" + (order.canceled() ? "CANCELED" : "ACTIVE");
    }

    private static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        CommandDispatchDemo bus = new CommandDispatchDemo();

        expect("null command", "INVALID_COMMAND", bus.dispatch(null));
        expect("null transport", "NOT_A_COMMAND", bus.route(null));
        expect("wrong transport type", "NOT_A_COMMAND", bus.route("noise"));
        expect("create null id", "INVALID_ID", bus.dispatch(new CreateOrder(null, 2)));
        expect("create blank id", "INVALID_ID", bus.dispatch(new CreateOrder(" ", 2)));
        expect("create zero", "INVALID_QUANTITY", bus.dispatch(new CreateOrder("O-1", 0)));
        expect("add null id", "INVALID_ID", bus.dispatch(new AddItems(null, 1)));
        expect("add zero", "INVALID_QUANTITY", bus.dispatch(new AddItems("O-1", 0)));
        expect("cancel blank id", "INVALID_ID", bus.dispatch(new CancelOrder(" ")));
        expect("add missing order", "NOT_FOUND", bus.dispatch(new AddItems("O-1", 1)));
        expect("cancel missing order", "NOT_FOUND", bus.dispatch(new CancelOrder("O-1")));

        expect("create valid", "CREATED O-1 qty=2",
                bus.dispatch(new CreateOrder("O-1", 2)));
        expect("create duplicate", "ALREADY_EXISTS",
                bus.dispatch(new CreateOrder("O-1", 3)));
        expect("route add", "UPDATED O-1 qty=5",
                bus.route(new AddItems("O-1", 3)));
        expect("active snapshot", "ORDER O-1 qty=5 status=ACTIVE",
                bus.snapshot("O-1"));
        expect("cancel", "CANCELED O-1", bus.dispatch(new CancelOrder("O-1")));
        expect("cancel again", "ALREADY_CANCELED",
                bus.dispatch(new CancelOrder("O-1")));
        expect("add after cancel", "ORDER_CANCELED",
                bus.dispatch(new AddItems("O-1", 1)));
        expect("canceled snapshot", "ORDER O-1 qty=5 status=CANCELED",
                bus.snapshot("O-1"));

        expect("create max", "CREATED MAX qty=2147483647",
                bus.dispatch(new CreateOrder("MAX", Integer.MAX_VALUE)));
        expect("overflow", "QUANTITY_OVERFLOW",
                bus.dispatch(new AddItems("MAX", 1)));
        expect("max unchanged", "ORDER MAX qty=2147483647 status=ACTIVE",
                bus.snapshot("MAX"));
        expect("unknown snapshot", "NOT_FOUND", bus.snapshot("missing"));
        expect("null snapshot", "INVALID_ID", bus.snapshot(null));
        expect("duplicate max", "ALREADY_EXISTS",
                bus.dispatch(new CreateOrder("MAX", 2)));
        expect("negative delta", "INVALID_QUANTITY",
                bus.dispatch(new AddItems("MAX", -1)));
        expect("cancel null id", "INVALID_ID",
                bus.dispatch(new CancelOrder(null)));

        System.out.println("PASS assertions=" + checks);
        System.out.println("PASS stored-orders=" + bus.orders.size());
        System.out.println("O-1=" + bus.snapshot("O-1"));
        System.out.println("MAX=" + bus.snapshot("MAX"));
        System.out.println("unknown=" + bus.snapshot("none"));
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc một compiler mới hơn hỗ trợ mức `--release 21`:

```bash
javac --release 21 -Xlint:all -Werror -encoding UTF-8 CommandDispatchDemo.java
java CommandDispatchDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
PASS assertions=27
PASS stored-orders=2
O-1=ORDER O-1 qty=5 status=CANCELED
MAX=ORDER MAX qty=2147483647 status=ACTIVE
unknown=NOT_FOUND
```

### Vì sao chương trình in PASS?

Hàm `expect` so sánh kết quả **thực tế** với chuỗi kỳ vọng của từng ca. Nếu không bằng nhau, nó ném `AssertionError`, vì vậy chương trình không thể in `PASS assertions=27` nếu một trong các so sánh trước đó thất bại.

- **27 assertions:** bao gồm sai kiểu, null, ID rỗng, quantity không hợp lệ, command trùng, đơn không tồn tại, hủy lặp, cập nhật đơn đã hủy và tràn số.
- **stored-orders=2:** chỉ hai ID `O-1` và `MAX` được tạo thành công; các command sai không thêm đơn.
- **O-1 ... CANCELED:** đơn được cộng từ 2 lên 5 trước khi hủy, rồi không thay đổi khi nhận lệnh cộng sau hủy.
- **MAX ... 2147483647:** lỗi `QUANTITY_OVERFLOW` không làm thay đổi số lượng tối đa đã lưu.
- **unknown=NOT_FOUND:** phương thức `snapshot` đọc trạng thái và xử lý đơn không tồn tại, không tạo dữ liệu mới.

Chương trình đã được biên dịch thành công với `javac --release 21 -Xlint:all -Werror`, **không có warning**, rồi chạy đúng năm dòng stdout như trên.

## 10. Kiểm tra compile-time khi thiếu một command case

Khi thêm biến thể mới vào `Command`, một dispatcher dùng `switch expression` không có `default` sẽ buộc code xử lý đủ subtype mới.

Ví dụ **cố ý không biên dịch được**:

```java
public class MissingCommandCase {
    sealed interface Command permits Create, Cancel, Refund {}
    record Create(String id) implements Command {}
    record Cancel(String id) implements Command {}
    record Refund(String id) implements Command {}

    static String handle(Command command) {
        return switch (command) {
            case Create(var id) -> "create";
            case Cancel(var id) -> "cancel";
            // Thiếu case Refund.
        };
    }
}
```

Biên dịch:

```bash
javac --release 21 -encoding UTF-8 MissingCommandCase.java
```

Compiler trả lỗi đã được tái hiện:

```text
error: the switch expression does not cover all possible input values
1 error
```

**Vì sao:** `Command` cho phép ba record `Create`, `Cancel`, `Refund`, nhưng `switch` chỉ xử lý hai. `switch expression` cần đầy đủ các khả năng đầu vào; compiler từ chối trường hợp thiếu subtype.

Cách sửa là thêm `case Refund(var id) -> ...` với hành vi hợp lệ, đồng thời viết test cho lệnh hoàn tiền. **Không nên thêm `default -> "OK"` chỉ để làm biến mất lỗi**, vì có thể che command mới chưa được triển khai.

### Không có default không đồng nghĩa xử lý null

Một `switch` đã exhaustive với mọi subtype của `Command` vẫn có thể ném `NullPointerException` khi selector null nếu không có `case null`. Exhaustiveness của hierarchy và chính sách null là hai vấn đề khác nhau. Dispatcher trong bài chủ động thêm `case null` để trả `INVALID_COMMAND`.

## 11. Kiểm tra compile-time khi case tổng quát che case cụ thể

Với pattern matching, **case rộng phải đứng sau case hẹp**. Ví dụ cố ý sai:

```java
public class DominatedCommandCase {
    sealed interface Command permits Create, Cancel {}
    record Create(String id) implements Command {}
    record Cancel(String id) implements Command {}

    static String handle(Command command) {
        return switch (command) {
            case Command any -> "generic";
            case Create(var id) -> "create";
            case Cancel(var id) -> "cancel";
        };
    }
}
```

`case Command any` khớp mọi subtype của `Command` khác null, nên hai case `Create` và `Cancel` sau đó không bao giờ được chọn. Kết quả kiểm chứng với `javac --release 21`:

```text
error: this case label is dominated by a preceding case label
2 errors
```

Đây là **compiler error**, không phải warning. Sửa bằng cách bỏ case `Command any` nếu hierarchy đã đóng và đủ case, hoặc đặt nó cuối khi thực sự cần một nhánh chung hợp lệ.

Trong dispatcher chính, các case `when invalidId(id)` và `when quantity <= 0` đứng trước case record cùng kiểu không guard để tránh chính lỗi dominance này.

## 12. Idempotency, retry, concurrency và transaction

Pattern switch quyết định **nên gọi handler nào**; nó không giải quyết những bài toán phân tán thường gặp ở command processing.

### 12.1. Retry và idempotency

- **CreateOrder:** cùng một ID tạo lại trả `ALREADY_EXISTS`; trạng thái không bị tạo đôi. Nhưng response lần hai khác lần đầu.
- **CancelOrder:** hủy lại trả `ALREADY_CANCELED`; trạng thái vẫn là canceled.
- **AddItems:** **không idempotent**. Gửi hai lần `AddItems("O-1",3)` sẽ tăng số lượng hai lần nếu đơn còn active.

Do đó khi consumer có thể nhận lại message do retry/at-least-once delivery, **không được suy luận rằng dùng `sealed Command` hoặc pattern switch đã bảo đảm exactly-once**. Cách làm phổ biến là gắn **command ID/idempotency key** cho từng yêu cầu và lưu kết quả đã xử lý trong cùng transaction với cập nhật domain khi có thể.

### 12.2. Đồng thời và lost update

Demo dùng `LinkedHashMap` và chuỗi `get → tính → put`. Nếu nhiều thread hoặc process cập nhật cùng một đơn đồng thời, một cập nhật có thể ghi đè kết quả cập nhật khác. Cần dùng transaction, optimistic locking/version, lock hoặc thiết kế concurrency khác tùy nơi lưu trữ.

Không sửa vấn đề này chỉ bằng cách thay `switch` thành `if` hay ngược lại. Điều phối kiểu dữ liệu và đồng bộ trạng thái là **hai tầng khác nhau**.

### 12.3. Validation và biên tin cậy

Trong ví dụ, constructor record cho phép một số input sai để các guard của dispatcher minh họa rõ cách hoạt động. Ở hệ thống production, có thể:

- Kiểm tra request khi deserialize/parse (schema, loại command, độ dài, dữ liệu bắt buộc).
- Đặt invariant trong constructor/factory của command nếu command phải luôn hợp lệ sau khi tạo.
- Kiểm tra quyền thực thi (authorization) trước khi cập nhật domain.
- Kiểm tra trạng thái hiện tại trong handler, vì chỉ kiểm tra input là chưa đủ.
- Dùng kiểu kết quả có cấu trúc `Success/ValidationError/NotFound/Conflict` thay vì chuỗi tự do như demo.

Đặc biệt, không đưa dữ liệu đầu vào tùy ý trực tiếp vào SQL, shell hoặc HTTP calls chỉ vì nó đã khớp một record pattern. Pattern matching không thay thế input validation và kiểm soát quyền truy cập.

## 13. Pattern switch so với handler registry và polymorphism

Một số cách khác cũng có thể điều phối command.

| Tiêu chí | Sealed command + pattern switch | Handler registry / polymorphism |
| --- | --- | --- |
| Tập command | Đóng, liệt kê bởi `permits` | Thường có thể mở rộng động |
| Thêm command mới | Cập nhật `permits` và các exhaustive switch | Đăng ký handler mới hoặc thêm implementation |
| Phân tích thiếu case | Compiler hỗ trợ với sealed hierarchy | Có thể phải dùng kiểm tra registry/config/test |
| Code điều phối | Một switch dễ đọc với số biến thể vừa phải | Dispatcher có thể chỉ lookup rồi gọi handler |
| Logic nghiệp vụ | Nên tách ra phương thức/service | Có thể nằm trong handler riêng |
| Phù hợp | Domain đóng, tool nội bộ, DSL, command nhỏ/vừa | Plugin API, hệ thống modular/microservice, nhiều team mở rộng |
| Runtime config | Chủ yếu tĩnh theo kiểu Java | Có thể dựa vào DI container hoặc cấu hình |

**Khi nào pattern switch hợp lý?** Khi thư viện kiểm soát toàn bộ biến thể, muốn compiler phát hiện lệnh mới chưa hỗ trợ, và số nhánh đủ nhỏ để giữ dispatcher dễ đọc.

**Khi nào nên chuyển sang registry?** Khi phần xử lý mỗi command có nhiều dependency, cần plugin thêm command ngoài module, hoặc dispatcher trở nên quá lớn. Có thể giữ `sealed Command` ở module domain và delegate từ `switch` sang các handler/service được inject để kết hợp lợi ích hai hướng.

**Visitor Pattern** là lựa chọn khác: mỗi command có `accept(visitor)`, còn visitor định nghĩa một `visit` cho từng subtype. Nó tách thao tác nhưng thường tăng boilerplate và đòi hỏi interface visitor được cập nhật khi thêm biến thể. Đừng chọn chỉ vì trong bài có từ "pattern"; lựa chọn phụ thuộc nhu cầu mở rộng.

## 14. Kiểm thử dispatcher đúng cách

Cần kiểm tra **đúng response lẫn trạng thái sau lệnh**, bởi một response `UPDATED` vẫn có thể bị in sai khi map không thay đổi.

### Bảng kiểm thử tối thiểu

| Trường hợp | Input | Kết quả kỳ vọng |
| --- | --- | --- |
| Selector null | `dispatch(null)` | `INVALID_COMMAND` |
| Transport không phải command | `route("noise")` | `NOT_A_COMMAND` |
| ID null/blank | `CreateOrder(null,2)`, `CancelOrder(" ")` | `INVALID_ID` |
| Quantity/Delta không dương | `CreateOrder("O-1",0)`, `AddItems("O-1",-1)` | `INVALID_QUANTITY` |
| Thao tác trên đơn chưa tồn tại | `AddItems("O-1",1)` | `NOT_FOUND` |
| Tạo mới | `CreateOrder("O-1",2)` | `CREATED O-1 qty=2` |
| Tạo trùng | `CreateOrder("O-1",3)` | `ALREADY_EXISTS`; đơn vẫn qty 2 |
| Cộng số lượng | `AddItems("O-1",3)` | `UPDATED O-1 qty=5` |
| Hủy lần đầu | `CancelOrder("O-1")` | `CANCELED O-1` |
| Hủy lặp | `CancelOrder("O-1")` | `ALREADY_CANCELED` |
| Cộng sau hủy | `AddItems("O-1",1)` | `ORDER_CANCELED`; qty vẫn 5 |
| Tràn số | `AddItems("MAX",1)` khi qty đã max | `QUANTITY_OVERFLOW`; qty không đổi |
| Thiếu subtype trong switch | Ví dụ `MissingCommandCase` | Compiler phải từ chối |
| Case bị che | Ví dụ `DominatedCommandCase` | Compiler phải từ chối |

Chương trình mục 9 đã thực hiện **27 phép assert với oracle độc lập** và kiểm tra snapshot giữa các thao tác. Những thông báo PASS chỉ được in nếu toàn bộ assert trước đó thành công.

### Các test nên bổ sung trong hệ thống thật

1. **Contract test:** lỗi input phải được ánh xạ sang response/error code API đúng thỏa thuận.
2. **Persistence/transaction test:** lệnh lỗi không tạo ra bản ghi hoặc làm thay đổi trạng thái không hợp lệ.
3. **Concurrency test:** hai lệnh tăng số lượng đồng thời không mất cập nhật.
4. **Retry/idempotency test:** gửi lại cùng command ID không áp dụng side effect hai lần.
5. **Authorization test:** caller không có quyền không thể tạo/hủy đơn dù command hợp lệ về kiểu.
6. **Compatibility test:** khi thêm subtype hoặc thay schema message, consumer cũ có phương án xử lý rõ ràng.
7. **Boundary test:** `Integer.MAX_VALUE`, ID rỗng, ID toàn khoảng trắng, giá trị null, record có trường sai.

**Branch coverage** từ JaCoCo có thể chỉ ra những đường chưa được chạy, nhưng không chứng minh logic đúng. Hãy dùng assert kết quả và trạng thái như bảng ở trên; có thể thêm mutation testing để phát hiện guard sai dấu (`delta <= 0` thành `delta < 0`, chẳng hạn).

## 15. Những lỗi thường gặp

1. **Dùng `switch` trên `Object` rồi cast thủ công trong từng nhánh.** Khi type/record patterns được phép, nên khai báo command qua `sealed interface` và dùng pattern variables thay cast.
2. **Cho rằng `sealed` tự validate dữ liệu command.** `CreateOrder(null,0)` vẫn có thể được tạo nếu record không đặt invariant; các guard hoặc constructor phải xử lý.
3. **Đặt case rộng trước case có `when`.** Case rộng sẽ che case đặc biệt và có thể gây compile error `dominated case`.
4. **Thêm `default -> "SUCCESS"` để switch khỏi thiếu case.** Với closed hierarchy, default có thể che command mới chưa có handler; hãy bổ sung case nghiệp vụ.
5. **Nhầm null selector với null component.** `dispatch(null)` đi vào `case null`; `dispatch(new CreateOrder(null,2))` phải đi vào guard kiểm tra ID.
6. **Gọi `id.isBlank()` trước khi kiểm tra null.** `id==null || id.isBlank()` an toàn; đảo thứ tự có thể gây NPE.
7. **Giả định `var` là dynamic typing.** `id` được compiler suy ra `String`, `quantity` suy ra `int` từ record.
8. **Đặt toàn bộ nghiệp vụ vào các biểu thức case dài.** Dispatcher nên chỉ có logic chọn nhánh và điều kiện ngắn, còn cập nhật state ở helper/handler.
9. **Không kiểm tra overflow của phép cộng số lượng.** `int` có thể wrap khi cộng vượt miền; dùng `Math.addExact` hoặc miền số học phù hợp.
10. **Gọi lại `AddItems` khi retry mà không có idempotency key.** Lệnh cộng có side effect không idempotent; cần chống replay ở tầng nghiệp vụ.
11. **Nhầm command với query.** Xem trạng thái đơn không phải lệnh ghi; có thể tách read method/handler riêng như `snapshot`.
12. **Cho rằng map demo đã thread-safe.** `LinkedHashMap` với chuỗi `get/put` không bảo đảm transaction và atomicity khi có cập nhật đồng thời.
13. **Coi compile-time exhaustiveness là kiểm tra mọi sai sót.** Compiler kiểm tra subtype/case, nhưng không kiểm tra quyền truy cập, dữ liệu null bên trong record hoặc chính sách nghiệp vụ.
14. **Chạy mã pattern switch/record pattern của bài ở mức Java 17.** Các tính năng này đã final từ Java 21; dùng `--release 21` với toolchain thích hợp.

## 16. Bài tập tự luyện

**Bài 1.** Nếu thêm `record RestoreOrder(String orderId) implements Command {}`, bước nào cần thực hiện để không phá mô hình `sealed`?

*Đáp án:* Thêm `RestoreOrder` vào `permits`, quyết định invariant cho command, bổ sung case trong `switch` và handler khôi phục, rồi thêm test trạng thái. Nếu chưa xử lý subtype mới, compiler sẽ báo `switch expression` không exhaustive.

**Bài 2.** Tại sao `case CreateOrder(var id, var quantity)` không guard phải đứng sau hai case kiểm tra ID và quantity?

*Đáp án:* Case không guard khớp mọi `CreateOrder` khác null. Nếu đứng trước, hai case có `when` phía sau bị dominated. Đặt guard chuyên biệt trước để kiểm tra dữ liệu đúng thứ tự.

**Bài 3.** `dispatch(null)` và `route(null)` có cùng kết quả không?

*Đáp án:* Không, theo hợp đồng minh họa: `dispatch(null)` trả `INVALID_COMMAND` bởi `case null`, còn `route(null)` trả `NOT_A_COMMAND` vì `instanceof Command` thất bại. Nếu API yêu cầu đồng nhất mã lỗi, cần thay đổi policy ở boundary.

**Bài 4.** Vì sao `AddItems("O-1",3)` không idempotent?

*Đáp án:* Nếu đơn active và hai lệnh được thực hiện, số lượng tăng hai lần. Pattern switch không chống retry; cần command ID/idempotency store và transaction phù hợp.

**Bài 5.** Vì sao `Math.addExact` tốt hơn `previous.quantity() + delta` trong bài?

*Đáp án:* Nó ném `ArithmeticException` khi tràn `int`, cho phép handler trả `QUANTITY_OVERFLOW` và giữ nguyên state. Phép cộng `int` thông thường có thể overflow và wrap thành giá trị không hợp lệ.

**Bài 6.** `record CancelOrder(String orderId) implements Command {}` có thể chứa `orderId == null` không?

*Đáp án:* Có nếu constructor không validate. Record pattern `CancelOrder(var id)` vẫn có thể khớp record đó; `invalidId(id)` phải xử lý null an toàn.

**Bài 7.** Nếu số loại command tăng lên hàng trăm và mỗi handler cần nhiều dependency, nên làm gì?

*Đáp án:* Có thể giữ model command đóng theo module nhưng delegate từ `switch` sang handler/service riêng, hoặc dùng handler registry với cơ chế xác nhận đủ handler. Cần đánh giá modularity, quy tắc mở rộng và khả năng kiểm tra thiếu nhánh.

**Bài 8.** Sau khi nhận `ORDER_CANCELED` từ `AddItems`, cần assert gì ngoài response?

*Đáp án:* Đọc lại đơn (ví dụ `snapshot`) và xác nhận trạng thái vẫn `CANCELED`, số lượng không đổi. Kiểm thử side effect quan trọng ngang với kiểm thử mã kết quả.

## 17. Tài liệu tham khảo chính thức

- [JEP 409 – Sealed Classes (Java 17)](https://openjdk.org/jeps/409)
- [JEP 395 – Records (Java 16)](https://openjdk.org/jeps/395)
- [JEP 394 – Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 440 – Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 – Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 – Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
- [JLS Java 21 – Switch blocks, dominance/exhaustiveness](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [JLS Java 21 – Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
