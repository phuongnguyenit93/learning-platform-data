# 1.2. Phân biệt kiểu tĩnh, phân phối động của OOP và lời gọi được quyết định lúc chạy

Trong Java, **kiểu của một biểu thức được kiểm tra lúc biên dịch** nhưng **phần cài đặt của một phương thức instance có thể được chọn lúc chạy**. Hai điều này cùng tồn tại, không mâu thuẫn. Cũng cần phân biệt cơ chế đa hình thông thường với các cơ chế chủ động tìm hoặc liên kết lời gọi khi chương trình đang chạy, chẳng hạn Reflection, Method Handle và bytecode `invokedynamic`.

Sau bài này, bạn có thể xác định: trình biên dịch nhìn thấy kiểu nào; overload nào được chọn; phương thức override nào chạy; khi nào cần tra cứu phương thức ở runtime; và vì sao `invokevirtual` không đồng nghĩa với `invokedynamic`.

## 1. Ba khái niệm dễ bị trộn lẫn

Xét biểu thức:

```java
Animal pet = new Dog();
```

- **Kiểu tĩnh (static/declared type)** của biến `pet` là `Animal`. `javac` dùng kiểu này để kiểm tra thành viên có thể truy cập, chữ ký lời gọi, phép gán và phép ép kiểu. Java là ngôn ngữ có hệ thống kiểu tĩnh.
- **Kiểu thực tế (runtime class)** của đối tượng đang được `pet` tham chiếu là `Dog`. Đây là thông tin runtime dùng khi phân phối lời gọi phương thức instance có thể override.
- **Phân phối động (dynamic dispatch)** là bước chọn **implementation** cho một chữ ký phương thức đã được xác định, dựa trên kiểu thực tế của receiver. Nó không có nghĩa runtime tự tìm một overload bất kỳ theo kiểu thực tế của mọi đối số.

Một biến có thể lần lượt tham chiếu các đối tượng thuộc những lớp con khác nhau, miễn là phép gán hợp lệ. Tên lớp bên trái phép gán không đổi chỉ vì đối tượng bên phải có lớp con cụ thể. Giá trị `null` không có đối tượng đích; nếu gọi phương thức instance trên receiver `null`, lời gọi sẽ ném `NullPointerException`.

| Câu hỏi | Chủ yếu được quyết định ở đâu? | Ví dụ |
| --- | --- | --- |
| `pet` có thể gọi những phương thức nào, theo chữ ký nào? | Lúc biên dịch, từ kiểu tĩnh và quyền truy cập | `Animal` phải khai báo/thừa kế phương thức phù hợp |
| Khi có nhiều overload cùng tên, chọn chữ ký nào? | Lúc biên dịch, theo kiểu biểu thức đối số và quy tắc overload | `feed(Object)` hay `feed(String)` |
| Với chữ ký instance có thể override, chạy thân phương thức nào? | Lúc chạy, theo lớp thực tế của receiver | `Dog.speak()` thay cho `Animal.speak()` |
| Tên phương thức/lớp chỉ được biết khi chạy thì tìm bằng cách nào? | Runtime lookup hoặc runtime linkage chuyên biệt | Reflection, Method Handle, `invokedynamic` |

Lưu ý thuật ngữ: **static type** không phải **static method**. `static` trong `Animal pet` nói về việc kiểm tra kiểu; `static` trong `static void f()` nói về thành viên thuộc lớp, không tham gia override kiểu instance.

## 2. Quy trình hai bước: overload trước, override sau

Khi gặp `receiver.method(argument)`, hãy tách hai việc:

1. **Compile time:** `javac` xác định kiểu tĩnh của receiver và các đối số; tìm các phương thức khả dụng; áp dụng quy tắc overload để chọn **một chữ ký**. Kiểu trả về, phạm vi truy cập, khả năng chuyển đổi kiểu, varargs và generic có thể ảnh hưởng đến tính hợp lệ của lời gọi. Chữ ký được chọn phải hợp lệ dù đối tượng runtime sau này thuộc lớp con nào.
2. **Runtime:** nếu lời gọi là phương thức instance có thể override (`invokevirtual`/`invokeinterface`), JVM chọn implementation tương ứng với **chính chữ ký đã chọn** trên lớp thực tế của receiver. Nó không quay lại chọn overload dựa trên lớp thực tế của đối số.

Với static method, constructor, lời gọi `super` và private method, không có cơ chế override instance thông thường. Các trường (field) cũng không có phân phối động như phương thức instance.

### Ví dụ Java 17+ biên dịch và chạy độc lập

Lưu tệp sau đúng tên `DispatchDemo.java`:

```java
public class DispatchDemo {
    static class Animal {
        String role = "animal";

        String speak() {
            return "Animal.speak";
        }

        String feed(Object food) {
            return "Animal.feed(Object): " + food;
        }

        static String kind() {
            return "Animal.kind";
        }
    }

    static class Dog extends Animal {
        String role = "dog";

        @Override
        String speak() {
            return "Dog.speak";
        }

        @Override
        String feed(Object food) {
            return "Dog.feed(Object): " + food;
        }

        String feed(String food) {
            return "Dog.feed(String): " + food;
        }

        static String kind() {
            return "Dog.kind";
        }
    }

    interface Greeter {
        String greet();
    }

    static class FriendlyDog extends Dog implements Greeter {
        @Override
        public String greet() {
            return "FriendlyDog.greet";
        }
    }

    public static void main(String[] args) {
        Animal pet = new Dog();

        System.out.println("speak: " + pet.speak());
        System.out.println("feed via Animal: " + pet.feed("bone"));
        System.out.println("feed via Dog: " + ((Dog) pet).feed("bone"));
        System.out.println("field via Animal: " + pet.role);
        System.out.println("static Animal: " + Animal.kind());
        System.out.println("static Dog: " + Dog.kind());

        Greeter greeter = new FriendlyDog();
        System.out.println("interface: " + greeter.greet());
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 DispatchDemo.java
java DispatchDemo
```

Kết quả:

```text
speak: Dog.speak
feed via Animal: Dog.feed(Object): bone
feed via Dog: Dog.feed(String): bone
field via Animal: animal
static Animal: Animal.kind
static Dog: Dog.kind
interface: FriendlyDog.greet
```

**Phân tích từng điểm mấu chốt:**

- `pet.speak()`: kiểu tĩnh `Animal` cho phép gọi `speak()`; đối tượng thực tế `Dog` đã override đúng chữ ký, nên chạy `Dog.speak()`.
- `pet.feed("bone")`: dù `"bone"` là `String`, tại vị trí gọi `pet` chỉ có kiểu tĩnh `Animal`, nơi overload khả dụng là `feed(Object)`. `javac` chọn `Animal.feed(Object)`. Lúc chạy, `Dog.feed(Object)` **override chính chữ ký ấy**, vì vậy kết quả là `Dog.feed(Object): bone`; runtime **không đổi** sang `Dog.feed(String)`.
- `((Dog) pet).feed("bone")`: sau khi ép kiểu, receiver trong biểu thức có kiểu tĩnh `Dog`; overload `feed(String)` giờ có thể được chọn vì cụ thể hơn `feed(Object)`. Phép ép kiểu còn được JVM kiểm tra lúc chạy; ép một `Animal` không thực sự là `Dog` sẽ gây `ClassCastException`.
- `pet.role`: field được chọn theo **kiểu tĩnh** `Animal`, nên giá trị là `animal` dù đối tượng có field `Dog.role`. Đây là **field hiding**, không phải method overriding.
- `Animal.kind()` và `Dog.kind()`: hai static method có cùng chữ ký là **method hiding**. Dùng tên lớp cho rõ ràng; static method không được phân phối theo lớp runtime của receiver.
- `greeter.greet()`: biến có kiểu interface `Greeter`; đối tượng `FriendlyDog` cung cấp implementation. Đây cũng là đa hình runtime, thường tương ứng với bytecode `invokeinterface`.

`@Override` không tạo ra cơ chế phân phối động; nó yêu cầu trình biên dịch xác nhận phương thức thật sự override/implement một phương thức hợp lệ. Nhờ đó, lỗi sai chữ ký dễ được phát hiện. Nếu bỏ `@Override` và vô tình viết `feed(String)` trong khi định ghi đè `feed(Object)`, bạn đã tạo overload mới chứ chưa ghi đè phương thức cũ.

## 3. Có thể và không thể quyết định lại ở runtime

**Có thể đổi implementation:** cùng lời gọi `pet.speak()` có thể chạy thân phương thức khác nhau nếu lần lượt truyền `Animal`, `Dog`, hoặc lớp con khác có override. Đây là điểm mở rộng cốt lõi của OOP: caller phụ thuộc hợp đồng kiểu cha/interface thay vì chọn thủ công từng lớp con.

**Không thể tự xuất hiện thành viên mới qua biến kiểu cha:** nếu `Dog` có phương thức riêng `wagTail()` mà `Animal` không khai báo hoặc kế thừa, biểu thức `pet.wagTail()` không hợp lệ khi biên dịch chỉ vì runtime có thể là `Dog`. Muốn gọi trực tiếp, cần một kiểu tĩnh khai báo phương thức đó (ví dụ ép kiểu đã kiểm tra hoặc dùng interface phù hợp). Một cách khác là runtime lookup như Reflection, nhưng đó là cơ chế khác.

**Không thể đổi overload sau biên dịch:** giả sử có `print(Object)` và `print(String)`. Với `Object value = "hi";`, lời gọi `print(value)` sẽ chọn overload `print(Object)` lúc biên dịch, dù đối tượng runtime là `String`. Nếu overload được chọn có override ở một lớp con thì bước override vẫn diễn ra sau đó; hai bước không được nhập làm một.

**Không phải mọi lời gọi đều virtual:** `static`, `private`, `super.method()`, constructor và truy cập field có quy tắc liên kết khác. Phương thức `final` không thể bị override, dù opcode do trình biên dịch phát ra vẫn có thể là `invokevirtual`; **opcode** và khả năng override không phải hai khái niệm đồng nhất.

## 4. Nhìn vào bytecode: điều gì thực sự “động”?

Sau khi biên dịch ví dụ trên, thử:

```bash
javap -c -p DispatchDemo
```

Hãy tìm các lời gọi (mã số constant-pool có thể khác nhau giữa bản JDK):

| Opcode JVM | Ý nghĩa điển hình | Điểm cần nhớ |
| --- | --- | --- |
| `invokevirtual` | Gọi phương thức instance theo class | Có thể thực hiện dynamic dispatch để tìm override theo lớp thực tế |
| `invokeinterface` | Gọi phương thức qua interface | Tìm implementation tương ứng trên đối tượng thực tế |
| `invokestatic` | Gọi static method | Không phải virtual override |
| `invokespecial` | Constructor, private method hoặc lời gọi `super` và một số trường hợp đặc biệt | Không phân phối override theo cách của lời gọi virtual thông thường |
| `invokedynamic` | Runtime linkage thông qua bootstrap method và `CallSite` | Một cơ chế liên kết call site khác, **không phải** opcode mặc định cho mọi lời gọi đa hình |

Trong bytecode của `pet.feed("bone")`, tham chiếu phương thức vẫn gắn với **chữ ký** `Animal.feed(Object)`, không phải `Dog.feed(String)`. Khi receiver là `Dog`, JVM tìm override `Dog.feed(Object)`. Đây là bằng chứng cho việc overload và override xảy ra ở hai thời điểm khác nhau.

`invokedynamic` được thiết kế để liên kết một call site linh hoạt khi chạy. Một bootstrap method cung cấp `CallSite` có target là một `MethodHandle`; tùy loại `CallSite`, target có thể cố định hoặc thay đổi theo hợp đồng của nó. Trong Java hiện đại, compiler thường dùng `invokedynamic` để triển khai lambda và phép nối chuỗi; cách phát bytecode cụ thể tùy JDK/compiler. Vì thế, bạn **có thể** nhìn thấy `invokedynamic` cho phép nối chuỗi trong `System.out.println("speak: " + pet.speak())`, nhưng đó không có nghĩa `pet.speak()` đã trở thành một lời gọi Reflection hay một overload được chọn lại ở runtime.

JVM có thể inline/devirtualize một lời gọi khi JIT chứng minh được kiểu đích phù hợp, rồi hủy tối ưu nếu giả định không còn đúng. Tối ưu hóa hiệu năng này phải giữ nguyên ngữ nghĩa đa hình đã được Java quy định; “phân phối động” không đồng nghĩa mọi lần thực thi đều bắt buộc dò bảng phương thức từ đầu.

## 5. Runtime lookup: khi cả đích gọi chỉ được biết trong lúc chạy

Đa hình thông thường cần compiler biết **hợp đồng phương thức** trước. Nếu ứng dụng đọc tên lớp, tên phương thức hoặc plugin từ cấu hình, nó có thể cần **Reflection** hoặc **Method Handle** để tìm đích khi chạy.

Ví dụ Reflection độc lập, lưu tên `ReflectiveCallDemo.java`:

```java
import java.lang.reflect.Method;

public class ReflectiveCallDemo {
    public static class Hello {
        public String say(String name) {
            return "Xin chào, " + name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        String className = "ReflectiveCallDemo$Hello";

        Class<?> type = Class.forName(className);
        Object instance = type.getDeclaredConstructor().newInstance();
        Method method = type.getMethod("say", String.class);

        Object result = method.invoke(instance, "Lan");
        System.out.println(result);
    }
}
```

```bash
javac -encoding UTF-8 ReflectiveCallDemo.java
java ReflectiveCallDemo
```

```text
Xin chào, Lan
```

Ở đây `Class.forName` tìm lớp qua **tên nhị phân** lúc chạy (dấu `$` biểu thị lớp lồng); `getMethod("say", String.class)` tìm public method theo tên và tham số; `Method.invoke` gọi phương thức trên object thực tế. Compiler không kiểm chứng chuỗi `"say"` có đúng là một method tồn tại. Đổi tên hoặc chữ ký có thể dẫn tới `ClassNotFoundException`, `NoSuchMethodException`, `IllegalAccessException` và các lỗi khác khi chạy. Nếu thân phương thức được Reflection gọi ném exception, `Method.invoke` đóng gói nguyên nhân trong `InvocationTargetException`.

Các cơ chế liên quan nhưng khác nhau:

- **Dynamic dispatch OOP:** caller đã có chữ ký `speak()` qua kiểu `Animal`/interface; runtime chỉ chọn implementation thích hợp. Đây là lựa chọn mặc định cho đa hình và mở rộng bằng interface.
- **Reflection (`Class`, `Method`, `Constructor`):** cho phép tra cứu metadata và thực thi khi tên/chữ ký được cung cấp tại runtime; đổi lại kiểm tra kiểu bị dời về runtime, cần xử lý access và exception.
- **Method Handle (`java.lang.invoke`):** biểu diễn đích gọi có kiểu phương thức (`MethodType`); có thể được tìm/ghép ở runtime rồi gọi bằng `invoke` hoặc `invokeExact`. Nó liên quan đến hạ tầng `invokedynamic` nhưng sử dụng `MethodHandle` **không tự làm** cho một lời gọi trở thành opcode `invokedynamic`.
- **Dynamic Proxy:** một đối tượng proxy triển khai interface và chuyển lời gọi đến `InvocationHandler`; hữu ích với cross-cutting concerns, interceptor, RPC. Nó vẫn chịu các hợp đồng interface và không biến Java thành ngôn ngữ kiểu động.
- **`invokedynamic`:** bytecode có bootstrap liên kết call site lúc chạy; đây là cơ chế cấp JVM. Đừng dùng tên opcode làm tên gọi chung cho `invokevirtual`, Reflection hoặc proxy.

Điểm chung là có quyết định được dời tới runtime; **điểm khác** là quyết định đó liên quan đến implementation của chữ ký đã biết, việc tìm method theo metadata, hay việc liên kết toàn bộ call site.

## 6. Khi thiết kế ứng dụng, nên chọn gì?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Nhiều cách xử lý cùng một hợp đồng, ví dụ `PaymentProcessor.process()` | Interface + override | Kiểm tra kiểu tại compile time, mở rộng implementation tự nhiên |
| Hai hàm cùng tên phục vụ kiểu tham số khác nhau | Overload có chủ đích | Caller chọn chữ ký từ kiểu tĩnh; tránh kỳ vọng runtime chọn theo lớp đối số |
| Cần gọi plugin có tên class do cấu hình đưa vào lúc chạy | Cơ chế plugin/ServiceLoader; Reflection khi thật sự cần | Có thể phát hiện provider ở runtime nhưng vẫn nên kiểm tra contract rõ ràng |
| Cần adapter/interceptor theo interface | Dynamic Proxy hoặc implementation/decorator cụ thể | Thể hiện rõ boundary cho lời gọi được chặn |
| Viết framework runtime linkage, lambda factory hoặc công cụ JVM | Method Handle / `invokedynamic` khi có lý do kỹ thuật | Kiểm soát liên kết call site, chấp nhận độ phức tạp lớn hơn |

Trước khi dùng Reflection chỉ để chọn giữa các lớp con đã biết, cân nhắc interface, factory hoặc dependency injection: chúng thường dễ kiểm tra kiểu, dễ refactor và dễ test hơn. Dù runtime dispatch có thể có chi phí, không nên mặc định nó chậm: JVM tối ưu các lời gọi phổ biến khá tốt. Hãy đo hiệu năng thực tế trước khi thay đổi thiết kế.

## 7. Các lỗi tư duy và cách tự kiểm tra

1. **“Java kiểu tĩnh nên không thể gọi động.”** Sai: static type checking và dynamic method dispatch hoạt động ở hai tầng khác nhau.
2. **“Đối tượng là `Dog` nên overload `Dog.feed(String)` chắc chắn chạy.”** Sai khi receiver có kiểu tĩnh `Animal`: overload được chọn trước theo `Animal`, rồi mới dispatch override cùng chữ ký.
3. **“`static` method là một dạng override.”** Sai: nó được ẩn (hiding); nên gọi bằng tên lớp. Field cũng bị ẩn, không được virtual dispatch.
4. **“Mọi gọi động trong JVM đều dùng `invokedynamic`.”** Sai: `invokevirtual` và `invokeinterface` đã hỗ trợ đa hình runtime thông thường.
5. **“Ép kiểu đổi đối tượng thành lớp khác.”** Sai: cast kiểm tra/cung cấp một kiểu biểu thức mới; object vẫn là object cũ. Cast sai ném `ClassCastException`.
6. **“Dùng Reflection thì không cần quan tâm chữ ký/khả năng truy cập.”** Sai: việc kiểm tra chuyển sang lúc chạy; lỗi có thể xuất hiện muộn và khó phát hiện hơn.
7. **“Runtime dispatch luôn cản trở tối ưu hóa.”** Không chính xác: JIT có thể inline dựa trên quan sát/giả định hợp lệ, đồng thời giữ đúng ngữ nghĩa khi lớp đích thay đổi.

**Bài tự kiểm tra nhanh (dựa trên `DispatchDemo`):**

- `Animal x = new Dog(); x.speak()` trả gì? → `Dog.speak` vì override được dispatch theo runtime class.
- `Animal x = new Dog(); x.feed(42)` trả gì? → `Dog.feed(Object): 42`, bởi compiler chọn `feed(Object)` và `Dog` override chữ ký đó.
- `Animal x = new Dog(); x.role` trả gì? → `animal`, vì truy cập field phụ thuộc kiểu tĩnh.
- `((Dog) x).feed("bone")` chọn overload nào? → `Dog.feed(String)`, bởi kiểu tĩnh của receiver sau cast là `Dog`.
- Nếu `x` thực sự trỏ tới `new Animal()`, cast `(Dog) x` có tạo ra một `Dog` không? → Không; phép cast sẽ ném `ClassCastException`.
- Thấy `invokedynamic` trong `javap` có đủ kết luận chương trình đang dùng Reflection không? → Không; có thể chỉ là lambda hoặc string concatenation.

**Quy tắc đọc một lời gọi Java:** xác định **kiểu tĩnh của receiver và đối số → chữ ký/overload mà compiler chọn → loại lời gọi (virtual, interface, static, special hay dynamic linkage) → lớp thực tế của receiver nếu cần dispatch → implementation hoặc call-site target thực thi**. Tách đúng những bước này sẽ giúp dự đoán hành vi, đọc bytecode và gỡ lỗi cơ chế runtime chính xác.