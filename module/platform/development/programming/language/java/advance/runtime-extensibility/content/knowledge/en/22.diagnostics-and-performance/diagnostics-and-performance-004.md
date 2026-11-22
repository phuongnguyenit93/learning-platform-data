# Điều tra ServiceConfigurationError từ tệp đăng ký, module hoặc constructor

Một ứng dụng Java có khả năng mở rộng thường dùng java.util.ServiceLoader để tìm implementation của một service interface (SPI) mà không cần biết trước tên class cụ thể. Việc phát hiện provider có thể dựa vào **META-INF/services** trên classpath hoặc **uses/provides** trong Java Platform Module System (JPMS). Cùng một lỗi ServiceConfigurationError có thể xuất hiện do tên file khai báo sai, cú pháp tên provider hỏng, class không tồn tại, class không thực sự triển khai SPI, thiếu constructor hợp lệ hoặc một provider method trong module hoạt động sai.

Mục tiêu của bài là **điều tra có hệ thống thay vì đoán theo một thông báo lỗi**: xác định provider được tìm từ đâu, lỗi xảy ra ở bước nào, đọc cause và class loader/module metadata, rồi sửa đúng nguồn phát hành. Ta sẽ dựng hai lab Java 17+ độc lập, một trên **classpath** và một dùng **explicit named modules**, với đầu ra kiểm chứng được.

## 1. ServiceConfigurationError là gì và xuất hiện ở đâu?

**java.util.ServiceConfigurationError extends java.lang.Error**, không phải Exception. Theo tài liệu Java 17, đây là lỗi khi **locating, loading hoặc instantiating** service provider. Bởi vậy:

- catch (Exception ex) **không bắt** ServiceConfigurationError.
- Bắt đúng ServiceConfigurationError tại ranh giới **service discovery/instantiation** có ý nghĩa khi host muốn báo lỗi cấu hình, đóng tính năng phụ thuộc hoặc cách ly một plugin tùy chọn.
- Không bắt Throwable rồi tiếp tục như không có chuyện gì: VirtualMachineError, ThreadDeath và lỗi nghiêm trọng khác không phải lỗi provider configuration thông thường.
- Thông báo getMessage() thường mang tên service/provider và gợi ý nguyên nhân, nhưng **văn bản không phải giao thức ổn định**. Đừng phân loại theo một chuỗi thông báo duy nhất; hãy xem stack trace, getCause() và artifact thực tế.

Vòng đời discovery điển hình:

~~~text
ServiceLoader.load(Service.class)
           |
           v
Tạo ServiceLoader (chưa chắc đã duyệt provider)
           |
           v
iterator.hasNext() hoặc iterator.next()
   |
   +--> classpath: tìm, đọc META-INF/services/<SPI>
   |                 parse tên provider
   |
   +--> JPMS: tìm provides trong module đã được giải quyết
   |             (consumer named module cần uses)
   |
   v
Nạp provider class / kiểm tra subtype hoặc provider()
           |
           v
Khởi tạo bằng public no-arg constructor
hoặc gọi public static provider() trong explicit named module
           |
           +--> lỗi: ServiceConfigurationError
           |
           v
Nhận provider instance
           |
           v
Gọi method nghiệp vụ (lỗi riêng của provider)
~~~

**Chỉ gọi ServiceLoader.load(...) không phải phép kiểm tra đầy đủ**. ServiceLoader duyệt và tạo provider theo cơ chế lazy. Cả Iterator.hasNext() và Iterator.next() có thể ném ServiceConfigurationError; khi dùng stream(), lỗi có thể xảy ra ở thao tác thực sự khám phá hoặc nạp provider, kể cả Provider.get().

Phân biệt ba nhóm:

| Giai đoạn | Dấu hiệu | Lỗi có thể nhận |
| --- | --- | --- |
| Không có registration hợp lệ | Không tìm thấy descriptor/provides phù hợp | Thường là **0 provider**, không nhất thiết có ServiceConfigurationError |
| Có registration nhưng không nạp/tạo được | Class thiếu, sai subtype, constructor/factory lỗi | **ServiceConfigurationError** |
| Provider đã tạo, gọi nghiệp vụ thất bại | Resource riêng thiếu, input sai, I/O, exception do plugin | Lỗi nghiệp vụ; **không tự động** trở thành ServiceConfigurationError |

Ví dụ: descriptor **sai tên file** nên không được phát hiện có thể cho tập kết quả rỗng; descriptor **đúng tên nhưng khai báo class không tồn tại** thường dẫn tới ServiceConfigurationError khi duyệt. Hai trường hợp này cần cách khắc phục khác nhau.

## 2. Bản đồ nguyên nhân: file đăng ký, JPMS và constructor

| Nguồn khai báo | Tình huống | Điểm cần xác minh |
| --- | --- | --- |
| META-INF/services trên classpath | File sai tên, đặt sai vị trí, không có trong runtime classpath | Exact path META-INF/services/<tên nhị phân SPI>, nội dung JAR |
| META-INF/services trên classpath | Dòng không phải tên class hợp lệ, sai encoding hoặc I/O khi đọc | Nội dung file, UTF-8, số dòng, dấu # comment, khoảng trắng |
| META-INF/services trên classpath | Tên class không tồn tại hoặc loader không nhìn thấy | Class có mặt trong JAR nào, loader nào thực sự đang được dùng |
| META-INF/services trên classpath | Provider không là subtype của SPI | Kiểm tra interface thực sự implemented và **class identity** |
| META-INF/services trên classpath | Provider không có public constructor không tham số | javap -public, constructors và visibility của class |
| META-INF/services trên classpath | Constructor ném exception hoặc error | Stack trace và getCause() |
| Explicit named module (JPMS) | Consumer thiếu uses service hoặc module provider không được resolve | module-info, module graph, cách gọi ServiceLoader.load |
| Explicit named module (JPMS) | provides trỏ provider không load được, constructor lỗi | module descriptor runtime, loader, cause |
| Explicit named module (JPMS) | public static provider() trả null, ném lỗi hoặc không đúng type | Chữ ký và kết quả của provider method |
| Automatic module | Dùng kỳ vọng provider factory như explicit named module | Automatic module dùng constructor; không có provider method |
| Bất kỳ mô hình nào | Có hai bản SPI trùng tên nhưng khác defining loader | So sánh ClassLoader và Class object, không chỉ tên class |

**Không mọi lỗi JPMS đều mang đúng tên ServiceConfigurationError**. Lỗi biên dịch module-info, lỗi resolution trước lúc tạo layer hoặc IllegalAccessError/NoClassDefFoundError trong code nghiệp vụ có thể mang loại exception/error khác. Ta cần xác định chặng thất bại đầu tiên thay vì quy mọi lỗi plugin về một nhãn.

## 3. Descriptor trên classpath: những quy tắc dễ sai

Trên classpath, service configuration file có **đường dẫn chính xác**:

~~~text
META-INF/services/com.example.spi.MyService
~~~

Tên file là **tên binary đầy đủ của service interface/class**, không phải tên provider, không có phần mở rộng .txt, .class hoặc .java. File này nằm tại **gốc mỗi JAR** chứa registration. Mỗi dòng hợp lệ là tên đầy đủ của một provider class; một dấu # mở đầu phần comment đến hết dòng. ServiceLoader cho phép whitespace bao quanh các dòng, nhưng tên provider không thể chứa khoảng trắng bên trong.

Ví dụ:

~~~text
# UTF-8 text; file name = META-INF/services/demo.spi.Action
demo.providers.Healthy
demo.providers.Backup
~~~

**Ba lỗi cần phân biệt:**

1. Tệp bị đổi từ META-INF/services/demo.spi.Action thành META-INF/services/demo.spi.Actions. Với đúng một JAR trong classpath, loader **không thấy tệp đăng ký cho Action** và có thể trả 0 provider.
2. Tệp đúng tên nhưng một dòng ghi demo.providers.NotPresent. Tên được đọc thành một registration; khi Java không tìm được class, ServiceConfigurationError có thể phát sinh trong lúc duyệt.
3. Tệp đúng tên nhưng chứa "not a class name!". Đây không phải tên binary hợp lệ; parser có thể báo ServiceConfigurationError khi đang đọc descriptor, **trước khi tạo bất kỳ instance**.

Cả ba đều có thể khiến người dùng báo "không load được plugin", nhưng không sửa bằng cùng thao tác. Trường hợp (1) cần sửa packaging/tên file; trường hợp (2) cần sửa registration hoặc classpath; trường hợp (3) cần sửa format/encoding.

**Đừng đọc source file trong project rồi kết luận JAR đúng.** Cần kiểm tra file thực sự có trong artifact được triển khai bằng jar --list và kiểm tra nội dung của chính entry trong artifact (có thể giải nén bản sao khi điều tra). Đường dẫn trên Windows hiển thị dấu phân cách thư mục khác nhau nhưng **tên entry trong JAR** vẫn dùng dấu /.

## 4. Lab classpath Java 17+: tái hiện bảy biến thể

Lab này biên dịch cùng một tập class provider rồi đóng gói nhiều JAR có **descriptor khác nhau**. Như vậy, chỉ cần thay JAR trên runtime classpath là ta có thể phân biệt lỗi packaging, tên class, subtype và constructor.

### 4.1. Cây thư mục

~~~text
classpath-lab/
├── src/
│   ├── api/demo/spi/Action.java
│   ├── host/demo/host/Check.java
│   └── providers/demo/providers/
│       ├── Healthy.java
│       ├── NeedsArgument.java
│       ├── Boom.java
│       └── NotAction.java
├── descriptors/
│   ├── good/META-INF/services/demo.spi.Action
│   ├── typo/META-INF/services/demo.spi.Actions
│   ├── missing-class/META-INF/services/demo.spi.Action
│   ├── bad-syntax/META-INF/services/demo.spi.Action
│   ├── no-ctor/META-INF/services/demo.spi.Action
│   ├── throws/META-INF/services/demo.spi.Action
│   └── wrong-type/META-INF/services/demo.spi.Action
├── build/               (tạo khi build)
└── dist/                (tạo khi build)
~~~

### 4.2. SPI chung

File **src/api/demo/spi/Action.java**:

~~~java
package demo.spi;

public interface Action {
    String id();
}
~~~

Cả host và provider cùng tham chiếu tới **dist/api.jar** khi compile. JAR provider không đóng gói lại demo/spi/Action.class.

### 4.3. Provider tốt

File **src/providers/demo/providers/Healthy.java**:

~~~java
package demo.providers;

import demo.spi.Action;

public final class Healthy implements Action {
    public Healthy() {}

    @Override
    public String id() {
        return "ok";
    }
}
~~~

Đây là provider classpath hợp lệ: public class, implements Action, public constructor không tham số.

### 4.4. Class đúng interface nhưng thiếu constructor no-arg

File **src/providers/demo/providers/NeedsArgument.java**:

~~~java
package demo.providers;

import demo.spi.Action;

public final class NeedsArgument implements Action {
    public NeedsArgument(String message) {}

    @Override
    public String id() {
        return "argument";
    }
}
~~~

Khi đã tự khai báo **chỉ** constructor nhận String, Java không tự sinh constructor không tham số. Vì thế ServiceLoader không thể tạo instance theo quy tắc classpath, dù class tồn tại và thực sự implements Action. Đây là nguyên nhân riêng, **không phải ClassNotFoundException**.

### 4.5. Constructor có đúng chữ ký nhưng tự ném exception

File **src/providers/demo/providers/Boom.java**:

~~~java
package demo.providers;

import demo.spi.Action;

public final class Boom implements Action {
    public Boom() {
        throw new IllegalStateException("construction failed");
    }

    @Override
    public String id() {
        return "boom";
    }
}
~~~

ServiceLoader tìm được class và constructor phù hợp, nhưng **khởi tạo thất bại**. Trong stack trace của ServiceConfigurationError, getCause() có thể thể hiện exception gốc do constructor ném. Khi điều tra, cần ghi cả cause chain chứ không chỉ nhãn "could not instantiate".

### 4.6. Class tồn tại nhưng không phải subtype của SPI

File **src/providers/demo/providers/NotAction.java**:

~~~java
package demo.providers;

public final class NotAction {
    public NotAction() {}
}
~~~

Class này cố tình **không implements Action**. Nếu descriptor ghi tên nó như một provider của demo.spi.Action, việc Java nhìn thấy class chưa đủ: kiểm tra kiểu sẽ thất bại và ServiceConfigurationError được ném khi discovery/instantiation.

### 4.7. Host phân biệt lỗi cấu hình và lỗi nghiệp vụ

File **src/host/demo/host/Check.java**:

~~~java
package demo.host;

import demo.spi.Action;
import java.util.Iterator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Check {
    public static void main(String[] args) {
        boolean trace = args.length > 0 && "--trace".equals(args[0]);
        Iterator<Action> providers =
                ServiceLoader.load(Action.class).iterator();
        boolean found = false;

        for (;;) {
            Action action;
            try {
                if (!providers.hasNext()) {
                    break;
                }
                action = providers.next();
            } catch (ServiceConfigurationError error) {
                System.out.println("CONFIG_ERROR");
                if (trace) {
                    error.printStackTrace(System.err);
                }
                return;
            }

            found = true;
            try {
                System.out.println("FOUND " + action.id());
            } catch (RuntimeException failure) {
                // Phần nghiệp vụ chạy sau khi provider đã được tạo.
                System.out.println("PROVIDER_RUNTIME_ERROR");
                if (trace) {
                    failure.printStackTrace(System.err);
                }
            }
        }

        if (!found) {
            System.out.println("NO_PROVIDER");
        }
    }
}
~~~

**Vì sao try phải bao cả hasNext() lẫn next()?** Java 17 cho phép ServiceConfigurationError phát sinh ở **cả hai**. Với bad-syntax, vấn đề có thể xuất hiện trong lúc đọc config ngay tại hasNext(); với no-ctor hoặc throws, lỗi thường được phát hiện khi next() cố tạo instance.

Mã này cố ý **dừng discovery sau một lỗi cấu hình**. Theo hợp đồng JDK, iterator sau ServiceConfigurationError chỉ best-effort để tìm provider tiếp theo; không được bảo đảm phục hồi. Một chiến lược thử tiếp cho plugin tùy chọn phải có hạn mức lỗi/vòng duyệt, ghi nhận trạng thái partial và không xem tập provider chưa đầy đủ là thành công. Với bài điều tra, dừng rồi sửa artifact là cách tái hiện nguyên nhân nhất quán hơn.

Khi có --trace, exception được in ở **stderr**, vì vậy text stack trace/JDK-specific có thể khác nhau. Stdout ổn định chỉ chứa nhãn trong ví dụ.

### 4.8. Nội dung bảy descriptor

Tạo các file văn bản dưới descriptors/ với **nội dung tương ứng**:

**good/META-INF/services/demo.spi.Action**

~~~text
demo.providers.Healthy
~~~

**typo/META-INF/services/demo.spi.Actions** (cố ý sai **tên file**, không sai nội dung)

~~~text
demo.providers.Healthy
~~~

**missing-class/META-INF/services/demo.spi.Action**

~~~text
demo.providers.DoesNotExist
~~~

**bad-syntax/META-INF/services/demo.spi.Action**

~~~text
not a class name!
~~~

**no-ctor/META-INF/services/demo.spi.Action**

~~~text
demo.providers.NeedsArgument
~~~

**throws/META-INF/services/demo.spi.Action**

~~~text
demo.providers.Boom
~~~

**wrong-type/META-INF/services/demo.spi.Action**

~~~text
demo.providers.NotAction
~~~

Không có file descriptor chung ở build/providers/. Ta đưa descriptor vào **từng JAR** khi đóng gói; mỗi lượt chạy chỉ dùng một JAR biến thể và api.jar.

### 4.9. Compile, đóng JAR và chạy

Từ thư mục **classpath-lab/**, với JDK 17+ và shell bash/POSIX:

~~~bash
mkdir -p build/api build/providers build/host dist

javac --release 17 -encoding UTF-8 -d build/api \
  src/api/demo/spi/Action.java
jar --create --file dist/api.jar -C build/api .

javac --release 17 -encoding UTF-8 \
  -cp dist/api.jar -d build/providers \
  src/providers/demo/providers/*.java

javac --release 17 -encoding UTF-8 \
  -cp dist/api.jar -d build/host \
  src/host/demo/host/Check.java

for case_name in good typo missing-class bad-syntax no-ctor throws wrong-type
do
  jar --create --file "dist/$case_name.jar" \
    -C build/providers . -C "descriptors/$case_name" .
done

for case_name in good typo missing-class bad-syntax no-ctor throws wrong-type
do
  printf "%s -> " "$case_name"
  java -cp "build/host:dist/api.jar:dist/$case_name.jar" \
    demo.host.Check
done
~~~

**Stdout kỳ vọng chính xác** với đúng các JAR và classpath đã nêu:

~~~text
good -> FOUND ok
typo -> NO_PROVIDER
missing-class -> CONFIG_ERROR
bad-syntax -> CONFIG_ERROR
no-ctor -> CONFIG_ERROR
throws -> CONFIG_ERROR
wrong-type -> CONFIG_ERROR
~~~

Cách hiểu:

- **good**: tên descriptor và constructor hợp lệ, in FOUND ok.
- **typo**: provider class hiện diện nhưng file services có tên demo.spi.Actions thay vì demo.spi.Action. Không có registration cho SPI đang dùng, nên in NO_PROVIDER chứ **không bắt buộc có error**.
- **missing-class**: descriptor yêu cầu một class không tồn tại trong runtime loader.
- **bad-syntax**: tên provider không hợp lệ ngay từ nội dung file.
- **no-ctor**: thiếu public no-arg constructor.
- **throws**: constructor chạy rồi ném IllegalStateException.
- **wrong-type**: class tồn tại nhưng không assignable tới Action.

Nếu chạy trên Windows trong PowerShell/CMD, dấu phân cách trong -cp là dấu **;**, không phải dấu **:**. Các cú pháp for, dấu \ để xuống dòng, biến $case_name và mkdir -p thuộc bash; dùng Git Bash/WSL hoặc viết lại tương đương cho PowerShell.

Để xem nguyên nhân gốc của từng biến thể, chạy riêng:

~~~bash
java -cp "build/host:dist/api.jar:dist/throws.jar" \
  demo.host.Check --trace

java -cp "build/host:dist/api.jar:dist/no-ctor.jar" \
  demo.host.Check --trace

javap -public -classpath "dist/api.jar:dist/no-ctor.jar" \
  demo.providers.NeedsArgument
~~~

Lệnh javap giúp xác nhận có constructor nhận String nhưng **không có constructor rỗng**. Với throws, stack trace nên thể hiện đường khởi tạo provider và IllegalStateException gốc. Không so khớp toàn bộ stderr bằng văn bản cố định: thông điệp/stack frame phụ thuộc cách JDK thể hiện lỗi.

## 5. Quy trình chẩn đoán classpath theo bằng chứng

Khi ServiceLoader không thấy provider hoặc ném ServiceConfigurationError, hãy làm lần lượt:

1. **Xác nhận service type thực sự là gì.** In Action.class.getName() và Action.class.getClassLoader(); không suy từ tên đơn giản hoặc một bản interface trong source tree.
2. **Xác nhận class loader tìm provider.** ServiceLoader.load(Action.class) dùng TCCL của thread gọi; ServiceLoader.load(Action.class, explicitLoader) dùng loader được truyền. Classpath của IDE, test runner, servlet container và thread worker có thể khác nhau.
3. **Kiểm tra chính xác runtime JAR.** Dùng jar --list --file plugin.jar để tìm META-INF/services/demo.spi.Action và class .class liên quan. Không chỉ nhìn file bên ngoài JAR.
4. **Mở descriptor đúng tên và kiểm tra từng dòng.** Đúng tên binary class, không chứa khoảng trắng bất hợp lệ, không lẫn suffix .class, đúng UTF-8. Một dòng sai có thể làm toàn lượt discovery thất bại.
5. **Kiểm tra class có tải được không.** Nếu tên class đúng nhưng JVM báo class not found, xem dependency còn thiếu, class loader scope, JAR version và module/classpath deployment.
6. **Kiểm tra subclass/constructor.** So sánh SPI bằng isAssignableFrom(...) trên Class object thực tế; dùng javap -public hoặc reflection có kiểm soát để xác nhận constructor phù hợp.
7. **Kiểm tra getCause() và stack trace.** Phân biệt lỗi parse, linkage, constructor hoặc factory code tự ném lỗi.
8. **Sửa artifact rồi chạy trong tiến trình sạch** khi có thể; không dựa vào reload() như một thao tác "chữa" một descriptor/JAR còn sai.

Lệnh tham khảo:

~~~bash
jar --list --file dist/good.jar
jar --list --file dist/missing-class.jar
javap -public -classpath "dist/api.jar:dist/good.jar" \
  demo.providers.Healthy
~~~

Khi log trong hệ thống thật, lưu **service name, provider name (nếu đã biết), artifact path/hash, JDK version, loader identity, module name, exception class, message, cause chain và giai đoạn**. Tránh ghi full source hoặc mật khẩu cấu hình của plugin vào log. Cần quan sát riêng kết quả NO_PROVIDER, CONFIG_ERROR và PROVIDER_RUNTIME_ERROR.

**Chi tiết có thể gây hiểu nhầm:** hai file JAR cùng có descriptor cho một SPI có thể khiến ServiceLoader tìm nhiều provider. Thứ tự file descriptor phụ thuộc thứ tự ClassLoader.getResources(...). Không xây logic chính xác của hệ thống dựa vào một thứ tự classpath ngẫu nhiên; càng không để một JAR hỏng đứng trước một provider tốt mà mặc định provider tốt chắc chắn được sử dụng.

## 6. JPMS: điều gì thay đổi khi provider nằm trong named module?

Từ Java 9, explicit named module thường khai báo provider bằng **module-info.java**:

~~~java
// Trong một module provider (mã minh họa):
module demo.provider {
    requires demo.api;
    provides demo.spi.Action with demo.provider.Direct;
}
~~~

Consumer là **explicit named module** cần khai báo **uses demo.spi.Action** nếu gọi ServiceLoader cho service đó. Nếu thiếu uses, ServiceLoader có thể ném ServiceConfigurationError ngay khi tạo loader; kiểm tra lỗi ở bước gọi load(...) chứ không chỉ iterator.

So với classpath descriptor:

| Vấn đề | Classpath/unnamed module | Explicit named module |
| --- | --- | --- |
| Nơi khai báo provider | META-INF/services/<SPI> | provides ... with ... trong module-info |
| Phạm vi tìm | ClassLoader và các resource mà nó nhìn thấy | Graph module đã được resolve; có thể dùng load(layer, service) |
| Consumer uses | Không có module-info | Cần uses đối với caller explicit named module |
| Cách tạo provider | Public no-arg constructor | Public no-arg constructor **hoặc provider method** hợp lệ |
| Provider class có cần implements SPI? | Có | Nếu dùng provider() thì class factory **không nhất thiết** implements SPI |
| Tính hợp lệ của tên/type | Chủ yếu phát hiện khi runtime scan | Nhiều lỗi descriptor được javac phát hiện lúc compile module |
| Resource descriptor đồng thời | Service file đăng ký classpath provider | Provider trong named module được định danh bằng provides; không nên dùng service file như nguồn đăng ký thay thế |
| Provider discovery order | Phụ thuộc ClassLoader.getResources và từng descriptor | Thứ tự các module trong layer không được bảo đảm |

**Provider method** trong explicit named module là **public static phương thức tên provider, không tham số, kiểu trả về assignable tới service**. Nếu tồn tại, ServiceLoader dùng nó để lấy instance. Method có thể trả null hoặc ném lỗi; cả hai là nguyên nhân ServiceConfigurationError lúc tạo provider.

**Automatic module** trên module path có quy tắc khác: cần provider constructor, không hỗ trợ kiểu factory provider method của explicit named module. Vì vậy mọi hướng dẫn "chỉ cần thêm public static provider()" phải kiểm tra artifact thực sự là explicit module hay automatic module.

Cần phân biệt **module chưa được resolve** với **provider đã được resolve nhưng tạo thất bại**. Module có trong thư mục --module-path chưa chứng minh đã thuộc module graph được thực thi. Trong lab dưới đây, ta thêm --add-modules demo.provider để chắc chắn module provider được giải quyết.

## 7. Lab JPMS Java 17+: direct constructor và factory provider

Lab này tách biệt với classpath-lab để tránh nhầm tên binary giữa hai bộ mã. Chúng ta tạo ba explicit modules:

- **demo.api**: xuất public SPI Action.
- **demo.provider**: đăng ký hai provider, một trực tiếp qua public constructor và một qua public static provider().
- **demo.host**: khai báo uses và gọi ServiceLoader.

### 7.1. Cây thư mục

~~~text
module-lab/
├── src/
│   ├── demo.api/
│   │   ├── module-info.java
│   │   └── demo/spi/Action.java
│   ├── demo.provider/
│   │   ├── module-info.java
│   │   └── demo/provider/
│   │       ├── Direct.java
│   │       └── Factory.java
│   └── demo.host/
│       ├── module-info.java
│       └── demo/host/Main.java
└── build/mods/              (tạo khi biên dịch)
~~~

### 7.2. Module API

File **src/demo.api/module-info.java**:

~~~java
module demo.api {
    exports demo.spi;
}
~~~

File **src/demo.api/demo/spi/Action.java**:

~~~java
package demo.spi;

public interface Action {
    String id();
}
~~~

### 7.3. Module provider và hai cơ chế khởi tạo

File **src/demo.provider/module-info.java**:

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.Action with
            demo.provider.Direct, demo.provider.Factory;
}
~~~

File **src/demo.provider/demo/provider/Direct.java**:

~~~java
package demo.provider;

import demo.spi.Action;

public final class Direct implements Action {
    public Direct() {}

    @Override
    public String id() {
        return "direct";
    }
}
~~~

File **src/demo.provider/demo/provider/Factory.java**:

~~~java
package demo.provider;

import demo.spi.Action;

public final class Factory {
    private Factory() {}

    // Trong explicit named module, ServiceLoader nhận instance từ method này.
    public static Action provider() {
        return () -> "factory";
    }
}
~~~

Factory **không implements Action** và có constructor private. Điều này hợp lệ vì nó công khai một provider method có kiểu trả về là Action; ServiceLoader gọi provider() và nhận lambda thực sự implements Action. **Không áp dụng mẫu này cho classpath descriptor** rồi chờ ServiceLoader classpath gọi Factory.provider(): trường hợp classpath cần class provider assignable tới SPI và public no-arg constructor.

Không cần exports demo.provider trong module-info: class dùng làm provider có thể nằm trong package không exports, và service framework vẫn có cơ chế truy cập provider phù hợp. Nếu host muốn tự reflection vào non-public member của provider thì cần phân tích opens/exports riêng, không suy từ việc ServiceLoader đã tạo được instance.

### 7.4. Module host có uses

File **src/demo.host/module-info.java**:

~~~java
module demo.host {
    requires demo.api;
    uses demo.spi.Action;
}
~~~

File **src/demo.host/demo/host/Main.java**:

~~~java
package demo.host;

import demo.spi.Action;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        boolean trace = args.length > 0 && "--trace".equals(args[0]);

        try {
            List<String> ids = new ArrayList<>();
            for (Action provider : ServiceLoader.load(Action.class)) {
                ids.add(provider.id());
            }

            Collections.sort(ids);
            for (String id : ids) {
                System.out.println("FOUND " + id);
            }
            if (ids.isEmpty()) {
                System.out.println("NO_PROVIDER");
            }
        } catch (ServiceConfigurationError error) {
            System.out.println("CONFIG_ERROR");
            if (trace) {
                error.printStackTrace(System.err);
            }
        }
    }
}
~~~

Host gom ID rồi **sắp xếp** trước khi in vì thứ tự tìm provider từ nhiều module không được định nghĩa tổng quát. Trong lab này hai provider nằm cùng module với thứ tự provides cụ thể, nhưng sắp xếp giúp output không phụ thuộc vào chính sách thứ tự khi bài tập mở rộng thêm module.

Lưu ý trong sản phẩm thật, method provider.id() có thể ném lỗi nghiệp vụ và nên được catch riêng. Ở đây cả hai provider có id() thuần, nên try/catch tập trung vào failure khi ServiceLoader giải quyết hoặc khởi tạo provider.

### 7.5. Biên dịch và chạy trên module path

Từ thư mục **module-lab/**, JDK 17+ và shell bash/POSIX:

~~~bash
mkdir -p build/mods

javac --release 17 -encoding UTF-8 \
  --module-source-path src -d build/mods \
  -m demo.api,demo.provider,demo.host

java --module-path build/mods \
  --add-modules demo.provider \
  -m demo.host/demo.host.Main
~~~

Stdout kỳ vọng chính xác:

~~~text
FOUND direct
FOUND factory
~~~

Dùng lệnh sau để kiểm tra **module descriptor đã biên dịch**:

~~~bash
java --module-path build/mods --describe-module demo.provider
java --module-path build/mods --describe-module demo.host
~~~

Lệnh --describe-module có thể in thêm tên packages, requires, exports và thứ tự khác nhau giữa JDK; điều cần xem là demo.provider chứa **provides demo.spi.Action** và demo.host có **uses demo.spi.Action**. Nếu bạn không thấy provider khi thử ở môi trường khác, kiểm tra graph đã resolve và chú ý rằng ví dụ dùng --add-modules demo.provider để đưa nó vào graph.

### 7.6. Tái hiện lỗi từ provider method trong module

Sau khi xác nhận lab thành công, **chỉ trong bản lab riêng**, đổi thân Factory.provider() thành:

~~~java
public static Action provider() {
    return null;
}
~~~

Đây là **đoạn sửa một method**, không phải file Java hoàn chỉnh. Biên dịch lại module-lab bằng lệnh javac ở trên, rồi chạy lại. Trình biên dịch có thể chấp nhận vì kiểu trả về là Action, nhưng ServiceLoader khi gọi provider() nhận null sẽ ném ServiceConfigurationError. Host in:

~~~text
CONFIG_ERROR
~~~

Bật --trace để xem cause/stack trace cụ thể:

~~~bash
java --module-path build/mods --add-modules demo.provider \
  -m demo.host/demo.host.Main --trace
~~~

Một biến thể khác là để Factory.provider() ném IllegalStateException. Khi đó ServiceConfigurationError thường mang cause phản ánh lỗi bên trong factory. Lưu ý: **thông điệp/cause chi tiết phụ thuộc trường hợp và bản JDK**, nên đừng so sánh toàn bộ stack trace bằng text literal.

Muốn tái hiện lỗi **constructor trong explicit named module**, khôi phục Factory.provider() hợp lệ rồi đổi constructor của Direct:

~~~java
public Direct() {
    throw new IllegalStateException("module constructor failed");
}
~~~

Lệnh compile lại vẫn có thể thành công (constructor đúng public no-arg), nhưng lúc tạo provider Direct thì ném lỗi và ServiceLoader báo ServiceConfigurationError. Đây là failure runtime. Ngược lại, nếu **bỏ hoàn toàn** public no-arg constructor khỏi Direct và Direct không có provider() hợp lệ, javac có thể từ chối câu provides ngay tại compile time; đừng gán mọi lỗi định nghĩa module đều cho một exception runtime.

### 7.7. Tái hiện consumer thiếu uses

Trong bản lab, bỏ dòng uses demo.spi.Action; khỏi module-info.java của demo.host, biên dịch lại rồi thử gọi ServiceLoader.load(Action.class). Theo hợp đồng JDK 17, caller thuộc explicit named module không khai báo uses cho service có thể gặp ServiceConfigurationError ngay ở **lời gọi load(...)**.

Điểm cần kiểm tra: method trong code host đã đặt lời gọi load(...) bên trong try/catch nên có thể quan sát được CONFIG_ERROR. Nếu bạn chỉ catch lỗi quanh for-loop nhưng tạo ServiceLoader **bên ngoài try**, lỗi khởi tạo service loader do thiếu uses sẽ đi qua boundary.

Để khắc phục, khôi phục uses vào module-info.java của consumer; không sửa provides ở provider module nếu lỗi thực sự xuất phát từ consumer.

## 8. Trình tự điều tra lỗi module đúng nghĩa

Với named module, quy trình phải bắt đầu từ **cấu hình runtime**, không phải tìm ngay META-INF/services:

1. **Xác minh provider là explicit/automatic/unnamed module.** Dùng jar --describe-module cho modular JAR hoặc java --describe-module với module path; kiểm tra module-info.class và module graph.
2. **Xem consumer có uses hay không.** ServiceLoader.load từ explicit module yêu cầu uses tương ứng; đặt try quanh cả lời gọi tạo loader.
3. **Xem provider có được resolve không.** Chỉ nằm trong thư mục module path chưa đủ; xác minh root modules, --add-modules, resolution hoặc ModuleLayer runtime.
4. **Đọc provides ... with ... của provider.** Provider class phải được khai báo trong chính module cung cấp service; nhiều lỗi subtype/constructor được javac bắt sớm nếu build từ source hợp lệ.
5. **Kiểm tra cách tạo instance:** không có provider method thì cần public no-arg constructor và assignability; nếu có public static provider() thì kiểm tra kiểu trả về, null và exception do method ném.
6. **Kiểm tra danh tính SPI:** module API nào được consumer và provider đọc? Hai bản interface cùng tên nhưng do loader khác định nghĩa có thể không assignable.
7. **Đọc cause chain và runtime class/module:** in class.getModule().getName(), getClassLoader() khi có Class object hợp lệ. Không chỉ dùng getName() vì không phân biệt loader.
8. **Sửa đúng artifact và tái triển khai:** nếu module descriptor sai, xây lại module; nếu constructor/factory thất bại, sửa implementation; nếu module chưa resolve, sửa graph và cách tạo layer.

**Lỗi compile-time của module-info không được phép che dưới nhãn ServiceConfigurationError.** Ví dụ module-info dùng provides với provider không thuộc module hoặc không đáp ứng điều kiện JLS có thể bị javac từ chối trước lúc ứng dụng chạy. Phân định thời điểm lỗi sẽ tiết kiệm thời gian điều tra đáng kể.

ModuleLayer còn làm bài toán tinh tế hơn: ServiceLoader.load(layer, Action.class) tìm service trong layer và các parent layer theo hợp đồng API, **không tìm classpath/unnamed module providers** giống việc scan toàn bộ TCCL. Vì thế thiếu provider ở layer-specific lookup chưa hẳn là provider implementation hỏng; có thể host đang dùng sai layer.

## 9. Constructor, provider method và lỗi linkage khác nhau thế nào?

| Trường hợp | Thứ đã được chứng minh | Điều vẫn có thể sai |
| --- | --- | --- |
| Class provider xuất hiện trong jar --list | Có file .class ở artifact | JAR runtime có được loader nhìn thấy? Class có phải subtype SPI? |
| Class.forName(name, false, loader) thành công | Có thể định vị/định nghĩa class, tùy loader | Constructor public no-arg, dependency khi initialize, provider method và quyền truy cập |
| javap cho thấy public X() | Bytecode có constructor đúng hình dạng | Constructor có thể ném exception |
| Provider implements SPI tại source | Source có câu implements | Runtime SPI có thể là bản class identity khác |
| Class có public static provider() | Có method đúng tên | Chỉ dùng làm provider method trong bối cảnh module hỗ trợ; return type/return value có thể sai |
| ServiceLoader.load(...) trả object | Đã tạo ServiceLoader | Chưa chắc đã duyệt, nạp hoặc tạo provider |
| Iterator.hasNext() trả true | Có provider candidate | Iterator.next() vẫn có thể ném ServiceConfigurationError |
| Provider instance tạo thành công | Constructor/factory trả về instance | Method nghiệp vụ vẫn có thể ném exception hoặc dùng resource sai |

**NoClassDefFoundError không đồng nghĩa ClassNotFoundException.** Một provider class có thể tồn tại nhưng khi JVM liên kết hoặc khởi tạo nó, một dependency khác bị thiếu hoặc không tương thích. Xem cause chain và danh sách dependency, không chỉ sửa tên descriptor. Với lỗi linkage khác (NoSuchMethodError, IncompatibleClassChangeError, IllegalAccessError), cần xem ABI/JAR runtime; không mặc định mọi Error đều được ServiceLoader bọc thành ServiceConfigurationError trong mọi chặng.

**TCCL:** ServiceLoader.load(Service.class) dùng Thread.currentThread().getContextClassLoader(). Một worker thread có context loader khác thread main, hoặc plugin manager dùng loader riêng, có thể tìm thấy descriptor nhưng không nạp được implementation/API đúng. Nếu thiết kế cho phép, dùng ServiceLoader.load(Service.class, pluginLoader) và quản lý loader rõ ràng. Thay TCCL mà không restore trong finally có thể gây lỗi lookup dây chuyền cho request tiếp theo.

**Class identity:** hai Class object có cùng tên demo.spi.Action nhưng được định nghĩa bởi hai ClassLoader khác nhau là **hai type JVM khác nhau**. Khi báo "not a subtype" dù source implements Action, kiểm tra defining loader của cả interface và implementation; tránh đóng API JAR bản riêng vào mỗi plugin nếu host cần ép provider về interface do host định nghĩa.

## 10. Cách log đủ thông tin mà không lộ dữ liệu nhạy cảm

Đừng chỉ bắt rồi in "CONFIG_ERROR"; trong sản phẩm cần đủ ngữ cảnh để truy nguyên. Một helper đơn giản ở ranh giới lỗi có thể là:

~~~java
// Mã minh họa tích hợp, không phải file Java độc lập.
static void reportServiceFailure(
        Class<?> service, ServiceConfigurationError error) {
    System.err.println("service=" + service.getName());
    System.err.println("serviceLoader=" + service.getClassLoader());
    System.err.println("message=" + error.getMessage());

    Throwable cause = error.getCause();
    int depth = 0;
    while (cause != null && depth < 8) {
        System.err.println("cause[" + depth + "]="
                + cause.getClass().getName()
                + ": " + cause.getMessage());
        cause = cause.getCause();
        depth++;
    }
    error.printStackTrace(System.err);
}
~~~

Đối với logger structured ở production, ưu tiên các trường service, candidateProvider, artifactId, artifactHash, loaderId, moduleName, stage (LOOKUP/PARSE/LOAD/INSTANTIATE/INVOKE), exceptionClass, rootCauseClass và correlationId. Đừng dùng hashCode() của ClassLoader như một định danh toàn cục duy nhất không thể trùng; gán ID riêng trong plugin manager nếu cần.

Nếu getCause() là null, vẫn có thể có lỗi nghiêm trọng trong bản thân descriptor; **null cause không có nghĩa lỗi giả**. Ghi message và ngữ cảnh chính xác để chẩn đoán. Nếu provider() trả null trong named module, bản JDK có thể báo "provider method returned null" mà không có một cause là Throwable do user code ném.

Tránh log toàn bộ mã nguồn plugin, credential, URL có token hoặc dữ liệu người dùng; chỉ in stack trace đầy đủ vào kênh log nội bộ được bảo vệ. Với hệ thống có nhiều phiên bản JDK, đừng parse string chi tiết từ stack trace làm protocol.

## 11. Điều gì xảy ra nếu tiếp tục duyệt sau ServiceConfigurationError?

Theo Javadoc Java 17, sau khi Iterator.hasNext() hoặc next() ném ServiceConfigurationError, những lời gọi tiếp theo **thử tốt nhất** để tìm provider còn lại, nhưng **không có bảo đảm phục hồi**. Có thể một lỗi ở tệp cấu hình làm iterator không tiến được hoặc nhiều lỗi xuất hiện liên tiếp.

Vì thế:

- **SPI bắt buộc** như xác thực, policy hoặc logic mà sự đầy đủ của tập provider là điều kiện an toàn: thường nên fail closed, không chạy với tập thiếu.
- **Plugin tùy chọn** có thể cho phép degraded mode nếu host định nghĩa ranh giới lỗi, giới hạn số lần thử/steps, log provider bị từ chối và báo trạng thái partial.
- **Không dùng while(iterator.hasNext()) với hasNext ngoài try**: lỗi parse vẫn có thể lọt.
- **Không gọi iterator.next() vô hạn sau lỗi** với kỳ vọng tự động skip.
- **Không gọi reload() như cách sửa descriptor**. reload() xóa cache ServiceLoader, không tự sửa JAR, module descriptor, constructor hay dependency.
- **Không đổi nguồn JAR/loader trong khi cùng một iterator đang được sử dụng** rồi coi kết quả là có thể dự đoán. Khi deploy lại, tạo phiên loading mới đúng lifecycle.

Nếu có thể tổ chức plugin theo artifact độc lập và có plugin manager kiểm soát class loader, cách ly vùng discovery theo gói giúp một JAR sai bớt ảnh hưởng plugin khác. Nhưng giải pháp này cần quản lý parent delegation và SPI identity, không chỉ tạo tùy tiện nhiều URLClassLoader.

## 12. Các lỗi chẩn đoán thường gặp

| Triệu chứng | Sai lầm dễ mắc | Cách sửa |
| --- | --- | --- |
| Class có trong JAR nhưng NO_PROVIDER | Tưởng có .class là ServiceLoader sẽ tự scan implementation | Kiểm tra META-INF/services hoặc module provides |
| ServiceConfigurationError do wrong class name | Chỉ nhìn constructor của class đúng trong source | Xem **dòng descriptor thực tế** đang gọi tới class nào |
| Thấy "not a subtype" dù implements ở source | Coi tên class trùng là type identity | So sánh class loader/module và API JAR runtime |
| Constructor nhận một tham số, không có public no-arg | Cho rằng Java tự sinh default constructor | Thêm explicit public no-arg hoặc chuyển sang explicit module factory nếu phù hợp |
| Constructor throw nhưng log không có nguyên nhân | Catch Error rồi chỉ in getMessage() | Log stack trace và getCause() |
| Provider module không được tìm thấy | Chỉ kiểm tra JAR có trên --module-path | Kiểm tra module đã resolve và service loader scope |
| Named consumer thiếu uses | Chỉ sửa provides ở provider | Thêm uses ở consumer named module |
| Factory.provider() trả null | Cho rằng return null nghĩa là không có provider | Đây là lỗi cấu hình/khởi tạo; dùng cơ chế capability selection khác |
| Module factory class không implements SPI | Áp quy tắc classpath lên explicit named module | Kiểm tra provider() public static no-arg trả subtype của SPI |
| Việc compile module-info lỗi | Cố bắt ServiceConfigurationError ở runtime | Sửa JLS module declarations trước build |
| Iterator không tiến sau khi catch | Vòng retry vô hạn | Dừng/giới hạn; đừng hứa hồi phục |
| reload() rồi vẫn lỗi | Cache được xóa nhưng artifact sai nguyên trạng | Sửa JAR/module và tạo loader phù hợp |
| Provider method chạy nhưng business method fail | Gộp lỗi business vào lỗi descriptor | Tách giai đoạn discovery khỏi invoke |

Một trường hợp ít gặp nhưng quan trọng: nếu ClassLoader.getResources tìm service descriptor qua **HTTP URL** và server trả **200 OK kèm trang HTML cho một đường dẫn không tồn tại** thay vì 404, ServiceLoader có thể cố parse HTML thành provider names và phát sinh ServiceConfigurationError. Đây là lý do phải kiểm tra nguồn resource, không chỉ nội dung JAR trong môi trường class loader dùng URL từ mạng.

## 13. Checklist điều tra nhanh

Trước khi đóng một lỗi ServiceConfigurationError, hãy trả lời được:

1. **Đây là classpath, automatic module hay explicit named module?**
2. **Service type chính xác** là class/interface nào; ClassLoader và Module của nó là gì?
3. **Registration đến từ đâu**: META-INF/services/<SPI> hay provides trong module-info?
4. **Nếu classpath**: descriptor có đúng tên, vị trí, UTF-8 và tên class không; class có thật trong JAR runtime không?
5. **Nếu JPMS**: consumer có uses, provider có provides, module đã resolve, loader/layer đúng không?
6. **Cách khởi tạo**: public no-arg constructor hay provider() đúng bối cảnh? Có ném exception/trả null không?
7. **Subtype và dependency**: provider có assignable với service Class object runtime không, thiếu library hoặc ABI nào không?
8. **Stage lỗi**: ServiceLoader.load, hasNext, next, Provider.get hay business invoke?
9. **Cause/log**: đã ghi tên service/provider, artifact, module, class loader, stack trace và cause chain chưa?
10. **Khắc phục và regression test**: đã sửa artifact/config đúng chặng và chạy lại bằng classpath/module graph sạch chưa?

**Bài tập củng cố:** (a) đổi classpath-lab descriptor good thành demo.providers.DoesNotExist rồi so sánh kết quả với typo; (b) sửa NeedsArgument để có public no-arg constructor và kiểm tra no-ctor chuyển thành FOUND; (c) bật --trace để phân loại lỗi ctor throw và wrong-type; (d) trong module-lab bỏ uses khỏi consumer rồi bổ sung lại; (e) thay Factory.provider() trả null rồi sửa; (f) chạy service lookup bằng một loader không nhìn thấy descriptor và giải thích vì sao không thấy provider **không nhất thiết** là ServiceConfigurationError.

## 14. Tài liệu chuẩn và kết luận

- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): mục *Deploying service providers*, *Errors*, iterator(), stream(), load(ModuleLayer,...), reload().
- [Java SE 17 — ServiceConfigurationError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html): loại Error và mục đích.
- [Java SE 17 — ServiceLoader.Provider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): type(), get() và lỗi tạo instance.
- [JLS 17 — Module Declarations / Service Provision](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4): quy tắc provides và provider method.
- [Java SE 17 — jar](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) và [javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): kiểm tra nội dung artifact, constructor và API.

**Kết luận:** ServiceConfigurationError là **tín hiệu lỗi ở ranh giới khám phá, nạp hoặc khởi tạo provider**, không phải một chẩn đoán nguyên nhân duy nhất. Muốn điều tra đúng, trước hết xác định **classpath descriptor hay JPMS registration**, sau đó đối chiếu đúng class loader/module, kiểm tra subclass/constructor hoặc provider method, đọc cause chain và tái hiện bằng một artifact tối giản. Không thấy provider, provider tạo thất bại và provider chạy lỗi là **ba trạng thái khác nhau**; phân biệt chúng là điều kiện để sửa đúng và tránh lỗi lặp lại trong hệ thống plugin.