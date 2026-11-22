# 11.1 Mục đích của `invokedynamic` và khác biệt với `invokevirtual` hoặc `invokeinterface`

Trong bytecode JVM, `invokevirtual` và `invokeinterface` biểu diễn những lời gọi theo **hợp đồng method của class/interface**: bytecode tham chiếu đến một method cụ thể trong constant pool, và ở thời điểm thực thi JVM chọn implementation tương ứng với receiver theo quy tắc dispatch. `invokedynamic` giải quyết bài toán khác: **liên kết một call site với một hành vi gọi được xác định thông qua bootstrap method**, thay vì buộc bytecode ngay từ đầu tham chiếu đến method của một class/interface theo cơ chế dispatch truyền thống.

`invokedynamic` được đưa vào JVM từ Java 7 (JSR 292). Nó cho phép một compiler hoặc runtime xác định cách một call site hoạt động **khi liên kết** (linking), thông qua `MethodHandle` và `CallSite`. Nhờ đó, JVM hỗ trợ tốt hơn các kiểu lời gọi sinh động, ngôn ngữ chạy trên JVM, lambda và các chiến lược tối ưu hóa của Java compiler, trong khi vẫn giữ quy tắc chặt chẽ về **chữ ký tham số và kết quả** của call site.

Bài học trả lời trực tiếp: `invokedynamic` tồn tại để làm gì, điểm nào khác `invokevirtual`/`invokeinterface`, điều gì xảy ra ở bước bootstrap, và làm cách nào quan sát chúng trong Java 17+.

**Sau bài này, bạn có thể:**

- Giải thích vì sao cả `invokevirtual` và `invokeinterface` đều hỗ trợ polymorphism nhưng vẫn khác với `invokedynamic`.
- Đọc một mục `InvokeDynamic` trong constant pool và một mục `BootstrapMethods` qua `javap -v`.
- Phân biệt **linkage** với **execution**: bootstrap tạo/đưa ra `CallSite`; các lần gọi sau dùng target của call site.
- Hiểu vai trò của `MethodHandles.Lookup`, tên call site, `MethodType`, bootstrap arguments, `CallSite` và `MethodHandle`.
- Nhận biết nơi Java compiler có thể phát ra `invokedynamic`: lambda, method reference và string concatenation.
- Hiểu vì sao `ConstantCallSite` khác `MutableCallSite` hoặc `VolatileCallSite`, cùng giới hạn của việc thay target.
- Chẩn đoán các lỗi linkage như `BootstrapMethodError` mà không nhầm với lỗi do target method ném ra.

## 1. Ba bytecode instructions giải quyết ba cơ chế lời gọi

Một câu source Java như `receiver.doWork()` không tự nói rõ bytecode nào được phát ra: nó còn phụ thuộc vào kiểu tĩnh của receiver, method kind và compiler. Ba instructions trong phạm vi bài này là:

| Instruction | Tham chiếu tại bytecode/constant pool | Điều JVM làm khi gọi | Trường hợp tiêu biểu |
| --- | --- | --- | --- |
| `invokevirtual` | Symbolic method reference gắn với class và tên/chữ ký method | Dispatch đến implementation thích hợp theo class thực tế của receiver, với các quy tắc method selection | Instance method của class; override giữa superclass/subclass |
| `invokeinterface` | Symbolic interface-method reference gắn với interface và tên/chữ ký method | Dispatch thông qua hợp đồng interface và class thực tế của receiver, có xét các quy tắc implementation/default method | Gọi method trên biến có kiểu interface |
| `invokedynamic` | **Call-site specifier**: tên/chữ ký dynamic invocation và thông tin bootstrap | Resolve bootstrap để có `CallSite`; sau khi liên kết, invoke target `MethodHandle` của call site | Lambda factory, string concatenation, một số ngôn ngữ động và code sinh bytecode |

Hai instructions đầu đều có thể gọi hành vi khác nhau ở runtime nhờ **overriding hoặc implementation của receiver**. Vì vậy sẽ **sai** nếu giải thích rằng `invokevirtual`/`invokeinterface` là “tĩnh” còn `invokedynamic` mới là “động”.

**Sự khác nhau quan trọng:** với `invokevirtual`/`invokeinterface`, bản thân instruction biểu diễn một **method reference theo mô hình class/interface**. Với `invokedynamic`, instruction biểu diễn một **call site được liên kết bởi bootstrap method**, cho phép bootstrap quyết định target là gì, có thể dựng adapter, tạo factory, cache hoặc chọn một chiến lược runtime phù hợp.

### 1.1. Ví dụ trực giác về `invokevirtual`

```java
class Animal {
    String sound() { return "generic"; }
}

class Dog extends Animal {
    @Override
    String sound() { return "woof"; }
}

// Đoạn minh họa:
Animal animal = new Dog();
String value = animal.sound(); // "woof"
```

Mặc dù biến `animal` có kiểu tĩnh `Animal`, receiver thực tế là `Dog`, nên lời gọi virtual đi tới override `Dog.sound()`. JVM không cần một bootstrap method tùy biến cho điều đó: polymorphic dispatch đã được `invokevirtual` thiết kế sẵn.

### 1.2. Ví dụ trực giác về `invokeinterface`

```java
interface Formatter {
    String format(String text);
}

class PlainFormatter implements Formatter {
    @Override
    public String format(String text) {
        return "[" + text + "]";
    }
}

// Đoạn minh họa:
Formatter formatter = new PlainFormatter();
String value = formatter.format("A"); // "[A]"
```

Gọi `formatter.format("A")` trên kiểu interface thông thường tạo `invokeinterface`. Việc implementation cụ thể có thể thay đổi theo object là **polymorphism của interface**, không phải `invokedynamic`.

Cả hai đoạn trên chỉ minh họa cấu trúc class/interface; một chương trình hoàn chỉnh, biên dịch được và kiểm chứng bytecode nằm ở mục 4.

## 2. Vì sao cần `invokedynamic` nếu JVM đã có dynamic dispatch?

`invokevirtual` và `invokeinterface` làm tốt khi lời gọi có thể diễn đạt thành “gọi method mang tên X/chữ ký Y qua class/interface Z”. Nhưng các ngôn ngữ hoặc runtime có thể cần:

1. **Chọn hành vi tại call site theo quy tắc ngôn ngữ**, không nhất thiết theo một tên method của một class/interface Java đã biết.
2. **Dựng target từ một tập thao tác**: method handle tới method thực, method adapters, kiểm tra kiểu, chuyển đổi argument, ghép thao tác hoặc strategy tối ưu.
3. **Đưa thông tin bổ sung cho bootstrap** từ compiler, ví dụ recipe cho string concatenation hoặc method handle tới lambda body.
4. **Liên kết một lần và tái sử dụng** call site đã liên kết, thay vì yêu cầu compiler viết tay một chuỗi dispatch bằng reflection hoặc một wrapper class cố định cho mọi biến thể.
5. Với mô hình thích hợp, **thay target của một call site có kiểu ổn định** khi chiến lược dispatch thay đổi. Điều này đòi `MutableCallSite`/`VolatileCallSite` hoặc cơ chế runtime tương ứng, không có nghĩa mọi `invokedynamic` đều tự thay target.

Hai ví dụ thực tế của **Java**:

- **Lambda và method reference:** compiler có thể phát `invokedynamic` để liên kết một *factory* tạo đối tượng functional interface, thường dùng `LambdaMetafactory`. Sau khi tạo object, lời gọi vào phương thức của functional interface vẫn có thể là **`invokeinterface`**.
- **String concatenation:** với target bytecode phiên bản Java hiện đại, compiler có thể phát `invokedynamic` và dùng `StringConcatFactory` để tổ chức phép nối chuỗi, thay vì luôn phát một chuỗi `new StringBuilder` + `append`.

**Không nên nói** rằng mọi lambda/method reference hoặc mọi phép nối chuỗi bắt buộc sẽ luôn có một `invokedynamic` trong mọi compiler/JDK/optimization mode. Đây là một chiến lược bytecode do compiler lựa chọn. Kiểm tra bằng `javap` trên file `.class` thật mới là bằng chứng cho bản build cụ thể.

## 3. Cấu trúc một dynamic call site

Ở mức JVM, một `invokedynamic` instruction tham chiếu đến một mục `CONSTANT_InvokeDynamic_info` trong constant pool. Mục đó liên hệ với:

- **`bootstrap_method_attr_index`**: vị trí trong thuộc tính class-file `BootstrapMethods` chứa handle tới bootstrap method và các bootstrap arguments tĩnh.
- **`name_and_type_index`**: tên và *method descriptor* của dynamic call site, ví dụ `format:()LMyFormatter;` hoặc `makeConcatWithConstants:(I)Ljava/lang/String;`.

Không nên đọc tên `format` hoặc `makeConcatWithConstants` trong dòng `invokedynamic` giống như “đây chính là method instance mà JVM sẽ gọi”. Đó là **tên dùng khi liên kết call site**; bootstrap có quyền diễn giải tên theo hợp đồng riêng. `CONSTANT_InvokeDynamic_info` không phải `CONSTANT_Methodref` trỏ trực tiếp đến một class owner và method implementation.

Mô hình:

```text
              Class file
        +---------------------+
        | invokedynamic #N    |
        +----------+----------+
                   |
                   v
        CONSTANT_InvokeDynamic
        +---------------------+
        | bootstrap index     |----> BootstrapMethods
        | NameAndType         |       - bootstrap MethodHandle
        +----------+----------+       - static bootstrap arguments
                   |
                   v
            Call-site type
           (arguments)result
                   |
          JVM resolve/link site
                   |
                   v
          invoke bootstrap method
           (Lookup, name, MethodType,
            optional static arguments)
                   |
                   v
                CallSite
                   |
                   v
             target MethodHandle
                   |
                   v
            execute target with
            dynamic arguments
```

Sơ đồ chỉ biểu diễn **trình tự logic**, không hàm ý class file lưu sẵn một object `CallSite`. Object call site được tạo/nhận trong quá trình linking tại runtime.

### 3.1. Bootstrap method thường nhận gì?

Một dạng phổ biến:

```java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType invokedType) throws Throwable {
    // Tìm/chế biến MethodHandle target, kiểm tra contract và trả CallSite.
}
```

Đây là **mã khung minh họa**, không có body hoàn chỉnh. Ba đối số cốt lõi:

1. `caller` (`MethodHandles.Lookup`): ngữ cảnh lookup của class chứa dynamic instruction, kèm các quyền tương ứng. Không phải “được truy cập private của mọi class”.
2. `name` (`String`): tên call site do compiler/bytecode ghi. Bootstrap tự quyết định ý nghĩa.
3. `invokedType` (`MethodType`): chữ ký bắt buộc của dynamic instruction: **kiểu của mọi argument và return type**.

Ngoài ba phần cốt lõi, compiler có thể cấu hình các **static bootstrap arguments**. JVM đưa chúng vào bootstrap theo thứ tự đã ghi. Ví dụ lambda metafactory thường nhận kiểu SAM, method handle của implementation, và instantiated method type; string concat factory có thể nhận recipe và constants.

**Phân biệt static bootstrap arguments với dynamic arguments:**

- Static bootstrap args là metadata/constant cung cấp khi **link call site**.
- Dynamic arguments là giá trị nằm trên operand stack truyền vào **mỗi lần thực thi** instruction đã link.

Nếu một string concatenation site nhận `int` làm dynamic argument, `int` đó có thể thay đổi ở mỗi lần gọi; recipe bootstrap không vì thế được xử lý lại cho mỗi giá trị.

### 3.2. Bootstrap được chạy khi nào?

JVM resolve call-site specifier khi cần liên kết dynamic instruction. Thời điểm chính xác có thể liên quan đến cách runtime quyết định resolve, nhưng điều quan trọng là: **sau khi liên kết thành công, instruction gắn với object `CallSite` đã chọn**. Các lần thực thi không tự động gọi lại bootstrap chỉ vì giá trị argument thay đổi.

Một sắc thái từ JVMS: nếu nhiều thread đồng thời resolve cùng một site, bootstrap **có thể được gọi ở nhiều thread**; JVM chọn một `CallSite` để cài đặt, các kết quả khác bị bỏ qua. Vì vậy, “bootstrap chắc chắn được gọi đúng một lần trên toàn bộ chương trình” là khẳng định quá mạnh. Bootstrap có side effects cần tự đảm bảo thread safety.

Call-site binding và target binding cũng khác nhau:

- Một **dynamic instruction** đã link gắn với object `CallSite` được chọn.
- `CallSite` có `target` là `MethodHandle`. Với loại call site cho phép thay đổi target, cùng một object call site có thể được **relinked** đến target mới mà vẫn giữ **MethodType**.
- `ConstantCallSite` không cho đổi target sau khi tạo. `MutableCallSite` hoặc `VolatileCallSite` có thể đổi target theo semantics tương ứng.

## 4. Chương trình Java 17+ hoàn chỉnh: thấy cả ba instructions

Tạo file **`InvokeDynamicContrastDemo.java`**:

```java
import java.util.Locale;

public class InvokeDynamicContrastDemo {
    static class Animal {
        String sound() { return "generic"; }
    }

    static class Dog extends Animal {
        @Override
        String sound() { return "woof"; }
    }

    interface Formatter {
        String format(String text);
    }

    static class PlainFormatter implements Formatter {
        @Override
        public String format(String text) { return "[" + text + "]"; }
    }

    static String display(Formatter formatter, String value) {
        return formatter.format(value);
    }

    static String message(int number) {
        return "id=" + number;
    }

    public static void main(String[] args) {
        Animal animal = new Dog();
        System.out.println("virtual: " + animal.sound());

        Formatter formatter = new PlainFormatter();
        System.out.println("interface: " + display(formatter, "A"));

        Formatter lambda = value -> value.toUpperCase(Locale.ROOT);
        System.out.println("lambda: " + display(lambda, "hello"));

        System.out.println("concat: " + message(12));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 InvokeDynamicContrastDemo.java
java InvokeDynamicContrastDemo
```

**Stdout đã kiểm tra bằng chương trình thực:**

```text
virtual: woof
interface: [A]
lambda: HELLO
concat: id=12
```

Đọc source:

- `Animal animal = new Dog()` rồi gọi `animal.sound()`: receiver có kiểu runtime `Dog`, JVM chọn override `Dog.sound()`, in `woof`.
- `display` nhận một biến kiểu `Formatter` và gọi `formatter.format(value)`: thao tác polymorphic qua interface.
- `Formatter lambda = value -> ...` là một expression mà compiler có thể biểu diễn bằng dynamic factory call site; factory trả object `Formatter`, sau đó `display` **vẫn gọi** `Formatter.format` qua interface.
- `message(int)` nối chuỗi với `number` là một giá trị runtime, đủ để quan sát string-concat call site trong class file được build.

Cùng lúc đó, `System.out.println(...)` là một lời gọi instance method khác, nên bytecode có thể chứa **nhiều** `invokevirtual`; không nên suy ra mỗi dòng source chỉ tương ứng đúng một invoke instruction.

### 4.1. Xem bytecode bằng `javap`

Sau khi biên dịch, chạy:

```bash
javap -c -p InvokeDynamicContrastDemo
javap -v InvokeDynamicContrastDemo
```

Trong output `javap -c -p`, bạn sẽ thấy các dòng **có bản chất như** (số index/offset được lược bỏ vì phụ thuộc compiler và bản build):

```text
invokevirtual      // Method InvokeDynamicContrastDemo$Animal.sound:()Ljava/lang/String;
invokeinterface    // InterfaceMethod InvokeDynamicContrastDemo$Formatter.format:(Ljava/lang/String;)Ljava/lang/String;
invokedynamic      // InvokeDynamic ...:format:()LInvokeDynamicContrastDemo$Formatter;
invokedynamic      // InvokeDynamic ...:makeConcatWithConstants:(I)Ljava/lang/String;
```

Lệnh `javap -v` sẽ cho thấy mục `BootstrapMethods` với các method handle tham chiếu tới những factory, chẳng hạn:

```text
java/lang/invoke/LambdaMetafactory.metafactory
java/lang/invoke/StringConcatFactory.makeConcatWithConstants
```

Trong bài thực nghiệm, `javac --release 17` đã tạo đúng những loại instruction này và `javap` đã xác nhận `invokevirtual`, `invokeinterface`, `invokedynamic` cùng hai bootstrap factories. **Không** coi offset/constant-pool index hay thứ tự các mục bootstrap là API ổn định: chúng có thể khác giữa các compiler/JDK, flags và source code sau chỉnh sửa.

### 4.2. Tại sao interface call vẫn tồn tại khi dùng lambda?

Dòng lambda có hai ý nghĩa khác nhau:

```java
Formatter lambda = value -> value.toUpperCase(Locale.ROOT);
String result = lambda.format("hello");
```

1. **Tạo/thu được object functional interface:** có thể dùng `invokedynamic` với `LambdaMetafactory` làm bootstrap. Call site có thể làm vai trò **factory** trả về một instance tương thích `Formatter`. Đối với lambda **không capture** như ví dụ này, factory không cần argument capture.
2. **Gọi SAM method trên object:** `lambda.format(...)` là một interface invocation thông thường. Bytecode có thể là `invokeinterface`.

Không phải `invokedynamic` “thay `invokeinterface`”. Chúng có thể xuất hiện trong **cùng một luồng thực thi** cho hai công việc khác nhau. Một lambda có capture (ví dụ ghi nhớ một biến local effectively final) có thể tạo factory call site **có dynamic arguments** đại diện cho các giá trị được capture.

### 4.3. Nhìn vào `StringConcatFactory`

Với:

```java
static String message(int number) {
    return "id=" + number;
}
```

Compiler hiện đại có thể chọn call site trả `String` và nhận `int`: `(I)Ljava/lang/String;` (dạng method descriptor JVM). Bootstrap `StringConcatFactory.makeConcatWithConstants` có thể nhận **recipe** chứa literal `"id="` cùng placeholder cho argument động.

Để tránh nhầm:

- `makeConcatWithConstants` là **bootstrap method** trong metadata, không có nghĩa mỗi lần gọi `message(n)` đều chạy lại bootstrap.
- `number` là **dynamic argument** tại lần thực thi.
- Đầu ra là `String`, được tạo bằng target method handle đã liên kết phù hợp.
- Compiler có thể constant-fold các phép nối toàn literal; không phải mọi phép `"a" + "b"` đều tạo `invokedynamic`.

## 5. `invokevirtual` và `invokeinterface`: polymorphism có quy tắc sẵn

Khi gọi một instance method thông thường, JVM thực hiện hai nhóm việc:

- **Resolution:** symbolic reference xác định method được nhắc tới, class/interface liên quan và các quy tắc truy cập/lookup.
- **Method selection/dispatch:** dựa trên receiver và quy tắc overriding/implementation để chọn method body được chạy.

Đây là **dispatch cố định bởi semantics của JVM**. JVM không hỏi application một bootstrap callback để lựa chọn tùy ý. Nếu `Animal a = new Dog()`, `invokevirtual Animal.sound` có thể chọn `Dog.sound` vì override. Nếu `Formatter f` chứa instance của class triển khai cụ thể, `invokeinterface Formatter.format` tìm implementation hợp lệ theo quy tắc interface invocation.

### 5.1. Sự khác biệt không phải early binding so với late binding

Một so sánh sai thường gặp:

```text
invokevirtual   = static
invokeinterface = static
invokedynamic   = dynamic
```

Cách so sánh này khiến người đọc tưởng hai instruction đầu không có runtime polymorphism. Thực tế:

- Cả `invokevirtual` và `invokeinterface` **đều có thể chọn implementation khác nhau ở runtime** khi receiver khác nhau.
- `invokedynamic` thêm **khả năng lập trình cách liên kết target của call site**. Bootstrap có thể tạo target ổn định hoặc target có thể đổi, tùy `CallSite`.
- Tùy target, invokedynamic cũng có thể gọi một method handle đại diện cho **virtual invocation**. Nó không loại bỏ các dispatch rules bên dưới một target đã chọn.

**Tóm lại:** polymorphism trên receiver và bootstrap-defined call-site linkage là hai khái niệm khác nhau, không phải hai mức “động/tĩnh” đơn giản.

### 5.2. `invokeinterface` không chỉ có một method body cố định

Interface có thể có nhiều implementors, và từ Java 8 có default methods. `invokeinterface` thực hiện method selection theo quy tắc JVM, có thể chọn implementation trong class hoặc default method thích hợp. Các trường hợp không có implementation hợp lệ hoặc xuất hiện xung đột sẽ dẫn tới lỗi resolution/invocation phù hợp. Không nên trình bày `invokeinterface` như một phép gọi hàm “giả lập” hoàn toàn ngoài JVM.

### 5.3. Các invoke instructions khác có vai trò riêng

Để nhìn đúng bức tranh:

- `invokestatic`: lời gọi static method; không có receiver dispatch như virtual invocation.
- `invokespecial`: dùng cho instance initialization (`<init>`), private method invocation và các trường hợp gọi đặc biệt như `super`.
- `invokevirtual`, `invokeinterface`: các dạng instance invocation mà bài này so sánh.
- `invokedynamic`: liên kết theo call-site specifier + bootstrap.

Tất cả là JVM instructions, không phải API Java có thể gọi trực tiếp bằng cách viết `invokedynamic(...)` trong source Java chuẩn.

## 6. Linking và execution: bootstrap không phải target method

Quá trình liên kết và gọi có thể minh họa bằng pseudocode:

```text
Khi call site cần được resolve:
    bootstrap = resolveBootstrapMethod(...)
    type = resolveCallSiteMethodType(...)
    staticArgs = resolveBootstrapArguments(...)
    callSite = bootstrap(callerLookup, callSiteName, type, staticArgs...)
    verify(callSite != null)
    verify(callSite.type() == type)
    bindDynamicInstructionTo(callSite)

Mỗi lần thực thi instruction đã link:
    arguments = valuesFromOperandStack()
    target = callSite.getTarget()
    result = invokeTargetWithExactDescriptor(target, arguments)
```

**Đây là pseudocode**, không phải mã Java/JVM triển khai. JVM không bắt buộc thực hiện từng bước dưới dạng các hàm có tên như vậy; đặc tả chỉ định hành vi quan sát được.

Các điều kiện quan trọng:

1. Bootstrap method phải cung cấp một `CallSite` hợp lệ.
2. `CallSite.type()` phải **khớp method descriptor** của dynamic instruction về cả parameter và return types.
3. Sau khi link thành công, target được gọi như qua `MethodHandle.invokeExact` theo descriptor của dynamic site. Điều này là **semantics của instruction**, không có nghĩa Java source phải viết `invokeExact` cho mỗi `invokedynamic`.
4. Với `ConstantCallSite`, target không đổi; với `MutableCallSite`/`VolatileCallSite`, target được cập nhật theo quy tắc tương ứng nhưng **không được đổi type**.
5. Nếu target method ném `RuntimeException` hoặc `Error` khi thực thi sau linkage, đó là **lỗi của target**, không tự động biến thành lỗi bootstrap.

### 6.1. `CallSite` và `MethodHandle` khác nhau

`MethodHandle` mô tả một thao tác có thể gọi và chữ ký `MethodType`. `CallSite` chứa một **target MethodHandle** có `MethodType` ổn định, và có thể cung cấp `dynamicInvoker()` để gọi target hiện tại.

Hình dung:

```text
invokedynamic instruction  -->  CallSite object
                                    |
                                    +-- current target: MethodHandle
                                    |             |
                                    |             +-- target code / adapters
                                    |
                                    +-- type: (arguments)result
```

Không nên coi một object `MethodHandle` được tạo thủ công bằng `findStatic` là một `invokedynamic` instruction. Nó chỉ là target tiềm năng. Mối liên hệ với bytecode instruction phát sinh khi JVM resolve một `CONSTANT_InvokeDynamic_info` thật.

## 7. Ví dụ đầy đủ: dựng bootstrap/`ConstantCallSite` bằng Java API

Trong Java source thông thường, ta có thể viết một **bootstrap method** và tự gọi nó để quan sát cơ chế `CallSite`. Ví dụ này **mô phỏng phần cấu thành liên kết**, **không phát sinh một lệnh `invokedynamic` tùy biến**. Để tạo `invokedynamic` với custom bootstrap trong class file, cần compiler/code generator/bytecode tooling phù hợp.

Tạo file **`BootstrapModelDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Locale;

public class BootstrapModelDemo {
    private static String upper(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    public static CallSite bootstrap(
            MethodHandles.Lookup caller,
            String name,
            MethodType type) throws ReflectiveOperationException {
        if (!name.equals("transform")) {
            throw new IllegalArgumentException("Unknown operation: " + name);
        }

        MethodHandle target = caller.findStatic(
                BootstrapModelDemo.class, "upper",
                MethodType.methodType(String.class, String.class));
        if (!target.type().equals(type)) {
            throw new IllegalArgumentException("Mismatched target type");
        }
        return new ConstantCallSite(target);
    }

    public static void main(String[] args) throws Throwable {
        MethodType descriptor =
                MethodType.methodType(String.class, String.class);
        CallSite site = bootstrap(
                MethodHandles.lookup(), "transform", descriptor);
        MethodHandle invoker = site.dynamicInvoker();

        String result1 = (String) invoker.invokeExact("abc");
        String result2 = (String) invoker.invokeExact("java");
        System.out.println("call-site type: " + site.type());
        System.out.println("first: " + result1);
        System.out.println("second: " + result2);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 BootstrapModelDemo.java
java BootstrapModelDemo
```

Stdout đã kiểm tra:

```text
call-site type: (String)String
first: ABC
second: JAVA
```

**Giải thích theo từng thành phần:**

- `MethodType.methodType(String.class, String.class)` yêu cầu nhận một `String`, trả `String`: `(String)String`.
- `name` là `"transform"` do caller truyền. Nó không cần trùng tên method Java `upper`, vì bootstrap chủ động diễn giải tên.
- `caller.findStatic(...)` trả một `MethodHandle` tới `upper`. Caller có quyền phù hợp trong ví dụ vì nằm trong chính class.
- `new ConstantCallSite(target)` chứa target không thể thay thế bằng target khác sau khi tạo.
- `site.dynamicInvoker()` là một `MethodHandle` liên kết tới target của site. Hai lần gọi với `"abc"` và `"java"` chạy cùng logic nhưng dùng dữ liệu khác nhau.
- `(String) invoker.invokeExact(...)` ghi rõ return type `String`, khớp chữ ký target.

**Ranh giới của ví dụ:** dòng `bootstrap(...)` được gọi như **method Java bình thường**; JVM không thực hiện `CONSTANT_InvokeDynamic_info` resolution cho dòng đó. Vì vậy nó không chứng minh `invokedynamic` được phát ra từ custom bootstrap; ví dụ giúp hiểu **loại object** mà bootstrap thật cần trả về.

### 7.1. Vì sao có tham số `Lookup`?

`MethodHandles.Lookup` đóng gói quyền truy cập của caller và ngữ cảnh lookup. Bootstrap không tự có quyền “không giới hạn” để lấy private methods của module bất kỳ. Khi tạo `MethodHandle` từ class hoặc package khác, phải tuân thủ visibility và JPMS. Nếu `findStatic` không tìm được signature, có thể gặp `NoSuchMethodException`; nếu không được phép, có thể gặp `IllegalAccessException`.

Một bootstrap method được JVM gọi cho dynamic site thường nhận `Lookup` gắn với caller của instruction, nhưng nó vẫn phải tuân thủ hợp đồng và kiểm tra đầu vào nếu dùng để định tuyến tới các implementation do application cung cấp.

## 8. `ConstantCallSite`, `MutableCallSite`, `VolatileCallSite`

Các loại call site thường gặp:

| Loại | Có thể thay target sau khi tạo? | Đặc điểm chính | Khi thích hợp |
| --- | --- | --- | --- |
| `ConstantCallSite` | **Không** | Target ổn định; JVM có thể tối ưu hóa mạnh dựa trên sự bất biến này | Lambda/string-concat factory hoặc link cố định khi phù hợp |
| `MutableCallSite` | **Có** | Target có thể đổi, nhưng propagation giữa threads cần tuân thủ semantics/`syncAll` | Dynamic language runtime, inline cache hoặc relinking chủ động |
| `VolatileCallSite` | **Có** | Đọc/ghi target theo volatile semantics để thay đổi target được quan sát theo hợp đồng của lớp | Cần visibility cập nhật giữa threads mà không dùng cơ chế syncAll tương tự |

**Quy tắc không đổi:** Khi đã có `CallSite`, **type của target mới phải bằng type của target cũ**. Có thể thay method/adapter đang được gọi, nhưng **không** thay một site `(String)String` thành `(int)int` chỉ bằng `setTarget`.

### 8.1. Ví dụ đầy đủ: thay target của `MutableCallSite`

Tạo **`MutableCallSiteDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;

public class MutableCallSiteDemo {
    private static String oldVersion(String text) {
        return "old:" + text;
    }

    private static String newVersion(String text) {
        return "new:" + text;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type =
                MethodType.methodType(String.class, String.class);
        MethodHandle oldTarget = lookup.findStatic(
                MutableCallSiteDemo.class, "oldVersion", type);
        MethodHandle newTarget = lookup.findStatic(
                MutableCallSiteDemo.class, "newVersion", type);

        MutableCallSite site = new MutableCallSite(oldTarget);
        MethodHandle invoker = site.dynamicInvoker();

        String before = (String) invoker.invokeExact("Ada");
        System.out.println("before: " + before);

        site.setTarget(newTarget);
        MutableCallSite.syncAll(new MutableCallSite[] {site});

        String after = (String) invoker.invokeExact("Ada");
        System.out.println("after: " + after);
        System.out.println("site type: " + site.type());
    }
}
```

Chạy:

```bash
javac --release 17 MutableCallSiteDemo.java
java MutableCallSiteDemo
```

Stdout đã kiểm tra:

```text
before: old:Ada
after: new:Ada
site type: (String)String
```

Giải thích:

1. `oldTarget` và `newTarget` đều có `MethodType (String)String`.
2. `site.dynamicInvoker()` cho phép lời gọi trỏ tới **target hiện tại** của site.
3. Lần đầu gọi với `"Ada"`, target cũ trả `"old:Ada"`.
4. `site.setTarget(newTarget)` thay đổi target. `MutableCallSite.syncAll(...)` được dùng để đồng bộ publication của thay đổi này theo hợp đồng lớp trong trường hợp có nhiều luồng.
5. Lần gọi sau trả `"new:Ada"`, trong khi `site.type()` **không đổi**.

**Tương tự ví dụ trước:** chương trình này sử dụng `MutableCallSite` bằng Java API trực tiếp, **không tự sinh bytecode `invokedynamic`**. Khi một `invokedynamic` instruction thật được liên kết tới `MutableCallSite`, việc thay target sẽ ảnh hưởng các lần thực thi tiếp theo theo semantics của call site đó.

### 8.2. `MutableCallSite.syncAll` có nghĩa gì?

`MutableCallSite` không cam kết mọi thread thấy thay đổi target ngay theo cách volatile. `syncAll` là API dùng để cung cấp hiệu ứng đồng bộ phù hợp với các cập nhật target đã được thực hiện. `VolatileCallSite` có hợp đồng visibility khác (volatile semantics). Nếu build một dynamic language runtime đa luồng, việc thiếu các quy tắc publication có thể tạo hiện tượng một thread tiếp tục thấy target cũ.

Không dùng `MutableCallSite` chỉ để “đổi method tùy ý” mà bỏ qua synchronization semantics; cũng không chuyển target giữa các `MethodType` khác nhau.

## 9. Lambda và method reference: ví dụ `invokedynamic` khác với dynamic invocation

Java 8 giới thiệu lambda. Việc compiler tạo class/object cho lambda là một chi tiết triển khai. JVM cung cấp cơ chế `invokedynamic` mà `LambdaMetafactory` có thể dùng để liên kết một **factory call site**.

Ví dụ:

```java
@FunctionalInterface
interface Formatter {
    String format(String s);
}

static String upper(String s) {
    return s.toUpperCase(java.util.Locale.ROOT);
}

// Đoạn minh họa nằm trong class/method tương ứng:
Formatter a = s -> upper(s);
Formatter b = Example::upper;
String value = a.format("java");
```

Đây là **đoạn minh họa**: `Example` là tên class chứa method `upper`. Nếu đặt trong chương trình đầy đủ, cần khai báo `Formatter` và class theo cú pháp tương ứng.

Ở đây có thể xảy ra hai loại lời gọi:

- Khi tạo `Formatter a` hoặc `Formatter b`, compiler có thể phát `invokedynamic` để tạo/thu được object functional interface. Bootstrap `LambdaMetafactory.metafactory` nhận các metadata về SAM method type, implementation method handle và instantiated type.
- Khi gọi `a.format("java")`, source truy cập method trên kiểu `Formatter`, có thể phát `invokeinterface`. Code thực thi của lambda cuối cùng gọi `upper`.

Không nên đồng nhất **factory tạo lambda** với **mỗi lần gọi lambda**. Dynamic call site của lambda factory và interface invocation trên object lambda có nhiệm vụ khác nhau, dù có thể nằm trong cùng chương trình.

### 9.1. Captured và non-captured lambda

Với `s -> s.toUpperCase(...)`, lambda không dùng giá trị local bên ngoài; factory site có thể không cần dynamic capture arguments. Với:

```java
String prefix = "Hi ";
Formatter f = s -> prefix + s;
```

giá trị `prefix` được capture; call site tạo lambda có thể nhận giá trị đó làm **dynamic argument**. Bootstrap method nhận thêm **static metadata** về shape của functional interface, nhưng `prefix` thực tế của mỗi lần tạo lambda không nhất thiết là bootstrap constant.

Tách bạch hai loại dữ liệu này là chìa khóa để hiểu `invokedynamic` có thể kết hợp **liên kết hành vi** với **dữ liệu runtime**.

## 10. String concatenation: call site không phải lời gọi method có tên cố định

Trong Java 9+, JDK cung cấp `StringConcatFactory`. Một expression như:

```java
static String label(int id) {
    return "item-" + id;
}
```

có thể được compiler phát dưới dạng một dynamic call site với descriptor kiểu `(I)Ljava/lang/String;`. Tên trong constant pool có thể là `makeConcatWithConstants`, và thuộc tính `BootstrapMethods` cho biết bootstrap method handle tới `java.lang.invoke.StringConcatFactory`.

Vì sao điều này hữu ích?

- Compiler có thể trình bày **shape của phép nối** và static constants cho bootstrap, thay vì phải biết một chuỗi lệnh append tối ưu duy nhất tại compile time.
- Runtime có thể chọn implementation tối ưu cho target JDK, các kiểu argument và recipe.
- Khi nối nhiều lần với dữ liệu khác nhau, call site đã được liên kết vẫn có thể xử lý nhiều giá trị dynamic.
- Đây là chi tiết triển khai **có quyền thay đổi** theo compiler/runtime; ứng dụng không nên dựa vào tên factory hay cách tạo String để diễn giải semantics nghiệp vụ của toán tử `+`.

### 10.1. Không lấy `StringConcatFactory` làm bằng chứng của dynamic language dispatch

Dù `invokedynamic` được thiết kế rộng cho nhiều ngôn ngữ chạy trên JVM, string concat là một tính năng của Java có semantics rất rõ theo JLS. Trong trường hợp này bootstrap không “tìm method theo tên từ người dùng”; nó tạo target cho một thao tác nối chuỗi có chữ ký và constants được compiler cung cấp.

Điều đáng học là **tính tổng quát của call-site linkage**, không phải giả định `invokedynamic` luôn chọn method theo tên tại mỗi lần gọi.

## 11. `invokedynamic` so với gọi `MethodHandle.invokeExact`

Hai khái niệm gần nhau nhưng không trùng:

| Khía cạnh | `MethodHandle.invokeExact(...)` trong Java source | JVM instruction `invokedynamic` |
| --- | --- | --- |
| Điểm xuất phát | Java source gọi một method đặc biệt trên object `MethodHandle` | Bytecode chứa dynamic call-site specifier |
| Cách biết target | Caller đã giữ một object `MethodHandle` và dùng kiểu đó | JVM resolve bootstrap thành `CallSite` và lấy target |
| Khi chọn target | Chương trình đã tạo/nhận handle trước lời gọi | Bootstrap quyết định target trong quá trình liên kết call site |
| Kiểm tra chữ ký | Call-site descriptor của `invokeExact` phải bằng `handle.type()` | `CallSite.type()` phải bằng descriptor của `invokedynamic` |
| Có cần `BootstrapMethods`? | Không, nếu chỉ gọi handle trực tiếp | Có thông tin bootstrap cho call-site specifier tương ứng |
| Có thể làm target invocation? | Có, là cách gọi một `MethodHandle` | Semantics invocation của dynamic instruction dùng target `MethodHandle` theo type đã link |

Một đoạn code:

```java
MethodHandle h = MethodHandles.lookup().findStatic(
        SomeClass.class, "work",
        MethodType.methodType(int.class, int.class));
int x = (int) h.invokeExact(7);
```

là **đoạn minh họa** và cần có `SomeClass.work(int)`, imports và xử lý checked exceptions. Nó cho thấy caller giữ một handle và gọi đúng type. **Không** có căn cứ để nói compiler phải phát một `invokedynamic` tại dòng `h.invokeExact(7)`. Đây là chữ ký đặc biệt của `MethodHandle`, nhưng `invokedynamic` là một opcode khác.

Trong source Java bình thường cũng **không có** cú pháp `invokedynamic methodName(...)` để buộc compiler phát một dynamic instruction với bootstrap tùy ý. Muốn thử custom bootstrap **thật** cần compiler/bytecode generation tool hỗ trợ tạo constant-pool `InvokeDynamic` và `BootstrapMethods`.

## 12. Error handling: liên kết sai khác target thực thi lỗi

Khi đọc stack trace, phải biết lỗi xuất hiện **trong quá trình liên kết** hay **sau khi đã liên kết và gọi target**.

| Lỗi / hiện tượng | Giai đoạn thường gặp | Ý nghĩa / hướng kiểm tra |
| --- | --- | --- |
| `BootstrapMethodError` | Linkage/resolution | Bootstrap hoặc các argument của nó không thể resolve; bootstrap không trả `CallSite` hợp lệ; target type không trùng call-site descriptor; hoặc lỗi bootstrap phù hợp theo JVMS |
| `NoSuchMethodException` tại `Lookup.findStatic` | Trong code bootstrap | Không tìm được method có đúng tên/kind/type được bootstrap yêu cầu; nếu bootstrap ném checked exception khi JVM resolve site, thường được bọc thành linkage error phù hợp |
| `IllegalAccessException` tại `Lookup.findVirtual/findStatic` | Trong code bootstrap | Lookup context không được quyền truy cập target method/class; cần sửa quyền/module hay target |
| `WrongMethodTypeException` từ lời gọi `MethodHandle.invokeExact` thủ công | Khi code Java gọi MH | Descriptor tại caller khác `handle.type()`; **không tự động** là lỗi của một `invokedynamic` |
| `ClassCastException` hoặc `IllegalArgumentException` từ target | Khi thực thi target | Target/code adapter nhận dữ liệu không hợp lệ; không mặc nhiên do bootstrap |
| `NullPointerException` khi `invokevirtual`/`invokeinterface` receiver null | Khi gọi thông thường | Receiver object không tồn tại; không có liên hệ trực tiếp với bootstrap |
| `NoSuchMethodError`/`AbstractMethodError`/`IncompatibleClassChangeError` | JVM method resolution/selection/invocation | Có thể liên quan binary incompatibility hoặc contract method không phù hợp; không phải mọi lỗi này đều là `BootstrapMethodError` |

**Chẩn đoán `BootstrapMethodError`:** xác định lỗi ở bước resolve bootstrap method handle/static arguments, trong body bootstrap, hay tại bước JVM kiểm tra kết quả `CallSite` có `MethodType` đúng. Theo JVMS, lỗi linkage liên quan bootstrap có những quy tắc truyền/wrap `Error` cụ thể; không nên khẳng định mọi exception từ bootstrap đều được bọc y hệt nhau. Xem `getCause()`, stack trace và từng phiên bản JVM.

### 12.1. Ví dụ type mismatch ở bootstrap

Giả sử instruction được khai báo với descriptor:

```text
(java.lang.String)java.lang.String
```

Bootstrap trả một `ConstantCallSite` có target `MethodHandle` kiểu:

```text
(int)int
```

Đây là **mô tả lỗi linkage**, không phải chương trình Java độc lập. `CallSite.type()` không trùng descriptor của dynamic instruction; JVM không thể liên kết site đó và có thể ném `BootstrapMethodError`.

Chú ý: code Java tự gọi `new ConstantCallSite(target)` với target khác kiểu **không** tự sinh `BootstrapMethodError`. Lỗi này gắn với **resolution của dynamic call site/dynamic constant bởi JVM**, không phải bất kỳ object `CallSite` nào được tạo thủ công.

### 12.2. Target ném lỗi sau khi link

Nếu bootstrap đã trả một call site hợp lệ nhưng target method ném `IllegalStateException` khi nhận input xấu, exception đó là **lỗi chạy target**. JVM không tự gọi lại bootstrap hoặc biến mọi lỗi chạy target thành `BootstrapMethodError`.

Tương tự, thay một `MutableCallSite` bằng target mới có cùng signature không có nghĩa loại bỏ mọi bug của target. Linking contract đảm bảo **type shape**, không đảm bảo target luôn thành công về nghiệp vụ.

## 13. Performance và tối ưu hóa: không có “nhanh hơn” một cách tuyệt đối

Mục đích quan trọng của `invokedynamic` là trao cho runtime/compiler một cơ chế linh hoạt để xây và liên kết target tại từng site, **không phải** bảo đảm nó nhanh hơn `invokevirtual`/`invokeinterface` trong mọi workload.

Một `ConstantCallSite` có target ổn định giúp JVM/JIT có cơ hội tối ưu hóa. Một `MutableCallSite` đổi target thường xuyên có thể làm các giả định tối ưu không còn đúng và kéo theo chi phí đồng bộ/tái tối ưu. Ngược lại, `invokevirtual`/`invokeinterface` được JIT tối ưu rất tốt với thông tin type profile, devirtualization và inlining khi phù hợp.

Khi đánh giá:

- Đo chi phí **linkage/bootstrap** riêng với chi phí **những lần execution đã link**. Một bootstrap tốn kém không có nghĩa mọi lần thực thi đều tốn kém như vậy.
- Kiểm tra site có ổn định kiểu/target không; số kiểu receiver và mức độ biến động target có ảnh hưởng đến khả năng tối ưu.
- Sử dụng benchmark chuẩn như JMH khi có câu hỏi hiệu năng; tránh kết luận từ một lần `System.nanoTime()` chưa có warm-up và kiểm soát JVM flags.
- Đừng thêm `invokedynamic` bằng bytecode tooling chỉ vì nghĩ tên opcode nghe “động” thì sẽ tự tối ưu tốt hơn.

**Đúng semantics trước, benchmark sau.** Đa số Java application nên viết Java source rõ nghĩa và để compiler/JVM tự chọn những kỹ thuật phù hợp.

## 14. Bảo mật và module boundaries

`invokedynamic` không mở quyền truy cập vô hạn:

1. Bootstrap method handle phải resolve được theo quy tắc JVM. Nếu tên, type, access hoặc static args không hợp lệ, site không thể liên kết đúng.
2. `Lookup` được chuyển đến bootstrap có ngữ cảnh/privileges liên quan đến **caller của dynamic instruction**, nhưng nó không cho phép truy cập tùy tiện mọi private member từ module khác.
3. Khi bootstrap dùng `findStatic`, `findVirtual`, `privateLookupIn`, các API đó vẫn chịu language access và JPMS.
4. MethodHandle đã được tạo hợp lệ là một **capability**: nếu runtime phát tán handle tới code không tin cậy, phải xem xét quyền mà target có thể thực hiện.
5. Compiler/bytecode generator nhận input không đáng tin có thể tạo bootstrap arguments hoặc call-site names gây lỗi, khởi tạo lớp ngoài dự kiến hoặc gọi code nguy hiểm. Cần giới hạn những target được phép liên kết và validate đầu vào.

Ví dụ một ngôn ngữ động tự xây cache method calls có thể chọn bootstrap theo class của receiver ở **lần gọi đầu** rồi tạo adapter phù hợp; tuy nhiên thiết kế đó phải có chiến lược invalidate/relink và bảo vệ quyền truy cập. Opcode `invokedynamic` **không tự thực hiện cache theo receiver** nếu bootstrap không lập trình điều đó.

## 15. Quy trình debug `invokedynamic` thực tế

Khi chương trình có stack trace phức tạp hoặc một lambda/string concat bất ngờ lỗi khi lên JDK mới:

### Bước 1 — Xác định class file thật

Lấy file `.class` đã build theo đúng JDK/compiler/flags của môi trường gặp lỗi. Nếu chạy từ JAR, dùng đúng artifact đó; không dựa vào source mới hơn chưa deploy.

### Bước 2 — Inspect instructions và constant pool

```bash
javap -c -p InvokeDynamicContrastDemo
javap -v InvokeDynamicContrastDemo
```

Đọc:

- Có `invokevirtual`, `invokeinterface`, hay `invokedynamic` tại method cần kiểm tra?
- `invokedynamic` tham chiếu constant-pool index nào, có **NameAndType** gì?
- `BootstrapMethods` tại index đó trỏ tới bootstrap method handle nào?
- Có static bootstrap arguments nào? Ví dụ method type, implementation handle, recipe.

Không phỏng đoán chỉ từ method name hiển thị sau dấu `#` trong disassembly. Cần nối **instruction → constant pool → BootstrapMethods**.

### Bước 3 — Kiểm tra hợp đồng type

- Dynamic site descriptor có các parameter và return types nào?
- Bootstrap trả `CallSite.type()` tương đương descriptor ấy không?
- Nếu bootstrap dựng `MethodHandle` từ lookup rồi `asType`/adapters, type cuối cùng trước khi đóng vào `CallSite` là gì?
- Với `MutableCallSite`, target mới có **cùng type** với target cũ không?

### Bước 4 — Xác định lỗi linkage hay target logic

Nếu là `BootstrapMethodError`, đọc cause chain và vị trí bootstrap. Nếu lỗi xảy ra sau linkage từ code của target, điều tra target method và dữ liệu thực thi.

Đối với `invokevirtual`/`invokeinterface`, kiểm tra receiver thực tế, method overriding/default implementations, class loader mismatch và binary compatibility. Không tự tìm `BootstrapMethods` cho một lời gọi thông thường không dùng `invokedynamic`.

### Bước 5 — Kiểm tra thay đổi mục tiêu ở runtime

Nếu site là mutable/volatile, xác minh đường `setTarget`, `syncAll` khi dùng MutableCallSite, và việc các threads quan sát target đúng theo hợp đồng. Đối với `ConstantCallSite`, target không thay đổi; tìm nguyên nhân khác thay vì giả định “bootstrap được gọi lại mỗi lần”.

### Bước 6 — Chẩn đoán tương thích khi nâng cấp JVM

Xem target classfile version, JDK runtime, tool sinh bytecode, quyền JPMS, và sự tương thích của framework/lambda metafactory/custom bootstraps. Một `BootstrapMethodError` sau nâng cấp có thể đến từ bytecode generator hoặc signatures không hợp lệ, chứ không nên chữa mặc định bằng `--add-opens`.

## 16. Những hiểu lầm cần tránh

**Hiểu lầm 1 — “`invokevirtual` và `invokeinterface` là static dispatch.”**

Sai. Cả hai đều có runtime method selection theo receiver, đó là nền tảng polymorphism của JVM.

**Hiểu lầm 2 — “`invokedynamic` gọi tên method được ghi trong opcode giống `invokevirtual`.”**

Sai. Nó tham chiếu call-site specifier với bootstrap; tên call site được bootstrap diễn giải, còn target method handle được quyết định qua linking.

**Hiểu lầm 3 — “Bootstrap được gọi trên mỗi dynamic invocation.”**

Sai sau khi site đã liên kết thành công. JVM dùng `CallSite` đã link; target có thể thay đổi với các site cho phép relinking. Tuy nhiên, đừng khẳng định bootstrap body luôn thực thi đúng một lần trong mọi tình huống concurrent resolution.

**Hiểu lầm 4 — “Mọi `invokedynamic` đều có target mutable.”**

Sai. `ConstantCallSite` không cho đổi target; mutable/volatile site mới có semantics đổi target.

**Hiểu lầm 5 — “Lambda sử dụng `invokedynamic` nên gọi `lambda.apply(...)` cũng phải là `invokedynamic`.”**

Sai. Factory tạo lambda có thể dùng `invokedynamic`, nhưng invocation của phương thức functional interface thường là `invokeinterface`.

**Hiểu lầm 6 — “`MethodHandle.invokeExact` và `invokedynamic` là cùng opcode.”**

Sai. Một bên là signature-polymorphic API gọi một handle đã có; bên kia là bytecode instruction liên kết call site qua bootstrap.

**Hiểu lầm 7 — “Gọi bootstrap bằng Java bình thường chứng minh custom `invokedynamic` hoạt động.”**

Sai. Mô phỏng tạo `CallSite` chỉ kiểm thử code bootstrap/handle; muốn instruction thật phải tạo đúng class-file entry và call-site specifier.

**Hiểu lầm 8 — “`StringConcatFactory` chỉ chạy khi nối chuỗi của ngôn ngữ động.”**

Sai. Java compiler dùng nó cho string concatenation trong Java, tùy compiler strategy và target runtime.

**Hiểu lầm 9 — “Bootstrap có `Lookup` nên có thể vượt mọi private/module restrictions.”**

Sai. Lookup có scope và access privileges theo quy tắc JVM/JPMS; private access tới named module khác có thể bị hạn chế.

**Hiểu lầm 10 — “Đổi `MutableCallSite` sang signature khác sẽ cho JVM tự adapt.”**

Sai. `CallSite.type()` bất biến. Target mới phải có cùng `MethodType`; nếu cần conversion, phải xây một adapter **tương thích** trước khi gán.

**Hiểu lầm 11 — “Bất kỳ exception từ target của indy đều là `BootstrapMethodError`.”**

Sai. Lỗi bootstrap thuộc linkage; lỗi nghiệp vụ của target sau linkage không tự động trở thành lỗi bootstrap.

**Hiểu lầm 12 — “`invokedynamic` luôn nhanh hơn virtual dispatch.”**

Sai. JIT tối ưu rất tốt virtual/interface calls; hiệu năng indy phụ thuộc call-site stability, target shape, linking cost và workload.

## 17. Bài tập tự kiểm tra và đáp án

**Câu 1.** Vì sao `Animal a = new Dog(); a.sound();` vẫn được coi là gọi động nếu bytecode là `invokevirtual`?

**Đáp án:** Vì implementation được chọn theo class thực tế của receiver (`Dog`) tại runtime, theo quy tắc virtual dispatch. “Động” ở đây là **receiver-based dispatch**, khác cơ chế bootstrap-defined call-site linkage của `invokedynamic`.

**Câu 2.** `Formatter f = s -> s.toUpperCase(); f.format("hi");`: khả năng xuất hiện `invokedynamic` và `invokeinterface` ở đâu?

**Đáp án:** Khi tạo đối tượng lambda, compiler có thể dùng `invokedynamic` cùng `LambdaMetafactory`. Khi gọi `f.format("hi")` theo kiểu `Formatter`, bytecode có thể dùng `invokeinterface`. Hai instruction giải quyết hai việc khác nhau.

**Câu 3.** Mục `InvokeDynamic` có bootstrap index và NameAndType. Nó có trỏ trực tiếp đến implementation method không?

**Đáp án:** Không. Nó mô tả **call site** và cách tìm bootstrap, còn bootstrap quyết định `CallSite`/target `MethodHandle` phải liên kết.

**Câu 4.** Bootstrap nhận ba đối số chuẩn nào và vai trò của `MethodType` là gì?

**Đáp án:** `MethodHandles.Lookup caller`, `String name`, `MethodType type`; có thể thêm static bootstrap args. `MethodType` là hợp đồng parameter và return types mà target của `CallSite` phải khớp.

**Câu 5.** `ConstantCallSite` và `MutableCallSite` khác nhau chỗ nào khi muốn đổi implementation?

**Đáp án:** Constant target không đổi; Mutable target có thể được `setTarget` để chuyển sang MethodHandle khác **cùng type**, và cần xét `syncAll` khi phối hợp nhiều threads.

**Câu 6.** Một bytecode site `(String)String` nhận `CallSite` có target `(int)int`. Điều gì sai?

**Đáp án:** `CallSite.type()` không bằng descriptor của invokedynamic site, nên linkage thất bại (thường `BootstrapMethodError`), không phải runtime polymorphic dispatch bình thường.

**Câu 7.** Vì sao `"id=" + number` có thể sử dụng `invokedynamic`?

**Đáp án:** Compiler có thể dùng `StringConcatFactory` làm bootstrap để tạo target nối chuỗi theo recipe, với `number` là argument động mỗi lần thực thi. Phép nối hai literal có thể bị constant folding nên không nhất thiết có indy.

**Câu 8.** Một bootstrap method có side effect tăng biến đếm. Có thể khẳng định nó tăng đúng một lần cho mỗi dynamic instruction không?

**Đáp án:** Không trong mọi trường hợp. Concurrent resolution có thể kích hoạt bootstrap nhiều lần và JVM chỉ chọn một kết quả call site. Không dựa vào side effect không được đồng bộ trong bootstrap.

**Câu 9.** `MethodHandle h = lookup.findStatic(...); h.invokeExact(...);` có tự tạo `BootstrapMethods` entry không?

**Đáp án:** Không chỉ từ việc gọi `invokeExact`. Đây là direct MethodHandle invocation. Muốn custom invokedynamic instruction, bytecode phải chứa call-site specifier và bootstrap metadata tương ứng.

**Câu 10.** Sau khi site liên kết thành công, target method ném `IllegalStateException`. Có phải `BootstrapMethodError` không?

**Đáp án:** Không mặc định. Đây là exception từ target trong quá trình execution. Cần đọc stack trace và cause thực tế, không kết luận đó là lỗi liên kết.

**Câu 11.** Vì sao `invokeinterface` không phải một `invokedynamic` “đơn giản hơn”?

**Đáp án:** `invokeinterface` áp dụng dispatch dựa trên interface method reference và receiver theo semantics cố định của JVM. `invokedynamic` liên kết target bằng bootstrap-defined call-site mechanism; sự khác nhau là **cơ chế chọn target**.

**Câu 12.** Trong `javap -v`, cần kết hợp những thông tin nào để hiểu một `invokedynamic`?

**Đáp án:** Instruction offset và constant-pool index, entry `CONSTANT_InvokeDynamic_info` với name/descriptor, bootstrap method index trong `BootstrapMethods`, bootstrap method handle và static arguments. Chỉ nhìn tên sau `InvokeDynamic` là chưa đủ.

## 18. Tài liệu chuẩn

- **Java Virtual Machine Specification 17, §6.5 — `invokedynamic`, `invokevirtual`, `invokeinterface`:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html — opcode semantics, dispatch và cơ chế gọi target.
- **JVMS 17, §5.4.3.6 — Dynamically-Computed Constant and Call Site Resolution:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6 — bootstrap resolution, liên kết `CallSite`, concurrent resolution và lỗi.
- **JVMS 17, §4.4.10 / §4.7.23:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html — `CONSTANT_InvokeDynamic_info` và thuộc tính `BootstrapMethods`.
- **Java SE 17, `CallSite` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html — target MethodHandle và ba loại CallSite.
- **Java SE 17, `ConstantCallSite` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html — target bất biến.
- **Java SE 17, `MutableCallSite` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html — relinking và `syncAll`.
- **Java SE 17, `VolatileCallSite` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html — visibility theo volatile semantics.
- **Java SE 17, `MethodHandle` và `MethodType`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html ; https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html .
- **Java SE 17, `LambdaMetafactory`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html — linkage của lambda/metafactory.
- **Java SE 17, `StringConcatFactory`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html — bootstrap cho string concatenation.
- **JEP 292 và JSR 292:** https://openjdk.org/jeps/292 ; https://jcp.org/en/jsr/detail?id=292 — Method Handles và invokedynamic trong phát triển JVM.

**Kết luận:** `invokevirtual` và `invokeinterface` đã là những cơ chế **dynamic method dispatch qua receiver**. `invokedynamic` bổ sung khả năng **định nghĩa cách một call site được liên kết thông qua bootstrap**; sau khi liên kết, call site thực thi target `MethodHandle` có chữ ký chính xác. Hãy xem instruction, call-site specifier, bootstrap metadata và target type như **bốn lớp thông tin liên quan nhưng khác nhau**, thay vì coi mọi lệnh có chữ “dynamic” là cùng một cơ chế.