# Khả năng đọc mô-đun, quyền truy cập package và split package trong Java

**Java Platform Module System (JPMS)** được giới thiệu từ Java 9 để mô tả phụ thuộc giữa các **named modules**, kiểm soát package nào là API công khai, và ngăn ứng dụng vô tình phụ thuộc những phần implementation chưa được mở. Khi biên dịch mã Java 17 bằng `javac`, muốn truy cập một lớp từ module khác, việc lớp ấy có `public` vẫn **chưa đủ**: phải xét đồng thời quan hệ **readability**, quyền **exports** của package và quyền truy cập Java thông thường.

Một tình huống khác rất hay xuất hiện khi chuyển dự án từ classpath sang module path là **split package**: hai nguồn module cùng chứa những lớp thuộc cùng tên package. JPMS thiết kế resolution và class loading để tránh những tình huống nhập nhằng nguy hiểm này. Bài học giải thích ba vấn đề dưới cùng một góc nhìn: **module nào nhìn thấy module nào, package nào được tiếp cận, và vì sao package trùng tên có thể phá quá trình biên dịch/khởi động**.

## 1. Mô hình cần nhớ: module, package, type và lời gọi

Mỗi named module được mô tả bởi `module-info.java`:

```java
module com.example.app {
    requires com.example.lib;
}
```

Mỗi package chứa các compilation units khai báo `package ...;`. Một module thường chứa nhiều package, nhưng một package không tự động trở thành public API chỉ vì có một `public class` bên trong.

Có thể hình dung kiểm tra truy cập theo ba lớp:

1. **Readability:** Module A có *reads* module B hay không? Thường khai báo `requires B;`, hoặc nhận readability qua `requires transitive`.
2. **Package export:** Module B có **exports** package chứa kiểu cần sử dụng tới A hay không? Có thể export cho mọi module hoặc một số module cụ thể.
3. **Java access control:** Type/method/field có modifier `public`, `protected`, package-private hoặc `private` phù hợp với ngữ cảnh truy cập không?

Cả ba điều kiện đều quan trọng khi **truy cập tĩnh theo Java source**. Các quy tắc cho reflection sâu còn liên quan **opens** và sẽ được trình bày riêng.

### Bảng kết hợp nhanh

| A reads B | B exports package p cho A | Type `p.T` public | A có thể dùng `p.T` trong source? |
| --- | --- | --- | --- |
| Không | Có | Có | **Không**: thiếu readability |
| Có | Không | Có | **Không**: package bị encapsulate |
| Có | Có | Không (top-level package-private) | **Không**: Java access control vẫn áp dụng |
| Có | Có | Có | **Có**, nếu thành viên đang truy cập cũng đủ visibility |
| Có | Qualified export chỉ tới module C, còn A khác C | Có | **Không**: export không dành cho A |

`exports` **không có nghĩa “mọi class trong package đều thành public”**. Nó chỉ cho phép truy cập những types và members đủ mức visibility theo các quy tắc Java thông thường. Một method `private` không tự trở thành callable chỉ vì package được export.

## 2. Readability: `requires` là cạnh trong đồ thị module

Khai báo:

```java
module com.example.app {
    requires com.example.lib;
}
```

có ý nghĩa: `com.example.app` **đọc** `com.example.lib`. Ở compile time, `javac` phải tìm được module phụ thuộc trong module graph phù hợp, thường qua `--module-path` hoặc `--module-source-path`; ở runtime, launcher/module resolver cũng phải resolve dependency phù hợp.

**Readability có hướng:** A reads B không có nghĩa B reads A. Readability cũng **không tự bắc cầu qua `requires` thông thường**.

Giả sử:

```text
A --requires--> B --requires--> C
```

A đọc B; B đọc C; **A chưa tự động đọc C** chỉ vì tồn tại đường đi qua B. Nếu A cần trực tiếp dùng API từ C, A phải có cạnh đọc hợp lệ tới C, hoặc B phải công bố phụ thuộc C qua `requires transitive C;`.

Mọi named module **ngầm đọc `java.base`** (trừ cách diễn giải đặc biệt của chính `java.base`), nên mã có thể dùng `String` và `Object` mà không cần viết `requires java.base;`. Một module còn đọc chính nó.

### `requires transitive`: công bố một phụ thuộc thành một phần API

```java
module com.example.facade {
    requires transitive com.example.lib;
}
```

Nếu A reads `com.example.facade`, thì A cũng reads `com.example.lib` nhờ yêu cầu transitive của facade. Chú ý:

- Đây là **mở rộng quan hệ đọc**, không tự động export package của library.
- Library vẫn phải `exports` package tương ứng để A sử dụng public types.
- Khi một API public trả về hoặc nhận tham số có type từ module phụ thuộc, `requires transitive` thường diễn tả quan hệ API chính xác hơn `requires` thường.

Ví dụ đồ thị:

```text
com.example.app --requires--> com.example.facade
com.example.facade --requires transitive--> com.example.lib

=> app reads facade và reads lib
```

Không có `requires transitive` ở facade, app chỉ được đảm bảo đọc facade. Cách sửa khi app trực tiếp import API library là **thêm `requires com.example.lib` ở app** hoặc, nếu thực sự là phụ thuộc được facade xuất hiện trong API, đổi thành `requires transitive` tại facade.

### `requires static`: phụ thuộc bắt buộc lúc compile, tùy chọn lúc runtime

```java
module com.example.client {
    requires static com.example.annotations;
}
```

`requires static` thể hiện dependency cần quan sát lúc biên dịch nhưng **có thể không có ở runtime**. Nó phù hợp với một số annotation API hoặc thư viện chỉ được dùng trong quá trình build, nhưng không thể suy ra rằng “mọi lời gọi tới nó sẽ chạy được nếu JAR vắng mặt”. Nếu code runtime cần tải lớp/thực hiện method thuộc module tùy chọn, thiếu module thực sự vẫn có thể gây lỗi khi class linking/loading hoặc thực thi.

`requires transitive static` cũng là modifier combination có ý nghĩa riêng trong hệ thống module; khi gặp nó cần kiểm tra chính xác hợp đồng compile-time/runtime và cách dependency được resolve, thay vì coi nó hoàn toàn tương đương `requires transitive`.

## 3. `exports`: package nào là public API của module?

Module thư viện:

```java
module com.example.lib {
    exports com.example.api;
}
```

Khai báo này export package `com.example.api` cho mọi module khác **có quyền đọc `com.example.lib`**. Nếu thư viện còn package `com.example.internal` nhưng không export, bên ngoài sẽ **không** có quyền gọi tĩnh `com.example.internal.Hidden`, kể cả khi `Hidden` là `public`.

Ví dụ:

```text
com.example.lib
├── module-info.java       // exports com.example.api;
├── com/example/api/Greeting.java
└── com/example/internal/Secret.java
```

| Tên type | Điều kiện package/module | Có thể truy cập từ app đọc lib? |
| --- | --- | --- |
| `com.example.api.Greeting` public | Package được export, module được đọc | Có |
| `com.example.api.Helper` package-private | Package được export, module được đọc | Không, vẫn package-private |
| `com.example.internal.Secret` public | Package không được export | Không trong truy cập tĩnh thông thường |

**Concealed package** là cách gọi package không được export cho module gọi đến. Encapsulation cho phép thay đổi cách cài đặt bên trong mà không cam kết API nguồn cho bên ngoài. `requires` chỉ là cạnh phụ thuộc; nó không thể “mở khóa” toàn bộ các package concealed.

### Qualified exports: chỉ cho phép một số module cụ thể

```java
module com.example.lib {
    exports com.example.api;
    exports com.example.spi to com.example.adapter;
}
```

Ở đây `com.example.api` được export rộng, còn `com.example.spi` chỉ được export **có điều kiện** cho named module `com.example.adapter`. Module `com.example.app` có `requires com.example.lib;` vẫn **không** được truy cập tĩnh `com.example.spi` nếu không nằm trong danh sách được phép.

Qualified exports hữu ích khi một package cần cho module tích hợp cụ thể nhưng chưa muốn thành API rộng. Tuy nhiên, nó tạo coupling qua **tên module** trong descriptor; thay module name sẽ cần xem lại các `to ...` liên quan.

**Đừng nhầm module name và package name.** `module com.example.lib` là một định danh; package `com.example.api` là một namespace riêng. Chúng có thể có tiền tố giống nhau theo quy ước, nhưng không bị bắt buộc phải trùng.

## 4. Ví dụ Java 17 chạy đầy đủ: `requires transitive` cộng `exports`

Ví dụ gồm ba named modules trong một cây source. Đây là một chương trình hoàn chỉnh, không cần dependency bên ngoài JDK.

```text
project/
└── src/
    ├── com.example.lib/
    │   ├── module-info.java
    │   └── com/example/api/Greeting.java
    ├── com.example.facade/
    │   ├── module-info.java
    │   └── com/example/facade/Facade.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
```

**`src/com.example.lib/module-info.java`:**

```java
module com.example.lib {
    exports com.example.api;
}
```

**`src/com.example.lib/com/example/api/Greeting.java`:**

```java
package com.example.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "from library";
    }
}
```

**`src/com.example.facade/module-info.java`:**

```java
module com.example.facade {
    requires transitive com.example.lib;
    exports com.example.facade;
}
```

**`src/com.example.facade/com/example/facade/Facade.java`:**

```java
package com.example.facade;

import com.example.api.Greeting;

public final class Facade {
    private Facade() {
    }

    public static String message() {
        return "facade -> " + Greeting.message();
    }
}
```

**`src/com.example.app/module-info.java`:**

```java
module com.example.app {
    requires com.example.facade;
}
```

**`src/com.example.app/com/example/app/Main.java`:**

```java
package com.example.app;

import com.example.api.Greeting;
import com.example.facade.Facade;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
        System.out.println(Facade.message());
    }
}
```

Đứng tại thư mục `project`, dùng JDK có thể biên dịch Java 17:

```sh
javac --release 17 -encoding UTF-8 -d mods --module-source-path src -m com.example.lib,com.example.facade,com.example.app
java --module-path mods -m com.example.app/com.example.app.Main
```

**Stdout chính xác:**

```text
from library
facade -> from library
```

Đầu ra là các module đã biên dịch:

```text
mods/
├── com.example.lib/
│   ├── module-info.class
│   └── com/example/api/Greeting.class
├── com.example.facade/
│   ├── module-info.class
│   └── com/example/facade/Facade.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

Vì sao `Main` import trực tiếp `Greeting` dù `com.example.app/module-info.java` **chỉ có `requires com.example.facade`**? Bởi facade đã viết `requires transitive com.example.lib;`, khiến app đọc luôn lib. Đồng thời lib export `com.example.api`, giúp public type `Greeting` truy cập được.

Có thể kiểm tra descriptor đã biên dịch:

```sh
java --module-path mods --describe-module com.example.facade
javap -v mods/com.example.facade/module-info.class
```

`java --describe-module` cho biết khai báo module ở dạng dễ đọc; `javap -v` đi sâu vào `Module` attribute của class file `module-info.class`. Dạng trình bày chi tiết sẽ tùy bản JDK; đừng dùng toàn bộ stdout help hay constant-pool offsets làm tiêu chí kiểm thử.

### Negative test 1: đổi `requires transitive` thành `requires`

Sửa riêng `src/com.example.facade/module-info.java`:

```java
module com.example.facade {
    requires com.example.lib;
    exports com.example.facade;
}
```

Giữ nguyên app, biên dịch lại các module. `Main` nhập trực tiếp `com.example.api.Greeting` nhưng app không còn được truyền quyền **read** lib qua facade. Trình biên dịch báo lỗi liên quan module `com.example.lib` không được app đọc hoặc package không hiển thị. Dòng lỗi chính xác khác nhau theo JDK; **đây là ví dụ cố ý biên dịch thất bại**. Có hai phương án sửa:

- Nếu facade thực sự phơi bày API lib như một phần hợp đồng công khai, khôi phục `requires transitive com.example.lib;`.
- Nếu app tự chủ động phụ thuộc library, thêm `requires com.example.lib;` vào descriptor app.

### Negative test 2: giữ readability nhưng bỏ `exports`

Khôi phục `requires transitive` ở facade, rồi đổi `module-info.java` của library thành:

```java
module com.example.lib {
}
```

App giờ **đọc** lib nhưng package `com.example.api` không còn được export, nên `Main` và `Facade` không được dùng `Greeting` như API bình thường. Đây cũng là **negative test**, không phải code dùng chạy thành công. Thêm lại `exports com.example.api;` để khôi phục truy cập.

Thí nghiệm cho thấy hai lỗi đều có thể dẫn đến thông báo kiểu “package is not visible” nhưng **căn nguyên khác**: thiếu readability hay package không được export.

## 5. `opens` và truy cập reflection: khác `exports`

Một package có thể cần được framework đọc bằng reflection ở runtime, bao gồm constructor, field hoặc method không public. JPMS tách nhu cầu này khỏi việc cấp API cho mã nguồn:

- **`exports p;`**: cung cấp quyền truy cập Java thông thường tới các public types/public hoặc protected members đủ điều kiện cho các module đọc module chủ. Nó cũng cho phép một số reflection không cần phá encapsulation đối với các thành viên truy cập được.
- **`opens p;`**: mở package cho **deep reflection ở runtime**, cho phép reflection thử suppress Java language access checks đối với các thành viên trong package theo điều kiện API liên quan. Nó **không cấp quyền import và gọi tĩnh từ mã nguồn khác** như một `exports`.
- **`opens p to x.y;`**: chỉ mở package cho named module `x.y`.
- **`open module x.y { ... }`**: mở toàn bộ packages của module cho reflection; không đồng nghĩa export tất cả packages cho compile-time API.

Ví dụ module descriptor phù hợp:

```java
module com.example.lib {
    exports com.example.api;
    opens com.example.internal to com.example.framework;
}
```

Module `com.example.framework` có thể được cho phép deep reflection vào `com.example.internal`; các module khác không tự được hưởng. Module client khác vẫn không thể trực tiếp `import com.example.internal.Secret;` chỉ nhờ `opens`.

**Trong cùng một package**, cũng có thể vừa `exports` vừa `opens` với các phạm vi phù hợp. Hai directive giải quyết các loại truy cập khác nhau.

### Deep reflection và `setAccessible`

Reflection không bỏ qua mọi quy tắc đơn giản chỉ vì gọi `setAccessible(true)`. Với strong encapsulation, `setAccessible` có thể không được chấp nhận nếu package của named module chưa được mở đúng phía. Thường gặp `java.lang.reflect.InaccessibleObjectException` khi cố can thiệp private member mà module chưa `opens` package cho module gọi. Cần kiểm tra tình huống cụ thể qua `AccessibleObject.trySetAccessible()` hoặc ngoại lệ được ném.

**Chú ý:** Phải phân biệt truy cập reflection nông tới public members thuộc exported packages, và **deep reflection** cần vượt Java visibility checks. `exports` không mặc định cho phép một framework từ module khác đọc tùy ý mọi private field.

### Khi framework dùng classpath

Ứng dụng không module hóa thường chạy trong **unnamed module**. Để mở một package cho framework ở classpath, có thể cần cấu hình runtime:

```sh
java --add-opens com.example.lib/com.example.internal=ALL-UNNAMED ...
```

Đây là **dạng minh họa của option**, dấu `...` cần thay bằng cách launch ứng dụng thực tế. `ALL-UNNAMED` là target đặc biệt cho tất cả unnamed modules, không phải tên một named module bình thường. Khi có thể chỉnh sửa library, ưu tiên khai báo `opens`/`opens ... to ...` đúng phạm vi thay vì mở quá rộng chỉ để tránh một lỗi reflection.

## 6. Split package: một tên package bị chia qua nhiều module

**Split package** là khi các classes thuộc cùng **tên package** được phân bố ở nhiều module hoặc thành phần phân giải lớp khác nhau. Ví dụ:

```text
module.alpha
└── com/example/shared/Alpha.class

module.beta
└── com/example/shared/Beta.class
```

Hai modules cùng có package `com.example.shared`. Trong Java trước JPMS hoặc khi đơn thuần dựa vào nhiều JAR trên classpath, kiểu bố trí này từng xuất hiện khá nhiều. Với named modules trên module path, nó gây khó cho resolution và class loading bởi package name không còn ánh xạ duy nhất tới một nguồn.

### Không nên diễn giải quá tuyệt đối

Có **nhiều cấp kiểm tra** đối với split package:

1. **Readability graph/resolution:** Theo API `java.lang.module`, resolution thất bại nếu một module đọc hai module cùng export **cùng tên package tới nó**, hoặc nếu module tự có package trùng với package mà module nó đọc export tới nó.
2. **Layer/class loader:** Việc định nghĩa các modules vào một module layer/class loader có thêm hạn chế riêng; chẳng hạn, tạo một layer dùng **cùng một class loader** không được có packages chồng lấn giữa các modules được đưa vào loader đó.
3. **Classpath + module path:** Gặp package cùng tên ở hai nơi có thể dẫn tới class không tìm thấy, lựa chọn nguồn lớp khác mong đợi hoặc khác biệt giữa compile và runtime, tùy cấu hình loader/module graph.

Vì vậy, **“hễ hai JAR chứa cùng package thì `javac` chắc chắn lập tức báo một lỗi duy nhất”** là kết luận quá đơn giản: cần biết mỗi JAR đang ở classpath hay module path, chúng được resolve như thế nào, có export package hay không, có cùng class loader hay không. Nhưng đây vẫn là **thiết kế cần tránh** khi tổ chức named modules, vì rất dễ làm build hoặc launch thất bại.

### Ví dụ lỗi resolution với hai packages cùng được export

Giả sử hai named modules:

**`src/com.example.alpha/module-info.java`:**

```java
module com.example.alpha {
    exports com.example.shared;
}
```

**`src/com.example.beta/module-info.java`:**

```java
module com.example.beta {
    exports com.example.shared;
}
```

Chúng có hai classes khác nhau nhưng cùng package `com.example.shared`. Một module client:

```java
module com.example.app {
    requires com.example.alpha;
    requires com.example.beta;
}
```

Khi client đọc cả hai modules export cùng package tới nó, graph không nhất quán. Thông báo có thể đề cập “reads package ... from both ...” hoặc “package ... is declared in module ...”, tùy lệnh và JDK. Đây là **mô hình negative test**, chưa cung cấp các class source cần thiết để chạy độc lập.

**Không giải quyết bằng cách đổi tên class** nếu package name vẫn trùng: vấn đề ở **package namespace**. Giải pháp bền vững là thống nhất quyền sở hữu package, đổi package ở một module, tách thành một module chứa toàn bộ package hoặc đổi cấu trúc phụ thuộc để tránh đọc các exports trùng tên.

### Split package giữa classpath và module path

Ví dụ một JAR cũ có `com.example.shared.Legacy` trên classpath, còn module mới có `com.example.shared.NewType` trên module path. Tùy cách module được resolve và classloader phân giải package, class trên classpath có thể không hiển thị như bạn mong đợi, dẫn đến lỗi kiểu `NoClassDefFoundError` hoặc `ClassNotFoundException` dù file thực tế nằm trong JAR.

Không dùng “JAR nằm trên classpath nên chắc chắn sẽ được thấy” làm quy tắc chung khi package đó cũng xuất hiện trong một named module. Hãy **di chuyển package về một nơi duy nhất**, hoặc nếu thực sự làm migration đặc biệt, nghiên cứu `--patch-module` như giải pháp có kiểm soát.

## 7. Named, automatic và unnamed modules: khác nhau khi migration

| Loại module | Hình thành | Đặc điểm cần nhớ |
| --- | --- | --- |
| **Explicit named module** | JAR/directory có `module-info.class` phù hợp | Readability/exports/opens theo descriptor; encapsulation chủ động |
| **Automatic module** | JAR thông thường được đặt trên module path và được hệ module xem như automatic | Có tên module tự động hoặc từ manifest; các packages được export, cơ chế readability rộng để hỗ trợ migration |
| **Unnamed module** | Mã được load từ classpath | Không có `module-info`; code truyền thống thường có phạm vi truy cập rộng hơn trong migration, nhưng named modules không tự động đọc unnamed module |

Một số hệ quả:

- **Automatic module** đọc những resolved named modules khác và có cơ chế tương thích với unnamed modules trong runtime; nó export mọi package. Đây là nhịp cầu migration, không phải lý do để giữ package trùng nhau vô thời hạn.
- **Unnamed module** đọc các resolved modules theo quy tắc riêng và có thể tiếp cận các packages được export phù hợp, nhưng không được “bẻ khóa” concealed package của một named module tùy ý.
- **Named module** thông thường không thể chỉ `requires` một unnamed module bằng tên vì unnamed module không có module name để nêu trong descriptor.

Khi chuyển thư viện cũ lên module path, cần kiểm tra **automatic module name**, package conflicts và dependencies của chính thư viện. Việc đổi chỗ JAR từ classpath sang module path **không chỉ là đổi một tham số dòng lệnh**; ý nghĩa resolution đã đổi.

## 8. Các lệnh hỗ trợ điều tra module graph

Lệnh biên dịch/chạy thường gặp:

```sh
javac --release 17 --module-source-path src -d mods -m com.example.app,com.example.lib
java --module-path mods -m com.example.app/com.example.app.Main
```

Đây là **mẫu lệnh tổng quát**; dùng cây module và danh sách modules phù hợp với project. Với ví dụ có ba modules ở mục 4, dùng chính lệnh ba modules đã cung cấp, vì facade là một thành phần bắt buộc.

Các công cụ hữu ích:

| Lệnh | Mục tiêu |
| --- | --- |
| `java --list-modules` | Xem system modules của runtime và thông tin version khi có |
| `java --module-path mods --describe-module com.example.lib` | Xem module descriptor của module trên đường dẫn |
| `jar --describe-module --file lib.jar` | Xem mô tả module của JAR, kể cả thông tin automatic module nếu phù hợp |
| `jdeps --module-path mods --list-deps mods/com.example.app` | Phân tích các module dependencies quan sát từ artifact theo cấu hình |
| `javap -v mods/com.example.app/module-info.class` | Quan sát `Module` attribute trong compiled descriptor |
| `javac --help` và `java --help` | Tra options đúng JDK, đặc biệt module path và flag liên quan |

**`jdeps` là công cụ phân tích phụ thuộc tĩnh**, không phải bằng chứng tuyệt đối cho mọi đường đi reflection/dynamic class loading. Khi kết quả khác behavior runtime, kiểm tra thêm các module được resolve, service loading, reflective access và những JAR thực tế.

### Tùy chọn `--add-reads`, `--add-exports`, `--add-opens`

Trong migration hoặc thử nghiệm, launcher và compiler có thể hỗ trợ các điều chỉnh module graph:

```text
--add-reads   com.example.app=com.example.lib
--add-exports com.example.lib/com.example.internal=com.example.app
--add-opens   com.example.lib/com.example.internal=com.example.app
```

Ba dòng trên là **mẫu cú pháp để đối chiếu**, chưa phải lệnh Java đầy đủ và phải áp dụng ở phase cần thiết (compiler, runtime hoặc cả hai, theo từng option):

- **`--add-reads`** thêm readability edge.
- **`--add-exports`** mở đường truy cập vào public API của package theo mục tiêu chỉ định.
- **`--add-opens`** mở package cho deep reflection ở runtime.

Những cờ này không đồng nghĩa nhau. `--add-exports` không tự cấp quyền gọi private method bằng reflection; `--add-opens` không tự cấp quyền import source package theo `exports`. Có những tổ hợp, nhất là với `--release` và platform modules, bị giới hạn hoặc bị từ chối.

**Định hướng dài hạn:** sửa `module-info.java`, thiết kế package/API và quản lý dependencies đúng là giải pháp duy trì được. Option cưỡng bức graph phù hợp cho migration hoặc chẩn đoán có thời hạn; không nên biến thành một tập bypass vô hạn.

## 9. Những lỗi và thông báo thường thấy

| Dấu hiệu | Điều cần kiểm tra | Cách sửa đúng bản chất |
| --- | --- | --- |
| `module not found: ...` | Đường dẫn module path/source path, tên module, JAR có hợp lệ? | Sửa module descriptor và paths; đảm bảo module được quan sát |
| `package ... is not visible` | Module client có reads owner không? Owner có exports package đó cho client không? | Sửa `requires` và/hoặc `exports` phù hợp |
| `package ... is declared in module ..., which does not export it` | Package bị concealed | Export đúng package hoặc bỏ phụ thuộc vào internal API |
| `module ... does not read ...` | Readability edge bị thiếu | `requires` hoặc `requires transitive` phù hợp |
| `module ... reads package ... from both ...` | Hai module cùng export một package tới consumer | Loại bỏ split package hoặc thay cấu trúc graph |
| `InaccessibleObjectException` | Framework cố deep reflection vào package chưa được mở | `opens`/qualified opens hoặc `--add-opens` ở runtime theo nhu cầu |
| `NoClassDefFoundError` trong migration | Compile/runtime paths khác nhau, split package hoặc dependency bị thiếu | Kiểm tra module path, classpath, resolution và file thực tế |
| `IllegalAccessError` tại runtime | Binary liên kết tới class/member không còn accessible sau thay descriptor/phiên bản module | So sánh descriptor, ABI và môi trường runtime |

Các chuỗi lỗi trên là **dấu hiệu thường gặp**; thông báo nguyên văn có thể khác theo JDK và vị trí kiểm tra. Một lỗi biên dịch do export không hợp lệ khác với một lỗi runtime do encapsulation/loader; hãy phân biệt phase xảy ra.

### Quy trình debug từng bước

1. **Ghi version và mode:** `javac -version`, `java -version`; module path và classpath thực tế, JAR nào là automatic module?
2. **Xác định module chủ của type:** lớp cần import nằm trong package nào và được build vào JAR/module nào?
3. **Vẽ readability:** client `requires` module nào, có `requires transitive` phù hợp không, module phụ thuộc có được resolve không?
4. **Kiểm tra `exports`:** package được export rộng, export có điều kiện hay concealed? Public class/member có đủ Java visibility?
5. **Nếu dùng reflection:** package đã `opens` cho đúng module framework chưa? Lời gọi dùng reflection nông hay deep reflection?
6. **Nếu có hai bản package cùng tên:** kiểm tra tất cả JAR trên classpath/module path và các module được resolve; tránh thay đổi ngẫu nhiên thứ tự đường dẫn như cách “fix” lâu dài.
7. **Xác thực compile và runtime riêng:** một module graph ở compile time có thể khác runtime vì missing modules, toolchain, automatic modules hoặc flags.
8. **Sửa nguồn sở hữu package, chạy lại từ output sạch:** tránh class/JAR cũ làm sai lệch kết quả.

## 10. Tình huống thiết kế trước và sau

### Trường hợp 1: thư viện có internal API

**Trước:** module library đặt toàn bộ packages vào `exports` để client compile được, khiến `com.example.internal` thành một phần public interface không mong muốn.

**Sau:** chỉ export `com.example.api`; package `com.example.internal` ở lại nội bộ. Nếu một framework cần introspection riêng, thêm `opens com.example.internal to <framework-module>;` đúng mục đích.

### Trường hợp 2: facade công khai kiểu từ thư viện phụ thuộc

**Trước:**

```java
module com.example.facade {
    requires com.example.lib;
    exports com.example.facade;
}
```

Client chỉ `requires com.example.facade` nhưng import thêm library API nên thiếu readability edge.

**Sau:** nếu library types là một phần công khai của facade:

```java
module com.example.facade {
    requires transitive com.example.lib;
    exports com.example.facade;
}
```

Sau đó app đọc lib một cách hợp lệ qua facade, miễn lib thực sự export package cần thiết.

### Trường hợp 3: một package bị chia giữa hai JAR

**Trước:**

```text
legacy-api.jar -> com/example/shared/Api.class
legacy-impl.jar -> com/example/shared/Impl.class
```

Khi đưa từng JAR thành named/automatic modules và có một consumer cần cả hai, khả năng gặp conflict tăng lên.

**Sau:** chuyển `Impl` sang package riêng thuộc implementation module, ví dụ `com.example.impl`; giữ API ở `com.example.shared` thuộc một module sở hữu. Nếu package cần ở cùng chỗ để sử dụng package-private accesses, xem lại ranh giới module và có thể gộp phần code đó trong **một module** thay vì tách JAR theo cách cũ.

**Không dùng package-private như một kênh liên lạc qua hai named modules** chỉ vì các class có cùng tên package; JPMS phân biệt runtime package theo tên và module/class loader, nên cách sắp xếp đó không giữ nguyên đặc quyền package-private giữa các module.

## 11. Các hiểu nhầm phổ biến

**“Đã `requires` module B thì truy cập được mọi class public của B.”** Sai. Package chứa class cần được export cho client, và Java visibility vẫn áp dụng.

**“`exports` đủ, không cần `requires`.”** Sai đối với module client truy cập tĩnh thông thường; phải có cạnh readability hợp lệ.

**“`requires` luôn transitive.”** Sai. Chỉ `requires transitive` (hoặc những cơ chế đặc biệt khác trong graph) mới truyền readability sang client theo quy tắc JPMS.

**“`opens` cũng như `exports`.”** Sai. `opens` giải quyết reflective access ở runtime; nó không công bố một package như API compile-time.

**“`open module` công khai toàn bộ API Java cho mọi module.”** Sai. Nó mở packages cho reflection, không thay thế các exports cần thiết cho truy cập nguồn.

**“Mọi split package đều được JVM tự động gộp thành một.”** Sai. Module resolution/class loading đặt giới hạn để tránh package namespace mơ hồ. Đừng trông chờ Java ghép package từ nhiều named modules thành một package chung.

**“Cùng tên package là cùng package-private access dù ở hai module.”** Sai. Runtime package identity gắn với module/class loader và namespace; cùng chuỗi ký tự tên chưa đủ để gộp quyền truy cập.

**“Có thể chữa split package bằng `--add-exports`.”** Không nhất thiết; thêm exports còn có thể tạo xung đột khi một consumer đọc nhiều module cùng export một package. Sửa package ownership và graph thường đúng hơn.

**“Automatic module là explicit named module với `module-info.java`.”** Sai. Automatic module được suy ra từ JAR trên module path và có cơ chế tương thích migration; cấu hình sẽ khác khi chuyển sang explicit descriptor.

**“`jdeps` sẽ phát hiện mọi reflection dependency.”** Không. Phân tích tĩnh không thấy hết reflection và việc nạp lớp động, nên cần kiểm thử runtime.

## 12. Checklist trước khi chạy `javac` với module path

- [ ] Mỗi module có tên rõ ràng và `module-info.java` phù hợp nếu là explicit named module.
- [ ] Module consumer có read edges tới những module mà source trực tiếp dùng.
- [ ] Các phụ thuộc là một phần public API được đánh dấu `requires transitive` đúng chỗ; không dùng transitive cho tất cả tùy tiện.
- [ ] Package định đưa thành public API có `exports`, đúng đối tượng nhận export (unqualified/qualified).
- [ ] Public types và members có Java access modifiers phù hợp; package-private vẫn được bảo vệ.
- [ ] Framework cần deep reflection có `opens` đúng phạm vi, không mở rộng cả module nếu không cần.
- [ ] Mỗi package có owner rõ; kiểm tra split packages giữa named, automatic modules và classpath.
- [ ] Module path được khai báo riêng với classpath; biết dependency nào là automatic/unnamed.
- [ ] Đã thử biên dịch bằng `--release 17` và chạy bằng module path trên JDK mục tiêu.
- [ ] Khi gặp lỗi, đã phân loại **readability**, **exports**, **opens**, **Java modifiers** hay **split package** trước khi sửa?

**Ghi nhớ:** *Readability* quyết định module nào nhìn thấy module nào; *exports* quyết định package nào trở thành API cho truy cập Java bình thường; *opens* cấp quyền reflective access sâu ở runtime. Split package khiến việc phân giải namespace kém rõ ràng và thường phá module graph/class loading. Thiết kế mỗi package có một chủ sở hữu rõ ràng và khai báo đúng `requires`/`exports` là cách khai thác JPMS ổn định.

## Tài liệu tham khảo

- Java Language Specification 17, Chapter 7, *Packages and Modules*, phần `7.7`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
- Java SE 17, package `java.lang.module`, *Resolution and readability graph*, bao gồm điều kiện xung đột exports: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html
- Java SE 17, `ModuleLayer` — điều kiện trùng package/class loader khi định nghĩa layer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Dev.java, *Strong Encapsulation with --add-exports and --add-opens*: https://dev.java/learn/organizing/modules/add-exports-opens/
- Oracle JDK 17, *The javac Command* — `--module-path`, `--module-source-path` và `--add-reads`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html