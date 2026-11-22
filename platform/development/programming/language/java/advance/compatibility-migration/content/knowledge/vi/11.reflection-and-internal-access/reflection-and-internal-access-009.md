# Chuỗi tên lớp trong cấu hình mà `jdeps` không phát hiện

Một ứng dụng Java có thể vượt qua bước biên dịch, chạy `jdeps` mà không thấy phụ thuộc đáng ngờ, nhưng vẫn lỗi sau khi nâng JDK hoặc nâng thư viện. Nguyên nhân đôi khi không nằm ở lời gọi Java được viết trực tiếp trong source code, mà nằm ở **tên class được lưu dưới dạng chuỗi**: trong file `.properties`, YAML, XML, JSON, biến môi trường, bảng cấu hình hoặc metadata của plugin. Khi runtime đọc chuỗi đó rồi gọi `Class.forName(...)`, `ClassLoader.loadClass(...)` hoặc một framework dùng reflection, JVM mới thực sự tìm và sử dụng class tương ứng.

`jdeps` là công cụ hữu ích để phân tích **các phụ thuộc tĩnh trong class file/JAR**. Nó không phải công cụ chạy ứng dụng và không thể suy ra đầy đủ những class sẽ được nạp từ dữ liệu cấu hình. Vì thế, kết quả `jdeps` không báo phụ thuộc **không chứng minh** rằng ứng dụng không dùng một class nội bộ, class đã bị đổi tên hoặc dependency tùy chọn ở runtime.

Trong Java Advance Compatibility Migration, đây là một khoảng mù quan trọng: class chỉ được tham chiếu qua chuỗi cấu hình có thể không xuất hiện như một tham chiếu kiểu trong constant pool mà `jdeps` dựa vào để lập đồ thị phụ thuộc. Bài học này giải thích cơ chế, tình huống thường gặp và cách kết hợp phân tích tĩnh với kiểm tra cấu hình và quan sát runtime để không bỏ sót các phụ thuộc động.

## 1. Phụ thuộc tĩnh và phụ thuộc động khác nhau thế nào?

### 1.1. Phụ thuộc tĩnh: class được tham chiếu bằng kiểu Java

Xét mã:

```java
package com.example.app;

import com.example.plugins.FastNormalizer;

public class Processor {
    public String process(String input) {
        return new FastNormalizer().normalize(input);
    }
}
```

Để biên dịch class này, compiler cần biết kiểu `FastNormalizer`. Class file của `Processor` có các tham chiếu biểu tượng tới class và member tương ứng. Công cụ phân tích bytecode như `jdeps` có cơ sở để tìm quan hệ phụ thuộc đó khi các class và đường dẫn đầu vào được cung cấp phù hợp.

Đây là phụ thuộc **có thể quan sát bằng phân tích tĩnh**: nếu class được dùng đã đổi package, bị xóa hoặc chuyển khỏi JAR, mã nguồn hoặc binary consumer có thể bị ảnh hưởng. `jdeps` giúp lập danh sách những dependency như vậy nhưng không thay thế kiểm tra hành vi runtime.

### 1.2. Phụ thuộc động: tên class là dữ liệu

Bây giờ xét mã:

```java
package com.example.app;

public class Processor {
    public Object create(String className) throws Exception {
        Class<?> type = Class.forName(className);
        return type.getDeclaredConstructor().newInstance();
    }
}
```

Chương trình không import `FastNormalizer`. Bytecode chỉ cần biết các API chuẩn như `Class`, `Constructor` và `Object`. Tên class cụ thể có thể được cung cấp lúc chạy:

```properties
processor.implementation=com.example.plugins.FastNormalizer
```

Một lần chạy khác có thể dùng:

```properties
processor.implementation=com.example.plugins.LegacyNormalizer
```

Với cùng một file `Processor.class`, hai cấu hình có thể nạp hai implementation khác nhau. Không có yêu cầu compiler phải ghi một tham chiếu kiểu tới từng implementation trong class file của `Processor`. Công cụ chỉ phân tích dependency tĩnh không thể biết những tên class nào sẽ xuất hiện trong cấu hình của môi trường production.

### 1.3. Điểm khác biệt quyết định kết quả phân tích

| Đặc điểm | Tham chiếu kiểu trực tiếp | Tên class trong chuỗi cấu hình |
|---|---|---|
| Ví dụ | `new FastNormalizer()` | `Class.forName(configuredName)` |
| Kiểm tra tại compile time | Compiler biết kiểu và API được gọi | Compiler không biết class name cuối cùng nếu nó đến từ cấu hình |
| Dấu vết trong class file consumer | Thường có tham chiếu class/member | Có thể chỉ thấy API reflection và chuỗi/logic đọc cấu hình |
| `jdeps` suy ra phụ thuộc tới implementation | Có thể khi tham chiếu tĩnh tồn tại | Không thể suy ra chắc chắn từ tên chỉ có trong cấu hình ngoài |
| Thời điểm phát hiện thiếu class | Compile hoặc runtime tùy cách đóng gói | Thường chỉ khi runtime cố nạp class |
| Nguy cơ sau migration | Thay đổi bytecode/API, module, JAR | Ngoài các nguy cơ trên còn có cấu hình cũ, tên class cũ, nạp động |

Cần phân biệt hai ý: `jdeps` **có thể phân tích JAR chứa implementation** nếu đưa JAR đó làm đầu vào; nhưng kết quả phân tích JAR ứng dụng **không tự chứng minh rằng ứng dụng sẽ nạp implementation đó qua cấu hình**. Vấn đề ở đây là thiếu *đường liên kết động từ dữ liệu cấu hình đến class thực tế*.

## 2. `jdeps` thực sự quan sát những gì?

`jdeps` là công cụ đi kèm JDK, dùng để phân tích các phụ thuộc của Java class file, JAR và module. Các chế độ phổ biến hỗ trợ xem dependency theo package, class hoặc module.

Ví dụ:

```bash
jdeps --summary application.jar
```

Hoặc xem mức class:

```bash
jdeps --verbose:class --recursive application.jar
```

Khi các dependency ngoài được đặt ở thư mục `libs`, có thể bổ sung classpath để phân tích:

```bash
jdeps --class-path 'libs/*' --verbose:class --recursive application.jar
```

`jdeps` có thể giúp xác định module và package được tham chiếu, kiểm tra phụ thuộc tới JDK internal APIs theo những tham chiếu tĩnh mà nó quan sát được, và hỗ trợ lập kế hoạch modularization. Chẳng hạn:

```bash
jdeps --jdk-internals application.jar
```

Tuy nhiên, `--jdk-internals` không biến công cụ thành máy dò mọi cách dùng API nội bộ. Nếu ứng dụng chỉ đọc chuỗi `"jdk.internal.misc.Unsafe"` từ file cấu hình rồi nạp class bằng reflection, có thể không có tham chiếu class tĩnh tới `Unsafe` để `jdeps` báo cáo.

### 2.1. Những gì `jdeps` không thể suy luận đầy đủ

- Tên class được đọc từ file `.properties`, YAML, XML, JSON hoặc database tại runtime.
- Tên class được hình thành bằng ghép chuỗi, convention hoặc tên môi trường.
- Class nạp bởi custom `ClassLoader`, plugin framework hoặc `URLClassLoader` từ một thư mục ngoài artifact chính.
- Các provider được tìm qua tài nguyên `META-INF/services/` chỉ nhờ tên provider trong nội dung file cấu hình dịch vụ.
- Class/constructor/method được chọn bằng annotation metadata hoặc cấu hình framework khi không tồn tại tham chiếu kiểu trực tiếp trong code đang phân tích.
- Dependency chỉ xuất hiện ở một tenant, profile, feature flag hoặc một nhánh lỗi ít dùng.
- Những đường nạp class do script khởi động, agent, container hoặc hạ tầng triển khai kích hoạt.

Không phải mọi trường hợp trên đều hoàn toàn vô hình với mọi chế độ phân tích: ví dụ, một module descriptor có thể khai báo `uses` hoặc `provides`, và bytecode của provider có thể có tham chiếu tĩnh của riêng nó. Điểm cốt lõi là **đồ thị dependency tĩnh không phải đồ thị mọi class sẽ được thực thi trong toàn bộ cấu hình runtime**.

### 2.2. Vì sao `jdeps` sạch vẫn chưa phải kết luận migration an toàn?

Giả sử:

```text
application.jar
   |
   | class file tham chiếu java.base và API reflection
   v
jdeps chỉ thấy dependency tĩnh quen thuộc

production.properties
   |
   | implementation=com.example.legacy.OldConnector
   v
Class.forName(...)
   |
   v
legacy-connector.jar (chỉ nạp ở production)
```

Nếu bản JAR `legacy-connector.jar` bị loại khỏi image mới, `jdeps application.jar` không có lý do để cảnh báo rằng cấu hình production sẽ thiếu class. Lỗi chỉ xuất hiện khi code chạy đến đoạn tải connector tương ứng. Nếu connector tự dùng API nội bộ của JDK, ứng dụng còn có thể vượt qua việc tìm class nhưng thất bại khi gọi reflection hoặc method trong class đó.

## 3. Tên class có thể nằm ở đâu trong một hệ thống Java?

Không chỉ file `.properties` mới chứa tên class. Trong hệ thống thực tế, một implementation thường được chọn bởi metadata cấu hình trải rộng trên repository, artifact và hạ tầng triển khai.

### 3.1. File `.properties`

```properties
payment.gateway.class=com.example.payment.LegacyGateway
report.renderer.class=com.example.report.PdfRenderer
```

Ứng dụng dùng `Properties` hoặc một thư viện config để đọc giá trị. Nếu package `com.example.payment` đổi tên, source vẫn biên dịch được nhưng runtime có thể lỗi khi nạp `LegacyGateway`.

### 3.2. YAML và JSON

```yaml
pipeline:
  handlerClass: com.example.pipeline.LegacyHandler
```

```json
{
  "serializerClass": "com.example.serialize.CustomSerializer"
}
```

Framework có thể dùng `handlerClass` hoặc `serializerClass` làm dữ liệu để tạo object. Một lần đổi tên package trong code chưa chắc cập nhật các file cấu hình được triển khai độc lập.

### 3.3. XML và metadata framework

```xml
<component
    name="auditPublisher"
    class="com.example.audit.FileAuditPublisher" />
```

Một XML trong resources, JAR phụ thuộc hoặc thư mục cấu hình bên ngoài cũng có thể xác định class runtime. Một số framework nhận tên fully qualified class, một số nhận alias hoặc ID rồi ánh xạ sang class. Cần hiểu cấu trúc của từng framework; không thể giả định tên property chung cho tất cả.

### 3.4. Java SPI với `META-INF/services/`

Java Service Provider Interface có thể đăng ký implementation trong file tài nguyên. Giả sử có service interface:

```java
package com.example.spi;

public interface Encoder {
    byte[] encode(String value);
}
```

Một JAR provider có file:

```text
META-INF/services/com.example.spi.Encoder
```

Nội dung file:

```text
com.example.providers.Utf8Encoder
```

Client dùng:

```java
ServiceLoader<Encoder> providers = ServiceLoader.load(Encoder.class);
for (Encoder provider : providers) {
    System.out.println(provider.getClass().getName());
}
```

Client có tham chiếu tĩnh tới **service interface** `Encoder`, nhưng tên provider `Utf8Encoder` có thể chỉ được khai báo trong tài nguyên dịch vụ của JAR. Phân tích `jdeps` của client không bảo đảm sẽ tìm và xác thực được mọi tên provider trong file dịch vụ. Khi có provider sai tên, không còn class, không có constructor/provider method phù hợp hoặc lỗi nạp class, `ServiceLoader` có thể báo `ServiceConfigurationError`.

Với *named modules*, dịch vụ cũng có thể được khai báo bằng `uses` và `provides ... with ...` trong `module-info.java`. Đây là metadata module, không phải chuỗi tên class tùy ý trong file `.properties`; cần kiểm tra cả hai hình thức khi hệ thống pha trộn classpath và module path.

### 3.5. Biến môi trường, system property và nguồn dữ liệu ngoài

```bash
java -Dapp.handlerClass=com.example.handlers.FastHandler \
     -jar application.jar
```

```java
String name = System.getProperty("app.handlerClass");
Class<?> type = Class.forName(name);
```

Giá trị thực có thể được đặt trong Docker Compose, Kubernetes manifest, Helm chart, secret/config management, startup script hoặc giao diện quản trị. Nếu chỉ rà soát source repository, có thể bỏ qua chính cấu hình đang chạy trên production.

Trong một số hệ thống, tên class còn được lưu trong database hoặc gửi tới ứng dụng qua một dịch vụ cấu hình. Cần xem các nguồn đó như một phần của inventory migration, đồng thời tránh in dữ liệu nhạy cảm ra log hoặc đưa file secret vào repository.

## 4. Ví dụ end-to-end: class chỉ tồn tại trong cấu hình

Giả sử ứng dụng có nhiệm vụ chuẩn hóa chuỗi, nhưng implementation được chọn lúc runtime. Mã ứng dụng không import class plugin nào.

### 4.1. Source ứng dụng

File `src-app/com/example/app/ConfiguredNormalizer.java`:

```java
package com.example.app;

import java.io.InputStream;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class ConfiguredNormalizer {
    public static void main(String[] args) throws Exception {
        Properties config = new Properties();

        try (InputStream in = Files.newInputStream(Path.of("plugin.properties"))) {
            config.load(in);
        }

        String className = config.getProperty("normalizer.class");
        if (className == null || className.isBlank()) {
            throw new IllegalArgumentException("normalizer.class is required");
        }

        Class<?> type = Class.forName(className);
        Object instance = type.getDeclaredConstructor().newInstance();
        Method normalize = type.getMethod("normalize", String.class);
        Object result = normalize.invoke(instance, "  Hello Java  ");

        System.out.println(result);
    }
}
```

Ví dụ dùng Java 11 trở lên (`Path.of` và `String.isBlank`). Để bài tập đơn giản, ứng dụng gọi method bằng reflection hoàn toàn; thiết kế production tốt hơn nên dùng interface có kiểu rõ ràng và giới hạn implementation được cho phép.

### 4.2. Source plugin

File `src-plugin/com/example/plugins/FastNormalizer.java`:

```java
package com.example.plugins;

public class FastNormalizer {
    public FastNormalizer() {
    }

    public String normalize(String input) {
        return input.strip().toLowerCase(java.util.Locale.ROOT);
    }
}
```

File `plugin.properties`:

```properties
normalizer.class=com.example.plugins.FastNormalizer
```

Ứng dụng có thể được biên dịch mà không cần plugin JAR trên compile classpath. Chỉ đến runtime mới cần plugin thực sự tồn tại.

### 4.3. Biên dịch và đóng gói

Ví dụ với shell kiểu Unix:

```bash
mkdir -p out-app out-plugin

javac -d out-app src-app/com/example/app/ConfiguredNormalizer.java
javac -d out-plugin src-plugin/com/example/plugins/FastNormalizer.java

jar --create --file app.jar -C out-app .
jar --create --file normalizer-plugin.jar -C out-plugin .
```

Phân tích ứng dụng:

```bash
jdeps --verbose:class app.jar
```

Phân tích này có thể hiển thị các dependency tới `java.base` và các API dùng trong code ứng dụng, nhưng không nhất thiết có dòng phụ thuộc tới `com.example.plugins.FastNormalizer`: tên lớp đó chỉ nằm trong `plugin.properties`, không phải kiểu mà `ConfiguredNormalizer.class` tham chiếu trực tiếp.

Chạy chương trình với JAR plugin:

```bash
java -cp 'app.jar:normalizer-plugin.jar' \
     com.example.app.ConfiguredNormalizer
```

Kết quả mong đợi:

```text
hello java
```

Nếu bỏ `normalizer-plugin.jar` khỏi runtime classpath:

```bash
java -cp app.jar com.example.app.ConfiguredNormalizer
```

Chương trình có thể thất bại với `ClassNotFoundException: com.example.plugins.FastNormalizer`, dù bản thân `app.jar` vẫn được biên dịch và `jdeps` vẫn phân tích được.

Trên Windows, dấu phân tách classpath là dấu chấm phẩy (`;`), ví dụ `-cp 'app.jar;normalizer-plugin.jar'` trong PowerShell. File `plugin.properties` ở ví dụ trên được đọc từ **working directory** của tiến trình; chạy từ thư mục khác cần đặt file đúng vị trí hoặc sửa code để nhận đường dẫn cấu hình.

### 4.4. Đổi tên class tạo ra lỗi mà build không phát hiện

Giả sử trong phiên bản sau, plugin đổi thành `com.example.plugins.StandardNormalizer`, nhưng file cấu hình production vẫn chứa:

```properties
normalizer.class=com.example.plugins.FastNormalizer
```

Nếu class cũ không còn trong artifact, runtime sẽ cố nạp tên cũ và thất bại. Việc biên dịch lại ứng dụng không sửa được chuỗi cấu hình ngoài JAR. Đây là một ví dụ điển hình của *source build thành công nhưng deployment không tương thích với cấu hình thực tế*.

Ngay cả khi class mới có method `normalize(String)` giống class cũ, reflection không tự động ánh xạ tên class cũ sang tên class mới.

## 5. Các lỗi runtime có thể xuất hiện sau khi tìm được tên class

Tìm được chuỗi tên class là điều kiện đầu tiên, không phải kết thúc kiểm thử. Runtime còn phải tìm thấy class, xác minh bytecode, kiểm tra quyền truy cập, khởi tạo và thực thi phần chức năng mà framework mong đợi.

| Lỗi hoặc exception | Bối cảnh thường gặp | Cần kiểm tra |
|---|---|---|
| `ClassNotFoundException` | `Class.forName` hoặc class loader không tìm thấy tên trong cấu hình | Tên class, JAR, classpath/module path, class loader |
| `NoClassDefFoundError` | Class được cần đến khi liên kết/sử dụng nhưng dependency thiếu hoặc class từng khởi tạo thất bại | Dependency runtime, cause ban đầu, classpath |
| `UnsupportedClassVersionError` | Plugin được build cho class file version mới hơn JVM đang chạy | JDK build và runtime, `--release`, bytecode version |
| `ClassFormatError` hoặc `VerifyError` | Bytecode plugin không hợp lệ hoặc bị công cụ biến đổi sai | Agent, proxy/bytecode generator, artifact thực tế |
| `NoSuchMethodException` | Reflection tìm constructor/method với chữ ký không tồn tại | API runtime của plugin, tên và kiểu tham số |
| `IllegalAccessException` | Java reflection không có quyền gọi member | Modifier, module access, cách gọi reflection |
| `InaccessibleObjectException` | Deep reflection bị JPMS strong encapsulation chặn | `opens`, caller module, framework/JDK |
| `InvocationTargetException` | Method được gọi qua reflection đã ném exception | `getCause()` để tìm lỗi logic gốc |
| `ExceptionInInitializerError` | Static initializer trong plugin thất bại | Biến môi trường, dependency, code khởi tạo |
| `ClassCastException` | Plugin không thực sự implement interface/ký kết kiểu mà ứng dụng yêu cầu hoặc class loader khác nhau | API/SPI, class loader, JAR trùng |
| `ServiceConfigurationError` | SPI provider đăng ký sai hoặc không thể tải/tạo | File `META-INF/services`, module declarations, provider |

Không nên sửa mọi lỗi bằng cách thêm một JVM flag. Mỗi nhóm phản ánh một giai đoạn hoặc hợp đồng khác nhau. Ví dụ, `--add-opens` không làm một class bị thiếu xuất hiện trên classpath; `--add-exports` không sửa method đã bị đổi descriptor; nâng JVM không tự sửa tên class sai trong YAML.

### 5.1. Reflection trên API nội bộ của JDK

Rủi ro rõ rệt khi nâng JDK là tên class nội bộ nằm trong cấu hình, chẳng hạn một class ở package `jdk.internal.*`. Nếu code chỉ đọc tên này từ properties rồi `Class.forName`, `jdeps --jdk-internals` trên consumer có thể không hiển thị phụ thuộc mong đợi.

Nhưng khi runtime cố truy cập sâu vào thành viên của một class nội bộ, JPMS có thể chặn do package không được export hoặc open. Từ những JDK đã áp dụng strong encapsulation, việc gọi `setAccessible(true)` vào thành viên không public của package nội bộ có thể ném `InaccessibleObjectException`.

Điều tra cần xác định **thư viện nào** yêu cầu tên class nội bộ, nó dùng API gì và có phiên bản thay thế dùng API chuẩn không. Trong một số trường hợp có thể dùng `--add-opens` hoặc `--add-exports` như biện pháp tạm thời có phạm vi rõ ràng, nhưng nên ưu tiên nâng framework, thư viện hoặc chuyển sang API được hỗ trợ.

## 6. Class loader và JPMS làm bài toán phức tạp hơn

### 6.1. Một class có trên disk vẫn có thể không được loader tìm thấy

Class loader quyết định namespace và khả năng nhìn thấy class. Trong ứng dụng plugin, servlet container hoặc framework, class có thể nằm trong JAR nhưng được nạp bởi loader khác với loader mà `Class.forName` đang sử dụng.

`Class.forName(String)` dùng loader xác định theo ngữ cảnh caller; một số framework lại dùng *thread context class loader*:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName(className, false, loader);
```

Tham số `false` yêu cầu không khởi tạo class như một phần của lời gọi đó. Nó không bảo đảm class sẽ khởi tạo hoặc thực thi thành công về sau.

Khi lỗi chỉ xuất hiện trong plugin hoặc container, cần ghi lại class loader thực tế, đường dẫn class source và cơ chế parent delegation. Không nên mặc định rằng mọi class trên hệ thống đều được application class loader nhìn thấy.

### 6.2. Cùng tên class nhưng khác class loader

JVM phân biệt kiểu theo tên nhị phân **và class loader định nghĩa**. Hai loader khác nhau có thể định nghĩa hai class cùng tên nhưng hai kiểu không tương đương. Một plugin mang theo bản sao của API được chia sẻ với host có thể gặp `ClassCastException` dù tên class trong thông báo trông giống nhau.

Vì vậy, inventory dependency động cần ghi cả vị trí JAR và loader nạp class. Chỉ kiểm tra tên fully qualified class chưa đủ khi dùng hệ plugin hoặc application server.

### 6.3. Named module, `exports` và `opens`

Với JPMS, một JAR plugin đặt trên module path có thể thuộc named module, automatic module hoặc không được đưa vào module graph tùy cấu hình. Tên class đúng và JAR có trên module path chưa bảo đảm class được resolve và truy cập hợp lệ.

Trong named module:

- `requires` (hoặc quan hệ đọc tương đương theo cấu hình) quyết định module nào đọc được module nào.
- `exports` công bố các public type của package cho truy cập Java thông thường từ module được phép.
- `opens` cho phép deep reflection đến package trong phạm vi chỉ định.

Nếu một framework cần gọi constructor hoặc đọc private field qua reflection, package có thể cần `opens` cho module framework. Không nên dùng `--add-opens` để che mọi lỗi truy cập khi thực tế thiếu module, export hoặc dependency.

### 6.4. Automatic module và unnamed module trong migration

Các JAR trên classpath thường thuộc unnamed module; JAR không có descriptor đặt trên module path có thể trở thành automatic module. Việc chuyển JAR từ classpath sang module path có thể thay đổi cách module resolution, package access và service loading hoạt động.

Một cấu hình plugin từng chạy được trên classpath có thể lỗi sau khi chuyển sang named modules vì module chưa được đưa vào graph hoặc package không được mở đúng cách. Khi test migration, cần dùng đúng cơ chế triển khai của production chứ không chỉ test trên classpath cho tiện.

## 7. Làm thế nào để tìm những chuỗi tên class bị bỏ sót?

Vì `jdeps` không nhìn thấy toàn bộ dữ liệu runtime, cần bổ sung **inventory cấu hình**. Đây không phải một lệnh có thể đảm bảo tìm được mọi tên class; cần phối hợp nhiều nguồn.

### 7.1. Tìm trong source và resources

Có thể bắt đầu bằng một đợt tìm kiếm theo các API và key thường gặp:

```bash
rg -n 'Class\.forName|loadClass\(|getDeclaredConstructor|ServiceLoader|setAccessible' \
  src

rg -n 'className|class-name|class:|implementation|provider|driverClass|factory' \
  src/main/resources config
```

Các lệnh dùng công cụ `rg` (ripgrep) nếu đã cài. Đây là gợi ý tìm kiếm, không phải bộ quy tắc áp dụng cho mọi framework; tùy dự án, tên cấu hình có thể là `type`, `strategy`, `adapter`, `dialect` hoặc key do nhóm tự định nghĩa.

Để tìm tên class trong nhiều file cấu hình, có thể tìm các chuỗi dạng tên package quen thuộc:

```bash
rg -n 'com\.example\.|org\.|jdk\.internal\.|sun\.' \
  config src/main/resources
```

Kết quả cần được phân loại thủ công theo ngữ cảnh: không phải chuỗi có dấu chấm nào cũng là tên class; URL, tên package, logger và tên bean có thể có hình thức tương tự.

### 7.2. Kiểm tra resources bên trong JAR

```bash
jar --list --file application.jar
jar --list --file plugin.jar
```

Chú ý các file như:

```text
META-INF/services/*
META-INF/spring/*
*.properties
*.xml
*.json
*.yaml
*.yml
```

Không phải mọi JAR đều có cấu trúc giống nhau. Với Spring Boot executable JAR hoặc artifact đóng gói nested JAR, cần hiểu loader và cách resources được chứa bên trong. Nếu plugin được tải từ thư mục riêng lúc chạy, phải kiểm tra cả thư mục đó, không chỉ application JAR.

### 7.3. Rà soát cấu hình vận hành

Với hệ thống nhiều môi trường, hãy xem các nguồn cấu hình thực sự được sử dụng:

- File config được mount vào container hoặc VM.
- Biến môi trường và system properties được truyền trong startup script.
- Kubernetes ConfigMap, Helm values hoặc cơ chế quản lý cấu hình tương ứng.
- Thông tin đăng ký plugin trong database hoặc dịch vụ quản lý feature flag.
- Cấu hình theo profile như `dev`, `test`, `staging`, `prod`.
- Cấu hình theo khách hàng/tenant và phiên bản cũ đang tồn tại.

Lưu ý không in toàn bộ secret vào log để phục vụ inventory. Có thể trích xuất key và danh sách class name sau khi loại bỏ thông tin nhạy cảm.

### 7.4. Lập bảng inventory phụ thuộc động

Một bảng theo dõi hữu ích có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| Config source | File, key, biến môi trường hoặc dịch vụ cấu hình cung cấp tên class |
| Effective value | Tên class được dùng sau khi profile và override được áp dụng |
| Loader/module | Class loader hoặc module dự kiến nạp class |
| Artifact | JAR, image, plugin bundle chứa class |
| Instantiation path | `Class.forName`, `ServiceLoader`, framework factory hoặc mechanism khác |
| Contract | Interface, constructor, method, annotation hoặc metadata bắt buộc |
| Environment | Dev/test/staging/prod/tenant áp dụng cấu hình |
| Migration risk | Missing class, API đổi, reflection bị chặn, bytecode quá mới, v.v. |
| Verification | Test hoặc log chứng minh class nạp và hoạt động |
| Owner/status | Nhóm chịu trách nhiệm và trạng thái xử lý |

Ví dụ:

| Config source | Effective value | Rủi ro khi nâng JDK | Test tối thiểu |
|---|---|---|---|
| `plugin.properties:normalizer.class` | `com.example.plugins.FastNormalizer` | Thiếu JAR hoặc class bị đổi package | Nạp, tạo instance và gọi `normalize` |
| `META-INF/services/...Encoder` | `com.example.providers.Utf8Encoder` | Provider chưa được đóng gói hoặc module chưa resolve | Duyệt `ServiceLoader` và gọi `encode` |
| Property dùng bởi framework legacy | Một class `jdk.internal.*` | Deep reflection bị strong encapsulation chặn | Khởi tạo framework và chạy luồng tích hợp thực tế |

Inventory là một phần của migration plan; tránh kết luận “không có rủi ro” khi chưa xác nhận effective configuration của các môi trường liên quan.

## 8. Quan sát class loading ở runtime

Phân tích cấu hình giúp tìm ứng viên. Chạy ứng dụng trong điều kiện đại diện giúp xác nhận class nào **thực sự được nạp** và từ đâu.

### 8.1. Unified logging của JVM

Trên các JDK hiện đại, có thể bật log class loading:

```bash
java -Xlog:class+load=info -cp 'app.jar:plugin.jar' \
  com.example.app.ConfiguredNormalizer
```

Output có thể bao gồm tên class và nguồn nạp, tùy JDK và mức log. Vì log khá lớn, nên thu thập trong môi trường kiểm thử, lọc theo package/plugin hoặc lưu thành file có chính sách bảo vệ thông tin phù hợp.

Mục tiêu là trả lời những câu hỏi cụ thể:

- Class được cấu hình có được nạp hay không?
- Nó được nạp từ JAR hoặc module nào?
- Có nhiều JAR chứa class trùng tên không?
- Việc nạp có xảy ra ở startup hay chỉ khi một feature được kích hoạt?

Nếu plugin được nạp qua custom class loader, log class loading là một nguồn bằng chứng bổ sung rất hữu ích khi classpath tĩnh của ứng dụng không thể hiện đầy đủ hệ plugin.

### 8.2. Ghi log tại điểm chọn implementation

Ở đoạn code chủ động đọc tên class từ cấu hình, nên có log cấu trúc hoặc diagnostic giúp xác định key cấu hình, tên class sau khi resolve và kết quả nạp:

```java
String className = config.getProperty("normalizer.class");
System.out.println("Selected normalizer class: " + className);

Class<?> type = Class.forName(className);
System.out.println("Loaded class from: " +
    type.getProtectionDomain().getCodeSource());
```

Đây là minh họa cho môi trường kiểm thử; `CodeSource` có thể là `null` trong một số trường hợp, và không nên ghi dữ liệu cấu hình bí mật vào log. Ở production, sử dụng logger có kiểm soát thay vì `System.out.println`, đồng thời phân loại thông tin được phép ghi.

### 8.3. Test nhiều profile và feature path

Một class nằm trong cấu hình chưa chắc được nạp ngay khi khởi động. Ví dụ, handler cho loại giao dịch hiếm, provider theo tenant hoặc fallback khi backend lỗi có thể chỉ được kích hoạt ở một nhánh cụ thể.

Vì vậy, smoke test khởi động thành công không đủ. Nên chạy các trường hợp có thể kích hoạt những tên class khác nhau, bao gồm profile production, plugin tùy chọn, error path và feature flag.

## 9. Kiểm thử hợp đồng động thay vì chỉ kiểm tra class tồn tại

Một số kiểm thử dừng tại `Class.forName(name)` rồi cho rằng migration đã thành công. Điều này chỉ chứng minh class được tìm thấy (và có thể đã khởi tạo tùy overload), không bảo đảm nó tương thích với framework hoặc API được mong đợi.

### 9.1. Dùng interface thay vì gọi method theo tên nếu có thể

Thay vì reflection tự do:

```java
Object object = Class.forName(className)
    .getDeclaredConstructor()
    .newInstance();
```

hãy thiết kế một hợp đồng kiểu cụ thể:

```java
package com.example.spi;

public interface Normalizer {
    String normalize(String input);
}
```

Và nạp implementation có kiểm tra kiểu:

```java
Class<?> rawType = Class.forName(className);
Class<? extends Normalizer> implementation =
    rawType.asSubclass(Normalizer.class);

Normalizer normalizer = implementation
    .getDeclaredConstructor()
    .newInstance();

String result = normalizer.normalize("Example");
```

`asSubclass` giúp phát hiện sớm trường hợp class được cấu hình không thực hiện interface mong đợi. Tuy nhiên, constructor vẫn có thể không tồn tại, không public hoặc ném exception; cần test đầy đủ đường khởi tạo và lời gọi nghiệp vụ.

### 9.2. Kiểm tra các ràng buộc constructor và method

Nếu framework yêu cầu constructor không tham số, hãy kiểm tra `getDeclaredConstructor()` và điều kiện quyền truy cập. Nếu framework yêu cầu method với chữ ký nhất định, kiểm tra cả kiểu tham số/return thay vì chỉ tên method.

Khi framework dùng annotation, generic metadata hoặc named modules, cần xác minh các điều kiện đó theo bản framework/JDK mục tiêu. Chỉ có interface đúng chưa chắc đủ nếu framework vẫn cần reflection vào thành viên private.

### 9.3. Test chất lượng cho SPI

Một bài test SPI nên duyệt provider thực tế và sử dụng chúng:

```java
import com.example.spi.Normalizer;
import java.util.ServiceLoader;

public class ProviderSmokeTest {
    public static void main(String[] args) {
        int count = 0;
        for (Normalizer normalizer : ServiceLoader.load(Normalizer.class)) {
            count++;
            System.out.println(normalizer.normalize("  JAVA  "));
        }
        if (count == 0) {
            throw new IllegalStateException("No Normalizer providers found");
        }
    }
}
```

Đoạn minh họa cần có service interface và provider được đóng gói đúng. Nếu service không bắt buộc ở mọi profile, điều kiện `count == 0` phải được điều chỉnh theo chính sách của môi trường, thay vì áp dụng máy móc.

### 9.4. Kiểm thử binary đã phát hành

Khi migration thư viện, có thể cần giữ client JAR cũ và chạy cùng runtime/dependency mới. Nếu tên class trong config trỏ đến implementation cũ, hãy xác minh cả việc tạo instance và gọi API mà client kỳ vọng. Nếu sửa/biên dịch lại mọi thứ trước khi test, có thể bỏ qua lỗi mà artifact production cũ vẫn gặp.

## 10. Kết hợp `jdeps` với các nguồn bằng chứng khác

Không nên bỏ `jdeps` chỉ vì nó có điểm mù. Cách phù hợp là dùng mỗi nguồn cho câu hỏi mà nó trả lời tốt nhất.

| Nguồn/công cụ | Trả lời tốt | Không chứng minh đầy đủ |
|---|---|---|
| `jdeps` | Dependency tĩnh ở mức class/JAR/module, tham chiếu tới JDK internals dạng tĩnh | Class name đến từ dữ liệu cấu hình hoặc hành vi runtime |
| Tìm kiếm source/config | Những string literal, config keys và tên provider được lưu dưới dạng text | Giá trị được dựng động, override ngoài repository, code ít dùng |
| `jar --list` và kiểm tra resource | Artifact nào chứa class/resource khai báo provider | Class thực sự được nạp trong tiến trình |
| `javap -verbose`/`-s` | Class file version, constant pool, member descriptor | Cấu hình runtime, module graph đầy đủ, hành vi framework |
| `-Xlog:class+load=info` | Class thực sự được nạp trong những đường chạy đã thử | Class chưa được nạp ở nhánh chưa test |
| Integration/contract test | Có nạp, khởi tạo và thực thi được không | Mọi profile, tenant hoặc điều kiện production chưa được bao phủ |
| Release notes/migration guide | Thành phần JDK/framework đổi hoặc bị loại bỏ | Ứng dụng cụ thể có đang dùng thành phần đó qua config hay không |

### 10.1. Phân tích JAR plugin riêng

Nếu tìm được `legacy-connector.jar` trong inventory, có thể chạy:

```bash
jdeps --jdk-internals legacy-connector.jar
jdeps --verbose:class --recursive legacy-connector.jar
```

Khi phân tích cả plugin, bạn có thể phát hiện các phụ thuộc **tĩnh bên trong plugin** mà `jdeps` của ứng dụng chính không thấy. Nhưng nếu plugin cũng dùng cấu hình chuỗi hoặc reflection, điểm mù tương tự vẫn tồn tại và cần được kiểm tra tiếp.

### 10.2. Lưu ý multi-release JAR

Một JAR có thể chứa các class dành riêng cho những phiên bản Java khác nhau trong `META-INF/versions/`. Khi dùng `jdeps` với multi-release JAR, cần chọn tùy chọn phân tích phù hợp với phiên bản mục tiêu, ví dụ:

```bash
jdeps --multi-release 17 --verbose:class library.jar
```

Điều này giúp tránh chỉ xem class cơ sở rồi bỏ sót dependency của biến thể được dùng trên JDK mục tiêu. Dù vậy, nó vẫn không giải quyết bài toán tên class được cung cấp bằng cấu hình ngoài JAR.

## 11. Quy trình migration đối với phụ thuộc qua chuỗi cấu hình

Một quy trình thực dụng có thể chia thành các bước sau.

### Bước 1: Xác định môi trường mục tiêu

Ghi phiên bản JDK hiện tại và mục tiêu, vendor/build, framework, module path/classpath, các plugin JAR và cấu hình khởi động. Phân biệt compiler JDK với JVM runtime thực sự.

### Bước 2: Chạy phân tích tĩnh

Sử dụng `jdeps` trên ứng dụng và các JAR quan trọng để lập danh sách dependency tĩnh. Ghi lại những API nội bộ hoặc module/package đáng chú ý. Không đánh dấu “không dùng” chỉ vì công cụ không xuất hiện một tên class.

### Bước 3: Tạo inventory từ cấu hình

Tìm `Class.forName`, `loadClass`, factory reflection, `ServiceLoader`, tên provider và các trường cấu hình chứa tên class. Rà soát resources trong JAR và cấu hình được triển khai bên ngoài repository. Với nhiều profile/tenant, ghi lại effective value cho từng phạm vi.

### Bước 4: Ánh xạ tên class đến artifact và loader

Với mỗi tên được tìm thấy, xác định JAR chứa class, phiên bản, class file major version, class loader hoặc module có nhiệm vụ nạp. Đánh dấu trường hợp class chỉ xuất hiện trong artifact optional hoặc môi trường production.

### Bước 5: Đối chiếu thay đổi JDK/framework

Kiểm tra class/package đã bị loại bỏ hoặc đổi tên, API đã thay đổi, strong encapsulation, module exports/opens và yêu cầu JDK của plugin. Đừng chỉ tập trung vào class missing; một class vẫn tồn tại nhưng không còn gọi được constructor hoặc method cũ.

### Bước 6: Chạy test động có chủ đích

Chạy ít nhất các đường nạp class trong effective configuration: tìm class, tạo instance, kiểm tra interface/constructor, gọi thao tác tiêu biểu và xử lý ngoại lệ. Với SPI, duyệt và kích hoạt provider. Với ORM/serializer, chạy integration test có quyền reflection thực sự.

### Bước 7: Quan sát runtime

Thu thập class loading log hoặc diagnostic tại điểm chọn plugin. Xác nhận nguồn JAR, loader và việc nạp trong profile mục tiêu. Lưu dấu vết đủ để tái hiện nhưng không đưa secret ra log.

### Bước 8: Sửa và khóa lại hợp đồng

Nếu class name cũ không còn hợp lệ, cập nhật cấu hình và kế hoạch deploy. Nếu implementation dùng JDK internal API, ưu tiên API chuẩn hoặc dependency/framework được hỗ trợ. Với plugin architecture, chuyển dần sang interface/SPI rõ ràng, dùng alias/versioning cho implementation và test contract. Nếu cần flag module tạm thời, ghi owner và điều kiện loại bỏ.

### Bước 9: Kiểm thử trong deployment tương đương production

Thử đúng container image, launcher, classpath/module path, plugin directory và effective config. Chạy các profile, feature flag và trường hợp fallback quan trọng. Chỉ kết luận đã xử lý khi những cấu hình cần hỗ trợ đã có bằng chứng test, không phải chỉ khi một job `jdeps` hoàn tất.

## 12. Thiết kế hệ thống để giảm phụ thuộc mong manh vào tên class

Tên class trong file cấu hình là một hình thức liên kết trực tiếp từ deployment tới chi tiết triển khai. Khi đổi package hoặc refactor, lớp liên kết này dễ bị bỏ sót vì compiler không kiểm soát nó. Có thể giảm rủi ro bằng các cách sau.

### 12.1. Dùng tên logic hoặc alias ổn định

Thay vì cho cấu hình chỉ định FQCN:

```properties
normalizer.class=com.example.plugins.FastNormalizer
```

có thể dùng tên chức năng:

```properties
normalizer.type=fast
```

Ứng dụng ánh xạ `fast` tới implementation thông qua registry có kiểu rõ ràng. Khi đổi package hoặc thay class, nhà phát triển có thể cập nhật registry mà không cần sửa mọi file cấu hình đã triển khai. Alias cũng phải có chính sách versioning, vì đổi ý nghĩa của `fast` có thể làm thay đổi hành vi dù không lỗi liên kết.

### 12.2. Dùng SPI có hợp đồng kiểm thử

Một interface ổn định và `ServiceLoader` giúp giảm phụ thuộc vào việc client biết chính xác class name của implementation. Tuy nhiên, provider vẫn phải được đăng ký đúng, đóng gói đúng và kiểm thử thực tế. Đổi từ reflection tự do sang SPI không tự động loại bỏ mọi dependency động.

### 12.3. Fail fast với thông báo hữu ích

Nếu implementation là thiết yếu, nên kiểm tra class/contract ngay khi khởi động hoặc trong bước readiness thích hợp, thay vì đợi request đầu tiên mới nạp class và làm khách hàng gặp lỗi.

Thông báo lỗi nên nêu key cấu hình, tên class sau khi resolve, loại lỗi gốc và artifact/loader liên quan khi có thể. Không nên bọc mọi lỗi thành `RuntimeException("Unable to start")` mà làm mất nguyên nhân ban đầu.

### 12.4. Quản lý vòng đời plugin và cấu hình

Đối với hệ thống có plugin phát hành riêng, cần version policy, support matrix và kiểm thử tương thích giữa host, plugin, JDK và framework. Khi đổi tên class, cân nhắc cơ chế alias/adapter hoặc cảnh báo cấu hình cũ trong giai đoạn chuyển tiếp.

### 12.5. Giới hạn class được phép nạp từ cấu hình

Không nên cho dữ liệu không đáng tin cậy tự do chỉ định tên class rồi nạp và khởi tạo bất kỳ class nào. Nếu class name có thể bị thao túng qua input bên ngoài, cần dùng allowlist/registry, xác thực quyền cấu hình, hạn chế nguồn plugin và phân tách trust boundary phù hợp.

Vấn đề này không chỉ liên quan migration mà còn liên quan bảo mật và vận hành. Một plugin không được kiểm soát có thể chạy code tùy ý với quyền của tiến trình; việc `Class.forName` thành công không nói gì về độ tin cậy của implementation.

## 13. Các hiểu nhầm thường gặp

**“`jdeps` không báo class nên ứng dụng không phụ thuộc vào nó.”** Không đúng. Class có thể chỉ được nhắc trong `.properties`, YAML, XML, `META-INF/services/` hoặc database và được nạp ở runtime.

**“Có chuỗi tên class trong bytecode thì `jdeps` sẽ hiểu đó là dependency.”** Không nhất thiết. Một string literal thông thường không phải tham chiếu kiểu Java; `jdeps` không thực thi `Class.forName` để kiểm tra mọi chuỗi.

**“Chỉ cần quét source repository.”** Không đủ. Cấu hình production, plugin directory, image và tài nguyên trong dependency JAR có thể không nằm trong source của ứng dụng.

**“`Class.forName` thành công là đủ.”** Không. Constructor, method, interface, module access và logic khởi tạo/thực thi vẫn có thể lỗi.

**“`jdeps --jdk-internals` sẽ phát hiện mọi truy cập JDK nội bộ.”** Không. Công cụ chủ yếu dựa trên dependency tĩnh; API nội bộ được nạp qua chuỗi/reflective lookup có thể không được nhận diện.

**“Bổ sung `--add-opens` sẽ sửa mọi lỗi class loading.”** Không. Cần phân biệt thiếu class, sai bytecode version, thiếu module, thiếu export và deep reflection bị chặn.

**“Application khởi động được nghĩa là mọi plugin đều tương thích.”** Không. Nhiều plugin chỉ nạp khi được gọi theo profile, feature flag, tenant hoặc error path.

**“Có class trong JAR nghĩa là JVM đã nạp đúng class đó.”** Không. Thứ tự classpath, module path, class loader và JAR trùng có thể quyết định class thực sự được nạp.

**“Chuyển sang `ServiceLoader` là hết phụ thuộc động.”** Không. Provider vẫn được đăng ký qua metadata, và việc nạp provider cần được kiểm thử.

## 14. Checklist điều tra chuỗi tên class khi nâng cấp JDK

- [ ] Đã ghi nhận JDK, vendor/build, framework và cơ chế classpath/module path thực tế.
- [ ] Đã chạy `jdeps` cho ứng dụng và những JAR/plugin quan trọng, hiểu phạm vi phân tích tĩnh.
- [ ] Đã tìm các điểm `Class.forName`, `ClassLoader.loadClass`, factory reflection và `ServiceLoader`.
- [ ] Đã rà soát `.properties`, YAML, XML, JSON và resource registration trong JAR.
- [ ] Đã kiểm tra system properties, biến môi trường và cấu hình ngoài repository.
- [ ] Đã thống kê effective class names theo profile, tenant và feature path quan trọng.
- [ ] Đã xác định JAR/module/class loader chứa mỗi implementation.
- [ ] Đã xác minh class file version, API/constructor/interface mà client hoặc framework yêu cầu.
- [ ] Đã đánh giá truy cập JDK internal APIs, module `exports` và `opens`.
- [ ] Đã kiểm thử tạo instance và gọi chức năng, không chỉ nạp class.
- [ ] Đã kiểm thử SPI provider, plugin tùy chọn và các đường chạy ít dùng.
- [ ] Đã quan sát class loading trên môi trường tương đương production.
- [ ] Đã lưu bằng chứng và phân loại các cấu hình chưa được kiểm chứng.
- [ ] Đã có kế hoạch cập nhật tên class/alias/registry và rollback khi cần.

## 15. Kết luận

`jdeps` giúp nhận diện những dependency được thể hiện qua tham chiếu tĩnh trong class file, nhưng **không thể bảo đảm tìm ra các class chỉ được chọn bằng chuỗi tên trong cấu hình runtime**. Khi class được nạp qua reflection, `ServiceLoader`, plugin framework hoặc custom class loader, việc phụ thuộc vào implementation có thể không được compiler hoặc `jdeps` phát hiện từ artifact ứng dụng chính.

Trong Java Advance Compatibility Migration, cách xử lý không phải bỏ công cụ phân tích tĩnh mà là bổ sung các nguồn bằng chứng: quét cấu hình trong và ngoài JAR, kiểm tra metadata provider, xác định class loader/module, quan sát việc nạp class và chạy integration test cho các đường cấu hình quan trọng. Kết quả an toàn chỉ có giá trị khi **đúng class, đúng artifact, đúng JDK, đúng quyền truy cập và đúng hành vi** đã được xác minh trong môi trường mục tiêu.
