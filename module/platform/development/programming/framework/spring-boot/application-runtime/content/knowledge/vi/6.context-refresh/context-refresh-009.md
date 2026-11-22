# Context cha–con trong Spring: khả năng nhìn thấy bean và phạm vi sở hữu

## 1. Bối cảnh và mô hình

Trong một ứng dụng Spring Boot thông thường, `SpringApplication.run(...)` tạo một `ApplicationContext` chính. Tuy nhiên, Spring Framework cũng hỗ trợ **phân cấp nhiều ApplicationContext**: một context làm cha của một hoặc nhiều context con. Mỗi context có **BeanFactory/bean registry riêng**, nhưng context con có thể sử dụng các bean của context cha thông qua cơ chế tìm kiếm lên cấp trên.

Chủ đề này có hai câu hỏi cốt lõi:

1. **Bean nào nhìn thấy bean nào?** Một bean do context con tạo có thể phụ thuộc vào bean của cha hay không? Cha có tự thấy bean đăng ký ở con không? Nếu hai nơi dùng cùng bean name thì kết quả tra cứu nào được chọn?
2. **Context nào sở hữu bean?** Bean nào chịu trách nhiệm tạo, áp dụng post-processor, quản lý singleton cache và gọi callback khi đóng? Context con lấy bean của cha có làm bean đó đổi chủ sở hữu không?

Tư duy quan trọng: phân cấp context là **phân cấp vùng tra cứu và quản lý vòng đời**. Nó khác với việc đặt class vào package cha/con, khác với quan hệ kế thừa class trong Java, và cũng khác với kế thừa `BeanDefinition` của Spring.

~~~mermaid
flowchart TB
    P["Parent ApplicationContext\nBeanFactory cha\nsharedClock, auditClient, policy=parent"]
    C1["Child ApplicationContext A\nBeanFactory con A\norderService, policy=child-A"]
    C2["Child ApplicationContext B\nBeanFactory con B\nreportService, policy=child-B"]
    C1 -->|"tra cứu bean còn thiếu lên cha"| P
    C2 -->|"tra cứu bean còn thiếu lên cha"| P
~~~

Trong hình, A và B **cùng thấy** bean được đăng ký trong cha, nhưng A không tự động thấy các bean chỉ do B đăng ký và ngược lại. Cha cũng không tự nhìn xuống từng con.

### Quy tắc bao quát

| Truy vấn / quan hệ | Kết quả thông thường | Lý do |
| --- | --- | --- |
| Child gọi `getBean("sharedClock")`, child không có tên này, parent có | Nhận **instance từ parent** | Tra cứu theo tên được ủy quyền lên parent khi local không có |
| Parent gọi `getBean("orderService")`, chỉ child A có | Không tìm thấy | Parent không tra cứu ngược xuống child |
| Child A gọi `getBean("reportService")`, chỉ child B có | Không tìm thấy | Sibling không trực tiếp tra cứu lẫn nhau |
| Child và parent cùng đăng ký `policy` | Child lấy bản **local** của mình khi gọi tên `policy`; parent vẫn lấy bản của parent | Bean con che (shadow) bean cùng tên ở cha đối với tra cứu xuất phát từ con |
| Child inject một singleton chỉ tồn tại trong parent | Dùng **cùng instance singleton của parent** | Không sao chép bean khi truy cập qua hierarchy |
| Đóng child A | Child A hủy các singleton do nó quản lý; parent còn hoạt động nếu không được đóng riêng | Ownership không chuyển theo nơi tiêu thụ bean |

Đây là quy tắc mặc định của hierarchy đối với Spring bean factories. Những cơ chế thêm như custom bean resolution, proxy, scope hoặc cấu hình đặc biệt có thể thay đổi chi tiết quan sát được.

## 2. Thiết lập quan hệ parent–child

### 2.1. Một context có một parent, có thể có nhiều child

`ApplicationContext` có `getParent()`; `HierarchicalBeanFactory` có `getParentBeanFactory()` và `containsLocalBean(...)`. Mỗi context con chỉ có một parent trực tiếp, nhưng nhiều con có thể dùng chung một parent. Context cha không sở hữu danh sách “mọi bean của mọi con” để tra cứu ngược.

Cần phân biệt:

- **ApplicationContext hierarchy:** nhiều container, mỗi container tự đăng ký và quản lý bean; cho phép tra cứu lên parent.
- **Bean definition inheritance:** một bean definition dùng cấu hình của bean definition khác làm mẫu (chẳng hạn `ChildBeanDefinition`, XML `parent=...`), có thể vẫn cùng một context. Đây không phải quan hệ giữa hai container.
- **Java inheritance:** `class B extends A` kế thừa thành viên/method của Java; không quyết định bean thuộc container nào.
- **Package/component scanning:** gói `com.example.parent` và `com.example.child` không tự tạo hai ApplicationContext; một `@ComponentScan` có thể quét cả hai vào **một** context.

Một ứng dụng chỉ có một context vẫn có thể chứa hàng nghìn bean từ nhiều package. Chỉ có hai bean cùng tên **trong hai context khác nhau** mới áp dụng quy tắc che tên giữa cha–con; hai definition trùng tên trong **cùng** registry là câu chuyện bean-definition overriding riêng.

### 2.2. Tạo hierarchy bằng Spring Framework

API `AnnotationConfigApplicationContext` cho phép lập trình một hierarchy có chủ đích:

~~~java
AnnotationConfigApplicationContext parent =
        new AnnotationConfigApplicationContext(ParentConfig.class);

AnnotationConfigApplicationContext child =
        new AnnotationConfigApplicationContext();

child.setParent(parent);
child.register(ChildConfig.class);
child.refresh();
~~~

Với cách viết trên, parent đã được refresh khi constructor có tham số trả về; child được gán parent **trước** khi gọi `refresh()`. Những bean trong child được đăng ký và tạo ở child; khi chúng cần một bean không có ở local, bean factory có thể tìm ở parent.

**Vòng đời:** cần đóng child rồi đóng parent theo thứ tự ngược với lúc tạo. Việc đóng child **không được hiểu** là parent cũng sẽ bị đóng và ngược lại. Một code path tạo hierarchy phải có trách nhiệm đóng đầy đủ những context nó đã khởi tạo.

### 2.3. Tạo hierarchy bằng Spring Boot

Spring Boot có `SpringApplicationBuilder` với `parent(...)` và `child(...)`:

~~~java
ConfigurableApplicationContext child =
    new SpringApplicationBuilder(ParentConfig.class)
        .web(WebApplicationType.NONE)
        .child(ChildConfig.class)
        .web(WebApplicationType.NONE)
        .run(args);
~~~

Đoạn này là một **lựa chọn khởi động khác** với cách dựng thủ công bằng Spring Framework. Cần import `org.springframework.boot.WebApplicationType`, `org.springframework.boot.builder.SpringApplicationBuilder` và `org.springframework.context.ConfigurableApplicationContext`, cùng hai class config mà ví dụ hoàn chỉnh ở phần sau định nghĩa. `WebApplicationType.NONE` làm rõ rằng ví dụ chỉ kiểm tra container, không mở HTTP server. `child.getParent()` truy cập parent từ context trả về.

Spring Boot có ràng buộc riêng khi dựng hierarchy: theo tài liệu `SpringApplicationBuilder`, các web component cần nằm trong child và parent/child dùng **cùng Environment** trong hierarchy được builder tạo. Không tạo hai web-server context tùy tiện rồi giả định hai ứng dụng HTTP sẽ độc lập; hãy xác định rõ layer nào thật sự sở hữu web runtime.

## 3. Khả năng nhìn thấy bean: tra cứu lên trên, không tra cứu xuống dưới

Giả sử parent đăng ký bean `sharedClock`, child đăng ký bean `orderService`.

~~~text
Parent:
    sharedClock
Child:
    orderService(sharedClock)
~~~

Khi tạo `orderService`, child có thể inject `sharedClock` do parent sở hữu. Nhưng nếu một bean ở parent cần `orderService` chỉ tồn tại ở child thì việc autowire bằng cơ chế thông thường của parent sẽ không tìm thấy bean ấy.

Vì vậy, thường đặt những thành phần dùng chung, không phụ thuộc logic riêng của child vào parent: config dùng chung, client hạ tầng được quản lý tập trung, policy không tham chiếu nghiệp vụ con. Đặt controller, handler hoặc chức năng từng module ở child. Parent không nên nhận constructor dependency ngược đến child cụ thể; thiết kế như vậy phá vỡ tính phân tầng và thường dẫn đến lỗi `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` khi parent khởi tạo.

### 3.1. Tra cứu theo tên

- `child.getBean("sharedClock")`: nếu không có definition local, Spring sẽ tra cứu trong parent; instance trả về vẫn là bean của parent.
- `child.containsBean("sharedClock")`: có thể là `true` dù child không sở hữu bean.
- `child.containsLocalBean("sharedClock")`: `false` khi chỉ parent khai báo bean.
- `parent.containsBean("orderService")`: `false` nếu bean chỉ có ở child.
- `child.getBeanDefinitionNames()`: dùng để kiểm tra các definition **local** đã đăng ký trong child; không tự liệt kê toàn bộ ancestor definitions.

Hai API `containsBean` và `containsLocalBean` được thiết kế để trả lời những câu hỏi khác nhau. Dùng nhầm chúng dễ khiến dashboard quản trị hoặc logic kiểm tra cấu hình báo sai quyền sở hữu.

### 3.2. Cùng bean name: child che bean của parent

Ví dụ parent có:

~~~java
@Bean("policy")
String parentPolicy() {
    return "parent-policy";
}
~~~

Child có:

~~~java
@Bean("policy")
String childPolicy() {
    return "child-policy";
}
~~~

Đây là **hai bean definition ở hai BeanFactory khác nhau**:

- `parent.getBean("policy", String.class)` trả `"parent-policy"`;
- `child.getBean("policy", String.class)` trả `"child-policy"`;
- bean `policy` trong parent không bị xóa hay thay đổi;
- child của một nhánh khác không bị ảnh hưởng bởi policy local của nhánh hiện tại.

Khái niệm chính xác là **shadowing theo mức tra cứu**, không phải ghi đè cùng definition trong một registry. Cờ `spring.main.allow-bean-definition-overriding=false` của Spring Boot kiểm soát việc ghi đè definition trong cùng bean factory; nó không tự cấm parent/child có cùng một tên bean. Nếu định nghĩa local tên `policy` có kiểu khác kiểu caller yêu cầu, Spring không nhất thiết “bỏ qua bean local sai kiểu để lấy bản parent”; có thể nhận lỗi kiểu, vì local name đã che tên parent.

### 3.3. Tra cứu theo kiểu phức tạp hơn theo tên

Để chọn bean theo type trong hierarchy, cần quan tâm cách API liệt kê candidate:

- `child.getBeansOfType(Service.class)` từ `ListableBeanFactory` chủ yếu liệt kê bean **được xác định bởi bean factory hiện tại**, không phải danh sách toàn bộ ancestor.
- `BeanFactoryUtils.beansOfTypeIncludingAncestors(child, Service.class)` là API chuyên để lấy bean của cả child và ancestors.
- `BeanFactoryUtils.beanNamesForTypeIncludingAncestors(...)` có quy tắc tránh trùng tên: bean ở cấp thấp hơn che bean cùng tên ở cấp trên, **kể cả khi kiểu của hai bean khác nhau**.
- Injection theo type có thể nhìn thấy candidate hợp lệ từ parent; nếu có nhiều candidate phù hợp tại các cấp, vẫn cần `@Qualifier`, `@Primary` hoặc các quy tắc chọn candidate tương ứng. Không nên tin rằng “bean ở child luôn được ưu tiên theo type” trong mọi cấu hình.

Ví dụ: parent có `PaymentGateway` tên `globalGateway` và child có `PaymentGateway` tên `tenantGateway`. Hai bean khác tên vẫn có thể trở thành hai candidate cho một điểm inject `PaymentGateway`; hãy dùng qualifier để nói rõ ý định. Nếu child khai báo **cùng tên** `globalGateway`, bản local che parent ở đường tra cứu theo tên đó.

## 4. Phạm vi sở hữu: ai tạo, ai giữ singleton, ai hủy?

**Chủ sở hữu bean** là bean factory/context đã đăng ký và quản lý bean definition (hoặc instance được đăng ký với container ấy), không phải nơi đầu tiên gọi `getBean(...)`.

| Hoạt động | Bean khai báo trong parent | Bean khai báo trong child |
| --- | --- | --- |
| Định nghĩa bean | Registry của parent | Registry của child |
| Tạo singleton thông thường | Parent bean factory | Child bean factory |
| Lookup từ child | Child có thể nhận bean do parent tạo | Nhận bean local |
| BeanPostProcessor / lifecycle | Hệ thống xử lý của context sở hữu bean | Hệ thống xử lý của context sở hữu bean |
| Cache singleton | Cache của parent | Cache của child |
| Đóng context sở hữu | Parent quản lý hủy singleton do mình tạo | Child quản lý hủy singleton do mình tạo |
| Có tự chuyển quyền sở hữu khi inject qua context khác? | Không | Không |

### Singleton là “một instance trên mỗi container”

`@Scope("singleton")` là scope mặc định; **singleton trong Spring có phạm vi theo container**, không mặc định chỉ có một đối tượng duy nhất toàn bộ JVM.

- Nếu parent định nghĩa `sharedClient` một lần và hai children cùng inject: thông thường cả hai nhận **cùng một instance** từ parent.
- Nếu parent và child đều tự đăng ký bean `sharedClient` (hoặc hai tên khác nhau cùng class), mỗi container có thể tạo instance riêng; đó không phải lỗi của singleton scope.
- Nếu một context có scope `prototype`, mỗi lần lấy prototype theo quy tắc có thể tạo instance mới; Spring không tự quản lý toàn bộ giai đoạn hủy của prototype theo cách singleton.
- Những scope như `request`/`session` yêu cầu web-aware context và ngữ cảnh request phù hợp; có hierarchy không tự bật các scope ấy.

Đừng nhầm “bean shared” với “bean thread-safe”. Một singleton đặt ở parent có thể được nhiều request hoặc child contexts dùng chung, vì vậy client, cache và state mutable phải được thiết kế an toàn theo mức chia sẻ thực tế.

### Lifecycle và shutdown

Khi một child gọi `getBean("sharedClient")` lấy bean của parent, child **không** trở thành chủ sở hữu bean đó. Đóng child không nên tự đóng client đang được các child khác sử dụng qua parent. Khi muốn dừng toàn bộ hierarchy, đóng các child trước, đợi công việc phụ thuộc hoàn thành, rồi mới đóng parent. Nếu đóng parent trong khi child còn dùng bean từ parent, hệ thống có thể gặp lỗi dùng tài nguyên đã bị hủy.

Dùng callback `@PreDestroy`, `DisposableBean`, hoặc destroy method thích hợp cho tài nguyên do context thực sự quản lý. Tham chiếu Java thuần được truyền vào child không tự tạo thêm quyền shutdown đối với parent bean.

## 5. Ví dụ Java 17+ chạy được: tạo hai context, tra cứu và kiểm chứng ownership

Ví dụ dùng Spring Framework API nằm trong dependency Spring Boot Starter. Nó tạo parent và child bằng hai bean factories thật, không cần HTTP server hoặc database. Chọn Java 17+ và dự án Maven Spring Boot Starter; giả sử artifact `context-hierarchy-demo`, package `com.example.hierarchy`.

**File `src/main/java/com/example/hierarchy/ContextHierarchyDemo.java`:**

~~~java
package com.example.hierarchy;

import org.springframework.beans.factory.BeanFactoryUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ContextHierarchyDemo {

    static final class SharedClock {
    }

    static final class ChildHandler {
        final SharedClock clock;

        ChildHandler(SharedClock clock) {
            this.clock = clock;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ParentConfig {

        @Bean("policy")
        public String parentPolicy() {
            return "parent-policy";
        }

        @Bean("sharedClock")
        public SharedClock sharedClock() {
            return new SharedClock();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChildConfig {

        @Bean("policy")
        public String childPolicy() {
            return "child-policy";
        }

        @Bean("childHandler")
        public ChildHandler childHandler(SharedClock sharedClock) {
            return new ChildHandler(sharedClock);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext parent =
                new AnnotationConfigApplicationContext(ParentConfig.class);

        AnnotationConfigApplicationContext child =
                new AnnotationConfigApplicationContext();
        child.setParent(parent);
        child.register(ChildConfig.class);
        child.refresh();

        try {
            System.out.println("parent.policy="
                    + parent.getBean("policy", String.class));
            System.out.println("child.policy="
                    + child.getBean("policy", String.class));

            System.out.println("child.seesSharedClock="
                    + child.containsBean("sharedClock"));
            System.out.println("child.ownsSharedClock="
                    + child.containsLocalBean("sharedClock"));
            System.out.println("parent.seesChildHandler="
                    + parent.containsBean("childHandler"));

            Object fromParent = parent.getBean("sharedClock");
            Object fromChild = child.getBean("sharedClock");
            System.out.println("sameSharedClock="
                    + (fromParent == fromChild));

            ChildHandler handler = child.getBean(ChildHandler.class);
            System.out.println("handlerUsesParentClock="
                    + (handler.clock == fromParent));

            System.out.println("child.localClockCount="
                    + child.getBeansOfType(SharedClock.class).size());
            System.out.println("child.hierarchyClockCount="
                    + BeanFactoryUtils.beansOfTypeIncludingAncestors(
                            child, SharedClock.class).size());
        } finally {
            child.close();
            parent.close();
        }
    }
}
~~~

**Cách chạy:** tạo Maven Spring Boot project bằng Spring Initializr với dependency `Spring Boot Starter`; dùng package `com.example.hierarchy`, artifact `context-hierarchy-demo`, giữ file `pom.xml` có Spring Boot Maven Plugin và đặt class trên theo đúng đường dẫn. Chạy từ thư mục dự án:

~~~bash
mvn -q -DskipTests package
java -jar target/context-hierarchy-demo-0.0.1-SNAPSHOT.jar
~~~

Tên JAR phụ thuộc `artifactId` và `version` trong `pom.xml`. Lệnh trên giả định version mặc định `0.0.1-SNAPSHOT` của ví dụ. Nếu chọn version khác, thay tên artifact tương ứng.

**Những dòng do chương trình in ra:**

~~~text
parent.policy=parent-policy
child.policy=child-policy
child.seesSharedClock=true
child.ownsSharedClock=false
parent.seesChildHandler=false
sameSharedClock=true
handlerUsesParentClock=true
child.localClockCount=0
child.hierarchyClockCount=1
~~~

Từng dòng thể hiện một quy tắc:

1. `parent.policy` và `child.policy` khác nhau dù cùng bean name: child che bean parent trong đường tra cứu bắt đầu ở child.
2. Child thấy `sharedClock` nhưng `containsLocalBean` là `false`: nhìn thấy không đồng nghĩa sở hữu.
3. Parent không thấy `childHandler`: hướng visibility bất đối xứng.
4. `sameSharedClock=true` chứng minh bean từ parent không bị copy khi child truy cập.
5. `handlerUsesParentClock=true` chứng minh một bean **do child tạo** được inject bean **do parent tạo**.
6. `getBeansOfType` tại child chỉ trả local Clock (0), còn `BeanFactoryUtils.beansOfTypeIncludingAncestors` gồm parent (1).

Vì ứng dụng chỉ chạy `AnnotationConfigApplicationContext` và không khởi động một Spring Boot web server, output chủ yếu gồm các dòng trên; việc bổ sung logger hoặc dependencies có thể tạo thêm log, nhưng giá trị các dòng kiểm tra không thay đổi khi giữ nguyên source/config như ví dụ.

**Vì sao ví dụ không đặt `@SpringBootApplication` trên `ContextHierarchyDemo`?** Bài học chủ động đăng ký chính xác `ParentConfig` và `ChildConfig` ở hai context. `@SpringBootApplication` bật component scan; nếu scan cả hai configuration vào **cùng context**, ví dụ có thể trở thành xung đột bean name và mất ý nghĩa của parent–child.

## 6. Khi triển khai bằng SpringApplicationBuilder

Trong Spring Boot, API fluent cho phép cấu hình context hierarchy mà không phải tự gọi `register(...)` và `refresh()`. Ví dụ dưới đây dùng lại hai class `ParentConfig` và `ChildConfig` ở phần 5; cần import:

~~~java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
~~~

Thay phần tạo context trong `main` bằng:

~~~java
ConfigurableApplicationContext child =
        new SpringApplicationBuilder(ContextHierarchyDemo.ParentConfig.class)
                .web(WebApplicationType.NONE)
                .child(ContextHierarchyDemo.ChildConfig.class)
                .web(WebApplicationType.NONE)
                .run(args);

ConfigurableApplicationContext parent =
        (ConfigurableApplicationContext) child.getParent();

try {
    System.out.println(child.getBean("policy"));
    System.out.println(parent.getBean("policy"));
} finally {
    child.close();
    parent.close();
}
~~~

Đây là **đoạn thay thế** cho khối dựng context trong ví dụ, không đặt cả hai khối tạo hierarchy cùng chạy. Kết quả hai lệnh `println` lần lượt là `child-policy` và `parent-policy` với configuration đã cho. Không cần khai báo Spring MVC hay Servlet trong ví dụ container thuần. Với ứng dụng Boot thực có web stack, kiểm tra kỹ hạn chế của `SpringApplicationBuilder` đối với web context ở cấp con và việc parent/child chia sẻ `Environment`.

### Phân biệt cấu hình context với chia tách tiến trình

Một hierarchy được dựng trong **cùng JVM** không tạo isolation tương đương microservice, container OS hay security sandbox. Bean ở parent có thể trở thành tài nguyên chung giữa các con. Mỗi child có registry riêng, nhưng thường vẫn dùng cùng heap, process, classloader và một số dependency hạ tầng. Đừng đưa dữ liệu bí mật của tenant này vào một parent singleton rồi mặc định rằng các child khác không thể tham chiếu nó.

## 7. Bean name, điều kiện cấu hình và component scan trong hierarchy

### 7.1. Child shadowing khác bean overriding

| Trường hợp | Chính sách/hiện tượng | Điều xảy ra |
| --- | --- | --- |
| Parent có bean `policy` và child cũng có `policy` | Shadowing xuyên hai context | `child.getBean("policy")` dùng local; parent giữ nguyên |
| Hai `@Bean("policy")` được đăng ký trong **cùng** bean factory | Bean definition overriding | Với Spring Boot mặc định chặn overriding, có thể phát sinh `BeanDefinitionOverrideException` |
| Parent có type `Gateway`, child có type `Gateway` nhưng tên khác | Nhiều candidate theo type | Có thể cần qualifier hoặc chính sách chọn bean |
| Child có bean cùng tên nhưng type khác parent | Shadowing vẫn dựa theo **name** | Không bảo đảm fallback lên parent khi caller yêu cầu type của parent |
| Parent chỉ có `sharedClock`, child không có | Kế thừa lookup, không kế thừa definition | Child dùng instance do parent sở hữu |

Nếu muốn thay đổi implementation theo child, đặt bean local tên có ý nghĩa rõ ràng và kiểm thử đường tra cứu. Dùng lại cùng bean name được Spring hỗ trợ nhưng dễ gây nhầm lẫn khi debug. Nếu nhiều implementation có tên khác nhau, `@Qualifier` hoặc `@Primary` có thể phù hợp; chúng không phải công cụ biến hai bean cùng name thành hai bean phân biệt.

### 7.2. Phạm vi của các điều kiện auto-configuration

Trong Spring Boot, `@ConditionalOnMissingBean` có thuộc tính `search` với `SearchStrategy`:

- `ALL`: xét cả context hiện tại và ancestors; đây là mặc định của điều kiện này theo API Boot.
- `CURRENT`: chỉ xét context hiện tại.
- `ANCESTORS`: chỉ xét các ancestors, không tính context hiện tại.

Ví dụ cấu hình **minh họa**, đặt trong một auto-configuration có thứ tự xử lý hợp lệ:

~~~java
@ConditionalOnMissingBean(
        value = SharedClock.class,
        search = SearchStrategy.CURRENT)
@Bean
SharedClock localClock() {
    return new SharedClock();
}
~~~

Đoạn này cần import `ConditionalOnMissingBean` và `SearchStrategy` từ package `org.springframework.boot.autoconfigure.condition` cùng annotation `@Bean`. Nếu có parent `SharedClock` nhưng child chưa có local, điều kiện tìm **CURRENT** vẫn có thể thỏa và tạo thêm một clock thuộc child. Ngược lại, chiến lược **ALL** sẽ xét clock ở parent trước khi quyết định điều kiện missing bean.

Đây là một cách cụ thể cho thấy **bean nhìn thấy được từ ancestor** và **bean tồn tại trong registry hiện tại** là hai điều khác nhau. Điều kiện `@ConditionalOnMissingBean` phụ thuộc những bean definitions đã được xử lý tại thời điểm đánh giá; theo tài liệu Boot, thường dành cho auto-configuration, không nên đặt tùy tiện trên các configuration ngang cấp rồi giả định thứ tự tạo bean bất biến.

### 7.3. Quét component đúng tầng

Một lỗi phổ biến là parent cấu hình `@ComponentScan("com.example")` quá rộng, khiến cả controller và service vốn dành cho child được đăng ký **ở parent**. Khi đó:

- Parent khởi tạo những bean chỉ nên tồn tại trong child.
- Child có thể tiếp tục scan chúng và tạo thêm instance.
- Các bean có state tưởng tách riêng lại chia sẻ state qua parent, hoặc mâu thuẫn scope.
- Một bean thuộc module con có thể tạo vòng phụ thuộc không mong đợi khi bị nạp ở context cha.

Nên cấp **configuration sources** và base packages có chủ đích cho mỗi tầng; các cấu hình dùng chung được tạo một lần ở parent, thành phần riêng theo module đặt vào đúng child. Có thể kiểm kê `getBeanDefinitionNames()`, `containsLocalBean(...)` và định danh instance để xác minh.

## 8. Sự kiện và môi trường: điểm đặc biệt của hierarchy

### Application events đi lên ancestor

Sự kiện được `ApplicationEventPublisher` phát từ child thường được chuyển lên các context cha. Do đó, listener ở parent **có thể** nhận event được phát bởi child. Chiều ngược lại không tự đối xứng: phát event ở parent không bảo đảm listener chỉ đăng ký trong child sẽ được gọi.

Đặc biệt, Spring Boot có thể phát startup events cho nhiều `SpringApplication` của một hierarchy; listener ở parent có thể thấy sự kiện từ chính parent và từ child. Nếu chỉ muốn xử lý sự kiện của context hiện tại, so sánh context nguồn của sự kiện với context listener đang sở hữu trước khi xử lý:

~~~java
if (event.getApplicationContext() != myContext) {
    return;
}
~~~

Đoạn này áp dụng cho event có API `getApplicationContext()` phù hợp, như một số `SpringApplicationEvent`/`ApplicationContextEvent`, không phải mọi event tùy ý. `myContext` là context của listener cần được cung cấp bằng cơ chế injection hoặc callback tương ứng.

**Lưu ý:** “listener nhận sự kiện từ child” **không** có nghĩa parent có thể `getBean(...)` của child. Cơ chế truyền sự kiện và cơ chế bean lookup là hai API độc lập.

### Cấu hình và Environment

Với Spring Boot `SpringApplicationBuilder` hierarchy, tài liệu quy định parent và child sử dụng cùng `Environment`. Như vậy property `server.port` hay active profile không tự tạo namespace riêng cho từng child. Khác biệt giữa bean registries không hàm ý mỗi child nhận cấu hình bị cô lập.

Nếu cần cấu hình theo từng nhóm child, hãy lập thiết kế rõ ràng: property prefix riêng, nguồn config chuyên biệt hoặc mô hình context setup phù hợp; kiểm tra cách thuộc tính được bind vào từng bean tại thời điểm tạo context. Không dựa vào giả định “cùng key nhưng ở child sẽ tự override parent environment” như cách bean name shadowing hoạt động.

## 9. Khi nào nên dùng context cha–con?

Hierarchy hữu ích khi ứng dụng có **tầng nền tảng dùng chung** và các **context con có vòng đời/chức năng riêng**:

- Một parent cung cấp resource pool hoặc client được quản lý tập trung; nhiều child xử lý workload khác nhau.
- Ứng dụng plugin/module có các module cần cô lập registry để giảm xung đột component scan và chủ động bật/tắt module.
- Một số cấu trúc web truyền thống có root `WebApplicationContext` và child context cho từng `DispatcherServlet`; các handler/controllers thuộc con, service/repository dùng chung có thể ở root.

Tuy vậy, hierarchy làm tăng độ phức tạp trong chẩn đoán bean lookup, bean lifecycle, event propagation và cấu hình. Với Spring Boot ứng dụng thông thường, **một ApplicationContext**, dependency injection rõ ràng, package/module hợp lý và condition thích hợp thường dễ vận hành hơn. Chọn hierarchy khi cần ranh giới lifecycle hoặc registry thực sự, không chỉ vì dự án có nhiều package.

### Không dùng hierarchy thay cho bảo mật tenant

Context cha–con không cung cấp phân quyền truy cập thông tin. Nếu các child phục vụ tenant khác nhau, bất kỳ shared parent bean nào chứa credentials, cache hoặc mutable state phải được kiểm tra rõ phạm vi. Cần áp dụng authorization, isolation của tài nguyên và thiết kế dữ liệu riêng, không kỳ vọng BeanFactory thay thế chính sách an toàn dữ liệu.

## 10. Các lỗi và cách chẩn đoán

### “Bean có trong parent nhưng @Autowired ở child không tìm thấy”

1. Xác nhận child **thực sự đã gán parent** trước `refresh()`.
2. Xác nhận parent đã được refresh và bean mong đợi có trong parent registry.
3. Xem tên, type, qualifier, generic type, profile, điều kiện đăng ký và tình trạng bean có phải autowire candidate không.
4. Phân biệt lookup theo tên với lookup theo type; bean local cùng tên có thể che bean parent.
5. Nếu có nhiều candidate theo type, kiểm tra `@Qualifier`/`@Primary` và injection point.

Không “sửa” bằng cách đăng ký ngẫu nhiên một bản bean khác vào child trước khi xác định đúng ownership; việc này có thể tạo hai client hoặc hai transaction manager riêng ngoài ý muốn.

### “Parent service cần bean ở child nên startup lỗi”

Parent không nhìn xuống child. Nếu một service dùng chung phải gọi logic theo từng child, cân nhắc đảo chiều dependency, đẩy orchestration xuống child, đưa một abstraction không phụ thuộc child vào parent hoặc định nghĩa một cơ chế đăng ký/dispatch có vòng đời rõ ràng. Không tìm cách làm parent inject child bean bằng component scan tràn lan, vì điều đó thường phá ranh giới context.

### “Không báo trùng bean nhưng child nhận implementation khác dự kiến”

Kiểm tra bean name trùng giữa parent và child. `child.getBean("policy")` ưu tiên local; nếu child đăng ký `policy`, parent bean cùng tên bị che trong lookup đó. Xem `containsLocalBean` và bean definition registry của child trước khi kết luận bean ở parent đã bị overwrite.

### “Đóng module làm shared client bị đóng hoặc bị leak”

Xác định bean được tạo ở đâu và ai gọi lifecycle cleanup. Nếu shared client thuộc parent, các child không nên tự gọi `close()` trên nó. Nếu resource chỉ phục vụ child, đừng đăng ký nó ở parent rồi để phụ thuộc vòng đời sai. Đóng child rồi parent; kiểm tra listener, scheduler, connection pool và các callback `@PreDestroy`/destroy methods.

### “Child A nhìn thấy bean của Child B”

Nếu đang nhìn thấy cùng tên/type từ các child, có thể bean thực ra nằm trong parent, cả hai context đang cùng scan một configuration, hoặc code đã chuyển tham chiếu đối tượng trực tiếp giữa hai module. Hai context cùng parent không tự có đường lookup qua sibling. Kiểm tra hierarchy thực tế và local bean definitions của từng tầng.

### “getBeansOfType() trả danh sách thiếu, còn getBean() lại lấy được”

`ListableBeanFactory.getBeansOfType` và lookup `getBean(name)` có phạm vi tra cứu khác nhau trong hierarchy. Nếu cần kiểm kê toàn bộ candidate qua ancestors, dùng `BeanFactoryUtils.beansOfTypeIncludingAncestors`. Chú ý khi parent và child trùng tên: bản local sẽ che bản ancestor trong tiện ích này.

### “Listener ở parent nhận event hai lần”

Kiểm tra mỗi context phát event của chính mình, cộng với việc event từ child được truyền lên parent. Với event mang thông tin context, lọc theo `getApplicationContext()` hoặc định danh phù hợp. Không suy đoán rằng một bean listener chỉ nhận event của context sở hữu nó.

## 11. Quy tắc triển khai và kiểm thử

Khi dùng hierarchy, một nhóm test nhỏ nhưng có chủ đích nên kiểm tra:

1. Child inject được bean của parent và nhận **cùng instance**.
2. Parent không inject/tìm được bean chỉ đăng ký trong child.
3. Hai child có thể dùng chung parent bean nhưng không trực tiếp đọc bean local của nhau.
4. Bean cùng tên ở parent và child cho kết quả đúng ở từng context; không có bean collision ngoài dự định.
5. `getBeansOfType` chỉ dùng khi cần local view; utility có ancestors dùng khi cần hierarchy view.
6. Khi close một child, parent resource vẫn dùng được cho child khác; khi shutdown toàn bộ, các child được đóng trước parent.
7. Component scan/configuration sources chỉ đăng ký bean vào tầng chủ đích.
8. Nếu dùng Boot auto-configuration, điều kiện `@ConditionalOnMissingBean(search=...)` kiểm tra đúng cấp dự định.
9. Nếu dùng web hoặc events, kiểm tra thêm giới hạn hierarchy web context và propagation của events.

Không nhất thiết đưa toàn bộ mô hình hierarchy vào ứng dụng chỉ để kiểm thử phân tầng logic. Nếu không cần quản lý lifecycle hay registry riêng, code Java module hóa trong một context thường đủ.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Parent có bean `clock`; child không khai báo `clock`. `child.containsBean("clock")` và `child.containsLocalBean("clock")` trả gì?  
**Trả lời:** thường là `true` và `false`: thấy qua parent nhưng không sở hữu.

**Câu 2.** Parent và child đều có bean tên `formatter`. Khi child gọi `getBean("formatter")`, parent bean có bị hủy không?  
**Trả lời:** child thường nhận bản local; parent bean vẫn tồn tại và thuộc parent.

**Câu 3.** Hai sibling contexts có cùng parent. Child A tự động inject được bean chỉ đăng ký ở child B không?  
**Trả lời:** không. Hai child nhìn lên parent, không có cơ chế lookup ngang mặc định.

**Câu 4.** Parent singleton được hai child inject thì có phải ba singleton khác nhau không?  
**Trả lời:** không. Nếu hai child dùng bean qua parent, họ thường chia sẻ **một instance thuộc parent**.

**Câu 5.** Tại sao `child.getBeansOfType(Clock.class)` có thể trả về map rỗng nhưng `child.getBean("sharedClock")` lại thành công?  
**Trả lời:** liệt kê theo type tại bean factory local khác với lookup theo tên có thể chuyển lên parent.

**Câu 6.** Nếu parent và child cùng đăng ký tên bean, có cần bật `spring.main.allow-bean-definition-overriding=true` không?  
**Trả lời:** không chỉ vì trùng tên ở **hai bean factories khác nhau**; đó là shadowing xuyên context, không phải đăng ký đè trong cùng registry.

**Câu 7.** Đóng child có mặc định được đóng parent singleton dùng chung không?  
**Trả lời:** không nên coi việc đóng child là đóng parent. Phải quản lý chuỗi shutdown và ownership riêng.

**Câu 8.** Listener ở parent nhận event phát từ child có chứng minh parent thấy bean của child không?  
**Trả lời:** không. Event propagation đi lên, bean lookup không đi xuống.

## Tài liệu chính thức

- [Spring Boot — SpringApplication / Fluent Builder API](https://docs.spring.io/spring-boot/reference/features/spring-application.html): `SpringApplicationBuilder`, parent/child, giới hạn web context, shared Environment và sự kiện.
- [Spring Framework — BeanFactoryUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanFactoryUtils.html): tra cứu gồm ancestor và quy tắc bean trùng tên.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): `singleton` gắn với container và các scope khác.
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html): ý nghĩa phạm vi post-processor và cấu hình annotation.
- [Spring Framework — Bean Definition Inheritance](https://docs.spring.io/spring-framework/reference/core/beans/child-bean-definitions.html): phân biệt với parent/child ApplicationContext.
- [Spring Boot — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): thuộc tính `search`.
- [Spring Boot — SearchStrategy API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html): `ALL`, `CURRENT`, `ANCESTORS`.