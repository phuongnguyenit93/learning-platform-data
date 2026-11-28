# `--add-opens` theo đúng module và package khi cần cấu hình tích hợp được xác định rõ

## 1. Khi nào một tích hợp reflection cần `--add-opens`?

Khi ứng dụng Java dùng reflection để đọc field private, gọi method không public hoặc khởi tạo class qua constructor bị hạn chế truy cập, việc có đối tượng `Field`, `Method` hay `Constructor` **không đồng nghĩa** với việc được phép sử dụng member đó. Java Platform Module System (JPMS) kiểm soát khả năng truy cập xuyên ranh giới module.

Trên JDK hiện đại, nếu một library hoặc framework cần *deep reflection* vào package của **named module** khác, package đó phải được mở phù hợp. Có hai cách chính:

- Khi **sở hữu module nguồn**, khai báo `opens` hoặc `opens ... to ...` trong `module-info.java` nếu việc truy cập là một phần thiết kế tích hợp.
- Khi **cấu hình tích hợp lúc chạy** và chưa thể sửa module nguồn, truyền tùy chọn launcher `--add-opens` cho **đúng module nguồn, đúng package, đúng module đích** cần reflection.

Không nên đưa tùy chọn mở hàng loạt vào mọi JVM chỉ để tránh một lỗi ngẫu nhiên. Việc mở package làm tăng bề mặt truy cập vào chi tiết triển khai bên trong và có thể tạo phụ thuộc khó duy trì khi nâng JDK hoặc framework.

Bài học thuộc chương **Quyền reflection**, mô-đun **JAVA_VERSION_JAVA18**, tập trung vào khả năng kiểm chứng hợp đồng API và hành vi reflection trên JDK đang dùng. JDK 18 đã thay đổi cách Core Reflection được triển khai thông qua JEP 416, nhưng các quy tắc module về truy cập reflective vẫn là hợp đồng quan trọng trên JDK hiện đại. Bài này chỉ dùng cú pháp và cơ chế còn được hỗ trợ; không dựa vào tùy chọn mở truy cập legacy đã lỗi thời.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `exports`, `opens`, `--add-exports` và `--add-opens`.
2. Đọc đúng cấu trúc `--add-opens=<source-module>/<package>=<target-module>`.
3. Xác định module/package nguồn và module gọi reflection từ metadata runtime.
4. Phân biệt `trySetAccessible()` trả `false` với `setAccessible(true)` ném `InaccessibleObjectException`.
5. Chạy một ví dụ hai named module trước và sau khi mở đúng một package.
6. Dùng `ALL-UNNAMED` chỉ khi caller nằm trên classpath, không phải named module.
7. Đặt tùy chọn trong **JVM thực sự chạy mã tích hợp hoặc test**, không nhầm với compiler hay build daemon.
8. Giới hạn rủi ro, viết kiểm thử và lên kế hoạch loại bỏ tùy chọn khi thư viện có API công khai phù hợp.

## 2. Bản đồ quyền truy cập của JPMS

Hãy tưởng tượng module `com.example.model` chứa một class internal và module `com.example.inspector` cần dùng reflection.

| Cấu hình ở module chứa class | Truy cập thông thường từ bên ngoài | Deep reflection vào private member của package |
| --- | --- | --- |
| Không `exports`, không `opens` | Không truy cập trực tiếp vào class qua source code module khác | Không, trừ khi có cấu hình mở phù hợp |
| `exports com.example.model.api;` | Client đọc module được dùng public API trong package xuất | Không tự động được truy cập private member |
| `opens com.example.model.internal;` | Không biến package thành public API có thể import trực tiếp khi biên dịch | Có thể bật deep reflection từ các module khác |
| `opens com.example.model.internal to com.example.inspector;` | Không xuất package cho mọi client | Chỉ mở cho named module được nêu |
| `--add-opens=com.example.model/com.example.model.internal=com.example.inspector` | Không tự thay đổi quyền compile-time trong source client | Mở package đó lúc chạy cho module inspector |

Điểm mấu chốt:

- **Export** công bố quyền truy cập thông thường tới các public type và public/protected member đủ điều kiện.
- **Open** cho phép reflective access sâu vào member không public của package, khi code gọi dùng API có thể vô hiệu hóa kiểm tra truy cập.
- `--add-exports` là lựa chọn dành cho việc bổ sung quyền xuất package; **không thay thế** việc mở package khi framework cần private field.
- `--add-opens` mở package tại runtime; không biến private field thành public trong Java source và không tự động gọi `setAccessible(true)`.

Một package có thể vừa được `exports` vừa được `opens` nếu cả public API và deep reflection đều cần thiết. Ngược lại, mở package **không đồng nghĩa** với việc mọi class trong package được phép import từ source Java của module khác.

### Vì sao không dùng `--illegal-access`?

Cơ chế nới lỏng encapsulation bằng `--illegal-access` đã trở thành tùy chọn obsolete từ JDK 17 và không phải lời giải phù hợp trên JDK hiện hành. Không dùng `--illegal-access=permit` hoặc `--illegal-access=warn` làm hướng dẫn sửa lỗi. Thay vào đó, xác định nhu cầu tích hợp cụ thể; nếu không có API thay thế, chỉ mở đúng package cần thiết với `--add-opens`.

## 3. Cú pháp chính xác của `--add-opens`

Cú pháp launcher:

```text
--add-opens=<source-module>/<package>=<target-module>
```

Khi có nhiều module đích được phép:

```text
--add-opens=<source-module>/<package>=<target-module-1>,<target-module-2>
```

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `source-module` | Module **sở hữu class/field/method** cần reflection | `com.example.model` |
| `package` | Package khai báo class cần deep reflection, viết đúng tên đầy đủ | `com.example.model.internal` |
| `target-module` | Module chứa mã thực sự gọi `trySetAccessible`/`setAccessible` hoặc sử dụng truy cập private | `com.example.inspector` |
| `ALL-UNNAMED` | Đối tượng đích đặc biệt đại diện **mọi unnamed module**, điển hình là mã trên classpath | `ALL-UNNAMED` |

Ví dụ:

```bash
java \
  --add-opens=com.example.model/com.example.model.internal=com.example.inspector \
  --module-path out \
  -m com.example.inspector/com.example.inspector.Main
```

Phải phân biệt **module** với **package**. `com.example.model` là tên module được định nghĩa trong `module-info.java`; `com.example.model.internal` là tên package chứa class. Chúng có thể giống tiền tố, nhưng không phải hai giá trị có thể thay thế cho nhau.

Trên dòng lệnh `java`, có thể viết tùy chọn và giá trị tách bằng một dấu cách hoặc viết liền bằng dấu `=`. Dạng viết liền `--add-opens=...` thường dễ truyền qua script, Docker và cấu hình JVM.

**Vị trí quan trọng:** Đây là tùy chọn JVM launcher; đặt nó **trước** `-m`, `-jar` hoặc tên main class. Nếu đặt sau main class hoặc tên JAR, chuỗi đó thường sẽ là đối số ứng dụng, không còn là cấu hình của JVM.

## 4. Ví dụ có thể biên dịch: hai named module

Chúng ta tạo một mô hình có API công khai và một class triển khai không được xuất. Module inspector chỉ biết API công khai nhưng muốn kiểm tra một private field để minh họa vì sao cần mở package.

### 4.1. Cấu trúc thư mục

```text
reflection-opens-demo/
└── src/
    ├── com.example.model/
    │   ├── module-info.java
    │   └── com/example/model/
    │       ├── api/
    │       │   ├── ConfigView.java
    │       │   └── ConfigFactory.java
    │       └── internal/
    │           └── InternalConfig.java
    └── com.example.inspector/
        ├── module-info.java
        └── com/example/inspector/
            └── Main.java
```

Tên thư mục ngay dưới `src` khớp với tên module để `javac --module-source-path src` có thể biên dịch nhiều module.

### 4.2. Module sở hữu dữ liệu

File `src/com.example.model/module-info.java`:

```java
module com.example.model {
    exports com.example.model.api;
}
```

Package `api` được xuất cho client. Package `internal` không được xuất và cũng chưa mở.

File `src/com.example.model/com/example/model/api/ConfigView.java`:

```java
package com.example.model.api;

public interface ConfigView {
    String label();
}
```

File `src/com.example.model/com/example/model/api/ConfigFactory.java`:

```java
package com.example.model.api;

import com.example.model.internal.InternalConfig;

public final class ConfigFactory {
    private ConfigFactory() {
    }

    public static ConfigView create() {
        return new InternalConfig("D-42");
    }
}
```

File `src/com.example.model/com/example/model/internal/InternalConfig.java`:

```java
package com.example.model.internal;

import com.example.model.api.ConfigView;

public final class InternalConfig implements ConfigView {
    private final String diagnosticCode;

    public InternalConfig(String diagnosticCode) {
        this.diagnosticCode = diagnosticCode;
    }

    @Override
    public String label() {
        return "ready";
    }
}
```

`diagnosticCode` là dữ liệu giả để minh họa quyền truy cập, không phải credential thực. Trong ứng dụng thật, việc sử dụng reflection để đọc state private cần có lý do nghiệp vụ và chính sách bảo mật rõ ràng.

### 4.3. Module gọi reflection

File `src/com.example.inspector/module-info.java`:

```java
module com.example.inspector {
    requires com.example.model;
}
```

File `src/com.example.inspector/com/example/inspector/Main.java`:

```java
package com.example.inspector;

import com.example.model.api.ConfigFactory;
import com.example.model.api.ConfigView;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        ConfigView config = ConfigFactory.create();
        System.out.println("public=" + config.label());

        Class<?> type = config.getClass();
        Field field = type.getDeclaredField("diagnosticCode");

        Module owner = type.getModule();
        Module caller = Main.class.getModule();
        String pkg = type.getPackageName();

        System.out.println("owner=" + owner.getName());
        System.out.println("package=" + pkg);
        System.out.println("caller=" + caller.getName());
        System.out.println("openToCaller=" + owner.isOpen(pkg, caller));
        System.out.println("canAccessBefore=" + field.canAccess(config));

        boolean enabled = field.trySetAccessible();
        System.out.println("trySetAccessible=" + enabled);

        if (enabled) {
            System.out.println("private=" + field.get(config));
        } else {
            System.out.println("private=<blocked>");
        }
    }
}
```

Phân tích:

- `ConfigFactory.create()` cung cấp đối tượng thông qua interface công khai `ConfigView`; inspector không import class internal.
- `getDeclaredField("diagnosticCode")` lấy metadata của member private trên class runtime.
- `Field.canAccess(config)` hỏi liệu caller có thể dùng field ở thời điểm đó hay không.
- `Field.trySetAccessible()` chỉ trả `true` khi JVM có thể bật quyền truy cập reflective; nếu thất bại vì package chưa mở, nó trả `false`.
- `field.get(config)` chỉ chạy sau khi đã có quyền; không cần ép kiểu sang `InternalConfig`.

**Lưu ý:** `getDeclaredField` tìm được metadata không có nghĩa là `get` sẽ được cho phép. Khâu khám phá member và khâu sử dụng private member là hai bước có quy tắc riêng.

### 4.4. Biên dịch các module

Từ thư mục dự án, trên Linux/macOS:

```bash
mkdir -p out
javac --release 18 --module-source-path src -d out \
  $(find src -name '*.java')
```

Lệnh biên dịch ví dụ giữ source/API ở mức Java 18 để minh họa tính tương thích. Quy tắc mở package ở runtime vẫn áp dụng trên JDK hiện hành.

Trên PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
$sources = Get-ChildItem -Path src -Filter *.java -Recurse |
    ForEach-Object { $_.FullName }
javac --release 18 --module-source-path src -d out $sources
if ($LASTEXITCODE -ne 0) {
    throw "Compilation failed"
}
```

Điều kiện ví dụ: có JDK hiện đại hỗ trợ `--release 18` và đang đứng ở thư mục chứa `src`. Nếu dự án đã chọn release tối thiểu khác, thay `18` bằng release thực sự được hỗ trợ.

## 5. Chạy không mở package, sau đó mở đúng một package

### 5.1. Trường hợp mặc định: package internal vẫn đóng

Trên Bash hoặc PowerShell:

```bash
java --module-path out \
  -m com.example.inspector/com.example.inspector.Main
```

Kết quả kỳ vọng (rút gọn):

```text
public=ready
owner=com.example.model
package=com.example.model.internal
caller=com.example.inspector
openToCaller=false
canAccessBefore=false
trySetAccessible=false
private=<blocked>
```

Đây là trạng thái **đúng theo thiết kế**: inspector gọi API công khai được nhưng không có quyền deep reflection vào package `internal` của module khác.

### 5.2. Mở chính xác package cho named module inspector

```bash
java --module-path out \
  --add-opens=com.example.model/com.example.model.internal=com.example.inspector \
  -m com.example.inspector/com.example.inspector.Main
```

Kết quả kỳ vọng:

```text
public=ready
owner=com.example.model
package=com.example.model.internal
caller=com.example.inspector
openToCaller=true
canAccessBefore=false
trySetAccessible=true
private=D-42
```

Tùy chọn chỉ mở `com.example.model.internal` thuộc `com.example.model` cho `com.example.inspector` trong lần khởi động JVM này. Nó không mở tất cả package của module nguồn và cũng không mở package ấy cho mọi module khác.

`canAccessBefore=false` vẫn đúng: field private chưa tự trở nên public. Khi `trySetAccessible()` thành công, reflected `Field` được đặt vào trạng thái bỏ qua kiểm tra truy cập ngôn ngữ cho việc sử dụng tương ứng.

Để chạy trên PowerShell, dùng một dòng:

```powershell
java --module-path out --add-opens=com.example.model/com.example.model.internal=com.example.inspector -m com.example.inspector/com.example.inspector.Main
if ($LASTEXITCODE -ne 0) {
    throw "Run failed"
}
```

### 5.3. Một phép thử đối chứng quan trọng

Thử mở **sai package**:

```bash
java --module-path out \
  --add-opens=com.example.model/com.example.model.api=com.example.inspector \
  -m com.example.inspector/com.example.inspector.Main
```

Kết quả deep reflection vào `InternalConfig` vẫn bị từ chối: field nằm trong package `com.example.model.internal`, không phải `com.example.model.api`.

Hoặc mở **đúng package nhưng sai target module** (module đích phải tồn tại và được giải quyết thì cấu hình mới có ý nghĩa):

```text
--add-opens=com.example.model/com.example.model.internal=com.example.some.other.module
```

Ngay cả khi một module khác được mở, điều đó không tự cấp quyền cho `com.example.inspector`. Đây là lý do phải xác định đúng module của code thực sự gọi `trySetAccessible`, thay vì đoán theo tên framework hoặc tên ứng dụng.

## 6. Phân biệt `trySetAccessible`, `setAccessible` và `canAccess`

Ba API trả lời những câu hỏi khác nhau:

| API | Câu hỏi | Hành vi đáng chú ý |
| --- | --- | --- |
| `field.canAccess(receiver)` | Caller hiện tại có dùng field được không? | Trả `boolean`; yêu cầu receiver hợp lệ cho instance field |
| `field.trySetAccessible()` | Có thể bật bỏ qua kiểm tra truy cập không? | Trả `true` nếu bật thành công, `false` nếu không được phép |
| `field.setAccessible(true)` | Yêu cầu bật bỏ qua kiểm tra truy cập | Có thể ném `InaccessibleObjectException` khi không thể bật |

`trySetAccessible` là lựa chọn thuận tiện cho tích hợp có cơ chế fallback:

```java
Field field = target.getClass().getDeclaredField("diagnosticCode");
if (field.trySetAccessible()) {
    Object value = field.get(target);
    // Chỉ đọc field private nếu việc truy cập là hợp lệ và cần thiết.
} else {
    // Dùng public API, adapter khác hoặc báo cấu hình chưa đáp ứng.
}
```

Nếu dùng `setAccessible(true)` mà package chưa mở, có thể nhận:

```text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module com.example.model does not "opens com.example.model.internal"
to module com.example.inspector
```

Thông báo minh họa trên biểu đạt nguyên nhân; câu chữ chính xác có thể khác giữa các bản JDK và loại member.

**Không dùng `AccessibleObject.isAccessible()` cho mã mới.** API này đã deprecated vì tên dễ gây hiểu nhầm: nó nói về cờ suppression, không trực tiếp cho biết caller có thể truy cập member hay không. `canAccess(receiver)` phản ánh trạng thái dùng member hiện tại; `trySetAccessible()` thử nâng khả năng truy cập theo hợp đồng module.

### Chú ý về `final`

Mở package không có nghĩa là được phép thay đổi mọi field `final`. Theo hợp đồng `AccessibleObject`, các field `static final`, field `final` trong record và field `final` của hidden class thuộc nhóm không thể sửa bằng `setAccessible`; việc bật accessible trên chúng chỉ cho phép đọc nếu được hỗ trợ.

Với những trường hợp khác, việc sửa state private/final bằng reflection vẫn là phụ thuộc mong manh vào chi tiết triển khai và có thể bị các quy tắc JDK hiện hành hạn chế thêm. Ví dụ của bài **chỉ đọc** field private, không khuyến nghị dùng `--add-opens` để sửa bất biến của đối tượng.

## 7. Khi sở hữu module: ưu tiên mở package có chủ đích trong `module-info.java`

Nếu bạn sở hữu cả library và mã tích hợp, cấu hình module nguồn bằng khai báo tường minh có thể dễ quản lý hơn flag runtime. Chẳng hạn:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.inspector;
}
```

Sau khi biên dịch lại cả hai module, chạy như ở mục 5.1 **không cần** `--add-opens`; `trySetAccessible()` sẽ thành công cho inspector vì khai báo đã cho phép.

So sánh phạm vi:

| Cách mở | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| `opens p;` trong `module-info.java` | Mở package `p` cho mọi module tại runtime | Framework tích hợp cần nhiều module consumer và đã đánh giá rủi ro |
| `opens p to m;` | Chỉ mở `p` cho named module `m` | Giao diện tích hợp đã xác định cụ thể |
| `--add-opens=s/p=m` | Mở package `p` của module `s` cho `m` trong JVM được cấu hình | Tích hợp runtime khi chưa thể sửa module nguồn |
| `--add-opens=s/p=ALL-UNNAMED` | Mở cho tất cả unnamed module | Framework/caller nằm trên classpath |

Tránh khai báo `open module com.example.model { ... }` chỉ để phục vụ một field: từ khóa `open module` mở **mọi package** của module cho deep reflection. Với nhu cầu rõ ràng ở một package, `opens ... to ...` hoặc `--add-opens` có phạm vi nhỏ hơn.

Điểm khác biệt quan trọng: `opens` trong `module-info.java` mô tả hợp đồng module thuộc sản phẩm; `--add-opens` là ngoại lệ cấu hình ở JVM khởi động. Khi quản trị một hệ thống lớn, hãy ghi lại lý do, module đích và thời điểm dự kiến loại bỏ ngoại lệ.

## 8. Khi caller nằm trên classpath: `ALL-UNNAMED`

Nếu thư viện thực hiện reflection được nạp trên **classpath**, nó thường thuộc một **unnamed module**, không có tên ổn định để ghi ở vế phải. Khi thật sự cần mở package từ named module nguồn cho caller classpath:

```bash
java \
  --module-path lib-modules \
  --add-modules=com.example.model \
  --add-opens=com.example.model/com.example.model.internal=ALL-UNNAMED \
  --class-path app.jar \
  com.example.app.Main
```

Đây là **mẫu cấu hình**: `lib-modules` phải chứa module `com.example.model`, `app.jar` phải chứa ứng dụng trên classpath và module nguồn phải được giải quyết lúc khởi động. Dùng `--add-modules` khi cần làm module nguồn được giải quyết trong cấu hình lai module-path/classpath; không cần thêm nó một cách máy móc nếu module đã được giải quyết qua graph.

`ALL-UNNAMED` mở package cho **mọi unnamed module**, không chỉ một JAR. Nó rộng hơn việc chỉ định một named module cụ thể. Nếu công cụ có thể chạy dưới named module, cân nhắc chuyển sang cấu hình đó để thu hẹp phạm vi mở.

### Cách xác nhận caller thực sự unnamed

Trong code tích hợp:

```java
Module caller = IntegrationAdapter.class.getModule();
System.out.println("isNamed=" + caller.isNamed());
System.out.println("name=" + caller.getName());
```

Nếu `isNamed=false` thì `getName()` trả `null` và caller thuộc unnamed module. Nếu `isNamed=true`, hãy dùng **tên module thực tế** ở vế phải của `--add-opens`; dùng `ALL-UNNAMED` sẽ không giải quyết yêu cầu của named caller.

Không nhầm `--add-modules=ALL-MODULE-PATH` với `ALL-UNNAMED`. Hai chuỗi là hai khái niệm khác nhau: một bên chỉ tập module được giải quyết, một bên chỉ các unnamed module đích của thao tác mở.

## 9. Xác định chính xác nguồn lỗi từ metadata và stack trace

Khi gặp lỗi, **đừng đoán** flag từ tên dependency. Lấy metadata của class khai báo member và module thực sự gọi reflection:

```java
Class<?> declaringType = field.getDeclaringClass();
Module source = declaringType.getModule();
Module caller = IntegrationAdapter.class.getModule();
String packageName = declaringType.getPackageName();

System.out.println("sourceModule=" + source.getName());
System.out.println("sourcePackage=" + packageName);
System.out.println("callerModule=" + caller.getName());
System.out.println("callerNamed=" + caller.isNamed());
System.out.println("openToCaller=" + source.isOpen(packageName, caller));
```

Ví dụ này giả định đoạn mã nằm trong lớp `IntegrationAdapter`, là chính lớp đang thực hiện reflection; thay tên lớp bằng class caller thực tế. Với field kế thừa, dùng `field.getDeclaringClass()`, không chỉ dùng `object.getClass()`, vì member có thể được khai báo trong class cha thuộc package/module khác.

Từ kết quả `sourceModule` và `sourcePackage`, có thể xây dựng một tùy chọn giới hạn theo caller:

```text
--add-opens=<sourceModule>/<sourcePackage>=<callerModule>
```

Nếu caller unnamed, thay vế phải bằng `ALL-UNNAMED`. Nếu source là unnamed module, nó vốn có chế độ mở cho reflective access; không dùng một tên module giả để tạo `--add-opens`.

### Quy trình chẩn đoán nhanh

1. Tìm lớp, field, method hoặc constructor đang bị từ chối.
2. Xác nhận đó là nhu cầu **deep reflection** chứ không phải thiếu public API.
3. Xác định named module nguồn bằng `getDeclaringClass().getModule().getName()`.
4. Xác định package nguồn bằng `getDeclaringClass().getPackageName()`.
5. Xác định module của **code gọi reflection**, có thể khác module ứng dụng chính.
6. Kiểm tra `isOpen(package, callerModule)`; nếu false, cân nhắc giải pháp API hoặc mở đúng package.
7. Đặt `--add-opens` ở JVM thực sự chạy code, rồi khởi động lại tiến trình.
8. Chạy lại test; loại bỏ flag thử nghiệm không còn cần thiết.

### Xem mô tả module khi có module path

Ví dụ với các class đã biên dịch:

```bash
java --module-path out --describe-module com.example.model
```

Lệnh cho phép xem phần thông tin module được công bố. Dùng thêm log runtime như `getModule()` để tìm đúng package và caller; kết quả mô tả module không thay thế được kiểm tra reflective access trên một member cụ thể.

## 10. Đặt flag ở đúng JVM của test runner và ứng dụng

Một lỗi phổ biến: thêm `--add-opens` vào nơi chỉ chạy **compiler** hoặc JVM **build daemon**, trong khi reflection diễn ra bên trong **JVM test** hoặc tiến trình ứng dụng khác.

### 10.1. Chạy trực tiếp bằng `java`

```bash
java \
  --add-opens=com.example.model/com.example.model.internal=com.example.inspector \
  --module-path out \
  -m com.example.inspector/com.example.inspector.Main
```

Với deployment service, cung cấp cùng tùy chọn cho lệnh khởi động service, container entrypoint hoặc cấu hình launcher mà ứng dụng sử dụng. Không thêm nó sau main class.

### 10.2. Maven Surefire hoặc Failsafe

Nếu test thực sự được chạy trong một JVM có module nguồn `com.example.model` **ở dạng named module**, và code gọi reflection trong test runner ở classpath, cấu hình JVM fork của Surefire/Failsafe có thể cần:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>
            --add-opens=com.example.model/com.example.model.internal=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
```

**Điều kiện quan trọng:** ví dụ này chỉ đúng khi module nguồn thực sự được nạp dưới tên `com.example.model` còn caller thuộc unnamed module. Nếu test cũng là named module, thay `ALL-UNNAMED` bằng tên module của test/adapter. Nếu cả module nguồn được đặt trên classpath, flag mở named module ở trên có thể không cần thiết hoặc không đúng cấu hình.

Không dùng flag chỉ để che lỗi phân giải dependency hoặc sai cấu hình test. Khi plugin fork JVM riêng, lệnh JVM của tiến trình con mới là nơi cần cấu hình `argLine`; tham số của JVM chạy Maven không tự truyền vào mọi JVM fork.

### 10.3. Gradle Test task

Với Gradle, có thể cấu hình JVM của task chạy test:

```kotlin
tasks.test {
    jvmArgs(
        "--add-opens=com.example.model/com.example.model.internal=ALL-UNNAMED"
    )
}
```

Điều kiện named/unnamed giống phần Maven: xác nhận cấu hình module-path/classpath của test trước khi chọn target. Nếu class caller là named module `com.example.inspector`, phải mở cho `com.example.inspector`.

Đưa chính sách này vào task cụ thể, thay vì gắn một danh sách mở module toàn cục cho mọi test hoặc mọi ứng dụng. Nên ghi chú tại chỗ library nào cần deep reflection và lý do.

### 10.4. CI, container và nhiều process

Mỗi JVM là một tiến trình với cấu hình riêng. Một job có thể có JVM Gradle daemon, JVM test, JVM ứng dụng, JVM chạy migration và JVM chạy công cụ code generation. Chỉ tiến trình nào thực hiện reflective access cần flag. Nếu CI chạy nhiều JDK/version, kiểm tra trên từng JVM mục tiêu.

Hạn chế dùng biến môi trường toàn cục để nhét `--add-opens` vào **mọi** Java process. Khi bắt buộc dùng launcher environment options, hãy scope theo job/process và có bước kiểm tra để tránh flag lan sang chương trình không liên quan.

## 11. Không nhầm `--add-opens` với các loại lỗi khác

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `trySetAccessible()` trả `false` cho private field trong named module khác | Package chưa mở tới caller | Xác định source module/package/caller rồi cân nhắc `opens` hoặc `--add-opens` |
| `setAccessible(true)` ném `InaccessibleObjectException` | Không thể vô hiệu hóa kiểm tra access theo module | Đọc thông báo `does not "opens"`, kiểm tra phạm vi cần mở |
| `Field.get` ném `IllegalAccessException` | Chưa có quyền dùng member | Kiểm tra mức truy cập, `canAccess` và trạng thái `trySetAccessible` |
| `NoSuchFieldException` hoặc `NoSuchMethodException` | Tên member hoặc chữ ký không khớp | Kiểm tra class, method signature, inherited/declared members |
| `IllegalArgumentException` khi `Field.get` | Receiver không đúng hoặc tham số không phù hợp | Kiểm tra kiểu instance; không mặc định thêm `--add-opens` |
| Compile lỗi vì import package không được export | Thiếu quyền truy cập compile-time, không phải deep reflection | Dùng public API; đánh giá `exports` hoặc `--add-exports` nếu thật sự cần |
| Đã thêm `--add-opens` mà vẫn thất bại | Sai module nguồn, package, caller, vị trí flag hoặc JVM thực thi | Log metadata và kiểm tra câu lệnh khởi động tiến trình thực |
| Warning về module đích không tồn tại | Target module chưa được giải quyết hoặc sai tên | Kiểm tra module path, module graph và tên chính xác |
| Lỗi truy cập internal JDK class sau nâng JDK | Strong encapsulation và phụ thuộc API không công bố | Ưu tiên API hỗ trợ; chỉ mở package cụ thể nếu là tích hợp đã xác định |

Lưu ý: `--add-opens` không tự sửa lỗi thiếu dependency, sai tên class, sai method descriptor, exception nghiệp vụ hay giới hạn được thiết kế riêng bởi framework. Nó chỉ thay đổi một phần quyền mở package trong JPMS.

## 12. Rủi ro, phương án thay thế và nguyên tắc vận hành

### 12.1. Tôn trọng ranh giới API

Ưu tiên sử dụng API public hoặc cơ chế extension hợp lệ thay cho deep reflection. Nếu framework cần truy cập dữ liệu riêng, xem xét:

- Public interface, accessor hoặc DTO được thiết kế cho nhu cầu tích hợp.
- SPI hoặc service provider được công bố bởi library.
- Serialization/ORM extension đã được tác giả library hỗ trợ.
- `opens ... to <framework-module>` trong module bạn sở hữu, thay vì flag toàn cục.

Không ép framework truy cập private field chỉ vì không muốn thiết kế một API chính thức. Member private không có cam kết tương thích mạnh như public API; nó có thể đổi tên, kiểu hoặc ý nghĩa giữa các phiên bản.

### 12.2. Dùng phạm vi nhỏ nhất

Một quyết định cấu hình có thể được ghi thành:

| Câu hỏi cần ghi nhận | Ví dụ |
| --- | --- |
| Vì sao cần deep reflection? | Module inspector đọc một field phục vụ kiểm tra tích hợp |
| Module nguồn? | `com.example.model` |
| Package cần mở? | `com.example.model.internal` |
| Caller named hay unnamed? | Named module `com.example.inspector` |
| Cấu hình tối thiểu? | `--add-opens=com.example.model/com.example.model.internal=com.example.inspector` |
| Kế hoạch loại bỏ? | Thay bằng public diagnostic API ở phiên bản kế tiếp |

Nếu caller là một named module rõ ràng, không thay thành `ALL-UNNAMED` cho tiện. Không dùng một danh sách các package `java.base` hay `jdk.*` lấy từ mạng rồi áp dụng hàng loạt cho mọi JVM.

### 12.3. Mở package không bảo đảm thay đổi private final state

Việc bật `setAccessible` chỉ liên quan tới quyền truy cập reflective. Nó không hủy các giới hạn riêng của ngôn ngữ/JVM đối với member `final`, record hoặc các API có invariant khác. Một ứng dụng đọc state private vẫn cần cân nhắc độ ổn định; sửa state private đặc biệt dễ gây bất biến sai và lỗi khó chẩn đoán.

### 12.4. Liên hệ đúng với Java 18 và JEP 416

JEP 416 đưa Core Reflection lên nền tảng Method Handles trong Java 18. Đây là thay đổi triển khai, không phải chỉ thị mở thêm mọi package. Các tích hợp dựa vào chi tiết reflection nội bộ không được công bố có thể lỗi khi nâng JDK; giải pháp lâu dài là dùng API hỗ trợ và hợp đồng JPMS chính thức, không cố quay về một implementation legacy.

Tương tự, `MethodHandles.privateLookupIn` phải tuân theo quy tắc module và package openness thích hợp. Đổi API gọi reflection không có nghĩa là tự động vượt qua strong encapsulation.

## 13. Checklist kiểm chứng và bài tập

Trước khi đưa `--add-opens` vào môi trường staging/production:

- [ ] Đã chứng minh đúng lỗi `trySetAccessible=false` hoặc `InaccessibleObjectException` do JPMS.
- [ ] Đã xác định class **khai báo** member bị truy cập.
- [ ] Đã ghi đúng tên named module nguồn và package nguồn.
- [ ] Đã xác định module **thực sự gọi** deep reflection; không đoán theo tên ứng dụng.
- [ ] Đã kiểm tra public API hoặc qualified `opens` là lựa chọn thay thế được hay không.
- [ ] Đã chọn target named module cụ thể hoặc `ALL-UNNAMED` đúng với cách nạp caller.
- [ ] Đã đặt flag lên **JVM thực thi**, không nhầm với JVM build/compile.
- [ ] Đã thử chạy đối chứng khi không có flag và khi có flag.
- [ ] Đã kiểm tra side effect, exception và hành vi truy cập trên JDK hỗ trợ.
- [ ] Đã ghi lại lý do, chủ sở hữu cấu hình và điều kiện có thể loại bỏ flag.

### Bài tập tự thực hành

1. Chạy ví dụ hai module ở phần 4 mà không thêm flag; ghi lại `openToCaller` và `trySetAccessible`.
2. Thêm đúng một flag `--add-opens`; quan sát giá trị thay đổi và private field có thể được đọc.
3. Thay package trong flag thành `com.example.model.api`; giải thích vì sao vẫn không truy cập được `InternalConfig`.
4. Bỏ flag và thêm `opens com.example.model.internal to com.example.inspector;` vào module nguồn; chạy lại.
5. Thay target bằng `ALL-UNNAMED` nhưng vẫn chạy inspector như named module; dự đoán kết quả.
6. Thử gọi `field.setAccessible(true)` thay vì `trySetAccessible()` trước khi mở package và xem exception.
7. Đặt flag **sau** tên main module/class rồi quan sát sự khác biệt so với vị trí trước `-m`.
8. Thêm một field mới, xác định `getDeclaringClass()` và giải thích vì sao cần dùng package của class khai báo member.
9. Thiết kế một API public thay cho nhu cầu đọc `diagnosticCode`; đánh giá khi nào có thể xóa flag.

## 14. Tài liệu tham khảo chính thức

- [The java Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp `--add-opens`, `--add-exports`, module path và module launcher.
- [Migrating from JDK 8 to Later JDK Releases — JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): strong encapsulation và cách sử dụng `--add-opens` trên JDK hiện hành.
- [AccessibleObject — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `setAccessible`, `canAccess`, trường hợp mở package và giới hạn final field.
- [InaccessibleObjectException — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): exception khi không thể vô hiệu hóa kiểm tra truy cập.
- [Module — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `getName`, `isNamed`, `isOpen` và quy tắc openness.
- [JLS 25, mục 7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html): ý nghĩa `exports`/`opens` và qualified opens.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): nền tảng strong encapsulation và lý do không dùng lại giải pháp nới lỏng legacy.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai Core Reflection từ Java 18, không phải thay đổi quyền truy cập.

**Ghi nhớ:** `--add-opens` có dạng `--add-opens=<module sở hữu class>/<package của class>=<module thực hiện reflection>`. Chỉ dùng khi đã xác định rõ nhu cầu tích hợp; với named caller hãy mở cho đúng tên module, còn `ALL-UNNAMED` chỉ dành cho caller classpath. Dùng `getDeclaringClass()`, `getModule()`, `getPackageName()` và `trySetAccessible()` để kiểm chứng trước và sau cấu hình. Ưu tiên public API hoặc qualified `opens` khi kiểm soát được thiết kế, và không mở hàng loạt package không liên quan.
