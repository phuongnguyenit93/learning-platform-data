# Tham số hoặc biến cục bộ che khuất trường trong Java

> **Java core — language-basics / Phạm vi và khởi tạo**  
> **Môi trường:** JDK 17+, một file chạy độc lập, không sử dụng thư viện ngoài.  
> **Mục tiêu:** Nhận diện *shadowing* khi tham số/biến cục bộ trùng tên trường (field), dùng `this.field` hoặc `ClassName.staticField` để chọn đúng đối tượng cần truy cập, và tránh nhầm với lỗi khai báo trùng hai biến cục bộ.

## 1. Che khuất trường (*field shadowing*) là gì?

Một lớp có thể khai báo trường và một phương thức có thể khai báo **tham số hoặc biến cục bộ cùng tên**. Trong phạm vi của biến cục bộ/tham số, tên viết đơn lẻ thường chỉ đến khai báo **gần hơn**, khiến trường bị che khuất:

~~~java
public final class Sample {
    private int score = 10;

    public void show() {
        int score = 3; // Local score che khuất trường score.
        System.out.println(score);      // 3: local.
        System.out.println(this.score); // 10: field.
    }
}
~~~

Hai thực thể vẫn tồn tại riêng. Shadowing không xóa trường, không thay kiểu của trường và không tự chuyển dữ liệu giữa trường với biến cục bộ.

- `score`: tên đơn, được phân giải đến local `score` trong phương thức `show`.
- `this.score`: truy cập rõ ràng trường instance `score` của **đối tượng đang gọi** `show`.
- Sau khi rời phạm vi local, có thể dùng tên trường không bị che khuất ở ngữ cảnh instance phù hợp.

**Phân biệt:** Biến cục bộ che khuất **trường** là hợp lệ; nhưng khai báo một local mới trùng tên với local hoặc tham số còn đang có phạm vi chồng lấn thường là **lỗi biên dịch**.

## 2. Tham số trùng tên trường: ví dụ constructor và setter

Mẫu rất phổ biến trong Java:

~~~java
public final class Student {
    private String name;
    private int age;

    public Student(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

Trong constructor `Student(String name, int age)`:

| Biểu thức | Đối tượng được tham chiếu |
| --- | --- |
| `name` | Tham số `name` của constructor |
| `this.name` | Trường `name` thuộc đối tượng hiện tại |
| `age` | Tham số `age` |
| `this.age` | Trường `age` thuộc đối tượng hiện tại |
| `this.age = age` | Gán **giá trị tham số** vào **trường instance** |

`this` là tham chiếu tới đối tượng hiện tại trong constructor và phương thức instance. Nếu đặt tên tham số khác tên trường (`studentName`), có thể viết `name = studentName;` khi không còn local nào che khuất `name`; tuy nhiên `this.name = studentName;` thường rõ nghĩa hơn.

Constructor không có kiểu trả về, còn setter như `setAge` là phương thức trả `void`. Cả hai đều có thể nhận tham số trùng tên trường.

## 3. Lỗi dễ bỏ sót: `value = value` chỉ tự gán tham số

~~~java
public final class Counter {
    private int value; // Mặc định 0.

    public void wrongSet(int value) {
        value = value; // Chỉ tự gán tham số, KHÔNG sửa field.
    }

    public void correctSet(int value) {
        this.value = value; // Sửa field.
    }

    public int current() {
        return value; // Không có local value nên đọc field.
    }
}
~~~

Nếu tạo `Counter counter = new Counter();` rồi gọi `counter.wrongSet(7)`, `counter.current()` vẫn bằng 0. Sau `counter.correctSet(7)`, kết quả mới là 7.

**Vì sao Java không báo lỗi?** Lệnh `value = value` đúng cú pháp: cả hai tên đều phân giải đến tham số local, nên đó là phép gán hợp lệ nhưng không có tác dụng mong muốn. Nhiều IDE hoặc static analyzer có thể cảnh báo dạng tự gán này.

Không nên khắc phục bằng cách biến tất cả trường thành `static`; cần dùng đúng tham chiếu `this` hoặc đổi tên tham số hợp lý.

## 4. Biến cục bộ cũng có thể che khuất trường

Shadowing không chỉ xảy ra ở danh sách tham số:

~~~java
public final class Gauge {
    private int level = 20;

    public void inspect() {
        int level = 5;
        System.out.println("local=" + level);      // local=5
        System.out.println("field=" + this.level); // field=20
        this.level += level;
        System.out.println("updated=" + this.level); // updated=25
    }
}
~~~

Ở đây giá trị local `level` và field `this.level` độc lập. Phép `this.level += level` dùng cả hai trong một biểu thức để cập nhật trường.

Với local cùng tên trường đặt trong **khối con**, tên local có hiệu lực trong vùng thích hợp:

~~~java
class Example {
    private int total = 100;

    void run() {
        System.out.println(total); // 100.
        {
            int total = 7;
            System.out.println(total);      // 7.
            System.out.println(this.total); // 100.
        }
        System.out.println(total); // 100: local trong khối đã hết scope.
    }
}
~~~

Local `total` của khối chỉ tồn tại về mặt phạm vi tên từ chỗ khai báo đến cuối khối. **Trường vẫn là trường của đối tượng**, không bị xóa khi local bắt đầu hoặc kết thúc scope.

## 5. Trường `static`: dùng tên lớp để tránh nhập nhằng

Trường `static` thuộc về lớp, không phải trạng thái riêng của một instance. Nếu local hoặc tham số có tên giống trường static, dùng `ClassName.field`:

~~~java
public final class AppSettings {
    private static String mode = "DEFAULT";

    public static void setMode(String mode) {
        AppSettings.mode = mode;
    }

    public static void show(String mode) {
        System.out.println("parameter=" + mode);
        System.out.println("classField=" + AppSettings.mode);
    }
}
~~~

`AppSettings.mode = mode` cập nhật trường của lớp bằng giá trị tham số; `mode = mode` chỉ tự gán tham số.

Trong một phương thức `static` **không có `this`**, nên `this.mode` là lỗi biên dịch. Nếu cần trường instance từ phương thức static, phải có một đối tượng thích hợp rồi truy cập thông qua tham chiếu đó (và theo quyền truy cập Java).

Một phương thức instance vẫn có thể truy cập trường static, nhưng nên dùng tên lớp để người đọc biết đây là trạng thái dùng chung. Trường static có thể bị thay đổi từ các lời gọi khác; local trùng tên không tạo ra một bản sao của trường static.

## 6. Phân biệt shadowing với trùng tên local và thiếu gán

Ba tình huống thường bị nhầm nhưng có kết quả biên dịch khác nhau:

| Tình huống | Kết quả |
| --- | --- |
| `private int count;` và phương thức nhận `int count` | Hợp lệ: tham số che khuất field; dùng `this.count` để đọc/ghi field |
| Phương thức nhận `int count` rồi khai báo thêm `int count` trong khối con | Không hợp lệ: tên tham số vẫn trong scope |
| `int count;` trong thân phương thức rồi đọc ngay | Không hợp lệ: local chưa được *definitely assigned* |

Một field `int` nhận giá trị mặc định 0 khi đối tượng được tạo; local `int` không tự nhận giá trị mặc định. Shadowing chỉ đổi cách **phân giải tên**, không thay đổi quy tắc khởi tạo của hai loại biến.

## 7. Hướng thiết kế để giảm nhầm lẫn

Dùng tên tham số giống trường (ví dụ `this.name = name`) là cách viết Java phổ biến, nhưng nên giữ mã dễ đọc:

- Trong constructor/setter, dùng nhất quán `this.field = field` khi có tên trùng nhau.
- Dùng `Type.staticField` để truy cập trạng thái của lớp, không giả định `this` có trong phương thức static.
- Tránh đặt local trùng tên field trong các khối quá dài nếu khiến người đọc liên tục phải phân biệt `value` với `this.value`.
- Cân nhắc `final` cho tham số/local không cần gán lại. `final` ngăn thay đổi giá trị biến theo quy tắc Java, nhưng **không** tự giải quyết shadowing hay khiến đối tượng mutable trở thành bất biến.
- Dùng getter hoặc các phương thức cập nhật có ý nghĩa nghiệp vụ nếu việc chỉnh sửa trường cần kiểm tra điều kiện, thay vì cho phép thay trực tiếp ở mọi nơi.
- Khi đọc lỗi hoặc điều tra bug, xác định rõ từng tên đang tham chiếu **local**, **parameter**, **instance field** hay **static field**.

Ví dụ truy cập trường instance từ static theo đối tượng được truyền vào:

~~~java
static int readCount(Counter counter) {
    return counter.current();
}
~~~

Những lựa chọn này giúp mã dễ bảo trì; bản thân từ khóa `this` không làm một phép gán đúng về mặt nghiệp vụ nếu điều kiện hoặc giá trị truyền vào đã sai.

## 8. Chương trình Java 17+ chạy độc lập

Tạo file **FieldShadowingDemo.java**:

~~~java
public final class FieldShadowingDemo {
    private static String status = "READY";

    private final String name;
    private int count; // Mặc định 0.

    public FieldShadowingDemo(String name) {
        this.name = name;
    }

    private void wrongSet(int count) {
        count = count; // Chỉ tự gán tham số.
    }

    private void setCount(int count) {
        this.count = count;
    }

    private void increase(int count) {
        this.count += count;
    }

    private void showLocal() {
        int count = 100;
        System.out.println("localCount=" + count);
        System.out.println("fieldCount=" + this.count);
    }

    private void showName() {
        String name = "Temporary";
        System.out.println("localName=" + name);
        System.out.println("instanceName=" + this.name);
    }

    private void showBlock() {
        String status = "BLOCK";
        System.out.println("blockStatus=" + status);
        System.out.println("classStatus=" + FieldShadowingDemo.status);
    }

    private static String statusPair(String status) {
        return status + "/" + FieldShadowingDemo.status;
    }

    private static void changeStatus(String status) {
        FieldShadowingDemo.status = status;
    }

    private static int readCount(FieldShadowingDemo demo) {
        return demo.count; // Có đối tượng để đọc field instance.
    }

    private static int plusOne(int count) {
        return count + 1;
    }

    public static void main(String[] args) {
        FieldShadowingDemo demo = new FieldShadowingDemo("Lan");
        System.out.println("constructorName=" + demo.name);
        System.out.println("defaultCount=" + demo.count);

        demo.wrongSet(8);
        System.out.println("afterWrong=" + demo.count);

        demo.setCount(8);
        System.out.println("afterSetter=" + demo.count);
        demo.showLocal();

        demo.increase(3);
        System.out.println("afterIncrease=" + demo.count);
        demo.showName();

        System.out.println("staticValue=" + FieldShadowingDemo.status);
        System.out.println("statusPair=" + statusPair("LOCAL"));
        changeStatus("ACTIVE");
        System.out.println("newStatus=" + FieldShadowingDemo.status);
        System.out.println("newPair=" + statusPair("PARAM"));

        demo.showBlock();
        System.out.println("afterBlockStatus=" + FieldShadowingDemo.status);
        System.out.println("readInstanceFromStatic=" + readCount(demo));
        System.out.println("methodResult=" + plusOne(4));

        {
            int temporary = 2;
            System.out.println("siblingOne=" + temporary);
        }
        {
            int temporary = 3;
            System.out.println("siblingTwo=" + temporary);
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 FieldShadowingDemo.java
java FieldShadowingDemo
~~~

**Expected stdout chính xác:**

~~~text
constructorName=Lan
defaultCount=0
afterWrong=0
afterSetter=8
localCount=100
fieldCount=8
afterIncrease=11
localName=Temporary
instanceName=Lan
staticValue=READY
statusPair=LOCAL/READY
newStatus=ACTIVE
newPair=PARAM/ACTIVE
blockStatus=BLOCK
classStatus=ACTIVE
afterBlockStatus=ACTIVE
readInstanceFromStatic=11
methodResult=5
siblingOne=2
siblingTwo=3
~~~

`afterWrong=0` cho thấy tự gán tham số không cập nhật field; `afterSetter=8` và `afterIncrease=11` là hai cập nhật trường đúng cách qua `this.count`. `localName`/`instanceName` phân biệt local và field, còn `statusPair`/`newPair` chứng minh tham số trùng tên với trường static vẫn có thể được phân biệt qua tên lớp.

## 9. Checklist và bài tập

| Tình huống | Cần làm gì? |
| --- | --- |
| Constructor nhận `String name` và lớp có field `name` | Dùng `this.name = name;` |
| Setter chỉ viết `value = value;` | Kiểm tra lại: thường là lỗi tự gán tham số |
| Local `count` trùng với field `count` | Dùng `count` cho local, `this.count` cho field |
| Tham số `mode` trùng static field `mode` | Dùng `ClassName.mode` khi cần field |
| Dùng `this` trong static method | Không hợp lệ; dùng tên lớp hoặc tham chiếu đối tượng |
| Local mới trùng tham số ở khối lồng | Lỗi trùng khai báo, không phải field shadowing |
| Đọc local chưa gán | Không đạt definite assignment dù tên đang trong scope |
| Hai khối anh em cùng dùng tên `temp` | Hợp lệ khi hai phạm vi không chồng lấn |

**Bài 1.** Viết lớp `Account` có field `balance` và setter `setBalance(int balance)`. Dự đoán trạng thái với `balance = balance;` rồi sửa bằng `this.balance = balance;`.

**Bài 2.** Tạo một phương thức có local trùng tên field, in cả `name` và `this.name`. Điều gì thay đổi khi local ra khỏi khối?

**Bài 3.** Khai báo `static int limit` và phương thức `static void change(int limit)`. Vì sao `limit = limit;` không cập nhật field? Sửa bằng tên lớp.

**Bài 4.** Thử khai báo local `int count` bên trong một phương thức đã nhận tham số `int count`; lý giải lỗi biên dịch, rồi chuyển local đó sang một khối anh em không trùng scope.

**Bài 5.** Phân biệt một field `int value;` chưa gán tường minh với một local `int value;` chưa gán. Biến nào được đọc ngay và tại sao?

### Ghi nhớ

**Tham số/biến cục bộ có thể che khuất field cùng tên mà không xóa field.** Trong phương thức/constructor instance, dùng `this.field` để truy cập đúng trường; trong ngữ cảnh static, dùng `ClassName.staticField`. Tránh lỗi `value = value`, phân biệt shadowing field hợp lệ với local-local trùng phạm vi không hợp lệ, và nhớ rằng scope không thay thế kiểm tra definite assignment.
