# Chuyển hệ thống sang module tường minh và khám phá trong ModuleLayer con

## 1. Mục tiêu của bài thực hành

Một ứng dụng Java có thể bắt đầu với **classpath**, nạp plugin JAR qua **URLClassLoader** và tìm implementation bằng **ServiceLoader** với các file **META-INF/services**. Khi hệ thống lớn lên, chúng ta muốn tổ chức ranh giới module rõ ràng hơn: SPI ở module công khai, host ở module riêng và implementation plugin trong **explicit named module** mà host không cần import. Đồng thời plugin được nạp vào một **ModuleLayer con** để có thể bổ sung hoặc thay phiên bản mà không đưa mọi plugin vào boot layer của JVM.

Bài này xây dựng một ví dụ **Java 17+ có thể chạy từ đầu đến cuối**, gồm ba named modules:

- **lab.api**: chứa interface SPI **lab.api.Greeting**, được dùng chung.
- **lab.host**: ứng dụng chủ, dùng SPI và gọi **ServiceLoader.load(layer, Greeting.class)**.
- **lab.provider**: plugin triển khai SPI, công bố provider bằng **provides ... with ...** và **không exports package implementation**.

Chúng ta sẽ compile ba module bằng javac, đóng **lab.provider** thành JAR, **chỉ đặt lab.api và lab.host trên module path để khởi chạy host**, sau đó để host tự tạo một child ModuleLayer từ JAR plugin. Cuối bài, bạn sẽ phân biệt được **discovery** với **module resolution**, kiểm tra đúng lớp và module đang chạy, xử lý lỗi module graph và hiểu cách phát triển kiến trúc để nâng cấp plugin.

Kết quả mong đợi:

1. Plugin **không nằm trong boot layer**.
2. Host tự tạo được **child ModuleLayer** chứa lab.provider.
3. **ServiceLoader** tìm được implementation từ child layer.
4. Host gọi SPI thành công, không phụ thuộc source class implementation.
5. Package implementation **không cần exports hay opens** cho host.
6. Interface SPI vẫn dùng **một bản Class identity** ở parent/boot layer.

**Phạm vi:** bài tập tập trung vào chuyển đổi, cách build/launch và khám phá module trong layer con; không coi ModuleLayer là sandbox hay hệ quản lý vòng đời plugin đầy đủ.

## 2. Trước và sau chuyển đổi

### 2.1. Kiến trúc classpath truyền thống

~~~text
app.jar + api.jar + provider.jar   (classpath)
  |
  +-- lab.api.Greeting
  +-- lab.provider.internal.SimpleGreeting
  +-- META-INF/services/lab.api.Greeting
  |
  +-- ServiceLoader.load(Greeting.class)
          -> tìm provider theo service configuration resource
~~~

Đăng ký provider trên classpath thường nằm trong file văn bản **META-INF/services/lab.api.Greeting** với nội dung **lab.provider.internal.SimpleGreeting**. Host có thể dùng ClassLoader phù hợp để đưa provider JAR vào phạm vi tìm kiếm.

Điểm hạn chế của một classpath chung:
- Không có module descriptor để quy định rõ **requires, exports, uses, provides**.
- Public class có thể bị consumer khác import trực tiếp, dù nhà phát triển chỉ muốn công khai SPI.
- Các JAR phụ thuộc có thể va chạm phiên bản trên classpath.
- Thêm plugin JAR vào một thư mục không đồng nghĩa application class loader đang chạy đã nhìn thấy nó.
- Việc thay class definition của plugin đã được load vẫn đòi hỏi quản lý class loader, cache và lifecycle.

**Classpath không sai**: với ứng dụng nhỏ hoặc SPI ổn định, ServiceLoader + JAR trên classpath là một giải pháp hợp lý. Chuyển sang JPMS là một quyết định kiến trúc cần điều kiện build/deploy tương ứng.

### 2.2. Kiến trúc explicit named modules và child layer

~~~text
BOOT LAYER
  lab.api  [exports lab.api]
     ^
     | requires
     |
  lab.host [requires lab.api; uses lab.api.Greeting]
     |
     | 1. ModuleFinder.of(pluginsDirectory)
     | 2. Configuration.resolve(..., root lab.provider)
     | 3. defineModulesWithOneLoader(...)
     v
CHILD MODULE LAYER
  lab.provider
    requires lab.api ---------------> dùng API từ BOOT LAYER
    provides lab.api.Greeting
       with lab.provider.internal.SimpleGreeting
    [không exports lab.provider.internal]

  ServiceLoader.load(childLayer, Greeting.class)
     -> provider object
     -> host sử dụng qua Greeting
~~~

**Lab.api** chỉ được định nghĩa trong boot layer, không copy vào child layer. Lab.provider thuộc layer mới, phụ thuộc API từ parent. Vì vậy khi host nhận một instance **Greeting** từ provider, nó có thể dùng chung đúng interface và không cần truy cập package implementation.

**Cảnh báo khái niệm:** ModuleLayer là một nhóm named modules đã được resolve cùng ánh xạ class loader. Nó không phải một thư mục JAR, cũng không phải một class loader duy nhất trong mọi chiến lược. ModuleLayer có parent layers; module trong child có thể phụ thuộc module ở parent, nhưng parent không tự có quyền import các implementation ở child.

## 3. Danh sách thay đổi khi chuyển từ classpath sang JPMS

| Vấn đề | Trước (classpath) | Sau (explicit named modules) |
| --- | --- | --- |
| API/SPI | Một JAR hoặc package dùng chung | Module **lab.api** với **exports lab.api** |
| Host | Class dùng SPI, loader/truy cập jar tùy thiết kế | Module **lab.host** với **requires lab.api** và **uses lab.api.Greeting** |
| Provider registration | **META-INF/services/lab.api.Greeting** | **provides lab.api.Greeting with ...** trong module-info.java |
| Provider dependencies | Phụ thuộc compile/runtime classpath | **requires lab.api** và module dependencies cần thiết |
| Implementation visibility | Public class có thể bị import nếu nằm trên classpath | Package implementation không exports/opens |
| Plugin discovery | ServiceLoader dùng class loader hoặc TCCL | **ServiceLoader.load(childLayer, Greeting.class)** |
| Runtime visibility | JAR được loader nhìn thấy | Module được **finder tìm, resolve, định nghĩa** trong layer |
| Thay plugin | Quản lý JAR và loader mới nếu class đã load | Quản lý JAR, layer/loader mới và cutover; không tự hot swap |
| Quản trị lỗi | ClassNotFoundException, ServiceConfigurationError và linkage | Thêm FindException, ResolutionException, LayerInstantiationException, access checks |
| Kiểm thử | Chỉ classpath có thể che lỗi modules | Biên dịch và chạy **module path thật** |

**Không cần duy trì hai nguồn đăng ký song song** cho cùng provider chỉ để hỗ trợ explicit module. Với explicit named module, **provides** là nguồn khai báo provider chính. Một JAR không có module-info.class nhưng được đặt trên module path có thể thành **automatic module**; automatic module không tương đương explicit module và không cho cùng mức đóng gói.

## 4. Chuẩn bị môi trường

Ví dụ yêu cầu:
- **JDK 17 hoặc mới hơn** có công cụ **java**, **javac** và **jar** trên PATH.
- Quyền tạo file trong một thư mục demo.
- Terminal bash trên Linux/macOS hoặc PowerShell trên Windows.
- Không dùng Maven/Gradle và không yêu cầu dependency ngoài JDK.

Xác nhận toolchain:

~~~bash
java -version
javac -version
jar --version
~~~

**Mục tiêu build** là Java 17 thông qua **javac --release 17**, kể cả khi compiler trên máy bạn mới hơn. Cờ này kiểm soát language/class-file/platform API release, nhưng bản demo được vận hành trong môi trường có hỗ trợ module system và các API Java 17.

Tạo cấu trúc tệp như sau (các đường dẫn là tương đối so với thư mục **demo**):

~~~text
demo/
├── src/
│   ├── lab.api/
│   │   ├── module-info.java
│   │   └── lab/api/Greeting.java
│   ├── lab.provider/
│   │   ├── module-info.java
│   │   └── lab/provider/internal/SimpleGreeting.java
│   └── lab.host/
│       ├── module-info.java
│       └── lab/host/Main.java
├── mods/                    # Sinh khi biên dịch
│   ├── lab.api/
│   ├── lab.provider/
│   └── lab.host/
└── plugins/                 # Sinh khi đóng gói
    └── lab.provider.jar
~~~

**Tên thư mục dưới src là tên module** tương ứng với cách dùng **--module-source-path src**. Mỗi module có một **module-info.java** ở gốc thư mục module. File lab.provider.jar được đặt riêng ngoài module path của host lúc startup để plugin được resolve trong child layer.

## 5. Viết module API: lab.api

File **src/lab.api/module-info.java**:

~~~java
module lab.api {
    exports lab.api;
}
~~~

File **src/lab.api/lab/api/Greeting.java**:

~~~java
package lab.api;

public interface Greeting {
    String greet(String name);
}
~~~

Giải thích:
- **exports lab.api** cho các module khác truy cập các public types của package API.
- **Greeting** là hợp đồng mà cả host lẫn provider đều dùng.
- Không đưa logic triển khai vào lab.api.
- Version và behavioral contract của Greeting cần do nền tảng công bố; việc module hóa không thay thế quản lý binary compatibility.

Nếu lab.api có nội bộ implementation/helper, hãy đặt chúng ở package không export. Nếu SPI dùng DTO trong signature, các DTO và package cần thiết cũng phải accessible theo thiết kế.

## 6. Viết module provider: lab.provider

File **src/lab.provider/module-info.java**:

~~~java
module lab.provider {
    requires lab.api;
    provides lab.api.Greeting with lab.provider.internal.SimpleGreeting;
}
~~~

File **src/lab.provider/lab/provider/internal/SimpleGreeting.java**:

~~~java
package lab.provider.internal;

import lab.api.Greeting;

public final class SimpleGreeting implements Greeting {
    public SimpleGreeting() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Ý nghĩa các chỉ thị:
- **requires lab.api**: module provider đọc được module chứa SPI.
- **provides lab.api.Greeting with lab.provider.internal.SimpleGreeting**: provider registration được ghi trong **module descriptor**, không còn phụ thuộc việc tìm một META-INF/services resource trên classpath.
- **Không có exports lab.provider.internal**: mã lab.host không thể import class implementation như một API công khai.
- **Không có opens lab.provider.internal**: không mở package nội bộ cho deep reflection của host.

Lớp **SimpleGreeting** vẫn là public và có **public constructor không tham số**, đúng yêu cầu của đường provider constructor trong explicit named module. ServiceLoader có cơ chế riêng để tạo provider đã khai báo trong module descriptor mà không yêu cầu package implementation export cho consumer.

**Một điểm rất dễ nhầm:** “Không export package” và “provider class không public” là hai vấn đề khác nhau. Không export package là ranh giới giữa modules; class được ghi trực tiếp sau **with** vẫn phải đáp ứng điều kiện provider type. Với Java 17, explicit named module cũng có mô hình public static **provider()** hợp lệ cho provider factory, nhưng ví dụ này cố ý chọn constructor để dễ theo dõi.

Không cần thêm **exports lab.provider.internal to lab.host** chỉ để ServiceLoader hoạt động; làm vậy sẽ làm mất ranh giới API mà chúng ta đang muốn giữ.

## 7. Viết module host: lab.host

File **src/lab.host/module-info.java**:

~~~java
module lab.host {
    requires lab.api;
    uses lab.api.Greeting;
}
~~~

File **src/lab.host/lab/host/Main.java**:

~~~java
package lab.host;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;
import lab.api.Greeting;

public final class Main {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: Main <plugins-directory>");
        }

        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        Configuration config = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("lab.provider"));
        ModuleLayer child = boot.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

        System.out.println("Provider in boot: " +
                boot.findModule("lab.provider").isPresent());
        System.out.println("Provider in child: " +
                child.findModule("lab.provider").isPresent());

        int count = 0;
        for (Greeting provider : ServiceLoader.load(child, Greeting.class)) {
            System.out.println("Provider module: " +
                    provider.getClass().getModule().getName());
            System.out.println("Greeting: " + provider.greet("Java"));
            System.out.println("API in boot layer: " +
                    (Greeting.class.getModule().getLayer() == boot));
            System.out.println("Implementation exported: " +
                    provider.getClass().getModule().isExported(
                            "lab.provider.internal", Main.class.getModule()));
            count++;
        }
        System.out.println("Providers found: " + count);
        if (count == 0) {
            throw new IllegalStateException("No plugin provider discovered");
        }
    }
}
~~~

Đọc từng bước trong Main:

1. **ModuleLayer.boot()** lấy layer ban đầu chứa lab.host, lab.api và các module Java đã được resolve khi launch.
2. **Path.of(args[0])** lấy đường dẫn thư mục **plugins** do caller truyền; ở đây thư mục chứa **lab.provider.jar** đã được đóng gói.
3. **ModuleFinder.of(Path.of(args[0]))** xây module finder, nhìn thấy những modular JAR hoặc exploded modules trên đường dẫn đó.
4. **boot.configuration().resolve(finder, ModuleFinder.of(), Set.of("lab.provider"))** tạo một **Configuration mới**, với parent configuration là boot và root module **lab.provider** phải tìm được. Vì lab.provider **requires lab.api**, quá trình resolution nhìn thấy lab.api đã được resolve trong parent configuration.
5. **boot.defineModulesWithOneLoader(config, ClassLoader.getSystemClassLoader())** định nghĩa các module trong configuration mới thuộc một child ModuleLayer. Chiến lược này dùng **một new class loader cho modules được định nghĩa trong layer mới**, với class loader cha được truyền vào. Nó không di chuyển lab.api khỏi boot layer.
6. **ServiceLoader.load(child, Greeting.class)** tìm service provider trong child layer và các parent layers theo quy tắc API, rồi trả các provider để host duyệt.
7. Host gọi **greet()** qua interface, in tên module thực tế và xác minh package implementation không export cho host.
8. Nếu không tìm thấy provider, host ném IllegalStateException để bài thực hành thất bại rõ ràng thay vì âm thầm kết thúc.

**Vì sao lab.host có uses?** Khi module có code gọi ServiceLoader cho một service, khai báo **uses lab.api.Greeting** là một phần hợp đồng JPMS. **requires lab.api** chỉ cho host tham chiếu kiểu Greeting; nó **không thay** cho uses.

**Vì sao lab.host không requires lab.provider?** Host không nên tạo dependency tĩnh tới implementation plugin. Host chỉ requires API. Module provider là root mà host chọn khi resolve child layer, nên code host không cần import hoặc requires provider module.

**Điểm tinh tế:** **child.findModule("lab.provider")** có thể tìm module trong child hoặc parent layers; riêng trong ví dụ, boot không có lab.provider, nên hai dòng “in boot: false” và “in child: true” chứng minh provider được đưa vào layer mới. Nếu cần liệt kê đúng những module trực tiếp thuộc child, dùng **child.modules()**.

**Kiểm tra an toàn:** ModuleFinder đọc metadata module, nhưng đó không phải bước xác minh chữ ký, nguồn gốc hay độ an toàn của plugin. Trong production, hãy kiểm tra file JAR và quyền trước khi build layer hoặc instantiate provider.

## 8. Biên dịch ba module với javac

### 8.1. Lệnh chung trên Linux/macOS

Đứng trong thư mục **demo** (nơi chứa src/), chạy:

~~~bash
mkdir -p plugins
javac --release 17 --module-source-path src -d mods \
  -m lab.api,lab.provider,lab.host
jar --create --file plugins/lab.provider.jar -C mods/lab.provider .
~~~

Lệnh **javac** dùng module-source-path để hiểu các thư mục theo module name và sinh tệp **module-info.class** cùng các class files. Lệnh **jar** gói output của lab.provider thành JAR tường minh.

### 8.2. Lệnh tương đương trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force plugins | Out-Null
javac --release 17 --module-source-path src -d mods -m lab.api,lab.provider,lab.host
jar --create --file plugins/lab.provider.jar -C mods/lab.provider .
~~~

Các lệnh dùng dấu phân cách thư mục tương đối mà Java tools có thể xử lý trên Windows. Lưu ý PowerShell không dùng dấu **\\** của bash để nối dòng lệnh; trong ví dụ Windows mỗi lệnh javac nằm trên một dòng.

### 8.3. Xác minh plugin.jar thật sự là explicit named module

~~~bash
jar --describe-module --file plugins/lab.provider.jar
~~~

Output có thể chứa đường dẫn artifact tuyệt đối khác nhau theo máy, nhưng những phần quan trọng cần nhìn thấy là:

~~~text
lab.provider
requires java.base mandated
requires lab.api
provides lab.api.Greeting with lab.provider.internal.SimpleGreeting
contains lab.provider.internal
~~~

**lab.provider** phải có descriptor và chỉ thị **provides**. Nếu jar --describe-module cho biết **automatic module** hoặc không thấy provides, hãy kiểm tra quá trình build và module-info.class trong JAR, không tiếp tục giả định mọi thứ đã được module hóa.

Vì lab.provider.internal không exports/opens, descriptor thường có dòng **contains lab.provider.internal** thay vì dòng exports cho package đó. Điều này là có chủ đích.

## 9. Khởi chạy host mà không resolve plugin ở boot

Đây là **bước then chốt** của bài. Khi launch, chỉ đưa hai module **lab.api** và **lab.host** vào **--module-path**; plugin JAR nằm riêng trong thư mục **plugins** để **ModuleFinder** của host tìm và tạo layer mới.

**Linux/macOS:**

~~~bash
java --module-path "mods/lab.api:mods/lab.host" \
  -m lab.host/lab.host.Main plugins
~~~

**Windows PowerShell:**

~~~powershell
java --module-path "mods/lab.api;mods/lab.host" -m lab.host/lab.host.Main plugins
~~~

Dấu phân cách giữa hai module-path entries là **:** trên Linux/macOS và **;** trên Windows. Đường dẫn **plugins** là **argument của chương trình Main**, không phải một phần --module-path của boot.

**Output chính xác của ví dụ:**

~~~text
Provider in boot: false
Provider in child: true
Provider module: lab.provider
Greeting: Hello, Java!
API in boot layer: true
Implementation exported: false
Providers found: 1
~~~

Giải thích từng kết quả:
- **Provider in boot: false**: JVM khởi chạy không resolve lab.provider vào boot layer.
- **Provider in child: true**: host tự resolve và define lab.provider trong child layer.
- **Provider module: lab.provider**: object được tạo từ named module của plugin, không phải classpath/unnamed module.
- **Greeting: Hello, Java!**: host gọi interface lab.api.Greeting và nhận kết quả từ implementation.
- **API in boot layer: true**: SPI được dùng từ parent/boot layer, không có một bản định nghĩa API bị nhân đôi trong child.
- **Implementation exported: false**: package provider không export cho lab.host mà ServiceLoader vẫn hoạt động.
- **Providers found: 1**: chỉ có một provider được đăng ký theo cấu hình ví dụ.

**Quan sát thêm:** Output không chứa tên đường dẫn tuyệt đối hoặc địa chỉ class loader, vì các giá trị đó thay đổi tùy máy. Các câu lệnh in có chủ đích dùng những giá trị boolean và tên module ổn định để có thể đối chiếu trên nhiều hệ điều hành.

## 10. Nối các bước lại với nhau: ai chịu trách nhiệm phần nào?

| Bước | API/cơ chế | Ai chịu trách nhiệm? |
| --- | --- | --- |
| Phát hành lab.provider.jar | javac, jar, build pipeline | Nhà phát triển provider/build system |
| Kiểm tra JAR/version/trust | Registry, checksum, chính sách | Host/deployment pipeline |
| Chọn thư mục plugins | Path và cấu hình ứng dụng | Host |
| Tìm module artifact | ModuleFinder.of(...) | Java API cung cấp; host chọn path |
| Giải quyết module graph | Configuration.resolve(...) | Module system; host chọn root/finder |
| Định nghĩa layer/loader | ModuleLayer.defineModulesWithOneLoader(...) | Module system theo cấu hình của host |
| Khám phá provider | ServiceLoader.load(child, Greeting.class) | ServiceLoader, với layer mà host cấp |
| Tạo provider | Provider constructor hoặc provider method | ServiceLoader khi được duyệt/yêu cầu |
| Chọn plugin theo ID/version/policy | Registry và business rules | Host |
| start(), health, handle(), stop() | SPI lifecycle do ứng dụng định nghĩa | Host |
| Cập nhật version và rollback | Layer mới, routing, cleanup | Host |
| Kiểm soát mã không đáng tin | Process/container isolation, permissions | Host/platform |

**ModuleLayer không thay thế ServiceLoader** và ServiceLoader cũng **không tự resolve hoặc define ModuleLayer từ thư mục plugins**. Đó là hai nửa khác nhau của quy trình: host có một graph module hợp lệ, sau đó yêu cầu ServiceLoader khám phá providers trong graph ấy.

## 11. Vì sao dùng ModuleFinder, resolve và define theo thứ tự này?

### 11.1. ModuleFinder chỉ tìm metadata khả dụng

~~~java
// Mảnh minh họa; path là Path đã được kiểm chứng.
ModuleFinder finder = ModuleFinder.of(path);
~~~

Finder có thể tìm module descriptor trong modular JAR, exploded module và automatic modules ở những vị trí được hỗ trợ. **Tìm thấy JAR** không có nghĩa nó đã được resolve, class đã được load hoặc provider đã được khởi tạo. Muốn xem tên module có thể tìm thấy, có thể dùng **finder.findAll()** theo chính sách validation của host.

Một JAR legacy không chứa module-info.class nhưng được đưa lên module path có thể được xem là automatic module. Bài thực hành yêu cầu explicit module, nên kiểm tra descriptor thay vì coi mọi tên do ModuleFinder trả về là một cuộc chuyển đổi thành công.

### 11.2. Configuration.resolve kiểm tra phụ thuộc

~~~java
// Mảnh minh họa sau khi đã có parent configuration và finder.
Configuration config = parent.configuration().resolve(
        finder, ModuleFinder.of(), Set.of("lab.provider"));
~~~

**Set.of("lab.provider")** chỉ rõ root module cần resolve. Các phụ thuộc **requires** sẽ được giải quyết từ finder và parent configurations theo quy tắc JPMS. Nếu thiếu lab.api hoặc đặt sai module name, resolution sẽ thất bại trước khi có provider để gọi.

Trong demo, lab.api đã được resolve vào boot. Điều này quan trọng cho type identity: **đừng tạo bản lab.api mới trong child nếu định dùng Greeting.class của host từ boot**. Nếu một plugin có dependency riêng, mô hình version resolution cần được thiết kế cẩn thận; JPMS không phải bộ giải quyết version theo kiểu Maven/Gradle.

**resolve** và **resolveAndBind** không giống nhau. **resolveAndBind** có thêm service binding trong quá trình resolution để thêm modules cung cấp các services được sử dụng theo quy tắc API; demo dùng **resolve** cùng một root provider rõ ràng để giải thích rành mạch và có kết quả xác định. Khi có nhiều plugin hoặc module dùng service khác, cân nhắc cách resolution phù hợp với yêu cầu của hệ thống.

### 11.3. defineModulesWithOneLoader định nghĩa module và loader

~~~java
// Mảnh minh họa; config đã được resolve theo parent.
ModuleLayer child = parent.defineModulesWithOneLoader(
        config, ClassLoader.getSystemClassLoader());
~~~

Cấu hình này định nghĩa các modules trong config bằng một loader mới phù hợp với parent loader được chỉ định. Trong ví dụ chỉ có module provider mới, nên cách này đủ đơn giản.

Với nhiều plugins có dependencies xung đột hoặc yêu cầu cô lập khác nhau:
- Cân nhắc **defineModulesWithManyLoaders** hoặc nhiều child layers độc lập.
- Đặt API/SPI chung ở parent layer, không để một plugin tự tạo bản API với identity khác.
- Xem kỹ quy tắc packages trong một module graph và các trường hợp trùng/split package.
- Không dựa vào class loader như một biện pháp sandbox cho mã không đáng tin.
- Test thực tế class identity và ServiceLoader visibility khi thêm layer lồng nhau.

Một ModuleLayer có thể được garbage collected khi không còn reachable, nhưng **không có một thao tác ModuleLayer.close() tiêu chuẩn để chủ động unload toàn bộ class ngay lập tức**. Quản lý vòng đời plugin là trách nhiệm của host.

## 12. ServiceLoader.load(layer, service) hoạt động ra sao?

Với JPMS, **ServiceLoader.load(childLayer, Greeting.class)** khám phá providers trong child layer và các ancestor layers theo contract API. Điều này có hai hệ quả:

1. **Provider của parent layer cũng có thể xuất hiện**. Không giả định kết quả luôn chỉ gồm các modules được định nghĩa trực tiếp trong child. Nếu cần “chỉ plugin trong child”, host phải đặt chính sách lọc theo module/layer/registry.
2. **Provider được khai báo bởi module descriptor** qua provides, không phải vì host import implementation class. Class provider có thể nằm trong package không export.

**Provider discovery và instantiation thường lazy.** Tạo ServiceLoader chưa đồng nghĩa mọi provider đã được khởi tạo. Khi duyệt iterator hoặc lấy Provider.get(), JDK có thể nạp và khởi tạo; lỗi cấu hình có thể xuất hiện tại bước duyệt thay vì khi tạo ServiceLoader.

Một cách quan sát provider type trước khi lấy instance là **ServiceLoader.stream()**:

~~~java
// Mảnh Java minh họa: child và Greeting đã có.
// Cần thực hiện trong module khai báo uses lab.api.Greeting.
ServiceLoader<Greeting> services = ServiceLoader.load(child, Greeting.class);
for (ServiceLoader.Provider<Greeting> entry : services.stream().toList()) {
    System.out.println(entry.type().getName());
}
~~~

**type()** có thể giúp đọc kiểu mà không gọi constructor provider ngay; **get()** yêu cầu lấy provider instance. Với explicit module có factory provider() hợp lệ, kiểu từ Provider.type() có thể là kiểu trả về, không phải bản thân factory. **Không coi type() là kiểm toán độ an toàn** của bytecode.

Nếu muốn chỉ nhận providers thuộc layer mới và đã có object:
~~~java
// Mảnh minh họa sau khi chọn đúng child; không phải chương trình riêng.
for (Greeting item : ServiceLoader.load(child, Greeting.class)) {
    if (item.getClass().getModule().getLayer() != child) {
        continue;
    }
    // Host xác minh ID, version, hợp đồng và quyền trước activation.
}
~~~

Cách lọc trên **có thể đã instantiate provider trước khi kiểm tra**. Với nguồn không đáng tin, hãy kiểm tra artifact/metadata trước khi resolve hoặc gọi ServiceLoader, không dựa vào filter sau constructor để phòng side effects.

## 13. Vì sao uses và provides là điều kiện khác với requires?

**requires lab.api** trong host/provider cho phép mã tham chiếu kiểu Greeting theo module readability. **exports lab.api** công bố public interface cho module khác. Hai chỉ thị này chưa nói rằng mã trong host dùng dịch vụ động hoặc module provider đăng ký implementation.

**uses lab.api.Greeting** ghi rõ module **lab.host** là consumer của service. ServiceLoader khi được gọi từ named module phải tuân thủ điều kiện uses theo quy tắc JSR 376/JPMS.

**provides lab.api.Greeting with lab.provider.internal.SimpleGreeting** ghi rõ module **lab.provider** cung cấp implementation. Chỉ thị **with** phải trỏ tới provider type nằm trong đúng module provider và đáp ứng điều kiện mà JPMS/ServiceLoader yêu cầu.

Một phản ví dụ thường gặp:

~~~java
// Mảnh module-info.java sai về ý đồ: KHÔNG thay cho uses.
module lab.host {
    requires lab.api;
    // thiếu uses lab.api.Greeting;
}
~~~

Ngay cả khi host compile được code sử dụng class Greeting, thiếu uses có thể khiến **service loading từ named module bị từ chối**. Sửa **module-info.java**, không phải thêm requires lab.provider hoặc export package nội bộ.

**Một phản ví dụ khác:** module provider có class implements Greeting nhưng không có provides. JVM không tự quét mọi .class trong một named module để tìm implementation. Cần đăng ký provider theo module descriptor; với automatic/classpath providers quy tắc khác.

**Không sửa bằng cách exports lab.provider.internal** chỉ để host gọi reflection vào provider constructor. Việc đó thường phá encapsulation và che đi lỗi thiết kế discovery.

## 14. Bài tập xác minh và các lỗi chủ động

### 14.1. Bỏ plugin.jar khỏi thư mục plugins

Nếu **ModuleFinder.of** không thấy lab.provider và **Set.of("lab.provider")** vẫn được dùng làm root, resolution thất bại vì root module không được tìm thấy. Đây không giống tình huống “ServiceLoader duyệt được nhưng trả zero providers”.

**Phân biệt:**
- Không tìm thấy module root → lỗi ở **module discovery/resolution**.
- Có module root nhưng không có provides → có thể **không có provider** tương ứng.
- Có provides nhưng provider class không hợp lệ → **ServiceConfigurationError** khi service loading.
- Có instance nhưng greet() lỗi → lỗi ở **application contract/runtime**, không phải ModuleFinder.

### 14.2. Đổi tên module trong provider descriptor

Nếu module-info.java ghi **module lab.other** nhưng host vẫn resolve root **lab.provider**, module finder không có root lab.provider. Hãy chọn module name có chủ đích, đồng bộ build, registry và code resolution.

### 14.3. Bỏ requires lab.api ở provider

Provider source cần type lab.api.Greeting; không có readability hợp lệ sẽ gây lỗi khi compile named module. Hãy thêm đúng requires thay vì chuyển interface sang package implementation.

### 14.4. Bỏ uses khỏi host

Host vẫn có thể tham chiếu Greeting qua requires, nhưng module chứa lời gọi ServiceLoader thiếu khai báo sử dụng service. Kiểm tra lỗi service loading và module descriptor. **requires không thay uses**.

### 14.5. Bỏ provides khỏi provider

Provider vẫn có thể compile như một class bình thường, nhưng ServiceLoader không nhận thông tin rằng module ấy cung cấp Greeting. Dù module đã resolve trong child, **được resolve không đồng nghĩa được đăng ký làm service provider**.

### 14.6. Đưa cả provider.jar lên boot module path

Nếu đưa lab.provider.jar vào module path của boot và nó được resolve ở launch (qua roots hoặc service binding), provider có thể nằm trong boot layer. Khi đó bài thực hành không còn kiểm chứng mô hình “provider chỉ ở child”, và việc định nghĩa lại cùng module vào child có thể gây những hệ quả module graph/layer khác với ý định.

Để giữ phép thử rõ ràng: **boot chỉ có lab.api và lab.host; thư mục plugins được tìm qua ModuleFinder ở runtime**.

### 14.7. Đưa một bản lab.api khác vào child layer

Nếu plugin mang bản sao API/SPI và graph/loader để class đó được định nghĩa riêng, host có thể gặp class identity mismatch, linkage hoặc ClassCastException. Nên đặt API ổn định ở parent và chỉ đưa provider + dependency riêng vào child, có kiểm tra hợp đồng phiên bản.

### 14.8. Đổi package implementation sang package-private

Class provider được ghi trực tiếp sau with cần thỏa điều kiện visibility/provider constructor/factory method của JPMS. Không export package không đồng nghĩa class provider được phép tùy tiện package-private. Với ví dụ này, SimpleGreeting là **public class** với public no-arg constructor; việc package vẫn không exports chỉ hạn chế truy cập từ module khác.

## 15. Các loại lỗi cần theo dõi

| Triệu chứng/exception | Thường xuất hiện ở đâu? | Cách xử lý |
| --- | --- | --- |
| **FindException** | ModuleFinder / resolve không tìm được hoặc không đọc được module | Kiểm tra đường dẫn, tên module, file JAR và descriptor |
| **ResolutionException** | Configuration không giải quyết được graph | Kiểm tra requires, module dependencies, constraints và packages |
| **LayerInstantiationException** | Define layer/loader thất bại | Kiểm tra cấu trúc module graph, loader và package conflicts |
| **ServiceConfigurationError** | ServiceLoader đọc provides và tạo provider thất bại | Kiểm tra uses/provides, constructor/provider method, cause |
| **NoClassDefFoundError** | Link/load provider hoặc dependency | Kiểm tra class thực tế trên module path, JNI/dependency và cause |
| **IllegalAccessError** | Module access hoặc Java member visibility | Kiểm tra exports/opens/readability và API contract |
| **ClassCastException** | API identity không trùng hoặc kiểu sai | Kiểm tra defining loader, module và SPI shared |
| **NoSuchMethodError** | Plugin bytecode gọi binary API không có ở runtime | Khóa version SPI/dependency và test contract |
| Có provider nhưng không gọi được nghiệp vụ | Host lifecycle hoặc API behavior | Kiểm tra version, thread safety, config và tests |
| Layer cũ còn giữ bộ nhớ | Provider/loader/thread/callback vẫn reachable | Host quản lý stop/close/remove references |

**ServiceConfigurationError là một Error**, không phải checked exception; nên bắt có chủ đích ở ranh giới discovery và quyết định quarantine/reject plugin, không nuốt mọi Throwable. Exception của **greet()**, **start()** hoặc **stop()** do host xử lý theo hợp đồng ứng dụng, không tự chuyển thành chính sách fallback của ServiceLoader.

Có thể dùng công cụ:
- **jar --describe-module --file plugins/lab.provider.jar**: kiểm tra module descriptor và provides.
- **jar --list --file plugins/lab.provider.jar**: kiểm tra module-info.class và class files được đóng gói.
- **jdeps --module-path ... plugins/lab.provider.jar**: quan sát static module/library dependencies theo cách phù hợp với artifact.
- **ModuleLayer.boot().modules()** và **child.modules()**: xem modules trực tiếp trong mỗi layer.
- **provider.getClass().getModule()**: xác định module của provider thật sự được trả về.
- **provider.getClass().getClassLoader()**: kiểm tra loader mà JVM dùng.
- **ServiceLoader.load(child, Greeting.class)**: kiểm tra discovery gắn với đúng layer.

Những công cụ trên bổ sung cho nhau; không có một lệnh nào thay thế được integration tests.

## 16. Nâng cấp plugin trong mô hình child ModuleLayer

Ví dụ này nạp một plugin lần đầu. Trong production, hot update là một **quy trình do host điều phối**, không phải chỉ thay file JAR rồi gọi **ServiceLoader.reload()**:

~~~text
Plugin v1 ACTIVE (child layer L1)
      |
      +--> Nhận plugin-v2.jar, verify signature/hash/version/permissions
      |
      v
Host tạo ModuleFinder cho artifact v2
      |
      v
Resolve Configuration v2 và define ModuleLayer L2 riêng
      |
      v
ServiceLoader.load(L2, SPI) + contract checks
      |
      v
Host cấu hình, start và health-check provider v2
      |
      +-- FAIL --> Giữ v1, dọn resource v2, báo lỗi
      |
      v
Chuyển traffic mới sang v2
      |
      v
Drain request cũ, stop v1, gỡ callback/thread/TCCL/reference
      |
      v
Cho phép layer L1 và loader của nó được GC khi không còn tham chiếu
~~~

**ModuleLayer không có hàm close/unload tổng quát**. Thư viện/plugin có thể giữ thread, scheduler, connection, static callbacks hoặc context class loader, khiến object cũ không được thu gom. Host cần chính sách lifecycle, timeout, rollback và leak detection. ServiceLoader.reload() chỉ xóa cache của một ServiceLoader; nó không định nghĩa lại module code đã load trong layer cũ.

Mỗi child layer có thể cùng khai báo **module name** của plugin ở các phiên bản khác nhau nếu được tạo thành các graph/layer riêng phù hợp, nhưng phải quản lý isolation và version routing cẩn thận. Đừng đặt hai JAR cùng module name và packages xung đột vào cùng một finder/configuration rồi hy vọng JPMS tự chọn bản “mới nhất”.

Với hệ thống đa tenant hoặc plugin độc lập, cân nhắc một layer/loader riêng cho mỗi nhóm plugin khi có lý do cô lập dependency. Tránh lạm dụng nhiều layers nếu chỉ có một vài extension ổn định; complexity vận hành có thể vượt lợi ích.

## 17. Kiến trúc migration tăng dần, không cần chuyển mọi JAR cùng lúc

Một ứng dụng lớn có thể chuyển theo từng bước:

1. **Tách API/SPI ra module ổn định** và giảm những class implementation bị host import trực tiếp.
2. **Chuyển host sang named module** có requires + uses, xác nhận khởi chạy với module path.
3. **Chuyển từng provider JAR sang explicit module**, viết requires + provides, giữ package implementation không export.
4. **Giữ API ở parent boot layer**, không copy SPI vào mỗi plugin artifact.
5. **Thêm một plugin resolver/layer builder** vào host, trước hết chỉ hỗ trợ một provider đã kiểm thử như bài này.
6. **Thêm validation và registry**: module name, version, artifact hash, API range, dependency policy.
7. **Thêm lifecycle manager**: start/health/stop, update/rollback, routing và leak detection.
8. **Di chuyển thêm plugin**, có test cùng lúc nhiều providers, lỗi dependency và lớp/module visibility.
9. **Gỡ đường classpath cũ** khi tất cả những plugin cần hỗ trợ đã qua migration, hoặc duy trì một compatibility bridge được thiết kế có chủ đích.

Nếu thư viện bên thứ ba chưa có module-info.java, automatic modules có thể giúp chuyển tiếp trên module path, nhưng không cung cấp cùng sự đóng gói chặt như explicit modules. Đừng nhầm việc “đặt JAR lên module path” với việc nhà phát triển đã thật sự mô tả requires/exports/uses/provides.

Với những plugin legacy chỉ có service configuration file, một hướng thực tế là build lại với module-info.java và đăng ký **provides** chính xác. Khi chuyển, kiểm tra bằng cả **jar --describe-module** và test discovery trong **ModuleLayer con**, vì lỗi không được phát hiện nếu các bài test vẫn chạy hoàn toàn trên classpath.

## 18. Các tiêu chí nghiệm thu của bài thực hành

| Kiểm tra | Kết quả đạt yêu cầu |
| --- | --- |
| javac --release 17 biên dịch cả ba explicit modules | Không lỗi compiler |
| lab.provider.jar chứa module-info.class | jar --describe-module hiển thị lab.provider |
| lab.provider descriptor có requires lab.api | Phụ thuộc SPI rõ ràng |
| lab.provider descriptor có provides Greeting with SimpleGreeting | Service registration đúng |
| lab.host descriptor có uses lab.api.Greeting | Consumer khai báo use |
| Launch module path chỉ có lab.api và lab.host | lab.provider không resolve trong boot |
| ModuleFinder nhìn thấy lab.provider.jar | Có module root cần resolve |
| Configuration.resolve + defineModulesWithOneLoader thành công | child layer có lab.provider |
| ServiceLoader.load(child, Greeting.class) có provider | Có ít nhất một instance trong ví dụ |
| Greeting trả “Hello, Java!” | Host dùng API chung thành công |
| Greeting.class có module trong boot layer | Không duplicate SPI ở child |
| Package provider.internal không export cho host | Implementation đóng gói đúng |
| Không thay đổi source khi thêm provider mới phù hợp SPI | Host phụ thuộc hợp đồng, không phụ thuộc implementation |

### Câu hỏi tự kiểm tra

**1. Tại sao host phải dùng ServiceLoader.load(childLayer, Greeting.class) thay vì mặc định load(Greeting.class)?**  
Vì một plugin được resolve trong layer con có thể không nằm trong phạm vi tra cứu mà overload mặc định dùng qua thread context class loader. Chỉ định layer giúp host chủ động xác định nơi khám phá dịch vụ.

**2. Tại sao phải có uses trong module host?**  
requires chỉ tạo readability đối với API. uses công bố module host tiêu thụ service động, để ServiceLoader kiểm tra đúng hợp đồng JPMS.

**3. Tại sao package implementation không exports mà host vẫn gọi được greet()?**  
Host gọi phương thức của interface **lab.api.Greeting** vốn được export từ parent. ServiceLoader có cơ chế tạo provider hợp lệ trong named module dù package implementation không export cho host.

**4. Tại sao chỉ copy lab.provider.jar vào thư mục plugins chưa đủ?**  
Chưa có module được resolved hoặc layer/loader được define; host phải dùng ModuleFinder/Configuration/ModuleLayer và khám phá qua ServiceLoader được gắn với layer thích hợp.

**5. resolve có tự gọi constructor provider không?**  
Không. resolve xây module configuration; việc định nghĩa class/lấy provider và thực thi constructor là giai đoạn khác, thường lazy theo ServiceLoader.

**6. Có thể dùng reload() để đổi lab.provider.jar bản v1 thành v2 không?**  
Không. reload() xóa cache ServiceLoader, không thay module/class definition trong layer cũ. Host cần workflow phiên bản, layer/loader mới và cutover.

**7. Khi ServiceLoader.load(childLayer, ...) trả nhiều providers, có phải tất cả đều thuộc child không?**  
Không nhất thiết; theo API nó có thể khám phá providers trong cả ancestors. Host phải áp dụng policy chọn provider, xác minh module/layer nếu cần.

## 19. Checklist dùng trong dự án thật

- [ ] Đã xác định SPI nằm ở module API chung, versioned, export package cần thiết.
- [ ] Host là named module và khai báo **requires + uses** chính xác.
- [ ] Provider là **explicit named module**, có **requires + provides**, không export package implementation nếu không cần.
- [ ] Host không requires/import implementation module.
- [ ] Provider artifact có module-info.class và được kiểm tra descriptor sau packaging.
- [ ] Plugin JAR nằm ngoài boot module path nếu mục tiêu là nạp vào child layer.
- [ ] Host xác minh nguồn artifact/version/hash trước khi đưa JAR vào module finder.
- [ ] ModuleFinder, resolution roots và module dependencies được quản lý minh bạch.
- [ ] Parent API được dùng chung để tránh nhân đôi Class identity của SPI.
- [ ] Host dùng **ServiceLoader.load(layer, SPI.class)** để khám phá đúng phạm vi.
- [ ] Host xử lý **không có provider**, lỗi cấu hình và lỗi khởi tạo theo policy.
- [ ] Host chọn provider theo ID/capability/version, không coi thứ tự duyệt là ranking nghiệp vụ.
- [ ] Có kiểm thử trên module path thật và cả Windows/Linux nếu công bố hỗ trợ.
- [ ] Có kế hoạch nhiều modules, xung đột dependency, class loader/layer và service visibility.
- [ ] Có lifecycle start/health/stop/rollback, quản lý TCCL và reference để tránh leaks.
- [ ] Không coi ModuleLayer, ServiceLoader hay Java module encapsulation là security sandbox.

**Kết luận:** Chuyển sang explicit named modules không chỉ là thêm **module-info.java**. Muốn khám phá plugin trong ModuleLayer con, host phải **tách SPI chung ở parent**, **đăng ký uses/provides đúng nơi**, **tìm và resolve plugin module**, **định nghĩa child layer bằng chiến lược loader phù hợp** và **gọi ServiceLoader theo layer mới**. Bài thực hành cho thấy boot layer vẫn chỉ chứa API/host, implementation plugin được nạp riêng mà không cần export package nội bộ.

## Tài liệu Java 17 tham khảo

- ModuleLayer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- ModuleFinder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Configuration: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- ServiceLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java module declarations: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
- JDK javac: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- JDK jar: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
