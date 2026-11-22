# Phân biệt `--add-exports` với `--add-opens` trong Java Module System

## 1. Vì sao cần hai tùy chọn này?

Từ Java 9, Java Platform Module System (JPMS) quản lý cả **phụ thuộc module** và **mức độ hiển thị package**. Một class được khai báo `public` vẫn chưa chắc sử dụng được từ module khác: package của class ấy có thể chưa được `exports`. Mặt khác, một framework dùng Reflection đôi khi cần đọc constructor, field hoặc method không public, mà quyền truy cập thông thường vẫn không cho phép.

Hai tùy chọn dòng lệnh cho phép thêm ngoại lệ vào cấu hình module:

- **`--add-exports`**: xuất một package của module nguồn cho module đích, để module đích có thể sử dụng **kiểu public và thành viên truy cập được theo quy tắc Java**, bao gồm truy cập trực tiếp khi biên dịch và khi chạy. Nó **không tự mở quyền vào private field/method**.
- **`--add-opens`**: mở một package cho module đích thực hiện **deep reflection tại runtime**, ví dụ `getDeclaredField(...)` rồi `trySetAccessible()` / `setAccessible(true)`. Nó **không biến package đó thành package được export cho trình biên dịch**.

Cả hai đều là ngoại lệ đối với tính đóng gói mạnh (*strong encapsulation*). Khi thiết kế một module mình sở hữu, nên cân nhắc khai báo `exports` / `opens` có chủ đích trong `module-info.java` trước khi cần đến cờ dòng lệnh. Khi phải tương thích với thư viện cũ, hãy mở đúng package cho đúng module cần dùng.

## 2. So sánh nhanh

| Tiêu chí | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Mục đích chính | Cho phép sử dụng API `public` của package bị đóng gói | Cho phép Reflection truy cập sâu tới cả thành viên không public |
| Truy cập trực tiếp từ mã nguồn Java bên ngoài module | **Có**, đối với các kiểu/thành viên mà Java visibility cho phép | **Không cấp quyền biên dịch** cho import hoặc gọi trực tiếp |
| Dùng với `javac` | **Có tác dụng** trong biên dịch | Không mở quyền biên dịch; `javac` cảnh báo tùy chọn không có hiệu lực ở compile time |
| Dùng với `java` | **Có tác dụng** tại runtime | **Có tác dụng** tại runtime |
| Cho phép `trySetAccessible()` với private member ở package đích | **Không**, chỉ export chưa đủ | **Có thể**, nếu package đã mở cho module của caller và không có giới hạn khác |
| Giữ các quy tắc `private`, package-private, `protected` khi truy cập trực tiếp | **Có** | **Có**; deep reflection vẫn phải dùng Reflection API |
| Tương ứng trong `module-info.java` | `exports some.package;` hoặc `exports some.package to target.module;` | `opens some.package;` hoặc `opens some.package to target.module;` |

**Không nên rút gọn thành “exports cho public, opens cho private”**: `opens` cũng cho phép Reflection với member public, còn `exports` cho phép những kiểu/thành viên public đã đủ điều kiện truy cập phản chiếu thông thường. Khác biệt thực tế là **quyền truy cập API theo Java language rules** so với **quyền deep reflection**.

## 3. Cú pháp và ý nghĩa từng phần

Cả hai tùy chọn đều nhận mẫu:

~~~text
--add-exports <source-module>/<package>=<target-module>[,<target-module>...]
--add-opens   <source-module>/<package>=<target-module>[,<target-module>...]
~~~

Ví dụ:

~~~bash
java --add-exports=demo.vault/internal.api=demo.client ...
java --add-opens=demo.vault/internal.api=demo.framework ...
java --add-opens=demo.vault/internal.api=ALL-UNNAMED ...
~~~

- `demo.vault` là **module chứa package** cần xuất/mở.
- `internal.api` là **tên package đầy đủ**, không phải tên class hay method.
- `demo.client` hoặc `demo.framework` là **module được cấp quyền**.
- `ALL-UNNAMED` là mục tiêu đặc biệt dành cho **tất cả unnamed modules** (thông thường là mã nạp từ classpath, kể cả các thư viện JAR trên classpath). Nó có phạm vi rộng hơn một named module cụ thể.
- Có thể chỉ định nhiều named module ở vế phải, cách nhau bằng dấu phẩy.
- Dạng `--add-opens=module/package=target` và `--add-opens module/package=target` đều được Java launcher hỗ trợ; dạng có `=` sau tên tùy chọn thuận tiện khi cấu hình JVM arguments trong một số công cụ.

Hai cờ này **không tự thêm quan hệ module readability**. Với named module muốn sử dụng dependency, vẫn cần `requires demo.vault;` trong `module-info.java` hoặc cơ chế thích hợp như `--add-reads`. Với ứng dụng trên classpath, nếu `demo.vault` nằm trên module path nhưng chưa được giải quyết vào module graph, có thể cần `--add-modules demo.vault`.

Lưu ý: tên target trong lệnh là **module của mã tiêu thụ API hoặc mã thực hiện Reflection**, không nhất thiết là module chứa class mà ứng dụng đang xử lý dữ liệu.

## 4. Ví dụ Java 17+ có thể biên dịch và chạy

Ta sẽ tự tạo một named module `demo.vault` chứa public class nhưng **không export package**. Hai chương trình ở classpath sẽ lần lượt thử **gọi trực tiếp public method** và **Reflection vào private method**. Cách này cho phép quan sát chính xác tác dụng từng flag, không cần phụ thuộc vào lớp nội bộ không ổn định của JDK.

### 4.1. Cấu trúc thư mục

~~~text
project/
├── src/
│   └── demo.vault/
│       ├── module-info.java
│       └── internal/
│           └── api/
│               └── PublicTool.java
├── client-src/
│   ├── DirectMain.java
│   └── ReflectMain.java
├── mods/                 (sinh khi biên dịch)
└── out/                  (sinh khi biên dịch)
~~~

File `src/demo.vault/module-info.java`:

~~~java
module demo.vault {
    // Không có exports hay opens cho internal.api.
}
~~~

File `src/demo.vault/internal/api/PublicTool.java`:

~~~java
package internal.api;

public final class PublicTool {
    private PublicTool() { }

    public static String greet() {
        return "hello";
    }

    private static String secret() {
        return "hidden";
    }
}
~~~

File `client-src/DirectMain.java`:

~~~java
import internal.api.PublicTool;

public class DirectMain {
    public static void main(String[] args) {
        System.out.println("direct: " + PublicTool.greet());
    }
}
~~~

File `client-src/ReflectMain.java`:

~~~java
import java.lang.reflect.Method;

public class ReflectMain {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("internal.api.PublicTool");
        Method method = type.getDeclaredMethod("secret");

        boolean opened = method.trySetAccessible();
        System.out.println("private opened: " + opened);

        if (opened) {
            System.out.println("reflect: " + method.invoke(null));
        }
    }
}
~~~

`ReflectMain` không import `PublicTool`: nó chỉ biết tên lớp dạng chuỗi. Phương thức `secret` là `private static`, nên `method.invoke(null)` là đúng kiểu receiver sau khi được mở quyền. `trySetAccessible()` trả `false` khi package chưa được mở cho unnamed module của caller.

### 4.2. Tạo thư mục đầu ra và biên dịch

Trong thư mục `project`, tạo trước các thư mục đầu ra. Ví dụ Bash (Linux/macOS):

~~~bash
mkdir -p mods/demo.vault out
~~~

Trong PowerShell (Windows), có thể dùng:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/demo.vault,out
~~~

Các lệnh `javac` tiếp theo áp dụng như nhau trên cả hai môi trường:

~~~bash
javac -d mods/demo.vault src/demo.vault/module-info.java src/demo.vault/internal/api/PublicTool.java

javac --module-path mods --add-modules demo.vault --add-exports demo.vault/internal.api=ALL-UNNAMED -d out client-src/DirectMain.java client-src/ReflectMain.java
~~~

Ở lần biên dịch thứ hai, `DirectMain` **import trực tiếp** class từ package chưa xuất. Vì vậy phải cung cấp `--add-exports` cho **`javac`**. Nếu bỏ cờ này, trình biên dịch sẽ báo package `internal.api` không hiển thị từ module `demo.vault`.

`--add-modules demo.vault` đảm bảo named module trên module path được giải quyết. Cờ `--add-exports` ở đây chỉ cấp quyền cho unnamed modules, đúng với vị trí của `DirectMain` trên classpath.

### 4.3. Chạy ví dụ truy cập trực tiếp: cần `--add-exports` lúc chạy

~~~bash
java --module-path mods --add-modules demo.vault --add-exports demo.vault/internal.api=ALL-UNNAMED -cp out DirectMain
~~~

Stdout:

~~~text
direct: hello
~~~

**Vì sao vẫn cần cờ tại runtime?** Cờ `javac --add-exports` chỉ ảnh hưởng quá trình biên dịch. Nó không tự ghi một quyền export vĩnh viễn vào `demo.vault`. Nếu chạy chương trình đã biên dịch nhưng bỏ cờ runtime, việc liên kết/truy cập class không được export có thể dẫn đến `IllegalAccessError`.

Dùng **chỉ `--add-opens` ở `javac` không giải quyết lỗi import**, vì mở package để Reflection tại runtime không phải xuất package cho mã nguồn compile time.

### 4.4. Chạy ví dụ Reflection: cần `--add-opens`

Chạy trước **không cấp quyền mở package**:

~~~bash
java --module-path mods --add-modules demo.vault -cp out ReflectMain
~~~

Stdout:

~~~text
private opened: false
~~~

Reflection vẫn tìm được metadata phương thức qua `getDeclaredMethod("secret")`, nhưng không được bật quyền gọi method `private` trong package chưa mở cho caller.

Thêm **`--add-opens`**:

~~~bash
java --module-path mods --add-modules demo.vault --add-opens demo.vault/internal.api=ALL-UNNAMED -cp out ReflectMain
~~~

Stdout:

~~~text
private opened: true
reflect: hidden
~~~

Bây giờ package `internal.api` được mở cho unnamed module; `trySetAccessible()` có thể bật cờ bỏ qua kiểm tra quyền và `Method.invoke` gọi được phương thức `private`. **Không cần `--add-exports`** cho đoạn `ReflectMain` này, bởi nó không import hay tham chiếu tĩnh đến `PublicTool`.

### 4.5. Kết quả tổng hợp

| Tác vụ | Chỉ `--add-exports` | Chỉ `--add-opens` |
| --- | --- | --- |
| Biên dịch `DirectMain` có `import internal.api.PublicTool` | Có, nếu module được resolve và quyền đọc phù hợp | Không |
| Chạy `DirectMain` đã được biên dịch hợp lệ | Đủ quyền truy cập public API ở runtime | Không phải cấu hình cho quyền biên dịch ban đầu; đừng dùng thay `--add-exports` |
| Bật `trySetAccessible()` cho `private secret()` từ `ReflectMain` | Không, nếu không có quyền mở khác | Có trong ví dụ này |
| Truy cập phương thức `public` bằng Reflection thông thường | Có thể, theo quy tắc truy cập Java | Có thể, theo cơ chế reflective access |

Ví dụ được kiểm tra với OpenJDK 21 (mã và tùy chọn tương thích JDK 17): `direct: hello`; `private opened: false`; `private opened: true` rồi `reflect: hidden`.

## 5. So sánh với `exports` và `opens` trong `module-info.java`

Một tác giả module có thể khai báo quyền một cách chủ đích:

~~~java
module demo.library {
    exports demo.library.api;
    exports demo.library.spi to demo.plugin;

    opens demo.library.model to demo.framework;
}
~~~

Đây là **minh họa cấu hình**; muốn biên dịch phải có các package tương ứng và target modules phù hợp.

- `exports demo.library.api;`: mọi module có quyền đọc module này được dùng public API của package.
- `exports ... to demo.plugin;`: chỉ `demo.plugin` có quyền export được chỉ định.
- `opens ... to demo.framework;`: mở package để framework dùng Reflection vào các thành viên, kể cả non-public, ở runtime. Nó không cho phép code của framework import trực tiếp những kiểu trước đó chưa được export lúc biên dịch.
- Có thể **vừa `exports` vừa `opens` một package** khi cần cả API công khai lẫn deep reflection.
- `open module demo.library { ... }` mở mọi package trong module đó cho Reflection. Cách này rộng hơn mở từng package; một `open module` không khai báo thêm các `opens` riêng.

Cờ dòng lệnh thêm các cạnh export/open tương ứng **cho tiến trình đang biên dịch hoặc chạy**, dù module gốc không khai báo như vậy. Chúng không sửa file `module-info.java` đã phát hành.

## 6. Chẩn đoán lỗi và chọn đúng cờ

### Trường hợp A: lỗi import ở compile time

Thông báo thường có ý như:

~~~text
package ... is not visible
(package ... is declared in module ..., which does not export it)
~~~

Nếu mã **thực sự phải tham chiếu trực tiếp public API** ở package ấy, xét `--add-exports` cho `javac` và lệnh chạy. Kiểm tra trước xem có API public được hỗ trợ ở package khác không. `--add-opens` không giúp import compile thành công.

### Trường hợp B: `IllegalAccessError` tại runtime

Thường xảy ra khi mã đã compile với quyền truy cập nhưng JVM chạy không có cùng quyền export, hoặc môi trường module khác bản build. Đối chiếu cấu hình `--add-exports` giữa **compile** và **runtime** và kiểm tra module graph. Đừng vội thêm `--add-opens` chỉ vì thấy chữ “Access”.

### Trường hợp C: `InaccessibleObjectException` hoặc `trySetAccessible() == false`

Nếu stack trace/điều kiện báo package chưa được **opened** cho module gọi Reflection, cờ phù hợp thường là:

~~~bash
java --add-opens=source.module/source.package=target.module ...
~~~

Với một ứng dụng legacy chạy ở classpath, target có thể là `ALL-UNNAMED`. Dù đã mở package, vẫn phải tuân thủ các ràng buộc API khác: kiểu receiver hợp lệ, hành vi `final`, khả năng sửa field và chính sách môi trường.

### Trường hợp D: không tìm được class/module

`ClassNotFoundException` hoặc thông báo không tìm thấy module **không tự động được giải quyết** bằng `--add-exports` / `--add-opens`. Kiểm tra đường dẫn `--module-path`, `-cp`, tên module và việc resolve module (ví dụ `--add-modules`) trước. Nếu named module cần đọc một module khác mà chưa có quan hệ readability, xét `requires` hoặc `--add-reads` thích hợp.

## 7. Quy tắc dùng an toàn, bền vững

1. **Ưu tiên API được hỗ trợ.** Package nội bộ của JDK/thư viện có thể thay đổi giữa các bản nâng cấp; có thể thay code Reflection bằng API chính thức để khỏi duy trì cờ.
2. **Mở quyền tối thiểu.** Chọn một package và target named module cụ thể khi có thể. `ALL-UNNAMED` cấp quyền rộng cho mọi mã trên classpath.
3. **Đặt cờ ở đúng JVM.** Với `java -jar app.jar`, JVM argument cần xuất hiện **trước `-jar`**. Test runner, IDE, Gradle/Maven test fork hoặc ứng dụng trong container có JVM riêng thì cần cấu hình vào tiến trình Java thực sự chạy code.
4. **Phân biệt compile và run.** `--add-exports` có thể cần ở cả hai; `--add-opens` chỉ phục vụ runtime Reflection. Đặt `--add-opens` vào `javac` không tạo quyền compile time.
5. **Không biến cờ thành hợp đồng API.** Có quyền Reflection không đảm bảo thao tác sẽ thành công: còn kiểu đối tượng đích, `final` field, kiểu dữ liệu, exception từ method được gọi và các giới hạn khác.
6. **Kiểm tra phiên bản Java.** Ở JDK 17, cơ chế đóng gói mạnh của JDK được áp dụng mặc định; tùy chọn legacy `--illegal-access` không còn tác dụng mở quyền như ở các phiên bản cũ.

## 8. Tự kiểm tra

**Câu 1.** Một package không export chứa `public class InternalApi`; client dùng `import` để gọi public method. Cần loại quyền nào?  
**Đáp án:** `--add-exports` hoặc một export phù hợp trong `module-info.java`, đồng thời đáp ứng readability. Đối với lựa chọn cờ dòng lệnh, cấp quyền ở cả bước cần biên dịch và bước chạy.

**Câu 2.** Thư viện dùng `getDeclaredField("secret")` và `trySetAccessible()`, nhưng package trong named module chưa được mở. Cờ nào đúng trọng tâm?  
**Đáp án:** `--add-opens` từ module chứa package sang module thực hiện Reflection; `--add-exports` không đủ để mở private field.

**Câu 3.** `--add-opens` có làm `import internal.api.PublicTool` compile được không?  
**Đáp án:** Không. `--add-opens` không cấp quyền truy cập trực tiếp lúc compile.

**Câu 4.** `ALL-UNNAMED` có nghĩa là cấp quyền cho một JAR duy nhất?  
**Đáp án:** Không. Nó bao gồm mọi unnamed module, thường là các thư viện/app trên classpath.

**Câu 5.** Dùng `--add-opens` rồi mọi thao tác ghi `final` field đều hợp lệ?  
**Đáp án:** Không. Mở package để Reflection không xóa các giới hạn về thao tác trên field và những quy tắc API khác.

**Ghi nhớ:** cần **gọi trực tiếp public API bị che bởi ranh giới module** → xét `--add-exports`; cần **Reflection sâu vào thành viên không public** → xét `--add-opens`. Luôn xác định đúng module nguồn, package, module đích, giai đoạn compile/run và quan hệ module readability.

### Tài liệu chính thức

- [Dev.java — Circumventing Strong Encapsulation with `--add-exports` and `--add-opens`](https://dev.java/learn/organizing/modules/add-exports-opens/)
- [Dev.java — Reflective Access with Open Modules and Open Packages](https://dev.java/learn/modules/opening-for-reflection/)
- [Oracle JDK 17 Migration Guide — Strong Encapsulation and Module Options](https://docs.oracle.com/en/java/javase/17/migrate/)
- [Java Language Specification §7.7.2 — Exported and Opened Packages](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2)
