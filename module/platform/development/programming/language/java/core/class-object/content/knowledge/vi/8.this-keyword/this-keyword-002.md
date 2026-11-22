# Dùng `this` để phân biệt trường và tham số trùng tên trong Java

Trong Java, **`this`** là biểu thức tham chiếu đến **đối tượng hiện tại** trong ngữ cảnh instance thích hợp. Một cách sử dụng thường gặp nhất là viết **`this.field`** để phân biệt **trường (field) của đối tượng** với **tham số (parameter) hoặc biến cục bộ (local variable) cùng tên**. Nhờ đó, constructor và phương thức có thể gán đúng trạng thái cho đối tượng thay vì vô tình gán một biến cho chính nó.

Bài học thuộc Java Core — *class-object*, tập trung vào việc phân giải tên và thiết lập dữ liệu cho **đúng instance**. Các ví dụ chạy độc lập yêu cầu **Java 17 trở lên**.

## 1. Vấn đề: một tên, hai biến khác nhau

Xét lớp có một trường tên `name` và constructor cũng nhận tham số tên `name`:

~~~java
class Student {
    private String name;

    Student(String name) {
        name = name;
    }
}
~~~

Đoạn mã này **biên dịch được**, nhưng **không gán giá trị cho trường `name`**. Trong thân constructor, tham số `name` đang nằm trong phạm vi và **che khuất (shadow)** trường cùng tên. Cả hai `name` trong `name = name;` đều được hiểu là **tham số**. Về tác dụng, câu lệnh tự gán tham số cho chính nó; trường của đối tượng vẫn giữ giá trị mặc định `null`.

Cách viết đúng:

~~~java
class Student {
    private String name;

    Student(String name) {
        this.name = name;
    }
}
~~~

Trong `this.name = name;`:

- **`this`** là tham chiếu tới đối tượng `Student` đang được khởi tạo.
- **`this.name`** là **trường `name` của đối tượng đó**.
- **`name` ở vế phải** là **tham số constructor** đang nhận giá trị từ đối số bên gọi.
- Dấu `=` gán **giá trị của tham số** vào **trường**.

Đây là khác biệt giữa *gán trạng thái cho object* và *gán vào biến cục bộ của lời gọi*.

## 2. Trường, tham số và biến tham chiếu là ba khái niệm khác nhau

Ví dụ lời gọi:

~~~java
Student an = new Student("An");
~~~

Khi chạy, có thể hình dung:

~~~text
Biến tham chiếu an
        |
        v
  đối tượng Student
  +------------------+
  | field name: "An" |
  +------------------+

Lời gọi Student("An")
  tham số name = "An"  (chỉ nằm trong lời gọi constructor)
          |
          +--- this.name = name
                    |
                    v
                field của object
~~~

Trong ví dụ này, **`an`** là biến tham chiếu ở nơi gọi, **tham số `name`** là biến riêng của lời gọi constructor, còn **`this.name`** là trường thuộc đối tượng mà `an` tham chiếu sau khi khởi tạo thành công.

Tham số được sử dụng trong lúc phương thức/constructor chạy. Trường instance tiếp tục là phần trạng thái của object sau khi lời gọi hoàn tất. Hai object khác nhau có thể có cùng trường tên `name` nhưng **giữ hai giá trị riêng**.

| Cách viết | Ý nghĩa khi có tham số cùng tên |
| --- | --- |
| `name` | Tham số hoặc biến cục bộ gần nhất mang tên `name` |
| `this.name` | Trường instance `name` của đối tượng hiện tại |
| `other.name` | Trường `name` của đối tượng mà `other` tham chiếu, nếu quy tắc truy cập cho phép |
| `Student student` | Biến tham chiếu chứa tham chiếu tới đối tượng, **không phải** field `name` |
| `this` | Bản thân tham chiếu đến đối tượng hiện tại, **không phải** từ khóa “gọi constructor” khi đứng riêng |

**Chú ý:** khi không có tên gần hơn che khuất, Java cho phép dùng `name` thay cho `this.name` trong phương thức instance. `this` đặc biệt cần thiết khi có trùng tên hoặc muốn làm rõ rằng đang truy cập trạng thái của object.

## 3. Ví dụ hoàn chỉnh: lỗi `name = name` và cách sửa

Tạo tệp **`ThisShadowingDemo.java`**:

~~~java
class BrokenProfile {
    private String name;

    BrokenProfile(String name) {
        name = name; // Sai logic: tham số tự gán cho chính nó.
    }

    String name() {
        return name;
    }
}

class StudentProfile {
    private String name;
    private int level;

    StudentProfile(String name, int level) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (level < 1) {
            throw new IllegalArgumentException("Cấp độ phải dương");
        }
        this.name = name;
        this.level = level;
    }

    void rename(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name;
    }

    void promoteTo(int level) {
        if (level < this.level) {
            throw new IllegalArgumentException("Không được giảm cấp");
        }
        this.level = level;
    }

    String summary() {
        return name + " (level " + level + ")";
    }
}

public class ThisShadowingDemo {
    public static void main(String[] args) {
        BrokenProfile broken = new BrokenProfile("An");
        System.out.println("Broken: " + broken.name());

        StudentProfile an = new StudentProfile("An", 1);
        StudentProfile binh = new StudentProfile("Binh", 2);

        an.rename("Anh");
        an.promoteTo(3);

        System.out.println(an.summary());
        System.out.println(binh.summary());

        try {
            an.promoteTo(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
        System.out.println(an.summary());
    }
}
~~~

Tại thư mục chứa tệp, thực hiện:

~~~bash
javac -encoding UTF-8 ThisShadowingDemo.java
java ThisShadowingDemo
~~~

**Stdout chính xác:**

~~~text
Broken: null
Anh (level 3)
Binh (level 2)
Từ chối: Không được giảm cấp
Anh (level 3)
~~~

### Từng bước lý giải kết quả

1. `new BrokenProfile("An")` truyền `"An"` vào tham số `name`. Câu `name = name;` chỉ gán lại tham số; trường `BrokenProfile.name` chưa được thiết lập và mặc định là `null`. Khi ghép chuỗi để in, Java biểu diễn giá trị này thành chữ `null`.
2. `new StudentProfile("An", 1)` kiểm tra và gán `this.name = name`, `this.level = level` vào đúng instance đầu tiên.
3. `new StudentProfile("Binh", 2)` tạo **instance thứ hai**, với hai trường riêng, không dùng chung với instance An.
4. `an.rename("Anh")` gán tham số `name` mới vào **trường của instance An**. Việc này không đổi tên của Bình.
5. `an.promoteTo(3)` so sánh **tham số** `level = 3` với **trường hiện tại** `this.level = 1`, rồi cập nhật trường thành 3.
6. `an.promoteTo(0)` ném ngoại lệ trước phép gán, nên trường `this.level` vẫn là 3.

Ở ví dụ này, `this` vừa giúp phân biệt trùng tên vừa giúp đọc đúng ý điều kiện `level < this.level`: bên trái là **cấp độ muốn đặt**, bên phải là **cấp độ hiện có**.

## 4. Phân tích chính xác biểu thức `this.field = parameter`

Mẫu thường gặp trong constructor hoặc setter:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }
}
~~~

Đây là **định nghĩa lớp minh họa**, không có `main`. Đối với dòng:

~~~java
this.width = width;
~~~

hãy đọc từ trái sang phải:

1. `this`: đối tượng `Rectangle` đang được khởi tạo.
2. Dấu `.`: truy cập thành viên của đối tượng.
3. `width` phía trái: trường `width` của object.
4. Dấu `=`: phép gán.
5. `width` phía phải: tham số constructor kiểu `int` được đưa vào lúc `new Rectangle(...)`.

Không nên nói rằng `this` làm thay đổi **giá trị của tham số**; nó làm rõ **đích của phép gán**. Kiểu của trường và giá trị biểu thức vế phải vẫn phải tương thích theo luật gán của Java.

### Vì sao đặt tham số trùng tên field lại phổ biến?

Nó tạo quy ước nhất quán giữa API và trạng thái:

~~~java
Book(String title, String author) {
    this.title = title;
    this.author = author;
}
~~~

Chỉ cần nhìn header và các phép gán, người đọc hiểu ngay đối số nào khởi tạo field nào. Thay vì đổi tham số thành `newTitle` hoặc `inputTitle` để tránh trùng tên, nhiều dự án Java chọn giữ tên tự nhiên và dùng `this.title` ở phía field.

**Đây là một quy ước thiết kế, không phải cú pháp bắt buộc.** Tên tham số và tên trường không nhất thiết phải giống nhau.

## 5. Biến cục bộ cũng có thể che field

Không chỉ tham số: một **biến cục bộ** được khai báo trong một phạm vi cũng có thể che trường cùng tên.

Tạo tệp hoàn chỉnh **`ThisLocalVariableDemo.java`**:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void inspect() {
        int value = 100;
        System.out.println("local=" + value);
        System.out.println("field=" + this.value);
    }

    void add(int amount) {
        this.value = Math.addExact(this.value, amount);
    }

    int value() {
        return this.value;
    }
}

public class ThisLocalVariableDemo {
    public static void main(String[] args) {
        Counter first = new Counter(10);
        Counter second = new Counter(20);

        first.inspect();
        first.add(5);
        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
    }
}
~~~

Chạy:

~~~bash
javac ThisLocalVariableDemo.java
java ThisLocalVariableDemo
~~~

Stdout:

~~~text
local=100
field=10
first=15
second=20
~~~

Trong `inspect()`, biến cục bộ `int value = 100;` che tên trường `value` của object. Vì vậy:

- `System.out.println(value)` đọc **biến cục bộ** 100.
- `System.out.println(this.value)` đọc **trường** của `first`, ban đầu là 10.
- Sau `first.add(5)`, chỉ trường của `first` thành 15; trường của `second` vẫn là 20.

Trong `add(int amount)`, không có tham số `value` cùng tên, nên `this.value` không bắt buộc về mặt phân giải tên; có thể viết `value = Math.addExact(value, amount)`. Viết `this.value` vẫn hợp lệ và giúp thể hiện rõ trạng thái instance.

**Lưu ý phạm vi:** một biến cục bộ không được khai báo trùng tên với tham số đang có hiệu lực trong cùng phạm vi một phương thức theo cách gây trùng khai báo; ví dụ `void f(int x) { int x = 1; }` là lỗi compile. Điều đó khác với trường instance cùng tên tham số, vốn **được phép** và là tình huống `this` giải quyết.

## 6. Khi không dùng `this`, Java tìm tên nào?

Giả sử có:

~~~java
class Example {
    private int points;

    Example(int points) {
        this.points = points;
    }

    int points() {
        return points;
    }

    void setPoints(int points) {
        this.points = points;
    }
}
~~~

Đây là lớp minh họa. Các ngữ cảnh tên rất khác nhau:

| Vị trí | Viết `points` nghĩa là | Viết `this.points` nghĩa là |
| --- | --- | --- |
| Trong constructor `Example(int points)` | Tham số constructor | Trường của instance đang tạo |
| Trong `points()` không có local/parameter trùng tên | Trường của instance hiện tại | Cùng trường đó |
| Trong `setPoints(int points)` | Tham số của phương thức | Trường của instance nhận lời gọi |
| Trong một phương thức có `int points = 5;` | Biến cục bộ | Trường của instance |

Java có các quy tắc **phạm vi (scope)** và **che khuất tên (shadowing)**. Một tham số hoặc local variable hợp lệ có thể che tên trường được nhìn thấy bằng tên đơn giản. Thêm `this.` chuyển cách truy cập thành **biểu thức chọn thành viên** của đối tượng hiện tại.

Đừng rút gọn thành “Java luôn ưu tiên tham số hơn mọi thứ” cho tất cả loại tên và phạm vi. Với kiểu lồng nhau, kế thừa, trường static và các dạng định danh khác còn có quy tắc riêng. Đối với bài này, quan hệ cần nắm chắc là **tham số hoặc local cùng tên che instance field** khi dùng tên trần.

## 7. `this` ở constructor và ở phương thức instance

Trong constructor, `this` chỉ object **đang được khởi tạo**:

~~~java
StudentProfile(String name, int level) {
    this.name = name;
    this.level = level;
}
~~~

Trong phương thức instance, `this` chỉ object **nhận lời gọi hiện tại**:

~~~java
void rename(String name) {
    this.name = name;
}
~~~

Hai biến `an` và `binh` cùng có thể gọi `rename`, nhưng mỗi lời gọi có một **receiver object** riêng:

~~~java
an.rename("Anh");      // this trỏ đến object mà an tham chiếu
binh.rename("Bình");   // this trỏ đến object mà binh tham chiếu
~~~

Đó là lý do một phương thức được định nghĩa trong lớp nhưng thao tác được trên **nhiều bản trạng thái độc lập**.

Có thể viết `this.name` nhiều lần trong các constructor/phương thức của lớp, nhưng `this` **không phải biến toàn cục cố định**: giá trị tham chiếu của nó phụ thuộc đối tượng đang được sử dụng trong từng lời gọi.

## 8. `this` không bắt buộc ở mọi lần truy cập trường

Khi **không có biến gần hơn cùng tên**, code sau có cùng ý nghĩa về việc đọc trường:

~~~java
int getLevel() {
    return level;
}

int getLevelExplicitly() {
    return this.level;
}
~~~

Cả hai là **đoạn phương thức minh họa** trong lớp có instance field `level`. Nếu trong thân phương thức xuất hiện một tham số hoặc local `level`, cách viết tên trần có thể đổi nghĩa; `this.level` vẫn nêu rõ field của object.

Hai phong cách thường gặp:

- Chỉ viết `this.` **khi có che khuất** hoặc khi cần làm rõ receiver.
- Nhất quán dùng `this.` cho **mọi instance field** để tăng khả năng phân biệt field và local.

Java chấp nhận cả hai. Dự án nên chọn quy ước dễ đọc và nhất quán, thay vì kết luận một phong cách là bắt buộc đối với toàn bộ ứng dụng.

### Đổi tên tham số có giải quyết vấn đề không?

Có:

~~~java
void rename(String newName) {
    this.name = newName;
}
~~~

Nếu không có local `name` khác, cách viết `name = newName;` cũng có thể gán đúng field. Nhưng quy ước `this.name = name` thường dễ so sánh giữa tên trường và tham số, đặc biệt với constructor có nhiều trường.

Không nên lạm dụng tên `this` như một tên biến: `this` là **từ khóa đặc biệt**, không phải identifier hợp lệ để tự khai báo biến.

## 9. `this` và `static`: không có receiver instance

Một phương thức `static` thuộc ngữ cảnh lớp chứ không có một object hiện tại để dùng `this`.

Ví dụ **cố ý sai**:

~~~java
class Invalid {
    private int value;

    static void update(int value) {
        this.value = value; // Lỗi biên dịch: không dùng this ở static context.
    }
}
~~~

Nếu thao tác cần cập nhật field của một object, hãy có tham chiếu object cụ thể:

~~~java
class Valid {
    private int value;

    static void update(Valid target, int value) {
        if (target == null) {
            throw new IllegalArgumentException("target là null");
        }
        target.value = value;
    }

    void update(int value) {
        this.value = value;
    }
}
~~~

Đây là **định nghĩa lớp minh họa**, không có `main`. Hai phương thức `update` khác chữ ký vì một cái nhận `(Valid, int)`, cái kia nhận `(int)`. Trong phương thức static, `target.value` truy cập field của object được đưa vào. Trong phương thức instance, `this.value` truy cập field của receiver.

Field `static` nên được truy cập bằng **tên lớp** khi hợp lý; `this` không phải cách thể hiện trạng thái lớp dùng chung. Ví dụ `Counter.total` khác với `this.value`.

## 10. `this.field` khác `this(...)`

Hai cú pháp dễ gây nhầm:

| Cú pháp | Mục đích | Ví dụ |
| --- | --- | --- |
| `this.field` | Chọn field của object hiện tại | `this.name = name;` |
| `this.method(...)` | Gọi một instance method của object hiện tại | `this.rename("An");` |
| `this(...)` | Gọi constructor khác **cùng lớp** | `this(name, 0);` |
| `super(...)` | Gọi constructor lớp cha | `super(name);` |
| `super.field` | Chọn field của superclass khi truy cập hợp lệ | `super.value` |

Một ví dụ constructor ủy quyền (minh họa, không có `main`):

~~~java
class Product {
    private String name;
    private int quantity;

    Product(String name) {
        this(name, 0);
    }

    Product(String name, int quantity) {
        this.name = name;
        this.quantity = quantity;
    }
}
~~~

`new Product("Sách")` tạo **một object**, gọi constructor một tham số rồi ủy quyền sang constructor hai tham số trên **cùng object**. Câu `this(name, 0)` không gán trường `name`; chính dòng `this.name = name` trong constructor hai tham số mới làm điều đó.

Trong **Java 17**, lời gọi tường minh `this(...)` hoặc `super(...)` trong constructor phải đứng đầu thân constructor tương ứng. Không tự gọi `this(...)` đệ quy vô hạn hoặc viết `this(...)` như một lời gọi phương thức thông thường ở giữa `setName`.

## 11. `this` và field bị che trong kế thừa

Ngoài tham số che field, lớp con cũng có thể khai báo một field **cùng tên** với field của lớp cha. Khi đó `this.field` và `super.field` có thể khác nhau, tùy lớp khai báo mà biểu thức đang nằm trong và quy tắc truy cập.

Tạo tệp **`ThisAndSuperDemo.java`**:

~~~java
class ParentBox {
    protected int size = 10;
}

class ChildBox extends ParentBox {
    private int size = 20;

    ChildBox(int size) {
        this.size = size;
    }

    void printSizes() {
        System.out.println("child=" + this.size);
        System.out.println("parent=" + super.size);
    }
}

public class ThisAndSuperDemo {
    public static void main(String[] args) {
        ChildBox box = new ChildBox(30);
        box.printSizes();
    }
}
~~~

~~~bash
javac ThisAndSuperDemo.java
java ThisAndSuperDemo
~~~

Stdout:

~~~text
child=30
parent=10
~~~

Trong `ChildBox(int size)`, tham số `size` che tên field của lớp con. `this.size = size;` gán trường `ChildBox.size` thành 30. `ParentBox.size` vốn có initializer 10 và vẫn giữ 10, nên `super.size` đọc được 10.

**Không nên cố ý che field trong kế thừa nếu không có lý do rõ ràng**: nó tạo hai trường vật lý/khái niệm mang cùng tên, dễ gây nhầm lẫn. Ví dụ chỉ để phân biệt chính xác `this` và `super`; trong thiết kế thực tế, thường nên dùng tên field không gây tranh chấp.

## 12. Dùng `this` khi setter phải kiểm tra giá trị mới

Nếu getter hoặc setter cần thao tác với trường có cùng tên tham số, `this` giúp mô tả rõ **giá trị cũ** và **giá trị được yêu cầu**.

~~~java
class InventoryItem {
    private int quantity;

    InventoryItem(int quantity) {
        setQuantity(quantity);
    }

    void setQuantity(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("Số lượng không được âm");
        }
        this.quantity = quantity;
    }

    void increase(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số cộng phải dương");
        }
        this.quantity = Math.addExact(this.quantity, quantity);
    }
}
~~~

Đây là **định nghĩa lớp minh họa**, không có `main`. Trong `setQuantity`, điều kiện kiểm tra **tham số mới** `quantity`, sau đó cập nhật field `this.quantity`. Trong `increase`, `this.quantity` phía phải là **số lượng hiện có**, còn tham số `quantity` là **lượng muốn cộng**.

Lưu ý việc gọi một phương thức instance có thể bị override từ constructor có thể nguy hiểm nếu phương thức ấy không được kiểm soát, vì object chưa hoàn tất khởi tạo. Ở ví dụ `InventoryItem`, lớp không có subclass hay override; trong API hướng kế thừa nên thận trọng với chiến lược này và ưu tiên khởi tạo dữ liệu một cách an toàn.

### Vì sao phép gán đúng chưa đủ để class đúng?

Ngay cả khi viết đúng `this.quantity = quantity;`, một constructor vẫn phải bảo đảm **giá trị hợp lệ** theo invariant của lớp. Không nên bỏ qua kiểm tra chỉ vì đã sửa được lỗi trùng tên. Hai lỗi khác nhau cần tách biệt:

1. **Sai receiver hoặc sai đích gán:** `quantity = quantity;`.
2. **Sai dữ liệu nghiệp vụ:** `this.quantity = -10;` khi lớp yêu cầu số lượng không âm.

Một lớp tốt cần giải quyết cả hai.

## 13. Một số chi tiết cần nhớ về biểu thức `this`

- Trong phương thức instance hoặc constructor của lớp thường, `this` tham chiếu object hiện tại. Nó **không tạo object mới** và không phải là một từ đồng nghĩa với tên lớp.
- Có thể truyền `this` làm đối số đến phương thức khác hoặc trả về `this` trong phương thức instance khi kiểu tương thích. Nhưng **không nên làm lộ `this` từ constructor** cho các đối tượng/luồng khác trước khi khởi tạo hoàn chỉnh.
- Bên trong **lambda**, `this` (khi hợp lệ) vẫn chỉ instance của ngữ cảnh bao ngoài, không chỉ một “object lambda” mới.
- Bên trong **anonymous inner class**, `this` có thể chỉ instance của chính lớp vô danh; khi cần tham chiếu instance của lớp ngoài, Java có cú pháp `OuterClass.this` trong ngữ cảnh hợp lệ.
- Không thể viết `this` trong một **static method** hoặc static initializer vì ở đó không có receiver object hiện tại.

Các chi tiết này giải thích vì sao `this` có ngữ nghĩa phụ thuộc **ngữ cảnh**. Tuy nhiên, với việc phân biệt field và parameter trong một lớp thông thường, mẫu quan trọng vẫn là **`this.field = parameter;`**.

## 14. Những lỗi thường gặp và cách phát hiện

| Lỗi | Hiện tượng | Cách sửa |
| --- | --- | --- |
| `name = name;` khi có field và parameter trùng tên | Tham số tự gán; field vẫn giá trị cũ/mặc định | Viết `this.name = name;` |
| `this.name = this.name;` | Field tự gán; tham số bị bỏ qua | Vế phải dùng `name` của tham số |
| Trong setter viết `age = age;` | Object không được cập nhật | `this.age = age;` |
| Trong phương thức có local `int value`, dùng `value` và nghĩ là field | In/đọc nhầm local | `this.value` khi cần field |
| Dùng `this.field` trong `static` | Lỗi compile: không có `this` | Dùng một tham chiếu object cụ thể hoặc biến thành instance method |
| Nhầm `this(field)` với `this.field` | Cú pháp/chức năng khác hoàn toàn | `this(...)` chỉ dùng để ủy quyền constructor |
| Dùng `this.field` để chỉ field cùng tên của superclass | Có thể đang lấy field bị che ở lớp con | Dùng `super.field` khi cần và truy cập hợp lệ |
| Cho rằng `this.field = parameter` tự kiểm tra dữ liệu | Lưu cả giá trị sai vào object | Xác thực invariant trước khi gán |
| Cho rằng `this` ở hai instance luôn trỏ cùng object | Hai object bị hiểu nhầm là một | Receiver thay đổi theo đối tượng nhận lời gọi |
| Để `this` thoát ra từ constructor trước khi xong | Mã khác có thể thấy trạng thái chưa hoàn chỉnh | Không công bố receiver quá sớm |

Trong IDE, một số cảnh báo kiểu “assignment to itself” có thể giúp phát hiện `name = name;`. Tuy nhiên không nên dựa hoàn toàn vào cảnh báo: compiler Java **không nhất thiết từ chối** câu lệnh tự gán này. Hãy kiểm thử trạng thái sau constructor và setter.

## 15. Checklist đọc và review code

Khi thấy một constructor hoặc setter có cùng tên trường/tham số:

1. Liệt kê **field** cần thiết lập, chẳng hạn `name`, `age`, `level`.
2. Xác định các **tham số** có cùng tên và phạm vi hiệu lực.
3. Ở mỗi phép gán, kiểm tra vế trái có thật sự là **`this.field`** không.
4. Kiểm tra vế phải là dữ liệu được yêu cầu, không phải chính field.
5. Kiểm tra các **precondition** trước khi ghi field.
6. Nếu cần so sánh giá trị mới và cũ, viết rõ **tham số** và **`this.field`**.
7. Kiểm thử ít nhất một đối tượng với giá trị khác mặc định, và nếu có thể, **hai đối tượng với dữ liệu khác nhau**.
8. Nếu là phương thức static, xác định tham chiếu object mà phương thức thực sự cần xử lý.
9. Nếu có kế thừa/field hiding, phân biệt `this.field`, `super.field` và field của lớp thực sự đang khai báo method.
10. Khi dùng constructor chaining, kiểm tra `this(...)` chỉ chọn constructor cùng lớp chứ không thay thế phép gán các field.

Ví dụ, sau `new StudentProfile("An", 1)`, bài kiểm tra trạng thái phải đọc lại được **`"An"` và `1`**, không chỉ xác nhận lệnh `new` không ném ngoại lệ.

## 16. Bài tập tự luyện

**Bài 1 — Tìm lỗi.** Dự đoán giá trị `id` sau `new User(9)`:

~~~java
class User {
    private int id;

    User(int id) {
        id = id;
    }

    int id() {
        return id;
    }
}
~~~

Sửa constructor sao cho trường nhận giá trị 9.

**Bài 2 — Trường hay tham số?** Trong `void setAge(int age) { this.age = age; }`, từng `age` ở vế trái và phải thuộc về đâu?

**Bài 3 — Biến cục bộ.** Giả sử class có field `int total = 7;`. Trong instance method, có `int total = 100;`. Dự đoán `System.out.println(total)` và `System.out.println(this.total)`.

**Bài 4 — Nhiều instance.** Cho hai `StudentProfile` với các tên `"Lan"` và `"Minh"`. Gọi `rename("Linh")` trên object đầu. Object thứ hai có đổi tên không? Vì sao?

**Bài 5 — Static.** Giải thích vì sao `static void update(int age) { this.age = age; }` sai. Đề xuất một instance method hoặc dùng tham số object để thay thế.

**Bài 6 — Constructor delegation.** Phân biệt `this(name, 0)` và `this.name = name` trong constructor. Câu lệnh nào gán field, câu lệnh nào gọi constructor khác?

**Bài 7 — Field hiding.** Một lớp con cũng khai báo `size` như lớp cha. Tại sao `this.size` và `super.size` có thể cho kết quả khác nhau?

**Bài 8 — Thiết kế an toàn.** Viết constructor `Product(String name, int stock)` với hai trường `private final String name;` và `private int stock;`; từ chối tên rỗng/`null`, stock âm, rồi gán đúng bằng `this`.

### Đáp án tham khảo

1. Field `id` vẫn bằng 0 vì `id = id` tự gán tham số; sửa thành `this.id = id;`.
2. `this.age` là trường instance; `age` không kèm `this` là tham số.
3. In `100` rồi `7`, vì local `total` che tên field `total`.
4. Không. `this` ở `rename` trỏ đến object được gọi; object thứ hai giữ trường riêng.
5. Static không có receiver `this`; viết `void update(int age) { this.age = age; }` trong lớp thích hợp, hoặc `static void update(Person p, int age) { p.age = age; }` khi có quyền truy cập field.
6. `this(name, 0)` ủy quyền constructor; `this.name = name` gán field của object hiện tại.
7. `this.size` có thể chọn field do lớp con khai báo, `super.size` chọn field được nhìn qua superclass theo quy tắc truy cập.
8. Ví dụ phần thân: `if (name == null || name.isBlank() || stock < 0) throw new IllegalArgumentException(); this.name = name; this.stock = stock;` (constructor đặt trong lớp có đủ hai field).

## 17. Tài liệu đối chiếu

- [Java Language Specification 17, §6.4.1 — Shadowing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4.1): quy tắc che khuất tên trường bởi parameter/local và các tên khác.
- [Java Language Specification 17, §15.8.3 — `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.3): ngữ nghĩa biểu thức `this`, các ngữ cảnh hợp lệ và không hợp lệ.
- [Java Language Specification 17, §8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): trường của lớp, instance field và static field.
- [Java Language Specification 17, §8.8.7 — Constructor Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7): phần thân constructor và lời gọi constructor tường minh.

**Ghi nhớ:** khi field và tham số có **cùng tên**, viết **`this.field = parameter;`** để gán đúng trạng thái cho object. `this.field` chỉ trường của **instance nhận lời gọi**, còn tên trần thường được phân giải về tham số/local đang che field. Phân biệt được hai phía phép gán sẽ tránh một lỗi Java rất dễ biên dịch qua nhưng làm đối tượng giữ sai dữ liệu.
