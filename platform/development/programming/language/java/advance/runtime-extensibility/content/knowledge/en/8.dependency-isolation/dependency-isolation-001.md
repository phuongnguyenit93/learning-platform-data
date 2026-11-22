# Dùng chung loader cho hợp đồng và loader riêng cho từng plugin

Một hệ thống Java hỗ trợ plugin thường phải đáp ứng đồng thời hai yêu cầu: **host và mọi plugin cùng hiểu một hợp đồng mở rộng**, nhưng **mỗi plugin được phép sử dụng phiên bản thư viện nội bộ khác nhau**. Nếu đặt toàn bộ plugin và dependency vào một classpath với một application class loader, các lớp có cùng tên nhị phân có thể xung đột phiên bản. Nếu lại nạp cả interface hợp đồng thành nhiều bản độc lập, provider có thể không còn ép kiểu được về interface mà host sử dụng.

Giải pháp nền tảng là **dùng chung class loader định nghĩa các kiểu hợp đồng**, đồng thời **tạo một class loader riêng cho mỗi plugin** để nạp implementation và dependency của plugin đó. Cấu trúc này tạo ranh giới phụ thuộc rõ ràng, phù hợp để xây dựng runtime extensibility bằng Java 17+.

## 1. Vì sao cần hai phạm vi nạp lớp?

Giả sử host công bố interface GreetingPlugin. Plugin Alpha và Beta đều implements GreetingPlugin, nhưng mỗi plugin đóng gói thư viện có lớp com.example.dep.Utility:

- Alpha cần bản Utility có hành vi trả về chuỗi library-alpha-v1.
- Beta cần bản Utility có hành vi trả về chuỗi library-beta-v2.
- Host chỉ muốn gọi GreetingPlugin.id() và GreetingPlugin.message(); host không cần biết Utility.

Nếu cả hai JAR được dồn vào **cùng một classpath** và nạp bằng **cùng một class loader**, JVM chỉ định nghĩa một lớp với tên nhị phân com.example.dep.Utility trong loader đó. Nó không thể dùng hai định nghĩa khác nhau cùng tên trong một loader chỉ theo ý muốn của từng plugin. Tùy thứ tự classpath và dependency resolution, một bản Utility có thể bị chọn cho cả hai plugin, dẫn tới hành vi sai hoặc lỗi liên kết khi API thư viện không tương thích.

Ngược lại, nếu host nạp GreetingPlugin bằng loader A, còn plugin định nghĩa một bản GreetingPlugin khác bằng loader B, Java coi chúng là **hai kiểu khác nhau**, ngay cả khi cùng tên package, cùng mã nguồn và cùng chữ ký phương thức. Việc ép plugin về kiểu của host có thể thất bại.

Cần giữ **một danh tính chung cho hợp đồng**, nhưng **tách danh tính cho các lớp nội bộ**.

## 2. Danh tính class trong JVM: tên lớp cộng với loader định nghĩa

Một lớp Java trong JVM được xác định bởi cặp:

~~~text
(binary class name, defining class loader)
~~~

Ví dụ:

~~~text
(com.example.spi.GreetingPlugin, SharedLoader)  ← hợp đồng chung

(com.example.dep.Utility, PluginAlphaLoader)     ← Utility của Alpha
(com.example.dep.Utility, PluginBetaLoader)      ← Utility của Beta
~~~

Hai Utility ở trên là hai Class object khác nhau dù cùng tên nhị phân. Chúng có thể có bytecode, static field, singleton và dependency khác nhau. Đây chính là cơ sở của **cô lập phiên bản thư viện theo plugin**.

Ngược lại, host và hai plugin phải cùng tham chiếu đến **chính xác Class object** của GreetingPlugin. Những kiểu DTO, exception, enum, callback và interface nào **đi qua biên giữa host với plugin** cũng cần cùng một định nghĩa lớp hoặc phải chuyển đổi qua một định dạng trung lập.

Có thể hình dung sơ đồ nạp lớp như sau:

~~~text
       Bootstrap / Platform Class Loaders (JDK)
                         |
             Shared/API Parent Loader
             chứa plugin-api và kiểu chung
                  /              \
                 /                \
       PluginAlphaLoader       PluginBetaLoader
       alpha.jar + libs A      beta.jar + libs B
       Utility bản v1          Utility bản v2

Host giao tiếp qua GreetingPlugin thuộc Shared/API Loader.
Plugin Alpha và Beta không nhìn thấy lớp riêng của nhau.
~~~

Trong hệ thống lớn, host có thể được nạp bằng một loader riêng cùng nhìn thấy API parent. Trong ví dụ tối giản bên dưới, **application class loader** đang chứa host và api.jar được dùng làm parent chung cho hai URLClassLoader. Cách này minh họa chính xác việc chia sẻ API và cô lập dependency, nhưng **không giấu các class nội bộ của host khỏi plugin**: lớp nào hiện diện ở parent vẫn có thể được child loader tìm thấy.

## 3. Sơ đồ phụ thuộc và nguyên tắc chia sẻ

| Thành phần | Được nạp ở đâu | Nội dung nên có |
| --- | --- | --- |
| plugin-api.jar | Shared/API parent loader | GreetingPlugin và mọi kiểu hợp đồng mà host/plugin cùng trao đổi |
| host.jar | Application/host loader | Điều phối, kiểm tra version, chọn plugin, quản lý loader và vòng đời |
| alpha.jar | PluginAlphaLoader | AlphaPlugin cùng Utility phiên bản Alpha và dependency riêng |
| beta.jar | PluginBetaLoader | BetaPlugin cùng Utility phiên bản Beta và dependency riêng |
| Các kiểu java.lang, java.util... | Các loader nền tảng của JDK | String, List, ServiceLoader, ClassLoader, URLClassLoader... |

Định hướng phụ thuộc biên dịch nên là:

~~~text
host --------------------> plugin-api
alpha implementation ----> plugin-api
beta implementation -----> plugin-api

host -- runtime discovery --> alpha / beta (qua interface chung)
~~~

**Không** import AlphaPlugin hay BetaPlugin trực tiếp vào host. **Không** để chữ ký GreetingPlugin trả về com.example.dep.Utility hoặc một class chỉ tồn tại trong plugin Alpha. Nếu host cần dữ liệu, định nghĩa DTO chung trong plugin-api hoặc trao đổi bằng kiểu JDK chung, rồi chuyển đổi từ kiểu nội bộ của plugin trước khi trả kết quả.

Khi triển khai, chỉ cung cấp **một bản API hợp đồng** qua parent. Đừng đưa các dependency cần cô lập vào parent, bởi loader mặc định của Java thường ủy quyền lên parent trước; một lớp Utility đã có ở parent sẽ được dùng chung thay vì được nạp riêng trong hai child.

## 4. Parent-first delegation và giới hạn của URLClassLoader

Class loader Java thông thường dùng nguyên tắc **parent-first**: khi được yêu cầu nạp một class, loader hỏi parent trước; nếu parent không tìm thấy, nó mới thử nguồn của chính mình. URLClassLoader mặc định cũng tuân theo hướng ủy quyền này.

Với parent chứa plugin-api nhưng **không chứa** alpha.jar, beta.jar và các thư viện nội bộ:

1. PluginAlphaLoader cần GreetingPlugin: parent trả về đúng lớp API chung.
2. PluginAlphaLoader cần AlphaPlugin: parent không có class này; loader Alpha nạp từ alpha.jar.
3. PluginAlphaLoader cần Utility: parent không có Utility; loader Alpha định nghĩa bản của alpha.jar.
4. PluginBetaLoader cần Utility: parent không có Utility; loader Beta định nghĩa bản của beta.jar.
5. Host nhận AlphaPlugin và BetaPlugin qua interface GreetingPlugin có cùng danh tính kiểu ở parent.

Điểm dễ nhầm: chỉ tạo hai URLClassLoader **chưa đảm bảo cô lập** nếu parent đã mang các JAR plugin hoặc thư viện cần tách. Ví dụ host chạy với alpha.jar và beta.jar trên system classpath thì parent có thể định nghĩa Utility trước, khiến hai child nhận cùng một bản. Vì vậy, **classpath khởi động host chỉ nên mang API và host**, còn các JAR plugin được đưa vào URL của từng child loader.

Một biến thể **child-first** có thể dùng trong plugin engine phức tạp để ưu tiên dependency riêng. Nhưng phải ủy quyền các kiểu hợp đồng, kiểu JDK và package chia sẻ được quy định cho parent; nếu child-first tự định nghĩa lại GreetingPlugin, ranh giới SPI sẽ hỏng. URLClassLoader trong ví dụ này **không phải loader child-first tự viết**.

## 5. Ví dụ Java 17+: hai plugin có lớp thư viện cùng tên nhưng khác hành vi

Ví dụ bên dưới tạo **bốn JAR**: api.jar, host.jar, alpha.jar và beta.jar. Mỗi plugin JAR có riêng một lớp com.example.dep.Utility, khác nội dung. Hai loader con có chung parent chứa GreetingPlugin. Host dùng ServiceLoader để tìm provider trong từng plugin.

Các file cần tạo:

~~~text
src/
  api/com/example/spi/GreetingPlugin.java
  host/com/example/app/Main.java
  alpha/com/example/dep/Utility.java
  alpha/com/example/plugins/AlphaPlugin.java
  beta/com/example/dep/Utility.java
  beta/com/example/plugins/BetaPlugin.java
resources/
  alpha/META-INF/services/com.example.spi.GreetingPlugin
  beta/META-INF/services/com.example.spi.GreetingPlugin
~~~

### 5.1. API hợp đồng chung

**src/api/com/example/spi/GreetingPlugin.java**

~~~java
package com.example.spi;

public interface GreetingPlugin {
    String id();
    String message();
}
~~~

Chữ ký chỉ dùng String, một kiểu JDK mà cả host và plugin cùng biết. API không khai báo phụ thuộc vào Utility, AlphaPlugin hay BetaPlugin. Khi thiết kế hệ thống thật, các kiểu input/output công khai, exception của hợp đồng và API truyền callback cũng nên nằm tại artifact chung.

### 5.2. Plugin Alpha và bản dependency riêng

**src/alpha/com/example/dep/Utility.java**

~~~java
package com.example.dep;

public final class Utility {
    private Utility() {}

    public static String label() {
        return "library-alpha-v1";
    }
}
~~~

**src/alpha/com/example/plugins/AlphaPlugin.java**

~~~java
package com.example.plugins;

import com.example.dep.Utility;
import com.example.spi.GreetingPlugin;

public final class AlphaPlugin implements GreetingPlugin {
    public String id() {
        return "alpha";
    }

    public String message() {
        return Utility.label();
    }
}
~~~

**resources/alpha/META-INF/services/com.example.spi.GreetingPlugin**

~~~text
com.example.plugins.AlphaPlugin
~~~

Tệp META-INF/services thông báo lớp triển khai cho ServiceLoader. Khi dùng classpath, file phải có **tên trùng tên nhị phân của service** và chứa **tên nhị phân của provider**, được lưu dưới dạng văn bản UTF-8.

### 5.3. Plugin Beta và bản dependency khác

**src/beta/com/example/dep/Utility.java**

~~~java
package com.example.dep;

public final class Utility {
    private Utility() {}

    public static String label() {
        return "library-beta-v2";
    }
}
~~~

**src/beta/com/example/plugins/BetaPlugin.java**

~~~java
package com.example.plugins;

import com.example.dep.Utility;
import com.example.spi.GreetingPlugin;

public final class BetaPlugin implements GreetingPlugin {
    public String id() {
        return "beta";
    }

    public String message() {
        return Utility.label();
    }
}
~~~

**resources/beta/META-INF/services/com.example.spi.GreetingPlugin**

~~~text
com.example.plugins.BetaPlugin
~~~

Hai tệp Utility.java có **cùng package, cùng tên class**, nhưng nằm trong hai nguồn biên dịch và hai JAR khác nhau. Chúng cố tình biểu diễn hai phiên bản không thể cùng được định nghĩa trong một loader. Việc dùng hai URLClassLoader tách biệt giải quyết chính sự trùng tên này.

### 5.4. Host tạo hai plugin loader có chung API parent

**src/host/com/example/app/Main.java**

~~~java
package com.example.app;

import com.example.spi.GreetingPlugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class Main {
    private static GreetingPlugin onlyProvider(ClassLoader loader) {
        Iterator<GreetingPlugin> it =
                ServiceLoader.load(GreetingPlugin.class, loader).iterator();

        if (!it.hasNext()) {
            throw new IllegalStateException("No provider");
        }
        GreetingPlugin provider = it.next();
        if (it.hasNext()) {
            throw new IllegalStateException("Multiple providers");
        }
        return provider;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: Main <alpha.jar> <beta.jar>");
        }

        ClassLoader shared = GreetingPlugin.class.getClassLoader();
        URL alphaUrl = Path.of(args[0]).toUri().toURL();
        URL betaUrl = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader alphaLoader =
                    new URLClassLoader(new URL[]{alphaUrl}, shared);
             URLClassLoader betaLoader =
                    new URLClassLoader(new URL[]{betaUrl}, shared)) {

            GreetingPlugin alpha = onlyProvider(alphaLoader);
            GreetingPlugin beta = onlyProvider(betaLoader);

            System.out.println(alpha.id() + ": " + alpha.message());
            System.out.println(beta.id() + ": " + beta.message());

            Class<?> apiFromAlpha = Class.forName(
                    "com.example.spi.GreetingPlugin", false, alphaLoader);
            Class<?> apiFromBeta = Class.forName(
                    "com.example.spi.GreetingPlugin", false, betaLoader);

            System.out.println("API shared: " +
                    (apiFromAlpha == GreetingPlugin.class &&
                     apiFromBeta == GreetingPlugin.class));

            Class<?> depFromAlpha = Class.forName(
                    "com.example.dep.Utility", false, alphaLoader);
            Class<?> depFromBeta = Class.forName(
                    "com.example.dep.Utility", false, betaLoader);

            System.out.println("Dependency isolated: " +
                    (depFromAlpha != depFromBeta));
        }
    }
}
~~~

Những điểm then chốt:

- **GreetingPlugin.class.getClassLoader()** trả loader thực sự đã nạp interface hợp đồng vào host. Ở ví dụ chạy classpath này, đó là application class loader chứa api.jar và host.jar. Cả hai URLClassLoader sử dụng nó làm parent.
- **Mỗi URLClassLoader nhận URL của một plugin JAR riêng.** Không đưa cả alpha.jar và beta.jar vào cùng một child.
- **ServiceLoader.load(GreetingPlugin.class, loader)** chỉ rõ loader dùng để khám phá provider. Overload ServiceLoader.load(GreetingPlugin.class) không truyền loader sử dụng thread context class loader; trong ví dụ này nó thường không nhìn thấy plugin JAR.
- **onlyProvider** xác minh mỗi loader tìm được đúng một provider; nếu không tìm thấy hoặc có nhiều hơn một provider thì ném lỗi rõ ràng. Trong hệ thật có thể có nhiều provider trong một JAR, khi đó dùng registry có id riêng và chính sách chọn.
- **Class.forName(name, false, loader)** yêu cầu class mà loader được cung cấp nhìn thấy; tham số false tránh chủ động khởi tạo class chỉ để kiểm tra danh tính. Phép == so sánh Class object, không so chuỗi tên.
- **try-with-resources** gọi close() cho URLClassLoader sau khi không còn dùng provider ở ví dụ. Việc đóng loader không đồng nghĩa class lập tức bị unload; mục 7 giải thích vòng đời.

### 5.5. Biên dịch và đóng gói JAR

Đứng tại thư mục chứa src và resources, dùng **PowerShell trên Windows**, JDK 17 trở lên. Các file .java và tài nguyên META-INF/services phải được tạo trước bằng đúng đường dẫn ở trên:

~~~powershell
New-Item -ItemType Directory -Force -Path out/api,out/host,out/alpha,out/beta,dist | Out-Null

javac --release 17 -encoding UTF-8 -d out/api src/api/com/example/spi/GreetingPlugin.java
jar --create --file dist/api.jar -C out/api .

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d out/alpha src/alpha/com/example/dep/Utility.java src/alpha/com/example/plugins/AlphaPlugin.java
jar --create --file dist/alpha.jar -C out/alpha . -C resources/alpha META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d out/beta src/beta/com/example/dep/Utility.java src/beta/com/example/plugins/BetaPlugin.java
jar --create --file dist/beta.jar -C out/beta . -C resources/beta META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d out/host src/host/com/example/app/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp "dist/api.jar;dist/host.jar" com.example.app.Main dist/alpha.jar dist/beta.jar
~~~

Trên Linux/macOS, có thể tạo thư mục bằng lệnh mkdir -p out/api out/host out/alpha out/beta dist rồi đổi dấu chấm phẩy **chỉ trong runtime classpath** thành dấu hai chấm. Lệnh javac và jar còn lại giữ nguyên. Ở môi trường sử dụng build tool, tổ chức mỗi API/host/plugin thành module/artifact riêng và bảo đảm package plugin-private không bị đưa vào runtime classpath của host.

**Stdout chính xác khi chạy:**

~~~text
alpha: library-alpha-v1
beta: library-beta-v2
API shared: true
Dependency isolated: true
~~~

Kết quả được kiểm chứng bằng javac --release 17, đóng gói JAR riêng và chạy trên JDK mới hơn. Hai dòng đầu chứng tỏ plugin nhận đúng **phiên bản Utility của chính nó**. Dòng API shared: true chứng tỏ cả hai loader ủy quyền về cùng một Class object của GreetingPlugin. Dòng Dependency isolated: true chứng tỏ hai lớp com.example.dep.Utility không có cùng danh tính Class, dù tên nhị phân của chúng giống nhau.

**Vì sao không có alpha.jar và beta.jar trong tham số -cp của java?** Các JAR này được tải bằng URLClassLoader do Main.java tạo từ hai đối số chương trình. Nếu thêm chúng vào -cp, application class loader có thể nạp class plugin trước child loader, làm vô hiệu phép thử cô lập. Ở đây chỉ api.jar và host.jar hiện diện trên classpath khởi động.

Có thể kiểm tra JAR Alpha:

~~~powershell
jar tf dist/alpha.jar
~~~

Danh sách phải bao gồm các entry sau (cùng với manifest và thư mục):

~~~text
com/example/dep/Utility.class
com/example/plugins/AlphaPlugin.class
META-INF/services/com.example.spi.GreetingPlugin
~~~

Không nên thấy com/example/spi/GreetingPlugin.class được đóng gói trong alpha.jar. Hợp đồng phải được cung cấp chung từ api.jar. Tương tự, beta.jar chứa Utility.class phiên bản riêng, BetaPlugin.class và descriptor tương ứng.

## 6. Khi plugin có nhiều JAR dependency riêng

Thực tế một plugin có thể dùng nhiều thư viện, không phải chỉ một Utility.class đóng gói cùng JAR. Tạo URLClassLoader với danh sách URL bao gồm **plugin.jar và mọi dependency JAR thuộc riêng plugin đó**:

~~~java
URL[] pluginUrls = {
    Path.of("plugins/alpha/alpha.jar").toUri().toURL(),
    Path.of("plugins/alpha/lib/vendor-a.jar").toUri().toURL(),
    Path.of("plugins/alpha/lib/vendor-b.jar").toUri().toURL()
};
ClassLoader apiParent = GreetingPlugin.class.getClassLoader();
URLClassLoader pluginLoader = new URLClassLoader(pluginUrls, apiParent);
~~~

Đây là **đoạn minh họa dùng bên trong method có xử lý Exception** và import java.net.URL, java.net.URLClassLoader, java.nio.file.Path; nó không phải source file độc lập. URLClassLoader nạp class từ các URL JAR mà nó quản lý. Các JAR trên cần được quản lý như một tập triển khai thống nhất, có xác minh phiên bản và không nạp trùng API hợp đồng. Mỗi plugin khác có thể dùng một danh sách JAR riêng, miễn parent không chứa các thư viện cần cô lập.

Với dependency nội bộ **cùng tên binary** mà hai plugin cần **khác phiên bản**, hai loader riêng tạo danh tính Class khác nhau. Nhưng nếu có một thư viện nằm trong parent và child cùng có bản khác, quy tắc parent-first sẽ ưu tiên bản ở parent. Khi phân loại dependency, đừng chỉ nhìn Maven/Gradle dependencies trên giấy: phải kiểm tra **runtime classpath và delegation thực tế**.

Nếu thư viện của plugin cần gọi vào host, hãy định nghĩa một API hẹp trong artifact chung, chẳng hạn PluginContext do host cung cấp, rồi truyền instance qua interface; tránh cho dependency riêng import trực tiếp class nội bộ của host.

## 7. Vòng đời loader, cache và giải phóng tài nguyên

Một URLClassLoader thường là **đơn vị nạp lớp và tài nguyên** sống cùng plugin. Khi plugin dừng hoặc được thay thế, host cần thực hiện các bước phù hợp:

1. Ngừng điều phối request hoặc job mới vào plugin đang dừng.
2. Chờ hoặc hủy các hoạt động đang chạy theo chính sách ứng dụng.
3. Gọi phương thức cleanup/close của plugin nếu hợp đồng công bố; ngắt thread, unregister listener, đóng connection và những tài nguyên plugin đã tạo.
4. Giải phóng registry, ServiceLoader, Class object và instance của plugin mà host còn giữ.
5. Gọi URLClassLoader.close() để đóng tài nguyên JAR/URL do loader quản lý.
6. Loại bỏ những tham chiếu giữ plugin loader nếu muốn nó đủ điều kiện để JVM thu gom.

**close() không buộc JVM unload class ngay lập tức.** Class unloading phụ thuộc vào khả năng thu gom class loader và những object liên quan. Thread còn sống, thread context class loader (TCCL), static registry, ThreadLocal, logger, JDBC driver, callback hoặc cache trong host có thể tiếp tục giữ tham chiếu. Không thể tuyên bố đã hot-unload một plugin chỉ vì phương thức close() kết thúc.

Một ServiceLoader có cache các provider đã khám phá; reload() xóa cache nội bộ và bắt đầu khám phá lại, nhưng **không thay thế class loader** và không tự mở lại URLClassLoader đã đóng. Nếu triển khai hot reload bằng JAR mới, nên tạo loader mới, kiểm tra tương thích, chuyển traffic và giải phóng loader cũ có kiểm soát. Các bước này thuộc **vòng đời plugin** chứ không chỉ thuộc hành vi loadClass.

## 8. Thread Context Class Loader và ServiceLoader

Nhiều framework/JDK API có thể dùng **thread context class loader** để tìm tài nguyên hoặc provider thay vì dùng loader của class gọi. Ví dụ overload ServiceLoader.load(GreetingPlugin.class) sử dụng context class loader của thread hiện tại để khám phá provider.

Trong host quản lý nhiều loader, **ưu tiên truyền loader tường minh** khi API cho phép như ở ví dụ Main.java. Nếu một thư viện trong plugin dựa vào TCCL, host có thể cần đặt context loader quanh lời gọi plugin rồi **khôi phục bằng finally**:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(alphaLoader);
    System.out.println(alpha.message());
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đây là đoạn minh họa đặt **bên trong main khi alphaLoader và alpha đang còn sống**; không thêm vào Main.java của ví dụ nếu muốn giữ nguyên stdout đã kiểm chứng. Đặt TCCL phải có phạm vi ngắn và được khôi phục đầy đủ; nếu thread pool giữ nhầm loader, nó có thể làm rò rỉ loader cũ khi thay plugin. TCCL không thay đổi định nghĩa class đã được parent/child quyết định và không biến hai bản API thành cùng một kiểu.

Cũng cần nhớ rằng ServiceLoader.load(service, pluginLoader) có thể thấy những descriptor dịch vụ trong **parent** nếu parent chứa tài nguyên tương ứng. Ví dụ cố tình để host không có descriptor GreetingPlugin, nên mỗi loader chỉ phát hiện provider từ JAR riêng. Nếu host cũng công bố provider, cần lọc hoặc thiết kế discovery theo nguồn/plugin cụ thể để tránh vô tình chọn provider của parent.

## 9. Những lỗi điển hình và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ClassCastException hoặc ServiceConfigurationError: not a subtype | SPI được định nghĩa lại ở plugin loader hoặc class loader không chia sẻ cùng kiểu | Đưa SPI, DTO và exception hợp đồng lên API parent; kiểm tra Class object |
| NoSuchMethodError/NoClassDefFoundError ở plugin | Dependency thực sự được nạp từ parent hoặc thiếu JAR nội bộ | Kiểm tra runtime URLs, classpath host và version dependency |
| Hai plugin cùng dùng một hành vi Utility | Utility đã có trong parent hoặc plugin dùng chung một child loader | Loại dependency riêng khỏi parent, tạo một loader cho mỗi plugin |
| Host không tìm thấy provider | Sai META-INF/services, thiếu JAR hoặc gọi overload ServiceLoader không nhìn thấy child | Kiểm tra descriptor và truyền đúng class loader cho ServiceLoader.load |
| Plugin A thấy class của B ngoài ý muốn | Cả hai JAR nằm trong cùng loader hoặc có một loader chung chứa implementation | Tách các URL và tránh share implementation qua parent |
| Metaspace tăng sau nhiều lần reload | Thread, cache, TCCL, class/instance hoặc resource còn giữ loader cũ | Thực hiện cleanup và bỏ tham chiếu theo vòng đời |
| Chỉ đóng URLClassLoader mà vẫn còn task chạy | Loader được đóng khi provider chưa ngừng sử dụng tài nguyên | Ngừng nhận việc, drain/cancel task, cleanup plugin rồi mới close |

**Bài toán tinh vi: classpath chứa hai bản API.** Với URLClassLoader parent-first như ví dụ, một bản API tình cờ được đóng vào plugin.jar thường vẫn nhường quyền định nghĩa cho API ở parent; nhưng nếu sử dụng child-first, module layer tùy chỉnh hay loader không ủy quyền đúng, plugin có thể tự định nghĩa bản thứ hai. Vì vậy vẫn nên **không đóng gói plugin-api trong plugin JAR** và bảo vệ namespace hợp đồng được ủy quyền lên parent.

**Bài toán thư viện dùng chung thực sự:** Một số thư viện là phần của hợp đồng và phải dùng chung (ví dụ API DTO có một kiểu từ thư viện thứ ba trong chữ ký). Khi đó chúng cần có phiên bản tương thích được thống nhất ở API parent. Không được tự động cô lập mọi thư viện mà quên rằng kiểu xuất hiện ở chữ ký phải giữ cùng danh tính bên host và plugin.

**Giới hạn bảo mật:** URLClassLoader tách **namespace/dependency**, không phải sandbox bảo mật. Plugin Java chạy cùng JVM có thể thực thi mã, mở file/network, tạo thread và tác động đến trạng thái tiến trình theo quyền môi trường. Đối với plugin không đáng tin, cần ranh giới tiến trình/OS/container và giao thức trao đổi phù hợp, thay vì nghĩ rằng child class loader tự ngăn được hành vi nguy hiểm.

## 10. Những kiểm tra bắt buộc trước khi đưa vào plugin runtime

- **Danh tính hợp đồng:** GreetingPlugin.class == Class.forName("com.example.spi.GreetingPlugin", false, pluginLoader) phải true cho từng plugin. Làm tương tự cho những DTO và callback đi qua biên.
- **Danh tính dependency:** Khi cố ý dùng hai version cùng binary name, đối chiếu Class object được nạp từ AlphaLoader và BetaLoader phải khác nhau.
- **Phân phối JAR:** Host chỉ biên dịch/phụ thuộc vào API; implementation JAR không được xuất hiện trên classpath khởi động nếu cần loader riêng nạp nó.
- **Metadata ServiceLoader:** Mỗi plugin JAR có đúng resource META-INF/services/<service binary name> và lớp provider tương thích.
- **Không rò kiểu nội bộ:** Method công khai trong SPI không nhận/trả về class chỉ có trong plugin-private loader. Chuyển đổi ra kiểu chung trước khi qua biên.
- **Trùng dependency:** Soát các class cùng tên giữa plugin và parent. Parent-first ưu tiên parent; hai child chỉ cô lập lớp nếu parent không định nghĩa lớp đó.
- **Vòng đời:** Test dừng/reload, đóng resource, giải phóng instance, thread và TCCL; xác định policy khi provider load lỗi.
- **Tương thích API:** Test plugin được build với những phiên bản plugin-api mà host cam kết hỗ trợ. Cô lập loader không tự xử lý thay đổi chữ ký, constructor, DTO hay ngữ nghĩa hợp đồng.

Để tự kiểm chứng nguyên tắc, hãy chạy đúng ví dụ mục 5, quan sát **API shared: true** và **Dependency isolated: true**, sau đó thử đưa alpha.jar vào runtime classpath của host hoặc dùng một URLClassLoader chứa cả hai JAR. Phân tích vì sao cùng một loader không thể định nghĩa song song hai bản Utility có cùng tên, và tại sao việc đưa dependency vào parent làm mất lợi ích parent-first isolation.

**Tài liệu tham khảo:** Java SE 17 API Specification cho java.lang.ClassLoader, java.net.URLClassLoader và java.util.ServiceLoader:
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html

Tư duy thiết kế cần giữ vững là **share what crosses the boundary; isolate what stays inside a plugin**: hợp đồng và kiểu trao đổi cần một danh tính JVM chung; các lớp implementation và dependency riêng cần một namespace độc lập. Class loader là cơ chế thực thi ranh giới đó, còn quản lý tương thích, discovery, vòng đời và bảo mật là trách nhiệm của plugin host.
