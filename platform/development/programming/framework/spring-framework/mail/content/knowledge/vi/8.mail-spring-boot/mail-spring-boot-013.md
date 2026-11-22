# Kiểm tra điều kiện auto-configuration khi bean không xuất hiện

## 1. Hiện tượng: đã thêm Spring Mail nhưng không inject được JavaMailSender

Trong ứng dụng **Spring Boot** sử dụng **Spring Framework Mail**, đoạn code gửi email thường inject **JavaMailSender**:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final JavaMailSender mailSender;

    public NotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Dùng mailSender để gửi thông báo...
}
~~~

Nếu ứng dụng khởi động nhưng Spring không tạo được bean, log có thể chứa lỗi:

~~~text
Parameter 0 of constructor in ...NotificationService required
a bean of type 'org.springframework.mail.javamail.JavaMailSender'
that could not be found.
~~~

Thông điệp này chỉ mô tả **điểm thất bại khi dependency injection**: Spring cần một bean đúng kiểu nhưng không tìm thấy. Nó **không khẳng định** nguyên nhân là “chưa cài thư viện”, cũng không đồng nghĩa SMTP server đang từ chối kết nối. Để giải quyết, phải kiểm tra **điều kiện auto-configuration**, **classpath**, **configuration properties**, **các bean đã có** và **context đang được khởi tạo**.

Trong Spring Boot, **auto-configuration** là cơ chế tự đăng ký bean dựa trên những điều kiện có thể kiểm tra được tại runtime. Nó không phải cam kết rằng “chỉ cần thêm starter là chắc chắn có JavaMailSender”.

### Các loại tình huống cần phân biệt

| Hiện tượng | Ý nghĩa ban đầu | Hướng điều tra |
|---|---|---|
| Không có bean JavaMailSender, ứng dụng lỗi khi inject | Bean chưa được đăng ký với kiểu cần thiết | Điều kiện tạo bean, cấu hình, custom bean, test context |
| Có bean MailSender nhưng không có JavaMailSender | Có implementation của interface cha nhưng không đáp ứng API MIME | Kiểm tra bean tùy biến đang chặn auto-config |
| Có JavaMailSender nhưng gửi mail thất bại | Bean đã tạo; lỗi xảy ra khi kết nối/gửi | SMTP host, TLS, AUTH, mạng, quota, địa chỉ nhận |
| Ứng dụng lỗi ngay khi tạo mail sender | Điều kiện có thể đã match nhưng cấu hình/khởi tạo thất bại | Exception nguyên nhân, JNDI, binding, bean factory |
| Lỗi chỉ xảy ra trong test | Test tạo context khác runtime thật | Test slice, mock, @ActiveProfiles, @Import |
| Bean tồn tại nhưng inject bị ambiguous | Nhiều bean cùng kiểu, Spring không chọn được | @Primary, @Qualifier, cấu hình bean |

**Không có bean** khác với **có bean nhưng không kết nối SMTP được**. Mở kết nối, đăng nhập và thực sự phát thư là những bước sau khi Spring context đã chọn xong bean.

## 2. Auto-configuration của Spring Mail được kích hoạt bằng điều kiện nào?

Trong Spring Boot 3.x, cơ chế thường liên quan đến **MailSenderAutoConfiguration** thuộc package **org.springframework.boot.autoconfigure.mail**. Khi sử dụng **spring-boot-starter-mail**, thư viện cần thiết cho Spring Mail và Jakarta Mail thường được đưa vào classpath qua dependency.

Mô hình điều kiện khái quát:

~~~mermaid
flowchart TD
    A[Spring Boot đánh giá MailSenderAutoConfiguration] --> B{Các class Mail/Jakarta Mail cần thiết có trên classpath?}
    B -- Không --> X[Không áp dụng cấu hình mail]
    B -- Có --> C{Đã có bean MailSender?}
    C -- Có --> Y[Back off: ưu tiên bean do ứng dụng cung cấp]
    C -- Không --> D{Có spring.mail.host hoặc spring.mail.jndi-name phù hợp?}
    D -- Không --> Z[Không tạo sender vì thiếu điều kiện cấu hình]
    D -- Có --> E[Chọn cấu hình theo host hoặc JNDI]
    E --> F[Khởi tạo JavaMailSenderImpl]
    F --> G[JavaMailSender có thể được inject]
~~~

Sơ đồ thể hiện đường xử lý thông dụng của Spring Boot 3.3.x; chi tiết annotation và nhánh con nên đối chiếu với **phiên bản Spring Boot thực tế** của ứng dụng. Điều kiện căn bản thường bao gồm:

1. **Classpath có các kiểu cần thiết**: thành phần Spring Mail, Jakarta Mail và các lớp mail mà auto-configuration tham chiếu.
2. **Chưa có bean MailSender**: Spring Boot không tự tạo sender mặc định để ghi đè một sender đã được ứng dụng hoặc thư viện khác đăng ký.
3. **Có nguồn cấu hình gửi mail**: thường là **spring.mail.host**, hoặc một **spring.mail.jndi-name** hợp lệ khi dùng mail session qua JNDI.
4. **Không bị exclude auto-configuration**: cấu hình Boot không bị loại bỏ bằng annotation hoặc property.
5. **Context thực sự nạp auto-configuration**: ví dụ ứng dụng Spring Boot thông thường; một test slice hoặc context tối giản có thể không nạp cấu hình đó.

Trong cấu trúc auto-configuration của Spring Boot, **MailSenderAutoConfiguration** dùng các conditional annotation, bật binding **MailProperties** và import các nhánh cấu hình dành cho host/port hoặc JNDI. Có thể tra các lớp **MailSenderPropertiesConfiguration** và **MailSenderJndiConfiguration** khi cần hiểu nhánh nào được chọn.

### Phân biệt @ConditionalOnClass và @ConditionalOnMissingBean

**@ConditionalOnClass** kiểm tra sự hiện diện của class trên classpath, ví dụ kiểu thuộc Spring Mail hoặc Jakarta Mail. Thiếu thư viện là nguyên nhân trực tiếp khiến điều kiện không match.

**@ConditionalOnMissingBean** kiểm tra bean đã được đăng ký trong context. Nếu đã có một bean phù hợp, Boot chủ động **back off**: không đăng ký bean mặc định nữa. Đây thường là hành vi có chủ đích, không phải lỗi của Spring.

Với Spring Mail, việc back off trên **MailSender** có một hệ quả quan trọng: một bean custom chỉ triển khai **MailSender** nhưng không triển khai **JavaMailSender** có thể khiến JavaMailSender mặc định không được tạo, trong khi service lại yêu cầu inject đúng **JavaMailSender**.

## 3. Kiểm tra dependency và classpath trước tiên

Với Spring Boot và Gradle, cách phổ biến để bật mail support là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
~~~

**Starter** mang các dependency hỗ trợ gửi mail. Đó không phải một bean JavaMailSender trực tiếp và cũng không chứa sẵn SMTP host hoặc credential để gửi email thật.

Một số lỗi classpath:

- Chỉ có **spring-context-support** nhưng thiếu Jakarta Mail implementation cần thiết.
- Thêm dependency ở **testImplementation** thay vì runtime **implementation**, khiến ứng dụng thật không thấy các class.
- Loại trừ transitively một dependency Jakarta Mail hoặc activation cần thiết trong cấu hình build.
- Trộn **javax.mail** của hệ sinh thái cũ với **jakarta.mail** của Spring Boot 3.x, khiến import hoặc loại đối tượng không tương thích.
- Project nhiều module không khai báo dependency mail cho module thực sự chạy; dependency nằm ở một module khác nhưng không nằm trong runtime classpath của ứng dụng.

Spring Boot 3.x sử dụng hệ namespace **jakarta.mail.\***. Ví dụ **jakarta.mail.internet.MimeMessage** được sử dụng cùng JavaMailSender. Code cũ import **javax.mail.internet.MimeMessage** không thể chỉ thay tên package một cách tùy ý nếu dependency vẫn thuộc thế hệ cũ; cần đồng bộ thư viện, phiên bản Spring và cách sử dụng API.

Khi kiểm tra classpath, hãy dựa trên **dependency graph của module chạy**, không chỉ nhìn thấy một dòng dependency trong file khác. Ví dụ các lệnh Gradle mang tính tham khảo:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-mail --configuration runtimeClasspath
~~~

Tên project, runtime classpath và cú pháp lệnh phụ thuộc cấu trúc Gradle; trong dự án đa module cần chọn đúng project. Với Maven có thể dùng **mvn dependency:tree**. Đây là các lệnh để developer dùng khi chẩn đoán, không phải một phần của việc tự động tạo bean.

Nếu condition report ghi **@ConditionalOnClass did not find required class**, cần xác định class thiếu rồi sửa dependency thực sự. Thêm một property **spring.mail.host** sẽ không sửa lỗi thiếu class.

## 4. Kiểm tra spring.mail.host và spring.mail.jndi-name

Khi dùng gửi mail qua SMTP host, một cấu hình cơ bản:

~~~yaml
# application.yml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

**spring.mail.host** là một property quan trọng để kích hoạt nhánh cấu hình SMTP thông thường. Các property **username**, **password**, **port** và **properties.mail.smtp.\*** điều chỉnh cách kết nối/gửi; chúng **không tự thay thế** điều kiện về host trong trường hợp dùng nhánh host-based.

Ví dụ cấu hình dễ nhầm:

~~~yaml
spring:
  mail:
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Nếu không có **spring.mail.host** ở bất kỳ nguồn cấu hình hiệu lực nào và cũng không dùng JNDI, Spring Boot có thể **không đăng ký mail sender** vì thiếu điều kiện bắt đầu. Khi đó lỗi inject JavaMailSender có thể xuất hiện dù dependency starter hoàn toàn đúng.

### Dùng JNDI mail session

Trong một số application server, JavaMail Session được cung cấp qua **JNDI**. Cấu hình có thể là:

~~~yaml
spring:
  mail:
    jndi-name: mail/Session
~~~

Khi chọn JNDI, việc tìm Session phụ thuộc môi trường cung cấp JNDI resource. Ứng dụng Spring Boot chạy standalone thông thường không tự có resource **mail/Session**. Nếu cấu hình JNDI mà không có JNDI resource, quá trình khởi tạo bean có thể thất bại; trường hợp đó phải phân biệt với tình huống **auto-configuration hoàn toàn không match**.

**Không cấu hình đồng thời host và JNDI một cách tùy tiện.** Hãy chọn cách quản lý Session rõ ràng; khi dùng JNDI, các thiết lập tương ứng trên Session do application server cung cấp có thể quyết định hành vi thay vì các thuộc tính SMTP trên Spring Boot.

### Các cách viết sai thường gặp

| Cấu hình | Vấn đề |
|---|---|
| **spring.mail.hostname** | Không phải khóa Spring Boot chuẩn cho host; cần **spring.mail.host** |
| **mail.host** ở cấp root | Không được MailProperties bind thành **spring.mail.host** |
| **spring.mail.smtp.host** | Không giống thuộc tính **spring.mail.host** của Spring Boot |
| Chỉ đặt **spring.mail.port** | Không đủ để kích hoạt nhánh host-based |
| Chỉ đặt **spring.mail.username** | Không đủ để kích hoạt nhánh host-based |
| Đặt **spring.mail.host** trong profile không active | Property chưa hiện diện ở context đang khởi động |
| Đặt biến môi trường ở terminal khác/container khác | Process Java có thể không nhận được giá trị |

Có thể viết SMTP property trực tiếp dưới **spring.mail.properties** cho Jakarta Mail, nhưng cần phân biệt **property dùng để Boot quyết định tạo bean** và **property được chuyển cho JavaMail khi đã có bean**. Việc đặt **spring.mail.properties.mail.smtp.host** không thay thế chắc chắn cho **spring.mail.host** trong điều kiện auto-configuration.

## 5. Active profile và nguồn property hiệu lực

Giả sử file:

~~~yaml
# application-dev.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
~~~

Nếu ứng dụng không kích hoạt profile **dev**, các giá trị đó không nhất thiết được load. Chạy ứng dụng:

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

hoặc đặt biến môi trường **SPRING_PROFILES_ACTIVE=dev** trong môi trường của tiến trình.

Trong production, cấu hình host có thể được inject qua **SPRING_MAIL_HOST** hoặc một placeholder được bind đến nguồn secret/config. Điểm cần xác minh là **giá trị cuối cùng mà Spring Environment nhìn thấy**, không phải “file đã có một dòng host”.

Một số nguồn gây sai lệch:

- Profile đang active không đúng như dự định.
- File cấu hình nằm ngoài classpath hoặc chưa được đóng gói.
- File hoặc biến môi trường ở container host không được truyền vào container ứng dụng.
- Một property source có độ ưu tiên cao hơn ghi đè giá trị từ YAML.
- Test có **@TestPropertySource**, **@ActiveProfiles**, **@DynamicPropertySource** hoặc config riêng khác runtime.
- Một profile khác đưa **spring.mail.jndi-name** vào khiến nhánh cấu hình được chọn khác kỳ vọng.

Có thể bật thông tin về **active profiles** trong log khởi động; nếu dùng **Actuator env/configprops**, phải giới hạn quyền truy cập và tránh công khai secret. Spring Boot có cơ chế làm mờ hoặc giới hạn hiển thị các giá trị nhạy cảm, nhưng cấu hình bảo mật vẫn thuộc trách nhiệm người vận hành.

## 6. Bean tùy biến khiến auto-configuration chủ động back off

Đây là trường hợp dễ gây nhầm lẫn nhất: dependency và **spring.mail.host** đều đúng, nhưng Spring Boot vẫn không tạo **JavaMailSenderImpl**.

Ví dụ ứng dụng tự khai báo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

@Configuration
public class CustomMailConfig {
    @Bean
    MailSender customMailSender() {
        return new MailSender() {
            @Override
            public void send(SimpleMailMessage message) {
                // Fake/no-op minh họa.
            }

            @Override
            public void send(SimpleMailMessage... messages) {
                // Fake/no-op minh họa.
            }
        };
    }
}
~~~

Vì bean **customMailSender** có kiểu **MailSender**, điều kiện **@ConditionalOnMissingBean(MailSender.class)** có thể không còn thỏa mãn. Khi đó Spring Boot **không tạo JavaMailSender mặc định**. Nhưng service lại yêu cầu kiểu con **JavaMailSender**, nên inject thất bại.

~~~text
CustomMailConfig
  |
  v
MailSender bean tồn tại
  |
  v
MailSenderAutoConfiguration back off
  |
  v
Không có JavaMailSender bean
  |
  v
Injection JavaMailSender thất bại
~~~

Một custom **JavaMailSender** đầy đủ cũng có thể khiến auto-configuration back off. Trong trường hợp đó, nếu service inject JavaMailSender thành công thì không có vấn đề: Boot đang tôn trọng cấu hình của ứng dụng.

### Cách sửa theo nhu cầu thực tế

Nếu chỉ muốn dùng SMTP sender mặc định, **loại bỏ hoặc giới hạn phạm vi bean custom** đang chặn nó. Nếu muốn custom mail sender, hãy đăng ký bean đúng **JavaMailSender** và cung cấp đầy đủ hành vi cần thiết cho MIME và transport, thay vì chỉ implement MailSender khi service cần JavaMailSender.

Trong test, custom fake chỉ nên được đăng ký trong **test context** bằng **@TestConfiguration**, mock bean hoặc profile test rõ ràng. Tránh để fake/no-op MailSender vô tình được quét vào production và làm Boot back off.

### Khi có nhiều bean cùng kiểu

Nếu có nhiều JavaMailSender do ứng dụng tự định nghĩa, Spring có thể báo **NoUniqueBeanDefinitionException** khi inject một bean mà không có qualifier. Lỗi này khác hoàn toàn “bean could not be found”. Cần chọn một sender rõ ràng bằng **@Qualifier**, **@Primary** hoặc một gateway định tuyến, không cố bật auto-configuration để tạo thêm bean thứ ba.
## 7. Đọc Condition Evaluation Report để biết vì sao bean không xuất hiện

**Condition Evaluation Report** là nguồn quan trọng nhất để hiểu auto-configuration có được áp dụng hay không. Spring Boot đánh giá các điều kiện như **@ConditionalOnClass**, **@ConditionalOnBean**, **@ConditionalOnMissingBean**, **@ConditionalOnProperty** hoặc điều kiện tùy chỉnh; report mô tả những cấu hình **matched** và **did not match** cùng lý do.

Trong quá trình chẩn đoán, có thể khởi động ứng dụng với cờ debug:

~~~bash
java -jar app.jar --debug
~~~

Hoặc cấu hình:

~~~yaml
debug: true
~~~

Khi debug được bật, Spring Boot có thể ghi một báo cáo các điều kiện auto-configuration vào log, kể cả lúc quá trình startup gặp lỗi khiến ứng dụng không khởi tạo hoàn chỉnh. Tên mục và văn bản cụ thể có thể khác giữa các phiên bản Spring Boot, vì vậy hãy tìm các mục **MailSenderAutoConfiguration**, **MailSenderPropertiesConfiguration** và **MailSenderJndiConfiguration** thay vì chờ một câu chữ cố định.

Một đoạn report **minh họa**, không phải output chuẩn cần khớp từng ký tự:

~~~text
Negative matches:

MailSenderAutoConfiguration:
   Did not match:
      - No spring.mail.host or spring.mail.jndi-name property found
~~~

Trong tình huống này, thiếu host/JNDI là nguyên nhân chính. Việc cấu hình thêm password hoặc bật **mail.smtp.auth** không thay thế được điều kiện nêu trong report.

Một tình huống khác:

~~~text
Negative matches:

MailSenderAutoConfiguration:
   Did not match:
      - @ConditionalOnMissingBean found bean of type MailSender:
        customMailSender
~~~

Ý nghĩa: Boot nhìn thấy một bean MailSender được đăng ký và **chủ động không tạo sender mặc định**. Việc đi tìm thư viện thiếu có thể không giải quyết được tình huống này.

Một ví dụ khác:

~~~text
Negative matches:

MailSenderAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find required class
        ...
~~~

Khi đó cần kiểm tra **runtime classpath**, starter, dependency exclusion hoặc phiên bản thư viện.

### Khi report cho thấy positive match mà vẫn inject lỗi

**Positive match** không đồng nghĩa bean đã được tạo thành công và sẵn sàng. Chẳng hạn:

- Auto-configuration class match nhưng **nhánh con** tạo bean không match.
- Cấu hình chọn nhánh JNDI nhưng không tìm được mail Session trong JNDI.
- Bean factory method ném exception khi khởi tạo.
- Bean được tạo trong **context khác** với context chứa service cần inject.
- Bean thực tế thuộc kiểu **MailSender** nhưng service yêu cầu **JavaMailSender**.
- Một **BeanDefinition** tồn tại nhưng bị lỗi trong giai đoạn instantiate.

Vì vậy khi xem report, hãy kết hợp với **stack trace gốc**, tên bean trong context và thông điệp lỗi phụ thuộc. Đừng dừng ở một dòng “MailSenderAutoConfiguration matched”.

## 8. Dùng Spring Boot Actuator để quan sát bean và điều kiện

Khi ứng dụng đã khởi động và có Spring Boot Actuator, một số endpoint có thể giúp quan sát cấu hình:

| Endpoint | Thông tin cung cấp | Câu hỏi cần trả lời |
|---|---|---|
| **/actuator/conditions** | Kết quả đánh giá điều kiện auto-configuration | MailSenderAutoConfiguration được áp dụng hay bị loại? |
| **/actuator/beans** | Các bean có trong application context | Có bean JavaMailSender? Bean nằm trong context nào? |
| **/actuator/configprops** | Các configuration properties được bind | MailProperties có giá trị phù hợp không? |
| **/actuator/env** | Các thuộc tính và nguồn cấu hình | spring.mail.host đang lấy từ nguồn nào? |

Không phải endpoint nào cũng mặc định được expose qua HTTP. Có thể cấu hình exposure phù hợp trong môi trường **phát triển hoặc quản trị**:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions,beans,configprops,env
~~~

**Không mở công khai các endpoint cấu hình trong production.** Chúng có thể bộc lộ cấu trúc bean, tên property, endpoint nội bộ hoặc metadata nhạy cảm dù giá trị secret được sanitize. Dùng authentication/authorization, network restriction và cấu hình hiển thị phù hợp; không sao chép dữ liệu secret vào log/ticket khi điều tra.

Nếu application context **không khởi động được**, actuator HTTP chưa sẵn sàng. Khi đó ưu tiên cờ **--debug**, stack trace hoặc kiểm tra bean bằng một bài test/context có thể khởi động một phần.

### Condition report trong một test

Trong bài test dùng Spring Boot, có thể thu kết quả điều kiện ngay từ test context. Ví dụ đọc report từ BeanFactory với điều kiện context đã được khởi tạo:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootTest
class MailConditionsInspectionTest {

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void inspectConditions() {
        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        report.getConditionAndOutcomesBySource()
                .forEach((source, outcomes) -> {
                    if (source.contains("MailSender")) {
                        System.out.println(source + " -> " + outcomes);
                    }
                });
    }
}
~~~

Đoạn này dùng để **quan sát khi chẩn đoán**, không phải assertion ổn định cho CI: việc in object **ConditionAndOutcomes** có thể không phải cách trình bày tối ưu, và tên internal source có thể thay đổi theo Spring Boot version. Khi muốn kiểm tra ràng buộc một cách bền vững, nên assert **bean có/không có** với context được cấu hình rõ ràng thay vì so sánh toàn bộ chuỗi log.

## 9. Đừng nhầm bean chưa đăng ký với kết nối SMTP không thành công

**JavaMailSenderImpl** thường có thể được tạo ra từ host, port, username, password và JavaMail properties mà **chưa thực hiện một lần gửi hay kết nối mạng nào**. Vì vậy:

~~~text
Spring context tạo JavaMailSenderImpl
        |
        v
Bean xuất hiện trong ApplicationContext
        |
        v
Service inject JavaMailSender thành công
        |
        v
JavaMailSender.send(...)
        |
        v
Kết nối SMTP / STARTTLS / AUTH / gửi mail
~~~

Nếu sai mật khẩu SMTP hoặc server không phản hồi, thông thường bean vẫn tồn tại; **send()** mới ném ngoại lệ kết nối, xác thực hoặc gửi thư.

Spring Boot cũng có tùy chọn **spring.mail.test-connection**. Khi được bật, Boot có thể chủ động kiểm tra kết nối mail trong quá trình startup. Nếu SMTP server không thể kết nối, ứng dụng có thể **khởi động thất bại** dù điều kiện tạo bean đã match.

Ví dụ:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    test-connection: true
~~~

Thuộc tính này giúp kiểm tra đường truyền khi khởi động, nhưng có đánh đổi: sự cố SMTP tạm thời có thể làm ứng dụng không sẵn sàng dù các chức năng nghiệp vụ khác không phụ thuộc mail. **test-connection** không phải điều kiện bắt buộc để tạo JavaMailSender và cũng không bảo đảm các email về sau sẽ được phát thành công.

| Lỗi quan sát được | Khả năng liên quan |
|---|---|
| **No qualifying bean of type JavaMailSender** | Bean chưa được tạo/không nằm trong context |
| **MailAuthenticationException** khi gọi send | Credential, token hoặc chính sách SMTP AUTH |
| **MailSendException** khi gọi send | Kết nối, SMTP transaction hoặc một/một số message thất bại |
| **ConnectException / timeout** trong test-connection | Host/port/network/server/TLS ở thời điểm startup |
| **NamingException** khi dùng JNDI | Không tìm được JNDI Session/resource |
| **BeanCreationException** | Bean factory khởi tạo lỗi; cần đọc nested cause |

Nếu console in cả **“No bean found”** và một stack trace phức tạp, hãy xác định **exception gốc đầu tiên** và điều kiện context tương ứng. Những lỗi phụ thuộc xuất hiện sau có thể chỉ là hậu quả.

## 10. Auto-configuration bị exclude hoặc không được nạp

Ngay cả khi classpath và properties hợp lệ, một ứng dụng có thể cố ý tắt MailSenderAutoConfiguration.

Ví dụ:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.mail.MailSenderAutoConfiguration;

@SpringBootApplication(exclude = MailSenderAutoConfiguration.class)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Hoặc bằng configuration property:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.mail.MailSenderAutoConfiguration
~~~

Khi auto-configuration bị exclude, Boot không tự tạo sender qua cấu hình đó, bất kể bạn khai báo **spring.mail.host**. Nếu ứng dụng vẫn cần gửi mail, nó phải đăng ký một sender phù hợp bằng cấu hình khác, hoặc bỏ exclude khi đã xác định đúng yêu cầu.

Ngoài exclude trực tiếp còn có những tình huống:

- Ứng dụng không chạy qua **Spring Boot auto-configuration** thông thường, ví dụ tự tạo một Spring context thuần không bật các auto-config cần thiết.
- Test sử dụng **@ContextConfiguration** với tập @Configuration hạn chế, không chứa cấu hình auto-config.
- Test slice như **@WebMvcTest** chỉ tạo các bean phục vụ lát cắt MVC, không tương đương với context đầy đủ của ứng dụng.
- Một module hoặc library có cấu hình Spring riêng nhưng không phải Boot application context đã nạp auto-config.
- Cấu hình bootstrap riêng hoặc nhiều context cha/con đặt sender ở nơi service không thể nhìn thấy.

Đối với test, **đừng bật toàn bộ auto-configuration chỉ để sửa lỗi mock không xuất hiện** nếu bài test chỉ cần kiểm tra controller/service. Khi cần một mail gateway cho unit test, hãy cung cấp mock hoặc fake thích hợp. Khi cần kiểm tra Boot thật sự tạo sender, hãy dùng một test context có auto-configuration cần thiết và một bộ properties rõ ràng.

## 11. Bean bị thiếu chỉ trong test: xác định đúng loại test context

Ứng dụng chạy bình thường nhưng test báo thiếu JavaMailSender là trường hợp phổ biến. Nguyên nhân thường không nằm ở SMTP, mà vì **test tạo ApplicationContext khác**.

### @SpringBootTest

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = "spring.mail.host=127.0.0.1")
@ActiveProfiles("test")
class MailSenderContextTest {

    @Autowired
    JavaMailSender mailSender;

    @Test
    void contextProvidesMailSender() {
        org.assertj.core.api.Assertions.assertThat(mailSender)
                .isNotNull();
    }
}
~~~

Test này quan sát việc **context tạo sender**, không chủ động gửi thư. Vì JavaMailSenderImpl thường không mở kết nối cho đến khi gửi, có thể dùng host giả để kiểm tra bean nếu **spring.mail.test-connection** không được bật ở nguồn cấu hình có hiệu lực. Nếu test profile có một custom **MailSender** khác, bean mặc định có thể vẫn back off.

### @WebMvcTest và các slice tests

Ví dụ controller inject một service, service inject JavaMailSender:

~~~text
@WebMvcTest
   |
   +-- MVC controller
          |
          v
       Mail service
          |
          v
       JavaMailSender (có thể chưa được tạo trong slice)
~~~

**@WebMvcTest** không tự tạo đầy đủ tất cả dependency của ứng dụng. Khi test controller không yêu cầu gửi mail thật, thường mock **service** hoặc **mail gateway** được controller sử dụng. Ví dụ theo Spring Boot 3.3:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(NotificationController.class)
class NotificationControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    NotificationService notificationService;

    @Test
    void example() {
        // Dùng mvc để kiểm thử HTTP behavior của controller.
    }
}
~~~

Ví dụ giả định **NotificationController** và **NotificationService** thuộc ứng dụng. Nó minh họa cách đặt mock ở **ranh giới phù hợp với mục tiêu của test**; test controller không cần SMTP.

**@MockBean** là annotation được dùng trong Spring Boot 3.3. Với các thế hệ Spring/Boot khác, cơ chế mock trong context có thể thay đổi; hãy dùng API tương ứng với phiên bản dự án.

### Khi muốn mock trực tiếp JavaMailSender

Trong SpringBootTest dùng để kiểm tra service xây dựng nội dung email, có thể đăng ký:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class NotificationServiceTest {
    @MockBean
    private JavaMailSender mailSender;

    @Autowired
    private NotificationService service;

    // Verify service gọi mailSender với message mong đợi.
}
~~~

Khi **@MockBean JavaMailSender** được đăng ký, auto-configuration có thể back off vì context **đã có một sender bean**. Đây là điều bình thường: mock được dùng cho test, không cần thêm JavaMailSenderImpl thật. Nếu kiểm tra condition report, bạn sẽ thấy điều kiện missing bean khác so với runtime mà **không có mock**.

### Một tình huống khác: mock nhầm interface cha

Nếu test chỉ mock **MailSender**, trong khi service inject **JavaMailSender**, auto-configuration có thể không tạo JavaMailSender mặc định vì đã có MailSender. Khi ấy test vẫn thiếu bean JavaMailSender. Hãy mock **đúng interface service yêu cầu** hoặc cấu trúc lại service dùng interface thích hợp.
## 12. Kiểm tra từng điều kiện bằng ApplicationContextRunner

Khi cần hiểu tự động cấu hình có hoạt động theo một bộ thuộc tính cụ thể hay không, **ApplicationContextRunner** từ Spring Boot Test là công cụ hữu ích. Nó tạo **ApplicationContext nhỏ, có kiểm soát**, cho phép bật auto-configuration cần quan sát và kiểm tra bean kết quả.

Ví dụ đơn giản:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.mail.MailSenderAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.mail.javamail.JavaMailSender;

class MailSenderAutoConfigurationConditionsTest {
    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    MailSenderAutoConfiguration.class));

    @Test
    void createsJavaMailSenderWhenHostIsConfigured() {
        contextRunner
                .withPropertyValues("spring.mail.host=localhost")
                .run(context ->
                        assertThat(context).hasSingleBean(
                                JavaMailSender.class));
    }

    @Test
    void doesNotCreateSenderWithoutHostOrJndi() {
        contextRunner
                .run(context ->
                        assertThat(context).doesNotHaveBean(
                                JavaMailSender.class));
    }
}
~~~

Ví dụ giả định **spring-boot-starter-mail** và thư viện **spring-boot-test** nằm trên test runtime classpath, không có nguồn cấu hình bổ sung nào tạo sẵn sender. Đó là lý do hai trường hợp có thể cho kết quả khác nhau. Khi ứng dụng tùy biến **MailSender** hoặc dùng JNDI, cần bổ sung context tương ứng.

Nếu muốn xem chi tiết điều kiện khi dùng runner, có thể gắn **ConditionEvaluationReportLoggingListener** hoặc đọc report từ BeanFactory trong callback. Điều này giúp tìm nguyên nhân tại đúng thời điểm Spring đưa ra quyết định, không cần chạy SMTP thật.

### Ví dụ tự đăng ký bean và quan sát back off

Giả sử một cấu hình test có bean **MailSender** nhưng không có **JavaMailSender**. Sử dụng cùng runner và thêm cấu hình custom bean, có thể xác minh rằng BeanFactory chứa MailSender do ứng dụng cung cấp nhưng không tạo JavaMailSenderImpl mặc định. Quan trọng là cần kiểm tra **đúng kiểu bean**, vì:

~~~text
MailSender là interface cha
          ^
          |
JavaMailSender mở rộng MailSender
          ^
          |
JavaMailSenderImpl implements JavaMailSender
~~~

Một bean JavaMailSender luôn có thể dùng như MailSender, nhưng một implementation MailSender tùy biến không nhất thiết hỗ trợ MimeMessage. Spring Boot không thể suy đoán rằng ứng dụng muốn tự động đổi một MailSender custom thành JavaMailSender.

Không cần viết test chỉ để đếm số điều kiện nếu report đã giải thích rõ nguyên nhân. ApplicationContextRunner hữu ích nhất khi bạn đang **phát triển cấu hình thư viện**, cần kiểm soát nhiều tổ hợp property/bean hoặc muốn đảm bảo auto-configuration custom không vô tình ghi đè bean người dùng.

## 13. Quy trình chẩn đoán từ thông báo lỗi đến nguyên nhân

Với lỗi **No qualifying bean of type JavaMailSender**, có thể đi từ triệu chứng đến nguyên nhân bằng cây quyết định:

~~~mermaid
flowchart TD
    A[Không inject được JavaMailSender] --> B{Đang chạy Spring Boot context nào?}
    B -->|Test slice / context giới hạn| C[Kiểm tra auto-config được nạp và mock đúng kiểu]
    B -->|Ứng dụng Boot đầy đủ| D[Bật condition report]
    D --> E{MailSenderAutoConfiguration được áp dụng?}
    E -->|Không vì classpath| F[Kiểm tra starter / runtime dependencies]
    E -->|Không vì property| G[Kiểm tra spring.mail.host hoặc jndi-name có hiệu lực]
    E -->|Không vì existing bean| H[Kiểm tra bean MailSender tùy biến]
    E -->|Đang bị exclude| I[Gỡ exclude nếu muốn dùng mặc định]
    E -->|Có match| J{Bean JavaMailSender có trong context?}
    J -->|Có| K[Kiểm tra qualifier / injection point / context]
    J -->|Không| L[Kiểm tra nhánh config, bean factory exception, JNDI]
~~~

Một trình tự thực hành ngắn:

1. **Đọc đầy đủ stack trace.** Xác định lỗi thật là không có bean, bean không duy nhất, bean creation thất bại hay lỗi SMTP connection.
2. **Xác định ApplicationContext**: ứng dụng Boot đầy đủ, @SpringBootTest, @WebMvcTest hay Spring context được dựng thủ công.
3. **Bật Condition Evaluation Report** và tìm **MailSenderAutoConfiguration** cùng các nhánh con.
4. **Nếu classpath thiếu**, xem dependency của module chạy và dùng đúng namespace Jakarta Mail của phiên bản Spring Boot.
5. **Nếu property thiếu**, kiểm tra host hoặc JNDI trong **Environment hiệu lực**, profile đang active và nguồn config có độ ưu tiên cao.
6. **Nếu có existing MailSender**, xác định bean custom nằm ở đâu, kiểu thực tế và nhu cầu của service.
7. **Nếu auto-config bị exclude**, xác minh có chủ đích hay không.
8. **Nếu auto-config match**, xem bean definition, lỗi khởi tạo và các context khác nhau trước khi kết luận.
9. **Sau khi có bean**, mới chuyển sang chẩn đoán STARTTLS, SMTP AUTH, host/port và gửi thử nếu chức năng gửi chưa hoạt động.

### Tình huống A: thêm starter nhưng quên host

~~~yaml
spring:
  mail:
    port: 587
    username: mailer
    password: some-example-value
~~~

Nếu không có host hoặc JNDI ở nguồn config khác, MailSenderAutoConfiguration có thể không được kích hoạt. Sửa bằng cách cung cấp **spring.mail.host** ở đúng profile/config source và bảo vệ credential bằng secret; không cần tạo custom JavaMailSenderImpl chỉ để né điều kiện này.

### Tình huống B: host chỉ khai báo ở profile prod

~~~yaml
# application-prod.yml
spring:
  mail:
    host: smtp.example.com
~~~

Test chạy profile **test** sẽ không tự nhận host từ profile **prod**. Hãy lựa chọn rõ mục tiêu: nếu chỉ test business logic thì dùng mock/fake; nếu test auto-configuration thì cấp **spring.mail.host** thử nghiệm cho context. Không kích hoạt prod trong unit test chỉ để có bean.

### Tình huống C: mock MailSender nhưng service cần JavaMailSender

~~~java
@MockBean
private org.springframework.mail.MailSender mailSender;
~~~

Service inject **JavaMailSender** nên vẫn không có bean phù hợp. Tạo mock đúng kiểu **JavaMailSender** hoặc thay interface của service nếu chỉ cần chức năng MailSender cơ bản. Report sẽ giúp phát hiện back off do existing MailSender.

### Tình huống D: bean được tạo nhưng server từ chối đăng nhập

~~~text
org.springframework.mail.MailAuthenticationException:
Authentication failed
~~~

Đây không phải lỗi thiếu JavaMailSender. Cần kiểm tra SMTP AUTH, credential, TLS, cổng, quyền gửi, tài khoản bị khóa hoặc token hết hạn. Thay đổi auto-configuration không giải quyết bản chất của lỗi xác thực.

### Tình huống E: bean đúng nhưng test controller vẫn lỗi

Một @WebMvcTest chỉ nạp lát cắt web và thiếu service dependency sẽ báo lỗi riêng. Nếu controller cần **NotificationService**, test có thể mock **NotificationService**. Việc thêm SMTP host vào @WebMvcTest không nhất thiết giải quyết vấn đề test slice thiếu bean service.

## 14. Khi nào cần tự tạo JavaMailSender bean?

Auto-configuration mặc định đủ cho nhiều ứng dụng: chỉ cần mail starter, **spring.mail.host** và các property liên quan. Tuy nhiên, một ứng dụng có thể cần **nhiều SMTP account**, sender đặc thù hoặc lựa chọn transport động, khi đó cấu hình bean thủ công có thể phù hợp.

Ví dụ tạo một JavaMailSenderImpl rõ ràng:

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class ExplicitMailSenderConfig {
    @Bean
    JavaMailSender applicationMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername("example-user");
        sender.setPassword("example-only-placeholder");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        return sender;
    }
}
~~~

Ví dụ trên dùng giá trị giả để tập trung vào API. Trong ứng dụng thật, host và credential phải được lấy từ **externalized configuration/secret store**, không hard-code. Khi đã đăng ký bean **JavaMailSender** này, Boot thường back off và service có thể inject sender do ứng dụng cung cấp.

Cấu hình thủ công có trách nhiệm lớn hơn:

- Đặt host, port, timeout, TLS, authentication và charset phù hợp.
- Bảo vệ secret và hỗ trợ thay đổi credential theo cơ chế vận hành.
- Nếu có nhiều sender, sử dụng qualifier hoặc một gateway định tuyến rõ.
- Đảm bảo bean tự tạo không bị đăng ký sai profile, ví dụ fake sender từ test rơi vào production.
- Giữ nguyên semantics của việc gửi mail và xử lý lỗi của transport.

**Không cần tạo custom sender chỉ vì đang thiếu spring.mail.host.** Trong nhiều trường hợp, sửa điều kiện cấu hình hiệu lực và kiểm tra report là cách khắc phục đúng hơn, ít code hơn.

## 15. Ghi log và quan sát trạng thái bean một cách an toàn

Khi điều tra hệ thống production, các dữ liệu hữu ích gồm:

~~~text
activeProfiles=prod
mailSenderBeanPresent=true
mailSenderImplementation=JavaMailSenderImpl
mailConfigurationSource=runtime-environment
smtpHostCategory=production-provider
mailConnectionCheck=not-run
~~~

Đây là định dạng minh họa, không phải log tự có của Spring. Một số trường có thể không cần thiết hoặc nhạy cảm tùy chính sách của tổ chức. Đừng ghi **password**, **access token**, toàn bộ **JavaMailProperties** hoặc **MimeMessage** có dữ liệu riêng tư để chẩn đoán bean.

Nếu đang cần biết cấu hình cuối cùng, đọc **/actuator/configprops** hoặc **/actuator/env** trong một kênh quản trị bảo vệ và kiểm tra giá trị đã được làm mờ. Khi cần trao đổi với đồng nghiệp, có thể chia sẻ **điều kiện match/negative match, tên class, active profiles và tên property**, bỏ secret và địa chỉ người nhận.

Các chỉ số SMTP như tỷ lệ send lỗi, thời gian gửi, số lần timeout hoặc event delivered/bounced nên được theo dõi **sau** khi bean đã tồn tại. Chúng phản ánh health vận chuyển, không phải quá trình đánh giá conditional auto-configuration.

## 16. Nguyên tắc cần nhớ khi JavaMailSender không xuất hiện

| Câu hỏi | Bằng chứng cần tìm | Hướng sửa đúng |
|---|---|---|
| Mail library có trên runtime classpath không? | Dependency graph, lỗi ConditionalOnClass | Bổ sung starter/dependency đúng module |
| Có host hoặc JNDI không? | Environment, MailProperties, condition report | Khai báo đúng spring.mail.host hoặc jndi-name |
| Có bean MailSender custom trước đó không? | Bean list, ConditionalOnMissingBean report | Bỏ/giới hạn custom bean hoặc cung cấp JavaMailSender phù hợp |
| Có exclude MailSenderAutoConfiguration không? | Annotation và spring.autoconfigure.exclude | Bỏ exclude nếu muốn Boot tạo bean |
| Có dùng test slice hoặc context hẹp không? | @WebMvcTest, @ContextConfiguration, test configuration | Mock đúng dependency hoặc nạp context cần thiết |
| Auto-config match nhưng bean vẫn không có? | Nested exception, nhánh JNDI/host, bean factory | Sửa lỗi tạo bean và context |
| Có bean nhưng SMTP lỗi? | Stack trace send/test-connection, SMTP response | Kiểm tra TLS, AUTH, network, host, provider policy |

**Quy trình cốt lõi:** xác nhận context đang chạy → đọc **Condition Evaluation Report** → đối chiếu **classpath**, **spring.mail.host/JNDI**, **existing MailSender bean**, **exclude và test context** → xác minh kiểu bean **JavaMailSender** trong ApplicationContext. Chỉ sau khi đã có bean mới chuyển sang kiểm tra kết nối và giao thức SMTP.

Điều kiện không match thường có **lý do cụ thể** được Spring Boot ghi lại. Dựa vào lý do đó để sửa **nguồn gốc cấu hình hoặc dependency**, thay vì thêm một JavaMailSenderImpl thủ công theo phản xạ, sẽ giúp ứng dụng Spring Framework Mail dễ kiểm soát, dễ kiểm thử và nhất quán giữa các môi trường.
