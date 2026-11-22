# Bảo toàn tệp đăng ký dịch vụ khi gộp hoặc đổi tên package trong JAR

## 1. Vì sao plugin có thể biến mất sau khi đóng gói?

Java SPI (Service Provider Interface) cho phép ứng dụng tìm implementation tại thời điểm chạy qua `java.util.ServiceLoader`, không cần liệt kê các implementation trong mã ứng dụng. Với đăng ký bằng classpath/module path kiểu JAR truyền thống, một thư viện khai báo provider bằng tệp văn bản:

```text
META-INF/services/<tên nhị phân đầy đủ của service interface>
```

Mỗi dòng hữu hiệu trong tệp là **tên nhị phân đầy đủ của một provider class**; dòng trống và phần sau dấu `#` là chú thích. Ví dụ:

```text
# META-INF/services/com.example.spi.GreetingProvider
com.example.plugin.EnGreetingProvider
com.example.plugin.ViGreetingProvider
```

Khi build JAR thông thường, việc copy resources giữ nguyên tệp này. Rủi ro phát sinh ở bước **fat/uber JAR**, **shade**, **relocate** package hoặc **minimize**: class có thể vẫn tồn tại trong JAR nhưng provider không được tìm thấy; ngược lại, metadata tồn tại nhưng trỏ đến class đã đổi tên hoặc bị loại khỏi artifact. Đây là lỗi về **quan hệ giữa bytecode, tên class và tài nguyên đăng ký**, không thể sửa bằng việc chỉ chỉnh `MANIFEST.MF`.

## 2. Quy tắc phải giữ nguyên

Có ba thành phần phải nhất quán:

1. **Service type:** tên sau `META-INF/services/` phải khớp với tên nhị phân đầy đủ của interface/abstract class mà `ServiceLoader.load(ServiceType.class)` yêu cầu. Nếu relocation đổi package của service interface, tên **tệp** đăng ký cũng phải được cập nhật.
2. **Provider type:** mỗi tên class ghi trong nội dung tệp phải trỏ tới provider thực sự nằm trong JAR sau khi relocate. Nếu implementation đổi từ `com.example.plugin.Foo` sang `shaded.com.example.plugin.Foo`, tên trong nội dung phải đổi tương ứng.
3. **Khả năng nạp:** provider phải tuân thủ hợp đồng SPI (tương thích với service type, có thể được ServiceLoader khởi tạo theo cơ chế thích hợp) và classloader/module layer sử dụng phải nhìn thấy cả metadata lẫn class.

Ở classpath, provider thông thường là class concrete public có public constructor không tham số. Trong named Java modules, `provides ... with ...` là cơ chế khai báo chuẩn; quy định về constructor/provider method có điểm khác, vì vậy không suy diễn cơ chế classpath sang mọi module.

### Khi merge nhiều JAR

Hai thư viện có thể chứa **cùng đường dẫn** `META-INF/services/com.example.spi.GreetingProvider`, nhưng nội dung khác nhau. Nếu công cụ đóng gói lấy một tệp và ghi đè tệp còn lại, một hoặc nhiều provider sẽ bị mất khỏi danh sách. Tệp kết quả cần giữ **hợp** các provider hợp lệ, thường là ghép từng dòng rồi xử lý trùng lặp/chú thích theo công cụ build:

```text
# plugin-a.jar
com.example.plugins.EnglishGreeting

# plugin-b.jar
com.example.plugins.VietnameseGreeting

# đúng trong uber.jar, sau merge
com.example.plugins.EnglishGreeting
com.example.plugins.VietnameseGreeting
```

Đừng áp dụng chiến lược hợp nhất bằng cách ghi đè hoặc nối byte tùy tiện vào các tài nguyên cấu hình khác: `META-INF/services/` có ngữ nghĩa riêng. Kiểm tra riêng các tài nguyên liên quan của framework nếu chúng dùng định dạng khác.

### Khi relocate package

Hãy phân biệt hai trường hợp:

| Thay đổi | Tên tệp đăng ký | Nội dung tệp |
| --- | --- | --- |
| Chỉ đổi package provider | Giữ tên service interface | Đổi tên provider tương ứng |
| Đổi package service interface | Đổi theo tên service interface mới | Đổi provider nếu provider cũng relocate |
| Chỉ gộp JAR, không relocate | Giữ nguyên | Hợp nhất danh sách provider của các JAR |
| Provider bị loại bởi minimizer | Tệp có thể còn | Phải giữ class được khai báo hoặc bỏ đăng ký có chủ đích |

Không tự đổi tên tệp nếu ứng dụng vẫn gọi API service gốc: `ServiceLoader` tìm đúng tên service type mà nó nhận được.

## 3. Cấu trúc ví dụ tối thiểu

Giả sử có API và hai plugin:

```text
src/
  com/example/spi/GreetingProvider.java
  com/example/plugin/EnglishGreeting.java
  com/example/plugin/VietnameseGreeting.java
  Demo.java
resources/
  META-INF/services/com.example.spi.GreetingProvider
```

`src/com/example/spi/GreetingProvider.java`:

```java
package com.example.spi;

public interface GreetingProvider {
    String greeting();
}
```

`src/com/example/plugin/EnglishGreeting.java`:

```java
package com.example.plugin;

import com.example.spi.GreetingProvider;

public final class EnglishGreeting implements GreetingProvider {
    public EnglishGreeting() {}
    @Override public String greeting() { return "Hello"; }
}
```

`src/com/example/plugin/VietnameseGreeting.java`:

```java
package com.example.plugin;

import com.example.spi.GreetingProvider;

public final class VietnameseGreeting implements GreetingProvider {
    public VietnameseGreeting() {}
    @Override public String greeting() { return "Xin chào"; }
}
```

`resources/META-INF/services/com.example.spi.GreetingProvider` (UTF-8):

```text
com.example.plugin.EnglishGreeting
com.example.plugin.VietnameseGreeting
```

`src/Demo.java`:

```java
import com.example.spi.GreetingProvider;
import java.util.ServiceLoader;

public class Demo {
    public static void main(String[] args) {
        for (GreetingProvider provider : ServiceLoader.load(GreetingProvider.class)) {
            System.out.println(provider.greeting());
        }
    }
}
```

Biên dịch và chạy ví dụ trên với Java 17+ ở thư mục chứa `src` và `resources`:

```bash
javac -d out src/com/example/spi/GreetingProvider.java src/com/example/plugin/EnglishGreeting.java src/com/example/plugin/VietnameseGreeting.java src/Demo.java
jar --create --file greetings.jar -C out . -C resources .
java -cp greetings.jar Demo
```

Output (theo thứ tự provider trong tệp đăng ký của ví dụ này):

```text
Hello
Xin chào
```

`jar -C resources .` là bước cốt yếu: phải đóng gói tệp đăng ký cùng các `.class`. Một JAR chỉ chứa class mà quên `META-INF/services` vẫn có thể chạy lệnh `java` thành công, nhưng vòng lặp `ServiceLoader` không in gì.

## 4. Cấu hình build khi tạo fat/shaded JAR

### Gradle Shadow

Với Gradle và plugin Shadow tương thích với phiên bản Gradle đang dùng, yêu cầu merge tệp SPI bằng transformer chuyên dụng:

```groovy
// build.gradle: ví dụ phần cấu hình khi plugin Shadow đã được áp dụng
tasks.named('shadowJar') {
    mergeServiceFiles()
}
```

`mergeServiceFiles()` hợp nhất các tệp trong `META-INF/services` từ những dependency được đưa vào Shadow JAR. Nếu có relocation, cần xác minh trong artifact cuối rằng **cả tên tệp và tên provider** đã được cập nhật đúng. Không mặc định mọi transformer hoặc mọi phiên bản plugin xử lý mọi loại metadata như nhau.

Một cấu hình relocation minh họa (trường hợp muốn cô lập package dependency):

```groovy
tasks.named('shadowJar') {
    mergeServiceFiles()
    relocate 'com.vendor.impl', 'internal.shaded.com.vendor.impl'
}
```

Sau build, hãy mở chính Shadow JAR để kiểm tra đường dẫn `META-INF/services` và từng dòng nội dung. Nếu service interface thuộc API công khai không relocate, tên tệp của API ấy phải giữ nguyên.

### Maven Shade

Với `maven-shade-plugin`, transformer `ServicesResourceTransformer` có nhiệm vụ hợp nhất các service descriptors và cập nhật tên theo relocation:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-shade-plugin</artifactId>
  <version>3.6.1</version>
  <executions>
    <execution>
      <phase>package</phase>
      <goals><goal>shade</goal></goals>
      <configuration>
        <transformers>
          <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
        </transformers>
        <relocations>
          <relocation>
            <pattern>com.vendor.impl</pattern>
            <shadedPattern>internal.shaded.com.vendor.impl</shadedPattern>
          </relocation>
        </relocations>
      </configuration>
    </execution>
  </executions>
</plugin>
```

Đây là đoạn cấu hình để đặt trong `<plugins>` của `pom.xml`, không phải một POM hoàn chỉnh. Khi thay đổi phiên bản plugin, kiểm tra tài liệu và kết quả build của chính phiên bản được dùng.

### JAR ghép thủ công

Nếu dùng script tự giải nén các dependency vào cùng một thư mục rồi đóng gói lại, việc giải nén có thể ghi đè những file SPI trùng đường dẫn. Cần thu thập tất cả service descriptors trước khi giải nén, kết hợp danh sách theo đúng service type, cập nhật tên khi relocate, rồi ghi tệp tổng hợp vào artifact. Dùng Shadow/Shade thường an toàn và dễ bảo trì hơn vì chúng có cơ chế xử lý tài nguyên SPI chuyên biệt.

## 5. Cách kiểm chứng artifact cuối

Việc nhìn vào source tree hoặc chạy unit test trên classpath của IDE chưa đủ: lỗi có thể chỉ xảy ra **sau khi package**. Hãy kiểm tra tệp JAR thực sự sẽ phân phối.

Liệt kê metadata:

```bash
jar --list --file build/libs/app-all.jar
```

Tìm những mục bắt đầu bằng `META-INF/services/`. Xem nội dung một descriptor (lệnh `unzip -p` nếu có công cụ unzip):

```bash
unzip -p build/libs/app-all.jar META-INF/services/com.example.spi.GreetingProvider
```

Đối chiếu bằng `jar --list` xem các class provider có mặt với đường dẫn tương ứng tên binary (`com.example.plugin.EnglishGreeting` → `com/example/plugin/EnglishGreeting.class`). Với relocation, đối chiếu mọi tên **sau** thay đổi.

Chạy smoke test trên **JAR sau đóng gói** bằng classpath/module path giống môi trường triển khai, liệt kê provider thay vì chỉ kiểm tra không ném exception:

```java
long count = ServiceLoader.load(GreetingProvider.class).stream().count();
if (count != 2) {
    throw new AssertionError("Expected 2 providers, found " + count);
}
```

Đây là **đoạn Java đặt trong một method hoặc test**, không phải câu lệnh có thể chạy trực tiếp trong shell. Với API `ServiceLoader.stream()`, việc liệt kê có thể kích hoạt kiểm tra provider/configuration; kiểm tra thêm khả năng khởi tạo và hành vi thực tế bằng cách duyệt instance như trong `Demo`.

Một kiểm tra CI hữu ích: build artifact → đọc toàn bộ service descriptors → xác minh mỗi provider tham chiếu đến class tồn tại → chạy test `ServiceLoader` với artifact đó. Với plugin tùy chọn, kiểm tra đúng **tập provider kỳ vọng của từng cấu hình phân phối**, tránh hard-code một số lượng cho mọi môi trường.

## 6. Các lỗi hay gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `ServiceLoader` trả về 0 provider | Không đóng gói descriptor, đặt sai tên tệp hoặc classloader không nhìn thấy JAR | Kiểm tra `META-INF/services/<service FQCN>`, resource trong artifact và classloader |
| Thiếu một số plugin sau fat JAR | Một descriptor ghi đè descriptor khác | Dùng transformer hợp nhất service files; kiểm tra toàn bộ provider sau merge |
| `ServiceConfigurationError: Provider ... not found` | Descriptor trỏ tên cũ sau relocate hoặc class bị loại bởi minimizer | Cập nhật tên provider và quy tắc giữ class; đối chiếu nội dung JAR |
| `ServiceConfigurationError: ... not a subtype` | Mismatch giữa provider/service API; có thể do nhân đôi API class ở classloader khác | Bảo đảm provider triển khai đúng service type được nạp |
| Chạy ở IDE được, fat JAR không được | Build đóng gói resources khác classpath phát triển | Kiểm tra trực tiếp final JAR và chạy smoke test trên nó |
| Plugin load bằng module path nhưng không hiện | Descriptor trên classpath không thay cho module declaration của named module | Dùng `uses` và `provides ... with ...` hợp lệ trong `module-info.java`, kiểm tra module layer |

Lưu ý thêm: `ServiceLoader` có cơ chế lazy discovery và cache; khi thay đổi classpath/plugin runtime, có thể cần tạo loader mới hoặc gọi `reload()` trên instance loader phù hợp. Tuy nhiên `reload()` **không sửa được metadata thiếu/sai trong JAR**.

## 7. Trường hợp Java module system (JPMS)

Trong một **named module** khai báo tĩnh, provider được công bố bằng descriptor module:

```java
module com.example.plugin {
    requires com.example.spi;
    provides com.example.spi.GreetingProvider
        with com.example.plugin.EnglishGreeting;
}
```

Module consumer thường khai báo:

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingProvider;
}
```

Khi shade/relocate module có `module-info.class`, thay đổi package/class có thể làm hỏng `requires`, `exports`, `opens`, `uses`, `provides` và chữ ký/định danh module. Không giả định merge tệp `META-INF/services` là đủ để biến nhiều named module thành một named module hợp lệ. Nếu dùng **automatic module** hoặc chạy JAR trên classpath, hành vi tìm provider khác trường hợp named module có `module-info.class`; hãy test đúng chế độ triển khai.

## 8. Checklist khi phát hành plugin

- Xác định chính xác service interface và provider class công khai nào phải được giữ.
- Mở mọi dependency JAR có `META-INF/services/<service>`; ghi nhận danh sách provider trước merge.
- Cấu hình merge service descriptors khi tạo fat/uber JAR và cập nhật tên metadata khi relocate.
- Kiểm tra minimizer/obfuscator không xóa hoặc đổi tên provider mà metadata chưa được đồng bộ; dùng keep rules hoặc tắt minimize cho SPI cần thiết.
- Đọc descriptor và danh sách class **trong artifact cuối**, không suy luận từ source.
- Kiểm tra `ServiceLoader` trên artifact sau package, trong classloader/module layer sẽ triển khai.
- Chạy bài kiểm tra tích hợp với ít nhất hai provider từ hai dependency khi muốn chứng minh merge giữ đủ cả hai.
- Nếu thư viện đóng gói theo nhiều biến thể, kiểm tra từng biến thể; không mặc định `jar` thường và `shadowJar` có cùng nội dung.

**Nguyên tắc vận hành:** bảo toàn đăng ký SPI nghĩa là giữ được cả **đường dẫn descriptor**, **nội dung tên provider** và **class bytecode tương ứng** sau mọi bước gộp, relocate hoặc tối ưu hóa. Chỉ khi kiểm chứng cả ba trên artifact cuối mới có cơ sở khẳng định plugin được tìm thấy đúng lúc chạy.
