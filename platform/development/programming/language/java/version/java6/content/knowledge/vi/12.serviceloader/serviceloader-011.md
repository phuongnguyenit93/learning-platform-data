# Kiểm thử ServiceLoader: provider bị thiếu, cấu hình trùng và constructor thất bại

## 1. Mục tiêu kiểm thử

`ServiceLoader` giúp ứng dụng tìm các implementation (provider) của một service type mà không phải tạo từng lớp bằng `new`. Với provider trên **classpath**, tên lớp triển khai được khai báo trong resource `META-INF/services/<tên nhị phân đầy đủ của service>`. Cơ chế này vẫn có mặt và được hỗ trợ trong Java hiện đại.

Điểm quan trọng khi kiểm thử không chỉ là “tải được provider”, mà là **phân biệt đúng ba nhóm tình huống**:

1. Provider **không được đăng ký**: không có descriptor cho service trong classpath mà class loader nhìn thấy, hoặc descriptor hợp lệ không chứa provider nào; kết quả duyệt có thể **rỗng**, không mặc định là ngoại lệ.
2. Descriptor **có tên provider nhưng lớp không tồn tại/không tải được**: đây là **cấu hình hỏng**, thường phát sinh `ServiceConfigurationError` khi việc khám phá được kích hoạt.
3. Một provider **được đăng ký nhiều lần**: Java **bỏ qua tên provider trùng lặp** trong cùng file hoặc giữa nhiều file cấu hình cho cùng service. Việc trùng tên **không đồng nghĩa** tạo nhiều instance.
4. Provider **có constructor bị lỗi**: khi `ServiceLoader` khởi tạo provider và constructor ném ngoại lệ, việc duyệt phát sinh `ServiceConfigurationError`, thường giữ ngoại lệ gốc ở `getCause()`.

Đây là các trường hợp khác nhau về ý nghĩa vận hành: **không có implementation** có thể là trạng thái hợp lệ của plugin tùy chọn; **có cấu hình không hợp lệ** là một lỗi triển khai cần điều tra.

| Tình huống | Đầu vào thử nghiệm | Điều cần khẳng định |
| --- | --- | --- |
| Không có provider được đăng ký | Class loader không thấy `META-INF/services/lab.spi.Processor` | Duyệt kết thúc, số provider bằng `0` |
| Có tên lớp không tồn tại | Descriptor ghi `lab.providers.DoesNotExist` | Duyệt ném `ServiceConfigurationError` |
| Lặp tên trong một file và giữa hai file | Cùng `lab.providers.GoodProcessor` xuất hiện nhiều lần | Chỉ một provider tương ứng được tạo trong lần duyệt |
| Constructor ném ngoại lệ | Descriptor ghi `lab.providers.BadProcessor` có constructor ném `IllegalStateException` | Duyệt ném `ServiceConfigurationError`; `getCause()` là `IllegalStateException` |

**Phạm vi:** ví dụ chạy hoàn toàn trên **classpath**, với `ServiceLoader.load(service, classLoader)` và provider descriptor dưới `META-INF/services`. Named modules có ngữ nghĩa `uses`/`provides` riêng; không trộn `module-info.java` vào fixture classpath này. Mã ví dụ tương thích **JDK 17 trở lên**.

## 2. Vì sao phải dựng fixture riêng cho từng kịch bản?

`ServiceLoader` sử dụng các resource mà **class loader cụ thể** nhìn thấy. Nếu cả ứng dụng kiểm thử và dependency đều đặt các tệp `META-INF/services` trên cùng runtime classpath, kết quả có thể bị ảnh hưởng bởi plugin khác đã được đóng gói sẵn. Kiểm thử dễ đưa ra kết luận sai nếu chỉ đổi nội dung tệp trong thư mục source nhưng không kiểm tra classpath thực sự.

Cách đáng tin cậy:

- **Giữ các lớp Java** trong một thư mục output (`out`), nhưng **không đặt descriptor thử nghiệm vào `out`**.
- Mỗi test tạo một **thư mục resource riêng** (ví dụ `absent`, `missing`, `duplicate-1`, `duplicate-2`, `broken`).
- Tạo `URLClassLoader` mới cho từng test và nạp descriptor từ đúng các resource root của kịch bản.
- Mỗi kịch bản tạo một đối tượng `ServiceLoader` mới thông qua `load(service, classLoader)`, sau đó **duyệt thật** để ép khám phá và khởi tạo provider.
- Đóng class loader, dọn các tệp tạm và đưa lỗi kiểm thử lên rõ ràng bằng `AssertionError` nếu kết quả sai.

Fixture này vẫn dùng **đúng API chuẩn**; `URLClassLoader` được sử dụng để cách ly đầu vào kiểm thử trong JVM thông thường. Đây là cơ chế vẫn dùng được trên Java hiện đại, không phụ thuộc Java Extension Mechanism cũ.

## 3. Các lớp thuộc hợp đồng và provider

Tạo cấu trúc thư mục sau:

~~~text
service-loader-cases/
└── src/
    └── lab/
        ├── spi/
        │   └── Processor.java
        ├── providers/
        │   ├── GoodProcessor.java
        │   └── BadProcessor.java
        └── app/
            └── ServiceLoaderCases.java
~~~

Không tạo sẵn `META-INF/services` trong `src`. Chương trình kiểm thử ở mục 4 sẽ sinh descriptor trong thư mục tạm cho từng trường hợp, để test không phụ thuộc resource tình cờ tồn tại ở môi trường.

### 3.1. Service contract

Tệp `src/lab/spi/Processor.java`:

~~~java
package lab.spi;

public interface Processor {
    String process();
}
~~~

### 3.2. Provider hoạt động đúng, có bộ đếm constructor

Tệp `src/lab/providers/GoodProcessor.java`:

~~~java
package lab.providers;

import lab.spi.Processor;

public final class GoodProcessor implements Processor {
    public static int instances;

    public GoodProcessor() {
        instances++;
    }

    @Override
    public String process() {
        return "OK";
    }
}
~~~

`instances` giúp khẳng định không chỉ số phần tử được trả về, mà cả **số lần constructor chạy** khi có đăng ký trùng. Trong hệ thống thực tế, tránh dùng biến static toàn cục làm cơ chế thống kê provider; ở đây nó chỉ là dụng cụ quan sát của bài kiểm thử độc lập.

### 3.3. Provider có constructor thất bại

Tệp `src/lab/providers/BadProcessor.java`:

~~~java
package lab.providers;

import lab.spi.Processor;

public final class BadProcessor implements Processor {
    public BadProcessor() {
        throw new IllegalStateException("ctor boom");
    }

    @Override
    public String process() {
        return "never";
    }
}
~~~

Lớp này được khai báo đúng kiểu (`public`, implements `Processor`, constructor công khai không tham số). Lỗi xảy ra **bên trong constructor**, để chứng minh rằng ngay cả descriptor hợp lệ và lớp tồn tại vẫn có thể thất bại khi tạo instance.

## 4. Chương trình kiểm thử bốn tình huống, có assertion thật

Tệp `src/lab/app/ServiceLoaderCases.java`:

~~~java
package lab.app;

import lab.spi.Processor;
import lab.providers.GoodProcessor;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Comparator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;
import java.util.stream.Stream;

public final class ServiceLoaderCases {
    private static final String CONFIG =
            "META-INF/services/" + Processor.class.getName();

    private static Path config(Path root, String text) throws IOException {
        Path descriptor = root.resolve(CONFIG);
        Files.createDirectories(descriptor.getParent());
        Files.writeString(descriptor, text, StandardCharsets.UTF_8);
        return root;
    }

    private static URLClassLoader classLoader(Path... roots) throws IOException {
        URL[] urls = new URL[roots.length];
        for (int i = 0; i < roots.length; i++) {
            urls[i] = roots[i].toUri().toURL();
        }
        return new URLClassLoader(urls, Processor.class.getClassLoader());
    }

    private static int count(ClassLoader cl) {
        int n = 0;
        for (Processor provider : ServiceLoader.load(Processor.class, cl)) {
            if (!"OK".equals(provider.process())) {
                throw new AssertionError("Unexpected provider result");
            }
            n++;
        }
        return n;
    }

    private static void expectFailure(
            String label, ClassLoader cl, Class<? extends Throwable> cause) {
        try {
            count(cl);
        } catch (ServiceConfigurationError error) {
            if (cause != null && !cause.isInstance(error.getCause())) {
                throw new AssertionError("Wrong failure cause", error);
            }
            System.out.println(label + "=ServiceConfigurationError");
            return;
        }
        throw new AssertionError("Expected ServiceConfigurationError: " + label);
    }

    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("spi-test-");
        try {
            Path absent = Files.createDirectory(temp.resolve("absent"));
            Path missingClass = config(temp.resolve("missing"),
                    "lab.providers.DoesNotExist\n");
            Path first = config(temp.resolve("duplicate-1"),
                    "lab.providers.GoodProcessor\nlab.providers.GoodProcessor\n");
            Path second = config(temp.resolve("duplicate-2"),
                    "lab.providers.GoodProcessor\n");
            Path broken = config(temp.resolve("broken"),
                    "lab.providers.BadProcessor\n");

            try (URLClassLoader loader = classLoader(absent)) {
                if (count(loader) != 0) throw new AssertionError("Expected 0");
                System.out.println("absent=0");
            }
            try (URLClassLoader loader = classLoader(missingClass)) {
                expectFailure("missing class", loader, null);
            }
            GoodProcessor.instances = 0;
            try (URLClassLoader loader = classLoader(first, second)) {
                if (count(loader) != 1 || GoodProcessor.instances != 1) {
                    throw new AssertionError("Duplicate provider was instantiated");
                }
                System.out.println("duplicates=1");
            }
            try (URLClassLoader loader = classLoader(broken)) {
                expectFailure("bad constructor", loader, IllegalStateException.class);
            }
        } finally {
            try (Stream<Path> paths = Files.walk(temp)) {
                for (Path file : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(file);
                }
            }
        }
    }
}
~~~

### Giải thích bộ kiểm thử

**`CONFIG`:** được tạo từ `Processor.class.getName()`, nên resource có tên đúng là `META-INF/services/lab.spi.Processor`. Đó là định danh của **service**, không phải của lớp provider. Tệp cấu hình phải ở UTF-8; `Files.writeString(..., StandardCharsets.UTF_8)` bảo đảm điều đó.

**`classLoader(Path... roots)`:** URLClassLoader nhận một hoặc nhiều thư mục root chứa descriptor. Parent `Processor.class.getClassLoader()` giúp lớp provider và service contract được nạp qua cùng định danh kiểu Java; nếu tùy tiện nạp một bản sao `Processor.class` ở class loader khác, provider có thể không gán được vào service type và bài test sẽ kiểm tra sai thứ cần kiểm tra.

**`count(ClassLoader)`:** vòng `for` thật sự gọi iterator của `ServiceLoader` và dùng instance. Chỉ gọi `ServiceLoader.load(...)` rồi kết luận “không có lỗi” sẽ **bỏ sót lỗi lazy-loading**. Hàm kiểm tra cả hành vi `process()` của provider, sau đó mới trả số phần tử.

**`expectFailure(...)`:** dự kiến có `ServiceConfigurationError`; nếu không có lỗi, nó ném `AssertionError` để test thất bại. Với constructor lỗi, nó còn kiểm tra chính xác kiểu nguyên nhân ở `error.getCause()`. Với provider class hoàn toàn không tồn tại, `getCause()` có thể không có thông tin theo một đường lỗi cụ thể, vì vậy test khẳng định **kiểu lỗi hợp đồng** thay vì dựa vào chuỗi thông báo nội bộ.

**Tình huống trùng tên:** `duplicate-1` chứa cùng tên `GoodProcessor` hai lần; `duplicate-2` cũng đăng ký tên đó. Cả hai cùng được thêm vào class loader, nhằm kiểm chứng loại bỏ trùng **trong một file lẫn giữa các file**. Khẳng định `count == 1` và `instances == 1` với class loader/ServiceLoader mới sẽ phát hiện tình trạng tạo lặp ngoài ý muốn.

**Dọn dẹp:** `try-with-resources` đóng URLClassLoader. Khối `finally` xóa cây tệp tạm theo thứ tự con trước cha. Mỗi lần chạy test có đường dẫn tạm riêng nên không đụng nhau; nếu assertion thất bại, quá trình dọn dẹp vẫn được thực hiện.

## 5. Biên dịch, chạy và kết quả chính xác

Mở terminal trong thư mục `service-loader-cases`. Lệnh sau dùng `javac` sẵn có trong JDK 17+; không cần Maven/Gradle hoặc JUnit:

~~~bash
javac -encoding UTF-8 -d out src/lab/spi/Processor.java src/lab/providers/GoodProcessor.java src/lab/providers/BadProcessor.java src/lab/app/ServiceLoaderCases.java
java -cp out lab.app.ServiceLoaderCases
~~~

Kết quả khi cả bốn assertion đều đạt:

~~~text
absent=0
missing class=ServiceConfigurationError
duplicates=1
bad constructor=ServiceConfigurationError
~~~

Nếu xuất hiện sai biệt (ví dụ `duplicates=2` hoặc constructor không ném lỗi), chương trình sẽ ném `AssertionError` và chạy kết thúc không thành công. Vì thế đây là **bộ kiểm thử kiểm tra kết quả**, không chỉ in log để xem bằng mắt.

Lưu ý khi chạy: `out` chứa những file `.class` được biên dịch từ bốn source trên. **Không sao chép descriptor thật cho `lab.spi.Processor` vào `out/META-INF/services`** khi chạy fixture này, bởi nếu parent class loader nhìn thấy descriptor ngoài ý muốn, test “absent” sẽ không còn độc lập. Các descriptor của từng kịch bản do chương trình tự tạo trong thư mục tạm và chỉ được gắn vào URLClassLoader tương ứng.

### 5.1. Đọc từng kết quả

- `absent=0`: resource root `absent` không có `META-INF/services/lab.spi.Processor`; không có provider nào được phát hiện. Đây là trạng thái **đăng ký rỗng**, không phải cấu hình đã khai báo provider sai.
- `missing class=ServiceConfigurationError`: cấu hình ghi `lab.providers.DoesNotExist` nhưng class loader không nạp được lớp đó. Không nên diễn giải trường hợp này thành “không có provider”.
- `duplicates=1`: các bản đăng ký giống hệt nhau được nhận diện và bỏ qua, nên provider hợp lệ chỉ xuất hiện một lần trong lần duyệt này.
- `bad constructor=ServiceConfigurationError`: tên provider và type đều hợp lệ; khi khởi tạo, constructor ném `IllegalStateException("ctor boom")`, được `ServiceLoader` báo thành lỗi cấu hình. Bài test xác minh nguyên nhân qua `getCause()`, không phụ thuộc vào văn bản lỗi.

## 6. Những chi tiết API ảnh hưởng đến độ đúng của test

### 6.1. Lỗi có thể xuất hiện khi duyệt, không phải ở `load()`

`ServiceLoader` làm việc **lười (lazy)**: provider được tìm/nạp/khởi tạo khi iterator hoặc luồng xử lý yêu cầu. Vì vậy kiểu test sau chưa đủ để chứng minh cấu hình hợp lệ:

~~~java
// Chưa bắt buộc phải nạp và khởi tạo các provider:
ServiceLoader<Processor> loader = ServiceLoader.load(Processor.class);
~~~

Để kiểm thử constructor lỗi, cần buộc trình tải **tạo instance**. Vòng `for (Processor p : loader)` là cách rõ ràng. Nếu dùng API `stream()` (có từ Java 9), stream trả về các phần tử kiểu `ServiceLoader.Provider<Processor>` và `Provider.get()` mới yêu cầu tạo instance. Chỉ đếm số descriptor/provider qua stream **không nhất thiết kích hoạt constructor**; test constructor lỗi như vậy có thể báo đạt sai.

Ví dụ khi đang ở trong một phương thức và đã có `loader`:

~~~java
for (ServiceLoader.Provider<Processor> provider : loader.stream().toList()) {
    Processor instance = provider.get(); // ép khởi tạo provider
    System.out.println(instance.process());
}
~~~

Đây là **đoạn minh họa**, không phải tệp Java độc lập. Với descriptor trỏ đến `BadProcessor`, lỗi xảy ra khi provider được khởi tạo; việc thu thập danh sách provider type trước đó chưa đủ để khẳng định constructor chạy thành công.

### 6.2. `ServiceConfigurationError` là `Error`

`ServiceConfigurationError` kế thừa `java.lang.Error`, không kế thừa `Exception`. Do đó `catch (Exception e)` sẽ **không** bắt được lỗi này. Trong test có mục tiêu cố ý kiểm tra SPI bị hỏng, dùng `catch (ServiceConfigurationError e)` hoặc assertion tương ứng là chính xác.

Trong ứng dụng thực tế, không nên tự động nuốt lỗi này rồi giả lập rằng không có provider, vì nó có thể che giấu JAR lỗi, thiếu dependency hoặc lỗ hổng đóng gói. Khi lỗi là nghiêm trọng, báo lại nguyên nhân gốc và ngữ cảnh cấu hình. Khôi phục và bỏ qua provider lỗi sau một `ServiceConfigurationError` không được bảo đảm thành công trong mọi trường hợp; không thiết kế cơ chế điều hành dựa vào việc iterator tự phục hồi.

### 6.3. Đừng nhầm cache với việc loại bỏ đăng ký trùng

Mỗi `ServiceLoader` có **cache các provider đã nạp**; `reload()` xóa cache. Việc loại bỏ tên trùng trong các descriptor lại là quy tắc của **khám phá provider**. Chúng liên quan nhưng không đồng nhất:

- Duyệt lại **cùng một** `ServiceLoader` có thể trả các instance đã cache; điều này không chứng minh file cấu hình bị trùng.
- Một test kiểm tra tên trùng nên tạo `ServiceLoader` mới, class loader sạch và đếm cả instance như ví dụ.
- `reload()` có thể khiến provider được tạo lại khi duyệt, nhưng **không tự cập nhật runtime classpath** hay khiến lớp vừa thêm trên ổ đĩa được class loader hiện tại nhìn thấy.
- Tạo các `ServiceLoader` độc lập có cache độc lập; không có cam kết rằng một lớp provider chỉ có một instance trên toàn JVM.

### 6.4. Thứ tự provider và nhiều file cấu hình

Bên trong một descriptor, tên provider được xử lý theo thứ tự liệt kê. Khi descriptor nằm ở **nhiều resource root/JAR**, thứ tự resource phụ thuộc cách class loader trả về các URL. Không xây assertion về thứ tự bất biến giữa hai JAR khi mục tiêu bài test chỉ là kiểm tra **không lặp tên**.

Nếu muốn kiểm thử chính xác thứ tự có ý nghĩa nghiệp vụ, hãy tự định nghĩa quy tắc chọn provider ổn định (ví dụ ID/priority nằm trong hợp đồng), rồi kiểm tra quy tắc đó; đừng dựa vào thứ tự classpath.

### 6.5. Class loader là một phần của đầu vào kiểm thử

Nếu test chạy trong IDE, Gradle hoặc một plugin framework khác, thread context class loader có thể nhìn thấy nhiều service descriptor hơn mong đợi. Để đầu vào rõ ràng, ví dụ dùng overload:

~~~java
ServiceLoader<Processor> loader =
        ServiceLoader.load(Processor.class, explicitlyChosenClassLoader);
~~~

Đây là **đoạn minh họa**; `explicitlyChosenClassLoader` phải là một biến ClassLoader đã có trong phương thức. Trong bài lab, `classLoader(...)` xây ClassLoader từ đúng fixture resource roots. Cần kiểm tra **cả nguồn cấu hình và khả năng nạp các class provider**: có descriptor chưa đủ nếu class của provider nằm ngoài phạm vi tìm kiếm.

## 7. Mở rộng bộ kiểm thử vào dự án thật

Các kịch bản bổ sung có giá trị, khi service là một phần quan trọng của sản phẩm:

| Trường hợp bổ sung | Fixture | Assertion cần có |
| --- | --- | --- |
| Lớp provider không implement service | Descriptor trỏ đến class không gán được vào interface | `ServiceConfigurationError` khi nạp |
| Constructor không công khai/không có no-arg | Provider ở **classpath** không có constructor công khai không tham số | `ServiceConfigurationError` |
| Descriptor sai định dạng | Tệp UTF-8 có provider name không hợp lệ | `ServiceConfigurationError` khi parse |
| Có provider tốt rồi đến provider lỗi | Một descriptor đăng ký provider hợp lệ trước, sau đó provider lỗi | Có thể đã nhận một số instance trước khi lỗi; kiểm thử lỗi khi duyệt đến provider hỏng |
| Resource không được đóng gói vào JAR | Test artifact không chứa `META-INF/services/<service>` ở classpath root | Không phát hiện provider từ artifact đó |
| Fat/shaded JAR làm mất descriptor | Hai thư viện có cùng tên tệp service, bản build gộp chỉ giữ một file | Soát descriptor cuối và khẳng định đủ provider cần thiết |

Các test tích hợp thực tế nên dựng classpath từ **artifact cuối cùng**, đặc biệt nếu build dùng plugin shading/relocation. Một file resource có nội dung đúng trong `src/main/resources` chưa chứng minh file đó tồn tại nguyên vẹn trong JAR khi triển khai.

Với JUnit Jupiter (JUnit 5), có thể dùng `assertThrows(ServiceConfigurationError.class, () -> { ... })`, nhưng thân lambda phải **duyệt hoặc khởi tạo provider thật**. Không kiểm tra ngoại lệ chỉ bằng cách gọi `ServiceLoader.load(...)`. Nếu dùng `assertEquals(0, ...)` với trường hợp không đăng ký, hãy duyệt hết loader; không dùng `loader != null` để kết luận có provider.

### 7.1. Làm sao kiểm tra descriptor đã thật sự được tìm thấy?

Đoạn sau có thể đặt trong một phương thức Java để chẩn đoán (các import cần thiết: `java.util.Enumeration`, `java.net.URL`, `java.io.IOException`):

~~~java
String path = "META-INF/services/" + Processor.class.getName();
Enumeration<URL> found = someClassLoader.getResources(path);
while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
~~~

`someClassLoader` là class loader cần kiểm tra, không phải biến có sẵn trong chương trình. Đoạn mã có thể ném `IOException`. Nó giúp xác nhận những descriptor URL mà class loader tìm được, nhưng **không thay thế** kiểm tra lớp provider có tải/khởi tạo được hay không.

## 8. Sai lầm thường gặp và cách tránh

1. **Gộp “không có file cấu hình” với “có file nhưng provider class bị thiếu”.** Trường hợp đầu thường cho kết quả rỗng; trường hợp sau là lỗi cấu hình cần được phát hiện.
2. **Chỉ gọi `load()` rồi coi test thành công.** Do lazy loading, phải duyệt iterator hoặc gọi `Provider.get()` để bắt lỗi khởi tạo.
3. **Dùng `catch (Exception)` để bắt `ServiceConfigurationError`.** Đây là `Error`; test nên bắt đúng kiểu muốn xác minh.
4. **Đếm lần khởi tạo sau khi duyệt lại cùng loader** mà không xét cache. Tạo fixture/loader mới hoặc xác định rõ cache là điều đang muốn kiểm tra.
5. **Coi cấu hình trùng là một lỗi mặc định.** API bỏ qua tên class provider trùng trong cùng hoặc nhiều descriptor; bài kiểm thử nên xác minh số provider còn lại.
6. **Khẳng định thứ tự provider giữa nhiều JAR.** Thứ tự tìm resource phụ thuộc class loader, nên chỉ khẳng định yêu cầu nghiệp vụ tự xác định.
7. **Cho toàn bộ test dùng classpath chính của ứng dụng** rồi vô tình phát hiện những provider nằm ở dependencies khác. Cách ly descriptor của từng kịch bản bằng class loader riêng.
8. **So sánh chính xác chuỗi ngoại lệ nội bộ.** Chúng có thể thay đổi giữa các phiên bản hoặc ngữ cảnh. Kiểm tra **loại lỗi, nguyên nhân, số provider và hành vi quan sát được**.
9. **Không thử artifact triển khai thật.** Khi build gộp nhiều service descriptor, phải xác nhận tất cả dòng provider vẫn còn trong `META-INF/services` của JAR cuối cùng.

## 9. Bài tự luyện

**Bài 1.** Cấu hình cho `lab.spi.Processor` không tồn tại. `ServiceLoader.load(Processor.class, cl)` có luôn ném `ServiceConfigurationError` ngay lập tức không?

**Đáp án:** Không. Khi không có provider đăng ký mà class loader có thể thấy, việc duyệt bình thường không trả phần tử; `ServiceLoader` không bắt buộc ném lỗi chỉ vì số provider bằng 0.

**Bài 2.** Trong cùng descriptor có ba dòng tên `lab.providers.GoodProcessor`. Một descriptor khác cũng có dòng đó. Với fixture của mục 4, số provider và số lần constructor chạy là bao nhiêu?

**Đáp án:** Một provider tương ứng, một lần constructor chạy trong lần duyệt của ServiceLoader mới. Việc trùng tên bị bỏ qua, không tạo bốn provider.

**Bài 3.** Một descriptor ghi đúng tên `BadProcessor`, nhưng constructor ném `IllegalStateException`. Đâu là kiểu lỗi consumer nhận khi duyệt? Có thể tìm nguyên nhân gốc ở đâu?

**Đáp án:** `ServiceConfigurationError`. `getCause()` cho phép kiểm tra `IllegalStateException` trong kịch bản cụ thể này.

**Bài 4.** Test `ServiceLoader.load(Processor.class).stream().count() > 0` có đủ khẳng định mọi constructor provider chạy thành công không?

**Đáp án:** Không. `stream()` là stream của metadata `Provider<S>`; muốn kiểm tra quá trình khởi tạo phải gọi `Provider.get()` hoặc duyệt bằng iterator của `ServiceLoader`.

**Bài 5.** Vì sao test case lỗi nên dùng class loader mới và fixture tài nguyên riêng?

**Đáp án:** Để cô lập descriptor có chủ đích, tránh tác động từ resource trên classpath bên ngoài và cache của một ServiceLoader đã được duyệt trước đó.

## 10. Tài liệu API hiện hành

- [Oracle Java SE 26 — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): provider-configuration files, duplicate names, lazy loading, error conditions, caching và class loader.
- [Oracle Java SE 26 — `ServiceConfigurationError`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceConfigurationError.html): loại lỗi dành cho các tình huống locate/load/instantiate provider thất bại.
- [Oracle Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): đối chiếu hợp đồng còn áp dụng khi chạy ví dụ trên Java 17+.

Những nguyên tắc và test trong bài sử dụng các API còn được hỗ trợ. Không cần các cơ chế Java extension directory hoặc công cụ triển khai provider đã lỗi thời.
