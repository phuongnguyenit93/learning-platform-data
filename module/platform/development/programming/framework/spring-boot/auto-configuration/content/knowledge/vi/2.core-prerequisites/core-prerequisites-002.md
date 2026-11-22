# Phân biệt đăng ký định nghĩa bean với khởi tạo đối tượng bean

## 1. Vì sao cần phân biệt?

Trong Spring Boot, việc framework **biết rằng một bean có thể được tạo** và việc **đã tạo một đối tượng Java cụ thể** là hai sự kiện khác nhau. Sự khác biệt đặc biệt quan trọng khi tìm hiểu **auto-configuration**: một điều kiện có thể quyết định có đăng ký định nghĩa bean hay không, trong khi quá trình tạo đối tượng thật diễn ra sau đó, theo scope, lazy initialization và nhu cầu sử dụng.

Ví dụ, một lớp auto-configuration có phương thức **@Bean** để cung cấp bộ xử lý. Khi Spring đưa định nghĩa đó vào **BeanFactory**, không nhất thiết constructor hay phương thức tạo bộ xử lý đã chạy. Nếu bean là singleton thông thường và không lazy, Spring thường tạo nó trong lúc refresh **ApplicationContext**; nếu nó lazy, Spring có thể đợi tới khi bean được yêu cầu; nếu là prototype, mỗi lần yêu cầu có thể tạo một instance mới.

Hai câu hỏi cần tách riêng:

1. **Bean definition đã đăng ký chưa?** Spring có metadata và quy tắc để tạo bean mang tên đó hay chưa?
2. **Bean instance đã tồn tại chưa?** Spring đã thật sự gọi constructor/factory method, thực hiện injection và đưa đối tượng qua quá trình khởi tạo cần thiết hay chưa?

Một bean definition tồn tại **không bảo đảm** instance đã tồn tại, và trong một số cơ chế đặc biệt, một đối tượng singleton có thể được đăng ký trực tiếp mà không có BeanDefinition thông thường.

## 2. Hai tầng: BeanDefinition và bean instance

### 2.1. BeanDefinition là “bản mô tả cách tạo”

**BeanDefinition** là metadata trong container, thường gồm một phần hoặc toàn bộ thông tin:

- **Tên bean** để container định danh; tên có thể sinh từ tên lớp hoặc tên phương thức **@Bean**, hoặc được chỉ định tường minh.
- **Nguồn và cách tạo**: lớp mục tiêu, constructor, phương thức factory, bean chứa factory method, hoặc một cơ chế tạo do container hỗ trợ.
- **Scope**, chẳng hạn **singleton** hoặc **prototype**.
- **Lazy-init**, điều kiện khởi tạo, dependency, constructor arguments và property values, nếu có.
- Thông tin phục vụ vòng đời, như init/destroy method, role và các cờ xử lý khác.

Thông tin cụ thể phụ thuộc cách định nghĩa. Với **@Bean**, BeanDefinition có thể trỏ đến **phương thức factory trên lớp cấu hình** thay vì đơn giản giữ constructor của kiểu trả về. Vì thế không nên coi BeanDefinition là “một đối tượng Java mẫu” hay “một instance đang ngủ”.

Bean definition có thể xuất hiện qua:

- **@ComponentScan** tìm **@Component**, **@Service**, **@Repository**, **@Controller** trong vùng quét.
- **@Configuration** và các phương thức **@Bean** được bộ xử lý cấu hình đọc.
- **@Import** và các **BeanDefinitionRegistryPostProcessor** đăng ký thêm định nghĩa.
- Đăng ký chương trình qua **BeanDefinitionRegistry.registerBeanDefinition(...)**.
- **Auto-configuration** của Spring Boot: framework phát hiện cấu hình ứng viên và chỉ đăng ký các nhánh đáp ứng điều kiện.

**Lưu ý:** Việc đọc annotation, xử lý import và đăng ký definition xảy ra trong nhiều bước phối hợp; không phải mọi definition đều được tạo đồng loạt trong một thao tác duy nhất.

### 2.2. Bean instance là đối tượng được tạo và quản lý

**Bean instance** là đối tượng thực tế được container tạo hoặc nhận và quản lý. Khi tạo bean thông thường, Spring có thể thực hiện một số bước:

1. Chọn cách khởi tạo từ BeanDefinition: constructor, phương thức **@Bean** hoặc factory khác.
2. Giải quyết dependency và tạo/inject những bean cần thiết.
3. Thực hiện dependency injection, các callback nhận biết container nếu phù hợp.
4. Gọi các **BeanPostProcessor** trước/sau initialization, **@PostConstruct**, **InitializingBean.afterPropertiesSet()** và init method theo quy tắc tương ứng.
5. Có thể trả về **proxy** đã qua xử lý, không nhất thiết đúng object “thô” ban đầu từ constructor.
6. Với singleton, thường giữ instance trong singleton registry để sử dụng lại; với các scope khác, cách lưu và tạo do scope quyết định.

Đây là luồng khái quát; thứ tự chi tiết của post-processor, proxy và callback cần xét loại bean và extension đang dùng. **Đăng ký definition chỉ cung cấp thông tin để tạo; những bước trên chưa bắt buộc xảy ra tại thời điểm đăng ký.**

| Tiêu chí | BeanDefinition | Bean instance |
| --- | --- | --- |
| Bản chất | Metadata/công thức tạo bean trong container | Đối tượng Java đã được tạo hoặc được cung cấp cho container |
| Định danh | Tên bean, thuộc tính của definition | Object reference thực tế |
| Tồn tại từ khi nào? | Sau khi framework hoặc code đăng ký definition | Khi có yêu cầu khởi tạo theo scope và lifecycle |
| Có chạy constructor/factory method chưa? | Không suy ra được | Có bước tạo/nhận đối tượng thực tế; có thể qua factory/proxy |
| Với singleton không lazy | Thường có definition trước | Thường tạo trong giai đoạn refresh |
| Với singleton lazy | Definition đã có | Có thể chưa tạo cho đến lần đầu cần dùng |
| Với prototype | Một definition có thể tồn tại lâu | Có thể tạo nhiều instance từ cùng một definition |
| Trong auto-configuration | Điều kiện quyết định definition nào được đăng ký | Instance chỉ xuất hiện nếu định nghĩa được chọn và quá trình tạo xảy ra thành công |

Cần tránh suy luận đơn giản “mỗi BeanDefinition luôn tương ứng chính xác một object”. Prototype có nhiều instance; scoped proxy và **FactoryBean** có cấu trúc riêng; và **registerSingleton(...)** cho phép đăng ký trực tiếp một object vào singleton registry trong một số tình huống.

## 3. Các mốc trong quá trình khởi động Spring Boot

Một ứng dụng điển hình chạy **SpringApplication.run(...)** để tạo và refresh ApplicationContext. Có thể phân tách theo mục đích:

~~~text
SpringApplication.run(...)
       |
       v
Chuẩn bị Environment và ApplicationContext
       |
       v
Nạp các nguồn cấu hình, đăng ký definition ban đầu
       |
       v
Xử lý @Configuration, @ComponentScan, @Import,
các ứng viên auto-configuration và condition liên quan
       |
       v
BeanDefinitionRegistryPostProcessor /
BeanFactoryPostProcessor có thể xem, thêm, sửa definition
       |
       v
Đăng ký các BeanPostProcessor, hoàn thiện BeanFactory
       |
       v
Khởi tạo trước các singleton thông thường không lazy
       |
       v
Context refresh hoàn tất; các cơ chế startup còn lại chạy
       |
       v
Lần gọi getBean/injection sau đó vẫn có thể tạo lazy/prototype
~~~

**Sơ đồ trên là mô hình khái niệm**, không bảo đảm trong toàn bộ refresh chỉ có “đăng ký tất cả definition, rồi mới tạo bất kỳ object nào”. Một số bean hạ tầng, đặc biệt các post-processor, cần được tạo sớm để chính chúng xử lý metadata; việc đăng ký bổ sung cũng có thể diễn ra trong refresh. Mục đích của sơ đồ là phân biệt **thời điểm quyết định có bean** với **thời điểm tạo instance cho bean nghiệp vụ**.

### 3.1. BeanDefinitionRegistryPostProcessor và BeanFactoryPostProcessor

- **BeanDefinitionRegistryPostProcessor** có thể can thiệp vào **registry của bean definition**, đặc biệt thêm các definition trước giai đoạn tạo singleton thông thường.
- **BeanFactoryPostProcessor** có thể đọc/chỉnh metadata của definition đã được đăng ký mà không cần khởi tạo bean nghiệp vụ tương ứng. Cơ chế này xử lý **định nghĩa**, còn **BeanPostProcessor** xử lý **đối tượng bean** trong quá trình khởi tạo.
- Bộ xử lý **@Configuration** của Spring là một phần quan trọng giúp biến phương thức **@Bean** và các cấu hình liên quan thành BeanDefinition.

Không dùng **getBean(...)** tùy tiện bên trong BeanFactoryPostProcessor chỉ để kiểm tra một bean có tồn tại hay không: lời gọi đó có thể ép tạo instance quá sớm, làm sai giả định về vòng đời và việc áp dụng BeanPostProcessor.

### 3.2. Auto-configuration quyết định đăng ký, không đồng nghĩa đã tạo instance

Trong Spring Boot 3.x, **@SpringBootApplication** bao gồm **@EnableAutoConfiguration**. Các auto-configuration ứng viên được phát hiện qua tệp **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**; điều kiện có thể nằm ở cấp class hoặc cấp method **@Bean**.

Ví dụ minh họa logic (đây là mảnh mã của một lớp auto-configuration, chưa phải chương trình chạy độc lập):

~~~java
@AutoConfiguration
@ConditionalOnClass(Client.class)
class ClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Client.class)
    Client client() {
        return new Client();
    }
}
~~~

Nếu **Client** có trên classpath và chưa có bean phù hợp, điều kiện có thể cho phép đăng ký định nghĩa cho bean tạo từ phương thức **client()**. Điều này **không chứng minh** phương thức đã chạy ngay khi điều kiện được đánh giá. Với một singleton không lazy, nó thường được gọi sau đó trong refresh; nếu có lazy initialization thì có thể muộn hơn.

Một cách hiểu dễ nhầm: **@ConditionalOnMissingBean** không phải câu hỏi “object đã gọi constructor chưa?”. Nó xét thông tin về bean hiện có trong container theo kiểu/tên/điều kiện khai báo, dựa trên các definition đã được xử lý tại thời điểm đánh giá. Vì thế **bean đã có definition nhưng chưa có instance** vẫn có thể làm nhánh default rút lui. Các điều kiện này chịu ảnh hưởng thứ tự xử lý definition; nên dùng đúng trong auto-configuration thay vì đặt tùy tiện trên cấu hình thường.

Tương tự, **@ConditionalOnClass** xem classpath; **@ConditionalOnProperty** xem Environment. Các condition giúp quyết định nhánh **đăng ký**; lỗi ném từ constructor, thiếu dependency lúc tạo hoặc kết nối tài nguyên thất bại là vấn đề của giai đoạn **khởi tạo**, không phải lý do để kết luận condition chắc chắn chưa match.

## 4. Ví dụ Spring Boot chạy được: definition đã có, instance chưa tạo

Ví dụ này dùng **Java 21 + Spring Boot 3.3.13 + Maven 3.9+**. Nó cho thấy ba cách tạo instance từ các BeanDefinition đã đăng ký:

- **eagerTask**: singleton mặc định, tạo trong refresh.
- **lazyTask**: singleton có **@Lazy**, chỉ tạo khi được yêu cầu trong ví dụ.
- **prototypeTask**: prototype, tạo mới mỗi lần container được yêu cầu.

Đồng thời, một **BeanFactoryPostProcessor** chỉ kiểm tra metadata qua **containsBeanDefinition(...)** và singleton registry qua **containsSingleton(...)**. Không gọi **getBean(...)** ở giai đoạn kiểm tra sớm.

Cấu trúc dự án:

~~~text
bean-stages/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── dev/example/
        │       └── StageApplication.java
        └── resources/
            └── application.properties
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>bean-stages</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/dev/example/StageApplication.java**

~~~java
package dev.example;

import java.util.List;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

@SpringBootApplication(proxyBeanMethods = false)
public class StageApplication {

    public static void main(String[] args) {
        try (var context = SpringApplication.run(StageApplication.class, args)) {
            var factory = context.getBeanFactory();

            for (String name : List.of(
                    "eagerTask", "lazyTask", "prototypeTask")) {
                System.out.printf(
                    "AFTER_REFRESH %s singleton=%s%n",
                    name, factory.containsSingleton(name));
            }

            Task lazy1 = context.getBean("lazyTask", Task.class);
            Task lazy2 = context.getBean("lazyTask", Task.class);
            System.out.println("SAME lazyTask=" + (lazy1 == lazy2));

            Task prototype1 = context.getBean("prototypeTask", Task.class);
            Task prototype2 = context.getBean("prototypeTask", Task.class);
            System.out.println(
                "SAME prototypeTask=" + (prototype1 == prototype2));
        }
    }

    @Bean
    static BeanFactoryPostProcessor inspectDefinitions() {
        return factory -> {
            for (String name : List.of(
                    "eagerTask", "lazyTask", "prototypeTask")) {
                System.out.printf(
                    "REGISTERED %s definition=%s singleton=%s%n",
                    name,
                    factory.containsBeanDefinition(name),
                    factory.containsSingleton(name));
            }
        };
    }

    @Bean
    Task eagerTask() {
        System.out.println("CREATE eagerTask");
        return new Task();
    }

    @Bean
    @Lazy
    Task lazyTask() {
        System.out.println("CREATE lazyTask");
        return new Task();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    Task prototypeTask() {
        System.out.println("CREATE prototypeTask");
        return new Task();
    }

    static final class Task {
    }
}
~~~

Điểm cần nhận biết: phương thức **inspectDefinitions()** là **static @Bean** để BeanFactoryPostProcessor được tạo sớm mà không ép tạo sớm instance của lớp cấu hình **StageApplication** vì một phương thức factory không static. Đây là thực hành phù hợp khi khai báo BeanFactoryPostProcessor qua **@Bean**.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

Cấu hình này chỉ làm gọn output. Không cần web server; starter ở đây cung cấp Spring Boot và Spring Context. Nếu dùng môi trường có hệ thống log/agent riêng, vẫn có thể thấy thêm dòng log từ môi trường: tập trung vào các dòng chương trình tự in dưới đây.

### 4.1. Build và chạy

Đứng tại thư mục **bean-stages**, dùng JDK 21:

~~~bash
mvn -q -DskipTests package
java -jar target/bean-stages-0.0.1-SNAPSHOT.jar
~~~

Các dòng do ví dụ tự in, theo thứ tự:

~~~text
REGISTERED eagerTask definition=true singleton=false
REGISTERED lazyTask definition=true singleton=false
REGISTERED prototypeTask definition=true singleton=false
CREATE eagerTask
AFTER_REFRESH eagerTask singleton=true
AFTER_REFRESH lazyTask singleton=false
AFTER_REFRESH prototypeTask singleton=false
CREATE lazyTask
SAME lazyTask=true
CREATE prototypeTask
CREATE prototypeTask
SAME prototypeTask=false
~~~

**Giải thích theo dấu mốc:**

1. **REGISTERED ... definition=true**: Khi BeanFactoryPostProcessor được gọi, cả ba bean nghiệp vụ đều có definition trong BeanFactory. Ở thời điểm kiểm tra, chúng **chưa xuất hiện trong singleton registry**.
2. **CREATE eagerTask**: Trong refresh, Spring tạo singleton không lazy qua phương thức **@Bean eagerTask()**. Đây là việc tạo instance; dòng này xuất hiện **sau** các dòng kiểm tra definition.
3. **AFTER_REFRESH eagerTask singleton=true**: Sau khi **SpringApplication.run(...)** trả về, singleton eager đã được tạo và giữ trong container.
4. **AFTER_REFRESH lazyTask singleton=false**: Definition của lazyTask đã đăng ký nhưng chưa có singleton instance, vì chưa ai yêu cầu nó trong ví dụ.
5. **CREATE lazyTask** chỉ xuất hiện một lần dù gọi **getBean(...)** hai lần; singleton trả về cùng một reference, nên **SAME lazyTask=true**.
6. **CREATE prototypeTask** xuất hiện hai lần. Hai lần gọi **getBean(...)** tạo hai object khác nhau; chúng không được giữ như singleton, nên **SAME prototypeTask=false**.

Kết quả này chứng minh **một BeanDefinition đã đăng ký không quyết định số lượng instance hay thời điểm tạo**; hai yếu tố đó còn phụ thuộc scope và thời điểm dependency được yêu cầu.

### 4.2. Những thay đổi làm kết quả khác đi

- Nếu bỏ **@Lazy** khỏi lazyTask, bean đó trở thành singleton thường và thường được tạo trong refresh, trước khi lệnh **getBean(...)** trong main chạy.
- Nếu thêm **spring.main.lazy-initialization=true** khi chạy ứng dụng, Spring Boot cho phép trì hoãn nhiều bean singleton vốn eager; khi ấy output về singleton sau refresh cần đánh giá lại. Không dùng property đó khi đối chiếu stdout mẫu.
- Nếu một singleton eager cần inject **lazyTask** như dependency trực tiếp, Spring có thể buộc tạo lazyTask trong quá trình xây dựng singleton eager dù lazyTask mang **@Lazy** trên định nghĩa. **Lazy không đồng nghĩa bảo đảm chưa có ai dùng bean trước khi startup hoàn tất.**
- Nếu một singleton inject trực tiếp prototypeTask bằng constructor, Spring tạo một prototype cho lần inject đó; singleton giữ reference được inject và việc gọi phương thức trên singleton nhiều lần **không tự sinh prototype mới**. Muốn lấy prototype mới theo mỗi lần dùng, có thể inject **ObjectProvider<Task>** với qualifier phù hợp và gọi **getObject()** khi cần.
- Nếu constructor hoặc factory method của eagerTask ném exception, definition vẫn đã được chọn/đăng ký trước đó nhưng refresh có thể thất bại. Điều này khác với trường hợp condition khiến definition không hề được đăng ký.

## 5. Phân biệt singleton, lazy singleton và prototype

Spring mặc định dùng **singleton scope** cho bean. Đây là singleton **theo từng bean name trong một Spring IoC container**, không phải khẳng định duy nhất một đối tượng của lớp đó trong toàn bộ JVM. Cùng một class có thể có nhiều bean name và nhiều instance tương ứng.

| Scope/cách tạo | Có definition trước khi getBean? | Lúc nào instance có thể xuất hiện? | Mỗi lần getBean cùng tên trả gì? |
| --- | --- | --- | --- |
| Singleton thông thường | Có | Thường trong refresh nếu không lazy | Cùng một instance được container quản lý |
| Singleton **@Lazy** | Có | Lần đầu thật sự cần, trừ khi dependency ép tạo sớm | Cùng một instance sau khi đã tạo |
| Prototype | Có | Khi được yêu cầu | Thường mỗi lần yêu cầu một instance mới |
| Request/session scope (ứng dụng web có cấu hình phù hợp) | Có | Trong phạm vi request/session và khi được yêu cầu | Theo vòng đời của scope; proxy có thể đứng ở giữa |

**@Lazy** nói về việc trì hoãn khởi tạo, **@Scope** nói về vòng đời/phạm vi lưu instance. Hai annotation giải quyết các câu hỏi khác nhau. Một BeanDefinition vẫn có thể tồn tại lâu dù instance prototype sinh ra nhiều lần và không được Spring quản lý giai đoạn hủy như singleton theo mặc định.

Đừng hiểu **@Lazy trên @Component hoặc @Bean** giống hoàn toàn **@Lazy tại điểm injection**. Cái thứ nhất tác động đến cách khởi tạo bean được định nghĩa; cái thứ hai có thể khiến Spring inject proxy trì hoãn giải quyết dependency. Khi debug, cần xem annotation nằm ở đâu và có dependency eager nào kéo việc khởi tạo lên sớm hay không.

## 6. Các API cho câu hỏi “đã đăng ký hay đã tạo?”

Một số API có tên gần giống nhau nhưng trả lời những câu hỏi khác nhau:

| API | Ý nghĩa gần đúng | Điều không nên kết luận |
| --- | --- | --- |
| **BeanFactory.containsBean(name)** | BeanFactory có thể nhận biết bean mang tên này, kể cả theo một số quy tắc parent/alias | Không chứng minh instance đã tạo |
| **ConfigurableListableBeanFactory.containsBeanDefinition(name)** | Factory hiện có một BeanDefinition cục bộ cho tên này | Không chứng minh đã tạo object |
| **BeanFactory.getBean(name)** | Yêu cầu bean; có thể kích hoạt tạo bean, resolve proxy/scope | Không phải phép kiểm tra chỉ đọc |
| **SingletonBeanRegistry.containsSingleton(name)** | Registry có singleton object đã đăng ký cho tên này | Không phải kiểm tra chung cho prototype hay mọi FactoryBean |
| **BeanFactory.isSingleton(name)** | Bean được xem có ngữ nghĩa singleton theo factory | Không đồng nghĩa singleton instance đã có |
| **BeanFactory.isPrototype(name)** | Bean được xem có ngữ nghĩa prototype theo factory | Không đồng nghĩa đã tạo instance nào |
| **ConfigurableListableBeanFactory.getBeanDefinition(name)** | Đọc metadata của bean definition cục bộ | Không trả về instance của bean |

Ví dụ một đoạn kiểm tra chỉ đọc đối với metadata đã có:

~~~java
// bf là ConfigurableListableBeanFactory nhận từ ApplicationContext.
// Đoạn này minh họa, chưa phải chương trình Java độc lập.
String name = "lazyTask";

boolean defined = bf.containsBeanDefinition(name);
boolean singletonObjectPresent = bf.containsSingleton(name);

System.out.println("defined=" + defined);
System.out.println("singletonObjectPresent=" + singletonObjectPresent);
~~~

Với **lazyTask** trong ví dụ runnable, trước lần **getBean("lazyTask")**, dòng trên sẽ in **defined=true** và **singletonObjectPresent=false**. Chú ý: **containsSingleton** có nghĩa là singleton registry hiện giữ đối tượng tương ứng; nó không phải kiểm tra toàn cục việc constructor của *mọi* loại bean trong tất cả scope đã từng chạy hay chưa.

**Ngoại lệ đáng nhớ:** **DefaultListableBeanFactory.registerSingleton(...)** cho phép đưa trực tiếp một instance vào singleton registry; đối tượng đó không bắt buộc đi qua BeanDefinition thông thường. **FactoryBean** có hai tầng (factory object và product object), nên truy xuất tên bean và tên có tiền tố **&** có ngữ nghĩa khác. Với các trường hợp đặc biệt này, không áp dụng máy móc sơ đồ “một definition → một instance”.

## 7. Liên hệ thực tế với auto-configuration của Spring Boot

Khi đọc source hoặc condition report, hãy tách ba loại trạng thái:

1. **Không có bean definition của nhánh**: condition class/property/bean không đạt, hoặc auto-configuration không được import/excluded. Không có gì để tạo từ nhánh đó.
2. **Có definition nhưng chưa có instance**: thường gặp ở singleton lazy, prototype trước lần getBean, hoặc bean thuộc scope chưa hoạt động. Condition có thể đã match hoàn toàn.
3. **Có definition và đã cố tạo instance nhưng thất bại**: ví dụ thiếu dependency cần inject, constructor ném exception, cấu hình kết nối không hợp lệ. Ở đây lỗi xảy ra ở giai đoạn khởi tạo, không phải lúc chọn nhánh condition.

**@ConditionalOnMissingBean** thường được dùng để Spring Boot “back off” khi ứng dụng có bean tùy biến. Cụ thể, nếu ứng dụng đăng ký definition cho bean **PaymentClient** nhưng bean đó lazy và chưa có instance, auto-configuration có điều kiện thiếu bean theo cùng kiểu **vẫn có thể bị loại**. Nó không cần chờ đối tượng PaymentClient được tạo xong để biết rằng một bean phù hợp đã được ứng dụng khai báo.

Trình tự tư duy:

~~~text
Có thư viện / class cần thiết?
          |
        Có
          v
Nhánh auto-configuration thỏa các condition khác?
          |
        Có
          v
Đã có bean definition phù hợp làm @ConditionalOnMissingBean thất bại?
          |
     Có --+--> Không đăng ký default BeanDefinition
          |
        Không
          v
Đăng ký default BeanDefinition
          |
          v
Scope + lazy + dependency + lifecycle quyết định lúc tạo instance
~~~

Sơ đồ nhằm diễn đạt một nhánh default **có @ConditionalOnMissingBean**; không áp dụng cho tất cả auto-configuration. Điều kiện có thể nằm ở lớp hoặc phương thức và có thể liên quan đến tên bean, annotation, search strategy hoặc điều kiện khác. Không suy ra việc “bean cùng kiểu tồn tại” luôn loại mọi cấu hình khác.

### 7.1. Condition evaluation report trả lời điều gì?

Khởi động một ứng dụng Spring Boot với tham số **--debug** hoặc bật logging chẩn đoán phù hợp để xem **condition evaluation report**. Báo cáo giúp biết auto-configuration nào **match/không match** và lý do. Nó giải thích **quyết định điều kiện**, nhưng **không phải nhật ký khởi tạo constructor của từng instance**.

Ví dụ với ứng dụng thực có logging cho phép:

~~~bash
java -jar target/app.jar --debug
~~~

Đây là lệnh mẫu cho một JAR tên app.jar trong ứng dụng khác; với dự án runnable ở mục 4, dùng tên JAR thực và bỏ **logging.level.root=OFF** nếu muốn xem log. Điều kiện match không chứng minh khởi tạo thành công; condition report cũng không thay thế stack trace của **BeanCreationException**.

### 7.2. Khi nào nên dùng actuator/beans?

Với ứng dụng có Actuator và endpoint được cấu hình, **/actuator/beans** cho thấy thông tin về bean trong các ApplicationContext, như tên/kiểu/scope/dependencies theo dữ liệu được cung cấp. Nó hữu ích để kiểm tra **định danh và cấu hình bean**, nhưng không nên coi riêng danh sách đó là phép đếm chính xác số đối tượng prototype từng tạo. Nếu cần lý do auto-configuration match hoặc không match, **/actuator/conditions** đúng mục đích hơn.

Các endpoint Actuator phải được cấu hình exposure và bảo vệ phù hợp; starter Actuator không có nghĩa mọi endpoint đều công khai.

## 8. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Hệ quả | Cách kiểm tra đúng |
| --- | --- | --- |
| “Có @Bean là đã chạy phương thức tạo bean.” | Đánh đồng định nghĩa với runtime | Tìm dấu mốc tạo instance hoặc kiểm tra singleton registry |
| “Condition match thì bean đã được tạo thành công.” | Bỏ sót lỗi BeanCreationException | Phân biệt condition report với lỗi lúc refresh/getBean |
| “@ConditionalOnMissingBean chỉ kiểm tra object đã tạo.” | Dự đoán sai cơ chế back off | Kiểm tra bean definition đã được xử lý và điều kiện cụ thể |
| “@Lazy chắc chắn không bao giờ tạo trong startup.” | Bỏ qua dependency eager yêu cầu bean | Kiểm tra chuỗi dependency và chỗ inject |
| “Prototype được inject vào singleton thì tự làm mới mỗi lần gọi.” | Giữ cùng instance trong singleton | Dùng ObjectProvider nếu cần truy xuất prototype từng lần |
| “isSingleton=true nghĩa là đã có instance.” | Không nhận ra lazy singleton | So sánh isSingleton với containsSingleton |
| “Đọc bằng getBean chỉ để xác minh bean tồn tại.” | Vô tình tạo bean và gây side effect | Dùng API đọc BeanDefinition khi chỉ cần metadata |
| “@Primary tạo hoặc chặn bean mặc định.” | Nhầm lựa chọn injection với điều kiện registration | @Primary giải quyết ưu tiên khi inject, không là điều kiện đăng ký |
| “Spring có đúng một object cho mỗi class singleton.” | Nhầm singleton per bean-name với singleton per class/JVM | Xem bean name, container và scope |
| “Nhìn số lượng definition có thể suy ra số instance.” | Sai với lazy, prototype, FactoryBean và proxy | Quan sát cơ chế tạo, scope và singleton registry |

Một lỗi thực tế: ứng dụng có bean tự khai báo **@Lazy**, nhưng auto-configuration default không xuất hiện. Đây thường là hành vi đúng khi default dùng **@ConditionalOnMissingBean**: định nghĩa do người dùng khai báo đã đủ để framework rút lui. Ngược lại, nếu default definition được đăng ký nhưng bean chưa xuất hiện trên log khởi tạo, hãy xem **lazy/scope** trước khi kết luận auto-configuration không hoạt động.

## 9. Quy trình chẩn đoán một bean cụ thể

Giả sử một ứng dụng cần bean **OrderClient** nhưng chưa rõ vì sao nó không hoạt động. Xác định vấn đề bằng các câu hỏi:

1. **Có candidate config không?** Kiểm tra thư viện chứa auto-configuration và file imports của Spring Boot 3.x; kiểm tra exclude nếu có.
2. **Condition match không?** Xem classpath, property, loại ứng dụng, bean điều kiện và **condition evaluation report**.
3. **BeanDefinition có trong factory không?** Kiểm tra đúng bean name bằng API metadata; chú ý alias/parent context và các định nghĩa đăng ký tùy biến.
4. **Bean thuộc scope gì, có lazy không?** Xem BeanDefinition, các điểm injection và dependency eager.
5. **Object đã được tạo chưa?** Với singleton dùng dấu mốc phù hợp từ singleton registry; với prototype hay request scope cần xét từng lần truy xuất trong scope.
6. **Nếu tạo thất bại, lỗi ở đâu?** Xem stack trace liên quan đến dependency resolution, constructor, factory method, binding, initialization callback hay kết nối tài nguyên.
7. **Nếu nhận được object nhưng hành vi không như mong đợi, có proxy/decorator không?** Kiểm tra kiểu thực, bean được chọn qua **@Qualifier/@Primary**, bean name và AOP trong môi trường tương ứng.

Khi instrument ứng dụng, hạn chế gọi **getBean(...)** trong các callback cấu hình quá sớm; log từ constructor, factory method, BeanPostProcessor hoặc listener đúng giai đoạn là bằng chứng chính xác hơn cho câu hỏi về **thời điểm khởi tạo**.

## 10. Bài tập suy luận

**Bài 1.** Một singleton **@Lazy** có BeanDefinition và đã làm condition **@ConditionalOnMissingBean** của default không đạt. Hỏi instance của bean đó đã chắc chắn được tạo chưa?

**Đáp án:** Chưa. Điều kiện thiếu bean có thể thấy definition phù hợp; singleton lazy có thể vẫn chưa được tạo tới khi có dependency yêu cầu.

**Bài 2.** Trong ứng dụng ở mục 4, hai lần **getBean("prototypeTask")** đều in **CREATE prototypeTask**. Có phải Spring đã đăng ký hai BeanDefinition khác nhau?

**Đáp án:** Không. Một definition mang scope prototype có thể tạo nhiều instance.

**Bài 3.** Sau khi **SpringApplication.run(...)** trả về, **containsBeanDefinition("lazyTask") = true**, **containsSingleton("lazyTask") = false**. Có mâu thuẫn không?

**Đáp án:** Không. Spring đã biết cách tạo bean nhưng chưa giữ instance singleton. Kết quả hợp lý nếu chưa có điểm nào ép tạo lazyTask.

**Bài 4.** Một bean singleton không lazy có definition được chọn nhưng ứng dụng báo **BeanCreationException** ở constructor. Có thể nói auto-configuration không đăng ký bean không?

**Đáp án:** Không thể kết luận như vậy. Ngược lại, lỗi constructor thường cho thấy Spring đang cố tạo instance từ một definition; cần xem stack trace và nguyên nhân tạo bean thất bại.

**Bài 5.** Một singleton giữ field là prototype bean được inject một lần. Gọi phương thức trên singleton mười lần có tạo mười prototype mới không?

**Đáp án:** Không tự động. Phải yêu cầu lại prototype qua provider hoặc cơ chế lookup thích hợp nếu muốn mỗi lượt một instance.

## 11. Ghi nhớ

Khi Spring Boot quyết định một auto-configuration có được áp dụng hay không, câu hỏi trọng tâm là **các BeanDefinition nào đủ điều kiện để được đăng ký**. Khi Spring container vận hành, câu hỏi tiếp theo là **instance nào được khởi tạo, vào lúc nào, trong scope nào và có thành công hay không**.

Dùng **BeanDefinition/condition report** để tìm hiểu **lựa chọn cấu hình**; dùng **scope, lazy, dependency graph, lifecycle callback và lỗi BeanCreationException** để hiểu **quá trình tạo đối tượng**. Giữ rõ hai tầng này sẽ giải thích được vì sao bean đã được khai báo nhưng chưa có object, vì sao bean mặc định rút lui dù bean người dùng lazy, và vì sao một prototype có thể sinh nhiều object từ cùng một định nghĩa.

### Nguồn tham khảo

- Spring Framework, *Bean Overview*: https://docs.spring.io/spring-framework/reference/core/beans/definition.html
- Spring Framework, *Bean Scopes*: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework, *Lazy-initialized Beans*: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Framework, *Container Extension Points*: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
