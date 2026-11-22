# Phân biệt tạo ApplicationContext, đăng ký BeanDefinition và refresh trong Spring Boot

## 1. Ba thao tác liên tiếp nhưng có ý nghĩa khác nhau

Khi một ứng dụng Spring Boot khởi chạy, ba khái niệm thường bị gọi chung là “Spring tạo bean”: **tạo ApplicationContext**, **đăng ký định nghĩa bean** và **refresh context**. Hiểu rõ ranh giới giúp giải thích tại sao trong một số thời điểm Spring “biết” về một bean nhưng chưa có instance để sử dụng, vì sao BeanFactoryPostProcessor có thể tác động vào cấu hình và tại sao lỗi khởi tạo thường chỉ xuất hiện lúc refresh.

Ba thao tác có thể tách bằng cách diễn đạt ngắn:

1. **Tạo context:** tạo đối tượng container (và tùy loại context, tạo/chuẩn bị BeanFactory bên trong). Container **chưa hoàn thành khởi tạo**.
2. **Đăng ký BeanDefinition:** đưa **metadata/công thức tạo bean** vào registry. Spring đã biết phải tạo loại đối tượng nào, với tên, scope, điều kiện và các dependency tương ứng; **chưa đồng nghĩa đã gọi constructor hoặc tạo instance**.
3. **refresh():** hoàn thiện quá trình khởi tạo context: chuẩn bị môi trường, xử lý và bổ sung bean definitions, đăng ký các post-processor, khởi tạo các singleton non-lazy, thiết lập hạ tầng lifecycle/events và thông báo context đã refresh. Sau khi thành công, context sẵn sàng phục vụ việc lấy/sử dụng bean theo phạm vi của nó.

Đây là mô hình giải thích về **Spring ApplicationContext**. Với Spring Boot bình thường, lập trình viên thường chỉ gọi **SpringApplication.run(...)**; Boot sẽ điều phối việc tạo context, nạp cấu hình và gọi **refresh()** nội bộ. Không cần tự gọi refresh trên context Boot đã khởi chạy.

## 2. Sơ đồ vòng đời

~~~text
              Tạo ApplicationContext
              (new context / Boot tạo)
                         |
                         v
               Context chưa refresh
                         |
                         v
         Đăng ký các nguồn cấu hình/định nghĩa
          registerBean(...), register(...),
             scan(...), XML, auto-config...
                         |
                         v
               BeanDefinition registry
           tên bean, class, scope, metadata
                         |
                Chưa phải bean instance
                         |
                         v
                    refresh()
                         |
          +--------------+---------------+
          | Chuẩn bị context/BeanFactory |
          | Xử lý config classes, scan   |
          | Chạy factory post-processors |
          | Đăng ký BeanPostProcessors   |
          | Khởi tạo singleton non-lazy  |
          | Hoàn thiện lifecycle/events  |
          +--------------+---------------+
                         |
                         v
              Context hoạt động (active)
                         |
             getBean(...), gọi business logic
                         |
                         v
                 close() / shutdown
~~~

Cần đọc sơ đồ theo hướng **khái niệm**, không suy luận rằng mọi định nghĩa bean đều được đăng ký trước khi bắt đầu refresh. Ví dụ, một class **@Configuration** có các phương thức **@Bean** có thể đã được đăng ký làm nguồn cấu hình từ trước, nhưng **các BeanDefinition do @Bean sinh ra** được phát hiện/đăng ký trong bước xử lý configuration class khi refresh. Component scanning và auto-configuration cũng có thể góp phần phát sinh thêm bean definitions trong giai đoạn này.

Một điểm phân biệt nữa: **refresh context** không phải là hot reload mã nguồn hay tự động cập nhật dữ liệu cấu hình mỗi lần file thay đổi.

## 3. Giai đoạn 1 — Tạo context là tạo bộ chứa

Một số cách tạo context bằng Spring Framework:

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
~~~

Đây là constructor **không tham số**, nên ta chủ động quyết định khi nào đăng ký cấu hình và khi nào refresh. **AnnotationConfigApplicationContext** là một implementation dùng được với Java configuration và annotation-based bean registration.

Trước khi gọi refresh:

- Đối tượng **context** đã tồn tại.
- Nó có các API registry / BeanFactory để nhận định nghĩa bean. Bản thân loại context này cũng có thể chuẩn bị một số định nghĩa hạ tầng annotation ngay từ constructor, nên **không nên khẳng định số lượng BeanDefinition bằng 0**.
- **context.isActive()** chưa biểu thị một context đã khởi động đầy đủ.
- Các bean nghiệp vụ không tự được khởi tạo chỉ vì vừa gọi constructor không tham số.

**Điểm khác biệt rất quan trọng giữa các constructor:**

~~~java
// Cách A: tự điều khiển các pha; chưa refresh ở dòng đầu.
AnnotationConfigApplicationContext ctx =
        new AnnotationConfigApplicationContext();
ctx.register(MyConfiguration.class);
ctx.refresh();

// Cách B: constructor nhận configuration class và tự refresh.
AnnotationConfigApplicationContext ready =
        new AnnotationConfigApplicationContext(MyConfiguration.class);
~~~

Hai đoạn chỉ là **minh họa API**; cần tự định nghĩa **MyConfiguration** trước khi dùng. Ở cách B, **constructor có Class<?>... đầu vào tự đăng ký nguồn cấu hình và refresh**, nên sau khi constructor trả về, context thường đã sẵn sàng nếu startup thành công. Không suy diễn từ câu “new context” rằng **mọi constructor của mọi loại context** đều ở trạng thái chưa refresh.

Ngoài ra, **GenericApplicationContext** giữ một **DefaultListableBeanFactory** nội bộ để nhận definitions trước refresh; nhiều implementation **AbstractRefreshableApplicationContext** có cách quản lý BeanFactory khác. Luôn đọc contract của loại context cụ thể.

## 4. Giai đoạn 2 — Đăng ký BeanDefinition là đăng ký bản mô tả

**BeanDefinition** lưu thông tin dùng để tạo và cấu hình bean, có thể gồm:

| Thuộc tính / thông tin | Ý nghĩa |
| --- | --- |
| Bean name | Tên dùng để tra cứu một bean |
| Bean class hoặc factory method | Loại đối tượng hoặc cách tạo đối tượng |
| Scope | singleton, prototype hoặc scope được cung cấp phù hợp |
| Constructor arguments / property values | Dữ liệu và dependency cần truyền |
| Lazy initialization | Có hoãn việc tạo bean hay không |
| Initialization / destroy metadata | Cơ chế khởi tạo/giải phóng theo lifecycle |
| Qualifiers, primary, dependency metadata | Hỗ trợ chọn bean và giải quyết dependency |

**Định nghĩa** là công thức, còn **instance** là sản phẩm được tạo theo công thức đó. Một bean name được registry nhận biết chưa khẳng định Spring đã gọi constructor.

Các con đường phổ biến để hình thành BeanDefinition:

- **context.registerBean("greetingService", GreetingService.class)**: đăng ký bằng lập trình, trực tiếp gắn tên với class và metadata.
- **context.register(AppConfig.class)**: đăng ký một class cấu hình làm nguồn; các phương thức **@Bean** sẽ được xử lý trong pha startup.
- **@ComponentScan** / **context.scan(...)**: tìm các class component và đăng ký định nghĩa tương ứng.
- **@Import**, configuration classes, XML và auto-configuration của Boot: thêm definitions dựa trên các nguồn và điều kiện.
- **BeanDefinitionRegistryPostProcessor**: có thể đăng ký/thay đổi definitions trong giai đoạn container đang xử lý cấu hình.

### Hai kiểm tra không tương đương

~~~java
context.containsBeanDefinition("greetingService");
context.getBeanFactory().containsSingleton("greetingService");
~~~

- **containsBeanDefinition** hỏi registry đã có **BeanDefinition với tên đó** chưa.
- **containsSingleton** hỏi singleton registry đang chứa **instance singleton với tên đó** chưa.

Có thể thấy **true / false** sau khi đăng ký định nghĩa nhưng trước refresh; sau refresh với bean singleton non-lazy, thường là **true / true**.

**Ngoại lệ cần nhớ:** có những singleton được đăng ký trực tiếp bằng **registerSingleton(...)** và không nhất thiết có BeanDefinition; BeanDefinition cũng có thể thuộc scope prototype hoặc lazy và chưa có instance ngay sau refresh. Vì vậy không dùng một trong hai phép kiểm tra làm định nghĩa tuyệt đối cho phép còn lại.

## 5. Giai đoạn 3 — refresh() mới khởi tạo context hoàn chỉnh

Trong các context thuộc **AbstractApplicationContext**, phương thức **refresh()** là mốc thực hiện quy trình startup. Tùy phiên bản và loại context, các công việc tiêu biểu gồm:

1. **Chuẩn bị trạng thái và property sources** của context.
2. **Chuẩn bị BeanFactory**, gắn các thành phần hạ tầng của context.
3. **Chạy BeanDefinitionRegistryPostProcessor và BeanFactoryPostProcessor**, gồm việc phân tích class cấu hình, component scan và thêm/sửa definitions. Với **@Configuration**, đây là lúc các method **@Bean** thường được xử lý thành bean definitions.
4. **Đăng ký BeanPostProcessor**. Chúng có thể tham gia các bước trước/sau khởi tạo bean, hỗ trợ tiêm dependency, xử lý một số annotation và tạo proxy khi có cơ chế phù hợp.
5. **Khởi tạo message source, event multicaster** và những thành phần hạ tầng liên quan.
6. Thực thi hook của context, ví dụ **onRefresh()**; trong một web context, giai đoạn này có thể liên quan việc tạo/khởi động web server.
7. **preInstantiateSingletons:** tạo các singleton **không lazy** còn lại, giải quyết dependency và chạy các callback khởi tạo tương ứng.
8. **Hoàn tất refresh:** khởi động một số lifecycle bean và phát **ContextRefreshedEvent**.

Đây là tóm tắt có giá trị học tập, **không phải danh sách API bất biến hoặc thứ tự đủ mọi internal hook**. Một số bean hạ tầng hoặc post-processor có thể được tạo **trước** giai đoạn khởi tạo các singleton ứng dụng. Vì thế câu “refresh mới tạo bean” phải hiểu là **refresh điều phối quá trình khởi tạo đầy đủ**, không phải Spring bảo đảm hoàn toàn không có bean instance nào tồn tại trước đó.

### refresh xử lý dependency ra sao?

Giả sử **OrderService** cần **OrderRepository** qua constructor:

~~~java
public OrderService(OrderRepository repository) {
    this.repository = repository;
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Khi chuẩn bị tạo **OrderService**, BeanFactory phải tìm một bean **OrderRepository** phù hợp; có thể phải tạo repository trước service. Nếu thiếu dependency và không có cơ chế optional, startup có thể thất bại ở refresh (với singleton eager), thay vì ở lúc chỉ đăng ký một BeanDefinition.

**@PostConstruct**, **InitializingBean.afterPropertiesSet()**, init-method và BeanPostProcessor tham gia vào lifecycle tạo bean theo contract của từng cơ chế. Chúng không phải synonym với toàn bộ phương thức **ApplicationContext.refresh()**.

### Khi nào context được coi là sẵn sàng?

**ContextRefreshedEvent** cho biết refresh của context đã hoàn tất. Trong Spring Boot, startup thông thường còn có bước chạy **ApplicationRunner** / **CommandLineRunner** và phát **ApplicationReadyEvent** sau khi refresh thành công. Vì vậy:

- **ContextRefreshedEvent**: mốc của Spring Framework / context.
- **ApplicationReadyEvent**: mốc Spring Boot sau các runner.
- **Readiness của hệ thống triển khai**: có thể phụ thuộc health checks, readiness probes và các dịch vụ bên ngoài.

Không đồng nhất ba mốc này.

## 6. Ví dụ Java 17+: quan sát rõ ba giai đoạn

Ví dụ sau dùng trực tiếp **AnnotationConfigApplicationContext** để tách các giai đoạn. Có thể đặt trong dự án Spring Boot Maven tạo bằng Spring Initializr với **Java 17+**, dependency **Spring Boot Starter** và plugin build mặc định; đây là bài tập **Spring Framework container API** chạy trong một project có dependency Spring, nên phương thức **main** cố ý không gọi **SpringApplication.run**.

File **src/main/java/com/example/demo/ContextPhasesDemo.java**:

~~~java
package com.example.demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

@SpringBootApplication
public class ContextPhasesDemo {

    public static class GreetingService {
        public GreetingService() {
            System.out.println("5 | GreetingService constructed");
        }

        public String greet() {
            return "Xin chao Spring";
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        System.out.println("1 | created; active=" + context.isActive());

        // Chỉ đăng ký BeanDefinition; chưa tạo instance.
        context.registerBean("greetingService", GreetingService.class);

        System.out.println("2 | definition="
                + context.containsBeanDefinition("greetingService"));
        System.out.println("3 | singleton instance="
                + context.getBeanFactory()
                        .containsSingleton("greetingService"));

        // Refresh làm context xử lý definitions, tạo singleton non-lazy.
        context.refresh();

        System.out.println("6 | refreshed; active=" + context.isActive());
        System.out.println("7 | singleton instance="
                + context.getBeanFactory()
                        .containsSingleton("greetingService"));
        System.out.println("8 | " + context.getBean(GreetingService.class).greet());

        context.close();
        System.out.println("9 | closed; active=" + context.isActive());
    }
}
~~~

**Vai trò của @SpringBootApplication trong file này:** annotation giúp project Spring Boot nhận diện main class theo cấu hình build thông thường. Vì **main** tự tạo **AnnotationConfigApplicationContext** thay vì gọi **SpringApplication.run**, annotation trên main class **không tự kích hoạt Boot auto-configuration** cho context thủ công đó. Để tạo một Boot runtime đầy đủ, cần dùng luồng bootstrap của Spring Boot.

### Chạy chương trình

Trong thư mục dự án Maven được tạo bởi Spring Initializr, bảo đảm đây là main class mục tiêu, sau đó chạy:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell/cmd:
# .\mvnw.cmd spring-boot:run
~~~

Các dòng do chương trình tự in (không tính log build hay thư viện) theo thứ tự:

~~~text
1 | created; active=false
2 | definition=true
3 | singleton instance=false
5 | GreetingService constructed
6 | refreshed; active=true
7 | singleton instance=true
8 | Xin chao Spring
9 | closed; active=false
~~~

Mã cố tình dùng số **5** cho log constructor để dễ thấy: constructor **không chạy ở bước đăng ký definition**, mà chạy **trong refresh** và trước khi dòng **6** in ra. Không có dòng số **4** trong ví dụ; đây là cách đánh dấu mốc constructor xen giữa hai bước quan sát. Các dòng trên là output do chương trình in; dependency/build tool có thể in log riêng.

### Phân tích từng điểm quan sát

| Mốc | Code chính | Kết quả | Giải thích |
| --- | --- | --- | --- |
| Sau constructor context | **new AnnotationConfigApplicationContext()** | active=false | Context tồn tại nhưng chưa refresh |
| Sau registerBean | **containsBeanDefinition(...)** | true | Registry đã có bản mô tả |
| Ngay sau registerBean | **containsSingleton(...)** | false | Chưa tạo singleton instance |
| Trong refresh | **new GreetingService()** do container gọi | In log constructor | Tạo singleton non-lazy |
| Sau refresh | **isActive()** và singleton check | true / true | Context hoạt động, bean đã có |
| Sau getBean | **greet()** | In câu chào | Gọi method trên instance do Spring quản lý |
| Sau close | **isActive()** | false | Context đã đóng |

**Lưu ý về tính runnable:** đây là chương trình Java 17+ **có dependency Spring Boot/Spring Framework**, không thể biên dịch bằng lệnh **javac ContextPhasesDemo.java** thuần túy nếu không cung cấp Spring jars trên classpath. Maven Wrapper ở trên đảm nhiệm classpath và chạy main class. Nếu dự án có nhiều main classes, cần chọn main class bằng cấu hình plugin tương ứng.

## 7. Trường hợp @Configuration và @Bean: definition có thể xuất hiện trong refresh

Ví dụ ở phần 6 đăng ký **greetingService** bằng **registerBean**, nên BeanDefinition tồn tại ngay sau lời gọi. Với class **@Configuration** có **@Bean**, sự kiện đăng ký khác một chút:

~~~java
@Configuration
public class AppConfig {

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

Đây là **minh họa cấu hình**, cần các import **org.springframework.context.annotation.Configuration** và **org.springframework.context.annotation.Bean**, cùng class **GreetingService** tương ứng.

Nếu làm:

~~~java
AnnotationConfigApplicationContext ctx =
        new AnnotationConfigApplicationContext();

ctx.register(AppConfig.class);
// Lúc này AppConfig là nguồn cấu hình được đăng ký.
ctx.refresh();
// Trong refresh, @Bean methods được phân tích để tạo definitions.
GreetingService service = ctx.getBean(GreetingService.class);
ctx.close();
~~~

Khi **register(AppConfig.class)** trả về, **AppConfig** đã được ghi nhận, nhưng không được mặc định hiểu rằng BeanDefinition **greetingService** của mọi phương thức **@Bean** đã được phân tích xong ngay lúc đó. Spring dùng **ConfigurationClassPostProcessor** trong quá trình refresh để phân tích class cấu hình, xử lý các nguồn import/scan và đăng ký những bean definitions suy ra.

Vì vậy câu hỏi **“bean definition có tồn tại trước refresh không?”** phụ thuộc **cách đăng ký**:

- Dùng **registerBean(...)** trực tiếp: definition của bean đó có trước refresh.
- Dùng **register(AppConfig.class)** chứa **@Bean**: source configuration có trước refresh; definition do @Bean tạo ra có thể được bổ sung **trong refresh**.
- Dùng **component scanning**: các định nghĩa có thể được scan/đăng ký trước refresh hoặc trong xử lý configuration class, tùy cách khởi tạo.
- Dùng **Spring Boot auto-configuration**: các định nghĩa được bổ sung dựa trên classpath, conditions và property trong quá trình bootstrap/refresh.

Đừng suy diễn rằng toàn bộ definitions đã “đóng băng” ngay trước refresh.

## 8. Phân biệt BeanDefinition, BeanFactory, bean instance và ApplicationContext

| Thành phần | Câu hỏi nó trả lời |
| --- | --- |
| **BeanDefinition** | Bean nên được tạo/cấu hình thế nào? |
| **BeanDefinitionRegistry** | Hệ thống đã đăng ký những mô tả bean nào? |
| **BeanFactory** | Làm thế nào tìm, tạo và quản lý bean theo metadata và scope? |
| **ApplicationContext** | Làm sao cung cấp BeanFactory cùng cấu hình, lifecycle, resource, sự kiện và hạ tầng khác? |
| **Bean instance** | Đối tượng Java thực tế nào đang được ứng dụng sử dụng? |

**Singleton bean** mặc định được quản lý theo **một container**, không phải singleton tuyệt đối cho toàn bộ JVM nếu có nhiều ApplicationContext. **Prototype bean** thường được tạo khi được yêu cầu, không phải cứ refresh là tạo sẵn. Bean **@Lazy** có thể chưa tạo cho đến khi thật sự cần, dù context đã refresh; một bean lazy vẫn có thể được tạo sớm nếu bị một singleton eager khác phụ thuộc vào nó.

Nên tránh nói **“refresh tạo tất cả bean”**. Cách diễn đạt chính xác hơn là: refresh chuẩn bị toàn bộ container, xử lý definitions và **khởi tạo các singleton non-lazy** cùng những bean hạ tầng cần thiết; các scope/lazy/conditional behaviors có thể khiến nhiều instance chỉ xuất hiện về sau.

## 9. Trong Spring Boot, ba pha nằm ở đâu?

Với Spring Boot, entry point phổ biến:

~~~java
@SpringBootApplication
public class ProductionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProductionApplication.class, args);
    }
}
~~~

Đây là **đoạn minh họa**, cần import phù hợp và đặt trong project Boot. Khi gọi **SpringApplication.run(...)**, Boot tự:

1. Chuẩn bị các thông tin startup, **Environment**, sources và kiểu ứng dụng (SERVLET, REACTIVE hoặc NONE).
2. Tạo loại **ApplicationContext** phù hợp (ví dụ servlet web context cho Spring MVC).
3. Chuẩn bị context và nạp các nguồn cấu hình, auto-configuration cùng cơ chế tạo/đăng ký definitions.
4. Gọi **refresh()**, để Framework hoàn tất xử lý definitions, khởi tạo beans và hạ tầng.
5. Thực hiện thêm các mốc Boot sau refresh, chẳng hạn runner và sự kiện ready.
6. Trả về **ConfigurableApplicationContext** nếu startup hoàn tất.

Vì Boot đã thực hiện refresh, mã ứng dụng **không gọi refresh() lần thứ hai** trên context được trả về. Với loại **GenericApplicationContext** được Spring Boot sử dụng ở nhiều cấu hình, refresh lặp lại không được hỗ trợ; gọi lại có thể ném **IllegalStateException**. Khi cần tái tạo runtime theo code/config mới, thường dùng restart hoặc cơ chế refresh cấu hình được hỗ trợ rõ ràng cho hệ thống đó.

### BeanFactoryPostProcessor và BeanPostProcessor ở vị trí nào?

Hai loại extension point dễ bị nhầm:

- **BeanFactoryPostProcessor:** làm việc với bean factory / definitions **trước giai đoạn khởi tạo singleton ứng dụng**. Phù hợp điều chỉnh metadata hoặc đọc definitions theo contract, không phải nơi thao tác logic với toàn bộ bean instances.
- **BeanPostProcessor:** được đăng ký để can thiệp vào **lifecycle của từng instance bean** khi được khởi tạo; nó có thể góp phần inject metadata hoặc tạo wrapper/proxy tùy processor.

**BeanDefinitionRegistryPostProcessor** mở rộng BeanFactoryPostProcessor và có thể đóng góp thêm definitions vào registry trước khi các singleton ứng dụng được tạo.

Một số post-processors chính nó cũng là bean và được Spring khởi tạo sớm để thực hiện nhiệm vụ. Do đó luôn phân biệt **“khởi tạo singleton ứng dụng ở cuối quá trình refresh”** với **“không có instance nào được tạo trước điểm đó”**.

## 10. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân/cách hiểu | Hướng xử lý |
| --- | --- | --- |
| Vừa tạo context đã gọi getBean và gặp lỗi | Context chưa hoàn tất refresh và các processor chưa chạy | Đăng ký nguồn rồi gọi refresh đúng một lần |
| containsBeanDefinition=true, containsSingleton=false | Có metadata, chưa có singleton instance | Đây là trạng thái bình thường trước refresh |
| Đăng ký @Configuration nhưng chưa thấy @Bean definition | @Bean cần được config parser xử lý | Quan sát sau refresh |
| Constructor chỉ được gọi ở refresh | Singleton eager được tạo trong startup | Bình thường, không phải registerBean tạo instance |
| Sau refresh vẫn chưa thấy một bean prototype | Prototype tạo theo yêu cầu | Gọi getBean khi cần và quản lý lifecycle phù hợp |
| Sau refresh chưa thấy bean @Lazy | Khởi tạo lazy bị trì hoãn | Kiểm tra @Lazy và dependency eager |
| Lỗi Missing Bean / UnsatisfiedDependencyException lúc startup | BeanFactory không giải được dependency, thường bộc lộ trong refresh | Kiểm tra bean definitions, conditions, scopes, constructor |
| Lỗi BeanCurrentlyInCreationException | Có vấn đề dependency cycle hoặc lifecycle | Thiết kế lại quan hệ phụ thuộc và tìm vòng lặp |
| Gọi refresh() lần nữa trên GenericApplicationContext | Loại context này không hỗ trợ refresh nhiều lần | Tạo context mới / dùng restart phù hợp |
| ContextRefreshedEvent đã phát nhưng runner chưa xong | Spring Boot còn thực thi runner sau refresh | Dùng ApplicationReadyEvent/readiness khi đúng nhu cầu |
| Tưởng refresh là reload application.yml liên tục | refresh() là bước startup container, không phải file watcher | Dùng cơ chế cấu hình động hoặc restart theo thiết kế |
| Tự new Service() rồi kỳ vọng Spring inject mọi dependency | Đối tượng tự tạo nằm ngoài lifecycle bean do context quản lý | Đăng ký/khởi tạo thông qua Spring khi cần DI |

### Những câu hỏi kiểm tra hiểu biết

**Câu 1.** Sau **new AnnotationConfigApplicationContext()** (constructor không tham số), có thể tuyên bố mọi business bean đã khởi tạo chưa? Vì sao?

**Câu 2.** Vì sao **registerBean("x", X.class)** có thể làm **containsBeanDefinition("x")** trả true nhưng **containsSingleton("x")** trả false?

**Câu 3.** Với **@Configuration** và **@Bean**, vì sao có thể phải chờ refresh mới thấy BeanDefinition được sinh từ method?

**Câu 4.** Một singleton có **@Lazy** có bắt buộc được tạo trong refresh không? Nếu nó bị một singleton eager khác phụ thuộc thì sao?

**Câu 5.** Spring Boot đã gọi **SpringApplication.run(...)** thành công. Có nên gọi **refresh()** trực tiếp trên context trả về nữa không?

**Gợi ý:** (1) chưa, vì container chưa được refresh; (2) metadata và instance là hai trạng thái khác nhau; (3) framework phân tích configuration class trong refresh; (4) không bắt buộc, nhưng dependency có thể buộc tạo sớm; (5) không, Boot đã refresh trong startup, gọi lại có thể không được hỗ trợ.

## 11. Ghi nhớ

- **Tạo ApplicationContext:** tạo bộ chứa và các cấu trúc nền tảng của nó.
- **Đăng ký BeanDefinition:** cung cấp công thức/metadata về bean; riêng @Bean, scan và auto-configuration có thể bổ sung definitions trong refresh.
- **refresh():** điều phối xử lý cấu hình và các post-processors, khởi tạo singleton non-lazy, hoàn tất lifecycle/events và đưa context vào trạng thái hoạt động.
- **SpringApplication.run(...):** ở ứng dụng Spring Boot bình thường, thực hiện toàn bộ các thao tác trên theo thứ tự thích hợp; code nghiệp vụ không cần tự lắp ghép.

Tài liệu chính thức để kiểm tra behavior theo phiên bản:

1. Spring Framework — AnnotationConfigApplicationContext, cách tạo context với no-arg constructor rồi register/refresh: https://docs.spring.io/spring-framework/reference/core/beans/java/instantiating-container.html
2. Spring Framework API — GenericApplicationContext, registerBean và giới hạn refresh: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/GenericApplicationContext.html
3. Spring Framework API — AbstractApplicationContext.refresh: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
4. Spring Boot — SpringApplication, startup và application events: https://docs.spring.io/spring-boot/reference/features/spring-application.html

Ví dụ được viết cho **Java 17+**, API của Spring Framework 6.x / Spring Boot 3.x. Hãy đối chiếu tài liệu tương ứng với phiên bản thực tế vì các tùy chọn bootstrap có thể thay đổi ở các major versions.