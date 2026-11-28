# Dùng trySetAccessible và xử lý trường hợp không được cấp quyền

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Đóng gói JDK. Reflection cho phép ứng dụng đọc metadata, gọi method hoặc làm việc với field và constructor mà không cần biết kiểu cụ thể tại thời điểm biên dịch. Tuy nhiên, Java Platform Module System giới hạn việc mở quyền truy cập sâu vào member không public. `AccessibleObject.trySetAccessible()` cung cấp cách yêu cầu quyền truy cập có kiểm soát: trả về `true` nếu có thể bật cờ accessible, trả về `false` nếu module/access control không cho phép. Bài học hướng dẫn cách dùng API này, xác định nguyên nhân bị từ chối, cấu hình `opens` đúng phạm vi và thiết kế fallback an toàn trên Java hiện đại.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt kiểm tra truy cập thông thường với việc bật cờ accessible cho reflection.
- Dùng `trySetAccessible()` với `Field`, `Method` và `Constructor`.
- Hiểu khác biệt giữa `canAccess()`, `trySetAccessible()` và `setAccessible(true)`.
- Giải thích khi nào package phải được mở bằng `opens`.
- Xử lý kết quả `false` mà không làm ứng dụng dừng đột ngột.
- Kiểm tra module/package bằng `Module.isOpen()`.
- Chọn API công khai hoặc Method Handles khi reflection sâu không phù hợp.
- Tránh phụ thuộc vào việc sửa field `final` bằng reflection, đặc biệt từ JDK 26.

## 1. trySetAccessible dùng để làm gì?

`AccessibleObject` là lớp nền của các đối tượng reflection như `Field`, `Method` và `Constructor`. Những đối tượng này mặc định vẫn tuân theo quy tắc truy cập của Java. Khi framework cần truy cập một member mà code gọi bình thường không được phép truy cập, nó có thể yêu cầu bỏ qua một số kiểm tra bằng cách bật accessible flag.

Java 9 bổ sung `trySetAccessible()` cùng với module system. API này vẫn hiện hành trong Java 16 và các JDK mới hơn. Nó hữu ích khi framework hoặc thư viện cần deep reflection nhưng phải xử lý được trường hợp module không cấp quyền.

```java
Field field = User.class.getDeclaredField("email");

if (field.trySetAccessible()) {
    Object value = field.get(user);
} else {
    // Package không mở cho module đang gọi.
    // Chuyển sang API công khai hoặc báo lỗi cấu hình rõ ràng.
}
```

Kết quả của lời gọi:

- `true`: accessible flag đã được bật. Code có thể dùng đối tượng reflection để truy cập member theo quyền đã được cấp.
- `false`: Java không thể bật flag theo quy tắc truy cập hiện tại. Không tiếp tục gọi `get()`, `set()` hoặc `invoke()` với giả định rằng private access đã được cấp.

Nếu accessible flag đã là `true`, `trySetAccessible()` không cần làm gì thêm và trả về `true`.

### 1.1. API này không phải cơ chế vượt qua module system

`trySetAccessible()` không tự mở package của module khác. Nó chỉ hỏi runtime xem quyền truy cập có thể được bật theo module graph và Java access control hiện tại hay không.

Ví dụ, một module có thể export package để module khác sử dụng public type, nhưng vẫn không mở package cho deep reflection vào private field. Trong trường hợp đó, `trySetAccessible()` trên private field có thể trả về `false`.

Muốn cho module framework truy cập sâu, module chứa class phải mở package cho đúng module gọi bằng `opens` hoặc cấu hình runtime tương ứng.

### 1.2. Dùng cho Field, Method và Constructor

API thuộc `AccessibleObject` nên cách xử lý tương tự áp dụng cho cả ba loại:

```java
Field field = User.class.getDeclaredField("email");
Method method = User.class.getDeclaredMethod("normalizeEmail");
Constructor<User> constructor =
        User.class.getDeclaredConstructor(String.class);
```

Mỗi đối tượng có thể gọi `trySetAccessible()` riêng. Quyền bật thành công cho một member không có nghĩa mọi member khác trong package đều đã được bật; mỗi đối tượng reflection giữ trạng thái accessible flag của chính nó.

## 2. Phân biệt canAccess, trySetAccessible và setAccessible

Ba API này có mục đích khác nhau:

| API | Mục đích | Kết quả khi không có quyền |
|---|---|---|
| `canAccess(target)` | Kiểm tra caller hiện có thể truy cập member trên target không | Trả về `false` |
| `trySetAccessible()` | Thử bật accessible flag để bỏ qua kiểm tra Java access control | Trả về `false` nếu không thể bật |
| `setAccessible(true)` | Yêu cầu bật accessible flag | Ném `InaccessibleObjectException` nếu không thể bật |

`canAccess()` là phép kiểm tra, không phải yêu cầu cấp quyền. `trySetAccessible()` mới là thao tác thử bật accessible flag.

Ví dụ với field instance:

```java
Field field = User.class.getDeclaredField("email");

boolean accessibleBefore = field.canAccess(user);
boolean enabled = field.trySetAccessible();
boolean accessibleAfter = field.canAccess(user);
```

Với field instance hoặc instance method, đối số phải là object thuộc declaring class hoặc lớp con phù hợp. Với static field, static method và constructor, truyền `null`:

```java
Field counter = Metrics.class.getDeclaredField("count");
boolean canRead = counter.canAccess(null);

Constructor<User> constructor =
        User.class.getDeclaredConstructor(String.class);
boolean canCreate = constructor.canAccess(null);
```

Nếu truyền sai loại receiver, `canAccess()` ném `IllegalArgumentException`. Đừng truyền `null` cho instance field hoặc instance method.

### 2.1. Không dùng isAccessible

`AccessibleObject.isAccessible()` đã deprecated từ Java 9. Tên phương thức dễ gây hiểu lầm: nó trả về trạng thái accessible flag đã được bật hay chưa, không trả lời trực tiếp caller có quyền truy cập member hay không.

Khi cần kiểm tra quyền truy cập hiện tại, dùng `canAccess(target)`. Khi cần thử bật quyền deep reflection, dùng `trySetAccessible()`.

Không dùng `isAccessible()` trong code mới.

## 3. Khi nào trySetAccessible có thể thành công?

Quyền bật accessible flag phụ thuộc vào caller, declaring class, member và module chứa package. Những trường hợp chính được API quy định gồm:

- Caller và declaring class nằm trong cùng module.
- Member là public, declaring class là public và package được export tới module của caller.
- Member là protected static, declaring class là public, package được export tới caller và caller là subclass phù hợp.
- Package chứa declaring class được mở cho module của caller.

Các package thuộc unnamed module và open module được xem là mở cho mọi module ở runtime. Điều này giải thích vì sao reflection trên classpath thường dễ hoạt động hơn trên named module, nhưng không nên dựa vào hành vi classpath khi triển khai một ứng dụng modular.

Với deep reflection vào private member của một class thuộc module khác, trường hợp cần quan tâm nhất là package phải được mở cho module đang gọi.

### 3.1. Export không thay thế opens

Ví dụ module domain:

```java
module com.example.domain {
    exports com.example.domain.model;
}
```

Module reflector:

```java
module com.example.reflector {
    requires com.example.domain;
}
```

Module reflector có thể import public type trong package `com.example.domain.model`. Nhưng package chỉ được export; nó chưa được mở cho deep reflection. Nếu `User` có private field `email`, lời gọi `trySetAccessible()` từ module reflector có thể trả về `false`.

Để cho phép reflection sâu, module domain có thể khai báo qualified opens:

```java
module com.example.domain {
    exports com.example.domain.model;
    opens com.example.domain.model to com.example.reflector;
}
```

Giờ đây module `com.example.reflector` có thể yêu cầu quyền truy cập sâu vào member trong package đó. Các module khác không tự động nhận quyền tương tự.

### 3.2. Mở package ở runtime

Khi chưa thể sửa module descriptor của thư viện, có thể dùng launcher option `--add-opens` để mở một package cụ thể cho module đích:

```text
java --add-opens com.example.domain/com.example.domain.model=com.example.reflector ...
```

Nếu framework chạy trên classpath, module đích là `ALL-UNNAMED`:

```text
java --add-opens com.example.domain/com.example.domain.model=ALL-UNNAMED -jar application.jar
```

`--add-opens` là cấu hình runtime. Nó không thay đổi source code hay biến package thành API compile-time. Chỉ mở đúng package và đúng module thực sự cần reflection; ghi nhận flag như một cấu hình triển khai có chủ sở hữu và kế hoạch loại bỏ khi dependency đã được cập nhật.

Không dùng `--illegal-access` làm cách mở quyền trong Java hiện đại. Cơ chế chuyển tiếp đó đã lỗi thời và không còn cấp quyền truy cập như các JDK cũ.

JDK internals cũng chịu strong encapsulation. Java 16 áp dụng mặc định chặt hơn cho phần lớn internal API qua JEP 396; Java 17 tiếp tục hoàn tất thay đổi này qua JEP 403. `trySetAccessible()` không tự mở package của `java.base` hoặc module JDK khác. Nếu framework đang truy cập private member trong JDK, hãy ưu tiên nâng cấp framework và dùng API được tài liệu hóa; chỉ xem `--add-opens` là cấu hình chuyển tiếp hẹp khi đã xác định chính xác package và module cần quyền.

## 4. Xử lý khi trySetAccessible trả về false

Kết quả `false` là một nhánh xử lý bình thường của API, không phải lỗi runtime bất ngờ. Framework nên quyết định rõ việc tiếp tục, dùng fallback hay dừng với thông báo có ích.

Ví dụ class domain có accessor công khai:

```java
package com.example.domain.model;

public final class User {
    private final String email;

    public User(String email) {
        this.email = email;
    }

    public String email() {
        return email;
    }
}
```

Một thành phần reflection có thể ưu tiên đọc private field khi package đã mở, và dùng accessor nếu chưa được cấp quyền:

```java
package com.example.reflector;

import com.example.domain.model.User;
import java.lang.reflect.Field;
import java.util.Optional;

public final class UserInspector {
    public static Optional<String> readEmail(User user)
            throws NoSuchFieldException, IllegalAccessException {
        Field field = User.class.getDeclaredField("email");

        if (!field.canAccess(user) && !field.trySetAccessible()) {
            return Optional.ofNullable(user.email());
        }

        return Optional.ofNullable((String) field.get(user));
    }
}
```

Ví dụ này minh họa fallback. Trong một ứng dụng thực tế, nếu accessor đã là hợp đồng phù hợp thì nên gọi accessor trực tiếp, không cần reflection. Reflection chỉ nên được dùng khi thư viện thật sự phải làm việc với metadata hoặc kiểu chưa biết trước.

### 4.1. Khi không có fallback phù hợp

Nếu framework bắt buộc phải đọc private field và không có API thay thế, hãy dừng sớm với lỗi nêu rõ package và module cần mở:

```java
Field field = User.class.getDeclaredField("email");

if (!field.trySetAccessible()) {
    Module targetModule = User.class.getModule();
    Module callerModule = UserInspector.class.getModule();

    throw new IllegalStateException(
            "Cannot access " + field
            + "; package " + User.class.getPackageName()
            + " in module " + targetModule.getName()
            + " must be opened to " + callerModule.getName()
    );
}
```

Thông báo này giúp người vận hành biết cần kiểm tra module descriptor hoặc cấu hình `--add-opens` nào. Tránh thông báo chung chung như “reflection failed”, vì nguyên nhân có thể là module chưa mở, field không tồn tại hoặc caller dùng sai receiver.

### 4.2. Phân biệt false với exception

| Tình huống | Cách xử lý |
|---|---|
| `trySetAccessible()` trả `false` | Không tiếp tục truy cập private member; fallback hoặc báo lỗi cấu hình |
| `setAccessible(true)` không thể bật quyền | Có thể ném `InaccessibleObjectException` |
| `Field.get()` không có quyền truy cập cần thiết | Ném `IllegalAccessException` |
| Không tìm thấy field/method/constructor | Ném `NoSuchFieldException`, `NoSuchMethodException` hoặc lỗi tương ứng |
| `canAccess()` nhận receiver sai | Ném `IllegalArgumentException` |

Nếu đã chọn `trySetAccessible()`, hãy xử lý boolean return trước khi gọi `get()`, `set()` hoặc `invoke()`. Không nên gọi `setAccessible(true)` chỉ để thay một kết quả boolean bằng exception mà code không xử lý.

## 5. Kiểm tra trạng thái module bằng Module.isOpen

Khi framework cần chẩn đoán module access, có thể kiểm tra package có được mở cho module caller không:

```java
Module targetModule = User.class.getModule();
Module callerModule = UserInspector.class.getModule();

String packageName = User.class.getPackageName();

boolean opened = targetModule.isOpen(packageName, callerModule);

System.out.println("Package opened to caller: " + opened);
```

`Module.isOpen(packageName, otherModule)` trả về `true` khi package được mở cho module đích, kể cả trường hợp mở qualified. Nếu cần kiểm tra quyền export source-level, dùng `isExported()`; nhưng `isExported()` không phải phép kiểm tra thay thế cho deep reflection. Khi câu hỏi là private member có thể được mở cho reflection hay không, hãy kiểm tra `isOpen()`.

Có thể dùng thông tin này trong diagnostic log:

- Tên module chứa class.
- Tên module caller.
- Package chứa member.
- Trạng thái `isOpen`.
- Tên member mà framework đang cố truy cập.

Không ghi giá trị private của field vào log chỉ để chẩn đoán quyền truy cập.

## 6. Áp dụng cho Method và Constructor

`trySetAccessible()` không chỉ dùng với field. Framework có thể cần gọi private method hoặc constructor khi tích hợp với một thư viện cũ hoặc cơ chế plugin.

Ví dụ private method:

```java
Method method = User.class.getDeclaredMethod("normalizeEmail");

if (!method.trySetAccessible()) {
    throw new IllegalStateException(
            "Package is not open for private method access");
}

Object normalized = method.invoke(user);
```

Ví dụ private constructor:

```java
Constructor<User> constructor =
        User.class.getDeclaredConstructor(String.class);

if (!constructor.trySetAccessible()) {
    throw new IllegalStateException(
            "Package is not open for constructor access");
}

User user = constructor.newInstance("dev@example.com");
```

Cả hai ví dụ đều cần import các lớp reflection tương ứng. Khi gọi `Method.invoke()`, lỗi từ method đích được bọc trong `InvocationTargetException`. Framework nên kiểm tra cause để phân biệt lỗi nghiệp vụ với lỗi reflection.

Nếu có thể tạo object qua public constructor, factory method hoặc dependency injection API, ưu tiên các điểm mở rộng công khai đó thay vì gọi private constructor.

## 7. trySetAccessible không đồng nghĩa có thể sửa mọi field

Bật accessible flag chỉ liên quan đến kiểm tra truy cập. Nó không bảo đảm mọi thao tác đọc/ghi đều hợp lệ.

Các field không thể được sửa bằng reflection theo cách thông thường gồm:

- `static final` field.
- `final` field trong record.
- `final` field của hidden class.

Đặc biệt với record, các component được thiết kế để mang dữ liệu bất biến sau khi khởi tạo. Nếu cần tạo record với giá trị khác, gọi canonical constructor thay vì tìm cách ghi vào field private:

```java
public record UserView(String email, boolean active) {}

UserView view = new UserView("dev@example.com", true);
```

### 7.1. Lưu ý thay đổi từ JDK 26 về final field

Từ JDK 26, việc sửa một instance field `final` bằng deep reflection tạo cảnh báo runtime theo JEP 500. Mặc định, thao tác còn được cho phép trong giai đoạn chuẩn bị, nhưng một JDK tương lai sẽ chặn mutation này nếu không được bật rõ ràng.

Điều này có nghĩa thư viện không nên dùng `trySetAccessible()` rồi `Field.set()` để thay đổi field final như một kỹ thuật khởi tạo object thông thường. Cảnh báo JDK 26 là tín hiệu cần nâng cấp thư viện hoặc thay đổi cách tạo object. Các tùy chọn cho phép mutation chỉ nên được xem là biện pháp tương thích có kiểm soát trong quá trình migration, không phải thiết kế mặc định cho ứng dụng mới.

Khi làm việc với record hoặc immutable object, hãy dùng constructor, factory, builder hoặc API deserialization có hỗ trợ mô hình bất biến. Với field mutable không final, chỉ ghi khi package đã mở và hợp đồng của thư viện cho phép thay đổi trạng thái đó.

## 8. Khi nào nên dùng Method Handles?

Một số framework cần một cơ chế truy cập member có thể tái sử dụng thay vì gọi reflection lặp đi lặp lại. Method Handles có thể là lựa chọn phù hợp nếu ứng dụng cần một lookup có quyền rõ ràng.

`MethodHandles.privateLookupIn()` có thể tạo lookup với quyền private trong class đích khi các điều kiện module được đáp ứng. Nếu class thuộc module khác, package phải được mở cho module caller và caller cần đọc module chứa class đích.

Ví dụ khái quát:

```java
MethodHandles.Lookup lookup = MethodHandles.privateLookupIn(
        User.class,
        MethodHandles.lookup()
);

VarHandle emailHandle = lookup.findVarHandle(
        User.class,
        "email",
        String.class
);

String email = (String) emailHandle.get(user);
```

Method Handles không phải đường vòng để bỏ qua `opens`. Chúng vẫn tuân theo quyền lookup và module access. Hãy chọn reflection khi cần metadata linh hoạt; chọn Method Handles khi cần handle có kiểu rõ ràng và được tạo một lần để tái sử dụng.

## 9. Kiểm thử trường hợp được cấp và bị từ chối quyền

Một test chạy hoàn toàn trên classpath có thể không tái hiện đúng lỗi module encapsulation vì unnamed module có các package mở rộng rãi cho reflection. Để kiểm tra tình huống bị từ chối do module, hãy chạy test với named module trên module path.

Giả sử module domain export package model nhưng không mở package:

```java
module com.example.domain {
    exports com.example.domain.model;
}
```

Module test/reflector đọc module domain:

```java
module com.example.reflector {
    requires com.example.domain;
    requires org.junit.jupiter.api;
}
```

Test kiểm tra private field không thể bật accessible flag:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;

import com.example.domain.model.User;
import java.lang.reflect.Field;
import org.junit.jupiter.api.Test;

class TrySetAccessibleDeniedTest {
    @Test
    void returnsFalseWhenPackageIsNotOpen() throws Exception {
        User user = new User("dev@example.com");
        Field field = User.class.getDeclaredField("email");

        assertFalse(field.canAccess(user));
        assertFalse(field.trySetAccessible());
    }
}
```

Sau đó thêm qualified opens trong module domain:

```java
module com.example.domain {
    exports com.example.domain.model;
    opens com.example.domain.model to com.example.reflector;
}
```

Test thành công:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.domain.model.User;
import java.lang.reflect.Field;
import org.junit.jupiter.api.Test;

class TrySetAccessibleAllowedTest {
    @Test
    void enablesAccessWhenPackageIsOpen() throws Exception {
        User user = new User("dev@example.com");
        Field field = User.class.getDeclaredField("email");

        assertTrue(field.trySetAccessible());
        assertEquals("dev@example.com", field.get(user));
    }
}
```

Hai test cần được chạy trong hai cấu hình module tương ứng. Không thể kỳ vọng test denied vẫn trả false sau khi package đã được mở cho module test.

## 10. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Gọi `setAccessible(true)` rồi giả định luôn thành công | Module có thể không mở package | Dùng `trySetAccessible()` và xử lý `false` |
| Dùng `canAccess()` như thao tác cấp quyền | Đây chỉ là phép kiểm tra hiện trạng | Gọi `trySetAccessible()` khi cần deep reflection |
| Truyền `null` cho instance field | Receiver không hợp lệ | Truyền object đúng kiểu; chỉ dùng null cho static member/constructor |
| Nhầm `exports` với `opens` | Export không cấp deep reflection vào private member | Mở package cho module framework |
| Mở toàn bộ module cho mọi framework | Tăng bề mặt truy cập không cần thiết | Dùng qualified `opens` |
| Bắt mọi exception rồi tiếp tục | Có thể che lỗi thiếu field hoặc lỗi nghiệp vụ | Phân biệt lỗi module, lookup và lỗi khi gọi member |
| Dùng `isAccessible()` | API deprecated và tên gây hiểu nhầm | Dùng `canAccess()` |
| Dùng reflection để sửa record component | Field của record không thể được sửa theo cách này | Tạo record mới qua constructor |
| Dùng reflection sửa final field thông thường | JDK 26 phát cảnh báo và sẽ siết chặt hơn | Loại bỏ final-field mutation |
| Nghĩ Method Handles bỏ qua module access | Lookup vẫn phải có quyền thích hợp | Cấp `opens` hẹp hoặc dùng API công khai |

## 11. Quy trình xử lý lỗi truy cập

Khi `trySetAccessible()` trả về `false` hoặc framework nhận `InaccessibleObjectException`, hãy làm theo thứ tự:

1. Xác định chính xác member cần truy cập: field, method hay constructor.
2. Xác định module chứa declaring class và module caller.
3. Kiểm tra package có được export hay open cho caller không.
4. Xác định nhu cầu thực sự là truy cập public API hay deep reflection.
5. Tìm accessor, constructor, factory hoặc SPI công khai có thể thay thế.
6. Nếu deep reflection là yêu cầu hợp lệ, thêm qualified `opens` trong module descriptor hoặc `--add-opens` runtime có phạm vi hẹp.
7. Chạy integration test trên module path với JDK mục tiêu.
8. Kiểm tra framework có đang sửa `final` field hay không; xử lý cảnh báo JDK 26 nếu có.
9. Ghi lại module/package cần quyền trong tài liệu triển khai và loại bỏ cấu hình tạm khi dependency đã được nâng cấp.

Không mở package trước khi biết module nào thực sự cần quyền. Điều đó giúp cấu hình dễ kiểm tra và tránh cấp quyền sâu ngoài phạm vi nghiệp vụ.

## 12. Checklist sử dụng trySetAccessible

Trước khi đưa reflection vào ứng dụng, hãy kiểm tra:

1. Có thể dùng public accessor hoặc constructor thay reflection không?
2. Member cần truy cập có thực sự private/protected không?
3. Đã gọi `trySetAccessible()` và xử lý cả hai kết quả true/false chưa?
4. `canAccess()` có nhận đúng receiver cho instance/static member không?
5. Module caller và module chứa class đã được xác định chưa?
6. Package có được mở đúng cho module caller không?
7. Có thể dùng qualified `opens` thay vì mở rộng toàn module không?
8. Có phân biệt `exports` với `opens` không?
9. Có test trên named module path không?
10. Có tránh mutation đối với record component và field final không?
11. Framework có ghi log đủ module/package để chẩn đoán mà không lộ dữ liệu nhạy cảm không?
12. Có kế hoạch thay thế reflection nội bộ bằng API được hỗ trợ không?

## 13. Bài tập vận dụng

**Bài 1 — canAccess và trySetAccessible:** Tạo class `Account` có private field `status`. Gọi `canAccess(account)` trước và sau `trySetAccessible()`. Giải thích vì sao hai kết quả thay đổi.

**Bài 2 — Module không mở package:** Tạo hai named module `domain` và `reflector`. Export package chứa `Account` nhưng không mở package. Viết test chứng minh `trySetAccessible()` trả false cho private field.

**Bài 3 — Qualified opens:** Mở package cho riêng module `reflector`. Chạy lại test và kiểm tra `trySetAccessible()` trả true. Thử từ module thứ ba để xác minh quyền không được cấp đại trà.

**Bài 4 — Fallback:** Viết một inspector ưu tiên reflection nhưng dùng accessor công khai khi quyền không được cấp. Kiểm tra cả hai cấu hình module.

**Bài 5 — Record và final field:** Tạo record `AccountView`, thử đọc component bằng accessor và phân tích vì sao không nên dùng reflection để sửa field. Kiểm tra log khi thư viện cũ mutation final field trên JDK 26.

---

## Tài liệu tham khảo

- [AccessibleObject — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `canAccess`, `setAccessible` và quy tắc truy cập module.
- [Field — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html): đọc/ghi field, quyền reflection và hạn chế với final field.
- [Module — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): `isOpen`, `isExported` và trạng thái module.
- [JLS — Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html): ngữ nghĩa `exports` và `opens`.
- [MethodHandles — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): `privateLookupIn` và lookup access.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396): strong encapsulation mặc định trong Java 16.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation trong Java 17 trở lên.
- [JEP 500 — Prepare to Make Final Mean Final](https://openjdk.org/jeps/500): cảnh báo và lộ trình hạn chế mutation final field bằng deep reflection từ JDK 26.

---

**Ghi nhớ:** `trySetAccessible()` là cách thử cấp quyền reflection có kiểm soát: true nghĩa là accessible flag đã bật, false nghĩa là không thể bật theo module/access rules. Với private member của module khác, package cần được mở cho đúng module caller. Hãy ưu tiên API công khai, xử lý false như một nhánh bình thường và tránh sửa final field bằng reflection.
