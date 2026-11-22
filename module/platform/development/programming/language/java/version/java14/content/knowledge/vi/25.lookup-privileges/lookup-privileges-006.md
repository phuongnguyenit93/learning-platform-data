# Giới hạn truy cập package không `exports` hoặc không `opens` với `MethodHandles.Lookup`

## 1. Vấn đề cần hiểu

Kể từ Java 9, **Java Platform Module System (JPMS)** cho phép một **named module** chỉ định rõ những package nào được công khai cho module khác qua `exports` và những package nào được phép **deep reflection** qua `opens`. Các ranh giới này vẫn là cơ chế bảo vệ hiện hành trên JDK 17, 21, 25 và các phiên bản mới.

Đối với `java.lang.invoke.MethodHandles.Lookup`, quyền truy cập không chỉ dựa vào việc một class hay method mang `public`. Khi code trong **module `m.client`** cố lấy `MethodHandle` để gọi thành viên của class nằm trong **module `m.library`**, JVM xem xét **đồng thời**:

1. **Mối quan hệ đọc module** (*module readability*): `m.client` có đọc `m.library` không?
2. **Package được xuất (*exported*) hay được mở (*opened*) không?** Và quyền đó dành cho module nào?
3. **Class/member có modifier phù hợp không?** `public`, `protected`, package-private hay `private`?
4. **Đối tượng `Lookup` mang những access modes nào?** Một `Lookup` ít quyền không thể truy cập ngoài quyền nó có.
5. **Loại truy cập yêu cầu**: gọi một thành viên `public` qua `findStatic/findVirtual` khác với lấy `private Lookup` bằng `MethodHandles.privateLookupIn`.

**Thông điệp trọng tâm:**

> Một class `public` trong package không `exports` cho caller **không tự trở thành API public liên module**. Và `exports` package **không tương đương `opens`**: export cho truy cập public theo quy tắc module; open dành cho deep reflection, bao gồm việc xin `private Lookup` khi đáp ứng đầy đủ điều kiện.

Bài học này dùng hai **named modules** độc lập, chạy ba lần với **không flag**, `--add-exports` và `--add-opens` để chứng minh sự khác biệt bằng kết quả thực tế. Toàn bộ nguồn demo tương thích **Java 17+**, không dùng API incubator, `sun.misc.Unsafe`, `IMPL_LOOKUP` hay mẹo bỏ kiểm soát truy cập đã lỗi thời.

## 2. Phân biệt bốn khái niệm: `requires`, `exports`, `opens`, `Lookup`

### 2.1. `requires`: khả năng đọc module khác

Ví dụ descriptor của một client:

```java
module m.client {
    requires m.library;
}
```

Điều này tạo mối quan hệ **`m.client` đọc `m.library`**. Nhưng **`requires` không xuất package nào của `m.library`**. Nếu thư viện giữ một package kín, chỉ thêm `requires` không đủ để import/call API trong package đó.

Về mặt runtime:

```java
boolean canRead = ClientClass.class.getModule()
        .canRead(TargetClass.class.getModule());
```

Đây là **trích đoạn** với hai class giả định đã truy cập được trong ngữ cảnh; nó cho biết một mối quan hệ module, **không** tự chứng minh package đã exported/opened.

### 2.2. `exports`: API cho truy cập Java thông thường

Trong `module-info.java` của thư viện:

```java
module m.library {
    exports lib.api;
}
```

`lib.api` có thể được code ở module đọc `m.library` sử dụng theo quy tắc thông thường, **đối với các public types/public members có thể truy cập**. `exports` không biến method `private` hay class package-private thành public.

Có thể giới hạn đích xuất package:

```java
exports lib.api to m.client;
```

Đây là **qualified export**: chỉ các module được nêu mới được xuất package đó theo chính sách module. Tên module phải khớp với module thật, không phải tên JAR hay tên package của consumer.

### 2.3. `opens`: cho phép deep reflection

Ví dụ:

```java
module m.library {
    opens lib.model to m.client;
}
```

Package `lib.model` **không nhất thiết có mặt như API public tại thời điểm biên dịch code client**. Nhưng nó được **mở tại runtime cho `m.client`** để các API reflection thích hợp có thể kiểm tra/truy cập non-public members.

Theo hợp đồng `MethodHandles.privateLookupIn`, khi caller ở module khác, cần package **được mở** tới caller, caller có đầy đủ quyền `PRIVATE` và `MODULE`, đồng thời caller module **đọc** target module.

Có thể khai báo:

```java
opens lib.model;
```

để mở package **không giới hạn module đích**. Chỉ nên làm vậy nếu thật sự muốn mở rộng quyền reflection. Trong framework lớn, ưu tiên **qualified opens** đến module cụ thể thay vì mở hết cho mọi module.

### 2.4. `Lookup` là một capability, không phải tên lớp được phép truy cập

`MethodHandles.Lookup` biểu diễn **ngữ cảnh và quyền truy cập** dùng khi JVM tạo `MethodHandle` hoặc truy cập kiểu/class liên quan.

```java
MethodHandles.Lookup caller = MethodHandles.lookup();
```

`lookup()` là **caller-sensitive**: lookup mang ngữ cảnh của class **thực sự gọi** method. Không nên tạo một lookup có quyền cao trong thư viện rồi đưa tùy tiện cho caller không tin cậy. Ai giữ lookup có thể có quyền truy cập tương ứng với capability mà nó biểu diễn.

Khác với `MethodHandle` đã tạo thành công, `Lookup` còn có nhiệm vụ kiểm tra **quyền khi tìm member**; một handle đã được cấp có thể được gọi theo contract của chính handle, nhưng việc có được handle từ đầu đòi hỏi access check hợp lệ.

## 3. Bảng quyết định khi caller ở module khác

Giả sử code `m.client` **đọc được `m.library`**, class đích là `public`, có một method `public static` và một method `private static`:

| Trạng thái của package trong `m.library` đối với `m.client` | Gọi method public bằng `lookup().findStatic(...)` | Lấy `privateLookupIn` và truy cập private | Được import package lúc compile? |
| --- | --- | --- | --- |
| Không `exports`, không `opens` | **Không** | **Không** | **Không** |
| Chỉ `exports pkg to m.client` | **Có** | **Không** | **Có**, nếu class/member đủ public |
| Chỉ `opens pkg to m.client` | **Có ở runtime** với caller Lookup phù hợp | **Có**, nếu đọc module và caller có quyền đầy đủ | **Không**, vì open không phải export compile-time |
| Vừa `exports` vừa `opens` tới client | **Có** | **Có**, nếu các điều kiện của `privateLookupIn` được đáp ứng | **Có** |
| `exports pkg;` công khai, không `opens` | **Có** | **Không** cho caller ở module khác | **Có** |

**Sắc thái dễ nhầm:** theo API `Module.isExported(package, other)`, một package **được mở đến `other` cũng được coi là exported đến `other` ở *runtime***. Vì vậy với `--add-opens`, `Module.isExported(...)` có thể trả `true`, dù `module-info.java` không chứa một chỉ thị `exports` mới và **không** vì thế mà compiler của một dự án khác tự được phép import package kín.

Bảng giả định target class/method đủ `public` cho truy cập public. Nếu target class là package-private hoặc method là private thì `exports` không thay đổi Java access modifiers; cần một ngữ cảnh đặc quyền hợp lệ, không chỉ một flag export.

## 4. Các API `Lookup` liên quan

### 4.1. `MethodHandles.lookup()`

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

Đối tượng này có ngữ cảnh của class gọi và thông thường có quyền đầy đủ **trong phạm vi class của caller**. Khi chuyển sang module khác, nó vẫn bị chi phối bởi **module readability**, `exports`/`opens` và quyền của class/member.

Ví dụ:

```java
MethodHandle h = lookup.findStatic(
        SomeClass.class,
        "message",
        MethodType.methodType(String.class)
);
```

Đoạn minh họa trên cần có `SomeClass` truy cập hợp lệ và import `java.lang.invoke`. Nếu class nằm trong module khác có package không exported cho caller, việc tìm handle public có thể thất bại với `IllegalAccessException`.

### 4.2. `MethodHandles.publicLookup()`

```java
MethodHandles.Lookup minimal = MethodHandles.publicLookup();
```

`publicLookup()` có quyền **UNCONDITIONAL** tối thiểu: có thể tìm public members của public classes trong **package được exported vô điều kiện**. Nó **không** là lối đi vòng quanh `exports`/`opens`. Một qualified export/open chỉ cấp cho module cụ thể không biến package thành **unconditionally exported** để `publicLookup` dùng tùy ý.

Khi xây framework, cần chọn API theo quyền thực sự của caller, không mặc định `publicLookup()` “có mọi quyền public”.

### 4.3. `Lookup.in(target)`

```java
MethodHandles.Lookup narrowed = lookup.in(targetClass);
```

`Lookup.in(...)` thay đổi lookup class theo giới hạn API nhưng **không nâng quyền**. Chuyển sang class khác package/module có thể làm **mất** các modes như `PACKAGE`, `PRIVATE` hoặc `MODULE`. Dùng nó không thể “nhảy” vào một non-exported package để mở các private members.

Không nên viết logic bảo mật với giả định `lookup.in(secretType)` tự có quyền của `secretType`.

### 4.4. `MethodHandles.privateLookupIn(targetClass, callerLookup)`

```java
MethodHandles.Lookup privileged =
        MethodHandles.privateLookupIn(targetClass, MethodHandles.lookup());
```

**Để truy cập sâu xuyên hai named modules**, tất cả điều kiện phải đúng:

1. `targetClass` là class tham chiếu hợp lệ, không phải primitive type, `void` hay array.
2. `callerLookup` mang quyền **`PRIVATE`** và **`MODULE`**.
3. Caller module **đọc** target module.
4. Target module **opens** package chứa target class **cho caller module**.

Nếu không đáp ứng kiểm tra truy cập, `privateLookupIn` có thể ném `IllegalAccessException`. Nếu đối số class không hợp lệ như primitive/array, có thể ném `IllegalArgumentException`.

Với caller/target **cùng module**, điều kiện cross-module open/read không đặt ra theo cách tương tự; tuy nhiên vẫn cần khả năng lookup hợp lệ. Khi `privateLookupIn` chuyển qua module khác thành công, lookup kết quả có `PRIVATE` nhưng **mất `MODULE` mode**; không thể dùng nó làm một “master key” liên tiếp để mở private lookup ở module thứ ba.

**Cảnh báo an toàn:** private lookup là một capability mạnh. Javadoc lưu ý một lookup được cấp trên package opened còn có khả năng định nghĩa class theo những quy tắc API nhất định. Chỉ mở package cho module thực sự tin cậy và cần quyền.

## 5. Dự án thực hành: hai module, ba mức quyền

Chúng ta tạo:

- **`m.library`**: module chứa API public, package kín và package có qualified opens.
- **`m.client`**: module sử dụng, có `requires m.library`.
- Client sẽ dùng `Class.forName` để có một `Class<?>` của package kín, **không import `lib.hidden.SecretBox` trực tiếp**. Việc tải class và việc truy cập member là hai kiểm tra khác nhau.

Cây source:

```text
lookup-lab/
├── src/
│   ├── m.library/
│   │   ├── module-info.java
│   │   └── lib/
│   │       ├── api/Greeting.java
│   │       ├── hidden/SecretBox.java
│   │       └── model/OpenedBox.java
│   └── m.client/
│       ├── module-info.java
│       └── client/Main.java
└── mods/              ← được javac tạo
```

**Đây là ứng dụng modular thực sự**, không phải ví dụ hai package chạy trên classpath. Nếu đặt toàn bộ class trong một unnamed module, hành vi module export/open sẽ khác và không tái hiện được thí nghiệm.

### 5.1. File `src/m.library/module-info.java`

```java
module m.library {
    exports lib.api;
    opens lib.model to m.client;
}
```

Giải thích:

- `lib.api`: **exported vô điều kiện**, dùng được cho client đọc thư viện và có quyền truy cập API public.
- `lib.model`: **opened riêng cho `m.client`**, cho phép `privateLookupIn` khi đủ điều kiện nhưng không là public API compile-time cho mọi module.
- `lib.hidden`: **không exports, không opens**; module client không có quyền public member lookup hoặc deep lookup xuyên module theo mặc định.

### 5.2. File `src/m.library/lib/api/Greeting.java`

```java
package lib.api;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "hello";
    }
}
```

Class và method là `public`, package `lib.api` đã exported. Client có thể import `lib.api.Greeting` bình thường hoặc dùng `Lookup.findStatic`.

### 5.3. File `src/m.library/lib/hidden/SecretBox.java`

```java
package lib.hidden;

public final class SecretBox {
    public static String publicMessage() {
        return "hidden-public";
    }

    private static String secret() {
        return "hidden-secret";
    }
}
```

Cả class và method `publicMessage` đều là `public`, nhưng **package `lib.hidden` không được exported/opened**. Bởi vậy `public` không đủ để caller ở module khác truy cập.

Method `secret` còn có `private`; chỉ `--add-exports` sẽ không làm nó truy cập được bằng `privateLookupIn` từ bên ngoài. Cần package opened và capability phù hợp.

### 5.4. File `src/m.library/lib/model/OpenedBox.java`

```java
package lib.model;

public final class OpenedBox {
    private static String secret() {
        return "opened-secret";
    }
}
```

`lib.model` được `opens ... to m.client`, nên client có thể lấy private lookup và truy cập method `secret` tại runtime. **Không phải** vì method private bị đổi thành public; đó là quyền deep reflection được chủ sở hữu module mở có chủ đích.

### 5.5. File `src/m.client/module-info.java`

```java
module m.client {
    requires m.library;
}
```

`requires` tạo quan hệ **đọc** cần thiết nhưng không làm các package kín của `m.library` tự động exported.

### 5.6. File `src/m.client/client/Main.java`

```java
package client;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class Main {
    @FunctionalInterface
    interface Action {
        String call() throws Throwable;
    }

    static void test(String key, Action action) {
        try {
            System.out.println(key + "=" + action.call());
        } catch (Throwable ex) {
            System.out.println(key + "=DENIED:"
                    + ex.getClass().getSimpleName());
        }
    }

    static String publicCall(String className, String methodName)
            throws Throwable {
        Class<?> type = Class.forName(className);

        MethodHandle handle = MethodHandles.lookup().findStatic(
                type, methodName, MethodType.methodType(String.class));

        return (String) handle.invokeWithArguments();
    }

    static String privateCall(String className) throws Throwable {
        Class<?> type = Class.forName(className);

        MethodHandles.Lookup privileged =
                MethodHandles.privateLookupIn(
                        type, MethodHandles.lookup());

        MethodHandle handle = privileged.findStatic(
                type, "secret", MethodType.methodType(String.class));

        return (String) handle.invokeWithArguments();
    }

    public static void main(String[] args) throws Exception {
        Class<?> hidden = Class.forName("lib.hidden.SecretBox");
        Module library = hidden.getModule();
        Module client = Main.class.getModule();

        System.out.println("readsLibrary="
                + client.canRead(library));
        System.out.println("apiExported="
                + library.isExported("lib.api", client));
        System.out.println("hiddenExported="
                + library.isExported("lib.hidden", client));
        System.out.println("hiddenOpened="
                + library.isOpen("lib.hidden", client));
        System.out.println("modelOpened="
                + library.isOpen("lib.model", client));
        System.out.println("hiddenLoaded=" + (hidden != null));

        test("apiPublic",
                () -> publicCall("lib.api.Greeting", "message"));
        test("hiddenPublic",
                () -> publicCall("lib.hidden.SecretBox", "publicMessage"));
        test("hiddenPrivate",
                () -> privateCall("lib.hidden.SecretBox"));
        test("openedPrivate",
                () -> privateCall("lib.model.OpenedBox"));
    }
}
```

**Mục đích chương trình:**

- `Class.forName("lib.hidden.SecretBox")` thử **tải class** bằng tên, không tự động đọc field/method private hay nhận quyền access package.
- `MethodHandles.lookup().findStatic(...)` kiểm tra quyền truy cập **public member** trong ngữ cảnh `client.Main`.
- `MethodHandles.privateLookupIn(...)` thử lấy lookup có quyền private; đây là bước có thể bị module system từ chối **trước** khi tìm method private.
- `Module.isExported(package, client)` và `isOpen(package, client)` cung cấp trạng thái access ở **runtime** với client cụ thể.
- Helper `test` chủ động bắt `Throwable` để demo in tên exception gọn. **Không nên bắt mọi `Throwable` trong ứng dụng production**: error nghiêm trọng như `OutOfMemoryError` thường cần được xử lý theo chính sách riêng. Việc bắt rộng ở đây chỉ để quan sát khác biệt các test case có chủ ý.

## 6. Biên dịch 2 module bằng Java 17+ và chạy mặc định

Đặt terminal tại thư mục `lookup-lab`. Tạo cấu trúc và lưu đúng sáu file vào các path nêu ở mục 5.

**Linux/macOS với shell POSIX** (khi các tên source path không có dấu cách):

```bash
mkdir -p mods
javac --release 17 \
    --module-source-path src \
    -d mods \
    $(find src -name '*.java')

java --module-path mods --module m.client/client.Main
```

Nếu dự án có tên file/thư mục chứa dấu cách, nên dùng build tool hoặc truyền file paths bằng cách tương thích shell, không dựa vào word splitting của `$(find ...)`. Đây chỉ là demo nhỏ với path đơn giản.

**PowerShell trên Windows**:

```powershell
New-Item -ItemType Directory -Path mods -Force | Out-Null

$javaFiles = Get-ChildItem -Path src -Recurse -Filter "*.java" |
        ForEach-Object { $_.FullName }

javac --release 17 --module-source-path src -d mods $javaFiles
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

java --module-path mods --module m.client/client.Main
```

**Kết quả đã biên dịch/chạy bằng OpenJDK 21 với `--release 17`**, khi không thêm quyền:

```text
readsLibrary=true
apiExported=true
hiddenExported=false
hiddenOpened=false
modelOpened=true
hiddenLoaded=true
apiPublic=hello
hiddenPublic=DENIED:IllegalAccessException
hiddenPrivate=DENIED:IllegalAccessException
openedPrivate=opened-secret
```

### 6.1. Vì sao những kết quả này đúng?

- **`readsLibrary=true`**: `requires m.library` cho phép client đọc module thư viện.
- **`apiExported=true`**: `lib.api` được exported, nên lookup tìm method public `Greeting.message` thành công → `hello`.
- **`hiddenExported=false` và `hiddenOpened=false`**: package `lib.hidden` hoàn toàn kín với `m.client`.
- **`hiddenLoaded=true`**: class tồn tại trong module đã resolved và JVM có thể nạp nó qua `Class.forName`. **Nạp class thành công không chứng minh được access member thành công.**
- **`hiddenPublic=DENIED:IllegalAccessException`**: dù `SecretBox` và `publicMessage` là public, module không export package cho caller.
- **`hiddenPrivate=DENIED:IllegalAccessException`**: `privateLookupIn` thất bại vì package `lib.hidden` không được mở cho client.
- **`modelOpened=true` và `openedPrivate=opened-secret`**: `lib.model` được qualified open tới `m.client`; client có full caller lookup và đọc target module, nên private lookup thành công.

Khi debug, hãy đọc **exception type và nơi phát sinh**. Với `Lookup.findStatic`, access check có thể ném `IllegalAccessException`; đừng dùng `ClassNotFoundException` như dấu hiệu duy nhất của package được bảo vệ.

## 7. Thử `--add-exports`: chỉ làm package có API public đối với client

Chạy lại **cùng class files**, chỉ thay lệnh chạy:

```bash
java --add-exports m.library/lib.hidden=m.client \
    --module-path mods \
    --module m.client/client.Main
```

**Stdout đã xác minh:**

```text
readsLibrary=true
apiExported=true
hiddenExported=true
hiddenOpened=false
modelOpened=true
hiddenLoaded=true
apiPublic=hello
hiddenPublic=hidden-public
hiddenPrivate=DENIED:IllegalAccessException
openedPrivate=opened-secret
```

### 7.1. Phân tích

`--add-exports m.library/lib.hidden=m.client` chỉ định:

- Module nguồn: `m.library`.
- Package nguồn: `lib.hidden`.
- Module được hưởng quyền public access: `m.client`.

Kết quả:
- `Module.isExported("lib.hidden", client)` thành **true**.
- `Lookup.findStatic` trên public class/public method của `lib.hidden` thành công.
- `Module.isOpen("lib.hidden", client)` vẫn là **false**.
- `privateLookupIn` vẫn bị `IllegalAccessException`.

Đây là phép thử trực tiếp rằng **export ≠ open**. Việc thành viên mang `private` không biến mất chỉ vì dùng flag export.

**Lưu ý build:** `--add-exports` là option có thể có ý nghĩa ở môi trường compile/runtime phù hợp. Trong demo, client **không import package kín** và class đã biên dịch sẵn, nên flag chỉ cần truyền khi **chạy**. Nếu thực sự muốn compile source dùng `import lib.hidden.SecretBox`, cần thiết kế `exports` phù hợp trong module descriptor hoặc cấu hình biên dịch chủ động, thay vì kỳ vọng runtime flag tự làm compiler chấp nhận source.

## 8. Thử `--add-opens`: cho phép deep reflection ở runtime

Chạy lần thứ ba:

```bash
java --add-opens m.library/lib.hidden=m.client \
    --module-path mods \
    --module m.client/client.Main
```

**Stdout đã xác minh:**

```text
readsLibrary=true
apiExported=true
hiddenExported=true
hiddenOpened=true
modelOpened=true
hiddenLoaded=true
apiPublic=hello
hiddenPublic=hidden-public
hiddenPrivate=hidden-secret
openedPrivate=opened-secret
```

### 8.1. Điều gì thay đổi?

`--add-opens m.library/lib.hidden=m.client` cho phép **deep reflection của `m.client`** lên `lib.hidden` trong `m.library` ở runtime:

- `Module.isOpen("lib.hidden", client)` chuyển thành **true**.
- `MethodHandles.privateLookupIn(SecretBox.class, MethodHandles.lookup())` nay có thể thành công nếu caller có `PRIVATE`+`MODULE` và read edge.
- Client tìm method `private static secret()` qua lookup đã được cấp và gọi thành công → `hidden-secret`.
- `Module.isExported("lib.hidden", client)` cũng trả **true tại runtime**, vì API `Module.isExported(package, other)` coi package đã mở cho `other` là exported ở runtime.

**Cực kỳ quan trọng:** `--add-opens` **không** biến `lib.hidden` thành API được exports trong source descriptor. Một dòng `import lib.hidden.SecretBox;` trong code client **vẫn không được biên dịch hợp lệ chỉ dựa vào một runtime opens**.

### 8.2. Nên dùng flag như thế nào?

`--add-opens` và `--add-exports` giúp:

- Chẩn đoán nguyên nhân `IllegalAccessException` và xác nhận giả thuyết về module boundary.
- Cấu hình truy cập của framework được cho phép bởi tổ chức, khi thư viện chưa cung cấp chính sách module phù hợp.
- Di trú ứng dụng cần một giai đoạn tương thích, có kế hoạch chuyển sang API/module descriptor phù hợp.

Chúng **không** nên là giải pháp mặc định mở rộng toàn bộ thư viện lâu dài. Ưu tiên **`exports` API công khai** hoặc **`opens ... to framework.module`** có đích rõ ràng trong `module-info.java`. Trong ứng dụng đóng gói, ghi nhận flags vào cấu hình runtime/build và kiểm thử sau nâng cấp JDK.

### 8.3. Trường hợp ứng dụng client chạy trên classpath

Nếu consumer không phải named module mà thuộc **unnamed module**, đích option có thể là **`ALL-UNNAMED`**, ví dụ:

```bash
java --add-opens m.library/lib.hidden=ALL-UNNAMED ...
```

Dấu `...` trong dòng trên là **ký hiệu minh họa** cho các options khác; không phải một lệnh runnable độc lập. Khi consumer là **named module `m.client`** trong demo, phải dùng `=m.client`. Đừng cấp `ALL-UNNAMED` nếu chỉ một named module được phép truy cập.

## 9. Vì sao `Class.forName` thành công nhưng `Lookup.findStatic` lại thất bại?

Dòng code:

```java
Class<?> type = Class.forName("lib.hidden.SecretBox");
```

chỉ yêu cầu JVM **tìm và nạp class** theo tên trong môi trường đã resolve module phù hợp. Nó **không** có nghĩa caller được phép:

- Viết một `import` từ package không exported tại compile time.
- Tạo một method handle tới public member trong package kín.
- Gọi private method hoặc truy cập private field.
- Định nghĩa class trong package target.
- Tự có lookup mang quyền của target class.

Vì vậy:

```java
Class<?> hidden = Class.forName("lib.hidden.SecretBox");
MethodHandle handle = MethodHandles.lookup().findStatic(
        hidden, "publicMessage", MethodType.methodType(String.class));
```

Đoạn trên **có thể tải class** nhưng bị từ chối ở bước **`findStatic`** theo luật export/access. Bài demo chứng minh chính xác: `hiddenLoaded=true` cùng với `hiddenPublic=DENIED:IllegalAccessException` trong lần chạy mặc định.

Trong ứng dụng khác, `Class.forName` cũng có thể thất bại do module không resolved, class không tồn tại, dependency/class loader hoặc lỗi khởi tạo. Không nên suy ra `Class.forName` luôn thành công bất kể module boundary; demo thành công vì `m.client requires m.library` và class có mặt trên module path.

## 10. Tra cứu trạng thái module bằng API hiện hành

`java.lang.Module` cung cấp các phép kiểm tra:

| API | Câu hỏi nó trả lời |
| --- | --- |
| `client.canRead(library)` | Client hiện có thể đọc module library không? |
| `library.isExported("lib.api", client)` | Package có được exported cho client ở runtime không? |
| `library.isExported("lib.api")` | Package có được exported **vô điều kiện** ở runtime không? |
| `library.isOpen("lib.model", client)` | Package có được opened cho client ở runtime không? |
| `library.isOpen("lib.model")` | Package có được opened **vô điều kiện** ở runtime không? |
| `someClass.getModule()` | Class nằm trong module nào? |
| `lookup.lookupClass()` | Lookup hiện mang lookup class nào? |
| `lookup.lookupModes()` | Những access-mode bits nào vẫn còn? |
| `lookup.hasFullPrivilegeAccess()` | Lookup có đầy đủ quyền tương ứng với khái niệm full privilege theo API không? |

**Đọc kết quả chính xác:**

- `isExported(package, client)` **không tự kiểm tra client có đọc module hay không**. Muốn đánh giá quyền caller cần xét thêm `client.canRead(library)` và modifiers.
- Một package **được opens cho client** được coi **exported tới client ở runtime** theo định nghĩa của `isExported(package, other)`. Vì vậy không dùng `isExported` để kết luận chắc chắn source `module-info.java` có dòng `exports`.
- `isOpen(package, client)` **không tự kiểm tra client đọc module hay không**. Hai điều kiện cần tách rõ.
- `lookupModes()` cho biết capability của một `Lookup`, không thay thế việc kiểm tra target member/class. Các flags như `PUBLIC`, `PRIVATE`, `PACKAGE`, `MODULE`, `ORIGINAL` và `UNCONDITIONAL` có quy tắc riêng.

Dùng `Module.getDescriptor()` khi cần đọc metadata descriptor gốc, nhưng phân biệt metadata đó với các quyền hiệu lực có thể bị thay đổi bởi **command-line overrides** hoặc runtime module APIs.

## 11. `exports` và `opens` khác nhau cả ở compile-time

Giả sử code client viết:

```java
// CỐ Ý SAI với module-info.java trong demo:
import lib.hidden.SecretBox;

public class CompileErrorExample {
    public static void main(String[] args) {
        System.out.println(SecretBox.publicMessage());
    }
}
```

Với `lib.hidden` không được `exports`, compiler sẽ từ chối package không visible tới module `m.client` (message nguyên văn có thể khác giữa JDK). Mở package bằng `opens lib.hidden to m.client` hoặc chỉ truyền `--add-opens` khi **chạy** không biến đoạn import thành API compile-time.

Trái lại, source client có thể:

```java
import lib.api.Greeting;

String message = Greeting.message();
```

Đây là **trích đoạn hợp lệ đặt trong một method** của module `m.client`, vì `lib.api` được exported và `Greeting/message` đều public.

**Kết luận:** API public thông thường nên được thiết kế qua `exports`; mở sâu reflection cho serialization/DI/testing nên được thiết kế qua `opens` có phạm vi rõ ràng. Không dùng `opens` thay thế `exports` chỉ vì muốn compiler được phép import package.

## 12. Những lỗi và exception liên quan

### 12.1. `IllegalAccessException` từ method handle lookup

Trường hợp thường gặp:

```java
lookup.findStatic(type, "publicMessage",
        MethodType.methodType(String.class));
```

Nếu target module không xuất/mở package phù hợp cho caller hoặc modifiers không cho phép, `Lookup.findStatic` có thể ném **`IllegalAccessException`**. Demo cố ý giữ nguyên nguyên nhân và chỉ in tên exception cho dễ đối chiếu.

### 12.2. `IllegalAccessException` từ `privateLookupIn`

```java
MethodHandles.privateLookupIn(type, MethodHandles.lookup());
```

Nếu package của target nằm ở module khác mà **không opened** cho caller, phương thức này bị từ chối. Cũng vậy, nếu lookup được truyền **thiếu quyền `PRIVATE` hoặc `MODULE`**, nó không được phép lấy full private access qua cross-module.

Đừng sửa bằng `publicLookup()` vì lookup này **ít quyền hơn**, không phải nhiều quyền hơn.

### 12.3. `NoSuchMethodException` không phải `IllegalAccessException`

Nếu method không tồn tại hoặc chữ ký `MethodType` không khớp, có thể xuất hiện `NoSuchMethodException` thay vì vấn đề module. Ví dụ `findStatic(type, "secret", methodType(int.class))` không khớp method trả `String`.

Khi debug, cần đối chiếu **tên, static/instance, parameter types, return type** trước khi kết luận cần `--add-opens`.

### 12.4. `InaccessibleObjectException` trong reflection

Với `java.lang.reflect.AccessibleObject.setAccessible(true)` trên member ở package không được opened thích hợp, JDK có thể ném **`java.lang.reflect.InaccessibleObjectException`**. Đó là API reflection khác với `MethodHandles.Lookup`; không nên lấy exception message của reflection áp đặt cho mọi method handle lookup.

### 12.5. `IllegalAccessError` khi liên kết bytecode

Khác với checked exception `IllegalAccessException` khi API tìm handle, `IllegalAccessError` có thể xuất hiện khi JVM **resolve/link một symbolic reference** mà quyền truy cập không hợp lệ tại runtime. Phải phân biệt lỗi này với `ClassNotFoundException` hoặc `NoClassDefFoundError` do thiếu class/module.

## 13. Cách gỡ lỗi package không xuất hoặc không mở

Một quy trình có thể áp dụng cho dự án nhiều module:

**Bước 1 — Xác định module caller và target.**

```java
Module caller = SomeCaller.class.getModule();
Module target = targetClass.getModule();
System.out.println(caller.getName());
System.out.println(target.getName());
```

Trích đoạn cần có biến/class thực tế phù hợp; `getName()` trả null nếu module là unnamed, nên xử lý trường hợp classpath riêng.

**Bước 2 — Kiểm tra readability.**

```java
boolean readable = caller.canRead(target);
```

Nếu false, xem `requires`, module resolution, cách chạy module path và hướng read edge, trước khi tập trung vào export/open.

**Bước 3 — Kiểm tra package access đúng target.**

```java
String pkg = targetClass.getPackageName();
boolean exported = target.isExported(pkg, caller);
boolean opened = target.isOpen(pkg, caller);
```

Phân biệt **exported runtime** và **opened runtime**. Chỉ cần public member lookup thì export có thể đủ; private access xuyên module thường cần open.

**Bước 4 — Kiểm tra lookup có quyền gì.**

```java
MethodHandles.Lookup lk = MethodHandles.lookup();
System.out.println(lk.lookupClass());
System.out.println(lk.lookupModes());
```

Nếu lấy lookup do bên thứ ba truyền vào, đừng giả định nó vẫn có `MODULE`/`PRIVATE`. `Lookup.in` hoặc chuyển qua nhiều module có thể hạ quyền.

**Bước 5 — Xác nhận method signature.**

```java
MethodType type = MethodType.methodType(String.class);
```

Nếu tên method, `static`/instance hoặc chữ ký không khớp, lỗi không phải do `exports`. Xem API docs, public types và parameter/return type thực.

**Bước 6 — Tái hiện có kiểm soát.**

Chạy lần lượt không flag, `--add-exports ...=m.client`, `--add-opens ...=m.client`. Sự khác biệt giữa public member và private lookup giúp xác định đúng loại quyền thiếu. Sau đó chọn **thiết kế module lâu dài** thay vì phụ thuộc một flag quá rộng.

**Bước 7 — Kiểm thử trong bản đóng gói thực.**

Đảm bảo các named modules thật sự nằm trên module path/runtime image, module client reads target và các JVM flags cần thiết được truyền khi chạy ứng dụng. Không coi thử nghiệm classpath/IDE là đại diện chính xác cho cấu hình named modules trong image/production.

## 14. Quyền Lookup là vấn đề bảo mật và thiết kế API

Một `Lookup` có quyền mạnh là **capability** nên được quản lý như một tài nguyên có quyền hạn, không phải object cấu hình vô hại. Hãy:

- **Giữ package kín nếu không có API công khai cần xuất.** Nếu API dùng cho khách hàng, chỉ xuất package thật sự cần bằng `exports`.
- **Chỉ mở package cho module được tin cậy.** Với serialization hoặc DI framework, `opens p to framework.module` thường an toàn hơn mở `opens p;` vô điều kiện.
- **Không công khai full-privilege Lookup cho code không tin cậy.** Kiểm soát API nhận/trả `Lookup` hoặc `MethodHandle` chứa quyền truy cập nhạy cảm.
- **Không dùng `MethodHandles.Lookup.IMPL_LOOKUP`**, reflective hacks hay `--illegal-access` như giải pháp. Cơ chế `--illegal-access` không còn giúp vượt strong encapsulation JDK internals trên các JDK hiện đại; nên sử dụng API/chính sách module chính thức.
- **Không dùng `--add-opens ...=ALL-UNNAMED` khi chỉ một named module cần quyền.** Cấp đích càng hẹp càng tốt.
- **Không biến private fields thành “API ổn định”.** Deep reflection có thể làm tăng coupling khi internal implementation thay đổi.
- **Không trộn quyền Java module với quyền filesystem.** `opens` không cấp quyền đọc file; `exports` không làm chương trình có quyền administrator.

Với những yêu cầu công khai hóa API lâu dài, cân nhắc xây lớp facade/adapter nằm trong exported package hoặc interface service phù hợp, tránh để consumer phụ thuộc vào private implementation của thư viện.

## 15. Lỗi tư duy thường gặp

### Lỗi A — Class `public` ở package kín thì bên ngoài truy cập được

Sai. `public` không bỏ qua ranh giới của **named module**. Trong demo, `SecretBox.publicMessage` là public nhưng `hiddenPublic=DENIED:IllegalAccessException` khi chưa export/open.

### Lỗi B — `requires m.library` nghĩa là đọc được mọi package

Sai. `requires` tạo **read edge**, không xuất các package kín. Chỉ `lib.api` trong demo được exported vô điều kiện.

### Lỗi C — `exports` cho phép private reflection

Sai. Chạy với `--add-exports` làm `hiddenPublic` thành công nhưng `hiddenPrivate` vẫn bị từ chối.

### Lỗi D — `opens` tương đương export compile-time

Sai. `opens` chủ yếu dành cho deep reflection **runtime**. `Module.isExported(package, client)` có thể true tại runtime do open, nhưng Java compiler không vì vậy tự cho import package không exported trong source.

### Lỗi E — `Class.forName` đã thành công tức là được phép gọi method

Sai. Class loading và member access khác nhau. Demo cho thấy `hiddenLoaded=true` nhưng `findStatic` bị từ chối.

### Lỗi F — `MethodHandles.publicLookup()` có mọi quyền truy cập public

Sai. `publicLookup()` bị giới hạn vào public members của public types trong package **được exported vô điều kiện**, không vượt qua qualified module boundaries.

### Lỗi G — `lookup.in(target)` tự nâng quyền sang target

Sai. `Lookup.in` không tăng access modes, thậm chí có thể làm mất `PRIVATE`, `PACKAGE` và `MODULE`.

### Lỗi H — Một private lookup đã lấy được có thể mở mọi module khác

Sai. `privateLookupIn` xuyên module thành công làm mất `MODULE` trong lookup kết quả, nên không thể tiếp tục dùng như master key xin private lookup mới ở module thứ ba.

### Lỗi I — Mọi lỗi lookup đều do `opens`

Sai. Có thể do class/method không tồn tại, sai `MethodType`, thiếu read edge, method không `static` hoặc lookup modes không phù hợp. Kiểm tra exception cụ thể.

### Lỗi J — Dùng `--add-opens` vĩnh viễn là giải pháp sạch nhất

Không nhất thiết. Nó mở thêm quyền runtime, có thể làm giảm tính đóng gói. Ưu tiên thiết kế `exports`/`opens` có chủ đích trong module descriptor hoặc API chính thức; dùng flag có phạm vi hẹp khi cần tương thích.

## 16. Bài tập tự đánh giá

**Câu 1.** `module m.client { requires m.library; }` đã đủ để gọi `lib.hidden.SecretBox.publicMessage()` chưa?

**Đáp án:** Chưa. Client có read edge nhưng `lib.hidden` không được exported/opened tới client.

**Câu 2.** Trong baseline, vì sao `hiddenLoaded=true` nhưng `hiddenPublic` bị `IllegalAccessException`?

**Đáp án:** Tải class bằng `Class.forName` không cấp quyền truy cập member. `Lookup.findStatic` thực hiện access checks của module/package và từ chối package kín.

**Câu 3.** Khi thêm `--add-exports m.library/lib.hidden=m.client`, điều gì được phép?

**Đáp án:** Public member access trong package đó tới `m.client` theo quy tắc access. Demo trả `hiddenPublic=hidden-public`, nhưng `hiddenPrivate` vẫn bị từ chối.

**Câu 4.** Vì sao `--add-opens` cho phép private lookup thành công?

**Đáp án:** Vì package được mở cho caller, caller có `PRIVATE`+`MODULE` modes và module đọc target. Demo trả `hiddenPrivate=hidden-secret`.

**Câu 5.** Vì sao `hiddenExported=true` khi dùng `--add-opens` mà không có `exports` trong descriptor?

**Đáp án:** `Module.isExported(package, other)` tính package opened như exported cho `other` **ở runtime**, không đồng nghĩa export compile-time.

**Câu 6.** `privateLookupIn` có đủ quyền nếu caller dùng `MethodHandles.publicLookup()` không?

**Đáp án:** Không. `publicLookup()` không có quyền `PRIVATE` và `MODULE` để dùng như caller lookup cần thiết cho private lookup xuyên module.

**Câu 7.** `lookup.in(targetClass)` có thể tăng quyền không?

**Đáp án:** Không. Nó không tăng capability, và chuyển sang module/package khác có thể làm mất một số modes.

**Câu 8.** Có thể dùng chỉ `opens lib.model to m.client;` rồi import `lib.model.OpenedBox` trong source client không?

**Đáp án:** Không chỉ vì `opens`. Compiler cần package exported phù hợp để import, trừ khi có cấu hình compile-time access đặc biệt và được kiểm soát. Deep reflection runtime có thể dùng `Class.forName`/`privateLookupIn` như demo.

**Câu 9.** Khác nhau giữa `IllegalAccessException` và `NoSuchMethodException` khi tìm handle?

**Đáp án:** Một lỗi phản ánh access check; lỗi còn lại có thể phản ánh method/signature không tìm thấy. Không vội mở package khi sai `MethodType`.

**Câu 10.** Consumer đang ở classpath (unnamed module), phải dùng đích flag nào nếu cần tạm mở package?

**Đáp án:** `ALL-UNNAMED` cho các unnamed modules, nhưng chỉ sử dụng khi thực sự cần; với named module cụ thể, chỉ định tên module thay vì mở rộng toàn bộ classpath.

## 17. Checklist trước khi kết luận một lỗi `Lookup`

- [ ] Xác định class caller và target thực sự thuộc **named/unnamed module** nào.
- [ ] Kiểm tra read edge (`requires`, `Module.canRead`) giữa hai module.
- [ ] Phân biệt package exported, opened, qualified hay hoàn toàn kín.
- [ ] Kiểm tra access modifiers của class/member, không chỉ nhìn từ khóa `public`.
- [ ] Kiểm tra lookup class/modes, đặc biệt `PRIVATE` và `MODULE` trước `privateLookupIn`.
- [ ] Dùng `Module.isExported(package, callerModule)` và `isOpen`, nhớ runtime opens có thể làm `isExported` true.
- [ ] Tách class loading (`Class.forName`) khỏi member access (`findStatic`/`findVirtual`).
- [ ] Kiểm tra tên, static/instance và `MethodType` trước khi đổi module config.
- [ ] Dùng thử `--add-exports` và `--add-opens` trên môi trường test để xác định đúng nguyên nhân.
- [ ] Ưu tiên module descriptor/API công khai, giới hạn quyền deep reflection cho module cần thiết.
- [ ] Không dùng internal lookup hacks, `--illegal-access` hoặc `ALL-UNNAMED` quá rộng như giải pháp mặc định.
- [ ] Viết positive/negative tests cho package exported/opened/concealed trên **module path**.
- [ ] Không dựa vào kết quả từ classpath hoặc IDE để suy đoán mọi kết quả khi triển khai JPMS.

## 18. Tài liệu chuẩn còn áp dụng

1. [Oracle Java SE 25 — MethodHandles](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, `publicLookup`, `privateLookupIn`, điều kiện caller modes/readability/opens.
2. [Oracle Java SE 25 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access modes, `findStatic`, `in` và giới hạn cross-module.
3. [Oracle Java SE 25 — Module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen` và ý nghĩa opened package khi xác định exported runtime.
4. [Oracle Java SE 17 — Module System overview](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html): mô hình module và descriptor, xuất/mở package.
5. [Oracle Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): API tương thích Java 17 dùng trong ví dụ.
6. [OpenJDK — JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): Java 17 tăng strong encapsulation của JDK internals, không nên dựa vào lối truy cập nội bộ cũ.
