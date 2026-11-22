# Vòng đời, khả năng tìm theo tên và mục đích của hidden class trong Java 17

**Chủ đề:** Java 17  
**Chương:** Reflection và truy cập  
**Bài học:** Vòng đời, khả năng tìm theo tên và mục đích của hidden class

Hidden class là một loại class được định nghĩa tại runtime bằng API của `java.lang.invoke.MethodHandles.Lookup`, dành cho những class mà framework hoặc runtime tạo ra bằng bytecode và không cần xuất hiện như class thông thường trong namespace của class loader.

Một hidden class có thể được khởi tạo, tạo instance, gọi method bằng method handle và tham gia nest của một class khác. Tuy nhiên, nó **không thể được tìm thấy bằng tên thông qua cơ chế tải class thông thường** như `Class.forName()` hoặc `ClassLoader.loadClass()`. Đây là điểm quan trọng giúp framework tạo class triển khai tạm thời mà không làm đầy namespace của class loader.

Hidden class được chuẩn hóa trong Java 15 qua JEP 371 và tiếp tục được hỗ trợ trong Java 17. API chính là:

- `MethodHandles.Lookup.defineHiddenClass(...)`: định nghĩa hidden class từ bytecode.
- `MethodHandles.Lookup.defineHiddenClassWithClassData(...)`: định nghĩa hidden class và gắn dữ liệu class riêng.
- `Class.isHidden()`: kiểm tra một đối tượng `Class` có đại diện cho hidden class hay không.
- `MethodHandles.Lookup.lookupClass()`: lấy `Class` mà một lookup object đang đại diện.
- `MethodHandles.Lookup.ClassOption.NESTMATE` và `STRONG`: các tùy chọn quan trọng ảnh hưởng đến quyền truy cập và vòng đời.

Hidden class đặc biệt hữu ích cho framework tạo proxy, adapter, accessor hoặc các class triển khai được sinh động. Nó không phải cách khai báo class thông thường, không phải cơ chế bảo mật để giấu dữ liệu, và không thay thế class loader hoặc JPMS.

## 1. Hidden class là gì?

Một class Java thông thường được định nghĩa trong source code hoặc bytecode và có thể được tìm theo tên nhị phân trong namespace của class loader. Ví dụ:

```java
Class<?> type = Class.forName("com.example.User");
```

Hoặc:

```java
Class<?> type = classLoader.loadClass("com.example.User");
```

Cơ chế này phù hợp với các class ứng dụng, plugin, thư viện và API công khai.

Nhưng framework đôi khi cần sinh bytecode mới khi chương trình chạy. Ví dụ:

- Tạo class adapter để gọi một API cụ thể nhanh hơn.
- Sinh accessor cho field hoặc property của entity.
- Tạo implementation cho một interface hoặc một biểu thức đã được phân tích.
- Sinh class hỗ trợ serialization, mapping hoặc proxy.
- Tạo mã triển khai chuyên biệt theo cấu trúc dữ liệu tại runtime.

Nếu mỗi class được sinh đều được định nghĩa như một class thông thường, namespace của class loader có thể chứa rất nhiều class có tên, kể cả những class chỉ dùng trong thời gian ngắn. Điều này làm việc quản lý vòng đời, xung đột tên và class unloading phức tạp hơn.

**Hidden class** giải quyết nhóm nhu cầu này: class được định nghĩa và sử dụng qua các tham chiếu runtime, nhưng không được đăng ký như một class có thể tải lại bằng tên.

### 1.1. Hidden class vẫn là một class thực sự

Hidden class không phải một đoạn mã giả lập hoặc một object đặc biệt thay cho class. JVM vẫn định nghĩa class, tạo metadata, kiểm tra bytecode, thực hiện khởi tạo class và có thể tạo instance của nó.

Ta có thể lấy `Class<?>` của hidden class và kiểm tra:

```java
Class<?> hiddenType = hiddenLookup.lookupClass();

System.out.println(hiddenType.isHidden()); // true
System.out.println(hiddenType.getClassLoader());
System.out.println(hiddenType.getModule());
```

Nó vẫn có:

- Một đối tượng `Class<?>`.
- Một defining class loader.
- Một runtime package và module theo ngữ cảnh định nghĩa.
- Các method, field, constructor và metadata cần thiết.
- Vòng đời class và khả năng được JVM unload.

Điểm khác biệt nằm ở **khả năng khám phá và cách class được tham chiếu**. Hidden class không được tìm lại bằng tên thông thường trong namespace class loader.

### 1.2. Hidden class không phải modifier trong source code

Java không có cú pháp khai báo như:

```java
// Đây không phải cú pháp Java:
hidden class GeneratedAccessor {
}
```

Thay vào đó, framework tạo hoặc nhận bytecode của class rồi yêu cầu JVM định nghĩa nó qua `MethodHandles.Lookup`.

Vì vậy, hidden class thường xuất hiện trong code của framework, bytecode generator hoặc runtime, thay vì trong mã nghiệp vụ thông thường.

## 2. Vì sao hidden class không thể tìm theo tên?

Một class thông thường có thể được tra cứu bằng tên nhị phân thông qua class loader. Hidden class được thiết kế để không tham gia cách tra cứu đó.

Các API tải class theo tên như:

```java
Class.forName("com.example.GeneratedAccessor");
classLoader.loadClass("com.example.GeneratedAccessor");
```

không thể dùng để tìm một hidden class đã được định nghĩa. Nếu biết tên classfile ban đầu cũng không có nghĩa ta có thể tải hidden class qua tên đó.

Thay vào đó, code nhận được một `Lookup` từ thao tác định nghĩa và lấy `Class<?>` trực tiếp:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classBytes,
                true
        );

Class<?> hiddenType = hiddenLookup.lookupClass();
```

`hiddenLookup` là đường tham chiếu do JVM trả về cho class vừa định nghĩa. Từ lookup này, caller có thể tìm method handle phù hợp, tạo instance hoặc thực hiện các thao tác được quyền truy cập cho phép.

### 2.1. Tên do Class.getName() trả về không phải khóa tra cứu

Một hidden class vẫn có thể có tên hiển thị khi gọi `Class.getName()`. Với hidden class, tên thường gồm tên nhị phân của classfile cộng một phần hậu tố do JVM tạo, ví dụ dạng:

```text
com.example.GeneratedAccessor/0x0000000800c02400
```

Phần hậu tố là tên không định danh do JVM sinh để phân biệt class. Không nên dựa vào chuỗi này để:

- Gọi `Class.forName()`.
- Gọi `ClassLoader.loadClass()`.
- Lưu làm định danh ổn định giữa các lần chạy.
- Tạo cấu hình hoặc tên plugin.
- So sánh danh tính class giữa hai JVM.

Tên đó phục vụ thông tin runtime và chẩn đoán. Cách tham chiếu đúng là giữ `Class<?>`, `Lookup`, instance hoặc `MethodHandle` được trả về trong quá trình định nghĩa.

### 2.2. Hidden class có thể được quan sát nếu đã có tham chiếu

"Hidden" không có nghĩa class hoàn toàn vô hình trước mọi công cụ. Nếu chương trình đã giữ `Class<?>`, instance hoặc method handle của nó, chương trình có thể sử dụng những tham chiếu đó và kiểm tra metadata tương ứng.

Ví dụ:

```java
Class<?> type = hiddenLookup.lookupClass();

if (type.isHidden()) {
    System.out.println("Đây là hidden class");
}
```

Tên hidden class cũng có thể xuất hiện trong stack trace hoặc thông tin chẩn đoán. Vì vậy, không xem hidden class như cơ chế che giấu bí mật hay bảo vệ dữ liệu.

### 2.3. Không thể dùng hidden class như một dependency được tham chiếu bằng tên

Hidden class không được thiết kế để các class khác tham chiếu bằng symbolic name trong constant pool của bytecode như một kiểu thông thường. Do đó, hidden class không phù hợp làm:

- Kiểu superclass hoặc superinterface được khai báo trong class khác.
- Kiểu field, tham số hoặc giá trị trả về được khai báo trong bytecode class khác.
- Kiểu public trong API mà caller cần compile hoặc load bằng tên.
- Điểm mở rộng cho plugin discovery theo tên class.

Caller vẫn có thể thao tác với đối tượng qua `Object`, interface công khai hoặc method handle. Ví dụ framework có thể giữ method handle tới một method trong hidden class mà không cần class khác tham chiếu tên hidden class.

## 3. API định nghĩa hidden class trong Java 17

Hidden class được định nghĩa qua `MethodHandles.Lookup`. Đây là API thuộc package `java.lang.invoke`.

### 3.1. Lookup.defineHiddenClass()

Chữ ký API chính:

```java
Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        Lookup.ClassOption... options
) throws IllegalAccessException
```

Ý nghĩa tham số:

| Tham số | Ý nghĩa |
|---|---|
| `bytes` | Bytecode classfile cần định nghĩa |
| `initialize` | Có khởi tạo class ngay sau khi định nghĩa hay không |
| `options` | Tùy chọn như `NESTMATE` hoặc `STRONG` |

Kết quả là một `Lookup` mới có lookup class là hidden class vừa được định nghĩa.

Ví dụ khung:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE
        );

Class<?> hiddenClass = hiddenLookup.lookupClass();
```

Bytecode phải hợp lệ và classfile phải thuộc cùng package với lookup class. Lookup dùng để định nghĩa phải có quyền truy cập đầy đủ theo yêu cầu của API. Nếu không đáp ứng điều kiện truy cập hoặc package, thao tác có thể thất bại.

### 3.2. Vì sao cần MethodHandles.Lookup?

`Lookup` mang theo ngữ cảnh truy cập của code đang thực hiện thao tác. Nó xác định class gọi, quyền truy cập và ngữ cảnh module cần thiết.

Điều này có ý nghĩa vì hidden class được định nghĩa trong cùng package và class loader với lookup class. Quyền định nghĩa không phải một thao tác toàn cục mà bất kỳ code nào cũng có thể thực hiện với bytecode tùy ý.

Trong ví dụ đơn giản, `MethodHandles.lookup()` tạo lookup phản ánh quyền của class hiện tại:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
System.out.println(lookup.lookupClass());
```

Một framework có thể nhận hoặc tạo lookup phù hợp từ class đích. Việc tạo lookup có quyền private hoặc full privilege cần tuân theo quy tắc của `MethodHandles` và module system; không thể tự ý nâng quyền chỉ bằng cách gọi một API.

### 3.3. Classfile phải cùng package với lookup class

`defineHiddenClass()` định nghĩa class trong cùng package với lookup class. Vì vậy bytecode đưa vào phải khai báo class thuộc package tương ứng.

Ví dụ nếu lookup class nằm trong:

```java
package com.example.runtime;
```

thì classfile cần định nghĩa hidden class cũng phải thuộc package `com.example.runtime`. Không thể dùng lookup ở package này để tùy ý định nghĩa hidden class trong một package khác.

Điều kiện này gắn hidden class với ngữ cảnh định nghĩa và quyền truy cập của lookup.

## 4. Vòng đời hidden class: weak mặc định và STRONG

Một lý do quan trọng để dùng hidden class là khả năng unload class mà không cần đợi toàn bộ defining class loader bị thu hồi.

Vòng đời của hidden class phụ thuộc vào các tham chiếu giữ nó sống và tùy chọn định nghĩa class.

### 4.1. Mặc định: hidden class có thể được unload độc lập với class loader

Nếu không chỉ định `ClassOption.STRONG`, hidden class được giữ bằng quan hệ weak từ defining class loader. Điều này cho phép JVM unload hidden class khi không còn tham chiếu mạnh cần thiết, ngay cả khi class loader định nghĩa nó vẫn còn sống.

Mô hình khái quát:

```text
Defining ClassLoader vẫn còn sống
              |
              | weak reference
              v
          Hidden Class
              ^
              |
       strong references
       từ Class / instance /
       Lookup / MethodHandle
```

Khi các tham chiếu mạnh đến hidden class và instance của nó không còn, class có thể đủ điều kiện để được unload. Việc unload do JVM và garbage collector quyết định; ứng dụng không thể yêu cầu thời điểm unload chính xác.

Đây là khác biệt có ích so với class thông thường được định nghĩa trong class loader: class thông thường thường gắn với vòng đời của defining loader, trong khi hidden class mặc định có thể được thu hồi riêng khi không còn được sử dụng.

### 4.2. Tham chiếu mạnh vẫn giữ hidden class sống

Hidden class không tự biến mất chỉ vì nó không thể tìm bằng tên. Nếu ứng dụng còn giữ các tham chiếu như:

- Instance được tạo từ hidden class.
- Đối tượng `Class<?>` của hidden class.
- `MethodHandles.Lookup` trả về từ thao tác định nghĩa.
- `MethodHandle` trỏ tới method của hidden class.
- Một object hoặc cấu trúc dữ liệu khác giữ các tham chiếu đó.

thì hidden class vẫn có thể còn được sử dụng và chưa đủ điều kiện unload.

Ví dụ:

```java
Class<?> hiddenType = hiddenLookup.lookupClass();

Object instance = hiddenType.getDeclaredConstructor().newInstance();

// Khi còn giữ instance hoặc hiddenType,
// không nên kỳ vọng class được unload.
```

Việc gán biến thành `null` cũng không bảo đảm class được unload ngay. JVM cần xác định không còn đường tham chiếu mạnh nào giữ class hoặc instance sống, sau đó việc class unloading còn phụ thuộc chính sách GC và trạng thái runtime.

### 4.3. ClassOption.STRONG: giữ hidden class theo vòng đời class loader

Nếu định nghĩa hidden class với `STRONG`:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.STRONG
        );
```

hidden class được giữ mạnh bởi defining class loader. Nó không được unload riêng chỉ vì các tham chiếu khác đến class đã biến mất; class loader phải trở nên không còn được sử dụng và có thể được thu hồi thì hidden class mới có thể được unload cùng loader.

So sánh:

| Đặc điểm | Mặc định (không STRONG) | Có `STRONG` |
|---|---|---|
| Quan hệ từ defining loader | Weak reachability | Strong reachability |
| Có thể unload khi loader vẫn sống? | Có, nếu không còn tham chiếu mạnh khác | Không |
| Vòng đời gần với class thông thường? | Không, có thể ngắn hơn loader | Gần hơn với class gắn với loader |
| Mục đích | Class sinh động, có thể thu hồi riêng | Class cần sống theo vòng đời loader |

`STRONG` không có nghĩa class tồn tại vĩnh viễn. Khi defining class loader có thể được thu hồi, hidden class được giữ bởi loader cũng có thể được unload.

### 4.4. Không thể dựa vào thời điểm garbage collection

Class unloading không phải thao tác đồng bộ mà code có thể quan sát chính xác sau một lệnh `System.gc()`. Lời gọi đó chỉ là yêu cầu GC, không phải cam kết class sẽ được unload.

Khi thiết kế framework, nên:

- Giải phóng tham chiếu tới `Class`, instance, `Lookup` và `MethodHandle` khi không còn dùng.
- Tránh lưu method handle của hidden class trong cache toàn cục vô thời hạn.
- Chọn `STRONG` chỉ khi cần giữ class theo vòng đời loader.
- Không viết logic nghiệp vụ phụ thuộc vào thời điểm class được unload.

## 5. Tùy chọn NESTMATE: hidden class tham gia nest

Java có khái niệm *nest* để các class có quan hệ tin cậy về quyền truy cập private. Ví dụ class ngoài và nested class thường thuộc cùng nest.

Khi định nghĩa hidden class với `ClassOption.NESTMATE`, hidden class được thêm vào nest của lookup class. Nhờ đó, hidden class có thể truy cập private member của nest host theo quy tắc nest-based access control.

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE
        );
```

Điều này hữu ích cho framework sinh accessor hoặc implementation cần tương tác với private state của class đích.

### 5.1. NESTMATE không đồng nghĩa mở package cho mọi module

`NESTMATE` giải quyết quan hệ truy cập private trong nest. Nó không thay thế `exports` hoặc `opens` của JPMS và không cấp quyền tùy ý vượt qua module boundary.

Quyền truy cập vẫn phụ thuộc lookup và các quy tắc module. Không nên dùng `NESTMATE` như cách sửa mọi lỗi reflection hoặc lỗi đóng gói mạnh.

### 5.2. Khi nào cần NESTMATE?

Chọn `NESTMATE` khi class sinh ra cần truy cập private member của class sở hữu lookup, ví dụ:

- Sinh accessor cho field private.
- Sinh implementation hỗ trợ class đích và cần gọi private method.
- Sinh mã tối ưu hóa hoạt động như một thành viên tin cậy của nest.

Nếu hidden class chỉ gọi public API và không cần quyền private của nest host, không nhất thiết phải bật tùy chọn này.

## 6. Class initialization và constructor là hai việc khác nhau

Tham số `initialize` của `defineHiddenClass()` quyết định JVM có chạy class initialization ngay sau khi định nghĩa hay không.

### 6.1. initialize = true

```java
Lookup hiddenLookup = lookup.defineHiddenClass(
        classBytes,
        true
);
```

Nếu class có static initializer (`<clinit>`), JVM thực hiện khởi tạo class theo quy tắc thông thường trước khi thao tác định nghĩa hoàn tất.

### 6.2. initialize = false

```java
Lookup hiddenLookup = lookup.defineHiddenClass(
        classBytes,
        false
);
```

Class được định nghĩa nhưng việc khởi tạo được trì hoãn cho đến khi có thao tác chủ động sử dụng class yêu cầu initialization, theo quy tắc khởi tạo class của JVM.

Tham số này **không** có nghĩa constructor instance tự được gọi hoặc object được tạo. Định nghĩa class, khởi tạo class (static initialization) và tạo instance là ba giai đoạn khác nhau.

### 6.3. Tạo instance sau khi định nghĩa

Từ `Lookup` trả về, có thể lấy `Class<?>` rồi sử dụng reflection hoặc method handle theo quyền phù hợp:

```java
Class<?> hiddenClass = hiddenLookup.lookupClass();

Object instance =
        hiddenClass.getDeclaredConstructor().newInstance();
```

Nếu hidden class không có constructor truy cập được theo ngữ cảnh hiện tại, thao tác tạo instance có thể thất bại. Một framework có thể dùng `hiddenLookup.findConstructor(...)` để tạo method handle phù hợp thay vì dựa vào reflection.

## 7. Ví dụ hoàn chỉnh: định nghĩa hidden class từ bytecode

JDK không cung cấp API cấp cao để viết bytecode tùy ý. Framework thường dùng bytecode generator hoặc thư viện như ASM để tạo classfile. Để minh họa API Java 17 mà không phụ thuộc thư viện ngoài, ví dụ sau đọc bytecode của một class cùng package, rồi định nghĩa một hidden class từ chính bytecode đó.

Ví dụ cần hai class trong cùng package `com.example`. Class `GeneratedTask` là mẫu bytecode:

```java
package com.example;

class GeneratedTask {
    public static String run() {
        return "Hidden implementation executed";
    }
}
```

Class demo:

```java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassDemo {

    static byte[] classBytes(Class<?> type) throws IOException {
        String resourceName = type.getSimpleName() + ".class";

        try (InputStream input =
                     type.getResourceAsStream(resourceName)) {

            if (input == null) {
                throw new IOException("Cannot find " + resourceName);
            }

            return input.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = classBytes(GeneratedTask.class);

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(
                        bytes,
                        true,
                        MethodHandles.Lookup.ClassOption.NESTMATE
                );

        Class<?> hiddenClass = hiddenLookup.lookupClass();

        System.out.println("isHidden = " + hiddenClass.isHidden());
        System.out.println("name = " + hiddenClass.getName());

        MethodHandle run = hiddenLookup.findStatic(
                hiddenClass,
                "run",
                MethodType.methodType(String.class)
        );

        String result = (String) run.invokeExact();
        System.out.println(result);
    }
}
```

Biên dịch và chạy từ thư mục source phù hợp:

```bash
javac --release 17 -d out com/example/GeneratedTask.java com/example/HiddenClassDemo.java
java -cp out com.example.HiddenClassDemo
```

Kết quả minh họa:

```text
isHidden = true
name = com.example.GeneratedTask/0x0000000800c02400
Hidden implementation executed
```

Phần hậu tố trong tên là ví dụ; JVM có thể sinh giá trị khác ở mỗi lần chạy.

### 7.1. Điều gì đã xảy ra?

1. `GeneratedTask.class` được đọc thành mảng byte.
2. `MethodHandles.lookup()` tạo lookup trong package `com.example`.
3. `defineHiddenClass()` định nghĩa một hidden class từ bytecode cùng package.
4. `lookupClass()` lấy `Class<?>` của hidden class.
5. `isHidden()` xác nhận class thuộc loại hidden.
6. `findStatic()` tạo method handle tới method `run`.
7. `invokeExact()` gọi method mà không cần tải class theo tên.

Ví dụ sử dụng bytecode của một class bình thường làm mẫu để minh họa cơ chế. Trong framework thật, bytecode thường được sinh chuyên biệt cho class hoặc dữ liệu tại runtime; hidden class được tạo để không cần đăng ký implementation đó trong namespace tên class thông thường.

### 7.2. Vì sao gọi method handle thay vì Class.forName?

Sau khi định nghĩa, ta đã có lookup và `Class<?>`. Việc tìm method thông qua `hiddenLookup.findStatic(...)` dùng trực tiếp quyền và class mà lookup đại diện.

Nếu cố tìm lại class theo chuỗi tên từ `hiddenClass.getName()`, cơ chế class loader thông thường không tìm được hidden class đó. Vì vậy, hãy giữ tham chiếu được trả về trong quá trình định nghĩa.

## 8. defineHiddenClassWithClassData(): gắn dữ liệu với hidden class

Ngoài bytecode, framework đôi khi cần gắn dữ liệu riêng với class được sinh ra, chẳng hạn cấu hình, metadata hoặc thông tin liên quan đến quá trình sinh mã.

Java 17 cung cấp `defineHiddenClassWithClassData()` để định nghĩa hidden class và gắn một object class data:

```java
Lookup defineHiddenClassWithClassData(
        byte[] bytes,
        Object classData,
        boolean initialize,
        Lookup.ClassOption... options
) throws IllegalAccessException
```

Dữ liệu này được liên kết với hidden class theo cơ chế class data của `MethodHandles`. Nó không giống một field static thông thường được khai báo trong classfile.

Một số điểm cần nhớ:

- Class data gắn với hidden class được định nghĩa.
- API truy cập class data được thiết kế cho lookup có quyền phù hợp.
- Dữ liệu có thể là object cấu hình hoặc metadata mà bytecode sinh ra cần sử dụng.
- Không nên xem class data như một cơ chế lưu trữ bền vững; vòng đời của nó gắn với class và các tham chiếu liên quan.

Khả năng này hữu ích khi framework muốn giữ dữ liệu triển khai ở runtime mà không cần nhúng toàn bộ giá trị vào bytecode dạng hằng số.

## 9. Hidden class giải quyết bài toán gì?

### 9.1. Tránh làm đầy namespace class loader

Một framework có thể sinh hàng nghìn implementation chuyên biệt trong suốt thời gian chạy. Nếu mỗi class được đăng ký như class thông thường, tên và metadata của chúng có thể tồn tại theo vòng đời loader.

Hidden class không được tìm theo tên trong namespace thông thường. Với mặc định weak, class có thể được unload riêng khi không còn tham chiếu, ngay cả khi class loader vẫn sống.

### 9.2. Giảm nguy cơ xung đột tên của class sinh động

Class thông thường trong cùng class loader không thể tùy ý định nghĩa nhiều class có cùng tên nhị phân. Hidden class không được đăng ký theo cùng cách tra cứu tên, nên framework có thể định nghĩa nhiều hidden class từ classfile có cùng tên ban đầu trong cùng ngữ cảnh loader.

Tên runtime của chúng được JVM bổ sung hậu tố để phân biệt. Code không nên dùng tên này như định danh nghiệp vụ.

### 9.3. Hỗ trợ implementation chuyên biệt

Framework có thể sinh bytecode dựa trên metadata của một class hoặc schema. Ví dụ:

- Accessor chỉ đọc một tập field cụ thể.
- Adapter chuyển đổi một kiểu dữ liệu sang giao thức.
- Implementation cho một biểu thức hoặc lambda đã phân tích.
- Mã mapping giữa object và cột database.
- Proxy nội bộ được tạo để tối ưu một đường gọi.

Hidden class phù hợp khi implementation chỉ cần được framework giữ và sử dụng qua các tham chiếu runtime.

### 9.4. Hỗ trợ quyền truy cập private qua nestmate

Với `NESTMATE`, hidden class có thể tham gia nest của lookup class và truy cập private member theo quy tắc nest. Điều này giúp framework tạo accessor hoặc adapter hoạt động cùng class đích mà không phải biến toàn bộ field thành public.

Tùy chọn này cần được dùng đúng ngữ cảnh; nó không phải cách cấp quyền chung cho module khác.

### 9.5. Vòng đời phù hợp với class sinh tạm thời

Một class triển khai được tạo cho một cấu trúc dữ liệu hoặc tác vụ cụ thể có thể không cần tồn tại sau khi tác vụ kết thúc. Hidden class mặc định hỗ trợ class unloading độc lập với loader khi các tham chiếu đã biến mất.

Điều này có thể giảm áp lực giữ metadata class trong các framework sinh nhiều class động. Tuy nhiên, nếu framework giữ lại instance, lookup hoặc method handle trong cache, hidden class vẫn có thể sống lâu.

## 10. Hidden class khác gì class thông thường và anonymous class?

| Tiêu chí | Class thông thường | Anonymous/local class | Hidden class |
|---|---|---|---|
| Khai báo bằng source code | Có | Có | Không có modifier source; định nghĩa từ bytecode |
| Tìm bằng tên class loader | Có, nếu class được định nghĩa theo cơ chế thông thường | Có thể có tên runtime, nhưng không phải API tra cứu ổn định | Không |
| Có `Class<?>` | Có | Có | Có |
| Có thể tạo instance | Có | Có | Có |
| Có thể gọi method | Trực tiếp hoặc reflection/handle | Trực tiếp hoặc reflection/handle | Qua instance, reflection hoặc method handle theo quyền |
| Có thể tham gia nest | Theo quy tắc class/nest | Theo cấu trúc khai báo | Có thể chọn `NESTMATE` |
| Unload độc lập với defining loader | Thường không theo cơ chế thông thường | Không phải mục tiêu của cơ chế anonymous/local | Có thể, mặc định weak |
| Mục đích chính | Model, API, implementation ổn định | Implementation cục bộ được khai báo trong source | Implementation bytecode được sinh động, không cần tra cứu tên |

Anonymous class và local class vẫn là class được compiler tạo ra từ source code. Hidden class là class được định nghĩa bằng runtime API và có chính sách discoverability/lifecycle riêng.

## 11. Hidden class không phải cơ chế bảo mật

Tên "hidden" dễ tạo cảm giác class được bảo vệ khỏi mọi truy cập, nhưng ý nghĩa kỹ thuật là **không thể khám phá bằng tên qua class loader thông thường**.

Nếu một chương trình có tham chiếu đến `Class<?>`, instance hoặc method handle, nó vẫn có thể sử dụng những gì được quyền truy cập cho phép. Stack trace và công cụ chẩn đoán cũng có thể cho thấy tên runtime của class.

Hidden class không:

- Mã hóa bytecode.
- Che giấu dữ liệu khỏi người có quyền truy cập runtime.
- Thay thế kiểm soát truy cập của Java hoặc JPMS.
- Cung cấp sandbox cho mã không tin cậy.
- Bảo đảm code sinh ra không thể bị quan sát hoặc phân tích.

Nếu cần bảo mật, phải dùng mô hình quyền truy cập, module boundary, xác thực, mã hóa và sandbox phù hợp với yêu cầu thực tế. Không dùng hidden class để giữ bí mật khóa hoặc dữ liệu nhạy cảm.

## 12. Khi nào không nên dùng hidden class?

Hidden class là công cụ chuyên biệt. Class thông thường phù hợp hơn nếu ứng dụng cần một hoặc nhiều đặc điểm sau:

- Class phải được plugin hoặc framework khác tìm theo tên.
- Class là một kiểu công khai trong API.
- Class phải xuất hiện trong cấu hình bằng tên nhị phân.
- Class cần được nạp qua `ClassLoader.loadClass()`.
- Hệ thống cần quét package/classpath để khám phá implementation.
- Vòng đời class nên gắn rõ ràng với class loader.
- Code không sinh bytecode và không có nhu cầu quản lý class runtime chuyên biệt.

Ví dụ một plugin được cấu hình bằng:

```text
implementation=com.example.plugins.CsvImporter
```

cần một class có thể được class loader tìm bằng tên. Hidden class không phù hợp với hợp đồng này.

Tương tự, nếu chỉ cần tạo một lambda, anonymous class hoặc class thông thường, hãy dùng ngôn ngữ Java và API chuẩn trước. Không nên tự xây bytecode generator và hidden class nếu không có nhu cầu thực sự.

## 13. Các lỗi và hiểu nhầm thường gặp

### Lỗi 1. Nghĩ hidden class có thể tải lại bằng Class.forName()

Không thể. Hidden class không được đăng ký để tra cứu theo tên trong namespace class loader. Giữ `Lookup`, `Class<?>`, instance hoặc method handle nhận được khi định nghĩa.

### Lỗi 2. Dùng Class.getName() làm tên ổn định

Tên hidden class có hậu tố do JVM sinh và không phải khóa tra cứu ổn định. Không lưu tên này vào cấu hình hoặc database để tải lại sau.

### Lỗi 3. Nghĩ hidden class không có Class<?>

Hidden class vẫn có `Class<?>`. Có thể lấy qua `hiddenLookup.lookupClass()` và kiểm tra bằng `isHidden()`.

### Lỗi 4. Nghĩ hidden class tự unload ngay sau khi method kết thúc

Không. Class chỉ đủ điều kiện unload khi không còn tham chiếu mạnh giữ nó hoặc instance của nó sống; thời điểm unload do JVM quyết định.

### Lỗi 5. Chọn STRONG mà không cân nhắc vòng đời loader

`STRONG` giữ hidden class mạnh từ defining loader. Nếu loader sống lâu, hidden class cũng có thể bị giữ lâu hơn. Chọn mặc định weak khi cần class có thể được thu hồi riêng.

### Lỗi 6. Cho rằng NESTMATE mở toàn bộ module

Không. `NESTMATE` cho phép tham gia nest và truy cập private member theo quy tắc nest. Nó không thay thế `exports`, `opens` hoặc quyền module.

### Lỗi 7. Định nghĩa bytecode khác package với lookup class

`defineHiddenClass()` yêu cầu classfile thuộc cùng package với lookup class. Hãy sinh bytecode đúng package hoặc dùng lookup từ package phù hợp với thiết kế.

### Lỗi 8. Nhầm initialize với tạo instance

`initialize = true` chạy class initialization, không gọi constructor instance. Tạo object là thao tác riêng sau đó.

### Lỗi 9. Giữ method handle trong cache vô hạn

Method handle có thể giữ hidden class sống. Cache toàn cục cần có chính sách giới hạn, loại bỏ hoặc gắn vòng đời với đối tượng sử dụng.

### Lỗi 10. Xem hidden class là lớp bảo mật

Hidden class chỉ không được tra cứu bằng tên. Nếu có tham chiếu runtime, code vẫn có thể sử dụng class theo quyền được cấp.

## 14. Quy trình quyết định sử dụng hidden class

Trước khi chọn hidden class, hãy trả lời các câu hỏi:

1. Class có được sinh bằng bytecode tại runtime không?
2. Class có cần được tìm lại qua tên hoặc classpath không?
3. Class chỉ phục vụ implementation nội bộ trong một framework/runtime?
4. Có cần truy cập private member của class đích không? Nếu có, `NESTMATE` có phù hợp không?
5. Class có nên được unload độc lập với class loader không? Nếu có, cân nhắc mặc định weak.
6. Có cần giữ class theo vòng đời loader không? Nếu có, cân nhắc `STRONG`.
7. Framework có giữ `Class`, instance, `Lookup` hoặc `MethodHandle` lâu hơn dự kiến không?
8. Module và lookup có đủ quyền để định nghĩa class trong package đích không?

Bảng chọn nhanh:

| Nhu cầu | Lựa chọn |
|---|---|
| Class thông thường, cần load theo tên | Class thông thường / class loader |
| Class sinh động, không cần name lookup | Hidden class |
| Hidden class cần truy cập private member trong nest | Hidden class với `NESTMATE` |
| Hidden class có thể unload khi loader còn sống | Hidden class mặc định (weak) |
| Hidden class cần sống theo defining loader | Hidden class với `STRONG` |
| Framework cần class data gắn với implementation | `defineHiddenClassWithClassData()` |
| Plugin cần discovery bằng tên | Class thông thường |

## 15. Tài liệu tham khảo chính thức

- [JDK 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, `defineHiddenClassWithClassData`, `lookupClass` và các tùy chọn class.
- [JDK 17 API — MethodHandles.Lookup.ClassOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
- [JDK 17 API — Class.isHidden()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isHidden()): kiểm tra class có phải hidden class hay không.
- [JDK 17 API — Class.getName()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getName()): cách biểu diễn tên của hidden class.
- [JDK 17 API — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): lookup, method handle và class data.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): mục tiêu thiết kế, discoverability, lifecycle và các API hidden class được chuẩn hóa từ Java 15.

**Ghi nhớ:** Hidden class được định nghĩa từ bytecode qua `MethodHandles.Lookup`, có thể sử dụng bằng `Class<?>` và `MethodHandle`, nhưng không thể tìm lại bằng tên qua `Class.forName()` hoặc `ClassLoader.loadClass()`. Mặc định, hidden class có thể được unload độc lập với defining loader khi không còn tham chiếu mạnh; `STRONG` giữ class theo vòng đời loader. Dùng `NESTMATE` khi cần quyền truy cập private trong nest. Hidden class phù hợp cho implementation do framework sinh động, không phải class API công khai hay cơ chế bảo mật.
