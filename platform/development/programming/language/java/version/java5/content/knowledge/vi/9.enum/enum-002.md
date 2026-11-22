# Khai báo enum và các hằng enum

## 1. Enum mô tả một tập giá trị có tên và có kiểu riêng

Một kiểu liệt kê (`enum`) mô tả một tập giá trị được khai báo trước, chẳng hạn hướng di chuyển hoặc trạng thái đơn hàng:

```java
enum OrderState {
    NEW,
    PAID,
    SHIPPED
}
```

Ở đây:

- `OrderState` là một kiểu Java.
- `NEW`, `PAID`, `SHIPPED` là ba hằng enum thuộc kiểu đó.
- Mỗi hằng đại diện cho một đối tượng enum được tạo trong quá trình khởi tạo lớp.
- Biến `OrderState` có thể tham chiếu đến một hằng của kiểu này hoặc mang giá trị `null`.

Ví dụ:

```java
OrderState state = OrderState.NEW;
state = OrderState.PAID;
```

Đổi giá trị biến `state` không sửa đối tượng `NEW` thành `PAID`; nó làm biến tham chiếu đến một hằng khác.

Enum giúp chữ ký API diễn đạt tập giá trị hợp lệ:

```java
static boolean isPaid(OrderState state) {
    return state == OrderState.PAID;
}
```

Nơi gọi không thể truyền một chuỗi hoặc một số nguyên tùy ý như thể đó là `OrderState`:

```java
// Không biên dịch:
// OrderState state = "PAID";
// OrderState state = 1;
// isPaid("PAID");
```

Điều quan trọng là **tên hằng đi cùng kiểu chứa nó**, chứ không chỉ là những tên được nhóm lại cho đẹp. Cơ chế này được đưa vào từ Java 5 và vẫn dùng trong Java hiện đại; chương trình hoàn chỉnh trong bài chạy với Java 17+.

## 2. Cú pháp khai báo cơ bản

### 2.1. Các hằng ngăn cách bằng dấu phẩy

```java
enum Direction {
    NORTH,
    EAST,
    SOUTH,
    WEST
}
```

Có thể viết ngắn trên một dòng nếu vẫn dễ đọc:

```java
enum Direction { NORTH, EAST, SOUTH, WEST }
```

Đây là hai cách viết thay thế cho cùng một khai báo; không đặt đồng thời hai kiểu cùng tên trong cùng phạm vi.

Quy ước đặt tên thường dùng:

| Thành phần | Quy ước | Ví dụ |
| --- | --- | --- |
| Tên kiểu enum | PascalCase | `OrderState`, `Direction` |
| Tên hằng | Chữ hoa, nối từ bằng gạch dưới | `NEW`, `IN_PROGRESS` |
| Tên biến | camelCase | `currentState`, `direction` |

Viết hoa là quy ước dễ nhận diện hằng, không phải điều kiện duy nhất để trình biên dịch công nhận hằng enum. Tên vẫn phải là định danh Java hợp lệ và không được khai báo trùng trong phạm vi không cho phép.

### 2.2. Dấu phẩy cuối được phép

```java
enum Priority {
    LOW,
    NORMAL,
    HIGH,
}
```

Dấu phẩy sau `HIGH` hợp lệ. Nó có thể giúp việc thêm hoặc thay đổi các dòng hằng thuận tiện hơn.

### 2.3. Dấu chấm phẩy ngăn danh sách hằng với thành viên

Nếu enum chỉ có các hằng, dấu chấm phẩy sau hằng cuối không bắt buộc:

```java
enum SwitchState {
    OFF, ON
}
```

Nếu phía sau có trường, hàm tạo hoặc phương thức, phải kết thúc danh sách hằng bằng dấu chấm phẩy:

```java
enum SwitchState {
    OFF,
    ON;

    boolean isOn() {
        return this == ON;
    }
}
```

Dấu phẩy phân tách các hằng với nhau. Dấu chấm phẩy kết thúc phần danh sách hằng để bắt đầu các khai báo thành viên khác.

Không viết trường hoặc phương thức trước danh sách hằng. Với một enum có hằng, danh sách hằng nằm ở đầu thân khai báo.

## 3. Đặt enum ở đâu và truy cập như thế nào?

### 3.1. Enum cấp cao nhất

Nếu enum là một kiểu `public` cấp cao nhất:

```java
public enum Direction {
    NORTH, EAST, SOUTH, WEST
}
```

thì với cách tổ chức tệp Java thông thường, lưu nó trong `Direction.java`.

Nếu không ghi `public`, enum cấp cao nhất có phạm vi truy cập trong package:

```java
enum InternalState {
    READY, CLOSED
}
```

Không khai báo một enum cấp cao nhất là `private` hoặc `protected`; các mức đó áp dụng cho những ngữ cảnh thành viên thích hợp, không phải kiểu cấp cao nhất.

### 3.2. Enum là thành viên của một lớp

```java
class Order {
    enum State {
        NEW, PAID, SHIPPED
    }

    private State state = State.NEW;
}
```

Kiểu được tham chiếu bằng `Order.State` từ một nơi có quyền truy cập phù hợp.

Enum thành viên ngầm định là `static`; nó không cần một đối tượng `Order` bao ngoài để tạo ra các hằng riêng. Không có một bộ `NEW`, `PAID`, `SHIPPED` mới cho mỗi đơn hàng.

Nếu không có ràng buộc truy cập khác, dùng tên đầy đủ của kiểu để làm rõ nơi khai báo:

```java
Order.State state = Order.State.NEW;
```

Enum lồng có thể được khai báo `public`, `private` hoặc mức khác phù hợp với nơi đặt nó. Các hằng là thành viên public của kiểu enum, nhưng quyền truy cập vào chính kiểu enum vẫn quyết định bên ngoài có dùng được chúng hay không.

## 4. Hằng enum là đối tượng, không phải số nguyên

Mỗi hằng trong danh sách tạo ra một thành viên ngầm định có tính chất `public static final` và mang kiểu enum tương ứng.

Với:

```java
enum OrderState {
    NEW, PAID, SHIPPED
}
```

có thể truy cập bằng:

```java
OrderState first = OrderState.NEW;
OrderState second = OrderState.NEW;

System.out.println(first == second); // true
```

Hai tham chiếu cùng trỏ đến hằng `NEW` của cùng kiểu enum đã được định nghĩa. So sánh `==` là cách tự nhiên để kiểm tra hằng enum.

Các giới hạn cơ bản:

```java
// Không hợp lệ:
// OrderState state = new OrderState();
// OrderState.NEW = OrderState.PAID;
// int code = OrderState.PAID;
```

- Không dùng `new` để tạo thêm đối tượng enum từ mã ứng dụng.
- Không gán lại trường hằng `NEW`.
- Không có chuyển đổi ngầm định từ hằng enum sang `int`.

Enum có thể cung cấp dữ liệu số riêng khi bài toán cần, nhưng mã nghiệp vụ đó là một thuộc tính được thiết kế tường minh, không phải bản chất của hằng enum.

### 4.1. Biến enum vẫn có thể là null

```java
OrderState state = null;

System.out.println(state == OrderState.NEW); // false
// state.name(); // Ném NullPointerException nếu gọi.
```

Kiểu enum không tự tạo một ràng buộc khác `null` cho mọi biến. Nếu một API bắt buộc có trạng thái, cần kiểm tra hoặc mô hình hóa hợp đồng đó rõ ràng.

`==` với một hằng hoạt động an toàn khi biến còn lại là `null`; gọi phương thức trên biến `null` thì không.

### 4.2. Trường tham chiếu đến hằng không tự trở thành một hằng mới

```java
enum Level {
    LOW,
    HIGH;

    static final Level DEFAULT = LOW;
}
```

`DEFAULT` là một trường tham chiếu đến `LOW`, không phải một hằng thứ ba trong danh sách enum. `Level.values()` vẫn chỉ chứa `LOW` và `HIGH`; `Level.DEFAULT.name()` là `"LOW"`.

Muốn khai báo một hằng enum mới, phải đặt nó trong danh sách hằng ở đầu thân enum.

## 5. Hằng có thể mang dữ liệu riêng

Một enum là một dạng lớp, nên có thể có trường, hàm tạo và phương thức:

```java
enum OrderState {
    NEW("Mới"),
    PAID("Đã thanh toán"),
    SHIPPED("Đã giao");

    private final String label;

    OrderState(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }
}
```

Các chuỗi trong ngoặc là đối số khởi tạo của từng hằng:

```text
NEW      → label = "Mới"
PAID     → label = "Đã thanh toán"
SHIPPED  → label = "Đã giao"
```

Lưu ý:

- Không viết `public` hoặc `protected` cho hàm tạo enum.
- Hàm tạo không ghi mức truy cập trong enum có quyền truy cập private theo quy tắc của enum.
- Mã bên ngoài không được gọi hàm tạo để thêm hằng.
- Nếu hàm tạo cần đối số, mỗi hằng phải cung cấp lời gọi phù hợp.
- Dấu chấm phẩy sau `SHIPPED(...)` là cần thiết vì phía sau còn thành viên.

Các trường ở ví dụ dùng `final` và dữ liệu `String`, phù hợp với thông tin cố định của trạng thái. Tuy nhiên, từ khóa `enum` không tự làm mọi trạng thái bên trong đối tượng bất biến. Một trường có thể bị thiết kế cho phép sửa, hoặc một trường `final` có thể tham chiếu đến một collection mutable.

Các hằng được dùng chung trong chương trình; tránh lưu trạng thái thay đổi của từng đơn hàng vào chính `OrderState.NEW`. Trạng thái riêng của mỗi đơn hàng thuộc về đối tượng đơn hàng; enum chỉ biểu diễn giá trị trạng thái.

## 6. Chương trình hoàn chỉnh

Lưu thành `EnumDeclarationDemo.java`:

```java
public class EnumDeclarationDemo {
    public enum OrderState {
        NEW("Mới"),
        PAID("Đã thanh toán"),
        SHIPPED("Đã giao");

        private final String label;

        OrderState(String label) {
            this.label = label;
        }

        public String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        OrderState current = OrderState.NEW;

        System.out.println("name = " + current.name());
        System.out.println("label = " + current.label());
        System.out.println("same = " + (current == OrderState.NEW));

        for (OrderState state : OrderState.values()) {
            System.out.println(state.name() + " -> " + state.label());
        }

        OrderState parsed = OrderState.valueOf("PAID");
        System.out.println("parsed = " + parsed.label());

        current = OrderState.SHIPPED;
        System.out.println("current = " + current.name());

        // Không biên dịch nếu bật các dòng sau:
        // current = "PAID";
        // current = new OrderState("Khác");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all EnumDeclarationDemo.java
java EnumDeclarationDemo
```

Stdout chính xác:

```text
name = NEW
label = Mới
same = true
NEW -> Mới
PAID -> Đã thanh toán
SHIPPED -> Đã giao
parsed = Đã thanh toán
current = SHIPPED
```

Kiểu `OrderState` được đặt bên trong lớp chính để toàn bộ ví dụ nằm trong một tệp. Nó là enum thành viên ngầm định `static`, không cần tạo một `EnumDeclarationDemo` để dùng các hằng.

Các thao tác trong ví dụ:

- Truy cập một hằng bằng tên kiểu và tên hằng.
- Đọc dữ liệu riêng của hằng.
- So sánh danh tính hằng bằng `==`.
- Duyệt toàn bộ hằng theo thứ tự khai báo.
- Tìm một hằng theo đúng tên.
- Gán một biến sang một giá trị enum khác.

Đây là việc thay đổi giá trị của biến `current`, không phải khai báo thêm hằng lúc chạy.

## 7. Các thành viên có sẵn giúp sử dụng khai báo

### 7.1. values(): lấy các hằng theo thứ tự khai báo

```java
OrderState[] states = OrderState.values();
```

Mảng chứa các hằng `NEW`, `PAID`, `SHIPPED` theo thứ tự đã viết. Có thể dùng vòng lặp để sinh lựa chọn giao diện hoặc xử lý từng giá trị.

Thay đổi một ô trong mảng trả về không sửa danh sách hằng đã khai báo:

```java
OrderState[] states = OrderState.values();
states[0] = OrderState.SHIPPED;

System.out.println(OrderState.values()[0]); // NEW
```

Mảng là cấu trúc chứa các tham chiếu, không phải cơ chế thêm, xóa hoặc đổi định nghĩa hằng enum.

### 7.2. name() và toString(): tên khai báo và chuỗi biểu diễn

`name()` trả chính xác tên đã khai báo, ví dụ `"PAID"`. Đây không phải nhãn tiếng Việt `"Đã thanh toán"`.

`toString()` mặc định cũng trả tên hằng, nhưng enum có thể ghi đè nó để thay đổi cách biểu diễn. Vì vậy, khi cần một nhãn hiển thị riêng, trường `label` như ví dụ làm rõ sự khác nhau giữa tên định danh và nội dung cho người dùng.

Đổi tên hằng có thể ảnh hưởng dữ liệu hoặc giao thức bên ngoài đang dùng tên đó. Hãy xác định rõ định dạng lưu hoặc trao đổi thay vì coi tên khai báo có thể tùy ý thay mà không tác động.

### 7.3. valueOf(): tìm theo đúng tên hằng

```java
OrderState state = OrderState.valueOf("PAID");
```

Chuỗi phải khớp chính xác, có phân biệt chữ hoa–thường và không tự bỏ khoảng trắng:

```java
// Các lời gọi sau ném IllegalArgumentException:
// OrderState.valueOf("paid");
// OrderState.valueOf(" PAID ");
// OrderState.valueOf("Đã thanh toán");
```

Truyền `null` ném `NullPointerException`. Khi đọc dữ liệu bên ngoài, cần quy tắc xác thực và xử lý giá trị không hợp lệ; `valueOf` không tự chuyển nhãn hiển thị thành hằng.

### 7.4. ordinal(): vị trí không phải mã nghiệp vụ

`ordinal()` trả vị trí khai báo bắt đầu từ 0. Với ví dụ, `NEW` có vị trí 0.

Thêm hoặc sắp xếp lại hằng có thể đổi vị trí. Vì vậy, không dùng `ordinal()` như một mã ổn định để lưu cơ sở dữ liệu hoặc trao đổi giữa hệ thống. Nếu cần mã như `"new"` hay `100`, khai báo trường mã tường minh và định nghĩa quy tắc chuyển đổi riêng.

## 8. Những giới hạn giúp tránh thiết kế sai

### 8.1. Không thêm giá trị enum từ dữ liệu lúc chạy

Danh sách hằng nằm trong mã nguồn đã biên dịch. Một bản ghi mới trong cơ sở dữ liệu không thể tự tạo một hằng enum mới.

Enum phù hợp khi tập giá trị là một phần của mô hình chương trình. Với danh mục do người dùng mở rộng liên tục, một thực thể dữ liệu hoặc một mô hình mã riêng thường phù hợp hơn.

### 8.2. Không kế thừa enum để thêm hằng

Không viết một lớp con tự do của enum chỉ để mở rộng danh sách giá trị. Java kiểm soát tập thể hiện của kiểu enum; các hằng được khai báo trong chính thân enum.

Enum đã có lớp cha ngầm định liên quan đến `java.lang.Enum`, nên không dùng `extends` để chọn một lớp cha khác. Nó vẫn có thể cài đặt interface khi cần một hợp đồng hành vi; đó là khả năng khác với mở rộng danh sách hằng.

### 8.3. Enum không tự kiểm tra chuyển trạng thái nghiệp vụ

Khai báo `NEW`, `PAID`, `SHIPPED` không tự cấm:

```java
OrderState state = OrderState.NEW;
state = OrderState.SHIPPED;
```

Hai phép gán đều hợp lệ về kiểu. Nếu nghiệp vụ yêu cầu phải thanh toán trước khi giao, cần logic chuyển trạng thái ở mô hình phù hợp. Kiểu enum bảo đảm giá trị nằm trong tập đã khai báo, không tự bảo đảm thứ tự sự kiện.

### 8.4. Cùng tên hằng không có nghĩa cùng kiểu

```java
enum PaymentState {
    NEW, COMPLETED
}

enum ShipmentState {
    NEW, DELIVERED
}
```

`PaymentState.NEW` và `ShipmentState.NEW` là hai giá trị thuộc hai kiểu khác nhau. Không gán giá trị của kiểu này cho biến kiểu kia chỉ vì cùng tên `NEW`.

## 9. Tự kiểm tra một khai báo

Khi khai báo enum mới, hãy xác định:

1. Tập giá trị có thực sự thuộc về mô hình được kiểm soát trong mã nguồn không?
2. Tên kiểu và tên hằng có diễn tả đúng ý nghĩa không?
3. Danh sách hằng có dấu phẩy và dấu chấm phẩy đúng chỗ không?
4. Enum có nằm ở tệp hoặc phạm vi truy cập thích hợp không?
5. Dữ liệu trên từng hằng có cố định và không chứa trạng thái riêng của mỗi đối tượng nghiệp vụ không?
6. Tên khai báo, nhãn hiển thị và mã trao đổi bên ngoài đã được phân biệt chưa?
7. API có cần chặn `null` hoặc kiểm tra chuyển trạng thái riêng không?

Một khai báo enum tốt vừa có tập giá trị rõ ràng vừa làm cho mã gọi dễ đọc như `OrderState.PAID`, đồng thời giữ những quy tắc nghiệp vụ vượt ngoài tập giá trị ở đúng nơi chịu trách nhiệm.

## Tài liệu đối chiếu

- [JLS §8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9): khai báo enum, danh sách hằng, hàm tạo và thành viên.
- [Java Enum API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html): `name()`, `ordinal()`, `toString()`, `valueOf` và quan hệ các hằng.
