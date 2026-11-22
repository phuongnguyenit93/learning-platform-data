# Default method và lời gọi ở mức bytecode trong Java 8+

> **Chủ đề cha:** JVM và công cụ. *Default method* cho phép interface có một phương thức instance kèm phần thân mặc định để class triển khai có thể dùng hoặc override. Method body được lưu trong **class file của interface**; class triển khai không cần có bản copy. Khi gọi, JVM chọn implementation theo kiểu tĩnh của receiver, class hierarchy và superinterface hierarchy. Vì vậy cùng một method có thể được gọi bằng `invokeinterface`, `invokevirtual` hoặc `invokespecial`. Bài này dùng `javap` để quan sát bytecode Java 8 và giải thích sự khác nhau.

## 1. Mục tiêu học tập

Bạn sẽ có thể:
1. Giải thích vì sao Java 8 bổ sung default method và cách nó hỗ trợ tiến hóa interface.
2. Viết đúng default method, phân biệt với abstract/static/private interface method.
3. Áp dụng quy tắc chọn implementation: class/superclass, subinterface cụ thể hơn, và xử lý hai default độc lập.
4. Dùng `InterfaceName.super.method()` để gọi default method của direct superinterface.
5. Biết default method được lưu trong interface class file, không được copy vào class triển khai.
6. Đọc method flags, `Code` attribute, constant pool, method descriptor và class-file major version.
7. Phân biệt `invokeinterface`, `invokevirtual`, `invokespecial` và `invokestatic`.
8. Dùng `javap -c -p -v` để kiểm tra instruction và symbolic reference thực tế.
9. Hiểu trường hợp receiver kiểu class nhưng JVM vẫn chọn default method từ interface.
10. Nhận biết rủi ro binary compatibility khi thêm default method vào interface đã phát hành.

## 2. Default method giải quyết vấn đề gì?

Trước Java 8, interface chủ yếu khai báo các method trừu tượng. Nếu thư viện thêm một abstract method vào interface đã có nhiều class bên thứ ba triển khai, các class đó có thể phải bổ sung implementation khi biên dịch lại.

Java 8 cho phép interface định nghĩa method có body:

```java
public interface Logger {
    void log(String message);

    default void flush() {
        // Hành vi mặc định chung.
    }
}
```

Class cũ có thể kế thừa `flush()` mà không cần override. Class cần hành vi riêng vẫn có thể khai báo `@Override public void flush()`.

**Default method là instance method có body trong interface.** Nó có receiver `this`, có thể gọi abstract instance method khác, nhưng không biến interface thành class: interface không có instance field, constructor hay state riêng của mỗi object.

### 2.1. Cú pháp và đặc điểm

```java
public interface Greeter {
    default String greet(String name) {
        return "Hello, " + name;
    }
}

class EnglishGreeter implements Greeter {
    // Kế thừa greet() mà không cần viết lại.
}
```

- `default` là modifier dành cho method trong interface.
- Method default là `public`; nếu bỏ chữ `public` thì nó vẫn được hiểu là public.
- Method phải có body; không thể vừa `default` vừa `abstract`.
- Class triển khai có thể kế thừa hoặc override method.
- Khi override, không được giảm mức truy cập của method public.
- Nên dùng `@Override` để compiler kiểm tra ý định override.

Default method không phải một “method được tự động copy” vào mọi class triển khai. Đây là một implementation thuộc interface, được JVM tìm khi cần chọn method cho object.

### 2.2. Default khác abstract, static và private interface method

| Loại method | Có body? | Có receiver object? | Class triển khai kế thừa như instance behavior? |
| --- | --- | --- | --- |
| Abstract interface method | Không | Có khi được gọi qua object | Concrete class phải cung cấp implementation |
| Default interface method | Có | Có | Có, nếu không bị override/quy tắc ưu tiên khác chi phối |
| Static interface method | Có | Không | Không kế thừa như instance method |
| Private interface method | Có | Có hoặc static tùy khai báo | Không được class triển khai kế thừa |

Static method trong interface đã có từ Java 8 nhưng không phải default method:

```java
interface Texts {
    static String empty() {
        return "";
    }
}

String value = Texts.empty();
```

Private interface methods chỉ có từ **Java 9**; chúng hỗ trợ chia sẻ code nội bộ giữa các method trong interface, không phải API để class triển khai gọi trực tiếp. Ví dụ Java 8 trong bài không dùng private interface method.

Default method cũng không được khai báo method override-equivalent với các method public của `Object` như `toString()`, `equals(Object)` hoặc `hashCode()`. Các method đó đã có implementation trong class hierarchy và có quy tắc riêng.

## 3. Quy tắc chọn implementation khi nhiều interface cùng khai báo method

### 3.1. Method trong class hoặc superclass được ưu tiên

Nếu class hierarchy có method instance trùng signature với default method của interface, method trong class hierarchy được ưu tiên:

```java
interface HasOrigin {
    default String origin() {
        return "interface";
    }
}

class Parent {
    public String origin() {
        return "class";
    }
}

class Child extends Parent implements HasOrigin {
    // Kế thừa Parent.origin().
}

// new Child().origin() trả "class".
```

Nếu superclass khai báo method abstract, default method không tự động xóa nghĩa vụ implement abstract method của class hierarchy. Concrete subclass có thể vẫn phải override method đó.

### 3.2. Default từ subinterface cụ thể hơn được ưu tiên

Nếu một interface con override default method của interface cha, implementation từ interface con cụ thể hơn sẽ được kế thừa:

```java
interface Root {
    default String label() { return "root"; }
}

interface Left extends Root {
    @Override
    default String label() { return "left"; }
}

interface Right extends Root {
    // Kế thừa Root.label().
}

interface Bottom extends Left, Right {
    // Kế thừa Left.label(), vì Left cụ thể hơn Root.
}
```

Nhiều đường kế thừa tới cùng một declaration không tự tạo ra nhiều implementation khác nhau.

### 3.3. Hai default độc lập: class phải giải quyết xung đột

Nếu hai superinterface không liên quan khai báo default method có cùng signature, compiler không tự chọn theo thứ tự `implements`:

```java
interface A {
    default String value() { return "A"; }
}

interface B {
    default String value() { return "B"; }
}

// Không hợp lệ nếu class concrete không override:
// class Broken implements A, B { }
```

Class hoặc subinterface phải override và quyết định hành vi:

```java
class Combined implements A, B {
    @Override
    public String value() {
        return A.super.value() + "+" + B.super.value();
    }
}
```

Kết quả là `A+B`. `A.super.value()` và `B.super.value()` gọi rõ implementation của các direct superinterface tương ứng.

Nếu `A` chỉ là superinterface gián tiếp thông qua `Combined`, class triển khai không thể tùy tiện viết `A.super.value()`; phải gọi `Combined.super.value()` nếu `Combined` cung cấp default method phù hợp. Cú pháp `InterfaceName.super.method()` dành cho **direct superinterface**.

Một subinterface cũng có thể override để giải quyết xung đột. Khi có abstract/default declarations trùng signature, compiler áp dụng quy tắc inheritance/override của JLS; không giả định default bất kỳ luôn thắng abstract method.

### 3.4. Hai cách dùng super khác nhau

- `super.method()` gọi implementation thuộc class superclass.
- `InterfaceName.super.method()` gọi default method của direct superinterface.
- `this.method()` hoặc `object.method()` là lời gọi instance thông thường, cho phép dynamic dispatch.

Không thay `InterfaceName.super.method()` bằng `super.method()` khi mục tiêu là chọn implementation của interface.

## 4. Default method được lưu ở đâu trong class file?

Khi biên dịch interface có default method, compiler lưu method body trong file `InterfaceName.class`. Class triển khai chỉ khai báo interface trong metadata; **không có một bản copy method được compiler chèn vào class triển khai**.

Với ví dụ `Greeting` trong phần thực hành:
- `Greeting.class` khai báo `greet()` với body trong `Code` attribute.
- `Inherited.class` chỉ khai báo constructor, không có method `greet()`.
- Object của `Inherited` vẫn gọi được `greet()` vì JVM có thể tìm implementation thích hợp trong superinterface hierarchy.

Reflection cũng giúp kiểm tra:

```java
Method method = Greeting.class.getDeclaredMethod("greet");
System.out.println(method.isDefault());
```

`Method.isDefault()` trả `true` cho method default được khai báo trong interface. `Inherited.class.getDeclaredMethods()` không chứa `greet()` vì class không tự khai báo method đó.

### 4.1. Class-file version và method flags

Java 8 dùng class-file **major version 52**. Khi dùng JDK mới hơn với `javac --release 8`, compiler vẫn tạo class file version 52.

Ví dụ output `javap -v Greeting`:

```text
public default java.lang.String greet();
  descriptor: ()Ljava/lang/String;
  flags: (0x0001) ACC_PUBLIC
  Code:
    ...
```

Các chi tiết dễ nhầm:
- `javap` hiển thị chữ `default` để người đọc nhận diện method.
- Trong access flags của method, **không có flag riêng tên `ACC_DEFAULT`**.
- Method có `ACC_PUBLIC` và body trong `Code`; nó không có `ACC_ABSTRACT`.
- `descriptor: ()Ljava/lang/String;` nghĩa là method không có tham số và trả về `java.lang.String`.

### 4.2. Constant pool: Methodref và InterfaceMethodref

Class file có constant pool chứa symbolic reference đến class, interface, field và method. Hai entry quan trọng:

- `CONSTANT_Methodref`: tham chiếu method của class.
- `CONSTANT_InterfaceMethodref`: tham chiếu method của interface.

`javap` thường in ngắn thành `Methodref` và `InterfaceMethodref`. Entry cho biết owner, tên method và descriptor. Opcode dùng symbolic reference để resolve method, sau đó JVM chọn implementation theo quy tắc tương ứng.

## 5. Bốn opcode cần phân biệt

Default method không có một opcode duy nhất. Opcode phụ thuộc **dạng lời gọi và kiểu tĩnh của receiver**; implementation cuối cùng được JVM chọn theo quy tắc method resolution/selection.

| Opcode | Ý nghĩa chính | Ví dụ thường gặp |
| --- | --- | --- |
| `invokeinterface` | Gọi method qua interface reference | `Greeting g; g.greet()` |
| `invokevirtual` | Gọi instance method qua class method reference, dynamic dispatch theo object | `Child c; c.origin()` |
| `invokespecial` | Lời gọi cần xử lý đặc biệt | Constructor, `super.method()`, `InterfaceName.super.method()` |
| `invokestatic` | Gọi static method | `Texts.empty()` |

### 5.1. `invokeinterface`

Khi receiver có kiểu tĩnh là interface, javac thường tạo `invokeinterface` với symbolic reference đến interface method. JVM kiểm tra object có implement interface và chọn method phù hợp theo runtime class.

Nếu class override method, implementation trong class hierarchy được chọn. Nếu không, JVM có thể chọn một default method cụ thể nhất trong superinterface hierarchy. Nếu có nhiều default không cái nào cụ thể hơn, lời gọi binary có thể thất bại bằng `IncompatibleClassChangeError`.

### 5.2. `invokevirtual`

`invokevirtual` thường được dùng cho lời gọi qua class reference. Nhưng JVM cho phép symbolic reference của `invokevirtual` resolve tới interface method. Nếu class hierarchy không có implementation phù hợp, JVM có thể chọn một default method non-abstract từ superinterface hierarchy.

Trong chương trình thực hành, lời gọi `value.greet()` với `value` có kiểu tĩnh `Inherited` được javac biên dịch thành `invokevirtual Inherited.greet`, dù `Inherited` không khai báo method `greet()`. JVM vẫn tìm được default method `Greeting.greet()`.

**Không thể chỉ nhìn tên opcode rồi kết luận method body được khai báo trong class hay interface.** Cần đọc cả symbolic reference, class hierarchy và superinterface metadata.

### 5.3. `invokespecial`

`invokespecial` dùng cho constructor, method của superclass và lời gọi trực tiếp default method của direct superinterface:

```java
class Resolved implements Combined {
    String callInterfaceDefault() {
        return Combined.super.value();
    }

    String callClassSuper() {
        return super.toString();
    }
}
```

`Combined.super.value()` được javac biên dịch thành `invokespecial` với symbolic reference tới interface method `Combined.value()`. Bên trong `Combined.value()`, các lời gọi `A.super.value()` và `B.super.value()` cũng dùng `invokespecial`.

Đây là lời gọi chọn implementation cụ thể, khác với `this.value()` có dynamic dispatch.

### 5.4. `invokestatic`

Static method trong interface không phải default method và được gọi qua tên interface:

```java
interface Numbers {
    static int twice(int value) {
        return value * 2;
    }
}

int result = Numbers.twice(21);
```

Lời gọi static interface method dùng `invokestatic` với symbolic reference tới interface method. Static method không được kế thừa như instance default method.

## 6. Chương trình Java 8 hoàn chỉnh để quan sát dispatch

Chương trình sau kiểm tra:
- Default method được khai báo trong interface, không phải class triển khai.
- Lời gọi thông qua biến kiểu interface và biến kiểu class.
- Method từ superclass được ưu tiên hơn interface default.
- Hai default xung đột được giải quyết bằng override trong subinterface.
- `InterfaceName.super` và `super.method()` có bytecode khác nhau.

Lưu source thành `DefaultMethodBytecodeDemo.java`:


```java
import java.util.Arrays;

interface Greeting {
    default String greet() { return "hello"; }
}

interface A {
    default String value() { return "A"; }
}

interface B {
    default String value() { return "B"; }
}

interface Combined extends A, B {
    @Override
    default String value() {
        return A.super.value() + "+" + B.super.value();
    }
}

interface ClassDefault {
    default String origin() { return "interface"; }
}

class Parent {
    public String parentOnly() { return "parent"; }
    public String origin() { return "class"; }
}

class Inherited extends Parent implements Greeting, ClassDefault {
    // Kế thừa Greeting.greet() và Parent.origin().
}

class Resolved extends Parent implements Combined {
    String explicitInterfaceDefault() {
        return Combined.super.value();
    }

    String explicitClassSuper() {
        return super.parentOnly();
    }
}

public class DefaultMethodBytecodeDemo {
    static String throughInterface(Greeting value) {
        return value.greet();
    }

    static String throughClass(Inherited value) {
        return value.greet();
    }

    static String directClass(Resolved value) {
        return value.parentOnly();
    }

    public static void main(String[] args) throws Exception {
        Inherited first = new Inherited();
        Resolved second = new Resolved();

        boolean declaredInInterface =
                Greeting.class.getDeclaredMethod("greet").isDefault();
        boolean declaredInClass = Arrays.stream(
                Inherited.class.getDeclaredMethods())
                .anyMatch(method -> method.getName().equals("greet"));

        System.out.println("default declared in interface: "
                + declaredInInterface);
        System.out.println("default declared in class: " + declaredInClass);
        System.out.println("interface-typed call: "
                + throughInterface(first));
        System.out.println("class-typed call: " + throughClass(first));
        System.out.println("class method wins: " + first.origin());
        System.out.println("diamond resolution: " + second.value());
        System.out.println("explicit interface super: "
                + second.explicitInterfaceDefault());
        System.out.println("explicit class super: "
                + second.explicitClassSuper());
        System.out.println("class receiver call: " + directClass(second));
    }
}
```

## 7. Biên dịch, chạy và dùng javap

Trên JDK 9 trở lên, dùng `--release 8` để kiểm tra API/language target Java 8:

```bash
javac --release 8 DefaultMethodBytecodeDemo.java
java DefaultMethodBytecodeDemo
```

Nếu dùng chính JDK 8, chỉ cần `javac DefaultMethodBytecodeDemo.java` rồi `java DefaultMethodBytecodeDemo`; compiler Java 8 đã tạo class file version 52.

**Stdout thực tế đã kiểm thử:**

```text
default declared in interface: true
default declared in class: false
interface-typed call: hello
class-typed call: hello
class method wins: class
diamond resolution: A+B
explicit interface super: A+B
explicit class super: parent
class receiver call: parent
```

`javap` là công cụ JDK để disassemble class file:

| Lệnh | Tác dụng |
| --- | --- |
| `javap Greeting` | Liệt kê interface và method cơ bản |
| `javap -c Greeting` | In các JVM instruction trong `Code` attribute |
| `javap -p Greeting` | Hiển thị cả member không public |
| `javap -v Greeting` | In chi tiết version, constant pool, flags, descriptors và attributes |
| `javap -c -p -v Greeting` | Kết hợp disassembly và thông tin class file đầy đủ |

Chạy trong cùng thư mục có các class files:

```bash
javap -c -p -v DefaultMethodBytecodeDemo
javap -c -p -v Greeting
javap -c -p -v Combined
javap -c -p -v Resolved
javap -c -p -v Inherited
```

### 7.1. Gọi qua kiểu interface: `invokeinterface`

Trong method `throughInterface(Greeting)`, javac tạo bytecode tương đương:

```text
static java.lang.String throughInterface(Greeting);
  0: aload_0
  1: invokeinterface #7, 1
       // InterfaceMethod Greeting.greet:()Ljava/lang/String;
  6: areturn
```

`aload_0` đưa receiver từ local variable 0 lên operand stack. `invokeinterface` tham chiếu `Greeting.greet` qua constant pool entry kiểu `InterfaceMethodref`. JVM chọn implementation phù hợp cho object thực tế; `areturn` trả String về caller.

### 7.2. Gọi qua kiểu class dù method nằm trong interface: `invokevirtual`

Method `throughClass(Inherited)` trong cùng lần biên dịch cho kết quả:

```text
static java.lang.String throughClass(Inherited);
  0: aload_0
  1: invokevirtual #13
       // Method Inherited.greet:()Ljava/lang/String;
  4: areturn
```

Constant pool ghi symbolic reference tới `Inherited.greet` dưới dạng `Methodref`, dù `Inherited.class` không khai báo method `greet()`. JVM resolve method reference và có thể tìm default method trong superinterface hierarchy.

Đây là chi tiết quan trọng: **không thể nói gọi default method thì luôn dùng invokeinterface**. Kiểu tĩnh của receiver và symbolic reference do compiler tạo ra quyết định opcode; JVM vẫn có thể chọn implementation nằm trong interface.

### 7.3. Gọi rõ default của interface: `invokespecial`

Trong class `Resolved`:

```java
String explicitInterfaceDefault() {
    return Combined.super.value();
}
```

`javap -c -p -v Resolved` cho thấy:

```text
java.lang.String explicitInterfaceDefault();
  0: aload_0
  1: invokespecial #7
       // InterfaceMethod Combined.value:()Ljava/lang/String;
  4: areturn
```

`Combined.super.value()` được biên dịch thành `invokespecial` với symbolic reference tới **interface method** `Combined.value()`. Trong body `Combined.value()`, hai lời gọi `A.super.value()` và `B.super.value()` cũng được biên dịch thành `invokespecial` tới `A.value()` và `B.value()`.

### 7.4. Gọi superclass: `invokespecial` với Methodref

```java
String explicitClassSuper() {
    return super.parentOnly();
}
```

Bytecode:

```text
java.lang.String explicitClassSuper();
  0: aload_0
  1: invokespecial #13
       // Method Parent.parentOnly:()Ljava/lang/String;
  4: areturn
```

Cùng mnemonic `invokespecial` nhưng symbolic reference ở đây là method của class `Parent`, kiểu `Methodref`. Vì vậy phải đọc cả opcode và owner/reference type, không chỉ đọc mnemonic.

Ngược lại, `value.parentOnly()` với receiver kiểu `Resolved` là lời gọi thông thường và dùng `invokevirtual`. Nó cho phép dispatch bình thường theo object, còn `super.parentOnly()` yêu cầu gọi implementation của superclass.

### 7.5. Những dòng khác cần kiểm tra

`javap -v Greeting` cho thấy:
- `major version: 52`.
- `public default java.lang.String greet()`.
- `flags: ACC_PUBLIC` và có `Code` attribute.
- Không có flag `ACC_DEFAULT` riêng.

`javap -p Inherited` chỉ liệt kê constructor; không có method `greet()`. `javap -c -p -v Combined` cho thấy `Combined.value()` gọi `A.value()` và `B.value()` bằng `invokespecial` với các `InterfaceMethodref` tương ứng.

Các số offset và constant-pool index như `#7`, `#13` phụ thuộc class file/compiler. Hãy tập trung vào opcode, tên owner, method descriptor và loại symbolic reference; không hard-code các index đó trong tài liệu phân tích.

## 8. JVM chọn default method như thế nào?

Với lời gọi `invokeinterface` hoặc `invokevirtual`, có thể tóm tắt quy tắc lựa chọn cho object như sau:

1. Nếu runtime class khai báo method override phù hợp, dùng method đó.
2. Nếu không, tìm từ direct superclass lên các superclass tiếp theo; method instance phù hợp trong class hierarchy được ưu tiên.
3. Nếu class hierarchy không có implementation phù hợp, xét các **maximally-specific superinterface methods**.
4. Nếu có đúng một method non-abstract phù hợp, JVM chọn method đó.
5. Nếu có nhiều default không cái nào cụ thể hơn, lời gọi có thể thất bại bằng `IncompatibleClassChangeError`. Nếu không có implementation concrete phù hợp, có thể gặp `AbstractMethodError`.

Đây là phần runtime. Trình biên dịch Java cũng phát hiện xung đột ở source level; class concrete không thể đơn giản kế thừa hai default không liên quan cùng signature mà không override.

`invokespecial` có quy tắc riêng vì nó gọi trực tiếp method của current class, superclass hoặc direct superinterface. Trong Java source, `InterfaceName.super.method()` chỉ được dùng với direct superinterface và default method hợp lệ.

### 8.1. Class method wins không có nghĩa default bị xóa

Trong demo, `Parent.origin()` và `ClassDefault.origin()` có cùng signature. `Inherited.origin()` trả `"class"` vì method của superclass được ưu tiên. Default method vẫn được khai báo trong interface; chỉ là nó không được chọn cho lời gọi này.

### 8.2. Nhiều đường kế thừa không đồng nghĩa nhiều default

Nếu một interface được kế thừa qua nhiều nhánh nhưng cuối cùng chỉ có một declaration phù hợp, compiler/JVM không coi các đường đi là nhiều implementation khác nhau. Xung đột thực sự xuất hiện khi có nhiều declaration default non-abstract độc lập cùng signature và không có quan hệ specificity giải quyết.

## 9. Binary compatibility khi thêm default method

Default method cho phép interface tiến hóa mà không bắt mọi class triển khai cũ phải viết method mới. Theo JLS, thêm một default method hoặc chuyển abstract method thành default method **không phá binary compatibility nói chung** đối với binary đã biên dịch trước đó.

Tuy nhiên, một binary cũ có thể implement hai interface độc lập; sau khi thư viện cập nhật, cả hai interface có thể cùng khai báo default method trùng signature. Nếu binary cũ gọi method mà không có default nào cụ thể hơn, JVM có thể ném `IncompatibleClassChangeError` tại lời gọi.

Khi thiết kế interface công khai:
- Kiểm tra signature mới có đụng method trong superclass hoặc các interface phổ biến không.
- Chọn implementation mặc định phù hợp với contract của các implementation cũ.
- Tránh default method có side effect hoặc giả định state mà class triển khai không có.
- Recompile/test các implementation quan trọng để phát hiện conflict ở source level.
- Khi có conflict, yêu cầu class/subinterface override rõ ràng thay vì dựa vào thứ tự interface.

## 10. Lỗi thường gặp khi đọc default method và bytecode

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Nghĩ default method được copy vào mọi class triển khai | Body nằm trong interface class file; class có thể không khai báo method đó |
| Nghĩ default method là static | Nó là instance method; static interface method là loại riêng |
| Nghĩ default method luôn dùng `invokeinterface` | Receiver class-typed có thể dùng `invokevirtual` |
| Nghĩ `invokevirtual` không thể chọn default method | JVM có thể resolve reference tới interface method và chọn default phù hợp |
| Nghĩ `Interface.super.m()` giống `super.m()` | Một cái gọi direct superinterface, một cái gọi class superclass |
| Gọi `A.super.m()` khi A chỉ là superinterface gián tiếp | Cú pháp này chỉ dùng với direct superinterface |
| Nghĩ class phải override mọi default method | Class có thể kế thừa default nếu không có quy tắc ưu tiên/xung đột khác |
| Nghĩ hai default không liên quan được chọn theo thứ tự implements | Cần override để giải quyết rõ ràng |
| Nghĩ có flag `ACC_DEFAULT` trong class file | Không có flag đó; method public có Code và không abstract |
| Chỉ đọc opcode, bỏ qua constant pool owner | Cần đọc cả `Methodref`/`InterfaceMethodref` và tên owner |
| Nghĩ `javap` hiển thị machine code CPU | Nó disassemble JVM bytecode trong class file, không phải native code JIT |
| Nghĩ bytecode của mọi compiler giống từng offset | Compiler có thể tạo sequence khác nhau nhưng vẫn giữ ngữ nghĩa Java/JVM |
| Dùng private interface method trong Java 8 | Private interface method chỉ có từ Java 9 |
| Nghĩ thêm default method luôn an toàn tuyệt đối cho mọi binary | Một số binary cũ có thể gặp `IncompatibleClassChangeError` khi invoke hai default độc lập |

## 11. Bài tập tự kiểm tra

**1.** Default method được khai báo ở đâu trong class file?  
— Trong class file của interface, có method body/`Code` attribute.

**2.** Class triển khai không override default method có cần compiler copy method vào class không?  
— Không. Class có thể kế thừa implementation thông qua interface hierarchy.

**3.** Biến có kiểu tĩnh `Greeting` gọi `greet()` thường dùng opcode nào?  
— `invokeinterface`.

**4.** Biến có kiểu tĩnh `Inherited` gọi `greet()` trong ví dụ dùng opcode nào?  
— `invokevirtual` với symbolic reference `Inherited.greet`; JVM vẫn có thể chọn default method của `Greeting`.

**5.** `Combined.super.value()` trong class triển khai dùng opcode nào?  
— `invokespecial` với symbolic reference tới interface method `Combined.value`.

**6.** `super.parentOnly()` dùng opcode nào?  
— `invokespecial` với symbolic reference tới class method `Parent.parentOnly`.

**7.** Nếu superclass có method instance trùng signature với interface default thì implementation nào được ưu tiên?  
— Method trong class hierarchy; nếu superclass declaration là abstract thì concrete subclass vẫn phải thực hiện nghĩa vụ override.

**8.** Hai superinterface độc lập có default method trùng signature. Class concrete không override có biên dịch được không?  
— Không. Cần override để giải quyết xung đột.

**9.** Có flag `ACC_DEFAULT` trong method access flags không?  
— Không. `javap` nhận diện từ ngữ cảnh interface và method flags/body.

**10.** `javap -c -p -v` hiển thị gì?  
— Disassembled bytecode, member non-public, constant pool, flags, descriptors, class version và attributes.

**11.** Class-file major version 52 biểu thị phiên bản nào?  
— Java SE 8.

**12.** Default method có làm interface mất khả năng là functional interface không?  
— Không tự động. Functional interface vẫn có thể có default/static methods miễn chỉ còn một abstract method logic.

**13.** Có thể viết `A.super.m()` nếu class chỉ implements `Combined` và `Combined extends A` không?  
— Không; `A` là superinterface gián tiếp. Gọi `Combined.super.m()` nếu Combined cung cấp default phù hợp.

**14.** Vì sao thêm default method có thể gây lỗi trên binary cũ?  
— Binary cũ có thể implement hai interface độc lập mà sau này đều khai báo default method cùng signature; lúc invoke, JVM không tìm được một default duy nhất và có thể ném `IncompatibleClassChangeError`.

## 12. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — JLS Chapter 9: Interfaces](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html): khai báo default method, kế thừa, overriding và xung đột signature.
- [Oracle Java SE 26 — JLS Chapter 13: Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se26/html/jls-13.html): `13.5.7 về thay đổi method declarations trong interface và thêm default method.
- [Oracle Java SE 26 — JVMS Chapter 5](https://download.java.net/java/early_access/jdk26/docs/specs/jvms/jvms-5.html): method resolution, interface method resolution và `5.4.6 method selection.
- [Oracle Java SE 26 — JVMS Chapter 6](https://download.java.net/java/early_access/jdk26/docs/specs/jvms/jvms-6.html): instruction semantics của `invokeinterface`, `invokevirtual`, `invokespecial` và `invokestatic`.
- [Oracle JDK 27 — javap tool](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html): disassemble class file và các option `-c`, `-p`, `-v`.
- [Oracle Java 8 Compatibility Guide](https://www.oracle.com/java/technologies/javase/8-compatibility-guide.html): class-file major version 52 của Java 8.

**Tóm tắt:** Default method là instance method có body nằm trong interface class file. Class triển khai không cần có bản copy method. `invokeinterface` và `invokevirtual` đều có thể chọn default implementation theo runtime type; `invokespecial` được dùng khi gọi rõ implementation của superclass hoặc direct superinterface. Muốn hiểu lời gọi thực sự đi đâu, hãy đọc opcode, constant-pool reference và quy tắc method selection bằng `javap` cùng JVMS.
