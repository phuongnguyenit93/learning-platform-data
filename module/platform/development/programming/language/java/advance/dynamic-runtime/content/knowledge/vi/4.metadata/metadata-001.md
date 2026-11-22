# 4.1 Đọc modifier, `AccessFlag` và thành phần `synthetic` do trình biên dịch tạo

Khi khảo sát một lớp tại runtime, Reflection cho biết những gì đang tồn tại trong **kiểu đã biên dịch**, không chỉ những gì tác giả nhìn thấy trong tệp `.java`. Một phương thức do `javac` sinh ra để duy trì tính đa hình, một trường giữ biến đã capture hoặc những modifier được mã hóa trong `.class` có thể xuất hiện trong kết quả đọc metadata dù bạn không khai báo trực tiếp chúng.

Bài này tập trung vào ba câu hỏi liên quan nhưng khác nhau:

1. **Java language modifiers:** thành phần có `public`, `private`, `static`, `final`, `abstract`, `volatile`… theo cách diễn đạt ở ngôn ngữ Java không?
2. **JVM access flags:** class file đánh dấu cấu trúc bằng những bit nào, bao gồm `ACC_BRIDGE`, `ACC_SYNTHETIC` hoặc `ACC_MANDATED` không có từ khóa tương ứng trong mã nguồn?
3. **Compiler-generated members:** thành phần nào được trình biên dịch bổ sung, vì sao tồn tại và nên xử lý chúng như thế nào khi dùng Reflection, công cụ phân tích hoặc framework?

> **Mốc phiên bản:** `Modifier`, `getModifiers()`, `isSynthetic()` và `Method.isBridge()` đã có trong Java 17. `java.lang.reflect.AccessFlag` và các phương thức `accessFlags()` được bổ sung từ **Java 20**. Các ví dụ chính bên dưới biên dịch với **Java 21+**; khi chạy Java 17, dùng các API thay thế nêu ở phần tương thích.

## 1. Mô hình ba lớp metadata

```text
Java source
  public class Child extends Base<String> {
      public String copy(String value) { ... }
  }
              |
              v  javac (biên dịch + type erasure + mã hỗ trợ)
.class / class file
  flags: ACC_PUBLIC ...
  method copy(String): ACC_PUBLIC
  method copy(Object): ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
              |
              v  JVM nạp class
Reflection
  getModifiers()  -> các modifier ở mức ngôn ngữ
  accessFlags()   -> tập access flags phù hợp vị trí trong class file
  isSynthetic()   -> thành phần được đánh dấu synthetic
  isBridge()      -> method cầu nối do compiler tạo
```

Có hai điều cần giữ tách bạch:

- Một **modifier** là khái niệm ở mức ngôn ngữ Java. Reflection biểu diễn nhóm này bằng số nguyên `int` của `getModifiers()`, rồi dùng các hàm `Modifier.isXxx(mask)` để giải mã.
- Một **access flag** là bit theo cấu trúc class file hoặc module descriptor. `AccessFlag` mô hình hóa bit và **ngữ cảnh** của nó. Không phải cờ nào cũng là từ khóa Java, và không phải đặc tính Java nào cũng có bit cờ riêng.

Mọi thành phần compiler-generated đều nên được quan sát theo metadata thực tế, không kết luận chỉ từ tên `$...`, vì tên phụ trợ có thể đổi giữa phiên bản compiler.

## 2. Đọc modifier bằng `getModifiers()` và `Modifier`

Các lớp Reflection cơ bản:

| Đối tượng cần đọc | API tìm thành phần | API đọc modifier |
| --- | --- | --- |
| Class/interface/enum/record | `Class<?> type` | `type.getModifiers()` |
| Trường | `type.getDeclaredField("name")` | `field.getModifiers()` |
| Phương thức | `type.getDeclaredMethod("name", ParamType.class)` | `method.getModifiers()` |
| Constructor | `type.getDeclaredConstructor(ParamType.class)` | `constructor.getModifiers()` |
| Tham số | `method.getParameters()` | `parameter.getModifiers()` |

`getModifiers()` trả về **bitmask**, không phải ordinal hay một enum. Kiểm tra bằng hàm chuyên dụng:

```java
int modifiers = field.getModifiers();

boolean isPublic = Modifier.isPublic(modifiers);
boolean isStatic = Modifier.isStatic(modifiers);
boolean isFinal = Modifier.isFinal(modifiers);
String readable = Modifier.toString(modifiers);
```

Đây là **đoạn mã minh họa**, giả định `field` là một `java.lang.reflect.Field` và đã import `java.lang.reflect.Modifier`.

Ví dụ với một trường `private static final`, ba bit tương ứng đều có mặt; kiểm tra `modifiers == Modifier.PRIVATE` sẽ **sai** vì bitmask chứa nhiều cờ. Hãy dùng `Modifier.isPrivate(modifiers)` hoặc phép toán bit được kiểm soát.

### 2.1. Loại thành phần quyết định modifier nào có nghĩa

| Loại | Modifier thường gặp | Cách đọc |
| --- | --- | --- |
| Class | `public`, `abstract`, `final`; member class có thể `static` | `Modifier.isFinal(type.getModifiers())` |
| Method | `public`, `protected`, `private`, `static`, `final`, `abstract`, `synchronized`, `native` | `Modifier.isSynchronized(method.getModifiers())` |
| Field | `public`, `private`, `static`, `final`, `volatile`, `transient` | `Modifier.isVolatile(field.getModifiers())` |
| Constructor | modifier truy cập `public`/`protected`/`private` | `Modifier.isPublic(constructor.getModifiers())` |
| Parameter | một số modifier liên quan đến tham số, ví dụ `final` | `Modifier.isFinal(parameter.getModifiers())` |

Không áp dụng máy móc mọi `Modifier.isXxx` lên mọi loại: `volatile` có nghĩa cho **field**; `synchronized` có nghĩa cho **method**; `transient` không phải modifier của method.

### 2.2. `getDeclaredXxx` và `getXxx` khác nhau

- `getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructors()` trả các thành phần **được khai báo trong class file của chính kiểu đó**, bao gồm cả `private` và các thành phần do compiler tạo nếu tồn tại. Không tự lấy thành phần kế thừa từ superclass.
- `getFields()`, `getMethods()` tập trung vào các thành phần **public** nhìn thấy từ kiểu, có thể bao gồm những thành phần kế thừa. Đây không phải phép thay thế tương đương khi muốn kiểm kê class file.
- API không cam kết thứ tự của các mảng từ `getDeclaredMethods()` hay `getDeclaredFields()`. Nếu cần báo cáo ổn định, hãy **sắp xếp theo một khóa có chủ đích** trước khi hiển thị.
- Với method overload, `getDeclaredMethod(name, parameterTypes...)` định vị theo tên và **kiểu tham số**, không phải số lượng tham số hay kiểu trả về. Với bridge method, hai phương thức có thể cùng tên nhưng khác parameter type sau type erasure.

## 3. `AccessFlag`: xem chính xác hơn metadata ở mức JVM

Từ Java 20, `AccessFlag` biểu diễn các cờ class file và module; các API Reflection trả về `Set<AccessFlag>` không sửa đổi trực tiếp được.

| Nguồn Reflection | API từ Java 20 |
| --- | --- |
| `Class<?>` | `type.accessFlags()` |
| `Field` | `field.accessFlags()` |
| `Method` / `Constructor` | `method.accessFlags()` / `constructor.accessFlags()` |
| `Parameter` | `parameter.accessFlags()` |

Ví dụ:

```java
boolean isBridge = method.accessFlags().contains(AccessFlag.BRIDGE);
boolean isSynthetic = method.accessFlags().contains(AccessFlag.SYNTHETIC);
boolean isVolatile = field.accessFlags().contains(AccessFlag.VOLATILE);
```

Đây là **đoạn minh họa**, giả định `method`, `field` đã tồn tại và đã import `java.lang.reflect.AccessFlag`.

### 3.1. Bit trùng nhau ở các vị trí khác nhau

Đừng suy luận ý nghĩa của một bit nếu chưa biết **loại cấu trúc** sở hữu nó.

| Mask | Trong field | Trong method |
| --- | --- | --- |
| `0x0040` | `ACC_VOLATILE` | `ACC_BRIDGE` |
| `0x0080` | `ACC_TRANSIENT` | `ACC_VARARGS` |

Ngoài ra bit `0x0020` có nghĩa là `ACC_SUPER` tại vị trí class trong class file, nhưng là `ACC_SYNCHRONIZED` với method. `AccessFlag.Location` biểu thị vị trí: `CLASS`, `INNER_CLASS`, `FIELD`, `METHOD`, `METHOD_PARAMETER` và những vị trí liên quan module.

Khi bạn có mask và vị trí hợp lệ, có thể dùng:

```java
Set<AccessFlag> fieldFlags =
        AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.FIELD);
Set<AccessFlag> methodFlags =
        AccessFlag.maskToAccessFlags(0x0040, AccessFlag.Location.METHOD);
```

Đây cũng là **đoạn minh họa** (import `java.util.Set` và `AccessFlag`). `fieldFlags` chứa `VOLATILE`; `methodFlags` chứa `BRIDGE`. Dùng đúng `Location` thay vì thử giải mã bằng một mặt nạ `Modifier` chung.

### 3.2. Modifier của ngôn ngữ ≠ mọi cờ trong `.class`

Một số cờ có dạng gần trực tiếp với modifier nguồn, chẳng hạn `PUBLIC`, `FINAL`, `VOLATILE`, `SYNCHRONIZED`. Những cờ như `BRIDGE`, `SYNTHETIC`, `MANDATED` lại mô tả tạo tác và metadata của JVM, **không phải từ khóa Java**. Phương thức `flag.sourceModifier()` cho biết cờ có modifier nguồn tương ứng trực tiếp hay không; `flag.mask()` trả vị trí bit tương ứng.

Chiều ngược lại cũng có ngoại lệ: `sealed` được mô tả qua metadata permitted subclasses, có thể truy vấn bằng `Class.isSealed()` và `getPermittedSubclasses()`; record có `Record` attribute và `Class.isRecord()`. **Không có `AccessFlag.RECORD` hoặc `AccessFlag.SEALED`** để thay thế các API đó.

`AccessFlag` là API dễ đọc và giàu ngữ nghĩa hơn khi phân tích cấu trúc đã biên dịch, nhưng nó không thay thế hoàn toàn các truy vấn mức ngôn ngữ hoặc các thuộc tính riêng như `isRecord()`.

## 4. Thực hành 1 — Modifier và AccessFlag cùng soi một trường/method

Tạo tệp **`ModifierFlagsDemo.java`**:

```java
import java.lang.reflect.AccessFlag;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ModifierFlagsDemo {
    static final class Gadget {
        private volatile int state;
        public synchronized void refresh() {}
        public void send(String... messages) {}
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Gadget.class;
        Field state = type.getDeclaredField("state");
        Method refresh = type.getDeclaredMethod("refresh");
        Method send = type.getDeclaredMethod("send", String[].class);

        System.out.println("class final: " + Modifier.isFinal(type.getModifiers()));
        System.out.println("field volatile (Modifier): "
                + Modifier.isVolatile(state.getModifiers()));
        System.out.println("field VOLATILE (AccessFlag): "
                + state.accessFlags().contains(AccessFlag.VOLATILE));
        System.out.println("method synchronized (Modifier): "
                + Modifier.isSynchronized(refresh.getModifiers()));
        System.out.println("method SYNCHRONIZED (AccessFlag): "
                + refresh.accessFlags().contains(AccessFlag.SYNCHRONIZED));
        System.out.println("method varargs: " + send.isVarArgs());
        System.out.println("method VARARGS: "
                + send.accessFlags().contains(AccessFlag.VARARGS));
        System.out.println("0x40 as FIELD: "
                + AccessFlag.maskToAccessFlags(0x40,
                        AccessFlag.Location.FIELD).contains(AccessFlag.VOLATILE));
        System.out.println("0x40 as METHOD: "
                + AccessFlag.maskToAccessFlags(0x40,
                        AccessFlag.Location.METHOD).contains(AccessFlag.BRIDGE));
    }
}
```

Biên dịch bằng JDK 21+:

```bash
javac ModifierFlagsDemo.java
java ModifierFlagsDemo
```

**Stdout chính xác:**

```text
class final: true
field volatile (Modifier): true
field VOLATILE (AccessFlag): true
method synchronized (Modifier): true
method SYNCHRONIZED (AccessFlag): true
method varargs: true
method VARARGS: true
0x40 as FIELD: true
0x40 as METHOD: true
```

Giải thích:

1. `Modifier.isFinal(type.getModifiers())` đọc tính `final` của class.
2. `volatile` là modifier của field, do đó `Modifier.isVolatile` và `AccessFlag.VOLATILE` đều có thể nhận diện.
3. `synchronized` là modifier của method. `send(String...)` có cờ `VARARGS`; tham số runtime là một `String[]`, dù cú pháp nguồn dùng dấu ba chấm.
4. Hai lần giải mã `0x40` cùng cho `true` nhưng diễn giải **hai ý nghĩa khác nhau** nhờ `Location.FIELD` và `Location.METHOD`.

> `Modifier.toString(mask)` phục vụ hiển thị modifier nguồn; không dùng nó làm bộ giải mã toàn bộ cờ cấu trúc JVM. Khi cần nhận diện bridge/synthetic, dùng API chuyên dụng hoặc `accessFlags()`.

## 5. `synthetic` là gì và khi nào compiler tạo thêm thành phần?

Theo class file format, `ACC_SYNTHETIC` hoặc `Synthetic` attribute đánh dấu thành phần do compiler tạo mà không tương ứng với khai báo nguồn bình thường. Các API như `Class.isSynthetic()`, `Field.isSynthetic()`, `Method.isSynthetic()` và `Constructor.isSynthetic()` cho phép phát hiện.

Những tình huống thường gặp:

- **Bridge method cho generics/type erasure**: compiler bổ sung method để giữ đúng override và đa hình sau xóa kiểu generic, hoặc trường hợp covariance tương tự.
- **Trường lưu captured value** của local/anonymous class: để một đối tượng có thể dùng lại biến bên ngoài sau khi phương thức tạo nó đã kết thúc.
- **Một số cấu trúc hỗ trợ nội bộ**: tùy compiler và phiên bản class file. Không nên mặc định có cùng tên hoặc cùng số lượng helper field/method giữa mọi compiler.

### 5.1. `synthetic`, `bridge`, `mandated`, `implicit` có phải một không?

| Khái niệm | Phản ánh điều gì? | Cách hỏi |
| --- | --- | --- |
| `synthetic` | Thành phần là tạo tác do compiler sinh, được đánh dấu synthetic | `member.isSynthetic()`; `AccessFlag.SYNTHETIC` |
| `bridge` | Method cầu nối để thích ứng chữ ký / bảo toàn override ở bytecode | `method.isBridge()`; `AccessFlag.BRIDGE` |
| `mandated` | Thành phần/tham số có mặt theo quy tắc ngôn ngữ dù không viết tường minh; tại các vị trí class file có hỗ trợ cờ | `AccessFlag.MANDATED` hoặc `Parameter.isImplicit()` trong trường hợp tham số |
| `implicit` | Khai báo được ngôn ngữ quy định ngầm, như một số thành phần của enum/record | Không mặc định `isSynthetic() == true` |

Một bridge method **thường vừa `isBridge()` vừa `isSynthetic()`** trong bytecode do `javac` tạo. Tuy nhiên không thể kết luận mọi thành phần compiler-generated đều synthetic:

- Constructor mặc định, bộ khởi tạo lớp và các thành phần khai báo ngầm của enum/record có ngoại lệ theo JVM Specification.
- Method `values()` và `valueOf(String)` của enum, accessor `x()` của record, `equals/hashCode/toString` do record sinh là các thành phần ngầm được ngôn ngữ đặc tả. Đừng lọc mất chúng chỉ vì chúng không xuất hiện tường minh trong source.
- `static`, tên có dấu `$` hoặc tên trông “máy tạo” **không đủ bằng chứng** là synthetic.
- Java 11+ hỗ trợ nestmates, nên compiler không nhất thiết sinh các method truy cập private kiểu `access$...` như compiler cũ. Lambda thường liên quan `invokedynamic` và hiện thực runtime; không gán một hình dạng lớp/field duy nhất cho tất cả các JDK.

## 6. Thực hành 2 — Bridge method do type erasure

Tạo tệp **`BridgeSyntheticDemo.java`**:

```java
import java.lang.reflect.AccessFlag;
import java.lang.reflect.Method;
import java.util.Locale;

public class BridgeSyntheticDemo {
    static class Base<T> {
        public T copy(T value) {
            return value;
        }
    }

    static final class StringBox extends Base<String> {
        @Override
        public String copy(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws Exception {
        Method source = StringBox.class.getDeclaredMethod("copy", String.class);
        Method generated = StringBox.class.getDeclaredMethod("copy", Object.class);

        System.out.println("source: bridge=" + source.isBridge()
                + ", synthetic=" + source.isSynthetic());
        System.out.println("generated: bridge=" + generated.isBridge()
                + ", synthetic=" + generated.isSynthetic());
        System.out.println("generated BRIDGE flag: "
                + generated.accessFlags().contains(AccessFlag.BRIDGE));
        System.out.println("generated SYNTHETIC flag: "
                + generated.accessFlags().contains(AccessFlag.SYNTHETIC));
        System.out.println("bridge invoke: "
                + generated.invoke(new StringBox(), "java"));
    }
}
```

```bash
javac BridgeSyntheticDemo.java
java BridgeSyntheticDemo
```

**Stdout chính xác khi biên dịch bằng `javac` JDK 21+:**

```text
source: bridge=false, synthetic=false
generated: bridge=true, synthetic=true
generated BRIDGE flag: true
generated SYNTHETIC flag: true
bridge invoke: JAVA
```

### 6.1. Vì sao xuất hiện method thứ hai?

`Base<T>.copy(T)` sau type erasure có chữ ký mức JVM nhận `Object`. `StringBox.copy(String)` là method người viết thực sự khai báo, nhưng JVM phải tiếp tục hỗ trợ lời gọi đa hình thông qua kiểu `Base<String>`. `javac` tạo thêm bridge đại ý:

```java
// MÃ MINH HỌA CƠ CHẾ, KHÔNG phải một khai báo Java có thể đặt cùng lớp
public Object copy(Object value) {
    return copy((String) value);
}
```

Method đại diện ở class file có tham số `Object`, gọi bản `copy(String)` và trả về `String` như một `Object`. Bridge giúp những bytecode đã gọi chữ ký bị xóa kiểu vẫn đi tới hành vi override của lớp con.

Khi đọc `StringBox.class.getDeclaredMethods()`, Reflection thấy cả method nguồn và bridge. Nếu đang tạo **danh mục API cho con người**, thường cần ẩn bridge trùng lặp; nếu đang làm bytecode analyzer hoặc dispatch engine, **không được xóa bỏ hoặc bỏ qua ảnh hưởng của bridge**. Lựa chọn lọc phải phụ thuộc mục đích.

### 6.2. Xác minh bằng `javap`

Dùng:

```bash
javap -p -v 'BridgeSyntheticDemo$StringBox'
```

Dấu nháy đơn giữ ký tự `$` không bị shell thay thế. Trong kết quả dài, tìm method `copy(java.lang.Object)`. Một dòng cờ tiêu biểu khi biên dịch ví dụ này bằng `javac` là:

```text
flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

`javap -v` hiển thị sự thật ở class file, còn `Method.isBridge()` và `Method.isSynthetic()` là cách đọc tương ứng tại runtime. Không nhầm một method có cờ `BRIDGE` với “một method bridge thủ công” viết trong source: cờ do compiler/tool tạo class file thiết lập.

## 7. Thực hành 3 — Field capture được sinh ra, nhưng record không synthetic

Tạo tệp **`SyntheticFieldDemo.java`**:

```java
import java.lang.reflect.Field;
import java.util.Arrays;

public class SyntheticFieldDemo {
    record Point(int x, int y) {}

    static Runnable capture(String message) {
        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(message);
            }
        }
        return new LocalTask();
    }

    public static void main(String[] args) {
        Runnable task = capture("Hello");
        Field[] fields = task.getClass().getDeclaredFields();
        boolean hasSyntheticField = Arrays.stream(fields).anyMatch(Field::isSynthetic);

        System.out.println("captured synthetic field: " + hasSyntheticField);
        System.out.println("record class synthetic: " + Point.class.isSynthetic());
        System.out.println("record components: " + Point.class.getRecordComponents().length);
        task.run();
    }
}
```

```bash
javac SyntheticFieldDemo.java
java SyntheticFieldDemo
```

**Stdout với `javac` JDK 21+:**

```text
captured synthetic field: true
record class synthetic: false
record components: 2
Hello
```

`LocalTask` có phương thức `run()` truy cập `message` của phạm vi bao ngoài; compiler tạo một trường lưu giá trị được capture. Tên trường là **chi tiết triển khai** của compiler và không được ứng dụng dựa vào. Kiểm tra `Field.isSynthetic()` đáng tin hơn việc đoán tên.

`Point` là record trong source Java, được nhận diện qua `isRecord()` và `getRecordComponents()`. Bản thân class record không phải một lớp synthetic chỉ vì compiler tạo một số thành phần của nó. Hai record component `x` và `y` là các thành phần được khai báo trong nguồn.

> Với các compiler khác `javac`, cách tạo field phụ trợ có thể khác. Vì vậy hãy tránh kiểm tra bắt buộc “mọi local class đều có chính xác một synthetic field” hoặc “mọi compiler đều chọn cùng tên trường”.

## 8. Metadata của tham số và `mandated`

`Parameter` có các phương thức riêng ngoài `getModifiers()`:

- `isNamePresent()`: class file có lưu tên parameter qua metadata phù hợp hay không. Nếu không, `getName()` có thể trả `arg0`, `arg1`... và **đó không phải tên nguồn được bảo đảm**.
- `isSynthetic()`: parameter là tạo tác mà không được khai báo tường minh/ngầm ở mức nguồn.
- `isImplicit()`: parameter tương ứng khai báo ngầm theo ngôn ngữ (thường tương quan với cờ `MANDATED` khi được ghi vào `MethodParameters`).
- `accessFlags()`: từ Java 20, xem tập flag ở vị trí `METHOD_PARAMETER`.

Ví dụ đoạn kiểm tra để đưa vào một công cụ Reflection:

```java
// Fragment: executable là Method hoặc Constructor<?> đã lấy qua Reflection
for (java.lang.reflect.Parameter parameter : executable.getParameters()) {
    System.out.println(parameter.getName()
            + " named=" + parameter.isNamePresent()
            + " synthetic=" + parameter.isSynthetic()
            + " implicit=" + parameter.isImplicit()
            + " flags=" + parameter.accessFlags());
}
```

Muốn tên tham số nguồn ổn định, thường biên dịch với `javac -parameters ...`; tùy compiler, target và loại parameter, `MethodParameters` có thể chứa thông tin khác nhau. Từ JDK 21, `javac` cũng ghi metadata cho nhiều parameter synthetic/mandated trong trường hợp áp dụng. **Không phân loại tham số chỉ theo tên như `arg0` hay `this$0`**.

## 9. Thiết kế bộ đọc metadata cho công cụ/framework

Bước đọc thông thường:

1. Xác định đúng `Class<?>` và class loader; sử dụng `getDeclaredFields()`, `getDeclaredMethods()` nếu muốn kiểm kê chính **class file này**.
2. Đọc modifier nguồn bằng `getModifiers()` + `Modifier`; với Java 20+ đọc thêm `accessFlags()`.
3. Ghi rõ `isSynthetic()` và `isBridge()` cho mỗi method; với constructor/parameter/field, dùng các API synthetic phù hợp.
4. Chọn chính sách xử lý theo mục đích: **hiển thị tài liệu API** có thể ẩn bridge; **phân tích bytecode/dispatch** nên giữ để hiểu chữ ký và tương thích nhị phân.
5. Sắp xếp kết quả trước khi hiển thị hoặc serialize. Không dựa vào thứ tự mảng Reflection và không dựa vào tên compiler-generated.

Ví dụ minh họa riêng cho việc liệt kê method, với đầu vào `Class<?> type` đã được xác định:

```java
// Fragment Java 21+: type đã có giá trị.
java.lang.reflect.Method[] methods = type.getDeclaredMethods();
java.util.Arrays.sort(methods,
        java.util.Comparator.comparing(java.lang.reflect.Method::toGenericString));

for (java.lang.reflect.Method method : methods) {
    boolean compilerArtifact = method.isSynthetic() || method.isBridge();
    System.out.printf("%s | flags=%s | compilerArtifact=%s%n",
            method.toGenericString(), method.accessFlags(), compilerArtifact);
}
```

Đây là **đoạn minh họa dùng trong công cụ**, không phải một chương trình chạy độc lập. `toGenericString()` có ích để mô tả và sort, nhưng không thiết kế một giao thức lâu dài dựa vào chuỗi định dạng Reflection; nếu cần định danh ổn định, hãy mã hóa tên, kiểu tham số, kiểu trả về, declaring class và loader theo hợp đồng của công cụ.

### 9.1. Lưu ý quyền truy cập

`Modifier.isPublic(method.getModifiers())` chỉ cho biết **khai báo** `public`. Nó không bảo đảm mã gọi ở mọi module được phép reflection invoke:

- Class chứa method có thể không public hoặc package không được module `exports` tới bên gọi.
- `getDeclaredMethod` có thể đọc metadata của method private, nhưng muốn **invoke/access** còn bị kiểm tra Java access control và Java module system.
- `setAccessible(true)` hoặc `trySetAccessible()` không tự vượt được mọi module boundary; `opens`/quyền truy cập tương ứng vẫn có vai trò.
- Truy vấn metadata cũng không đồng nghĩa được phép sửa field hay gọi private constructor.

### 9.2. Khi nào nên lọc synthetic?

| Bài toán | Khuyến nghị |
| --- | --- |
| Trang tài liệu API hướng tới người đọc | Hiển thị method nguồn và tránh bản sao bridge khi phù hợp; vẫn giữ các member implicit có ý nghĩa (record/enum). |
| Schema mapper/serializer | Xác định rõ quy tắc field và property; không tự động serialize mọi synthetic capture field. |
| Framework tìm annotation/handler | Hiểu quan hệ bridge–method nguồn; một số framework phải resolve bridge tới method đúng. |
| Công cụ bytecode hoặc binary compatibility | Giữ mọi member có liên quan, kể cả synthetic/bridge, vì có thể là điểm nối runtime bắt buộc. |
| Audit, debug class loader / reflection | Lưu cả cờ, declaring class và thông tin phương thức thay vì suy luận qua tên. |

## 10. Tương thích Java 17 và kiểm tra qua class file

Nếu môi trường dừng ở **Java 17**, các phương thức `accessFlags()` và enum `AccessFlag` chưa có. Vẫn có thể dùng:

```java
boolean publicMember =
        java.lang.reflect.Modifier.isPublic(method.getModifiers());
boolean bridge = method.isBridge();
boolean synthetic = method.isSynthetic();
```

Đây là fragment Java 17 với biến `method` đã tồn tại. Nếu cần bit `ACC_*` không có API phản chiếu tương ứng, dùng `javap -v -p <ClassName>` trong môi trường biên dịch hoặc công cụ đọc class file đáng tin cậy; không cố ép `Modifier` thành bộ giải mã đầy đủ class file.

Khi phân tích binary, xem các mục phù hợp trong `javap`:

- `flags: (0x...) ACC_...` của class, field, method;
- `Signature` ghi kiểu generic mà JVM descriptor đã erasure;
- `MethodParameters` chứa tên và cờ tham số khi có;
- `InnerClasses`, `Record`, `PermittedSubclasses` và các attribute khác cho các tính chất không thuộc modifier nguồn đơn thuần.

Không nhất thiết mọi compiler đều ghi cùng bộ attribute phụ trợ. `javap` là công cụ kiểm tra bytecode trên máy; Reflection là quan sát kiểu runtime đã được nạp, có thể chịu ảnh hưởng của class loader, module và công cụ thay đổi bytecode.

## 11. Lỗi phổ biến

1. **Dùng `getModifiers() == Modifier.PUBLIC`:** sai khi thành phần có thêm `static`, `final`...; giải mã bằng `Modifier.isPublic(...)`.
2. **Dùng `Modifier.toString()` để tìm bridge/synthetic:** nó biểu diễn Java language modifiers, không thay thế `Method.isBridge()`/`isSynthetic()`.
3. **Xem `0x40` luôn là volatile:** sai tại vị trí method, bit đó là `BRIDGE`.
4. **Cho rằng `getDeclaredMethods()` chỉ trả method viết trong source:** sai; nó có thể gồm bridge và các method compiler-generated.
5. **Loại toàn bộ thành phần “không viết ra” như synthetic:** sai với default constructor và những member implicit hợp lệ của enum/record.
6. **Cho rằng mọi method có dấu `$` đều synthetic:** tên không phải cờ; kiểm tra thuộc tính metadata.
7. **Cho rằng Java 17 hỗ trợ `AccessFlag`:** API này có từ Java 20; chọn toolchain Java 21+ khi chạy ví dụ của bài.
8. **Cho rằng `public` luôn invoke được qua mọi module:** access kiểm tra cả visibility, exports/opens và ngữ cảnh bên gọi.
9. **Cho rằng array `getDeclaredMethods()` có thứ tự khai báo:** API không bảo đảm; hãy sort trước khi báo cáo.
10. **Ẩn bridge ngay trong bộ thực thi/framework:** có thể bỏ mất đường đi đa hình hoặc xử lý sai metadata, nhất là khi runtime dựa vào method descriptor đã erasure.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Vì sao cần truyền `AccessFlag.Location` khi giải mã một bitmask? `0x0080` mang ý nghĩa gì trong field so với method?

**Câu 2.** `StringBox` ở thực hành 2 có mấy dạng `copy` được `getDeclaredMethod` truy cập? Vì sao method nhận `Object` không viết trong nguồn?

**Câu 3.** Một record có các method/compiler-generated, vậy `Point.class.isSynthetic()` có bắt buộc trả `true` không?

**Câu 4.** Dùng `getMethods()` hay `getDeclaredMethods()` để rà soát mọi member trong class file, bao gồm `private` và synthetic? Khi nào cần sort?

**Câu 5.** Trên JDK 17, muốn kiểm tra method có bridge flag thì dùng API nào? Có thể dùng `AccessFlag.BRIDGE` trực tiếp không?

**Câu 6.** Vì sao một method `public` trả `Modifier.isPublic(...) == true` nhưng vẫn không invoke được từ module khác?

**Đáp án gợi ý:** (1) Vì bit có nghĩa theo vị trí; `0x0080` là `TRANSIENT` ở field, `VARARGS` ở method. (2) `copy(String)` là method nguồn; `copy(Object)` là bridge synthetic do erasure để duy trì override. (3) Không; thành phần ngầm hợp lệ của record không làm class synthetic. (4) `getDeclaredMethods()`; sort mọi lúc cần đầu ra ổn định. (5) `Method.isBridge()`; `AccessFlag` không có trên JDK 17. (6) Quyền Reflection còn tùy class bao, Java module exports/opens và ngữ cảnh gọi.

## 13. Tài liệu chuẩn

- [Java SE 21 — `java.lang.reflect.Modifier`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Modifier.html): các bitmask và phép kiểm tra modifier.
- [Java SE 21 — `java.lang.reflect.AccessFlag`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessFlag.html): tập cờ JVM, `Location`, `mask()` và `maskToAccessFlags()`.
- [Java SE 21 — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html), [`Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html), [`Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html), [`Parameter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html): đọc metadata runtime.
- [Java Virtual Machine Specification 21 — Class File Format, Chương 4](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): `ACC_*`, `Synthetic`, `MethodParameters`, `Signature` và các thuộc tính class file.
- [Java Language Specification 21 — `13.1 The Form of a Binary](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.1): thành phần compiler-generated và quy tắc mô tả binary.

Khi đọc metadata ở runtime, hãy hỏi **đối tượng là loại cấu trúc nào**, **đang đọc modifier nguồn hay access flag của JVM**, và **thành phần đó có được compiler tạo thêm hay không**. Ba câu hỏi này giúp diễn giải chính xác bridge, synthetic và các member ngầm mà không bỏ sót các cấu trúc cần thiết để chương trình Java hoạt động đúng.