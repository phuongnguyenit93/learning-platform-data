# Điều kiện public, khả năng gán kiểu và constructor không tham số của SPI trên classpath

## 1. Bối cảnh: ServiceLoader nạp provider từ classpath như thế nào?

Một **Service Provider Interface (SPI)** mô tả khả năng mà ứng dụng chính (host) cần, còn **provider** là lớp hiện thực khả năng đó. Trên **classpath**, Java có thể tìm provider thông qua **java.util.ServiceLoader** mà host không cần trực tiếp gọi constructor của từng implementation.

Ví dụ, host chỉ phụ thuộc giao diện GreetingService, còn JAR của bên mở rộng đăng ký lớp PoliteGreeting. Khi duyệt ServiceLoader, JVM đọc tài nguyên **META-INF/services/<tên nhị phân đầy đủ của service>**, tải tên lớp provider và tạo instance.

Ba điều kiện cốt lõi đối với một provider được đăng ký theo cơ chế **META-INF/services trên classpath** là:

1. **Lớp provider phải public**, có thể được loader nhìn thấy và là lớp cụ thể có thể khởi tạo.
2. **Lớp provider phải gán được cho kiểu service**: implements interface SPI hoặc extends service class tương ứng.
3. **Lớp provider phải có constructor public không tham số** để ServiceLoader tạo instance.

Đây là điều kiện cho provider kiểu **constructor trên classpath**; không được nhầm với cơ chế public static provider() có thể dùng trong một số **named module**. Một chữ ký đúng nhưng cấu hình runtime sai vẫn có thể khiến ứng dụng không tìm được provider.

## 2. Ba điều kiện và cách phân biệt

| Kiểm tra | Điều cần đúng | Lỗi thường gặp |
| --- | --- | --- |
| Public/khả năng truy cập | Provider là public class phù hợp, không phải non-static inner class; class loader có thể tìm thấy nó | Lớp package-private, tên provider sai, JAR không ở classpath |
| Khả năng gán kiểu (assignability) | ServiceType.class.isAssignableFrom(ProviderType.class) trả true | Có phương thức trùng tên nhưng quên implements, extends sai kiểu, hai bản SPI do class loader khác nhau định nghĩa |
| Constructor không tham số | Có constructor **public** với **0 tham số**, có thể gọi thành công | Chỉ có constructor nhận Config, constructor private/package-private, constructor ném lỗi |

Ngoài ba điều kiện đó, provider phải thực sự khởi tạo được: không abstract, không phải interface khi dùng đường tạo instance trực tiếp, không bị lỗi khởi tạo lớp, thiếu dependency hoặc vòng lặp khởi tạo. Tệp đăng ký dịch vụ cũng phải đúng tên và định dạng.

Một lớp có thể qua hai điều kiện nhưng trượt điều kiện còn lại. Ví dụ, public và implements SPI không bảo đảm có public no-arg constructor; ngược lại, public constructor cũng không làm lớp trở thành subtype của SPI.

## 3. Điều kiện public: public cho cả lớp và constructor

### 3.1. Public class là điều kiện riêng

Trong Java, một top-level class khai báo không có public sẽ có quyền truy cập package-private. Ví dụ sau **không hợp lệ để làm classpath provider theo quy tắc ServiceLoader**, dù constructor được ghi là public:

~~~java
package example.provider;

import example.spi.GreetingService;

// Mã minh họa trường hợp sai, không thay thế provider của ví dụ chạy ở phần 7.
final class HiddenGreeting implements GreetingService {
    public HiddenGreeting() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Constructor public không thể bù cho lớp package-private. Một provider khai báo là public static nested class có thể dùng nếu đáp ứng các điều kiện còn lại; lúc đăng ký phải dùng **binary name** có dấu **$** giữa tên lớp ngoài và tên lớp lồng. Một **non-static inner class** phụ thuộc instance của lớp bao ngoài nên không phù hợp cho provider được tạo trực tiếp bằng public no-arg constructor.

Giao diện SPI cũng cần **truy cập được từ provider và caller**. Đối với SPI dự định dùng qua package/JAR, thường khai báo public interface hoặc public abstract class. Đừng hiểu rằng chỉ thêm public vào SPI đã làm provider hợp lệ.

### 3.2. Public không có nghĩa là ở đúng classpath

Dù class là public, ServiceLoader vẫn không tìm ra nó nếu không có lớp bytecode trong classpath của loader liên quan, tên trong service descriptor sai, hoặc không nhìn thấy dependency cần thiết. Chữ public điều chỉnh khả năng truy cập của mã Java; **đường tìm lớp và tài nguyên** do class loader quyết định.

Ở phần lớn ứng dụng classpath thông thường, ServiceLoader.load(ServiceType.class) dùng **thread context class loader** hiện tại. Trong host/plugin container có nhiều loader, kết quả tìm provider có thể khác nhau giữa các thread hoặc giữa các loader. Khi cần chủ động chọn loader, dùng overload ServiceLoader.load(serviceClass, classLoader) và đảm bảo loader đó nhìn thấy cả resource đăng ký lẫn provider.

## 4. Khả năng gán kiểu: cùng chữ ký không có nghĩa là cùng SPI

Java dùng **nominal typing** cho class/interface, không suy ra một lớp implements interface chỉ vì có method giống hệt.

~~~java
// Chỉ là minh họa: lớp này chưa implements GreetingService.
public final class LooksLikeGreeting {
    public String greet(String name) {
        return "Hello, " + name;
    }

    public LooksLikeGreeting() {}
}
~~~

Một lớp như LooksLikeGreeting có thể có method public với cùng tham số và kiểu trả về nhưng **không gán được cho GreetingService**. Để thành provider, cần khai báo:

~~~java
public final class PoliteGreeting implements GreetingService {
    public PoliteGreeting() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Hai đoạn này là mã rút gọn nhằm minh họa quan hệ kiểu; chương trình hoàn chỉnh và các khai báo package/import nằm ở phần 7.

Kiểm tra bằng reflection theo đúng chiều:

~~~java
boolean compatible = GreetingService.class.isAssignableFrom(PoliteGreeting.class);
~~~

Giá trị compatible là true khi PoliteGreeting triển khai GreetingService đang được host dùng (hoặc là subtype của một service class). Cách viết ngược PoliteGreeting.class.isAssignableFrom(GreetingService.class) không trả lời câu hỏi đó.

**Cẩn trọng với nhiều class loader.** Định danh class tại runtime phụ thuộc **tên nhị phân và class loader định nghĩa nó**. Nếu host và plugin vô tình đóng gói hai bản SPI giống tên nhưng do hai loader khác nhau định nghĩa, quan hệ assignability có thể thất bại dù mã nguồn cùng ghi implements example.spi.GreetingService. Thiết kế plugin nên thống nhất nơi tải bản SPI dùng chung và tránh nhúng bản sao SPI riêng vào từng plugin khi chúng cần trao đổi cùng kiểu với host.

## 5. Constructor không tham số: public, tồn tại và gọi được

### 5.1. Constructor tường minh và constructor mặc định

ServiceLoader cần một **public constructor không có tham số** để tạo provider trên classpath. Khai báo tường minh giúp ý định rõ ràng:

~~~java
public final class PoliteGreeting implements GreetingService {
    public PoliteGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Nếu một **public class không khai báo bất kỳ constructor nào**, compiler sinh **default constructor** không tham số với mức truy cập tương ứng (public). Vì vậy trường hợp đó cũng đáp ứng điều kiện, miễn lớp có thể tạo được.

Nhưng **ngay khi tự khai báo một constructor nhận tham số**, Java không còn tự sinh default constructor:

~~~java
// Minh họa trường hợp sai với ServiceLoader classpath.
public final class ConfiguredGreeting implements GreetingService {
    private final String prefix;

    public ConfiguredGreeting(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public String greet(String name) {
        return prefix + name;
    }
}
~~~

ConfiguredGreeting public và implements SPI, nhưng thiếu constructor public không tham số. Không thể yêu cầu ServiceLoader trên classpath tự đoán một Config để truyền vào constructor.

Constructor private, protected hoặc package-private không thỏa yêu cầu public, ngay cả khi không nhận tham số. Constructor của superclass **không được thừa kế** như method; điều kiện cần kiểm tra trên class provider thực sự được ghi trong descriptor.

### 5.2. Có constructor chưa đủ nếu gọi constructor thất bại

Một public no-arg constructor vẫn có thể ném exception hoặc kích hoạt lỗi khởi tạo lớp. Khi ServiceLoader tạo instance, các lỗi đó có thể được báo dưới dạng **ServiceConfigurationError**, kèm nguyên nhân gốc nếu có. Không để constructor phụ thuộc vào trạng thái global chưa khởi tạo hoặc thực hiện công việc mạng kéo dài không được công bố.

Nếu provider cần cấu hình runtime, với SPI trên classpath có thể:
- Tạo provider qua no-arg constructor rồi gọi phương thức cấu hình/khởi động được SPI công bố, có kiểm soát vòng đời và lỗi.
- Cấp context qua phương thức riêng của hợp đồng thay vì nhúng dependency ngầm vào constructor.
- Nếu kiểm soát kiến trúc JPMS của named module, cân nhắc provider factory method như phần 10; không áp dụng sai phương thức đó cho JAR classpath.

Đừng dùng reflection để ép constructor private thành accessible nhằm "sửa" cơ chế ServiceLoader; làm như vậy tạo một cơ chế khởi tạo khác, phụ thuộc chính sách truy cập và module, không giải quyết hợp đồng classpath provider.

## 6. Đăng ký đúng META-INF/services trên classpath

Đối với SPI example.spi.GreetingService, đường dẫn tài nguyên **phải chính xác**:

~~~text
META-INF/services/example.spi.GreetingService
~~~

Nội dung tệp, mã hóa **UTF-8**, ghi **binary name đầy đủ** của mỗi provider, mỗi tên một dòng:

~~~text
example.provider.PoliteGreeting
~~~

Không thêm đuôi .class hay .java vào tên file cấu hình hoặc tên lớp trong nội dung. Tên file theo **service**, còn dòng nội dung theo **provider**. Có thể có nhiều provider, mỗi provider một dòng; dòng trống được bỏ qua và dấu # bắt đầu comment. Nếu cùng provider bị liệt kê trùng, ServiceLoader bỏ qua tên trùng theo quy tắc của nó.

Tài nguyên này có thể nằm trong provider JAR hoặc một classpath entry khác, nhưng khi chạy, loader phải tìm được resource và load được lớp tương ứng. Tệp nằm đúng thư mục nguồn của dự án chưa chắc đã được copy vào JAR hay đưa vào classpath cuối cùng. Khi đóng gói, kiểm tra bên trong artifact thay vì chỉ nhìn source tree.

## 7. Ví dụ hoàn chỉnh, chạy được với Java 17+

Ví dụ sau dùng một SPI public, một provider public có public no-arg constructor, một host không import provider và một service descriptor.

Cấu trúc thư mục, tính từ thư mục demo:

~~~text
demo/
├── src/
│   └── example/
│       ├── spi/GreetingService.java
│       ├── provider/PoliteGreeting.java
│       └── app/Main.java
├── resources/
│   └── META-INF/
│       └── services/
│           └── example.spi.GreetingService
└── out/                    (thư mục output tạo trước khi biên dịch)
~~~

**src/example/spi/GreetingService.java**:

~~~java
package example.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

**src/example/provider/PoliteGreeting.java**:

~~~java
package example.provider;

import example.spi.GreetingService;

public final class PoliteGreeting implements GreetingService {
    public PoliteGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

**src/example/app/Main.java**:

~~~java
package example.app;

import example.spi.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        int found = 0;
        for (GreetingService provider : loader) {
            System.out.println(provider.greet("Java"));
            found++;
        }

        System.out.println("Providers: " + found);
    }
}
~~~

**resources/META-INF/services/example.spi.GreetingService** (tệp văn bản thuần UTF-8):

~~~text
example.provider.PoliteGreeting
~~~

Từ thư mục demo, tạo thư mục out và biên dịch các tệp .java:

~~~bash
mkdir out
javac -encoding UTF-8 --release 17 -d out src/example/spi/GreetingService.java src/example/provider/PoliteGreeting.java src/example/app/Main.java
~~~

Trên Linux/macOS, chạy với dấu **:** ngăn cách hai classpath entries:

~~~bash
java -cp "out:resources" example.app.Main
~~~

Trên Windows, dùng dấu **;** thay thế:

~~~powershell
java -cp "out;resources" example.app.Main
~~~

**Stdout chính xác** (chỉ có một provider được đăng ký):

~~~text
Xin chao, Java!
Providers: 1
~~~

Vì Main chỉ import interface GreetingService, host không cần tham chiếu trực tiếp tới PoliteGreeting. ServiceLoader đọc descriptor từ resources, tải class và khởi tạo provider khi vòng for duyệt tới nó.

Để thấy sự khác biệt giữa **lỗi không tìm thấy provider** và **provider vi phạm điều kiện**, thử bỏ resources khỏi runtime classpath rồi chạy:

~~~bash
java -cp out example.app.Main
~~~

Khi chỉ có các class trong out và không có bản descriptor khác, kết quả là:

~~~text
Providers: 0
~~~

Trường hợp này **không có ServiceConfigurationError** vì không có provider nào được đăng ký mà loader tìm thấy. Ngược lại, khi descriptor có tên một lớp nhưng lớp đó không hợp lệ, lỗi thường xảy ra trong lúc duyệt và nạp provider.

## 8. Kiểm tra chủ động ba điều kiện bằng reflection

Để chẩn đoán trong môi trường ví dụ, có thể kiểm tra các thuộc tính của class trước khi đăng ký. Đây là **công cụ kiểm tra**, không phải cách thay ServiceLoader tạo instance.

Tạo tệp **src/example/app/Inspector.java**:

~~~java
package example.app;

import example.spi.GreetingService;
import java.lang.reflect.Modifier;

public final class Inspector {
    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> candidate = Class.forName("example.provider.PoliteGreeting");

        boolean isPublic = Modifier.isPublic(candidate.getModifiers());
        boolean isConcrete = !candidate.isInterface()
                && !Modifier.isAbstract(candidate.getModifiers());
        boolean isAssignable = GreetingService.class.isAssignableFrom(candidate);

        boolean hasPublicNoArg;
        try {
            candidate.getConstructor();
            hasPublicNoArg = true;
        } catch (NoSuchMethodException ex) {
            hasPublicNoArg = false;
        }

        System.out.println("public: " + isPublic);
        System.out.println("concrete: " + isConcrete);
        System.out.println("assignable: " + isAssignable);
        System.out.println("public no-arg: " + hasPublicNoArg);
    }
}
~~~

Sau khi đã biên dịch ví dụ phần 7, chạy thêm:

~~~bash
javac -encoding UTF-8 --release 17 -cp out -d out src/example/app/Inspector.java
java -cp out example.app.Inspector
~~~

**Stdout chính xác:**

~~~text
public: true
concrete: true
assignable: true
public no-arg: true
~~~

**Giải thích:** Modifier.isPublic kiểm tra access của lớp; !Modifier.isAbstract và !isInterface kiểm tra đây là kiểu có thể tạo instance trực tiếp; isAssignableFrom kiểm tra quan hệ kiểu theo đúng hướng; Class.getConstructor() tìm constructor public không tham số (nếu không có thì ném NoSuchMethodException).

Bốn kết quả true vẫn **không bảo đảm discovery thành công**: Inspector chưa kiểm tra descriptor, classpath entry, sự nhất quán class loader, dependency, lỗi khởi tạo hoặc logic của constructor. Inspector dùng cách tải lớp trong ví dụ đơn giản; trong plugin host thực tế phải kiểm tra đúng class loader được cấu hình cho ServiceLoader.

## 9. Nhận diện lỗi và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Không thấy provider nào, không ném lỗi | Thiếu META-INF/services trong runtime classpath hoặc descriptor không được loader thấy | Kiểm tra đường dẫn resource, nội dung JAR, classpath và context class loader |
| ServiceConfigurationError khi duyệt provider | Descriptor chứa tên sai, class không load được hoặc không đáp ứng contract | Kiểm tra tên binary, classpath và cause của lỗi |
| Lớp package-private | Class provider không public | Đổi thành public top-level class hoặc public static nested class hợp lệ |
| Có method giống SPI nhưng không implements/extends | Không có quan hệ kiểu nominal | Triển khai đúng SPI, thống nhất class loader cho API chung |
| Lớp public nhưng không có public no-arg constructor | Chỉ có constructor nhận tham số hoặc no-arg không public | Khai báo public Provider() {} thực sự phù hợp |
| Constructor tồn tại nhưng ném lỗi | Phụ thuộc cấu hình hoặc initializer thất bại | Kiểm tra cause, dời bước khởi tạo có thể thất bại sang lifecycle có hợp đồng rõ |
| Nhiều bản cùng tên SPI | Hai class loader định nghĩa hai lớp khác nhau | Chia sẻ một bản SPI trong loader phù hợp, tránh đóng gói trùng |
| Provider abstract/non-static inner | Không thể khởi tạo theo lối direct-constructor | Dùng concrete public class với no-arg constructor |
| Chỉ thêm static provider() vào classpath provider | Nhầm cơ chế named module với classpath | Trên classpath vẫn phải có public no-arg constructor và provider subtype |

**Khi phát sinh ServiceConfigurationError**, nhớ rằng ServiceLoader nạp provider **lazily**. Lỗi có thể xảy ra khi gọi Iterator.hasNext(), Iterator.next(), duyệt for-each, hoặc khi xử lý Stream/Provider.get(), chứ không nhất thiết ngay tại ServiceLoader.load(...). Bắt đúng loại lỗi này ở ranh giới *discovery/loading* để ghi nhận provider lỗi và áp dụng chính sách fail-fast hoặc fallback đã định nghĩa:

~~~java
// Đoạn minh họa xử lý discovery, không phải chương trình độc lập.
try {
    for (GreetingService provider : ServiceLoader.load(GreetingService.class)) {
        System.out.println(provider.greet("Java"));
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println("Invalid service provider configuration: "
            + error.getMessage());
}
~~~

Không mặc định dùng catch(Throwable) để nuốt mọi Error. ServiceConfigurationError là một lỗi chuyên biệt của cơ chế nạp dịch vụ; lỗi nền tảng của JVM cần chính sách khác. Nếu một provider lỗi, quyết định bỏ qua hay dừng phải được thực thi cẩn thận: tiếp tục dùng cùng iterator sau lỗi có thể tiếp tục gặp trạng thái lỗi, và không nên giả định có thể bỏ qua provider bằng một lần next().

Khi tạo JAR, có thể kiểm tra mục lưu trữ bằng lệnh **jar --list --file tên-file.jar** và xác nhận tồn tại tài nguyên META-INF/services cùng class được chỉ định. Không dựa vào tên thư mục source hoặc việc IDE compile thành công để kết luận runtime discovery đã đúng.

## 10. Điểm khác biệt quan trọng với Java modules

Chỉ xét **SPI trên classpath** thì ServiceLoader sử dụng **META-INF/services** và đường khởi tạo provider bằng **public no-arg constructor**. Với **named module** được khai báo rõ bằng module-info.java, service được đăng ký bởi **provides ... with ...** và có thêm cơ chế **provider method**:

~~~java
// Trích đoạn module-info.java minh họa, không phải chương trình độc lập.
provides example.spi.GreetingService
    with example.provider.GreetingFactory;
~~~

~~~java
// Trích đoạn kiểu factory trong named module, cần các class/import của module.
public final class GreetingFactory {
    public static GreetingService provider() {
        return new PoliteGreeting();
    }
}
~~~

Khi có public static **provider()** không tham số với kiểu trả về gán được cho service, ServiceLoader của **named module** có thể gọi method đó thay vì constructor; **class factory không bắt buộc implements SPI**, và không buộc có public no-arg constructor theo đường khởi tạo này. Nếu named-module provider **không có provider method**, nó phải có provider constructor public không tham số và phải gán kiểu được cho SPI. Một **automatic module** trên module path vẫn phải dùng provider constructor; nó không hỗ trợ provider method theo cơ chế này.

**Không suy diễn** rằng một JAR đặt trên classpath chỉ cần khai báo static provider() là đủ. Một classpath provider phải là subtype của SPI và có public no-arg constructor để ServiceLoader tạo nó. Đó chính là phạm vi của bài học này.

## 11. Bài kiểm thử tối thiểu cho từng provider

| Bài kiểm thử | Kết quả đúng |
| --- | --- |
| Provider hợp lệ, descriptor đúng, classpath đúng | ServiceLoader tìm và tạo được provider |
| Bỏ descriptor khỏi runtime classpath | Không tìm được provider; có thể được 0 kết quả |
| Đổi provider class thành package-private | Báo cấu hình provider lỗi khi nạp |
| Xóa implements/extends SPI nhưng giữ method cùng tên | Báo lỗi do không gán kiểu được |
| Chỉ giữ constructor có tham số | Báo lỗi do thiếu public no-arg constructor |
| Đổi constructor no-arg thành private | Báo lỗi do constructor không public |
| Constructor ném IllegalStateException | Nạp provider thất bại; kiểm tra cause |
| Nhân đôi API SPI bằng class loader khác | Kiểm tra khả năng gán kiểu của lớp runtime thực tế |
| Chuyển JAR sang named module/automatic module | Xác minh lại quy tắc registration/khởi tạo đúng với loại module |

Trong hệ thống có plugin do bên thứ ba cung cấp, nên tự động kiểm thử từng artifact sau khi đóng gói: xác minh có META-INF/services đúng tên, chạy ServiceLoader bằng class loader mô phỏng môi trường host, thử gọi một hành vi tối thiểu và kiểm tra loại lỗi khi provider thiếu điều kiện.

## 12. Checklist trước khi phát hành classpath SPI

1. SPI là interface/class được host và provider truy cập qua API chung; provider dùng **đúng cùng kiểu SPI tại runtime**.
2. Provider là **public concrete class** (hoặc dạng public static nested thích hợp), thật sự implements/extends SPI.
3. Có **public constructor không tham số** và constructor thực thi an toàn.
4. Đúng tên tài nguyên **META-INF/services/<service binary name>**, mã hóa UTF-8; mỗi dòng chỉ đúng **provider binary name**.
5. Cả descriptor, provider và dependency có mặt trong runtime classpath mà ServiceLoader sử dụng.
6. Đã kiểm thử bằng ServiceLoader thực tế, không chỉ dựa vào javac hay reflection; lỗi được quan sát tại thời điểm duyệt/khởi tạo provider.
7. Đã phân biệt rõ cơ chế classpath với cơ chế provider method trong named module.

**Ghi nhớ:** **public** quyết định khả năng truy cập lớp, **assignability** quyết định có đúng kiểu SPI, và **public no-arg constructor** quyết định ServiceLoader classpath có đường tạo instance hay không. Ba điều kiện phải cùng đúng; descriptor và class loader phải đưa provider đến được nơi cần nạp.

Tham khảo API chuẩn: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
