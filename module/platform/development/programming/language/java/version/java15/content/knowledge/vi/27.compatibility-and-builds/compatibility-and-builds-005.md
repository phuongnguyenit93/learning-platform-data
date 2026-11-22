# Ranh giới module và `MethodHandles.Lookup` khi đóng gói (Java 15+)

> **Phạm vi:** Cách Java kiểm soát truy cập giữa các module khi mã được biên dịch, đóng JAR và chạy trên module path; cách `MethodHandles.Lookup` làm việc với quyền truy cập đó; và ý nghĩa của `Lookup.defineHiddenClass`, API được bổ sung chính thức ở Java 15. Các nguyên tắc và API dưới đây vẫn áp dụng trên JDK hiện đại. Ví dụ chạy bằng JDK 17 trở lên.

## 1. Cần phân biệt những ranh giới nào?

Một ứng dụng có thể chạy tốt khi các thư viện cùng nằm trên classpath nhưng gặp lỗi truy cập sau khi chuyển thành các **named module** trên `--module-path`. Lý do là Java áp dụng đồng thời quy tắc ngôn ngữ (`public`, `private`, package-private), quy tắc module (đọc module nào, export/open package nào) và quyền của đối tượng `Lookup`.

| Thành phần | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| `module-info.java` | Module phụ thuộc module nào; package nào là API công khai hoặc được mở cho phản chiếu | `requires`, `exports`, `opens` |
| `requires other.module` | Module hiện tại **đọc** module khác, cho phép giải quyết các API được xuất phù hợp | `requires demo.vault` |
| `exports p` | Mã ở module khác có thể biên dịch và truy cập kiểu/thành viên `public` thuộc package `p`, nếu đọc được module | `exports demo.vault.api` |
| `opens p to m` | Module `m` được phép phản chiếu sâu vào package `p` ở thời điểm chạy, theo quy tắc API | `opens demo.vault.api to demo.client` |
| `MethodHandles.Lookup` | Chứa ngữ cảnh class gọi và các quyền có thể dùng để lấy `MethodHandle` hoặc định nghĩa class | `MethodHandles.lookup()` |
| `ClassLoader` và tên package | Quyết định định danh lớp/runtime package; class cùng tên package nhưng ở loader/module khác không tự có quyền của nhau | `defineHiddenClass` phải dùng đúng ngữ cảnh |

**`exports` không đồng nghĩa với `opens`.** Export cho phép dùng API `public` theo quy tắc truy cập thông thường; không tự cấp quyền lấy private field/method. Open chủ yếu phục vụ deep reflection ở runtime; không làm cho package trở thành API có thể import và biên dịch từ module khác. Với mã đi qua biên giới module, có thể cần cả `requires`, `exports` và `opens` tùy thao tác.

Sơ đồ kiểm tra khi từ module A muốn truy cập thành viên của lớp ở module B:

1. A có đọc được B không (`requires` hoặc cạnh đọc thích hợp)?
2. Lớp có thể truy cập công khai qua package được `exports` cho A không, hay thao tác cần `opens` cho A?
3. Modifier của lớp/thành viên và quyền thực tế của `Lookup` có đủ không?
4. Khi tạo class động, vị trí package, loader và module có phù hợp với `Lookup` đang dùng không?

## 2. Quyền của `MethodHandles.Lookup`

`MethodHandles.lookup()` lấy lookup theo **class thực sự gọi phương thức này**, không theo nơi một tham chiếu `Lookup` được truyền đến sau đó. Nó kiểm tra quyền khi tạo `MethodHandle`, chẳng hạn bằng `findVirtual`, `findStatic`, `findGetter` hoặc `findConstructor`; việc gọi handle đã tạo không lặp lại toàn bộ bước kiểm tra truy cập theo cách tra cứu ban đầu.

Các lựa chọn thường gặp:

- `MethodHandles.lookup()`: lookup gắn với class đang gọi, thường có quyền đầy đủ đối với ngữ cảnh class đó. `hasFullPrivilegeAccess()` kiểm tra lookup có cả quyền `PRIVATE` và `MODULE`.
- `MethodHandles.publicLookup()`: dành cho API `public` có thể truy cập công khai; không cấp quyền private hay package. Đặc biệt, nó không thay thế một lookup theo module khi cần qualified export.
- `lookup.in(Target.class)`: đổi class đích để tra cứu nhưng có thể **mất** các mode như `PRIVATE`, `PACKAGE`, `MODULE`. Đây không phải cách nâng quyền.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)`: xin lookup có quyền truy cập private ở `Target`. Cần `callerLookup` ban đầu có `PRIVATE` và `MODULE`; khi target nằm ở **module khác**, module của caller phải đọc module target và package của target phải `opens` cho caller. Lookup trả về khi vượt module có quyền private trong target nhưng **không còn quyền MODULE**, nên `hasFullPrivilegeAccess()` là `false`.
- `Lookup.defineHiddenClass(bytes, initialize, options)`: cần **full privilege access** và bytecode khai báo lớp thuộc cùng package với lookup class. Không thể dùng một lookup đã mất `MODULE` để định nghĩa hidden class, kể cả khi `privateLookupIn` đã cho phép tra cứu private member.

**Nguyên tắc bảo mật:** Không truyền `Lookup` có đặc quyền đầy đủ như một tiện ích mở cho mã không đáng tin cậy. Nó là một năng lực truy cập; giữ việc tạo class động trong module tin cậy, cung cấp API hẹp để sử dụng kết quả.

## 3. Ví dụ hoàn chỉnh: hai module, truy cập private và hidden class

Ví dụ dùng một module thư viện `demo.vault` và một module gọi `demo.client`. Thư viện xuất API công khai, chỉ mở package cho module client, đồng thời tự định nghĩa hidden class từ bytecode được đóng trong JAR.

Cấu trúc thư mục:

```text
src/
├── demo.vault/
│   ├── module-info.java
│   └── demo/vault/api/
│       ├── Vault.java
│       ├── HiddenTemplate.java
│       └── HiddenFactory.java
└── demo.client/
    ├── module-info.java
    └── demo/client/
        └── Main.java
```

**`src/demo.vault/module-info.java`**

```java
module demo.vault {
    exports demo.vault.api;
    opens demo.vault.api to demo.client;
}
```

`exports` giúp client import `Vault` và `HiddenFactory`. `opens ... to demo.client` là quyền chủ đích, cho phép riêng `demo.client` sử dụng `privateLookupIn` để tra cứu thành viên private. Không mở toàn bộ module.

**`src/demo.vault/demo/vault/api/Vault.java`**

```java
package demo.vault.api;

public final class Vault {
    private final String token = "internal-42";

    public String status() {
        return "ready";
    }
}
```

**`src/demo.vault/demo/vault/api/HiddenTemplate.java`**

```java
package demo.vault.api;

final class HiddenTemplate {
    static String message() {
        return "generated-ok";
    }
}
```

`HiddenTemplate` là file class mẫu được biên dịch và đóng trong JAR. Nó không phải hidden class ngay khi biên dịch; một **bản thể class mới** chỉ trở thành hidden khi `defineHiddenClass` nhận bytecode của file này.

**`src/demo.vault/demo/vault/api/HiddenFactory.java`**

```java
package demo.vault.api;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HiddenFactory {
    private HiddenFactory() {}

    public static String inspect() throws Throwable {
        byte[] bytes;
        try (InputStream in =
                     HiddenFactory.class.getResourceAsStream("HiddenTemplate.class")) {
            if (in == null) {
                throw new IOException("Missing HiddenTemplate.class in package");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, true);
        Class<?> hiddenType = hiddenLookup.lookupClass();

        MethodHandle message = hiddenLookup.findStatic(
                hiddenType, "message", MethodType.methodType(String.class));

        return hiddenType.isHidden() + ":" + (String) message.invoke();
    }
}
```

Tại đây, `MethodHandles.lookup()` được tạo **bên trong** `HiddenFactory`, cùng module và package với bytecode `HiddenTemplate`; do đó nó còn full privilege và được phép định nghĩa hidden class. `getResourceAsStream` đọc bytecode nằm trong chính JAR/module, không phụ thuộc thư mục source ở runtime. Lệnh `defineHiddenClass(bytes, true)` định nghĩa và yêu cầu khởi tạo lớp mới; `lookupClass()` trả về `Class<?>` của hidden class để tạo handle gọi `message`.

**`src/demo.client/module-info.java`**

```java
module demo.client {
    requires demo.vault;
}
```

**`src/demo.client/demo/client/Main.java`**

```java
package demo.client;

import demo.vault.api.HiddenFactory;
import demo.vault.api.Vault;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class Main {
    public static void main(String[] args) throws Throwable {
        Vault vault = new Vault();
        MethodHandles.Lookup caller = MethodHandles.lookup();

        MethodHandle status = caller.findVirtual(
                Vault.class, "status", MethodType.methodType(String.class));
        System.out.println("status=" + (String) status.invoke(vault));

        MethodHandles.Lookup deep =
                MethodHandles.privateLookupIn(Vault.class, caller);
        MethodHandle token = deep.findGetter(Vault.class, "token", String.class);
        System.out.println("token=" + (String) token.invoke(vault));
        System.out.println(
                "crossModuleFullPrivilege=" + deep.hasFullPrivilegeAccess());

        System.out.println("hidden=" + HiddenFactory.inspect());
    }
}
```

### Biên dịch, đóng modular JAR và chạy

Từ thư mục chứa `src/`, dùng JDK 17+; những API chính trong ví dụ có từ Java 15:

```bash
javac --module-source-path src -d mods -m demo.vault,demo.client

mkdir dist
jar --create --file dist/demo.vault.jar -C mods/demo.vault .
jar --create --file dist/demo.client.jar -C mods/demo.client .

java --module-path dist --module demo.client/demo.client.Main
```

Kết quả chuẩn:

```text
status=ready
token=internal-42
crossModuleFullPrivilege=false
hidden=true:generated-ok
```

Giải thích:

1. `caller.findVirtual` thành công vì client `requires demo.vault`, package `demo.vault.api` được `exports`, và `status()` là `public`.
2. `privateLookupIn` thành công vì ngoài quyền full privilege của `caller` còn có `opens demo.vault.api to demo.client`. Nó đọc được `token` private nhưng lookup kết quả không giữ mode `MODULE` khi đi qua module, nên in `false`.
3. `HiddenFactory.inspect()` chạy trong **module sở hữu bytecode**, tạo hidden class cùng package rồi truy cập bằng handle trên lookup vừa được trả về. Khách hàng chỉ gọi API công khai, không cần quyền định nghĩa class.
4. Cả hai JAR phải chứa `module-info.class` ở gốc; `demo.vault.jar` còn phải chứa `demo/vault/api/HiddenTemplate.class`. Nếu thiếu class mẫu, `getResourceAsStream` trả `null` và ví dụ báo lỗi có ý nghĩa.

Có thể kiểm tra mô tả module ngay từ sản phẩm đóng gói:

```bash
jar --describe-module --file dist/demo.vault.jar
jar --describe-module --file dist/demo.client.jar
```

## 4. Hidden class của Java 15: vì sao liên quan đến đóng gói?

Hidden classes được đưa vào Java 15 qua JEP 371 và là API chính thức, không cần bật preview. Chúng phục vụ framework/runtime tạo code lúc chạy, chẳng hạn triển khai lambda, proxy hoặc logic sinh động có vòng đời ngắn. Khác với class thông thường:

- `Lookup.defineHiddenClass` nhận bytecode `.class` và trả về một `Lookup` trỏ đến lớp mới. Bytecode phải có tên lớp nội bộ thuộc **cùng package** với lookup class; runtime package, class loader và module tương ứng do lookup quyết định.
- Hidden class có danh tính thực, có thể thao tác qua `Class<?>`, reflection hoặc `MethodHandle` đã có; nhưng nó **không có tên nhị phân thông thường** để tìm bằng `Class.forName` hoặc `ClassLoader.loadClass`. Không dùng tên của nó làm khóa cấu hình, tên plugin hay API công khai.
- Theo mặc định hidden class không bị class loader giữ mạnh như class thường, vì vậy có thể được thu hồi khi không còn tham chiếu phù hợp. Tùy chọn `Lookup.ClassOption.STRONG` tạo quan hệ mạnh hơn với class loader khi cần giữ vòng đời lâu hơn.
- Tùy chọn `Lookup.ClassOption.NESTMATE` dùng khi hidden class cần tham gia cùng nest với lookup class, ví dụ để truy cập private member của nest host; nó không phải tùy chọn bắt buộc cho trường hợp gọi phương thức package-private trong ví dụ.
- `initialize=true` yêu cầu khởi tạo hidden class khi định nghĩa; `false` cho phép khởi tạo theo nhu cầu sử dụng sau. Dù chọn cách nào, bytecode vẫn phải hợp lệ và có phiên bản class file mà JVM hiện tại hỗ trợ.

**Ranh giới quan trọng nhất:** `opens` cho một module khác giúp deep reflection qua `privateLookupIn`, nhưng lookup liên module đó **không đủ full privilege cho `defineHiddenClass`**. Nếu một thư viện tạo code động cần định nghĩa class trong package của module khác, hãy thiết kế factory tin cậy thực thi ở module đích hoặc một giao diện ủy quyền đặc quyền có kiểm soát; đừng mặc định mở package là đủ.

## 5. Khi nào build thành công nhưng chạy thất bại?

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa đúng thiết kế |
| --- | --- | --- |
| `package ... is not visible` khi `javac` | Thiếu `requires` hoặc package chưa được `exports` cho module gọi | Khai báo đúng dependency và export API cần dùng |
| `IllegalAccessException` từ `privateLookupIn` | Package của module đích chưa `opens` cho module caller, caller không đọc module đích, hoặc lookup đầu vào thiếu quyền | Dùng `opens p to m` có phạm vi nhỏ, kiểm tra module graph và lookup nguồn |
| `IllegalAccessException` từ `defineHiddenClass` | Lookup thiếu `PRIVATE`/`MODULE`, hay đã đi qua `privateLookupIn` liên module | Định nghĩa trong module sở hữu package bằng full privilege lookup |
| `IllegalArgumentException` về package khi định nghĩa hidden class | Tên package của bytecode khác package của lookup class | Sinh/đóng đúng binary name và đặt factory vào package tương ứng |
| `ClassFormatError` hoặc `UnsupportedClassVersionError` | Bytecode không hợp lệ hoặc phiên bản class file vượt JVM chạy | Dùng compiler/generator tạo bytecode hợp lệ phù hợp runtime |
| `Missing HiddenTemplate.class in package` | JAR/shading/minimizer đã bỏ resource `.class` mà factory đọc | Kiểm tra nội dung JAR và quy tắc đóng gói resource |
| `ClassNotFoundException` khi dùng tên hidden class | Hidden class không thể tải lại qua tìm kiếm theo tên thông thường | Giữ `Class<?>` hoặc method handle do factory trả về |
| Chạy trên classpath được, chạy trên module path lỗi | Named module kích hoạt quy tắc readability/export/open và resolution khác môi trường classpath | Kiểm tra `module-info.class`, đường dẫn chạy và module graph, không dựa vào truy cập private ngầm |

**Chú ý:** `InaccessibleObjectException` thường gặp với Core Reflection (`setAccessible`) khi bị chặn bởi module encapsulation; các thao tác `Lookup` ở ví dụ chủ yếu báo `IllegalAccessException`. Không nên gộp mọi lỗi thành “JAR hỏng”.

Để khoanh vùng lỗi quyền truy cập lúc chạy, JVM còn hỗ trợ `--show-module-resolution`; có thể thử lệnh chẩn đoán sau:

```bash
java --show-module-resolution --module-path dist --module demo.client/demo.client.Main
```

Nếu cần kiểm chứng tác động của `opens` trong một môi trường thử nghiệm, có thể bỏ chỉ thị `opens` khỏi descriptor và chạy với tùy chọn chẩn đoán `--add-opens demo.vault/demo.vault.api=demo.client`. Đây là cấu hình cấp quyền lúc khởi động, không nên dùng lâu dài để che một hợp đồng module thiết kế chưa đúng.

## 6. Checklist dành cho người phát hành thư viện/framework

1. **Xác định API cần export.** Chỉ export package dùng làm hợp đồng `public`; giữ package triển khai không export để tránh khóa chặt API vào chi tiết nội bộ.
2. **Phân biệt compile-time và runtime access.** Dùng `requires`/`exports` cho mã gọi bình thường; chỉ thêm `opens ... to ...` khi có nhu cầu reflection cụ thể. Tránh `open module` nếu không thật sự cần mở toàn bộ.
3. **Đặt nơi tạo lookup đúng chỗ.** `MethodHandles.lookup()` phản ánh class gọi; đưa factory vào đúng module/package nếu cần định nghĩa class. Đừng mặc định `lookup.in(...)` hoặc `privateLookupIn(...)` liên module sẽ cho quyền định nghĩa class.
4. **Đóng đủ bytecode.** Kiểm tra JAR chứa `module-info.class`, mọi class/resource mà factory đọc, không nhầm `src/` với classpath ở runtime. Kiểm tra sau bước shading/minimization.
5. **Biên dịch hướng đúng runtime.** Nếu phát hành cho một phiên bản JDK cụ thể, cấu hình `javac --release <version>` tương ứng; build chạy trên JDK mới không bảo đảm class file sẽ chạy trên JVM cũ.
6. **Thử ở chế độ phát hành.** Chạy JAR thực tế từ `--module-path` và qua lệnh `--module` giống môi trường triển khai, ngoài các bài test từ IDE; kiểm tra cả lối đi reflection và hidden-class factory.
7. **Hạn chế quyền mở package.** Quyền `opens` sâu có thể cho phép thao tác private và định nghĩa class thường trong package qua các API thích hợp. Chỉ cấp cho module thực sự tin cậy; ưu tiên factory/API công khai có hợp đồng rõ ràng.
8. **Không dựa vào tên hidden class.** Duy trì tham chiếu `Class<?>`/`MethodHandle` nếu cần; cân nhắc vòng đời và `STRONG` theo nhu cầu thực tế.

## 7. Tự kiểm tra hiểu bài

- **Chỉ `exports p` có đủ để đọc `private` field từ module khác?** Không. Cần điều kiện của `privateLookupIn`, gồm việc package target mở cho caller khi vượt module.
- **`privateLookupIn` sang module khác có dùng để gọi `defineHiddenClass` không?** Không, vì lookup kết quả thiếu `MODULE` và không có full privilege.
- **Hidden class có phải class mẫu `HiddenTemplate.class` đã được nạp bình thường không?** Không. `HiddenTemplate.class` là bytecode đầu vào; `defineHiddenClass` định nghĩa một class mới với định danh hidden riêng.
- **Đưa JAR lên `--module-path` có tự biến mọi package thành API công khai?** Không. Named module chỉ công bố các package được `exports`, còn `opens` kiểm soát truy cập phản chiếu sâu.
- **Mỗi module có cần mở package chứa factory của nó cho client khi factory tự tạo hidden class?** Không. Factory chạy cùng module và dùng lookup của chính nó; client chỉ cần truy cập API public được export.

## Tài liệu chính thức

- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): thiết kế và mục đích của hidden classes trong Java 15.
- [Java API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quyền lookup, `privateLookupIn`, `defineHiddenClass`, `NESTMATE` và `STRONG`.
- [Dev.java — Introduction to Modules](https://dev.java/learn/modules/intro/): `requires`, `exports`, `opens` và ranh giới truy cập.
- [javac Tool Reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--module-source-path`, `--module-path` và đóng gói module.
