# Named module, unnamed module và open module trong Java Reflection

## 1. Mục tiêu và bối cảnh

Từ Java 9, **Java Platform Module System (JPMS)** bổ sung ranh giới module bên cạnh package, class và access modifier. Hai lớp đều là `public` chưa chắc có thể được truy cập từ bất kỳ module nào: ngoài quyền truy cập ở cấp Java, JVM còn xét **đồ thị module**, khả năng đọc module (`readability`), gói được **export** và gói được **open** cho Reflection.

Khi làm việc với `Class<?>`, `Method`, `Field` và `Constructor`, ba khái niệm cần phân biệt:

- **Named module**: module có tên, thường được khai báo bằng `module-info.java`; các JAR dạng *automatic module* trên module path cũng là named module.
- **Unnamed module**: module không có tên, chứa class được nạp từ **class path**; mỗi class loader có unnamed module của riêng nó.
- **Open module**: một **loại named module** được khai báo bằng `open module ...`; mọi package thuộc module đó được mở cho deep reflection ở runtime.

Ba thuật ngữ không cùng một trục phân loại: **open module là named module**, còn unnamed module là một dạng module riêng. Cần phân biệt thêm chỉ thị `opens package.name` trong một named module thông thường với việc biến **toàn bộ** module thành `open module`.

Sau bài này, bạn có thể đọc metadata module qua Reflection, cấu hình `module-info.java` đúng cho cả API công khai và thư viện dùng Reflection, giải thích lỗi `InaccessibleObjectException` và quyết định khi nào dùng `exports`, `opens`, `open module` hoặc tùy chọn dòng lệnh `--add-opens`.

## 2. JPMS nằm ở đâu trong quá trình truy cập?

Ví dụ có hai module:

```text
com.example.inspector
    |
    | requires com.example.target   (đọc module)
    v
com.example.target
    ├── com.example.target.api
    │       exports ...             (API công khai)
    └── com.example.target.internal
            opens ... to com.example.inspector
                                    (deep reflection được cấp phép)
```

Trong sơ đồ, `requires` thiết lập quan hệ đọc, `exports` cấp quyền sử dụng public API với điều kiện Java/module phù hợp, còn `opens` cho phép deep reflection trong phạm vi được mở. Mở package cho Reflection **không tự cho phép import** public type của package ấy lúc biên dịch.

Điểm riêng của bài này là **chính sách mặc định theo loại module**: unnamed module trên classpath, explicit named module, automatic module và explicit open module. Các module có thể hỗ trợ Reflection theo cách khác nhau dù source Java của caller không thay đổi.

## 3. Bảng so sánh chính xác

| Đặc điểm | Explicit named module thông thường | Unnamed module | Explicit open module |
| --- | --- | --- | --- |
| Cách tạo điển hình | `module name { ... }` trong `module-info.java` | Class/JAR trên `--class-path` hoặc `-cp` | `open module name { ... }` trong `module-info.java` |
| `Module.isNamed()` | `true` | `false` | `true` |
| `Module.getName()` | Tên module | `null` | Tên module |
| Quyền export package | Theo `exports` (và quy tắc truy cập runtime thích hợp) | Mọi package được export | Mọi package mở ở runtime, nhưng **không mặc nhiên là API được export để compile** |
| Deep reflection giữa module | Chỉ package được `opens` phù hợp, hoặc trường hợp truy cập đã được cho phép | Mọi package được mở | Mọi package được mở |
| Giao diện bảo vệ bằng `module-info.java` | Có, theo từng package | Không có descriptor nguồn riêng | Có, nhưng mở toàn bộ package |
| Use case | Library/application thiết kế API và Reflection có chọn lọc | Ứng dụng legacy classpath | Ứng dụng/module chủ ý cho phép framework truy cập Reflection rộng |

### 3.1. Explicit named module

Một module tên `com.example.target` có thể khai báo:

```java
module com.example.target {
    exports com.example.target.api;
    opens com.example.target.internal to com.example.inspector;
}
```

- `exports com.example.target.api;` cho phép module đọc phù hợp dùng public API của package này.
- `opens com.example.target.internal to com.example.inspector;` mở package internal **chỉ cho module được nêu** để deep reflection.
- Những package không export và không open được **đóng gói mạnh** đối với module bên ngoài.
- Có thể viết `exports p to m1, m2;` để export có điều kiện hoặc `opens p;` để mở cho mọi module tại runtime.

Với một module muốn sử dụng API:

```java
module com.example.inspector {
    requires com.example.target;
}
```

Lệnh `requires` tạo readability, nhưng **không tự mở** trường private của package bên target.

### 3.2. Unnamed module

Mọi class nằm trên classpath và được nạp bởi một class loader thuộc về unnamed module của class loader đó. Chạy chương trình dạng:

```bash
java -cp classes UnnamedDemo
```

thường có `UnnamedDemo.class.getModule().isNamed() == false` và `getName() == null`.

Unnamed module **đọc được mọi named module có thể quan sát được**, và export/open mọi package của nó. Đây là cơ chế tương thích để nhiều ứng dụng classpath cũ vẫn chạy. Tuy nhiên, việc một class nằm trong unnamed module **không** tự cho phép nó vượt ranh giới private của các named module khác; muốn phản chiếu vào package đóng của named module, phía **named module đích** phải mở gói hoặc runtime phải được cấu hình tương đương.

Chú ý: không có nghĩa tất cả lớp trong toàn bộ JVM đều nằm trong một unnamed module duy nhất. `ClassLoader.getUnnamedModule()` cho biết unnamed module của một class loader cụ thể.

### 3.3. Open module

Nếu mọi package của module được thiết kế cho deep reflection, có thể khai báo:

```java
open module com.example.target {
    exports com.example.target.api;
}
```

- `open module` mở **tất cả package của module** cho runtime Reflection.
- Các chỉ thị `exports` vẫn cần thiết để thiết kế compile-time API; từ khóa `open` **không** thay cho mọi `exports` ở cấp biên dịch.
- **Không được đặt chỉ thị `opens package.name;` trong body của `open module`**, vì toàn bộ package đã mở.
- Module vẫn có **tên**, có thể khai báo `requires`, `exports`, `uses`, `provides` và tham gia đồ thị module.

Chỉ nên dùng `open module` nếu việc mở toàn bộ package là chủ đích. Với thư viện lớn, `opens một.vài.package to module.framework` thường giúp giữ ranh giới ổn định hơn.

### 3.4. Automatic module là một named module khác cần biết

Một JAR không có `module-info.class` khi đặt trên module path có thể trở thành **automatic module**, tên được lấy theo metadata `Automatic-Module-Name` hoặc suy ra từ tên JAR. Automatic module có `isNamed() == true`, export và mở các package của mình; nó không đồng nhất với unnamed module chỉ vì không có `module-info.java`.

Dùng `Module.getDescriptor().isAutomatic()` khi cần xác định automatic module. Trên explicit named module, có thể dùng `Module.getDescriptor().isOpen()` để xác định khai báo `open module`. Với unnamed module, `getDescriptor()` trả `null`, vì vậy phải kiểm tra trước khi gọi các phương thức trên descriptor.

**Ba tình huống runtime điển hình:** classpath → unnamed module; modular JAR rõ `module-info.class` → explicit named module; JAR không có descriptor trên module path → automatic named module.

## 4. Reflection API liên quan

| API | Ý nghĩa thực tế |
| --- | --- |
| `Class.getModule()` | Tìm module chứa kiểu được phản chiếu. |
| `Module.isNamed()` | Kiểm tra module có tên không. |
| `Module.getName()` | Tên module; `null` với unnamed module. |
| `Module.getDescriptor()` | Metadata `ModuleDescriptor`; `null` nếu unnamed module. |
| `Module.canRead(Module other)` | Module hiện tại có quan hệ đọc được `other` hay không. |
| `Module.isExported(String pkg)` | Package được export **không giới hạn bên nhận** theo ngữ nghĩa runtime hay không. |
| `Module.isExported(String pkg, Module other)` | Package được truy cập/export ở runtime đối với module `other` hay không; **opens có thể khiến kết quả là true**. |
| `Module.isOpen(String pkg)` | Package được mở không giới hạn bên nhận tại runtime hay không. |
| `Module.isOpen(String pkg, Module other)` | Package được mở cho module `other` hay không. |
| `AccessibleObject.setAccessible(true)` | Yêu cầu bỏ qua một số kiểm tra truy cập ngôn ngữ; JPMS vẫn có thể từ chối với `InaccessibleObjectException`. |
| `AccessibleObject.trySetAccessible()` | Cố gắng bật quyền truy cập; trả `false` nếu không thể bật vì các kiểm tra truy cập. |

Lưu ý khi chẩn đoán:

- Một package `opens p to m` có thể làm cả `isOpen(p, m)` và **`isExported(p, m)`** trả `true` ở runtime. Điều này **không chứng minh** descriptor có chỉ thị `exports p to m`; hãy đọc `ModuleDescriptor.exports()` nếu cần phân tích **khai báo**.
- Với `isOpen(pkg, thisSameModule)`, kết quả có thể là `true` vì module có quyền truy cập chính nó. Để kiểm tra quyền của framework bên ngoài, phải truyền **đúng module của framework**, không dùng module nguồn làm đối số thứ hai.
- `Module.isOpen(String pkg)` và overload nhận module khác nhau: một lệnh `opens p to m` là **qualified opening**, nên `isOpen(p)` vẫn có thể là `false`, còn `isOpen(p, m)` là `true`.
- `Class.getModule()` hoạt động với các lớp Java thông thường; đối với kiểu mảng, module tương ứng là module của kiểu thành phần; kiểu nguyên thủy và `void` thuộc `java.base` theo API.
- `ModuleLayer.boot()` cung cấp layer của named modules được resolve tại khởi động; unnamed modules không phải một mục để tra như named module trong layer.

## 5. Ví dụ Java 17+ độc lập: named module mở một package cho Reflection

Ta tạo **hai named module**: `com.example.target` chứa dữ liệu và `com.example.inspector` đọc dữ liệu đó bằng Reflection. Cấu trúc thư mục:

```text
src/
├── com.example.target/
│   ├── module-info.java
│   └── com/example/target/
│       ├── api/PublicApi.java
│       └── internal/Secret.java
└── com.example.inspector/
    ├── module-info.java
    └── com/example/inspector/Inspector.java
```

### 5.1. Mã nguồn module target

File **`src/com.example.target/module-info.java`**:

```java
module com.example.target {
    exports com.example.target.api;
    opens com.example.target.internal to com.example.inspector;
}
```

File **`src/com.example.target/com/example/target/api/PublicApi.java`**:

```java
package com.example.target.api;

public class PublicApi {
    public static String greeting() {
        return "hello";
    }
}
```

File **`src/com.example.target/com/example/target/internal/Secret.java`**:

```java
package com.example.target.internal;

public class Secret {
    private final String value = "jpms";
}
```

Lớp `Secret` được khai báo `public` để ví dụ tập trung vào module boundary; **trường `value` là private** và package `internal` không có chỉ thị `exports`. Để đọc trường, module inspector phải dùng deep reflection, nhờ `opens ... to ...`.

### 5.2. Mã nguồn module inspector

File **`src/com.example.inspector/module-info.java`**:

```java
module com.example.inspector {
    requires com.example.target;
}
```

File **`src/com.example.inspector/com/example/inspector/Inspector.java`**:

```java
package com.example.inspector;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Inspector {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("com.example.target.internal.Secret");

        Module target = type.getModule();
        Module inspector = Inspector.class.getModule();

        System.out.println("inspector named=" + inspector.isNamed());
        System.out.println("target named=" + target.isNamed());
        System.out.println("target name=" + target.getName());

        String internal = "com.example.target.internal";
        System.out.println("internal open to inspector="
                + target.isOpen(internal, inspector));
        System.out.println("internal unqualified export="
                + target.isExported(internal));
        System.out.println("internal runtime export to inspector="
                + target.isExported(internal, inspector));

        Constructor<?> ctor = type.getDeclaredConstructor();
        ctor.setAccessible(true);
        Object instance = ctor.newInstance();

        Field field = type.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println("secret=" + field.get(instance));
    }
}
```

### 5.3. Biên dịch, chạy và quan sát stdout

Đứng ở thư mục chứa `src/`, chạy bằng JDK 17 hoặc cao hơn:

```bash
javac --release 17 -d mods --module-source-path src -m com.example.target,com.example.inspector
java --module-path mods -m com.example.inspector/com.example.inspector.Inspector
```

Kết quả:

```text
inspector named=true
target named=true
target name=com.example.target
internal open to inspector=true
internal unqualified export=false
internal runtime export to inspector=true
secret=jpms
```

Các file trong ví dụ đã được biên dịch với `javac --release 17` và chạy thành công trên JDK 21, stdout khớp nội dung trên.

**Giải thích:**

1. `Inspector` và `Secret` đều thuộc named module.
2. `Class.forName` tìm lớp bằng tên trong môi trường đã resolve module; điều này **không đồng nghĩa** mã Java ở module inspector được phép `import Secret` vì package `internal` không export như compile-time API.
3. `isOpen(internal, inspector) == true` vì target khai báo **qualified opens** cho `com.example.inspector`.
4. `isExported(internal) == false` vì package không được export/open **vô điều kiện** trong trường hợp này.
5. `isExported(internal, inspector) == true` là điểm dễ bất ngờ: khi package được mở tới inspector, API phản ánh quyền truy cập runtime, dù source không có `exports internal`. Đây **không phải** bằng chứng rằng `import Secret` được trình biên dịch Java chấp nhận.
6. `setAccessible(true)` trên constructor và private field thành công nhờ package được mở cho **đúng module caller**, nên in `secret=jpms`.

### 5.4. Thử thay đổi quyền để hiểu lỗi

Nếu xóa dòng `opens com.example.target.internal to com.example.inspector;` rồi biên dịch lại, các thao tác `setAccessible(true)` vào non-public member của `Secret` từ module inspector **không còn được cho phép**. Chương trình sẽ thất bại với `java.lang.reflect.InaccessibleObjectException` khi cố bật khả năng truy cập, trừ khi bạn cấp quyền mở bằng cơ chế khác.

Nếu thay bằng:

```java
module com.example.target {
    exports com.example.target.api;
    opens com.example.target.internal;
}
```

package `internal` được mở **cho mọi module**, thay vì chỉ riêng inspector.

Nếu thay khai báo module bằng:

```java
open module com.example.target {
    exports com.example.target.api;
}
```

toàn bộ package trong target sẽ được mở cho deep reflection, bao gồm `internal`. Các chỉ thị `exports` vẫn là chính sách public API ở mức compile-time. Khi chạy biến thể `open module`, một số phép hỏi `isExported(...)` tại runtime có thể thay đổi so với biến thể chỉ mở có điều kiện, vì quyền runtime đã mở rộng.

**Quan trọng:** mỗi biến thể `module-info.java` phía trên là **một cấu hình thay thế**, không ghép tất cả lại vào cùng file.

## 6. Ví dụ unnamed module trên classpath

Một chương trình Java 17+ ngắn có thể xác nhận module của mã classpath.

File **`UnnamedDemo.java`**:

```java
public class UnnamedDemo {
    public static void main(String[] args) {
        Module module = UnnamedDemo.class.getModule();

        System.out.println("named=" + module.isNamed());
        System.out.println("name=" + module.getName());
    }
}
```

Chạy:

```bash
javac --release 17 UnnamedDemo.java
java -cp . UnnamedDemo
```

Output:

```text
named=false
name=null
```

Cũng là mã nguồn trên, nhưng khi ứng dụng được đóng gói thành module tường minh trên module path và chạy bằng `-m`, `Class.getModule()` sẽ phản ánh **named module chứa class** tương ứng.

Đặc biệt, không nên xem `getName() == null` như tên chuỗi `"null"`: API thực sự trả về giá trị Java `null` cho unnamed module; chỉ phép nối chuỗi trong `println` mới biến nó thành chữ `null` trong stdout.

## 7. Di chuyển ứng dụng legacy và xử lý lỗi deep reflection

### 7.1. `InaccessibleObjectException` khác `IllegalAccessException` như thế nào?

Khi công cụ Reflection gọi `field.setAccessible(true)` từ module A tới private field trong module B nhưng package đích không open cho A, việc **bật quyền truy cập** có thể ném `InaccessibleObjectException` (unchecked).

Nếu không bật được quyền và vẫn gọi `Field.get(...)` hoặc `Method.invoke(...)` trong tình huống không được phép, thao tác truy cập có thể gặp `IllegalAccessException` (checked) theo API tương ứng.

Hãy phân biệt **lỗi khi yêu cầu vượt kiểm tra** với **lỗi khi thực hiện truy cập**. Chỉ đổi sang `trySetAccessible()` không làm quyền module rộng hơn: API này giúp thăm dò bằng `boolean` thay vì luôn yêu cầu quyền bằng `setAccessible(true)`.

Ví dụ minh họa có chủ đích (không phải chương trình độc lập):

```java
Field field = targetClass.getDeclaredField("value");
if (field.trySetAccessible()) {
    Object value = field.get(targetObject);
    // xử lý value
} else {
    // yêu cầu mở package đúng module từ phía chủ sở hữu
}
```

Đừng mặc định `setAccessible(true)` sẽ vượt qua JPMS chỉ vì ứng dụng đang chạy với quyền hệ điều hành cao.

### 7.2. Cấu hình mở package mà không đổi source module

Khi module target thuộc thư viện hoặc JDK không thể sửa ngay, runtime có tùy chọn tạm thời:

```bash
java --add-opens com.example.target/com.example.target.internal=com.example.inspector --module-path mods -m com.example.inspector/com.example.inspector.Inspector
```

Cú pháp:

```text
--add-opens <module-nguồn>/<package>=<module-nhận>
```

Nếu ứng dụng gọi Reflection thuộc unnamed module trên classpath, đích thường là `ALL-UNNAMED`:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp classes UnnamedDemo
```

Lệnh này minh họa **cú pháp** mở package `java.lang` của `java.base` cho các unnamed modules; chương trình `UnnamedDemo` ở trên không thực sự cần quyền đó. Đừng thêm tùy chọn chỉ vì thấy ví dụ: phải xác định **đúng module/package đang chặn** và **module caller**.

Các tùy chọn khác có chức năng **khác nhau**:

- `--add-exports nguồn/package=đích` mở quyền truy cập tới public types/members ở runtime; **không phải** thay thế tổng quát cho deep reflection vào private members.
- `--add-reads nguồn=đích` bổ sung quan hệ readability, nhưng **không tự export/open** package.
- `--add-opens nguồn/package=đích` mở package để Reflection có thể yêu cầu quyền truy cập sâu từ module được chỉ định.

Từ Java 17, `--illegal-access` không còn là cơ chế giúp vượt qua strong encapsulation của JDK. Đối với ứng dụng hiện đại, nên ưu tiên API công khai hoặc `opens` có phạm vi vừa đủ thay vì dựa vào tùy chọn toàn cục hoặc truy cập nội bộ của JDK.

### 7.3. Mở package có thực sự an toàn và cần thiết?

Nhiều framework DI, serialization, ORM hay testing phải quan sát constructor, annotation, field hoặc setter qua Reflection. Tuy vậy, **không phải mọi framework đều cần private reflective access**. Có framework chỉ dùng public API, code generation hoặc module-specific integration.

Khi quyết định, nên hỏi:

1. Framework thật sự dùng package nào và chạy trong **named hay unnamed module**?
2. Nó chỉ cần public types/members hay cần đặt `accessible` cho private member?
3. Có thể dùng `opens p to framework.module` để giới hạn module nhận không?
4. Có cần `exports p` cho mã Java thường biên dịch tham chiếu trực tiếp vào API không?
5. Trong triển khai thực tế, tên module của framework có được xác nhận từ `Class.getModule().getName()` hay chưa?

Đây là lý do `open module` đôi khi thuận tiện cho ứng dụng được framework quản lý toàn phần, nhưng không phải lựa chọn mặc định cho một thư viện muốn giữ package nội bộ kín.

## 8. Chẩn đoán lỗi theo tình huống

| Triệu chứng | Khả năng liên quan đến module | Cách kiểm tra |
| --- | --- | --- |
| Không `import` được public class từ module khác | Thiếu `requires` hoặc package không `exports` đúng đối tượng | Xem hai `module-info.java` và module path lúc compile |
| `setAccessible(true)` ném `InaccessibleObjectException` | Package không `opens` cho module gọi | In `targetClass.getModule()` và `callerClass.getModule()`, kiểm tra `isOpen(package, callerModule)` |
| `Class.getModule().getName()` trả `null` | Class ở unnamed module | Kiểm tra `isNamed()`, classpath và class loader |
| Một JAR không có `module-info.java` nhưng `isNamed()==true` | JAR được dùng như automatic module trên module path | Kiểm tra `getDescriptor().isAutomatic()` |
| `open module` mà compile vẫn báo package không visible | Package không được `exports` để compile | Khai báo `exports` cho API cần công khai, tách với `opens` |
| Reflective access hoạt động ở classpath nhưng lỗi khi chuyển sang module path | Thay đổi ranh giới strong encapsulation | Xem package đích cần `opens`, đích của `opens ... to ...` và cấu hình launch |

Các tình huống không phải lỗi JPMS cũng có thể gây `ClassNotFoundException`, `NoClassDefFoundError` hay `IllegalAccessException`. Đừng sửa `module-info.java` một cách suy đoán: kiểm tra tên kiểu, class loader, module resolution, stack trace và đúng API phát sinh lỗi.

## 9. Lỗi thường gặp và cách tránh

**Lỗi 1: Cho rằng unnamed module và open module giống nhau.** Unnamed module không có tên, gắn với class loader/classpath. Open module là named module khai báo mở toàn bộ package. Cả hai có tính mở rộng cho Reflection ở runtime, nhưng cách cấu hình và quan hệ module khác nhau.

**Lỗi 2: Cho rằng named module chỉ có dạng có `module-info.java`.** Automatic module trên module path cũng là named module. Đọc `getDescriptor().isAutomatic()` trước khi kết luận nguồn gốc module.

**Lỗi 3: Cho rằng `exports` cho phép truy cập mọi private field.** `exports` dành cho API công khai và normal access; cần `opens` thích hợp nếu muốn `setAccessible(true)` với private members từ module ngoài.

**Lỗi 4: Cho rằng `opens` khiến `import` compile thành công.** `opens` không công bố package thành compile-time public API. Nếu module khác phải tham chiếu trực tiếp, cân nhắc `exports`.

**Lỗi 5: Đọc `isExported(pkg, other) == true` rồi suy ra module-info có `exports`.** Ở runtime, package được mở cho `other` có thể khiến kết quả đó cũng là `true`. Cần phân biệt **trạng thái runtime** với **chỉ thị trong `ModuleDescriptor`**.

**Lỗi 6: Dùng `isOpen(pkg, targetModule)` để kiểm tra quyền framework.** Một module có quyền truy cập package của chính nó; phải dùng module của **caller** ở phía framework thực tế.

**Lỗi 7: Tưởng rằng classpath code có thể deep reflect tùy ý vào JDK internals.** Java hiện đại đóng gói mạnh nhiều package của named modules; phía target phải open package cần thiết, hoặc launch option phù hợp.

**Lỗi 8: Dùng `open module` để giải quyết mọi lỗi import.** Đây là quyết định runtime Reflection, không thay thế chính sách export/readability cho biên dịch.

## 10. Bài tập và checklist tự kiểm tra

1. Chạy ví dụ `com.example.target`/`com.example.inspector`, đối chiếu cả sáu dòng stdout. Thử xóa `opens ... to ...`, quan sát vị trí lỗi `InaccessibleObjectException`.
2. Thử thêm lại `opens` ở dạng **unqualified** và quan sát sự khác nhau giữa `isOpen(package)` và `isOpen(package, inspector)`.
3. Thay `module com.example.target` bằng `open module com.example.target`, bỏ dòng `opens` riêng, biên dịch lại. Giải thích vì sao reflection vào `Secret` vẫn hoạt động.
4. Dùng `Module.getDescriptor()` kiểm tra `isOpen()` và danh sách `exports()` của module. Phân biệt metadata khai báo với `Module.isExported(pkg, module)` theo quyền runtime.
5. Chạy `UnnamedDemo` trên classpath. Sau đó đóng gói trong một named module, chạy bằng `-m` và so sánh `getName()`.
6. Với thư viện định đưa vào module path, kiểm tra các package thực sự cần public API và package thực sự cần deep reflection trước khi quyết định dùng `exports` hay `opens`.

**Ghi nhớ:** `Class.getModule()` cho biết kiểu thuộc module nào; `Module.isNamed()` phân biệt named/unnamed; `module-info.java` điều khiển **readability**, **exports** và **opens**; còn từ khóa `open module` mở mọi package của một **named module** cho deep reflection. Khi Reflection thất bại, cần tìm chính xác **module sở hữu package**, **module đang gọi**, và **loại quyền đang thiếu**.