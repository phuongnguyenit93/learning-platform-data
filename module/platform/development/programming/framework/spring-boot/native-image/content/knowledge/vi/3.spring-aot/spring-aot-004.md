# Sinh mã đăng ký, tạo và liên kết các bean bằng Spring AOT

Trong một ứng dụng Spring Boot, **bean** là đối tượng do Spring IoC container quản lý. Khi chạy trên JVM, Spring có thể quét annotation, phân tích các lớp cấu hình, tạo `BeanDefinition`, tìm constructor, giải quyết dependency rồi tạo bean lúc khởi động hoặc khi có nhu cầu. Cơ chế này linh hoạt, nhưng một phần công việc có thể phải thực hiện lại mỗi lần ứng dụng khởi động và có thể phụ thuộc vào reflection hoặc các cấu trúc động.

**Spring AOT (Ahead-of-Time)** chuyển những thông tin Spring có thể xác định ở **thời điểm build** thành mã Java được sinh sẵn. Phần mã đó mô tả cách **đăng ký bean**, cách **cung cấp đối tượng bean** và cách **liên kết dependency** để container dùng khi ứng dụng chạy. Đây là một mắt xích quan trọng khi biên dịch Spring Boot thành **GraalVM Native Image**, vì trình phân tích reachability cần nhìn thấy các đường gọi và kiểu có thể xuất hiện.

Bài học tập trung vào ba thao tác cốt lõi: đăng ký định nghĩa bean, tạo instance và liên kết các bean với nhau. Đồng thời, bài học chỉ ra phần nào được chuẩn bị ở build time, phần nào vẫn diễn ra tại runtime và cách kiểm tra kết quả AOT.

## 1. Phân biệt ba thao tác

Ba khái niệm thường bị gộp thành “Spring tạo bean”, nhưng chúng diễn ra tại những thời điểm và mức trừu tượng khác nhau:

| Thao tác | Vai trò | Ví dụ | Thời điểm thực hiện |
|---|---|---|---|
| **Đăng ký bean** | Cung cấp cho container một `BeanDefinition` gồm tên, kiểu, scope, thông tin tạo bean và các thuộc tính cần thiết | Đăng ký bean `paymentGateway` với một instance supplier | Mã đăng ký được **sinh khi build**, còn lệnh đăng ký vào container được **thực thi khi runtime** |
| **Tạo bean** | Thực thi supplier, constructor hoặc factory method để có instance thật | Gọi `new LocalPaymentGateway()` | Thường tại runtime khi container khởi tạo singleton hoặc khi bean được yêu cầu |
| **Liên kết bean** | Xác định và cung cấp bean phụ thuộc cho constructor, factory method hoặc điểm injection khác | Cung cấp `PaymentGateway` cho `PaymentService` | Đường cấp dependency có thể được **sinh khi build**, còn việc lấy instance thường vẫn diễn ra tại runtime |

**Mã được sinh ở build time không có nghĩa mọi đối tượng bean đều được tạo ở build time.** Khi native executable khởi động, Spring vẫn vận hành container, tạo singleton, áp dụng scope, xử lý lifecycle và giải quyết những dependency cần thiết theo cấu hình đã được chuẩn bị. Spring AOT chủ yếu làm giảm công việc khám phá và suy luận cấu trúc ứng dụng tại runtime.

## 2. Vì sao Spring cần sinh mã bean?

Trong chế độ thông thường, các bước khởi động có thể bao gồm quét `@Component`, `@Service`, `@Configuration`, đọc `@Bean`, áp dụng điều kiện, xử lý metadata và suy luận cách injection. Một số bước dùng reflection và có thể dẫn tới nhiều kiểu hoặc phương thức không thể nhận diện đầy đủ từ các lời gọi Java tĩnh.

Spring AOT chuyển phần có thể xác định trước thành các lời gọi Java và dữ liệu đăng ký cụ thể:

- Container có thể nhận một tập `BeanDefinition` đã được chuẩn bị theo cấu hình build.
- Instance supplier đã sinh thể hiện rõ hơn cách gọi constructor hoặc factory method.
- Đường liên kết dependency được mô tả bằng mã dễ phân tích hơn, thay vì chỉ phụ thuộc vào việc dò tìm annotation lúc chạy.
- Runtime hints có thể bổ sung những khả năng reflection, proxy, serialization hoặc resource mà mã sinh chưa biểu đạt hết.

Với GraalVM Native Image, những lời gọi tường minh này giúp **reachability analysis** nhận diện các lớp và phương thức cần có trong executable. Tuy nhiên, AOT không bảo đảm mọi trường hợp reflection đều được loại bỏ; một số thư viện và tình huống injection vẫn cần metadata riêng.

## 3. Ví dụ gốc: ứng dụng có hai bean phụ thuộc nhau

Giả sử một ứng dụng Spring Boot có một cổng thanh toán và dịch vụ xử lý thanh toán:

~~~java
package example.payment;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

interface PaymentGateway {
    String authorize(String orderId);
}

final class LocalPaymentGateway implements PaymentGateway {
    @Override
    public String authorize(String orderId) {
        return "APPROVED:" + orderId;
    }
}

final class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    String pay(String orderId) {
        return gateway.authorize(orderId);
    }
}

@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new LocalPaymentGateway();
    }

    @Bean
    PaymentService paymentService(PaymentGateway gateway) {
        return new PaymentService(gateway);
    }
}
~~~

Giả sử `PaymentConfiguration` nằm trong phạm vi component scan hoặc được `@Import` từ cấu hình ứng dụng chính. Spring nhận biết hai định nghĩa bean:

- `paymentGateway`: kiểu khai báo là `PaymentGateway`, giá trị trả về từ factory method `paymentGateway()`.
- `paymentService`: kiểu `PaymentService`, được tạo bởi factory method `paymentService(PaymentGateway gateway)`.

Dependency `PaymentGateway` trong tham số factory method là cạnh nối giữa hai bean. Spring cần tìm một bean phù hợp kiểu, sau đó mới gọi phương thức tạo `paymentService`. Lựa chọn `@Configuration(proxyBeanMethods = false)` phù hợp ở đây vì các phương thức `@Bean` không trực tiếp gọi lẫn nhau; chúng nhận dependency qua tham số do container cung cấp.

### Sơ đồ phụ thuộc

~~~mermaid
flowchart TD
    A["PaymentConfiguration"] --> B["BeanDefinition: paymentGateway"]
    A --> C["BeanDefinition: paymentService"]
    B --> D["LocalPaymentGateway instance"]
    D --> E["PaymentGateway dependency"]
    E --> F["PaymentService instance"]
    C --> F
    F --> G["Mã nghiệp vụ pay(orderId)"]
~~~

Mũi tên biểu diễn **quan hệ tạo và cấp dependency**, không phải thứ tự sinh file hay một lịch tạo mọi đối tượng cố định. Nếu có bean lazy, prototype hoặc điều kiện runtime được hỗ trợ, thời điểm tạo instance có thể khác.

## 4. Dòng xử lý từ nguồn Java đến mã đăng ký AOT

Với Spring Boot đã cấu hình AOT, quá trình xử lý có thể được hiểu theo các giai đoạn sau:

~~~mermaid
flowchart TD
    A["Source: @Configuration, @Bean, @Component, ..."] --> B["Chạy quá trình phân tích Spring AOT"]
    B --> C["Xác định cấu trúc bean/configuration"]
    C --> D["Sinh BeanDefinition, instance supplier, mã khởi tạo container"]
    C --> E["Đóng góp runtime hints cần thiết"]
    D --> F["Biên dịch mã Java AOT"]
    E --> G["GraalVM phân tích reachability"]
    F --> G
    G --> H["Native executable"]
    H --> I["Runtime: đăng ký bean và tạo instance khi cần"]
~~~

Quy trình trên có hai lớp thời gian:

**Build time:** Spring khởi tạo một môi trường xử lý AOT, áp dụng các phần xử lý cấu hình thích hợp, phân tích hệ thống bean, sinh các lớp hỗ trợ và metadata. Nếu build native, GraalVM tiếp tục phân tích mã ứng dụng cùng mã AOT và runtime hints.

**Runtime:** Khi executable được chạy, mã khởi tạo AOT đăng ký các bean definition đã chuẩn bị vào container. Container tạo bean theo scope và dependency, thực hiện những callback vòng đời được hỗ trợ và phục vụ yêu cầu ứng dụng.

Điểm quan trọng là **AOT làm sớm phần khám phá cấu trúc**, còn **IoC container vẫn chịu trách nhiệm quản lý vòng đời đối tượng**.

## 5. Mã đăng ký bean được sinh trông như thế nào?

Mã AOT do Spring sinh ra phụ thuộc phiên bản Spring Framework/Boot, loại bean, cấu hình và các AOT processor tham gia. Tên lớp, tên phương thức và API trong file sinh có thể thay đổi qua các phiên bản. Vì vậy, đoạn dưới đây chỉ là **mã minh họa ý tưởng**, không phải bản sao nguyên văn đầu ra của một phiên bản Spring:

~~~java
// MÔ PHỎNG Ý TƯỞNG — không phải mã nguồn AOT thực tế.
void registerBeans(BeanDefinitionRegistry registry,
                   ConfigurableListableBeanFactory beanFactory,
                   PaymentConfiguration configuration) {

    RootBeanDefinition gatewayDefinition =
        new RootBeanDefinition(PaymentGateway.class);
    gatewayDefinition.setInstanceSupplier(
        () -> configuration.paymentGateway()
    );
    registry.registerBeanDefinition(
        "paymentGateway", gatewayDefinition
    );

    RootBeanDefinition serviceDefinition =
        new RootBeanDefinition(PaymentService.class);
    serviceDefinition.setInstanceSupplier(() -> {
        PaymentGateway gateway =
            beanFactory.getBean(PaymentGateway.class);
        return configuration.paymentService(gateway);
    });
    registry.registerBeanDefinition(
        "paymentService", serviceDefinition
    );
}
~~~

Đoạn mô phỏng làm rõ ba ý:

1. **Đăng ký:** container nhận thông tin về `paymentGateway` và `paymentService` trước khi cần tạo instance.
2. **Tạo:** mỗi `BeanDefinition` có một cơ chế cung cấp instance. Mã tạo bean có thể gọi trực tiếp constructor hoặc factory method.
3. **Liên kết:** khi tạo `paymentService`, container lấy dependency `PaymentGateway` rồi chuyển cho factory method.

Trong file sinh thật, Spring có thể sử dụng các API như `BeanInstanceSupplier`, mã hỗ trợ factory method, lớp `__BeanDefinitions` và mã đăng ký tổng hợp; đừng dùng đoạn mô phỏng để đoán chính xác tên class hoặc thứ tự các lời gọi. Cách học chắc chắn nhất là **mở generated sources của chính dự án**.

### BeanDefinition khác instance như thế nào?

Một `BeanDefinition` giống “công thức” tạo bean: nó mô tả bean và cho container biết cách sản xuất đối tượng. Đối tượng thật chỉ xuất hiện khi công thức được thực thi.

Với scope mặc định `singleton`, Spring thường tạo một instance cho mỗi bean definition trong container và tái sử dụng instance đó. Với `prototype`, container có thể gọi cơ chế tạo nhiều lần khi có yêu cầu mới. Với `@Lazy`, tạo instance có thể bị trì hoãn. Những quy tắc này vẫn là trách nhiệm của container ở runtime, kể cả khi cách tạo đã được sinh mã từ trước.

## 6. AOT xử lý liên kết dependency ra sao?

Spring AOT có thể sinh mã giúp container giải quyết những điểm injection đã được nhận diện. Tuy nhiên, **dependency resolution** vẫn tuân theo semantics của Spring:

| Cách khai báo | Điều Spring phải bảo toàn |
|---|---|
| Constructor injection | Chọn constructor phù hợp và cấp các đối tượng cần thiết |
| Tham số của `@Bean` method | Lấy dependency trước khi gọi factory method |
| `@Qualifier` | Phân biệt bean khi có nhiều ứng viên cùng kiểu |
| `@Primary` | Ưu tiên ứng viên khi có nhiều bean phù hợp |
| `ObjectProvider<T>` | Cho phép lấy bean theo nhu cầu, không buộc tạo ngay mọi dependency |
| `@Lazy` và các scope | Duy trì việc tạo bean theo thời điểm và phạm vi tương ứng |
| `@Autowired` trên field/method | Cần xử lý injection point, có thể phát sinh nhu cầu truy cập reflective |

Xét trường hợp có hai cổng thanh toán:

~~~java
@Bean("localGateway")
PaymentGateway localGateway() {
    return new LocalPaymentGateway();
}

@Bean("remoteGateway")
PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}

@Bean
PaymentService paymentService(
        @Qualifier("localGateway") PaymentGateway gateway) {
    return new PaymentService(gateway);
}
~~~

Đây là đoạn trích bổ sung cho ví dụ trước; `RemotePaymentGateway` giả định đã được định nghĩa. Điều AOT cần thể hiện không chỉ là kiểu `PaymentGateway` mà còn là **qualifier `localGateway`**. Nếu mã sinh chỉ lấy một bean bất kỳ theo kiểu, nó sẽ sai với semantics của ứng dụng. Spring xử lý metadata injection để bảo toàn điều kiện lựa chọn bean.

**Không nên đồng nhất đồ thị dependency với một danh sách khởi tạo theo thứ tự cứng.** Trong Spring, dependency có thể là lazy, optional hoặc được truy vấn bằng `ObjectProvider`. Vòng phụ thuộc constructor không tự trở nên hợp lệ nhờ AOT; ứng dụng vẫn phải giải quyết vấn đề thiết kế dependency đó.

## 7. Spring AOT xử lý những gì, và xử lý đến đâu?

Một số nguồn định nghĩa bean phổ biến gồm:

- `@Component`, `@Service`, `@Repository`, `@Controller` nằm trong phạm vi scan.
- `@Configuration` và các phương thức `@Bean`.
- `@Import`, auto-configuration và những bean definition được tạo từ cơ chế cấu hình mà Spring AOT hỗ trợ.
- Những thành phần hạ tầng như bean post-processor, proxy, transaction hoặc validation khi framework và thư viện cung cấp tích hợp AOT phù hợp.

Spring Framework có các điểm mở rộng chuyên cho AOT, tiêu biểu là **`BeanFactoryInitializationAotProcessor`** và **`BeanRegistrationAotProcessor`**. Chúng cho phép framework hoặc thư viện đóng góp mã khởi tạo container hoặc điều chỉnh việc sinh đăng ký bean. Đây là cơ chế dành cho thành phần hạ tầng; ứng dụng thông thường nên ưu tiên cấu hình Spring tiêu chuẩn trước khi tự viết processor.

AOT không thể tự suy ra mọi thao tác đăng ký bean diễn ra hoàn toàn động sau khi ứng dụng đã được build. Ví dụ, nếu mã runtime đọc danh sách class từ một kho dữ liệu bên ngoài rồi mới tạo `BeanDefinition` cho từng class, tập bean thực tế có thể vượt ra ngoài những gì AOT đã chuẩn bị. Tình huống này đòi hỏi thiết kế lại cơ chế mở rộng hoặc cung cấp tích hợp AOT chuyên biệt.

### Phân biệt AOT code với runtime hints

- **Mã đăng ký bean** cho container biết có bean nào và cách tạo, liên kết chúng.
- **Runtime hints** mô tả thêm các khả năng phải được Native Image giữ lại, như constructor được gọi qua reflection, JDK proxy, resource hoặc serialization.
- **GraalVM reachability analysis** dùng mã ứng dụng, mã AOT và metadata để xác định những phần cần đóng gói vào native executable.

Một bean đã được đăng ký đúng **không bảo đảm** mọi reflection do chính bean đó sử dụng đều hoạt động. Ví dụ, `PaymentService` có thể được tạo thành công, nhưng một thư viện bên trong service dùng `Class.forName` với tên class từ request vẫn có thể thiếu metadata trong bản native.

## 8. Cấu hình, profile và điều kiện tại build time

Spring AOT phân tích context theo **môi trường xử lý AOT**. Điều này quan trọng với `@Profile`, `@ConditionalOnProperty`, `@ConditionalOnClass` và các điều kiện auto-configuration.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    @Profile("dev")
    PaymentGateway devGateway() {
        return new LocalPaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway prodGateway() {
        return new RemotePaymentGateway();
    }
}
~~~

Nếu xử lý AOT diễn ra với profile `prod`, cấu trúc bean được sinh ra có thể khác với khi xử lý bằng profile `dev`. **Đừng mặc định đổi `spring.profiles.active` tại lúc chạy executable native sẽ tạo ra các bean đã bị loại khỏi quá trình xử lý AOT.** Cần lựa chọn profile, thuộc tính và điều kiện build phù hợp với cách triển khai, sau đó kiểm thử trên đúng artifact đã tạo.

Phân biệt hai nhóm cấu hình:

1. **Cấu hình ảnh hưởng cấu trúc bean**: thay đổi ứng viên, điều kiện có bean, loại bean hoặc cơ chế đăng ký. Nhóm này phải được đánh giá cẩn thận trong bước AOT.
2. **Giá trị được bean đọc trong runtime**: ví dụ URL dịch vụ, timeout hay credential được cung cấp khi chạy. Tùy cách ứng dụng sử dụng, các giá trị này vẫn có thể thay đổi mà không cần thay cấu trúc bean.

Không có quy tắc “mọi cấu hình Spring Boot bị đóng băng khi build”. Điều cần kiểm tra là **giá trị đó có tham gia quyết định cấu trúc context mà AOT đã sinh mã hay không**.

## 9. Quan sát mã AOT trong dự án

Với dự án Spring Boot và build plugin tương ứng, có thể yêu cầu Spring xử lý AOT mà chưa cần hoàn tất native compilation:

~~~bash
# Maven: Spring Boot Maven Plugin
./mvnw spring-boot:process-aot

# Gradle: Spring Boot Gradle Plugin
./gradlew processAot
~~~

Trên Windows, dùng wrapper tương ứng `mvnw.cmd` hoặc `gradlew.bat`. Khi dùng các goal/task trên, cần đảm bảo Spring Boot plugin và phiên bản Java đã được cấu hình tương thích. Các thư mục thường gặp:

| Build tool | Vị trí generated sources thường gặp |
|---|---|
| Maven | `target/spring-aot/main/sources` |
| Gradle | `build/generated/aotSources` |

Tên thư mục và cấu trúc đầu ra cụ thể có thể tùy phiên bản hoặc cấu hình build. Trong những nguồn sinh, hãy tìm các class hỗ trợ `BeanDefinitions`, `BeanFactoryRegistrations`, việc tạo `BeanInstanceSupplier` và mã khởi tạo `ApplicationContext`.

Một quy trình đọc generated sources có ích:

1. Xác nhận bean `paymentGateway` và `paymentService` xuất hiện trong kết quả phân tích AOT.
2. Tìm supplier hoặc factory method dùng để tạo từng bean.
3. Xem dependency `PaymentGateway` được cấp cho `PaymentService` như thế nào.
4. So sánh với những khai báo `@Qualifier`, `@Profile`, scope và `@Lazy` có trong source.
5. Nếu không thấy bean mong đợi, kiểm tra phạm vi scan, điều kiện cấu hình và môi trường xử lý AOT trước khi kết luận công cụ sinh mã sai.

**Không sửa trực tiếp file generated sources.** Chúng sẽ được sinh lại ở lần build kế tiếp. Nếu cần thay đổi, hãy chỉnh source configuration hoặc cơ chế AOT extension rồi chạy lại quá trình xử lý.

## 10. Từ mã AOT đến GraalVM Native Image

Khi mục tiêu là chạy native, các lệnh build thông dụng (với native build plugin/profile đã được cấu hình) là:

~~~bash
# Maven
./mvnw -Pnative native:compile

# Gradle
./gradlew nativeCompile
~~~

Quy trình native build sử dụng đầu ra AOT cùng mã ứng dụng để GraalVM phân tích khả năng truy cập. Có ba lớp kiểm tra khác nhau:

| Mức kiểm tra | Chứng minh được điều gì? | Chưa đủ để kết luận điều gì? |
|---|---|---|
| `process-aot` thành công | Spring đã sinh được mã AOT theo môi trường xử lý | Ứng dụng native chắc chắn biên dịch được |
| Native compilation thành công | GraalVM sinh được executable từ tập mã và metadata | Mọi endpoint và mọi nhánh nghiệp vụ đều hoạt động |
| Kiểm thử executable native | Những luồng đã chạy có kết quả quan sát được đúng | Những luồng chưa được test cũng tương thích |

Vì vậy, với ví dụ thanh toán, cần kiểm tra ít nhất: context khởi động, bean `paymentService` được tạo, dependency đúng implementation, phương thức `pay()` trả kết quả mong đợi và các profile được hỗ trợ hoạt động trên artifact tương ứng.

Có thể bổ sung integration test hoặc smoke test gọi endpoint, nhưng trọng tâm là **chạy cùng các trường hợp trên JVM và native** để phát hiện khác biệt do AOT hoặc metadata.

## 11. Lỗi thường gặp khi liên kết bean qua AOT

| Dấu hiệu | Khả năng cần kiểm tra | Hướng khắc phục |
|---|---|---|
| `NoSuchBeanDefinitionException` chỉ xảy ra khi chạy native | Bean không thuộc cấu trúc được phân tích AOT hoặc bị điều kiện/profile loại | Xem môi trường build, điều kiện và generated registrations |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng kiểu nhưng thiếu cách phân biệt | Kiểm tra `@Qualifier`, `@Primary` và định nghĩa bean |
| Không tạo được bean vì constructor/method không truy cập được | Injection hoặc thư viện cần reflective access mà metadata chưa đủ | Xem exception, đường tạo bean và runtime hints liên quan |
| Bean được tạo nhưng thiếu resource/template khi xử lý | Resource chưa được đóng gói trong image | Kiểm tra resource hints và đường dẫn classpath |
| Đăng ký bean động hoạt động trên JVM nhưng không có trong native | Hành vi đăng ký xảy ra sau thời điểm AOT phân tích hoặc thiếu hỗ trợ AOT | Chuyển tập bean về cấu hình xác định được tại build hoặc viết tích hợp AOT phù hợp |
| Chuyển profile lúc chạy không tạo được bean kỳ vọng | Profile hoặc điều kiện cấu trúc đã được quyết định trong xử lý AOT | Build theo profile mục tiêu và kiểm thử từng cấu hình hỗ trợ |

Không nên chữa mọi lỗi bằng cách “giữ hết reflection”: lỗi bean có thể bắt nguồn từ điều kiện, quan hệ dependency, qualifier hoặc đăng ký động, không chỉ từ reflection metadata. Luôn đọc stack trace, so sánh context JVM và native, rồi khoanh vùng theo từng bước.

## 12. Thực hành: chủ động dự đoán đồ thị bean

Hãy mở rộng ví dụ bằng một implementation `RemotePaymentGateway` và hai bean có tên `localGateway`, `remoteGateway`. `PaymentService` sử dụng `@Qualifier("localGateway")`. Sau đó:

1. Vẽ sơ đồ các bean và dependency dự kiến khi bật profile `dev`.
2. Chạy `process-aot`, kiểm tra mã đăng ký được sinh có bean cần thiết và điểm cấp dependency phù hợp.
3. Thử bỏ `@Qualifier` khi tồn tại hai bean cùng kiểu, quan sát lỗi hoặc kết quả chọn ứng viên theo những cơ chế ưu tiên thực tế của Spring.
4. Thêm `@Lazy` vào `PaymentService` và phân biệt **thời điểm đăng ký định nghĩa** với **thời điểm tạo instance** bằng log trong constructor.
5. Build native và chạy lại các trường hợp hợp lệ; nếu thấy khác JVM, lần lượt kiểm tra cấu trúc bean đã được AOT tạo, metadata cần thiết và môi trường build.

Kết quả mong đợi là người học có thể trả lời chính xác: “Spring đã **biết cách tạo bean** từ khi build, nhưng **bean được tạo lúc nào** còn phụ thuộc vào container, scope và nhu cầu runtime.”

## 13. Ghi nhớ

Trong Spring Boot Native Image, sinh mã bean bằng Spring AOT phục vụ ba mục đích liên quan: **đăng ký rõ cấu trúc bean**, **cung cấp đường tạo instance có thể phân tích được** và **thể hiện cách giải quyết dependency**. Quá trình này giảm phần khám phá động khi khởi động và giúp GraalVM nhìn thấy những đường gọi Java cần thiết.

Tuy nhiên, Spring AOT không thay thế IoC container, không buộc mọi singleton được tạo tại build time và không tự giải quyết mọi reflection của ứng dụng. Một bản native đáng tin cậy cần có cấu trúc bean được chuẩn bị phù hợp với môi trường triển khai, runtime hints đúng phạm vi và kiểm thử trên executable đã build.
