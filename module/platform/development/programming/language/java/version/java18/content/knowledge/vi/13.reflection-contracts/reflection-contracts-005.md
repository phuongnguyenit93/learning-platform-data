# Type erasure, bridge method và synthetic method khi nhận diện chữ ký thực thi

## 1. Mục tiêu bài học

Khi dùng Java Reflection để quét method, bạn có thể thấy nhiều method hơn số method đã viết trong source. Một phương thức `accept(String)` có thể đi kèm `accept(Object)`; một phương thức `Integer value()` có thể đi kèm `Number value()`, dù trong class con bạn chỉ khai báo một phương thức. Các method bổ sung này thường xuất hiện để bảo toàn hợp đồng override khi Java compiler chuyển từ kiểu generic sang bytecode JVM.

Bài học thuộc chương **Hợp đồng reflection** của module `JAVA_VERSION_JAVA18`. Module tìm hiểu những kiến thức từ Java 18 còn hữu ích trên JDK hiện đại, bao gồm kiểm chứng hợp đồng Reflection và MethodHandle. Các khái niệm `type erasure`, `bridge method` và `synthetic method` là hợp đồng ngôn ngữ, JVM và Reflection vẫn áp dụng hiện nay; chúng không phải tính năng tạm thời hoặc cơ chế cũ cần loại bỏ.

Sau bài học, bạn sẽ:

- Phân biệt chữ ký phương thức trong Java source, kiểu đã erasure và method descriptor của JVM.
- Dự đoán kiểu tham số, kiểu trả về tại runtime sau type erasure.
- Giải thích tại sao compiler tạo bridge method để bảo đảm override và dynamic dispatch.
- Đọc đúng `Method.isBridge()`, `Method.isSynthetic()`, `getParameterTypes()` và `getGenericParameterTypes()`.
- Nhận diện method nguồn, method bridge và các synthetic method khác trong kết quả Reflection.
- Thiết kế bộ quét API tránh đếm bridge hai lần, đồng thời không làm sai hợp đồng khi cần phân tích bytecode.
- Kiểm chứng dự đoán bằng `javac`, `java` và `javap` trên JDK đang sử dụng.

## 2. Ba lớp thông tin dễ bị nhầm

Khi nói đến “chữ ký phương thức”, cần xác định đang xét tầng nào:

| Tầng | Đối tượng quan sát | Đặc điểm |
| --- | --- | --- |
| Java source | Tên method và kiểu tham số của khai báo | Chữ ký Java **không** dùng kiểu trả về để phân biệt overload. |
| Kiểu sau erasure | Kiểu đã xóa type argument và thay type variable bằng erasure của bound | Quyết định nhiều kiểu tham số/return thấy ở bytecode và Reflection. |
| JVM method descriptor | Danh sách kiểu tham số **và kiểu trả về** ở bytecode | Cho phép JVM phân biệt những method cùng tên, cùng tham số nhưng khác return type. |

Ví dụ source:

~~~java
interface Converter<T> {
    T convert(T input);
}
~~~

Với type variable `T` không có bound tường minh, erasure của `T` là `Object`. Vì vậy method descriptor sau khi biên dịch tương ứng:

~~~text
convert(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Ký hiệu descriptor dùng:

- `L...;` cho kiểu tham chiếu, ví dụ `Ljava/lang/Object;`.
- `(...)` cho danh sách tham số theo thứ tự.
- Phần sau `)` cho kiểu trả về.
- `V` cho `void`, `I` cho `int`, và các ký hiệu JVM tương ứng.

Điểm mấu chốt: hai method có thể **không thể khai báo cùng nhau trong một class Java source** nếu chỉ khác kiểu trả về, nhưng **có thể cùng xuất hiện trong class file** khi compiler sinh bridge method.

## 3. Type erasure thay đổi những gì?

Type erasure là phép ánh xạ kiểu generic về kiểu có thể biểu diễn ở runtime. Một số quy tắc quan trọng theo JLS mục 4.6:

| Khai báo trong Java | Erasure | Diễn giải |
| --- | --- | --- |
| `List<String>` | `List` | Type argument `String` không nằm trong runtime parameter Class. |
| `Map<String, Integer>` | `Map` | Các type argument không phân biệt runtime class. |
| `T` (không bound) | `Object` | Bound ngầm định là `Object`. |
| `T extends Number` | `Number` | Erasure bằng bound đầu tiên. |
| `T extends Number & Comparable<T>` | `Number` | Dùng erasure của **leftmost bound**. |
| `T[]` với `T extends Number` | `Number[]` | Erasure áp dụng cho kiểu phần tử mảng. |

Ví dụ:

~~~java
class NumberBox<T extends Number & Comparable<T>> {
    public T normalize(T value) {
        return value;
    }
}
~~~

Method `normalize` có tham số đã erasure là `Number` và return type đã erasure cũng là `Number`. Trong Reflection:

~~~java
Method method = NumberBox.class.getDeclaredMethod("normalize", Number.class);

System.out.println(method.getParameterTypes()[0]);        // class java.lang.Number
System.out.println(method.getReturnType());               // class java.lang.Number
System.out.println(method.getGenericParameterTypes()[0]); // T
~~~

Nếu chỉ thử `getDeclaredMethod("normalize", Integer.class)`, kết quả là `NoSuchMethodException`: `Integer` là một giá trị có thể dùng với một phiên bản generic phù hợp, nhưng **không phải** kiểu tham số runtime của khai báo đã erasure.

### Không thể overload chỉ khác type argument

Đoạn sau không hợp lệ:

~~~java
class InvalidOverloads {
    void save(java.util.List<String> values) {
    }

    void save(java.util.List<Integer> values) {
    }
}
~~~

Cả hai method đều có erasure của tham số là `List`, nên gây **name clash** khi biên dịch. Kiểu `List<String>` và `List<Integer>` không thể dùng để phân biệt hai overload này tại JVM.

Từ kết luận trên, khi Reflection tìm method bằng `Class.getDeclaredMethod(name, parameterTypes)`, hãy truyền các `Class<?>` thực tế sau erasure. Không có `List<String>.class` để dùng làm tham số tra cứu.

## 4. Vì sao Java compiler tạo bridge method?

Xét interface generic:

~~~java
interface Receiver<T> {
    T echo(T input);
}
~~~

Và lớp triển khai:

~~~java
final class StringReceiver implements Receiver<String> {
    @Override
    public String echo(String input) {
        return input.trim();
    }
}
~~~

Ở mức Java source, `StringReceiver.echo(String)` triển khai `Receiver<String>.echo(String)` hợp lệ. Nhưng khi xét descriptor đã erasure:

~~~text
Receiver.echo(Object) : Object
StringReceiver.echo(String) : String
~~~

Hai descriptor này khác nhau. Nếu bytecode chỉ chứa `StringReceiver.echo(String)`, lời gọi từ một biến có kiểu `Receiver<String>` sẽ không tìm được implementation với descriptor `echo(Object):Object` theo hợp đồng JVM.

Compiler tạo một method trung gian (*bridge*) tương đương về mặt ý tưởng với:

~~~java
// Minh họa hành vi ở mức bytecode; không viết thủ công cùng class nguồn.
public Object echo(Object input) {
    return echo((String) input);
}
~~~

Bridge nhận `Object` theo descriptor của interface đã erasure, ép kiểu rồi gọi implementation `echo(String)`. Nhờ đó, dynamic dispatch vẫn hoạt động:

~~~java
Receiver<String> receiver = new StringReceiver();
System.out.println(receiver.echo("  hello  ")); // hello
~~~

Method bridge là cách compiler bắc cầu giữa hợp đồng **ngôn ngữ Java với generic** và hợp đồng **method descriptor tại JVM**. Bạn không cần gọi nó trực tiếp trong mã ứng dụng bình thường, nhưng Reflection và công cụ bytecode có thể quan sát được nó.

### Bridge cũng có thể do covariant return

Bridge không chỉ xuất hiện vì generic. Ví dụ:

~~~java
class BaseValue {
    public Number value() {
        return 1;
    }
}

class IntegerValue extends BaseValue {
    @Override
    public Integer value() {
        return 2;
    }
}
~~~

Java cho phép kiểu trả về `Integer` hẹp hơn `Number` khi override. JVM method descriptor có return type; compiler có thể tạo bridge `Number value()` để duy trì lời gọi đến method với return type gốc, song song với `Integer value()`.

Vì vậy, **`isBridge()` không có nghĩa method nhất định bắt nguồn từ một khai báo generic**. Nó mô tả vai trò kết nối giữa hai chữ ký mà compiler cần duy trì.

## 5. Chương trình Reflection kiểm chứng bridge

Tạo file `BridgeInspector.java`:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public class BridgeInspector {
    interface Receiver<T> {
        T echo(T input);
    }

    static final class StringReceiver implements Receiver<String> {
        @Override
        public String echo(String input) {
            return input.trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Method[] methods = StringReceiver.class.getDeclaredMethods();

        // Không giả định thứ tự do getDeclaredMethods() trả về.
        Arrays.sort(methods, Comparator
                .comparing(Method::getName)
                .thenComparing(m -> Arrays.toString(m.getParameterTypes()))
                .thenComparing(m -> m.getReturnType().getName()));

        for (Method method : methods) {
            if (!method.getName().equals("echo")) {
                continue;
            }

            System.out.printf(
                    "%s %s(%s) bridge=%s synthetic=%s%n",
                    method.getReturnType().getSimpleName(),
                    method.getName(),
                    Arrays.toString(method.getParameterTypes()),
                    method.isBridge(),
                    method.isSynthetic());
        }

        Method interfaceMethod =
                Receiver.class.getDeclaredMethod("echo", Object.class);
        System.out.println(
                "Interface raw parameter: "
                        + interfaceMethod.getParameterTypes()[0].getTypeName());
        System.out.println(
                "Interface generic parameter: "
                        + interfaceMethod.getGenericParameterTypes()[0].getTypeName());

        Method bridge =
                StringReceiver.class.getDeclaredMethod("echo", Object.class);
        Method implementation =
                StringReceiver.class.getDeclaredMethod("echo", String.class);

        System.out.println("Bridge found: " + bridge.isBridge());
        System.out.println("Source method found: " + !implementation.isBridge());

        Receiver<String> receiver = new StringReceiver();
        System.out.println(receiver.echo("  xin chào  "));
    }
}
~~~

Biên dịch và chạy trên JDK đang sử dụng:

~~~sh
javac BridgeInspector.java
java BridgeInspector
~~~

Một kết quả điển hình với `javac`:

~~~text
Object echo([class java.lang.Object]) bridge=true synthetic=true
String echo([class java.lang.String]) bridge=false synthetic=false
Interface raw parameter: java.lang.Object
Interface generic parameter: T
Bridge found: true
Source method found: true
xin chào
~~~

Ở đây cần chú ý:

1. Trong source `StringReceiver` chỉ có một khai báo `echo(String)`.
2. `getDeclaredMethods()` vẫn thấy cả `echo(Object)` vì class file có bridge do compiler tạo.
3. `Receiver.echo(T)` có raw parameter `Object` nhưng metadata generic mô tả nó bằng type variable `T`.
4. `getDeclaredMethod("echo", Object.class)` trả về bridge; `getDeclaredMethod("echo", String.class)` trả về implementation.
5. Thứ tự method do Reflection trả về **không được bảo đảm**; chương trình sắp xếp để kết quả dễ đọc.

Đây là đầu ra minh họa từ `javac`; khi làm công cụ phân tích nhiều compiler hoặc nguồn bytecode khác Java, hãy kiểm tra flags thực tế thay vì giả định số lượng method sinh ra luôn giống nhau.

## 6. Đọc đúng các API trên Method

Các API liên quan vẫn là nền tảng của Reflection trên JDK hiện đại:

| API | Thông tin cung cấp | Cách hiểu đúng |
| --- | --- | --- |
| `getName()` | Tên method | Chưa đủ để xác định duy nhất một method. |
| `getParameterTypes()` | `Class<?>[]` của tham số runtime | Dựa trên kiểu ở descriptor; generic type argument đã bị erasure. |
| `getReturnType()` | `Class<?>` của return type runtime | Cần xét khi phân biệt các method cùng tên/tham số ở JVM. |
| `getGenericParameterTypes()` | `Type[]` mô tả khai báo generic | Có thể trả `TypeVariable`, `ParameterizedType` hoặc `Class`. |
| `getGenericReturnType()` | `Type` mô tả return type generic | Không đồng nghĩa kết quả đã thay thế theo kiểu cụ thể của receiver. |
| `isBridge()` | Phương thức bridge hay không | Nhận diện method trung gian compiler tạo để bảo toàn override. |
| `isSynthetic()` | Phương thức synthetic hay không | Nhận diện phần tử do compiler/công cụ tạo, không tương ứng trực tiếp với khai báo source theo định nghĩa metadata. |
| `getDeclaringClass()` | Class/interface khai báo method | Quan trọng khi phân biệt phương thức khai báo và kế thừa. |
| `toGenericString()` | Mô tả method gồm type parameter nếu có | Phù hợp chẩn đoán, không dùng như khóa nhị phân ổn định. |

Ví dụ phân biệt `Class` và `Type` khi tham số là generic:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.util.List;

class ListApi {
    public void handle(List<String> values) {
    }

    public static void inspect() throws ReflectiveOperationException {
        Method method = ListApi.class.getDeclaredMethod("handle", List.class);

        Class<?> raw = method.getParameterTypes()[0];
        Type generic = method.getGenericParameterTypes()[0];

        System.out.println(raw.getTypeName());     // java.util.List
        System.out.println(generic.getTypeName()); // java.util.List<java.lang.String>
    }
}
~~~

Generic metadata có thể được lưu trong thuộc tính `Signature` của class file và được các API generic Reflection đọc lại. Điều đó **không có nghĩa JVM tạo một runtime class riêng cho `List<String>`**. Nếu metadata generic bị thiếu hoặc không đọc được, công cụ cần xử lý theo khả năng thực tế của class file thay vì suy đoán type argument.

### Một bẫy khác: generic của lớp cha không tự biến thành method cụ thể

Nếu Reflection đọc trực tiếp method khai báo trong `Receiver`:

~~~java
Method method = Receiver.class.getDeclaredMethod("echo", Object.class);
System.out.println(method.getGenericReturnType().getTypeName()); // T
~~~

Bạn vẫn nhận `T`, không tự động nhận `String` chỉ vì đang dùng `StringReceiver`. Muốn suy ra type argument của một quan hệ kế thừa cụ thể, cần phân tích generic superclass/interface qua `getGenericSuperclass()`, `getGenericInterfaces()` và các đối tượng `Type` tương ứng. Đây là một bước **type-variable resolution** riêng, không nằm trong `Method.getReturnType()`.

## 7. Bridge và synthetic khác nhau thế nào?

Hai cờ này trả lời hai câu hỏi khác nhau:

- `isBridge()`: method có được đánh dấu là **bridge** ở JVM hay không?
- `isSynthetic()`: method có được đánh dấu là **synthetic** hay không?

Với bridge do `javac` tạo trong ví dụ trên, cả hai thường là `true`. Tuy nhiên, một synthetic method không nhất thiết là bridge; compiler có thể tạo synthetic method cho những mục đích triển khai khác.

| `isBridge()` | `isSynthetic()` | Cách diễn giải thực tế |
| --- | --- | --- |
| `false` | `false` | Thường là method khai báo hoặc method được công cụ tạo mà không gắn synthetic flag. Không thể suy ra chắc chắn nó từng được viết trong source. |
| `true` | `true` | Trường hợp thường gặp của bridge do compiler Java tạo. |
| `false` | `true` | Synthetic method không phải bridge, ví dụ method hỗ trợ triển khai do compiler tạo. |
| `true` | `false` | Không phải hình mẫu thông thường của bridge do `javac` tạo; công cụ phân tích bytecode nên đọc các flag thực tế thay vì tự suy diễn. |

Một số chi tiết cần tránh hiểu sai:

- `isSynthetic() == false` **không chứng minh** chắc chắn method có một khai báo viết tay trong source. Ngôn ngữ và compiler có thể có các khai báo ngầm định khác.
- `isBridge() == true` **không chứng minh** class đang dùng generic; covariant return cũng có thể dẫn tới bridge.
- `isSynthetic() == true` không tự nói method có an toàn để bỏ qua khi gọi ở runtime hay không.
- Một method synthetic có thể có tên do compiler quy định; không nên dựa vào tiền tố tên như `lambda$` làm bộ lọc duy nhất.

Nếu mục tiêu là trình bày API mà lập trình viên chủ động khai báo, có thể lọc bridge và synthetic. Nếu mục tiêu là phản ánh chính xác class file, tìm đường dispatch hoặc chẩn đoán lỗi runtime, cần giữ chúng và hiển thị rõ các flag.

## 8. Covariant return và getDeclaredMethod không có tham số return type

Với ví dụ `IntegerValue` ở phần trước:

~~~java
Method[] all = IntegerValue.class.getDeclaredMethods();

for (Method method : all) {
    if (method.getName().equals("value")) {
        System.out.printf(
                "%s value() bridge=%s synthetic=%s%n",
                method.getReturnType().getSimpleName(),
                method.isBridge(),
                method.isSynthetic());
    }
}
~~~

Một bản build với `javac` thường chứa:

~~~text
Integer value() bridge=false synthetic=false
Number value() bridge=true synthetic=true
~~~

Cả hai method có tên `value` và không có tham số; khác nhau ở kiểu trả về. API `getDeclaredMethod("value")` **không cho truyền return type**. Theo hợp đồng `Class.getDeclaredMethod`, nếu có nhiều method cùng tên/tham số, nó chọn method có return type cụ thể hơn các method còn lại; nếu không xác định được lựa chọn duy nhất theo quy tắc đó, kết quả có thể được chọn tùy ý.

Vì vậy, để kiểm kê đúng mọi method của class file hoặc tìm descriptor cụ thể:

1. Gọi `getDeclaredMethods()`.
2. Lọc theo tên và danh sách tham số.
3. Xét thêm `getReturnType()`, `isBridge()` và `isSynthetic()`.
4. Không dùng thứ tự array hoặc chuỗi `toString()` làm định danh duy nhất.

Lưu ý rằng `getDeclaredMethods()` chỉ liệt kê method **khai báo bởi class/interface đó**, không tự thêm method kế thừa. `getMethods()` là phép liệt kê public method rộng hơn, gồm thành viên kế thừa theo quy tắc Reflection; hai API không thể thay thế nhau khi xây danh sách contract.

## 9. Chữ ký Java khác khóa nhận diện method trong công cụ runtime

Một bộ quét API phục vụ tài liệu có thể muốn gom mỗi method theo ý nghĩa khai báo trong Java source. Nhưng công cụ bytecode, proxy hoặc instrumentation có thể cần phân biệt những entry JVM cùng tên và tham số nhưng khác return type.

Ví dụ hai cách xây khóa:

| Bài toán | Thông tin nên xét |
| --- | --- |
| Phân nhóm overload theo Java source | Tên và kiểu tham số; sau đó xử lý bridge/override riêng. |
| Nhận diện duy nhất entry khai báo ở một class file | Declaring class, tên, danh sách tham số runtime và return type. |
| Hiển thị API cho người sử dụng | Giữ method không bridge/synthetic theo chính sách rõ ràng, xử lý kế thừa và quyền truy cập. |
| Điều tra lỗi dispatch hoặc binary compatibility | Giữ cả bridge, synthetic và thông tin descriptor. |

Vì JVM tính cả return type trong method descriptor, **không nên gộp hai method chỉ vì cùng tên và cùng parameter array** khi đang phân tích class file. Mặt khác, không nên hiển thị bridge như một overload độc lập do người viết API chủ động công bố.

### Ví dụ bộ lọc cho danh sách method khai báo

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public final class ApiMethodScanner {
    private ApiMethodScanner() {
    }

    public static List<Method> visibleDeclaredMethods(Class<?> type) {
        return Arrays.stream(type.getDeclaredMethods())
                .filter(method -> !method.isBridge())
                .filter(method -> !method.isSynthetic())
                .sorted(Comparator
                        .comparing(Method::getName)
                        .thenComparing(method ->
                                Arrays.toString(method.getParameterTypes()))
                        .thenComparing(method ->
                                method.getReturnType().getName()))
                .toList();
    }
}
~~~

Bộ lọc này là **chính sách trình bày** nhằm bỏ các method compiler-generated thường thấy. Nó không tái dựng source tuyệt đối, không tự giải quyết override hoặc type-variable binding và không nên áp dụng cho mọi công cụ. Với framework cần gọi bridge theo descriptor đã erasure hoặc công cụ phân tích bytecode, hãy giữ bridge trong tập dữ liệu.

## 10. Tìm chính xác method khi generic đã erasure

Giả sử có:

~~~java
class UserListApi {
    public void process(java.util.List<String> users) {
    }
}
~~~

Tra cứu đúng:

~~~java
Method method = UserListApi.class.getDeclaredMethod(
        "process", java.util.List.class);
~~~

Không thể viết kiểu như `List<String>.class`. Method lookup bằng Reflection yêu cầu `Class<?>...` của kiểu tham số runtime.

Tương tự:

~~~java
class BoundedApi<T extends Number> {
    public T scale(T value) {
        return value;
    }
}
~~~

Tra cứu đúng là:

~~~java
Method method = BoundedApi.class.getDeclaredMethod("scale", Number.class);
~~~

Đây là hậu quả trực tiếp của erasure: `T extends Number` biến thành `Number` ở tham số và return type runtime.

### Cần chú ý phương thức generic và overload

Nếu quét nhiều method tên giống nhau, hãy so sánh toàn bộ danh sách `getParameterTypes()` theo thứ tự. Số lượng tham số, kiểu nguyên thủy/boxed, mảng và varargs đều ảnh hưởng đến nhận diện method. Varargs cũng là một dạng mảng ở descriptor; `Method.isVarArgs()` cho biết method được khai báo với cú pháp biến số đối số.

Đừng cố tìm overload theo tên rồi lấy “method đầu tiên” từ `getDeclaredMethods()`. API không hứa thứ tự của array, và bridge có thể khiến tên xuất hiện nhiều lần.

## 11. Xem trực tiếp descriptor và các JVM flags bằng javap

Reflection là cách nhìn ở runtime; `javap` giúp đối chiếu class file sau biên dịch.

Sau khi biên dịch `BridgeInspector.java`:

~~~sh
javac BridgeInspector.java
javap -p -v 'BridgeInspector$StringReceiver'
~~~

Tên nhị phân của nested class có ký tự `$`; dấu nháy đơn trong lệnh giúp shell không coi ký tự này là phép mở rộng biến. Trên Windows PowerShell cũng có thể dùng chuỗi trong dấu nháy đơn.

Trong output `javap -v`, hãy tìm hai bản `echo`:

~~~text
public java.lang.String echo(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

public java.lang.Object echo(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: ... ACC_BRIDGE, ACC_SYNTHETIC ...
~~~

Ngoài descriptor, `javap` còn có thể hiển thị thuộc tính `Signature` cho thông tin generic khai báo. Lưu ý `Signature` mô tả generic metadata; descriptor mới là mô tả kiểu đầu vào/đầu ra ở JVM.

Không cần hard-code toàn bộ danh sách flags hoặc số dòng output của `javap`: những chi tiết trình bày có thể khác theo compiler/JDK. Hãy đối chiếu thông tin cốt lõi: descriptor, `ACC_BRIDGE`, `ACC_SYNTHETIC` và method thật được bridge gọi.

## 12. Ví dụ lỗi ClassCastException qua bridge

Bridge có thể thực hiện cast để chuyển từ erased type sang kiểu cụ thể của implementation. Nếu caller dùng raw type và đưa giá trị sai, lỗi có thể nổ **trong bridge**:

~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
static void demonstrateUnsafeRawCall() {
    BridgeInspector.Receiver raw =
            new BridgeInspector.StringReceiver();

    raw.echo(42); // Có thể ném ClassCastException ở bridge.
}
~~~

Đây là ví dụ cố ý sử dụng raw type không an toàn để giải thích hành vi, **không phải cách viết nên áp dụng**. Với `Receiver<String>` bình thường, compiler Java kiểm tra kiểu đối số và không cho truyền `Integer`.

Stack trace có thể nhắc tới method cùng tên mà bạn không tìm thấy trong source. Khi đó, kiểm tra `isBridge()` hoặc `javap` để xác định method trung gian thực tế. Việc bridge ném `ClassCastException` ở tình huống raw type không phải lỗi compiler: đó là hệ quả của lời gọi vi phạm hợp đồng kiểu.

## 13. Kiểm thử hợp đồng Reflection thay vì kiểm tra tên method

Một bài test Reflection cho ví dụ `BridgeInspector` có thể kiểm chứng:

~~~java
Method raw = BridgeInspector.StringReceiver.class
        .getDeclaredMethod("echo", Object.class);
Method specific = BridgeInspector.StringReceiver.class
        .getDeclaredMethod("echo", String.class);

if (!raw.isBridge() || !raw.isSynthetic()) {
    throw new AssertionError("Missing expected javac bridge flags");
}
if (specific.isBridge()) {
    throw new AssertionError("Implementation must not be a bridge");
}
if (raw.getReturnType() != Object.class) {
    throw new AssertionError("Wrong erased return type");
}
if (specific.getReturnType() != String.class) {
    throw new AssertionError("Wrong implementation return type");
}

Method declaration = BridgeInspector.Receiver.class
        .getDeclaredMethod("echo", Object.class);
if (!declaration.getGenericReturnType().getTypeName().equals("T")) {
    throw new AssertionError("Expected generic type variable T");
}
~~~

Đây là test dành cho ví dụ biên dịch bằng `javac` như bài đã mô tả. Với framework xử lý class file từ nhiều ngôn ngữ/compiler, tiêu chí test cần được điều chỉnh theo mục tiêu: phân tích JVM descriptor/flags hay trình bày API ở mức Java source.

Nên phân biệt ba nhóm kiểm thử:

| Cần kiểm chứng | Phương pháp |
| --- | --- |
| Generic source contract | Biên dịch Java source và kiểm tra compiler từ chối name clash không hợp lệ. |
| Reflection contract | Gọi `getDeclaredMethods()`, kiểm tra raw/generic types và bridge/synthetic flags. |
| Runtime dispatch | Gọi qua interface/parent type; xác nhận implementation phù hợp được chạy. |

Nếu cần quan sát class file, dùng `javap -v -p` như một bước xác minh thủ công hoặc trong môi trường kiểm thử phù hợp.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `getDeclaredMethods()` trả nhiều method cùng tên hơn source. | Có bridge/synthetic method được compiler tạo. | Đọc `isBridge()`, `isSynthetic()`, parameter và return types. |
| Không tìm được `process(List<String>)`. | Reflection tra cứu theo raw/erased `Class`. | Dùng `List.class`. |
| Không tìm được `echo(String)` trên interface `Receiver<T>`. | Khai báo interface đã erasure thành `echo(Object)`. | Tra cứu `Object.class` trên interface; tra cứu `String.class` trên implementation. |
| Trình tạo API docs hiển thị hai overload gây hiểu nhầm. | Bridge bị liệt kê như method người dùng viết. | Lọc bridge trong lớp trình bày, giữ raw dữ liệu cho chẩn đoán. |
| So sánh method chỉ theo tên và tham số bỏ sót một entry. | Có thể có cùng tên/tham số nhưng khác return ở JVM. | Xét `getReturnType()` khi cần định danh bytecode. |
| `isSynthetic()` là true nhưng `isBridge()` false. | Synthetic phục vụ mục đích khác bridge. | Dùng đúng flag; không suy diễn mọi synthetic đều là bridge. |
| `getGenericReturnType()` trả `T`, không trả `String`. | Method được đọc từ khai báo generic gốc. | Phân tích thêm generic supertype của concrete class nếu cần binding. |
| Lấy method đầu tiên từ array để chọn overload. | Thứ tự của `getDeclaredMethods()` không xác định. | Lọc đầy đủ chữ ký và sắp xếp nếu cần hiển thị ổn định. |
| Raw type gọi method rồi nhận `ClassCastException`. | Bridge thực hiện cast về kiểu implementation. | Dùng generic type an toàn, kiểm tra cast và stack trace. |

## 15. Quy trình nhận diện chữ ký thực thi trong dự án

1. **Xác định phạm vi quét:** declared methods của một class hay toàn bộ public/inherited methods.
2. **Đọc đủ các thuộc tính:** tên, kiểu tham số runtime, kiểu trả về, declaring class, bridge và synthetic flags.
3. **Không giả định thứ tự Reflection:** sắp xếp khi tạo tài liệu hoặc snapshot test.
4. **Tách raw và generic view:** dùng `getParameterTypes()` cho lookup runtime; dùng `getGenericParameterTypes()` để diễn giải generic metadata.
5. **Giải thích type erasure:** type variable thay bằng bound đầu tiên, type argument bị xóa khỏi raw class.
6. **Nhận diện bridge:** hiểu quan hệ với overriding generic hoặc covariant return; giữ bridge khi kiểm tra dispatch.
7. **Áp dụng bộ lọc theo mục tiêu:** ẩn bridge/synthetic cho tài liệu API nếu thích hợp; giữ chúng trong phân tích class file.
8. **Đối chiếu bytecode khi mơ hồ:** dùng `javap` để xem descriptor và JVM access flags.
9. **Kiểm thử hành vi:** gọi method qua interface hoặc superclass để xác nhận dynamic dispatch đúng.
10. **Ghi rõ hợp đồng:** chỉ công bố những thông tin Reflection mà công cụ thực sự bảo đảm, không suy đoán source từ tên hoặc số lượng method.

## 16. Bài tập thực hành

### Bài tập 1: Dự đoán erasure

Với ba khai báo sau, hãy xác định `getParameterTypes()`, `getReturnType()`, rồi giải thích lý do:

~~~java
<T> T identity(T value) { return value; }

<T extends Number> T twice(T value) { return value; }

<T extends Number & Comparable<T>> T bound(T value) { return value; }
~~~

**Gợi ý:** kiểu `T` không bound thành `Object`; kiểu `T` có leftmost bound `Number` thành `Number`.

### Bài tập 2: Kiểm kê bridge

Biên dịch `BridgeInspector.java`, chạy chương trình và ghi lại từng method `echo`:

- Parameter types runtime.
- Return type runtime.
- `isBridge()` và `isSynthetic()`.
- Generic return type ở khai báo interface.

Giải thích vì sao `StringReceiver` có hai method `echo` ở bytecode dù trong source chỉ viết một.

### Bài tập 3: Covariant return

Biên dịch hai class `BaseValue` và `IntegerValue`. Dùng `getDeclaredMethods()` để tìm `value`; so sánh return type, bridge flag và synthetic flag. Giải thích vì sao trường hợp này có thể tạo bridge dù không khai báo generic.

### Bài tập 4: Thử name clash

Thử khai báo hai method `save(List<String>)` và `save(List<Integer>)` cùng class. Dự đoán lỗi compiler và giải thích bằng erasure. Sau đó đổi tên một method hoặc thay đổi kiểu tham số runtime để chương trình hợp lệ.

### Bài tập 5: Viết bộ quét API

Viết chương trình liệt kê những method khai báo của một class, sắp xếp ổn định và có tùy chọn `includeGenerated`. Khi `includeGenerated=false`, lọc bridge và synthetic; khi true, in cả raw descriptor và flags. So sánh kết quả với `javap`.

### Bài tập 6: Chẩn đoán raw type

Gọi `Receiver` qua raw type với đối số sai kiểu và quan sát stack trace. Xác định bridge có thực hiện cast hay không. Giải thích vì sao cách gọi bằng `Receiver<String>` giúp compiler ngăn lỗi này trước runtime.

**Tự kiểm:** phân biệt source signature/JVM descriptor; dự đoán đúng erasure; xác định đúng bridge/synthetic; không đếm bridge thành overload chủ động; không coi generic metadata là runtime class riêng; giữ method generated khi phân tích bytecode.

## 17. Ghi nhớ

- **Type erasure là quy tắc của Java generics:** `List<String>` có raw runtime class `List`, `T` không bound thành `Object`, `T` có bound thành leftmost bound.
- **Bridge method bảo toàn overriding/dynamic dispatch** khi kiểu sau erasure hoặc covariant return khiến descriptor của implementation khác descriptor cần đáp ứng.
- **`isBridge()` và `isSynthetic()` là hai thuộc tính khác nhau.** Bridge do `javac` tạo thường có cả hai flag; synthetic không nhất thiết là bridge.
- **`getDeclaredMethods()` có thể trả method không có trong source** và không bảo đảm thứ tự.
- **`getParameterTypes()`/`getReturnType()` mô tả kiểu runtime; `getGenericParameterTypes()`/`getGenericReturnType()` đọc thông tin khai báo generic.**
- **Chữ ký Java không dùng return type để phân biệt overload, nhưng JVM descriptor có return type.** Công cụ phân tích class file cần xét thêm kiểu trả về.
- **Không lọc bridge vô điều kiện.** Ẩn nó khi trình bày API nếu phù hợp, nhưng giữ nó khi cần phân tích bytecode, lời gọi runtime và binary compatibility.
- **Kiểm chứng bằng source, Reflection và `javap`** giúp phân biệt chính xác hợp đồng ngôn ngữ, compiler và JVM trên JDK đang sử dụng.

## Tài liệu chính thống

- [Oracle Java SE 27 — Method API: isBridge, isSynthetic, generic parameter/return types](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html).
- [Oracle Java SE 27 — Class API: getDeclaredMethods và getDeclaredMethod](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html).
- [Java Language Specification 27 — mục 4.6 Type Erasure](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html#jls-4.6).
- [Dev.java — Type Erasure và Bridge Methods](https://dev.java/learn/generics/type-erasure/).
- [Java Virtual Machine Specification 27 — Method Descriptors (mục 4.3.3)](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html#jvms-4.3.3).

