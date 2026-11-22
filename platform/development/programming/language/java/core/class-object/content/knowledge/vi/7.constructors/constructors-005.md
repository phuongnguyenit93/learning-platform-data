# Hàm khởi tạo không tham số do người lập trình khai báo trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Viết đúng **constructor không tham số** (*no-argument constructor* hoặc *no-arg constructor*) do lập trình viên tự khai báo trong một lớp Java.
- Phân biệt constructor không tham số **khai báo tường minh** với **default constructor** được compiler tự tạo khi lớp hoàn toàn không khai báo constructor nào.
- Giải thích ý nghĩa của `new ClassName()`, cách khởi tạo các instance fields, thứ tự khởi tạo và vai trò của constructor trong việc bảo đảm trạng thái đối tượng hợp lệ.
- Hiểu vì sao khi đã tự khai báo một constructor có tham số, Java không còn tự cung cấp default constructor; biết cách khai báo thêm no-arg constructor nếu API cần.
- Dùng `this(...)` để ủy quyền cho constructor khác, phân biệt với `super(...)` và lời gọi `super()` ngầm định.
- Áp dụng `public`, `protected`, package-private, `private` cho constructor; phân biệt quyền gọi constructor với quyền truy cập lớp.
- Chẩn đoán các lỗi phổ biến: khai báo kiểu trả về, sai tên, gọi constructor không tồn tại, thiếu gán `final` field hoặc không thể gọi constructor lớp cha.
- Biên dịch và chạy những ví dụ Java 17+ có kết quả đầu ra xác định.

## 1. Constructor không tham số là gì?

**Constructor (hàm khởi tạo)** là thành phần đặc biệt của lớp được thực thi trong quá trình tạo đối tượng bằng `new` hoặc qua cơ chế tạo đối tượng phù hợp khác của Java. Một constructor:

- Có **tên giống hệt tên lớp**.
- **Không khai báo kiểu trả về** — không có `void` và cũng không có bất kỳ kiểu nào khác.
- Có danh sách tham số riêng, có thể rỗng hoặc có nhiều tham số.
- Có thể khởi tạo instance fields, kiểm tra điều kiện và tổ chức bất biến (*invariant*) của đối tượng.
- Không phải phương thức bình thường: constructor không được kế thừa, override hoặc gọi như `object.ConstructorName()`.

**Constructor không tham số do người lập trình khai báo** là constructor được viết rõ trong mã nguồn với cặp ngoặc tròn **`()` rỗng**, ví dụ:

~~~java
public class Lamp {
    private boolean on;
    private int brightness;

    public Lamp() {
        on = false;
        brightness = 50;
    }

    public boolean isOn() {
        return on;
    }

    public int getBrightness() {
        return brightness;
    }
}
~~~

Đây là tệp `Lamp.java` biên dịch được, chưa có `main` để chạy trực tiếp. `public Lamp()` là constructor không có tham số hình thức nào, do người lập trình viết. Khi mã bên ngoài có quyền truy cập phù hợp gọi `new Lamp()`, đối tượng mới có `on == false` và `brightness == 50` khi constructor kết thúc bình thường.

Cấu trúc tổng quát cho một class tên `ClassName`:

~~~java
[accessModifier] ClassName() {
    // Lệnh khởi tạo hợp lệ
}
~~~

Phần `[accessModifier]` biểu thị thành phần tùy chọn trong sơ đồ cú pháp, **không phải** ký tự `[]` cần gõ trong Java. Access modifier có thể là `public`, `protected`, `private`, hoặc không ghi để có package-private. Constructor còn có thể khai báo `throws` và trong một số trường hợp có annotation/type parameters thích hợp; nhưng **không được** khai báo `static`, `final`, `abstract` hoặc kiểu trả về như một method.

## 2. Phân biệt no-arg tự viết với default constructor do compiler sinh

Hai class sau đều gọi được với `new Type()`, nhưng **constructor được tạo bởi hai nguồn khác nhau**:

~~~java
class AutoCreated {
    int quantity = 7;
    // Không khai báo constructor: compiler cung cấp default constructor.
}

class ManuallyCreated {
    private final int quantity;

    ManuallyCreated() {
        quantity = 7; // Constructor không tham số tường minh.
    }
}
~~~

Ở `AutoCreated`, giá trị 7 đến từ **field initializer**, không phải code tự viết trong default constructor. Ở `ManuallyCreated`, lệnh gán 7 nằm trong constructor `ManuallyCreated()` và compiler **không** tự sinh thêm constructor mặc định.

| Điều kiện | Constructor không tham số được gọi |
| --- | --- |
| Class không khai báo constructor nào | *Default constructor* do compiler ngầm cung cấp |
| Class tự khai báo `X()` | *Explicit no-arg constructor* của lập trình viên |
| Class chỉ khai báo `X(int n)` | Không có `X()` tự động; `new X()` là lỗi biên dịch |

Chương học về *constructor mặc định* giải thích đầy đủ điều kiện compiler tạo nó, quyền truy cập và quan hệ superclass. **Trọng tâm của bài này** là: khi **chủ động viết `X()`**, bạn có thể chọn giá trị khởi đầu có nghĩa, khởi tạo `final` fields, kiểm tra invariant hoặc gọi `this(...)` để dùng lại constructor có tham số. `new X()` một mình không cho biết constructor được ngầm sinh hay tự viết; phải đọc declaration của class.

## 3. Cú pháp constructor không tham số chính xác

~~~java
public class Device {
    private String model;
    private boolean enabled;

    public Device() {
        model = "Generic";
        enabled = true;
    }
}
~~~

Đây là tệp `Device.java` biên dịch được. Những điểm cần kiểm tra:

1. Tên constructor là **`Device`**, trùng chính xác tên lớp `Device`, có phân biệt chữ hoa/chữ thường.
2. Giữa hai dấu `(` và `)` không có tham số.
3. Không có `void` hoặc kiểu trả về phía trước `Device`.
4. Thân constructor là khối lệnh `{ ... }`; đây là nơi có thể kiểm tra/khởi tạo trạng thái.
5. Constructor có mức truy cập `public`; việc gọi từ lớp khác còn phụ thuộc khả năng truy cập lớp và các quy tắc module/package tương ứng.

So sánh các dạng:

| Khai báo | Kết luận |
| --- | --- |
| `public Device() { }` | Constructor không tham số tường minh, hợp lệ |
| `Device() { }` | Constructor không tham số, quyền package-private |
| `private Device() { }` | Constructor không tham số chỉ được gọi ở những nơi có quyền truy cập private |
| `public void Device() { }` | **Method thông thường** có kiểu trả về `void`, không phải constructor |
| `public device() { }` trong lớp `Device` | Sai kiểu khai báo constructor vì tên khác chữ hoa/thường; thường báo lỗi khai báo method thiếu return type |
| `public static Device() { }` | Sai cú pháp/khai báo; constructor không `static` |
| `public final Device() { }` | Sai; `final` không phải modifier constructor hợp lệ |
| `public Device(int id) { }` | Constructor **có một tham số**, không phải no-arg constructor |

Constructor **không khai báo `return value;`**. Trong constructor, `return;` không kèm giá trị có thể được dùng theo quy tắc ngôn ngữ để kết thúc sớm, nhưng nên tránh nếu nó dễ làm trạng thái đối tượng thiếu nhất quán.

## 4. Ví dụ hoàn chỉnh Java 17+: no-arg constructor và constructor có tham số

Lưu mã dưới đây thành **`NoArgConstructorDemo.java`**:

~~~java
public class NoArgConstructorDemo {
    static final class Notebook {
        private final String title;
        private int pages = 20;
        private boolean archived;
        private static int created;

        Notebook() {
            this("Untitled");
        }

        Notebook(String title) {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("title is required");
            }
            this.title = title;
            created++;
        }

        void addPages(int more) {
            if (more <= 0) {
                throw new IllegalArgumentException("more must be positive");
            }
            pages += more;
        }

        String summary() {
            return title + ": pages=" + pages + ", archived=" + archived;
        }

        static int createdCount() {
            return created;
        }
    }

    public static void main(String[] args) {
        Notebook first = new Notebook();
        Notebook second = new Notebook("Java");

        second.addPages(5);

        System.out.println(first.summary());
        System.out.println(second.summary());
        System.out.println("created=" + Notebook.createdCount());
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 NoArgConstructorDemo.java
java NoArgConstructorDemo
~~~

Output:

~~~text
Untitled: pages=20, archived=false
Java: pages=25, archived=false
created=2
~~~

**Phân tích:**

1. `new Notebook()` chọn constructor `Notebook()` **không tham số**, do lập trình viên viết.
2. Dòng đầu thân constructor `Notebook()` là `this("Untitled");`. Đây là lời gọi **constructor khác trong cùng lớp**.
3. Constructor `Notebook(String title)` kiểm tra `title` và gán field `final title` bằng `"Untitled"`. Nó tăng `created` một lần.
4. `new Notebook("Java")` gọi trực tiếp constructor có tham số. Nó khởi tạo field `title` thành `"Java"` và tăng `created` thêm một lần.
5. `pages = 20` là **instance field initializer**, chạy trong quá trình khởi tạo **mỗi đối tượng**; cả hai đối tượng ban đầu có `20` trang.
6. `archived` không có initializer nên nhận default value `false`.
7. `second.addPages(5)` sửa `pages` của đối tượng thứ hai từ `20` thành `25`. Đối tượng đầu vẫn `20`.
8. `created` là static field dùng chung trong lớp `Notebook`, nên sau hai lần khởi tạo thành công giá trị là `2`.

Ví dụ quan trọng vì constructor `()` **không bắt buộc tự gán từng field**: có thể ủy quyền thông qua `this(...)` để tránh trùng lặp logic và để constructor có tham số làm điểm tập trung kiểm tra dữ liệu.

### 4.1. Tại sao `this(...)` có ích?

Nếu tự viết hai constructor như sau:

~~~java
class Example {
    private final String title;
    private int pages;

    Example() {
        this.title = "Untitled";
        this.pages = 20;
    }

    Example(String title) {
        this.title = title;
        this.pages = 20;
    }
}
~~~

Đây là lớp minh họa hợp lệ, nhưng logic `pages = 20` bị lặp lại. Khi yêu cầu thay đổi, rất dễ sửa một nơi mà quên nơi khác.

Có thể thay bằng **constructor chaining**:

~~~java
class Example {
    private final String title;
    private final int pages;

    Example() {
        this("Untitled", 20);
    }

    Example(String title, int pages) {
        this.title = title;
        this.pages = pages;
    }
}
~~~

Bây giờ logic gán `final` fields nằm trong một constructor chính. Cả hai đoạn lớp `Example` ở trên là **hai phương án thay thế**, không phải hai class `Example` được khai báo cùng lúc trong một package/file.

## 5. Field default values và constructor không tham số

Nếu một field không có initializer, Java vẫn gán **giá trị mặc định** cho field trong quá trình tạo đối tượng. No-arg constructor có thể giữ nguyên hoặc ghi đè những giá trị đó.

| Kiểu field | Giá trị mặc định |
| --- | --- |
| `byte`, `short`, `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `boolean` | `false` |
| `char` | Giá trị mã UTF-16 bằng 0 |
| Kiểu tham chiếu: `String`, mảng, collection, class khác | `null` |

Ví dụ, constructor rỗng không tự đổi một field `String name;` thành chuỗi rỗng `""` và không tự tạo `new ArrayList<>()`. Nếu nghiệp vụ đòi giá trị khác null, người lập trình phải khởi tạo ở field initializer, instance initializer, constructor hoặc con đường thiết kế hợp lệ khác.

Lưu **`DefaultVsExplicitDemo.java`**:

~~~java
public class DefaultVsExplicitDemo {
    static class Implicit {
        int value = 7;
        // Không khai báo constructor: compiler cấp default constructor.
    }

    static class Explicit {
        int value;
        Explicit() {
            value = 9;
        }
    }

    static class OnlyParameterized {
        int value;

        OnlyParameterized(int value) {
            this.value = value;
        }
    }

    static class EmptyExplicit {
        int number;
        boolean ready;
        String text;

        EmptyExplicit() {
            // Constructor tường minh rỗng.
        }
    }

    public static void main(String[] args) {
        System.out.println("implicit=" + new Implicit().value);
        System.out.println("explicit=" + new Explicit().value);
        System.out.println("parameterized=" + new OnlyParameterized(11).value);

        EmptyExplicit empty = new EmptyExplicit();
        System.out.println("empty=" + empty.number + ","
                + empty.ready + "," + empty.text);

        // new OnlyParameterized(); // Không biên dịch: thiếu constructor ().
    }
}
~~~

Chạy:

~~~bash
javac DefaultVsExplicitDemo.java
java DefaultVsExplicitDemo
~~~

Output:

~~~text
implicit=7
explicit=9
parameterized=11
empty=0,false,null
~~~

`Implicit` không khai báo constructor nên có default constructor do compiler cấp. `Explicit` và `EmptyExplicit` khai báo no-arg constructor rõ ràng. `OnlyParameterized` chỉ có constructor nhận `int`, vì vậy **không có** constructor `()` mặc định.

Trong `EmptyExplicit`, constructor rỗng hợp lệ vì các fields thông thường nhận default values; **không** nên suy ra mọi đối tượng sau đó đã đáp ứng các yêu cầu nghiệp vụ như “`text` không null”.

## 6. Thứ tự khởi tạo khi gọi `new ClassName()`

Không nên tưởng rằng constructor là lệnh đầu tiên chạy trên một đối tượng mới. Đối với một lớp thông thường, thứ tự khái quát là:

1. **Cấp phát đối tượng**, tất cả instance fields nhận **default values** trước.
2. Thực hiện chuỗi constructor thích hợp, bao gồm constructor của superclass, theo quy tắc gọi `super(...)` hoặc `this(...)`.
3. **Field initializers** và **instance initializer blocks** của từng lớp được chạy ở thời điểm thích hợp trong quá trình khởi tạo lớp đó, theo thứ tự xuất hiện trong mã nguồn.
4. Thực hiện thân constructor tương ứng sau các bước khởi tạo lớp cha và instance initializers của lớp hiện tại.
5. Nếu constructor kết thúc bình thường, biểu thức `new` trả tham chiếu tới đối tượng đã khởi tạo.

Trong ví dụ no-arg constructor có lời gọi `this("Untitled")`, việc ủy quyền **không làm field initializers chạy hai lần** cho cùng một đối tượng. Chuỗi constructor kết thúc trong constructor không gọi `this(...)` nữa mới đi qua bước gọi superclass và chạy các field initializers của lớp theo quy tắc.

### 6.1. Ví dụ thứ tự có inheritance

Lưu thành **`NoArgInitializationOrderDemo.java`**:

~~~java
public class NoArgInitializationOrderDemo {
    static int trace(String text, int value) {
        System.out.println(text);
        return value;
    }

    static class Base {
        int baseValue = trace("base field initializer", 1);

        Base() {
            System.out.println("Base constructor");
        }
    }

    static class Child extends Base {
        int count = trace("child field initializer", 2);

        {
            System.out.println("child initializer block");
            count += 3;
        }

        Child() {
            // Java 17 chèn lời gọi super() ngầm định tại đây.
            System.out.println("Child constructor");
            count += 4;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        System.out.println("result=" + child.baseValue + "," + child.count);
    }
}
~~~

Chạy:

~~~bash
javac NoArgInitializationOrderDemo.java
java NoArgInitializationOrderDemo
~~~

Output:

~~~text
base field initializer
Base constructor
child field initializer
child initializer block
Child constructor
result=1,9
~~~

Kết quả cho thấy:

- Phần khởi tạo của `Base` thực thi trước phần của `Child`.
- `count` được gán `2`, sau đó block tăng thành `5`, rồi thân constructor tăng thành `9`.
- Không có lời gọi `super()` viết ra trong constructor `Child()`, nên theo quy tắc Java 17 compiler đặt một lời gọi `super();` ngầm định ở đầu constructor.
- Lớp cha phải có constructor không tham số **có thể truy cập** nếu constructor con dùng `super()` ngầm định.

**Chú ý:** Dòng chú thích không phải câu lệnh `super();`. Nếu muốn viết rõ, Java 17 đòi `super();` hoặc `this(...);` được đặt làm câu lệnh constructor invocation đầu tiên; không đặt lệnh in log trước nó.

## 7. Constructor chaining: `this()`, `this(...)` và `super()`

Một constructor có thể gọi constructor khác bằng:

- **`this(...)`**: gọi một constructor khác của **chính lớp đó**, ví dụ `this("Guest")`.
- **`super(...)`**: gọi một constructor của **lớp cha**, ví dụ `super(5)`.

Với **Java 17**, lời gọi constructor tường minh `this(...)` hoặc `super(...)` phải là **câu lệnh đầu tiên** trong thân constructor. Nếu không có lời gọi tường minh nào, compiler chèn `super();` ngầm định cho constructor của lớp thông thường thích hợp. Hai lời gọi tường minh không thể cùng chiếm vị trí đầu tiên trong một constructor.

Ví dụ:

~~~java
class User {
    private final String name;

    User() {
        this("Guest");
    }

    User(String name) {
        this.name = name;
    }
}
~~~

No-arg constructor `User()` chuyển trách nhiệm gán `name` cho constructor `User(String)`. Tránh sao chép logic và chỉ cần kiểm tra tính hợp lệ của tên ở một nơi nếu bài toán cần validation.

Constructor **không được tạo vòng đệ quy**:

~~~java
// Ví dụ sai, không được đưa vào cùng chương trình để biên dịch:
// class Loop {
//     Loop() { this(1); }
//     Loop(int n) { this(); }
// }
~~~

Vòng `Loop() -> Loop(int) -> Loop()` dẫn tới lỗi biên dịch do recursive constructor invocation. Mỗi chuỗi ủy quyền cần đi đến một constructor không tiếp tục ủy quyền trong cùng lớp.

### 7.1. Khi superclass không có constructor không tham số

Giả sử:

~~~java
class Parent {
    Parent(String name) {
    }
}

class Child extends Parent {
    Child() {
        // Java định gọi super() ngầm định,
        // nhưng Parent không có constructor ().
    }
}
~~~

Đây là **ví dụ cố ý không hợp lệ**: `Parent` chỉ có constructor `Parent(String)`; `Child()` không thể gọi `super()` ngầm định vì constructor lớp cha không tồn tại.

Sửa bằng cách gọi constructor cha phù hợp **ngay dòng đầu**:

~~~java
class Parent {
    private final String name;

    Parent(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

class Child extends Parent {
    Child() {
        super("Default parent");
    }
}
~~~

Đoạn lớp thay thế ở trên **biên dịch hợp lệ** trong tệp Java thích hợp, dù chưa có `main` để chạy. `Child()` là **constructor không tham số do người lập trình viết**; nó vẫn có quyền gọi `super("Default parent")` bên trong. “Không tham số” mô tả **danh sách tham số của `Child()`**, không bắt buộc constructor ấy phải gọi `super()` không tham số.

**Phân biệt:** constructor không tham số của một lớp con **không đảm bảo** superclass phải có no-arg constructor, miễn constructor con chọn đúng một đường gọi superclass hợp lệ. Nhưng nếu constructor con **không có lời gọi tường minh** thì compiler mặc định thử `super()`.

## 8. Khởi tạo field `final` trong constructor không tham số

Một instance field `final` chưa có initializer tại khai báo được gọi là **blank final field**. Java yêu cầu các constructor hoàn tất bình thường phải bảo đảm field này được gán theo quy tắc definite assignment.

Ví dụ hợp lệ:

~~~java
class Session {
    private final String token;
    private final int attempts;

    Session() {
        token = "anonymous";
        attempts = 0;
    }
}
~~~

No-arg constructor đã gán cả hai blank final fields, do đó hợp lệ.

Ví dụ **không hợp lệ**:

~~~java
// Mã cố ý sai:
// class Session {
//     private final String token;
//     Session() {
//         // Thiếu gán token trên đường kết thúc constructor bình thường.
//     }
// }
~~~

Compiler không chấp nhận một constructor có đường hoàn tất bình thường khi blank final field bắt buộc chưa được gán.

Có thể dùng chaining để constructor khác gán các final fields:

~~~java
class Session {
    private final String token;

    Session() {
        this("anonymous");
    }

    Session(String token) {
        this.token = token;
    }
}
~~~

Đây là một **phương án khác** khai báo lớp `Session`, không phải đoạn thêm đồng thời bên dưới class `Session` trước đó. Trong no-arg constructor, không nên cố gán `token` **lần thứ hai** sau khi constructor `Session(String)` đã gán: `final` ngăn gán lại theo quy tắc Java.

**Lưu ý:** `final` field kiểu tham chiếu không tự biến đối tượng nó tham chiếu thành bất biến. Chẳng hạn `final List<String> tags` có thể trỏ tới một `ArrayList` vẫn cho phép sửa phần tử. No-arg constructor phải quyết định trạng thái hợp lệ, chứ không dựa vào `final` để bảo vệ toàn bộ object graph.

## 9. Phạm vi truy cập của constructor không tham số

Constructor có thể có access modifier riêng, ảnh hưởng nơi được phép gọi `new ClassName()`.

| Khai báo | Khả năng gọi theo phạm vi thông thường |
| --- | --- |
| `public Widget() { }` | Nơi truy cập được lớp, constructor và module/package tương ứng |
| `protected Widget() { }` | Cùng package và các ngữ cảnh kế thừa được Java cho phép; có quy tắc cụ thể khi gọi từ package khác |
| `Widget() { }` | Package-private: gọi từ mã có quyền trong cùng package |
| `private Widget() { }` | Gọi trong phạm vi private được Java cho phép (kể cả các trường hợp *nestmates*) |

**Lớp public không tự tạo public constructor.** Ví dụ:

~~~java
public class Service {
    Service() {
    }
}
~~~

Đây là tệp `Service.java` hợp lệ. `Service` là kiểu `public`, nhưng constructor `Service()` là **package-private** vì không có modifier; mã thuộc package khác không thể dùng `new Service()` trực tiếp.

Nếu lớp dùng làm API public và mong caller bên ngoài tạo đối tượng bằng `()`, hãy khai báo constructor `public` rõ ràng:

~~~java
public class Service {
    public Service() {
    }
}
~~~

Hai đoạn `Service` là **hai phương án thay thế**.

### 9.1. No-arg constructor private để kiểm soát tạo đối tượng

Lưu tệp **`PrivateConstructorDemo.java`**:

~~~java
public class PrivateConstructorDemo {
    static final class Config {
        private final int port;

        private Config() {
            port = 8080;
        }

        static Config createDefault() {
            return new Config();
        }

        int port() {
            return port;
        }
    }

    public static void main(String[] args) {
        Config config = Config.createDefault();
        System.out.println("port=" + config.port());

        // Trong class bên ngoài cùng nest, một số truy cập private
        // vẫn có thể hợp lệ; tránh suy luận rằng private là ranh giới
        // bảo mật tuyệt đối trước mã đã được cho chạy cùng quyền.
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PrivateConstructorDemo.java
java PrivateConstructorDemo
~~~

Output:

~~~text
port=8080
~~~

Ở đây `Config()` là **no-arg constructor private**, không thể được mã tùy ý ngoài phạm vi private truy cập trực tiếp. Phương thức `createDefault()` do lớp cung cấp là một **static factory** để kiểm soát việc tạo đối tượng. Mẫu này có thể dùng khi muốn giữ quyền tạo đối tượng trong một nơi, nhưng constructor private **không biến lớp thành singleton tự động**: mỗi lần factory thực hiện `new Config()` vẫn tạo đối tượng mới.

Với một **utility class** chỉ gồm phương thức static, constructor private rỗng cũng thường được dùng để ngăn lời gọi `new` không cần thiết. Tuy nhiên, nếu thiết kế dành cho kế thừa, một constructor private có thể làm subclass không thể gọi constructor của lớp cha, nên cần lựa chọn access modifier phù hợp.

### 9.2. Default constructor ngầm định cũng có quyền truy cập

Nếu lớp không khai báo constructor, compiler cung cấp default constructor với quyền truy cập theo quy tắc của lớp Java tương ứng. Vì vậy **không nên mặc định** rằng một lớp với constructor ngầm định luôn tạo được từ mọi package. Với thư viện, viết constructor tường minh thường giúp người đọc nhận rõ API tạo đối tượng, đặc biệt khi có yêu cầu quyền truy cập khác mặc định.

## 10. Kiểm tra tính hợp lệ và exception trong no-arg constructor

Constructor không tham số **không nhận dữ liệu trực tiếp từ caller**, nhưng vẫn có thể đặt trạng thái hợp lệ, sử dụng giá trị mặc định có chủ đích, hoặc ném exception nếu không thể khởi tạo thành công.

Ví dụ:

~~~java
class Counter {
    private int value;

    Counter() {
        value = 0;
    }

    int current() {
        return value;
    }
}
~~~

Đoạn class hợp lệ. Dù `int` field vốn đã mặc định `0`, phép gán tường minh `value = 0;` vẫn có thể có giá trị **truyền đạt ý định**: đối tượng mới bắt đầu ở trạng thái 0.

Nếu nghiệp vụ cần thời gian hoặc giá trị cấu hình mặc định, hãy cân nhắc:

- **Giá trị cố định rõ ràng** nếu hành vi cần xác định, ví dụ `timeoutSeconds = 30`.
- **Tính toán từ thời điểm tạo đối tượng**, nếu đặc tả đòi, nhưng hiểu rằng đầu ra có thể thay đổi mỗi lần chạy; đừng hứa stdout cố định cho thời gian hiện tại.
- **Gọi constructor khác bằng `this(...)`** để tái sử dụng kiểm tra dữ liệu.
- **Factory method** khi việc tạo đối tượng cần các bước phức tạp, có lỗi I/O hoặc nhiều nguồn cấu hình.

Nếu một constructor ném exception trước khi kết thúc bình thường, biểu thức `new` không trả về đối tượng cho caller theo đường chạy đó. Side effects đã thực hiện trước exception (chẳng hạn thay đổi static field hoặc ghi log) không tự động bị rollback. Vì vậy nên tránh đưa đối tượng `this` chưa khởi tạo đầy đủ cho mã bên ngoài truy cập.

### 10.1. Constructor có thể khai báo `throws`

Ví dụ:

~~~java
class Connection {
    Connection() throws java.io.IOException {
        // Ví dụ minh họa khả năng khai báo checked exception.
    }
}
~~~

Khai báo trên **hợp lệ về cú pháp**; caller của `new Connection()` phải xử lý hoặc khai báo ngoại lệ checked tương ứng theo quy tắc Java. Constructor không tham số vẫn có thể có **`throws`**, vì `throws` không phải một tham số hình thức.

Tuy nhiên, không nên tự ý khai báo checked exceptions khi constructor không có thao tác có nguy cơ lỗi tương ứng. Một lớp cần kết nối mạng/tệp có thể được thiết kế tốt hơn với factory hoặc thao tác mở tài nguyên riêng biệt, tùy yêu cầu.

## 11. Constructor không tham số và overloading

**Constructor overloading** cho phép một lớp khai báo nhiều constructor với **danh sách kiểu tham số khác nhau**. Ví dụ:

~~~java
class Point {
    private final int x;
    private final int y;

    Point() {
        this(0, 0);
    }

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

Đây là class biên dịch hợp lệ khi đặt trong file thích hợp. Hai constructor có chữ ký khác nhau: `Point()` và `Point(int,int)`.

- `new Point()` chọn constructor không tham số.
- `new Point(3, 4)` chọn constructor có hai tham số.
- `new Point(3)` **không hợp lệ** vì lớp chưa cung cấp constructor một tham số.

Java **không hỗ trợ default parameter syntax** kiểu `Point(int x = 0)` trong khai báo constructor. Nếu muốn cung cấp giá trị mặc định, có thể dùng overload `()` rồi ủy quyền bằng `this(...)` như trên.

Không thể tạo hai overload chỉ khác access modifier hoặc `throws` mà vẫn có cùng danh sách tham số:

~~~java
// Hai dòng không thể xuất hiện cùng trong class Point:
// public Point() { }
// private Point() throws Exception { }
~~~

Chúng đều khai báo constructor với danh sách tham số rỗng `Point()`; khác quyền truy cập và `throws` không tạo chữ ký constructor mới.

### 11.1. Tác động của việc thêm constructor có tham số vào lớp cũ

Ban đầu:

~~~java
class Settings {
    int timeout = 10;
}
~~~

Compiler sinh default constructor nên `new Settings()` hợp lệ. Nếu sửa lớp thành:

~~~java
class Settings {
    int timeout;

    Settings(int timeout) {
        this.timeout = timeout;
    }
}
~~~

thì code khách hàng còn gọi `new Settings()` sẽ **không biên dịch** nếu được biên dịch lại, vì implicit default constructor đã biến mất.

Nếu muốn giữ API cũ, khai báo tường minh:

~~~java
class Settings {
    int timeout;

    Settings() {
        this(10);
    }

    Settings(int timeout) {
        this.timeout = timeout;
    }
}
~~~

Ba đoạn class `Settings` là **ba phiên bản thiết kế thay thế**, không khai báo đồng thời. Việc sửa constructor có thể ảnh hưởng **source compatibility** và cả binary compatibility của thư viện đã được sử dụng, nên cần kiểm thử tại các call sites.

## 12. Trường hợp nào nên khai báo no-arg constructor?

### Phù hợp

1. **Đối tượng có trạng thái mặc định hợp lệ**: `new Counter()` bắt đầu ở 0; `new Notebook()` tạo đối tượng với tên mặc định và số trang ban đầu.
2. **Cần một API tạo đối tượng thuận tiện** bên cạnh constructor chi tiết: `new Point()` ủy quyền `this(0,0)`.
3. **Cần giữ cách dùng `new X()`** khi bổ sung constructor có tham số vào lớp đã có.
4. **Thư viện/framework yêu cầu constructor có thể truy cập với 0 tham số**: có thể tồn tại yêu cầu này ở các công cụ phản chiếu, serializer, ORM, DI container. Cần đọc hợp đồng cụ thể của framework, vì mỗi framework có quy tắc khác nhau về visibility/khởi tạo.
5. **Cần kiểm soát khả năng khởi tạo**: `private X()` hoặc factory giúp hạn chế nơi được phép tạo đối tượng.

### Cần cân nhắc hoặc không phù hợp

- Khi mọi đối tượng **bắt buộc phải có dữ liệu không thể tự cung cấp hợp lệ**, ví dụ mã giao dịch không được rỗng hoặc khóa nghiệp vụ phải có ngay khi tạo, constructor có tham số hoặc factory là lựa chọn tốt hơn.
- Khi no-arg constructor tạo một đối tượng ở **trạng thái nửa vời**, bắt caller nhớ gọi `setX`, `setY`, `initialize` theo đúng thứ tự. Cách đó dễ sinh lỗi bỏ sót.
- Khi muốn dùng no-arg constructor chỉ để che lỗi `new X()` mà không hiểu vì sao đối tượng cần được tạo bằng cách ấy.
- Khi trường có dữ liệu mutable, cần đảm bảo từng instance có tài nguyên/trạng thái riêng nếu yêu cầu độc lập; tránh đưa một collection `static` dùng chung mà tưởng no-arg constructor đã tạo collection riêng.

**Nguyên tắc thiết kế:** constructor nên thiết lập **bất biến của đối tượng** để sau khi khởi tạo thành công, các method public có thể sử dụng trạng thái mà không phải phòng vệ trước một object chưa sẵn sàng.

## 13. Những lỗi biên dịch và hiểu nhầm thường gặp

| Tình huống | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `constructor X cannot be applied to given types` khi `new X()` | Lớp chỉ có constructor có tham số hoặc no-arg constructor không phù hợp | Khai báo `X()` hợp lệ, hoặc truyền đúng đối số |
| `constructor X() is undefined` | Không có constructor `()` mà caller có thể sử dụng | Kiểm tra danh sách constructor thực có |
| `void X() { }` được viết để “tạo constructor” | Đây là **method** `void`, không phải constructor | Viết `X() { }` không có kiểu trả về |
| Viết `static X() { }` | Constructor không `static` | Bỏ `static`; nếu cần factory, tạo static method trả `X` |
| Tên constructor khác chữ hoa/thường | Tên phải trùng tên lớp | Sửa chính xác `ClassName()` |
| Constructor không tham số bị khai báo trùng | Hai constructor cùng danh sách tham số rỗng | Giữ một constructor `()` duy nhất |
| Thêm constructor có tham số làm `new X()` hỏng | Compiler không còn tự sinh default constructor | Khai báo thêm explicit `X()` nếu cần |
| `implicit super constructor Parent() is undefined` | `Parent` không có no-arg constructor phù hợp | Viết `super(args)` tường minh hoặc thiết kế lại lớp cha |
| `call to this must be first statement` trong Java 17 | Đặt log/gán field trước `this(...)` | Đưa `this(...)` lên đầu thân constructor |
| `recursive constructor invocation` | Các `this(...)` gọi vòng tròn | Thiết kế một constructor đích không tiếp tục ủy quyền |
| `variable x might not have been initialized` với blank final field | Có đường kết thúc constructor không gán field `final` | Gán ở mọi đường hợp lệ hoặc ủy quyền constructor gán đủ |
| Constructor `private` không gọi được từ lớp khác | Quyền truy cập hạn chế | Dùng constructor/factory công khai được thiết kế |
| Class `public` nhưng constructor không `public` | Access của class và constructor là hai thứ khác nhau | Khai báo `public ClassName()` nếu cần |
| Nghĩ constructor rỗng tự khởi tạo `String` thành `""` | Default value của reference field là `null` | Gán initializer/constructor tường minh |
| Nghĩ `new X()` luôn gọi default constructor do compiler sinh | Có thể `X()` do lập trình viên viết | Kiểm tra khai báo thực trong lớp |
| Nghĩ `this(...)` tạo thêm đối tượng | Constructor chaining chạy trên **cùng đối tượng** | `this(...)` không phải `new` |
| Gọi `X()` trên object như method | Constructor không là method kế thừa/callable theo cú pháp instance method | Tạo bằng `new X()` hoặc dùng factory |

### 13.1. Vì sao bỏ constructor tường minh có thể không phải cách sửa tốt?

Nếu một class có no-arg constructor đang kiểm tra hoặc gán giá trị quan trọng, xóa nó chỉ để compiler cung cấp implicit default constructor có thể thay đổi hành vi: những phép kiểm tra và gán đặc biệt sẽ biến mất. Dù `new X()` vẫn biên dịch, object có thể ở trạng thái khác.

Ngược lại, nếu constructor tường minh **thật sự rỗng**, không có yêu cầu đặc biệt về access modifier, API, framework hoặc tài liệu, việc để compiler cấp default constructor cho lớp đơn giản đôi khi có thể gọn hơn. Nhưng cần xem xét quyền truy cập và khả năng bảo trì trước khi xóa.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Lớp `class Book { String title; }` có khai báo constructor không? `new Book()` có hợp lệ không?  
**Đáp án:** Lớp không có constructor do người lập trình khai báo; compiler sinh default constructor phù hợp, nên `new Book()` hợp lệ từ vị trí có quyền truy cập. Field `title` mặc định là `null`.

**Câu 2.** Trong lớp `class Book { Book(String title) {} }`, `new Book()` có biên dịch không?  
**Đáp án:** Không. Constructor có tham số đã được khai báo, nên compiler không sinh implicit default constructor. Phải viết thêm `Book()` hoặc truyền `String` phù hợp.

**Câu 3.** `public void Book() { }` có phải constructor không tham số không?  
**Đáp án:** Không. Đây là method bình thường vì có kiểu trả về `void`. Constructor phải viết `public Book() { }`.

**Câu 4.** Vì sao `Book() { this("Untitled"); }` thường tốt hơn việc lặp lại toàn bộ phép gán ở nhiều constructor?  
**Đáp án:** Nó ủy quyền cho một constructor chính để tái sử dụng validation và khởi tạo trạng thái, tránh logic trùng lặp.

**Câu 5.** Nếu `Book()` ủy quyền qua `this("Untitled")`, Java có tạo hai đối tượng `Book` hay chạy field initializer hai lần không?  
**Đáp án:** Không. Đây là chuỗi constructor trên cùng một đối tượng; field initializers của lớp không chạy lặp theo số mắt xích ủy quyền.

**Câu 6.** Constructor `Child()` không ghi `this(...)` hay `super(...)`, nhưng `Parent` chỉ có `Parent(int n)`. Kết quả là gì?  
**Đáp án:** Nếu không có constructor cha không tham số có thể truy cập, việc gọi `super()` ngầm định gây lỗi biên dịch. Có thể sửa bằng `super(value)` tường minh ở vị trí hợp lệ trong constructor con.

**Câu 7.** `public class Widget` có `Widget() { }` không kèm `public`; code thuộc package khác có gọi trực tiếp `new Widget()` được không?  
**Đáp án:** Không. Class là public nhưng constructor là package-private.

**Câu 8.** No-arg constructor `private Widget() { }` có thể được static factory `Widget.create()` trong cùng lớp gọi không?  
**Đáp án:** Có. Factory có quyền truy cập constructor private của chính lớp và có thể tạo đối tượng rồi trả về theo API.

**Câu 9.** Một blank final instance field không có initializer. No-arg constructor kết thúc bình thường mà chưa gán field đó có hợp lệ không?  
**Đáp án:** Không, nếu chưa được khởi tạo ở nơi hợp lệ khác. Constructor phải bảo đảm definite assignment theo quy tắc `final`.

**Câu 10.** `new Lamp()` với `Lamp()` rỗng có tự khiến mọi field có giá trị nghiệp vụ hợp lệ không?  
**Đáp án:** Không. Field vẫn được gán default value và các initializer phù hợp, nhưng default value như `null` hoặc `0` có thể không thỏa điều kiện của ứng dụng.

**Câu 11.** Hai constructor `X()` khác nhau chỉ ở `public` và `private` có được khai báo đồng thời không?  
**Đáp án:** Không. Cả hai có danh sách tham số rỗng, nên trùng chữ ký constructor; access modifier không tạo overload khác.

**Câu 12.** Đoạn `class C { C() { } }` có default constructor do compiler cấp thêm không?  
**Đáp án:** Không. Đây là explicit no-arg constructor; compiler không cấp một default constructor thứ hai.

## Tổng kết

**Hàm khởi tạo không tham số do người lập trình khai báo** là constructor có tên trùng lớp, không có kiểu trả về và có danh sách tham số rỗng, ví dụ `public User() { ... }`. Nó khác với **default constructor** chỉ được compiler sinh khi lớp không khai báo constructor nào. Tự khai báo một constructor bất kỳ sẽ ngăn compiler tự sinh default constructor, vì vậy nếu cần hỗ trợ `new X()` phải viết no-arg constructor rõ ràng.

No-arg constructor có thể khởi tạo field, kiểm tra invariant, gọi `this(...)` để tái sử dụng constructor khác, hoặc gọi `super(...)` phù hợp. Khi không gọi `this(...)`/`super(...)` tường minh, quy tắc `super()` ngầm định đòi superclass có constructor không tham số truy cập được. Chú ý `final` fields, access modifier, thứ tự khởi tạo và trạng thái hợp lệ của object: **mục tiêu của constructor không chỉ để `new X()` biên dịch, mà còn để đối tượng sẵn sàng sử dụng sau khi tạo**.
