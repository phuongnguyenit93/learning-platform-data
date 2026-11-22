# Lớp trừu tượng có hoặc không có phương thức abstract trong Java

Trong Java, từ khóa `abstract` trên **lớp** và trên **phương thức** có hai ý nghĩa liên quan nhưng không đồng nhất:

- **Lớp `abstract`**: là lớp không thể được khởi tạo trực tiếp bằng `new TênLớp(...)`. Nó vẫn có thể chứa trạng thái, constructor, phương thức có thân, phương thức `static` và phương thức `final`.
- **Phương thức `abstract`**: chỉ khai báo chữ ký, không có thân phương thức; lớp con cụ thể phải cung cấp cách triển khai, trừ khi việc triển khai đã được thừa hưởng hợp lệ từ một lớp cha khác.

**Quy tắc cốt lõi:** Một lớp khai báo phương thức `abstract` thì chính lớp đó phải khai báo `abstract`; chiều ngược lại **không bắt buộc**. Nghĩa là lớp `abstract` có thể có **0, 1 hoặc nhiều** phương thức `abstract`.

| Trường hợp | Hợp lệ? | Hệ quả |
| --- | --- | --- |
| `abstract class A` chỉ có phương thức có thân | Có | Không được `new A()`, nhưng lớp con cụ thể có thể kế thừa toàn bộ hành vi |
| `abstract class A` có phương thức `abstract` | Có | Lớp con cụ thể phải hoàn thiện các phương thức trừu tượng còn thiếu |
| `class A` trực tiếp khai báo phương thức `abstract` | Không | Lỗi biên dịch: lớp phải là `abstract` |
| Lớp con không `abstract` còn kế thừa phương thức `abstract` chưa triển khai | Không | Lớp con phải triển khai hoặc được khai báo `abstract` |

## 1. Lớp abstract không khai báo phương thức abstract

Một lớp có thể cung cấp đầy đủ hành vi mặc định nhưng vẫn được thiết kế để **chỉ tồn tại thông qua lớp con**. Ví dụ, mọi chứng từ đều có mã và cách mô tả chung, nhưng ứng dụng chỉ tạo các loại chứng từ cụ thể.

Tạo tệp **NoAbstractMethodDemo.java**:

~~~java
abstract class Document {
    private final String code;

    protected Document(String code) {
        this.code = code;
    }

    public final String code() {
        return code;
    }

    public String describe() {
        return "Document: " + code;
    }
}

final class Receipt extends Document {
    Receipt(String code) {
        super(code);
    }
}

public class NoAbstractMethodDemo {
    public static void main(String[] args) {
        Document doc = new Receipt("R-01");
        System.out.println(doc.code());
        System.out.println(doc.describe());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac NoAbstractMethodDemo.java
java NoAbstractMethodDemo
~~~

Kết quả chính xác:

~~~text
R-01
Document: R-01
~~~

**Vì sao hợp lệ?** `Document` không khai báo một phương thức `abstract` nào. `Receipt` không phải ghi đè `code()` hay `describe()`, vì hai phương thức ấy đã có thân và được thừa hưởng. Constructor `Document(String)` vẫn được gọi thông qua `super(code)`; bản thân constructor không thể khai báo `abstract`.

Dù không có phương thức trừu tượng, `new Document("R-02")` vẫn **bị lỗi biên dịch** vì `Document` là lớp `abstract`. Một tham chiếu kiểu `Document` vẫn hoàn toàn hợp lệ: `Document doc = new Receipt("R-01");` — kiểu tham chiếu là lớp cha, đối tượng thật là `Receipt`.

Với lớp không chứa phương thức `abstract`, biểu thức `new Document("TMP") {}` cũng có thể hợp lệ: dấu `{}` tạo **lớp con ẩn danh** và khởi tạo lớp con đó, không phải tạo một thể hiện trực tiếp của `Document`. Cách này chỉ dùng được nếu constructor và các ràng buộc kế thừa cho phép.

**Khi nào hữu ích?**

- Muốn cấm việc khởi tạo kiểu nền quá chung chung và buộc ứng dụng dùng kiểu con có ý nghĩa nghiệp vụ.
- Muốn tập trung trường dữ liệu, constructor, kiểm tra bất biến và hành vi dùng chung cho một họ lớp.
- Muốn dành khả năng bổ sung điểm mở rộng ở lớp cha trong tương lai, nhưng hiện tại chưa cần một phương thức `abstract`.

Đừng dùng `abstract` chỉ để đặt các hàm tiện ích `static`: một lớp tiện ích `final` với constructor `private` thường thể hiện ý định rõ hơn.

## 2. Lớp abstract có phương thức abstract

Khi mọi lớp con phải tự định nghĩa một phần hành vi, phương thức `abstract` là **hợp đồng bắt buộc**. Phần hành vi đã biết có thể được viết sẵn trong lớp cha và gọi tới phương thức trừu tượng nhờ đa hình.

Tạo tệp **WithAbstractMethodDemo.java**:

~~~java
abstract class Figure {
    private final String name;

    protected Figure(String name) {
        this.name = name;
    }

    abstract double area();

    String summary() {
        return name + " area = " + area();
    }
}

final class Square extends Figure {
    private final double side;

    Square(double side) {
        super("Square");
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}

public class WithAbstractMethodDemo {
    public static void main(String[] args) {
        Figure figure = new Square(3);
        System.out.println(figure.summary());
        System.out.println(figure.area());
    }
}
~~~

~~~bash
javac WithAbstractMethodDemo.java
java WithAbstractMethodDemo
~~~

Kết quả chính xác:

~~~text
Square area = 9.0
9.0
~~~

Phương thức `Figure.area()` chỉ có chữ ký và dấu `;`, **không có `{ ... }`**. Lớp `Square` dùng `@Override` và cung cấp thân phương thức. Khi `summary()` gọi `area()` trên một đối tượng `Square`, Java thực thi `Square.area()` theo cơ chế **dynamic dispatch** (điều phối động). Đây cũng là cách lớp cha chia sẻ quy trình nhưng để lớp con quyết định một bước trong quy trình.

Ví dụ trên dùng quyền truy cập package-private cho `area()`; khi ghi đè, không được giảm mức truy cập. Trong API dùng giữa nhiều package, có thể chủ động khai báo `public abstract double area();` và ghi đè bằng `public double area()`.

## 3. Lớp con abstract và lớp con cụ thể

Một lớp con vẫn được khai báo `abstract` nếu chưa triển khai hết phương thức trừu tượng kế thừa. Đoạn sau chỉ minh họa quan hệ kế thừa; không phải chương trình có `main`:

~~~java
abstract class Writer {
    abstract String write();
}

abstract class NamedWriter extends Writer {
    String name() {
        return "named";
    }
    // Vẫn để lại write() chưa triển khai.
}

class PlainWriter extends NamedWriter {
    @Override
    String write() {
        return "ok";
    }
}
~~~

`NamedWriter` **không tự khai báo** phương thức `abstract` mới, nhưng **kế thừa** nghĩa vụ triển khai `write()` từ `Writer`; vì vậy nó vẫn phải là lớp `abstract`. `PlainWriter` là lớp cụ thể và đã triển khai `write()`, nên có thể khởi tạo.

Phân biệt chính xác hai câu sau:

- “Lớp này **không khai báo** phương thức abstract nào” không có nghĩa là toàn bộ cây kế thừa không còn phương thức abstract.
- “Lớp cụ thể có thể được tạo đối tượng” chỉ đúng khi mọi phương thức abstract được kế thừa đã có triển khai hợp lệ.

## 4. Những lỗi cần nhận diện

- Lớp khai báo trực tiếp một phương thức `abstract` thì bản thân lớp phải là `abstract`.
- Phương thức `abstract` chỉ có chữ ký và kết thúc bằng `;`; không được kèm thân `{ ... }`.
- Lớp con không `abstract` phải có triển khai hợp lệ cho mọi phương thức trừu tượng còn thiếu trong toàn bộ hệ phân cấp, kể cả nghĩa vụ kế thừa gián tiếp.
- Lớp trừu tượng có thể có phương thức thường, `static` hoặc `final` có thân; chi tiết về các tổ hợp modifier bị cấm thuộc bài chuyên về modifier.

## 5. Phân biệt với interface và cách chọn thiết kế

- **Abstract class**: phù hợp khi các lớp có quan hệ “là một loại của”, cần chia sẻ **trạng thái**, **constructor**, hành vi chung hoặc một số bước bắt buộc phải viết lại. Mỗi lớp Java chỉ được `extends` trực tiếp **một lớp**.
- **Interface**: phù hợp khi cần công bố một **khả năng/hợp đồng** mà nhiều lớp thuộc các hệ phân cấp khác nhau đều có thể đáp ứng. Một lớp có thể `implements` nhiều interface. Interface có thể chứa phương thức `abstract` (thường được ngầm hiểu là `public abstract`), đồng thời có `default`, `static` và `private` method theo quy tắc Java hiện đại.

Không phải cứ có phương thức abstract là cần chọn lớp cha abstract: nếu không cần chia sẻ trạng thái hay constructor và chỉ cần ràng buộc khả năng, interface thường đơn giản hơn. Nếu quan hệ kế thừa khiến lớp con phụ thuộc quá chặt vào chi tiết lớp cha, cân nhắc **composition** (chứa và ủy quyền cho đối tượng khác).

**Câu hỏi tự kiểm tra:** Một lớp `abstract` chỉ có phương thức có thân có hợp lệ không? **Có.** Lớp con cụ thể của nó có bắt buộc `@Override` phương thức nào không? **Không**, nếu không có nghĩa vụ abstract kế thừa khác. Thêm một phương thức `abstract` vào lớp cha thì sao? **Lớp con cụ thể phải có triển khai hợp lệ**, trực tiếp hoặc kế thừa từ lớp trung gian đã triển khai.

**Điểm cần nhớ:** `abstract class` nói về **khả năng tạo đối tượng trực tiếp** và vai trò lớp nền; `abstract method` nói về **phần hành vi chưa được triển khai**. Hai khái niệm liên quan, nhưng lớp `abstract` không bắt buộc phải sở hữu phương thức `abstract`.
