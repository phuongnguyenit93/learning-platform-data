# Phân biệt singleton của Spring với mẫu Singleton GoF

## 1. Hai khái niệm có tên giống nhau nhưng đơn vị bảo đảm khác nhau

**Singleton của Spring** là một *bean scope* trong IoC container: với **một bean definition cụ thể trong một container**, Spring quản lý một instance dùng chung. Những lần lấy hoặc tiêm phụ thuộc tham chiếu đến cùng bean đó sẽ nhận lại cùng đối tượng do container cung cấp. Đây là scope **mặc định** của Spring.

**Singleton theo mẫu thiết kế Gang of Four (GoF)** là một cách thiết kế lớp nhằm kiểm soát việc khởi tạo và cung cấp một điểm truy cập chung đến một instance. Trong mô hình Java thông thường, mẫu này thường bảo đảm một instance **cho một lớp trong phạm vi ClassLoader tải lớp đó**, miễn là cách hiện thực không bị phá vỡ bởi những cơ chế tạo đối tượng đặc biệt.

Công thức cần nhớ:

- **Spring singleton = một instance trên mỗi bean definition trong mỗi Spring IoC container.**
- **GoF Singleton = một instance được kiểm soát ở cấp lớp/ClassLoader.**

Do đó, **Spring singleton không có nghĩa là mỗi class Java chỉ có một object trong toàn JVM**. Cùng một lớp có thể sinh nhiều Spring singleton hợp lệ nếu có nhiều bean definition hoặc nhiều container.

## 2. Bảng so sánh

| Khía cạnh | Spring singleton | GoF Singleton |
|---|---|---|
| Đơn vị quản lý | Bean definition (tên/định danh bean) trong một IoC container | Lớp có logic tự kiểm soát khởi tạo |
| Phạm vi thông thường | Mỗi container, mỗi bean | Mỗi ClassLoader đối với cách hiện thực GoF thông dụng |
| Ai quản lý instance? | Spring BeanFactory/ApplicationContext | Mã của lớp (static field, factory method, enum...) |
| Cách lấy instance | Dependency injection, hoặc `context.getBean(...)` | Thường gọi `MySingleton.getInstance()` hoặc hằng enum |
| Constructor | Có thể public và nhận dependency qua constructor | Thường private để chặn `new` từ bên ngoài |
| Hai bean cùng Java class | **Có thể là hai instance khác nhau** nếu đăng ký thành hai bean | Một triển khai GoF thường hướng tới một instance cho class đó |
| Hai Spring context khác nhau | Mỗi context có thể quản lý một instance riêng | Một static singleton thông thường có thể được dùng chung nếu hai context dùng cùng class do cùng ClassLoader tải |
| Cấu hình và DI | Tích hợp quản lý phụ thuộc, cấu hình, khởi tạo và hủy bean | Phải tự thiết kế cách truyền phụ thuộc, khởi tạo và dọn dẹp |
| Thay thế trong unit test | Dễ tiêm mock/fake hoặc khai báo bean thay thế | Gọi static toàn cục làm thay thế và cô lập test khó hơn |
| Bảo đảm thread-safe cho state | **Không tự động** | **Không tự động**; khởi tạo an toàn cũng chưa làm mọi phương thức an toàn |
| Khi nào thích hợp? | Dịch vụ, repository, collaborator do Spring quản lý | Thành phần độc lập framework thật sự cần một điểm truy cập tĩnh |

`@Singleton` không phải cơ chế cần dùng để chọn scope chuẩn trong Spring Framework: cách thường dùng là để mặc định hoặc khai báo `@Scope("singleton")`. Nếu một lớp đồng thời là GoF Singleton và được đăng ký bean trong Spring, hai cơ chế không tự động đồng nhất phạm vi với nhau.

## 3. Spring singleton hoạt động như thế nào?

Giả sử Spring có bean mang tên `paymentService`. Trong cùng `ApplicationContext`, những nơi yêu cầu **bean đó** thông qua injection hoặc `getBean("paymentService")` sẽ chia sẻ tham chiếu được Spring quản lý.

```text
ApplicationContext A
├── bean definition: paymentService  ──> PaymentService object #1
│                                      ↑      ↑       ↑
│                                      |      |       |
│                                  Controller Service Job
└── bean definition: backupService   ──> PaymentService object #2

ApplicationContext B
└── bean definition: paymentService  ──> PaymentService object #3
```

Ba đối tượng trên hoàn toàn có thể cùng kiểu `PaymentService`. Quy tắc singleton vẫn được tuân thủ: mỗi bean definition thuộc một container chỉ có một instance được quản lý ở một thời điểm theo vòng đời tương ứng.

### 3.1. Khai báo trong ứng dụng Spring

Một bean được tạo với `@Component`, `@Service`, `@Repository` hoặc phương thức `@Bean` có scope `singleton` mặc định nếu không khai báo scope khác:

```java
@Service
public class CatalogService {
    private final ProductRepository repository;

    public CatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product findById(long id) {
        return repository.findById(id);
    }
}
```

Đoạn trên là **minh họa thành phần trong một ứng dụng có `ProductRepository`/`Product`**; không phải chương trình độc lập. Không cần private constructor, static `INSTANCE`, hoặc `getInstance()`. Container tạo bean và truyền dependency qua constructor. Nhiều controller dùng `CatalogService` sẽ thường được tiêm cùng một bean của context.

Khai báo tường minh cũng hợp lệ nhưng dư thừa khi dùng scope mặc định:

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
CatalogService catalogService(ProductRepository repository) {
    return new CatalogService(repository);
}
```

Nếu dùng đoạn khai báo này, cần import `Bean`, `Scope` và `ConfigurableBeanFactory`, đặt phương thức trong một lớp `@Configuration` hợp lệ, đồng thời có bean `ProductRepository`. Đây là minh họa cấu hình, không ghép trực tiếp với ví dụ `@Service` ở trên để tránh định nghĩa trùng bean ngoài ý muốn.

### 3.2. Khi nào instance được tạo và được tái sử dụng?

Thông thường, singleton bean không được đánh dấu lazy sẽ được khởi tạo khi `ApplicationContext` refresh; `@Lazy` có thể trì hoãn khởi tạo đến lúc cần. Sau khi tạo, container quản lý tham chiếu và cung cấp lại đối tượng cho các lần yêu cầu cùng bean, thay vì gọi constructor lại mỗi lần `getBean()`.

Spring còn quản lý dependency injection và lifecycle callback (chẳng hạn `@PostConstruct`, `@PreDestroy`) theo các quy tắc bean lifecycle. Với container đóng đúng cách, các callback hủy tương ứng có thể được gọi. Một object do `new` trực tiếp bên ngoài Spring không tự nhiên trở thành singleton bean.

Lưu ý: Spring có thể trả về **proxy** do các cơ chế như AOP tạo ra. Khi nói `getBean()` trả cùng instance, ta so sánh tham chiếu bean **do container cung cấp**; không nên suy từ đó rằng đối tượng luôn chính là instance lớp triển khai gốc mà không có proxy.

## 4. GoF Singleton tự kiểm soát việc tạo đối tượng

Một hiện thực phổ biến trong Java 17+ là *initialization-on-demand holder*. JVM bảo đảm quá trình khởi tạo lớp được đồng bộ đúng cách, nên cách này có tính lazy và khởi tạo an toàn mà không phải tự thêm `synchronized` quanh từng lần gọi:

```java
public final class SettingsRegistry {
    private SettingsRegistry() {
    }

    private static final class Holder {
        private static final SettingsRegistry INSTANCE =
                new SettingsRegistry();
    }

    public static SettingsRegistry getInstance() {
        return Holder.INSTANCE;
    }
}
```

Mỗi nơi cùng sử dụng lớp `SettingsRegistry` từ cùng ClassLoader sẽ thường nhận cùng đối tượng khi gọi `getInstance()`. Constructor private ngăn lời gọi `new SettingsRegistry()` thông thường ở bên ngoài lớp. Đây là một **class tự cung cấp singleton**; không cần Spring container để gọi nó.

Tuy nhiên, `static` không đồng nghĩa duy nhất trên mọi process/JVM/ClassLoader. Các cách tương tác đặc biệt với reflection, serialization, cloning hoặc Java instrumentation cũng cần được xét khi thiết kế một Singleton nghiêm ngặt. Java `enum` với một phần tử là một lựa chọn vững hơn cho một số yêu cầu bảo vệ danh tính singleton, nhưng vẫn tồn tại theo phạm vi lớp/ClassLoader chứ không biến thành một instance trên toàn hệ phân tán.

Một GoF Singleton muốn nhận `DataSource`, HTTP client hoặc cấu hình phụ thuộc môi trường phải tự thiết kế phương thức cung cấp những dependency này. Vì vậy trong ứng dụng Spring, ép mọi service thành GoF Singleton thường làm mất lợi ích dependency injection và khó thay thế đối tượng khi test.

## 5. Thí nghiệm chạy được: cùng bean, khác bean, khác container và GoF

Ví dụ sau tạo **hai bean cùng kiểu** trong context thứ nhất, **cùng bean name** ở context thứ hai, rồi đối chiếu với một GoF Singleton. Không cần chạy Spring Boot, servlet hay database.

Yêu cầu: JDK 17+ và Maven 3.9+.

Cấu trúc:

```text
singleton-demo/
├── pom.xml
└── src/main/java/example/SingletonComparison.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>singleton-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/example/SingletonComparison.java`:

```java
package example;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SingletonComparison {

    public static void main(String[] args) {
        try (var contextA = new AnnotationConfigApplicationContext(AppConfig.class);
             var contextB = new AnnotationConfigApplicationContext(AppConfig.class)) {

            Service a1 = contextA.getBean("primaryService", Service.class);
            Service a2 = contextA.getBean("primaryService", Service.class);
            Service backup = contextA.getBean("backupService", Service.class);
            Service b1 = contextB.getBean("primaryService", Service.class);

            System.out.println("Same bean in context A: " + (a1 == a2));
            System.out.println("Different beans, same class: " + (a1 == backup));
            System.out.println("Same name, different contexts: " + (a1 == b1));

            var global1 = GlobalSettings.getInstance();
            var global2 = GlobalSettings.getInstance();
            System.out.println("GoF getInstance twice: " + (global1 == global2));

            System.out.println("Spring bean scope: " +
                    contextA.isSingleton("primaryService"));
        }
    }

    public static class Service {
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Service primaryService() {
            return new Service();
        }

        @Bean
        public Service backupService() {
            return new Service();
        }
    }

    public static final class GlobalSettings {
        private GlobalSettings() {
        }

        private static final class Holder {
            private static final GlobalSettings INSTANCE =
                    new GlobalSettings();
        }

        public static GlobalSettings getInstance() {
            return Holder.INSTANCE;
        }
    }
}
```

Tại thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.SingletonComparison
```

Stdout của chương trình (bỏ qua log riêng của Maven nếu môi trường hiển thị):

```text
Same bean in context A: true
Different beans, same class: false
Same name, different contexts: false
GoF getInstance twice: true
Spring bean scope: true
```

**Giải thích từng phép so sánh:**

1. `a1 == a2` là `true`: hai lần yêu cầu cùng `primaryService` trong `contextA` lấy cùng Spring singleton.
2. `a1 == backup` là `false`: `primaryService` và `backupService` là hai **bean definition** dù đều trả về `Service`. Mỗi bean riêng vẫn có scope singleton.
3. `a1 == b1` là `false`: hai `ApplicationContext` độc lập tạo bean cùng tên riêng của từng container.
4. Hai lần gọi `GlobalSettings.getInstance()` là `true`: GoF Singleton dùng cùng static holder của lớp đã tải.
5. `isSingleton("primaryService")` là `true`: container xác nhận scope của bean này.

Thí nghiệm này cố ý tạo hai context độc lập. Với cấu trúc **parent/child context**, child có thể ủy quyền tìm bean cho parent, nên phải xem bean thật sự thuộc container nào trước khi kết luận hai lần lookup sẽ tạo hai instance.

## 6. Vì sao scope singleton của Spring không phải cơ chế đồng bộ luồng?

Một Spring singleton thường được nhiều request, worker hoặc thread gọi đồng thời. **Chỉ một instance** là phát biểu về danh tính đối tượng; **thread-safe** là phát biểu về tính đúng đắn khi truy cập đồng thời.

Ví dụ thiết kế nguy hiểm:

```java
@Service
public class CheckoutService {
    private long currentOrderId; // Mutable state dùng chung giữa mọi caller

    public void checkout(long orderId) {
        currentOrderId = orderId;
        // Thread khác có thể ghi đè field này trước khi xử lý xong.
        charge(currentOrderId);
    }

    private void charge(long orderId) {
        // Gọi cổng thanh toán thực tế ở đây.
    }
}
```

Đây là **mã minh họa lỗi thiết kế**, không phải ví dụ chạy độc lập. Request A đặt `currentOrderId = 10`; trước khi A gọi `charge`, request B có thể đổi field thành `20`. A có nguy cơ xử lý nhầm đơn hàng. Đổi thành scope GoF Singleton cũng không xử lý vấn đề.

Cách sửa trong trường hợp không cần chia sẻ trạng thái:

```java
@Service
public class CheckoutService {
    public void checkout(long orderId) {
        charge(orderId); // Dùng tham số/biến cục bộ của từng lần gọi.
    }

    private void charge(long orderId) {
        // Gọi cổng thanh toán thực tế ở đây.
    }
}
```

Nguyên tắc áp dụng: giữ singleton service **stateless** khi có thể; trạng thái cho mỗi request nên nằm trong tham số, biến cục bộ hoặc một đối tượng thuộc đúng vòng đời yêu cầu. Nếu bắt buộc chia sẻ mutable state, cần cơ chế đồng bộ và ràng buộc nhất quán phù hợp (`Atomic*`, lock, thiết kế bất biến, transaction/database...), bất kể chọn Spring hay GoF.

## 7. Những hiểu nhầm thường gặp và cách kiểm tra

### “Một `@Service` singleton nghĩa là chỉ một object của class đó trong ứng dụng?”

Không nhất thiết. `@Service` thông thường đăng ký một bean singleton trong container thực tế đang quét component. Nhưng bạn vẫn có thể tạo một object bằng `new`, định nghĩa thêm bean qua `@Bean`, hoặc tạo container khác. Phạm vi Spring kiểm soát là **bean được quản lý**, không phải tất cả object cùng class.

### “`@Scope("singleton")` và constructor private của GoF là tương đương?”

Không. `@Scope` nói Spring phải quản lý bean như thế nào; constructor private là biện pháp thiết kế Java để giới hạn cách bên ngoài tạo object. Một Spring bean singleton có thể dùng constructor public, và `@Scope("singleton")` không làm constructor đó trở thành private.

### “Spring singleton tự động tồn tại trên mọi server/pod?”

Không. Mỗi JVM/container ứng dụng có các object và registry của chính nó. Trong hệ thống có nhiều replica, singleton không giúp lưu trạng thái dùng chung hoặc bảo đảm một tác vụ toàn cụm chỉ được chạy một lần. Bài toán phân tán cần storage, khóa hoặc cơ chế điều phối khác.

### “Tiêm `prototype` vào `singleton` thì mỗi lần gọi method sẽ nhận prototype mới?”

Không. Với constructor/field injection thông thường, dependency `prototype` được giải quyết **lúc Spring xây dựng singleton**, nên singleton giữ lại instance được tiêm ban đầu. Nếu cần instance mới mỗi lần thao tác, có thể tiêm `ObjectProvider<PrototypeType>` và gọi `getObject()` khi cần. Đây là hành vi dependency injection và phạm vi bean, không phải đặc tính của GoF Singleton.

### “Dùng `getBean()` hai lần thì luôn nhận đối tượng giống nhau?”

Chỉ đúng trong ngữ cảnh đủ điều kiện: **cùng container và cùng singleton bean**, không có logic thay đổi đặc biệt. Với `prototype` hoặc context khác, không được suy như vậy. Đừng kiểm tra bằng `equals()` khi cần xác định cùng tham chiếu: dùng `==`. `context.isSingleton(beanName)` giúp kiểm tra scope, còn `==` kiểm tra danh tính hai tham chiếu đã lấy.

### “Singleton của Spring luôn được khởi tạo ngay lúc ứng dụng bắt đầu?”

Không hoàn toàn. Mặc định singleton thường eager-initialized khi context refresh, nhưng `@Lazy` có thể trì hoãn. Thời điểm tạo và số lượng instance là **hai trục khái niệm khác nhau**.

## 8. Chọn giải pháp nào trong thực tế?

Trong dự án có Spring, ưu tiên để Spring quản lý `@Service`, `@Repository`, `@Component` hoặc đối tượng do `@Bean` trả về, truyền dependency qua constructor và sử dụng singleton mặc định khi dịch vụ không giữ state của từng request. Cách này làm cho lifecycle, cấu hình theo môi trường và thay thế dependency trong test rõ ràng hơn.

Chỉ chọn GoF Singleton có chủ đích khi cần một thực thể độc lập khỏi IoC container với API static và đã xét tác động đến testability, lifecycle, concurrency và ClassLoader. Không cần triển khai `private static INSTANCE` bên trong mọi Spring `@Service`: nó thường tạo **hai tầng quản lý instance** khó hiểu, đồng thời có thể bỏ qua DI.

**Checklist tự kiểm tra:**

- Cùng **bean name**, cùng **container**, scope singleton → cùng tham chiếu do Spring cung cấp.
- Hai **bean name** với hai lần khởi tạo của cùng class → có thể là hai singleton khác nhau.
- Hai **container độc lập** → mỗi container có singleton registry của riêng mình.
- Một class triển khai **GoF Singleton** → logic cấp class/ClassLoader quyết định instance, không phụ thuộc tên Spring bean.
- Cả hai cơ chế → cần thiết kế thread-safety riêng nếu đối tượng chia sẻ mutable state.

## Tài liệu tham khảo chính thức

- Spring Framework — [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, phạm vi container và bean.
- Spring Framework — [Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): khai báo và cấu hình scope của bean.
- Spring Framework — [Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definition và thành phần metadata.
