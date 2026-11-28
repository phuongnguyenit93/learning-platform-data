# requires, khả năng đọc module và quy tắc giả định readability riêng của core reflection

## 1. Bối cảnh và mục tiêu

Trong Java Platform Module System (JPMS), một mô-đun được phép sử dụng API của mô-đun khác không chỉ vì class có modifier `public`. Kiểm soát truy cập gồm **readability** (mô-đun gọi có đọc mô-đun đích không?), **exports** (package có được công khai cho mô-đun gọi không?) và **opens** (package có cho phép deep reflection không?).

Một chi tiết dễ gây hiểu lầm khi học phần *quyền reflection* là: code không khai báo `requires target.module;`, `Module.canRead(target)` trả `false`, nhưng `Method.invoke` trên phương thức `public` thuộc package `exports` vẫn chạy thành công. Đây không phải lỗi kiểm soát quyền, mà là **quy tắc riêng có chủ đích của core reflection**: khi sử dụng các reflected objects `Field`, `Method`, `Constructor`, bước kiểm tra quyền **giả định module chứa caller đọc module khai báo thành viên**. Quy tắc này tiếp tục tồn tại trong Javadoc Java SE 25.

Bài học thuộc phạm vi Java 18 và các hợp đồng JPMS còn áp dụng trên JDK hiện đại. Không sử dụng mẹo phụ thuộc implementation, `--illegal-access`, xóa encapsulation bằng reflection nội bộ hay các API đã lỗi thời.

**Kết quả cần đạt:**

- Giải thích `requires` ảnh hưởng thế nào đến biên dịch và đồ thị readability.
- Phân biệt module **có mặt trong module layer** với việc caller **có cạnh đọc** module đó.
- Chỉ ra vì sao `Class.forName(Module, String)` lấy được `Class<?>` nhưng bản thân nó không cấp quyền sử dụng các thành viên.
- Chứng minh core reflection cho phép gọi **public member của public class trong package exported** dù `canRead` vẫn `false`.
- Chứng minh giả định readability **không vượt qua encapsulation**: package không exported/opened và private member vẫn bị giới hạn.
- Phân biệt `requires`, `exports`, `opens`, `--add-modules`, `--add-reads`, `--add-exports` và `--add-opens`.
- Tự chạy ma trận kiểm chứng bằng hai named modules, trên JDK 18 trở lên.

## 2. Ba điều kiện khác nhau của module system

Xét mô-đun `sample.consumer` muốn truy cập class trong `sample.target`.

| Khái niệm | Nguồn cấu hình | Ý nghĩa | Cách quan sát |
| --- | --- | --- | --- |
| Module resolution | Các root modules, dependency trong module path | `sample.target` đã được đưa vào module graph/layer hay chưa | `ModuleLayer.boot().findModule("sample.target")` |
| Readability | `requires`, `requires transitive`, `--add-reads` | `sample.consumer` có cạnh đọc `sample.target` không | `consumer.canRead(target)` |
| Exports | `exports package;` hoặc `exports ... to ...;` | Cho phép truy cập các public types/public members theo quy tắc module | `target.isExported(packageName, consumer)` |
| Opens | `opens package;` hoặc `opens ... to ...;` | Cho phép deep reflection vào thành viên không public bằng `trySetAccessible`/`setAccessible` | `target.isOpen(packageName, consumer)` |

**`requires` không phải `opens`.** Một mô-đun có thể đọc mô-đun khác, nhưng vẫn không được truy cập private field, constructor hay method của module đích. Ngược lại, riêng core reflection có thể gọi public method của exported package mà không cần caller có cạnh đọc ở runtime.

Một mô-đun **không có `requires`** đến target vẫn có thể quan sát target nếu target đã được **resolved** trong cùng module layer, ví dụ target là một root bổ sung do `--add-modules`. Nhưng việc target đã resolved **không tự làm `consumer.canRead(target)` thành `true`**.

### 2.1. `requires` là cạnh đọc thực

```java
module sample.consumer {
    requires sample.target;
}
```

Khi khai báo như trên, `sample.consumer` có dependency tới `sample.target`. Mô-đun target được đưa vào quá trình resolution, và `sample.consumer.canRead(sample.target)` sẽ là `true` trong đồ thị bình thường. Nếu package đích `exports` phù hợp, code Java có thể sử dụng public type của nó trực tiếp lúc biên dịch.

Nếu không khai báo `requires`, biên dịch một `import sample.target.api.ExportedApi;` từ named module `sample.consumer` sẽ bị từ chối (trừ khi có cấu hình bù như `--add-reads` trong môi trường biên dịch). Nhưng việc biên dịch lớp chỉ sử dụng tên kiểu dưới dạng chuỗi và API reflection **không cần** import kiểu đích.

### 2.2. Quy tắc giả định readability của core reflection

Trong `java.lang.reflect.AccessibleObject`, Javadoc quy định khi reflected object `Method`, `Field` hoặc `Constructor` được sử dụng, kiểm tra quyền truy cập **giả định module của caller đọc module chứa thành viên**. Vì vậy, so sánh sau không mâu thuẫn:

```text
consumer.canRead(target) == false

target exports "sample.target.api"
ExportedApi là public class; greeting() là public method

Constructor.newInstance() -> có thể thành công
Method.invoke(...)       -> có thể thành công

consumer.canRead(target) vẫn false
```

Điều này là **một giả định trong access check**, không phải thao tác `consumer.addReads(target)`. Nó không tạo cạnh đọc mới, không chỉnh `module-info.class`, không biến một package private thành exported và không thay đổi khả năng biên dịch các import Java thông thường.

Lưu ý: phạm vi phát biểu trên là **core reflection khi sử dụng reflected objects**, không phải mọi cách gọi API động. Đừng suy rộng tự động sang mọi cơ chế khác như `MethodHandles.Lookup`, symbol resolution hoặc truy cập bytecode thông thường.

### 2.3. Có `Class<?>` không đồng nghĩa có quyền truy cập

`Class.forName(Module module, String name)` thử tìm class trong module chỉ định, **không kiểm tra class đó có accessible với caller không**, không chạy class initializer và trả `null` khi không tìm thấy.

Ví dụ:

```java
Module target = ModuleLayer.boot()
        .findModule("sample.target")
        .orElseThrow();

Class<?> type = Class.forName(
        target, "sample.target.internal.InternalApi");
```

`type` có thể khác `null` dù package `sample.target.internal` không được exported. Nhưng việc lấy được `Class<?>` hoặc gọi `getDeclaredMethods()` chỉ là **khám phá metadata**. Khi dùng `Constructor.newInstance` hay `Method.invoke`, các kiểm tra quyền thực tế mới được áp dụng.

## 3. Ma trận dự kiến trước khi chạy code

Mô-đun `sample.target` trong ví dụ sẽ có ba package:

| Package | Module descriptor | Trạng thái khi gọi từ `sample.consumer` |
| --- | --- | --- |
| `sample.target.api` | `exports sample.target.api;` | Public class/constructor/method được gọi qua reflection, dù caller chưa đọc target |
| `sample.target.internal` | Không `exports` và không `opens` | Có thể lấy metadata bằng `Class.forName`, nhưng không dùng constructor public từ module khác; private cũng không thể bật access |
| `sample.target.opened` | `opens sample.target.opened;` | Deep reflection được phép, kể cả private method sau `trySetAccessible()` |

Chú ý một chi tiết của API `Module`: **package đã `opens` được xem là exported tại runtime đối với mô-đun được mở tới**. Vì vậy, `target.isExported("sample.target.opened", consumer)` có thể trả `true`, dù descriptor **không có** chỉ thị `exports` cho package đó. Điều này không có nghĩa `opens` thay thế `exports` khi kiểm tra `import` lúc biên dịch. Muốn biết một package mở cho deep reflection, dùng `isOpen`; muốn kiểm tra xuất package theo ngữ nghĩa khai báo, xem `ModuleDescriptor.exports()`.

Điểm quan trọng nhất là phải tách ba câu hỏi:

1. Module target **đã được resolved** chưa?
2. Caller có cạnh **đọc thực** qua `Module.canRead` chưa?
3. Access check đang xét **compile-time direct access**, **public core reflection**, hay **deep reflection**?

## 4. Hai named modules: target và consumer

Thiết lập thư mục minh họa dưới đây **chỉ là ví dụ trong bài học**; worker không tạo các file này trong repository. Khi tự thực hành, hãy đặt chúng trong một thư mục lab riêng.

```text
reflection-readability-lab/
  src/
    sample.target/
      module-info.java
      sample/target/api/ExportedApi.java
      sample/target/internal/InternalApi.java
      sample/target/opened/DeepApi.java
    sample.consumer/
      module-info.java
      app/ReflectProbe.java
  mods/                     # output sau khi javac
```

### 4.1. Descriptor của target

Tệp `src/sample.target/module-info.java`:

```java
module sample.target {
    exports sample.target.api;
    opens sample.target.opened;
}
```

- `sample.target.api` được exported để các public types/members là API công khai.
- `sample.target.internal` không có chỉ thị nào: package bị đóng với module khác.
- `sample.target.opened` mở cho deep reflection, nhưng không có `exports` trong module descriptor.

### 4.2. Ba class có hành vi quan sát được

Tệp `src/sample.target/sample/target/api/ExportedApi.java`:

```java
package sample.target.api;

public final class ExportedApi {
    public static final String CATEGORY = "public-api";

    public ExportedApi() {
    }

    public String greet() {
        return "hello-from-exported";
    }

    private String secret() {
        return "not-open";
    }
}
```

Tệp `src/sample.target/sample/target/internal/InternalApi.java`:

```java
package sample.target.internal;

public final class InternalApi {
    public InternalApi() {
    }

    public String greet() {
        return "internal-only";
    }
}
```

Tệp `src/sample.target/sample/target/opened/DeepApi.java`:

```java
package sample.target.opened;

public final class DeepApi {
    public DeepApi() {
    }

    private String secret() {
        return "opened-private";
    }
}
```

Cả ba class đều có modifier `public`, vì mục đích bài học là **cách JPMS kiểm soát package**, không phải phân biệt modifier public/private của class. Riêng `secret()` là private để chứng minh export không cấp deep reflection.

### 4.3. Descriptor của consumer không requires target

Tệp `src/sample.consumer/module-info.java`:

```java
module sample.consumer {
    // Không khai báo: requires sample.target;
}
```

Named module `sample.consumer` vẫn đọc `java.base` như mọi named module bình thường, nhưng **không đọc `sample.target`**. Mã consumer ở phần tiếp theo không sử dụng `import sample.target...` và không tham chiếu kiểu đích trực tiếp khi biên dịch.

**Điểm cần kiểm chứng:** khi target được nạp vào boot layer bằng `--add-modules sample.target`, consumer có thể tìm `Class<?>` rồi thực hiện core reflection trên API đã exported, trong khi `consumer.canRead(target)` vẫn bằng `false`.

## 5. Chương trình kiểm thử core reflection

Tạo `src/sample.consumer/app/ReflectProbe.java`:

```java
package app;

import java.lang.Module;
import java.lang.ModuleLayer;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import java.util.Objects;

public final class ReflectProbe {
    private static void check(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    private static Class<?> load(Module module, String binaryName) {
        Class<?> result = Class.forName(module, binaryName);
        check(result != null, "Không tìm được " + binaryName);
        check(result.getModule() == module,
                "Class không nằm trong module được chỉ định");
        return result;
    }

    public static void main(String[] args) throws Exception {
        check(args.length <= 1
                && (args.length == 0 || "reads".equals(args[0])),
                "Chỉ chấp nhận không có arg hoặc arg reads");

        boolean expectReadEdge = args.length == 1;
        Module consumer = ReflectProbe.class.getModule();
        Module target = ModuleLayer.boot()
                .findModule("sample.target")
                .orElseThrow(() -> new AssertionError(
                        "Chưa resolve sample.target: cần --add-modules"));

        check("sample.consumer".equals(consumer.getName()),
                "Chương trình phải chạy dưới named module sample.consumer");
        check(consumer.canRead(target) == expectReadEdge,
                "Trạng thái readability không đúng với mode đang chạy");

        // Package exported và opened có trạng thái khác nhau.
        check(target.isExported("sample.target.api", consumer),
                "Package api phải được exported tới consumer");
        check(!target.isOpen("sample.target.api", consumer),
                "Package api không được opens");
        check(!target.isExported("sample.target.internal", consumer),
                "Package internal không được exported");
        check(!target.isOpen("sample.target.internal", consumer),
                "Package internal không được opens");
        check(target.isOpen("sample.target.opened", consumer),
                "Package opened phải mở cho consumer");
        check(target.isExported("sample.target.opened", consumer),
                "Package opened được xem là exported tại runtime");
        check(target.getDescriptor().exports().stream()
                .noneMatch(e -> e.source().equals("sample.target.opened")),
                "Descriptor không được có exports cho package opened");

        // A. Public core reflection thành công dù không có requires.
        Class<?> exported = load(
                target, "sample.target.api.ExportedApi");

        Constructor<?> publicConstructor = exported.getConstructor();
        check(publicConstructor.canAccess(null),
                "Public constructor trong exported package phải accessible");
        Object object = publicConstructor.newInstance();

        Method publicMethod = exported.getMethod("greet");
        check(publicMethod.canAccess(object),
                "Public method trong exported package phải accessible");
        check(Objects.equals(
                "hello-from-exported", publicMethod.invoke(object)),
                "Method.invoke không trả đúng kết quả");

        Field publicField = exported.getField("CATEGORY");
        check(Objects.equals(
                "public-api", publicField.get(null)),
                "Field.get không đọc được public field");

        // B. Exports KHÔNG cho phép mở private method.
        Method privateMethod = exported.getDeclaredMethod("secret");
        check(!privateMethod.trySetAccessible(),
                "Exports không tương đương opens khi truy cập private");

        try {
            privateMethod.setAccessible(true);
            throw new AssertionError(
                    "setAccessible phải bị từ chối với private member");
        } catch (InaccessibleObjectException expected) {
            // Truy cập deep reflection bị chặn đúng hợp đồng.
        }

        // C. Lấy được Class metadata KHÔNG cấp quyền khởi tạo class.
        Class<?> internal = load(
                target, "sample.target.internal.InternalApi");
        Constructor<?> internalConstructor = internal.getConstructor();
        check(!internalConstructor.canAccess(null),
                "Public constructor trong non-exported package bị chặn");
        check(!internalConstructor.trySetAccessible(),
                "Non-exported, non-open package không được override access");

        try {
            internalConstructor.newInstance();
            throw new AssertionError(
                    "Phải từ chối constructor trong package bị đóng");
        } catch (IllegalAccessException expected) {
            // Kiểm tra Java language access không vượt qua exports.
        }

        // D. Opens hỗ trợ deep reflection dù không khai báo requires.
        Class<?> deep = load(
                target, "sample.target.opened.DeepApi");
        Constructor<?> deepConstructor = deep.getDeclaredConstructor();
        check(deepConstructor.trySetAccessible(),
                "Opened package phải cho phép constructor access");
        Object opened = deepConstructor.newInstance();

        Method secret = deep.getDeclaredMethod("secret");
        check(secret.trySetAccessible(),
                "Opened package phải cho phép private method access");
        check(Objects.equals("opened-private", secret.invoke(opened)),
                "Deep reflection qua opens không đúng");

        // E. Core reflection không sửa module readability graph.
        check(consumer.canRead(target) == expectReadEdge,
                "Reflection không được thêm một read edge thực");

        System.out.println("mode=" +
                (expectReadEdge ? "explicit read edge" : "no read edge"));
        System.out.println("consumer.canRead(target)="
                + consumer.canRead(target));
        System.out.println("PASS: public reflection on exported package");
        System.out.println("PASS: exports does not open private members");
        System.out.println("PASS: class discovery is not access permission");
        System.out.println("PASS: private reflection on opened package");
        System.out.println("PASS: reflection did not modify readability");
    }
}
```

Chương trình không sử dụng API nội bộ, không yêu cầu `--add-opens java.base/...` và không cần `setAccessible` thành công trên package mà target không mở. Nó minh họa một luồng xử lý có thể tái lập: **module resolution → `Class<?>` discovery → public access → deep-access rejection/permission → kiểm tra `canRead` không đổi**.

## 6. Biên dịch và chạy hai trạng thái readability

Từ thư mục `reflection-readability-lab`, biên dịch **cả hai named modules**. Không chuyển `sample.consumer` sang classpath, vì unnamed module có quy tắc đọc khác và không phù hợp với thí nghiệm `canRead=false` của named module.

### 6.1. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path mods | Out-Null
javac --release 18 --module-source-path src -d mods src/sample.target/module-info.java src/sample.target/sample/target/api/ExportedApi.java src/sample.target/sample/target/internal/InternalApi.java src/sample.target/sample/target/opened/DeepApi.java src/sample.consumer/module-info.java src/sample.consumer/app/ReflectProbe.java

# A: target đã resolved, consumer KHÔNG có read edge.
java --module-path mods --add-modules sample.target --module sample.consumer/app.ReflectProbe

# B: thêm read edge runtime, không sửa source.
java --module-path mods --add-modules sample.target --add-reads sample.consumer=sample.target --module sample.consumer/app.ReflectProbe reads
```

### 6.2. Bash/Linux/macOS

```bash
mkdir -p mods
javac --release 18 --module-source-path src -d mods src/sample.target/module-info.java src/sample.target/sample/target/api/ExportedApi.java src/sample.target/sample/target/internal/InternalApi.java src/sample.target/sample/target/opened/DeepApi.java src/sample.consumer/module-info.java src/sample.consumer/app/ReflectProbe.java

java --module-path mods --add-modules sample.target --module sample.consumer/app.ReflectProbe
java --module-path mods --add-modules sample.target --add-reads sample.consumer=sample.target --module sample.consumer/app.ReflectProbe reads
```

`--add-modules sample.target` yêu cầu launcher **resolve** target như một root bổ sung. Nó không tự cấp quyền đọc target cho `sample.consumer`. Chỉ `--add-reads sample.consumer=sample.target` trong trường hợp B mới thêm cạnh đọc runtime; chương trình nhận argument `reads` để xác nhận đúng mode.

### 6.3. Kết quả dự kiến

Lần chạy A:

```text
mode=no read edge
consumer.canRead(target)=false
PASS: public reflection on exported package
PASS: exports does not open private members
PASS: class discovery is not access permission
PASS: private reflection on opened package
PASS: reflection did not modify readability
```

Lần chạy B:

```text
mode=explicit read edge
consumer.canRead(target)=true
PASS: public reflection on exported package
PASS: exports does not open private members
PASS: class discovery is not access permission
PASS: private reflection on opened package
PASS: reflection did not modify readability
```

| Điều quan sát | Không có read edge | Có `--add-reads` |
| --- | --- | --- |
| Target hiện diện trong boot layer | Có | Có |
| `consumer.canRead(target)` | `false` | `true` |
| `Constructor.newInstance` trên exported public class | Thành công | Thành công |
| `Method.invoke` trên exported public method | Thành công | Thành công |
| `Field.get` trên exported public field | Thành công | Thành công |
| `trySetAccessible` trên private method trong exported-only package | `false` | `false` |
| Public constructor trong package không exported/opened | `IllegalAccessException` | `IllegalAccessException` |
| Private method trong opened package sau `trySetAccessible` | Thành công | Thành công |

**Kết luận từ thí nghiệm:** thêm readability không tự làm thay đổi exports/opens. Public core reflection thành công ngay cả khi thiếu read edge bởi hợp đồng assume readability; private reflection vẫn phụ thuộc opens.

### 6.4. Thay bằng requires khi phát triển ứng dụng thật

Nếu sửa `src/sample.consumer/module-info.java` trong thư mục thực hành thành:

```java
module sample.consumer {
    requires sample.target;
}
```

Sau khi biên dịch lại, có thể chạy:

```bash
java --module-path mods --module sample.consumer/app.ReflectProbe reads
```

Lúc này `sample.target` được resolve theo dependency `requires` và consumer thực sự có quyền đọc target. Không cần `--add-modules`; còn public/private reflection vẫn tuân theo quyền exports/opens.

**`requires` không tự biến `sample.target.internal` thành API công khai**, và cũng không cho phép truy cập private member của exported-only package.

## 7. Vì sao compile-time access khác runtime reflection?

### 7.1. Import không hợp lệ khi thiếu requires

Đây là đoạn mã **cố ý không biên dịch** nếu đặt trong named module `sample.consumer` và không thêm `requires sample.target;`:

```java
// Phản ví dụ ở phía consumer: module thiếu requires sample.target.
import sample.target.api.ExportedApi;

public class DirectUse {
    public static void main(String[] args) {
        System.out.println(new ExportedApi().greet());
    }
}
```

Target dù có `exports sample.target.api;` thì javac vẫn cần consumer **đọc target** để dùng kiểu đó trực tiếp. Thêm `--add-modules` **chỉ ở lệnh chạy** không sửa được lỗi biên dịch. Với dependency thật trong ứng dụng, cách thông thường là khai báo `requires sample.target;` và bảo đảm package đích exported.

Trong công cụ đặc biệt hay white-box test, `javac --add-reads sample.consumer=sample.target` có thể là một lựa chọn cấu hình; không nên lạm dụng để che thiếu dependency trong module descriptor.

Ngược lại, `ReflectProbe.java` chỉ tham chiếu `Class<?>`, `Method`, `Field`, `Constructor` và tên binary dưới dạng chuỗi. Không có kiểu từ target trong chữ ký Java được biên dịch, nên consumer không cần `requires sample.target;` để biên dịch.

### 7.2. Lấy metadata khác gọi được thành viên

`Class.forName(Module, String)` không kiểm tra access. Vì vậy:

```java
Class<?> internal = Class.forName(
        target, "sample.target.internal.InternalApi");

// Có thể lấy tên và metadata, dù package không exported.
System.out.println(internal.getName());
System.out.println(internal.getDeclaredConstructors().length);
```

Tuy nhiên `internal.getConstructor().newInstance()` vẫn bị chặn bởi `IllegalAccessException`. Đây là khác biệt giữa **class discovery** và **quyền sử dụng member**. `Module.canRead()` cũng chỉ cho biết trạng thái graph; nó không phải một phương thức truy cập vào class.

### 7.3. Public visibility và deep reflection là hai mức riêng

- `getMethod("greet")` tìm public method; `invoke` thực thi sau khi access check.
- `getDeclaredMethod("secret")` có thể lấy metadata của private method, nhưng không có nghĩa caller được gọi nó.
- `trySetAccessible()` kiểm tra khả năng bỏ qua Java language access checks; trả `false` nếu module không cho phép.
- `setAccessible(true)` có thể ném `InaccessibleObjectException` thay vì âm thầm vượt qua JPMS.
- `canAccess(receiver)` kiểm tra caller có thể sử dụng reflected object tại thời điểm gọi hay không; **không phải** cách kiểm tra chỉ riêng read edge.

Trong bài, exported-only package cho phép public reflection nhưng không cho phép `secret()`. Opened package cho phép deep reflection, kể cả private member. Đừng suy luận rằng `public class` đồng nghĩa `private field` sẽ truy cập được.

### 7.4. Đặc biệt: opens được xem là exported tại runtime

Theo Javadoc `Module.isExported(package, other)`, **package open cho một module được xem là exported cho module đó tại runtime**. Vì vậy:

```text
module-info.java:
    opens sample.target.opened;          # không có exports

Runtime:
    target.isOpen("sample.target.opened", consumer)      -> true
    target.isExported("sample.target.opened", consumer)  -> true

Descriptor:
    target.getDescriptor().exports()
        không liệt kê sample.target.opened
```

Điều này giải thích tại sao kết quả `Module.isExported` ở runtime không nên được dùng để suy ra nguyên văn `exports` trong descriptor. Compile-time direct reference vẫn phải đáp ứng quy tắc `requires` và `exports`, còn core reflection dựa vào các kiểm tra runtime.

## 8. Cấu hình module: thay đổi cái gì, không thay đổi cái gì?

| Công cụ/chỉ thị | Tác động chính | Không tự động làm được |
| --- | --- | --- |
| `requires sample.target;` | Thêm dependency/read edge giữa named modules | Không mở package private |
| `requires transitive sample.target;` | Cho các module đọc module khai báo cũng có thể đọc target theo tính bắc cầu | Không cho deep reflection nếu thiếu opens |
| `--add-modules sample.target` | Đưa target vào tập root modules runtime | Không cấp read edge cho consumer |
| `--add-reads sample.consumer=sample.target` | Bổ sung read edge runtime từ consumer sang target | Không export hoặc open package |
| `exports sample.target.api;` | Cho phép API public trong package đối với module đọc target khi biên dịch | Không cho truy cập private member |
| `exports sample.target.api to sample.consumer;` | Export có điều kiện tới module nhận | Không mở private member |
| `opens sample.target.opened;` | Cho phép deep reflection từ các module khác | Không thêm `requires` trong source |
| `opens sample.target.opened to sample.consumer;` | Cho phép deep reflection giới hạn tới consumer | Không cho module khác quyền mở tương tự |
| `--add-exports sample.target/sample.target.internal=sample.consumer` | Bổ sung export runtime cho public API của một package | Không mở private member |
| `--add-opens sample.target/sample.target.api=sample.consumer` | Mở package cho deep reflection runtime | Không thêm dependency compile-time trong descriptor |

`--add-exports`, `--add-opens` và `--add-reads` hữu ích khi chẩn đoán hoặc làm white-box test, nhưng nên cân nhắc hợp đồng module thay vì mặc định đưa mọi tham số mở quyền vào production.

**Lưu ý về bài test:** nếu bật `--add-exports` hoặc `--add-opens` bổ sung trên chính ba package của ví dụ, một số assertion của `ReflectProbe` sẽ thay đổi kết quả vì trạng thái module đã khác so với fixture. Đó là hành vi đúng, không phải Java phản hồi không nhất quán. Hãy xây một mode test riêng nếu muốn đo tác động của các option này.

### 8.1. Core reflection không đại diện mọi API truy cập động

`AccessibleObject` xác định quy tắc assume readability cho **reflected objects**. Không thể suy luận rằng `MethodHandles.Lookup` hoặc mọi bytecode được link động sẽ tự bỏ qua readability. Các cơ chế này có hợp đồng access riêng, và một số thao tác của `MethodHandles` yêu cầu caller có read edge thật.

Khi viết công cụ framework, đừng dùng một phép thử `Method.invoke` thành công để bảo đảm `MethodHandles.privateLookupIn` sẽ thành công. Hãy đánh giá riêng readability, exports, opens và quyền `Lookup` theo API thực tế.

## 9. Chẩn đoán lỗi trong dự án modular thực tế

| Hiện tượng | Điều cần xác minh | Hướng xử lý |
| --- | --- | --- |
| `ModuleLayer.boot().findModule("sample.target")` rỗng | Target chỉ nằm trên module path nhưng không được resolved | Bổ sung `requires` hợp lệ hoặc `--add-modules` khi chạy |
| Java source `import` public class thất bại | Consumer thiếu readability, hoặc target không exports package | Sửa `module-info.java` theo dependency thực |
| `Class.forName(Module, name)` trả `null` | Tên binary sai, class không thuộc module chỉ định, module chưa chứa class | Kiểm tra module, package, binary name và output biên dịch |
| Lấy được `Class<?>` nhưng `newInstance()` ném `IllegalAccessException` | Class/constructor không accessible qua package export | Kiểm tra `Module.isExported`, modifier của class và constructor |
| `getDeclaredMethod` tìm thấy method nhưng `trySetAccessible` trả `false` | Package không opened cho caller hoặc member không thể mở theo hợp đồng | Xem `opens`/`--add-opens`, hạn chế deep reflection |
| `setAccessible(true)` ném `InaccessibleObjectException` | Module không cho suppression access check | Dùng API public được export hoặc mở có chủ đích |
| `canRead(target)` trả `false` nhưng `invoke` thành công | Đúng quy tắc assume readability của core reflection | Không thêm `requires` chỉ để hợp thức hóa reflection nếu không có dependency tĩnh |
| `canRead(target)` vẫn `false` sau reflection | Access check không thay đổi module graph | Dùng `requires`/`--add-reads` nếu thật sự cần cạnh đọc |
| Package `opens` nhưng `isExported` trả `true` | Runtime xem open package là exported tới module được mở | Xem `isOpen` hoặc `ModuleDescriptor.exports()` để phân biệt |
| Test chạy trên classpath không tái hiện lỗi | Caller nằm trong unnamed module, có luật readability khác | Chạy consumer như **named module** trên module path |

### 9.1. Trình tự điều tra khuyến nghị

Khi gặp lỗi reflection, kiểm tra lần lượt:

1. **Đúng module graph?** Target nằm ở module layer nào? Có `--add-modules` hoặc `requires` chưa?
2. **Cạnh đọc thực?** Kiểm tra `consumer.canRead(target)`, nhưng nhớ core reflection chỉ giả định cạnh đọc khi access check.
3. **Đúng package?** Dùng `Class.getPackageName()` và `Class.getModule()` để tìm class nằm trong module/package nào.
4. **Package exported hay opened?** Kiểm tra `target.isExported(p, consumer)` và `target.isOpen(p, consumer)`; đọc descriptor nếu cần phân biệt compile-time và runtime.
5. **Member public hay private?** Kiểm tra modifier và quyền suppression; dùng `canAccess`/`trySetAccessible` thay cho suy đoán.
6. **Đúng API đang gọi?** `Method.invoke` là core reflection; `MethodHandles.Lookup` hoặc một framework tạo bytecode có thể kiểm tra quyền khác.

Không chữa mọi lỗi bằng `--add-opens java.base/...`. Việc mở rộng quyền bừa bãi vừa khó tái lập vừa che cấu hình module sai; với ứng dụng thông thường, sửa `requires`/`exports`/`opens` ở đúng module có chủ đích sẽ rõ ràng và dễ bảo trì hơn.

### 9.2. Vì sao không nên dùng isAccessible()?

`AccessibleObject.isAccessible()` đã bị deprecated vì tên dễ tạo hiểu nhầm: nó chỉ báo trạng thái cờ **suppression of access checks**, không thực sự đánh giá quyền truy cập của caller. Với JDK hiện đại, dùng:

- `canAccess(receiver)` để hỏi caller hiện có quyền truy cập reflected object hay không.
- `trySetAccessible()` để thử bật suppression khi cần, trả về boolean.
- `setAccessible(true)` nếu muốn thao tác thất bại bằng exception khi không thể mở quyền, và chủ động xử lý `InaccessibleObjectException`.

Cần tránh việc bắt `Exception` chung rồi tiếp tục gọi `invoke`, vì sẽ che nguyên nhân thật: lỗi class discovery, module access hay lỗi do method đích ném ra.

## 10. Các câu hỏi tự kiểm tra

**Câu 1.** `sample.consumer` không khai báo `requires sample.target;`, nhưng runtime bổ sung `--add-modules sample.target`. `consumer.canRead(target)` có nhất thiết bằng `true` không?

Không. `--add-modules` bảo đảm target được resolve; nó không tự cấp read edge cho consumer.

**Câu 2.** Tại sao `Method.invoke` thành công trên `ExportedApi.greet()` dù `canRead(target) == false`?

Vì core reflection giả định readability khi kiểm tra access cho `Method`. `ExportedApi` và `greet()` đều public, package được exported, nên quyền truy cập public vẫn hợp lệ. Module graph không bị sửa.

**Câu 3.** Có được gọi `InternalApi` bằng reflection chỉ vì `Class.forName(target, name)` tìm được class?

Không. Discovery không đồng nghĩa access. Package `internal` không exported/opened; `Constructor.newInstance` bị từ chối.

**Câu 4.** Nếu module consumer thêm `requires sample.target;`, private `ExportedApi.secret()` tự trở nên truy cập được không?

Không. `requires` chỉ tạo dependency/readability; private access giữa modules vẫn cần package mở hoặc điều kiện quyền phù hợp theo hợp đồng Java.

**Câu 5.** Vì sao package chỉ có `opens` nhưng `Module.isExported(package, consumer)` vẫn có thể trả `true`?

Javadoc `Module` xem package opened là exported tới module được mở **ở runtime**. Điều đó không phải chỉ thị `exports` trong source, cũng không tạo `requires`.

**Câu 6.** Tại sao không thể suy từ `Method.invoke` thành công rằng `MethodHandles.privateLookupIn` sẽ thành công?

Hai API có hợp đồng access khác nhau. Quy tắc giả định readability được mô tả cụ thể cho core reflection; không tự áp dụng cho mọi `Lookup` của method handles.

## 11. Checklist và bài tập mở rộng

- [ ] Có hai named modules `sample.target` và `sample.consumer`, không dùng unnamed module.
- [ ] Consumer ban đầu không khai báo `requires sample.target;`.
- [ ] Target được resolve trong boot layer bằng `--add-modules sample.target`.
- [ ] `consumer.canRead(target)` là `false` trước và sau khi dùng reflected objects.
- [ ] Public constructor, public method, public field trong exported package truy cập thành công bằng core reflection.
- [ ] Private method của exported-only package không bật được `trySetAccessible`.
- [ ] `setAccessible(true)` trên private method đó ném `InaccessibleObjectException`.
- [ ] `Class.forName(Module, name)` lấy được class trong non-exported package, nhưng tạo instance bị `IllegalAccessException`.
- [ ] Private method trong opened package gọi được khi `trySetAccessible` thành công.
- [ ] Hiểu vì sao `isExported` ở runtime có thể trả `true` cho opened-only package.
- [ ] Thêm `--add-reads` hoặc `requires` khiến `canRead` trở thành `true` mà không tự mở quyền private.
- [ ] Chạy được cùng ví dụ trên JDK 18+ bằng `javac --release 18` và `java --module-path`.

**Bài tập 1 — thay đổi khả năng đọc:** Chạy thí nghiệm ở hai mode không có read edge và có `--add-reads`. Ghi lại `canRead` và từng dòng PASS. Giải thích tại sao kết quả core reflection không đổi trong khi read edge đổi.

**Bài tập 2 — qualified exports:** Đổi `exports sample.target.api;` thành `exports sample.target.api to sample.consumer;`. Xác minh consumer vẫn gọi được public member qua reflection, nhưng một named module khác không nằm trong danh sách nhận export không có cùng quyền.

**Bài tập 3 — qualified opens:** Đổi `opens sample.target.opened;` thành `opens sample.target.opened to sample.consumer;`. Dùng thêm một caller module trong thư mục lab để chứng minh quyền deep reflection được cấp theo module nhận.

**Bài tập 4 — API ranh giới khác:** Thử `MethodHandles.publicLookup()` hoặc `MethodHandles.privateLookupIn(...)` trong một ví dụ riêng, đối chiếu yêu cầu `requires`/`exports`/`opens` của nó với core reflection. Đừng mặc định hai API có cùng quy tắc assume readability.

**Tiêu chí hoàn thành:** Có thể giải thích chính xác khi nào `requires` cần cho code Java thông thường, khi nào core reflection giả định readability, và vì sao điều đó **không** phá ranh giới encapsulation của module đích.

## Tài liệu tham khảo

- [AccessibleObject — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html): quy tắc assume readability của `Field`, `Method` và `Constructor`, `canAccess`, `trySetAccessible` và `setAccessible`.
- [Module — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen` và các thay đổi read/export/open ở runtime.
- [Class — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `Class.forName(Module, String)` không kiểm tra accessibility của class.
- [java.lang.module — Module Resolution](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/package-summary.html): cách tính đồ thị readability và dependency `requires`.
- [java launcher — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `--add-modules`, `--add-reads`, `--add-exports`, `--add-opens`.
- [javac — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--module-source-path`, `--release` và options khi biên dịch modular code.
- [The Java Language Specification, Chapter 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html): khai báo mô-đun, `requires`, `exports` và `opens`.
