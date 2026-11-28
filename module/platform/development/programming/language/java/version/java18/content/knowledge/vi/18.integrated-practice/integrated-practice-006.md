# Tạo cặp fixture named module để so sánh quyền reflection và privateLookupIn()

> **Phạm vi:** Chương **Thực hành tổng hợp** của module `JAVA_VERSION_JAVA18`. Java 18 mang đến JEP 416 (tái triển khai core reflection bằng method handles), nhưng các hợp đồng công khai của `java.lang.reflect`, `java.lang.invoke.MethodHandles` và hệ thống module Java (JPMS) vẫn giữ vai trò quyết định quyền truy cập trên JDK hiện đại. Bài này xây dựng **hai named modules có thể chạy được** để so sánh public reflection, deep reflection và `MethodHandles.privateLookupIn()`. Chỉ sử dụng API hiện hành; không dựa vào lớp nội bộ JDK hoặc cách phá bỏ encapsulation trên diện rộng.

## 1. Mục tiêu của bài thực hành

Sau bài này, người học có thể:

1. Tạo **module chứa đối tượng đích** `lab.vault` và **module thực hiện kiểm chứng** `lab.probe`.
2. Phân biệt `requires`, `exports` và `opens` trong kiểm tra quyền JPMS.
3. Dùng reflection để tìm public/private method và phân biệt **lấy metadata** với **quyền gọi method**.
4. Quan sát `IllegalAccessException`, `InaccessibleObjectException` và giá trị của `trySetAccessible()` khi package chưa được mở.
5. Kiểm chứng `MethodHandles.privateLookupIn()` chỉ thành công khi lookup caller có quyền phù hợp, module caller đọc module đích và package đích được mở cho caller.
6. Chạy **hai cấu hình** trên JDK 18+: fixture A chỉ `exports`, fixture B có thêm `opens` được giới hạn cho module `lab.probe`.
7. Nhận ra quyền truy cập được kiểm tra tại **giai đoạn khác nhau** đối với reflection và method handles.

Các đầu ra cần xác minh gồm: tên module, quan hệ đọc module, trạng thái `exports/opens`, việc gọi public method, kết quả `trySetAccessible` và khả năng tạo private method handle.

## 2. Mô hình hai named modules

Ta dùng đúng **hai named modules**:

| Module | Chức năng | Cấu hình cần có |
|---|---|---|
| `lab.vault` | Chứa class `lab.vault.api.Vault` với public method và private method. | `exports lab.vault.api`; fixture B bổ sung `opens lab.vault.api to lab.probe`. |
| `lab.probe` | Chứa `lab.probe.Main` để kiểm tra reflection và method handles. | `requires lab.vault` để đọc module đích và sử dụng public API. |

Sơ đồ phụ thuộc:

~~~text
                      requires lab.vault
       ┌─────────────────────────────────────┐
       │                                     ▼
┌──────────────┐                     ┌──────────────┐
│  lab.probe   │                     │  lab.vault   │
│ Main.java    │                     │ Vault.java   │
│              │                     │              │
│ Reflection   │── public API ──────▶│ label()      │
│ MethodHandles│                     │              │
│              │── deep reflection ─▶│ reveal()     │
└──────────────┘    cần opens       │ private      │
                                    └──────────────┘
~~~

Đây là hai module **có tên thật trong `module-info.java`**, không phải hai package trong cùng unnamed module. Sự khác biệt quan trọng vì JPMS áp dụng quy tắc đóng gói theo module.

### Vì sao cần cả exports và opens?

- `exports lab.vault.api` làm **public type và public members** của package khả dụng cho module đọc `lab.vault`.
- `opens lab.vault.api to lab.probe` cho phép **deep reflection** từ đúng module `lab.probe` vào package đó, theo điều kiện của API.
- `exports` **không** tự cho phép gọi private method qua reflection.
- `opens` **không biến** private method thành public method hay tự động bỏ access check của mọi thao tác.
- `requires lab.vault` làm module `lab.probe` **đọc** module đích; đây cũng là một điều kiện để `privateLookupIn` hoạt động giữa hai named modules.

Fixture này cố ý giữ `exports` ở cả hai cấu hình để phần **public access luôn thành công**. Khi so sánh, ta chỉ thay đổi quyền **mở package cho deep reflection**, không thay đổi tên class, code Java hay phương thức được kiểm thử.

## 3. Chuẩn bị cấu trúc project

Tạo các tệp dưới một thư mục thực hành riêng, ví dụ `named-module-access-lab`:

~~~text
named-module-access-lab/
├── src/
│   ├── lab.vault/
│   │   ├── module-info.java
│   │   └── lab/
│   │       └── vault/
│   │           └── api/
│   │               └── Vault.java
│   └── lab.probe/
│       ├── module-info.java
│       └── lab/
│           └── probe/
│               └── Main.java
└── mods/                       # thư mục build, tạo khi biên dịch
    ├── closed/
    └── opened/
~~~

Tách `src/lab.vault` và `src/lab.probe` theo tên module giúp `javac --module-source-path src` nhận ra module chứa mỗi source file.

**Yêu cầu:** Dùng JDK **18 trở lên** với lệnh `java`, `javac` có hỗ trợ JPMS. Không cần Gradle, Maven, thư viện bên thứ ba hay cờ preview. Không chạy dưới classpath để kiểm chứng quyền module: khi chuyển sang unnamed module, các quy tắc deep reflection sẽ khác và làm bài test sai mục tiêu.

## 4. Fixture A: module đích chỉ exports, không opens

Tệp `src/lab.vault/module-info.java`:

~~~java
module lab.vault {
    exports lab.vault.api;
}
~~~

Module này cho phép ứng dụng bên ngoài import class public của package `lab.vault.api`. Nó **không** mở package cho module `lab.probe` thực hiện deep reflection.

Tệp `src/lab.vault/lab/vault/api/Vault.java`:

~~~java
package lab.vault.api;

public final class Vault {

    private final String secret = "fixture-only";

    public String label() {
        return "public:ok";
    }

    private String reveal() {
        return "private:" + secret;
    }
}
~~~

Class được cố ý thiết kế nhỏ:

- `Vault` là public, nằm trong package đã `exports`.
- `label()` là public instance method: caller khác module có thể dùng trực tiếp, qua reflection hoặc public method handle.
- `reveal()` là private instance method: caller khác module **không** được phép gọi nếu không có quyền deep reflection.
- `secret` là private field, giúp mở rộng bài test với `Field`.
- Chuỗi `fixture-only` là dữ liệu thử nghiệm, **không** phải secret thật. Không lưu token hoặc mật khẩu thật trong fixture.

Tệp `src/lab.probe/module-info.java`:

~~~java
module lab.probe {
    requires lab.vault;
}
~~~

Không cần khai báo `opens` ở module `lab.probe`. Đây là **caller**; package phải được mở nằm trong **module đích `lab.vault`**. Nhầm lẫn vị trí khai báo `opens` là lỗi rất phổ biến.

## 5. Chương trình kiểm chứng chung cho cả hai cấu hình

Tệp `src/lab.probe/lab/probe/Main.java`:

~~~java
package lab.probe;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import lab.vault.api.Vault;

public final class Main {

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Throwable {
        Vault target = new Vault();

        Module targetModule = Vault.class.getModule();
        Module callerModule = Main.class.getModule();

        boolean readable = callerModule.canRead(targetModule);
        boolean exported = targetModule.isExported(
                "lab.vault.api", callerModule);
        boolean opened = targetModule.isOpen(
                "lab.vault.api", callerModule);

        System.out.println("TARGET_MODULE=" + targetModule.getName());
        System.out.println("CALLER_MODULE=" + callerModule.getName());
        System.out.println("READS_TARGET=" + readable);
        System.out.println("EXPORTED_TO_CALLER=" + exported);
        System.out.println("OPEN_TO_CALLER=" + opened);

        check(readable, "lab.probe must read lab.vault");
        check(exported, "The target public package must be exported");

        // 1. Public reflection luôn thành công ở hai fixture.
        Method publicMethod = Vault.class.getMethod("label");
        String publicResult = (String) publicMethod.invoke(target);
        System.out.println("PUBLIC_REFLECTION=" + publicResult);
        check("public:ok".equals(publicResult),
                "Unexpected public reflection result");

        // 2. Public MethodHandle cũng thành công.
        MethodHandle publicHandle = MethodHandles.lookup().findVirtual(
                Vault.class, "label",
                MethodType.methodType(String.class));

        String publicHandleResult =
                (String) publicHandle.invokeExact(target);
        System.out.println("PUBLIC_HANDLE=" + publicHandleResult);
        check("public:ok".equals(publicHandleResult),
                "Unexpected public handle result");

        // 3. Tìm metadata private KHÔNG đồng nghĩa được phép invoke.
        Method privateMethod = Vault.class.getDeclaredMethod("reveal");
        System.out.println("PRIVATE_METADATA=" + privateMethod.getName());

        try {
            privateMethod.invoke(target);
            throw new AssertionError(
                    "Private invoke should fail before suppressing access");
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "PRIVATE_WITHOUT_OVERRIDE=IllegalAccessException");
        }

        // 4. trySetAccessible: false khi chưa opens; true khi đã opens.
        Method soft = Vault.class.getDeclaredMethod("reveal");
        boolean accessible = soft.trySetAccessible();
        System.out.println("TRY_SET_ACCESSIBLE=" + accessible);
        check(accessible == opened,
                "Reflection access does not match opens fixture");

        if (accessible) {
            String privateValue = (String) soft.invoke(target);
            System.out.println("PRIVATE_REFLECTION=" + privateValue);
            check("private:fixture-only".equals(privateValue),
                    "Unexpected private reflection result");
        } else {
            System.out.println("PRIVATE_REFLECTION=DENIED");
        }

        // 5. setAccessible(true) ném InaccessibleObjectException nếu bị chặn.
        Method strict = Vault.class.getDeclaredMethod("reveal");
        boolean inaccessible = false;
        try {
            strict.setAccessible(true);
            System.out.println("SET_ACCESSIBLE=SUCCESS");
        } catch (InaccessibleObjectException expected) {
            inaccessible = true;
            System.out.println(
                    "SET_ACCESSIBLE=InaccessibleObjectException");
        }
        check(inaccessible != opened,
                "Unexpected setAccessible result");

        // 6. Field private tuân quy tắc opens tương tự.
        Field secretField = Vault.class.getDeclaredField("secret");
        boolean fieldAccessible = secretField.trySetAccessible();
        System.out.println("PRIVATE_FIELD_ACCESS=" + fieldAccessible);
        check(fieldAccessible == opened,
                "Field access does not match opens fixture");

        if (fieldAccessible) {
            System.out.println(
                    "PRIVATE_FIELD_VALUE=" + secretField.get(target));
        }

        // 7. publicLookup không có MODULE+PRIVATE, dù package đã opens.
        try {
            MethodHandles.privateLookupIn(
                    Vault.class, MethodHandles.publicLookup());
            throw new AssertionError(
                    "publicLookup must not gain private privileges");
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "PUBLIC_LOOKUP_FOR_PRIVATE=IllegalAccessException");
        }

        // 8. Lookup của class Main có quyền ban đầu phù hợp.
        try {
            MethodHandles.Lookup privateLookup =
                    MethodHandles.privateLookupIn(
                            Vault.class, MethodHandles.lookup());

            check(opened,
                    "privateLookupIn should not succeed without opens");

            System.out.println("PRIVATE_LOOKUP=SUCCESS");

            // Sang module khác, lookup kết quả mất quyền MODULE.
            boolean hasModuleMode =
                    (privateLookup.lookupModes()
                            & MethodHandles.Lookup.MODULE) != 0;
            System.out.println("RESULT_LOOKUP_HAS_MODULE=" + hasModuleMode);
            check(!hasModuleMode,
                    "Cross-module private lookup should lose MODULE mode");

            MethodHandle privateHandle = privateLookup.findVirtual(
                    Vault.class, "reveal",
                    MethodType.methodType(String.class));

            String result = (String) privateHandle.invokeExact(target);
            System.out.println("PRIVATE_HANDLE=" + result);
            check("private:fixture-only".equals(result),
                    "Unexpected private handle result");

        } catch (IllegalAccessException expected) {
            check(!opened,
                    "privateLookupIn failed even though package is open");
            System.out.println("PRIVATE_LOOKUP=IllegalAccessException");
        }
    }
}
~~~

**Giải thích thiết kế kiểm thử:**

- `Module.canRead`, `Module.isExported` và `Module.isOpen` cho biết chính xác quan hệ JPMS của **hai module đang chạy**, không phải suy đoán từ tên folder.
- `getDeclaredMethod("reveal")` tìm metadata private ngay cả khi package chưa mở; lần gọi `invoke` ban đầu vẫn không đủ quyền.
- `trySetAccessible()` và `setAccessible(true)` được gọi trên **hai đối tượng `Method` mới**, tránh việc một lần bật accessible trước đó làm sai ca kiểm thử sau.
- `privateLookupIn` nhận `MethodHandles.lookup()` tạo trong `Main`, có quyền `MODULE` và `PRIVATE` ban đầu; ngược lại `publicLookup()` không có các quyền này.
- `privateLookupIn` có thể ném `IllegalAccessException` khi package chưa được `opens`, dù public method của class vẫn truy cập được.
- Khi private lookup thành công qua hai named modules, kết quả có quyền private trên target nhưng **không có `MODULE` mode**, theo hợp đồng cross-module.
- `invokeExact(target)` đúng vì private handle được tạo bằng `findVirtual` với kiểu thực tế `(Vault)String` và call site trả `String`.
- Các lệnh `check` giúp tránh báo thành công giả nếu cách đóng gói module hoặc cấu hình JVM khác với fixture dự kiến.

## 6. Biên dịch và chạy fixture A: exports-only

Từ thư mục `named-module-access-lab`, trên **Windows PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/closed | Out-Null

javac --module-source-path src --module lab.vault,lab.probe -d mods/closed

java --module-path mods/closed --module lab.probe/lab.probe.Main
~~~

Trên Linux/macOS, thay dòng tạo thư mục bằng:

~~~shell
mkdir -p mods/closed
~~~

Hai dòng `javac` và `java` còn lại giống nhau trên cả ba hệ điều hành vì `--module-path` chỉ trỏ đến **một** thư mục.

Kết quả dự kiến:

~~~text
TARGET_MODULE=lab.vault
CALLER_MODULE=lab.probe
READS_TARGET=true
EXPORTED_TO_CALLER=true
OPEN_TO_CALLER=false
PUBLIC_REFLECTION=public:ok
PUBLIC_HANDLE=public:ok
PRIVATE_METADATA=reveal
PRIVATE_WITHOUT_OVERRIDE=IllegalAccessException
TRY_SET_ACCESSIBLE=false
PRIVATE_REFLECTION=DENIED
SET_ACCESSIBLE=InaccessibleObjectException
PRIVATE_FIELD_ACCESS=false
PUBLIC_LOOKUP_FOR_PRIVATE=IllegalAccessException
PRIVATE_LOOKUP=IllegalAccessException
~~~

### Cách đọc kết quả

- `READS_TARGET=true`: `requires lab.vault` có hiệu lực.
- `EXPORTED_TO_CALLER=true`: module caller được dùng public API từ package.
- `OPEN_TO_CALLER=false`: package chưa cho phép deep reflection đối với module caller.
- Public reflection và public method handle **thành công**.
- `getDeclaredMethod` vẫn tìm được private method.
- Private invocation không qua access override **không thành công**.
- `trySetAccessible` trả false; `setAccessible(true)` ném `InaccessibleObjectException`.
- `privateLookupIn` ném `IllegalAccessException`. Đây là **lỗi quyền**, không phải `NoSuchMethodException`, vì `reveal()` có tồn tại.

Trong fixture này, **exports không đủ để mở private members**.

## 7. Fixture B: mở đúng package cho đúng module

Ta muốn so sánh với **cùng hai module và cùng code `Vault`/`Main`**, chỉ thay một yếu tố: package `lab.vault.api` được mở cho `lab.probe`.

Có hai cách thực hiện, phục vụ mục đích khác nhau.

### Cách B1 — Thử nhanh bằng cờ runtime --add-opens

Giữ nguyên các file và output `mods/closed` của fixture A, chạy một **JVM mới**:

~~~powershell
java --module-path mods/closed --add-opens lab.vault/lab.vault.api=lab.probe --module lab.probe/lab.probe.Main
~~~

Cờ này có nghĩa là **mở package `lab.vault.api` của module `lab.vault` cho module `lab.probe` trong tiến trình này**. Đây là cách chẩn đoán hoặc kiểm thử quyền được hỗ trợ trên JDK hiện đại; không đồng nghĩa khuyến nghị mở package tùy tiện trong sản phẩm.

### Cách B2 — Khai báo opens rõ ràng trong module-info.java

Trong project thử nghiệm, thay nội dung `src/lab.vault/module-info.java` bằng:

~~~java
module lab.vault {
    exports lab.vault.api;
    opens lab.vault.api to lab.probe;
}
~~~

Giữ nguyên `src/lab.probe/module-info.java`:

~~~java
module lab.probe {
    requires lab.vault;
}
~~~

Biên dịch vào thư mục `mods/opened` **riêng** để không đè bản closed đã tạo:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/opened | Out-Null

javac --module-source-path src --module lab.vault,lab.probe -d mods/opened

java --module-path mods/opened --module lab.probe/lab.probe.Main
~~~

Lệnh build không còn dùng `--add-opens`; quyền mở package đã được khai báo bằng descriptor của module đích.

Cả B1 và B2 đều có kết quả dự kiến:

~~~text
TARGET_MODULE=lab.vault
CALLER_MODULE=lab.probe
READS_TARGET=true
EXPORTED_TO_CALLER=true
OPEN_TO_CALLER=true
PUBLIC_REFLECTION=public:ok
PUBLIC_HANDLE=public:ok
PRIVATE_METADATA=reveal
PRIVATE_WITHOUT_OVERRIDE=IllegalAccessException
TRY_SET_ACCESSIBLE=true
PRIVATE_REFLECTION=private:fixture-only
SET_ACCESSIBLE=SUCCESS
PRIVATE_FIELD_ACCESS=true
PRIVATE_FIELD_VALUE=fixture-only
PUBLIC_LOOKUP_FOR_PRIVATE=IllegalAccessException
PRIVATE_LOOKUP=SUCCESS
RESULT_LOOKUP_HAS_MODULE=false
PRIVATE_HANDLE=private:fixture-only
~~~

**Quan sát quan trọng:**

1. `PRIVATE_WITHOUT_OVERRIDE` vẫn là `IllegalAccessException`: `opens` không biến private method thành public; reflection chỉ gọi được sau khi **bật** suppression bằng `trySetAccessible` hoặc `setAccessible(true)`.
2. `PUBLIC_LOOKUP_FOR_PRIVATE` vẫn bị từ chối: mở package không nâng quyền của `MethodHandles.publicLookup()`.
3. `PRIVATE_LOOKUP=SUCCESS` chứng minh caller có full-privilege lookup ban đầu, đọc module đích và module đích đã mở package cho caller.
4. `RESULT_LOOKUP_HAS_MODULE=false`: lookup “dịch chuyển” từ module `lab.probe` sang `lab.vault` qua `privateLookupIn` bị bỏ `MODULE` mode; nó không được phép vô hạn tiếp tục lấy private lookup ở module thứ ba.

**Khuyến nghị thiết kế:** Khi kiểm soát được source của module, dùng `opens package.name to trusted.consumer` thay vì dựa lâu dài vào cờ runtime. Tránh `open module` không giới hạn nếu ứng dụng chỉ cần mở một package cho một consumer cụ thể.

## 8. Ma trận so sánh hai fixture

| Thao tác | A: chỉ exports | B: exports + opens cho lab.probe |
|---|---|---|
| `requires lab.vault` / `canRead` | Đọc được module đích. | Đọc được module đích. |
| Public `Vault` và `label()` | Truy cập được. | Truy cập được. |
| `Class.getDeclaredMethod("reveal")` | Tìm được metadata. | Tìm được metadata. |
| `Method.invoke` private, chưa bật accessible | `IllegalAccessException`. | `IllegalAccessException`. |
| `Method.trySetAccessible()` | `false`. | `true`. |
| `Method.setAccessible(true)` | `InaccessibleObjectException`. | Thành công. |
| `Field.trySetAccessible()` private field | `false`. | `true`. |
| `privateLookupIn(Vault.class, publicLookup())` | `IllegalAccessException`. | `IllegalAccessException`. |
| `privateLookupIn(Vault.class, lookup())` từ `Main` | `IllegalAccessException`. | Thành công. |
| `privateLookup.findVirtual(... "reveal")` | Không tạo được private lookup. | Trả private method handle. |
| `privateHandle.invokeExact(target)` | Không có handle để gọi. | Trả `private:fixture-only`. |

Ma trận này cho phép học viên **đặt một giả thuyết rồi kiểm chứng bằng cả nguồn reflection và nguồn method handles**, thay vì chỉ nhìn một exception đơn lẻ.

## 9. Phân biệt lỗi theo giai đoạn và API

Một điểm quan trọng của bài thực hành là **cùng một nguyên nhân quyền** nhưng hai API có thể báo lỗi bằng những cách khác nhau.

| Giai đoạn | API | Biểu hiện khi thiếu quyền |
|---|---|---|
| Lấy metadata | `Class.getDeclaredMethod("reveal")` | Vẫn có thể lấy `Method`; chưa thực thi private method. |
| Gọi reflection chưa suppress | `Method.invoke(target)` | `IllegalAccessException`. |
| Thử bật accessible không ném lỗi truy cập thông thường | `Method.trySetAccessible()` | Trả `false`. |
| Yêu cầu bật accessible trực tiếp | `Method.setAccessible(true)` | `InaccessibleObjectException` khi không thể mở quyền. |
| Tạo private lookup cross-module | `MethodHandles.privateLookupIn(...)` | `IllegalAccessException` nếu điều kiện access không thỏa. |
| Tạo method handle cho private member | `privateLookup.findVirtual(...)` | Chỉ thực hiện nếu đã có lookup đủ quyền. |
| Gọi handle đã tạo | `MethodHandle.invokeExact(...)` | Kiểm tra `MethodType` tại call site; không tự làm lại access check thông thường. |

### Phân biệt với các lỗi không phải quyền module

- `NoSuchMethodException`: tên hoặc chữ ký member không tồn tại theo yêu cầu lookup. Trong fixture này, method `reveal()` **có tồn tại**, nên nguyên nhân chính không phải thiếu method.
- `WrongMethodTypeException`: method handle đã có nhưng descriptor của `invokeExact` không khớp, ví dụ ép kiểu trả về thành `Object` trong khi handle thực tế trả `String`.
- `InvocationTargetException`: reflection gọi được method nhưng **thân method** ném throwable; không đồng nghĩa lỗi `opens`.
- `ClassCastException` hoặc `NullPointerException` từ adapter: vấn đề dữ liệu/ép kiểu khi invocation, không phải thất bại tạo private lookup.

Khi debug hãy đặt câu hỏi: “Ta đã tạo được `Method` hay `MethodHandle` chưa? Quyền bị từ chối ở bước nào?” Tránh sửa tên method khi thực ra cần xem module descriptor, và tránh thêm `opens` khi vấn đề là một `MethodType` sai.

## 10. Các lỗi thiết kế fixture thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Không có `module-info.java` | Chạy trên classpath, không kiểm chứng đúng JPMS named modules. | Tạo đủ hai module descriptors. |
| Đặt `opens` ở `lab.probe` thay vì `lab.vault` | Không mở package chứa private member cần đọc. | Khai báo ở module **sở hữu package**. |
| Chỉ dùng `exports` rồi kỳ vọng đọc private member | `trySetAccessible` false, `privateLookupIn` thất bại. | Thêm `opens ... to lab.probe` nếu thực sự cần. |
| Bỏ `requires lab.vault` ở caller | Caller không đọc được target module và không biên dịch direct import. | Khai báo `requires lab.vault`. |
| Bỏ `exports lab.vault.api` nhưng vẫn import `Vault` | Lỗi compile-time hoặc access của public API. | Giữ exports để cô lập thử nghiệm deep reflection. |
| Dùng `publicLookup()` cho `privateLookupIn` | Thiếu `MODULE` và `PRIVATE` modes. | Dùng `MethodHandles.lookup()` được tạo ở caller đủ quyền. |
| Cố dùng `lookup.in(Vault.class)` để tự nâng quyền | `Lookup.in` không phải API tăng quyền private. | Dùng `privateLookupIn` khi đã có opens/reads và quyền caller. |
| Gọi `Method.invoke` trước khi bật accessible và mong thành công sau opens | `opens` không bỏ private modifier. | Bật accessible trên reflected Method khi policy cho phép. |
| Chạy JVM với cờ `--add-opens` ngoài ý muốn cho fixture A | Fixture A trở thành “opened”, kết quả không còn là baseline. | Chạy A bằng lệnh riêng, không có cờ thêm. |
| Biên dịch lại target mà không tách output | Dễ lẫn class/module descriptor cũ. | Dùng `mods/closed` và `mods/opened`. |
| Đổi return type trong `invokeExact` | `WrongMethodTypeException`, không liên quan JPMS. | So khớp cả receiver, parameters và return type. |
| Mở toàn bộ module/package không cần thiết | Tăng quyền deep reflection và giảm encapsulation. | Giới hạn `opens` đúng package và module đáng tin. |

Một ranh giới bảo mật cần nhớ: `privateLookupIn` tạo một lookup có thể truy cập private members trong phạm vi đã được cho phép; **đừng trao lookup hoặc private method handle đó cho code không đáng tin**. Một khi capability đã được tạo, `asType`/`bindTo` không làm nó “mất” quyền truy cập member gốc theo nghĩa an toàn bảo mật.

## 11. Nâng cao: tách “mở package” khỏi “mở member”

Trong fixture B, có hai lớp quyết định:

1. **Chính sách module:** `lab.vault` mở package cho `lab.probe` (qua descriptor hoặc runtime option có giới hạn).
2. **Thao tác API cụ thể:** reflection phải bật `accessible` trên `Method` hoặc `Field`; method handles cần `privateLookupIn` để tạo lookup đủ quyền.

Điều này giải thích tại sao sau khi `opens`, dòng:

~~~java
Method m = Vault.class.getDeclaredMethod("reveal");
m.invoke(new Vault()); // Vẫn có thể ném IllegalAccessException.
~~~

không tự thành công, nhưng:

~~~java
Method m = Vault.class.getDeclaredMethod("reveal");
if (m.trySetAccessible()) {
    String value = (String) m.invoke(new Vault());
}
~~~

có thể thành công.

Đối với MethodHandle:

~~~java
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                Vault.class, MethodHandles.lookup());

MethodHandle h = privateLookup.findVirtual(
        Vault.class, "reveal",
        MethodType.methodType(String.class));

String value = (String) h.invokeExact(new Vault());
~~~

`privateLookupIn` là bước **lấy quyền truy cập member trong target class**, còn `findVirtual` tạo handle tương ứng. Không thể thay toàn bộ chuỗi đó bằng `MethodHandles.publicLookup().findVirtual(...)` cho private method.

Một lưu ý riêng cho named modules: kết quả của `privateLookupIn` khi vượt qua ranh giới module không còn `MODULE` mode. Đây là giới hạn có chủ đích để tránh tiếp tục “chuyển” full privilege qua các module ngoài phạm vi cho phép.

## 12. Checklist thực hành và báo cáo kết quả

### Checklist xây dựng

- [ ] Có `src/lab.vault/module-info.java` và `src/lab.probe/module-info.java`.
- [ ] Module `lab.probe` có `requires lab.vault`.
- [ ] Module `lab.vault` có `exports lab.vault.api` trong cả hai fixture.
- [ ] `Vault` public, `label()` public, `reveal()` và `secret` private.
- [ ] `Main` thực hiện `Module.canRead`, `isExported` và `isOpen`.
- [ ] Fixture A chạy mà **không** có `opens` và **không** có `--add-opens`.
- [ ] Fixture B chạy với **qualified opens** hoặc cờ test `--add-opens` được giới hạn.
- [ ] Không dùng classpath/unnamed module thay cho named modules.
- [ ] Hai cấu hình được chạy trong các JVM mới.

### Checklist kết quả

- [ ] A và B đều gọi được public `label()` bằng reflection và MethodHandle.
- [ ] A và B đều lấy được metadata private `reveal()`.
- [ ] A: `trySetAccessible=false`; `setAccessible` báo `InaccessibleObjectException`.
- [ ] A: `privateLookupIn` báo `IllegalAccessException`.
- [ ] B: `trySetAccessible=true` và `Method.invoke` private thành công **sau** khi bật suppression.
- [ ] B: `privateLookupIn` thành công với `MethodHandles.lookup()` từ `Main`.
- [ ] B: private method handle trả đúng chuỗi `private:fixture-only`.
- [ ] B: lookup result mất `MODULE` mode khi đi qua hai named modules.
- [ ] Cả A và B: `publicLookup()` không tự được cấp private access.
- [ ] Có giải thích vì sao `exports` và `opens` là hai quyền khác nhau.

### Mẫu bảng báo cáo

| Kiểm chứng | Fixture A | Fixture B | Điều rút ra |
|---|---|---|---|
| `Module.isOpen` | false | true | Chỉ B mở deep reflection. |
| Public reflection | OK | OK | `exports` đủ cho public API. |
| Private reflection chưa override | IAE | IAE | Private vẫn là private. |
| `trySetAccessible` | false | true | Bật suppression cần opens. |
| `setAccessible(true)` | InaccessibleObjectException | OK | Phân biệt exception với boolean. |
| `privateLookupIn` | IllegalAccessException | OK | Cần opens và lookup caller đủ quyền. |
| Private method handle | Không tạo được | OK | Tạo capability sau khi access được duyệt. |

**Kết luận:** Hai named modules cho một fixture kiểm chứng có tính xác định. `requires` tạo quan hệ readability; `exports` cho public API; `opens` cho deep reflection theo module consumer. `Method.trySetAccessible()`/`setAccessible(true)` và `MethodHandles.privateLookupIn()` kiểm tra quyền ở các bước khác nhau, nên kết quả báo lỗi khác nhau nhưng đều phản ánh chính sách JPMS. Dùng `opens ... to ...` có phạm vi nhỏ và chạy hai cấu hình tách biệt để chứng minh đúng hợp đồng trên JDK hiện đại.

## 13. Câu hỏi tự đánh giá

1. Vì sao `lab.probe` phải khai báo `requires lab.vault`?
2. Tại sao `exports lab.vault.api` đủ cho public `label()` nhưng không đủ cho private `reveal()`?
3. `getDeclaredMethod("reveal")` có thất bại chỉ vì package chưa mở không?
4. Vì sao `Method.invoke` private vẫn ném `IllegalAccessException` trong fixture B nếu chưa bật accessible?
5. `trySetAccessible()` và `setAccessible(true)` khác nhau về cách báo thất bại thế nào?
6. `privateLookupIn` có thể thành công nếu dùng `publicLookup()` làm caller hay không? Vì sao?
7. Ba điều kiện cần khi `privateLookupIn` truy cập class trong **module khác** là gì?
8. Vì sao lookup trả về khi dịch chuyển qua ranh giới module mất `MODULE` mode?
9. Sự khác nhau giữa mở package bằng `module-info.java` và dùng `--add-opens` cho một lần chạy là gì?
10. Nếu private method handle đã được tạo, `invokeExact` có thể ném `WrongMethodTypeException` không? Đó có phải lỗi quyền module không?
11. Tại sao thử nghiệm này phải dùng hai **named** modules thay vì classpath?
12. Bạn sẽ thiết kế `opens` như thế nào để cho một framework cần deep reflection truy cập package mà không mở cho mọi module?

## Tài liệu tham khảo chính thức

- [Java SE 26: `AccessibleObject` – `trySetAccessible()`, `setAccessible(true)`, module opens](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [Java SE 26: `MethodHandles.privateLookupIn` – MODULE, PRIVATE, readability và opens](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Java SE 26: `MethodHandles.Lookup` – quyền và cross-module lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Java SE 26: `java.lang.Module` – `canRead`, `isExported` và `isOpen`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html).
- [Java SE 26: `Method` – invoke và access check](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Method.html).
- [OpenJDK JEP 416 – Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [Java SE 26: `java` command – `--module-path`, `--module`, `--add-opens`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- [Java SE 26: `javac` command – biên dịch nhiều named modules bằng `--module-source-path` và `--module`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html).
