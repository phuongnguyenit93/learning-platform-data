# @Target(ElementType.MODULE): dùng annotation trên `module-info.java` trong Java

## 1. Annotation có đích MODULE nghĩa là gì?

Từ Java 9, **Java Platform Module System (JPMS)** cho phép một ứng dụng được tổ chức thành các **named module**. Mỗi module được khai báo trong tệp `module-info.java`, có tên riêng và có thể mô tả các quan hệ như `requires`, `exports`, `opens`, `uses` và `provides`.

Với một annotation type được khai báo bằng:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.MODULE)
@interface ModuleMarker {
}
```

`ElementType.MODULE` cho phép gắn annotation đó vào **khai báo module**, tức khai báo bắt đầu bằng từ khóa `module` hoặc `open module` trong `module-info.java`. Annotation mô tả metadata của **toàn module**, chứ không gắn riêng cho class, method, package hoặc một chỉ thị `requires`/`exports`.

Ví dụ về vị trí hợp lệ (minh họa cú pháp, chưa phải chương trình hoàn chỉnh):

```java
@com.example.metadata.ModuleMarker
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Ở đây `@ModuleMarker` đứng ngay **trước khai báo `module`**. Cách viết tên đầy đủ `@com.example.metadata.ModuleMarker` giúp thấy rõ annotation type đến từ package nào. Nếu annotation type được truy cập hợp lệ, `module-info.java` cũng có thể dùng `import` rồi viết simple name.

Cần phân biệt ba cấp độ:

| Khái niệm | Đối tượng được mô tả | Tệp hoặc cú pháp điển hình |
| --- | --- | --- |
| **Module** (JPMS) | Một named module, tập hợp package và quan hệ module | `module-info.java`; `ElementType.MODULE` |
| **Package** | Không gian tên chứa các kiểu Java | `package-info.java`; `ElementType.PACKAGE` |
| **Type** | Class, interface, enum, annotation type, record | `class`, `interface`, ...; `ElementType.TYPE` |

Một module có thể chứa nhiều package; package và module không phải hai tên gọi cho cùng một thứ. “Gradle module” hoặc “Maven module” cũng không mặc nhiên đồng nghĩa với **JPMS named module**: phải xét dự án có mô tả JPMS `module-info.java` hay không.

## 2. `module-info.java` và chỗ đặt annotation

Ví dụ một module descriptor thông thường:

```java
module com.example.catalog {
    requires java.sql;
    exports com.example.catalog.api;
    opens com.example.catalog.model;
}
```

Nội dung descriptor mô tả mối quan hệ của module với module khác. Muốn gắn annotation đích `MODULE`, đặt nó **trước toàn bộ khai báo module**:

```java
@com.example.metadata.BuildOwner(team = "catalog")
module com.example.catalog {
    requires java.sql;
    exports com.example.catalog.api;
    opens com.example.catalog.model;
}
```

Trong đoạn minh họa này, `BuildOwner` phải là một annotation type truy cập được và có `@Target(ElementType.MODULE)` (hoặc target bao gồm `MODULE`).

Các điểm cần nhớ về cú pháp:

1. `module-info.java` là tệp khai báo module. Nó **không khai báo `package ...;`** như tệp class thông thường. Khai báo module chứa các chỉ thị JPMS, không chứa class hay phương thức `main`.
2. Annotation đứng trước `module` hoặc `open module`, sau phần import nếu có. Một ví dụ dùng tên đầy đủ thường dễ đọc và tránh phụ thuộc vào `import` trong bài học.
3. Nếu annotation có element bắt buộc, phải điền đủ tại vị trí gắn, chẳng hạn `@BuildOwner(team = "catalog")`.
4. Annotation chỉ đánh dấu **module declaration**. Nó không dùng để đánh dấu riêng dòng `requires java.sql;`, `exports ...;`, `opens ...;`, `uses ...;` hoặc `provides ...;`.
5. `module-info.java` được `javac` biên dịch thành `module-info.class`, dùng để biểu diễn module descriptor và thông tin annotation được giữ lại theo retention.
6. `@Target(ElementType.MODULE)` chỉ xác định **nơi được phép gắn** annotation; nó không tự làm phát sinh `requires`, `exports`, `opens` hoặc các quy tắc module khác.

Một annotation type cũng có thể cho phép nhiều đích:

```java
@Target({ElementType.MODULE, ElementType.TYPE})
@interface Reviewed {
}
```

Khi đó `@Reviewed` có thể đặt trên khai báo module và trên khai báo type. Nếu chỉ có `@Target(ElementType.MODULE)`, cố gắn nó vào `class`, `method` hoặc `package` sẽ bị compiler từ chối.

## 3. Ví dụ Java 17+ hoàn chỉnh: khai báo và đọc annotation trên module

Chúng ta sẽ tạo một named module tên `com.example.catalog`. Annotation `@ModuleOwner` đánh dấu thông tin người sở hữu module, được lưu đến runtime. Chương trình đọc metadata qua đối tượng `java.lang.Module`.

### 3.1. Cấu trúc thư mục

Tạo đúng cây tệp sau (dấu chấm trong `com.example.catalog` ở cấp module là một phần **tên thư mục module** khi dùng `--module-source-path`):

```text
src/
└── com.example.catalog/
    ├── module-info.java
    └── com/
        └── example/
            └── catalog/
                ├── meta/
                │   └── ModuleOwner.java
                └── app/
                    └── Main.java
```

Trong ví dụ này có **một module** với hai package: `com.example.catalog.meta` và `com.example.catalog.app`. Đây là source layout phù hợp với lệnh biên dịch nhiều module `--module-source-path src`.

### 3.2. `src/com.example.catalog/com/example/catalog/meta/ModuleOwner.java`

```java
package com.example.catalog.meta;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.MODULE)
public @interface ModuleOwner {
    String team();
    int revision() default 1;
}
```

Đây là một annotation type top-level `public`; do đó tệp phải là `ModuleOwner.java`. `team()` là phần tử bắt buộc còn `revision()` là phần tử tùy chọn có mặc định `1`.

- `@Target(ElementType.MODULE)` yêu cầu annotation chỉ áp dụng được cho khai báo module.
- `@Retention(RetentionPolicy.RUNTIME)` giữ metadata để có thể đọc từ `Module` bằng reflection lúc chạy.
- `public` quyết định quyền truy cập tên annotation type theo các quy tắc Java; nếu module khác cần sử dụng type này, còn phải cân nhắc `requires` và `exports`.

### 3.3. `src/com.example.catalog/module-info.java`

```java
@com.example.catalog.meta.ModuleOwner(team = "platform")
module com.example.catalog {
    exports com.example.catalog.meta;
}
```

Đây chính là chỗ dùng `ElementType.MODULE`. `@ModuleOwner(team = "platform")` đánh dấu **module `com.example.catalog`**, không phải class `Main` hay package `meta`.

Ta cố ý không truyền `revision`, nên giá trị quan sát được sau này là default `1`. Chỉ thị `exports com.example.catalog.meta;` cho phép module khác đọc được các **public type** trong package này nếu có quan hệ đọc module phù hợp; trong ví dụ, `Main` thuộc cùng module nên không cần `exports` để import `ModuleOwner`.

### 3.4. `src/com.example.catalog/com/example/catalog/app/Main.java`

```java
package com.example.catalog.app;

import com.example.catalog.meta.ModuleOwner;

public class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();
        ModuleOwner annotation = module.getAnnotation(ModuleOwner.class);

        System.out.println(module.getName());
        System.out.println(module.isNamed());
        System.out.println(annotation.team());
        System.out.println(annotation.revision());
    }
}
```

`Main.class.getModule()` trả về `java.lang.Module` của class `Main`. Đối tượng `Module` triển khai `AnnotatedElement`, vì vậy có phương thức `getAnnotation(Class<T>)` để lấy annotation hiện diện trên module. Trong ví dụ, annotation chắc chắn hiện diện và retention là `RUNTIME`, nên `annotation` không bị `null`.

### 3.5. Biên dịch và chạy

Đứng ở thư mục chứa `src`, với JDK 17 trở lên:

```bash
javac --release 17 -d out --module-source-path src -m com.example.catalog
java --module-path out --module com.example.catalog/com.example.catalog.app.Main
```

**Stdout chính xác:**

```text
com.example.catalog
true
platform
1
```

Giải thích:

1. `javac --module-source-path src -m com.example.catalog` tìm nguồn của named module và tạo class files cùng `module-info.class` trong thư mục output.
2. `java --module-path out --module com.example.catalog/com.example.catalog.app.Main` khởi chạy `Main` trong **named module**, do đó `module.getName()` là `com.example.catalog`, còn `isNamed()` là `true`.
3. `module.getAnnotation(ModuleOwner.class)` tìm annotation được gắn trên module declaration.
4. `team()` trả về `"platform"` vì đã chỉ định tường minh. `revision()` trả về `1` vì dùng giá trị mặc định.

Đoạn này đã được đối chiếu bằng cách biên dịch với `--release 17` và chạy trên JDK hỗ trợ Java 17; stdout ở trên tương ứng chính xác với chương trình.

## 4. Vai trò của `@Retention` đối với MODULE

`@Target(ElementType.MODULE)` trả lời “annotation được **đặt ở đâu**?”. `@Retention` trả lời “annotation được **lưu giữ đến khi nào**?”. Hai khía cạnh phải được quyết định riêng.

| Retention | Đặc điểm | Đọc bằng `Module.getAnnotation(...)`? |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Chỉ có ở nguồn; compiler có thể xử lý rồi bỏ khỏi class file | Không |
| `RetentionPolicy.CLASS` | Lưu trong class file, nhưng không được giữ để Java reflection đọc ở runtime | Không |
| `RetentionPolicy.RUNTIME` | Metadata được giữ để reflection quan sát ở runtime | Có, nếu annotation thực sự hiện diện trên module và kiểu được truy cập phù hợp |

Nếu không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`. Do đó, gắn `@ModuleOwner` vào `module-info.java` mà quên `RUNTIME` vẫn có thể biên dịch, nhưng phương thức `getAnnotation(ModuleOwner.class)` trong ví dụ runtime sẽ không tìm được annotation đó.

Khi sử dụng reflection cần kiểm tra `null`, vì `getAnnotation(...)` trả `null` nếu annotation không hiện diện hoặc không sẵn có ở runtime:

```java
ModuleOwner owner = module.getAnnotation(ModuleOwner.class);
if (owner != null) {
    System.out.println(owner.team());
}
```

Đoạn này là minh họa độc lập về cách xử lý kết quả; nó giả sử biến `module` đã được khai báo và `ModuleOwner` nằm trong phạm vi sử dụng.

Lưu ý: dùng `@Target(MODULE)` **không bắt buộc** phải dùng `RUNTIME`. Chọn retention dựa trên nhu cầu: kiểm tra ở nguồn, phân tích class file hay đọc qua reflection lúc chạy. Với bài tập trên, `RUNTIME` là điều kiện cần để in `team()` qua `Module.getAnnotation`.

## 5. Metadata MODULE có thể mô tả gì, và không làm gì?

Ví dụ các element phù hợp với annotation đánh dấu một module:

```java
@Target(ElementType.MODULE)
@Retention(RetentionPolicy.RUNTIME)
@interface ModuleMetadata {
    String owner();
    String[] tags() default {};
    boolean experimental() default false;
}
```

Vị trí sử dụng có thể là:

```java
@com.example.meta.ModuleMetadata(
    owner = "infra",
    tags = {"observability", "core"},
    experimental = true
)
module com.example.metrics {
}
```

Đây là **ví dụ cú pháp**: muốn biên dịch thực tế, phải có `ModuleMetadata` với tên đầy đủ đúng, package truy cập được và cấu hình module thích hợp. Metadata có thể phục vụ tạo báo cáo, audit nội bộ, công cụ build hoặc hiển thị thông tin khi chạy. Nhưng Java **không tự thi hành chính sách** dựa trên `owner`, `tags` hoặc `experimental`.

Cụ thể:

- `@ModuleMetadata(owner = "infra")` **không tự thay đổi quyền truy cập module**.
- `@ModuleMetadata(experimental = true)` **không tự bật hay tắt module**.
- Annotation **không thay thế** `requires`, `exports`, `opens`, `uses` hoặc `provides`.
- Khi viết công cụ tiêu thụ annotation, bạn vẫn phải định nghĩa cách diễn giải element, kiểm tra giá trị và hành vi phát sinh.
- Chú giải trên một module cũng **không tự lan truyền** sang các package, class hoặc những module được khai báo trong `requires`.

Với metadata nhạy cảm như khóa truy cập, mật khẩu, token, không nên ghi chúng thành annotation values bởi thông tin có thể lưu trong class file và được công cụ phân tích hoặc reflection truy xuất.

## 6. Named, automatic và unnamed module

Tại runtime, `Class.getModule()` trả về một đối tượng `Module`, nhưng không phải mọi `Module` đều đến từ một tệp `module-info.java` được tác giả khai báo.

**Explicit named module:** Có descriptor `module-info.java` (hoặc descriptor tương ứng trong class file), được nhận diện bằng tên module. Đây là trường hợp bạn trực tiếp gắn annotation `@Target(MODULE)` vào module declaration. Ví dụ `com.example.catalog` ở trên.

**Automatic module:** Một JAR không có explicit module descriptor có thể trở thành automatic module khi đặt lên module path theo quy tắc JPMS. Nó có tên module nhưng **không có khai báo `module-info.java` do bạn viết để gắn module annotation trực tiếp theo ví dụ**.

**Unnamed module:** Mã chạy từ classpath thông thường thường nằm trong unnamed module. `Main.class.getModule().isNamed()` có thể là `false`, `getName()` là `null`. Không có module declaration trong `module-info.java` để bạn gắn một annotation `MODULE` cho nhóm classpath đó.

Vì thế, để học rõ `ElementType.MODULE`, nên biên dịch và chạy thử trên **module path** với một explicit named module. Nếu chỉ chạy class từ classpath, cần phân biệt kết quả vì bạn đã thay đổi môi trường module của chương trình.

## 7. Quyền truy cập kiểu annotation và JPMS

Annotation `@ModuleOwner` là một Java type thật sự, nên ngoài `@Target(MODULE)`, nó còn chịu quy tắc truy cập và phụ thuộc module.

- **Trong cùng named module:** các package khác nhau thuộc cùng module có thể truy cập một annotation type `public` nếu kiểu và các thành phần tham chiếu phù hợp. Không cần xuất package chỉ để code trong cùng module dùng nhau.
- **Giữa các named module:** việc import một `public` annotation type thông thường đòi hỏi module sử dụng đọc được module cung cấp (`requires` phù hợp) và package API được `exports` theo đúng phạm vi. Tên `public` một mình không vượt qua ranh giới module.
- **Runtime reflection:** annotation muốn được nhìn thấy bằng API reflection phải có `RUNTIME`; ngoài ra bộ đọc vẫn phải có khả năng truy cập/resolve kiểu annotation. Quy tắc truy cập phản chiếu sâu và `opens` là vấn đề khác với việc gắn annotation lên module declaration.
- Nếu một module muốn dùng annotation type từ **module thư viện khác**, phải khai báo dependency tương ứng trong descriptor; trình biên dịch cần nhìn thấy annotation type khi xử lý module declaration.

Các tên package trong cùng một source tree không tự xác lập ranh giới module: ranh giới xuất hiện từ descriptor, cách biên dịch và cách tải module của chương trình.

## 8. Lỗi thường gặp

### Lỗi 1: Gắn annotation MODULE vào class

Đoạn sau cố ý **không hợp lệ** khi `ModuleOwner` chỉ cho phép `ElementType.MODULE`:

```java
@ModuleOwner(team = "platform")
class CatalogService {}
```

Compiler báo annotation type không áp dụng được cho loại khai báo này. Nếu bạn muốn hỗ trợ cả module và type, thiết kế `@Target({ElementType.MODULE, ElementType.TYPE})`. Nếu metadata chỉ mô tả module, giữ nguyên `MODULE` và chuyển annotation vào `module-info.java`.

### Lỗi 2: Gắn annotation trực tiếp vào `exports` hoặc `requires`

Không có vị trí gắn annotation trên từng module directive theo cú pháp của bài này:

```java
module com.example.catalog {
    @ModuleOwner(team = "platform")
    exports com.example.catalog.meta;
}
```

Đây là ví dụ **sai cú pháp**. Muốn chú giải module, chuyển annotation lên trước từ khóa `module` hoặc `open module`.

### Lỗi 3: Có MODULE nhưng không thấy annotation khi dùng reflection

Cần kiểm tra: annotation type có `@Retention(RetentionPolicy.RUNTIME)` không; annotation có đặt đúng trên module declaration không; chương trình có đang chạy trong đúng named module không; có dùng đúng type `ModuleOwner.class` hay không.

Không nên chữa bằng cách tự thêm `exports` hoặc `opens` bừa bãi; trước hết phân biệt **retention**, **vị trí gắn annotation** và **ngữ cảnh chạy JPMS**.

### Lỗi 4: Biên dịch kiểu classpath làm mất ngữ cảnh module

Khi khởi chạy ví dụ với `java --module-path out --module com.example.catalog/com.example.catalog.app.Main`, chương trình biết rõ tên named module. Nếu chuyển sang cách chạy `java -cp ...` và bỏ việc khởi chạy module, class có thể thuộc unnamed module, không cho kết quả phản ánh annotation của descriptor như mong đợi.

### Lỗi 5: Nhầm MODULE với PACKAGE

`@Target(ElementType.PACKAGE)` dành cho khai báo package, thường đặt trên dòng `package ...;` trong `package-info.java`. `@Target(ElementType.MODULE)` dành cho dòng khai báo `module ... { ... }` trong `module-info.java`. Một annotation chỉ có `PACKAGE` không thể gắn lên module descriptor và ngược lại.

### Lỗi 6: Dùng API Java cũ

JPMS và `ElementType.MODULE` ra đời trong Java 9. Dự án biên dịch theo ngôn ngữ/API Java 8 không thể sử dụng module declaration và target `MODULE`. Ví dụ ở đây dùng `javac --release 17` để thống nhất nền tảng Java 17+.

## 9. Khi nào nên chọn ElementType.MODULE?

Dùng annotation đích `MODULE` khi thông tin có **phạm vi toàn module** và bạn có công cụ thực sự sử dụng nó: module owner, nhãn phục vụ báo cáo, trạng thái hỗ trợ, mức độ thử nghiệm hay phân loại module. Nếu yêu cầu chỉ mô tả một class, method hoặc package, hãy đặt metadata ở đúng cấp thích hợp thay vì đánh dấu toàn module.

Một quy trình triển khai thực tế:

1. Xác nhận dự án đang dùng JPMS explicit named modules và có `module-info.java`.
2. Xác định metadata áp dụng cho **toàn module**, không chỉ một class hoặc package.
3. Định nghĩa annotation type, `@Target(ElementType.MODULE)`, các element bắt buộc và mặc định.
4. Chọn `@Retention` theo cách công cụ đọc annotation; dùng `RUNTIME` nếu gọi `Module.getAnnotation`.
5. Gắn annotation trên khai báo module trong `module-info.java`, truyền đủ element bắt buộc.
6. Biên dịch, chạy qua module path, thử đọc metadata từ `Class.getModule()` và kiểm tra trường hợp annotation vắng mặt.
7. Nếu phát hành annotation như API giữa nhiều module, rà soát quan hệ `requires`, `exports`, phiên bản thư viện và cách các consumer sử dụng nó.

**Ghi nhớ:** `ElementType.MODULE` xác định **đích được phép gắn annotation là khai báo module trong `module-info.java`**. Java hỗ trợ lưu metadata ấy theo `@Retention` và đọc qua `java.lang.Module` khi retention phù hợp; chính các chỉ thị JPMS mới quyết định quan hệ phụ thuộc và khả năng truy cập giữa module.
