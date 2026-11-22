# 4.2 Nhận diện bridge method và tránh xử lý trùng phương thức generic

## 1. Bài toán: vì sao một phương thức Java lại hiện ra hai lần?

Khi dùng Reflection để quét `Class.getDeclaredMethods()` hoặc `Class.getMethods()`, một class dùng generic có thể xuất hiện **hai `Method` liên quan đến cùng một hành vi**, dù trong mã nguồn ta chỉ viết một phương thức override. Một phần tử là phương thức do lập trình viên khai báo; phần tử còn lại là **bridge method** do trình biên dịch tạo để giữ đúng cơ chế ghi đè và đa hình sau khi biên dịch generic.

Nếu framework quét mọi method để đăng ký endpoint, thực thi hook, sinh schema, tạo menu thao tác, hoặc xử lý annotation, nó có thể đăng ký hoặc gọi cùng hành vi hai lần. Ngược lại, nếu khử trùng bằng **tên method** hoặc **tên + số tham số**, framework có thể xóa nhầm overload hợp lệ.

Mục tiêu của bài:

1. Giải thích được mối liên hệ giữa **type erasure**, **override**, **bridge method** và **covariant return type**.
2. Nhận diện bridge bằng `Method.isBridge()` và phân biệt với `Method.isSynthetic()`.
3. Đọc đúng metadata từ `getDeclaredMethods()`, `getMethods()`, `getParameterTypes()`, `getReturnType()` và `getDeclaringClass()`.
4. Xây dựng quy trình khám phá method **không xử lý bridge như một nghiệp vụ riêng**, đồng thời giữ nguyên các overload thực sự.
5. Biết khi nào chỉ lọc bridge là đủ và khi nào phải **giải quyết bridge về method nguồn** để tra cứu annotation/chữ ký generic.

> **Điểm cốt lõi:** Bridge method là method thật trong bytecode và có thể được JVM gọi. Nó “trùng” về **ý nghĩa nghiệp vụ** với method đích mà nó chuyển tiếp đến, chứ không nhất thiết trùng chữ ký JVM hoặc trùng đối tượng `Method`.

## 2. Vì sao trình biên dịch sinh bridge method?

### 2.1. Generic bị xóa kiểu khi đi vào bytecode

Java áp dụng **type erasure**: biến kiểu không có bound, chẳng hạn `T`, được thay bằng `Object`; biến kiểu có bound thường được thay bằng bound thích hợp (ví dụ `T extends Number` được xóa thành `Number`). Trình biên dịch cũng đưa vào những phép ép kiểu cần thiết.

Xét hợp đồng:

```java
interface Transformer<T> {
    T transform(T value);
}

final class TrimTransformer implements Transformer<String> {
    @Override
    public String transform(String value) {
        return value.trim();
    }
}
```

Ở **mã nguồn**, `TrimTransformer.transform(String)` override `Transformer<String>.transform(String)`. Nhưng khi xóa kiểu, phương thức của interface mang dạng tương đương `Object transform(Object)`, còn method class con viết vẫn là `String transform(String)`. Nếu chỉ giữ hai phương thức này, một lời gọi được biên dịch theo kiểu `Transformer` có thể không dispatch đến bản triển khai mong muốn.

Để bảo toàn đa hình, `javac` có thể phát sinh một phương thức trung gian. Mô tả cơ chế bằng **mã giả** (không chép thêm đoạn này vào class Java ở trên):

```java
// Bridge do compiler tạo trong bytecode, KHÔNG phải khai báo Java cần viết.
public Object transform(Object value) {
    return transform((String) value);
}
```

Bridge nhận tham số có kiểu sau erasure, ép kiểu rồi chuyển tiếp đến `transform(String)`. Vì vậy:

- `transform(String)` là **phương thức nghiệp vụ** mà tác giả viết.
- `transform(Object)` là **bridge** để lời gọi qua hợp đồng đã xóa kiểu vẫn đi tới bản triển khai.
- Nếu cố đưa giá trị không phải `String` qua đường gọi đã xóa kiểu, phép cast của bridge có thể ném `ClassCastException`. Đây không phải “Reflection tự thêm lỗi”; nó là một phần cơ chế an toàn kiểu ở runtime.

Cách biểu diễn chữ ký ở tầng JVM cũng giúp giải thích hiện tượng: descriptor chứa **kiểu tham số và kiểu trả về**. Trong ví dụ này, hai descriptor tương ứng có thể là:

```text
(Ljava/lang/String;)Ljava/lang/String;   // implementation
(Ljava/lang/Object;)Ljava/lang/Object;   // compiler bridge
```

Trong **ngôn ngữ Java**, overload không phân biệt chỉ bằng kiểu trả về. Trong **class file/JVM**, hai method có thể khác descriptor nhờ kiểu trả về hoặc tham số; trình biên dịch dùng khả năng đó để tạo bridge mà lập trình viên không thể/không cần khai báo thủ công.

### 2.2. Bridge cũng xuất hiện khi return type hiệp biến

Generic không phải nguyên nhân duy nhất. Java cho phép subclass override một method trả về `Number` bằng method trả về `Integer`:

```java
class ValueBase {
    public Number value() { return 10; }
}

class IntValue extends ValueBase {
    @Override
    public Integer value() { return 20; }
}
```

Mã nguồn có một method `IntValue.value(): Integer`. Trên bytecode do `javac` sinh, class con có thể có thêm bridge `value(): Number` chuyển tiếp đến `value(): Integer`. Ở đây **tên và danh sách tham số giống nhau**, nhưng return type khác: đây là lý do `getDeclaredMethods()` có thể trả về cả hai `Method`.

Với kiểu trả về covariant, xóa trùng chỉ dựa vào tên và tham số có thể khiến framework chọn nhầm bridge hoặc mất thông tin về kiểu trả về cụ thể nhất.

### 2.3. Bridge và overload là hai khái niệm khác nhau

- **Override:** Cung cấp triển khai cụ thể cho hợp đồng của lớp/interface cha. Bridge hỗ trợ giữ override đúng sau biên dịch.
- **Overload:** Nhiều phương thức có **cùng tên nhưng khác danh sách kiểu tham số** do lập trình viên khai báo, ví dụ `transform(String)` và `transform(CharSequence)`. Chúng là những API khác nhau và không được bỏ chỉ vì trùng tên.
- **Bridge:** Phương thức do compiler tạo, thường ủy quyền sang một implementation. Nó có thể mang danh sách kiểu tham số khác implementation (generic erasure) hoặc chỉ khác kiểu trả về (covariant override).

Không nên suy luận rằng “cùng tên” = “cùng method” hoặc “có cùng số tham số” = “cùng ý nghĩa”.

## 3. Các API Reflection để nhận diện chính xác

| API / thuộc tính | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `Class.getDeclaredMethods()` | Liệt kê mọi method **khai báo tại đúng kiểu**, kể cả compiler-generated bridge/synthetic | Không liệt kê method chỉ kế thừa; không bảo đảm thứ tự |
| `Class.getMethods()` | Liệt kê public methods của kiểu và phần kế thừa phù hợp | Có thể thấy cả bridge public và method đích; còn có method từ `Object` |
| `Method.isBridge()` | `true` nếu method là bridge | Tín hiệu chính xác và trực tiếp nhất để nhận diện bridge qua core Reflection |
| `Method.isSynthetic()` | `true` nếu phần tử là synthetic do compiler/tool tạo | Bridge thường synthetic; **synthetic không đồng nghĩa bridge** |
| `Method.getParameterTypes()` | Kiểu tham số **đã erasure** dưới dạng `Class<?>[]` | Bridge của ví dụ generic nhận `Object`, implementation nhận `String` |
| `Method.getReturnType()` | Kiểu trả về JVM ở runtime | Bridge covariant có thể trả `Number`, implementation trả `Integer` |
| `Method.getGenericParameterTypes()` / `getGenericReturnType()` | Thông tin `Type`, `TypeVariable`, `ParameterizedType` nếu metadata còn lưu | Không tự suy ra toàn bộ phép thay thế generic trong mọi tầng kế thừa |
| `Method.getDeclaringClass()` | Class/interface **khai báo** method này | Quan trọng khi xử lý kết quả từ `getMethods()` có cả kế thừa |
| `Method.getModifiers()` | Cờ truy cập, `static`, `abstract`... | `public` không cho biết method có phải bridge hay không |

`getDeclaredMethods()` phản ánh **class file**, không chỉ mã Java người viết; do đó compiler có thể bổ sung method không có dòng nguồn tương ứng. Và việc xuất hiện trong kết quả Reflection không có nghĩa method có thể được gọi từ mọi module hoặc mọi ngữ cảnh truy cập.

Một API khác dễ gây hiểu nhầm: `getMethod("value")` và `getDeclaredMethod("value")` trả về **một** method theo quy tắc lựa chọn của Reflection. Nếu có các method cùng tên/tham số nhưng return type khác, API có thể ưu tiên return type cụ thể hơn. Vì vậy **không dùng tra cứu một method để kết luận class không có bridge**: muốn phân tích đầy đủ phải liệt kê và kiểm tra từng `Method.isBridge()`.

## 4. Ví dụ chạy độc lập trên Java 17+

Mã dưới đây chứng minh đồng thời ba hiện tượng: bridge do erasure, bridge do covariant return, và overload hợp lệ phải được giữ nguyên.

Tạo **`BridgeMethodDemo.java`** với toàn bộ nội dung sau:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Locale;
import java.util.stream.Collectors;

interface Transformer<T> {
    T transform(T value);
}

final class TrimTransformer implements Transformer<String> {
    @Override
    public String transform(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }

    // Overload hợp lệ: cùng tên và một tham số, khác kiểu tham số.
    public String transform(CharSequence value) {
        return value.toString();
    }

    // Overload hợp lệ thứ hai: hai tham số.
    public String transform(String value, int repeat) {
        return value.repeat(repeat);
    }
}

class ValueBase {
    public Number value() {
        return 10;
    }
}

final class IntValue extends ValueBase {
    @Override
    public Integer value() {
        return 20;
    }
}

public class BridgeMethodDemo {
    private static String params(Method method) {
        return Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));
    }

    private static void printDeclared(Class<?> type) {
        Method[] methods = type.getDeclaredMethods();

        // Reflection không bảo đảm thứ tự: sắp xếp để stdout ổn định.
        Arrays.sort(methods, Comparator.comparing(Method::getName)
                .thenComparing(BridgeMethodDemo::params)
                .thenComparing(m -> m.getReturnType().getSimpleName()));

        for (Method method : methods) {
            System.out.printf(
                    "%s(%s):%s bridge=%s synthetic=%s%n",
                    method.getName(),
                    params(method),
                    method.getReturnType().getSimpleName(),
                    method.isBridge(),
                    method.isSynthetic());
        }

        long userMethods = Arrays.stream(methods)
                .filter(method -> !method.isBridge())
                .count();
        System.out.println("user methods=" + userMethods);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        System.out.println("TrimTransformer");
        printDeclared(TrimTransformer.class);

        Method viaErasure = TrimTransformer.class
                .getMethod("transform", Object.class);
        Method source = TrimTransformer.class
                .getMethod("transform", String.class);

        System.out.println("lookup Object is bridge="
                + viaErasure.isBridge());
        System.out.println("lookup String is bridge="
                + source.isBridge());
        System.out.println("invoke bridge="
                + viaErasure.invoke(new TrimTransformer(), "  java  "));

        System.out.println("IntValue");
        printDeclared(IntValue.class);

        Method valueBridge = Arrays.stream(
                        IntValue.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .findFirst()
                .orElseThrow();

        System.out.println("return bridge="
                + valueBridge.getReturnType().getSimpleName());
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac BridgeMethodDemo.java
java BridgeMethodDemo
```

**Stdout khi biên dịch bằng `javac` trên JDK 17+:**

```text
TrimTransformer
transform(CharSequence):String bridge=false synthetic=false
transform(Object):Object bridge=true synthetic=true
transform(String):String bridge=false synthetic=false
transform(String,int):String bridge=false synthetic=false
user methods=3
lookup Object is bridge=true
lookup String is bridge=false
invoke bridge=JAVA
IntValue
value():Integer bridge=false synthetic=false
value():Number bridge=true synthetic=true
user methods=1
return bridge=Number
```

**Đọc kết quả:**

1. `TrimTransformer` có ba method do tác giả viết và thêm một bridge `transform(Object):Object`. Nếu framework xử lý tất cả kết quả `getDeclaredMethods()` như các nghiệp vụ độc lập, `transform(String)` có nguy cơ được xử lý **hai lần**: một lần trực tiếp và một lần qua bridge.
2. `transform(CharSequence)` và `transform(String)` đều nhận **một tham số**, nhưng là hai overload thật. Quy tắc “mỗi tên + số lượng tham số một lần” sẽ xóa nhầm một trong hai.
3. `getMethod("transform", Object.class)` tìm bridge; `getMethod("transform", String.class)` tìm implementation. Gọi bridge với chuỗi `"  java  "` chuyển tới implementation, nên trả `"JAVA"`.
4. `IntValue.value()` có một implementation trả `Integer` và bridge trả `Number`. Hai method cùng tên, **không có tham số**, nhưng khác return type. `getDeclaredMethods()` liệt kê cả hai.
5. `isBridge()` nhận diện đúng hai method cầu nối; trong ví dụ này `isSynthetic()` cũng đúng với chúng. Đừng suy ngược rằng **mọi synthetic đều là bridge**.

Ở ví dụ này `printDeclared` cố ý chỉ duyệt method của **chính class**. Nếu đổi thành `getMethods()`, kết quả còn chứa method public kế thừa, chẳng hạn từ `Object`; không thể giữ nguyên số lượng hoặc stdout như ở trên.

## 5. Cách tránh xử lý trùng khi khám phá method

### 5.1. Trước hết xác định đơn vị cần thu thập

Một công cụ chỉ muốn **method nghiệp vụ do lập trình viên khai báo trực tiếp** có cách thu thập khác một công cụ muốn **toàn bộ public API kế thừa** hoặc một trình phân tích **bytecode**.

- **Sinh tài liệu API mức source/đăng ký handler:** thường bắt đầu từ `getDeclaredMethods()`, lọc bridge rồi áp dụng các điều kiện nghiệp vụ khác (modifier, annotation, quyền truy cập).
- **Khám phá public API kể cả kế thừa:** bắt đầu từ `getMethods()`, lọc bridge khi bridge không phải API riêng, dùng `getDeclaringClass()` và chữ ký để phân biệt nguồn khai báo.
- **Debugger/bytecode analyzer/JVM tooling:** có thể **phải giữ bridge** vì chúng tồn tại thật trong class file và ảnh hưởng đến dispatch, stack trace, hành vi invocation. Trong nhóm này, gắn nhãn bridge thay vì xóa.
- **Framework nhận được chính `Method` là bridge:** không chỉ bỏ qua; có thể cần tìm **method đích mà bridge chuyển tiếp đến** trước khi đọc annotation hoặc kiểu generic phục vụ nghiệp vụ.

### 5.2. Mẫu lọc an toàn cho danh sách method do class khai báo

Khi mục đích chỉ là liệt kê các phương thức nghiệp vụ ở **một class cụ thể**, ví dụ tối thiểu là:

```java
// Trích đoạn: cần import java.lang.reflect.Method, java.util.Arrays,
// java.util.Comparator và java.util.List.
List<Method> methods = Arrays.stream(type.getDeclaredMethods())
        .filter(method -> !method.isBridge())
        .sorted(Comparator.comparing(Method::getName)
                .thenComparing(m -> Arrays.toString(m.getParameterTypes()))
                .thenComparing(m -> m.getReturnType().getName()))
        .toList();
```

Với `type = TrimTransformer.class`, danh sách này giữ lại **cả ba overload do tác giả viết** và bỏ bridge `transform(Object)`. `toList()` có sẵn từ Java 16. Đoạn mã chỉ là **trích đoạn**, không phải file có `main` độc lập; nó giả định biến `type` đã tồn tại.

Tùy sản phẩm, nếu cần loại mọi compiler-generated method khỏi màn hình dành cho người dùng, có thể cân nhắc thêm `!method.isSynthetic()`. Nhưng **đừng thay bộ lọc bridge bằng bộ lọc synthetic rồi cho rằng hai khái niệm giống nhau**. Synthetic khác (ví dụ method trợ giúp do compiler tạo) có vai trò riêng và có thể cần giữ trong công cụ phân tích runtime.

**Quan trọng:** `filter(!isBridge())` là cách hợp lý để không **đếm bridge thành một nghiệp vụ riêng** trong trường hợp khám phá method. Nó **không phải bộ giải quyết mọi tình huống ghi đè, kế thừa, proxy hoặc annotation**.

### 5.3. Vì sao khử trùng theo tên hoặc tên + số tham số là sai?

Xét hai cách dễ mắc lỗi:

```java
// SAI về mặt nghiệp vụ: bỏ các overload cùng tên.
Set<String> seen = new HashSet<>();
for (Method method : type.getDeclaredMethods()) {
    if (seen.add(method.getName())) {
        register(method);
    }
}

// VẪN SAI: transform(String) và transform(CharSequence)
// cùng có name="transform", parameterCount=1.
String key = method.getName() + "/" + method.getParameterCount();
```

Đây là **mã phản ví dụ**, không phải chương trình hoàn chỉnh: `type`, `method` và `register` chỉ là các ký hiệu minh họa. Khử trùng như vậy có thể chọn một bridge, bỏ implementation hoặc xóa overload hợp lệ. Vì Reflection không bảo đảm thứ tự mảng, kết quả còn có thể thay đổi giữa lần chạy.

Thực hành tốt hơn:

1. **Lọc bridge theo cờ metadata** (`isBridge()`) nếu mục đích là khám phá method nghiệp vụ.
2. **Giữ đầy đủ kiểu tham số**, không chỉ `parameterCount`. Với việc phân tích bytecode, khóa nhận diện có thể bao gồm **declaring class, tên method, danh sách kiểu tham số và kiểu trả về** (JVM descriptor). Với API mức Java, xử lý override/hiding theo quy tắc riêng và giữ nguyên overload hợp lệ.
3. **Sắp xếp chủ động** nếu cần output ổn định. `getDeclaredMethods()` và `getMethods()` không hứa thứ tự.
4. **Đếm sau khi lọc** nếu chỉ số cần biểu diễn số action/handler nghiệp vụ, không lấy `getDeclaredMethods().length` làm số method do tác giả viết.
5. **Không gọi `Method.invoke` trong giai đoạn scan chỉ để nhận dạng**. Việc đó có thể gây tác dụng phụ, tiêu thụ tài nguyên hoặc làm thay đổi trạng thái. Đọc metadata là đủ để nhận diện bridge.

Ngay cả `Set<Method>` cũng không phải giải pháp tự động: bridge và implementation có thể khác kiểu tham số hoặc kiểu trả về, nên chúng không nhất thiết được coi là cùng một đối tượng metadata.

## 6. Khi nào phải tìm lại method đích của bridge?

Một số framework nhận vào một `Method` do proxy, interceptor, reflection scan hay callback cung cấp. Nếu `method.isBridge() == true`, framework có thể muốn biết **method nghiệp vụ gốc** để:

- Tra cứu chính xác annotation dùng cho routing, validation hoặc serialization.
- Xác định tham số và return type ở mức triển khai cụ thể.
- Lập khóa cache theo method nghiệp vụ, tránh hai khóa đại diện cùng một hành vi.
- Hiển thị phương thức mà tác giả viết thay vì signature sau erasure.

Trong ví dụ đã chạy, cặp cụ thể được biết rõ:

```java
// Trích đoạn minh họa, giả sử các class ở ví dụ trên đã tồn tại.
Method bridge = TrimTransformer.class
        .getDeclaredMethod("transform", Object.class);
Method target = TrimTransformer.class
        .getDeclaredMethod("transform", String.class);

System.out.println(bridge.isBridge()); // true
System.out.println(target.isBridge()); // false
```

Tuy nhiên, **JDK core Reflection không có một API tổng quát kiểu `getBridgedMethod()` để tự trả về method đích**. Không nên viết thuật toán tổng quát chỉ bằng “cùng tên + cùng số tham số + không phải bridge”, vì `TrimTransformer` có cả `transform(CharSequence)` lẫn `transform(String)`; hai method này đều có một tham số và đều không phải bridge.

Giải quyết bridge-to-target chắc chắn có thể cần phối hợp:

- Kiểu khai báo và hệ phân cấp generic (`getGenericInterfaces()`, `getGenericSuperclass()`).
- Thay thế type variables bằng kiểu thực của subclass, xử lý bound và phép erasure.
- Chữ ký method, return type và tính tương thích override.
- Phân tích bytecode chuyển tiếp khi thật sự cần độ chính xác ở cấp JVM, nhất là trước nhiều compiler/ngôn ngữ khác nhau.

Nếu ứng dụng đã dùng một framework cung cấp **bridge resolution**, nên dùng giải pháp đã được kiểm chứng của framework đó, rồi kiểm thử theo các trường hợp generic/overload/covariant thực tế. Không tự gắn bridge với “ứng viên đầu tiên” từ `getDeclaredMethods()`.

### 6.1. Annotation không tự động “đi theo” mọi override

Chính sách đọc annotation phải được định nghĩa rõ:

- `Method.getAnnotation(...)` tra metadata của `Method` được truyền vào; nó không bảo đảm tìm annotation ở method override khác hoặc interface ancestor.
- `@Inherited` theo Java có ý nghĩa đối với annotation trên **class**, không tạo cơ chế kế thừa tự động cho annotation method override.
- Compiler có thể sao chép một số annotation vào bridge trong những tình huống cụ thể, nhưng không nên biến hành vi của một compiler thành hợp đồng chung cho mọi compiler và mọi annotation.
- Vì vậy một framework cần policy nhất quán: đọc annotation tại method triển khai, hoặc chủ động tìm ở interface/superclass nếu nghiệp vụ yêu cầu; khi đầu vào là bridge, trước tiên giải quyết về method đích khi thích hợp.

**Không nên** lọc bridge rồi tuyên bố mọi thông tin annotation “đã được kế thừa đúng”: đó là hai bài toán khác nhau.

## 7. Những trường hợp biên và hiểu nhầm phổ biến

### 7.1. `isBridge()` và `isSynthetic()` không tương đương

Bridge từ `javac` thường mang cả cờ `ACC_BRIDGE` và `ACC_SYNTHETIC` trong class file. Nhưng synthetic có thể được dùng cho các chi tiết compiler-generated khác. Khi câu hỏi là “đây có phải bridge không?”, dùng **`isBridge()`**. Dùng `isSynthetic()` khi mục tiêu là lọc/ghi nhận rộng hơn về thành viên do compiler tạo.

### 7.2. Không phải cứ generic là có bridge

`List<String>`, generic method, class generic hoặc việc dùng `T` không tự động bắt buộc sinh bridge. Bridge xuất hiện khi compiler cần điều chỉnh giữa semantics của source-level overriding và bytecode/JVM-level method descriptors. Hãy **quan sát cờ trên class đã biên dịch**, thay vì đoán chỉ từ sự xuất hiện của dấu `<...>` trong mã nguồn.

### 7.3. Erasure không phải lúc nào cũng thành `Object`

Ví dụ `T extends Number` thường erases về `Number`; bound có thể tác động trực tiếp đến signature bridge. Không hard-code quy tắc “bridge luôn có tham số `Object`” hoặc “bridge luôn trả `Object`”. Covariant-return bridge trong `IntValue` nhận **0 tham số** và trả `Number`.

### 7.4. `getMethods()` còn xét thừa kế; `getDeclaredMethods()` không xét

`getDeclaredMethods()` trên class con chỉ xét những method **do class đó khai báo**, bao gồm bridge được compiler khai báo tại class đó. Nếu cần method từ cha/interface, `getMethods()` chỉ cung cấp phần **public**; muốn quét cả non-public của từng superclass thì phải tự duyệt hierarchy. Đừng gộp kết quả nhiều class rồi khử trùng theo tên, vì override, overload, default method và bridge cần quy tắc riêng.

### 7.5. Không phải method tên giống nhau đều liên quan đến bridge

Các method `static` bị che khuất theo quy tắc hiding, không override động như instance method. Private method không override theo cách thông thường. Overload là API khác nhau. `isBridge()` giúp tránh dùng suy đoán từ tên, access modifier hoặc số lượng đối số.

### 7.6. Generic reflection có thể cho thấy cả kiểu nguồn và kiểu sau erasure

Ở interface `Transformer<T>`, `getGenericParameterTypes()` có thể cho thấy `T` (`TypeVariable`); ở implementation nó có thể là `String`, trong khi bridge là `Object`. Muốn suy ra `T -> String` trong một chuỗi type/interface, cần giải quyết type variables theo **ngữ cảnh class thực tế**. Chỉ gọi `getGenericParameterTypes()` một lần không tự động làm hết việc đó.

### 7.7. Chú ý compiler, build và access control

Ví dụ dựa trên Java 17+ và bridge do `javac` sinh. Trình biên dịch khác hoặc bytecode đã biến đổi có thể thêm các method synthetic khác. Ngoài ra, nhận được `Method` trong Reflection không phải giấy phép bỏ qua `private`/module boundary; invocation có thể chịu kiểm soát truy cập. Hãy kiểm tra các giả định của framework bằng bytecode thực tế của artifact đã build.

## 8. Kiểm tra bridge ngay trong class file

Sau khi biên dịch ví dụ, có thể xem bytecode bằng:

```bash
javap -p -c -v TrimTransformer
javap -p -c -v IntValue
```

Trong output `javap`, tìm các method cùng tên với implementation, cờ **`ACC_BRIDGE`** và **`ACC_SYNTHETIC`**, cùng bytecode chuyển tiếp như `checkcast` và `invokevirtual` khi có. Đối chiếu với method do người viết khai báo. Không cần dựa vào vị trí/thứ tự của method: `javap` và Reflection trình bày theo các quy tắc khác nhau.

Cách kiểm chứng có ý nghĩa là:

1. Xác định method nghiệp vụ ở mã nguồn.
2. Xác nhận compiler tạo bridge nào và bridge chuyển tiếp đến đâu.
3. Chạy Reflection để so `isBridge()`, `isSynthetic()`, tham số, kiểu trả về.
4. Xác nhận logic scan của ứng dụng chỉ tạo **một xử lý nghiệp vụ** cho từng method đích, nhưng vẫn giữ các overload khác nhau.

Các bước này đặc biệt hữu ích khi một framework đột nhiên báo **“duplicate handler”** sau khi thêm interface generic hoặc đổi return type override.

## 9. Tình huống áp dụng thực tế

| Bối cảnh | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Tự viết dispatcher/registry từ `getDeclaredMethods()` | Đăng ký hai lần handler generic | Lọc `isBridge()` khi tạo danh sách handler; giữ overload thật |
| Sinh API docs từ Reflection | Hiện chữ ký `Object -> Object` bên cạnh `String -> String` | Hiển thị method đích, ghi nhận bridge chỉ khi người đọc cần chi tiết bytecode |
| Quét annotation trên các method | Bỏ qua annotation do nhận vào bridge, hoặc gộp nhầm annotation từ cha | Resolve method đích và áp dụng policy tìm annotation ở declaration/interface rõ ràng |
| Framework nhận `Method` do interceptor cung cấp | Cache nghiệp vụ lưu cả bridge và implementation | Chuẩn hóa về method nghiệp vụ trước khi tạo cache key nếu ngữ cảnh yêu cầu |
| Phân tích bytecode, đo dispatch/stack trace | Mất một method JVM thật nếu lọc bridge | Giữ bridge và gắn metadata `ACC_BRIDGE`/`isBridge()` |
| Quét public method kế thừa qua `getMethods()` | Lẫn bridge, overload, override và method của `Object` | Lọc theo scope/`getDeclaringClass()`; xử lý method inheritance trước khi quy đổi thành action |

## 10. Bài tập tự kiểm tra

**Bài 1.** `interface Repository<T> { T save(T x); }` và `class StringRepository implements Repository<String>` với `public String save(String x)`. Vì sao có thể thấy `save(Object)` khi gọi `getDeclaredMethods()`?  
**Đáp án:** `Repository<T>.save(T)` erases thành `save(Object)`; compiler tạo bridge cho dispatch qua hợp đồng erasure đến `save(String)`. Kiểm tra bằng `isBridge()`.

**Bài 2.** `getDeclaredMethods()` trả về `run(String)` và `run(Integer)`, cả hai `isBridge() == false`. Có được xóa một method theo khóa `"run/1"` không?  
**Đáp án:** Không. Đây là hai overload hợp lệ cùng một số tham số nhưng khác **kiểu** tham số.

**Bài 3.** Class con override `Number value()` bằng `Integer value()`. Vì sao hai `Method` có cùng tên và không tham số nhưng khác return type?  
**Đáp án:** Bridge phục vụ covariant return có thể mang signature trả `Number`; method source trả `Integer`. JVM descriptor chứa return type.

**Bài 4.** Một `Method` có `isSynthetic() == true`. Có thể kết luận chắc chắn `isBridge() == true` không?  
**Đáp án:** Không. Synthetic là nhóm rộng hơn. Dùng `isBridge()` để xác định bridge.

**Bài 5.** Framework nhận được bridge từ `getMethod("transform", Object.class)` và cần annotation của `transform(String)`. Có nên lấy method non-bridge đầu tiên cùng tên không?  
**Đáp án:** Không. Có thể có overload `transform(CharSequence)` cùng tên/số tham số. Cần giải quyết mapping bridge-to-target bằng kiểu generic/hierarchy và quy tắc override, rồi áp dụng policy đọc annotation.

**Bài 6.** Khi làm tool phân tích bytecode, có nên bỏ mọi bridge từ đầu?  
**Đáp án:** Không. Bridge là method JVM thật, cần giữ để hiểu dispatch và bytecode; chỉ lọc khỏi danh sách **nghiệp vụ** nếu đó là yêu cầu.

## 11. Checklist khi xây bộ quét method

- Xác định chính xác mục tiêu: method của **một class**, public method **có kế thừa**, hay mọi method **ở bytecode**.
- Với danh sách nghiệp vụ, xét `isBridge()` trước khi đăng ký/gọi method.
- Bảo toàn overload bằng **kiểu tham số thực**, không gộp theo tên/số lượng tham số.
- Không tin vào thứ tự Reflection; sắp xếp kết quả khi cần output ổn định.
- Nếu nhận một `Method` là bridge và cần annotation/chữ ký nguồn, giải quyết **bridge-to-target** có kiểm chứng; không chọn ứng viên bằng heuristic sơ sài.
- Phân biệt `isSynthetic` với `isBridge`, kiểu generic source với kiểu sau erasure, source method với JVM method descriptor.
- Kiểm thử ít nhất các trường hợp **generic interface, covariant return, overload cùng số tham số, kế thừa**, và bytecode do compiler thực sự dùng trong project.

**Ghi nhớ:** Bridge sinh ra để bảo toàn tính đúng của Java sau type erasure/covariant override. Với Reflection phục vụ nghiệp vụ, chọn **method đích** và bỏ bridge khỏi danh sách đăng ký độc lập; với công cụ đọc bytecode, giữ bridge như một thành viên thật. **Không “dedup” bằng tên phương thức.**

### Tài liệu chuẩn

- [Oracle Java Tutorials — Effects of Type Erasure and Bridge Methods](https://docs.oracle.com/javase/tutorial/java/generics/bridgeMethods.html): nguyên nhân và cơ chế compiler tạo bridge khi xóa kiểu generic.
- [Oracle Java SE 17 — `Method.isBridge()` và `isSynthetic()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): hợp đồng API và bridge phục vụ covariant override.
- [Oracle Java SE 17 — `Class.getDeclaredMethods()` và `getMethods()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): phạm vi liệt kê, method sinh bởi compiler và thứ tự không bảo đảm.
- [Oracle Java Tutorials — Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html): bound, cast và bridge trong runtime generics.
