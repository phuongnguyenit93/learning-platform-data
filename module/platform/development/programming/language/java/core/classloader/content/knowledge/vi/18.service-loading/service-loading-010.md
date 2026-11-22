# Provider constructor, provider method và khác biệt theo cách triển khai

## 1. Vì sao cùng là service provider nhưng có hai cách tạo?

Trong Java, **ServiceLoader<S>** là cơ chế phát hiện implementation của một **service type** — thường là interface hoặc abstract class — mà application không cần biết tên cụ thể của từng implementation lúc biên dịch.

Ví dụ application dùng service **Transform**, còn nhà cung cấp triển khai có thể đến từ module hoặc JAR khác. Java hỗ trợ hai cơ chế tạo service provider, nhưng **không phải hai cơ chế đều hoạt động trong mọi kiểu triển khai**:

- **Provider constructor:** ServiceLoader trực tiếp gọi **public constructor không tham số** của provider class; provider class phải là subtype/implementation của service.
- **Provider method:** Trong **explicit named module**, một provider class có thể công bố **public static method tên chính xác provider, không có tham số**, trả về đối tượng có kiểu trả về gán được cho service; class chứa provider method **không bắt buộc implements service**.

Khác biệt mấu chốt: một JAR đăng ký provider bằng **META-INF/services trên classpath** không được ServiceLoader xử lý provider method như named module explicit. Các **automatic modules** cũng yêu cầu provider constructor, không hỗ trợ provider method.

Bài này giải thích hợp đồng của JDK 17+, ví dụ runnable về cả hai đường, tầm quan trọng của module-info.java, cách đọc **ServiceLoader.Provider.type()/get()**, lỗi thường gặp và những giới hạn của class loading/lazy discovery.

## 2. Các khái niệm chính

### 2.1 Service type

Service type **S** thường là một public interface được consumer và các providers cùng nhìn thấy:

~~~java
package lesson.api;

public interface Transform {
    String apply(String input);
}
~~~

ClassLoader và module system phải bảo đảm consumer/provider dùng **cùng runtime service type**, không chỉ cùng binary name. Nếu host và plugin mỗi bên tự define một bản **lesson.api.Transform** riêng, ServiceLoader có thể từ chối provider do không assignable hoặc phát sinh lỗi type identity liên quan.

### 2.2 Provider class

Provider class là type được liệt kê trong **provides ... with ...** của module descriptor, hoặc trong cấu hình **META-INF/services/<service-name>** trên classpath.

Không phải mọi provider class đều là **instance được giao cho consumer**: với provider method, provider class có thể chỉ là **factory holder**. Đối tượng consumer nhận được là kết quả trả về từ method provider().

### 2.3 Provider constructor

Một **provider constructor** là public constructor không có tham số. Khi provider class không khai báo provider method theo quy tắc named-module, ServiceLoader cần class ấy assignable với service và khởi tạo trực tiếp.

~~~java
public final class DirectTransform implements Transform {
    public DirectTransform() {
    }

    @Override
    public String apply(String input) {
        return input;
    }
}
~~~

Đây là snippet nằm trong bối cảnh đã có interface Transform và imports/phần package thích hợp; không phải chương trình độc lập.

### 2.4 Provider method

Một provider method là **public static no-args method tên chính xác provider**. Với explicit named module:

~~~java
public final class FactoryProvider {
    private FactoryProvider() {
    }

    public static Transform provider() {
        return new SomeTransform();
    }
}
~~~

Đây là snippet cần các types Transform/SomeTransform tương ứng. **FactoryProvider** không cần implements Transform và không cần public no-args constructor. ServiceLoader gọi **FactoryProvider.provider()** để nhận đối tượng thực sự thực hiện service.

### 2.5 ServiceLoader.Provider<S>

Từ Java 9, **ServiceLoader.stream()** cung cấp các phần tử kiểu **ServiceLoader.Provider<S>**. Mỗi phần tử có:

- **type()**: Class của provider type có thể được lọc/kiểm tra trước khi tạo instance. Với provider method, đây là **kiểu trả về được khai báo của provider()**, không nhất thiết là class chứa factory method hoặc runtime class chính xác của object.
- **get()**: lấy/khởi tạo một instance của service; có thể gọi constructor hoặc provider method tùy cách triển khai.

Đừng nhầm **ServiceLoader.Provider.get()** với method tên **provider()** trên provider class: đây là hai API khác nhau.

## 3. Bảng so sánh theo cách triển khai

| Loại triển khai | Khai báo provider ở đâu? | Cách tạo | Điều kiện bắt buộc |
| --- | --- | --- | --- |
| **Explicit named module, direct provider** | **module-info.java**: provides S with Impl | Gọi provider constructor | Provider class public, implements/extends S, có public no-args constructor, nếu không có provider method. |
| **Explicit named module, factory provider** | **module-info.java**: provides S with Factory | Gọi public static provider() | Provider class public; provider() public static không tham số và kiểu trả về assignable với S; class factory không cần implements S. |
| **Classpath / unnamed module** | **META-INF/services/<fully-qualified-service-name>** | Gọi public no-args constructor | Class liệt kê phải implements/extends S; chỉ có provider() là **không đủ**. |
| **Automatic module trên module path** | Provider metadata suy từ **META-INF/services** trong JAR | Gọi public no-args constructor | Provider class phải assignable với S và có public no-args constructor; **provider method không được hỗ trợ**. |

**Cảnh báo:** “Đặt JAR lên module path” chưa bảo đảm hỗ trợ provider method. JAR phải là **explicit named module** có module descriptor **module-info.class** (tương ứng module-info.java khi biên dịch). Automatic module nhận tên tự động từ manifest/tên JAR là trường hợp khác.

## 4. Quy tắc cho explicit named module

### 4.1 requires, exports, uses và provides

Một hệ modular điển hình có:

~~~text
lesson.api
  exports lesson.api
  chứa interface Transform

lesson.providers
  requires lesson.api
  provides lesson.api.Transform with lesson.impl.CtorTransform,
      lesson.impl.FactoryProvider

lesson.app
  requires lesson.api
  uses lesson.api.Transform
  consumer gọi ServiceLoader.load(Transform.class)
~~~

- **requires** trong module provider/consumer cho phép tham chiếu đến API module.
- **exports** của module API cho phép các module khác truy cập service interface.
- **uses** trong explicit consumer module khai báo nhu cầu sử dụng service; ServiceLoader có thể báo ServiceConfigurationError nếu thiếu theo các overload và context liên quan.
- **provides ... with ...** khai báo provider classes thực sự thuộc chính module provider; không chỉ đến file resources.
- Module provider **không nhất thiết phải exports package implementation**. Javadoc còn khuyến nghị giữ package implementation đóng kín khi có thể.

### 4.2 Nếu class có cả constructor lẫn provider method?

Khi provider class trong explicit named module **khai báo provider method hợp lệ**, ServiceLoader sử dụng **method đó** để tạo instance, thay vì chọn constructor theo cảm tính.

Do đó provider method không chỉ là một tiện ích mà caller phải chủ động gọi bằng reflection. Nó là quy tắc mà **ServiceLoader** áp dụng khi module descriptor xác định provider class.

### 4.3 Factory provider không cần implements service

Ví dụ:

~~~java
public final class FactoryProvider {
    private FactoryProvider() {
        throw new AssertionError("not constructed");
    }

    public static Transform provider() {
        return new ActualTransform();
    }
}
~~~

Trong explicit module, điều này hợp lệ nếu **ActualTransform implements Transform** và method return type gán được cho Transform. ServiceLoader không cần gọi constructor private của FactoryProvider.

Nhưng nếu chính FactoryProvider được liệt kê trong **META-INF/services** trên classpath mà không implements Transform, lookup sẽ thất bại. Đó là khác biệt lớn nhất của chủ đề.

### 4.4 Đừng nhầm public method với public instance

**provider()** bắt buộc là public và static, không tham số. Nó có thể trả về một implementation class **không public** nếu kiểu trả về khai báo phù hợp với service và quy tắc accessibility của module cho phép.

**Provider.type()** không có nghĩa Class trả về luôn có public constructor không tham số hoặc có thể được consumer tự tạo. ServiceLoader.Provider.get() mới là con đường chuẩn để lấy instance.

## 5. Ví dụ runnable Java 17+ số 1: hai provider trong explicit named module

Ví dụ hoàn chỉnh này có ba modules: API, provider và consumer. Nó chứng minh:

- Provider **CtorTransform** được tạo qua public constructor.
- **FactoryProvider** không implements service và chỉ có private constructor, nhưng được chấp nhận vì có provider().
- **ServiceLoader.stream()** cho phép đọc type metadata trước khi gọi Provider.get().
- Với factory method, **Provider.type()** chính là **kiểu trả về khai báo** (ở đây FactoryResult), không phải FactoryProvider.

### 5.1 Cấu trúc file

~~~text
project/
└── src/
    ├── lesson.api/
    │   ├── module-info.java
    │   └── lesson/api/Transform.java
    ├── lesson.providers/
    │   ├── module-info.java
    │   └── lesson/impl/
    │       ├── CtorTransform.java
    │       └── FactoryProvider.java
    └── lesson.app/
        ├── module-info.java
        └── lesson/app/Main.java
~~~

**src/lesson.api/module-info.java**:

~~~java
module lesson.api {
    exports lesson.api;
}
~~~

**src/lesson.api/lesson/api/Transform.java**:

~~~java
package lesson.api;

public interface Transform {
    String apply(String input);
}
~~~

**src/lesson.providers/module-info.java**:

~~~java
module lesson.providers {
    requires lesson.api;

    provides lesson.api.Transform
            with lesson.impl.CtorTransform,
                 lesson.impl.FactoryProvider;
}
~~~

**src/lesson.providers/lesson/impl/CtorTransform.java**:

~~~java
package lesson.impl;

import lesson.api.Transform;

public final class CtorTransform implements Transform {
    public CtorTransform() {
        System.out.println("ctor invoked");
    }

    @Override
    public String apply(String input) {
        return "ctor:" + input;
    }
}
~~~

**src/lesson.providers/lesson/impl/FactoryProvider.java**:

~~~java
package lesson.impl;

import lesson.api.Transform;

public final class FactoryProvider {
    private FactoryProvider() {
        throw new AssertionError("not constructed");
    }

    public static FactoryResult provider() {
        System.out.println("factory method invoked");
        return new FactoryResult();
    }
}

final class FactoryResult implements Transform {
    @Override
    public String apply(String input) {
        return "factory:" + input;
    }
}
~~~

**src/lesson.app/module-info.java**:

~~~java
module lesson.app {
    requires lesson.api;
    uses lesson.api.Transform;
}
~~~

**src/lesson.app/lesson/app/Main.java**:

~~~java
package lesson.app;

import lesson.api.Transform;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        List<ServiceLoader.Provider<Transform>> providers =
                ServiceLoader.load(Transform.class).stream()
                        .sorted(Comparator.comparing(
                                p -> p.type().getName()))
                        .toList();

        System.out.println("provider count = " + providers.size());

        for (ServiceLoader.Provider<Transform> p : providers) {
            System.out.println("type = " + p.type().getName());
            Transform service = p.get();
            System.out.println("result = "
                    + service.apply("abc"));
        }
    }
}
~~~

### 5.2 Biên dịch và chạy

Đứng trong thư mục **project** có source tree như trên:

~~~bash
javac --module-source-path src -d mods -m lesson.api,lesson.providers,lesson.app
java --module-path mods --add-modules lesson.providers -m lesson.app/lesson.app.Main
~~~

**Lý do dùng --add-modules lesson.providers:** bảo đảm module provider có mặt trong graph của lần chạy này để lookup tìm được module chứa provider. Không nhầm một module JAR có mặt trên module path với một module chắc chắn đã được resolved vào module graph.

**Stdout đã kiểm chứng khi biên dịch/chạy JDK 21; code tương thích Java 17+:**

~~~text
provider count = 2
type = lesson.impl.CtorTransform
ctor invoked
result = ctor:abc
type = lesson.impl.FactoryResult
factory method invoked
result = factory:abc
~~~

### 5.3 Phân tích theo từng bước

1. **ServiceLoader.load(Transform.class)** tạo service loader cho service type. Module consumer đã có **uses lesson.api.Transform**.
2. **stream()** duyệt metadata providers. **sorted()** làm thứ tự demo ổn định theo class name thay vì dựa vào thứ tự discovery.
3. Trong output, **provider count = 2** chứng tỏ cả hai entries trong provides directive được phát hiện.
4. **type = lesson.impl.CtorTransform** là class provider trực tiếp, implements Transform.
5. Lúc **p.get()** tương ứng CtorTransform, constructor public không tham số chạy và in **ctor invoked**.
6. **type = lesson.impl.FactoryResult** là declared return type của FactoryProvider.provider(), không phải tên FactoryProvider.
7. **p.get()** tiếp theo gọi **FactoryProvider.provider()**, in **factory method invoked** và trả FactoryResult.
8. **FactoryProvider** có private constructor ném AssertionError. Không xuất hiện lỗi đó, vì ServiceLoader **không** tạo instance FactoryProvider bằng constructor.
9. Cả hai objects trả về thực sự implements Transform, nên consumer chỉ gọi **service.apply("abc")** mà không cần biết nguồn.

### 5.4 Vì sao FactoryResult có thể package-private?

FactoryResult là top-level class **không public** và thực thi Transform; provider method khai báo trả về FactoryResult. Nó nằm trong cùng module/package với FactoryProvider, nên code provider có thể truy cập nó.

Consumer **không trực tiếp new FactoryResult()** và không cần package implementation được exports. ServiceLoader hỗ trợ khởi tạo provider thông qua method đã công bố trong module descriptor. Nếu consumer cố phản chiếu/sử dụng class không public đó trực tiếp, vẫn phải tôn trọng Java/JPMS accessibility.

### 5.5 Những điểm làm kết quả sai

Nếu bỏ **uses** khỏi explicit consumer module, ServiceLoader có thể báo ServiceConfigurationError theo quy tắc của API.

Nếu bỏ **--add-modules lesson.providers** trong chính ví dụ, module provider không nhất thiết nằm trong resolved graph và có thể không được tìm thấy. Nếu thay **provider()** bằng tên khác như create(), ServiceLoader không nhận nó là provider method.

Nếu method chỉ là instance method hoặc có tham số, đó **không phải** provider method hợp lệ. Nếu FactoryProvider không implements Transform và không có provider method hợp lệ, module declaration có thể bị compiler từ chối hoặc runtime lookup thất bại tùy lỗi.

## 6. Ví dụ runnable Java 17+ số 2: classpath chỉ dùng constructor

Trường hợp truyền thống triển khai SPI trên **application classpath** không có module-info.java. ServiceLoader tìm providers qua **provider-configuration file**:

~~~text
META-INF/services/<fully-qualified-binary-name-of-service>
~~~

Ví dụ service **lesson.spi.Transform** cần file:

~~~text
META-INF/services/lesson.spi.Transform
~~~

với nội dung:

~~~text
lesson.impl.ClassicTransform
~~~

### 6.1 Cấu trúc

~~~text
classpath-project/
├── cp-src/
│   └── lesson/
│       ├── spi/Transform.java
│       ├── impl/ClassicTransform.java
│       └── app/ClasspathDemo.java
└── cp-out/
    └── META-INF/
        └── services/
            └── lesson.spi.Transform
~~~

**cp-src/lesson/spi/Transform.java**:

~~~java
package lesson.spi;

public interface Transform {
    String apply(String input);
}
~~~

**cp-src/lesson/impl/ClassicTransform.java**:

~~~java
package lesson.impl;

import lesson.spi.Transform;

public final class ClassicTransform implements Transform {
    public ClassicTransform() {
        System.out.println("classic constructor invoked");
    }

    @Override
    public String apply(String input) {
        return "classic:" + input;
    }
}
~~~

**cp-src/lesson/app/ClasspathDemo.java**:

~~~java
package lesson.app;

import lesson.spi.Transform;
import java.util.ServiceLoader;

public class ClasspathDemo {
    public static void main(String[] args) {
        for (Transform service : ServiceLoader.load(
                Transform.class)) {
            System.out.println("result = "
                    + service.apply("abc"));
        }
    }
}
~~~

**cp-out/META-INF/services/lesson.spi.Transform** là text file UTF-8:

~~~text
lesson.impl.ClassicTransform
~~~

### 6.2 Biên dịch và chạy

Đứng trong thư mục **classpath-project**. Đầu tiên tạo cây source và service file như mô tả. Bảo đảm provider configuration file nằm **trong cp-out/META-INF/services** chứ không chỉ ở cp-src.

~~~bash
javac -d cp-out   cp-src/lesson/spi/Transform.java   cp-src/lesson/impl/ClassicTransform.java   cp-src/lesson/app/ClasspathDemo.java
java -cp cp-out lesson.app.ClasspathDemo
~~~

Lệnh javac nhiều dòng dùng dấu nối **backslash** cho Linux/macOS shell. Nếu dùng Windows PowerShell, nhập trên một dòng:

~~~powershell
javac -d cp-out cp-src/lesson/spi/Transform.java cp-src/lesson/impl/ClassicTransform.java cp-src/lesson/app/ClasspathDemo.java
java -cp cp-out lesson.app.ClasspathDemo
~~~

Stdout thực tế đã kiểm chứng trên JDK 21:

~~~text
classic constructor invoked
result = classic:abc
~~~

ServiceLoader đọc text provider-configuration file, thấy **lesson.impl.ClassicTransform**, dùng class loader phù hợp để tìm class, kiểm tra assignable với service, rồi gọi **public no-args constructor**.

Không có module-info.java, không dùng provides directive và không sử dụng provider method. Để đóng gói JAR, bạn phải giữ nguyên path **META-INF/services/lesson.spi.Transform** trong archive; nếu thiếu entry này, ServiceLoader có thể không phát hiện provider dù class file vẫn tồn tại.

### 6.3 Cú pháp provider-configuration file

Theo Javadoc, provider configuration là **UTF-8 text**. Mỗi dòng là **fully qualified binary name** của provider, có thể có whitespace và comment bắt đầu bằng **#**:

~~~text
# Các provider của lesson.spi.Transform
lesson.impl.ClassicTransform
# lesson.impl.AnotherTransform
~~~

Các dòng trống và comments được bỏ qua. Provider names trùng trong file hoặc nhiều files được ServiceLoader khử trùng lặp theo quy tắc API. Nếu có nhiều JAR, loader có thể dùng **ClassLoader.getResources** để tìm nhiều files có cùng path META-INF/services/....

**File này không phải Java source và không chứa dòng provides lesson.spi.Transform with ...**. Dòng đó thuộc module-info.java của explicit named module.

## 7. Tình huống sai có chủ đích: classpath không dùng provider method

Hãy tưởng tượng có class:

~~~java
package lesson.impl;

import lesson.spi.Transform;

public final class FactoryOnly {
    private FactoryOnly() {
    }

    public static Transform provider() {
        return new ClassicTransform();
    }
}
~~~

Đây là một Java source class hợp lệ nếu ClassicTransform/Transform đã tồn tại, nhưng FactoryOnly **không implements Transform**. Khi provider-configuration file đổi thành:

~~~text
lesson.impl.FactoryOnly
~~~

ServiceLoader chạy theo **classpath rule**, đòi FactoryOnly assignable với lesson.spi.Transform và có public no-args constructor. Vì FactoryOnly không thỏa, loader thất bại **dù có public static provider()**.

Với cùng ClasspathDemo và file provider-configuration thay đổi như trên, JDK 21 báo lỗi bắt đầu bằng:

~~~text
Exception in thread "main" java.util.ServiceConfigurationError: lesson.spi.Transform: lesson.impl.FactoryOnly not a subtype
~~~

Phần stack trace và line numbers có thể khác theo JDK. Dòng trên đã quan sát khi chạy ví dụ thực tế với JDK 21.

**Đây là khác biệt có ý nghĩa nhất giữa explicit modules và classpath:** Classpath ServiceLoader không nhìn thấy một phương thức provider() rồi tự áp dụng quy tắc provider factory của module explicit.

### 7.1 Cách sửa tình huống classpath

Có hai hướng chính:

- **Giữ classpath:** đăng ký một **class public implements Transform có public constructor không tham số**, ví dụ ClassicTransform.
- **Chuyển sang explicit named module:** viết **module-info.java** có provides ... with FactoryOnly và cung cấp provider() hợp lệ theo module rules.

Không phải cứ thêm chữ **static** hoặc đổi tên file META-INF/services là chuyển sang factory provider. Mô hình đăng ký là yếu tố quyết định.

## 8. Automatic module: gần named module nhưng quy tắc constructor

Một **automatic module** là JAR không có explicit module descriptor nhưng được đặt trên **module path** và được module system xem như named automatic module theo những quy tắc riêng.

Đối với ServiceLoader, Javadoc nêu rõ **automatic module bắt buộc có provider constructor**; provider method **không được hỗ trợ**.

| Trường hợp | Descriptor | Provider method? | Constructor requirement |
| --- | --- | --- | --- |
| Explicit module | module-info.class thực sự | Có | Không cần nếu dùng provider method. |
| Automatic module | Sinh tự động từ JAR không có descriptor | **Không** | Có, public no-args và assignable với service. |
| Unnamed module/classpath | Không có descriptor | **Không** | Có, public no-args và assignable với service. |

Một JAR có **Automatic-Module-Name** trong manifest vẫn là **automatic module** nếu không có explicit module-info.class. Thuộc tính manifest đặt tên module ổn định hơn, **không tự cấp tính năng provider method**.

Có thể phân phối provider theo cách classpath trước, sau đó chuyển sang explicit module. Khi chuyển, bạn phải xác định rõ cách đăng ký:

~~~text
Classpath / automatic module:
  META-INF/services/lesson.spi.Transform
    lesson.impl.ClassicTransform

Explicit module:
  module lesson.providers {
    requires lesson.api;
    provides lesson.api.Transform with lesson.impl.CtorTransform,
        lesson.impl.FactoryProvider;
  }
~~~

Trong explicit module, không nên dựa vào việc provider method được ServiceLoader tìm ra chỉ từ service file nếu không có provides directive.

## 9. Provider constructor và provider method: quy tắc hợp lệ chi tiết

### 9.1 Provider constructor

Đối với đường trực tiếp:

- Provider class phải **public**.
- Provider class phải là concrete class có thể khởi tạo và **implements/extends service**.
- Phải có **public no-args constructor**; private/package-private no-args constructor không đạt hợp đồng.
- Constructor có thể thực hiện dependency setup, nhưng exception từ constructor thường bị ServiceLoader bọc thành **ServiceConfigurationError** khi được gọi.
- Một constructor có tham số không được ServiceLoader tự dependency-inject. Nếu bạn cần factory logic, explicit named module có thể sử dụng provider method.
- Nếu class là abstract hoặc không thể tạo instance, cấu hình constructor-path không hợp lệ.

### 9.2 Provider method

Đối với explicit named module:

- Tên method là chính xác **provider**, lowercase.
- **public static**, **không tham số**.
- Return type được khai báo phải **assignable với service type**.
- Method có thể trả object của một class implementation khác với chính factory holder.
- Method không được trả **null**; ServiceLoader.Provider.get() coi đó là lỗi cấu hình.
- Method có thể ném exception; ServiceLoader báo **ServiceConfigurationError**, thường lưu cause thích hợp.
- Nếu class file có nhiều public static no-args methods tên provider theo những descriptors khác nhau, ServiceLoader có thể coi đó là ambiguous/error.
- Class provider nằm trong **cùng module** với provides directive.
- Không cần public no-args constructor của factory holder khi provider method hợp lệ.

**Tránh nhầm:** class FactoryProvider với static method tên makeProvider hoặc newInstance không được nhận là provider method tự động. Chỉ đúng tên **provider()** theo hợp đồng.

### 9.3 Top-level hoặc static nested provider

JLS yêu cầu service provider được nêu trong module declaration là public class hoặc interface kiểu top-level hay nested static phù hợp. Non-static inner class không phù hợp làm provider type trong provides directive. Với path constructor, khả năng tạo bằng public no-args còn cần thỏa đặc tính constructor của Java.

Không nên dùng enum class làm provider trong provides directive; JLS quy định đó là compile-time error. Một abstract class hoặc interface có thể là provider holder nếu có provider method hợp lệ, nhưng không thể là direct provider cần constructor.

## 10. ServiceLoader.Provider.type() có thể đánh lừa người đọc

**Provider.type()** không đồng nghĩa “class chứa module descriptor entry” trong mọi trường hợp.

### 10.1 Provider constructor

Với provider class CtorTransform:

~~~text
module-info.java:
  provides Transform with CtorTransform

ServiceLoader.Provider.type():
  lesson.impl.CtorTransform
~~~

### 10.2 Provider method

Với FactoryProvider:

~~~text
module-info.java:
  provides Transform with FactoryProvider

FactoryProvider declares:
  public static FactoryResult provider()

ServiceLoader.Provider.type():
  lesson.impl.FactoryResult
~~~

Đây là **kiểu trả về khai báo**, không nhất thiết runtime class chính xác của object nếu method trả subtype cụ thể hơn. Nếu khai báo:

~~~java
public static Transform provider() {
    return new FactoryResult();
}
~~~

thì **Provider.type()** có thể là **lesson.api.Transform**, dù runtime object là FactoryResult.

Vì vậy:

- Dùng **Provider.type()** để quan sát/lọc theo contract của ServiceLoader, nhưng hiểu nó đại diện cho loại gì.
- Không giả định **type()** trả FactoryProvider.class.
- Không dùng **type().getConstructor().newInstance()** để tạo provider một cách tổng quát.
- Dùng **Provider.get()** nếu muốn đúng cơ chế khởi tạo do ServiceLoader hỗ trợ.

### 10.3 Annotation filtering cần tính đến return type

Một hệ thống có annotation trên provider factory holder sẽ không nhất thiết nhìn thấy annotation ấy qua Provider.type() nếu factory method trả về type khác. Nếu framework dùng **stream().filter(p -> p.type().isAnnotationPresent(...))**, hãy đặt metadata/annotations ở **declared return type** hoặc chọn một chiến lược lookup có chủ đích.

Điều này quan trọng trong plugin systems có nhiều implementations cần filter theo khả năng của provider.

## 11. Lazy discovery, instantiation và cache

### 11.1 load() không có nghĩa tạo mọi instance ngay

~~~java
ServiceLoader<Transform> loader =
        ServiceLoader.load(Transform.class);
~~~

Chỉ tạo ServiceLoader. Provider discovery/instantiation chủ yếu diễn ra **lazily** khi iterator hoặc stream thực sự được xử lý.

Với iterator:

~~~java
for (Transform transform : loader) {
    System.out.println(transform.apply("x"));
}
~~~

Provider instances được tạo khi duyệt, và ServiceLoader duy trì cache các providers đã được load.

Với stream:

~~~java
loader.stream()
        .filter(p -> p.type().getName().contains("Factory"))
        .map(ServiceLoader.Provider::get)
        .forEach(p -> System.out.println(p.apply("x")));
~~~

Lọc bằng **type()** có thể xảy ra trước **get()**. Không nên cho rằng chỉ tạo Stream là factory method/constructor đã chạy; tuy nhiên khi xử lý stream, class loading và provider discovery có thể đã có tác động runtime trước get().

### 11.2 Phân biệt hai cache

- **Iterator** cache các instantiated provider objects theo quy tắc ServiceLoader.
- **Stream** cache provider descriptors/Provider objects đã tìm; **Provider.get()** mới tạo hoặc lấy instance theo contract của method. Không tự giả định mỗi lần get() luôn trả cùng singleton.
- **reload()** xóa provider caches của chính ServiceLoader instance. Iterator/Stream đang dùng trước reload phải bỏ đi; chúng có thể ném **ConcurrentModificationException** nếu dùng sau khi reload.
- Một ServiceLoader object không được bảo đảm thread-safe để nhiều threads cùng dùng đồng thời.

Provider constructor và provider() nên được thiết kế với semantics tạo instance rõ ràng. Singleton, pooling hoặc dependency caching là trách nhiệm implementation, không phải điều ServiceLoader tự bảo đảm chỉ bởi việc dùng provider method.

## 12. Provider lifecycle và công việc thực tế

### 12.1 Constructor-path thích hợp khi

- Implementation trực tiếp đơn giản, có default constructor public.
- Không cần quyết định runtime phức tạp trước khi tạo object.
- Cần chạy trên classpath hoặc automatic modules.
- Muốn dễ đóng gói qua META-INF/services và tương thích rộng.

### 12.2 Provider method thích hợp khi

- Explicit named module muốn **ẩn implementation cụ thể** đằng sau factory holder.
- Object cần được tạo qua dependency graph, cache, singleton hoặc cấu hình nội bộ module.
- Provider class không muốn/không thể implements service trực tiếp.
- Muốn dùng internal implementation không có public constructor nhưng vẫn trả đối tượng service cho consumer.
- Muốn trì hoãn quyết định chọn subtype cho đến lúc ServiceLoader gọi provider().

**Giới hạn:** phương thức provider() không tự nhận context/arguments từ ServiceLoader; nó là **no-args**. Nếu cần nhận cấu hình từ caller, thiết kế service interface trả factory object hoặc cung cấp method nhận parameters sau khi ServiceLoader giao instance, thay vì tưởng rằng ServiceLoader tự đưa tham số vào provider().

### 12.3 Package encapsulation

Với explicit modules, nên **không export implementation package** nếu consumer chỉ cần public service API. Điều này cho phép implementation thay đổi mà không làm public module surface phình ra.

Ví dụ module provider:

~~~java
module lesson.providers {
    requires lesson.api;
    provides lesson.api.Transform with lesson.impl.FactoryProvider;
}
~~~

Không có exports lesson.impl. Consumer dùng Transform mà không phải tham chiếu trực tiếp đến FactoryProvider.

## 13. ServiceLoader.load: chọn context loader cho đúng

Các overload đáng chú ý:

~~~java
ServiceLoader.load(Transform.class);
ServiceLoader.load(Transform.class, explicitLoader);
ServiceLoader.load(layer, Transform.class);
~~~

Đây là snippet, cần biến explicitLoader/layer khi chạy.

- **load(service)**: chọn **Thread Context ClassLoader** của thread hiện tại theo hợp đồng API.
- **load(service, classLoader)**: xác định loader làm điểm xuất phát cho tìm providers và provider configuration resources.
- **load(ModuleLayer, service)**: tìm trong layer được chỉ định và parent layers theo quy tắc module layer, hữu ích với plugin runtime tạo layer động.

Không đánh đồng **TCCL** với **defining loader** của service interface. Nếu service type ở host bị plugin loader tự define bản trùng, provider có thể không assignable với host service type. Kiểm tra **serviceClass.getClassLoader()**, **provider.getClass().getClassLoader()** và module graph trong quá trình chẩn đoán.

**TCCL phải được khôi phục** nếu hệ thống thay nó tạm trong shared thread pool: worker sống lâu có thể giữ ClassLoader plugin cũ, làm memory retention sau unload.

## 14. Service provider trong ModuleLayer động

Khi plugin runtime tạo **ModuleLayer mới**, code host có thể dùng:

~~~java
ServiceLoader<Transform> services =
        ServiceLoader.load(pluginLayer, Transform.class);
~~~

Đây là snippet, cần biến pluginLayer và service Transform phù hợp, module graph đã có providers hợp lệ.

**ServiceLoader.load(layer, service)** xem providers trong layer và ancestors. Với one-loader/many-loaders modules, ServiceLoader còn có semantics tìm provider dựa trên module layer, không chỉ đọc một file META-INF/services ở current working directory.

Điều cần đảm bảo:

1. Module descriptor của provider có **provides S with Provider**.
2. Module chứa service interface có exports phù hợp.
3. Consumer/module context có quyền **uses** theo API.
4. Plugin layer đã được define và có các modules providers.
5. Runtime service Class mà caller truyền vào là **cùng service identity** provider được thiết kế để implement.
6. Vòng đời provider/loader được quản lý khi plugin dừng; cache ServiceLoader, futures và threads có thể giữ loaders cũ.

Provider method không thay đổi các quy tắc module access/identity. Nó chỉ thay cách tạo object từ provider class sau khi provider được tìm.

## 15. Lỗi thường gặp và thông điệp cần hiểu

### 15.1 ServiceConfigurationError: not a subtype

**Nguyên nhân điển hình:**

- Trên classpath/automatic module, provider class trong META-INF/services không implements service.
- Runtime có hai bản class service cùng binary name nhưng khác defining loaders.
- Classpath registration trỏ đến factory holder chỉ có static provider() thay vì implementation trực tiếp.

**Hành động:** kiểm tra deployment mode, service interface identity, file META-INF/services và public provider constructor. Không dùng provider method trên classpath để né yêu cầu subtype.

### 15.2 ServiceConfigurationError: Unable to get public no-arg constructor

Provider class dùng constructor-path nhưng không có **public** constructor không tham số. Có thể bạn khai báo constructor nhận dependencies:

~~~java
public DirectProvider(Config config) {
}
~~~

ServiceLoader không tự inject Config. Trong explicit named module, cân nhắc provider method; còn classpath/automatic module phải cung cấp constructor public no-args hoặc chuyển mô hình provider thành service factory với constructor no-args.

### 15.3 Provider method trả null

Trong explicit named module:

~~~java
public static Transform provider() {
    return null;
}
~~~

Đây là sai contract khi ServiceLoader gọi method. ServiceLoader.Provider.get() báo **ServiceConfigurationError**. Luôn trả một object assignable với service và đã ở trạng thái hợp lệ.

### 15.4 Provider method ném exception

~~~java
public static Transform provider() {
    throw new IllegalStateException("Configuration missing");
}
~~~

ServiceLoader báo ServiceConfigurationError, thường giữ nguyên nhân ở cause. Điều tra lỗi factory bên trong chứ không chỉ catch rồi âm thầm bỏ qua trong mọi trường hợp.

### 15.5 Thiếu uses ở explicit consumer module

Module có consumer code gọi ServiceLoader nhưng không khai báo **uses service.type** có thể gặp ServiceConfigurationError. Đừng nghĩ chỉ **requires service-api-module** là đủ cho quy tắc service use trong explicit named module.

### 15.6 Provider module nằm trên module path nhưng không resolved

Có module provider JAR không có nghĩa ServiceLoader luôn tìm thấy. Module graph khi khởi động có thể chưa chứa provider module. Kiểm tra **--add-modules**, root modules, service binding hoặc định nghĩa ModuleLayer phù hợp.

### 15.7 Không thấy provider vì quên META-INF/services

Nếu triển khai classpath mà thiếu file **META-INF/services/fully.qualified.Service**, ServiceLoader có thể trả zero providers dù implementation class compile bình thường. Kiểm tra output/JAR entries, không chỉ source tree.

### 15.8 Nhiều provider implementations không được tìm theo thứ tự mong đợi

Các modules khác nhau có thứ tự discovery không được bảo đảm như thứ tự bạn nhìn trên filesystem. Các provider entries trong **một provides directive** có thứ tự theo module descriptor, nhưng các modules trong một layer có thể không có thứ tự ổn định.

Nếu cần chọn provider dựa trên priority, định nghĩa metadata/config/ordering rõ ràng và sort, như ví dụ named module.

### 15.9 Nhầm ServiceLoader.Provider.type với provider class

Với provider method, type() là **declared return type** của provider(), nên khác factory holder. Không dùng điều này để truy cập constructor của factory holder hoặc suy ra annotation đặt ở factory holder.

### 15.10 Concurrent use hoặc reload khi đang iterate

ServiceLoader instances không thread-safe. Việc gọi reload trong khi đang duyệt iterator/stream cũ có thể ném ConcurrentModificationException. Thiết kế cache và synchronization tại cấp application/framework phù hợp thay vì dùng ServiceLoader object chia sẻ không khóa giữa nhiều threads.

## 16. Bảng quyết định khi thiết kế provider

| Câu hỏi | Cách tiếp cận |
| --- | --- |
| Có explicit module-info.java với provides? | Có thể dùng provider constructor **hoặc** provider method. |
| Provider class trực tiếp implements service và có public no-args constructor? | Constructor-path đơn giản, portable. |
| Class factory không implements service nhưng trả service object? | Dùng public static provider() trong **explicit named module**. |
| Provider nằm trong JAR trên classpath? | META-INF/services + subtype public + public no-args constructor. |
| Provider là automatic module trên module path? | Constructor-path; provider method không hỗ trợ. |
| Muốn ẩn implementation khỏi consumer modules? | Đóng kín implementation package, chỉ export service API. |
| Muốn inspect type trước khi tạo instance? | ServiceLoader.stream() và Provider.type(), nhớ factory return type. |
| Muốn tạo instance đúng cách không quan tâm cơ chế? | Dùng Provider.get() hoặc iterator(). |
| Muốn tìm providers trong ModuleLayer động? | ServiceLoader.load(layer, service). |
| Muốn hot reload providers? | ServiceLoader.reload() và tạo/lifecycle loaders/layers phù hợp; reload không tự thay class đã định nghĩa. |
| Muốn singleton/provider cache? | Thiết kế rõ trong implementation; đừng dựa vào việc gọi get() luôn trả cùng object. |

## 17. An toàn, độ tin cậy và tương thích

### 17.1 Không xem SPI discovery là cơ chế trust

ServiceLoader có thể nạp class và chạy constructor/provider method từ module/JAR trong runtime. Đó là **mã thực thi**, có thể gây side effects, network I/O hoặc truy cập dữ liệu. Chỉ nạp providers từ nguồn phù hợp với trust policy của ứng dụng; ClassLoader/module boundary không tự là security sandbox đầy đủ.

### 17.2 Tách errors của cấu hình với lỗi application

Nếu provider không tìm được, ServiceLoader có thể cho zero items. Nếu provider được khai báo nhưng **không hợp lệ**, ServiceLoader thường báo **ServiceConfigurationError** trong iteration, stream processing hoặc get(). Không nên catch tất cả Throwable để im lặng bỏ qua; lỗi cấu hình của deployment là tín hiệu cần sửa.

### 17.3 Thiết kế provider() không làm công việc quá bất ngờ

Provider method có thể phức tạp, nhưng nên document rõ chi phí khởi tạo, tạo thread, mở kết nối và cleanup. Một factory method thực hiện hoạt động tốn kém trong lần lookup đầu có thể tăng latency; side effects hoặc exception sẽ xuất hiện lúc consumer dùng ServiceLoader.

### 17.4 Class loader leaks khi redeploy

Nếu application giữ ServiceLoader, Provider descriptors, provider instances hoặc TCCL của plugin sau khi dừng, defining loader cũ có thể vẫn reachable. **reload()** chỉ xóa cache của ServiceLoader instance, không tự đóng plugin executor hoặc thu hồi module layer ngay. Plugin manager phải điều phối lifecycle riêng.

## 18. Bài tập tự kiểm tra

**Câu 1.** Provider class của explicit named module không implements service, có private constructor nhưng có public static no-args provider() trả service. Hợp lệ không?

**Đáp án:** Có, nếu provider method và module descriptor hợp lệ. ServiceLoader dùng provider() để lấy instance.

**Câu 2.** Classpath META-INF/services liệt kê class ở câu 1. ServiceLoader có tự gọi static provider() không?

**Đáp án:** Không. Classpath provider phải assignable với service và có public no-args constructor.

**Câu 3.** Một automatic module trên module path có hỗ trợ provider method không?

**Đáp án:** Không. Theo Javadoc, automatic module phải dùng provider constructor.

**Câu 4.** Trong explicit named module, provider class có public no-args constructor và public static provider() hợp lệ. ServiceLoader dùng con đường nào?

**Đáp án:** Provider method theo quy tắc khi provider method được khai báo.

**Câu 5.** ServiceLoader.Provider.type() cho FactoryProvider.provider() trả FactoryResult: type() là FactoryProvider.class hay FactoryResult.class?

**Đáp án:** FactoryResult.class, vì là declared return type của provider method.

**Câu 6.** Nếu provider() khai báo return type Transform nhưng thực tế trả FactoryResult, type() có tự đổi thành FactoryResult.class không?

**Đáp án:** Không. type() phản ánh **declared return type**, nên là Transform.class.

**Câu 7.** Thiếu module-info.java nhưng JAR có Automatic-Module-Name có được dùng factory-only provider() không?

**Đáp án:** Không. Automatic-Module-Name không biến automatic module thành explicit module có provider-method support.

**Câu 8.** Tại sao consumer explicit module nên có uses?

**Đáp án:** Để khai báo service dependency với module system và đáp ứng yêu cầu ServiceLoader khi gọi từ explicit module.

**Câu 9.** Provider method trả null thì sao?

**Đáp án:** ServiceLoader báo ServiceConfigurationError khi cố tạo service object.

**Câu 10.** ServiceLoader.load(Transform.class) có chắc tạo tất cả instances ngay không?

**Đáp án:** Không. Discovery/instantiation chủ yếu lazy thông qua iterator/stream/get().

**Câu 11.** Nếu muốn cùng một service type được chia sẻ giữa host và plugin, điều gì quan trọng ở ClassLoader?

**Đáp án:** Host và provider phải dùng cùng runtime Class identity của service, không chỉ cùng tên chuỗi.

**Câu 12.** Provider method có được nhận tham số Config do ServiceLoader tự inject không?

**Đáp án:** Không. Provider method theo hợp đồng là public static no-args. Cấu hình cần được xử lý qua thiết kế khác.

## 19. Tổng kết

~~~text
                     ServiceLoader<S>
                            |
              +-------------+-------------+
              |                           |
       Explicit named module     Classpath / automatic module
              |                           |
       module-info.java          META-INF/services / metadata
       provides S with P                  |
              |                           |
      Có public static provider()?        |
           |         |                    |
          Có        Không                 |
           |         |                    |
           v         v                    v
      gọi P.provider()      tạo P qua public no-args constructor
           |                       |
           v                       v
     S-compatible object     P phải implements/extends S
              |                           |
              +-------------+-------------+
                            |
                            v
                     consumer nhận S
~~~

**Ghi nhớ năm điểm:**

1. **Provider constructor** cần public no-args và provider class assignable với service.
2. **Provider method** chỉ được hỗ trợ cho **explicit named module** theo đường provides directive; factory holder không nhất thiết implements service.
3. **Classpath và automatic module** dùng constructor-path, không chỉ dựa vào static provider().
4. **ServiceLoader.Provider.type()** của method-path là **declared return type** của provider(), còn **get()** mới lấy instance.
5. Discovery/instantiation **lazy**, có cache, lỗi báo **ServiceConfigurationError** và vẫn phải tôn trọng class-loader identity, module boundaries và lifecycle.

### Tài liệu chuẩn

- Java SE 17 **ServiceLoader API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 **ServiceLoader.Provider API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java SE 17 **JLS §7.7.4 Service Provision**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4
- Java SE 17 **ModuleLayer API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Dev.java **Decoupling Modules with Services**: https://dev.java/learn/organizing/modules/services/
