# defineModulesWithOneLoader và defineModulesWithManyLoaders

## 1. Mục tiêu: chọn chiến lược ClassLoader cho một ModuleLayer

Từ Java 9, Java Platform Module System (JPMS) cho phép một ứng dụng tạo **ModuleLayer** mới ở runtime. Đây là tình huống thường gặp ở plugin runtime, công cụ IDE, container hoặc ứng dụng muốn nạp một tập **named modules** độc lập với lớp module được khởi tạo lúc JVM bắt đầu.

Hai API tiện ích trên **java.lang.ModuleLayer** là:

- **defineModulesWithOneLoader**: tạo **một ClassLoader mới** và gán **toàn bộ modules của configuration** vào loader đó.
- **defineModulesWithManyLoaders**: tạo **một ClassLoader mới cho mỗi module** trong configuration.

Điểm khác biệt cốt lõi là **mapping từ module tới defining loader**. Cả hai đều tạo layer mới, tạo runtime Module objects và thiết lập module graph tương ứng. Chúng không chỉ tạo một lớp wrapper quanh những Class objects sẵn có.

### Bạn sẽ học được gì?

Sau bài này, bạn có thể:

1. Giải thích **ModuleFinder → Configuration → ModuleLayer** theo đúng thứ tự.
2. Phân biệt **parent layer** với **parent ClassLoader**.
3. Biết khi nào chọn one-loader, khi nào chọn many-loaders.
4. Dùng **findLoader**, **findModule**, **Class.getModule** và **Class.getClassLoader** để kiểm tra runtime.
5. Tạo hai named modules Java 17+ và load chúng bằng cả hai chiến lược.
6. Hiểu **direct delegation**, package overlap, split delegation, readability và class identity.
7. Biết điểm khác nhau giữa **instance overload** và **static overload trả Controller**.
8. Chẩn đoán lỗi resolve/define/load và thiết kế vòng đời module layer cho plugin.

## 2. Ba đối tượng không thể đánh đồng

### 2.1 ModuleFinder: tìm các module artifacts

**java.lang.module.ModuleFinder** giúp tìm module definitions từ các nguồn như exploded module directories hoặc modular JARs.

~~~java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
~~~

Đây là snippet đặt trong method có import phù hợp. **Path.of("mods")** trỏ tới thư mục chứa các modules đã biên dịch. Một ModuleFinder cung cấp thông tin để resolution lựa chọn modules; nó **không tự tạo ModuleLayer** và không phải một ClassLoader.

### 2.2 Configuration: đồ thị module đã resolve

**java.lang.module.Configuration** chứa các resolved modules và quan hệ requires/readability ở mức configuration.

~~~java
ModuleLayer parent = ModuleLayer.boot();
Configuration cf = parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("demo.beta"));
~~~

Snippet trên giả sử đã khai báo finder, có import và tồn tại module demo.beta trong finder. **resolve** lấy boot-layer configuration làm parent, dùng finder để tìm module demo.beta và các dependencies phù hợp.

**Configuration chưa đồng nghĩa các classes đã được nạp vào JVM.** Nó là mô tả graph đã resolve; muốn định nghĩa các named modules ở runtime còn cần bước tạo layer.

### 2.3 ModuleLayer: module graph được định nghĩa ở JVM runtime

Layer chứa những **java.lang.Module** objects thực tế được JVM nhận biết, đi kèm ánh xạ module → ClassLoader.

~~~java
ModuleLayer layer =
        parent.defineModulesWithOneLoader(
                cf, ClassLoader.getSystemClassLoader());
~~~

Sau đó:

~~~java
ClassLoader loader = layer.findLoader("demo.beta");
Module module = layer.findModule("demo.beta").orElseThrow();
~~~

**findLoader** cho biết loader tương ứng với module; **findModule** trả Optional Module theo tên. Các method này không tự chạy main hoặc constructor của module.

### Tóm tắt ba bước

~~~text
Modular JARs / exploded modules
               |
               v
       ModuleFinder.of(...)
               |
               v
Configuration.resolve(... roots ...)
               |
               v
       Configuration cf
               |
               v
ModuleLayer.defineModulesWithOneLoader(...)
hoặc defineModulesWithManyLoaders(...)
               |
               v
        ModuleLayer runtime
           /         \
       Module       ClassLoader mapping
~~~

## 3. API chính xác: instance và static overloads

Cùng tên method nhưng API có **hai nhóm overload khác nhau**.

### 3.1 Instance overload: một parent layer

~~~java
ModuleLayer defineModulesWithOneLoader(
        Configuration cf, ClassLoader parentLoader);

ModuleLayer defineModulesWithManyLoaders(
        Configuration cf, ClassLoader parentLoader);
~~~

Đây là API declarations, không phải class Java độc lập. Khi gọi như sau:

~~~java
ModuleLayer parent = ModuleLayer.boot();
ModuleLayer child =
        parent.defineModulesWithManyLoaders(cf, parentLoader);
~~~

**parent** sẽ là parent layer của **child**. Configuration phải có đúng **một parent configuration tương ứng với parent.configuration()**; nếu không, lời gọi có thể ném IllegalArgumentException.

### 3.2 Static overload: một hoặc nhiều parent layers và Controller

~~~java
static ModuleLayer.Controller defineModulesWithOneLoader(
        Configuration cf,
        List<ModuleLayer> parentLayers,
        ClassLoader parentLoader);

static ModuleLayer.Controller defineModulesWithManyLoaders(
        Configuration cf,
        List<ModuleLayer> parentLayers,
        ClassLoader parentLoader);
~~~

Chúng trả **ModuleLayer.Controller**, không trực tiếp trả ModuleLayer. Lấy layer bằng:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                cf, List.of(parent), parentLoader);

ModuleLayer child = controller.layer();
~~~

Với một parent, kết quả layer về mặt tạo module tương ứng instance overload:

~~~java
parent.defineModulesWithOneLoader(cf, parentLoader);
~~~

Các static overload phù hợp khi cần **nhiều parent layers** hoặc quyền điều chỉnh module edges bằng **Controller.addReads/addExports/addOpens** sau khi tạo layer.

**Quan trọng:** danh sách parentLayers phải trùng **số lượng, thứ tự và configuration parents** của cf theo hợp đồng API. Không tùy ý đưa layer khác vào chỉ vì có tên module giống nhau.

### 3.3 Bảng so sánh

| Thuộc tính | OneLoader | ManyLoaders |
| --- | --- | --- |
| Số loader được tạo | **1 loader mới** cho toàn bộ modules trong cf | **1 loader mới/module** trong cf |
| Mapping module → loader | Nhiều module chung một loader | Mỗi module một loader riêng |
| findLoader của hai modules khác nhau | **Cùng object ClassLoader** | **Hai object ClassLoader khác nhau** |
| Loader cha | Tham số parentLoader | Cùng tham số parentLoader cho từng loader mới |
| Delegation giữa modules | Module-aware direct delegation, kể cả tới parent layers | Module-aware direct delegation giữa loader của các modules |
| Resource lookup | Tìm resources từ các modules của layer do loader ấy quản lý trước parent | Tìm resources thuộc module loader ấy quản lý trước parent |
| Package overlap trong cf | **Không hợp lệ** nếu nhiều modules có cùng package | Có thể có về mapping loader, nhưng resolution/readability còn ràng buộc |
| Split delegation | Có thể làm layer không tạo được | Phân phối module ra nhiều loaders có thể tránh ràng buộc one-loader cụ thể |
| API phiên bản instance | Trả ModuleLayer | Trả ModuleLayer |
| API phiên bản static | Trả Controller | Trả Controller |

**Một loader không đồng nghĩa một module.** Một ClassLoader do OneLoader tạo có thể define classes từ nhiều named modules riêng biệt. Ngược lại ManyLoaders có nhiều loaders nhưng vẫn nằm trong **một ModuleLayer** và cùng configuration graph.

## 4. Parent layer khác parent ClassLoader

Hai tham số có chữ parent nhưng **không cùng tác dụng**:

- **Parent layer** quyết định **module graph ancestry**: module nào ở parent layers, những Module objects nào có thể được đọc hoặc tìm theo ancestry.
- **parentLoader** là **ClassLoader cha của loader hoặc các loaders mới**, được dùng khi class/resource name không map vào các modules có đường direct delegation thích hợp.

Ví dụ:

~~~java
ModuleLayer boot = ModuleLayer.boot();

ModuleLayer child =
        boot.defineModulesWithManyLoaders(
                cf,
                ClassLoader.getSystemClassLoader());
~~~

Ở đây:

- Parent **layer** của child là **boot**.
- Parent **loader** của mỗi loader mới là **system/application ClassLoader**.
- Một loader mới trong child có thể **direct delegate** sang loader của module khác theo module graph, không chỉ hỏi parentLoader theo parent-first thông thường.

### 4.1 parentLoader có thể là null

Javadoc cho phép **parentLoader = null**, tương ứng bootstrap loader. Điều này không có nghĩa newly created loader = null; chính API vẫn **tạo ClassLoader mới**, chỉ có parent loader là bootstrap.

~~~java
ModuleLayer child =
        boot.defineModulesWithOneLoader(cf, null);
~~~

Đây là snippet có sẵn cf và boot. **child.findLoader("demo.beta")** vẫn trả một loader mới cho module đó, không trả null chỉ vì parentLoader truyền null.

### 4.2 parentLoader không phải loader dùng để định nghĩa các module mới

Một hiểu lầm rất phổ biến:

~~~java
ModuleLayer child =
        boot.defineModulesWithOneLoader(
                cf,
                ClassLoader.getSystemClassLoader());
~~~

Từ đó kết luận: “Các module mới được system loader định nghĩa.” **Sai.** Method tạo **một loader mới có parent là system loader**. Kiểm tra:

~~~java
ClassLoader created = child.findLoader("demo.beta");
boolean same = created == ClassLoader.getSystemClassLoader();
// same là false với modules được định nghĩa trong child layer
~~~

Khi muốn dùng những loader do chính mình tạo và cung cấp mapping module → loader, đó là bài toán của **ModuleLayer.defineModules** với function mapping, không phải hai phương thức tiện ích đang học.

## 5. Chúng xử lý delegation như thế nào?

### 5.1 Direct delegation dựa trên module và package

Các loaders do hai convenience APIs tạo **không chỉ dựa trên chuỗi parent-first truyền thống**.

Khi loadClass nhận tên một class, loader xem **tên package** để tìm module sở hữu package trong module graph mà nó biết. Nếu class map tới một module khác trong cùng layer hoặc module ở parent layer được export phù hợp theo graph, nó có thể **direct delegate tới ClassLoader của module đó**.

Nếu tên class **không map được tới module nào**, loader dùng parentLoader.

~~~text
Module loader muốn load "alpha.api.Greeter"
            |
            v
Package "alpha.api" map tới demo.alpha?
            |
            +-- Có: tìm loader của demo.alpha
            |          |
            |          v
            |      direct delegation
            |
            +-- Không: fallback parent ClassLoader
~~~

Cơ chế này giúp các modules trong layer đọc classes từ module khác phù hợp với **requires/readability và exports** mà không buộc loader tree phản ánh y hệt module graph.

### 5.2 OneLoader vẫn có nhiều Module objects

Với OneLoader, các classes từ demo.alpha và demo.beta đều có cùng defining loader, nhưng:

~~~text
Class alpha.api.Greeter
  -> getModule().getName() = demo.alpha

Class beta.api.Consumer
  -> getModule().getName() = demo.beta

Hai Class objects có cùng defining loader,
nhưng thuộc hai runtime named modules khác nhau.
~~~

**Cùng loader không xóa module boundary.** Readability, exports, opens và quyền truy cập theo JPMS vẫn được kiểm soát.

### 5.3 ManyLoaders: module A gọi code của module B

Khi demo.beta có:

~~~java
requires demo.alpha;
~~~

và demo.alpha export package chứa Greeter, loader của demo.beta biết cách delegate tới loader của demo.alpha. Không cần tự override loadClass để thực hiện module-aware delegation trong trường hợp tiêu chuẩn.

**Đừng suy luận rằng getParent() của loader demo.beta chính là loader demo.alpha.** Hai loader mới có thể có cùng parentLoader, còn việc đọc class giữa modules dùng direct delegation dựa trên module mapping.

## 6. Ví dụ Java 17+ số 1: biên dịch hai named modules

Tạo cấu trúc thư mục:

~~~text
project/
├── src/
│   ├── demo.alpha/
│   │   ├── module-info.java
│   │   └── alpha/api/Greeter.java
│   └── demo.beta/
│       ├── module-info.java
│       └── beta/api/Consumer.java
└── LayerCompareDemo.java
~~~

**src/demo.alpha/module-info.java**:

~~~java
module demo.alpha {
    exports alpha.api;
}
~~~

**src/demo.alpha/alpha/api/Greeter.java**:

~~~java
package alpha.api;

public final class Greeter {
    public String hello() {
        return "hello";
    }
}
~~~

**src/demo.beta/module-info.java**:

~~~java
module demo.beta {
    requires demo.alpha;
    exports beta.api;
}
~~~

**src/demo.beta/beta/api/Consumer.java**:

~~~java
package beta.api;

import alpha.api.Greeter;

public final class Consumer {
    public String call() {
        return new Greeter().hello();
    }
}
~~~

Tại thư mục project, dùng JDK 17+:

~~~bash
javac --module-source-path src -d mods -m demo.alpha,demo.beta
~~~

Sau lệnh này, thư mục output **mods** có hai exploded named modules:

~~~text
mods/
├── demo.alpha/
│   ├── module-info.class
│   └── alpha/api/Greeter.class
└── demo.beta/
    ├── module-info.class
    └── beta/api/Consumer.class
~~~

**Không** thêm mods vào classpath theo kiểu **-cp mods** rồi kỳ vọng JVM coi mỗi directory con là named module. Ví dụ sẽ dùng **ModuleFinder.of(Path.of("mods"))** để resolve các module ở bước runtime.

### 6.1 Tại sao phải có module-info.java?

Module demo.beta khai báo **requires demo.alpha**, nên Configuration sẽ resolve cả hai modules khi root là demo.beta. Module demo.alpha **exports alpha.api**, cho phép Consumer sử dụng Greeter. Trong code Consumer, câu lệnh **new Greeter().hello()** là tương tác Java bình thường, nhưng JVM cần loader mapping và module graph hợp lệ để nạp Greeter từ module alpha.

Không phải cứ đặt các class trong hai thư mục là tạo được module dependency; module descriptor và configuration resolution mới là phần quyết định.

## 7. Ví dụ Java 17+ số 2: cùng một graph, hai chính sách loader

Tạo file **LayerCompareDemo.java** ngay thư mục project:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerCompareDemo {
    static String runConsumer(ModuleLayer layer) throws Exception {
        ClassLoader loader = layer.findLoader("demo.beta");

        Class<?> type = loader.loadClass("beta.api.Consumer");
        Object instance = type.getConstructor().newInstance();

        return (String) type.getMethod("call").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        ModuleLayer parent = ModuleLayer.boot();

        Configuration cf = parent.configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("demo.beta"));

        ModuleLayer one = parent.defineModulesWithOneLoader(
                cf, ClassLoader.getSystemClassLoader());

        ModuleLayer many = parent.defineModulesWithManyLoaders(
                cf, ClassLoader.getSystemClassLoader());

        ClassLoader oneAlpha = one.findLoader("demo.alpha");
        ClassLoader oneBeta = one.findLoader("demo.beta");
        ClassLoader manyAlpha = many.findLoader("demo.alpha");
        ClassLoader manyBeta = many.findLoader("demo.beta");

        System.out.println("one same loader = "
                + (oneAlpha == oneBeta));
        System.out.println("many same loader = "
                + (manyAlpha == manyBeta));

        Class<?> alphaOne = oneAlpha.loadClass("alpha.api.Greeter");
        Class<?> alphaMany = manyAlpha.loadClass("alpha.api.Greeter");

        System.out.println("one alpha module = "
                + alphaOne.getModule().getName());
        System.out.println("many alpha module = "
                + alphaMany.getModule().getName());

        System.out.println("one consumer = " + runConsumer(one));
        System.out.println("many consumer = " + runConsumer(many));

        System.out.println("alpha Class equal across layers = "
                + (alphaOne == alphaMany));

        System.out.println("one loader is new = "
                + (oneAlpha != ClassLoader.getSystemClassLoader()));
    }
}
~~~

Biên dịch và chạy **host launcher** trong unnamed module:

~~~bash
javac -d host-out LayerCompareDemo.java
java -cp host-out LayerCompareDemo
~~~

Stdout kỳ vọng khi có đúng hai module artifacts ở mods và không có bản cạnh tranh của các lớp trên classpath:

~~~text
one same loader = true
many same loader = false
one alpha module = demo.alpha
many alpha module = demo.alpha
one consumer = hello
many consumer = hello
alpha Class equal across layers = false
one loader is new = true
~~~

### 7.1 Giải thích từng kết quả

**one same loader = true:** cả demo.alpha và demo.beta trong layer **one** được định nghĩa tới cùng một ClassLoader mới.

**many same loader = false:** trong layer **many**, mỗi named module có một ClassLoader riêng. Hai module là hai phần tử của cùng Configuration nhưng được mapping sang hai loaders khác nhau.

**one/many alpha module = demo.alpha:** dù chính sách loader khác, class Greeter vẫn thuộc named module demo.alpha. Mapping module → loader không xóa Module identity.

**one/many consumer = hello:** Consumer của demo.beta gọi Greeter của demo.alpha thành công. Module graph **requires + exports** hợp lệ. Với ManyLoaders, module-aware direct delegation giúp loader beta lấy Greeter từ loader alpha.

**alpha Class equal across layers = false:** bạn đã tạo **hai layer mới riêng biệt**, mỗi layer có loader riêng cho demo.alpha. Dù tên và bytes Greeter giống nhau, defining loader khác nhau nên đó là hai runtime Class khác nhau.

**one loader is new = true:** tham số system loader là **parent** của newly created loader. Chính layer tạo một loader mới để define modules của nó.

### 7.2 Tại sao code dùng reflection?

LayerCompareDemo được chạy trong **unnamed module** trên host classpath và không biên dịch với requires demo.beta. Dùng ClassLoader + reflection giúp launcher tìm và gọi Consumer sau khi tạo layer ở runtime.

**Điều kiện để reflection gọi được:** package beta.api được module demo.beta **exports không điều kiện**; Consumer, constructor và method call là public. Nếu package không export hoặc method không accessible, reflection từ unnamed module có thể ném IllegalAccessException hoặc InaccessibleObjectException tùy thao tác. Đây là quy tắc module access, không phải lỗi do OneLoader/ManyLoaders.

### 7.3 Giới hạn của stdout

Kết quả trên áp dụng cho file và lệnh biên dịch/chạy nêu rõ. Nếu bạn:

- Đổi tên package/class hoặc module.
- Đưa bản demo.alpha/demo.beta khác lên module path khi JVM launch.
- Thêm split packages hoặc dependency mới không resolve được.
- Sửa module-info exports/requires.

thì kết quả hoặc exception có thể khác. Không coi ví dụ như lời hứa rằng mọi module graph đều tạo được bằng cả hai chiến lược.

## 8. Đặt two layers cạnh nhau không làm Class tương thích tự động

Một ClassLoader được tạo cho layer one và một ClassLoader khác được tạo cho layer many. Cặp:

~~~text
("alpha.api.Greeter", oneLoader)
            !=
("alpha.api.Greeter", manyAlphaLoader)
~~~

là hai class identities.

Hệ quả:

- Một instance Greeter thuộc layer one không tự cast được sang Greeter do layer many define.
- Một type của host và một type cùng binary name do module trong layer define không tự tương thích.
- Reflection, ServiceLoader và API có thể cần class identity chung tại boundary.
- Dùng **Interface/DTO chung** từ parent/shared loader có thể giúp host và plugin giao tiếp an toàn, nếu module graph/readability/exports cho phép.

**Không nhầm hai câu hỏi:**

1. Trong **cùng một layer**, hai modules có **cùng defining loader** không?
2. Giữa **hai layers độc lập**, Class objects có bằng nhau không?

OneLoader trả true cho câu (1) trong layer one, nhưng không làm kết quả câu (2) thành true.

## 9. Lựa chọn OneLoader: lợi ích và giới hạn

### 9.1 Khi nào phù hợp?

**defineModulesWithOneLoader** có thể hợp lý nếu:

- Một tập modules trong layer được deploy/đóng vòng đời như **một nhóm thống nhất**.
- Không có overlapping packages giữa các modules trong configuration.
- Module graph không tạo tình huống split delegation bị cấm.
- Bạn muốn số ClassLoader ít hơn và không cần loader isolation giữa các modules của nhóm.
- Classes trong cùng nhóm vẫn phải giữ module access boundaries qua JPMS.

**Một loader vẫn có thể định nghĩa nhiều modules, và mỗi class vẫn có Class.getModule riêng.** Vì thế không phải cứ OneLoader là mất tên module hoặc mất exports/opens.

### 9.2 Overlapping packages là blocker cụ thể của OneLoader

Javadoc mô tả OneLoader **không tạo được layer** nếu **hai hay nhiều modules trong configuration chứa cùng tên package**. Lý do cơ bản: một loader không thể có một package name ánh xạ mơ hồ vào hai modules trong chính layer đó.

Ví dụ khái niệm:

~~~text
module plugin.a
  contains package plugin.shared

module plugin.b
  contains package plugin.shared

OneLoader cho cả hai:
  package plugin.shared -> module nào?
  => LayerInstantiationException theo quy tắc OneLoader
~~~

**Không kết luận rằng ManyLoaders luôn giải quyết được mọi split package.** Resolver có thể từ chối cấu hình nếu readability dẫn tới xung đột package, và module graph/security còn những giới hạn khác. Việc ánh xạ mỗi module vào loader riêng chỉ giải quyết một phần xung đột ở cấp loader.

### 9.3 Split delegation là blocker khác của OneLoader

Javadoc nêu OneLoader cũng có thể thất bại khi loader kết quả sẽ phải **delegate tới nhiều loader khác nhau cho cùng một package** ở parent layers.

~~~text
New layer, ONE loader
       |
       +-- cần package p từ parentLoader X
       |
       +-- đồng thời cần package p từ parentLoader Y

Không thể nhất quán ánh xạ một package p
với hai đích delegation trong loader đó
=> trường hợp split delegation, layer không tạo được
~~~

Đây là điều kiện riêng khác với **overlapping packages** trong chính configuration mới. Khi thiết kế layer, cần xem cả graph parent layers, packages được export và loader mapping của các modules mà graph sẽ đọc.

### 9.4 Không đánh đồng ít ClassLoader với tiết kiệm bộ nhớ được bảo đảm

OneLoader tạo ít loader objects hơn. Tuy vậy, tổng bộ nhớ của ứng dụng còn phụ thuộc số classes, metadata, code, objects, caches và GC. Không suy ra rằng OneLoader chắc chắn có throughput/latency/memory tốt hơn trong mọi workload mà không đo thực tế.

## 10. Lựa chọn ManyLoaders: lợi ích và giới hạn

### 10.1 Khi nào phù hợp?

**defineModulesWithManyLoaders** hữu ích khi:

- Muốn mỗi named module có **defining loader riêng**.
- Cần phân biệt ownership của các classes theo module.
- Muốn dùng nhiều loaders mà vẫn dựa vào module-aware delegation chính thức của JDK.
- Muốn tránh việc một loader duy nhất phải ánh xạ nhiều packages/modules bất tương thích.
- Muốn thiết kế những ranh giới unloading/retention có chủ đích, nhưng vẫn cần kiểm soát module layer và object references.

**Đừng diễn giải “mỗi module có loader riêng” là mọi class ở layer đều hoàn toàn cô lập khỏi nhau.** Các module vẫn đọc lẫn nhau khi graph requires/exports cho phép, và loaders direct delegate theo package mapping.

### 10.2 Parent loader vẫn được chia sẻ

ManyLoaders tạo một loader/module và **parent của mỗi loader mới đều là parentLoader được truyền vào**.

~~~text
parentLoader (ví dụ AppLoader)
     ^
     | parent        ^ parent
     |               |
Loader demo.alpha  Loader demo.beta
     |               |
  Greeter            Consumer
       <--- module-aware delegation khi cần --->
~~~

Trong một số trường hợp loadClass có thể direct delegate sang loader của module khác trong layer; đó không phải quan hệ parent-child giữa hai loader mới.

### 10.3 Khi nào ManyLoaders không phù hợp?

Nếu bạn muốn toàn bộ group modules dùng **chính cùng một loader** vì kiến trúc hoặc muốn một group là một loader scope thống nhất, ManyLoaders không đáp ứng.

Nếu nhu cầu chỉ là sử dụng **custom ClassLoader do bạn tự quản lý**, cả hai convenience APIs cũng không phải API trực tiếp nhận ClassLoader đó làm defining loader. Khi ấy cần xem **ModuleLayer.defineModules** với hàm mapping module name → ClassLoader và tự quản lý delegation đúng module readability.

## 11. Instance overload và Controller trong dự án thực

ModuleLayer có cả overload tiện dụng và static overload nâng cao.

### 11.1 Chỉ cần layer: instance overload

~~~java
ModuleLayer child =
        ModuleLayer.boot().defineModulesWithOneLoader(
                cf, ClassLoader.getSystemClassLoader());
~~~

Đúng khi bạn có một parent layer phù hợp và không cần cầm Controller.

### 11.2 Cần điều chỉnh cạnh module: static overload

Tạo file **LayerControllerDemo.java**, dùng lại hai modules trong thư mục mods đã biên dịch ở phần 6:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class LayerControllerDemo {
    public static void main(String[] args) {
        ModuleLayer parent = ModuleLayer.boot();

        Configuration cf = parent.configuration().resolve(
                ModuleFinder.of(Path.of("mods")),
                ModuleFinder.of(),
                Set.of("demo.beta"));

        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithManyLoaders(
                        cf,
                        List.of(parent),
                        ClassLoader.getSystemClassLoader());

        ModuleLayer layer = controller.layer();

        Module alpha = layer.findModule("demo.alpha").orElseThrow();
        Module beta = layer.findModule("demo.beta").orElseThrow();
        Module host = LayerControllerDemo.class.getModule();

        System.out.println("layer has 2 modules = "
                + (layer.modules().size() == 2));
        System.out.println("beta reads alpha = "
                + beta.canRead(alpha));

        controller.addReads(beta, host);
        System.out.println("beta reads host after addReads = "
                + beta.canRead(host));

        System.out.println("two different loaders = "
                + (layer.findLoader("demo.alpha")
                        != layer.findLoader("demo.beta")));
    }
}
~~~

Chạy:

~~~bash
javac -d host-out LayerControllerDemo.java
java -cp host-out LayerControllerDemo
~~~

Stdout kỳ vọng:

~~~text
layer has 2 modules = true
beta reads alpha = true
beta reads host after addReads = true
two different loaders = true
~~~

**Giải thích:** demo.beta cần demo.alpha theo requires, nên beta.canRead(alpha) true. **controller.addReads(beta, host)** tạo thêm read edge tới unnamed module của launcher, sau đó beta.canRead(host) true. Đây là thao tác **tăng runtime readability** của module trong layer, không định nghĩa lại class hoặc đổi loader mapping.

**Lưu ý giới hạn:** chỉ gọi Controller methods với những modules/conditions được API cho phép. Việc bổ sung đọc/exports/opens có ảnh hưởng tới module encapsulation; không mở package hoặc read edge tùy tiện như một cách “sửa lỗi reflection” nếu không có chủ đích thiết kế.

### 11.3 Controller.addExports và addOpens khác addReads

- **addReads(source, target)**: source module được phép đọc target.
- **addExports(source, packageName, target)**: export package của source cho target ở runtime để truy cập public types theo quy tắc.
- **addOpens(source, packageName, target)**: mở package cho target để phục vụ deep reflection theo quy tắc module.
- **Không phương thức nào** biến một Class đã có thành Class do loader khác định nghĩa.
- Một edge bổ sung không đồng nghĩa tất cả reflective access tự hợp lệ; vẫn cần xét quyền của member, readability/exports/opens và code đang gọi.

Những method này nằm trên **Controller** của layer được định nghĩa bằng static overload. Instance overload không trả Controller nên không thể dùng controller của chính lời gọi đó.

## 12. Kết hợp ModuleFinder, Configuration và ModuleLayer đúng cách

Một quy trình chuẩn trong plugin manager:

~~~text
[1] Chọn nguồn module artifacts
        |
        v
[2] ModuleFinder.of(pluginDirs...)
        |
        v
[3] Chọn parent layers và Configuration parents
        |
        v
[4] resolve roots + transitive dependencies
        |
        v
[5] Kiểm tra module names, packages, graph constraints
        |
        v
[6] Chọn OneLoader / ManyLoaders / custom mapping
        |
        v
[7] Định nghĩa ModuleLayer mới
        |
        v
[8] layer.findLoader(moduleName) + loadClass(...)
        |
        v
[9] Bắt đầu plugin theo API/lifecycle riêng
        |
        v
[10] Quản lý unload/redeployment và references
~~~

**Bước resolve trước bước define** là quan trọng: lỗi thiếu dependency, duplicate module names hoặc package conflict ở graph thường xuất hiện sớm trong module resolution. Lỗi loader mapping như overlapping packages của OneLoader hoặc split delegation có thể xuất hiện ở bước define layer.

**Không gọi defineModulesWithManyLoaders rồi suy ra nó tự download module dependencies**. API dùng Configuration đã resolve và finder của cấu hình tương ứng; module artifacts phải tồn tại và hợp lệ.

## 13. Layer isolation và class identity

Các method này thường được dùng để tạo plugin versions khác nhau:

~~~text
Host / boot layer
       |
       +-- PluginLayer V1
       |      +-- ClassLoader V1 hoặc loader/module V1
       |
       +-- PluginLayer V2
              +-- ClassLoader V2 hoặc loader/module V2
~~~

Class có cùng tên ở hai layers nhưng do hai defining loaders khác nhau **không phải cùng runtime type**.

Điều này ảnh hưởng:

- **cast/instanceof** giữa host và plugin object.
- Reflection khi so sánh Class objects.
- Method signatures và loader constraints.
- ServiceLoader providers nếu service type không chia sẻ đúng loader.
- Serialization và caches chứa đối tượng của version cũ.

**Đừng dùng layer làm sandbox bảo mật hoàn chỉnh.** Module layer và class-loader boundary mang lại tổ chức namespace, readability, exports và loader isolation; chúng không tự bảo đảm code không tin cậy được cách ly khỏi toàn bộ API nguy hiểm.

### 13.1 Shared API boundary

Một plugin runtime thường để API giao tiếp chung ở parent/shared module, rồi plugin implementations ở child layers:

~~~text
Shared parent module:
    plugin.api (interface Plugin)

Plugin layer:
    plugin.impl.one -> requires plugin.api
    plugin.impl.two -> requires plugin.api
~~~

Mục tiêu là host và plugin nhìn thấy **cùng Class plugin.api.Plugin** nếu cần cast object plugin thành interface host. Không đưa bản duplicate của interface API vào plugin module/layer rồi mong JVM coi chúng là một Class chỉ vì binary name giống nhau.

## 14. Resource lookup và ModuleLayer

Cả hai loại convenience loaders hỗ trợ resource lookup theo cơ chế có nêu trong Javadoc:

- **OneLoader:** loader mới tìm resources trong **các modules của layer** mà nó define trước khi tìm ở parentLoader.
- **ManyLoaders:** mỗi loader tìm resources trong **module riêng** mà nó define trước khi tìm ở parentLoader.

**Không đồng nhất class delegation và resource search.** Module encapsulation vẫn có thể giới hạn non-class resources trong named modules. Một resource tồn tại trong modular JAR chưa chắc ClassLoader.getResource có thể trả URL nếu package của resource không đáp ứng openness thích hợp.

Với code gắn trực tiếp một named module, **Module.getResourceAsStream** hoặc **Class.getResourceAsStream** có các quy tắc module-aware riêng và có thể phù hợp hơn so với tra resource tùy ý từ loader.

Nếu two modules chứa resource cùng tên, OneLoader tìm trên nhiều modules mà nó define; thứ tự trả về có thể không phù hợp để làm policy cấu hình. Cần tránh tên trùng hoặc dùng API xác định module sở hữu resource để tăng tính quyết định.

## 15. Các lỗi thường gặp và nguyên nhân

### 15.1 ResolutionException khi Configuration không hợp lệ

**Nguồn:** bước parent.configuration().resolve(...), chưa phải bước tạo loader.

Có thể do module cần thiết không tìm thấy, dependency requirements không thể thỏa, package conflicts trong graph hoặc module artifacts không hợp lệ.

**Cách kiểm tra:** tên root module có đúng không, ModuleFinder.of trỏ tới exploded modules/JAR chính xác chưa, module-info.requires/export có phù hợp không.

### 15.2 IllegalArgumentException do Configuration parent không khớp

Instance overload đòi cf có đúng một parent configuration là configuration của **layer receiver**. Static overload đòi parentLayers khớp parents của cf cả về **thứ tự**.

Đây không phải lỗi nạp class từ file, mà là lỗi **khớp giữa graph mô tả và graph runtime**.

### 15.3 LayerInstantiationException vì overlapping packages

Nếu hai modules trong cf cùng chứa package p và chọn OneLoader, một loader không thể ánh xạ package ấy vào hai modules cùng layer. Hãy sửa module packaging/graph hoặc cân nhắc ManyLoaders nếu các ràng buộc readability khác cho phép.

### 15.4 LayerInstantiationException do split delegation

Khi một loader OneLoader mới phải delegate cùng package tới nhiều loaders khác nhau trong parent layers, API có thể từ chối tạo layer. Cần kiểm tra phân bố packages và các module exports/reads ở parent graph; không chỉ xem tên modules trong layer mới.

### 15.5 ClassNotFoundException sau khi tạo layer

- Bạn dùng **layer.findLoader sai module name**?
- Binary class name thiếu package hoặc dùng dấu slash?
- Class thực sự nằm trong module đã resolve đó không?
- Code nạp class không exported/readable ở đường delegation phù hợp?
- Bạn đang hỏi system loader thay vì loader mới mà findLoader trả về?

Dùng **Class.getClassLoader**, **Class.getModule** khi đã load được một Class để kiểm tra owner.

### 15.6 IllegalAccessException / InaccessibleObjectException

Các method vẫn tôn trọng JPMS access. Nếu package không exports public types tới caller hoặc không opens cho reflection, code có thể load Class nhưng không thể gọi constructor/method qua reflection như mong muốn. Điều chỉnh **module-info** hoặc edges Controller theo hợp đồng; không coi đây là bằng chứng cần đổi OneLoader sang ManyLoaders.

### 15.7 LinkageError, loader constraints và ClassCastException

Nếu host và plugin không chia sẻ API Class đúng cách, tên giống nhau vẫn có thể dẫn tới hai runtime types khác. Xem defining loaders và module graph. Khi JVM cần thống nhất type trong chữ ký, lỗi liên kết có thể lộ ra.

### 15.8 Module name trong configuration đã có ở parent?

ModuleLayer.findModule tìm trong layer và parent layers, nhưng việc resolution còn có chính sách riêng đối với module names. Không nên giả định muốn lấy một version module mới thì chỉ cần đặt lại tên module đã có trên parent graph bất kể constraints. Xác định rõ parent configurations, artifact versions và dự định layering; tránh xung đột tại graph resolution.

### 15.9 Không unload class dù đã bỏ reference tới layer

Creating ModuleLayer có thể tạo loader objects giữ nhiều definitions. **Class unloading phụ thuộc reachability của defining loaders**; chỉ xóa biến local layer không tự đảm bảo GC/unloading. Nếu Thread context loader, plugin instances, service providers, callbacks hoặc caches vẫn giữ loaders/modules, các versions cũ có thể còn sống.

## 16. Khi nào chọn OneLoader, khi nào ManyLoaders?

| Câu hỏi thiết kế | Ưu tiên xem xét |
| --- | --- |
| Có nhiều modules nhưng muốn chúng dùng chung một loader? | **OneLoader** |
| Muốn rõ ownership theo module, một loader/module? | **ManyLoaders** |
| Nhiều modules có cùng package trong configuration? | **OneLoader không hợp lệ**; ManyLoaders còn tùy graph/readability |
| Có rủi ro split delegation ở một loader duy nhất? | Xem **ManyLoaders** hoặc thiết kế lại graph |
| Muốn dùng chính custom ClassLoaders có sẵn? | **defineModules** với mapping function, không phải hai convenience APIs |
| Cần chỉnh reads/exports/opens sau khi tạo layer? | Dùng **static overload trả Controller** |
| Muốn parent layer boot nhưng parent loader là application loader? | Cả hai method đều hỗ trợ |
| Chỉ muốn nạp một modular JAR đơn giản tại startup? | Cân nhắc **--module-path** và launcher JPMS trước khi tự tạo layer |
| Muốn quản lý plugin versions/redeploy? | Layer mới, loader identity, API boundary và lifecycle rõ ràng |
| Muốn giảm memory chắc chắn? | Đo thực tế; ít loaders không tự đảm bảo hiệu năng tốt hơn |

**Quy tắc:** chọn theo **module-to-loader mapping thực sự mong muốn**, không theo số modules hoặc cảm giác “many có vẻ tốt hơn”.

## 17. Tự kiểm tra kiến thức

**Câu 1.** defineModulesWithOneLoader tạo loader nào?

**Trả lời:** Tạo một **ClassLoader mới** cho tất cả modules trong Configuration, có parent là parentLoader được truyền.

**Câu 2.** defineModulesWithManyLoaders có làm demo.beta phải dùng loader demo.alpha làm parent không?

**Trả lời:** Không. Mỗi loader mới có parentLoader được truyền; giao tiếp cross-module dùng direct delegation theo package/module graph.

**Câu 3.** Vì sao one.findLoader("demo.alpha") == one.findLoader("demo.beta") là true?

**Trả lời:** Cả hai modules được define vào cùng loader mới trong layer one.

**Câu 4.** Nếu same loader, hai modules còn độc lập về JPMS exports/reads không?

**Trả lời:** Có. Module objects và graph riêng vẫn được JVM áp dụng.

**Câu 5.** Tại sao alphaOneClass == alphaManyClass là false?

**Trả lời:** Hai layers khác nhau có defining loaders khác nhau dù binary name/bytes giống nhau.

**Câu 6.** Instance overload và static overload trả gì?

**Trả lời:** Instance trả ModuleLayer; static trả ModuleLayer.Controller, lấy layer bằng controller.layer().

**Câu 7.** parentLoader có phải loader định nghĩa classes trong layer mới không?

**Trả lời:** Không. Method tạo loader mới có parent là parentLoader.

**Câu 8.** Vì sao OneLoader có thể thất bại khi hai modules dùng cùng package p?

**Trả lời:** Một loader không thể ánh xạ cùng package vào hai modules của cùng layer; Javadoc quy định overlapping packages gây LayerInstantiationException.

**Câu 9.** ManyLoaders có bảo đảm mọi split package đều hợp lệ không?

**Trả lời:** Không. Configuration resolution/readability còn có thể từ chối xung đột; mỗi module/loader riêng chỉ thay một phần điều kiện.

**Câu 10.** Loader từ ManyLoaders tìm class trong module khác bằng cách nào?

**Trả lời:** Direct delegation dựa vào package-to-module mapping và graph exports/reads, không nhất thiết qua getParent().

**Câu 11.** Muốn thay đổi thêm một read edge ở runtime, dùng gì?

**Trả lời:** Static overload nhận parentLayers và trả Controller, sau đó controller.addReads theo hợp đồng.

**Câu 12.** Vì sao không thể xem ModuleFinder.of(...) là kết quả đã load class?

**Trả lời:** ModuleFinder chỉ tìm module definitions, Configuration resolve graph, ModuleLayer define runtime modules, còn class loading xảy ra khi class được yêu cầu.

## 18. Ghi nhớ

~~~text
MODULE ARTIFACTS
       |
       v
ModuleFinder.of(...)
       |
       v
Configuration.resolve(... roots ...)
       |
       v
ModuleLayer.boot()
       |
       +-- defineModulesWithOneLoader
       |      -> 1 ClassLoader mới cho N modules
       |
       +-- defineModulesWithManyLoaders
              -> N ClassLoader mới cho N modules
                   |
                   +-- direct delegation giữa modules
                       theo graph khi cần
~~~

- **ModuleLayer** là một runtime graph của named modules và module-to-loader mapping.
- **OneLoader**: nhiều modules dùng chung loader, nhưng vẫn có modules riêng và JPMS access rules.
- **ManyLoaders**: mỗi module có loader riêng, vẫn có thể delegate trực tiếp theo module graph.
- **parentLayer** xác định ancestry của modules, còn **parentLoader** là parent của loaders mới.
- **Instance API trả ModuleLayer; static API trả Controller.**
- Một loader chứa nhiều modules phải tránh **overlapping packages** và **split delegation** bị cấm.
- Dùng **findLoader** và **Class.getModule/getClassLoader** để kiểm tra runtime, thay vì đoán theo đường dẫn file/JAR.
- Layer mới không tự bảo đảm unload layer cũ; cần quản lý strong references, threads và plugin lifecycle.

### Nguồn chính thức

- Java SE 21 **ModuleLayer API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 21 **ModuleLayer.Controller API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.Controller.html
- Java SE 21 **Configuration API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- Java SE 21 **ModuleFinder API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java SE 21 **Module API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 **JPMS specification (JLS §7)**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
