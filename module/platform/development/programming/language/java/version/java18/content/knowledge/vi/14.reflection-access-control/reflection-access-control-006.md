# Public member trong public class và vai trò của package được export

## 1. Mục tiêu: public chưa đủ nếu package không được export

Trong module **JAVA_VERSION_JAVA18**, chương **Quyền reflection** giúp kiểm chứng các hợp đồng truy cập Java còn áp dụng trên JDK hiện đại. Một trong những nhầm lẫn phổ biến là cho rằng chỉ cần khai báo lớp `public` và phương thức `public` thì reflection từ mọi module sẽ gọi được phương thức đó.

Từ khi Java Platform Module System (JPMS) tồn tại, cần xem xét **cả quyền Java thông thường lẫn ranh giới module**. Với caller ở một *named module khác*, phép gọi công khai thông thường cần:

1. Phương thức là `public` (hoặc có quyền phù hợp với caller).
2. Lớp khai báo phương thức có khả năng truy cập công khai, ví dụ một top-level `public class`.
3. **Package chứa lớp khai báo được module sở hữu export cho module caller**: `exports p;` hoặc `exports p to caller.module;`.

Ba điều kiện này không đồng nghĩa với việc có thể truy cập member `private`. Và ngược lại, một `public class` nằm trong package không được export **không tự tạo API công khai vượt qua module boundary**.

Bài tập trung vào các API hiện đại và vẫn được hỗ trợ: `Class.getMethod`, `Class.getDeclaredMethod`, `Method.invoke`, `AccessibleObject.canAccess` / `trySetAccessible`, cùng `Module.isExported` và `Module.isOpen`. Không sử dụng cơ chế nới lỏng encapsulation đã lỗi thời để né cấu hình module.

Sau bài này, bạn sẽ phân biệt được: **khám phá method** (lookup metadata), **quyền gọi method** (access check), **export package** (API công khai cho module khác), và **open package** (cho phép deep reflection khi cần).

## 2. Bốn lớp của hợp đồng truy cập

### 2.1. Khả năng truy cập của lớp

`public class Service` là lớp public ở mức khai báo Java. Nhưng khi nó thuộc named module `demo.library`, package của `Service` vẫn phải được export phù hợp để module khác truy cập nó qua cơ chế truy cập công khai thông thường.

Đừng gộp hai câu hỏi:

- `Modifier.isPublic(Service.class.getModifiers())` trả lời lớp có khai báo `public` không.
- `Service.class.getModule().isExported("demo.api", callerModule)` trả lời module sở hữu có export package cho caller hay không.

Một lớp có thể là `public` ở câu thứ nhất nhưng package không được export ở câu thứ hai.

### 2.2. Khả năng truy cập của member

`getMethod("ping", String.class)` tìm method `public` theo tên và kiểu tham số khai báo, bao gồm public inherited methods. `getDeclaredMethod` tìm method được khai báo tại lớp, kể cả private, nhưng không tự cấp quyền gọi.

Với instance method, caller còn phải cung cấp receiver thuộc kiểu phù hợp; với static method, receiver truyền vào `Method.invoke` có thể là `null`. Bài sẽ dùng static method để chỉ đo **quyền module**, không làm nhiễu phép thử vì tạo object.

### 2.3. Khả năng đọc module và export package

JPMS phân biệt:

- `requires demo.library;`: module tiêu thụ khai báo **readability** để dùng API khác khi biên dịch.
- `exports demo.api;`: module thư viện công bố một package không giới hạn đích export cho các module khác có khả năng đọc module đó.
- `exports demo.api to demo.consumer;`: chỉ export package cho module đích đã nêu.
- Không có `exports demo.internal;`: package internal **không nằm trong API được export**, cho dù các class trong đó là `public`.

**Lưu ý kỹ thuật quan trọng:** kiểm tra truy cập của *core reflection* có một khác biệt với kiểm tra ngôn ngữ Java ở compile time: đối với reflected object, việc kiểm tra access được thực hiện như thể module chứa caller đọc module khai báo member. Vì vậy `Module.canRead(...)` là thông tin kiến trúc hữu ích, nhưng không nên máy móc kết luận rằng `Method.invoke` chắc chắn thất bại chỉ vì không có một cạnh readability được khai báo trực tiếp. Export và các điều kiện access còn lại vẫn phải được đánh giá. Với source code Java dùng API trực tiếp, thiết lập `requires` phù hợp.

### 2.4. Mở package cho reflection sâu

`opens demo.internal to demo.consumer;` **khác** `exports demo.internal to demo.consumer;`:

- `exports` cho phép truy cập các type/member đủ điều kiện `public` theo hợp đồng module.
- `opens` cho phép caller phù hợp *yêu cầu bỏ kiểm tra truy cập* qua `trySetAccessible()`/`setAccessible(true)` cho reflection; nó **không** tự biến package thành exported API để source code import/compile.
- `opens` không tự khiến `Method.invoke` bỏ access check khi chưa yêu cầu suppression; code vẫn cần `trySetAccessible()` nếu chỉ được open mà không được export.
- Export một package **không** tự cho phép gọi private field/method từ module khác.

Trong thiết kế API mới, ưu tiên export những public API thật sự cần; chỉ open package hạn chế theo framework sử dụng deep reflection. Tránh mở toàn module chỉ vì một testcase.

## 3. Sơ đồ quyết định khi reflection qua module boundary

```text
Class<?> đã được load, Method đã được lấy
                    |
                    v
         Caller muốn gọi public member?
                    |
                    v
  Declaring class có public / public member?
         |                               |
        Không                            Có
         |                               |
         v                               v
  Cần access riêng              Package của declaring class
  hoặc thiết kế lại              được export cho caller?
                                         |      |
                                       Không    Có
                                         |      |
                                         v      v
                               Invoke thường  invoke có thể
                               bị từ chối      gọi (còn kiểm tra
                                         |     receiver/arguments)
                                         v
                               Có opens phù hợp?
                                     |     |
                                   Không   Có
                                     |     |
                                     v     v
                                 Không được  thử trySetAccessible()
                                 bypass      rồi mới invoke
```

Trong sơ đồ, `declaring class` là kết quả `method.getDeclaringClass()`. Khi method được kế thừa hoặc được compiler sinh bridge, **đừng suy quyền truy cập chỉ từ tên lớp dùng để gọi `getMethod`**: cần biết method đang được khai báo ở lớp nào và module nào sở hữu nó.

Một method vẫn có thể thất bại tại bước gọi vì sai receiver, sai số lượng/kiểu tham số hoặc vì method đích ném exception. Đây là các vấn đề **khác** với export.

## 4. So sánh các cấu hình module

Giả sử code ở `demo.consumer` muốn phản chiếu method trong `demo.library`.

| Thư viện: class / method | Package trong `module-info.java` | Lookup bằng `getMethod` | `invoke` khi chưa suppression | `trySetAccessible` từ module khác |
| --- | --- | --- | --- | --- |
| `public class` + `public static ping` | `exports demo.api;` | Tìm được | Được phép nếu các điều kiện gọi khác đúng | Có thể thành công, nhưng không cần |
| `public class` + `public static ping` | Không export/open `demo.internal` | Có thể lấy metadata | Bị chặn bởi module access | `false` (khi không có ngoại lệ quyền nào khác) |
| `public class` + `public static ping` | `opens demo.internal to demo.consumer;`, không export | Có thể lấy metadata | Vẫn bị chặn khi chưa suppression | `true` cho caller phù hợp; sau đó có thể gọi |
| `public class` + `public static ping` | `exports demo.internal to demo.consumer;` | Tìm được | Được phép từ `demo.consumer` | Có thể thành công cho public method đó |
| `public class` + `private static secret` | Chỉ `exports demo.api;` | `getMethod` không lấy private; `getDeclaredMethod` tìm được | Không được phép | Không tự thành công vì private và package chưa open |
| Lớp package-private với `public` member | `exports demo.api;` | Có thể lấy metadata | Không đủ vì lớp khai báo không public | Cần quyền hợp lệ hoặc package open |

**Điều cần nhớ:** lấy được metadata của một method không phải bằng chứng gọi được method. Một package `opens` không đồng nghĩa với `exports`; và modifier `public` của member không thay thế modifier của declaring class hoặc export policy của module.

## 5. Bài thực hành bằng hai named module thực sự

Để thấy chính xác vai trò của `exports`, ví dụ sử dụng hai module riêng thay vì đặt mọi class trên classpath. Một module công bố API, module còn lại là caller chạy reflection.

### 5.1. Cấu trúc mã nguồn

```text
jpms-reflection-lab/
└── src/
    ├── demo.library/
    │   ├── module-info.java
    │   └── demo/
    │       ├── api/
    │       │   └── PublishedService.java
    │       └── internal/
    │           └── InternalService.java
    └── demo.consumer/
        ├── module-info.java
        └── demo/
            └── consumer/
                └── Main.java
```

`demo.library` có hai package. Chỉ `demo.api` được export, còn `demo.internal` không được export hoặc open. Cả hai class đều cố ý khai báo `public` và cả hai method `ping` đều `public static`: khác biệt kết quả vì **module policy**, không vì modifier method.

### 5.2. Module thư viện: chỉ export API

File `src/demo.library/module-info.java`:

```java
module demo.library {
    exports demo.api;
}
```

File `src/demo.library/demo/api/PublishedService.java`:

```java
package demo.api;

public final class PublishedService {
    private PublishedService() { }

    public static String ping(String input) {
        return "PUBLIC:" + input;
    }

    private static String secret() {
        return "PRIVATE";
    }
}
```

File `src/demo.library/demo/internal/InternalService.java`:

```java
package demo.internal;

public final class InternalService {
    private InternalService() { }

    public static String ping(String input) {
        return "INTERNAL:" + input;
    }
}
```

`PublishedService` có method `public` trong package được export. `InternalService` cũng là `public` và method `ping` cũng `public`, nhưng package `demo.internal` là nội bộ. Phương thức `secret()` minh họa trường hợp **package exported** nhưng **member private**.

### 5.3. Module tiêu thụ: requires thư viện

File `src/demo.consumer/module-info.java`:

```java
module demo.consumer {
    requires demo.library;
}
```

Khai báo `requires` làm `demo.library` đọc được ở cấp source/module graph; consumer có thể import `demo.api.PublishedService` vì package đó được export. Consumer không được import `demo.internal.InternalService` theo API ngôn ngữ Java thông thường, vì thư viện không export `demo.internal`.

### 5.4. Main: quan sát lookup và access độc lập

File `src/demo.consumer/demo/consumer/Main.java`:

```java
package demo.consumer;

import demo.api.PublishedService;

import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module callerModule = Main.class.getModule();

        // Ca A: public member + public class + exported package.
        Method published = PublishedService.class.getMethod(
                "ping", String.class);
        Module libraryModule = published.getDeclaringClass().getModule();
        String publishedPackage =
                published.getDeclaringClass().getPackageName();

        System.out.println("API_EXPORTED_TO_CALLER="
                + libraryModule.isExported(publishedPackage, callerModule));
        System.out.println("API_CAN_ACCESS=" + published.canAccess(null));

        if (!published.canAccess(null)) {
            throw new AssertionError("Public exported API phải truy cập được");
        }

        Object publishedResult = published.invoke(null, "hello");
        if (!"PUBLIC:hello".equals(publishedResult)) {
            throw new AssertionError("Sai kết quả public API");
        }
        System.out.println("API_INVOKE=PASS");

        // Ca B: public member + public class + NON-exported package.
        // Class.forName có thể load class; lookup metadata có thể thành công.
        Class<?> internalType = Class.forName(
                "demo.internal.InternalService");
        Method internal = internalType.getMethod("ping", String.class);
        Module internalModule = internal.getDeclaringClass().getModule();
        String internalPackage =
                internal.getDeclaringClass().getPackageName();

        System.out.println("INTERNAL_EXPORTED_TO_CALLER="
                + internalModule.isExported(internalPackage, callerModule));
        System.out.println("INTERNAL_OPEN_TO_CALLER="
                + internalModule.isOpen(internalPackage, callerModule));
        System.out.println("INTERNAL_CAN_ACCESS=" + internal.canAccess(null));

        if (internal.canAccess(null)) {
            throw new AssertionError("Internal method bị lộ access");
        }

        try {
            internal.invoke(null, "hello");
            throw new AssertionError("Invoke không được phép thành công");
        } catch (IllegalAccessException expected) {
            System.out.println("INTERNAL_INVOKE=DENIED");
        }

        boolean internalSuppression = internal.trySetAccessible();
        if (internalSuppression) {
            throw new AssertionError("Internal package không được open");
        }
        System.out.println("INTERNAL_TRY_SET_ACCESSIBLE=false");

        // Ca C: package được export nhưng private method vẫn private.
        Method privateMethod = PublishedService.class
                .getDeclaredMethod("secret");
        boolean privateSuppression = privateMethod.trySetAccessible();
        if (privateSuppression) {
            throw new AssertionError("Exports không mở private reflection");
        }
        System.out.println("PRIVATE_TRY_SET_ACCESSIBLE=false");

        System.out.println("MODULE_ACCESS_CONTRACT=PASS");
    }
}
```

Lưu ý các chỗ dùng `canAccess(null)`: cả `ping` và `secret` đều là **static method**, nên receiver của kiểm tra access là `null`. Đối với instance method, `canAccess` cần receiver không-null thuộc kiểu khai báo thích hợp; không sử dụng `null` cho instance method.

Trong mã này, `getMethod` xác định tên và kiểu tham số `String.class`. Nó không tự kiểm tra việc `demo.internal` có được export và cũng không tự mở package; việc truy cập được đo bằng `canAccess` và kiểm tra thực tế khi `invoke`.

### 5.5. Biên dịch và chạy đúng chế độ module

Từ thư mục `jpms-reflection-lab` trên JDK 18 trở lên:

```bash
javac -encoding UTF-8 --module-source-path src -d mods \
    -m demo.library,demo.consumer

java --module-path mods \
    -m demo.consumer/demo.consumer.Main
```

Dấu `\` cuối dòng là cú pháp tiếp tục lệnh trong Bash; nếu dùng Windows PowerShell hoặc Command Prompt, đặt từng lệnh trên một dòng:

```powershell
javac -encoding UTF-8 --module-source-path src -d mods -m demo.library,demo.consumer
java --module-path mods -m demo.consumer/demo.consumer.Main
```

**Không chuyển hai module sang classpath để chạy thử hợp đồng export.** Class trong unnamed module hoặc trên classpath có quy tắc module khác với named module. Nếu chạy `java -cp ...` và không thiết lập module graph như trên, bạn không còn đang đo cùng một tình huống JPMS.

### 5.6. Kết quả cần quan sát

```text
API_EXPORTED_TO_CALLER=true
API_CAN_ACCESS=true
API_INVOKE=PASS
INTERNAL_EXPORTED_TO_CALLER=false
INTERNAL_OPEN_TO_CALLER=false
INTERNAL_CAN_ACCESS=false
INTERNAL_INVOKE=DENIED
INTERNAL_TRY_SET_ACCESSIBLE=false
PRIVATE_TRY_SET_ACCESSIBLE=false
MODULE_ACCESS_CONTRACT=PASS
```

Các dòng quan trọng nhất:

- `API_CAN_ACCESS=true`: một phương thức public trong lớp public thuộc package export cho caller có thể gọi được mà không cần phá access.
- `INTERNAL_CAN_ACCESS=false` và `INTERNAL_INVOKE=DENIED`: chỉ khai báo `public` không biến một class nội bộ thành API liên module.
- `INTERNAL_TRY_SET_ACCESSIBLE=false`: khi package không export/open theo những điều kiện phù hợp, suppression cũng không được phép.
- `PRIVATE_TRY_SET_ACCESSIBLE=false`: export cho phép API công khai, không cho phép deep reflection tùy ý vào private method.

Ví dụ cố ý chỉ gọi `trySetAccessible()` đối với các method bị từ chối để minh họa chính sách truy cập; không cần `setAccessible(true)` để gọi public exported API.

## 6. Thử thay đổi riêng export policy để xem khác biệt

### 6.1. Unqualified export: công bố cho mọi module phù hợp

Trong `demo.library/module-info.java`:

```java
module demo.library {
    exports demo.api;
    exports demo.internal;
}
```

`demo.internal` giờ trở thành exported package. Từ `demo.consumer`, method `InternalService.ping` đủ điều kiện public-access nên `internal.canAccess(null)` có thể thành `true` và `internal.invoke(null, "hello")` thành công.

Tất nhiên test `Main` ở mục 5 đang **mong đợi thất bại** cho internal API, nên cần sửa assertion hoặc chạy một test khác khi thử cấu hình này. Không giữ nguyên kỳ vọng `DENIED` rồi kết luận module policy sai.

Xuất bản toàn bộ internal package chỉ để test chạy qua thường không phải lựa chọn kiến trúc tốt. Trước hết hãy xem phương thức thực sự cần nằm ở public API nào.

### 6.2. Qualified export: công bố cho một module cụ thể

Nếu chỉ `demo.consumer` được phép dùng public API trong `demo.internal`:

```java
module demo.library {
    exports demo.api;
    exports demo.internal to demo.consumer;
}
```

Khi đó:

- `libraryModule.isExported("demo.internal")` có thể là `false` vì không export vô điều kiện.
- `libraryModule.isExported("demo.internal", callerModule)` là `true` đối với `demo.consumer`.
- Với một module khác không được nêu trong danh sách `to`, kết quả `isExported(package, otherModule)` vẫn là `false`.

**Đừng dùng overload `isExported(String)` để kết luận qualified export không tồn tại.** Khi kiểm tra quyền cho một consumer cụ thể, phải truyền `Module` caller vào `isExported(String, Module)`.

### 6.3. Open package không giống export package

Thay vì export `demo.internal`, hãy thử:

```java
module demo.library {
    exports demo.api;
    opens demo.internal to demo.consumer;
}
```

Trong trường hợp này, `demo.internal` **không** là package exported cho source-level public access. Tuy nhiên, `internal.trySetAccessible()` có thể trả `true` cho module `demo.consumer`, và `internal.invoke(null, "hello")` có thể thành công **sau khi** suppression được bật trên đúng `Method`.

Điểm cần chú ý ở chương trình mục 5: `internal.canAccess(null)` trước `trySetAccessible` vẫn phản ánh kiểm tra access ban đầu. Sau khi bật suppression thành công, kiểm tra lại `internal.canAccess(null)` và thử `invoke` để quan sát khác biệt. Vì assertion cũ cố ý yêu cầu `trySetAccessible=false`, hãy đổi kỳ vọng khi thực hành case `opens`.

`opens` là cơ chế cho các tình huống reflection sâu có kiểm soát như serializer/mapping framework. Đừng thay `exports` bằng `opens` nếu mục tiêu của bạn là cung cấp một thư viện Java với public API ổn định cho module khác.

### 6.4. Export không mở private method

Dù `demo.api` đã `exports`, `PublishedService.secret()` vẫn là private. `getDeclaredMethod("secret")` có thể trả về metadata, nhưng caller khác module không được gọi private method chỉ nhờ export.

Nếu cố ý cần deep reflection cho một framework đáng tin cậy, có thể bổ sung:

```java
opens demo.api to demo.consumer;
```

Sau đó `trySetAccessible` cho private method có thể thành công với caller phù hợp. Cân nhắc kỹ vì mở package cho reflection sâu tạo ra bề mặt truy cập lớn hơn export. Thường tốt hơn là đưa ra public accessor/API chính thức thay vì mở private implementation chỉ để test.

## 7. Cấu hình dòng lệnh dùng khi chẩn đoán

Khi kiểm tra một ứng dụng modular đã được build mà không thể sửa ngay `module-info.java`, JVM còn hỗ trợ các tùy chọn khởi động có phạm vi rõ:

```bash
java --module-path mods \
    --add-exports demo.library/demo.internal=demo.consumer \
    -m demo.consumer/demo.consumer.Main
```

Tùy chọn `--add-exports` bổ sung quyền export package cho module đích; về mặt access public, kết quả gần với qualified export từ descriptor. Test ban đầu phải điều chỉnh vì `internal.invoke` có thể thành công.

Để thử deep reflection có kiểm soát:

```bash
java --module-path mods \
    --add-opens demo.library/demo.internal=demo.consumer \
    -m demo.consumer/demo.consumer.Main
```

`--add-opens` làm package có thể được mở cho caller thích hợp, để `trySetAccessible` có thể thành công; nó **không thay cho** `--add-exports` khi cần compile/import public API.

Hai tùy chọn này vẫn là cơ chế JDK hiện đại, nhưng nên dùng như công cụ chẩn đoán/migration có phạm vi hạn chế. Không coi chúng là phương án mặc định để một thư viện liên module tiếp cận nội bộ của thư viện khác. Nếu cần phân phối API ổn định, cấu hình `exports`/`opens` đúng chỗ trong module descriptor và ghi rõ hợp đồng.

Không sử dụng các hướng dẫn dựa trên `--illegal-access=permit` hoặc truy cập sâu mặc định vào các package nội bộ của JDK: đó là hướng tiếp cận lỗi thời, không phù hợp với strong encapsulation của JDK hiện đại.

## 8. Các khác biệt quan trọng khi chẩn đoán reflection

### 8.1. Metadata lookup không đồng nghĩa với quyền invocation

```java
Class<?> type = Class.forName("demo.internal.InternalService");
Method m = type.getMethod("ping", String.class);

// Cả hai lời gọi đầu có thể thành công dù module không export package.
System.out.println(m.getDeclaringClass().getName());
System.out.println(m.getParameterTypes().length);

// Kiểm tra quyền gọi tách biệt.
System.out.println(m.canAccess(null));
m.invoke(null, "hello"); // có thể IllegalAccessException
```

`getMethod` trả về metadata cho public member nhưng không cấp quyền vượt module. Ngược lại, `getDeclaredMethod` có thể cho phép bạn tìm thấy method private mà không được phép gọi.

Trong hệ thống plugin, cũng cần lưu ý `Class.forName(String)` mặc định yêu cầu khởi tạo class, có thể kích hoạt static initializer. Khi chỉ cần metadata, cân nhắc `Class.forName(name, false, loader)` với class loader phù hợp để không khởi tạo class quá sớm; điều đó vẫn **không** cấp thêm quyền truy cập module.

### 8.2. Cần xét cả quyền của declaring class

Một `public` method trong class không phải public vẫn chưa trở thành một API công khai cho caller khác package.

Ví dụ bổ sung (không nằm trong chương trình hai module ở mục 5):

```java
package demo.api;

// Lớp package-private dù package demo.api được export.
final class PackagePrivateService {
    public static String ping() {
        return "not a public class";
    }
}
```

Caller khác package có thể lấy metadata của method theo reflection, nhưng không được gọi method đó bằng public Java access thông thường chỉ vì modifier của method là `public`. Luôn kiểm tra cả declaring class:

```java
boolean publicClass = java.lang.reflect.Modifier.isPublic(
        method.getDeclaringClass().getModifiers());
boolean publicMethod = java.lang.reflect.Modifier.isPublic(
        method.getModifiers());
```

Nếu declaring class là inner/nested type, còn có yếu tố enclosing type và access của ngữ cảnh khai báo. Đừng biến riêng kiểm tra modifier của method thành quyết định cho phép gọi.

### 8.3. Export của module sở hữu method, không của caller

Khi đã có `Method`, kiểm tra module theo **declaring class**:

```java
Class<?> owner = method.getDeclaringClass();
Module ownerModule = owner.getModule();
Module callerModule = Main.class.getModule();
String packageName = owner.getPackageName();

boolean exported = ownerModule.isExported(packageName, callerModule);
boolean opened = ownerModule.isOpen(packageName, callerModule);
```

`callerModule` phải là module của **code thực hiện access** theo ngữ cảnh cụ thể, không nhất thiết là module chứa đối tượng nhận kết quả hoặc module của một interface đầu vào.

Trong framework nhiều module, đoạn code gọi `method.invoke(...)` có thể nằm trong module của framework. Khi thư viện cần deep reflection, câu hỏi “package được opens cho ai?” phải trả lời theo **framework module** thực hiện `trySetAccessible`, không đơn giản theo module ứng dụng đang dùng framework. Đây là lý do `opens package to framework.module;` thường chính xác hơn mở cho một module ứng dụng không trực tiếp thực hiện reflection.

### 8.4. Reflection và MethodHandle không có cùng API kiểm tra

`Method.invoke` và `MethodHandles.Lookup` đều bị ràng buộc bởi quyền truy cập, nhưng API lookup và khái niệm lookup class/access mode của MethodHandle có quy tắc riêng. Đặc biệt, không thể lấy một `Method` bằng `getMethod` rồi suy ra `MethodHandles.publicLookup()` chắc chắn lấy được handle cùng cách trong mọi tình huống, nhất là qualified exports.

Khi dùng MethodHandle, hãy kiểm tra hợp đồng riêng của `MethodHandles.lookup()`, `publicLookup()`, `privateLookupIn(...)` và các điều kiện module. Không suy luận rằng `setAccessible` hay `trySetAccessible` đối với một `Method` đã tạo ra một quyền truy cập phổ quát cho mọi Lookup khác.

### 8.5. Phân biệt các loại exception

| Bước | Exception / kết quả | Ý nghĩa |
| --- | --- | --- |
| `Class.forName` | `ClassNotFoundException` | Class không được tìm thấy qua cách phân giải đang dùng |
| `getMethod` / `getDeclaredMethod` | `NoSuchMethodException` | Tên hoặc kiểu tham số khai báo không đúng |
| `canAccess` | `false` | Access check hiện tại không cho phép; không tự mở quyền |
| `trySetAccessible` | `false` | Không thể bật suppression theo quyền hiện tại |
| `setAccessible(true)` | `InaccessibleObjectException` | Không được phép bypass module encapsulation theo yêu cầu |
| `Method.invoke` | `IllegalAccessException` | Method tồn tại nhưng quyền gọi bị từ chối |
| `Method.invoke` | `IllegalArgumentException` | Sai receiver/argument hoặc chuyển đổi argument không hợp lệ |
| `Method.invoke` | `InvocationTargetException` | Code trong method đã được gọi và ném exception |

`NoSuchMethodException` không chứng minh package bị chặn; đây thường là lỗi *tra cứu*. `IllegalAccessException` với method đã tìm thấy chỉ ra lỗi *quyền gọi*. Nếu thấy `InvocationTargetException`, quyền gọi đã vượt qua ranh giới access; cần xem `getCause()` để xác định lỗi nghiệp vụ trong method.

Lưu ý `trySetAccessible` chỉ là một phép yêu cầu suppression, không nên dùng kết quả `true` để suy rằng mọi receiver hoặc đối số đều hợp lệ. Kiểm tra access là một phần của lời gọi, không phải toàn bộ tính đúng đắn của lời gọi.

## 9. Thiết kế bộ test hợp đồng module

Một bộ test nên có cả **kỳ vọng được phép** và **kỳ vọng bị từ chối**; không chỉ in ra kết quả bằng console rồi đánh giá bằng mắt.

| Test | Điều kiện ban đầu | Assertion cốt lõi |
| --- | --- | --- |
| T1 — public exported | `demo.api` được `exports`; class và method public | `canAccess(null) == true`; `invoke` thành công |
| T2 — public unexported | `demo.internal` không export/open | `getMethod` tìm được; `canAccess(null) == false`; `invoke` ném `IllegalAccessException` |
| T3 — no deep access | `demo.internal` không open | `trySetAccessible() == false` |
| T4 — export != opens | `demo.api` export nhưng không open; method `secret` private | `getDeclaredMethod` tìm được; `trySetAccessible() == false` |
| T5 — qualified export | `exports demo.internal to demo.consumer;` | `isExported(pkg, consumerModule) == true` và public invocation được phép |
| T6 — qualified opens | `opens demo.internal to demo.consumer;`, không export | `trySetAccessible() == true`; sau suppression có thể gọi |
| T7 — negative caller | Một module không nằm trong danh sách `to` | Không thừa hưởng quyền export/open dành cho consumer khác |

Các test T1–T4 chạy với cấu hình ở mục 5. T5–T7 yêu cầu descriptor hoặc bộ module fixture riêng vì chính policy đã thay đổi; không thể vừa mong `INTERNAL_INVOKE=DENIED` vừa mong `INTERNAL_INVOKE=PASS` trong cùng cấu hình mà không thay đổi điều kiện.

### 9.1. Đảm bảo chạy trên module path

Một test có thể bất ngờ “PASS” vì vô tình chạy class trên classpath và không tạo named module như dự kiến. Trước khi assert access, có thể kiểm tra:

```java
Module consumer = Main.class.getModule();
if (!consumer.isNamed()) {
    throw new AssertionError("Test phải chạy trong named module");
}

Module library = PublishedService.class.getModule();
if (!"demo.library".equals(library.getName())) {
    throw new AssertionError("Sai module thư viện");
}
```

Nếu module consumer hoặc library là unnamed, hãy sửa cấu hình test runner/module path trước khi kết luận về JPMS.

### 9.2. Không đánh đồng read-edge và export-edge

Trong code compile-time, `requires` xác định module readability, `exports` xác định phần API công khai của module đích. Trong core reflection, việc kiểm tra readability được giả định thuận lợi cho reflective caller theo đặc tả, nên không cố biến `Module.canRead` thành một assertion tương đương `canAccess`.

Một test hữu ích sẽ in cả `getModule().getName()`, `isExported(pkg, caller)` và `canAccess(receiver)` khi chẩn đoán. Phép gọi thực tế (`invoke`) vẫn là bằng chứng cuối cho quyền gọi ở cấu hình đó.

### 9.3. Tránh biến test thành thay đổi quyền sản xuất

Một test cần đọc private state của ứng dụng có thể nên dùng API công khai, factory hoặc adapter dành cho test thay vì thêm `open module` vào production descriptor. Nếu phải mở package cho framework thật sự, dùng qualified `opens` đến module framework khi có thể, kèm test chứng minh module không được chỉ định vẫn không có deep access.

Đừng sửa modifier class từ package-private thành public hoặc export toàn bộ package internal chỉ để làm cho reflection “chạy được”; thay đổi đó mở rộng API surface và có thể trở thành cam kết tương thích mà thư viện phải duy trì.

## 10. Checklist chẩn đoán khi public method vẫn bị từ chối

1. **Kiểm tra chữ ký:** tên + `Class<?>[]` tham số có chính xác không? Nếu không, sửa lookup trước.
2. **Kiểm tra declaring class:** `method.getDeclaringClass()` có phải public không? Có phải superclass/internal implementation không?
3. **Kiểm tra member:** `Modifier.isPublic(method.getModifiers())` có đúng không?
4. **Kiểm tra module thực:** `method.getDeclaringClass().getModule()` và module của caller có đúng như kỳ vọng không?
5. **Kiểm tra export:** `ownerModule.isExported(packageName, callerModule)`; đừng chỉ gọi overload không tham số caller khi package qualified export.
6. **Kiểm tra opens nếu cần deep reflection:** `ownerModule.isOpen(packageName, callerModule)`; chỉ yêu cầu `trySetAccessible` khi thật sự cần.
7. **Tách quyền và đối số:** method có public access vẫn có thể lỗi khi receiver không phù hợp, số lượng/kiểu đối số sai, hoặc code trong method ném exception.
8. **Xác nhận launch mode:** chạy trên module path với named modules, không lẫn với classpath.
9. **Ưu tiên sửa hợp đồng module:** export public API, chỉ open chính xác package cần deep reflection.
10. **Chạy lại test được phép và bị từ chối:** quyền mới mở cho đúng caller nhưng không vô tình công khai internal API cho mọi module.

## 11. Bài tập và tiêu chí hoàn thành

**Bài A — exported API:** chạy bài mục 5, giải thích vì sao `PublishedService.ping` được invoke dù caller ở module khác. Ghi lại `getDeclaringClass`, `isExported` và `canAccess`.

**Bài B — public nhưng internal:** giữ class và method `InternalService.ping` đều public, không export/open package. Xác nhận lấy được `Method`, nhưng `invoke` thất bại với `IllegalAccessException`.

**Bài C — qualified export:** thêm `exports demo.internal to demo.consumer;`. Điều chỉnh test để method public được gọi. Dùng overload `isExported(String, Module)`, không dựa vào `isExported(String)`.

**Bài D — qualified opens:** thay qualified exports bằng `opens demo.internal to demo.consumer;`. Xác nhận `trySetAccessible` là bước cần thiết trước khi gọi; không nhầm kết quả với source-level import.

**Bài E — public class nhưng private member:** giữ `demo.api` exported, tra cứu `secret()` bằng `getDeclaredMethod`. Xác nhận chỉ export không cho phép deep reflection vào private method.

**Bài F — named module vs classpath:** chạy cùng nội dung qua module path và thử một cấu hình classpath ở môi trường thực hành riêng. So sánh kết quả, nêu rõ vì sao chỉ phép thử named-module mới xác minh hợp đồng `exports` của JPMS.

**Tiêu chí hoàn thành:** bạn giải thích và kiểm thử được vì sao “`public method` trong `public class`” vẫn có thể bị từ chối giữa các module; xác định đúng module và package của declaring class; phân biệt export với opens và discovery với invocation; sửa đúng `module-info.java` hoặc cấu hình test mà không tùy tiện mở rộng quyền production.

### Tài liệu tham khảo

- [Java SE Class — getMethod / getDeclaredMethod](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): phạm vi tìm public/declared method.
- [Java SE AccessibleObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `canAccess`, giới hạn khi qua module.
- [Java SE Method](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html): `invoke` và các ngoại lệ.
- [Java SE Module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `isExported`, `isOpen`, `canRead`.
- [Java Language Specification — Modules and Access Control](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7): module declaration, `requires`, `exports`, `opens`.
- [Java Platform Module System — javac/java tooling](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `--module-path`, `--add-exports`, `--add-opens`.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): bối cảnh strong encapsulation vẫn áp dụng trên JDK hiện đại.
