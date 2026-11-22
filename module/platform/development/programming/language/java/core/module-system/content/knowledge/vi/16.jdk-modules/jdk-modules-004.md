# JDK internal module không phải API công khai

Từ Java 9, Java Platform Module System (JPMS) tổ chức JDK thành nhiều named module. Một số module cung cấp API tiêu chuẩn Java SE, một số là API hoặc công cụ riêng của JDK, và nhiều module chứa các package **nội bộ** chỉ phục vụ implementation của JVM hoặc thư viện nền tảng.

Điểm quan trọng nhất: **một class có mặt trong JDK không có nghĩa đó là API công khai được hỗ trợ để ứng dụng phụ thuộc trực tiếp**. Tên module hay package có thể được tìm thấy trong runtime image, nhưng module boundary vẫn quyết định package có được export/open cho code khác hay không. Ngay cả khi có thể vượt ranh giới bằng JVM flag, API nội bộ cũng không tự trở thành hợp đồng tương thích ổn định.

Bài này giải thích cách nhận biết API nội bộ, phân biệt module `java.*` và `jdk.*`, các lỗi compile/runtime khi truy cập, ý nghĩa của `--add-exports` và `--add-opens`, cùng quy trình chuyển sang API được hỗ trợ.

## 1. Ba lớp API cần phân biệt

Trong JDK hiện đại, nên phân biệt ít nhất ba nhóm:

| Nhóm | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| Java SE API công khai | `java.lang`, `java.util`, `java.net.http`, `java.sql` | API chuẩn có hợp đồng và tài liệu Java SE tương ứng |
| JDK-specific API được công bố | Một số API trong `jdk.jfr`, `com.sun.source.*` của `jdk.compiler` | Chỉ dùng khi chủ động phụ thuộc vào JDK và có tài liệu hỗ trợ phù hợp |
| JDK internal implementation API | `jdk.internal.*`, nhiều package `com.sun.tools.javac.*` hoặc `com.sun.org.apache.*.internal` | Không xem là API ứng dụng ổn định; tránh import và reflection trực tiếp |

**Không thể đánh giá một package chỉ dựa vào prefix.** Không phải mọi class có tiền tố `com.sun` đều nội bộ và không phải mọi API thuộc module `jdk.*` đều bị cấm sử dụng. Muốn xác định ranh giới thật, hãy xem module descriptor, tài liệu JDK và chính sách hỗ trợ của API đó.

Ví dụ:

- `java.base` chứa cả `java.util` — API công khai — và `jdk.internal.misc` — implementation detail.
- `jdk.compiler` export các package của Compiler Tree API như `com.sun.source.tree`, nhưng không export mọi package implementation của compiler.
- `jdk.unsupported` chứa một số API được duy trì vì tương thích, như `sun.misc.Unsafe`; chữ “unsupported” là cảnh báo không nên coi chúng là nền tảng thiết kế mới.

Tên của module và mức độ hỗ trợ của package là **hai câu hỏi riêng**.

## 2. Module có mặt không đồng nghĩa package được công khai

Trong JPMS, một named module có thể:

- Chứa nhiều package.
- Export một số package ra ngoài.
- Chỉ export một số package cho những named module được chỉ định.
- Open package cho reflection sâu.
- Giữ những package còn lại bị encapsulate.

Ví dụ khái niệm:

~~~java
module com.acme.engine {
    exports com.acme.engine.api;
    exports com.acme.engine.spi to com.acme.plugins;
    opens com.acme.engine.persistence to com.acme.orm;
}
~~~

Một consumer đọc `com.acme.engine` không mặc nhiên được import class trong tất cả các package của module.

Tương tự, `java.base` là module được mọi named module đọc ngầm, nhưng điều đó **không có nghĩa mọi package trong `java.base` đều được export**.

Quan hệ truy cập có thể tóm tắt:

~~~text
Module A đọc Module B?
         │
         ▼
B có exports package P cho A không?
         │
         ├── Có  → A có thể dùng public type/member trong P,
         │         vẫn tuân thủ Java access modifiers
         │
         └── Không → Java source ở A không được import P
                     như API bình thường

Deep reflection?
         │
         ▼
B có opens package P cho module caller không?
         │
         ├── Có  → Reflection có thể yêu cầu bỏ qua
         │         access checks trong giới hạn cho phép
         │
         └── Không → setAccessible có thể thất bại
~~~

`requires`, `exports` và `opens` giải quyết các vấn đề khác nhau. Thêm `requires java.base` không giúp truy cập package nội bộ chưa được export.

## 3. Xem module của JDK bằng Java launcher

Liệt kê các module mà runtime image hiện tại công bố:

~~~bash
java --list-modules
~~~

Ví dụ output rút gọn:

~~~text
java.base@21.0.2
java.logging@21.0.2
java.sql@21.0.2
jdk.compiler@21.0.2
jdk.jfr@21.0.2
jdk.unsupported@21.0.2
...
~~~

Phiên bản thực tế và tập module phụ thuộc vào JDK hoặc runtime image đang sử dụng.

Lệnh này cho thấy module có thể quan sát được, **không xác nhận mọi package trong module là public API**. Một runtime image tùy chỉnh từ `jlink` còn có thể không chứa một số module vốn có trong JDK đầy đủ.

Mô tả module cụ thể:

~~~bash
java --describe-module java.base
java --describe-module jdk.compiler
java --describe-module jdk.unsupported
~~~

Cần phân biệt các dòng trong descriptor:

- `exports package.name`: package được export không giới hạn cho các module có readability phù hợp.
- `exports package.name to module.one,module.two`: qualified export chỉ cho các module được nêu.
- `opens package.name`: package được mở cho deep reflection.
- `contains package.name`: package thuộc module, **không phải một lời hứa export**.
- `requires other.module`: module dependency.
- `uses`/`provides`: service consumption/provider metadata.

Khi thấy `contains jdk.internal.misc`, đừng suy ra code ứng dụng được phép import `jdk.internal.misc`. `contains` chỉ phản ánh quyền sở hữu package của module.

## 4. Ví dụ compile-time: package nội bộ không visible

Giả sử ứng dụng modular cố dùng API nội bộ:

~~~java
// src/com.acme.app/module-info.java
module com.acme.app {
}
~~~

~~~java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import jdk.internal.misc.Unsafe;

public class Main {
    public static void main(String[] args) {
        System.out.println(Unsafe.class.getName());
    }
}
~~~

Biên dịch:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.acme.app
~~~

Trên JDK có strong encapsulation, compiler có thể báo lỗi tương tự:

~~~text
package jdk.internal.misc is not visible
(package jdk.internal.misc is declared in module java.base,
 which does not export it to module com.acme.app)
~~~

Lỗi này có ý nghĩa cụ thể:

1. Class/package có thể **tồn tại** trong JDK.
2. Module `java.base` sở hữu package đó.
3. Package **không được export** cho `com.acme.app`.
4. Code không thể import nó như API bình thường.

Không phải lỗi “thiếu dependency Maven”, cũng không phải lỗi chưa khai báo `requires java.base`. Mọi named module đã đọc `java.base` ngầm; thứ bị chặn là **package export**.

Khi một dependency không phải API công khai, cách sửa ưu tiên là đổi sang API được hỗ trợ. Việc thêm flags vượt ranh giới chỉ nên dùng để chẩn đoán hoặc duy trì tương thích trong giai đoạn chuyển đổi.

## 5. Khi chạy trên classpath vẫn có ranh giới JPMS

Một ứng dụng chưa có `module-info.java` thường chạy trên classpath:

~~~bash
java -cp app.jar com.acme.app.Main
~~~

Code trên classpath thuộc **unnamed module** của class loader tương ứng. Unnamed module có khả năng đọc các module được JPMS cho phép theo quy tắc của nó, nhưng **không được tự bỏ qua package encapsulation**.

Vì vậy, việc chuyển ứng dụng từ module path về classpath không bảo đảm các lệnh import `jdk.internal.*` hoặc reflection vào private JDK state hoạt động.

Trong các thông báo lỗi, bạn có thể thấy:

~~~text
module java.base does not export jdk.internal.misc to unnamed module
~~~

hoặc:

~~~text
module java.base does not "opens java.lang" to unnamed module
~~~

`unnamed module` trong thông báo chỉ nơi code đang chạy; source module vẫn là named module của JDK.

## 6. Phân biệt truy cập public API và deep reflection

Hai nhóm lỗi thường bị nhầm:

### 6.1. Public class nhưng package không export

Ví dụ code import `jdk.internal.misc.Unsafe`. Nếu package chưa được export, compiler hoặc JVM có thể từ chối truy cập class dù class có access modifier `public`.

Đây là vấn đề **exports**, không nhất thiết liên quan tới reflection.

### 6.2. Class hợp lệ nhưng private member không được mở

Ví dụ reflection vào một field của `java.lang.String`:

~~~java
import java.lang.reflect.Field;

public class ReflectString {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
~~~

Trên JDK hiện đại, `setAccessible(true)` có thể ném:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... java.lang.String.value accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

Ở đây `java.lang` là package được export cho API thông thường, nhưng **không có nghĩa private member trong package đã được mở cho deep reflection**.

Hãy phân biệt `exports` với `opens`. Sửa sai loại quyền có thể khiến người bảo trì thêm nhiều JVM flags mà ứng dụng vẫn không chạy.

## 7. --add-exports: nới quyền import public API tạm thời

JPMS cung cấp tùy chọn:

~~~text
--add-exports SOURCE_MODULE/PACKAGE=TARGET_MODULE
~~~

Ví dụ cấp quyền cho module `com.acme.app` sử dụng public type từ package chưa được export:

~~~bash
javac \
  --add-exports java.base/jdk.internal.misc=com.acme.app \
  --module-source-path src \
  -d out \
  -m com.acme.app
~~~

Nếu ứng dụng vẫn phụ thuộc vào truy cập đó lúc runtime, có thể cần flag tương ứng:

~~~bash
java \
  --add-exports java.base/jdk.internal.misc=com.acme.app \
  --module-path out \
  --module com.acme.app/com.acme.app.Main
~~~

Nếu caller nằm trên classpath, đích có thể là token launcher `ALL-UNNAMED`:

~~~bash
java \
  --add-exports java.base/jdk.internal.misc=ALL-UNNAMED \
  -cp app.jar \
  com.acme.app.Main
~~~

Tuy nhiên:

- `--add-exports` **không đổi** access modifier `private` thành `public`.
- Nó **không biến API nội bộ thành API được JDK cam kết hỗ trợ**.
- Nó có thể cần lặp lại trong cấu hình compile, test và production.
- Việc internal class hoặc method thay đổi ở JDK tiếp theo vẫn có thể làm code lỗi.

Đây là **biện pháp migration có kiểm soát**, không phải kiến trúc khuyến nghị.

## 8. --add-opens: nới quyền deep reflection tạm thời

Khi framework reflection vào private member, flag tương ứng là:

~~~text
--add-opens SOURCE_MODULE/PACKAGE=TARGET_MODULE
~~~

Ví dụ mở `java.lang` của `java.base` cho code chạy trên classpath:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -cp app.jar \
  com.acme.app.Main
~~~

Với named module framework, có thể cấp cho đúng module:

~~~bash
java \
  --add-opens java.base/java.lang=com.acme.framework \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Quyền được cấp cho **module thực sự thực hiện reflection**, không nhất thiết là module chứa `main` hoặc module gọi một framework API ở tầng cao.

Bảng so sánh:

| Cần làm gì? | Cơ chế thích hợp | Giới hạn |
| --- | --- | --- |
| Dùng public type/member của package chưa export | `--add-exports` | Không cho phép tự do đọc private field |
| Dùng `setAccessible` hoặc private lookup vào package chưa open | `--add-opens` | Không tự tạo compile-time export |
| Consumer đọc named module thông thường | `requires` hoặc quan hệ readability đúng | Không bypass package encapsulation |
| Công bố API từ module do mình quản lý | `exports` trong `module-info.java` | Chỉ API được export |
| Cho một framework reflection vào package do mình quản lý | `opens package to framework.module` | Quyền chỉ dành cho module đích |

Nếu sở hữu module của chính ứng dụng, ưu tiên sửa thiết kế bằng `exports` hoặc qualified `opens` có phạm vi hẹp, thay vì dựa vào JVM flags trải khắp môi trường.

## 9. Các mốc strong encapsulation khi nâng cấp JDK

Từ Java 9, ranh giới module đã thay đổi cách các ứng dụng cũ sử dụng JDK internals.

| Mốc | Ý nghĩa đối với migration |
| --- | --- |
| Trước Java 9 | Một số ứng dụng truy cập trực tiếp internal JDK classes dù API không được hỗ trợ |
| Java 9 | JPMS ra đời; có giai đoạn nới quyền đối với một số reflective access cũ để hỗ trợ migration |
| Java 11–15 | Một số truy cập vẫn chạy nhưng phát cảnh báo `illegal reflective access` |
| Java 16 | Strong encapsulation trở thành mặc định theo JEP 396; vẫn còn cơ chế opt-out tạm trong giai đoạn chuyển đổi |
| Java 17 trở đi | JEP 403 siết strong encapsulation; `--illegal-access` không còn cấp lại quyền nới lỏng như trước |

Cần nhớ:

- Cảnh báo trên một bản JDK cũ **không bảo đảm** code sẽ chạy trên JDK mới.
- `--illegal-access=permit` là lựa chọn migration cũ, không phải giải pháp bền vững trên Java 17+.
- `--add-exports` và `--add-opens` là cơ chế cụ thể hơn nhưng không bảo đảm internal API vẫn tồn tại trong tương lai.
- Một số API đặc biệt trong `jdk.unsupported` được giữ vì tương thích; không nên suy rộng ngoại lệ này cho toàn bộ `jdk.internal.*`.

Khi xử lý migration, hãy kiểm tra đúng Java version của compiler, unit test, integration test và production runtime.

## 10. jdk.compiler: ví dụ phân biệt API được công bố với implementation

`jdk.compiler` là một module của JDK. Trong module này có các API được export, chẳng hạn package thuộc Compiler Tree API:

~~~java
module com.acme.analyzer {
    requires jdk.compiler;
}
~~~

Code ứng dụng có thể import một type thuộc package được export:

~~~java
import com.sun.source.tree.Tree;
~~~

Trong khi đó, các package implementation như `com.sun.tools.javac.util` không mặc nhiên được export làm public API cho consumer.

Ví dụ import:

~~~java
import com.sun.tools.javac.util.Context;
~~~

có thể bị compiler từ chối vì module `jdk.compiler` không export package đó cho module của ứng dụng.

Hai package đều có prefix `com.sun`, nhưng mức độ hỗ trợ và quyền export khác nhau. Câu hỏi đúng là **descriptor có export package đó cho mình hay không, và tài liệu JDK có công bố API đó để dùng hay không?**

Ngoài ra, `jdk.compiler` là API JDK-specific chứ không phải mọi runtime image tùy chỉnh đều có nó. Nếu ứng dụng cần một API thuộc `jdk.compiler`, phải bảo đảm module đó hiện diện trong môi trường chạy.

## 11. jdk.unsupported và sun.misc.Unsafe: ngoại lệ không phải tiền lệ

Một số phần mềm hiệu năng cao hoặc framework cũ từng phụ thuộc vào `sun.misc.Unsafe`. Để hỗ trợ khả năng tương thích, JDK có module `jdk.unsupported`, với package `sun.misc` được công bố theo descriptor của module.

Named module có thể cần khai báo:

~~~java
module com.acme.legacy {
    requires jdk.unsupported;
}
~~~

Nhưng điều này không làm `sun.misc.Unsafe` trở thành API Java SE được hỗ trợ ổn định. Những phương thức liên quan tới thao tác bộ nhớ và trạng thái đối tượng có thể thay đổi hoặc bị hạn chế theo thời gian.

Phân biệt:

- `sun.misc.Unsafe` thuộc module `jdk.unsupported`, được giữ theo chính sách tương thích cụ thể.
- `jdk.internal.misc.Unsafe` thuộc `java.base` và package của nó bị encapsulate.
- Hai class không phải lời hứa rằng mọi chức năng của nhau có thể thay thế hoặc sẽ tồn tại lâu dài.

Khi thấy `Unsafe` trong dependency, nên tìm mục đích sử dụng thật sự trước khi lựa chọn cách thay thế.

## 12. Phát hiện dependency vào internal JDK APIs bằng jdeps

Công cụ `jdeps` của JDK có thể phân tích class/JAR để tìm tham chiếu tĩnh tới JDK internals.

Ví dụ:

~~~bash
jdeps --jdk-internals libs/legacy-library.jar
~~~

Với application JAR:

~~~bash
jdeps --jdk-internals app.jar
~~~

Nếu có multi-release JAR, xác định release cần phân tích:

~~~bash
jdeps --multi-release 17 --jdk-internals libs/legacy-library.jar
~~~

Output có thể nêu class gọi tới API nội bộ, module/package chứa API đó và đôi khi gợi ý replacement phù hợp.

Quy trình sử dụng:

1. Quét application artifact.
2. Quét dependency quan trọng hoặc dependency bị nêu trong stack trace.
3. Ghi lại internal API, class gọi nó và artifact/version sở hữu class.
4. Phân loại sử dụng trực tiếp trong source với sử dụng gián tiếp qua library.
5. Đề xuất API công khai thay thế hoặc phiên bản dependency mới tương thích JDK mục tiêu.

Giới hạn của `jdeps`:

- Phân tích chủ yếu dựa trên thông tin class file.
- `Class.forName("...")`, reflection dựa trên chuỗi, dynamic proxy hoặc bytecode sinh động có thể không được phát hiện đầy đủ.
- Không có cảnh báo từ `jdeps --jdk-internals` **không chứng minh** chương trình hoàn toàn không sử dụng internals.

Cần kết hợp kiểm thử trên JDK mục tiêu, đặc biệt với serialization, ORM, instrumentation và các thư viện tạo bytecode lúc runtime.

## 13. Không nhầm JDK internal API với API bị deprecated hoặc module bị loại bỏ

Ba tình huống cần phân loại riêng:

**JDK internal API:** package/class là implementation detail, có thể bị encapsulate. Ví dụ một class trong `jdk.internal.*`.

**Deprecated public API:** API công khai nhưng có cảnh báo nên chuyển sang API mới. Một public API bị deprecated vẫn có thể được export và cho phép sử dụng trong giai đoạn hiện tại. Dùng `jdeprscan` hoặc compiler warning để đánh giá.

**Module hoặc API đã được loại bỏ:** một số thành phần từng thuộc JDK đã không còn trong phiên bản sau. Lỗi `module not found` hoặc `ClassNotFoundException` có thể đến từ việc module không còn hiện diện, chứ không phải bị encapsulate.

Đừng chữa mọi trường hợp bằng `--add-opens`:

- Nếu module không tồn tại, mở package không tạo ra module bị thiếu.
- Nếu class đã bị loại bỏ, `--add-exports` không tái tạo class.
- Nếu API public chỉ bị deprecated, cần đọc lộ trình replacement thay vì mặc định nó là JDK internal.

Phân loại đúng giúp tránh JVM flags vô nghĩa và giảm thời gian chẩn đoán.

## 14. Hướng thay thế các internal APIs thường gặp

Không có một replacement duy nhất áp dụng cho mọi JDK internal API. Hãy xác định **tính năng ứng dụng thực sự cần**.

| Nhu cầu cũ | Hướng thay thế hoặc kiểm tra |
| --- | --- |
| Mã hóa/giải mã Base64 qua class cũ của JDK | `java.util.Base64` |
| Truy cập field với memory semantics đặc biệt bằng `Unsafe` | `VarHandle`, `MethodHandles`, `AtomicInteger` và các API concurrency công khai |
| Quản lý cleanup tài nguyên qua implementation detail | `java.lang.ref.Cleaner`, `AutoCloseable` hoặc API tài nguyên phù hợp |
| XML parsing qua `com.sun.org.apache.*.internal` | JAXP, DOM, SAX hoặc thư viện XML có public API |
| Thao tác khóa, chữ ký, chứng chỉ bằng class an ninh nội bộ | `java.security`, `java.security.cert` hoặc thư viện được hỗ trợ |
| Khai thác chi tiết implementation của compiler | API compiler/tree được export và có tài liệu, hoặc công cụ/compiler plugin chính thức |
| Reflection để đọc private field của JDK class | Public accessor, factory, interface hoặc mô hình dữ liệu thay thế |

Ví dụ dùng API Base64 chuẩn:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class EncodingExample {
    public static void main(String[] args) {
        byte[] raw = "hello".getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder().encodeToString(raw);
        byte[] decoded = Base64.getDecoder().decode(encoded);

        System.out.println(encoded);
        System.out.println(new String(decoded, StandardCharsets.UTF_8));
    }
}
~~~

Output:

~~~text
aGVsbG8=
hello
~~~

Ví dụ không cần import class nội bộ hay nới module boundary. Đây là hướng ưu tiên khi JDK đã có public API đáp ứng nhu cầu.

### VarHandle thay cho một số mục đích dùng Unsafe

Nếu ứng dụng cần thao tác nguyên tử với field do chính mình sở hữu, có thể dùng public `VarHandle` API:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    public int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
~~~

Đoạn code sử dụng API chuẩn cho atomic field operation và không cần truy cập `sun.misc.Unsafe`.

Tuy nhiên, `VarHandle` không có nghĩa là có thể thay toàn bộ các tính năng của `Unsafe` bằng một API tương đương 1:1. Các thao tác native memory, object layout hoặc low-level runtime phải được xem xét riêng và chọn public API phù hợp với phiên bản JDK mục tiêu.

## 15. Khi lỗi đến từ thư viện bên thứ ba

Ứng dụng có thể không trực tiếp import internal class nhưng vẫn gặp lỗi do dependency thực hiện reflection hoặc truy cập nội bộ.

Một stack trace giả định:

~~~text
java.lang.reflect.InaccessibleObjectException: ...
    at third.party.mapper.InternalAccessor.open(...)
    at third.party.mapper.Mapper.read(...)
    at com.acme.app.Main.main(...)
~~~

Ở đây, code trong thư viện mapper mới là nơi yêu cầu deep reflection.

Các bước nên làm:

1. Xác định artifact thực tế chứa class `third.party.mapper.InternalAccessor`.
2. Ghi lại version dependency đang được chạy, không chỉ version trong khai báo build.
3. Kiểm tra thư viện có bản phát hành hỗ trợ JDK mục tiêu không.
4. Ưu tiên nâng cấp thư viện hoặc đổi cách cấu hình framework.
5. Chạy test trên đúng runtime image/JDK dùng cho production.
6. Nếu cần `--add-opens` tạm thời, cấp quyền cho đúng module gọi reflection.
7. Loại bỏ flag sau khi đã cập nhật dependency.

Với Maven, có thể xem dependency tree:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies
~~~

Kiểm tra dependency gián tiếp quan trọng vì một bản library cũ có thể được kéo vào qua framework khác dù project đã cập nhật direct dependency.

## 16. Mẫu báo lỗi và hướng chẩn đoán

| Triệu chứng | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `package ... is not visible` | Package thuộc named module nhưng không export cho consumer | Dùng API được hỗ trợ hoặc xem lại exports |
| `module X does not export P to Y` | Public type/member trong P bị chặn bởi module boundary | Xác định source module, package và target module |
| `InaccessibleObjectException` | Deep reflection vào package chưa open | Xác định module gọi reflection, bỏ dependency vào private field nếu có thể |
| `IllegalAccessError` khi chạy | Runtime không cho phép truy cập đã được bytecode yêu cầu | So sánh compile/runtime flags và API đang bị gọi |
| `ClassNotFoundException` | Class không được loader tìm thấy; có thể đã bị loại bỏ hoặc dependency thiếu | Kiểm tra module path, phiên bản JDK và artifact |
| `NoSuchMethodError` | Binary dùng method không tồn tại trong class đã nạp | Kiểm tra binary compatibility, version và sử dụng internal API |
| `illegal reflective access` warning trên JDK cũ | Code dựa vào cơ chế tương thích đã bị siết ở JDK mới | Nâng cấp library và bỏ reflection không được hỗ trợ |
| `--illegal-access` không giải quyết lỗi | Trên JDK hiện đại tùy chọn không còn mở quyền như trước | Sửa code hoặc dùng biện pháp có mục tiêu trong giai đoạn migration |

Một mẫu ghi nhận sự cố:

~~~text
Java version:
  java --version

Runtime command:
  java ... --module-path ... -m ...

Source module:
  java.base

Package:
  jdk.internal.misc

Caller module:
  com.acme.app (hoặc unnamed module)

Access type:
  normal access / deep reflection

Dependency:
  com.acme:legacy-lib:version

Planned resolution:
  upgrade dependency / use public API / temporary scoped flag
~~~

Đừng tự động mở hàng loạt package chỉ vì exception liên tục xuất hiện. Mỗi flag nên gắn với một nguyên nhân và một kế hoạch loại bỏ cụ thể.

## 17. Quy trình migration sang JDK mới

Đối với ứng dụng có dependency cũ, có thể áp dụng một quy trình có kiểm soát:

**Bước 1 — Xác định target JDK.** Đồng bộ compiler, CI, staging và production. Ghi `java --version` và đường dẫn executable thực tế.

**Bước 2 — Quét code và dependency.** Tìm `sun.*`, `jdk.internal.*` hoặc các import không được hỗ trợ; chạy `jdeps --jdk-internals`.

**Bước 3 — Kiểm thử trên JDK mục tiêu.** Ghi lỗi compile, runtime linkage và reflection riêng biệt.

**Bước 4 — Xem module descriptor.** Dùng `java --describe-module` để biết package nào export/open cho ai. Với JAR thư viện có module descriptor, dùng `jar --describe-module --file library.jar`.

**Bước 5 — Phân loại dependency.** Tách code của ứng dụng khỏi library bên thứ ba; xác định version cần nâng cấp.

**Bước 6 — Thay bằng public API.** Ưu tiên API Java SE hoặc JDK-specific documented API phù hợp.

**Bước 7 — Cấp quyền tạm nếu bắt buộc.** Dùng `--add-exports` hoặc `--add-opens` với đúng source/package/target, theo dõi trong cấu hình build/deploy.

**Bước 8 — Test trên runtime image thật.** Đặc biệt với image tùy chỉnh từ `jlink`, nơi không phải mọi `jdk.*` module đều được đóng gói.

**Bước 9 — Loại dần workaround.** Sau khi nâng cấp dependency, kiểm thử bỏ từng flag để tránh duy trì lối truy cập internals không cần thiết.

Nếu ứng dụng là thư viện được nhiều project khác sử dụng, việc chuyển public signature khỏi JDK internal type càng quan trọng. Public API phụ thuộc một kiểu không được export có thể khiến consumer không thể compile ngay cả khi implementation của thư viện chạy được ở môi trường riêng.

## 18. Checklist thiết kế trước khi phụ thuộc module JDK

Trước khi thêm `requires jdk.some.module` hoặc import một class từ JDK:

- [ ] Package có được module descriptor export cho module của mình không?
- [ ] API có tài liệu public và chính sách hỗ trợ phù hợp không?
- [ ] API thuộc Java SE hay chỉ thuộc JDK-specific module?
- [ ] Runtime image triển khai có chứa module đó không?
- [ ] Có API Java SE nào đáp ứng cùng yêu cầu không?
- [ ] Có đang dựa vào reflection hoặc private field của JDK không?
- [ ] Có cần JVM flags nới encapsulation để chạy hay biên dịch không?
- [ ] Nếu cần workaround, đã có lý do và kế hoạch loại bỏ chưa?
- [ ] Các dependency bên thứ ba có tương thích với JDK mục tiêu không?
- [ ] Đã test trên cấu hình module path và runtime thật chưa?

**Nguyên tắc thực hành:** chỉ dựa vào những package mà module công bố và tài liệu cam kết phù hợp; giữ dependency vào implementation detail ở mức thấp nhất hoặc loại bỏ hoàn toàn.

## Kết luận

JDK được modular hóa không có nghĩa mọi class trong JDK đều là API công khai. `java.base` có cả Java SE API và package nội bộ; `jdk.compiler` có cả API được công bố và implementation package; `jdk.unsupported` duy trì một số API vì tương thích nhưng không cung cấp cam kết ổn định như Java SE.

Muốn quyết định có nên sử dụng một API, hãy xem **module descriptor, exports/opens và tài liệu hỗ trợ**, không chỉ tên class hoặc khả năng tìm thấy JAR/JMOD. Khi migration gặp lỗi `package is not visible`, `IllegalAccessError` hoặc `InaccessibleObjectException`, hãy xác định đúng loại truy cập, quét dependency bằng `jdeps --jdk-internals`, và ưu tiên public API thay thế. `--add-exports`/`--add-opens` có thể hữu ích tạm thời, nhưng **mở được package không biến JDK internal API thành hợp đồng được hỗ trợ lâu dài**.
