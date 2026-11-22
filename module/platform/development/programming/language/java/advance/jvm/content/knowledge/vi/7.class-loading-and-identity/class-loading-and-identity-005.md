# Class path, module path và ảnh hưởng của module đến truy cập lớp trong JVM

## Mục tiêu bài học

Từ Java 9, hệ thống module của Java Platform (*JPMS — Java Platform Module System*) bổ sung một tầng mô tả **module phụ thuộc vào module nào và package nào được phép truy cập**. Vì vậy, một tệp `.class` hoặc JAR tồn tại trên ổ đĩa chưa đủ để kết luận mã nguồn có thể import kiểu của nó, JVM có thể tìm thấy nó hoặc reflection có thể đọc được private member bên trong.

Sau bài học, bạn có thể:
- Phân biệt **class path**, **module path** và những cách tìm class/interface khi chạy Java.
- Hiểu **unnamed module**, **named module** (explicit và automatic) và vai trò của `module-info.java`/`module-info.class`.
- Giải thích các khái niệm **observability**, **module resolution**, **readability** và **accessibility** mà không đánh đồng chúng.
- Áp dụng `requires`, `exports`, `opens`, `requires transitive` và các tham số dòng lệnh liên quan.
- Biên dịch/chạy ví dụ Java 17+ bằng class path và module path; biết vì sao hai ví dụ dùng cách cấu hình khác nhau.
- Chẩn đoán lỗi “module not found”, “package is not visible”, `ClassNotFoundException`, `NoClassDefFoundError` và `InaccessibleObjectException`.
- Nhớ rằng định danh class runtime vẫn phụ thuộc **tên nhị phân và defining class loader**, không đơn thuần một path hoặc tên module.

## 1. Class path và module path giải quyết những vấn đề gì?

**Class path** là danh sách địa điểm JVM/công cụ Java tìm các lớp ứng dụng theo cơ chế truyền thống: thư mục chứa cấu trúc package và các JAR. Code ứng dụng được đặt trên class path của Java launcher thường thuộc **unnamed module** của class loader tương ứng.

**Module path** là danh sách địa điểm để hệ thống module phát hiện **module**. Một module thường là một JAR có `module-info.class` (*modular JAR*) hoặc một thư mục module đã biên dịch (*exploded module*). Các JAR thông thường không có module descriptor vẫn có thể trở thành **automatic modules** khi đặt trên module path, tùy quy tắc định danh.

Hai khái niệm này không thay thế nhau hoàn toàn. Một chương trình có thể dùng cả hai, nhưng **đặt JAR ở nơi khác có thể thay đổi cách JVM nhóm mã vào module và cách kiểm tra truy cập**.

| Tiêu chí | Class path | Module path |
| --- | --- | --- |
| Đầu vào thông dụng | Thư mục các `.class`, JAR | Exploded modules, modular JAR, một số JAR thường làm automatic modules |
| Module của mã đặt tại đó | Thường là **unnamed module** | **Named module** sau khi được phát hiện và resolve |
| Cấu hình ở `java` | `-cp`, `-classpath`, `--class-path` | `-p`, `--module-path` |
| Cấu hình ở `javac` | `-cp` / `--class-path` | `--module-path` |
| Quan hệ phụ thuộc | Không khai báo dependency graph bằng `module-info` | `requires` và quá trình module resolution/readability |
| Kiểm soát package công khai | Chủ yếu dựa access modifier Java | Thêm **`exports`** và **`opens`**, tùy module đọc được |
| Chạy main | `java -cp out pkg.Main` | `java --module-path mods -m name/pkg.Main` |
| Vấn đề thường gặp | Sai classpath, thiếu JAR, bản phụ thuộc trùng | Module chưa resolve, không đọc được module, package không export/open, split package |

**Không được nhầm:**
- Class path **không phải** package name. Package `com.example.api` tương ứng đường dẫn `com/example/api` **bên dưới root classpath**, không phải nguyên root phải trỏ vào thư mục cuối `api`.
- Module path **không phải** đường dẫn trực tiếp đến mọi class trong module. Nó chứa nơi có thể tìm module, còn class được xác định thông qua module và class loader.
- Đưa một file JAR vào module path **không bảo đảm module đó đã được resolve**. Việc resolution còn phụ thuộc root modules, `requires` và tùy chọn launcher.
- Module path **không phải giải pháp tự động khắc phục ClassNotFoundException**. Việc tìm/đọc/truy cập lớp là nhiều bước khác nhau.

## 2. Định danh class ở runtime không chỉ là tên hiển thị

Trong mã nguồn Java, ta viết `com.example.api.Service`; JVM dùng *binary name* và class loader để xác định một class/interface runtime. Theo mô hình JVMS, class identity dựa trên **cặp (binary name, defining class loader)**.

Ví dụ:

~~~text
Tên nguồn / binary:   com.example.api.Service
JVM internal name:    com/example/api/Service
Class file:           com/example/api/Service.class

Class loader L1 defines Service -> class identity A
Class loader L2 defines Service -> class identity B
~~~

Hai class cùng tên nhưng do **hai defining class loader khác nhau** định nghĩa có thể là **hai kiểu khác nhau**: cast từ A sang B có thể thất bại. Ngược lại, hai đường dẫn chứa bản sao cùng tên không chứng minh rằng JVM sẽ nạp cả hai: chiến lược delegation, classpath search order, module graph và custom loaders quyết định class nào được tìm/định nghĩa.

Module là **một tầng tổ chức và kiểm soát truy cập** bổ sung. Không thể giản lược “class identity = module name + class name”; class loader vẫn là nhân tố cốt lõi. Để quan sát thực tế, Java cung cấp:
- `SomeType.class.getClassLoader()`: defining loader, có thể trả `null` đối với lớp do bootstrap loader định nghĩa.
- `SomeType.class.getModule()`: module sở hữu class runtime.
- `SomeType.class.getModule().isNamed()`: phân biệt named và unnamed module.
- `SomeType.class.getModule().getName()`: tên module nếu là named; có thể trả `null` với unnamed module.

Một module named đã được resolve thường gắn với class loader và module layer thích hợp; loader tùy triển khai có thể định nghĩa nhiều module. **Module layers** cho phép ứng dụng tạo thêm module configuration riêng, nhưng chúng không tự thay đổi quy tắc class identity nêu trên.

## 3. Ví dụ class path: ứng dụng không dùng module descriptor

Tạo tệp **`ClassPathDemo.java`** ở thư mục đang làm việc:

~~~java
public class ClassPathDemo {
    public static void main(String[] args) {
        Module module = ClassPathDemo.class.getModule();

        System.out.println("named=" + module.isNamed());
        System.out.println("moduleName=" + module.getName());
        System.out.println("message=classpath works");
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 -d out ClassPathDemo.java
java -cp out ClassPathDemo
~~~

**Stdout chính xác trong cấu hình classpath này:**

~~~text
named=false
moduleName=null
message=classpath works
~~~

Giải thích:
1. `javac -d out` đặt `ClassPathDemo.class` vào thư mục `out`.
2. `java -cp out ClassPathDemo` dùng `out` như **classpath root**.
3. Lớp ứng dụng ở unnamed module, do đó `isNamed() == false` và `getName() == null`.
4. Không cần `module-info.java` khi chạy ví dụ trên.

Với mã trong package, ví dụ `package demo; public class Main { ... }`, file sau biên dịch nằm trong cấu trúc `out/demo/Main.class` và launcher phải dùng **tên đủ package**:

~~~bash
java -cp out demo.Main
~~~

**Không chạy** `java -cp out/demo Main` như cách cấu hình chuẩn để sử dụng một class có package `demo`; Java launcher tìm theo binary name với root classpath phù hợp. Ví dụ package ở trên là **đoạn mô tả**, không phải thêm một file đã tồn tại từ chương trình độc lập trước đó.

### Cách viết nhiều phần tử classpath

Hình thức:

~~~text
java -cp <classpath> pkg.Main
~~~

Trong đó phần tử classpath có thể là thư mục hoặc JAR, phân cách:
- Trên **Windows**: dấu chấm phẩy `;`.
- Trên **Linux/macOS**: dấu hai chấm `:`.

Ví dụ minh họa (giả sử các đường dẫn thật sự tồn tại):

~~~text
Windows:
java -cp "out;libs/api.jar;libs/impl.jar" demo.Main

Linux/macOS:
java -cp "out:libs/api.jar:libs/impl.jar" demo.Main
~~~

Cú pháp `libs/*` ở classpath cho phép Java launcher mở rộng thành các JAR trực tiếp trong thư mục đó theo quy tắc wildcard; nó **không đồng nghĩa quét đệ quy toàn bộ thư mục con**. Nên quote đường dẫn khi có dấu cách hoặc ký tự đặc biệt. Cách tổ chức build trong Maven/Gradle có thể thiết lập classpath hộ bạn, nhưng JVM rốt cuộc vẫn cần một tập đường dẫn đúng khi khởi động.

### Classpath order và phụ thuộc trùng

Nếu cùng binary name xuất hiện nhiều lần trong classpath, thứ tự tìm kiếm và hành vi loader có thể khiến **một bản được nạp thay vì bản còn lại**. Việc một file có mặt không bảo đảm phiên bản đó được dùng. Khi điều tra:
- Ghi lại toàn bộ lệnh chạy JVM và `java.class.path` khi cần.
- Kiểm tra classpath/module path thực tế chứ không chỉ dependency declaration.
- Dùng logging class loading của JVM theo cấu hình thích hợp (ví dụ `-Xlog:class+load=info` của HotSpot) để hỗ trợ phân tích lớp được tải từ đâu.
- Không dựa vào thứ tự wildcard JAR để chọn bản dependency mong muốn; xử lý xung đột trong build/deployment.

## 4. JPMS: named module, module descriptor và module graph

Một **explicit named module** có khai báo trong **`module-info.java`** và được biên dịch thành `module-info.class`. Khai báo module thể hiện **phụ thuộc trực tiếp**, **package được export** và **package mở cho reflection sâu**, cùng cấu hình dịch vụ khi cần.

Ví dụ mô tả (đoạn code module descriptor):

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

Một module thư viện:

~~~java
module com.acme.lib {
    exports com.acme.lib.api;
}
~~~

Ý nghĩa:
- Module `com.acme.app` khai báo **`requires com.acme.lib`** để có quan hệ đọc giữa các module.
- Module `com.acme.lib` chỉ export **package `com.acme.lib.api`** theo khai báo này. Các package khác dù chứa `public class` vẫn không tự được API truy cập trực tiếp bởi code ở module khác.
- Mọi named module có **readability tới `java.base`** theo quy tắc ngầm định; không cần ghi `requires java.base;` cho phần lớn ứng dụng.

Không phải một thư viện “đã nằm trên module path” thì mọi named module khác đương nhiên đọc được thư viện đó. Có bước **module resolution** hình thành configuration từ các **root modules** và các ràng buộc phụ thuộc `requires`, sau đó hệ thống áp dụng readability và exports để xét truy cập.

### Từ path đến một kiểu có thể dùng: bốn điều kiện

Để mã trong named module `A` dùng bình thường một kiểu `public` ở package `p` của named module `B`:

1. **Observable**: module `B` phải được công cụ/hệ thống nhận diện trên module path, system modules hoặc nguồn thích hợp.
2. **Resolved**: module `B` phải có mặt trong module graph được giải quyết cho ứng dụng.
3. **Readable**: module `A` phải đọc được `B` (thường qua `requires B;` hoặc quan hệ hợp lệ khác).
4. **Accessible**: `B` phải **export** package `p` đến `A`, và class/member còn phải thỏa access modifier Java như `public`/`protected`.

Các điều kiện này **không đồng nghĩa**. Một JAR có mặt trên module path có thể observable nhưng chưa resolved; một module đã resolved có thể không readable từ `A`; một module đã readable vẫn có thể không export package chứa kiểu.

## 5. Ví dụ Java 17+ chạy bằng module path: hai module thực

Cấu trúc thư mục mong muốn:

~~~text
src/
  com.acme.lib/
    module-info.java
    com/acme/lib/api/Greeter.java
  com.acme.app/
    module-info.java
    com/acme/app/Main.java
~~~

Tệp **`src/com.acme.lib/module-info.java`**:

~~~java
module com.acme.lib {
    exports com.acme.lib.api;
}
~~~

Tệp **`src/com.acme.lib/com/acme/lib/api/Greeter.java`**:

~~~java
package com.acme.lib.api;

public final class Greeter {
    private Greeter() {
    }

    public static String hello() {
        return "Hello from library";
    }
}
~~~

Tệp **`src/com.acme.app/module-info.java`**:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

Tệp **`src/com.acme.app/com/acme/app/Main.java`**:

~~~java
package com.acme.app;

import com.acme.lib.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.hello());
        System.out.println("module=" + Main.class.getModule().getName());
    }
}
~~~

Từ thư mục chứa `src`, biên dịch bằng **JDK 17+**:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.acme.lib,com.acme.app
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

**Stdout chính xác:**

~~~text
Hello from library
module=com.acme.app
~~~

Vì sao các lệnh hoạt động?
1. `--module-source-path src` khai báo root của **cấu trúc mã nguồn nhiều module**, mỗi thư mục module có tên module và chứa `module-info.java`.
2. `-m com.acme.lib,com.acme.app` ở lệnh **`javac`** chỉ rõ module nguồn cần biên dịch (khác ngữ cảnh `-m` của `java`).
3. `-d mods` tạo các thư mục exploded module như `mods/com.acme.lib`, `mods/com.acme.app`.
4. `java --module-path mods -m com.acme.app/com.acme.app.Main` lấy `com.acme.app` làm root module; module graph resolve `com.acme.lib` vì khai báo `requires`; launcher chạy main class.
5. `Greeter` được export bởi thư viện, nên import và gọi từ module `com.acme.app` là hợp lệ.

**Chỉ có một kết quả mong đợi với ví dụ đầy đủ này**; nếu tạo đúng đường dẫn và sử dụng JDK hỗ trợ `--release 17`, chương trình không cần JAR bên ngoài.

### Điều gì xảy ra nếu bỏ `exports`?

Thay descriptor thư viện thành:

~~~java
module com.acme.lib {
    // Không exports com.acme.lib.api
}
~~~

Đây là **phương án minh họa**, không được áp dụng nếu muốn chạy bản ví dụ thành công ở trên. `Greeter` vẫn là một **public class**, và `com.acme.app` vẫn khai báo `requires com.acme.lib`. Tuy nhiên package chứa `Greeter` **không được export** sang module ứng dụng, nên compiler có thể báo package **không visible** / không được export. Thay lại `exports com.acme.lib.api;` để biên dịch được.

Điều này minh họa chính xác khác biệt giữa **access modifier `public`** và **JPMS package exports**. Chỉ có cả hai điều kiện phù hợp mới đủ cho truy cập thông thường từ module khác.

## 6. Readability: `requires` và `requires transitive`

**Readability** là quan hệ ở cấp module: module này có thể đọc module kia theo module graph. Một explicit named module thông thường khai báo phụ thuộc bằng `requires`.

Ví dụ:

~~~text
module A requires B
module B requires C
~~~

Không được suy luận từ hai dòng trên rằng **A chắc chắn có quyền đọc trực tiếp C**. Nếu module B muốn các module phụ thuộc vào B cũng đọc được C theo tính chất transitive, B có thể khai báo:

~~~java
module com.acme.facade {
    requires transitive com.acme.api;
}
~~~

Nếu `com.acme.app` có `requires com.acme.facade;`, quan hệ transitive đó khiến ứng dụng đọc được `com.acme.api` theo quy tắc module readability. **Dù vậy, package muốn được dùng vẫn phải export thích hợp**, chẳng hạn `com.acme.api` phải export package chứa kiểu API.

### Một số khai báo quan trọng

| Cú pháp | Vai trò |
| --- | --- |
| `requires other.module;` | Khai báo module hiện tại phụ thuộc vào module kia; module graph cho phép đọc nó. |
| `requires transitive other.module;` | Module nào đọc module hiện tại theo quan hệ tương ứng cũng được thiết lập readability tới module kia theo quy tắc transitivity. |
| `requires static other.module;` | Biểu thị phụ thuộc cần thiết lúc compile, có thể vắng lúc runtime nếu code không thực sự cần dùng đến; cần thiết kế optional dependency cẩn thận. |
| `exports com.acme.api;` | Export package cho các module đọc module này. |
| `exports com.acme.internal to com.acme.friend;` | **Qualified exports:** chỉ export package cho các module được nêu. |
| `opens com.acme.model;` | Mở package cho reflective access sâu ở runtime, không tự tạo quyền import bình thường ở compile time. |
| `opens com.acme.model to com.acme.json;` | **Qualified opens:** chỉ mở package cho module được nêu. |
| `open module com.acme.framework { ... }` | Mở tất cả package của module cho reflection sâu, nhưng không export tất cả package cho ordinary compile-time access. |

Một số quy tắc phụ thuộc đặc thù như `requires static transitive` cũng được JPMS hỗ trợ, nhưng hãy xác định rõ ý đồ API và optional dependency trước khi dùng.

**Không lạm dụng `requires transitive`**: nó thể hiện phụ thuộc cấu thành API của module, không chỉ là một “mẹo” để code chỗ khác thấy thêm class. Với phụ thuộc implementation thuần nội bộ, `requires` thông thường thường rõ ràng hơn.

## 7. Exports khác Opens: truy cập bình thường và reflection

Đây là điểm cốt lõi về **ảnh hưởng của module đến truy cập lớp**.

### Exports

`exports com.acme.api;` giúp code ở module khác **đọc được module hiện tại** truy cập công khai thông thường đến các kiểu `public` trong package đó, kèm quy tắc modifiers của Java. **Exports không tự mở private fields** cho reflection sâu.

Ví dụ một package được export:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

Code ở module đọc `com.acme.model` có thể dùng `import com.acme.model.api.Customer;` nếu class/members công khai và class tồn tại. Nhưng reflection với `setAccessible(true)` đối với private field của `Customer` từ module khác **không được bảo đảm** chỉ nhờ exports.

### Opens

`opens com.acme.model.internal;` mở package cho **deep reflection** ở runtime, cho phép framework có quyền reflective access phù hợp đến private/package-private/protected members theo quy tắc API và các hạn chế khác. Tuy nhiên **opens không tương đương exports ở compile time**: source trong module khác không tự được phép import ordinary code từ package chỉ được opens.

Ví dụ descriptor:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Ý nghĩa:
- Package `com.acme.domain.api` là API công khai, cho phép các module đọc được sử dụng trực tiếp.
- Package `com.acme.domain.model` được mở **riêng cho module `com.acme.json`** để framework trong module đó dùng reflection sâu.
- Những module khác không được suy luận rằng package model đã export hoặc đã mở đối với chúng.

Một **open module** mở tất cả package để reflection nhưng vẫn có tập exports riêng. Không nên dùng `open module` vô điều kiện nếu chỉ một hoặc vài package thực sự cần deep reflection.

### Bảng nhanh

| Cấu hình package | Import class public từ module khác | Reflection sâu vào private member |
| --- | --- | --- |
| Không `exports`, không `opens` | Không, theo ordinary compile-time access | Thường bị chặn qua ranh giới module |
| `exports p;` | Có, nếu readable và class/member công khai | Không chỉ nhờ `exports` |
| `opens p;` | Không chỉ nhờ opens ở compile time | Có thể được phép cho các module khác theo quy tắc reflection |
| `exports p; opens p;` | Có | Có thể được phép |
| `exports p to A;` | Module A được export, module khác không | Không chỉ nhờ exports |
| `opens p to A;` | Không chỉ nhờ opens | Chỉ module A được mở |
| Package thuộc unnamed module | Theo cơ chế tương thích, được export và open | Dễ tương tác reflection hơn, vẫn phải xét API và chính sách bảo mật khác |

**Caveat quan trọng:** “Mở package” không cho phép chạy tùy ý mã native hoặc bỏ qua mọi giới hạn JVM; còn có access rules của reflection API, class loader, security và code logic. Phân biệt quyền từ JPMS với quyền của hệ thống, dữ liệu và ứng dụng.

## 8. Unnamed module: classpath trong thế giới JPMS

Từ Java 9, code không có module declaration được gán vào **unnamed module** của class loader thích hợp. Thiết kế này hỗ trợ ứng dụng Java cũ.

Các đặc điểm:
- Một unnamed module **đọc mọi observable module** theo mô hình module system; tuy nhiên named modules trên module path vẫn cần được **resolve thích hợp** để có mặt trong configuration mà ứng dụng dùng.
- Unnamed module **exports và opens mọi package** của nó theo quy tắc JPMS.
- Named module **không thể dùng khai báo `requires` để phụ thuộc trực tiếp vào unnamed module**, vì unnamed module không có tên để khai báo trong descriptor.
- Có thể có **nhiều unnamed modules** gắn với các class loader khác nhau; không nên mặc định chỉ có đúng một unnamed module vật lý trên toàn JVM.
- Không nên lẫn unnamed **module** với **unnamed package** (default package); một class có `package com.example;` vẫn có thể thuộc unnamed module khi nằm trên classpath.

### Classpath cần dùng một named module trên module path

Giả sử thư viện `com.acme.lib` ở module path còn chương trình truyền thống nằm trên classpath. Lệnh minh họa:

~~~bash
java --module-path mods --add-modules com.acme.lib -cp classes com.acme.app.Main
~~~

Lệnh này có ý nghĩa **chỉ nếu `classes` chứa class `com.acme.app.Main` đã biên dịch theo cấu hình classpath và mô-đun `com.acme.lib` có trên module path**. `--add-modules com.acme.lib` bổ sung module thư viện làm root khi cần, khiến nó được resolve. Nhưng **không thay thế exports**: chương trình classpath chỉ được ordinary access đến package mà thư viện export phù hợp.

Nếu named module cần đọc classpath/unnamed module, chỉ `requires` trong `module-info.java` là **không đủ/không hợp lệ**. Có những tùy chọn đặc biệt như `--add-reads my.module=ALL-UNNAMED` ở các tình huống chuyển tiếp; nhưng nên ưu tiên module hóa thư viện hoặc đưa phụ thuộc vào dạng module rõ ràng hơn thay vì kéo dài cấu hình đặc biệt không cần thiết.

## 9. Automatic module: JAR thường được đặt trên module path

Một JAR **không chứa `module-info.class`** có thể được hệ thống module coi là **automatic module** khi đặt trên module path.

Đặc điểm chính:
- Có **tên module** được lấy từ manifest attribute `Automatic-Module-Name` nếu có, hoặc suy ra từ tên file JAR theo quy tắc.
- Một automatic module **exports mọi package** và **opens mọi package** của nó, giúp tương thích với thư viện truyền thống.
- Automatic modules có cơ chế readability rộng, gồm khả năng đọc các module cần cho quá trình chuyển tiếp, kể cả nội dung thuộc unnamed modules theo quy tắc module system.
- Chúng **không cần `module-info.class`** trong JAR; dù vậy chúng vẫn là **named modules** khi được resolve trên module path.
- Tên được suy ra từ filename có thể thay đổi khi đổi tên JAR/phiên bản; nên sử dụng manifest `Automatic-Module-Name` ổn định nếu cần tương thích trong quá trình chuyển đổi.

**Cẩn thận khi dùng automatic module:** module này có thể giúp chương trình named module tạm thời phụ thuộc vào JAR cũ, nhưng **không cung cấp strong encapsulation mặc định** vì tất cả package đều được export/open. Khi thư viện bổ sung module descriptor tường minh trong bản sau, accessibility có thể thay đổi; cần rà soát các package đang được sử dụng.

### Ba cách đặt cùng một JAR

~~~text
lib/legacy.jar trên CLASS PATH
  -> code thuộc unnamed module
  -> không có tên module dùng được trong "requires"

lib/legacy.jar trên MODULE PATH (không module-info)
  -> có thể trở thành automatic named module
  -> cần được resolve; tên suy ra/manifest

lib/modern.jar trên MODULE PATH (có module-info)
  -> explicit named module
  -> requires/exports/opens theo descriptor
~~~

Không nên kết luận cứ file đuôi `.jar` thì tự biết classpath hay module path; **cách launcher/compiler được cấu hình** mới quyết định vai trò của JAR.

## 10. Module resolution, root modules và module graph

Một module tồn tại trên module path là **observable**, nhưng nó có được đưa vào configuration đang chạy hay không còn phụ thuộc **root modules** và resolution.

Khi chạy:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

`com.acme.app` là **root module**. Resolver đi qua các phụ thuộc `requires` và các ràng buộc module để xây dựng graph phù hợp; nhờ `requires com.acme.lib;`, module thư viện xuất hiện trong configuration.

Với chương trình khởi chạy từ classpath, đôi khi cần thêm:

~~~bash
java --module-path mods --add-modules com.acme.lib -cp classes demo.Main
~~~

Đây là cú pháp minh họa yêu cầu một classpath main class có thật. `--add-modules` bổ sung module cần làm root, **không tự export các package bị đóng** và **không tự làm một named module có quyền truy cập vào unnamed module**.

Một số tùy chọn hữu ích:

| Tùy chọn | Vai trò |
| --- | --- |
| `--module-path PATH`, `-p PATH` | Vị trí tìm application modules. |
| `--module NAME[/MAINCLASS]`, `-m NAME[/MAINCLASS]` | Chạy main class trong named module đã resolve. |
| `--add-modules M1,M2` | Bổ sung root modules; có những giá trị đặc biệt theo launcher, ví dụ `ALL-MODULE-PATH`. |
| `--limit-modules M1,M2` | Giới hạn tập module observable đối với quá trình resolution theo quy tắc JVM. |
| `--show-module-resolution` | In thông tin resolution để chẩn đoán graph. |
| `--list-modules` | Liệt kê các module có thể quan sát trong ngữ cảnh launcher và version của chúng. |
| `--describe-module NAME` | Hiển thị thông tin một named module. |
| `jar --describe-module --file FILE.jar` | Xem thông tin module của JAR, gồm automatic module khi phù hợp. |

Ví dụ kiểm tra:

~~~bash
java --list-modules
java --module-path mods --describe-module com.acme.lib
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Không cung cấp “stdout chính xác” cho các lệnh chẩn đoán này vì kết quả phụ thuộc JDK, tập module, classpath/module path thực tế và platform. Đối với ví dụ hai module hoàn chỉnh ở mục 5, stdout ứng dụng được xác định riêng.

### Split package và module conflict

**Split package** là tình huống cùng tên package xuất hiện trong nhiều module. JPMS hạn chế trường hợp một module đọc những module có package trùng nhau gây mơ hồ/vi phạm constraints; điều này có thể khiến biên dịch hoặc resolution thất bại ngay cả khi trước đó cách ghép JAR trên classpath vẫn chạy.

Thay vì dựa vào classpath order để né lỗi, hãy:
- Xác định JAR nào chứa package trùng.
- Cập nhật/thay thế dependency hoặc di chuyển/đổi package ownership có chủ đích.
- Kiểm tra module graph và class loader, tránh copy package nội bộ vào nhiều named modules.

Không phải mọi xung đột package đều có cùng thông báo lỗi; lỗi chính xác phụ thuộc các module và bối cảnh compile/runtime.

## 11. Tùy chọn phá encapsulation: dùng có chủ đích

JPMS cung cấp tùy chọn chuyển tiếp/migration, nhưng chúng không nên là thiết kế mặc định.

### `--add-reads`

Cú pháp khái quát:

~~~text
--add-reads SOURCE_MODULE=TARGET_MODULE
--add-reads SOURCE_MODULE=ALL-UNNAMED
~~~

Tùy chọn này bổ sung **readability edge** của source module tới target module ở cấu hình thích hợp. Nó **không tự khiến mọi package private/public đều truy cập được**; vẫn cần exports và access modifiers. Dùng để xử lý trường hợp named module cần nhìn class ở unnamed module trong migration, khi không thể đơn giản dùng `requires`.

### `--add-exports`

Cú pháp:

~~~text
--add-exports SOURCE_MODULE/PACKAGE=TARGET_MODULE
--add-exports SOURCE_MODULE/PACKAGE=ALL-UNNAMED
~~~

Cho phép package của source module được **export thêm đến target**, để code trong target module đã có readability phù hợp truy cập **public API**. Có thể đặt ở compiler hoặc runtime khi cần tương ứng; cấu hình chỉ ở compile time không tự bảo đảm runtime có cùng quyền.

Ví dụ minh họa cú pháp:

~~~bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp classes demo.Main
~~~

Lệnh trên **không phải khuyến nghị dựa vào JDK internal API** và chỉ có ý nghĩa nếu có class `demo.Main` cần quyền đó; các internal API có thể thay đổi hoặc biến mất. Không dùng `--add-exports` chỉ vì một framework cần mở private field cho reflection; tình huống đó dùng `opens`/`--add-opens` thích hợp.

### `--add-opens`

Cú pháp:

~~~text
--add-opens SOURCE_MODULE/PACKAGE=TARGET_MODULE
--add-opens SOURCE_MODULE/PACKAGE=ALL-UNNAMED
~~~

Mở package cho **deep reflection tại runtime** đối với target được chỉ định. Nó không phải lệnh “export package để source import ở compile time”. Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp classes demo.Main
~~~

Đây là ví dụ về **cú pháp tùy chọn migration**, không phải chương trình độc lập, không có stdout cố định. **Java 17 strongly encapsulates JDK internals**; việc reflection gọi `setAccessible(true)` vào private member của package chưa mở có thể ném `InaccessibleObjectException`.

### Ưu tiên phương án bền vững

Thứ tự xử lý thường hợp lý:
1. **Dùng API công khai và cấu hình module descriptor đúng**.
2. Nếu framework cần reflection, **mở đúng package cho đúng module** bằng `opens ... to ...;`.
3. Nếu buộc chuyển tiếp, dùng `--add-reads/--add-exports/--add-opens` với phạm vi nhỏ, ghi lại lý do và kế hoạch bỏ flag.
4. Không mở toàn bộ module hoặc toàn JDK chỉ để chữa một lỗi thiếu quyền chưa được phân tích.

## 12. Truy cập class qua reflection, Class.forName và ClassLoader

Đừng đồng nhất:
- **Tìm/nạp class** từ class loader.
- **Resolve module graph**.
- **Truy cập type/member** theo JLS/JPMS.
- **Bypass Java access checks** qua reflective APIs khi package đã được mở phù hợp.

Ví dụ gọi:

~~~java
Class<?> type = Class.forName("com.acme.lib.api.Greeter");
System.out.println(type.getModule().getName());
~~~

Đây là **đoạn minh họa** bên trong phương thức Java, có thể ném `ClassNotFoundException` và kết quả còn tùy loader/cấu hình runtime. `Class.forName` không phải “bùa” làm mọi module trở nên readable hay mọi private field có thể truy cập.

**Chỉ có reference `Class<?>` không chứng minh member public/private ở trong đó truy cập được.** Với reflection, `getDeclaredField` có thể phát hiện thành viên nhưng `setAccessible(true)` và đọc/ghi thực tế còn bị giới hạn bởi module opens/accessibility theo API. Ngược lại, một package chỉ mở cho reflection không có nghĩa compiler Java có thể import ordinary type từ package đó.

### Resource lookup cũng có quy tắc riêng

`ClassLoader.getResource`/`Module.getResourceAsStream` được thiết kế để tìm **tài nguyên**, không phải cơ chế thay thế module exports/opens cho class access. Named module có thể có quy tắc đóng gói non-class resources liên quan đến opened packages; khi resource không được tìm thấy, không nên tự động kết luận file JAR không chứa nó. Xem contract của API resource được dùng, package resource và module mở package nào.

## 13. Kiểm tra module runtime bằng API Java

Ví dụ standalone **`ModuleInfoDemo.java`** có thể chạy trên classpath:

~~~java
public class ModuleInfoDemo {
    public static void main(String[] args) {
        Module app = ModuleInfoDemo.class.getModule();
        Module base = String.class.getModule();

        System.out.println("appNamed=" + app.isNamed());
        System.out.println("baseName=" + base.getName());
        System.out.println("appReadsBase=" + app.canRead(base));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 ModuleInfoDemo.java
java -cp . ModuleInfoDemo
~~~

**Stdout chính xác trên JDK 17+ chuẩn với classpath launch:**

~~~text
appNamed=false
baseName=java.base
appReadsBase=true
~~~

Giải thích:
- Lớp trong classpath thuộc unnamed module.
- `String` thuộc named platform module `java.base`.
- Unnamed module đọc module `java.base`; điều này **không tự mở private members** của `java.lang.String` cho reflection.

### Kiểm tra readable và exported bằng API

Module API còn có các phương thức như `Module.canRead(Module)`, `Module.isExported(String, Module)` và `Module.isOpen(String, Module)`. Chúng hỗ trợ kiểm tra trạng thái runtime module graph nhưng không được dùng để đoán mọi access check của Java:

~~~java
Module base = String.class.getModule();
Module caller = ModuleInfoDemo.class.getModule();

System.out.println(base.isExported("java.lang", caller));
System.out.println(base.isOpen("java.lang", caller));
~~~

Đoạn trên là **minh họa trong phương thức của class ModuleInfoDemo**, không được ghép vào ví dụ trước khi biên dịch mà không sửa source phù hợp. Các giá trị có thể khác nếu runtime được bật các flag `--add-opens`/`--add-exports` hoặc module configuration tùy chỉnh.

## 14. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân khả dĩ | Hướng điều tra |
| --- | --- | --- |
| `Error: Could not find or load main class ...` | Root classpath sai, binary name sai, thiếu main class hoặc loader không tìm được | Kiểm tra `-cp` trỏ tới root package, tên đầy đủ và file class thật. |
| `ClassNotFoundException` | Class loader/reflective lookup không tìm thấy binary class được yêu cầu | Kiểm tra classpath, module graph, loader được sử dụng, tên binary. |
| `NoClassDefFoundError` | VM không thể load/define class cần dùng hoặc initialization của class từng thất bại | Xem cause và version/dependency thực tế; không chỉ dò filename. |
| `module not found: com.acme.lib` | Module không observable với path/định danh đang dùng, hoặc không thỏa resolution | Kiểm tra `--module-path`, tên module, `module-info`/manifest. |
| `package ... is not visible` | Module caller không đọc target hoặc package không export sang caller | Kiểm tra cả `requires` lẫn `exports` và qualified exports. |
| Public class ở package không export bị từ chối | `public` không đủ qua ranh giới named modules | Export đúng package, không tự sửa access bằng reflection. |
| `InaccessibleObjectException` khi gọi `setAccessible(true)` | Module sở hữu package không opens tới module gọi reflection | Thêm `opens p to framework.module;` hoặc `--add-opens` tạm thời, không dùng `--add-exports` thay. |
| `IllegalAccessError` tại runtime | Binary thực thi vi phạm access checks khi class/module configuration khác lúc build | So module graph, exports, build/runtime artifacts, JAR versions. |
| Named module không import được class ở classpath | Named module không có phụ thuộc `requires` tới unnamed module | Module hóa dependency hoặc migration flag `--add-reads` phù hợp. |
| Có JAR trên module path nhưng chương trình không tìm thấy class | Module chưa resolve, tên package/module khác, loader/context không đúng | Kiểm tra root modules, `--add-modules`, descriptor và exports. |
| “Modules have split package” hoặc resolution conflict | Cùng package nằm trong nhiều modules gây xung đột | Rà soát dependency, bỏ trùng/đổi ownership; không dựa classpath order. |
| JAR đổi tên khiến `requires X` hỏng | Tên automatic module được suy ra từ filename | Dùng tên module ổn định qua manifest hoặc explicit module-info. |
| Trước Java 9 reflection vào JDK private chạy, Java 17 thất bại | Strong encapsulation của JDK internals | Nâng framework/API; mở package giới hạn nếu bắt buộc chuyển tiếp. |
| Có `requires transitive` nhưng vẫn không import type | Package của dependency không export tới module dùng hoặc class/member không public | Kiểm tra readability **và** exports, không chỉ requires chain. |

### Checklist điều tra thực tế

1. **Đang compile hay run?** Lỗi khi compile có thể khác lỗi linking/access của bytecode đã được tạo.
2. **Class nằm ở đâu?** Kiểm tra đường dẫn `.class`, JAR, tên binary và cấu trúc package.
3. **JAR được đưa vào classpath hay module path?** Đừng kết luận từ build.gradle/pom.xml nếu runtime thực tế khác.
4. **Module thuộc loại nào?** Explicit named, automatic named hay unnamed?
5. **Đã resolved chưa?** Xem root modules, `requires`, `--add-modules` và output `--show-module-resolution`.
6. **Caller đọc được module target không?** Kiểm tra requires, transitive edges, `Module.canRead` nếu cần.
7. **Package được export sang caller không?** Kiểm tra `exports`/qualified exports, class/member modifiers.
8. **Có deep reflection không?** Kiểm tra `opens`/qualified opens thay vì chỉ `exports`.
9. **Class loader nào định nghĩa class?** Đừng bỏ qua custom loader, module layers hoặc bản JAR trùng.
10. **So build và runtime artifact**: module descriptor, manifest `Automatic-Module-Name`, phiên bản JVM, tùy chọn launcher và thư viện thực tế.

## 15. Bài tập tự kiểm tra

**Câu 1.** Một JAR có trong `--module-path` thì class của nó chắc chắn truy cập được từ mọi named module khác?

**Đáp án:** Không. Module cần observable/resolved, caller cần readability, package cần exports phù hợp, kiểu/member còn phải thỏa access modifiers.

**Câu 2.** Vì sao `public class Internal` trong một package không export vẫn không import được từ named module khác?

**Đáp án:** `public` chỉ là điều kiện access trong Java; JPMS yêu cầu package được export đến module caller bên cạnh readability.

**Câu 3.** `requires B;` có tự làm module A đọc được module C nếu B requires C không?

**Đáp án:** Không nhất thiết. Quan hệ transitive phải được khai báo/thiết lập theo quy tắc, ví dụ B có `requires transitive C;`.

**Câu 4.** Khác nhau giữa `exports p;` và `opens p;` là gì?

**Đáp án:** `exports` cho phép ordinary compile-time/runtime access tới public/protected API từ module đọc được; `opens` cho phép deep reflection runtime và không tương đương việc export package để import ordinary source ở compile time.

**Câu 5.** Một chương trình nằm trên classpath có thể hỏi tên module của chính mình không?

**Đáp án:** Có. `SomeClass.class.getModule()` trả một unnamed module; `isNamed()` false và `getName()` null.

**Câu 6.** Named module `A` muốn dùng JAR cũ trên classpath, có thể viết `requires unnamed;` trong module-info không?

**Đáp án:** Không. Unnamed module không có module name để khai báo requires; nên module hóa/thay dependency hoặc dùng các cơ chế migration phù hợp.

**Câu 7.** Tại sao `Class.forName(...)` không bảo đảm `setAccessible(true)` với private field thành công?

**Đáp án:** Loading/lookup class khác với module access. Deep reflection qua ranh giới named module có thể cần package được opens phù hợp.

**Câu 8.** Một JAR không có module-info khi nằm trên module path gọi là gì?

**Đáp án:** Có thể được suy ra thành **automatic module**, có tên lấy từ manifest `Automatic-Module-Name` hoặc filename, với quy tắc compatibility riêng.

**Câu 9.** Có thể định danh class runtime chỉ bằng tên module + tên class?

**Đáp án:** Không chính xác. Theo JVMS, định danh class/interface runtime dựa vào **binary name và defining class loader**; module membership là thông tin tổ chức/access bổ sung.

**Câu 10.** Tại sao module path có thể gây lỗi split package mà trước đó classpath chạy được?

**Đáp án:** Named modules có constraints về module graph, package ownership và visibility, không cho phép cấu hình đọc các module có package trùng gây mơ hồ. Classpath truyền thống có mô hình tìm class khác, nên cùng tập JAR có thể gặp lỗi khác khi chuyển sang JPMS.

**Câu 11.** Bật `--add-opens` có giúp Java source import một internal package chưa export không?

**Đáp án:** Không. `--add-opens` dành cho reflective access ở runtime; ordinary source access thường cần exports và readability thích hợp.

**Câu 12.** Vì sao chỉ đổi tên JAR lại có thể khiến module cần `requires` không tìm thấy?

**Đáp án:** Nếu dùng **automatic module** với tên suy ra từ filename, tên module có thể thay đổi. Dùng explicit module descriptor hoặc manifest name ổn định.

## 16. Bản đồ tư duy

~~~text
                CÙNG MỘT CLASS / JAR
                         |
                  đặt ở đâu?
                /                \
         CLASS PATH           MODULE PATH
             |                     |
         unnamed module       named module
             |                 /          \
       exports/opens all  explicit     automatic
             |           module-info   inferred name
             |              |          exports/opens all
             |         requires / exports / opens
             |              |
             +--------------+-----------------+
                            |
                     Tìm và dùng class
                            |
                   1. Observable?
                   2. Resolved?
                   3. Readable?
                   4. Package exported?
                   5. Java modifiers OK?
                            |
                          ACCESS

Deep reflection: ngoài điều kiện API cụ thể, xét "opens"
Runtime class identity: (binary name, defining class loader)
~~~

**Điểm cốt lõi:** **class path quyết định nơi tìm class theo cơ chế truyền thống**, còn **module path hỗ trợ khám phá named modules và giải quyết phụ thuộc JPMS**. Đối với named module, **readability không thay thế exports**, và **exports không thay thế opens cho deep reflection**. Khi điều tra lớp “không thấy” hay “không truy cập được”, luôn tách vấn đề tìm/nạp lớp, resolution/readability, package accessibility, reflection và class loader.

## Tài liệu tham khảo chính thức

- [JLS Java SE 17 — §7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7).
- [JLS Java SE 17 — §7.7.2 Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2).
- [JLS Java SE 17 — §7.7.5 Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.5).
- [JVMS Java SE 17 — §5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3).
- [Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Java SE 17 — The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [Java SE 17 — Migrating From JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html).
- [Java SE 17 API — java.lang.Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).
