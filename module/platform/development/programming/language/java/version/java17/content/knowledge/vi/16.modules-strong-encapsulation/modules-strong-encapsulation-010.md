# Kiểm thử thư viện reflection trong môi trường module thực tế

## 1. Vì sao phải kiểm thử reflection trên module path?

Từ Java 9, Java Platform Module System (JPMS) cho phép ứng dụng đóng gói code thành **module có tên**, khai báo dependency và kiểm soát package nào được công khai hoặc mở cho reflection. Java 17 áp dụng cơ chế đóng gói mạnh (*strong encapsulation*) trong runtime.

Một thư viện có thể chạy bình thường khi ứng dụng đặt mọi class trên **classpath**, nhưng thất bại khi chuyển sang **module path**. Nguyên nhân thường là thư viện cần đọc/ghi field private, gọi constructor không public hoặc khám phá metadata bằng reflection, trong khi module chứa class chưa mở package tương ứng cho module thư viện.

Các tình huống phổ biến gồm JSON mapper, dependency injection, ORM, bean mapper, validation framework, serializer, plugin framework và test framework. Nếu production chạy named modules, test tích hợp cần chạy trong **môi trường module thật**. Chỉ chạy test trên classpath có thể che giấu lỗi vì classpath thuộc unnamed module và không phản ánh ranh giới exports/opens.

Bài học tập trung vào phân biệt `exports`/`opens`, kiểm tra deep reflection, dựng hai named modules, chạy test trên module path và chẩn đoán lỗi của thư viện thực tế.

## 2. Nền tảng JPMS cần biết

### 2.1. Module descriptor

Một named module thường có file `module-info.java` ở gốc source:

```java
module com.acme.domain {
    exports com.acme.domain.api;
}
```

Module descriptor có thể khai báo:

- `requires`: module dependency.
- `exports`: công khai package cho code module khác.
- `opens`: cho phép reflection sâu vào package ở runtime.
- `uses` và `provides ... with ...`: cơ chế service provider.

Ví dụ:

```java
module com.acme.application {
    requires com.acme.domain;
    requires java.net.http;
}
```

Khi module nằm trên module path, JVM tạo module graph và áp dụng quy tắc readability, exports và opens. Những quy tắc này không được kiểm tra giống hệt khi toàn bộ code chạy trong unnamed module trên classpath.

### 2.2. Classpath và module path

| Cách chạy | Tổ chức code | Ranh giới module |
|---|---|---|
| Classpath | Class/JAR thường thuộc unnamed module | Không có exports/opens riêng cho từng module ứng dụng |
| Module path | Module có tên và descriptor được đọc | Có readability, exports và opens |
| Automatic module | JAR không có descriptor được suy ra tên module | Có tên module tự động và tham gia module graph theo quy tắc automatic module |

Ví dụ shell kiểu Unix:

```shell
java -cp app.jar:lib.jar com.acme.Main
java --module-path mods -m com.acme.application/com.acme.application.Main
```

Trên Windows, dấu phân cách classpath thường là `;`; trên Linux/macOS thường là `:`.

**Điểm quan trọng:** kiểm thử reflection chỉ trên classpath không chứng minh thư viện tương thích với strong encapsulation. Nếu production chạy module path, test tích hợp cần chạy module path và dùng module descriptor gần với production.

## 3. exports và opens giải quyết hai nhu cầu khác nhau

### 3.1. exports: công khai API

`exports` công khai các kiểu public trong package:

```java
module com.acme.domain {
    exports com.acme.domain.api;
}
```

Consumer có thể import và gọi public API:

```java
import com.acme.domain.api.Customer;
Customer customer = new Customer("C-100", "An");
System.out.println(customer.name());
```

`exports` không có nghĩa mọi field/method private trong package đều được phép truy cập bằng deep reflection. Nó chủ yếu xác định quyền truy cập API public theo quy tắc module và Java access control.

### 3.2. opens: cho phép deep reflection

`opens` cho phép module đích dùng reflection để truy cập sâu vào các thành viên của package, kể cả thành viên không public, theo các điều kiện của `AccessibleObject`:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.jsonmapper;
}
```

Ở đây, `com.acme.domain.api` là API công khai; `com.acme.domain.model` được mở riêng cho module mapper. Nếu thư viện chỉ gọi public accessor, có thể chỉ cần exports. Nếu thư viện cần field private hoặc constructor không public, package cần được mở cho đúng module thực hiện reflection.

### 3.3. Bảng so sánh

| Khai báo | Public API cho module khác | Deep reflection |
|---|---|---|
| Không `exports`, không `opens` | Không công khai | Không |
| `exports p` | Có, cho mọi module đọc module nguồn | Không tự cấp quyền truy cập sâu |
| `exports p to m` | Có, chỉ cho module `m` | Không tự cấp quyền truy cập sâu |
| `opens p` | Không làm package thành API compile-time | Có ở runtime |
| `opens p to m` | Không làm package thành API compile-time | Có cho module `m` |
| `open module x { ... }` | Vẫn cần exports để công khai API compile-time | Mở mọi package cho reflection runtime |

### 3.4. Qualified opens và open module

Ưu tiên mở package có mục tiêu:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model
            to com.acme.jsonmapper, com.acme.persistence;
}
```

Tên module đích phải là tên module thực tế của thư viện trong module graph. Không đoán tên từ tên file JAR; hãy kiểm tra descriptor hoặc automatic module name.

`open module com.acme.domain { ... }` mở tất cả package cho deep reflection ở runtime. Nó không biến mọi package thành public API ở compile time. Đây là cấu hình rộng, chỉ dùng khi toàn bộ module thực sự được thiết kế cho reflection sâu.

## 4. Reflection và strong encapsulation

### 4.1. Khám phá metadata khác với truy cập member

Core reflection có các API:

- `Class.getFields()`, `getDeclaredFields()`.
- `Class.getMethods()`, `getDeclaredMethods()`.
- `Class.getConstructors()`, `getDeclaredConstructors()`.
- `Field`, `Method`, `Constructor`.
- `AccessibleObject.setAccessible`, `trySetAccessible`, `canAccess`.

Việc lấy metadata của member và việc được phép truy cập member là hai chuyện khác nhau. Có thể lấy được đối tượng `Field` mô tả field private, nhưng thao tác đọc field vẫn bị chặn nếu module/package không cho phép.

```java
Field field = Customer.class.getDeclaredField("email");
```

`getDeclaredField` tìm field được khai báo trực tiếp trong class; nó không tự cấp quyền đọc giá trị private.

### 4.2. trySetAccessible và setAccessible

```java
boolean allowed = field.trySetAccessible();
```

- `trySetAccessible()` cố gắng bật quyền truy cập sâu; trả `true` nếu thành công, `false` nếu không thể bật.
- `setAccessible(true)` yêu cầu bật quyền; nếu module không mở package phù hợp, có thể ném `InaccessibleObjectException`.
- Nếu access suppression không được bật, `Field.get`, `Field.set` hoặc `Method.invoke` có thể ném `IllegalAccessException`.

Ví dụ:

```java
Field field = Customer.class.getDeclaredField("email");
if (field.trySetAccessible()) {
    System.out.println(field.get(customer));
} else {
    System.out.println("Package chưa mở cho caller");
}
```

### 4.3. canAccess

`AccessibleObject.canAccess(Object obj)` kiểm tra member có thể được truy cập từ caller hiện tại hay không:

```java
Field instanceField = Customer.class.getDeclaredField("email");
boolean canRead = instanceField.canAccess(customer);
```

Với field/method instance, truyền receiver object. Với static member, truyền `null`. Receiver không phù hợp có thể gây `IllegalArgumentException`. `canAccess` không tự mở package và không thay thế `trySetAccessible`.

### 4.4. InaccessibleObjectException

Ví dụ:

```text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module com.acme.domain does not "opens com.acme.domain.api"
to module com.acme.reflecttest
```

Thông báo thường nêu module chứa class, package chứa member và module caller đang thực hiện deep reflection. Ba thông tin này cho biết directive `opens` cần cân nhắc. Không mở toàn bộ module trước khi xác định thư viện nào thực sự cần quyền đó.

## 5. Ví dụ hai named module để kiểm thử reflection

Ta tạo hai module: `com.acme.domain` chứa model và `com.acme.reflecttest` kiểm thử reflection. Mục tiêu là quan sát cùng một class trong hai cấu hình: package export nhưng chưa open thì public API hoạt động và private reflection bị chặn; khi package mở cho test module thì deep reflection thành công.

### 5.1. Cấu trúc thư mục

```text
reflection-lab/
└── src/
    ├── com.acme.domain/
    │   ├── module-info.java
    │   └── com/acme/domain/api/Customer.java
    └── com.acme.reflecttest/
        ├── module-info.java
        └── com/acme/reflecttest/ReflectionProbe.java
```

### 5.2. Module descriptor của domain

File `src/com.acme.domain/module-info.java`:

```java
module com.acme.domain {
    exports com.acme.domain.api;
}
```

Package API được export nhưng chưa có opens.

### 5.3. Class chứa private field

File `src/com.acme.domain/com/acme/domain/api/Customer.java`:

```java
package com.acme.domain.api;

public final class Customer {
    private final String email;
    private final String name;

    public Customer(String email, String name) {
        this.email = email;
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

### 5.4. Module descriptor của test

File `src/com.acme.reflecttest/module-info.java`:

```java
module com.acme.reflecttest {
    requires com.acme.domain;
}
```

### 5.5. Chương trình kiểm tra

File `src/com.acme.reflecttest/com/acme/reflecttest/ReflectionProbe.java`:

```java
package com.acme.reflecttest;

import com.acme.domain.api.Customer;
import java.lang.reflect.Field;

public class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Customer customer = new Customer("an@example.test", "An");
        System.out.println("Public name: " + customer.name());

        Field email = Customer.class.getDeclaredField("email");
        System.out.println("Field found: " + email.getName());

        boolean opened = email.trySetAccessible();
        System.out.println("Deep reflection allowed: " + opened);

        if (opened) {
            System.out.println("Private email: " + email.get(customer));
        } else {
            try {
                email.get(customer);
                throw new AssertionError("Expected IllegalAccessException");
            } catch (IllegalAccessException expected) {
                System.out.println("Private field access was blocked");
            }
        }
    }
}
```

### 5.6. Biên dịch và chạy trên module path

Từ thư mục `reflection-lab`:

```shell
javac --module-source-path src -d mods \
  -m com.acme.domain,com.acme.reflecttest

java --module-path mods \
  -m com.acme.reflecttest/com.acme.reflecttest.ReflectionProbe
```

Kết quả dự kiến:

```text
Public name: An
Field found: email
Deep reflection allowed: false
Private field access was blocked
```

Đây là bằng chứng rằng `exports` đủ cho public API nhưng không tự cấp quyền đọc private field bằng deep reflection.

## 6. Mở package có mục tiêu và chạy lại test

### 6.1. Qualified opens trong module-info.java

Sửa module descriptor của domain thành:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.api to com.acme.reflecttest;
}
```

Directive `opens` cấp quyền deep reflection vào package `com.acme.domain.api` cho module `com.acme.reflecttest`. Nó không thay thế `exports`; exports vẫn cần thiết để test module import và gọi public API ở compile time.

Biên dịch lại:

```shell
javac --module-source-path src -d mods \
  -m com.acme.domain,com.acme.reflecttest
```

Chạy:

```shell
java --module-path mods \
  -m com.acme.reflecttest/com.acme.reflecttest.ReflectionProbe
```

Kết quả dự kiến:

```text
Public name: An
Field found: email
Deep reflection allowed: true
Private email: an@example.test
```

### 6.2. Vì sao qualified opens tốt hơn open module?

Module domain chỉ cho phép module test cụ thể truy cập sâu. Những module khác không tự nhận quyền đó. Đây là nguyên tắc **least privilege** áp dụng cho module descriptor.

Trong production, thay `com.acme.reflecttest` bằng tên module thực tế của thư viện cần reflection. Không mở package cho test module rồi kết luận framework production cũng được phép; caller module khác nhau sẽ có quyền khác nhau.

### 6.3. Kiểm tra module/package ở runtime

Java cho phép kiểm tra thông tin module:

```java
Module domainModule = Customer.class.getModule();
Module callerModule = ReflectionProbe.class.getModule();

System.out.println(domainModule.getName());
System.out.println(callerModule.getName());

System.out.println(domainModule.isExported(
        "com.acme.domain.api", callerModule
));
System.out.println(domainModule.isOpen(
        "com.acme.domain.api", callerModule
));
```

Các kết quả cho biết package có được export/open tới module caller cụ thể không. Đây là thông tin hữu ích khi chẩn đoán test chạy trong module graph phức tạp.

## 7. Dùng --add-opens trong test/runtime

### 7.1. Thêm quyền mở bằng command line

Trong một số trường hợp, không thể sửa module descriptor của module chứa model, ví dụ module đến từ dependency bên thứ ba. Có thể thử cấp quyền mở ở runtime bằng:

```shell
java --module-path mods \
  --add-opens com.acme.domain/com.acme.domain.api=com.acme.reflecttest \
  -m com.acme.reflecttest/com.acme.reflecttest.ReflectionProbe
```

Cú pháp:

```text
--add-opens <source-module>/<package>=<target-module>
```

Lệnh này mở package `com.acme.domain.api` trong module nguồn `com.acme.domain` cho module đích `com.acme.reflecttest` tại runtime.

Đây là công cụ hữu ích để:

- Kiểm tra nhanh liệu lỗi có xuất phát từ package chưa mở không.
- Chạy test với dependency chưa thể sửa module descriptor.
- Cung cấp cấu hình runtime tạm thời trong lúc lập kế hoạch migration.

Nếu quyền này là yêu cầu production lâu dài, hãy cân nhắc đưa qualified `opens` vào module descriptor của module sở hữu package, hoặc cấu hình launcher có kiểm soát theo chính sách triển khai.

### 7.2. ALL-UNNAMED dành cho code trên classpath

Nếu thư viện reflection chạy trên classpath, caller thuộc unnamed module. Có thể dùng:

```shell
java --module-path mods \
  --add-opens com.acme.domain/com.acme.domain.api=ALL-UNNAMED \
  -cp legacy-mapper.jar \
  com.acme.legacy.Main
```

`ALL-UNNAMED` mở package cho các unnamed module. Đây là phạm vi rộng hơn một module đích cụ thể. Khi có thể, hãy dùng named module cho thư viện và mở package đúng module đó.

Không viết `ALL-UNNAMED` trong directive `opens ... to ...` của `module-info.java`; đó là target đặc biệt của command-line option, không phải tên module Java trong source descriptor.

### 7.3. --add-exports không thay thế --add-opens

Hai option:

```text
--add-exports source.module/package=target.module
--add-opens   source.module/package=target.module
```

không tương đương:

- `--add-exports` cho phép truy cập public types/members của package không được export bởi module descriptor, trong phạm vi runtime/biên dịch mà option áp dụng.
- `--add-opens` cho phép deep reflection vào package ở runtime.

Nếu thư viện cần truy cập private field, `--add-exports` đơn thuần không đủ. Nếu code cần import một public class từ package không export, `--add-opens` không thay thế directive exports cho compile-time API.

### 7.4. Không dựa vào --illegal-access

Các hướng dẫn cũ từng khuyên dùng `--illegal-access=permit` để nới lỏng truy cập vào JDK internals. Trên Java 17, không dùng option này như một giải pháp mở module; strong encapsulation của JDK internals đã được áp dụng và option cũ không còn khôi phục cơ chế truy cập rộng trước đây.

Nếu một thư viện cần truy cập nội bộ của JDK, hãy nâng cấp thư viện lên phiên bản tương thích hoặc dùng API công khai được hỗ trợ. Không xây dựng ứng dụng mới dựa trên quyền truy cập JDK internals.

## 8. Kiểm thử thư viện reflection thực tế

Ví dụ hai module tự viết giúp hiểu quy tắc. Khi tích hợp một thư viện thật, cần xác định **module nào thực hiện reflection** và package nào của ứng dụng bị truy cập.

### 8.1. Xác định tên module của dependency

Tên file JAR không nhất thiết là tên module. Kiểm tra:

```shell
jar --describe-module --file path/to/library.jar
```

Với JAR có `module-info.class`, lệnh hiển thị module descriptor. Với JAR chưa có descriptor, JDK có thể hiển thị tên automatic module dựa trên metadata/tên JAR.

Có thể xem module graph lúc khởi chạy:

```shell
java --show-module-resolution \
  --module-path mods:lib \
  -m com.acme.application/com.acme.application.Main
```

Nếu dependency chạy trên classpath, nó thuộc unnamed module; trong trường hợp đó, target của `--add-opens` thường là `ALL-UNNAMED`.

### 8.2. Xác định package nào cần mở

Đừng mở toàn bộ package domain chỉ vì framework ném `InaccessibleObjectException`. Hãy đọc exception để tìm:

- Module chứa class/field/constructor.
- Package chứa member.
- Module caller thực hiện `setAccessible`.
- Member cụ thể mà thư viện cần truy cập.

Sau đó quyết định:

1. Thư viện có thể dùng public constructor/accessor thay cho private reflection không?
2. Có thể chuyển model sang API mà framework hỗ trợ mà không mở private state không?
3. Nếu deep reflection thực sự cần thiết, có thể mở đúng package cho đúng module không?

### 8.3. Thử với package public API và package model riêng

Một thiết kế có thể tách:

```text
com.acme.domain
├── com.acme.domain.api       (exports)
├── com.acme.domain.model     (opens to mapper)
└── com.acme.domain.internal  (không export, không open)
```

Module descriptor:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.jsonmapper;
}
```

API công khai được dùng bình thường. Mapper được phép deep reflection vào model package. Internal package không bị mở cho consumer khác.

Đây là cách giữ encapsulation có chủ đích: mở phần framework cần, không mở toàn bộ module.

### 8.4. Kiểm thử bằng đúng module path của production

Một integration test có giá trị cần giống production ở những điểm ảnh hưởng module access:

- Module descriptor của ứng dụng giống hoặc tương đương.
- Dependency nằm trên module path nếu production dùng module path.
- Tên module của dependency được xác định đúng.
- Test launcher dùng cùng `--add-opens`/`--add-exports` nếu production thực sự cần chúng.
- Test không vô tình đặt module cần kiểm tra lên classpath.
- JDK runtime tương ứng với môi trường triển khai.

Nếu production chạy named module nhưng test runner đưa tất cả code lên classpath, test có thể xanh trong khi production thất bại. Cần cấu hình test fork để chạy module path hoặc tạo một bài kiểm thử tích hợp riêng khởi động JVM theo đúng module graph.

## 9. Kiểm thử theo hợp đồng: public API, deep reflection và lỗi mong đợi

Một test tốt không chỉ chứng minh “reflection chạy được”. Nó cần xác định quyền truy cập nào được thiết kế.

### 9.1. Test public API vẫn hoạt động khi package chỉ export

```java
Customer customer = new Customer("a@example.test", "An");
assertEquals("An", customer.name());
```

Đây là contract công khai. Nếu chỉ cần public API, không nên mở package để test này chạy.

### 9.2. Test deep reflection bị chặn khi package chưa open

```java
Field field = Customer.class.getDeclaredField("email");
assertFalse(field.trySetAccessible());
```

Nếu yêu cầu thiết kế là module ngoài không được truy cập private state, đây là một test hữu ích. Có thể tiếp tục xác nhận `field.get(customer)` ném `IllegalAccessException`.

### 9.3. Test deep reflection thành công khi package được mở đúng module

```java
Field field = Customer.class.getDeclaredField("email");
assertTrue(field.trySetAccessible());
assertEquals("a@example.test", field.get(customer));
```

Test này chỉ nên chạy trong module configuration có directive `opens` tương ứng hoặc JVM được khởi chạy với `--add-opens` đúng target.

### 9.4. Test thư viện thay vì chỉ test reflection API

Nếu ứng dụng sử dụng JSON mapper, hãy gọi API serialization/deserialization thực tế:

```java
// Pseudocode: thay bằng API của thư viện đang dùng.
String json = mapper.writeValueAsString(customer);
Customer copy = mapper.readValue(json, Customer.class);
assertEquals(customer.name(), copy.name());
```

Đồng thời test các trường hợp framework cần truy cập:

- Public constructor/accessor.
- Constructor không public nếu framework được cấu hình dùng.
- Private field nếu framework được cấu hình field access.
- Annotation và generic metadata.
- Inheritance hoặc nested type nếu model sử dụng.

Không suy luận rằng một thư viện luôn cần opens chỉ vì nó có sử dụng reflection. Một số thư viện chỉ đọc public metadata và gọi accessor; một số thư viện khác có thể cần deep reflection tùy chế độ mapping. Kiểm tra tài liệu và hành vi của phiên bản thực tế.

## 10. JUnit và test framework trong môi trường module

### 10.1. Test framework cũng là một module caller

Nếu test chạy trong named module, test framework có thể cần:

- Đọc module chứa test.
- Khám phá test class/method.
- Gọi constructor hoặc method theo cơ chế reflection.
- Truy cập package chứa fixture hoặc test support.

Vì vậy, khi test module path, cần xác định module caller của reflection. Có thể framework cần package test mở cho framework; trong khi một thư viện production khác cần package model mở cho module của chính thư viện đó.

~~~text
com.acme.domain
    opens com.acme.domain.model to com.acme.mapper;

com.acme.tests
    opens com.acme.tests to <test-framework-module>;
~~~

Tên module framework phải lấy từ JAR/module descriptor của đúng phiên bản dependency, không đoán từ tên Maven artifact.

### 10.2. Không thêm opens cho test module rồi quên production

Giả sử JUnit test chạy được vì test command có:

```text
--add-opens com.acme.domain/com.acme.domain.model=ALL-UNNAMED
```

nhưng production chạy module path không có flag đó. Kết quả test không chứng minh production hoạt động.

Hãy quyết định package cần mở cho module nào và bảo đảm cấu hình production có cùng quyền nếu framework thực sự cần. Nếu chỉ test framework cần quyền, đừng mở model package rộng hơn mức cần thiết.

### 10.3. Tích hợp với build tool

Maven/Gradle có thể chạy test theo classpath hoặc module path tùy cấu hình và phiên bản plugin. Không giả định rằng chỉ vì project có `module-info.java` nên test runner chắc chắn đang chạy trong named module.

Khi cấu hình test:

1. Xem lệnh JVM thực tế mà build tool dùng.
2. Kiểm tra dependency nằm trên module path hay classpath.
3. Kiểm tra test module có tên hay đang ở unnamed module.
4. Kiểm tra các `--add-opens`/`--add-exports` được truyền.
5. Tạo integration test fork riêng nếu build tool mặc định không chạy theo module graph cần kiểm tra.

Một test khởi chạy JVM con bằng `ProcessBuilder` với `--module-path` cũng có thể dùng để xác minh cấu hình thật, miễn là class/module artifacts đúng với production.

## 11. MethodHandles và các cơ chế reflection khác

### 11.1. MethodHandles không phải đường vòng bỏ qua JPMS

Java có `MethodHandles` và `MethodHandles.Lookup` để truy cập method/field theo cơ chế handle. Chúng hữu ích cho framework hiệu năng cao hoặc API cần biểu diễn thao tác như một object.

`MethodHandles.privateLookupIn(targetClass, lookup)` cũng tuân theo quy tắc module. Module chứa package cần mở cho module caller phù hợp; nếu không, việc lấy private lookup sẽ thất bại.

```java
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                Customer.class,
                MethodHandles.lookup()
        );
```

Không dùng MethodHandles như cách né `opens`. Nếu một thư viện cần private access, module boundary vẫn phải cho phép quyền đó.

### 11.2. Reflection và serialization

Serialization framework có thể sử dụng nhiều chiến lược:

- Public constructor hoặc factory.
- Accessor.
- Constructor đặc biệt.
- Field reflection.
- MethodHandles.
- Generated code tại compile time.

Chiến lược khác nhau dẫn đến nhu cầu module khác nhau. Hãy đọc tài liệu module của thư viện và kiểm thử bằng đúng cấu hình. Nếu framework hỗ trợ code generation hoặc public constructor, có thể giảm nhu cầu deep reflection.

### 11.3. Reflection vào JDK internals

Java 17 áp dụng strong encapsulation cho nội bộ JDK. Không nên để ứng dụng truy cập các class/package nội bộ như `sun.*` hoặc `jdk.internal.*` bằng reflection.

Hướng xử lý hiện đại:

- Dùng API công khai được Java SE hỗ trợ.
- Nâng cấp dependency có truy cập JDK internals.
- Thay thế thư viện đã lỗi thời.
- Kiểm tra API supported và chính sách module/provider trước khi triển khai.

Không dùng `--illegal-access=permit` như giải pháp chung trên Java 17.

## 12. Công cụ kiểm tra module và dependency

### 12.1. jar --describe-module

```shell
jar --describe-module --file path/to/library.jar
```

Cho biết tên module, module descriptor, các package được export và dependency khai báo. Với JAR chưa có descriptor, JDK có thể hiển thị tên automatic module.

### 12.2. java --show-module-resolution

```shell
java --show-module-resolution \
  --module-path mods:lib \
  -m com.acme.application/com.acme.application.Main
```

Option này hiển thị cách JVM phân giải module và dependency khi khởi động. Nó hữu ích khi module bị thiếu, module name sai hoặc module graph không như dự kiến.

### 12.3. jdeps

`jdeps` phân tích dependency ở cấp class/package/module:

```shell
jdeps --module-path lib --print-module-deps application.jar
jdeps --jdk-internals application.jar
```

`jdeps` không thay thế runtime reflection test. Một thư viện có thể truy cập tên class/field qua reflection bằng chuỗi, nên dependency đó không nhất thiết xuất hiện đầy đủ trong phân tích bytecode tĩnh.

### 12.4. Kiểm tra Module ở runtime

```java
Module module = Customer.class.getModule();
Module target = ReflectionProbe.class.getModule();

System.out.println("Name: " + module.getName());
System.out.println("Named: " + module.isNamed());
System.out.println(module.isExported("com.acme.domain.api", target));
System.out.println(module.isOpen("com.acme.domain.api", target));
```

Đây là kiểm tra cấu hình module ở runtime, không thay thế test hành vi thực tế của thư viện.

## 13. Quy trình chẩn đoán khi thư viện reflection lỗi trên Java 17

**Bước 1 — Xác định exception gốc.** Tìm `InaccessibleObjectException`, `IllegalAccessException`, `IllegalAccessError` hoặc lỗi reflection cụ thể. Đọc đầy đủ module/package/member trong thông báo.

**Bước 2 — Xác định caller module.** Caller có thể là test code, framework, mapper hoặc dependency. Package cần mở phải mở cho module thực hiện deep reflection, không nhất thiết cho module application.

**Bước 3 — Kiểm tra module descriptor.** Dùng `jar --describe-module` cho dependency và kiểm tra `module-info.java` của ứng dụng.

**Bước 4 — Phân biệt public access và deep reflection.** Nếu chỉ cần public API, kiểm tra `exports`. Nếu cần private field/constructor, kiểm tra `opens`.

**Bước 5 — Thử quyền mở tối thiểu.** Dùng `--add-opens source/package=target` trong một lần chạy kiểm thử có kiểm soát. Nếu lỗi biến mất, đã khoanh vùng được module boundary liên quan.

**Bước 6 — Chuyển cấu hình đúng vào module descriptor hoặc launcher.** Ưu tiên qualified opens trong module sở hữu package nếu framework cần quyền đó ổn định.

**Bước 7 — Chạy lại integration test không có quyền dư.** Xác nhận package khác vẫn đóng và public API không bị ảnh hưởng.

**Bước 8 — Kiểm tra đúng runtime.** Test trên JDK 17 và cấu hình module path tương ứng với môi trường triển khai.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test chạy classpath nên không thấy lỗi | Classpath không tái hiện ranh giới named module | Chạy integration test trên module path |
| Có `exports` nhưng private field vẫn không đọc được | Exports không cấp deep reflection | Thêm qualified `opens` nếu thực sự cần |
| Thêm `opens` nhưng code import class vẫn lỗi compile | Opens không thay thế exports | Export package API cần dùng ở compile time |
| Mở package cho application nhưng framework vẫn lỗi | Caller thực sự là module của framework | Mở package cho đúng module caller |
| Dùng tên JAR làm target opens | Tên JAR không nhất thiết là module name | Dùng `jar --describe-module` |
| Dùng `--add-exports` để truy cập private field | Exports chỉ công khai API | Dùng opens đúng phạm vi |
| Dùng `--add-opens ...=ALL-UNNAMED` rộng trong production | Mọi unnamed module có thể được mở quyền | Chuyển dependency sang named module hoặc giới hạn quyền |
| Dùng `open module` để sửa một package | Mở tất cả package quá rộng | Dùng qualified opens |
| Gọi `setAccessible(true)` và không xử lý exception | Module có thể từ chối quyền truy cập | Dùng `trySetAccessible` hoặc xử lý exception |
| Dùng `getDeclaredField` rồi nghĩ đã có quyền đọc | Metadata discovery khác access check | Kiểm tra `canAccess`/`trySetAccessible` |
| Test có `--add-opens`, production không có | Test và production module graph khác nhau | Đồng bộ cấu hình hoặc test cả hai mode |
| Thư viện cần truy cập JDK internals | Dependency dựa trên API không được hỗ trợ | Nâng cấp/thay thư viện và dùng API công khai |

## 15. Ví dụ cấu hình production và test có chủ đích

Giả sử module ứng dụng dùng module `com.acme.jsonmapper` để ánh xạ model. Descriptor:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.jsonmapper;
}
```

Module application:

```java
module com.acme.application {
    requires com.acme.domain;
    requires com.acme.jsonmapper;
}
```

Trong môi trường test, nếu test code trực tiếp kiểm tra private field của domain, test module có thể cần được thêm vào qualified opens trong **test-specific descriptor/configuration** hoặc test có thể chạy với `--add-opens` riêng. Không nên mặc định thêm test module vào production descriptor nếu production không có nhu cầu.

Một chiến lược kiểm thử rõ:

| Test | Module configuration | Kỳ vọng |
|---|---|---|
| Public API contract | Chỉ `exports` | Public constructor/accessor dùng được |
| Private access blocked | Không mở package cho test probe | `trySetAccessible()` trả false |
| Framework integration | Mở model package cho module mapper | Mapper hoạt động theo chế độ đã cấu hình |
| Production launch | Cùng module graph và opens như production | Hành vi khởi động và mapping giống production |
| Encapsulation regression | Không mở package internal không cần thiết | Reflection ngoài phạm vi được phép bị chặn |

Đây là cách kiểm tra cả **khả năng hoạt động** lẫn **ranh giới đóng gói**.

## 16. Bài tập thực hành

### Bài 1 — Tạo hai module

Tạo `com.acme.domain` và `com.acme.reflecttest` theo ví dụ. Biên dịch bằng `javac --module-source-path` và chạy bằng `java --module-path -m`. Quan sát khác biệt giữa public accessor và private field.

### Bài 2 — Thêm qualified opens

Thêm:

```java
opens com.acme.domain.api to com.acme.reflecttest;
```

Biên dịch và chạy lại. Giải thích tại sao `trySetAccessible()` thay đổi từ false sang true và vì sao `exports` vẫn cần giữ.

### Bài 3 — Dùng --add-opens

Giữ module descriptor không có opens, chạy bằng:

```shell
java --module-path mods \
  --add-opens com.acme.domain/com.acme.domain.api=com.acme.reflecttest \
  -m com.acme.reflecttest/com.acme.reflecttest.ReflectionProbe
```

So sánh kết quả với qualified opens trong descriptor. Xác định ưu/nhược điểm của cấu hình runtime.

### Bài 4 — Thử --add-exports

Bỏ exports khỏi domain descriptor, thử truy cập public class từ test module. Sau đó dùng `--add-exports` và quan sát public API. Thử đọc private field và giải thích vì sao export không thay thế opens.

### Bài 5 — Thử library trên classpath

Đặt test probe hoặc một thư viện reflection lên classpath và chạy cùng domain module. Dùng `--add-opens ...=ALL-UNNAMED`, sau đó chuyển library sang module path nếu thư viện hỗ trợ. So sánh module caller và phạm vi quyền.

### Bài 6 — Kiểm tra tên module dependency

Dùng `jar --describe-module` để tìm module name của một dependency có reflection. Thử cấu hình qualified opens tới đúng tên module. Không đoán từ tên artifact.

### Bài 7 — Viết test contract

Viết ba test: public accessor luôn hoạt động; deep reflection bị chặn khi package không mở; deep reflection hoạt động khi package được mở đúng module. Sau đó gọi API của thư viện thực tế thay vì chỉ gọi `Field.get`. Ghi rõ module path và JVM arguments của test.

## 17. Câu hỏi tự kiểm tra

1. Vì sao test reflection trên classpath không đủ để xác nhận ứng dụng chạy tốt trên module path?
2. `exports` và `opens` khác nhau thế nào?
3. Một package có thể được export nhưng vẫn không cho đọc private field bằng reflection không?
4. `getDeclaredField` thành công có nghĩa `Field.get` sẽ thành công không?
5. `trySetAccessible()` trả false trong trường hợp nào?
6. `setAccessible(true)` có thể ném exception nào khi module không mở package?
7. Module nào cần được ghi ở target của qualified opens: application hay thư viện gọi reflection?
8. Vì sao mở package cho test module không chứng minh framework production được phép truy cập?
9. `--add-opens` và `--add-exports` khác nhau thế nào?
10. Khi nào dùng `ALL-UNNAMED` và vì sao nó có phạm vi rộng?
11. `open module` ảnh hưởng thế nào đến tất cả package?
12. Làm sao tìm đúng module name của dependency?
13. Vì sao MethodHandles không phải cách vượt qua JPMS?
14. Test framework có thể cần opens riêng cho package test như thế nào?
15. Tại sao cần chạy test trong một JVM/module graph tương tự production?

## 18. Tài liệu tham khảo

- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): kiểm tra module name, exports và opens ở runtime.
- [Java SE 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `setAccessible`, `trySetAccessible`, `canAccess` và giới hạn module.
- [Java SE 17 API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): lỗi khi không thể bật quyền truy cập sâu.
- [Java Language Specification — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): cú pháp và quy tắc module declaration.
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261): thiết kế module system, module path, exports và opens.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation của JDK internals trong các phiên bản hiện đại.
- [Java SE 17 Tools Reference — jar](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): `jar --describe-module`.
- [Java SE 17 Tools Reference — java](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--module-path`, `--add-opens`, `--add-exports` và module launch.
- [Java SE 17 Tools Reference — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency và JDK internals.

Khi kiểm thử thư viện reflection, hãy chạy trong **named module trên module path** giống môi trường triển khai. Dùng `exports` cho public API, `opens` cho deep reflection và chỉ mở package tới module thực sự gọi reflection. Kiểm tra cả trường hợp được phép lẫn bị từ chối giúp xác nhận thư viện hoạt động đúng mà vẫn giữ được ranh giới đóng gói mạnh của Java 17.
