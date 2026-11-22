# Nhận diện phương thức `bridge` và `synthetic` qua Reflection trong Java Generics

## 1. Mục tiêu

Khi đọc các phương thức của một class bằng Java Reflection, đôi khi bạn thấy **nhiều phương thức hơn số phương thức đã viết trong source**. Chẳng hạn class chỉ khai báo `String map(String)`, nhưng Reflection còn liệt kê `Object map(Object)`. Điều này có thể xảy ra vì trình biên dịch tạo **bridge method** để giữ hành vi ghi đè sau khi generic bị xóa kiểu (*type erasure*).

Java cung cấp hai phép kiểm tra trực tiếp trong `java.lang.reflect.Method`:

- `method.isBridge()` — phương thức có cờ bridge của JVM hay không.
- `method.isSynthetic()` — phương thức có cờ synthetic của JVM hay không.

Bài này tập trung vào cách đọc hai cờ đó một cách chính xác, kết nối chúng với **chữ ký phương thức, quy tắc override và output của `javap`**, phân biệt một bridge với phương thức phụ trợ do compiler tạo và sử dụng kết quả Reflection trong công cụ quét API.

Sau bài học, bạn sẽ:

1. Giải thích được tại sao class con generic có thể xuất hiện thêm method trong Reflection.
2. Viết được chương trình liệt kê các phương thức declared kèm kiểu tham số, kiểu trả về, `isBridge()` và `isSynthetic()`.
3. Nhìn ra sự khác biệt giữa `bridge=true, synthetic=true`, `bridge=false, synthetic=true` và một phương thức thông thường.
4. Chọn được `getDeclaredMethods()` hay `getMethods()` khi kiểm tra một class.
5. Tránh đếm trùng phương thức public API khi xây dựng framework, bộ quét annotation, tài liệu API hoặc công cụ kiểm thử.

## 2. Vì sao generic override có thể cần bridge?

Xét một interface generic:

```java
interface Mapper<T> {
    T map(T value);
}
```

Lớp triển khai gắn `T` thành `String`:

```java
final class StringMapper implements Mapper<String> {
    @Override
    public String map(String value) {
        return value.strip();
    }
}
```

Tại **source**, phương thức `String map(String)` đáp ứng hợp đồng của `Mapper<String>`. Tuy nhiên, descriptor của `Mapper.map(T)` ở JVM, do `T` không có bound rõ ràng, có dạng:

```text
(Ljava/lang/Object;)Ljava/lang/Object;
```

Phương thức được người lập trình khai báo trong `StringMapper` có descriptor:

```text
(Ljava/lang/String;)Ljava/lang/String;
```

Nếu chỉ có `map(String)`, một lời gọi đã biên dịch nhằm tới phương thức trên interface có descriptor `map(Object):Object` sẽ không trực tiếp khớp với descriptor `map(String):String` ở class con.

Để bảo đảm tính đa hình, compiler có thể tạo phương thức **bridge** trong `StringMapper`. Xét về hành vi, bridge tương tự:

```java
// MINH HỌA BYTECODE DO COMPILER SINH, KHÔNG TỰ THÊM VÀO SOURCE:
public Object map(Object input) {
    return map((String) input);
}
```

Bridge nhận kiểu sau erasure, chuyển tiếp tới implementation thật và có thể chèn cast cần thiết.

Sơ đồ:

```text
Mapper<String> variable
        |
        | lời gọi map(...), descriptor gốc map(Object):Object
        v
StringMapper.map(Object):Object       [bridge + synthetic]
        |
        | ép Object thành String, gọi implementation
        v
StringMapper.map(String):String       [phương thức do lập trình viên viết]
```

Điều quan trọng: class file có thể chứa **hai** method cùng tên `map` vì danh sách tham số/kiểu trả về trong descriptor bytecode khác nhau. Người lập trình không nên cố khai báo thủ công một overload có erasure trùng như vậy.

### 2.1. Bridge bảo vệ hợp đồng generic như thế nào?

Với tham chiếu có kiểu đúng:

```java
Mapper<String> mapper = new StringMapper();
String text = mapper.map("  Java  ");
```

Java kiểm tra rằng đối số là `String` ngay lúc biên dịch; bridge cho phép lời gọi đi qua giao diện với descriptor đã xóa rồi dispatch về implementation ở class con.

Nếu cố dùng raw type:

```java
// Minh họa hành vi rủi ro; có thể sinh cảnh báo raw/unchecked:
Mapper raw = new StringMapper();
raw.map(123);
```

Bridge có thể ném `ClassCastException` khi ép `Integer` thành `String`. Vấn đề gốc là lời gọi đã phá hợp đồng `Mapper<String>` qua raw type. Bridge không phải một cơ chế chuyển đổi dữ liệu tùy ý.

## 3. `Method.isBridge()` và `Method.isSynthetic()` khác nhau

Đối tượng `Method` biểu diễn một phương thức mà Reflection nhìn thấy. Các phương thức kiểm tra:

```java
boolean bridge = method.isBridge();
boolean synthetic = method.isSynthetic();
```

có ý nghĩa độc lập:

| Trạng thái | Diễn giải thực tế |
| --- | --- |
| `bridge=false`, `synthetic=false` | Phương thức thông thường không mang hai cờ đó. |
| `bridge=true`, `synthetic=true` | Trường hợp bridge do `javac` thường sinh khi cần giữ override/đa hình sau erasure hoặc với covariant return. |
| `bridge=false`, `synthetic=true` | Phương thức do compiler tạo vì mục đích khác, chẳng hạn helper triển khai lambda ở một cách biên dịch cụ thể. |
| `bridge=true`, `synthetic=false` | Hai cờ trên JVM là khái niệm riêng; đừng tự định nghĩa logic của công cụ với giả định `isBridge()` và `isSynthetic()` luôn đồng nhất trong mọi class file và mọi công cụ sinh bytecode. |

`isBridge()` hỏi phương thức có cờ `ACC_BRIDGE` theo class file hay không. `isSynthetic()` hỏi phương thức có cờ `ACC_SYNTHETIC` theo class file hay không. Thông thường bridge do Java compiler sinh là synthetic, nhưng **synthetic không đồng nghĩa bridge**.

`synthetic` ở đây là thuật ngữ của JVM cho thành phần không xuất hiện như một khai báo thông thường trong source. Nó **không phải** thuộc tính generic, không liên quan trực tiếp đến từ khóa `synchronized`, và cũng không có nghĩa rằng phương thức không thể được Reflection tìm thấy hoặc gọi.

### 3.1. Các API Reflection liên quan

| API | Để làm gì |
| --- | --- |
| `Method.isBridge()` | Kiểm tra bridge flag. |
| `Method.isSynthetic()` | Kiểm tra synthetic flag của method. |
| `Method.getName()` | Tên phương thức. |
| `Method.getParameterTypes()` | Kiểu tham số raw/erased ở runtime. |
| `Method.getReturnType()` | Kiểu trả về runtime của method. |
| `Method.getGenericParameterTypes()` | Đọc thông tin tham số generic từ khai báo/metadata nếu có. |
| `Method.getGenericReturnType()` | Đọc khai báo kiểu trả về generic nếu có. |
| `Method.getDeclaringClass()` | Class/interface thực sự khai báo method này trong class file. |
| `Class.getDeclaredMethods()` | Đọc các phương thức được khai báo trong class/interface đó, bao gồm non-public và compiler-generated methods; không gồm phương thức chỉ được kế thừa. |
| `Class.getMethods()` | Đọc các phương thức `public` có thể nhìn thấy của class/interface, bao gồm các phương thức public được kế thừa. |
| `java.lang.reflect.Modifier` | Kiểm tra các modifier thông thường như `public`, `private`, `static`. |

**Đừng tìm `isBridge()` ở đối tượng `Class<?>` hoặc ở `Field`.** Đây là API của `Method`. `isSynthetic()` còn xuất hiện ở một số đối tượng Reflection khác nhưng ý nghĩa phụ thuộc thành phần đang được kiểm tra.

## 4. Ví dụ Java 17 hoàn chỉnh: bridge, covariant return và lambda synthetic

Tạo tệp **`BridgeReflectionDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class BridgeReflectionDemo {
    interface Mapper<T> {
        T map(T input);
    }

    static final class StringMapper implements Mapper<String> {
        @Override
        public String map(String input) {
            return input.strip();
        }
    }

    static class Base {
        Number score() {
            return 1;
        }
    }

    static final class Derived extends Base {
        @Override
        Integer score() {
            return 2;
        }
    }

    static final class LambdaHolder {
        Runnable callback() {
            return () -> { };
        }
    }

    static void inspect(Class<?> type) {
        System.out.println("[" + type.getSimpleName() + "]");
        Arrays.stream(type.getDeclaredMethods())
                .sorted(Comparator.comparing(Method::getName)
                        .thenComparing(m -> Arrays.toString(m.getParameterTypes())))
                .forEach(m -> System.out.println(format(m)));
    }

    static String format(Method m) {
        String params = Arrays.stream(m.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));
        return m.getName() + "(" + params + ")->"
                + m.getReturnType().getSimpleName()
                + " | bridge=" + m.isBridge()
                + " synthetic=" + m.isSynthetic();
    }

    public static void main(String[] args) throws Exception {
        Mapper<String> mapper = new StringMapper();
        System.out.println("result=" + mapper.map("  Java  "));
        System.out.println("score=" + new Derived().score());
        inspect(StringMapper.class);
        inspect(Derived.class);
        inspect(LambdaHolder.class);
        Method bridge = StringMapper.class.getDeclaredMethod(
                "map", Object.class);
        System.out.println("erasedParam="
                + bridge.getParameterTypes()[0].getSimpleName());
    }
}
```

Biên dịch bằng Java 17 hoặc JDK mới hơn có hỗ trợ `--release 17`:

```bash
javac --release 17 BridgeReflectionDemo.java
java BridgeReflectionDemo
```

Kết quả đã kiểm tra bằng `javac --release 17` và `java`:

```text
result=Java
score=2
[StringMapper]
map(Object)->Object | bridge=true synthetic=true
map(String)->String | bridge=false synthetic=false
[Derived]
score()->Integer | bridge=false synthetic=false
score()->Number | bridge=true synthetic=true
[LambdaHolder]
callback()->Runnable | bridge=false synthetic=false
lambda$callback$0()->void | bridge=false synthetic=true
erasedParam=Object
```

Các dòng trên là output của cách biên dịch bằng **`javac`** đã kiểm tra. Tên chính xác như `lambda$callback$0`, việc có/không có helper lambda và thứ tự những phương thức do compiler sinh có thể khác ở compiler/JDK/chiến lược chuyển mã khác; đừng viết business logic phụ thuộc trực tiếp vào tên helper lambda đó. Trong ví dụ, `sorted(...)` được đưa vào để kết quả liệt kê deterministic với bộ method được compiler này sinh ra.

### 4.1. Đọc nhóm `StringMapper`

```text
map(Object)->Object | bridge=true synthetic=true
map(String)->String | bridge=false synthetic=false
```

`map(String)` chính là phương thức tác giả viết. `map(Object)` được sinh để phù hợp với erasure của `Mapper<T>.map(T)`; vì vậy nó mang bridge flag và synthetic flag.

Hai phương thức có cùng tên nhưng **tham số runtime khác nhau**, do đó:

```java
StringMapper.class.getDeclaredMethod("map", String.class);
StringMapper.class.getDeclaredMethod("map", Object.class);
```

đều có thể tìm được method ở class file sau khi Java compiler đã phát sinh bridge. Kết quả thứ hai biểu diễn bridge; cách dùng Reflection đó không khiến source `StringMapper` thực sự công bố một overload `map(Object)` mới cho lập trình viên viết Java thông thường.

### 4.2. Đọc nhóm `Derived`: bridge không chỉ gắn với generic

```text
score()->Integer | bridge=false synthetic=false
score()->Number | bridge=true synthetic=true
```

Ở đây `Base.score()` trả `Number`, còn `Derived.score()` ghi đè hợp lệ với kiểu trả về hẹp hơn `Integer` (*covariant return*). Vì descriptor JVM gồm cả return type, `javac` có thể tạo bridge `Number score()` để giữ dispatch tương thích với những lời gọi đã biên dịch theo kiểu trả về `Number`.

Điều này cho thấy: **thấy `isBridge() == true` không đủ để kết luận phương thức cha có type parameter generic.** Bridge cũng có thể xuất hiện từ covariant return của phương thức không generic.

Nếu chỉ muốn biết lớp con có phương thức do compiler sinh để bảo toàn override hay không, hãy xem cả quan hệ kế thừa và chữ ký raw. Nếu muốn biết trường hợp nào là generic erasure, cần đọc khai báo generic của supertype.

### 4.3. Đọc nhóm `LambdaHolder`: synthetic chưa chắc bridge

```text
callback()->Runnable | bridge=false synthetic=false
lambda$callback$0()->void | bridge=false synthetic=true
```

Trong bytecode do `javac` sử dụng cho lambda ở ví dụ, compiler tạo một helper `lambda$callback$0()` và đánh dấu là synthetic. Helper này **không thực hiện nhiệm vụ tương thích chữ ký override**, nên `isBridge() == false`.

Một lambda ở source được triển khai bằng cơ chế liên quan `invokedynamic` và runtime của Java. Hãy phân biệt helper method xuất hiện trong class khai báo lambda với đối tượng thực thi `Runnable` được tạo khi chạy. Reflection trên `LambdaHolder.class` đang soi các phương thức được khai báo trong class ấy, không phải liệt kê mọi phương thức có thể có trong implementation object của lambda.

## 5. Xác nhận bằng `javap`: nhìn trực tiếp descriptor và cờ bytecode

Sau khi biên dịch ví dụ, dùng `javap` để đọc class file của các lớp lồng:

```bash
javap -p -s 'BridgeReflectionDemo$StringMapper'
javap -p -s 'BridgeReflectionDemo$Derived'
javap -p -s 'BridgeReflectionDemo$LambdaHolder'
```

Những đoạn descriptor chính:

```text
public java.lang.String map(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

public java.lang.Object map(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
```

```text
java.lang.Integer score();
  descriptor: ()Ljava/lang/Integer;

java.lang.Number score();
  descriptor: ()Ljava/lang/Number;
```

```text
java.lang.Runnable callback();
  descriptor: ()Ljava/lang/Runnable;

private static void lambda$callback$0();
  descriptor: ()V
```

Chuyển sang chế độ chi tiết:

```bash
javap -p -v 'BridgeReflectionDemo$StringMapper'
javap -p -v 'BridgeReflectionDemo$Derived'
javap -p -v 'BridgeReflectionDemo$LambdaHolder'
```

Tìm dòng `flags` của các phương thức. Ví dụ kiểu hiển thị:

```text
flags: (...) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

Với helper lambda:

```text
flags: (...) ACC_PRIVATE, ACC_STATIC, ACC_SYNTHETIC
```

Các cờ này giải thích trực tiếp giá trị mà `isBridge()` và `isSynthetic()` phản ánh. Dùng `javap -c -p` nếu cần xem thân của bridge: nó thường đọc tham số `Object`, chuyển kiểu và gọi implementation `String`. Chi tiết opcode có thể thay đổi tùy compiler; hãy theo **hợp đồng chuyển tiếp** thay vì cố ghi nhớ từng opcode.

Trong PowerShell và các shell Unix, dấu nháy đơn quanh tên lớp lồng giúp `$StringMapper` không bị xử lý như tên biến shell.

## 6. `getDeclaredMethods()` hay `getMethods()`?

Đây là một lựa chọn quan trọng khi viết công cụ dùng Reflection.

### 6.1. `getDeclaredMethods()`: tập method khai báo trực tiếp

```java
Method[] methods = StringMapper.class.getDeclaredMethods();
```

Kết quả gồm phương thức mà class file của `StringMapper` trực tiếp khai báo: `map(String)` và bridge `map(Object)`. Nó cũng có thể bao gồm các phương thức `private`, `protected`, `package-private` hay synthetic nếu chúng được khai báo tại đó.

Nó **không bao gồm** các phương thức chỉ được thừa kế từ superclass hoặc interface mà class chưa khai báo trực tiếp. Nó không trả constructors; dùng `getDeclaredConstructors()` để đọc constructor.

Dùng khi muốn:

- Kiểm tra chính xác compiler đã đặt những method nào vào **class này**.
- Tìm bridge hoặc helper synthetic của class.
- Debug sự thay đổi bytecode của một lớp cụ thể.
- Quét annotation chỉ do class hiện tại khai báo, nếu chính sách scanner là như vậy.

### 6.2. `getMethods()`: tập phương thức public có thể nhìn thấy

```java
Method[] methods = StringMapper.class.getMethods();
```

Kết quả gồm public methods được khai báo và public methods được thừa kế theo quy tắc Reflection. Nó có thể có bridge public và các phương thức từ `Object`, interface, hoặc superclass.

Dùng khi cần thấy **public surface** có thể gọi được trên class. Nhưng nếu mục tiêu là “đếm số method lập trình viên đã viết”, `getMethods().length` sẽ cho kết quả sai vì inherited methods và compiler-generated methods.

Lưu ý: `getDeclaredMethods()` và `getMethods()` **không bảo đảm thứ tự**. Hãy sắp xếp bằng tiêu chí cụ thể trước khi hiển thị, so sánh snapshot hoặc kiểm thử.

### 6.3. Vì sao `getDeclaredMethod` có thể gây hiểu nhầm?

```java
Method real = StringMapper.class.getDeclaredMethod(
        "map", String.class);

Method bridge = StringMapper.class.getDeclaredMethod(
        "map", Object.class);
```

Tham số truyền vào `getDeclaredMethod` là **runtime parameter types**, không phải type arguments ở source. Sau erasure, bridge nhận `Object`, nên kết quả thứ hai là một phương thức có thật trong class file.

Nếu có hai phương thức JVM cùng tên và cùng danh sách parameter types nhưng khác return type (có thể do covariant return và bridge), Reflection cung cấp quy tắc chọn method khi dùng `getDeclaredMethod`; đừng dùng một phép tra cứu theo tên/tham số để **điều tra đầy đủ tất cả method**. Hãy dùng `getDeclaredMethods()` và kiểm tra return type, `isBridge`, `isSynthetic` của từng phần tử.

## 7. Chữ ký generic và raw descriptor: không nên gộp làm một

`Method.getReturnType()` và `Method.getGenericReturnType()` trả thông tin liên quan nhưng không trùng nhau:

```java
Method m = Mapper.class.getDeclaredMethod("map", Object.class);

System.out.println(m.getReturnType());        // class java.lang.Object
System.out.println(m.getGenericReturnType()); // T
```

`Mapper<T>.map(T)` dùng một type variable `T` trong source. Sau erasure, kiểu trả về runtime là `Object`, nhưng metadata generic của method khai báo trong interface có thể cho Reflection biết đây là `T`.

Đối với bridge `StringMapper.map(Object)`, bạn thường thấy thông tin raw/erased (như `Object`) bởi phương thức bridge được compiler sinh ra để nối descriptor, trong khi implementation `map(String)` có kiểu trả về `String`.

Để xem quan hệ giữa lớp con và generic interface, kiểm tra:

```java
StringMapper.class.getGenericInterfaces();
```

Đầu ra có thể chứa một `ParameterizedType` biểu diễn `Mapper<String>`. Đây là **metadata của quan hệ supertype**; không có nghĩa mọi instance `Mapper<String>` mang một tham số type runtime có thể kiểm tra bằng `instanceof Mapper<String>`.

### 7.1. Tham số có bound khác `Object`

Nếu interface được khai báo:

```java
interface NumberMapper<T extends Number> {
    T map(T value);
}
```

thì erasure của type variable `T` là `Number`, nên descriptor tương ứng dùng `Number`, không phải `Object`. Khi thực hiện Reflection, hãy tìm method bridge với tham số raw phù hợp (`Number.class`) và đừng mặc định mọi bridge generic đều nhận `Object`.

Ví dụ chữ ký:

```text
map(Number):Number
```

có thể là đường chuyển tiếp đến implementation cụ thể có tham số `Integer`. `Object` xuất hiện ở ví dụ chính vì type variable của interface **không có bound tường minh**.

### 7.2. Synthetic và bridge không phải là “type erasure itself”

Erasure là quy tắc dịch kiểu generic sang dạng tương thích bytecode. Một method generic có thể bị erasure mà **không sinh bridge**:

```java
static <T> T identity(T value) {
    return value;
}
```

Nếu không có quan hệ override cần nối hai descriptor khác nhau, method `identity` không cần bridge. Ngược lại, phương thức không generic với covariant return có thể cần bridge. Vì vậy:

- Có generic **không suy ra** `isBridge() == true`.
- Có bridge **không suy ra** phương thức cha generic.
- Có synthetic **không suy ra** có bridge.
- Không có bridge **không suy ra** không hề có type erasure.

## 8. Cách lọc method khi xây công cụ quét API

Một framework có thể quét method để tạo tuyến REST, ghi thông tin audit, xây metadata hoặc đăng ký handler. Nếu không phân biệt bridge, một phương thức source có thể được xử lý hai lần khi class file chứa cả implementation và bridge.

### 8.1. Lọc các phương thức compiler-generated trong một lượt quét

Một chính sách hợp lý **khi chỉ muốn những phương thức người lập trình công bố trực tiếp trên class**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

static List<Method> sourceLikeDeclaredMethods(Class<?> type) {
    return Arrays.stream(type.getDeclaredMethods())
            .filter(m -> !m.isBridge())
            .filter(m -> !m.isSynthetic())
            .toList();
}
```

Đoạn trên là **một utility method minh họa**, cần đặt trong class và có import phù hợp khi dùng. Nó giữ các method không có hai cờ, nhưng không đảm bảo tìm được “toàn bộ API ở source” trong mọi ngữ cảnh:

- Phương thức **thừa kế** không nằm trong `getDeclaredMethods()`.
- Interface default methods, annotation, override và generic hierarchy vẫn cần chính sách riêng.
- Những cấu trúc class file do các compiler hoặc bytecode generator khác sinh có thể có cờ/metadata khác nhau.
- Không phải mọi method không synthetic đều công khai ra bên ngoài; vẫn phải kiểm tra `Modifier.isPublic(...)` hoặc các access rules khác.

Nếu bạn chỉ muốn loại method bridge nhưng **vẫn cần quan sát synthetic helper**, chỉ dùng:

```java
.filter(m -> !m.isBridge())
```

Không có một bộ lọc duy nhất đúng cho mọi nhiệm vụ. Chính sách “chỉ source-like methods” hợp lý cho tài liệu nội bộ đơn giản, nhưng sẽ bỏ qua dữ liệu hữu ích khi debug bytecode.

### 8.2. Tránh đếm trùng nhưng vẫn bảo toàn thông tin annotation

Giả sử một scanner tạo một mô tả API cho mỗi phương thức triển khai. Bridge có thể xuất hiện cạnh phương thức cùng nhiệm vụ nghiệp vụ. Một cách tiếp cận:

1. Quét `getDeclaredMethods()` hoặc `getMethods()` tùy phạm vi scanner.
2. Xác định trước liệu scanner cần **implementation method**, **interface contract**, hay cả hai.
3. Nhận diện bridge bằng `isBridge()`, không suy luận chỉ từ tên hay kiểu trả về.
4. Khi bridge đại diện cho một implementation, cố tìm method đích qua **tên, quan hệ kiểu tham số, quan hệ kiểu trả về và hierarchy**; đừng ghép bừa method đầu tiên cùng tên.
5. Với annotation, cần xác định nơi annotation được khai báo và quy tắc framework có hợp nhất metadata từ interface, superclass, method implementation hay bridge không.
6. Dùng test với generic interface, covariant return, overload, inherited method và raw type để kiểm chứng scanner thực sự không bỏ sót hoặc đăng ký trùng.

Đừng mặc định rằng annotation trên method source luôn hoặc không bao giờ được compiler chép sang bridge trong mọi công cụ/JDK. Nếu thông tin annotation có tác dụng pháp lý/nghiệp vụ, hãy kiểm tra bytecode thực và chính sách của framework. Không nên xóa bridge khỏi kết quả **trước khi** phân giải quan hệ override nếu scanner cần nó để hiểu một method gốc.

### 8.3. Đừng nhận diện bridge qua tên method

Trong ví dụ, bridge vẫn có tên `map`, giống implementation. Trong ví dụ covariant return, bridge có tên `score`, giống method thật. Nó **không có một tiền tố tiêu chuẩn** như `bridge$`.

Ngược lại, tên `lambda$callback$0` ở ví dụ là một chi tiết sinh mã của `javac`; tên khác hoặc cách triển khai khác hoàn toàn có thể xảy ra.

Tiêu chí chuẩn để xác định bridge ở Reflection là `Method.isBridge()`. Dùng `isSynthetic()` để nhận biết synthetic method nói chung, không suy đoán từ tiền tố tên.

## 9. Các tình huống kiểm tra điển hình

### Tình huống A: Reflection thấy `map(Object)` dù source chỉ có `map(String)`

Kiểm tra:

```java
for (Method m : StringMapper.class.getDeclaredMethods()) {
    System.out.println(m.getName() + ": " + m.isBridge());
}
```

Nếu `map(Object)` là bridge, bạn sẽ nhìn thấy `true`. Dùng `javap -v` để kiểm tra `ACC_BRIDGE` và `ACC_SYNTHETIC`. Đừng sửa class source để “xóa” một phương thức compiler đã tạo: nó cần thiết cho dispatch đúng.

### Tình huống B: Quét handler khiến cùng một chức năng xuất hiện hai lần

Nếu hai `Method` có cùng tên nhưng một có `isBridge() == true`, cần xem chúng có cùng implementation nghiệp vụ không. Với scanner hướng tới source-level API, lọc hoặc gộp bridge theo đúng quy tắc resolution. Kiểm thử với annotation ở interface và implementation trước khi coi filtering là đủ.

### Tình huống C: Synthetic method xuất hiện dù class không dùng generics

Ví dụ method helper của lambda. Một method có `isSynthetic() == true`, `isBridge() == false` không chứng minh class có generic. Dùng `javap` và khai báo source để hiểu compiler tạo method đó vì lý do gì.

### Tình huống D: Override covariant return dẫn tới hai kết quả cùng tên, cùng tham số

Với `Number score()` ở cha và `Integer score()` ở con, JVM có thể có bridge trả `Number` và implementation trả `Integer`. Sử dụng **toàn bộ `getDeclaredMethods()`** để nghiên cứu cặp method; tra cứu một method theo tên và danh sách tham số chưa chắc giúp phân tích đầy đủ khác biệt return type.

### Tình huống E: Kết quả quét không ổn định giữa các lần chạy

Theo đặc tả Reflection, thứ tự phần tử trong mảng trả về từ `getDeclaredMethods()` không được bảo đảm. Hãy sort theo tiêu chí ổn định như tên, danh sách tham số và kiểu trả về khi xuất báo cáo. Không dựa vào vị trí `[0]` để quyết định phương thức nào “thật” hay “bridge”.

### Tình huống F: Thư viện bytecode hoặc compiler khác javac

Đừng giả định class file nào cũng giống bytecode do `javac --release 17` tạo. Một số class file được sinh bởi công cụ runtime, weaving hoặc compiler ngôn ngữ JVM khác. `isBridge()`/`isSynthetic()` phản ánh cờ thực trong method hiện tại; ý nghĩa nghiệp vụ hoặc nguồn sinh method cần xác minh theo toolchain cụ thể.

## 10. Quy trình debug thực tế

Khi công cụ Reflection báo có phương thức lạ:

1. **Chốt class cần kiểm tra** và gọi `getDeclaredMethods()` để xem chính phương thức nằm trong class file đó.
2. **In tối thiểu**: tên, parameter types, return type, `isBridge()`, `isSynthetic()`, `getDeclaringClass()`.
3. **Sort kết quả**, bởi Reflection không đảm bảo thứ tự.
4. Nếu là bridge, **tìm supertype generic hoặc method covariant return** và so sánh descriptor trước/sau erasure.
5. Nếu chỉ synthetic, **kiểm tra lambda/helper hoặc cơ chế sinh mã khác**; không tự coi đó là bridge.
6. Dùng `javap -p -s` để xem descriptor và `javap -p -v` để kiểm tra flags. Khi cần xác minh hướng gọi, dùng `javap -p -c`.
7. **Quyết định theo mục đích scanner**: giữ method để debug bytecode, hoặc lọc/gộp nó khi hiển thị logical API.
8. **Thử lại** với interface generic, class kế thừa generic, covariant return, overload và code có lambda để kiểm tra logic phân loại.

Một bảng tra cứu nhanh:

| Kết quả quan sát | Ý nghĩa nên điều tra |
| --- | --- |
| `bridge=true, synthetic=true`, tham số `Object` | Bridge do erasure kiểu generic không bound. |
| `bridge=true, synthetic=true`, khác return type | Có thể là bridge hỗ trợ covariant return. |
| `bridge=false, synthetic=true`, tên giống helper lambda | Compiler-generated helper, không làm nhiệm vụ bridge override. |
| `bridge=false, synthetic=false` | Method thường, nhưng vẫn cần kiểm tra access/public/inherited nếu mô tả API. |
| `getMethods()` cho nhiều method hơn `getDeclaredMethods()` | Có thể vì tập public inherited, không nhất thiết đều là bridge. |
| Compiler báo `name clash` | Chữ ký source và erasure xung đột; không giải quyết bằng cách thêm phương thức bridge thủ công. |

## 11. Các lỗi tư duy cần tránh

**Sai lầm 1 — `isSynthetic()` nghĩa là `isBridge()`.** Thực tế synthetic bao gồm nhiều loại method do compiler sinh. Ví dụ helper lambda ở chương trình chạy được là synthetic nhưng không bridge.

**Sai lầm 2 — mọi generic method đều có bridge.** Một phương thức generic độc lập không tham gia override thường không cần bridge. Bridge được sinh khi cần giữ tương thích lời gọi/override sau biên dịch.

**Sai lầm 3 — bridge là overload source mà người dùng phải gọi.** Bridge là chi tiết biên dịch để đảm bảo dispatch. Framework và reflection có thể thấy nó; lời gọi Java source nên tuân thủ hợp đồng generic hoặc covariant return đã công bố.

**Sai lầm 4 — `getDeclaredMethods()` chỉ trả phương thức do programmer viết.** Nó còn có thể trả bridge và helper synthetic được khai báo trong class file.

**Sai lầm 5 — có thể lọc hết synthetic mà không đánh giá nhu cầu.** Đối với tài liệu source API, lọc synthetic có thể hợp lý. Nhưng trong công cụ debug, coverage hoặc instrumenting bytecode, bỏ hết synthetic có thể làm mất dữ liệu cần thiết.

**Sai lầm 6 — reflection method order là cố định.** Java không hứa thứ tự; mọi báo cáo và test so sánh nên tự sắp xếp hoặc so theo tập hợp.

**Sai lầm 7 — `getGenericReturnType()` luôn cho biết type argument runtime của đối tượng.** API này mô tả khai báo/metadata generic của method, không tự tái tạo specialization runtime của mọi instance `List<T>`.

**Sai lầm 8 — `isBridge()` cho biết chính xác method đích được gọi.** Cờ chỉ nhận diện bridge. Muốn biết bridge chuyển tiếp tới đâu, cần xem quan hệ kiểu hoặc inspect bytecode (`javap -c`) và tránh heuristic chỉ dựa vào tên.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `StringMapper.class.getDeclaredMethods()` có thể chứa cả `map(String)` và `map(Object)` trong khi source chỉ định nghĩa `map(String)`?

<details>
<summary>Đáp án</summary>

`Mapper<T>.map(T)` erases thành `map(Object):Object`; implementation sau khi gắn `T = String` là `map(String):String`. Compiler sinh bridge `map(Object):Object` để giữ dispatch từ interface/supertype. Bridge được Reflection nhìn thấy với `isBridge() == true`.

</details>

**Câu 2.** `isSynthetic() == true` có chứng minh một method là bridge không?

<details>
<summary>Đáp án</summary>

Không. Synthetic method có thể là helper do compiler tạo để thực hiện lambda hoặc mục đích khác. Kiểm tra `isBridge()` riêng; nếu cần, đọc `ACC_BRIDGE`/`ACC_SYNTHETIC` bằng `javap -v`.

</details>

**Câu 3.** Khi quét một class để tìm method do class đó khai báo, nên bắt đầu bằng `getMethods()` hay `getDeclaredMethods()`?

<details>
<summary>Đáp án</summary>

`getDeclaredMethods()` vì nó truy xuất method khai báo tại class hiện tại, gồm cả non-public và synthetic. Nếu mục tiêu là toàn bộ public surface kể cả inherited methods thì cân nhắc `getMethods()`. Cả hai đều có thể trả compiler-generated methods; cần chính sách filtering phù hợp.

</details>

**Câu 4.** Vì sao `Derived.score()` cũng có thể sinh bridge dù không sử dụng generics?

<details>
<summary>Đáp án</summary>

`Base.score()` trả `Number`, `Derived.score()` override bằng `Integer` (covariant return). Descriptor JVM khác return type, nên compiler có thể tạo bridge `Number score()` để đáp ứng lời gọi theo descriptor của superclass.

</details>

**Câu 5.** Tại sao không nên nhận diện method synthetic bằng tên `lambda$...`?

<details>
<summary>Đáp án</summary>

Tên helper là chi tiết compiler, không phải định danh chuẩn của mọi synthetic method. Reflection có `isSynthetic()`, và `javap -v` cho thấy `ACC_SYNTHETIC`. Một synthetic method có thể không có tiền tố `lambda$` và một method bridge thường có cùng tên với implementation.

</details>

## 13. Tóm lược kỹ thuật

**`Method.isBridge()` kiểm tra bridge method; `Method.isSynthetic()` kiểm tra synthetic method.** Bridge thường được compiler tạo để điều hòa sự khác biệt descriptor sau generic erasure hoặc covariant return, trong khi synthetic là nhóm rộng hơn, bao gồm cả helper lambda do compiler sinh.

Khi cần phân tích chính xác, sử dụng **`getDeclaredMethods()` + kiểu tham số/return + `isBridge()` + `isSynthetic()`**, kết hợp `javap -s/-v` để xác minh descriptor và flags. Khi xây công cụ quét API, xác định rõ bạn muốn **method hiện diện trong bytecode** hay **method thể hiện hợp đồng source**, rồi lọc/gộp theo mục đích. Không phụ thuộc vào tên helper hoặc thứ tự phương thức mà Reflection trả về.