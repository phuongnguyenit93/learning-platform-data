# LayerInstantiationException khi tạo layer

## 1. LayerInstantiationException báo hiệu điều gì?

Trong Java Platform Module System (JPMS), `ModuleLayer` là một tập hợp các module đã được định nghĩa tại runtime. Ứng dụng có thể tạo custom layer để nạp plugin, extension hoặc các module không nằm trong boot layer.

`java.lang.LayerInstantiationException` là runtime exception cho biết **JVM không thể định nghĩa các module của một `Configuration` thành một `ModuleLayer` theo ánh xạ class loader được yêu cầu**. Lỗi thường phát sinh ở bước gọi các phương thức như:

- `ModuleLayer.defineModulesWithOneLoader(...)`.
- `ModuleLayer.defineModulesWithManyLoaders(...)`.
- `ModuleLayer.defineModules(...)`.
- Các overload instance tương ứng được gọi trên một `ModuleLayer` cha.

Điểm quan trọng: **module resolution** và **layer instantiation** là hai giai đoạn khác nhau.

~~~text
ModuleFinder
    |
    v
Configuration.resolve / resolveAndBind
    |
    | Thành công: đã có module graph
    v
ModuleLayer.defineModules...
    |
    | Thành công: mỗi module được gắn với một defining class loader
    v
ModuleLayer sẵn sàng nạp class
~~~

Một cấu hình module có thể được resolve thành công nhưng vẫn không thể instantiate khi nhiều module buộc phải chia sẻ một loader, khi delegation không nhất quán hoặc khi ánh xạ module vào loader vi phạm các ràng buộc của JVM.

Vì vậy, nếu gặp `LayerInstantiationException`, cần xác định **lỗi ở bước định nghĩa layer**, không chỉ nhìn danh sách dependency hoặc sửa `requires` một cách tùy tiện.

## 2. Ví dụ tạo custom ModuleLayer

Giả sử host muốn nạp một module plugin từ thư mục `plugins`:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public final class PluginLayers {

    public static ModuleLayer create(Path pluginDirectory) {
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder finder = ModuleFinder.of(pluginDirectory);

        Configuration configuration =
                parent.configuration().resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("com.acme.plugin"));

        return parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());
    }
}
~~~

Đoạn code gồm hai phần có thể thất bại độc lập:

1. `resolve(...)` tìm root module và phân giải dependency.
2. `defineModulesWithOneLoader(...)` định nghĩa các module đã resolve vào một class loader mới chung.

Nếu module path thiếu dependency, bước 1 có thể ném `FindException` hoặc `ResolutionException` tùy nguyên nhân. Nếu configuration đã hợp lệ nhưng mô hình class loader không đáp ứng ràng buộc, bước 2 có thể ném `LayerInstantiationException`.

Không nên viết một khối `catch (RuntimeException)` duy nhất rồi báo chung là “module not found”. Nó làm mất thông tin giai đoạn và khiến người điều tra sửa nhầm cấu hình.

## 3. Ba thành phần cần ghi lại trước khi sửa lỗi

Khi phân tích lỗi tạo layer, ghi lại tối thiểu:

| Thành phần | Ví dụ | Vì sao cần biết? |
|---|---|---|
| Parent layer | `ModuleLayer.boot()` | Xác định module/package đã có ở layer cha |
| Configuration | `Configuration` được trả về từ `resolve` | Xác định những module dự kiến đưa vào layer mới |
| Loader strategy | One loader, many loaders hoặc custom mapping | Xác định vì sao các package/module bị ánh xạ vào loader không phù hợp |

Cùng một `Configuration` có thể thành công với chiến lược loader này nhưng thất bại với chiến lược khác.

Ví dụ:

~~~java
ModuleLayer parent = ModuleLayer.boot();

Configuration cf = parent.configuration().resolve(
        ModuleFinder.of(pluginPath),
        ModuleFinder.of(),
        Set.of("com.acme.plugin"));

ModuleLayer layer = parent.defineModulesWithOneLoader(
        cf, ClassLoader.getSystemClassLoader());
~~~

Khi đọc stack trace, phân biệt lỗi đến từ `resolve` hay `defineModulesWithOneLoader`. Đây là bước định hướng quan trọng nhất.

## 4. Nguyên nhân phổ biến: hai module chứa cùng package

Với `defineModulesWithOneLoader`, tất cả module thuộc configuration mới được định nghĩa vào **cùng một class loader**. Một loader không thể định nghĩa cùng một package như package của hai module khác nhau theo mô hình này.

Ví dụ về cấu trúc có nguy cơ xung đột:

~~~text
plugins/
├── com.acme.plugin.alpha.jar
│   └── com/acme/shared/AlphaHelper.class
└── com.acme.plugin.beta.jar
    └── com/acme/shared/BetaHelper.class
~~~

Hai named module đều chứa package:

~~~text
com.acme.shared
~~~

Nếu cả hai module cùng được đưa vào configuration rồi gọi `defineModulesWithOneLoader`, bước định nghĩa layer có thể bị từ chối vì **overlapping packages**.

Điểm đáng lưu ý:

- Không cần có hai class trùng tên; chỉ cần **tên package giống nhau** trong hai module đã đủ tạo xung đột đối với chiến lược một loader.
- Modifier `public` và `exports` không làm xung đột package biến mất.
- Hai JAR có package chung nhưng dùng classpath truyền thống không chứng minh chúng có thể cùng hoạt động như explicit named modules với một loader.
- Tên package phải được so sánh theo tên đầy đủ; chia sẻ prefix, ví dụ `com.acme`, không tự tạo xung đột nếu package thực tế khác nhau.

Cách sửa ưu tiên là **đặt mỗi package thuộc một module rõ ràng**. Có thể chuyển code chia sẻ vào module API hoặc common module riêng, rồi để các plugin dùng `requires` thay vì sao chép package.

## 5. Phân biệt split package và split delegation

Hai khái niệm dễ bị nhầm:

### 5.1. Overlapping packages / split package

Hai module trong configuration chứa cùng package, ví dụ:

~~~text
Module A: com.acme.shared
Module B: com.acme.shared
~~~

Điều này trực tiếp gây vấn đề khi cố ánh xạ cả hai module vào một loader.

### 5.2. Split delegation

Một class loader mới có thể cần chuyển yêu cầu nạp các class cùng một package tới **nhiều parent class loader khác nhau** vì những module ở các parent layer được ánh xạ khác nhau.

Ví dụ tình huống khái niệm:

~~~text
                   Custom Layer
                One shared loader
                  /          \
                 /            \
 Parent loader A                Parent loader B
 Module A exports p             Module B exports p
~~~

Nếu loader của layer mới phải chọn hơn một loader đích cho cùng package `p`, direct delegation không còn duy nhất. `defineModulesWithOneLoader` có thể thất bại do **split delegation**, dù từng module riêng lẻ đã hợp lệ.

Đây là lý do cần kiểm tra cả parent layers và class loaders, không chỉ tìm package trùng trong chính configuration mới.

Việc đổi sang `defineModulesWithManyLoaders` có thể phù hợp với một số kiến trúc nhưng không phải phương thuốc mặc định. Nếu module graph hoặc package ownership vẫn không nhất quán, cần sửa thiết kế và cách phân giải dependency trước.

## 6. Định nghĩa module vào class loader đã chứa module trùng tên

Với phương thức ánh xạ tùy biến:

~~~java
ModuleLayer.defineModules(
        configuration,
        parentLayers,
        moduleName -> someLoader);
~~~

JVM kiểm tra các ràng buộc liên quan class loader. Một nguyên nhân gây `LayerInstantiationException` là cố định nghĩa một module vào loader **đã có module cùng tên**.

Ví dụ một plugin host giữ lại loader từ lần triển khai trước rồi tiếp tục dùng loader đó cho cùng module name ở một layer mới.

Điều cần nhớ:

- Một module name có thể xuất hiện ở những layer khác nhau khi được tổ chức theo class loader phù hợp.
- Nhưng không thể mặc định rằng cùng một class loader có thể được dùng nhiều lần để định nghĩa lại một module cùng tên.
- Hot reload thường cần **loader mới** cho phiên bản plugin mới, cùng chiến lược giải phóng tham chiếu tới loader cũ.

Nếu host cache `ClassLoader` toàn cục và map mọi phiên bản plugin mới vào loader cũ, hãy kiểm tra đây có phải nguồn lỗi hay không.

## 7. Loader đã định nghĩa class trong package của module mới

Một trường hợp quan trọng của custom mapping là ánh xạ module vào loader đã tự định nghĩa các type thuộc package mà module sắp sở hữu.

Ví dụ một URLClassLoader đã nạp:

~~~text
com.acme.plugin.internal.Helper
~~~

Sau đó ứng dụng muốn gán module `com.acme.plugin` chứa cùng package `com.acme.plugin.internal` vào chính loader này.

JVM có thể từ chối vì loader đã định nghĩa class trong package trước khi module được định nghĩa vào loader.

Vì vậy, khi xây dựng custom plugin loader:

1. Tạo hoặc chuẩn bị loader trước.
2. Định nghĩa module/layer đúng trình tự.
3. Chỉ sau đó mới bắt đầu nạp class từ các module của layer.
4. Không gọi `Class.forName(...)` hoặc `loader.loadClass(...)` quá sớm để “kiểm tra” class trong package sắp được định nghĩa.

Một lỗi phổ biến là code discovery/inspection nạp class trước khi layer được tạo, vô tình làm thay đổi trạng thái class loader và gây xung đột khi instantiate.

## 8. Hạn chế với module java.base và package java.*

Các API tạo custom layer không cho phép tự do định nghĩa lại những thành phần lõi thuộc namespace dành riêng cho nền tảng.

Những cấu hình như sau không hợp lệ:

- Cấu hình cố đưa module tên `java.base` vào layer mới.
- Module mới chứa package tên `java` hoặc bắt đầu bằng `java.`, ví dụ `java.acme.plugin`.
- Với custom module-to-loader mapping, một số class loader đặc biệt bị cấm làm loader đích theo contract API.

Ví dụ một plugin vô tình tạo package:

~~~java
package java.acme.plugin;
~~~

đây không phải cách đặt tên package hợp lệ cho custom module layer. Đổi sang namespace do ứng dụng sở hữu, ví dụ:

~~~java
package com.acme.plugin;
~~~

Không dùng `--add-exports` hoặc `--add-opens` để khắc phục trường hợp này: các tùy chọn đó liên quan quyền truy cập package, không trao quyền định nghĩa lại package nền tảng.

## 9. Lựa chọn defineModulesWithOneLoader, ManyLoaders và custom mapping

Ba chiến lược có đặc điểm khác nhau:

| Cách tạo layer | Ánh xạ loader | Thích hợp khi |
|---|---|---|
| `defineModulesWithOneLoader` | Các module trong configuration mới chia sẻ một loader | Nhóm module phối hợp chặt chẽ, không xung đột package/delegation |
| `defineModulesWithManyLoaders` | Mỗi module trong layer nhận loader riêng do API tạo | Muốn phân tách module theo loader và để API quản lý delegation |
| `defineModules` | Hàm tùy biến quyết định loader cho từng module | Host có hệ thống class loader riêng và kiểm soát đầy đủ ánh xạ |

Chọn phương án dựa trên kiến trúc. Nhiều loader có thể giúp tránh một số xung đột do gom quá nhiều module vào một loader, nhưng:

- Module graph vẫn phải hợp lệ.
- Không thể dựa vào việc nhiều loader để hợp thức hóa mọi split package giữa các module có quan hệ readability.
- Service API truyền qua biên giới plugin phải dùng cùng class identity.
- Với custom mapping, loader phải tuân thủ những ràng buộc về module definition và class loading/delegation.

Không nên chuyển sang many-loaders chỉ để làm exception biến mất mà bỏ qua nguyên nhân. Hãy ghi lại tại sao mô hình loader mới đúng với yêu cầu hệ thống.

## 10. Ví dụ chuyển từ one loader sang many loaders

Với configuration đã resolve:

~~~java
ModuleLayer parent = ModuleLayer.boot();

Configuration cf = parent.configuration().resolve(
        ModuleFinder.of(pluginDirectory),
        ModuleFinder.of(),
        Set.of("com.acme.plugin.alpha", "com.acme.plugin.beta"));
~~~

Phiên bản một loader:

~~~java
ModuleLayer layer = parent.defineModulesWithOneLoader(
        cf,
        ClassLoader.getSystemClassLoader());
~~~

Nếu cấu trúc module thỏa các ràng buộc phù hợp, có thể dùng nhiều loader:

~~~java
ModuleLayer layer = parent.defineModulesWithManyLoaders(
        cf,
        ClassLoader.getSystemClassLoader());
~~~

Sau khi tạo layer, có thể tìm loader gắn với từng module:

~~~java
ClassLoader alphaLoader =
        layer.findLoader("com.acme.plugin.alpha");

ClassLoader betaLoader =
        layer.findLoader("com.acme.plugin.beta");

System.out.println(alphaLoader == betaLoader);
~~~

Với phương thức many-loaders, các module trong layer được định nghĩa vào loader riêng. Dù vậy, điều này không có nghĩa hai plugin được phép định nghĩa riêng service interface mà host và plugin trao đổi qua API.

Nếu host sử dụng `com.acme.plugin.api.Plugin` từ parent layer, provider ở layer con phải triển khai đúng service interface đó. Nếu plugin tự đóng gói bản sao API dưới loader khác, lỗi class identity có thể xuất hiện sau khi layer được tạo.

## 11. Module resolution failure không phải layer instantiation failure

Một troubleshooting flow nên phân biệt ba nhóm exception:

| Giai đoạn | Exception thường gặp | Bản chất |
|---|---|---|
| Find module | `FindException` | Không tìm được module, artifact không đọc được hoặc lỗi phát hiện module |
| Resolve configuration | `ResolutionException` | Module graph không thỏa ràng buộc resolution |
| Define layer | `LayerInstantiationException` | Không thể định nghĩa các module vào loader theo mapping yêu cầu |

Ngoài ra, nếu parent configuration và parent layers được truyền không tương ứng, API có thể ném `IllegalArgumentException`. Các lỗi từ mapping function cũng có thể được truyền ra ngoài, chứ không tự biến thành `LayerInstantiationException` trong mọi trường hợp.

Ví dụ logging theo giai đoạn:

~~~java
ModuleLayer parent = ModuleLayer.boot();

Configuration cf;
try {
    cf = parent.configuration().resolve(
            ModuleFinder.of(pluginDirectory),
            ModuleFinder.of(),
            Set.of("com.acme.plugin"));
} catch (java.lang.module.FindException ex) {
    System.err.println("Failed to find modules");
    ex.printStackTrace();
    throw ex;
} catch (java.lang.module.ResolutionException ex) {
    System.err.println("Failed to resolve configuration");
    ex.printStackTrace();
    throw ex;
}

try {
    return parent.defineModulesWithOneLoader(
            cf, ClassLoader.getSystemClassLoader());
} catch (LayerInstantiationException ex) {
    System.err.println("Failed to instantiate module layer");
    ex.printStackTrace();
    throw ex;
}
~~~

Ở ví dụ hoàn chỉnh, phương thức chứa đoạn code trên cần trả về `ModuleLayer` và khai báo các biến đầu vào phù hợp.

Phân tách như vậy giúp log chỉ ra đúng giai đoạn; không nên viết fallback lặp vô hạn hoặc retry tạo layer với cùng input khi chưa hiểu nguyên nhân.

## 12. Bẫy parent configuration không khớp parent layer

Ví dụ:

~~~java
ModuleLayer boot = ModuleLayer.boot();

Configuration cf = boot.configuration().resolve(
        ModuleFinder.of(pluginPath),
        ModuleFinder.of(),
        Set.of("com.acme.plugin"));
~~~

Cấu hình trên có parent là configuration của boot layer. Nếu sau đó gọi phương thức định nghĩa layer với một tập parent layers không tương ứng, API có thể ném `IllegalArgumentException`.

Điều này khác với `LayerInstantiationException`:

- `IllegalArgumentException`: caller truyền một tổ hợp configuration/parent layers không hợp lệ theo contract phương thức.
- `LayerInstantiationException`: thao tác định nghĩa module/layer không thể hoàn thành vì những ràng buộc instantiation.

Khi dùng static API với nhiều parent layers:

~~~java
ModuleLayer.defineModulesWithOneLoader(
        cf,
        List.of(parentLayer),
        ClassLoader.getSystemClassLoader());
~~~

hãy đảm bảo danh sách parent layers đúng thứ tự và khớp với các parent configurations của `cf`.

Không dùng một `Configuration` của cây layer này rồi gắn nhầm sang cây layer khác chỉ vì các module name nhìn giống nhau.

## 13. Kiểm tra module descriptor và package ownership

Một cách điều tra có hệ thống là đọc descriptor của mọi module trong `Configuration` rồi nhóm package theo owner.

Ví dụ helper:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ResolvedModule;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class PackageInspector {

    public static Map<String, List<String>> packageOwners(
            Configuration configuration) {

        Map<String, List<String>> owners = new TreeMap<>();

        for (ResolvedModule resolved : configuration.modules()) {
            String moduleName = resolved.name();

            for (String packageName :
                    resolved.reference().descriptor().packages()) {

                owners.computeIfAbsent(
                        packageName, unused -> new ArrayList<>())
                        .add(moduleName);
            }
        }

        return owners;
    }

    public static void printOverlaps(Configuration configuration) {
        packageOwners(configuration).forEach((pkg, modules) -> {
            if (modules.size() > 1) {
                System.err.println(
                        "Overlapping package " + pkg + " in " + modules);
            }
        });
    }
}
~~~

Sử dụng:

~~~java
Configuration cf = /* configuration đã resolve */;
PackageInspector.printOverlaps(cf);
~~~

Nếu có:

~~~text
Overlapping package com.acme.shared in
[com.acme.plugin.alpha, com.acme.plugin.beta]
~~~

đây là dấu hiệu rất mạnh cho việc `defineModulesWithOneLoader` sẽ không phù hợp với configuration đó.

Lưu ý: helper trên chỉ phát hiện package trùng **trong configuration đang xét**. Nó không tự kiểm tra split delegation qua parent loaders hay trạng thái class đã được loader định nghĩa trước đó. Nếu helper không in lỗi, không nên kết luận rằng layer chắc chắn instantiate thành công.

## 14. Cách kiểm tra JAR thực tế

Khi package overlap xuất hiện, cần xem artifact được đặt trên module path, không chỉ source trong repository.

Với explicit modular JAR:

~~~bash
jar --describe-module --file plugins/com.acme.plugin.alpha.jar
jar --describe-module --file plugins/com.acme.plugin.beta.jar
~~~

Để xem class entries:

~~~bash
jar --list --file plugins/com.acme.plugin.alpha.jar
jar --list --file plugins/com.acme.plugin.beta.jar
~~~

Ví dụ một package được đóng gói ở cả hai JAR:

~~~text
com/acme/shared/Utils.class
~~~

Ngay cả khi tên class không giống nhau, chỉ việc có hai entry dưới cùng package ở hai module đã là dấu hiệu nên xem lại package ownership.

Nếu build tool shading hoặc repackaging dependency đã copy package vào plugin JAR, hãy kiểm tra cấu hình shading. Một dependency tưởng như “dùng chung” có thể vô tình bị đóng gói bên trong nhiều modular JAR và tạo split package.

Giải pháp thường là:

- Đưa code dùng chung vào module có package owner duy nhất.
- Sử dụng `requires` tới module chung.
- Hoặc relocate package của dependency khi thực sự cần và bảo đảm descriptor/artifact được cập nhật nhất quán.

Không nên chỉ xóa một class để tránh trùng tên; cần giải quyết quyền sở hữu toàn package.

## 15. Phân biệt module path với classpath

Khi ứng dụng trước đây chạy trên classpath, các class có thể được nạp từ nhiều JAR mà không có module descriptor tường minh. Sau khi chuyển plugin sang named module trên module path, JPMS áp dụng những ràng buộc mới về package ownership, readability và loader mapping.

Ví dụ một framework cũ có:

~~~text
legacy-a.jar -> com.acme.util
legacy-b.jar -> com.acme.util
~~~

Khi cả hai JAR trở thành automatic modules hoặc explicit modules, tình huống chia package có thể dẫn đến lỗi module resolution hoặc layer instantiation, tùy module graph và cách tạo layer.

Đừng đánh đồng “chạy được trên classpath” với “có thể đưa nguyên xi lên module path”.

Một kế hoạch migration thường cần:

1. Xác định các JAR chứa package trùng.
2. Tách package dùng chung ra module riêng.
3. Cập nhật module descriptors.
4. Kiểm tra graph bằng công cụ JDK.
5. Chạy lại đúng cơ chế tạo custom layer mà host sử dụng.

## 16. Automatic module có thể ảnh hưởng thế nào?

JAR không có `module-info.class` khi đặt trên module path có thể được coi là automatic module. Tên module có thể được lấy từ manifest hoặc suy ra từ file name.

Automatic modules thường export packages rộng để hỗ trợ migration, nhưng điều này không loại bỏ các hạn chế của class loader mapping.

Nếu một automatic module và một explicit module chứa cùng package, hoặc hai automatic modules trùng package, có thể gặp conflict khi cả hai cùng phải được đọc hoặc định nghĩa vào loader theo cấu hình cụ thể.

Hãy kiểm tra tên module và package của từng JAR:

~~~bash
jar --describe-module --file libs/legacy-a.jar
jar --describe-module --file libs/legacy-b.jar
~~~

Đặc biệt cần để ý automatic module name được suy ra từ file name có thể không ổn định nếu artifact đổi tên.

Việc thêm `Automatic-Module-Name` có thể ổn định tên module chuyển tiếp, nhưng **không sửa split package**. Package ownership vẫn phải được xử lý bằng thiết kế hoặc packaging.

## 17. Kiểm tra cấu hình bằng công cụ JDK

Một vài lệnh hỗ trợ điều tra:

~~~bash
java --module-path plugins --list-modules
~~~

Lệnh này liệt kê các observable modules của module path đang dùng.

~~~bash
java --module-path plugins --describe-module com.acme.plugin
~~~

Lệnh này mô tả module descriptor mà launcher có thể quan sát.

~~~bash
java --module-path plugins --validate-modules
~~~

Tùy phiên bản JDK, `--validate-modules` kiểm tra module path và báo các vấn đề metadata/module conflict mà launcher phát hiện.

Khi chạy một ứng dụng modular:

~~~bash
java --show-module-resolution \
  --module-path mods:plugins \
  -m com.acme.host/com.acme.host.Main
~~~

`--show-module-resolution` hữu ích cho graph được phân giải khi **launcher khởi chạy ứng dụng**. Tuy nhiên, nếu host tạo custom layer sau đó bằng code, output của launcher không nhất thiết hiển thị đầy đủ các module được resolve động trong custom layer. Với lỗi layer runtime, cần log riêng configuration và module-to-loader mapping trong host.

Trên Windows, dấu phân cách module path thường là dấu chấm phẩy thay vì dấu hai chấm. Điều chỉnh lệnh theo hệ điều hành và shell.

## 18. Thêm logging đúng vị trí tạo layer

Để debug production, nên log những thông tin có giá trị trước khi gọi define:

~~~java
static void logConfiguration(Configuration cf) {
    System.out.println("Modules to define:");
    cf.modules().stream()
            .map(ResolvedModule::name)
            .sorted()
            .forEach(name -> System.out.println(" - " + name));
}
~~~

Ví dụ gọi:

~~~java
Configuration cf = /* resolved configuration */;
logConfiguration(cf);
PackageInspector.printOverlaps(cf);

try {
    ModuleLayer layer = ModuleLayer.boot()
            .defineModulesWithOneLoader(
                    cf, ClassLoader.getSystemClassLoader());

    System.out.println("Layer created: " + layer);
} catch (LayerInstantiationException ex) {
    System.err.println("Layer instantiation failed");
    ex.printStackTrace();
    throw ex;
}
~~~

Để dùng helper này, import `java.lang.module.ResolvedModule`. Với hệ thống lớn, log thêm:

- Danh sách parent layer và module trong parent configuration.
- Loader strategy đã chọn.
- Loader instance được mapping function trả về nếu dùng custom mapping.
- File/JAR location của từng module reference.
- Package overlap và các package được export từ parent layers.
- Root module names được truyền vào `resolve` hoặc `resolveAndBind`.

Tránh in thông tin nhạy cảm hoặc toàn bộ đường dẫn nội bộ ra log công khai nếu môi trường bảo mật yêu cầu giới hạn dữ liệu chẩn đoán.

## 19. Một chiến lược sửa lỗi theo từng nhóm nguyên nhân

### Trường hợp A: module có package trùng trong one-loader layer

Cách xử lý:

1. Xác nhận package trùng trong configuration.
2. Xác định package owner đúng.
3. Di chuyển class dùng chung sang một named module riêng hoặc đổi package ownership.
4. Cập nhật `requires` và đường dẫn import.
5. Build lại modular JARs.
6. Thử tạo layer lại với đúng configuration.

Không nên chỉ dùng `--add-exports`, vì export quyền truy cập không giải quyết xung đột package owner.

### Trường hợp B: split delegation tới parent loaders

Cách xử lý:

1. Xác định package nào được yêu cầu delegate.
2. Xem những parent module nào export package đó.
3. Xác định defining loader của từng module.
4. Thiết kế lại việc chia sẻ API/module giữa parent layers nếu cần.
5. Xem xét many-loaders hoặc custom loader mapping chỉ khi chúng thực sự tạo ánh xạ delegation nhất quán.

### Trường hợp C: custom loader đã giữ module/class cũ

Cách xử lý:

1. Xem loader mapping có trả về loader đã dùng cho phiên bản module trước hay không.
2. Kiểm tra loader có định nghĩa class trong package của module mới hay không.
3. Tạo loader mới cho thế hệ plugin mới, theo thiết kế lifecycle phù hợp.
4. Không nạp class trước khi định nghĩa module.
5. Tránh giữ class loader cũ qua cache, thread context loader hoặc static registry không cần thiết.

### Trường hợp D: package hoặc module dùng namespace bị cấm

Cách xử lý:

1. Tìm package `java` hoặc `java.*` trong artifact plugin.
2. Đổi package sang namespace thuộc ứng dụng.
3. Loại cấu hình cố định nghĩa module `java.base` ở layer tùy chỉnh.
4. Build lại và kiểm tra descriptor/package list.

## 20. Không nhầm với ClassNotFoundException, ClassCastException và InaccessibleObjectException

Có những lỗi xuất hiện **sau** khi layer đã được tạo:

| Exception | Thời điểm thường gặp | Câu hỏi chính |
|---|---|---|
| `LayerInstantiationException` | Khi định nghĩa custom layer | Module-to-loader mapping có hợp lệ không? |
| `ClassNotFoundException` | Khi tìm/nạp một class | Class có nằm trong loader/module được tìm kiếm không? |
| `NoClassDefFoundError` | Khi liên kết hoặc khởi tạo đường sử dụng class | Dependency/class trước đó có thất bại hoặc không thể tìm được không? |
| `ClassCastException` | Khi ép kiểu object | Hai type có cùng class identity không? |
| `IllegalAccessError` | Khi truy cập bị JVM từ chối | Readability, exports và Java access có cho phép không? |
| `InaccessibleObjectException` | Khi deep reflection không được phép | Package đã open cho module caller chưa? |
| `ServiceConfigurationError` | Khi tìm/khởi tạo service provider | `uses`, `provides`, resolution và provider hợp lệ chưa? |

Nếu `ModuleLayer.defineModules...` đã trả về layer thành công, lỗi sau đó thường cần được debug theo cơ chế class loading hoặc service loading, thay vì tiếp tục gọi chung là layer instantiation failure.

## 21. Đừng retry mù khi layer creation thất bại

Tạo layer không phải thao tác nên retry vô điều kiện. Với custom loader mapping, API không đảm bảo mọi trường hợp định nghĩa layer đều là thao tác nguyên tử; có thể có module đã được định nghĩa trước khi một phần thao tác thất bại.

Điều này đặc biệt quan trọng nếu ứng dụng map module mới vào **loader dùng lại**. Việc gọi lại với cùng loader mà không điều tra trạng thái đã thay đổi có thể làm lỗi khó chẩn đoán hơn.

Một chính sách an toàn hơn:

1. Giữ nguyên stack trace và thông tin configuration.
2. Không tự thử lại vào cùng loader sau exception.
3. Phân tích mapping/package conflict.
4. Chỉnh sửa artifact hoặc tạo bộ loader mới khi thiết kế cho phép.
5. Chạy test định nghĩa layer độc lập trước khi cho phép host nạp plugin vào production.

Không nên xóa cache hoặc đổi class loader global như một biện pháp cứu vãn không kiểm soát.

## 22. Ví dụ test đơn vị kiểm tra layer có tạo được không

Trong dự án plugin, nên có một integration test sử dụng **chính modular JARs cuối** và chiến lược loader của host.

Ví dụ JUnit 5:

~~~java
import org.junit.jupiter.api.Test;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertNotNull;

final class ModuleLayerIntegrationTest {

    @Test
    void createsPluginLayer() {
        Path plugins = Path.of("build/plugin-modules");

        ModuleLayer parent = ModuleLayer.boot();

        Configuration cf = parent.configuration().resolve(
                ModuleFinder.of(plugins),
                ModuleFinder.of(),
                Set.of("com.acme.plugin"));

        ModuleLayer layer = parent.defineModulesWithOneLoader(
                cf,
                ClassLoader.getSystemClassLoader());

        assertNotNull(layer.findModule("com.acme.plugin")
                .orElse(null));
    }
}
~~~

Test này cần thư mục `build/plugin-modules` thực sự chứa artifact module hợp lệ khi được chạy. Nó không chứng minh mọi class/plugin behavior hoạt động; test tiếp theo cần xác nhận service discovery và lời gọi API nếu host yêu cầu.

Nếu ứng dụng dùng many-loaders, test phải dùng chính `defineModulesWithManyLoaders`; nếu dùng custom mapping, test phải mô phỏng loader mapping thực tế. Thử một chiến lược khác rồi xem như đã xác nhận production là chưa đủ.

## 23. Checklist trước khi triển khai custom layer

- [ ] Đã xác định đúng root modules cần resolve.
- [ ] `ModuleFinder` trỏ tới đúng modular JARs hoặc exploded modules.
- [ ] `Configuration` được resolve từ đúng parent configuration.
- [ ] Parent layers được truyền đúng thứ tự và khớp với parent configurations.
- [ ] Biết sẽ dùng one-loader, many-loaders hay custom mapping.
- [ ] Với one-loader, không có overlapping packages trong configuration.
- [ ] Không có split delegation không thể giải quyết giữa các parent loaders.
- [ ] Với custom mapping, loader chưa định nghĩa trùng module name.
- [ ] Với custom mapping, loader chưa định nghĩa class thuộc package của module mới.
- [ ] Không cố định nghĩa module `java.base` hoặc package `java.*` trong custom layer.
- [ ] Plugin JAR không vô tình chứa bản sao package của module API dùng chung.
- [ ] Đã kiểm tra descriptor/JAR thực tế chứ không chỉ source.
- [ ] Đã ghi log phân biệt lỗi find, resolve và define.
- [ ] Không retry mù sau `LayerInstantiationException`.
- [ ] Có integration test tạo layer bằng artifact và loader strategy dùng ở production.

## 24. Ghi nhớ

`LayerInstantiationException` xuất hiện khi **không thể định nghĩa các module đã resolve thành một layer theo ánh xạ class loader được yêu cầu**. Đây là lỗi của giai đoạn định nghĩa layer; nó không đồng nghĩa mọi lỗi JPMS đều phát sinh từ dependency thiếu.

Những nhóm nguyên nhân đáng kiểm tra trước:

1. Hai hoặc nhiều module chứa **cùng package** khi buộc dùng một loader.
2. Một loader phải **delegate cùng package tới nhiều loader khác nhau**.
3. Custom loader đã có module cùng tên hoặc đã định nghĩa class trong package mà module mới muốn sở hữu.
4. Configuration chứa module/package thuộc namespace nền tảng bị cấm.
5. Parent layers, configuration và loader strategy không được phối hợp đúng (một số trường hợp cho ra exception khác, chẳng hạn `IllegalArgumentException`).

Hướng điều tra hiệu quả là **ghi lại stack trace → xác định resolve hay define → liệt kê module/package owners → kiểm tra loader mapping và parent layers → sửa package ownership hoặc loader strategy → thử lại từ cấu hình sạch**. Không dùng `--add-exports` hoặc `--add-opens` để “chữa” xung đột định nghĩa module, vì các cờ đó điều chỉnh truy cập package chứ không thay đổi ràng buộc layer instantiation.

### Tham khảo API

- Java SE 21, `java.lang.ModuleLayer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 21, `java.lang.LayerInstantiationException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/LayerInstantiationException.html
- Java SE 21, `java.lang.module.Configuration`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
