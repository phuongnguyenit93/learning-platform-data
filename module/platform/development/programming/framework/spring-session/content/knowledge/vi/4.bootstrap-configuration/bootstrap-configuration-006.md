# Khi cấu hình thủ công khiến cấu hình tự động ngừng áp dụng

Spring Boot có thể tự cấu hình nhiều thành phần cho ứng dụng dựa trên dependency, thuộc tính và các bean đã có trong ApplicationContext. Khi lập trình viên khai báo cấu hình thủ công, một phần auto-configuration có thể chủ động bỏ qua bean hoặc cấu hình tương ứng. Đây là cơ chế phối hợp giữa cấu hình mặc định và cấu hình do ứng dụng kiểm soát.

Với Spring Session, cơ chế này quyết định cách ứng dụng tạo repository, đăng ký filter và thiết lập cookie. Hiểu điều kiện nào khiến auto-configuration lùi lại giúp tránh tình trạng thiếu bean, có hai cơ chế quản lý session cùng hoạt động hoặc cấu hình thực tế khác với dự định.

## 1. Auto-configuration hoạt động như thế nào?

Trong ứng dụng Spring Boot, `@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Annotation này yêu cầu Spring Boot tìm các lớp auto-configuration phù hợp trên classpath và đưa chúng vào quá trình tạo ApplicationContext.

Auto-configuration không phải một cấu hình cứng luôn được áp dụng. Mỗi lớp hoặc bean thường đi kèm điều kiện. Các điều kiện phổ biến gồm:

| Điều kiện | Ý nghĩa |
|---|---|
| `@ConditionalOnClass` | Chỉ áp dụng khi một lớp thư viện có mặt trên classpath |
| `@ConditionalOnMissingClass` | Chỉ áp dụng khi lớp được chỉ định không có trên classpath |
| `@ConditionalOnProperty` | Chỉ áp dụng khi thuộc tính có giá trị thỏa điều kiện |
| `@ConditionalOnBean` | Chỉ áp dụng khi ApplicationContext đã có bean phù hợp |
| `@ConditionalOnMissingBean` | Chỉ áp dụng khi chưa có bean phù hợp |
| `@ConditionalOnWebApplication` | Chỉ áp dụng trong loại ứng dụng web được chỉ định |
| `@ConditionalOnResource` | Chỉ áp dụng khi tài nguyên được chỉ định tồn tại |

Ví dụ, một auto-configuration có thể tạo một bean mặc định khi ứng dụng chưa cung cấp bean tương ứng:

```java
@Configuration(proxyBeanMethods = false)
class ExampleServiceAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ExampleService.class)
    ExampleService exampleService() {
        return new DefaultExampleService();
    }
}
```

Nếu ứng dụng không khai báo `ExampleService`, Spring Boot tạo `DefaultExampleService`. Nếu ứng dụng cung cấp một bean `ExampleService` phù hợp, điều kiện `@ConditionalOnMissingBean` không còn thỏa mãn và phương thức tạo bean mặc định sẽ không được áp dụng.

Điều này thường được gọi là *auto-configuration back-off*: cấu hình tự động lùi lại khi ứng dụng đã cung cấp cấu hình tương ứng. Back-off diễn ra ở phạm vi của điều kiện cụ thể. Một bean mặc định có thể bị bỏ qua trong khi các auto-configuration khác vẫn tiếp tục hoạt động.

## 2. Vì sao cấu hình thủ công khiến auto-configuration back off?

Auto-configuration được thiết kế với giả định rằng ứng dụng có thể cần thay thế một số mặc định. Nếu Spring Boot luôn tạo bean mặc định bất kể bean của ứng dụng, ApplicationContext có thể có nhiều bean cùng vai trò và việc inject trở nên mơ hồ.

`@ConditionalOnMissingBean` là cách phổ biến để tránh tình trạng đó. Khi một bean phù hợp đã tồn tại, Spring Boot coi đó là dấu hiệu ứng dụng muốn tự kiểm soát thành phần này.

Các nguồn cấu hình thủ công thường gặp:

- Một phương thức `@Bean` trong lớp `@Configuration`.
- Một lớp `@Component`, `@Service` hoặc `@Repository` được component scan phát hiện.
- Một annotation `@Enable...` nhập thêm cấu hình bằng cơ chế import.
- Một thư viện khác đăng ký bean cùng loại trước khi điều kiện auto-configuration được đánh giá.
- Một cấu hình dành riêng cho profile đang hoạt động.

Ví dụ, ứng dụng khai báo bean của riêng mình:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationServiceConfiguration {

    @Bean
    ExampleService exampleService() {
        return new CustomExampleService();
    }
}
```

Khi Spring Boot đánh giá `ExampleServiceAutoConfiguration`, bean `ExampleService` của ứng dụng đã được đăng ký. Điều kiện `@ConditionalOnMissingBean(ExampleService.class)` không còn đúng nên `DefaultExampleService` không được tạo.

Điều cần ghi nhớ là một bean tùy chỉnh có thể làm thay đổi kết quả của những điều kiện khác. Sau khi thêm cấu hình thủ công, hãy kiểm tra những auto-configuration phụ thuộc vào bean đó, đặc biệt nếu bean mới chỉ triển khai một phần chức năng mà cấu hình mặc định trước đây cung cấp.

## 3. Back-off không đồng nghĩa tắt toàn bộ Spring Boot

Các điều kiện có thể được đặt trên cả lớp cấu hình hoặc từng phương thức `@Bean`.

- Nếu điều kiện trên một phương thức `@Bean` không thỏa mãn, Spring bỏ qua bean đó; các bean khác trong cùng lớp cấu hình vẫn có thể được tạo.
- Nếu điều kiện trên toàn lớp cấu hình không thỏa mãn, lớp cấu hình đó không được áp dụng.
- Nếu một auto-configuration khác có điều kiện độc lập, nó vẫn có thể chạy bình thường.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class MessagingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessagePublisher.class)
    MessagePublisher messagePublisher() {
        return new DefaultMessagePublisher();
    }

    @Bean
    MessageFormatter messageFormatter() {
        return new DefaultMessageFormatter();
    }
}
```

Nếu ứng dụng tự khai báo `MessagePublisher`, bean publisher mặc định bị bỏ qua. `MessageFormatter` vẫn có thể được tạo vì phương thức này không có điều kiện thiếu bean tương ứng.

Đây là lý do khi thấy một tính năng không được cấu hình tự động, cần xác định chính xác bean hoặc lớp cấu hình nào đã back off. Không nên kết luận rằng `@EnableAutoConfiguration` đã bị vô hiệu hóa chỉ vì một bean mặc định không xuất hiện.

## 4. Phân biệt thuộc tính cấu hình, bean tùy chỉnh và loại trừ auto-configuration

Có ba cách thường dùng để thay đổi hành vi mặc định của Spring Boot. Mỗi cách có phạm vi tác động khác nhau.

### 4.1. Thay đổi thuộc tính để điều chỉnh cấu hình mặc định

Nếu auto-configuration cung cấp thuộc tính cho nhu cầu cần thay đổi, hãy ưu tiên cấu hình thuộc tính. Cách này vẫn để Spring Boot tạo và kết nối các thành phần theo thiết kế của nó.

Ví dụ minh họa cấu hình session:

```yaml
spring:
  session:
    timeout: 30m
    redis:
      namespace: shop:session
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
```

Tên và phạm vi thuộc tính có thể thay đổi theo phiên bản Spring Boot và module Spring Session. Cần đối chiếu metadata cấu hình của đúng phiên bản dependency trong dự án. Ý chính là: nếu chỉ cần thay đổi timeout, namespace hoặc thông tin kết nối, hãy tìm thuộc tính được hỗ trợ trước khi tự tạo repository hay filter.

### 4.2. Khai báo bean để thay thế một thành phần mặc định

Khi cần triển khai hành vi riêng, ứng dụng có thể khai báo bean theo contract mà auto-configuration kiểm tra. Nếu điều kiện là `@ConditionalOnMissingBean`, bean của ứng dụng sẽ khiến bean mặc định tương ứng back off.

Trong Spring Session, ví dụ điển hình là cung cấp một `CookieSerializer` để kiểm soát tên cookie hoặc thuộc tính cookie:

```java
@Configuration(proxyBeanMethods = false)
class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SHOPSESSION");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
```

Bean này tùy chỉnh cách tuần tự hóa cookie session. Nó không có nghĩa ứng dụng đã tự cung cấp `SessionRepository`; Spring Boot vẫn có thể cấu hình repository từ Redis hoặc JDBC nếu các điều kiện tương ứng được đáp ứng.

Ví dụ này cho thấy cần xem xét đúng loại bean. Tùy chỉnh serializer không nên bị nhầm với việc thay thế toàn bộ cơ chế lưu session.

### 4.3. Loại trừ một auto-configuration

Khi muốn ngăn một auto-configuration cụ thể được áp dụng, Spring Boot hỗ trợ loại trừ bằng thuộc tính `spring.autoconfigure.exclude` hoặc thuộc tính `exclude` của `@SpringBootApplication` / `@EnableAutoConfiguration`.

Ví dụ về hình thức khai báo:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.example.SomeAutoConfiguration
```

Tên lớp trong ví dụ là chỗ giữ chỗ; cần dùng đúng tên lớp auto-configuration thực tế mà dự án muốn loại trừ. Loại trừ có phạm vi rộng hơn việc cung cấp một bean để điều kiện `@ConditionalOnMissingBean` tự back off. Khi đã loại trừ cấu hình, ứng dụng có trách nhiệm tự cung cấp những thành phần cần thiết mà cấu hình đó trước đây tạo ra.

Không nên loại trừ cả nhóm cấu hình chỉ để thay đổi một thuộc tính nhỏ. Sau khi loại trừ, hãy liệt kê các bean và hạ tầng mà tính năng vẫn cần, rồi kiểm tra chúng đã được đăng ký đầy đủ hay chưa.

## 5. Spring Session: khi nào cấu hình mặc định lùi lại?

Trong ứng dụng Spring Boot Servlet, Spring Session tích hợp với Servlet `HttpSession`. Spring Boot có thể sử dụng dependency, cấu hình kết nối và thuộc tính để chọn cách lưu session, sau đó đăng ký các thành phần tích hợp phù hợp.

Với Redis, dependency Spring Session Data Redis cùng cấu hình Redis cho phép ứng dụng dùng repository Redis. Với JDBC, dependency Spring Session JDBC và `DataSource` cho phép lưu session vào các bảng quan hệ.

Trong các phiên bản Boot hỗ trợ cấu hình store bằng thuộc tính, có thể chọn store và điều chỉnh timeout qua `application.yml`. Hãy dùng đúng tên thuộc tính được hỗ trợ bởi phiên bản đang chạy. Không nên sao chép cấu hình từ một phiên bản Boot khác mà không kiểm tra metadata.

Một số thao tác thủ công có thể làm nhánh cấu hình tự động liên quan đến session thay đổi:

| Cấu hình thủ công | Tác động có thể xảy ra |
|---|---|
| Cung cấp `SessionRepository` phù hợp | Auto-configuration có điều kiện thiếu repository có thể không tạo repository mặc định |
| Dùng `@EnableRedisHttpSession` | Nhập cấu hình Spring Session Redis theo cách tường minh; một số cấu hình tự động liên quan có thể back off |
| Dùng `@EnableJdbcHttpSession` | Nhập cấu hình Spring Session JDBC theo cách tường minh; cần tránh đồng thời cấu hình một repository khác |
| Cung cấp `CookieSerializer` | Thay đổi cách tạo cookie; repository vẫn có thể được cấu hình tự động |
| Tự đăng ký Servlet filter | Có thể xung đột với filter do Boot/Spring Session đăng ký nếu cùng xử lý một session |

Tác động cụ thể phụ thuộc phiên bản Boot, phiên bản Spring Session và điều kiện trên từng auto-configuration. Hãy dùng báo cáo điều kiện để xác minh thay vì suy luận chỉ từ tên annotation.

## 6. Hai cách cấu hình Spring Session và cách chọn

### Cách A: Để Spring Boot tự cấu hình

Đây thường là cách đơn giản nhất khi ứng dụng sử dụng một repository được hỗ trợ trực tiếp. Ví dụ, ứng dụng có dependency Redis và cấu hình kết nối Redis; Spring Boot có thể tạo hạ tầng cần thiết cho Spring Session.

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
  session:
    timeout: 30m
    redis:
      namespace: catalog:session
```

Ứng dụng tiếp tục dùng API Servlet:

```java
@RestController
class CartController {

    @PostMapping("/cart/item")
    String addItem(HttpServletRequest request) {
        HttpSession session = request.getSession();
        session.setAttribute("lastAction", "add-item");
        return "saved";
    }
}
```

Mã controller không cần biết session được lưu trong Redis hay JDBC. Spring Session đảm nhiệm việc tích hợp `HttpSession` với repository đã được cấu hình.

### Cách B: Bật cấu hình repository một cách tường minh

Khi cần kiểm soát cách cấu hình Spring Session, ứng dụng có thể dùng annotation cấu hình tương ứng. Ví dụ với Redis:

```java
@Configuration(proxyBeanMethods = false)
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
class ManualRedisSessionConfiguration {
}
```

Cấu hình này yêu cầu có `RedisConnectionFactory` phù hợp. Trong ứng dụng Spring Boot, factory có thể được tạo từ cấu hình Redis nếu dependency và điều kiện tương ứng vẫn được thỏa mãn.

Với JDBC, annotation tương ứng là `@EnableJdbcHttpSession`; ứng dụng cần có `DataSource` và schema Spring Session đúng phiên bản. Cần xem tài liệu phiên bản đang dùng để xác nhận các thuộc tính và cách khởi tạo schema.

Khi dùng chế độ tường minh, hãy kiểm tra cấu hình tự động nào vẫn hoạt động và cấu hình nào đã back off. Tránh đồng thời bật nhiều cơ chế tạo repository cho cùng một ứng dụng. Nếu ứng dụng vừa tự khai báo repository vừa bật annotation cấu hình store, hãy xác định rõ bean nào là nguồn chính và loại bỏ cấu hình trùng lặp.

## 7. Vì sao `@Primary` hoặc `@Qualifier` không thay thế cơ chế back-off?

`@Primary` và `@Qualifier` giúp Spring chọn bean khi có nhiều ứng viên cho một điểm inject. Chúng không ngăn Spring tạo bean mặc định.

Ví dụ, nếu ứng dụng có một `SessionRepository` tùy chỉnh nhưng auto-configuration cũng tạo một repository khác, gắn `@Primary` vào repository tùy chỉnh có thể giúp một số điểm inject chọn đúng bean. Tuy nhiên, cả hai bean vẫn tồn tại; những thành phần khác có thể nhận bean theo tên hoặc theo cách inject khác.

Tương tự, `@Qualifier` chỉ chọn một bean có qualifier phù hợp tại điểm inject. Nó không làm cho điều kiện `@ConditionalOnMissingBean` trở thành false trừ khi bean đó thực sự khớp điều kiện mà auto-configuration đang kiểm tra.

Một số dự án bật `spring.main.allow-bean-definition-overriding=true` để cho phép bean cùng tên ghi đè lẫn nhau. Đây là cơ chế đăng ký bean theo tên, khác với back-off theo điều kiện. Nó có thể che giấu cấu hình trùng lặp và làm kết quả phụ thuộc thứ tự đăng ký. Hãy dùng bean tùy chỉnh theo contract được auto-configuration kiểm tra hoặc loại trừ cấu hình có chủ đích, thay vì dùng ghi đè tên bean như cách sửa mặc định.

## 8. Điều kiện được đánh giá khi ApplicationContext khởi tạo

Auto-configuration được đánh giá trong quá trình tạo ApplicationContext. Điều kiện thường dựa vào bean definition, classpath và thuộc tính có sẵn tại thời điểm đó.

Thứ tự cấu hình có ý nghĩa. Spring Boot sắp xếp auto-configuration bằng các cơ chế thứ tự như `@AutoConfigureBefore` và `@AutoConfigureAfter`. Cấu hình của ứng dụng thường được xử lý để auto-configuration có thể nhận ra bean do người dùng cung cấp.

Khi tự xây dựng một thư viện có auto-configuration, cần khai báo thứ tự nếu một cấu hình phụ thuộc vào bean do auto-configuration khác tạo ra. Không nên dựa vào thứ tự ngẫu nhiên của component scan để giải quyết phụ thuộc giữa các auto-configuration.

Một điểm quan trọng là kiểu trả về của phương thức `@Bean` giúp Spring nhận diện kiểu bean trong quá trình đánh giá điều kiện. Hãy khai báo kiểu trả về theo contract cụ thể mà các cấu hình khác cần kiểm tra. Nếu khai báo quá chung, điều kiện dựa trên kiểu có thể khó nhận diện bean như dự định ở một số tình huống khởi tạo.

Ví dụ, nếu auto-configuration kiểm tra `ExampleService`, hãy khai báo phương thức trả về `ExampleService` hoặc kiểu triển khai tương thích, thay vì khai báo kiểu trả về chung chung như `Object`.

Sau khi ApplicationContext đã khởi tạo, thêm hoặc thay đổi bean không làm toàn bộ điều kiện auto-configuration được đánh giá lại như một cấu hình động. Nếu cần thay đổi store hoặc repository, nên xem đó là thay đổi cấu hình khởi động và tạo lại ApplicationContext theo quy trình triển khai phù hợp.

## 9. Cách chẩn đoán khi bean tự động không xuất hiện

Spring Boot cung cấp Condition Evaluation Report để giải thích vì sao một auto-configuration được áp dụng hoặc bị bỏ qua.

Có thể bật báo cáo điều kiện khi khởi động bằng tham số:

```text
java -jar app.jar --debug
```

Trong log, tìm phần báo cáo điều kiện. Các mục positive match cho biết điều kiện đã thỏa mãn; negative match cho biết điều kiện không thỏa mãn và thường kèm lý do. Tên và cách trình bày log có thể khác nhau theo phiên bản.

Nếu ứng dụng đã bật Spring Boot Actuator và cho phép truy cập endpoint tương ứng, endpoint `conditions` cũng có thể cung cấp thông tin về các điều kiện. Chỉ nên expose endpoint này theo chính sách bảo mật của môi trường; không mở công khai thông tin chẩn đoán cấu hình nội bộ.

Quy trình chẩn đoán thực tế:

1. Xác nhận phiên bản Spring Boot và Spring Session đang chạy, cùng dependency thực tế trên classpath.
2. Xác nhận profile đang hoạt động và giá trị thuộc tính sau khi áp dụng biến môi trường, file cấu hình và tham số dòng lệnh.
3. Khởi động với `--debug` hoặc đọc endpoint điều kiện đã được bảo vệ.
4. Tìm auto-configuration liên quan đến tính năng đang thiếu.
5. Đọc lý do điều kiện không thỏa mãn: thiếu class, thiếu bean, đã có bean cùng loại, thuộc tính bị tắt hoặc ứng dụng không thuộc loại web cần thiết.
6. Tìm cấu hình thủ công đã cung cấp bean hoặc bật annotation nào làm thay đổi kết quả.
7. Chọn cách sửa nhỏ nhất: điều chỉnh thuộc tính, sửa bean tùy chỉnh, bỏ annotation trùng lặp hoặc loại trừ đúng auto-configuration.
8. Khởi động lại và xác nhận ApplicationContext có đúng các bean cần thiết.

Ví dụ, nếu session không được lưu vào Redis như mong muốn, hãy xác minh `RedisConnectionFactory`, `SessionRepository`, `SessionRepositoryFilter` và cookie resolver/serializer. Việc một bean xuất hiện không tự chứng minh toàn bộ luồng session đã được đăng ký đúng.

## 10. Những lỗi cấu hình thường gặp

### Có repository tùy chỉnh nhưng thiếu filter

Một `SessionRepository` có thể lưu dữ liệu đúng, nhưng ứng dụng Servlet vẫn cần lớp tích hợp để các request dùng `HttpSession` đi qua repository. Nếu filter không được đăng ký, controller có thể vẫn làm việc với session của container.

Khi tự cung cấp repository, cần xác nhận Spring Boot/Spring Session đã đăng ký filter tương ứng. Nếu tự đăng ký filter, kiểm tra thứ tự để filter chạy trước các filter cần đọc session, chẳng hạn Spring Security. Không đăng ký hai filter cùng quản lý một session.

### Bật annotation cấu hình tường minh trùng với auto-configuration

Ứng dụng đã để Boot cấu hình Redis session nhưng sau đó thêm `@EnableRedisHttpSession` theo một ví dụ trên mạng. Tùy phiên bản, annotation này có thể nhập cấu hình repository tường minh và làm thay đổi các điều kiện cấu hình khác. Hậu quả có thể là nhiều bean, bean mặc định back off hoặc cấu hình filter khó dự đoán.

Hãy chọn một cách cấu hình có chủ đích và kiểm tra condition report sau khi thay đổi.

### Chỉ thêm dependency nhưng chưa có cấu hình kết nối

Có dependency Redis trên classpath không bảo đảm ứng dụng có thể kết nối Redis. Auto-configuration có thể yêu cầu thêm một `RedisConnectionFactory`, thuộc tính kết nối hợp lệ hoặc điều kiện khác. Condition report giúp phân biệt thiếu thư viện với thiếu bean kết nối.

### Bean tùy chỉnh chỉ triển khai một phần contract

Một bean có đúng kiểu có thể khiến bean mặc định back off, dù bean tùy chỉnh chưa cung cấp đủ hành vi mà ứng dụng cần. Điều kiện back-off chỉ xác nhận sự hiện diện của bean theo tiêu chí đã khai báo; nó không đánh giá chất lượng hay tính đầy đủ của logic.

Hãy kiểm tra các phụ thuộc và hành vi mà những thành phần khác kỳ vọng từ contract đó.

### Cố khắc phục bằng ghi đè bean theo tên

Bật bean overriding có thể khiến ứng dụng khởi động nhưng không làm rõ cấu hình nào đang được dùng. Ưu tiên đọc điều kiện, xác định bean bị trùng và chỉnh sửa nguồn cấu hình có trách nhiệm tạo ra bean đó.

## 11. Kiểm thử hành vi back-off

Không nên chỉ kiểm tra rằng ứng dụng khởi động thành công. Cần kiểm tra cả hai trường hợp: khi không có bean tùy chỉnh, auto-configuration tạo mặc định; khi có bean tùy chỉnh, mặc định tương ứng không xuất hiện.

Với một auto-configuration do dự án tự viết, có thể dùng `ApplicationContextRunner` từ Spring Boot Test để dựng ApplicationContext nhỏ và kiểm tra từng trường hợp. Ví dụ khái quát:

```java
class ExampleServiceAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ExampleServiceAutoConfiguration.class));

    @Test
    void createsDefaultWhenNoCustomBeanExists() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(ExampleService.class);
            assertThat(context.getBean(ExampleService.class))
                    .isInstanceOf(DefaultExampleService.class);
        });
    }

    @Test
    void backsOffWhenCustomBeanExists() {
        contextRunner
                .withUserConfiguration(CustomExampleServiceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ExampleService.class);
                    assertThat(context.getBean(ExampleService.class))
                            .isInstanceOf(CustomExampleService.class);
                });
    }
}
```

Đây là mẫu kiểm thử cho auto-configuration của dự án; cần bổ sung import, package và dependency Spring Boot Test phù hợp. Với Spring Session, kiểm thử tích hợp nên xác nhận:

- ApplicationContext có một repository phù hợp với store đã chọn.
- Filter quản lý session được đăng ký đúng một lần và đúng thứ tự.
- Cookie serializer/resolver có cấu hình như mong đợi.
- Một session tạo ở request trước có thể được đọc ở request sau.
- Nếu có hai instance dùng chung kho, instance thứ hai đọc được session do instance thứ nhất tạo.
- Logout hoặc invalidate khiến session cũ không còn được chấp nhận.

Khi ứng dụng có bean tùy chỉnh, nên kiểm tra cả loại bean, qualifier hoặc tên bean mà các thành phần liên quan sử dụng. Một assertion đơn giản về số lượng bean có thể phát hiện cấu hình trùng lặp sớm.

## 12. Nguyên tắc lựa chọn cấu hình trong ứng dụng Spring Session

Khi khởi tạo Spring Session, hãy đi theo thứ tự sau:

1. Xác định ứng dụng dùng Servlet `HttpSession` hay WebFlux `WebSession`.
2. Chọn kho dữ liệu: Redis hoặc JDBC, dựa trên tải, độ trễ, vận hành và yêu cầu lưu trữ.
3. Kiểm tra dependency và thuộc tính mà phiên bản Spring Boot hỗ trợ.
4. Để auto-configuration tạo repository và filter nếu nhu cầu nằm trong phạm vi mặc định.
5. Chỉ cung cấp bean tùy chỉnh khi cần thay đổi một contract cụ thể, ví dụ `CookieSerializer`.
6. Chỉ dùng `@EnableRedisHttpSession` hoặc `@EnableJdbcHttpSession` khi muốn cấu hình Spring Session theo cách tường minh và đã hiểu các auto-configuration liên quan.
7. Dùng condition report để xác minh cấu hình thực tế sau khi khởi động.
8. Kiểm thử repository, filter, cookie, timeout và hành vi giữa nhiều instance.

Cấu hình tự động giúp ứng dụng có bộ mặc định nhất quán và giảm lượng cấu hình lặp lại. Cấu hình thủ công cho phép ứng dụng kiểm soát một thành phần cụ thể; khi bean đó thỏa điều kiện mà auto-configuration kiểm tra, Spring Boot sẽ bỏ qua phần mặc định tương ứng. Hiểu rõ phạm vi điều kiện và xác minh bằng Condition Evaluation Report giúp ứng dụng Spring Session có cấu hình dễ dự đoán, không tạo repository hoặc filter trùng lặp và vận hành ổn định khi triển khai nhiều instance.

