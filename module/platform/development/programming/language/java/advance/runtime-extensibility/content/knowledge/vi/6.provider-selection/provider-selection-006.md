# Xử lý provider lỗi và giới hạn của việc tiếp tục duyệt sau lỗi cấu hình

Trong hệ thống Java cho phép mở rộng lúc chạy, ServiceLoader giúp tìm các provider triển khai một SPI (Service Provider Interface). Khi một provider hỏng, host thường muốn giữ các provider còn lại hoạt động. Điều này có thể thực hiện trong một số tình huống, nhưng **không có cam kết rằng cứ bắt ServiceConfigurationError rồi gọi tiếp Iterator.next() là bỏ qua được provider lỗi**.

Bài này giải thích ranh giới phục hồi của ServiceLoader trên classpath, so sánh chiến lược dừng ngay với thử tiếp có giới hạn, cung cấp thí nghiệm Java 17+ và hướng dẫn chọn chính sách cho hệ thống plugin thực tế.

## 1. Ba dạng lỗi phải phân biệt khi chọn provider

Một vòng lựa chọn provider thường trải qua ba chặng:

1. **Phát hiện cấu hình (discovery):** tìm file META-INF/services/<tên đầy đủ của SPI>, đọc và phân tích danh sách tên provider.
2. **Nạp và khởi tạo (loading/instantiation):** phân giải class, kiểm tra có triển khai đúng SPI và tạo đối tượng provider.
3. **Dùng provider (execution):** gọi phương thức nghiệp vụ, mở resource, kết nối dịch vụ hoặc xử lý dữ liệu.

| Tình huống | Lỗi có thể quan sát | Bản chất |
| --- | --- | --- |
| Descriptor có cú pháp sai hoặc không đọc được | ServiceConfigurationError trong quá trình duyệt | Cấu hình dịch vụ không hợp lệ |
| Descriptor chỉ đến class không tồn tại hoặc không thuộc SPI | ServiceConfigurationError | Khai báo provider không thể nạp/dùng được |
| Provider classpath không có public constructor không tham số | ServiceConfigurationError | Không đáp ứng hợp đồng khởi tạo |
| Constructor của provider ném lỗi | Thường là ServiceConfigurationError có cause liên quan | Không tạo được đối tượng provider |
| Provider tạo thành công nhưng process() ném RuntimeException | RuntimeException của chính implementation, trừ khi nó tự ném loại khác | Lỗi trong lúc dùng provider, nằm sau bước discovery |
| Không có descriptor cho service yêu cầu | Có thể duyệt được 0 provider, không mặc nhiên có ServiceConfigurationError | Không phát hiện provider được đăng ký |

**ServiceConfigurationError là một lớp con của java.lang.Error**, không phải Exception. Việc catch (Exception ex) không bắt được nó. Ta có thể bắt **đúng loại ServiceConfigurationError** ở biên duyệt SPI nhằm xử lý lỗi cấu hình dự kiến, nhưng không nên bắt rộng Throwable hoặc Error rồi coi tất cả là lỗi plugin bình thường: VirtualMachineError, ThreadDeath và các sự cố nghiêm trọng không phù hợp với chính sách "bỏ qua và thử tiếp".

Một provider chạy được nhưng trả kết quả không đạt yêu cầu kinh doanh không trở thành "provider lỗi cấu hình". Việc lọc theo capability, priority, input format hoặc health check phải được thiết kế riêng, sau khi xác định provider đã nạp được.

## 2. Hợp đồng của ServiceLoader về phục hồi sau lỗi

Tài liệu Java SE 17 nêu rõ:

- ServiceLoader.load(...) tạo đối tượng loader, nhưng tìm kiếm và khởi tạo provider phần lớn là **lazy**. Chỉ gọi load(...) chưa chứng minh mọi provider hợp lệ.
- Khi dùng ServiceLoader.iterator(), cả **hasNext() và next()** có thể ném ServiceConfigurationError nếu lỗi xảy ra trong quá trình định vị, nạp hoặc khởi tạo provider.
- Nếu một lần duyệt gây lỗi, các lần gọi tiếp trên iterator sẽ **nỗ lực tốt nhất (best effort)** để định vị/khởi tạo provider tiếp theo. **Không thể bảo đảm nói chung rằng nó sẽ phục hồi.**
- Với ServiceLoader.stream(), lỗi cũng có thể xuất hiện ở các thao tác thực sự định vị hoặc nạp provider, kể cả khi chúng xảy ra trong terminal operation.

Hệ quả trực tiếp là code sau không có cơ sở để chạy an toàn:

~~~java
// Phản ví dụ: KHÔNG dùng trong chương trình cần tính đúng đắn.
while (iterator.hasNext()) {
    try {
        Service provider = iterator.next();
        use(provider);
    } catch (ServiceConfigurationError error) {
        // "Bỏ qua rồi đi tiếp" không được API bảo đảm.
    }
}
~~~

Có ít nhất ba vấn đề. Thứ nhất, **hasNext() nằm ngoài try**, nên lỗi từ bước đọc cấu hình vẫn thoát ra ngoài. Thứ hai, lỗi có thể khiến iterator không tiến được, dẫn đến lặp lại lỗi hoặc kết thúc bất ngờ. Thứ ba, việc nuốt lỗi làm host báo rằng plugin hợp lệ trong khi hệ thống chỉ chạy được một phần.

Một phiên bản sửa đúng phạm vi bắt lỗi vẫn phải có **giới hạn số lần thử**, báo cáo lỗi và phương án dừng. Không có giới hạn thì vòng lặp có thể kẹt mãi ở cùng một lỗi nếu iterator không tiến.

## 3. Hai chính sách xử lý chính

**Dừng ngay (fail fast / fail closed):** một lỗi ServiceConfigurationError khiến quá trình nạp tập provider bị dừng; host ghi nhận nguyên nhân và từ chối bật chức năng phụ thuộc vào tập provider đó. Chọn khi provider là thành phần bắt buộc, danh sách phải đầy đủ, hoặc sai cấu hình làm kết quả không đáng tin.

**Thử tiếp có giới hạn (bounded best effort):** host ghi lỗi, thử gọi lại iterator tối đa một số bước/lỗi định trước, vẫn xử lý những provider nạp được, rồi kết thúc bằng trạng thái đầy đủ hoặc một phần. Chọn khi plugin là tùy chọn, có thể bị vô hiệu hóa độc lập, và sản phẩm chấp nhận bỏ qua plugin bị lỗi. Đây là **nỗ lực phục hồi**, không phải lời hứa rằng mọi provider hợp lệ phía sau một provider hỏng đều được tìm thấy.

| Yêu cầu hệ thống | Chính sách phù hợp | Điều phải kiểm tra |
| --- | --- | --- |
| Phân quyền, xác thực, chính sách bảo mật hoặc bộ xử lý bắt buộc | Fail closed | Không thể coi tập provider thiếu thành phần là hợp lệ |
| Plugin trang trí/tính năng tùy chọn | Bounded best effort nếu có kiểm soát | Ghi rõ plugin bị từ chối, không bỏ qua âm thầm |
| Nhiều JAR plugin cài độc lập | Khám phá và xác thực từng gói, tách loader khi kiến trúc cho phép | Một JAR lỗi không làm che khuất các gói khác |
| Có thể cấu hình lại và triển khai mới | Sửa artifact/descriptor rồi tạo phiên duyệt mới có kiểm chứng | reload() không tự sửa lỗi cũ |
| Chức năng có thứ tự ưu tiên provider | Quyết định rõ có cho phép fallback hay không | Không suy rằng provider bị hỏng chỉ bị bỏ qua một lần |

## 4. Thí nghiệm Java 17+: provider tốt, provider hỏng constructor và provider tốt phía sau

Mục tiêu của lab là quan sát **điểm phát sinh lỗi** và chứng minh rằng kết quả fail-fast có thể xác định, còn kết quả thử tiếp chỉ là best effort.

Cấu trúc thư mục từ gốc lab/:

~~~text
lab/
├── src/
│   ├── api/demo/spi/Processor.java
│   ├── providers/demo/providers/Alpha.java
│   ├── providers/demo/providers/Broken.java
│   ├── providers/demo/providers/Omega.java
│   └── host/demo/host/Run.java
├── descriptors/
│   ├── good/META-INF/services/demo.spi.Processor
│   └── broken/META-INF/services/demo.spi.Processor
└── build/                        (được tạo bởi lệnh build)
~~~

### 4.1. Định nghĩa SPI

File **src/api/demo/spi/Processor.java**:

~~~java
package demo.spi;

public interface Processor {
    String id();
    String process(String value);
}
~~~

Interface là hợp đồng được host cung cấp. Bản Java compiler của provider tham chiếu đúng artifact API, và lúc chạy host đặt API lên classpath chung.

### 4.2. Provider tốt đầu tiên

File **src/providers/demo/providers/Alpha.java**:

~~~java
package demo.providers;

import demo.spi.Processor;

public final class Alpha implements Processor {
    public Alpha() {}

    @Override
    public String id() {
        return "alpha";
    }

    @Override
    public String process(String value) {
        return "A:" + value;
    }
}
~~~

### 4.3. Provider có constructor ném lỗi

File **src/providers/demo/providers/Broken.java**:

~~~java
package demo.providers;

import demo.spi.Processor;

public final class Broken implements Processor {
    public Broken() {
        throw new IllegalStateException("constructor failed");
    }

    @Override
    public String id() {
        return "broken";
    }

    @Override
    public String process(String value) {
        return "B:" + value;
    }
}
~~~

Broken đáp ứng yêu cầu có **public constructor không tham số**, nhưng constructor cố tình ném lỗi. Đây là lỗi **khởi tạo provider**, không phải lỗi phương thức process. Đối với cấu hình provider classpath, ServiceLoader sẽ phản ánh lỗi khởi tạo qua ServiceConfigurationError; exception nguyên gốc có thể thấy trong chuỗi cause.

### 4.4. Provider tốt ở phía sau

File **src/providers/demo/providers/Omega.java**:

~~~java
package demo.providers;

import demo.spi.Processor;

public final class Omega implements Processor {
    public Omega() {}

    @Override
    public String id() {
        return "omega";
    }

    @Override
    public String process(String value) {
        return "Z:" + value;
    }
}
~~~

### 4.5. Hai file descriptor độc lập

File **descriptors/good/META-INF/services/demo.spi.Processor**:

~~~text
demo.providers.Alpha
demo.providers.Omega
~~~

File **descriptors/broken/META-INF/services/demo.spi.Processor**:

~~~text
demo.providers.Alpha
demo.providers.Broken
demo.providers.Omega
~~~

Mỗi lần chạy chỉ đặt **một** JAR chứa descriptor lên classpath. Descriptor đúng tên SPI; nó liệt kê provider bằng tên đầy đủ của class, một tên mỗi dòng. Gói broken chứa ba tên theo thứ tự Alpha → Broken → Omega; việc Broken thất bại có thể ảnh hưởng đến khả năng tìm Omega tùy trạng thái iterator và cách nó gặp lỗi.

### 4.6. Host: chế độ dừng ngay và thử tiếp có giới hạn

File **src/host/demo/host/Run.java**:

~~~java
package demo.host;

import demo.spi.Processor;
import java.util.Iterator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Run {
    private static final int MAX_STEPS = 8;
    private static final int MAX_CONFIG_ERRORS = 2;

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: Run strict|bounded");
        }

        ServiceLoader<Processor> loader = ServiceLoader.load(Processor.class);

        switch (args[0]) {
            case "strict" -> strict(loader);
            case "bounded" -> bounded(loader);
            default -> throw new IllegalArgumentException(
                    "Unknown mode: " + args[0]);
        }
    }

    private static void use(Processor provider) {
        try {
            System.out.println(
                    "USE " + provider.id() + " -> " + provider.process("x"));
        } catch (RuntimeException ex) {
            System.out.println("PROCESS_ERROR: " + provider.id());
        }
    }

    private static void strict(ServiceLoader<Processor> loader) {
        try {
            for (Processor provider : loader) {
                use(provider);
            }
            System.out.println("DONE");
        } catch (ServiceConfigurationError error) {
            System.out.println("STOP CONFIG_ERROR");
            // Trong ứng dụng thật: log cả error và getCause().
        }
    }

    private static void bounded(ServiceLoader<Processor> loader) {
        Iterator<Processor> iterator = loader.iterator();
        int configErrors = 0;

        for (int step = 0; step < MAX_STEPS; step++) {
            Processor provider;
            try {
                // CẢ hasNext lẫn next đều có thể báo lỗi cấu hình.
                if (!iterator.hasNext()) {
                    System.out.println("DONE");
                    return;
                }
                provider = iterator.next();
            } catch (ServiceConfigurationError error) {
                configErrors++;
                System.out.println("CONFIG_ERROR #" + configErrors);

                if (configErrors >= MAX_CONFIG_ERRORS) {
                    System.out.println("STOP ERROR_LIMIT");
                    return;
                }
                continue; // Chỉ thử lại; KHÔNG bảo đảm bỏ qua được lỗi.
            }

            use(provider);
        }

        System.out.println("STOP STEP_LIMIT");
    }
}
~~~

Đặc điểm cần quan sát trong code:

- try/catch của **strict** bao cả vòng for; do đó lỗi phát sinh ở iterator.hasNext() lẫn iterator.next() đều được bắt.
- try/catch của **bounded** bao cả hai lời gọi iterator; nó không bắt chung mọi Error.
- MAX_CONFIG_ERRORS chặn việc lặp mãi khi iterator tiếp tục báo lỗi; MAX_STEPS là **giới hạn thứ hai** để tránh vòng duyệt quá dài ngay cả khi không có cấu hình lỗi liên tiếp. Đây là ví dụ cho tập plugin nhỏ, không phải ngưỡng mặc định tối ưu cho mọi hệ thống.
- Lỗi từ process() được phân loại riêng thành PROCESS_ERROR. Một provider khởi tạo thành công nhưng xử lý dữ liệu thất bại không được phép làm ta hiểu sai là lỗi descriptor.
- Code in thông điệp ngắn để stdout ổn định. Trong ứng dụng thật phải log exception, nguyên nhân gốc, thông tin artifact và quyết định vô hiệu hóa provider.

**Giới hạn có chủ ý:** Nếu provider.id() tự ném RuntimeException trong catch của use(), biểu thức provider.id() ở nhánh catch cũng có thể ném lần nữa. Trong ứng dụng thật, nên lấy ID đã xác minh từ metadata/registration trước, không phụ thuộc vào việc gọi phương thức của chính provider đang lỗi. Các provider của lab đều có id() ổn định để tập trung vào ServiceConfigurationError.

### 4.7. Build và chạy từ JAR phát hành

Từ thư mục lab/, dùng JDK 17+ và shell bash/POSIX:

~~~bash
mkdir -p build/api build/providers build/host dist

javac -encoding UTF-8 -d build/api src/api/demo/spi/Processor.java
jar --create --file build/api.jar -C build/api .

javac -encoding UTF-8 -cp build/api.jar -d build/providers src/providers/demo/providers/Alpha.java src/providers/demo/providers/Broken.java src/providers/demo/providers/Omega.java

javac -encoding UTF-8 -cp build/api.jar -d build/host src/host/demo/host/Run.java

jar --create --file dist/good.jar -C build/providers . -C descriptors/good .
jar --create --file dist/broken.jar -C build/providers . -C descriptors/broken .

java -cp "build/host:build/api.jar:dist/good.jar" demo.host.Run strict
java -cp "build/host:build/api.jar:dist/broken.jar" demo.host.Run strict
java -cp "build/host:build/api.jar:dist/broken.jar" demo.host.Run bounded
~~~

Trên Windows khi gọi Java trực tiếp từ PowerShell/CMD, dấu phân cách classpath là **;** thay cho **:**. Cú pháp mkdir -p và cách xuống dòng ở trên dành cho bash.

Mỗi JAR có đầy đủ class của Alpha, Broken và Omega; sự khác biệt duy nhất giữa hai bản nằm ở **danh sách tên provider trong META-INF/services**. Điều này tách rõ tác động của service configuration khỏi tác động của việc biên dịch các class.

Lệnh kiểm tra JAR:

~~~bash
jar --list --file dist/good.jar
jar --list --file dist/broken.jar
~~~

Bạn cần thấy entry **META-INF/services/demo.spi.Processor** và các file .class dưới demo/providers. Chỉ liệt kê class có mặt trong JAR chưa đủ: ServiceLoader chỉ biết các provider được khai báo cho đúng SPI trong descriptor.

## 5. Diễn giải kết quả thực nghiệm

**Chạy strict với good.jar** cho stdout chính xác:

~~~text
USE alpha -> A:x
USE omega -> Z:x
DONE
~~~

**Chạy strict với broken.jar** cho stdout chính xác:

~~~text
USE alpha -> A:x
STOP CONFIG_ERROR
~~~

Alpha được tạo và xử lý trước. Khi tới Broken, constructor ném IllegalStateException; việc iterator cố tạo provider đó thất bại và vòng strict dừng. Omega có khai báo trong file nhưng **không được dùng** ở lượt strict, bởi vì host quyết định kết thúc ngay sau lỗi cấu hình.

**Chạy bounded với broken.jar** có thể cho kết quả minh họa sau ở một runtime Java 17:

~~~text
USE alpha -> A:x
CONFIG_ERROR #1
USE omega -> Z:x
DONE
~~~

Ở tình huống đó iterator đã tiến qua Broken và tiếp tục tìm được Omega. **Không được coi bốn dòng trên là đầu ra cam kết trên mọi runtime, mọi loại lỗi hoặc mọi file cấu hình.** Hợp đồng API chỉ nói best effort. Với lỗi không thể vượt qua, có thể xảy ra nhiều lỗi liên tiếp; khi chạm MAX_CONFIG_ERRORS, chương trình in STOP ERROR_LIMIT. Nếu không tới được cuối trong MAX_STEPS, chương trình in STOP STEP_LIMIT. Cả hai nhánh dừng này đều phải được xử lý như trạng thái tập provider **không đầy đủ**.

Điều có thể khẳng định độc lập với chi tiết thực thi là: bounded sẽ không thử nhiều hơn MAX_STEPS vòng lặp, sẽ dừng sau MAX_CONFIG_ERRORS lỗi cấu hình mà nó đã bắt, và sẽ không đưa ra lời hứa rằng provider phía sau Broken chắc chắn được nạp.

Một điều tinh tế: **hasNext() có thể cũng báo lỗi** (ví dụ khi đang đọc file descriptor bị hỏng), chứ không chỉ next() khi tạo Broken. Trong vài trường hợp, cả việc xác định "còn provider nào không?" cũng chưa thể hoàn tất. Bởi vậy không thể bảo đảm luôn có một provider cụ thể để "skip" sau khi gặp ServiceConfigurationError.

## 6. Chọn provider và cơ chế fallback: phần nào kiểm soát được?

Nhiều host không cần mọi provider; chúng chỉ muốn một implementation phù hợp, chẳng hạn theo ID, media type hoặc capability. Có ba lựa chọn khác nhau:

**Lựa chọn sau khi khởi tạo:** duyệt từng provider và gọi id() hoặc supports(...), rồi chọn provider đầu tiên đáp ứng điều kiện. Cách này có thể gây side effect trong constructor của những provider đứng trước, và có thể bị chặn bởi lỗi cấu hình của provider chưa cần dùng.

**Lọc theo metadata của provider type:** ServiceLoader.stream() trả các ServiceLoader.Provider<S>. Có thể đọc Provider.type() để xem kiểu khai báo rồi mới Provider.get() để khởi tạo; nhờ đó đôi khi tránh khởi tạo provider không được chọn. Tuy nhiên, chính giai đoạn định vị và phân giải type vẫn có thể ném ServiceConfigurationError. stream().filter(...).findFirst() **không biến một tập descriptor hỏng thành tập hợp luôn lọc được an toàn**.

**Đọc registry/manifest do host kiểm soát trước khi đưa JAR vào loader:** khi mỗi plugin có metadata được xác minh độc lập, host có thể quyết định nên tạo loader và nạp plugin nào. Đây là ranh giới kiểm soát rõ hơn cho sản phẩm có yêu cầu chọn provider theo phiên bản, độ ưu tiên, quyền hạn và khả năng tương thích.

Ví dụ chọn provider theo **tên class** bằng stream() chỉ mang tính minh họa (không phải chương trình độc lập):

~~~java
ServiceLoader<Processor> loader = ServiceLoader.load(Processor.class);

try {
    Processor selected = loader.stream()
            .filter(p -> p.type().getName().equals("demo.providers.Omega"))
            .findFirst()
            .orElseThrow()
            .get();
    System.out.println(selected.process("x"));
} catch (ServiceConfigurationError error) {
    // Việc quét metadata hoặc Provider.get() vẫn có thể lỗi.
    // Ghi nhận tập plugin không hợp lệ thay vì giả định đã lọc hết.
}
~~~

Đoạn code giả định đã có interface Processor và class tương ứng của lab. Nếu không tìm thấy provider thì orElseThrow() ném NoSuchElementException; đây là tình huống khác ServiceConfigurationError. Tương tự, nếu selected.process("x") ném RuntimeException thì đó là lỗi thực thi implementation, không mặc nhiên được catch trên bắt.

**Không dùng stream().findFirst() như một cơ chế "fallback tự động" sau lỗi cấu hình.** Nếu việc lấy provider đầu tiên thất bại, terminal operation có thể kết thúc bằng exception; không có cam kết tự loại provider lỗi rồi thử phần tử tiếp theo.

## 7. Khi nào được tiếp tục, khi nào nên dừng?

Dưới đây là cách phân ranh theo mức rủi ro:

| Kết quả quan sát | Đánh giá | Hành động |
| --- | --- | --- |
| Một provider tùy chọn ném RuntimeException lúc xử lý đầu vào, nhưng host đã biết ID và contract của nó | Lỗi nghiệp vụ/vòng đời riêng của provider | Có thể đánh dấu provider unhealthy, dùng fallback **đã định nghĩa**, log và giới hạn retry |
| ServiceConfigurationError khi duyệt SPI bắt buộc | Cấu hình tập provider không tin cậy | Dừng khởi tạo chức năng, báo lỗi cấu hình và yêu cầu sửa artifact |
| ServiceConfigurationError trong tập plugin tùy chọn | Có thể còn provider dùng được, nhưng iterator không hứa sẽ hồi phục | Chỉ thử tiếp nếu chính sách chấp nhận degraded mode, có giới hạn và có thông báo |
| Nhiều lỗi cấu hình liên tiếp, hoặc lặp lại lỗi giống nhau | Có nguy cơ không tiến được | Dừng theo error budget/step budget; đánh dấu discovery không hoàn chỉnh |
| Lỗi class linkage/version như NoClassDefFoundError, NoSuchMethodError | Có thể do tập JAR/class loader không tương thích | Kiểm tra dependency/API/classpath; không bắt Error đại trà để xem như lỗi thông thường |
| Mất tính toàn vẹn, chữ ký, quyền hoặc chính sách bảo mật của plugin | Không chỉ là vấn đề ServiceLoader | Từ chối nạp theo chính sách bảo mật, không fallback qua plugin tùy tiện |

Đặc biệt đối với hệ thống có nhiều plugin từ các nhóm khác nhau, **"tiếp tục sau lỗi" không có nghĩa là "đã kiểm tra hết danh sách"**. Báo cáo kết quả nên phân biệt loaded, rejected, failed discovery và not examined. Một trạng thái SUCCESS chung khi chưa xác định được đầy đủ provider thường gây hiểu nhầm.

Nếu business contract bắt buộc đúng một implementation có khả năng xử lý yêu cầu, quá trình chọn nên trả về kết quả có cấu trúc như selected, unsupported, invalid configuration hoặc ambiguous selection. Không nên để một catch rỗng quyết định ngầm rằng thiếu provider là hợp lệ.

## 8. Mẫu xử lý lỗi cho host thực tế

Bộ lab dùng System.out để dễ đọc. Khi triển khai, tổ chức các bước như sau:

1. **Định danh artifact và nguồn nạp:** log service, plugin ID/version nếu có metadata, đường dẫn JAR, hash/nguồn phát hành, class loader được chọn.
2. **Xác minh trước khi nạp:** kiểm tra file tồn tại, descriptor đúng tên, phiên bản API, dependencies, điều kiện tương thích. Static preflight không thay được runtime discovery, nhưng giúp phát hiện nhiều lỗi packaging sớm.
3. **Quyết định trước chính sách bắt lỗi:** SPI bắt buộc → fail closed; SPI tùy chọn → best effort có giới hạn và trạng thái partial.
4. **Bắt lỗi tại đúng biên:** ServiceConfigurationError quanh hasNext()/next(); lỗi process() quanh lời gọi provider; lỗi I/O và timeout theo API riêng; tránh catch Throwable.
5. **Lưu cause đầy đủ:** ghi stack trace và getCause() khi có, kèm loại giai đoạn. Không chỉ ghi một nhãn CONFIG_ERROR rồi xóa thông tin.
6. **Dừng theo ngân sách rõ ràng:** tổng số lỗi cấu hình, số bước duyệt và deadline tổng (nếu cần). Ngân sách số bước trong demo không chặn được một lời gọi đơn lẻ bị treo; production có thể cần cách ly tiến trình hoặc timeout ở ranh giới thích hợp.
7. **Không sử dụng provider đã thất bại khởi tạo:** provider chưa tạo đối tượng hợp lệ không thể được thêm vào registry. Với provider đã khởi tạo nhưng không qua health check, đóng tài nguyên và hủy đăng ký theo lifecycle.
8. **Trả kết quả startup có mức độ hoàn chỉnh:** fully ready / degraded / failed, các provider đã chấp nhận hoặc bị từ chối, lý do và hành động khắc phục.

Một thiết kế plugin loader độc lập cho mỗi gói có thể làm phạm vi ảnh hưởng của lỗi nhỏ hơn: mỗi JAR được kiểm tra, nạp và theo dõi riêng. Tuy nhiên, chỉ việc tạo nhiều URLClassLoader chưa đủ để cách ly nếu parent loader vẫn nhìn thấy mọi plugin, vì class/resource lookup vẫn có thể đi qua parent. Host phải kiểm soát **classpath của parent, quyền sở hữu SPI, dependency và quy tắc delegation**. Đồng thời không nên đóng loader ngay khi còn provider đang hoạt động; cần giữ loader sống tới khi plugin dừng, hủy callback và giải phóng tài nguyên.

Với mã của bên thứ ba **không tin cậy**, class loader không phải sandbox bảo mật. Nếu plugin có thể thực thi mã tùy ý, hãy cân nhắc tách tiến trình và giới hạn quyền. Việc catch ServiceConfigurationError không thể bảo đảm tính an toàn của JVM khi plugin có side effect ngay lúc khởi tạo.

## 9. Những hành vi dễ hiểu sai của ServiceLoader

### 9.1. Caching và reload()

ServiceLoader duy trì cache các provider đã nạp; lần iterator() tiếp theo có thể trả lại các instance đã cache trước khi tiếp tục tìm những provider chưa nạp. Vì thế thử lại một iteration mới với **cùng ServiceLoader** không đồng nghĩa "bắt đầu từ trạng thái sạch". Cần phân biệt retry để quan sát với retry sau sửa cấu hình.

Gọi reload() xóa cache provider của ServiceLoader nhưng **không sửa file descriptor/JAR lỗi**, không tự unload class, cũng không đảm bảo lỗi không lặp lại. Các iterator hoặc stream bắt đầu trước reload() cần bị bỏ; việc dùng iterator cũ sau reload() có thể ném ConcurrentModificationException. Đừng gọi reload() trong catch mỗi khi gặp ServiceConfigurationError: cách đó có thể chỉ khiến host quay lại chính cấu hình hỏng.

Đối với hot reload plugin, cần bảo đảm loader cũ không còn thread, callback, reference hoặc resource sống; rồi tạo loader/ServiceLoader mới cho artifact đã xác minh. Đây là công việc lifecycle, không phải chức năng chữa lỗi của ServiceLoader.

### 9.2. Error xuất hiện muộn vì lazy loading

Câu lệnh sau chưa kiểm chứng được toàn bộ tập provider:

~~~java
ServiceLoader<Processor> loader = ServiceLoader.load(Processor.class);
System.out.println("ServiceLoader created");
~~~

Một phần công việc chỉ xảy ra khi iterator.hasNext(), iterator.next(), stream terminal operation hoặc Provider.get() được gọi. Nếu startup check chỉ gọi load(...) rồi báo thành công, hệ thống có thể thất bại ở request đầu tiên.

### 9.3. Cấu hình descriptor và lỗi cú pháp

Trong classpath, descriptor phải nằm ở **META-INF/services/<tên đầy đủ SPI>** và chứa tên binary hợp lệ của các implementation. Lỗi đọc file, sai format, sai tên class, class không phù hợp hoặc thiếu constructor có thể dẫn đến ServiceConfigurationError trong quá trình duyệt. Đừng suy diễn rằng mọi lỗi đều xảy ra khi next() tạo đối tượng: đọc descriptor có thể phát sinh lỗi ngay tại hasNext().

Nếu descriptor có dòng sai, một implementation hợp lệ ở các dòng sau **không được bảo đảm** sẽ được duyệt tới. Đây chính là lý do phương án bounded phải có nhánh thất bại và không hứa recovery hoàn toàn.

### 9.4. Khác biệt giữa classpath và module path

Trên classpath, provider thường được khai báo bằng META-INF/services; provider class cần public constructor không tham số để ServiceLoader có thể khởi tạo. Trên JPMS module path, module descriptor dùng uses/provides; provider method và quy tắc khác cũng có thể xuất hiện. Vì vậy khi log thiếu constructor, cần kiểm tra **chế độ triển khai thực tế** trước khi áp dụng cách sửa cho classpath.

### 9.5. Không thay đổi loader khi nhiều thread đang duyệt

Các instance ServiceLoader **không an toàn cho nhiều thread truy cập đồng thời**. Không chia sẻ một ServiceLoader đang reload/iterate giữa nhiều luồng rồi xem mọi ConcurrentModificationException là lỗi của provider. Nếu cần registry dùng chung, tạo snapshot provider đã xác minh và quản lý việc thay snapshot có đồng bộ/lifecycle rõ ràng.

## 10. Bảng chẩn đoán lỗi và hành động tương ứng

| Dấu hiệu | Kiểm tra ngay | Hành động |
| --- | --- | --- |
| 0 provider mà không có ServiceConfigurationError | Đúng tên SPI/descriptor? JAR có nằm trong classpath/loader? | Sửa đăng ký và classpath |
| Error ném từ hasNext() | Descriptor hỏng, đọc resource gặp lỗi, loader không truy cập file | Xem stack trace/đường dẫn; tránh vòng while có hasNext ngoài try |
| Error ném từ next() | Class provider, kiểu SPI, public no-arg constructor, dependency, constructor failure | Sửa class/đóng gói/API compatibility; log cause |
| Chạy được Alpha rồi không thấy Omega | Provider giữa đường gây lỗi; host fail fast hoặc iterator không phục hồi | Phân biệt chính sách dừng với khả năng phục hồi của API |
| Một lỗi lặp lại mãi khi thử next | Iterator không tiến/đang gặp lỗi cấu hình dai dẳng | Dừng theo max errors/max steps; sửa gói thay vì retry vô hạn |
| Provider nạp được nhưng process thất bại | Resource riêng, runtime state, input, I/O/remote service | Bắt lỗi riêng của provider, đánh dấu unhealthy hoặc dùng fallback đã định nghĩa |
| Sau reload vẫn lỗi y hệt | Gói cấu hình/JAR chưa được sửa; loader cũ còn được dùng | Kiểm tra artifact, tạo phiên nạp mới đúng lifecycle |
| stream().filter(...).findFirst() thất bại trước khi trả provider mong muốn | Lỗi xảy ra trong lazy discovery hoặc type loading | Bắt ServiceConfigurationError ở biên chọn; không tin rằng filter bỏ qua lỗi |
| ClassCastException hoặc ServiceConfigurationError "not a subtype" | SPI bị nạp bởi hai class loader hoặc implementation thực sự sai kiểu | Cố định SPI chung, kiểm tra class loader/dependency version |
| NoClassDefFoundError / NoSuchMethodError trong plugin | Dependency thiếu hoặc không khớp phiên bản runtime | Kiểm tra dependency graph và class thực sự được nạp |

Để chẩn đoán, dùng lệnh jar --list --file plugin.jar xem entry META-INF/services và các .class; dùng javap -public -classpath plugin.jar <tên class> để xem chữ ký constructor. Khi nghi ngờ xung đột, kiểm tra artifact của SPI tại runtime và class loader định nghĩa mỗi class. Không gán tất cả các lỗi cùng một thông báo "plugin broken".

## 11. Bài tập kiểm chứng giới hạn phục hồi

**Bài tập A — thay thứ tự descriptor:** trong broken descriptor, đặt Broken lên trước Alpha. Dự đoán strict: thông báo STOP CONFIG_ERROR có thể xuất hiện trước mọi dòng USE. Với bounded, quan sát xem các provider sau Broken có được tìm thấy không; kết quả không thay đổi hợp đồng best effort của API.

**Bài tập B — sửa Broken:** bỏ exception trong constructor rồi build lại JAR. Lúc này strict có thể duyệt cả ba provider; chạy lại từ một tiến trình Java mới để không nhầm với cache/loader đã tạo trước.

**Bài tập C — cố tình sai tên class:** đổi dòng demo.providers.Broken thành demo.providers.DoesNotExist; chạy strict và bounded. Dùng stack trace để xác nhận lỗi là không tìm thấy provider class, khác với lỗi constructor của thí nghiệm chính. Không giả định retry sau hai loại lỗi có cùng hành vi.

**Bài tập D — sai định dạng descriptor:** thêm một dòng không phải tên binary hợp lệ, ví dụ "bad provider name!". Lỗi đọc/parse descriptor có thể xảy ra ngay khi iterator tìm provider; bổ sung log để phân biệt hasNext() và next(). Không dùng kết quả quan sát được trên một bản JDK làm bảo đảm chung.

**Bài tập E — provider lỗi nghiệp vụ:** tạo một provider có constructor hợp lệ nhưng process() ném IllegalArgumentException. So sánh PROCESS_ERROR với CONFIG_ERROR và cách host quyết định fallback. Điều quan trọng là không biến lỗi thực thi một phương thức thành bằng chứng descriptor sai.

**Tiêu chí hoàn thành:** giải thích được (1) vì sao catch (Exception) không bắt ServiceConfigurationError, (2) vì sao phải bắt lỗi của cả hasNext() lẫn next(), (3) ý nghĩa chính xác của best effort và giới hạn retry, (4) sự khác nhau giữa provider lỗi khởi tạo và provider lỗi nghiệp vụ, (5) khi nào chọn fail closed và khi nào cho phép degraded mode, và (6) vì sao reload() không phải giải pháp cho cấu hình sai.

**Tài liệu tham khảo:** [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), đặc biệt các phần Errors, iterator(), stream() và reload(). Nguyên tắc trọng tâm là: **thử tiếp có thể có ích, nhưng kết quả phục hồi không được bảo đảm; host phải giới hạn, ghi nhận và xử lý trạng thái nạp không đầy đủ**.