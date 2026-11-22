# Thiết kế API công khai thay vì phụ thuộc nội bộ JDK

Java Reflection cho phép đọc metadata và gọi thành viên khi đáp ứng quy tắc truy cập; nó không biến mọi class nhìn thấy trong JDK thành **API được hỗ trợ lâu dài**. Trong hệ thống module Java (JPMS), một lớp có chữ `public` vẫn có thể nằm trong package không được `exports` và không được dùng như một hợp đồng công khai. Cách thiết kế bền vững là chọn API công khai có tài liệu, đặt ranh giới module rõ ràng, che giấu implementation và dùng Reflection đúng phạm vi quyền truy cập.

Bài học này thuộc chủ đề **Module và đóng gói**: ta sẽ nhận diện API JDK nội bộ, hiểu vì sao việc cưỡng ép truy cập dễ hỏng khi nâng JDK, thiết kế API ổn định cho module của chính mình, kiểm tra bằng Reflection và lập kế hoạch chuyển đổi mã đang dùng nội bộ JDK.

## 1. “Public” về cú pháp khác “public API” về hợp đồng

Một class có thể là `public class Example`, nhưng có ít nhất ba câu hỏi khác nhau:

1. **Class/member có modifier `public` không?** `Modifier.isPublic(type.getModifiers())` hoặc `Modifier.isPublic(method.getModifiers())` kiểm tra một phần metadata.
2. **Package có được module sở hữu `exports` cho module gọi không?** Với named module, JPMS kiểm tra accessibility tại ranh giới module. Package không export không trở thành API dùng trực tiếp chỉ vì class là `public`.
3. **API đó có được JDK hoặc thư viện cam kết hỗ trợ, ghi tài liệu và duy trì không?** Đây là câu hỏi về tính ổn định, khả năng tương thích và chính sách phát hành. JPMS giúp đóng gói, nhưng `exports` tự nó không phải một cam kết tương thích vô hạn.

Các namespace mang tính cảnh báo khi gặp trong ứng dụng là `jdk.internal.*`, nhiều package `sun.*`, `sun.reflect.*` hoặc `sun.security.*`. Chúng có thể thay đổi, bị đóng gói chặt hơn hoặc bị loại khỏi runtime. Một ngoại lệ đáng chú ý là một số API được tài liệu hóa trong package có tiền tố `com.sun.*`, chẳng hạn `com.sun.net.httpserver.HttpServer` thuộc module `jdk.httpserver`: **không thể chỉ dựa vào tiền tố package để kết luận API có được hỗ trợ hay không**. Hãy tra chính tài liệu API và module của phiên bản JDK mà dự án hỗ trợ.

Một ví dụ quen thuộc: mục tiêu mã hóa/giải mã Base64 nên dùng `java.util.Base64` (API chính thức), thay vì dựa vào bộ mã hóa nội bộ cũ của JDK.

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] input = "hello".getBytes(StandardCharsets.UTF_8);
String encoded = Base64.getEncoder().encodeToString(input);
byte[] decoded = Base64.getDecoder().decode(encoded);
String result = new String(decoded, StandardCharsets.UTF_8);
```

Đây là đoạn minh họa để đặt trong một phương thức. API `Base64` có hợp đồng công khai, nằm trong `java.base`; ứng dụng không cần mở package nội bộ hay dùng Reflection để mã hóa Base64.

**Nguyên tắc:** từ khóa `public` chỉ là một phần của câu chuyện. Muốn phụ thuộc lâu dài, cần kiểm tra **package được xuất khẩu cho bên dùng, khả năng truy cập thật sự và tư cách API được hỗ trợ**.

## 2. Ranh giới JPMS: requires, exports và opens

JPMS (Java Platform Module System, Java 9+) mô tả phụ thuộc và truy cập module bằng `module-info.java`.

| Khai báo hoặc cơ chế | Mục đích | Tác động đáng nhớ |
| --- | --- | --- |
| `requires com.example.lib;` | Module hiện tại đọc module `com.example.lib` | Chỉ đọc được module chưa đủ để truy cập các package không export |
| `exports com.example.lib.api;` | Mở package API cho code từ các module đọc module này | Cho phép truy cập kiểu/thành viên public theo quy tắc Java; Reflection thông thường trên API public cũng dùng được |
| `exports com.example.lib.spi to com.example.plugin;` | Export có điều kiện tới module được nêu | Module khác không được import trực tiếp package này |
| `opens com.example.lib.model;` | Cho phép truy cập Reflection sâu ở runtime | Không cấp quyền import package không export ở compile time |
| `opens com.example.lib.model to com.example.serializer;` | Mở package cho một module Reflection cụ thể | Giới hạn phạm vi mở so với `opens` không định danh |
| Không `exports`, không `opens` | Giấu chi tiết implementation | Code bên ngoài không có quyền truy cập trực tiếp hoặc truy cập Reflection sâu thông thường |

`exports` và `opens` **không thay thế nhau**:

- `exports` phục vụ API public. Đọc metadata và gọi public method trên public class thuộc package đã export có thể thực hiện qua Reflection mà không cần mở package để sửa quyền truy cập.
- `opens` cho phép các công cụ như serializer hoặc dependency injection truy cập sâu vào thành viên không public khi truy cập đó thực sự cần thiết và còn phù hợp với các kiểm tra khác. Nó **không** làm một package trở thành package được import bình thường tại compile time.
- `open module com.example.lib { ... }` mở toàn bộ package của module cho Reflection sâu. Đây là lựa chọn rộng; thường nên ưu tiên `opens package to framework.module` chính xác khi làm việc với framework.
- Một package có thể vừa `exports` vừa `opens` nếu có lý do rõ ràng cho cả hai; còn API public thông thường chỉ cần `exports`.

Đối với một class trong named module, cần xét cả việc module gọi **đọc** module sở hữu (readability), package **được export** tới bên gọi và member có quyền truy cập phù hợp. Khả năng tải `Class` bằng tên hay lấy được metadata không đồng nghĩa sẽ gọi hợp lệ được một thành viên.

### Kiểm tra xuất khẩu/mở package bằng API công khai của Module

```java
Module owner = String.class.getModule();
Module caller = MyClass.class.getModule(); // MyClass thuộc ứng dụng của bạn

boolean publicApiVisible = owner.isExported("java.lang", caller);
boolean deepReflectionAllowed = owner.isOpen("java.lang", caller);
```

Đây là đoạn minh họa, `MyClass` là lớp ứng dụng do bạn định nghĩa. Hai hàm `Module.isExported(String, Module)` và `Module.isOpen(String, Module)` phân biệt quyền export và open **đối với module gọi cụ thể**. Với JDK 17 tiêu chuẩn, `java.base` export `java.lang` nhưng không mở không điều kiện package này cho mọi ứng dụng; vì vậy đừng mặc định đọc được mọi field private của `String`.

Kiểm tra `Module.isExported` vẫn chưa đủ để kết luận một API an toàn dùng lâu dài: nó chỉ mô tả chính sách truy cập JPMS của phiên bản runtime đang xét.

## 3. Ví dụ kiến trúc: chỉ xuất khẩu API, giữ implementation trong module

Thiết kế một thư viện `com.example.greeter` với hai package:

```text
src/
├── com.example.greeter/
│   ├── module-info.java
│   └── com/example/greeter/
│       ├── api/
│       │   ├── Greeter.java
│       │   └── Greeters.java
│       └── internal/
│           └── DefaultGreeter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Mục tiêu: module ứng dụng có thể tạo dịch vụ qua factory và sử dụng interface public. Thư viện được phép thay đổi `DefaultGreeter` mà không bắt người dùng phụ thuộc vào lớp implementation.

### Tệp 1 — src/com.example.greeter/module-info.java

```java
module com.example.greeter {
    exports com.example.greeter.api;
}
```

Cố ý **không export** package `com.example.greeter.internal`. Code của chính module `com.example.greeter` vẫn dùng được class trong package đó theo quyền truy cập Java thông thường.

### Tệp 2 — src/com.example.greeter/com/example/greeter/api/Greeter.java

```java
package com.example.greeter.api;

public interface Greeter {
    String greet(String name);
}
```

### Tệp 3 — src/com.example.greeter/com/example/greeter/api/Greeters.java

```java
package com.example.greeter.api;

import com.example.greeter.internal.DefaultGreeter;

public final class Greeters {
    private Greeters() {
    }

    public static Greeter create() {
        return new DefaultGreeter();
    }
}
```

Factory trả về **interface** thay vì `DefaultGreeter`, giữ hợp đồng của bên gọi nhỏ và rõ.

### Tệp 4 — src/com.example.greeter/com/example/greeter/internal/DefaultGreeter.java

```java
package com.example.greeter.internal;

import com.example.greeter.api.Greeter;

public final class DefaultGreeter implements Greeter {
    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Từ khóa `public` của `DefaultGreeter` là cần thiết để factory ở package khác trong cùng module gọi constructor công khai. Nhưng class này vẫn không nằm trong public API **đối với module ứng dụng** vì package không được export.

### Tệp 5 — src/com.example.app/module-info.java

```java
module com.example.app {
    requires com.example.greeter;
}
```

Ứng dụng chỉ khai báo phụ thuộc vào module thư viện, rồi dùng các type từ package exported.

### Tệp 6 — src/com.example.app/com/example/app/Main.java

```java
package com.example.app;

import com.example.greeter.api.Greeter;
import com.example.greeter.api.Greeters;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Greeter service = Greeters.create();
        System.out.println(service.greet("Java"));

        Class<?> apiType = Greeter.class;
        Module owner = apiType.getModule();
        Module caller = Main.class.getModule();

        System.out.println("API type: " + apiType.getName());
        System.out.println("API module: " + owner.getName());
        System.out.println("API exported: "
                + owner.isExported("com.example.greeter.api", caller));
        System.out.println("Internal exported: "
                + owner.isExported("com.example.greeter.internal", caller));

        Method method = apiType.getMethod("greet", String.class);
        Object output = method.invoke(service, "Reflection");
        System.out.println("Reflection: " + output);
    }
}
```

### Biên dịch và chạy

Tại thư mục cha chứa `src`, chạy bằng JDK 17+:

```bash
javac --module-source-path src -d out -m com.example.greeter,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
```

Kết quả:

```text
Hello, Java
API type: com.example.greeter.api.Greeter
API module: com.example.greeter
API exported: true
Internal exported: false
Reflection: Hello, Reflection
```

**Tại sao Reflection vẫn gọi được?** `getMethod("greet", String.class)` tìm ra method public trên **interface `Greeter` thuộc package đã export**. Reflection gọi qua hợp đồng công khai; JVM dispatch đến implementation thật, dù implementation nằm trong package ẩn. Đây là một ví dụ đóng gói đúng cách: bên gọi không cần nhập hoặc thao tác Reflection sâu với `DefaultGreeter`.

Nếu thử thêm vào `Main.java`:

```java
import com.example.greeter.internal.DefaultGreeter;
```

compiler từ chối import package không export trong module `com.example.greeter`. Dù `DefaultGreeter` có modifier `public`, module `com.example.app` không được quyền phụ thuộc trực tiếp vào package này.

**Lưu ý:** mã ví dụ cung cấp đầy đủ các tệp cho modular compilation. Nó cần đúng cấu trúc thư mục và tên module. Cú pháp `--module-source-path`, `-m` và `--module-path` thuộc công cụ JDK, không phụ thuộc shell-specific command substitution.

## 4. Reflection không vượt được đóng gói của JPMS

Những thao tác dưới đây có ý nghĩa khác nhau:

```java
Class<?> type = Class.forName("java.lang.String");
java.lang.reflect.Method method =
        type.getMethod("substring", int.class);
```

`String` nằm trong `java.lang` là package public/exported của `java.base`, nên phương thức public có thể được dùng bằng API thông thường hoặc Reflection theo kiểm tra truy cập.

Còn đây là **mã minh họa kiểu truy cập không nên xây thành tính năng**:

```java
java.lang.reflect.Field internal =
        String.class.getDeclaredField("value");
internal.setAccessible(true);
```

Trên nhiều bản JDK 17+, `String` có field private tên `value`, nhưng **đừng phụ thuộc vào tên hoặc cấu trúc lưu trữ đó**: một JDK khác hoặc phiên bản sau có thể thay đổi. `getDeclaredField` có thể trả metadata, nhưng `setAccessible(true)` có thể ném `java.lang.reflect.InaccessibleObjectException` vì `java.base` không mở `java.lang` cho module gọi. Nếu field không còn tồn tại, có thể gặp `NoSuchFieldException` từ bước tìm metadata.

Hãy chọn API public phù hợp mục đích:

```java
String text = "hello";
char first = text.charAt(0);
int length = text.length();
byte[] utf8 = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
```

Các API trên biểu đạt **ý định** (ký tự, độ dài, encoding), không buộc code phải hiểu storage private của `String`.

### Các lỗi/khả năng cần phân biệt

| Hiện tượng | Nguyên nhân phổ biến | Cách xử lý hợp lý |
| --- | --- | --- |
| Compile error báo package không visible/exported | Package thuộc named module nhưng không được export cho code gọi | Dùng API xuất khẩu chính thức; điều chỉnh module descriptor nếu package thuộc dự án mình và việc export có chủ đích |
| `InaccessibleObjectException` khi `setAccessible(true)` | JPMS từ chối bật truy cập sâu tới package không open | Tránh đọc private JDK fields; với package của chính mình, `opens ... to ...` nếu có lý do |
| `IllegalAccessException` khi `Method.invoke` hoặc `Field.get` | Access check của thành viên/kiểu không thỏa | Dùng public API hợp lệ; đảm bảo receiver, quyền truy cập và module tương ứng |
| `ClassNotFoundException`/`NoSuchMethodException` | Tên class/method hoặc phiên bản triển khai khác với giả định | Không ghim tên internal; dùng API documented và cơ chế phát hiện capability rõ ràng |
| `Class.forName(name)` thành công nhưng invoke thất bại | Class loading và quyền truy cập member là hai bước khác nhau | Không coi việc tải class là “đã được phép sử dụng API” |

`AccessibleObject.trySetAccessible()` (Java 9+) trả về `false` khi không bật truy cập được, thay vì luôn ném exception cho thất bại quyền truy cập; các lỗi khác vẫn có thể xảy ra. Dùng nó để viết code chẩn đoán dễ kiểm soát lỗi, **không phải** để thăm dò rồi cưỡng ép encapsulation của JDK.

## 5. API thay thế phù hợp cho những nhu cầu thường gặp

| Nhu cầu thực tế | Ví dụ phụ thuộc không nên mặc định dùng | Hướng public API nên xem xét |
| --- | --- | --- |
| Mã hóa/giải mã Base64 | Bộ giải mã Base64 nội bộ JDK đời cũ | `java.util.Base64` |
| Atomic update hoặc truy cập biến có memory semantics cụ thể | `sun.misc.Unsafe` chỉ để CAS/read/write field | `java.util.concurrent.atomic` hoặc `java.lang.invoke.VarHandle` khi phù hợp |
| Gọi method/constructor, khám phá metadata | Hack quyền truy cập với `sun.reflect.*` | `java.lang.reflect`, `java.lang.invoke.MethodHandles`, constructor/factory public |
| Tính toán mật mã, chữ ký và secure random | Implementation trực tiếp dưới `sun.security.*` | `java.security`, `javax.crypto`, nhà cung cấp thuật toán qua chuẩn JCA/JCE |
| Truy cập thông tin JVM và môi trường | Đọc field private của lớp runtime JDK | `Runtime`, `ManagementFactory`, `java.lang.management` theo dữ liệu cần |
| Xử lý nội dung `String` | Đọc private `String.value` | `String.charAt`, `codePoints`, `getBytes(Charset)`, `length` |
| Cơ chế tải file, tài nguyên và module | Can thiệp cấu trúc nội bộ class loader | `ClassLoader.getResource*`, `Class.getResource*`, `Module`, `ServiceLoader` theo mục tiêu |

Bảng là **định hướng theo mục đích**, không khẳng định từng API thay thế hoàn toàn mọi khả năng của internal API. Chẳng hạn `sun.misc.Unsafe` có nhiều nhóm tính năng khác nhau; cần phân loại việc sử dụng thực tế để chọn `VarHandle`, atomic classes, API foreign function/memory được hỗ trợ trên JDK mục tiêu, hoặc thiết kế lại.

Tương tự, `MethodHandles.privateLookupIn` là API public nhưng **không phải đường vòng qua quyền module**: để tạo private lookup cho lớp ở module khác, các điều kiện module/open package vẫn phải được đáp ứng. Không thiết kế thư viện bằng giả định lookup có thể truy cập mọi private JDK class.

## 6. Hai cờ khởi chạy thường gây hiểu nhầm: add-exports và add-opens

JDK có các cờ tương thích/chẩn đoán được dùng trong một số hệ thống cũ:

```bash
# Ví dụ dạng cú pháp, không phải cấu hình khuyến nghị lâu dài:
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp app.jar com.example.Main

java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
```

- `--add-exports module/package=target` mở quyền truy cập package ở mức **API public** đối với target được chỉ định. Nó thường được dùng tạm khi code cần import/link tới public types trong package vốn không export.
- `--add-opens module/package=target` mở package đối với **Reflection sâu** ở runtime, ví dụ cho phép framework cũ thử truy cập private members. Cờ này không biến private member thành public compile-time API.
- `ALL-UNNAMED` áp dụng cho các unnamed modules (thường là code chạy trên classpath). Với named module, target nên là **tên module cụ thể**. Việc mở quyền có thể cần cấu hình tương ứng cả compile time và runtime, tùy trường hợp.
- Cờ mở quyền **không sửa hợp đồng API** và không bảo đảm internal class/method vẫn tồn tại hoặc giữ semantics sau nâng JDK.
- Với Java 17, cơ chế nới truy cập tổng quát `--illegal-access` của thời Java 9–16 đã trở nên lỗi thời/không còn hiệu lực nới encapsulation. Không dùng nó làm giải pháp cho môi trường Java 17+.

Một rule thiết kế thực dụng: nếu hệ thống chỉ chạy được khi mở `java.base/java.lang` để đọc field private của `String`, hãy ghi nhận đó là **nợ tương thích** và thay code bằng API public trước khi coi quá trình migration hoàn tất.

Nếu framework thật sự cần Reflection vào **class do bạn sở hữu**, khai báo module có chủ đích:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.serializer;
}
```

Đây là ví dụ module descriptor **minh họa**; module `com.example.serializer` phải hiện diện trong đồ thị module khi build/run tương ứng. Nó bảo vệ hợp đồng API xuất khẩu, đồng thời chỉ trao quyền Reflection sâu vào package model cho serializer được nêu. Không nên “mở toàn bộ” chỉ để tránh phải xác định package thật sự cần truy cập.

## 7. Phát hiện phụ thuộc nội bộ JDK trước khi nâng phiên bản

Một bước quan trọng là xác định phụ thuộc theo **cả hai hướng tĩnh và động**.

### Quét tĩnh bằng jdeps

Trên JDK có công cụ `jdeps`, quét file JAR ứng dụng:

```bash
jdeps --jdk-internals app.jar
```

Tùy cấu trúc ứng dụng, bổ sung classpath/module-path cho các thư viện phụ thuộc để `jdeps` phân tích chính xác hơn. Với multi-release JAR, có thể chỉ định phiên bản mục tiêu, ví dụ `--multi-release 17`. `jdeps --jdk-internals` báo các phụ thuộc tĩnh đáng chú ý tới JDK internal API và trong nhiều trường hợp gợi ý API công khai thay thế.

**Giới hạn:** `jdeps` phân tích bytecode và phụ thuộc có thể quan sát tĩnh, nên có thể **bỏ sót truy cập xây tên class bằng chuỗi và Reflection**, code sinh động, plugin nạp về sau hoặc native integration. Không coi kết quả `jdeps` rỗng là bằng chứng toàn bộ đường chạy không dùng internals.

### Rà soát Reflection và cấu hình runtime

Tìm trong chính code/cấu hình dự án:

- Chuỗi tên package `sun.`, `jdk.internal.`, `sun.reflect.`, cùng những lời gọi `Class.forName`/`getDeclared*`/`setAccessible` tới class của JDK.
- Các VM flags `--add-opens`, `--add-exports`; xác định nơi nào đang cần chúng và mục tiêu cụ thể.
- Thư viện JSON, ORM, DI, bytecode agent, proxy hoặc plugin cũ: chúng có thể dùng Reflection sâu trong code bên thứ ba dù code ứng dụng không gọi trực tiếp.
- Các kịch bản chạy quan trọng: module-path so với classpath, test, dev, CI và môi trường production có thể có tập flags khác nhau.

Khi tìm thấy dependency, hãy ghi rõ **mục đích nghiệp vụ**, API nội bộ cụ thể, thay thế public và mức độ rủi ro nâng phiên bản. Đây là cách tránh “chữa” mọi chỗ bằng cùng một flag rồi bỏ sót vấn đề thiết kế.

## 8. Thiết kế API bền vững cho thư viện Java của chính bạn

Các nguyên tắc giúp lớp nội bộ có thể thay đổi mà ứng dụng sử dụng không phải sửa theo:

1. **Định nghĩa hợp đồng trước:** export package `api` chứa interface, factory, record/DTO hoặc class ổn định. Chỉ trả về kiểu có thể truy cập từ bên gọi. Tránh để public method trả về kiểu nội bộ mà consumer không thể gọi tên hoặc xử lý đúng.
2. **Ẩn implementation thực tế:** package `internal`/`impl` không export; khởi tạo qua factory hoặc dependency injection công khai. Đừng hướng dẫn consumer `Class.forName("...internal...")`.
3. **Chỉ mở Reflection tối thiểu:** package nào cần serializer/DI đọc private fields thì cân nhắc `opens ... to ...` cho đúng module. Nếu có thể thiết kế constructor, accessor hoặc adapter public thay cho deep reflection thì API sẽ dễ bảo trì hơn.
4. **Không xuất khẩu ngẫu nhiên package nội bộ chỉ để sửa lỗi biên dịch:** việc thêm `exports` sẽ biến chi tiết implementation thành thứ consumer có thể phụ thuộc. Mọi lần tái cấu trúc package này về sau có thể gây lỗi.
5. **Dùng `ServiceLoader` khi cần plugin/extensibility:** nhà cung cấp có thể được cấu hình bằng `provides ... with ...`, còn bên tiêu thụ dùng `uses ...` và interface service phù hợp. Không bắt caller nhận biết implementation private bằng tên class cố định.
6. **Giữ API tương thích có chủ đích:** khi thay signature, kiểu trả về, yêu cầu module hoặc hành vi được tài liệu hóa, đánh giá tương thích nguồn/nhị phân và kiểm thử consumer. Từ “public” một mình không bảo đảm tương thích.
7. **Đặt chính sách hỗ trợ rõ:** chỉ dựa vào API công khai của phiên bản Java tối thiểu đã công bố; tránh ngầm yêu cầu phiên bản mới hơn qua reflection vào class không có trong baseline.

Trong ví dụ ở mục 3, nếu `DefaultGreeter` chuyển từ tạo chuỗi trực tiếp sang dùng tài nguyên cấu hình, caller vẫn chỉ nhìn thấy `Greeter.greet(String)`. Đây là lợi ích của abstraction kết hợp encapsulation JPMS.

## 9. Migration theo từng bước: từ implementation detail sang hợp đồng

Giả sử một codebase đang dùng Reflection để lấy trực tiếp backing array của `String` rồi xử lý byte. Khi nâng JDK, thao tác này có thể thất bại do field/private layout thay đổi hoặc do `java.base/java.lang` không open.

Quy trình:

1. **Phân tích ý định:** cần duyệt ký tự, Unicode code point, UTF-8 bytes hay chỉ độ dài? Đó là các yêu cầu khác nhau, nên không thể thay tất cả bằng cùng một API.
2. **Chọn API công khai:** `charAt` duyệt UTF-16 code units; `codePoints` làm việc theo Unicode code points; `getBytes(StandardCharsets.UTF_8)` tạo mảng byte UTF-8; `length` cho số UTF-16 code units. Không lẫn code point count với `length()`.
3. **Thay phụ thuộc nội bộ và loại bỏ mở quyền không cần thiết:** xóa reflection hack, cờ `--add-opens` nếu không còn caller nào cần.
4. **Kiểm chứng đúng hành vi:** thêm test với ký tự ngoài BMP, null input nếu nghiệp vụ có, encoding và hiệu năng thực tế nếu đây là đường nóng. Không giả định backing array nội bộ có encoding hoặc bố cục cố định.
5. **Kiểm chứng môi trường deployment:** chạy trên JDK tối thiểu đã hỗ trợ, thử module-path khi module hóa, chạy toàn bộ luồng tích hợp có plugin/agent.
6. **Giám sát tương thích:** dùng `jdeps --jdk-internals` trong quy trình kiểm tra bản build khi phù hợp và review các VM flags mới được thêm.

Với một dependency bên thứ ba bắt buộc dùng internals, ưu tiên nâng lên phiên bản thư viện có hỗ trợ JDK mục tiêu hoặc thay thư viện. Cờ mở module chỉ nên là **biện pháp tạm có phạm vi và kế hoạch gỡ**, nếu vận hành thật sự đòi hỏi.

## 10. Lỗi thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| “Class `public` nghĩa là public API” | JPMS còn kiểm tra export; API có thể chỉ là implementation detail | Xem tài liệu hỗ trợ, module sở hữu, package export và mục đích API |
| “`Class.forName` thành công nghĩa là gọi được mọi method” | Class loading tách biệt với quyền access/reflection | Chỉ gọi public method trên API được export hoặc mở quyền có chủ đích cho code mình sở hữu |
| Dùng `setAccessible(true)` cho `java.base` rồi cho rằng nó luôn hoạt động | Strong encapsulation có thể gây `InaccessibleObjectException` | Dùng `String`/collections/JCA/JDK APIs public thay cho private fields |
| Dùng `--add-opens` để sửa lỗi import package không export | Opens chỉ phục vụ reflection runtime, không cấp quyền compile-time import | Thiết kế exported public API; phân biệt với `--add-exports` |
| Thêm `--add-exports` vĩnh viễn | Vẫn khóa chặt ứng dụng vào package nội bộ | Di chuyển sang supported API, giới hạn workaround |
| Tự động thay `Unsafe` bằng một API bất kỳ | Những tính năng khác nhau đòi hỏi giải pháp khác nhau | Phân loại thao tác, chọn `VarHandle`, atomic API hoặc giải pháp phù hợp |
| Coi tên `com.sun.*` đều nội bộ | Một số API dạng này được JDK công bố và tài liệu hóa | Đánh giá theo module/tài liệu, không theo tiền tố đơn thuần |
| Chỉ chạy `jdeps` rồi tuyên bố không phụ thuộc internal API | Reflection động và native có thể không hiện trong static dependency | Kết hợp code review, cấu hình, integration test và jdeps |
| Exports toàn bộ `impl` vì consumer muốn import một class | Đưa implementation thành phụ thuộc của client | Dùng factory/service interface/DTO trong package `api` |
| Dùng `opens` rộng toàn module vì framework | Nới quyền Reflection quá mức cần thiết | Ưu tiên mở package cụ thể, qualified `opens ... to ...` nếu phù hợp |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `public class DefaultGreeter` ở package không export có thể import từ named module khác chỉ vì class có modifier `public` không?

**Trả lời:** Không. JPMS kiểm tra quyền export của package đối với module gọi; modifier `public` không đủ.

**Câu 2.** `exports package` khác `opens package` ở đâu?

**Trả lời:** `exports` cung cấp quyền truy cập API public từ các module đọc được module sở hữu; `opens` cho phép Reflection sâu tại runtime theo phạm vi mở. `opens` một mình không cấp quyền import thông thường ở compile time.

**Câu 3.** Trong ví dụ `Greeter`, vì sao `method.invoke(service, "Reflection")` hoạt động khi implementation không export?

**Trả lời:** `Method` là thành viên public thuộc interface `Greeter` ở package API được export. JVM dispatch lời gọi instance đến implementation ẩn bên trong module, nên không cần mở package implementation cho caller.

**Câu 4.** `--add-opens java.base/java.lang=ALL-UNNAMED` có biến việc đọc private field `String` thành thiết kế API tốt không?

**Trả lời:** Không. Nó chỉ nới quyền Reflection cho target được chỉ định, không biến representation private thành hợp đồng public ổn định.

**Câu 5.** `jdeps --jdk-internals` không báo gì có nghĩa ứng dụng không dùng internals?

**Trả lời:** Không chắc. Mã có thể tạo tên class ở runtime, gọi Reflection theo chuỗi, nạp plugin hay thực hiện thao tác native ngoài phạm vi phân tích phụ thuộc tĩnh.

**Câu 6.** Có thể dùng `Modifier.isPublic(type.getModifiers())` làm tiêu chí duy nhất để xác nhận “API được hỗ trợ” không?

**Trả lời:** Không. Cần xem module, quyền export, tài liệu, phiên bản Java mục tiêu và chính sách tương thích.

**Ghi nhớ:** Reflection là công cụ khám phá/call metadata trong giới hạn truy cập Java, còn **API công khai** là ranh giới hợp đồng của hệ thống. Hãy dùng supported JDK APIs, export đúng package API của mình, giữ implementation không export và mở Reflection sâu chỉ khi thật sự có nhu cầu hợp lệ.