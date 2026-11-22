# Đăng ký `EnvironmentPostProcessor` và điều phối thứ tự thực thi trong Spring Boot 3.3

## 1. Bài toán: cần thay đổi Environment trước khi tạo các bean

Trong một ứng dụng Spring Boot, các giá trị cấu hình có thể đến từ `application.properties`, `application.yaml`, biến môi trường, đối số dòng lệnh, Java system properties, tệp ngoài ứng dụng và nhiều nguồn khác. Spring Boot kết hợp các nguồn này thành `Environment`, sau đó các thành phần dùng `@Value`, `Environment` hoặc `@ConfigurationProperties` để đọc và liên kết giá trị.

Có những yêu cầu không chỉ dừng ở việc khai báo một tệp:

- Thêm một `PropertySource` cung cấp các **giá trị mặc định của thư viện nội bộ**.
- Đọc một tệp cấu hình theo quy ước riêng từ classpath và đưa các khóa vào `Environment`.
- Tạo một giá trị dẫn xuất từ các thuộc tính đã có, trước khi bean nghiệp vụ khởi tạo.
- Chuyển tên một khóa cấu hình cũ sang tên mới trong giai đoạn chuyển đổi.
- Bổ sung hoặc thay đổi môi trường đủ sớm để hệ thống khởi động đọc được các khóa cần thiết.
- Điều phối nhiều bước xử lý môi trường theo một thứ tự có chủ đích.

Spring Boot 3.3 cung cấp giao diện **`EnvironmentPostProcessor`** để thực hiện điều đó.

Chủ đề bài này thuộc nhóm **Mở rộng Environment** của **Spring Boot Externalized Configuration**. Nội dung tập trung vào **cách đăng ký `EnvironmentPostProcessor` và điều phối thứ tự thực thi**, không chỉ vào việc viết một class Java đơn lẻ.

Bạn sẽ thực hành:

1. Viết `EnvironmentPostProcessor` dùng `MapPropertySource`.
2. Đăng ký trong `META-INF/spring.factories` với đúng khóa đầy đủ.
3. Điều phối hai processor bằng `Ordered` và `ConfigDataEnvironmentPostProcessor.ORDER`.
4. Phân biệt **thứ tự thực thi processor** với **độ ưu tiên của `PropertySource`**.
5. Quan sát giá trị trong `ApplicationRunner` và thử ghi đè từ CLI.
6. Nắm cách dùng `@Order`, xử lý logging sớm và `DeferredLogFactory`.
7. Tránh lỗi đăng ký, phụ thuộc bean quá sớm, vô tình ghi đè nguồn cấu hình và xử lý lặp.
8. Viết kiểm thử đơn vị cho thứ tự/PropertySource và kiểm thử tích hợp cho cơ chế discovery.

Các ví dụ dành cho **Java 17+ và Spring Boot 3.3.x**.

## 2. `EnvironmentPostProcessor` là gì?

Giao diện chính thức:

```java
package org.springframework.boot.env;

public interface EnvironmentPostProcessor {

    void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application);
}
```

Hai tham số:

- `ConfigurableEnvironment`: môi trường cấu hình có thể chỉnh sửa; từ đó truy cập `MutablePropertySources`, profile và giá trị property.
- `SpringApplication`: ứng dụng Spring Boot đang khởi động, không phải `ApplicationContext` đã hoàn thiện.

Theo JavaDoc Spring Boot 3.3, `EnvironmentPostProcessor` cho phép tùy biến `Environment` **trước khi application context được refresh**.

Một cách hình dung:

```text
SpringApplication.run(...)
         |
         v
Environment được chuẩn bị
         |
         +-- Các EnvironmentPostProcessor của Boot
         +-- Các EnvironmentPostProcessor tự viết
         |       |
         |       +-- thêm / thay đổi PropertySource
         |       +-- xử lý dữ liệu cấu hình bổ sung
         |
         v
Environment đã được điều chỉnh
         |
         v
ApplicationContext tạo và refresh
         |
         +-- Condition / auto-configuration
         +-- @ConfigurationProperties binding
         +-- @Value / Environment lookup
         +-- Bean khởi tạo
         |
         v
Ứng dụng phục vụ
```

Điểm khác với `@PostConstruct` hoặc `ApplicationRunner`: các cơ chế kia chạy khi bean/context đã được tạo hoặc ứng dụng gần như đã sẵn sàng, quá muộn cho nhiều quyết định dựa vào cấu hình khi khởi động.

### 2.1. `Environment` là gì?

`Environment` không chỉ là `System.getenv()`. Nó trừu tượng hóa nhiều nguồn có **độ ưu tiên khác nhau** và cung cấp API như:

```java
environment.getProperty("demo.region")
environment.getProperty("demo.timeout", Duration.class)
environment.getActiveProfiles()
```

Khi cần thay đổi tập nguồn cấu hình, dùng:

```java
MutablePropertySources sources = environment.getPropertySources();
```

với `ConfigurableEnvironment`.

`PropertySource` đại diện một nguồn có tên, ví dụ command-line arguments, system properties, system environment hoặc một cấu trúc `Map` được tạo bởi ứng dụng.

### 2.2. `EnvironmentPostProcessor` khác `BeanFactoryPostProcessor`

Hai loại này phục vụ hai giai đoạn và hai mục đích:

| Công cụ | Mục tiêu chính |
| --- | --- |
| `EnvironmentPostProcessor` | Thay đổi `Environment` trong giai đoạn sớm của Spring Boot |
| `ApplicationContextInitializer` | Tùy biến `ApplicationContext` trước refresh |
| `BeanFactoryPostProcessor` | Tác động đến bean definitions/BeanFactory trong quá trình chuẩn bị context |
| `BeanPostProcessor` | Can thiệp vòng đời từng bean |
| `ApplicationRunner` | Chạy sau khi application context khởi động |
| `@PropertySource` | Nạp một `PropertySource` thông qua cấu hình của Spring, thường muộn hơn thời điểm Boot cần một số khóa khởi động |

Vì các loại extension ở những tầng khác nhau, **thứ tự thực thi `EnvironmentPostProcessor` không tự điều phối bean post-processors**.

## 3. Spring Boot tìm `EnvironmentPostProcessor` ở đâu?

Trong **Spring Boot 3.3**, cách đăng ký chuẩn là khai báo implementation trong:

```text
src/main/resources/META-INF/spring.factories
```

Nội dung với một processor:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.MyEnvironmentPostProcessor
```

Phần bên trái là **tên đầy đủ của giao diện** `org.springframework.boot.env.EnvironmentPostProcessor`, không phải tên class của ứng dụng, không phải `spring.factories` namespace của Spring Framework, và không phải một tên tùy ý.

Phần bên phải là tên fully-qualified của implementation Java, gồm package và class.

Sau khi `spring.factories` có mặt trên classpath, Spring Boot dùng cơ chế factory loading của nó để tìm và khởi tạo các processor được đăng ký.

**Điểm cần nhớ:** chỉ viết một class có `implements EnvironmentPostProcessor` **chưa đủ** để Boot tự phát hiện nó. Annotation `@Component` cũng không phải con đường thay thế chuẩn cho đăng ký `EnvironmentPostProcessor`.

### 3.1. Không nhầm với `AutoConfiguration.imports`

Từ Spring Boot 3, các auto-configuration class thường được công bố qua:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nhưng **`EnvironmentPostProcessor` vẫn dùng**:

```text
META-INF/spring.factories
```

Đây là hai cơ chế discovery dành cho **hai loại extension khác nhau**. Không được chép tên processor vào `AutoConfiguration.imports` rồi mong `postProcessEnvironment(...)` tự chạy.

### 3.2. Đăng ký nhiều processor

Một file `spring.factories` có thể khai báo danh sách:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.DefaultsEnvironmentPostProcessor,example.environment.DerivedEnvironmentPostProcessor
```

Đây là một dòng trong file `.properties`. Có thể dùng dấu `\` nối dòng theo cú pháp properties nếu danh sách dài.

**Thứ tự xuất hiện trong danh sách không nên là hợp đồng thứ tự thực thi.** Muốn điều phối thứ tự, sử dụng `Ordered` hoặc `@Order` trên class.

### 3.3. Nếu project đã có `spring.factories`

Không tạo nhiều định nghĩa cùng một key trong **cùng file** rồi dựa vào việc parser sẽ tự ghép chúng. Dùng một giá trị gồm các tên class phân tách bằng dấu phẩy; giữ lại những đăng ký khác với key khác của file đó.

Với thư viện được đóng gói thành nhiều JAR, mỗi JAR có thể mang một `META-INF/spring.factories` của riêng nó. Cơ chế factory loading có thể nạp các đăng ký từ classpath mà không bắt buộc gom tất cả vào file của ứng dụng.

## 4. `EnvironmentPostProcessor` được khởi tạo như thế nào?

Với một implementation đơn giản:

```java
package example.environment;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;

public final class MyEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        // Chỉnh sửa Environment tại đây.
    }
}
```

Spring Boot tạo processor sớm, trước khi các bean thông thường được khởi tạo. Điều này có các hệ quả:

- Đừng mặc định constructor của processor có thể inject mọi `@Service`, `@Repository`, `DataSource`, HTTP client hoặc bean ứng dụng.
- Đừng trông chờ `@Value` trên field của processor được xử lý như trên một Spring bean bình thường.
- Đừng đặt `@PostConstruct` trên processor rồi coi đó là hook để thao tác sớm.
- Hãy dùng tham số `ConfigurableEnvironment` để lấy cấu hình đã có ở thời điểm processor chạy.
- Nếu cần những API đặc biệt do Boot hỗ trợ trong constructor, dùng đúng các loại constructor parameter đã được JavaDoc cho phép.

Spring Boot 3.3 hỗ trợ các tham số constructor **tùy chọn** dành cho processor:

- `DeferredLogFactory`.
- `ConfigurableBootstrapContext`; API bootstrap liên quan như `BootstrapContext` hoặc `BootstrapRegistry` được tài liệu đề cập.

Ví dụ:

```java
public MyEnvironmentPostProcessor(DeferredLogFactory factory) {
    // Tạo logger có hỗ trợ ghi log hoãn.
}
```

Không nên suy luận rằng một constructor bất kỳ nhận `MyRepository` sẽ được autowire như Spring bean. Bộ factory loading này không có hợp đồng DI của `ApplicationContext`.

## 5. Hai loại thứ tự rất dễ bị nhầm

Đây là điểm quan trọng nhất của bài.

### 5.1. Thứ tự thực thi processor

Giả sử có hai processor:

```text
A: nạp các giá trị fallback
B: đọc fallback và tạo một giá trị dẫn xuất
```

Nếu B phải thấy dữ liệu do A thêm vào, cần đảm bảo **A chạy trước B**:

```text
Environment trước A
       |
       v
A thêm PropertySource "defaults"
       |
       v
Environment sau A
       |
       v
B đọc các khóa vừa thêm, tạo "derived"
       |
       v
Environment sau B
```

Đây là **processor execution order**.

### 5.2. Độ ưu tiên của nguồn thuộc tính

Một `Environment` có nhiều `PropertySource`:

```text
PropertySources (mô tả từ ưu tiên cao xuống thấp)
  - commandLineArgs
  - systemProperties
  - systemEnvironment
  - config data
  - defaults
```

Khi cùng một key tồn tại ở nhiều nguồn, nguồn được tìm thấy trước theo thứ tự ưu tiên thường thắng.

```java
sources.addFirst(mySource);
```

đặt nguồn vào đầu danh sách nguồn tại thời điểm gọi, nên có thể **ghi đè** các nguồn hiện có.

```java
sources.addLast(mySource);
```

đặt nguồn vào cuối danh sách hiện tại, nên nó thường chỉ hoạt động như **fallback** so với các nguồn đang có.

Đây là **PropertySource precedence**.

**A chạy trước B không có nghĩa các giá trị của A luôn ưu tiên hơn B.** B có thể thêm một `PropertySource` vào cuối danh sách, hoặc A có thể thêm nguồn vào đầu. Quyết định phải dựa trên **cả hai trục thứ tự**.

### 5.3. Bảng phân biệt

| Câu hỏi | Cơ chế liên quan |
| --- | --- |
| Processor nào chạy trước? | `Ordered#getOrder()`, `@Order` |
| Một processor có nhìn thấy nguồn do processor khác thêm chưa? | Thứ tự thực thi |
| Nếu nhiều nguồn có cùng `demo.mode`, giá trị nào thắng? | Thứ tự `PropertySource` |
| Giá trị `application.yaml` đã được nạp trước khi processor đọc chưa? | Thời điểm processor so với Config Data |
| Profile-specific config đã được xử lý chưa? | Thời điểm Config Data xử lý |
| CLI override có thắng giá trị fallback không? | Vị trí `addFirst`/`addLast` và nguồn có hiệu lực |
| Có nên mở nhiều thread để chạy processor không? | Không; hãy theo hợp đồng lifecycle và thứ tự chính thức |

## 6. Điều phối processor bằng `Ordered`

Spring Boot 3.3 cho phép implementation của `EnvironmentPostProcessor` triển khai giao diện:

```java
import org.springframework.core.Ordered;
```

Ví dụ:

```java
public final class AlphaEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        // ...
    }
}
```

`Ordered` có phương thức:

```java
int getOrder();
```

Quy tắc chung:

**Giá trị order càng nhỏ thì mức ưu tiên chạy càng cao.**

Ví dụ:

```text
order=10    -> chạy trước
order=50    -> chạy sau
order=100   -> chạy muộn hơn
```

Các hằng số:

```java
Ordered.HIGHEST_PRECEDENCE
Ordered.LOWEST_PRECEDENCE
```

tương ứng với hai đầu của dải order.

### 6.1. Không sử dụng những số nguyên tùy ý khi phụ thuộc Config Data

Nếu yêu cầu “chạy sau khi Boot đã đọc `application.yaml`”, số nguyên `100` có thể không diễn đạt ý định rõ ràng. Spring Boot có processor nội bộ:

```java
org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor
```

Class này triển khai `Ordered` và cung cấp hằng số:

```java
ConfigDataEnvironmentPostProcessor.ORDER
```

Vì vậy có thể viết:

```java
@Override
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER + 1;
}
```

để biểu đạt processor tùy chỉnh chạy sau processor Config Data trong cơ chế sắp xếp `EnvironmentPostProcessor`.

Nếu muốn chạy **trước** Config Data:

```java
@Override
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER - 1;
}
```

Chọn trước/sau phải dựa trên dữ liệu mà processor cần. Không có quy tắc “processor tùy chỉnh luôn phải chạy trước để có ưu tiên cao”.

### 6.2. Chạy trước Config Data có nghĩa gì?

Tại thời điểm đó, processor không nên giả định `application.yaml` và `application-{profile}.yaml` đã được tải bởi Config Data. Nó có thể làm việc với những nguồn rất sớm, ví dụ system properties, environment variables hoặc các nguồn đã tồn tại khi được gọi.

Nếu một processor cần lấy `demo.region` đã khai báo **chỉ trong `application.yaml`**, hãy chọn order sau Config Data để có thể đọc nó.

Nếu mục tiêu là cung cấp một thuộc tính Boot cần đọc khi **khởi tạo Config Data**, phải chạy đủ sớm và hiểu thật kỹ tính tương thích với `spring.config.*`; việc tùy biến các khóa bootstrap có thể thay đổi toàn bộ cách nạp cấu hình.

### 6.3. Không hardcode giá trị số bên trong Boot nếu có hằng số

Tránh viết:

```java
return -2147483638;
```

chỉ vì hiện tại nó trùng một order nội bộ mà bạn đọc được từ code của một phiên bản. Dùng:

```java
return ConfigDataEnvironmentPostProcessor.ORDER + 1;
```

diễn đạt ý định rõ hơn và giảm phụ thuộc vào một con số chi tiết triển khai.

## 7. Điều phối bằng `@Order`

JavaDoc cũng cho phép dùng:

```java
import org.springframework.core.annotation.Order;
```

Ví dụ:

```java
@Order(200)
public final class BetaEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        // ...
    }
}
```

Tương tự, giá trị nhỏ hơn được sắp trước.

Lựa chọn giữa hai cách:

| Cách | Ưu điểm |
| --- | --- |
| `implements Ordered` | `getOrder()` có thể diễn đạt order bằng mã Java; dễ tham chiếu hằng số của Boot |
| `@Order(...)` | Cú pháp ngắn gọn khi order là hằng số compile-time phù hợp |
| Không có order rõ ràng | Ít code, nhưng không nên dùng khi có phụ thuộc về thứ tự |

Trong cùng một processor, hãy chọn **một quy ước chính** để dễ hiểu. Nếu `Ordered` và `@Order` cùng xuất hiện với thông tin mâu thuẫn, người đọc sẽ phải biết chi tiết comparator được dùng để hiểu cái nào được ưu tiên.

### Trường hợp hai processor có cùng order

Không nên dựa vào việc file `spring.factories` liệt kê A trước B hoặc thứ tự classpath ổn định để suy ra A chắc chắn chạy trước B nếu chúng cùng order.

Nếu B phụ thuộc dữ liệu của A, chỉ định **order khác nhau và rõ ràng**, ví dụ:

```text
A = ConfigDataEnvironmentPostProcessor.ORDER + 1
B = ConfigDataEnvironmentPostProcessor.ORDER + 20
```

Order bằng nhau không phải hợp đồng phụ thuộc đáng tin cậy giữa các processor.

## 8. Ví dụ hoàn chỉnh — hai processor có quan hệ thứ tự

Ví dụ ứng dụng cần:

- `demo.region` lấy từ `application.properties`.
- `demo.mode` có thể do file hoặc CLI cung cấp.
- Fallback `demo.mode=development` và `demo.retry-count=2` nếu chưa có nguồn khác.
- `demo.instance-label` là chuỗi dẫn xuất `region/mode`.
- Nếu người dùng đã cấu hình `demo.instance-label`, giá trị đó phải có ưu tiên hơn giá trị dẫn xuất.

Thiết kế:

```text
ConfigDataEnvironmentPostProcessor
     |
     v
DefaultsEnvironmentPostProcessor
  ORDER = ConfigDataEnvironmentPostProcessor.ORDER + 1
  addLast(demo.mode, demo.retry-count)
     |
     v
DerivedEnvironmentPostProcessor
  ORDER = ConfigDataEnvironmentPostProcessor.ORDER + 20
  đọc demo.region, demo.mode
  addLast(demo.instance-label)
     |
     v
Các bean ứng dụng sử dụng Environment đã chuẩn bị
```

Đây là ví dụ **có chủ đích dùng `addLast`** để không vô tình ghi đè các giá trị mà người triển khai đã cung cấp.

### 8.1. Cấu trúc thư mục

```text
src/
  main/
    java/
      example/
        environment/
          EnvironmentDemoApplication.java
          DefaultsEnvironmentPostProcessor.java
          DerivedEnvironmentPostProcessor.java
    resources/
      application.properties
      META-INF/
        spring.factories
```

### 8.2. Processor A: nạp fallback

Tạo:

`src/main/java/example/environment/DefaultsEnvironmentPostProcessor.java`

```java
package example.environment;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class DefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    public static final String SOURCE_NAME = "demo-epp-defaults";

    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 1;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        MutablePropertySources sources = environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            return;
        }

        Map<String, Object> defaults = Map.of(
                "demo.mode", "development",
                "demo.retry-count", "2"
        );

        sources.addLast(new MapPropertySource(SOURCE_NAME, defaults));
    }
}
```

Giải thích:

- Processor thực thi sau Config Data theo order được khai báo.
- Nguồn có tên cố định `demo-epp-defaults`, thuận tiện để xác định khi chẩn đoán.
- `MapPropertySource` biến các cặp key/value thành nguồn cấu hình.
- `addLast` ưu tiên những nguồn đã tồn tại trước fallback.
- Guard `contains(SOURCE_NAME)` giảm nguy cơ thêm cùng một nguồn hai lần nếu processor bị gọi lại trong bài test hoặc một ngữ cảnh đặc biệt.
- Fallback không phải một `@ConfigurationProperties` bean; bean có thể liên kết giá trị từ nguồn vừa thêm khi khởi tạo sau đó.

Dữ liệu trong `Map` là giá trị ví dụ không nhạy cảm. Không đưa token, mật khẩu hay private key trực tiếp vào mã nguồn.

### 8.3. Processor B: tạo giá trị dẫn xuất

Tạo:

`src/main/java/example/environment/DerivedEnvironmentPostProcessor.java`

```java
package example.environment;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.util.StringUtils;

public final class DerivedEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    public static final String SOURCE_NAME = "demo-epp-derived";

    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 20;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        MutablePropertySources sources = environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            return;
        }

        String region = environment.getProperty("demo.region");

        if (!StringUtils.hasText(region)) {
            return;
        }

        String mode = environment.getProperty(
                "demo.mode", "development");

        String label = region + "/" + mode;

        sources.addLast(new MapPropertySource(
                SOURCE_NAME,
                Map.of("demo.instance-label", label)
        ));
    }
}
```

Phân tích:

1. `DerivedEnvironmentPostProcessor` chạy **sau** `DefaultsEnvironmentPostProcessor`.
2. Nó đọc `demo.region`, có thể đến từ `application.properties`, profile, CLI hoặc nguồn khác.
3. Nó đọc `demo.mode`; nếu file không khai báo mode, nó có thể thấy fallback của processor A.
4. Nó tạo chuỗi `region/mode`.
5. `addLast` đặt giá trị dẫn xuất ở mức fallback. Người triển khai vẫn có thể khai báo trực tiếp `demo.instance-label` ở một nguồn ưu tiên cao hơn.

Nếu `demo.region` không có hoặc rỗng, ví dụ này **không tạo** `demo.instance-label`. Đó là quyết định minh họa; ứng dụng thật phải quyết định thuộc tính nào bắt buộc và validation nên xử lý trường hợp thiếu như thế nào.

### 8.4. Đăng ký trong `spring.factories`

Tạo file **chính xác**:

`src/main/resources/META-INF/spring.factories`

Nội dung:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.DefaultsEnvironmentPostProcessor,example.environment.DerivedEnvironmentPostProcessor
```

Chú ý:

- Key là `org.springframework.boot.env.EnvironmentPostProcessor`.
- Tên class gồm package đầy đủ `example.environment`.
- Không thêm ký tự `@Component`.
- Không ghi vào `AutoConfiguration.imports`.
- Không dùng ký tự phân cách tùy ý như dấu `;` nếu định dạng factory yêu cầu danh sách ngăn bằng dấu phẩy.
- Thứ tự khai báo trong dòng chỉ là danh sách đăng ký; **thứ tự chạy được quyết định bởi `getOrder()`**.

### 8.5. File cấu hình nguồn

Tạo:

`src/main/resources/application.properties`

```properties
spring.application.name=epp-order-demo

demo.region=ap-southeast-1
demo.mode=production
```

Ở đây `demo.retry-count` và `demo.instance-label` không xuất hiện trong file:

- `demo.retry-count` sẽ nhận fallback `2`.
- `demo.instance-label` có thể được tạo bởi processor B.
- `demo.mode` lấy từ file là `production`, thắng fallback `development` vì nguồn fallback được `addLast`.

### 8.6. Ứng dụng đọc kết quả

Tạo:

`src/main/java/example/environment/EnvironmentDemoApplication.java`

```java
package example.environment;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class EnvironmentDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                EnvironmentDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner display(Environment environment) {
        return args -> {
            System.out.println("demo.region="
                    + environment.getProperty("demo.region"));

            System.out.println("demo.mode="
                    + environment.getProperty("demo.mode"));

            System.out.println("demo.retry-count="
                    + environment.getProperty("demo.retry-count"));

            System.out.println("demo.instance-label="
                    + environment.getProperty("demo.instance-label"));
        };
    }
}
```

`ApplicationRunner` chạy sau khi context đã khởi tạo. Vì vậy nó phù hợp để **quan sát đầu ra**, không phải nơi đăng ký hoặc chạy `EnvironmentPostProcessor`.

### 8.7. Kết quả dự kiến

Sau khi dùng Maven wrapper:

```bash
./mvnw spring-boot:run
```

hoặc JAR đã được đóng gói:

```bash
java -jar app.jar
```

(cần thay `app.jar` bằng tên file thật), các dòng dữ liệu minh họa là:

```text
demo.region=ap-southeast-1
demo.mode=production
demo.retry-count=2
demo.instance-label=ap-southeast-1/production
```

Dữ liệu được tạo ra như sau:

| Key | Nguồn có hiệu lực trong ví dụ |
| --- | --- |
| `demo.region` | `application.properties` |
| `demo.mode` | `application.properties`, thắng fallback |
| `demo.retry-count` | `demo-epp-defaults` |
| `demo.instance-label` | `demo-epp-derived` |

Nếu không thấy những dòng này, hãy kiểm tra `spring.factories`, classpath, package, build output và các nguồn cấu hình có ưu tiên cao hơn.

## 9. Thực nghiệm: thay đổi từng nguồn để hiểu thứ tự

### Thử A: CLI ghi đè `demo.mode`

Chạy:

```bash
java -jar app.jar --demo.mode=canary
```

Nếu không có nguồn ưu tiên đặc biệt khác:

```text
demo.region=ap-southeast-1
demo.mode=canary
demo.retry-count=2
demo.instance-label=ap-southeast-1/canary
```

Vì processor B chạy sau Config Data và đọc `Environment` lúc đó, nó có thể thấy giá trị CLI `canary`.

### Thử B: CLI ghi đè chính khóa dẫn xuất

```bash
java -jar app.jar --demo.instance-label=operator-defined
```

Kết quả giá trị cuối:

```text
demo.instance-label=operator-defined
```

Processor B vẫn có thể tạo một fallback `ap-southeast-1/production`, nhưng `addLast` giữ cho cấu hình của người vận hành được ưu tiên.

### Thử C: bỏ `demo.mode` khỏi file

Nếu `application.properties` chỉ còn:

```properties
demo.region=ap-southeast-1
```

thì:

```text
demo.mode=development
demo.retry-count=2
demo.instance-label=ap-southeast-1/development
```

Fallback từ processor A có hiệu lực trước khi processor B đọc `demo.mode`.

### Thử D: bỏ `demo.region`

Nếu không còn nguồn nào cung cấp `demo.region`, processor B không tạo `demo.instance-label`. Kết quả có thể:

```text
demo.region=null
demo.instance-label=null
```

Từ `"null"` trong output là do `String` concatenation của Java với kết quả `null`; nó không có nghĩa `Environment` đã lưu chuỗi `"null"` làm property.

Trong dự án thật, nếu `demo.region` là bắt buộc, nên dùng `@ConfigurationProperties` và validation để fail fast hoặc đưa ra thông báo có ý nghĩa, thay vì chỉ in null.

## 10. Thay `addLast` bằng `addFirst` thay đổi gì?

Trong processor A:

```java
sources.addLast(new MapPropertySource(...));
```

có nghĩa nguồn fallback được thêm ở cuối thứ tự ưu tiên hiện có.

Nếu thay thành:

```java
sources.addFirst(new MapPropertySource(...));
```

nguồn `demo-epp-defaults` có thể thắng những giá trị cùng key ở các nguồn đã tồn tại, kể cả `application.properties` hoặc CLI tại thời điểm thêm.

Ví dụ fallback:

```text
demo.mode=development
```

mà dùng `addFirst` thì người vận hành có thể thấy `demo.mode=development` dù họ đã khai báo `demo.mode=production` trong file.

Điều này thường **không phù hợp cho default**. Nhưng `addFirst` có thể hữu ích nếu có một chính sách ép buộc giá trị, trong trường hợp được thiết kế và giải thích rõ.

### 10.1. `addBefore` và `addAfter`

`MutablePropertySources` còn hỗ trợ:

```java
sources.addBefore(existingSourceName, customSource);
sources.addAfter(existingSourceName, customSource);
```

Hai phương thức này giúp đặt nguồn theo vị trí tương đối với một nguồn **đã tồn tại**.

Điều kiện: `existingSourceName` phải có mặt tại thời điểm thực thi. Tên các nguồn do framework thêm có thể thay đổi theo phiên bản, profile và cách nạp. Không hardcode một tên nội bộ dễ thay đổi nếu chưa có lý do và kiểm thử phù hợp.

### 10.2. `replace` và `remove`

Có thể thao tác:

```java
sources.replace(name, newSource);
sources.remove(name);
```

Nhưng hai thao tác này mang tính xâm lấn. Thay/xóa một nguồn từ Boot hoặc thư viện khác có thể làm thay đổi rộng hành vi cấu hình. Đối với bài học, **thêm nguồn mang tên riêng** dễ an toàn và dễ chẩn đoán hơn.

### 10.3. Không ghép ba khái niệm làm một

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Order của processor | `getOrder() = ... + 20` | Processor chạy sau processor có order nhỏ hơn |
| Vị trí nguồn | `sources.addLast(...)` | Giá trị của nguồn mới làm fallback tại thời điểm thêm |
| Nguồn thắng cuối | `environment.getProperty("demo.mode")` | Kết quả sau khi xét toàn bộ PropertySource hiện có |

Một processor chạy muộn chưa chắc ghi đè được nguồn cũ. Ngược lại, một processor chạy sớm thêm nguồn bằng `addFirst` có thể ảnh hưởng mạnh tới các processor chạy sau.

## 11. Vì sao order so với `ConfigDataEnvironmentPostProcessor` đặc biệt quan trọng?

`ConfigDataEnvironmentPostProcessor` là thành phần Boot chịu trách nhiệm nạp/apply Config Data vào Spring `Environment`. Những nguồn này gồm `application.properties`, YAML, tài liệu profile-specific và các import config data được hỗ trợ.

Nếu processor của bạn cần:

```java
String region = environment.getProperty("demo.region");
```

mà `demo.region` **chỉ có trong `application.properties`**, bạn muốn Config Data được áp dụng trước.

Đó là lý do ví dụ dùng:

```java
ConfigDataEnvironmentPostProcessor.ORDER + 1
```

và:

```java
ConfigDataEnvironmentPostProcessor.ORDER + 20
```

### 11.1. Chạy trước Config Data

Một processor có order:

```java
ConfigDataEnvironmentPostProcessor.ORDER - 1
```

thường được gọi trước processor Config Data, nên không thể mặc định đã có cấu hình từ `application.yaml`.

Nếu bạn phải cung cấp một giá trị mà Config Data cần đọc từ rất sớm, có thể thiết kế processor trước Config Data, nhưng cần hiểu chính xác những nguồn đã sẵn có và các quy tắc Boot áp dụng.

Ví dụ những thuộc tính như:

```text
spring.config.name
spring.config.location
spring.config.additional-location
```

được dùng sớm để quyết định vị trí nạp cấu hình. Thay đổi những giá trị này bằng processor cần thận trọng để tránh vòng phụ thuộc và hành vi startup không nhất quán.

### 11.2. Chạy sau Config Data

Processor chạy sau Config Data có thể:

- Đọc những giá trị đã nạp từ `application.properties`/YAML.
- Đọc active profiles đã được xác định trong quá trình xử lý config data.
- Tạo fallback cho các khóa thuộc nghiệp vụ của ứng dụng.
- Tạo giá trị dẫn xuất từ nguồn có hiệu lực.

Nhưng nếu bạn thêm một property mà Boot **đã tiêu thụ từ trước để quyết định config data**, đừng mặc định Boot sẽ quay lại và thực hiện toàn bộ quá trình load từ đầu. Một `PropertySource` bổ sung muộn không có nghĩa cơ chế bootstrap được lặp lại.

### 11.3. Tránh “tự gọi lại” Config Data processor

Không nên tùy tiện tạo:

```java
new ConfigDataEnvironmentPostProcessor(...)
```

hoặc gọi `applyTo` lặp lại từ processor của bạn chỉ để chắc chắn config data đã tải. Hãy dùng **order** để điều phối và để Spring Boot quản lý lifecycle chuẩn.

## 12. Order giữa các processor của các thư viện

Trong một ứng dụng lớn, nhiều dependency có thể có EPP:

```text
spring-boot core
internal-security-starter
internal-observability-starter
application-specific extension
```

Giả sử:

- A thêm fallback mặc định.
- B giải mã một nguồn có format riêng.
- C tạo property dẫn xuất phụ thuộc kết quả của B.

Thiết kế cần làm rõ:

```text
B phải chạy trước C
A có cần chạy trước B không?
C đọc key nào?
B thêm source ở đầu hay cuối?
```

Một phương án:

```java
public final class SecurityEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {
    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 5;
    }
}
```

```java
public final class DerivedEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {
    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 10;
    }
}
```

Đây là **ví dụ điều phối cục bộ**. Nếu nhiều team cùng dùng khoảng order đó, họ nên thống nhất quy ước trong tài liệu của thư viện, không để từng module tùy chọn số ngẫu nhiên.

Khi một yêu cầu phụ thuộc phức tạp không thể biểu diễn rõ bằng thứ tự đơn, cân nhắc hợp nhất các bước phụ thuộc vào một processor có các hàm nội bộ rõ ràng, thay vì tạo một chuỗi hàng chục EPP được ghép bằng số.

## 13. Không nhầm `@Order` với thứ tự tên class trong `spring.factories`

Một file:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.DerivedEnvironmentPostProcessor,example.environment.DefaultsEnvironmentPostProcessor
```

liệt kê B trước A.

Nếu `getOrder()` của A nhỏ hơn B, hệ thống EPP vẫn sử dụng thông tin order để sắp xếp theo hợp đồng. Do đó không nên sửa danh sách class chỉ để cố điều khiển thứ tự chạy.

Để diễn đạt yêu cầu:

```text
A chạy trước B
```

hãy dùng:

```text
A.getOrder() < B.getOrder()
```

trong khi `getOrder()` của cả hai vẫn được chọn sao cho phù hợp vị trí tương đối với Config Data.

Nếu các order bằng nhau, tránh dựa vào thứ tự classpath hoặc cách factory loader liệt kê class làm cam kết lâu dài.

## 14. Logging sớm: tại sao `Logger` bình thường có thể chưa như mong đợi?

`EnvironmentPostProcessor` chạy trước khi toàn bộ ứng dụng và logging configuration hoàn thành. Tài liệu API Spring Boot 3.3 cho phép processor nhận `DeferredLogFactory` qua constructor.

Ví dụ:

```java
package example.environment;

import org.apache.commons.logging.Log;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.boot.logging.DeferredLogFactory;
import org.springframework.core.env.ConfigurableEnvironment;

public final class LoggingEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private final Log log;

    public LoggingEnvironmentPostProcessor(
            DeferredLogFactory logFactory
    ) {
        this.log = logFactory.getLog(getClass());
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        this.log.info("Preparing custom environment properties");
    }
}
```

Đây là ví dụ độc lập về **logging**, không phải class thứ ba cần thêm vào `spring.factories` của bài chạy hai processor trừ khi bạn chủ ý đăng ký nó.

Lợi ích: log có thể được hoãn phát cho đến khi phần cấu hình logging của ứng dụng đã sẵn sàng hơn.

**Không log dữ liệu bí mật** hay xuất toàn bộ `Environment`. Một số property source có thể chứa mật khẩu, token hoặc connection string. Cả deferred log cũng không làm nội dung nhạy cảm tự trở nên an toàn.

### 14.1. Vì sao không inject logger service?

Một service logging riêng của ứng dụng có thể chưa được tạo ở giai đoạn EPP. Dùng cơ chế logging sớm được Boot hỗ trợ hoặc phát log một cách cẩn trọng; đừng kéo cả dependency graph của Spring context vào constructor EPP.

## 15. `ConfigurableBootstrapContext` có vai trò gì?

Spring Boot 3.3 cho phép EPP nhận `ConfigurableBootstrapContext` trong constructor. Đây là vùng cộng tác sớm, dành cho những thành phần cần chia sẻ đối tượng hoặc kết quả được tạo trước khi application context hoàn chỉnh.

Ý tưởng:

```text
Giai đoạn bootstrap
    |
    +-- Processor tạo một đối tượng cần chia sẻ
    +-- BootstrapContext có thể giữ đối tượng
    |
    v
Giai đoạn chuẩn bị ApplicationContext
    |
    +-- Các thành phần hỗ trợ có thể sử dụng thông tin đã đăng ký
```

Đừng hiểu bootstrap context là một `ApplicationContext` đầy đủ có thể tìm tùy ý tất cả bean. Nó có API và mục tiêu riêng.

Với bài thêm `MapPropertySource`, **không cần** `ConfigurableBootstrapContext`. Khi cần tải dữ liệu có chi phí cao hoặc chia sẻ dữ liệu giữa các bước startup, hãy đọc tài liệu và thiết kế rõ lifecycle thay vì tạo global mutable singleton.

## 16. Idempotence: tránh thao tác không mong muốn khi chạy lại

Trong ví dụ, mỗi processor có:

```java
if (sources.contains(SOURCE_NAME)) {
    return;
}
```

Điều này có ích khi:

- Unit test gọi processor nhiều lần.
- Một môi trường thử nghiệm chuẩn bị context nhiều lần và muốn giữ nguyên một nguồn.
- Một extension được chạy lại một cách có chủ đích.

Tuy nhiên, guard “đã có thì bỏ qua” không phù hợp với mọi yêu cầu. Nếu quy tắc đúng là **cập nhật** giá trị từ môi trường mới, bạn có thể phải tính lại và thay source bằng một cơ chế được kiểm soát.

Đừng dùng:

```java
sources.addFirst(new MapPropertySource("same-name", map));
```

nhiều lần rồi mặc định mọi cấu trúc nguồn vẫn ổn định. `MutablePropertySources` quản lý nguồn theo tên, và thêm trùng tên có thể làm thay đổi vị trí/thứ tự ngoài ý định.

Tốt hơn:

1. Chọn một tên nguồn ổn định, có prefix riêng.
2. Xác định chính sách **add once**, **replace**, hay **merge** ngay từ thiết kế.
3. Kiểm tra sự hiện diện của nguồn trước thao tác.
4. Không xóa/thay nguồn của module khác nếu không có hợp đồng.
5. Kiểm tra bằng test hai lần gọi.

## 17. Không làm EPP trở thành nơi gọi mạng hoặc cơ sở dữ liệu

Một cách làm dễ gây lỗi:

```java
public MyEnvironmentPostProcessor(RemoteSettingsClient client) {
    this.client = client;
}
```

Không nên kỳ vọng `RemoteSettingsClient` đã là Spring bean sẵn sàng. Ngoài ra, gọi mạng ở giai đoạn bootstrap có những rủi ro:

- Không có timeout, ứng dụng có thể treo khi khởi động.
- Một endpoint tạm thời lỗi làm toàn bộ app không lên.
- Logging/metrics/tracing chưa hoàn thiện.
- Vòng phụ thuộc giữa config và client dùng config.
- Thông tin xác thực có thể chưa được nạp đầy đủ.
- Kiểm thử tích hợp phụ thuộc môi trường bên ngoài.

Nếu nhiệm vụ là nạp một **nguồn cấu hình remote chuẩn**, Spring Boot có hệ thống **Config Data API**, trong đó có `ConfigDataLocationResolver` và `ConfigDataLoader` cho các loại location riêng.

Nên cân nhắc API chuyên biệt đó khi cần tích hợp một location như `custom://...` vào `spring.config.import`, thay vì cố mô phỏng mọi cơ chế profile, import, optional và precedence trong một EPP.

EPP phù hợp nhất khi thay đổi môi trường theo quy tắc rõ ràng, đủ sớm, ít phụ thuộc và có hành vi khởi động xác định.

## 18. Thêm file YAML tùy chỉnh bằng EPP

Ngoài `MapPropertySource`, một EPP có thể đọc một file rồi thêm `PropertySource`.

Ví dụ tư duy:

```text
classpath:/feature-defaults.yaml
         |
         v
YamlPropertySourceLoader
         |
         v
PropertySource(s)
         |
         v
environment.getPropertySources().addLast(...)
```

Spring Boot có:

```java
org.springframework.boot.env.YamlPropertySourceLoader
```

cho trường hợp tải YAML từ `Resource`.

Một minh họa đọc file tùy chọn:

```java
package example.environment;

import java.io.IOException;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;

public final class FeatureDefaultsPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        var resource = new ClassPathResource("feature-defaults.yaml");

        if (!resource.exists()) {
            return;
        }

        try {
            List<PropertySource<?>> sources =
                    new YamlPropertySourceLoader()
                            .load("feature-defaults", resource);

            for (PropertySource<?> source : sources) {
                if (!environment.getPropertySources()
                        .contains(source.getName())) {
                    environment.getPropertySources().addLast(source);
                }
            }
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot load feature defaults", ex);
        }
    }
}
```

Đoạn này là **ví dụ tùy chọn**, không phải thành phần của demo hai processor đã đăng ký ở mục 8.

Các chú ý:

- Loader có thể trả **nhiều `PropertySource`**, chẳng hạn YAML nhiều tài liệu; không nên mặc định chỉ có phần tử đầu tiên.
- `addLast` chọn ưu tiên thấp hơn các nguồn hiện có.
- Cần làm rõ khi thiếu file là bỏ qua hay fail-fast.
- Nếu file dùng profile/activation/import phức tạp, EPP đơn giản không tự tái tạo toàn bộ hành vi Config Data.
- Với các tệp `.properties`/YAML cấu hình chuẩn, hãy ưu tiên `spring.config.import` hoặc quy tắc nạp cấu hình mặc định của Spring Boot trước khi tự viết loader.

## 19. Kiểm tra PropertySource đã được thêm chưa

Trong một bean chạy sau khởi động:

```java
@Bean
ApplicationRunner inspect(ConfigurableEnvironment environment) {
    return args -> {
        System.out.println(
                "defaults registered: "
                + environment.getPropertySources()
                        .contains("demo-epp-defaults"));

        System.out.println(
                "derived registered: "
                + environment.getPropertySources()
                        .contains("demo-epp-derived"));
    };
}
```

Phương thức này đặt trong lớp `@Configuration` hoặc `@SpringBootApplication`, không phải một tệp Java độc lập.

Nó giúp phân biệt:

```text
Processor không được đăng ký/chạy
```

với:

```text
Processor chạy nhưng key bị nguồn ưu tiên hơn ghi đè
```

Nếu hai nguồn được thêm nhưng `demo.mode` không như bạn mong đợi, hãy xem **vị trí nguồn** và PropertySource precedence, đừng kết luận EPP chưa chạy.

### 19.1. Quan sát thứ tự nguồn một cách an toàn

Có thể liệt kê **tên nguồn** trong môi trường phát triển:

```java
for (PropertySource<?> source :
        environment.getPropertySources()) {
    System.out.println(source.getName());
}
```

Đoạn này chỉ in tên, không in giá trị. Không dump toàn bộ `source.getSource()` lên log vì có thể chứa secret.

Tên PropertySource do framework thêm có thể phức tạp và thay đổi theo phiên bản/định dạng/config data. Không xây hợp đồng sản phẩm dựa trên một tên nội bộ chưa được tài liệu đảm bảo.

## 20. Kiểm thử processor bằng môi trường giả lập

Cơ chế gọi:

```java
postProcessEnvironment(environment, application)
```

là API Java bình thường, nên có thể kiểm thử một processor mà không khởi động toàn bộ Spring Boot.

Ví dụ JUnit 5:

```java
package example.environment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

class EnvironmentProcessorsTest {

    @Test
    void defaultsAndDerivedSourcesWork() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource("test-input", Map.of(
                        "demo.region", "eu-west-1",
                        "demo.mode", "qa"
                )));

        SpringApplication application =
                new SpringApplication(Object.class);

        var defaults = new DefaultsEnvironmentPostProcessor();
        var derived = new DerivedEnvironmentPostProcessor();

        assertTrue(defaults.getOrder() < derived.getOrder());

        defaults.postProcessEnvironment(environment, application);
        derived.postProcessEnvironment(environment, application);

        assertEquals("eu-west-1",
                environment.getProperty("demo.region"));
        assertEquals("qa",
                environment.getProperty("demo.mode"));
        assertEquals("2",
                environment.getProperty("demo.retry-count"));
        assertEquals("eu-west-1/qa",
                environment.getProperty("demo.instance-label"));
    }

    @Test
    void explicitlyConfiguredLabelWins() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource("test-input", Map.of(
                        "demo.region", "eu-west-1",
                        "demo.mode", "qa",
                        "demo.instance-label", "operator-defined"
                )));

        SpringApplication application =
                new SpringApplication(Object.class);

        new DefaultsEnvironmentPostProcessor()
                .postProcessEnvironment(environment, application);
        new DerivedEnvironmentPostProcessor()
                .postProcessEnvironment(environment, application);

        assertEquals("operator-defined",
                environment.getProperty("demo.instance-label"));
    }
}
```

Để dùng `MockEnvironment` và JUnit 5, project cần dependency test phù hợp, ví dụ:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Hai test trên chứng minh **logic thêm nguồn và giá trị có hiệu lực** trong một môi trường do test dựng thủ công.

Chúng **chưa chứng minh** file `META-INF/spring.factories` được đóng gói và framework đã discovery hai processor trong ứng dụng thật.

## 21. Kiểm thử tích hợp: xác minh `spring.factories`

Để xác minh discovery, cần khởi động ứng dụng Spring Boot thật trong test hoặc chạy artifact được đóng gói.

Ví dụ JUnit 5 với Spring Boot:

```java
package example.environment;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

class RegisteredEnvironmentProcessorsTest {

    @Test
    void registeredProcessorsApplyWhenBootStarts() {
        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(
                        EnvironmentDemoApplication.class)
                        .web(WebApplicationType.NONE)
                        .run("--demo.region=eu-north-1",
                             "--demo.mode=integration")) {

            assertEquals("eu-north-1/integration",
                    context.getEnvironment()
                            .getProperty("demo.instance-label"));

            assertEquals("2",
                    context.getEnvironment()
                            .getProperty("demo.retry-count"));
        }
    }
}
```

Test dùng `SpringApplicationBuilder` khởi tạo lifecycle Spring Boot, do đó có thể phát hiện hai processor qua `spring.factories` khi cấu hình classpath đúng.

Tại sao test này khác unit test?

- Unit test gọi EPP trực tiếp, nên vẫn có thể pass khi quên `spring.factories`.
- Test tích hợp cần Boot **tự tìm class** qua metadata trong resources.
- Test tích hợp cũng xác nhận thứ tự liên quan Config Data và các giá trị trong context thực.

Nếu test tích hợp thất bại nhưng unit test qua, ưu tiên kiểm tra:

1. `src/main/resources/META-INF/spring.factories` có được đưa vào test classpath không?
2. Key giao diện có đúng không?
3. Class names đầy đủ, không sai package, không sai chính tả?
4. Build có sao chép resources không?
5. Có lỗi constructor/lifecycle sớm không?
6. `getOrder()` có đi đúng sau Config Data không?
7. Có nguồn cấu hình khác ghi đè giá trị dự kiến không?

### 21.1. Vì sao `ApplicationContextRunner` chưa chắc đủ cho test discovery?

`ApplicationContextRunner` rất hữu ích để test auto-configuration và bean definitions. Nhưng việc tạo một context thông thường qua runner **không đồng nghĩa** với chạy toàn bộ chuỗi `SpringApplication` events đã kích hoạt mọi `EnvironmentPostProcessor` qua `spring.factories`.

Nếu cần kiểm tra **discovery EPP thật**, hãy dùng một test có Spring Boot startup lifecycle tương ứng thay vì chỉ tạo `ApplicationContextRunner` mà không tự gọi EPP.

## 22. Thứ tự listener và thứ tự EPP không phải một

Spring Boot có `EnvironmentPostProcessorApplicationListener`, một listener tham gia giai đoạn startup và kích hoạt các implementation EPP được đăng ký.

Điều cần phân biệt:

- **Order của listener** quyết định listener này được gọi khi nào so với các application listener khác.
- **Order của EPP** quyết định những EnvironmentPostProcessor bên trong được thực thi theo thứ tự nào.

Hai cấp order khác nhau.

Nếu một đội thêm custom `ApplicationListener<ApplicationEnvironmentPreparedEvent>` và một đội khác thêm EPP, đừng chỉ so sánh số order của hai class rồi kết luận chắc chắn thứ tự như khi cả hai là EPP. Cần xem lifecycle và listener ordering đúng tầng.

Trong hầu hết tình huống chỉ cần tùy biến `Environment` bằng EPP, hãy dùng `Ordered` hoặc `@Order` trực tiếp trên EPP thay vì tự thay đổi thứ tự listener nội bộ của Boot.

## 23. Những lỗi đăng ký thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| EPP không được gọi | Chưa có `spring.factories` | Tạo `src/main/resources/META-INF/spring.factories` |
| Có file nhưng EPP không chạy | Key sai tên package | Dùng `org.springframework.boot.env.EnvironmentPostProcessor` |
| EPP bị nhầm vào `AutoConfiguration.imports` | Nhầm extension SPI | Đưa EPP vào `spring.factories` |
| Class được `@Component` nhưng không chạy ở thời điểm mong muốn | Component scan muộn và không phải discovery EPP | Dùng `spring.factories` |
| `ClassNotFoundException` | Giá trị trong factories không trùng package/class | Sửa fully-qualified class name |
| Constructor không khởi tạo được | Mong DI bean nghiệp vụ hoặc constructor không được factory hỗ trợ | Dùng no-arg hoặc constructor theo API Boot |
| B đọc key chưa có | B chạy trước A hoặc trước Config Data | Đặt `getOrder()` phù hợp |
| CLI không ghi đè được default | Custom source được `addFirst` | Dùng `addLast` nếu chỉ muốn fallback |
| Ghi log rất sớm không như kỳ vọng | Logging chưa cấu hình hoàn chỉnh | Xem `DeferredLogFactory` |
| Chạy test trực tiếp qua EPP nhưng app thật không có giá trị | Test chưa kiểm tra discovery qua factories | Thêm startup integration test |
| Không thấy file sau build | Resources không được copy/đóng gói | Kiểm tra `target/classes/META-INF` và JAR |
| Có nguồn nhưng giá trị khác | Nguồn khác ưu tiên cao hoặc giá trị bị tính từ nguồn khác | Kiểm tra `PropertySource` order và config data |
| Boot vẫn dùng vị trí config cũ | Thuộc tính `spring.config.*` được đặt sau khi Boot đã dùng | Thiết kế processor chạy đủ sớm hoặc dùng CLI/env |
| Processor bị gọi lại gây lỗi | Chưa có chính sách idempotence | Guard source name hoặc replace có chủ đích |
| Startup thất bại do network | EPP gọi dịch vụ ngoài quá sớm | Tách sang Config Data API hoặc tầng phù hợp |

## 24. Lỗi thiết kế: đoán order dựa trên `spring.factories`

Không nên viết:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=example.environment.FirstPostProcessor,example.environment.SecondPostProcessor
```

rồi suy ra:

```text
First luôn chạy trước Second vì đứng trước.
```

Thay vào đó:

```java
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER + 1;
}
```

và:

```java
public int getOrder() {
    return ConfigDataEnvironmentPostProcessor.ORDER + 20;
}
```

Thứ tự càng thấp chạy càng sớm. Nếu các processor có quan hệ phụ thuộc, phải đặt order tường minh.

Đừng dùng `Thread.sleep`, ghi file marker hay biến static để cố tạo thứ tự khởi động. Boot đã có một hợp đồng ordering cho EPP.

## 25. Lỗi thiết kế: tưởng chạy muộn nghĩa là ưu tiên cao

Giả sử B chạy sau A, nhưng cả hai đều `addLast`. Nếu A thêm `demo.timeout=5s` rồi B thêm `demo.timeout=30s` vào cuối, **không thể tự kết luận B thắng vì nó chạy sau**. Cùng key ở nguồn có thứ tự ưu tiên cao hơn vẫn là điều quyết định `Environment#getProperty`.

Ví dụ:

```text
PropertySources sau A:
  - applicationConfig
  - A

PropertySources sau B addLast:
  - applicationConfig
  - A
  - B
```

Trong cấu trúc minh họa này, nếu cả A và B đều khai báo `demo.timeout`, A ưu tiên hơn B, dù B chạy muộn.

Nếu muốn B ghi đè A nhưng không muốn vượt CLI, cần **chọn vị trí tương đối** có chủ đích bằng `addBefore` hoặc `addAfter`, và kiểm tra các nguồn hiện có. Không nên cứ dùng `addFirst` vì có thể ghi đè cả command-line properties.

## 26. Có nên dùng EPP cho mọi cấu hình tùy chỉnh?

Không. Hãy chọn API theo loại nhu cầu.

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Đọc file cấu hình chuẩn theo vị trí Boot tìm mặc định | `application.properties` / YAML |
| Import file cấu hình chuẩn khác | `spring.config.import` |
| Biến môi trường trong container/OS | Environment variable |
| Gom cấu hình có kiểu | `@ConfigurationProperties` |
| Chuyển chuỗi sang kiểu miền riêng | `Converter` + `@ConfigurationPropertiesBinding` |
| Bổ sung property source rất sớm | `EnvironmentPostProcessor` |
| Xử lý location config riêng như `custom:` | `ConfigDataLocationResolver` + `ConfigDataLoader` |
| Tùy biến bean/context sau khi có `ApplicationContext` | Initializer/bean extension thích hợp |
| Kiểm tra hành vi sau khi context khởi động | `ApplicationRunner`/`CommandLineRunner` |

Một giải pháp đơn giản bằng `spring.config.import=optional:file:./extra.properties` thường dễ bảo trì hơn viết một EPP chỉ để đọc thêm một `.properties` thông thường.

EPP có giá trị rõ ràng khi cần **cơ chế tùy biến Environment**, thứ tự xử lý sớm hoặc tích hợp một nguồn config theo logic riêng.

## 27. Quy tắc bảo mật và vận hành

Thao tác môi trường ảnh hưởng sâu vào ứng dụng. Một số thực hành cần thiết:

1. **Không hardcode secret trong map fallback.** Fallback có thể là tên môi trường, số retry, cờ tính năng; mật khẩu/token nên có nguồn an toàn hơn.
2. **Không in tất cả property values ra log.** Dễ lộ thông tin nhạy cảm.
3. **Không ghi đè CLI và biến môi trường một cách bất ngờ** bằng `addFirst` khi mục tiêu là default.
4. **Đặt tên PropertySource có prefix riêng** tránh trùng với nguồn từ Boot hoặc module khác.
5. **Giới hạn dependency** trong EPP, tránh repository và network nặng.
6. **Xác định chính sách thiếu file/giá trị**: bỏ qua, fallback hay fail-fast.
7. **Giải thích order** trong mã nguồn bằng tên hằng số Boot khi phụ thuộc Config Data.
8. **Có test tích hợp đăng ký factories** thay vì chỉ test thuật toán processor.
9. **Theo dõi log startup ở môi trường an toàn**, có xử lý nhạy cảm phù hợp.
10. **Không đặt cấu hình về vị trí config data muộn** rồi mong Boot nạp lại toàn bộ.
11. **Đừng tạo vòng phụ thuộc:** processor cần cấu hình, cấu hình lại cần nguồn do processor khác tạo nhưng processor đó chạy sau.
12. **Cân nhắc thay đổi khi nâng cấp Boot**, vì lifecycle và internal processors có thể thay đổi; kiểm tra lại hợp đồng của phiên bản đang dùng.

## 28. Bài tập tự kiểm tra

### Bài 1 — đường dẫn đăng ký

**Hỏi:** Một class `MyEnvironmentPostProcessor` đã `implements EnvironmentPostProcessor`. Để Spring Boot 3.3 tự tìm thấy, đặt tên nó ở đâu?

**Đáp án:** Trong `src/main/resources/META-INF/spring.factories`, với key đầy đủ `org.springframework.boot.env.EnvironmentPostProcessor`.

### Bài 2 — thứ tự chạy

**Hỏi:** Processor A `getOrder()=10`, B `getOrder()=20`. Processor nào được sắp trước?

**Đáp án:** A, vì số order nhỏ hơn có mức ưu tiên chạy cao hơn.

### Bài 3 — thứ tự trong factories

**Hỏi:** Nếu danh sách `spring.factories` ghi B trước A, nhưng A có order nhỏ hơn B, nên dựa vào thông tin nào để quyết định thứ tự?

**Đáp án:** Dựa vào hợp đồng `Ordered`/`@Order`, không dựa vào vị trí trong danh sách.

### Bài 4 — Config Data

**Hỏi:** Processor muốn đọc `demo.region` chỉ có trong `application.properties`. Nên chạy trước hay sau `ConfigDataEnvironmentPostProcessor`?

**Đáp án:** Sau, ví dụ dùng `ConfigDataEnvironmentPostProcessor.ORDER + 1`.

### Bài 5 — fallback

**Hỏi:** Muốn cung cấp `demo.retry-count=2` chỉ khi không có nguồn khác, chọn `addFirst` hay `addLast`?

**Đáp án:** Thường chọn `addLast` để có ưu tiên thấp hơn các nguồn hiện có.

### Bài 6 — hai trục thứ tự

**Hỏi:** B chạy sau A nhưng B dùng `addLast`. Có phải B luôn ghi đè các khóa của A không?

**Đáp án:** Không. Thứ tự chạy EPP và vị trí `PropertySource` là hai cơ chế khác nhau.

### Bài 7 — registration namespace

**Hỏi:** Có thể đặt EPP vào `AutoConfiguration.imports` thay vì `spring.factories` không?

**Đáp án:** Không phải cơ chế đăng ký EPP chuẩn của Spring Boot 3.3. `AutoConfiguration.imports` phục vụ auto-configuration.

### Bài 8 — bean dependency

**Hỏi:** Có nên tiêm một repository ứng dụng vào constructor của EPP rồi truy cập DB ngay ở startup không?

**Đáp án:** Không nên giả định repository đã sẵn sàng. EPP được khởi tạo rất sớm. Hãy thiết kế xử lý nhẹ, ít phụ thuộc và chọn extension API phù hợp.

### Bài 9 — lỗi bị ghi đè

**Hỏi:** `demo.mode` đã có trong CLI nhưng kết quả vẫn là fallback do EPP thêm. Nên kiểm tra gì?

**Đáp án:** Vị trí thêm nguồn (`addFirst`/`addLast`), thời điểm nguồn được thêm và PropertySource precedence. Không chỉ thay `getOrder()`.

### Bài 10 — logging

**Hỏi:** Vì sao EPP có thể cần `DeferredLogFactory`?

**Đáp án:** Vì xử lý môi trường diễn ra rất sớm, trước khi logging được cấu hình đầy đủ. Deferred logging phù hợp với vòng đời đó.

### Bài 11 — test unit và integration

**Hỏi:** Unit test gọi trực tiếp `postProcessEnvironment` thành công đã chứng minh factories đăng ký đúng chưa?

**Đáp án:** Chưa. Cần test startup có Spring Boot lifecycle thực hoặc kiểm tra artifact chứa `META-INF/spring.factories`.

### Bài 12 — source name

**Hỏi:** Vì sao nên dùng `SOURCE_NAME` cố định và kiểm tra `contains`?

**Đáp án:** Để định danh nguồn rõ ràng và tránh thêm lặp gây thay đổi vị trí nguồn ngoài ý định khi phương thức được gọi lại.

### Bài 13 — ghi đè config location

**Hỏi:** Processor chạy sau Config Data mới thêm `spring.config.location`. Boot có bắt buộc nạp lại config từ location mới không?

**Đáp án:** Không. Những property quyết định Config Data được dùng rất sớm. Nếu cần thay đổi, phải làm ở đúng giai đoạn hoặc cấp qua CLI/env/system properties theo hợp đồng.

### Bài 14 — chọn công cụ

**Hỏi:** Chỉ cần import một tệp `extra.properties` trên file system. Có nhất thiết viết EPP không?

**Đáp án:** Không. Thường có thể dùng `spring.config.import` hoặc cơ chế Config Data chuẩn, đơn giản hơn.

## 29. Checklist triển khai thực tế

- [ ] Xác định vì sao cần EPP thay vì Config Data/`@ConfigurationProperties`.
- [ ] Class triển khai đúng `org.springframework.boot.env.EnvironmentPostProcessor`.
- [ ] `postProcessEnvironment` chỉ làm việc hợp lệ ở giai đoạn bootstrap.
- [ ] Đã đăng ký đầy đủ class trong `META-INF/spring.factories`.
- [ ] Key trong factories đúng package `org.springframework.boot.env`.
- [ ] Đã quyết định EPP phải chạy trước hay sau Config Data.
- [ ] Đã dùng `Ordered` hoặc `@Order` với giá trị có chủ đích.
- [ ] Các processor phụ thuộc nhau có order khác nhau, rõ ràng.
- [ ] Không phụ thuộc thứ tự các tên class trong factories.
- [ ] Đã chọn `addFirst`, `addLast` hoặc vị trí tương đối phù hợp.
- [ ] Đã chọn tên PropertySource ổn định và tránh trùng.
- [ ] Có chính sách chạy lặp: add once, replace hay merge.
- [ ] Không kéo repository/HTTP client/bean nghiệp vụ vào EPP.
- [ ] Không in secret, không dump toàn bộ `Environment`.
- [ ] Nếu cần log sớm, cân nhắc `DeferredLogFactory`.
- [ ] Có unit test cho logic chỉnh sửa `Environment`.
- [ ] Có integration test xác minh discovery từ factories.
- [ ] Kiểm tra build output/JAR mang `META-INF/spring.factories`.
- [ ] Xác định rõ nguồn nào thắng khi CLI/env/file có cùng key.
- [ ] Không tự động đọc lại Config Data khi processor chạy muộn.
- [ ] Có tài liệu giải thích phạm vi và lý do tồn tại của EPP.

## 30. Tổng kết

**Đăng ký** và **thứ tự** là hai mảnh ghép riêng của `EnvironmentPostProcessor`:

```text
META-INF/spring.factories
      |
      v
Boot tìm các implementation EPP
      |
      v
Sắp xếp bằng Ordered / @Order
      |
      v
Chạy postProcessEnvironment theo order
      |
      v
Mỗi EPP thêm/sửa PropertySource
      |
      v
PropertySource precedence quyết định giá trị cuối
      |
      v
Environment được bean/condition/binder sử dụng
```

Ba nguyên tắc cần nhớ:

1. **Trong Spring Boot 3.3, EPP đăng ký bằng `META-INF/spring.factories`**, với key `org.springframework.boot.env.EnvironmentPostProcessor`.
2. **Dùng `Ordered` hoặc `@Order` để xác định thứ tự gọi**, ưu tiên nhỏ chạy trước; nếu cần nạp `application.properties` trước, dùng vị trí order **sau** `ConfigDataEnvironmentPostProcessor.ORDER`.
3. **Thứ tự gọi processor không bằng thứ tự ưu tiên giá trị**. `addFirst`, `addLast` và các thao tác lên `MutablePropertySources` mới quyết định vị trí của nguồn cấu hình.

Một EPP đáng tin cậy cần có mục đích rõ ràng, thứ tự hợp lý, thao tác PropertySource có chủ đích, ít phụ thuộc lúc bootstrap và kiểm thử đầy đủ. Khi nắm chắc những nguyên tắc đó, bạn có thể mở rộng `Environment` của Spring Boot mà không phá vỡ các quy tắc externalized configuration hiện có.

## Tài liệu tham khảo

- Spring Boot 3.3.13 Java API — `EnvironmentPostProcessor`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 3.3.13 Java API — `EnvironmentPostProcessorApplicationListener`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessorApplicationListener.html
- Spring Boot 3.3.13 Java API — `ConfigDataEnvironmentPostProcessor`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Customize the Environment or ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/3.3/how-to/application.html
- Spring Framework API — `MutablePropertySources`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/MutablePropertySources.html
