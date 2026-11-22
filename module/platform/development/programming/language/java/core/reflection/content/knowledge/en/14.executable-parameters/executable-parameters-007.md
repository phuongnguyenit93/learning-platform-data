# Modifier của tham số và giới hạn metadata có sẵn trong Java Reflection

## 1. Vấn đề cần giải quyết

Java Reflection không chỉ cho phép tìm lớp, phương thức và constructor. Một `Method` hoặc `Constructor` còn có thể được khảo sát ở mức **tham số hình thức** (formal parameter) qua `java.lang.reflect.Parameter`. Điều này hữu ích khi viết framework ánh xạ request, dependency injection, serializer, trình tạo tài liệu API hoặc công cụ kiểm tra chữ ký.

Tuy nhiên, không phải mọi thông tin từng xuất hiện trong tệp nguồn `.java` đều được giữ lại trong tệp `.class`. Đặc biệt, cần tách ba loại dữ liệu:

1. **Cấu trúc chữ ký**: số lượng, thứ tự, kiểu runtime của tham số. JVM lưu chúng trong *method descriptor*; thông tin này không phụ thuộc tùy chọn `javac -parameters`.
2. **Modifier/cờ và metadata của tham số**: `final`, `synthetic`, `mandated/implicit` và tên tham số có thể được phản ánh từ attribute `MethodParameters`, nếu class file cung cấp thông tin tương ứng.
3. **Cú pháp nguồn**: cách viết từ khóa, tên biến cục bộ, chú thích và formatting ban đầu không thể được tái tạo đầy đủ chỉ từ `Parameter`.

Ví dụ nguồn:

```java
public void send(final String topic, int retries) {
}
```

Reflection luôn có thể tìm chữ ký tham số theo kiểu `String` và `int` trong một class file hợp lệ. Nhưng nó **không bảo đảm** biết tên `topic`, `retries` hoặc biết `topic` được khai báo `final` nếu metadata cần thiết đã bị loại bỏ.

**Mục tiêu bài học:** đọc đúng `Parameter.getModifiers()` và các API liên quan; hiểu `MethodParameters`, `-parameters`, những tham số implicit/synthetic và giới hạn khi metadata không tồn tại.

## 2. Cách lấy `Parameter` từ một executable

`java.lang.reflect.Executable` là superclass chung của `Method` và `Constructor<?>`. Cả hai đều có:

- `getParameterCount()`: số lượng tham số trong chữ ký phản ánh.
- `getParameterTypes()`: mảng `Class<?>[]` biểu diễn kiểu runtime đã erasure.
- `getGenericParameterTypes()`: các `Type` biểu diễn kiểu generic nếu còn metadata phù hợp.
- `getParameters()`: mảng `Parameter[]` theo thứ tự tham số.
- `getParameterAnnotations()`: annotation trên các parameter theo khả năng hiển thị ở runtime.
- `isVarArgs()`: executable được đánh dấu varargs hay không.

Mỗi `Parameter` có thể cung cấp:

| API | Ý nghĩa |
| --- | --- |
| `getDeclaringExecutable()` | `Method` hoặc `Constructor` sở hữu tham số |
| `getType()` | Kiểu runtime dạng `Class<?>`, ví dụ `String[].class` |
| `getParameterizedType()` | Kiểu generic dạng `Type` nếu thông tin tồn tại |
| `getName()` | Tên từ metadata hoặc tên thay thế như `arg0` |
| `isNamePresent()` | Có tên tham số được cung cấp theo class file hay không |
| `getModifiers()` | Bit modifier Java của tham số |
| `isImplicit()` | Tham số được khai báo ngầm định theo ngôn ngữ? |
| `isSynthetic()` | Tham số là cấu trúc sinh bởi compiler, không khai báo tường minh hay ngầm định trong nguồn? |
| `isVarArgs()` | Tham số biểu diễn danh sách đối số biến độ dài? |
| `getAnnotations()` / `getAnnotatedType()` | Metadata annotation và type-use annotation nếu được lưu, giữ retention phù hợp |

Ví dụ minh họa cách lấy `Parameter[]`:

```java
Method m = Service.class.getDeclaredMethod(
        "send", String.class, int.class);
Parameter[] parameters = m.getParameters();

for (int i = 0; i < parameters.length; i++) {
    Parameter p = parameters[i];
    System.out.println(i + ": " + p.getType().getTypeName());
}
```

Đây là **đoạn code minh họa**: cần import `java.lang.reflect.Method`, `java.lang.reflect.Parameter`, định nghĩa `Service.send(String,int)` và xử lý `NoSuchMethodException`. Ví dụ độc lập đầy đủ nằm ở mục 5.

## 3. `Parameter.getModifiers()` thực sự biểu diễn gì?

`Parameter.getModifiers()` trả về một `int` chứa các bit modifier của tham số theo mô hình Reflection. Với tham số Java được **khai báo tường minh**, modifier Java nguồn thông dụng và hợp lệ tại vị trí này là `final`. Các từ khóa `public`, `private`, `protected`, `static`, `abstract` không phải modifier hợp lệ của một formal parameter.

Kiểm tra tham số có modifier `final`:

```java
boolean isFinal = Modifier.isFinal(parameter.getModifiers());
```

`Modifier.isFinal(int)` kiểm tra bit `final`. Tránh gọi `Modifier.isPublic(parameter.getModifiers())` rồi từ đó suy luận về quyền truy cập của tham số; bản thân formal parameter không có access level giống field hay method.

Ví dụ:

```java
void save(final String name, int count) {
}
```

Nếu compiler đã lưu metadata tương ứng, Reflection có thể phát hiện `final` ở tham số `name`, còn `count` không có `final`. Nhưng **kết quả `getModifiers() == 0` không chứng minh trong tệp nguồn tham số không có modifier nào**: có thể `MethodParameters` đã bị bỏ hoặc thông tin bị mất qua công cụ sinh/chỉnh bytecode.

### Modifier khác với tên và kiểu

- `getType()` thường vẫn trả về kiểu runtime có thể sử dụng dù tên/modifier bị mất; kiểu nằm trong descriptor.
- `getName()` có thể trả `arg0` khi thiếu tên; nó **không đồng nghĩa tên nguồn là `arg0`**.
- `getModifiers()` không thay thế `isImplicit()`, `isSynthetic()` hay `isVarArgs()` khi cần phân loại tham số.
- `Modifier.toString(parameter.getModifiers())` chỉ diễn giải các modifier mà tiện ích `Modifier` biết hiển thị; đừng dùng nó để kết luận toàn bộ loại cờ trong `MethodParameters`.

Với Java 20+, `Parameter.accessFlags()` cung cấp một tập `AccessFlag` được phản ánh cho tham số. Khi viết chương trình tương thích **Java 17**, hãy dùng các API `getModifiers()`, `isImplicit()` và `isSynthetic()`; không đưa `accessFlags()` vào chương trình Java 17 vì API đó chỉ xuất hiện sau.

## 4. Class file lưu những gì trong `MethodParameters`?

JVM lưu chữ ký của method/constructor qua descriptor. `MethodParameters` là **attribute tùy chọn**, được định nghĩa trong Java Virtual Machine Specification. Khi có mặt, attribute này chứa dữ liệu từng tham số theo thứ tự tương ứng với descriptor:

- `name_index`: chỉ mục tên tham số trong constant pool, hoặc `0` nếu không có tên.
- `access_flags`: tập bit mô tả một số đặc tính của tham số.

Ba cờ quan trọng:

| Cờ trong `MethodParameters` | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `ACC_FINAL` | `0x0010` | Tham số được khai báo `final` |
| `ACC_SYNTHETIC` | `0x1000` | Tham số được sinh như chi tiết triển khai compiler; không khai báo trực tiếp hoặc ngầm định trong nguồn theo quy tắc ngôn ngữ |
| `ACC_MANDATED` | `0x8000` | Tham số được ngôn ngữ quy định ngầm định; compiler cần tạo tham số đó |

`ACC_MANDATED` và `ACC_SYNTHETIC` mang ý nghĩa **khác nhau**: một tham số do đặc tả ngôn ngữ bắt buộc có thể là *implicit*, còn tham số synthetic có thể chỉ phục vụ triển khai của compiler. Không ghép chúng thành một nhãn “tham số tự sinh” rồi mất sự phân biệt.

Ánh xạ API thường dùng:

```java
parameter.isImplicit();   // Liên quan trạng thái implicit / mandated
parameter.isSynthetic();  // Liên quan trạng thái synthetic
parameter.getModifiers(); // Các bit modifier của tham số
```

Đây chỉ là lời gọi minh họa (chưa khai báo biến `parameter`). Với file class thiếu `MethodParameters`, các cờ này **không có đủ dữ liệu** để thuật lại chính xác tất cả đặc điểm khi viết mã nguồn. Đặc biệt, `false` ở `isImplicit()` hoặc `isSynthetic()` không nên được coi là bằng chứng tuyệt đối rằng compiler không tạo tham số.

**Không nhầm vị trí các cờ:** `ACC_VARARGS` ở `method_info.access_flags` mô tả đặc tính varargs của *phương thức*, không phải một cờ `ACC_VARARGS` trong `MethodParameters`. `Parameter.isVarArgs()` nhận diện tham số cuối thích hợp qua metadata executable.

### Vì sao `javac -parameters` quan trọng?

Lệnh:

```bash
javac -parameters Example.java
```

yêu cầu `javac` ghi metadata về **tên formal parameter** của constructor và method để Reflection có thể lấy bằng `Executable.getParameters()`. Trên bytecode được `javac` sinh, tùy chọn này cũng giúp công cụ thấy `MethodParameters` cùng các cờ parameter hiện diện.

Nếu biên dịch không có `-parameters`, nhiều parameter tường minh sẽ không còn tên thật và các cờ gắn với `MethodParameters` có thể không quan sát được. JVM vẫn cần descriptor kiểu tham số để xác minh và gọi method, nên `getParameterTypes()`/`getParameterCount()` tiếp tục hoạt động.

Lưu ý sự khác biệt:

- `-parameters`: tạo metadata tham số dành cho Java Reflection.
- `-g`: tạo debug information, ví dụ `LocalVariableTable`/`LineNumberTable`. Có thể giúp debugger hoặc công cụ bytecode, nhưng **không thay thế bảo đảm của `-parameters` cho `Parameter.isNamePresent()`**.
- `-g:none`: bỏ debug information, không có nghĩa bắt buộc loại bỏ `MethodParameters` nếu đã sử dụng `-parameters`.

Không giả định mọi compiler, obfuscator hoặc bytecode transformer đều giữ các attribute như `javac`. Nếu framework cần tên tham số đáng tin, hãy quy định rõ build config hoặc cung cấp annotation tên tường minh làm phương án thay thế.

## 5. Ví dụ Java 17+ runnable: modifier và metadata

Tạo tệp **`ParameterFlagsDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Parameter;

public class ParameterFlagsDemo {
    public static void send(
            final String topic, int count, String... tags) {
        // Ví dụ chỉ dùng để quan sát chữ ký.
    }

    static class Host {
        class Member {
            Member(int number) {
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Method send = ParameterFlagsDemo.class.getDeclaredMethod(
                "send", String.class, int.class, String[].class);
        Parameter[] params = send.getParameters();

        System.out.println("method params: " + params.length);
        for (int i = 0; i < params.length; i++) {
            Parameter p = params[i];
            System.out.println(i + " type=" + p.getType().getTypeName()
                    + " name=" + p.getName()
                    + " present=" + p.isNamePresent()
                    + " final=" + Modifier.isFinal(p.getModifiers())
                    + " implicit=" + p.isImplicit()
                    + " synthetic=" + p.isSynthetic()
                    + " varargs=" + p.isVarArgs());
        }

        System.out.println("method varargs: " + send.isVarArgs());

        Constructor<?> memberCtor =
                Host.Member.class.getDeclaredConstructor(
                        Host.class, int.class);
        System.out.println("member constructor params: "
                + memberCtor.getParameterCount());
        System.out.println("first parameter is Host: "
                + (memberCtor.getParameterTypes()[0] == Host.class));
    }
}
```

Biên dịch với metadata tên tham số:

```bash
javac -parameters ParameterFlagsDemo.java
java ParameterFlagsDemo
```

**Stdout mong đợi với `javac` JDK 17+ và class file do chính lệnh trên biên dịch:**

```text
method params: 3
0 type=java.lang.String name=topic present=true final=true implicit=false synthetic=false varargs=false
1 type=int name=count present=true final=false implicit=false synthetic=false varargs=false
2 type=java.lang.String[] name=tags present=true final=false implicit=false synthetic=false varargs=true
method varargs: true
member constructor params: 2
first parameter is Host: true
```

Giải thích:

1. `send` có ba tham số, lấy `Class<?>` và thứ tự từ descriptor; kiểu thứ ba là `String[]` ở runtime dù nguồn viết `String...`.
2. `-parameters` làm `isNamePresent()` là `true` cho những tham số có tên trong class file. `getName()` trả đúng `topic`, `count`, `tags`.
3. `Modifier.isFinal(...)` là `true` cho tham số `topic`; hai tham số sau không `final`.
4. Ba tham số `send` đều được khai báo tường minh nên `isImplicit()` và `isSynthetic()` là `false`.
5. `isVarArgs()` chỉ đúng với tham số cuối `tags`; `Method.isVarArgs()` đúng cho method `send`.
6. `Host.Member` là non-static member inner class, vì vậy constructor mà Reflection thấy có thêm tham số đầu kiểu `Host` và tổng cộng hai tham số, dù nguồn chỉ ghi `Member(int)`. Chương trình **không giả định** tên hay cờ implicit của tham số ẩn là cố định trên mọi compiler.

### Kiểm chứng khi không có `-parameters`

Để thấy sự khác biệt, biên dịch lại (đè các tệp `.class` được tạo từ chính ví dụ này):

```bash
javac ParameterFlagsDemo.java
java ParameterFlagsDemo
```

Điều quan trọng cần kiểm tra là `getParameterCount()` và các kiểu của `send` vẫn giữ nguyên, trong khi ba tên tham số tường minh có thể không còn được lưu. Với `javac` thông thường, `isNamePresent()` ở các tham số ấy là `false` và `getName()` thường trả `arg0`, `arg1`, `arg2`. Những cờ phụ thuộc `MethodParameters` cũng có thể không còn được phản ánh.

Không trình bày một mẫu stdout thứ hai như thể mọi compiler/bytecode transformer đều đưa ra cùng cờ: phần nào trong metadata bị giữ lại là đặc tính của class file thực tế.

### Xem bytecode bằng `javap`

```bash
javap -v -p ParameterFlagsDemo
```

Tìm các mục `MethodParameters`, `descriptor` và `flags` của method `send`. Khi có `-parameters`, bạn có thể tìm tên và cờ `final` trong dữ liệu tham số. Descriptor của `send` thể hiện `String`, `int` và `String[]`; không cần tên để mô tả các kiểu này.

Nếu không có `MethodParameters`, đó là giới hạn dữ liệu ở **class file**; Reflection không thể đoán lại chính xác tên hay modifier nguồn chỉ dựa vào số lượng và kiểu tham số.

## 6. `isImplicit`, `isSynthetic` và tham số do compiler tạo

### 6.1. Inner class và enclosing instance

Non-static inner member class gắn với một instance của lớp bao ngoài. Constructor của nó thường có một tham số runtime đứng đầu để nhận đối tượng bao ngoài.

```java
class House {
    class Room {
        Room(int floor) {
        }
    }
}
```

Từ Reflection:

```java
Constructor<?> ctor =
        House.Room.class.getDeclaredConstructor(House.class, int.class);
Class<?>[] runtimeTypes = ctor.getParameterTypes();
```

Đây là đoạn minh họa cần import `java.lang.reflect.Constructor` và xử lý checked exception. `runtimeTypes[0]` là `House.class`; `runtimeTypes[1]` là `int.class`.

Tham số cho enclosing instance được sinh để thể hiện ngữ nghĩa của inner class. Khi có metadata cần thiết, compiler có thể ghi cờ mô tả nó là implicit/mandated. Nhưng việc `getParameters()` có trả đúng danh sách kiểu **không đồng nghĩa** `isImplicit()` hay `isSynthetic()` luôn báo đúng ý nghĩa nguồn khi metadata bị loại bỏ. Bài toán gọi constructor phải dựa vào signature và một enclosing instance thật, không chỉ vào một flag.

### 6.2. Enum constructor

Constructor của enum nhận các tham số hỗ trợ tên và ordinal ở mức bytecode, ngoài các tham số được viết trong nguồn. Đây là dữ liệu liên quan tới cách JVM biểu diễn enum và có thể được phản ánh ở chữ ký constructor.

```java
enum Mode {
    FAST(1), SAFE(2);

    private final int speed;

    Mode(int speed) {
        this.speed = speed;
    }
}
```

Không được kết luận rằng chỉ có duy nhất một tham số runtime vì nguồn viết `Mode(int)`. Tuy nhiên, **không cố gọi enum constructor bằng Reflection**: `Constructor.newInstance(...)` không cho tạo enum object theo cách này và có thể ném `IllegalArgumentException`.

Khi phân tích `Parameter[]` của enum, cần tách các tham số ngầm định hoặc do compiler thêm với những tham số người viết khai báo. Với metadata không đầy đủ, đừng xây công cụ chỉ bằng bộ lọc `!p.isSynthetic() && !p.isImplicit()` rồi tin rằng nó tái tạo chữ ký nguồn hoàn hảo.

### 6.3. Local/anonymous class và biến captured

Các local/anonymous classes có thể capture biến local effectively final hoặc cần truyền ngữ cảnh bao ngoài vào constructor. Compiler có thể thêm các tham số kỹ thuật, chẳng hạn để chuyển những giá trị captured.

Vì dạng chữ ký phụ thuộc context và compiler, hãy kiểm tra `getDeclaredConstructors()`, `getParameterTypes()` và metadata thực tế. Không áp đặt “tham số đầu luôn là outer class” cho mọi local/anonymous class; quy tắc về enclosing instance của **non-static member inner class** không bao phủ toàn bộ trường hợp.

### 6.4. Không đồng nhất implicit, synthetic với `final`

Một tham số có thể:

- Được viết tường minh và có `final`.
- Được viết tường minh mà không có `final`.
- Được ngôn ngữ quy định ngầm định (implicit/mandated).
- Do compiler tạo như một chi tiết triển khai (synthetic).

Những khía cạnh này **không cùng một trục phân loại**. `Modifier.isFinal(p.getModifiers())` nói về cờ `final`; `p.isImplicit()` và `p.isSynthetic()` nói về nguồn gốc parameter theo thông tin phản ánh. Không suy ra `final` chỉ vì tham số được compiler sinh, và cũng không cho rằng `final` nghĩa là synthetic.

## 7. Tên tham số: `getName` khác `isNamePresent`

Ví dụ:

```java
public void register(String username, int attempts) {
}
```

Nếu thiếu metadata tên:

```java
Parameter[] ps = method.getParameters();
System.out.println(ps[0].getName());        // Có thể là arg0
System.out.println(ps[0].isNamePresent());   // false nếu không có tên
```

Đây là đoạn minh họa cần `method` đại diện cho đúng method. `getName()` không trả `null` chỉ vì metadata tên thiếu; nó cung cấp một tên thay thế để lập trình viên vẫn có thể sử dụng `Parameter` API.

**Quy tắc cho framework:** muốn dùng tên parameter làm khóa dependency injection hoặc tên query argument, hãy kiểm tra `isNamePresent()`. Nếu false, không tự ý dùng `arg0` làm tên API thật của người sử dụng. Có thể yêu cầu build bật `-parameters` hoặc sử dụng annotation chứa tên đã khai báo tường minh.

Kể cả `isNamePresent() == true`, metadata có thể đã bị **obfuscate** hoặc sửa bởi bytecode transformer. Điều đó chứng minh class file hiện tại cung cấp một tên, không chứng minh đó chắc chắn là token trong source trước khi biến đổi.

## 8. `getType`, `getParameterizedType` và varargs không phải modifier thông thường

### 8.1. Generic erasure

Cho method:

```java
void consume(java.util.List<String> names) {
}
```

- `Parameter.getType()` trả `java.util.List.class`: kiểu runtime sau type erasure.
- `Parameter.getParameterizedType()` có thể cho thấy `List<String>` khi `Signature` attribute được lưu phù hợp.
- `getModifiers()` không có nhiệm vụ chứa thông tin `<String>`.
- Nếu mất `Signature`, metadata class file không đủ để khôi phục một cách chắc chắn type argument `String`.

Điều tương tự áp dụng cho generic type variable, wildcard và kiểu parameterized trên constructor/method.

### 8.2. Varargs và tham số mảng

`String... values` được biểu diễn như `String[]` trong descriptor JVM. Không thể chỉ nhìn `getType() == String[].class` rồi khẳng định nguồn viết `String...` thay vì `String[]`.

```java
void accept(String[] values) {}
void collect(String... values) {}
```

`accept` không được đánh dấu varargs; `collect` được đánh dấu varargs. `Executable.isVarArgs()` và `Parameter.isVarArgs()` trên tham số cuối giúp phân biệt thuộc tính runtime. **Varargs không phải một bit modifier thông thường của từng parameter trong `MethodParameters`**.

### 8.3. Receiver parameter trong cú pháp nguồn

Java còn hỗ trợ cú pháp **receiver parameter** tường minh ở một số khai báo method/constructor, ví dụ:

```java
class Point {
    void check(Point this) {
    }
}
```

Receiver parameter là cách biểu đạt về receiver/các annotation liên quan ở ngôn ngữ, **không phải** một formal parameter bình thường trong danh sách đối số runtime. `Executable.getParameters()` không sinh thêm một `Parameter` chỉ vì nguồn ghi `Point this`. Nếu cần metadata annotation trên receiver, xem `Executable.getAnnotatedReceiverType()` khi class file cung cấp.

Do đó, không đồng nhất cụm từ **receiver parameter** với tham số enclosing instance do compiler đưa vào constructor của non-static member inner class.

## 9. Annotation trên parameter và giới hạn retention

Annotation không phải modifier bit:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}

class Example {
    void process(@Label("user") String name) {
    }
}
```

Dùng Reflection có thể đọc annotation từ `Parameter.getAnnotation(Label.class)`, nhưng chỉ khi retention phù hợp và metadata có mặt trong class file. Nếu annotation có `RetentionPolicy.SOURCE`, nó không có mặt trong class file chuẩn; nếu retention là `CLASS`, thông thường không được expose qua core Reflection runtime.

Chú ý sự khác biệt giữa **declaration annotation** trên formal parameter và **type-use annotation** trên kiểu của parameter. `Parameter.getAnnotations()` và `Parameter.getAnnotatedType()` trả các góc nhìn khác nhau. Cả hai đều không biến `getModifiers()` thành nơi lưu mọi annotation.

## 10. Quy trình phân tích có khả năng chịu thiếu metadata

Khi một framework muốn liệt kê tham số executable, có thể dùng quy trình sau:

1. Xác định đúng `Method` hoặc `Constructor<?>`. Không suy đoán constructor của inner class chỉ từ số tham số nguồn.
2. Dùng `getParameterCount()`/`getParameterTypes()` làm nền tảng vì chúng phản ánh descriptor.
3. Lấy `getParameters()` để đọc tên và modifier. Kiểm tra `isNamePresent()` **trước khi** phụ thuộc `getName()`.
4. Đọc `getModifiers()` và kiểm tra `final` bằng `Modifier.isFinal()`. Nếu chỉ nhận bit 0, chưa thể biết nguồn có `final` hay không khi metadata thiếu.
5. Đọc `isImplicit()`/`isSynthetic()` để nhận diện các trường hợp compiler/language thêm tham số **nếu metadata hỗ trợ**. Đừng mặc định false đồng nghĩa “được người viết khai báo”.
6. Với varargs, hỏi `Executable.isVarArgs()` và `Parameter.isVarArgs()`; với generics, dùng `getParameterizedType()`.
7. Nếu tên/cờ không đáng tin, kiểm tra quy trình build và class file với `javap -v -p`, đặc biệt `MethodParameters`, `Signature`, `RuntimeVisibleParameterAnnotations` và descriptor.
8. Nếu không tìm đủ metadata, báo dữ liệu **không xác định** hoặc dùng hợp đồng đặt tên khác đã thiết kế trước. Không đoán lại nguyên văn mã nguồn.

### Ví dụ quyết định trong code

```java
for (Parameter p : executable.getParameters()) {
    String name = p.isNamePresent()
            ? p.getName()
            : "<unknown>";
    boolean declaredFinal = Modifier.isFinal(p.getModifiers());
    // Các cờ phản ánh class file hiện có; đừng coi false
    // là bằng chứng không thể sai về cú pháp nguồn.
    System.out.println(name + " / final-flag=" + declaredFinal);
}
```

Đây là đoạn minh họa, trong đó `executable` là một `Executable` đã được xác định và cần import `Executable`, `Parameter`, `Modifier`. Ý tưởng là bộc lộ ranh giới giữa thông tin đã biết và metadata thiếu, thay vì âm thầm suy diễn.

## 11. Các lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Không dùng `-parameters` nhưng vẫn coi `getName()` là tên nguồn | `getName()` có thể trả `arg0`/`arg1` do thiếu metadata | Kiểm tra `isNamePresent()` |
| `getModifiers() == 0` nghĩa là chắc chắn nguồn không ghi `final` | Có thể không có `MethodParameters` | Xem build flags/class file; báo thiếu dữ liệu |
| Mọi tham số do compiler sinh đều `isSynthetic()` | Có nhóm `implicit/mandated` khác `synthetic`, và metadata có thể thiếu | Kiểm tra phân loại và hợp đồng API |
| `-g` tương đương `-parameters` | Debug attribute và MethodParameters có mục đích khác nhau | Dùng `-parameters` khi cần tên qua Reflection |
| `getParameterTypes()` cần `-parameters` | Descriptor lưu kiểu runtime riêng | Dùng API này kể cả khi tên bị mất |
| Mảng `String[]` chứng minh parameter nguồn là varargs | Cả tham số mảng thường lẫn varargs có thể có kiểu `String[]` | Dùng `isVarArgs()` |
| `List<String>` luôn dựng lại được từ `getType()` | Type erasure làm `getType()` là `List.class` | Xem `getParameterizedType()` và `Signature` |
| `getParameters()` tương ứng 1-1 với các tham số viết tường minh | Constructor inner/enum, local/anonymous có thể thêm tham số | Phân tích executable và metadata thực tế |
| `getModifiers()` chứa annotation parameter | Annotation lưu theo attributes/retention khác | Dùng API annotation |
| Thấy `isImplicit() == false` thì suy ra nguồn chắc chắn khai báo tham số | Flag có thể không tồn tại trong class file | Không suy luận chắc chắn khi thiếu metadata |

## 12. Bài tự kiểm tra

**Câu 1.** Một method được khai báo `process(final String item, int retries)`. Nếu Reflection trả `Modifier.isFinal(first.getModifiers()) == false`, có được kết luận nguồn không ghi `final` không?

**Đáp án:** Không. Cần xác định `MethodParameters` có ghi cờ tương ứng và liệu class file bị biến đổi hay không. Giá trị false đơn lẻ chỉ mô tả metadata Reflection hiện quan sát được.

**Câu 2.** `getParameterTypes()` có thể hoạt động khi không bật `javac -parameters` không?

**Đáp án:** Có. Method descriptor giữ kiểu runtime; `-parameters` chủ yếu phục vụ metadata tên/parameter flags.

**Câu 3.** `p.getName()` trả `arg0` và `p.isNamePresent()` trả `false`. `arg0` có phải chắc chắn là tên đã viết trong `.java` không?

**Đáp án:** Không. Đây là tên thay thế do Reflection cung cấp khi class file không chứa tên formal parameter.

**Câu 4.** `ACC_MANDATED` và `ACC_SYNTHETIC` có đồng nghĩa không?

**Đáp án:** Không. `mandated` liên quan tham số ngầm định theo yêu cầu ngôn ngữ; `synthetic` liên quan chi tiết triển khai compiler.

**Câu 5.** Vì sao `Parameter.isVarArgs()` có thể trả true dù `getModifiers()` không có cờ varargs?

**Đáp án:** Varargs thuộc metadata method-level `ACC_VARARGS` và vị trí tham số cuối; không phải một flag thuộc danh sách ba cờ của `MethodParameters`.

**Câu 6.** Một constructor non-static inner class có hai `Parameter` trong khi nguồn khai báo một tham số. Có phải Reflection sai không?

**Đáp án:** Không. Chữ ký runtime có thể thêm tham số đầu để truyền enclosing instance.

## 13. Ghi nhớ và nguồn chuẩn

**Không đồng nhất chữ ký runtime với toàn bộ cú pháp nguồn.** `Executable.getParameters()` luôn mô tả tham số hiện có ở executable; kiểu tham số lấy từ descriptor, còn tên, modifier `final` và cờ implicit/synthetic có thể phụ thuộc `MethodParameters`. Sử dụng `-parameters` khi cần tên, kiểm tra `isNamePresent()` trước khi tin `getName()`, và phân biệt `ACC_FINAL`, `ACC_SYNTHETIC`, `ACC_MANDATED`.

Tài liệu chuẩn:

- [Java SE 21 — `java.lang.reflect.Parameter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Java SE 21 — `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html)
- [JVM Specification 21 — `MethodParameters` attribute (`4.7.24)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html)
- [`javac` option `-parameters`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
