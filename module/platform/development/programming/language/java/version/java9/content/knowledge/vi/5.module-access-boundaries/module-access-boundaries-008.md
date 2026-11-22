# Chẩn đoán `IllegalAccessException` và `InaccessibleObjectException` trong Java

`IllegalAccessException` và `InaccessibleObjectException` đều liên quan đến việc Java từ chối một thao tác truy cập, nhưng chúng xuất hiện ở những bước khác nhau. `IllegalAccessException` là checked exception khi một API phản chiếu (reflection) hoặc `MethodHandles.Lookup` không có quyền thực hiện thao tác. `InaccessibleObjectException` là unchecked exception thường gặp khi `setAccessible(true)` cố bỏ qua kiểm tra truy cập nhưng JPMS không mở package của module đích cho module gọi.

Muốn sửa đúng lỗi, trước hết cần xác định module gọi, module chứa lớp đích, package, member và loại truy cập đang được yêu cầu. Sau đó chọn `exports` cho API công khai hoặc `opens` cho deep reflection, với phạm vi hẹp nhất có thể.

## 1. Hai exception biểu thị hai tình huống khác nhau

| Exception | Loại | Thời điểm thường gặp | Ý nghĩa |
|---|---|---|---|
| `IllegalAccessException` | Checked exception | `Field.get/set`, `Method.invoke`, `Constructor.newInstance` hoặc các thao tác tra cứu bằng `MethodHandles.Lookup`. | Kiểm tra truy cập của thao tác hiện tại không cho phép caller truy cập member hoặc kiểu được yêu cầu. |
| `InaccessibleObjectException` | Unchecked exception (`RuntimeException`) | `AccessibleObject.setAccessible(true)` không thể bật quyền truy cập bị bỏ qua do ranh giới module/package. | Caller đang yêu cầu deep reflection nhưng module đích không mở package cho caller. |

`IllegalAccessException` yêu cầu code xử lý hoặc khai báo `throws`. `InaccessibleObjectException` có thể phát sinh khi chạy và thường cần sửa module descriptor, cấu hình JVM hoặc cách thư viện truy cập.

Không nên suy luận chỉ từ tên exception rằng mọi lỗi truy cập đều do JPMS. Kiểm tra thông báo đầy đủ và dòng đầu tiên thuộc ứng dụng trong stack trace để tìm đúng thao tác thất bại.

## 2. `IllegalAccessException`: thao tác hiện tại không được phép

Reflection không tự động cấp quyền truy cập vào member chỉ vì chương trình đã tìm thấy member đó. Ví dụ, `getDeclaredField` có thể trả về một `Field` đại diện cho field `private`, nhưng gọi `Field.get` vẫn phải tuân theo quy tắc truy cập.

```java
Field field = Person.class.getDeclaredField("name");
Object value = field.get(person);
```

Nếu caller không có quyền đọc field theo quy tắc Java và module, `field.get(person)` ném `IllegalAccessException`. Tương tự, `Method.invoke` và `Constructor.newInstance` có thể ném exception này khi caller không được phép gọi member.

Các nguyên nhân thường gặp:

- Member là `private` hoặc `protected` và caller không thỏa điều kiện truy cập của Java.
- Class hoặc package nằm trong module khác nhưng package chưa được export cho module caller.
- Caller đang dùng một `MethodHandles.Lookup` không có đủ access modes để tra cứu hoặc gọi member.
- Một thư viện reflection đang truy cập API nội bộ hoặc member không được công bố của dependency.

Với `Method.invoke`, cần phân biệt `IllegalAccessException` với `InvocationTargetException`: exception thứ nhất nói rằng caller không được phép gọi method; exception thứ hai bọc exception do chính method đích ném ra sau khi method đã được gọi.

## 3. `InaccessibleObjectException`: deep reflection bị module chặn

Java reflection có thể tìm thấy member không công khai bằng `getDeclaredField`, `getDeclaredMethod` hoặc `getDeclaredConstructor`. Tuy nhiên, để bỏ qua kiểm tra truy cập thông thường, chương trình có thể cần gọi:

```java
field.setAccessible(true);
```

Trong JPMS, module đích phải mở package chứa member cho module gọi thì deep reflection mới được phép. Nếu package không mở và điều kiện của `AccessibleObject` không được đáp ứng, `setAccessible(true)` ném `InaccessibleObjectException`.

Đối với trường hợp không muốn xử lý exception này, API hiện hành `trySetAccessible()` là lựa chọn phù hợp:

```java
if (field.trySetAccessible()) {
    Object value = field.get(person);
    System.out.println(value);
} else {
    System.out.println("Package is not open for deep reflection");
}
```

`trySetAccessible()` trả về `false` nếu không thể bật quyền truy cập bị bỏ qua. Nếu bật được, các thao tác reflection tiếp theo vẫn có thể thất bại vì lý do khác, chẳng hạn truyền sai đối tượng hoặc giá trị không tương thích.

Không dùng `isAccessible()` để kiểm tra quyền truy cập. Phương thức này đã lỗi thời từ Java 9; dùng `canAccess(object)` để kiểm tra quyền truy cập hiện tại và `trySetAccessible()` khi thực sự cần bật deep reflection.

## 4. Phân biệt `exports` và `opens`

Đây là điểm quan trọng nhất khi chẩn đoán lỗi trong JPMS:

| Khai báo | Cho phép điều gì? | Không cho phép điều gì? |
|---|---|---|
| `exports package.name;` | Module khác đọc và dùng các kiểu/member `public` của package, nếu có readability phù hợp. | Không cấp quyền deep reflection vào member `private` hoặc package-private. |
| `exports package.name to caller.module;` | Chỉ module được nêu có thể dùng API `public` của package. | Không mở package cho deep reflection. |
| `opens package.name;` | Cho phép reflection truy cập sâu vào package ở runtime từ các module khác. | Không làm package trở thành API có thể import khi biên dịch. |
| `opens package.name to caller.module;` | Chỉ module được nêu được deep reflection vào package. | Không cấp quyền đó cho các module khác. |
| `open module module.name { ... }` | Mở tất cả package của module cho deep reflection ở runtime. | Không tự export tất cả package thành API công khai. |

`exports` dành cho API công khai. `opens` dành cho reflection cần truy cập sâu, ví dụ framework ánh xạ field private. Hai khai báo có mục đích khác nhau và không thay thế cho nhau.

Ví dụ module sở hữu model có thể export API công khai và mở riêng package cho framework:

```java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.entity to com.acme.framework;
}
```

Module `com.acme.framework` có thể deep-reflect package `com.acme.model.entity` ở runtime. Package đó không vì thế trở thành API có thể import tự do khi biên dịch. Nếu framework cần dùng kiểu `public` trong package, hãy cấu hình thêm `exports` phù hợp.

Tránh dùng `open module` chỉ để chữa một lỗi ở một package: nó mở toàn bộ package của module cho deep reflection. Hãy ưu tiên `opens package to module` với đúng package và đúng caller.

## 5. Cách đọc thông báo lỗi

Thông báo của `InaccessibleObjectException` thường cho biết member, module chứa class và module caller. Ví dụ dạng thông báo:

```text
Unable to make private ... accessible:
module com.acme.model does not "opens com.acme.model.entity"
to module com.acme.framework
```

Có thể đọc thông báo theo thứ tự:

1. **Member:** field/method/constructor nào đang được truy cập?
2. **Module đích:** module chứa class/member, ở ví dụ là `com.acme.model`.
3. **Package đích:** package cần mở, ở ví dụ là `com.acme.model.entity`.
4. **Caller:** module thực hiện reflection, ở ví dụ là `com.acme.framework`.
5. **Hành động:** mở đúng package cho đúng caller hoặc thay đổi cách truy cập để dùng API công khai.

Với `IllegalAccessException`, thông báo có thể ngắn hơn và không nói rõ package chưa export hay member không được phép. Hãy xác định declaring class và module của caller bằng code chẩn đoán:

```java
Module caller = Main.class.getModule();
Module target = field.getDeclaringClass().getModule();
String packageName = field.getDeclaringClass().getPackageName();

System.out.println("caller module: " + caller.getName());
System.out.println("target module: " + target.getName());
System.out.println("package: " + packageName);
System.out.println("exported to caller: " +
        target.isExported(packageName, caller));
System.out.println("open to caller: " +
        target.isOpen(packageName, caller));
```

Nếu `getName()` trả về `null`, module tương ứng là unnamed module, thường là code chạy trên classpath. Đây là cơ sở để chọn `ALL-UNNAMED` trong các tùy chọn launcher khi caller thực sự là code classpath.

## 6. Ví dụ hoàn chỉnh: từ hai exception đến `--add-opens`

Ví dụ có hai named module:

- `com.acme.model` export package `com.acme.model`, nhưng không mở package đó cho deep reflection.
- `com.acme.app` phụ thuộc vào model và thử đọc field `private` bằng reflection.

Cấu trúc source:

```text
workspace/
└── src/
    ├── com.acme.model/
    │   ├── module-info.java
    │   └── com/acme/model/Person.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
```

**Module model — `src/com.acme.model/module-info.java`:**

```java
module com.acme.model {
    exports com.acme.model;
}
```

**Class model — `src/com.acme.model/com/acme/model/Person.java`:**

```java
package com.acme.model;

public final class Person {
    private final String name = "Ada";
}
```

**Module ứng dụng — `src/com.acme.app/module-info.java`:**

```java
module com.acme.app {
    requires com.acme.model;
}
```

**Lớp chạy — `src/com.acme.app/com/acme/app/Main.java`:**

```java
package com.acme.app;

import com.acme.model.Person;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        Person person = new Person();
        Field field = Person.class.getDeclaredField("name");

        try {
            field.get(person);
        } catch (IllegalAccessException ex) {
            System.out.println("IllegalAccessException");
        }

        try {
            field.setAccessible(true);
            System.out.println("Deep reflection enabled");
            System.out.println(field.get(person));
        } catch (InaccessibleObjectException ex) {
            System.out.println("InaccessibleObjectException");
        }
    }
}
```

### Biên dịch

Chạy từ thư mục `workspace/` bằng JDK 17 trở lên:

```shell
javac --module-source-path src -d out -m com.acme.model,com.acme.app
```

### Chạy khi package chưa được mở

```shell
java --module-path out -m com.acme.app/com.acme.app.Main
```

Stdout:

```text
IllegalAccessException
InaccessibleObjectException
```

Package đã được `exports`, nên ứng dụng có thể biên dịch và sử dụng class `Person` công khai. Nhưng field `name` là `private`; `exports` không cho phép deep reflection, vì vậy `setAccessible(true)` thất bại.

### Chạy với quyền mở đúng package cho đúng module

```shell
java --module-path out --add-opens com.acme.model/com.acme.model=com.acme.app -m com.acme.app/com.acme.app.Main
```

Stdout:

```text
IllegalAccessException
Deep reflection enabled
Ada
```

`--add-opens source.module/package=target.module` mở package ở runtime cho module đích. Ở đây, `com.acme.model/com.acme.model` là module/package sở hữu field và `com.acme.app` là module caller. `field.get(person)` đầu tiên vẫn ném `IllegalAccessException` vì chưa bật quyền truy cập cho field; sau khi `setAccessible(true)` thành công nhờ package được mở, thao tác đọc trả về `Ada`.

Ví dụ đã được biên dịch và chạy trên JDK 24.0.2. Kết quả xác nhận hai exception phát sinh ở hai thao tác riêng biệt và quyền mở package khắc phục đúng lỗi deep reflection.

## 7. Chọn cách sửa theo tình huống

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Ứng dụng cần dùng kiểu `public` từ module khác. | Module đích export package bằng `exports`; module caller khai báo `requires` để có readability. |
| Framework cần đọc/ghi field `private` trong module do bạn quản lý. | Thêm `opens package to framework.module` vào `module-info.java` của module sở hữu class. |
| Không thể sửa module descriptor của dependency bên thứ ba. | Thêm `--add-opens source.module/package=caller.module` vào lệnh chạy nếu thực sự cần deep reflection. |
| Code reflection chạy trên classpath (unnamed module). | Nếu cần, dùng `--add-opens source.module/package=ALL-UNNAMED`; chỉ áp dụng cho caller classpath. |
| Framework dùng `trySetAccessible()` và nhận `false`. | Kiểm tra package có được mở cho module framework không; xử lý nhánh không truy cập được thay vì giả định luôn thành công. |
| `MethodHandles.privateLookupIn` ném `IllegalAccessException`. | Kiểm tra caller có lookup phù hợp, có readability tới module đích và package đích đã mở cho caller chưa. |
| Code trực tiếp đã biên dịch nhưng runtime ném `IllegalAccessError`. | Kiểm tra sự thay đổi module descriptor, classpath/module path và phiên bản binary; đây là `LinkageError`, khác hai exception reflection ở trên. |

Không dùng `--add-exports` để thay cho `--add-opens` khi framework cần truy cập member private. `--add-exports` cấp quyền truy cập API `public` của package; `--add-opens` cấp quyền deep reflection ở runtime.

## 8. Các tùy chọn launcher liên quan

| Tùy chọn | Mục đích |
|---|---|
| `--add-exports module/package=target` | Export package của module nguồn cho module đích để truy cập các kiểu/member `public`. |
| `--add-opens module/package=target` | Mở package của module nguồn cho deep reflection ở runtime. |
| `--add-reads module=target` | Bổ sung quan hệ readability từ module nguồn tới module đích. |
| `--patch-module module=files` | Bổ sung hoặc thay thế nội dung của module khi cần vá module; không phải giải pháp thông thường cho lỗi access. |

Ví dụ mở package JDK cho code chạy trên classpath:

```shell
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
```

Chỉ dùng tùy chọn này khi thư viện thực sự cần deep reflection vào `java.lang`. Tốt hơn là cập nhật thư viện để dùng API công khai được hỗ trợ hoặc cấu hình module riêng của ứng dụng. Không mở toàn bộ module nếu chỉ cần một package.

JDK đã áp dụng strong encapsulation cho các internal API của nền tảng từ Java 17. Không dựa vào `--illegal-access` để khôi phục cơ chế truy cập rộng cũ; hãy dùng API được hỗ trợ và mở package có chủ đích khi cần.

## 9. Quy trình chẩn đoán thực tế

1. Đọc toàn bộ exception, nguyên nhân lồng nhau và stack trace; xác định API reflection hoặc method-handle thất bại.
2. Xác định declaring class, package và module đích; xác định module caller hoặc unnamed module.
3. Kiểm tra member là `public`, `protected`, package-private hay `private`, và caller đang yêu cầu truy cập thông thường hay deep reflection.
4. Kiểm tra module descriptor: `requires` cho readability, `exports` cho API công khai, `opens` cho deep reflection.
5. Chọn sửa nhỏ nhất: dùng API công khai, export đúng package, mở đúng package cho framework, hoặc thêm launcher option có phạm vi cụ thể.
6. Chạy lại trên đúng JDK, module path và lệnh triển khai; xác nhận exception biến mất và chức năng vẫn hoạt động.
7. Nếu lỗi liên quan tới JDK internal API, tìm API thay thế và kiểm tra dependency có còn dựa vào package nội bộ không.

Các lệnh hỗ trợ kiểm tra module:

```shell
java --module-path out --describe-module com.acme.model
jar --describe-module --file dependency.jar
jdeps --jdk-internals application.jar
```

`--describe-module` và `jar --describe-module` giúp xem tên module, dependency, package export hoặc open trong descriptor. `jdeps --jdk-internals` giúp phát hiện việc phụ thuộc vào JDK internal API; nó không thay thế việc kiểm tra quyền truy cập reflection ở runtime.

## 10. Những cách xử lý nên tránh

- Không mở toàn bộ module bằng `open module` chỉ để khắc phục một field private trong một package.
- Không mở package cho `ALL-UNNAMED` nếu caller thực tế là một named module.
- Không nhầm `exports` với `opens`; public API và deep reflection có ranh giới riêng.
- Không bắt `Exception` chung rồi bỏ qua lỗi access. Ghi nhận module, package và member để chẩn đoán được nguyên nhân.
- Không coi `trySetAccessible()` trả về `false` là đã đọc được dữ liệu; phải xử lý rõ nhánh không truy cập được.
- Không dùng reflection để truy cập JDK internal API nếu có API công khai được hỗ trợ.
- Không thêm `--add-opens` vào mọi môi trường một cách mặc định; ghi rõ lý do, package, caller và phạm vi cần thiết.

## Tài liệu tham khảo

- [Java API — `AccessibleObject`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java API — `InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html)
- [Java Language Specification — Module Declarations](https://docs.oracle.com/en/java/javase/24/docs/specs/jls/jls-7.html)
- [Java Launcher — `--add-exports`, `--add-opens`, and module options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
