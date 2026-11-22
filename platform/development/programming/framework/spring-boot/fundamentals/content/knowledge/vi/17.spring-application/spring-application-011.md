# Context hierarchy khi ứng dụng có nhiều context

Một ứng dụng Spring không nhất thiết chỉ có một `ApplicationContext`. Trong những kiến trúc có nhiều khu vực cấu hình hoặc nhiều web entry point, ta có thể tổ chức context theo quan hệ **parent–child** (cha–con). Context cha thường giữ các bean dùng chung; context con giữ những bean chỉ thuộc một ứng dụng web, một servlet hoặc một module cụ thể.

Điểm quan trọng của hierarchy là **hướng nhìn thấy bean**:

- Context con có thể tra cứu bean được đăng ký trong chính nó.
- Nếu không tìm thấy bean phù hợp ở local context, việc tra cứu có thể tiếp tục lên context cha.
- Context cha không nhìn xuống context con.
- Hai context anh em (siblings) không tự nhìn thấy bean của nhau.

Mỗi context vẫn là một container riêng, có bean registry, singleton cache và lifecycle riêng. Parent–child hierarchy giúp chia sẻ dependency theo một chiều; nó không hợp nhất tất cả bean thành một registry duy nhất.

## 1. ApplicationContext là gì?

`ApplicationContext` là container cấp cao của Spring. Nó quản lý bean definitions, tạo và kết nối bean, cung cấp resource loading, event publishing, environment và các dịch vụ nền tảng khác.

Một ứng dụng Spring Boot thông thường tạo một application context trong quá trình:

~~~java
@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Trong phần lớn ứng dụng web đơn giản, một context là đủ. Nhưng nếu cần nhiều vùng cấu hình riêng, có thể tạo nhiều context và liên kết chúng thành cây:

~~~text
                 Parent ApplicationContext
                 (bean dùng chung)
                           |
               +-----------+-----------+
               |                       |
               v                       v
       Child Context A          Child Context B
       (API / servlet A)        (API / servlet B)
~~~

Parent cung cấp các bean nền tảng mà cả hai child có thể sử dụng. Child A và Child B không trực tiếp nhìn thấy bean riêng của nhau.

## 2. Vì sao cần context hierarchy?

Một số lý do kiến trúc có thể khiến nhiều context hữu ích:

- **Chia sẻ bean giữa nhiều web application/servlet:** service và repository dùng chung ở parent, còn controller, handler hoặc view resolver nằm ở child.
- **Tách cấu hình theo entry point:** mỗi servlet hoặc khu vực web có mapping, interceptor và controller riêng.
- **Tách module có vòng đời riêng:** một nhóm bean có thể được tạo/đóng theo context con mà vẫn dùng được các dịch vụ chung ở context cha.
- **Phân chia trách nhiệm cấu hình:** parent quản lý infrastructure dùng chung, child quản lý cấu hình chỉ áp dụng cho một khu vực.

Ví dụ, một ứng dụng nội bộ có hai web entry point:

~~~text
Parent context
  ├── UserService
  ├── OrderRepository
  ├── DataSource
  └── SharedClock

Child context: /admin/*
  ├── AdminController
  └── AdminWebConfiguration

Child context: /partner/*
  ├── PartnerController
  └── PartnerWebConfiguration
~~~

Hai child có thể sử dụng `UserService` và `OrderRepository` từ parent. Nhưng cấu hình web và controller của khu vực admin không tự động xuất hiện trong child partner.

Hierarchy có thêm chi phí về cấu hình, quan sát bean và quản lý lifecycle. Không nên tạo nhiều context chỉ để chia package hoặc chia layer trong một ứng dụng bình thường.

## 3. Quy tắc tra cứu bean giữa parent và child

Bean lookup trong hierarchy tuân theo nguyên tắc **local trước, parent sau**:

1. Container hiện tại tìm bean trong registry của chính nó.
2. Nếu không tìm thấy bean phù hợp, nó có thể ủy quyền tra cứu lên parent.
3. Quá trình có thể tiếp tục qua các cấp parent nếu hierarchy có nhiều tầng.
4. Không có bước tra cứu ngược từ parent xuống child.

Sơ đồ:

~~~text
Child.getBean("sharedClock")
           |
           v
  Child có bean local không?
       /          \
     Có            Không
     |               |
     v               v
  Trả local     Hỏi Parent
                    |
                    v
             Parent có bean?
                /      \
              Có        Không
              |           |
              v           v
           Trả bean    Báo không tìm thấy
~~~

### 3.1. Child dùng được bean từ parent

Ví dụ với Spring Framework:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ParentConfiguration {

    @Bean
    Clock sharedClock() {
        return Clock.systemUTC();
    }
}
~~~

Child khai báo service cần bean đó:

~~~java
@Configuration(proxyBeanMethods = false)
class ChildConfiguration {

    @Bean
    ReportService reportService(Clock sharedClock) {
        return new ReportService(sharedClock);
    }
}
~~~

Khi `ChildConfiguration` được nạp vào context con có parent chứa `Clock`, Spring có thể phân giải dependency `Clock` từ context cha.

### 3.2. Parent không dùng được bean chỉ tồn tại ở child

Giả sử child đăng ký `AdminController`. Lời gọi:

~~~java
parentContext.getBean(AdminController.class);
~~~

sẽ không tìm thấy bean đó nếu nó chỉ được đăng ký trong child. Parent không tìm kiếm trong các context con.

Quy tắc này giúp parent không phụ thuộc ngược vào chi tiết triển khai của child. Nếu parent cần chức năng do child cung cấp, ranh giới phụ thuộc có thể đang bị đặt ngược; hãy chuyển abstraction hoặc bean dùng chung lên một module/context phù hợp.

## 4. Bean trùng tên trong child và parent

Một child có thể khai báo bean cùng tên với bean trong parent. Khi tra cứu từ child, bean local có độ ưu tiên trước và che khuất bean cùng tên ở parent trong phạm vi child:

~~~java
@Configuration(proxyBeanMethods = false)
class ParentConfiguration {
    @Bean
    String greeting() {
        return "Hello from parent";
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
class ChildConfiguration {
    @Bean
    String greeting() {
        return "Hello from child";
    }
}
~~~

Kết quả tra cứu:

| Nơi tra cứu | Giá trị nhận được |
|---|---|
| Parent context | `Hello from parent` |
| Child context | `Hello from child` |

Child không thay đổi bean definition hoặc instance trong parent. Nó chỉ có bean local cùng tên, khiến tra cứu từ child ưu tiên bean local.

Trong ứng dụng thực tế, tránh dùng cùng tên cho các bean khác ý nghĩa nếu không có chủ đích rõ ràng. Shadowing có thể khiến người đọc khó biết dependency đang được lấy từ cấp nào. Nếu muốn tùy chỉnh một bean dùng chung cho mọi child, hãy cấu hình bean ở parent hoặc thiết kế một abstraction phù hợp.

### 4.1. Tra cứu theo kiểu và nhiều ứng viên

Khi tra cứu theo kiểu, child có thể sử dụng bean từ parent nếu không có ứng viên local phù hợp. Nếu nhiều ứng viên cùng kiểu tồn tại qua hierarchy, việc phân giải dependency còn phụ thuộc qualifier, primary và quy tắc autowiring của Spring.

Đặc biệt, các API liệt kê bean có thể có semantics khác nhau giữa phạm vi local và ancestor. Ví dụ `getBeanNamesForType` trên một bean factory tập trung vào registry của nó, còn `BeanFactoryUtils.beansOfTypeIncludingAncestors(...)` được thiết kế để xét cả ancestors. Khi cần tổng hợp danh sách bean từ nhiều cấp, hãy chọn API có ý nghĩa rõ ràng và kiểm thử context thực tế.

Đừng giả định rằng mọi collection injection trong child luôn có đúng danh sách bean mà bạn tưởng tượng từ toàn bộ hierarchy. Nếu một pipeline cần tất cả handler ở parent lẫn child, hãy xác định rõ cách tổng hợp và thứ tự của danh sách.

## 5. Mỗi context có bean registry và singleton riêng

Hai context độc lập có thể khai báo bean cùng class, nhưng chúng tạo instance riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class SharedConfiguration {
    @Bean
    SharedClock sharedClock() {
        return new SharedClock();
    }
}
~~~

Nếu `SharedConfiguration` được nạp trong cả parent và child, mỗi context có thể tạo một `SharedClock` singleton riêng. Scope singleton có nghĩa là một instance cho bean definition trong **mỗi container**, không phải một instance toàn JVM.

Trong hierarchy, nếu child không khai báo bean local và tra cứu bean từ parent, child sử dụng instance do parent quản lý. Nếu child khai báo lại bean, nó có instance riêng.

~~~text
Parent context
  sharedClock bean definition
          |
          v
  SharedClock instance P

Child context
  sharedClock bean definition (nếu khai báo riêng)
          |
          v
  SharedClock instance C
~~~

Điều này cũng áp dụng cho các scope khác. Prototype được tạo theo từng lần phân giải ở context sở hữu bean definition; web scope phụ thuộc context và scope environment thích hợp.

## 6. BeanPostProcessor và cấu hình không tự lan truyền giữa các context

Mỗi application context có quá trình đăng ký và xử lý bean riêng. Một `BeanPostProcessor` đăng ký trong child chỉ xử lý bean do child tạo; nó không quay lại xử lý instance đã được tạo trong parent. Ngược lại, processor của parent không tự trở thành processor của child chỉ vì child có parent.

Điều này quan trọng với:

- Annotation processing và proxy AOP.
- Các processor xử lý dependency injection.
- Bean validation hoặc các tích hợp dựa trên BeanPostProcessor.
- Các custom processor của thư viện.

Ví dụ, nếu parent tạo một service singleton trước khi child được khởi tạo, một BeanPostProcessor chỉ được đăng ký trong child không thể áp dụng proxy hoặc callback cho service đó.

Nếu một bean dùng chung cần AOP, transaction hoặc annotation processing, hãy đặt cấu hình và processor cần thiết ở **context sở hữu bean đó**. Không giả định việc khai báo `@EnableTransactionManagement` hoặc processor trong child sẽ làm thay đổi các bean của parent.

Tương tự, một `@Configuration` được nạp trong parent không tự động được xử lý lại trong child. Muốn child có cấu hình riêng, phải đăng ký nó trong child hoặc thông qua cấu hình child import.

## 7. Lifecycle của parent và child

Mỗi context có lifecycle riêng:

- Context được tạo và refresh độc lập.
- Singleton của context được tạo theo dependency/lazy policy của context đó.
- Callback khởi tạo chạy trong quá trình tạo bean thuộc context tương ứng.
- Context có thể được đóng riêng; các singleton do context đó quản lý sẽ đi qua destruction lifecycle.

Một child phụ thuộc bean từ parent nên được đóng trước parent. Nếu parent bị đóng trong khi child vẫn đang sử dụng các bean của parent, dependency của child có thể không còn hoạt động đúng.

Trình tự quản lý thông thường:

~~~text
1. Tạo Parent context
2. Refresh Parent context
3. Tạo Child context, gắn Parent
4. Refresh Child context
5. Sử dụng ứng dụng
6. Đóng Child context
7. Đóng Parent context
~~~

Khi dùng `SpringApplicationBuilder`, Spring Boot quản lý việc xây dựng hierarchy. Nếu ứng dụng tự tạo context bằng API Spring Framework, code cần có trách nhiệm refresh và đóng từng context đúng cách.

### 7.1. Đóng child không có nghĩa đóng parent

Hai context có lifecycle riêng. Khi một child được đóng, các bean do child sở hữu được hủy theo lifecycle của child. Parent vẫn tồn tại cho đến khi được đóng riêng hoặc được một cơ chế quản lý cấp cao đóng lại.

Khi dừng toàn bộ ứng dụng, hãy bảo đảm cả hierarchy được đóng theo đúng thứ tự. Với context do SpringApplicationBuilder quản lý, cần để builder/application lifecycle xử lý theo cách được hỗ trợ thay vì tự ý đóng một context giữa lúc ứng dụng còn chạy.

### 7.2. Prototype vẫn có quy tắc destruction riêng

Hierarchy không thay đổi quy tắc scope. Spring không tự gọi destruction callbacks cho prototype instance sau khi giao cho client, dù bean được yêu cầu từ parent hay child. Nơi tạo prototype vẫn cần chịu trách nhiệm giải phóng tài nguyên của instance đó.

## 8. Tạo context hierarchy bằng SpringApplicationBuilder

Spring Boot cung cấp `SpringApplicationBuilder` để xây dựng quan hệ parent–child thuận tiện:

~~~java
import org.springframework.boot.builder.SpringApplicationBuilder;

public class MultiContextApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(SharedInfrastructureConfiguration.class)
                .child(ApiConfiguration.class)
                .run(args);
    }
}
~~~

Trong ví dụ này:

- `SharedInfrastructureConfiguration` là source cấu hình của context cha.
- `ApiConfiguration` là source cấu hình của context con.
- `run(args)` khởi chạy hierarchy đã được builder định nghĩa.

Ví dụ minh họa cách kết hợp các nguồn cấu hình; các class cần được đánh dấu cấu hình phù hợp và cung cấp dependency cần thiết.

### 8.1. Khai báo parent và child rõ ràng

Có thể viết:

~~~java
new SpringApplicationBuilder()
        .parent(SharedInfrastructureConfiguration.class)
        .child(AdminConfiguration.class)
        .run(args);
~~~

`parent(...)` bổ sung source cho parent application; `child(...)` tạo ứng dụng con với source riêng. Builder còn hỗ trợ sibling để tạo các context con cùng một parent.

### 8.2. Một parent với nhiều child

~~~java
new SpringApplicationBuilder()
        .parent(SharedInfrastructureConfiguration.class)
        .child(AdminConfiguration.class)
        .sibling(PartnerConfiguration.class)
        .run(args);
~~~

Mô hình:

~~~text
SharedInfrastructureConfiguration
              |
        Parent context
          /       \
         /         \
        v           v
  Admin child   Partner child
~~~

Hai child dùng được bean của parent, nhưng không tự nhìn thấy bean local của nhau.

`SpringApplicationBuilder` có thể cấu hình loại ứng dụng web cho từng application trong hierarchy bằng API builder tương ứng. Khi dùng nhiều web context, cần xác định rõ context nào là servlet/reactive/non-web, servlet mapping và server lifecycle. Không nên sao chép cấu hình web của một context sang context khác nếu không cần.

## 9. Tạo hierarchy thủ công với AnnotationConfigApplicationContext

Để hiểu rõ cơ chế parent–child mà không phụ thuộc Boot builder, có thể tạo hai context bằng Spring Framework:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

AnnotationConfigApplicationContext parent =
        new AnnotationConfigApplicationContext();
parent.register(ParentConfiguration.class);
parent.refresh();

AnnotationConfigApplicationContext child =
        new AnnotationConfigApplicationContext();
child.setParent(parent);
child.register(ChildConfiguration.class);
child.refresh();

try {
    ReportService service = child.getBean(ReportService.class);
    service.generate();

    Clock clock = child.getBean(Clock.class);
    System.out.println(clock.instant());
} finally {
    child.close();
    parent.close();
}
~~~

Trong ví dụ:

- Parent đăng ký `Clock`.
- Child đăng ký `ReportService`, bean cần `Clock`.
- Child có thể inject `Clock` từ parent.
- Parent không thể lấy `ReportService` từ child.
- Child được đóng trước parent.

Khi dùng API thủ công, phải gọi `refresh()` sau khi đăng ký cấu hình và gắn parent. Nếu đăng ký source sau khi context đã refresh, không nên mong bean definition tự được xử lý như một lần bootstrap bình thường.

## 10. Mô hình root context và DispatcherServlet child context

Trong cấu hình Spring MVC truyền thống (trước khi dùng Spring Boot auto-configuration phổ biến), một web application thường có:

- **Root WebApplicationContext:** giữ service, repository, datasource và các bean dùng chung.
- **DispatcherServlet WebApplicationContext:** giữ controller, handler mapping, view resolver và cấu hình web dành cho servlet.

Mô hình:

~~~text
Servlet container
       |
       v
Root WebApplicationContext
  ├── Services
  ├── Repositories
  └── DataSource
       |
       v
DispatcherServlet
       |
       v
Child WebApplicationContext
  ├── Controllers
  ├── HandlerMappings
  └── ViewResolvers
~~~

Child context của DispatcherServlet có thể sử dụng service ở root context. Root context không phụ thuộc vào controller trong child. Cách chia này giúp nhiều DispatcherServlet có thể dùng chung infrastructure nhưng giữ cấu hình web riêng.

### 10.1. Spring Boot có tự tạo hierarchy này không?

Một ứng dụng Spring Boot web thông thường thường chạy với **một application context** chứa cả web infrastructure và các bean ứng dụng. Boot không tự động tạo root context và một child context riêng cho DispatcherServlet chỉ vì ứng dụng có Spring MVC.

Hierarchy chỉ xuất hiện khi ứng dụng hoặc framework cấu hình nó một cách rõ ràng, ví dụ thông qua nhiều SpringApplication hoặc `SpringApplicationBuilder`, hay khi tích hợp một kiến trúc web đặc thù.

Vì vậy, không nên tạo parent–child context theo thói quen của các ứng dụng Spring MVC truyền thống nếu ứng dụng Boot chỉ có một web server và một nhóm controller.

## 11. Component scanning trong từng context

Mỗi context có cấu hình scan riêng. Nếu cả parent và child cùng scan một package lớn, một số component có thể được đăng ký trong cả hai context, tạo ra hai instance độc lập.

Ví dụ không nên:

~~~java
@Configuration
@ComponentScan("com.example")
class ParentConfiguration {
}
~~~

~~~java
@Configuration
@ComponentScan("com.example")
class ChildConfiguration {
}
~~~

Nếu cả hai scan cùng toàn bộ package, service có thể xuất hiện ở cả parent và child. Khi child tra cứu bean local, bean local có thể che khuất bean parent, khiến ứng dụng khó đoán instance nào được sử dụng.

Nên phân chia phạm vi:

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan("com.example.shared")
class ParentConfiguration {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan("com.example.admin.web")
class AdminChildConfiguration {
}
~~~

Parent scan các component dùng chung; child scan component web riêng. Có thể dùng `@Import` để đăng ký một cấu hình cụ thể thay vì scan nếu module nhỏ.

## 12. Environment và property giữa các context

`Environment` chứa property sources, active profiles và các thông tin môi trường dùng để cấu hình ứng dụng. Trong hierarchy, mỗi context có thể có Environment riêng hoặc được cấu hình để chia sẻ/ kế thừa theo cách builder và ứng dụng lựa chọn.

Không nên giả định rằng:

- mọi property được khai báo trong child chắc chắn ghi đè parent theo cùng một quy tắc ở mọi setup;
- active profile của parent và child luôn độc lập;
- một thay đổi Environment ở context này tự động cập nhật mọi context khác.

Khi dùng `SpringApplicationBuilder`, cần đọc semantics của phiên bản Boot đang dùng về việc chia sẻ Environment giữa parent/child và các tùy chỉnh builder. Nếu tự tạo context thủ công, có thể gắn Environment phù hợp trước khi refresh.

Ví dụ thiết lập Environment riêng:

~~~java
AnnotationConfigApplicationContext child =
        new AnnotationConfigApplicationContext();

var environment = new org.springframework.core.env.StandardEnvironment();
environment.setActiveProfiles("admin");
child.setEnvironment(environment);
child.setParent(parent);
child.register(AdminConfiguration.class);
child.refresh();
~~~

Đoạn code minh họa một child có Environment được thiết lập riêng. Nếu muốn chia sẻ property source hoặc profile với parent, hãy cấu hình điều đó một cách tường minh và kiểm thử thứ tự property resolution.

## 13. Application events trong hierarchy

Các context có event publisher riêng. Khi một event được publish từ child context, Spring có thể chuyển tiếp event lên các context cha theo cơ chế của `ApplicationContext`. Parent không tự phát event xuống các child.

Ví dụ:

~~~java
child.publishEvent(new CustomApplicationEvent(child, "updated"));
~~~

Listener ở child có thể nhận event trong context của nó; listener ở parent cũng có thể nhận event được chuyển tiếp từ child. Nhưng event được publish từ parent không tự động được phát xuống child contexts.

Điều này cần được lưu ý khi cùng một listener hoặc cấu hình event được đăng ký ở nhiều context: có thể nhận cùng một event qua nhiều nơi nếu listener được cấu hình ở cả child và parent. Hãy xác định rõ nơi sở hữu listener và tránh xử lý trùng.

Với lifecycle events như `ContextRefreshedEvent`, mỗi context có lifecycle riêng và có thể phát event tương ứng khi refresh. Listener ở parent có thể thấy event được chuyển tiếp từ child, nên cần phân biệt context nguồn nếu logic chỉ nên chạy một lần ở cấp root.

## 14. Hierarchy không phải ranh giới bảo mật hay process isolation

Parent và child cùng chạy trong một JVM, cùng không gian bộ nhớ và thường cùng một tiến trình ứng dụng. Việc tách context không phải sandbox:

- Child có thể tra cứu bean của parent.
- Bean parent có thể chứa credential hoặc client dùng chung.
- Một lỗi nghiêm trọng trong JVM có thể ảnh hưởng toàn bộ context.
- Không có cách ly CPU, memory hoặc quyền hệ điều hành chỉ nhờ hierarchy.

Nếu cần cô lập bảo mật, khả năng scale, deploy hoặc fault isolation, hãy xem xét process/service boundary, container hoặc cơ chế bảo mật thực sự. Không dùng context hierarchy như một lớp bảo vệ dữ liệu giữa các nhóm người dùng.

## 15. Khi nào nên và không nên dùng nhiều context?

| Tình huống | Nhận định |
|---|---|
| Nhiều DispatcherServlet cần cấu hình web riêng nhưng chia sẻ service/repository | Có thể phù hợp với root/child contexts |
| Nhiều web module có vòng đời và bean registry riêng | Có thể phù hợp nếu ranh giới rõ |
| Ứng dụng Boot đơn giản chỉ có một server và một API | Thường chỉ cần một context |
| Muốn chia package controller/service/repository | Component scan và package structure thường đủ |
| Muốn có nhiều môi trường dev/test/prod | Dùng profiles/property sources, không cần nhiều context chỉ vì môi trường |
| Muốn cách ly bảo mật hoặc lỗi giữa module | Context hierarchy không cung cấp isolation đủ mạnh |
| Muốn chạy hai service có thể deploy/scale độc lập | Tách process/service thường phù hợp hơn |

Mỗi context thêm chi phí về:

- Cấu hình bootstrap và component scanning.
- Quản lý parent/child lifecycle.
- Phân biệt bean local và bean ancestor.
- Điều tra log, events và conditions.
- Tránh duplicate bean và tạo instance ngoài ý muốn.
- Kiểm thử các cấu hình ở từng cấp.

Chỉ nên tạo hierarchy khi có nhu cầu kiến trúc cụ thể mà một context đơn không thể biểu đạt gọn gàng.

## 16. Kiểm thử context hierarchy

Có thể kiểm thử quy tắc nhìn thấy bean bằng hai context thật:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;

class ContextHierarchyTest {

    @Test
    void childCanUseParentBeanButParentCannotUseChildBean() {
        var parent = new AnnotationConfigApplicationContext(
                ParentConfiguration.class);

        var child = new AnnotationConfigApplicationContext();
        child.setParent(parent);
        child.register(ChildConfiguration.class);
        child.refresh();

        try {
            assertThat(child.getBean(Clock.class)).isNotNull();
            assertThat(child.getBean(ReportService.class)).isNotNull();

            assertThrows(
                    NoSuchBeanDefinitionException.class,
                    () -> parent.getBean(ReportService.class)
            );
        } finally {
            child.close();
            parent.close();
        }
    }
}
~~~

Ví dụ giả định `ParentConfiguration` đăng ký `Clock` và `ChildConfiguration` đăng ký `ReportService` cần `Clock`. Có thể mở rộng test để kiểm tra:

- Bean cùng tên ở child có che khuất bean parent trong child lookup không.
- Hai context có tạo singleton instance riêng khi cùng khai báo một kiểu không.
- BeanPostProcessor ở child không xử lý bean đã được tạo trong parent.
- Event từ child được listener ở parent nhận theo đúng kỳ vọng.
- Đóng child trước parent không làm rò rỉ tài nguyên.
- Component scan không đăng ký duplicate component ở cả hai cấp.

### 16.1. Kiểm thử Spring Boot builder

Với ứng dụng Boot, có thể kiểm tra hierarchy được tạo bằng `SpringApplicationBuilder` và xác nhận:

~~~java
ConfigurableApplicationContext child =
        new SpringApplicationBuilder(ParentConfiguration.class)
                .child(ChildConfiguration.class)
                .run();

try {
    assertThat(child.getParent()).isNotNull();
    assertThat(child.getBean(ReportService.class)).isNotNull();
} finally {
    child.close();
}
~~~

Đây là khung minh họa; tùy cách builder quản lý hierarchy và context, cần bảo đảm parent cũng được đóng đúng lifecycle. Trong test thật, nên dùng try/finally hoặc cơ chế quản lý context phù hợp để đóng cả parent lẫn child, và không để context từ test này rò sang test khác.

## 17. Lỗi thường gặp khi có nhiều context

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Child không inject được service | Service chưa được đăng ký ở parent, parent chưa refresh hoặc child chưa gắn đúng parent | Kiểm tra bootstrap order và bean definition |
| Parent không tìm thấy controller child | Nhầm hướng nhìn thấy bean | Đưa abstraction cần dùng lên parent hoặc gọi từ child |
| Bean bị tạo hai lần | Cùng cấu hình/component được đăng ký ở cả parent và child | Thu hẹp component scan và xác định nơi sở hữu bean |
| Child dùng bean khác mong đợi | Bean local che khuất bean cùng tên ở parent | Kiểm tra local bean names và qualifier |
| AOP/transaction không hoạt động với service parent | Processor chỉ được đăng ký ở child | Đăng ký processor/configuration tại context sở hữu service |
| Child hoạt động lỗi sau khi parent đóng | Child vẫn phụ thuộc bean parent đã bị hủy | Đóng child trước parent |
| Collection injection thiếu hoặc thừa bean | API lookup chỉ xét local hoặc ancestor theo semantics khác nhau | Chọn API including ancestors và kiểm thử danh sách |
| Event listener xử lý hai lần | Listener được đăng ký ở nhiều context hoặc event được chuyển tiếp lên parent | Xác định context sở hữu listener và kiểm tra event source |
| Context startup phức tạp, khó chẩn đoán | Nhiều tầng scan/import/auto-configuration | Giảm số context và làm rõ ranh giới module |

## 18. Nguyên tắc thiết kế context hierarchy

1. Chỉ tạo nhiều context khi có ranh giới lifecycle, web entry point hoặc cấu hình thực sự cần tách.
2. Đặt bean dùng chung ở parent; đặt bean đặc thù ở child.
3. Giữ hướng dependency một chiều: child có thể phụ thuộc parent, parent không phụ thuộc child.
4. Tránh quét cùng package ở nhiều context nếu không muốn có nhiều instance.
5. Nhớ rằng singleton được quản lý theo từng context, không phải toàn JVM.
6. Đăng ký BeanPostProcessor và AOP infrastructure ở context sở hữu bean cần được xử lý.
7. Đóng child trước parent và giải phóng tài nguyên đúng lifecycle.
8. Xác định rõ Environment, profiles, event listeners và collection lookup khi có nhiều cấp.
9. Không coi hierarchy là ranh giới bảo mật hoặc process isolation.
10. Kiểm thử bean visibility và lifecycle bằng các context thực tế.

Context hierarchy cho phép Spring tổ chức một ứng dụng thành parent và child contexts: parent cung cấp bean dùng chung, child cung cấp bean riêng và có thể tra cứu ngược lên parent. Mỗi context vẫn có registry, singleton cache, processor và lifecycle riêng. Khi dùng đúng, mô hình này hữu ích cho nhiều web entry point hoặc module có cấu hình độc lập; với một ứng dụng Spring Boot thông thường, một context đơn thường dễ vận hành và dễ hiểu hơn.
