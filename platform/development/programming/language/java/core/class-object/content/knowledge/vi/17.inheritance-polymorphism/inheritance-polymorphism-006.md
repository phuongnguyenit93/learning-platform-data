# Ghi đè phương thức và kiểm tra bằng `@Override` trong Java

**Ghi đè phương thức (method overriding)** là cơ chế một lớp con cung cấp cách triển khai mới cho một **phương thức instance** được kế thừa từ lớp cha, hoặc triển khai phương thức theo hợp đồng của interface. Đây là một nền tảng của **đa hình runtime**: cùng một lời gọi trên biến có kiểu lớp cha có thể chạy phần triển khai của lớp con tùy **kiểu thực tế của object**.

Annotation `@Override` giúp compiler xác nhận ý định ấy. Nếu bạn gõ sai tên, sai kiểu tham số, hoặc phương thức thực tế chỉ là một overload mới, compiler sẽ báo lỗi thay vì để một phương thức mang tên gần giống tồn tại mà không được gọi như mong đợi.

Bài này thuộc **Java core - class-object**, nhóm **Kế thừa và đa hình**. Nội dung giải thích hợp đồng overriding, sự phân biệt với overloading, static hiding và field hiding, các ràng buộc về quyền truy cập, kiểu trả về và ngoại lệ, cách dùng `super`, interface/default methods, generic bridge methods, các lỗi phổ biến, cùng bài thực nghiệm Java **17+** có stdout rõ ràng.

## 1. Ý tưởng qua ví dụ nhỏ

Lớp cha định nghĩa một hành vi có thể thay đổi:

~~~java
class Animal {
    String sound() {
        return "unknown";
    }
}
~~~

Lớp con cung cấp hành vi chuyên biệt:

~~~java
class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
~~~

Hai đoạn là **các định nghĩa lớp minh họa**, có thể đặt cùng package. Với biến `Animal animal = new Cat();`, lời gọi `animal.sound()` chạy phiên bản `Cat.sound()` và trả `"meow"`.

Hãy tách hai khái niệm:

- **Kiểu tham chiếu tại compile time:** `Animal`. Compiler dùng nó để kiểm tra xem lời gọi `sound()` có hợp lệ và chữ ký nào được chọn.
- **Kiểu object thực tế tại runtime:** `Cat`. Với phương thức instance có thể override, Java chọn phần triển khai thích hợp dựa trên object thật.

`@Override` **không tạo ra đa hình**. Đa hình đã được quy định bởi ngữ nghĩa Java. Annotation đóng vai trò **kiểm tra lúc biên dịch** và làm rõ ý định cho người đọc.

## 2. Chương trình hoàn chỉnh 1 — đa hình khi ghi đè

Tạo tệp **`OverrideBasicsDemo.java`**:

~~~java
class Creature {
    String describe() {
        return "creature";
    }

    String sound() {
        return "?";
    }
}

class Bird extends Creature {
    @Override
    String describe() {
        return "bird";
    }

    @Override
    String sound() {
        return "chirp";
    }
}

class Dog extends Creature {
    @Override
    String sound() {
        return "woof";
    }
}

public class OverrideBasicsDemo {
    static void print(Creature creature) {
        System.out.println(creature.describe()
                + " => " + creature.sound());
    }

    public static void main(String[] args) {
        Creature first = new Bird();
        Creature second = new Dog();
        Creature third = new Creature();

        print(first);
        print(second);
        print(third);
        System.out.println("bird by parent ref="
                + first.sound());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OverrideBasicsDemo.java
java OverrideBasicsDemo
~~~

**Stdout chính xác:**

~~~text
bird => chirp
creature => woof
creature => ?
bird by parent ref=chirp
~~~

**Phân tích:**

- `Bird` override `describe` và `sound`; cả hai lời gọi chạy phiên bản Bird.
- `Dog` chỉ override `sound`; nó **kế thừa** `describe` từ `Creature`, nên kết quả là `creature => woof`.
- `Creature` không cần override gì; object thực tế là Creature thì dùng chính method của Creature.
- Method `print(Creature)` không biết cụ thể object thuộc lớp con nào. Nó gọi cùng một API, nhưng nhận hành vi tùy object.

Đây là mục đích quan trọng của đa hình: **code phụ thuộc hợp đồng chung**, còn các loại object cung cấp cách thực hiện khác nhau.

## 3. `@Override` làm được gì?

Khi đặt ngay trước khai báo phương thức:

~~~java
@Override
public String toString() {
    return "my object";
}
~~~

compiler kiểm tra phương thức thực sự override hoặc implement một phương thức phù hợp từ supertype theo quy tắc Java. Nếu không có phương thức thích hợp để ghi đè, nó báo **lỗi compile-time**.

Lợi ích thực tế:

1. **Phát hiện typo:** `toStirng` không vô tình trở thành method riêng không được gọi qua `toString`.
2. **Phát hiện lệch tham số:** `draw(int)` không bị nhầm thành override của `draw()`.
3. **Tự ghi tài liệu:** người đọc nhận ra đây là phần triển khai hành vi kế thừa, không phải một method hoàn toàn mới.
4. **Bảo vệ khi refactor:** nếu hợp đồng supertype đổi tên hoặc đổi chữ ký không tương thích, compiler có thể phát hiện method con không còn override.
5. **Giữ rõ ý định trong code review:** đặc biệt hữu ích ở hệ thống có nhiều lớp con.

Annotation này được khai báo trong `java.lang`, nên thông thường **không cần import** để viết `@Override`. Nó được dùng trên **khai báo phương thức**, không dùng trên field hoặc constructor.

Điểm cần nhớ: **không đặt `@Override` không có nghĩa method không override**. Nếu chữ ký và các quy tắc thỏa, Java vẫn thực hiện overriding bình thường. Dù vậy, trong code hiện đại nên dùng annotation nhất quán cho các phương thức thật sự override.

## 4. Lỗi chữ ký mà `@Override` bắt được

Giả sử lớp cha có:

~~~java
class Canvas {
    void draw(int size) {
        System.out.println("Canvas size=" + size);
    }
}
~~~

Cách viết sai:

~~~java
class BrokenCanvas extends Canvas {
    @Override
    void draw(long size) {
        System.out.println("Broken size=" + size);
    }
}
~~~

Đây là **ví dụ cố ý không biên dịch**: `draw(long)` khác `draw(int)`, nên là một phương thức **overload**, không phải override của method lớp cha. Annotation khiến compiler từ chối kiểu lỗi “method does not override or implement a method from a supertype”.

Cách đúng nếu muốn ghi đè:

~~~java
class FixedCanvas extends Canvas {
    @Override
    void draw(int size) {
        System.out.println("Fixed size=" + size);
    }
}
~~~

Hai lớp `Canvas`, `FixedCanvas` có thể đặt cùng một tệp ở cùng package. Lời gọi `Canvas c = new FixedCanvas(); c.draw(4);` sẽ in `Fixed size=4`.

Nếu muốn thêm `draw(long)` như một overload thật sự, vẫn có thể làm điều đó, **nhưng không gắn `@Override`** và cần hiểu compiler chọn overload nào ở nơi gọi.

## 5. Override và overload khác nhau bản chất

| Khía cạnh | Overriding | Overloading |
| --- | --- | --- |
| Quan hệ | Method được kế thừa/được triển khai theo supertype | Nhiều method cùng tên, khác danh sách tham số |
| Quyết định chính | Chọn implementation instance tại runtime | Chọn chữ ký thích hợp tại compile time |
| Tên | Phải phù hợp method supertype | Cùng tên |
| Tham số | Phải thỏa chữ ký/subsignature tương ứng | Phải khác danh sách kiểu/thứ tự/số lượng |
| Return type | Phải return-type-substitutable | Return type riêng không đủ để tạo overload |
| `@Override` | Nên dùng | Không dùng cho overload thuần túy |
| Static method | Không override theo nghĩa đa hình instance | Có thể overload; với subclass còn có hiding |

**Công thức nhớ:** compiler trước tiên quyết định **method nào có chữ ký được gọi**, rồi runtime dispatch phần triển khai instance **nếu method đó có thể override**. Đừng nói “Java luôn chọn theo runtime type” mà bỏ qua bước chọn overload tại compile time.

## 6. Chương trình hoàn chỉnh 2 — overload được chọn trước, override được dispatch sau

Tạo tệp **`OverloadOverrideDemo.java`**:

~~~java
class BasePrinter {
    String print(Object value) {
        return "base:Object";
    }
}

class FancyPrinter extends BasePrinter {
    @Override
    String print(Object value) {
        return "fancy:Object";
    }

    String print(String value) {
        return "fancy:String";
    }
}

public class OverloadOverrideDemo {
    public static void main(String[] args) {
        BasePrinter asBase = new FancyPrinter();
        FancyPrinter asFancy = new FancyPrinter();

        System.out.println("base ref="
                + asBase.print("hello"));
        System.out.println("fancy ref="
                + asFancy.print("hello"));
        System.out.println("object cast="
                + asFancy.print((Object) "hello"));
        System.out.println("null="
                + asFancy.print(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OverloadOverrideDemo.java
java OverloadOverrideDemo
~~~

**Stdout:**

~~~text
base ref=fancy:Object
fancy ref=fancy:String
object cast=fancy:Object
null=fancy:String
~~~

Giải thích từng dòng:

- Biến `asBase` có kiểu khai báo `BasePrinter`. Tại compile time, compiler chỉ xét các chữ ký sẵn có qua kiểu đó, chọn `print(Object)`. Runtime thấy object `FancyPrinter` nên chạy **bản override** `FancyPrinter.print(Object)`.
- Biến `asFancy` có kiểu `FancyPrinter`, nên compiler nhìn thấy cả `print(Object)` lẫn `print(String)`; với chuỗi, overload `String` cụ thể hơn được chọn.
- Khi ép `(Object)`, overload `Object` được chọn, dù object thực tế vẫn là chuỗi.
- Với `null`, `String` cụ thể hơn `Object` nên Java chọn `print(String)`. Nếu tồn tại hai overload không liên quan kiểu tham số, lời gọi `null` có thể trở thành **mơ hồ** và không biên dịch.

Không dựa trên `@Override` để “thay thế” bước chọn overload. Đây là hai cơ chế phối hợp nhưng **khác vai trò**.

## 7. Chữ ký method trong overriding

Trong trường hợp cơ bản, cần **cùng tên** và **danh sách tham số tương thích theo luật chữ ký/subsignature**. Kiểu trả về không phải thành phần để phân biệt hai method overload thông thường.

Ví dụ:

~~~java
class Report {
    void export(String format) {
    }
}

class CsvReport extends Report {
    @Override
    void export(String format) {
    }
}
~~~

Hai lớp trên là **mã minh họa hợp lệ**, cùng package. Modifier `@Override` hợp lệ vì `CsvReport.export(String)` override method tương ứng của `Report`.

Những thay đổi sau **không phải cùng chữ ký**:

- `export(Object)` thay cho `export(String)`.
- `export(String, boolean)` thay cho `export(String)`.
- `export(String... formats)` thay cho `export(String)` (varargs là array `String[]`, khác `String`).
- `Export(String)` chữ hoa đầu so với `export(String)` chữ thường.

Một nhầm lẫn khác: phương thức có kiểu trả về khác nhưng cùng tên và tham số **không tự trở thành overload mới hợp lệ**. Java không hỗ trợ phân biệt overload chỉ bằng return type.

### Varargs và mảng

Trong Java, `String...` của varargs có chữ ký phương thức dựa trên `String[]`. Một phương thức với `String[]` ở supertype có thể được ghi đè bằng khai báo varargs phù hợp, mặc dù sự khác biệt về modifier varargs có thể dẫn tới cảnh báo hoặc khó đọc. Khi override API, nên giữ **cách khai báo tham số nhất quán** để người gọi không bất ngờ.

## 8. Quy tắc quyền truy cập: không được thu hẹp

Khi ghi đè method instance, mức truy cập của method con **không được hạn chế hơn** mức được phép của phương thức cha:

| Method supertype | Phương thức override hợp lệ điển hình |
| --- | --- |
| `public` | `public` |
| `protected` | `protected` hoặc `public` |
| Package-private, nếu method thực sự được kế thừa/override theo các điều kiện package | Package-private, `protected` hoặc `public` phù hợp |
| `private` | **Không thể override** method private của superclass |

Ví dụ minh họa:

~~~java
class BaseTask {
    protected String status() {
        return "base";
    }
}

class PublicTask extends BaseTask {
    @Override
    public String status() {
        return "ready";
    }
}
~~~

Đây là mã hợp lệ: mở rộng từ `protected` thành `public` được phép.

Ví dụ **cố ý không biên dịch**:

~~~java
class BrokenTask extends BaseTask {
    @Override
    private String status() {
        return "hidden";
    }
}
~~~

Phương thức con không thể hạ mức truy cập của method `protected` đã được ghi đè, đồng thời `private` không dùng để override method superclass như vậy.

**Lưu ý cross-package:** package-private methods ở superclass khác package có quy tắc kế thừa/override riêng; đừng đơn giản giả định mọi method trùng tên ở hai class là override. `@Override` giúp compiler kiểm tra cụ thể việc này.

## 9. Covariant return: kiểu trả về có thể cụ thể hơn

Một phương thức ghi đè không nhất thiết có **return type giống hệt theo tên** khi trả reference. Java cho phép kiểu trả về phù hợp theo quan hệ **return-type-substitutability**; trường hợp thông dụng là **covariant return**: subclass trả kiểu con cụ thể hơn.

Ví dụ:

~~~java
class Resource {
    String id() {
        return "resource";
    }
}

class ImageResource extends Resource {
    @Override
    String id() {
        return "image";
    }
}

class Creator {
    Resource create() {
        return new Resource();
    }
}

class ImageCreator extends Creator {
    @Override
    ImageResource create() {
        return new ImageResource();
    }
}
~~~

Các định nghĩa trên là mã minh họa hợp lệ. `ImageCreator.create()` có kiểu trả về `ImageResource`, là kiểu con của `Resource` được lớp cha công bố.

Không thể tùy ý đổi `int` sang `long` hoặc `double` rồi gọi đó là covariant return. Với primitive và `void`, các quy tắc kiểu trả về **chặt hơn**: không dùng widening conversion để hợp thức hóa override.

## 10. Chương trình hoàn chỉnh 3 — visibility, covariance và checked exceptions

Tạo tệp **`OverrideRulesDemo.java`**:

~~~java
import java.io.IOException;

class BaseLoader {
    protected Number load() throws IOException {
        return 1;
    }
}

class FastLoader extends BaseLoader {
    @Override
    public Integer load() {
        return 42;
    }
}

public class OverrideRulesDemo {
    public static void main(String[] args) throws IOException {
        BaseLoader loader = new FastLoader();
        Number value = loader.load();

        System.out.println("value=" + value);
        System.out.println("runtime type="
                + value.getClass().getSimpleName());

        FastLoader direct = new FastLoader();
        Integer moreSpecific = direct.load();
        System.out.println("direct=" + moreSpecific);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 OverrideRulesDemo.java
java OverrideRulesDemo
~~~

**Stdout:**

~~~text
value=42
runtime type=Integer
direct=42
~~~

Những quy tắc thể hiện ở đây:

1. `BaseLoader.load()` là `protected`; `FastLoader.load()` mở rộng thành `public`.
2. Lớp cha trả `Number`; lớp con trả `Integer` hợp lệ vì `Integer extends Number`.
3. Lớp cha khai báo `throws IOException`; lớp con **không cần** khai báo checked exception nào.
4. Khi gọi qua biến `BaseLoader`, compiler xét hợp đồng `load() throws IOException`, nên `main` khai báo `throws IOException`.
5. Runtime dispatch vẫn chạy `FastLoader.load()`, trả 42.

Nếu method con cố khai báo **checked exception rộng hơn** chưa được cho phép bởi hợp đồng của method cha, compiler sẽ từ chối. Ví dụ method cha chỉ khai báo `IOException` nhưng method con khai báo `throws Exception` là sai. Với unchecked exceptions như `RuntimeException`, quy tắc giới hạn `throws` khác; không nên xem mọi exception như nhau.

## 11. Quy tắc ngoại lệ khi override

Khi superclass method khai báo checked exceptions, method override **không được mở rộng tùy ý** loại checked exceptions mà caller buộc phải xử lý.

Ví dụ hợp lệ:

~~~java
class ParentReader {
    void read() throws java.io.IOException {
    }
}

class ChildReader extends ParentReader {
    @Override
    void read() throws java.io.FileNotFoundException {
    }
}
~~~

`FileNotFoundException` là một subclass của `IOException`, nên khai báo checked exception hẹp hơn là phù hợp.

Ví dụ **cố ý không biên dịch**:

~~~java
class BadReader extends ParentReader {
    @Override
    void read() throws Exception {
    }
}
~~~

`Exception` rộng hơn `IOException`, nên vi phạm hợp đồng checked exceptions của method đã được ghi đè.

Một subclass cũng có thể không khai báo checked exceptions nào khi implementation xử lý được lỗi bên trong. Ngược lại, caller qua reference kiểu lớp cha **vẫn thấy chữ ký throws của lớp cha tại compile time**, dù object thực tế có implementation không ném lỗi ấy.

### Có phải `@Override` gây các hạn chế này?

Không. Chữ ký, quyền truy cập, kiểu trả về và `throws` là **quy tắc overriding của ngôn ngữ**. Annotation chỉ làm rõ và xác nhận ý định. Bỏ annotation **không** biến một override trái luật thành hợp lệ.

## 12. Method nào không thể override?

Các trường hợp cần phân biệt:

| Thành viên | Overriding? | Cơ chế liên quan |
| --- | --- | --- |
| Instance method có thể kế thừa, không `final` | Có khi đáp ứng quy tắc | Virtual dispatch |
| `final` instance method | **Không** | Không được viết override ở subclass |
| `private` method ở superclass | **Không** | Không được kế thừa như method override; method cùng tên ở subclass là độc lập |
| `static` method | **Không** | Static method hiding nếu cùng chữ ký phù hợp |
| Constructor | **Không** | Constructor không được kế thừa |
| Field | **Không** | Field hiding, truy cập dựa vào kiểu tham chiếu |
| `abstract` instance method | Có thể/được triển khai | Subclass cụ thể cung cấp implementation |
| Interface abstract/default method | Có thể được triển khai/override | Các quy tắc interface và default method |
| `Object.getClass()` | **Không** | Method `final` trong `Object` |

Từ khóa `final` đặt trên **class** cũng ngăn class đó có subclass. Một class `final` vẫn có thể override method đã nhận từ superclass hoặc implement interface trong **chính class đó**, nhưng class khác không thể `extends` nó.

Phương thức `private` trong superclass không override được vì không phải method được kế thừa để ghi đè theo ngữ nghĩa tương ứng. Một method cùng tên ở subclass có thể tồn tại riêng, nhưng không cung cấp **polymorphic replacement** cho lời gọi tới private method của lớp cha.

## 13. Static method hiding không phải phương thức ghi đè

`@Override` dùng để kiểm tra **instance method override** (và method implementation từ interface) theo các quy tắc Java. Không thể dùng annotation này để biến một `static method` thành virtual method:

~~~java
class BaseView {
    static String label() { return "base"; }
    String kind() { return "base instance"; }
}
class SpecialView extends BaseView {
    static String label() { return "special"; } // Hiding.
    @Override String kind() { return "special instance"; }
}
~~~

Ví dụ trên là khai báo lớp hợp lệ, chưa có `main`. Với một reference `BaseView ref = new SpecialView();` thì `ref.label()` chọn BaseView.label() theo kiểu tĩnh, còn `ref.kind()` dispatch đến `SpecialView.kind()`. Không thêm `@Override` trước `SpecialView.label()`: compiler sẽ từ chối vì static method **không override**.

Quy tắc này được nhắc tại đây để bạn biết **khi nào `@Override` không hợp lệ**. Bài **“Che khuất trường và phương thức static theo kiểu khai báo”** phân tích đầy đủ lookup, static hiding, fields và các tình huống ép kiểu. Để thực hiện đa hình runtime, dùng instance method thay vì static method.

## 14. Tại sao field hiding dễ gây nhầm với overriding?

Xét:

~~~java
class ParentState {
    int value = 1;

    int readValue() {
        return value;
    }
}

class ChildState extends ParentState {
    int value = 2;

    @Override
    int readValue() {
        return value;
    }
}
~~~

Hai lớp trên là mã minh họa hợp lệ. Nếu:

~~~java
ParentState state = new ChildState();
~~~

thì:

- `state.value` đọc field `ParentState.value`, trả 1.
- `state.readValue()` chạy method `ChildState.readValue()`, trả 2.

Đây là khác biệt **field access vs virtual method invocation**, không phải lỗi compiler. Tuy vậy, trùng tên field ở cả parent và child thường làm code khó đọc. Trong thiết kế domain, nên để field `private`, cung cấp method truy vấn có hợp đồng rõ và hạn chế tình huống shadowing/hiding trường không cần thiết.

## 15. Dùng `super` để gọi phiên bản lớp cha

Ghi đè không bắt buộc **thay thế hoàn toàn** implementation lớp cha. Một subclass có thể mở rộng hành vi bằng `super.method(...)`:

~~~java
class BasicLogger {
    void log(String message) {
        System.out.println("base: " + message);
    }
}

class AuditedLogger extends BasicLogger {
    @Override
    void log(String message) {
        super.log(message);
        System.out.println("audit: " + message);
    }
}
~~~

Đây là mã minh họa hợp lệ. Khi gọi `new AuditedLogger().log("saved")`, method override chạy và chủ động gọi phiên bản của superclass trước khi ghi thêm thông tin audit.

Nhưng `super` **không tự tắt virtual dispatch ở những lời gọi khác nằm sâu bên trong method superclass**. Nếu `super.log()` gọi một method instance có thể override như `format()`, lời gọi `format()` từ thân superclass có thể vẫn dispatch tới subclass.

## 16. Chương trình hoàn chỉnh 4 — `super` và dispatch bên trong method cha

Tạo tệp **`SuperDispatchDemo.java`**:

~~~java
class BaseLogger {
    String format(String value) {
        return "[" + value + "]";
    }

    void log(String value) {
        System.out.println("base.log="
                + format(value));
    }
}

class JsonLogger extends BaseLogger {
    @Override
    String format(String value) {
        return "{value:" + value + "}";
    }

    @Override
    void log(String value) {
        super.log(value);
        System.out.println("child.log="
                + format(value));
    }
}

public class SuperDispatchDemo {
    public static void main(String[] args) {
        BaseLogger logger = new JsonLogger();
        logger.log("ok");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SuperDispatchDemo.java
java SuperDispatchDemo
~~~

**Stdout:**

~~~text
base.log={value:ok}
child.log={value:ok}
~~~

`logger.log("ok")` chọn implementation `JsonLogger.log`. Bên trong, `super.log(value)` chạy thân method `BaseLogger.log`; tuy vậy lời gọi **`format(value)` trong method BaseLogger** vẫn là lời gọi instance tới object thực tế `JsonLogger`, nên chọn `JsonLogger.format`.

**`super.method()` chỉ chỉ định method cha được gọi ở đúng vị trí ấy**, không tạo một object cha tách biệt hoặc khóa mọi lời gọi bên trong về superclass.

Ngoài ra, `super` không được dùng tùy ý từ static context như thể đó là một instance. Nó mang ý nghĩa trong ngữ cảnh kế thừa của instance.

## 17. Interface methods và `@Override`

Khi class implement interface, những phương thức thỏa hợp đồng interface cũng thường được đánh dấu `@Override`:

~~~java
interface Drawable {
    void draw();
}

class Circle implements Drawable {
    @Override
    public void draw() {
        System.out.println("circle");
    }
}
~~~

**Lưu ý quyền truy cập:** method của interface kiểu trên mặc định `public abstract`. Vì thế implementation phải **`public`**; bỏ `public` ở `Circle.draw()` sẽ làm mức truy cập hẹp hơn hợp đồng và không biên dịch.

Từ Java 6, việc dùng `@Override` để đánh dấu method thực hiện hợp đồng interface là cú pháp quen thuộc được compiler hỗ trợ. Trong Java 17, không có lý do phải bỏ annotation chỉ vì method đến từ interface chứ không phải superclass class.

Một subclass khác có thể kế thừa implementation từ superclass đã implement interface; không cần triển khai lại nếu hợp đồng đã được thỏa mãn.

## 18. Default methods và xung đột từ hai interfaces

Interface có thể cung cấp **default method**. Nếu class implement hai interface cung cấp default method cùng chữ ký và không có quy tắc chọn tự động phù hợp, class phải giải quyết xung đột.

Tạo tệp **`InterfaceDefaultDemo.java`**:

~~~java
interface NamedItem {
    default String label() {
        return "named";
    }
}

interface TimestampedItem {
    default String label() {
        return "timestamped";
    }
}

class ReportItem implements NamedItem, TimestampedItem {
    @Override
    public String label() {
        return NamedItem.super.label()
                + "+" + TimestampedItem.super.label();
    }
}

public class InterfaceDefaultDemo {
    public static void main(String[] args) {
        ReportItem report = new ReportItem();
        NamedItem asNamed = report;
        TimestampedItem asTimestamped = report;

        System.out.println("direct=" + report.label());
        System.out.println("named=" + asNamed.label());
        System.out.println("stamped="
                + asTimestamped.label());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InterfaceDefaultDemo.java
java InterfaceDefaultDemo
~~~

**Stdout:**

~~~text
direct=named+timestamped
named=named+timestamped
stamped=named+timestamped
~~~

`ReportItem` phải cung cấp `label()` để làm rõ cách kết hợp, vì hai interface có default implementations cùng chữ ký. `NamedItem.super.label()` và `TimestampedItem.super.label()` là cú pháp gọi trực tiếp default implementation của interface tương ứng trong ngữ cảnh hợp lệ.

Sau khi class override `label()`, **dù biến có kiểu interface nào**, virtual dispatch vẫn chọn `ReportItem.label()`.

Quy tắc liên quan khác: khi một **class superclass** đã cung cấp method instance phù hợp, phương thức lớp thường có ưu tiên theo quy tắc inheritance so với một default method interface. Nhưng không được giản lược tất cả trường hợp kế thừa interface phức tạp thành “interface cuối cùng trong danh sách thắng”; **thứ tự liệt kê interfaces không phải cơ chế giải quyết xung đột**.

## 19. Abstract method và implementation trong subclass

Một abstract superclass có thể đặt hợp đồng:

~~~java
abstract class Shape {
    abstract double area();
}
~~~

Một concrete subclass phải triển khai method abstract còn thiếu (nếu không, bản thân subclass phải abstract):

~~~java
final class Square extends Shape {
    private final double side;

    Square(double side) {
        if (side < 0) {
            throw new IllegalArgumentException("side âm");
        }
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}
~~~

Đây là định nghĩa các lớp minh họa hợp lệ. `Square.area()` là cách triển khai hợp đồng `Shape.area()` và nên dùng `@Override`.

Một abstract method không có implementation để gọi bằng `super.area()` ở superclass đó. Nếu subclass muốn sử dụng logic chung, superclass có thể cung cấp thêm **concrete method** với tên/hợp đồng phù hợp. Tránh “viết `super`” máy móc chỉ vì đang override.

## 20. `final` method và Template Method

Một method `final` không được override ở subclass. Điều này có thể là lựa chọn thiết kế có chủ đích: superclass giữ nguyên **chuỗi thao tác** trong một method `final`, còn các bước chuyên biệt được đặt trong methods khác có thể override.

Tạo tệp **`FinalTemplateDemo.java`**:

~~~java
abstract class Job {
    final void execute() {
        System.out.println("start");
        doWork();
        System.out.println("finish");
    }

    abstract void doWork();
}

class ExportJob extends Job {
    @Override
    void doWork() {
        System.out.println("export");
    }
}

public class FinalTemplateDemo {
    public static void main(String[] args) {
        Job job = new ExportJob();
        job.execute();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FinalTemplateDemo.java
java FinalTemplateDemo
~~~

**Stdout:**

~~~text
start
export
finish
~~~

Superclass kiểm soát template `execute()` và ngăn subclass thay đổi cấu trúc tổng thể qua overriding. Nhưng method `doWork()` là abstract và được `ExportJob` triển khai. Khi `execute()` gọi `doWork()`, JVM dispatch tới subclass.

**Đánh đổi:** `final` giúp bảo vệ một thuật toán, nhưng cũng hạn chế khả năng mở rộng. Chỉ đánh dấu final khi thật sự muốn giữ invariant của hành vi, không phải vì “mọi method đều nên final”.

## 21. Override các phương thức từ `Object`

Những override thường gặp nhất trong code domain:

- `toString()` giúp trả mô tả dễ đọc.
- `equals(Object)` xác định equality theo hợp đồng của kiểu.
- `hashCode()` phải nhất quán với `equals`.
- Một số phương thức của Object khác cũng có thể override tùy quy tắc, nhưng `getClass()` là final và không thể override.

**Chữ ký chính xác đặc biệt quan trọng:**

~~~java
@Override
public boolean equals(Object other) {
    // implementation có ý nghĩa.
    return super.equals(other);
}
~~~

Đây là **một phương thức minh họa**, không phải ví dụ equality theo giá trị. Nếu thay `Object` bằng một kiểu domain như `Person`:

~~~java
public boolean equals(Person other) {
    return false;
}
~~~

thì nó trở thành **overload**, không override `Object.equals(Object)`. Nếu gắn `@Override` lên overload này mà không có method phù hợp trong supertype, compiler sẽ phát hiện.

Không tự động override `equals` cho mọi entity mutable: hãy chọn hợp đồng identity/value equality phù hợp và luôn bảo vệ quy tắc `equals/hashCode`.

## 22. Chương trình hoàn chỉnh 5 — `equals`, `hashCode`, `toString` với `@Override`

Tạo tệp **`EqualityOverrideDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class AccountKey {
    private final String id;

    AccountKey(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id rỗng");
        }
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof AccountKey key)) {
            return false;
        }
        return id.equals(key.id);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id);
    }

    @Override
    public String toString() {
        return "AccountKey(" + id + ")";
    }
}

public class EqualityOverrideDemo {
    public static void main(String[] args) {
        AccountKey a = new AccountKey("K-01");
        AccountKey b = new AccountKey("K-01");
        AccountKey c = new AccountKey("K-02");

        System.out.println("a equals b=" + a.equals(b));
        System.out.println("a same b=" + (a == b));
        System.out.println("a equals c=" + a.equals(c));
        System.out.println("hash same="
                + (a.hashCode() == b.hashCode()));

        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);
        keys.add(c);
        System.out.println("set size=" + keys.size());
        System.out.println("text=" + a);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 EqualityOverrideDemo.java
java EqualityOverrideDemo
~~~

**Stdout:**

~~~text
a equals b=true
a same b=false
a equals c=false
hash same=true
set size=2
text=AccountKey(K-01)
~~~

**Giải thích:**

- `a` và `b` là hai object riêng (`a == b` là false) nhưng cùng `id`, nên `equals` trả true.
- `hashCode` dựa vào cùng `id`, bảo đảm object bằng nhau có cùng hash code.
- `HashSet` dùng equality/hash để tránh thêm trùng một giá trị, nên chỉ có hai keys.
- `System.out.println(a)` sử dụng `toString()` đã override.

Đây là **value object** với `id` bất biến. Nếu override `hashCode()` theo mutable field rồi đổi field khi object đang trong `HashSet`, có thể làm collection tìm/xóa sai. Dùng `@Override` không tự đảm bảo implementation của `equals` là đúng; annotation chỉ xác nhận chữ ký và quan hệ kế thừa.

## 23. Generics, type erasure và bridge methods

Generics khiến một số override trông khác chữ ký runtime sau **type erasure**, nhưng compiler Java có thể tạo **bridge methods** trong bytecode để giữ đa hình và tương thích nhị phân.

Ví dụ với interface generic:

~~~java
interface Source<T> {
    T read();
}

final class StringSource implements Source<String> {
    @Override
    public String read() {
        return "java";
    }
}
~~~

Ở cấp source, `StringSource.read()` hợp đồng với `Source<String>.read()`. Nhưng JVM có những quy tắc method descriptors sau erasure mà compiler cần xử lý tương thích.

Tạo tệp **`GenericOverrideDemo.java`**:

~~~java
interface ValueSource<T> {
    T read();
}

class TextSource implements ValueSource<String> {
    @Override
    public String read() {
        return "java";
    }
}

public class GenericOverrideDemo {
    public static void main(String[] args) {
        ValueSource<String> source = new TextSource();
        System.out.println("value=" + source.read());

        TextSource concrete = new TextSource();
        System.out.println("direct=" + concrete.read());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericOverrideDemo.java
java GenericOverrideDemo
~~~

**Stdout:**

~~~text
value=java
direct=java
~~~

Nếu muốn quan sát compiler tạo bridge method (đầu ra diagnostic tùy công cụ/phiên bản, không ghi thành stdout chương trình), sau khi biên dịch có thể chạy:

~~~bash
javap -c -p -v TextSource
~~~

Tra cứu các dấu hiệu liên quan `ACC_BRIDGE` và `ACC_SYNTHETIC`. **Đừng tự viết bridge method bằng tay như một override thứ hai**, và đừng nhầm generics name clash với overload hợp lệ. Compiler còn có quy tắc **subsignature** và **erasure** để đảm bảo các method generic hợp đồng đúng.

## 24. Override có thể gọi method con trong constructor cha: rủi ro gì?

Trong Java, constructor superclass có thể gọi instance method được subclass override. Lời gọi vẫn **virtual dispatch** tới implementation trên object thực tế, ngay cả khi **instance field initializers của subclass chưa chạy**.

Tạo tệp **`ConstructorOverrideRiskDemo.java`**:

~~~java
class ParentConstructor {
    ParentConstructor() {
        System.out.println("parent constructor");
        describe();
    }

    void describe() {
        System.out.println("parent describe");
    }
}

class ChildConstructor extends ParentConstructor {
    private String message = "ready";

    ChildConstructor() {
        System.out.println("child constructor: " + message);
    }

    @Override
    void describe() {
        System.out.println("child describe: " + message);
    }
}

public class ConstructorOverrideRiskDemo {
    public static void main(String[] args) {
        new ChildConstructor();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConstructorOverrideRiskDemo.java
java ConstructorOverrideRiskDemo
~~~

**Stdout:**

~~~text
parent constructor
child describe: null
child constructor: ready
~~~

Phân tích:

1. Object `ChildConstructor` được cấp phát với instance fields có default values, trong đó `message=null`.
2. Constructor của lớp cha chạy trước instance initializer của lớp con.
3. `ParentConstructor()` gọi `describe()` — đó là method overridable.
4. JVM chọn `ChildConstructor.describe()`, dù field con còn `null`.
5. Sau khi constructor cha kết thúc, initializer `message="ready"` mới chạy, rồi thân constructor con in giá trị `ready`.

**Khuyến nghị:** không gọi các phương thức có thể override từ constructor, nhất là khi implementation lớp con phụ thuộc trạng thái được khởi tạo sau đó. Cần tránh công bố `this` trước khi object tạo xong. `@Override` giúp nhìn ra quan hệ ghi đè, nhưng **không khắc phục** lifecycle hazard này.

## 25. Dynamic dispatch có áp dụng cho mọi lời gọi không?

Không. Tóm tắt những tình huống phổ biến:

| Cách dùng | Quyết định chính | Ví dụ |
| --- | --- | --- |
| Instance method overridable | Dispatch theo object thực tế sau khi chọn chữ ký | `animal.sound()` |
| Overloaded method | Chọn overload dựa trên compile-time types | `print(Object)` vs `print(String)` |
| Static method | Static binding/hiding theo kiểu khai báo | `BaseView.label()` |
| Field access | Resolve field theo compile-time type | `baseReference.code` |
| Constructor | Chạy chuỗi khởi tạo theo luật `new`/`this`/`super` | `new Child()` |
| Private instance method của superclass | Không overridable từ subclass | `private void helper()` |
| Final method | Không cho subclass override | `final void execute()` |
| `super.method()` | Chỉ định implementation super tại điểm gọi | `super.log(message)` |
| Interface default method | Chịu quy tắc interface/class precedence và override | `NamedItem.super.label()` |

Đừng giải bài đa hình chỉ bằng việc đếm từ khóa `extends`. Hãy xác định **kiểu tham chiếu**, **chữ ký được chọn**, **phương thức có thể override không**, rồi mới xét **kiểu object runtime** và có `super` hay không.

## 26. Lỗi biên dịch phổ biến liên quan `@Override`

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Method does not override/implement a method from a supertype | Sai tên hoặc chữ ký; thực tế là overload | Kiểm tra tên/tham số chính xác |
| Attempting to assign weaker access privileges | Giảm `public`/`protected` | Giữ hoặc mở rộng visibility |
| Return type is not compatible | Return type không return-type-substitutable | Dùng đúng kiểu/covariant reference |
| Overridden method does not throw Exception | Method con thêm checked exception trái hợp đồng | Bỏ hoặc thu hẹp checked exceptions |
| Cannot override final method | Superclass method `final` | Thiết kế extension point khác |
| Static method cannot override instance method | Trộn static và instance cùng chữ ký kế thừa | Không trộn; chọn mô hình phù hợp |
| Static method annotation `@Override` | Static hiding không phải overriding | Bỏ annotation; dùng tên lớp |
| Overload `equals(Person)` nhưng tưởng override `equals(Object)` | Khác tham số | Dùng `equals(Object)` |
| Interface implementation thiếu `public` | Interface method có quyền public | Khai báo public method |
| Hai interface default methods cùng chữ ký | Ambiguity cần giải quyết | Override tại class, chọn/kết hợp logic |
| Generic methods bị name clash sau erasure | Hai chữ ký xóa kiểu mâu thuẫn | Điều chỉnh thiết kế generic/đổi tên |
| Gọi method override trong constructor cha đọc field con null | Dynamic dispatch trước khi field con init | Tránh gọi overridable method trong constructor |

Khi compiler báo lỗi, **không nên xóa `@Override` ngay** chỉ để qua bước biên dịch. Nếu ý định là ghi đè, cần sửa chữ ký/quyền/return/throws. Chỉ bỏ annotation khi tác giả **thực sự muốn một overload mới** hoặc một static method hiding hợp lệ.

## 27. Thiết kế tốt một hierarchy có overriding

Một số nguyên tắc có giá trị thực tế:

**Hợp đồng supertype rõ ràng.** Method cha/interface cần nêu ý nghĩa, preconditions và postconditions. Lớp con có thể đổi cách triển khai nhưng không nên phá các kỳ vọng hợp lý của caller đang dùng kiểu cha.

**Không để implementation phụ thuộc vào subclass không kiểm soát.** Constructor superclass gọi method có thể override dễ gặp tình huống field chưa sẵn sàng. Nếu cần khởi tạo qua bước chung, dùng helper `private` hoặc logic không dispatch ra subclass vào thời điểm chưa hoàn tất.

**Ưu tiên composition khi không có quan hệ “is-a” đúng.** Kế thừa chỉ để dùng lại vài dòng code có thể tạo hierarchy khó quản lý; composition/delegation có thể rõ hơn.

**Dùng `final` có chủ đích.** Các bước có thể mở rộng nên được định nghĩa rõ. Những quy tắc bất biến hoặc kết cấu thuật toán cần bảo vệ có thể dùng method final, như `Job.execute()`.

**Không nhầm override với việc thay đổi state trực tiếp.** Field hiding/overloading không tự bảo đảm đa hình. API hành vi nên biểu đạt những thao tác có nghĩa, không cần cố override getter/setter cho mọi field.

**Kiểm thử qua kiểu cha.** Nếu API hứa đa hình, hãy viết test qua `Base b = new Child();` thay vì chỉ dùng `Child c = new Child();`. Điều đó giúp phát hiện những method đã bị viết thành overload ngoài ý muốn.

**Gắn `@Override` nhất quán.** Đây là tín hiệu nhỏ nhưng hữu ích để người đọc phân biệt method kế thừa với API mới của lớp.

## 28. Quy trình dự đoán chương trình in gì

Khi đề bài có hierarchy và hỏi stdout, hãy làm theo thứ tự:

1. Xác định từng **object thực tế** được tạo bằng `new`.
2. Ghi **kiểu biến tại compile time** nơi mỗi method được gọi.
3. Xác định tên method và **overload được chọn** qua danh sách tham số/kiểu compile time.
4. Kiểm tra method đó là **instance overridable**, `final`, `private`, `static` hay constructor.
5. Nếu là instance overridable, chọn **implementation của object runtime**.
6. Nếu lời gọi dùng `super`, xét chính method superclass được chỉ định tại điểm gọi.
7. Với `super.method()` có lời gọi instance khác bên trong, tiếp tục áp dụng dispatch khi cần.
8. Nếu có fields trùng tên, giải quyết theo **compile-time field type**, không virtual dispatch.
9. Nếu constructor đang chạy, kiểm tra **thứ tự instance initializers**, vì overridden method có thể thấy field còn default.
10. Cuối cùng mới viết những dòng output theo trật tự câu lệnh thực thi.

Đối với `OverloadOverrideDemo`, bước 3 đặc biệt quan trọng: `asBase.print("hello")` được chọn chữ ký `print(Object)`, sau đó mới dispatch tới `FancyPrinter.print(Object)`; **không** tự chuyển qua overload `print(String)` chỉ vì object runtime là FancyPrinter.

## 29. Bài tập tự luyện

**Bài 1.** Lớp cha có `void show(int x)`. Lớp con khai báo `void show(long x)` với `@Override`. Compiler phản ứng ra sao và vì sao?

**Bài 2.** `Animal a = new Dog(); a.sound();`. Nếu Dog override `sound`, body nào được chạy? Tham chiếu có kiểu Animal ảnh hưởng tới phần nào?

**Bài 3.** Nếu lớp cha khai báo `public void run()` thì lớp con có thể override bằng `protected void run()` không?

**Bài 4.** Superclass method trả `Number`, subclass trả `Integer`. Khi nào hợp lệ? Trả `long` thay `int` có tự hợp lệ tương tự không?

**Bài 5.** Superclass `read() throws IOException`, subclass `read() throws Exception`. Vì sao không hợp lệ? Nếu subclass không khai báo throws thì sao?

**Bài 6.** Lớp cha và con có `static String label()`. `Base ref = new Child(); ref.label()` có dynamic dispatch như instance method không?

**Bài 7.** Lớp cha và con có field `value`. `Base ref = new Child(); ref.value` đọc field nào? Còn `ref.getValue()` nếu Child override method thì sao?

**Bài 8.** `public boolean equals(Person p)` có override `Object.equals(Object)` không? `@Override` có giúp phát hiện nhầm lẫn không?

**Bài 9.** Một class implement hai interfaces có default `label()` cùng chữ ký. Có thể bỏ qua xung đột chỉ bằng cách đổi thứ tự `implements` không?

**Bài 10.** Trong `super.log(x)`, nếu code superclass gọi `format(x)` và subclass đã override `format`, phiên bản nào có thể chạy?

**Bài 11.** Vì sao override method mà không ghi `@Override` vẫn có thể được JVM dispatch? Vậy annotation có tác dụng thực chất gì?

**Bài 12.** Superclass constructor gọi method overridable, subclass override đọc `String name="ready"`. Vì sao output có thể là `null`?

**Bài 13.** Generic interface `Source<T>` có `T read()`, lớp `TextSource implements Source<String>` có `String read()`. Compiler có thể sinh thêm loại method nào để giữ hợp đồng ở bytecode?

**Bài 14.** Một `final` method làm “template” gọi method abstract. Subclass có thể override template không? Có thể implement abstract step không?

**Bài 15.** Nếu compiler báo `method does not override or implement`, vì sao không nên xóa annotation ngay lập tức?

### Đáp án tham khảo

1. Lỗi compile-time: `show(long)` là overload mới chứ không override `show(int)`; sửa tham số thành `int` nếu muốn ghi đè.
2. Implementation Dog chạy theo object runtime; kiểu tham chiếu Animal dùng để kiểm tra API/chữ ký khi compile.
3. Không; giảm visibility từ public xuống protected bị cấm.
4. Hợp lệ khi Integer là subtype của Number; primitive return không có covariance kiểu widening tùy ý.
5. `Exception` là checked exception rộng hơn, làm hợp đồng caller nặng hơn; subclass có thể bỏ checked exception.
6. Không; static method hiding theo quy tắc compile time, nên `Base.label()` được chọn qua kiểu Base.
7. Field giải quyết theo kiểu Base; method instance overridable dispatch theo object Child.
8. Không, đó là overload. Gắn `@Override` sẽ khiến compiler báo lỗi nếu không có method supertype phù hợp cùng chữ ký.
9. Không; class cần giải quyết theo luật interface/default methods, thường bằng override `label()`.
10. `super.log` chọn thân superclass, nhưng lời gọi instance `format` trong thân đó vẫn có thể dispatch tới subclass.
11. Overriding là quy tắc ngôn ngữ; `@Override` là kiểm tra compile-time và tín hiệu cho người đọc.
12. Field con còn default khi constructor cha gọi override trước khi initializer của lớp con chạy.
13. Bridge method synthetic, theo yêu cầu type erasure và tương thích dispatch.
14. Template final không override được; subclass triển khai abstract step, và template gọi step qua đa hình.
15. Vì có thể đang có typo, sai kiểu tham số, sai quyền truy cập hoặc supertype thay đổi. Nếu ý định là override, phải sửa lỗi hợp đồng thay vì che lỗi.

## 30. Checklist khi viết một method `@Override`

- Method này đến từ **superclass hoặc interface nào**?
- Nó có thật sự là **instance method có thể override**, không phải static/private/final/constructor?
- **Tên và tham số** có đúng không? Có nhầm overload do primitive/wrapper, array/varargs hoặc tham số thêm/bớt không?
- Kiểu trả về có đúng **return-type-substitutability** không?
- Có đang vô tình **thu hẹp visibility**?
- Checked exceptions có rộng hơn hợp đồng supertype không?
- Nếu implement interface, method có `public` khi được yêu cầu không?
- Nếu override `equals`, có đúng `equals(Object)` và `hashCode` nhất quán không?
- Nếu subclass dùng `super.method()`, có hiểu các lời gọi virtual bên trong method cha không?
- Nếu superclass constructor có lời gọi overridable, có thể quan sát field con chưa khởi tạo không?
- Nếu method liên quan generics, có name clash sau erasure không?
- Có test thông qua **biến kiểu superclass/interface** để xác nhận đa hình không?
- Nếu `@Override` báo lỗi, đã kiểm tra nguyên nhân thay vì vội xóa annotation chưa?

## 31. Tài liệu chuẩn Java 17

- [JLS 17 §8.4.8.1 — Overriding (by Instance Methods)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.1): quy tắc override instance methods.
- [JLS 17 §8.4.8.2 — Hiding (by Class Methods)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.2): sự khác biệt giữa static method hiding và overriding.
- [JLS 17 §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): visibility, return type và throws.
- [JLS 17 §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): chữ ký và subsignature.
- [JLS 17 §8.4.5 — Method Result](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.5): return-type-substitutability.
- [JLS 17 §8.4.9 — Overloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.9): overload và cách phân biệt phương thức.
- [JLS 17 §9.4.1 — Inheritance and Overriding in Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1): ghi đè interface methods.
- [JLS 17 §9.6.4.4 — @Override](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.4): ý nghĩa annotation.
- [JLS 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): lựa chọn method và runtime dispatch.
- [JLS 17 §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): trình tự khởi tạo object và nguy cơ virtual calls trong constructor.
- [Java SE 17 API — Override](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Override.html): annotation kiểm tra overriding.
- [Java SE 17 API — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `equals`, `hashCode`, `toString` và các method `final`.

**Ghi nhớ:** overriding là cách subclass hoặc implementation **thay đổi hành vi của instance method theo hợp đồng supertype**. Compiler chọn chữ ký hợp lệ theo kiểu tham chiếu, còn runtime dispatch chọn body thích hợp cho object thật. `@Override` không kích hoạt cơ chế này, nhưng giúp **bắt lỗi sai tên/chữ ký và thể hiện ý định**. Đừng nhầm overriding với overload, static hiding hay field hiding; luôn xem xét visibility, return type, checked exceptions, default methods, `super` và trạng thái khởi tạo object khi thiết kế đa hình.
