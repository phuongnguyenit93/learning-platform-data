# `Module.isExported`, `Module.isOpen` và kiểm tra ngữ cảnh truy cập

## 1. Vấn đề: `public` vẫn có thể chưa đủ

`Module.isExported` và `Module.isOpen` đọc **trạng thái quyền package tại runtime** từ góc nhìn một module cụ thể. Khi chẩn đoán Reflection, hãy xác định đúng module chứa package đích (`source`) và module **thực sự gọi** `setAccessible` (`client`): đó có thể là framework, không phải module ứng dụng khởi tạo yêu cầu.

Khi cần tham chiếu public API bằng mã Java thông thường, xét readability và `exports`; khi muốn bỏ qua Java access checks từ module khác, xét `opens`. Phần dưới tập trung vào cách diễn giải chính xác bốn overload và trường hợp `opens` cũng làm `isExported` trả `true` ở runtime.

Bốn API của `java.lang.Module` là trọng tâm bài:

```java
boolean x1 = source.isExported("example.api");
boolean x2 = source.isExported("example.api", client);
boolean x3 = source.isOpen("example.internal");
boolean x4 = source.isOpen("example.internal", client);
```

Đoạn trên là minh họa với hai biến kiểu `Module` đã được xác định. Mỗi API hỏi về quyền của **một package trong module nguồn**, không trực tiếp hỏi một field/method có thể đọc hoặc gọi được hay không.

**Điểm mấu chốt:** `opens` khác `exports` về mục đích, nhưng **một package mở cho module đích được xem như export cho module đó tại runtime**. Vì thế, `isExported(pn, client)` có thể trả `true` dù `module-info.java` chỉ khai báo `opens pn to client;`. Đừng nhầm kết quả runtime với quyền import package đó tại compile time.

## 2. Xác định đúng source, client và package

Gọi:

- **`source`**: module chứa package/lớp đang được truy cập.
- **`client`** (hay `callerModule`): module chứa mã thực sự thực hiện Reflection.
- **`pn`**: tên package đầy đủ như `"example.internal"`; không phải tên lớp `example.internal.Secret` hay đường dẫn `example/internal`.

Lấy thông tin từ class:

```java
Module source = TargetType.class.getModule();
Module client = MyInspector.class.getModule();
String pn = TargetType.class.getPackageName();
```

Đây là đoạn minh họa, đòi hỏi các class được khai báo ở chương trình phù hợp. Nếu package không export nên mã client không thể import `TargetType` trực tiếp, bạn có thể nhận `source` từ một lớp API public đã export cùng module, từ `Class.forName(...)` khi thích hợp, hoặc tra module đã resolve bằng `ModuleLayer.boot().findModule("ten.module")` nếu nó thuộc boot layer.

| Cách kiểm tra | Ý nghĩa |
| --- | --- |
| `source.isNamed()` | Phân biệt named module và unnamed module |
| `source.getName()` | Tên module; `null` với unnamed module |
| `source.getPackages().contains(pn)` | Package hiện được module báo là của nó? |
| `client.canRead(source)` | Client có thể đọc source? |
| `source.isExported(pn)` | Export không điều kiện tại runtime? |
| `source.isExported(pn, client)` | Export ít nhất đến client tại runtime? |
| `source.isOpen(pn)` | Open không điều kiện tại runtime? |
| `source.isOpen(pn, client)` | Open ít nhất đến client tại runtime? |

**Không đảo hướng:** Khi hỏi quyền truy cập vào package của `source`, gọi `source.isOpen(pn, client)`, không phải `client.isOpen(pn, source)`.

Trong ứng dụng thực tế, `client` có thể là module của framework đang chạy đoạn Reflection, **không nhất thiết là module ứng dụng đã gọi vào framework**. Đây là một nguồn gây lỗi cấu hình `opens ... to ...` rất phổ biến.

## 3. `isExported`: package được nhìn thấy cho mục đích nào?

### 3.1. `isExported(String pn)`

Trả `true` nếu package được export **không điều kiện** tại runtime:

```java
module m.library {
    exports demo.api;
}
```

`source.isExported("demo.api")` sẽ là `true` với module này nếu `demo.api` là package hiện có. Mã trong module khác muốn tham chiếu trực tiếp kiểu `public` từ `demo.api` còn cần các điều kiện Java/module access khác, đặc biệt readability.

Không dùng `isExported(pn)` thay cho kiểm tra `client.canRead(source)`: tài liệu Java quy định các phương thức `isExported` **không kiểm tra** module đang xét có được module client đọc hay không.

Lưu ý quan trọng: package được **open không điều kiện** cũng được xem như export không điều kiện ở runtime, nên `source.isExported(pn)` có thể là `true` khi descriptor có `opens pn;` mà không có `exports pn;`.

### 3.2. `isExported(String pn, Module other)`

Kiểm tra package đã export ít nhất cho module `other` hay chưa. Ví dụ:

```java
module m.library {
    exports demo.spi to m.client;
}
```

Với đúng module `m.client`:

- `source.isExported("demo.spi")` là `false` vì export **có điều kiện**.
- `source.isExported("demo.spi", client)` là `true` vì client có trong danh sách đích.

Trường hợp **qualified opens** còn tinh tế hơn:

```java
module m.library {
    opens demo.internal to m.client;
}
```

Ở **runtime**, `source.isExported("demo.internal", client)` là **`true`** vì package mở cho client được coi là export cho client. Nhưng `source.isExported("demo.internal")` là `false` khi không có export/open không điều kiện.

Đừng suy luận rằng mã nguồn `m.client` có thể viết `import demo.internal.Secret;` chỉ vì overload hai tham số trả `true`. `opens` phục vụ Reflection và quyền runtime; `exports` mới là tuyên bố public API thông thường khi trình biên dịch kiểm tra tính truy cập giữa named modules.

### 3.3. Trường hợp module tự truy cập chính mình

Nếu package thuộc `source`, `source.isExported(pn, source)` trả `true`: Java xem module có quyền tới package của chính nó. Đây **không** phải bằng chứng package được export ra ngoài. Muốn biết quyền của framework khác, truyền đúng `Module` của framework đó.

## 4. `isOpen`: cho phép truy cập Reflection sâu

### 4.1. `isOpen(String pn)`

Kiểm tra package có được open **không điều kiện** hay không:

```java
module m.library {
    opens demo.model;
}
```

Trong cấu hình đó, `source.isOpen("demo.model")` là `true`. Package open cho phép các API Reflection phù hợp có thể yêu cầu bỏ qua Java language access checks đối với member ở package đó, ví dụ `private` constructor hoặc field.

Ngược lại, nếu module chỉ có:

```java
module m.library {
    exports demo.api;
}
```

thì `source.isExported("demo.api")` là `true` nhưng `source.isOpen("demo.api")` vẫn là `false`. Export không tự động cấp quyền deep reflection.

### 4.2. `isOpen(String pn, Module other)`

Kiểm tra package đã open cho **một module cụ thể** hay chưa:

```java
module m.library {
    opens demo.model to m.client;
}
```

Nếu không có thay đổi quyền bổ sung ở runtime:

| Kiểm tra | Kết quả |
| --- | --- |
| `source.isOpen("demo.model")` | `false` |
| `source.isOpen("demo.model", client)` | `true` |
| `source.isExported("demo.model")` | `false` |
| `source.isExported("demo.model", client)` | **`true`** vì open cũng được coi là export tại runtime |
| `client.canRead(source)` | Phải kiểm tra **riêng** |

Tài liệu `Module` cũng quy định `source.isOpen(pn, source)` trả `true` nếu package thuộc chính source. Vì vậy, khi kiểm tra một framework bên ngoài, truyền `source` làm `other` sẽ cho kết quả dễ gây hiểu lầm.

### 4.3. So sánh các chỉ thị

Bảng giả định **explicit named module** và package thật sự thuộc nó, không có thêm `--add-exports`/`--add-opens`:

| `module-info.java` | `isExported(pn)` | `isOpen(pn)` | `isExported(pn, client)` | `isOpen(pn, client)` |
| --- | --- | --- | --- | --- |
| Không có `exports`/`opens` | false | false | false | false |
| `exports p;` | true | false | true | false |
| `exports p to m.client;` | false | false | true | false |
| `opens p;` | **true** | true | **true** | true |
| `opens p to m.client;` | false | false | **true** | true |

Ở hai dòng qualified, `client` là đúng module `m.client`. Nếu truyền một module khác không có trong danh sách, các kết quả qualified tương ứng sẽ là `false`. Các phương thức trả trạng thái access **hiện hành**, không chỉ đọc các dòng khai báo trong nguồn.

## 5. Kiểm tra đủ ngữ cảnh: đọc module, package và member

Để mã Java ở module client có thể **tham chiếu trực tiếp** public API trong source, phải xét đồng thời:

1. **Readability:** `client.canRead(source)`. Lệnh `requires m.library;` trong `module-info.java` tạo quan hệ đọc khi module graph được resolve theo các quy tắc JPMS.
2. **Export:** package chứa public API được export cho client; cần phân biệt export công khai và qualified.
3. **Java access control:** kiểu và member thực sự có quyền phù hợp, ví dụ class `public`, method `public`.

Để **deep reflection** từ một framework, câu hỏi bổ sung là package có **open tới module chứa framework** hay không. Khi thao tác trên `Field`, `Method`, `Constructor`, phương thức ở `java.lang.reflect.AccessibleObject` còn phản ánh khả năng access cụ thể:

| API | Tác dụng |
| --- | --- |
| `getDeclaredField("value")` | Tìm metadata về field **khai báo trực tiếp**, không tự cấp quyền đọc giá trị |
| `canAccess(instance)` | Kiểm tra quyền truy cập hiện tại của **caller** đối với reflected object |
| `trySetAccessible()` | Thử bật chế độ bỏ qua access checks; trả `true` nếu bật được, `false` khi không thể |
| `setAccessible(true)` | Yêu cầu bật chế độ đó; có thể ném `InaccessibleObjectException` khi JPMS cấm |
| `Field.get(instance)` / `Method.invoke(...)` | Thực hiện truy cập/gọi và áp dụng quy tắc phù hợp |

**Ngữ cảnh caller rất quan trọng:** Mã ở module `m.framework` gọi `trySetAccessible()` thì source phải mở package cho `m.framework`. Mở package cho `m.app` là chưa chắc giúp ích, ngay cả khi `m.app` là nơi khởi động framework.

**Một khác biệt kỹ thuật:** Theo tài liệu `AccessibleObject`, việc sử dụng reflected objects để truy cập member có biến thể trong kiểm tra quyền: Reflection **giả định readability** khi kiểm tra access. Vì vậy không được áp dụng máy móc tất cả quy tắc compile-time reference cho thao tác Reflection runtime. Dù vậy, `canRead` vẫn hữu ích khi phân tích module graph và quyền truy cập Java thông thường; bản thân nó không hề đủ để vượt qua package encapsulation.

Không đồng nhất ba việc **tìm thấy `Class`**, **lấy được `Field`/`Method` metadata** và **được phép đọc/gọi member đó**. Ví dụ `Class.forName` có thể tìm một class nhưng `trySetAccessible` vẫn thất bại nếu package không mở cho caller.

## 6. Ví dụ thực hành Java 17+: hai named module

Ví dụ dưới đây cho thấy **qualified opens**: một package nội bộ không export công khai nhưng vẫn mở cho Reflection của client cụ thể. Tạo các tệp:

```text
src/
├── m.library/
│   ├── module-info.java
│   └── demo/
│       ├── api/Api.java
│       └── model/Secret.java
└── m.client/
    ├── module-info.java
    └── demo/client/Main.java
```

**`src/m.library/module-info.java`**

```java
module m.library {
    exports demo.api;
    opens demo.model to m.client;
}
```

**`src/m.library/demo/api/Api.java`**

```java
package demo.api;

public final class Api {
    private Api() {
    }
}
```

**`src/m.library/demo/model/Secret.java`**

```java
package demo.model;

public final class Secret {
    private final String message = "hello";

    private Secret() {
    }
}
```

**`src/m.client/module-info.java`**

```java
module m.client {
    requires m.library;
}
```

**`src/m.client/demo/client/Main.java`**

```java
package demo.client;

import demo.api.Api;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        Module source = Api.class.getModule();
        Module client = Main.class.getModule();

        System.out.println("client reads library: "
                + client.canRead(source));
        System.out.println("api exported to all: "
                + source.isExported("demo.api"));
        System.out.println("api open to all: "
                + source.isOpen("demo.api"));
        System.out.println("model exported to all: "
                + source.isExported("demo.model"));
        System.out.println("model exported to client at runtime: "
                + source.isExported("demo.model", client));
        System.out.println("model open to all: "
                + source.isOpen("demo.model"));
        System.out.println("model open to client: "
                + source.isOpen("demo.model", client));

        // Không import trực tiếp package demo.model.
        Class<?> type = Class.forName("demo.model.Secret");
        Constructor<?> constructor = type.getDeclaredConstructor();
        System.out.println("constructor trySetAccessible: "
                + constructor.trySetAccessible());
        Object instance = constructor.newInstance();

        Field field = type.getDeclaredField("message");
        System.out.println("field trySetAccessible: "
                + field.trySetAccessible());
        System.out.println("secret: " + field.get(instance));
    }
}
```

Tại thư mục chứa `src`, biên dịch rồi chạy:

```bash
javac -d out --module-source-path src src/m.library/module-info.java src/m.library/demo/api/Api.java src/m.library/demo/model/Secret.java src/m.client/module-info.java src/m.client/demo/client/Main.java
java --module-path out -m m.client/demo.client.Main
```

**Stdout mong đợi:**

```text
client reads library: true
api exported to all: true
api open to all: false
model exported to all: false
model exported to client at runtime: true
model open to all: false
model open to client: true
constructor trySetAccessible: true
field trySetAccessible: true
secret: hello
```

Phân tích:

- `requires m.library;` giúp client đọc module thư viện; `canRead` là `true`.
- `demo.api` chỉ được `exports` công khai: `isExported` là `true`, `isOpen` là `false`.
- `demo.model` được `opens ... to m.client`: không export/open không điều kiện. Nhưng **`isExported("demo.model", client) == true` tại runtime**, vì qualified open cho client cũng tính là export.
- Client không viết `import demo.model.Secret;`. Thay vào đó, `Class.forName` lấy class theo tên. Đây là đường tra cứu metadata, không cấp sẵn quyền truy cập constructor/field.
- Hai lần `trySetAccessible()` thành công vì package thực sự được mở cho module `m.client` chứa mã gọi, nên code có thể khởi tạo object bằng private constructor và đọc private field.

**Bài thử lỗi có kiểm soát:** Bỏ dòng `opens demo.model to m.client;` trong module nguồn, biên dịch lại. Khi đó `isOpen("demo.model", client)` và `isExported("demo.model", client)` trở thành `false`. `constructor.trySetAccessible()` cũng trả `false`; nếu mã vẫn gọi `constructor.newInstance()` như thể đã được cấp quyền, có thể gặp `IllegalAccessException`. Hãy kiểm tra giá trị trả về và ngừng nhánh truy cập sâu khi thất bại.

## 7. Kiểm tra nhanh từ classpath và `java.base`

Đây là ví dụ riêng, không cần tổ chức nhiều module. Lưu `ModuleProbe.java`:

```java
public class ModuleProbe {
    public static void main(String[] args) {
        Module mine = ModuleProbe.class.getModule();
        Module base = String.class.getModule();

        System.out.println("mine named: " + mine.isNamed());
        System.out.println("mine reads java.base: " + mine.canRead(base));
        System.out.println("java.lang exported: "
                + base.isExported("java.lang"));
        System.out.println("java.lang open: "
                + base.isOpen("java.lang"));
        System.out.println("java.lang exported to mine: "
                + base.isExported("java.lang", mine));
        System.out.println("java.lang open to mine: "
                + base.isOpen("java.lang", mine));
    }
}
```

```bash
javac ModuleProbe.java
java -cp . ModuleProbe
```

**Stdout trên cấu hình JDK 17+ tiêu chuẩn, không thêm `--add-opens java.base/java.lang=ALL-UNNAMED`:**

```text
mine named: false
mine reads java.base: true
java.lang exported: true
java.lang open: false
java.lang exported to mine: true
java.lang open to mine: false
```

`ModuleProbe` chạy trong **unnamed module** của class loader; `String` thuộc named module `java.base`. Package `java.lang` được export để mã dùng public API như `String.length()`, nhưng điều đó không cho phép Reflection từ classpath tùy ý đọc các field private của `String`.

## 8. Các loại module đặc biệt và hệ quả

### Explicit named module

Module có khai báo tường minh `module-info.java` cho phép kiểm soát từng package bằng `exports` và `opens` (kể cả qualified dạng `to m.client`). Đây là trường hợp bảng so sánh ở mục 4 áp dụng trực tiếp.

### `open module`

Khai báo `open module m.library { ... }` mở **mọi package thuộc module** cho Reflection. Đây là đặc tính cấp module, khác với `opens p;` chỉ mở một package. Với package thuộc một open module, `isOpen(pn)` trả `true`; package open không điều kiện cũng được xem như export không điều kiện ở runtime. Trong phần thân `open module` không khai báo thêm các chỉ thị `opens` riêng.

### Unnamed module

Mã nạp từ classpath thường thuộc unnamed module. Theo hợp đồng Java `Module`, các phương thức `isExported` và `isOpen` **khi gọi trên unnamed module** luôn trả `true`; unnamed module cũng đọc mọi module. Nhưng unnamed module không khiến named module khác tự động mở các package của chúng cho mã classpath.

### Automatic module

Một JAR không có explicit module descriptor có thể trở thành **automatic module** nếu được đưa lên module path. Automatic module có tên (`isNamed() == true`), export và open các package theo cơ chế tương thích. Phân biệt nó với unnamed module. Có thể xem `module.getDescriptor().isAutomatic()` khi descriptor tồn tại.

### Module tự truy cập package

`source.isOpen(pn, source)` hoặc `source.isExported(pn, source)` trả `true` với package thuộc source. Nếu vô tình truyền `source` thay cho module framework đang truy cập, kết quả dễ bị diễn giải sai thành quyền mở ra ngoài.

## 9. Quyền runtime có thể khác khai báo nguồn

`Module.isExported` và `Module.isOpen` phản ánh **runtime module state**. Khi chạy Java, có thể bổ sung các quyền:

| Cơ chế | Tác dụng |
| --- | --- |
| `requires m.library;` | Thiết lập module readability theo module graph |
| `exports p;` hoặc `exports p to m.client;` | Public API unqualified / qualified |
| `opens p;` hoặc `opens p to m.client;` | Reflection access unqualified / qualified |
| `--add-reads m.client=m.library` | Thêm read edge lúc chạy |
| `--add-exports m.library/demo.internal=m.client` | Thêm export cho client lúc chạy |
| `--add-opens m.library/demo.model=m.client` | Thêm open cho client lúc chạy |

Giả sử bỏ `opens demo.model to m.client;` trong thư viện, sau khi biên dịch lại có thể bật quyền open ngay khi chạy (nếu bạn kiểm soát launch command):

```bash
java --module-path out --add-opens m.library/demo.model=m.client -m m.client/demo.client.Main
```

`--add-opens` là lựa chọn cho nhu cầu deep reflection. `--add-exports` có ý nghĩa khác, hỗ trợ public access tại runtime; đừng tự động thêm cả hai khi chưa xác định yêu cầu.

Các phương thức `Module.addReads`, `Module.addExports` và `Module.addOpens` cũng tồn tại nhưng **được bảo vệ bởi điều kiện về caller và trạng thái module**. Một framework ở module bất kỳ không thể giả định nó được tự do mở tất cả package của module khác.

Vì vậy, `source.getDescriptor().exports()` hoặc `opens()` biểu diễn mô tả của module và có thể **khác trạng thái runtime** do các lệnh cấu hình hoặc cập nhật. Khi phân tích một lỗi, hãy nhìn đồng thời descriptor, `Module` object thực tế, tham số khởi chạy và module layer liên quan.

## 10. Quy trình debug `InaccessibleObjectException`

Một quy trình ngắn nhưng đầy đủ:

1. **Lớp đích:** xác định `targetClass.getName()` và `targetClass.getPackageName()`.
2. **Module nguồn:** `targetClass.getModule()`, cùng tên và trạng thái `isNamed()`.
3. **Caller thật:** tìm class đang chạy `setAccessible`/`trySetAccessible`; lấy `Accessor.class.getModule()`. Nếu đó là framework, module framework mới là `other`.
4. **Truy vấn quyền package:** so sánh `source.isOpen(pn)` với `source.isOpen(pn, callerModule)`; tương tự cho `isExported`.
5. **Readability:** hỏi `callerModule.canRead(source)` riêng, nhất là khi có lỗi compile/module resolution hay Java access bình thường.
6. **Kiểm tra member cụ thể:** thử `canAccess`/`trySetAccessible` hoặc xem exception thật, lưu ý constructor, instance/static field và method yêu cầu tham số `obj` phù hợp.
7. **Kiểm tra runtime:** `module-info.java`, `--module-path` so với `-cp`, launch flags, agent và các API cập nhật quyền.

Khi exception ghi module `m.library` không `opens demo.model` cho module `m.framework`, hãy kiểm tra quyền open **tới `m.framework`**. Thêm `opens demo.model to m.app;` chỉ vì ứng dụng chính thuộc `m.app` có thể không xử lý đúng caller.

### Những suy luận cần tránh

- `isOpen(pn) == false` **không** có nghĩa `isOpen(pn, client)` luôn false (có qualified opens).
- `isExported(pn, client) == true` **không** có nghĩa package chắc chắn có dòng `exports`; kết quả có thể đến từ `opens` ở runtime.
- `isOpen(pn, client) == true` **không** bảo đảm mọi hành động Reflection thành công vô điều kiện.
- `canRead(source) == true` **không** cho phép đọc field private nếu thiếu các điều kiện Reflection khác.
- `getDeclaredField` tìm thấy field **không** đồng nghĩa caller được phép `Field.get`.
- `isOpen(pn, source) == true` với một package thuộc source **không** chứng minh package đó đã mở cho framework bên ngoài.

## 11. Bài tự kiểm tra

Cho module nguồn:

```java
module m.provider {
    exports demo.api;
    opens demo.internal to m.consumer;
}
```

Giả sử `demo.api` và `demo.internal` là hai package có thật, module `m.consumer` đã resolve và đọc module nguồn, không có runtime override. Dự đoán:

```java
provider.isExported("demo.api");                   // A
provider.isOpen("demo.api");                       // B
provider.isExported("demo.internal");              // C
provider.isOpen("demo.internal");                  // D
provider.isExported("demo.internal", consumer);    // E
provider.isOpen("demo.internal", consumer);        // F
provider.isOpen("demo.internal", provider);        // G
```

**Đáp án:** A = `true`; B = `false`; C = `false`; D = `false`; E = **`true`** (qualified opens cũng có hiệu lực export tại runtime); F = `true`; G = `true` (module được truy cập package của chính mình).

Đây là các mảnh mã để suy luận, không phải tệp Java độc lập có thể biên dịch. Muốn chạy, sử dụng chương trình đầy đủ ở mục 6.

## 12. Ghi nhớ và tài liệu chuẩn

**Đặt câu hỏi từ góc nhìn source và caller:** `source.isExported(package, callerModule)` và `source.isOpen(package, callerModule)`. Overload một tham số hỏi quyền không điều kiện; overload hai tham số hỏi quyền ít nhất cho một module cụ thể. Package mở cho module đích **được xem là exported cho module đó tại runtime**, nhưng `opens` vẫn có mục đích riêng là deep reflection; `exports` dùng cho public API thông thường. Quyền đọc module, quyền package và quyền của member cần đánh giá riêng.

Tài liệu đối chiếu:

- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [Java SE 21 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java Language Specification `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
