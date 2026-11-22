# `InaccessibleObjectException` và nguyên nhân không thể mở truy cập trong Java Reflection

Một đoạn reflection có thể tìm được `Field`, `Method` hoặc `Constructor` nhưng thất bại ngay tại `setAccessible(true)`:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make ... accessible:
  module java.base does not "opens java.lang" to unnamed module ...
```

Đây thường là dấu hiệu của **strong encapsulation (đóng gói mạnh) giữa các module**, nhất là khi thư viện cố phản chiếu sâu vào thành viên `private` của JDK hay của một *named module* khác. Cần phân biệt ba chuyện: **tìm thấy khai báo**, **được phép bỏ qua kiểm tra truy cập của ngôn ngữ Java**, và **thực sự đọc/ghi/gọi thành viên**. Tìm thấy một field bằng `getDeclaredField()` chưa cấp quyền đọc field đó.

Bài này trình bày ngữ nghĩa của `InaccessibleObjectException` trong Java 17+, cách `exports` và `opens` của Java Platform Module System (JPMS) tác động đến reflection, quy trình chẩn đoán, cách sửa đúng từ `module-info.java` và cách dùng `--add-opens` có giới hạn.

## 1. Khi nào xuất hiện `InaccessibleObjectException`?

`java.lang.reflect.InaccessibleObjectException` là **unchecked exception** (kế thừa `RuntimeException`). Nó biểu thị rằng chương trình **không thể yêu cầu bỏ qua Java language access checks** cho một đối tượng reflection, thường là với `AccessibleObject.setAccessible(true)`. Các đối tượng có liên quan gồm:

| Đối tượng | API thường kích hoạt lỗi | Định nghĩa điều muốn làm |
| --- | --- | --- |
| `Field` | `field.setAccessible(true)` | Xin cho phép đọc/ghi field dù kiểm tra truy cập thông thường sẽ chặn |
| `Method` | `method.setAccessible(true)` | Xin cho phép gọi method vượt qua access checks thông thường |
| `Constructor<?>` | `constructor.setAccessible(true)` | Xin cho phép gọi constructor vượt qua access checks thông thường |
| Mảng `AccessibleObject[]` | `AccessibleObject.setAccessible(array, true)` | Xin suppress access checks cho từng phần tử |

Đặc biệt, *exception này không có nghĩa field hoặc method không tồn tại*. Ví dụ `String.class.getDeclaredField("value")` có thể tìm được field `private` nội bộ, nhưng `setAccessible(true)` không nhất thiết thành công.

### Ba API, ba câu hỏi khác nhau

- `getDeclaredField("x")`, `getDeclaredMethod(...)`: **có khai báo như vậy không?** Thường trả về metadata mà chưa cho phép thao tác member.
- `canAccess(receiver)`: **với caller và receiver hiện tại, thao tác reflective có vượt được access check không?** Có thể trả `true` nếu thành viên vốn accessible hoặc việc suppress check đã được cho phép.
- `trySetAccessible()`: **thử yêu cầu suppress Java language access checks**; trả `true` khi thành công, `false` khi không thể mở truy cập theo các quy tắc cho phép của API (một lỗi khác như `SecurityException` vẫn có thể xảy ra trong môi trường áp dụng chính sách bảo mật).
- `setAccessible(true)`: yêu cầu tương tự `trySetAccessible()` nhưng có thể **ném `InaccessibleObjectException`** khi không thể bật quyền truy cập.

Cờ accessibility trên đối tượng `AccessibleObject` là cơ chế reflection; nó **không thay đổi** modifier gốc của class, field hay method. `private` vẫn là `private`. `setAccessible(false)` chỉ bật lại việc kiểm tra truy cập thông thường đối với đối tượng reflection đó.

## 2. Nguyên nhân nền tảng: thiếu quyền mở package cho đúng caller

JPMS (Java 9+) bổ sung ranh giới giữa các named module trên quy tắc `public`/`private` của ngôn ngữ. `requires` tạo quan hệ đọc module, `exports` cung cấp quyền sử dụng public API, còn `opens` cho phép yêu cầu bỏ qua Java access checks khi Reflection cần truy cập sâu. **`InaccessibleObjectException` phát sinh ở bước xin mở quyền**, không phải vì một field đã biến mất.

| Chính sách của package trong named module | Public API từ module khác | `setAccessible(true)` vào private member từ module khác |
| --- | --- | --- |
| Không `exports` hoặc `opens` | Không được phép theo đường Java thông thường | Bị chặn khi không có quyền hợp lệ khác |
| Chỉ `exports p` (có thể `to m`) | Có, với caller được phép và visibility hợp lệ | `exports` không đủ |
| Chỉ `opens p` (có thể `to m`) | Không tự cấp quyền `import` khi biên dịch | Có thể thành công với module caller được mở |
| Cả `exports` và `opens` | Có quyền API public và khả năng deep reflection theo phạm vi đã cấp | Có thể thành công |

Nếu sở hữu module `com.example.domain`, có thể `exports com.example.domain.api;` cho API chính thức và `opens com.example.domain.model to com.example.serializer;` cho serializer phải đọc private members. Nếu chọn `open module`, mọi package sẽ mở cho Reflection; trong body của `open module` không thêm `opens` từng package.

### Vì sao lỗi xuất hiện nhiều từ Java 17?

Các phiên bản JDK trước đây có những cơ chế tương thích để nhiều thư viện tiếp tục phản chiếu vào nội bộ JDK. Từ **Java 17 (JEP 403)**, đóng gói mạnh các internal JDK APIs là hành vi mặc định và tùy chọn legacy `--illegal-access` không còn bật lại cơ chế mở rộng truy cập cũ. Những thư viện vẫn gọi `setAccessible(true)` vào field/method thuộc package JDK chưa mở có thể gặp `InaccessibleObjectException`.

Ví dụ `java.lang` thuộc module `java.base`. Module này có public APIs thông dụng, nhưng việc nhìn thấy lớp `java.lang.String` **không** trao quyền đọc field `private` của `String`. Ngay cả khi sử dụng `String` bình thường, deep reflection vào cấu trúc nội bộ của nó có thể bị chặn.

## 3. Ví dụ Java 17+ có thể chạy và tái hiện lỗi

Lưu đoạn sau thành `DeepReflectionDemo.java`. Ví dụ cố tình thử truy cập field nội bộ của `String` để quan sát khác biệt giữa việc **tìm được khai báo** và việc **được phép mở truy cập**. Chương trình chỉ thử metadata/accessibility, không đọc hay sửa giá trị field `String`.

```java
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Modifier;

public class DeepReflectionDemo {
    public static void main(String[] args) throws Exception {
        Class<?> owner = String.class;
        Field field = owner.getDeclaredField("value");
        String receiver = "hello";

        System.out.println("module: " + owner.getModule().getName());
        System.out.println("field private: "
                + Modifier.isPrivate(field.getModifiers()));
        System.out.println("canAccess before: "
                + field.canAccess(receiver));

        boolean opened = field.trySetAccessible();
        System.out.println("trySetAccessible: " + opened);

        try {
            field.setAccessible(true);
            System.out.println("setAccessible: OK");
        } catch (InaccessibleObjectException ex) {
            System.out.println("setAccessible: InaccessibleObjectException");
        }

        System.out.println("canAccess after: "
                + field.canAccess(receiver));
    }
}
```

Biên dịch/chạy thông thường:

```bash
javac DeepReflectionDemo.java
java DeepReflectionDemo
```

Khi chưa có quyền mở package `java.lang` cho code ở *unnamed module* (classpath), kết quả điển hình trên Java 17+ là:

```text
module: java.base
field private: true
canAccess before: false
trySetAccessible: false
setAccessible: InaccessibleObjectException
canAccess after: false
```

- `getDeclaredField("value")` thành công vì API cho phép xem thông tin khai báo.
- `trySetAccessible()` trả `false`: không có quyền suppress access checks tới private field thuộc package JDK đó.
- `setAccessible(true)` yêu cầu cùng quyền nhưng ném exception. Đây là điểm xảy ra lỗi được mô phỏng trong bài.

Chạy lại cùng class **với đúng một package được mở**:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED DeepReflectionDemo
```

Kết quả dự kiến:

```text
module: java.base
field private: true
canAccess before: false
trySetAccessible: true
setAccessible: OK
canAccess after: true
```

Tùy chọn này mở `java.lang` của module `java.base` tới tất cả *unnamed modules*, gồm mã chạy trên classpath của ví dụ. Điều đó cho phép suppress checks tại runtime; **nó không biến field thành public** và không thay đổi `getModifiers()`. Tránh phụ thuộc trực tiếp vào `String.value` trong mã ứng dụng thật: cấu trúc nội bộ JDK không phải public contract ổn định.

## 4. Tách bốn nguyên nhân thường bị nhầm

### 4.1. Package thuộc module khác chưa `opens`

Triệu chứng: tên module và package nguồn xuất hiện trong thông báo, chẳng hạn:

```text
module com.example.domain does not "opens com.example.domain.model"
to module com.example.serializer
```

Đây là lỗi **mở package**. Sửa tại module sở hữu dữ liệu nếu có thể, ví dụ `opens com.example.domain.model to com.example.serializer;`. Đừng sửa ở module gọi bằng cách viết `opens` cho package không thuộc quyền sở hữu của nó.

### 4.2. Package `exports` nhưng không `opens`

Một method `public` của một class `public` có thể gọi theo cách bình thường từ module có quyền đọc/export; đồng thời field `private` của chính class đó vẫn không được truy cập sâu. Các framework JSON, ORM, dependency injection cần khởi tạo/điền field bằng reflection có thể gặp trường hợp này.

Sửa theo nhu cầu thực tế: API công khai → `exports`; truy cập private runtime bởi framework → `opens` thích hợp. Có thể dùng cả hai nếu hai nhu cầu cùng tồn tại.

### 4.3. Code không có quyền truy cập Java thông thường

Field `private` hoặc method package-private từ package/caller khác có thể gây `IllegalAccessException` khi **đọc/ghi/gọi mà không suppress access checks**. Trường hợp này không mặc định đồng nghĩa với `InaccessibleObjectException`.

Ví dụ `field.get(receiver)` có thể ném `IllegalAccessException` nếu checks đang bật. Nhưng `field.setAccessible(true)` mới là yêu cầu suppress; nếu module chặn yêu cầu đó thì `InaccessibleObjectException` xuất hiện.

### 4.4. Chạy bằng classpath, module path hoặc môi trường khác nhau

Trong unnamed module (mã classpath), một module có tên thường thấy caller đích là `ALL-UNNAMED` trong cấu hình `--add-opens`. Với named module, đích phải là **đúng tên module**, ví dụ `com.example.serializer`. Vì vậy một lệnh chạy được trong IDE nhưng không chạy trong production có thể do flags JVM, module path, module descriptors hoặc cách đóng gói khác nhau.

Nhớ rằng cấu hình build hoặc tham số của `javac` không nhất thiết cũng là tham số của JVM đang chạy. Quyền deep reflection cần được cấp trong **process runtime** thật sự có lỗi.

## 5. Chọn cách sửa: `module-info.java` hay runtime flag?

Khi bạn **sở hữu module đích**, cách rõ ràng nhất là công khai hợp đồng phản chiếu cần thiết trong `module-info.java`. Ví dụ module domain:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.mapper;
}
```

Giải thích: `com.example.mapper` là **tên module**, không phải tên package hoặc tên class. Nếu dự án sử dụng một framework được đóng gói thành named module, cần mở cho **module name mà framework thực sự sử dụng**. Đừng suy ra tên này từ artifact Maven một cách mù quáng: automatic module name và module name khai báo có thể khác artifact file name.

Khi bạn **không sở hữu module đích**, có thể dùng tùy chọn runtime hẹp nhất cho một vấn đề tương thích cụ thể:

```bash
java --add-opens com.example.domain/com.example.domain.model=com.example.mapper \
     --module-path mods \
     --module com.example.app/com.example.app.Main
```

Dấu `\` ở cuối dòng trong ví dụ là cách nối dòng cho shell kiểu POSIX; trên Windows PowerShell, hãy viết lệnh thành một dòng hoặc dùng cú pháp nối dòng của PowerShell. Tên module/package ở đây là **ví dụ cấu trúc**, chỉ dùng sau khi thay bằng tên có thật trong ứng dụng.

Đối với ứng dụng trên classpath:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
```

Cú pháp của tùy chọn:

```text
--add-opens SOURCE_MODULE/PACKAGE=TARGET_MODULE
```

Khi nhiều target, có thể khai báo phù hợp theo tài liệu JVM/version; thường chỉ cần module của framework/caller thật sự sử dụng, hoặc `ALL-UNNAMED` nếu thư viện nằm trên classpath. **Chỉ mở package thực sự cần**, vì mỗi `--add-opens` làm rộng phạm vi mã có thể sử dụng reflection để vượt qua các kiểm tra truy cập trong package đó.

### `--add-opens` khác `--add-exports` ra sao?

| Tùy chọn | Mục đích chính | Có tự cho phép suppress private access không? |
| --- | --- | --- |
| `--add-exports source/pkg=target` | Bổ sung quyền truy cập tới public types của package | Không |
| `--add-opens source/pkg=target` | Mở package cho reflection tại runtime | Có thể, theo quy tắc `AccessibleObject` |

**Không thay `--add-opens` bằng `--add-exports`** khi vấn đề là `setAccessible(true)` trên field `private`. Ngược lại, khi chương trình cần *compile/import* public class từ module không export, có thể phải giải quyết exports; `--add-opens` không làm cho mọi import compile-time hợp lệ.

Tốt hơn nữa, nếu có public API chính thức, hãy sử dụng public API hoặc phiên bản thư viện đã được cập nhật để tránh truy cập nội bộ. Flag tương thích nên được xem là giải pháp có kiểm soát, nhất là khi thư viện chạm nhiều gói JDK nội bộ.

## 6. Quy trình đọc stack trace để tìm đúng package và module

Một stack trace điển hình thường có thông điệp chứa:

```text
Unable to make <member> accessible:
module <source-module> does not "opens <source-package>"
to <caller-module>
```

Hãy trích đúng bốn dữ kiện: **thành viên bị truy cập**, **source module**, **source package**, **caller module**. Ví dụ: `java.lang.String.value`, `java.base`, `java.lang` và `unnamed module`. Khi thông báo nói `to unnamed module`, giải pháp runtime thường cần `ALL-UNNAMED`; khi nói `to module com.example.mapper`, cần nhắm tới đúng named module.

Có thể kiểm tra metadata tại runtime:

```java
Class<?> type = String.class;

Module sourceModule = type.getModule();
String packageName = type.getPackageName();
Module callerModule = DeepReflectionDemo.class.getModule();

System.out.println(sourceModule.getName());
System.out.println(packageName);
System.out.println(callerModule.isNamed());
System.out.println(sourceModule.isOpen(packageName, callerModule));
```

Đây là **đoạn minh họa dùng trong class `DeepReflectionDemo`**, không phải chương trình độc lập mới. Với ví dụ classpath chưa mở `java.lang`, `callerModule.isNamed()` là `false` và `sourceModule.isOpen("java.lang", callerModule)` là `false`. Khi thêm flag `--add-opens java.base/java.lang=ALL-UNNAMED`, phép kiểm tra `isOpen(packageName, callerModule)` trả `true`.

Nếu application được chia thành nhiều classloader/module layer hoặc nhiều Java processes, hãy kiểm tra đúng JVM process phát sinh exception. Các flags đã đặt cho process khác sẽ không giải quyết lỗi.

## 7. `canAccess()` và `trySetAccessible()`: cách dùng an toàn

Thay vì luôn gọi `setAccessible(true)` rồi để exception lan tới tận tầng ứng dụng, thư viện có thể chủ động thăm dò khả năng truy cập:

```java
import java.lang.reflect.Field;

public final class SafeFieldRead {
    public static Object read(Field field, Object receiver)
            throws IllegalAccessException {
        if (!field.canAccess(receiver) && !field.trySetAccessible()) {
            throw new IllegalStateException(
                    "Không thể mở reflection cho "
                    + field.getDeclaringClass().getName()
                    + "." + field.getName());
        }
        return field.get(receiver);
    }
}
```

Đây là **class tiện ích độc lập về cú pháp**; nó không bao gồm `main`. `receiver` phải hợp lệ với field: field instance cần một đối tượng thuộc class khai báo hoặc subtype phù hợp; field static dùng `null`. Truyền sai receiver có thể gây `IllegalArgumentException`. `trySetAccessible()` trả `false` khi không thể mở do quy tắc JPMS; không phải mọi lỗi truy cập đều chuyển thành `false`.

Lưu ý về thiết kế: nếu làm thư viện dùng trên Java 17+, đừng bắt `InaccessibleObjectException` rồi tiếp tục giả vờ đọc field thành công. Hãy cung cấp thông báo chẩn đoán có tên module/package và phương án API công khai, `opens` có chủ đích, hoặc cập nhật thư viện.

Với các framework mới, các lựa chọn có cấu trúc như constructor injection, accessors hợp lệ, factory methods, `MethodHandles.privateLookupIn` (nếu điều kiện module cho phép), hoặc cấu hình serialization được hỗ trợ có thể bền vững hơn so với phụ thuộc vào field `private` nội bộ của JDK. **`privateLookupIn` cũng không phải đường vòng để vượt qua package chưa được mở**, vì nó chịu những quy tắc access/module riêng.

## 8. Phân biệt với exception khác của Reflection

| Loại lỗi | Thường xảy ra ở đâu | Ý nghĩa thực tế |
| --- | --- | --- |
| `NoSuchFieldException` / `NoSuchMethodException` | `getDeclaredField` / `getDeclaredMethod` | Không tìm được tên/chữ ký trong phạm vi API tìm kiếm |
| `IllegalAccessException` | `Field.get/set`, `Method.invoke` hoặc constructor invoke | Access checks chưa được đáp ứng khi thực hiện thao tác |
| `InaccessibleObjectException` | `setAccessible(true)` | Không thể bật suppress Java access checks, thường do package/module chưa `opens` |
| `InvocationTargetException` | `Method.invoke` hoặc `Constructor.newInstance` | Thân method/constructor được gọi đã ném exception; xem `getCause()` |
| `IllegalArgumentException` | `Field.get/set`, `canAccess`, `Method.invoke`... | Đối số/receiver/kiểu không hợp lệ |
| `SecurityException` | Khi môi trường bảo mật có cơ chế kiểm soát tương ứng | Một chính sách runtime có thể từ chối thao tác khác với JPMS `opens` |

Từ khóa phân biệt:

- **Lookup failure:** tên thành viên hoặc chữ ký/phạm vi tìm kiếm sai.
- **Access check failure:** member tồn tại nhưng chưa thể thao tác.
- **Suppress failure:** không được bật chế độ vượt qua access checks ⇒ trường hợp `InaccessibleObjectException`.
- **Target exception:** method đã chạy, lỗi phát sinh từ code đích chứ không phải do mở quyền.

Chẩn đoán đúng loại lỗi sẽ tránh giải pháp sai như «thêm `--add-opens`» cho `NoSuchFieldException` hoặc sửa `getDeclaredMethod` khi thực tế package của module đang bị đóng.

## 9. Những lỗi cấu hình thường gặp

**Lỗi A — Dùng `exports` thay cho `opens`.** Thêm `exports p` chỉ giúp dùng public API; không cấp quyền truy cập `private` qua `setAccessible(true)` cho module bên ngoài. Cần `opens p to framework.module` nếu framework thực sự có yêu cầu legitimate deep reflection.

**Lỗi B — Mở sai phía.** Directive `opens` nằm trong module **sở hữu package bị phản chiếu**, không phải trong module caller. Nếu stack trace nói `module java.base does not "opens java.lang"` thì việc chỉnh `module-info.java` của ứng dụng để `opens com.example.app` không giải quyết vấn đề đối với `java.lang`.

**Lỗi C — Dùng sai target.** `ALL-UNNAMED` là tập unnamed modules trên classpath; một thư viện đã nằm trong named module cần quyền hướng tới tên module thật của nó. Thông báo exception là manh mối đáng tin hơn suy đoán từ tên JAR.

**Lỗi D — Đặt cờ ở build mà không đặt ở runtime.** `--add-opens` phải áp dụng lên đúng JVM thực hiện reflection. IDE Run Configuration, lệnh `java`, tiến trình Gradle Test, container và server production có thể có JVM args khác nhau. Tránh giải pháp «đã thêm flag» khi thêm nhầm vào JVM khác.

**Lỗi E — Dùng `--illegal-access=permit` theo hướng dẫn cũ.** Từ Java 17 tùy chọn này đã lỗi thời, không khôi phục được quyền mở package JDK như cơ chế tương thích trước đó. Nên cập nhật thư viện hoặc cấp `--add-opens` chính xác nếu thật sự cần.

**Lỗi F — Mở mọi package JDK để dập log.** Cách đó vừa mở rộng quyền runtime không cần thiết vừa che dấu phụ thuộc vào API nội bộ thiếu ổn định. Chỉ mở package đã xác minh và theo dõi vì sao thư viện còn cần truy cập đó.

**Lỗi G — Nghĩ `public` member luôn đủ.** Một public method bên trong class/package/module không được xuất đúng phạm vi có thể vẫn inaccessible. Cần xét cả accessibility của declaring class, package/module và caller.

## 10. Quy trình xử lý sự cố theo từng bước

1. **Xác định nơi ném lỗi.** Là `setAccessible`, `trySetAccessible`, `getDeclaredXxx` hay `invoke`? Chỉ nhìn câu «reflection failed» chưa đủ.
2. **Đọc chính xác message.** Ghi lại source module, package, caller và member. Nếu không có thông điệp JPMS, xem thêm khả năng khác.
3. **Xác định cách chạy.** Mã caller thuộc unnamed module trên classpath hay named module trên module path? Nơi lỗi phát sinh là đúng JVM/process nào?
4. **Xác minh mục đích.** Framework thực sự cần private field/method, hay có thể gọi public API hoặc cập nhật bản tương thích Java 17+?
5. **Nếu sở hữu module nguồn**, mở package nhỏ nhất tới đúng module đích bằng `opens ... to ...`. Nếu bên sử dụng là unnamed module và phải hỗ trợ trường hợp đó, cân nhắc chính sách opens rộng hơn một cách chủ động.
6. **Nếu không sở hữu module nguồn**, dùng phiên bản thư viện hỗ trợ JDK hiện tại; chỉ khi cần thiết mới thêm `--add-opens source/pkg=target` cho đúng runtime.
7. **Chạy lại test thực tế** trên JDK, runtime args và cách đóng gói giống production; kiểm tra không còn `InaccessibleObjectException` và hành vi chức năng vẫn chính xác.

### Câu hỏi tự kiểm tra

**1.** Vì sao `getDeclaredField("value")` có thể thành công nhưng `setAccessible(true)` thất bại?  
Vì tìm metadata không đồng nghĩa có quyền suppress access checks xuyên ranh giới module.

**2.** `exports com.example.model;` có đủ để framework đọc private field bằng reflection không?  
Không. Khi caller nằm trong module khác, thường cần `opens com.example.model to framework.module;` hoặc quyền runtime tương đương.

**3.** `--add-opens java.base/java.lang=ALL-UNNAMED` tác động đến đâu?  
Mở **package `java.lang`** thuộc **module `java.base`** cho deep reflection từ **unnamed modules** trong runtime JVM có flag ấy; không biến `String.value` thành public, không cho phép mọi compile-time imports từ JDK internals.

**4.** Khi `Method.invoke(...)` ném `InvocationTargetException`, có nên mặc định thêm `--add-opens`?  
Không. Phải đọc `getCause()` vì phương thức đích đã chạy và ném lỗi riêng; chỉ bổ sung opens khi thật sự có bằng chứng lỗi liên quan JPMS.

## Ghi nhớ

- `InaccessibleObjectException` thường báo **không thể bật suppress access checks**; nó không đồng nghĩa `NoSuchFieldException` hay `IllegalAccessException`.
- **`exports` cho public API**, **`opens` cho deep reflection tại runtime**, với khả năng chỉ định module đích.
- **`trySetAccessible()`** giúp kiểm tra khả năng mở quyền mà không phải luôn nhận `InaccessibleObjectException`; **`canAccess()`** trả lời về access với caller/receiver thực tế.
- Trên Java 17+, strong encapsulation bảo vệ phần lớn nội bộ JDK. Ưu tiên public API/thư viện tương thích; nếu buộc phải mở package, chỉ mở đúng nguồn/đích và đúng JVM.

Hiểu rành mạch ba tầng **tìm khai báo → xin suppress checks → thực thi truy cập** là chìa khóa để giải thích và xử lý đúng nguyên nhân của `InaccessibleObjectException`.
