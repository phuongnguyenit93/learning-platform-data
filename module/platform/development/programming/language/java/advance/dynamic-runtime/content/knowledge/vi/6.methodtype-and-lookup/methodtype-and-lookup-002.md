# 6.2 Mô tả tham số, kiểu trả về và receiver bằng `MethodType`

Trong Java, `java.lang.invoke.MethodType` mô tả **danh sách kiểu tham số theo đúng thứ tự** và **kiểu trả về** của một phương thức hoặc lời gọi động. Đây là thành phần nền tảng của `MethodHandle`, `MethodHandles.Lookup` và liên kết lời gọi `invokedynamic`. Điểm dễ nhầm nhất: **chữ ký khai báo của instance method không có tham số `this`, nhưng `MethodHandle` gọi instance method thường có `receiver` ở tham số đầu tiên**.

Bài này giải thích cách tạo, đọc, biến đổi `MethodType`, cách receiver xuất hiện khi lookup method, sự khác nhau của static/instance/constructor, và vì sao `invokeExact` yêu cầu chữ ký đúng đến từng kiểu.

> **Môi trường:** Ví dụ độc lập dùng Java **17+** (API `java.lang.invoke` đã có từ trước). Biên dịch bằng `javac --release 17` hoặc `javac` từ JDK 17+. Các chương trình đầy đủ bên dưới đã được đối chiếu đầu ra bằng biên dịch và chạy thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Tạo `MethodType` từ kiểu trả về, kiểu tham số Java và giải thích chính xác thứ tự các đối số của `methodType(...)`.
- Đọc `returnType()`, `parameterCount()`, `parameterType(index)`, `parameterArray()`, `parameterList()`, và chuyển đổi sang JVM method descriptor.
- Phân biệt **chữ ký của method được khai báo** với **chữ ký lời gọi của MethodHandle** sau `findStatic`, `findVirtual`, `findConstructor` và `bindTo`.
- Hiểu receiver là gì, vì sao nó có mặt ở đầu danh sách tham số handle khi gọi instance method, và trường hợp nào không có receiver.
- Sử dụng `changeParameterType`, `changeReturnType`, `insertParameterTypes`, `appendParameterTypes`, `dropParameterTypes` để tạo chữ ký mới mà không nhầm với thao tác sửa code thực thi.
- Phân tích lỗi `WrongMethodTypeException`, phân biệt `invokeExact`, `invoke` và `asType`.

## 2. `MethodType` thực sự biểu diễn gì?

`MethodType` là một giá trị **bất biến** (immutable) gồm:

```text
MethodType = (parameterType[0], parameterType[1], ..., parameterType[n-1])
             -> returnType

Ví dụ:
             (String, int) -> boolean
MethodType:  (String,int)boolean
Descriptor:  (Ljava/lang/String;I)Z
```

Mỗi thành phần kiểu được biểu diễn bằng một đối tượng `Class<?>`, chẳng hạn `String.class`, `int.class`, `long.class`, `String[].class` hoặc `void.class`. **Kiểu trả về được truyền trước**, sau đó mới đến các kiểu tham số:

```java
MethodType type = MethodType.methodType(
        boolean.class, String.class, int.class);
```

Đây là **đoạn minh họa**, với import `java.lang.invoke.MethodType`. Kết quả mô tả phương thức nhận `(String, int)` và trả về `boolean`. Không có tên method trong đối tượng này.

### 2.1. Những gì `MethodType` không chứa

Một `MethodType` không lưu:

- Tên method (ví dụ `parse` hay `send`), class hoặc interface khai báo method.
- Modifier như `public`, `static`, `private` hoặc `synchronized`; không bao hàm quyền truy cập.
- Tên tham số như `username`, `count` hay default value.
- Generic type arguments, ví dụ `List<String>` khác `List<Integer>` ở compile time nhưng đều dùng `List.class` trong method descriptor runtime.
- Annotation, checked exceptions hoặc nội dung bytecode.
- Nhãn riêng nói rằng tham số đầu là receiver. Receiver chỉ được **suy ra theo loại handle hoặc cách handle được xây dựng**; một `MethodType` tự nó chỉ biết những kiểu theo vị trí.

Hai method khác tên nhưng có cùng kiểu tham số và kiểu trả về có thể chia sẻ `MethodType` tương đương. Ngược lại, chỉ cần khác một kiểu tham số, thứ tự hoặc kiểu trả về là khác chữ ký `MethodType`.

### 2.2. Bất biến, bằng nhau theo nội dung, có thể được cache

`MethodType` không cho sửa trực tiếp danh sách kiểu đã tạo. Các phép `change...`, `insert...`, `drop...` tạo hoặc trả về một `MethodType` mới theo nghĩa giá trị; đối tượng ban đầu không đổi.

`equals(...)` so sánh từng kiểu tham số và kiểu trả về theo đúng vị trí. Không nên dùng `==` làm quy tắc nhận diện vì factory **có thể cache** nhưng API không bảo đảm hai lần tạo cùng kiểu luôn trả đúng cùng object.

Ví dụ:

```java
MethodType a = MethodType.methodType(int.class, String.class);
MethodType b = MethodType.methodType(int.class, String.class);
boolean same = a.equals(b); // true
```

Đây là fragment không độc lập; chú thích kết quả dựa trên quy tắc so sánh của API. Việc dùng `Class<?>` còn gắn với danh tính class loader: hai class cùng tên nhị phân nhưng được định nghĩa bởi loader khác nhau vẫn là hai kiểu runtime khác nhau, dẫn đến hai `MethodType` có thể **không bằng nhau** dù chuỗi descriptor giống nhau.

## 3. Tạo chữ ký: kiểu trả về trước, tham số theo thứ tự

Import cơ bản:

```java
import java.lang.invoke.MethodType;
```

Các mẫu:

| Khai báo/phương thức muốn mô tả | Cách tạo `MethodType` | Dạng dễ đọc |
| --- | --- | --- |
| `void reset()` | `methodType(void.class)` | `()void` |
| `int size()` | `methodType(int.class)` | `()int` |
| `String name(int id)` | `methodType(String.class, int.class)` | `(int)String` |
| `boolean verify(String token, int retries)` | `methodType(boolean.class, String.class, int.class)` | `(String,int)boolean` |
| `long sum(long a, long b)` | `methodType(long.class, long.class, long.class)` | `(long,long)long` |
| `String[] split(String regex)` | `methodType(String[].class, String.class)` | `(String)String[]` |
| `void print(String... values)` | `methodType(void.class, String[].class)` | `(String[])void` |

Mọi lời gọi `methodType` trong bảng có thể viết thành `MethodType.methodType(...)`; bảng rút gọn tên lớp cho dễ đọc.

**Lưu ý quan trọng:**

1. `void.class` chỉ hợp lệ cho **kiểu trả về**, nhằm chỉ một phương thức không trả giá trị; không thể dùng làm kiểu tham số.
2. Tham số có thể là primitive, array hoặc reference type; `int.class` **không phải** `Integer.class`, và `String.class` **không phải** `Object.class`.
3. `String...` trong mã nguồn trở thành tham số `String[]` trong method descriptor. Cờ `varargs` của method thuộc metadata riêng; `MethodType` chỉ biểu diễn kiểu mảng.
4. `MethodType.methodType(Object.class, Object.class, Object.class)` khác `MethodType.genericMethodType(2)` về cách tạo nhưng có thể tương đương về kiểu; `genericMethodType(2)` dùng `Object` cho hai tham số và kiểu trả về.
5. Số **parameter slots** bị giới hạn trong JVM. Một `long` hoặc `double` tiêu thụ hai slot, kiểu khác thường một slot. `parameterCount()` là **số kiểu tham số**, không phải số slot; tạo `MethodType` quá giới hạn có thể phát sinh `IllegalArgumentException`.

## 4. Đọc một `MethodType`

Những method thường dùng:

| API | Trả về / ý nghĩa |
| --- | --- |
| `returnType()` | `Class<?>` của kết quả; có thể là `void.class` |
| `parameterCount()` | Số tham số dạng `int` |
| `parameterType(index)` | Kiểu tham số ở chỉ số **0-based** |
| `parameterArray()` | Mảng `Class<?>[]` chứa các kiểu theo thứ tự |
| `parameterList()` | `List<Class<?>>` chứa các kiểu theo thứ tự |
| `toString()` | Dạng ngắn dùng simple class names, ví dụ `(String,long)int` |
| `toMethodDescriptorString()` | JVM method descriptor theo cú pháp class file, ví dụ `(Ljava/lang/String;J)I` |
| `descriptorString()` | Tương đương API lấy descriptor, có từ JDK hiện đại |
| `equals(Object)` | So sánh toàn bộ chuỗi kiểu tham số và kiểu kết quả |

Khi muốn hiển thị “tham số thứ nhất là gì?”, hãy nhớ thứ tự tham số của `MethodType` là thứ tự **đầu vào của lời gọi mà đối tượng đó đang mô tả**. Với MethodType dùng để tìm một instance method, đây là tham số khai báo; với `handle.type()`, đây là tất cả tham số của **handle**, có thể gồm receiver ở vị trí 0.

### 4.1. JVM method descriptor không phải tên method

Các ký hiệu thường gặp:

| Java type | JVM descriptor |
| --- | --- |
| `void` (chỉ trả về) | `V` |
| `int` | `I` |
| `long` | `J` |
| `boolean` | `Z` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `Object` | `Ljava/lang/Object;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

Ví dụ `(Ljava/lang/String;J)I` nghĩa là “nhận `String` rồi `long`; trả `int`”. Các tham số nằm **trong** dấu ngoặc; kiểu trả về nằm **sau** ngoặc. Chuỗi đó không bao gồm tên method, class chủ sở hữu hoặc cờ `static`.

`MethodType.fromMethodDescriptorString(descriptor, loader)` đọc lại descriptor thành `MethodType`. Với tên class reference, `loader` quyết định kiểu runtime nào được giải quyết. Descriptor hợp lệ nhưng class không tìm được có thể dẫn tới `TypeNotPresentException`; cú pháp descriptor sai dẫn đến `IllegalArgumentException`. Không coi việc parse descriptor là lời gọi method hoặc yêu cầu khởi tạo các lớp được mô tả.

**Ghi chú về round-trip:** `toMethodDescriptorString()` và `fromMethodDescriptorString(...)` đối chiếu tốt khi class đều có thể được nhìn thấy bằng cùng loader. Chúng **không phải phép đối ngược tuyệt đối** trong mọi môi trường nhiều loader hoặc với loại `Class<?>` không thể mô tả danh nghĩa.

## 5. Thực hành 1: tạo, đọc và biến đổi `MethodType`

Tạo tệp **`MethodTypeIntrospectionDemo.java`**:

```java
import java.lang.invoke.MethodType;

public class MethodTypeIntrospectionDemo {
    public static void main(String[] args) {
        MethodType signature = MethodType.methodType(
                int.class, String.class, long.class);
        System.out.println("type: " + signature);
        System.out.println("return: " + signature.returnType().getSimpleName());
        System.out.println("arity: " + signature.parameterCount());
        System.out.println("parameters: "
                + signature.parameterList().stream()
                        .map(Class::getSimpleName).toList());
        System.out.println("descriptor: "
                + signature.toMethodDescriptorString());

        MethodType decoded = MethodType.fromMethodDescriptorString(
                "(Ljava/lang/String;J)I",
                MethodTypeIntrospectionDemo.class.getClassLoader());
        System.out.println("descriptor round-trip: " + signature.equals(decoded));

        MethodType changed = signature
                .changeParameterType(0, Object.class)
                .changeReturnType(long.class);
        System.out.println("changed: " + changed.toMethodDescriptorString());
        System.out.println("appended: "
                + signature.appendParameterTypes(boolean.class)
                        .toMethodDescriptorString());
        System.out.println("insert/drop round-trip: "
                + signature.insertParameterTypes(
                        0, MethodTypeIntrospectionDemo.class)
                        .dropParameterTypes(0, 1).equals(signature));
        System.out.println("erased: " + signature.erase().toMethodDescriptorString());
        System.out.println("wrapped: "
                + MethodType.methodType(int.class, boolean.class)
                        .wrap().toMethodDescriptorString());
        try {
            MethodType.methodType(int.class, void.class);
        } catch (IllegalArgumentException exception) {
            System.out.println("void parameter: rejected");
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 MethodTypeIntrospectionDemo.java
java MethodTypeIntrospectionDemo
```

**Stdout:**

```text
type: (String,long)int
return: int
arity: 2
parameters: [String, long]
descriptor: (Ljava/lang/String;J)I
descriptor round-trip: true
changed: (Ljava/lang/Object;J)J
appended: (Ljava/lang/String;JZ)I
insert/drop round-trip: true
erased: (Ljava/lang/Object;J)I
wrapped: (Ljava/lang/Boolean;)Ljava/lang/Integer;
void parameter: rejected
```

Giải thích:

1. `signature` nhận `String, long` và trả `int`. `parameterCount() == 2` dù `long` sử dụng hai JVM local-variable/argument slots tại mức bytecode.
2. Chuỗi `(Ljava/lang/String;J)I` chứa **đủ kiểu** để phục dựng MethodType khi loader phù hợp.
3. `changeParameterType(0, Object.class)` đổi **tham số đầu** từ `String` sang `Object`; `changeReturnType(long.class)` đổi kiểu kết quả. `signature` cũ không đổi.
4. `appendParameterTypes(boolean.class)` thêm tham số vào **cuối**; `insertParameterTypes(0, ...)` thêm vào **đầu**, còn `dropParameterTypes(0, 1)` xóa đoạn nửa mở `[0, 1)`.
5. `erase()` thay reference type bằng `Object` nhưng giữ kiểu primitive `long` và `int`. `wrap()` đưa primitive `boolean`, `int` thành `Boolean`, `Integer`.
6. Java từ chối `void.class` ở vị trí tham số; `void.class` hợp lệ ở vị trí trả về.

Đây là thay đổi **đối tượng mô tả kiểu**, chưa thao tác lên method thực tế, chưa tìm method, cũng chưa thay đổi cách chương trình gọi method.

## 6. Receiver: điểm khác nhau giữa method khai báo và method handle

Xét Java source:

```java
class Service {
    String repeat(String text, int times) {
        return text.repeat(times);
    }
}
```

Đây là **fragment minh họa**, chưa có `main`. Method khai báo ở source nhận **hai tham số tường minh** `String` và `int`, trả `String`. Vì vậy chữ ký thành viên, hay JVM method descriptor của method, là:

```text
(String,int)String
(Ljava/lang/String;I)Ljava/lang/String;
```

Nhưng để thực sự gọi instance method, JVM phải biết **đối tượng đích**: `this`/receiver. Method handle do `Lookup.findVirtual(Service.class, "repeat", ...)` tạo thường có dạng:

```text
MethodType dùng làm đối số findVirtual:
    (String, int)String
    [KHÔNG có receiver]

MethodType từ handle.type() sau findVirtual:
    (Service, String, int)String
     ^^^^^^^
     receiver ở vị trí parameterType(0)

Gọi handle:
    handle.invokeExact(serviceObject, "ha", 3)
                        ^^^^^^^^^^^^^
                        receiver
```

Đây là **khác biệt bản chất**:

- **MethodType của method khai báo:** chỉ gồm các tham số trong khai báo và return type. `this` không xuất hiện trong JVM method descriptor của instance method.
- **MethodType của handle gọi instance method:** receiver được mô hình hóa như tham số đầu tiên. Lời gọi `MethodHandle.invokeExact` đưa receiver vào trước các tham số khai báo.
- **Không ghi receiver vào đối số `MethodType` truyền cho `findVirtual`**. Chính `Lookup` thêm receiver vào handle kết quả.
- Receiver có kiểu reference là class/interface mà handle yêu cầu, thông thường là `refc` đã truyền cho `findVirtual` (trường hợp quyền truy cập protected và một số dạng lookup có thể có kiểu receiver chặt hơn).
- Receiver **không phải tên tham số** và không được đánh dấu đặc biệt bên trong `MethodType`. Việc nó là receiver chỉ có ý nghĩa theo nguồn gốc handle/operation.

### 6.1. Static method không có receiver

Với `static long sum(long a, long b)`, `Lookup.findStatic` được gọi bằng `methodType(long.class, long.class, long.class)`. Handle kết quả thường nhận đúng `(long, long)` và trả `long`. Không tự thêm đối số `Service.class` chỉ vì method nằm trong class `Service`.

### 6.2. Gắn một receiver vào handle

`MethodHandle.bindTo(serviceObject)` gắn receiver reference vào vị trí tham số đầu của một handle phù hợp và trả một handle mới:

```text
Trước bindTo: (Service, String, int)String
Sau  bindTo: (String, int)String

Receiver đã cố định, nên người gọi không truyền lại.
```

Việc `bindTo` **không sửa định nghĩa method** hay khiến method chuyển thành `static`. Nó tạo một callable khác có đối tượng đích được cung cấp trước. `bindTo` áp dụng cho tham số đầu thuộc reference type; để gắn một đối số primitive hoặc tại vị trí khác, có thể dùng các combinator như `MethodHandles.insertArguments` theo đúng hợp đồng.

### 6.3. `findSpecial` và `unreflect`

`Lookup.findSpecial(...)` cũng cho ra handle có receiver, nhưng cơ chế gọi là kiểu `invokespecial` với quy tắc quyền truy cập và dispatch riêng. Không tự xem nó là `findVirtual` với một tên method khác. `Lookup.unreflect(Method)` có thể lấy handle từ metadata Reflection: đối với instance method, kiểu handle cũng bao gồm receiver; với static method thì không.

Trong thực tế, cách kiểm tra chắc nhất sau một thao tác lookup/adapter là đọc **`handle.type()`**, thay vì suy luận hoàn toàn từ chuỗi tên method.

## 7. Thực hành 2: quan sát receiver bằng `findVirtual` và `bindTo`

Tạo tệp **`MethodTypeReceiverDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class MethodTypeReceiverDemo {
    static class Handler {
        String echo(String text, int times) {
            return text.repeat(times);
        }

        static long add(long left, long right) {
            return left + right;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType declared = MethodType.methodType(
                String.class, String.class, int.class);
        MethodHandle virtual = lookup.findVirtual(
                Handler.class, "echo", declared);

        System.out.println("declared parameter count: " + declared.parameterCount());
        System.out.println("virtual parameter count: " + virtual.type().parameterCount());
        System.out.println("receiver: " + virtual.type().parameterType(0).getSimpleName());
        System.out.println("receiver prefixed: "
                + virtual.type().equals(
                        declared.insertParameterTypes(0, Handler.class)));
        System.out.println("virtual result: "
                + (String) virtual.invokeExact(new Handler(), "ha", 3));

        MethodHandle bound = virtual.bindTo(new Handler());
        System.out.println("bound matches declaration: " + bound.type().equals(declared));
        System.out.println("bound result: " + (String) bound.invokeExact("go", 2));

        MethodHandle staticHandle = lookup.findStatic(
                Handler.class, "add",
                MethodType.methodType(long.class, long.class, long.class));
        System.out.println("static parameter count: "
                + staticHandle.type().parameterCount());
        System.out.println("static result: "
                + (long) staticHandle.invokeExact(4L, 6L));
    }
}
```

```bash
javac --release 17 MethodTypeReceiverDemo.java
java MethodTypeReceiverDemo
```

**Stdout:**

```text
declared parameter count: 2
virtual parameter count: 3
receiver: Handler
receiver prefixed: true
virtual result: hahaha
bound matches declaration: true
bound result: gogo
static parameter count: 2
static result: 10
```

Cách đọc kết quả:

1. `declared` mô tả `Handler.echo(String,int): String` có **2** tham số khai báo. `Lookup.findVirtual` tự thêm `Handler` vào trước, nên `virtual.type()` có **3** tham số.
2. So sánh `virtual.type()` với `declared.insertParameterTypes(0, Handler.class)` cho `true`. Đây là phép **kiểm chứng dạng chữ ký**, không có nghĩa chúng ta phải tự thêm receiver vào `findVirtual`.
3. Gọi `virtual.invokeExact(new Handler(), "ha", 3)` đưa `Handler` vào đầu; `String.repeat(3)` cho `hahaha`.
4. `bindTo(new Handler())` gắn receiver, khiến handle mới có đúng dạng `(String,int)String`.
5. `findStatic` cho method `add` không có receiver; 2 tham số của handle chính là 2 tham số khai báo.

**Nhớ:** `MethodType` của handle mô tả cách **gọi handle**, không phải cách trình biên dịch Java viết chữ ký source. Đây là nguyên nhân dễ nhầm số lượng tham số khi debug dynamic invocation.

## 8. Constructor: lookup trả `void`, handle trả đối tượng

Với constructor Java:

```java
class Box {
    Box(String value) { /* ... */ }
}
```

Đây là một fragment minh họa. Constructor trong JVM được biểu diễn như method `<init>` trả về `void`, nên khi tìm bằng `Lookup.findConstructor(Box.class, type)`, đối số `type` phải có **return type = `void.class`**:

```java
MethodType constructorType = MethodType.methodType(
        void.class, String.class);
MethodHandle constructor = MethodHandles.lookup()
        .findConstructor(Box.class, constructorType);
```

Đây là fragment giả định `Box` tồn tại và caller có quyền lookup.

Sau khi tìm thành công, `constructor.type()` lại **trả về `Box.class`** chứ không phải `void.class`: handle này tạo object và trả object mới. Dạng như sau:

```text
Constructor trong class file: (String)void
MethodType đưa vào lookup: (String)void
MethodType của handle:     (String)Box
```

Không có receiver object đầu vào vì object được tạo **trong quá trình gọi constructor**. Đừng áp dụng công thức “mọi instance member đều prepend receiver” cho constructor handle.

## 9. `MethodType` là hợp đồng kiểu của lời gọi `MethodHandle`

`MethodHandle` chứa một `MethodType` truy vấn qua `handle.type()`. Nhưng **có một MethodType đúng** chưa đồng nghĩa đã có một method thực tế hoặc đã được phép gọi nó; `Lookup` phải giải quyết tên/chủ sở hữu và kiểm tra quyền truy cập.

Hai cách gọi quan trọng:

| API | Cách khớp kiểu |
| --- | --- |
| `handle.invokeExact(...)` | Từng kiểu đối số **và kiểu trả về được ngữ cảnh gọi yêu cầu** phải khớp chính xác với `handle.type()`. |
| `handle.invoke(...)` | Có thể thực hiện chuyển đổi tương thích qua cơ chế tương đương `asType` trước khi gọi, trong giới hạn API cho phép. |
| `handle.asType(newType)` | Tạo một **adapter handle** có `newType`, nếu các chuyển đổi tham số/kết quả hợp lệ. `handle` gốc vẫn giữ type cũ. |
| `handle.invokeWithArguments(...)` | Cách gọi linh hoạt qua `Object`/danh sách, thuận tiện cho tooling nhưng có chuyển đổi/overhead và không có cùng ràng buộc tĩnh như `invokeExact`. |

### 9.1. Kiểu trả về cũng là một phần của `invokeExact`

Một sai sót khó nhìn:

```java
// Ví dụ minh họa: giả sử twiceHandle.type() là (long)long
long ok = (long) twiceHandle.invokeExact(7L);
Object wrong = twiceHandle.invokeExact(7L); // WrongMethodTypeException
```

`invokeExact` là **signature-polymorphic**: trình biên dịch xác định call-site descriptor từ kiểu tĩnh của đối số và **kiểu trả về mong đợi tại vị trí lời gọi**. Trong lệnh đầu, kiểu kết quả được yêu cầu là `long`. Lệnh thứ hai yêu cầu kết quả `Object`, không khớp với `long`, dù Java thông thường cho phép boxing primitive sang `Object` ở nhiều ngữ cảnh khác.

Dùng kết quả một cách tường minh, ví dụ `(long) handle.invokeExact(7L)`, và kiểm tra `handle.type()`. Với handle trả `void`, lời gọi theo ngữ cảnh `void` phải tương thích.

### 9.2. `invoke` và `asType` có chuyển đổi nhưng không tùy ý

Với handle thực tế `(long)long`:

- `(long) handle.invokeExact(7L)`: khớp chính xác.
- `(long) handle.invoke(7)`: call site có tham số `int`; `invoke` có thể dùng phép **widening `int -> long`** tương thích.
- `MethodHandle changed = handle.asType(MethodType.methodType(long.class, int.class))`: adapter nhận `int`, chuyển thành `long` rồi gọi target; `changed.type()` là `(int)long`.

`asType` không sửa `handle` gốc, không biến đổi logic nghiệp vụ và không hỗ trợ mọi phép chuyển kiểu. Một yêu cầu chuyển đổi không thể biểu diễn hợp lệ có thể gây `WrongMethodTypeException` khi tạo adapter hoặc gọi; reference cast sai lúc chạy có thể ném `ClassCastException`. Đừng trông chờ `asType` tự parse chuỗi `"42"` thành số `42`.

## 10. Thực hành 3: constructor, receiver và `invokeExact`

Tạo tệp **`MethodTypeConstructorAndInvokeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodTypeConstructorAndInvokeDemo {
    static class Box {
        private final String value;

        Box(String value) {
            this.value = value;
        }

        String value() {
            return value;
        }
    }

    static long twice(long input) {
        return input * 2;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType constructorType = MethodType.methodType(void.class, String.class);
        MethodHandle constructor = lookup.findConstructor(Box.class, constructorType);
        System.out.println("constructor lookup return: "
                + constructorType.returnType().getSimpleName());
        System.out.println("constructor handle return: "
                + constructor.type().returnType().getSimpleName());
        System.out.println("constructor handle parameters: "
                + constructor.type().parameterCount());

        Box box = (Box) constructor.invokeExact("box-1");
        MethodHandle getter = lookup.findVirtual(
                Box.class, "value", MethodType.methodType(String.class));
        System.out.println("getter receiver: "
                + getter.type().parameterType(0).getSimpleName());
        System.out.println("getter result: "
                + (String) getter.invokeExact(box));

        MethodHandle twiceHandle = lookup.findStatic(
                MethodTypeConstructorAndInvokeDemo.class,
                "twice", MethodType.methodType(long.class, long.class));
        System.out.println("invokeExact: " + (long) twiceHandle.invokeExact(7L));
        System.out.println("invoke widening: " + (long) twiceHandle.invoke(7));
        MethodHandle adapted = twiceHandle.asType(
                MethodType.methodType(long.class, int.class));
        System.out.println("asType then exact: "
                + (long) adapted.invokeExact(7));
        try {
            Object incorrect = twiceHandle.invokeExact(7L);
            System.out.println(incorrect);
        } catch (WrongMethodTypeException exception) {
            System.out.println("wrong return context: "
                    + exception.getClass().getSimpleName());
        }
    }
}
```

```bash
javac --release 17 MethodTypeConstructorAndInvokeDemo.java
java MethodTypeConstructorAndInvokeDemo
```

**Stdout:**

```text
constructor lookup return: void
constructor handle return: Box
constructor handle parameters: 1
getter receiver: Box
getter result: box-1
invokeExact: 14
invoke widening: 14
asType then exact: 14
wrong return context: WrongMethodTypeException
```

**Phân tích:** `findConstructor` nhận kiểu `(String)void` nhưng tạo handle `(String)Box`; `findVirtual` cho getter không khai báo tham số lại cho handle có một tham số `Box` là receiver. `invokeExact` phải khớp cả kiểu trả về, còn `invoke` và `asType` xử lý trường hợp `int -> long` khi được phép. Ở lời gọi sai, compiler suy ra kiểu kết quả `Object` theo biến đích, khiến nó khác `long` và phát sinh `WrongMethodTypeException` mà chương trình cố ý bắt để minh họa.

## 11. Các thao tác chỉnh chữ ký và cách sử dụng đúng

`MethodType` có các method **không biến đổi object hiện tại**:

| Thao tác | Ý nghĩa | Ví dụ nếu gốc là `(String,int)boolean` |
| --- | --- | --- |
| `changeReturnType(long.class)` | Đổi kiểu trả về | `(String,int)long` |
| `changeParameterType(1, long.class)` | Thay kiểu ở index 1 | `(String,long)boolean` |
| `insertParameterTypes(0, Service.class)` | Chèn trước index 0 | `(Service,String,int)boolean` |
| `appendParameterTypes(Object.class)` | Nối ở cuối | `(String,int,Object)boolean` |
| `dropParameterTypes(0, 1)` | Bỏ các vị trí trong đoạn `[0,1)` | `(int)boolean` |
| `erase()` | Thay mọi reference type bằng `Object`, giữ primitive | `(Object,int)boolean` |
| `generic()` | Thay cả primitive và reference types bằng `Object` (trong hình dạng tổng quát theo API) | `(Object,Object)Object` |
| `wrap()` | Chuyển primitive sang wrapper khi có | `(String,Integer)Boolean` |
| `unwrap()` | Chuyển wrapper tương ứng sang primitive | Phụ thuộc các wrapper thực tế đang có |

Đây là bảng **kết quả biểu diễn kiểu**, không phải các MethodHandle đang được gọi. Một số thao tác có thể báo lỗi nếu index nằm ngoài miền, đưa `void.class` vào tham số, hoặc vượt giới hạn số slot.

### 11.1. Vì sao `MethodType` mới không tự thay cách gọi method?

Giả sử ta có `MethodType oldType = methodType(String.class, String.class, int.class)`. Lệnh `oldType.changeParameterType(1, long.class)` tạo chữ ký khác, nhưng **không tạo method mới `echo(String,long)`**. Nếu dùng type sai này để `lookup.findVirtual(Handler.class, "echo", ...)`, lookup có thể báo `NoSuchMethodException` vì method có kiểu khai báo khác. Nếu có sẵn handle cũ, chỉ những adapter hợp lệ (như `asType`) mới tạo một đường gọi chấp nhận kiểu khác theo quy tắc chuyển đổi.

Tương tự, thêm receiver bằng `insertParameterTypes(0, Handler.class)` chỉ tạo ra **một chuỗi kiểu tương đương với handle type dự kiến**, không tự thực hiện lookup hay bind receiver.

### 11.2. Các bẫy index thường gặp

- `parameterType(0)` đọc **tham số đầu**, không phải kiểu trả về.
- `dropParameterTypes(start, end)` dùng **end-exclusive**, nên `dropParameterTypes(0, 1)` xóa đúng một tham số.
- `insertParameterTypes(0, ...)` thêm trước phần tử đầu; nếu muốn thêm cuối, dùng `appendParameterTypes(...)`.
- `parameterCount() == 0` hợp lệ cho `()void` hoặc `()String`; không tự suy luận rằng method đó là static, vì một instance method có thể không có tham số khai báo nhưng handle vẫn có receiver.
- Không ép mặc định `List<String>` thành một type riêng trong `MethodType`: JVM nhìn thấy raw `List.class` ở đây; thông tin generic nằm trong cấu trúc khác của Reflection hoặc bytecode.

## 12. So sánh bốn dạng lời gọi thường gặp

Giả sử class `Worker` có các thành viên hợp lệ và `lookup` có quyền truy cập tương ứng:

| Member / hành động | `MethodType` đưa vào Lookup | `MethodType` thực tế của handle | Receiver? |
| --- | --- | --- | --- |
| `static int calc(String x)` qua `findStatic` | `(String)int` | `(String)int` | Không |
| `String render(int n)` qua `findVirtual` | `(int)String` | `(Worker,int)String` | Có, vị trí 0 |
| `new Worker(String id)` qua `findConstructor` | `(String)void` | `(String)Worker` | Không, object được tạo mới |
| `render` sau `bindTo(worker)` | Handle sẵn có `(Worker,int)String` | `(int)String` | Receiver đã gắn, không truyền nữa |

Bảng trên mô tả nguyên tắc chuẩn khi lookup thành công. Với protected method, một số kiểu handle khác hoặc adapter đặc biệt, receiver type có thể chặt hơn `Worker`; kiểm tra `handle.type()` là nguồn xác minh tức thời.

### 12.1. Receiver của Reflection không phải một tham số `MethodType` riêng biệt

Java có cú pháp annotated receiver parameter trong trường hợp hợp lệ, ví dụ `void m(@Readonly Example this)` (chỉ minh họa cú pháp, giả định annotation tồn tại). Reflection có thể đọc receiver annotations qua `Executable.getAnnotatedReceiverType()`. Nhưng metadata chú thích receiver không khiến `MethodType` của **chữ ký khai báo** tự thêm một tham số `this`. Khi mô tả handle gọi method instance, receiver hiện diện trong handle signature bởi **cơ chế invocation**, không bởi một modifier hay tên tham số.

Đây là điểm quan trọng khi kết hợp `Method.getParameterTypes()` với `MethodHandles.Lookup.findVirtual`: mảng kiểu tham số khai báo không chứa receiver; Handle type sau lookup thì có.

## 13. Tình huống ứng dụng: viết bộ kiểm tra chữ ký cho runtime invocation

Một loader hoặc framework chọn method theo cấu hình, chẳng hạn tên class, method, danh sách kiểu đầu vào và kiểu trả về. Một quy trình hợp lý:

1. Giải quyết class chứa method và các tham số thành đối tượng `Class<?>` từ **class loader có chủ đích**; không coi tên chuỗi là đủ để chứng minh hai kiểu là một.
2. Dựng `MethodType` theo **thứ tự `returnType`, rồi `parameterTypes`**.
3. Chọn đúng cách lookup: `findStatic` cho static method, `findVirtual` cho instance method, `findConstructor` cho constructor.
4. Sau lookup, đọc `handle.type()` để nhận diện **receiver** được chèn hoặc **kiểu trả về của constructor** được thay.
5. Nếu có instance cố định, dùng `bindTo` theo hợp đồng; nếu kiểu đầu vào của caller khác, chỉ dùng `asType` khi chuyển đổi an toàn và được hỗ trợ.
6. Ghi log descriptor hoặc danh sách class type cùng class loader khi chẩn đoán, và tách lỗi lookup khỏi lỗi gọi.

Đối với công cụ log, nên ghi cả:

```text
requested member: Handler.echo(String,int):String
lookup type:       (String,int)String
handle type:       (Handler,String,int)String
bound handle type: (String,int)String
```

Không tạo tên method từ `MethodType` hoặc suy luận quyền truy cập từ `handle.type()`. Để diễn giải generic, tên tham số, annotation hoặc modifier, đọc API Reflection tương ứng ngoài `MethodType`.

### 13.1. Đối chiếu `java.lang.reflect.Method` với `MethodType`

Khi đã có `java.lang.reflect.Method reflected`, có thể dựng chữ ký **khai báo**:

```java
// Fragment: reflected là đối tượng java.lang.reflect.Method đã có.
MethodType declaredType = MethodType.methodType(
        reflected.getReturnType(), reflected.getParameterTypes());
```

`getParameterTypes()` chứa **kiểu erased của tham số khai báo**, không tự gồm receiver. Nếu method instance và bạn tìm lại bằng `findVirtual(reflected.getDeclaringClass(), reflected.getName(), declaredType)`, handle nhận receiver đầu tiên nếu lookup thành công. Với method static, chữ ký handle không thêm receiver. Lựa chọn `Lookup.unreflect(reflected)` hữu ích khi đã có `Method`; vẫn cần quyền truy cập phù hợp.

### 13.2. Chọn cách hiển thị hợp đồng cho người đọc hay máy

- `MethodType.toString()` ngắn và phù hợp học/diagnostic; tên lớp dùng **simple name** nên có thể trùng nhau giữa package khác nhau.
- `toMethodDescriptorString()` phù hợp đối chiếu bytecode và lưu kiểu descriptor theo JVMS, nhưng **không lưu danh tính class loader**.
- Nếu cần định danh một method duy nhất, kết hợp ít nhất class chủ sở hữu, tên method, kiểu tham số và kiểu trả về, cùng ngữ cảnh loader/module khi cần.
- Không dùng `MethodType.toString()` làm giao thức serialize bất biến giữa các phiên bản hay hệ thống.

## 14. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchMethodException` khi `findVirtual` | Truyền type **có cả receiver** vào lookup hoặc sai kiểu tham số/kiểu trả về, sai tên method | Bỏ receiver khỏi type yêu cầu, đọc signature khai báo chính xác |
| `NoSuchMethodException` khi `findStatic` | Method không static hoặc type/name khác | Chọn đúng lookup và chữ ký |
| `IllegalAccessException` tại Lookup | Class/member hoặc module không cho quyền truy cập tương ứng | Dùng lookup có quyền hợp lệ, kiểm tra visibility/module exports/opens |
| `WrongMethodTypeException` tại `invokeExact` | Call-site type khác `handle.type()`, có thể do **kiểu kết quả** | In `handle.type()`, kiểm tra cast và kiểu tĩnh từng đối số |
| `WrongMethodTypeException` tại `asType`/`invoke` | Không có phép chuyển đổi hợp lệ theo API | Thiết kế adapter đúng hoặc chuyển dữ liệu có chủ đích trước khi gọi |
| `ClassCastException` khi invoke/adapt | Reference chuyển kiểu không hợp lệ khi chạy | Kiểm tra kiểu runtime và hợp đồng |
| `IllegalArgumentException` tạo `MethodType` | Tham số `void.class` hoặc vượt số slot | Sửa khai báo kiểu và số tham số |
| `IndexOutOfBoundsException` từ `parameterType`/`dropParameterTypes` | Index không nằm trong phạm vi | Kiểm tra `parameterCount()` và đoạn nửa mở |
| `TypeNotPresentException` từ descriptor | Class reference trong descriptor không giải được bằng loader | Kiểm tra class loader, classpath/module path |
| Gọi `bindTo` xong vẫn truyền receiver | Receiver đã được cố định, số tham số handle giảm | Gọi theo `bound.type()` thực tế |

**Phân biệt các thời điểm:** lỗi `NoSuchMethodException` và `IllegalAccessException` thường xuất hiện khi **lookup**; `WrongMethodTypeException` xảy ra khi **ghép kiểu/gọi/adapt handle**; lỗi nghiệp vụ của method được gọi là vấn đề khác. `MethodType` một mình chỉ là mô tả kiểu; nó không khởi chạy code của phương thức đích.

## 15. Câu hỏi tự kiểm tra

1. Với `MethodType.methodType(void.class, String.class, int.class)`, kiểu trả về là gì và `parameterCount()` bằng bao nhiêu?
2. Method khai báo `String query(int id)` trong class `Repository` được tìm bằng `findVirtual`. Có cần thêm `Repository.class` vào `MethodType` truyền cho lookup không? `handle.type()` có thể là gì?
3. Vì sao `findConstructor(Widget.class, methodType(void.class, String.class))` cho handle trả về `Widget`?
4. Khi `bindTo` một receiver, `parameterCount()` của handle tăng hay giảm?
5. `(long) handle.invokeExact(7L)` thành công với handle `(long)long`. Vì sao `Object x = handle.invokeExact(7L)` có thể sai?
6. Trong descriptor `(Ljava/lang/String;J)I`, ký tự `J` và `I` đại diện cho gì? Tên method và receiver có nằm trong descriptor không?
7. `MethodType` có phân biệt `List<String>` và `List<Integer>` như hai kiểu tham số runtime khác nhau không?
8. `MethodType.erase()` và `generic()` khác nhau thế nào với một chữ ký chứa `int`?
9. Khi log hai `MethodType` có descriptor cùng chuỗi nhưng `equals()` lại `false`, điều gì ở runtime nên kiểm tra?
10. Nếu method instance nhận **0 tham số khai báo**, có phải handle `findVirtual` cũng có `parameterCount() == 0` không?

**Đáp án gợi ý:** (1) `void`, có 2 tham số. (2) Không; lookup nhận `(int)String`, handle thường `(Repository,int)String`. (3) Constructor JVM có return `void` trong khai báo, handle tạo và trả đối tượng `Widget`. (4) Giảm một khi gắn tham số đầu. (5) `invokeExact` khớp cả return type ngữ cảnh; `Object` khác `long`. (6) `J=long`, `I=int`; không chứa tên/receiver. (7) Không; kiểu generic bị erasure về `List.class` khi tạo descriptor. (8) `erase()` giữ primitive, `generic()` chuyển thành `Object`. (9) Class loader/danh tính `Class<?>`. (10) Không; handle vẫn cần receiver.

## 16. Nguồn đối chiếu chuẩn

- [Java SE 21 API — `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): factory, bất biến, `equals`, đọc tham số/kiểu trả về, descriptor, biến đổi và giới hạn.
- [Java SE 21 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findStatic`, `findVirtual`, `findConstructor` và các quy tắc receiver.
- [Java SE 21 API — `MethodHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `bindTo`, `asType`.
- [JVM Specification 21, `4.3.3 Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3): cú pháp descriptor và giới hạn argument slots.
- [Oracle Java Magazine — Method handles: a better way to do Java reflection](https://blogs.oracle.com/javamagazine/java-reflection-method-handles/): minh họa method signature và receiver sau lookup.

Điều cần ghi nhớ khi dùng `MethodType` là luôn hỏi: **type này mô tả method được khai báo, hay mô tả lời gọi của một `MethodHandle` cụ thể?** Chỉ cần phân biệt đúng hai ngữ cảnh đó, bạn sẽ xác định chính xác tham số, kiểu trả về và receiver khi lookup, bind hoặc invoke trong Java dynamic runtime.