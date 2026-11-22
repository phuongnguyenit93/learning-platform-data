# Chẩn đoán lỗi khả năng đọc module, exports và opens trong Java JPMS

Khi chạy ứng dụng Java có **Java Platform Module System (JPMS)**, một class tồn tại trong JAR và có modifier `public` vẫn có thể không được module khác truy cập. Một lời gọi reflection có thể thất bại mặc dù class đã load thành công, hoặc code chạy trong IDE nhưng sinh `IllegalAccessError` khi deploy. Ba nhóm nguyên nhân thường bị trộn lẫn là **readability** (khả năng đọc module), **exports** (quyền truy cập API công khai của package) và **opens** (quyền truy cập phản chiếu sâu).

Chẩn đoán đúng đòi hỏi biết **ai đang truy cập**, **class thuộc module nào**, **package nào chứa class**, **quyền nào đang thiếu** và **kiểm tra xảy ra lúc compile, link hay reflection runtime**. Không nên dùng `--add-opens` cho toàn JVM như một câu thần chú chữa mọi lỗi: nó không thay thế việc resolve module, không tự tạo dependency compile-time, không tìm class bị thiếu và làm yếu đóng gói nếu mở quá rộng.

Bài này áp dụng cho **Java 17+**, có một ví dụ Java 17 đã được biên dịch/chạy với ba chế độ: mặc định, chỉ `--add-exports` và chỉ `--add-opens`. Ngoài ra có các ca compile-time `does not read`, `does not export` và runtime `IllegalAccessError` được tái hiện riêng, kèm quy trình quan sát module graph bằng công cụ JDK.

## 1. Ba câu hỏi cần hỏi theo đúng thứ tự

Hãy gọi module đang thực hiện thao tác là **consumer** `C`, module chứa class mục tiêu là **library/provider** `L`, package chứa class là `p`.

| Tầng kiểm tra | Câu hỏi | API chẩn đoán | Cách khai báo/cấp quyền điển hình |
| --- | --- | --- | --- |
| **Reads** | `C` có đọc `L` không? | `C.canRead(L)` | `requires L;` hoặc quan hệ runtime được cấp hợp lệ |
| **Exports** | `L` có export package `p` cho `C` không? | `L.isExported(p, C)` | `exports p;`, `exports p to C;`, hoặc override có giới hạn |
| **Opens** | `L` có open package `p` cho module thực hiện reflection không? | `L.isOpen(p, caller)` | `opens p;`, `opens p to caller;`, hoặc override có giới hạn |

**Hướng của quan hệ dễ nhầm nhất:**

~~~text
module C (consumer/caller)                  module L (library/provider)
      |                                                  |
      +------------------ reads ----------------------->  |
                                                         |
      <------------------- exports p --------------------+
      <-------------------- opens p ---------------------+

C.canRead(L)               // hướng C -> L
L.isExported("p", C)        // package của L -> C
L.isOpen("p", C)            // package của L -> C
~~~

Điều kiện truy cập thông thường từ code của module `C` đến một **public type** trong package `p` của module `L` bao gồm `C` đọc `L` và `L` export `p` cho `C` (cộng các điều kiện visibility Java thông thường). Để **reflection sâu** vào private member trong package `p`, package phải được mở thích hợp cho module thực sự gọi API reflection, trừ những trường hợp Java cho phép `setAccessible` mà không cần opens vì quyền truy cập vốn đã hợp lệ.

**Lưu ý:** `opens` không giống `exports` trong ý nghĩa nguồn, nhưng **open package cũng được coi là exported ở runtime** khi kiểm tra bằng `Module.isExported`. Điều này được minh họa trong ví dụ thực nghiệm: sau `--add-opens`, cả `isOpen` và `isExported` đều trả `true` cho cùng target. Nếu muốn biết một package đã được export/open **trong descriptor tĩnh**, hãy quan sát `ModuleDescriptor.exports()`/`opens()` chứ không suy từ một kiểm tra runtime đơn lẻ.

## 2. Readability: module consumer có thực sự đọc module đích?

Ví dụ một ứng dụng phụ thuộc API của thư viện:

~~~java
module diag.consumer {
    requires diag.library;
}
~~~

Khi hai module được resolve theo đúng configuration, quan hệ `requires diag.library;` thường tạo khả năng `diag.consumer` **đọc** `diag.library`. Đây là câu hỏi về **module graph**, không phải liệu `diag.library.jar` có tồn tại trong thư mục.

Một module có thể xuất hiện trên `--module-path` nhưng **chưa được resolve** vào graph đang chạy. Ngược lại, một classloader có thể tìm class bằng cơ chế đặc biệt mà compile-time readability chưa được khai báo; đừng đánh đồng việc load class với quyền dùng public API.

### 2.1. Dấu hiệu thiếu readability

Nếu source trong `diag.consumer` viết:

~~~java
import diag.library.api.Greeter;

public final class Probe {
    String text = Greeter.sayHello();
}
~~~

đây là **đoạn minh họa**; để dùng, file phải có khai báo `package` đúng với vị trí của nó. Khi `diag.consumer` không khai báo `requires diag.library;`, compiler có thể báo:

~~~text
package diag.library.api is not visible
(package diag.library.api is declared in module diag.library, but module diag.consumer does not read it)
~~~

Thông báo đã nêu trực tiếp **module nào không đọc module nào**. Sửa đúng trong dự án module rõ ràng là bổ sung `requires diag.library;` nếu dependency là cần thiết, thay vì mở package bằng `opens`.

### 2.2. `requires`, `requires transitive` và `requires static`

- `requires L;`: module đang khai báo đọc module `L`.
- `requires transitive L;`: trong đúng quan hệ graph, mở rộng readability sang module phụ thuộc vào module đang khai báo; hữu ích khi hợp đồng public API của một module có sử dụng type từ module khác. Không dùng `transitive` để chữa lỗi access một cách tùy tiện.
- `requires static L;`: yêu cầu dependency ở compile time nhưng có thể vắng mặt khi chạy theo hợp đồng optional dependency; nếu code thật sự cần class mà runtime không có, vẫn có thể thất bại. Không coi `requires static` là giải pháp để “tự tìm” module.
- `--add-reads C=L`: có thể bổ sung read edge có phạm vi trong thao tác compile/launcher phù hợp, thường để chẩn đoán hoặc hỗ trợ migration. Nó không thay thế việc khai báo module lâu dài nếu phụ thuộc là tĩnh.

**Tầng đầu tiên cần xác minh** là module `L` đã được resolve đúng chưa, sau đó mới hỏi `C.canRead(L)`. `--add-reads` không tự đưa một module hoàn toàn vắng mặt vào graph; khi cần có thể phải điều chỉnh root modules/module path.

## 3. Exports: đọc được module chưa đồng nghĩa thấy mọi package

Một module chỉ expose public API có chọn lọc:

~~~java
module diag.library {
    exports diag.library.api;
}
~~~

Đoạn descriptor trên **không export** `diag.library.internal`. Dù một class trong package nội bộ có modifier `public`, named module khác không được mặc nhiên truy cập bằng ordinary compiled code.

| Dạng descriptor | Ai có quyền truy cập public types trong package? |
| --- | --- |
| `exports diag.library.api;` | Các module đọc được module nguồn, theo các điều kiện khác |
| `exports diag.library.api to diag.consumer;` | Chỉ các module đích được liệt kê |
| Không có `exports` cho package | Package được encapsulate đối với ordinary access từ module khác |
| `opens diag.library.internal to diag.consumer;` | Package được open cho reflection sâu và được xem là exported ở runtime cho target, nhưng **không** đồng nghĩa có thể import nó khi compile mà không có cấu hình cần thiết |

Một package **không tự export các subpackage**. Ví dụ `exports diag.library;` không có nghĩa export `diag.library.internal;`.

Một class `public` trong package không export vẫn có thể được một loader tìm thấy hoặc tên class được reflection nhìn thấy; lỗi access có thể xảy ra **sau bước tìm class**, khi dùng public type/member hoặc khi yêu cầu deep reflection. Vì vậy `Class.forName(...)` thành công không xác nhận rằng ordinary access hay `setAccessible(true)` chắc chắn thành công.

### 3.1. Dấu hiệu thiếu exports

Với class `public diag.library.internal.Vault` nhưng descriptor không export package đó, khi consumer cố import:

~~~java
package diag.consumer;

import diag.library.internal.Vault;

public final class CompileProbe {
    public static void main(String[] args) {
        System.out.println(Vault.class.getName());
    }
}
~~~

Java compiler sẽ báo dạng:

~~~text
package diag.library.internal is not visible
(package diag.library.internal is declared in module diag.library, which does not export it)
~~~

**Khác hoàn toàn** thông báo thiếu readability `does not read`. Nếu consumer đã có `requires diag.library;` mà vẫn lỗi, việc thêm `requires` lần nữa không làm package được export.

Cách sửa bền vững: chỉ export **package API thật sự thuộc hợp đồng public**. Nếu code consumer đang import implementation internal, cân nhắc refactor sang interface/service API thay vì export cả package nội bộ. `--add-exports diag.library/diag.library.internal=diag.consumer` là biện pháp có thể dùng để phân biệt nguyên nhân, hỗ trợ migration có kiểm soát hoặc code đã được chủ thư viện chấp thuận; đừng coi nó là chính sách mặc định lâu dài.

## 4. Opens: reflection sâu qua ranh giới module

`exports` chủ yếu phục vụ quyền truy cập thông thường vào **public API**; `opens` cho phép framework phản chiếu sâu hơn vào các member không public trong phạm vi package được cấp quyền.

Ví dụ framework muốn đọc private field:

~~~java
Class<?> type = Class.forName("diag.library.internal.Vault");
var field = type.getDeclaredField("TOKEN");
field.setAccessible(true);
System.out.println(field.get(null));
~~~

Đây là snippet minh họa; cần các imports/exception handling trong chương trình hoàn chỉnh. Nếu package `diag.library.internal` chưa open cho module chứa đoạn reflection, `setAccessible(true)` thường ném `java.lang.reflect.InaccessibleObjectException`. Tương tự, `trySetAccessible()` có thể trả `false` thay vì ném lỗi khi không được phép.

### 4.1. Phân biệt bốn trường hợp

| Mục tiêu | Quyền thường cần | Ghi chú |
| --- | --- | --- |
| Gọi public member của public class từ code biên dịch trong module khác | Reads từ consumer và exports từ provider | Còn phải đáp ứng visibility Java |
| Reflection thông thường vào public member của public class đã export | Export public API phù hợp | Không nhất thiết cần opens nếu không phá access checks |
| `setAccessible(true)` để chạm private member từ module khác | **Opens** package cho module thực hiện reflection | Export **đơn thuần không đủ** |
| Host trên classpath cần deep reflection vào named module | Opens package cho **unnamed module thực sự gọi reflection** | Nếu phải dùng launcher, có thể nhắm `ALL-UNNAMED`; phạm vi rộng, cần cân nhắc |

**Không nhầm module của business caller và module của reflection framework.** Nếu Hibernate/Jackson/framework chạy trong module riêng và chính framework gọi `setAccessible`, target opens phải là module của framework, không phải tên module của controller gọi framework ở tầng trên.

**Độ chính xác bổ sung:** các core reflection APIs xử lý readability theo quy tắc riêng (các access checks bằng reflection có giả định readability). Vì vậy đừng chỉ nhìn `C.canRead(L)==false` rồi khẳng định đó là lý do duy nhất khiến một `setAccessible` thất bại. Hãy đọc message của exception, xác định module thực thi reflective access và kiểm tra `isOpen`/`isExported` phù hợp. Với truy cập **ordinary bytecode**, readability vẫn là một điều kiện nền tảng riêng biệt.

### 4.2. Qualified opens khác mở toàn bộ module

~~~java
module diag.library {
    exports diag.library.api;
    opens diag.library.internal to diag.consumer;
}
~~~

Descriptor trên open riêng `diag.library.internal` cho `diag.consumer`. Không cần `open module diag.library { ... }` chỉ để một framework đọc một package. `open module` mở sâu mọi package của module, làm giảm khả năng đóng gói nhiều hơn.

## 5. Bài thực hành Java 17: ba chế độ truy cập một package nội bộ

Tạo hai **explicit named modules** và năm tệp sau; ví dụ chạy hoàn chỉnh với JDK 17+. Nó minh họa rõ sự khác nhau giữa `reads`, `exports`, `opens` bằng cách quan sát cả API `Module` và một thao tác `Field.setAccessible`. Không dùng thư viện ngoài.

### 5.1. Cấu trúc thư mục

~~~text
src/
├── diag.library/
│   ├── module-info.java
│   └── diag/library/
│       ├── api/Greeter.java
│       └── internal/Vault.java
└── diag.consumer/
    ├── module-info.java
    └── diag/consumer/Main.java
~~~

Tệp **`src/diag.library/module-info.java`**:

~~~java
module diag.library {
    exports diag.library.api;
}
~~~

Đây là module thư viện có public API ở `diag.library.api` nhưng giữ `diag.library.internal` không export/open.

Tệp **`src/diag.library/diag/library/api/Greeter.java`**:

~~~java
package diag.library.api;

public final class Greeter {
    private Greeter() {}
    public static String sayHello() { return "hello"; }
}
~~~

Tệp **`src/diag.library/diag/library/internal/Vault.java`**:

~~~java
package diag.library.internal;

public final class Vault {
    private static final String TOKEN = "sealed";
}
~~~

`Vault` có modifier `public` để người học không nhầm nguyên nhân với việc class package-private; lỗi ở đây là **package chưa export/open** và field là private.

Tệp **`src/diag.consumer/module-info.java`**:

~~~java
module diag.consumer {
    requires diag.library;
}
~~~

Consumer đã đọc được library, nên ví dụ có thể tách lỗi **exports/opens** khỏi lỗi thiếu **reads**.

Tệp **`src/diag.consumer/diag/consumer/Main.java`**:

~~~java
package diag.consumer;

import diag.library.api.Greeter;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module app = Main.class.getModule();
        Module lib = Greeter.class.getModule();
        System.out.println("reads=" + app.canRead(lib));
        System.out.println("apiExported=" + lib.isExported("diag.library.api", app));
        System.out.println("internalExported=" + lib.isExported("diag.library.internal", app));
        System.out.println("internalOpen=" + lib.isOpen("diag.library.internal", app));
        System.out.println("apiCall=" + Greeter.sayHello());

        Class<?> vault = Class.forName("diag.library.internal.Vault");
        Field token = vault.getDeclaredField("TOKEN");
        try {
            token.setAccessible(true);
            System.out.println("token=" + token.get(null));
        } catch (InaccessibleObjectException expected) {
            System.out.println("privateAccess=denied");
        }
    }
}
~~~

**Giải thích các điểm quyết định:**

- `Main.class.getModule()` lấy module đang thực hiện reflection, không lấy nhầm module chứa `Vault`.
- `Greeter.class.getModule()` trả module chứa class public API; ở đây chính là module chứa `Vault`.
- `canRead` đo quan hệ consumer → provider; `isExported`/`isOpen` đo package provider → consumer.
- `Greeter.sayHello()` được compiler cho phép do `requires` + `exports diag.library.api;`.
- `Class.forName` chỉ lấy class object, không chứng minh có quyền phá đóng gói private field.
- `getDeclaredField("TOKEN")` có thể tìm private field, nhưng `setAccessible(true)` là bước thử quyền deep reflection.
- Catch chỉ `InaccessibleObjectException` làm output xác định cho trường hợp thiếu opens; exception khác vẫn có thể nổi lên để không che lỗi cấu hình khác.

### 5.2. Biên dịch

Từ thư mục chứa `src/`:

~~~bash
javac --release 17 --module-source-path src -d mods -m diag.library,diag.consumer
~~~

`--module-source-path src` ánh xạ folder tên module tới source tree, `-d mods` chứa output theo module. `--release 17` giúp kiểm tra tương thích Java 17 ngay cả khi compiler thực tế mới hơn. Ví dụ đã được biên dịch và chạy bằng Amazon Corretto JDK 17.

### 5.3. Chạy mặc định: reads có, API exported, internals đóng

~~~bash
java --module-path mods -m diag.consumer/diag.consumer.Main
~~~

Stdout **chính xác**:

~~~text
reads=true
apiExported=true
internalExported=false
internalOpen=false
apiCall=hello
privateAccess=denied
~~~

Từ kết quả này:

1. `reads=true` xác nhận `requires diag.library;` đã thiết lập readability.
2. `apiExported=true` xác nhận package public API truy cập được.
3. `internalExported=false` và `internalOpen=false`: internal package chưa cấp quyền cho consumer.
4. Lời gọi public API vẫn chạy được (`hello`), chỉ có deep reflection vào `TOKEN` bị chặn.
5. Bản thân việc `Class.forName` trả `Class<?>` không phải bằng chứng đủ để gọi private member.

### 5.4. Chỉ cấp --add-exports: vẫn không đọc được private field

~~~bash
java --module-path mods --add-exports diag.library/diag.library.internal=diag.consumer -m diag.consumer/diag.consumer.Main
~~~

Stdout **chính xác**:

~~~text
reads=true
apiExported=true
internalExported=true
internalOpen=false
apiCall=hello
privateAccess=denied
~~~

`--add-exports` thay đổi quyền truy cập public API của package **cho đúng target module**, nhưng **không** mở deep reflection vào private member. Vì thế `setAccessible(true)` tiếp tục thất bại. Đây là một phép thử hữu ích khi troubleshooting: nếu một framework chỉ thiếu opens, việc thêm exports không sửa được vấn đề cốt lõi.

### 5.5. Chỉ cấp --add-opens: deep reflection thành công

~~~bash
java --module-path mods --add-opens diag.library/diag.library.internal=diag.consumer -m diag.consumer/diag.consumer.Main
~~~

Stdout **chính xác**:

~~~text
reads=true
apiExported=true
internalExported=true
internalOpen=true
apiCall=hello
token=sealed
~~~

Hai phát hiện quan trọng:

- `internalOpen=true` và `token=sealed` xác nhận package đã open cho **đúng module gọi reflection**; private field được truy cập.
- **`internalExported=true` dù chỉ thêm `--add-opens`**. JDK coi open package là exported trong runtime access checks; không nên suy từ `isExported(true)` rằng descriptor ban đầu có mệnh đề `exports`.

**Cả ba lệnh đã được biên dịch/chạy và đối chiếu stdout thực tế với JDK 17.** Kết quả này là cố định cho bộ module/code của bài, không phụ thuộc vào số plugin hay thứ tự phát hiện provider ngoài môi trường.

## 6. Tái hiện lỗi biên dịch: thiếu reads và thiếu exports

Phần này mô tả **biến thể cố ý sai để thấy diagnostic**, không thêm chúng vào project demo đúng cùng lúc. Giữ code ở mục 5 làm baseline; sửa riêng từng ca rồi hoàn nguyên.

### 6.1. Ca A — module consumer không đọc library

Tạm đổi `src/diag.consumer/module-info.java` thành:

~~~java
module diag.consumer { }
~~~

Giữ nguyên `Main.java` đang import `diag.library.api.Greeter` và chạy lại:

~~~bash
javac --release 17 --module-source-path src -d mods -m diag.library,diag.consumer
~~~

Compiler từ chối vì `diag.consumer` **không đọc** `diag.library`. Thông điệp cốt lõi đã được tái hiện trong fixture riêng:

~~~text
package diag.library.api is not visible
(package diag.library.api is declared in module diag.library, but module diag.consumer does not read it)
~~~

**Cách sửa đúng:** thêm `requires diag.library;` trở lại descriptor của consumer. `--add-opens` cho package API sẽ không thay thế trực tiếp một quan hệ readability compile-time vốn bị thiếu. Khi có `requires`, mới tiếp tục chẩn đoán package exports nếu cần.

### 6.2. Ca B — consumer đọc được library nhưng muốn import internal

Khôi phục `module diag.consumer { requires diag.library; }`. Giả sử thêm file **`src/diag.consumer/diag/consumer/CompileProbe.java`**:

~~~java
package diag.consumer;

import diag.library.internal.Vault;

public final class CompileProbe {
    public static void main(String[] args) {
        System.out.println(Vault.class.getName());
    }
}
~~~

Chạy lại lệnh `javac` ở mục 6.1. Vì `diag.library.internal` chưa export, compiler từ chối. Thông báo cốt lõi đã được tái hiện:

~~~text
package diag.library.internal is not visible
(package diag.library.internal is declared in module diag.library, which does not export it)
~~~

Lúc này **readability đã đúng**, lỗi ở việc package không export. Có ba hướng cân nhắc: không dùng internal type mà chuyển sang API đã export (ưu tiên), sửa descriptor thư viện nếu package thật sự là public contract, hoặc cấp `--add-exports` có chọn lọc khi bạn hiểu và chấp nhận coupling nội bộ.

### 6.3. Ca C — compile có quyền nhưng runtime thiếu quyền

Nếu compile với targeted override, ví dụ:

~~~bash
javac --release 17 --module-path mods --module-source-path src --add-exports diag.library/diag.library.internal=diag.consumer -d out -m diag.consumer
~~~

thì compiler có thể cho `CompileProbe` liên kết đến `Vault`. Nhưng nếu **runtime** không có export tương đương trong module graph, JVM có thể ném:

~~~text
java.lang.IllegalAccessError: class diag.consumer.CompileProbe (in module diag.consumer) cannot access class diag.library.internal.Vault (in module diag.library) because module diag.library does not export diag.library.internal to module diag.consumer
~~~

Dòng trên thể hiện **mẫu lỗi**, tên class tùy variant. Trong fixture kiểm thử riêng đã quan sát `IllegalAccessError` tương ứng, và khi thêm lại `--add-exports diag.library/diag.library.internal=diag.consumer` vào JVM thì code truy cập public class chạy được.

Bài học: **compiler flags và JVM launcher flags là hai giai đoạn khác nhau**. Cấp override cho một lượt `javac` không tự lưu quyền đó vào `module-info.class` hay bảo đảm JVM production cấp lại cùng quyền. Đặc biệt, tránh dùng quyền tạm thời để mã hóa sự phụ thuộc dài hạn vào internal API.

### 6.4. Không đoán lỗi từ một chữ “inaccessible”

- **`does not read`** → hỏi quan hệ reads và module resolution.
- **`does not export`** → hỏi exports của package đối với target.
- **`does not open`** trong `InaccessibleObjectException` → hỏi deep reflection/opens đối với module thực hiện reflection.
- **`ClassNotFoundException`** → hỏi loader/module path, không gắn ngay vào `opens`.
- **`IllegalAccessError`** → hỏi runtime access check trong bytecode/linkage, có thể khác quyền ở compile time.

Đọc toàn bộ thông báo, đặc biệt tên **source module**, **target module**, **package** và class, thay vì chỉ tìm một từ khóa lỗi rồi thêm flag.

## 7. Công cụ JDK để điều tra theo bằng chứng

### 7.1. Đầu tiên xác định JDK và cách chạy

~~~bash
java -version
javac -version
java --list-modules
~~~

Phải kiểm tra Java thực sự được launcher/deployment dùng, không chỉ Java SDK mà IDE hiển thị. Trong môi trường nhiều JDK, `javac` và `java` có thể thuộc hai phiên bản khác nhau. Với custom runtime images (`jlink`), module list có thể nhỏ hơn JDK đầy đủ.

Cần biết process thực sự chạy với `--class-path` hay `--module-path`, class nào là main class, tên module gốc là gì và các launcher flags đã áp dụng thế nào.

### 7.2. Xem descriptor của module đang được tìm thấy

Trong project mục 5, lệnh:

~~~bash
java --module-path mods --describe-module diag.library
~~~

Cho biết module `diag.library`, các package được export và các package chỉ chứa nội bộ. Bản đã kiểm thử có những phần có ý nghĩa:

~~~text
exports diag.library.api
requires java.base mandated
contains diag.library.internal
~~~

Đường dẫn module trong output phụ thuộc máy nên không ghi cố định ở đây. Nếu module `diag.library` đã được build thành JAR, `jar --describe-module --file path/to/diag.library.jar` có thể kiểm tra descriptor của đúng file JAR được phân phối.

**Cẩn thận với phiên bản artifact:** build output trong IDE, JAR trong repository và JAR trong production có thể khác. Hãy kiểm tra file/runtime **thực sự đang sử dụng**, không đọc một bản `module-info.java` chưa build rồi kết luận graph phải giống nó.

### 7.3. Xem module resolution lúc khởi động

~~~bash
java --module-path mods --show-module-resolution -m diag.consumer/diag.consumer.Main
~~~

JDK ghi ra graph được resolve trước khi chạy chương trình. Trong fixture của bài, xuất hiện quan hệ:

~~~text
diag.consumer requires diag.library
~~~

Kết quả đầy đủ có thể chứa nhiều module hệ thống và các dòng `binds` khác tùy JDK/environment. **Không so khớp nguyên văn toàn bộ stdout** của lệnh này như một test cố định; chỉ lấy thông tin module gốc, dependency edge và provider binding thực sự cần chẩn đoán.

Nếu `diag.library` không nằm trong resolved graph, kiểm tra `--module-path` và root modules. Một JAR đặt trong thư mục module path nhưng không được resolve **chưa đủ** để `--add-opens` có ý nghĩa với đúng module đích.

### 7.4. Dùng jdeps phân tích phụ thuộc tĩnh

~~~bash
jdeps --module-path mods --check diag.consumer
~~~

Trên fixture đã kiểm thử, `jdeps` chỉ ra descriptor của `diag.consumer` có `requires diag.library;` và dependency mặc định tới `java.base`. `jdeps` có thể giúp phát hiện phụ thuộc không cần thiết, đường truy cập qua internal JDK APIs và dự đoán vấn đề trước runtime.

**Giới hạn:** phân tích static dependency không nhìn thấy mọi `Class.forName`/reflection dựa trên tên string, provider được nạp động hoặc module layer được tạo sau đó. Vì thế `jdeps` báo graph hợp lệ **không** có nghĩa ứng dụng không thể gặp `InaccessibleObjectException` khi framework chạy.

### 7.5. Logging module của JVM (khi cần)

JDK hỗ trợ Unified Logging; có thể dùng tùy cấu hình:

~~~bash
java -Xlog:module=debug --module-path mods -m diag.consumer/diag.consumer.Main
~~~

Đây là **lệnh chẩn đoán bổ sung**, không phải lựa chọn mặc định cho mọi production run. Log có thể nhiều, khác giữa các bản JDK; nên chỉ bật ở môi trường có kiểm soát, giới hạn dung lượng và thời gian thu thập. Không dựa vào wording cụ thể trong debug log để xây API nghiệp vụ.

### 7.6. Ghi runtime module identity trong code

Đoạn dưới đây đặt trong method có đối tượng class mục tiêu và caller:

~~~java
Module caller = Main.class.getModule();
Module target = Greeter.class.getModule();

System.out.println(caller.getName());
System.out.println(target.getName());
System.out.println(caller.canRead(target));
System.out.println(target.isExported("diag.library.api", caller));
System.out.println(target.isOpen("diag.library.internal", caller));
~~~

Đây là **snippet phụ thuộc các class trong ví dụ**, không phải source file độc lập. Khi chẩn đoán plugin, nên log thêm `caller.getLayer()`, `target.getLayer()`, class loader của hai class, tên package và tên method/field gây lỗi. Hai module cùng tên trong **hai layers/loaders khác nhau** không nhất thiết là cùng đối tượng module; nên lấy Module từ **Class<?> thực tế đang được dùng**.

## 8. Cách khoanh vùng từng loại exception

| Exception/diagnostic | Xảy ra thường ở bước | Bằng chứng cần lấy | Ưu tiên sửa |
| --- | --- | --- | --- |
| `error: module not found: X` | Compile/resolve module graph | `--module-path`, module name, artifact, `requires X` | Đúng artifact/path/module name/roots |
| `FindException` hoặc `ResolutionException` | Resolve cấu hình/boot layer | Root modules, descriptors, version constraints, cyclic/conflicting packages | Sửa module graph/packaging |
| `package ... is not visible: does not read` | Compile-time | Consumer descriptor và target module đã được tìm thấy | `requires` hoặc mô hình dependency đúng |
| `package ... is not visible: does not export` | Compile-time | Provider `exports`/qualified target | Export API cần thiết hoặc bỏ dùng internal package |
| `IllegalAccessError` | Bytecode linkage/access ở runtime | Cặp module thực tế và flags compile/runtime | Đồng bộ quyền hoặc sửa descriptor/API |
| `IllegalAccessException` | Java reflection checks | Member modifier, class visibility, export/open, caller module | Quyền reflective phù hợp hoặc dùng public API |
| `InaccessibleObjectException` | `setAccessible` không mở được access | Package, target module của reflection, `isOpen` | Qualified opens đúng chỗ, tránh broad opens |
| `ClassNotFoundException` | Class loading dựa trên tên | Loader, classpath/module path, package/module thật | Sửa loading/distribution |
| `NoClassDefFoundError` | Dùng class đã từng compile nhưng thiếu lúc runtime/linking | Dependency, cause chain, classloader identity | Sửa artifact/module resolution/dependency |
| `ServiceConfigurationError` | Tìm/khởi tạo service provider | `uses`, `provides`, `META-INF/services`, constructor/factory, dependencies | Sửa cấu hình SPI/provider trước khi sửa exports/opens |
| `InvocationTargetException` | Invocation qua reflection | `getCause()` là exception từ method được gọi | Chẩn đoán lỗi nghiệp vụ của method nếu access đã qua |

**Không phải mọi lỗi hiện chữ “module” đều do access policy.** `FindException` có thể xảy ra trước khi class được load; `NoClassDefFoundError` có thể do JAR thiếu hoặc lỗi khởi tạo class. Mở package không tạo ra bytecode còn thiếu.

### 8.1. `IllegalAccessError` khác `IllegalAccessException`

- `IllegalAccessError` là **LinkageError** phát sinh ở tầng JVM khi một instruction/linkage không được phép truy cập, thường sau khi bytecode đã biên dịch trong điều kiện khác với runtime.
- `IllegalAccessException` là checked exception được reflection API ném khi quyền truy cập Java/JPMS không đáp ứng.
- `InaccessibleObjectException` là runtime exception thường gặp ở `setAccessible(true)` khi package không mở để suppress access checks.

Thử bắt một `IllegalAccessException` không bắt được `IllegalAccessError`. Cách xử lý vận hành là **sửa graph/packaging**, không catch `Throwable` để che việc JDK từ chối truy cập.

### 8.2. Xác định module nào thực sự gọi reflection

Giả sử ứng dụng `business.app` gọi thư viện framework `example.mapper`, framework lại gọi `setAccessible(true)` vào entity ở module `domain.model`:

~~~text
business.app  ---> example.mapper ---> reflection on domain.model/privateField
                       |
                       +-- module thực hiện setAccessible()
domain.model ------------------------ opens p to example.mapper
~~~

Thông thường package `p` phải được mở **cho `example.mapper`**, không đơn giản cho `business.app`. Nếu framework nằm trên classpath, target có thể là unnamed module; lúc dùng launcher `--add-opens domain.model/p=ALL-UNNAMED` cần hiểu phạm vi bao gồm **mọi unnamed module** trong process, không chỉ thư viện đó.

Dùng code `SomeFrameworkClass.class.getModule()` (khi có thể) hoặc stack trace để xác định đúng caller. Không dùng tên JAR như thể tự động bằng tên module JPMS.

## 9. Runtime overrides: chữa triệu chứng hay giải quyết hợp đồng?

Java cung cấp nhiều cách nới quan hệ module. Nên hiểu hướng, giai đoạn áp dụng và phạm vi.

| Cơ chế | Thêm quyền gì | Khi nào có ích |
| --- | --- | --- |
| `requires L;` | Read edge có chủ đích trong descriptor của consumer | Dependency tĩnh lâu dài |
| `exports p;` / `exports p to C;` | Public API package trong provider | Hợp đồng compile-time rõ ràng |
| `opens p;` / `opens p to F;` | Deep reflection permission từ provider tới framework | Framework hợp lệ cần field/constructor không public |
| `--add-reads C=L` | Bổ sung reads ở giai đoạn tool/launcher phù hợp | Debug/migration, dependency ngoài descriptor |
| `--add-exports L/p=C` | Bổ sung export package từ provider sang target | Debug một internal API hoặc cấu hình tương thích có chọn lọc |
| `--add-opens L/p=F` | Bổ sung opens package cho caller reflection | Debug reflection hay framework có chủ đích |
| `Module.addReads/addExports/addOpens` | Module tự điều chỉnh quyền theo hạn chế caller | Code có quyền trong module nguồn |
| `ModuleLayer.Controller` | Host có controller điều chỉnh các **source module thuộc layer mà controller quản lý** | Hệ plugin/runtime tạo module layer mới |

### 9.1. Không dùng tất cả các flags cùng lúc để chẩn đoán

Nếu ngay lần thử đầu đã thêm `--add-reads`, `--add-exports` và `--add-opens` cho mọi package, có thể làm ứng dụng chạy được nhưng **mất bằng chứng nguyên nhân**. Thử tối thiểu theo chuỗi: xác nhận module được resolve → reads → exports → reflection opens. Mỗi lần chỉ sửa **một quyền mục tiêu**, ghi nhận thay đổi trong `canRead`/`isExported`/`isOpen` và kết quả exception.

### 9.2. Compile-time và runtime không phải cùng một configuration

Ví dụ `javac --add-exports` có thể cho phép import một internal type, trong khi `java` chạy không có flag sẽ vẫn từ chối ở runtime. Phải kiểm tra **hai command lines thực tế** và file `module-info.class` sau compile; IDE test runner cũng có thể tự thêm flags khác với artifact production.

Ngược lại, thêm `--add-exports` chỉ khi chạy không giúp source file từng bị `javac` từ chối compile. Một flag của JVM không thay đổi biên dịch đã xảy ra trước đó.

### 9.3. Ưu tiên sửa nguồn của hợp đồng khi có quyền

- Nếu `requires` thiếu thật sự, bổ sung vào consumer module descriptor.
- Nếu package là API được phép công khai, export đúng package (tốt hơn qualified export nếu chỉ một consumer cần).
- Nếu framework được phép truy cập sâu, open package **cho module framework cụ thể**.
- Nếu package là implementation private, đổi kiến trúc để consumer không phụ thuộc vào nó.
- Nếu lỗi chỉ do module chưa resolve/class loader không thấy JAR, sửa cách đóng gói/resolution, không thay flags access.
- Nếu platform/library không cho phép sửa descriptor, ghi lại targeted override như một **ngoại lệ được quản lý**, pin version và test hồi quy khi nâng JDK.

Đừng sửa lỗi bằng `open module` toàn thư viện hoặc `ALL-UNNAMED` cho tất cả package chỉ vì chưa xác định caller nào cần quyền. Điều đó tạo coupling và quyền truy cập sâu không cần thiết.

## 10. JPMS trong plugin system, ModuleLayer và nhiều class loaders

Với host có plugin nạp vào layer riêng, ba kiểm tra access có thêm chiều **module identity**:

~~~text
boot layer (host)
       |
       +--- child ModuleLayer (plugin generation V1)
       |         diag.library  (ClassLoader A)
       |         diag.consumer (ClassLoader B)
       |
       +--- child ModuleLayer (plugin generation V2)
                 diag.library  (ClassLoader C)
                 diag.consumer (ClassLoader D)
~~~

Tên module trùng nhau không có nghĩa object `Module`, `Class<?>` hoặc class loader giống nhau giữa V1 và V2. Nếu host kiểm tra `canRead` trên một module lấy từ V1 nhưng class gây lỗi thuộc V2, kết quả chẩn đoán có thể gây hiểu lầm.

### 10.1. Nên ghi dữ kiện gì?

Trong lỗi thực tế, thu thập:

1. `Class<?>` của **consumer thực tế** và **target class thực tế**.
2. `Class.getModule()`, `Module.getName()`, `Module.getLayer()` và `Class.getClassLoader()` tương ứng.
3. Package cụ thể được truy cập, public/private modifier, loại truy cập bytecode hay reflection.
4. `canRead` theo hướng consumer → target, `isExported`/`isOpen` theo hướng provider → caller.
5. Module resolution roots, provider layer configuration, parent layer và nơi đặt plugin JAR.
6. Các runtime access overrides đã áp dụng cho **đúng generation**.
7. Nếu có stack trace, frame nào thực hiện `setAccessible` hoặc invoke thực tế.

### 10.2. ModuleLayer.Controller không phải quyền sửa mọi module

`ModuleLayer.Controller.addReads(source, target)`, `addExports(source, p, target)` và `addOpens(source, p, target)` có giới hạn quan trọng: **source phải nằm trong layer do controller tạo/quản lý**. Controller của child layer không được dùng để sửa một source thuộc `java.base` trong boot layer. Target có thể là module ở layer khác theo hợp đồng API nhưng điều đó không cấp quyền sửa module target.

Controller cũng không thể tạo module/class bị thiếu, không biên dịch lại code và không thay đổi `ModuleDescriptor` tĩnh. Nó bổ sung quan hệ động **không có API thu hồi trực tiếp** tương ứng. Khi xử lý bug access trong plugin, cần cân nhắc security boundary và chỉ để trusted host giữ controller.

### 10.3. Đừng nhầm ClassCastException với lỗi exports

Hai class có cùng binary name nhưng khác defining loader có thể không tương thích kiểu. `ClassCastException` với tên class giống nhau từ hai loaders không thể sửa bằng `--add-exports`/`--add-opens`. Hợp đồng SPI/DTO giữa host và plugin cần được định nghĩa ở API module/classloader chung; đây là vấn đề **runtime type identity**, không phải vấn đề access package.

Tương tự, nếu consumer dùng `ServiceLoader` mà không thấy provider, trước tiên kiểm tra `uses`/`provides` hoặc file `META-INF/services`, module resolution và đúng loader/layer. Chỉ xem exports/opens nếu stack trace thật sự cho thấy provider không thể truy cập một API hoặc framework reflection bị chặn.

## 11. Những ngộ nhận thường dẫn đến sửa sai

**Ngộ nhận 1: “Class public nên module nào cũng truy cập được.”** Không đúng; public modifier không vượt qua ranh giới package exports của named module.

**Ngộ nhận 2: “Đã requires module rồi nên được import mọi package.”** Không đúng; `requires` tạo reads, không export toàn bộ internals của module đích.

**Ngộ nhận 3: “--add-exports sửa mọi lỗi InaccessibleObjectException.”** Không đúng; deep reflection vào private member thường cần `opens`. Ba chế độ ở mục 5 cho kết quả đối chiếu trực tiếp.

**Ngộ nhận 4: “--add-opens không ảnh hưởng isExported.”** Không đúng tại runtime. Open package được xem là exported cho target khi hỏi bằng `Module.isExported`; cần xem descriptor nếu muốn phân biệt khai báo tĩnh.

**Ngộ nhận 5: “Class.forName thành công nghĩa là field private truy cập được.”** Không đúng; class loading và Java access checks là các giai đoạn độc lập.

**Ngộ nhận 6: “Đưa JAR lên module path là module đã được resolve.”** Không nhất thiết; resolved graph phụ thuộc roots, requires và service binding/configuration.

**Ngộ nhận 7: “Thêm --add-opens khi runtime cũng giải quyết lỗi javac.”** Không đúng. Compile-time checker chạy trước và cần descriptor/flags phù hợp riêng.

**Ngộ nhận 8: “Module tên giống nhau nên chắc cùng module.”** Không đúng với các layer/loader khác nhau. Luôn xét đối tượng `Module` thực.

**Ngộ nhận 9: “Đã dùng jdeps thì reflection chắc chắn không lỗi.”** Không đúng. `jdeps` phân tích phụ thuộc tĩnh và không thấy mọi tên class xây dựng động.

**Ngộ nhận 10: “Cứ thêm ALL-UNNAMED là an toàn.”** Không đúng; nó có thể cấp quyền cho nhiều thư viện trên classpath, tăng rủi ro phụ thuộc nội bộ và mở rộng bề mặt reflection.

## 12. Quy trình chẩn đoán tuần tự

~~~text
Có lỗi dùng class/member của một module?
                    |
                    v
Có module/class thực sự ở runtime không?
                    |
       +------------+----------------+
       | không                       | có
       v                             v
sửa path, roots, loader       Là ordinary compiled access?
       |                             |
       |                      +------+------+
       |                      | có          | reflection
       |                      v             v
       |                 C.canRead(L)?    Xác định module gọi
       |                      |           setAccessible/invoke
       |                 thiếu reads?      |
       |                      |             v
       |                      v        Có cần deep access?
       |                 sửa requires        |
       |                      |         +---+---+
       |                      v         | không | có
       |                 L exports p?   v       v
       |                      |       check     L opens p cho
       |                 thiếu export?  public   caller?
       |                      |       visibility |
       |                      v                  v
       |                 export API /         qualified opens
       |                 bỏ dùng internals        |
       +------------------------------+-----------+
                                      |
                                      v
                        Chạy lại đúng build và runtime
                                      |
                                      v
                        Kiểm tra exception/cause còn lại
~~~

Trong quá trình này, mỗi bước phải có **bằng chứng**. Hãy ghi dạng:

~~~text
consumer module = diag.consumer
library module  = diag.library
package         = diag.library.internal
operation       = Field.setAccessible(true)
canRead         = true
isExported      = false
isOpen          = false
exception       = InaccessibleObjectException
minimal trial   = --add-opens diag.library/diag.library.internal=diag.consumer
result          = reflection works
~~~

Với đúng fixture demo ở mục 5, bảng này phân biệt được nguyên nhân opens mà không cần thay thư viện hoặc đưa toàn bộ JVM sang unnamed module.

### 12.1. Khi nào cần sửa ngay, khi nào nên đo thêm?

Nếu lỗi là permission rõ ràng từ `IllegalAccessError`/`InaccessibleObjectException`, việc đo CPU heap thường **không giúp**; cần sửa cấu hình/module graph. Nếu hệ thống chỉ chậm khi startup vì khám phá modules, class loading hoặc reflection, hãy đo bằng JFR/profiler phù hợp và so sánh startup traces trước khi tối ưu. Không suy rằng `--add-opens` hay `--add-exports` là “tối ưu hiệu năng”: đó là **quyền truy cập**, không phải công cụ tăng tốc.

Việc lặp lại `Class.forName`/reflection scans nhiều lần có thể gây overhead ở framework; cache metadata theo **đúng classloader/layer generation** khi phù hợp, đồng thời bảo đảm cache không giữ classloader plugin cũ vĩnh viễn. Không cache một `Class<?>` từ generation V1 rồi dùng nó để kiểm tra permissions của V2.

## 13. Kiểm thử hồi quy và bảo vệ đóng gói

Mỗi module graph/module layer được triển khai nên có tối thiểu:

| Nhóm test | Test case | Điều cần xác nhận |
| --- | --- | --- |
| Module resolution | Bỏ `diag.library` khỏi module path | Build/boot báo thiếu module thay vì lỗi business khó hiểu |
| Reads | Bỏ `requires diag.library` | Compiler báo không đọc module |
| Qualified exports | Code import internal package | Compiler từ chối nếu package không export |
| Public API | `Greeter.sayHello()` | Chạy được với `requires` + `exports` đúng |
| Deep reflection mặc định | Private field trong package chưa open | Bị từ chối như mong đợi |
| Add exports only | `--add-exports` đúng package/target | Public access được nới nhưng private reflection vẫn bị từ chối |
| Add opens only | `--add-opens` đúng package/target | `isOpen` true và private reflection dùng được |
| Compile/runtime mismatch | Compile với export override, chạy thiếu override | Có `IllegalAccessError`; test bảo đảm packaging cuối không lệch |
| Caller identity | Framework module khác host business module | Opens phải nhắm đúng module đang gọi reflection |
| Multi-layer | Hai generations trùng module name khác loader | Debug trên đúng module identity, không lẫn V1/V2 |
| Security | Chỉ đúng package/target được cấp opens | Không vô tình mở rộng bằng `ALL-UNNAMED` |
| Deployment | JVM, module flags, app server, container khác IDE | Ghi actual module graph/flags và chạy smoke test |

Đặc biệt, cần một **test chạy artifact production thật** chứ không chỉ unit test trong IDE. Maven Surefire, Gradle test runner hoặc IDE có thể dùng classpath và tự thêm `--add-opens`; khi chạy ứng dụng dưới module path thật, access checks sẽ khác. Dùng cấu hình test phản ánh launcher của deployment.

### 13.1. Checklist thông tin khi báo lỗi

Một bug report hiệu quả nên đính kèm:

- **JDK/JRE version** của process lỗi và build tool.
- **Tên module chính xác**, package và class gây lỗi, source/target modules.
- Một phần **stack trace nguyên vẹn**, nhất là `module ... does not export/open ... to ...`.
- **`module-info.java`** của producer/consumer, không cần tài liệu khác không liên quan.
- Runtime **module path/classpath**, `--add-modules`/`--add-reads`/`--add-exports`/`--add-opens`.
- Kết quả nhỏ của `--describe-module`, `--show-module-resolution`, `jdeps`/runtime access query.
- Nếu dùng plugin, **ModuleLayer**, ClassLoader, plugin generation và cách host tạo layer.
- Thử nghiệm có kiểm soát một targeted override, kết quả trước/sau.
- Giải pháp dài hạn dự kiến: sửa descriptor, đổi API hay giữ một compatibility flag có lý do.

Không log secrets, stack variables chứa PII hoặc nội dung nhạy cảm khi lấy các bằng chứng trên.

## 14. Tóm tắt bằng một bảng quyết định

| Triệu chứng đã xác minh | Quyền/điều kiện cần xét đầu tiên | Đừng sửa nhầm bằng |
| --- | --- | --- |
| `module not found` | Resolution/module path/roots | `--add-opens` |
| `consumer does not read library` | `requires` hoặc targeted `--add-reads` | Chỉ `--add-exports` |
| `library does not export package` khi import public class | `exports` hoặc targeted `--add-exports` | Chỉ thêm `requires` |
| `setAccessible` báo package không open | `opens` đúng caller hoặc targeted `--add-opens` | Chỉ `--add-exports` |
| Compile thành công, runtime `IllegalAccessError` | So sánh compile flags và runtime graph | Catch exception rồi tiếp tục |
| `Class.forName` không thấy class | Loader/module resolution/artifact | `--add-opens` |
| `ClassCastException` giữa cùng tên class khác loader | Runtime class identity và shared API | `--add-exports` |
| `jdeps` hợp lệ nhưng runtime reflection lỗi | Caller module, package opens và code dùng reflection | Giả định jdeps phủ hết dynamic names |

**Kết luận:** JPMS có nhiều lớp quyền tách biệt, và việc chẩn đoán chỉ đáng tin khi đo trên **đúng Module objects ở đúng runtime**. Hãy kiểm tra *consumer reads provider*, *provider exports package to consumer*, rồi *provider opens package to reflection caller*; đối chiếu nguồn descriptor với runtime overrides, module graph và stack trace. Dùng quyền **nhỏ nhất**, sửa đúng tầng gây lỗi, và kiểm thử lại ở môi trường deploy thật.

### Nguồn tài liệu Java SE 17

- [Java Platform Module System – JLS `7.7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens` và module declarations.
- [Java SE 17 – Class `Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen` và runtime access.
- [Java SE 17 – `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): điều kiện `setAccessible`, readability và reflection across modules.
- [Java SE 17 – `InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): lỗi không thể suppress access checks.
- [Java SE 17 – `ModuleLayer.Controller`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.Controller.html): giới hạn addReads/addExports/addOpens trong child layer.
- [Java 17 `java` launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--module-path`, `--show-module-resolution`, `--add-reads`, `--add-exports`, `--add-opens`.
- [Java 17 `javac`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compile options, module-source-path và diagnostics.
- [Java 17 `jdeps`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích phụ thuộc module và `--check`.
