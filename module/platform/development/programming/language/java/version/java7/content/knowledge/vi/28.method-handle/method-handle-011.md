# Phân biệt sử dụng API được hỗ trợ với phụ thuộc API nội bộ trong MethodHandle

## 1. Vấn đề cần hiểu

Khi làm việc với `MethodHandle`, đôi lúc ta nhìn thấy tên lớp hay cấu trúc thực thi bên trong JDK và tưởng rằng có thể dùng chúng như một API bình thường. Đây là hai loại hợp đồng khác nhau:

- **API được hỗ trợ**: các lớp, phương thức, kiểu và quy tắc truy cập mà nền tảng Java công bố để ứng dụng sử dụng. Trong chủ đề này, trọng tâm là API công khai của `java.lang.invoke`, ví dụ `MethodHandle`, `MethodHandles`, `MethodHandles.Lookup` và `MethodType`.
- **Chi tiết triển khai nội bộ**: lớp con cụ thể của handle, trường private của JDK, cấu trúc phục vụ JVM/JIT và những package không được công bố thành API ứng dụng. Các chi tiết này có thể khác giữa JDK, phiên bản hoặc nhà cung cấp.

Sự phân biệt này vẫn rất quan trọng trên **Java 17+**, khi Java Platform Module System (JPMS) áp dụng cơ chế đóng gói mạnh đối với phần lớn JDK internals. Mục tiêu là sử dụng khả năng gọi động có kiểu của `MethodHandle` mà không tạo phụ thuộc mong manh vào cách JDK cài đặt nó.

**Nguyên tắc:** dựa vào hợp đồng công khai đã được tài liệu hóa của `MethodHandle`, không dựa vào class thực tế mà `handle.getClass()` tình cờ trả về.

## 2. Cách xác định một API có được hỗ trợ hay không

Đừng quyết định chỉ bằng tên package có chứa từ `java` hoặc vì code biên dịch được. Hãy kiểm tra nhiều yếu tố:

1. **Tài liệu chính thức:** loại và thành viên có được công bố trong Java SE/JDK API documentation cho phiên bản đích không? Với Java 17, xem `java.lang.invoke` trong module `java.base`.
2. **Quyền truy cập theo Java và JPMS:** class/method có public đúng nghĩa không; package có được module `exports` để sử dụng như API hay không?
3. **Hợp đồng được mô tả:** tài liệu cho phép dựa vào những gì — chữ ký, kiểu trả về, lỗi, kiểm tra quyền và ngữ nghĩa gọi. Đừng suy diễn từ mã nguồn private hoặc từ tên lớp thực thi.
4. **Tính khả chuyển:** một thành viên của implementation riêng hoặc package `jdk.internal.*`, dù có thể mở bằng JVM flags, không tự biến thành API được Java SE bảo đảm.
5. **Trạng thái phiên bản:** một API công khai vẫn có thể bị `@Deprecated`, `forRemoval` hoặc có hành vi đặc thù phiên bản. Hãy kiểm tra Javadoc hiện hành và đường thay thế nếu có; không sử dụng API chỉ vì nó từng xuất hiện ở bản Java cũ.

Với MethodHandle, các điểm tựa chắc chắn là:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
~~~

Đây là các lớp công khai trong API Java 17; việc import chúng thông thường không đòi hỏi `--add-exports` hay `--add-opens`.

**Lưu ý:** “được hỗ trợ” không có nghĩa là JVM phải dùng cùng một chiến lược tối ưu, cùng tên implementation class hoặc có cùng tốc độ trên mọi máy. Java SE quy định ngữ nghĩa API, còn JIT có quyền chọn cách thực hiện phù hợp.

## 3. Bảng phân biệt trong hệ sinh thái MethodHandle

| Thành phần hoặc cách làm | Đánh giá | Lý do |
| --- | --- | --- |
| `java.lang.invoke.MethodHandle`, `MethodType`, `MethodHandles` | **API công khai được hỗ trợ** | Có tài liệu Java SE, dùng trực tiếp để biểu diễn lời gọi có kiểu |
| `MethodHandles.lookup()`, `Lookup.findStatic/findVirtual/findConstructor` | **API công khai được hỗ trợ** | Kiểm tra thành viên, chữ ký và quyền truy cập lúc tạo handle |
| `handle.invokeExact(...)`, `invoke(...)`, `asType(...)`, `bindTo(...)` | **API công khai được hỗ trợ** | Hợp đồng gọi/biến đổi handle được quy định rõ |
| `MethodHandles.filterReturnValue` và các combinator công khai | **API công khai được hỗ trợ** | Ghép lời gọi động theo kiểu đầu vào/đầu ra |
| `java.lang.invoke.CallSite`, `ConstantCallSite`, `MutableCallSite`, `VolatileCallSite` | **API công khai được hỗ trợ** | Phục vụ call site và liên kết hành vi động theo hợp đồng riêng |
| `java.lang.invoke.VarHandle` | **API công khai được hỗ trợ** | Dành cho các access mode của biến, gồm chế độ đồng bộ/atomic khi phù hợp |
| Dùng `MethodHandles.privateLookupIn` với quyền truy cập hợp lệ vào class **do ứng dụng quản lý** | **Cách dùng API được hỗ trợ, có điều kiện** | Phải thỏa quyền `Lookup` và quy tắc `opens`/module; không tự mở quyền truy cập của JDK |
| Phân nhánh theo `handle.getClass().getName()` để suy ra cách gọi | **Phụ thuộc implementation** | Class cụ thể của handle không phải hợp đồng ổn định |
| Ép kiểu handle sang class con triển khai bên trong JDK | **Phụ thuộc API nội bộ** | `MethodHandle` không cho ứng dụng một bộ class con cố định để sử dụng |
| Truy cập các class `jdk.internal.*` hoặc private field của `java.lang.invoke` | **Không phải API Java SE cho ứng dụng** | Có thể bị đóng gói, đổi cấu trúc hoặc xóa mà không giữ tương thích |
| Dùng `sun.misc.Unsafe` để thay thế lời gọi/field access thông thường | **Không nên dùng làm API ứng dụng** | Ngoại lệ đóng gói không đồng nghĩa với hợp đồng Java SE ổn định; ưu tiên API chuẩn phù hợp |
| Đưa `--add-exports`/`--add-opens` vào cấu hình để gọi JDK internals | **Biện pháp tương thích tạm thời** | Flag chỉ thay đổi giới hạn truy cập, không bảo đảm API nội bộ ổn định |

Điểm tinh tế: tên `java.lang.invoke` là một **package công khai**, nhưng **không phải mọi thành viên hoặc class private bên trong package ấy đều là API ứng dụng**. Ngay cả `handle.getClass()` — lời gọi hợp lệ của `Object` — cũng có thể cho biết một tên implementation mà bạn **không được xây logic phụ thuộc vào đó**.

## 4. Sử dụng MethodHandle qua hợp đồng công khai

### 4.1. Tra cứu hành vi bằng `Lookup`

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle max = lookup.findStatic(
        Math.class, "max",
        MethodType.methodType(int.class, int.class, int.class));

int result = (int) max.invokeExact(3, 7);
System.out.println(result); // 7
~~~

Đây là **đoạn đặt trong method có `throws Throwable`**, không phải file Java độc lập. Điều được phép dựa vào:

- `Lookup.findStatic` tìm method theo **class, tên, `MethodType`** và quyền của lookup.
- `max.type()` trả `(int,int)int`; `invokeExact` đòi khớp chính xác **cả kiểu đối số và kiểu trả về tại call site**.
- Phương thức `Math.max(int,int)` được thực thi và trả về số lớn hơn.

Điều **không** được suy ra: handle phải có một tên class con cụ thể, Java phải triển khai bằng một chiến lược reflection nhất định hoặc một lần `invokeExact` luôn nhanh hơn lời gọi trực tiếp. Đó là việc của JVM.

### 4.2. Phân biệt chữ ký công khai với tổ chức nội bộ

`MethodType` là hợp đồng có thể quan sát:

~~~java
System.out.println(max.type()); // (int,int)int
~~~

Ngược lại, phần sau chỉ phù hợp cho chẩn đoán nhất thời, **không dùng làm quyết định nghiệp vụ**:

~~~java
// Không xây logic dựa vào tên class triển khai của handle.
String implementationClass = max.getClass().getName();
System.out.println(implementationClass);
~~~

Đoạn trên chỉ chạy khi đã có `max`; **không có stdout cố định** vì Java không cam kết class triển khai cụ thể của một method handle. Tránh viết:

~~~java
// Sai về thiết kế: tên implementation có thể đổi tùy JDK.
if (max.getClass().getName().contains("SomeInternalHandle")) {
    // Chọn một luồng xử lý chỉ vì tên class nội bộ.
}
~~~

Thay vào đó, xác định hành vi và kiểu cần dùng bằng `max.type()`, `MethodType`, contract của target và dữ liệu cấu hình đã kiểm tra. Nếu cần metadata về thành viên gốc và được phép truy cập, xem `Lookup.revealDirect(handle)`/`MethodHandleInfo` với giới hạn quyền và loại handle phù hợp; không phải mọi handle đã biến đổi đều là direct handle có thể “giải mã” như vậy.

### 4.3. Dùng API public để biến đổi handle

~~~java
// Gốc: (int,int)int.
MethodHandle atLeastTen =
        MethodHandles.insertArguments(max, 0, 10);

// Mới: (int)int.
int value = (int) atLeastTen.invokeExact(4);
System.out.println(value); // 10
~~~

Đây là fragment sử dụng biến `max` đã tạo. `insertArguments` là API công khai, tạo handle mới với một đối số đã cố định. Không cần sửa đổi field private hoặc cấu trúc nội bộ của `max` để đạt mục đích.

Một số phương án công khai khác:

- `asType`: thích nghi chữ ký khi các chuyển đổi kiểu theo hợp đồng được hỗ trợ.
- `bindTo`: cố định tham số tham chiếu đầu tiên (thường là receiver của instance method).
- `filterArguments`/`filterReturnValue`: ghép các bước xử lý có kiểu.
- `permuteArguments`/`dropArguments`: sắp xếp hoặc bỏ qua đối số theo hợp đồng đã định.

Các adapter phải tôn trọng `MethodType`; việc sử dụng API công khai không tự bảo đảm mọi chuyển kiểu sẽ thành công.

## 5. Quyền truy cập hợp lệ khác với truy cập nội bộ JDK

Một nhầm lẫn phổ biến: “Nếu có thể lấy handle tới private method thì đó là API nội bộ”. Thực ra cần tách rõ **API dùng để lấy handle** và **thành viên đích**.

**Trường hợp hợp lệ:** một class trong ứng dụng dùng `MethodHandles.lookup()` để tạo handle tới private method của **chính class đó**, theo quyền vốn có của Java. Bộ máy `Lookup` hỗ trợ việc này.

~~~java
public class SelfLookup {
    private static String greet() {
        return "Xin chao";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findStatic(
                SelfLookup.class, "greet",
                MethodType.methodType(String.class));
        System.out.println((String) handle.invokeExact());
    }
}
~~~

Đoạn trên là **minh họa cấu trúc class**, cần thêm các `import java.lang.invoke.*` khi biên dịch trong file riêng; kết quả in `Xin chao`. Class có quyền truy cập member private của chính mình. Đây là việc dùng **API public** để gọi **member private của ứng dụng**, hoàn toàn khác với ép truy cập các private field phục vụ implementation của JDK.

**Trường hợp cần cảnh giác:** code cố lấy một `Lookup` đặc quyền không được công khai, sử dụng reflection để mở field private của `MethodHandles.Lookup` hoặc tra cứu class `jdk.internal.*` nhằm bỏ qua cơ chế access check. Tình trạng “chạy được trên một JDK” không chứng minh hành vi có hợp đồng tương thích.

### Quy tắc module trong Java 17+

- `exports` một package của module giúp code bên ngoài truy cập **public types/public members** theo phạm vi export và quyền đọc module.
- `opens` một package cho phép **deep reflection tại runtime** theo phạm vi được mở. Nó không biến mọi thành viên private thành API mà tác giả module hứa duy trì.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)` là API công khai có kiểm tra quyền: caller lookup phải có chế độ phù hợp, và khi qua module khác, module gọi phải đọc module đích và package đích cần được mở cho module gọi.
- `MethodHandles.publicLookup()` không có quyền private; phù hợp để tìm các public member trong các public class được công bố truy cập công khai.

Nếu bạn là **chủ sở hữu module ứng dụng**, việc thiết kế package nào `exports` hoặc `opens` cho framework là một quyết định về API và quyền truy cập. Nếu module là **nội bộ của JDK**, việc buộc nó mở bằng flag không làm thành viên nội bộ trở thành API được bảo đảm. Một handle đã được tạo hợp lệ cũng là một *capability*: người giữ có thể gọi member tương ứng, nên không chuyển handle nhạy cảm cho code thiếu tin cậy.

## 6. Chương trình Java 17+ dùng hoàn toàn API được hỗ trợ

Ví dụ dưới đây chỉ import `java.lang.invoke`, không dựa vào lớp con triển khai hoặc reflection mở private field JDK. Chương trình minh họa static/virtual/constructor, binding receiver và khác biệt quyền truy cập giữa `lookup()` với `publicLookup()`.

Tạo file **`SupportedInvokeApiDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class SupportedInvokeApiDemo {
    public static String decorate(String value) {
        return "[" + value + "]";
    }

    public static final class Greeter {
        private final String prefix;

        public Greeter(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + ", " + name;
        }
    }

    private static String hidden(String name) {
        return "private: " + name;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Public API: static handle có kiểu (String)String.
        MethodHandle decorate = lookup.findStatic(
                SupportedInvokeApiDemo.class, "decorate",
                MethodType.methodType(String.class, String.class));
        System.out.println(
                "static: " + (String) decorate.invokeExact("ok"));

        // Tra cứu constructor bằng (String)void;
        // handle thực tế trả Greeter.
        MethodHandle ctor = lookup.findConstructor(
                Greeter.class,
                MethodType.methodType(void.class, String.class));
        Greeter greeter = (Greeter) ctor.invokeExact("Xin chao");

        // Method instance: receiver Greeter là tham số đầu.
        MethodHandle greet = lookup.findVirtual(
                Greeter.class, "greet",
                MethodType.methodType(String.class, String.class));
        System.out.println("virtual type: " + greet.type());
        System.out.println(
                "virtual: " + (String) greet.invokeExact(greeter, "Lan"));

        // Adapter public: cố định receiver, còn (String)String.
        MethodHandle bound = greet.bindTo(greeter);
        System.out.println(
                "bound: " + (String) bound.invokeExact("Minh"));

        // lookup() trong chính class có quyền đọc private method của class.
        MethodHandle ownPrivate = lookup.findStatic(
                SupportedInvokeApiDemo.class, "hidden",
                MethodType.methodType(String.class, String.class));
        System.out.println(
                "own private: " + (String) ownPrivate.invokeExact("An"));

        // publicLookup() có quyền hạn hẹp và không lấy private method.
        try {
            MethodHandles.publicLookup().findStatic(
                    SupportedInvokeApiDemo.class, "hidden",
                    MethodType.methodType(String.class, String.class));
            System.out.println("unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("public lookup private: denied");
        }

        // Kiểu public được hỗ trợ; không dựa vào decorate.getClass().
        System.out.println("API type: " + decorate.type());
    }
}
~~~

Dùng **JDK 17+** để biên dịch; cờ `--release 17` buộc mã nguồn/bytecode theo Java 17 và giới hạn API tới những API được công bố ở mức release tương ứng:

~~~bash
javac --release 17 SupportedInvokeApiDemo.java
java SupportedInvokeApiDemo
~~~

`stdout`:

~~~text
static: [ok]
virtual type: (Greeter,String)String
virtual: Xin chao, Lan
bound: Xin chao, Minh
own private: private: An
public lookup private: denied
API type: (String)String
~~~

Vì sao output này đáng tin:

1. `findStatic` tìm đúng `decorate(String)`, sau đó `invokeExact` nhận và trả `String`.
2. `findConstructor` tìm kiểu `(String)void` nhưng tạo handle trả `Greeter`.
3. `findVirtual` bổ sung receiver `Greeter` vào chữ ký; `bindTo` cố định receiver nên còn `(String)String`.
4. `lookup()` được tạo trong `SupportedInvokeApiDemo` và có quyền truy cập private method `hidden` của chính class đó.
5. `publicLookup()` không được phép lấy `hidden`, nên nhánh `catch (IllegalAccessException)` được chạy.
6. `decorate.type()` phản ánh `MethodType` ổn định của handle; không cần inspect implementation class.

Nếu đổi code để phụ thuộc vào tên `decorate.getClass().getName()`, chương trình sẽ đánh mất tính khả chuyển dù phần gọi `invokeExact` vẫn hợp lệ. Ví dụ này có thể chạy trực tiếp bằng Java, không cần thêm thư viện hoặc mở module JDK.

## 7. Vì sao phụ thuộc API nội bộ dễ gây lỗi

### 7.1. Class triển khai không thuộc hợp đồng của `MethodHandle`

Javadoc công khai cho phép JVM tạo các subclass nội bộ của `MethodHandle`. Chúng có thể quan sát được qua `Object.getClass()` trong một số tình huống, nhưng **không được dựa vào cấu trúc phân lớp cụ thể**. JVM có thể chọn một cách triển khai khác giữa hai bản JDK hoặc hai nhà cung cấp mà vẫn giữ nguyên hành vi của API.

Ví dụ rủi ro:

~~~java
// Anti-pattern: điều khiển logic theo tên implementation class.
String name = handle.getClass().getName();
boolean hasPreferredInternalShape = name.contains("Internal");
// Không nên dùng kết quả này làm điều kiện gọi, cache hoặc phân quyền.
~~~

Đây là đoạn **phản ví dụ** trong scope đã có biến `handle`, không phải chương trình độc lập; không có quy tắc nào bảo đảm chuỗi `Internal` xuất hiện hoặc có ý nghĩa. Nếu cần biết handle có kiểu gì, dùng `handle.type()`. Nếu cần hiểu hành vi nghiệp vụ, lưu metadata **do ứng dụng sở hữu** bên cạnh handle.

### 7.2. Truy cập nội bộ thông qua reflection không ổn định

Dùng `setAccessible(true)`, truy cập private member trong `java.lang.invoke` hoặc tìm class `jdk.internal.*` có thể chạm ranh giới JPMS. Từ Java 17, phần lớn nội bộ JDK bị đóng gói mạnh theo **JEP 403**. Kể cả khi JVM được cấu hình để cho phép truy cập, mã vẫn phụ thuộc vào chi tiết có thể thay đổi.

Cần phân biệt các tùy chọn:

| Tùy chọn | Vai trò thực tế | Điều không được suy ra |
| --- | --- | --- |
| `--add-exports` | Bổ sung quyền truy cập các public types/members trong một package module nhất định | Không bảo đảm package đó là Java SE API ổn định |
| `--add-opens` | Mở package cho reflective/deep access ở runtime | Không cấp hợp đồng giữ nguyên private field/method |
| `--illegal-access` trên JDK 17 | Tùy chọn cũ đã mất hiệu lực thực chất | Không còn là giải pháp bật truy cập nội bộ tổng quát |

Các cờ này có thể cần để duy trì một dependency bên thứ ba cũ trong giai đoạn chuyển đổi. Cần xem chúng là **tín hiệu kỹ thuật phải được xử lý**, kiểm tra tác động và đặt kế hoạch nâng cấp, không xem là giải pháp lâu dài cho code MethodHandle mới.

### 7.3. Thấy một tên trong JDK không có nghĩa là được phép phụ thuộc

`jdeps` có thể chỉ ra sử dụng JDK internals; một import `jdk.internal.*` hoặc `sun.*` đáng được kiểm tra. Tuy nhiên, xét mức độ hỗ trợ phải dựa vào tài liệu và loại API cụ thể — có những API thuộc JDK khác Java SE API, và có những ngoại lệ đóng gói phục vụ tương thích. Việc còn truy cập được **không** tự xác nhận một hợp đồng ổn định.

Ví dụ `sun.misc.Unsafe` còn có mặt trong một số JDK để tương thích nhưng không phải thay thế nên dùng cho `MethodHandle`, `VarHandle` hoặc API chuẩn khác. Nếu yêu cầu là truy cập biến nguyên tử, `VarHandle` là một hướng công khai cần xem xét theo access mode và memory-ordering semantics; nếu yêu cầu là gọi method động, dùng `MethodHandles.Lookup` và `MethodHandle`.

## 8. Phát hiện phụ thuộc nội bộ trong dự án

Có thể kiểm tra từ source, cấu hình build và artifact đã biên dịch.

### Bước 1: tìm dấu hiệu trong source/build

Trong IDE hoặc công cụ tìm kiếm mã, tra cứu:

~~~text
jdk.internal.
sun.misc.
sun.reflect.
getDeclaredField(
setAccessible(
--add-exports
--add-opens
--illegal-access
getClass().getName()
~~~

Danh sách là **gợi ý tìm kiếm**, không phải kết luận tự động: một lời gọi `getDeclaredField` để kiểm tra class **do ứng dụng quản lý** có thể hoàn toàn hợp lệ. Hãy kiểm tra mục tiêu thực sự và ranh giới module. Đặc biệt quan sát code tìm private field bên trong `java.lang.invoke` hoặc diễn giải tên class của `MethodHandle`.

### Bước 2: dùng `jdeps` trên artifact

Với ứng dụng đã biên dịch, công cụ `jdeps` của JDK có lựa chọn phân tích phụ thuộc vào API nội bộ:

~~~bash
jdeps -jdkinternals path/to/app.jar
~~~

Có thể kiểm tra bytecode class đã biên dịch:

~~~bash
jdeps -jdkinternals SupportedInvokeApiDemo.class
~~~

Khi phụ thuộc nội bộ được phát hiện, `jdeps` thường nêu class gây phụ thuộc và gợi ý thay thế nếu có. **Không mong đợi một đoạn stdout cố định** vì kết quả tùy artifact và phiên bản JDK. Với ví dụ chỉ dùng `java.lang.invoke` công khai ở trên, không có lý do xuất hiện báo cáo dùng JDK internals.

Giới hạn cần biết: `jdeps` chủ yếu là **phân tích tĩnh**. Những tên class được xây trong chuỗi rồi gọi qua reflection, một phần code chỉ nạp động hoặc một dependency không có trong artifact đang quét có thể không bị phát hiện. Vì vậy, phải kết hợp kiểm tra source, dependency tree và chạy thử trên các JDK mục tiêu.

### Bước 3: tái kiểm tra với JDK mục tiêu

- Biên dịch với `javac --release 17` nếu baseline là Java 17 và code không cần API mới hơn.
- Chạy test chức năng trên môi trường Java mà ứng dụng sẽ triển khai. Kiểm tra cả nhánh success lẫn `IllegalAccessException`, `NoSuchMethodException` và `WrongMethodTypeException` theo hợp đồng.
- Thử trên JDK/vendor dự kiến hỗ trợ; không mặc định việc chạy được trên một bản JDK chứng minh khả chuyển.
- Theo dõi các cờ mở module, warning/exception do encapsulation và các import nội bộ xuất hiện trong thư viện phụ thuộc.

**Không xóa bừa cờ JVM khi ứng dụng chưa kiểm chứng**, vì một thư viện cũ có thể đang phụ thuộc vào nó. Thứ tự đúng là xác định nguồn phụ thuộc, nâng cấp/thay API, thử lại rồi mới bỏ cấu hình tạm thời.

## 9. Chuyển từ phụ thuộc nội bộ sang API được hỗ trợ

| Nhu cầu ban đầu | Cách phụ thuộc dễ gặp | Hướng thiết kế phù hợp hơn |
| --- | --- | --- |
| Tìm và gọi method động | Tìm class/field private bên trong `java.lang.invoke` | `MethodHandles.lookup()/publicLookup()`, `findStatic`, `findVirtual` và `invokeExact/invoke` |
| Tạo object theo constructor tại runtime | Gọi constructor nội bộ qua cơ chế không có hợp đồng | `Lookup.findConstructor` cùng `MethodType` chính xác |
| Chuyển đổi/ghép lời gọi | Sửa cấu trúc nội bộ của handle để gắn tham số | `bindTo`, `insertArguments`, `asType`, `filterArguments` hoặc `filterReturnValue` |
| Đọc/ghi trạng thái biến có yêu cầu memory ordering | Tự dùng API bộ nhớ nội bộ JDK | Xem xét `VarHandle` và access mode phù hợp, hoặc `java.util.concurrent.atomic` |
| Muốn giữ metadata của một hành vi động | Đọc tên class nội bộ hoặc private field của handle | Lưu cấu trúc metadata do ứng dụng tự định nghĩa và kiểm tra `MethodType` |
| Framework cần truy cập private member của model ứng dụng | Dùng `setAccessible` với JDK internals hoặc mở cả hệ thống | Thiết kế package/module `opens` có mục tiêu và dùng `privateLookupIn` có quyền hợp lệ khi thực sự cần |
| Cần điều phối nhiều lời gọi cố định | Phân nhánh theo hình dạng implementation class | Đặt `MethodHandle` trong cấu trúc ánh xạ rõ ràng, ví dụ tên nghiệp vụ → handle được phép |

**Cẩn thận với việc thay thế tự động:** `VarHandle` không phải API gọi method, và `MethodHandle` không tự cung cấp đầy đủ atomic access semantics như `VarHandle`. Mỗi API cần phù hợp hành vi và yêu cầu đồng bộ tương ứng.

## 10. Các tình huống dễ hiểu nhầm

**Tình huống A — “Tôi có thể gọi `getClass()` nên có thể phụ thuộc tên class đó.”**

`getClass()` là public API của `Object`, nhưng suy ra hành vi của handle từ **concrete implementation class** là phụ thuộc implementation. API cần dùng là `handle.type()` và hợp đồng lời gọi/adapter.

**Tình huống B — “`privateLookupIn` tồn tại, vậy mọi private method JDK đều được truy cập.”**

Sai. `privateLookupIn` có điều kiện kiểm tra quyền, module readability và `opens`. Ngay cả khi package được mở, private member của JDK không tự trở thành API được hỗ trợ. Hãy dùng nó cho model/framework có quyền hợp lệ, với phạm vi truy cập cụ thể.

**Tình huống C — “Lỗi `IllegalAccessException` có thể sửa bằng cách thêm cờ JVM.”**

Cờ mở module đôi khi là biện pháp chuyển tiếp cho phần mềm cần tương thích, nhưng cần điều tra nguyên nhân: class không export, member private, `Lookup` sai ngữ cảnh hay đang dùng API nội bộ? Cách sửa dài hạn thường là dùng public API hoặc thay thư viện.

**Tình huống D — “API public thì mọi call site sẽ chạy đúng.”**

`MethodHandle.invokeExact` đòi kiểu chính xác: `(int,int)int` khác `(int,int)Object`. Sai chữ ký có thể ném `WrongMethodTypeException` dù handle được tạo bằng API hoàn toàn được hỗ trợ.

**Tình huống E — “`jdeps` không báo gì, chắc chắn dự án sạch.”**

`jdeps -jdkinternals` phân tích bytecode nên có thể không thấy truy cập nội bộ qua reflection động, plugin chỉ nạp khi chạy hoặc dependency không có trong phạm vi phân tích. Cần bổ sung code review và integration test.

## 11. Checklist trước khi đưa MethodHandle vào code sản xuất

1. Chỉ dùng các lớp/phương thức `java.lang.invoke` đã được tài liệu Java SE/JDK tương ứng công bố.
2. Xác định `MethodType`, loại method và lỗi truy cập trước khi cache hoặc gọi handle.
3. Không dựa vào `handle.getClass()`, private field hoặc subclass của JDK để ra quyết định.
4. Kiểm tra `Lookup` có quyền phù hợp; không trao handle/lookup nhạy cảm cho mã không tin cậy.
5. Phân biệt quyền truy cập member **của ứng dụng** với quyền truy cập vào implementation **của JDK**.
6. Với JPMS, xem `exports`/`opens` và quan hệ module đúng mục tiêu; tránh mở package JDK chỉ để code mới chạy được.
7. Rà soát `jdk.internal.*`, `sun.*` và các cờ `--add-exports`/`--add-opens` bằng công cụ tìm kiếm, `jdeps` và test.
8. Nếu phát hiện phụ thuộc nội bộ, xác định nhu cầu chức năng thực sự rồi chuyển sang API công khai phù hợp trước khi bỏ cờ tương thích.
9. Kiểm thử với phiên bản JDK/vender triển khai và xử lý exception đúng ranh giới ứng dụng.
10. Khi không cần runtime dispatch, lời gọi Java trực tiếp, lambda hoặc method reference thường dễ đọc và bảo trì hơn.

**Ghi nhớ:** `MethodHandle` là **API công khai chứa tham chiếu hành vi có kiểu**. Cách JVM lưu trữ, đặt tên và tối ưu handle là **chi tiết triển khai**. Tránh phụ thuộc nội bộ; hãy khai thác `Lookup`, `MethodType`, `invokeExact` và combinator theo tài liệu chính thức.

## Tài liệu tham khảo hiện hành

- [Java SE 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): hợp đồng typed handle, `type()`, `invokeExact` và tính không ổn định của subclass triển khai.
- [Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()`, `privateLookupIn()` và các combinator.
- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quyền truy cập, factory methods và cross-module lookup.
- [OpenJDK — JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): nền tảng strong encapsulation trên JDK 17.
- [Oracle JDK 17 — Preparing for Migration](https://docs.oracle.com/en/java/javase/17/migrate/preparing-migration.html): `jdeps -jdkinternals` và phương án thay thế JDK internals.
- [Dev.java — Strong Encapsulation](https://dev.java/learn/modules/strong-encapsulation/): ranh giới `exports`/`opens` và tác động JPMS.
