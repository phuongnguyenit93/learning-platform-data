# 6.6 findVirtual, findStatic, findSpecial và findConstructor

`MethodHandles.Lookup` cung cấp bốn phương thức tạo `MethodHandle` cho bốn nhu cầu gọi khác nhau: gọi instance method có dispatch đa hình (`findVirtual`), gọi static method (`findStatic`), gọi instance method bằng ngữ nghĩa đặc biệt tương tự `super`/`invokespecial` (`findSpecial`), và tạo object bằng constructor (`findConstructor`). Cả bốn nhận thông tin kiểu thông qua `MethodType` và kiểm tra quyền truy cập từ một `Lookup`.

Điểm dễ nhầm: `MethodType` truyền vào factory mô tả **chữ ký khai báo của method**, chưa có receiver; handle do `findVirtual`/`findSpecial` tạo sẽ có thêm receiver. Constructor thì ngược lại: descriptor cần `void` nhưng handle tạo ra lại **trả về object**. Bài này giải thích chi tiết cách chọn API, cách truy cập, cách gọi đúng kiểu và Java 17+ runnable example.

## 1. Bảng quyết định

| Factory | Loại member | Tham số receiver của handle | `MethodType` khi lookup | Handle được tạo (thường gặp) |
| --- | --- | --- | --- | --- |
| `findVirtual(refc, name, type)` | Instance method | Có, ở đầu | `(args...)Return` | `(refc,args...)Return` |
| `findStatic(refc, name, type)` | Static method | Không | `(args...)Return` | `(args...)Return` |
| `findSpecial(refc, name, type, specialCaller)` | Instance method theo `invokespecial` | Có, bị giới hạn theo `specialCaller` | `(args...)Return` | `(specialCaller,args...)Return` (có thể hẹp hơn) |
| `findConstructor(refc, type)` | Constructor | Không | `(args...)void` | `(args...)refc` |

`refc` là class/interface dùng để resolve method hoặc class chứa constructor. `name` là tên phương thức. `type` là `MethodType` gồm loại trả về và danh sách kiểu tham số khai báo. `specialCaller` chỉ tồn tại với `findSpecial` và xác định ngữ cảnh lời gọi đặc biệt mà JVM cho phép.

~~~text
Lookup + Class + MethodType + (tên, specialCaller tùy API)
                    |
         +----------+-----------+---------------------+
         |          |           |                     |
   findVirtual  findStatic  findSpecial        findConstructor
         |          |           |                     |
  receiver+args    args   receiver+args             args
         |          |           |                     |
 virtual dispatch  static  invokespecial rules    tạo object
~~~

Đây là phép so sánh **ngữ nghĩa**, không phải cam kết rằng compiler sẽ sinh trực tiếp các instruction `invokevirtual`, `invokestatic`, `invokespecial` ngay tại source call `handle.invokeExact`.

## 2. `MethodType` đầu vào khác với `MethodHandle.type()`

Giả sử class `Counter` khai báo:

~~~java
public int increment(int value) { return value + 1; }
public static int doubleIt(int value) { return value * 2; }
public Counter(String label) { /* constructor */ }
~~~

Ba dòng chỉ minh họa các thành viên **bên trong class Counter**, chưa phải file chạy độc lập.

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle virtual = lookup.findVirtual(
        Counter.class, "increment", MethodType.methodType(int.class, int.class));
// MethodType tra cứu: (int)int
// virtual.type() : (Counter,int)int

MethodHandle statik = lookup.findStatic(
        Counter.class, "doubleIt", MethodType.methodType(int.class, int.class));
// MethodType tra cứu: (int)int
// statik.type() : (int)int

MethodHandle create = lookup.findConstructor(
        Counter.class, MethodType.methodType(void.class, String.class));
// MethodType tra cứu: (String)void
// create.type() : (String)Counter
~~~

Đoạn trên cần `java.lang.invoke.*` và ngữ cảnh xử lý checked exception. Với `findVirtual`, instance nhận lời gọi là tham số số 0 của **handle**, không nằm trong `MethodType` dùng để tìm member. Với `findStatic`, method không có receiver nên handle giữ nguyên chữ ký. Với `findConstructor`, `void.class` mô tả descriptor JVM của constructor; handle dùng để cấp phát object trả về kiểu tham chiếu `Counter`.

`MethodType.methodType(String.class, int.class, long.class)` có ý nghĩa một hàm trả `String` nhận `int, long`. Nó **không mô tả class type chứa method**, không mô tả generic parameter như `List<String>`: descriptor chạy ở JVM dùng các kiểu runtime đã erasure.

## 3. Lookup và kiểm tra access

`MethodHandles.lookup()` trả `MethodHandles.Lookup` gắn với **lớp thực sự gọi** factory `lookup()`, chứ không gắn với một chuỗi tên class do người dùng nhập. Tại thời điểm `findVirtual`/`findStatic`/`findSpecial`/`findConstructor`, JVM/JDK kiểm tra class, member, chữ ký và access modes của lookup.

- `MethodHandles.lookup()`: sử dụng quyền theo ngữ cảnh caller hiện tại. Có thể tìm public hoặc các member có quyền phù hợp, kể cả private/nestmate trong các tình huống hợp lệ.
- `MethodHandles.publicLookup()`: phù hợp khi chỉ cần public API có thể truy cập theo module rules; không mang private privileges.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)`: thử tạo lookup có quyền private trong `Target` nếu tất cả điều kiện access/module được thỏa mãn. Không phải lệnh vượt JPMS.
- `lookup.in(Other.class)` có thể thay đổi lookup class nhưng giảm access modes. Không được mặc định rằng lookup chuyển kiểu vẫn giữ đủ quyền để gọi `findSpecial`.
- Handle đã tạo thành công trở thành một capability gọi member. Vì access thường được kiểm tra khi **tạo handle**, cần thận trọng khi đưa handle truy cập private member cho code không đáng tin.

Lookup thường báo `NoSuchMethodException` nếu không tìm thấy thành viên theo tên/chữ ký, `IllegalAccessException` nếu không được quyền hoặc chọn sai kind (ví dụ tìm instance method bằng `findStatic`). Phân biệt lỗi lúc lookup với `WrongMethodTypeException` khi gọi `invokeExact`.

## 4. `findVirtual`: gọi instance method theo virtual dispatch

Chữ ký:

~~~java
MethodHandle findVirtual(Class<?> refc, String name, MethodType type)
        throws NoSuchMethodException, IllegalAccessException
~~~

Với `public String greet(String name)` trong class `Parent`:

~~~java
MethodHandle greet = lookup.findVirtual(
        Parent.class, "greet",
        MethodType.methodType(String.class, String.class));
// greet.type() thường là (Parent,String)String

Parent receiver = new Child();
String result = (String) greet.invokeExact(receiver, "An");
~~~

Đây là **đoạn minh họa** với `Child extends Parent` và override `greet`, nên lời gọi có thể chạy `Child.greet("An")`. `findVirtual` tạo handle với receiver argument đầu và với non-private virtual method, implementation được chọn theo runtime class của receiver.

Giải thích:

1. Tham số `Parent.class` là kiểu mà lookup dùng để resolve; `new Child()` vẫn hợp lệ vì object này là instance của `Parent`.
2. `MethodType.methodType(String.class, String.class)` chỉ mô tả `greet(String):String`, **không chứa Parent receiver**.
3. `invokeExact` kiểm tra kiểu receiver compile-time là `Parent` và return type mong đợi là `String`. Dùng biến `Child child` trực tiếp có thể sinh descriptor receiver `Child` không khớp, trừ khi cast sang `Parent`.
4. Với phương thức instance không-private, override trên receiver được tôn trọng; với private method được lookup hợp lệ, không có virtual override dispatch vì private methods không override.
5. Với `protected` khác package, receiver của handle có thể bị giới hạn hẹp hơn `refc` theo quy tắc access, nên kiểm tra `handle.type()` thực tế khi xử lý các case phức tạp.
6. Có thể dùng với interface instance methods; handle có ngữ nghĩa dispatch tương ứng `invokeinterface` khi thích hợp.

**Không dùng `findVirtual` cho static method.** Khi cần một instance cụ thể làm callback, `greet.bindTo(receiver)` cố định receiver rồi trả handle mới không còn tham số receiver đầu; dynamic dispatch vẫn phụ thuộc runtime type của object đó.

## 5. `findStatic`: gọi static method không có receiver

Chữ ký:

~~~java
MethodHandle findStatic(Class<?> refc, String name, MethodType type)
        throws NoSuchMethodException, IllegalAccessException
~~~

Ví dụ với JDK:

~~~java
MethodHandle parse = lookup.findStatic(
        Integer.class, "parseInt",
        MethodType.methodType(int.class, String.class));
int value = (int) parse.invokeExact("123");
~~~

`parse.type()` là `(String)int`. Không truyền `Integer` hay bất cứ receiver nào. Dòng minh họa giả định có biến `lookup` với quyền access hợp lệ và enclosing method `throws Throwable`.

Đặc điểm chính:

- Static method không có dispatch theo runtime receiver; không có receiver để chọn override.
- Subclass có thể *hide* static method cùng tên/chữ ký, nhưng một handle đã resolve tới static target cụ thể không tự chọn lại implementation.
- Khi **gọi** handle, class khai báo static method có thể được khởi tạo nếu trước đó chưa khởi tạo. Không suy luận rằng chỉ tạo handle đã kích hoạt toàn bộ logic static initializer.
- Lookup yêu cầu đúng static method. `findStatic(Foo.class,"run", methodType(...))` sẽ thất bại nếu `run` là instance method.
- Không thêm `Foo.class` vào `MethodType` như một tham số giả; đó là lỗi chữ ký.

Nếu target trả `void`, `MethodType` và `MethodHandle.type()` cùng có return type `void.class`. Với `invokeExact`, kiểu kết quả của call site cũng phải là `void`, ví dụ một expression statement bỏ qua kết quả.

## 6. `findSpecial`: gọi theo ngữ nghĩa `invokespecial`

Chữ ký:

~~~java
MethodHandle findSpecial(Class<?> refc, String name,
                         MethodType type, Class<?> specialCaller)
        throws NoSuchMethodException, IllegalAccessException
~~~

`findSpecial` tạo handle cho lời gọi kiểu `invokespecial`. Khác với `findVirtual`, nó **không chạy normal override dispatch** theo runtime class của receiver. Trường hợp thường thấy là lời gọi `super.method(...)` trong một subclass, hoặc interface default method với cơ chế gọi `InterfaceName.super.method(...)` khi các điều kiện JVM/Java được đáp ứng.

Các tham số:

| Biến | Vai trò |
| --- | --- |
| `refc` | Class/interface làm điểm tham chiếu khi resolve method |
| `name` | Tên instance method, không nhận `"<init>"` để tạo constructor |
| `type` | Chữ ký khai báo của instance method (chưa có receiver) |
| `specialCaller` | Class có ngữ cảnh tương đương chứa chỉ thị `invokespecial`, chi phối quyền và việc chọn body |

**Ràng buộc access then chốt:** Theo Java SE 21 Javadoc, `specialCaller` phải **trùng chính xác lookup class** của `Lookup` dùng tại thời điểm `findSpecial`, và lookup phải có **private access privileges**. Nếu không, `IllegalAccessException` có thể xảy ra trước cả khi method được resolve. Do đó không thể lấy `publicLookup()` rồi đặt `specialCaller` thành bất kỳ class nào để gọi method cha của nó.

Ví dụ class minh họa:

~~~java
class Parent {
    public String greet() { return "Parent"; }
}

class Child extends Parent {
    @Override public String greet() { return "Child"; }

    static MethodHandle parentHandle() throws ReflectiveOperationException {
        // Chính Child gọi lookup(): lookup class = Child
        MethodHandles.Lookup own = MethodHandles.lookup();
        return own.findSpecial(
                Parent.class, "greet",
                MethodType.methodType(String.class),
                Child.class);
    }
}
~~~

Đoạn này cần `import java.lang.invoke.*;` và đặt các class trong ngữ cảnh Java phù hợp. Handle có type thông thường `(Child)String`; gọi với receiver `Child` thực hiện body `Parent.greet()` như một lời gọi `super.greet()`, bất kể `Child` override method.

Lưu ý nâng cao: quy tắc `invokespecial` còn quy định cách chọn phương thức khi `refc` là **ancestor xa** của `specialCaller`. Nếu `C extends B extends A`, `findSpecial(A.class, "m", ..., C.class)` có thể thực thi implementation ở `B` theo quy tắc selection liên quan đến superclass trực tiếp. Vì vậy đừng mô tả `findSpecial` là “gọi chính xác body của class nào tùy ý”.

Constructor trong JVM cũng liên quan opcode `invokespecial`, nhưng `findSpecial` **không dùng cho `"<init>"`**. Phần tạo object được API thiết kế riêng `findConstructor`.

## 7. `findConstructor`: descriptor `void` nhưng handle trả object

Chữ ký:

~~~java
MethodHandle findConstructor(Class<?> refc, MethodType type)
        throws NoSuchMethodException, IllegalAccessException
~~~

Nếu `Ticket` có constructor `public Ticket(long id)`:

~~~java
MethodHandle ctor = lookup.findConstructor(
        Ticket.class, MethodType.methodType(void.class, long.class));
Ticket ticket = (Ticket) ctor.invokeExact(42L);
~~~

Đây là đoạn minh họa cần `Ticket`/`lookup` và method `throws Throwable`. Lookup nhận `(long)void`, còn `ctor.type()` là `(long)Ticket`. Vì sao? Constructor JVM là method khởi tạo instance với descriptor trả `void`; handle của API này đồng thời cấp phát object rồi chạy constructor, nên handle **trả về object đã tạo**.

Nhớ các điểm:

- `findConstructor` không nhận tên chuỗi và không nhận receiver; gọi handle với các tham số constructor đúng thứ tự.
- `refc` là class chứa constructor; constructor không được kế thừa như instance method. `Child.class` không tự lấy constructor từ superclass.
- Không dùng `MethodType.methodType(Ticket.class, long.class)` để lookup constructor, dù handle sau lookup có return type `Ticket`.
- Phải chọn đúng overload constructor theo parameter types. `findConstructor(Ticket.class, methodType(void.class,int.class))` không tự tìm constructor `Ticket(long)` bằng widening trong giai đoạn lookup.
- Constructor `private` cần Lookup đủ quyền; `publicLookup` không tự được dùng mọi constructor private.
- Lần **gọi** handle tạo object có thể kích hoạt class initialization. Exception do constructor ném thường truyền trực tiếp qua method handle, không tự bọc `InvocationTargetException`.

## 8. Ví dụ hoàn chỉnh Java 17+: kiểm chứng bốn factory

Tạo file `LookupMethodsDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupMethodsDemo {
    public static class Parent {
        public String greet(String name) {
            return "Parent: " + name;
        }
    }

    public static class Child extends Parent {
        @Override
        public String greet(String name) {
            return "Child: " + name;
        }

        public static MethodHandle parentGreetHandle()
                throws ReflectiveOperationException {
            // Phương thức này ở trong Child: lookup class chính là Child.
            MethodHandles.Lookup ownLookup = MethodHandles.lookup();
            return ownLookup.findSpecial(
                    Parent.class,
                    "greet",
                    MethodType.methodType(String.class, String.class),
                    Child.class);
        }
    }

    public static class Message {
        private final String content;

        public Message(String content) {
            this.content = content;
        }

        public String show() {
            return "Message(" + content + ")";
        }

        public static Message normalized(String input) {
            return new Message(input.trim().toUpperCase());
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType greetType =
                MethodType.methodType(String.class, String.class);

        // Virtual: lấy method từ Parent, receiver thực là Child.
        MethodHandle virtual = lookup.findVirtual(
                Parent.class, "greet", greetType);
        Parent asParent = new Child();
        String virtualResult = (String) virtual.invokeExact(asParent, "An");
        System.out.println("virtual = " + virtualResult);
        System.out.println("virtual type ok = " + virtual.type().equals(
                MethodType.methodType(String.class, Parent.class, String.class)));

        // Static: không có receiver.
        MethodHandle statik = lookup.findStatic(
                Message.class,
                "normalized",
                MethodType.methodType(Message.class, String.class));
        Message normalized = (Message) statik.invokeExact("  hello  ");
        System.out.println("static = " + normalized.show());
        System.out.println("static type ok = " + statik.type().equals(
                MethodType.methodType(Message.class, String.class)));

        // Special: tạo lookup trong Child để thực hiện body Parent.greet.
        MethodHandle special = Child.parentGreetHandle();
        Child child = new Child();
        String specialResult = (String) special.invokeExact(child, "An");
        System.out.println("special = " + specialResult);
        System.out.println("special type ok = " + special.type().equals(
                MethodType.methodType(String.class, Child.class, String.class)));

        // Constructor: lookup yêu cầu (String)void, handle trả (String)Message.
        MethodHandle constructor = lookup.findConstructor(
                Message.class, MethodType.methodType(void.class, String.class));
        Message created = (Message) constructor.invokeExact("raw");
        System.out.println("constructor = " + created.show());
        System.out.println("constructor type ok = " + constructor.type().equals(
                MethodType.methodType(Message.class, String.class)));

        // bindTo lưu receiver của handle virtual và bỏ tham số receiver đầu.
        MethodHandle bound = virtual.bindTo(asParent);
        String boundResult = (String) bound.invokeExact("Bình");
        System.out.println("bound = " + boundResult);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 LookupMethodsDemo.java
java LookupMethodsDemo
~~~

`stdout` dự kiến:

~~~text
virtual = Child: An
virtual type ok = true
static = Message(HELLO)
static type ok = true
special = Parent: An
special type ok = true
constructor = Message(raw)
constructor type ok = true
bound = Child: Bình
~~~

Phân tích:

1. `virtual.type()` là `(Parent,String)String`. Instance runtime là `Child` nên kết quả `Child: An`.
2. `statik.type()` là `(String)Message`; target `Message.normalized` không nhận receiver. `trim()` bỏ khoảng trắng và `toUpperCase()` chuyển `hello` thành `HELLO`.
3. `Child.parentGreetHandle()` gọi `lookup()` ngay trong `Child`; `findSpecial` nhận `specialCaller=Child.class` và trả handle `(Child,String)String`. Body thực thi là `Parent.greet`, kết quả `Parent: An`.
4. `findConstructor` nhận `MethodType` trả `void` và tạo handle trả `Message`; `new Message("raw")` được thực hiện qua handle.
5. `bound` bỏ receiver từ virtual handle nhưng receiver đã bind vẫn là object `Child`, nên kết quả `Child: Bình`.

Chương trình không cần thêm module `--add-opens` vì các thành viên trong ví dụ có thể được truy cập đúng từ ngữ cảnh `Lookup` đã dùng. `main` khai báo `throws Throwable` vì chữ ký `MethodHandle.invokeExact` cho phép target ném `Throwable`.

## 9. `invokeExact`, `invoke` và thích nghi kiểu

Một handle có chữ ký **cố định**; `invokeExact` đòi **descriptor tại call site**, gồm kiểu tham số và **kiểu kết quả**, đúng bằng `handle.type()`. Với `virtual.type() = (Parent,String)String`:

~~~java
Parent parent = new Child();
String ok = (String) virtual.invokeExact(parent, "A"); // Đúng

Child child = new Child();
// String wrong = (String) virtual.invokeExact(child, "B");
// Sai vì compiler lập descriptor (Child,String)String.
~~~

Đây là đoạn minh họa trong method có class/biến đã khai báo. Receiver là `Child` vẫn *là* một `Parent` trong Java, nhưng `invokeExact` nhìn **kiểu compile-time tại call site**. Cast `(Parent) child` hoặc gán vào biến kiểu `Parent` để khớp. Tương tự, nếu handle trả `Message` mà call site trông đợi `Object`, `invokeExact` có thể ném `WrongMethodTypeException`.

- `invoke(...)` cho phép một số conversion tương thích theo `asType`; không có nghĩa tự chuyển mọi giá trị.
- `asType(newType)` tạo một handle adapter theo các quy tắc chuyển kiểu được hỗ trợ. Nó không đổi member thực hay quyền truy cập vốn có.
- `bindTo(receiver)` ràng buộc argument đầu tiên có kiểu reference, giảm số tham số của handle đi một.
- `handle.type()` và `MethodType.methodType(...)` giúp kiểm tra chính xác trước khi invoke.
- Khi dùng `invokeExact` trong expression statement với method trả `void`, call site phải mong đợi `void`; khi nhận primitive `int` phải có ngữ cảnh kết quả `int`.

Ví dụ với constructor handle `(String)Message`:

~~~java
Message a = (Message) constructor.invokeExact("A");
// Object b = constructor.invokeExact("B"); // Sai type kỳ vọng.
Object c = constructor.invoke("C");          // invoke có thể adapt return Message -> Object.
~~~

`Object c` là lời gọi minh họa để phân biệt `invoke` với `invokeExact`; cả hai đều yêu cầu code có `throws Throwable`.

## 10. So sánh virtual dispatch, static hiding và special invocation

Cho quan hệ:

~~~java
class A {
    String name() { return "A"; }
    static String kind() { return "A"; }
}
class B extends A {
    @Override String name() { return "B"; }
    static String kind() { return "B"; }
}
class C extends B {
    @Override String name() { return "C"; }
}
~~~

Đây là các class minh họa, không phải file độc lập. Phân biệt:

- Handle `findVirtual(A.class, "name", methodType(String.class))` với receiver thực là `C` có thể chạy `C.name()` theo virtual dispatch.
- Handle `findStatic(A.class, "kind", methodType(String.class))` chạy đúng static target đã resolve từ `A`; không hỏi object runtime và không dispatch đến `B.kind()`.
- `findSpecial(A.class, "name", methodType(String.class), C.class)` (nếu tạo bằng lookup hợp lệ bên trong `C`) có ngữ nghĩa `invokespecial`, **không đảm bảo gọi body A.name()**. JVM còn áp dụng lựa chọn superclass trực tiếp; trong hierarchy tương ứng, có thể chọn `B.name()`. Đây là điểm khác với suy nghĩ “findSpecial ép chọn bất kỳ ancestor được truyền vào”.
- Constructor không tham gia virtual dispatch hay static hiding; nó chọn overload của class cụ thể.

Nếu có interface default method, `findSpecial` trong class triển khai hợp lệ có thể mô phỏng ý nghĩa `InterfaceName.super.method()` khi thỏa điều kiện caller/access; dùng `findVirtual` khi bạn cần hành vi dispatch thông thường.

## 11. Overload, varargs, generic và constructor

**Overload:** lookup chọn theo `MethodType` đã khai báo, không tự chạy Java overload resolution từ argument values của lời gọi runtime. `findVirtual(Foo.class,"set",methodType(void.class,int.class))` khác `methodType(void.class,Integer.class)`. Constructor cũng vậy: `findConstructor(Foo.class,methodType(void.class,int.class))` không tự tìm constructor chỉ nhận `long`.

**Generic:** `MethodType` dùng runtime `Class<?>` sau type erasure. Method khai báo `List<String> values()` có return type descriptor `List.class`, không có `List<String>.class`. Generic metadata là chuyện khác, có thể đọc bằng reflection nếu cần.

**Varargs:** Một method/constructor khai báo `String... pieces` thực tế có parameter type cuối `String[].class` trong bước lookup. Handle có thể có tính chất variable-arity collector, cho phép một số lời gọi `invoke` gom đối số thành mảng; `asFixedArity()` dùng khi muốn cố định arity. Không tra cứu bằng `String.class` chỉ vì source khai báo `String...`.

**Constructor:** Khi `new` một object qua handle, constructor trả `void` theo JVM descriptor, còn object mới là giá trị trả về của handle. Đừng viết `methodType(Foo.class, ...)` ở `findConstructor`.

## 12. Lỗi thường gặp và cách sửa

| Khi nào? | Lỗi / biểu hiện | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- | --- |
| Lúc lookup | `NoSuchMethodException` | Tên/method type sai, overload không tồn tại | Kiểm tra tên, return, parameter types chính xác |
| Lúc lookup | `IllegalAccessException` | Member không truy cập được, sai kind, `findSpecial` thiếu private access/sai `specialCaller` | Xác minh `lookup.lookupClass()`, access modes, JPMS, method kind |
| Lúc lookup | `NullPointerException` | Truyền `null` cho refc/name/type/specialCaller bắt buộc | Validate input |
| Lúc invoke | `WrongMethodTypeException` | Call-site descriptor `invokeExact` khác `handle.type()` | Kiểm tra receiver compile-time type, args, return type |
| Lúc invoke | `ClassCastException` hoặc lỗi conversion | `invoke`/`asType` không thể chuyển kiểu | Chọn adapter/kiểu tương thích |
| Lúc invoke | `NullPointerException` | Receiver instance bằng `null` hoặc target tự ném | Kiểm tra receiver và stack trace |
| Lúc invoke | Exception/error từ method đích | Business logic/constructor lỗi | Bắt loại exception thực, phân biệt với lookup failure |
| Lúc invoke | `ExceptionInInitializerError` | Static method/constructor kích hoạt initializer lỗi | Kiểm tra lỗi khởi tạo class và cause |

### Ba lỗi tinh vi

1. **Tự thêm receiver vào `MethodType` tìm `findVirtual`**: khiến lookup tìm chữ ký không có thực. Receiver chỉ xuất hiện trong handle trả về.
2. **Truyền `specialCaller` khác lookup class**: fail access mặc dù method là public. Với `findSpecial`, private access và caller relation là phần của contract.
3. **Dùng return type class ở `findConstructor`**: ví dụ `methodType(Foo.class,String.class)` là sai; phải tìm `methodType(void.class,String.class)` rồi nhận handle có result `Foo`.

Với `MethodHandle`, exception do target ném thường đi ra trực tiếp chứ không được bọc mặc định như `InvocationTargetException` của `java.lang.reflect.Method.invoke`. Đừng bắt `InvocationTargetException` theo thói quen khi không sử dụng reflection `Method.invoke`.

## 13. Quy trình áp dụng thực tế

1. Xác định mục tiêu: instance polymorphic, static, super/default-special hay constructor. Bốn factory không hoán đổi cho nhau.
2. Tạo `Lookup` từ code có quyền phù hợp. Nếu cần `findSpecial`, đặt điểm tạo `Lookup` đúng caller class hoặc dùng cách được quyền theo quy tắc API; không suy đoán về private access xuyên module.
3. Xác định `MethodType` đúng descriptor khai báo; constructor có return type `void` và instance method không chứa receiver.
4. Lookup handle và phân biệt `NoSuchMethodException` / `IllegalAccessException` ở bước resolve với lỗi runtime của target.
5. Kiểm tra `handle.type()` khi kết nối dynamic dispatcher; dùng `invokeExact` chỉ khi call-site type khớp hoàn toàn. Dùng `invoke`, `asType` hoặc `bindTo` khi có lý do rõ ràng.
6. Nếu gọi lặp lại cùng một method, có thể cache handle để tránh repeated lookup, nhưng cân nhắc class loader lifecycle và access.
7. Với performance, benchmark workload thực bằng JMH nếu cần; MethodHandle có thể được JVM tối ưu, nhưng không bảo đảm luôn nhanh hơn reflection hoặc lời gọi trực tiếp.

## 14. Tự kiểm tra

**Câu 1.** `findVirtual(Foo.class,"run",methodType(void.class,int.class))` trả handle thông thường có type gì?

**Đáp án:** `(Foo,int)void`; receiver được thêm vào đầu sau lookup.

**Câu 2.** `findStatic` cần receiver lúc invoke không?

**Đáp án:** Không. Target là static method đã resolve; handle nhận đúng các declared parameters.

**Câu 3.** Vì sao `findVirtual(Parent.class,"greet",...)` với instance runtime `Child` chạy override của `Child`?

**Đáp án:** Virtual dispatch chọn implementation theo runtime class receiver cho method có thể override.

**Câu 4.** `findSpecial` có thể đặt `specialCaller` tùy ý không?

**Đáp án:** Không. `specialCaller` phải trùng lookup class và lookup cần private access; JVM cũng kiểm tra quan hệ/đích hợp lệ.

**Câu 5.** Tại sao `findConstructor(Foo.class, methodType(void.class,String.class))` tạo handle trả `Foo`?

**Đáp án:** Constructor JVM mô tả `(String)void`, nhưng handle thực hiện cấp phát và khởi tạo rồi trả object `Foo` mới.

**Câu 6.** Có thể dùng `findSpecial(Foo.class,"<init>",...)` để gọi constructor không?

**Đáp án:** Không; dùng `findConstructor`.

**Câu 7.** `invokeExact` nhận biến `Child child` cho handle receiver type `Parent` có chắc chạy?

**Đáp án:** Không. Descriptor của call site mang type compile-time `Child`, phải cast/gán sang `Parent` hoặc chọn adapter hợp lệ.

**Câu 8.** `NoSuchMethodException` khác `WrongMethodTypeException` ở đâu?

**Đáp án:** Loại đầu thường xuất hiện khi tra cứu member không có chữ ký đúng; loại sau xuất hiện khi gọi handle không khớp chữ ký.

**Câu 9.** Gọi method qua handle có tự bọc business exception trong `InvocationTargetException` không?

**Đáp án:** Không mặc định; target exception được truyền trực tiếp theo semantics của MethodHandle.

## Tài liệu chuẩn

- [Java SE 21 — MethodHandles.Lookup và bốn factory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 21 — MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 21 — MethodHandle: invokeExact, invoke, asType, bindTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 21 — MethodHandles.privateLookupIn](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup))
- [Java Virtual Machine Specification SE 21 — Method Invocation Instructions](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html)
