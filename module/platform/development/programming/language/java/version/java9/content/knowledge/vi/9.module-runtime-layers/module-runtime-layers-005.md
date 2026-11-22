# Phân giải bằng Configuration và lựa chọn mô-đun gốc

## 1. Configuration nằm ở đâu trong JPMS?

Java Platform Module System (JPMS) chia quá trình khởi tạo mô-đun thành các bước có trách nhiệm riêng:

1. **ModuleFinder** tìm các mô-đun có thể quan sát được từ module path hoặc runtime image.
2. **Root modules** xác định những mô-đun bắt đầu quá trình phân giải.
3. **Configuration** chứa đồ thị mô-đun đã phân giải: các root và những phụ thuộc bắt buộc được tìm thấy theo module descriptor.
4. **ModuleLayer** tạo lớp mô-đun lúc chạy, gắn các mô-đun trong Configuration với class loader.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["ModuleFinder: tìm mô-đun"] --> B["Chọn root module names"]
    B --> C["Configuration.resolve / resolveAndBind"]
    C --> D["Configuration: đồ thị đã phân giải"]
    D --> E["ModuleLayer: tạo lớp mô-đun"]
    E --> F["ClassLoader và truy cập mô-đun lúc chạy"]
~~~

**Configuration không tự tải hoặc khởi tạo class.** Nó mô tả kết quả phân giải và các quan hệ phụ thuộc. Muốn dùng các mô-đun trong một lớp chạy mới, ứng dụng tiếp tục tạo ModuleLayer từ Configuration đó.

Các API trong bài vẫn là API JPMS hiện hành. Ví dụ dùng cú pháp Java 17+, nhưng phần phân giải bằng Configuration và ModuleLayer áp dụng từ Java 9 trở lên.

## 2. ModuleFinder: tìm mô-đun ở đâu?

ModuleFinder là nguồn tra cứu các mô-đun. Nó không quyết định mô-đun nào sẽ trở thành root.

Các cách tạo finder thường dùng:

- **ModuleFinder.of(Path...)**: tìm mô-đun trong các đường dẫn được chỉ định. Đường dẫn có thể là modular JAR hoặc thư mục chứa các mô-đun.
- **ModuleFinder.ofSystem()**: tìm các mô-đun thuộc runtime image của JDK.
- **ModuleFinder.of()**: tạo finder rỗng, không tìm thấy mô-đun nào.
- **ModuleFinder.compose(finders...)**: kết hợp nhiều finder thành một nguồn tra cứu.

Hai phương thức hữu ích để kiểm tra finder:

- **find(moduleName)** trả về Optional<ModuleReference> cho tên mô-đun được yêu cầu.
- **findAll()** trả về tập các ModuleReference mà finder tìm thấy.

Ví dụ:

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("mlib"));

Optional<ModuleReference> reference =
        finder.find("com.acme.orders");

System.out.println(reference.isPresent());
~~~

Tên truyền vào find là tên mô-đun trong module descriptor, không phải tên package hay tên tệp JAR. Với explicit module, tên được khai báo trong module-info.java. Với automatic module, tên được suy ra theo quy tắc đặt tên của module path hoặc thuộc tính Automatic-Module-Name.

## 3. Root module là gì?

Root module là mô-đun được chọn làm điểm bắt đầu để resolver xây dựng đồ thị phụ thuộc. Root được chỉ định bằng **tên mô-đun**, ví dụ:

~~~java
Set<String> roots = Set.of("com.acme.orders");
~~~

Nếu orders khai báo requires com.acme.common, resolver sẽ tìm và đưa common vào Configuration khi tìm thấy mô-đun đó ở các nguồn hợp lệ. Không cần đưa mọi dependency vào roots.

Có thể chọn nhiều root cùng lúc:

~~~java
Set<String> roots = Set.of(
        "com.acme.orders",
        "com.acme.reporting"
);
~~~

Mỗi root được phân giải cùng các phụ thuộc cần thiết. Một mô-đun được thêm làm root dù không được root khác yêu cầu trực tiếp vẫn có thể xuất hiện trong Configuration.

Cần phân biệt ba khái niệm:

- **Root**: điểm khởi đầu do ứng dụng hoặc launcher chọn.
- **Dependency**: mô-đun được resolver tìm thấy vì một mô-đun khác khai báo requires.
- **Observable module**: mô-đun nằm trong phạm vi các nguồn mà resolver được phép tra cứu.

Một tên root không tìm thấy trong các nguồn có thể quan sát sẽ làm quá trình phân giải thất bại. Chọn root không có nghĩa là ép resolver bỏ qua dependency bị thiếu hoặc xung đột.

## 4. Configuration.resolve() phân giải đồ thị như thế nào?

Configuration là đối tượng bất biến đại diện cho kết quả phân giải. API thường dùng khi tạo một lớp mô-đun con là phương thức instance:

~~~java
Configuration parentConfiguration =
        ModuleLayer.boot().configuration();

ModuleFinder before = ModuleFinder.of(Path.of("mlib"));
ModuleFinder after = ModuleFinder.of();

Set<String> roots = Set.of("com.acme.orders");

Configuration configuration =
        parentConfiguration.resolve(before, after, roots);
~~~

Ba tham số có ý nghĩa:

- **before**: finder được ưu tiên tra cứu trước các parent Configuration.
- **after**: finder được tra cứu sau các parent Configuration.
- **roots**: tập tên mô-đun bắt đầu quá trình phân giải.

Thứ tự tra cứu cho một mô-đun là: finder before, các parent Configuration, rồi finder after. Cách sắp xếp này hữu ích khi tạo lớp mô-đun con: đặt mô-đun mới trong before, dùng boot layer làm parent, và để after rỗng nếu không có nguồn dự phòng.

Khi gọi resolve, resolver thực hiện các công việc chính:

1. Tìm các root trong các nguồn có thể quan sát.
2. Đọc module descriptor của từng mô-đun đã tìm thấy.
3. Theo các khai báo requires để tìm phụ thuộc đệ quy.
4. Kiểm tra tính nhất quán của đồ thị mô-đun.
5. Trả về Configuration nếu đồ thị hợp lệ.

Các khai báo trong module descriptor ảnh hưởng trực tiếp đến đồ thị:

- **requires X**: X là dependency bắt buộc ở runtime.
- **requires transitive X**: X vẫn là dependency; đồng thời các mô-đun đọc mô-đun khai báo này cũng được hưởng khả năng đọc X theo quy tắc readability.
- **requires static X**: dependency được yêu cầu lúc biên dịch nhưng có thể vắng mặt khi chạy. Nếu X không có ở runtime, resolver không bắt buộc phải tìm thấy X; ứng dụng vẫn phải tránh sử dụng trực tiếp các kiểu của X khi X vắng mặt.
- **exports** và **opens** điều khiển khả năng truy cập package; chúng không chọn root.
- **uses** và **provides** khai báo quan hệ dịch vụ; chúng liên quan đến service binding được trình bày ở phần sau.

Nếu có nhiều parent Configuration, có thể dùng overload static của Configuration.resolve và truyền danh sách parent. Trường hợp phổ biến chỉ có một parent thì phương thức instance dễ đọc và thể hiện rõ Configuration cha đang được mở rộng.

## 5. resolve() và resolveAndBind() khác nhau thế nào?

**Configuration.resolve()** giải quyết các root cùng dependency theo requires. Nó không tự thêm một mô-đun provider chỉ vì mô-đun khác khai báo uses một service mà provider đó triển khai.

**Configuration.resolveAndBind()** thực hiện phân giải dependency và thêm bước service binding. Resolver tìm các mô-đun provider có khai báo provides tương ứng với service được các mô-đun trong đồ thị sử dụng. Provider được tìm thấy có thể kéo theo dependency riêng của nó; các dependency đó tiếp tục được phân giải.

Ví dụ module descriptor của mô-đun sử dụng service:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingProvider;
}
~~~

Module descriptor của provider:

~~~java
module com.acme.provider {
    requires com.acme.spi;
    provides com.acme.spi.GreetingProvider
        with com.acme.provider.DefaultGreetingProvider;
}
~~~

Nếu provider nằm trong các finder có thể quan sát, resolveAndBind có thể đưa provider vào Configuration dù app không khai báo requires com.acme.provider.

Ví dụ gọi API:

~~~java
Configuration configuration =
        ModuleLayer.boot().configuration()
                .resolveAndBind(
                        ModuleFinder.of(Path.of("mlib")),
                        ModuleFinder.of(),
                        Set.of("com.acme.app")
                );
~~~

Khi tạo layer và tải provider, có thể dùng ServiceLoader với layer đó:

~~~java
ServiceLoader<GreetingProvider> providers =
        ServiceLoader.load(layer, GreetingProvider.class);
~~~

Service binding hữu ích khi muốn chọn provider theo module path và service contract. Nếu ứng dụng không dùng cơ chế service hoặc provider đã là dependency trực tiếp, resolve thường là đủ.

## 6. Chọn root từ Java launcher

Khi chạy ứng dụng theo module, launcher chọn mô-đun chính làm root:

~~~bash
java --module-path mlib \
     -m com.acme.orders/com.acme.orders.Main
~~~

Phần trước dấu gạch chéo là tên mô-đun; phần sau là tên lớp main. Nếu bỏ phần lớp main, launcher dùng quy tắc xác định main class của mô-đun khi có khai báo phù hợp.

Có thể thêm root độc lập với mô-đun chính bằng **--add-modules**:

~~~bash
java --module-path mlib \
     --add-modules com.acme.metrics \
     -m com.acme.orders/com.acme.orders.Main
~~~

Các giá trị đặc biệt thường dùng của --add-modules:

- **ALL-DEFAULT**: các mô-đun hệ thống thuộc tập mặc định của launcher.
- **ALL-SYSTEM**: tất cả mô-đun hệ thống có thể quan sát.
- **ALL-MODULE-PATH**: tất cả mô-đun tìm thấy trên module path.

Các root bổ sung vẫn phải có mặt trong phạm vi mô-đun có thể quan sát. Resolver sẽ đưa dependency của chúng vào đồ thị theo quy tắc thông thường.

**--limit-modules** có mục đích khác: giới hạn tập mô-đun có thể quan sát và các dependency được phép xem xét. Nó không phải cách thay thế trực tiếp cho việc chọn root bằng -m hoặc --add-modules.

Khi cần xem launcher đang phân giải mô-đun nào, có thể bật:

~~~bash
java --show-module-resolution \
     --module-path mlib \
     -m com.acme.orders/com.acme.orders.Main
~~~

Thông tin hiển thị giúp xác định root và các dependency được phân giải trong lần chạy đó.

## 7. Tạo ModuleLayer từ Configuration

Sau khi có Configuration hợp lệ, ứng dụng có thể tạo một lớp mô-đun con. Với một parent layer:

~~~java
ModuleLayer parent = ModuleLayer.boot();

ModuleLayer.Controller controller =
        parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer layer = controller.layer();
~~~

Một số lựa chọn tạo layer:

- **defineModulesWithOneLoader**: các mô-đun mới dùng chung một class loader.
- **defineModulesWithManyLoaders**: mỗi mô-đun mới có class loader riêng.
- **defineModules**: cung cấp hàm ánh xạ tên mô-đun sang class loader để kiểm soát cách phân bổ loader.

Đối số parent loader là loader cha của các loader được tạo cho layer mới. Chọn chiến lược loader theo yêu cầu cô lập, khả năng nạp lớp và tương tác giữa các mô-đun.

Có thể kiểm tra layer sau khi tạo:

~~~java
Optional<Module> appModule =
        layer.findModule("com.acme.orders");

ClassLoader appLoader =
        layer.findLoader("com.acme.orders");

System.out.println(appModule.isPresent());
System.out.println(appLoader);
~~~

**ModuleLayer.Controller** là đối tượng điều khiển layer vừa tạo. Ngoài việc lấy layer qua layer(), controller còn cung cấp các thao tác có chủ đích để bổ sung quan hệ đọc, export hoặc open ở runtime. Chỉ nên dùng các thao tác này khi kiến trúc thực sự cần quyền truy cập động; thiết kế module descriptor rõ ràng thường dễ bảo trì hơn.

Tạo Configuration và tạo ModuleLayer là hai bước riêng. Configuration có thể được kiểm tra trước; nếu chỉ cần phân tích đồ thị phụ thuộc thì chưa cần tạo layer hoặc tải class.

## 8. Ví dụ hoàn chỉnh: chọn một root và tự động phân giải dependency

Ví dụ tạo hai mô-đun. Mô-đun app là root; mô-đun API được đưa vào Configuration vì app khai báo requires.

Cấu trúc thư mục:

~~~text
project/
├── src/
│   ├── com.acme.greet.api/
│   │   ├── module-info.java
│   │   └── com/acme/greet/api/Greeter.java
│   └── com.acme.greet.app/
│       ├── module-info.java
│       └── com/acme/greet/app/Main.java
└── ResolveModules.java
~~~

**Mô-đun API**

Tệp src/com.acme.greet.api/module-info.java:

~~~java
module com.acme.greet.api {
    exports com.acme.greet.api;
}
~~~

Tệp src/com.acme.greet.api/com/acme/greet/api/Greeter.java:

~~~java
package com.acme.greet.api;

public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

**Mô-đun ứng dụng**

Tệp src/com.acme.greet.app/module-info.java:

~~~java
module com.acme.greet.app {
    requires com.acme.greet.api;
}
~~~

Tệp src/com.acme.greet.app/com/acme/greet/app/Main.java:

~~~java
package com.acme.greet.app;

import com.acme.greet.api.Greeter;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "JPMS" : args[0];
        System.out.println(new Greeter().greet(name));
    }
}
~~~

**Biên dịch và đóng gói**

Từ thư mục project, tạo thư mục mods và mlib. Trên Linux/macOS:

~~~bash
mkdir -p mods mlib
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force mods, mlib
~~~

Biên dịch hai mô-đun:

~~~bash
javac --module-source-path src -d mods \
      -m com.acme.greet.api,com.acme.greet.app
~~~

Đóng gói từng mô-đun thành modular JAR:

~~~bash
jar --create --file mlib/com.acme.greet.api.jar \
    -C mods/com.acme.greet.api .

jar --create --file mlib/com.acme.greet.app.jar \
    -C mods/com.acme.greet.app .
~~~

**Chương trình phân giải và tạo layer**

Tệp ResolveModules.java nằm ngoài hai mô-đun, trong unnamed module của classpath. Chương trình chọn duy nhất app làm root. API được resolver tìm thấy nhờ khai báo requires của app.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

public class ResolveModules {
    public static void main(String[] args) {
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder before = ModuleFinder.of(Path.of("mlib"));
        ModuleFinder after = ModuleFinder.of();

        Set<String> roots = Set.of("com.acme.greet.app");

        Configuration configuration = parent.configuration()
                .resolve(before, after, roots);

        String resolvedNames = configuration.modules().stream()
                .map(ResolvedModule::name)
                .sorted()
                .collect(Collectors.joining(", "));

        System.out.println("Child configuration: " + resolvedNames);

        ModuleLayer.Controller controller =
                parent.defineModulesWithOneLoader(
                        configuration,
                        ClassLoader.getSystemClassLoader()
                );

        ModuleLayer layer = controller.layer();

        System.out.println("App in child layer: "
                + layer.findModule("com.acme.greet.app").isPresent());
        System.out.println("API in child layer: "
                + layer.findModule("com.acme.greet.api").isPresent());
    }
}
~~~

Biên dịch và chạy chương trình phân giải:

~~~bash
javac ResolveModules.java
java -cp . ResolveModules
~~~

Stdout:

~~~text
Child configuration: com.acme.greet.api, com.acme.greet.app
App in child layer: true
API in child layer: true
~~~

Có thể chạy ứng dụng trực tiếp bằng launcher để kiểm tra main class và dependency:

~~~bash
java --module-path mlib \
     -m com.acme.greet.app/com.acme.greet.app.Main
~~~

Stdout:

~~~text
Hello, JPMS!
~~~

Kết quả cho thấy chỉ cần chọn com.acme.greet.app làm root; resolver tự tìm com.acme.greet.api vì quan hệ requires. Configuration con chỉ liệt kê các mô-đun được phân giải trong cấu hình con. java.base thuộc boot layer cha nên không xuất hiện trong danh sách này.

## 9. Kiểm tra Configuration khi debug

Một số API giúp quan sát kết quả:

- **configuration.modules()**: tập ResolvedModule thuộc Configuration hiện tại.
- **configuration.parents()**: các Configuration cha.
- **configuration.findModule(name)**: tìm một ResolvedModule theo tên.
- **ResolvedModule.name()**: tên mô-đun đã phân giải.
- **ResolvedModule.reference()**: ModuleReference tương ứng, có thể dùng để đọc descriptor.
- **ModuleLayer.modules()**: các Module đã được định nghĩa trong layer.
- **ModuleLayer.findModule(name)**: tìm Module trong layer.
- **ModuleLayer.findLoader(name)**: lấy class loader của mô-đun trong layer.

Khi debug, nên kiểm tra theo thứ tự:

1. Finder có tìm thấy đúng tên mô-đun không?
2. Tên root có đúng với tên trong module descriptor không?
3. Các khai báo requires có được đáp ứng từ finder hoặc parent Configuration không?
4. Có package bị chia sẻ xung đột giữa các mô-đun trong cùng đồ thị không?
5. Nếu dùng service, mô-đun client đã khai báo uses và provider đã khai báo provides chưa?
6. Configuration đã hợp lệ nhưng lỗi chỉ xuất hiện khi tạo layer hay tải class? Khi đó cần kiểm tra lựa chọn class loader, parent layer và quy tắc truy cập package.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| FindException | Finder không tìm thấy mô-đun, đường dẫn sai hoặc mô-đun không hợp lệ | Kiểm tra module path, tên mô-đun và module descriptor |
| ResolutionException | Dependency bắt buộc không được tìm thấy hoặc đồ thị có xung đột | Kiểm tra requires, các parent Configuration và các mô-đun trùng package |
| Root không xuất hiện trong Configuration | Chọn nhầm tên hoặc root không thuộc nguồn có thể quan sát | So sánh root với tên mô-đun trong descriptor và kiểm tra finder |
| Provider không được đưa vào đồ thị | Chỉ gọi resolve, thiếu uses/provides hoặc provider không nằm trong nguồn tra cứu | Kiểm tra service descriptor và cân nhắc resolveAndBind |
| Module có trong Configuration nhưng không tìm thấy class | Chưa tạo layer, dùng sai layer/loader hoặc class không thuộc mô-đun mong muốn | Kiểm tra ModuleLayer, findModule và findLoader |
| Lỗi khi tạo layer | Cấu hình loader hoặc quan hệ giữa các mô-đun không phù hợp | Kiểm tra API defineModules được chọn và parent loader |

Không nên xử lý lỗi bằng cách thêm tất cả mô-đun vào roots một cách tùy tiện. Việc đó có thể che khuất root thực sự, làm đồ thị lớn hơn và kéo thêm dependency không cần thiết. Hãy xác định mô-đun khởi đầu theo chức năng ứng dụng, sau đó để resolver xử lý dependency theo module descriptor.

## 11. Quy trình lựa chọn root trong thực tế

Khi dùng API JPMS để tạo lớp mô-đun động:

1. Xác định chức năng cần chạy và chọn đúng tên mô-đun làm root.
2. Tạo ModuleFinder cho các mô-đun của ứng dụng.
3. Chọn parent Configuration phù hợp, thường là Configuration của boot layer.
4. Gọi resolve hoặc resolveAndBind tùy ứng dụng có cần service binding hay không.
5. Kiểm tra danh sách ResolvedModule để xác nhận đồ thị.
6. Tạo ModuleLayer với chiến lược class loader phù hợp.
7. Dùng layer để tìm mô-đun, tải lớp hoặc nạp service provider.

Root xác định phạm vi bắt đầu; requires xác định dependency thông thường; resolveAndBind bổ sung provider cho service; ModuleLayer biến đồ thị đã phân giải thành môi trường mô-đun lúc chạy. Nắm rõ ranh giới của bốn thành phần này giúp kiểm soát module path, dependency và việc nạp mô-đun động một cách có chủ đích.
