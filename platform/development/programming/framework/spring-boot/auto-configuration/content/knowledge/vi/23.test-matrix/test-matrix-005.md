# Dùng withParent để xác minh SearchStrategy trong cây ApplicationContext

## Mục tiêu bài học

Spring cho phép một ApplicationContext có **parent context**. Context con có thể sử dụng bean được cung cấp bởi context cha, trong khi context cha không nhìn thấy bean chỉ được đăng ký ở context con. Kiểu cấu trúc này xuất hiện trong ứng dụng có nhiều vùng cấu hình, ứng dụng servlet có root/child context, hoặc hệ thống cần cô lập một phần bean theo từng context.

Spring Boot cung cấp SearchStrategy để các bean condition quyết định phạm vi tìm kiếm trong cây context. Nếu không hiểu phạm vi này, một auto-configuration có thể bỏ qua bean mặc định vì thấy bean ở parent, hoặc tạo thêm bean ở child dù parent đã có một bean cùng kiểu.

Bài học này tập trung vào cách kiểm chứng ba chiến lược bằng ApplicationContextRunner.withParent(...):

- CURRENT: chỉ tìm trong context hiện tại.
- ANCESTORS: tìm trong tất cả context cha, không tìm context hiện tại.
- ALL: tìm toàn bộ hierarchy, gồm context hiện tại và các ancestor.

Sau bài học, bạn có thể giải thích khác biệt giữa ba chiến lược, dự đoán kết quả của bean condition, viết test parent/child độc lập và xác định khi nào cần dùng chiến lược tường minh thay cho mặc định.

## 1. Vì sao ApplicationContext có parent?

Một ApplicationContext quản lý bean definitions, singleton instances, Environment, event infrastructure và các dịch vụ container khác. Một context có thể được gắn parent để tổ chức nhiều phạm vi cấu hình.

Ví dụ khái niệm:

~~~text
Root ApplicationContext
  - DataSource
  - SharedService
  - Security infrastructure
       |
       +---- Child ApplicationContext A
       |       - Controller A
       |       - ViewResolver A
       |       - Feature A beans
       |
       +---- Child ApplicationContext B
               - Controller B
               - ViewResolver B
               - Feature B beans
~~~

Context con có thể tìm bean ở chính nó và tiếp tục tìm lên parent khi cần. Context cha không tìm ngược xuống các context con. Vì vậy, hai context có thể chứa các bean cùng kiểu nhưng vẫn giữ phạm vi riêng.

Một ví dụ thường gặp là servlet application có root context chứa service/repository và một hoặc nhiều servlet-specific child context chứa controller, handler mapping hoặc view configuration. Context hierarchy cũng có thể được dựng trong test để mô phỏng một module dùng chung và một module riêng.

**Đừng nhầm parent context với kế thừa class Java.** Đây là quan hệ giữa các BeanFactory/ApplicationContext ở runtime. Bean ở parent không được copy vào child; child có thể tra cứu bean ở parent theo quy tắc hierarchy.

## 2. Ba SearchStrategy khác nhau ở phạm vi tìm kiếm

Spring Boot định nghĩa enum SearchStrategy trong package org.springframework.boot.autoconfigure.condition.

| Chiến lược | Phạm vi tìm kiếm | Khi nào điều kiện nhìn thấy bean? |
| --- | --- | --- |
| CURRENT | Chỉ context đang đánh giá condition | Bean phải được đăng ký trong context hiện tại |
| ANCESTORS | Tất cả parent/ancestor; bỏ qua context hiện tại | Bean phải nằm trong một context cha |
| ALL | Toàn bộ cây: context hiện tại và mọi ancestor | Bean có thể nằm ở current hoặc bất kỳ parent nào |

Hình dung khi condition được đánh giá trong Child:

~~~text
                 ALL
       +-----------------------+
       |                       |
   Parent A                Parent B
       |                       |
       +-----------+-----------+
                   |
                Child
                   |
CURRENT:           |  chỉ Child
ANCESTORS: Parent A + Parent B, không gồm Child
ALL:        Parent A + Parent B + Child
~~~

Với một context chỉ có một parent, ANCESTORS và ALL đều có thể nhìn thấy bean ở parent. Khác biệt quan trọng xuất hiện khi bean nằm trong chính child: ANCESTORS bỏ qua nó, còn ALL và CURRENT nhìn thấy nó.

### 2.1. CURRENT

CURRENT giới hạn việc kiểm tra vào BeanFactory của context hiện tại. Nếu child cần một bean được tạo và sở hữu ngay trong child, chiến lược này giúp condition không bị thỏa mãn chỉ vì parent có bean cùng kiểu.

Ví dụ, một child context của mỗi tenant cần tạo một TenantFeature riêng. Parent có thể cung cấp một dịch vụ chung, nhưng không nên làm cho condition của feature cục bộ tự khớp. Khi đó CURRENT là lựa chọn phù hợp.

### 2.2. ANCESTORS

ANCESTORS chỉ tìm các context cha, từ parent trực tiếp đi lên các ancestor cao hơn. Nó bỏ qua bean nằm trong child hiện tại.

Chiến lược này hữu ích khi một feature chỉ nên hoạt động nếu một dịch vụ nền tảng đã được cung cấp ở cấp cha. Ví dụ, một child context chỉ đăng ký adapter nếu root context cung cấp một SharedInfrastructure bean.

Một hệ quả dễ bỏ sót: nếu child đã có bean nhưng parent không có, condition với ANCESTORS vẫn coi bean đó là vắng mặt.

### 2.3. ALL

ALL tìm trong toàn bộ hierarchy. Đây là lựa chọn mặc định của các annotation bean condition trong Spring Boot như ConditionalOnBean và ConditionalOnMissingBean. ConditionalOnSingleCandidate cũng có thuộc tính search.

Với ALL, bean ở parent có thể làm cho ConditionalOnBean khớp trong child. Tương tự, bean ở parent có thể khiến ConditionalOnMissingBean không khớp và ngăn child tạo default bean trùng loại.

### 2.4. Giá trị mặc định là ALL

Trong Spring Boot 3.3, thuộc tính search của ConditionalOnBean và ConditionalOnMissingBean mặc định là SearchStrategy.ALL. ConditionalOnSingleCandidate cũng mặc định tìm toàn bộ hierarchy.

Do đó, code sau:

~~~java
@Bean
@ConditionalOnMissingBean(SharedClient.class)
SharedClient sharedClient() {
    return new DefaultSharedClient();
}
~~~

có thể back off khi parent context đã cung cấp SharedClient, dù child context không có bean đó ở local scope.

Nếu đây không phải hành vi mong muốn, hãy đặt search tường minh:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = SharedClient.class,
        search = SearchStrategy.CURRENT)
SharedClient childSharedClient() {
    return new ChildSharedClient();
}
~~~

Việc chọn CURRENT hay ALL là một phần của contract kiến trúc, không chỉ là chi tiết cú pháp.

## 3. SearchStrategy tác động lên condition, không thay đổi cấu trúc context

SearchStrategy quyết định phạm vi bean condition dùng để kiểm tra. Nó không thay đổi parent-child relationship và không thay đổi quy tắc lookup bean thông thường.

Cần phân biệt ba điều:

1. **Condition search:** annotation có nhìn thấy bean ở parent, child hay cả hai?
2. **Bean lookup/injection:** khi một bean cần dependency, Spring tìm ứng viên theo quy tắc BeanFactory hierarchy, type, qualifier và primary.
3. **Bean ownership:** bean vẫn thuộc context đã đăng ký nó; child không biến bean parent thành local bean của mình.

Ví dụ, nếu parent có SharedClient và child không có, child vẫn có thể inject SharedClient từ parent. Nếu dùng ConditionalOnBean với CURRENT, condition có thể không khớp dù việc lookup thông thường từ child có thể tìm thấy bean ở parent. Đây không phải mâu thuẫn: condition và dependency lookup đang dùng hai quy tắc phạm vi khác nhau.

Ngược lại, nếu child có bean cùng kiểu và dùng CURRENT, condition khớp dựa trên local bean. Điều đó không có nghĩa parent có thể nhìn thấy bean của child.

**SearchStrategy không phải công cụ chọn implementation.** Nó không thay thế @Qualifier hoặc @Primary. Nếu điều kiện khớp và một bean method cần inject một kiểu có nhiều ứng viên, quy tắc autowiring vẫn phải giải quyết được ứng viên, chẳng hạn bằng qualifier hoặc primary.

## 4. Những annotation có thuộc tính search

Trong Spring Boot 3.3, các bean condition thường gặp có thuộc tính search:

| Annotation | Ý nghĩa condition | Tình huống hierarchy |
| --- | --- | --- |
| ConditionalOnBean | Khớp nếu tìm thấy bean thỏa yêu cầu | Child feature phụ thuộc bean ở parent |
| ConditionalOnMissingBean | Khớp nếu không tìm thấy bean thỏa yêu cầu | Quyết định có tạo default trong child hay không |
| ConditionalOnSingleCandidate | Khớp nếu tìm được một ứng viên autowire duy nhất | Kiểm tra dependency dùng chung ở nhiều context |

Ví dụ ConditionalOnBean:

~~~java
@Bean
@ConditionalOnBean(
        value = SharedInfrastructure.class,
        search = SearchStrategy.ANCESTORS)
ChildAdapter childAdapter() {
    return new ChildAdapter();
}
~~~

ChildAdapter chỉ được đăng ký khi một SharedInfrastructure bean tồn tại ở parent/ancestor. Bean cùng kiểu chỉ có trong child không thỏa điều kiện này.

Ví dụ ConditionalOnMissingBean:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = ChildFeature.class,
        search = SearchStrategy.CURRENT)
ChildFeature childFeature() {
    return new DefaultChildFeature();
}
~~~

Bean ChildFeature ở parent không ngăn child tạo implementation cục bộ. Đây là một lựa chọn hợp lý nếu mỗi child cần feature instance riêng.

Ví dụ ConditionalOnSingleCandidate:

~~~java
@AutoConfiguration
@ConditionalOnSingleCandidate(
        value = SharedClient.class,
        search = SearchStrategy.ALL)
class ChildClientAutoConfiguration {
}
~~~

Điều kiện này kiểm tra xem có một ứng viên có thể xác định cho kiểu SharedClient trong phạm vi đã chọn hay không. Nếu nhiều ứng viên phù hợp, primary candidate có thể làm cho việc chọn một bean trở nên rõ ràng. SearchStrategy chỉ thay đổi hierarchy được xét; quy tắc xác định single candidate vẫn được áp dụng.

## 5. Dùng ApplicationContextRunner.withParent để tạo hierarchy trong test

ApplicationContextRunner tạo một context non-web mới cho mỗi lần gọi run. Phương thức withParent(ApplicationContext) cấu hình parent của context sắp được tạo.

Mẫu sử dụng:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(ParentConfiguration.class)
        .run(parent -> {
            new ApplicationContextRunner()
                    .withParent(parent)
                    .withConfiguration(
                            AutoConfigurations.of(ChildAutoConfiguration.class))
                    .run(child -> {
                        // Assert kết quả trong child context.
                    });
        });
~~~

Trình tự là:

1. Runner ngoài tạo và refresh parent context.
2. Callback nhận parent context đang hoạt động.
3. Runner bên trong dùng parent đó để tạo child context.
4. Child được refresh và các condition được đánh giá trong hierarchy.
5. Callback child thực hiện assertion.
6. Child runner đóng child sau khi callback kết thúc; sau đó runner ngoài đóng parent.

AssertableApplicationContext mà runner cung cấp cũng là một ApplicationContext, nên có thể truyền trực tiếp vào withParent.

**Nên dùng AutoConfigurations.of(...) cho cấu hình auto-configuration được kiểm thử.** Cách này giữ đúng vai trò của auto-configuration và thứ tự xử lý so với user configuration. Bean conditions chỉ nhìn thấy các bean definitions đã được xử lý tới thời điểm đánh giá; Spring Boot khuyến nghị đặt ConditionalOnBean/ConditionalOnMissingBean trong auto-configuration và khai báo ordering nếu cần một auto-configuration khác cung cấp bean phụ thuộc.

## 6. Ví dụ JUnit 5 hoàn chỉnh: kiểm tra cả ba chiến lược

Ví dụ dưới đây dùng một interface Marker làm kiểu bean cần tìm. Parent context đăng ký ParentMarker; child context đăng ký các feature theo kết quả condition.

**Tệp:** src/test/java/example/hierarchy/SearchStrategyHierarchyTest.java

~~~java
package example.hierarchy;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.SearchStrategy;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SearchStrategyHierarchyTest {

    @Test
    void allAndAncestorsSeeParentButCurrentDoesNot() {
        new ApplicationContextRunner()
                .withUserConfiguration(ParentConfiguration.class)
                .run(parent -> new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(ParentLookupAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).hasSingleBean(AllFeature.class);
                            assertThat(child).hasSingleBean(AncestorFeature.class);
                            assertThat(child).hasSingleBean(DefaultAllFeature.class);
                            assertThat(child).doesNotHaveBean(CurrentFeature.class);
                        }));
    }

    @Test
    void ancestorsDoesNotSeeBeanDefinedOnlyInCurrentContext() {
        new ApplicationContextRunner()
                .withUserConfiguration(LocalMarkerConfiguration.class)
                .withConfiguration(
                        AutoConfigurations.of(LocalLookupAutoConfiguration.class))
                .run(child -> {
                    assertThat(child).hasSingleBean(LocalMarker.class);
                    assertThat(child).hasSingleBean(AllLocalFeature.class);
                    assertThat(child).hasSingleBean(CurrentLocalFeature.class);
                    assertThat(child).doesNotHaveBean(AncestorLocalFeature.class);
                });
    }

    @Test
    void missingBeanWithDefaultAllBacksOffForParentBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(ParentConfiguration.class)
                .run(parent -> new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(MissingAllAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).doesNotHaveBean(ChildMarker.class);
                            assertThat(child.getBean(Marker.class))
                                    .isSameAs(parent.getBean(ParentMarker.class));
                        }));
    }

    @Test
    void missingBeanWithCurrentCanCreateChildBeanDespiteParentBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(ParentConfiguration.class)
                .run(parent -> new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(MissingCurrentAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).hasSingleBean(ChildMarker.class);
                            assertThat(child.getBean(Marker.class))
                                    .isInstanceOf(ChildMarker.class);
                            assertThat(parent.getBean(Marker.class))
                                    .isInstanceOf(ParentMarker.class);
                        }));
    }

    interface Marker {
    }

    static class ParentMarker implements Marker {
    }

    static class LocalMarker implements Marker {
    }

    static class ChildMarker implements Marker {
    }

    static class AllFeature {
    }

    static class AncestorFeature {
    }

    static class CurrentFeature {
    }

    static class DefaultAllFeature {
    }

    static class AllLocalFeature {
    }

    static class AncestorLocalFeature {
    }

    static class CurrentLocalFeature {
    }

    @Configuration(proxyBeanMethods = false)
    static class ParentConfiguration {

        @Bean
        ParentMarker parentMarker() {
            return new ParentMarker();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class LocalMarkerConfiguration {

        @Bean
        LocalMarker localMarker() {
            return new LocalMarker();
        }
    }

    @AutoConfiguration
    static class ParentLookupAutoConfiguration {

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.ALL)
        AllFeature allFeature() {
            return new AllFeature();
        }

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.ANCESTORS)
        AncestorFeature ancestorFeature() {
            return new AncestorFeature();
        }

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.CURRENT)
        CurrentFeature currentFeature() {
            return new CurrentFeature();
        }

        @Bean
        @ConditionalOnBean(Marker.class)
        DefaultAllFeature defaultAllFeature() {
            return new DefaultAllFeature();
        }
    }

    @AutoConfiguration
    static class LocalLookupAutoConfiguration {

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.ALL)
        AllLocalFeature allLocalFeature() {
            return new AllLocalFeature();
        }

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.ANCESTORS)
        AncestorLocalFeature ancestorLocalFeature() {
            return new AncestorLocalFeature();
        }

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.CURRENT)
        CurrentLocalFeature currentLocalFeature() {
            return new CurrentLocalFeature();
        }
    }

    @AutoConfiguration
    static class MissingAllAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Marker.class)
        ChildMarker childMarker() {
            return new ChildMarker();
        }
    }

    @AutoConfiguration
    static class MissingCurrentAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(
                value = Marker.class,
                search = SearchStrategy.CURRENT)
        ChildMarker childMarker() {
            return new ChildMarker();
        }
    }
}
~~~

### 6.1. Đọc kết quả từng test

**Test 1 — parent có Marker**

ParentConfiguration đăng ký ParentMarker. Child dùng ba chiến lược:
- ALL thấy ParentMarker nên tạo AllFeature.
- ANCESTORS thấy ParentMarker nên tạo AncestorFeature.
- CURRENT chỉ tìm trong child, nơi chưa có Marker, nên không tạo CurrentFeature.
- DefaultAllFeature cũng xuất hiện vì search mặc định của ConditionalOnBean là ALL.

**Test 2 — chỉ child có Marker**

LocalMarkerConfiguration đăng ký Marker trong context hiện tại:
- ALL thấy LocalMarker.
- CURRENT thấy LocalMarker.
- ANCESTORS bỏ qua current context nên không tạo AncestorLocalFeature.

**Test 3 — ConditionalOnMissingBean mặc định**

Parent có Marker, child không có Marker local. ConditionalOnMissingBean mặc định tìm ALL, vì vậy parent bean làm điều kiện không khớp và child không tạo ChildMarker.

**Test 4 — ConditionalOnMissingBean với CURRENT**

Parent vẫn có Marker, nhưng condition chỉ tìm trong child. Child chưa có Marker local, nên default ChildMarker được tạo. Parent vẫn giữ ParentMarker của riêng nó.

Bốn test này xác nhận rằng SearchStrategy ảnh hưởng tới quyết định đăng ký bean trong context đang được refresh. Chúng không yêu cầu kết nối database, HTTP server hay dịch vụ bên ngoài.

## 7. Dependency và lệnh chạy

Yêu cầu Java 17+ và Spring Boot 3.3.x. Trong Gradle project đã quản lý version bằng Spring Boot plugin hoặc BOM:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy test tại module chứa lớp kiểm thử:

~~~bash
# Linux/macOS
./gradlew test --tests "example.hierarchy.SearchStrategyHierarchyTest"

# Windows
gradlew.bat test --tests "example.hierarchy.SearchStrategyHierarchyTest"
~~~

**Kết quả kỳ vọng:** bốn test PASS. Test dùng AssertJ để xác minh bean registration; không có System.out.println nên không có stdout nội dung cố định. Gradle sẽ hiển thị kết quả test theo cấu hình logging của dự án.

Đây là test code được thiết kế cho Spring Boot 3.3/JUnit 5; chưa thực thi trong môi trường dự án cụ thể. Nếu chạy trong module hiện tại, hãy dùng đúng version Spring Boot BOM của module và xác nhận package test trùng với đường dẫn source.

## 8. Khi nào chọn từng chiến lược?

### Chọn ALL khi bean có thể được cung cấp ở bất kỳ tầng nào

Dùng ALL khi feature chỉ cần biết bean có tồn tại trong ứng dụng/context hierarchy hay không. Đây là hành vi mặc định phổ biến cho bean condition của auto-configuration.

Ví dụ:
- Một parent context đã cung cấp shared client.
- Child context không cần tạo thêm default cùng vai trò.
- Một infrastructure bean được đăng ký ở root context nhưng được dùng trong child.

### Chọn CURRENT khi feature thuộc riêng child

Dùng CURRENT khi bean phải được đăng ký ngay trong context đang xét. Đây là cách giữ tính độc lập của từng child context.

Ví dụ:
- Mỗi servlet child context cần một handler riêng.
- Mỗi tenant context cần adapter riêng.
- Parent có một service cùng kiểu nhưng child vẫn phải có implementation local.

Trước khi chọn CURRENT, kiểm tra xem việc tạo thêm bean cùng kiểu ở child có gây ambiguity trong injection hay không. Nếu child cần local bean, hãy định nghĩa rõ tên/qualifier và dependency nào nên dùng local implementation.

### Chọn ANCESTORS khi chỉ parent mới được phép cung cấp dependency

Dùng ANCESTORS khi child chỉ nên bật feature nếu hạ tầng được cung cấp từ parent. Nếu child tự tạo bean đó, condition không khớp; điều này có thể là chủ đích để giữ một ranh giới sở hữu rõ ràng.

Ví dụ:
- Một child adapter chỉ hoạt động khi root context có SharedInfrastructure.
- Feature phụ thuộc vào một registry dùng chung, không muốn bị kích hoạt bởi registry local được khai báo nhầm trong child.

Không chọn ANCESTORS chỉ vì tên của nó có vẻ gần với parent hơn. Hãy xác định liệu bean ở current context có được phép thỏa điều kiện hay không.

## 9. Những lưu ý khi áp dụng trong auto-configuration thực tế

### 9.1. Bean conditions phụ thuộc thứ tự xử lý

ConditionalOnBean và ConditionalOnMissingBean chỉ có thể xét bean definitions đã được xử lý tới thời điểm condition chạy. Vì vậy, Boot khuyến nghị dùng chúng trên auto-configuration; auto-configuration được thiết kế để áp dụng sau cấu hình người dùng.

Nếu một condition phụ thuộc bean do auto-configuration khác tạo, hãy khai báo ordering phù hợp:

~~~java
@AutoConfiguration(after = SharedInfrastructureAutoConfiguration.class)
class ChildFeatureAutoConfiguration {
}
~~~

Thứ tự chỉ giúp bean definition của cấu hình phụ thuộc được xử lý sau cấu hình cung cấp dependency. Nó không tạo bean và không thay thế constructor injection.

### 9.2. Parent bean có thể được inject dù CURRENT không tìm thấy nó

Một tình huống dễ gây nhầm:

- Parent chứa SharedService.
- Child dùng ConditionalOnBean(search = CURRENT) và condition không khớp.
- Một bean khác trong child vẫn có thể inject SharedService từ parent qua lookup bình thường.

Điều đó hợp lệ. CURRENT chỉ giới hạn condition search; nó không tắt khả năng lookup parent của child.

### 9.3. Parent và child có thể chứa cùng kiểu bean

Nếu child tạo bean cùng kiểu với parent, child thường sử dụng bean local của nó khi lookup theo kiểu trong chính child; parent vẫn giữ bean riêng. Hãy dùng qualifier nếu cần phân biệt rõ, nhất là khi có nhiều candidate hoặc dependency được chuyển qua các tầng.

SearchStrategy không giải quyết ambiguity. Nếu condition ALL thấy một bean ở parent và một bean ở child, nó chỉ xác nhận sự hiện diện theo phạm vi; việc inject một dependency đơn vẫn tuân theo quy tắc candidate, @Primary và @Qualifier.

### 9.4. Không dùng condition như cơ chế kiểm soát vòng đời

SearchStrategy không phải công cụ đóng/mở context, chia sẻ instance hoặc quản lý scope. Nó chỉ điều chỉnh nơi bean condition tìm kiếm. Nếu cần bean singleton theo tenant, request hoặc servlet, hãy thiết kế context/scope phù hợp.

### 9.5. Test non-web và web context

ApplicationContextRunner tạo context non-web. Nếu hierarchy thực tế là root WebApplicationContext và servlet child context, hãy dùng WebApplicationContextRunner hoặc dựng context web phù hợp. Ý nghĩa của SearchStrategy không đổi, nhưng context factory và loại bean web cần đúng với ứng dụng thực tế.

## 10. Lỗi thường gặp khi kiểm thử SearchStrategy

1. **Không dùng withParent.** Hai runner độc lập không tạo hierarchy; condition trong child không thể nhìn thấy bean ở context khác nếu context đó không được đặt làm parent.
2. **Dùng CURRENT nhưng mong bean parent thỏa điều kiện.** CURRENT chỉ tìm context đang đánh giá condition.
3. **Dùng ANCESTORS nhưng mong bean child thỏa điều kiện.** ANCESTORS loại current context khỏi phạm vi tìm kiếm.
4. **Cho rằng ALL chỉ tìm parent.** ALL gồm cả current context và mọi ancestor.
5. **Quên mặc định ALL.** ConditionalOnBean/ConditionalOnMissingBean có thể bị ảnh hưởng bởi bean parent dù code không khai báo search.
6. **Nhầm condition search với dependency lookup.** Child có thể inject parent bean dù một condition dùng CURRENT không khớp.
7. **Cho rằng parent nhìn thấy child.** Quan hệ lookup đi từ child lên parent; parent không tra cứu ngược xuống child.
8. **Dùng ConditionalOnMissingBean trên cấu hình thường được xử lý quá sớm.** Condition chỉ biết bean definitions đã xử lý; nên dùng trong auto-configuration và khai báo ordering khi phụ thuộc cấu hình khác.
9. **Kiểm tra bean từ sai scope trong assertion.** Assertion có thể tìm bean ở parent theo mặc định; khi cần kiểm tra local bean, hãy dùng assertion scope hoặc kiểm tra BeanFactory của context nguồn.
10. **Tạo hai bean cùng kiểu rồi không phân biệt.** Condition có thể khớp nhưng autowiring vẫn mơ hồ; dùng qualifier/primary và kiểm tra dependency riêng.
11. **Đóng parent trước khi chạy child.** Child cần parent còn hoạt động trong suốt thời gian test; lồng runner như ví dụ để vòng đời được quản lý đúng.
12. **Dùng ApplicationContextRunner cho test servlet hierarchy mà không kiểm tra loại context.** Với ứng dụng web, chọn runner hoặc context factory phù hợp.

## 11. Checklist khi thiết kế hoặc review condition

Trước khi thêm thuộc tính search, trả lời:

- Bean cần tìm thuộc về context nào: current, parent hay có thể ở bất kỳ tầng nào?
- Nếu parent có bean, child có nên tạo default riêng không?
- Nếu child có bean nhưng parent không có, condition có nên khớp không?
- Có nhiều parent/ancestor không, và bean ở ancestor xa có được tính không?
- Annotation đang dùng là ConditionalOnBean, ConditionalOnMissingBean hay ConditionalOnSingleCandidate?
- Có phụ thuộc vào bean do auto-configuration khác tạo không? Nếu có, thứ tự đã rõ chưa?
- Bean method có dependency type mơ hồ cần qualifier/primary không?
- Test đã tạo parent thật bằng withParent chưa?
- Test đã xác minh cả bean local lẫn bean được kế thừa từ parent chưa?

Một bảng quyết định nhỏ thường đủ để review:

| Bean nằm ở đâu? | CURRENT | ANCESTORS | ALL |
| --- | --- | --- | --- |
| Chỉ ở child | Thấy | Không thấy | Thấy |
| Chỉ ở parent | Không thấy | Thấy | Thấy |
| Ở cả child và parent | Thấy child | Thấy parent | Thấy cả hierarchy |
| Không có ở đâu | Không thấy | Không thấy | Không thấy |

Bảng mô tả phạm vi tìm kiếm. Với ConditionalOnMissingBean, đảo kết quả logic: condition khớp khi không tìm thấy bean phù hợp trong phạm vi đã chọn.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Parent context có Marker, child context không có. ConditionalOnBean(Marker.class, search = CURRENT) có khớp không?

**Đáp án:** Không. CURRENT chỉ xét bean definitions ở child.

**Câu 2.** Child context có Marker, parent không có. ConditionalOnBean(Marker.class, search = ANCESTORS) có khớp không?

**Đáp án:** Không. ANCESTORS chỉ tìm ở các context cha, không xét child hiện tại.

**Câu 3.** Parent có Marker, child không có Marker. ConditionalOnMissingBean(Marker.class) mặc định có tạo bean default ở child không?

**Đáp án:** Không. Search mặc định là ALL, nên bean ở parent được tính và condition missing không khớp.

**Câu 4.** Muốn mỗi child context có thể tạo một default riêng dù parent đã có bean cùng kiểu, nên dùng chiến lược nào?

**Đáp án:** CURRENT cho ConditionalOnMissingBean, nếu chính sách của ứng dụng là chỉ xét bean local trong child.

**Câu 5.** Một bean condition dùng CURRENT không khớp vì bean chỉ nằm ở parent. Một bean khác trong child có thể inject parent bean đó không?

**Đáp án:** Có. SearchStrategy chỉ thay phạm vi condition; lookup/injection thông thường từ child vẫn có thể tìm bean ở parent.

## 13. Ghi nhớ

withParent tạo một ApplicationContext hierarchy thực sự để kiểm chứng bean conditions. CURRENT tìm current context; ANCESTORS tìm các parent mà không xét current; ALL tìm toàn bộ cây. ConditionalOnBean và ConditionalOnMissingBean mặc định dùng ALL, vì vậy một bean ở root/parent có thể ảnh hưởng đến auto-configuration chạy trong child.

Hãy chọn chiến lược dựa trên nơi bean được sở hữu và phạm vi mà feature cần quan sát. Dùng ApplicationContextRunner.withParent để test cả trường hợp bean chỉ ở parent, chỉ ở child, và bean được tìm thấy trong toàn hierarchy. Cuối cùng, nhớ rằng condition search không thay thế bean lookup, qualifier, primary hoặc thứ tự xử lý auto-configuration.

### Tài liệu Spring Boot chính thức

- Spring Boot 3.3 — SearchStrategy Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html
- Spring Boot 3.3 — ConditionalOnBean Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3 — ConditionalOnMissingBean Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 — ApplicationContextRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 — AbstractApplicationContextRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html
