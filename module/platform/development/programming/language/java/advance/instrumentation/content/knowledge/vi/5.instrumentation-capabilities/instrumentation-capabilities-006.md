# Primitive class, array class và những lớp không thể sửa bằng Java Instrumentation

Khi xây dựng Java agent để quan sát, đo hiệu năng hoặc thay đổi bytecode của một JVM đang chạy, ta không thể giả định rằng mọi đối tượng `Class<?>` đều có thể được **retransform** hoặc **redefine**. Hai nhóm luôn bị loại trừ là **primitive class** (bao gồm đối tượng `Class` đại diện cho `void`) và **array class**. Ngoài ra, JVM có thể có những lớp đặc biệt khác không thể sửa.

Bài này thuộc chủ đề **Khả năng Instrumentation**, tập trung vào việc nhận diện đúng các loại lớp đó, kiểm tra bằng `Instrumentation.isModifiableClass(Class<?>)` và phân biệt khả năng sửa một **lớp** với việc hỗ trợ một **thao tác thay đổi bytecode**. Sau bài học, bạn sẽ biết vì sao `int[].class` không thể retransform nhưng vẫn có thể instrument phương thức Java thực hiện thao tác trên mảng; cách xử lý `UnmodifiableClassException`; và cách lọc mục tiêu trước khi gọi instrumentation API.

## 1. “Class” trong Java không phải lúc nào cũng là file .class

`java.lang.Class<?>` có thể đại diện cho một lớp được định nghĩa bằng bytecode, một interface, kiểu nguyên thủy, `void` hoặc một lớp mảng do JVM tạo ra. Chúng đều có `Class` object nhưng không có cùng cơ chế hình thành:

| Biểu thức | Kết quả `isPrimitive()` | Kết quả `isArray()` | Bản chất |
| --- | --- | --- | --- |
| `int.class` | `true` | `false` | Đối tượng `Class` đại diện primitive `int` |
| `Integer.TYPE` | `true` | `false` | Cùng đối tượng `Class` với `int.class` |
| `void.class` / `Void.TYPE` | `true` | `false` | Đối tượng `Class` đại diện kiểu giả `void` |
| `Integer.class` | `false` | `false` | Lớp wrapper thông thường `java.lang.Integer` |
| `int[].class` | `false` | `true` | Lớp mảng một chiều có phần tử `int` |
| `int[][].class` | `false` | `true` | Lớp mảng hai chiều có phần tử `int` |
| `String[].class` | `false` | `true` | Lớp mảng chứa tham chiếu `String` |
| `String.class` | `false` | `false` | Lớp thường, có class file trong JDK |
| `Runnable.class` | `false` | `false` | Interface thông thường |

Trong biểu thức `int[].class`, chữ `class` không nói rằng có một file `int[].class` do `javac` sinh ra. JVM tạo array class theo quy tắc riêng. Tương tự, kiểu nguyên thủy `int` không có bytecode của một class thông thường mà agent có thể thay thế.

Những cặp tên dễ nhầm:

- `int.class == Integer.TYPE` là `true`, nhưng `int.class == Integer.class` là `false`.
- `Integer[].class` cũng là array class, dù phần tử `Integer` là một class thông thường.
- `String.class` và `String[].class` là **hai** đối tượng `Class` khác nhau. Khả năng sửa lớp `String` không quyết định khả năng sửa lớp mảng `String[]`.
- Các kiểu `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean` và `void` đều được nhận diện bằng `Class.isPrimitive()`.

## 2. Hợp đồng của Instrumentation.isModifiableClass()

Phương thức:

~~~java
boolean isModifiableClass(Class<?> theClass)
~~~

trả lời câu hỏi: **“Lớp này có được JVM coi là modifiable cho retransformation hoặc redefinition không?”** Không có chuyển đổi bytecode hoặc attach nào được thực hiện khi chỉ gọi phương thức kiểm tra này.

Các quy tắc quan trọng trong Java Instrumentation API:

1. Nếu trả về `false`, lớp đó **không thể** retransform hoặc redefine qua các API tương ứng.
2. Nếu trả về `true`, lớp **qua được bước kiểm tra modifiability**, nhưng chưa bảo đảm thao tác thực tế sẽ thành công.
3. Với **primitive class** và **array class**, kết quả **luôn là `false`** theo hợp đồng API, bất kể cấu hình JVM.
4. `isModifiableClass(null)` ném `NullPointerException`; phải kiểm tra `null` trong code lọc đầu vào.
5. Giá trị này **không phụ thuộc** vào việc JVM hiện có hỗ trợ retransformation hoặc redefinition. Hai loại capability đó phải được kiểm tra **riêng**.

Có thể hình dung hai bước xác nhận cần thiết:

~~~text
Lớp mục tiêu C
    |
    v
inst.isModifiableClass(C)?
    | false
    +----------> Không thử sửa C
    |
    | true
    v
Thao tác muốn làm là gì?
    |
    +--> retransform -> inst.isRetransformClassesSupported()?
    |
    +--> redefine ----> inst.isRedefineClassesSupported()?
                              |
                              v
                       Kiểm tra ràng buộc thay đổi
                       bytecode rồi mới thực hiện
~~~

**`isModifiableClass(C) == true` không tương đương `retransformClasses(C)` chắc chắn thành công.** Việc có capability, class bytes hợp lệ và loại thay đổi mà JVM cho phép là các điều kiện độc lập.

### Phân biệt ba câu hỏi

| Câu hỏi | API | Ý nghĩa |
| --- | --- | --- |
| Lớp `C` có thể sửa bằng hai cơ chế này về nguyên tắc không? | `isModifiableClass(C)` | Khả năng của **một lớp cụ thể** |
| JVM/agent hiện hỗ trợ retransform không? | `isRetransformClassesSupported()` | Khả năng **của môi trường và agent** |
| JVM/agent hiện hỗ trợ redefine không? | `isRedefineClassesSupported()` | Khả năng **của môi trường và agent** |

Đối với Java agent, hai capability thường cần khai báo trong manifest với `Can-Retransform-Classes: true` và `Can-Redefine-Classes: true`, đồng thời JVM phải thực sự hỗ trợ. Khai báo manifest không thể “mở khóa” khả năng sửa primitive hoặc array class.

## 3. Primitive class và array class: hai nhóm luôn không thể sửa

### 3.1. Primitive class

Các đối tượng `boolean.class`, `byte.class`, `char.class`, `short.class`, `int.class`, `long.class`, `float.class`, `double.class` và `void.class` không biểu diễn lớp bình thường có method bytecode để thay.

Ví dụ:

~~~java
boolean a = inst.isModifiableClass(int.class);       // false
boolean b = inst.isModifiableClass(Integer.TYPE);    // false
boolean c = inst.isModifiableClass(void.class);      // false
~~~

Các lệnh như `iadd`, `iload` hoặc `ireturn` xuất hiện **bên trong phương thức của một class khác**. Muốn đo phép cộng kiểu `int`, agent cần instrument **method thực hiện phép cộng**, không sửa `int.class`.

**Phân biệt với wrapper:** `java.lang.Integer` là một class có bytecode thông thường, nên `Integer.class.isPrimitive()` trả `false`. Tuy nhiên không được kết luận ngay `inst.isModifiableClass(Integer.class)` sẽ `true` trên mọi JVM: phải hỏi runtime. Càng không được xem mọi lớp JDK là an toàn để sửa.

### 3.2. Array class

Array class được JVM tạo theo kiểu phần tử và số chiều; không tương ứng với một file class độc lập mà agent có thể retransform.

~~~java
boolean a = inst.isModifiableClass(int[].class);       // false
boolean b = inst.isModifiableClass(String[].class);    // false
boolean c = inst.isModifiableClass(long[][].class);    // false
boolean d = inst.isModifiableClass(Object[][][].class);// false
~~~

Điều này áp dụng cho **mọi** array class, bao gồm mảng primitive, mảng object, nhiều chiều và mảng có kiểu phần tử là interface. Mặc dù `int[].class.isPrimitive()` là `false`, `int[].class.isArray()` là `true` nên vẫn bị loại. Với `String[].class`, yếu tố quyết định là **lớp mảng**, không phải `String.class` có thể sửa hay không.

Các method thực hiện thao tác trên mảng vẫn có bytecode có thể là mục tiêu instrument:

| Thao tác | Bytecode thường liên quan | Lớp mà agent cần nhắm tới |
| --- | --- | --- |
| Tạo mảng primitive | `newarray` | Class chứa lệnh tạo mảng |
| Tạo mảng đối tượng | `anewarray` | Class chứa lệnh tạo mảng |
| Tạo mảng nhiều chiều | `multianewarray` | Class chứa lệnh tạo mảng |
| Đọc phần tử `int[]` | `iaload` | Class chứa method đọc mảng |
| Ghi phần tử tham chiếu | `aastore` | Class chứa method ghi mảng |
| Đọc chiều dài mảng | `arraylength` | Class chứa method truy cập mảng |

Ví dụ Java:

~~~java
public int total(int[] values) {
    int result = 0;
    for (int value : values) {
        result += value;
    }
    return result;
}
~~~

Khi instrument phương thức `total`, agent có thể thêm đo thời gian vào **bytecode của class khai báo `total`**, nếu class đó đủ điều kiện. Agent không cần và không thể redefine `int[].class`. Đây là một khác biệt rất quan trọng giữa **instrument thao tác dùng một kiểu** với **instrument lớp đại diện cho kiểu đó**.

## 4. Những lớp nào khác có thể không sửa được?

Ngoài hai nhóm luôn bị loại, JVM TI Specification còn nhắc tới **một số lớp phụ thuộc implementation** (*implementation-defined classes*) không thể sửa. Không có một danh sách tên class cố định, portable, để áp dụng cho mọi JDK/JVM. Vì vậy **kiểm tra từng `Class<?>` bằng `isModifiableClass` ở chính JVM mục tiêu** là cách đúng.

### 4.1. Hidden class

JDK 15+ có hidden classes, được tạo thông qua `MethodHandles.Lookup.defineHiddenClass(...)`; Java 17+ cung cấp `Class.isHidden()` để nhận diện. Chúng thường xuất hiện trong việc hiện thực các tính năng động của runtime. Trên HotSpot hiện đại, hidden class **không thể redefine hoặc retransform**. Đó là một ví dụ quan trọng về lớp không thể sửa dù `isPrimitive()` và `isArray()` đều `false`.

~~~java
if (clazz.isHidden()) {
    // Không xếp vào danh sách mục tiêu redefine/retransform.
}
~~~

Đoạn trên là **minh họa lọc ứng viên**, không phải chương trình chạy độc lập; `clazz` phải được cung cấp từ code khám phá class. Không giả định rằng **mọi** lớp tổng hợp `synthetic` đều là hidden class hoặc mọi lớp sinh động đều không thể sửa. Chẳng hạn, việc một tên class chứa `$$Lambda` không phải hợp đồng API ổn định để kiểm tra khả năng sửa; hãy dùng `isHidden()` và `isModifiableClass()`.

### 4.2. Final, record, enum, interface và lớp thư viện JDK

Một số đặc điểm **không tự động đồng nghĩa** với unmodifiable:

- `final class`: `final` cấm kế thừa trong Java, không tự có nghĩa là `isModifiableClass == false`.
- `record`, `enum`, `sealed class`: có các quy tắc cấu trúc riêng, nhưng chỉ dựa trên từ khóa này không đủ để kết luận khả năng retransform/redefine.
- Interface hoặc abstract class: JVM có thể hỗ trợ instrument method phù hợp; phải kiểm tra từng lớp.
- Class được bootstrap class loader nạp, chẳng hạn `java.lang.String`: không phải cứ thuộc `java.*` là tự động bị API đánh dấu `false`; trên JVM cụ thể có thể modifiable. Việc thay đổi lớp lõi vẫn tiềm ẩn ảnh hưởng rộng, cần cân nhắc độc lập với kết quả boolean.

Cần tách bạch ba khái niệm: **khả năng sửa class**, **quy tắc cấu trúc class file**, và **quyền truy cập module hoặc hệ thống**. Chẳng hạn, `Instrumentation.isModifiableModule(Module)` là API khác để hỏi về khả năng mở rộng quan hệ module; không thay thế `isModifiableClass` và không cho phép sửa primitive/array class.

## 5. Ví dụ Java 17+: chạy agent và kiểm chứng ngay trên JVM

Để gọi `Instrumentation.isModifiableClass` cần có **Instrumentation instance** do JVM cấp cho Java agent qua `premain` hoặc `agentmain`. Không có constructor công khai để ứng dụng thông thường tự tạo instance. Ví dụ sau sử dụng `-javaagent` lúc khởi động, **chỉ kiểm tra metadata và thử một lỗi có kiểm soát trên array class**, không sửa bytecode ứng dụng.

### 5.1. Tạo ModifiabilityProbe.java

~~~java
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class ModifiabilityProbe {
    private static volatile Instrumentation instrumentation;

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
    }

    public static void main(String[] args) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException(
                    "Run with -javaagent:modifiability-probe.jar");
        }

        Class<?>[] examples = {
            int.class, void.class, int[].class, String[][].class
        };

        for (Class<?> type : examples) {
            System.out.printf(
                    "%s | primitive=%b | array=%b | modifiable=%b%n",
                    type.getTypeName(),
                    type.isPrimitive(),
                    type.isArray(),
                    inst.isModifiableClass(type));
        }

        System.out.println("ownClassModifiable="
                + inst.isModifiableClass(ModifiabilityProbe.class));
        System.out.println("retransformSupported="
                + inst.isRetransformClassesSupported());
        System.out.println("redefineSupported="
                + inst.isRedefineClassesSupported());

        if (inst.isRetransformClassesSupported()) {
            try {
                inst.retransformClasses(int[].class);
                System.out.println("arrayRetransform=unexpected-success");
            } catch (UnmodifiableClassException expected) {
                System.out.println(
                        "arrayRetransform=UnmodifiableClassException");
            }
        } else {
            System.out.println("arrayRetransform=not-attempted");
        }
    }
}
~~~

Chương trình dùng `getTypeName()` để tên mảng hiển thị dưới dạng `int[]` hoặc `java.lang.String[][]`, dễ đọc hơn dạng tên JVM như `[I`, `[[Ljava.lang.String;`.

### 5.2. Tạo file agent.mf

Nội dung manifest:

~~~text
Manifest-Version: 1.0
Premain-Class: ModifiabilityProbe
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

Lưu ý **kết thúc file manifest bằng một dòng trống**. Hai dòng `Can-...: true` là yêu cầu năng lực của agent; JVM vẫn quyết định có đáp ứng được hay không. Lớp `ModifiabilityProbe` có cả `premain` và `main` để dùng cùng một chương trình làm agent và ứng dụng mẫu, tránh cần dự án riêng.

### 5.3. Biên dịch, đóng gói, chạy

Đặt hai file `ModifiabilityProbe.java` và `agent.mf` trong cùng thư mục. Chạy bằng JDK 17+:

~~~bash
javac ModifiabilityProbe.java
jar --create --file modifiability-probe.jar --manifest agent.mf ModifiabilityProbe.class
java -javaagent:modifiability-probe.jar -cp . ModifiabilityProbe
~~~

**Ví dụ stdout đã chạy thành công trên HotSpot JDK 24:**

~~~text
int | primitive=true | array=false | modifiable=false
void | primitive=true | array=false | modifiable=false
int[] | primitive=false | array=true | modifiable=false
java.lang.String[][] | primitive=false | array=true | modifiable=false
ownClassModifiable=true
retransformSupported=true
redefineSupported=true
arrayRetransform=UnmodifiableClassException
~~~

**Bốn dòng đầu** với giá trị `modifiable=false` là phần có tính quy tắc cho primitive/array. **Ba dòng capability/ownClassModifiable** phụ thuộc JVM và cách cấu hình agent, nên không coi toàn bộ output trên là cố định cho mọi môi trường. Nếu JVM không hỗ trợ retransformation, chương trình sẽ in `arrayRetransform=not-attempted`. Đoạn `catch` chỉ nhận đúng `UnmodifiableClassException`; nó không che các lỗi bất ngờ khác.

Có thể bỏ hẳn khối `retransformClasses(int[].class)` để biến ví dụ thành công cụ **chỉ đọc**, vì giá trị `false` của `isModifiableClass(int[].class)` đã đủ chứng minh lớp mảng không được phép sửa.

### 5.4. Vì sao phải chạy bằng -javaagent?

Dòng:

~~~java
public static void premain(String arguments, Instrumentation inst)
~~~

là entry point mà JVM gọi khi xử lý `Premain-Class` trong manifest. JVM cấp tham số `Instrumentation` trước khi chạy `main`. Nếu chỉ gọi `java ModifiabilityProbe` mà không có `-javaagent` thì biến static không được khởi tạo và chương trình báo lỗi chủ đích. Việc chạy code trong IDE cũng phải cấu hình VM options tương ứng.

## 6. Lọc lớp đủ điều kiện trước khi retransform

Khi agent muốn xử lý nhiều lớp, đừng truyền bừa `inst.getAllLoadedClasses()` vào `retransformClasses(...)`. Danh sách lớp đã load **không phải danh sách lớp có thể sửa**.

Trên Java 21, `Instrumentation.getAllLoadedClasses()` được mô tả là trả các class/interface đã load, **bao gồm array class và hidden class**. Theo JVM TI Specification, primitive class không được tính vào danh sách lớp đã load đó; việc không thấy primitive trong danh sách **không có nghĩa** `isModifiableClass(int.class)` sẽ `true`.

Mẫu lọc dưới đây là **đoạn logic chạy bên trong agent đã có `Instrumentation inst`**, không phải lớp Java độc lập:

~~~java
if (!inst.isRetransformClassesSupported()) {
    System.out.println("JVM/agent does not support retransformation");
    return;
}

java.util.List<Class<?>> accepted = new java.util.ArrayList<>();
for (Class<?> candidate : inst.getAllLoadedClasses()) {
    if (candidate == null) {
        continue;
    }
    if (candidate.isPrimitive() || candidate.isArray()) {
        continue;
    }
    if (!inst.isModifiableClass(candidate)) {
        continue;
    }

    // Những điều kiện lọc mục tiêu thực tế nên đặt ở đây:
    // package, class loader, tên lớp, phạm vi ứng dụng...
    accepted.add(candidate);
}

System.out.println("Candidates allowed by preflight: "
        + accepted.size());
~~~

Ý nghĩa:

1. Check capability của thao tác **trước khi** chuẩn bị retransformation.
2. Loại các kiểu đặc biệt được contract bảo đảm không thể sửa.
3. Vẫn kiểm tra `isModifiableClass` cho **mọi** class còn lại, vì JVM có thể có những lớp không thể sửa khác.
4. Lọc thêm **phạm vi ứng dụng**: chỉ nên chọn class cần theo dõi, tránh chạm toàn bộ runtime.
5. Nếu cần retransform thật, đăng ký transformer phù hợp, sau đó mới gọi `inst.retransformClasses(...)` trên danh sách đã chọn và xử lý lỗi. Ví dụ trên chỉ **đếm ứng viên**, chưa retransform bất kỳ lớp nào.

Không phải cứ lọc `isHidden()` và `isArray()` là đủ; ngay cả lớp thông thường cũng có thể bị JVM đánh dấu không thể sửa. Ngược lại, không cần đoán trước bằng tên package rằng lớp nào tuyệt đối không thể sửa: dùng kết quả runtime để quyết định.

## 7. Thêm rào cản: một class modifiable vẫn có thể sửa không thành công

Giả sử `inst.isModifiableClass(MyService.class)` trả `true` và capability retransformation cũng là `true`. Việc thay bytecode vẫn có thể thất bại nếu biến đổi vi phạm hợp đồng JVM TI.

### 7.1. Retransformation và redefinition là hai thao tác khác nhau

| Thao tác | API | Vai trò |
| --- | --- | --- |
| Retransformation | `retransformClasses(Class<?>...)` | Chạy lại chuỗi transformer trên class đã load, theo quy tắc tái sử dụng/áp dụng biến đổi hiện có |
| Redefinition | `redefineClasses(ClassDefinition...)` | Cấp bytecode class mới để thay thế định nghĩa của class đã load |
| Load-time transformation | `addTransformer(...)` | Có thể xử lý bytecode lúc JVM **định nghĩa một class mới**, trước khi class được tạo |

Primitive và array class không phải những class thường có file bytecode gửi vào cơ chế redefinition/retransformation; **không có cách hợp lệ để dùng `redefineClasses` nhằm “thêm method vào `int[].class`”**.

Cần lưu ý load-time transformation và retransform/redefine **không phải cùng một phép kiểm tra**. `isModifiableClass` mô tả khả năng sửa class **đã tồn tại** qua retransform hoặc redefine; nó không phải một nút tắt chung cho mọi transformer lúc class load.

### 7.2. Không được tự ý đổi cấu trúc class

Theo JVM TI của Java 21, các giới hạn thông dụng đối với retransformation/redefinition bao gồm:

- Có thể thay **method bodies**, constant pool và các attributes trong giới hạn được cho phép.
- Không được thêm, xóa, đổi tên field/method; không thay method signature, modifiers hoặc quan hệ kế thừa.
- Không được thay các thuộc tính `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`.
- Bytecode kết quả vẫn phải đúng định dạng và được JVM xác minh; các lệnh và stack frames phải tương thích.

Ví dụ, muốn thêm log vào **body** của `OrderService.process()` có thể là một mục tiêu hợp lệ nếu class modifiable và transformer tạo bytecode hợp lệ. Muốn thêm hẳn field `private int counter;` vào class **đang load** qua retransform là thay đổi cấu trúc không được phép trong giới hạn trên; dù `isModifiableClass(OrderService.class)` đã trả `true`.

Nếu một method đang có frame thực thi, thay đổi redefinition không nhất thiết đổi bytecode của frame đó ngay; các lời gọi mới dùng version mới theo quy tắc JVM. Việc redefine class cũng không tự chạy lại static initializer. Những vấn đề này khác với câu hỏi modifiability.

## 8. Ngoại lệ và quy trình chẩn đoán

| Quan sát hoặc lỗi | Nguyên nhân có thể | Bước xử lý |
| --- | --- | --- |
| `isModifiableClass(int.class) == false` | Primitive luôn không thể sửa | Instrument class chứa thao tác dùng `int` |
| `isModifiableClass(String[].class) == false` | Array class luôn không thể sửa | Instrument nơi tạo/đọc/ghi mảng |
| `isModifiableClass(SomeClass.class) == false` | JVM đánh dấu class không thể sửa | Loại khỏi danh sách; tìm điểm instrument khác |
| `isModifiableClass(null)` ném `NullPointerException` | Đầu vào là `null` | Kiểm tra input trước khi gọi |
| `isRetransformClassesSupported() == false` | Capability của JVM/agent không có | Xem manifest, JVM implementation, chiến lược load-time |
| `UnmodifiableClassException` | Một class được yêu cầu sửa là không thể sửa | Kiểm tra từng target với `isModifiableClass` |
| `UnsupportedOperationException` | Capability thiếu hoặc thay đổi vượt giới hạn cho phép | Xem cờ capability và thay đổi cấu trúc class |
| `ClassFormatError` | Class bytes không đúng định dạng | Kiểm tra output của transformer/bytecode generator |
| `NoClassDefFoundError` trong redefine/retransform | Tên class trong bytecode không khớp class cần sửa | Giữ đúng internal name và định nghĩa mục tiêu |
| `isModifiableClass == true` nhưng transformer không thay đổi gì | Transformer trả `null`, không đăng ký phù hợp hoặc không được gọi trong bước hiện tại | Kiểm tra logic transformer, `canRetransform`, thời điểm load/retransform |

Khi gọi `retransformClasses` hoặc `redefineClasses` cho nhiều class và một class không thể sửa, phương thức sẽ ném ngoại lệ theo hợp đồng; nếu một lần gọi retransform/redefine thất bại thì không có class nào **trong lần gọi đó** được thay thành công. Cần bảo đảm danh sách mục tiêu hợp lệ trước khi gọi, đồng thời vẫn chuẩn bị xử lý lỗi vì lớp/cấu hình và trạng thái runtime có thể thay đổi.

**Không dùng kết quả `isModifiableClass` như một giấy phép sửa bất kỳ class nào.** Nó chỉ là một phép kiểm tra kỹ thuật về tính modifiable của target; việc có nên instrument lớp lõi, lớp security-sensitive hoặc lớp từ thư viện bên thứ ba còn phụ thuộc mục đích, tính tương thích và khả năng kiểm thử.

## 9. Sơ đồ quyết định chọn mục tiêu

~~~text
Có Class<?> target?
    |
    +-- null -----------------> Bỏ qua / báo input không hợp lệ
    |
    +-- target.isPrimitive() -> Không thể sửa class primitive
    |
    +-- target.isArray() ----> Không thể sửa class mảng
    |
    v
inst.isModifiableClass(target)?
    |
    +-- false ---------------> Loại; có thể là hidden/VM-defined...
    |
    +-- true ----------------> Kiểm tra capability theo thao tác
                                  |
                                  v
                            Chọn transformer/bytecode hợp lệ
                                  |
                                  v
                            Chỉ sửa class nằm trong phạm vi
                                  |
                                  v
                            Thực hiện, xử lý lỗi, đo kết quả
~~~

Điểm chốt là chọn đúng **class chứa bytecode muốn quan sát**. Khi mục tiêu là số nguyên hoặc mảng, thường phải instrument phương thức thao tác trên dữ liệu đó; `int.class` hay `String[].class` không phải đối tượng cần đưa vào danh sách retransformation.

## 10. Bài tập tự kiểm tra

**Câu 1.** `Integer.TYPE` và `Integer.class` có phải cùng một `Class<?>` không? Cái nào chắc chắn không modifiable?

**Câu 2.** `String.class` trên một JVM trả `isModifiableClass == true`. Từ đó suy ra `String[].class` cũng modifiable được không?

**Câu 3.** `inst.isModifiableClass(MyService.class) == true` nhưng `inst.isRetransformClassesSupported() == false`. Có thể gọi `retransformClasses(MyService.class)` thành công không?

**Câu 4.** Khi muốn thêm kiểm tra trước thao tác `values[i] = 10` trong method Java đang load, nên sửa `int[].class` hay class khai báo method chứa lệnh `iastore`?

**Câu 5.** Một class đánh dấu `final` hoặc `record` có mặc nhiên không thể retransform không? Nếu muốn thêm field mới qua retransform khi class đã load thì sao?

**Câu 6.** Vì sao đoạn code sau có thể sai ngay cả khi danh sách chứa đầy đủ class JVM đang load?

~~~java
inst.retransformClasses(inst.getAllLoadedClasses());
~~~

**Đáp án:**

1. Khác nhau. `Integer.TYPE == int.class`, là primitive class và **chắc chắn không thể sửa**; `Integer.class` là wrapper class, phải hỏi `isModifiableClass`.
2. **Không.** `String[].class` là array class nên kết quả luôn `false`.
3. **Không.** Phải có capability retransformation; boolean modifiability riêng của class chưa đủ.
4. Instrument **class chứa method** dùng lệnh `iastore`, sau khi kiểm tra điều kiện; không sửa array class.
5. `final`/`record` không tự động đồng nghĩa `false`. Dù class modifiable, **thêm field mới** vào class đã load là thay đổi cấu trúc vượt giới hạn retransform/redefine nêu trên.
6. `getAllLoadedClasses()` có thể chứa array/hidden classes và nhiều class không modifiable; đồng thời capability có thể thiếu, phạm vi quá rộng và bytecode chưa bảo đảm an toàn. Cần lọc và chọn mục tiêu trước khi thao tác.

## 11. Nguồn kỹ thuật chính thức

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hợp đồng `isModifiableClass`, `isRetransformClassesSupported`, `isRedefineClassesSupported`, `getAllLoadedClasses` và ngoại lệ.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `Class.isPrimitive()`, `Class.isArray()`, `Class.isHidden()`, `Class.getTypeName()`.
- [Java SE 21 — JVM Tool Interface, Is Modifiable Class](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#IsModifiableClass): primitive/array và các lớp implementation-defined không thể sửa.
- [Java SE 21 — JVM TI Retransform Classes / Redefine Classes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): những thay đổi cấu trúc và bytecode được JVM cho phép.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): cơ chế biến đổi bytecode lúc load, redefine, retransform.
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): thiết kế hidden classes và giới hạn của instrumentation khi class đã load.
