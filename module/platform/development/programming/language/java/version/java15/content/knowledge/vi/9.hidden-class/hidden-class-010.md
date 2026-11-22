# Ứng dụng hidden class trong lambda, adapter và framework sinh mã

**Hidden class** (lớp ẩn) là một loại class được JVM định nghĩa trong thời gian chạy để phục vụ **chi tiết triển khai nội bộ**, thay vì để các lớp khác tìm và tham chiếu bằng tên nhị phân (*binary name*). Tính năng này được đưa vào Java 15 bằng **JEP 371** và tiếp tục có mặt trong các phiên bản Java hiện đại.

Hidden class đặc biệt hữu ích khi chương trình hoặc thư viện cần **tạo bytecode cho những lớp trợ giúp**: hiện thực hóa lambda, kết nối một method handle với interface, tạo adapter hoặc thực thi một đoạn mã do framework biên dịch động. Thay vì thêm hàng loạt tên class vào không gian tên của class loader, framework có thể tạo một implementation mà mã bên ngoài chỉ cần biết **interface, `MethodHandle` hoặc đối tượng** được trả ra.

## 1. Hidden class là gì và không phải là gì?

Đối với một class thông thường:

```java
class NamedAdapter {
    String adapt(String input) {
        return "[" + input + "]";
    }
}
```

JVM có thể tải nó qua class loader và các đoạn mã khác có thể tham chiếu bằng tên nhị phân thích hợp.

Một hidden class được tạo thông qua API:

```java
MethodHandles.Lookup#defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
```

Đây là **ký hiệu chữ ký API để giải thích**, không phải một câu lệnh Java độc lập. Trong code thật gọi `lookup.defineHiddenClass(bytes, true, options...)`, sau đó lấy `hiddenLookup.lookupClass()`.

Khác biệt chính:

| Đặc điểm | Class thông thường | Hidden class |
| --- | --- | --- |
| Cách định nghĩa | `ClassLoader.defineClass`, compiler/linker hoặc `Lookup.defineClass` | `Lookup.defineHiddenClass` |
| Tên để mã khác tra cứu | Có tên nhị phân thông thường | **Không có tên nhị phân dùng để tra cứu** |
| Tra cứu bằng `Class.forName(name)` | Có thể tìm nếu đúng tên, class loader và môi trường | **Không** tìm được hidden class theo tên |
| Trực tiếp dùng làm kiểu được ghi trong constant pool của class khác | Có thể | Không thể tham chiếu hidden class bằng tên từ constant pool của class khác |
| Tiếp cận lúc chạy | `Class<?>`, instance, reflection và method handle | Vẫn có `Class<?>`, instance, reflection và method handle khi nắm được tham chiếu hợp lệ |
| Vòng đời | Thường gắn với khả năng giải phóng class loader | Mặc định có thể được unload độc lập với loader; tùy `STRONG` và reachability |

**Hidden không có nghĩa là bí mật hay sandbox bảo mật.** Một hidden class vẫn có `Class<?>`, có thể được quan sát qua đối tượng hoặc công cụ phù hợp; nó không dùng để che giấu mã độc và không tự hạn chế quyền thực thi.

Cũng không nên nhầm hidden class với **`private` nested class**, **anonymous class** viết bằng `new Interface() { ... }`, hay class có tên khó đoán. Một class khai báo trong mã nguồn bằng cú pháp thông thường không tự trở thành hidden class.

## 2. Vì sao lambda là ví dụ điển hình?

Khi viết:

```java
import java.util.function.Function;

Function<String, String> shout = value -> value.toUpperCase();
System.out.println(shout.apply("java")); // JAVA
```

Tại mức ngôn ngữ, người lập trình chỉ yêu cầu một đối tượng thực hiện **functional interface** `Function<String, String>`. Compiler có thể biên dịch biểu thức lambda thành lời gọi `invokedynamic`; JVM liên kết điểm gọi thông qua cơ chế như `java.lang.invoke.LambdaMetafactory` để tạo ra đối tượng triển khai interface.

Trong **OpenJDK hiện đại**, phần implementation của nhiều lambda được sinh dưới dạng **hidden class**. Điều này phù hợp vì:

- Mã ứng dụng cần **gọi `shout.apply(...)`**, không cần tra cứu một tên class implementation của lambda.
- Class implementation là chi tiết do runtime sinh ra; tên và cấu trúc có thể thay đổi.
- Một lớp trợ giúp nội bộ không cần trở thành một mục tên bình thường để các class khác liên kết bằng constant pool.
- Runtime có thể chọn vòng đời và phương pháp chia sẻ/tái sử dụng implementation phù hợp.

**Không suy từ đây rằng mọi JVM bắt buộc phải hiện thực hóa lambda bằng hidden class.** Ngôn ngữ Java chỉ quy định hành vi của lambda, không bắt buộc người lập trình dựa vào tên lớp sinh, số lượng lớp sinh hoặc kết quả `getClass().isHidden()` của đối tượng lambda.

Đoạn kiểm tra sau có thể dùng để **quan sát một bản JDK cụ thể**, nhưng không phải kiểm thử portable cho đúng/sai của biểu thức lambda:

```java
Runnable task = () -> System.out.println("run");
System.out.println(task.getClass().isHidden());
```

Trên nhiều bản OpenJDK hiện đại, dòng thứ hai in `true`; đó là **đặc điểm triển khai**, không phải lời hứa của đặc tả ngôn ngữ đối với mọi bản JVM.

Một lưu ý quan trọng về vòng đời: implementation lambda do OpenJDK tạo thường sử dụng **strong hidden class**, vì runtime muốn gắn chúng với vòng đời loader của lớp gọi. Không kết luận rằng mọi lambda có thể được unload riêng ngay sau khi một instance lambda biến mất.

## 3. Adapter: dùng lớp ẩn phía sau một interface ổn định

**Adapter** chuyển một cơ chế gọi thành một interface thuận tiện hơn. Ví dụ framework có sẵn một phép biến đổi văn bản ở dạng bytecode sinh động, nhưng khách hàng chỉ làm việc qua một hợp đồng:

```java
interface TextAdapter {
    String adapt(String input);
}
```

Một framework có thể tạo class triển khai `TextAdapter` vào lúc chạy và trả về một instance:

```java
TextAdapter adapter = /* một instance sinh động */;
String output = adapter.adapt("Java");
```

Hai dòng trên là **mã minh họa** vì chưa có cách tạo `adapter`. Ý tưởng là mã tiêu thụ adapter **không cần biết class implementation có tên gì**.

Điểm mạnh của hidden class ở đây:

1. **Hợp đồng bên ngoài ổn định:** caller biết `TextAdapter`, không cần biết class được sinh tên `Adapter123` hay `Adapter456`.
2. **Tránh tên implementation dùng làm API:** framework không cần công bố một tên nhị phân tra cứu được.
3. **Có thể tách vòng đời:** lớp trợ giúp tồn tại khi còn được tham chiếu; trường hợp hidden class không `STRONG` có thể được unload độc lập với class loader khi không còn reachable.
4. **Có đường gọi hiệu quả:** framework có thể dùng instance qua interface hoặc `MethodHandle` tới constructor/phương thức của lớp ẩn.
5. **Chọn quyền truy cập có kiểm soát:** nếu cần một lớp sinh động truy cập private member của cùng nest, framework có thể dùng tùy chọn `NESTMATE` với lookup đủ đặc quyền.

Không phải adapter nào cũng cần hidden class. Một adapter viết bằng lambda, method reference hoặc một class được định nghĩa sẵn có thể đơn giản hơn. Hidden class đặc biệt phù hợp khi **implementation phải được tạo từ bytecode trong thời gian chạy**.

## 4. Ví dụ Java 17+: tạo một adapter bằng hidden class

Ví dụ sau dùng **một file nguồn duy nhất** để dễ biên dịch. File chứa ba top-level type cùng package mặc định: lớp chạy thử `HiddenAdapterDemo`, interface `TextAdapter`, và lớp mẫu `AdapterTemplate`.

`javac` biên dịch `AdapterTemplate` thành file `AdapterTemplate.class`. Demo đọc chính file bytecode ấy làm nguồn cho `defineHiddenClass`. Trong một framework thực tế, bytecode thường được **tạo hoặc biến đổi động** bằng công cụ phát sinh class-file. Kỹ thuật đọc file `.class` ở đây chỉ giúp học API **không cần thư viện tạo bytecode bổ sung**.

Lưu toàn bộ nội dung thành `HiddenAdapterDemo.java` (UTF-8):

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Locale;

public class HiddenAdapterDemo {
    public static void main(String[] args) throws Throwable {
        byte[] bytecode;
        try (InputStream in = HiddenAdapterDemo.class
                .getResourceAsStream("AdapterTemplate.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing AdapterTemplate.class");
            }
            bytecode = in.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup = MethodHandles.lookup()
                .defineHiddenClass(
                        bytecode,
                        true,
                        MethodHandles.Lookup.ClassOption.NESTMATE);

        Class<?> impl = hiddenLookup.lookupClass();

        Object instance = hiddenLookup
                .findConstructor(impl, MethodType.methodType(void.class))
                .invoke();

        // Mã bên ngoài chỉ cần biết interface ổn định.
        TextAdapter adapter = (TextAdapter) instance;

        System.out.println("hidden=" + impl.isHidden());
        System.out.println("adapted=" + adapter.adapt("Java"));
        System.out.println("differentClass=" + (impl != AdapterTemplate.class));
        System.out.println("nestmate=" +
                (impl.getNestHost() == HiddenAdapterDemo.class));

        try {
            Class.forName(impl.getName());
            System.out.println("discoverable=true");
        } catch (ClassNotFoundException e) {
            System.out.println("discoverable=false");
        }
    }
}

interface TextAdapter {
    String adapt(String input);
}

class AdapterTemplate implements TextAdapter {
    public String adapt(String input) {
        return "[" + input.toUpperCase(Locale.ROOT) + "]";
    }
}
```

Biên dịch và chạy **trong thư mục chứa file nguồn**:

```bash
javac -encoding UTF-8 HiddenAdapterDemo.java
java HiddenAdapterDemo
```

**Đầu ra chính xác trên OpenJDK 17+** đối với code này:

```text
hidden=true
adapted=[JAVA]
differentClass=true
nestmate=true
discoverable=false
```

Ví dụ đã được biên dịch và chạy bằng JDK hiện đại. Cách diễn giải:

- `getResourceAsStream("AdapterTemplate.class")` đọc bytecode của class mẫu cùng package. Nếu file `.class` không có trong classpath, chương trình báo lỗi rõ ràng.
- `MethodHandles.lookup()` tạo một lookup có quyền của lớp gọi. `defineHiddenClass(bytecode, true, NESTMATE)` định nghĩa một **class ẩn mới**, khởi tạo nó và thêm nó như nestmate của lớp lookup.
- `hiddenLookup.lookupClass()` lấy `Class<?>` của lớp ẩn, không cần `Class.forName`.
- `findConstructor(...)` trả về một `MethodHandle` tới constructor. `.invoke()` tạo instance; ứng dụng cast qua interface `TextAdapter`.
- `differentClass=true` nghĩa là **lớp ẩn khác lớp mẫu mang tên `AdapterTemplate`**, dù cùng nguồn bytecode. `AdapterTemplate.class` là class bình thường do `javac` tạo và JVM tải theo cơ chế thông thường.
- `nestmate=true` cho thấy tùy chọn `NESTMATE` làm lớp ẩn thuộc nest có host là `HiddenAdapterDemo`. Đây là quan hệ JVM về quyền truy cập private, không phải việc lớp ẩn có thể tra cứu bằng tên.
- `discoverable=false` cho thấy `Class.forName(impl.getName())` không tìm lại được hidden class bằng chuỗi tên.

Tên do `impl.getName()` trả về có thể chứa hậu tố với dấu `/` và một định danh do JVM tạo. **Không đưa tên ấy vào cấu hình, API, cơ chế tìm class theo tên hay điều kiện kiểm thử dựa trên chuỗi chính xác.**

Lưu ý riêng về `MethodHandle.invoke()`: trong ví dụ constructor trả về một đối tượng có kiểu implementation chỉ biết ở runtime, nên dùng `invoke()` rồi ép kiểu qua interface. `invokeExact()` yêu cầu kiểu ở điểm gọi khớp chính xác chữ ký method handle, do đó không thể tùy tiện coi kiểu trả về hidden implementation như `TextAdapter` ngay ở điểm gọi.

## 5. Các bước framework sinh mã áp dụng hidden class

Một framework dùng bytecode động có thể tổ chức theo quy trình sau:

```text
Phân tích nhu cầu tại runtime
        |
        v
Xác định interface / hành vi đích
        |
        v
Sinh hoặc biến đổi bytecode class triển khai
        |
        v
Lấy MethodHandles.Lookup phù hợp package/module
        |
        v
Lookup.defineHiddenClass(bytes, initialize, options...)
        |
        v
Nhận Class<?> / MethodHandle / instance
        |
        v
Cache nếu cần, gọi qua interface hoặc MethodHandle
        |
        v
Giải phóng tham chiếu khi không còn cần lớp sinh động
```

Các ứng dụng phù hợp gồm:

- **Sinh trình xử lý biểu thức**: biên dịch một biểu thức đã phân tích/kiểm tra thành bytecode, sau đó gọi qua interface chung, không cần đặt tên cho mỗi lớp sinh.
- **Sinh adapter**: biến các ràng buộc phương thức thành implementation của một interface định sẵn.
- **Sinh callback hoặc lambda implementation**: tạo lớp trợ giúp gắn với một call site do runtime quản lý.
- **Sinh code hỗ trợ serialization/mapping**: khi một thư viện thực sự sinh bytecode runtime để tăng tốc biến đổi cấu trúc dữ liệu, hidden class có thể là lựa chọn nếu implementation không cần được tìm theo tên.
- **Sinh bộ thực thi nội bộ ngắn hạn**: một loại tác vụ có nhiều phiên bản bytecode và muốn lớp có khả năng unload khi ngừng dùng, không buộc phải tạo class loader mới cho từng phiên bản.

Đây là **các trường hợp sử dụng khả thi**, không phải khẳng định mọi framework cụ thể đều dùng hidden class cho chức năng ấy. Nhiều framework còn lựa chọn bytecode class có tên, reflection, method handle, generated source, AOT code hoặc Java dynamic proxy tùy API và mục tiêu triển khai.

Đặc biệt, **`java.lang.reflect.Proxy` không đồng nghĩa với hidden class**. Proxy API là một cơ chế tạo implementation cho interface; các proxy class có các quy tắc sinh, tên và khả năng truy cập riêng. Không dựa vào việc thấy một proxy được tạo lúc chạy để kết luận nó ẩn.

## 6. Hai tùy chọn quan trọng: NESTMATE và STRONG

`MethodHandles.Lookup.ClassOption` có hai giá trị dùng cho `defineHiddenClass`:

| Tùy chọn | Ý nghĩa | Khi nào cân nhắc |
| --- | --- | --- |
| `NESTMATE` | Thêm hidden class vào **nest** của lookup class để có quan hệ truy cập private giữa các nestmate theo quy tắc JVM | Code sinh cần làm việc với private member của cùng nest và lookup có đặc quyền phù hợp |
| `STRONG` | Tạo liên hệ mạnh giữa hidden class và defining loader, tương tự class thông thường | Lớp sinh cần tồn tại cùng vòng đời class loader, ví dụ implementation dài hạn do runtime giữ |

**Không cung cấp `STRONG`:** hidden class thường có khả năng được unload khi không còn reachable, **kể cả khi loader vẫn còn sống**. Nhưng GC và class unloading là không xác định thời điểm; còn tham chiếu đến instance, `Class<?>`, method handle hoặc cache có thể khiến JVM tiếp tục giữ nó.

**Có `STRONG`:** class chịu quan hệ vòng đời chặt hơn với loader. Nó không có nghĩa là “vĩnh viễn không thể unload”; loader vẫn có thể được thu hồi khi phù hợp. Nếu một framework cứ tạo vô hạn strong hidden classes trong loader sống lâu, nó vẫn có thể gây áp lực bộ nhớ metadata.

**`NESTMATE` không làm một class bất kỳ tự có quyền truy cập private**. Chỉ lookup đủ quyền, đúng package/module và quy tắc JVM mới được định nghĩa lớp ẩn theo cách này. Đừng cấp một privileged `Lookup` cho mã không tin cậy vì đó là đối tượng mang quyền truy cập.

Trong ví dụ chạy được, `NESTMATE` chủ yếu để minh họa nest host; phương thức `adapt` chỉ dùng interface công khai trong package demo, không cần quyền truy cập private đặc biệt.

## 7. Điều kiện và hạn chế khi dùng API

Khi gọi `Lookup.defineHiddenClass(...)`:

1. Cần **class-file bytes hợp lệ**; phương thức không tự biên dịch Java source text. Có thể lấy bytecode từ compiler hoặc bộ tạo class-file được hỗ trợ.
2. Lookup phải có **full privilege access** cần thiết. Không thể tùy tiện sử dụng `MethodHandles.publicLookup()` để định nghĩa class ẩn trong package khác.
3. Class định nghĩa từ bytecode phải thuộc **cùng runtime package** với lookup class. Package/module và quyền truy cập phải phù hợp.
4. Tham số `initialize` kiểm soát việc khởi tạo class lúc định nghĩa: `true` yêu cầu khởi tạo, `false` không yêu cầu khởi tạo ngay. Việc dùng class sau đó vẫn tuân theo quy tắc khởi tạo JVM.
5. Hidden class không có tên nhị phân có thể dùng cho symbolic reference từ class khác. Vì vậy không nên dùng nó làm một kiểu public API mà công cụ bên ngoài phải load bằng tên.
6. Mã tạo có thể dùng reflection hoặc method handles thông qua `Class<?>` mà `defineHiddenClass` trả lại, trong phạm vi quyền truy cập hợp lệ.
7. Class ẩn **không phải hệ thống sandbox**. Bytecode không tin cậy vẫn có thể thực hiện các hành động mà runtime cho phép, nên phải kiểm soát nguồn bytecode và quyền thực thi.

Java 16+ còn có `Lookup.defineHiddenClassWithClassData(...)`, hỗ trợ gắn **class data** để lớp ẩn sử dụng khi chạy (ví dụ đối tượng metadata, method handles). Đây là API còn áp dụng trong Java hiện đại, nhưng không cần cho ví dụ adapter cơ bản trên. Khi dùng, hãy tuân theo tài liệu về cách truy cập class data và quản lý các tham chiếu do nó giữ.

Nếu công cụ sinh bytecode phát sinh class-file không đúng định dạng hoặc bytecode chứa symbolic reference không phù hợp, việc định nghĩa có thể ném các lỗi xác minh/linkage tương ứng. Không giả định rằng `defineHiddenClass` tự sửa hoặc tự xác thực mọi logic cấp cao của mã được sinh.

## 8. Tích hợp với lambda và adapter có cần tự gọi defineHiddenClass?

**Thường là không.** Khi tác vụ chỉ là chuyển một hàm thành callback, lambda hoặc method reference là API Java đơn giản và dễ bảo trì hơn:

```java
import java.util.function.Function;
import java.util.Locale;

Function<String, String> normalized = s -> s.toUpperCase(Locale.ROOT);
System.out.println(normalized.apply("java")); // JAVA
```

Compiler/JVM quản lý cơ chế liên kết và implementation thay vì ứng dụng tự sinh class-file bytes. Đừng tự viết bộ tạo hidden class chỉ vì muốn tối ưu một biểu thức lambda bình thường.

Dùng `LambdaMetafactory` trực tiếp cũng là API cấp thấp dành cho tình huống cần xây dựng functional object từ method handle. Bên trong OpenJDK, nó có thể sử dụng strong hidden implementation classes. Tuy nhiên, **không nên gọi `LambdaMetafactory` chỉ để ép một kiểu lớp sinh cụ thể**: các chi tiết về lớp được sinh không thuộc hợp đồng ổn định mà mã nghiệp vụ nên phụ thuộc.

Khi framework cần **thay đổi cấu trúc của implementation ở runtime** (ví dụ tạo nhiều biến thể adapter hoặc biên dịch một biểu thức vào bytecode), làm việc trực tiếp với `Lookup.defineHiddenClass` có thể hợp lý. Quyết định này nên dựa trên nhu cầu thật, kiểm thử hiệu năng, profiling và yêu cầu về unload, thay vì mặc định rằng lớp ẩn luôn nhanh hơn class bình thường.

## 9. Khả năng quan sát và gỡ lỗi

Một hidden class có thể xuất hiện trong stack trace, profiler hoặc diagnostic tooling với **tên không phải tên nhị phân thông thường**. Theo tài liệu JVM, tên do `Class.getName()` trả về cho hidden class có thể chứa ký tự `/`. Do đó:

- Dùng `Class.isHidden()` để kiểm tra class ẩn, không dùng tìm kiếm chuỗi `$$Lambda` hoặc hậu tố tùy ý.
- Đừng giả định tên từ `Class.getName()` luôn dùng được cho `Class.forName(...)`.
- Không lưu tên lớp ẩn để tạo lại implementation sau khi restart. Nếu cần phục hồi, lưu **metadata nghiệp vụ** hoặc code/config có thể sinh lại bytecode.
- Khi cần quan sát hiệu năng, đo cả lượng class sinh, class unloading, loader/cache reachability và chi phí sinh bytecode, chứ không chỉ thời gian gọi phương thức.
- Đừng cố giữ mọi `Class<?>` hoặc `MethodHandle` sinh ra trong một cache vô hạn nếu mục tiêu là unload độc lập.

**Không nên dùng hidden class** nếu plugin system, serialization protocol hoặc service registry **bắt buộc khôi phục implementation bằng tên class**. Trong trường hợp đó, class có tên hoặc một API factory/registry do ứng dụng quản lý sẽ phù hợp hơn.

## 10. So sánh nhanh các cách tạo hành vi

| Cách tiếp cận | Có cần tự sinh bytecode? | Lợi ích/chú ý |
| --- | --- | --- |
| Lambda/method reference | Không | Rõ ràng, ngắn gọn; JVM chọn chiến lược triển khai |
| Class bình thường | Không | Phù hợp public API, có thể tham chiếu, tra cứu theo tên |
| `java.lang.reflect.Proxy` | Không trực tiếp | Proxy interface theo API riêng; **không mặc định là hidden class** |
| `MethodHandle` | Không | Gọi phương thức động mà không nhất thiết sinh class |
| `Lookup.defineClass(byte[])` | Có bytecode | Định nghĩa **class có tên** trong cùng package phù hợp |
| `Lookup.defineHiddenClass(byte[], ...)` | Có bytecode | Implementation nội bộ không tra cứu theo tên; có tùy chọn vòng đời và nestmate |
| `LambdaMetafactory` | Thông thường không tự sinh bytecode ở phía ứng dụng | Liên kết functional object từ method handle; hành vi lớp implementation do runtime quyết định |

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Hidden class chính là `private class` hoặc anonymous class | Hidden class là khái niệm JVM; xác định bằng `Class.isHidden()` |
| Hidden class không thể gọi phương thức hoặc reflection | Khi có `Class<?>`/lookup hợp lệ vẫn có thể tương tác |
| Tên từ `getName()` dùng được với `Class.forName` | Hidden class không có tên nhị phân để tra cứu theo cách ấy |
| Mọi lambda và mọi Java proxy đều bắt buộc là hidden class | Chi tiết sinh code phụ thuộc API/JVM/framework |
| Hidden class mặc định tồn tại suốt đời của class loader | Mặc định có thể unload độc lập; `STRONG` thay đổi quan hệ |
| Hidden class luôn unload ngay khi GC chạy | Chỉ có **khả năng** unload khi đủ điều kiện; GC không bảo đảm thời điểm |
| `NESTMATE` là quyền truy cập tự do tới bất kỳ class nào | Cần lookup đặc quyền và cùng quy tắc nest/package/module |
| Text block tự chuyển source thành bytecode hidden class | Text block chỉ tạo `String`; `defineHiddenClass` nhận **byte[] class-file** |
| Hidden class bảo vệ được bytecode không tin cậy | Không phải sandbox hay lớp cách ly bảo mật |
| Dùng class ẩn luôn nhanh hơn interface/lambda thường | Cần profiling; phát sinh bytecode, cache và unload đều có chi phí |

## 12. Tự kiểm tra

Xem ba tình huống sau:

1. Một ứng dụng Java cần callback để chuyển tên người dùng thành chữ hoa. Có cần tự tạo hidden class không?
2. Framework phát sinh 100.000 biến thể triển khai một interface ở runtime, nhưng mã bên ngoài chỉ cần gọi interface; framework muốn cho phép những implementation không còn dùng được unload độc lập với loader. Hidden class có phù hợp không, và nên cân nhắc tùy chọn nào?
3. Một plugin manager lưu tên implementation vào file cấu hình rồi dùng `Class.forName(...)` để khôi phục sau restart. Có nên lưu tên của hidden class không?
4. Cùng một bytecode `AdapterTemplate.class` được load theo tên thông thường và được truyền vào `defineHiddenClass`. Hai `Class<?>` ấy có nhất thiết là cùng một class không?

**Đáp án:**

1. Không cần; viết lambda hoặc method reference là lựa chọn đơn giản hơn.
2. Có thể phù hợp nếu bytecode được sinh đúng package và thiết kế cache/reachability rõ ràng. Không cung cấp `STRONG` nếu mục tiêu là cho lớp có cơ hội unload độc lập; vẫn phải giải phóng instance, `Class<?>`, method handle và tham chiếu cache để JVM có thể thu hồi.
3. Không. Hidden class không tra cứu được bằng tên. Hãy lưu định danh nghiệp vụ hoặc dữ liệu đủ để **sinh lại** implementation, hoặc chọn class có tên nếu API yêu cầu.
4. Không. `defineHiddenClass` định nghĩa một hidden class **mới**, có identity khác với named class từ cùng nguồn bytecode. Ví dụ độc lập ở mục 4 in `differentClass=true`.

## Tài liệu tham khảo hiện hành

- [OpenJDK — JEP 371: Hidden Classes](https://openjdk.org/jeps/371): mục tiêu thiết kế, động cơ phục vụ framework và JVM.
- [Oracle Java SE 26 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, quyền lookup, cách dùng và giới hạn.
- [Oracle Java SE 26 — Lookup.ClassOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
- [Oracle Java SE 26 — Class](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): `isHidden()`, tên hidden class và giới hạn tra cứu.
- [Oracle Java SE 26 — LambdaMetafactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): liên kết functional object, lambda runtime, lưu ý về implementation.