# Rà soát reflection, bytecode generation và annotation processor khi nâng cấp lên Java 17

> **Chủ đề:** Java 17  
> **Chương:** Nâng cấp lên Java 17  
> **Mục tiêu:** Nhận diện các điểm có thể bị ảnh hưởng khi nâng ứng dụng lên Java 17, đặc biệt là reflection sâu, truy cập API nội bộ của JDK, sinh bytecode lúc chạy và annotation processor trong quá trình biên dịch. Biết cách rà soát dependency, sửa theo API được hỗ trợ và chỉ dùng tùy chọn mở module như giải pháp chuyển tiếp có kiểm soát.

## 1. Vì sao cần rà soát ba nhóm này?

Java 17 tiếp tục thực thi mạnh mẽ ranh giới module được giới thiệu từ Java 9. Một số ứng dụng chạy được trên Java cũ có thể gặp lỗi khi chuyển sang Java 17 vì thư viện hoặc code của ứng dụng:

- Dùng reflection để truy cập field, constructor hoặc method private trong package của JDK.
- Phụ thuộc vào class thuộc package nội bộ như `sun.*`, `com.sun.*` hoặc các package không được module export.
- Sinh bytecode rồi định nghĩa class bằng class loader hoặc API nội bộ của JDK.
- Dùng annotation processor truy cập các implementation class nội bộ của `javac`.
- Dựa vào các hành vi truy cập bất hợp pháp từng được cảnh báo nhưng vẫn tạm hoạt động ở những bản Java trước.

Những vấn đề này thường không xuất hiện ở compile time. Ứng dụng có thể biên dịch thành công nhưng lỗi khi chạy một tính năng ít dùng, khi framework khởi tạo proxy, khi ORM đọc field private hoặc khi compiler chạy annotation processor.

Trong Java 17, cần rà soát ba lớp:

1. **Reflection:** code có truy cập thành viên không công khai hoặc package không được mở không?
2. **Bytecode generation:** thư viện tạo class có dùng API được hỗ trợ và tuân thủ module boundary không?
3. **Annotation processing:** processor có dùng API công khai của compiler hay phụ thuộc implementation nội bộ?

## 2. Thay đổi quan trọng: strong encapsulation trong Java 17

### 2.1. Từ JPMS đến strong encapsulation

Java 9 đưa vào Java Platform Module System (JPMS). Một named module có thể quyết định:

- Package nào được **export** để module khác truy cập API công khai.
- Package nào được **open** để module khác dùng reflection sâu.
- Module nào được đọc thông qua `requires`.

Các phiên bản Java 9 đến Java 15 có giai đoạn chuyển tiếp cho một số package JDK cũ. Từ Java 16, strong encapsulation được áp dụng mặc định; Java 17 tiếp tục chính sách này theo JEP 403.

Hệ quả là ứng dụng không thể dựa vào việc truy cập sâu mọi implementation class trong JDK như trước. Một lời gọi reflection có thể ném `java.lang.reflect.InaccessibleObjectException` nếu package của module đích không được mở cho module gọi.

### 2.2. `--illegal-access` không còn là cách sửa trên Java 17

Ở các phiên bản chuyển tiếp, tùy chọn `--illegal-access` từng điều khiển mức độ cảnh báo/cho phép một số truy cập phản chiếu bất hợp pháp đến package JDK cũ.

Trên Java 17, tùy chọn này đã lỗi thời và không khôi phục cơ chế mở rộng như các bản Java trước. Không dùng các lệnh như:

```bash
java --illegal-access=permit -jar app.jar
```

để xử lý lỗi truy cập module trên Java 17. Cần xác định module/package đích, nâng cấp thư viện hoặc mở đúng package bằng cơ chế module phù hợp khi thực sự cần.

### 2.3. Export và open là hai quyền khác nhau

| Chỉ thị | Tác dụng |
|---|---|
| `exports p` | Cho phép code module khác truy cập API công khai trong package `p` theo quy tắc Java access |
| `opens p` | Cho phép reflection sâu vào các thành viên của package `p` ở runtime |
| `open module m` | Mở mọi package của module cho reflection sâu ở runtime |
| Không export/không open | Module khác không có quyền truy cập thông thường hoặc reflection sâu vào package đó |

Ví dụ:

```java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.entity to org.hibernate.orm.core;
}
```

Module khác có thể dùng API công khai trong `com.acme.model.api`. Hibernate được mở quyền reflection sâu vào `com.acme.model.entity`. Các package khác vẫn giữ ranh giới đóng gói.

Không nên dùng `opens` khi code chỉ cần gọi public API; cũng không nên nghĩ `exports` sẽ cho phép framework truy cập field private.

## 3. Rà soát reflection

### 3.1. Những API cần tìm trong source code

Tìm các lời gọi reflection thường gặp:

```java
field.setAccessible(true);
method.setAccessible(true);
constructor.setAccessible(true);
AccessibleObject.setAccessible(...);
```

Ngoài ra, rà soát:

- `Class.getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor`.
- `Field.get`/`Field.set`, `Method.invoke`, `Constructor.newInstance`.
- `MethodHandles.privateLookupIn` và `Lookup.find*`.
- `Class.forName` với tên class được cấu hình động.
- Framework ORM, dependency injection, JSON/XML mapper, serializer, proxy và mocking framework.

Không phải mọi lời gọi reflection đều có vấn đề. Truy cập public API hoặc reflection trong cùng module vẫn có thể hoạt động bình thường. Mục tiêu là tìm chỗ vượt qua ranh giới module hoặc phụ thuộc vào JDK internals.

### 3.2. Ví dụ truy cập field private

Giả sử một class trong module của ứng dụng:

```java
package com.acme.model;

public class Customer {
    private String name;
}
```

Trong cùng một module hoặc khi package được mở phù hợp, code có thể dùng:

```java
Field field = Customer.class.getDeclaredField("name");
if (field.trySetAccessible()) {
    Object value = field.get(customer);
}
```

`trySetAccessible()` trả về `false` nếu không thể bật quyền truy cập phản chiếu. Nó giúp code xử lý trường hợp package không được mở mà không phải dựa vào exception để điều khiển luồng.

Với `setAccessible(true)`, nếu quyền truy cập không thể được bật do ranh giới module, lời gọi có thể ném `InaccessibleObjectException`.

### 3.3. Dùng canAccess thay cho kiểm tra cũ

Java 9 bổ sung `AccessibleObject.canAccess(Object)` để kiểm tra một đối tượng reflection có thể truy cập thành viên với receiver cụ thể hay không:

```java
Field field = Customer.class.getDeclaredField("name");
boolean accessible = field.canAccess(customer);
```

Với thành viên static, truyền `null` làm receiver:

```java
Field version = Config.class.getDeclaredField("VERSION");
boolean accessible = version.canAccess(null);
```

`canAccess` kiểm tra khả năng truy cập theo ngữ cảnh hiện tại; nó không tự mở package và cũng không cấp quyền truy cập.

### 3.4. Kiểm tra và mở quyền có điều kiện

Ví dụ code xử lý rõ ràng:

```java
Field field = Customer.class.getDeclaredField("name");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Package com.acme.model is not open for deep reflection");
}

String name = (String) field.get(customer);
```

Thông báo lỗi nên nêu module/package cần được mở để vận hành. Không nên nuốt lỗi rồi trả giá trị mặc định, vì có thể làm dữ liệu ORM/serialization sai mà không rõ nguyên nhân.

### 3.5. Mở package bằng module descriptor

Nếu bạn sở hữu module chứa class và framework thực sự cần reflection sâu, khai báo `opens` trong `module-info.java`:

```java
module com.acme.application {
    requires org.hibernate.orm.core;

    opens com.acme.application.entity
        to org.hibernate.orm.core;
}
```

Chỉ package entity được mở cho module Hibernate. Đây là cách thể hiện rõ ràng trong module descriptor và phù hợp khi bạn kiểm soát source của module.

Nếu ứng dụng không dùng module descriptor (chạy trên classpath), unnamed module vốn được mở cho reflection theo quy tắc JPMS. Nhưng khi thư viện cố truy cập package nội bộ của một named module JDK, ranh giới strong encapsulation vẫn có hiệu lực.

### 3.6. Dùng --add-opens khi không thể sửa module descriptor

Tùy chọn runtime `--add-opens` mở một package của module nguồn cho module đích:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar legacy-app.jar
```

Ý nghĩa:

- `java.base` là module nguồn.
- `java.lang` là package được mở.
- `ALL-UNNAMED` là tất cả unnamed module (thường là code trên classpath).

Nếu module đích có tên, dùng tên module đó thay cho `ALL-UNNAMED`:

```bash
java --add-opens java.base/java.lang=com.acme.application -m com.acme.application/com.acme.Main
```

Có thể mở nhiều package bằng nhiều tùy chọn:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED --add-opens java.base/java.util=ALL-UNNAMED -jar legacy-app.jar
```

Đây là workaround ở runtime. Nó làm giảm mức đóng gói của package được mở cho module đích. Hãy giới hạn chính xác package và module nhận quyền; không mở toàn bộ module nếu chỉ cần một package.

### 3.7. --add-exports dành cho truy cập API công khai trong package chưa export

`--add-exports` và `--add-opens` không thể thay thế nhau:

- `--add-exports` cho phép truy cập thông thường đến các kiểu/thành viên public của package chưa được export.
- `--add-opens` cho phép reflection sâu ở runtime vào package.

Ví dụ:

```bash
java --add-exports java.base/sun.security.x509=ALL-UNNAMED -jar legacy-app.jar
```

Tùy chọn này chỉ cấp quyền truy cập cho package cụ thể trong module graph/runtime. Nó không biến API nội bộ thành API được hỗ trợ ổn định. Nếu JDK thay đổi hoặc loại bỏ class nội bộ, ứng dụng vẫn có thể hỏng.

Với code biên dịch cần tham chiếu package không export, tùy chọn compiler tương ứng có thể được dùng:

```bash
javac --add-exports java.base/sun.security.x509=ALL-UNNAMED ...
```

Không nên thêm cả `--add-exports` và `--add-opens` theo thói quen. Chỉ dùng đúng quyền cần thiết sau khi đã xác định lỗi.

### 3.8. MethodHandles và privateLookupIn

Code dùng `MethodHandles` cũng chịu quy tắc module. Ví dụ:

```java
MethodHandles.Lookup lookup =
        MethodHandles.privateLookupIn(Customer.class,
                MethodHandles.lookup());

VarHandle nameHandle = lookup.findVarHandle(
        Customer.class, "name", String.class);
```

`privateLookupIn` tạo lookup có quyền truy cập private trong class đích khi các điều kiện module được đáp ứng. Trong trường hợp caller và target thuộc module khác nhau, caller phải đọc target module và package của target phải được mở cho caller module; lookup ban đầu cũng phải có quyền cần thiết.

Nếu package không được mở, lời gọi có thể thất bại với `IllegalAccessException`. Không được giả định `MethodHandles` tự bỏ qua strong encapsulation chỉ vì không dùng `setAccessible`.

### 3.9. Ưu tiên API công khai thay cho reflection nội bộ

Trước khi thêm `--add-opens`, xem xét:

- Có public method hoặc API chuyên dụng thay thế không?
- Framework đã có bản mới hỗ trợ Java 17 chưa?
- Có thể cấu hình framework dùng constructor/setter thay vì truy cập field private không?
- Có thể viết adapter trong module sở hữu class để cung cấp API rõ ràng không?
- Có thể dùng SPI/service thay vì quét và truy cập implementation bằng reflection không?

Mở package chỉ nên là quyết định có lý do, có phạm vi và có kế hoạch loại bỏ khi dependency được nâng cấp.

## 4. Rà soát JDK internal API và dependency

### 4.1. Tìm tham chiếu đến JDK internals bằng jdeps

`jdeps` có thể phát hiện nhiều tham chiếu tĩnh đến JDK internal API:

```bash
jdeps --jdk-internals --recursive app.jar
```

Nếu ứng dụng cần phân tích dependency trong thư mục thư viện:

```bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
```

Với multi-release JAR, chỉ định phiên bản class file cần phân tích:

```bash
jdeps --jdk-internals --multi-release 17 --recursive app.jar
```

Kết quả có thể nêu class của ứng dụng đang phụ thuộc package nội bộ nào và gợi ý API thay thế nếu JDK cung cấp.

### 4.2. Giới hạn của jdeps

`jdeps` phân tích dependency có thể suy ra từ bytecode và cấu trúc archive. Nó không thể phát hiện chắc chắn mọi truy cập động:

- `Class.forName("sun....")` khi tên class được ghép từ cấu hình.
- Reflection đến field/method theo tên được đọc từ file.
- Class name do plugin hoặc framework cung cấp lúc chạy.
- Bytecode được sinh ra sau khi chương trình khởi động.
- Đường đi chỉ xuất hiện trong môi trường production hoặc một tính năng hiếm dùng.

Vì vậy, cần kết hợp jdeps với tìm kiếm source code, rà soát dependency, test tích hợp và quan sát runtime.

### 4.3. Tìm API deprecated bằng jdeprscan

`jdeprscan` tìm cách sử dụng API đã deprecated trong class/JAR:

```bash
jdeprscan --release 17 --for-removal app.jar
```

Lệnh này bổ sung cho `jdeps` nhưng trả lời câu hỏi khác:

- `jdeps --jdk-internals`: ứng dụng có phụ thuộc JDK internal API không?
- `jdeprscan`: ứng dụng có sử dụng API deprecated hoặc deprecated for removal không?

API deprecated không nhất thiết là internal API; API internal cũng không nhất thiết được đánh dấu deprecated. Nên chạy cả hai khi rà soát nâng cấp.

### 4.4. Kiểm tra module descriptor và dependency

Với modular JAR:

```bash
jar --describe-module --file app.jar
```

Liệt kê module trong runtime:

```bash
java --list-modules
```

Kiểm tra các dependency và module được yêu cầu. Một ứng dụng chạy trên classpath có thể không có descriptor; khi đó jdeps vẫn hữu ích để phát hiện tham chiếu nội bộ nhưng không thay thế việc rà soát module và reflection.

## 5. Rà soát bytecode generation

### 5.1. Bytecode generation là gì?

Một số framework tạo class trong lúc chạy thay vì chỉ dùng class đã biên dịch sẵn. Các trường hợp phổ biến:

- Dynamic proxy cho interface.
- Proxy/subclass phục vụ ORM và lazy loading.
- Mock object trong test.
- Dependency injection và AOP.
- Serializer tạo accessor hoặc adapter tối ưu.
- Framework tạo class để gọi method/field nhanh hơn reflection.

Thư viện thường dùng ASM, Byte Buddy, Javassist hoặc API của JDK để sinh bytecode. Khi nâng lên Java 17, cần kiểm tra cả khả năng đọc class file version mới và cách class được định nghĩa trong module/package.

### 5.2. Kiểm tra phiên bản thư viện sinh bytecode

Đối với mỗi dependency có khả năng tạo class:

1. Kiểm tra release hỗ trợ Java 17.
2. Xem release note về JPMS, strong encapsulation, reflection và class definition.
3. Cập nhật framework lên phiên bản còn được hỗ trợ.
4. Chạy test các tính năng tạo proxy, mock, ORM entity và serialization.
5. Kiểm tra log cảnh báo hoặc exception khi class được define.

Không nên chỉ nâng ASM hoặc Byte Buddy riêng lẻ nếu framework bao bọc chúng có yêu cầu phiên bản riêng. Dùng dependency version mà framework công bố hỗ trợ.

### 5.3. Class loader, package và module khi define class

Class được định nghĩa trong một class loader và gắn với runtime package/module theo quy tắc JVM. Hai class có cùng tên package nhưng được định nghĩa bởi class loader khác nhau không nhất thiết thuộc cùng runtime package.

Điều này ảnh hưởng đến:

- Truy cập package-private class/member.
- Truy cập protected member.
- Định nghĩa subclass/proxy trong package của target.
- Quyền truy cập của generated code vào module khác.

Nếu framework tạo class trong class loader riêng, generated class có thể không truy cập được package-private member mà framework kỳ vọng. Lỗi thường xuất hiện ở runtime khi class được define hoặc khi JVM verify/link class.

### 5.4. Ưu tiên MethodHandles.Lookup.defineClass

Java 9 bổ sung `MethodHandles.Lookup#defineClass(byte[])` để định nghĩa class trong cùng package và class loader/module với lookup class, nếu lookup có quyền package phù hợp.

Ví dụ minh họa:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
byte[] generatedClassBytes = generateClassBytes();

Class<?> generated = lookup.defineClass(generatedClassBytes);
```

Các điều kiện quan trọng:

- Bytecode phải hợp lệ và tên class phải thuộc cùng package với lookup class.
- Lookup cần có quyền `PACKAGE` phù hợp.
- Class được định nghĩa trong class loader và runtime package/module của lookup class.
- Class name không được xung đột với class đã định nghĩa trong cùng loader.

API này phù hợp khi generated class cần nằm trong package của class sở hữu lookup. Nó không phải API để định nghĩa class tùy ý vào một package bất kỳ trong module khác.

### 5.5. Lookup và privateLookupIn

Nếu cần tạo lookup có quyền truy cập private vào một class khác, có thể dùng `MethodHandles.privateLookupIn` khi module access cho phép:

```java
MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(
                Customer.class,
                MethodHandles.lookup());
```

Với target ở module khác, package target cần được open cho module của caller và module caller phải đọc target module. Đây là quy tắc module, không thể bỏ qua bằng việc chỉ tạo bytecode.

### 5.6. Hidden classes

Java 15 bổ sung hidden classes qua `Lookup#defineHiddenClass`. Hidden class phù hợp với implementation class được tạo cho framework/runtime và không cần được tìm thấy bằng tên nhị phân thông thường.

Ví dụ khái quát:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                generatedClassBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE);

Class<?> hiddenClass = hiddenLookup.lookupClass();
```

Hidden class có một số đặc điểm:

- Không thể được nạp theo cách thông thường bằng `Class.forName` theo tên nhị phân.
- Không phải class thông thường có thể tìm thấy bằng class loader enumeration.
- Có thể tham gia nest của class lookup nếu dùng `NESTMATE` và thỏa điều kiện.
- Phù hợp với proxy/adapter nội bộ không cần tên class ổn định cho ứng dụng.

Không phải mọi framework đều cần hidden class. Dùng API này chỉ khi thiết kế class generation yêu cầu và thư viện đã hỗ trợ Java 17.

### 5.7. Tránh phụ thuộc vào API nội bộ để định nghĩa class

Các framework cũ có thể dùng reflection hoặc internal API để gọi các cơ chế như `ClassLoader#defineClass` với quyền truy cập đặc biệt, hoặc tham chiếu package `jdk.internal.*`.

Trên Java 17, truy cập package nội bộ bị strong encapsulation bảo vệ. Hãy ưu tiên:

- `MethodHandles.Lookup#defineClass`.
- `MethodHandles.Lookup#defineHiddenClass` nếu phù hợp.
- Proxy API công khai `java.lang.reflect.Proxy` cho interface proxy.
- Phiên bản mới của ASM/Byte Buddy/Javassist đã hỗ trợ Java 17.

Không nên mở rộng hàng loạt package `java.base/jdk.internal.*` để giữ một framework cũ hoạt động mà chưa đánh giá rủi ro.

## 6. Dynamic proxy và module boundary

### 6.1. Proxy API tiêu chuẩn

`java.lang.reflect.Proxy` là API công khai để tạo proxy cho interface:

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.getName().equals("findName")) {
        return "Java 17";
    }
    return null;
};

Service service = (Service) Proxy.newProxyInstance(
        Service.class.getClassLoader(),
        new Class<?>[] { Service.class },
        handler);
```

Proxy API là lựa chọn phù hợp khi cần implement interface động. Không cần tự sinh bytecode hoặc gọi internal JDK API cho trường hợp đơn giản này.

### 6.2. Proxy trong named module

Khi interface thuộc named module, proxy class phải tuân thủ quy tắc module và package. JDK có thể tạo proxy trong module/package phù hợp theo visibility của interface.

Nếu proxy implement interface không public hoặc các interface đến từ package/module có visibility hạn chế, cần xem lại:

- Interface có public không?
- Package có export cho module sử dụng không?
- Các interface có thỏa điều kiện cùng package/module theo quy tắc Proxy không?
- Framework có cố truy cập proxy implementation bằng reflection sâu không?

Đừng giả định proxy class luôn nằm trong package ứng dụng hoặc có thể truy cập mọi thành viên nội bộ của interface.

## 7. Rà soát annotation processor

### 7.1. Annotation processor chạy khi nào?

Annotation processor là code chạy trong quá trình biên dịch để đọc annotation, phân tích model và có thể sinh source file hoặc resource mới.

Các API chuẩn gồm:

- `javax.annotation.processing`: giao diện processor, round environment, messager và filer.
- `javax.lang.model`: mô hình type, element, annotation và package.
- `com.sun.source.*`: public compiler tree API để đọc cú pháp source, thuộc module `jdk.compiler`.

Một processor có thể chạy trong JVM của compiler, vì vậy dependency của processor và code xử lý annotation cũng phải tương thích với JDK 17.

### 7.2. Phân biệt API công khai với javac internals

Nên dùng:

- `javax.annotation.processing.AbstractProcessor`.
- `ProcessingEnvironment`, `RoundEnvironment`, `Filer`, `Messager`.
- `TypeElement`, `ExecutableElement`, `VariableElement`, `Types`, `Elements`.
- `com.sun.source.tree` và `com.sun.source.util` khi cần phân tích cây cú pháp bằng API công khai.

Tránh phụ thuộc vào implementation nội bộ như:

- `com.sun.tools.javac.code.*`.
- `com.sun.tools.javac.tree.*`.
- `com.sun.tools.javac.processing.*`.
- `com.sun.tools.javac.util.*`.

Các package nội bộ của compiler không phải API ổn định cho processor bên ngoài. Trên Java 17, strong encapsulation có thể chặn truy cập reflection hoặc truy cập module không được export. Việc mở package nội bộ bằng flag chỉ nên là workaround tạm thời trong khi nâng cấp processor.

### 7.3. Ví dụ processor dùng API chuẩn

Processor tối giản:

```java
package com.acme.processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

public class AuditProcessor extends AbstractProcessor {
    @Override
    public Set<String> getSupportedAnnotationTypes() {
        return Set.of("com.acme.annotations.Audit");
    }

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.RELEASE_17;
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        for (TypeElement annotation : annotations) {
            var elements = roundEnv.getElementsAnnotatedWith(annotation);
            for (var element : elements) {
                processingEnv.getMessager().printMessage(
                        javax.tools.Diagnostic.Kind.NOTE,
                        "Found @Audit on " + element);
            }
        }
        return false;
    }
}
```

Processor này chỉ dùng API chuẩn để tìm element có annotation và ghi diagnostic. Nó không cần truy cập class nội bộ của javac.

### 7.4. Đăng ký processor trên classpath

Nếu processor được đóng gói như JAR thông thường, có thể đăng ký qua service provider file:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung file là tên class processor:

```text
com.acme.processor.AuditProcessor
```

Khi biên dịch, đặt processor JAR trên processor path:

```bash
javac --processor-path processor.jar -d out src/com/acme/App.java
```

`--processor-path` (hoặc `-processorpath`) chỉ định nơi tìm annotation processor. Nó khác `--class-path`: processor path là nơi compiler tìm code processor; classpath là nơi tìm dependency của chương trình đang biên dịch.

### 7.5. Đăng ký processor như named module

Nếu processor được modular hóa, module descriptor có thể khai báo:

```java
module com.acme.audit.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with com.acme.processor.AuditProcessor;
}
```

Đặt processor module trên processor module path:

```bash
javac --processor-module-path processor-mods -d out src/com/acme/App.java
```

Nếu processor sử dụng public compiler tree API trong `com.sun.source.*`, module processor có thể cần `requires jdk.compiler;`. Không dùng package `com.sun.tools.javac.*` như dependency API ổn định.

### 7.6. Chỉ định processor tường minh

Để tránh tự động phát hiện mọi processor trên path, có thể chỉ định class:

```bash
javac --processor-path processor.jar --processor com.acme.processor.AuditProcessor -d out src/com/acme/App.java
```

Trong build có nhiều processor, việc chỉ định rõ danh sách giúp kiểm soát processor nào được thực thi và giảm khác biệt giữa môi trường developer/CI.

### 7.7. Chẩn đoán processor

Một số tùy chọn javac hữu ích:

| Tùy chọn | Mục đích |
|---|---|
| `-proc:none` | Không chạy annotation processing |
| `-proc:only` | Chỉ chạy annotation processing, không thực hiện compile thông thường |
| `-processor <class>` | Chỉ định processor class |
| `-processorpath <path>` | Đường dẫn tìm processor trên classpath |
| `--processor-module-path <path>` | Đường dẫn tìm processor module |
| `-s <directory>` | Thư mục chứa source được processor sinh ra |
| `-d <directory>` | Thư mục output class |

Ví dụ tắt processing để xác định lỗi có đến từ processor hay không:

```bash
javac -proc:none -d out src/com/acme/App.java
```

Nếu build thành công khi tắt processing, đó là manh mối để điều tra processor hoặc code được sinh ra. Không phải giải pháp cuối cùng nếu dự án phụ thuộc vào source được processor tạo.

### 7.8. Processor chạy trong compile-time, không phải runtime

Annotation processor thường chạy khi build/compile. Runtime image tạo bằng jlink không cần chứa processor nếu ứng dụng chỉ cần class đã được sinh và biên dịch.

Tách rõ:

- Processor JAR là build-time dependency.
- Generated source/class là build output.
- Runtime dependency là class/JAR/module cần khi ứng dụng chạy.

Không đưa processor vào runtime image chỉ vì processor được dùng trong quá trình biên dịch, trừ khi chính ứng dụng có một yêu cầu runtime riêng đối với thư viện đó.

## 8. Khi annotation processor dùng javac internals

### 8.1. Dấu hiệu thường gặp

Khi nâng JDK, một processor cũ có thể gặp:

- `IllegalAccessError` khi truy cập class/package nội bộ của `jdk.compiler`.
- `InaccessibleObjectException` khi dùng reflection sâu.
- `NoSuchFieldError` hoặc `NoSuchMethodError` do implementation của javac thay đổi.
- `ClassNotFoundException` hoặc `NoClassDefFoundError` do processor path/module path không đúng.
- Lỗi sinh source/class do processor giả định cấu trúc nội bộ của compiler.

Các lỗi này có thể đến từ processor trực tiếp hoặc dependency mà processor sử dụng.

### 8.2. Dùng add-exports/add-opens chỉ như workaround tạm thời

Nếu processor cũ tham chiếu public class trong package nội bộ chưa export, có thể thử mở export ở compile time:

```bash
javac --add-exports jdk.compiler/com.sun.tools.javac.code=ALL-UNNAMED \
      --processor-path processor.jar \
      -d out src/com/acme/App.java
```

Nếu processor dùng reflection sâu vào private member của compiler, cần mở package cho JVM chạy javac. Tùy chọn `-J` chuyển đối số đến JVM khởi chạy compiler:

```bash
javac -J--add-opens=jdk.compiler/com.sun.tools.javac.processing=ALL-UNNAMED \
      --processor-path processor.jar \
      -d out src/com/acme/App.java
```

Các package ví dụ chỉ minh họa. Chỉ mở đúng package được nêu trong lỗi thực tế và đúng module đích. Không thêm hàng loạt package `com.sun.tools.javac.*`.

Workaround có thể giúp một build cũ chạy tạm, nhưng không bảo đảm processor tương thích với các bản JDK tiếp theo. Hướng xử lý lâu dài là cập nhật processor hoặc chuyển sang API công khai.

### 8.3. Kiểm tra processor version

Với mỗi processor:

1. Xác định tên artifact và phiên bản thực tế trong build dependency tree.
2. Đọc release notes để tìm hỗ trợ Java 17 và thay đổi liên quan javac/JPMS.
3. Kiểm tra processor có dùng `com.sun.tools.javac.*` hay không.
4. Cập nhật lên bản được nhà cung cấp hỗ trợ.
5. Xóa workaround module nếu bản mới không còn cần.
6. Chạy lại compile sạch để bảo đảm source được sinh nhất quán.

Một số processor có thể phụ thuộc sâu vào implementation của javac. Không nên suy ra tính tương thích chỉ từ việc ứng dụng runtime chạy được trên Java 17; processor cần được kiểm tra trong chính bước compile bằng JDK 17.

## 9. Quy trình rà soát khi nâng cấp lên Java 17

### Bước 1 — Kiểm kê thành phần có liên quan

Lập danh sách:

- Framework ORM, DI, proxy, AOP và serialization.
- Thư viện bytecode generation.
- Annotation processor và compiler plugin.
- Thư viện test/mocking.
- Các đoạn code gọi reflection hoặc MethodHandles.
- Thư viện sử dụng JNI hoặc JDK internal API.

Kiểm tra dependency tree để biết phiên bản thực tế được resolve, kể cả dependency bắc cầu. Không chỉ rà soát dependency khai báo trực tiếp.

### Bước 2 — Phân tích JDK internal API

Chạy:

```bash
jdeps --jdk-internals --recursive --multi-release 17 app.jar
jdeprscan --release 17 --for-removal app.jar
```

Chạy thêm với các dependency JAR cần kiểm tra. Ghi lại class/package nội bộ được tham chiếu và API công khai thay thế.

### Bước 3 — Tìm reflection và class generation động

Tìm trong source và cấu hình các từ khóa:

```text
setAccessible
trySetAccessible
getDeclaredField
getDeclaredMethod
getDeclaredConstructor
privateLookupIn
Class.forName
defineClass
defineHiddenClass
Proxy.newProxyInstance
```

Đồng thời kiểm tra:

- Cấu hình framework có bật field access hoặc private access không?
- Có class name được nạp từ file cấu hình/plugin không?
- Có bytecode được sinh trong runtime không?
- Có code được generate tại compile time không?

Tìm kiếm source chỉ là bước đầu vì framework có thể gọi các API này ở bên trong dependency.

### Bước 4 — Cập nhật thư viện

Ưu tiên phiên bản được nhà cung cấp xác nhận hỗ trợ Java 17. Kiểm tra riêng:

- Framework có hỗ trợ strong encapsulation không?
- Bytecode generator có hiểu class file version 61 và module boundary không?
- Annotation processor có tương thích với javac 17 không?
- Có bản vá cho `InaccessibleObjectException`, `IllegalAccessError` hoặc lỗi proxy không?

Nếu dependency không còn được duy trì, đánh giá thay thế hoặc cô lập nó thay vì tiếp tục mở rộng quyền truy cập nội bộ của JDK.

### Bước 5 — Chỉ thêm module flags có phạm vi nhỏ

Khi chưa thể loại bỏ dependency cũ:

1. Ghi nhận module nguồn và package chính xác trong lỗi.
2. Xác định module đích (tên module hoặc `ALL-UNNAMED`).
3. Phân biệt cần `--add-exports` hay `--add-opens`.
4. Thêm flag ở đúng giai đoạn: compile time hoặc runtime.
5. Ghi chú lý do, dependency sở hữu và phiên bản dự kiến loại bỏ workaround.

Không đặt một flag mở rộng toàn module vào script chung chỉ để che một lỗi chưa được hiểu.

### Bước 6 — Kiểm thử các đường đi ít dùng

Các tính năng cần chạy thử:

- Khởi động ứng dụng và scan component.
- ORM load entity, lazy proxy, mapping field private.
- JSON/XML serialization/deserialization.
- Dependency injection, AOP và dynamic proxy.
- Mocking trong test.
- Plugin loading và reflection theo cấu hình.
- Compile sạch có annotation processing.
- Build incremental và build trên CI.

### Bước 7 — Xóa workaround không còn cần

Sau khi nâng framework/processor:

- Thử chạy không có `--add-opens`/`--add-exports`.
- Xóa flag từng cái một.
- Chạy lại test cho tính năng liên quan.
- Giữ lại chỉ flag thực sự cần, với phạm vi hẹp và tài liệu giải thích.

## 10. Kiểm thử và quan sát trên Java 17

### 10.1. Kiểm thử trên JDK mục tiêu thực tế

Chạy compile và test bằng JDK 17 thực tế sẽ triển khai, không chỉ biên dịch bằng JDK mới hơn rồi đặt target bytecode 17. Việc đặt target version không mô phỏng toàn bộ module system, reflection và implementation của javac 17.

### 10.2. Bật log để xác định lỗi

Khi có lỗi truy cập, giữ đầy đủ:

- Exception type và message.
- Tên module nguồn.
- Package bị chặn.
- Module đích/caller.
- Stack trace đầy đủ.
- Phiên bản JDK và dependency liên quan.

Thông báo `InaccessibleObjectException` thường nêu package/module cần mở. Dùng thông tin đó để xác định quyền cần thiết thay vì mở package một cách phỏng đoán.

### 10.3. Kiểm tra cả runtime và compile-time

| Giai đoạn | Thành phần cần kiểm tra |
|---|---|
| Compile | javac, annotation processor, compiler plugin, generated source |
| Test | Mock framework, proxy, reflection, test runtime |
| Startup | Dependency injection, ORM bootstrap, service loading |
| Runtime feature | Serialization, dynamic class loading, plugin, scripting |
| Production-like | Class loader lifecycle, module flags, native dependencies |

Một build compile thành công không chứng minh processor không có vấn đề ở build khác hoặc incremental compile. Một test đơn giản cũng không chứng minh framework không dùng reflection ở một tính năng khác.

## 11. Những lỗi thường gặp khi nâng lên Java 17

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `InaccessibleObjectException` | Reflection sâu vào package chưa được open | Nâng framework; nếu cần, mở đúng package bằng `opens` hoặc `--add-opens` |
| `IllegalAccessError` | Code tham chiếu kiểu/member trong package không được export cho module caller | Dùng API công khai; kiểm tra `exports` hoặc `--add-exports` có phạm vi hẹp |
| `NoSuchFieldException` sau khi nâng JDK | Code/framework dựa vào field nội bộ không ổn định | Bỏ phụ thuộc implementation; dùng API được hỗ trợ |
| `NoSuchMethodError` hoặc `NoSuchFieldError` trong processor | Processor phụ thuộc cấu trúc nội bộ của javac đã thay đổi | Cập nhật processor và kiểm tra compatibility với JDK 17 |
| Proxy tạo được nhưng gọi method lỗi | Module/package visibility hoặc generated class nằm trong loader/module không phù hợp | Kiểm tra interface visibility, class loader và module của proxy |
| `IllegalAccessException` từ `privateLookupIn` | Caller không đọc target module hoặc package target chưa open | Điều chỉnh module descriptor hoặc dùng API công khai |
| Class generation lỗi verifier | Bytecode sai, class file version không phù hợp hoặc access flags/package không hợp lệ | Cập nhật bytecode library và sinh class file tương thích Java 17 |
| Processor không được chạy | Processor JAR không nằm trên processor path/module path hoặc service registration sai | Kiểm tra `--processor-path`/`--processor-module-path` và service descriptor |
| Generated source không được compile | Processor sinh source sai package, tên hoặc kiểu | Kiểm tra output của `-s`, log processor và generated source |
| Ứng dụng chỉ chạy khi có nhiều add-opens | Framework cũ đang phụ thuộc reflection sâu vào JDK internals | Cập nhật/thay framework; giữ workaround tối thiểu trong thời gian chuyển tiếp |

### 11.1. Hiểu đúng lỗi module access

Khi thấy lỗi truy cập, phân loại trước:

- Lỗi compile vì package không export: xem `exports`/`--add-exports`.
- Lỗi reflection sâu vì package không open: xem `opens`/`--add-opens`.
- Lỗi `privateLookupIn`: kiểm tra readability và opens.
- Lỗi class definition: kiểm tra loader, package, module, lookup mode và bytecode.
- Lỗi processor: xác định lỗi xảy ra trong JVM chạy javac hay trong module graph của source đang compile.

Đừng thêm cả hai loại flag cho mọi lỗi. Quyền truy cập thông thường và quyền reflection sâu giải quyết hai vấn đề khác nhau.

### 11.2. Trường hợp đặc biệt của sun.misc.Unsafe

Một số code cũ dùng `sun.misc.Unsafe` cho thao tác bộ nhớ hoặc cấp phát đặc biệt. Đây là API nội bộ/không được khuyến nghị cho ứng dụng thông thường; một số API quan trọng vẫn được giữ khả dụng vì lý do tương thích, nhưng không nên xem đó là hợp đồng ổn định.

Khi rà soát, tìm cả `sun.misc.Unsafe` và các API nội bộ khác. Nếu có thể, thay bằng API chuẩn phù hợp như VarHandle, ByteBuffer, java.util.concurrent hoặc các API memory/access được hỗ trợ trong phiên bản Java mục tiêu. Không chuyển sang một internal API khác chỉ để tránh lỗi hiện tại.

## 12. Những điểm cần lưu ý về class file và bytecode trên Java 17

Java 17 hỗ trợ class file version 61. Thư viện sinh bytecode phải tạo class file tương thích với runtime đích và hiểu các cấu trúc bytecode/attribute mà nó cần xử lý.

Khi rà soát:

- Xác nhận bytecode library hỗ trợ class file version 61.
- Kiểm tra target version mà framework yêu cầu khi sinh class.
- Không dùng class file mới hơn Java 17 nếu ứng dụng phải chạy trên Java 17.
- Kiểm tra stack map frames, access flags, nestmate và module/package assumptions.
- Chạy test thực tế cho proxy, mock, ORM lazy loading và generated accessor.

Việc biên dịch source bằng `--release 17` giúp giới hạn API Java mà source được phép sử dụng, nhưng không tự kiểm tra toàn bộ bytecode được sinh động bởi framework lúc runtime.

## 13. Checklist rà soát trước khi phát hành Java 17

### Reflection

- [ ] Đã tìm `setAccessible`, `trySetAccessible`, `getDeclared*` và `privateLookupIn`.
- [ ] Đã phân biệt lỗi export với lỗi open.
- [ ] Đã cập nhật framework ORM, DI, serialization, proxy và mocking.
- [ ] Mọi `--add-opens` còn lại đều có module/package đích cụ thể và lý do được ghi nhận.
- [ ] Không dựa vào `--illegal-access`.

### Bytecode generation

- [ ] Đã liệt kê framework sinh proxy/class lúc runtime.
- [ ] Bytecode library hỗ trợ class file version 61.
- [ ] Ưu tiên API công khai như `Lookup.defineClass`, `defineHiddenClass` hoặc `Proxy` khi phù hợp.
- [ ] Không reflection vào implementation nội bộ của ClassLoader/javac/JDK.
- [ ] Đã kiểm thử class loader, module và package access của generated class.

### Annotation processor

- [ ] Đã kiểm kê processor trực tiếp và bắc cầu.
- [ ] Processor tương thích với javac 17.
- [ ] Processor dùng API chuẩn `javax.annotation.processing`/`javax.lang.model` khi có thể.
- [ ] Processor không phụ thuộc `com.sun.tools.javac.*` nếu có lựa chọn được hỗ trợ.
- [ ] Processor path/module path và service registration được cấu hình rõ.
- [ ] Generated source được kiểm tra trong clean build và CI.

### Build và runtime

- [ ] Đã chạy `jdeps --jdk-internals` trên ứng dụng và dependency phù hợp.
- [ ] Đã chạy `jdeprscan --release 17`.
- [ ] Đã chạy test tích hợp bằng JDK 17 thực tế.
- [ ] Đã thử các tính năng ít dùng: startup scan, proxy, ORM, serialization, plugin và compile processing.
- [ ] Đã xóa các module flags không còn cần sau khi cập nhật dependency.

## 14. Bài tập thực hành

### Bài 1 — Phân biệt exports và opens

Một framework gọi `setAccessible(true)` trên field private của entity thuộc module ứng dụng. Module descriptor chỉ có `exports com.acme.entity`.

1. Vì sao có thể vẫn gặp `InaccessibleObjectException`?
2. Cần dùng `opens` hay `exports`?
3. Hãy viết chỉ thị mở package cho module framework cụ thể.

**Gợi ý:** `exports` cho truy cập API công khai; reflection sâu cần `opens`. Ví dụ:

```java
opens com.acme.entity to org.example.orm;
```

### Bài 2 — Xử lý lỗi privateLookupIn

Một module `com.acme.app` gọi `MethodHandles.privateLookupIn` với class thuộc module `com.acme.model`. Nêu hai điều kiện module cần thỏa và cách sửa module descriptor.

### Bài 3 — Tìm JDK internal API

Chạy:

```bash
jdeps --jdk-internals --recursive --multi-release 17 app.jar
```

Đọc kết quả, xác định class ứng dụng/dependency tham chiếu package nội bộ và tìm API thay thế được JDK gợi ý. Sau đó chạy lại để xác nhận dependency đã được loại bỏ.

### Bài 4 — Rà soát annotation processor

Một processor lỗi `IllegalAccessError` khi truy cập `com.sun.tools.javac.tree`.

1. Vì sao package này không phải API ổn định cho processor?
2. Những API chuẩn nào có thể thay thế?
3. Nên kiểm tra phiên bản processor và module path ra sao?
4. Vì sao thêm `--add-exports` chỉ là workaround?

### Bài 5 — Chọn API định nghĩa class

Một framework cần tạo implementation class trong cùng package với class sở hữu lookup. So sánh:

- `ClassLoader#defineClass`.
- `MethodHandles.Lookup#defineClass`.
- `MethodHandles.Lookup#defineHiddenClass`.

Chọn API phù hợp và nêu giới hạn về package, class loader và khả năng tìm class theo tên.

### Bài 6 — Tạo checklist migration

Chọn một dự án có ORM, dependency injection và annotation processor. Lập danh sách dependency cần kiểm tra, lệnh jdeps/jdeprscan, các tính năng cần test và mọi module flag tạm thời. Xác định điều kiện để xóa từng flag.

## 15. Tài liệu chính thức của Java 17

- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): chính sách strong encapsulation trong Java 17 và trạng thái của `--illegal-access`.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396): thay đổi mặc định strong encapsulation từ Java 16.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module, exports, opens và các tùy chọn `--add-exports`/`--add-opens`.
- [Java SE 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible` và quy tắc reflection.
- [Java SE 17 API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): exception khi không thể bật quyền truy cập phản chiếu.
- [Java SE 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `privateLookupIn`, `defineClass` và `defineHiddenClass`.
- [Java SE 17 API — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): API tạo dynamic proxy cho interface.
- [Java 17 javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): processor path/module path và tùy chọn compiler.
- [Java 17 jdeps command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency và JDK internal API.
- [Java 17 jdeprscan command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): phát hiện việc sử dụng API deprecated.
- [Java SE 17 API — javax.annotation.processing](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html): API chuẩn cho annotation processor.
- [Java SE 17 API — javax.lang.model](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/package-summary.html): mô hình type, element và package dùng trong annotation processing.
- [Java SE 17 API — com.sun.source.util](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/package-summary.html): public compiler tree API.

**Ghi nhớ:** Java 17 áp dụng strong encapsulation cho JDK internals. Reflection sâu cần package được mở; truy cập API công khai trong package cần được export. Bytecode generator phải tôn trọng class loader, package và module, ưu tiên các API như `Lookup#defineClass` hoặc `defineHiddenClass`. Annotation processor nên dùng `javax.annotation.processing` và `javax.lang.model` thay vì `com.sun.tools.javac.*`. Hãy dùng `jdeps --jdk-internals`, `jdeprscan`, rà soát source/dependency và test bằng JDK 17 thật; chỉ giữ `--add-opens`/`--add-exports` như workaround hẹp, có lý do và kế hoạch loại bỏ.
