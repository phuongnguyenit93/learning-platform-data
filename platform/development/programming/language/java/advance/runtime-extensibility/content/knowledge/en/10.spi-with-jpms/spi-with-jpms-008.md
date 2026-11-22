# Những khai báo cần đổi khi đưa cùng provider từ classpath sang module path

Java cho phép mở rộng ứng dụng bằng **Service Provider Interface (SPI)** và **ServiceLoader**. Trên classpath, một provider thường được đăng ký bằng tệp META-INF/services chứa tên lớp triển khai. Khi chuyển sang **Java Platform Module System (JPMS)** trên module path, cơ chế khám phá provider của một **explicit named module** chuyển sang khai báo trong **module-info.java**. Cùng một lớp Java có thể tiếp tục triển khai service cũ, nhưng cách khai báo **service được dùng ở đâu**, **service do module nào cung cấp** và **module nào đọc được kiểu service** phải nhất quán.

Bài này trả lời trực tiếp câu hỏi: **Những khai báo nào phải thêm, sửa hoặc giữ lại khi một provider từng chạy trên classpath được đóng gói và chạy dưới module path?** Nội dung dùng Java 17+, phân biệt rõ explicit module với automatic module, đưa ví dụ cùng một provider JAR chạy ở cả hai chế độ và trình bày cách xử lý lỗi thường gặp khi di trú.

## 1. So sánh nhanh các khai báo

Giả sử service là **demo.greeting.api.Greeting**, lớp triển khai là **demo.greeting.provider.VietnameseGreeting**. Ta có ba vai trò:

- **API**: định nghĩa Greeting.
- **Consumer/host**: gọi ServiceLoader.load(Greeting.class).
- **Provider/plugin**: định nghĩa VietnameseGreeting.

| Vấn đề | Khi chạy trên classpath (unnamed module) | Khi chạy thành explicit named modules |
| --- | --- | --- |
| Provider được đăng ký ở đâu? | Tệp META-INF/services/demo.greeting.api.Greeting, có dòng tên provider | **provides demo.greeting.api.Greeting with demo.greeting.provider.VietnameseGreeting;** trong module-info.java của provider |
| Consumer thông báo muốn tìm service ở đâu? | Không cần module-info.java | **uses demo.greeting.api.Greeting;** trong module-info.java của module thực hiện lời gọi ServiceLoader |
| Consumer phụ thuộc API ra sao? | API có trên classpath | **requires demo.greeting.api;** trong descriptor của consumer nếu API nằm ở module khác |
| Provider phụ thuộc API ra sao? | API có trên classpath | **requires demo.greeting.api;** trong descriptor của provider nếu API nằm ở module khác |
| Module chứa interface công khai API ra sao? | Interface public và nhìn thấy qua classpath | **exports demo.greeting.api;** trong descriptor của module API để module khác dùng được |
| Có phải exports package implementation? | Không áp dụng ranh giới export JPMS | **Không cần exports demo.greeting.provider;** cho riêng cơ chế ServiceLoader |
| Có phải opens package implementation? | Không cần chỉ để ServiceLoader gọi constructor | **Không cần opens** cho cơ chế cung cấp service chuẩn |
| Consumer có phải requires module provider? | Không phụ thuộc trực tiếp implementation | **Không nên requires provider** chỉ để khám phá service; giữ sự phụ thuộc vào API |
| Tệp META-INF/services cũ còn bắt buộc? | **Có**, nếu provider chỉ được đăng ký theo cơ chế classpath | **Không thay thế được provides** khi provider là explicit named module; có thể giữ để hỗ trợ chạy lại trên classpath |

Bảng áp dụng cho **explicit named module có module-info.class**. Nếu chỉ đưa JAR thường, **chưa có module-info.class**, lên module path, JAR thường trở thành **automatic module**: các khai báo META-INF/services vẫn có thể được chuyển thành metadata cung cấp service của automatic module. Vì vậy, “đưa JAR lên module path” và “modularize thành explicit named module” là hai bước khác nhau.

## 2. Trước khi di trú: đăng ký SPI trên classpath

Ứng dụng cũ thường có ba nhóm class:

~~~text
api.jar
└── demo/greeting/api/Greeting.class

provider.jar
├── demo/greeting/provider/VietnameseGreeting.class
└── META-INF/services/demo.greeting.api.Greeting

app.jar
└── demo/greeting/app/Main.class
~~~

Tệp **META-INF/services/demo.greeting.api.Greeting** có nội dung UTF-8:

~~~text
demo.greeting.provider.VietnameseGreeting
~~~

Tên **tệp** là tên nhị phân đầy đủ của **service**, còn mỗi dòng **nội dung** là tên nhị phân của **provider**. ServiceLoader sử dụng class loader để tìm tệp cấu hình này, nạp tên lớp được ghi trong đó rồi tạo provider khi duyệt kết quả.

Trong phiên bản classpath, các JAR thường nằm trên đường chạy:

~~~bash
java -cp "api.jar:provider.jar:app.jar" demo.greeting.app.Main
~~~

Với hệ điều hành Windows, dấu phân cách các phần tử classpath trong lệnh java là dấu chấm phẩy (;), còn trên Linux/macOS là dấu hai chấm (:).

**Điểm di trú cần nhớ:** Nếu một JAR đã trở thành **explicit named module**, Java không lấy danh sách provider của module ấy chỉ từ META-INF/services. Provider của module phải được khai báo bằng **provides ... with ...**. Vì thế chỉ di chuyển nguyên provider JAR từ classpath sang module path rồi trông đợi descriptor tệp cũ hoạt động như trước có thể khiến provider biến mất khỏi kết quả ServiceLoader.

## 3. Những thay đổi trong module-info.java của từng vai trò

### 3.1. Module API phải exports gói service

Giả sử interface Greeting nằm trong module có tên **demo.greeting.api**. File **module-info.java** của API là:

~~~java
module demo.greeting.api {
    exports demo.greeting.api;
}
~~~

Khai báo exports cho phép mã ở các module khác truy cập kiểu public Greeting ở thời điểm biên dịch và khi chạy. Nếu API nằm trong module riêng mà không exports package, consumer/provider ở module khác không thể tham chiếu interface theo cách thông thường.

Đây là export của **hợp đồng API**, không phải export tất cả mã nội bộ của ứng dụng. Nếu service interface có sẵn trong một module API công khai khác thì dùng đúng tên module hiện hữu, không tự dựng thêm module trùng tên.

### 3.2. Consumer cần requires API và uses service

**module-info.java** của module ứng dụng **demo.greeting.app**:

~~~java
module demo.greeting.app {
    requires demo.greeting.api;
    uses demo.greeting.api.Greeting;
}
~~~

Hai dòng này có ý nghĩa khác nhau:

- **requires demo.greeting.api**: cho phép module app đọc module chứa kiểu Greeting và biên dịch dòng import/type reference. requires tạo cạnh phụ thuộc giữa các **module**, không khai báo việc dùng service để tìm provider.
- **uses demo.greeting.api.Greeting**: thông báo module app có thể dùng ServiceLoader để khám phá nhà cung cấp cho **kiểu service cụ thể**. Với caller nằm trong explicit named module, thiếu uses là lỗi hợp đồng và lời gọi ServiceLoader.load có thể ném **ServiceConfigurationError**.

Cách viết sai phổ biến:

~~~java
// Thiếu uses: đây là descriptor CHƯA ĐỦ cho code gọi ServiceLoader.
module demo.greeting.app {
    requires demo.greeting.api;
}
~~~

Dù API đã nhìn thấy, consumer vẫn chưa tuyên bố nhu cầu dịch vụ. Một khai báo requires **không thay thế uses**.

Nếu app trực tiếp khai báo:

~~~java
requires demo.greeting.provider;
~~~

chỉ để ServiceLoader tìm được một implementation thì đã tạo phụ thuộc cứng vào provider, làm mất mục tiêu thay thế plugin mà không sửa consumer. Thông thường module app chỉ **requires API** và **uses service**, không requires module provider. Trường hợp code thực sự tham chiếu một kiểu exported của provider là bài toán phụ thuộc trực tiếp khác, cần xem xét riêng.

### 3.3. Provider cần requires API và provides service with implementation

**module-info.java** của **demo.greeting.provider**:

~~~java
module demo.greeting.provider {
    requires demo.greeting.api;
    provides demo.greeting.api.Greeting
        with demo.greeting.provider.VietnameseGreeting;
}
~~~

Trong đó:

- **requires demo.greeting.api**: provider đọc và triển khai interface Greeting do module API export.
- **provides demo.greeting.api.Greeting with demo.greeting.provider.VietnameseGreeting**: khai báo module này là nhà cung cấp service Greeting, lớp provider cụ thể được chứa trong **chính module ấy**.
- Không cần **exports demo.greeting.provider** chỉ để ServiceLoader khởi tạo provider. JPMS cho phép ServiceLoader truy cập provider đúng hợp đồng service dù package implementation không được export trực tiếp cho các module ứng dụng.

Một provides không được dùng để khai báo lớp triển khai thực sự nằm trong module khác. Nếu một module có nhiều provider cho cùng service, có thể liệt kê nhiều tên sau with, phân cách bởi dấu phẩy, hoặc dùng thiết kế module/provider phù hợp.

Khai báo sau **không phải giải pháp đúng** khi chuyển từ tệp classpath sang explicit module:

~~~java
// SAI: exports implementation không thay thế provides.
module demo.greeting.provider {
    requires demo.greeting.api;
    exports demo.greeting.provider;
}
~~~

Export làm package có thể truy cập trực tiếp; nó không đăng ký provider với ServiceLoader. Ngược lại, provides đăng ký dịch vụ mà không cần phơi bày mọi implementation như API công khai.

### 3.4. Chuyển dòng đăng ký cũ thành gì?

Mapping trực tiếp:

~~~text
Classpath file:
  META-INF/services/demo.greeting.api.Greeting

Classpath file content:
  demo.greeting.provider.VietnameseGreeting

Explicit provider module:
  provides demo.greeting.api.Greeting
      with demo.greeting.provider.VietnameseGreeting;
~~~

Đây là **thay đổi khai báo**, không yêu cầu đổi tên interface, thuật toán xử lý, method business hay lớp triển khai nếu provider vẫn đáp ứng hợp đồng trên module path. Khi tên package/service/provider đã đổi trong quá trình refactor, phải cập nhật đồng thời cả descriptor và tệp đăng ký dual-mode nếu còn sử dụng.

## 4. Ví dụ Java 17 hoàn chỉnh: cùng provider chạy ở cả hai chế độ

Ví dụ dùng đúng **một implementation** VietnameseGreeting. Ta tạo ba modular JAR: API, provider và ứng dụng, đồng thời giữ tệp META-INF/services trong provider JAR để có thể chạy cả trên **classpath** lẫn **module path**.

### 4.1. Cấu trúc dự án

~~~text
greeting-spi/
├── src/
│   ├── demo.greeting.api/
│   │   ├── module-info.java
│   │   └── demo/greeting/api/Greeting.java
│   ├── demo.greeting.provider/
│   │   ├── module-info.java
│   │   ├── demo/greeting/provider/VietnameseGreeting.java
│   │   └── META-INF/services/demo.greeting.api.Greeting
│   └── demo.greeting.app/
│       ├── module-info.java
│       └── demo/greeting/app/Main.java
├── mods/           (được tạo khi biên dịch)
└── mlib/           (chứa các JAR sau khi đóng gói)
~~~

Các thư mục **src/<module-name>** là cách tổ chức phù hợp với tham số javac --module-source-path. Trong dự án build bằng Maven/Gradle, module-info.java và các resource thường nằm trong thư mục nguồn theo cấu trúc build tool, nhưng **đầu ra JAR** phải có module-info.class và các resource đặt đúng vị trí bên trong.

### 4.2. API

**src/demo.greeting.api/module-info.java**

~~~java
module demo.greeting.api {
    exports demo.greeting.api;
}
~~~

**src/demo.greeting.api/demo/greeting/api/Greeting.java**

~~~java
package demo.greeting.api;

public interface Greeting {
    String sayHello(String name);
}
~~~

### 4.3. Provider

**src/demo.greeting.provider/module-info.java**

~~~java
module demo.greeting.provider {
    requires demo.greeting.api;
    provides demo.greeting.api.Greeting
        with demo.greeting.provider.VietnameseGreeting;
}
~~~

**src/demo.greeting.provider/demo/greeting/provider/VietnameseGreeting.java**

~~~java
package demo.greeting.provider;

import demo.greeting.api.Greeting;

public final class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {
    }

    @Override
    public String sayHello(String name) {
        return "Xin chào, " + name;
    }
}
~~~

Provider ở ví dụ dùng **public no-args constructor** và public concrete class triển khai interface service. Đường khởi tạo này hoạt động được cả trên classpath, automatic module và explicit module.

**src/demo.greeting.provider/META-INF/services/demo.greeting.api.Greeting**:

~~~text
demo.greeting.provider.VietnameseGreeting
~~~

Tệp vừa nêu được giữ lại để hỗ trợ **classpath**. Với explicit named module, ServiceLoader dùng provides trong module-info.class; một mục trong tệp META-INF/services trỏ tới provider đã được triển khai trong named module sẽ không được tính lặp lại như một provider trong unnamed module.

### 4.4. Consumer

**src/demo.greeting.app/module-info.java**

~~~java
module demo.greeting.app {
    requires demo.greeting.api;
    uses demo.greeting.api.Greeting;
}
~~~

**src/demo.greeting.app/demo/greeting/app/Main.java**

~~~java
package demo.greeting.app;

import demo.greeting.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        int count = 0;
        for (Greeting provider : ServiceLoader.load(Greeting.class)) {
            System.out.println(provider.sayHello("Lan"));
            count++;
        }
        System.out.println("providers=" + count);
    }
}
~~~

Chương trình không tham chiếu VietnameseGreeting. Code ở cả hai chế độ không đổi; khác biệt nằm ở **descriptor, resource và cách khởi chạy**.

### 4.5. Biên dịch và đóng gói ba modular JAR

Các lệnh sau chạy từ thư mục greeting-spi trong Bash trên Linux/macOS/Git Bash, với **JDK 17+** và đầy đủ file vừa tạo:

~~~bash
mkdir -p mods mlib

javac -encoding UTF-8 --module-source-path src -d mods \
  $(find src -name '*.java')

mkdir -p mods/demo.greeting.provider/META-INF/services
cp src/demo.greeting.provider/META-INF/services/demo.greeting.api.Greeting \
   mods/demo.greeting.provider/META-INF/services/

jar --create --file mlib/demo.greeting.api.jar \
  -C mods/demo.greeting.api .
jar --create --file mlib/demo.greeting.provider.jar \
  -C mods/demo.greeting.provider .
jar --create --file mlib/demo.greeting.app.jar \
  -C mods/demo.greeting.app .
~~~

Phần javac biên dịch cả ba module theo **module-source-path** và xử lý phụ thuộc module từ module-info.java. Tệp descriptor service là **resource**, không phải file Java; vì thế lệnh cp bảo đảm tệp này thực sự được đưa vào provider JAR. Có thể cấu hình build tool tự copy resource thay bước thủ công.

Kiểm tra provider JAR:

~~~bash
jar --list --file mlib/demo.greeting.provider.jar
jar --describe-module --file mlib/demo.greeting.provider.jar
~~~

Các entry quan trọng **phải xuất hiện** trong danh sách JAR (đây không phải toàn bộ stdout của jar --list):

~~~text
module-info.class
demo/greeting/provider/VietnameseGreeting.class
META-INF/services/demo.greeting.api.Greeting
~~~

Lệnh jar --describe-module cho biết provider JAR là explicit module, tên **demo.greeting.provider**, có requires đối với API và provides Greeting với VietnameseGreeting. Nếu không có module-info.class, đó không còn là explicit module như ví dụ.

### 4.6. Chạy trên classpath

Dùng đúng ba JAR vừa đóng gói và đặt lên classpath:

~~~bash
java -cp "mlib/demo.greeting.api.jar:mlib/demo.greeting.provider.jar:mlib/demo.greeting.app.jar" \
  demo.greeting.app.Main
~~~

Kết quả:

~~~text
Xin chào, Lan
providers=1
~~~

Khi modular JAR được đặt trên **classpath**, module-info.class của chúng không được dùng để xây module descriptor; các lớp trở thành một phần của **unnamed module**. Vì thế ServiceLoader khám phá provider dựa vào tệp META-INF/services trong JAR. Nếu bỏ tệp đó nhưng vẫn giữ provides trong module-info.class, phiên chạy classpath này sẽ không tự phát hiện provider.

### 4.7. Chạy trên module path

Dùng cùng ba JAR và lệnh khởi chạy module:

~~~bash
java --module-path mlib \
  --add-modules demo.greeting.provider \
  --module demo.greeting.app/demo.greeting.app.Main
~~~

Kết quả:

~~~text
Xin chào, Lan
providers=1
~~~

Ở đây:

- **--module-path mlib** đặt vị trí các module mà hệ thống có thể quan sát.
- **--module demo.greeting.app/demo.greeting.app.Main** chọn main module và main class.
- **--add-modules demo.greeting.provider** chủ động thêm provider vào tập module gốc cần resolve. Đây là lựa chọn tường minh giúp ví dụ chắc chắn có provider đã được resolve; trong những lần khởi chạy khác, cơ chế **service binding** của quá trình module resolution cũng có thể đưa provider vào graph.
- App có **uses Greeting**, provider có **provides Greeting with VietnameseGreeting**, cả hai đọc module API tương ứng.
- Package demo.greeting.provider vẫn có thể không exports; ServiceLoader vẫn tạo instance provider theo hợp đồng.

Kết quả giống classpath nhưng cơ chế đăng ký khác. Việc thêm provider module vào module graph mới chỉ khiến module có mặt; nếu bỏ **provides** khỏi explicit provider descriptor, tệp META-INF/services không tự trở thành khai báo cung cấp service thay thế.

**Trên Windows**, phần --module-path chỉ nhận một thư mục mlib trong ví dụ nên lệnh không cần thay dấu phân cách. Nếu có nhiều thư mục trong --module-path, Windows dùng dấu chấm phẩy (;). Các lệnh mkdir/cp/find ở bước biên dịch là Bash; với PowerShell cần thay bằng lệnh tạo thư mục, copy resource và danh sách file Java tương ứng.

## 5. Không nhầm bốn chế độ triển khai

Có bốn tình huống cùng xuất hiện trong quá trình di trú. Kết luận về khai báo phụ thuộc **JAR thực sự được chạy với chế độ nào**:

| Loại provider JAR | Đặt ở đâu? | Cách ServiceLoader biết provider |
| --- | --- | --- |
| JAR thường không có module-info.class | Classpath | Đọc META-INF/services |
| JAR thường không có module-info.class (**automatic module**) | Module path và đã được resolve | Metadata service có thể được suy ra từ META-INF/services |
| **Explicit modular JAR** có module-info.class | Module path và đã được resolve | **provides ... with ...** trong module descriptor |
| **Explicit modular JAR** có module-info.class | Classpath | module-info.class bị bỏ qua; cần META-INF/services cho SPI trên classpath |

Đặc biệt:

- **Automatic module** có tên module (đặt bằng Automatic-Module-Name trong manifest hoặc suy ra từ tên JAR), nhưng **chưa có descriptor module-info.java đầy đủ**. Dữ liệu service hiện diện trong META-INF/services tiếp tục có vai trò trong metadata được hệ thống tạo cho automatic module. Automatic module không có mức đóng gói như explicit module: các package được export/open rộng.
- **Explicit module** có descriptor đã biên dịch; với provider của module này, phải dùng **provides**. Không suy luận “đã có META-INF/services thì module path chắc chắn thấy provider” khi module là explicit.
- **Dual-mode modular JAR** nên chứa **cả provides** và tệp META-INF/services nếu một artifact phải phục vụ đồng thời Java 17 module path và ứng dụng cũ trên classpath.
- **Unnamed module** là môi trường của classpath. Mã bên trong vẫn có thể gọi ServiceLoader nhưng không có module-info.java riêng với uses/provides để JVM đọc.

Một file manifest chỉ có Automatic-Module-Name **không thay thế module-info.java** và không chuyển thư viện thành explicit named module.

## 6. Module path nhìn thấy JAR chưa chắc module đã được resolve

Việc tìm được file provider trong thư mục mlib không có nghĩa provider đã tham gia **module graph** của tiến trình. Cần phân biệt:

~~~text
Có JAR trên đĩa
       |
       v
Có thể quan sát qua --module-path
       |
       v
Module được resolve vào graph/layer hiện dùng
       |
       v
Provider được module descriptor khai báo
       |
       v
ServiceLoader của caller có thể khám phá provider
       |
       v
Khởi tạo provider và sử dụng theo contract
~~~

Ở mức module graph:

- **requires** tạo quan hệ đọc module được nêu tên; requires API của cả consumer và provider là cấu trúc phụ thuộc compile-time/runtime bình thường.
- **uses** biểu diễn nhu cầu sử dụng service trong module consumer.
- **provides** biểu diễn nguồn cung cấp service trong module provider.
- **Service binding** trong quá trình resolution có thể đưa module provider vào graph khi có module đã resolve tuyên bố dùng service tương ứng. Với một bản phân phối riêng, phải kiểm tra quy trình launcher, plugin loader hoặc module layer thực tế có bật bước này hay không.
- **--add-modules demo.greeting.provider** là cách minh thị yêu cầu resolve provider trong ví dụ thực hành; không phải khuyến nghị thêm từng provider bằng tay vào mọi hệ plugin.
- Khi tạo runtime image với **jlink**, lựa chọn **--bind-services** có thể cần thiết nếu muốn đưa service providers vào image qua cơ chế binding.
- Với hệ plugin **ModuleLayer** động, lớp cấu hình mới có thể được tạo qua quá trình resolve hoặc resolveAndBind; danh sách provider thực tế còn phụ thuộc module layer đang dùng.

Nếu ServiceLoader trả 0 provider trên module path, kiểm tra module resolution/graph trước khi khẳng định provides viết sai. Một provider khai báo đúng nhưng **không được resolve** vẫn không có mặt để ServiceLoader khám phá trong layer tương ứng.

## 7. Quy tắc về constructors, provider() và encapsulation

### 7.1. Provider qua constructor

Đường đi đơn giản, phù hợp di trú từ classpath:

~~~java
package demo.greeting.provider;

import demo.greeting.api.Greeting;

public final class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {
    }

    @Override
    public String sayHello(String name) {
        return "Xin chào, " + name;
    }
}
~~~

Class provider **public**, là lớp concrete, triển khai service và có **public no-args constructor**. Đường đi này phù hợp để giữ một lớp implementation hoạt động cho cả classpath và module path.

Nếu lớp chỉ có constructor nhận tham số, ServiceLoader không tự biết cách dependency injection những tham số ấy qua cơ chế constructor provider thông thường. Khi di trú, cần thiết kế cách tạo provider phù hợp thay vì nghĩ requires hoặc opens có thể tự tiêm dependency.

### 7.2. Provider method là khả năng riêng của explicit named module

Trong explicit module, Java 17 hỗ trợ khai báo class provider có **public static provider()** không tham số, trả về một kiểu có thể gán cho service. Khi dùng cách đó, bản thân class được liệt kê trong provides không nhất thiết phải implements service.

Ví dụ mô tả API bên trong một explicit module (mã minh họa phương án thay thế, không dùng trong chương trình chạy độc lập ở phần 4):

~~~java
package demo.greeting.provider;

import demo.greeting.api.Greeting;

public final class GreetingFactory {
    private GreetingFactory() {
    }

    public static Greeting provider() {
        return name -> "Xin chào, " + name;
    }
}
~~~

Descriptor tương ứng:

~~~java
module demo.greeting.provider {
    requires demo.greeting.api;
    provides demo.greeting.api.Greeting
        with demo.greeting.provider.GreetingFactory;
}
~~~

ServiceLoader sẽ dùng provider() để lấy instance Greeting. Tuy nhiên:

- Trên **classpath**, cơ chế từ META-INF/services không hỗ trợ hình thức provider method như cơ chế module; class được liệt kê trong resource vẫn phải là implementation phù hợp và có public no-args constructor.
- **Automatic module** trên module path cũng không hỗ trợ provider method theo kiểu của explicit module; provider constructor là bắt buộc.
- Nếu mục tiêu là cùng một provider chạy ở cả classpath và module path, tiếp tục dùng **public concrete implementation có no-args constructor** thường thuận tiện nhất.

Không chuyển cách tạo instance chỉ vì thay vị trí JAR khi điều đó không cần cho nghiệp vụ.

### 7.3. Không cần exports/opens implementation cho ServiceLoader

Khai báo provides cho phép runtime làm việc qua cơ chế cung cấp dịch vụ chính thức. Một provider ở package chưa export vẫn có thể được khám phá và khởi tạo, miễn đáp ứng điều kiện hợp đồng.

**exports** cho phép các module khác truy cập kiểu public trong package bằng quan hệ đọc module phù hợp; **opens** liên quan tới truy cập phản chiếu sâu của framework ở runtime. Không dùng exports toàn implementation hoặc opens toàn module chỉ như “mẹo” chữa ServiceLoader không tìm thấy provider. Trước hết kiểm tra provides, uses, requires và resolution.

Nếu ứng dụng bên ngoài tự reflection vào trường/constructor không công khai của provider, đó là yêu cầu độc lập với ServiceLoader, cần đánh giá chính sách opens cụ thể thay vì mở rộng bừa bãi.

## 8. Cùng provider trong host/plugin thực tế

Khi triển khai plugin được nạp tại runtime, host có thể cần hai ranh giới khác biệt:

1. **Ranh giới dịch vụ**: host biết kiểu Greeting từ API và gọi ServiceLoader.
2. **Ranh giới module/class loader**: host xác định provider JAR được resolve vào ModuleLayer nào, ở class loader nào, và service type được hiểu là cùng Class identity hay không.

Với plugin trên classpath truyền thống, host có thể tạo URLClassLoader và dùng:

~~~java
// MÃ MINH HỌA ĐOẠN GỌI KHI BIẾT pluginLoader; không chạy độc lập.
ServiceLoader<Greeting> providers =
        ServiceLoader.load(Greeting.class, pluginLoader);
~~~

Với provider ở **module layer mới**, có thể dùng:

~~~java
// MÃ MINH HỌA ĐOẠN GỌI KHI BIẾT layer và Greeting; không chạy độc lập.
ServiceLoader<Greeting> providers =
        ServiceLoader.load(layer, Greeting.class);
~~~

Phương thức load(layer, service) tìm trong **layer được chỉ định và các ancestor layer**. Đây không phải phép “quét toàn bộ module path JVM” tùy ý. Mã tạo layer, resolver, class loader và quyền đọc module phải do host quản lý nhất quán; module nằm trên ổ đĩa nhưng chưa nằm trong layer liên quan sẽ không tự xuất hiện.

Trong cả hai trường hợp, **module của caller dùng ServiceLoader phải khai báo uses** nếu caller là explicit named module. Việc đưa Greeting.class làm tham số không xóa trách nhiệm khai báo uses của module chứa điểm gọi.

### Không tạo hai bản sao API

Một lỗi migration khác xảy ra khi provider ở class loader/module layer riêng nạp một bản sao service API, thay vì dùng chung interface của host. Khi đó cùng tên demo.greeting.api.Greeting nhưng hai Class khác nhau, provider có thể không tương thích với service mà host hỏi.

Thiết kế thường là để API chung nằm trong module/loader cha đã resolve và để provider đọc đúng module ấy; tránh mang bản sao API trong một plugin layer khác không có quan hệ chia sẻ. **JPMS module name giống nhau không tự bảo đảm hai ModuleLayer hoặc loader có cùng Class identity.** Đây là vấn đề bên cạnh requires/uses/provides, cần kiểm tra khi plugin được nạp động.

## 9. Phân tích những tình huống migration thường gặp

### Tình huống A: đổi toàn bộ sang explicit named modules

- API có exports service package.
- Consumer có requires API + uses service.
- Provider có requires API + provides service with class.
- Provider được resolve vào graph/layer tương ứng.
- Implementation class vẫn đáp ứng hợp đồng constructor/provider method.
- Để chạy thuần module path, tệp META-INF/services không còn là nguồn đăng ký bắt buộc.

Đây là con đường có encapsulation rõ nhất trong JPMS.

### Tình huống B: vẫn cần hỗ trợ ứng dụng legacy trên classpath

Giữ **cả**:

~~~text
META-INF/services/demo.greeting.api.Greeting
~~~

và trong provider module-info.java:

~~~java
provides demo.greeting.api.Greeting
    with demo.greeting.provider.VietnameseGreeting;
~~~

Một artifact có thể dùng cùng bytecode implementation trong cả hai chế độ. Quy trình CI cần test cả đường chạy. Nếu chỉ kiểm tra module path rồi xóa resource, bản chạy classpath có thể mất provider dù module path vẫn đúng.

### Tình huống C: JAR thường được đưa lên module path mà chưa viết module-info

JAR đó là **automatic module**, không phải explicit module. Các tệp META-INF/services vẫn có thể đóng vai trò khai báo providers cho automatic module sau khi module được resolve. Thông thường đây là giai đoạn chuyển tiếp.

Dù có tên module (có thể ổn định nhờ Automatic-Module-Name), automatic module không đem lại cùng mức đóng gói/khai báo phụ thuộc tường minh như explicit module; kiểm thử service discovery và khả năng tương thích của public constructor là cần thiết.

### Tình huống D: consumer vẫn ở classpath, provider đã là named module

ServiceLoader của code unnamed module có thể tìm được provider ở named module **đã resolve và nhìn thấy qua loader/layer phù hợp**. Consumer classpath không có module-info riêng; cơ chế uses của explicit consumer không áp dụng cho nó. Tuy nhiên, provider có thể chưa được resolve, hoặc service API có thể tồn tại ở nhiều vị trí khác nhau.

Đừng kết luận chỉ từ việc “đã đặt JAR trong --module-path” rằng consumer classpath sẽ thấy provider. Kiểm tra --add-modules hoặc service binding, API identity và loader thực tế của ứng dụng.

### Tình huống E: consumer đã là named module, provider còn trên classpath

Một consumer explicit module cần requires đối với module API và uses service. ServiceLoader có thể khám phá provider dạng classpath qua provider-configuration file nếu lớp provider nhìn thấy được và dùng đúng service API. Đồng thời phải tránh đặt bản sao package API ở cả classpath và module path gây xung đột hoặc incompatibility.

Hệ lai nên được kiểm thử theo cấu hình launcher thực tế; không áp dụng máy móc quy tắc của “cả ba đều named modules” cho mọi tổ hợp.

## 10. Khi đóng gói bằng build tool, kiểm tra đầu ra chứ không chỉ nguồn

Nếu dùng Gradle hoặc Maven, tập trung vào cấu trúc của **JAR cuối cùng**:

~~~text
api.jar
├── module-info.class
└── demo/greeting/api/Greeting.class

provider.jar
├── module-info.class
├── demo/greeting/provider/VietnameseGreeting.class
└── META-INF/services/demo.greeting.api.Greeting   (nếu dual-mode)

app.jar
├── module-info.class
└── demo/greeting/app/Main.class
~~~

Thông thường module-info.java đặt ở src/main/java/module-info.java; META-INF/services đặt ở src/main/resources/META-INF/services/<FQCN của service>. Build tool phải biên dịch module descriptor thành **gốc JAR** và copy resource thành **META-INF/services** ở gốc JAR, không lồng thêm src/main/resources bên trong.

Khi dùng fat/uber JAR, cần lưu ý:

- Merge nhiều tệp META-INF/services nếu đóng nhiều provider classpath vào chung artifact; chỉ lấy một bản có thể làm mất các provider khác.
- Nếu relocate/shade package, cập nhật cả tên service/provider trong descriptor, resource và code liên quan; module-info.class cũng cần được xử lý đúng khả năng build tool. Không coi việc merge tài nguyên là tương đương module resolution.
- JPMS **không cho phép split packages** giữa các named modules trong cùng phạm vi giải quyết. Khi tách API/provider thành các module, đặt package theo ranh giới rõ, không sao chép cùng một package class vào hai module.
- Thư viện chưa modularize có thể ở dạng automatic module; tên module suy ra từ tên JAR có thể thay đổi khi đổi tên artifact. Nếu thật sự dùng module name trong requires, nên ổn định module name hoặc lên kế hoạch chuyển explicit module.
- Không tự động coi java -jar, java -cp và java --module-path là ba cách chạy tương đương. Cấu hình launcher quyết định artifact được xem là unnamed, automatic hay explicit named module.

Đối với thư viện phải hỗ trợ cả Java 8 và Java 17, cần kế hoạch packaging đa phiên bản hoặc biên dịch phù hợp; không đóng module-info.class biên dịch bằng JDK mới rồi giả định mọi JVM cũ đọc được. Bài này tập trung **Java 17+**.

## 11. Chẩn đoán lỗi migration theo từng lớp

### 11.1. Kiểm tra descriptor và resource trong JAR

~~~bash
jar --describe-module --file mlib/demo.greeting.provider.jar
jar --list --file mlib/demo.greeting.provider.jar
~~~

Kỳ vọng nhìn thấy module-info.class và khai báo provides. Nếu jar --describe-module cho biết đó là automatic module (hoặc không có descriptor explicit) thì bạn vẫn ở chế độ automatic; lúc này cần phân biệt quy tắc tự suy ra metadata từ service file.

Nếu module-info.class có mặt nhưng thiếu provides, hãy sửa module descriptor của **provider**, biên dịch và đóng gói lại. Chỉ thêm hoặc sửa tệp META-INF/services sẽ không đăng ký provider explicit trong module descriptor.

### 11.2. Kiểm tra module có được resolve không

~~~bash
java --show-module-resolution \
  --module-path mlib \
  --add-modules demo.greeting.provider \
  --module demo.greeting.app/demo.greeting.app.Main
~~~

Lệnh cho biết graph resolution mà launcher tạo. Phần diagnostic về module resolution được in bên cạnh output ứng dụng; output phụ thuộc tập module/JDK nên không dùng một stack trace giả làm kết quả cố định.

Nếu provider module vắng mặt khỏi graph dù nằm trên module path, kiểm tra --add-modules, service binding, root modules và ModuleLayer mà ứng dụng thực sự đang dùng.

### 11.3. Kiểm tra uses và requires

- Nếu module consumer được biên dịch hoặc chạy không đọc được kiểu Greeting: kiểm tra **requires demo.greeting.api** và **exports demo.greeting.api** từ module API.
- Nếu caller là explicit module và ServiceLoader.load báo lỗi kiểu “module ... does not declare uses”: bổ sung **uses demo.greeting.api.Greeting** trong module gọi ServiceLoader.
- Nếu provider báo lỗi compile khi khai báo provides hoặc implements Greeting: kiểm tra **requires demo.greeting.api**, tên service, tên provider, vị trí class trong module và tính hợp lệ của constructor/provider method.
- Nếu ServiceLoader duyệt được nhưng instantiate thất bại, kiểm tra provider constructor hoặc provider(), exception trong khởi tạo và dependency runtime.

### 11.4. Phân biệt trả về rỗng với lỗi cấu hình

ServiceLoader không nhất thiết ném lỗi khi **không tìm thấy provider nào**; code có thể duyệt 0 phần tử. Ngược lại, khi provider đã được khai báo nhưng tên lớp, kiểu dịch vụ hoặc cách khởi tạo sai, quá trình khám phá/khởi tạo lazy có thể ném **ServiceConfigurationError**.

Với công cụ kiểm tra, đừng bắt mọi lỗi rồi đổi thành providers=0 vì che giấu sự cố build. Ghi lại **service name**, **module của caller**, **module chứa provider**, **module layer**, **class loader**, đường chạy và exception trong log chẩn đoán.

Trong ứng dụng có nhiều provider, **không giả định thứ tự trả về** là cam kết ưu tiên toàn cục; module discovery, classpath và layer có các quy tắc thứ tự khác nhau. Nếu cần chọn một implementation cụ thể, định nghĩa tiêu chí lựa chọn trong hợp đồng service hoặc cấu hình host.

## 12. Những lỗi dễ mắc và cách sửa

| Biểu hiện | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| Chạy classpath thấy provider, module path trả 0 | JAR đã là explicit module nhưng thiếu provides, hoặc provider không được resolve | Thêm provides, kiểm tra graph/module layer |
| Module path chạy được, classpath trả 0 | Đã xóa META-INF/services khỏi dual-mode JAR | Giữ resource đúng tên và đúng nội dung cho classpath |
| Caller named module ném ServiceConfigurationError về uses | Module app thiếu uses | Thêm uses service vào đúng module chứa lời gọi |
| Compile module app không thấy API | Thiếu requires hoặc API module không exports service package | Sửa requires/exports |
| Provider khai báo provides nhưng compile lỗi | Class/provider không nằm trong module, sai kiểu hoặc thiếu constructor/provider method phù hợp | Sửa module graph và hợp đồng provider |
| Dùng exports implementation vẫn không thấy provider | exports không đăng ký SPI | Thêm provides ... with ... |
| Provider classpath dùng được nhưng automatic module không tạo được | Constructor không phù hợp hoặc module chưa resolve | Giữ public no-args constructor; kiểm tra module resolution |
| Thử provider() trên classpath/automatic module | Chỉ explicit module hỗ trợ cơ chế provider method | Dùng implementation trực tiếp có public no-args constructor |
| JAR thường thành automatic module có tên bất ngờ | Tên suy từ tên artifact | Thêm Automatic-Module-Name để ổn định tên; hoặc modularize tường minh |
| Module layer động không thấy provider | Tìm sai layer hoặc chưa resolve provider | Resolve vào layer liên quan và dùng đúng ServiceLoader.load(layer, service) |
| ClassCastException/not a subtype | Nạp hai bản service API qua loader/layer khác nhau | Thống nhất API identity qua parent/shared module |
| CI thành công nhưng bản phân phối thiếu provider | Resource/module-info.class bị đóng gói sai | Kiểm tra JAR cuối cùng bằng jar --list/--describe-module |

Không sửa lỗi phát hiện provider bằng cách mở exports/opens toàn bộ module nếu không có chứng cứ về access. Những thay đổi đó làm tăng bề mặt API mà không giải quyết đúng việc thiếu khai báo SPI.

## 13. Bộ kiểm thử tối thiểu cho quá trình chuyển đổi

Việc thêm một descriptor vào source chưa đủ chứng minh plugin chạy đúng. Nên có những lần chạy độc lập với classpath và module path:

1. **Classpath legacy:** dùng ba JAR ở -cp như phần 4.6; phải thấy đúng một VietnameseGreeting.
2. **Explicit module path:** dùng --module-path và --add-modules như phần 4.7; phải thấy đúng một VietnameseGreeting dù package implementation không exports.
3. **Khả năng phát hiện thiếu tệp classpath:** với artifact thử nghiệm bỏ META-INF/services nhưng giữ module-info.class, chế độ classpath sẽ thấy 0 provider. Không dùng artifact này thay cho JAR dual-mode sau test.
4. **Kiểm tra uses:** module consumer không có uses phải bị nhận diện là cấu hình sai khi gọi ServiceLoader; kiểm tra lỗi đúng lớp thay vì dựa vào output rỗng.
5. **Kiểm tra provides:** với explicit module thiếu provides, provider không được phát hiện qua module metadata chỉ nhờ class có tồn tại trong JAR.
6. **Không requires provider:** xác nhận module app chỉ phụ thuộc module API, và việc thay module provider không buộc app biên dịch lại.
7. **Kiểm tra ModuleLayer/loader:** nếu host nạp plugin động, dùng đúng layer chứa provider, có chính sách reload và dọn tham chiếu.
8. **Kiểm tra đóng gói:** xác nhận module-info.class ở gốc mỗi modular JAR, service resource có mặt nếu dual-mode và tên package không bị thay đổi bởi shading.
9. **Kiểm tra phiên bản:** chạy với JDK mục tiêu, kiểm tra cả compilation và runtime module resolution.

Trong thử nghiệm thay đổi descriptor, hãy tạo **artifact thử nghiệm riêng**; không sửa JAR phát hành đang dùng giữa lúc nhiều lần chạy song song. Không hardcode thứ tự provider khi có nhiều provider trong môi trường thật.

## 14. Checklist chuyển cùng provider sang module path

Trước khi đưa một provider SPI cũ lên JPMS, trả lời lần lượt:

- **Loại JAR:** provider sẽ là automatic module hay explicit named module? Có module-info.class trong bản đóng gói không?
- **Service API:** gói chứa service interface có được exports từ API module không?
- **Consumer:** module gọi ServiceLoader có requires API và **uses service** không?
- **Provider:** module chứa implementation có requires API và **provides service with provider** không?
- **Construction:** implementation có phù hợp với constructor/providing method của chế độ chạy không?
- **Encapsulation:** package implementation được giữ kín, tránh exports/opens không cần thiết chưa?
- **Resolution:** provider module có được resolve vào graph/layer mà ServiceLoader đang nhìn thấy không?
- **Dual mode:** nếu còn chạy trên classpath, META-INF/services có được giữ và copy vào JAR đúng vị trí không?
- **API identity:** host và provider có dùng cùng kiểu service thực sự ở runtime không?
- **Phân phối:** đã chạy thử cả java -cp và java --module-path bằng JAR cuối cùng, kiểm tra output và lỗi lazy discovery chưa?
- **Khả năng thay thế:** consumer còn độc lập với tên lớp triển khai và provider module không?

**Một bản chuyển đổi đúng** duy trì hợp đồng Java của provider, nhưng chuyển nguồn đăng ký từ tệp META-INF/services sang provides của explicit provider module, khai báo nhu cầu bằng uses trong consumer và bảo đảm requires/exports cho API được tham chiếu. Nếu cần hỗ trợ cả hai cách chạy, giữ đồng thời descriptor JPMS và tệp cấu hình classpath trong JAR cuối; luôn kiểm tra module resolution và layer trước khi kết luận ServiceLoader không hoạt động.

## Tài liệu tham khảo

- Java SE 17, **ServiceLoader** — hợp đồng classpath provider-configuration, provider trong module, uses/provides, constructor/provider method và ServiceConfigurationError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- dev.java, **Decoupling Modules with Services** — service directives và service binding: https://dev.java/learn/organizing/modules/services/
- dev.java, **Incremental Modularization with Automatic Modules** — automatic modules, module names và khả năng dùng META-INF/services: https://dev.java/learn/organizing/modules/automatic-module/