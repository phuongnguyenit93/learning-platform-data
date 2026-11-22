# Giới hạn phương thức provider đối với module tự động và classpath

## 1. Vấn đề cần phân biệt

Trong Java Platform Module System (JPMS), ServiceLoader có thể tìm dịch vụ (service) và tạo các đối tượng cung cấp dịch vụ (service providers) từ nhiều cách đóng gói khác nhau. Một điểm dễ nhầm là **public static provider()**: phương thức này có thể được ServiceLoader gọi để tạo service trong **explicit named module**, nhưng **không được ServiceLoader hỗ trợ như cơ chế provider factory cho automatic module hoặc provider trên classpath**.

Xem hai kiểu provider:

~~~java
// Mảnh minh họa: Greeter là interface service.
public final class DirectGreeter implements Greeter {
    public DirectGreeter() { }
    @Override public String greet() { return "direct"; }
}
~~~

~~~java
// Mảnh minh họa: FactoryGreeter không implements Greeter.
public final class FactoryGreeter {
    private FactoryGreeter() { }
    public static Greeter provider() {
        return () -> "factory";
    }
}
~~~

Class thứ nhất được tạo bằng **public constructor không tham số**. Class thứ hai có **public static provider()** không tham số trả về Greeter, nên có thể được liệt kê trong **provides ... with ...** của một explicit named module dù bản thân FactoryGreeter không implements Greeter. Nếu chỉ ghi FactoryGreeter vào tệp **META-INF/services** trên classpath hoặc đặt JAR legacy chứa đăng ký ấy vào module path dưới dạng automatic module, ServiceLoader **không chuyển sang gọi provider()**; nó yêu cầu provider class tương thích trực tiếp với service và có provider constructor.

Đây là quy tắc về **cơ chế triển khai provider**, khác với việc một ứng dụng có thể tự gọi bất kỳ static factory method nào qua Java code thông thường. Sự tồn tại của phương thức tên provider() không tự làm ServiceLoader công nhận nó ở mọi chế độ.

Bài học giải thích ba môi trường triển khai, đường đăng ký provider, hành vi thực tế của ServiceLoader, ví dụ Java 17 chạy được và cách thiết kế SPI tương thích khi chuyển từ classpath sang JPMS.

## 2. Ba môi trường triển khai không giống nhau

| Môi trường | JAR/module được nhận diện thế nào? | Khai báo provider cho ServiceLoader | Cơ chế lấy instance được hỗ trợ |
|---|---|---|---|
| **Classpath / unnamed module** | Class nằm trên classpath, thuộc unnamed module của class loader | Tệp **META-INF/services/<tên.binary.của.Service>** | Provider class phải gán được cho service và có **public no-arg constructor** |
| **Automatic module** | JAR **không có module-info.class**, được đặt trên **module path** và được resolve thành named module tự động | Các tệp **META-INF/services** có thể được ánh xạ thành thông tin provides trong module descriptor suy ra | Cũng phải có **provider constructor**; **không hỗ trợ provider method** |
| **Explicit named module** | Module có **module-info.class** với module descriptor tường minh | Chỉ thị **provides Service with ProviderClass** trong **module-info.java** | **Public static provider()** không tham số trả kiểu service hợp lệ, **hoặc** nếu không có provider method thì dùng public no-arg constructor |

**Nhớ hai trục độc lập:**

1. **Đặt JAR ở đâu?** Classpath đưa class vào unnamed module; module path có thể đưa JAR legacy thành automatic module nếu được resolve; một modular JAR có module-info.class là explicit named module.
2. **ServiceLoader tạo instance bằng gì?** Classpath và automatic module dùng **constructor route**; explicit named module có thể dùng **provider-method route**.

Automatic module là **named module**, nhưng không phải **explicit named module**. Nó được tạo để hỗ trợ dịch chuyển thư viện legacy lên module path. Tính chất named module, tên module được suy ra hoặc gán qua manifest **Automatic-Module-Name**, và việc ServiceLoader đọc service metadata không làm automatic module có quyền sử dụng provider factory method.

Ví dụ file **greeter-plugin.jar** không có module-info.class:

~~~text
java -cp greeter-plugin.jar ...
    -> classpath / unnamed module

java --module-path greeter-plugin.jar --add-modules greeter.plugin ...
    -> automatic module tên greeter.plugin

# Khi đóng gói module-info.class chứa provides:
java --module-path mods --add-modules greeter.plugin ...
    -> explicit named module
~~~

Các dòng trên chỉ minh họa các chế độ; chương trình chạy đầy đủ nằm ở phần 6.

## 3. Quy tắc ServiceLoader đối với explicit named module

Một module khai báo:

~~~java
// module-info.java: mảnh minh họa
module greeting.plugin {
    requires greeting.spi;
    provides greeting.spi.Greeter
        with greeting.impl.FactoryGreeter;
}
~~~

Khi tìm provider, ServiceLoader biết module đã khai báo FactoryGreeter là provider cho Greeter. Class provider trong module có thể cung cấp **phương thức provider**:

~~~java
// Mảnh minh họa: lớp thuộc module greeting.plugin.
package greeting.impl;

import greeting.spi.Greeter;

public final class FactoryGreeter {
    private FactoryGreeter() { }

    public static Greeter provider() {
        return () -> "Xin chào từ factory";
    }
}
~~~

Điều kiện cần nhớ của **provider method**:

- Tên phương thức chính xác là **provider**.
- Phương thức **public static**, **không nhận tham số**.
- Kiểu trả về được khai báo phải gán được cho **kiểu service**; chẳng hạn Greeter hoặc một subtype của Greeter.
- Lớp được liệt kê sau **with** là provider class thuộc chính module khai báo. Lớp đó **không bắt buộc implements Greeter**, vì kết quả từ provider() mới là instance của service.
- Nếu provider class có provider method hợp lệ, ServiceLoader sẽ **gọi provider method** để lấy instance; constructor của provider class không phải con đường tạo service trong trường hợp này.
- Nếu provider class không có provider method, nó phải là subtype của service và có **public no-arg constructor** để ServiceLoader khởi tạo trực tiếp.
- Phương thức provider() có thể trả **null** hoặc ném lỗi tại runtime; đây là lỗi cấu hình/tạo service, thường được ServiceLoader báo qua **ServiceConfigurationError**.

Có thể biểu diễn hai nhánh:

~~~text
Explicit named module:
  module-info: provides Greeter with ProviderClass
                         |
                         v
             ProviderClass có
             public static provider()?
                  /           \
                Có            Không
                |               |
      Gọi provider()      Kiểm tra subtype
      lấy Greeter          và public no-arg ctor
                |               |
             Greeter        new ProviderClass()
~~~

**Lưu ý:** Đây là sơ đồ logic của quy tắc; ServiceLoader còn thực hiện các bước khám phá, nạp, kiểm tra module/class và báo lỗi khi cấu hình không hợp lệ.

Một static method tên provider() không có nghĩa là toàn bộ static factory pattern bị giới hạn. Ứng dụng vẫn có thể viết **Factory.create(...)** và gọi trực tiếp trong mọi môi trường. Quy tắc chỉ nói về **entry point mà java.util.ServiceLoader tự động sử dụng**.

## 4. Tại sao automatic module không dùng provider()?

Automatic module được suy ra từ một JAR legacy trên module path, **không có module-info.class tường minh**. Nó có thể chứa:

~~~text
legacy-greeter.jar
├── example/impl/LegacyGreeter.class
└── META-INF/services/example.spi.Greeter
~~~

Trong đó tệp **META-INF/services/example.spi.Greeter** liệt kê:

~~~text
example.impl.LegacyGreeter
~~~

Khi công cụ module path suy ra descriptor cho automatic module, thông tin trong các tệp services có thể được chuyển thành các **provides** trong descriptor tự động. Tuy nhiên ServiceLoader quy định **automatic-module provider phải có provider constructor**, tức **public constructor không tham số**. Không có nhánh gọi static provider() cho cách triển khai này.

Vì vậy:

- Automatic module vẫn được ServiceLoader tìm thông qua thông tin service đã suy ra.
- Provider class phải **implements/extends service** và phải có **public no-arg constructor**.
- Nếu provider class chỉ có static provider() mà không implements service hoặc không có constructor hợp lệ, đó không phải provider thích hợp cho automatic module.
- Đưa JAR legacy lên module path và đặt **Automatic-Module-Name** trong manifest chỉ tạo tên module ổn định hơn, **không biến nó thành explicit named module**, cũng không bật hỗ trợ factory method.
- Muốn dùng nhánh factory của ServiceLoader, cần cung cấp module descriptor tường minh phù hợp và khai báo **provides ... with ...** cho provider.

**Chú ý khác biệt cấu hình:** Với classpath, một service file có thể liệt kê provider nằm ở một JAR khác nếu class loader tìm thấy class. Khi suy ra automatic module, khai báo service trong JAR phải hợp lệ với module được tạo, trong đó provider được liệt kê phải thuộc module tương ứng; dữ liệu service file bị sao chép sai sau khi shading/relocation có thể khiến quá trình suy ra module descriptor thất bại sớm. Kiểm tra nội dung JAR và dùng **jar --describe-module** trước khi dựa vào automatic module.

## 5. Tại sao provider trên classpath không dùng provider()?

Khi provider nằm trên classpath, ServiceLoader đọc resource theo quy ước:

~~~text
META-INF/services/example.spi.Greeter
~~~

Nội dung là các **tên binary class provider** theo từng dòng, ví dụ:

~~~text
example.impl.DirectGreeter
example.impl.AnotherGreeter
~~~

Tệp phải được lưu dưới mã hóa **UTF-8**. ServiceLoader nạp class theo tên, kiểm tra class có assignable tới kiểu service và có **public no-arg constructor**, rồi tạo instance khi cần. Nó không đối xử tên trong service file như một class factory có static provider().

Một class vừa implements Greeter, vừa có public no-arg constructor, vừa tình cờ có public static provider() vẫn có thể là classpath provider hợp lệ; nhưng ServiceLoader **gọi constructor**, không tự chọn method.

Đối chiếu:

~~~java
// Mảnh minh họa: cả hai phương thức đều tồn tại.
public final class DualGreeter implements Greeter {
    public DualGreeter() {
        System.out.println("CONSTRUCTOR");
    }

    @Override
    public String greet() {
        return "direct";
    }

    public static Greeter provider() {
        System.out.println("PROVIDER_METHOD");
        return () -> "factory";
    }
}
~~~

Trong **classpath/automatic module**, nếu class này đăng ký hợp lệ, ServiceLoader tạo bằng **DualGreeter()**; trong **explicit named module có provides ... with DualGreeter**, ServiceLoader có thể dùng **provider()**. Ví dụ chạy độc lập ở phần 6 kiểm chứng chính sự khác biệt này.

**Không nhầm:** Tệp **META-INF/services** là metadata chỉ ra *lớp provider*. Nó không có cú pháp để chỉ một phương thức hoặc chuyển tham số đến provider(). Đặt tên class bằng hậu tố **#provider** hay viết chuỗi dạng **Class::provider** trong service file không biến nó thành method reference hợp lệ.

## 6. Ví dụ Java 17 chạy được: cùng một provider, ba cách triển khai

Ví dụ dùng **cùng một interface Greeter**, **cùng class DualGreeter** và **cùng host App** để so sánh:

1. JAR trên **classpath** → constructor.
2. JAR legacy trên **module path** thành **automatic module** → constructor.
3. Provider được biên dịch thành **explicit named module** có **provides ... with ...** → static provider().

Tất cả output dùng ASCII để kết quả không phụ thuộc encoding của console.

### 6.1. Cây nguồn

Tạo cấu trúc:

~~~text
service-modes/
├── spi/
│   └── src/demo/spi/Greeter.java
├── plugin/
│   ├── src/demo/impl/DualGreeter.java
│   └── resources/META-INF/services/demo.spi.Greeter
├── host/
│   └── src/demo/host/App.java
└── modules/
    ├── demo.spi/module-info.java
    ├── demo.plugin/module-info.java
    └── demo.host/module-info.java
~~~

Cả ba chế độ dùng lại ba tệp Java thông thường. Chỉ **cách đóng gói và module descriptors** thay đổi.

### 6.2. Service contract

**spi/src/demo/spi/Greeter.java**

~~~java
package demo.spi;

public interface Greeter {
    String message();
}
~~~

Interface thuộc nhóm API chung, được host và plugin biên dịch cùng một phiên bản tương thích. Trong ví dụ classpath, nó có trên classpath; trong ví dụ named modules, nó thuộc **demo.spi** và được export.

### 6.3. Provider có cả constructor và static provider()

**plugin/src/demo/impl/DualGreeter.java**

~~~java
package demo.impl;

import demo.spi.Greeter;

public final class DualGreeter implements Greeter {
    public DualGreeter() {
        System.out.println("CONSTRUCTOR");
    }

    @Override
    public String message() {
        return "direct";
    }

    public static Greeter provider() {
        System.out.println("PROVIDER_METHOD");
        return () -> "factory";
    }
}
~~~

Provider được cố ý thiết kế hợp lệ cho **constructor route** và cho **provider-method route**. Constructor in **CONSTRUCTOR**; method in **PROVIDER_METHOD**. Giá trị message cũng khác nhau để chứng minh instance nhận được đến từ nhánh nào.

Chú ý return type của phương thức provider() là **Greeter**. Trong explicit named module, **Provider.type()** sẽ trả về kiểu khai báo ấy, không nhất thiết trả về **DualGreeter.class**.

### 6.4. Host dùng ServiceLoader và in kiểu provider

**host/src/demo/host/App.java**

~~~java
package demo.host;

import demo.spi.Greeter;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) {
        ServiceLoader<Greeter> loader =
                ServiceLoader.load(Greeter.class);

        ServiceLoader.Provider<Greeter> descriptor = loader.stream()
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No Greeter provider"));

        System.out.println("type=" + descriptor.type().getSimpleName());

        Greeter greeter = descriptor.get();
        System.out.println("value=" + greeter.message());
    }
}
~~~

Lệnh **descriptor.type()** chỉ xem kiểu mà ServiceLoader quảng bá, không khởi tạo service instance. **descriptor.get()** mới kích hoạt nhánh khởi tạo.

Ví dụ giả định môi trường chỉ có đúng một provider Greeter do project này công bố; khi nhiều provider khả kiến, không nên dùng **findFirst()** làm chính sách chọn provider quan trọng mà thiếu tiêu chí tường minh.

### 6.5. Service file cho classpath và automatic module

**plugin/resources/META-INF/services/demo.spi.Greeter**

~~~text
demo.impl.DualGreeter
~~~

Tên file là **demo.spi.Greeter**, chính xác theo fully qualified binary name của service. Nội dung là tên implementation class. Bản JAR legacy tạo ở bước kế tiếp **không có module-info.class**.

### 6.6. Compile JAR legacy và host

Chạy các lệnh dưới đây từ thư mục **service-modes**, trên JDK 17 trở lên.

Linux/macOS (bash):

~~~bash
mkdir -p build/api build/plugin build/host

javac --release 17 -encoding UTF-8 -d build/api \
  spi/src/demo/spi/Greeter.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/plugin \
  plugin/src/demo/impl/DualGreeter.java

cp -R plugin/resources/META-INF build/plugin/

jar --create --file build/demo-plugin.jar -C build/plugin .

javac --release 17 -encoding UTF-8 -cp build/api -d build/host \
  host/src/demo/host/App.java
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/api, build/plugin, build/host | Out-Null

javac --release 17 -encoding UTF-8 -d build/api spi/src/demo/spi/Greeter.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/plugin plugin/src/demo/impl/DualGreeter.java

Copy-Item -Recurse -Force plugin/resources/META-INF build/plugin/

jar --create --file build/demo-plugin.jar -C build/plugin .

javac --release 17 -encoding UTF-8 -cp build/api -d build/host host/src/demo/host/App.java
~~~

Lệnh jar tạo **build/demo-plugin.jar** chứa **demo/impl/DualGreeter.class** và service file **META-INF/services/demo.spi.Greeter**. Nó không chứa **module-info.class**, và không cần đóng gói bản thứ hai của Greeter.class.

Kiểm tra nội dung:

~~~bash
jar --list --file build/demo-plugin.jar
~~~

Kết quả có thể còn META-INF/MANIFEST.MF, nhưng cần xuất hiện hai entry quan trọng vừa nêu. Không thay service file bằng tên **demo.impl.DualGreeter.provider** vì ServiceLoader mong đợi tên class.

### 6.7. Chạy trên classpath

Linux/macOS:

~~~bash
java -cp build/api:build/host:build/demo-plugin.jar demo.host.App
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/host;build/demo-plugin.jar" demo.host.App
~~~

**Stdout:**

~~~text
type=DualGreeter
CONSTRUCTOR
value=direct
~~~

Giải thích: các class ở classpath thuộc unnamed module; ServiceLoader tìm class theo META-INF/services, đọc kiểu class DualGreeter và gọi **public DualGreeter()**. Nó **không gọi** public static provider(), nên không có dòng PROVIDER_METHOD.

### 6.8. Chạy chính JAR đó như automatic module

Vì **build/demo-plugin.jar** không chứa module-info.class, đặt nó trên module path sẽ cho module tự động. Với tên file **demo-plugin.jar**, tên module suy ra là **demo.plugin**.

Linux/macOS:

~~~bash
java --module-path build/demo-plugin.jar \
  --add-modules demo.plugin \
  -cp build/api:build/host \
  demo.host.App
~~~

Windows PowerShell:

~~~powershell
java --module-path build/demo-plugin.jar --add-modules demo.plugin -cp "build/api;build/host" demo.host.App
~~~

**Stdout:**

~~~text
type=DualGreeter
CONSTRUCTOR
value=direct
~~~

Đây là điểm cần quan sát: **module đã là named module**, nhưng **ServiceLoader vẫn dùng constructor**, vì automatic module không hỗ trợ provider factory method. Service file của JAR giúp mô tả dịch vụ trong automatic module. Host và SPI vẫn đang ở unnamed module trên classpath; automatic module có thể đọc các kiểu cần thiết theo cơ chế của automatic modules.

Cờ **--add-modules demo.plugin** yêu cầu resolve automatic module vào module graph. Chỉ đặt file ở module path mà không cho module được resolve có thể khiến ServiceLoader không thấy provider như bạn kỳ vọng. Dùng **jar --describe-module --file build/demo-plugin.jar** để kiểm tra tên và descriptor suy ra.

### 6.9. Tạo explicit named modules

Giữ nguyên interface, provider và host, thêm ba module descriptor sau.

**modules/demo.spi/module-info.java**

~~~java
module demo.spi {
    exports demo.spi;
}
~~~

**modules/demo.plugin/module-info.java**

~~~java
module demo.plugin {
    requires demo.spi;
    provides demo.spi.Greeter with demo.impl.DualGreeter;
}
~~~

**modules/demo.host/module-info.java**

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.Greeter;
}
~~~

Tại đây, module provider khai báo **provides ... with ...**. Module host khai báo **uses**. Host không khai báo requires demo.plugin vì phần lõi chỉ biết hợp đồng, không cần phụ thuộc trực tiếp vào module triển khai. Module plugin phải được resolve khi chạy; lệnh dưới dùng **--add-modules** để đảm bảo.

Biên dịch lại thành ba **exploded named modules**. Linux/macOS (bash):

~~~bash
mkdir -p build/mods/demo.spi build/mods/demo.plugin build/mods/demo.host

javac --release 17 -encoding UTF-8 \
  -d build/mods/demo.spi \
  modules/demo.spi/module-info.java \
  spi/src/demo/spi/Greeter.java

javac --release 17 -encoding UTF-8 \
  --module-path build/mods \
  -d build/mods/demo.plugin \
  modules/demo.plugin/module-info.java \
  plugin/src/demo/impl/DualGreeter.java

javac --release 17 -encoding UTF-8 \
  --module-path build/mods \
  -d build/mods/demo.host \
  modules/demo.host/module-info.java \
  host/src/demo/host/App.java

java --module-path build/mods \
  --add-modules demo.plugin \
  --module demo.host/demo.host.App
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/mods/demo.spi, build/mods/demo.plugin, build/mods/demo.host | Out-Null

javac --release 17 -encoding UTF-8 -d build/mods/demo.spi modules/demo.spi/module-info.java spi/src/demo/spi/Greeter.java

javac --release 17 -encoding UTF-8 --module-path build/mods -d build/mods/demo.plugin modules/demo.plugin/module-info.java plugin/src/demo/impl/DualGreeter.java

javac --release 17 -encoding UTF-8 --module-path build/mods -d build/mods/demo.host modules/demo.host/module-info.java host/src/demo/host/App.java

java --module-path build/mods --add-modules demo.plugin --module demo.host/demo.host.App
~~~

**Stdout của explicit named modules:**

~~~text
type=Greeter
PROVIDER_METHOD
value=factory
~~~

Giải thích:

1. Khác với JAR legacy, **demo.plugin** nay có **module-info.class** và **provides demo.spi.Greeter with demo.impl.DualGreeter**.
2. ServiceLoader thấy trong provider class có **public static Greeter provider()** hợp lệ, nên sử dụng provider method. Constructor **DualGreeter()** không được gọi ở nhánh này.
3. **Provider.type()** trả về **Greeter** vì đó là **declared return type của provider()**; nó không nhất thiết trả về DualGreeter, cũng không nhất thiết trả về runtime class của lambda.
4. Khi **descriptor.get()** được gọi, phương thức provider() in **PROVIDER_METHOD** và trả về một instance thực hiện Greeter.
5. Instance do lambda thực hiện message() trả **factory**.

Đây là phép so sánh trên **cùng source Java**: khác biệt đến từ **cách triển khai provider và module metadata**, không phải tên method hay cách gọi của host.

### 6.10. Bảng đối chiếu kết quả

| Chế độ | Đường đăng ký | Provider.type().getSimpleName() | Cách ServiceLoader lấy instance | message() |
|---|---|---|---|---|
| Classpath | META-INF/services | DualGreeter | public no-arg constructor | direct |
| Automatic module | Service metadata suy ra từ META-INF/services | DualGreeter | public no-arg constructor | direct |
| Explicit named module | provides ... with ... | Greeter | public static provider() | factory |

Nếu môi trường có thêm provider Greeter từ JAR/module khác, **findFirst()** có thể chọn provider khác. Giữ ví dụ trong môi trường sạch, hoặc thêm tiêu chí chọn provider cụ thể để kiểm tra độc lập.

## 7. Trường hợp class chỉ có provider() và không implements service

Giả sử class sau được dùng làm provider:

~~~java
package demo.impl;

import demo.spi.Greeter;

public final class FactoryOnly {
    private FactoryOnly() { }

    public static Greeter provider() {
        return () -> "from-factory";
    }
}
~~~

Trong **explicit named module**, đổi khai báo:

~~~java
module demo.plugin {
    requires demo.spi;
    provides demo.spi.Greeter with demo.impl.FactoryOnly;
}
~~~

Cách này hợp lệ vì FactoryOnly có provider method đúng chữ ký, và giá trị nó trả về có kiểu Greeter.

Trên **classpath**, nếu tệp **META-INF/services/demo.spi.Greeter** ghi **demo.impl.FactoryOnly**, ServiceLoader sẽ không gọi provider(). FactoryOnly không implements Greeter và không có public constructor phù hợp, nên đó là cấu hình provider không hợp lệ: quá trình duyệt/nạp có thể ném **ServiceConfigurationError**.

Với **automatic module** tạo từ JAR chứa service file tương ứng, trường hợp này cũng **không được hỗ trợ**. Đừng tưởng vì automatic module được suy ra thành named module nên ServiceLoader sẽ tự áp dụng quy tắc của explicit module.

**Chú ý:** Tại compile-time, một explicit module có thể kiểm tra provider method qua **javac** khi đọc module-info.java. Classpath/automatic không có module-info.java tường minh để biểu diễn factory-only provider, nên cần một provider class trực tiếp hoặc chuyển sang explicit module.

## 8. Giải pháp khi muốn dùng factory nhưng phải hỗ trợ classpath/automatic

Một SPI dễ phân phối cho cả ba môi trường thường không bắt ServiceLoader tự gọi static provider(). Thay vào đó, **service do ServiceLoader tạo chính là factory có constructor hợp lệ**, còn factory đó có phương thức instance để tạo đối tượng nghiệp vụ.

Ví dụ:

~~~java
package demo.spi;

// Mảnh minh họa service factory contract.
public interface GreeterFactory {
    String id();
    Greeter create(String prefix);
}
~~~

~~~java
package demo.impl;

import demo.spi.Greeter;
import demo.spi.GreeterFactory;

// Mảnh minh họa provider áp dụng được cho classpath/automatic.
public final class DefaultGreeterFactory implements GreeterFactory {
    public DefaultGreeterFactory() { }

    @Override
    public String id() {
        return "default";
    }

    @Override
    public Greeter create(String prefix) {
        return () -> prefix + " Java";
    }
}
~~~

Host sẽ:

~~~java
// Mảnh minh họa, không phải chương trình Java độc lập.
GreeterFactory factory = ServiceLoader.load(GreeterFactory.class)
        .findFirst()
        .orElseThrow();

Greeter greeter = factory.create("Hello");
System.out.println(greeter.message());
~~~

**Stdout của mảnh trên**, nếu interface Greeter có method message() như ví dụ chính và DefaultGreeterFactory là provider duy nhất:

~~~text
Hello Java
~~~

Cơ chế:

- **Classpath:** ServiceLoader gọi **DefaultGreeterFactory()** qua service file META-INF/services/demo.spi.GreeterFactory.
- **Automatic module:** cũng gọi **public constructor không tham số**, với service metadata trong JAR.
- **Explicit named module:** có thể khai báo **provides demo.spi.GreeterFactory with demo.impl.DefaultGreeterFactory**, vẫn sử dụng constructor nếu không có static provider() hợp lệ trong class.
- **Phần tạo đối tượng có tham số** thuộc method instance **create(prefix)** của factory service, sau khi host đã nhận factory.

Factory service có thể quản lý cấu hình, cache, dependencies và vòng đời theo hợp đồng riêng; việc tạo đối tượng nghiệp vụ không còn bị giới hạn bởi chữ ký **public static provider() không tham số** của ServiceLoader.

**Đừng nhầm hai chữ “factory”:** **provider method** là giao thức khởi tạo đặc biệt của ServiceLoader cho explicit named modules; **factory service** là mô hình thiết kế do ứng dụng định nghĩa, hoạt động độc lập với chế độ module.

## 9. Những lỗi và ngộ nhận phổ biến

### 9.1. “Automatic module là named module nên provider() phải hoạt động”

Sai. Automatic module có tên và được resolve trong module graph, nhưng ServiceLoader **quy định riêng** rằng automatic-module provider phải có **provider constructor**. Nếu cần static provider() làm entry point cho ServiceLoader, hãy biên dịch một **explicit named module** có chỉ thị provides tương ứng.

### 9.2. “Chỉ cần thêm Automatic-Module-Name trong manifest”

Sai. Manifest **Automatic-Module-Name** đặt tên module ổn định hơn cho JAR không có module-info.class. Nó **không sinh ra module descriptor tường minh** có đầy đủ uses/provides do tác giả viết, và không mở khóa cơ chế provider method.

### 9.3. “Chuyển JAR sang module path nhưng giữ nguyên services file là đủ để gọi factory”

Sai. Service file có thể được dùng để xác định provider cho automatic module, nhưng bản thân service file chỉ ghi **tên class**, không ghi provider method. Để dùng provider() theo JPMS, cần explicit named module và **provides ... with ...**; class provider trong module phải khai báo phương thức hợp lệ.

### 9.4. “Class được liệt kê trong service file chỉ cần có static provider()”

Sai ở classpath và automatic module. Provider class phải **gán được cho service** và có **public constructor không tham số**. Factory-only class thiếu các đặc điểm này sẽ khiến ServiceLoader không lấy được service và có thể ném **ServiceConfigurationError**.

### 9.5. “ServiceLoader.Provider.type() luôn là class ghi sau with”

Không đúng với provider method. Nếu explicit named module dùng **public static Greeter provider()**, **Provider.type()** trả **Greeter.class** theo chữ ký return type, không phải factory class. Nếu host muốn chọn provider theo annotation ở factory class, bộ lọc dựa trên type() có thể sai; nên công bố metadata phù hợp hoặc dùng factory service/registry.

### 9.6. “Dùng static provider(String config) cho ServiceLoader truyền cấu hình”

Không được hỗ trợ: **provider method của ServiceLoader không nhận tham số**. Những method tên provider nhưng có tham số không phải provider entry point được định nghĩa. Khi cần cấu hình động, dùng **service factory có method create(config)**, DI container hoặc một giao thức khởi tạo rõ khác.

### 9.7. “Đã có module-info.java thì không cần khai báo uses”

Một **consumer explicit module** dùng ServiceLoader cần khai báo **uses** cho service trong module-info.java theo hợp đồng API. Module provider khai báo provides; ứng dụng không nên phụ thuộc cứng vào module implementation bằng requires trừ khi có lý do riêng. Nếu provider module không được resolve, ServiceLoader vẫn có thể tìm không thấy provider dù module JAR nằm trên module path.

### 9.8. “Không tìm thấy provider nên chắc chắn code provider() bị sai”

Không đủ bằng chứng. Hãy kiểm tra đúng tầng: môi trường classpath/module path, module descriptor, service file, tên module, module đã được resolve chưa, visibility của provider class, type assignability, constructor/method access, class loader và lỗi gốc. **Không tìm thấy provider** và **provider bị cấu hình sai** là hai tình huống khác nhau.

## 10. Checklist khi chuyển SPI từ classpath sang JPMS

1. **Xác định artifact:** JAR không có module-info.class trên module path là automatic module; manifest Automatic-Module-Name chỉ cung cấp tên module.
2. **Kiểm tra service file:** tên **META-INF/services/<service binary name>** và nội dung class provider hợp lệ, UTF-8, provider thuộc JAR/module dự định.
3. **Chọn đường khởi tạo:** muốn chạy được trên classpath/automatic thì provider implements service và có public no-arg constructor; muốn ServiceLoader tự gọi provider() thì cung cấp explicit named module.
4. **Viết module descriptor:** explicit provider module khai báo **provides Service with ProviderClass**; explicit consumer module khai báo **uses Service** và requires module API nếu cần.
5. **Đảm bảo provider method đúng:** public, static, tên provider, không tham số, return type gán được cho service; không giả định ServiceLoader gọi method trong automatic/classpath.
6. **Giữ API dùng chung:** cùng danh tính service interface/runtime Class, version API tương thích và module resolution/class loader phù hợp.
7. **Không dùng thứ tự provider ngẫu nhiên:** lựa chọn dựa trên metadata/ID hoặc chính sách đã định nghĩa; kiểm tra hành vi của **Provider.type()** khi factory method trả kiểu chung.
8. **Kiểm thử tối thiểu ba chế độ:** legacy classpath, automatic module, explicit named module; quan sát constructor hay provider() được gọi, test lỗi thiếu provider, sai constructor/method, và kiểm tra module graph.
9. **Dự trù đường tương thích:** nếu phải hỗ trợ cả ba chế độ và cần cấu hình khởi tạo, ưu tiên **factory-as-service** có public no-arg constructor hơn việc phụ thuộc vào static provider().

## 11. Câu hỏi tự kiểm tra

**Câu 1.** JAR có file META-INF/services và class chứa public static provider(), nhưng không implements service. Khi đặt JAR lên module path thành automatic module, ServiceLoader có gọi provider() không?

**Đáp án:** Không. Automatic-module providers yêu cầu provider constructor và subtype phù hợp của service. Cách khai báo factory-only này không hợp lệ cho automatic module; cần chuyển thành explicit named module hoặc sửa service thành lớp factory triển khai trực tiếp contract.

**Câu 2.** Một class vừa implements service vừa có public no-arg constructor và public static provider() hợp lệ. Điều gì khác khi chuyển từ classpath sang explicit named module?

**Đáp án:** Trên classpath ServiceLoader gọi constructor. Trong explicit named module với provides ... with ... và method hợp lệ, ServiceLoader gọi provider(). Điều này có thể đổi instance được trả về và làm **Provider.type()** trả declared return type của method.

**Câu 3.** Automatic-Module-Name đặt trong MANIFEST.MF có khiến ServiceLoader dùng provider() không?

**Đáp án:** Không. Thuộc tính đó chỉ giúp ổn định tên của automatic module. Để dùng provider method theo ServiceLoader phải có explicit module descriptor thích hợp.

**Câu 4.** Tại sao không nên dùng tên class của provider trong file META-INF/services để biểu diễn cú pháp gọi method?

**Đáp án:** Service configuration file chỉ liệt kê tên binary của **provider class**. ServiceLoader không có cú pháp gọi method trong tệp này; method route được quyết định từ cấu hình explicit named module và chữ ký provider().

**Câu 5.** Cần truyền prefix và dependency để tạo Greeter, nhưng plugin vẫn phải chạy trên classpath. Nên thiết kế thế nào?

**Đáp án:** ServiceLoader tạo một **GreeterFactory** đơn giản có public no-arg constructor, rồi host gọi **factory.create(prefix, dependencies)** theo hợp đồng tự định nghĩa. Đó là factory service chứ không phải ServiceLoader provider method.

## 12. Tài liệu chuẩn và điểm cần ghi nhớ

- Oracle Java SE 17 API, **ServiceLoader** — mục Developing service providers, Deploying service providers as modules, Deploying service providers on the class path và Errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java SE 17 API, **ServiceLoader.Provider** — ý nghĩa type() khi module dùng provider factory method: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java SE 17 **ModuleFinder**, quy tắc suy ra module descriptor từ JAR/metadata service: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java Language Specification 17, **§7.7.4 Service Provision**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4
- Dev.java, **Incremental Modularization with Automatic Modules**: https://dev.java/learn/organizing/modules/automatic-module/

**Ghi nhớ:** Provider method của ServiceLoader (**public static provider() không tham số**) thuộc cơ chế khai báo provider của **explicit named module**. Provider trong **automatic module hoặc trên classpath** được ServiceLoader tạo qua **public no-arg constructor** của class triển khai service. Khi cần hỗ trợ đa môi trường mà vẫn muốn cấu hình tạo đối tượng, hãy thiết kế **factory là service** thay vì dựa vào provider() ở những môi trường không hỗ trợ.
