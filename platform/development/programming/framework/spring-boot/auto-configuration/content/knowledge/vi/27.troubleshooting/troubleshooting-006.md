# Bean nền có mặt nhưng cấu hình phụ thuộc được đánh giá sai thời điểm

## 1. Triệu chứng và nguyên nhân

Một lỗi khó hiểu trong Spring Boot auto-configuration là bean nền cuối cùng vẫn xuất hiện trong **ApplicationContext**, nhưng bean phụ thuộc vào nó lại không được đăng ký. Log có thể cho thấy prerequisite đã được tạo thành công, trong khi **@ConditionalOnBean** của auto-configuration phụ thuộc báo không tìm thấy bean.

Nguyên nhân có thể nằm ở thời điểm đánh giá condition:

1. Spring xử lý configuration classes và đăng ký bean definitions.
2. Bean conditions được đánh giá trong quá trình xử lý đó.
3. Sau khi definitions đã được đăng ký, Spring mới tạo bean instances theo dependency graph và lifecycle.

**@ConditionalOnBean** và **@ConditionalOnMissingBean** chỉ nhìn thấy các bean definitions đã được xử lý tại thời điểm condition chạy. Chúng không chờ context khởi tạo xong rồi đánh giá lại. Nếu auto-configuration phụ thuộc chạy trước auto-configuration cung cấp bean nền, condition có thể trả về **false**. Bean nền được đăng ký sau đó cũng không làm condition cũ tự chạy lại.

Vì vậy, thông báo “bean không tồn tại” đôi khi có nghĩa chính xác là “bean definition chưa được xử lý tại thời điểm kiểm tra”. Nó không nhất thiết có nghĩa dependency bị thiếu khỏi toàn bộ ứng dụng.

Bài học dùng **Java 17 và Spring Boot 3.3.13** để trình bày cách nhận diện lỗi, khai báo ordering, thiết kế bean conditions, kiểm tra type metadata và viết test bằng **ApplicationContextRunner**.

## 2. Phân biệt bean definition và bean instance

| Khái niệm | Ý nghĩa | Thời điểm |
|---|---|---|
| Bean definition | Metadata mô tả bean: tên, type, factory method, scope, dependency và cách khởi tạo | Được đăng ký trong giai đoạn xử lý configuration |
| Bean instance | Đối tượng Java thực tế được tạo từ bean definition | Thường được tạo khi context refresh hoặc khi bean được yêu cầu nếu lazy |
| Bean condition | Điều kiện quyết định một configuration/bean definition có được đăng ký hay không | Khi Spring xử lý configuration và đăng ký bean definitions |
| Dependency injection | Kết nối các bean instances với dependency của chúng | Khi bean được tạo và khởi tạo |

Ví dụ, khi Spring xử lý:

~~~java
@Bean
SearchClient searchClient() {
    return new SearchClient();
}
~~~

Spring có thể đăng ký bean definition cho **searchClient** trước khi đối tượng **SearchClient** được khởi tạo. Một condition dựa trên bean type có thể nhận biết definition này nếu nó đã được xử lý và method signature cung cấp đủ type information.

Ngược lại, nếu condition chạy trước khi configuration chứa method trên được xử lý, registry chưa có definition để condition tìm thấy. Một log xuất hiện sau khi ứng dụng khởi động thành công không chứng minh bean đã có mặt ở thời điểm condition được đánh giá.

## 3. Bean condition chỉ nhìn thấy definitions đã xử lý

**@ConditionalOnBean** khớp khi bean đáp ứng tiêu chí đã có trong BeanFactory. Có thể kiểm tra theo type, tên bean hoặc annotation.

Theo type:

~~~java
@Bean
@ConditionalOnBean(SearchClient.class)
SearchFacade searchFacade(SearchClient client) {
    return new SearchFacade(client);
}
~~~

Theo tên:

~~~java
@Bean
@ConditionalOnBean(name = "acmeSearchClient")
SearchFacade searchFacade(SearchClient client) {
    return new SearchFacade(client);
}
~~~

**@ConditionalOnMissingBean** có giới hạn thời điểm tương tự. Nếu một auto-configuration cung cấp bean mặc định chạy trước configuration có bean tùy chỉnh, condition có thể kết luận nhầm rằng chưa có bean và đăng ký default.

Spring Boot khuyến nghị đặt **@ConditionalOnBean** và **@ConditionalOnMissingBean** trên auto-configuration classes. Auto-configuration được xử lý sau các bean definitions do ứng dụng khai báo, nên có thể nhận biết bean tùy chỉnh đó.

Không nên đặt bean condition trên một configuration class được component-scan tùy ý rồi giả định mọi bean khác đã được đăng ký. Thứ tự xử lý của configuration thông thường có thể không đáp ứng giả định đó.

## 4. Tình huống lỗi điển hình

Giả sử thư viện có hai auto-configuration:

- **SearchClientAutoConfiguration** cung cấp bean nền **SearchClient**.
- **SearchFacadeAutoConfiguration** chỉ cung cấp **SearchFacade** khi **SearchClient** đã có.

Nếu không khai báo quan hệ thứ tự, cấu hình phụ thuộc có thể được xử lý trước:

~~~text
1. Spring xử lý SearchFacadeAutoConfiguration
2. @ConditionalOnBean(SearchClient.class) được đánh giá
3. SearchClient definition chưa được xử lý
4. Condition trả về false
5. SearchFacade không được đăng ký
6. Spring xử lý SearchClientAutoConfiguration
7. SearchClient definition được đăng ký
8. Context tiếp tục khởi tạo và SearchClient xuất hiện
9. Condition cũ không được đánh giá lại
~~~

Kết quả cuối cùng có thể là:

| Bean | Trạng thái |
|---|---|
| SearchClient | Có |
| SearchFacade | Không có |
| ApplicationContext | Có thể vẫn khởi động thành công |

Nếu một bean khác bắt buộc inject SearchFacade, ứng dụng có thể thất bại với **UnsatisfiedDependencyException** hoặc **NoSuchBeanDefinitionException**. Nếu không có bean nào yêu cầu facade, lỗi chỉ biểu hiện thành tính năng tùy chọn không được kích hoạt.

## 5. Cách sửa: khai báo thứ tự auto-configuration

Spring Boot cung cấp **before**, **beforeName**, **after** và **afterName** trên **@AutoConfiguration**. Với prerequisite thuộc cùng thư viện, khai báo **after** trực tiếp.

### 5.1. Bean nền

Tệp src/main/java/com/acme/search/SearchClient.java:

~~~java
package com.acme.search;

public class SearchClient {

    private final String provider;

    public SearchClient(String provider) {
        this.provider = provider;
    }

    public String provider() {
        return this.provider;
    }
}
~~~

### 5.2. Bean phụ thuộc

Tệp src/main/java/com/acme/search/SearchFacade.java:

~~~java
package com.acme.search;

public class SearchFacade {

    private final SearchClient client;

    public SearchFacade(SearchClient client) {
        this.client = client;
    }

    public String provider() {
        return this.client.provider();
    }
}
~~~

### 5.3. Auto-configuration cung cấp bean nền

Tệp SearchClientAutoConfiguration.java:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class SearchClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    SearchClient searchClient() {
        return new SearchClient("starter-default");
    }
}
~~~

**@ConditionalOnMissingBean** cho phép ứng dụng thay thế client mặc định bằng bean của mình. Method trả về type cụ thể **SearchClient**, giúp bean conditions khác có đủ type information khi kiểm tra definition.

### 5.4. Auto-configuration phụ thuộc

Tệp SearchFacadeAutoConfiguration.java:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchClient;
import com.acme.search.SearchFacade;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = SearchClientAutoConfiguration.class)
public class SearchFacadeAutoConfiguration {

    @Bean
    @ConditionalOnBean(SearchClient.class)
    SearchFacade searchFacade(SearchClient client) {
        return new SearchFacade(client);
    }
}
~~~

Thuộc tính **after** khai báo rằng **SearchFacadeAutoConfiguration** phải được áp dụng sau **SearchClientAutoConfiguration**. Khi bean condition của facade được đánh giá, definition của client đã được xử lý.

Tham số **SearchClient client** giúp Spring inject client khi tạo facade, nhưng parameter không thay thế condition ordering. Condition phải match trước thì bean method mới được đăng ký.

### 5.5. Đăng ký auto-configuration

Tạo file src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
com.acme.search.autoconfigure.SearchClientAutoConfiguration
com.acme.search.autoconfigure.SearchFacadeAutoConfiguration
~~~

Mỗi dòng là tên đầy đủ của một auto-configuration class. Ordering được khai báo bằng annotation; không dựa vào thứ tự tình cờ của các dòng trong imports file để thể hiện quan hệ phụ thuộc.

Auto-configuration nên được phát hiện qua imports file. Không đưa package của thư viện vào component scan của ứng dụng để thay thế cơ chế này.

## 6. Kiểm thử bằng ApplicationContextRunner

**ApplicationContextRunner** kiểm tra các auto-configuration trong một context nhỏ. **AutoConfigurations.of(...)** áp dụng ordering metadata của các auto-configuration được cung cấp.

Tệp SearchAutoConfigurationTests.java:

~~~java
package com.acme.search.autoconfigure;

import com.acme.search.SearchClient;
import com.acme.search.SearchFacade;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SearchAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    SearchFacadeAutoConfiguration.class,
                                    SearchClientAutoConfiguration.class
                            )
                    );

    @Test
    void registersDependentBeanAfterPrerequisiteDefinition() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(SearchClient.class);
            assertThat(context).hasSingleBean(SearchFacade.class);
            assertThat(context.getBean(SearchFacade.class).provider())
                    .isEqualTo("starter-default");
        });
    }

    @Test
    void skipsDependentBeanWhenPrerequisiteIsAbsent() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                SearchFacadeAutoConfiguration.class
                        )
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(SearchClient.class);
                    assertThat(context).doesNotHaveBean(SearchFacade.class);
                });
    }

    @Test
    void usesApplicationDefinedPrerequisite() {
        this.runner
                .withUserConfiguration(UserSearchClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(SearchClient.class);
                    assertThat(context).hasSingleBean(SearchFacade.class);
                    assertThat(context.getBean(SearchFacade.class).provider())
                            .isEqualTo("application");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSearchClientConfiguration {

        @Bean
        SearchClient applicationSearchClient() {
            return new SearchClient("application");
        }
    }
}
~~~

Ba test case thể hiện ba hành vi:

| Scenario | Kết quả mong đợi |
|---|---|
| Có cả hai auto-configuration | Client và facade đều được đăng ký; facade dùng client mặc định |
| Chỉ có auto-configuration phụ thuộc | Condition không match; context vẫn chạy và không có facade |
| Ứng dụng tự khai báo client | Default client back off; facade dùng client của ứng dụng |

Test thứ nhất cố ý đưa auto-configuration phụ thuộc vào danh sách trước auto-configuration nền. Annotation **after** vẫn bảo đảm thứ tự áp dụng đúng.

Với Maven và Spring Boot 3.3.13, cần dependency **spring-boot-autoconfigure** và **spring-boot-starter-test** ở test scope. Đặt BOM 3.3.13 trong dependencyManagement hoặc dùng Spring Boot parent; project cần Java 17.

Chạy:

~~~bash
./mvnw -Dtest=SearchAutoConfigurationTests test
~~~

Kết quả mong đợi khi các class và dependency được đặt đúng package:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là output dự kiến của ví dụ, không phải kết quả chạy trên project hiện tại.

## 7. Chọn before, after và afterName

| Thuộc tính | Ý nghĩa | Khi dùng |
|---|---|---|
| **@AutoConfiguration(after = Other.class)** | Áp dụng sau auto-configuration được chỉ định | Có quan hệ phụ thuộc trực tiếp và class có trên compile classpath |
| **@AutoConfiguration(before = Other.class)** | Áp dụng trước auto-configuration được chỉ định | Cấu hình phải đăng ký bean definitions trước cấu hình khác |
| **@AutoConfiguration(afterName = "...")** | Áp dụng sau class được chỉ định bằng tên | Không muốn tạo compile dependency lên auto-configuration tùy chọn |
| **@AutoConfiguration(beforeName = "...")** | Áp dụng trước class được chỉ định bằng tên | Cần thứ tự nhưng không tham chiếu trực tiếp class |
| **@AutoConfigureAfter / @AutoConfigureBefore** | Annotation ordering chuyên biệt | Dùng khi cần annotation riêng hoặc giữ style tương thích |
| **@AutoConfigureOrder** | Đặt thứ tự tổng quát giữa các auto-configuration | Các auto-configuration không có quan hệ trực tiếp nhưng cần thứ tự tương đối |

Nếu bean nền đến từ thư viện tùy chọn và class auto-configuration của nó không có trên compile classpath, có thể dùng tên đầy đủ:

~~~java
@AutoConfiguration(
    afterName = "com.vendor.search.autoconfigure.VendorSearchAutoConfiguration"
)
public class AcmeSearchAutoConfiguration {
}
~~~

Khai báo bằng tên tránh phải tham chiếu trực tiếp class tùy chọn. Nếu auto-configuration nền không có trên runtime classpath thì bean nền cũng không xuất hiện; **@ConditionalOnBean** vẫn phải kiểm tra tính năng có được đăng ký hay không.

Với quan hệ trực tiếp giữa hai class cùng thư viện, **after = SomeAutoConfiguration.class** thường rõ ràng và dễ refactor hơn.

## 8. Ordering bean definitions khác ordering bean instances

Không dùng **@DependsOn** hoặc **@Order** để sửa bean condition:

| Cơ chế | Điều khiển điều gì? | Sửa condition đánh giá quá sớm? |
|---|---|---|
| **@AutoConfiguration(after = ...)** | Thứ tự áp dụng auto-configuration và đăng ký bean definitions | Có, nếu prerequisite nằm trong auto-configuration được sắp sau |
| **@DependsOn** | Thứ tự khởi tạo bean instances | Không |
| **@Order** | Thứ tự phần tử trong một số collection/callback được Spring sắp xếp | Không |
| **@Primary** | Chọn bean ưu tiên khi có nhiều candidate cùng type | Không |
| **@Lazy** | Trì hoãn khởi tạo bean instance | Không |

**@AutoConfiguration(after = ...)** không yêu cầu client instance phải được tạo trước facade instance. Khi facade được khởi tạo, dependency parameter đã cho Spring biết cần tạo client trước khi inject.

**@DependsOn** chỉ có ý nghĩa sau khi bean definitions đã tồn tại. Nó không khiến một **@ConditionalOnBean** đã trả về false được đánh giá lại.

**@Order** không phải annotation sắp xếp auto-configuration classes. Dùng **@AutoConfigureOrder** khi cần thứ tự tổng quát; nếu có quan hệ prerequisite rõ ràng, khai báo after hoặc before trực tiếp.

## 9. Kiểm tra type metadata của @Bean method

Bean conditions dựa vào thông tin type mà Spring suy ra từ bean definitions đã xử lý. Vì vậy, return type của **@Bean** method rất quan trọng.

Ví dụ tốt khi condition kiểm tra **SearchClient.class**:

~~~java
@Bean
SearchClient searchClient() {
    return new DefaultSearchClient();
}
~~~

Ví dụ dễ làm mất thông tin type:

~~~java
@Bean
Object searchClient() {
    return new DefaultSearchClient();
}
~~~

Ở ví dụ thứ hai, method signature chỉ công bố **Object**. Khi condition được đánh giá trước khi instance được tạo, Spring không thể dựa vào runtime object sau này để kết luận definition có type SearchClient.

Nếu condition kiểm tra interface SearchClient, return type interface là đủ. Nếu condition kiểm tra concrete implementation, return type nên thể hiện concrete type đó khi có thể. Tránh trả về Object, raw type hoặc một type quá rộng khi bean condition cần kiểm tra type cụ thể.

## 10. Phân biệt các tình huống có vẻ giống nhau

### 10.1. Bean nền thật sự không có

Dependency không được khai báo, classpath condition không khớp hoặc auto-configuration nền bị exclude. Bean definition không xuất hiện ở bất kỳ thời điểm nào.

Kiểm tra dependency runtime, AutoConfiguration.imports, @ConditionalOnClass, property condition và exclusions.

### 10.2. Bean nền xuất hiện sau condition

Auto-configuration nền có mặt nhưng được áp dụng sau cấu hình phụ thuộc. Condition chạy trước nên không nhìn thấy definition.

Khai báo after hoặc afterName trên auto-configuration phụ thuộc.

### 10.3. Bean nền có type metadata không đủ

Bean method khai báo return type quá chung, khiến condition không thể nhận diện type mong muốn trước khi instance được tạo.

Khai báo return type cụ thể hoặc type contract mà condition thực sự kiểm tra.

### 10.4. Bean nền chỉ được đăng ký động quá muộn

Một số extension tự đăng ký bean definitions bằng registry post-processor hoặc cơ chế động. Nếu definition chỉ xuất hiện sau thời điểm condition đã chạy, bean condition không thể dự đoán nó.

Nếu có thể, chuyển prerequisite sang configuration/auto-configuration có thứ tự rõ ràng. Nếu không, đừng dùng @ConditionalOnBean để phụ thuộc vào bean được đăng ký động sau phase đó; thiết kế extension point phù hợp với lifecycle của cơ chế đăng ký.

### 10.5. Bean nằm trong parent context

Ứng dụng có thể có context hierarchy. Bean nằm ở parent context không giống bean definition trong registry của child context. Bean conditions có thuộc tính search để kiểm soát phạm vi tìm kiếm theo context hierarchy.

Xác định bean nằm ở context nào và chọn SearchStrategy phù hợp. Không mặc định bean trong một context bất kỳ sẽ luôn được nhìn thấy bởi mọi condition.

### 10.6. Bean condition chỉ gate một method

Nếu @ConditionalOnBean đặt trên @Bean method, chỉ bean method đó bị ảnh hưởng. Các bean khác trong configuration class vẫn có thể được đăng ký.

Nếu condition đặt trên class, nó áp dụng cho cả configuration class. Chọn vị trí annotation theo phạm vi thật sự cần gate.

## 11. Chẩn đoán bằng Condition Evaluation Report

Khi bean phụ thuộc không xuất hiện, bật condition report:

~~~bash
java -jar app.jar --debug
~~~

Hoặc cấu hình logger:

~~~yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
~~~

Tìm report của auto-configuration liên quan. Một kết quả no-match có thể ghi condition không tìm thấy bean type hoặc bean name yêu cầu.

Đọc report theo các câu hỏi:

1. Auto-configuration phụ thuộc có được phát hiện không?
2. Auto-configuration nền có nằm trong candidate list không?
3. Condition nào không match?
4. Condition đang kiểm tra type hay tên bean nào?
5. Auto-configuration nền được áp dụng trước hay sau?
6. Bean method nền có return type đủ cụ thể không?
7. Có property, classpath condition hoặc exclusion nào khiến bean nền không được đăng ký?

Report thường cho biết lý do condition không match, nhưng không nhất thiết trình bày toàn bộ lịch sử thời gian dưới dạng timeline. Để tái hiện, dùng ApplicationContextRunner và thay đổi một đầu vào tại một thời điểm.

Kiểm tra bean sau startup chỉ xác nhận trạng thái cuối. Muốn chứng minh lỗi ordering, cần xem condition report và thứ tự áp dụng auto-configuration.

## 12. Cách sửa theo nguyên nhân

| Nguyên nhân | Cách sửa |
|---|---|
| Auto-configuration phụ thuộc chạy trước auto-configuration nền | Thêm @AutoConfiguration(after = BaseAutoConfiguration.class) |
| Auto-configuration nền là dependency tùy chọn | Dùng afterName và giữ condition kiểm tra bean/class phù hợp |
| Condition nằm trên configuration được component-scan | Chuyển bean condition sang auto-configuration class được đăng ký qua imports |
| Return type của @Bean quá rộng | Công bố return type cụ thể để condition suy ra type |
| Bean nền không có do classpath/property/exclusion | Sửa dependency hoặc điều kiện thực sự làm bean nền không được đăng ký |
| Bean nền nằm ở context khác | Xác định context hierarchy và cấu hình SearchStrategy phù hợp |
| Bean được đăng ký động sau condition | Đưa prerequisite vào phase đăng ký có thể ordering hoặc đổi extension design |
| Cần kiểm tra bean instance/runtime state | Chuyển logic sang bean/service/event sau khi context được tạo |

Không thêm @DependsOn, @Lazy hoặc @Primary theo phản xạ. Chúng giải quyết các vấn đề khác nhau và có thể che triệu chứng mà không sửa thời điểm đánh giá condition.

## 13. Lỗi thường gặp khi thiết kế auto-configuration phụ thuộc

- **Dựa vào thứ tự imports file:** thứ tự dòng không thay thế cho @AutoConfiguration(after = ...).
- **Không khai báo ordering giữa hai auto-configuration có phụ thuộc:** bean condition có thể chạy trước khi prerequisite definition tồn tại.
- **Đặt @ConditionalOnBean lên configuration class được scan như user config:** không có bảo đảm mọi user bean definitions đã được xử lý.
- **Nghĩ bean instance phải tồn tại thì condition mới match:** bean condition có thể làm việc với bean definition đã được xử lý; instance chưa cần khởi tạo.
- **Dùng @DependsOn để ép condition đợi:** @DependsOn chỉ điều khiển instance creation.
- **Dùng @Order cho auto-configuration:** dùng @AutoConfiguration ordering hoặc @AutoConfigureOrder.
- **Trả Object từ bean method rồi condition theo concrete type:** type metadata có thể không đủ.
- **Gộp prerequisite và dependent bean methods vào cùng class rồi dựa vào thứ tự method:** không dùng thứ tự khai báo method làm hợp đồng giữa các bean conditions; tách auto-configuration nếu có dependency về registration.
- **Tưởng condition false luôn làm startup fail:** thường nó chỉ bỏ qua bean/configuration; lỗi xuất hiện nếu dependency khác bắt buộc bean bị bỏ qua.
- **Dùng @ConditionalOnMissingBean để tạo default trước khi user beans được xử lý:** đặt trên auto-configuration và giữ ordering phù hợp.
- **Không kiểm tra context hierarchy:** bean ở parent/child context có thể không được tìm theo chiến lược mong muốn.
- **Dùng condition cho trạng thái runtime:** condition không phải nơi gọi service, mở kết nối hoặc đọc bean instance.
- **Không test cả trường hợp có và không có prerequisite:** test thành công đơn lẻ chưa chứng minh feature được bỏ qua đúng khi thiếu dependency.
- **Chỉ kiểm tra bean sau startup:** cần kiểm tra cả condition report và ordering metadata để tìm lỗi thời điểm.

## 14. Checklist review một cặp auto-configuration

- [ ] Auto-configuration nền có được liệt kê trong AutoConfiguration.imports không?
- [ ] Auto-configuration phụ thuộc có được liệt kê không?
- [ ] Class phụ thuộc có after hoặc afterName đúng không?
- [ ] Bean condition kiểm tra đúng type hoặc tên bean không?
- [ ] Return type của prerequisite @Bean method có cung cấp đủ type information không?
- [ ] Bean condition có nằm trên auto-configuration class thay vì config được scan tùy ý không?
- [ ] User-defined bean có thể thay thế default bean không?
- [ ] Khi prerequisite vắng mặt, dependent feature có được bỏ qua an toàn không?
- [ ] Có test với ApplicationContextRunner cho cả hai trạng thái không?
- [ ] Có consumer test xác nhận auto-configuration imports được phát hiện không?
- [ ] Có xem condition report khi test failure không?
- [ ] Có tránh dùng @DependsOn, @Lazy hoặc @Order sai mục đích không?

## 15. Quy trình điều tra trong dự án thực tế

1. Xác nhận bean phụ thuộc nào không xuất hiện và bean nền có xuất hiện sau khi context khởi động hay không.
2. Đọc condition report để lấy lý do @ConditionalOnBean hoặc @ConditionalOnMissingBean không match.
3. Xác định auto-configuration nào cung cấp bean nền và auto-configuration nào tiêu thụ nó.
4. Kiểm tra cả hai class có được liệt kê trong AutoConfiguration.imports không.
5. Kiểm tra ordering annotation trên class phụ thuộc.
6. Kiểm tra @Bean return type của prerequisite có đủ cụ thể không.
7. Kiểm tra bean condition đặt ở class-level hay method-level và phạm vi gate có đúng không.
8. Dựng ApplicationContextRunner tối giản với danh sách auto-configurations có thứ tự giống ứng dụng.
9. Viết test cho trường hợp prerequisite có, không có và do user cung cấp.
10. Sửa ordering/metadata hoặc dependency thật sự gây lỗi.
11. Chạy lại test, sau đó chạy consumer application với đúng BOM/profile của ứng dụng.
12. Kiểm tra condition report và bean graph cuối cùng trước khi phát hành.

## 16. Câu hỏi tự kiểm tra

1. Vì sao bean nền có thể có sau startup nhưng @ConditionalOnBean vẫn không match? **Vì condition được đánh giá khi đăng ký bean definitions và chỉ nhìn những definitions đã được xử lý đến thời điểm đó.**
2. Condition có tự chạy lại khi bean nền được đăng ký sau không? **Không.**
3. Thuộc tính nào khai báo auto-configuration phụ thuộc phải chạy sau cấu hình nền? **@AutoConfiguration(after = BaseAutoConfiguration.class).**
4. Khi không muốn compile dependency lên auto-configuration tùy chọn, dùng gì? **afterName với tên class đầy đủ.**
5. @AutoConfiguration(after = ...) điều khiển thứ tự nào? **Thứ tự áp dụng auto-configuration và đăng ký bean definitions.**
6. Nó có điều khiển thứ tự tạo bean instances không? **Không.** Dependency graph và @DependsOn điều khiển instance creation.
7. Vì sao @DependsOn không sửa được condition đánh giá quá sớm? **Condition đã quyết định có đăng ký bean definition hay không trước khi instance creation bắt đầu.**
8. Vì sao nên đặt @ConditionalOnBean trên auto-configuration? **Auto-configuration được xử lý sau user-defined bean definitions và có ordering rõ ràng với auto-configuration khác.**
9. Vì sao return type của @Bean method quan trọng? **Bean conditions chỉ dựa vào type information có sẵn từ bean definition/method signature khi đánh giá.**
10. Nếu condition không match, ứng dụng có luôn fail startup không? **Không.** Bean có thể chỉ bị bỏ qua; startup fail nếu bean khác bắt buộc dependency đó.
11. Dùng công cụ nào để xem condition match/no-match? **ConditionEvaluationReport, thường được in khi chạy --debug.**
12. @Order có thay thế @AutoConfiguration(after=...) không? **Không.** Hai annotation điều khiển các loại ordering khác nhau.
13. Khi prerequisite nằm ở parent context, cần kiểm tra gì? **Context hierarchy và SearchStrategy của bean condition.**
14. Test nào phù hợp để xác nhận ordering của auto-configuration? **ApplicationContextRunner kết hợp AutoConfigurations.of(...) và test cả prerequisite có/không có.**

## 17. Tài liệu tham khảo chính thức (Spring Boot 3.3)

- [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): bean conditions, ordering, imports file và khuyến nghị đặt bean conditions trên auto-configuration.
- [ConditionalOnBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): điều kiện chỉ match với bean definitions đáp ứng tiêu chí và đã được xử lý.
- [ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): điều kiện back-off khi bean phù hợp đã có trong BeanFactory.
- [AutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): thuộc tính before, beforeName, after và afterName.
- [AutoConfigureAfter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html): ordering giữa auto-configuration classes và phân biệt definition order với instance creation.
- [AutoConfigureOrder API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html): thứ tự tổng quát giữa các auto-configuration không có quan hệ trực tiếp.
- [ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): dựng context độc lập để test auto-configuration và bean conditions.
