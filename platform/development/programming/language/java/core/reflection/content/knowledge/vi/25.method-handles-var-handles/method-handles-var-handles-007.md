# `MethodHandles.privateLookupIn` và điều kiện mở truy cập theo module (Java 17+)

## 1. Vì sao cần `privateLookupIn`?

`MethodHandle` và `VarHandle` cung cấp cách truy cập phương thức, constructor và biến thông qua một **đối tượng năng lực truy cập** (`MethodHandles.Lookup`). Khi dùng `findVirtual`, `findStatic`, `findVarHandle`, v.v., Java kiểm tra quyền của `Lookup` ngay lúc tạo handle. Việc giữ được `Class<?>` hoặc biết tên thành viên private **không tự cấp quyền** để truy cập thành viên đó.

Phương thức:

~~~java
MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(Target.class, callerLookup);
~~~

tạo một `Lookup` có **ngữ cảnh tra cứu là `Target`** và có thể truy cập thành viên `private` của `Target`, nhưng **chỉ khi `callerLookup` đã đủ quyền và ranh giới module cho phép truy cập sâu** (*deep reflection*). API này xuất hiện từ Java 9, phù hợp với hệ thống module JPMS. Nó không mở package, không vô hiệu hóa module system và cũng chưa tạo `MethodHandle` hay `VarHandle`; muốn sử dụng một thành viên, phải tìm thành viên bằng `targetLookup` ở bước kế tiếp.

Mục tiêu của bài:

- Hiểu sự khác nhau giữa `MethodHandles.lookup()`, `publicLookup()`, `Lookup.in(...)` và `privateLookupIn(...)`.
- Nắm chính xác yêu cầu `PRIVATE`, `MODULE`, quan hệ `reads` và chỉ thị `opens`.
- Phân biệt `exports` với `opens` và biết dùng `--add-opens` để thử nghiệm/chẩn đoán.
- Gọi được method private và field private bằng MethodHandle/VarHandle, xử lý lỗi truy cập đúng chỗ.
- Nhận ra việc `Lookup` đi từ module này sang module khác làm mất mode `MODULE` và không thể tùy ý “chuyển tiếp” quyền private.

## 2. `Lookup` là quyền truy cập có thể truyền đi

`MethodHandles.lookup()` là **caller-sensitive**: lời gọi nằm trong lớp nào thì thông thường trả về `Lookup` với `lookupClass()` là lớp đó, có quyền đầy đủ của lớp gọi (trong một lời gọi thông thường, gồm các mode `PRIVATE` và `MODULE`).

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();
System.out.println(caller.lookupClass().getName());
~~~

`MethodHandles.publicLookup()` chỉ cho phép nhóm truy cập public theo quy tắc của nó, **không có `PRIVATE`/`MODULE` để gọi `privateLookupIn`**. `caller.in(Other.class)` thay lớp làm ngữ cảnh tìm kiếm nhưng quyền có thể bị giảm, đặc biệt khi đổi class/package/module; nó không phải một cách tự nâng quyền private.

Các method quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `MethodHandles.lookup()` | Tạo lookup gắn với **lớp thực sự đang gọi** |
| `MethodHandles.publicLookup()` | Lookup public, không đủ quyền để yêu cầu private lookup |
| `lookup.lookupClass()` | Lớp mà lookup hiện đại diện |
| `lookup.lookupModes()` | Bitmask quyền, gồm `PUBLIC`, `PRIVATE`, `PROTECTED`, `PACKAGE`, `MODULE` ... |
| `lookup.in(SomeClass.class)` | Đổi ngữ cảnh với quyền không tăng lên |
| `MethodHandles.privateLookupIn(Target.class, lookup)` | Yêu cầu một lookup mới có quyền private trên `Target`, sau kiểm tra điều kiện |
| `lookup.findVirtual`, `findStatic`, `findVarHandle` | Tạo handle trên thành viên theo quyền lookup đang có |

`Lookup` là một **capability**: nếu code được nhận một lookup đủ mạnh hoặc một handle tới method private thì code đó có thể thực thi khả năng đã được cấp. Hạn chế chia sẻ các đối tượng này cho plugin/thành phần không đáng tin; đừng coi việc giấu tên method là hàng rào bảo mật.

## 3. Các điều kiện của `privateLookupIn` theo Java 17

Xét `M1` là module chứa `callerLookup.lookupClass()` và `M2` là module chứa `Target.class`.

### 3.1. Điều kiện chung

1. `callerLookup` phải có **cả `Lookup.PRIVATE` và `Lookup.MODULE`**. Một `Lookup` đã bị giới hạn bằng `publicLookup()` hay `dropLookupMode(...)` có thể không đủ quyền. `privateLookupIn` không tự lấy lại mode đã mất.
2. `Target` phải là một **class/interface thực**, không phải primitive, `void` hoặc array class; dùng `int.class`, `void.class`, `String[].class` làm target sẽ gây `IllegalArgumentException`.
3. `targetClass` và `callerLookup` không được `null`; nếu không sẽ có `NullPointerException`.
4. Với các kiểm tra quyền không đạt, lời gọi có thể ném **`IllegalAccessException`**. Trên môi trường Java 17 còn bật Security Manager, chính sách tương ứng cũng có thể gây `SecurityException`.

### 3.2. Khi `M1 == M2`

Khi lookup có đủ `PRIVATE`/`MODULE` và target nằm **cùng module**, `privateLookupIn` cho lookup có full-privilege access đến target, kể cả khác package trong module đó. Không cần thêm `opens` chỉ để làm private lookup **nội bộ cùng module**.

Điều này không có nghĩa cú pháp Java thông thường trong một lớp được phép gọi method private của lớp khác. Quyền mở rộng này được cấp qua API có kiểm tra `Lookup` và phải được người sở hữu lookup quyết định sử dụng.

### 3.3. Khi `M1 != M2`

Phải thỏa **đồng thời**:

- **`M1 reads M2`:** module gọi có quan hệ đọc đến module đích, ví dụ `requires vault.core;` trong `module-info.java`, hoặc cấu hình tương ứng khi chạy.
- **`M2 opens package chứa Target cho M1`:** ví dụ `opens demo.vault to demo.client;` trong descriptor của M2, hoặc thêm quyền mở đúng package qua `--add-opens vault.core/demo.vault=demo.client`.

Ngoài ra caller lookup vẫn phải có `PRIVATE` và `MODULE` như điều kiện chung. Chỉ có quyền đọc module hoặc chỉ có `exports` **chưa đủ** để truy cập thành viên private.

| Tình huống | `privateLookupIn(Target, caller)` |
| --- | --- |
| Cùng module, caller lookup đủ mode | Có thể tạo private lookup |
| Khác module, có `reads` và package được `opens` cho caller | Có thể tạo private lookup |
| Khác module, package chỉ `exports` | Không được phép private lookup |
| Khác module, package `opens` nhưng module caller không đọc module đích | Không đủ điều kiện |
| `publicLookup()` dù package đã `opens` | Không đủ `PRIVATE`/`MODULE` |
| Target là `int.class` hay `String[].class` | `IllegalArgumentException` |

> **Nguyên tắc:** kiểm tra module được thực hiện theo **module của lookup class**, không phải theo tên module do ứng dụng muốn giả định hoặc chỉ theo vị trí của file gọi API. Chuyển một `Lookup` qua API không làm nó có thêm quyền.

## 4. `exports` khác `opens` như thế nào?

`module-info.java` có hai khái niệm bổ sung nhau:

~~~java
module vault.core {
    exports demo.vault;
    opens demo.internal to demo.client;
}
~~~

- `exports demo.vault;`: cho các module đọc được `vault.core` sử dụng **kiểu public và thành viên public** trong package đó theo cơ chế truy cập thông thường. Không cho phép mở private members.
- `opens demo.internal to demo.client;`: cho phép **deep reflection** vào package `demo.internal` từ module `demo.client` (vẫn cần các điều kiện lookup/module phù hợp). Không phải lời tuyên bố rằng toàn bộ kiểu package đó có thể được import trực tiếp khi biên dịch.
- `opens demo.internal;`: mở cho mọi module; phạm vi rộng hơn cần thiết.
- `open module vault.core { ... }`: mở tất cả package trong module; chỉ chọn khi thực sự phù hợp.
- Một package có thể được `exports` và `opens` đồng thời nếu cần cả sử dụng API public lẫn reflection private.

Nếu không sở hữu mã nguồn module đích, JVM hỗ trợ tùy chọn khi chạy:

~~~bash
--add-opens vault.core/demo.vault=demo.client
~~~

Phần trước dấu `=` là `module/package` cần mở; phần sau là **module được cấp quyền**, không phải tên package. Với code chạy từ **classpath**, module đích có thể mở cho `ALL-UNNAMED`:

~~~bash
--add-opens vault.core/demo.vault=ALL-UNNAMED
~~~

`--add-exports` và `--add-opens` là hai cơ chế khác nhau: thêm `--add-exports` không cho phép truy cập private. `--add-opens` cũng không tự cấp mode `PRIVATE`/`MODULE` cho một caller lookup yếu, và không tạo một quan hệ `reads` còn thiếu. Với module có tên, `--add-reads source.module=target.module` có thể bổ sung quan hệ đọc khi thực sự cần.

## 5. Ví dụ 1 — gọi method private, thao tác field private trong cùng module

Chương trình Java 17+ sau gồm hai **top-level class** trong cùng tệp, đặt trên classpath (unnamed module). Chúng **không phải nestmate**; do đó lookup trực tiếp của `PrivateLookupDemo` không được truy cập member private của `TokenBox`.

Tạo tệp `PrivateLookupDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;

class TokenBox {
    private int count = 1;

    private String reveal(String prefix) {
        return prefix + "ok";
    }
}

public class PrivateLookupDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup caller = MethodHandles.lookup();

        try {
            caller.findVirtual(
                    TokenBox.class, "reveal",
                    MethodType.methodType(String.class, String.class));
        } catch (IllegalAccessException ex) {
            System.out.println("Direct lookup denied");
        }

        MethodHandles.Lookup privileged =
                MethodHandles.privateLookupIn(TokenBox.class, caller);

        MethodHandle reveal = privileged.findVirtual(
                TokenBox.class, "reveal",
                MethodType.methodType(String.class, String.class));

        TokenBox box = new TokenBox();
        System.out.println((String) reveal.invokeExact(box, "ID:"));

        VarHandle count = privileged.findVarHandle(
                TokenBox.class, "count", int.class);
        int before = (int) count.get(box);
        count.set(box, 5);
        int after = (int) count.get(box);
        System.out.println("count: " + before + " -> " + after);
    }
}
~~~

Chạy:

~~~bash
javac PrivateLookupDemo.java
java PrivateLookupDemo
~~~

Kết quả mong đợi:

~~~text
Direct lookup denied
ID:ok
count: 1 -> 5
~~~

**Phân tích:** `caller` được tạo trong `PrivateLookupDemo` nên `findVirtual` trực tiếp không thể đọc `TokenBox.reveal` private. `privateLookupIn` đổi ngữ cảnh có quyền sang `TokenBox`. `findVirtual` tạo handle có chữ ký logic gồm receiver `TokenBox` rồi tới tham số `String`; `invokeExact(box, "ID:")` đòi hỏi kiểu Java ở điểm gọi khớp chính xác. `findVarHandle` tạo quyền truy cập tới trường `int count`; `get` và `set` trên instance cũng thực hiện theo kiểu được khai báo.

Nếu đặt `TokenBox` thành **nested class** cùng nest với lớp gọi, Java có thể cho phép truy cập private bằng nestmate access ngay cả khi không dùng `privateLookupIn`. Vì vậy, ví dụ cố ý dùng hai top-level class để chỉ ra khác biệt.

## 6. Ví dụ 2 — hai module có tên: bị từ chối rồi mở package

Ta sẽ tạo module `vault.core` chứa `demo.vault.Vault` và module `demo.client` chứa chương trình thử nghiệm. `vault.core` **xuất API public** để `demo.client` biên dịch, nhưng ban đầu **chưa mở** package cho deep reflection.

Cấu trúc thư mục:

~~~text
src/
├── vault.core/
│   ├── module-info.java
│   └── demo/vault/Vault.java
└── demo.client/
    ├── module-info.java
    └── demo/client/Main.java
~~~

Tệp `src/vault.core/module-info.java`:

~~~java
module vault.core {
    exports demo.vault;
}
~~~

Tệp `src/vault.core/demo/vault/Vault.java`:

~~~java
package demo.vault;

public final class Vault {
    public Vault() {}

    private String secret() {
        return "ACCESS_GRANTED";
    }
}
~~~

Tệp `src/demo.client/module-info.java`:

~~~java
module demo.client {
    requires vault.core;
}
~~~

Tệp `src/demo.client/demo/client/Main.java`:

~~~java
package demo.client;

import demo.vault.Vault;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class Main {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup caller = MethodHandles.lookup();

        System.out.println("reads: "
                + Main.class.getModule().canRead(Vault.class.getModule()));
        System.out.println("open: "
                + Vault.class.getModule().isOpen(
                        "demo.vault", Main.class.getModule()));

        try {
            MethodHandles.Lookup target =
                    MethodHandles.privateLookupIn(Vault.class, caller);

            MethodHandle secret = target.findVirtual(
                    Vault.class, "secret",
                    MethodType.methodType(String.class));

            Vault vault = new Vault();
            System.out.println((String) secret.invokeExact(vault));
        } catch (IllegalAccessException ex) {
            System.out.println("Private lookup denied");
        }
    }
}
~~~

Tại thư mục chứa `src`, biên dịch và chạy (Java 17+):

~~~bash
javac --module-source-path src -d out -m vault.core,demo.client
java --module-path out -m demo.client/demo.client.Main
~~~

Kết quả khi `vault.core` chỉ có `exports`:

~~~text
reads: true
open: false
Private lookup denied
~~~

Quan hệ đọc có do `requires vault.core;`. Nhưng `exports demo.vault;` **không đồng nghĩa** `opens demo.vault;`; `privateLookupIn` ném `IllegalAccessException` trước khi tìm method.

Hãy chạy lại với quyền mở package chỉ cho `demo.client`:

~~~bash
java --module-path out \
  --add-opens vault.core/demo.vault=demo.client \
  -m demo.client/demo.client.Main
~~~

Dấu `\` ở cuối dòng là cú pháp nối dòng thường dùng trong shell Unix. Trên Windows PowerShell, có thể viết cùng lệnh **trên một dòng**:

~~~powershell
java --module-path out --add-opens vault.core/demo.vault=demo.client -m demo.client/demo.client.Main
~~~

Kết quả:

~~~text
reads: true
open: true
ACCESS_GRANTED
~~~

Để cấu hình bằng mã nguồn module thay vì flag chạy, đổi `src/vault.core/module-info.java` thành:

~~~java
module vault.core {
    exports demo.vault;
    opens demo.vault to demo.client;
}
~~~

Sau đó **biên dịch lại cả hai module** và chạy lệnh thông thường, không cần `--add-opens`. Đích mở là **module client**, không phải package `demo.client`; tên trùng chỉ là lựa chọn của ví dụ.

> Ví dụ hai module này đòi hỏi tổ chức thư mục và biên dịch bằng JPMS. Đặt mọi class lên classpath rồi chạy sẽ chuyển chúng vào unnamed module, nơi quy tắc mở package khác với một named module được đóng kín. Vì vậy không dùng một demo classpath để “chứng minh” named module đã mở hay chưa.

## 7. Điều gì xảy ra với lookup khi “teleport” qua module?

`privateLookupIn(Target.class, caller)` được mô tả là **teleport lookup** đến target:

- Nếu hai lớp thuộc **cùng module**, kết quả có full-privilege access trên target và `previousLookupClass()` là `null`.
- Nếu chuyển từ module `M1` sang module `M2` khác, kết quả có `PRIVATE` nhưng **mất `MODULE`**; `previousLookupClass()` ghi nhận lớp lookup ban đầu trong `M1`. Java 17 còn quy định lookup kết quả không có `ORIGINAL`.
- Vì không còn `MODULE`, không thể lấy kết quả đó làm `caller` cho một `privateLookupIn` thứ hai sang class/module khác. Không thể xâu chuỗi việc cấp quyền sâu tới các module theo cách này.

Để kiểm tra trong `Main` của ví dụ 2, sau khi tạo thành công `target` có thể thêm:

~~~java
System.out.println("target lookup class: "
        + target.lookupClass().getName());
System.out.println("previous lookup class: "
        + target.previousLookupClass().getName());
System.out.println("has MODULE: "
        + ((target.lookupModes() & MethodHandles.Lookup.MODULE) != 0));
~~~

Đoạn trên là **fragment**, chỉ chạy khi `target` được tạo từ hai module khác nhau; kết quả của `previousLookupClass()` khi đó không phải `null`:

~~~text
target lookup class: demo.vault.Vault
previous lookup class: demo.client.Main
has MODULE: false
~~~

Không áp dụng đoạn này máy móc vào trường hợp cùng module vì `previousLookupClass()` lúc đó có thể `null`. Sau khi đã có `MethodHandle` hợp lệ, Java chủ yếu kiểm tra kiểu gọi và khả năng thực thi của handle; không thực hiện lại phép cấp quyền `privateLookupIn` ở mỗi lần `invoke`. Vì vậy handle tới member private là đối tượng cần quản lý cẩn thận.

## 8. So sánh với Reflection `setAccessible(true)`

Java Reflection truyền thống có thể dùng `getDeclaredMethod`, `getDeclaredField` và `setAccessible(true)`; Method Handles tạo trực tiếp một handle từ `Lookup`. Cả hai chịu ràng buộc **strong encapsulation** của module system, nhưng thời điểm và API kiểm tra khác nhau.

| Nội dung | Reflection truyền thống | Method Handles |
| --- | --- | --- |
| Tìm member | `Class.getDeclaredMethod` / `getDeclaredField` | `Lookup.findVirtual` / `findVarHandle` |
| Yêu cầu truy cập sâu | `setAccessible(true)` hoặc `trySetAccessible()` | `MethodHandles.privateLookupIn(...)` |
| Module đóng package | Có thể bị `InaccessibleObjectException` / không mở được accessible | `privateLookupIn` có thể ném `IllegalAccessException` |
| Thực thi | `Method.invoke`, `Field.get/set` | `MethodHandle.invokeExact/invoke`, `VarHandle.get/set` |
| Kiểu lỗi khi gọi | `InvocationTargetException` có thể bọc lỗi từ method | MethodHandle thường truyền trực tiếp throwable của method; cũng cần xử lý sai kiểu gọi |

Không nên diễn giải `privateLookupIn` như một “bypass” tương đương `setAccessible(true)`. Cả hai chỉ hoạt động trong phạm vi quyền được Java cho phép. Một thư viện cần tương thích nhiều phiên bản nên yêu cầu module sở hữu dữ liệu **mở có chọn lọc** đúng package, thay vì khuyến nghị `open module` hoặc `--add-opens` tất cả package theo mặc định.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra / xử lý |
| --- | --- | --- |
| `IllegalAccessException` tại `privateLookupIn` | Caller thiếu `PRIVATE`/`MODULE`, không có `reads`, hoặc target package không `opens` | In `lookupModes()`, `canRead`, `isOpen`; kiểm tra descriptor/flag |
| `IllegalArgumentException` tại `privateLookupIn` | Target là primitive, void hoặc array | Dùng `Class` của class/interface thực |
| `IllegalAccessException` tại `findVirtual` sau khi có lookup | Thành viên không truy cập được bởi lookup hoặc chọn sai quyền/ngữ cảnh | Kiểm tra lookup thực sự dùng và declaring class |
| `NoSuchMethodException` tại `findVirtual` | Tên/`MethodType` không đúng, overload sai | Đối chiếu **kiểu trả về lẫn danh sách tham số** của MethodType |
| `NoSuchFieldException` tại `findVarHandle` | Tên field hoặc kiểu field không khớp | Đối chiếu kiểu field chính xác |
| `WrongMethodTypeException` lúc gọi handle | Sai kiểu ở điểm gọi `invokeExact` hay adapter type không phù hợp | So sánh `handle.type()` với kiểu receiver/argument/return |
| `ClassCastException` khi gọi handle | Đối tượng tại runtime không phù hợp khi có chuyển kiểu | Kiểm tra receiver và kiểu đối số |
| `InaccessibleObjectException` từ `setAccessible` | Package chưa mở cho deep reflection | Mở package đúng target hoặc chọn API public |
| Chạy được trên classpath nhưng lỗi trên module path | Khác biệt giữa unnamed module và named module | Chạy mẫu JPMS thật, kiểm tra `module-info.java` |

Checklist chẩn đoán ngắn (các dòng sau là **fragment** trong class đã import `MethodHandles` và biết `Target`):

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();
Module from = caller.lookupClass().getModule();
Module to = Target.class.getModule();
String pkg = Target.class.getPackageName();

System.out.println("PRIVATE: "
        + ((caller.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
System.out.println("MODULE: "
        + ((caller.lookupModes() & MethodHandles.Lookup.MODULE) != 0));
System.out.println("reads: " + from.canRead(to));
System.out.println("opens: " + to.isOpen(pkg, from));
~~~

Ở đây `Target` là lớp đích có sẵn trong chương trình, không phải tên API giả định. Kiểm tra thuộc tính này giúp xác định thiếu quyền nào **trước khi** dùng thử một thao tác truy cập private.

## 10. Thiết kế an toàn với module và Method Handle

1. **Sở hữu quyền mở package tại module đích.** Ưu tiên `opens package to trusted.module;` nếu thư viện thực sự cần deep reflection. Đối với tương tác thông thường, cung cấp public API qua `exports` hoặc qua service interface.
2. **Tạo lookup tại vị trí đáng tin.** `MethodHandles.lookup()` phải được gọi trong mã của module caller có quyền phù hợp; một lookup nhận từ `publicLookup` hoặc plugin không đáng tin không thể tự nâng cấp.
3. **Chỉ yêu cầu member cần thiết.** Sau khi có private lookup, tạo đúng `MethodHandle`/`VarHandle` cần dùng, không lưu và phát tán lookup đầy đủ nếu chỉ cần thao tác hẹp.
4. **Tách kiểm tra quyền và lỗi nghiệp vụ.** `IllegalAccessException` khi tạo lookup khác với `WrongMethodTypeException` khi gọi handle và lỗi do chính method đích ném.
5. **Không dựa vào tên package để suy ra quyền.** Module identity, `reads` và `opens` là các điều kiện runtime. Một package cùng tên trong hai module cũng không đương nhiên được cùng quyền truy cập.
6. **Không mở rộng vô tội vạ package của JDK.** Nếu chẩn đoán lỗi `java.base`, cân nhắc API được hỗ trợ thay vì dùng `--add-opens java.base/...=ALL-UNNAMED` trong sản phẩm.

`Lookup` mạnh là một quyền có thể ủy quyền. Khi một module mở package cho module khác, module nhận quyền có thể tạo handle tới member private trong package được mở; quyết định này có tác động đến ranh giới đóng gói của ứng dụng.

## 11. Câu hỏi tự kiểm tra

1. `publicLookup()` có đủ quyền gọi `privateLookupIn` không? **Không**, vì thiếu `PRIVATE` và `MODULE`.
2. Hai class khác package nhưng cùng named module có bắt buộc `opens` không? **Không chỉ vì khác package**; `privateLookupIn` với caller full-privilege có thể tạo lookup private cùng module.
3. Module client đã `requires vault.core;` và target package được `exports`, vậy đã gọi member private được chưa? **Chưa**; package còn phải `opens` cho client nếu khác module.
4. `--add-opens vault.core/demo.vault=demo.client` trao quyền cho ai? **Module `demo.client`**, không phải mọi module; vẫn cần caller lookup đủ mode.
5. Điều gì mất khi `privateLookupIn` chuyển giữa hai module có tên? **Mode `MODULE`** trên lookup kết quả; `previousLookupClass()` ghi nhận lớp lookup trước đó.
6. Vì sao cùng mã nguồn chạy trên classpath đôi khi khác module path? **Unnamed module mở package**, còn named module có mô tả `exports`/`opens` và các quan hệ đọc được kiểm tra.
7. Một `MethodHandle` đã được tạo thành công có cần gọi lại `privateLookupIn` trước mỗi `invokeExact` không? **Không**; phải dùng handle đúng chữ ký và giữ an toàn capability đã được cấp.

## 12. Tài liệu chính thức

- [Java SE 17 — MethodHandles và privateLookupIn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Oracle Java 17 Migration Guide — --add-opens](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html)

**Ghi nhớ:** `privateLookupIn` chỉ thành công khi caller lookup có **`PRIVATE` + `MODULE`**; nếu target ở module khác, cần thêm **`reads`** và **`opens`** đúng package/đúng module. `exports` chỉ giúp sử dụng API public, không mở private member. Sau khi được cấp quyền, `MethodHandle`/`VarHandle` là capability thực sự có thể thực thi và cần được quản lý cẩn thận.