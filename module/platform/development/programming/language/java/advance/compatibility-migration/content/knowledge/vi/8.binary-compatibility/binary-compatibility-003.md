# Xóa, đổi tên hoặc di chuyển lớp và package

Trong Java, tên đầy đủ của một lớp là một phần của hợp đồng nhị phân. Khi compiler tạo bytecode, nó ghi tên lớp, interface, field và method mà chương trình tham chiếu vào constant pool và descriptor. JVM dùng các tên và descriptor đó để nạp lớp, liên kết method, truy cập field và thực thi lời gọi.

Vì vậy, xóa một class, đổi tên class hoặc chuyển class sang package khác có thể làm các binary đã biên dịch không còn tìm được kiểu mà chúng tham chiếu. Một thay đổi tưởng như chỉ là sắp xếp lại source tree có thể dẫn tới `NoClassDefFoundError`, `ClassNotFoundException`, `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` hoặc lỗi khi nạp service, cấu hình và dữ liệu đã lưu.

Trong một đợt Java compatibility migration, cần phân biệt việc đổi vị trí file `.java` với việc đổi binary name của class. Đổi vị trí file trong repository nhưng giữ nguyên khai báo `package` và tên class thường không làm thay đổi binary identity. Ngược lại, sửa package declaration hoặc tên class sẽ tạo binary name mới, ngay cả khi logic bên trong không đổi.

## 1. Binary name của class là gì?

### 1.1. Tên package và tên class tạo thành binary name

Giả sử source khai báo:

```java
package com.acme.payment;

public class PaymentService {
}
```

Tên đơn giản là `PaymentService`, tên đầy đủ theo source là `com.acme.payment.PaymentService`, và binary name mà JVM dùng để nhận diện class là `com.acme.payment.PaymentService`. Trong class file, tên nội bộ thường được biểu diễn bằng dấu gạch chéo:

```text
com/acme/payment/PaymentService
```

Nếu chuyển class sang package `com.acme.billing`, binary name đổi thành `com.acme.billing.PaymentService`. JVM coi đây là một kiểu khác, dù source code giữ nguyên nội dung và tên class đơn giản.

Tương tự, đổi tên class từ `PaymentService` thành `BillingService` tạo binary name mới. Không có cơ chế tự động để JVM suy luận rằng class mới là class cũ chỉ vì chúng có cùng nội dung.

### 1.2. Binary identity khác với vị trí file source

Java build tool thường mong source nằm trong thư mục tương ứng với package, ví dụ:

```text
src/main/java/
└── com/acme/payment/PaymentService.java
```

Tuy nhiên, điều quyết định tên class được tạo là khai báo package và tên type trong source, không chỉ là đường dẫn file. Compiler có thể biên dịch source từ một đường dẫn khác, nhưng class file vẫn mang binary name theo khai báo.

Di chuyển file `PaymentService.java` sang một thư mục khác mà giữ nguyên:

```java
package com.acme.payment;
public class PaymentService { }
```

thì binary name vẫn là `com.acme.payment.PaymentService`. Đây là thay đổi bố trí source, không phải package migration. Dù vậy, build script, source set, code generator hoặc IDE có thể phụ thuộc vào đường dẫn cũ; cần kiểm tra chúng riêng.

Ngược lại, chỉ sửa dòng package:

```java
package com.acme.billing;
```

đã làm binary name thay đổi. Các client đã compile vẫn tham chiếu tên cũ.

### 1.3. Class loader cũng tham gia vào danh tính runtime

Trong JVM, class được xác định bởi binary name cùng với defining class loader. Hai class cùng tên nhưng được định nghĩa bởi hai class loader khác nhau có thể là hai kiểu không tương thích với nhau. Vì thế, ứng dụng plugin, application server, OSGi hoặc hệ thống có class loader tùy chỉnh cần xem xét cả nơi class được nạp.

Khi di chuyển package, các vấn đề có thể xuất hiện ở parent-first/child-first delegation, package sealing, class loader constraint và giao tiếp giữa module/plugin. Chỉ xác nhận JAR có chứa class mới chưa đủ nếu runtime vẫn nạp một bản class cũ từ class loader khác.

## 2. JVM lưu tham chiếu tới class và method như thế nào?

### 2.1. Constant pool và symbolic reference

Class file chứa constant pool, nơi lưu các tên class, tên method, tên field, kiểu dữ liệu và các symbolic reference cần cho liên kết. Ví dụ source:

```java
PaymentService service = new PaymentService();
service.charge(100L);
```

Bytecode sẽ tham chiếu tới class `com/acme/payment/PaymentService` và method có tên `charge` cùng descriptor tương ứng. JVM dùng thông tin đó để tìm class và method tại runtime.

Nếu class được đổi package, binary name trong constant pool của client cũ không tự được sửa. Nếu method có tham số hoặc kiểu trả về là class đã chuyển package, descriptor cũng thay đổi.

### 2.2. Descriptor có chứa tên kiểu tham chiếu

Ví dụ method:

```java
public Receipt charge(PaymentRequest request) { ... }
```

Nếu `PaymentRequest` nằm trong `com.acme.payment.model` và `Receipt` nằm trong `com.acme.payment.result`, descriptor nhị phân của method chứa tên nội bộ của các kiểu đó, về dạng:

```text
(Lcom/acme/payment/model/PaymentRequest;)Lcom/acme/payment/result/Receipt;
```

Khi chuyển `PaymentRequest` sang package khác, descriptor của method cũng thay đổi. Giữ nguyên tên method `charge` và logic không đủ để giữ binary compatibility.

Các trường hợp cần chú ý:

- Kiểu tham số của method public/protected.
- Kiểu trả về của method.
- Kiểu field public/protected.
- Superclass và interface được triển khai.
- Constructor có tham số là class đã di chuyển.
- Kiểu được dùng trong annotation, generic signature hoặc exception declaration.
- Kiểu được tham chiếu bởi bridge method hoặc generated bytecode.

Generic type arguments thường bị type erasure trong descriptor, nhưng generic signature metadata vẫn có thể chứa tên class. Công cụ phân tích API và compiler consumer có thể phát hiện thay đổi này dù descriptor đã xóa một phần thông tin generic.

## 3. Xóa class gây ra những lỗi nào?

### 3.1. Class đã compile nhưng không còn trong runtime classpath

Giả sử client được biên dịch với thư viện version 1 có:

```java
package com.acme.payment;

public class PaymentService {
    public void charge() { }
}
```

Client:

```java
import com.acme.payment.PaymentService;

public class Checkout {
    public void complete() {
        new PaymentService().charge();
    }
}
```

Ở version 2, thư viện xóa `PaymentService` mà không giữ lớp tương thích. Client cũ vẫn có thể tồn tại dưới dạng bytecode đã biên dịch, nhưng khi JVM cần nạp `PaymentService`, runtime không tìm thấy class. Tùy thời điểm và cách class được sử dụng, lỗi thường là:

```text
java.lang.NoClassDefFoundError: com/acme/payment/PaymentService
```

Nếu ứng dụng dùng reflection:

```java
Class.forName("com.acme.payment.PaymentService");
```

thì có thể nhận `ClassNotFoundException`. Hai lỗi có ngữ cảnh khác nhau: `ClassNotFoundException` thường được ném bởi API nạp class tường minh như `Class.forName`, còn `NoClassDefFoundError` là lỗi linkage khi JVM cần một class nhưng không thể tìm/nạp được class đó.

### 3.2. Xóa class được dùng làm kiểu tham số hoặc kiểu trả về

Một client có thể không trực tiếp khởi tạo class nhưng vẫn tham chiếu nó trong descriptor của method:

```java
public interface PaymentGateway {
    Receipt charge(PaymentRequest request);
}
```

Nếu `Receipt` hoặc `PaymentRequest` bị xóa khỏi runtime, lỗi có thể xuất hiện khi JVM nạp interface, kiểm tra method, reflection hoặc thực thi lời gọi. Không nên chỉ tìm `new OldClass()` để xác định phạm vi ảnh hưởng; cần tìm mọi vị trí kiểu đó xuất hiện trong public/protected API và dependency graph.

### 3.3. Xóa method hoặc constructor liên quan

Nếu class vẫn tồn tại nhưng method mà client cũ gọi bị xóa, đổi tên hoặc đổi descriptor, JVM có thể ném `NoSuchMethodError`. Nếu field bị xóa hoặc đổi descriptor, có thể ném `NoSuchFieldError`.

Đổi constructor cũng là một dạng thay đổi nhị phân. Constructor được biểu diễn như method đặc biệt `<init>` với descriptor riêng. Nếu client cũ gọi constructor `(String)`, nhưng version mới chỉ còn constructor `(Path)`, bytecode cũ không tự tìm constructor mới thay thế.

### 3.4. Xóa class có thể gây lỗi muộn

Không phải mọi class được tham chiếu đều được nạp ngay khi ứng dụng khởi động. Một class chỉ được dùng trong nhánh xử lý hiếm, plugin tùy chọn, scheduled job hoặc endpoint ít người gọi có thể chỉ gây lỗi khi chức năng đó được thực thi.

Do đó, startup test không đủ để chứng minh class removal an toàn. Cần kiểm tra toàn bộ consumer và các luồng sử dụng class, bao gồm reflection, service loading và cấu hình bên ngoài.

## 4. Đổi tên hoặc di chuyển class/package là thay đổi binary name

### 4.1. Đổi tên class

Từ:

```java
package com.acme.payment;
public class PaymentService { }
```

sang:

```java
package com.acme.payment;
public class BillingService { }
```

đã tạo một binary name mới. Client tham chiếu `com.acme.payment.PaymentService` không tự chuyển sang `BillingService`.

### 4.2. Di chuyển class sang package mới

Từ:

```java
package com.acme.payment;
public class PaymentService { }
```

sang:

```java
package com.acme.billing;
public class PaymentService { }
```

binary name mới là `com.acme.billing.PaymentService`. Đây là thay đổi tên kiểu từ góc nhìn JVM. Tất cả client, subclass, annotation, resource và cấu hình ghi tên cũ đều cần được xem xét.

### 4.3. Di chuyển package không chỉ ảnh hưởng import

Một thay đổi package có thể ảnh hưởng:

- Bytecode tham chiếu tới class cũ.
- Method descriptor chứa kiểu cũ.
- Kế thừa, interface implementation và generic signature.
- Package-private class, field, constructor và method.
- Reflection và `Class.forName`.
- `ServiceLoader`, file `META-INF/services` và `module-info.java`.
- Java serialization và dữ liệu đã lưu.
- Annotation scanning của framework, component scan và entity scan.
- Resource nằm dưới package path.
- JNI/native method và tên symbol.
- Tài liệu, cấu hình XML/YAML/properties và script triển khai.

Vì vậy, refactor package trong IDE có thể cập nhật source trong một repository, nhưng không tự cập nhật consumer bên ngoài, dữ liệu serialized cũ hoặc hệ thống tích hợp sử dụng tên class dạng chuỗi.

## 5. Package-private access và runtime package

### 5.1. Chuyển package có thể làm mất quyền truy cập

Các thành phần không khai báo `public` hoặc `protected` có thể chỉ được truy cập trong cùng package theo quy tắc Java. Ví dụ:

```java
package com.acme.payment;

class PaymentValidator {
    void validate() { }
}

public class PaymentService {
    void execute() {
        new PaymentValidator().validate();
    }
}
```

Nếu chuyển riêng `PaymentValidator` sang `com.acme.validation`, `PaymentService` không còn truy cập được class/method package-private như trước. Compiler có thể báo lỗi source ngay khi biên dịch lại.

Ngay cả khi chuyển cả hai class, các class khác trong package cũ có thể mất quyền truy cập vào member package-private. Cần kiểm tra package boundary và xác định liệu member nên được mở rộng visibility, thay đổi API hoặc đặt lại các class liên quan cùng package.

### 5.2. Runtime package không chỉ dựa vào tên package

Trong JVM, runtime package gắn với tên package và defining class loader. Hai class có cùng package name nhưng được nạp bởi class loader khác nhau không nhất thiết thuộc cùng runtime package. Điều này quan trọng với plugin, application server và hệ thống module/class loader tùy chỉnh.

Khi chuyển class giữa JAR, module hoặc class loader, package-private access có thể thay đổi dù tên package source không đổi. Cần kiểm tra cách đóng gói và nạp class trong môi trường thực tế.

### 5.3. Sealed class và quan hệ package

Sealed class/interface có danh sách permitted subclasses. Với các class trong unnamed module, các quy tắc về package và module ảnh hưởng đến nơi subclass được phép tồn tại. Di chuyển class hoặc permitted subclass sang package/module khác có thể làm khai báo sealed type không còn hợp lệ hoặc làm thay đổi khả năng mở rộng.

Khi di chuyển package, kiểm tra:

- Mệnh đề `permits` và tên đầy đủ của subclass.
- Quy tắc cùng package khi các type ở unnamed module.
- Quan hệ module khi các type ở named module.
- Các subclass được sinh bởi plugin hoặc module khác.

## 6. Java Platform Module System (JPMS) khi chuyển package

### 6.1. `exports` và `opens` cần cập nhật

Trong dự án dùng `module-info.java`, package được export hoặc open bằng tên package. Ví dụ:

```java
module com.acme.payment {
    exports com.acme.payment.api;
    opens com.acme.payment.model to com.fasterxml.jackson.databind;
}
```

Nếu chuyển `com.acme.payment.api` sang `com.acme.billing.api`, module descriptor cần cập nhật `exports`. Nếu framework dùng reflection vào model mới, `opens` cũng cần trỏ tới package mới.

Một package không được export có thể vẫn được dùng nội bộ module nhưng consumer ở module khác không truy cập được. Một package không được open có thể làm reflection sâu thất bại dù code compile bình thường.

### 6.2. `uses` và `provides` của ServiceLoader

Module descriptor có thể khai báo:

```java
module com.acme.payment {
    uses com.acme.payment.spi.PaymentProvider;
    provides com.acme.payment.spi.PaymentProvider
        with com.acme.payment.internal.DefaultPaymentProvider;
}
```

Nếu chuyển interface SPI hoặc implementation sang package mới, phải cập nhật cả `uses` và `provides`. Nếu dùng classpath và file `META-INF/services`, tên interface trong đường dẫn file và tên provider bên trong file cũng phải được cập nhật.

Thiếu cấu hình có thể khiến `ServiceLoader` không tìm thấy provider hoặc ném `ServiceConfigurationError` khi nạp provider không hợp lệ.

### 6.3. Split package và module path

Di chuyển một phần class của package sang JAR/module khác có thể tạo split package. Trên classpath, split package có thể dẫn tới class loading khó đoán tùy class loader. Trên module path, các named module không được cùng chứa package trùng theo quy tắc JPMS; ứng dụng có thể thất bại khi khởi động module layer hoặc resolution.

Khi tách package thành module mới, hãy xác định package thuộc module nào, module nào export/open package và module nào đọc module đó qua `requires`. Tránh để cùng một package tồn tại trong nhiều JAR/module nếu hệ thống sẽ chạy trên module path.

## 7. Reflection, framework scanning và cấu hình dạng chuỗi

### 7.1. Reflection không được compiler cập nhật tự động

Các đoạn code sau phụ thuộc vào tên class dạng chuỗi:

```java
Class<?> type = Class.forName("com.acme.payment.PaymentService");
Object instance = type.getDeclaredConstructor().newInstance();
```

Refactor package trong IDE có thể cập nhật import và type reference tĩnh, nhưng không phải công cụ nào cũng phát hiện chuỗi tên class. Nếu class được đổi tên hoặc chuyển package, cấu hình reflection có thể tiếp tục trỏ tới tên cũ và chỉ lỗi khi chạy.

Rà soát các API và vị trí sau:

- `Class.forName(...)` và `ClassLoader.loadClass(...)`.
- `MethodHandles` và reflection tìm method/field theo tên.
- `ServiceLoader.load(...)` và provider configuration.
- Tên class trong XML, YAML, JSON, properties hoặc database.
- Plugin registry, dependency injection, serializer polymorphic type và scripting.
- Annotation scan theo package prefix.

### 7.2. Framework component scan và entity scan

Các framework có thể dùng package name để giới hạn vùng quét component, controller, repository, entity, mapper hoặc configuration. Ví dụ, một cấu hình scan package cũ có thể không phát hiện bean sau khi chuyển sang package mới.

Kiểm tra:

- Component scan và package scan base package.
- ORM entity scan, repository scan và mapping file.
- Jackson polymorphic type hoặc tên class trong payload.
- Validation provider, converter, serializer và mapper registration.
- Test scan, test configuration và test fixture.
- Native image reflection/resource configuration nếu ứng dụng có build native image.

Một ứng dụng có thể khởi động mà không có bean/entity mới được scan, rồi lỗi khi request hoặc truy vấn đầu tiên chạy. Vì vậy cần test hành vi và kiểm tra registry/metadata sau khi chuyển package.

### 7.3. Resource path đi theo package

Một số API tải resource tương đối với package của class:

```java
InputStream stream = PaymentService.class.getResourceAsStream("messages.properties");
```

Nếu resource được đóng gói dưới đường dẫn tương ứng package, di chuyển class có thể làm thay đổi đường dẫn tìm resource. Tương tự, file properties, template, XML mapping, SQL script hoặc schema đặt cạnh class có thể không được tìm thấy sau khi package thay đổi.

Kiểm tra cả resource được copy bởi build tool và resource được tạo trong quá trình build. Không chỉ di chuyển file `.java`; cần xác định hợp đồng resource path và cách framework tìm resource.

## 8. Java serialization và dữ liệu đã lưu

### 8.1. Tên class là một phần của serialized stream

Với Java Object Serialization, stream chứa tên class và metadata của class. Nếu một object được serialize khi class mang tên `com.acme.payment.PaymentRecord`, sau đó class bị đổi package thành `com.acme.billing.PaymentRecord`, dữ liệu cũ có thể không deserialize được nếu runtime không còn class cũ.

Ngay cả khi giữ `serialVersionUID`, việc đổi binary name vẫn là một vấn đề riêng. `serialVersionUID` giúp kiểm tra tương thích cấu trúc serialization của class có cùng identity; nó không tự ánh xạ tên class cũ sang tên mới.

### 8.2. Chiến lược duy trì dữ liệu serialization cũ

Nếu phải đọc dữ liệu cũ, có thể giữ class tương thích tại binary name cũ và cung cấp logic chuyển đổi sang model mới. Một lựa chọn khác là dùng `ObjectInputStream.resolveClass` tùy chỉnh để ánh xạ descriptor cũ sang class mới, nhưng cách này cần được thiết kế cẩn thận và kiểm tra kỹ schema/field compatibility.

Không nên coi việc override `resolveClass` là cách thay package toàn cục đơn giản. Mapping có thể thất bại nếu cấu trúc field, kiểu tham chiếu, hierarchy hoặc serialization protocol đã thay đổi. Với dữ liệu quan trọng lâu dài, cân nhắc định dạng dữ liệu có schema/version rõ ràng như JSON/Avro/Protobuf thay vì phụ thuộc trực tiếp vào tên class Java.

### 8.3. `serialVersionUID`, `readObject` và `readResolve`

Khi giữ class cũ làm compatibility facade, xác định rõ:

- `serialVersionUID` có được khai báo tường minh không.
- Field cũ còn được giữ hay cần chuyển đổi.
- `readObject` có thể chuyển dữ liệu sang representation mới không.
- `readResolve` có thể trả về object mới mà consumer mong đợi không.
- Có serialized object lồng nhau chứa nhiều class đã di chuyển không.

Test bằng dữ liệu serialized thật từ version cũ. Tạo object mới rồi serialize/deserialize trong cùng version mới không chứng minh tương thích dữ liệu lịch sử.

## 9. JNI, native library và tên lớp

JNI có thể dùng tên class, package và signature để liên kết native method. Nếu class hoặc package thay đổi, tên JNI symbol được tạo theo quy tắc mã hóa của JNI có thể thay đổi. Native library cũ có thể không còn tìm thấy method tương ứng.

Rà soát:

- Method khai báo `native`.
- Native library dùng `RegisterNatives` với class và signature cụ thể.
- JNI header sinh từ `javac -h`.
- Native agent, profiler hoặc thư viện C/C++ tìm class qua JNI.
- Cấu hình native image hoặc binding generator.

Sau khi di chuyển class, cần tạo lại JNI header, build native library tương ứng và chạy integration test trên đúng OS/architecture. Đổi package trong Java mà không cập nhật native code có thể làm lỗi chỉ xuất hiện khi gọi native method.

## 10. Giữ tương thích bằng facade, adapter và deprecation

Khi một class public đã được phát hành và có consumer bên ngoài, cách an toàn thường là giữ binary name cũ trong một giai đoạn chuyển tiếp. Class mới trở thành API canonical, còn class cũ đóng vai trò facade/adapter.

### 10.1. Giữ class cũ làm facade kế thừa class mới

Nếu class mới không `final`, không có giới hạn kế thừa và constructors phù hợp, class cũ có thể kế thừa class mới:

```java
// API mới
package com.acme.billing;

public class BillingService {
    public BillingService(String tenant) { }

    public void charge(long amount) { }
}
```

```java
// Compatibility facade tại binary name cũ
package com.acme.payment;

/** @deprecated Use com.acme.billing.BillingService. */
@Deprecated(since = "2.0", forRemoval = false)
public class PaymentService extends com.acme.billing.BillingService {
    public PaymentService(String tenant) {
        super(tenant);
    }
}
```

Client cũ vẫn tìm thấy `com.acme.payment.PaymentService` và constructor cũ. Client mới có thể chuyển dần sang `BillingService`.

Phải giữ tất cả constructor mà consumer cũ có thể gọi. Constructor không được kế thừa tự động, nên facade cần khai báo lại các constructor public/protected cần duy trì. Cần giữ method cũ và descriptor cũ nếu chúng là một phần của API đã phát hành.

### 10.2. Dùng composition khi không thể kế thừa

Nếu class mới là `final`, constructor không phù hợp hoặc kế thừa làm lộ semantics không mong muốn, dùng composition:

```java
package com.acme.payment;

/** @deprecated Use com.acme.billing.BillingService. */
@Deprecated(since = "2.0", forRemoval = false)
public final class PaymentService {
    private final com.acme.billing.BillingService delegate;

    public PaymentService(String tenant) {
        this.delegate = new com.acme.billing.BillingService(tenant);
    }

    public void charge(long amount) {
        delegate.charge(amount);
    }
}
```

Composition giữ API cũ nhưng cần chuyển tiếp đầy đủ method, exception, null contract, lifecycle và semantics. Nếu class cũ có nhiều method public, cần duy trì toàn bộ surface mà consumer đang dùng.

### 10.3. Giữ interface cũ làm interface chuyển tiếp

Nếu một interface được chuyển package, có thể giữ interface cũ mở rộng interface mới:

```java
package com.acme.billing.spi;

public interface BillingProvider {
    Receipt charge(Request request);
}
```

```java
package com.acme.payment.spi;

/** @deprecated Use com.acme.billing.spi.BillingProvider. */
@Deprecated(since = "2.0", forRemoval = false)
public interface PaymentProvider extends com.acme.billing.spi.BillingProvider {
}
```

Class cũ đã `implements PaymentProvider` sẽ đồng thời là instance của interface mới thông qua quan hệ kế thừa. Tuy nhiên, nếu interface mới thêm abstract method, class implementation cũ có thể không cung cấp implementation. Khi method đó được gọi, runtime có thể ném `AbstractMethodError`. Cần giữ hợp đồng method cũ hoặc cung cấp default method/adapter có semantics phù hợp.

### 10.4. Giữ kiểu cũ trong chữ ký API cũ

Một lỗi thường gặp là giữ class facade cũ nhưng đổi ngay method cũ để nhận/trả về type mới:

```java
// API cũ
public OldReceipt charge(OldRequest request);

// Không tương thích binary nếu thay descriptor
public NewReceipt charge(NewRequest request);
```

Tên method giống nhau không giữ được binary descriptor. Nên giữ method cũ với kiểu cũ và thêm API mới có tên hoặc chữ ký khác:

```java
public OldReceipt charge(OldRequest request) {
    NewReceipt result = billingService.charge(convert(request));
    return convertBack(result);
}

public NewReceipt chargeNew(NewRequest request) {
    return billingService.charge(request);
}
```

Nếu cần chuyển đổi kiểu, định nghĩa rõ adapter và hành vi đối với null, lỗi, field không còn tương ứng và dữ liệu mặc định.

## 11. Di chuyển package theo từng giai đoạn

Một package migration lớn nên được chia thành các bước có thể phát hành độc lập.

### Giai đoạn 1: Chuẩn bị API mới

- Tạo class/interface ở package mới.
- Xác định API canonical và ownership của từng type.
- Thêm adapter/facade cần thiết.
- Cập nhật module descriptor, service provider và resource path.
- Chưa xóa binary name cũ.

### Giai đoạn 2: Duy trì compatibility facade

- Giữ class/interface cũ ở package cũ.
- Forward method/constructor sang API mới.
- Đánh dấu deprecated và cung cấp migration note.
- Giữ descriptor cũ cho method/field/constructor quan trọng.
- Thêm test cho consumer cũ và consumer mới.

### Giai đoạn 3: Chuyển consumer

- Cập nhật import và type reference trong source.
- Cập nhật reflection string, XML/YAML/properties và package scanning.
- Cập nhật service loader, module descriptor, serialization mapping và JNI nếu có.
- Kiểm tra generated source, test fixture và tài liệu.
- Theo dõi warning deprecated để xác định consumer còn dùng API cũ.

### Giai đoạn 4: Ngừng sử dụng API cũ

- Thông báo thời điểm kết thúc hỗ trợ.
- Xác nhận consumer nội bộ và đối tác đã chuyển.
- Đo mức sử dụng nếu hệ thống có telemetry phù hợp.
- Chuẩn bị major release nếu xóa API cũ là breaking change.
- Cung cấp migration guide và phiên bản cuối còn giữ facade.

### Giai đoạn 5: Xóa facade trong major release

Chỉ xóa class/package cũ khi chính sách versioning cho phép breaking change và consumer đã có kế hoạch nâng cấp. Nếu có dữ liệu serialized, plugin ngoài, SDK hoặc integration contract phụ thuộc tên cũ, phải có kế hoạch chuyển đổi riêng. Một major version không tự động làm dữ liệu lịch sử biến mất.

## 12. Kiểm tra phạm vi ảnh hưởng trước khi xóa hoặc di chuyển class

### 12.1. Kiểm tra API public/protected

Lập danh sách:

- Class/interface/enum/record public và protected.
- Constructor public/protected.
- Method và field có kiểu tham số/trả về là class đang di chuyển.
- Superclass/interface, annotation và nested class.
- Generic signature, exception declaration và bridge method.
- SPI, plugin extension point và class được consumer subclass.

Một class không public vẫn có thể được dùng bởi module khác trong cùng package, reflection, framework hoặc code generation. Không nên kết luận class an toàn để xóa chỉ vì nó không xuất hiện trong tài liệu API.

### 12.2. Tìm tham chiếu tĩnh và động

Tìm tên đầy đủ cũ trong source, build file và cấu hình:

```text
com.acme.payment.PaymentService
com.acme.payment.spi.PaymentProvider
```

Tìm cả dạng slash trong cấu hình bytecode/tooling:

```text
com/acme/payment/PaymentService
```

Rà soát `Class.forName`, `loadClass`, reflection, ServiceLoader, module descriptor, framework scanning, serializer type id, JNI và resource lookup. Tên class có thể được tạo từ property hoặc database nên code search đơn thuần không thể phát hiện tất cả.

### 12.3. Kiểm tra JAR và bytecode

Dùng `jar tf` để xem nội dung archive:

```bash
jar tf payment-library.jar
```

Dùng `javap` để xem binary API và descriptor:

```bash
javap -classpath payment-library.jar -public com.acme.payment.PaymentService
javap -classpath payment-library.jar -s com.acme.payment.PaymentService
javap -classpath payment-library.jar -verbose com.acme.payment.PaymentService
```

`-public` giúp xem các member public; `-s` hiển thị descriptor; `-verbose` cho thêm constant pool và metadata. So sánh JAR cũ và mới để xác định class cũ còn tồn tại hay không, method/constructor có giữ descriptor không và package mới đã được đóng gói chưa.

### 12.4. Dùng công cụ API compatibility

Các công cụ như japicmp và Revapi có thể so sánh API của hai artifact và phát hiện class bị xóa/đổi tên, method/field thay đổi, thay đổi modifier hoặc hierarchy. Cần cấu hình đúng scope API và version baseline.

Các công cụ này hữu ích nhưng không thay thế runtime test cho reflection, service loading, serialization, JNI hoặc cấu hình dạng chuỗi. Một class có thể không thuộc public API nhưng vẫn là contract thực tế với framework hoặc plugin.

### 12.5. Dùng jdeps và dependency graph

`jdeps` giúp phân tích dependency giữa class/package/module:

```bash
jdeps -summary payment-library.jar
jdeps -verbose:class payment-library.jar
```

Với ứng dụng nhiều module, kết hợp dependency graph của Gradle/Maven để biết module nào phụ thuộc artifact cũ. Xem cả compile, runtime, test, annotation processor và plugin classpath. Dependency bắc cầu có thể kéo version cũ của thư viện chứa class đã di chuyển.

## 13. Kiểm thử binary compatibility và consumer compatibility

### 13.1. Binary compatibility test

Giữ một consumer fixture được biên dịch với version thư viện cũ. Sau đó chạy chính binary đó với version thư viện mới trong runtime classpath. Đây là cách trực tiếp để phát hiện lỗi linkage do class/method/field bị xóa hoặc đổi descriptor.

Quy trình minh họa:

1. Compile consumer với library v1.
2. Lưu nguyên class file của consumer và dependency cần thiết.
3. Thay library v1 bằng library v2 trên runtime classpath.
4. Chạy các luồng sử dụng class, method, field và constructor liên quan.
5. Ghi lại lỗi linkage và các chức năng không còn hoạt động.

Không compile lại consumer ở bước 3, vì compile lại sẽ kiểm tra source compatibility thay vì binary compatibility.

### 13.2. Source compatibility test

Lấy source consumer cũ và compile lại với library v2. Test này phát hiện import/package không còn tồn tại, visibility thay đổi, overload hoặc type inference thay đổi và các lỗi source khác.

Source compatibility và binary compatibility cần hai pipeline hoặc hai fixture riêng. Một thay đổi có thể pass một loại nhưng fail loại còn lại.

### 13.3. Runtime integration test

Chạy artifact cuối trong môi trường giống production và kiểm tra:

- Khởi động, component scan và dependency injection.
- Gọi endpoint, job, message handler và plugin extension.
- ServiceLoader tìm thấy provider đúng.
- Reflection và serialization đọc được dữ liệu cũ.
- Resource/template/configuration được nạp đúng.
- JNI/native method hoạt động trên OS/architecture đích.
- Module resolution và access rules đúng trên module path.

Kiểm tra cả đường thành công và đường lỗi. Một class cũ có thể chỉ được dùng khi xử lý một loại payload hoặc khi bật một profile cụ thể.

## 14. Ví dụ xuyên suốt: chuyển package nhưng giữ binary compatibility

Giả sử thư viện `payment-core` v1 công bố:

```java
package com.acme.payment;

public class PaymentService {
    public PaymentService(String tenant) { }

    public Receipt charge(PaymentRequest request) { ... }
}
```

Ở v2, nhóm muốn chuyển API sang `com.acme.billing`. Nếu chỉ đổi package của ba class, client cũ sẽ không còn tìm thấy `PaymentService`, `Receipt` và `PaymentRequest` theo binary name cũ. Method descriptor cũng đổi vì hai kiểu dữ liệu đã chuyển package.

Một lộ trình tương thích hơn:

1. Tạo `com.acme.billing.BillingService`, `BillingRequest` và `BillingReceipt`.
2. Giữ `com.acme.payment.PaymentService`, `PaymentRequest` và `Receipt` trong artifact v2.
3. Giữ constructor cũ và method `charge(PaymentRequest)` với descriptor cũ.
4. Trong method cũ, chuyển đổi request sang model mới, gọi service mới và chuyển kết quả về kiểu cũ.
5. Thêm API mới dùng `BillingRequest`/`BillingReceipt` với tên method rõ ràng.
6. Cập nhật module descriptor, service provider, framework scanning và resource path.
7. Compile source consumer cũ với v2 và chạy binary consumer v1 với v2.
8. Kiểm thử serialization của `PaymentRequest`/`Receipt` đã lưu từ v1.
9. Đánh dấu API cũ deprecated, phát hành migration guide và theo dõi consumer chuyển đổi.
10. Chỉ xóa facade cũ trong major release sau khi đã giải quyết dữ liệu và consumer phụ thuộc.

Trong ví dụ này, facade phải giữ cả các kiểu cũ được dùng trong method descriptor. Chỉ giữ class `PaymentService` cũ nhưng xóa `PaymentRequest` hoặc đổi kiểu trả về sang `BillingReceipt` vẫn có thể phá binary compatibility.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách phòng tránh |
|---|---|---|
| Nghĩ chuyển file source là đổi package | Có thể nhầm thay đổi bố trí file với binary name | Kiểm tra package declaration và binary name thực tế |
| Chỉ cập nhật import trong repository | Consumer ngoài, reflection và config vẫn dùng tên cũ | Rà soát mọi contract tĩnh và động |
| Giữ class cũ nhưng đổi kiểu trong method signature | Descriptor thay đổi, binary cũ có thể lỗi linkage | Giữ method cũ với descriptor cũ; thêm API mới riêng |
| Chỉ test compile | Không phát hiện binary cũ hoặc cấu hình runtime | Chạy binary compatibility fixture và integration test |
| Chỉ test startup | Class cũ có thể chỉ được nạp ở nhánh xử lý muộn | Gọi các endpoint/job/plugin và nhánh ít dùng |
| Giữ `serialVersionUID` rồi đổi package | Tên class trong stream vẫn không khớp | Giữ compatibility class hoặc migration mapping có test |
| Quên `META-INF/services`/module descriptor | Service provider không được tìm thấy | Cập nhật `uses`, `provides` và provider file |
| Quên package-private access | Compile lỗi hoặc access runtime thay đổi | Kiểm tra package boundary và class loader |
| Di chuyển package trên module path mà không xem split package | Module resolution có thể thất bại | Xác định package ownership và exports/opens |
| Xóa facade ngay ở minor release | Consumer cũ có thể không chạy | Theo chính sách versioning; dùng deprecation và major release |

## 16. Hồ sơ bàn giao cho một thay đổi class/package

Trước khi chấp nhận xóa, đổi tên hoặc di chuyển class/package, cần lưu:

1. **API inventory:** binary name cũ/mới, visibility, constructors, methods, fields, superclass và interfaces.
2. **Descriptor diff:** tham số, kiểu trả về, field descriptor, generic signature và exception liên quan.
3. **Consumer inventory:** module, artifact, plugin, framework, cấu hình và hệ thống ngoài đang tham chiếu tên cũ.
4. **Runtime contract inventory:** reflection, ServiceLoader, JPMS, serialization, JNI, resource và package scanning.
5. **Compatibility strategy:** facade, adapter, interface bridge, migration mapping hoặc major breaking release.
6. **Binary test report:** consumer binary v1 chạy với thư viện v2.
7. **Source test report:** source consumer v1 compile với thư viện v2.
8. **Integration report:** module, service, plugin, dữ liệu cũ và runtime môi trường đích.
9. **Migration guide:** tên mới, cách thay import/API, thay đổi cấu hình và thời điểm loại bỏ tên cũ.
10. **Release decision:** owner, rủi ro còn lại, version phát hành và phương án rollback.

### Checklist trước khi phát hành

- [ ] Đã xác định binary name cũ và mới của mọi class được di chuyển.
- [ ] Đã kiểm tra method/field/constructor descriptor chứa các type bị đổi package.
- [ ] Đã phân biệt source compatibility với binary compatibility.
- [ ] Đã rà soát subclass, interface implementation và package-private access.
- [ ] Đã cập nhật `exports`, `opens`, `uses`, `provides` và service provider file.
- [ ] Đã rà soát reflection, framework scanning, cấu hình dạng chuỗi và resource path.
- [ ] Đã đánh giá Java serialization và dữ liệu lịch sử.
- [ ] Đã kiểm tra JNI/native binding nếu có.
- [ ] Đã kiểm tra split package và class loader trên môi trường đích.
- [ ] Đã giữ facade/adapter nếu cần hỗ trợ consumer cũ.
- [ ] Đã chạy binary consumer cũ với artifact mới.
- [ ] Đã compile source consumer cũ với API mới.
- [ ] Đã chạy integration test trên artifact cuối và các luồng ít được gọi.
- [ ] Đã chuẩn bị migration guide và kế hoạch loại bỏ facade theo versioning policy.

Xóa, đổi tên hoặc di chuyển class/package là thay đổi hợp đồng nhị phân vì binary name và descriptor được ghi trực tiếp vào class file. Giữ tương thích đòi hỏi duy trì các tên và chữ ký cũ ở nơi consumer còn phụ thuộc, thường bằng facade hoặc adapter, đồng thời cập nhật các contract động như reflection, serialization, service loading và JNI. Khi có binary test, source test và integration test riêng, nhóm có thể xác định rõ phạm vi breaking change và phát hành package migration theo từng giai đoạn.
