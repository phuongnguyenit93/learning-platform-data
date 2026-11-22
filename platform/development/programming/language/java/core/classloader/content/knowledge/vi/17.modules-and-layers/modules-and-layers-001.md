# JPMS thay đổi mô hình quan sát và truy cập kiểu như thế nào?

## 1. Từ ClassLoader và classpath đến module graph

**Java Platform Module System (JPMS)** xuất hiện trong Java 9 (JEP 261). Nó không thay ClassLoader, nhưng bổ sung một tầng mô tả phụ thuộc và đóng gói ở cấp **module**. Với chương trình chạy trên classpath truyền thống, việc sử dụng một kiểu chủ yếu phụ thuộc vào khả năng loader tìm class và các mức truy cập `public`, `protected`, package-private, `private`. Với **named modules**, còn có các ràng buộc **module observability, resolution, readability, exports và opens**.

Một class `public` trong JAR không còn mặc nhiên là API có thể truy cập từ mọi module khác. **Có thể tìm thấy `Class<?>` mà vẫn không được phép sử dụng method của class đó.**

Ví dụ khái niệm:

```text
module school.app
    │ requires
    ▼
module school.library
    ├── exports school.library.api
    │      └── public class PublicApi    → truy cập thông thường
    └── school.library.internal
           └── public class Secret       → không export, bị đóng kín
```

Các lớp có thể cùng được định nghĩa bởi JVM, nhưng chỉ package được export mới trở thành public API cho module đọc thư viện. Package được mở bằng `opens` còn phục vụ **deep reflection**, một cơ chế khác với `exports`.

Bài này giải thích chính xác **JPMS thay đổi mô hình quan sát và truy cập kiểu như thế nào**, cách nó kết hợp ClassLoader và ModuleLayer, và các tình huống lỗi thường gặp trên Java 17+.

## 2. Phân biệt bốn khái niệm quan trọng

| Khái niệm | Câu hỏi chính | Không đồng nghĩa với |
|---|---|---|
| **Observable module** | Môi trường compiler/runtime có thể quan sát module này như một ứng viên không? | Module đã tham gia runtime graph |
| **Resolved module** | Resolver đã chọn module vào configuration chưa? | Mọi module khác đều đọc được nó |
| **Readable module** | Module A có một read edge đến module B không? | Mọi package của B đều truy cập được |
| **Accessible type/member** | Readability, exports/opens và Java access có cho phép thao tác này không? | Class file có thể được tìm bằng loader |

Vì vậy cần xem các bước khác nhau:

```text
module artifacts / observable modules
                 │
                 ▼
       root modules + resolution
                 │
                 ▼
       resolved module graph
                 │
                 ▼
     readability: A reads B?
                 │
                 ▼
       B exports package to A?
                 │
                 ├── Truy cập Java thông thường
                 │
                 └── Nếu deep reflection:
                           B opens package to A?
                 │
                 ▼
           quyền truy cập thực tế
```

Đây là sơ đồ **điều kiện sử dụng một kiểu**. ClassLoader vẫn chịu trách nhiệm nạp/định nghĩa runtime classes, và JVM có thể trì hoãn resolution của các ký hiệu bytecode. Không được hiểu sơ đồ là từng bước JVM luôn chạy theo đúng thứ tự tuần tự tại mỗi lệnh gọi method.

## 3. Observable và resolved: có file JAR chưa đủ

**Observability** là khái niệm của JLS `7.7.6: một module có thể được host system quan sát qua compilation units/module artifacts của môi trường. Các Java platform modules và những module artifacts trên module path là những nguồn quan trọng.

**Resolution** xác định tập module thực sự thuộc module graph của một lần build/run. Ví dụ:

```bash
java --module-path mods --module school.app/school.app.Main
```

Resolver bắt đầu từ root `school.app` và những roots khác do cấu hình yêu cầu, sau đó chọn các module cần thiết theo `requires`. Dù thư mục `mods` chứa nhiều artifacts, **không phải mọi module đặt ở đó đều mặc nhiên resolved**.

Muốn bổ sung root module:

```bash
java --module-path mods --add-modules school.debug --module school.app/school.app.Main
```

Đây là ví dụ cú pháp, giả định `school.debug` và `school.app` thực sự tồn tại. `--add-modules` làm module trở thành root phù hợp, không tự export hoặc open toàn bộ package của nó.

Tách rõ ba lỗi:
- **Module không observable:** cấu hình đường dẫn hoặc tên module sai.
- **Module observable nhưng chưa resolved:** không thuộc roots hoặc dependency closure đang chọn.
- **Module resolved nhưng không accessible:** không có read edge hoặc package không export/open.

Trong debug, sử dụng `java --show-module-resolution ...` để xem resolution thực tế, thay vì chỉ kiểm tra có tệp JAR trên ổ đĩa.

## 4. Readability: yêu cầu module phụ thuộc module khác

Descriptor `module-info.java` định nghĩa quan hệ phụ thuộc:

```java
module school.app {
    requires school.library;
}
```

Điều này tạo read edge từ `school.app` đến `school.library` trong cấu hình module phù hợp. Tuy nhiên, **`requires school.library` không mở mọi package của library**.

Ví dụ:

```java
module school.library {
    exports school.library.api;
}
```

App đọc library, nên có thể dùng những kiểu public thuộc `school.library.api`. Package `school.library.internal` không được export và không phải API thông thường của library, ngay cả khi nó chứa class khai báo `public`.

### requires transitive

```java
module school.library {
    requires transitive school.model;
    exports school.library.api;
}
```

Khi `school.app` đọc `school.library`, read edge đến `school.model` được **implied** theo `requires transitive`, hỗ trợ trường hợp API public của library sử dụng kiểu public từ model. Nhưng `requires transitive` không tự export package từ một trong hai module.

### requires static

`requires static school.optional;` biểu thị dependence dùng lúc compile nhưng có thể không cần module đích ở runtime theo các quy tắc resolution. Đừng nhầm với trường/method Java `static`.

### java.base

Named modules bình thường đọc `java.base` theo quy tắc JPMS, nên các kiểu chuẩn như `String` và `Object` vẫn khả dụng mà không cần ghi tường minh `requires java.base;` trong mọi descriptor.

## 5. Exports: công bố API theo package

`exports package.name;` cung cấp quyền truy cập thông thường cho các module khác đọc module hiện tại:

```java
module school.library {
    exports school.library.api;
}
```

Khi package được export và read edge tồn tại, code ngoài module có thể import những kiểu `public` thích hợp và sử dụng member thỏa Java access control.

Không được hiểu `exports` là:
- Tự làm mọi class trong package thành `public`.
- Cho phép truy cập private field/method bằng deep reflection.
- Tự tạo read edge từ mọi module khác đến module này.
- Xuất mọi package con: package `school.library.api.internal` là package riêng, không tự được export chỉ vì `school.library.api` được export.

### Qualified exports

```java
module school.library {
    exports school.library.api;
    exports school.library.testing to school.testkit;
}
```

Chỉ module `school.testkit` mới được hưởng qualified export của `school.library.testing`, bên cạnh điều kiện cần đọc module đích. Đây là cách công bố API hạn chế cho công cụ kiểm thử hoặc module thân cận.

Package name và Java access vẫn có ý nghĩa: một class package-private trong package đã export không tự trở thành public.

## 6. Opens: quyền deep reflection lúc chạy

JPMS phân biệt **truy cập source/binary thông thường** với **deep reflection**.

- `exports p;`: cho phép truy cập public/protected API phù hợp ở compile/runtime.
- `opens p;`: cho phép truy cập reflection sâu hơn ở runtime, có thể bật `AccessibleObject.setAccessible(true)` hoặc `trySetAccessible()` đối với thành viên private khi các điều kiện khác đáp ứng.
- `opens p to framework.module;`: chỉ mở cho module được liệt kê.
- `open module m { ... }`: mở các packages ở runtime theo cơ chế open module, nhưng vẫn phải dùng `exports` cho compile-time public API.

Ví dụ:

```java
module school.library {
    exports school.library.api;
    opens school.library.internal to school.app;
}
```

`school.app` được phản chiếu vào `school.library.internal` theo chính sách mở này, **nhưng chỉ có `opens` không khiến Java source của app được phép `import school.library.internal.Secret`**. Import trực tiếp cần `exports` phù hợp.

### Bảng so sánh

| Khai báo trong module B | A import public type khi compile | A reflection public ở runtime | A deep reflection private |
|---|---|---|---|
| Không export/open package | Không | Thường không | Không |
| `exports p;` | Có nếu A đọc B | Có | Không tự động |
| `exports p to A;` | Cho A | Cho A | Không tự động |
| `opens p;` | Không do opens | Có thể theo runtime access | Có |
| `opens p to A;` | Không do opens | Cho A | Cho A |
| `open module B` | Chỉ package được exports | Các package được mở | Có theo quyền/runtime checks |

Một điều tinh tế: `Module.isExported(p, A)` có thể trả `true` **ở runtime** sau khi `p` được mở tới A, dù `module-info.java` không có `exports p`. Không dùng đơn độc kết quả `isExported` để suy ra compiler cho phép `import` package đó.

## 7. Ví dụ đầy đủ Java 17+: tìm được class nhưng bị chặn truy cập

Tạo hai named modules:
- `school.library` có package API được export và package internal bị đóng.
- `school.app` đọc `school.library`.
- App gọi public API thành công, lấy được `Class<?>` của internal class bằng tên, nhưng reflective invocation bị chặn.

### 7.1. Bố cục

```text
project/
└── src/
    ├── school.library/
    │   ├── module-info.java
    │   └── school/library/
    │       ├── api/PublicApi.java
    │       └── internal/Secret.java
    └── school.app/
        ├── module-info.java
        └── school/app/Demo.java
```

File `src/school.library/module-info.java`:

```java
module school.library {
    exports school.library.api;
}
```

File `src/school.library/school/library/api/PublicApi.java`:

```java
package school.library.api;

public final class PublicApi {
    private PublicApi() {
    }

    public static String message() {
        return "hello API";
    }
}
```

File `src/school.library/school/library/internal/Secret.java`:

```java
package school.library.internal;

public final class Secret {
    private Secret() {
    }

    public static String reveal() {
        return "secret";
    }

    private static String whisper() {
        return "private";
    }
}
```

File `src/school.app/module-info.java`:

```java
module school.app {
    requires school.library;
}
```

File `src/school.app/school/app/Demo.java`:

```java
package school.app;

import java.lang.reflect.Method;
import school.library.api.PublicApi;

public final class Demo {
    public static void main(String[] args) throws Exception {
        Module app = Demo.class.getModule();
        Module library = PublicApi.class.getModule();

        System.out.println("app module: " + app.getName());
        System.out.println("library module: " + library.getName());
        System.out.println("reads library: " + app.canRead(library));
        System.out.println("api exported: "
                + library.isExported("school.library.api", app));
        System.out.println("internal exported: "
                + library.isExported("school.library.internal", app));
        System.out.println("internal opened: "
                + library.isOpen("school.library.internal", app));
        System.out.println("api message: " + PublicApi.message());

        Class<?> hidden = Class.forName(
                "school.library.internal.Secret");
        System.out.println("found hidden: " + hidden.getName());

        try {
            System.out.println("public reflection: "
                    + hidden.getMethod("reveal").invoke(null));
        } catch (IllegalAccessException expected) {
            System.out.println("public reflection: denied");
        }

        Method privateMethod =
                hidden.getDeclaredMethod("whisper");
        System.out.println("deep reflection enabled: "
                + privateMethod.trySetAccessible());
    }
}
```

### 7.2. Biên dịch và chạy

Chạy trong thư mục `project` với JDK 17+:

```bash
javac --module-source-path src -d mods src/school.library/module-info.java src/school.library/school/library/api/PublicApi.java src/school.library/school/library/internal/Secret.java src/school.app/module-info.java src/school.app/school/app/Demo.java
java --module-path mods --module school.app/school.app.Demo
```

Stdout:

```text
app module: school.app
library module: school.library
reads library: true
api exported: true
internal exported: false
internal opened: false
api message: hello API
found hidden: school.library.internal.Secret
public reflection: denied
deep reflection enabled: false
```

**Điểm cần hiểu:**

1. `requires school.library` nên `app.canRead(library)` là `true`.
2. API package `school.library.api` được export: gọi `PublicApi.message()` thành công.
3. `school.library.internal.Secret` là class `public`, nhưng package không export, nên app không được import hoặc gọi trực tiếp.
4. `Class.forName` vẫn tìm được runtime class nội bộ; việc có `Class<?>` **không tự chứng minh member access hợp lệ**.
5. `Method.invoke` thất bại với `IllegalAccessException`; code bắt và in `public reflection: denied`.
6. `trySetAccessible` trên private method trả `false` do package không open đến app.

Ví dụ đã được kiểm chứng biên dịch và chạy trên JDK 21; cú pháp, module access và API phù hợp Java 17+.

### 7.3. Chỉ thêm opens thì điều gì đổi?

Sửa đúng một file `src/school.library/module-info.java` thành:

```java
module school.library {
    exports school.library.api;
    opens school.library.internal to school.app;
}
```

Biên dịch lại hai modules bằng lệnh `javac` ở mục 7.2, rồi chạy lại. Những dòng thay đổi thành:

```text
internal exported: true
internal opened: true
public reflection: secret
deep reflection enabled: true
```

Những dòng còn lại không đổi. `opens` cho phép runtime reflection của `school.app`. Lúc này `isExported(internal, app)` cũng trả `true` vì **runtime access** có thể được cấp từ `opens`; điều đó **không** cho phép compile-time import package chỉ được open.

Đây là minh chứng trực tiếp cho sự khác nhau giữa **class lookup**, **readability**, **exports** và **opens**.

## 8. Reflection error: IllegalAccessException và InaccessibleObjectException

Trong code reflection:

```java
// Trích đoạn: type là Class<?> của một class khác.
java.lang.reflect.Field field = type.getDeclaredField("value");
field.setAccessible(true);
```

Nếu package đích không được mở cho module caller, `setAccessible(true)` có thể ném `java.lang.reflect.InaccessibleObjectException`. Dùng `trySetAccessible()` thường cho phép kiểm tra bằng boolean thay vì ném exception khi quyền access không thể được bật.

Phân biệt:
- `IllegalAccessException`: một lời gọi reflective method/field/constructor không có quyền truy cập.
- `InaccessibleObjectException`: yêu cầu nới quyền reflection bằng `setAccessible` không thể đáp ứng.
- `IllegalAccessError`: lỗi liên kết/runtime bytecode access, khác một checked reflective exception.
- `ClassNotFoundException`: loader không tìm thấy class; không thể kết luận là thiếu export từ mỗi CNFE.

Không “sửa” mọi lỗi này bằng cách bắt `Throwable` hoặc mở mọi package. Phương án đúng là cung cấp public API phù hợp, dùng `exports`/`opens` có mục tiêu, hoặc sửa thiết kế framework.

## 9. Các flag của Java module system

| Flag | Chức năng |
|---|---|
| `--module-path` hoặc `-p` | Nguồn module artifacts để resolver tìm |
| `--add-modules m` | Thêm module gốc khi resolve |
| `--add-reads source=target` | Bổ sung read edge |
| `--add-exports source/pkg=target` | Bổ sung qualified export |
| `--add-opens source/pkg=target` | Mở package cho deep reflection runtime |
| `--show-module-resolution` | In chi tiết resolution lúc khởi động |

Ví dụ chạy lại chương trình ở mục 7 với quyền mở package từ command line mà **không thay descriptor**:

```bash
java --module-path mods --add-opens school.library/school.library.internal=school.app --module school.app/school.app.Demo
```

Khi framework ở classpath (unnamed module), có thể gặp target `ALL-UNNAMED`:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar Main
```

Lệnh thứ hai chỉ **minh họa cú pháp**, giả định `app.jar` và `Main` có thật; đây không phải khuyến cáo mở package JDK một cách rộng rãi. Ưu tiên module descriptor hoặc public API rõ ràng trước, và dùng flag phạm vi nhỏ để chẩn đoán/migration.

`--add-opens` không tự đưa module chưa resolve vào graph hoặc làm code source compile được `import` package. `--add-exports` không tự tạo deep-reflection permission cho thành viên private.

## 10. ClassLoader tiếp tục xác định runtime class

JPMS bổ sung `Module` nhưng không bỏ **defining ClassLoader** và các quy tắc runtime class identity. Với một class:

```java
Class<?> type = String.class;
Module module = type.getModule();
ClassLoader loader = type.getClassLoader();

System.out.println(module.getName());
System.out.println(loader);
```

Đây là **trích đoạn Java**, cần đặt trong method/class. `String` thuộc `java.base`, bootstrap defining loader thường được hiển thị qua `null`.

Điểm quan trọng:
- Một ClassLoader có thể định nghĩa class của **nhiều named modules**; không có luật một module phải có loader riêng.
- Hai class ở **hai named modules** dùng cùng loader không tự có quyền package-private với nhau hoặc vượt module access.
- Một class có thể được loader nhận yêu cầu nạp (initiating loader) khác loader đã định nghĩa nó.
- Một số built-in/module-layer loaders dùng **direct delegation theo package-to-module mapping**, không nhất thiết là chuỗi parent-first đơn giản.
- Muốn xác định class runtime, log **`getName()`, `getModule()`, `getClassLoader()`** cùng nhau.

Vì thế, JPMS kết hợp **module graph** và **class loader graph**, không thay một đồ thị bằng đồ thị còn lại.

## 11. ModuleLayer: thêm modules động mà không sửa boot layer

`ModuleLayer` là tập runtime named modules đã được định nghĩa từ một `Configuration` và gán cho các class loaders. `ModuleLayer.boot()` biểu diễn layer được tạo lúc JVM khởi động. Ứng dụng plugin có thể tạo **child layer** để bổ sung module mới mà không thay đổi boot layer.

~~~text
Boot layer: java.base, host.api
    |
    +-- Child layer: sample.plugin
          +-- sample.plugin.api.Plugin
~~~

Một chuỗi thao tác điển hình:

1. Dùng `ModuleFinder.of(...)` để tìm artifact chứa module và đọc descriptor.
2. Gọi `parent.configuration().resolve(finder, ModuleFinder.of(), roots)` để tính dependency graph của các roots được chọn.
3. Gọi `parent.defineModulesWithOneLoader(configuration, parentLoader)` hoặc `defineModulesWithManyLoaders` để tạo runtime modules gắn với loader mới.
4. Dùng `child.findModule("sample.plugin")` hoặc `child.findLoader("sample.plugin")` để kiểm tra module và loader; `Class.getModule().getLayer()` cho biết layer thực sự của một class đã được nạp.

**Một layer không phải subclass của `ClassLoader`.** `WithOneLoader` ánh xạ tất cả modules của configuration mới vào một loader; `WithManyLoaders` tạo một loader cho mỗi module. Cả hai đều phải tuân thủ module resolution, package ownership và access rules. Resource, class identity và vòng đời plugin vẫn cần thiết kế riêng.

Nếu chương trình chỉ cần chứng minh **JPMS chặn truy cập vào một class**, ví dụ hai named modules ở mục 7 đã đủ. Khi cần triển khai dynamic loading, bài về `ModuleLayer.boot`, `ModuleFinder` và `defineModulesWithOneLoader/ManyLoaders` trong chương này trình bày thí nghiệm độc lập, lệnh build và loader mapping chi tiết hơn.

## 12. Type identity giữa modules, loaders và layers

Hai modules có cùng tên ở **hai ModuleLayers khác nhau** không nhất thiết là cùng đối tượng Module runtime. Hai class có cùng binary name do **hai defining loaders khác nhau** định nghĩa là hai runtime classes khác nhau, dù chúng được lấy từ hai bản JAR có nội dung giống nhau.

```text
Layer-A → Loader-A → module example.plugin → example.Plugin
Layer-B → Loader-B → module example.plugin → example.Plugin

Class_A != Class_B khi defining loaders khác nhau
```

Kết quả:
- Không cast object implementation qua hai lớp cùng tên chỉ vì `getName()` bằng nhau.
- Đặt API interface chia sẻ trong module/loader chung ổn định nếu các plugin cần giao tiếp với host.
- Quan hệ `requires`/`exports` quyết định readability/access, còn identity kiểu vẫn phụ thuộc loader và định nghĩa runtime.
- Tạo layer mới không tự đóng layer cũ hay buộc JVM unload class; còn phụ thuộc references, tasks, GC và vòng đời loader.

## 13. Unnamed modules: classpath chưa biến mất

Code chạy trên classpath thường thuộc **unnamed module** liên kết với class loader của nó. Đặc điểm chính:

- `Module.isNamed()` trả `false`; `Module.getName()` trả `null`.
- Mỗi ClassLoader có unnamed module tương ứng; JVM có thể có nhiều unnamed modules.
- Unnamed module đọc mọi runtime module theo các quy tắc đặc biệt, và export/open mọi package của chính nó.
- Nhưng nó **không tự có quyền truy cập mọi package không export/open** trong named modules.

Ví dụ `UnnamedDemo.java`:

```java
public final class UnnamedDemo {
    public static void main(String[] args) {
        Module module = UnnamedDemo.class.getModule();
        System.out.println("named: " + module.isNamed());
        System.out.println("module name: " + module.getName());
    }
}
```

Chạy:

```bash
javac UnnamedDemo.java
java -cp . UnnamedDemo
```

Stdout:

```text
named: false
module name: null
```

Điều này giúp JPMS hỗ trợ ứng dụng legacy, nhưng cũng đồng nghĩa chuyển JAR từ classpath sang module path có thể thay đổi đáng kể quyền truy cập giữa các thư viện.

## 14. Automatic modules và chiến lược migration

Một JAR **không có `module-info.class`** nhưng được đặt trên module path có thể trở thành **automatic module** khi được resolve:

- Tên module được suy ra từ manifest `Automatic-Module-Name` hoặc tên JAR.
- Nó có quy tắc đọc rộng phục vụ tương thích với module khác và code legacy.
- Các packages của automatic module được export và open rộng; **không cung cấp strong encapsulation như explicit named module chỉ export API**.
- Dễ tạo cầu nối khi một phần dependency graph còn là thư viện cũ.

Ví dụ trong main manifest:

```text
Automatic-Module-Name: legacy.network
```

Điều này giúp tên module ổn định khi JAR di chuyển từ classpath sang module path. Tuy nhiên:
- JAR trên classpath vẫn thuộc unnamed module.
- JAR tự động trên module path không có cấu trúc quyền bằng một descriptor tường minh.
- JAR có `module-info.class` trở thành explicit module theo quy tắc tương ứng.

Đừng lầm rằng package có tên `internal` được bảo vệ khỏi code bên ngoài khi thư viện vẫn là automatic module.

## 15. ServiceLoader và khai báo uses/provides

JPMS cung cấp mô hình SPI với descriptor:

Module consumer:

```java
module shop.app {
    requires shop.api;
    uses shop.api.PaymentProvider;
}
```

Module provider:

```java
module shop.payment.impl {
    requires shop.api;
    provides shop.api.PaymentProvider
        with shop.payment.impl.DefaultPaymentProvider;
}
```

Đây là **hai descriptor minh họa**, giả định interface và implementation tương ứng tồn tại. Package implementation của provider **không nhất thiết phải export** cho consumer chỉ để `ServiceLoader` tìm và khởi tạo provider theo contract JPMS.

Một số API discovery:
- `ServiceLoader.load(Service.class)` thường lấy Thread Context ClassLoader cho mô hình hỗ trợ loader.
- `ServiceLoader.load(ModuleLayer layer, Service.class)` tìm provider trong layer theo contract.
- `ModuleLayer.findLoader(name)` hữu ích khi host cần loader của module plugin.

TCCL vẫn hữu ích, nhưng khi plugin nằm trong child layer, phải xác định API/framework dùng **TCCL**, explicit loader hay **ModuleLayer** để không bỏ sót provider.

## 16. Resource visibility và class access không phải một phép kiểm

Đối với named module, các API resource:
- `ClassLoader.getResource(...)`
- `Class.getResource(...)`
- `Module.getResourceAsStream(...)`

có những quy tắc riêng về encapsulation, đặc biệt với resource thuộc package không open. Một file tồn tại vật lý trong JAR không tự bảo đảm một caller bất kỳ lấy được resource qua ClassLoader API.

Ngược lại, `Class.forName(...)` có thể tìm được class trong package không export, nhưng gọi constructor/method có thể bị module access ngăn. Vì thế không dùng `getResource("...class")` như phép thử duy nhất cho type accessibility.

## 17. Bảng chẩn đoán lỗi JPMS

| Lỗi/triệu chứng | Nhóm nguyên nhân | Hướng kiểm tra |
|---|---|---|
| `module not found` | Module không observable/resolved | `--module-path`, tên module, root, `requires` |
| `package ... is not visible` lúc compile | Không readability hoặc không export | `requires`, `exports` |
| `ClassNotFoundException` | Loader/layer không tìm được class | Module resolution, loader, binary name |
| `IllegalAccessError` | Bytecode truy cập thành viên không hợp lệ | Readability, exports, runtime package, ABI |
| `IllegalAccessException` từ reflection | Reflective invoke thiếu quyền | Public access, package exports/opens |
| `InaccessibleObjectException` | Deep reflection bị strong encapsulation chặn | `opens` hoặc qualified `--add-opens` |
| `LayerInstantiationException` | Module configuration/layer không hợp lệ | Package overlap, split delegation, module rules |
| `ClassCastException` với hai tên class giống | Khác defining ClassLoaders | `getClassLoader` và `getModule` |
| Module có trên disk nhưng `findModule` không thấy | Chưa thuộc configuration/layer đang hỏi | Root modules, resolution, layer parent |
| `ServiceLoader` không tìm provider | Sai discovery path/module descriptor | `uses`/`provides`, layer, TCCL |

**Không phải mọi lỗi đều là lỗi loader.** Class tồn tại nhưng bị chặn `exports`/`opens` là lỗi **module access** khác class file thiếu hoặc classpath sai.

## 18. Quy trình debug JPMS thực tế

1. Xác nhận JVM/JDK thật: `java -version`, `javac -version`.
2. Kiểm tra artifact nằm trên **classpath** hay **module path**.
3. Đọc `module-info.java`/`module-info.class` hoặc xác định automatic module name.
4. Xác định module graph: root modules, `requires`, `requires transitive`, resolution logs.
5. Tìm lớp runtime: `getName()`, `getModule()`, `getClassLoader()`.
6. Kiểm tra `Module.canRead` cho quan hệ giữa caller và target.
7. Kiểm tra package đã `exports` hay `opens` đúng module chưa.
8. Kiểm tra access modifiers và kiểu reflection được dùng.
9. Nếu có plugin, xác định `ModuleLayer`, `findLoader`, TCCL và API chung.
10. Nếu có SPI, kiểm tra `uses`/`provides` và overload của ServiceLoader.
11. Dùng `--add-reads`, `--add-exports` hoặc `--add-opens` giới hạn phạm vi để chẩn đoán; sau đó sửa descriptor/architecture.
12. Chạy test trên runtime và cách launch thực tế, không suy từ chạy classpath rằng modular launch sẽ giống hệt.

Lệnh hữu ích:

```bash
java --list-modules
java --describe-module java.sql
java --show-module-resolution --module-path mods --module school.app/school.app.Demo
```

Dòng thứ ba giả định đã xây modules ví dụ ở mục 7. `java --list-modules` và `--describe-module` hiển thị thông tin module trong runtime phù hợp; có thể xem nội dung `module-info.class` qua công cụ `jar --describe-module` đối với JAR.

## 19. Các hiểu nhầm cần tránh

| Hiểu nhầm | Sự thật |
|---|---|
| JAR ở module path là mọi class lập tức usable | Cần resolution, readability, exports/opens và Java access |
| `requires` tự export mọi package của dependency | Không; dependency kiểm soát exports |
| Class `public` luôn gọi được từ mọi module | Package chứa nó có thể không được export |
| `exports` cho phép gọi private members qua reflection | Deep reflection cần opens phù hợp |
| `opens` cho phép import package lúc compile | Không; cần exports |
| `Class.forName` thành công là có quyền invoke | Không; class lookup không kiểm tra quyền mọi member |
| Mỗi module có đúng một loader độc lập | Một loader có thể định nghĩa nhiều named modules |
| Một layer là một loader | Layer ánh xạ modules tới một hoặc nhiều loaders |
| Hai class cùng tên trong hai layers chắc là cùng kiểu | Defining loaders có thể khác nhau |
| Automatic module đóng kín implementation | Automatic modules có chính sách access rộng |
| Classpath không còn hoạt động từ Java 9 | Classpath tiếp tục qua unnamed modules |
| `setAccessible(true)` vượt mọi hạn chế | Strong encapsulation có thể từ chối |
| `--add-opens` giải quyết mọi lỗi | Không giải quyết dependency, resolution, ABI hoặc thiếu class |
| Module graph thay hoàn toàn ClassLoader graph | Hai cơ chế cùng tồn tại và tương tác |

## 20. Câu hỏi tự kiểm tra

1. **JPMS có từ Java mấy?** Java 9.
2. **Module path và resolved graph có phải một?** Không; module có thể ở path nhưng chưa resolved.
3. **A `requires B` có dùng được tất cả class public của B không?** Không; phải xét package exports của B.
4. **B `exports b.api` có tự export `b.api.internal` không?** Không; đó là package khác.
5. **`Class.forName` tìm được class internal có bảo đảm reflective invoke được không?** Không.
6. **Khác biệt chính giữa exports và opens?** Exports phục vụ truy cập API thông thường; opens phục vụ deep reflection runtime.
7. **`opens p to A` có làm source của A import p hợp lệ không?** Không.
8. **Vì sao `Module.isExported(p,A)` có thể true sau opens?** API hỏi runtime access, mà opens có thể cấp runtime export.
9. **Một ClassLoader có thể định nghĩa nhiều named modules không?** Có.
10. **`Class.getModule()` để làm gì?** Xác định runtime module của class.
11. **Tạo child ModuleLayer có unload layer cũ không?** Không tự động.
12. **Code trên classpath thuộc module loại nào?** Unnamed module của loader tương ứng.
13. **Automatic module có strong encapsulation như explicit module giới hạn exports không?** Không.
14. **Service provider không export implementation package có thể được ServiceLoader dùng không?** Có, theo `provides` và contract phù hợp.
15. **Nếu method bị `InaccessibleObjectException`, nên kiểm tra gì?** Package đã opens đến module caller chưa.
16. **Hai class có cùng binary name ở hai loader khác nhau có chắc cùng runtime type không?** Không.
17. **Readability và class loadability có giống nhau không?** Không.
18. **Nâng từ classpath lên named modules phải xem gì?** Resolution, requires, exports/opens, service descriptors, loaders/layers, tests.

## Tài liệu chuẩn

- [JEP 261 — Module System](https://openjdk.org/jeps/261): cơ chế JPMS, module path và module resolution.
- [Java Language Specification 17 — Chapter 7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): `7.7` module declarations, `7.7.1` dependences, `7.7.2` exports/opens, `7.7.5` unnamed modules, `7.7.6` module observability.
- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `getClassLoader`.
- [Java SE 17 API — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): `Configuration`, `findModule`, `findLoader`, `defineModulesWithOneLoader` và `defineModulesWithManyLoaders`.
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getModule`, `getClassLoader`, `Class.forName`.
- [Java SE 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible` và phản chiếu sâu.
- [Java SE 17 API — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): `uses`/`provides` và service discovery theo module layer.
- [JVMS 17 — Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, class loaders, module runtime access.

**Kết luận:** JPMS không chỉ giúp đặt tên cho các JAR. Nó đưa **module observability và resolution**, các **read edges**, **exports/opens** và **ModuleLayer** vào mô hình. ClassLoader vẫn tìm/định nghĩa class; JPMS xác định module nào quan sát/đọc module nào và package nào thực sự được phép truy cập. Vì vậy khi debug Java 9+, luôn hỏi riêng: **“Có tìm/nạp được class không?”** và **“Code caller có quyền dùng class/member đó theo cách này không?”**
