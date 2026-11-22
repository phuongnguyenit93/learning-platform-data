# Phân biệt nạp chồng, ghi đè và che khuất trong Java

## 1. Ba cơ chế có tên phương thức giống nhau nhưng không cùng ý nghĩa

Trong Java, khi gặp hai khai báo cùng tên, không thể lập tức kết luận chúng là **nạp chồng** (*overloading*) hay **ghi đè** (*overriding*). Cần xem **danh sách tham số**, **quan hệ lớp cha–lớp con**, **phương thức instance hay static**, và đôi khi cả **kiểu của biểu thức gọi**. Ngoài ra, tên field trùng giữa lớp cha và lớp con, hoặc biến cục bộ trùng tên field, có thể dẫn tới các dạng **che khuất** (*hiding/shadowing*) với quy tắc khác method.

- **Nạp chồng (overloading):** nhiều phương thức **cùng tên**, có **danh sách tham số khác nhau một cách hợp lệ**. Trình biên dịch chọn chữ ký áp dụng được dựa vào **kiểu tĩnh của đối số**, số tham số, phép chuyển đổi và luật *most-specific*. Nạp chồng có thể xuất hiện trong cùng lớp hoặc giữa các phương thức được thừa hưởng và khai báo mới.
- **Ghi đè (overriding):** lớp con cung cấp implementation cho một **instance method** có chữ ký tương ứng của kiểu cha theo quy tắc Java. Khi gọi phương thức có thể override, **kiểu thực tế của đối tượng nhận lời gọi** quyết định implementation được chạy lúc runtime (*dynamic dispatch*).
- **Che khuất (hiding):** một khai báo ở phạm vi cụ thể làm tên thành viên cùng tên ở phạm vi khác không còn được phân giải như trước. Trường hợp thường học cùng hai cơ chế trên là **static method hiding**: lớp con khai báo static method có chữ ký tương ứng với static method của superclass. Với **field hiding**, field cùng tên ở lớp con cũng che khuất field lớp cha khi truy cập theo quy tắc kiểu tĩnh; field không có dynamic dispatch.

> **Mấu chốt:** *overloading chọn chữ ký theo lời gọi tại compile time; overriding chọn implementation của instance method tại runtime; static method hiding không dùng dynamic dispatch*. Field hiding và local-variable shadowing là các dạng che khuất tên riêng, cần phân biệt với static method hiding.

## 2. Bảng đối chiếu tổng thể

| Tiêu chí | Nạp chồng — overloading | Ghi đè — overriding | Che khuất static method — hiding |
| --- | --- | --- | --- |
| Các phương thức có cùng tên? | Có | Có | Có |
| Danh sách tham số | **Khác** hợp lệ | **Tương ứng** theo quy tắc override | **Tương ứng** theo quy tắc hide |
| Quan hệ kế thừa | Không bắt buộc; có thể trong cùng lớp | Có quan hệ siêu kiểu/subtype phù hợp | Thường giữa subclass và superclass |
| Loại method | Có thể là instance hoặc static | **Instance method**, không phải static | **Static method** |
| Quyết định chính | Compile time dựa vào kiểu đối số và overload khả dụng | Runtime dựa vào receiver thực tế, sau khi chữ ký đã được chọn | Compile time dựa vào kiểu tại vị trí tham chiếu |
| `@Override` | Không dùng cho method chỉ overload | Nên dùng để kiểm tra override | Không dùng; static không override |
| Kiểu trả về | Có thể khác, nhưng **không đủ** để overload | Phải tương thích; reference có thể covariant | Phải thỏa điều kiện tương thích theo quy tắc hiding |
| `final` | Vẫn có thể overload bằng chữ ký khác | Không thể override final instance method | Không thể hide final static method |
| Tác động runtime | Phụ thuộc method được chọn; method instance ấy vẫn có thể override | Dispatch tới implementation cụ thể theo object | Không đổi đích thành static method subclass chỉ vì object runtime là subclass |

Bảng nói về **method**. Với **field**, không có overloading hay overriding theo nghĩa method. Một field ở subclass cùng tên field superclass có thể **hide field**, dù cả hai vẫn tồn tại trong cấu trúc đối tượng hoặc lớp.

## 3. Ví dụ chạy độc lập: nhìn thấy cả ba cơ chế trên cùng một hierarchy

Tạo tệp **`PolymorphismComparisonDemo.java`** với toàn bộ mã Java 17+ sau:

```java
class Parent {
    String label = "Parent.field";

    String describe() {
        return "Parent.instance";
    }

    static String category() {
        return "Parent.static";
    }

    String print(Object value) {
        return "Parent.print(Object)";
    }
}

class Child extends Parent {
    String label = "Child.field";

    @Override
    String describe() {
        return "Child.instance";
    }

    static String category() {
        return "Child.static";
    }

    String print(String value) {
        return "Child.print(String)";
    }
}

public class PolymorphismComparisonDemo {
    public static void main(String[] args) {
        Parent parentRef = new Child();
        Child childRef = new Child();

        System.out.println(parentRef.describe());
        System.out.println(childRef.describe());

        System.out.println(Parent.category());
        System.out.println(Child.category());
        System.out.println(parentRef.category());
        System.out.println(childRef.category());

        System.out.println(parentRef.print("Java"));
        System.out.println(childRef.print("Java"));
        System.out.println(childRef.print((Object) "Java"));

        System.out.println(parentRef.label);
        System.out.println(childRef.label);
        System.out.println(((Parent) childRef).label);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac PolymorphismComparisonDemo.java
java PolymorphismComparisonDemo
```

**Standard output chính xác:**

```text
Child.instance
Child.instance
Parent.static
Child.static
Parent.static
Child.static
Parent.print(Object)
Child.print(String)
Parent.print(Object)
Parent.field
Child.field
Parent.field
```

Bốn phần đáng chú ý:

**A. Ghi đè instance method:** `parentRef` có **kiểu tĩnh `Parent`** nhưng trỏ tới **object `Child`**. `parentRef.describe()` chạy `Child.describe()` vì đây là instance method đã override. `childRef.describe()` cũng chạy implementation đó.

**B. Che khuất static method:** `Child.category()` khai báo static method tương ứng với `Parent.category()`. `Parent.category()` trả `Parent.static`, còn `Child.category()` trả `Child.static`. Dù Java cho phép biểu thức `parentRef.category()`, kết quả vẫn là `Parent.static` theo **kiểu tĩnh `Parent`** của biểu thức; `childRef.category()` trả `Child.static` theo **kiểu tĩnh `Child`**. Trong code thật nên gọi static method qua **tên lớp**.

**C. Nạp chồng:** `Parent.print(Object)` và `Child.print(String)` là hai overload (khác tham số). Qua biến `Parent parentRef`, trình biên dịch chỉ tìm được `print(Object)` thích hợp theo kiểu `Parent`, nên `parentRef.print("Java")` trả `Parent.print(Object)`. Qua biến `Child childRef`, cả hai chữ ký được nhìn thấy và `print(String)` cụ thể hơn cho đối số `String`. Ép kiểu đối số `(Object) "Java"` khiến `childRef.print((Object) "Java")` chọn `print(Object)`. Trong chương trình này `Child` **không override `print(Object)`**, nên phương thức được kế thừa từ `Parent` chạy.

**D. Che khuất field:** `Parent.label` và `Child.label` là **hai field khác nhau** cùng tên. Truy cập field được phân giải theo **kiểu tĩnh của biểu thức**: `parentRef.label` trả `Parent.field`, `childRef.label` trả `Child.field`, ép `childRef` sang `Parent` khiến phép truy cập field chọn `Parent.label`. Việc object thực là `Child` không gây field dynamic dispatch.

**Kết luận quan sát:** cùng một `new Child()` có thể gọi một method override của `Child`, một static method được chọn theo kiểu `Parent`, một overload phụ thuộc kiểu đối số, và field có cùng tên nhưng vẫn được chọn theo kiểu tĩnh. Không thể dùng duy nhất “object thực tế là lớp nào?” để trả lời tất cả.

## 4. Nạp chồng: cùng tên, khác danh sách tham số

Hai khai báo tạo overload khi có **chữ ký khác nhau hợp lệ**: khác số tham số, kiểu tham số, thứ tự kiểu hoặc quan hệ signature cho phép theo JLS. Trong trường hợp không generic, có thể nhớ **tên + danh sách kiểu tham số theo thứ tự** là yếu tố cốt lõi. Tên tham số và kiểu trả về không được dùng để phân biệt hai method cùng chữ ký.

```java
class Converter {
    String convert(int number) {
        return "int=" + number;
    }

    String convert(long number) {
        return "long=" + number;
    }

    String convert(String text, boolean uppercase) {
        return uppercase ? text.toUpperCase() : text;
    }

    String convert(boolean uppercase, String text) {
        return convert(text, uppercase);
    }
}
```

Đây là **khai báo lớp hợp lệ** nhưng không có `main`. Có bốn overload cùng tên `convert` với các danh sách tham số khác nhau. Hai bản cuối khác thứ tự `String, boolean` và `boolean, String`.

Ví dụ **cố ý không biên dịch**:

```java
// class Invalid {
//     int parse(String text) {
//         return Integer.parseInt(text);
//     }
//
//     long parse(String text) {
//         return Long.parseLong(text);
//     }
// }
```

Hai bản `parse(String)` chỉ khác **kiểu trả về**, nên bị coi là khai báo trùng. Viết `public` thay `private`, đổi tên tham số `text` thành `value`, đổi `throws` hoặc thêm `final` cũng không đủ tạo overload.

### Overload được chọn lúc biên dịch

Phân giải overload xem:

1. Tập method cùng tên **có thể tìm thấy và truy cập** từ kiểu tĩnh của receiver/phạm vi hiện tại.
2. Số lượng đối số, kiểu tĩnh từng đối số và phép chuyển đổi phương thức Java cho phép.
3. Các pha áp dụng: dạng phù hợp không cần boxing/varargs trước; tiếp theo có thể xét boxing/unboxing; cuối cùng xét **variable arity** nếu cần.
4. Các overload **cụ thể nhất** trong pha thích hợp; nếu không có lựa chọn duy nhất, compiler báo **ambiguous**.

Dù biến `Object value = "hello";` đang chứa object `String`, khi gọi `process(value)` compiler nhìn đối số kiểu **`Object`**, không tự chuyển sang overload `process(String)`. Đây là khác biệt nền tảng với dispatch của override.

### Boxing, widening và varargs

Tạo tệp **`OverloadingRulesDemo.java`**:

```java
class Choice {
    static String choose(long n) {
        return "long";
    }

    static String choose(Integer n) {
        return "Integer";
    }

    static String choose(int... numbers) {
        return "varargs=" + numbers.length;
    }
}

public class OverloadingRulesDemo {
    public static void main(String[] args) {
        System.out.println(Choice.choose(7));
        System.out.println(Choice.choose(Integer.valueOf(7)));
        System.out.println(Choice.choose());
        System.out.println(Choice.choose(1, 2));
    }
}
```

```bash
javac OverloadingRulesDemo.java
java OverloadingRulesDemo
```

```text
long
Integer
varargs=0
varargs=2
```

- `choose(7)`: `7` có kiểu `int`. Mở rộng nguyên thủy `int → long` được xét trước việc boxing `int → Integer`, nên chọn `choose(long)`.
- `choose(Integer.valueOf(7))`: kiểu biểu thức là `Integer`, khớp bản `choose(Integer)` trước bước unboxing.
- `choose()`: biến thể `int...` nhận 0 phần tử.
- `choose(1, 2)`: biến thể `int...` nhận hai phần tử.

Mỗi overload mới có thể ảnh hưởng đến lời gọi sau **khi biên dịch lại**; ví dụ thêm `convert(String)` vào API vốn chỉ có `convert(Object)` có thể khiến `convert("a")` chọn bản mới.

### `null` và tham số tham chiếu

`null` có thể áp dụng cho nhiều kiểu tham chiếu; nếu hai kiểu không có quan hệ cụ thể hơn, lời gọi có thể mơ hồ:

```java
class Logger {
    static void log(String text) { }
    static void log(Integer number) { }

    static void sample() {
        // log(null);           // Lỗi ambiguous: String hay Integer?
        log((String) null);     // Chọn log(String).
        log((Integer) null);    // Chọn log(Integer).
    }
}
```

Hai method trên cùng tồn tại hợp lệ; **chỉ dòng `log(null)` đã comment là lỗi**. Với overload `log(Object)` và `log(String)`, `log(null)` thường chọn `log(String)` vì `String` cụ thể hơn `Object`. Cast ở đây **không tạo đối tượng**: giá trị vẫn `null`, chỉ thay kiểu tĩnh biểu thức.

### Generic và erasure

`void consume(List<String>)` và `void consume(List<Integer>)` không tạo được hai overload trong cùng một lớp, vì các tham số generic đều bị xóa còn `List` ở erasure, dẫn đến **name clash**.

```java
// import java.util.List;
//
// class InvalidGenerics {
//     void consume(List<String> names) { }
//     void consume(List<Integer> numbers) { }
//     // Lỗi biên dịch vì cả hai có cùng erasure.
// }
```

Tương tự, `void send(int... values)` và `void send(int[] values)` không thể là hai overload riêng; tham số varargs ở chữ ký tương ứng kiểu mảng `int[]`. Quy tắc chữ ký generic và *override-equivalent signatures* có chi tiết hơn mẹo đơn giản “ký tự khai báo khác nhau”.

## 5. Ghi đè: instance method của lớp con thay thế implementation kế thừa

**Overriding** xảy ra khi subtype cung cấp một instance method thỏa quy tắc chữ ký, khả năng truy cập và kiểu trả về phù hợp với method instance của supertype. Thường sử dụng annotation **`@Override`** để nhờ compiler kiểm tra ý định.

```java
class Notification {
    String send() {
        return "generic";
    }
}

class EmailNotification extends Notification {
    @Override
    String send() {
        return "email";
    }
}
```

Đây là khai báo lớp có thể biên dịch nhưng không có `main`. Với `Notification n = new EmailNotification();`, biểu thức `n.send()` chạy `EmailNotification.send()`. Việc chọn implementation theo **receiver object thực tế** gọi là **dynamic dispatch**.

### Chữ ký và kiểu trả về khi override

Với method không generic thông thường, method override có cùng **tên và danh sách kiểu tham số**. Kiểu trả về phải tương thích:

- Với primitive hoặc `void`, không được tùy tiện đổi sang kiểu khác.
- Với reference type, Java cho phép **covariant return**: lớp con có thể trả về kiểu tham chiếu hẹp hơn, tương thích với kiểu trả về của method bị override.
- `throws` checked exceptions ở lớp con không được rộng hơn các điều kiện Java cho phép từ method superclass; có thể bỏ bớt hoặc dùng exception checked hẹp hơn phù hợp.
- Không được làm **giảm khả năng truy cập**: method `public` của lớp cha phải tiếp tục `public` trong bản override; method `protected` có thể override bằng `protected` hoặc `public` nhưng không giảm xuống `private`.
- Method `final` không thể override. Method `private` của superclass không được kế thừa để override theo cơ chế thông thường; method trùng tên ở subclass có thể là khai báo mới.
- Static method không override instance method; instance method cũng không thể override static method bằng chữ ký tương ứng hợp lệ.
- Một method package-private ở superclass khác package **không nhất thiết được kế thừa/override**; phân tích phải xét quyền truy cập và package, không chỉ hình dạng chữ ký.

Tạo tệp **`CovariantOverrideDemo.java`**:

```java
class Food {
    String name() {
        return "food";
    }
}

class Bread extends Food {
    @Override
    String name() {
        return "bread";
    }
}

class Kitchen {
    Food prepare() {
        return new Food();
    }
}

class Bakery extends Kitchen {
    @Override
    Bread prepare() {
        return new Bread();
    }
}

public class CovariantOverrideDemo {
    public static void main(String[] args) {
        Kitchen kitchen = new Bakery();
        Food item = kitchen.prepare();

        System.out.println(item.name());
        System.out.println(item instanceof Bread);
    }
}
```

Chạy:

```bash
javac CovariantOverrideDemo.java
java CovariantOverrideDemo
```

```text
bread
true
```

`Bakery.prepare()` có kiểu trả về `Bread`, là subtype của `Food`. Đây là **covariant return** hợp lệ khi override `Kitchen.prepare()`. Biến `kitchen` có kiểu tĩnh `Kitchen` nhưng runtime là `Bakery`, nên gọi implementation lớp con và tạo `Bread`. Biến `item` có kiểu `Food`, song receiver của `item.name()` là `Bread`, vì vậy kết quả `bread`.

### `@Override` giúp phát hiện gõ nhầm

```java
class ParentService {
    void start(int retries) { }
}

class ChildService extends ParentService {
    @Override
    void start(int retries) { } // Hợp lệ.

    // @Override
    // void start(long retries) { }
    // Nếu thêm @Override ở start(long) và không có
    // method tương ứng ở superclass/interface: lỗi biên dịch.
}
```

`start(long)` là **overload** của `start(int)` (tham số khác), không phải override. Annotation `@Override` giúp tránh việc vô tình tạo overload do gõ sai kiểu/số tham số khi ý định là ghi đè.

### Có thể override một abstract method

`abstract` chỉ mô tả method chưa có implementation trong kiểu đang khai báo. Concrete subclass triển khai bằng method tương ứng, tức là một quan hệ override/implementation theo quy tắc Java. Ví dụ `Runnable.run()` là contract; lớp hiện thực phải cung cấp `public void run()`, chứ không tạo một overload `run(String)` rồi coi là đủ.

### Ghi đè không bắt buộc khai báo `extends` trực tiếp

Một lớp có thể override method **được kế thừa gián tiếp** qua nhiều tầng superclass, hoặc thực hiện contract được thừa hưởng từ interface. Điều kiện phụ thuộc quan hệ type hierarchy và quy tắc Java. Không nên kiểm tra bằng cách chỉ mở ngay file superclass trực tiếp rồi kết luận thiếu method.

## 6. Che khuất static method: cùng tên và chữ ký nhưng ràng buộc tĩnh

Khi superclass có static method và subclass khai báo static method có chữ ký tương ứng hợp lệ, phương thức ở subclass **hide** phương thức superclass. Đây **không phải overriding**.

Tạo tệp **`StaticHidingDemo.java`**:

```java
class BaseConfig {
    static String source() {
        return "base";
    }
}

class AppConfig extends BaseConfig {
    static String source() {
        return "app";
    }
}

public class StaticHidingDemo {
    public static void main(String[] args) {
        BaseConfig base = new AppConfig();
        AppConfig app = new AppConfig();

        System.out.println(BaseConfig.source());
        System.out.println(AppConfig.source());
        System.out.println(base.source());
        System.out.println(app.source());
    }
}
```

```bash
javac StaticHidingDemo.java
java StaticHidingDemo
```

```text
base
app
base
app
```

`base` và `app` đều trỏ tới object runtime thuộc `AppConfig`. Nhưng `base.source()` được phân giải tĩnh theo kiểu `BaseConfig` của biến, trả `base`. `app.source()` được phân giải theo kiểu `AppConfig`, trả `app`.

Một số IDE/compiler có thể cảnh báo việc gọi static method qua biến tham chiếu vì cú pháp này gây nhầm với dynamic dispatch. **Cách viết tốt hơn** là `BaseConfig.source()` và `AppConfig.source()`, nêu rõ method thuộc lớp nào. Hai lời gọi qua biến ở ví dụ chỉ nhằm quan sát ràng buộc tĩnh.

### `@Override` không hợp lệ trên static method hiding

```java
class ParentUtil {
    static void reset() { }
}

class ChildUtil extends ParentUtil {
    // @Override             // Nếu dùng -> lỗi biên dịch.
    static void reset() { }   // Static method hiding hợp lệ.
}
```

Một annotation `@Override` trên `ChildUtil.reset()` sẽ không hợp lệ, vì static method không tham gia override instance method.

### Ràng buộc với `final` và visibility

Nếu static method superclass là `final`, subclass không thể khai báo static method có chữ ký tương ứng để hide nó. Bản hiding cũng phải tuân thủ các điều kiện về visibility, return type và `throws` thích hợp. Đặc biệt, một static method không thể hide một instance method cùng chữ ký ở superclass, và instance method không thể override một static method cùng chữ ký.

`static` chỉ liên quan tới method declaration. Không dùng câu “method này static nên object runtime quyết định bản static phù hợp”: đó chính là điều static hiding **không** làm.

### Interface static method có được thừa hưởng như class static method không?

Static method được khai báo trong **interface** không được thừa hưởng bởi các class implement interface theo cách các instance methods thông thường được thừa hưởng. Ví dụ:

```java
interface Tools {
    static String version() {
        return "v1";
    }
}

class ToolImpl implements Tools {
}
```

Gọi `Tools.version()` là hợp lệ; gọi `ToolImpl.version()` không hợp lệ chỉ vì `ToolImpl implements Tools`. Nếu `ToolImpl` tự khai báo một static method `version()`, đó là method riêng của lớp, **không phải override của `Tools.version()`**. Phân tích static hiding nên lấy đúng quan hệ khai báo trong class hierarchy và các quy tắc tương ứng.

## 7. Che khuất field: tên field không có đa hình runtime

Một subclass được phép khai báo field cùng tên với field kế thừa; Java **không coi đây là field overriding**. Mỗi field vẫn có vị trí/trạng thái riêng theo cấu trúc đối tượng hoặc lớp.

Tạo tệp **`FieldHidingDemo.java`**:

```java
class BaseUser {
    String role = "base";

    String baseRole() {
        return role;
    }
}

class AdminUser extends BaseUser {
    String role = "admin";

    String adminRole() {
        return role;
    }

    String inheritedRole() {
        return super.role;
    }
}

public class FieldHidingDemo {
    public static void main(String[] args) {
        AdminUser admin = new AdminUser();
        BaseUser base = admin;

        System.out.println(admin.role);
        System.out.println(base.role);
        System.out.println(admin.adminRole());
        System.out.println(admin.baseRole());
        System.out.println(admin.inheritedRole());
    }
}
```

Lệnh chạy:

```bash
javac FieldHidingDemo.java
java FieldHidingDemo
```

```text
admin
base
admin
base
base
```

Giải thích:

- `AdminUser.role` và `BaseUser.role` **cùng tồn tại**; chúng không tự đồng bộ với nhau.
- `admin.role` dùng field khai báo trong `AdminUser`; `base.role` dùng field của `BaseUser` theo kiểu tĩnh `BaseUser` của biến.
- `admin.adminRole()` đọc `role` trong thân method của `AdminUser` nên đọc field lớp con.
- `admin.baseRole()` thực thi method kế thừa từ `BaseUser` và trả `BaseUser.role`. Đây không phải field dynamic dispatch.
- `admin.inheritedRole()` dùng `super.role` để **chỉ rõ field của superclass**.

Trong thực tế, nên đặt instance fields `private` và truy cập qua method có hợp đồng rõ ràng. Nếu thay `base.role` bằng `base.getRole()` rồi override `getRole()` ở subclass, hành vi có thể **đổi thành dynamic dispatch của method**, nhưng đó là tính đa hình của **method**, không phải field.

### Static field cũng có thể bị hide

`static` không biến field thành polymorphic:

```java
class ParentFlags {
    static String mode = "parent";
}

class ChildFlags extends ParentFlags {
    static String mode = "child";
}
```

`ParentFlags.mode` và `ChildFlags.mode` là **hai static fields** khác nhau. Có thể truy cập rõ ràng qua tên lớp. Nếu dùng biến tham chiếu `ParentFlags ref = new ChildFlags();` và viết `ref.mode`, Java phân giải field theo **kiểu tĩnh `ParentFlags`**, không đổi sang `ChildFlags.mode` theo runtime object.

## 8. Shadowing: biến cục bộ hoặc tham số che khuất tên field

Trong một instance method/constructor, một tham số hoặc biến cục bộ có thể mang tên trùng với field. Khi đó tên đơn `name` ở trong phạm vi biến cục bộ thường chỉ tới **biến cục bộ/tham số**, còn `this.name` chỉ rõ field của object.

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    String getName() {
        return name;
    }
}
```

`this.name = name;` có hai vế khác nhau:

- **Vế trái `this.name`**: field của instance hiện tại.
- **Vế phải `name`**: tham số có cùng tên, che khuất field trong phạm vi tương ứng.

Nếu viết `name = name;`, phép gán chỉ tác động đến biến tham số (về bản chất tự gán) và **không thay đổi field**. Đây là **shadowing tên biến**, không phải overriding hay overloading.

Ví dụ khác:

```java
class Counter {
    private int count = 5;

    int compute() {
        int count = 10;          // Local che khuất field.
        return count + this.count;
    }
}
```

`new Counter().compute()` trả `15`: local `count == 10`, field `this.count == 5`. Không có phương thức nào bị override/hide trong ví dụ này.

### Shadowing và hiding có dùng được thay nhau không?

Trong tiếng Việt, “che khuất” đôi khi dùng cho cả *hiding* lẫn *shadowing*. Để chẩn đoán chính xác:

- **Method hiding:** static method ở lớp con che static method superclass với chữ ký tương ứng.
- **Field hiding:** field ở lớp con che field superclass cùng tên.
- **Variable shadowing:** tên local/parameter che tên field hoặc tên bên ngoài trong phạm vi cú pháp.

Ba trường hợp đều có hiện tượng **tên được phân giải khác đi**, nhưng quy tắc và cách sửa không giống nhau. Nên sử dụng thuật ngữ cụ thể khi thảo luận code.

## 9. Một method ở lớp con vừa override, vừa tham gia overload được không?

Có. Việc **override hay overload là quan hệ giữa những cặp khai báo nhất định**, không phải một nhãn cố định cho mọi method cùng tên trong một lớp.

Tạo tệp **`MixedMethodsDemo.java`**:

```java
class ParentParser {
    String parse(Object value) {
        return "Parent:Object";
    }

    String parse(int value) {
        return "Parent:int";
    }
}

class ChildParser extends ParentParser {
    @Override
    String parse(Object value) {
        return "Child:Object";
    }

    String parse(String value) {
        return "Child:String";
    }
}

public class MixedMethodsDemo {
    public static void main(String[] args) {
        ParentParser parent = new ChildParser();
        ChildParser child = new ChildParser();

        System.out.println(parent.parse("Java"));
        System.out.println(parent.parse(5));
        System.out.println(child.parse("Java"));
        System.out.println(child.parse((Object) "Java"));
        System.out.println(child.parse(5));
    }
}
```

Chạy:

```bash
javac MixedMethodsDemo.java
java MixedMethodsDemo
```

```text
Child:Object
Parent:int
Child:String
Child:Object
Parent:int
```

Phân tích:

1. `ChildParser.parse(Object)` **override** `ParentParser.parse(Object)`.
2. `ChildParser.parse(String)` là overload khác theo tham số, **không override** `parse(Object)`.
3. Với `ParentParser parent`, `parent.parse("Java")` chọn chữ ký `parse(Object)` ở compile time vì kiểu `ParentParser` không khai báo overload `parse(String)`. Runtime gọi implementation override `ChildParser.parse(Object)`, nên in `Child:Object`.
4. `parent.parse(5)` chọn `parse(int)` vì literal `5` có kiểu `int` và khớp chính xác. `ChildParser` không override chữ ký này, nên trả `Parent:int`.
5. Với `ChildParser child`, `child.parse("Java")` chọn overload `parse(String)` cụ thể hơn và trả `Child:String`.
6. `child.parse((Object) "Java")` chọn `parse(Object)`; runtime dùng implementation override trong `ChildParser`.
7. `child.parse(5)` chọn bản `parse(int)` được kế thừa, trả `Parent:int`.

Vì thế một dự án có thể đồng thời dùng **compile-time overload resolution** và **runtime overriding dispatch** trong **cùng lời gọi**. Hãy trả lời hai câu hỏi theo thứ tự: “Chữ ký nào được chọn?” rồi “Implementation nào của chữ ký đó được chạy?”.

## 10. Constructor: có nạp chồng nhưng không ghi đè

Constructor không phải method thường; Java cho phép **nhiều constructor khác danh sách tham số** trong cùng lớp (constructor overloading). Constructor **không kế thừa**, nên **không override** hoặc hide constructor của superclass.

```java
class Job {
    private final String name;
    private final int priority;

    Job(String name) {
        this(name, 1);
    }

    Job(String name, int priority) {
        this.name = name;
        this.priority = priority;
    }

    String summary() {
        return name + ":" + priority;
    }
}
```

`new Job("daily")` và `new Job("daily", 3)` chọn **hai constructor overload**. Trong constructor một tham số, `this(name, 1)` gọi constructor khác của **cùng instance**, không tạo object thứ hai. Không dùng `@Override` trên constructor.

Nếu subclass không khai báo constructor, compiler có thể sinh constructor mặc định tùy điều kiện của superclass. Nhưng đó là **constructor của subclass**, không phải constructor superclass được kế thừa.

## 11. Phân biệt thêm: cùng tên nhưng không override do `private` hoặc `static`

### Private method trong superclass

```java
class Base {
    private String detail() {
        return "base";
    }

    String summary() {
        return detail();
    }
}

class Derived extends Base {
    String detail() {
        return "derived";
    }
}
```

Đây là khai báo lớp hợp lệ. `Derived.detail()` **không override** `Base.detail()` vì method `private` của superclass không được kế thừa để override. `new Derived().summary()` trả `base`: thân `Base.summary()` gọi `Base.detail()` của chính lớp `Base`. Còn `new Derived().detail()` trả `derived`.

Không suy luận override chỉ từ việc hai method cùng tên, cùng tham số; phải xét **access modifier** và quan hệ kế thừa thật sự.

### Static method không tham gia override

```java
// class A {
//     static void work() { }
// }
// class B extends A {
//     @Override
//     static void work() { } // Lỗi vì static method không override.
// }
```

Bỏ `@Override` thì `B.work()` là **hiding** hợp lệ nếu các ràng buộc còn lại được đáp ứng. Không bỏ từ khóa `static` ở lớp con để biến nó thành instance override của một superclass static method: tổ hợp instance/static cùng chữ ký giữa subclass và superclass là xung đột bị Java chặn.

### Final method

```java
// class Parent {
//     final void save() { }
// }
// class Child extends Parent {
//     void save() { } // Lỗi: override final method.
// }
```

Nhưng `void save(String path) { }` ở subclass có thể **overload** với `Parent.save()` vì khác danh sách tham số. `final` ngăn **override** (hoặc hide khi áp dụng cho static method tương ứng), chứ không tự chặn mọi overload.

## 12. Câu hỏi “phương thức nào chạy?” có hai bước độc lập

Khi gặp lời gọi `receiver.method(args)`:

**Bước 1 — Compile time:** kiểu tĩnh của `receiver` và `args` quyết định những khai báo method nào nhìn thấy/áp dụng, và chữ ký overload nào được chọn. Compiler cũng kiểm tra accessibility, varargs, generic inference và nhiều ràng buộc khác.

**Bước 2 — Runtime:** với **instance method có thể override**, object receiver thực tế quyết định implementation của chữ ký đã chọn. Với **static method**, không có dynamic dispatch theo object runtime; với **field access**, field cũng được phân giải theo kiểu tĩnh.

Ví dụ suy luận:

```java
class Vehicle {
    String drive(Object mode) {
        return "Vehicle:Object";
    }
}

class Car extends Vehicle {
    @Override
    String drive(Object mode) {
        return "Car:Object";
    }

    String drive(String mode) {
        return "Car:String";
    }
}
```

Nếu `Vehicle v = new Car();`:

- `v.drive("eco")`: chữ ký được chọn là `drive(Object)` dựa vào kiểu tĩnh `Vehicle`; runtime chạy `Car.drive(Object)` và trả `Car:Object`.
- `((Car) v).drive("eco")`: kiểu tĩnh sau cast là `Car`, compiler chọn overload `drive(String)`; kết quả `Car:String`.
- `v.drive((Object) "eco")`: đối số được cast sang `Object`, chọn `drive(Object)`; runtime vẫn chạy `Car.drive(Object)`.

Đây là **khai báo lớp minh họa**, chưa có `main`. Nó làm rõ một điều: **ép kiểu tham chiếu** có thể thay đổi **tập overload** mà compiler xét, trong khi object thực tế không đổi. Bản thân cast không tạo đối tượng mới.

## 13. Che khuất khác với truy cập được đến thành viên cũ

Một tên bị hide **không có nghĩa implementation hoặc field của superclass bị xóa**.

- Với field, `super.fieldName` hoặc truy cập qua tham chiếu có kiểu superclass thích hợp có thể nhắm tới field superclass, nếu quyền truy cập cho phép.
- Với instance method override, trong một instance method của subclass, `super.method()` có thể yêu cầu triển khai superclass theo quy tắc `super`, dù gọi bình thường `this.method()` dispatch tới bản override.
- Với static method hiding, gọi rõ `Superclass.staticMethod()` vẫn dùng method superclass.
- Với shadowing bởi local variable, `this.fieldName` phân biệt field khỏi local.

Ví dụ:

```java
class BaseCounter {
    int value = 2;

    String describe() {
        return "Base:" + value;
    }

    static String category() {
        return "Base";
    }
}

class DetailedCounter extends BaseCounter {
    int value = 5;

    @Override
    String describe() {
        return super.describe() + ", Child:" + this.value;
    }

    static String category() {
        return "Child";
    }
}
```

Trong ngữ cảnh thích hợp:

- `new DetailedCounter().describe()` trả `Base:2, Child:5` vì `super.describe()` chạy method superclass (trong đó `value` là field của `BaseCounter`).
- `BaseCounter.category()` và `DetailedCounter.category()` là hai static methods phân giải rõ ràng theo tên lớp.
- Hai field `value` cùng tồn tại và không tự cập nhật đồng bộ chỉ vì trùng tên.

Dùng `super` để tái sử dụng implementation có thể hữu ích, nhưng một thiết kế với nhiều field trùng tên thường khó đọc và dễ tạo trạng thái không nhất quán. Ưu tiên encapsulation với field `private` và API rõ ràng.

## 14. Quyền truy cập và ràng buộc override/hiding

Để một khai báo ở lớp con thực sự override/hide thành viên superclass, phải xét **kế thừa hợp lệ** và **quy tắc truy cập**:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Superclass method `public` | Bản override/hide tương ứng không được giảm visibility. |
| Superclass method `protected` | Bản override hợp lệ có thể giữ `protected` hoặc mở thành `public`. |
| Superclass method package-private | Quan hệ package quyết định khả năng kế thừa/override; khác package phải xem kỹ. |
| Superclass method `private` | Không phải method được thừa hưởng để override/hide theo cách thông thường. |
| Superclass method `final` | Không được override final instance method; không được hide final static method theo chữ ký tương ứng. |
| Superclass method `static` | Không thể có instance override cùng chữ ký; bản static ở subclass có thể hide khi hợp lệ. |
| Method trong interface | Default/abstract method có quy tắc implementation/override; static interface method không thừa hưởng như static class method. |
| Checked exception | Bản override/hide theo quy tắc liên quan không tự được mở rộng checked throws tùy ý. |
| Kiểu trả về | Phải return-type-substitutable khi quan hệ override/hide yêu cầu, không tùy tiện đổi sang kiểu không tương thích. |

Những quy tắc này giải thích tại sao chỉ nhìn hai dòng `void run()` ở hai file có thể chưa đủ để phán đoán “override”: phải đọc modifier, package, superclass/interface và chữ ký thật.

### Override package-private qua ranh giới package

Nếu superclass nằm ở package khác và khai báo method không có modifier truy cập, subclass thường **không thừa hưởng method đó như một method có thể override**. Một method cùng tên/chữ ký được khai báo trong subclass lúc này có thể là method mới. Vì vậy `@Override` rất có giá trị: compiler báo sai nếu ý định override không thực sự xảy ra.

### Covariant return không phải overload theo kiểu trả về

`Food prepare()` ở superclass và `Bread prepare()` ở subclass (với `Bread extends Food`) có thể là **override hợp lệ với covariant return**. Nhưng hai khai báo cùng tên, cùng tham số, khác kiểu trả về **ngay trong một lớp** không tạo overload.

## 15. Những lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Cùng tên nghĩa là override” | Phải kiểm tra danh sách tham số và quan hệ kế thừa. Khác tham số có thể là overload. |
| “Java chọn overload theo object runtime” | Overload resolution dùng kiểu tĩnh. Runtime dispatch chỉ chọn implementation của instance method đã được chọn. |
| “Static method ở lớp con override static method lớp cha” | Đó là **method hiding**, không dynamic overriding. |
| “Field cùng tên được ghi đè” | Field có **hiding**, không có field dynamic dispatch. |
| “Kiểu trả về khác là overload” | Không đủ; chữ ký tham số phải khác hợp lệ. |
| “Tên tham số khác là overload” | Không; tên tham số không phân biệt chữ ký. |
| “`@Override` có thể gắn lên static method hiding” | Không; compiler sẽ bác bỏ annotation đó. |
| “`final` cấm mọi phương thức cùng tên ở subclass” | Cấm override/hide cùng chữ ký tương ứng; overload khác tham số có thể hợp lệ. |
| “`private` method superclass có thể override thông thường” | Không; private method không được thừa hưởng theo cách override. |
| “`super.method()` tạo object cha mới” | Không; dùng superclass implementation trên cùng instance hiện tại. |
| “`List<String>` và `List<Integer>` luôn tạo overload” | Có thể name clash do generic erasure. |
| “Dùng biến kiểu superclass thì mọi member theo runtime subclass” | Instance override có runtime dispatch; static method và field không như vậy. |
| “Cast `(Parent) child` biến object Child thành Parent” | Cast chỉ thay kiểu tĩnh của biểu thức tham chiếu; object runtime vẫn là Child. |
| “Constructor có thể override” | Constructor có thể overload nhưng **không kế thừa/override**. |
| “Một cặp method có cùng tên thì chỉ có một khái niệm áp dụng cho cả hierarchy” | Mỗi cặp chữ ký/khai báo cần xem riêng: một tên có thể vừa có overload, vừa có những override khác nhau. |

## 16. Tự kiểm tra với đáp án

**Câu 1.** Lớp `A` có `void show(int x)`, lớp `B extends A` khai báo `void show(String x)`. Đó là gì?

**Đáp án:** **Overloading**: cùng tên nhưng kiểu tham số khác. `show(String)` không override `show(int)`.

**Câu 2.** Lớp `A` có instance method `String greet()`, lớp `B extends A` có `@Override String greet()`. Với `A value = new B();`, `value.greet()` chạy method nào?

**Đáp án:** Implementation `B.greet()`, vì method là instance method có thể override và runtime receiver là `B`.

**Câu 3.** Nếu `A` và `B extends A` cùng khai báo `static String id()`, `A a = new B(); a.id()` chọn method nào?

**Đáp án:** `A.id()`, do static method được phân giải theo kiểu tĩnh `A` của biểu thức, không dùng runtime polymorphism.

**Câu 4.** Nếu `A` có field `String label = "A"`, `B` có field `String label = "B"`, `A a = new B();`, `a.label` là gì?

**Đáp án:** `"A"`, theo kiểu tĩnh `A`; đây là field hiding, không phải method overriding.

**Câu 5.** Trong một lớp, có thể khai báo `int read(String s)` và `long read(String s)` như hai overload không?

**Đáp án:** Không, vì kiểu trả về không đủ phân biệt chữ ký.

**Câu 6.** `final void execute()` của superclass có thể bị override không? Subclass có thể khai báo `execute(int retries)` không?

**Đáp án:** Không thể override `execute()`; `execute(int)` có danh sách tham số khác nên có thể là overload hợp lệ.

**Câu 7.** `@Override` trên method cùng tên nhưng khác tham số với mọi method superclass có tác dụng gì?

**Đáp án:** Nếu không thực sự override/implement method nào từ siêu kiểu thích hợp, compiler báo lỗi. Điều này giúp tìm trường hợp vô tình viết overload khi định ghi đè.

**Câu 8.** Trong `MixedMethodsDemo`, vì sao `parent.parse("Java")` in `Child:Object`?

**Đáp án:** Compiler chọn chữ ký `parse(Object)` từ kiểu tĩnh `ParentParser`. Nhưng runtime receiver là `ChildParser`, nên implementation override `ChildParser.parse(Object)` chạy.

**Câu 9.** `this.name = name;` trong constructor có phải method hiding không?

**Đáp án:** Không. Đây là trường hợp tham số `name` shadow field cùng tên; `this.name` chỉ rõ field.

**Câu 10.** Tại sao `ToolImpl.version()` không tự hợp lệ dù `ToolImpl implements Tools` và `Tools` có static method `version()`?

**Đáp án:** Static method trong interface không được thừa hưởng bởi implementing class theo cách đó; gọi `Tools.version()`.

**Câu 11.** `super.describe()` trong method override có gọi trên một object superclass riêng không?

**Đáp án:** Không. Nó gọi superclass implementation trên **cùng object hiện tại**, theo cú pháp `super`.

**Câu 12.** Với `Parent p = new Child();`, cast `((Child) p)` có làm đổi lớp của object không?

**Đáp án:** Không. Nó thay kiểu tĩnh của biểu thức nếu cast hợp lệ; object runtime vẫn là `Child`. Điều này có thể đổi tập overload mà compiler nhìn thấy.

## 17. Quy trình chẩn đoán trong code thực tế

Khi muốn biết hai khai báo cùng tên là overload, override hay hiding, hãy làm lần lượt:

1. **Đọc đầy đủ hai khai báo:** tên, danh sách kiểu tham số theo thứ tự, generic type parameters/erasure, modifier `static`, `private`, `final`, quyền truy cập và kiểu trả về.
2. **Xác định quan hệ lớp/kiểu:** hai method cùng một lớp, subclass/superclass hay interface? Khai báo ở superclass có được kế thừa hợp lệ không?
3. **Khác danh sách tham số?** Nếu có và khai báo không va chạm erasure/chữ ký, đó có thể là **overload**.
4. **Cùng chữ ký và đều là instance methods?** Nếu quan hệ kế thừa cùng các điều kiện override hợp lệ, đó là **overriding**.
5. **Cùng chữ ký và đều là static methods?** Trong quan hệ class hierarchy hợp lệ, đó là **static method hiding**.
6. **Tên trùng nhưng là field?** Kiểm tra **field hiding**; field được chọn theo kiểu tĩnh, không runtime dispatch.
7. **Tên trùng giữa local/parameter và field?** Kiểm tra **shadowing**; dùng `this.field` để nêu rõ field.
8. **Đến một lời gọi cụ thể:** ghi kiểu tĩnh receiver, kiểu tĩnh từng đối số; chọn overload trước, rồi xét runtime overriding (nếu áp dụng).
9. **Dùng `@Override` trên implementation thật sự ghi đè**, và khi cần quan sát thực tế, chạy chương trình nhỏ với output xác định thay vì đoán theo tên biến.

---

**Ghi nhớ:** **Overloading** khác nhau về *chữ ký tham số* và được phân giải khi biên dịch; **overriding** thay implementation của *instance method* trên object runtime; **hiding** với static method hoặc field làm tên ở lớp con che tên tương ứng ở lớp cha nhưng **không tự tạo runtime polymorphism**. Local-variable **shadowing** lại là vấn đề phạm vi tên. Chỉ cần xác định **loại thành viên, chữ ký, kiểu tĩnh và quan hệ kế thừa** theo đúng thứ tự, bạn có thể giải thích được phương thức nào thực thi và field nào được đọc trong những chương trình Java tưởng như mâu thuẫn.