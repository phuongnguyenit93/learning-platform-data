# --add-exports và --add-opens: phân biệt truy cập thường với reflection sâu

Khi nâng ứng dụng từ Java 8 lên Java 11, 17, 21 hoặc những bản Java mới hơn, một số thư viện cũ bắt đầu báo lỗi liên quan đến package không được công khai hoặc reflection không được phép truy cập thành viên nội bộ. Hai tùy chọn JVM thường xuất hiện trong hướng xử lý là `--add-exports` và `--add-opens`. Tên của chúng gần giống nhau nhưng giải quyết **hai loại truy cập khác nhau**: truy cập bằng ngôn ngữ Java thông thường và truy cập sâu qua reflection.

Nhầm hai tùy chọn có thể dẫn đến những cách sửa không hiệu quả. Chẳng hạn, thêm `--add-exports` không đồng nghĩa framework được phép đọc field `private`; còn thêm `--add-opens` không biến một package nội bộ thành API công khai để có thể `import` và biên dịch mã Java tùy ý.

Bài học thuộc nhóm **Reflection và API nội bộ** của module **Java Advance Compatibility Migration**. Mục tiêu là hiểu các ranh giới của Java Platform Module System (JPMS), chọn đúng tùy chọn ở đúng giai đoạn, và biết khi nào nên bỏ workaround để nâng thư viện hoặc sửa kiến trúc.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt *module readability*, *package export*, *package open* và quyền truy cập thành viên theo quy tắc ngôn ngữ Java.
- Giải thích `--add-exports` cho phép gì và **không** cho phép gì.
- Giải thích `--add-opens` cho phép gì và **không** cho phép gì.
- Nhận diện sự khác biệt giữa lỗi ở thời điểm biên dịch và lỗi ở runtime.
- Chọn target phù hợp cho named module hoặc mã nằm trên classpath thông qua `ALL-UNNAMED`.
- Đọc các lỗi `IllegalAccessError`, `IllegalAccessException` và `InaccessibleObjectException` theo đúng ngữ cảnh.
- Áp dụng các tùy chọn một cách có giới hạn trong Java command, Maven, Gradle, môi trường kiểm thử và sản xuất.
- Lập kế hoạch thay thế những phụ thuộc vào API nội bộ thay vì duy trì cờ mở quyền mãi mãi.

## 2. Nền tảng JPMS: đọc module, export package và truy cập thành viên

### 2.1. Module có tên và unnamed module

Từ Java 9, JPMS tổ chức các thành phần Java thành module. Một module có tên rõ ràng có thể khai báo `module-info.java`:

```java
module com.example.application {
    requires com.example.library;
}
```

Các lớp được nạp từ classpath truyền thống thường thuộc một **unnamed module** của class loader tương ứng. Các lớp trong JAR có descriptor khi được đặt trên module path thường thuộc **named module**. Một JAR chưa có descriptor trên module path có thể trở thành **automatic module**, mang quy tắc tương thích riêng.

Việc sử dụng JDK mới **không** bắt buộc toàn bộ ứng dụng phải có `module-info.java`. Nhiều hệ thống legacy vẫn chạy trên classpath, nhưng các lớp trong JDK đã thuộc những named module như `java.base` và `java.sql` nên việc truy cập API nội bộ vẫn chịu ràng buộc JPMS.

### 2.2. Ba điều kiện khác nhau để truy cập API theo cách thông thường

Giả sử module `com.example.application` cần gọi một class `public` thuộc module `com.example.library`. Phải xem xét ít nhất ba tầng:

1. **Module readability:** module gọi có đọc được module chứa class hay không?
2. **Package export:** module chứa class có export package đó tới module gọi hay không?
3. **Java access control:** class và thành viên có mức truy cập `public`, `protected` hoặc mức thích hợp trong ngữ cảnh gọi hay không?

Ví dụ:

```java
module com.example.library {
    exports com.example.library.api;
}
```

```java
module com.example.application {
    requires com.example.library;
}
```

Ở đây, `com.example.application` có thể tham chiếu các kiểu `public` trong `com.example.library.api`. Nó không tự động truy cập được package `com.example.library.internal` nếu package đó không được export.

Có thể ghi nhớ bằng sơ đồ:

```text
Module gọi đọc được module đích?
         |
         +-- Không --> Thiếu readability
         |
         +-- Có
              |
              v
Package được export cho module gọi?
         |
         +-- Không --> Bị chặn ở ranh giới package
         |
         +-- Có
              |
              v
Quy tắc public/protected/package/private có cho phép?
         |
         +-- Không --> Bị chặn ở ranh giới thành viên
         |
         +-- Có ----> Có thể truy cập theo cách thông thường
```

**`requires` và `exports` giải quyết hai điều kiện khác nhau.** Thêm `requires` không làm package nội bộ trở thành public API; thêm export cũng không biến một method `private` thành `public`.

### 2.3. Reflection thường và deep reflection

Reflection không phải một loại truy cập duy nhất.

**Reflection thường** có thể đọc metadata hoặc gọi thành viên `public` thông qua các API như `Class.getMethod` và `Method.invoke`. Khi truy cập các kiểu/thành viên của module khác, quy tắc module export và kiểm tra quyền truy cập vẫn có ý nghĩa.

**Deep reflection** xảy ra khi mã muốn bỏ qua kiểm tra thông thường để truy cập constructor, method hoặc field không công khai, ví dụ dùng:

```java
Field field = type.getDeclaredField("secret");
field.setAccessible(true);
Object value = field.get(null);
```

Deep reflection thường cần package đích được **open** đến module thực hiện reflection. Chỉ export package không đủ để cho phép truy cập `private`.

Một ứng dụng có thể gọi được method `public` nhưng vẫn bị chặn khi serializer hoặc ORM cố đọc field `private` của cùng class.

## 3. `--add-exports`: mở truy cập thông thường vào một package

### 3.1. Cú pháp và ý nghĩa

Cú pháp tổng quát:

```text
--add-exports <source-module>/<package>=<target-module>
```

Có thể dùng nhiều target module bằng danh sách phân cách bằng dấu phẩy, hoặc dùng giá trị đặc biệt `ALL-UNNAMED` để cấp quyền cho các unnamed module.

Ví dụ minh họa với module do chính dự án sở hữu:

```bash
java --add-exports com.example.core/com.example.internal=com.example.client \
     --module-path mods \
     -m com.example.client/com.example.client.Main
```

Lệnh này chỉ định rằng package `com.example.internal` của module `com.example.core` được export thêm cho `com.example.client`.

Đây là một **qualified export được bổ sung bằng cấu hình khi khởi chạy**. Nó không sửa file JAR hay `module-info.class` lưu trong artifact.

### 3.2. `--add-exports` cho phép điều gì?

Khi module gọi đã có quan hệ readability phù hợp và thỏa quy tắc Java access control, `--add-exports` có thể cho phép:

- Import các kiểu `public` trong package vốn không được export.
- Gọi constructor hoặc method `public` có thể truy cập theo quy tắc Java.
- Tham chiếu field `public` hoặc các thành viên có mức truy cập phù hợp.
- Sử dụng những API này từ source code khi compiler được cấu hình `--add-exports` tương ứng.
- Cho phép bytecode thực hiện truy cập công khai ở runtime khi JVM cũng được cấu hình tương ứng.

Ví dụ một package nội bộ có class `public`:

```java
package com.example.internal;

public final class InternalApi {
    private InternalApi() {}

    public static String message() {
        return "Xin chào từ internal API";
    }

    private static String secret = "demo-only";
}
```

Nếu package này chưa được export cho client, phép import sau sẽ không hợp lệ trong một explicit named module thông thường:

```java
import com.example.internal.InternalApi;
```

Compiler có thể báo rằng package không được export tới module đang biên dịch. Khi thêm đúng export lúc compile, import và lời gọi `InternalApi.message()` có thể trở thành hợp lệ.

### 3.3. `--add-exports` không cho phép điều gì?

Tùy chọn này **không**:

- Cấp quyền đọc method hoặc field `private` bằng deep reflection.
- Thay đổi `private` thành `public`.
- Tự động tạo quan hệ module readability nếu quan hệ đọc cần thiết chưa tồn tại.
- Làm cho class bị thiếu xuất hiện trong classpath/module path.
- Chứng minh API nội bộ được nhà cung cấp cam kết hỗ trợ.
- Bảo đảm class hoặc method nội bộ giữ nguyên tên và hành vi ở JDK tương lai.

Nếu framework làm:

```java
Field field = InternalApi.class.getDeclaredField("secret");
field.setAccessible(true);
```

thì việc export package để mã gọi thấy `InternalApi` vẫn **chưa đủ** để đảm bảo `setAccessible(true)` thành công. Đây là tình huống cần xem xét `opens` hoặc `--add-opens`.

## 4. `--add-opens`: cho phép deep reflection vào package

### 4.1. Cú pháp và ý nghĩa

Cú pháp tổng quát:

```text
--add-opens <source-module>/<package>=<target-module>
```

Ví dụ:

```bash
java --add-opens com.example.core/com.example.internal=com.example.client \
     --module-path mods \
     -m com.example.client/com.example.client.ReflectionMain
```

Lệnh yêu cầu JVM **open** package `com.example.internal` từ module `com.example.core` cho module `com.example.client`. Mục đích là cho phép các thao tác reflection sâu thuộc phạm vi mở này, chẳng hạn `setAccessible(true)` trên thành viên không public.

### 4.2. Tại sao framework cần opens?

Nhiều framework tạo object hoặc ánh xạ dữ liệu qua reflection:

- **ORM:** đọc/ghi field entity không public, tạo instance qua constructor.
- **Serializer/deserializer:** khám phá field, setter, constructor và metadata.
- **Dependency injection:** tạo bean, inject field, gọi lifecycle method.
- **Proxy/AOP:** xử lý method và class được sinh ở runtime.
- **Testing/mocking:** kiểm tra hoặc thay thế những thành viên thông thường không public.

Ví dụ:

```java
Class<?> type = Class.forName("com.example.internal.InternalApi");
Field field = type.getDeclaredField("secret");
field.setAccessible(true);
String value = (String) field.get(null);
```

Với named module đích không open package, lệnh `getDeclaredField` có thể tìm thấy metadata nhưng `setAccessible(true)` bị từ chối. Khi package được open cho module thực hiện reflection, thao tác có thể được phép trong phạm vi JPMS tương ứng.

### 4.3. `--add-opens` khác `exports` như thế nào?

`--add-opens` không phải là một cách viết khác của `--add-exports`:

- `--add-exports` phục vụ khả năng truy cập **API theo cách thông thường**, nhất là các kiểu/thành viên public.
- `--add-opens` phục vụ **reflection sâu** ở runtime vào package đã open.
- Thêm `--add-opens` vào lệnh `javac` không phải cách cấp quyền truy cập compile-time cho `import` trong source; compiler có thể thông báo tùy chọn này không có tác dụng khi biên dịch.
- Một package open có thể hỗ trợ reflection trên thành viên public và non-public theo quy tắc reflection, nhưng điều đó không tương đương export để source code truy cập theo cách thông thường.

Tính đúng đắn còn phụ thuộc vào module thực hiện reflection và class loader đang được dùng. Không nên mở package cho một module mà framework thực tế không thuộc module đó.

### 4.4. `opens` trong descriptor và `--add-opens` khi khởi chạy

Nếu bạn sở hữu source của module, có thể khai báo:

```java
module com.example.core {
    opens com.example.internal to com.example.client;
}
```

Nếu không sở hữu hoặc chưa thể sửa module descriptor, dùng tùy chọn runtime:

```bash
java --add-opens com.example.core/com.example.internal=com.example.client ...
```

Hai cách phục vụ mục tiêu tương tự nhưng có phạm vi quản lý khác nhau:

| Cách | Nơi khai báo | Phạm vi |
| --- | --- | --- |
| `opens p to m` | `module-info.java` | Là một phần contract module do tác giả phát hành. |
| `opens p` | `module-info.java` | Open package cho tất cả module theo quy tắc JPMS. |
| `open module m` | `module-info.java` | Open tất cả package của module cho deep reflection. |
| `--add-opens m/p=t` | Tùy chọn runtime | Bổ sung quyền open cho target ở lần chạy đó. |

Khi có quyền chỉnh source, ưu tiên `opens` đúng package và đúng module cần truy cập, thay vì open toàn bộ module. Với thư viện bên thứ ba, ưu tiên nâng phiên bản hỗ trợ JDK đích trước khi dùng workaround lâu dài.

## 5. So sánh trực tiếp `--add-exports` và `--add-opens`

| Tiêu chí | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Mục đích chính | Truy cập Java thông thường tới package chưa export. | Cho phép deep reflection vào package. |
| Có thể giúp `import` class public không được export? | Có, nếu compiler và các điều kiện còn lại được cấu hình phù hợp. | Không, không thay thế export ở compile time. |
| Có thể giúp gọi method public theo cách thông thường? | Có. | Không phải mục đích của tùy chọn; không tạo quyền compile-time thông thường. |
| Có thể giúp truy cập field/method private qua `setAccessible(true)`? | Không đủ. | Có thể, khi open cho đúng module gọi và không vướng ràng buộc khác. |
| Giai đoạn sử dụng | Thường cần ở compile time và runtime nếu source dùng API không export. | Chủ yếu ở runtime; cũng cần trong JVM chạy test/framework có reflection. |
| Target | Named module hoặc `ALL-UNNAMED`. | Named module hoặc `ALL-UNNAMED`. |
| Có tự tạo dependency `requires`? | Không. | Không. |
| Có làm API nội bộ trở nên ổn định? | Không. | Không. |
| Rủi ro | Ứng dụng phụ thuộc vào API implementation có thể thay đổi. | Mở thêm khả năng truy cập vào internals, khó kiểm soát nếu phạm vi quá rộng. |

**Quy tắc chọn nhanh:** source dùng `import internal.package.Type` và lỗi package không export → điều tra `--add-exports`. Framework dùng `setAccessible(true)` và bị chặn → điều tra `--add-opens`. Nếu class không tồn tại hoặc module chưa được nạp, cả hai đều chưa phải giải pháp đúng.

## 6. Thực hành với hai named module: lỗi compile và lỗi reflection

Ví dụ dưới đây dùng hai module do chúng ta tự định nghĩa. Cách này cho thấy sự khác biệt mà không phải dựa vào một API nội bộ cụ thể của JDK vốn có thể thay đổi giữa các phiên bản.

### 6.1. Cấu trúc thư mục

```text
demo/
├── src/
│   ├── com.example.core/
│   │   ├── module-info.java
│   │   └── com/example/internal/InternalApi.java
│   └── com.example.client/
│       ├── module-info.java
│       └── com/example/client/
│           ├── DirectClient.java
│           └── ReflectionMain.java
└── mods/
```

Module nguồn:

```java
// src/com.example.core/module-info.java
module com.example.core {
    // Cố ý không export package com.example.internal.
}
```

```java
// src/com.example.core/com/example/internal/InternalApi.java
package com.example.internal;

public final class InternalApi {
    private InternalApi() {}

    public static String message() {
        return "Public method trong package nội bộ";
    }

    private static String secret = "Thông tin minh họa";
}
```

Module client:

```java
// src/com.example.client/module-info.java
module com.example.client {
    requires com.example.core;
}
```

### 6.2. Trường hợp A: truy cập thông thường cần exports

Client trực tiếp:

```java
// src/com.example.client/com/example/client/DirectClient.java
package com.example.client;

import com.example.internal.InternalApi;

public final class DirectClient {
    public static void main(String[] args) {
        System.out.println(InternalApi.message());
    }
}
```

Biên dịch module core:

```bash
javac -d mods/com.example.core \
  src/com.example.core/module-info.java \
  src/com.example.core/com/example/internal/InternalApi.java
```

Nếu biên dịch client như một named module không có export bổ sung, phép import `InternalApi` sẽ bị từ chối vì `com.example.internal` không được export từ `com.example.core`.

Có thể chỉ định export lúc biên dịch:

```bash
javac --module-path mods \
  --add-exports com.example.core/com.example.internal=com.example.client \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/DirectClient.java \
  src/com.example.client/com/example/client/ReflectionMain.java
```

Lúc chạy client trực tiếp, cũng cần khai báo export tương ứng:

```bash
java --module-path mods \
  --add-exports com.example.core/com.example.internal=com.example.client \
  -m com.example.client/com.example.client.DirectClient
```

Nếu chỉ dùng tùy chọn ở compile time, runtime có thể từ chối truy cập và phát sinh `IllegalAccessError`. Ngược lại, chỉ thêm tùy chọn ở runtime không giúp sửa lỗi `import` khi compiler vẫn bị chặn.

### 6.3. Trường hợp B: reflection sâu cần opens

Một client khác không import `InternalApi` mà tra cứu lớp và field bằng tên:

```java
// src/com.example.client/com/example/client/ReflectionMain.java
package com.example.client;

import java.lang.reflect.Field;

public final class ReflectionMain {
    public static void main(String[] args) throws Exception {
        Class<?> type =
                Class.forName("com.example.internal.InternalApi");
        Field field = type.getDeclaredField("secret");

        field.setAccessible(true);
        System.out.println(field.get(null));
    }
}
```

Class `ReflectionMain` không cần truy cập kiểu `InternalApi` ở source level, nên việc biên dịch riêng lớp này không yêu cầu `--add-exports` cho package nội bộ.

Biên dịch client với module path và file descriptor:

```bash
javac --module-path mods \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/ReflectionMain.java
```

Chạy không có quyền open:

```bash
java --module-path mods \
  -m com.example.client/com.example.client.ReflectionMain
```

Trong cấu hình này, `field.setAccessible(true)` có thể ném `java.lang.reflect.InaccessibleObjectException` vì `com.example.internal` chưa được mở cho `com.example.client`.

Chạy với quyền open:

```bash
java --module-path mods \
  --add-opens com.example.core/com.example.internal=com.example.client \
  -m com.example.client/com.example.client.ReflectionMain
```

Thao tác reflection sâu có thể thành công dù `com.example.internal` vẫn không được export cho việc `import` ở compile time.

**Lưu ý về thao tác thực hành:** Hai luồng compile được trình bày để minh họa riêng từng quyền. Nếu triển khai cả hai client cùng một output directory, giữ nguyên cấu hình build và đảm bảo các class đã được biên dịch trong trường hợp tương ứng. Trong dự án thật nên tách hai bài thử thành hai task/cấu hình độc lập để tái hiện từng lỗi.

## 7. `ALL-UNNAMED` và sự khác biệt giữa classpath, module path

### 7.1. Khi framework nằm trên classpath

Nhiều ứng dụng legacy sử dụng classpath và không có module descriptor. Mã của chúng thường thuộc unnamed module. Để mở một package của named module cho mã này, cú pháp thường dùng:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -jar application.jar
```

Hoặc, nếu source classpath trực tiếp tham chiếu API public trong một package không export:

```bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED \
     -jar application.jar
```

Hai lệnh này **chỉ để minh họa cú pháp và nguyên tắc**. Không nên tự thêm các cờ trên vào production khi chưa có lỗi và tài liệu xác nhận package thực sự cần được truy cập. API trong `jdk.internal.*` là implementation detail và có thể thay đổi hoặc biến mất.

`ALL-UNNAMED` là nhóm unnamed modules, **không phải tên một JAR duy nhất**. Vì thế phạm vi mở quyền có thể rộng hơn mong muốn, đặc biệt nếu nhiều thư viện chạy trên classpath của một hoặc nhiều class loader.

### 7.2. Khi framework nằm trong named module

Nếu framework là một named module, ví dụ `com.example.framework`, chỉ định đúng tên đó:

```bash
java --add-opens java.base/java.lang=com.example.framework \
     --module-path mods \
     -m com.example.app/com.example.app.Main
```

Giá trị target phải tương ứng với **module của mã thực hiện reflection**, không nhất thiết là module khởi động ứng dụng. Nếu ORM được nạp bởi một module tên khác, mở package cho app module có thể vẫn không giải quyết được lỗi.

### 7.3. Automatic module

Một JAR legacy trên module path có thể trở thành automatic module. Nó có tên module và những đặc tính tương thích riêng. Không nên mặc định rằng cứ dùng JAR cũ thì target luôn là `ALL-UNNAMED`; nếu JAR đã được chạy như automatic module, target cần dựa trên module name được xác định thực tế.

Tra thông tin module của JAR:

```bash
jar --describe-module --file path/to/library.jar
```

Việc chuyển JAR từ classpath sang module path có thể đổi danh tính module của nó, do đó cũng có thể làm thay đổi target mà `--add-opens` hoặc `--add-exports` cần chỉ định.

## 8. Vì sao còn cần quan hệ readability?

`--add-exports` và `--add-opens` chỉ xử lý export/open của package. Chúng không phải lời giải tổng quát cho mọi lỗi phụ thuộc module.

Ví dụ:

```java
module com.example.app {
    // Nếu cần gọi module com.example.core bằng source Java thông thường:
    requires com.example.core;
}
```

Nếu module gọi chưa đọc được module đích, cần xem `requires`, module graph và trong những trường hợp đặc biệt là `--add-reads`:

```text
--add-reads <source-module>=<target-module>
```

Với code classpath có thể xuất hiện target `ALL-UNNAMED` trong các kịch bản chuyển tiếp. Đây là một cơ chế **khác** với export/open.

Cách nghĩ hữu ích khi xử lý lỗi:

- **Không tìm thấy module:** kiểm tra module path và module resolution.
- **Không đọc được module:** kiểm tra `requires` hoặc `--add-reads` khi thật sự cần.
- **Không thấy package public:** kiểm tra `exports` hoặc `--add-exports`.
- **Reflection sâu bị chặn:** kiểm tra `opens` hoặc `--add-opens`.
- **Không tìm thấy class/JAR:** kiểm tra classpath, class loader, dependency scope và môi trường triển khai.

## 9. Các kiểu lỗi và cách diễn giải

### 9.1. Lỗi compile: package không visible

Một thông báo có thể có nội dung tương tự:

```text
package com.example.internal is not visible
(package com.example.internal is declared in module com.example.core,
 which does not export it to module com.example.client)
```

**Ý nghĩa:** compiler thấy package trong named module nhưng package không export cho module gọi. Nếu việc dùng API này là chủ đích, có thể bổ sung export phù hợp. Nhưng nếu đó là package nội bộ, giải pháp tốt hơn là thay bằng API công khai của nhà cung cấp.

### 9.2. `IllegalAccessError` tại runtime

Một binary đã được biên dịch có thể gặp lỗi khi JVM thực hiện truy cập vào kiểu/thành viên bị module system chặn:

```text
java.lang.IllegalAccessError:
  class ... cannot access class ...
  because module ... does not export ... to module ...
```

**Ý nghĩa:** đường chạy thực tế thiếu export/readability hoặc có mismatch giữa cấu hình compile và runtime. Đừng giả định vì source compile thành công thì JVM production đã có cùng cờ.

### 9.3. `InaccessibleObjectException` với deep reflection

Lỗi tiêu biểu:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field ... accessible:
  module ... does not "opens ..." to ...
```

**Ý nghĩa:** reflection muốn vượt qua Java access checks nhưng package chưa open cho module thực hiện thao tác. Xác định module nguồn/package/target ngay trong thông báo lỗi; ưu tiên nâng framework hoặc sửa descriptor. `--add-exports` một mình thường không giúp.

### 9.4. `IllegalAccessException` và kiểm tra phản chiếu

`IllegalAccessException` cũng có thể xuất hiện khi gọi constructor hoặc method qua reflection mà quyền truy cập không phù hợp. Sự khác nhau thường liên quan đến thao tác mà API reflection đang thực hiện và việc có yêu cầu suppress access checks hay không.

`trySetAccessible()` có thể trả về `false` thay vì ném `InaccessibleObjectException` khi không thể bật access override, nhờ đó có thể xử lý tình huống một cách có kiểm soát. Nhưng nó không tạo quyền truy cập mới.

### 9.5. `ClassNotFoundException` không phải lỗi export/open

Nếu class loader không tìm thấy lớp:

```text
java.lang.ClassNotFoundException: com.vendor.LegacyProvider
```

thì thêm `--add-opens` hoặc `--add-exports` không làm JAR còn thiếu xuất hiện. Phải kiểm tra dependency runtime, module resolution, plugin directory và class loader.

### 9.6. Mã reflection có thể không hiển thị trong source ứng dụng

Framework có thể dùng reflection ở mã của thư viện bên thứ ba. Stack trace thường chứa tên framework/serializer/proxy library. Dù ứng dụng không tự gọi `setAccessible`, lỗi vẫn có thể đến từ framework mà dependency của ứng dụng kéo vào.

Do đó, khi chẩn đoán, ghi rõ **module thực hiện reflection**, module chứa package đích và phiên bản dependency gây lỗi.

## 10. Sự khác biệt theo phiên bản Java

### 10.1. Java 8: chưa có JPMS

Java 8 không có `module-info.java` và không hỗ trợ các tùy chọn JPMS `--add-exports`/`--add-opens`. Ứng dụng Java 8 có thể từng truy cập nhiều class nội bộ của JDK hoặc reflection vào các lớp nền tảng mà không gặp cùng cơ chế kiểm tra của Java 9+.

Khi nâng JDK, không thể chỉ giữ nguyên mọi JVM option và giả định runtime sẽ có hành vi tương đương.

### 10.2. Java 9 đến 15: có cơ chế chuyển tiếp

Java 9 giới thiệu JPMS, đồng thời nhiều bản JDK giai đoạn đầu sử dụng chính sách *relaxed strong encapsulation* cho một số package từng tồn tại trong JDK 8. `--illegal-access` từng được cung cấp để điều khiển một phần cơ chế này, và ứng dụng có thể thấy cảnh báo `Illegal reflective access`.

Cơ chế chuyển tiếp không đồng nghĩa mọi API nội bộ đều được phép truy cập. Các trường hợp đã bị chặn rõ vẫn cần sửa mã, nâng thư viện hoặc khai báo cấu hình phù hợp.

### 10.3. Java 16 và Java 17 trở lên: đóng gói chặt hơn

Ở Java 16, strong encapsulation trở thành mặc định trong nhiều trường hợp. Từ Java 17, JEP 403 củng cố đóng gói mạnh cho internals của JDK; tùy chọn `--illegal-access` cũ trở nên lỗi thời và không còn có tác dụng mở quyền như trước.

Vì vậy một workaround dựa vào việc bỏ qua cảnh báo trên JDK 11 có thể không còn giúp ứng dụng khởi động trên JDK 17+. Cần nâng framework và dùng API công khai, hoặc áp dụng `--add-opens`/`--add-exports` **có mục tiêu** trong thời gian chuyển tiếp.

### 10.4. Không phải mọi thứ trong `sun.*` đều có cùng trạng thái

Một số API đặc thù có cơ chế tương thích riêng, ví dụ API quan trọng được cung cấp qua module `jdk.unsupported`. Không suy luận rằng mọi package bắt đầu bằng `sun.` hoặc `com.sun.` đều có cùng ranh giới. Cần kiểm tra module thật sự chứa class, package export và tài liệu chính thức của JDK đích.

Cách bền vững vẫn là thay API nội bộ bằng API public được hỗ trợ khi có thể.

## 11. Tích hợp tùy chọn vào build và test

### 11.1. Cờ compile và cờ runtime phải đặt đúng nơi

Nếu mã Java thường **import** một class public trong package không export, quy trình build có thể cần `--add-exports` tại `javac`; chương trình chạy cũng có thể cần cùng export tại `java`.

Nếu framework **deep reflection**, JVM thực thi test hoặc ứng dụng có thể cần `--add-opens`. Đặt `--add-opens` chỉ vào compiler arguments không giải quyết lỗi reflection khi test hoặc production chạy.

Mỗi nơi có JVM riêng có thể cần cấu hình riêng:

- JVM chạy unit test.
- JVM chạy integration test.
- JVM chạy application/server.
- JVM chạy công cụ sinh mã hoặc annotation processor, nếu công cụ đó thực sự dùng reflection.
- JVM nằm trong container image hoặc application server của production.

Không sao chép cờ vào mọi JVM vô điều kiện. Chỉ thêm cho tiến trình thực sự cần truy cập.

### 11.2. Ví dụ Gradle

Minh họa một dự án cần export khi compile và open khi chạy test:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports',
        'java.base/jdk.internal.misc=ALL-UNNAMED'
    ]
}

tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'java.base/java.lang=ALL-UNNAMED'
    )
}
```

Đây là ví dụ về **vị trí cấu hình**, không phải khuyến nghị dùng những package JDK nội bộ này. Gradle có thể sử dụng toolchain, test launcher hoặc JavaExec task khác nhau; phải kiểm tra JVM thực tế chạy từng task. Nếu dự án dùng `--release` cho bản Java cũ, một số cách kết hợp `--add-exports` với `--release` có thể bị compiler từ chối; cần giải quyết yêu cầu API thay vì ép compiler bỏ qua mục tiêu release.

Nếu ứng dụng chạy bằng `JavaExec` hoặc một plugin riêng, `Test.jvmArgs` không tự động áp dụng cho tiến trình đó.

### 11.3. Ví dụ Maven

Nếu mục tiêu chỉ là mở package cho JVM chạy test, Maven Surefire có thể cấu hình JVM argument, ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>
            --add-opens java.base/java.lang=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
```

Với dự án đã sử dụng `argLine` cho JaCoCo hoặc một agent khác, phải **gộp** các tham số theo cơ chế plugin để không ghi đè tham số hiện có. Khả năng fork và phiên bản plugin cũng ảnh hưởng việc áp dụng flag.

Nếu cần export cho source compile, cấu hình compiler plugin theo `compilerArgs` hoặc cách được phiên bản plugin hỗ trợ. Không dùng `argLine` của test runner để mong sửa lỗi compilation.

### 11.4. JVM trong container và môi trường production

Đối với service triển khai trong container, có thể cấu hình cờ trong startup command hoặc cấu hình JVM option do nền tảng quản lý. Ghi rõ cờ nằm ở đâu:

```text
Local Java command
       |
       +-- Build JVM / compiler
       +-- Unit-test JVM
       +-- Integration-test JVM
       +-- Application JVM
       +-- Production container / application server
```

Không phải mọi JVM ở sơ đồ đều đọc cùng một biến môi trường hoặc cùng một file cấu hình. Sau deploy, cần xác nhận tiến trình Java chạy với arguments thực tế như dự kiến, không chỉ dựa vào README hoặc build script.

## 12. Vì sao không nên coi các cờ là giải pháp cuối cùng?

### 12.1. Phụ thuộc API nội bộ khó nâng cấp lâu dài

API trong package nội bộ có thể thay đổi tên class, chữ ký, semantics hoặc biến mất giữa các phiên bản JDK. `--add-exports` chỉ mở access; nó **không** giữ API đó ổn định.

Một dự án dùng `jdk.internal.*` có thể chạy hôm nay và hỏng sau khi đổi JDK, ngay cả khi giữ nguyên cờ export.

### 12.2. Mở reflection sâu có tác động đến encapsulation

`--add-opens` cho phép module khác dùng reflection sâu vào package đã open. Với target `ALL-UNNAMED`, nhiều thư viện trên classpath có thể được hưởng quyền mở đó. Đây là lý do nên:

- Hạn chế đúng package.
- Hạn chế đúng module khi có thể.
- Tránh mở toàn bộ `java.base` hoặc mở một danh sách package không được kiểm chứng.
- Không giả định JPMS là một sandbox bảo mật hoàn chỉnh.
- Xem cờ mở quyền như một thay đổi cấu hình cần được kiểm soát và rà soát.

### 12.3. Workaround dễ che giấu dependency cũ

Khi một framework cũ yêu cầu nhiều `--add-opens`, có thể đây là dấu hiệu nó chưa hỗ trợ JDK đích. Việc bổ sung cờ liên tiếp khiến khả năng nâng cấp trong tương lai phụ thuộc ngày càng nhiều vào chi tiết triển khai của JDK.

Cách ưu tiên hợp lý:

1. Nâng framework/thư viện lên bản hỗ trợ JDK đích.
2. Chuyển sang API public hoặc cơ chế plugin/service được hỗ trợ.
3. Nếu sở hữu module đích, sửa `module-info.java` bằng `exports`/`opens` chính xác.
4. Nếu chưa thể sửa ngay, dùng `--add-exports`/`--add-opens` tối thiểu với chủ sở hữu và kế hoạch loại bỏ.

## 13. Quy trình điều tra lỗi trong dự án migration

### Bước 1: Ghi lại lỗi và môi trường

Thu thập stack trace hoặc diagnostic đầy đủ; JDK vendor/version; source/target/release; phiên bản framework; classpath/module path; JVM arguments thật sự của tiến trình bị lỗi.

### Bước 2: Phân loại lỗi

Xác định lỗi thuộc:

- Module resolution hoặc class loading.
- Readability.
- Compile-time ordinary access.
- Runtime ordinary access.
- Deep reflection.

Không chọn flag chỉ dựa vào cụm từ “access denied” mà chưa xem loại thao tác và module đích.

### Bước 3: Xác định source module, package và target module

Đọc thông báo như:

```text
module java.base does not "opens java.lang" to unnamed module ...
```

Ta có:

- Source module: `java.base`.
- Package: `java.lang`.
- Target: một unnamed module; trong ví dụ ứng dụng classpath, target của cờ thường là `ALL-UNNAMED`.
- Loại vấn đề: cần deep reflection, do đó cần xem `--add-opens` chứ không phải `--add-exports`.

Nếu lỗi ghi “does not export”, đó thường là dấu hiệu ordinary access/export. Tuy nhiên vẫn cần xem stack trace và loại truy cập để tránh sửa nhầm.

### Bước 4: Kiểm tra module graph và artifact

Một số lệnh tham khảo:

```bash
java --list-modules

java --describe-module java.base

jar --describe-module --file path/to/dependency.jar

java --show-module-resolution \
     --module-path mods \
     -m com.example.app/com.example.app.Main
```

Có thể dùng `jdeps` để tìm một số phụ thuộc tĩnh vào API nội bộ:

```bash
jdeps --recursive --jdk-internals path/to/application.jar
```

Những công cụ này không phát hiện đầy đủ reflection, class được nạp theo tên cấu hình hoặc plugin xuất hiện ở runtime. Vì vậy, kết quả âm tính không chứng minh ứng dụng không phụ thuộc API nội bộ.

### Bước 5: Chọn giải pháp ít mở quyền nhất

Nếu có API public thay thế, ưu tiên chuyển API. Nếu phải dùng cờ tạm thời:

- Đúng **source module/package**.
- Đúng **target module** hoặc `ALL-UNNAMED` khi thật sự cần.
- Đúng **loại quyền** (export hoặc open).
- Đúng **tiến trình** (compiler, test runtime, app runtime).
- Có giải thích và mốc xem xét lại.

### Bước 6: Xác minh trên cấu hình đại diện

Build và test ở JDK đích. Kiểm tra startup, reflection, serialization, database driver, logging, agent và những flow nghiệp vụ dùng framework liên quan.

Nếu app chạy trên JDK 11 nhưng mục tiêu là JDK 17 hoặc 21, cần kiểm thử trên JDK mục tiêu; không coi cảnh báo ở bản cũ là bằng chứng chạy được trên bản mới.

### Bước 7: Ghi nhận workaround và kế hoạch loại bỏ

Tạo một bản ghi ngắn với mẫu:

| Trường | Nội dung |
| --- | --- |
| JVM flag | Cờ `--add-exports` hoặc `--add-opens` đầy đủ. |
| Source module/package | Ví dụ `java.base/java.lang`. |
| Target module | Module cụ thể hoặc `ALL-UNNAMED`. |
| Thành phần gây lỗi | Artifact, framework và phiên bản. |
| Loại truy cập | Compile-time ordinary, runtime ordinary hoặc deep reflection. |
| Bằng chứng | Stack trace, compiler diagnostic, log test. |
| Phạm vi áp dụng | Build, test, server hoặc container. |
| Hướng xử lý dài hạn | Nâng dependency, sửa code hoặc descriptor. |
| Chủ sở hữu | Nhóm chịu trách nhiệm. |
| Mốc xem xét | Release hoặc giai đoạn migration tiếp theo. |

## 14. Những hiểu lầm thường gặp

**“`--add-exports` mở mọi thứ trong package.”** Không. Nó không thay đổi quyền `private` hay tự cho phép deep reflection.

**“`--add-opens` giúp `import` mọi internal class.”** Không. Nó chủ yếu xử lý deep reflection trong runtime; ordinary source access vẫn cần export và các điều kiện khác.

**“Có `requires` thì dùng được mọi package.”** Không. Module readability và package export là hai ranh giới riêng.

**“`ALL-UNNAMED` chỉ cấp quyền cho app.jar.”** Không. Nó đại diện cho các unnamed module, có thể bao gồm nhiều thư viện classpath và class loader.

**“Cờ đã có trong build là production sẽ nhận.”** Không. JVM chạy build, test và application có thể khác nhau.

**“Chỉ cần thêm `--add-opens` thì hết mọi `ClassNotFoundException`.”** Sai. Lỗi không tìm thấy class thường do dependency, class loader hoặc module resolution.

**“JDK 11 chỉ cảnh báo nên JDK 17 cũng sẽ chạy.”** Không chắc. Chính sách đóng gói mạnh đã thay đổi giữa các phiên bản Java.

**“Có nhiều cờ mở quyền là việc bình thường sau migration.”** Một số cờ tạm thời có thể cần, nhưng chúng nên được kiểm kê và loại bỏ khi framework, dependency hoặc mã nguồn đã tương thích.

## 15. Checklist trước khi kết luận đã xử lý xong

- [ ] Đã xác nhận lỗi thuộc ordinary access hay deep reflection.
- [ ] Đã xác định module chứa package và module thực hiện truy cập.
- [ ] Đã kiểm tra module path, classpath, module readability và class loader.
- [ ] Đã phân biệt `exports`/`opens` trong descriptor với các cờ runtime.
- [ ] Đã dùng `--add-exports` cho trường hợp cần ordinary access và bố trí ở compile/runtime phù hợp.
- [ ] Đã dùng `--add-opens` cho deep reflection ở JVM thực thi đúng thành phần.
- [ ] Đã kiểm tra target named module hay `ALL-UNNAMED`, không suy đoán từ tên JAR.
- [ ] Đã xác nhận không thể thay bằng API public hoặc phiên bản thư viện mới trước khi giữ workaround.
- [ ] Đã kiểm thử trên JDK đích và cấu hình gần production.
- [ ] Đã ghi nhận rủi ro mở quyền, phạm vi, chủ sở hữu và kế hoạch loại bỏ cờ.

## 16. Tổng kết

**`--add-exports` giải quyết việc module khác truy cập kiểu/thành viên theo cách Java thông thường trong một package chưa export. `--add-opens` giải quyết việc framework hoặc mã khác cần deep reflection vào package chưa open.** Hai tùy chọn có cùng cấu trúc chỉ định module/package/target nhưng khác nhau ở loại quyền mà chúng bổ sung.

Trong Java compatibility migration, đừng dùng cờ JVM như một phép thử may rủi. Hãy xác định module graph, loại truy cập, nơi phát sinh lỗi và JVM cần cấu hình, sau đó dùng quyền nhỏ nhất có thể. Giải pháp lâu dài nên là API public, thư viện hỗ trợ JDK đích và module descriptor rõ ràng; các cờ mở quyền chỉ nên là cầu nối được kiểm soát trong quá trình chuyển đổi.
