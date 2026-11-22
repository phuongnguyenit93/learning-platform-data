# Hồ sơ hoàn chỉnh: descriptor, graph, service, layer, image và kiểm chứng

## 1. Mục tiêu và phạm vi

Một ứng dụng modular hoàn chỉnh cần nhiều phần phối hợp:

- **Module descriptor:** khai báo dependency, package API và service contract.
- **Module graph:** xác định module nào được resolve và quan hệ giữa chúng.
- **Service:** tách consumer khỏi implementation provider bằng `uses`/`provides`.
- **Module layer:** xác định nơi module được nạp; có thể dùng boot layer hoặc tạo child layer cho plugin.
- **Runtime image:** đóng gói JDK runtime cùng các module ứng dụng cần thiết bằng `jlink`.
- **Verification:** kiểm tra descriptor, dependency, service discovery, module resolution và image sau khi build.

Bài này dựng một ví dụ end-to-end dùng ba module: SPI, application và provider. Sau đó mở rộng sang hai cách triển khai: provider nằm trong boot layer và provider được nạp vào child layer riêng. Cuối cùng tạo runtime image tĩnh hoặc image có plugin ngoài.

## 2. Cấu trúc project

Ví dụ dùng dịch vụ `GreetingService`. Consumer cần tạo lời chào; provider cung cấp cách thực hiện.

Cấu trúc source:

```text
project/
├── src/
│   ├── com.acme.spi/
│   │   ├── module-info.java
│   │   └── com/acme/spi/GreetingService.java
│   ├── com.acme.app/
│   │   ├── module-info.java
│   │   └── com/acme/app/Main.java
│   └── com.acme.provider.en/
│       ├── module-info.java
│       └── com/acme/provider/en/EnglishGreeting.java
├── out/
├── mods/
├── plugins/
└── image/
```

Ba module có trách nhiệm riêng:

- `com.acme.spi` sở hữu service interface.
- `com.acme.app` là consumer, chỉ phụ thuộc vào SPI.
- `com.acme.provider.en` triển khai service và đăng ký implementation.

## 3. Module descriptor và service contract

### SPI module

Tệp `src/com.acme.spi/module-info.java`:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

Tệp `src/com.acme.spi/com/acme/spi/GreetingService.java`:

```java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
```

Package được export vì consumer và provider cần tham chiếu interface. SPI không cần biết implementation nằm ở module nào.

### Provider module

Tệp `src/com.acme.provider.en/module-info.java`:

```java
module com.acme.provider.en {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.en.EnglishGreeting;
}
```

Tệp `src/com.acme.provider.en/com/acme/provider/en/EnglishGreeting.java`:

```java
package com.acme.provider.en;

import com.acme.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Provider cần đọc SPI để triển khai interface. Với dạng provider class được khai báo trực tiếp bằng `provides ... with ...`, class triển khai phải public và có public constructor không tham số. Package implementation không cần export nếu consumer không gọi class provider trực tiếp.

### Consumer module

Tệp `src/com.acme.app/module-info.java`:

```java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.GreetingService;
}
```

Consumer khai báo `requires` để đọc service interface và `uses` để thông báo nhu cầu tìm provider. Nó không khai báo `requires com.acme.provider.en`, do đó không phụ thuộc trực tiếp vào implementation.

Tệp `src/com.acme.app/com/acme/app/Main.java`:

```java
package com.acme.app;

import com.acme.spi.GreetingService;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Java";

        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        boolean found = false;
        for (GreetingService service : services) {
            found = true;
            System.out.println(service.greet(name));
        }

        if (!found) {
            throw new IllegalStateException(
                    "No GreetingService provider was found");
        }
    }
}
```

Kết quả khi có provider tiếng Anh:

```text
Hello, Java!
```

## 4. Đọc module graph trước khi build

Quan hệ giữa các module:

```text
                    requires
com.acme.app ----------------------> com.acme.spi
     |                                     ^
     | uses GreetingService                | requires
     |                                     |
     + - - service binding - - > com.acme.provider.en
                                           |
                                           +-- provides GreetingService
```

Có hai loại quan hệ cần phân biệt:

- `requires` tạo dependency và readability giữa module.
- `uses`/`provides` mô tả quan hệ dịch vụ. Service binding có thể đưa provider vào graph mà không cần consumer phụ thuộc trực tiếp vào provider.

Module graph không phải call graph. Việc một module được resolve không có nghĩa mọi class trong module đều được nạp ngay hoặc mọi service method đều được gọi.

## 5. Biên dịch và đóng gói các module

Đứng tại thư mục `project`. Tạo thư mục output:

```bash
mkdir -p out mods
```

Biên dịch ba module cùng lúc:

```bash
javac --module-source-path src -d out -m com.acme.spi,com.acme.provider.en,com.acme.app
```

Sau khi biên dịch, thư mục `out` chứa các module đã biên dịch. Đóng gói thành modular JAR:

```bash
jar --create --file mods/com.acme.spi.jar -C out/com.acme.spi .
jar --create --file mods/com.acme.provider.en.jar -C out/com.acme.provider.en .
jar --create --file mods/com.acme.app.jar -C out/com.acme.app .
```

Mỗi JAR phải giữ lại `module-info.class`. Có thể kiểm tra:

```bash
jar --describe-module --file mods/com.acme.spi.jar
jar --describe-module --file mods/com.acme.provider.en.jar
jar --describe-module --file mods/com.acme.app.jar
```

Xác nhận các descriptor thể hiện đúng:

- SPI export package `com.acme.spi`.
- Provider requires SPI và provides `GreetingService`.
- App requires SPI và uses `GreetingService`.

Trên Windows, có thể chạy cùng lệnh `javac` và `jar` trong PowerShell; dấu phân cách nhiều entry trên module path là dấu chấm phẩy thay vì dấu hai chấm.

## 6. Chạy với provider trong boot layer

Khi cả ba JAR nằm trên module path:

```bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
```

Java launcher resolve root module `com.acme.app`, các dependency `requires`, và service provider phù hợp có thể quan sát được. Output `--show-module-resolution` thường có các dòng thể hiện root, requires và binds; nội dung chính xác tùy JDK và module graph.

Có thể truyền đối số:

```bash
java --module-path mods -m com.acme.app/com.acme.app.Main Ada
```

Kết quả:

```text
Hello, Ada!
```

Trong cách triển khai này, application, SPI và provider thuộc boot layer. `ServiceLoader.load(GreetingService.class)` tìm provider theo layer của caller.

Nếu không muốn provider được bind, hãy kiểm tra service declaration và tập module có thể quan sát. Không nên chỉ dựa vào việc JAR tồn tại trên ổ đĩa; provider phải được resolver nhìn thấy và đưa vào layer phù hợp.

## 7. Tạo custom ModuleLayer cho plugin

Với hệ thống plugin, có thể giữ application và SPI trong boot layer, còn provider nằm trong thư mục riêng:

```text
mods/
├── com.acme.spi.jar
└── com.acme.app.jar

plugins/
└── com.acme.provider.en.jar
```

Consumer module vẫn khai báo `uses` như trên. Provider JAR được compile với SPI có sẵn trên module path, nhưng được đóng gói riêng trong `plugins`.

Tạo các module nền tảng:

```bash
mkdir -p out mods plugins
javac --module-source-path src -d out -m com.acme.spi,com.acme.app
jar --create --file mods/com.acme.spi.jar -C out/com.acme.spi .
jar --create --file mods/com.acme.app.jar -C out/com.acme.app .
```

Biên dịch provider riêng, tham chiếu SPI từ `mods`:

```bash
javac --module-path mods --module-source-path src -d plugins -m com.acme.provider.en
jar --create --file plugins/com.acme.provider.en.jar -C plugins/com.acme.provider.en .
```

Trong application, có thể tạo child layer:

```java
import com.acme.spi.GreetingService;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

ModuleFinder pluginFinder =
        ModuleFinder.of(Path.of("plugins"));

Configuration pluginConfiguration =
        ModuleLayer.boot().configuration().resolveAndBind(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.acme.provider.en")
        );

ModuleLayer pluginLayer =
        ModuleLayer.boot().defineModulesWithOneLoader(
                pluginConfiguration,
                ClassLoader.getSystemClassLoader()
        );

ServiceLoader<GreetingService> plugins =
        ServiceLoader.load(pluginLayer, GreetingService.class);

for (GreetingService service : plugins) {
    System.out.println(service.greet("Ada"));
}
```

Ở đây:

- SPI module đã nằm trong boot layer vì application requires SPI.
- Provider được tìm trong thư mục `plugins`.
- `resolveAndBind` giải quyết provider cùng dependency và service binding liên quan.
- `defineModulesWithOneLoader` tạo child layer dùng parent class loader được chỉ định.
- `ServiceLoader.load(pluginLayer, GreetingService.class)` tìm service provider trong layer đó.

Trong ứng dụng thực tế, cần xử lý trường hợp provider không tồn tại, module name sai, dependency thiếu hoặc provider không khởi tạo được. Chỉ nạp plugin từ artifact đã được xác minh và phê duyệt; module layer không phải sandbox bảo mật.

Nếu có nhiều plugin, có thể tạo layer theo nhóm hoặc theo vòng đời triển khai. Tránh tạo lại cùng một layer cho mỗi request nếu không có yêu cầu isolation về class identity hoặc lifecycle.

## 8. Tạo runtime image với jlink

`jlink` tạo runtime image chứa JDK modules và application modules cần thiết. Với provider được đóng gói tĩnh trên module path, dùng `--bind-services` để liên kết các provider phù hợp cho service mà ứng dụng sử dụng.

Ví dụ:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --bind-services --output image
```

Lệnh trên:

- Lấy system modules từ thư mục `jmods` của JDK.
- Lấy application modules từ `mods`.
- Bắt đầu từ root module `com.acme.app`.
- Liên kết service provider phù hợp và dependency của chúng.
- Tạo runtime image tại `image`.

Chạy bằng image:

```bash
image/bin/java -m com.acme.app/com.acme.app.Main
```

Kiểm tra các module có trong image:

```bash
image/bin/java --list-modules
```

Trên Windows, executable là `image/bin/java.exe`; module path nhiều entry dùng dấu chấm phẩy.

### Image cho plugin nạp động

Nếu muốn provider nằm ngoài runtime image và được nạp bằng custom layer:

1. Link image từ các module nền tảng `com.acme.app` và `com.acme.spi`.
2. Không đưa provider plugin vào module path của lệnh `jlink`.
3. Đóng gói provider riêng trong thư mục `plugins`.
4. Chạy application từ image; application dùng `ModuleFinder`, `resolveAndBind` và `ModuleLayer` để tạo child layer.

Ví dụ link image nền tảng:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output image
```

Sau đó giữ `plugins/com.acme.provider.en.jar` bên ngoài image và dùng đoạn code custom layer ở phần trước.

Hai cách triển khai có mục đích khác nhau:

| Cách | Provider ở đâu? | Cách tìm |
|---|---|---|
| Static service binding | Được link vào runtime image | ServiceLoader trong boot layer |
| Dynamic plugin layer | JAR riêng ngoài image | ModuleFinder + resolveAndBind + ServiceLoader trong child layer |

`jlink` cần các module explicit phù hợp để link; automatic module không thể được dùng như một module đầu vào thông thường cho runtime image. Các thư viện còn là automatic module cần được modular hóa hoặc xử lý theo kiến trúc khác trước khi link.

## 9. Kiểm chứng descriptor và module graph

### Kiểm tra descriptor

```bash
jar --describe-module --file mods/com.acme.app.jar
jar --describe-module --file mods/com.acme.spi.jar
jar --describe-module --file mods/com.acme.provider.en.jar
```

Đối chiếu tên module và các directive với thiết kế. Nếu dùng plugin layer, kiểm tra provider JAR ở thư mục `plugins`.

### Kiểm tra dependency tĩnh

```bash
jdeps --module-path mods --check com.acme.app
jdeps --module-path mods --list-deps mods/com.acme.app.jar
```

`jdeps` giúp xem dependency bytecode và đối chiếu module descriptor. Nó không tự phát hiện đầy đủ reflection, class name trong cấu hình hoặc mọi provider được nạp động.

### Validate tập module

```bash
java --validate-modules --module-path mods --add-modules ALL-MODULE-PATH
```

Lệnh này yêu cầu kiểm tra các module quan sát được trên module path. Nó hữu ích để phát hiện module graph không nhất quán, split package và dependency lỗi. Dùng `ALL-MODULE-PATH` cho validation; không nhất thiết dùng làm root trong lệnh production.

### Quan sát resolution lúc chạy

```bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
```

Xác nhận:

- `com.acme.app` là root.
- `com.acme.spi` được resolve theo `requires`.
- Provider được bind khi service binding tìm thấy module phù hợp.
- Không có module ngoài dự kiến hoặc dependency bị thiếu.

Với custom layer, thêm log tên module trong configuration và layer được tạo để xác nhận provider được nạp từ đúng thư mục.

## 10. Kiểm chứng service discovery

Kiểm thử tối thiểu cần xác nhận:

- Có ít nhất một provider được tìm thấy trong deployment mong đợi.
- Provider trả kết quả đúng với input đại diện.
- Không có provider ngoài allowlist.
- Consumer xử lý đúng khi không có provider.
- Lỗi khởi tạo hoặc lỗi trong method provider được ghi nhận theo chính sách.
- Nhiều provider không làm kết quả phụ thuộc vào thứ tự duyệt ngoài ý muốn.

Ví dụ kiểm tra kết quả:

```text
Input: Ada
Expected: Hello, Ada!
Actual:   Hello, Ada!
Result:   PASS
```

Với plugin layer, kiểm tra thêm rằng SPI type được chia sẻ từ parent layer, provider được nạp vào child layer và `ServiceLoader.load(pluginLayer, GreetingService.class)` tìm đúng implementation.

Không coi việc `ServiceLoader` trả về một provider là bằng chứng provider đáng tin cậy. Artifact provenance, checksum/chữ ký và allowlist cần được xác minh độc lập.

## 11. Kiểm chứng runtime image

Sau khi link image:

```bash
image/bin/java --list-modules
image/bin/java --show-module-resolution -m com.acme.app/com.acme.app.Main
```

Chạy test chức năng từ chính image, không chỉ từ JDK đầy đủ. Điều này giúp phát hiện module hệ thống bị thiếu, provider không được bind hoặc cấu hình runtime khác với môi trường build.

Nếu dùng static service binding, xác nhận provider module có trong image. Nếu dùng dynamic plugin, xác nhận image có SPI và app, còn plugin JAR được tìm thấy trong thư mục ngoài image.

Kiểm thử trên OS và kiến trúc mục tiêu. Runtime image được tạo bởi `jlink` phụ thuộc nền tảng; cần build image phù hợp với hệ điều hành/kiến trúc triển khai.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| `module not found` | Sai module path, sai module name hoặc thiếu dependency |
| Package không visible | Consumer thiếu `requires` hoặc module sở hữu package thiếu `exports` |
| Không tìm thấy service provider | Thiếu `uses`/`provides`, provider không được resolve hoặc không nằm trong layer được tìm |
| Provider không khởi tạo | Constructor/provider declaration không hợp lệ hoặc code khởi tạo ném lỗi |
| Custom layer không resolve được provider | Finder trỏ sai thư mục, provider thiếu dependency hoặc SPI không có trong parent configuration |
| jlink báo module không hợp lệ | Dependency không phải explicit module phù hợp, thiếu module hoặc descriptor không nhất quán |
| Image chạy nhưng thiếu service | Provider chưa được link bằng service binding hoặc plugin ngoài image chưa được nạp vào child layer |
| Ứng dụng chạy trên JDK đầy đủ nhưng lỗi trên image | Runtime image thiếu module hệ thống, provider hoặc tài nguyên cần thiết |

## 13. Checklist phát hành

- [ ] Mỗi module có tên ổn định và descriptor đúng.
- [ ] Dependency `requires` phản ánh quan hệ thực tế.
- [ ] Chỉ export package API cần công khai.
- [ ] Consumer khai báo `uses`; provider khai báo `provides`.
- [ ] Không có split package hoặc dependency thiếu.
- [ ] Module graph được xác minh bằng `--show-module-resolution`.
- [ ] Dependency tĩnh được kiểm tra bằng `jdeps`.
- [ ] Service discovery được test ở đúng layer.
- [ ] Provider artifact có nguồn gốc, version và checksum được xác minh.
- [ ] Runtime image được tạo bằng đúng tập module.
- [ ] Image được test độc lập trên nền tảng mục tiêu.
- [ ] Có log, rollback và quy trình cập nhật provider.

## Ghi nhớ

- Descriptor định nghĩa readability, package API và service contract.
- Module graph được resolve từ root và dependency; service binding có thể thêm provider mà không tạo dependency trực tiếp từ consumer tới provider.
- Boot layer phù hợp với provider được triển khai cùng ứng dụng; child layer hữu ích cho plugin có lifecycle riêng.
- `jlink --bind-services` đưa provider phù hợp vào runtime image; plugin động có thể ở ngoài image và được nạp bằng custom layer.
- `jdeps`, `jar --describe-module`, `--validate-modules` và `--show-module-resolution` kiểm tra các khía cạnh khác nhau.
- Kiểm thử service, image và dependency động bằng đúng artifact triển khai.
- Module encapsulation và layer không phải sandbox; chỉ nạp provider từ nguồn đã được tin cậy.
