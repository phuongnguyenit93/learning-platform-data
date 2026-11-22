# Test split package và duplicate module name

Trong Java Platform Module System (JPMS), một project có thể biên dịch và chạy ổn trên classpath nhưng gặp lỗi khi đưa các JAR lên module path. Hai nhóm lỗi cần kiểm tra sớm là **split package** (nhiều module chứa cùng một package) và **duplicate module name** (nhiều artifact được nhận diện bằng cùng một tên module). Cả hai liên quan đến cấu trúc dependency, nhưng nguyên nhân và cách phát hiện không giống nhau.

Kiểm thử những tình huống này trước khi phát hành giúp phát hiện xung đột do thư viện bắc cầu, artifact cũ còn sót lại, automatic module hoặc sai sót đóng gói. Mục tiêu không chỉ là xác nhận ứng dụng chạy thành công mà còn chứng minh rằng cấu hình module path **từ chối những tổ hợp dependency không hợp lệ** và cung cấp thông tin đủ rõ để sửa.

## 1. Phân biệt hai loại xung đột

### Split package

Giả sử hai JAR chứa:

```text
alpha.jar
└── com/acme/shared/Alpha.class

beta.jar
└── com/acme/shared/Beta.class
```

Nếu hai artifact là hai named module độc lập, cả hai đều đóng góp class vào package `com.acme.shared`. Đây là split package ngay cả khi không có class nào trùng tên.

Vấn đề có thể xuất hiện khi một module consumer đọc package cùng tên được export từ hai module khác nhau, hoặc khi nhiều module được định nghĩa trong cùng class loader theo cách không thỏa ràng buộc package của JPMS.

### Duplicate module name

Giả sử:

```text
plugins/
├── formatter-v1.jar  → module com.acme.formatter
└── formatter-v2.jar  → module com.acme.formatter
```

Hai JAR khác nhau cùng được nhận diện là module `com.acme.formatter`. Đây là xung đột **định danh module**. Nó không phụ thuộc vào việc hai JAR có cùng package hoặc class hay không.

Một JAR có thể thuộc cả hai nhóm lỗi, nhưng không nên gọi chúng là cùng một vấn đề.

| Tiêu chí | Split package | Duplicate module name |
|---|---|---|
| Đối tượng trùng | Tên package trong nhiều module | Tên module của nhiều artifact |
| Ví dụ | Hai module có package `com.acme.shared` | Hai JAR có descriptor `module com.acme.foo` |
| Dấu hiệu thường gặp | Consumer đọc cùng package từ hai module; xung đột khi định nghĩa layer | Module finder báo nhiều định nghĩa hoặc một artifact bị che bởi artifact khác |
| Hướng sửa | Tách package, hợp nhất module, loại dependency trùng | Chỉ giữ một artifact/version cho mỗi tên module trong cấu hình |
| Có sửa được bằng `exports`/`opens` không? | Không giải quyết nguồn gốc package trùng | Không giải quyết tên module trùng |

Không nên mặc định rằng bất cứ hai module cùng chứa một package đều thất bại ngay tại bước quét module path. Kết quả còn tùy những module được resolve, quan hệ readability, exports, vị trí module path và class loader. Kiểm thử phải dựng đúng graph khiến sự cố xuất hiện.

## 2. Chuẩn bị fixture cô lập cho split package

Dùng một project thử nghiệm nhỏ, tách riêng khỏi ứng dụng production. Ví dụ cấu trúc:

```text
split-package-fixture/
├── src-alpha/
│   ├── module-info.java
│   └── com/acme/shared/Alpha.java
├── src-beta/
│   ├── module-info.java
│   └── com/acme/shared/Beta.java
└── src-app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

Module thứ nhất:

```java
// src-alpha/module-info.java
module com.acme.alpha {
    exports com.acme.shared;
}
```

```java
// src-alpha/com/acme/shared/Alpha.java
package com.acme.shared;

public final class Alpha {
    public static String name() {
        return "alpha";
    }
}
```

Module thứ hai:

```java
// src-beta/module-info.java
module com.acme.beta {
    exports com.acme.shared;
}
```

```java
// src-beta/com/acme/shared/Beta.java
package com.acme.shared;

public final class Beta {
    public static String name() {
        return "beta";
    }
}
```

Consumer:

```java
// src-app/module-info.java
module com.acme.app {
    requires com.acme.alpha;
    requires com.acme.beta;
}
```

```java
// src-app/com/acme/app/Main.java
package com.acme.app;

import com.acme.shared.Alpha;

public class Main {
    public static void main(String[] args) {
        System.out.println(Alpha.name());
    }
}
```

Hai module `com.acme.alpha` và `com.acme.beta` đều export `com.acme.shared`, trong khi `com.acme.app` yêu cầu đọc cả hai. Đây là một tình huống cố ý tạo ra xung đột về package visibility.

## 3. Biên dịch fixture và xác nhận lỗi mong đợi

Biên dịch mỗi module thư viện riêng để chúng không cạnh tranh trong cùng một lần compile:

```shell
mkdir -p out/alpha out/beta out/app mods

javac -d out/alpha \
  src-alpha/module-info.java \
  src-alpha/com/acme/shared/Alpha.java

jar --create --file mods/com.acme.alpha.jar -C out/alpha .

javac -d out/beta \
  src-beta/module-info.java \
  src-beta/com/acme/shared/Beta.java

jar --create --file mods/com.acme.beta.jar -C out/beta .
```

Các lệnh ví dụ dùng cú pháp shell trên Linux/macOS. Trên Windows có thể tạo thư mục bằng PowerShell và dùng từng lệnh `javac`/`jar` trên một dòng.

Sau đó thử compile consumer:

```shell
javac --module-path mods \
  -d out/app \
  src-app/module-info.java \
  src-app/com/acme/app/Main.java
```

**Kỳ vọng:** biên dịch thất bại vì consumer đọc package `com.acme.shared` từ cả `com.acme.alpha` và `com.acme.beta`. Tùy phiên bản JDK, thông báo có thể nêu module đọc cùng package từ hai module hoặc package không thể được truy cập một cách nhất quán.

Lỗi trong fixture này là **kết quả mong đợi**, không phải lỗi của bộ kiểm thử. Nếu compiler thành công một cách bất ngờ, cần xem lại module path, descriptor và xem cả hai thư viện có thực sự được compile dưới dạng named modules không.

Đừng chỉ kiểm tra exit code khác 0 mà bỏ qua nguyên nhân; một lỗi cú pháp trong fixture cũng khiến lệnh thất bại nhưng không chứng minh đã phát hiện split package.

## 4. Tạo kiểm thử âm có điều kiện kết quả rõ ràng

Một negative test nên kiểm tra hai điều:

1. Lệnh bị từ chối (exit code khác 0).
2. Chẩn đoán đề cập tới xung đột package/module mong đợi, không phải một lỗi ngẫu nhiên.

Ví dụ shell:

```shell
if javac --module-path mods \
    -d out/app \
    src-app/module-info.java \
    src-app/com/acme/app/Main.java \
    2> split-package-error.txt; then
  echo "FAIL: compilation unexpectedly succeeded"
  exit 1
fi

if grep -Eiq 'reads package|from both|package.*module' \
    split-package-error.txt; then
  echo "PASS: expected package conflict was detected"
else
  echo "FAIL: compilation failed for an unexpected reason"
  cat split-package-error.txt
  exit 1
fi
```

Các cụm trong biểu thức tìm kiếm là ví dụ dành cho output tiếng Anh. Thông báo lỗi có thể khác theo JDK hoặc locale, nên một bộ test lâu dài có thể cấu hình locale hoặc sử dụng tập pattern phù hợp với compiler được hỗ trợ.

Không khuyến khích so khớp nguyên một dòng thông báo, số dòng stack trace hoặc thứ tự module trong output; các chi tiết đó có thể thay đổi giữa các phiên bản JDK.

## 5. Tạo fixture duplicate module name

Để minh họa tình huống hai JAR có **cùng tên module**, tạo hai bản triển khai khác nhau nhưng mỗi bản đều dùng descriptor:

```java
module com.acme.duplicate {
    exports com.acme.duplicate.api;
}
```

Artifact A có thể chứa:

```java
package com.acme.duplicate.api;

public final class Version {
    public static String value() {
        return "A";
    }
}
```

Artifact B dùng cùng tên module và package nhưng trả về `"B"`. Đóng gói hai bản thành:

```text
duplicate-fixture/
└── mods/
    ├── duplicate-a.jar
    └── duplicate-b.jar
```

Hai JAR được biên dịch và đóng gói **riêng biệt**. Không đưa cả hai source tree vào một lần compile rồi coi đó là kiểm thử duplicate module name: lúc đó lỗi có thể đến từ source layout thay vì module finder đang nhận diện hai artifact.

Chạy công cụ kiểm tra module path:

```shell
java --module-path mods --validate-modules
```

Khi hai artifact có cùng tên module nằm trong **cùng một module-path directory** và cả hai được quan sát, module finder có thể báo lỗi nhiều định nghĩa của `com.acme.duplicate`. Đây là dạng kiểm thử hữu ích cho việc đóng gói nhầm cả hai version vào một thư mục.

### Lưu ý về thứ tự module path

Nếu hai artifact cùng tên nằm ở **hai phần tử module path khác nhau**, hành vi tìm kiếm có thể chọn định nghĩa gặp trước và che định nghĩa ở phần tử phía sau, thay vì luôn phát lỗi trùng tên. Ví dụ:

```shell
java --module-path "mods-v1:mods-v2" \
  --validate-modules
```

Trên Windows, dùng dấu `;` thay vì `:`. Vì có khả năng shadowing, **đừng coi một lần `--validate-modules` thành công là bằng chứng tuyệt đối rằng toàn bộ dependency artifacts không có tên module trùng**. Cần kiểm tra danh sách artifact đầu vào một cách độc lập.

## 6. Kiểm tra tên module thực tế của từng JAR

Tên file JAR không nhất thiết giống tên module. Có ba trường hợp phổ biến:

- **Explicit module:** tên lấy từ `module-info.class`.
- **Automatic module có `Automatic-Module-Name`:** tên lấy từ manifest.
- **Automatic module không có tên tường minh:** tên được suy ra từ filename theo quy tắc của module system.

Ví dụ:

```shell
jar --describe-module --file libs/formatter-1.0.jar
jar --describe-module --file libs/formatter-2.0.jar
```

Hai file có version khác nhau vẫn có thể khai báo cùng `module com.acme.formatter`. Điều này thường **đúng** về bản sắc module: hai version của cùng thư viện nên có cùng tên logic, nhưng **không được cùng tồn tại như hai định nghĩa cạnh tranh của một module trong cùng cấu hình**.

Hai automatic JAR cũng có thể tình cờ nhận cùng tên sau bước suy luận từ filename. Vì vậy, không nên chỉ tìm file có basename giống nhau; hãy lấy module name đúng như module finder nhìn thấy.

Một bài kiểm tra duplicate name hữu ích cần so sánh **tên module** chứ không chỉ so sánh file path.

## 7. Kiểm tra từng artifact bằng ModuleFinder

Để tránh bị che khuất bởi quy tắc chọn phần tử đầu tiên trên module path, có thể đọc mỗi JAR riêng bằng `ModuleFinder` và nhóm theo tên module.

Ví dụ chương trình kiểm tra:

```java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class DuplicateModuleNames {
    public static void main(String[] args) {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                "Pass JAR paths to inspect"
            );
        }

        Map<String, List<Path>> byName = new TreeMap<>();

        for (String arg : args) {
            Path jar = Path.of(arg).toAbsolutePath();

            for (ModuleReference ref :
                    ModuleFinder.of(jar).findAll()) {
                String name = ref.descriptor().name();
                byName.computeIfAbsent(
                    name, key -> new ArrayList<>()
                ).add(jar);
            }
        }

        boolean foundDuplicate = false;

        for (var entry : byName.entrySet()) {
            if (entry.getValue().size() > 1) {
                foundDuplicate = true;
                System.err.println(
                    "Duplicate module: " + entry.getKey()
                );
                entry.getValue().forEach(path ->
                    System.err.println("  " + path)
                );
            }
        }

        if (foundDuplicate) {
            System.exit(1);
        }

        System.out.println("No duplicate module names");
    }
}
```

Biên dịch bằng JDK hỗ trợ API/module syntax trong ví dụ và chạy với danh sách JAR:

```shell
javac DuplicateModuleNames.java

java DuplicateModuleNames \
  libs/formatter-1.0.jar \
  libs/formatter-2.0.jar
```

Đoạn kiểm tra tạo `ModuleFinder` **riêng cho từng JAR**, nên nó không phụ thuộc vào việc một module finder chung chọn bản nào trước. Nếu hai JAR trả về cùng `ModuleDescriptor.name()`, bài kiểm tra đánh dấu duplicate.

Có thể tích hợp logic này vào một Gradle/Maven verification task, truyền danh sách JAR đã được build tool resolve. Nếu muốn kiểm tra cả module nằm trong các JAR được đóng gói trong một archive khác, phải giải nén/đọc artifact thực tế phù hợp trước khi chạy.

## 8. ModuleFinder và ResolutionException khác nhau

JPMS có những giai đoạn riêng, nên lỗi có thể xuất hiện ở các chỗ khác nhau:

**Module discovery:** module finder tìm các module trong module path. Nhiều định nghĩa không thể phân biệt của cùng module name trong một nguồn có thể gây `FindException`.

**Module resolution:** module system tạo module graph từ root modules và dependency `requires`. Nếu graph làm một module đọc cùng package từ các module không tương thích, có thể nhận `ResolutionException`.

**Layer definition:** sau resolution, runtime định nghĩa module trong class loaders. Một số tổ hợp package/class loader không hợp lệ có thể gây `LayerInstantiationException`.

**Compilation:** `javac` áp dụng kiểm tra module readability và package visibility cho source; lỗi có thể xuất hiện ngay trước khi chạy.

Do đó, bộ kiểm thử không nên chỉ bắt một exception class. Hãy thiết kế fixture theo giai đoạn cần kiểm tra: compile failure, resolution failure, layer-definition failure hoặc artifact-name collision.

## 9. Kiểm thử split package bằng API Configuration

Với chương trình Java kiểm tra riêng, có thể dùng `ModuleFinder` và `Configuration.resolve` để buộc phân giải hai module cần kiểm tra:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

Configuration config =
    ModuleLayer.boot().configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.alpha", "com.acme.beta")
    );
```

Đoạn trên chỉ buộc hai module được phân giải làm root; **không nhất thiết tái hiện lỗi consumer đọc hai exports**, vì chưa có module `com.acme.app` đọc cả hai. Để kiểm tra xung đột tại resolution, cần thêm module consumer như trong fixture hoặc tạo quan hệ đọc gây xung đột.

Một ví dụ root phù hợp hơn:

```java
Configuration config =
    ModuleLayer.boot().configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.app")
    );
```

Khi `com.acme.app` yêu cầu cả alpha và beta và chúng cùng export `com.acme.shared`, resolution có thể từ chối graph. Cách này giúp test ở mức module configuration mà không cần thực thi `Main`.

Nếu viết unit test cho đoạn này, hãy bắt lỗi resolution đúng giai đoạn và ghi lại package/module nào gây xung đột; không nên bắt chung mọi `RuntimeException` rồi coi đó là thành công.

## 10. Trường hợp split package không bị phát hiện ngay

Có hai tình huống dễ làm bộ kiểm thử cho kết quả sai:

**Một module không được resolve:** hai JAR cùng chứa package trùng nhưng chỉ một module được đưa vào graph của lần chạy. Ứng dụng có thể khởi động bình thường. Vì vậy, phải chủ động chọn root hoặc consumer khiến cả hai module được dùng trong fixture.

**Package không được export cho cùng consumer:** trong một số graph, sự trùng tên package không gây xung đột readability theo cách fixture bên trên. Tuy nhiên, nếu modules được định nghĩa vào cùng class loader, có thể còn ràng buộc ở bước layer definition.

Điều này giải thích vì sao lệnh `java --list-modules` hoặc chỉ quét tên package không đủ để kết luận toàn bộ graph hợp lệ hay không. Muốn kiểm tra hành vi JPMS, phải thử resolution và, khi phù hợp, tạo layer/chạy module với cấu hình thực tế.

## 11. Split package trong automatic modules

Automatic module giúp dùng JAR truyền thống trên module path trong quá trình migration. Nhưng một JAR không có `module-info.class` vẫn có thể chứa package trùng với một explicit module khác.

Ví dụ:

```text
explicit-api.jar  → module com.acme.api
legacy-tools.jar  → automatic module legacy.tools
```

Nếu cả hai chứa `com.acme.shared`, việc đặt chúng lên module path có thể gây xung đột khi graph liên quan được phân giải. Automatic module còn thường export các package rộng, nên một package trùng dễ trở thành package mà consumer nhìn thấy từ nhiều nguồn.

Để kiểm thử, không cần sửa JAR thành explicit module chỉ để tái hiện lỗi. Hãy đưa đúng JAR legacy vào module path của fixture, xác nhận tên automatic module rồi tạo consumer đọc cả hai module.

Không sử dụng `--add-exports`, `--add-opens` hoặc `open module` để che split package. Những lựa chọn này điều chỉnh truy cập, không thay đổi package nằm trong artifact nào.

## 12. Kiểm thử với Maven và Gradle

Trong build thực tế, xung đột thường đến từ dependency bắc cầu, không phải từ những JAR được thêm trực tiếp.

Với Maven:

```shell
mvn dependency:tree
```

Với Gradle:

```shell
./gradlew dependencies --configuration runtimeClasspath
```

Đây là bước xác định **artifact nào đã được resolve**. Sau đó nên triển khai các kiểm tra:

1. Thu thập danh sách JAR thực tế trên runtime module path và compile module path.
2. Xác định module name của từng JAR; phát hiện duplicate names trước khi tạo layer.
3. Phân tích package bên trong từng JAR để tìm những tên package xuất hiện ở nhiều module.
4. Chạy `java --validate-modules` đối với module path tương ứng.
5. Chạy compile/module-resolution test với các root modules thực sự của ứng dụng.
6. Smoke test ứng dụng bằng đúng JDK/module path sẽ triển khai.

Đối với Gradle, có thể định nghĩa verification task tùy chỉnh lấy artifact files từ configuration đã resolve; đối với Maven, có thể chạy script kiểm tra trong giai đoạn verify. Điều quan trọng là kiểm tra **resolved artifacts**, không chỉ các dependency được khai báo trực tiếp trong build file.

## 13. Thiết kế CI gate cho module path

Một CI gate hữu ích có thể tách thành ba loại bài kiểm tra:

| Gate | Đầu vào | Điều kiện đạt |
|---|---|---|
| Module-name uniqueness | Tất cả JAR dự định đặt trên module path | Mỗi module name chỉ ánh xạ tới một artifact được chọn |
| Package ownership | Nội dung package của các artifact | Không có split package trái với thiết kế; các package trùng được điều tra |
| Module resolution/run | Module path, root modules, test fixtures | Cấu hình module hợp lệ; ứng dụng khởi chạy và dùng được API cần thiết |

Quy trình minh họa:

```text
Resolve dependencies (Maven/Gradle)
               |
               v
Collect actual modular JAR files
               |
               v
Read module names and package inventories
               |
               v
Reject unintended duplicates
               |
               v
java --validate-modules
               |
               v
Compile / resolve application root modules
               |
               v
Launch modular smoke tests
```

Một negative test nên được thực thi trên fixture riêng và xác nhận đúng loại lỗi. Không nên đưa JAR “cố tình lỗi” vào module path của build chính rồi mong toàn bộ pipeline hoạt động bình thường.

## 14. Cách sửa khi test phát hiện split package

Một số hướng xử lý theo mức độ ưu tiên:

- **Loại dependency hoặc version thừa:** ví dụ đang kéo cả JAR nguyên khối và các JAR đã tách module của cùng thư viện.
- **Chọn một module sở hữu package:** chuyển các class liên quan về một module thay vì phân tán package cùng tên.
- **Đổi package:** dùng namespace riêng theo module hoặc bounded context.
- **Relocate thư viện được shade:** khi không thể sửa source của third-party dependency và các ràng buộc API cho phép.
- **Cập nhật module descriptor:** sau khi tổ chức lại package, sửa `requires` và `exports` tương ứng.

Ví dụ, thay vì:

```text
com.acme.alpha → com.acme.shared.Alpha
com.acme.beta  → com.acme.shared.Beta
```

có thể chuyển thành:

```text
com.acme.alpha → com.acme.alpha.api.Alpha
com.acme.beta  → com.acme.beta.api.Beta
```

hoặc tạo một module API chung sở hữu `com.acme.shared` khi hai class thực sự thuộc cùng contract.

Relocation có thể ảnh hưởng reflection, `ServiceLoader` metadata và serialization, nên cần cập nhật cả cấu hình và resource liên quan.

## 15. Cách sửa khi test phát hiện duplicate module name

Một tên module hợp lệ nên tương ứng với **một định nghĩa được chọn** trong môi trường triển khai cụ thể.

Các cách xử lý phổ biến:

1. Loại JAR cũ hoặc version không còn dùng.
2. Dùng dependency constraints/lockfiles để bảo đảm chỉ một version được resolve.
3. Tránh thêm cùng artifact vào module path bằng hai đường dẫn khác nhau.
4. Nếu hai thư viện thực sự độc lập nhưng vô tình dùng cùng tên module, đổi tên module của một thư viện có kiểm soát và cập nhật consumers.
5. Nếu một JAR là automatic module, cấu hình tên module ổn định (ví dụ `Automatic-Module-Name`) ở phía publisher hoặc dùng artifact đã modular hóa phù hợp.
6. Kiểm tra lệnh chạy cuối cùng, vì lỗi có thể do launcher hoặc plugin manager lắp ghép lại module path ngoài dự kiến.

Không nên “sửa” duplicate module name bằng `--add-reads`, `--add-exports` hoặc `--add-opens`. Chúng không thay đổi danh tính module và không quyết định artifact version nào phải được chọn.

## 16. Phân biệt lỗi test với các lỗi JPMS khác

| Thông báo/ngoại lệ | Hướng điều tra |
|---|---|
| `reads package P from both M1 and M2` | Split package gây xung đột visibility đối với consumer |
| `FindException` kèm thông tin hai định nghĩa module | Duplicate module name trong nguồn module finder |
| `ResolutionException` | Module graph không phân giải được, có thể do package/readability |
| `LayerInstantiationException` | Ràng buộc class loader, package/module khi định nghĩa layer |
| `module not found: X` | Thiếu module, sai module path hoặc sai module name; không tự kết luận là duplicate |
| `package ... is not visible` | Thiếu `requires` hoặc package chưa export; không tự kết luận split package |
| `InaccessibleObjectException` | Deep reflection bị chặn; kiểm tra `opens` |
| `IllegalAccessError` | Bytecode không còn hợp lệ theo quyền truy cập runtime |

Việc đọc chính xác thông báo đầu tiên quan trọng hơn việc thêm cờ JVM theo phỏng đoán. Một package bị đóng do thiếu export không giống package trùng giữa hai module.

## 17. Checklist kiểm thử trước khi phát hành

- [ ] Lấy danh sách JAR thực sự được dùng, kể cả dependency bắc cầu.
- [ ] Xác định module name bằng descriptor, manifest hoặc module finder.
- [ ] Phát hiện duplicate module names kể cả khi các JAR nằm ở nhiều module-path entries.
- [ ] Kiểm kê package để phát hiện split package tiềm ẩn.
- [ ] Chạy `java --validate-modules` với module path của sản phẩm.
- [ ] Biên dịch các named modules với dependency thực tế.
- [ ] Kiểm tra resolution với root modules của ứng dụng hoặc plugin layer.
- [ ] Xác minh âm tính với fixture có lỗi được tạo chủ đích.
- [ ] Không coi mọi exit code khác 0 là đúng lỗi mong đợi.
- [ ] Kiểm tra hành vi trên JDK mục tiêu và custom runtime image khi có.
- [ ] Không dùng `opens`/`exports` để che cấu trúc module sai.
- [ ] Giữ chỉ một module definition cho mỗi tên module trong cấu hình cuối cùng.

**Kết luận:** Test split package và duplicate module name cần hai chiến lược bổ sung: kiểm tra **package ownership** để phát hiện tên package lặp giữa các module, và kiểm tra **module identity** để phát hiện nhiều artifact cùng một module name. Kết hợp quét artifact độc lập với kiểm thử resolution/layer thực tế sẽ phát hiện cả lỗi rõ ràng lẫn tình huống shadowing âm thầm.