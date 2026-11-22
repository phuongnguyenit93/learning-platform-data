# Package, module, protection domain và class loader khi định nghĩa hidden class (Java 15+)

## 1. Học gì ở bài này?

Từ Java 15, `MethodHandles.Lookup.defineHiddenClass(...)` cho phép định nghĩa một **hidden class** từ mảng byte `.class` hợp lệ, mà không tạo ra một lớp mang binary name có thể được tìm lại bằng `Class.forName` hoặc `ClassLoader.loadClass`. Khác biệt này hữu ích cho framework, bộ sinh bytecode và runtime ngôn ngữ, nhưng **không** có nghĩa lớp mới được tự do lựa chọn package, module, quyền truy cập hay class loader.

Một hidden class được định nghĩa trong **ngữ cảnh của lookup class**. JVM coi nó có cùng:

1. **Runtime package** với lookup class.
2. **Module** với lookup class.
3. **Protection domain** với lookup class.
4. **Defining class loader** với lookup class (dù không được class loader đăng ký và tìm theo tên như một lớp thông thường).

Bài học giải thích bốn mối quan hệ trên, cách chúng ảnh hưởng đến **package-private access**, quyền theo Java Platform Module System (JPMS) và **nest-based private access**, cùng ví dụ chạy được có kiểm tra từng thuộc tính bằng Java SE.

Kiến thức này **vẫn áp dụng trong Java hiện đại**. Hidden classes là tính năng chính thức trong Java 15 (JEP 371), không phải preview và không dùng cơ chế nội bộ lỗi thời như `Unsafe.defineAnonymousClass`. Với dự án mới, sử dụng JDK còn được hỗ trợ; tùy chọn `--release 15` ở ví dụ chỉ nhằm bảo đảm tính tương thích cú pháp/API với Java 15.

## 2. Trước hết: hidden class được tạo ở đâu?

API cốt lõi:

```java
MethodHandles.Lookup original = MethodHandles.lookup();
MethodHandles.Lookup hiddenLookup = original.defineHiddenClass(
        classBytes, false, MethodHandles.Lookup.ClassOption.NESTMATE);
Class<?> hiddenClass = hiddenLookup.lookupClass();
```

Đây là **đoạn minh họa**, cần đặt trong một phương thức và có `classBytes` hợp lệ. `original` là một `Lookup` có quyền của class gọi `MethodHandles.lookup()`. Phương thức nhận:

- `classBytes`: **toàn bộ byte của một JVM `ClassFile`**, không phải văn bản Java hay chuỗi hex. Thông thường tạo bằng `javac` rồi đọc bằng `InputStream.readAllBytes()` hoặc `Files.readAllBytes()`.
- `initialize`: `true` yêu cầu JVM khởi tạo hidden class ngay trong lời gọi; `false` chưa khởi tạo chỉ vì đang định nghĩa lớp. Việc kích hoạt khởi tạo về sau vẫn theo quy tắc JVM.
- `ClassOption...`: tùy chọn `NESTMATE` để tham gia nest của lookup class và `STRONG` để ràng buộc vòng đời với defining loader như lớp thường. Có thể không truyền tùy chọn nào.

Giá trị trả về là **Lookup mới trên chính hidden class**, không phải trực tiếp một `Class<?>`. Từ đó mới lấy `hiddenLookup.lookupClass()` hoặc tạo method handle để gọi phương thức.

### Hidden class có tên không?

`Class.getName()` của hidden class có dạng gần giống `demo.HiddenContextDemo$Template/0x...`. Dấu `/` và phần suffix do JVM tạo là đặc trưng của **tên không phải binary name**; không nên so sánh toàn bộ suffix hay lưu làm định danh ổn định. `Class.isHidden()` mới là cách kiểm tra trực tiếp trạng thái hidden.

Vì không có binary name thông thường, bạn không thể viết source `new demo.HiddenContextDemo$Template/0x...()`, không thể nạp lại hidden class bằng `Class.forName(hiddenClass.getName())`, và lớp khác không thể tham chiếu nó qua symbolic reference thông thường trong constant pool. Nhưng có thể giữ `Class<?>`, `Lookup`, `MethodHandle` hoặc instance để tiếp tục dùng.

## 3. Package: tên giống nhau **chưa đủ** để có quyền truy cập

### 3.1. Package trong source và runtime package

Trong source Java, dòng `package demo;` biểu thị tên package. **Runtime package** trong JVM phụ thuộc **cả package name và defining class loader**. Hai class có cùng chuỗi tên package `demo` nhưng do **hai defining loaders khác nhau** định nghĩa thì không đương nhiên thuộc cùng runtime package, nên không được dùng quyền package-private của nhau chỉ vì cùng tên văn bản.

Với `defineHiddenClass`, class file phải khai báo **internal class name** thuộc **cùng package** với lookup class. JVM sau đó đánh dấu hidden class có **cùng runtime package** với lookup class. Đây là điều kiện thiết yếu vì bytecode được tạo ra có thể truy cập các thành viên package-private thuộc package ấy.

Ví dụ:

| Lookup class | Internal name của bytes | Kết quả |
| --- | --- | --- |
| `demo.Host` | `demo/Generated` | Cùng package, có thể thỏa điều kiện package |
| `demo.Host` | `demo/Host$Template` | Cùng package, hợp lệ về tên package |
| `demo.Host` | `other/Generated` | Khác package, bị từ chối (`IllegalArgumentException`) |
| `a.b.Host` | `a/b/Generated` | Cùng package `a.b` |
| `a.b.Host` | `a/Generated` | Khác package, không hợp lệ |

**Cùng package không đủ để bảo đảm lời gọi thành công:** bytes còn phải đúng định dạng `ClassFile`, version được JVM hỗ trợ, lookup phải đủ quyền, và các class/supertype/dependency phải liên kết được.

### 3.2. Package-private khác private của nest

- **Package-private** (không có `public`/`protected`/`private`) được kiểm soát bởi **runtime package**. Hidden class cùng runtime package có thể dùng quyền package-private mà các quy tắc JVM cho phép.
- **Private** được bảo vệ bởi quy tắc **nest-based access control**. Chỉ cùng runtime package **không** cho phép truy cập tùy ý `private` của class khác.
- Để hidden class là **nestmate** của lookup class, dùng `ClassOption.NESTMATE`. Nếu không truyền, hidden class mặc định là **nest riêng của chính nó**, kể cả khi bytes xuất phát từ một nested class do `javac` biên dịch.

Do đó, câu “hidden class cùng package với host” **không thể thay thế** yêu cầu `NESTMATE` khi generated bytecode cần gọi trực tiếp private method của một nest khác.

### 3.3. Không bỏ qua kiểm tra quyền qua `Lookup`

`MethodHandles.lookup()` tạo một lookup có **full privilege access** đối với class đang gọi nó. `defineHiddenClass` yêu cầu lookup có full privilege access (bao gồm quyền `PRIVATE` và `MODULE`).

`MethodHandles.publicLookup()` chỉ có khả năng giới hạn cho thành viên public của các class phù hợp; nó **không đủ quyền** để `defineHiddenClass` và có thể dẫn đến `IllegalAccessException`. Tương tự, `lookup.in(targetClass)` có thể **giảm quyền** khi dịch sang class/package/nest/module khác; không thể tự nâng lại các quyền đã mất.

Hãy sử dụng lookup do **mã đáng tin cậy trong module/package phù hợp** cung cấp. Không phát tán một lookup có toàn quyền cho mã không tin cậy: nó là **capability** có thể cho phép truy cập các thành viên không public của phạm vi tương ứng.

## 4. Module: hidden class thuộc module của lookup class

JPMS (Java Platform Module System) quản lý khả năng đọc module, `exports`, `opens` và quyền truy cập ở ranh giới module. Với `defineHiddenClass`, JVM coi hidden class thuộc **chính module** của lookup class, thay vì lấy module từ tên file hay tự tạo một module mới.

| Tình huống của lookup class | Module của hidden class |
| --- | --- |
| Host chạy trên classpath, thuộc **unnamed module** của loader | Cùng unnamed module với host |
| Host trong một named module, ví dụ `hidden.demo` | Cùng named module `hidden.demo` |
| Bytecode có tên class cùng package nhưng lookup từ module khác | Không dùng tên package để “chọn” module khác; phải có lookup có đủ quyền ở module đích |

**Một class loader có thể định nghĩa class thuộc nhiều module khác nhau.** Cùng class loader **không đồng nghĩa cùng module**; trong `defineHiddenClass` cả hai cùng nhau phù hợp vì JVM sử dụng ngữ cảnh lookup class.

### 4.1. `exports` và `opens` không giống nhau

- `exports demo.api;` trong `module-info.java` cho phép các module đọc module này truy cập **public types và public members** trong package được export, theo quy tắc JPMS.
- `opens demo.internal;` (hoặc `opens ... to target.module;`) chủ yếu phục vụ **deep reflection** từ module khác trong phạm vi được mở.
- Không có khai báo nào tự trao `full privilege access` cho code bên ngoài. `opens` không cho phép bạn dùng một `publicLookup()` để tự định nghĩa hidden class trong package của module kia.

`MethodHandles.privateLookupIn` có thể tạo lookup với quyền private vào target class **khi thỏa điều kiện module và quyền**. Tuy nhiên, **đổi lookup qua ranh giới module làm mất `MODULE` mode**, và vì `defineHiddenClass` đòi **full privilege access**, không thể giả định một lookup chuyển từ module khác bằng `privateLookupIn` sẽ gọi `defineHiddenClass` được. Giải pháp đúng khi framework cần định nghĩa hidden class trong module đích là **hợp tác với một điểm vào đáng tin cậy trong chính module ấy** để cung cấp hoặc thực hiện thao tác thích hợp, thay vì cố vượt JPMS.

Đối với ứng dụng chỉ chạy trên classpath, mã nguồn vẫn có thể dùng `MethodHandles.lookup()` trong host và kiểm tra `getModule()` bằng API chuẩn. Việc chưa dùng `module-info.java` không biến hidden class thành một phần của module `java.base`.

## 5. Protection domain: cùng ngữ cảnh nguồn gốc, **không phải sandbox**

`java.security.ProtectionDomain` mô tả miền bảo vệ gắn với class, bao gồm thông tin như code source và các metadata/chính sách quyền lịch sử của Java. Khi JVM định nghĩa hidden class qua `Lookup.defineHiddenClass`, nó đánh dấu class đó có **cùng protection domain** với lookup class.

Có thể quan sát:

```java
boolean sameDomain = hiddenClass.getProtectionDomain()
        == hostClass.getProtectionDomain();
```

Đây là **đoạn minh họa**; cần có `hiddenClass` và `hostClass`. Với hidden class được tạo từ đúng lookup class, phép so sánh identity minh họa tương quan domain do API quy định.

Điều **không nên** suy luận:

- Hidden class không tự có **sandbox riêng** để chạy bytecode tùy ý.
- “Cùng protection domain” **không** có nghĩa bytes mới an toàn, không có side effects hoặc không thể đọc file, mở kết nối, thực thi logic nguy hiểm.
- Không nên xây cơ chế an toàn mới dựa trên việc bật Security Manager cũ; cách dùng Security Manager này đã bị vô hiệu hóa trong các JDK hiện đại. ProtectionDomain vẫn là khái niệm/metadata của Java và là một phần ngữ nghĩa của API, nhưng không phải tường bảo mật cho untrusted code.
- Không nên chuyển bytecode từ nguồn không tin cậy cho `defineHiddenClass` chỉ vì bạn dự đoán protection domain giống host. **Định nghĩa bytecode là cho phép JVM chạy mã** trong ngữ cảnh runtime.

Nếu cần xử lý plugin hoặc bytecode chưa tin cậy, áp dụng mô hình nguồn gốc và cách ly thực tế (chẳng hạn tiến trình riêng, kiểm soát tài nguyên, xác minh artifact); không coi hidden class như một cơ chế cách ly.

## 6. Class loader: “defining loader” không đồng nghĩa có thể tìm theo tên

### 6.1. JVM gán defining loader của lookup class

Khi gọi `defineHiddenClass`, JVM **không** yêu cầu `ClassLoader.defineClass` để tạo class có tên. Thay vào đó, JVM trực tiếp tạo hidden class và **đánh dấu defining loader** là defining loader của lookup class. Vì vậy:

```java
boolean sameLoader = hiddenClass.getClassLoader()
        == hostClass.getClassLoader();
```

Kết quả là `true` nếu `hostClass` chính là lookup class dùng để định nghĩa hidden class.

Sự tương đồng này **không** biến hidden class thành một lớp có tên công khai trong bảng tìm kiếm của loader:

- `Class.forName(hiddenClass.getName())` không tìm lại hidden class.
- `ClassLoader.loadClass(hiddenClass.getName())` không tìm lại hidden class.
- JVM **không ghi initiating loader** cho hidden class theo cơ chế nạp có tên thông thường.
- Hidden class có thể dùng class loader đã đánh dấu để phân giải **các lớp phụ thuộc có tên bình thường** khi cần liên kết.

Một hệ thống tạo class động phải **giữ `Class<?>`/`Lookup`/`MethodHandle`** nếu còn cần sử dụng hidden class. Không dựa vào suffix `/0x...`, không lưu tên hidden vào database rồi chờ loader khôi phục nó.

### 6.2. Vòng đời: mặc định yếu và tùy chọn `STRONG`

| Định nghĩa | Quan hệ với defining loader | Tác động |
| --- | --- | --- |
| Không truyền `STRONG` (mặc định) | Hidden class có thể được dỡ tải **độc lập** ngay cả khi loader vẫn reachable | Phù hợp nhiều lớp triển khai tạm thời do runtime sinh ra |
| Truyền `Lookup.ClassOption.STRONG` | Hidden class có quan hệ mạnh với defining loader như class thường | Hidden class có thể tồn tại đến khi loader có thể được GC dỡ |
| Giữ `Class<?>`, `MethodHandle`, instance hoặc reference liên quan | Vẫn có các tham chiếu cần thiết đến hidden class | Không được giả định lớp sẽ dỡ tải trong khi còn dùng |

**Không có lời hứa về thời điểm GC/unload.** Không thể “ép” một hidden class dỡ ngay chỉ bằng cách đặt biến local bằng `null`. Trong framework sinh hàng nghìn lớp, hãy kiểm soát cache, reference và memory pressure; chỉ dùng `STRONG` khi vòng đời thực sự cần gắn với defining loader.

### 6.3. Runtime package và class loader là một cặp

Nếu `demo.Host` được loader A định nghĩa, còn `demo.Other` được loader B định nghĩa, hai class **cùng tên package** chưa chắc có quyền package-private của nhau. Với hidden class do `demo.Host` tạo qua lookup của nó, JVM cho class mới cùng runtime package/defining loader với `demo.Host`. Không thể dùng `Lookup` của Host A để cấp quyền cho class loader B hoặc module khác một cách tùy ý.

## 7. Nest: quan hệ riêng biệt với package, module và loader

Một **nest** chứa một nest host và các nestmates, cho phép các class trong cùng nest truy cập **private members** của nhau theo quy tắc JVM. Với class Java lồng thông thường, compiler có thể phát sinh metadata `NestHost`/`NestMembers`.

Khi class file được biến thành hidden class:

- Nếu **không** truyền `ClassOption.NESTMATE`, hidden class có **nest của riêng nó**.
- Nếu truyền `NESTMATE`, JVM thêm hidden class vào **nest của lookup class**. Nest host của hidden class có thể là outer nest host của lookup class nếu lookup class là nested class.
- `NESTMATE` không cho phép vượt module/package, không tự bỏ qua bytecode verification, không sửa lỗi class file khác package và không giúp truy cập `private` của *mọi* class tùy ý.
- `NESTMATE` và `STRONG` là các ý nghĩa **độc lập**: một cái liên quan **private access**, một cái liên quan **lifecycle/class loader reachability**.

**Điểm quan trọng:** nếu class file mẫu được biên dịch từ một nested class, đừng cho rằng các NestHost attributes trong bytes sẽ tự động biến hidden class thành nestmate. Hãy truyền `NESTMATE` một cách rõ ràng khi mã sinh ra cần truy cập private của host.

## 8. Ví dụ đầy đủ: kiểm chứng package, module, protection domain, loader và nest

Ví dụ sau sử dụng **chỉ Java SE**. `Template` là class lồng tĩnh để `javac` tạo ra một file `.class` hợp lệ và có bytecode gọi tới phương thức `private` của outer class. Chương trình đọc **bytes** của file ấy, định nghĩa **hai hidden classes độc lập** từ cùng bytes (một lớp không có NESTMATE, một lớp có NESTMATE), so sánh các thuộc tính và gọi phương thức private thông qua hidden nestmate.

### 8.1. Cấu trúc dự án

```text
project/
└── src/
    └── demo/
        └── HiddenContextDemo.java
```

Tạo file **`src/demo/HiddenContextDemo.java`**:

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenContextDemo {
    private static String secret() {
        return "secret-ok";
    }

    static class Template {
        static String readSecret() {
            return HiddenContextDemo.secret();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream input = HiddenContextDemo.class
                .getResourceAsStream("HiddenContextDemo$Template.class")) {
            if (input == null) {
                throw new IOException("Missing compiled Template class");
            }
            bytes = input.readAllBytes();
        }

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandles.Lookup withoutNest =
                lookup.defineHiddenClass(bytes, false);
        Class<?> plain = withoutNest.lookupClass();

        MethodHandles.Lookup withNest = lookup.defineHiddenClass(
                bytes,
                false,
                MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> hidden = withNest.lookupClass();

        System.out.println("fullPrivilege=" + lookup.hasFullPrivilegeAccess());
        System.out.println("plainHidden=" + plain.isHidden());
        System.out.println("plainSelfNest=" + (plain.getNestHost() == plain));
        System.out.println("hidden=" + hidden.isHidden());
        System.out.println("samePackage="
                + hidden.getPackageName().equals(HiddenContextDemo.class.getPackageName()));
        System.out.println("sameModule="
                + (hidden.getModule() == HiddenContextDemo.class.getModule()));
        System.out.println("sameLoader="
                + (hidden.getClassLoader() == HiddenContextDemo.class.getClassLoader()));
        System.out.println("sameProtectionDomain="
                + (hidden.getProtectionDomain() == HiddenContextDemo.class.getProtectionDomain()));
        System.out.println("nestHostIsDemo="
                + (hidden.getNestHost() == HiddenContextDemo.class.getNestHost()));
        System.out.println("hiddenNameHasSlash=" + hidden.getName().contains("/"));

        MethodHandle call = withNest.findStatic(
                hidden, "readSecret", MethodType.methodType(String.class));
        System.out.println("privateAccess=" + (String) call.invokeExact());
    }
}
```

`Template` được compiler tạo thành file `HiddenContextDemo$Template.class` cùng package `demo`. Ở đây chữ `$` trong tên file resource là một phần tên class lồng được biên dịch, không phải “nơi viết” hidden class trong source. `getResourceAsStream(...)` chỉ đọc dữ liệu từ resource, **không** gọi `Class.forName` với hidden name.

Khi biên dịch, JVM class file chứa mã `readSecret()` có quyền nestmate của outer class theo cấu trúc source bình thường. Nhưng khi bytes đó được định nghĩa thành hidden class, tùy chọn `NESTMATE` mới quyết định liệu hidden class có thực sự cùng nest với `HiddenContextDemo` hay không.

### 8.2. Lệnh biên dịch và chạy trên classpath

Đứng tại thư mục `project`, sử dụng JDK hiện đại có `javac` hỗ trợ target Java 15 (ví dụ JDK 21):

```bash
javac --release 15 -encoding UTF-8 -d out src/demo/HiddenContextDemo.java
java -cp out demo.HiddenContextDemo
```

**Stdout chính xác, không phụ thuộc suffix JVM của tên hidden class:**

```text
fullPrivilege=true
plainHidden=true
plainSelfNest=true
hidden=true
samePackage=true
sameModule=true
sameLoader=true
sameProtectionDomain=true
nestHostIsDemo=true
hiddenNameHasSlash=true
privateAccess=secret-ok
```

**Giải thích kết quả:**

1. `fullPrivilege=true`: lookup trực tiếp trong method của class đang thực thi có quyền đủ để định nghĩa hidden class.
2. `plainHidden=true`, `plainSelfNest=true`: hidden class tạo **không dùng `NESTMATE`** mang nest riêng, dù bytes đến từ nested class.
3. `hidden=true`: lớp tạo qua API thực sự là hidden class.
4. `samePackage=true`: runtime package trùng với lookup class; kiểm tra tên package cùng với sự bảo đảm cùng defining loader.
5. `sameModule=true`: cùng đối tượng `Module`. Chạy trên classpath thì cả hai thuộc unnamed module tương ứng.
6. `sameLoader=true`: cùng class loader được đánh dấu defining loader, **không** có nghĩa có thể gọi `loadClass` để tìm hidden class.
7. `sameProtectionDomain=true`: cùng đối tượng `ProtectionDomain` theo quy tắc API.
8. `nestHostIsDemo=true`: khi truyền `NESTMATE`, hidden class có cùng nest host với `HiddenContextDemo`.
9. `hiddenNameHasSlash=true`: tên của hidden class không có dạng binary name thông thường. Đừng ghi rõ suffix vì mỗi lần định nghĩa có thể khác.
10. `privateAccess=secret-ok`: bytecode `readSecret()` có thể gọi `private static String secret()` của host vì hidden class đã được cấp nestmate membership.

**Vì sao không gọi `readSecret()` trên `plain`?** Lớp `plain` không có `NESTMATE` và không được cấp private access tới host như lớp `hidden`; nếu cố chạy cùng bytecode gọi private của outer class, nó có thể lỗi access khi JVM liên kết/giải quyết lời gọi. Ví dụ cố tình **không** dùng hành vi lỗi như bước thành công để output ổn định.

**Vì sao có hai hidden class dù bytes chỉ có một file?** Mỗi lời gọi `defineHiddenClass` tạo một `Class<?>` riêng với identity và suffix mới. Không nên giả định cùng bytes là cùng một class runtime. `initialize=false` ở ví dụ không có vấn đề vì `Template` không có static initializer cần quan sát; việc gọi method của hidden class có thể kích hoạt initialization khi cần.

### 8.3. Tùy chọn: chạy trong named module

Nếu muốn kiểm tra cả trường hợp **named module** trên Java 15+, chuyển cùng nội dung `HiddenContextDemo.java` sang cấu trúc:

```text
project/
└── module-src/
    └── hidden.demo/
        ├── module-info.java
        └── demo/
            └── HiddenContextDemo.java
```

Nội dung **`module-src/hidden.demo/module-info.java`**:

```java
module hidden.demo {
}
```

Sau đó đứng ở `project` và chạy:

```bash
javac --release 15 -encoding UTF-8 -d mods --module-source-path module-src -m hidden.demo
java --module-path mods -m hidden.demo/demo.HiddenContextDemo
```

**Stdout vẫn chính xác như mục 8.2.** Khác biệt là `HiddenContextDemo.class.getModule().isNamed()` sẽ là `true`; cả host và hidden class thuộc cùng named module `hidden.demo`. Không cần `exports demo;` chỉ để host và hidden class cùng module thực thi; `exports` là cơ chế để các module khác truy cập public API.

## 9. Khi nào dùng `NESTMATE`, khi nào dùng `STRONG`?

| Nhu cầu | Lựa chọn | Lý do |
| --- | --- | --- |
| Generated bytecode chỉ cần quyền public/package-private tương ứng | Không bắt buộc `NESTMATE` | Cùng runtime package đã được JVM quy định |
| Generated bytecode cần trực tiếp dùng `private` trong nest của host | `NESTMATE` | Tham gia access-control nest |
| Generated class tồn tại tạm thời, nên có thể dỡ độc lập với loader | Không truyền `STRONG` | Tránh ghim lifecycle vào loader một cách không cần thiết |
| Generated class có lifecycle bắt buộc cùng loader | Cân nhắc `STRONG` | Mạnh như quan hệ của class thường với defining loader |
| Muốn chọn package/module/loader khác qua class bytes | **Không dùng `defineHiddenClass` để vượt ranh giới** | API sử dụng context của lookup class |
| Nhận dữ liệu class file không tin cậy từ mạng | Không gọi trực tiếp trong tiến trình ứng dụng | Hidden class không phải sandbox |

Tùy chọn `NESTMATE` không nói gì về dỡ lớp; `STRONG` không tạo private access. Chúng độc lập và có thể được dùng cùng nhau nếu thiết kế runtime thật sự cần cả hai.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalAccessException` từ `defineHiddenClass` | Lookup thiếu **full privilege access**, ví dụ `publicLookup()` hoặc lookup đã mất mode | Tạo/nhận lookup có quyền từ trusted host trong module tương ứng; kiểm tra `hasFullPrivilegeAccess()` |
| `IllegalArgumentException` do package | Internal name trong class bytes không cùng package với lookup class | Kiểm tra `package` và internal name trong class file; dùng bytes của class cùng package |
| `ClassFormatError` | Bytes không phải `ClassFile` hợp lệ hoặc sai cấu trúc | Đọc binary `.class`, không dùng bytes của source `.java` |
| `UnsupportedClassVersionError` | Class file version cao hơn JVM đang dùng | Kiểm tra `javap -verbose` và `java -version`; tạo bytecode tương thích |
| `VerifyError` | Class bytecode vi phạm verifier | Kiểm tra generator, bytecode instructions, stack maps và types |
| `LinkageError` khác | Không thể liên kết supertype, dependency hoặc symbolic references | Kiểm tra classpath/module path, phiên bản phụ thuộc và accessibility |
| `IllegalAccessError` khi gọi private host | Hidden class không thuộc nest cần thiết hoặc bytecode cố truy cập sai phạm vi | Thêm `NESTMATE` khi hợp lệ, kiểm tra nest host và target method |
| `NoSuchMethodException` từ `findStatic` | Tên method hoặc `MethodType` không khớp | Kiểm tra class bytes đã biên dịch và chữ ký method |
| `WrongMethodTypeException` tại `invokeExact` | Kiểu tham số/kết quả Java tại call site không khớp chính xác method handle | Dùng đúng cast và `MethodType`; chỉ dùng `invoke` khi hiểu chuyển đổi |
| `ExceptionInInitializerError` | Static initializer của lớp mới ném lỗi | Kiểm tra code trong `static { ... }` và thời điểm `initialize` |
| `ClassNotFoundException` khi thử nạp hidden name | Hidden class không có binary name tra cứu được | Giữ `Class<?>` / `Lookup` / `MethodHandle` từ lúc định nghĩa |
| Bị giữ bộ nhớ lâu khi tạo nhiều class | Cache còn giữ method handle/class, hoặc truyền `STRONG` không cần thiết | Thiết kế lifecycle, quản lý reference và đo class metadata/metaspace |
| Kết quả khác giữa classpath và module path | Lớp thuộc unnamed vs named module, hoặc `exports`/`opens` khác | Kiểm tra `Class.getModule()`, lookup modes và chính sách module |

**Về class file version:** Java 15 dùng **major version 59**. Khi biên dịch ví dụ với `javac --release 15`, có thể xác minh bằng:

```bash
javap -verbose -classpath out demo.HiddenContextDemo
```

Trong thông tin bytecode, xem dòng `major version: 59`. Không nhầm class file version với phiên bản JVM đang dùng để **chạy** chương trình.

**Về an toàn:** không coi “cùng protection domain” hoặc “cùng loader” là phép bảo đảm code an toàn. JVM có thể thực thi static initializer và các method của class file, nên chỉ nhận bytes từ nguồn có tin cậy/kiểm soát và có mô hình cách ly thật nếu cần chạy mã bên ngoài.

## 11. Checklist thực hành

1. **Class bytes:** đã đọc đúng file `.class` ở dạng binary, không phải `.java` hay byte array của chuỗi?
2. **Package:** internal name của class file cùng package với lookup class? Cùng tên package nhưng loader khác có làm sai assumption về runtime package ở các class khác không?
3. **Lookup:** `hasFullPrivilegeAccess()` có `true`? Lookup có xuất phát từ trusted class/module đúng vị trí hay đã bị giảm modes?
4. **Module:** hidden class sẽ thuộc module của lookup class; có đang nhầm `exports`/`opens` với quyền định nghĩa code mới?
5. **Protection domain:** xác nhận đúng metadata domain được kế thừa, nhưng không coi đây là sandbox cho bytecode không tin cậy.
6. **Class loader:** hidden class dùng defining loader của lookup class nhưng không tra lại bằng tên; đã giữ reference khi còn cần chưa?
7. **Nest:** code có cần gọi private host không? Nếu cần, chọn `NESTMATE` và kiểm tra `getNestHost()`.
8. **Lifespan:** đã cân nhắc `STRONG` và cache/reference để tránh giữ lớp quá lâu?
9. **Initialization:** `initialize=true/false` có phù hợp side effects của static initializer?
10. **Validation:** đã chạy trên JVM hỗ trợ class file version và đối chiếu package/module/loader/domain/nest bằng API, không dựa vào suffix `getName()`?

## 12. Tài liệu chính thức

- **Java SE 15 — `MethodHandles.Lookup.defineHiddenClass`, đặc tả cùng runtime package, module, protection domain và loader:** https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **Java SE 15 — `MethodHandles`, `lookup()`, `publicLookup()` và `privateLookupIn()`:** https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.html
- **Java SE 15 — `Lookup.ClassOption.NESTMATE` và `STRONG`:** https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- **OpenJDK JEP 371 — Hidden Classes:** https://openjdk.org/jeps/371
- **JVM Specification — định nghĩa class, runtime package, class loader và `ClassFile`:** https://docs.oracle.com/javase/specs/jvms/se15/html/index.html
- **Java SE hiện đại — `MethodHandles.Lookup` (API còn được hỗ trợ):** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **Java SE hiện đại — `Class` (`getPackageName`, `getModule`, `getClassLoader`, `getProtectionDomain`, `isHidden` và `getNestHost`):** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html

Bài học chỉ sử dụng cơ chế Java SE **chính thức và còn áp dụng trong JDK hiện đại**. Phân biệt rõ quyền package/module, quan hệ nest và lifecycle class loader sẽ giúp tránh việc tin rằng hidden class có thể tự vượt các ranh giới truy cập của JVM.
