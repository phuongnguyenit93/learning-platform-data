# Gọi phương thức của hidden class qua interface hoặc MethodHandle (Java 15+)

## 1. Mục tiêu và bối cảnh

**Hidden class** là một lớp được định nghĩa động trong JVM, thông thường bằng `MethodHandles.Lookup.defineHiddenClass(byte[], boolean, ClassOption...)`. API này xuất hiện từ **Java 15** và vẫn được hỗ trợ trong Java hiện hành. Hidden class thường phục vụ code sinh lúc chạy: framework, trình biên dịch động, bộ sinh proxy/adapter hoặc runtime không muốn lớp triển khai trở thành một lớp có **binary name có thể liên kết và tìm nạp như lớp thông thường**.

Sau khi định nghĩa hidden class, một vấn đề thực tế là **gọi hành vi của đối tượng đó**. Có hai hướng phổ biến:

1. **Qua interface/lớp cha công khai:** hidden class `implements` một interface mà caller đã biết, ví dụ `Action`. Factory trả về `Action`; caller gọi `action.greet(...)` như Java bình thường.
2. **Qua `MethodHandle`:** code tin cậy đang có `Lookup` và `Class<?>` của hidden class có thể lấy handle tới constructor, phương thức instance hoặc static, sau đó gọi bằng `invoke`, `invokeExact` hay handle đã được điều chỉnh.

Hai cách **không loại trừ nhau**. Cùng một đối tượng có thể vừa dùng qua interface để cung cấp API ổn định, vừa được framework nội bộ gọi bằng `MethodHandle` cho các thao tác động.

> **Ý chính:** *Hidden* không có nghĩa là “không thể gọi phương thức”. Nó chủ yếu hạn chế việc đặt tên/liên kết tới **chính lớp triển khai**. Quan hệ kiểu với interface công khai và việc thực thi các method handle đã được cấp quyền vẫn hoạt động.

## 2. Từ định nghĩa hidden class đến một instance

Luồng cơ bản:

```text
byte[] classfile
      |
      v
Lookup.defineHiddenClass(classfile, initialize)
      |
      v
Lookup của hidden class -----> lookupClass(): Class<?> hiddenType
      |                                    |
      | findConstructor                    | findVirtual / findStatic
      v                                    v
MethodHandle constructor             MethodHandle method
      |
      | invoke()
      v
Object instance
      |                   |
      | cast nếu implements public interface
      v                   v
Action object       instance + MethodHandle
      |                   |
      v                   v
action.greet(...)   handle.invoke(...)/invokeExact(...)
```

Ví dụ thao tác cốt lõi **bên trong một phương thức đã có `byte[] bytes` hợp lệ**:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(bytes, true);
Class<?> hiddenType = hiddenLookup.lookupClass();

MethodHandle constructor = hiddenLookup.findConstructor(
        hiddenType, MethodType.methodType(void.class));
Object instance = constructor.invoke();
```

Đoạn này **không độc lập**, vì chưa khai báo `bytes`/imports; phần 6 có chương trình đầy đủ. Các chi tiết cần hiểu:

- `defineHiddenClass` định nghĩa lớp mới từ bytecode classfile. Tham số `true` yêu cầu **khởi tạo** lớp trong bước định nghĩa; không phải “làm lớp công khai”.
- `MethodHandles.lookup()` phải được gọi từ code có **full privilege access** trong đúng runtime package. Classfile đầu vào phải thuộc **cùng package** với lookup class; `publicLookup()` không đủ quyền để định nghĩa hidden class theo cách trên.
- `lookupClass()` trả về `Class<?>` thật của hidden class. Dùng `hiddenType.isHidden()` để kiểm chứng.
- `findConstructor(hiddenType, methodType(void.class))` tìm constructor không tham số. `void.class` ở `MethodType` là **kiểu trả về khai báo của constructor**, trong khi method handle kết quả có kiểu trả về **instance của hidden class**.
- `constructor.invoke()` tạo instance; biến Java có thể giữ nó dưới `Object`, interface hoặc superclass mà hidden class thực thi.

**Không tìm lớp bằng tên:** `Class.forName(hiddenType.getName())` không phải cách khôi phục hidden class. `Class<?>`, `Lookup` và instance đã có mới là những handle thực sự để dùng lớp. Tên runtime của hidden class không phải binary name thông thường để lập trình viên liên kết trực tiếp từ mã Java khác.

## 3. Hướng A: gọi qua interface công khai

Giả sử ứng dụng định nghĩa:

```java
public interface Action {
    String greet(String name);
}
```

Lớp triển khai (trước khi được định nghĩa thành hidden class) có thể là:

```java
final class HiddenAction implements Action {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Hai đoạn trên là **hai tệp riêng** `Action.java` và `HiddenAction.java` trong cùng package của ví dụ. Việc `HiddenAction` là package-private ở mã nguồn **không tự biến nó thành hidden class**; phải đưa bytecode vào `defineHiddenClass` như phần 2.

Khi factory đã tạo được instance:

```java
Action action = (Action) instance;
String result = action.greet("Linh");
```

`result` bằng `"Xin chào, Linh!"`. JVM biết đối tượng có triển khai `Action`, nên phép cast và **dispatch qua interface** hợp lệ. Client không phải viết tên hidden implementation trong source hay constant pool của mình.

**Ưu điểm:** kiểu kiểm tra ở compile-time, method name/signature rõ ràng, dễ test, dễ IDE autocomplete, thuận lợi cho API công khai. Factory có thể thay đổi cách sinh/định nghĩa hidden class nhưng chữ ký API vẫn là `Action`.

**Giới hạn:** caller chỉ gọi được phương thức có trong hợp đồng `Action` (hoặc kiểu tĩnh khác mà caller có quyền truy cập). Phương thức riêng `marks(int)` của hidden implementation sẽ không thể gọi bằng `action.marks(3)` nếu `Action` không khai báo nó.

Lưu ý về module: một interface khai báo `public` chưa chắc truy cập được từ mọi module. Với **named modules**, package của public API phải được `exports` phù hợp và module caller phải đọc được module đó. Quan hệ `implements` cũng phụ thuộc **định danh lớp** (class loader + binary name của interface): hai interface cùng tên ở hai class loader khác nhau không tự trở thành cùng một kiểu.

## 4. Hướng B: lấy `MethodHandle` từ hidden class

Code framework có `hiddenLookup` và `hiddenType` của hidden class có thể tạo handle tới phương thức instance:

```java
MethodHandle greet = hiddenLookup.findVirtual(
        hiddenType, "greet",
        MethodType.methodType(String.class, String.class));
```

Điểm quan trọng là phân biệt **method type khi tra cứu** và **method type của handle sau tra cứu**:

- `findVirtual` nhận `MethodType.methodType(String.class, String.class)`: nghĩa là **kết quả `String`**, **một đối số `String`**; **không liệt kê receiver** trong tham số tra cứu.
- `greet.type()` của handle trả về sẽ có dạng `(HiddenAction/0x..., String)String` về mặt ý nghĩa: đối số đầu tiên là **receiver** kiểu hidden class, sau đó đến `name`. Phần tên/suffix thực tế của lớp hidden có thể khác nhau giữa mỗi lần chạy.
- `hiddenLookup.findVirtual(...)` kiểm tra truy cập theo quyền của `Lookup`; không có quyền phù hợp sẽ không nhận được handle như mong muốn.

Sau khi đã có `Object instance`:

```java
String message = (String) greet.invoke(instance, "Nam");
```

Mặc dù biến `instance` có kiểu tĩnh `Object`, `invoke` có thể **điều chỉnh kiểu** ở lời gọi để cast receiver sang runtime hidden class trước khi gọi. Đối tượng phải thực sự là instance phù hợp; đối tượng sai kiểu có thể dẫn đến `ClassCastException`.

Kết quả ở ví dụ là `"Xin chào, Nam!"`. Phần 6 xác nhận bằng chương trình chạy thực tế.

### 4.1. MethodHandle không phải Java reflection thông thường

`MethodHandle` có **kiểu phương thức** (method type) được kiểm tra ở thời điểm liên kết/thực thi lời gọi; nó có thể được lấy từ `Lookup.findVirtual`, `findStatic`, `findConstructor`, hoặc điều chỉnh bằng các combinator/adapter.

- **`findVirtual`**: phương thức instance; handle chưa bind có **receiver ở tham số đầu**.
- **`findStatic`**: phương thức static; **không có receiver**. Chỉ dùng khi method được khai báo static và lookup có quyền.
- **`findConstructor`**: trả handle tạo đối tượng; việc dùng `MethodType.methodType(void.class, ...)` khi tìm constructor không có nghĩa kết quả gọi handle là `void`.
- **`bindTo(object)`**: cố định receiver tham chiếu ở vị trí đầu, tạo handle mới với **một tham số ít hơn**.
- **`asType(newType)`**: tạo adapter cho phép đổi kiểu đối số/kết quả theo những phép chuyển đổi được MethodHandle cho phép.

Method handle **không tự vượt qua** Java access control. Một `Lookup` không đủ quyền vẫn không thể lấy handle tới member tùy ý. Không nên coi việc biết `Class<?>` hoặc một chuỗi tên method là quyền gọi mọi private member.

### 4.2. `invoke` và `invokeExact`: khác biệt sống còn

| Tiêu chí | `invoke(...)` | `invokeExact(...)` |
|---|---|---|
| Kiểu tại call site | Có thể được điều chỉnh tương đương `asType`, nếu chuyển đổi hợp lệ | **Bắt buộc trùng chính xác** với `handle.type()` |
| Receiver tĩnh `Object` khi handle đòi hidden class | Có thể cast động nếu đối tượng đúng loại | Lỗi `WrongMethodTypeException` vì signature không trùng |
| Tham số primitive/return type | Một số boxing, unboxing, widening hoặc cast hợp lệ có thể áp dụng | Không tự thay đổi kiểu call-site |
| Dùng khi nào | Tích hợp động, kiểu nhận ở runtime chưa hoàn toàn khớp | Khi bạn kiểm soát chính xác descriptor và muốn hợp đồng gọi rõ ràng |
| Lỗi điển hình | `WrongMethodTypeException`, `ClassCastException`, các exception từ target | `WrongMethodTypeException` nếu sai method type; exception từ target nếu đã gọi được |

Ví dụ **sai** với handle nhận hidden class làm receiver:

```java
// Minh họa trong phạm vi có MethodHandle greet và Action action.
String wrong = (String) greet.invokeExact(action, "Test");
```

Lời gọi này **biên dịch được** do `invokeExact` là signature-polymorphic, nhưng khi chạy ném `WrongMethodTypeException` vì compiler phát descriptor `(Action, String)String`, trong khi handle gốc cần `(HiddenClass, String)String`. Java source không có một tên kiểu hidden class ổn định để viết trực tiếp vào descriptor call site.

**Sửa bằng adapter:**

```java
MethodHandle viaAction = greet.asType(
        MethodType.methodType(String.class, Action.class, String.class));
String ok = (String) viaAction.invokeExact(action, "Bình");
```

Đây là một giải pháp khi phía Java chỉ biết **interface công khai** ở compile-time. Adapter có kiểu đúng `(Action, String)String`, thực hiện cast receiver `Action` về hidden class lúc chạy rồi gọi target. Nếu `Action` thực tế không đến từ hidden class mong đợi, quá trình chuyển đổi receiver sẽ thất bại, không tự gọi một implementation khác.

**Chi tiết hay bị bỏ qua:** với `invokeExact`, **kiểu trả về tại call site cũng phải chính xác**. Cast `(String)` ở biểu thức trên không phải trang trí: nó giúp compiler phát descriptor trả về `String`. Nếu bạn bỏ cast và chỉ gọi như một statement, call site có return type `void` và có thể không khớp với handle trả `String`.

### 4.3. Bind receiver bằng `bindTo`

Khi thường xuyên gọi cùng một instance, có thể bind receiver:

```java
MethodHandle bound = greet.bindTo(instance);
String result = (String) bound.invokeExact("Mai");
```

Nếu `greet.type()` có hai tham số `(hiddenType, String)`, `bound.type()` chỉ còn một tham số `(String)`. Khi đó `invokeExact("Mai")` hợp lệ mà code không cần nhắc tới hidden class ở chữ ký. `bindTo` yêu cầu đối số đầu tiên là **kiểu tham chiếu**, phù hợp với receiver của phương thức instance; nó không dùng để bind primitive tùy ý.

Hãy cân nhắc vòng đời: handle đã bind giữ tham chiếu tới instance; lưu giữ handle lâu dài có thể đồng thời giữ instance/class liên quan sống lâu hơn mong muốn. Tối ưu hiệu năng chỉ nên dựa trên đo lường có kiểm soát, không giả định mọi lời gọi `MethodHandle` đều nhanh hơn dispatch interface.

### 4.4. Gọi method không có trên interface

Ví dụ `HiddenAction` còn có method `public String marks(int count)`. Client kiểu `Action` không thể viết `action.marks(3)`. Code có `Lookup` phù hợp có thể làm:

```java
MethodHandle marks = hiddenLookup.findVirtual(
        hiddenType, "marks", MethodType.methodType(String.class, int.class));
String result = (String) marks.invoke(instance, 3);
```

Với implementation `return "#".repeat(count);`, kết quả là `"###"`. Đây là một use case thực tế của MethodHandle: **framework gọi method được phát hiện lúc runtime** dù method đó không được công bố trong interface của client.

Với API công khai lâu dài, không nên để client phụ thuộc vào string `"marks"` hay tên implementation nội bộ. Thay vì vậy, hãy công bố một method trên interface, wrapper công khai, hoặc một handle đã được giới hạn năng lực nếu thật sự cần cơ chế gọi động.

## 5. So sánh nhanh và chọn cách phù hợp

| Nhu cầu | Interface / public superclass | MethodHandle |
|---|---|---|
| Client thông thường gọi hành vi có hợp đồng ổn định | **Ưu tiên** | Thường không cần |
| Compile-time checking, IDE refactor, tài liệu API dễ hiểu | **Mạnh** | Tên/kiểu method thường được kiểm tra động khi tạo handle |
| Framework đang có `Class<?>` hidden class và `Lookup` | Có thể ép kiểu nếu implementation khai báo interface | **Phù hợp** để tìm/bind phương thức |
| Gọi method chỉ tồn tại ở implementation | Không gọi trực tiếp qua interface chưa khai báo method | Có thể, với lookup đủ quyền |
| Lưu callback có thể gọi lại nhiều lần | Interface chức năng như `Runnable`, `Function` hoặc interface riêng | Handle đã bind/adapt cũng có thể dùng |
| Thay thế implementation mà giữ API ổn định | **Rất phù hợp** | Nếu công bố raw handle, cần quản lý method type kỹ |
| Quyền truy cập | Theo Java access control của public type | Theo quyền `Lookup` khi tạo handle và ranh giới capability |
| Hiệu năng | Dispatch interface tối ưu tốt | Có thể được JVM tối ưu nhưng còn phụ thuộc kiểu call site/adapter; cần benchmark |

Khi caller chỉ cần `greet`, **`Action` là thiết kế dễ hiểu và ít lỗi hơn**. Khi code runtime phải gọi một method của lớp mới được định nghĩa và không có tên tĩnh công khai, `MethodHandle` mang lại khả năng gọi động an toàn theo method type. Trong framework, có thể kết hợp: nội bộ giữ handle, bên ngoài trả interface.

## 6. Chương trình Java hoàn chỉnh (đã kiểm chứng với Java 17+)

Ví dụ có ba tệp cùng package mặc định; mục đích là mô phỏng việc biên dịch một implementation bình thường rồi **nạp lại classfile bằng `defineHiddenClass`**. Khi dùng trong dự án thật, nên đặt trong package được quản lý rõ ràng; yêu cầu bytecode và lookup phải cùng package vẫn giữ nguyên.

Sơ đồ:

```text
Action.java             (public interface)
HiddenAction.java       (implementation; compile lấy bytecode)
HiddenCallDemo.java     (nạp bytecode, định nghĩa hidden class, gọi hai kiểu)
```

### 6.1. `Action.java`

```java
public interface Action {
    String greet(String name);
}
```

### 6.2. `HiddenAction.java`

```java
final class HiddenAction implements Action {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }

    public String marks(int count) {
        return "#".repeat(count);
    }
}
```

`marks` là method chỉ có trên implementation; interface `Action` không khai báo nó. `String.repeat(int)` đã được Java hỗ trợ từ trước Java 15 nên ví dụ không cần preview feature.

### 6.3. `HiddenCallDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.nio.file.Files;
import java.nio.file.Path;

public class HiddenCallDemo {
    public static void main(String[] args) throws Throwable {
        byte[] classBytes = Files.readAllBytes(Path.of("HiddenAction.bytes"));
        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(classBytes, true);
        Class<?> hiddenType = hiddenLookup.lookupClass();

        MethodHandle constructor =
                hiddenLookup.findConstructor(hiddenType, MethodType.methodType(void.class));
        Object instance = constructor.invoke();
        Action action = (Action) instance;

        System.out.println("hidden=" + hiddenType.isHidden());
        System.out.println("interface=" + action.greet("Linh"));

        MethodHandle greet = hiddenLookup.findVirtual(
                hiddenType, "greet", MethodType.methodType(String.class, String.class));
        System.out.println("mh-receiver-hidden=" + greet.type().parameterType(0).isHidden());
        System.out.println("mh-invoke=" + (String) greet.invoke(instance, "Nam"));

        MethodHandle viaAction = greet.asType(
                MethodType.methodType(String.class, Action.class, String.class));
        System.out.println("mh-exact=" + (String) viaAction.invokeExact(action, "Bình"));

        MethodHandle bound = greet.bindTo(instance);
        System.out.println("mh-bound=" + (String) bound.invokeExact("Mai"));

        MethodHandle marks = hiddenLookup.findVirtual(
                hiddenType, "marks", MethodType.methodType(String.class, int.class));
        System.out.println("hidden-only=" + (String) marks.invoke(instance, 3));

        try {
            String value = (String) greet.invokeExact(action, "Test");
            System.out.println("unexpected=" + value);
        } catch (WrongMethodTypeException ex) {
            System.out.println("raw-exact=WrongMethodTypeException");
        }

        try {
            String value = (String) greet.invoke(new Object(), "Test");
            System.out.println("unexpected=" + value);
        } catch (ClassCastException ex) {
            System.out.println("wrong-receiver=ClassCastException");
        }

        try {
            Class.forName(hiddenType.getName());
            System.out.println("unexpected=by-name");
        } catch (ClassNotFoundException ex) {
            System.out.println("by-name=ClassNotFoundException");
        }
    }
}
```

### 6.4. Biên dịch và chạy

Dùng **JDK 17 hoặc mới hơn**; các API cốt lõi `defineHiddenClass`, `MethodHandle`, `MethodType`, `Class.isHidden` được hỗ trợ với target Java 17. Từ thư mục chứa ba tệp Java, trên **macOS/Linux**:

```bash
javac --release 17 -encoding UTF-8 Action.java HiddenAction.java HiddenCallDemo.java
mv HiddenAction.class HiddenAction.bytes
java -cp . HiddenCallDemo
```

Trên **Windows PowerShell**:

```powershell
javac --release 17 -encoding UTF-8 Action.java HiddenAction.java HiddenCallDemo.java
Rename-Item HiddenAction.class HiddenAction.bytes
java -cp . HiddenCallDemo
```

Tại sao phải đổi tệp `.class` sang `.bytes`? Đây **không phải phép biến đổi bytecode**: nội dung file không đổi. Việc đổi tên giúp lớp `HiddenAction` **không tình cờ được class loader tìm thấy như một lớp thông thường bằng tên** trong bài demo. `defineHiddenClass` mới là thao tác định nghĩa hidden class. `Path.of("HiddenAction.bytes")` phụ thuộc working directory; khi đóng gói ứng dụng thật, có thể đóng gói classfile như một **resource** và đọc bằng classpath/module resource API phù hợp.

**Stdout chính xác** của chương trình:

```text
hidden=true
interface=Xin chào, Linh!
mh-receiver-hidden=true
mh-invoke=Xin chào, Nam!
mh-exact=Xin chào, Bình!
mh-bound=Xin chào, Mai!
hidden-only=###
raw-exact=WrongMethodTypeException
wrong-receiver=ClassCastException
by-name=ClassNotFoundException
```

Giải nghĩa:

- `hidden=true`: object được tạo từ lớp hidden thực.
- `interface=...`: cast sang public interface và dispatch bình thường thành công.
- `mh-receiver-hidden=true`: receiver trong `greet.type()` chính là runtime hidden class, không phải `Action` hay `Object`.
- `mh-invoke=...`: `invoke` điều chỉnh receiver `Object` đúng loại.
- `mh-exact=...`: `asType` tạo handle có call-site descriptor `(Action,String)String`, nên `invokeExact` hoạt động.
- `mh-bound=...`: `bindTo(instance)` loại receiver khỏi danh sách đối số của handle mới.
- `hidden-only=###`: method `marks` không có trên interface vẫn gọi được với `Lookup` phù hợp.
- `raw-exact=...`: `invokeExact` trên handle gốc và receiver được khai báo `Action` thất bại vì **khác method type**.
- `wrong-receiver=...`: truyền một `Object` khác không thuộc hidden class làm cast receiver thất bại.
- `by-name=...`: hidden class không thể được nạp lại qua `Class.forName` bằng tên runtime trả về.

Các chuỗi kết quả không chứa tên runtime hidden class biến thiên, nên có thể so sánh trực tiếp giữa các lần chạy. Mã minh họa `main throws Throwable` chỉ để không che lấp các ngoại lệ method handle; API sản phẩm nên quy định lỗi ở mức phù hợp hơn.

## 7. Những lỗi hay gặp khi gọi qua MethodHandle

| Biểu hiện | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| `WrongMethodTypeException` tại `invokeExact` | Call site khác `handle.type()` ở receiver, đối số **hoặc kiểu trả về** | In `handle.type()`; dùng `asType(...)`, `bindTo` hoặc sửa cast/kiểu tĩnh đúng |
| `WrongMethodTypeException` tại `invoke` | Không thể điều chỉnh method type/arity theo `asType` | So lại số đối số, type trả về, primitive/reference, arity |
| `ClassCastException` khi invoke | Receiver hoặc một đối số reference không thể cast sang kiểu target | Kiểm tra runtime type và class loader; không gửi `new Object()` thay cho instance |
| `NoSuchMethodException` khi `findVirtual` | Sai tên, sai tham số/return type, method static chứ không virtual | Dùng đúng tên và `MethodType`, phân biệt `findVirtual`/`findStatic` |
| `IllegalAccessException` khi lookup | Lookup không đủ quyền với lớp/member hoặc sai module/package | Tạo/giữ lookup từ code tin cậy có quyền hợp lệ; không dùng `publicLookup()` thay thế |
| Lỗi khi `defineHiddenClass` | Classfile không hợp lệ, package của classfile không trùng lookup, lookup thiếu full privilege | Kiểm tra file, runtime package và quyền; không tự bỏ qua module access control |
| `ClassNotFoundException` từ `Class.forName(hiddenType.getName())` | Hidden class không có binary name để tra theo tên | Dùng `Class<?>`, instance, public interface hoặc `Lookup` đã có |
| `NullPointerException` khi bind/nhận receiver | Receiver bị null hoặc API yêu cầu đối tượng thật | Kiểm tra dữ liệu trước khi gọi; `bindTo` phải nhận receiver hợp lệ |
| Factory chạy ở IDE nhưng không tìm thấy `.bytes` khi đóng gói JAR | Dùng đường dẫn tương đối theo working directory | Đưa bytecode vào resource, đóng gói đúng package và đọc qua resource API |
| Dùng `invokeExact` trong statement rồi lỗi dù các đối số giống nhau | Call-site return type có thể thành `void`, không khớp target trả giá trị | Gán/cast kết quả theo đúng return type hoặc dùng handle đã adapt rõ ràng |
| Lộ method nội bộ cho client ngoài ý muốn | Trả trực tiếp `Lookup` hoặc `MethodHandle` quyền rộng | Trả interface hoặc capability giới hạn, không phát tán full-privilege lookup |

**Lỗi của phương thức đích:** exception mà target ném khi thực thi có thể được truyền qua method handle. `MethodHandle.invoke`/`invokeExact` không hoạt động giống `java.lang.reflect.Method.invoke` vốn bọc nhiều lỗi của method đích trong `InvocationTargetException`. Vì API method handle khai báo `throws Throwable`, mã ví dụ dùng `main throws Throwable`; khi xây dựng sản phẩm nên có chính sách riêng cho các loại lỗi mong đợi, không nuốt mọi lỗi bằng `catch (Throwable)` chung chung.

Một handle được tạo ra từ lookup có quyền tương đương **khả năng gọi đã được cấp quyền**. Vì thế phải coi handle hay lookup nhạy cảm là các **capability** cần hạn chế người nhận. Hidden class không phải cơ chế sandbox bảo mật.

## 8. Những quyết định thiết kế đáng lưu ý

### 8.1. Khi công bố API, ưu tiên kiểu mà client biết

Một framework có thể cung cấp:

```java
public static Action newAction() {
    // Tạo instance hidden class bên trong factory;
    // trả interface Action cho người dùng API.
    throw new UnsupportedOperationException("Minh họa chữ ký public API");
}
```

Đây **chỉ là minh họa chữ ký API**, không phải implementation thực hay lệnh nên chạy. Ví dụ đầy đủ phần 6 không sử dụng placeholder này. Điểm cần học là **chữ ký công khai nên dựa trên `Action`**, tránh yêu cầu client nhận `Class<?> hiddenType` hoặc tự tìm tên hidden class để gọi `greet`.

Nếu công cụ sinh code không thể triển khai interface nào đã biết, MethodHandle thích hợp cho biên điều khiển nội bộ. Khi chuyển ra client, bạn có thể bọc một handle trong implementation của một interface chức năng công khai, nhưng wrapper vẫn phải giữ hợp đồng lỗi, type, lifetime và quyền của method handle.

### 8.2. `NESTMATE` không cần cho interface public

`Lookup.ClassOption.NESTMATE` cho phép hidden class được thêm như một nestmate của lookup class, từ đó áp dụng quyền truy cập private trong cùng nest khi thỏa điều kiện. Nó **không bắt buộc** cho ví dụ public interface + public method ở đây. Không sử dụng `NESTMATE` chỉ để giải quyết `WrongMethodTypeException`: đó là vấn đề **descriptor của method handle**, không phải quyền nestmate.

`Lookup.ClassOption.STRONG` thay đổi quan hệ vòng đời giữa hidden class và defining class loader. Nó cũng **không** làm `invokeExact` tự điều chỉnh kiểu. Chỉ cân nhắc `STRONG` khi có yêu cầu thực về vòng đời, sau khi hiểu tác động giữ lớp sống lâu hơn.

### 8.3. Đừng dùng MethodHandle khi không cần

Một public interface thường là lựa chọn tốt khi method được xác định ở compile-time. MethodHandle mang lại linh hoạt nhưng cũng thêm:

- lỗi runtime do sai method type;
- phức tạp access control;
- quản lý bytecode/resource và lookup;
- ràng buộc vòng đời nếu handle giữ receiver hoặc class;
- yêu cầu test đường lỗi, type conversion và các tình huống khởi tạo.

Không có quy tắc **“MethodHandle luôn nhanh hơn interface”**. Hiệu năng tùy loại call site, độ ổn định của kiểu, tối ưu JIT, adapter và workload. Trước khi tối ưu, hãy đo bằng benchmark được thiết kế cẩn thận, giữ cả tính đúng và lỗi có kiểm soát.

### 8.4. Tách phần tạo lớp khỏi phần sử dụng

Mẫu thiết kế bền vững:

1. **Framework nội bộ** tạo/nhận classfile và định nghĩa hidden class bằng lookup có quyền.
2. **Factory nội bộ** tìm constructor, khởi tạo instance, lựa chọn interface hoặc method handle thích hợp.
3. **Public API** trả về `Action`/lớp cha được công bố, hoặc một callback/handle đã giới hạn đúng năng lực.
4. **Client** chỉ phụ thuộc vào hợp đồng công khai; không lưu tên hidden class runtime trong cấu hình/ID dữ liệu.

Khi cần gọi nhiều phiên bản hidden class khác nhau, đừng cache handle bằng **tên runtime** giả định ổn định. Các lần gọi `defineHiddenClass` có thể tạo định nghĩa lớp khác nhau từ cùng classfile; hãy quản lý instance/handle/class identity theo vòng đời thực tế.

## 9. Danh sách kiểm chứng trước khi đưa vào sản phẩm

- [ ] Public interface/superclass thực sự công bố tất cả hành vi mà client cần.
- [ ] Bytecode classfile có package hợp lệ và thực thi đúng interface đã được nạp trong class loader tương thích.
- [ ] Lookup dùng định nghĩa hidden class có full privilege access và đúng runtime package; module access đã được thiết kế.
- [ ] Constructor và method handles được tra đúng `MethodType`; biết rằng `findVirtual` thêm receiver vào handle.
- [ ] Khi dùng `invokeExact`, kiểu đối số **và kiểu kết quả tại call site** trùng hoàn toàn `handle.type()`; nếu không, dùng `asType`/binding thích hợp.
- [ ] Khi dùng `invoke`, kiểm thử cast receiver, chuyển đổi đối số và lỗi target.
- [ ] Không dựa vào `Class.forName` hay một tên runtime ổn định để tìm hidden class.
- [ ] Không rò rỉ lookup hoặc handles nội bộ có quyền rộng; chỉ công bố capability cần thiết.
- [ ] Test trên JDK hỗ trợ, cả IDE và gói phát hành thực tế; đảm bảo bytecode resource được đi kèm và đọc đúng.
- [ ] Test cả hai tuyến: dispatch qua interface và gọi bằng MethodHandle, bao gồm trường hợp sai type/receiver.

## 10. Kết luận

Gọi phương thức của hidden class trong Java 15+ có hai con đường bổ sung nhau. **Interface công khai** cho trải nghiệm Java tĩnh, dễ sử dụng, thích hợp làm hợp đồng bền vững của ứng dụng. **MethodHandle** cho phép framework tra cứu và gọi method của lớp chỉ được biết tại runtime; cần hiểu chính xác **receiver, `MethodType`, `invoke`, `invokeExact`, `asType` và `bindTo`**.

Hidden class làm ẩn **định danh có thể liên kết của implementation**, nhưng không cản trở việc truyền một instance dưới kiểu cha công khai hoặc gọi thông qua method handle hợp lệ. Thiết kế tốt là giữ lookup/method handle có quyền trong phần tin cậy, trao cho caller bề mặt API cần thiết, và kiểm thử các ranh giới type/access.

**Tài liệu chính thức vẫn áp dụng:**

- [Oracle Java SE 26 — `MethodHandles.Lookup` và `defineHiddenClass`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Oracle Java SE 26 — `MethodHandle` (`invoke`, `invokeExact`, `asType`, `bindTo`)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Oracle Java SE 26 — `MethodType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodType.html).
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371) (nền tảng API đưa vào Java 15, vẫn được sử dụng).
