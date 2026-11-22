# Đọc startup log và tìm nguyên nhân gốc trong chuỗi exception

Khi một ứng dụng Spring Boot không khởi động được, log thường hiển thị nhiều lớp thông tin: phiên bản, profile đang hoạt động, quá trình tạo bean, cấu hình database, web server, stack trace và exception lồng nhau. Đọc từ đầu đến cuối rồi sửa dòng code đầu tiên nhìn thấy trong stack trace thường dẫn đến chẩn đoán sai.

Cách làm hiệu quả là **đọc log theo cấu trúc và lần theo chuỗi exception từ lỗi được báo ra đến nguyên nhân sâu hơn**, đồng thời đối chiếu với những dòng log ngay trước thời điểm startup thất bại. Exception ngoài cùng thường cho biết Spring thất bại ở công đoạn nào; exception bên trong có thể chỉ ra nguyên nhân cụ thể như thiếu bean, sai kiểu cấu hình, database không kết nối được hoặc thiếu class trên runtime classpath.

Bài học trình bày cách nhận biết mốc startup, phân biệt exception ngoài cùng/cause/root cause/suppressed exception, đọc stack trace, xử lý các lỗi bean/configuration/database/port/classpath, sử dụng `--debug` và logging level, rồi xác nhận nguyên nhân bằng một lần chạy có kiểm soát.

Mục tiêu không phải thuộc lòng mọi exception class. Mục tiêu là biết **đặt đúng câu hỏi ở đúng lớp của lỗi**.

## 1. Startup log cho biết điều gì?

Khi gọi:

~~~java
SpringApplication.run(Application.class, args);
~~~

Spring Boot thực hiện nhiều bước trước khi ứng dụng sẵn sàng nhận request. Tùy ứng dụng, quá trình có thể gồm:

1. Chuẩn bị Environment và property sources.
2. Xác định profile active.
3. Tạo và refresh ApplicationContext.
4. Đăng ký, khởi tạo và inject bean.
5. Áp dụng bean post-processors, proxy và lifecycle callbacks.
6. Khởi động web server nếu có web stack.
7. Chạy ApplicationRunner/CommandLineRunner.
8. Phát tín hiệu ứng dụng đã sẵn sàng.

Không phải ứng dụng nào cũng có cùng các bước. Ứng dụng command-line không cần web server; ứng dụng reactive và servlet có những chi tiết lifecycle khác nhau.

### 1.1. Một startup log giản lược

~~~text
 :: Spring Boot ::                (v3.x.x)

2026-11-13 09:00:00.100  INFO 12345 --- [main]
com.example.Application : Starting Application using Java 21

2026-11-13 09:00:00.250  INFO 12345 --- [main]
com.example.Application : The following 1 profile is active: "dev"

2026-11-13 09:00:01.100  INFO 12345 --- [main]
o.s.b.w.embedded.tomcat.TomcatWebServer :
Tomcat initialized with port 8080 (http)

2026-11-13 09:00:01.700  INFO 12345 --- [main]
o.s.b.w.embedded.tomcat.TomcatWebServer :
Tomcat started on port 8080 (http)

2026-11-13 09:00:01.720  INFO 12345 --- [main]
com.example.Application :
Started Application in 1.8 seconds
~~~

Hãy nhận biết thời gian, level, process/thread, logger, profile, port và dòng xác nhận startup. Format chính xác thay đổi theo Spring Boot version và logging configuration; không nên phụ thuộc vào một vị trí cột cố định.

### 1.2. Startup log không chỉ là stack trace

Log còn có thể chứa warning về cấu hình deprecated, profile/property source, condition evaluation, database connection, server port, external service và lifecycle callback.

Những dòng ngay trước exception đầu tiên thường cung cấp bối cảnh quan trọng. Ví dụ, log cho thấy profile `prod` đang active có thể giải thích tại sao ứng dụng dùng database endpoint khác lúc chạy local.

### 1.3. Warning không nhất thiết là nguyên nhân

Một warning có thể xuất hiện gần lỗi nhưng không gây startup failure. Ví dụ Hibernate cảnh báo một setting deprecated, rồi DataSource thất bại vì sai host. Hãy xác định exception nào khiến startup abort trước khi sửa warning không liên quan.

## 2. Nhận biết Failure Analysis của Spring Boot

Spring Boot thường hiển thị một khối báo lỗi:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Web server failed to start. Port 8080 was already in use.

Action:

Identify and stop the process that's listening on port 8080
or configure this application to listen on another port.
~~~

Khối này thuộc cơ chế **Failure Analysis**. Nó thường gồm:

- **Description:** điều kiện hoặc thao tác thất bại.
- **Action:** hướng xử lý được gợi ý.
- **Exception:** stack trace có thể được in kèm tùy cấu hình.

### 2.1. Description và Action là điểm bắt đầu

`Port 8080 was already in use` khá cụ thể. Nhưng thông báo:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
~~~

chỉ cho biết DataSource chưa được cấu hình thành công. Cần kiểm tra JDBC dependency, profile, property và cấu hình DataSource tùy chỉnh.

Action hữu ích nhưng không thay thế việc xác minh trong chính ứng dụng.

### 2.2. Không phải exception nào cũng có Failure Analysis

Spring Boot có các FailureAnalyzer cho nhiều tình huống quen thuộc. Với exception tùy chỉnh hoặc lỗi không được nhận diện, bạn có thể chỉ thấy stack trace. Không có khối Description/Action không có nghĩa là không có nguyên nhân gốc.

### 2.3. Một exception có thể được in nhiều lần

Framework, application logger, launcher hoặc test runner có thể cùng in một failure. Đừng đếm số lần xuất hiện rồi kết luận có nhiều lỗi độc lập. Hãy đối chiếu timestamp, thread, exception type và cause chain.

## 3. Đọc log theo thứ tự nào?

Một trình tự thực tế:

1. Tìm `APPLICATION FAILED TO START` hoặc error đầu tiên dẫn tới lần startup abort.
2. Đọc Description/Action nếu có.
3. Xem những dòng log ngay trước lỗi để biết ứng dụng đang khởi tạo thành phần nào.
4. Xác định exception ngoài cùng.
5. Lần qua từng `Caused by`.
6. Tìm frame thuộc package ứng dụng trong stack trace liên quan.
7. Đối chiếu với property, dependency, profile hoặc môi trường được nhắc đến.
8. Thay đổi một yếu tố có cơ sở và chạy lại để xác nhận.

Không nên bắt đầu bằng cách đọc hàng trăm frame khi chưa hiểu exception chain. Trước hết cần biết **exception nào đang được báo**, sau đó mới tìm nơi phát sinh.

### 3.1. Lưu đủ log

Chỉ gửi dòng:

~~~text
Caused by: java.net.ConnectException: Connection refused
~~~

thì người nhận chưa biết component nào kết nối, host/port nào, lỗi xảy ra lúc startup hay trong request, exception nằm dưới bean nào và profile nào đang active.

Khi chia sẻ log, giữ một đoạn có context, toàn bộ cause chain và các frame liên quan. Che credential, token, session ID, dữ liệu cá nhân và thông tin nội bộ nhạy cảm.

## 4. Exception ngoài cùng, cause và root cause

Java exception có thể bọc exception khác. Một tầng framework bắt exception thấp hơn, thêm ngữ cảnh rồi ném exception mới kèm cause.

~~~text
UnsatisfiedDependencyException:
Error creating bean with name 'orderController'

Caused by: BeanCreationException:
Error creating bean with name 'orderService'

Caused by: IllegalStateException:
Payment endpoint is not configured
~~~

Có thể đọc thành:

- Spring không tạo được `orderController` vì dependency không sẵn sàng.
- Dependency đó liên quan tới `orderService`.
- Trong lúc tạo service, code hoặc cấu hình phát hiện endpoint thanh toán chưa được thiết lập.

Exception ngoài cùng mô tả lỗi ở ranh giới container; exception sâu hơn thường đưa thêm chi tiết cụ thể.

### 4.1. getCause()

Trong Java, exception có thể giữ exception gốc bằng `Throwable.getCause()`:

~~~java
Throwable cause = exception.getCause();
~~~

Một chuỗi cause có thể gồm nhiều tầng:

~~~text
Exception A
    |
    +-- cause: Exception B
                 |
                 +-- cause: Exception C
                              |
                              +-- cause: Exception D
~~~

Mỗi dòng `Caused by:` trong stack trace đánh dấu một exception được liên kết làm cause của exception phía trên.

### 4.2. Root cause thường sâu nhất, nhưng không phải quy tắc tuyệt đối

Trong chuỗi bọc đơn giản, exception sâu nhất thường có message cụ thể. Tuy nhiên, không phải cứ chọn cause sâu nhất là tìm đúng thứ cần sửa:

- `IllegalArgumentException` sâu bên trong có thể do dữ liệu đầu vào không hợp lệ.
- `SQLException` sâu nhất có thể chỉ là lỗi truyền tải; nguyên nhân vận hành có thể là database chưa chạy hoặc sai host.
- Exception trong cleanup có thể xuất hiện sau lỗi chính.
- Exception wrapper có thể chứa thông tin quan trọng về bean, property hoặc resource.

Hãy đọc cả chain, message, stack frames và log context. Root cause là **nguyên nhân có bằng chứng tốt nhất giải thích failure**, không phải đơn giản là dòng cuối cùng.

### 4.3. Exception ngoài cùng vẫn quan trọng

Không bỏ qua `UnsatisfiedDependencyException` chỉ vì phía dưới có `IllegalStateException`. Exception ngoài cùng thường cho biết bean nào đang được tạo và dependency nào không resolve được.

## 5. Đọc stack trace và tìm frame ứng dụng

Ví dụ:

~~~text
java.lang.IllegalStateException: Payment endpoint is not configured
    at com.example.payment.PaymentClientProperties.validate(PaymentClientProperties.java:42)
    at com.example.payment.PaymentClient.<init>(PaymentClient.java:27)
    at java.base/jdk.internal.reflect.DirectConstructorHandleAccessor.newInstance(...)
    at java.base/java.lang.reflect.Constructor.newInstance(...)
    at org.springframework.beans.BeanUtils.instantiateClass(...)
    at org.springframework.beans.factory.support.SimpleInstantiationStrategy.instantiate(...)
    ...
~~~

Mỗi frame `at ...` cho biết một method nằm trên call stack khi exception được tạo.

### 5.1. Tìm frame đầu tiên thuộc code ứng dụng

Trong ví dụ, `PaymentClientProperties.validate(PaymentClientProperties.java:42)` là frame đầu tiên thuộc package ứng dụng. Mở đúng file/dòng trong revision đã chạy và xem điều kiện nào ném exception.

Những frame tiếp theo thuộc reflection và Spring Framework, cho biết lỗi xảy ra trong quá trình Spring tạo bean.

### 5.2. Frame đầu tiên không luôn là nơi cần sửa

Nếu exception được ném từ thư viện:

~~~text
at com.vendor.sdk.HttpTransport.open(HttpTransport.java:88)
~~~

nguyên nhân có thể nằm ở URL, credential, DNS, TLS hoặc network bên ngoài, chứ không phải code thư viện.

Nếu frame đầu tiên là `java.net.Socket.connect`, tìm frame caller thuộc ứng dụng để biết adapter/component nào yêu cầu kết nối.

### 5.3. Frame cuối thường là infrastructure

Các frame sâu hơn có thể là reflection, dependency injection, servlet container hoặc thread runner. Chúng cho biết đường đi qua framework nhưng thường không chỉ ra cấu hình nghiệp vụ cần sửa.

Tuy vậy, frame Spring có thể xác nhận lỗi phát sinh khi bind property, tạo bean hoặc refresh context.

### 5.4. Dòng file và số dòng

`PaymentClientProperties.java:42` hữu ích khi source đúng revision đang chạy. Nếu code đã thay đổi sau khi log được tạo, số dòng có thể không còn khớp. Artifact không có debug information đầy đủ cũng có thể chỉ hiện class/method.

## 6. Suppressed exception và lỗi cleanup

Java hỗ trợ **suppressed exceptions**, thường gặp khi một exception khác xảy ra trong lúc đóng resource hoặc cleanup.

~~~java
try (InputStream input = resource.getInputStream()) {
    parse(input);
}
~~~

Nếu `parse(input)` ném exception và `close()` cũng thất bại, lỗi close có thể được gắn vào exception chính:

~~~text
java.io.IOException: Failed to parse catalog
    at com.example.catalog.CatalogLoader.load(CatalogLoader.java:51)
    Suppressed: java.io.IOException: Failed to close resource
        at com.example.catalog.CustomResource.close(CustomResource.java:18)
~~~

### 6.1. Suppressed không giống cause

- **Cause:** giải thích exception hiện tại được tạo ra do exception khác.
- **Suppressed:** exception phụ xảy ra trong lúc một exception khác đang được xử lý.

Khi tìm lỗi chính, đừng nhầm lỗi cleanup thành lỗi ban đầu. Nhưng suppressed exception vẫn đáng xem nếu nó cho thấy resource leak hoặc cleanup failure.

### 6.2. Exception có thể không có cause

Một exception có thể được tạo mà không truyền cause. Khi đó, message và vị trí ném exception trong code là manh mối chính.

### 6.3. Lỗi shutdown có thể xuất hiện sau startup failure

Context refresh thất bại có thể kích hoạt cleanup. Nếu đóng một bean cũng thất bại, log có thể có exception thứ hai. Xem timestamp, thread, cause/suppressed relationship và thông báo shutdown để phân biệt lỗi làm startup dừng với lỗi phát sinh khi dọn dẹp.

## 7. Ví dụ: đọc chuỗi exception từ controller tới property

Giả sử log:

~~~text
APPLICATION FAILED TO START

UnsatisfiedDependencyException:
Error creating bean with name 'invoiceController':
Unsatisfied dependency through constructor parameter 0

Caused by: BeanCreationException:
Error creating bean with name 'invoiceService':
Could not resolve placeholder 'app.tax.rate'

Caused by: PlaceholderResolutionException:
Could not resolve placeholder 'app.tax.rate'
~~~

Cách phân tích:

1. Bean ngoài cùng là `invoiceController`.
2. Controller cần `invoiceService`.
3. Spring không tạo được service.
4. Trong quá trình tạo service, placeholder `app.tax.rate` không được resolve.
5. Kiểm tra property, profile/config source và chính tả tên.

Không sửa controller constructor chỉ vì exception ngoài cùng nhắc tới controller. Controller là nơi Spring phát hiện dependency chain bị đứt.

### 7.1. Kiểm tra cấu hình

Ví dụ YAML:

~~~yaml
app:
  tax:
    rate: 0.08
~~~

Hoặc environment variable:

~~~text
APP_TAX_RATE=0.08
~~~

Cần xác minh property source thực sự được nạp trong môi trường đang chạy. Có file `application-dev.yml` không có nghĩa profile `dev` chắc chắn active.

### 7.2. Xác nhận sau khi sửa

- Chạy lại với cùng command và profile.
- Xác nhận lỗi placeholder biến mất.
- Xác nhận `invoiceService` và `invoiceController` được tạo.
- Nếu xuất hiện lỗi mới, tiếp tục chẩn đoán failure mới.

Một lần startup có thể gặp nhiều vấn đề liên tiếp; sửa một lỗi không bảo đảm các bước sau đều thành công.

## 8. Các exception thường gặp khi startup

| Exception | Thường cho biết |
| --- | --- |
| `UnsatisfiedDependencyException` | Không resolve được dependency của bean |
| `NoSuchBeanDefinitionException` | Không có bean phù hợp |
| `NoUniqueBeanDefinitionException` | Có nhiều bean candidate, không chọn được một |
| `BeanCreationException` | Bean thất bại trong quá trình tạo/khởi tạo |
| `BeanCurrentlyInCreationException` | Có vòng phụ thuộc hoặc bean đang được tạo bị tham chiếu lại |
| `ConfigurationPropertiesBindException` | Binding configuration properties thất bại |
| `BindException` | Dữ liệu không bind được vào target |
| `PortInUseException` | Web server không bind được cổng |
| `ApplicationContextException` | Context không thể khởi động/hoàn tất lifecycle |
| `IllegalStateException` | Trạng thái không phù hợp; cần xem message và vị trí ném |
| `ClassNotFoundException` | Cơ chế load class không tìm thấy class yêu cầu |
| `NoClassDefFoundError` | JVM không thể tìm hoặc sử dụng định nghĩa class lúc runtime |
| `NoSuchMethodError` | Bytecode gọi method không có trong version class runtime |
| `UnsupportedClassVersionError` | Bytecode mới hơn phiên bản JVM đang chạy |

Đây là gợi ý phân loại, không phải quy tắc suy luận tuyệt đối. Luôn đọc message và cause chain.

## 9. Lỗi dependency injection

Ví dụ:

~~~text
UnsatisfiedDependencyException:
Error creating bean with name 'orderController':
Unsatisfied dependency expressed through constructor parameter 0
~~~

Spring đang tạo `orderController` nhưng không thể cung cấp argument tương ứng.

### 9.1. NoSuchBeanDefinitionException

~~~text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentGateway' available
~~~

Kiểm tra:

- Có implementation `PaymentGateway` không?
- Implementation có được đăng ký bằng `@Component`, `@Service` hoặc `@Bean` không?
- Package có nằm trong component scan không?
- Bean có bị `@Profile` hoặc `@ConditionalOnProperty` loại khỏi context không?
- Dependency có ở runtime classpath không?
- Test có đang dùng slice chỉ nạp một phần bean không?

Ví dụ:

~~~java
@Component
public class DefaultPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Nếu class nằm ngoài package scan, annotation một mình không đủ để bean xuất hiện.

### 9.2. NoUniqueBeanDefinitionException

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
stripeGateway, sandboxGateway
~~~

Có hai bean cùng type phù hợp injection point. Có thể dùng `@Primary`, `@Qualifier`, profile/condition hoặc điều chỉnh bean definitions. Không xóa bean chỉ để startup pass nếu cả hai đều cần cho use case khác nhau.

### 9.3. Kiểm tra constructor parameter

Thông báo có thể nêu index hoặc tên parameter. Đối chiếu constructor của bean ngoài cùng với kiểu dependency. Lỗi có thể phát sinh ở một argument sâu hơn trong chain, không nhất thiết ở dependency đầu tiên bạn nhìn thấy.

### 9.4. Kiểm tra bằng context test

Unit test tự tạo service bằng mock không xác minh component scan hoặc bean resolution. Sau khi sửa wiring, dùng context test phù hợp để xác nhận Spring tạo được bean.

## 10. BeanCreationException: xác định bean thất bại

`BeanCreationException` thường kèm tên bean:

~~~text
Error creating bean with name 'dataSource'
~~~

hoặc:

~~~text
Error creating bean with name 'entityManagerFactory'
~~~

Đừng dừng ở exception class. Tìm cause chain và bean cụ thể.

### 10.1. Lỗi trong constructor

~~~java
@Component
public class PaymentClient {

    public PaymentClient(PaymentProperties properties) {
        if (properties.endpoint() == null) {
            throw new IllegalStateException(
                    "Payment endpoint is required"
            );
        }
    }
}
~~~

Nếu constructor kiểm tra cấu hình rồi ném exception, Spring bọc lỗi trong quá trình tạo bean. Kiểm tra giá trị properties mà bean nhận được và nguồn cung cấp giá trị đó.

### 10.2. Lỗi trong @PostConstruct

~~~java
@PostConstruct
void initialize() {
    loadRequiredCatalog();
}
~~~

Nếu `loadRequiredCatalog()` thất bại, bean có thể không hoàn thành initialization. Kiểm tra resource, quyền đọc, đường dẫn và parser error. Đừng tăng timeout hoặc đổi thứ tự bean nếu nguyên nhân là file không tồn tại.

### 10.3. Lỗi dây chuyền từ bean khác

`entityManagerFactory` có thể thất bại vì DataSource; DataSource có thể thất bại vì URL/credentials; connection có thể thất bại vì database chưa chạy. Lần tiếp cause chain thay vì sửa bean ngoài cùng một cách mù quáng.

## 11. Lỗi placeholder và ConfigurationProperties binding

Hai nhóm lỗi cần phân biệt:

- Placeholder không resolve được.
- Property có tồn tại nhưng không convert hoặc vi phạm validation.

### 11.1. Placeholder không resolve

~~~text
Could not resolve placeholder 'app.mail.endpoint'
~~~

Kiểm tra tên property, file được nạp, profile active, environment variable, dấu chấm/dấu gạch nối và nguồn cấu hình thực tế.

Nếu property bắt buộc, fail fast có ý nghĩa. Nếu optional, cung cấp default có chủ đích thay vì nuốt lỗi.

### 11.2. Binding sai kiểu

~~~text
Failed to bind properties under 'app.payment.timeout'
to java.time.Duration
~~~

Ví dụ cấu hình không hợp lệ:

~~~yaml
app:
  payment:
    timeout: someday
~~~

Java khai báo `Duration` nhưng Binder không thể chuyển `someday` thành khoảng thời gian. Một giá trị hợp lệ có thể là:

~~~yaml
app:
  payment:
    timeout: 5s
~~~

Đọc property path, target type và value. Không đổi field thành `String` chỉ để startup không báo lỗi nếu nghiệp vụ cần `Duration`.

### 11.3. Binding thành công nhưng validation thất bại

~~~text
Binding validation errors on app.payment
  Field error in object 'app.payment' on field 'maxAttempts':
  rejected value [0]; must be greater than or equal to 1
~~~

Giá trị `0` chuyển được thành `int` nhưng vi phạm `@Min(1)`. Đây là validation failure, không phải conversion failure.

### 11.4. ConfigurationPropertiesBindException

Tìm prefix và field lỗi trong nested cause. Những thông tin quan trọng gồm property name, value, kiểu Java, conversion hay validation và nguồn property nếu log cung cấp.

### 11.5. Profile là bằng chứng quan trọng

Nếu log cho biết profile `prod` active trong khi bạn mong property từ `application-dev.yml`, hãy xác nhận profile và run configuration trước khi sửa Java.

## 12. DataSource và database connection

Một startup failure thường gặp:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
~~~

Một tình huống khác:

~~~text
CannotGetJdbcConnectionException:
Failed to obtain JDBC Connection

Caused by: SQLException:
Connection refused
~~~

Trường hợp đầu thường là thiếu cấu hình DataSource phù hợp; trường hợp sau cho biết ứng dụng đã thử lấy connection nhưng thất bại.

### 12.1. Kiểm tra theo lớp

1. JDBC/JPA driver có trên runtime classpath không?
2. `spring.datasource.url` có đúng không?
3. Username/password có được truyền đúng không?
4. Database service có đang chạy không?
5. Host/port truy cập được từ môi trường chạy app không?
6. Database/schema có tồn tại không?
7. User có quyền kết nối và truy cập schema không?
8. TLS, certificate hoặc network policy có yêu cầu riêng không?

### 12.2. Phân biệt các loại lỗi kết nối

- `Connection refused` thường cho biết TCP connection không được chấp nhận tại host/port.
- `Access denied` hoặc authentication failure thường cho biết server đã nhận kết nối nhưng từ chối credential/quyền.
- `UnknownHostException` thường liên quan DNS/hostname.
- Timeout có thể liên quan network, firewall, server không phản hồi hoặc timeout config.

Kiểm tra từ đúng môi trường chạy ứng dụng. Kết nối thành công trên laptop không chứng minh container hoặc CI runner cũng truy cập được.

### 12.3. Không log password để debug

Chỉ log host/database/schema và trạng thái cấu hình nếu cần; không in password, token hoặc connection string chứa secret.

## 13. Port đã được sử dụng

Ví dụ:

~~~text
Web server failed to start. Port 8080 was already in use.
~~~

Có thể một process khác đang listen port, hoặc instance cũ vẫn còn chạy.

Port có thể được cấu hình bằng:

~~~properties
server.port=8080
~~~

hoặc:

~~~yaml
server:
  port: 8080
~~~

Có thể bị override bởi:

~~~text
SERVER_PORT=9090
~~~

hoặc command-line:

~~~bash
java -jar app.jar --server.port=9090
~~~

Kiểm tra cấu hình có hiệu lực, không chỉ một file `application.yml`.

Nếu server chưa bind được port, sửa controller mapping không giải quyết được lỗi socket. Với test cần server thật, `@SpringBootTest(webEnvironment = RANDOM_PORT)` giúp giảm xung đột port giữa các test, nhưng không thay thế việc cấu hình port production đúng.

## 14. Lỗi classpath và tương thích dependency

### 14.1. ClassNotFoundException

~~~text
ClassNotFoundException:
com.vendor.payment.PaymentClient
~~~

Kiểm tra dependency có trong runtime classpath, scope có phải chỉ compile/test, artifact đã đóng gói đúng, package/class name có thay đổi và module có được build/publish không.

### 14.2. NoClassDefFoundError

~~~text
NoClassDefFoundError:
com/vendor/payment/PaymentClient
~~~

Đây là lỗi linkage/runtime khác với `ClassNotFoundException`. Nó cũng có thể xuất hiện khi class trước đó khởi tạo thất bại, ví dụ do `ExceptionInInitializerError`. Tìm lần xuất hiện đầu tiên của lỗi khởi tạo nếu có.

### 14.3. NoSuchMethodError

~~~text
NoSuchMethodError:
com.vendor.api.ClientBuilder.timeout(...)
~~~

Code được compile với API có method đó, nhưng runtime nạp version class không có method tương ứng. Nguyên nhân thường là dependency version conflict hoặc compile/runtime classpath khác nhau.

Kiểm tra dependency tree, version thực tế trong artifact, dùng Boot BOM/dependency management nhất quán và xác nhận đúng artifact đang chạy.

### 14.4. UnsupportedClassVersionError

Class được compile cho class-file version mới hơn JVM runtime hỗ trợ. Kiểm tra JDK build, JDK chạy, Maven/Gradle toolchain, target/release và runtime image. Đây có thể là lỗi xảy ra trước khi Spring tạo ApplicationContext.

## 15. Đọc log theo thời gian: lỗi đầu tiên và lỗi dây chuyền

Một lỗi ban đầu có thể tạo ra nhiều thông báo tiếp theo:

~~~text
Failed to initialize DataSource
    |
    v
EntityManagerFactory bean cannot be created
    |
    v
OrderRepository cannot be initialized
    |
    v
OrderService dependency cannot be resolved
    |
    v
OrderController dependency cannot be resolved
    |
    v
APPLICATION FAILED TO START
~~~

Nếu chỉ nhìn dòng cuối, bạn có thể nghĩ controller là vấn đề. Nhưng nguyên nhân khởi đầu là DataSource.

### 15.1. Exception đầu tiên trong toàn file không nhất thiết là root cause

Log có thể chứa exception đã được xử lý, retry thất bại rồi thành công hoặc warning từ một thành phần không làm startup abort.

Hãy xác định exception đầu tiên **dẫn đến startup abort**, không phải exception đầu tiên xuất hiện trong bất kỳ ngữ cảnh nào.

### 15.2. Phân biệt lỗi khởi động và lỗi shutdown

Context refresh thất bại có thể kích hoạt cleanup. Nếu đóng bean cũng lỗi, log có thể in exception thứ hai. Xem timestamp, thread, cause/suppressed relationship và thông báo shutdown để phân biệt.

## 16. Tìm frame thuộc code ứng dụng và xác nhận giả thuyết

Ví dụ:

~~~text
BeanCreationException:
Error creating bean with name 'paymentClient'

Caused by: IllegalArgumentException:
Invalid endpoint

    at com.example.payment.PaymentProperties.validate(PaymentProperties.java:38)
    at com.example.payment.PaymentClient.<init>(PaymentClient.java:24)
    at java.base/jdk.internal.reflect...
    at org.springframework.beans.factory.support...
~~~

Thực hiện:

1. Mở `PaymentProperties.java` tại dòng 38.
2. Xác định điều kiện khiến `Invalid endpoint` được ném.
3. Xem giá trị endpoint đến từ đâu.
4. Xác nhận property source/profile thực tế.
5. Chỉ sửa code nếu validation hoặc logic sai; nếu config sai thì sửa nguồn config.
6. Chạy lại với cùng command/profile để xác nhận.

### 16.1. Generated code và proxy

Stack trace có thể chứa class proxy, reflection hoặc generated code. Nếu frame đầu tiên không thuộc source trực tiếp, tìm caller gần nhất thuộc package ứng dụng. Không cần hiểu mọi frame CGLIB/JDK để chẩn đoán một property sai; chỉ dùng chúng khi cần xác nhận proxy/call path.

### 16.2. Stack trace bị rút gọn

Một số logger, test runner hoặc giao diện IDE có thể rút gọn stack trace. Nếu không thấy đầy đủ `Caused by`, lấy log gốc hoặc bật hiển thị stack trace đầy đủ trước khi kết luận.

Không đoán nguyên nhân chỉ từ một dòng tóm tắt.
## 17. Dùng --debug và Condition Evaluation Report

Khi nghi ngờ một auto-configuration không được áp dụng hoặc bị back off, hãy chạy:

~~~bash
java -jar app.jar --debug
~~~

Với Maven development run:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Với Gradle:

~~~bash
./gradlew bootRun --args='--debug'
~~~

`--debug` yêu cầu Spring Boot tạo **Condition Evaluation Report** với thông tin về những auto-configuration condition khớp hoặc không khớp. Nó không phải công tắc bật mọi logging ở mức DEBUG và cũng không tự sửa bean bị thiếu.

### 17.1. Đọc positive matches và negative matches

Condition report thường phân nhóm:

- **Positive matches:** cấu hình/condition được áp dụng.
- **Negative matches:** cấu hình/condition không được áp dụng, kèm điều kiện không thỏa mãn.
- **Exclusions:** auto-configuration bị loại trừ.
- **Unconditional classes:** một số cấu hình không phụ thuộc điều kiện thông thường.

Ví dụ minh họa:

~~~text
DataSourceAutoConfiguration matched:
   - @ConditionalOnClass found required classes
   - @ConditionalOnMissingBean did not find any beans

DataSourceAutoConfiguration.PooledDataSourceConfiguration did not match:
   - @ConditionalOnProperty (spring.datasource.type) did not find property
~~~

Thông điệp cụ thể phụ thuộc version và condition. Đừng kỳ vọng mọi report có đúng các dòng ví dụ trên.

### 17.2. Condition report trả lời câu hỏi nào?

Nó hữu ích khi cần biết:

- Auto-configuration có được xem xét không?
- Class/dependency cần thiết có trên classpath không?
- Property condition có thỏa mãn không?
- Bean do người dùng định nghĩa có khiến Boot back off không?
- Cấu hình có bị exclude không?

Nó không thay thế stack trace của lỗi trong một bean đã được đăng ký. Nếu DataSource bean được tạo nhưng kết nối thất bại, condition report có thể cho biết tại sao auto-configuration được bật; cause chain mới chỉ ra lỗi kết nối cụ thể.

### 17.3. Không bật --debug liên tục trong mọi môi trường

Condition report có thể tạo nhiều log và làm output khó đọc. Bật khi chẩn đoán auto-configuration, lưu kết quả, rồi quay về mức log phù hợp.

## 18. Điều chỉnh logging level đúng phạm vi

Spring Boot dùng logging system được cấu hình bởi ứng dụng. Có thể điều chỉnh level bằng properties:

~~~properties
logging.level.root=INFO
logging.level.com.example=DEBUG
logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Hoặc YAML:

~~~yaml
logging:
  level:
    root: INFO
    com.example: DEBUG
    org.springframework.boot.autoconfigure: DEBUG
~~~

### 18.1. Root level và package level

- `logging.level.root` đặt level mặc định cho logger nếu không có cấu hình cụ thể hơn.
- `logging.level.com.example` tăng chi tiết cho package ứng dụng.
- `logging.level.org.springframework.boot.autoconfigure` hữu ích khi cần quan sát auto-configuration.

Không nhất thiết bật `DEBUG` cho toàn bộ `org.springframework`. Điều đó có thể tạo lượng log lớn và che thông tin cần tìm.

### 18.2. TRACE không phải lúc nào cũng tốt hơn DEBUG

TRACE có thể tạo nhiều chi tiết nội bộ. Hãy bật logger cụ thể theo component đang điều tra và chỉ trong khoảng thời gian cần thiết.

### 18.3. Logging level không tạo thêm exception cause

Nếu code log exception mà không truyền throwable:

~~~java
log.error("Startup failed: {}", exception.getMessage());
~~~

stack trace không tự xuất hiện chỉ vì đổi level. Muốn ghi throwable:

~~~java
log.error("Startup failed", exception);
~~~

Trong code production, nên giữ exception object khi log lỗi cần chẩn đoán. Tránh chỉ log `getMessage()` rồi vứt bỏ cause chain.

### 18.4. Không log cùng một exception ở mọi tầng

Nếu tầng thấp đã log exception đầy đủ, tầng cao lại log cùng exception nhiều lần, log sẽ trùng lặp. Hãy chọn nơi có đủ context để log một lần có ý nghĩa; những tầng khác có thể bổ sung context hoặc rethrow theo contract.

## 19. Kiểm tra profile và property source có hiệu lực

Khi log nhắc tới property, đừng chỉ nhìn file YAML trong editor. Spring Boot có nhiều nguồn cấu hình và thứ tự ưu tiên.

Những nguồn thường gặp:

- File cấu hình như `application.properties` hoặc `application.yml`.
- File profile-specific như `application-prod.yml`.
- OS environment variables.
- Java system properties.
- Command-line arguments.
- Config data/import hoặc property sources được ứng dụng thêm vào.

### 19.1. Xác nhận profile active

Startup log thường hiển thị profile active. Có thể đặt profile bằng:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

hoặc environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Nếu property chỉ được khai báo trong profile khác, Spring không tự dùng nó khi profile đó không active.

### 19.2. Giá trị command-line có thể override file

~~~bash
java -jar app.jar --server.port=9090
~~~

có thể khiến ứng dụng bind port 9090 dù file YAML ghi 8080. Khi đọc log port, hãy kiểm tra command-line và environment của process thực tế.

### 19.3. Kiểm tra property an toàn

Có thể log một giá trị cấu hình không nhạy cảm trong component liên quan hoặc dùng test để xác nhận binding. Không in toàn bộ Environment hay mọi configuration properties nếu chúng có thể chứa secret.

Actuator có endpoint như `env` và `configprops` ở những cấu hình phù hợp. Chúng có thể tiết lộ giá trị cấu hình; chỉ expose trong môi trường kiểm soát, áp dụng authentication/authorization và masking đúng cách. Không công khai endpoint này chỉ để tiện debug.

### 19.4. Đừng nhầm property thiếu với property bị override

Nếu property có trong file nhưng runtime vẫn nhận giá trị khác, có thể nguồn có precedence cao hơn đã override. Tìm source có hiệu lực thay vì thêm một bản sao property vào nhiều file khác nhau.

## 20. Bật log dependency/configuration khi cần

Nếu lỗi liên quan bean scan hoặc component registration, có thể tạm tăng log:

~~~properties
logging.level.org.springframework.context.annotation=DEBUG
logging.level.org.springframework.beans.factory.support=DEBUG
~~~

Nếu lỗi liên quan web server, chọn logger tương ứng với server/framework đang dùng. Nếu lỗi liên quan Hibernate/JPA, bật logger phù hợp phiên bản, nhưng tránh bật SQL bind values có dữ liệu nhạy cảm trên môi trường dùng dữ liệu thật.

### 20.1. Log phải phục vụ một giả thuyết

Ví dụ giả thuyết: “Bean payment adapter không được scan vì nằm ngoài package root.”

Có thể kiểm tra component scan/bean definitions. Không cần bật TRACE toàn bộ Spring để xác minh một class cụ thể.

### 20.2. Tăng log có thể ảnh hưởng timing

DEBUG có thể làm startup chậm hơn hoặc thay đổi timing trong hệ thống nhiều thread. Nếu điều tra race condition, ghi nhận rằng việc bật log có thể tác động timing; một lần chạy debug không phải bằng chứng tuyệt đối cho mọi tình huống.

## 21. Phân tích ví dụ: thiếu bean payment gateway

Giả sử startup log:

~~~text
APPLICATION FAILED TO START

UnsatisfiedDependencyException:
Error creating bean with name 'checkoutController':
Unsatisfied dependency expressed through constructor parameter 0

Caused by: UnsatisfiedDependencyException:
Error creating bean with name 'checkoutService':
Unsatisfied dependency expressed through constructor parameter 1

Caused by: NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentGateway' available
~~~

### 21.1. Đọc từ ngoài vào trong

- `checkoutController` cần `CheckoutService`.
- `CheckoutService` cần một dependency ở constructor parameter 1.
- Dependency đó là `PaymentGateway`.
- Context không có bean phù hợp.

Vậy lỗi là bean registration/selection, không phải controller request mapping.

### 21.2. Kiểm tra source

Có interface:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}
~~~

Implementation:

~~~java
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Class chưa có `@Component` và chưa có `@Bean` factory method. Nếu không có cách đăng ký khác, Spring không tự tạo bean chỉ vì class implements interface.

Có thể đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}
~~~

Ví dụ chỉ minh họa bean registration; implementation thật có thể cần HTTP client, credentials và cấu hình riêng.

### 21.3. Xác nhận bằng context test

Một test context có thể assert:

~~~java
assertThat(context).hasSingleBean(PaymentGateway.class);
~~~

Hoặc khởi động ứng dụng với cấu hình test và kiểm tra bean được resolve.

### 21.4. Nếu có hai implementation?

Nếu context báo `NoUniqueBeanDefinitionException`, hãy xem candidate names. Chọn implementation qua `@Primary`, `@Qualifier` hoặc conditions/profile có chủ đích.

## 22. Phân tích ví dụ: database không kết nối được

Log:

~~~text
BeanCreationException:
Error creating bean with name 'entityManagerFactory'

Caused by: PersistenceException:
Unable to build Hibernate SessionFactory

Caused by: JDBCConnectionException:
Unable to obtain JDBC Connection

Caused by: ConnectException:
Connection refused
~~~

### 22.1. Đọc tầng lỗi

- `entityManagerFactory` không tạo được.
- Hibernate không xây được SessionFactory.
- Hibernate không lấy được JDBC connection.
- TCP connection bị từ chối.

Điểm cần điều tra là database endpoint/network/readiness, không phải entity mapping trước tiên.

### 22.2. Kiểm tra endpoint runtime

Xác định host/port mà process đang sử dụng. Nếu chạy trong Docker, `localhost` thường trỏ tới chính container, không tự trỏ tới host hoặc container database khác.

Kiểm tra DNS/network từ chính container/service runtime. Đừng chỉ thử từ máy phát triển.

### 22.3. Xác nhận sau sửa

Khi database sẵn sàng hoặc URL đúng:

- Lỗi `Connection refused` biến mất.
- DataSource có thể lấy connection.
- Hibernate tiếp tục khởi tạo.
- Nếu có lỗi schema/mapping tiếp theo, xử lý như một failure mới.

Không đổi entity class để giải quyết TCP connection failure.

## 23. Phân tích ví dụ: property bind được nhưng sai quy tắc nghiệp vụ

Giả sử log:

~~~text
ConfigurationPropertiesBindException:
Error creating bean with name 'paymentProperties'

Caused by: BindValidationException:
Binding validation errors on app.payment

Field error in object 'app.payment'
on field 'maxAttempts':
rejected value [0]
must be greater than or equal to 1
~~~

Giá trị `0` chuyển được thành kiểu số nguyên nhưng vi phạm validation.

Nếu policy yêu cầu ít nhất một lần thử, sửa cấu hình:

~~~yaml
app:
  payment:
    max-attempts: 3
~~~

Nếu domain thực sự cho phép `0` nghĩa là không retry, constraint `@Min(1)` có thể đang sai và cần sửa code/contract. Đừng thay cấu hình chỉ để vượt qua validation nếu business meaning yêu cầu giá trị khác.

## 24. Phân tích ví dụ: port 8080 đã được sử dụng

Log:

~~~text
APPLICATION FAILED TO START

Web server failed to start. Port 8080 was already in use.
~~~

Kiểm tra:

1. Có instance cũ của app đang chạy không?
2. Có process khác dùng port 8080 không?
3. Run configuration có khởi động hai instance không?
4. Có cấu hình `server.port` hoặc `SERVER_PORT` override không?
5. Với test, có thể dùng random port không?

Trên Windows, có thể dùng PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
~~~

Sau đó xác định process:

~~~powershell
Get-Process -Id <OwningProcess>
~~~

Trên Linux/macOS có thể dùng `lsof` hoặc `ss` nếu có. Lệnh cụ thể tùy hệ điều hành.

Đừng dừng một process không rõ chủ sở hữu chỉ để giải phóng port. Xác định process và mục đích trước.

## 25. Chẩn đoán dependency version conflict

Ví dụ:

~~~text
NoSuchMethodError:
com.vendor.sdk.ClientBuilder.timeout(...)
~~~

Đây thường là dấu hiệu code compile với một API nhưng runtime nạp version khác.

### 25.1. Xem dependency tree

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Có thể thu hẹp dependency cụ thể để xem module nào kéo version khác vào graph.

### 25.2. Kiểm tra artifact thực tế

Nếu chạy executable JAR, kiểm tra dependency được đóng gói bên trong, không chỉ dependency tree của IDE. Artifact cũ hoặc deployment image cũ có thể vẫn chứa version không mong muốn.

### 25.3. Dùng BOM/dependency management

Với Spring Boot, ưu tiên dependency management tương thích với Boot version đang dùng. Không override riêng lẻ nhiều module Spring hoặc thư viện nền tảng nếu chưa kiểm tra compatibility.

## 26. Workflow chẩn đoán có thể lặp lại

**Bước 1 — Ghi nhận môi trường chạy.** Lưu Java version, Spring Boot version, command, profile, working directory và cách chạy (IDE, Maven, Gradle, executable JAR, container).

**Bước 2 — Xác định failure đầu tiên làm startup abort.** Tìm `APPLICATION FAILED TO START`, Failure Analysis hoặc exception đầu tiên dẫn tới context fail.

**Bước 3 — Đọc exception ngoài cùng.** Ghi bean/component và thao tác thất bại.

**Bước 4 — Lần theo cause chain.** Đọc từng `Caused by`, message và suppressed exceptions; không chỉ copy dòng cuối.

**Bước 5 — Tìm frame thuộc ứng dụng.** Mở source đúng revision và kiểm tra method/dòng được chỉ ra.

**Bước 6 — Đối chiếu môi trường và cấu hình.** Xác nhận profile, property source, dependency graph, port, network và filesystem.

**Bước 7 — Viết giả thuyết có thể kiểm chứng.** Ví dụ “profile prod không cung cấp app.payment.endpoint” thay vì “Spring bị lỗi”.

**Bước 8 — Thay đổi một yếu tố có cơ sở.** Tránh đổi nhiều property, dependency và code cùng lúc.

**Bước 9 — Chạy lại cùng điều kiện.** Giữ command, profile và môi trường giống lần trước, trừ yếu tố đang thử nghiệm.

**Bước 10 — Xác nhận bằng dấu hiệu cụ thể.** Lỗi cũ biến mất, bean được tạo, server bind thành công hoặc startup hoàn tất.

**Bước 11 — Chạy test phù hợp.** Context test cho wiring/configuration, integration test cho database/network, unit test cho logic.

**Bước 12 — Ghi lại kết luận và giới hạn.** Nêu nguyên nhân, bằng chứng, thay đổi và cách xác nhận.

### 26.1. Ví dụ một giả thuyết tốt

Không rõ ràng:

> Spring Boot không chạy được.

Có thể kiểm chứng:

> Context không tạo được PaymentClient vì property app.payment.endpoint không resolve trong profile staging. Startup log xác nhận profile staging; cause chain kết thúc ở placeholder resolution. Sau khi cung cấp property trong nguồn cấu hình của profile, bean được tạo và ứng dụng startup thành công.

Giả thuyết tốt nêu component, điều kiện, bằng chứng và cách xác nhận.

## 27. Sử dụng log trong IDE và terminal

### 27.1. IDE

Khi chạy từ IDE:

- Lưu toàn bộ console output, không chỉ exception cuối.
- Kiểm tra run configuration và environment variables.
- Kiểm tra profile được truyền vào.
- Xác nhận module/dependency classpath.
- Nếu console cắt log, lưu ra file hoặc mở output đầy đủ.
- Ghi nhận JDK IDE sử dụng, không chỉ JDK mặc định trong terminal.

### 27.2. Maven

~~~bash
mvn spring-boot:run
~~~

Truyền argument debug:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Xem dependency:

~~~bash
mvn dependency:tree
~~~

### 27.3. Gradle

~~~bash
./gradlew bootRun --args='--debug'
~~~

Xem runtime dependency:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

### 27.4. Executable JAR

~~~bash
java -jar app.jar --debug
~~~

Ghi nhận đúng file JAR và Java runtime. Nếu lỗi chỉ xuất hiện sau packaging, kiểm tra artifact, runtime classpath, external files và container configuration.

### 27.5. Giữ nguyên điều kiện khi tái hiện

Một lần chạy local với profile `dev` không xác nhận lỗi ở profile `prod`. Một lần chạy từ IDE không xác nhận executable JAR. Hãy tái hiện trong điều kiện gần môi trường phát sinh lỗi nhất có thể.

## 28. Logging an toàn và hữu ích

Startup logs có thể chứa database URL, access token, API key, request payload, dữ liệu cá nhân, hostname và topology nội bộ.

Khi tăng logging:

1. Chỉ bật logger cần thiết.
2. Không log secret hoặc raw credential.
3. Mask dữ liệu nhạy cảm trong cấu hình/payload.
4. Không expose Actuator env/configprops công khai.
5. Tắt log chi tiết sau khi chẩn đoán nếu không cần.
6. Tuân theo retention/access policy của hệ thống log.

### 28.1. Log exception với throwable

Nên dùng:

~~~java
log.error("Could not initialize payment client", exception);
~~~

thay vì chỉ:

~~~java
log.error("Could not initialize payment client: {}",
        exception.getMessage());
~~~

Cách thứ nhất giữ stack trace và cause chain trong logger hỗ trợ throwable. Trước khi log exception có thể chứa URL/credential, cần đảm bảo thông tin nhạy cảm đã được xử lý.

### 28.2. Đừng nuốt exception

Đoạn code:

~~~java
try {
    initialize();
} catch (Exception exception) {
    log.error("Initialization failed");
}
~~~

đã làm mất cause và có thể khiến ứng dụng tiếp tục trong trạng thái không hợp lệ.

Nếu initialization là bắt buộc, hãy rethrow exception hoặc bọc nó mà vẫn giữ cause:

~~~java
throw new IllegalStateException(
        "Could not initialize payment client",
        exception
);
~~~

Nếu failure có thể phục hồi, hãy định nghĩa retry/fallback rõ ràng và log outcome.

## 29. Custom FailureAnalyzer cho starter/module

Một starter có thể muốn cung cấp thông báo startup dễ hiểu cho lỗi cấu hình riêng. Spring Boot có extension point `FailureAnalyzer`.

Ví dụ minh họa:

~~~java
public class MissingCatalogFailureAnalyzer
        extends AbstractFailureAnalyzer<MissingCatalogException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            MissingCatalogException cause) {

        return new FailureAnalysis(
                "Required catalog resource was not found.",
                "Provide the catalog under the configured classpath location.",
                cause
        );
    }
}
~~~

`MissingCatalogException` là exception do module định nghĩa. Cách đăng ký analyzer phụ thuộc cơ chế được Spring Boot version của project hỗ trợ.

### 29.1. Analyzer không thay thế exception chain

FailureAnalyzer tạo thông điệp hướng dẫn dễ đọc, nhưng vẫn nên giữ exception gốc làm cause để người vận hành điều tra.

### 29.2. Khi nào nên tạo?

- Starter có cấu hình bắt buộc.
- Lỗi domain lặp lại và có action sửa cụ thể.
- Người dùng thư viện thường gặp lỗi setup khó hiểu.
- Có thể đưa ra action đáng tin cậy dựa trên exception type.

Không tạo analyzer chung chung cho mọi exception; thông báo sai có thể dẫn người dùng đi sai hướng.

## 30. Những lỗi thường gặp khi đọc startup log

### 30.1. Chỉ đọc exception ngoài cùng

Thấy `UnsatisfiedDependencyException` rồi sửa controller. Hãy lần qua cause chain để xác định bean hoặc property sâu hơn.

### 30.2. Chỉ đọc dòng Caused by cuối cùng

Bỏ mất ngữ cảnh bean, property hoặc thao tác ở exception wrapper. Hãy đọc toàn bộ chain và đối chiếu stack frames.

### 30.3. Sửa frame đầu tiên mà không kiểm tra message

Frame có thể thuộc thư viện/framework hoặc chỉ là caller. Mở source đúng revision và xem điều kiện ném exception.

### 30.4. Nhầm warning với startup failure

Sửa warning deprecated không liên quan. Hãy xác định exception thực sự làm context abort.

### 30.5. Chỉ kiểm tra application.yml

Runtime có thể dùng environment variable, command-line hoặc profile khác. Xác nhận profile và property source có hiệu lực; không log secret.

### 30.6. Tăng toàn bộ logging lên TRACE

Log quá lớn và khó tìm failure. Bật DEBUG/TRACE cho package/component cụ thể trong thời gian ngắn.

### 30.7. Chạy lại bằng môi trường khác

Lỗi xuất hiện trong container nhưng chỉ thử local IDE. Hãy tái hiện cùng artifact, Java version, profile, environment và network boundary.

### 30.8. Đổi nhiều thứ cùng lúc

Không biết thay đổi nào giải quyết lỗi. Tạo một giả thuyết, thay một yếu tố, chạy lại và ghi nhận.

### 30.9. Nuốt exception hoặc chỉ log message

Cause chain và stack trace bị mất. Log throwable ở tầng có context phù hợp và rethrow nếu startup không thể tiếp tục an toàn.

### 30.10. Cho rằng root cause luôn là dòng cuối

Suppressed/cleanup exception hoặc wrapper context có thể quan trọng hơn. Đọc cấu trúc exception và timeline.

### 30.11. Công khai Actuator env/configprops

Có thể lộ secret/configuration. Chỉ expose trong môi trường kiểm soát, bảo vệ endpoint và masking đúng cách.

### 30.12. Sửa code khi lỗi thuộc môi trường

Đổi service/bean để xử lý port conflict, DNS hoặc database chưa chạy. Phân biệt lỗi code, configuration, dependency và infrastructure trước khi sửa.

## 31. Mẫu ghi nhận một startup failure

~~~text
Context
- Application / module:
- Commit or build:
- Java version:
- Spring Boot version:
- Run command:
- Active profiles:
- Runtime environment:

Observed failure
- Startup phase:
- Outer exception:
- Bean/component:
- First application frame:
- Deepest relevant cause:
- Relevant log lines before failure:

Evidence
- Property/dependency/port/resource involved:
- What was checked:
- What was ruled out:

Hypothesis
- Most likely root cause:
- Evidence supporting it:

Verification
- Change made:
- Same command/profile rerun:
- Old exception gone:
- Application startup result:
- Remaining issue:
~~~

Đây là mẫu để tránh thiếu bối cảnh. Không cần điền trường không liên quan; không đính kèm credential hoặc secret.

## 32. Bài thực hành

### Bài A: Thiếu property

Tạo bean yêu cầu `app.payment.endpoint`. Chạy ứng dụng khi chưa cung cấp property và đọc exception chain. Bổ sung property vào đúng profile, chạy lại với cùng command và xác nhận bean được tạo.

### Bài B: Thiếu bean

Tạo controller phụ thuộc `PaymentGateway` nhưng không đăng ký implementation. Quan sát `UnsatisfiedDependencyException` và `NoSuchBeanDefinitionException`. Đăng ký bean bằng `@Component` hoặc `@Bean` rồi kiểm tra context.

### Bài C: Bean ambiguity

Đăng ký hai implementation cùng interface. Quan sát `NoUniqueBeanDefinitionException`. Dùng `@Primary` hoặc `@Qualifier` để giải quyết theo ý đồ ứng dụng.

### Bài D: Binding sai kiểu

Khai báo `Duration` nhưng cung cấp giá trị không hợp lệ. Phân biệt conversion failure với validation failure do `@Min` hoặc constraint tương ứng.

### Bài E: Database unavailable

Cấu hình JDBC URL tới host/port không có database đang lắng nghe. Đọc cause chain và phân biệt `Connection refused` với authentication failure.

### Bài F: Port conflict

Chạy hai instance dùng cùng port. Xác định process đang listen và thay đổi cấu hình có chủ đích. Không dừng process không rõ nguồn gốc.

### Bài G: Dependency conflict

Tạo tình huống runtime classpath không tương thích trong môi trường thử nghiệm. Quan sát `NoSuchMethodError`, xem dependency tree và xác định version được đóng gói.

### Bài H: Condition report

Chạy ứng dụng với `--debug`. Tìm một auto-configuration trong positive/negative matches và giải thích condition khiến nó được áp dụng hoặc bỏ qua.

### Bài I: Frame ứng dụng đầu tiên

Tạo constructor ném `IllegalStateException` với message cụ thể. Đọc stack trace, tìm file/dòng đầu tiên thuộc package ứng dụng và lần ngược giá trị gây lỗi.

### Bài J: Suppressed exception

Tạo resource mà parse và close đều có thể ném exception. Quan sát sự khác nhau giữa cause và suppressed exception.

### Bài K: Ghi nhận root cause

Chọn một startup failure trong môi trường test, điền mẫu ở phần 31. Nêu bằng chứng xác nhận nguyên nhân và cách kiểm tra lại.

## 33. Câu hỏi tự kiểm tra

**1. Vì sao không nên chỉ đọc exception ngoài cùng?**

Vì nó thường mô tả lỗi ở ranh giới framework/container; cause sâu hơn có thể chỉ ra property, dependency hoặc thao tác cụ thể thất bại.

**2. `Caused by` biểu thị điều gì?**

Một exception được liên kết làm nguyên nhân của exception hiện tại.

**3. Suppressed exception khác cause thế nào?**

Suppressed là lỗi phụ xảy ra trong lúc xử lý một exception khác, thường gặp khi cleanup resource.

**4. Root cause có luôn là exception sâu nhất không?**

Không. Cần đọc toàn bộ chain, timeline, suppressed exceptions và context.

**5. Frame đầu tiên thuộc package ứng dụng có ích gì?**

Nó thường chỉ ra method/file/dòng nơi code ứng dụng tham gia vào call path gây lỗi.

**6. `UnsatisfiedDependencyException` yêu cầu kiểm tra điều gì?**

Bean ngoài cùng, constructor parameter, bean candidate, component scan, profile, condition và dependency registration.

**7. `NoUniqueBeanDefinitionException` khác `NoSuchBeanDefinitionException` thế nào?**

Một lỗi không tìm thấy candidate phù hợp; lỗi kia có nhiều candidate phù hợp nhưng không chọn được một bean duy nhất.

**8. `--debug` giúp ích điều gì?**

Nó yêu cầu Spring Boot tạo Condition Evaluation Report để xem auto-configuration matches, non-matches và exclusions.

**9. `--debug` có tự bật mọi logger ở DEBUG không?**

Không. Nó không thay thế việc cấu hình logging level cho logger cụ thể.

**10. Vì sao phải kiểm tra active profile?**

Profile quyết định cấu hình/bean nào được kích hoạt; property mong đợi có thể nằm trong profile không active.

**11. `Connection refused` khác authentication failure thế nào?**

Connection refused thường xảy ra ở bước TCP; authentication failure thường xảy ra sau khi đã kết nối tới server nhưng credential/quyền bị từ chối.

**12. `NoSuchMethodError` thường gợi ý điều gì?**

Compile-time và runtime class version/API không tương thích, thường do dependency conflict hoặc artifact cũ.

**13. Vì sao một startup failure có thể tạo nhiều exception tiếp theo?**

Bean phụ thuộc nhau theo chuỗi; một bean thất bại khiến bean phụ thuộc cũng không thể tạo.

**14. Có nên log toàn bộ Environment khi debug không?**

Không nếu có khả năng chứa secret. Hãy kiểm tra giá trị không nhạy cảm và bảo vệ/mask nguồn cấu hình.

**15. Điều gì chứng minh giả thuyết root cause?**

Bằng chứng liên kết lỗi với cấu hình/code/môi trường và lần chạy lại trong cùng điều kiện cho thấy lỗi cũ biến mất sau thay đổi có chủ đích.

## 34. Kết luận

Đọc startup log hiệu quả là quá trình **tách lớp và xác minh nguyên nhân**, không phải tìm một dòng exception rồi sửa ngay. Exception ngoài cùng thường cho biết Spring thất bại khi tạo bean, bind cấu hình hoặc khởi động server. Cause chain cung cấp nguyên nhân sâu hơn; stack trace chỉ ra call path và frame thuộc code ứng dụng; những dòng log trước failure cho biết profile, dependency và trạng thái môi trường.

Khi chẩn đoán, hãy bắt đầu từ Failure Analysis và exception làm startup abort; đọc toàn bộ `Caused by` và suppressed exceptions; tìm frame ứng dụng và kiểm tra đúng revision; đối chiếu active profile, property source, runtime dependency, database, port và môi trường chạy. Dùng `--debug` cho condition evaluation và bật logging level có chọn lọc. Cuối cùng, đưa ra giả thuyết có thể kiểm chứng, thay đổi một yếu tố rồi chạy lại trong điều kiện tương đương.

Một startup failure thường là biểu hiện cuối của lỗi ở tầng thấp hơn: property thiếu, bean chưa đăng ký, dependency không tương thích, resource không đọc được hoặc dịch vụ ngoài chưa sẵn sàng. Khi đọc đúng cấu trúc log và kiểm tra từng giả thuyết bằng bằng chứng, bạn có thể tìm nguyên nhân gốc nhanh hơn và tránh sửa nhầm những thành phần chỉ xuất hiện trong chuỗi exception.


