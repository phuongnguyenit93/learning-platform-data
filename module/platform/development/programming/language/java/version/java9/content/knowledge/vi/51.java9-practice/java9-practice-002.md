# Khám phá nhiều nhà cung cấp qua ServiceLoader — thực hành Java 9+

## 1. Bài toán: nhiều cách triển khai, một hợp đồng dùng chung

Giả sử một ứng dụng cần xử lý dữ liệu bằng các **plugin độc lập**: xuất báo cáo ra nhiều định dạng, chuyển đổi văn bản, đọc các kiểu tệp, hoặc cung cấp nhiều cách hiển thị thông báo. Ứng dụng phải tìm được **tất cả implementation** đang có trong môi trường chạy, cho phép bổ sung nhà cung cấp mới mà **không sửa mã gọi cụ thể** của ứng dụng.

Đó là vai trò của cơ chế **Service Provider Interface (SPI)** và `java.util.ServiceLoader<S>`:

- **Service:** một interface hoặc abstract class mô tả hành vi chung cho ứng dụng sử dụng.
- **Provider:** một class/factory cung cấp implementation của service.
- **Consumer:** phần ứng dụng gọi `ServiceLoader.load(Service.class)`, duyệt providers và chọn implementation phù hợp.
- **Đăng ký provider:** bằng `provides ... with ...` trong **named module** hoặc bằng tệp `META-INF/services/...` khi cung cấp qua **classpath**.
- **Discovery:** hệ thống tìm các providers thông qua module system/class loader mà **không cần consumer tạo cứng `new ConcreteProvider()`**.

Từ Java 9, ServiceLoader tích hợp với Java Platform Module System (**JPMS**) và thêm `stream()` cùng `ServiceLoader.Provider<S>` để kiểm tra metadata trước khi cần tạo đối tượng. Bản thân `ServiceLoader` **đã có trước Java 9**; điều mới quan trọng trong chủ đề Java 9 là khả năng liên kết với **`uses/provides`, module path và Provider stream**. Những API này **vẫn được dùng trong Java SE hiện hành**.

**Mục tiêu thực hành:** tạo một service `GreetingService` có **hai provider độc lập** (tiếng Anh và tiếng Việt); consumer tự phát hiện cả hai, xử lý được trường hợp trống/trùng mã, và in kết quả ổn định **mà không phụ thuộc thứ tự discovery**. Sau đó xem cách phân phối providers bằng classpath, đọc metadata qua `stream()`, xử lý lỗi và các giới hạn plugin runtime.

Không cần framework DI để thực hiện ví dụ này. ServiceLoader là API tiêu chuẩn Java, nhưng **không tự** cung cấp versioning, sandbox bảo mật, dependency injection đầy đủ hoặc hot deployment.

## 2. Cơ chế hoạt động

Mô hình tổng quát:

```text
                Consumer
                   |
                   | ServiceLoader.load(GreetingService.class)
                   v
             GreetingService
                   |
         +---------+---------+
         |                   |
         v                   v
  EnglishGreeting      VietnameseGreeting
  (provider A)          (provider B)
         |                   |
         +---------+---------+
                   |
              SPI contract
```

Consumer chỉ biết interface. Nhà cung cấp có thể phát triển và đóng gói ở các module/JAR riêng. ServiceLoader khám phá các nhà cung cấp được **đăng ký và có thể truy cập qua class loader/module layer hiện tại**; không có nghĩa nó quét mọi JAR trong ổ đĩa hoặc tải plugin từ Internet.

### Ba sự kiện phải tách biệt

1. **Có provider trong module path/classpath:** file đã được triển khai, nhưng chưa chắc nằm trong phạm vi nhìn thấy của loader.
2. **Provider được discover:** ServiceLoader tìm được khai báo `provides` hoặc `META-INF/services` phù hợp.
3. **Provider được instantiate:** iterator hoặc `Provider.get()` tạo ra instance thực tế.

Hai bước sau diễn ra **lazily**, tùy lúc ứng dụng duyệt providers. `ServiceLoader.load(...)` không có nghĩa mọi nhà cung cấp đã được tạo ngay. `ServiceLoader.stream()` có thể cho phép xem loại provider qua `type()` rồi mới quyết định `get()`.

### Tại sao cần khám phá *nhiều* provider?

Một dịch vụ có thể có **0, 1 hoặc nhiều** nhà cung cấp. Khi có hai implementation khác nhau, ứng dụng thường cần **liệt kê tất cả**, kiểm tra tên/khả năng, rồi **chọn theo tiêu chí rõ ràng** hoặc gọi từng provider. Dùng `findFirst()` chỉ vì “cần một cái” dễ dẫn đến hành vi khó kiểm soát khi thứ tự module/provider thay đổi.

## 3. Dự án thực hành: bốn named modules

Ta xây một dự án nhỏ chạy trên **JDK 17+**, sử dụng cú pháp module đã được giới thiệu từ Java 9.

| Module | Vai trò | Quan hệ |
| --- | --- | --- |
| `demo.api` | Định nghĩa service `GreetingService` | Xuất package `demo.api` |
| `demo.english` | Provider tiếng Anh | `requires demo.api` và `provides` service |
| `demo.vietnamese` | Provider tiếng Việt | `requires demo.api` và `provides` service |
| `demo.app` | Consumer, không biết concrete classes | `requires demo.api` và `uses` service |

Cấu trúc tệp:

```text
service-demo/
  src/
    demo.api/
      module-info.java
      demo/api/GreetingService.java
    demo.english/
      module-info.java
      demo/english/EnglishGreeting.java
    demo.vietnamese/
      module-info.java
      demo/vietnamese/VietnameseGreeting.java
    demo.app/
      module-info.java
      demo/app/Main.java
```

Tất cả tên module/package và đường dẫn được chọn nhất quán. Nếu thay tên, cần cập nhật **module-info.java**, `package` và lệnh biên dịch tương ứng.

### 3.1. Định nghĩa SPI — `demo.api`

Tệp **`src/demo.api/module-info.java`**:

```java
module demo.api {
    exports demo.api;
}
```

Tệp **`src/demo.api/demo/api/GreetingService.java`**:

```java
package demo.api;

public interface GreetingService {
    String code();
    String greet(String name);
}
```

Service có hai phương thức:

- `code()`: mã định danh ổn định, ví dụ `"en"` và `"vi"`. Consumer sẽ dùng mã này để chọn/sắp xếp, không dựa vào tên class.
- `greet(String)`: hành vi triển khai thực tế.

**Lý do API có `code()`:** nếu service cung cấp nhiều nhà cung cấp mà không có thuộc tính phân biệt, consumer thường phải hard-code tên class rồi mất lợi ích của SPI. Với một hệ thống thật, SPI nên mô tả các thuộc tính nghiệp vụ cần thiết: định dạng hỗ trợ, version giao thức, priority có quy tắc rõ ràng, mức tương thích, v.v.

### 3.2. Provider thứ nhất — `demo.english`

Tệp **`src/demo.english/module-info.java`**:

```java
module demo.english {
    requires demo.api;
    provides demo.api.GreetingService
        with demo.english.EnglishGreeting;
}
```

Tệp **`src/demo.english/demo/english/EnglishGreeting.java`**:

```java
package demo.english;

import demo.api.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String code() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Lưu ý `EnglishGreeting` là **public top-level class** và có **public constructor không tham số**. Đây là hình thức provider đơn giản và phù hợp nhất cho ví dụ. Nó không cần export package `demo.english` sang consumer: service loading qua `provides` cho phép provider implementation được giữ kín ở mức module.

### 3.3. Provider thứ hai — `demo.vietnamese`

Tệp **`src/demo.vietnamese/module-info.java`**:

```java
module demo.vietnamese {
    requires demo.api;
    provides demo.api.GreetingService
        with demo.vietnamese.VietnameseGreeting;
}
```

Tệp **`src/demo.vietnamese/demo/vietnamese/VietnameseGreeting.java`**:

```java
package demo.vietnamese;

import demo.api.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {
    }

    @Override
    public String code() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

Ta có **hai module provider độc lập** đăng ký cùng `GreetingService`. Consumer không cần `requires demo.english` hoặc `requires demo.vietnamese`; nó chỉ cần API service và `uses`. Điều này cho phép thêm provider thứ ba bằng một module mới với `provides` mà không cần sửa module descriptor hay mã tạo provider cụ thể ở consumer.

**Lưu ý về cấu hình:** `provides A with B` phải nằm trong *module chứa B*. Một module không được `provides` implementation thuộc module khác. Nếu không có directive `provides`, việc class triển khai interface và tồn tại trên module path **không tự đủ** để ServiceLoader thấy nó.

### 3.4. Consumer — `demo.app`

Tệp **`src/demo.app/module-info.java`**:

```java
module demo.app {
    requires demo.api;
    uses demo.api.GreetingService;
}
```

Tệp **`src/demo.app/demo/app/Main.java`**:

```java
package demo.app;

import demo.api.GreetingService;

import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class Main {
    public static void main(String[] args) {
        Map<String, GreetingService> providers = new TreeMap<>();

        for (GreetingService provider
                : ServiceLoader.load(GreetingService.class)) {

            String code = provider.code();
            GreetingService old =
                    providers.putIfAbsent(code, provider);

            if (old != null) {
                throw new IllegalStateException(
                        "Duplicate provider code: " + code);
            }
        }

        if (providers.isEmpty()) {
            throw new IllegalStateException(
                    "No GreetingService providers found");
        }

        System.out.println("Providers=" + providers.size());
        providers.forEach((code, provider) ->
                System.out.println(
                        code + " -> " + provider.greet("Java")));
    }
}
```

Phân tích:

1. `ServiceLoader.load(GreetingService.class)` tạo loader cho một service type, không yêu cầu tên provider.
2. Vòng `for (GreetingService provider : ...)` yêu cầu **lần lượt instantiate** providers khi duyệt.
3. `TreeMap` lưu theo `code()` nên kết quả in ra có **thứ tự xác định bởi mã**, dù thứ tự phát hiện modules là không cố định.
4. `putIfAbsent` phát hiện **hai implementation khác nhau cùng mã**; tránh âm thầm chọn provider nào xuất hiện trước.
5. Khi không tìm thấy provider, chương trình thất bại với thông báo rõ, thay vì `NullPointerException` hoặc silently dùng cấu hình thiếu.
6. Consumer **không import** `demo.english.EnglishGreeting` hay `demo.vietnamese.VietnameseGreeting`. Hai package implementation cũng không được export.

Nếu SPI cho phép provider trả `null` từ `code()`, `TreeMap` sẽ ném lỗi vì key null; trong ứng dụng thật, đặt hợp đồng `code()` phải non-null, không rỗng, duy nhất và kiểm tra các trường hợp đó tại boundary.

## 4. Biên dịch và chạy — đầu ra có thể kiểm tra

Đứng tại thư mục `service-demo`, chạy bằng **JDK 17+**:

```bash
javac --release 17 -encoding UTF-8 --module-source-path src -d mods -m demo.api,demo.english,demo.vietnamese,demo.app
java --module-path mods --module demo.app/demo.app.Main
```

Lệnh `javac` đầu tiên thường không in ra gì nếu thành công. Cấu hình `--module-source-path src` yêu cầu layout `src/<module-name>/...` như mục 3; `-d mods` tạo các module output directories.

**Đầu ra ứng dụng (khi hai provider có sẵn như mô tả):**

```text
Providers=2
en -> Hello, Java
vi -> Xin chào, Java
```

Đầu ra được giữ ổn định nhờ `TreeMap`: không cần giả định rằng EnglishGreeting luôn được ServiceLoader phát hiện trước VietnameseGreeting. Với terminal không hiển thị Unicode đúng, kiểm tra encoding terminal; tệp nguồn đã được biên dịch với `-encoding UTF-8`.

### Tại sao provider modules có thể được tìm thấy mà app không requires chúng?

Khi JVM giải quyết module graph cho ứng dụng, **service binding** có thể đưa các provider modules trên module path vào graph theo `uses` và `provides`. Vì vậy app chỉ yêu cầu `demo.api`; các provider trở thành thành phần cài thêm. Điều này là đặc điểm quan trọng của Java 9 module system.

Nếu bạn cố tình chạy ở môi trường có giới hạn module graph hoặc layer được tạo riêng và không có provider modules được resolve, ServiceLoader có thể chỉ thấy 0 provider. Hãy kiểm tra bằng:

```bash
java --show-module-resolution --module-path mods --module demo.app/demo.app.Main
```

Tùy JDK và modules hiện diện, phần log resolution khác nhau. Bạn cần thấy các module provider được resolve qua cơ chế service binding hoặc theo root modules được khai báo; không hard-code nguyên đoạn log.

Nếu runtime/launcher của bạn có cách cấu hình resolution khác, có thể thử khai báo provider modules thành roots tường minh:

```bash
java --module-path mods --add-modules demo.english,demo.vietnamese --module demo.app/demo.app.Main
```

Đây là **cách kiểm tra/tùy chỉnh resolution khi có nhu cầu**, không phải yêu cầu mặc định của mọi ứng dụng JPMS. Đừng đưa `requires demo.english` hoặc `requires demo.vietnamese` vào consumer chỉ để ép discovery: như vậy sẽ làm mất tính linh hoạt của SPI.

## 5. Luồng khám phá: iterator và stream

Từ góc nhìn consumer, Java có hai cách phổ biến để duyệt.

### 5.1. for-each / iterator — dùng khi cần instance

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.code());
}
```

Đây là **trích đoạn** cần `import java.util.ServiceLoader;` và import `GreetingService`. Mỗi phần tử trả cho vòng lặp là **một instance** của service provider; loader thường tạo instance khi iterator tiến đến provider chưa được cache.

Ưu điểm: đơn giản, phù hợp khi công việc phải gọi `greet()` hoặc các hành vi thực tế của mọi provider.

### 5.2. stream() / Provider.type() — kiểm tra trước khi instantiate

`ServiceLoader.stream()` (Java 9+) trả `Stream<ServiceLoader.Provider<S>>`. Một `Provider<S>` có hai phương thức quan trọng:

- `type()`: trả `Class<? extends S>` đại diện cho loại provider mà API công bố.
- `get()`: lấy/tạo một instance của provider.

Ví dụ liệt kê tên loại của providers:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

loader.stream()
        .map(p -> p.type().getName())
        .sorted()
        .forEach(System.out::println);
```

**Kết quả với hai provider xây ở mục 3:**

```text
demo.english.EnglishGreeting
demo.vietnamese.VietnameseGreeting
```

Việc gọi `type()` không cần instantiate provider instance. Tuy nhiên ServiceLoader vẫn phải **discover và load metadata/type** để cung cấp đối tượng `Class`; đừng hiểu là không có bất kỳ class loading/validation nào.

Có thể sắp xếp theo tên provider type trước khi yêu cầu instance:

```java
List<GreetingService> all = ServiceLoader
        .load(GreetingService.class)
        .stream()
        .sorted(Comparator.comparing(
                p -> p.type().getName()))
        .map(ServiceLoader.Provider::get)
        .toList();
```

Trích đoạn này cần import `java.util.List`, `java.util.Comparator`, `java.util.ServiceLoader` và service interface. `Stream.toList()` có trong Java 16+, nên mã dùng tốt trên JDK 17+; đây **không** phải API Java 9 nguyên bản. Nếu viết code phải chạy chính xác trên Java 9, dùng `collect(Collectors.toList())` thay vì `toList()`.

**Phân biệt lựa chọn:** sắp xếp theo `Provider.type().getName()` ổn định theo tên class nhưng vẫn tạo sự phụ thuộc vào tên implementation. Trong ứng dụng production, tốt hơn nên chọn theo **capability/id/priority được service contract công bố**, như `code()` ở ví dụ chính. Nếu cần lọc dựa trên annotation trên provider type, `stream().filter(p -> p.type().isAnnotationPresent(...))` hữu ích để tránh tạo instance không cần thiết.

### 5.3. findFirst() không phải cơ chế chọn ưu tiên

`ServiceLoader.findFirst()` (Java 9+) trả `Optional<S>` với provider đầu tiên được phát hiện. Nhưng thứ tự giữa các modules/providers trong nhiều trường hợp **không được bảo đảm ổn định**. Vì vậy:

```java
Optional<GreetingService> maybe =
        ServiceLoader.load(GreetingService.class).findFirst();
```

được phép và hữu ích nếu mọi implementation đều tương đương đối với bài toán. Nó **không** thay một quy tắc chọn cụ thể như “luôn ưu tiên tiếng Việt”, “ưu tiên codec có version tương thích” hoặc “ưu tiên backend đạt SLA”. Khi cần selection policy, hãy duyệt/đánh giá các ứng viên phù hợp và quyết định tường minh.

## 6. Nhiều provider trên classpath: META-INF/services

Không phải mọi dự án hiện đại đều sử dụng **named modules**. Với ứng dụng/classpath truyền thống hoặc thư viện phát hành dưới dạng JAR không modular, cơ chế đăng ký bằng `META-INF/services` **vẫn còn áp dụng**.

**Khác biệt cách đăng ký:**

| Hình thức triển khai | Provider được khai báo ở đâu? |
| --- | --- |
| Explicit named module trên module path | Directive `provides Service with Implementation` trong `module-info.java` |
| Classpath/unnamed modules | Resource `META-INF/services/<fully.qualified.ServiceName>` |
| Automatic module | Có quy tắc liên quan metadata service và module descriptor được suy ra; cần kiểm tra packaging thực tế |

Với service trong ví dụ, resource tên **chính xác**:

```text
META-INF/services/demo.api.GreetingService
```

Nội dung resource, **UTF-8**, mỗi provider class một dòng:

```text
demo.english.EnglishGreeting
demo.vietnamese.VietnameseGreeting
```

Không đặt `module demo.*` trong resource; chỉ có **fully qualified binary class names**. File không có phần mở rộng `.txt`. Không lưu nó dưới `src/main/java` rồi quên đóng gói: ở runtime nó phải có mặt trên **classpath** hoặc nằm bên trong JAR ở đúng `META-INF/services/...`.

### Chạy lại cùng các class bằng classpath

Ta có thể dùng lại **4 tệp Java code** ở mục 3, nhưng **không biên dịch các `module-info.java`** trong biến thể classpath. Tại thư mục `service-demo`:

```bash
javac --release 17 -encoding UTF-8 -d out src/demo.api/demo/api/GreetingService.java src/demo.english/demo/english/EnglishGreeting.java src/demo.vietnamese/demo/vietnamese/VietnameseGreeting.java src/demo.app/demo/app/Main.java
```

Sau lệnh này, tạo file `out/META-INF/services/demo.api.GreetingService` và chép **nguyên hai dòng** tên provider ở trên. Sau đó chạy:

```bash
java -cp out demo.app.Main
```

**Stdout khi resource được đặt đúng:**

```text
Providers=2
en -> Hello, Java
vi -> Xin chào, Java
```

Nếu chỉ chạy `java -cp out demo.app.Main` mà quên resource `META-INF/services/demo.api.GreetingService`, class của hai provider **vẫn có thể nằm trong `out`** nhưng `ServiceLoader` không biết nhà cung cấp nào cần đăng ký. Ví dụ sẽ báo `No GreetingService providers found`.

**Quy tắc đóng gói:** khi tạo JAR provider, giữ nguyên resource `META-INF/services/...`. Một JAR có provider classes nhưng thiếu resource thường không được khám phá trong chế độ classpath. Với explicit modules, ưu tiên `provides` trong `module-info.java`; không cần ghi lặp cùng provider vào resource để giải quyết vấn đề của module path.

### Format resource hiện hành

- File mã hóa **UTF-8**.
- Mỗi dòng chứa một fully qualified provider binary name; dòng trống và khoảng trắng phù hợp được bỏ qua.
- `#` đánh dấu chú thích; nội dung phía sau `#` trên cùng dòng được bỏ qua.
- Các lần lặp **cùng một provider class name** trong những resource/service files được bỏ qua theo hợp đồng ServiceLoader.
- Một provider **khác class nhưng cùng mã nghiệp vụ** `code()` vẫn được xem là provider riêng; ví dụ chính sẽ phát hiện trùng mã khi build map.

Khi classpath có nhiều JAR đăng ký cùng một service, class loader có thể tìm được nhiều resource `META-INF/services/...`. Không dựa vào một thứ tự cố định giữa các JAR, class loaders hoặc module layers; hãy chọn/sắp xếp theo chính sách ứng dụng.

## 7. Ví dụ bổ sung: khám phá các tool providers có sẵn trong JDK

Ngoài một plugin tự tạo, JDK hiện hành có các **service providers** ngay trong các module của công cụ Java. Bài thử này không cần tự tạo 4 module, hữu ích khi chỉ muốn quan sát `ServiceLoader.stream()` ngay trên máy đang học.

Tệp **`JdkToolProviders.java`**:

```java
import java.util.List;
import java.util.ServiceLoader;
import java.util.spi.ToolProvider;

public class JdkToolProviders {
    public static void main(String[] args) {
        List<String> names = ServiceLoader
                .load(ToolProvider.class)
                .stream()
                .map(p -> p.type().getName())
                .sorted()
                .toList();

        System.out.println("Provider types=" + names.size());
        names.forEach(System.out::println);
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 JdkToolProviders.java
java JdkToolProviders
```

**Không có stdout cố định cho mọi JDK.** Số tool providers và tên lớp có thể thay đổi giữa JDK distributions, phiên bản hoặc runtime image. Một bản JDK đầy đủ có thể cung cấp providers cho `javac`, `jar`, `javadoc` và các công cụ khác; một runtime image đã tối giản có thể có ít provider hơn.

**Kiểm chứng trong môi trường thực:** trên OpenJDK 24 có thể khám phá nhiều implementations của `java.util.spi.ToolProvider` qua ServiceLoader. Điều này minh họa rằng discovery hoạt động với provider modules của JDK chứ không chỉ với hai lớp ứng dụng do ta tự viết.

Dùng `stream()` với `type()` chỉ để quan sát loại provider; không cần gọi công cụ thực thi. Khi muốn **tìm một công cụ theo tên**, service-specific API `ToolProvider.findFirst("javac")` có thể phù hợp hơn tự duyệt và dựa vào class name; đó là một API riêng do `ToolProvider` cung cấp.

## 8. Vòng đời, lazy loading và bộ nhớ đệm

### 8.1. Khi nào một provider được tạo?

`ServiceLoader.load(service)` tạo loader. Provider discovery và instantiation thường xảy ra **theo nhu cầu**, khi:

- `iterator().hasNext()`/`next()` di chuyển qua các provider;
- Terminal operation trên `stream()` duyệt candidates;
- `Provider.get()` yêu cầu một instance;
- `findFirst()` tìm/tạo provider đầu tiên.

Với `stream()`, `type()` giúp đánh giá provider type trước khi gọi `get()`, nhưng việc duyệt stream vẫn có thể phát hiện hoặc tải class metadata. Không dùng khẳng định sai “`stream()` không bao giờ load class”.

### 8.2. Cache nằm trong một ServiceLoader instance

Một `ServiceLoader` duy trì **cache các providers đã được load**. Khi duyệt lần hai qua cùng loader, các instance đã có trong cache của `iterator` được trả lại trước rồi mới tiếp tục phát hiện những provider chưa duyệt. Việc tạo **một ServiceLoader mới** không đồng nghĩa tái sử dụng cache của loader cũ.

`reload()` xóa cache của loader để các lượt duyệt tiếp theo có thể tìm/khởi tạo lại providers. Ví dụ:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService p : loader) {
    System.out.println(p.code());
}

loader.reload();

for (GreetingService p : loader) {
    System.out.println(p.code());
}
```

Đây là **trích đoạn**, cần `GreetingService`, import `ServiceLoader` và providers có thể truy cập. Sau `reload()`, **không dùng lại iterator/stream cũ** của cùng loader: chúng có thể ném `ConcurrentModificationException` vì cache đã thay đổi.

**Giới hạn quan trọng:** `reload()` **không phải plugin hot deploy**. Nó không tự thêm một module JAR mới vào module graph hiện có, không thay `ModuleLayer` hoặc class loader, và không tự đóng các instance cũ mà ứng dụng đang giữ. Nếu thực sự cần tải module mới trong một JVM đang chạy, phải thiết kế module layer/classloader lifecycle và phạm vi discovery riêng.

### 8.3. Đa luồng

`ServiceLoader` **không thread-safe**. Không cho hai thread đồng thời duyệt hoặc gọi `reload()` trên cùng instance mà không có cơ chế đồng bộ. Với ứng dụng server, cách thường đơn giản là:

1. Khám phá/validate providers khi khởi động hoặc khi bước reconfiguration được đồng bộ;
2. Tạo một **registry bất biến** của các service implementations hoặc provider descriptors đã được chấp thuận;
3. Cấp registry cho các thread xử lý theo mức thread-safety riêng của từng provider.

**Provider instance** có thể thread-safe hoặc không; ServiceLoader **không tự** bảo đảm thread safety của business methods `greet()` hay API plugin. Hợp đồng service cần nói rõ lifecycle (singleton/cached/per-request), trạng thái nội bộ và khả năng dùng song song.

### 8.4. Class loader và module layer

`ServiceLoader.load(ServiceType.class)` sử dụng **thread context class loader** làm điểm bắt đầu. Trong môi trường app server, plugin host hoặc framework có nhiều class loaders, việc đặt sai context class loader có thể làm thiếu provider hoặc giữ references quá lâu.

Các overload quan trọng:

```java
ServiceLoader.load(ServiceType.class);
ServiceLoader.load(ServiceType.class, someClassLoader);
ServiceLoader.load(someModuleLayer, ServiceType.class);
```

Đây là **chữ ký sử dụng minh họa** trong một chương trình đã khai báo `ServiceType`, `someClassLoader` và `someModuleLayer`. Overload với `ModuleLayer` (Java 9+) tìm providers trong layer đã cho và các layer cha; **không dò providers trong unnamed modules**. Với classloader overload, providers có thể đến từ named/unnamed modules có thể nhìn thấy theo quy tắc tương ứng.

Không lưu một ServiceLoader có context class loader của plugin A thành một singleton toàn JVM rồi dùng cho mọi ứng dụng/plugin khác. Điều đó có thể dẫn đến nhìn nhầm providers và giữ class loader sau khi plugin cần unload.

## 9. Thiết kế SPI cho nhiều implementation: chọn đúng provider

Một dự án thực tế không nên lấy provider đầu tiên theo thứ tự không được bảo đảm. Có một số chiến lược có ý nghĩa:

| Yêu cầu | Hướng xử lý |
| --- | --- |
| Cần gọi **tất cả** providers | Duyệt hết; quyết định thứ tự hiển thị/thi hành bằng một comparator có nghĩa |
| Cần provider có `id` cụ thể | Xây map `id → provider`; từ chối id trùng |
| Cần chọn theo định dạng | Giao diện SPI công bố `supports(format)` hoặc `supportedFormats()` |
| Cần ưu tiên theo chi phí/khả năng | Provider công bố metadata phù hợp; ứng dụng sắp xếp/chấm điểm |
| Không có provider | Báo cấu hình thiếu hoặc dùng fallback **được chỉ định minh bạch** |
| Có nhiều provider cùng ưu tiên | Quy định tie-breaker tường minh, không dùng discovery order |
| Có provider không hợp lệ | Báo lỗi cấu hình với ngữ cảnh; tránh silently bỏ qua một lỗi có thể che sự cố triển khai |

**Ví dụ chọn sau khi đã xây map:**

```java
GreetingService chosen = providers.get("vi");
if (chosen == null) {
    throw new IllegalStateException(
            "Vietnamese provider is not installed");
}
System.out.println(chosen.greet("Java"));
```

Trích đoạn nằm trong phương thức có biến `providers` kiểu `Map<String,GreetingService>`. Dòng output với provider ở ví dụ là:

```text
Xin chào, Java
```

Một plugin có mã `vi` nhưng chất lượng kém không trở nên đáng tin chỉ vì được ServiceLoader phát hiện. Trong môi trường mở rộng bởi bên thứ ba, ứng dụng còn cần quản lý **nguồn gốc artifacts, chữ ký/nội dung, cấu hình cho phép, tương thích API và quyền thực thi**. Module encapsulation không phải sandbox chống mã độc; plugin chạy bên trong JVM có thể có quyền đáng kể của process.

### Cách xử lý duplicate provider

Cùng một **provider class name** xuất hiện lặp trong resource `META-INF/services` có thể được ServiceLoader loại trùng. Nhưng nếu hai provider **khác class cùng công bố `code() == "vi"`**, runtime không tự biết rằng chúng xung đột về nghiệp vụ. Logic `putIfAbsent` ở ví dụ chính chủ động nhận ra điều đó. Tên class hay thứ tự load không được coi là cơ chế giải quyết xung đột.

## 10. Provider constructor và provider factory — quy tắc chính xác

Đối với một provider đặt trong **explicit named module**:

- Thông thường provider class `public`, không phải inner class, triển khai service và có **public no-argument constructor**. ServiceLoader sẽ khởi tạo bằng constructor.
- Ngoài ra có thể có **public static no-argument method tên `provider`** trả về loại phù hợp với service; ServiceLoader sẽ gọi factory method đó để lấy instance. Trong trường hợp này class chứa factory **không nhất thiết tự implement service**.
- Provider package có thể không được export; service mechanism có đường truy cập hợp lệ để tạo provider.
- Nếu có provider factory, `ServiceLoader.Provider.type()` có thể trả **return type của phương thức `provider()`**, không phải class khai báo factory. Đừng đồng nhất `type()` với tên class trong `provides` cho mọi trường hợp.

Ví dụ khai báo factory (trích đoạn **minh họa**, không thay các tệp trong ví dụ chính):

```java
// module-info.java trong explicit provider module:
provides demo.api.GreetingService
    with demo.extra.GreetingFactory;
```

```java
package demo.extra;

import demo.api.GreetingService;

public final class GreetingFactory {
    private GreetingFactory() {
    }

    public static GreetingService provider() {
        return new GreetingService() {
            @Override public String code() {
                return "extra";
            }
            @Override public String greet(String name) {
                return "Hi, " + name;
            }
        };
    }
}
```

Hai phần trên là **mô tả một provider module khác**, không nằm trong dự án runnable mục 3–4. Khi áp dụng phải bổ sung module descriptor (`requires demo.api`), đúng đường dẫn và compile module mới.

**Khác biệt cần nhớ:** provider trên **classpath** và **automatic module** cần provider constructor phù hợp; **provider factory method** kiểu trên không phải cơ chế dùng được ở những hình thức đó. Đừng thiết kế module provider factory rồi kỳ vọng cùng JAR sẽ hoạt động nguyên dạng trên classpath.

## 11. Các lỗi thực tế và cách kiểm tra

| Dấu hiệu | Nguyên nhân có khả năng | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Providers=0` / registry trống | Không có đăng ký/không thấy providers trong loader scope | Kiểm tra `provides`, `uses`, module path, resource `META-INF/services`, class loader |
| Named consumer lỗi `ServiceConfigurationError` ngay khi load | Thiếu `uses Service` hoặc service không accessible | Kiểm tra `module-info.java` của consumer và module export |
| Provider có class nhưng không được tìm thấy | Class hiện diện nhưng không có `provides`/service resource | Xem cấu hình đóng gói, modules được resolve, đường classpath |
| `ServiceConfigurationError` khi duyệt | Sai provider name, constructor, factory, classloader, dependency hoặc provider ném lỗi | Đọc cause/stack trace; sửa packaging hoặc implementation |
| `NoClassDefFoundError`/`ClassNotFoundException` trong provider | Provider phụ thuộc thư viện chưa có hoặc không nhìn thấy | Sửa module dependencies/classpath/class loader |
| Provider được phát hiện nhưng lệnh business lỗi | Provider có bug/không đáp ứng SPI contract | Viết test contract riêng cho từng provider |
| Thứ tự in thay đổi | Discovery order của modules/JAR không được bảo đảm chung | Sắp xếp theo `code`/priority và dùng tie-breaker |
| Hai provider cùng mã `vi` | Xung đột định danh nghiệp vụ | Phát hiện duplicate và từ chối/áp dụng chính sách rõ ràng |
| `reload()` nhưng provider JAR mới không xuất hiện | Module layer/classloader hiện tại không nhận module mới | Thiết kế discovery scope/module layer mới; không trông chờ `reload` tự hot-load |
| Duyệt iterator sau `reload()` ném `ConcurrentModificationException` | Iterator/stream cũ invalid vì cache đã reset | Lấy iterator/stream mới từ loader sau reload |
| Lỗi ngẫu nhiên khi nhiều thread cùng dùng loader | `ServiceLoader` không thread-safe | Đồng bộ discovery hoặc xây registry bất biến |
| Chạy classpath được nhưng module path lỗi | Thiếu `uses`/`provides` hoặc graph khác | Kiểm tra descriptor, build tasks và module resolution |
| Chạy module path được nhưng classpath trống | Thiếu `META-INF/services` resource | Đóng gói resource cho chế độ classpath |

### Tại sao ServiceConfigurationError đáng chú ý?

`ServiceConfigurationError` là **Error**, không phải `Exception` thông thường. Nó báo cấu hình provider **bị hỏng/không hợp lệ**: provider không load được, không có constructor hoặc factory phù hợp, resource bị lỗi format, factory ném lỗi hoặc trả null, v.v.

Lỗi có thể xảy ra **khi duyệt** chứ không chỉ lúc gọi `ServiceLoader.load(...)`. Vì vậy, đoạn:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);
System.out.println("Loader created");
for (GreetingService p : loader) {
    System.out.println(p.code());
}
```

có thể in `Loader created` rồi mới lỗi khi iterator cố gắng lấy provider. Đây là **trích đoạn minh họa**, không phải chương trình độc lập.

Trong ứng dụng production, nếu cần bổ sung ngữ cảnh:

```java
try {
    for (GreetingService p
            : ServiceLoader.load(GreetingService.class)) {
        System.out.println(p.code());
    }
} catch (java.util.ServiceConfigurationError failure) {
    throw new IllegalStateException(
            "Invalid GreetingService provider configuration",
            failure);
}
```

Đoạn trên chỉ minh họa cách **bảo tồn cause** khi báo lỗi ở lớp ứng dụng. Không nên bắt `ServiceConfigurationError` rồi âm thầm `continue`: việc cố skip provider hỏng **không được bảo đảm luôn hồi phục** và có thể che một lỗi cấu hình nghiêm trọng. Lỗi nghiệp vụ khi gọi `greet()` sau khi đã tạo provider cũng cần chính sách xử lý riêng.

## 12. Testing: xác minh mọi provider, không chỉ provider đầu

Kiểm thử một module plugin phải bao gồm:

1. **Kiểm tra số lượng/định danh:** với dự án ví dụ, cần đúng hai providers có mã `en` và `vi`.
2. **Thử chức năng từng provider:** `greet("Java")` trả đúng ngôn ngữ của implementation.
3. **Thử xung đột:** thêm provider thứ ba với `code() == "vi"` để bảo đảm registry báo lỗi.
4. **Thử thiếu provider:** bỏ provider modules khỏi module path hoặc resource `META-INF/services` và quan sát trường hợp không có implementation.
5. **Thử lỗi packaging:** sửa sai tên class trong service descriptor để xác nhận `ServiceConfigurationError` được báo đúng tầng.
6. **Thử thứ tự:** dù discovery order thay đổi, output nghiệp vụ vẫn sắp theo `code()` thay vì vị trí provider đầu tiên.
7. **Thử isolation/lifecycle:** nếu plugin host dùng custom loaders/layers, xác nhận được scope provider mong muốn và giải phóng classloader khi plugin bị unload.
8. **Thử tương thích JDK:** chạy lại bài kiểm thử khi nâng JDK/build plugin hoặc đổi module/classpath packaging.

Trong CI, có thể chạy command của mục 4 và kiểm tra đúng ba dòng stdout. Với biến thể classpath, cần đóng gói resource trước khi chạy; nếu không, test “không thấy provider” chỉ phản ánh resource bị thiếu, không kiểm tra đúng tính năng đa nhà cung cấp.

Nếu xây registry một lần khi startup, sau đó cho nhiều request dùng, hãy test thread-safety riêng của từng provider. `ServiceLoader` chỉ quản lý discovery/instantiation, không biết code nghiệp vụ của từng plugin có được phép dùng nhiều luồng hay không.

## 13. Checklist thiết kế plugin thực tế

- [ ] Định nghĩa SPI là interface/abstract class **nhỏ, ổn định và có thông tin lựa chọn provider**.
- [ ] Consumer **chỉ phụ thuộc module API**, dùng `uses` thay vì `requires` từng provider.
- [ ] Mỗi explicit provider module khai báo `provides Service with Implementation` và `requires` API nếu cần.
- [ ] Provider class/factory đáp ứng đúng quy tắc constructor/provider method của hình thức triển khai.
- [ ] Khi dùng classpath, đóng gói tệp UTF-8 `META-INF/services/<FQCN>`.
- [ ] Duyệt toàn bộ providers khi bài toán cần tất cả; không dựa vào thứ tự discovery bất định.
- [ ] Có policy rõ ràng cho **0 provider**, duplicate ID, nhiều provider cùng khả năng, và provider không tương thích.
- [ ] Hiểu `stream().type()`, `Provider.get()`, iterator, cache và `reload()`.
- [ ] Không dùng chung một ServiceLoader instance từ nhiều thread nếu không đồng bộ.
- [ ] Không dùng `reload()` như cơ chế tự hot-deploy JAR/module mới.
- [ ] Theo dõi `ServiceConfigurationError` như lỗi đóng gói/cấu hình cần xử lý.
- [ ] Thẩm định nguồn plugin và quyền thực thi; **JPMS encapsulation không phải security sandbox**.
- [ ] Có test cho mỗi provider và kiểm thử lại khi đổi class loader/module layer hoặc JDK.

## 14. Câu hỏi tự kiểm tra

1. **ServiceLoader là API mới hoàn toàn từ Java 9?** Không. Nó có trước; Java 9 bổ sung tích hợp JPMS, `stream()` và `Provider<S>`.
2. **Consumer có phải import và `new` mọi provider?** Không. Consumer chỉ biết service; ServiceLoader tìm providers đã đăng ký.
3. **`uses` viết ở module nào?** Module tiêu thụ service (`demo.app`).
4. **`provides` viết ở module nào?** Module chứa class provider.
5. **Phải export package provider implementation?** Không; explicit module provider có thể giữ implementation package không export.
6. **`ServiceLoader.load(...)` có tạo hết providers ngay?** Không, việc discovery/instantiation thường lazy.
7. **`stream().map(p -> p.type().getName())` đã tạo instance tất cả providers?** Không; `type()` xem type trước khi `get()`.
8. **`findFirst()` luôn chọn provider có priority cao nhất?** Không; thứ tự discovery nói chung không được bảo đảm.
9. **Muốn stdout ổn định khi có nhiều provider, làm gì?** Sắp xếp theo thuộc tính domain như `code()`/priority và quy định xử lý duplicate.
10. **Tệp đăng ký classpath tên thế nào?** `META-INF/services/demo.api.GreetingService`, nội dung là fully qualified provider class names.
11. **Một provider class có trên classpath là đủ để ServiceLoader tự phát hiện?** Không, phải có service configuration resource phù hợp.
12. **Một `ServiceLoader` có thread-safe không?** Không, phải đồng bộ hoặc xây registry phù hợp.
13. **`reload()` có tự thêm JAR vào module graph của JVM đang chạy?** Không.
14. **Một explicit named module có thể dùng provider factory method không?** Có, theo hợp đồng public static no-arg `provider()` trả service type; classpath/automatic module có yêu cầu khác.
15. **Tại sao không chỉ bắt Exception?** `ServiceConfigurationError` là `Error`, nên cần hiểu và xử lý riêng nếu muốn thêm ngữ cảnh.
16. **Khi module đã khai báo `provides` nhưng consumer không thấy plugin, kiểm tra gì?** Module graph/resolution, uses declaration, loader/layer scope và packaging.

## Tài liệu chính thức và hiện hành

- Java SE 26 — `java.util.ServiceLoader`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 26 — `ServiceLoader.Provider` (`type()` và `get()`): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java SE 26 — `java.util.spi.ToolProvider`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ToolProvider.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261
- Dev.java — Decoupling Modules with Services (`uses`, `provides`, service binding): https://dev.java/learn/organizing/modules/services/
- Java Language Specification, Modules/`uses`/`provides`: https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html#jls-7.7

**Kết luận:** `ServiceLoader` là công cụ chuẩn để **khám phá nhiều implementation cho một SPI**. Java 9 cho phép các module liên kết service tường minh qua `uses/provides` và truy vấn provider metadata bằng `stream()`. Trong ứng dụng thật, phải quản lý thứ tự lựa chọn, trường hợp thiếu/trùng provider, packaging, lỗi cấu hình và vòng đời/class loader — thay vì phụ thuộc “provider đầu tiên tìm thấy”.
