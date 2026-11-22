# Thực nghiệm lỗi SPI trên classpath: sai tên dịch vụ, thiếu constructor và thiếu tài nguyên

Java Service Provider Interface (SPI) cho phép host tìm implementation thông qua **java.util.ServiceLoader** mà không cần hard-code tên class cụ thể. Nhưng chỉ cần một ký tự sai ở tên descriptor, một provider thiếu constructor thích hợp hoặc một resource bị bỏ quên trong JAR, hành vi lúc chạy đã khác nhau. Bài này xây dựng **năm gói JAR thực nghiệm** từ cùng một bộ mã Java 17+, chạy từng gói ở một tiến trình riêng và giải thích vì sao lỗi xảy ra.

**Phạm vi:** SPI chạy trên **classpath** (unnamed modules), khai báo provider qua **META-INF/services**. Với Java Platform Module System (JPMS) trên module path, cú pháp provides/uses và quy tắc khởi tạo provider có khác biệt; không áp dụng nguyên xi tất cả quy tắc constructor của ví dụ classpath cho module path.

## 1. Ba điểm có thể hỏng trong vòng đời ServiceLoader

Trước khi thực nghiệm, tách ba giai đoạn để tránh chẩn đoán nhầm:

1. **Tìm cấu hình dịch vụ (discovery):** ServiceLoader tìm các resource có đường dẫn chính xác META-INF/services/<tên binary của interface SPI>. Nếu không tìm thấy descriptor nào phù hợp, duyệt ServiceLoader có thể trả về **0 provider**, dù class implementation vẫn nằm trong JAR.
2. **Đọc, kiểm tra và khởi tạo provider:** tên class ở mỗi dòng descriptor phải tồn tại, truy cập được, tương thích với SPI và có khả năng khởi tạo theo quy tắc classpath. Tại bước duyệt provider, lỗi như tên class sai hoặc thiếu public no-argument constructor thường được báo bằng **ServiceConfigurationError**.
3. **Sử dụng provider:** một provider đã nạp hợp lệ vẫn có thể thất bại trong phương thức nghiệp vụ khi cần tài nguyên mà JAR không chứa. Đó là **lỗi của implementation/resource**, không nhất thiết là lỗi discovery của ServiceLoader.

Ví dụ descriptor cho interface dev.lab.spi.Greeter:

~~~text
META-INF/services/dev.lab.spi.Greeter
~~~

Nội dung hợp lệ của file đó:

~~~text
dev.lab.plugin.HelloGreeter
~~~

**Tên file** là tên đầy đủ của interface dịch vụ, không phải tên của implementation. **Nội dung file** là một hoặc nhiều tên binary của class implementation; mỗi tên trên một dòng. Descriptor là file text UTF-8 dưới đường dẫn META-INF/services tại gốc classpath/JAR. Dòng trống và comment bắt đầu bằng # được phép, nhưng một đường dẫn sai hoặc tên class sai không được Java tự sửa.

Bảng giả thuyết để đối chiếu kết quả thí nghiệm:

| Thay đổi có chủ đích | Giai đoạn bị ảnh hưởng | Kết quả dự kiến trong host mẫu |
| --- | --- | --- |
| Không đổi gì | Discovery → khởi tạo → gọi greet | OK: Xin chào, Java! |
| Đặt sai **tên file descriptor** | Không tìm được cấu hình cho Greeter | NO_PROVIDER |
| Viết sai **tên class trong descriptor** | Đã thấy cấu hình nhưng không tìm được provider class | CONFIG_ERROR |
| Provider không có **public constructor không tham số** | Không thể khởi tạo provider trên classpath | CONFIG_ERROR |
| Thiếu **messages/greeting.txt** trong JAR | Provider khởi tạo được nhưng greet không đọc được file | RESOURCE_ERROR: messages/greeting.txt not found |

Các nhãn NO_PROVIDER, CONFIG_ERROR và RESOURCE_ERROR trong bảng là **chuỗi in ra bởi chương trình kiểm thử**, không phải tên mã lỗi chuẩn của JVM. Ta chủ động chuẩn hóa output để thí nghiệm ổn định giữa các bản JDK; khi chẩn đoán thật phải xem nguyên nhân đầy đủ trong exception.

## 2. Chuẩn bị cây thư mục của bài lab

Các đường dẫn dưới đây được tính từ thư mục gốc **lab/**:

~~~text
lab/
├── src/
│   ├── api/dev/lab/spi/Greeter.java
│   ├── plugin/dev/lab/plugin/HelloGreeter.java
│   ├── plugin/dev/lab/plugin/NeedsArgsGreeter.java
│   └── host/dev/lab/host/Host.java
├── descriptors/
│   ├── good/META-INF/services/dev.lab.spi.Greeter
│   ├── bad-file/META-INF/services/dev.lab.spi.Greeters
│   ├── bad-provider/META-INF/services/dev.lab.spi.Greeter
│   └── no-ctor/META-INF/services/dev.lab.spi.Greeter
└── resources/
    └── messages/greeting.txt
~~~

Thư mục **build/** và **dist/** sẽ được tạo bằng lệnh biên dịch ở phần sau. Mỗi nhánh descriptors là một bộ cấu hình độc lập dành cho một gói thực nghiệm; không đưa đồng thời nhiều bộ descriptor mâu thuẫn vào cùng một JAR.

Bộ lab này chỉ yêu cầu **JDK 17 trở lên** và các công cụ javac, jar, java đi kèm JDK. Những lệnh shell dùng cú pháp bash/POSIX; trên Windows có thể chạy trong môi trường bash tương thích, hoặc chuyển sang PowerShell và đổi dấu phân cách classpath như hướng dẫn phía dưới.

## 3. Viết mã nguồn dùng chung cho mọi trường hợp

### 3.1. API/SPI mà host và plugin đều biết

File **src/api/dev/lab/spi/Greeter.java**:

~~~java
package dev.lab.spi;

public interface Greeter {
    String greet(String name);
}
~~~

Greeter là **hợp đồng dùng chung**. Ta biên dịch vào một JAR API và đưa JAR ấy vào classpath của host. Implementation sẽ được biên dịch dựa trên cùng API; không tạo bản Greeter độc lập bên trong plugin JAR ở các lệnh đóng gói bên dưới.

### 3.2. Provider hợp lệ có resource riêng

File **src/plugin/dev/lab/plugin/HelloGreeter.java**:

~~~java
package dev.lab.plugin;

import dev.lab.spi.Greeter;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
        // Constructor public không tham số: ServiceLoader có thể gọi.
    }

    @Override
    public String greet(String name) {
        try (InputStream input =
                HelloGreeter.class.getResourceAsStream("/messages/greeting.txt")) {
            if (input == null) {
                throw new IllegalStateException(
                        "messages/greeting.txt not found");
            }
            String prefix =
                    new String(input.readAllBytes(), StandardCharsets.UTF_8).strip();
            return prefix + ", " + name + "!";
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
~~~

File **resources/messages/greeting.txt** có nội dung một dòng:

~~~text
Xin chào
~~~

Lưu ý về resource:

- Đường dẫn bắt đầu bằng **/** trong Class.getResourceAsStream biểu thị đường dẫn tuyệt đối từ **gốc classpath của loader định nghĩa class**. JAR phải có entry messages/greeting.txt.
- Nếu không có entry ấy, phương thức trả về **null**; code chủ động ném IllegalStateException với thông điệp rõ ràng.
- Resource được đọc khi gọi greet, **sau khi provider đã được phát hiện và tạo đối tượng**. Vì thế kết quả thiếu resource trong lab không bị ServiceLoader đổi thành CONFIG_ERROR.
- strip() loại bỏ ký tự xuống dòng cuối file; giải mã theo UTF-8 giúp nội dung tiếng Việt không phụ thuộc charset mặc định của máy.

### 3.3. Provider cố tình thiếu constructor phù hợp

File **src/plugin/dev/lab/plugin/NeedsArgsGreeter.java**:

~~~java
package dev.lab.plugin;

import dev.lab.spi.Greeter;

public final class NeedsArgsGreeter implements Greeter {
    private final String prefix;

    public NeedsArgsGreeter(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

Class này **biên dịch được** và triển khai Greeter đúng kiểu, nhưng chỉ có constructor nhận String. Một class đã khai báo constructor có tham số như vậy **không được Java tự sinh constructor không tham số**. Với provider được liệt kê trong META-INF/services trên classpath, ServiceLoader cần public constructor không tham số để khởi tạo và sẽ báo ServiceConfigurationError khi không thể lấy constructor đó.

Không nên nhầm với trường hợp class public **không khai báo constructor nào**: compiler có thể tạo constructor mặc định không tham số với mức truy cập tương ứng, nên trường hợp đó không tái hiện lỗi thiếu constructor.

### 3.4. Host để quan sát kết quả

File **src/host/dev/lab/host/Host.java**:

~~~java
package dev.lab.host;

import dev.lab.spi.Greeter;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) {
        int found = 0;

        try {
            for (Greeter provider : ServiceLoader.load(Greeter.class)) {
                found++;
                try {
                    System.out.println("OK: " + provider.greet("Java"));
                } catch (IllegalStateException ex) {
                    System.out.println("RESOURCE_ERROR: " + ex.getMessage());
                }
            }

            if (found == 0) {
                System.out.println("NO_PROVIDER");
            }
        } catch (ServiceConfigurationError ex) {
            System.out.println("CONFIG_ERROR");
        }
    }
}
~~~

Vòng for chủ động **duyệt** ServiceLoader. Việc chỉ gọi ServiceLoader.load(...) rồi không iterate không đủ để kết luận provider khởi tạo được: ServiceLoader nạp và khởi tạo các provider một cách **lazy**. Ở ví dụ này, mỗi lần chạy host chỉ đưa **một** plugin JAR vào classpath để tránh ảnh hưởng của kết quả discovery từ những JAR thực nghiệm khác.

Host bắt ServiceConfigurationError ở vòng ngoài vì lỗi discovery/khởi tạo có thể phát sinh khi iterator tiến tới provider. Host chỉ bắt IllegalStateException quanh greet để minh họa lỗi resource có chủ đích. Trong hệ thống thật, cần log **exception và cause gốc**: không nên chỉ in một nhãn như trong lab.

## 4. Tạo descriptor cho bốn biến thể

Hãy tạo đúng các file dưới đây; chúng là file **không có phần mở rộng** sau tên interface.

**A. Cấu hình đúng:** descriptors/good/META-INF/services/dev.lab.spi.Greeter

~~~text
dev.lab.plugin.HelloGreeter
~~~

**B. Sai tên file:** descriptors/bad-file/META-INF/services/dev.lab.spi.Greeters

~~~text
dev.lab.plugin.HelloGreeter
~~~

Ở B, **nội dung file đúng nhưng tên file có chữ s thừa**. ServiceLoader đang được gọi với Greeter.class nên nó tìm chính xác META-INF/services/dev.lab.spi.Greeter; file có tên Greeters không khớp. Đây là trường hợp **không phát hiện provider**.

**C. Sai tên class bên trong:** descriptors/bad-provider/META-INF/services/dev.lab.spi.Greeter

~~~text
dev.lab.plugin.HeloGreeter
~~~

Ở C, tên file descriptor đúng, nhưng **HeloGreeter** thiếu một chữ l so với class thực tế HelloGreeter. ServiceLoader thấy descriptor rồi cố phân giải tên class sai, vì thế kết quả là **ServiceConfigurationError** khi duyệt. Nó không tự bỏ qua lỗi này rồi báo NO_PROVIDER.

**D. Provider thiếu public no-arg constructor:** descriptors/no-ctor/META-INF/services/dev.lab.spi.Greeter

~~~text
dev.lab.plugin.NeedsArgsGreeter
~~~

Ở D, cả tên file và tên class đều đúng; vấn đề chỉ xuất hiện khi ServiceLoader thử khởi tạo NeedsArgsGreeter.

Trường hợp **E thiếu resource** sẽ dùng lại descriptor A, nhưng cố tình không đóng resources/messages/greeting.txt vào JAR.

## 5. Biên dịch class và đóng năm JAR

Từ thư mục gốc lab/, chạy tuần tự trong bash/POSIX:

~~~bash
mkdir -p build/api build/plugin build/host dist

javac -encoding UTF-8 -d build/api src/api/dev/lab/spi/Greeter.java
jar --create --file build/api.jar -C build/api .

javac -encoding UTF-8 -cp build/api.jar -d build/plugin src/plugin/dev/lab/plugin/HelloGreeter.java src/plugin/dev/lab/plugin/NeedsArgsGreeter.java
javac -encoding UTF-8 -cp build/api.jar -d build/host src/host/dev/lab/host/Host.java

jar --create --file dist/good.jar -C build/plugin . -C descriptors/good . -C resources .
jar --create --file dist/bad-file.jar -C build/plugin . -C descriptors/bad-file . -C resources .
jar --create --file dist/bad-provider.jar -C build/plugin . -C descriptors/bad-provider . -C resources .
jar --create --file dist/no-ctor.jar -C build/plugin . -C descriptors/no-ctor . -C resources .
jar --create --file dist/no-resource.jar -C build/plugin . -C descriptors/good .
~~~

**Giải thích lệnh đóng gói:**

- javac -d tạo class files theo cây package, ví dụ build/plugin/dev/lab/plugin/HelloGreeter.class.
- build/api.jar chứa Greeter.class và được đưa vào classpath **chung** khi biên dịch/chạy.
- -C build/plugin . đóng class implementation từ gốc build/plugin vào gốc JAR; tên entry không mang tiền tố build/plugin.
- -C descriptors/good . thêm META-INF/services vào đúng vị trí ở gốc JAR.
- -C resources . thêm messages/greeting.txt vào gốc JAR.
- Gói no-resource.jar **không có** tham số -C resources ., nên đây là gói có provider/descriptor đúng nhưng thiếu tài nguyên để thực hiện greet.

Cả hai class implementation đều hiện diện trong các JAR để đơn giản hóa build. Việc một class nằm trong JAR **không đồng nghĩa** nó là provider được đăng ký: chỉ class có tên trong descriptor Greeter mới được ServiceLoader lựa chọn. Vì vậy good.jar không cố khởi tạo NeedsArgsGreeter, dù class này cũng nằm trong archive.

Kiểm tra trực tiếp các entry quan trọng:

~~~bash
jar --list --file dist/good.jar
jar --list --file dist/bad-file.jar
jar --list --file dist/no-resource.jar
~~~

Trong good.jar phải có:

~~~text
dev/lab/plugin/HelloGreeter.class
dev/lab/plugin/NeedsArgsGreeter.class
META-INF/services/dev.lab.spi.Greeter
messages/greeting.txt
~~~

Lệnh jar --list còn có thể liệt kê META-INF/MANIFEST.MF và các mục thư mục; bốn dòng trên chỉ là **các entry cần xác nhận**, không phải toàn bộ stdout của jar. Trong bad-file.jar, entry descriptor phải là META-INF/services/dev.lab.spi.Greeters. Trong no-resource.jar, **không** được có messages/greeting.txt.

## 6. Chạy độc lập từng thực nghiệm

Chạy năm tiến trình Java riêng; trong mỗi tiến trình, classpath chỉ gồm **host classes, API JAR và đúng một JAR thực nghiệm**:

~~~bash
for case_name in good bad-file bad-provider no-ctor no-resource; do
    printf '%s -> ' "$case_name"
    java -cp "build/host:build/api.jar:dist/$case_name.jar" dev.lab.host.Host
done
~~~

**Stdout kỳ vọng chính xác** với các file và mã nguồn đã đưa ở trên:

~~~text
good -> OK: Xin chào, Java!
bad-file -> NO_PROVIDER
bad-provider -> CONFIG_ERROR
no-ctor -> CONFIG_ERROR
no-resource -> RESOURCE_ERROR: messages/greeting.txt not found
~~~

Dấu **:** dùng để phân cách các thành phần -cp trên Linux/macOS; nếu chạy Java trực tiếp trong **PowerShell/CMD Windows**, thay bằng dấu **;**. Chú ý lệnh for/printf ở trên là cú pháp bash; có thể gọi từng lệnh java riêng trong Windows shell.

Các kết quả có ý nghĩa khác nhau:

### Thử nghiệm 1 — Gói hợp lệ

ServiceLoader tìm descriptor Greeter → đọc tên HelloGreeter → tải class → tìm public no-arg constructor → tạo provider → host gọi greet → HelloGreeter tìm thấy messages/greeting.txt → in OK. Resource vẫn được đọc qua classpath, không cần file nằm cạnh thư mục làm việc.

### Thử nghiệm 2 — Sai tên file dịch vụ

Gói bad-file.jar chứa class implementation và resource đầy đủ, nhưng ServiceLoader không thấy file với tên **META-INF/services/dev.lab.spi.Greeter**. Không có provider đăng ký cho đúng SPI, nên vòng for không chạy và found = 0. Đây là **NO_PROVIDER**, không phải lỗi khởi tạo. Nếu đổi lại đúng tên descriptor, không cần sửa Java code.

### Thử nghiệm 3 — Sai tên class được khai báo

Gói bad-provider.jar có descriptor mang **đúng tên SPI**, nhưng bên trong ghi HeloGreeter. Khi duyệt provider, ServiceLoader cố tìm class theo tên đó và phát sinh ServiceConfigurationError. Host in CONFIG_ERROR. Khác với thử nghiệm 2, lỗi đã xảy ra **sau khi cấu hình dịch vụ được phát hiện**. Sửa **nội dung descriptor** mới là giải pháp.

### Thử nghiệm 4 — Thiếu constructor cần thiết

Gói no-ctor.jar ghi đúng tên NeedsArgsGreeter. Class này tồn tại và implements Greeter, nhưng chỉ khai báo NeedsArgsGreeter(String). Khi chạy trên classpath, ServiceLoader không biết tự cung cấp giá trị String và không tìm thấy public constructor không tham số; kết quả được chuẩn hóa thành CONFIG_ERROR. Sửa bằng cách cung cấp **public no-arg constructor hợp lệ**, hoặc thiết kế provider/DI theo cơ chế khác có hợp đồng rõ ràng, không giả định ServiceLoader classpath sẽ tự inject constructor arguments.

### Thử nghiệm 5 — Thiếu resource của provider

Gói no-resource.jar vẫn đăng ký HelloGreeter hợp lệ. Vòng for đã nhận provider, host gọi greet, sau đó getResourceAsStream trả về null. Chương trình báo RESOURCE_ERROR do chính HelloGreeter ném IllegalStateException. **ServiceLoader đã hoàn thành discovery và instantiation thành công**. Nếu provider đọc resource ngay trong constructor và constructor ném lỗi, ServiceLoader có thể bọc nguyên nhân khởi tạo trong ServiceConfigurationError; **vị trí đọc resource** ảnh hưởng đến nơi lỗi xuất hiện.

## 7. Cách chẩn đoán mà không đoán mò

Khi một SPI không hoạt động, hãy kiểm tra theo thứ tự thực thi:

**Bước 1 — Xác định host đang yêu cầu service nào.** Đọc chính xác lời gọi ServiceLoader.load(Greeter.class). Tên binary cần được đăng ký là dev.lab.spi.Greeter. Đừng suy diễn tên file descriptor từ tên class implementation.

**Bước 2 — Liệt kê entry trong JAR được triển khai.** Dùng jar --list --file path/to/plugin.jar. Kiểm tra chính xác tên META-INF/services/dev.lab.spi.Greeter và tài nguyên messages/greeting.txt. Tên package, chữ hoa/chữ thường và dấu chấm trong tên descriptor đều quan trọng. Một file đặt nhầm dưới src/main/resources/META-INF/services trong **nội bộ JAR** (có dư tiền tố source) sẽ không khớp đường dẫn ServiceLoader yêu cầu.

**Bước 3 — Đọc nội dung descriptor sau khi build.** Có thể giải nén JAR trong thư mục kiểm tra riêng, hoặc xem bằng công cụ ZIP, để bảo đảm mỗi dòng chứa tên đầy đủ của provider. Với demo, dùng:

~~~bash
jar --extract --file dist/good.jar META-INF/services/dev.lab.spi.Greeter
~~~

Lệnh trên sẽ trích file xuống thư mục hiện hành, vì vậy chỉ chạy từ **thư mục kiểm tra trống** nếu không muốn ghi đè file trùng tên. Descriptor không dùng cú pháp import Java, không chứa hậu tố .class và không dùng đường dẫn dạng dev/lab/plugin/HelloGreeter.class.

**Bước 4 — Kiểm tra class và constructor.** Dùng javap để xem chữ ký public:

~~~bash
javap -public -classpath dist/good.jar dev.lab.plugin.HelloGreeter
javap -public -classpath dist/no-ctor.jar dev.lab.plugin.NeedsArgsGreeter
~~~

Ở HelloGreeter sẽ có public HelloGreeter(); ở NeedsArgsGreeter chỉ có public NeedsArgsGreeter(java.lang.String). Bảo đảm class provider là public, có thể gán vào SPI và có constructor thích hợp. Nếu constructor tự ném exception, xem cause thay vì chỉ thay đổi descriptor.

**Bước 5 — Phân biệt provider không tìm thấy và resource không tìm thấy.** Nếu duyệt ra **0 provider**, ưu tiên điều tra descriptor/classpath/loader. Nếu đã tạo provider nhưng method gặp lỗi, xem class/resource/dependency của implementation. Dùng HelloGreeter.class.getResourceAsStream("/messages/greeting.txt") để tra resource tương ứng với loader của class; không dùng đường dẫn trên đĩa như src/main/resources/messages/greeting.txt khi chương trình đang chạy JAR.

**Bước 6 — Xem exception đầy đủ khi debug.** Host lab cố tình chuẩn hóa lỗi; khi cần chẩn đoán chính xác, thay nội dung catch ServiceConfigurationError bằng lệnh:

~~~java
ex.printStackTrace(System.err);
~~~

Cần nhìn cả các lớp cause bên dưới, ví dụ provider class không tồn tại, sai kiểu, thiếu constructor, lỗi xảy ra bên trong constructor hoặc thiếu dependency runtime. Không mặc định mọi ServiceConfigurationError đều do sai tên descriptor.

## 8. Những khác biệt dễ gây nhầm lẫn

| Tình huống | Điều cần nhớ |
| --- | --- |
| Descriptor đặt sai tên nên provider không thấy | Thường cho kết quả duyệt rỗng; Java **không tìm mọi class implements SPI** để suy ra provider |
| Descriptor tồn tại nhưng chứa tên class sai | Duyệt có thể ném ServiceConfigurationError; không nên chuyển âm thầm thành “0 provider” |
| Class không viết constructor nào | Compiler có thể sinh default no-arg constructor; hãy kiểm tra access thực tế thay vì chỉ đọc mã nguồn sơ lược |
| Class có constructor chỉ nhận tham số | Không tự có no-arg constructor; ServiceLoader classpath không tự inject dependency |
| Constructor public nhưng ném lỗi | Vẫn là thất bại khởi tạo provider; xem exception cause |
| Provider đã được tạo nhưng phương thức cần resource còn thiếu | Lỗi xảy ra khi dùng provider; phụ thuộc vào cách implementation xử lý null/IO exception |
| File resource có thật trong source nhưng không có trong JAR | Chạy IDE có thể thành công, còn gói triển khai thất bại; kiểm tra **artifact đã build** |
| Tên class provider có nhưng nằm ngoài runtime classpath | Phát hiện descriptor vẫn có thể thất bại tại bước tải provider class |
| Plugin API xuất hiện dưới hai class loader khác nhau | Hai kiểu cùng tên không nhất thiết tương thích; duy trì SPI do loader dùng chung cung cấp |
| Có nhiều provider | Thứ tự discovery có thể phụ thuộc classpath và cấu hình loader; đừng dựa vào thứ tự ngẫu nhiên |
| Gọi ServiceLoader.load nhưng chưa iterate | Chưa kiểm chứng provider có thể được khởi tạo; hãy duyệt hoặc chủ động lấy provider |
| Provider ở JPMS module path | Quy tắc provider và khai báo module khác; phân biệt thí nghiệm classpath với module path |

**ClassLoader và TCCL:** overload ServiceLoader.load(Greeter.class) sử dụng context class loader của thread hiện tại để tìm provider; trong lệnh java -cp của lab, thread main mặc định nhìn thấy các JAR trên application classpath. Một host plugin phức tạp có loader riêng nên cân nhắc overload ServiceLoader.load(Greeter.class, pluginLoader), đồng thời bảo đảm API Greeter có danh tính class thống nhất. Nếu framework dùng thread context class loader (TCCL), host phải đặt/khôi phục nó đúng phạm vi, tránh làm rò ngữ cảnh giữa các plugin.

**Resource và ngoại lệ:** Class.getResourceAsStream("/x") nhận đường dẫn / từ gốc của classpath; ClassLoader.getResourceAsStream("x") dùng đường dẫn không có / đầu. Không dùng System.getProperty("user.dir") để suy vị trí resource trong JAR. Đọc resource bằng InputStream, đóng tài nguyên và kiểm tra null như trong ví dụ.

**Classpath và đóng gói:** Trong Maven/Gradle, class và src/main/resources thường được đưa vào JAR theo cấu hình mặc định, nhưng hãy xác nhận artifact cuối và các dependency runtime. Không nhầm classpath lúc **compile** với classpath lúc **chạy**. Đưa thêm thư viện vào build chưa chắc host đã nạp thư viện đó. Đừng đóng API SPI thành hai bản có loader riêng nếu hai phía phải trao đổi đối tượng SPI.

**Tính an toàn:** File descriptor chỉ là danh sách khai báo provider, không xác thực nhà cung cấp mã. Host cần kiểm soát plugin JAR được phép cài đặt, phiên bản API, nguồn artifact, quyền truy cập và xử lý lỗi/lifecycle. ServiceLoader không tự tạo sandbox cho plugin không tin cậy.

## 9. Bài tập củng cố và tiêu chí hoàn thành

Bạn có thể lặp lại thí nghiệm bằng những biến thể nhỏ, kiểm tra một yếu tố mỗi lần:

1. **Xóa descriptor khỏi good.jar:** tạo một JAR chỉ gồm class và resource. Dự đoán: NO_PROVIDER. Lý do: thiếu đăng ký service dù class đã có.
2. **Giữ descriptor đúng nhưng đổi nội dung thành class không implements Greeter:** ServiceLoader sẽ từ chối kiểu provider không tương thích. Cần có class tồn tại thực sự để phân biệt với trường hợp sai tên class.
3. **Bổ sung public no-arg constructor cho NeedsArgsGreeter, rồi build lại:** nếu constructor tạo được object hợp lệ, trường hợp no-ctor không còn lỗi constructor; hãy kiểm tra thêm giá trị trả về và resource nếu implementation cần.
4. **Đặt resource dưới tên messages/Greeting.txt thay vì messages/greeting.txt:** kiểm tra việc tìm đường dẫn chính xác khi triển khai trên hệ thống phân biệt chữ hoa/thường.
5. **Chạy host với hai plugin JAR đồng thời:** quan sát cách ServiceLoader phát hiện các cấu hình và nhận ra vì sao mỗi thử nghiệm ban đầu phải chạy trong tiến trình có classpath xác định.

Một thí nghiệm được coi là hoàn tất khi bạn giải thích đúng:

- **NO_PROVIDER** nghĩa là ServiceLoader không tìm thấy provider được khai báo cho service cần nạp trong classpath hiện tại (ở thí nghiệm tương ứng).
- **CONFIG_ERROR** là lỗi lúc đọc/diễn giải provider declaration hoặc nạp/khởi tạo provider; phải xem nguyên nhân để biết chính xác tên class hay constructor.
- **RESOURCE_ERROR** ở lab xuất hiện **sau khi provider đã tạo được**, do implementation không tìm thấy file dữ liệu cần thiết.
- Sửa lỗi phải thực hiện ở **đúng tầng**: tên descriptor, nội dung descriptor, constructor/provider, hay resource nằm trong JAR phát hành.

Cách kiểm tra có giá trị nhất là **đóng JAR thật, chỉ nạp đúng artifact cần thử, duyệt ServiceLoader và quan sát từng giai đoạn**. Khi phân biệt được discovery, instantiation và execution, bạn sẽ tránh được việc sửa nhầm code Java cho một lỗi packaging, hoặc sửa descriptor khi nguyên nhân thực chất là resource bị bỏ quên.