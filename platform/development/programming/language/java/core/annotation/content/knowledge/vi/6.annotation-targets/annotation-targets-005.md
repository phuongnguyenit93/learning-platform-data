# `ElementType.PACKAGE` và `package-info.java` trong Java Annotation

## 1. Bài toán: gắn metadata cho cả một package

Trong Java, *package* nhóm các class, interface và các kiểu khác theo không gian tên. Đôi khi ta cần mô tả **chính package**: ai phụ trách, module thuộc nhóm nào, có yêu cầu audit hay có phải package dành cho API công khai không. Nếu mục tiêu là đặt metadata ở cấp package, Java cung cấp đích annotation `ElementType.PACKAGE` và file quy ước `package-info.java`.

Ví dụ về ý tưởng:

```java
@PackagePolicy(owner = "platform", audited = true)
package com.example.orders;
```

Đây là **package declaration đã được chú thích**, chứ không phải một annotation gắn lên class. Trong một dự án Java thông thường, khai báo ấy được đặt trong file `package-info.java` của package tương ứng.

Cần hiểu rõ ba điều từ đầu:

1. `@Target(ElementType.PACKAGE)` xác định **đích được phép đặt** của một annotation type.
2. `package-info.java` là nơi quy ước để viết **package annotations** và Javadoc ở cấp package.
3. Annotation chỉ là metadata. Java không tự thực hiện kiểm tra phân quyền, ghi log hay áp dụng chính sách cho mọi class vì package được gắn annotation. Công cụ hoặc chương trình phải đọc và xử lý nó.

Bài học tập trung vào cách khai báo, sử dụng, biên dịch và đọc annotation ở đích `PACKAGE`; các loại đích khác chỉ được nhắc đến để phân biệt.

## 2. `ElementType.PACKAGE` là gì?

`java.lang.annotation.ElementType` là một enum mô tả các vị trí cú pháp mà annotation được áp dụng. Trong đó, `ElementType.PACKAGE` là **khai báo package**.

Ta giới hạn một annotation type vào đích này bằng `@Target`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
@interface PackageTag {
    String value();
}
```

`PackageTag` được phép đặt trước **package declaration**. Nó không được áp dụng lên khai báo class hoặc method:

```java
// CỐ Ý SAI: PackageTag chỉ có target PACKAGE, không có TYPE
@PackageTag("orders")
class OrderService {
}
```

Compiler có thể thông báo `annotation type not applicable to this kind of declaration`. Vấn đề nằm ở **đích áp dụng**, không phải kiểu `String` hay tên element `value`.

Bảng phân biệt các đích hay bị nhầm:

| `ElementType` | Gắn ở đâu? | Ví dụ nơi gắn |
|---|---|---|
| `PACKAGE` | Khai báo `package ...;` | `package-info.java` |
| `TYPE` | Khai báo class/interface/enum/annotation | `class Order {}` |
| `METHOD` | Khai báo method | `void submit() {}` |
| `FIELD` | Khai báo field | `String id;` |
| `MODULE` | Khai báo module của JPMS | `module-info.java` |

`TYPE` **không thay thế** `PACKAGE`, và `MODULE` là cơ chế riêng của Java Platform Module System. Muốn annotation áp dụng đồng thời cho package và class, có thể khai báo `@Target({ElementType.PACKAGE, ElementType.TYPE})`; chỉ làm vậy nếu metadata thực sự có ý nghĩa ở cả hai vị trí.

## 3. Vì sao dùng file `package-info.java`?

Trong cấu trúc mã Java, mỗi file `.java` thường có package declaration như sau:

```java
package com.example.orders;

public class OrderService {
}
```

Dòng này đưa `OrderService` vào package `com.example.orders`, nhưng bản thân file `OrderService.java` không phải nơi thích hợp để lưu annotation cho package.

**Quy tắc ngôn ngữ:** Annotation đặt trên package declaration phải được viết trong compilation unit có tên `package-info.java`. Vì vậy, ta tạo file theo cấu trúc:

```text
src/
└── com/
    └── example/
        └── orders/
            ├── package-info.java
            ├── PackagePolicy.java
            ├── OrderService.java
            └── Main.java
```

Nội dung `package-info.java` có thể gồm Javadoc cho package, annotation và package declaration:

```java
/**
 * Các dịch vụ xử lý đơn hàng.
 *
 * <p>Package được nhóm platform quản lý.</p>
 */
@PackagePolicy(owner = "platform")
package com.example.orders;
```

Đây là file Java thực sự, không phải Markdown hay file cấu hình riêng. Tên file gồm chữ thường `package-info` và đuôi `.java`, cần giữ đúng chính tả. Vị trí thư mục nên khớp package name theo cách tổ chức source của dự án và build tool.

Lưu ý: `package-info.java` **không khai báo một class tên `package-info`**. Cụm có dấu gạch ngang này là quy ước tên file, không phải Java identifier dùng để đặt tên class.

## 4. Định nghĩa annotation dùng cho `PACKAGE`

Ta tự thiết kế annotation chứa người phụ trách package và cờ audit.

File **`PackagePolicy.java`** trong package `com.example.orders`:

```java
package com.example.orders;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackagePolicy {
    String owner();
    boolean audited() default false;
}
```

Ý nghĩa từng phần:

- `@interface PackagePolicy` khai báo một annotation type tên `PackagePolicy`.
- `@Target(ElementType.PACKAGE)` giới hạn vị trí sử dụng vào package declaration.
- `@Retention(RetentionPolicy.RUNTIME)` giữ annotation ở runtime để các API reflection có thể đọc.
- `owner()` là element `String` **bắt buộc**, phải được cung cấp khi gắn annotation.
- `audited() default false` cho phép bỏ qua `audited` và nhận giá trị mặc định `false`.

Vì khai báo annotation ở package `com.example.orders`, file `package-info.java` cùng package có thể tham chiếu `@PackagePolicy` bằng tên đơn giản. Nếu annotation nằm ở package khác, cần bảo đảm tên được phân giải hợp lệ bằng import hoặc tên đầy đủ.

Thiếu `@Retention(RUNTIME)` không làm định nghĩa package annotation sai. Tuy nhiên, nếu dự định đọc bằng `Package.getAnnotation(...)` khi chạy, chính sách retention là một điều kiện quan trọng.

## 5. Gắn annotation vào khai báo package

File **`package-info.java`**:

```java
/**
 * API và dịch vụ trong miền đơn hàng.
 *
 * <p>Chính sách package dùng để mô tả chủ sở hữu và yêu cầu audit.</p>
 */
@PackagePolicy(owner = "platform", audited = true)
package com.example.orders;
```

Đọc theo thứ tự:

1. Khối `/** ... */` là Javadoc cho package.
2. `@PackagePolicy(owner = "platform", audited = true)` là annotation nằm ngay trước package declaration.
3. `package com.example.orders;` xác định package được chú thích.

Nếu `audited` dùng giá trị mặc định, có thể viết:

```java
@PackagePolicy(owner = "platform")
package com.example.orders;
```

Không được bỏ `owner` vì `PackagePolicy.owner()` không có `default`:

```java
// CỐ Ý SAI: owner là element bắt buộc
@PackagePolicy(audited = true)
package com.example.orders;
```

Những đoạn trên là các **phương án riêng** cho nội dung cùng một file. Trong ví dụ chạy ở phần sau, chỉ dùng một bản `package-info.java` hợp lệ.

### Vị trí các câu lệnh `import`

Cú pháp Java đặt package declaration trước import declarations. Vì thế, nếu cần import cho annotation package, các dòng `import` phải theo **sau** câu lệnh `package ...;`:

```java
@com.example.metadata.PackagePolicy(owner = "orders")
package com.example.orders;
```

Sử dụng tên đầy đủ như trên là cách đơn giản khi annotation type ở package khác. Tránh chuyển `import` lên trước package declaration; đó là sai trật tự cú pháp compilation unit.

## 6. Ví dụ đầy đủ Java 17+: khai báo, áp dụng và đọc package annotation

Ví dụ sau có **ba file**, tất cả thuộc package `com.example.orders`.

### File 1 — `src/com/example/orders/PackagePolicy.java`

```java
package com.example.orders;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackagePolicy {
    String owner();
    boolean audited() default false;
}
```

### File 2 — `src/com/example/orders/package-info.java`

```java
/**
 * Package minh họa metadata ở cấp package.
 *
 * <p>Các class trong package này xử lý nghiệp vụ đơn hàng.</p>
 */
@PackagePolicy(owner = "platform", audited = true)
package com.example.orders;
```

### File 3 — `src/com/example/orders/Main.java`

```java
package com.example.orders;

public class Main {
    public static void main(String[] args) {
        Package currentPackage = Main.class.getPackage();
        PackagePolicy policy =
                currentPackage.getAnnotation(PackagePolicy.class);

        System.out.println("package=" + currentPackage.getName());
        System.out.println("owner=" + policy.owner());
        System.out.println("audited=" + policy.audited());
    }
}
```

Ở thư mục chứa `src`, chạy lệnh sau (JDK 17 trở lên):

```bash
javac -d out src/com/example/orders/PackagePolicy.java src/com/example/orders/package-info.java src/com/example/orders/Main.java
java -cp out com.example.orders.Main
```

**Stdout chính xác:**

```text
package=com.example.orders
owner=platform
audited=true
```

Giải thích hành trình dữ liệu:

1. `javac` biên dịch annotation type `PackagePolicy`, package declaration có annotation và `Main`.
2. Nhờ `RetentionPolicy.RUNTIME`, metadata package tồn tại để runtime đọc.
3. `Main.class.getPackage()` lấy đối tượng `java.lang.Package` biểu diễn package của class `Main`.
4. `getAnnotation(PackagePolicy.class)` đọc annotation mang kiểu `PackagePolicy` trên package đó.
5. `owner()` và `audited()` trả về hai giá trị được khai báo trong `package-info.java`.

**Giới hạn ví dụ:** `Main` giả định package có annotation runtime đúng kiểu; nếu bạn xóa `@PackagePolicy`, đổi retention, bỏ `package-info.class` khỏi kết quả build hoặc chạy với bộ class file không đồng bộ, `getAnnotation(...)` có thể trả `null` và dòng `policy.owner()` sẽ gây `NullPointerException`. Mã production cần kiểm tra `null` hoặc xử lý trường hợp annotation không có.

## 7. `package-info.class` và các chính sách retention

`package-info.java` là mã nguồn. Khi package annotation cần được giữ trong file class, compiler có thể tạo class file metadata mang tên **`package-info.class`** cho package đó. Đây là cơ sở để runtime đọc package annotation sau khi biên dịch và đóng gói.

Với `@Retention`:

| Chính sách | Khi biên dịch và chạy |
|---|---|
| `RetentionPolicy.SOURCE` | Annotation chỉ cần ở mã nguồn; không được ghi giữ trong class file |
| `RetentionPolicy.CLASS` | Annotation có trong class file nhưng không được cung cấp qua cơ chế reflection thông thường |
| `RetentionPolicy.RUNTIME` | Annotation được lưu và có thể đọc qua reflection lúc chạy |

Nếu **không viết `@Retention`**, mặc định là `RetentionPolicy.CLASS`, không phải `RUNTIME`.

Vì vậy, để chạy ví dụ `Package.getAnnotation(PackagePolicy.class)` và nhận giá trị, hãy đặt `@Retention(RetentionPolicy.RUNTIME)` trên `PackagePolicy`.

Lưu ý thêm về build:

- Khi đóng gói JAR, kiểm tra `com/example/orders/package-info.class` được giữ lại nếu chương trình cần metadata runtime. Nếu build tool loại bỏ file này, thông tin cần đọc có thể bị mất.
- File `package-info.java` không tự động xuất hiện trong classpath khi chỉ chạy `java`; chương trình dùng các file `.class` đã biên dịch.
- Không nên suy luận rằng một package luôn có file `package-info.class` trong mọi tình huống. Điều đó phụ thuộc nội dung package declaration, retention và cách compiler/build xử lý.
- Nếu metadata chỉ phục vụ bộ xử lý lúc biên dịch hoặc Javadoc, không nhất thiết phải chọn `RUNTIME`.

Có thể kiểm tra output sau khi biên dịch bằng cách nhìn trong thư mục `out/com/example/orders`. Với ví dụ ở trên, class file chứa package annotation runtime sẽ hiện diện cùng các class file thông thường.

## 8. Đọc package annotation bằng reflection

Java dùng `java.lang.Package` để đại diện metadata của một package. Cách tiếp cận thực tế, khi đã có một class thuộc package cần kiểm tra, là:

```java
Package pkg = SomeClass.class.getPackage();
```

Sau đó kiểm tra:

```java
PackagePolicy policy = pkg.getAnnotation(PackagePolicy.class);
if (policy != null) {
    System.out.println(policy.owner());
}
```

Các API hữu ích:

- `pkg.getName()`: tên package, ví dụ `com.example.orders`.
- `pkg.isAnnotationPresent(PackagePolicy.class)`: annotation kiểu chỉ định có mặt ở runtime hay không.
- `pkg.getAnnotation(PackagePolicy.class)`: lấy annotation cụ thể; có thể trả `null`.
- `pkg.getAnnotations()`: lấy các annotation có mặt trên package theo API reflection.

Một cách đọc có kiểm tra `null`:

```java
package com.example.orders;

public class PolicyReader {
    static String ownerOf(Class<?> type) {
        Package pkg = type.getPackage();
        if (pkg == null) {
            return "<unnamed package>";
        }
        PackagePolicy policy = pkg.getAnnotation(PackagePolicy.class);
        return policy == null ? "<unspecified>" : policy.owner();
    }
}
```

Đoạn này là **mảnh minh họa**, có thể biên dịch khi `PackagePolicy` đã có trong cùng package; không phải chương trình `main` độc lập.

### Phân biệt package annotation và class annotation

`PackagePolicy` gắn lên `package com.example.orders;`, không gắn lên từng class. Vì vậy:

```java
PackagePolicy fromPackage =
        Main.class.getPackage().getAnnotation(PackagePolicy.class);

PackagePolicy fromClass =
        Main.class.getAnnotation(PackagePolicy.class);
```

Với ví dụ mục 6, `fromPackage` nhận được annotation, còn `fromClass` là `null`: vì `Main` **không** được chú thích bằng `@PackagePolicy`. Ngoài ra, `@Target(PACKAGE)` không cho phép chú thích `Main` bằng kiểu annotation đó.

Một framework muốn áp dụng quy tắc metadata package cho từng class phải **chủ động tìm package của class và đọc annotation ở cấp package**. Java không tự thêm annotation lên các class.

### Package và class loader

Trong runtime, các package có liên quan đến class loader định nghĩa class. Vì thế, khi kiểm tra metadata trong ứng dụng dùng nhiều class loader, nên bắt đầu từ **class cụ thể** rồi gọi `SomeClass.class.getPackage()`. Đừng tự cho rằng chỉ cần cùng chuỗi tên package thì luôn có cùng đối tượng `Package` và cùng metadata trong mọi class loader.

## 9. `package-info.java` dùng cho Javadoc

Ngoài package annotation, `package-info.java` là nơi được khuyến nghị để viết **Javadoc cấp package**. Phần mô tả bằng khối `/** ... */` đặt ngay trước annotation và package declaration sẽ được Javadoc xử lý.

Ví dụ:

```java
/**
 * Cung cấp các thao tác kiểm tra và xử lý thanh toán.
 *
 * <p>Các kiểu trong package này cung cấp dịch vụ nội bộ.</p>
 *
 * @since 1.0
 */
package com.example.payment;
```

Đây là một `package-info.java` hoàn toàn hợp lệ dù **không có annotation**. Nó chứng minh hai mục đích của file là độc lập:

1. Mô tả package bằng Javadoc.
2. Gắn annotation vào package declaration khi cần metadata.

Có thể dùng cả hai trong cùng một file. Nếu annotation type có `@Documented`, annotation ấy còn có thể xuất hiện trong tài liệu API do Javadoc sinh ra theo cơ chế tài liệu của Java.

Đừng nhầm dấu `@since` trong **Javadoc comment** với Java annotation. `@since` là Javadoc tag, còn `@PackagePolicy(...)` là Java annotation nằm ngoài comment.

## 10. Lỗi thường gặp với `PACKAGE` và `package-info.java`

### 10.1. Đặt annotation package trong file class bình thường

Ví dụ **sai** nếu đặt trong file `OrderService.java`:

```java
@PackagePolicy(owner = "platform")
package com.example.orders;

public class OrderService {}
```

Annotation nằm trên package declaration chỉ được đặt trong compilation unit có tên `package-info.java`. Cách sửa: đưa khai báo annotation và dòng `package ...;` đã được chú thích sang `package-info.java`; file `OrderService.java` giữ khai báo package thông thường và class.

### 10.2. Dùng sai `@Target`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface TypeOnly {}
```

Annotation `TypeOnly` chỉ cho phép đích `TYPE`, nên `@TypeOnly package com.example.orders;` trong `package-info.java` không hợp lệ. Nếu định gắn trên package, đổi `@Target(ElementType.PACKAGE)` hoặc bổ sung `PACKAGE` vào tập đích đã cho phép.

### 10.3. Thiếu `@Retention(RUNTIME)` khi cần reflection

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
@interface BuildMarker {}
```

`BuildMarker` hợp lệ và có retention mặc định `CLASS`. Nếu gắn `@BuildMarker` trong `package-info.java` thì đừng kỳ vọng `pkg.getAnnotation(BuildMarker.class)` trả annotation lúc runtime. Nếu chương trình cần đọc bằng reflection, khai báo thêm `@Retention(RetentionPolicy.RUNTIME)` trên annotation type rồi biên dịch/đóng gói lại.

### 10.4. Thiếu element bắt buộc

```java
@interface OwnerInfo {
    String team();
    String contact() default "";
}
```

`@OwnerInfo` hoặc `@OwnerInfo(contact = "dev@example.test")` đều không hợp lệ nếu `team` không có `default`. Cần truyền `team = "platform"` hoặc thiết kế lại giá trị mặc định nếu có lý do nghiệp vụ.

Ngoài ra, để loại annotation này gắn lên package một cách minh bạch, nên thêm `@Target(ElementType.PACKAGE)`.

### 10.5. Sai tên package hoặc đường dẫn source

Ví dụ package declaration viết `package com.example.order;` (số ít), nhưng project định bố trí package `com.example.orders` (số nhiều). Tên package thực tế là giá trị **trong câu lệnh `package`**, không suy ra từ tên thư mục. Không khớp có thể khiến annotation nằm ở package khác với package của class đang đọc, hoặc gây lỗi build tùy cấu hình.

Kiểm tra đường dẫn source, nội dung `package-info.java` và câu lệnh `package` của class đang xét đều trỏ đến cùng một package.

### 10.6. Tưởng annotation tự áp dụng sang subpackage

`com.example.orders` và `com.example.orders.internal` là **hai package khác nhau**. Annotation trên `com.example.orders` không tự được kế thừa vào `com.example.orders.internal`.

Nếu subpackage cũng cần metadata cấp package, hãy khai báo `package-info.java` riêng cho subpackage, hoặc xây dựng quy tắc tìm kiếm phân cấp ở phía framework khi có nhu cầu. Đây là logic tự định nghĩa, không phải ngữ nghĩa `@Inherited` sẵn có cho package.

### 10.7. Khai báo metadata package ở nhiều nơi

Không tạo nhiều compilation unit có **package declaration được gắn annotation** cho cùng một package. Java giới hạn tối đa một khai báo package có annotation cho một package trong phạm vi biên dịch phù hợp.

Thực tế, nên để một file `package-info.java` rõ ràng tại package tương ứng, tránh bản trùng trong nhiều source roots gây lỗi hoặc xung đột khi build.

### 10.8. Nhầm `package-info.java` với `module-info.java`

`package-info.java` mô tả **package**; `module-info.java` khai báo **module** (Java 9+). Annotation cho module có đích `ElementType.MODULE` và được đặt tại module declaration; annotation cho package có đích `ElementType.PACKAGE` và được đặt tại package declaration. Hai loại không thay thế nhau.

## 11. Khi nào nên dùng package annotation?

Một số trường hợp hợp lý:

- Gắn tên đội hoặc đơn vị chịu trách nhiệm cho một miền package, để tool nội bộ xuất báo cáo.
- Cung cấp metadata cho các bộ kiểm tra kiến trúc: package thuộc tầng nào, nhóm nào hay phạm vi nào.
- Cấu hình quy tắc ở cấp package khi framework thực sự **được lập trình để đọc package annotation**.
- Tạo metadata cần có trong quá trình biên dịch nhờ annotation processor, hoặc cần phản ánh lúc runtime.

Ví dụ thiết kế:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

enum Layer {
    API, SERVICE, PERSISTENCE
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
@interface Architecture {
    Layer layer();
    String owner();
}
```

Nơi sử dụng, trong `package-info.java` cùng package với `Architecture` (hoặc tham chiếu đầy đủ đến annotation type):

```java
@Architecture(layer = Layer.SERVICE, owner = "platform")
package com.example.service;
```

**Điểm cần hiểu:** đây là dữ liệu mô tả kiến trúc. Compiler mặc định không ngăn một package `SERVICE` gọi package `PERSISTENCE` vì annotation này. Muốn enforce quy tắc phụ thuộc, ta cần bộ kiểm tra, plugin build hoặc framework chuyên đọc và đánh giá metadata.

Thiết kế tốt nên giữ element rõ kiểu, có mặc định hợp lý và chọn `@Retention` theo nơi xử lý thực tế. Tránh nhúng dữ liệu biến đổi thường xuyên hoặc bí mật vào annotation vì metadata có thể được phân phối cùng artifact biên dịch.

## 12. Bài tập tự kiểm tra

Xét annotation type sau:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
@interface ResponsibleTeam {
    String value();
    int priority() default 1;
}
```

Giả sử có file `src/com/example/catalog/package-info.java` và `src/com/example/catalog/CatalogService.java`.

Hãy xác định từng nhận định:

1. Viết `@ResponsibleTeam("catalog")` ngay trước `package com.example.catalog;` trong `package-info.java` có hợp lệ không?
2. Viết `@ResponsibleTeam(value = "catalog", priority = 2)` ở cùng vị trí có hợp lệ không?
3. Đặt `@ResponsibleTeam("catalog")` ngay trước `class CatalogService` có hợp lệ không?
4. Thay `package-info.java` bằng file `CatalogService.java` chứa package declaration có annotation có đúng quy tắc không?
5. `CatalogService.class.getAnnotation(ResponsibleTeam.class)` có đọc được annotation đặt trên package không?
6. `CatalogService.class.getPackage().getAnnotation(ResponsibleTeam.class)` có thể đọc annotation ở runtime không, khi `package-info.class` được biên dịch và đóng gói đúng?
7. Nếu đổi retention thành `SOURCE`, câu lệnh truy vấn `getAnnotation` lúc runtime có còn tìm thấy annotation không?
8. Package `com.example.catalog.internal` có tự nhận annotation từ `com.example.catalog` không?

Đáp án:

1. **Có.** `value()` là element bắt buộc và được dùng dưới dạng viết tắt.
2. **Có.** Truyền đủ hai element đúng kiểu, `priority` có thể được chỉ định tường minh.
3. **Không.** `ResponsibleTeam` chỉ cho phép `PACKAGE`, không cho phép `TYPE`.
4. **Không.** Package annotation phải đặt trong compilation unit tên `package-info.java`.
5. **Không.** Annotation gắn trên package, không gắn trực tiếp trên class.
6. **Có, nếu metadata runtime và classpath được chuẩn bị đúng.** `@Retention(RUNTIME)` cho phép reflection đọc package annotation.
7. **Không.** `SOURCE` không được giữ trong class file để phản chiếu lúc chạy.
8. **Không.** Subpackage độc lập, không kế thừa package annotation theo quy tắc Java mặc định.

## 13. Checklist trước khi dùng trong dự án

- Annotation type đã khai báo `@Target(ElementType.PACKAGE)` nếu chỉ dùng ở cấp package.
- Nếu cần reflection runtime, đã đặt `@Retention(RetentionPolicy.RUNTIME)`.
- Trong `package-info.java`, annotation nằm trước câu lệnh `package ten.package;`.
- Tên file giữ đúng `package-info.java`; đường dẫn source và tên package thống nhất theo build layout.
- Mọi element không có `default` đã được cung cấp, đúng tên, đúng kiểu và đúng quy tắc giá trị của Java annotation.
- Javadoc package được viết bằng khối `/** ... */` nếu package cần tài liệu API.
- Runtime artifact chứa metadata package phù hợp, bao gồm `package-info.class` khi cần.
- Đọc bằng `SomeClass.class.getPackage().getAnnotation(...)` khi muốn truy vấn annotation của package, có xử lý trường hợp trả `null`.
- Không mong package annotation tự truyền xuống class, method hoặc subpackage.
- Nếu annotation có ý nghĩa nghiệp vụ, đã xác định công cụ/framework nào sẽ thực sự đọc và xử lý metadata.

Hiểu đúng `PACKAGE` giúp đặt metadata **đúng cấp độ**. `package-info.java` kết nối định nghĩa annotation bằng `@interface` với package declaration, còn retention và phần mã đọc annotation quyết định metadata ấy có được sử dụng lúc chạy hay không.