# Kiểm tra mô-đun được nạp qua dịch vụ hoặc phản chiếu trong app image Java

> **Ngữ cảnh:** **Java 14 → App image**, nhưng bài sử dụng các kỹ thuật Java còn áp dụng trong JDK hiện hành. `jpackage` xuất hiện ở trạng thái incubating trong Java 14 và trở thành công cụ chính thức từ **Java 16** (JEP 392); các ví dụ dựa trên **Java 17+**, không dùng tên module incubator hoặc công cụ preview cũ. Điểm trọng tâm là: khi dùng **`ServiceLoader`**, **reflection** hoặc module được chọn động, một app image có thể thiếu những module mà phân tích phụ thuộc tĩnh không phát hiện.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **application image** của `jpackage` với **custom runtime image** của `jlink`; hiểu cái gì nằm trong app image nhưng chưa chắc đã được resolve hoặc load.
2. Giải thích tại sao các module chứa **service providers** và các module chứa class được gọi bằng **reflection** có thể không xuất hiện trong phép phân tích `jdeps` thông thường.
3. Hiểu quan hệ giữa `module-info.java`: `requires`, `uses`, `provides ... with`, `exports` và `opens`.
4. Tìm các provider thực sự khả dụng bằng `ServiceLoader`, đối chiếu với `ModuleLayer.boot()` và danh sách module trong runtime image.
5. Dùng `jlink --bind-services`, `jlink --suggest-providers` và `--add-modules` có chủ đích, thay vì đưa mọi module vào image một cách mù quáng.
6. Biết thay đổi **quan trọng từ JDK 25**: `jpackage` **không còn tự động đưa service bindings vào runtime do nó tạo** như những bản trước; cần lựa chọn cấu hình rõ ràng.
7. Tạo và kiểm chứng một ứng dụng modular gồm **service API, provider và app**, rồi so sánh image có/không có provider.
8. Viết một probe dùng `Class.forName` để xác minh **class chỉ được gọi động**, và chỉ ra vì sao `jdeps --print-module-deps` chưa đủ.
9. Chạy test trên **launcher của app image thật** ở hệ điều hành đích; tránh nhầm kết quả từ full JDK trên máy phát triển với bundled runtime.
10. Chẩn đoán các lỗi `ServiceConfigurationError`, `ClassNotFoundException`, `NoClassDefFoundError` và `InaccessibleObjectException` theo đúng nguyên nhân.

**Ý chính:** Kiểm tra **ba lớp khác nhau**: module có **trong runtime image** hay không; module có **được resolve trong layer** hay không; và **provider/class thực sự được tìm thấy, tải và sử dụng** hay không. Không có một phép `jdeps` duy nhất thay thế được cả ba.

## 2. App image là gì? Runtime image là gì?

Một **app image** là thư mục đầu ra do `jpackage --type app-image` tạo, chứa launcher của ứng dụng, app JAR/modules/resources và một Java runtime để khởi chạy ứng dụng mà người dùng không cần cài JDK riêng.

Một **custom runtime image** do `jlink` tạo chứa **một tập Java modules** cùng các phụ thuộc cần thiết, với các launcher/cấu trúc runtime tương ứng.

Ví dụ minh họa bố cục app image trên Linux:

```text
DemoApp/
  bin/
    DemoApp           # launcher của ứng dụng
  lib/
    app/              # ứng dụng/config do jpackage đưa vào
    runtime/          # runtime được jlink tạo hoặc được cung cấp sẵn
```

Cấu trúc trên là **minh họa Linux**, không phải hợp đồng về mọi đường dẫn nội bộ. Windows và macOS có bố cục launcher khác nhau; một số file runtime và đường dẫn chi tiết là triển khai riêng, có thể thay đổi giữa bản JDK.

**Phân biệt bốn khái niệm:**

| Khái niệm | Dấu hiệu | Không thể suy ra |
| --- | --- | --- |
| **Module trong image** | Runtime chứa module đó; `java --list-modules` của custom runtime liệt kê được | Chưa chắc module đã được **resolve** trong boot layer của lần chạy cụ thể. |
| **Module resolved trong layer** | `ModuleLayer.boot().findModule(name)` trả `Optional` có giá trị | Chưa chắc class/provider của module đã được load/khởi tạo. |
| **Class đã load được** | `Class.forName(name)` hoặc `Class.getModule()` xác nhận class | Chưa chắc quyền truy cập phản chiếu sâu đã được cấp. |
| **Service provider có thể sử dụng** | `ServiceLoader.load(service)` tìm được provider và khởi tạo thành công | Chưa chắc mọi provider mong đợi đều có mặt, hay provider hoạt động đúng nghiệp vụ. |

`--list-modules` quan sát **module có sẵn trong runtime**; `ModuleLayer.boot()` quan sát **module được resolve vào boot layer**. Một module chỉ được thêm vào image không tự biến mọi class của nó thành các class đã load.

### 2.1. Vì sao việc đóng gói làm lộ lỗi trước đó?

Full JDK trên máy phát triển có nhiều Java modules. Khi chạy bằng `java` thông thường, một số modules được resolve nhờ tập root modules mặc định và thuật toán service binding của module resolution.

Custom runtime do `jlink` tạo có thể **chỉ bao gồm module được chỉ định và closure của các phụ thuộc `requires`**. Một lớp được gọi bằng tên String hoặc một service provider không nằm trong closure ấy có thể bị bỏ ra khỏi runtime. Kết quả là app hoạt động trong IDE/full JDK, nhưng sau khi `jpackage` đóng gói thành image thì có thể không tìm thấy service hoặc class.

**Đừng khắc phục bằng cách yêu cầu người dùng cài full JDK.** Mục tiêu của app image là đóng gói runtime đúng; cần tìm đúng các module động và bổ sung chúng khi liên kết, sau đó test launcher đã đóng gói.

## 3. Phụ thuộc tĩnh, service discovery và reflection khác nhau thế nào?

### 3.1. Phụ thuộc tĩnh: `requires`

Trong module descriptor:

```java
module demo.app {
    requires demo.api;
}
```

`demo.app` khai báo phụ thuộc đọc module `demo.api`. Khi liên kết với `jlink --add-modules demo.app`, jlink tìm closure cần thiết của `requires`, bao gồm `demo.api` và các module được yêu cầu tiếp theo.

### 3.2. Phụ thuộc động qua `ServiceLoader`: `uses` / `provides`

```java
// module-info.java của consumer
module demo.app {
    requires demo.api;
    uses demo.spi.Greeter;
}
```

```java
// module-info.java của provider
module demo.provider {
    requires demo.api;
    provides demo.spi.Greeter with demo.impl.HelloGreeter;
}
```

`uses` thể hiện module consumer sử dụng một service. `provides ... with` thể hiện module provider cung cấp implementation của service đó. **Consumer được khuyến nghị không `requires` trực tiếp module provider**, nhằm giữ khả năng thay thế implementation.

Vì `demo.app` chỉ `requires demo.api`, một phép liên kết **không binding service** có thể không đưa `demo.provider` vào image, dù module provider tồn tại trên module path lúc build.

### 3.3. Phụ thuộc động qua reflection

```java
Class<?> type = Class.forName("java.util.logging.Logger");
```

Trong ví dụ này tên class là một **String**, không phải một reference kiểu `Logger` trong bytecode theo cách phân tích phụ thuộc tĩnh thường nhìn thấy. `jdeps` sẽ không suy ra chắc chắn tất cả các class/module có thể xuất hiện từ mọi giá trị String runtime, file cấu hình, annotation processor, plugin registry hoặc input.

Các framework dùng reflection để load serializers, drivers, providers, adapters hoặc UI classes thường gặp loại phụ thuộc này. Nó có thể được xây dựng từ config và chỉ xuất hiện trên một số nhánh chương trình, vì vậy phải kiểm tra **đường chạy thực tế**.

**Ghi nhớ:** `jdeps` rất hữu ích để tìm dependency tĩnh, nhưng kết quả của nó **không phải danh sách đầy đủ mọi module mà ứng dụng có thể cần thông qua service discovery hoặc reflection**.

## 4. Ví dụ modular hoàn chỉnh: API, provider và ứng dụng

Ví dụ sau có ba Java modules:

```text
src/
  demo.api/
    module-info.java
    demo/spi/Greeter.java
  demo.provider/
    module-info.java
    demo/impl/HelloGreeter.java
  demo.app/
    module-info.java
    demo/app/Main.java
```

### 4.1. Module `demo.api` định nghĩa service

File **`src/demo.api/module-info.java`**:

```java
module demo.api {
    exports demo.spi;
}
```

File **`src/demo.api/demo/spi/Greeter.java`**:

```java
package demo.spi;

public interface Greeter {
    String greet();
}
```

`exports demo.spi` cho phép module khác sử dụng interface `Greeter`. Module API không biết implementation cụ thể.

### 4.2. Module `demo.provider` cung cấp service

File **`src/demo.provider/module-info.java`**:

```java
module demo.provider {
    requires demo.api;
    provides demo.spi.Greeter with demo.impl.HelloGreeter;
}
```

File **`src/demo.provider/demo/impl/HelloGreeter.java`**:

```java
package demo.impl;

import demo.spi.Greeter;

public final class HelloGreeter implements Greeter {
    @Override
    public String greet() {
        return "Hello from provider";
    }
}
```

`HelloGreeter` là implementation thực sự. Module provider **không cần `exports demo.impl`** chỉ để `ServiceLoader` tạo provider theo hợp đồng module service; không nên xuất public API nội bộ không cần thiết.

### 4.3. Module `demo.app` sử dụng service

File **`src/demo.app/module-info.java`**:

```java
module demo.app {
    requires demo.api;
    uses demo.spi.Greeter;
}
```

File **`src/demo.app/demo/app/Main.java`**:

```java
package demo.app;

import demo.spi.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        System.out.println("provider-module="
                + ModuleLayer.boot()
                        .findModule("demo.provider").isPresent());

        var names = ServiceLoader.load(Greeter.class)
                .stream()
                .map(provider -> provider.type().getName())
                .sorted()
                .toList();
        System.out.println("providers=" + names);

        ServiceLoader.load(Greeter.class).forEach(greeter ->
                System.out.println("greeting=" + greeter.greet()));
    }
}
```

**Phân tích ba kết quả:**

- `provider-module=...` cho biết module `demo.provider` được **resolve** vào boot layer của launcher hay chưa.
- `providers=...` lấy danh sách tên class mà `ServiceLoader` tìm được. `ServiceLoader.Provider.type()` cho phép xem kiểu provider mà không nhất thiết tạo tất cả instance trước khi chọn.
- `greeting=...` chứng minh provider đã được **khởi tạo** và dùng thực tế, mạnh hơn việc chỉ thấy tên module trong ảnh.

**Điểm đúng về JPMS:** Module consumer có `uses demo.spi.Greeter`. Nếu bỏ `uses` khỏi named module rồi gọi `ServiceLoader.load(Greeter.class)`, có thể gặp `ServiceConfigurationError` do module gọi không khai báo sử dụng service. Đừng cố chữa lỗi này chỉ bằng `--add-modules`.

### 4.4. Biên dịch và chạy từ full JDK

Tạo các thư mục output `mods/demo.api`, `mods/demo.provider`, `mods/demo.app`. Các lệnh sau chạy trong Bash/sh trên Linux/macOS; với Windows hãy tạo thư mục bằng PowerShell và chạy các lệnh `javac` tương đương với dấu phân cách đường dẫn phù hợp:

```bash
mkdir -p mods/demo.api mods/demo.provider mods/demo.app

javac --release 17 -d mods/demo.api \
  src/demo.api/module-info.java \
  src/demo.api/demo/spi/Greeter.java

javac --release 17 --module-path mods -d mods/demo.provider \
  src/demo.provider/module-info.java \
  src/demo.provider/demo/impl/HelloGreeter.java

javac --release 17 --module-path mods -d mods/demo.app \
  src/demo.app/module-info.java \
  src/demo.app/demo/app/Main.java

java --module-path mods --module demo.app/demo.app.Main
```

**Stdout trên full JDK trong môi trường test có ba module trên module path:**

```text
provider-module=true
providers=[demo.impl.HelloGreeter]
greeting=Hello from provider
```

Khi chạy modular app từ full JDK với service provider khả dụng trên module path, Java launcher có thể resolve service provider trong quá trình module resolution. Nhưng đó **không** là bằng chứng `jlink` sẽ đưa provider vào một runtime thu gọn nếu không có cấu hình service binding tương ứng.

**Thông tin kiểm chứng:** Bộ mã ở phần 4–6 đã được biên dịch/chạy trên JDK 21 với `--release 17`; kết quả của ba tình huống jlink được kiểm tra trực tiếp. Những lệnh dùng `jpackage` áp dụng theo tài liệu toolchain tương ứng, và cần xác minh thêm trên chính JDK/hệ điều hành bạn phát hành.

## 5. Thử nghiệm 1: `jlink` không service-bind sẽ thiếu provider

Dùng các class đã biên dịch ở thư mục `mods`.

### 5.1. Liên kết chỉ module chính và requires closure

```bash
jlink --module-path mods \
  --add-modules demo.app \
  --output runtime-no-bind

./runtime-no-bind/bin/java --list-modules
./runtime-no-bind/bin/java \
  --module demo.app/demo.app.Main
```

`--list-modules` có thể liệt kê cả các module runtime chuẩn, nhưng với ba module `demo.*` ở ví dụ, chỉ có **`demo.api` và `demo.app`**, **không có `demo.provider`**.

**Stdout của riêng lệnh chạy `Main`**:

```text
provider-module=false
providers=[]
```

Không có dòng `greeting=...` vì `ServiceLoader` không thấy implementation nào trong runtime image đó.

**Nguyên nhân:** Mặc dù `demo.provider` nằm ở `mods` khi build, nó không thuộc `requires` closure của `demo.app` và không có `--bind-services` hoặc root module tường minh để liên kết nó. `ServiceLoader` vẫn hợp lệ về cú pháp; nó đơn giản không tìm được provider.

Điều này giải thích tình huống app chạy tốt trong IDE nhưng bản app image sau đóng gói chỉ trả danh sách provider rỗng.

### 5.2. Liên kết provider như một root module tường minh

Khi biết chính xác provider cần có:

```bash
jlink --module-path mods \
  --add-modules demo.app,demo.provider \
  --output runtime-explicit

./runtime-explicit/bin/java \
  --module demo.app/demo.app.Main
```

**Stdout:**

```text
provider-module=true
providers=[demo.impl.HelloGreeter]
greeting=Hello from provider
```

`--add-modules demo.provider` làm provider và phụ thuộc của nó nằm trong runtime. Đây là một lựa chọn có chủ đích khi bạn cần một danh sách provider đã được kiểm soát thay vì lấy tất cả provider tìm được.

### 5.3. Liên kết tự động các provider qua `--bind-services`

`jlink` có lựa chọn `--bind-services` để thêm service provider modules và dependencies tương ứng:

```bash
jlink --module-path mods \
  --add-modules demo.app \
  --bind-services \
  --output runtime-bind

./runtime-bind/bin/java \
  --module demo.app/demo.app.Main
```

**Stdout của ví dụ:**

```text
provider-module=true
providers=[demo.impl.HelloGreeter]
greeting=Hello from provider
```

Đây là lúc **`uses` trong `demo.app`** và **`provides ... with` trong `demo.provider`** cho phép service binding bổ sung provider. Với module path lớn, `--bind-services` có thể kéo thêm nhiều provider modules và các phụ thuộc của chúng, làm image lớn hơn. Hãy **kiểm tra tập module thực tế** chứ không coi `--bind-services` là lựa chọn miễn phí.

### 5.4. Dùng `--suggest-providers` để khám phá

`jlink` còn có:

```bash
jlink --module-path mods \
  --suggest-providers demo.spi.Greeter
```

Công cụ đề xuất provider module tìm được trên module path. Với bộ mẫu có một provider, output có nội dung tương tự:

```text
Suggested providers:
  demo.provider provides demo.spi.Greeter used by demo.app
```

Định dạng văn bản và tập provider hiển thị phụ thuộc JDK/module path; không coi stdout chẩn đoán này là hợp đồng API ổn định. Sau khi xem gợi ý, chọn **`--bind-services`** hoặc bổ sung **root provider modules** theo yêu cầu của app.

**Không có nghĩa `--suggest-providers` đã sửa runtime image**. Nó chỉ giúp *khám phá* provider, không sinh image chạy sẵn.

## 6. Ba tầng xác minh: available, resolved, usable

Đừng dùng một tín hiệu rồi kết luận mọi thứ đã đúng.

### 6.1. Tầng A — Module có trong runtime image?

Với **custom runtime image do `jlink` tạo**, thử:

```bash
./runtime-no-bind/bin/java --list-modules
./runtime-explicit/bin/java --list-modules
./runtime-bind/bin/java --list-modules
```

Các lệnh này cho biết **module có sẵn trong image**, không phải danh sách class được tải khi app chạy. Với bộ mẫu, bạn có thể lọc dòng `demo.*` bằng công cụ shell phù hợp; không được bỏ qua module JDK khác khi đánh giá kích thước/dependencies.

Với **app image `jpackage`**, đường dẫn runtime trong bundle có thể khác và `jpackage` thường dùng `--strip-native-commands` nên **có thể không có `bin/java` bên trong runtime**. Vì vậy cách xác minh **chính** là chạy launcher app và các probe trong chính ứng dụng (phần 4.3), hoặc kiểm tra một custom runtime riêng trước khi đưa vào app image; đừng phụ thuộc mãi vào một đường dẫn runtime nội bộ cụ thể.

### 6.2. Tầng B — Module có trong boot layer không?

Trong code đang chạy:

```java
boolean present = ModuleLayer.boot()
        .findModule("demo.provider")
        .isPresent();
System.out.println("provider-resolved=" + present);
```

Đây là **snippet trong phương thức**, không phải file độc lập. `ModuleLayer.boot()` chỉ kiểm tra boot layer và những module trong các parent layers tương ứng. Với hệ thống plugin tạo **custom ModuleLayer** sau startup, module có thể được resolve trong layer riêng nhưng **không có trong boot layer**. Khi đó phải kiểm tra **layer thực sự chứa module** bằng `ModuleLayer` bạn đã tạo hoặc bằng `someLoadedClass.getModule().getLayer()`.

Không được suy ra «module absent» toàn JVM chỉ vì `ModuleLayer.boot().findModule(name)` trả empty trong một hệ thống có module layers do ứng dụng tự quản lý.

### 6.3. Tầng C — Service provider thực sự tìm được và dùng được?

```java
var loader = java.util.ServiceLoader.load(demo.spi.Greeter.class);
var names = loader.stream()
        .map(provider -> provider.type().getName())
        .sorted()
        .toList();
System.out.println("providers=" + names);
```

Đây là **snippet dùng class `demo.spi.Greeter` từ bộ mẫu**, có thể đặt trong `Main`. Nó kiểm tra class provider mà `ServiceLoader` nhìn thấy trong ngữ cảnh loader/layer tương ứng.

Sau đó cần **thực sự gọi `provider.get()` hoặc duyệt instances** để xác minh không có lỗi ở khâu khởi tạo, thiếu constructor hợp lệ, dependency lúc chạy hoặc runtime exception của implementation. Chỉ thấy `Provider.type()` không đồng nghĩa mọi instance provider đã được tạo thành công.

### 6.4. Tầng D — Class reflection có tải và truy cập được không?

Một class khác có thể được tạo theo tên String:

```java
Class<?> type = Class.forName("com.example.plugins.FastCodec");
System.out.println(type.getModule().getName());
```

Đây là đoạn **minh họa**, class `com.example.plugins.FastCodec` phải tồn tại trong runtime/module hoặc class path thực tế thì mới chạy. `Class.forName` cho biết class có thể được **tìm/tải/khởi tạo theo dạng overload dùng một String**. Nếu dùng deep reflection trên thành viên private hoặc package chưa mở, còn cần kiểm tra quy tắc `exports`/`opens`. **Module có trong image không tự trao quyền reflective access.**

## 7. Ví dụ chạy được: phụ thuộc reflection mà `jdeps` không thấy

Thí nghiệm này dùng một class **có thật trong JDK hiện hành**: `java.util.logging.Logger` thuộc module `java.logging`. Chương trình **chỉ nhắc đến tên class qua String**, không `import java.util.logging.Logger`, nên phân tích bytecode tĩnh không có phụ thuộc kiểu thông thường đến module này.

Lưu file **`ReflectiveProbe.java`**:

```java
public class ReflectiveProbe {
    public static void main(String[] args) {
        boolean resolved = ModuleLayer.boot()
                .findModule("java.logging")
                .isPresent();

        boolean loadable;
        try {
            Class<?> type =
                    Class.forName("java.util.logging.Logger");
            loadable = "java.logging".equals(
                    type.getModule().getName());
        } catch (ClassNotFoundException e) {
            loadable = false;
        }

        System.out.println("java.logging-resolved=" + resolved);
        System.out.println("logger-loadable=" + loadable);
    }
}
```

Biên dịch bằng JDK 17+:

```bash
mkdir -p classes
javac --release 17 -d classes ReflectiveProbe.java

jdeps --print-module-deps classes
java -cp classes ReflectiveProbe
```

**Output của `jdeps --print-module-deps classes`** với bộ mẫu này:

```text
java.base
```

**Stdout của chương trình trên full JDK trong thí nghiệm:**

```text
java.logging-resolved=true
logger-loadable=true
```

Giải thích: Không có reference đến `Logger` trong bytecode dưới dạng import/chữ ký method hoặc lệnh trực tiếp, nên `jdeps` chỉ báo `java.base` trong mẫu. Nhưng full JDK còn có `java.logging` và trong cấu hình chạy từ class path này module đã được resolve.

### 7.1. Chạy với runtime tối thiểu chỉ có `java.base`

```bash
jlink --add-modules java.base \
  --output runtime-reflect-minimal

./runtime-reflect-minimal/bin/java \
  -cp classes ReflectiveProbe
```

**Stdout:**

```text
java.logging-resolved=false
logger-loadable=false
```

Dù `ReflectiveProbe` compile thành công và `jdeps` chỉ báo `java.base`, khi runtime không có `java.logging` thì `Class.forName("java.util.logging.Logger")` không tìm được class. Code chủ động bắt `ClassNotFoundException` nên chương trình in `false` thay vì crash.

### 7.2. Thêm module được dùng qua reflection

```bash
jlink --add-modules java.base,java.logging \
  --output runtime-reflect-with-logging

./runtime-reflect-with-logging/bin/java \
  -cp classes ReflectiveProbe
```

**Stdout:**

```text
java.logging-resolved=true
logger-loadable=true
```

**Ý nghĩa:** Khi một module chỉ xuất hiện thông qua **Class.forName**, cấu hình file, tên String hoặc framework, bạn phải **thêm module phù hợp vào custom runtime** và kiểm thử ở đường chạy thật. `jdeps` không thể luôn dự đoán được giá trị của những String động đó.

Các kết quả trên được kiểm tra trên JDK 21 với `--release 17`. Với các runtime tùy biến, module graph/phân giải có thể khác nếu chọn root modules khác; hãy chạy probe bằng **chính bundled runtime/launcher** của ứng dụng.

### 7.3. `jdeps` vẫn rất hữu ích, nhưng không đủ

`jdeps --print-module-deps` xuất một danh sách các module để dùng làm đầu vào `jlink --add-modules`. Nó là điểm bắt đầu tốt cho ứng dụng không modular hoặc tập JAR phức tạp:

```bash
jdeps --multi-release 17 --print-module-deps app.jar
```

Đây là lệnh **minh họa** khi file `app.jar` tồn tại và là artifact bạn muốn phân tích. Với third-party JAR dependencies, cần cung cấp class path/module path chính xác theo cách `jdeps` hỗ trợ để không nhận kết quả thiếu. `--ignore-missing-deps` chỉ bỏ qua thông báo missing, **không** làm các class/module thiếu tự xuất hiện trong image.

**Checklist sau `jdeps`:** rà soát các `Class.forName`, `ServiceLoader.load`, `META-INF/services`, file cấu hình provider, driver/serializer/backend chọn động và tính năng ít khi chạy. Sau đó bổ sung đúng modules và integration-test packaged launcher.

## 8. Đóng gói với `jpackage --type app-image`

`jpackage` tạo **application image** (launcher + application payload + Java runtime). Với modular app bộ mẫu:

```bash
jpackage --type app-image \
  --name DemoApp \
  --module-path mods \
  --module demo.app/demo.app.Main \
  --dest dist
```

Thư mục đầu ra `dist/DemoApp` phải là một đường dẫn mới/chưa tồn tại khi dùng mẫu trên. Trên Linux, launcher thường ở `dist/DemoApp/bin/DemoApp`; với Windows và macOS, vị trí file thực thi sẽ khác.

**Quan trọng:** Lệnh trên dùng **mặc định của phiên bản `jpackage` đang chạy**. Không được dựa trên việc default của Java 17/21 tương đương Java 25+ về service binding.

### 8.1. Thay đổi quan trọng từ JDK 25

Theo tài liệu Oracle Java SE 25 Packaging Overview và JDK 25 Release Notes:

- Trước **JDK 25**, `jpackage` tạo runtime có áp dụng service bindings theo default của các bản đó.
- **Từ JDK 25**, runtime do `jpackage` tạo **không tự thêm service bindings** mặc định.
- Vì thế app dùng `ServiceLoader` có thể thiếu provider modules sau khi nâng cấp toolchain đóng gói, dù source code, module path và app launcher không thay đổi.
- Muốn quay về hành vi thêm provider bằng service binding, **truyền `--bind-services` thông qua `--jlink-options`** hoặc **chỉ định rõ các provider module** cần thiết.

Đây là một thay đổi **hiện hành phải tính đến**, không phải một mẹo của bản incubator Java 14.

**Ví dụ chỉ định service binding rõ ràng** (Bash/sh):

```bash
jpackage --type app-image \
  --name DemoApp \
  --module-path mods \
  --module demo.app/demo.app.Main \
  --dest dist \
  --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services"
```

Lệnh này yêu cầu jpackage chuyển các flags trong **một chuỗi option** cho jlink. Bốn lựa chọn `--strip-*`/`--no-*` được giữ như cấu hình tối ưu runtime mà jpackage mặc định dùng; `--bind-services` được thêm vào cuối.

**Tại sao ghi cả bốn lựa chọn mặc định?** Khi tự truyền `--jlink-options`, cần xác định lại tập options cho jlink; không nên mặc định rằng các tối ưu hóa của jpackage sẽ luôn được tự thêm vào sau flags bạn chỉ định. Oracle cung cấp chính mẫu options này trong JDK 25 Release Notes.

**Một cách khác:** Nếu biết provider đúng là `demo.provider`, có thể khai báo rõ:

```bash
jpackage --type app-image \
  --name DemoExplicit \
  --module-path mods \
  --module demo.app/demo.app.Main \
  --add-modules demo.provider \
  --dest dist
```

`--add-modules` yêu cầu đưa provider vào tập root modules khi jpackage tạo runtime; đây là lựa chọn có chủ đích, tránh kéo tất cả providers không cần thiết qua `--bind-services`.

**Lưu ý thao tác:** Hai lệnh tạo **hai app images có tên khác nhau** để tránh ghi đè; phải đảm bảo `dist/DemoApp` hoặc `dist/DemoExplicit` chưa có, hoặc dọn đúng đường dẫn đầu ra trong môi trường build có kiểm soát. Không chạy xóa thư mục đích một cách mù quáng ở dự án thật.

### 8.2. Kiểm tra launcher của image thực tế

Với app image `DemoApp` tạo thành công trên Linux:

```bash
./dist/DemoApp/bin/DemoApp
```

Bạn mong muốn những dòng kiểm chứng:

```text
provider-module=true
providers=[demo.impl.HelloGreeter]
greeting=Hello from provider
```

Nếu thấy:

```text
provider-module=false
providers=[]
```

thì cần kiểm tra provider module có được đóng gói/resolved hay không, cấu hình service binding, module path và phiên bản jpackage đang dùng. **Không phán đoán từ tên thư mục image hay việc launcher mở được**.

Trong CI, hãy chạy **chính launcher đóng gói** trên nền tảng mục tiêu và assert provider được tìm thấy. Không chỉ chạy `java --module-path mods` từ full JDK rồi coi việc đóng gói đã thành công.

### 8.3. Nếu cung cấp runtime dựng sẵn

Khi dùng:

```bash
jpackage --type app-image \
  --name DemoApp \
  --module-path mods \
  --module demo.app/demo.app.Main \
  --runtime-image runtime-bind \
  --dest dist
```

`jpackage` sử dụng **custom runtime image có sẵn** từ `--runtime-image` thay vì tự liên kết runtime mới. Vì vậy, những module cần có phải **được đưa vào runtime-bind trước đó**. Không cho rằng `jpackage` sẽ tự sửa module graph của runtime mà bạn cung cấp. Hãy kiểm tra image đầu vào bằng `runtime-bind/bin/java --list-modules` và chạy launcher sau đóng gói.

**Ghi chú nền tảng:** Các gói cài đặt native và app image được tạo cho hệ điều hành mục tiêu; `jpackage` không tự cung cấp công cụ cross-platform packaging chung. Build/test trên từng platform bạn phát hành.

## 9. Phân biệt «module tồn tại» với «module đã load»

Có bốn khái niệm người học hay gộp làm một:

### 9.1. Included in image

`jlink` đã đưa module vào custom runtime. Ví dụ `java.logging` nằm trong image, có thể kiểm chứng bằng `--list-modules` của runtime tạo bằng jlink.

### 9.2. Resolved in module layer

Module resolution đã đưa module vào một layer. `ModuleLayer.boot().modules()` trả tập module trong boot layer; `findModule(name)` kiểm tra một tên. Với custom layers, dùng layer thích hợp. **Module đã resolve không đồng nghĩa toàn bộ classes của module đã được JVM khởi tạo.**

### 9.3. Class loaded

Một `Class<?>` có thể được lấy bằng `Class.forName` (trong ví dụ chính), `ClassLoader.loadClass` hoặc được JVM load theo đường dùng thực tế. `Class<?>.getModule()` cho biết class thuộc module nào; `getName()` có thể là `null` với **unnamed module** (classpath), nên khi in/report cần xử lý trường hợp này.

### 9.4. Service provider instantiated

`ServiceLoader.Provider.type()` giúp xem provider type, còn `Provider.get()`/iterator giúp tạo instance khi dùng. Quá trình này có thể ném `ServiceConfigurationError` nếu provider metadata/constructor/provider method sai hoặc dependency không dùng được.

**Cách audit đúng:** Không chỉ đọc `module-info.java` mà còn quan sát **đúng build artifact, đúng bundled runtime, đúng module layer, đúng class loader và đường gọi thật**.

## 10. Reflection: khi thiếu module khác khi thiếu quyền truy cập

Hai nhóm lỗi cần tách:

**A. Module/class không có hoặc không được resolve**

- `ClassNotFoundException` khi `Class.forName(...)` không tìm được class.
- `NoClassDefFoundError` hoặc `LinkageError` trong những tình huống phụ thuộc của class không khả dụng hoặc lỗi linking.
- Nếu module cần dùng không nằm trong runtime image, thêm **module cần thiết** khi liên kết.

**B. Class có nhưng deep reflection không được phép**

- Một class được tìm thấy qua `Class.forName` **không** nghĩa mọi private member có thể được truy cập.
- Trong JPMS, `exports` chi phối khả năng truy cập public API qua module boundary; `opens` cho phép deep reflection trên package theo phạm vi khai báo.
- `setAccessible(true)` có thể ném `java.lang.reflect.InaccessibleObjectException` nếu module/package không được mở thích hợp.
- Khi thiết kế module, ưu tiên khai báo `opens some.package to framework.module` với **đích cần thiết**, hoặc cấu hình `--add-opens` có mục đích. Không tự mở toàn bộ module/package nếu không cần.

Một snippet mô tả trong `module-info.java`:

```java
module my.app {
    requires some.framework;
    opens my.app.model to some.framework;
}
```

Đây là **ví dụ minh họa**, chỉ compile khi các module/packages tương ứng tồn tại. Nó diễn tả quyền deep reflection đối với package `my.app.model` được chỉ định, **không** bổ sung module bị thiếu vào runtime image.

**Không dùng `--add-opens` để chữa `ClassNotFoundException` do module bị jlink bỏ khỏi image.** Một flag quyền truy cập chỉ có ý nghĩa nếu module và class đích thực sự hiện diện/resolved phù hợp.

### 10.1. Khi ứng dụng có custom `ModuleLayer`

Một số plugin systems tạo layer mới ở runtime:

```java
ModuleLayer pluginLayer = /* layer do app tạo từ Configuration */;
java.util.ServiceLoader<MyService> loader =
        java.util.ServiceLoader.load(pluginLayer, MyService.class);
```

Đây là **pseudocode minh họa**, các tên `MyService` và `pluginLayer` cần được định nghĩa trong ứng dụng thật. Module ở custom layer có thể không xuất hiện trong `ModuleLayer.boot()`, nhưng vẫn được tìm qua `pluginLayer.findModule(...)`.

Đồng thời, một custom runtime image tối giản có thể **không chứa module/plugin mà app dự định tải sau khi khởi động**. Nếu plugin được đặt ngoài image, cần thiết kế module path, class loader, filesystem access và module-layer creation riêng. `--bind-services` tại link time không tự đưa vào những module chưa tồn tại trên module path ở lúc link.

## 11. `ServiceLoader` trong JAR classpath không modular

Không phải mọi app đều đã chuyển sang named modules. Với app chạy trên **classpath (unnamed module)**, cơ chế service truyền thống dùng file:

```text
META-INF/services/com.example.spi.Codec
```

Nội dung file là tên binary class của provider, ví dụ:

```text
com.example.impl.FastCodec
```

Đây là ví dụ **định dạng metadata trong JAR**, không phải tên class Java chuẩn có sẵn. Nếu JAR chứa `META-INF/services` được packaged cùng ứng dụng, `ServiceLoader` có thể tìm provider theo class loader phù hợp.

Nhưng:

- `jlink` **không tự suy ra mọi third-party classpath JAR** từ sự hiện diện của `META-INF/services` trong một artifact khác.
- `jdeps` không thay thế kiểm tra service descriptor và resource payload.
- Nếu provider class được đóng gói trong app JAR/classpath, bản thân provider không nhất thiết là một **named module** độc lập. Khi đó kiểm tra bằng `ModuleLayer.boot().findModule("provider.name")` không phản ánh trạng thái classpath provider; phải dùng `ServiceLoader` và classloader của ứng dụng.
- Với **automatic modules**, việc liên kết bằng `jlink` có những giới hạn khác so với explicit modules; nên chuẩn hóa modular artifacts hoặc cung cấp classpath JAR như app payload phù hợp thay vì giả định mọi automatic module có thể được link như module JDK.
- Khi package có thư viện service loader không modular, test thực tế bằng launcher bundled là cách an toàn nhất.

**Đừng gộp `META-INF/services` của classpath JAR với `provides ... with` trong module descriptor.** Chúng là hai cách mô tả provider trong các môi trường triển khai khác nhau.

## 12. Công cụ chẩn đoán cần biết

| Công cụ/API | Dùng để | Điều chưa chứng minh |
| --- | --- | --- |
| `jdeps --print-module-deps` | Ước lượng closure phụ thuộc tĩnh để chọn root modules | Không biết tất cả reflective class names/service providers động. |
| `jlink --suggest-providers ...` | Tìm provider modules cho một service trên module path | Không tạo image và không chứng minh provider được gọi thành công. |
| `jlink --bind-services` | Link provider modules và dependencies có thể tìm thấy | Không bảo đảm mọi plugin động ngoài module path đã được bao gồm. |
| `jlink --add-modules ...` | Chọn modules cần link như roots | Không tự cung cấp classpath payload hoặc quyền reflection. |
| `jpackage --type app-image` | Tạo app launcher + app files + runtime | Không mặc định cùng closure service across all JDK versions. |
| `runtime/bin/java --list-modules` | Xem module **có sẵn** trong custom runtime do jlink tạo | Không chứng minh class đã load. |
| `java --show-module-resolution` | In quyết định resolve modules khi khởi động | Không chứng minh một provider đã khởi tạo hay chạy tốt. |
| `ModuleLayer.boot().findModule` | Kiểm tra module được resolve ở boot layer | Không nhìn thấy mọi custom layer. |
| `ServiceLoader.load` | Tìm/khởi tạo providers theo module/classloader rules | Không tự enable missing modules hoặc thêm JAR vào image. |
| `Class.forName` / `Class.getModule` | Chứng minh class được tìm/tải và xem module của nó | Không tự bảo đảm deep reflection/private access. |
| `-Xlog:class+load=info` | Quan sát JVM thực sự load classes nào (nhiều output) | Không thay thế kiểm tra runtime module closure/uses/provides. |

Ví dụ muốn xem module resolution:

```bash
java --show-module-resolution \
  --module-path mods \
  --module demo.app/demo.app.Main
```

Output của option `--show-module-resolution` **phụ thuộc JDK/module path**, không nên hardcode toàn bộ log làm stdout mẫu. Mục tiêu là kiểm tra module nào được resolve nhờ dependency và service binding.

Ví dụ muốn log class loading từ runtime có launcher `java`:

```bash
./runtime-explicit/bin/java \
  -Xlog:class+load=info \
  --module demo.app/demo.app.Main
```

Log này có thể rất lớn; dùng tạm khi chẩn đoán. Dòng class load cho provider chỉ có khi code thực sự yêu cầu tải class; danh sách module resolved và class-loaded là hai điều khác nhau.

## 13. Quy trình kiểm tra một app image trong CI

Có thể tổ chức QA từng lớp:

### Giai đoạn A — Phân tích build artifacts

1. Chạy test unit bình thường trên full JDK.
2. Chạy `jdeps` với đúng class/module path để thu static dependencies.
3. Tìm các điểm `ServiceLoader.load`, `Class.forName`, `ClassLoader.loadClass` và config nêu tên class/provider.
4. Kiểm tra `module-info.java` của consumer có `uses` và provider có `provides ... with` đúng service.
5. Kiểm tra third-party JAR có `META-INF/services` hoặc plugin declarations nếu dùng classpath.

### Giai đoạn B — Dựng runtime riêng

1. Liệt kê modules cần thiết: closure tĩnh **cộng** providers/reflection dependencies đã được xác nhận.
2. Chọn `--add-modules provider.name` khi biết cụ thể hoặc `--bind-services` khi muốn link toàn bộ service providers có thể quan sát.
3. Build image trên đúng JDK release/architecture; dùng `jlink --list-plugins` nếu muốn xem options có hỗ trợ.
4. Xác minh image module inventory bằng `bin/java --list-modules` khi launcher runtime còn có.
5. Chạy các smoke tests của service và reflection bằng **runtime thu gọn**, không chỉ bằng full JDK.

### Giai đoạn C — Đóng app image

1. Gọi `jpackage --type app-image` với cấu hình rõ ràng; **trên JDK 25+ kiểm tra mặc định service binding đã thay đổi**.
2. Chạy **launcher thật của app image** trên từng hệ điều hành/kiến trúc mục tiêu.
3. Trong test, assert danh sách provider tối thiểu (hoặc provider cụ thể bắt buộc), không chỉ assert launcher exit code 0.
4. Chạy đường reflection chính với class names thật từ config/feature toggles.
5. Kiểm thử quyền deep reflection ở framework cần dùng, tránh chỉ kiểm tra `Class.forName`.
6. Ghi lại JDK build version, module list và kết quả smoke tests như build evidence.

### Giai đoạn D — Kiểm tra tính năng ít khi chạy

1. Khởi chạy các code paths có plugin/provider optional: locale, logging backend, JDBC, XML, crypto provider, UI adapter, serializer...
2. Nếu một class chỉ được tạo khi có cấu hình cụ thể, tạo test với cấu hình đó.
3. Trường hợp thiếu module, phân biệt module **không packaged** với module **packaged nhưng không resolved**.
4. Không làm việc theo kiểu «thêm tất cả module JDK cho chắc» nếu mục tiêu của app image là runtime gọn và kiểm soát attack surface.

## 14. Xử lý lỗi khi thực tế không thấy service hoặc class

| Biểu hiện | Nguyên nhân có thể | Điều cần kiểm tra |
| --- | --- | --- |
| `ServiceLoader.load(...).stream()` rỗng | Provider không được link/resolve, sai service name, sai layer/classloader | `--bind-services` hoặc explicit provider module, `uses/provides`, module path, app launcher. |
| `ServiceConfigurationError` | Thiếu `uses` trong named consumer, provider metadata/constructor sai, provider không tải/khởi tạo được | Descriptor, implementation, nguyên nhân lồng trong exception và provider API. |
| `ClassNotFoundException` qua `Class.forName` | Module/JAR không trong runtime hoặc không hiển thị với loader/resolution hiện tại | Image inventory, module layer, class loader, `--add-modules`, config name. |
| `NoClassDefFoundError` / `LinkageError` | Một dependency của class không sẵn, incompatibility/linkage lỗi | Dependency graph, bytecode/JDK version, packaged JARs và module resolution. |
| `InaccessibleObjectException` | Deep reflection bị JPMS encapsulation chặn | `opens`/`--add-opens` đúng package và target module. |
| Full JDK chạy, app image thất bại | JDK đầy đủ có modules/paths khác bundled runtime | Test launcher và module list của image; kiểm tra service-binding default JDK25+. |
| `ModuleLayer.boot().findModule` empty | Module không resolved ở boot, hoặc nằm trong custom layer | Layer thực tế, root modules, `ModuleLayer` tạo động. |
| `jdeps` không báo module thực sự cần | Dependency chỉ được chọn động qua String/service/config | Bổ sung dynamic dependency inventory và integration tests. |
| Service tìm thấy nhưng chạy lỗi | Provider instance tạo được nhưng logic/dependency/config sai | Gọi phương thức provider thật, phân tích exception và resources đã đóng gói. |
| Image phình to bất ngờ sau `--bind-services` | Service binding kéo thêm provider modules/dependencies | So sánh `--list-modules`, chọn explicit provider nếu phù hợp. |

**Chẩn đoán theo thứ tự:** (1) artifact có module/provider JAR hay không; (2) runtime có module và module được resolve ở layer nào; (3) `ServiceLoader`/`Class.forName` nhìn thấy class hay không; (4) instantiation, reflective access và hành vi nghiệp vụ có thành công không.

## 15. Những lưu ý quan trọng khi đổi JDK và quản lý runtime

### 15.1. Không dựa vào default giữa các release

Với JDK 17/21/25/26, toolchain có thể có các thay đổi về linking và packaging. Thay đổi JDK25 về **jpackage service binding** là ví dụ rõ ràng. Khi nâng cấp JDK build:

- Đọc release notes mới của `jpackage`, `jlink`, `ServiceLoader`.
- Giữ các flags quan trọng trong build script versioned, thay vì phụ thuộc vào defaults không được ghi nhận.
- Chạy lại smoke tests cho provider/reflection trên image mới.
- So sánh module inventory và kích thước giữa hai build, nhưng không dùng kích thước nhỏ hơn làm thước đo duy nhất về correctness.
- Nếu đưa một **prebuilt runtime** qua `--runtime-image`, cần tự cập nhật runtime đó khi JDK có bản vá bảo mật. `jlink` không làm cập nhật tự động sau khi image đã được phát hành.

### 15.2. Security và strong encapsulation

- Hạn chế mở package/module qua `opens`; tránh `--add-opens ALL-UNNAMED` bừa bãi chỉ để chạy một framework lỗi cấu hình.
- Không load plugin/provider từ nguồn không đáng tin; `ServiceLoader` có thể dẫn đến chạy code của implementation.
- Kiểm tra JAR resources, cấu hình provider và quyền filesystem trong app image.
- Cần version pinning/kiểm thử đối với providers vì binary compatibility ảnh hưởng việc load/khởi tạo.
- App image có runtime riêng nên phải có cơ chế phát hành bản cập nhật/các bản vá, không mặc định nó kế thừa JDK vá trên máy người dùng.

### 15.3. Phụ thuộc tùy chọn không phải lỗi mọi lúc

Không phải mọi module provider đều phải có trong mọi image. Nếu app có **optional features**, có thể chọn subset providers theo edition/platform. Điều quan trọng là **tuyên bố rõ tính năng bắt buộc và tính năng tùy chọn**, rồi test đúng môi trường:

- Bắt buộc: assert provider/class phải có, không rỗng.
- Tùy chọn: nếu thiếu phải có fallback được thiết kế và báo trạng thái rõ.
- Phụ thuộc native: module có mặt nhưng native library/resource không có cũng có thể làm provider fail.
- Khác OS/architecture: đóng gói và thử trên từng platform thay vì chép image giữa hệ điều hành.

## 16. Bài tập tự kiểm tra

### Bài 1 — Vì sao provider bị thiếu?

`demo.app` chỉ `requires demo.api; uses demo.spi.Greeter`, còn `demo.provider` khai báo `provides ... with`. Bạn chạy `jlink --add-modules demo.app` không `--bind-services`.

**Đáp án:** Closure của `requires` chỉ cần `demo.api`, không buộc đưa `demo.provider` vào image. `ServiceLoader` có thể trả rỗng. Thêm provider như một root (`--add-modules demo.app,demo.provider`) hoặc sử dụng `--bind-services`.

### Bài 2 — `ModuleLayer.boot` cho thấy provider, thế đã có instance chưa?

**Đáp án:** Chưa. Module đã được resolve nhưng provider có thể chưa được `ServiceLoader` tìm và khởi tạo. Kiểm tra `ServiceLoader.Provider.type()` rồi thực sự gọi provider trong đường chạy test.

### Bài 3 — `jdeps` chỉ báo `java.base` nhưng `Class.forName` lỗi

Một class chỉ gọi `Class.forName("java.util.logging.Logger")`. Image tạo từ `java.base`.

**Đáp án:** `jdeps` không nhìn ra module qua tên String như phụ thuộc tĩnh. Thêm `java.logging` vào root modules của `jlink` và chạy lại trên custom runtime; bài đã đưa ví dụ có stdout kiểm chứng.

### Bài 4 — `--add-opens` có sửa thiếu module không?

**Đáp án:** Không. `--add-opens` sửa quyền deep reflection khi module/class **đã hiện diện/resolved**. Nếu `ClassNotFoundException` do module không tồn tại trong runtime, cần đóng gói/resolve module trước.

### Bài 5 — Tại sao cần `uses`?

Consumer là named module gọi `ServiceLoader.load(Greeter.class)`. Nó chỉ `requires demo.api` mà không có `uses demo.spi.Greeter`.

**Đáp án:** Với named module, service loader yêu cầu khai báo `uses` tương ứng; thiếu có thể dẫn tới `ServiceConfigurationError`. `requires` nhằm truy cập API, không thay cho `uses`.

### Bài 6 — Khi nào dùng `--bind-services`?

**Đáp án:** Khi muốn jlink kéo các provider modules tìm thấy cho services của module graph; cần kiểm tra image size và providers thực tế. Nếu chỉ cần một provider xác định, có thể explicit `--add-modules demo.provider`.

### Bài 7 — Điều gì thay đổi từ JDK 25?

**Đáp án:** `jpackage` không còn service-bind mặc định vào runtime do nó sinh. Khi nâng JDK, phải thêm `--bind-services` trong `--jlink-options` hoặc chỉ định các provider modules bắt buộc, rồi smoke-test app image thật.

### Bài 8 — Vì sao phải chạy launcher app image?

**Đáp án:** Full JDK của máy build có thể chứa modules và service providers mà runtime rút gọn không chứa. Chỉ launcher đóng gói mới kiểm tra chính xác tập module/paths/options người dùng nhận.

### Bài 9 — Module được dùng trong custom `ModuleLayer` có hiện trong boot layer không?

**Đáp án:** Không nhất thiết. `ModuleLayer.boot()` chỉ mô tả boot layer; cần kiểm tra layer custom hoặc `Class.getModule().getLayer()`.

### Bài 10 — Class tìm được qua reflection nhưng truy cập private method bị lỗi

**Đáp án:** Đây có thể là lỗi encapsulation, không phải lỗi thiếu module. Xem `opens package to module` hoặc `--add-opens` có giới hạn theo nhu cầu, và kiểm tra exception cụ thể.

### Bài 11 — Thấy provider type nhưng lời gọi provider lỗi

**Đáp án:** `Provider.type()` chứng minh metadata/type khả dụng, không bảo đảm khởi tạo và chạy nghiệp vụ. Thử `Provider.get()` hoặc phương thức service, kiểm tra dependency/config/resource của provider.

### Bài 12 — `jpackage --runtime-image` có tự tải provider module còn thiếu không?

**Đáp án:** Không. Nó sử dụng runtime đã tạo. Nếu custom runtime thiếu provider/reflection module, phải dựng lại runtime có module cần thiết rồi mới đóng gói.

## 17. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): app image, runtime requirements và **thay đổi JDK 25 không service-bind mặc định**.
2. [JDK 25 Release Notes — `jpackage` service bindings (JDK-8345185)](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): hướng dẫn khôi phục hành vi qua `--jlink-options` và `--bind-services`.
3. [Java SE 25 — `jpackage` tool specification](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): `--type app-image`, `--add-modules`, `--runtime-image`, `--jlink-options`.
4. [Java SE 25 — `jlink` tool specification](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html): `--bind-services`, `--suggest-providers`, `--add-modules` và module image closure.
5. [Java SE 25 — `jdeps` tool specification](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html): phân tích dependencies và `--print-module-deps`, đầu vào của jlink.
6. [Java SE 25 — `java` launcher specification](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `--list-modules`, `--show-module-resolution`, `--add-modules` và module path.
7. [Java SE 25 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): `uses`/`provides`, cách khám phá provider, `Provider.type`/`get` và module layers.
8. [Java SE 25 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): boot layer, `findModule`, custom module layers và resolution.
9. [Java SE 25 — `Module`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `Class.getModule`, `Module.getName`, `getLayer`, access/readability.
10. [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` trở thành công cụ chính thức trong Java 16, sau giai đoạn incubating của Java 14/15.
11. [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): tham chiếu runtime tối thiểu của các ví dụ `--release 17`.
12. [Java SE 17 — `jlink`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): các tùy chọn `--bind-services` và `--add-modules` trong release tối thiểu được sử dụng.

**Ghi nhớ cuối bài:** **`jdeps` xác định dependency tĩnh**, không thể khẳng định đầy đủ các module chỉ được dùng qua `ServiceLoader` hoặc `Class.forName`. **`jlink`/`jpackage` quyết định module nào có trong bundled runtime**, còn **`ModuleLayer`, `ServiceLoader` và reflection** giúp xác minh runtime thật sự giải quyết và sử dụng chúng. Từ **JDK 25**, phải chủ động kiểm tra service binding của `jpackage`; tạo image xong luôn chạy **launcher đóng gói**, thử provider và class được gọi động, không chỉ dựa vào việc build không báo lỗi.