# Lớp con cụ thể và trách nhiệm hoàn thiện triển khai trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao lớp con **cụ thể** (concrete class) phải cung cấp đủ triển khai cho những phương thức trừu tượng còn tồn tại trong hệ phân cấp kế thừa.
- Phân biệt phương thức do lớp con tự triển khai với phương thức cụ thể mà nó **kế thừa** từ lớp cha hoặc nhận được qua phương thức `default` của interface.
- Nhận biết khi nào một lớp con phải tiếp tục khai báo `abstract`, cách kiểm tra chữ ký `@Override` và các lỗi biên dịch thường gặp.
- Thiết kế lớp cha trừu tượng để mô tả phần chung, rồi triển khai hành vi biến thiên tại những lớp con phù hợp.

**Bối cảnh:** Đây là một bài về *lớp trừu tượng* (`abstract class`) của Java. Trọng tâm là trách nhiệm hoàn thiện việc triển khai khi một lớp con chuyển từ trạng thái trừu tượng sang có thể khởi tạo đối tượng.

## 2. Lớp con cụ thể là gì?

Một lớp không khai báo `abstract` là **lớp cụ thể**. Nếu lớp đó kế thừa một lớp trừu tượng, trình biên dịch chỉ chấp nhận khi mọi phương thức trừu tượng mà lớp phải thực hiện đều đã có triển khai cụ thể hợp lệ.

Ví dụ về ý tưởng:

~~~java
abstract class Vehicle {
    abstract void move();
}

class Bicycle extends Vehicle {
    @Override
    void move() {
        System.out.println("Pedaling");
    }
}
~~~

`Vehicle` quy định rằng mọi phương tiện con phải có hành vi `move()`, nhưng chưa chỉ ra cách thực hiện. `Bicycle` hoàn thiện hợp đồng đó bằng một phương thức có thân; do vậy `new Bicycle()` là hợp lệ. Ngược lại, `new Vehicle()` không hợp lệ vì `Vehicle` là lớp trừu tượng.

Trách nhiệm này xét trên **toàn bộ chuỗi kế thừa và các interface có liên quan**, không chỉ những phương thức trừu tượng được khai báo trực tiếp ở lớp cha gần nhất.

### Điều kiện cốt lõi

Một lớp con cụ thể cần:

1. Có triển khai hợp lệ cho tất cả phương thức trừu tượng còn chưa được giải quyết, bao gồm các hợp đồng kế thừa gián tiếp và phương thức trừu tượng từ interface.
2. Tuân thủ quy tắc ghi đè của Java: tên, danh sách tham số, kiểu trả về, phạm vi truy cập và ngoại lệ kiểm tra (`checked exception`).
3. Gọi được constructor phù hợp của lớp cha khi khởi tạo; các trường `final` cần được khởi tạo đúng quy tắc như ở mọi lớp Java.

Điều kiện thứ ba thuộc quy tắc khởi tạo đối tượng nói chung, còn hai điều kiện đầu là phần thiết yếu của việc hoàn thiện hợp đồng trừu tượng.

## 3. Ai có trách nhiệm triển khai và khi nào được hoãn lại?

Lớp trung gian được phép hoãn nghĩa vụ phương thức `abstract` khi chính nó vẫn khai báo `abstract`. Lớp đầu tiên không còn `abstract` phải có triển khai hợp lệ cho mọi nghĩa vụ còn thiếu trong toàn bộ hệ phân cấp; nếu chưa sẵn sàng, hãy giữ lớp đó là `abstract` thay vì để lại một khai báo lớp cụ thể không biên dịch.

Điều cần kiểm tra là **nghĩa vụ còn tồn tại**, không phải số lượng phương thức mà lớp cuối tự viết. Triển khai phù hợp có thể đã được cung cấp ở lớp tổ tiên hoặc qua phương thức `default` của interface; phần kế tiếp minh họa rõ trường hợp kế thừa một triển khai có sẵn.

## 4. Không nhất thiết lớp con cuối cùng tự viết mọi phương thức

Hợp đồng chỉ đòi hỏi một **triển khai cụ thể hợp lệ đã tồn tại trong hệ phân cấp**, không bắt buộc lớp con cuối cùng viết lại mọi phương thức. Ví dụ:

~~~java
interface Printer {
    void print();
}

abstract class BasePrinter implements Printer {
    @Override
    public void print() {
        System.out.println("Printed");
    }
}

class OfficePrinter extends BasePrinter {
    // Kế thừa triển khai print() có sẵn.
}
~~~

`OfficePrinter` là lớp cụ thể hợp lệ mặc dù không khai báo `print()`. Triển khai `public void print()` của `BasePrinter` đã đáp ứng giao diện `Printer`. Việc `BasePrinter` vẫn được khai báo `abstract` không làm triển khai `print()` trở thành trừu tượng.

Tương tự, một phương thức `default` phù hợp từ interface có thể cung cấp hành vi mặc định. Tuy nhiên, khi có xung đột giữa các phương thức `default` không liên quan, lớp thực thi phải giải quyết xung đột theo quy tắc kế thừa của Java.

Vì vậy, khi đọc lỗi thiếu triển khai, hãy lần ngược toàn bộ hệ phân cấp để tìm **phương thức trừu tượng chưa được đáp ứng**, thay vì chỉ đếm số lượng phương thức `@Override` trong lớp cuối.

## 5. Ví dụ hoàn chỉnh: hoàn thiện theo nhiều tầng kế thừa

Lưu toàn bộ đoạn sau vào tệp `Main.java`:

~~~java
interface Exportable {
    String format();

    default String fileExtension() {
        return ".txt";
    }
}

abstract class Document implements Exportable {
    private final String title;

    protected Document(String title) {
        this.title = title;
    }

    public final String title() {
        return title;
    }

    public abstract String body();

    public String preview() {
        return title + " | " + body();
    }
}

abstract class TextDocument extends Document {
    protected TextDocument(String title) {
        super(title);
    }

    @Override
    public final String format() {
        return "text/plain";
    }
}

final class Note extends TextDocument {
    private final String content;

    Note(String title, String content) {
        super(title);
        this.content = content;
    }

    @Override
    public String body() {
        return content;
    }
}

public class Main {
    public static void main(String[] args) {
        Document doc = new Note("Week 1", "Review contracts");
        Exportable export = (Exportable) doc;

        System.out.println(doc.preview());
        System.out.println(export.format());
        System.out.println(export.fileExtension());
    }
}
~~~

Biên dịch/chạy với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 Main.java
java Main
~~~

Kết quả chuẩn:

~~~text
Week 1 | Review contracts
text/plain
.txt
~~~

**Phân tích từng tầng:**

1. `Exportable` đặt ra phương thức trừu tượng `format()` và cung cấp sẵn phương thức `default fileExtension()`.
2. `Document` là lớp trừu tượng, chưa triển khai `format()` của interface; nó còn bổ sung hợp đồng `body()`. Bên cạnh đó, `title()` và `preview()` đã có thân; `preview()` gọi `body()` qua cơ chế đa hình.
3. `TextDocument` giải quyết `format()` bằng một triển khai `final` nhưng vẫn còn `body()` trừu tượng, vì vậy tiếp tục là lớp `abstract`.
4. `Note` triển khai `body()`. Nó **kế thừa** `format()`, `preview()` và `title()`, đồng thời sử dụng `fileExtension()` mặc định. Như vậy tất cả hợp đồng đều được hoàn thiện, cho phép tạo `new Note(...)`.
5. Biến `doc` có kiểu khai báo `Document` nhưng giữ đối tượng `Note`. Lời gọi `doc.preview()` chạy mã có sẵn ở `Document`, còn lời gọi `body()` bên trong được phân giải động đến triển khai của `Note`.

`final class Note` chỉ thể hiện lựa chọn ngăn kế thừa tiếp, **không phải** điều kiện để một lớp trở thành cụ thể. Viết `class Note extends TextDocument` cũng hợp lệ. Ngược lại, `final` không được dùng trên phương thức `abstract` vì một bên cấm ghi đè, một bên đòi hỏi lớp con cung cấp triển khai.

### Vì sao constructor lớp cha vẫn chạy?

`Document` là lớp trừu tượng nên không tạo trực tiếp qua `new Document(...)`, nhưng vẫn có constructor `protected Document(String)` để khởi tạo phần trạng thái chung. Khi chạy `new Note(...)`, chuỗi gọi constructor là `Note` → `TextDocument` → `Document`, rồi việc khởi tạo hoàn tất theo thứ tự từ lớp cha trở xuống. Lớp con cụ thể phải gọi constructor lớp cha phù hợp bằng `super(...)`, tường minh hoặc ngầm định.

**Lưu ý thiết kế:** Không nên gọi các phương thức có thể bị ghi đè từ constructor của lớp cha trừu tượng. Phương thức có thể dispatch xuống lớp con khi các trường của lớp con chưa được khởi tạo xong.

## 6. Ví dụ trực tiếp: kết hợp hợp đồng từ abstract class và interface

Lưu đoạn sau vào `Example2.java` (độc lập với `Main.java` ở trên):

~~~java
interface Describable {
    String describe();
}

abstract class Shape implements Describable {
    public abstract double area();

    public String kind() {
        return "shape";
    }
}

final class Square extends Shape {
    private final double side;

    Square(double side) {
        this.side = side;
    }

    @Override
    public double area() {
        return side * side;
    }

    @Override
    public String describe() {
        return "square: " + area();
    }
}

public class Example2 {
    public static void main(String[] args) {
        Shape shape = new Square(3.0);
        System.out.println(shape.kind());
        System.out.println(shape.describe());
    }
}
~~~

~~~bash
javac --release 17 Example2.java
java Example2
~~~

~~~text
shape
square: 9.0
~~~

`Shape` chưa thực hiện `Describable.describe()` và còn khai báo `area()` trừu tượng. Vì vậy `Square` phải đáp ứng **cả hai** phương thức. `kind()` có thân trong `Shape` nên được kế thừa trực tiếp; không cần ghi đè.

## 7. Ghi đè đúng chữ ký để thực hiện hợp đồng

Một phương thức chỉ hoàn thiện hợp đồng trừu tượng khi nó thật sự **override** phương thức được kế thừa. Cần kiểm tra:

| Thành phần | Yêu cầu khi override | Ví dụ/ý nghĩa |
| --- | --- | --- |
| Tên và tham số | Cùng chữ ký phù hợp (có xét quy tắc tương đương chữ ký Java) | `run()` khác `run(int)`; khai báo sau chỉ là overload. |
| Kiểu trả về | Cùng kiểu hoặc kiểu trả về hiệp biến hợp lệ đối với kiểu tham chiếu | Cha trả `Number`, con có thể trả `Integer`. |
| Phạm vi truy cập | Không được thu hẹp mức truy cập của phương thức được ghi đè | Cha `public` thì con phải `public`. |
| Checked exception | Không khai báo checked exception mới hoặc rộng hơn quy tắc cho phép | Cha `throws IOException`, con có thể bỏ `throws`. |
| `@Override` | Nên dùng để trình biên dịch kiểm tra ý định ghi đè | Sai tên/tham số sẽ được phát hiện ngay. |

Ví dụ về kiểu trả về hiệp biến:

~~~java
abstract class Provider {
    public abstract Number number();
}

class IntProvider extends Provider {
    @Override
    public Integer number() {
        return 42;
    }
}
~~~

`Integer` là lớp con của `Number`, nên `IntProvider.number()` thỏa hợp đồng và `IntProvider` là lớp cụ thể.

Ngược lại, đoạn **cố ý sai, không biên dịch** sau đây cho thấy lỗi overload:

~~~java
abstract class Base {
    abstract String read();
}

class Wrong extends Base {
    String read(int index) {
        return "item " + index;
    }
}
~~~

`read(int)` là một phương thức khác với `read()`; nó không hoàn thiện hợp đồng của `Base`. Trình biên dịch sẽ báo lỗi rằng `Wrong` chưa triển khai phương thức trừu tượng `read()`. Cách sửa là khai báo `@Override String read() { ... }` đúng chữ ký hoặc giữ `Wrong` là lớp `abstract` nếu muốn tiếp tục trì hoãn việc thực hiện.

Một lỗi khác là dùng mức truy cập yếu hơn:

~~~java
abstract class PublicBase {
    public abstract void execute();
}

// CỐ Ý SAI: không biên dịch.
class InvalidChild extends PublicBase {
    @Override
    protected void execute() {
        // ...
    }
}
~~~

`execute()` của cha là `public`, còn con viết `protected` nên vi phạm quy tắc override. Sửa thành `public void execute()`.

Lưu ý: Phương thức `private`, `static` hay `final` không thể được khai báo `abstract`; việc đặt `static` cùng tên trong lớp con cũng không thay thế một phương thức instance trừu tượng.

## 8. Quy trình kiểm tra một lớp con cụ thể

Khi định nghĩa `class X extends Y`, hãy thực hiện theo thứ tự:

1. **Liệt kê hợp đồng:** Xem các phương thức trừu tượng còn tồn tại từ `Y`, các lớp tổ tiên và các interface mà X phải đáp ứng.
2. **Tìm triển khai kế thừa:** Kiểm tra xem lớp cha đã cung cấp phương thức cụ thể hợp lệ hoặc interface đã có `default` thích hợp hay chưa.
3. **Triển khai phần còn thiếu:** Viết phương thức với chữ ký và quy tắc override chính xác; dùng `@Override` trên từng phương thức cần ghi đè.
4. **Quyết định abstract hay concrete:** Nếu vẫn có hợp đồng chưa được thực hiện, để lớp là `abstract`; nếu muốn khởi tạo được thì phải hoàn thiện toàn bộ.
5. **Biên dịch và kiểm thử hành vi:** Kiểm tra constructor, các lời gọi qua kiểu lớp cha/interface và đầu ra thực tế.

Bảng tóm tắt:

| Trường hợp | Khai báo hợp lệ? | Có tạo trực tiếp bằng `new`? |
| --- | --- | --- |
| Lớp cha trừu tượng còn phương thức chưa có thân | Có, nếu lớp vẫn là `abstract` | Không |
| Lớp con `abstract` chưa triển khai hết | Có | Không |
| Lớp con không `abstract` nhưng còn thiếu triển khai | Không: lỗi biên dịch | Không |
| Lớp con cụ thể tự triển khai đủ | Có | Có, nếu constructor truy cập được |
| Lớp con cụ thể kế thừa đủ triển khai từ tổ tiên | Có | Có, nếu constructor truy cập được |

### Lỗi phổ biến và cách xử lý

- **Chỉ triển khai phương thức ở lớp cha trực tiếp:** Quên phương thức trừu tượng từ tổ tiên hoặc interface. Hãy kiểm tra toàn bộ chuỗi `extends` và `implements`.
- **Nhầm overload với override:** Viết `calculate(int)` khi hợp đồng yêu cầu `calculate()`. Thêm `@Override` để phát hiện sai chữ ký.
- **Bỏ `public` khi thực hiện phương thức interface:** Phương thức trừu tượng thông thường của interface là `public`, vì vậy triển khai cũng cần `public`.
- **Cho rằng kế thừa từ lớp `abstract` thì lớp con cũng bắt buộc `abstract`:** Sai; lớp con có thể là cụ thể nếu mọi nghĩa vụ triển khai đã được đáp ứng.
- **Ghi đè lại phương thức đã đủ dùng:** Không cần thiết; có thể dùng trực tiếp triển khai kế thừa. Hãy override khi hành vi thực sự cần khác và phương thức cho phép ghi đè.
- **Gọi phương thức override trong constructor lớp cha:** Có thể đụng trạng thái lớp con chưa sẵn sàng; ưu tiên hoàn tất khởi tạo trước khi gọi hành vi đa hình.

## 9. Tự kiểm tra

Xét đoạn mã:

~~~java
interface Identified {
    String id();
}

abstract class Entity implements Identified {
    public abstract boolean valid();

    public String label() {
        return id();
    }
}

abstract class StoredEntity extends Entity {
    @Override
    public final boolean valid() {
        return true;
    }
}

class Order extends StoredEntity {
    @Override
    public String id() {
        return "ORD-1";
    }
}
~~~

**Câu hỏi:**

1. `StoredEntity` đã hoàn thiện phương thức nào? Vì sao nó vẫn có thể khai báo `abstract`?
2. `Order` phải triển khai những phương thức nào để là lớp cụ thể?
3. `new Order().label()` trả về gì?
4. Có thể ghi đè `valid()` trong `Order` không?

**Đáp án và giải thích:** `StoredEntity` đã triển khai `valid()`, vẫn là `abstract` vì chưa triển khai `id()` và vì Java cho phép khai báo lớp trừu tượng ngay cả khi không còn phương thức trừu tượng. `Order` chỉ cần triển khai `id()`: nó kế thừa `valid()` từ `StoredEntity` và `label()` từ `Entity`. Biểu thức `new Order().label()` trả `"ORD-1"`. `Order` không thể override `valid()` do phương thức này được khai báo `final`.

## 10. Ghi nhớ

**Lớp con cụ thể chịu trách nhiệm bảo đảm mọi hợp đồng trừu tượng đã có triển khai hợp lệ khi kết thúc chuỗi kế thừa.** Triển khai có thể đến từ chính lớp con, lớp tổ tiên hoặc phương thức mặc định thích hợp của interface; lớp trung gian `abstract` được phép hoãn trách nhiệm. Trình biên dịch kiểm tra nghĩa vụ này bằng quy tắc override, nhưng chất lượng hành vi của triển khai vẫn cần được xác minh bằng kiểm thử và thiết kế hợp đồng rõ ràng.
