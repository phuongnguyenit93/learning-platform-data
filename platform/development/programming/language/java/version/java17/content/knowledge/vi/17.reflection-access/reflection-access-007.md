# Hidden class cho mã sinh động bằng `Lookup.defineHiddenClass` trong Java 17

## 1. Hidden class giải quyết vấn đề gì?

Framework, compiler hoặc runtime đôi khi cần **sinh bytecode trong lúc chương trình chạy**, sau đó định nghĩa class để thực thi. Ví dụ:

- Framework ORM sinh lớp adapter hoặc accessor để đọc/ghi thuộc tính.
- Thư viện serialization sinh mã chuyển object thành byte.
- Runtime của ngôn ngữ động sinh lớp triển khai một đoạn mã đã biên dịch.
- Framework proxy tạo implementation để kết nối một interface với logic tại runtime.

Nếu mỗi lớp được sinh ra đều là một class thông thường có tên, class loader có thể phải quản lý rất nhiều class. Những lớp này thường chỉ là chi tiết triển khai, không cần được tìm kiếm bằng tên nhị phân từ bên ngoài.

Java 15 giới thiệu **hidden class** qua JEP 371. Java 17 có API ổn định `MethodHandles.Lookup.defineHiddenClass` để định nghĩa loại class này từ class file bytes. Hidden class:

- Không được khám phá bằng cơ chế tải class thông thường theo tên như `Class.forName` hoặc `ClassLoader.loadClass`.
- Có thể được sử dụng thông qua `Class` object, `MethodHandles.Lookup` và method handle được cấp.
- Có thể là chi tiết triển khai được tạo và loại bỏ độc lập với vòng đời của class loader, tùy tùy chọn định nghĩa.
- Có thể trở thành nestmate để truy cập private member của nest host khi dùng `NESTMATE`.

Điểm cốt lõi: hidden class phù hợp với mã được sinh động và **không cần trở thành một kiểu có tên công khai trong hệ thống class loading**. Nó không phải cách thay thế mọi class thông thường, cũng không phải một cơ chế bảo mật để chạy bytecode không đáng tin cậy.

## 2. Hidden class khác class thông thường thế nào?

### 2.1. Class thông thường được tải theo tên

Một class thông thường có binary name, chẳng hạn `com.example.GeneratedTask`. Class loader có thể tìm class theo tên nếu class đó được định nghĩa và có thể truy cập:

~~~java
Class<?> type = Class.forName("com.example.GeneratedTask");
~~~

Các class thông thường phù hợp với kiểu dữ liệu công khai, API thư viện, lớp được tham chiếu trong bytecode khác, cấu hình framework hoặc những loại cần tải bằng tên.

### 2.2. Hidden class không được khám phá bằng tên

Hidden class được định nghĩa từ bytecode nhưng JVM gắn cho nó trạng thái hidden. Các cơ chế tải class thông thường không thể tìm nó bằng binary name như một class bình thường.

Có thể kiểm tra:

~~~java
Class<?> hiddenType = lookup.lookupClass();
System.out.println(hiddenType.isHidden()); // true
~~~

`Class.isHidden()` có từ Java 15. `Class.getName()` vẫn cung cấp tên phục vụ chẩn đoán, nhưng tên đó có thể chứa hậu tố đặc biệt do JVM tạo. Không lưu hoặc dùng chuỗi này như một tên class ổn định để gọi `Class.forName`.

Hidden class vẫn có `Class` object. Ứng dụng có thể dùng object đó để tạo instance, tra cứu constructor/method hoặc kiểm tra thông tin reflection theo quyền truy cập được cấp. “Hidden” nghĩa là không được khám phá theo cơ chế tên thông thường, không có nghĩa là không thể sử dụng.

### 2.3. So sánh với defineClass

`MethodHandles.Lookup` còn có phương thức `defineClass(byte[])` để định nghĩa class thông thường trong cùng package/runtime context của lookup:

| Tiêu chí | `Lookup.defineClass` | `Lookup.defineHiddenClass` |
|---|---|---|
| Loại class | Class thông thường | Hidden class |
| Khám phá bằng tên | Có thể được tải theo tên qua class loader | Không được tải bằng cơ chế tên thông thường |
| Tên binary ổn định để tham chiếu | Có | Không nên dựa vào tên được JVM gắn |
| Mục đích | Định nghĩa class có danh tính tên bình thường | Định nghĩa implementation class sinh động, không cần tên công khai |
| Khả năng unload độc lập | Theo vòng đời class loader thông thường | Có thể unload độc lập nếu không dùng tùy chọn `STRONG` và không còn tham chiếu giữ class sống |
| Nestmate | Theo quan hệ nest trong class file | Có thể yêu cầu bằng `NESTMATE` |

Nếu class được sinh ra cần được các class file khác tham chiếu bằng tên, hoặc cần đăng ký như một kiểu thông thường, hãy cân nhắc `defineClass` hoặc một class loader phù hợp thay vì hidden class.

## 3. API Lookup.defineHiddenClass trong Java 17

Phương thức chính có dạng:

~~~java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException;
~~~

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `bytes` | Mảng byte chứa class file hợp lệ của class cần định nghĩa |
| `initialize` | Có yêu cầu khởi tạo class ngay khi định nghĩa hay không |
| `options` | Các tùy chọn như `NESTMATE` và `STRONG` |

Kết quả trả về là một `Lookup` mới có lookup class là hidden class vừa định nghĩa. Đây là điểm quan trọng: thay vì cố tải class bằng tên, caller dùng lookup trả về để tìm constructor, method hoặc field handle của chính hidden class đó.

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classFileBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE);

Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

### 3.1. Bytecode phải thuộc cùng package với lookup class

Hidden class được định nghĩa trong cùng runtime package, class loader, module và protection domain với lookup class. Class file bytes phải mô tả một class thuộc **cùng package** với lookup class.

Ví dụ, nếu lookup class là `com.example.RuntimeCompiler`, class file cần có package `com.example`. Không thể dùng lookup đó để tùy ý định nghĩa hidden class trong `java.lang` hoặc một package khác.

Ràng buộc này giúp hidden class có môi trường truy cập và module context phù hợp với lookup. Nó cũng có nghĩa class loader được chọn gián tiếp thông qua lookup; `defineHiddenClass` không nhận một class loader tùy ý như tham số.

### 3.2. Lookup phải có full privilege access

`defineHiddenClass` yêu cầu lookup có **full privilege access**. Thông thường, code gọi API lấy lookup từ `MethodHandles.lookup()` bên trong class thuộc package đích:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

Lookup này đại diện cho quyền của class gọi. Một `publicLookup()` hoặc lookup đã bị giảm quyền không đủ để định nghĩa hidden class.

Nếu framework muốn định nghĩa class trong package của một thành phần khác, nó cần một lookup phù hợp được cung cấp theo thiết kế có chủ đích. Không nên giả định rằng mọi lời gọi `privateLookupIn` đều tạo ra full-privilege lookup, đặc biệt khi đi qua ranh giới module. Hãy kiểm tra quyền của lookup và điều kiện module trước khi gọi.

### 3.3. Class file bytes phải hợp lệ

Mảng `bytes` phải chứa class file hợp lệ, có version tương thích với runtime Java 17 và package đúng. Trong ứng dụng thực tế, bytecode thường được tạo bởi:

- ASM.
- Byte Buddy.
- Một compiler hoặc code generator của framework.
- Một compiler/runtime riêng của ứng dụng.

`defineHiddenClass` không tự sinh bytecode từ mã nguồn Java. Nó nhận class file bytes đã được tạo trước đó rồi định nghĩa class trong JVM.

## 4. Tạo hidden class và lấy instance bằng MethodHandles

Ví dụ dưới đây dùng một class file template đã biên dịch để minh họa bước định nghĩa tại runtime. Trong framework thực tế, phần đọc template có thể được thay bằng byte array do bytecode generator tạo ra; lời gọi `defineHiddenClass` vẫn giống nhau.

Tạo file `demo/HiddenClassDemo.java`:

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassDemo {
    public interface Task {
        String execute();
    }

    public static void main(String[] args) throws Throwable {
        byte[] classBytes;

        try (InputStream input =
                     HiddenClassDemo.class.getResourceAsStream("GeneratedTask.class")) {
            if (input == null) {
                throw new IOException("GeneratedTask.class not found");
            }
            classBytes = input.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(
                        classBytes,
                        true,
                        MethodHandles.Lookup.ClassOption.NESTMATE);

        Class<?> hiddenType = hiddenLookup.lookupClass();
        System.out.println(hiddenType.isHidden()); // true

        MethodHandle constructor = hiddenLookup.findConstructor(
                hiddenType,
                MethodType.methodType(void.class));

        Task task = (Task) constructor.invoke();
        System.out.println(task.execute());
    }
}

final class GeneratedTask implements HiddenClassDemo.Task {
    public GeneratedTask() {
    }

    @Override
    public String execute() {
        return "Hello from a hidden implementation";
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -d out demo/HiddenClassDemo.java
java -cp out demo.HiddenClassDemo
~~~

Kết quả:

~~~text
true
Hello from a hidden implementation
~~~

Phân tích:

1. Compiler tạo file `demo/GeneratedTask.class` cùng package với `HiddenClassDemo`.
2. Chương trình đọc bytecode đó thành `byte[]`. Trong một framework, bước này thường là kết quả của code generator.
3. `MethodHandles.lookup()` lấy lookup có quyền của `HiddenClassDemo`.
4. `defineHiddenClass` định nghĩa một hidden class trong cùng package/runtime context.
5. `hiddenLookup.lookupClass()` lấy `Class` object của hidden class.
6. `findConstructor` tìm constructor thông qua lookup vừa nhận.
7. Instance được sử dụng qua interface `Task`, vì vậy phần còn lại của ứng dụng không cần phụ thuộc vào tên implementation.

Class `GeneratedTask` ở đây là template để ví dụ có thể biên dịch chỉ với JDK. Trong trường hợp sinh bytecode thực sự, framework tạo byte array thay cho việc đọc file class template.

## 5. Tùy chọn initialize

Tham số thứ hai của `defineHiddenClass` quyết định thời điểm chạy class initialization (`<clinit>`):

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(classBytes, true);
~~~

- `true`: yêu cầu khởi tạo class trong quá trình định nghĩa trước khi phương thức trả về.
- `false`: trì hoãn khởi tạo cho tới khi có hành động chủ động đầu tiên cần khởi tạo class theo quy tắc JVM.

Khởi tạo class có thể thực thi static initializer, gán static field và phát sinh lỗi. Nếu static initializer ném exception, quá trình khởi tạo có thể thất bại và JVM báo `ExceptionInInitializerError` hoặc lỗi khởi tạo tương ứng.

Chọn `true` khi framework muốn phát hiện lỗi khởi tạo ngay ở bước define. Chọn `false` khi muốn trì hoãn chi phí khởi tạo tới lúc class thật sự được sử dụng. Dù chọn cách nào, không nên đặt side effect quan trọng vào static initializer nếu framework không kiểm soát được thời điểm kích hoạt.

## 6. ClassOption.NESTMATE

### 6.1. Nest-based access control

Java có cơ chế nest để các class thuộc cùng một nest có thể truy cập private member của nhau theo quy tắc ngôn ngữ và JVM. Ví dụ class ngoài và nested class có thể cùng một nest host.

Khi truyền `ClassOption.NESTMATE`, hidden class được định nghĩa như **nestmate của lookup class**:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

Nhờ vậy hidden class có thể truy cập private member của nest host theo quy tắc nest access, và các nestmate phù hợp cũng có thể truy cập private member của hidden class. Điều này hữu ích khi code generator tạo adapter hoặc accessor cần làm việc với private state của lớp chủ.

### 6.2. Không có NESTMATE

Nếu không truyền tùy chọn này, hidden class không được thêm vào nest của lookup class. Nó không tự có quyền truy cập private member của class gọi chỉ vì được định nghĩa từ lookup đó.

Có lookup đầy đủ để định nghĩa class không đồng nghĩa mọi class được định nghĩa đều tự động là nestmate. Quyền định nghĩa và quan hệ nest là hai vấn đề khác nhau.

### 6.3. NESTMATE không phải bỏ qua mọi kiểm tra truy cập

`NESTMATE` chỉ thiết lập quan hệ nest theo cơ chế JVM. Nó không:

- Cho phép truy cập private member của mọi class bất kỳ.
- Vượt qua mọi ràng buộc module hoặc package.
- Cho phép class tùy ý thay đổi nest host của một class đã tồn tại.
- Là cơ chế sandbox hay cấp quyền cho bytecode không đáng tin cậy.

Hidden class vẫn phải tuân thủ verifier, access checks và các quy tắc JVM còn lại.

## 7. ClassOption.STRONG và vòng đời hidden class

Một lợi ích quan trọng của hidden class là khả năng được unload độc lập với class loader khi không còn được tham chiếu. Theo mặc định, hidden class được giữ bởi quan hệ tham chiếu yếu từ defining class loader; khi không còn đường tham chiếu mạnh tới class, instance, lookup hoặc method handle liên quan, JVM có thể thu hồi class.

Có thể yêu cầu giữ hidden class mạnh từ class loader bằng `ClassOption.STRONG`:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                false,
                MethodHandles.Lookup.ClassOption.STRONG);
~~~

### 7.1. So sánh mặc định và STRONG

| Cấu hình | Quan hệ với defining class loader | Hệ quả vòng đời |
|---|---|---|
| Không có `STRONG` | Hidden class được giữ yếu từ loader | Có thể unload độc lập khi không còn tham chiếu giữ class sống |
| Có `STRONG` | Hidden class được giữ mạnh từ loader | Không thể unload độc lập trước khi loader trở nên không còn reachable |

`STRONG` không làm class trở thành class có thể tải theo tên. Nó chỉ thay đổi reachability và khả năng unload, không thay đổi tính hidden.

### 7.2. Không thể dựa vào thời điểm GC

Khả năng unload không có nghĩa JVM sẽ thu hồi class ngay sau khi method trả về. Nếu ứng dụng còn giữ:

- Instance của hidden class.
- `Class` object.
- `Lookup` hoặc `MethodHandle` tham chiếu tới hidden class.
- Callback hoặc object khác giữ tham chiếu tới các thành phần trên.

thì hidden class vẫn còn reachable. Ngay cả khi không còn tham chiếu, thời điểm garbage collection và class unloading không được bảo đảm chính xác.

### 7.3. Khi nào cần STRONG?

Chỉ chọn `STRONG` khi có lý do vòng đời rõ ràng, ví dụ framework muốn class tồn tại suốt vòng đời class loader. Nếu mục tiêu là sinh nhiều implementation tạm thời và cho phép chúng được unload độc lập, mặc định thường phù hợp hơn.

Không bật `STRONG` theo thói quen. Nếu framework sinh hàng nghìn hidden class và giữ mạnh tất cả chúng qua loader, lợi ích unload độc lập sẽ mất đi và metaspace có thể tăng.

## 8. Kết hợp các tùy chọn

`ClassOption` là enum có các tùy chọn:

- `NESTMATE`.
- `STRONG`.

Có thể kết hợp:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE,
                MethodHandles.Lookup.ClassOption.STRONG);
~~~

Trong ví dụ, hidden class vừa là nestmate của lookup class, vừa được giữ mạnh từ defining class loader.

Không có thứ tự ưu tiên đặc biệt giữa hai tùy chọn này; chúng điều khiển hai khía cạnh khác nhau: quyền truy cập theo nest và reachability/unloading.

## 9. Tạo bytecode động trong framework

`defineHiddenClass` nhận byte array, vì thế bước sinh bytecode là phần riêng của framework:

~~~java
byte[] generatedBytes = bytecodeGenerator.generate(
        packageName,
        implementationName,
        methodDefinitions);

MethodHandles.Lookup hiddenLookup =
        targetLookup.defineHiddenClass(
                generatedBytes,
                false,
                MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

`bytecodeGenerator` ở đây đại diện cho ASM, Byte Buddy hoặc compiler riêng. Để đoạn mã hoạt động:

1. Class file phải hợp lệ và có version tương thích Java 17.
2. Package trong class file phải khớp package của lookup class.
3. Lookup phải có full privilege access.
4. Các class/interface mà bytecode tham chiếu phải có thể được resolve từ defining loader/module.
5. Bytecode phải vượt qua verifier và tuân thủ access checks.

Một generator cần tự kiểm tra cấu trúc bytecode, method descriptor, stack map frame và class version theo thư viện đang dùng. `defineHiddenClass` không sửa bytecode sai thành bytecode hợp lệ.

### 9.1. Dùng interface làm ranh giới

Một thiết kế dễ bảo trì là cho hidden class implement một interface công khai:

~~~java
public interface QueryPlan {
    Object execute(Object input);
}
~~~

Framework định nghĩa hidden implementation rồi trả về `QueryPlan` cho phần còn lại của ứng dụng. Caller không cần biết tên class được sinh, không cần cast sang implementation nội bộ và không phụ thuộc vào hậu tố tên hidden class.

Đây cũng là cách giúp tách phần API ổn định khỏi bytecode sinh động.

### 9.2. Khi cần private access

Nếu generated implementation cần truy cập private field hoặc method của class chủ, framework có thể:

1. Nhận một lookup có quyền phù hợp từ class chủ.
2. Đảm bảo class bytes thuộc cùng package.
3. Định nghĩa hidden class với `NESTMATE`.
4. Chỉ cấp quyền cần thiết cho code generator đáng tin cậy.

Một `Lookup` có full privilege là một capability nhạy cảm. Không phát tán lookup đó cho plugin hoặc code không đáng tin cậy chỉ để thuận tiện.

## 10. Hidden class và các API liên quan

### 10.1. `defineHiddenClass` với `defineHiddenClassWithClassData`

Java 16 bổ sung `Lookup.defineHiddenClassWithClassData` để định nghĩa hidden class đồng thời gắn class data có thể truy cập theo cơ chế được cung cấp bởi `MethodHandles.classData`.

Đây là API nâng cao khi framework cần truyền dữ liệu gắn với class được sinh, thay vì tạo static field hoặc nhúng mọi thông tin vào bytecode. Với bài học cơ bản, `defineHiddenClass` là điểm bắt đầu; chỉ dùng class data khi có nhu cầu cụ thể và đọc đúng hợp đồng Java 17.

### 10.2. `LambdaMetafactory`

`LambdaMetafactory` là API công khai để tạo implementation của functional interface bằng method handle. Nếu mục tiêu chỉ là tạo lambda hoặc adapter cho functional interface, hãy cân nhắc API này trước khi tự sinh class file.

~~~java
Function<String, Integer> length = String::length;
System.out.println(length.apply("Java")); // 4
~~~

Không phải mọi nhu cầu tạo implementation động đều cần gọi `defineHiddenClass` trực tiếp. Các API cấp cao như lambda, dynamic proxy hoặc framework proxy có thể đã giải quyết phần lớn yêu cầu.

### 10.3. `Proxy`

`java.lang.reflect.Proxy` phù hợp khi cần tạo proxy triển khai một hoặc nhiều interface và chuyển lời gọi qua `InvocationHandler`. Nếu chỉ cần intercept method trên interface, hãy cân nhắc Proxy thay vì tự tạo bytecode và quản lý hidden class.

Hidden class hữu ích khi framework cần kiểm soát bytecode hoặc tạo implementation chuyên biệt mà Proxy không đáp ứng.

## 11. Giới hạn và trường hợp không nên dùng hidden class

Hidden class phù hợp với implementation nội bộ, nhưng không phải lựa chọn mặc định cho mọi class được tạo lúc runtime.

Không nên dùng khi:

- Class cần được tải bằng binary name từ cấu hình hoặc `Class.forName`.
- Class cần được các class file khác tham chiếu trực tiếp theo tên.
- Class là kiểu dữ liệu công khai cần serialization, plugin discovery hoặc service registration theo tên.
- Caller cần một class loader riêng biệt và không thể cung cấp lookup có defining loader phù hợp.
- Code sinh ra không cần bytecode tùy chỉnh và có thể dùng lambda, Proxy hoặc factory.
- Bytecode đầu vào không đáng tin cậy và ứng dụng đang nhầm hidden class với sandbox bảo mật.

Hidden class vẫn thực thi trong JVM với quyền của defining context. Nó không cô lập quyền truy cập file, mạng, thread hoặc reflection. Nếu chạy code không đáng tin cậy, cần thiết kế isolation/security ở mức hệ thống phù hợp; hidden class không thay thế cơ chế đó.

## 12. Lỗi thường gặp khi định nghĩa hidden class

### 12.1. Lookup không có full privilege access

Nếu dùng `MethodHandles.publicLookup()` hoặc lookup không đủ quyền, `defineHiddenClass` có thể ném `IllegalAccessException`.

**Cách xử lý:** lấy lookup từ class trong package đích hoặc nhận lookup có quyền phù hợp từ thành phần sở hữu package. Không tìm cách mở rộng quyền một cách tùy tiện.

### 12.2. Package trong class file không khớp

Class file thuộc `com.example.generated` nhưng lookup class thuộc `com.example.runtime` sẽ không thỏa yêu cầu cùng package.

**Cách xử lý:** cấu hình generator tạo class trong package của lookup, hoặc lấy lookup thích hợp từ package mà framework cần.

### 12.3. Nghĩ hidden class tải được bằng tên

`Class.getName()` không biến hidden class thành class có thể nạp bằng `Class.forName`. Không dùng tên được trả về làm khóa registry lâu dài.

**Cách xử lý:** giữ `Class` object, `Lookup`, `MethodHandle` hoặc interface mà instance implement.

### 12.4. Quên NESTMATE

Hidden class không tự động là nestmate của lookup class. Nếu bytecode cần truy cập private member của nest host, thiếu `NESTMATE` có thể dẫn đến lỗi access khi liên kết hoặc thực thi.

**Cách xử lý:** chỉ dùng `NESTMATE` khi quan hệ nest là một phần thiết kế và lookup có quyền phù hợp.

### 12.5. Dùng STRONG mà không xét unload

`STRONG` khiến defining loader giữ hidden class mạnh. Nếu tạo class liên tục, lựa chọn này có thể ngăn unload độc lập.

**Cách xử lý:** chỉ bật khi vòng đời cần class gắn với loader; nếu không, cân nhắc mặc định.

### 12.6. Nhầm defineHiddenClass với bytecode generator

Phương thức nhận class file bytes; nó không biên dịch mã nguồn hoặc sinh method body.

**Cách xử lý:** tách bước generate bytecode khỏi bước define class, kiểm tra output của generator trước khi gọi API.

### 12.7. Cho rằng hidden class là sandbox

Hidden class không cách ly quyền của code. Nó chỉ thay đổi khả năng khám phá và vòng đời class.

**Cách xử lý:** chỉ định nghĩa bytecode từ nguồn tin cậy hoặc áp dụng mô hình cô lập riêng.

## 13. Bài tập thực hành

### Bài 1 — Phân biệt class thường và hidden class

Giải thích khác biệt giữa `Lookup.defineClass` và `Lookup.defineHiddenClass` về khả năng khám phá bằng tên, vòng đời và cách caller giữ quyền truy cập.

### Bài 2 — Đọc ví dụ

Chạy chương trình `HiddenClassDemo` ở phần 4. Giải thích:

1. Vì sao class bytes và lookup phải cùng package?
2. Vì sao kết quả `isHidden()` là true?
3. Vì sao instance có thể được dùng qua interface `Task`?
4. Vì sao không cần biết tên runtime của hidden class?

### Bài 3 — Thử initialize

Thêm static initializer vào `GeneratedTask` để ghi một thông báo. Chạy với tham số `initialize = true` rồi `false`; xác định thời điểm thông báo xuất hiện khi class được sử dụng lần đầu.

### Bài 4 — So sánh NESTMATE

Tìm hiểu một class generated cần gọi private method của nest host. Thử định nghĩa với và không có `NESTMATE`; giải thích quan hệ nest và điều kiện quyền truy cập. Không thay đổi bytecode của class JDK.

### Bài 5 — Vòng đời STRONG

Định nghĩa hidden class với và không có `STRONG`. Vẽ sơ đồ tham chiếu giữa class loader, Lookup, Class object và instance. Giải thích vì sao không thể dùng thời điểm GC như một deadline xác định để kiểm tra unload.

### Bài 6 — Chọn API phù hợp

Với từng nhu cầu, chọn `defineHiddenClass`, `defineClass`, `Proxy` hoặc `LambdaMetafactory`:

- Implementation cần được tải lại theo tên từ cấu hình.
- Adapter cho một functional interface đơn giản.
- Proxy intercept lời gọi trên interface.
- Bytecode implementation nội bộ do framework sinh, không cần tên công khai.

Nêu lý do lựa chọn và ràng buộc về lookup/package.

## 14. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Giải thích hidden class là class được định nghĩa từ bytecode nhưng không được khám phá bằng cơ chế tải tên thông thường.
2. Dùng `Lookup.defineHiddenClass(byte[], boolean, ClassOption...)` và lấy class từ `returnedLookup.lookupClass()`.
3. Nêu được yêu cầu full-privilege lookup, package phù hợp và class file bytes hợp lệ.
4. Phân biệt `initialize = true` và `false`.
5. Giải thích tác dụng của `NESTMATE` và `STRONG`.
6. Mô tả hidden class có thể được unload độc lập theo reachability mặc định, nhưng GC/unloading không có thời điểm bảo đảm.
7. Dùng MethodHandles hoặc interface chung để tạo và gọi instance mà không phụ thuộc tên implementation.
8. Phân biệt hidden class với class thông thường, Proxy và lambda implementation.
9. Nhận diện trường hợp không nên dùng hidden class và không coi nó là sandbox.
10. Biên dịch ví dụ bằng JDK 17 mà không bật preview.

## 15. Tài liệu chính thức

- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): mục tiêu thiết kế, tính hidden, nestmate và khả năng unload.
- [Java SE 17 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): điều kiện định nghĩa hidden class, initialize và lookup trả về.
- [Java SE 17 API — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
- [Java SE 17 API — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): API kiểm tra trạng thái hidden qua `isHidden()`.
- [Java SE 17 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): API định nghĩa class thông thường qua `defineClass(byte[])` để so sánh.
- [Java SE 17 API — `MethodHandles.classData`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): API class data cho hidden class.
- [Java SE 17 API — `LambdaMetafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): tạo implementation của functional interface từ method handle.
- [Java SE 17 API — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): dynamic proxy cho interface.

**Ghi nhớ:** `defineHiddenClass` nhận bytecode đã được sinh, yêu cầu một lookup có full privilege trong đúng package và trả về lookup gắn với class ẩn. `NESTMATE` điều khiển quan hệ truy cập private theo nest; `STRONG` điều khiển reachability từ class loader. Hãy dùng hidden class cho implementation sinh động không cần tên công khai, giữ nó sau interface/MethodHandle phù hợp và quản lý vòng đời tham chiếu có chủ đích.
