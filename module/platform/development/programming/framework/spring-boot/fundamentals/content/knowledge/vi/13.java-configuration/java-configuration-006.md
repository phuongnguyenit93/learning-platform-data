# ImportSelector, DeferredImportSelector và lựa chọn cấu hình có chương trình

Trong Spring, annotation `@Import` cho phép một lớp cấu hình đưa thêm cấu hình hoặc thành phần khác vào ApplicationContext. Khi cần quyết định lớp cấu hình nào được import dựa trên metadata hoặc môi trường chạy, Spring cung cấp hai extension point: `ImportSelector` và `DeferredImportSelector`.

Cả hai đều trả về tên đầy đủ của các lớp cần import. Điểm khác nhau chính là thời điểm Spring gọi selector trong quá trình phân tích cấu hình. `ImportSelector` được xử lý trong luồng phân tích cấu hình thông thường; `DeferredImportSelector` được xử lý sau khi Spring đã xử lý các cấu hình thông thường, nhờ đó có thể đưa ra lựa chọn sau khi có thêm thông tin về tập cấu hình được phát hiện.

## 1. Vai trò của @Import

Một lớp cấu hình có thể import trực tiếp lớp cấu hình khác:

~~~java
@Configuration
@Import({
        DatabaseConfiguration.class,
        MessagingConfiguration.class
})
public class ApplicationConfiguration {
}
~~~

Spring tiếp tục phân tích các lớp được import như những nguồn cấu hình. Chúng có thể khai báo `@Bean`, import cấu hình khác hoặc áp dụng các điều kiện cấu hình.

Cách import trực tiếp phù hợp khi tập cấu hình đã biết tại thời điểm viết code. Khi muốn lựa chọn theo annotation trên lớp import, theo thuộc tính môi trường hoặc theo một quy tắc có chương trình, có thể đặt một selector vào `@Import`:

~~~java
@Configuration
@Import(StorageImportSelector.class)
public class ApplicationConfiguration {
}
~~~

Lớp `StorageImportSelector` không phải là nơi tự tạo instance của các bean nghiệp vụ. Nó chỉ trả về tên các lớp cấu hình mà Spring cần đưa vào quá trình xử lý.

## 2. ImportSelector hoạt động như thế nào?

`ImportSelector` thuộc package `org.springframework.context.annotation`. Hợp đồng cơ bản của interface là:

~~~java
public interface ImportSelector {

    String[] selectImports(AnnotationMetadata importingClassMetadata);
}
~~~

Spring truyền vào `AnnotationMetadata` của lớp cấu hình đang import selector. Selector có thể đọc metadata của lớp đó, ví dụ annotation nào đang hiện diện và các thuộc tính của annotation. Phương thức trả về mảng tên lớp đầy đủ (fully qualified class names) cần import.

Ví dụ, một annotation bật chức năng lưu trữ có thể mang thuộc tính lựa chọn:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(StorageImportSelector.class)
public @interface EnableStorage {

    String mode() default "memory";
}
~~~

Lớp cấu hình sử dụng annotation:

~~~java
@Configuration
@EnableStorage(mode = "filesystem")
public class ApplicationConfiguration {
}
~~~

Selector đọc thuộc tính `mode` từ metadata của lớp import:

~~~java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class StorageImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(
            AnnotationMetadata importingClassMetadata) {

        var attributes = importingClassMetadata.getAnnotationAttributes(
                EnableStorage.class.getName()
        );

        if (attributes == null) {
            throw new IllegalStateException(
                    "@EnableStorage metadata is missing"
            );
        }

        String mode = (String) attributes.get("mode");

        return switch (mode) {
            case "memory" -> new String[] {
                    InMemoryStorageConfiguration.class.getName()
            };
            case "filesystem" -> new String[] {
                    FileStorageConfiguration.class.getName()
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported storage mode: " + mode
            );
        };
    }
}
~~~

Khi `mode` là `filesystem`, selector trả về tên `FileStorageConfiguration`. Spring import và phân tích lớp cấu hình đó. Nếu là `memory`, lớp cấu hình được chọn sẽ là `InMemoryStorageConfiguration`.

Hai lớp cấu hình có thể cung cấp cùng một hợp đồng:

~~~java
@Configuration(proxyBeanMethods = false)
public class InMemoryStorageConfiguration {

    @Bean
    StorageClient storageClient() {
        return new InMemoryStorageClient();
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
public class FileStorageConfiguration {

    @Bean
    StorageClient storageClient() {
        return new FileStorageClient();
    }
}
~~~

Các service chỉ phụ thuộc vào interface `StorageClient`:

~~~java
@Service
public class DocumentService {

    private final StorageClient storageClient;

    public DocumentService(StorageClient storageClient) {
        this.storageClient = storageClient;
    }
}
~~~

Nhờ đó, logic chọn cấu hình nằm trong selector, còn service không cần tự kiểm tra `mode` hoặc tạo implementation bằng câu lệnh điều kiện.

### Đọc metadata của lớp import

Tham số `AnnotationMetadata` mô tả lớp cấu hình đang import selector. Nó cho phép selector đọc annotation và thuộc tính mà không cần khởi tạo instance của lớp cấu hình đó.

Một số thao tác thường dùng:

~~~java
boolean hasEnableStorage = importingClassMetadata.hasAnnotation(
        EnableStorage.class.getName()
);

Map<String, Object> attributes =
        importingClassMetadata.getAnnotationAttributes(
                EnableStorage.class.getName()
        );
~~~

Nếu selector được dùng với một annotation tổng hợp hoặc có nhiều annotation cấu hình liên quan, hãy xác định rõ metadata nào là nguồn quyết định. Tránh giả định rằng selector đang nhận metadata của một bean đã được khởi tạo.

## 3. Chọn cấu hình theo Environment

Selector cũng có thể dựa vào các thuộc tính môi trường. Spring hỗ trợ các callback kiểu `Aware` cho những đối tượng chiến lược được framework khởi tạo, trong đó có `EnvironmentAware`. Có thể dùng callback này để nhận `Environment`:

~~~java
import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;

public class StorageImportSelector
        implements ImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(
            AnnotationMetadata importingClassMetadata) {

        String mode = environment.getProperty(
                "app.storage.mode",
                "memory"
        );

        return switch (mode) {
            case "memory" -> new String[] {
                    InMemoryStorageConfiguration.class.getName()
            };
            case "filesystem" -> new String[] {
                    FileStorageConfiguration.class.getName()
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported app.storage.mode: " + mode
            );
        };
    }
}
~~~

Cấu hình có thể đặt trong `application.yml`:

~~~yaml
app:
  storage:
    mode: filesystem
~~~

Ở ví dụ này, selector đọc giá trị từ `Environment` và chọn một lớp cấu hình. Giá trị mặc định `memory` được dùng khi thuộc tính không tồn tại. Với giá trị không hợp lệ, selector ném exception để ứng dụng thất bại sớm thay vì âm thầm chọn một implementation ngoài dự kiến.

Có thể truyền giá trị qua biến môi trường hoặc tham số dòng lệnh theo các nguồn cấu hình Spring Boot hỗ trợ. Ví dụ:

~~~bash
APP_STORAGE_MODE=filesystem
~~~

Việc lựa chọn vẫn diễn ra trong giai đoạn phân tích cấu hình và tạo ApplicationContext. Thay đổi thuộc tính sau khi context đã khởi tạo không làm selector chạy lại hoặc tự thay thế bean đang được sử dụng.

## 4. DeferredImportSelector khác gì ImportSelector?

`DeferredImportSelector` là biến thể của `ImportSelector`:

~~~java
public interface DeferredImportSelector extends ImportSelector {

    // Các phương thức mở rộng cho xử lý deferred
}
~~~

Điểm quan trọng là Spring trì hoãn việc xử lý selector này cho tới sau khi đã xử lý các lớp cấu hình thông thường. Điều đó hữu ích khi quyết định import cần xét trên tập cấu hình đã được phát hiện hoặc cần phối hợp với các điều kiện cấu hình.

Ví dụ, một selector thông thường có thể được xử lý trong lúc Spring đang phân tích một lớp cấu hình, trong khi các cấu hình khác vẫn còn nằm trong luồng phân tích. Với deferred selector, Spring gom việc xử lý lại sau phần phân tích cấu hình thông thường. Nhờ vậy, cơ chế lựa chọn có thể hoạt động ở giai đoạn muộn hơn trong quá trình bootstrap.

Có thể đổi ví dụ theo Environment ở phần trước thành deferred selector:

~~~java
import org.springframework.context.EnvironmentAware;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class DeferredStorageImportSelector
        implements DeferredImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(
            AnnotationMetadata importingClassMetadata) {

        String mode = environment.getProperty(
                "app.storage.mode",
                "memory"
        );

        return switch (mode) {
            case "memory" -> new String[] {
                    InMemoryStorageConfiguration.class.getName()
            };
            case "filesystem" -> new String[] {
                    FileStorageConfiguration.class.getName()
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported app.storage.mode: " + mode
            );
        };
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
~~~

Annotation bật tính năng có thể import deferred selector này:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(DeferredStorageImportSelector.class)
public @interface EnableStorage {
}
~~~

Khi Spring xử lý cấu hình, deferred selector được ghi nhận và xử lý ở giai đoạn deferred. Nó vẫn trả về tên lớp cấu hình như `ImportSelector`; Spring tiếp tục đăng ký và phân tích các lớp đó.

Không nên chọn `DeferredImportSelector` chỉ vì tên của nó nghe có vẻ mạnh hơn. Nếu selector chỉ cần đọc metadata của annotation import và trả về một cấu hình, `ImportSelector` thường đã đủ. Chọn deferred khi thời điểm xử lý muộn hơn có ý nghĩa đối với quy tắc cấu hình.

## 5. DeferredImportSelector.Group dùng để làm gì?

Ngoài việc trì hoãn, `DeferredImportSelector` còn hỗ trợ cơ chế `Group`. Group cho phép gom kết quả từ nhiều deferred selector, xử lý chúng cùng nhau và quyết định danh sách import cuối cùng.

Hợp đồng rút gọn của group gồm hai bước:

~~~java
public interface Group {

    void process(
            AnnotationMetadata metadata,
            DeferredImportSelector selector
    );

    Iterable<Entry> selectImports();
}
~~~

- `process(...)` nhận metadata của lớp import và selector tương ứng để thu thập các lựa chọn.
- `selectImports()` trả về các entry đã được tổng hợp. Mỗi `Entry` liên kết metadata của lớp import với tên lớp được import.

Một selector có thể chỉ định group bằng cách ghi đè `getImportGroup()`:

~~~java
@Override
public Class<? extends Group> getImportGroup() {
    return StorageImportGroup.class;
}
~~~

Ví dụ minh họa một group thu thập kết quả:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class StorageImportGroup implements DeferredImportSelector.Group {

    private final List<Entry> entries = new ArrayList<>();

    @Override
    public void process(
            AnnotationMetadata metadata,
            DeferredImportSelector selector) {

        for (String className : selector.selectImports(metadata)) {
            entries.add(new Entry(metadata, className));
        }
    }

    @Override
    public Iterable<Entry> selectImports() {
        return List.copyOf(entries);
    }
}
~~~

Ví dụ này giữ lại các import đã thu thập. Một group thực tế có thể bổ sung logic loại trùng, ưu tiên hoặc loại bỏ cấu hình theo quy tắc của hệ thống. Group đặc biệt hữu ích khi nhiều selector cần phối hợp để tạo một tập cấu hình thống nhất.

Không cần tự viết Group nếu chỉ có một selector chọn một cấu hình. Hãy dùng cơ chế mặc định trước; chỉ thêm Group khi cần tổng hợp hoặc điều phối kết quả từ nhiều selector.

### Thứ tự xử lý selector

`DeferredImportSelector` mở rộng `Ordered`. Có thể điều khiển thứ tự tương đối bằng cách triển khai `getOrder()` hoặc dùng cơ chế sắp xếp tương ứng. Thứ tự giúp framework sắp xếp các selector trong quá trình deferred processing; nó không phải cam kết rằng mọi bean do selector import sẽ được khởi tạo theo thứ tự nghiệp vụ tùy ý.

Nếu nhiều selector cần phối hợp, Group là nơi phù hợp hơn để biểu diễn việc tổng hợp kết quả. Không nên dựa vào thứ tự ngẫu nhiên của component scan hoặc thứ tự khai báo class để điều khiển phụ thuộc giữa các bean.

## 6. Ví dụ thực tế: Spring Boot auto-configuration

Spring Boot sử dụng deferred import để triển khai cơ chế auto-configuration. Annotation `@EnableAutoConfiguration` được kích hoạt thông qua `@SpringBootApplication`; cơ chế này đưa `AutoConfigurationImportSelector` vào quá trình phân tích cấu hình.

Selector thu thập các ứng viên auto-configuration, sau đó các điều kiện như `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` và các điều kiện khác quyết định cấu hình nào thực sự có hiệu lực.

Trong Spring Boot 3, danh sách auto-configuration được công bố qua file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Một thư viện có thể khai báo tên các lớp auto-configuration của nó trong file này. Spring Boot đọc danh sách ứng viên thông qua cơ chế import deferred và đánh giá điều kiện của các cấu hình đó.

Điều này giúp thư viện cung cấp tích hợp theo classpath và cấu hình mà ứng dụng không cần import thủ công từng cấu hình. Ví dụ, khi thư viện client có mặt và người dùng chưa tự cung cấp bean thay thế, auto-configuration có thể đăng ký implementation mặc định.

`AutoConfigurationImportSelector` là ví dụ thực tế cho thấy deferred selection có thể điều phối một tập cấu hình lớn. Khi viết ứng dụng thông thường, hiếm khi cần tự xây dựng lại toàn bộ cơ chế auto-configuration của Spring Boot.

## 7. Phân biệt selector với các cơ chế đăng ký bean khác

Các extension point cấu hình có mục đích khác nhau:

| Cơ chế | Nhiệm vụ chính | Khi nên dùng |
|---|---|---|
| `@Import(SomeConfiguration.class)` | Import một lớp cấu hình đã biết | Tập cấu hình cố định |
| `ImportSelector` | Chọn tên các lớp cấu hình bằng code | Lựa chọn theo metadata hoặc quy tắc |
| `DeferredImportSelector` | Chọn cấu hình ở giai đoạn deferred | Cần xử lý sau các cấu hình thông thường |
| `DeferredImportSelector.Group` | Gom và điều phối nhiều kết quả deferred | Nhiều selector cần phối hợp |
| `ImportBeanDefinitionRegistrar` | Đăng ký BeanDefinition bằng code | Cần kiểm soát trực tiếp định nghĩa bean |
| `@Conditional` | Quyết định cấu hình hoặc bean có được áp dụng hay không | Điều kiện gắn với cấu hình/bean cụ thể |

Selector trả về tên lớp cần import, còn `ImportBeanDefinitionRegistrar` thao tác trực tiếp với `BeanDefinitionRegistry` để đăng ký định nghĩa bean. Nếu mục tiêu là đưa thêm các lớp cấu hình vào context, selector thường biểu đạt ý định tốt hơn. Nếu cần tạo nhiều BeanDefinition dựa trên metadata hoặc một mô hình đăng ký riêng, registrar có thể phù hợp hơn.

Các annotation `@Conditional` cũng có thể được dùng trên lớp cấu hình được import. Selector quyết định lớp nào được đưa vào quá trình phân tích; condition quyết định lớp hoặc bean đó có thỏa điều kiện để được áp dụng hay không. Hai cơ chế có thể bổ trợ nhau.

## 8. Những lỗi thường gặp khi viết selector

### Trả về tên lớp sai

Các phần tử trong mảng kết quả phải là tên lớp đầy đủ, chẳng hạn `com.example.storage.FileStorageConfiguration`. Dùng `SomeConfiguration.class.getName()` giúp tránh lỗi chính tả và đổi package.

Nếu tên lớp không tồn tại hoặc không thể tải, quá trình xử lý cấu hình sẽ thất bại.

### Trả về implementation thay vì cấu hình phù hợp

Selector có thể import một lớp cấu hình chứa các phương thức `@Bean`. Đây thường là cách rõ ràng để nhóm những bean liên quan và giữ logic đăng ký trong cơ chế cấu hình của Spring.

Không nên tự gọi constructor của service hoặc repository bên trong selector. Làm như vậy bỏ qua container, dependency injection, bean post-processing và các quy tắc scope.

### Để nhiều cấu hình cùng đăng ký một bean không tương thích

Nếu selector trả về hai cấu hình đều khai báo một bean cùng kiểu và cùng tên, ứng dụng có thể gặp xung đột hoặc có nhiều candidate khi inject. Hãy bảo đảm quy tắc lựa chọn có kết quả rõ ràng, hoặc thiết kế điều kiện/qualifier phù hợp khi thực sự cần nhiều implementation cùng tồn tại.

### Dùng deferred selector nhưng vẫn giả định nó chạy sau mọi bean

Deferred chỉ nói về thứ tự xử lý trong giai đoạn phân tích cấu hình. Nó không có nghĩa tất cả bean lazy, prototype, request scope hoặc mọi công việc startup đã hoàn tất. Cũng không có nghĩa ứng dụng đã sẵn sàng nhận request.

### Mong selector tự chạy lại khi thuộc tính thay đổi

Selector tham gia quá trình xây dựng ApplicationContext. Đổi thuộc tính sau khi context đã refresh không kích hoạt việc lựa chọn lại. Muốn cấu hình khác có hiệu lực, cần một chiến lược khởi tạo hoặc refresh context phù hợp.

## 9. Quy trình lựa chọn cấu hình có chương trình

Khi cần chọn cấu hình bằng code, có thể đi theo các bước sau:

1. Xác định điểm kích hoạt bằng `@Import` hoặc một annotation bật tính năng.
2. Xác định dữ liệu quyết định: metadata của lớp import, Environment hay danh sách ứng viên.
3. Dùng `ImportSelector` nếu có thể chọn ngay trong luồng xử lý cấu hình thông thường.
4. Dùng `DeferredImportSelector` nếu cần đợi các cấu hình thông thường được xử lý trước.
5. Chỉ dùng `Group` khi nhiều deferred selector cần gom, lọc, loại trùng hoặc điều phối kết quả.
6. Trả về tên đầy đủ của các lớp cấu hình và để Spring quản lý việc tạo bean.
7. Xác định rõ hành vi khi thiếu thuộc tính, giá trị không hợp lệ hoặc không có cấu hình nào được chọn.
8. Kiểm tra các trường hợp lựa chọn để bảo đảm đúng một tập cấu hình hợp lệ được đăng ký.

`ImportSelector` và `DeferredImportSelector` mở rộng khả năng cấu hình của Spring bằng cách tách quy tắc lựa chọn khỏi các bean nghiệp vụ. Hiểu đúng thời điểm xử lý của từng loại giúp chọn đúng extension point, tổ chức auto-configuration rõ ràng và để ApplicationContext tiếp tục quản lý dependency, lifecycle và scope của các thành phần được import.

