# `getClass()` và phân biệt lớp thực tế với kiểu khai báo trong Java

Một trong những ý tưởng cốt lõi của Java là **biến tham chiếu có kiểu được compiler biết**, nhưng **đối tượng mà biến trỏ tới có lớp thực tế tại runtime**. Hai thông tin ấy có liên quan nhưng **không nhất thiết giống nhau**.

Ví dụ:

~~~java
Object value = "Java";
~~~

Ở đây, kiểu khai báo của `value` là `Object`, nhưng object thực tế là một `String`. Vì vậy `value.getClass()` trả về đối tượng `Class` mô tả **`java.lang.String`**, chứ không phải `java.lang.Object`.

Phương thức `getClass()` được khai báo trong `java.lang.Object`:

~~~java
public final native Class<?> getClass();
~~~

Đây là **chữ ký API minh họa** của method, không phải phần thân method mà ta tự cài đặt. `final` có nghĩa class con **không thể override** `getClass()`. Mọi instance Java thông thường kế thừa khả năng truy xuất thông tin lớp runtime từ `Object`, và JVM trả về `Class` tương ứng với đối tượng nhận lời gọi.

Bài thuộc Java Core — **class-object**, phần **Lớp Object**. Chúng ta sẽ học cơ chế kiểu tĩnh và kiểu động, quan hệ với đa hình, `Class` literals, `instanceof`, reflection, interface, mảng, generic type erasure, `null`, quy tắc so sánh class, và các sai lầm khi dùng `getClass()` trong `equals()` hoặc thiết kế thư viện. Các chương trình độc lập dùng **Java 17+**, kèm lệnh chạy và stdout xác định.

## 1. Hai khái niệm phải tách riêng

Xét:

~~~java
Animal animal = new Dog();
~~~

Đây là **câu lệnh minh họa** giả định `Dog extends Animal`, và hai kiểu có thể truy cập.

- **Kiểu khai báo / kiểu tĩnh (declared/static type)** của biến `animal` là `Animal`. Compiler dùng thông tin này để kiểm tra các biểu thức như `animal.eat()` có hợp lệ không, và để lựa chọn chữ ký phương thức phù hợp.
- **Lớp thực tế (runtime class)** của object là `Dog`, vì biểu thức `new Dog()` tạo object của lớp `Dog`.
- `animal.getClass()` trả `Dog.class`, không trả `Animal.class`.
- Với phương thức instance có thể override, lời gọi qua `animal` có thể dispatch tới implementation của `Dog`.

Không tồn tại “hai object” ở ví dụ này. Chỉ có **một object Dog**, được giữ qua một biến có kiểu Animal.

Vì Java cho phép **upcasting** từ subclass lên superclass/interface, việc hai kiểu khác nhau là bình thường, không phải một kiểu lỗi dữ liệu.

## 2. Chương trình hoàn chỉnh 1 — kiểu biến và lớp object

Tạo tệp **`RuntimeClassDemo.java`**:

~~~java
class Vehicle {
    String kind() {
        return "vehicle";
    }
}

class Bicycle extends Vehicle {
    @Override
    String kind() {
        return "bicycle";
    }

    void ringBell() {
        System.out.println("ring");
    }
}

public class RuntimeClassDemo {
    public static void main(String[] args) {
        Vehicle vehicle = new Bicycle();

        System.out.println("declared=Vehicle");
        System.out.println("actual="
                + vehicle.getClass().getSimpleName());
        System.out.println("name="
                + vehicle.getClass().getName());
        System.out.println("literal="
                + Vehicle.class.getSimpleName());
        System.out.println("same Vehicle="
                + (vehicle.getClass() == Vehicle.class));
        System.out.println("same Bicycle="
                + (vehicle.getClass() == Bicycle.class));
        System.out.println("kind=" + vehicle.kind());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 RuntimeClassDemo.java
java RuntimeClassDemo
~~~

**Stdout chính xác:**

~~~text
declared=Vehicle
actual=Bicycle
name=Bicycle
literal=Vehicle
same Vehicle=false
same Bicycle=true
kind=bicycle
~~~

### Phân tích

- `declared=Vehicle` là dòng chúng ta cố ý in để diễn giải **kiểu khai báo trong source**. `getClass()` không có chức năng “đọc lại kiểu khai báo của biến”.
- `vehicle.getClass().getSimpleName()` trả tên đơn giản `Bicycle`.
- `getName()` ở đây trả `Bicycle` vì lớp nằm trong **unnamed package** và không phải nested class. Với package có tên, kết quả sẽ là tên binary đầy đủ thích hợp.
- `Vehicle.class` mô tả **chính kiểu Vehicle**, không mô tả object mà biến `vehicle` đang giữ.
- `kind()` là instance method được override, nên runtime gọi `Bicycle.kind()` dù biến được khai báo kiểu `Vehicle`.

Nếu muốn gọi `vehicle.ringBell()` trực tiếp, compiler sẽ từ chối vì API của kiểu `Vehicle` không khai báo method đó. Có thể kiểm tra kiểu động bằng `instanceof` và dùng **pattern variable** hoặc một phép cast an toàn.

## 3. Kiểu tham chiếu quyết định API nhìn thấy khi compile

Thử các dòng sau:

~~~java
Vehicle vehicle = new Bicycle();
vehicle.kind();       // Hợp lệ.
vehicle.getClass();   // Hợp lệ: Object.getClass().
~~~

Nhưng:

~~~java
// vehicle.ringBell(); // Không hợp lệ với kiểu khai báo Vehicle.
~~~

`ringBell()` là method riêng của `Bicycle`; việc object thực tế có method này **không làm compiler tự động bổ sung** nó vào API của biến `Vehicle`.

Cách an toàn trong Java 17:

~~~java
if (vehicle instanceof Bicycle bike) {
    bike.ringBell();
}
~~~

Đây là **đoạn minh họa** đặt tại một nơi có `vehicle` kiểu `Vehicle` và định nghĩa `Bicycle` phù hợp. `instanceof Bicycle bike` kiểm tra object tại runtime và, khi đúng, tạo pattern variable `bike` có kiểu `Bicycle` trong phạm vi hợp lệ.

Nếu chương trình chỉ cần gọi hành vi chung `kind()`, không nên ép kiểu xuống subclass vô cớ. Giá trị của đa hình là viết thuật toán trên **hợp đồng superclass/interface** thay vì thường xuyên khám phá lớp cụ thể.

## 4. `getClass()` trả đối tượng `Class`, không trả chuỗi

Kết quả của `getClass()` là một `java.lang.Class` object, không phải một `String`. Muốn lấy tên thì gọi các method của `Class`.

~~~java
Class<?> type = value.getClass();
String name = type.getName();
String simple = type.getSimpleName();
~~~

Đây là **các câu lệnh minh họa**, giả định `value` là tham chiếu không null. `Class<?> ` là cách thường dùng để giữ một class token khi chưa cần ràng buộc generic type cụ thể.

Các thao tác cơ bản:

| Biểu thức | Loại thông tin | Ví dụ cho `String.class` |
| --- | --- | --- |
| `getClass()` | `Class` của object runtime | `String.class` |
| `String.class` | Class literal của kiểu được nêu trong source | `String.class` |
| `getName()` | Tên nhị phân/định dạng tên JVM tùy loại kiểu | `java.lang.String` |
| `getSimpleName()` | Tên ngắn theo API | `String` |
| `getCanonicalName()` | Tên canonical nếu có | `java.lang.String` |
| `getPackageName()` | Tên package theo API | `java.lang` |
| `isInterface()` | Có phải interface không? | `false` |
| `isArray()` | Có phải array class không? | `false` |
| `getSuperclass()` | `Class` của direct superclass nếu có | `Object.class` |

**Không phải class nào cũng có canonical name.** Anonymous classes và local classes có thể trả `null` khi gọi `getCanonicalName()`. Vì vậy tránh code mặc định rằng `getCanonicalName()` luôn là một chuỗi không null.

## 5. `Class` object có phải duy nhất cho một runtime class?

Đối với một định nghĩa lớp runtime cụ thể, những tham chiếu đến cùng class object có thể so sánh bằng `==`. Ví dụ `new String("x").getClass() == String.class` là `true`.

~~~java
Class<?> first = "hello".getClass();
Class<?> second = String.class;
boolean same = first == second;
~~~

Kết quả `same` là `true` vì cả hai trỏ tới `Class` object đại diện cho **cùng runtime class**.

Tuy nhiên, JVM định danh class không chỉ bằng binary name; **defining class loader** cũng là một phần của danh tính. Trong plugin architecture hoặc application server, hai lớp có **cùng binary name** nhưng do **hai class loaders khác nhau định nghĩa** có thể là hai runtime classes riêng, có `Class` objects khác nhau.

Vì vậy:

- `typeA == typeB` kiểm tra chúng có mô tả **cùng runtime type** không.
- `typeA.getName().equals(typeB.getName())` chỉ so sánh **tên chuỗi**, chưa chắc hai runtime types là một.
- `getClass()` không dùng để khám phá “mã nguồn object đã được khai báo ở dòng nào”.

Trong code ứng dụng thông thường không có custom class loaders, sự khác biệt này ít xuất hiện, nhưng rất quan trọng khi debug `ClassCastException` khó hiểu trong hệ thống plugin.

## 6. Chương trình hoàn chỉnh 2 — biến `Object` giữ nhiều kiểu

Tạo tệp **`ObjectRuntimeTypesDemo.java`**:

~~~java
public class ObjectRuntimeTypesDemo {
    private static void inspect(Object value) {
        System.out.println("actual="
                + value.getClass().getSimpleName());
    }

    public static void main(String[] args) {
        Object text = "Java";
        Object number = Integer.valueOf(42);
        Object flag = Boolean.TRUE;

        inspect(text);
        inspect(number);
        inspect(flag);

        System.out.println("text is String="
                + (text instanceof String));
        System.out.println("number is Number="
                + (number instanceof Number));
        System.out.println("text is Object="
                + (text instanceof Object));
        System.out.println("exact Integer="
                + (number.getClass() == Integer.class));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ObjectRuntimeTypesDemo.java
java ObjectRuntimeTypesDemo
~~~

**Stdout:**

~~~text
actual=String
actual=Integer
actual=Boolean
text is String=true
number is Number=true
text is Object=true
exact Integer=true
~~~

Method `inspect(Object)` nhận reference chung, nên cùng một source method có thể xử lý các object khác nhau. `getClass()` quan sát đúng lớp runtime của từng object.

`number instanceof Number` trả true dù `number.getClass() == Number.class` sẽ là false, vì **Integer kế thừa Number**, còn `getClass()` báo kiểu **chính xác** của object.

Đây là điểm khác biệt then chốt khi lựa chọn giữa `getClass() == SomeType.class` và `instanceof SomeType`.

## 7. `getClass() == Type.class` khác `instanceof Type`

Cú pháp:

~~~java
object.getClass() == Parent.class
~~~

chỉ đúng khi class runtime của object **chính xác là `Parent`**. Nó không chấp nhận object của một subclass.

Còn:

~~~java
object instanceof Parent
~~~

đúng khi object runtime **tương thích kiểu `Parent`** theo quan hệ kiểu được kiểm tra, bao gồm object từ subclass. Đối với interface, `instanceof Interface` cũng có thể đúng khi object implement interface ấy.

| Trạng thái object | `getClass() == Parent.class` | `instanceof Parent` |
| --- | ---: | ---: |
| Object trực tiếp `new Parent()` | true | true |
| Object `new Child()` với `Child extends Parent` | false | true |
| Object `null` | **Ném NPE nếu gọi `getClass()`** | false |
| Object kiểu khác, không liên quan | false (nếu reference không null) | false |

**Lựa chọn:** cần **chính xác một class** thì so class tokens; cần **họ kiểu/các implementation của một hợp đồng** thì ưu tiên `instanceof`/đa hình.

Ngoài ra, việc tự chọn dùng exact class test ở giữa một API đa hình có thể vô tình loại subclass hợp lệ; không nên dùng `getClass()` để thay mọi `instanceof` trong code.

## 8. Chương trình hoàn chỉnh 3 — exact class và kế thừa

Tạo tệp **`ExactClassVersusInstanceofDemo.java`**:

~~~java
class Document {
}

class PdfDocument extends Document {
}

public class ExactClassVersusInstanceofDemo {
    static void check(Document document) {
        System.out.println(
                "actual=" + document.getClass().getSimpleName()
                + ", exactDocument="
                + (document.getClass() == Document.class)
                + ", isDocument="
                + (document instanceof Document)
                + ", isPdf="
                + (document instanceof PdfDocument));
    }

    public static void main(String[] args) {
        check(new Document());
        check(new PdfDocument());

        Document none = null;
        System.out.println("null instanceof="
                + (none instanceof Document));
        System.out.println("null test=" + (none == null));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ExactClassVersusInstanceofDemo.java
java ExactClassVersusInstanceofDemo
~~~

**Stdout:**

~~~text
actual=Document, exactDocument=true, isDocument=true, isPdf=false
actual=PdfDocument, exactDocument=false, isDocument=true, isPdf=true
null instanceof=false
null test=true
~~~

Phân tích:

1. Object `Document` trực tiếp có class chính xác `Document`.
2. Object `PdfDocument` vẫn là một `Document` theo quan hệ kế thừa, nhưng class của nó không bằng `Document.class`.
3. `null instanceof Document` luôn false; đây **không** phải cách phân biệt các lớp con.
4. Không được gọi `document.getClass()` nếu `document` có thể null mà chưa có bảo vệ. Chương trình chỉ gọi `check` với object không null.

Từ góc nhìn thiết kế, nếu `check` chỉ cần xem object có phải một Document, hãy dùng API `Document` thay vì truy vấn lớp thực tế. Exact class check thích hợp cho mục đích cụ thể, không phải mặc định cho mọi thuật toán.

## 9. Vì sao `getClass()` là `final`?

`Object.getClass()` là `final`; subclass không được thay cách một object báo cáo lớp runtime của chính nó. Vì thế:

~~~java
class Example {
    // @Override
    // public Class<?> getClass() { return Object.class; }
    // Cố ý không hợp lệ: Object.getClass() là final.
}
~~~

Đây là **đoạn minh họa**, những dòng bị comment là ví dụ cố ý không biên dịch nếu kích hoạt. Nếu một framework muốn công bố kiểu logic hoặc kiểu miền khác với class triển khai, nó phải dùng **API riêng** như `entityType()`, `category()` hoặc metadata, thay vì override `getClass()`.

Điều này **không** có nghĩa mọi method trong `Object` đều final. Ví dụ `toString()`, `equals(Object)`, `hashCode()` thường được override theo hợp đồng thích hợp.

Ngay cả khi một subclass muốn “đóng vai” superclass, `getClass()` vẫn trả về lớp runtime thực sự của object, không trả superclass để thuận tiện cho nghiệp vụ.

## 10. `getClass()` không giống dynamic dispatch

Đây là hai chủ đề có liên hệ nhưng không đồng nhất:

- **`getClass()`**: method final trả về `Class` của object thực tế.
- **Virtual method dispatch**: khi gọi instance method có thể override, JVM chọn implementation theo runtime class/object sau bước kiểm tra và lựa chọn chữ ký compile time.
- **Static method hiding**: method static không virtual dispatch kiểu instance.
- **Field access**: chọn field theo kiểu compile-time của biểu thức, không dispatch như override instance method.
- **Overloading**: compiler chọn chữ ký dựa trên kiểu và đối số tại compile time.

Một biến `Base ref = new Child();` có thể cho:

~~~text
ref.getClass()          -> Child.class
ref.overriddenMethod()  -> body trong Child
ref.staticMethod()      -> liên kết static theo kiểu compile-time
ref.hiddenField         -> field được xác định qua kiểu Base
~~~

Các dòng trên là **sơ đồ ngữ nghĩa**, không phải đoạn Java có class definitions đầy đủ. Kết luận: “`getClass()` trả Child” **không kéo theo** mọi biểu thức có cú pháp `ref.member` đều dùng member khai báo trong Child.

## 11. Chương trình hoàn chỉnh 4 — class runtime, static hiding và field hiding

Tạo tệp **`RuntimeClassAndBindingDemo.java`**:

~~~java
class BaseItem {
    String label = "base field";

    static String category() {
        return "base static";
    }

    String description() {
        return "base method";
    }
}

class SpecialItem extends BaseItem {
    String label = "child field";

    static String category() {
        return "child static";
    }

    @Override
    String description() {
        return "child method";
    }
}

public class RuntimeClassAndBindingDemo {
    public static void main(String[] args) {
        BaseItem item = new SpecialItem();

        System.out.println("actual="
                + item.getClass().getSimpleName());
        System.out.println("instance=" + item.description());
        System.out.println("field=" + item.label);
        System.out.println("static=" + BaseItem.category());
        System.out.println("child static=" + SpecialItem.category());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RuntimeClassAndBindingDemo.java
java RuntimeClassAndBindingDemo
~~~

**Stdout:**

~~~text
actual=SpecialItem
instance=child method
field=base field
static=base static
child static=child static
~~~

Lớp thực tế là `SpecialItem`. Nhưng field `label` được giải quyết qua kiểu khai báo `BaseItem`, còn static method `category()` được gọi với **tên class cụ thể** để tránh gây hiểu nhầm. Chỉ instance method `description()` được override nên dispatch về implementation của `SpecialItem`.

Điều này cho thấy không thể thay `getClass()` bằng “kiểu dùng cho mọi truy cập thành viên”. Kiểu compile-time và runtime cùng tham gia trong những quy tắc khác nhau.

## 12. Interface: object có class cụ thể, không có “class interface” làm lớp runtime

Ví dụ:

~~~java
Runnable task = () -> { };
~~~

Biến `task` có kiểu khai báo `Runnable`, nhưng object thực tế là một implementation do runtime tạo. `task.getClass()` trả về class **cụ thể** của object thực tế, không phải `Runnable.class`.

**Không nên dự đoán tên của lớp lambda** như một chuỗi cố định. Tên/chi tiết sinh lớp của lambda là implementation detail và có thể khác theo JVM, phiên bản hoặc bối cảnh.

Một ví dụ dùng `List`:

~~~java
java.util.List<String> names = java.util.List.of("An");
boolean exactInterface = names.getClass()
        == java.util.List.class;
boolean implementsList = names instanceof java.util.List;
~~~

Đây là **đoạn minh họa**. `exactInterface` là `false`, vì `List` là interface chứ không phải lớp concrete của object danh sách. `implementsList` là `true`.

Ngay cả một biến được khai báo qua interface, `getClass()` vẫn cung cấp class runtime cụ thể. Nhưng code nghiệp vụ thông thường nên thao tác qua hợp đồng `List`, thay vì so tên class implementation nội bộ của `List.of`.

## 13. Chương trình hoàn chỉnh 5 — interface và reflection API

Tạo tệp **`InterfaceRuntimeDemo.java`**:

~~~java
interface Messenger {
    String send();
}

class EmailMessenger implements Messenger {
    @Override
    public String send() {
        return "email";
    }
}

public class InterfaceRuntimeDemo {
    public static void main(String[] args) {
        Messenger messenger = new EmailMessenger();

        Class<?> actual = messenger.getClass();

        System.out.println("actual=" + actual.getSimpleName());
        System.out.println("declared interface="
                + Messenger.class.isInterface());
        System.out.println("actual is interface="
                + actual.isInterface());
        System.out.println("exact interface="
                + (actual == Messenger.class));
        System.out.println("compatible="
                + Messenger.class.isAssignableFrom(actual));
        System.out.println("message=" + messenger.send());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 InterfaceRuntimeDemo.java
java InterfaceRuntimeDemo
~~~

**Stdout:**

~~~text
actual=EmailMessenger
declared interface=true
actual is interface=false
exact interface=false
compatible=true
message=email
~~~

`Messenger.class.isInterface()` trả true vì class token này biểu diễn **interface**. Ngược lại, `actual` mô tả `EmailMessenger`, là concrete class, nên `isInterface()` false.

`Messenger.class.isAssignableFrom(actual)` là true: object có kiểu `EmailMessenger` có thể được dùng tại vị trí yêu cầu `Messenger`. Đừng đảo chiều phương thức này mà không nghĩ kỹ về **đích nhận phép gán**.

## 14. `isInstance`, `isAssignableFrom`, `cast` và `getClass`

Các method của `Class` trả lời những câu hỏi khác nhau:

| API | Câu hỏi |
| --- | --- |
| `obj.getClass()` | Object hiện tại thuộc runtime class nào? |
| `Type.class.isInstance(obj)` | Object có tương thích runtime với Type không? |
| `Type.class.isAssignableFrom(Subtype.class)` | Một giá trị của Subtype có thể gán sang biến kiểu Type không? |
| `Type.class.cast(obj)` | Ép tham chiếu sang Type với kiểm tra runtime; có thể ném ClassCastException |
| `obj instanceof Type` | Object có tương thích với Type theo phép thử `instanceof` không? |
| `obj.getClass() == Type.class` | Object có **đúng** runtime class Type không? |

Chú ý chiều của `isAssignableFrom`: **receiver là kiểu đích**.

~~~java
Number.class.isAssignableFrom(Integer.class) // true
Integer.class.isAssignableFrom(Number.class) // false
~~~

Đây là **hai biểu thức minh họa**, theo quan hệ `Integer extends Number`. Muốn tránh nhầm, đọc câu thứ nhất là “Number có thể nhận một đối tượng Integer”.

Khác với `getClass()`, `Type.class.isInstance(null)` trả `false` mà **không ném NullPointerException**. `Type.class.cast(null)` trả null, vì ép một tham chiếu null hợp lệ, nhưng gọi `null.getClass()` không hợp lệ tại runtime.

## 15. Chương trình hoàn chỉnh 6 — class token kiểm tra object

Tạo tệp **`ClassTokenChecksDemo.java`**:

~~~java
public class ClassTokenChecksDemo {
    public static void main(String[] args) {
        Object value = Integer.valueOf(7);

        System.out.println("actual="
                + value.getClass().getSimpleName());
        System.out.println("number instance="
                + Number.class.isInstance(value));
        System.out.println("integer instance="
                + Integer.class.isInstance(value));
        System.out.println("exact Number="
                + (value.getClass() == Number.class));
        System.out.println("Number from Integer="
                + Number.class.isAssignableFrom(Integer.class));
        System.out.println("Integer from Number="
                + Integer.class.isAssignableFrom(Number.class));

        Number number = Number.class.cast(value);
        System.out.println("cast=" + number.intValue());
        System.out.println("null instance="
                + Number.class.isInstance(null));
        System.out.println("null cast="
                + (Number.class.cast(null) == null));

        try {
            String.class.cast(value);
        } catch (ClassCastException ex) {
            System.out.println("wrong cast="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ClassTokenChecksDemo.java
java ClassTokenChecksDemo
~~~

**Stdout:**

~~~text
actual=Integer
number instance=true
integer instance=true
exact Number=false
Number from Integer=true
Integer from Number=false
cast=7
null instance=false
null cast=true
wrong cast=ClassCastException
~~~

`getClass() == Number.class` false, vì object runtime là `Integer`, mặc dù nó **là một `Number`**. `Number.class.cast(value)` thành công; `String.class.cast(value)` thất bại và ném `ClassCastException`.

Trong một factory hoặc plugin system, `isInstance`/`cast` có thể giúp thao tác với kiểu được giữ trong `Class<T>` token. Tuy nhiên, nếu code chỉ cần đa hình của một interface đã biết, gọi method qua interface vẫn đơn giản hơn reflection.

## 16. `null`: trường hợp `getClass()` không thể trả lời

Phương thức `getClass()` yêu cầu một **receiver object không null**. Ví dụ:

~~~java
Object value = null;
// Class<?> type = value.getClass(); // Ném NPE tại runtime.
~~~

Comment trên là một lời giải thích, không phải dòng cần chạy trong ví dụ hoàn chỉnh dưới đây.

Tạo tệp **`NullGetClassDemo.java`**:

~~~java
public class NullGetClassDemo {
    public static void main(String[] args) {
        Object absent = null;

        System.out.println("is null=" + (absent == null));
        System.out.println("instanceof String="
                + (absent instanceof String));

        try {
            absent.getClass();
        } catch (NullPointerException ex) {
            System.out.println("getClass throws="
                    + ex.getClass().getSimpleName());
        }

        Object present = "ok";
        System.out.println("present="
                + present.getClass().getSimpleName());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NullGetClassDemo.java
java NullGetClassDemo
~~~

**Stdout:**

~~~text
is null=true
instanceof String=false
getClass throws=NullPointerException
present=String
~~~

Khi receiver là null, JVM không có object để hỏi “lớp thực tế là gì”. Nên **kiểm tra null trước**, hoặc chọn `instanceof`/`Class.isInstance` nếu mục đích chỉ là kiểm tra tương thích mà null cần cho kết quả false.

Không nên lạm dụng exception handling cho null trong code nghiệp vụ. Ví dụ dùng `try/catch` chỉ để minh họa hành vi; cách rõ ràng hơn là `if (absent != null) { ... }` khi thao tác hợp lệ đòi object tồn tại.

## 17. Primitive, wrapper và class literals

Các giá trị primitive như `int`, `double`, `boolean` **không phải reference tới object**. Bạn không thể viết `int x = 7; x.getClass();`: compiler từ chối vì primitive không có instance methods.

Tuy nhiên, Java có các **class literals** cho primitive types:

~~~java
Class<Integer> primitive = int.class;
Class<Integer> boxed = Integer.class;
~~~

Đây là đoạn minh họa hợp lệ. Hai `Class` objects khác nhau:

- `int.class` mô tả primitive type `int`.
- `Integer.class` mô tả reference type wrapper `java.lang.Integer`.
- `Integer.valueOf(7).getClass()` là `Integer.class`, không phải `int.class`.
- `int.class.isPrimitive()` trả true, còn `Integer.class.isPrimitive()` false.

**Autoboxing** có thể biến một giá trị primitive thành wrapper object khi đưa vào biến `Object` hoặc tham số `Object`, nhưng hành động ấy không biến `int` thành một subclass của `Object`.

## 18. Chương trình hoàn chỉnh 7 — primitive và wrapper

Tạo tệp **`PrimitiveClassDemo.java`**:

~~~java
public class PrimitiveClassDemo {
    public static void main(String[] args) {
        int primitiveValue = 7;
        Object boxedValue = primitiveValue;

        System.out.println("primitive name="
                + int.class.getName());
        System.out.println("primitive type="
                + int.class.isPrimitive());
        System.out.println("wrapper name="
                + Integer.class.getName());
        System.out.println("wrapper primitive="
                + Integer.class.isPrimitive());
        System.out.println("boxed actual="
                + boxedValue.getClass().getSimpleName());
        System.out.println("same types="
                + (int.class == Integer.class));
        System.out.println("void primitive="
                + void.class.isPrimitive());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 PrimitiveClassDemo.java
java PrimitiveClassDemo
~~~

**Stdout:**

~~~text
primitive name=int
primitive type=true
wrapper name=java.lang.Integer
wrapper primitive=false
boxed actual=Integer
same types=false
void primitive=true
~~~

`void.class` là class token đặc biệt mô tả `void`; `Class.isPrimitive()` theo Java API trả true cho kiểu primitive **và void**. Không suy rằng có một object giá trị `void` để gọi `getClass()`.

Câu lệnh `Object boxedValue = primitiveValue;` sử dụng autoboxing thành `Integer`. Vì vậy `boxedValue.getClass()` trả `Integer.class`.

## 19. Mảng cũng là object và có runtime class

Mỗi object mảng Java đều có class runtime riêng mô tả **kiểu mảng**, ví dụ `int[]`, `String[]`, `String[][]`. `getClass()` trên một object mảng trả array class chứ không phải kiểu của **phần tử đầu tiên**.

Ví dụ:

~~~java
Object values = new String[2];
Class<?> type = values.getClass();
~~~

Kết quả `type` mô tả `String[]`. Có thể dùng:

- `type.isArray()` để xác định array class.
- `type.getComponentType()` để lấy class token của **kiểu phần tử trực tiếp**.
- `type.getName()` để thấy binary-style name của array class (ví dụ `[Ljava.lang.String;`).
- `type.getCanonicalName()` khi có canonical name (ví dụ `java.lang.String[]`).

Array của primitive khác array wrapper: `int[].class` không bằng `Integer[].class`. Mảng nhiều chiều cũng khác: `int[][].class.getComponentType()` là `int[].class`, không phải `int.class`.

## 20. Chương trình hoàn chỉnh 8 — các lớp mảng

Tạo tệp **`ArrayRuntimeClassDemo.java`**:

~~~java
public class ArrayRuntimeClassDemo {
    public static void main(String[] args) {
        Object ints = new int[3];
        Object texts = new String[2];
        Object matrix = new int[2][3];

        System.out.println("ints class="
                + ints.getClass().getName());
        System.out.println("ints component="
                + ints.getClass().getComponentType().getName());
        System.out.println("texts class="
                + texts.getClass().getName());
        System.out.println("texts canonical="
                + texts.getClass().getCanonicalName());
        System.out.println("matrix class="
                + matrix.getClass().getName());
        System.out.println("matrix component="
                + matrix.getClass().getComponentType().getName());
        System.out.println("array superclass="
                + (ints.getClass().getSuperclass() == Object.class));
        System.out.println("array is Object="
                + (ints instanceof Object));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ArrayRuntimeClassDemo.java
java ArrayRuntimeClassDemo
~~~

**Stdout:**

~~~text
ints class=[I
ints component=int
texts class=[Ljava.lang.String;
texts canonical=java.lang.String[]
matrix class=[[I
matrix component=[I
array superclass=true
array is Object=true
~~~

Những tên bắt đầu bằng `[` là **kiểu ký hiệu tên array của JVM** theo API `Class.getName()`: `[I` là một chiều `int[]`, `[[I` là hai chiều `int[][]`, `[Ljava.lang.String;` là array của references tới `String`.

`getComponentType()` chỉ bỏ **một mức mảng**. Do đó component của `int[][]` là `int[]`. Không nên viết logic tự tách chuỗi `getName()` nếu có thể dùng `isArray()` và `getComponentType()` chính thức.

## 21. Generic type arguments thường không tồn tại trong `getClass()`

Java generics chủ yếu dùng **type erasure**. Hai object đều là `ArrayList` ở runtime sẽ có **cùng runtime class**, cho dù biến được khai báo `List<String>` và `List<Integer>`.

Tạo tệp **`GenericErasureClassDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericErasureClassDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();

        words.add("Java");
        numbers.add(17);

        System.out.println("words class="
                + words.getClass().getSimpleName());
        System.out.println("numbers class="
                + numbers.getClass().getSimpleName());
        System.out.println("same class="
                + (words.getClass() == numbers.getClass()));
        System.out.println("words first=" + words.get(0));
        System.out.println("numbers first=" + numbers.get(0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericErasureClassDemo.java
java GenericErasureClassDemo
~~~

**Stdout:**

~~~text
words class=ArrayList
numbers class=ArrayList
same class=true
words first=Java
numbers first=17
~~~

`getClass()` **không thể phân biệt** `ArrayList<String>` và `ArrayList<Integer>` trong trường hợp này. Các đối số generic ở source không tạo ra hai concrete runtime classes riêng.

Cũng không thể dùng `instanceof List<String>` theo cách trực tiếp thông thường vì `List<String>` là kiểu generic không reifiable trong phép kiểm tra ấy. Có thể kiểm tra `instanceof List<?>`, rồi kiểm tra từng phần tử hoặc dùng một token/mô hình schema cho dữ liệu generic nếu thực sự cần thông tin kiểu.

Một số kiểu phản chiếu như `ParameterizedType` cho phép đọc **khai báo generic** của field, superclass hoặc method trong trường hợp metadata tồn tại; điều đó **không** có nghĩa `someList.getClass()` biết các type arguments mà biến caller dùng khi tạo object.

## 22. `getClass()` và thông tin kiểu tại compile time trong generics

Bản thân phương thức được khai báo trong `Object` với kết quả `Class<?> `, nhưng Java có quy tắc typing đặc biệt cho biểu thức gọi `getClass()` nhằm cung cấp loại `Class` token chặt hơn dựa trên **kiểu tĩnh của receiver**.

Ví dụ:

~~~java
Number value = Integer.valueOf(7);
Class<? extends Number> actual = value.getClass();
~~~

Đây là đoạn minh họa hợp lệ với Java 17. Biến `actual` có kiểu `Class<? extends Number>` ở compile time, trong khi object `Class` mà nó trỏ tới tại runtime vẫn là **`Integer.class`**.

Nếu receiver tại compile time là `Object`, kết quả typed theo `Class<? extends Object>` (tương đương một giới hạn rất rộng). Nếu kiểu receiver là một interface, quy tắc typing dùng dạng erasure phù hợp theo JLS, chứ không biến interface thành class runtime của object.

**Đừng đánh đồng kiểu generic của biến giữ `Class` token với runtime class object nó biểu diễn.** `Class<? extends Number>` là ràng buộc tĩnh; token bên trong có thể đại diện `Integer`, `Double` hoặc một subclass `Number` khác.

Với API factory, có thể truyền `Class<T>` làm tham số nếu muốn ràng buộc loại kết quả. Nhưng `getClass()` không ghi nhớ mọi kiểu generic argument ở biểu thức source.

## 23. Tên lớp: `getName`, `getSimpleName`, `getCanonicalName`

Các tên này hữu ích cho log, nhưng không đồng nghĩa:

- **Simple name**: tên ngắn, ví dụ `Entry`.
- **Binary name**: tên JVM dùng cho class thành viên với ký hiệu thích hợp, ví dụ `java.util.Map$Entry`.
- **Canonical name**: cách gọi canonical nếu tồn tại, ví dụ `java.util.Map.Entry`.
- **Anonymous/local classes**: có thể không có canonical name; một anonymous class có simple name rỗng.

Chương trình hoàn chỉnh **`ClassNameFormsDemo.java`**:

~~~java
public class ClassNameFormsDemo {
    static class Nested {
    }

    public static void main(String[] args) {
        Class<?> nested = Nested.class;

        System.out.println("simple="
                + nested.getSimpleName());
        System.out.println("binary="
                + nested.getName());
        System.out.println("canonical="
                + nested.getCanonicalName());

        class Local {
        }
        Class<?> local = Local.class;
        System.out.println("local canonical null="
                + (local.getCanonicalName() == null));

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
            }
        };

        System.out.println("anonymous simple empty="
                + anonymous.getClass().getSimpleName().isEmpty());
        System.out.println("anonymous canonical null="
                + (anonymous.getClass().getCanonicalName() == null));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ClassNameFormsDemo.java
java ClassNameFormsDemo
~~~

**Stdout:**

~~~text
simple=Nested
binary=ClassNameFormsDemo$Nested
canonical=ClassNameFormsDemo.Nested
local canonical null=true
anonymous simple empty=true
anonymous canonical null=true
~~~

Không dùng tên sinh ra cho local/anonymous class như `$1` làm khóa nghiệp vụ hay làm ràng buộc kiểm thử; tên binary cụ thể có thể phụ thuộc vị trí khai báo và compiler. Chương trình chỉ in các thuộc tính **được API quy định ổn định**: local/anonymous không có canonical name, anonymous simple name là chuỗi rỗng.

## 24. `getSuperclass` và `getInterfaces` trả gì?

Từ class token, có thể truy vấn quan hệ kiểu.

~~~java
Class<?> superclass = Integer.class.getSuperclass();
Class<?>[] interfaces = String.class.getInterfaces();
~~~

Đây là đoạn minh họa. `Integer.class.getSuperclass()` là `Number.class`. `getInterfaces()` trả mảng các interface được **khai báo trực tiếp** theo API, không phải một kết quả “duyệt toàn bộ graph rồi trả mọi interface”.

Các trường hợp đặc biệt:

- `Object.class.getSuperclass() == null`.
- `SomeInterface.class.getSuperclass() == null` vì interface không phải class có superclass thông thường.
- Primitive class tokens cũng có `getSuperclass() == null`.
- Array class có `Object.class` là direct superclass và còn implement các interface đặc biệt như `Cloneable`, `Serializable`.

Muốn kiểm tra một class **có tương thích** với một interface/superclass, `isAssignableFrom` hoặc `isInstance` thường thích hợp hơn việc tự đi qua một tầng `getSuperclass()`, vì kế thừa có thể nhiều tầng và interfaces tạo ra graph không đơn tuyến.

## 25. Reflection: `Class` là metadata, không phải thay thế thiết kế đa hình

Từ một `Class` token, Java Reflection API cho phép truy vấn nhiều metadata như tên, superclass, interfaces, methods và fields. Trong những ngữ cảnh hợp lệ, bạn cũng có thể gọi method hoặc tạo instance qua reflection với quyền truy cập tương ứng.

Nhưng **chỉ vì có `getClass()` không có nghĩa nên dùng reflection cho mọi nghiệp vụ**.

Ví dụ không nên viết:

~~~java
if (service.getClass().getSimpleName().equals("EmailService")) {
    // Hành vi cho EmailService.
} else if (service.getClass().getSimpleName().equals("SmsService")) {
    // Hành vi cho SmsService.
}
~~~

Đây là **pseudocode minh họa một anti-pattern**, không phải chương trình có class definitions đầy đủ. Những nhánh phụ thuộc tên lớp dễ hỏng khi đổi package, đổi tên implementation, tạo proxy, hoặc subclass mới.

Cách hướng đối tượng thường tốt hơn là định nghĩa hợp đồng:

~~~java
interface Service {
    void execute();
}
~~~

và để implementation override/implement `execute()`. Caller chỉ cần `service.execute()`, không cần khám phá tên lớp trước.

**Reflection có chỗ đứng riêng** trong dependency injection, serialization, testing tools, plugin frameworks và cơ chế ánh xạ. Hãy dùng nó khi thật sự xử lý metadata/kiểu động, thay vì thay thế những lời gọi polymorphic thông thường.

## 26. `Class.forName` khác `getClass()` ở đâu?

`obj.getClass()` bắt đầu từ **object đã có**, trả class runtime của nó.

`SomeType.class` bắt đầu từ **tên kiểu được viết tại source**, trả class token tương ứng.

`Class.forName("package.Type")` bắt đầu từ **tên kiểu dạng chuỗi**, yêu cầu class loader tìm class và — trong overload một tham số — **khởi tạo class theo quy tắc API**.

Đây là ba câu hỏi khác nhau:

| API | Đầu vào | Điều cần nhớ |
| --- | --- | --- |
| `obj.getClass()` | Object reference không null | Phát hiện runtime class của object |
| `Type.class` | Tên kiểu biết lúc biên dịch | Không cần object Type và không tự kích hoạt initialization chỉ bởi class literal |
| `Class.forName(name)` | Chuỗi tên + cơ chế loader | Tìm lớp và yêu cầu class initialization |
| `Class.forName(name, false, loader)` | Tên + loader + cờ initialize | Không yêu cầu class initialization khi initialize=false |

**Không nhầm việc có được một `Class` object với việc đã tạo instance của class đó.** `Class.forName` không tự gọi constructor `new Type()` chỉ để trả metadata.

## 27. Chương trình hoàn chỉnh 9 — class literal và `forName`

Tạo tệp **`ClassLookupDemo.java`**:

~~~java
class LazyPart {
    static {
        System.out.println("LazyPart initialized");
    }

    LazyPart() {
        System.out.println("LazyPart constructed");
    }
}

public class ClassLookupDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("begin");

        Class<?> literal = LazyPart.class;
        System.out.println("literal="
                + literal.getSimpleName());

        ClassLoader loader =
                ClassLookupDemo.class.getClassLoader();
        Class<?> metadata =
                Class.forName("LazyPart", false, loader);
        System.out.println("metadata same="
                + (metadata == literal));

        System.out.println("before forName");
        Class.forName("LazyPart");
        System.out.println("after forName");

        Object created = new LazyPart();
        System.out.println("runtime same="
                + (created.getClass() == literal));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ClassLookupDemo.java
java ClassLookupDemo
~~~

**Stdout:**

~~~text
begin
literal=LazyPart
metadata same=true
before forName
LazyPart initialized
after forName
LazyPart constructed
runtime same=true
~~~

`LazyPart.class` và `Class.forName(..., false, loader)` có thể lấy class token mà **chưa chạy static block**. Khi gọi `Class.forName("LazyPart")`, class mới cần initialized và static block in thông báo.

Lệnh `new LazyPart()` sau đó tạo instance, in thông báo constructor. `created.getClass() == literal` true vì token mô tả runtime class thật của object ấy.

Không thể từ stdout này khẳng định thời điểm chính xác class được **loaded/linked**; code chỉ quan sát static initialization và object construction.

## 28. `getClass()` bên trong superclass method

Ngay cả khi `getClass()` được gọi từ method khai báo trong superclass, nó vẫn trả class của **object thực sự**. Đây không phải phương thức bị subclass override; `getClass()` là final, nhưng object receiver vẫn mang đúng danh tính runtime.

Tạo tệp **`InheritedGetClassDemo.java`**:

~~~java
class BaseNode {
    String runtimeName() {
        return getClass().getSimpleName();
    }

    String staticName() {
        return BaseNode.class.getSimpleName();
    }
}

class ChildNode extends BaseNode {
}

public class InheritedGetClassDemo {
    public static void main(String[] args) {
        BaseNode first = new BaseNode();
        BaseNode second = new ChildNode();

        System.out.println("first runtime="
                + first.runtimeName());
        System.out.println("second runtime="
                + second.runtimeName());
        System.out.println("first static="
                + first.staticName());
        System.out.println("second static="
                + second.staticName());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 InheritedGetClassDemo.java
java InheritedGetClassDemo
~~~

**Stdout:**

~~~text
first runtime=BaseNode
second runtime=ChildNode
first static=BaseNode
second static=BaseNode
~~~

Method `runtimeName()` được viết trong BaseNode nhưng `getClass()` hỏi **receiver đang chạy method đó**, không hỏi “method được khai báo ở lớp nào”. Với object ChildNode, nó trả ChildNode.

Ngược lại, `BaseNode.class` là **literal cố định trong source**, nên `staticName()` luôn trả BaseNode dù method được gọi qua object của lớp con.

## 29. Dùng `getClass()` trong `equals()`: exact-type equality

Trong `equals(Object)`, có hai chiến lược thường được thảo luận:

**Chiến lược exact runtime type:**

~~~java
if (other == null || getClass() != other.getClass()) {
    return false;
}
~~~

Điều này chỉ chấp nhận hai object cùng **runtime class chính xác**. Nó loại object subclass cho dù các field ở superclass bằng nhau.

**Chiến lược family-of-types:**

~~~java
if (!(other instanceof BaseValue)) {
    return false;
}
~~~

Điều này chấp nhận object thuộc subtype phù hợp. Nếu một subclass bổ sung field có ý nghĩa equality, thiết kế cần rất cẩn thận để giữ tính **đối xứng và bắc cầu** của `equals`; không thể thay `getClass` bằng `instanceof` máy móc.

Việc lựa chọn phải phụ thuộc **hợp đồng equality** của kiểu. Với value objects bất biến mà mỗi class có miền giá trị riêng, exact-class check có thể hữu ích. Với entity do ORM tạo proxy subclass hoặc framework dùng dynamic proxies, exact runtime class comparison có thể **không phản ánh đúng** danh tính miền; cần xem chiến lược identity/equality và proxy của framework.

## 30. Chương trình hoàn chỉnh 10 — `equals` xét class chính xác

Tạo tệp **`ExactClassEqualityDemo.java`**:

~~~java
class Badge {
    private final int id;

    Badge(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (other == null || getClass() != other.getClass()) {
            return false;
        }
        Badge badge = (Badge) other;
        return id == badge.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}

class PremiumBadge extends Badge {
    PremiumBadge(int id) {
        super(id);
    }
}

public class ExactClassEqualityDemo {
    public static void main(String[] args) {
        Badge first = new Badge(7);
        Badge second = new Badge(7);
        Badge premium = new PremiumBadge(7);
        Badge premiumAgain = new PremiumBadge(7);

        System.out.println("base equals base="
                + first.equals(second));
        System.out.println("base equals child="
                + first.equals(premium));
        System.out.println("child equals base="
                + premium.equals(first));
        System.out.println("child equals child="
                + premium.equals(premiumAgain));
        System.out.println("same reference="
                + (first == second));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ExactClassEqualityDemo.java
java ExactClassEqualityDemo
~~~

**Stdout:**

~~~text
base equals base=true
base equals child=false
child equals base=false
child equals child=true
same reference=false
~~~

`Badge.equals` gọi `getClass()` trên **cả hai object**. Một Badge trực tiếp và PremiumBadge có runtime classes khác nhau, vì vậy chúng không bằng nhau dù `id` trùng. Hai PremiumBadge có cùng id vẫn được xem là bằng nhau theo implementation kế thừa từ Badge.

Đây là ví dụ **minh họa chiến lược exact class**, không phải công thức equality cho mọi entity. Nếu `PremiumBadge` có thêm thông tin miền làm thay đổi equality, cần thiết kế lại hợp đồng; không để một lớp con thêm state có ý nghĩa equality mà vẫn vô tình thừa kế phép so sánh chỉ dựa trên `id`.

Chú ý `hashCode` trong ví dụ chỉ dựa trên id: hai object khác class có thể cùng hash code, điều này **được phép** vì hai object không bằng nhau vẫn có thể trùng hash. Hợp đồng yêu cầu **nếu equals true thì hashCode phải bằng nhau**, chứ không yêu cầu ngược lại.

## 31. Proxy, framework và những trường hợp exact class quá chặt

Một số công cụ có thể tạo subclass/proxy class hoặc implementation động:

- ORM proxies có thể mang runtime class khác với lớp entity mà bạn khai báo.
- Dynamic proxy cho interface có class runtime do cơ chế proxy tạo, không chính là interface class token.
- Các thư viện tạo mock có thể thay class runtime theo kỹ thuật mock.
- Một số triển khai `List.of` sử dụng lớp nội bộ không được API cam kết giữ nguyên giữa các phiên bản JDK.

Nếu code viết:

~~~java
if (repository.getClass() == MyRepository.class) {
    // chỉ xử lý đúng class này
}
~~~

thì có thể bỏ qua proxy/wrapper hợp lệ dù nó thực hiện đúng giao diện. Đây là **pseudocode minh họa**, giả định biến và class tương ứng tồn tại.

Thay vì phụ thuộc exact class, hãy cân nhắc:

- `repository instanceof Repository` nếu chỉ cần quan hệ kiểu.
- Gọi trực tiếp các method của interface `Repository` nếu có thể.
- Dùng `Class.isAssignableFrom` khi đang cầm class tokens thay vì object.
- Dùng API chính thức của framework để lấy **user class** hoặc loại entity logic nếu ứng dụng có nhu cầu thật sự, vì `getClass()` trả runtime proxy class đúng theo JVM.

**Không khẳng định** mọi ORM/mocking framework luôn tạo subclass: cơ chế cụ thể phụ thuộc công cụ, phiên bản và cấu hình. Bài học chỉ ra giới hạn của kiểm tra exact runtime class.

## 32. Lỗi biên dịch và lỗi runtime thường gặp

| Tình huống | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `Object x = "a"; x.length();` | Kiểu khai báo `Object` không có `length()` | Dùng hợp đồng đúng hoặc kiểm tra/cast `String` |
| `int value = 1; value.getClass();` | Primitive không có instance methods | Dùng `int.class` hoặc boxing nếu cần |
| `Object obj = null; obj.getClass();` | Receiver null | Kiểm tra null hoặc dùng `instanceof`/`isInstance` |
| `obj.getClass() == Parent.class` bỏ qua subclass | Exact runtime class comparison | Dùng `instanceof` nếu cần chấp nhận subtype |
| `obj instanceof Parent` rồi nghĩ exact Parent | `instanceof` chấp nhận subclasses | So exact class nếu contract đòi |
| `List<String>` và `List<Integer>` được kỳ vọng khác `getClass` | Erasure và cùng implementation class | Kiểm tra schema/type tokens riêng |
| So sánh `getName()` rồi coi như runtime class identity | Hai loaders có thể định nghĩa class cùng tên | So `Class` tokens hoặc giải quyết loader identity |
| Dùng `getSimpleName()` làm định danh bền vững | Simple names có thể trùng, đổi theo refactor | Dùng ID miền ổn định |
| Gọi `getCanonicalName().length()` trên anonymous class | Canonical name có thể null | Kiểm tra null |
| Dự đoán class name cụ thể của lambda/`List.of` | Chi tiết implementation không được bảo đảm | Log đặc tính/contract, không hard-code tên |
| Dùng `getSuperclass()` để phát hiện mọi interface | Chỉ thấy direct superclass | Dùng `isAssignableFrom`/reflection theo mục đích |
| Dùng `getClass()` trong mọi nhánh nghiệp vụ | Bỏ qua đa hình, khó mở rộng | Dùng interface/override/dispatch theo hành vi |
| Exact `getClass()` trong `equals` nhưng có proxy | Proxy class có thể khác entity class | Định nghĩa equality phù hợp framework |
| Nghĩ `Type.class` tự gọi constructor | Class literal không tạo instance | Dùng `new` hoặc factory nếu cần object |
| Nghĩ `Class.forName` luôn chỉ load không initialize | Overload một tham số yêu cầu initialization | Xem cờ `initialize` của API |

## 33. Quy trình quyết định dùng API nào

Khi cần hỏi “object này thuộc loại gì?”, hãy xác định mục đích trước.

**Nếu cần hành vi nghiệp vụ:** dùng interface/superclass method và overriding thay vì hỏi class liên tục.

**Nếu cần biết chính xác implementation runtime:** dùng `obj.getClass()`, rồi có thể in `getName()` hoặc so token với `Type.class`, nhớ rằng proxy và class loaders có thể làm kết quả khác ý định nghiệp vụ.

**Nếu cần kiểm tra tương thích với hợp đồng:** dùng `obj instanceof Interface` hoặc `Interface.class.isInstance(obj)`. Khi đã có biến compile-time đúng type và API đủ dùng, thường không cần kiểm tra kiểu.

**Nếu đang giữ class tokens:** `Parent.class.isAssignableFrom(actualClass)` diễn đạt “Parent nhận kiểu actualClass được không?”.

**Nếu chỉ cần kiểm tra null:** dùng `obj == null` hoặc `obj != null`, không gọi `getClass()`.

**Nếu cần tạo object từ metadata:** `Class` và reflection có các API cho trường hợp cụ thể, nhưng cần xử lý constructor, quyền truy cập và lỗi; không suy từ `getClass()` ra một lệnh khởi tạo object mặc định.

**Nếu so sánh equality:** viết hợp đồng `equals/hashCode` có chủ đích; exact `getClass` và `instanceof` mang hai quan niệm khác nhau về phạm vi các giá trị có thể bằng nhau.

## 34. Bài tập dự đoán kết quả

**Bài 1.** `Object x = "Java";`. `x.getClass() == String.class` trả gì? Compiler có cho phép `x.length()` trực tiếp không?

**Bài 2.** `Number n = Integer.valueOf(8);`. `n.getClass().getSimpleName()`, `n instanceof Number`, `n.getClass() == Number.class` lần lượt là gì?

**Bài 3.** Với `class A {}` và `class B extends A {}`, `A a = new B();`, điều gì khác giữa `a.getClass() == A.class` và `a instanceof A`?

**Bài 4.** `Object x = null;`. So sánh `x instanceof String`, `String.class.isInstance(x)` và `x.getClass()`.

**Bài 5.** Tại sao `List<String> a = new ArrayList<>(); List<Integer> b = new ArrayList<>();` có thể thỏa `a.getClass() == b.getClass()`?

**Bài 6.** `int x = 10;`. Có thể gọi `x.getClass()` không? `int.class == Integer.class` là gì? Với `Object boxed = x;`, `boxed.getClass()` trả gì?

**Bài 7.** `Object x = new String[2];`. `x.getClass().isArray()` là gì? `getComponentType()` trả loại nào?

**Bài 8.** `Object x = new int[2][3];`. `x.getClass().getName()` và `getComponentType().getName()` trả gì?

**Bài 9.** `Runnable r = () -> { };`. Có nên so `r.getClass().getName()` với một tên lambda hard-code không? Vì sao?

**Bài 10.** `Parent.class.isAssignableFrom(Child.class)` có nghĩa gì? Có đối xứng với `Child.class.isAssignableFrom(Parent.class)` không?

**Bài 11.** Method được khai báo trong `Base` trả `getClass().getSimpleName()`. Nếu chạy trên instance `Child extends Base`, có buộc trả `Base` vì method nằm trong Base không?

**Bài 12.** `getClass()` có thể được subclass override để trả superclass `Base.class` thay vì actual `Child.class` không?

**Bài 13.** Vì sao việc đọc `SomeType.class` chưa chắc chạy static initializer, trong khi `Class.forName("SomeType")` có thể yêu cầu initialization?

**Bài 14.** Nếu `Employee.equals` dùng `getClass()` exact comparison, một proxy subclass biểu diễn cùng entity có chắc được xem là bằng không? Có nên đổi ngay sang `instanceof` trong mọi hệ thống không?

**Bài 15.** So sánh `getSimpleName`, `getName`, `getCanonicalName` với nested class, local class và anonymous class. Tên nào có thể null?

**Bài 16.** Vì sao `Base ref = new Child();` mà `ref.field` có thể đọc field Base, trong khi `ref.method()` gọi override Child, và `ref.getClass()` vẫn là Child?

### Đáp án tham khảo

1. `true`; `x.length()` không biên dịch vì kiểu khai báo là `Object`.
2. `Integer`, `true`, `false`. Number là superclass của Integer nhưng không phải exact class.
3. `false` và `true`: exact runtime class khác compatibility.
4. `false`, `false`, còn `x.getClass()` ném `NullPointerException`.
5. Vì cả hai object thật đều là `ArrayList`; generic type arguments bị erasure ở runtime.
6. Primitive không có `getClass()`; so class tokens là false; boxing tạo reference Integer nên `boxed.getClass() == Integer.class`.
7. `true`; component là `String.class`.
8. `[[I` và `[I` vì component của int[][] là int[].
9. Không; tên lớp của lambda là implementation detail không nên hard-code.
10. Parent có thể nhận Child, nhưng không nhất thiết Child nhận Parent; chiều gọi không đối xứng.
11. Không. Receiver runtime là Child nên `getClass()` trả `Child.class`.
12. Không. `Object.getClass()` là final.
13. Class literal không tự yêu cầu initialize; `Class.forName(name)` một tham số yêu cầu khởi tạo class theo API.
14. Không chắc; exact class comparison có thể từ chối proxy subclass. Không thay máy móc: phải xác định hợp đồng equality và cơ chế proxy cụ thể.
15. Nested class có simple/binary/canonical khác nhau; local/anonymous thường không có canonical name, `getCanonicalName()` trả null; anonymous simple name rỗng.
16. Field/static binding và virtual method dispatch tuân quy tắc khác nhau; `getClass()` luôn phản ánh runtime object.

## 35. Checklist tự kiểm tra kiến thức

- Đã phân biệt **declared type** với **actual runtime class** chưa?
- Khi dùng biến superclass/interface, có nhận ra compiler chỉ thấy API được kiểu khai báo công bố không?
- `getClass()` trả `Class` token chứ không trực tiếp trả string?
- Có phân biệt `obj.getClass()`, `Type.class`, `Class.forName`?
- Biết `Object.getClass()` là `final` và không thể override?
- Với subclass, phân biệt `getClass()==Parent.class` và `instanceof Parent`?
- Nhớ kiểm tra null trước `getClass()`?
- Biết primitive không gọi instance method, nhưng có class literal `int.class`?
- Hiểu `Object boxed=intValue` dẫn tới wrapper runtime class?
- Biết array là object, `isArray`/`getComponentType` trả gì?
- Hiểu generic erasure khiến hai `ArrayList<T>` có thể là cùng runtime class?
- Hiểu `isAssignableFrom` theo chiều “receiver là kiểu đích”?
- Tránh dự đoán tên class nội bộ của lambda, proxy, `List.of`?
- Biết local/anonymous classes có thể không có canonical name?
- Khi viết `equals()`, đã định nghĩa rõ exact-type hay family-of-types equality?
- Không nhầm việc `Class` object tồn tại với object instance đã được tạo?
- Dùng interface/đa hình cho hành vi thay vì chuỗi `if` xét simple class name?
- Với framework proxies và class loaders, đã tránh coi string tên class là danh tính runtime tuyệt đối?

## 36. Tài liệu chính thức để đối chiếu

- [Java SE 17 API — Object.getClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#getClass()): phương thức final và quy tắc kiểu kết quả.
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): class tokens, `getName`, `getSimpleName`, `getCanonicalName`, `isInstance`, `isAssignableFrom`, `cast`, `getComponentType`.
- [Java SE 17 API — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): class lookup và cờ initialization.
- [JLS 17 §4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): đối tượng/tham chiếu và các kiểu reference.
- [JLS 17 §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): vì sao generic type arguments không làm mỗi ArrayList có class runtime riêng.
- [JLS 17 §5 — Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html): upcasting, boxing và các kiểu chuyển đổi.
- [JLS 17 §15.20.2 — Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): phép thử tương thích kiểu.
- [JLS 17 §15.8.2 — Class Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.2): `Type.class`.
- [JLS 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): lựa chọn chữ ký và method dispatch.
- [JLS 17 §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): khi nào class/interface initialized.
- [JVMS 17 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): danh tính runtime class và defining loader.

**Kết luận:** `getClass()` trả về **lớp runtime chính xác của object**, bất kể biến đang giữ object được khai báo bằng superclass hay interface. Kiểu khai báo vẫn quyết định API compiler nhìn thấy, việc chọn overload và nhiều quy tắc truy cập; runtime class tham gia vào dispatch của những instance methods có thể override. Hãy dùng `getClass()` khi cần **class identity/metadata chính xác**, dùng `instanceof` hoặc `Class.isInstance/isAssignableFrom` khi cần **tương thích kiểu**, và ưu tiên **đa hình** khi cần hành vi. Không gọi `getClass()` trên null, không mong lấy generic type arguments từ nó và không biến tên runtime class thành khóa nghiệp vụ.
