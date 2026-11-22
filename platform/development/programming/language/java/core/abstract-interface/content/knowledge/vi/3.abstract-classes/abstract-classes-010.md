# Tổ hợp modifier hợp lệ và xung đột `abstract` với `final` trong Java

`abstract` và `final` đều liên quan đến kế thừa nhưng mang ý nghĩa khác nhau. Ở mức **lớp**, `abstract` ngăn khởi tạo trực tiếp và cho phép khai báo các phương thức cần lớp con triển khai; `final` ngăn lớp khác kế thừa. Ở mức **phương thức**, `abstract` khai báo hành vi chưa có thân, còn `final` bảo vệ một triển khai đã có khỏi việc bị override.

Điểm dễ nhầm là **một `abstract class` có thể chứa trường `final`, phương thức cụ thể `final`, và được kế thừa bởi một lớp con `final`**. Xung đột chỉ xuất hiện khi áp dụng `abstract` cùng `final` cho **chính một khai báo lớp hoặc phương thức**.

Bài học sử dụng Java 17+ và tập trung vào modifier của lớp trừu tượng, phương thức trừu tượng, cũng như những ngoại lệ theo vị trí khai báo.

## 1. Đọc modifier theo nơi nó được khai báo

| Chủ thể | `abstract` | `final` |
| --- | --- | --- |
| Lớp | Không thể `new` trực tiếp; có thể có phương thức trừu tượng. | Không thể bị `extends` bởi lớp khác. |
| Phương thức instance | Không có thân phương thức, kết thúc bằng `;`; lớp con cụ thể phải đáp ứng hợp đồng kế thừa. | Có triển khai và không thể bị ghi đè. |
| Trường | Không hợp lệ. | Chỉ được gán theo quy tắc khởi tạo của Java, sau đó không được gán lại. |
| Constructor | Không hợp lệ. | Không hợp lệ. |

Một `abstract class` **có thể không chứa phương thức `abstract` nào**. Lớp có thể trừu tượng chỉ để đóng vai trò lớp cơ sở, chia sẻ triển khai hoặc ngăn người dùng tạo một thể hiện không có ý nghĩa. Chiều ngược lại thì bắt buộc: **lớp khai báo một phương thức `abstract` phải là lớp `abstract`**.

## 2. Modifier trên **lớp trừu tượng**

### 2.1. Khai báo top-level và lớp thành viên

| Khai báo | Hợp lệ? | Lý do |
| --- | --- | --- |
| `abstract class Base {}` | Có | Lớp top-level phạm vi package-private. |
| `public abstract class Base {}` | Có | Lớp top-level công khai; nếu là top-level `public`, tệp nguồn phải đặt tên `Base.java`. |
| `final abstract class Base {}` | **Không** | `final` cấm kế thừa nhưng `abstract` cần để ngỏ lớp con. |
| `private abstract class Base {}` ở top-level | **Không** | `private` không được áp dụng cho lớp top-level. |
| `protected abstract class Base {}` ở top-level | **Không** | `protected` dành cho lớp thành viên phù hợp, không phải top-level. |
| `static abstract class Base {}` ở top-level | **Không** | Lớp top-level không thể khai báo `static`. |
| `private static abstract class Base {}` bên trong một lớp | Có | Lớp **thành viên** có thể đồng thời `private`, `static`, `abstract`. |
| `protected abstract class Base {}` bên trong một lớp | Có | Lớp thành viên có thể `protected abstract`. |
| `abstract sealed class Base permits Child {}` | Có, khi `Child` hợp lệ | Chỉ các lớp được cho phép mới kế thừa trực tiếp. |
| `abstract non-sealed class Child extends Base {}` | Có, nếu `Base` là lớp `sealed` cho phép trực tiếp `Child` | Mở lại khả năng kế thừa từ nhánh `Child`. |

`static abstract class` chỉ hợp lệ ở ngữ cảnh lớp thành viên: `static` mô tả quan hệ giữa **lớp lồng nhau** và lớp bao ngoài, không biến các phương thức `abstract` của nó thành phương thức static.

Từ Java 17, `sealed` quy định các lớp con trực tiếp được phép; mỗi lớp con trực tiếp đó phải là `final`, `sealed` hoặc `non-sealed`. Ba modifier `final`, `sealed`, `non-sealed` loại trừ lẫn nhau **trên cùng một lớp**. `abstract sealed` có ý nghĩa vì một lớp cha vẫn có thể trừu tượng dù chỉ giới hạn những lớp con nào được phép tồn tại. `non-sealed` không được dùng tùy ý cho một lớp không trực tiếp kế thừa lớp/interface `sealed`.

### 2.2. Trường hợp `abstract class` chứa thành viên `final`

Đoạn khai báo sau **hợp lệ**:

```java
abstract class Parent {
    private final int id;

    protected Parent(int id) {
        this.id = id;
    }

    public final int id() {
        return id;
    }

    public abstract String name();
}
```

Ở đây `Parent` là `abstract`, trường `id` là `final`, phương thức **có thân** `id()` là `final`, còn `name()` là `abstract`. Chúng tác động đến **ba chủ thể khác nhau**; không xung đột.

Một lớp con **cụ thể** có thể là `final` và vẫn `extends Parent`, miễn là nó triển khai đầy đủ phương thức trừu tượng kế thừa. `final` của lớp con chỉ ngăn các lớp khác kế thừa tiếp từ lớp con ấy. Lớp trừu tượng cũng có thể chứa constructor, phương thức cụ thể `private`, `static`, `synchronized` hoặc `final` theo đúng quy tắc Java. Không được suy ra rằng mọi phương thức của một lớp `abstract` cũng phải `abstract`.

## 3. Modifier trên **phương thức trừu tượng**

Một phương thức `abstract` trong `abstract class` là phương thức **instance** không có phần thân, kết thúc bằng `;`. Quyền truy cập được phép: `public`, `protected` hoặc package-private khi không viết modifier truy cập.

| Khai báo bên trong `abstract class` | Hợp lệ? | Lý do |
| --- | --- | --- |
| `public abstract void run();` | Có | Có thể được lớp con ghi đè và triển khai. |
| `protected abstract void run();` | Có | Cho phép lớp con truy cập, override. |
| `abstract void run();` | Có | Package-private; cần cân nhắc khi có lớp con ở package khác. |
| `private abstract void run();` | **Không** | Phương thức `private` không thể override. |
| `abstract final void run();` | **Không** | `final` cấm ghi đè, ngược với yêu cầu triển khai của `abstract`. |
| `abstract static void run();` | **Không** | `static` thuộc lớp, thực hiện *method hiding* thay vì override instance. |
| `abstract synchronized void run();` | **Không** | `synchronized` là đặc tính thực thi của phương thức có thân. |
| `abstract native void run();` | **Không** | `native` không được tổ hợp với `abstract`. |
| `abstract strictfp void run();` | **Không** | Hai modifier bị cấm kết hợp cho một phương thức; `strictfp` còn là đặc tính đã trở nên dư thừa trong Java hiện đại. |
| `abstract void run() {}` | **Không** | Phương thức trừu tượng không được có thân, kể cả thân rỗng. |

Các lưu ý liên quan:

- `abstract` method vẫn có thể khai báo tham số, generic type, giá trị trả về và `throws`; điểm khác biệt nằm ở việc không có thân và cần được triển khai qua kế thừa.
- Constructor, trường, initializer và phương thức static không thể được khai báo `abstract`.
- Modifier như `private`, `final`, `static`, `synchronized` có thể hợp lệ với **phương thức cụ thể có thân** trong một lớp `abstract`; chỉ tổ hợp chúng với `abstract` trên cùng phương thức mới gây lỗi.
- Với `interface`, một phương thức trừu tượng thông thường mặc định là `public abstract`. `interface` có thể khai báo phương thức `default`, `static` hoặc `private` **có thân**; điều này không khiến `private abstract`, `static abstract` hay `final abstract` trở nên hợp lệ.

## 4. Ví dụ đầy đủ chạy bằng Java 17+

Tạo tệp **`ModifierDemo.java`**:

```java
public class ModifierDemo {
    static abstract class Shape {
        private final String label;

        protected Shape(String label) {
            this.label = label;
        }

        public final String label() {
            return label;
        }

        public abstract int area();

        public String kind() {
            return "Shape";
        }

        public static String unit() {
            return "square units";
        }
    }

    static final class Rectangle extends Shape {
        private final int width;
        private final int height;

        Rectangle(int width, int height) {
            super("rectangle");
            this.width = width;
            this.height = height;
        }

        @Override
        public int area() {
            return width * height;
        }

        @Override
        public String kind() {
            return "Rectangle";
        }
    }

    public static void main(String[] args) {
        Shape shape = new Rectangle(3, 4);
        System.out.println(shape.label());
        System.out.println(shape.area());
        System.out.println(shape.kind());
        System.out.println(Shape.unit());
    }
}
```

Biên dịch và chạy:

```bash
javac ModifierDemo.java
java ModifierDemo
```

Kết quả stdout chính xác:

```text
rectangle
12
Rectangle
square units
```

Giải thích:

1. `Shape` là lớp **thành viên** nên `static abstract` hợp lệ. `new Shape(...)` trực tiếp không hợp lệ vì `Shape` là `abstract`.
2. `Shape.area()` không có thân, nên lớp cụ thể `Rectangle` phải cung cấp một triển khai.
3. `Shape.label()` là phương thức instance `final` **có thân**; lớp con không thể override `label()`.
4. Trường `private final String label` được khởi tạo trong constructor cha; nó không tác động đến quyền kế thừa.
5. `Shape.unit()` là phương thức `static` **cụ thể**, nên không xung đột với lớp trừu tượng.
6. `Rectangle` là `final` nhưng vẫn kế thừa hợp lệ từ `Shape`: nó chỉ không cho lớp **khác** kế thừa tiếp từ `Rectangle`.
7. `kind()` là phương thức instance cụ thể cho phép override; lời gọi qua tham chiếu kiểu `Shape` thực thi phiên bản của `Rectangle`.

Nếu bỏ `Rectangle.area()` mà vẫn giữ `Rectangle` là lớp cụ thể, `javac` sẽ báo lỗi do chưa triển khai phương thức trừu tượng. Nếu cố thêm `@Override public String label() { return "new"; }` vào `Rectangle`, cũng sẽ lỗi vì đang override phương thức `final`.

## 5. `abstract sealed` hợp lệ từ Java 17

Tạo tệp **`SealedAbstractDemo.java`**:

```java
public class SealedAbstractDemo {
    abstract static sealed class Result permits Success, Failure {
        abstract String describe();
    }

    static final class Success extends Result {
        @Override
        String describe() {
            return "OK";
        }
    }

    static non-sealed class Failure extends Result {
        @Override
        String describe() {
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        Result result = new Success();
        System.out.println(result.describe());
    }
}
```

Lệnh:

```bash
javac SealedAbstractDemo.java
java SealedAbstractDemo
```

Stdout:

```text
OK
```

`Result` trừu tượng nên không thể tạo trực tiếp, nhưng cho phép đúng hai lớp con trực tiếp `Success` và `Failure`. `Success` chọn `final` để kết thúc nhánh kế thừa; `Failure` chọn `non-sealed` để cho phép lớp khác kế thừa nó. Cả hai đã triển khai `describe()`. Một lớp khác trực tiếp `extends Result` mà không nằm trong `permits` sẽ bị trình biên dịch từ chối.

## 6. Các trường hợp **cố ý không biên dịch** và cách khắc phục

Những đoạn dưới đây là **ví dụ lỗi độc lập**, không phải mã để chạy cùng hai chương trình phía trên. Nội dung thông báo lỗi của `javac` có thể khác nhau theo phiên bản.

### 6.1. Xung đột `abstract final` trên lớp

```java
abstract final class WrongBase {}
```

Lớp `abstract` cần có khả năng được lớp khác kế thừa để trở thành lớp cụ thể; lớp `final` lại cấm mọi lớp con. Đổi thành `abstract class WrongBase {}` khi cần lớp cha trừu tượng, hoặc `final class WrongBase {}` khi muốn lớp cụ thể không kế thừa tiếp.

### 6.2. Xung đột `abstract final` trên phương thức

```java
abstract class WrongBase {
    public final abstract void execute();
}
```

`execute()` không có triển khai nhưng lại cấm override. Nếu đây là hợp đồng bắt buộc, chọn `public abstract void execute();`. Nếu phải cố định triển khai, chọn một **phương thức cụ thể** có thân và `final`, ví dụ `public final void execute() { System.out.println("run"); }`.

### 6.3. Phương thức trừu tượng lại `private`, `static`, `synchronized`

```java
abstract class WrongBase {
    private abstract void a();
    static abstract void b();
    abstract synchronized void c();
}
```

`private` không cho ghi đè, `static` không tham gia override instance, còn `synchronized` thuộc logic thực thi một phương thức có thân. Khi cần hợp đồng, chọn `public abstract`, `protected abstract` hoặc package-private `abstract`; khi cần helper private/static hoặc một phương thức đã đồng bộ hóa, cung cấp thân cụ thể và bỏ `abstract`.

Tương tự, `abstract native` và `abstract strictfp` trên cùng phương thức đều không hợp lệ.

### 6.4. Lớp không `abstract` chứa phương thức `abstract`

```java
class WrongBase {
    abstract void execute();
}
```

Sửa bằng `abstract class WrongBase` hoặc cung cấp thân cho `execute()`.

### 6.5. Phương thức `abstract` có thân

```java
abstract class WrongBase {
    abstract void execute() {
        System.out.println("run");
    }
}
```

Dù phần thân rỗng hay có câu lệnh, cú pháp vẫn sai. Hoặc bỏ phần thân và kết thúc bằng `;`, hoặc bỏ `abstract`.

### 6.6. Áp dụng `abstract` cho record

```java
abstract record Point(int x, int y) {}
```

Record là kiểu không thể dùng làm lớp cơ sở để kế thừa như class thông thường; không cho khai báo `abstract record`. Nếu cần hợp đồng đa hình, cân nhắc interface hoặc lớp trừu tượng thay cho record.

## 7. Quy tắc override có liên quan

Lớp con **cụ thể** phải hoàn thành các phương thức trừu tượng còn hiệu lực; lớp con **vẫn trừu tượng** có thể tiếp tục hoãn triển khai. Một override không được làm quyền truy cập hẹp hơn, không được mở rộng checked exception trái quy tắc và phải giữ kiểu trả về tương thích (có thể là kiểu con covariant). Nên dùng `@Override` để compiler xác minh chữ ký.

Ví dụ hợp lệ ở cấp tệp (không có `main`):

```java
abstract class Processor {
    protected abstract String process(String input);
}

final class UpperProcessor extends Processor {
    @Override
    public final String process(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

`Processor.process` là `protected abstract` trong cha, còn `UpperProcessor.process` là `public final` **có thân** trong con. Mở rộng quyền truy cập từ `protected` lên `public` là hợp lệ. Phương thức sau khi được triển khai hoàn toàn có thể đánh dấu `final`. Lớp con cũng có thể là `final`.

Ngược lại, **một phương thức cụ thể đã mang `final` ở cha** không thể override ở con, bất kể lớp cha có `abstract` hay không. Cần xem modifier gắn với chính khai báo nào trước khi xác định lỗi.

## 8. Checklist và tự kiểm tra

1. Xác định chủ thể: lớp top-level, lớp thành viên, phương thức instance, phương thức static, trường hay constructor.
2. `abstract final` trên **cùng một lớp** luôn sai, bất kể thứ tự từ khóa.
3. `abstract` cùng `final`, `private`, `static`, `synchronized`, `native` hoặc `strictfp` trên **cùng phương thức** là sai.
4. Phương thức `abstract` kết thúc bằng `;`, không có thân; lớp khai báo nó phải `abstract`.
5. `final` của **trường**, của **phương thức có thân** và của **lớp con đã triển khai đủ hợp đồng** có thể cùng tồn tại với một lớp cha `abstract`.
6. Lớp top-level không nhận `private`, `protected`, `static`; lớp thành viên có quy tắc riêng.
7. Với `sealed`, kiểm tra `permits` và xem từng lớp con trực tiếp đã khai báo `final` / `sealed` / `non-sealed` đúng chưa.
8. Với lỗi kế thừa, kiểm tra cả các phương thức abstract chưa được thực thi và các phương thức `final` không được override.

**Câu hỏi:** `abstract class A { final int id = 1; abstract void run(); }` có hợp lệ không? **Có.** `final` gắn với trường `id`, còn `abstract` gắn với lớp `A` và phương thức `run()`.

**Câu hỏi:** `final class B extends A { @Override void run() {} }` có hợp lệ không (với `A` ở trên)? **Có.** `B` triển khai `run()` rồi cấm các lớp khác kế thừa tiếp từ `B`.