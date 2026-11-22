# Định nghĩa kiểu dịch vụ và implementation trong ServiceLoader (Java 17+)

`java.util.ServiceLoader<S>` là API chuẩn của Java để **tìm và khởi tạo các implementation đã được đăng ký** cho một kiểu dịch vụ. API xuất hiện từ Java 6 và vẫn được dùng trong Java hiện đại, bao gồm ứng dụng chạy trên **classpath** và ứng dụng dùng **Java Platform Module System (JPMS)**.

Điểm cốt lõi của bài: **định nghĩa service type (hợp đồng), triển khai provider, đăng ký provider và để consumer chỉ phụ thuộc vào hợp đồng**. Một class chỉ có `implements` interface chưa tự động được ServiceLoader phát hiện.

```text
Consumer ------> Service type <------ Provider A
      |                 ^             Provider B
      |                 |
      +---- ServiceLoader tìm provider theo cấu hình runtime
```

## 1. Ba vai trò cần phân biệt

| Vai trò | Là gì? | Trách nhiệm |
| --- | --- | --- |
| **Service type** | `interface` hoặc `abstract class` đại diện cho một dịch vụ | Định nghĩa phương thức và quy tắc mà mọi implementation tuân thủ |
| **Service provider** | Class hoặc provider factory tạo ra đối tượng dịch vụ | Thực thi hợp đồng và được đăng ký để ServiceLoader khám phá |
| **Consumer** | Code sử dụng một hoặc nhiều provider | Chọn implementation theo yêu cầu nghiệp vụ, xử lý thiếu provider/lỗi khởi tạo |

Một **service** trong ServiceLoader được đại diện bởi một kiểu Java duy nhất, thường là interface. Service type có thể là abstract class nếu cần hành vi dùng chung, nhưng interface dễ tạo lớp API nhỏ, độc lập implementation. Service type **không phải** một object instance hoặc một “service” đang chạy trên mạng; đó là hợp đồng kiểu trong Java.

**ServiceLoader là cơ chế Service Provider Interface (SPI)**. Nó không tự động thực hiện toàn bộ dependency injection, quản lý vòng đời của một hệ thống plugin, chọn provider tốt nhất hay quét tất cả class đang có.

## 2. Thiết kế service type tốt

Giả sử ứng dụng cần chọn bộ tạo lời chào theo ngôn ngữ. Tạo API:

**`src/com/example/api/GreetingService.java`**

```java
package com.example.api;

public interface GreetingService {
    String languageTag();
    String greet(String name);
}
```

`greet` là chức năng chung; `languageTag` là metadata để consumer có thể chọn provider. ServiceLoader không tự hiểu ngôn ngữ, độ ưu tiên hay khả năng xử lý request; chính ứng dụng phải dựa trên contract để quyết định.

### Những quy tắc thiết kế quan trọng

1. **Giữ API độc lập implementation:** contract không import class riêng của nhà cung cấp. Consumer chỉ biên dịch dựa trên API; đổi provider không buộc sửa consumer.
2. **Định nghĩa rõ đầu vào và đầu ra:** quy định cách xử lý `null`, chuỗi rỗng, dữ liệu không hợp lệ, exception có thể phát sinh và điều kiện trả kết quả.
3. **Giữ hợp đồng nhất quán:** hai provider phải tuân theo cùng ngữ nghĩa phương thức. `greet` không nên bất ngờ xóa file hoặc gửi network request nếu contract chỉ hứa định dạng chuỗi.
4. **Hỗ trợ lựa chọn khi có nhiều provider:** metadata như `id()`, `languageTag()`, `supports(Format)` hoặc `priority()` nên có ý nghĩa được định nghĩa rõ, thay vì chọn theo thứ tự tùy tiện.
5. **Thiết kế API ổn định:** thêm abstract method vào interface có thể khiến implementation hiện có không còn tương thích. Dùng versioning, kiểm thử tương thích và cân nhắc default method khi có cơ sở rõ ràng.
6. **Ghi rõ thread safety:** ServiceLoader không làm cho object provider tự động an toàn khi dùng chung giữa các luồng. Implementation phải tuân thủ hợp đồng đã công bố.
7. **Đừng phình interface:** nếu mỗi provider chỉ hỗ trợ một phần, cân nhắc chia thành nhiều service type nhỏ, thay vì để nhiều method ném `UnsupportedOperationException`.

Provider có thể có thêm phương thức nội bộ, dependency, cấu hình hoặc cache. Consumer không nên cần biết những chi tiết đó nếu chúng không thuộc hợp đồng.

## 3. Viết implementation phù hợp với contract

Một provider trên **classpath** thường là class `public` triển khai interface, có **constructor `public` không tham số**.

**`src/com/example/provider/EnglishGreeting.java`**

```java
package com.example.provider;

import com.example.api.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String languageTag() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Tại sao thiết kế như vậy?

- `implements GreetingService` để compiler kiểm tra các phương thức của contract.
- `public` class và constructor `public` không tham số giúp ServiceLoader khởi tạo theo **provider constructor**.
- `final` là lựa chọn để hạn chế kế thừa implementation này; **không bắt buộc** đối với ServiceLoader.
- Constructor ở đây không cần tham số. `ServiceLoader` không tự suy ra cách inject arbitrary dependency vào constructor có tham số.
- Phương thức `languageTag()` cung cấp khả năng chọn implementation; `greet()` cung cấp chức năng thật.

**Lưu ý:** provider type theo tài liệu ServiceLoader phải `public` và không là *inner class*. Class top-level là lựa chọn dễ đọc, dễ đóng gói. Việc provider có state, cache, client hay mutable data không phải do ServiceLoader quản lý; cần thiết kế riêng.

## 4. Đăng ký trên classpath bằng `META-INF/services`

Khi chạy ứng dụng không dùng explicit named module, provider phải được khai báo trong **service configuration file**:

```text
META-INF/services/<fully-qualified-service-type>
```

Với ví dụ `GreetingService`, tên file chính xác là:

```text
META-INF/services/com.example.api.GreetingService
```

Nội dung file là danh sách **tên lớp provider đầy đủ**, mỗi tên trên một dòng:

```text
com.example.provider.EnglishGreeting
```

Các quy tắc quan trọng:

- Tên tệp là tên đầy đủ của **service type**, còn mỗi dòng bên trong là tên class **implementation**.
- File được mã hóa UTF-8; được phép có dòng trống và comment bắt đầu bằng `#`. Tên provider lặp trong metadata được bỏ qua.
- Resource phải thực sự nằm trong output directory hoặc JAR **trên classpath runtime**; chỉ đặt nó trong thư mục source là chưa đủ.
- Provider phải visible với class loader thực hiện tìm kiếm, là subtype của service trong chế độ provider constructor và có constructor đúng điều kiện.
- Đừng nhầm với `module-info.java`: đó là cách đăng ký cho **explicit named module**, được trình bày ở mục 6.

### Ví dụ classpath hoàn chỉnh, có thể chạy trên Java 17+

Tạo đúng các file sau trong thư mục `classpath-demo`:

```text
classpath-demo/
  src/
    com/example/api/GreetingService.java
    com/example/provider/EnglishGreeting.java
    com/example/app/Main.java
    META-INF/services/com.example.api.GreetingService
```

Nội dung `GreetingService.java` và `EnglishGreeting.java` là hai file đầy đủ ở mục 2 và 3. Thêm consumer:

**`src/com/example/app/Main.java`**

```java
package com.example.app;

import com.example.api.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        boolean found = false;
        for (GreetingService provider : loader) {
            if ("en".equals(provider.languageTag())) {
                System.out.println(provider.greet("Lan"));
                found = true;
                break;
            }
        }
        if (!found) {
            throw new IllegalStateException("No English provider");
        }
    }
}
```

Điểm đáng chú ý: `Main` import `GreetingService` và `ServiceLoader`; **không import hoặc gọi `new EnglishGreeting()`**. Việc tạo provider là do ServiceLoader và cấu hình runtime quyết định.

Từ thư mục `classpath-demo`, chạy bằng Bash:

```bash
mkdir -p out
javac -encoding UTF-8 -d out src/com/example/api/GreetingService.java src/com/example/provider/EnglishGreeting.java src/com/example/app/Main.java
cp -R src/META-INF out/
java -cp out com.example.app.Main
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/com/example/api/GreetingService.java src/com/example/provider/EnglishGreeting.java src/com/example/app/Main.java
Copy-Item -Recurse -Force src/META-INF out/
java -cp out com.example.app.Main
```

**Stdout chính xác:**

```text
Hello, Lan!
```

Lệnh `javac` biên dịch class vào `out`. Lệnh `cp` hoặc `Copy-Item` sao chép thư mục `META-INF` để ServiceLoader có thể tìm thấy provider. Nếu bỏ bước sao chép, chương trình vẫn compile nhưng không tìm thấy provider trong môi trường chạy ví dụ này; consumer sẽ ném `IllegalStateException`.

Trong dự án thật, có thể chia API, implementation và app thành các JAR riêng. Provider JAR phải chứa resource `META-INF/services/...` và implementation class; công cụ build như Maven/Gradle cần đóng gói resource đúng đường dẫn. Kiểm tra nhanh bằng `jar tf provider.jar`.

## 5. ServiceLoader tạo object lúc nào?

`ServiceLoader.load(GreetingService.class)` tạo một loader; nó không đảm bảo đã khởi tạo mọi provider ngay tại dòng này. Phần tìm và khởi tạo provider diễn ra **lazily** khi consumer duyệt bằng `iterator()`, `for-each`, `findFirst()` hoặc xử lý `stream()`.

- Khi không tìm thấy provider, duyệt iterator sẽ không trả implementation nào. Đây không tự động là lỗi của `ServiceLoader`; consumer phải có fallback hoặc thông báo lỗi nếu nghiệp vụ yêu cầu.
- Khi có nhiều provider, ServiceLoader có thể trả nhiều implementation; thứ tự giữa các nguồn/module **không nên dùng làm chính sách chọn mặc định**.
- Các provider đã load được cache trong từng loader. `reload()` xóa cache để lần duyệt tiếp theo tìm provider lại.
- Nếu metadata sai, provider không load được, constructor không hợp lệ hoặc factory thất bại, Java có thể ném `ServiceConfigurationError` trong quá trình duyệt/load.
- `ServiceLoader` không thread-safe; không dùng chung một instance loader qua nhiều thread mà thiếu chiến lược đồng bộ thích hợp.
- `ServiceLoader.load(ServiceType.class)` sử dụng context class loader của thread theo hợp đồng API. Trong môi trường plugin/container, class loader và vị trí resource có thể quyết định provider nào được tìm thấy.

Nếu service có nhiều provider, dùng metadata của interface để chọn:

```java
// Đoạn minh họa để đặt trong consumer khi đã có GreetingService.
GreetingService selected = ServiceLoader
        .load(GreetingService.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(p -> "en".equals(p.languageTag()))
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("No English provider"));
```

Đoạn trên dùng `ServiceLoader.stream()`, có từ Java 9 và vẫn có ích trên Java 17+. Trong thực tế, nếu chỉ cần metadata về class provider mà chưa muốn tạo instance, có thể kiểm tra `Provider::type` trước khi gọi `Provider::get`. Tuy nhiên, với provider factory method ở named module, `type()` mô tả kiểu trả về của factory, không nhất thiết là class factory khai báo trong `provides`.

## 6. Định nghĩa service và implementation bằng Java modules

JPMS (Java 9+) đưa cơ chế SPI vào **module descriptor**. Với explicit named modules:

- Module **API** `exports` package chứa service type.
- Module **provider** `requires` API và đăng ký `provides ServiceType with ProviderClass`.
- Module **consumer** `requires` API và khai báo `uses ServiceType`.
- Consumer **không cần** `requires` module implementation; service binding có thể đưa các provider phù hợp vào module graph.

### Ví dụ modular hoàn chỉnh (Java 17+)

Đây là **một dự án riêng biệt** với ví dụ classpath ở mục 4.

```text
module-demo/
  src/
    com.example.greet.api/
      module-info.java
      com/example/greet/api/Greeting.java
    com.example.greet.provider/
      module-info.java
      com/example/greet/provider/VietnameseGreeting.java
    com.example.greet.app/
      module-info.java
      com/example/greet/app/Main.java
```

**`src/com.example.greet.api/module-info.java`**

```java
module com.example.greet.api {
    exports com.example.greet.api;
}
```

**`src/com.example.greet.api/com/example/greet/api/Greeting.java`**

```java
package com.example.greet.api;

public interface Greeting {
    String greet(String name);
}
```

**`src/com.example.greet.provider/module-info.java`**

```java
module com.example.greet.provider {
    requires com.example.greet.api;
    provides com.example.greet.api.Greeting
            with com.example.greet.provider.VietnameseGreeting;
}
```

**`src/com.example.greet.provider/com/example/greet/provider/VietnameseGreeting.java`**

```java
package com.example.greet.provider;

import com.example.greet.api.Greeting;

public final class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
```

**`src/com.example.greet.app/module-info.java`**

```java
module com.example.greet.app {
    requires com.example.greet.api;
    uses com.example.greet.api.Greeting;
}
```

**`src/com.example.greet.app/com/example/greet/app/Main.java`**

```java
package com.example.greet.app;

import com.example.greet.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        for (Greeting provider : ServiceLoader.load(Greeting.class)) {
            System.out.println(provider.greet("Lan"));
        }
    }
}
```

Biên dịch và chạy từ thư mục `module-demo`, trong Bash hoặc PowerShell (lệnh một dòng):

```bash
javac -encoding UTF-8 --module-source-path src -d mods src/com.example.greet.api/module-info.java src/com.example.greet.api/com/example/greet/api/Greeting.java src/com.example.greet.provider/module-info.java src/com.example.greet.provider/com/example/greet/provider/VietnameseGreeting.java src/com.example.greet.app/module-info.java src/com.example.greet.app/com/example/greet/app/Main.java
java --module-path mods --module com.example.greet.app/com.example.greet.app.Main
```

**Stdout chính xác:**

```text
Xin chao, Lan!
```

Tại sao chạy được?

1. `com.example.greet.api` định nghĩa và `exports` kiểu `Greeting`.
2. `com.example.greet.provider` triển khai kiểu đó, khai báo `provides`. Package chứa implementation **không cần export**.
3. `com.example.greet.app` chỉ yêu cầu API, có `uses` nên ServiceLoader và module system có thể tìm provider thông qua module graph.
4. Khi `for-each` duyệt loader, provider được tạo qua constructor và được trả về dưới kiểu `Greeting`.

**Khác biệt đăng ký:** classpath sử dụng resource `META-INF/services/com.example.api.GreetingService`; explicit named module sử dụng `provides ... with ...`. Không chuyển máy móc cách này sang cách kia và giả định discovery hoạt động y hệt.

## 7. Hai cơ chế tạo provider: constructor và method

Một implementation cần thỏa **quy tắc khởi tạo** tương ứng với nơi provider được triển khai:

| Cơ chế | Yêu cầu | Nơi áp dụng |
| --- | --- | --- |
| **Provider constructor** | Provider class là subtype của service, có constructor `public` không tham số | Classpath, automatic module, hoặc explicit named module |
| **Provider method** | Class đăng ký có phương thức `public static provider()` không tham số, trả kiểu assignable sang service | **Explicit named module** |

### Provider constructor

`VietnameseGreeting` ở mục 6 là một ví dụ: nó `implements Greeting` và có `public VietnameseGreeting()`.

Nếu constructor có tham số bắt buộc và không có constructor `public` không tham số, ServiceLoader **không thể** tự gọi nó theo cơ chế constructor. Nếu muốn cấu hình phức tạp, cân nhắc đưa việc tạo tài nguyên vào một service kiểu factory, hoặc dùng provider method trong explicit named module.

### Provider factory method cho explicit named module

Trong module provider có thể dùng class factory sau làm phương án **thay thế** `VietnameseGreeting`:

```java
package com.example.greet.provider;

import com.example.greet.api.Greeting;

// Minh họa riêng: chưa nằm trong build ở mục 6.
public final class GreetingFactory {
    private GreetingFactory() {
    }

    public static Greeting provider() {
        return name -> "Factory says hello, " + name + "!";
    }
}
```

Nếu bổ sung class này vào source thực tế, có thể thay `provides` của module provider bằng:

```java
provides com.example.greet.api.Greeting
        with com.example.greet.provider.GreetingFactory;
```

Factory class **không cần `implements Greeting`**; kết quả của `provider()` mới cần là một `Greeting`. Tên method `provider` và modifier `public static` không tham số là một phần quy tắc của ServiceLoader. Nếu method trả `null` hoặc ném exception, discovery/khởi tạo có thể ném `ServiceConfigurationError`.

**Không dùng provider factory method này cho cấu hình `META-INF/services` trên classpath hay automatic module**; ở đó yêu cầu provider constructor. Đây là một khác biệt vẫn quan trọng trong JDK hiện hành.

*Ghi chú chạy thử:* `GreetingFactory` là đoạn minh họa mở rộng, không được liệt kê trong lệnh `javac` của dự án mẫu. Muốn thử, phải tạo thêm file source và cập nhật `module-info.java` cùng lệnh compile tương ứng.

## 8. Ranh giới thực tế: thiết kế provider có thể mở rộng và an toàn

### 8.1. Đặt API ở artifact độc lập

Tách `greeting-api`, `greeting-provider-x`, `greeting-provider-y` và `greeting-app` giúp consumer không phụ thuộc vào implementation. Provider vẫn cần API để biên dịch, và tại runtime phải phân phối đủ JAR/module cùng dependencies của provider.

Service type nên sử dụng những kiểu dữ liệu ổn định và được các provider hiểu giống nhau. Tránh để API trả kiểu nội bộ của một vendor cụ thể, vì điều đó buộc tất cả provider phụ thuộc vào vendor đó.

### 8.2. Chọn contract dạng factory khi tạo tài nguyên đắt

Nếu mỗi provider cần khởi tạo client, connection hoặc codec nặng, có thể định nghĩa service type là `ClientFactory`/`CodecFactory` thay vì trả về một client duy nhất ngay lập tức. Consumer chọn factory trước, rồi tạo tài nguyên khi cần.

**Đừng nhầm** service contract dạng factory với method `public static provider()` của JPMS: cái trước là thiết kế API nghiệp vụ, cái sau là một cơ chế để ServiceLoader khởi tạo provider.

### 8.3. Không giả định tự động chọn provider duy nhất

ServiceLoader cho phép **không có, một hoặc nhiều** provider. `findFirst()` có ích nếu nghiệp vụ thật sự chấp nhận bất kỳ provider nào; nếu cần ngôn ngữ, định dạng, phiên bản, quyền hạn hoặc ưu tiên cụ thể, hãy chọn theo metadata và quy tắc rõ ràng.

### 8.4. Hạn chế side effect trong provider constructor

Provider có thể khởi tạo lazily tại một thời điểm consumer không ngờ tới. Constructor làm quá nhiều I/O, gọi mạng hay thực thi tác vụ dài dễ khiến thao tác tìm provider trở nên khó chẩn đoán. Đặt trách nhiệm khởi tạo tốn kém vào API/service phù hợp, log lỗi rõ ràng và tôn trọng thời gian sống của tài nguyên.

### 8.5. Tách discovery và ứng dụng nghiệp vụ

`ServiceLoader` không bảo đảm isolation, sandbox, authorization hoặc trust cho plugin. Chỉ cài đặt/cho phép provider từ nguồn tin cậy, quản lý dependency và cấu hình runtime có kiểm soát. Một provider có thể chạy mã khi khởi tạo hay khi phương thức được gọi.

## 9. Kiểm thử triển khai và các lỗi thường gặp

Kiểm thử **contract** trực tiếp, rồi kiểm thử **SPI discovery** với đúng cách đóng gói mà ứng dụng sẽ chạy.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ServiceLoader` không trả provider classpath | Thiếu resource hoặc sai tên `META-INF/services/<service type>` | Kiểm tra đúng binary name, nội dung UTF-8, thư mục output và JAR bằng `jar tf` |
| Class có `implements` nhưng không được phát hiện | Chưa đăng ký provider | Tạo resource trên classpath hoặc khai báo `provides` trong explicit named module |
| `ServiceConfigurationError` lúc duyệt | Không tìm được class, sai subtype, thiếu constructor hoặc factory lỗi | Kiểm tra tên fully qualified, signature, cause và runtime dependencies |
| Module consumer không thấy provider | Thiếu `uses`, `provides` hoặc module provider không được phân phối/resolve | Kiểm tra module descriptor và `--module-path`; dùng `--show-module-resolution` để xem graph |
| App chọn sai provider | Dựa vào vị trí đầu trong danh sách hoặc không có metadata | Định nghĩa chính sách chọn provider rõ ràng |
| Có code import `ConcreteProvider` ở consumer | Consumer ràng buộc vào implementation | Import interface API, sử dụng ServiceLoader và đăng ký provider |
| Provider lỗi khi nhiều luồng truy cập | State của implementation không thread-safe | Bảo đảm hợp đồng concurrency hoặc kiểm soát việc chia sẻ object |
| Constructor ném lỗi bất ngờ | Dependency/cấu hình runtime thiếu, khởi tạo có side effect | Log nguyên nhân, kiểm thử runtime và thiết kế lifecycle rõ ràng |

### Checklist trước khi phát hành

- [ ] Service type được công bố ở package/API có thể truy cập và có contract rõ.
- [ ] Provider là implementation hợp lệ, khai báo constructor hoặc provider method đúng chế độ.
- [ ] Resource `META-INF/services` hoặc `provides` đã có trong artifact thực tế.
- [ ] Consumer dùng API và xử lý trường hợp không có provider.
- [ ] Khi có nhiều provider, có tiêu chí lựa chọn được kiểm thử.
- [ ] Đã chạy kiểm thử discovery với artifact/module path tương ứng môi trường production.
- [ ] Có phương án quan sát `ServiceConfigurationError`, xử lý lỗi và quản lý state/provider lifecycle.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Chỉ viết `class EnglishGreeting implements GreetingService` có đủ để ServiceLoader tự tìm thấy không?

**Đáp án:** chưa. Cần đăng ký bằng resource `META-INF/services` trên classpath hoặc `provides` trong explicit named module.

**Câu 2.** Vì sao trong JPMS consumer cần `uses Greeting` nhưng không nên `requires` trực tiếp module provider?

**Đáp án:** `uses` mô tả nhu cầu service cho module system; module provider tự công bố `provides`. Consumer chỉ cần phụ thuộc vào module xuất service API, nhờ vậy implementation có thể thay đổi độc lập.

**Câu 3.** Khi nào dùng provider method?

**Đáp án:** trong explicit named module, khi muốn một class có `public static provider()` tạo đối tượng service. Class factory không nhất thiết implements service; method phải trả kiểu phù hợp. Classpath và automatic module cần constructor hợp lệ.

**Câu 4.** Nếu có hai provider cùng cho `GreetingService`, cách nào chọn đáng tin hơn?

**Đáp án:** chọn theo `languageTag()` hoặc một tiêu chí được định nghĩa trong contract và ứng dụng, thay vì phụ thuộc vào thứ tự nhận được khi duyệt.

**Câu 5.** Nếu classpath demo compile nhưng báo `No English provider`?

**Đáp án:** trước tiên kiểm tra `out/META-INF/services/com.example.api.GreetingService` có tồn tại, nội dung đúng tên `com.example.provider.EnglishGreeting`, và `out` nằm trong `-cp` khi chạy.

## Tài liệu chính thức

- [ServiceLoader — Oracle Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [ServiceLoader.Provider — Oracle Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html)
- [Decoupling Modules with Services — dev.java](https://dev.java/learn/organizing/modules/services/)
- [Java Language Specification — Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7)

**Ghi nhớ:** định nghĩa một **service type** ổn định, viết **implementation** thỏa contract, **đăng ký provider** theo classpath hoặc JPMS, rồi để consumer tìm và chọn provider qua `ServiceLoader` mà không cần phụ thuộc trực tiếp vào class triển khai.
