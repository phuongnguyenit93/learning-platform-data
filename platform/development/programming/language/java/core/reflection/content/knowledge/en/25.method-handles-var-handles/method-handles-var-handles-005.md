# `MethodType` và kiểm tra chữ ký trong Java

## 1. `MethodType` mô tả điều gì?

Trong Java, `java.lang.invoke.MethodType` là một **mô tả bất biến của chữ ký kiểu phương thức**: đúng một kiểu trả về và danh sách các kiểu tham số có thứ tự. Nó thuộc nhóm API `java.lang.invoke`, được sử dụng khi tra cứu và gọi `MethodHandle`, khi thích nghi lời gọi động, và khi tra chữ ký truy cập của `VarHandle`.

Ví dụ, chữ ký `String label(String name, int count)` được biểu diễn bởi:

```java
import java.lang.invoke.MethodType;

MethodType signature = MethodType.methodType(
        String.class, String.class, int.class);
System.out.println(signature); // (String,int)String
```

Trong lời gọi `methodType`, **đối số đầu tiên là kiểu trả về**; hai đối số kế tiếp lần lượt là kiểu của `name` và `count`. Chữ ký `(String,int)String` được đọc là "nhận `String` và `int`, trả `String`". Nó **không** bao gồm tên phương thức `label`.

`MethodType` không lưu lớp khai báo, tên phương thức, tên tham số, modifier (`public`/`static`), generic type arguments, annotation hay danh sách `throws`. Chẳng hạn, `List<String>` và `List<Integer>` đều có thể được biểu diễn bằng `List.class` vì type erasure; `MethodType` không thể thay thế một `ParameterizedType`.

So sánh các khái niệm:

| API | Dữ liệu chính | Công dụng |
| --- | --- | --- |
| `MethodType` | Kiểu trả về và kiểu tham số runtime | Mô tả, so khớp, tạo/chỉnh chữ ký kiểu |
| `MethodHandle` | Một thao tác có thể gọi, kèm `type()` | Thực thi lời gọi động |
| `java.lang.reflect.Method` | Phương thức có tên, lớp khai báo, modifiers và metadata | Tìm và gọi phương thức bằng Core Reflection |
| `VarHandle` | Truy cập đến biến/field/phần tử mảng | `GET`, `SET`, CAS và những access mode khác |

**Lưu ý:** `MethodType` chỉ mô tả kiểu, bản thân nó không chứa mã thực thi và không có thao tác gọi phương thức như `invokeExact`.

## 2. Cách tạo và đọc một `MethodType`

Một số overload của factory `MethodType.methodType(...)`:

```java
MethodType none = MethodType.methodType(void.class);
MethodType unary = MethodType.methodType(int.class, String.class);
MethodType binary = MethodType.methodType(
        String.class, String.class, int.class);
MethodType fromArray = MethodType.methodType(
        String.class, new Class<?>[] { String.class, int.class });
```

Đây là các đoạn mã minh họa để đặt trong class/phương thức và import `java.lang.invoke.MethodType`; chương trình đầy đủ có ở phần sau.

Các hàm truy vấn thường dùng:

- `returnType()` trả `Class<?>` mô tả kiểu kết quả; `void.class` được phép khi không có kết quả.
- `parameterCount()` đếm tham số; `parameterType(i)` truy cập tham số thứ `i`, đánh số từ 0.
- `parameterArray()` và `parameterList()` liệt kê các kiểu tham số theo đúng thứ tự; việc thay đổi mảng kết quả không thay đổi `MethodType`.
- `toString()` hiển thị dạng dễ đọc, ví dụ `(String,int)String`.
- `toMethodDescriptorString()` chuyển sang JVM descriptor, ví dụ `(Ljava/lang/String;I)Ljava/lang/String;` (`I` biểu diễn primitive `int`).
- `MethodType.fromMethodDescriptorString(descriptor, loader)` đọc JVM descriptor với class loader được cung cấp để phân giải kiểu tham chiếu.

**Kiểu trả về `void` hợp lệ, kiểu tham số `void` không hợp lệ.** `MethodType.methodType(String.class, void.class)` ném `IllegalArgumentException`. Nếu kiểu trả về hoặc kiểu tham số bị truyền `null`, API ném `NullPointerException`. Đối với `parameterType(i)`, chỉ số ngoài khoảng sẽ phát sinh `IndexOutOfBoundsException`.

Kiểu primitive và wrapper là **hai kiểu khác nhau**: `int.class` khác `Integer.class`. Kiểu mảng là một kiểu riêng: `String[].class` khác `String.class`. `MethodType` xét đối tượng `Class` thực tế, kể cả class loader, không chỉ chuỗi tên lớp.

## 3. So sánh chính xác và biến đổi chữ ký

`MethodType` bất biến. Các phương thức điều chỉnh trả về một `MethodType` khác (hoặc có thể dùng lại đối tượng hiện tại nếu nội dung không đổi), không sửa đối tượng ban đầu:

| Phương thức | Tác dụng |
| --- | --- |
| `changeReturnType(Class<?>)` | Thay kiểu trả về |
| `changeParameterType(index, Class<?>)` | Thay kiểu một tham số |
| `insertParameterTypes(index, Class<?>...)` | Chèn các tham số vào vị trí xác định |
| `appendParameterTypes(Class<?>...)` | Nối thêm các tham số |
| `dropParameterTypes(start, end)` | Bỏ đoạn tham số từ `start` đến trước `end` |
| `wrap()` / `unwrap()` | Chuyển primitive sang wrapper hoặc chiều ngược lại trong mô tả |
| `equals(Object)` | Kiểm tra kiểu trả về và từng kiểu tham số trùng chính xác |

Ví dụ:

```java
MethodType oldType = MethodType.methodType(
        String.class, String.class, int.class);
MethodType newType = oldType.changeReturnType(Object.class)
        .insertParameterTypes(1, long.class);

// oldType: (String,int)String
// newType: (String,long,int)Object
```

Dùng `equals` để so sánh chữ ký theo nội dung; **không dùng `==` để thay cho phép kiểm tra tương đương**. Kiểu, vị trí và số tham số đều quan trọng. Nếu chỉ đổi `int` thành `Integer` hoặc đổi kiểu trả về, hai `MethodType` không bằng nhau.

Biến đổi `MethodType` **không tự động biến đổi hành vi hay kiểu của một `MethodHandle` đang có**. Để tạo handle có kiểu mới và bộ chuyển đổi phù hợp, dùng `handle.asType(newType)` khi chuyển đổi được cho phép.

## 4. Kiểu của `MethodHandle`, receiver và `invokeExact`

`MethodHandle.type()` trả về `MethodType` mà handle yêu cầu tại lời gọi. Với phương thức `static` được tra bằng `Lookup.findStatic`, kiểu handle thường trùng kiểu phương thức mô tả tại lookup.

Với `Lookup.findVirtual`, có hai mức chữ ký cần phân biệt:

```java
// Chữ ký khai báo của String.substring(int, int):
MethodType declared = MethodType.methodType(
        String.class, int.class, int.class);
MethodHandle handle = MethodHandles.lookup()
        .findVirtual(String.class, "substring", declared);

// handle.type(): (String,int,int)String
//              ^ receiver String được đưa vào đầu
```

Ví dụ trên cần import `MethodHandle`, `MethodHandles`, `MethodType` và đặt trong phương thức xử lý checked exceptions. `findVirtual` nhận kiểu theo khai báo, không có receiver. Nhưng khi **gọi handle**, receiver trở thành tham số đầu tiên. `bindTo(receiver)` có thể gắn sẵn receiver trên một handle thích hợp và giảm số tham số của handle kết quả.

`MethodHandle.invokeExact(...)` yêu cầu chữ ký tại **call site** khớp chính xác `handle.type()`: số lượng, thứ tự, kiểu tham số **và kiểu trả về**. Compiler xác định kiểu trả về của call site từ ngữ cảnh của biểu thức. Chẳng hạn:

```java
// handle.type() là (String,int,int)String:
String yes = (String) handle.invokeExact("abcdef", 1, 3);
// Object no = (Object) handle.invokeExact("abcdef", 1, 3);
// Dòng thứ hai có thể biên dịch nhưng ném WrongMethodTypeException.
```

Trường hợp sau yêu cầu **Object** tại call site, còn handle trả **String**. Dù `String` là subtype của `Object`, `invokeExact` không chấp nhận chuyển đổi đó. Khi lời gọi đứng riêng như statement và giá trị bị bỏ qua, call site có kiểu trả về `void`; điều này cũng có thể không khớp.

`MethodHandle.invoke(...)` linh hoạt hơn: nếu chữ ký khác, JVM có thể thực hiện chuyển đổi tương đương `asType` (chẳng hạn ép kiểu tham chiếu, boxing/unboxing trong phạm vi được hỗ trợ). `invokeExact` không làm bước thích nghi này. Khi không thích nghi được, có thể nhận `WrongMethodTypeException`; lỗi cast cụ thể có thể gây `ClassCastException`.

## 5. Ví dụ Java 17+ chạy độc lập: so chữ ký, kiểm tra lỗi và thích nghi

Lưu thành `MethodTypeSignatureDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodTypeSignatureDemo {
    public static String label(String name, int index) {
        return name + "-" + index;
    }

    static void requireType(MethodHandle handle, MethodType expected) {
        if (!handle.type().equals(expected)) {
            throw new IllegalArgumentException(
                    "Expected " + expected + " but found " + handle.type());
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodType signature = MethodType.methodType(
                String.class, String.class, int.class);

        System.out.println("type=" + signature);
        System.out.println("descriptor=" +
                signature.toMethodDescriptorString());
        System.out.println("count=" + signature.parameterCount());
        System.out.println("param0=" +
                signature.parameterType(0).getSimpleName());
        System.out.println("return=" +
                signature.returnType().getSimpleName());

        MethodType changed = signature.changeReturnType(Object.class);
        MethodType inserted = signature.insertParameterTypes(1, long.class);
        System.out.println("changed=" + changed);
        System.out.println("inserted=" + inserted);
        System.out.println("original=" + signature);

        MethodType decoded = MethodType.fromMethodDescriptorString(
                signature.toMethodDescriptorString(),
                MethodTypeSignatureDemo.class.getClassLoader());
        System.out.println("roundtrip=" + decoded.equals(signature));

        MethodHandle handle = MethodHandles.lookup().findStatic(
                MethodTypeSignatureDemo.class, "label", signature);
        System.out.println("handle=" + handle.type());
        requireType(handle, signature);
        System.out.println("checked=true");

        String exact = (String) handle.invokeExact("id", 7);
        System.out.println("exact=" + exact);

        try {
            Object ignored = (Object) handle.invokeExact("id", 7);
            System.out.println("unexpected=" + ignored);
        } catch (WrongMethodTypeException e) {
            System.out.println("wrongReturn=WrongMethodTypeException");
        }

        try {
            requireType(handle, signature.changeReturnType(Object.class));
        } catch (IllegalArgumentException e) {
            System.out.println("precheck=rejected");
        }

        MethodType adaptedType = MethodType.methodType(
                Object.class, Object.class, Integer.class);
        MethodHandle adapted = handle.asType(adaptedType);
        Object boxed = (Object) adapted.invokeExact(
                (Object) "box", Integer.valueOf(5));
        System.out.println("adaptedType=" + adapted.type());
        System.out.println("adaptedResult=" + boxed);

        MethodHandle substring = MethodHandles.lookup().findVirtual(
                String.class, "substring",
                MethodType.methodType(String.class, int.class, int.class));
        System.out.println("virtualType=" + substring.type());
        String part = (String) substring.invokeExact("methodtype", 0, 6);
        System.out.println("substring=" + part);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 MethodTypeSignatureDemo.java
java MethodTypeSignatureDemo
```

Stdout chính xác:

```text
type=(String,int)String
descriptor=(Ljava/lang/String;I)Ljava/lang/String;
count=2
param0=String
return=String
changed=(String,int)Object
inserted=(String,long,int)String
original=(String,int)String
roundtrip=true
handle=(String,int)String
checked=true
exact=id-7
wrongReturn=WrongMethodTypeException
precheck=rejected
adaptedType=(Object,Integer)Object
adaptedResult=box-5
virtualType=(String,int,int)String
substring=method
```

Giải thích các điểm then chốt:

1. `changeReturnType` và `insertParameterTypes` giữ nguyên `signature` ban đầu; `roundtrip=true` chứng minh descriptor giải mã trở về chữ ký tương đương.
2. `handle.type()` của `findStatic` khớp chữ ký `(String,int)String` đã dùng tra cứu. Hàm `requireType` kiểm tra trước khi dùng để phát hiện việc kết nối nhầm contract.
3. `String exact = (String) handle.invokeExact(...)` thành công. Cast kết quả `Object` làm thay đổi kiểu trả về của call site nên ném `WrongMethodTypeException`.
4. `asType` tạo adapter có kiểu `(Object,Integer)Object`, ép `Object` chứa chuỗi thành `String`, unbox `Integer` sang `int` rồi nâng kết quả `String` thành `Object`. Adapter không sửa handle ban đầu.
5. `findVirtual` yêu cầu receiver `String` đứng đầu. Hàm `substring("methodtype", 0, 6)` trả về `method`.

Hàm `requireType` là kiểm tra contract chủ động; JVM vẫn thực thi kiểm tra riêng khi gặp lời gọi `invokeExact`.

## 6. Liên hệ `VarHandle`: chữ ký phụ thuộc access mode

`VarHandle` không có một chữ ký chung cho mọi thao tác. `GET` đọc giá trị, `SET` ghi giá trị và nhận thêm đối số mới, `COMPARE_AND_SET` có hợp đồng riêng. Có thể tra:

- `vh.accessModeType(VarHandle.AccessMode.GET)` — kiểu call site của `GET`.
- `vh.accessModeType(VarHandle.AccessMode.SET)` — kiểu call site của `SET`.
- `vh.toMethodHandle(mode).type()` — kiểu của MethodHandle đại diện access mode.
- `vh.isAccessModeSupported(mode)` — xác định access mode có được loại VarHandle đó hỗ trợ hay không.

Với phần tử `int[]`, tọa độ gồm **mảng** và **chỉ số**. Một ví dụ độc lập lưu vào `VarHandleSignatureDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;

public class VarHandleSignatureDemo {
    public static void main(String[] args) {
        VarHandle vh = MethodHandles.arrayElementVarHandle(int[].class);
        MethodType getType = vh.accessModeType(VarHandle.AccessMode.GET);
        MethodType setType = vh.accessModeType(VarHandle.AccessMode.SET);
        MethodHandle getHandle = vh.toMethodHandle(VarHandle.AccessMode.GET);

        System.out.println("get=" + getType);
        System.out.println("set=" + setType);
        System.out.println("methodHandle=" + getHandle.type());
        System.out.println("getMatches=" + getHandle.type().equals(getType));

        int[] values = { 10, 20 };
        int value = (int) vh.get(values, 1);
        vh.set(values, 1, 42);
        System.out.println("before=" + value);
        System.out.println("after=" + values[1]);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 VarHandleSignatureDemo.java
java VarHandleSignatureDemo
```

Stdout:

```text
get=(int[],int)int
set=(int[],int,int)void
methodHandle=(int[],int)int
getMatches=true
before=20
after=42
```

`GET` có kiểu `(int[],int)int`; `SET` có kiểu `(int[],int,int)void` vì nhận thêm giá trị mới. Lời gọi access mode của `VarHandle` cũng có ngữ nghĩa signature polymorphic; kiểm tra `accessModeType` giúp tránh nhầm số và kiểu tọa độ, giá trị cần ghi và kiểu kết quả.

## 7. Cách kiểm tra chữ ký khi tích hợp code động

Trong hệ thống ánh xạ lời gọi runtime, plugin, adapter hoặc thư viện tạo MethodHandle, nên thực hiện:

1. Xây `MethodType expected` dựa trên hợp đồng của thao tác cần gọi. Ghi rõ **kiểu trả về**, không chỉ tham số.
2. Đọc kiểu thực tế bằng `handle.type()`. Với instance method, tính cả receiver, còn với VarHandle chọn `accessModeType` theo đúng mode.
3. Nếu yêu cầu trùng tuyệt đối, dùng `expected.equals(actual)` và đưa ra lỗi giải thích khi không khớp.
4. Nếu chủ định chấp nhận chuyển đổi, tạo adapter `handle.asType(expected)` và kiểm tra logic cast/unboxing; adapter có thể thất bại ngay hoặc lúc gọi tùy kiểu chuyển đổi.
5. Khi đọc descriptor từ bytecode hay cấu hình, sử dụng class loader phù hợp. Chữ ký đúng **không bảo đảm** target method tồn tại hoặc được truy cập: `Lookup.findStatic`/`findVirtual` còn thực hiện kiểm tra quyền truy cập và có thể ném `NoSuchMethodException` hoặc `IllegalAccessException`.

Với API mà kiểu đích biết tại compile time, ưu tiên lời gọi Java thông thường; `MethodType` hữu ích khi thực sự cần mô tả và xử lý chữ ký ở runtime.

## 8. Lỗi thường gặp

| Sai sót | Biểu hiện và cách tránh |
| --- | --- |
| Nhầm tham số đầu của `methodType` | Nó là **kiểu trả về**, còn các kiểu tham số theo sau |
| Cho `void.class` vào tham số | `IllegalArgumentException`; `void` chỉ phù hợp với kiểu trả về |
| Dùng `==` để so nội dung chữ ký | Dùng `equals` |
| Nhầm `int.class` và `Integer.class` | Chữ ký khác nhau; `invokeExact` không tự boxing |
| Bỏ receiver của `findVirtual` | `handle.type()` có thêm receiver ở vị trí đầu |
| Bỏ qua kiểu trả về tại `invokeExact` | Call site có thể sai dù mọi đối số nhìn đúng |
| Tưởng `asType` sửa nguyên handle | Nó trả về adapter có kiểu mới |
| Dùng `toString()` làm JVM descriptor | Dùng `toMethodDescriptorString()` |
| Tưởng `MethodType` lưu generic/throws/tên method | Chỉ mô tả kiểu runtime của tham số/trả về |
| Dùng chữ ký `get` cho `set` của `VarHandle` | Kiểm tra `accessModeType(mode)` cho từng mode |
| Trộn kiểu từ class loader khác nhau | Danh tính `Class` phụ thuộc loader; cần giải mã descriptor với loader đúng |

`invokeExact` và `invoke` khai báo `throws Throwable`; các ví dụ dùng `main throws Throwable` để code chạy độc lập. `WrongMethodTypeException` thường cho biết sai hợp đồng kiểu tại call site, trong khi `ClassCastException` có thể là lỗi chuyển giá trị khi dùng adapter.

## 9. Tự kiểm tra

**1.** `MethodType.methodType(void.class, String.class)` có hợp lệ không? — **Có**: nhận `String` và trả `void`. Ngược lại, `methodType(String.class, void.class)` không hợp lệ.

**2.** `findVirtual(String.class, "substring", methodType(String.class, int.class, int.class))` tạo `handle.type()` nào? — **`(String,int,int)String`**, vì có receiver `String`.

**3.** Handle có kiểu `(String,int)String`; ép kết quả `invokeExact` sang `Object` có phù hợp không? — **Không**: call site muốn trả `Object`, không trùng `String`.

**4.** Vì sao `VarHandle` cần `accessModeType` thay vì dùng một `MethodType` duy nhất? — Vì các mode có số tham số và kiểu trả về khác nhau.

**Ghi nhớ:** `MethodType` là hợp đồng kiểu bất biến. Khi kiểm tra lời gọi động, đối chiếu đầy đủ **return type + danh sách tham số theo thứ tự + receiver**; dùng `handle.type()` và `VarHandle.accessModeType(mode)` để xác nhận trước khi thực thi.

Tham khảo: [Javadoc `MethodType` Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html), [Javadoc `MethodHandle` Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html), [Javadoc `VarHandle` Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html).