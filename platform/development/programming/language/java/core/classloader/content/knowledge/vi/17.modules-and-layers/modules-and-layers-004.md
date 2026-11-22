# Readability, exports và opens trong Java Module System

## 1. Ba khái niệm nhưng ba câu hỏi khác nhau

**Java Platform Module System (JPMS)**, xuất hiện từ Java 9, tổ chức những package thành **named module** với quan hệ phụ thuộc và mức độ đóng gói rõ ràng. Khi module A cần dùng code trong module B, phải phân biệt:

1. **Readability**: A có **đọc** (`reads`) B hay không? Quan hệ này thường xuất phát từ `requires B;` trong `module-info.java` của A.
2. **Exports**: B có **xuất package** chứa API cần dùng cho A không? Từ khóa `exports` cho phép access bình thường đến public/protected types và members theo các quy tắc access của Java, trong đó compile-time readability vẫn phải hợp lệ.
3. **Opens**: B có **mở package** cho A để dùng **deep reflection** ở runtime không? Từ khóa `opens` là công cụ dành cho framework/reflection truy cập constructor, method hoặc field vốn không public bằng các API như `setAccessible(true)`.

Ghi nhớ:

> `requires` trả lời **đọc module nào**; `exports` trả lời **package nào là API cho code thông thường**; `opens` trả lời **package nào cho phép reflection sâu**.

Ba cơ chế **không thay thế lẫn nhau**. Có quyền đọc module không đồng nghĩa có quyền import mọi package nội bộ. Có `exports` không đồng nghĩa có quyền lấy field private bằng deep reflection. Có `opens` không đồng nghĩa có `exports` tại thời điểm biên dịch.

Ví dụ:

~~~java
// module-info.java của thư viện
module com.example.lib {
    exports com.example.lib.api;
    opens com.example.lib.internal to com.example.app;
}
~~~

~~~java
// module-info.java của ứng dụng
module com.example.app {
    requires com.example.lib;
}
~~~

Ứng dụng đọc lib; package `com.example.lib.api` được dùng qua import thông thường; package `com.example.lib.internal` không export nhưng cho `com.example.app` reflect sâu. Một package khác không export và không open vẫn bị đóng với app.

## 2. Readability: quan hệ giữa những module

Trong JPMS, module graph được resolver xây dựng từ các named modules có thể quan sát và các chỉ thị module. Cạnh **readability** có hướng:

~~~text
+---------------------+      requires       +-----------------------+
|   com.example.app   | ------------------> |   com.example.lib     |
|     consumer        |        reads        |      provider         |
+---------------------+                     +-----------------------+
~~~

`requires com.example.lib;` nằm trong descriptor của **consumer**, không phải của lib. Nó tạo quan hệ app reads lib khi modules được resolve đúng. Chiều ngược lại không tự xuất hiện.

Mọi named module luôn đọc chính nó và có readability thích hợp tới `java.base` mà không cần khai báo `requires java.base;`. Tuy nhiên một module đọc được B **không** tự nhìn thấy mọi class/package trong B: còn phải xét exports/opens và Java accessibility.

### Các dạng requires

| Chỉ thị | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `requires lib;` | Module hiện tại đọc lib. | App dùng API lib trực tiếp. |
| `requires transitive lib;` | Module hiện tại đọc lib; các module đọc module hiện tại được bổ sung readability tới lib theo quy tắc JPMS. | API facade công khai types đến từ lib. |
| `requires static lib;` | Phụ thuộc trong giai đoạn compile, không bắt buộc module đó hiện diện lúc chạy chỉ vì chỉ thị này. | Optional integration, annotation/compile-only API. |

Ví dụ:

~~~text
module app    { requires facade; }
module facade { requires transitive model; }
module model  { exports model.api; }
~~~

Trong graph đã resolve đúng, app đọc cả facade và model thông qua `requires transitive`. Nhưng việc **đọc** model không tự biến các package không export của model thành public API.

Đừng nhầm “JAR đặt trên module path” với “module đã có trong graph và có read edge”. Việc module được resolve còn phụ thuộc launcher/root modules và module resolver. Thư viện đặt trên **classpath** thông thường thuộc unnamed module, khác named module trên module path.

### Xem readability qua API

~~~java
Module app = Main.class.getModule();
Module lib = Greeting.class.getModule();
boolean reads = app.canRead(lib);
~~~

Đây chỉ là các biểu thức Java minh họa bên trong code có class tương ứng. `canRead` trả quan hệ đọc ở runtime, **không** cho biết package nào được export/open. API `addReads` có thể thêm read edge động với các điều kiện caller thích hợp; không nên coi nó là phương án thay thế descriptor đúng trong production.

## 3. Exports: bề mặt API được dùng bình thường

Ở provider:

~~~java
module com.example.lib {
    exports com.example.lib.api;
}
~~~

Ở consumer:

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

Nếu `Greeting` trong `com.example.lib.api` là `public class` và phương thức `hello()` là public, app có thể:

~~~java
import com.example.lib.api.Greeting;

// Trong một method Java hợp lệ:
String text = Greeting.hello();
~~~

**Lưu ý:** những đoạn trên mang tính minh họa, mỗi `module-info.java` nằm trong module của riêng nó; không phải một file Java duy nhất.

`exports` có tác dụng ở **mức package**. Nếu package được export, các public types trong đó trở thành phần bề mặt API theo Java access rules. `protected` vẫn phải tuân thủ điều kiện kế thừa/truy cập, không phải bất cứ code nào cũng truy cập được mọi protected member.

### Qualified exports

Bạn có thể export có chọn lọc:

~~~java
module com.example.lib {
    exports com.example.lib.spi to com.example.app, com.example.tools;
}
~~~

Chỉ những module được chỉ định nhận quyền export khi thỏa các điều kiện còn lại. Dạng `exports p;` là **unqualified**, còn `exports p to A, B;` là **qualified**.

### Tại sao class public trong package ẩn vẫn bị chặn?

~~~java
package com.example.lib.hidden;

public class Hidden {}
~~~

Nếu module lib **không exports** `com.example.lib.hidden`, `Hidden` vẫn không được import bình thường từ named module khác chỉ vì nó được khai báo public. Module boundary bổ sung một tầng encapsulation ngoài Java modifiers truyền thống.

Compiler có thể báo package không visible/not exported khi consumer cố import. Kiểm tra **hai điều kiện riêng**: consumer có `requires` phù hợp chưa và provider có `exports` package đó cho consumer chưa.

## 4. Opens: cấp quyền deep reflection lúc chạy

Từ khóa `opens` cấp khả năng truy cập sâu bằng reflection cho các module được phép:

~~~java
module com.example.lib {
    opens com.example.lib.internal;
}
~~~

Dạng trên mở cho mọi module phù hợp. Nếu chỉ một framework/app cần truy cập:

~~~java
module com.example.lib {
    opens com.example.lib.internal to com.example.app;
}
~~~

Đây là **qualified opens**: package được mở cho `com.example.app`, không phải mọi module.

### Opens không phải compile-time exports

Nếu lib chỉ `opens com.example.lib.internal to com.example.app;` mà **không exports**, code trong app không thể dùng cú pháp import trực tiếp class từ `internal` một cách bình thường tại compile time:

~~~java
// PHẢN VÍ DỤ: import không hợp lệ nếu package chỉ opens mà không exports
import com.example.lib.internal.Secret;
~~~

Nhưng code app có thể tìm class theo tên và reflect sâu vào thành viên private nếu package mở cho caller:

~~~java
Class<?> type = Class.forName("com.example.lib.internal.Secret");
var ctor = type.getDeclaredConstructor();
ctor.setAccessible(true);
Object value = ctor.newInstance();

var field = type.getDeclaredField("value");
field.setAccessible(true);
Object text = field.get(value);
~~~

Đây là đoạn minh họa nằm trong method có thể ném reflection exceptions. Tại sao đặt `ctor.setAccessible(true)`? Vì package không export tại compile time; một public constructor của class trong package không export không tự trở thành lời gọi truy cập thông thường hợp lệ từ module khác. Deep reflection được cấp bởi opens xử lý tình huống đó.

Nếu package chưa open cho module của code gọi `setAccessible(true)`, Java có thể ném `java.lang.reflect.InaccessibleObjectException`. Lời gọi `getDeclaredField(...)` có thể lấy metadata nhưng bước **vượt qua access checks** không tự hợp lệ.

### Exports có đủ để dùng private reflection không?

**Không.** Package `exports p;` cho phép sử dụng public API theo Java access rules, không cấp vô điều kiện quyền truy cập private fields/constructors bằng `setAccessible(true)` từ module khác. Framework serialization, ORM, DI hoặc thư viện JSON có thể cần `opens p to framework.module;`, hoặc cần được thiết kế lại để dùng public factory/getters.

### Một tinh tế trong Module.isExported

API runtime `Module.isExported(packageName, otherModule)` xem package **open cho otherModule** là **exported tại runtime** cho module đó. Do vậy:

- Descriptor chỉ khai báo `opens p to A;`.
- `lib.isOpen("p", A)` là `true`.
- `lib.isExported("p", A)` **cũng có thể là `true` ở runtime**.
- Nhưng **không có** chỉ thị `exports p;` trong module descriptor, nên compiler không coi package đó là exported cho code trực tiếp.

Muốn xác nhận **exports được khai báo thật**, dùng `lib.getDescriptor().exports()` trên named module có descriptor. Tránh chỉ nhìn `isExported` rồi suy ngược rằng `module-info.java` phải chứa một câu lệnh exports.

## 5. Bảng so sánh readability, exports và opens

| Thuộc tính | Readability | Exports | Opens |
| --- | --- | --- | --- |
| Đơn vị | Cạnh **module → module** | Package trong provider | Package trong provider |
| Khai báo thông thường | `requires B;` ở consumer | `exports p;` ở provider | `opens p;` ở provider |
| Có bản chọn lọc | `requires transitive` hoặc graph dynamic; không có `requires ... to ...` | `exports p to A;` | `opens p to A;` |
| Cho import public type ở compile time? | **Cần nhưng chưa đủ** | **Có**, với read edge và Java access rules | **Không**, nếu chỉ opens |
| Public access runtime | Read edge là một yếu tố | Có theo quy tắc | Opened package được coi là exported runtime cho module nhận |
| Cho deep reflection vào private | Không | Không | Có, khi opened đúng module và các điều kiện reflection khác phù hợp |
| API hỏi trạng thái | `caller.canRead(provider)` | `provider.isExported(p,caller)` | `provider.isOpen(p,caller)` |
| Lỗi điển hình | Module/package không visible | Package không exported | `InaccessibleObjectException` khi `setAccessible(true)` |

Trong một chương trình, **readability + package access + Java member access** phối hợp với nhau. Không dùng một trong ba cột để kết luận thay cho tất cả cột còn lại.

## 6. Ví dụ Java 17+ độc lập gồm hai named modules

Bài này xây hai module thực sự thay vì giả lập bằng classpath:

- `com.example.lib` có package public API được export, package internal được mở **chỉ cho app**, và package hidden không export/open.
- `com.example.app` khai báo `requires com.example.lib;`, gọi API public, thử đọc private field trong internal, rồi chứng minh hidden bị chặn.
- Module layer và module descriptor được quan sát trực tiếp.

### Cấu trúc

~~~text
example/
└── src/
    ├── com.example.lib/
    │   ├── module-info.java
    │   └── com/example/lib/
    │       ├── api/Greeting.java
    │       ├── internal/Secret.java
    │       └── hidden/Hidden.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

### File `src/com.example.lib/module-info.java`

~~~java
module com.example.lib {
    exports com.example.lib.api;
    opens com.example.lib.internal to com.example.app;
}
~~~

### File `src/com.example.lib/com/example/lib/api/Greeting.java`

~~~java
package com.example.lib.api;

public class Greeting {
    public static String hello() {
        return "Hello from exported API";
    }
}
~~~

### File `src/com.example.lib/com/example/lib/internal/Secret.java`

~~~java
package com.example.lib.internal;

public class Secret {
    private String value = "opened-secret";
}
~~~

### File `src/com.example.lib/com/example/lib/hidden/Hidden.java`

~~~java
package com.example.lib.hidden;

public class Hidden {
    private String value = "hidden-secret";
}
~~~

Hai class `Secret` và `Hidden` đều public, nhưng package của chúng không export; chỉ `internal` được mở có chọn lọc.

### File `src/com.example.app/module-info.java`

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

### File `src/com.example.app/com/example/app/Main.java`

~~~java
package com.example.app;

import com.example.lib.api.Greeting;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Main {
    private static String readPrivate(String name) throws Exception {
        Class<?> type = Class.forName(name);

        Constructor<?> constructor = type.getDeclaredConstructor();
        constructor.setAccessible(true);
        Object instance = constructor.newInstance();

        Field field = type.getDeclaredField("value");
        field.setAccessible(true);
        return (String) field.get(instance);
    }

    public static void main(String[] args) throws Exception {
        Module app = Main.class.getModule();
        Module lib = Greeting.class.getModule();

        System.out.println("app reads lib: " + app.canRead(lib));
        System.out.println("api exported to app: "
                + lib.isExported("com.example.lib.api", app));

        System.out.println("internal explicitly exported: "
                + lib.getDescriptor().exports().stream()
                    .anyMatch(e ->
                            e.source().equals("com.example.lib.internal")));

        System.out.println("internal opened to app: "
                + lib.isOpen("com.example.lib.internal", app));
        System.out.println("internal unqualified open: "
                + lib.isOpen("com.example.lib.internal"));
        System.out.println("hidden opened to app: "
                + lib.isOpen("com.example.lib.hidden", app));

        System.out.println("api: " + Greeting.hello());
        System.out.println("internal private: "
                + readPrivate("com.example.lib.internal.Secret"));

        try {
            readPrivate("com.example.lib.hidden.Hidden");
            System.out.println("hidden unexpected success");
        } catch (java.lang.reflect.InaccessibleObjectException expected) {
            System.out.println("hidden private: blocked");
        }

        System.out.println("app layer is boot: "
                + (app.getLayer() == ModuleLayer.boot()));
        System.out.println("lib in same layer: "
                + (lib.getLayer() == app.getLayer()));
    }
}
~~~

### Compile và chạy trên Linux/macOS

Đứng trong thư mục `example`:

~~~bash
mkdir -p out
javac --release 17 --module-source-path src -d out \
  $(find src -name '*.java')

java --module-path out \
  --module com.example.app/com.example.app.Main
~~~

### Compile và chạy trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
$sources = @(Get-ChildItem -Path src -Filter *.java -Recurse |
    ForEach-Object { $_.FullName })

javac --release 17 --module-source-path src -d out $sources
java --module-path out --module com.example.app/com.example.app.Main
~~~

`--module-source-path src` lấy các module từ các thư mục `src/<module-name>/`; `-d out` đưa chúng vào output modular tương ứng. Dùng `--module-path out` và `--module com.example.app/com.example.app.Main` lúc chạy để JPMS thực sự resolve named modules, thay vì nạp nhầm như classpath/unnamed module.

### Stdout đã kiểm chứng (OpenJDK 21, source tương thích Java 17)

~~~text
app reads lib: true
api exported to app: true
internal explicitly exported: false
internal opened to app: true
internal unqualified open: false
hidden opened to app: false
api: Hello from exported API
internal private: opened-secret
hidden private: blocked
app layer is boot: true
lib in same layer: true
~~~

Ý nghĩa các dòng:

1. `app reads lib: true`: chỉ thị `requires` có hiệu lực.
2. `api exported to app: true`: provider exports API.
3. `internal explicitly exported: false`: descriptor không có `exports` dành cho internal; nó **chỉ opens**.
4. `internal opened to app: true`: qualified opens nhắm đúng consumer.
5. `internal unqualified open: false`: internal **không** mở cho mọi module.
6. `hidden opened to app: false`: hidden chưa được phép deep reflection.
7. `api: Hello from exported API`: public API dùng được bình thường.
8. `internal private: opened-secret`: deep reflection vào private field thành công nhờ opens.
9. `hidden private: blocked`: `setAccessible(true)` gặp `InaccessibleObjectException` vì package đóng.
10. Hai dòng layer bằng `true`: trong ví dụ launcher, cả app và lib nằm ở **boot module layer**.

**Chú ý:** ví dụ cần cả `constructor.setAccessible(true)` và `field.setAccessible(true)`. Mã không giả định rằng class public trong package opened-only tự có constructor public có thể được gọi trực tiếp qua access thông thường.

## 7. Readability không tự động exports; exports không tự động readability

Điều kiện access thông thường giữa named modules được nhìn theo tầng:

~~~text
A reads B
   +
B exports package p to A
   +
Java type/member accessibility
   =
A có thể tham chiếu API trong p theo quy tắc bình thường
~~~

A khai báo `requires B;` nhưng B không export `p.internal`? A không thể import công khai các kiểu trong p.internal chỉ bằng read edge.

Ngược lại, B có `exports p.api;` nhưng A không đọc B? Một chỉ thị exports của B không tự bổ sung `requires B;` cho A. Sự khác nhau càng quan trọng khi chuyển code cũ từ classpath sang module path.

Reflection có một số quy tắc runtime và API tìm lớp riêng; `Class.forName` có thể tìm một đối tượng `Class<?>` ngay cả khi import compile-time không hợp lệ, nhưng điều đó **không chứng minh** bạn được phép gọi mọi constructor/method hay đọc field private. Thử access theo API/runtime policy cụ thể.

## 8. Qualified opens, open module, automatic và unnamed module

### Qualified và unqualified

~~~java
module lib {
    exports lib.api to consumer;
    opens lib.internal to framework.core;
}
~~~

Chỉ consumer nhận export của `lib.api`, chỉ framework.core nhận deep reflection của `lib.internal`. Với nhiều module được cấp quyền, tách tên bằng dấu phẩy.

### Open module

~~~java
open module lib {
    exports lib.api;
}
~~~

`open module` cho deep reflection trên tất cả package của module theo quy tắc runtime, nhưng **không tự exports tất cả package để import compile time**. Những package là API dùng bình thường vẫn cần exports nếu có consumer. Trong một open module, không khai báo `opens p;` riêng vì đã mở toàn bộ.

### Automatic module

Một JAR phù hợp được đặt trên module path mà không có descriptor có thể được resolver xem như **automatic module**. Loại module này có những quy tắc tương thích rộng về readability và việc export/open package. Nó hữu ích trong quá trình chuyển đổi nhưng không nên là lý do bỏ thiết kế ranh giới rõ ràng cho named modules lâu dài.

### Unnamed module

Các class trên classpath thông thường nằm trong **unnamed module** tương ứng loader. Unnamed module đọc các module khác và coi package của chính mình được export/open; nhưng named module không thể đơn giản viết `requires unnamed;` để đọc ngược unnamed module. Đây là lý do thiết kế mới nên ưu tiên ranh giới module rõ ràng.

## 9. ModuleLayer và ClassLoader là hai tầng khác nhau

Trong hệ thống nhiều plugin, người học dễ đánh đồng **module** với **class loader**:

- **ClassLoader** tìm hoặc định nghĩa class theo binary name và delegation policy.
- **Module resolution/readability** quyết định named module nào có mặt trong graph và ai đọc ai.
- **Exports/opens** quyết định quyền dùng package theo loại truy cập.
- **ModuleLayer** nhóm những resolved modules vào một layer, có quan hệ với parent layers và mapping tới class loaders.

**Một loader có thể gắn với nhiều module.** Cùng class loader không có nghĩa module A và B tự đọc nhau, cũng không có nghĩa package internal của B tự mở cho A. Ngược lại, hai class loader khác nhau không tự tạo một ModuleLayer mới.

Ví dụ API quan sát runtime:

~~~java
Module current = Main.class.getModule();
Module library = Greeting.class.getModule();

System.out.println(current.canRead(library));
System.out.println(library.isExported("com.example.lib.api", current));
System.out.println(library.isOpen("com.example.lib.internal", current));
System.out.println(current.getLayer());
System.out.println(Greeting.class.getClassLoader());
~~~

Đây là đoạn minh họa, không phải chương trình đầy đủ. `getDescriptor()` có thể là `null` đối với unnamed module; `getLayer()` có thể là `null` trong các ngữ cảnh không thuộc layer. Trong ví dụ boot-layer, hai module cùng layer nhưng mỗi package vẫn tuân access rules riêng.

Nếu muốn plugin ở layer mới, phải dùng API module resolution và tạo layer phù hợp. Chỉ tạo `new URLClassLoader(urls, parent)` không tự resolve module-info thành graph named modules theo ý bạn.

## 10. Tham số launcher: --add-reads, --add-exports, --add-opens

Khi tích hợp thư viện cũ hoặc chẩn đoán, Java launcher có các tùy chọn mở rộng graph/access tại runtime:

~~~text
--add-reads consumer=provider
--add-exports provider/package.name=consumer
--add-opens provider/package.name=consumer
~~~

Đây là **mẫu cú pháp**, thay tên module và package theo trường hợp thực tế.

| Tùy chọn | Công dụng chính | Không tự làm |
| --- | --- | --- |
| `--add-reads A=B` | Bổ sung cạnh readability từ A tới B ở runtime | Không export hay open package của B. |
| `--add-exports B/p=A` | Cấp export của package p từ B cho A ở runtime | Không cho reflection vào private members như opens. |
| `--add-opens B/p=A` | Cho phép deep reflection của A vào package p của B ở runtime | Không thêm chỉ thị exports compile-time vào descriptor. |

Với bài chạy ở phần 6, có thể cố tình mở package hidden cho app bằng:

~~~bash
java --module-path out \
  --add-opens com.example.lib/com.example.lib.hidden=com.example.app \
  --module com.example.app/com.example.app.Main
~~~

Lệnh này **thay điều kiện phép thử**: reflection vào Hidden có thể thành công và code sẽ in dòng `hidden unexpected success` vì không đi vào nhánh catch. Đây là một minh họa về tác động của override runtime, không phải kết quả baseline.

Một số cú pháp chấp nhận đích đặc biệt `ALL-UNNAMED` để cấp quyền cho code classpath. Phạm vi có thể rất rộng, cần đánh giá ảnh hưởng trước khi dùng. Với ứng dụng dài hạn, ưu tiên descriptor đúng hoặc kiến trúc API phù hợp thay vì dựa mãi vào các cờ mở package nội bộ.

API runtime như `Module.addReads`, `addExports`, `addOpens` có các quy tắc kiểm tra module gọi và quyền đã có; không được giả định một module bất kỳ có thể chỉnh mọi module khác tùy ý.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Compiler không thấy một module | Module chưa resolve hoặc consumer thiếu requires. | Xem module-info.java và module path. |
| Compiler báo package không visible | Provider không exports package cho consumer. | Thêm exports có chọn lọc nếu package đó thực sự là API. |
| Runtime IllegalAccessError | Điều kiện access/linkage không còn đúng với graph và version runtime. | So sánh module descriptors, runtime module path và override flags. |
| `InaccessibleObjectException` khi `setAccessible(true)` | Package chưa opens cho caller module. | Dùng public API hoặc qualified opens phù hợp. |
| Class public đã tìm thấy nhưng constructor bị từ chối | Package không export/open đúng, hoặc member không accessible. | Kiểm tra package access và setAccessible theo hợp đồng. |
| Chạy được chỉ khi có `--add-opens` | Config runtime đang mở package tạm thời. | Thiết kế module-info hoặc bỏ nhu cầu deep reflection. |
| `isExported(p,A)` là true dù descriptor không exports | Package opens cho A nên được xem là exported runtime. | Kiểm tra `isOpen` và `getDescriptor().exports()`. |
| Đã có `requires transitive` nhưng vẫn import lỗi | Package phía module transitive chưa được exports. | Xem cả readability lẫn exports. |
| Chỉ thêm JAR vào module path vẫn không tìm class | Module chưa resolve, hoặc nhầm classpath/module path. | Kiểm tra launcher flags và resolution roots. |
| Hai module dùng cùng ClassLoader nhưng reflect private thất bại | Loader chung không tự cho quyền opens. | Kiểm tra module identity, layer và package opens. |

### Checklist chẩn đoán

1. Lớp thuộc module nào? Dùng `clazz.getModule()` và `isNamed()`.
2. Consumer có đọc provider? `consumer.canRead(provider)`.
3. Provider có exports package cho consumer? `provider.isExported(p,consumer)` và **descriptor exports** nếu hỏi compile-time.
4. Code có cần deep reflection private? `provider.isOpen(p,consumer)`.
5. `opens`/`exports` có `to moduleName` không? Tên module thực của caller là gì?
6. Lệnh chạy có `--module-path` và `--module` phù hợp? Có dùng `--add-*` không?
7. Lớp nằm ở layer và class loader nào? Không suy modules chỉ từ classpath tên file.
8. Bạn có đang trộn API bình thường với reflective access trong cùng một khẳng định không?

## 12. Câu hỏi ôn tập

**Câu 1.** A khai báo `requires B;` nhưng B không exports package `b.internal`. A có thể import public class trong `b.internal` không?

**Đáp:** Không. Readability không tương đương package exports.

**Câu 2.** B `exports b.api;` cho A. Có thể tự `setAccessible(true)` vào private field bên b.api từ A không?

**Đáp:** Không chỉ vì exports. Deep reflection cần opens/điều kiện reflection phù hợp.

**Câu 3.** B `opens b.internal to A;` nhưng không exports. A có thể import class trực tiếp không?

**Đáp:** Không tại compile time. Nhưng deep reflection từ A có thể thành công ở runtime.

**Câu 4.** Vì sao `isExported("b.internal", A)` có thể true dù descriptor không có exports?

**Đáp:** API Module coi package opened to A là runtime-exported tới A. Dùng descriptor exports để xác định khai báo compile-time.

**Câu 5.** Cùng ClassLoader có khiến hai named modules truy cập private fields của nhau không?

**Đáp:** Không. Class loader identity khác module access; opens vẫn phải đáp ứng quy tắc JPMS.

## Tài liệu chuẩn

- [JLS Java SE 21 §7.7 – Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): requires/readability, exports, opens và transitive.
- [JLS Java SE 21 §7.7.2 – Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.2): compile-time vs runtime access và deep reflection.
- [Java SE 21 java.lang.Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): canRead, isExported, isOpen, descriptor, layer.
- [Java SE 21 ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): layer và mapping class loader.
- [Java SE 21 java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): module path và các cờ add-reads/add-exports/add-opens.
