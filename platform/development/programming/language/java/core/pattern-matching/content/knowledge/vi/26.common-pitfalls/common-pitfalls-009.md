# Nhầm record pattern với constructor pattern trong Java 21+

## 1. Lỗi tư duy thường gặp: cú pháp trông giống nhau nhưng làm việc khác nhau

Khi học Java 21, người mới dễ nhìn hai đoạn sau và tưởng rằng chúng đều là cách “gọi constructor” của record:

~~~java
record Point(int x, int y) {}

// TẠO đối tượng bằng lời gọi constructor.
Point point = new Point(2, 3);

// KHỚP và TÁCH dữ liệu của đối tượng đã tồn tại.
Object value = point;
if (value instanceof Point(int a, int b)) {
    System.out.println(a + b); // 5
}
~~~

Hai cú pháp có dấu ngoặc tròn và cùng tên `Point`, nhưng ý nghĩa hoàn toàn khác:

- `new Point(2, 3)` là **class instance creation expression**. Nó gọi constructor, tạo một đối tượng `Point`, thực hiện kiểm tra/chuẩn hóa trong constructor rồi trả về tham chiếu.
- `Point(int a, int b)` trong `instanceof` là **record pattern** (*deconstruction pattern*). Nó kiểm tra giá trị có khớp một record `Point` không, rồi ràng buộc các component vào biến `a` và `b`. Nó **không gọi constructor**, **không tạo Point mới**.
- Trong Java 21, **không có một loại “constructor pattern” tổng quát** cho mọi class chỉ vì class đó có constructor. Cú pháp `Type(...)` của record pattern dựa trên **khai báo record components**, không dựa trên danh sách tham số của một constructor tùy ý.

Bài này tập trung vào lỗi nhầm lẫn nói trên, cách phân biệt theo ngữ cảnh cú pháp, các lỗi compiler thường gặp, và cách sử dụng record pattern đúng trong thiết kế chương trình. Record patterns chính thức ổn định từ **Java 21 (JEP 440)** và có thể phối hợp với pattern matching trong `switch` (JEP 441).

## 2. Đối chiếu nhanh constructor và record pattern

| Tiêu chí | Constructor invocation | Record pattern |
| --- | --- | --- |
| Ví dụ | `new Point(2, 3)` | `Point(int a, int b)` |
| Mục đích | **Tạo** một instance mới | **Kiểm tra và tách** instance hiện có |
| Vị trí | Trong biểu thức tạo đối tượng, ví dụ bên phải `=` | Vị trí **pattern**: sau `instanceof`, trong `case` của `switch`, hoặc trong nested pattern |
| Nội dung ngoặc | **Giá trị/biểu thức đối số** khớp kiểu tham số constructor | **Component patterns** theo đúng thứ tự và kiểu component của record |
| Gọi constructor? | Có | Không |
| Tạo đối tượng record mới? | Có | Không |
| Dùng biến mới | Gán kết quả vào biến ở bên ngoài nếu muốn | Ràng buộc **pattern variables** khi match thành công |
| Cơ sở cấu trúc | Constructor hợp lệ và các tham số của nó | Danh sách **record components** khai báo trong record |
| Nếu không phù hợp | Lỗi biên dịch hoặc exception từ constructor | Lỗi biên dịch nếu pattern sai kiểu; nếu pattern hợp lệ nhưng không khớp dữ liệu thì nhánh không chạy |

Một cách nhớ đơn giản: **`new` tạo, `instanceof`/`case` kiểm tra và tách**. Tên record và các dấu ngoặc tương tự nhau không có nghĩa chúng sử dụng cùng cơ chế runtime.

## 3. Vì sao record patterns không phải lời gọi constructor?

Java record như:

~~~java
record Point(int x, int y) {}
~~~

khai báo một **cấu trúc dữ liệu** gồm hai component `x` và `y`. Compiler tạo canonical constructor, accessor `x()`/`y()`, và các thành viên thích hợp khác. Mã nguồn sau thao tác trên một đối tượng đã tồn tại:

~~~java
Point point = new Point(7, 4);

// Truy cập tường minh bằng accessor:
int a = point.x();
int b = point.y();

// Hoặc dùng record pattern (không tạo object mới):
if (point instanceof Point(var x, var y)) {
    System.out.println(x + y); // 11
}
~~~

Dạng record pattern có thể được hiểu về **ý nghĩa** như:

1. Xác định đối tượng đang xét phù hợp lớp record được yêu cầu hay không.
2. Deconstruct object bằng cách lấy các component của record.
3. So khớp từng component với pattern ở vị trí tương ứng.
4. Nếu toàn bộ khớp, ràng buộc biến pattern và tiếp tục trong phạm vi hợp lệ.

Mô tả này chỉ giúp hình dung, **không phải một phép biến đổi mã nguồn chính xác do compiler bắt buộc thực hiện**. Chi tiết đánh giá record patterns, trình tự truy xuất component và xử lý lỗi tuân theo Java Language Specification.

Điều quan trọng: **khi khớp record pattern, không có bước `new Point(...)`**. Một compact constructor dùng để validate `Point` chỉ chạy khi record được tạo qua constructor, không chạy lại mỗi lần record pattern khớp.

Các accessor của record có thể được người lập trình khai báo rõ và chứa hành vi. Vì vậy việc deconstruct có thể thực thi mã accessor và có thể gặp exception nếu accessor tự ném lỗi. **Không gọi constructor** không đồng nghĩa **không gọi mã nào** trong quá trình match.

## 4. Cú pháp đúng theo ngữ cảnh: biểu thức và pattern

### 4.1. Tạo đối tượng: dùng biểu thức đối số thực tế

~~~java
Point p = new Point(2, 3);          // Hai giá trị int.
Point q = new Point(p.x(), p.y());  // Có thể lấy giá trị từ object trước.
~~~

Biểu thức đối số trong `new Point(...)` phải tạo ra **giá trị** theo kiểu mà constructor yêu cầu. Câu lệnh này **sai**:

~~~java
// KHÔNG BIÊN DỊCH: var x, var y ở đây không phải đối số hợp lệ.
// Point p = new Point(var x, var y);
~~~

`var` không tự biến tham số constructor thành pattern. `var` chỉ có những vị trí cho phép suy luận kiểu theo cú pháp Java, ví dụ khai báo biến cục bộ và component pattern; không đặt `var x` làm một giá trị đối số.

### 4.2. So khớp object: dùng component patterns

~~~java
Object input = new Point(2, 3);
if (input instanceof Point(int x, int y)) {
    System.out.println("Tổng: " + (x + y)); // Tổng: 5
}
~~~

Ở đây `int x` và `int y` là **type patterns** dành cho component. Không hề có constructor `Point(int x, int y)` được gọi lần thứ hai. Nếu muốn compiler tự suy luận hai kiểu component:

~~~java
if (input instanceof Point(var x, var y)) {
    System.out.println(x * y); // 6
}
~~~

Compiler biết cả `x` và `y` của record `Point` là `int` nên biến pattern được suy luận kiểu `int`. Từ khóa `var` không tạo ra dynamic typing.

### 4.3. `Point(...)` không phải biểu thức tạo record

~~~java
// KHÔNG BIÊN DỊCH — record pattern không phải expression trả về Point.
// Point newPoint = Point(var x, var y);
~~~

Thay bằng:

~~~java
Point newPoint = new Point(2, 3);
~~~

Nếu mục đích là kiểm tra/tách dữ liệu, đặt record pattern vào vị trí pattern như `instanceof Point(var x, var y)` hoặc `case Point(var x, var y) -> ...`, không dùng nó như một expression độc lập.

## 5. Record pattern chỉ áp dụng với record class, không phải mọi constructor

Một class Java bình thường có constructor **không đồng nghĩa** nó có record components:

~~~java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}
~~~

Dạng sau **không biên dịch** trong Java 21:

~~~java
// KHÔNG BIÊN DỊCH: Person là class thường, không phải record.
// Object obj = new Person("An");
// if (obj instanceof Person(String name)) {
//     System.out.println(name);
// }
~~~

Lỗi compiler có thể là:

~~~text
deconstruction patterns can only be applied to records, Person is not a record
~~~

Dù constructor `Person(String name)` trông giống “mẫu có một chuỗi”, Java **không** tự suy ra cách deconstruct class `Person` từ constructor. Constructor nhận dữ liệu khi **tạo** object; nó không cung cấp một hợp đồng deconstruction tổng quát cho ngôn ngữ.

Cách xử lý class thường:

~~~java
Object obj = new Person("An");

if (obj instanceof Person person) {   // Type pattern thông thường.
    String name = person.name();      // Đọc qua phương thức.
    System.out.println(name);        // An
}
~~~

Ở đây `instanceof Person person` là type pattern, **không** phải record pattern. Nếu dữ liệu thuộc một mô hình value object thích hợp và bạn thực sự muốn deconstruction theo record components, có thể cân nhắc thiết kế `record Person(String name) {}`. Tuy nhiên không nên đổi một entity mutable hoặc một class mang invariant phức tạp thành record chỉ để dùng cú pháp gọn.

## 6. Constructor có thể validate; record pattern không validate bằng constructor lần nữa

Xét record có compact constructor:

~~~java
record Point(int x, int y) {
    public Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("Tọa độ phải không âm");
        }
    }
}
~~~

Khi tạo:

~~~java
Point ok = new Point(2, 3); // Hợp lệ.

// Lệnh sau ném IllegalArgumentException từ constructor:
// Point bad = new Point(-1, 3);
~~~

Khi so khớp một object đã được tạo hợp lệ:

~~~java
Object value = ok;
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
~~~

Constructor **không chạy lại**. Pattern chỉ kiểm tra và tách các component hiện có. Điều này quan trọng khi bạn dùng invariant như tọa độ không âm, giá trị không rỗng, hay số lượng dương:

- **Constructor của record** chịu trách nhiệm bảo vệ điều kiện tạo instance.
- **Record pattern** chịu trách nhiệm biểu diễn điều kiện khớp và lấy dữ liệu.
- **Domain service/handler** chịu trách nhiệm các quy tắc nghiệp vụ cần trạng thái bên ngoài.

Nếu bạn cần điều kiện bổ sung khi khớp, kết hợp pattern với `&&` hoặc `when`:

~~~java
Object input = new Point(4, 4);
if (input instanceof Point(int x, int y) && x == y) {
    System.out.println("Đường chéo"); // Đường chéo
}
~~~

Câu lệnh này không tạo một `Point(4,4)` mới; nó kiểm tra component của instance hiện có và điều kiện `x == y`.

## 7. Phân biệt lỗi compiler và pattern hợp lệ nhưng không khớp runtime

Bốn trường hợp đặc trưng:

### Lỗi A — sai số lượng component

~~~java
record Point(int x, int y) {}

// KHÔNG BIÊN DỊCH: Point có hai component, pattern chỉ cung cấp một.
// if (obj instanceof Point(int x)) { ... }
~~~

Đây là lỗi vì **số lượng component patterns** phải khớp số lượng record components, không phải compiler đang gọi một overload constructor có một tham số.

### Lỗi B — sai kiểu component

~~~java
// KHÔNG BIÊN DỊCH: component đầu có kiểu int.
// if (obj instanceof Point(String x, int y)) { ... }
~~~

`String x` không phải pattern áp dụng hợp lệ cho component `int`. Cách sửa:

~~~java
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
~~~

### Lỗi C — dùng record pattern trên class thường

~~~java
// KHÔNG BIÊN DỊCH: Person không phải record.
// if (obj instanceof Person(String name)) { ... }
~~~

Dùng `obj instanceof Person person` rồi gọi accessor của class.

### Lỗi D — dùng pattern làm đối số constructor

~~~java
// KHÔNG BIÊN DỊCH:
// new Point(var x, var y);
~~~

Dùng **giá trị** thực tế: `new Point(2, 3)` hoặc `new Point(existing.x(), existing.y())`.

Các lỗi này đều được quyết định **ở compile time**. Khác với tình huống hợp lệ nhưng không khớp:

~~~java
Object obj = "hello";

if (obj instanceof Point(var x, var y)) {
    System.out.println(x + y);
} else {
    System.out.println("Không phải Point"); // In dòng này.
}
~~~

Ở đây cú pháp và kiểu pattern hoàn toàn hợp lệ, nhưng instance có runtime class `String`, không phải `Point`. Java trả `false` cho `instanceof` và chạy nhánh `else`. **Không** có lỗi constructor.

## 8. Nested record pattern: không phải lời gọi nhiều constructor lồng nhau

Một ví dụ dễ gây nhầm lẫn hơn:

~~~java
record Point(int x, int y) {}
record Shipment(String id, Point destination) {}

Object value = new Shipment("S-1", new Point(1, 5));

if (value instanceof Shipment(var id, Point(var x, var y))) {
    System.out.println(id + " đến " + x + "," + y);
    // S-1 đến 1,5
}
~~~

Trong **biểu thức tạo object**:

~~~java
new Shipment("S-1", new Point(1, 5))
~~~

Java thực sự gọi constructor `Point` rồi constructor `Shipment` theo quá trình đánh giá biểu thức đối số.

Nhưng trong **record pattern**:

~~~java
Shipment(var id, Point(var x, var y))
~~~

Java không gọi constructor nào; nó deconstruct instance `Shipment` hiện có, rồi deconstruct component `destination` nếu component này khớp record `Point`. Mỗi cặp ngoặc trong pattern tương ứng với một **cấp dữ liệu record**, không phải constructor được gọi lại.

**Null ở record lồng:** Nếu `destination` là `null`, nested `Point(var x, var y)` không khớp. Điều này có thể khiến toàn bộ pattern `Shipment(var id, Point(...))` không khớp dù selector bên ngoài là một `Shipment` hợp lệ.

Có thể cung cấp case dự phòng:

~~~java
static String route(Object value) {
    return switch (value) {
        case Shipment(var id, Point(var x, var y)) ->
            id + " đến (" + x + "," + y + ")";
        case Shipment(var id, var destination) ->
            id + " thiếu điểm đến";
        case null -> "null";
        default -> "Kiểu khác";
    };
}
~~~

Nhánh record pattern cụ thể **đứng trước** nhánh tổng quát `Shipment(var id, var destination)`. Với `new Shipment("S-2", null)`, nhánh đầu không khớp, nhánh thứ hai vẫn có thể khớp và ràng buộc `destination == null`.

Chú ý: component pattern vô điều kiện như `var destination` có thể ràng buộc giá trị tham chiếu null trong một record pattern. Đừng nhầm điều đó với `null instanceof Point` — phép `instanceof` độc lập trên null trả về `false`.

## 9. `switch` pattern matching không tạo đối tượng mới

Trong Java 21, record patterns đặc biệt hữu ích khi phân nhánh dựa trên dữ liệu đã có:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Point(var x, var y) when x == y ->
            "Trên đường chéo: " + x;
        case Point(var x, var y) ->
            "Điểm (" + x + "," + y + ")";
        case null -> "null";
        default -> "Kiểu khác";
    };
}
~~~

Mỗi `case Point(...)` là **một pattern**, không phải lời gọi `new Point(...)`. Guard `when` chỉ được kiểm tra sau khi pattern đã khớp và pattern variables được ràng buộc.

- `case Point(var x, var y) when x == y`: chỉ chọn nếu là Point và hai tọa độ bằng nhau.
- `case Point(var x, var y)`: xử lý những Point còn lại.
- `case null`: xử lý selector null rõ ràng.
- `default`: xử lý giá trị không thuộc các kiểu trên.

**Thứ tự case quan trọng.** Nếu đặt nhánh `case Point(var x, var y)` không guard trước, nhánh cùng kiểu có guard phía sau có thể bị báo dominance vì đã bị che. Lựa chọn nhánh không phụ thuộc constructor nào từng được dùng để tạo Point, mà phụ thuộc **runtime value và điều kiện pattern**.

## 10. Generic record: tên kiểu cùng dấu ngoặc không xác nhận generic argument ở runtime

Cú pháp record patterns giống constructor còn dễ gây hiểu nhầm hơn khi record có generics:

~~~java
record Box<T>(T value) {}

// Khởi tạo object:
Box<String> box = new Box<>("Java");

// Tách component với kiểu đầu vào đã được biết:
if (box instanceof Box(var text)) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

Ở đây `new Box<>("Java")` gọi constructor, còn `Box(var text)` chỉ match và tách. Compiler suy luận `text` là `String` nhờ kiểu tĩnh `Box<String>` của `box`.

Nếu đầu vào chỉ là `Object`, không thể tùy ý kiểm tra tham số generic đã bị **type erasure**:

~~~java
// KHÔNG BIÊN DỊCH: Object -> Box<String> cần unchecked conversion.
// if (unknown instanceof Box<String>(var text)) { ... }
~~~

Dùng wildcard và kiểm tra component thật khi cần:

~~~java
Object unknown = new Box<>("Java");

if (unknown instanceof Box<?>(var item)
        && item instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

`Box<?>` cho phép kiểm tra record class mà không giả định tham số kiểu cụ thể; `item instanceof String` mới xác minh runtime type của component hiện có. Record pattern **không** phải một cơ chế tạo/gọi generic constructor, cũng không tự phục hồi generic argument bị erasure.

## 11. Ví dụ hoàn chỉnh Java 21+: tạo record và match record cạnh nhau

Lưu thành **`RecordConstructorPatternDemo.java`**:

~~~java
public class RecordConstructorPatternDemo {
    record Point(int x, int y) {
        public Point {
            if (x < 0 || y < 0) {
                throw new IllegalArgumentException("Tọa độ phải không âm");
            }
        }
    }

    record Shipment(String id, Point destination) {}

    static Point create(int x, int y) {
        return new Point(x, y); // Tạo mới: constructor chạy.
    }

    static String readPoint(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Tổng = " + (x + y); // Match/tách, không tạo Point.
        }
        return "Không phải Point";
    }

    static String describe(Object value) {
        return switch (value) {
            case Shipment(var id, Point(var x, var y)) ->
                id + " đến (" + x + "," + y + ")";

            case Shipment(var id, var destination) ->
                id + " thiếu điểm đến";

            case Point(var x, var y) when x == y ->
                "Trên đường chéo: " + x;

            case Point(var x, var y) ->
                "Điểm (" + x + "," + y + ")";

            case null -> "null";
            default -> "Kiểu khác";
        };
    }

    public static void main(String[] args) {
        Point p = create(2, 3);
        Point q = new Point(2, 3);

        System.out.println("Tạo: " + p);
        System.out.println("Bằng nhau: " + p.equals(q));
        System.out.println("Tách: " + readPoint(p));
        System.out.println("Match: " + describe(p));
        System.out.println("Chéo: " + describe(new Point(4, 4)));
        System.out.println("Lồng: " +
                describe(new Shipment("S-1", new Point(1, 5))));
        System.out.println("Thiếu: " +
                describe(new Shipment("S-2", null)));
        System.out.println("Null: " + describe(null));
        System.out.println("Khác: " + describe("hello"));

        try {
            new Point(-1, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi tạo: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 21 hoặc mới hơn**:

~~~bash
javac --release 21 RecordConstructorPatternDemo.java
java RecordConstructorPatternDemo
~~~

Đầu ra chính xác:

~~~text
Tạo: Point[x=2, y=3]
Bằng nhau: true
Tách: Tổng = 5
Match: Điểm (2,3)
Chéo: Trên đường chéo: 4
Lồng: S-1 đến (1,5)
Thiếu: S-2 thiếu điểm đến
Null: null
Khác: Kiểu khác
Lỗi tạo: Tọa độ phải không âm
~~~

**Tại sao đây là ví dụ phân biệt tốt?**

1. Hai lời gọi `new Point(2,3)` tạo ra hai instance có dữ liệu giống nhau; `equals()` của record đánh giá bằng nhau theo giá trị các component, **không** phải cùng object.
2. `readPoint(p)` dùng `instanceof Point(int x,int y)` để lấy hai số từ instance `p`, rồi tính tổng, không tạo đối tượng mới.
3. `describe` dùng `case Point(...)`, `case Shipment(...)` và `when` để phân loại cấu trúc dữ liệu theo record patterns.
4. `new Shipment("S-1", new Point(1,5))` là lời gọi constructor lồng nhau **thật**; `Shipment(var id, Point(var x, var y))` là record pattern lồng, **không** gọi constructor.
5. `Shipment("S-2", null)` cho thấy nested Point pattern có thể không khớp vì component null, trong khi pattern Shipment tổng quát vẫn xử lý được.
6. `new Point(-1,3)` ném exception **tại lúc khởi tạo** do compact constructor. Không có một pattern match nào cần chạy lại validation đó.

## 12. Bảng nhận diện lỗi và cách sửa

| Mã thường bị nhầm | Loại sai | Cách sửa hoặc giải thích đúng |
| --- | --- | --- |
| `new Point(var x, var y)` | Dùng cú pháp pattern làm đối số tạo object | `new Point(2,3)` hoặc các biểu thức trả `int` |
| `Point(var x,var y)` đứng độc lập bên phải phép gán | Dùng pattern như expression tạo object | `new Point(x,y)` nếu cần instance mới |
| `obj instanceof Person(String n)` với `Person` là class thường | Tưởng mọi constructor đều cho phép deconstruction | `obj instanceof Person p` rồi `p.name()` |
| `obj instanceof Point(int x)` | Sai số component so với record | `Point(int x,var ignored)` |
| `obj instanceof Point(String x,int y)` | Component `x` của Point là `int` | `Point(int x,int y)` hoặc `Point(var x,var y)` |
| `case Point(var x,var y)` được hiểu như lệnh tạo Point | Nhầm switch dispatch với object creation | Đây là kiểm tra và trích component của selector |
| `Shipment(var id, Point(...))` được hiểu là gọi 2 constructor | Nhầm nested patterns với nested creation | Đây là hai cấp destructuring, không có `new` |
| `default` được nghĩ là bắt null | Nhầm quy tắc null trong switch | Dùng `case null` nếu chấp nhận null |
| `Point(var x,var y)` luôn khớp mọi object | Bỏ qua kiểm tra record class | Phải đúng kiểu record và các component patterns đều khớp |
| Dùng `Box<String>(...)` từ `Object` và mong JVM kiểm tra generic argument | Quên type erasure | Dùng `Box<?>` rồi kiểm tra giá trị component cần thiết |

## 13. Bài tập tự kiểm tra

**Bài 1.** Cho:

~~~java
record User(String name, int age) {}
~~~

Trong hai cách viết `new User("An", 20)` và `User(var name, var age)`, cách nào tạo instance? Cách nào là pattern? Viết một `if` dùng pattern để in `name` khi đối tượng phù hợp.

**Bài 2.** Xét class thường:

~~~java
class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    String title() {
        return title;
    }
}
~~~

Vì sao `obj instanceof Book(String title)` sai trong Java 21, dù class có constructor `Book(String title)`? Hãy viết lại với type pattern.

**Bài 3.** Với `record Point(int x,int y) {}`, giải thích vì sao `new Point(3,4)` đúng nhưng `new Point(int x,int y)` sai trong ngữ cảnh biểu thức gọi constructor. Muốn trích `x` và `y` từ một instance `Point` có sẵn cần viết gì?

**Bài 4.** Với `record Delivery(String id, Point point) {}`, vì sao mẫu `Delivery(var id, Point(var x,var y))` có thể không khớp `new Delivery("D-1",null)` dù record ngoài là `Delivery` hợp lệ?

**Bài 5.** Nếu compact constructor của `Point` kiểm tra tọa độ không âm, việc chạy `if (p instanceof Point(var x,var y))` có gọi lại compact constructor không? Vì sao nên đặt invariant vào constructor thay vì kỳ vọng pattern tự kiểm tra?

**Gợi ý đáp án:**

~~~java
// Bài 1: Tạo instance:
User user = new User("An", 20);
// Bài 1: Khớp và tách:
Object obj = user;
if (obj instanceof User(var name, var age)) {
    System.out.println(name); // An
}

// Bài 2: Book là class thường, dùng type pattern:
if (obj instanceof Book book) {
    System.out.println(book.title());
}

// Bài 3:
Point p = new Point(3, 4);  // Constructor.
if (p instanceof Point(var x, var y)) {
    System.out.println(x + y); // 7
}
~~~

Bài 4: pattern `Point(...)` lồng trong không khớp null; có thể thêm một nhánh `Delivery(var id,var point)` chung để xử lý. Bài 5: **không** gọi lại constructor khi match; constructor bảo vệ điều kiện hợp lệ khi tạo record, còn record pattern dùng dữ liệu đã có để kiểm tra/tách.

## 14. Kết luận

- **Constructor expression** `new RecordType(values)` dùng **giá trị** để **tạo** object.
- **Record pattern** `RecordType(componentPatterns)` dùng **patterns** để **khớp và tách** object đã tồn tại.
- Java 21 không có “constructor pattern” tổng quát cho mọi class có constructor; record pattern dựa vào **record components**.
- Khi nhìn thấy `Point(...)`, hãy xét **ngữ cảnh**: sau `new` là tạo instance; sau `instanceof` hoặc trong `case` là pattern matching.
- Pattern không chạy lại canonical/compact constructor, nhưng vẫn áp dụng quy tắc kiểu, thứ tự component, nested matching, null và flow scoping.

### Tài liệu tham khảo

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): cú pháp và ngữ nghĩa deconstruction patterns cho record (Java 21).
- [JEP 395 — Records](https://openjdk.org/jeps/395): record components, constructor, accessor và value-oriented records.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): dùng record patterns trong switch, guard `when` và exhaustiveness.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [JLS 21, `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
