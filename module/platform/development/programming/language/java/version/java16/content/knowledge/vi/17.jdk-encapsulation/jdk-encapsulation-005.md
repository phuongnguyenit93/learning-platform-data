# Khác biệt giữa truy cập thông thường và deep reflection

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Đóng gói JDK  
**Áp dụng:** Java 16 trở lên; module system và reflection tiếp tục áp dụng trong các JDK hiện đại.

Java module system phân biệt việc một module công khai API cho module khác sử dụng với việc cho phép framework truy cập sâu vào các thành viên không công khai bằng reflection. Hai cơ chế thường bị nhầm là `exports` và `opens`.

- **Truy cập thông thường:** tuân theo quy tắc truy cập Java. Module đích cần đọc module nguồn; package chứa kiểu public phải được export cho module đích.
- **Deep reflection:** cho phép framework vượt qua kiểm tra truy cập Java thông thường để đọc hoặc gọi thành viên `private`, `protected` hoặc package-private. Package chứa thành viên phải được mở cho module gọi reflection, trừ trường hợp module gọi và module khai báo thành viên là cùng một module.

Việc gọi `getDeclaredField()` hoặc `getDeclaredMethod()` chỉ tìm thấy thành viên được khai báo; bản thân thao tác này không tự cấp quyền truy cập vào thành viên private. Khi framework cần bỏ qua kiểm tra truy cập, module system và trạng thái encapsulation của package vẫn được áp dụng.

## 1. Truy cập thông thường là gì?

Truy cập thông thường sử dụng API mà module chủ động công khai. Ví dụ, một module thư viện export package API:

```java
module com.example.domain {
    exports com.example.domain.api;
}
```

Module client có thể khai báo dependency:

```java
module com.example.client {
    requires com.example.domain;
}
```

Sau đó sử dụng các kiểu public trong package đã export:

```java
import com.example.domain.api.Customer;

public final class CustomerService {
    public String displayName(Customer customer) {
        return customer.displayName();
    }
}
```

Ở đây:

- Module `com.example.client` đọc module `com.example.domain` nhờ `requires`.
- Package `com.example.domain.api` được export.
- Kiểu và thành viên public có thể được truy cập theo quy tắc Java thông thường.
- Thành viên `private` bên trong `Customer` vẫn được bảo vệ.

`exports` không biến mọi thành viên của package thành public. Nó chỉ làm package có thể được truy cập theo quy tắc truy cập thông thường; modifier `public`, `protected`, package-private và `private` vẫn có ý nghĩa.

## 2. Reflection thông thường vẫn tuân theo kiểm tra truy cập

Reflection API có thể tìm và gọi public member mà không cần mở package cho deep reflection:

```java
import java.lang.reflect.Method;

static Object callPublicMethod(Object target) throws ReflectiveOperationException {
    Method method = target.getClass().getMethod("displayName");
    return method.invoke(target);
}
```

`getMethod()` tìm public method, còn `Method.invoke()` vẫn thực hiện kiểm tra quyền truy cập. Nếu class và method public nằm trong package được export phù hợp, thao tác reflection thông thường có thể thực hiện mà không cần `setAccessible(true)`.

Điều này gần với việc gọi public method trực tiếp trong mã Java. Reflection thay đổi cách chương trình tìm và gọi thành viên ở runtime; nó không mặc định tắt module encapsulation.

## 3. Deep reflection vượt qua kiểm tra truy cập như thế nào?

Deep reflection thường được framework dùng khi cần:

- Đọc hoặc ghi field `private` để ánh xạ object.
- Gọi constructor hoặc method không public.
- Tạo object từ dữ liệu mà không gọi constructor/factory public.
- Thực hiện serialization, dependency injection hoặc mapping dựa trên metadata nội bộ.

Ví dụ một framework tìm field private:

```java
import java.lang.reflect.Field;

static Object readPrivateField(Object target, String fieldName)
        throws ReflectiveOperationException {
    Field field = target.getClass().getDeclaredField(fieldName);

    if (!field.trySetAccessible()) {
        throw new IllegalAccessException(
            "Package is not open for deep reflection: "
                + field.getDeclaringClass().getPackageName()
        );
    }

    return field.get(target);
}
```

`getDeclaredField()` tìm field do class khai báo, kể cả field không public. `trySetAccessible()` yêu cầu JVM cho phép bỏ qua kiểm tra truy cập. Chỉ khi thao tác này thành công thì framework mới có thể đọc field private theo cách trên.

Deep reflection là quyền được module system kiểm soát. Nó không phải cách truy cập tùy ý mọi field của mọi class trong JVM.

## 4. Phân biệt exports và opens

`exports` và `opens` phục vụ hai mục đích khác nhau:

| Cơ chế | Truy cập thông thường | Deep reflection | Thời điểm áp dụng |
| --- | --- | --- | --- |
| `exports p` | Có, cho public/protected API theo quy tắc Java | Không tự cấp quyền truy cập private | Compile time và runtime |
| `exports p to m` | Có, chỉ cho module `m` | Không tự cấp quyền truy cập private | Compile time và runtime |
| `opens p` | Không cấp quyền truy cập Java thông thường khi package chưa export | Có, cho deep reflection từ các module khác | Runtime |
| `opens p to m` | Không cấp quyền truy cập Java thông thường | Có, chỉ cho module `m` | Runtime |
| `open module x` | Không tự export package cho mã Java khác | Mở tất cả package của module cho deep reflection | Runtime |

Ví dụ module công khai API và chỉ mở một package nội bộ cho framework:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.internal to com.example.mapper;
}
```

Ý nghĩa:

- Client Java thông thường sử dụng API trong `com.example.domain.api`.
- Framework module `com.example.mapper` có thể dùng deep reflection trên các class trong `com.example.domain.internal`.
- Các package khác vẫn được đóng kín đối với deep reflection từ module khác.

`opens` không thay thế `exports`. Nếu mã nguồn cần import và gọi trực tiếp một kiểu public từ package, package đó phải được export theo module graph. Ngược lại, nếu framework chỉ cần deep reflection tại runtime, mở đúng package là cơ chế phù hợp hơn export toàn package.

## 5. Ví dụ module mở đúng package cho framework

Giả sử ứng dụng có hai module:

```text
com.example.domain
  ├── com.example.domain.api
  └── com.example.domain.internal

com.example.mapper
  └── framework ánh xạ object bằng reflection
```

Module domain:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.internal to com.example.mapper;
}
```

Module framework đọc module domain để nhận các kiểu public API và object được chuyển qua API:

```java
module com.example.mapper {
    requires com.example.domain;
}
```

Class nội bộ:

```java
package com.example.domain.internal;

public final class Account {
    private final String accountNumber;

    public Account(String accountNumber) {
        this.accountNumber = accountNumber;
    }
}
```

Framework trong module `com.example.mapper` nhận object `Account` qua một API hoặc callback, sau đó đọc field:

```java
package com.example.mapper;

import java.lang.reflect.Field;

public final class AccountMapper {
    public static String readAccountNumber(Object account)
            throws ReflectiveOperationException {
        Field field = account.getClass().getDeclaredField("accountNumber");
        if (!field.trySetAccessible()) {
            throw new IllegalAccessException("Cannot access accountNumber");
        }
        return (String) field.get(account);
    }
}
```

Package `com.example.domain.internal` không cần export chỉ để framework deep-reflect vào field private. Directive `opens ... to com.example.mapper` cấp đúng quyền reflection cho module được chỉ định.

Trong thiết kế thực tế, nếu framework cần tạo object, hãy cân nhắc constructor/factory public hoặc SPI trước. Deep reflection tạo coupling vào cấu trúc nội bộ của class; đổi tên field hoặc thay đổi constructor có thể phá cấu hình framework.

## 6. trySetAccessible, setAccessible và canAccess

Các API hiện hành nên dùng:

| API | Hành vi |
| --- | --- |
| `trySetAccessible()` | Thử bỏ qua kiểm tra truy cập; trả `true` nếu thành công, `false` nếu module access không cho phép |
| `setAccessible(true)` | Yêu cầu bỏ qua kiểm tra truy cập; có thể ném `InaccessibleObjectException` nếu không được phép |
| `canAccess(target)` | Kiểm tra caller hiện có thể truy cập member trên target hay không |
| `getDeclaredField()` / `getDeclaredMethod()` | Tìm member được khai báo, không tự bỏ qua kiểm tra truy cập |

Ví dụ xử lý `trySetAccessible()`:

```java
Field field = type.getDeclaredField("secret");

if (field.canAccess(instance)) {
    Object value = field.get(instance);
} else if (field.trySetAccessible()) {
    Object value = field.get(instance);
} else {
    throw new IllegalAccessException(
        "The declaring package is not open to this module"
    );
}
```

Với static field hoặc constructor, đối số target của `canAccess()` phải là `null`. Với instance field hoặc method, truyền đúng object tương ứng. Truyền target không đúng loại hoặc dùng `null` cho instance member sẽ gây `IllegalArgumentException`.

Không dựa vào `isAccessible()` trong code mới; API này đã deprecated từ Java 9 và không diễn đạt đúng câu hỏi “caller có thể truy cập member hay không”. Dùng `canAccess()` và `trySetAccessible()` để thể hiện ý định rõ ràng.

## 7. InaccessibleObjectException và cách xử lý

Khi code gọi `setAccessible(true)` nhưng module không mở package cần thiết, JVM có thể ném `InaccessibleObjectException`:

```java
import java.lang.reflect.Field;

static Object readStringInternals(String value)
        throws ReflectiveOperationException {
    Field field = String.class.getDeclaredField("value");
    field.setAccessible(true); // Có thể ném InaccessibleObjectException.
    return field.get(value);
}
```

Ví dụ này chỉ nhằm minh họa hành vi bị chặn. Không dùng reflection vào field nội bộ của `String` trong ứng dụng production. Cấu trúc nội bộ của JDK không phải API ổn định; kiểu lưu trữ có thể thay đổi giữa các phiên bản.

Khi gặp exception:

1. Xác định class/module khai báo member.
2. Xác định package chứa member.
3. Xác định module gọi reflection.
4. Kiểm tra package có được mở cho module gọi hay không.
5. Ưu tiên API public hoặc cơ chế mở package có phạm vi nhỏ.
6. Chỉ dùng `--add-opens` như biện pháp chuyển tiếp khi chưa thể sửa module descriptor hoặc thư viện.

Không bắt `InaccessibleObjectException` rồi tiếp tục như thể field đã được đọc thành công. Nếu framework không thể hoạt động khi thiếu quyền reflection, báo lỗi cấu hình với tên module/package cần mở.

## 8. Dùng --add-opens khi cần cấu hình lúc khởi chạy

`--add-opens` mở một package của module nguồn cho module đích tại runtime:

```sh
java --add-opens com.example.domain/com.example.domain.internal=com.example.mapper \
     -m com.example.app/com.example.app.Main
```

Nếu framework chạy trên classpath (thuộc unnamed module), có thể dùng target `ALL-UNNAMED`:

```sh
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -jar legacy-app.jar
```

Đối số có dạng:

`--add-opens source-module/package=target-module`

Ví dụ trên mở `java.lang` trong `java.base` cho tất cả unnamed modules. Đây là quyền rộng; chỉ dùng khi thư viện cũ thực sự cần và có kế hoạch loại bỏ. Với ứng dụng module hóa, ưu tiên mở package cho đúng module framework thay vì `ALL-UNNAMED`.

`--add-opens` là tùy chọn runtime. Nó không làm package có thể được import trực tiếp trong mã nguồn như một package đã export.

## 9. Đừng nhầm --add-opens với --add-exports

Hai tùy chọn có mục đích khác nhau:

| Tùy chọn | Cấp quyền gì? | Có cho deep reflection private không? |
| --- | --- | --- |
| `--add-exports source/package=target` | Cho phép truy cập thông thường tới public types/members trong package | Không |
| `--add-opens source/package=target` | Mở package cho deep reflection tại runtime | Có |

Ví dụ:

- Một thư viện cần import public class trong package chưa export: xem xét `--add-exports` hoặc sửa module descriptor.
- Một framework cần truy cập private field qua reflection: cần package được `opens` hoặc `--add-opens`.

Không dùng `--add-exports` để chữa `InaccessibleObjectException` khi framework cần truy cập private member. Tùy chọn này không mở package cho deep reflection.

## 10. Strong encapsulation của JDK hiện đại

Java 16 đặt strong encapsulation của các thành phần nội bộ JDK làm mặc định theo JEP 396. Java 17 tiếp tục mạnh hóa việc đóng gói các internal API theo JEP 403. Vì vậy, ứng dụng không nên dựa vào việc reflection có thể truy cập tùy ý các package nội bộ như `java.lang`, `java.util` hoặc các package implementation khác.

Điểm cần nhớ:

- Public API được tài liệu hóa là hợp đồng tương thích mà ứng dụng nên dùng.
- Internal package/class không phải API ổn định dù có thể tìm thấy bằng reflection ở một runtime cụ thể.
- `--add-opens` có thể hỗ trợ migration cho thư viện cũ, nhưng tạo phụ thuộc vào chi tiết implementation.
- `--illegal-access` không còn là cách mở rộng quyền truy cập hữu ích trên JDK hiện đại; từ Java 17 tùy chọn này không khôi phục hành vi truy cập reflection cũ.
- Một số API nội bộ đặc biệt vẫn được duy trì vì lý do tương thích, nhưng không nên xem đó là lời mời sử dụng internal API mới.

Không xây kiến trúc mới dựa trên việc đọc field private của class thuộc JDK. Hãy tìm API public, API chuẩn thay thế hoặc nâng cấp framework đã hỗ trợ module system.

## 11. Khi nào nên dùng opens trong module-info.java?

Ưu tiên directive `opens` có phạm vi cụ thể khi module của bạn chủ động hỗ trợ framework:

```java
module com.example.application {
    requires com.example.mapper;

    exports com.example.application.api;
    opens com.example.application.persistence to com.example.mapper;
}
```

Chỉ package `com.example.application.persistence` được mở cho `com.example.mapper`. Package API khác vẫn tuân theo export và modifier truy cập bình thường.

Directive `open module` mở mọi package của module cho deep reflection:

```java
open module com.example.legacy {
    requires com.example.mapper;
}
```

Cách này hữu ích trong một số ứng dụng legacy cần framework reflection trên nhiều package, nhưng phạm vi rộng hơn đáng kể. Với module mới, dùng `opens package to framework.module` cho từng package cần thiết để giữ encapsulation rõ ràng.

Một module có `open` không tự động export package cho truy cập Java thông thường. Deep reflection và ordinary access vẫn là hai cơ chế riêng.

## 12. Chọn API thay thế deep reflection khi có thể

Deep reflection có chi phí bảo trì: framework phụ thuộc vào tên field, cấu trúc class và quyền mở package. Cân nhắc các lựa chọn:

| Nhu cầu | Lựa chọn nên ưu tiên |
| --- | --- |
| Đọc dữ liệu object | Getter hoặc public accessor |
| Tạo object | Constructor/factory public hoặc builder |
| Tích hợp framework | SPI, annotation processor hoặc cấu hình mapping được hỗ trợ |
| Truy cập private member có chủ đích trong cùng module | Reflection hoặc method handle với kiểm soát module rõ ràng |
| Truy cập API của JDK | Public Java SE API được tài liệu hóa |
| Kiểm tra phụ thuộc JDK internals | Phân tích dependency và nâng cấp thư viện |

`MethodHandles.privateLookupIn()` cũng chịu quy tắc module access; nó không phải lối tắt để vượt qua package chưa được mở. Nếu dùng method handles cho deep access, package phải mở cho module gọi và module của caller phải đọc module khai báo class đích.

## 13. Checklist chẩn đoán deep reflection

1. Thành viên cần truy cập là public API hay chi tiết private implementation?
2. Code đang dùng `getMethod()` hay `getDeclaredMethod()`/`getDeclaredField()`?
3. Có đang nhầm việc tìm thấy member với việc được phép truy cập member không?
4. Module nguồn đã export package cho ordinary access chưa?
5. Package đã mở cho đúng module framework khi cần deep reflection chưa?
6. `trySetAccessible()` trả về `false` hay `setAccessible(true)` ném `InaccessibleObjectException`?
7. Có thể dùng getter, constructor, factory hoặc SPI thay deep reflection không?
8. Nếu cần `--add-opens`, đã giới hạn đúng source package và target module chưa?
9. Có đang dùng `ALL-UNNAMED` quá rộng không?
10. Có nhầm `--add-exports` với `--add-opens` không?
11. Framework đã được nâng cấp để hỗ trợ Java module system chưa?
12. Ứng dụng có còn phụ thuộc JDK internal API không?

**Ghi nhớ:** Truy cập thông thường dựa trên `requires`, `exports` và modifier Java; deep reflection cần package được mở bằng `opens` hoặc `--add-opens`. `getDeclaredField()` chỉ tìm member, không cấp quyền truy cập. Dùng `trySetAccessible()` để kiểm tra khả năng mở quyền, xử lý `InaccessibleObjectException` đúng nguyên nhân và ưu tiên API public. Trên JDK hiện đại, strong encapsulation là mặc định; đừng dựa vào reflection tới JDK internals hoặc tùy chọn `--illegal-access` đã lỗi thời.

## Tài liệu chính thức

- [JEP 261 — Module System: exports, opens và module access](https://openjdk.org/jeps/261).
- [JEP 396 — Strongly Encapsulate JDK Internals by Default, Java 16](https://openjdk.org/jeps/396).
- [JEP 403 — Strongly Encapsulate JDK Internals, Java 17](https://openjdk.org/jeps/403).
- [Java SE 26 API — `AccessibleObject`, `trySetAccessible`, `canAccess` và `setAccessible`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [Java SE 26 API — `InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html).
- [Java SE 26 API — `Module`, `isExported` và `isOpen`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html).
- [Java SE 26 API — `MethodHandles.privateLookupIn`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup)).
