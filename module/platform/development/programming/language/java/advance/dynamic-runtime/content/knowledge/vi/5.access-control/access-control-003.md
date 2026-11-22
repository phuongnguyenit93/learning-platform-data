# 5.3 Đối chiếu `exports`, `opens`, module có tên và unnamed module

Hệ thống module của Java (*Java Platform Module System* – JPMS, từ Java 9) kiểm soát **module nào đọc được module nào** và **package nào của module được phép sử dụng từ bên ngoài**. Với chương trình động, reflection và các framework như dependency injection, serialization hay ORM, phân biệt `exports` và `opens` là điều kiện để hiểu vì sao một class `public` vẫn có thể bị từ chối truy cập.

Bài này tập trung vào quyền truy cập giữa **các module khác nhau** trên **Java 17+**: cách `exports` hỗ trợ API công khai, `opens` hỗ trợ deep reflection, khác biệt giữa *named module* và *unnamed module* (class path), cách kiểm tra bằng `java.lang.Module` và cách chẩn đoán lỗi.

## 1. Ba yếu tố phải xét riêng

Một lời gọi từ module A đến một kiểu nằm trong module B có nhiều tầng kiểm soát:

1. **Readability (quan hệ đọc):** A có đọc được B không? Với module tường minh, `requires B;` trong `module-info.java` thường tạo quan hệ này. `Module.canRead(other)` kiểm tra quan hệ ở runtime.
2. **Ranh giới package:** B có **export** package để A tham chiếu kiểu công khai bằng Java thông thường, hoặc **open** package để A truy cập bằng reflection không?
3. **Quyền Java ở mức class/member:** `public`, `protected`, package-private, `private` vẫn có ý nghĩa. `exports` không tự biến field `private` thành công khai; `opens` cho phép những API reflection thích hợp *đề nghị bỏ qua* kiểm tra truy cập bằng `setAccessible(true)` hoặc `trySetAccessible()`.

Ví dụ có `module shop.app { requires shop.core; }` mà `shop.core` **không** `exports shop.core.api;` thì `shop.app` vẫn không thể viết `import shop.core.api.Product;`, dù `Product` được khai báo `public`. Đọc được một module **không đồng nghĩa** truy cập được mọi package trong module.

Ngược lại, `exports` **không tạo quan hệ đọc**. Để tham chiếu tĩnh qua các named module, thông thường cần cả quan hệ readability và quyền export đến module gọi. Với core reflection, Java có quy tắc riêng: việc kiểm tra truy cập của đối tượng reflection giả định caller đã đọc module chứa member; điều này **không thay thế** quy tắc readability của mã Java thông thường.

## 2. Bảng đối chiếu `exports` và `opens`

Giả sử `p` nằm trong named module B, mã gọi nằm trong **named module A khác B**, và A đọc B khi cần dùng API tĩnh:

| Khai báo trong B | A `import` và gọi `public` API ở `p` lúc biên dịch? | A dùng reflection trên thành viên `public` của kiểu `public`? | A bật `setAccessible(true)` cho thành viên `private` của `p`? |
| --- | --- | --- | --- |
| `exports p;` | Có | Có | Không, nếu không có quyền mở khác |
| `opens p;` | Không | Có, ở runtime | Có, theo các quy tắc reflection |
| `exports p;` và `opens p;` | Có | Có | Có |
| Không khai báo cả hai | Không | Không truy cập thành viên từ module khác theo đường thông thường | Không |

**Hiểu đúng bảng:** `exports` cấp quyền để lập trình viên **sử dụng API công khai bằng mã Java thông thường**. `opens` cấp quyền để **công cụ runtime kiểm tra và truy cập sâu qua reflection** mà không bắt package trở thành API compile-time. Quy tắc đặc biệt cho code trong **chính module B** (có quyền nội bộ của nó) không được thể hiện trong bảng.

`opens` không phải lệnh “tắt” mọi kiểm soát của JVM: cần đúng API, đúng module được mở, đúng đối tượng phản chiếu; kiểm tra bảo mật khác và hạn chế ghi vào một số `final` field vẫn tồn tại.

## 3. `exports`: công bố public API

Ví dụ `module-info.java` của thư viện:

~~~java
module shop.core {
    exports shop.core.api;
}
~~~

Các module **đọc** `shop.core` có thể tham chiếu những kiểu `public` trong `shop.core.api` và các thành viên có quyền truy cập phù hợp. Các kiểu package-private, field `private` và package nội bộ khác **không tự động lộ ra**.

`exports` phù hợp cho API mà bạn chủ động cam kết cho module khác gọi: interface dịch vụ, model công khai hoặc lớp facade. Giữ các package triển khai nội bộ không export nếu caller không cần `import` chúng.

Muốn giới hạn đối tượng được phép sử dụng API, dùng **qualified export**:

~~~java
module shop.core {
    exports shop.core.spi to shop.app;
}
~~~

Chỉ named module `shop.app` được export package `shop.core.spi` theo khai báo này. Tên sau `to` là **tên module**, không phải tên package hay tên class. Việc export có điều kiện vẫn đòi hỏi quan hệ đọc phù hợp khi import tĩnh. Một unnamed module không thể được nêu trực tiếp trong `to` của `module-info.java`.

## 4. `opens`: mở package cho deep reflection

Ví dụ một thư viện cho phép framework phân tích đối tượng nội bộ:

~~~java
module shop.core {
    exports shop.core.api;
    opens shop.core.entity;
}
~~~

- `shop.core.api` là API dùng trực tiếp từ Java code.
- `shop.core.entity` **không** trở thành package có thể import từ module khác lúc biên dịch.
- Tại runtime, mã trong module khác có thể tìm class của `shop.core.entity` bằng reflection và, nếu thỏa điều kiện API, bật quyền truy cập cho constructor, field hay method không `public`.

Sự khác nhau giữa *nhìn thấy metadata* và *thực sự truy cập member* rất quan trọng. `Class.forName(...)`, `getDeclaredFields()` hoặc `getDeclaredConstructor()` có thể lấy metadata mà chưa dùng member. Lỗi thường phát sinh ở `setAccessible(true)`, `newInstance()`, `Field.get(...)` hoặc `Method.invoke(...)` khi kiểm tra truy cập thực sự xảy ra.

Hai API xử lý thất bại khác nhau:

- `field.trySetAccessible()` trả `false` nếu không thể bật truy cập (trong trường hợp thường gặp là package chưa open cho module đang phản chiếu).
- `field.setAccessible(true)` có thể ném `java.lang.reflect.InaccessibleObjectException` nếu quyền truy cập không thể bật.

Để chỉ mở cho framework được chỉ định, dùng **qualified opens**:

~~~java
module shop.core {
    exports shop.core.api;
    opens shop.core.entity to shop.app;
}
~~~

Lúc này chỉ mã reflection ở named module `shop.app` được hưởng quyền mở theo chỉ thị đó; **không** phải mọi module. Với framework thực tế, cần xác định **module chứa mã gọi reflection**, đôi khi khác module chứa ứng dụng hoặc model.

Một package có thể vừa `exports` vừa `opens`. Nếu nhiều package đều cần mở, cú pháp `open module shop.core { ... }` mở **toàn bộ** package của module cho reflection; vẫn phải khai báo `exports` cho những API cần dùng khi biên dịch. Trong một `open module`, không viết thêm chỉ thị `opens package;` vì không hợp lệ. Không có cú pháp `opens shop.core.*;` để mở package theo wildcard.

## 5. Named module, unnamed module và automatic module

| Loại | Được hình thành thế nào? | `Module.isNamed()` | Đọc module khác | Export/open package |
| --- | --- | --- | --- | --- |
| **Explicit named module** | Có `module-info.java`, đặt trong module path | `true` | Theo `requires`/quy tắc của module graph | Theo `exports`, `opens` và quyền mở bổ sung |
| **Unnamed module** | Class/JAR trên class path; mỗi class loader có unnamed module riêng | `false` | Đọc mọi module **đã được đưa vào module graph** | Export và open tất cả package của nó |
| **Automatic module** | JAR không có descriptor module tường minh, đặt trên module path | `true` | Được áp dụng quy tắc tương thích: đọc các module được giải quyết và unnamed modules | Tại runtime, export và open các package của chính nó |

**Không nhầm class path với module path:** Cùng một JAR không có `module-info.class` có thể thuộc **unnamed module** khi đặt trên class path, hoặc trở thành **automatic named module** khi đặt trên module path. Một JAR modular với descriptor đặt trên module path có thể là explicit named module. Đây là lý do quyền truy cập và lỗi reflection có thể thay đổi khi chuyển cách chạy ứng dụng.

Với unnamed module:

- `SomeClasspathClass.class.getModule().isNamed()` là `false`; `getName()` và `getDescriptor()` trả `null`.
- Các package của nó mặc định **được export và open**. Vì vậy deep reflection vào chính các lớp class path thường không gặp hàng rào `opens` giữa các module, dù vẫn có các quy tắc Java khác.
- Nó đọc các named module **đã được resolve** trong module graph, nhưng việc có JAR nằm trên module path **không tự bảo đảm** module đó được resolve cho một ứng dụng chỉ chạy từ class path. Tùy cách khởi chạy có thể cần `--add-modules`.
- Named module **không thể khai báo `requires` một unnamed module** (vì unnamed không có tên). Trường hợp di chuyển dần sang JPMS cần chủ động tổ chức dependency; có thể dùng `--add-reads some.named.module=ALL-UNNAMED` cho những kịch bản tương thích thích hợp.

**Automatic module vẫn là named module**: nó có tên module và có thể được một named module khác `requires`. Đừng đánh đồng “không có `module-info.java` trong JAR” với “unnamed” nếu JAR đang ở module path.

## 6. Kiểm tra quyền thực tế bằng `java.lang.Module`

Các API cốt lõi trên Java 17:

| API | Điều kiểm tra |
| --- | --- |
| `SomeClass.class.getModule()` | Module chứa class |
| `module.isNamed()` / `module.getName()` | Có tên module không / tên module (`null` với unnamed) |
| `module.getDescriptor()` | Descriptor khi có (`null` với unnamed) |
| `caller.canRead(target)` | Runtime module caller có đọc target không |
| `target.isExported("p")` | `p` được xem là export vô điều kiện **tại runtime** |
| `target.isExported("p", caller)` | `p` được xem là export tới caller **tại runtime** |
| `target.isOpen("p")` | `p` được open vô điều kiện tại runtime |
| `target.isOpen("p", caller)` | `p` được open tới caller tại runtime |
| `target.getDescriptor().exports()` | Các chỉ thị export **khai báo trong descriptor** |
| `target.getDescriptor().opens()` | Các chỉ thị opens **khai báo trong descriptor** |

**Điểm tinh tế quan trọng:** Theo Java 17, **package đã `opens` cho một module cũng được `Module.isExported(package, thatModule)` xem là exported ở runtime**; tương tự, package `opens` vô điều kiện có thể làm `isExported(package)` trả `true`. Điều đó **không** có nghĩa package có chỉ thị `exports` để caller `import` lúc biên dịch.

Vì thế, khi phân tích cấu hình:

- Muốn biết **chỉ thị tĩnh thực sự đã khai báo**, xem `module.getDescriptor().exports()` và `opens()` (đồng thời kiểm tra `ModuleDescriptor.isOpen()` cho `open module`).
- Muốn biết **khả năng truy cập hiện tại tại runtime**, dùng `isExported`/`isOpen` với **module bên gọi thật sự**.
- Muốn biết **readability**, dùng `caller.canRead(target)` **riêng biệt**; `isExported` và `isOpen` không kiểm tra quan hệ đọc.
- Tránh truyền chính `target` vào tham số `caller` để “thử truy cập bên ngoài”: module luôn có quyền truy cập package của **chính nó**, nên kết quả không phản ánh giới hạn đặt ra cho module khác.

Đối với unnamed module, xem `ClassLoader.getSystemClassLoader().getUnnamedModule()` hoặc `SomeClasspathClass.class.getModule()`. Nếu một ứng dụng có nhiều class loader, có thể có **nhiều unnamed module khác nhau**.

## 7. Ví dụ hoàn chỉnh: hai named module và quyền reflection

Cấu trúc dự án (hai module `demo.lib`, `demo.app`):

~~~text
src/
  demo.lib/
    module-info.java
    demo/api/Message.java
    demo/internal/Secret.java
  demo.app/
    module-info.java
    demo/app/Main.java
~~~

**File `src/demo.lib/module-info.java`**

~~~java
module demo.lib {
    exports demo.api;
    opens demo.internal;
}
~~~

**File `src/demo.lib/demo/api/Message.java`**

~~~java
package demo.api;

public class Message {
    public String text() {
        return "hello";
    }
}
~~~

**File `src/demo.lib/demo/internal/Secret.java`**

~~~java
package demo.internal;

public class Secret {
    private final String code = "deep-ok";

    private Secret() {}
}
~~~

**File `src/demo.app/module-info.java`**

~~~java
module demo.app {
    requires demo.lib;
}
~~~

**File `src/demo.app/demo/app/Main.java`**

~~~java
package demo.app;

import demo.api.Message;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        Module lib = Message.class.getModule();
        Module app = Main.class.getModule();

        System.out.println("lib named: " + lib.isNamed());
        System.out.println("lib name: " + lib.getName());
        System.out.println("app reads lib: " + app.canRead(lib));
        System.out.println("api declared exported: "
                + lib.getDescriptor().exports().stream()
                    .anyMatch(e -> e.source().equals("demo.api")));
        System.out.println("internal declared exported: "
                + lib.getDescriptor().exports().stream()
                    .anyMatch(e -> e.source().equals("demo.internal")));
        System.out.println("api runtime exported to app: "
                + lib.isExported("demo.api", app));
        System.out.println("api open to app: "
                + lib.isOpen("demo.api", app));
        System.out.println("internal runtime exported to app: "
                + lib.isExported("demo.internal", app));
        System.out.println("internal open to app: "
                + lib.isOpen("demo.internal", app));
        System.out.println("public call: " + new Message().text());

        Class<?> secretType = Class.forName("demo.internal.Secret");
        Constructor<?> constructor = secretType.getDeclaredConstructor();
        System.out.println("private ctor accessible: "
                + constructor.trySetAccessible());
        Object secret = constructor.newInstance();

        Field field = secretType.getDeclaredField("code");
        System.out.println("private field accessible: "
                + field.trySetAccessible());
        System.out.println("secret value: " + field.get(secret));
    }
}
~~~

Đứng ở thư mục chứa `src/`, chạy với **JDK 17 trở lên**:

~~~bash
javac --release 17 -d out --module-source-path src -m demo.lib,demo.app
java --module-path out -m demo.app/demo.app.Main
~~~

Stdout chính xác:

~~~text
lib named: true
lib name: demo.lib
app reads lib: true
api declared exported: true
internal declared exported: false
api runtime exported to app: true
api open to app: false
internal runtime exported to app: true
internal open to app: true
public call: hello
private ctor accessible: true
private field accessible: true
secret value: deep-ok
~~~

**Giải thích điểm then chốt:**

1. `Main` gọi `new Message().text()` được vì `demo.app` `requires demo.lib` và `demo.lib` `exports demo.api`.
2. Descriptor **không** có `exports demo.internal`, do đó `internal declared exported: false`. Nhưng `demo.internal` được `opens`, nên `isExported("demo.internal", app)` trả `true` **theo ngữ nghĩa runtime**. Đây không phải dấu hiệu có thể `import demo.internal.Secret` khi biên dịch.
3. Constructor và field của `Secret` đều `private`; `trySetAccessible()` trả `true` vì package `demo.internal` mở tới `demo.app`. Nếu bỏ `opens demo.internal;` và biên dịch lại, lệnh thử bật quyền sẽ trả `false`; chương trình hiện tại sau đó sẽ gặp lỗi truy cập khi tạo `Secret` bằng constructor private.
4. `getDescriptor().exports()` và `Module.isExported(...)` trả lời **hai câu hỏi khác nhau**: *khai báo export* và *quyền export hiệu lực lúc chạy*.

## 8. Ví dụ hoàn chỉnh: ứng dụng ở class path là unnamed module

Tạo file riêng `classpath/demo/cli/ClasspathMain.java` (không có `module-info.java`):

~~~java
package demo.cli;

public class ClasspathMain {
    public static void main(String[] args) {
        Module module = ClasspathMain.class.getModule();

        System.out.println("classpath named: " + module.isNamed());
        System.out.println("classpath name: " + module.getName());
        System.out.println("classpath descriptor: " + module.getDescriptor());
        System.out.println("classpath package exported: "
                + module.isExported("demo.cli"));
        System.out.println("classpath package open: "
                + module.isOpen("demo.cli"));
    }
}
~~~

Lệnh chạy tại cùng thư mục gốc:

~~~bash
javac --release 17 -d cpout classpath/demo/cli/ClasspathMain.java
java -cp cpout demo.cli.ClasspathMain
~~~

Stdout chính xác:

~~~text
classpath named: false
classpath name: null
classpath descriptor: null
classpath package exported: true
classpath package open: true
~~~

Class này được nạp từ class path nên nằm trong unnamed module của class loader. Không có module descriptor tường minh, nhưng các package của unnamed module vẫn được export và open.

## 9. Gỡ vướng tạm thời bằng tham số khi khởi chạy

Nếu không thể sửa `module-info.java` của thư viện ngay, Java hỗ trợ thêm quyền ở build/run. Ví dụ với hai module ở phần 7:

| Nhu cầu | Tham số | Phạm vi |
| --- | --- | --- |
| Cho `demo.app` sử dụng `public` API trong package không được export | `--add-exports demo.lib/demo.internal=demo.app` | Có thể cần dùng khi **biên dịch và chạy**, tùy mã tham chiếu |
| Cho `demo.app` deep reflection vào `demo.internal` | `--add-opens demo.lib/demo.internal=demo.app` | **Runtime**; không biến package thành API import tại compile-time |
| Cho mã từ mọi unnamed module (class path) deep reflection vào package | `--add-opens demo.lib/demo.internal=ALL-UNNAMED` | Runtime, phạm vi rộng hơn module đích xác định |
| Bổ sung quyền đọc unnamed module cho một named module | `--add-reads demo.app=ALL-UNNAMED` | Bổ sung readability, không tự động open các package |

Có thể thử **xóa** `opens demo.internal;` trong `src/demo.lib/module-info.java`, biên dịch lại, rồi chạy với cờ mở ở runtime:

~~~bash
javac --release 17 -d out --module-source-path src -m demo.lib,demo.app
java --add-opens demo.lib/demo.internal=demo.app --module-path out -m demo.app/demo.app.Main
~~~

Lúc này phần deep reflection vẫn hoạt động bởi JVM được yêu cầu mở riêng package đó. Nếu không dùng cờ, `trySetAccessible()` trên constructor private trả `false`. Nếu thay bằng `setAccessible(true)`, trường hợp quyền bị từ chối sẽ thường ném `InaccessibleObjectException`.

**Lưu ý về phạm vi và thời điểm:**

- `--add-exports` giải quyết quyền truy cập công khai, **không** thay thế `--add-opens` khi cần đọc field `private`.
- `--add-opens` là tùy chọn **runtime**, không tạo quyền import khi `javac` kiểm tra mã Java.
- `ALL-UNNAMED` là đích đặc biệt cho **tùy chọn command line**, không phải tên module có thể ghi trong `exports ... to` hoặc `opens ... to`.
- Với ứng dụng class path cần tìm named module do bạn cung cấp trong module path, có thể phải thêm `--add-modules demo.lib` để module đó tham gia module graph; quyền `opens` hoặc `exports` chỉ có ý nghĩa khi module tương ứng đã được resolve.
- Trên Java 17, không dựa vào `--illegal-access` như một giải pháp lâu dài: tùy chọn tương thích cũ đã trở nên lỗi thời và không còn mở hàng loạt các package JDK bị đóng. Hãy khai báo `opens` đúng chỗ hoặc dùng `--add-opens` có phạm vi hẹp khi cần.

## 10. Chọn thiết kế phù hợp

**Thư viện có API ổn định:** đặt lớp hợp đồng công khai trong package `api`, dùng `exports`. Giữ implementation trong package riêng và tránh export nó nếu caller không cần mã tĩnh.

**ORM / serializer / dependency-injection framework:** đối tượng miền có thể nằm trong package không export nhưng mở **có điều kiện** cho module chứa mã phản chiếu, ví dụ `opens app.model to framework.module;`. Kiểm tra **tên module thực tế** của framework, không đoán theo tên thư viện/JAR. Nếu framework đang chạy trên class path, cân nhắc quyền tương thích `ALL-UNNAMED` ở runtime khi bắt buộc.

**Công cụ chẩn đoán class loading:** ghi cả `type.getModule().getName()`, `isNamed()`, `getClassLoader()`, quan hệ `canRead` và trạng thái `isExported`/`isOpen`. Khi nguyên nhân không rõ, so sánh `module-info.java`/descriptor với chính các quyền runtime (có thể được bổ sung bằng tùy chọn JVM).

**Di chuyển class path → module path:** kiểm kê dependency trước. JAR chuyển sang explicit named module có thể mất khả năng truy cập mặc định vào các package nội bộ khi không có `exports`/`opens`; đồng thời named module của ứng dụng không thể trực tiếp `requires` các class đang ở unnamed module. Đưa các hợp đồng ổn định vào package export và xác định rõ phần cần reflection.

## 11. Các lỗi nhầm phổ biến

| Nhận định sai | Điều cần nhớ |
| --- | --- |
| “Class đã `public` thì module khác luôn import được.” | Package còn cần được `exports` cho caller, và caller cần đọc module chứa kiểu. |
| “`requires` cho quyền vào mọi package của module khác.” | `requires` xử lý readability; `exports`/`opens` xử lý ranh giới package. |
| “`exports` đủ để đọc field `private` bằng `setAccessible`.” | Thông thường cần package `opens` tới module phản chiếu. |
| “`opens` nghĩa là có thể `import` package.” | `opens` cho truy cập lúc chạy qua reflection, không cung cấp quyền tham chiếu tĩnh lúc biên dịch. |
| “`Module.isExported(p) == true` chứng minh `module-info.java` có `exports p;`.” | Package open cũng được xem như exported **ở runtime**. Kiểm tra `getDescriptor().exports()` nếu cần chỉ thị đã khai báo. |
| “`Class.forName` thành công nghĩa là mọi method/field đều truy cập được.” | Nạp class/lấy metadata và truy cập member là những bước kiểm tra khác nhau. |
| “Unnamed module là module có tên tự động.” | Unnamed **không có tên**; automatic module là **named module**. |
| “Mọi JAR không có `module-info` đều chạy trong unnamed module.” | JAR trên **module path** có thể là automatic named module. |
| “`--add-opens` là cách cấp quyền compile-time.” | `--add-opens` phục vụ runtime reflection; API tĩnh cần export phù hợp. |
| “Có JAR trên module path thì class path code đọc được ngay.” | Với named module tự cung cấp có thể cần `--add-modules` để module được resolve trước. |
| “Có thể ghi `to ALL-UNNAMED` trong `module-info.java`.” | `ALL-UNNAMED` chỉ là đích đặc biệt của các tùy chọn JVM. |

## 12. Tự kiểm tra

1. Một package chỉ có `exports p;`, trong đó một class `public` có field `private`. Module khác có thể import class đó không? Có bật `trySetAccessible()` cho field private không?
2. Một package chỉ có `opens p;`. Vì sao `isExported("p", otherModule)` có thể là `true` dù `getDescriptor().exports()` không chứa `p`?
3. Một chương trình chuyển JAR từ class path sang module path, sau đó reflection vào private field bị từ chối. Hãy xác định **module nào thực hiện reflection**, rồi chọn giữa `opens p to module.name;` và `--add-opens source.module/p=target.module`.
4. Vì sao đặt một JAR lên module path nhưng không `--add-modules` không nhất thiết làm nó khả dụng cho ứng dụng chạy từ class path?

**Tài liệu tham khảo (Java 17 / JPMS):**

- [`java.lang.Module` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [`java.lang.reflect.AccessibleObject` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Open packages for reflection (dev.java)](https://dev.java/learn/modules/opening-for-reflection/)
- [Qualified exports and opens (dev.java)](https://dev.java/learn/organizing/modules/qualified-exports-opens/)
- [The unnamed module (dev.java)](https://dev.java/learn/organizing/modules/unnamed-module/)
- [`--add-exports` and `--add-opens` (dev.java)](https://dev.java/learn/organizing/modules/add-exports-opens/).