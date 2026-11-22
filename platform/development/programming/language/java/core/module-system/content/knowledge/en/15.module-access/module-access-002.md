# Public type trong exported package

Trong Java Platform Module System (JPMS), một class được khai báo `public` chưa chắc có thể được module khác sử dụng. Để truy cập một **public type** thuộc **named module** khác, chương trình phải đáp ứng đồng thời các điều kiện về **readability** giữa các module, **export** của package chứa kiểu và **quyền truy cập Java** của chính kiểu và các thành viên được dùng.

Đây là điểm khác biệt quan trọng so với tư duy classpath truyền thống: `public` nói về khả năng truy cập theo ngôn ngữ Java, còn `exports` nói về ranh giới package của một module. Hai cơ chế bổ sung cho nhau, không cơ chế nào tự thay thế cơ chế còn lại.

## 1. Ba điều kiện để consumer sử dụng public type

Giả sử module `com.acme.app` muốn gọi `com.acme.catalog.api.CatalogClient` nằm trong module `com.acme.catalog`.

Để mã nguồn consumer sử dụng kiểu đó qua API công khai, cần:

1. **Module consumer đọc được module cung cấp:** thường qua `requires com.acme.catalog;` trong descriptor của consumer.
2. **Module cung cấp export package cho consumer:** `exports com.acme.catalog.api;` hoặc qualified export `exports ... to com.acme.app;`.
3. **Kiểu có quyền truy cập thích hợp:** với top-level class, interface, enum hoặc record được dùng công khai giữa các module, kiểu cần được khai báo `public`. Constructor, method và field mà consumer dùng cũng cần visibility hợp lệ.

Công thức khái quát:

```text
Có thể sử dụng public type từ named module khác
             =
  Consumer reads provider module
             +
  Provider exports the type's package to consumer
             +
  Type/member is accessible under Java rules
```

Một package được export không có nghĩa mọi class hoặc member bên trong đều trở thành public. Ngược lại, khai báo `public class` trong package chưa export không làm kiểu đó trở thành API truy cập được từ một named module bên ngoài.

## 2. Ví dụ hai module đơn giản

Thư viện công bố một API:

```text
project/
└── src/
    ├── com.acme.catalog/
    │   ├── module-info.java
    │   └── com/acme/catalog/api/CatalogClient.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
```

Descriptor của thư viện:

```java
// src/com.acme.catalog/module-info.java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

Public type thuộc package được export:

```java
// src/com.acme.catalog/com/acme/catalog/api/CatalogClient.java
package com.acme.catalog.api;

public final class CatalogClient {
    public CatalogClient() {
    }

    public String find(String id) {
        return "Catalog item: " + id;
    }
}
```

Descriptor của consumer:

```java
// src/com.acme.app/module-info.java
module com.acme.app {
    requires com.acme.catalog;
}
```

Ứng dụng sử dụng public API:

```java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import com.acme.catalog.api.CatalogClient;

public class Main {
    public static void main(String[] args) {
        CatalogClient client = new CatalogClient();
        System.out.println(client.find("P-100"));
    }
}
```

Trong ví dụ này, `requires` tạo readability, `exports` công bố package và `CatalogClient` cùng constructor/method được truy cập đều là `public`. Vì thế `javac` có thể biên dịch ứng dụng với module path đúng.

## 3. Biên dịch và chạy ví dụ trên

Đứng tại thư mục `project`. Nếu dùng Linux/macOS:

```shell
javac --module-source-path src \
      -d out \
      -m com.acme.catalog,com.acme.app

java --module-path out \
     -m com.acme.app/com.acme.app.Main
```

Kết quả mong đợi:

```text
Catalog item: P-100
```

`--module-source-path src` cho `javac` biết source tree được tổ chức theo tên module. Tùy chọn `-m` chọn các module nguồn cần biên dịch. `-d out` đưa class files đã biên dịch vào các thư mục module tương ứng bên dưới `out`.

`java --module-path out` dùng những module đã biên dịch; `-m com.acme.app/com.acme.app.Main` chỉ định module và main class.

Nếu muốn tạo modular JAR cho từng module:

```shell
jar --create --file com.acme.catalog.jar \
    -C out/com.acme.catalog .

jar --create --file com.acme.app.jar \
    --main-class com.acme.app.Main \
    -C out/com.acme.app .
```

Có thể kiểm tra descriptor được đóng gói:

```shell
jar --describe-module --file com.acme.catalog.jar
jar --describe-module --file com.acme.app.jar
```

Trong ứng dụng thực tế, Maven hoặc Gradle có thể thực hiện các bước biên dịch, đóng gói; nhưng điều kiện `requires`, `exports` và `public` vẫn giữ nguyên.

## 4. Thiếu requires: package export vẫn chưa đủ

Giữ nguyên descriptor của thư viện:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

Nhưng thay descriptor consumer bằng:

```java
module com.acme.app {
}
```

Khi mã nguồn cố import `CatalogClient`, compiler không có quan hệ readability phù hợp từ `com.acme.app` tới `com.acme.catalog`.

Một thông báo có thể có nội dung gần như:

```text
package com.acme.catalog.api is not visible
(package com.acme.catalog.api is declared in module
 com.acme.catalog, but module com.acme.app does not read it)
```

Cách sửa đúng là thêm dependency module theo nhu cầu thực tế:

```java
module com.acme.app {
    requires com.acme.catalog;
}
```

Chỉ thêm JAR vào module path không có nghĩa module consumer sẽ tự đọc mọi module có thể quan sát được. Module path chỉ cung cấp nguồn để tìm module; `requires` và cơ chế resolution mới xác định quan hệ đọc.

Ngoại lệ, runtime có các quy tắc riêng cho unnamed module và automatic modules; những cơ chế chuyển tiếp đó không nên được dùng để suy ra rằng explicit named module bình thường không cần khai báo dependency.

## 5. Thiếu exports: requires cũng chưa đủ

Nếu thư viện thay descriptor thành:

```java
module com.acme.catalog {
}
```

thì package `com.acme.catalog.api` không được export. Consumer có thể có `requires com.acme.catalog;`, compiler vẫn không cho phép tham chiếu public class trong package không export.

Thông báo thường gặp:

```text
package com.acme.catalog.api is not visible
(package com.acme.catalog.api is declared in module
 com.acme.catalog, which does not export it)
```

Cách xử lý chuẩn khi package thực sự là public API:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

Nếu package cố ý chứa implementation nội bộ, không nên export chỉ để caller truy cập một class. Hãy tạo public facade hoặc service interface trong package API đã được công bố và để implementation bên trong package không export.

## 6. exports không tự làm class trở thành public

Xét package đã được export:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

Nhưng source có:

```java
package com.acme.catalog.api;

class InternalCatalog {
    static String find(String id) {
        return id;
    }
}
```

`InternalCatalog` là **package-private top-level class**, không phải public type. Một consumer nằm ngoài package không được import hoặc dùng trực tiếp class này dù package chứa nó đã được export.

Tương tự:

```java
package com.acme.catalog.api;

public class CatalogClient {
    private CatalogClient() {
    }

    String internalLookup(String id) {
        return id;
    }
}
```

Consumer có thể thấy tên public class `CatalogClient`, nhưng không thể gọi private constructor hoặc package-private `internalLookup`.

Nếu API cần cho consumer khởi tạo và gọi method:

```java
package com.acme.catalog.api;

public class CatalogClient {
    public CatalogClient() {
    }

    public String find(String id) {
        return id;
    }
}
```

Cần thiết kế quyền truy cập ở **cả cấp type lẫn cấp member**. Không dùng `exports` để khắc phục một constructor không public hoặc member `private`.

## 7. Top-level, nested và member accessibility

Một exported package có thể chứa các loại kiểu khác nhau:

```java
package com.acme.catalog.api;

public interface Catalog {
    String find(String id);
}
```

```java
package com.acme.catalog.api;

public enum CatalogStatus {
    READY, UNAVAILABLE
}
```

```java
package com.acme.catalog.api;

public record CatalogItem(String id, String title) {
}
```

Các kiểu `public` này có thể là một phần API của package được export.

Với nested type, vẫn phải xét modifier và kiểu bao ngoài:

```java
package com.acme.catalog.api;

public class CatalogResult {
    public static class Summary {
    }

    private static class InternalState {
    }
}
```

Nếu consumer đọc module và package được export, nó có thể sử dụng `CatalogResult.Summary` theo quy tắc Java, nhưng không thể trực tiếp truy cập `CatalogResult.InternalState` vì nested type đó là `private`.

Một public nested type cũng không hữu ích như API công khai nếu chính kiểu bao ngoài không accessible. Hãy thiết kế toàn bộ chuỗi kiểu bao ngoài và member sao cho hợp đồng truy cập nhất quán.

## 8. Qualified exports: chỉ công bố API cho một số module

JPMS hỗ trợ export không điều kiện:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
}
```

Và **qualified export**:

```java
module com.acme.catalog {
    exports com.acme.catalog.integration to com.acme.partner;
}
```

Trong trường hợp thứ hai, package `com.acme.catalog.integration` chỉ được export cho named module `com.acme.partner`. Một named module khác `com.acme.app` có `requires com.acme.catalog;` nhưng không nằm trong danh sách `to` sẽ không được sử dụng public types của package integration theo đường truy cập thông thường.

Khi cần nhiều consumer:

```java
module com.acme.catalog {
    exports com.acme.catalog.integration
        to com.acme.partner, com.acme.admin;
}
```

Cú pháp `to` sử dụng **tên module**, không phải Maven artifact coordinates, tên package hay tên file JAR.

Qualified export thường dùng cho API hợp tác giữa những module biết rõ nhau, không phải để giấu một API mà trên thực tế mọi consumer đều cần. Khi đổi tên module đích, danh sách qualified exports cũng cần được xem xét cập nhật.

## 9. Public type và requires transitive

Giả sử module `com.acme.catalog` export API có kiểu trả về thuộc `com.acme.model`:

```java
// com.acme.catalog.api.Catalog
package com.acme.catalog.api;

import com.acme.model.Product;

public interface Catalog {
    Product find(String id);
}
```

Descriptor module catalog:

```java
module com.acme.catalog {
    requires transitive com.acme.model;
    exports com.acme.catalog.api;
}
```

Với `requires transitive`, consumer đọc `com.acme.catalog` cũng được trao readability tới `com.acme.model`, phù hợp khi public API của catalog phơi bày `Product`.

Consumer:

```java
module com.acme.app {
    requires com.acme.catalog;
}
```

Cách này không đồng nghĩa module `com.acme.model` tự export mọi package: chính module model vẫn cần export package chứa `Product`.

Nếu module catalog thay bằng `requires com.acme.model;` thông thường, consumer muốn trực tiếp sử dụng kiểu từ model có thể cần thêm `requires com.acme.model;` của chính nó.

Chỉ dùng `requires transitive` khi có ý định truyền readability như một phần contract. Đừng biến mọi dependency implementation thành transitive, vì consumer sẽ có thêm các quan hệ đọc không cần thiết.

## 10. exported package khác với open package

Hai directive giải quyết hai nhu cầu khác nhau:

| Khả năng | `exports P` | `opens P` |
|---|---|---|
| Consumer import và sử dụng public types theo Java thông thường | Có, khi consumer đọc module | Không tự cấp quyền compile-time thông thường |
| Truy cập public member theo Java access rules | Có | Không thay thế exports |
| Deep reflection vào private fields/constructors | Không tự động | Cho phép theo quy tắc reflection runtime |
| Áp dụng cho | Public API giữa named modules | Framework, serializer, ORM, reflection |
| Có phiên bản qualified `to M` | Có | Có |

Ví dụ một thư viện có public API và model dùng bởi framework:

```java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.model to com.acme.json;
}
```

Module ứng dụng dùng public API ở package `com.acme.catalog.api`. Framework `com.acme.json` được phép deep reflection vào `com.acme.catalog.model` ở runtime.

Không nên thay `exports com.acme.catalog.api;` bằng `opens com.acme.catalog.api;` nếu mục tiêu là để consumer import và gọi public API. Ngược lại, nếu framework cần sửa private field, chỉ export package không đủ; cần chính sách open package thích hợp.

`open module` mở rộng khả năng reflection đối với các package trong toàn module. Nó không biến mọi member private thành public API của Java và thường quá rộng đối với thiết kế strong encapsulation.

## 11. Public type trên classpath và module path

Một public class nằm trong JAR classpath truyền thống thường được truy cập dựa trên Java access modifier và cách class loader nạp class. Nếu cùng JAR được nhận diện thành **explicit named module** trên module path, `module-info.class` và module boundaries bắt đầu có hiệu lực.

So sánh:

```text
Classpath:
  public class + classloader visibility
  (không có exports từ named module của JAR đó)

Module path:
  module readability + exports + Java visibility
```

Đây là lý do một thư viện chạy ổn trên classpath có thể báo `package ... is not visible` sau khi chuyển sang module path.

Nếu JAR chưa có `module-info.class`, khi đặt trên module path nó có thể trở thành **automatic module**. Automatic module có cơ chế readability/exports đặc biệt để hỗ trợ migration, khác với explicit named module. Đừng dựa vào hành vi export rộng của automatic module để kết luận rằng mọi package vẫn sẽ public khi thư viện phát hành explicit descriptor về sau.

## 12. Không nhầm exported package với split package

Package được export không đồng nghĩa tên package đó có thể phân bố tùy ý trên nhiều named modules.

Ví dụ:

```text
com.acme.alpha
    com.acme.shared.Alpha

com.acme.beta
    com.acme.shared.Beta
```

Nếu cả hai module đều export `com.acme.shared` và consumer đọc cả hai, module graph có thể từ chối vì consumer đọc package cùng tên từ hai module.

Thông báo điển hình:

```text
module com.acme.app reads package com.acme.shared
from both com.acme.alpha and com.acme.beta
```

Vấn đề này không được giải quyết bằng cách thêm `exports` hoặc `opens`. Cần tổ chức package ownership rõ ràng: chuyển class vào đúng module, đổi tên package hoặc loại artifact trùng.

Khi thấy lỗi split package, hãy phân biệt với lỗi access thông thường do một package chưa được export. Nguyên nhân và cách sửa khác nhau.

## 13. Kiểm tra exports từ artifact đã đóng gói

Không nên chỉ tin descriptor còn nằm trong source tree. Module descriptor trong JAR cuối cùng mới là metadata mà module system sử dụng.

Kiểm tra bằng:

```shell
jar --describe-module --file libs/com.acme.catalog.jar
```

Công cụ có thể hiển thị tên module, dependency, package exports, opens và các dịch vụ được khai báo.

Khi chạy ứng dụng, có thể xem module resolution:

```shell
java --show-module-resolution \
     --module-path mods:libs \
     -m com.acme.app/com.acme.app.Main
```

Trên Windows, dấu phân cách các phần tử module path là `;`, không phải `:` như Linux/macOS.

Với một module đã có trong runtime image:

```shell
java --describe-module java.logging
```

Có thể kiểm tra những module được phân giải hoặc những quan hệ runtime bằng Java Module API khi cần. Tuy nhiên, các phép kiểm tra metadata không thay thế việc biên dịch và chạy consumer thực tế.

## 14. Kiểm tra quyền truy cập bằng Java Module API

Một chương trình có thể hỏi `Module` về readability và export:

```java
Module consumer = Main.class.getModule();
Module provider = CatalogClient.class.getModule();

boolean readable = consumer.canRead(provider);

boolean exportedToConsumer =
    provider.isExported("com.acme.catalog.api", consumer);

System.out.println("Readable: " + readable);
System.out.println("Exported: " + exportedToConsumer);
```

Ví dụ giả định cả `Main` và `CatalogClient` đều đã có thể tham chiếu/nạp trong môi trường kiểm tra. Nếu đang chẩn đoán một kiểu không accessible, tránh viết thêm code import trực tiếp kiểu đó chỉ để debug. Có thể dùng descriptor và module metadata từ API hoặc công cụ để xác định module và package liên quan.

Có hai cách hỏi export:

- `module.isExported("package.name")`: kiểm tra unqualified export.
- `module.isExported("package.name", consumer)`: kiểm tra package có được export cho một module cụ thể không, bao gồm qualified exports.

`module.canRead(other)` trả lời câu hỏi khác với `isExported`. Cần kiểm tra cả hai để giải thích một public type có thể được truy cập hay không.

Các API này phản ánh quan hệ module ở runtime, bao gồm một số thay đổi động được áp dụng trong quá trình chạy, không nhất thiết là toàn bộ những gì được ghi nguyên văn trong source descriptor.

## 15. Đối chiếu compile time và runtime

Một public type có thể biên dịch thành công nhưng gặp lỗi ở runtime nếu cấu hình hai giai đoạn không giống nhau.

Ví dụ compiler được cấp quyền export bổ sung:

```shell
javac \
  --module-path mods \
  --add-exports com.acme.catalog/com.acme.catalog.internal=com.acme.app \
  -d out/app \
  src-app/module-info.java \
  src-app/com/acme/app/Main.java
```

Nhưng ứng dụng chạy không có cờ tương ứng:

```shell
java --module-path mods:out \
  -m com.acme.app/com.acme.app.Main
```

Bytecode có thể gặp `IllegalAccessError` khi cố truy cập public class trong package `com.acme.catalog.internal` không được export cho module ứng dụng ở runtime.

Nếu thực sự cần workaround tạm thời ở runtime, phải chỉ định quyền phù hợp:

```shell
java \
  --module-path mods:out \
  --add-exports com.acme.catalog/com.acme.catalog.internal=com.acme.app \
  -m com.acme.app/com.acme.app.Main
```

Tuy nhiên, phương án bền vững hơn là chuyển consumer sang public API hoặc export package khi đó là hợp đồng được hỗ trợ. Không nên phụ thuộc lâu dài vào package `internal`.

Lỗi do thay đổi binary access như constructor từ `public` sang `private` cũng có thể gây `IllegalAccessError` mà không cần liên quan tới `exports`. Phải đọc chính xác nội dung lỗi và đối chiếu artifact thực tế.

## 16. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `module not found: M` | Module phụ thuộc không có trên module path hoặc tên sai | Kiểm tra module name và build dependency |
| `module A does not read B` | Thiếu readability | Khai báo `requires B;` hoặc xem lại module graph |
| `package P is not visible` | Package chưa export cho consumer hoặc thiếu readability | Kiểm tra `requires` và `exports` |
| `class X is not public` | Kiểu không có modifier `public` | Dùng public API hoặc sửa visibility ở source sở hữu |
| `constructor X() has private access` | Constructor không accessible | Dùng factory hoặc public constructor được hỗ trợ |
| `method m() is not public` | Member không có quyền truy cập phù hợp | Dùng API public thay thế |
| `InaccessibleObjectException` | Deep reflection bị chặn | Xem `opens` và chính sách framework |
| `IllegalAccessError` khi runtime | Bytecode và quyền truy cập runtime khác nhau | So sánh descriptor, flags, JAR và runtime |
| `reads package P from both M1 and M2` | Split package | Sửa cấu trúc package/dependency, không chỉ thêm export |

Nếu code chạy trên classpath nhưng không chạy trên module path, đừng mở hàng loạt package bằng `open module`. Hãy xác định đúng lỗi: readability, exports, Java visibility, reflection hay split package.

## 17. Thiết kế exported packages như public contract

Một số nguyên tắc giúp giữ module boundary rõ ràng:

1. **Export package API có chủ đích.** Package `api`, `spi` hoặc `public` chỉ nên chứa những kiểu mà consumer được phép phụ thuộc.
2. **Giữ package internal không export.** Public class nằm trong package internal có thể phục vụ nội bộ module hoặc cơ chế provider mà không trở thành contract của consumer.
3. **Không export tất cả package để chữa lỗi build.** Mỗi export là một cam kết tương thích tiềm năng với consumer.
4. **Giới hạn qualified export khi thích hợp.** Dùng `to` để chỉ rõ các module hợp tác thay vì công bố package cho toàn bộ module graph.
5. **Bảo đảm API surface nhất quán.** Public type phải có constructor/factory/method public phù hợp với trường hợp sử dụng được hỗ trợ.
6. **Dùng `requires transitive` có chọn lọc.** Chỉ truyền readability khi công khai dependency là một phần của API.
7. **Tách reflection khỏi API access.** `opens` cho framework không thay cho `exports` của API.
8. **Duy trì test compile từ consumer module riêng.** Nó phát hiện sớm việc package bị đóng hoặc API chưa thực sự accessible.
9. **Kiểm thử trên artifact được phân phối.** Source code và module descriptor trước đóng gói có thể khác file JAR cuối cùng.
10. **Ghi changelog khi thay đổi export.** Bỏ hoặc thu hẹp package export có thể phá source compatibility và runtime linkage dù class vẫn tồn tại.

## 18. Checklist thực hành

Trước khi dùng một public type từ named module khác, kiểm tra lần lượt:

- [ ] Consumer có dùng đúng **tên JPMS module** trong `requires` không?
- [ ] JAR chứa module có mặt trên module path và đã được resolve chưa?
- [ ] Module cung cấp đã export **đúng package** chứa kiểu chưa?
- [ ] Nếu export có `to`, consumer có nằm trong danh sách module đích không?
- [ ] Top-level/nested type có thực sự accessible dưới quy tắc Java không?
- [ ] Constructor, field, method cần sử dụng có visibility hợp lệ không?
- [ ] Nếu public API chứa kiểu của module khác, readability đã được xử lý phù hợp chưa?
- [ ] Nếu cần deep reflection, đã xét `opens` riêng biệt chưa?
- [ ] Compiler và runtime có đang dùng cùng artifact và module descriptor không?
- [ ] Có xung đột split package hoặc tên module trùng không?

**Kết luận:** `public` và `exports` là hai nửa của quyền truy cập API trong JPMS, còn `requires` cung cấp quan hệ đọc module. Một kiểu chỉ được sử dụng hợp lệ từ consumer khi cả module graph, package boundary và Java visibility đều cho phép. Thiết kế exported packages như hợp đồng API rõ ràng giúp ứng dụng modular giảm phụ thuộc vào implementation và tránh các lỗi truy cập khó phát hiện khi nâng cấp thư viện.