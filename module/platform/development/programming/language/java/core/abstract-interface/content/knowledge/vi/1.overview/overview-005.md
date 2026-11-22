# Quan hệ giữa kiểu, đối tượng, trạng thái và hành vi trong Java

## 1. Bức tranh tổng thể

Trong lập trình hướng đối tượng, bốn khái niệm **kiểu (type)**, **đối tượng (object)**, **trạng thái (state)** và **hành vi (behavior)** liên hệ với nhau nhưng không đồng nghĩa:

| Khái niệm | Câu hỏi trả lời | Ý nghĩa trong Java |
| --- | --- | --- |
| **Kiểu** | Một giá trị/tham chiếu được phép sử dụng như thế nào? | Lớp (`class`), lớp trừu tượng (`abstract class`), giao diện (`interface`), `record`, `enum`… xác định các thành viên có thể truy cập, ràng buộc kiểu và hợp đồng thao tác. |
| **Đối tượng** | Thực thể nào tồn tại khi chương trình chạy? | Một thể hiện được tạo từ lớp cụ thể; có danh tính riêng, thuộc tính của thể hiện và khả năng thực thi các phương thức. |
| **Trạng thái** | Thực thể đang ở tình trạng nào? | Các giá trị hiện tại của **trường thể hiện** (instance fields) và những dữ liệu mà đối tượng quản lý. |
| **Hành vi** | Thực thể có thể làm gì? | Các thao tác do phương thức thể hiện cung cấp; có thể đọc, kiểm tra hoặc thay đổi trạng thái và tương tác với đối tượng khác. |

Mối quan hệ quan trọng:

- **Kiểu mô tả khả năng và giới hạn sử dụng đối tượng**. Một đối tượng có thể được nhìn qua nhiều kiểu tương thích.
- **Đối tượng cụ thể sở hữu trạng thái thể hiện**. Mỗi đối tượng thường có các trường thể hiện riêng; hai tham chiếu trỏ vào *cùng* đối tượng thì nhìn thấy cùng trạng thái.
- **Hành vi là cách đối tượng bộc lộ hoặc thay đổi trạng thái**. Đóng gói giúp tránh sửa trạng thái tùy tiện.
- **Kiểu của biến tham chiếu được biết khi biên dịch; lớp thực tế của đối tượng được biết khi chạy**. Hai thông tin này có thể khác nhau.

Sơ đồ đọc theo chiều quan hệ:

```text
Kiểu / hợp đồng
   | cho biết được gọi thao tác nào
   v
Biến tham chiếu ----trỏ tới----> Đối tượng
                                  | giữ
                                  v
                              Trạng thái
                                  ^
                                  | được đọc / cập nhật
                                  |
                              Hành vi
```

Lưu ý: kiểu dữ liệu nguyên thủy như `int` hay `boolean` cũng là kiểu, nhưng giá trị nguyên thủy không phải đối tượng. Phần tiếp theo tập trung vào các **kiểu tham chiếu** và đối tượng.

## 2. Kiểu không phải đối tượng

Hãy phân biệt **khai báo biến**, **tạo đối tượng** và **gán tham chiếu**:

```java
Vehicle vehicle = new Bicycle("City");
```

- `Vehicle` là **kiểu khai báo của biến** `vehicle`; trình biên dịch dựa vào kiểu này để quyết định các thành viên có thể gọi trực tiếp.
- `new Bicycle("City")` tạo **một đối tượng** thuộc lớp cụ thể `Bicycle`, chạy constructor để thiết lập trạng thái ban đầu.
- `vehicle` lưu **tham chiếu** đến đối tượng. Phép gán tham chiếu không sao chép toàn bộ đối tượng.
- Nếu `Bicycle extends Vehicle`, một đối tượng `Bicycle` có thể được dùng ở vị trí yêu cầu `Vehicle`. Quan hệ này là đa hình theo kiểu con (subtype polymorphism).

Ví dụ: biến kiểu `Vehicle` có thể gọi phương thức được công bố bởi `Vehicle`, kể cả khi đối tượng đang trỏ đến thực sự là `Bicycle`. Muốn gọi thao tác chỉ có ở giao diện `Movable`, cần một tham chiếu có kiểu cho phép thao tác đó hoặc kiểm tra/ép kiểu hợp lệ.

**Đừng nhầm quan hệ “là một” với “có một”:** `Bicycle extends Vehicle` mô tả quan hệ kiểu con; còn `Car` có trường `Engine engine` là quan hệ hợp thành/liên kết đối tượng (has-a), không khiến `Car` trở thành kiểu con của `Engine`.

## 3. Ví dụ đầy đủ: một đối tượng, nhiều kiểu nhìn, một trạng thái

Tạo tệp `TypeStateDemo.java` với nội dung sau. Ví dụ dùng Java 17+, hoàn chỉnh và có thể biên dịch độc lập:

```java
public class TypeStateDemo {
    interface Movable {
        void move(int steps);
    }

    static abstract class Vehicle {
        private final String name;
        private int distance;

        protected Vehicle(String name) {
            this.name = name;
        }

        public final String name() {
            return name;
        }

        public final int distance() {
            return distance;
        }

        protected final void addDistance(int steps) {
            if (steps < 0) {
                throw new IllegalArgumentException("steps must be >= 0");
            }
            distance = Math.addExact(distance, steps);
        }

        public abstract String kind();
    }

    static final class Bicycle extends Vehicle implements Movable {
        Bicycle(String name) {
            super(name);
        }

        @Override
        public void move(int steps) {
            addDistance(steps);
        }

        @Override
        public String kind() {
            return "bicycle";
        }
    }

    public static void main(String[] args) {
        Bicycle bike = new Bicycle("City");
        Vehicle asVehicle = bike;
        Movable asMovable = bike;

        asMovable.move(3);
        System.out.println(asVehicle.name()
                + " / " + asVehicle.kind()
                + " / " + asVehicle.distance());

        asMovable.move(2);
        System.out.println(bike.distance());
        System.out.println(bike == asVehicle);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac TypeStateDemo.java
java TypeStateDemo
```

Kết quả chuẩn:

```text
City / bicycle / 3
5
true
```

Phân tích theo bốn khái niệm:

1. **Kiểu**: `Vehicle` là lớp trừu tượng có trạng thái chung và hợp đồng `kind()`; `Movable` là giao diện khai báo khả năng `move(int)`; `Bicycle` là lớp cụ thể kế thừa và hiện thực các hợp đồng ấy.
2. **Đối tượng**: chỉ có **một** lần `new Bicycle("City")`. Các biến `bike`, `asVehicle`, `asMovable` cùng trỏ tới **một đối tượng**.
3. **Trạng thái**: `name` được khởi tạo là `"City"` và không thể gán lại sau khởi tạo vì là trường `final`; `distance` bắt đầu bằng `0` và lần lượt trở thành `3`, `5`.
4. **Hành vi**: `move(3)` và `move(2)` làm thay đổi `distance`; `distance()` đọc trạng thái; `kind()` trả về thông tin loại xe.
5. **Đa hình**: gọi `asVehicle.kind()` thực thi triển khai `Bicycle.kind()` tại thời điểm chạy. Kết quả `bike == asVehicle` là `true` vì hai tham chiếu trỏ cùng đối tượng.

Đóng gói xuất hiện ở trường `private int distance`: mã bên ngoài không thể trực tiếp gán `distance = -100`. Mọi cập nhật qua `move()` phải tuân thủ kiểm tra số bước không âm. `Math.addExact` còn phát hiện tràn số nguyên và ném `ArithmeticException`, thay vì âm thầm quay vòng giá trị.

Lưu ý về khả năng gọi tại thời điểm biên dịch: `asVehicle.move(1)` **không biên dịch** vì `Vehicle` không khai báo `move`; trong khi `asMovable.move(1)` hợp lệ. Điều này không mâu thuẫn với việc cả hai trỏ cùng đối tượng.

## 4. Phân biệt ràng buộc lúc biên dịch và lúc chạy

Java kiểm tra thao tác hợp lệ theo **kiểu tĩnh** của biểu thức, rồi dùng cơ chế phân phối động cho các **phương thức thể hiện có thể ghi đè** (virtual instance methods).

| Tình huống | Quyết định bởi | Kết quả |
| --- | --- | --- |
| Có được viết `reference.someMethod()` không? | Kiểu tĩnh và mức truy cập khi biên dịch | Gọi phương thức không có trong hợp đồng kiểu sẽ lỗi biên dịch. |
| Triển khai nào của phương thức **đã ghi đè** được chạy? | Lớp thực tế của đối tượng khi chạy | Hỗ trợ đa hình động. |
| Chọn phiên bản **nạp chồng** (overload) nào? | Kiểu tham số/biểu thức tại thời điểm biên dịch | Không tự chọn lại overload vì lớp thực tế của đối tượng. |
| Truy cập trường trùng tên do **che khuất** (field hiding)? | Kiểu tĩnh của biểu thức | Trường không được phân phối động như phương thức ghi đè. |
| Gọi phương thức `static` hoặc `private`? | Quy tắc của lớp/khả năng truy cập, không phải ghi đè động | `static` thuộc lớp; `private` không bị ghi đè. |

Ví dụ minh họa **trường bị che khuất** và **phương thức bị ghi đè**. Lưu vào `DispatchDemo.java`:

```java
class Parent {
    String label = "Parent.field";

    String label() {
        return "Parent.method";
    }
}

class Child extends Parent {
    String label = "Child.field";

    @Override
    String label() {
        return "Child.method";
    }
}

public class DispatchDemo {
    public static void main(String[] args) {
        Parent value = new Child();
        System.out.println(value.label);
        System.out.println(value.label());
    }
}
```

```bash
javac DispatchDemo.java
java DispatchDemo
```

```text
Parent.field
Child.method
```

`value.label` đọc trường được xác định theo kiểu `Parent`, còn `value.label()` gọi phương thức ghi đè của `Child`. Trong thiết kế thực tế, nên ưu tiên `private` fields và truy cập qua phương thức thay vì khai báo hai trường trùng tên như ví dụ.

Với **overloading**, nếu có `print(Object)` và `print(String)`, biểu thức biến có kiểu khai báo `Object text = "hi";` sẽ chọn `print(Object)` khi viết `print(text)`; chỉ nhìn đối tượng là `String` lúc chạy không làm đổi overload được chọn.

## 5. Class, abstract class và interface diễn tả quan hệ này thế nào?

### Class cụ thể

- Có thể tạo đối tượng bằng `new` (nếu constructor và điều kiện truy cập cho phép).
- Khai báo trường thể hiện, constructor và các phương thức thao tác trên dữ liệu; có thể hiện thực giao diện và kế thừa một lớp cha.
- Chọn phạm vi truy cập phù hợp (`private`, `protected`, `public`) để bảo vệ bất biến của đối tượng.

### Abstract class

- **Không thể** `new` trực tiếp một lớp `abstract`, nhưng phần trạng thái và hành vi của nó vẫn trở thành phần của đối tượng thuộc lớp con cụ thể.
- Có thể có trường thể hiện, constructor, phương thức đã triển khai, phương thức `abstract` cần lớp con cụ thể hiện thực.
- Hữu ích khi các kiểu con có **trạng thái chung và logic dùng chung**, như `Vehicle.name`, `Vehicle.distance`, `Vehicle.addDistance()`.
- Java chỉ cho phép một lớp cha trực tiếp (kể cả nếu lớp cha trừu tượng), nên tránh dùng kế thừa chỉ để tái sử dụng vài dòng code.

### Interface

- Mô tả một **hợp đồng khả năng**: đối tượng hỗ trợ những thao tác gì, ví dụ `Movable.move(int)`.
- Không có **trường thể hiện** hay constructor để lưu trạng thái riêng. Các trường khai báo trong interface mặc định là `public static final` (hằng số thuộc interface), **không phải trạng thái của mỗi đối tượng**.
- Có thể có phương thức `abstract`, `default`, `static`; Java 9+ còn hỗ trợ phương thức `private` phục vụ triển khai trong interface. Phương thức `default` có thân hàm nhưng vẫn không tạo ra trường thể hiện cho interface.
- Một lớp có thể `implements` nhiều interface. Một interface có thể `extends` nhiều interface.
- Hữu ích khi nhiều lớp khác họ cùng sở hữu một khả năng chung, ví dụ `Bicycle`, `Robot` cùng `implements Movable` nhưng quản lý trạng thái bằng các cấu trúc khác nhau.

**Điểm then chốt:** interface quy định cách **quan sát/gọi hành vi**; lớp cụ thể quyết định **lưu trạng thái thế nào và thực hiện hành vi ra sao**. Tuy vậy, interface không nhất thiết hoàn toàn “không có triển khai”: `default` method có thể chia sẻ logic dựa trên các thao tác của hợp đồng.

## 6. Trạng thái, bất biến và vòng đời của đối tượng

### Trạng thái nằm ở đâu?

- **Instance field** thuộc từng đối tượng: hai lần `new Bicycle("City")` tạo hai đối tượng có trường `distance` độc lập.
- **Static field** thuộc về lớp, được dùng chung theo ngữ cảnh lớp nạp, nên không đại diện cho trạng thái riêng của từng đối tượng.
- **Biến cục bộ/tham số** tồn tại trong phạm vi lần gọi và không tự động trở thành trạng thái lâu dài của đối tượng.
- Trường tham chiếu cũng là một phần trạng thái: ví dụ `private Engine engine;` lưu tham chiếu tới đối tượng khác. Trạng thái có thể gián tiếp phụ thuộc vào đồ thị các đối tượng liên quan.

### Hành vi bảo vệ bất biến (invariant)

**Bất biến** là điều kiện phải luôn đúng ở các thời điểm quan sát hợp lệ của đối tượng. Ví dụ với đồng hồ quãng đường: `distance >= 0`. Thiết kế tốt duy trì bất biến bằng cách:

1. Thiết lập trạng thái khởi đầu hợp lệ trong constructor.
2. Giữ trường nhạy cảm ở mức `private`.
3. Kiểm tra đầu vào trước khi cập nhật và xử lý lỗi rõ ràng.
4. Tập trung thay đổi qua phương thức có tên phản ánh nghiệp vụ, như `move()` hay `deposit()`.
5. Không trả ra một đối tượng mutable nội bộ theo cách cho phép người gọi sửa trạng thái vượt qua kiểm tra (nếu cần, trả về bản sao hoặc kiểu chỉ đọc).

Một phương thức không nhất thiết thay đổi trạng thái: `distance()` chỉ đọc; `kind()` cung cấp thông tin. Ngược lại, phương thức có thể gây tác dụng bên ngoài (ghi tệp, gọi mạng) mà không sửa trường thể hiện; vì vậy **hành vi rộng hơn việc thay đổi state**.

`final` cần được hiểu đúng: trường nguyên thủy `final int x` không thể gán lại; nhưng `final List<String> items` chỉ cố định **tham chiếu**, đối tượng danh sách vẫn có thể thay đổi nếu nó mutable.

### Hai tham chiếu và hai đối tượng

```java
Bicycle first = new Bicycle("A");
Bicycle alias = first;
Bicycle second = new Bicycle("A");
```

Đoạn trên sử dụng lớp `Bicycle` đã định nghĩa trong ví dụ trước, **không phải chương trình độc lập**.

- `first == alias` là `true`: cùng danh tính đối tượng; cập nhật qua một biến được quan sát qua biến còn lại.
- `first == second` là `false`: hai lần `new` tạo hai đối tượng riêng dù cùng tên và cùng quãng đường lúc đầu.
- `==` giữa hai biến tham chiếu so sánh **danh tính tham chiếu**; `equals()` so sánh theo hợp đồng của lớp. Nếu lớp không ghi đè `equals()`, hành vi mặc định từ `Object` vẫn so sánh danh tính.
- Gán `alias = second` chỉ đổi đối tượng mà biến `alias` trỏ tới; không tự thay đổi `first` hoặc `second`.

## 7. Từ mô hình bài toán đến thiết kế Java

Ví dụ hệ thống đặt hàng có thể phân chia trách nhiệm như sau:

| Góc nhìn | Ví dụ | Quyết định thiết kế |
| --- | --- | --- |
| Kiểu nghiệp vụ | `Order`, `PaymentMethod` | Xác định các thao tác hợp lệ và các hợp đồng rõ ràng. |
| Đối tượng thực tế | Một đơn hàng cụ thể, một đối tượng cổng thanh toán cụ thể | Mỗi thực thể có vòng đời và danh tính phù hợp. |
| Trạng thái | Mã đơn, các dòng hàng, trạng thái `CREATED/PAID/CANCELLED` | Đóng gói dữ liệu, hạn chế trạng thái không hợp lệ. |
| Hành vi | `addItem()`, `pay()`, `cancel()` | Kiểm tra chuyển trạng thái hợp lệ và phối hợp đối tượng khác. |

Chẳng hạn, một đơn hàng đã hủy không được thanh toán là một **quy tắc bất biến nghiệp vụ**. Nó nên được thực thi trong hành vi như `pay()`, thay vì cho mã bên ngoài gán trực tiếp `order.status = PAID`.

Khi quyết định dùng **abstract class** hay **interface**, hãy hỏi:

- Các kiểu có chia sẻ *state thực sự* và cách duy trì bất biến giống nhau không? Nếu có, một lớp cha trừu tượng có thể phù hợp.
- Các kiểu chỉ chia sẻ *khả năng* mà cách lưu dữ liệu khác nhau? Interface thường diễn đạt hợp đồng tốt hơn.
- Có thể dùng **composition** (chứa/ủy quyền một đối tượng) thay kế thừa để tránh phụ thuộc chặt vào cấu trúc lớp cha không?
- Đối tượng có cần mutable không? Nếu không, xem xét đối tượng bất biến: thiết lập đầy đủ state trong constructor, không có phương thức làm đổi state; `record` thuận tiện cho mô hình dữ liệu đơn giản nhưng **không tự làm mọi thành phần tham chiếu trở nên bất biến sâu**.

## 8. Các ngộ nhận và lỗi thường gặp

1. **“Biến có kiểu gì thì đối tượng bắt buộc thuộc đúng lớp đó.”** Sai: biến `Vehicle` có thể trỏ tới đối tượng `Bicycle`; điều kiện là tương thích kiểu.
2. **“Gán biến tham chiếu tạo bản sao đối tượng.”** Sai: gán thông thường chỉ sao chép giá trị tham chiếu; muốn sao chép trạng thái phải có chiến lược sao chép cụ thể.
3. **“Interface không liên quan đến trạng thái.”** Chưa đủ: interface không chứa trường thể hiện, nhưng hành vi do interface quy định hoàn toàn có thể đọc/sửa trạng thái của đối tượng hiện thực nó.
4. **“Abstract class không thể có constructor hoặc field.”** Sai: lớp trừu tượng có thể khởi tạo phần trạng thái được thừa hưởng; chỉ không thể tạo trực tiếp thể hiện của chính lớp trừu tượng.
5. **“Mọi thành viên đều đa hình lúc chạy.”** Sai: trường bị che khuất, phương thức `static`, `private` và nạp chồng có quy tắc khác ghi đè phương thức thể hiện.
6. **“Getter/setter cho mọi field là đã đóng gói tốt.”** Không nhất thiết: setter tự do có thể phá bất biến. Hành vi nghiệp vụ như `withdraw(amount)` diễn đạt và kiểm soát quy tắc rõ hơn `setBalance(value)`.
7. **“`final` reference nghĩa là object bất biến.”** Sai: tham chiếu không thể gán lại, nhưng trạng thái đối tượng được trỏ tới có thể thay đổi.
8. **“Object mutable tự động an toàn đa luồng.”** Sai: dùng chung một đối tượng mutable giữa các thread cần thiết kế đồng bộ, bất biến hoặc cơ chế thread-safe thích hợp. Ví dụ `Bicycle` phía trên **không** cam kết an toàn đa luồng.

## 9. Tự kiểm tra

**Câu 1.** Với `Vehicle v = new Bicycle("X");`, kiểu tĩnh và lớp runtime là gì?

**Đáp án:** kiểu tĩnh là `Vehicle`, lớp runtime là `Bicycle`. Chỉ gọi trực tiếp các thành viên hiển thị qua `Vehicle`, nhưng phương thức thể hiện được `Bicycle` ghi đè sẽ chạy phiên bản của `Bicycle`.

**Câu 2.** Nếu hai biến cùng trỏ một `Bicycle` và gọi `move(4)` qua biến thứ nhất, biến thứ hai đọc `distance()` thấy gì?

**Đáp án:** trạng thái đã tăng thêm 4 so với trước (nếu lời gọi thành công), vì chỉ có một đối tượng được chia sẻ.

**Câu 3.** Vì sao `Movable` không trực tiếp lưu `distance` riêng cho mỗi đối tượng?

**Đáp án:** interface không có instance fields; lớp hiện thực như `Bicycle` hoặc lớp cha `Vehicle` phải lưu trạng thái.

**Câu 4.** Nếu muốn thêm `Robot` có thể `move()` nhưng không phải phương tiện giao thông, nên dùng gì?

**Đáp án:** cho `Robot implements Movable` và quản lý trạng thái riêng. Không nên ép `Robot extends Vehicle` chỉ để lấy phương thức di chuyển.

**Ghi nhớ:** **kiểu** là hợp đồng sử dụng, **đối tượng** là thực thể mang danh tính, **trạng thái** là dữ liệu hiện tại của thực thể, và **hành vi** là các thao tác tác động lên hoặc quan sát thực thể đó. Tách bốn vai trò này giúp hiểu đa hình, đóng gói và lựa chọn giữa `class`, `abstract class`, `interface` khi thiết kế Java.
