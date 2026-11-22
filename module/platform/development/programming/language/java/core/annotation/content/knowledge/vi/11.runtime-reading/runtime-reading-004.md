# Đọc annotation trên Package, Module và RecordComponent khi chạy Java

Khi làm việc với reflection, nhiều lập trình viên bắt đầu từ `Class.getAnnotation(...)`, `Method.getAnnotation(...)` hoặc `Field.getAnnotation(...)`. Nhưng Java còn cho phép đặt và đọc annotation trên ba loại thành phần có phạm vi khác hẳn: **package**, **module** và **record component**.

- **Package annotation** mô tả metadata ở mức package; source thường đặt trong `package-info.java` và khi chạy đọc qua một đối tượng `java.lang.Package`.
- **Module annotation** mô tả metadata của **named module** theo JPMS (Java Platform Module System); source đặt trên khai báo `module` trong `module-info.java` và đọc qua `java.lang.Module`.
- **Record-component annotation** gắn vào các thành phần trong phần khai báo record, ví dụ `record Account(@Label String id) {}`; khi chạy đọc qua `java.lang.reflect.RecordComponent`.

Cả ba đều hỗ trợ API dựa trên **`AnnotatedElement`**, nhưng chúng đại diện cho **những thực thể khác nhau**. Lấy annotation của class không đồng nghĩa lấy annotation của package, module hoặc record component chứa class đó.

## 1. Điều kiện chung để reflection đọc được annotation

Một annotation type có thể được khai báo với các meta-annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
@Retention(RetentionPolicy.RUNTIME)
@interface PackageLabel {
    String value();
}
~~~

Hai điều kiện cần tách riêng:

1. **`@Target`** quy định **đặt ở đâu hợp lệ**. Ví dụ `PACKAGE` dành cho khai báo package, `MODULE` dành cho khai báo module, `RECORD_COMPONENT` dành cho khai báo record component.
2. **`@Retention(RUNTIME)`** quy định annotation được giữ đến runtime để các API reflection trả về. Nếu không khai báo `@Retention`, mặc định là `CLASS`; `SOURCE` hoặc `CLASS` không được đọc như runtime declaration annotations qua các lời gọi `getAnnotation(...)`.

Annotation chưa có consumer thì không tự tạo chức năng. Ví dụ `@PackageLabel("catalog")` chỉ lưu nhãn; chương trình/framework phải lấy metadata và diễn giải nhãn nếu muốn xử lý khác đi.

### API chung: AnnotatedElement

`Package`, `Module` và `RecordComponent` đều triển khai `java.lang.reflect.AnnotatedElement`. Những method thông dụng gồm:

| Method | Kết quả và mục đích |
| --- | --- |
| `getAnnotation(A.class)` | Một annotation loại `A` hiện diện trực tiếp hoặc theo quy tắc present; trả `null` nếu không có |
| `getDeclaredAnnotation(A.class)` | Annotation loại `A` khai báo trực tiếp; trả `null` nếu không có |
| `getAnnotations()` | Mảng annotation hiện diện theo hợp đồng `AnnotatedElement` |
| `getDeclaredAnnotations()` | Mảng annotation trực tiếp, không tìm trên phần tử khác |
| `isAnnotationPresent(A.class)` | Kiểm tra annotation loại `A` có present hay không |
| `getAnnotationsByType(A.class)` | Lấy mọi annotation loại `A` theo quy tắc repeatable/container |
| `getDeclaredAnnotationsByType(A.class)` | Lấy annotations loại `A` trực tiếp hoặc gián tiếp thông qua container khai báo tại chính phần tử |

Với **`Package`, `Module`, `RecordComponent`**, một annotation không tự “được kế thừa” từ class hoặc superclass liên quan. `@Inherited` có ngữ nghĩa đặc biệt chủ yếu khi truy vấn **class annotations** theo superclass; không phải cơ chế lan truyền package/module/component metadata.

Nếu cần annotation lặp (`@Repeatable`), dùng `getAnnotationsByType`/`getDeclaredAnnotationsByType` để lấy các base annotations có thể nằm trong container; `getAnnotation` đơn lẻ không tự bung toàn bộ container.

## 2. Package annotation: định nghĩa trong package-info.java

### 2.1. Nơi đặt hợp lệ

Package metadata được gắn lên **package declaration**. Với package `demo.meta`, tạo file **`package-info.java`**:

~~~java
@PackageLabel("catalog")
package demo.meta;
~~~

Đây là **đoạn source minh họa**: lớp annotation `PackageLabel` phải nằm trong phạm vi import/lookup phù hợp và phải khai báo `@Target(PACKAGE)`, `@Retention(RUNTIME)` nếu muốn đọc khi chạy. Ví dụ đầy đủ có các file tương ứng ở mục 5.

`package-info.java` là vị trí chuẩn để tập trung documentation và annotation của package. File này sẽ được biên dịch thành **`package-info.class`** khi cần chứa metadata. API của `Package` đọc runtime package annotations từ `package-info.class` tương ứng với code source của package đó.

**Không** đặt package annotation trước một `class` thông thường rồi kỳ vọng nó trở thành annotation của package. Thêm `@PackageLabel` vào một class là sai vị trí nếu target chỉ có `PACKAGE`.

### 2.2. Cách lấy Package rồi đọc metadata

~~~java
Package pkg = Account.class.getPackage();
PackageLabel tag = pkg.getAnnotation(PackageLabel.class);
if (tag != null) {
    System.out.println(tag.value());
}
~~~

Đây là **đoạn code bên trong method**, giả định các kiểu `Account` và `PackageLabel` đã tồn tại. Ý nghĩa:

- `Account.class.getPackage()` tìm runtime package gắn với lớp `Account`.
- `pkg.getAnnotation(PackageLabel.class)` đọc annotation trên **package**, không phải trên class `Account`.
- Kiểm tra `null` vì package có thể không khai báo annotation ấy; không giả định mọi class có chung package name đều có metadata mong đợi.

### 2.3. Package runtime phụ thuộc class loader/code source

`Package` đại diện cho **runtime package**, vốn liên quan đến class loader và cách định nghĩa package, thay vì chỉ là một chuỗi package name. Với cùng một package name nhưng class loader khác nhau, không nên mặc định metadata/package object hoàn toàn giống nhau.

Đối với ứng dụng thông thường, **ưu tiên `SomeClass.class.getPackage()`** khi đã biết một class thuộc package cần hỏi. Các API tĩnh cũ như `Package.getPackage(String)` có giới hạn về package đã được định nghĩa và ngữ cảnh class loader, nên không thích hợp để suy ra rằng có thể truy vấn mọi package chỉ từ tên.

Nếu quên compile/đóng gói `package-info.class`, runtime có thể không thấy annotation dù file `package-info.java` tồn tại trong source. Khi chẩn đoán, kiểm tra sản phẩm build chứ không chỉ source.

## 3. Module annotation: đặt ở module-info.java

### 3.1. Module không phải Package

Java 9 giới thiệu JPMS và `java.lang.Module`. Một **named module** được khai báo trong `module-info.java`:

~~~java
@demo.meta.ModuleInfoTag("inventory")
module demo.meta {
}
~~~

Annotation phải có `@Target(ElementType.MODULE)` và retention phù hợp nếu cần đọc runtime. Khi module được biên dịch, metadata này nằm trong **`module-info.class`** của module.

Module declaration khác package declaration: `module demo.meta` và `package demo.meta` là hai khái niệm độc lập dù tình cờ trùng văn bản tên. `module-info.java` không phải nơi đặt package annotation; `package-info.java` không phải nơi đặt module annotation.

Một module chứa nhiều package; một package thuộc một module trong runtime đã được cấu hình (với các ràng buộc JPMS về package ownership). Annotation trên module **không tự lan tới tất cả Package objects** bên trong.

### 3.2. Đọc Module của một class

~~~java
Module module = Account.class.getModule();
System.out.println(module.isNamed());
ModuleInfoTag marker = module.getAnnotation(ModuleInfoTag.class);
if (marker != null) {
    System.out.println(marker.value());
}
~~~

Đây là đoạn minh họa, giả định `Account` thuộc module khai báo `ModuleInfoTag`.

- `Class.getModule()` trả đối tượng `Module` mà class thuộc về.
- `module.isNamed()` phân biệt **named module** với **unnamed module**.
- `module.getAnnotation(ModuleInfoTag.class)` tìm metadata trên module declaration.

Nếu chạy các class trên **classpath** thông thường, chúng nằm trong **unnamed module**. Đối tượng `Module` vẫn tồn tại và `isNamed()` trả `false`, nhưng không có `module-info.class` của một named module để chứa annotation. Theo API, `Module.getAnnotation(...)` trên unnamed module trả `null`; `getAnnotations()` trả mảng rỗng.

Muốn kiểm thử module annotation thực sự, cần compile/run bằng **module path** và có `module-info.java`. Chỉ đặt thêm một file tên `module-info.java` vào một dự án đang chạy trên classpath là chưa đủ để đảm bảo code thực thi dưới named-module mode.

### 3.3. Module descriptor không phải annotation query

`module.getDescriptor()` trả `java.lang.module.ModuleDescriptor` chứa thông tin JPMS như `requires`, `exports`, `opens`, `uses` và `provides`. Muốn đọc annotation trên khai báo module, dùng `module.getAnnotation(...)` theo API `AnnotatedElement`. Đây là hai loại metadata khác nhau.

Thực tế, việc class ở module có tên **không có nghĩa package đó đã được exported/opened cho module khác**. Khi viết framework quét module bên ngoài, vẫn phải quan tâm module readability và access rules; ví dụ ở mục 5 đọc từ code trong cùng module nên không cần cấu hình `exports` hoặc `opens` đặc biệt.

## 4. RecordComponent: đọc metadata ở phần khai báo record

Record là một dạng class được chuẩn hóa từ Java 16. Ví dụ:

~~~java
record Account(@ComponentInfoTag("record-only") String id, int age) {}
~~~

Mỗi cặp tên/kiểu trong header, như `String id` hoặc `int age`, là một **record component**. Đó không phải đối tượng `Field` và cũng không phải `Method`, dù Java tạo ra field, accessor và các thành phần constructor liên quan.

### 4.1. Lấy RecordComponent bằng reflection

~~~java
if (Account.class.isRecord()) {
    for (java.lang.reflect.RecordComponent component
            : Account.class.getRecordComponents()) {
        System.out.println(component.getName());
    }
}
~~~

Đây là đoạn code trong method. `Class.isRecord()` giúp kiểm tra trước. `getRecordComponents()` trả mảng các `RecordComponent` theo **thứ tự khai báo** nếu class là record; với class không phải record, API trả **`null`**, do đó không lặp trực tiếp khi chưa kiểm tra.

`RecordComponent` cung cấp:

| Method | Công dụng |
| --- | --- |
| `getName()` | Tên component, ví dụ `id` |
| `getType()` | Kiểu raw bằng `Class<?>` |
| `getGenericType()` | Kiểu tổng quát khi component có generic type |
| `getAccessor()` | `Method` đại diện cho accessor như `id()` |
| `getDeclaringRecord()` | Record class khai báo component |
| `getAnnotation(...)` / `getAnnotationsByType(...)` | Declaration annotations trên chính record component |
| `getAnnotatedType()` | Annotation trên **type use** của kiểu component (nếu có) |

Điểm quan trọng: **annotation declaration của record component** và **annotation trên kiểu được sử dụng để khai báo component** là hai vị trí thông tin khác nhau.

### 4.2. @Target(RECORD_COMPONENT) giữ annotation ở đúng RecordComponent

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.RECORD_COMPONENT)
@Retention(RetentionPolicy.RUNTIME)
@interface ComponentInfoTag {
    String value();
}

record Account(@ComponentInfoTag("record-only") String id) {}
~~~

Với target chỉ `RECORD_COMPONENT`, metadata áp dụng cho phần tử component và đọc qua:

~~~java
var component = Account.class.getRecordComponents()[0];
var info = component.getAnnotation(ComponentInfoTag.class);
System.out.println(info.value());  // record-only
~~~

Đây là **đoạn minh họa** (cần đặt vào một method) và không phải ví dụ ứng dụng hoàn chỉnh. Không dùng `Account.class.getAnnotation(ComponentInfoTag.class)` để tìm annotation của component: class và component là hai `AnnotatedElement` khác nhau.

### 4.3. Propagation: một annotation có thể xuất hiện ở nhiều nơi

JLS còn cho phép annotation viết ở record component được **lan truyền** sang các khai báo được sinh tương ứng nếu annotation type cho phép target đó. Ví dụ:

~~~java
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@Retention(RetentionPolicy.RUNTIME)
@interface CrossCheck {
    String value();
}

record Account(@CrossCheck("copied") String id, int age) {}
~~~

Trong record với **accessor và canonical constructor ngầm định**, annotation có thể xuất hiện ở:

1. `RecordComponent id` nhờ `RECORD_COMPONENT`.
2. Field `id` do record tạo ra nhờ `FIELD`.
3. Accessor method `id()` được sinh ngầm nhờ `METHOD`.
4. Formal parameter `id` của canonical constructor được suy diễn nhờ `PARAMETER`.

Đừng suy rằng Java tự tạo bốn bản sao của **mọi** annotation. Target nào hợp lệ thì chỉ những declaration tương ứng mới nhận annotation; retention còn quyết định chúng có thể được đọc lúc chạy không. Khi accessor hoặc canonical constructor được **khai báo tường minh**, các quy tắc propagation có khác biệt: không mặc định annotation trên component tự gắn lên accessor khai báo tường minh hoặc các formal parameters viết tường minh. Hãy kiểm tra JLS và chính source thay vì giả định luôn lan truyền.

Một annotation chỉ có `@Target(RECORD_COMPONENT)` **không tự hiện trên field, accessor, parameter**. Đây là trường hợp đối chứng rất hữu ích khi debug framework đọc nhầm `Field` thay vì `RecordComponent`.

### 4.4. TYPE_USE khác RECORD_COMPONENT

Giả sử định nghĩa:

~~~java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface NonNullLike {}

record Customer(@NonNullLike String name) {}
~~~

`@NonNullLike` là **type annotation** gắn với kiểu `String` được sử dụng. Để đọc type-use annotations, đi qua `RecordComponent.getAnnotatedType().getAnnotations()` hoặc `getAnnotation(NonNullLike.class)` trên `AnnotatedType` đó.

`RecordComponent.getAnnotations()` trả **declaration annotations** của component. Một annotation chỉ nhắm `TYPE_USE` không nên được tìm bằng cách giả định nó cũng có mặt như declaration annotation trên `RecordComponent`. Nếu thiết kế annotation có cả `RECORD_COMPONENT` và `TYPE_USE`, metadata có thể được lưu ở các khu vực riêng tùy từng vai trò.

Tên `NonNullLike` chỉ nói lên ý định; annotation tùy biến không tự khiến Java compiler kiểm tra non-null. Muốn validate, cần một checker/processor hoặc runtime consumer.

## 5. Ví dụ Java 17 chạy được: package, module và record trong cùng chương trình

Ta tạo một named module **`demo.meta`** gồm các annotation type và một record. Mọi source nằm trong module này, vì vậy `module-info.java` và `package-info.java` đều thật sự được biên dịch. Thư mục:

~~~text
src/
└── demo.meta/
    ├── module-info.java
    └── demo/
        └── meta/
            ├── ModuleInfoTag.java
            ├── PackageInfoTag.java
            ├── ComponentInfoTag.java
            ├── CrossCheck.java
            ├── package-info.java
            ├── Account.java
            └── Main.java
~~~

### File 1: src/demo.meta/module-info.java

~~~java
@demo.meta.ModuleInfoTag("inventory")
module demo.meta {
}
~~~

Ta dùng tên đầy đủ của annotation type vì `module-info.java` đang đánh dấu module declaration. Không cần `exports` vì ví dụ chạy `Main` bên trong chính module.

### File 2: src/demo.meta/demo/meta/ModuleInfoTag.java

~~~java
package demo.meta;

import java.lang.annotation.*;

@Target(ElementType.MODULE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ModuleInfoTag {
    String value();
}
~~~

### File 3: src/demo.meta/demo/meta/PackageInfoTag.java

~~~java
package demo.meta;

import java.lang.annotation.*;

@Target(ElementType.PACKAGE)
@Retention(RetentionPolicy.RUNTIME)
public @interface PackageInfoTag {
    String value();
}
~~~

### File 4: src/demo.meta/demo/meta/ComponentInfoTag.java

~~~java
package demo.meta;

import java.lang.annotation.*;

@Target(ElementType.RECORD_COMPONENT)
@Retention(RetentionPolicy.RUNTIME)
public @interface ComponentInfoTag {
    String value();
}
~~~

### File 5: src/demo.meta/demo/meta/CrossCheck.java

~~~java
package demo.meta;

import java.lang.annotation.*;

@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@Retention(RetentionPolicy.RUNTIME)
public @interface CrossCheck {
    String value();
}
~~~

### File 6: src/demo.meta/demo/meta/package-info.java

~~~java
@PackageInfoTag("catalog")
package demo.meta;
~~~

Annotation `@PackageInfoTag` ở đây gắn vào **package declaration**, không phải class nằm trong package.

### File 7: src/demo.meta/demo/meta/Account.java

~~~java
package demo.meta;

public record Account(
        @ComponentInfoTag("record-only")
        @CrossCheck("copied") String id,
        int age) {
}
~~~

`ComponentInfoTag` chỉ nhắm `RECORD_COMPONENT`; `CrossCheck` cho phép cả bốn vị trí component/field/method/parameter. Record ở đây có accessor và canonical constructor do compiler tạo.

### File 8: src/demo.meta/demo/meta/Main.java

~~~java
package demo.meta;

import java.lang.reflect.RecordComponent;

public class Main {
    public static void main(String[] args) throws Exception {
        Package pkg = Account.class.getPackage();
        Module module = Account.class.getModule();
        RecordComponent[] components = Account.class.getRecordComponents();
        RecordComponent id = components[0];

        var field = Account.class.getDeclaredField("id");
        var accessor = id.getAccessor();
        var ctorParam = Account.class
                .getDeclaredConstructor(String.class, int.class)
                .getParameters()[0];

        System.out.println("package=" +
                pkg.getAnnotation(PackageInfoTag.class).value());
        System.out.println("moduleNamed=" + module.isNamed());
        System.out.println("module=" +
                module.getAnnotation(ModuleInfoTag.class).value());
        System.out.println("record=" + Account.class.isRecord());
        System.out.println("components=" + components.length);
        System.out.println("component=" + id.getName() + ":" +
                id.getAnnotation(ComponentInfoTag.class).value());
        System.out.println("recordOnlyOnField=" +
                (field.getAnnotation(ComponentInfoTag.class) != null));
        System.out.println("crossField=" +
                (field.getAnnotation(CrossCheck.class) != null));
        System.out.println("crossAccessor=" +
                (accessor.getAnnotation(CrossCheck.class) != null));
        System.out.println("crossParameter=" +
                (ctorParam.getAnnotation(CrossCheck.class) != null));
    }
}
~~~

### Biên dịch và chạy

Tại thư mục **chứa `src`**, dùng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -d out --module-source-path src -m demo.meta
java --module-path out -m demo.meta/demo.meta.Main
~~~

**Stdout chính xác (đã kiểm chứng bằng JDK 21 với `--release 17`):**

~~~text
package=catalog
moduleNamed=true
module=inventory
record=true
components=2
component=id:record-only
recordOnlyOnField=false
crossField=true
crossAccessor=true
crossParameter=true
~~~

Các kết quả xác nhận:

- `package=catalog`: giá trị đọc qua `Account.class.getPackage().getAnnotation(PackageInfoTag.class)`, đến từ `package-info.class`.
- `moduleNamed=true` và `module=inventory`: code chạy trên **module path** nên `Account.class.getModule()` là named module `demo.meta`; metadata đến từ `module-info.class`.
- `record=true`: `Account` thực sự là record.
- `components=2`: các component khai báo là `id` và `age`; thứ tự phản ánh record header.
- `component=id:record-only`: `ComponentInfoTag` được lấy qua `RecordComponent`.
- `recordOnlyOnField=false`: target chỉ `RECORD_COMPONENT` nên không có declaration annotation đó trên field `id`.
- Ba kết quả `crossField=true`, `crossAccessor=true`, `crossParameter=true`: `CrossCheck` được propagation sang các declaration tương ứng do compiler tạo vì target của nó cho phép.

Nếu muốn tự thử các trường hợp lỗi, có thể bỏ `@Retention(RUNTIME)` khỏi **một** annotation type và quan sát việc reflection không đọc được annotation đó sau khi biên dịch lại. Tuy nhiên, các dòng trong `Main` hiện tại gọi trực tiếp `.value()` mà không kiểm tra `null` để ví dụ ngắn gọn; khi thử đổi retention, hãy thêm kiểm tra `null` trước khi gọi `value()`.

## 6. Những lỗi thường gặp khi đọc ba loại annotation này

### Lỗi 1: Tìm metadata của package bằng Class.getAnnotation

~~~java
// Đoạn minh họa; không phải một file độc lập.
var label = Account.class.getAnnotation(PackageInfoTag.class);
~~~

`PackageInfoTag` có `@Target(PACKAGE)`, nên lệnh trên sẽ không thấy annotation của `package-info.java`. Cách đúng:

~~~java
var label = Account.class.getPackage()
        .getAnnotation(PackageInfoTag.class);
~~~

### Lỗi 2: Quên package-info.java trong bản build

Có annotation trong source nhưng `package-info.class` không được build/copy vào output có thể dẫn đến runtime không thấy metadata. Kiểm tra output thư mục/module/JAR và bảo đảm package-info được biên dịch cùng các class có liên quan.

### Lỗi 3: Tìm module annotation khi đang chạy classpath

Nếu chạy bằng classpath, `Class.getModule()` thường trả **unnamed module**. Dù bạn đặt module annotation trong code ở nơi khác, lời gọi trên unnamed module không thể đọc metadata của một named module không tham gia cách chạy đó. Kiểm tra `isNamed()` và cách dùng `--module-path`, `-m`.

### Lỗi 4: Nhầm ModuleDescriptor với Module AnnotatedElement

`ModuleDescriptor` phản ánh khai báo phụ thuộc/export/open/service của JPMS; muốn lấy module annotations, dùng `java.lang.Module.getAnnotation(...)`.

### Lỗi 5: Nhầm record component với field hoặc accessor

Một record có field `id`, method `id()` và component `id`, nhưng ba thực thể được phản chiếu bằng các object khác nhau. Với `@Target(RECORD_COMPONENT)`, phải đọc qua `getRecordComponents()`. Nếu framework chỉ quét fields, metadata chỉ ở component sẽ bị bỏ sót.

### Lỗi 6: Không phân biệt declaration annotation và type-use annotation

`RecordComponent.getAnnotation(...)` đọc declaration metadata trên component; `getAnnotatedType()` dùng khi metadata thuộc về kiểu được khai báo. Một annotation trên `List<@NonNullLike String>` thậm chí có thể nằm trên type argument: khi đó phải duyệt `AnnotatedParameterizedType` để tìm vị trí annotation phù hợp.

### Lỗi 7: Tưởng @Inherited có tác dụng chung

`@Inherited` không làm package annotation đi vào các class bên trong, cũng không làm module annotation đi vào package, hoặc component annotation đi vào record class. Nếu thấy annotation trên field/accessor được sinh từ component, đó là **quy tắc propagation của record và target compatibility**, không phải `@Inherited`.

### Lỗi 8: Dùng reflection thiếu kiểm tra null và phạm vi truy cập

`getAnnotation(...)` trả `null` khi không có annotation; `getRecordComponents()` trả `null` nếu đối tượng `Class` không phải record. Code framework nên kiểm tra trước. Reflection trên thành phần không public có thể cần quy tắc truy cập module riêng khi muốn đọc/ghi giá trị hay gọi method; đừng nhầm khả năng đọc metadata với quyền invoke/access mọi thành phần.

## 7. Cách thiết kế API metadata có thể bảo trì

1. **Chọn đúng cấp độ sở hữu thông tin.** Chính sách cho toàn package → package annotation; khả năng/metadata toàn module → module annotation; metadata theo từng trường của record → record component annotation.
2. **Giới hạn @Target hợp lý.** Đặt `PACKAGE`, `MODULE`, `RECORD_COMPONENT` khi chỉ muốn một nơi; chỉ thêm `FIELD/METHOD/PARAMETER/TYPE_USE` khi có chủ ý cho các consumers ở vị trí đó.
3. **Chọn retention theo consumer.** Công cụ compile-time có thể dùng annotation SOURCE/CLASS; runtime reflection đòi hỏi RUNTIME. Không lạm dụng reflection nếu không cần.
4. **Định nghĩa quy ước package/module build.** Với package, compile và đóng gói `package-info.class`. Với module, compile và chạy đúng named-module mode để `module-info.class` có hiệu lực.
5. **Kiểm thử bằng nguồn thật.** Có thể viết một test tạo package-info/module-info/record, compile với `javac --release 17`, sau đó kiểm tra qua `Package`/`Module`/`RecordComponent` thay vì chỉ test mỗi `Class`.
6. **Xác định ý nghĩa nghiệp vụ riêng.** Annotation chứa metadata; framework phải quy định khi nào quét, xử lý thiếu annotation, precedence khi có nhiều giá trị và tác động của cấu hình runtime.

### Tình huống quyết định nhanh

| Yêu cầu | Vị trí annotation | Cách đọc ở runtime |
| --- | --- | --- |
| Phân loại toàn bộ package của các API | `package-info.java`, `@Target(PACKAGE)` | `AnyClassInPackage.class.getPackage().getAnnotation(...)` |
| Gắn nhãn cấp module JPMS | `module-info.java`, `@Target(MODULE)` | `SomeClass.class.getModule().getAnnotation(...)` |
| Metadata riêng của record component `id` | Record header, `@Target(RECORD_COMPONENT)` | Duyệt `RecordComponent[]`, `component.getAnnotation(...)` |
| Constraint gắn trên type argument | `@Target(TYPE_USE)` | `AnnotatedType` và các subtype tương ứng |
| Muốn annotation từ component xuất hiện thêm ở field/accessor/parameter được sinh | Thêm target `FIELD/METHOD/PARAMETER` | Đọc đúng `Field`/`Method`/`Parameter` tương ứng và kiểm tra propagation |

## 8. Tự kiểm tra kiến thức

**1. Vì sao `Account.class.getAnnotation(PackageInfoTag.class)` trả null dù package của Account có annotation?** Vì `Class` và `Package` là hai `AnnotatedElement` khác nhau. Đọc `Account.class.getPackage().getAnnotation(...)`.

**2. Có thể lấy module annotation khi chạy trên unnamed module không?** `Module` vẫn tồn tại, nhưng unnamed module không mang annotation khai báo trong `module-info.class` của một named module. Với `Module.getAnnotation`, kết quả là `null` trên unnamed module.

**3. `Account.class.getRecordComponents()` cho kết quả gì nếu Account là class thông thường, không phải record?** `null`. Nếu là record, trả mảng theo thứ tự khai báo component.

**4. Annotation chỉ có `@Target(RECORD_COMPONENT)` có tự xuất hiện trong `getDeclaredField("id")` không?** Không. Target này chỉ cho phép declaration annotation trên component.

**5. Tại sao `@CrossCheck` được đọc trên accessor và canonical constructor parameter trong ví dụ?** Vì annotation có thêm các targets `METHOD` và `PARAMETER` và ví dụ dùng các thành phần do compiler sinh ngầm. Không được suy kết quả đó cho mọi accessor/constructor khai báo tường minh.

**6. `@Retention(RUNTIME)` có tự đưa annotation từ package vào class hoặc từ record component vào record class không?** Không. Retention chỉ quyết định thời điểm dữ liệu còn hiện diện; vị trí sở hữu và propagation được điều khiển bởi các quy tắc riêng.

**7. Một annotation chỉ có `@Target(TYPE_USE)` trên kiểu `String` của component nên đọc qua đâu?** Từ `RecordComponent.getAnnotatedType()`, không coi đó là declaration annotation trên component.

## 9. Tài liệu chuẩn

- Java SE 21 API — **Package**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html
- Java SE 21 API — **Module**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 API — **RecordComponent**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html
- Java SE 21 API — **AnnotatedElement**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- Java Language Specification — **Record classes `8.10** và **annotation placement `9.7.4**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html và https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.4
- Java Language Specification — **Package and module declarations, Chapter 7**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html

Khi viết công cụ đọc annotation, hãy bắt đầu bằng câu hỏi **“metadata này được khai báo trên thực thể nào?”**. Nếu là package, module hay record component, hãy lấy đúng đối tượng `Package`, `Module` hoặc `RecordComponent` rồi truy vấn qua `AnnotatedElement`; lựa chọn đúng đối tượng quan trọng không kém `@Target`, `@Retention` và cách chương trình được biên dịch/khởi chạy.