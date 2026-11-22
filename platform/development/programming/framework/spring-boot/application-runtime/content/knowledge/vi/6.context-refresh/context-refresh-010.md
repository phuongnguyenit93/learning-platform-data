# Thiết kế phân cấp bằng SpringApplicationBuilder.parent, child và sibling

Một ứng dụng Spring Boot không nhất thiết chỉ có một `ApplicationContext`. Với `SpringApplicationBuilder`, ta có thể ghép các context thành **cây cha–con (parent–child)**, hoặc tạo **các context cùng cấp (sibling)** có chung một parent. Mỗi context có bean registry và vòng đời riêng, nhưng child có thể tra cứu bean do parent sở hữu. Đây là một cách tổ chức những thành phần dùng chung và những thành phần cần được khởi tạo, vận hành hoặc dừng riêng trong cùng JVM.

Bài học tập trung vào **đúng ngữ nghĩa ba API `parent(...)`, `child(...)` và `sibling(...)`**, cách lấy reference của từng context, hướng tra cứu bean, cách truyền tham số khởi động, quản lý `Environment` và đóng context theo thứ tự an toàn. Ví dụ chạy với Java 17+ và Spring Boot 3.3.x.

## 1. Nhìn phân cấp context như một cây, không phải một danh sách bean

Giả sử một ứng dụng có thành phần dùng chung (cấu hình nền tảng, client, service lõi) và hai nhóm chức năng cần hoạt động độc lập:

~~~text
                         JVM (một process)
                               |
                     Parent ApplicationContext
                     + CommonService
                     + SharedCounter
                               |
                 +-------------+--------------+
                 |                            |
        Child A ApplicationContext    Child B ApplicationContext
        + AlphaTask                   + BetaTask
        + Bean riêng của A            + Bean riêng của B
                 |                            |
           lookup Parent                lookup Parent
           không lookup B               không lookup A
~~~

Tại đây:

- **Parent** sở hữu những bean dùng chung. Khi A hoặc B cần một bean không tìm thấy trong container của mình, quá trình tra cứu có thể đi lên parent.
- **Child A** và **Child B** sở hữu bean riêng. Chúng không tự nhìn thấy bean chỉ tồn tại trong sibling còn lại.
- **Parent không tự nhìn xuống child** để tìm bean; chiều tra cứu bình thường là từ child lên parent.
- **Mỗi context có lifecycle riêng**. Đóng A không tự đóng B hay parent; nhưng tài nguyên chia sẻ và sự kiện có thể khiến các context ảnh hưởng gián tiếp đến nhau.

Đây vẫn là **một JVM**: các context có thể chia sẻ classloader, static fields, file, cổng mạng và dịch vụ bên ngoài. Phân cấp Spring không tạo ra ranh giới cách ly process.

Một bean `singleton` là singleton **trong container sở hữu bean đó**. Nếu parent tạo `SharedCounter`, A và B có thể tra cứu đúng **cùng một instance** của parent. Nhưng nếu A và B mỗi bên tự khai báo một bean `SharedCounter`, đó là hai instance riêng và có thể che khuất bean ở parent khi lookup theo tên hoặc type.

## 2. `SpringApplicationBuilder` giải quyết việc gì?

`SpringApplicationBuilder` nằm trong package `org.springframework.boot.builder`. Nó là API fluent để cấu hình `SpringApplication` và hỗ trợ dựng quan hệ giữa nhiều `ApplicationContext`.

| API | Hành động | Builder được trả về | Điểm dễ nhầm |
|---|---|---|---|
| `parent(Class<?>... sources)` | Thêm một application làm parent cho builder hiện tại. | **Parent builder** vừa tạo/chỉ định. | Nếu gọi `run()` ngay trên kết quả của `parent(...)`, bạn đang gọi trên parent builder. |
| `parent(ConfigurableApplicationContext parent)` | Gắn một parent context đã chạy vào builder hiện tại. | **Builder hiện tại**. | Parent đã có sẵn; phải quản lý thời gian sống của parent. |
| `child(Class<?>... sources)` | Tạo một application con của builder hiện tại. | **Child builder** mới. | Cấu hình và bean definitions không được tự sao chép toàn bộ; đây là context khác. |
| `sibling(Class<?>... sources)` | Tạo builder cho một context khác có cùng parent. | **Sibling builder** mới. | Có side effect: có thể khởi chạy application hiện tại và parent **không có args** nếu chưa chạy. |
| `sibling(Class<?>[] sources, String... args)` | Tạo sibling, đồng thời chỉ định arguments cho bước khởi động application hiện tại và parent nếu chưa chạy. | **Sibling builder** mới. | `args` của overload này phục vụ phần khởi động bị kích hoạt sớm; sibling mới vẫn cần được `run(args)`. |
| `run(String... args)` | Chạy application hiện tại; nếu cấu hình parent chưa chạy, parent được chạy trước. | **ConfigurableApplicationContext** của builder hiện tại. | Trả về context ở node bạn đang gọi, không phải toàn bộ cây. |
| `context()` | Lấy context đã được builder khởi chạy. | Context hoặc `null` nếu chưa khởi chạy. | Hữu ích khi `sibling(...)` đã khởi động builder khác như side effect. |

Hai lời gọi đơn giản thường gặp:

~~~java
ConfigurableApplicationContext child =
        new SpringApplicationBuilder(ParentConfig.class)
                .child(ChildConfig.class)
                .run(args);
~~~

Và:

~~~java
SpringApplicationBuilder childBuilder =
        new SpringApplicationBuilder(ChildConfig.class);

childBuilder.parent(ParentConfig.class); // Không chain run trên kết quả parent()
ConfigurableApplicationContext child = childBuilder.run(args);
~~~

Các đoạn trên **minh họa API**, giả định `ParentConfig`/`ChildConfig` là hai lớp cấu hình Spring hợp lệ và các import đã có. Cả hai cách đều có chủ đích khởi chạy **child** (parent sẽ được khởi chạy trước nếu cần).

Một lỗi dễ mắc là:

~~~java
new SpringApplicationBuilder(ChildConfig.class)
        .parent(ParentConfig.class)
        .run(args);
~~~

Lời gọi `parent(Class...)` **trả về parent builder**, vì vậy chuỗi trên không vận hành như cách đọc “chạy child”. Muốn điều khiển chính xác builder nào được `run`, lưu reference của child trước như ví dụ trên, hoặc bắt đầu từ parent rồi gọi `child(...).run(args)`.

## 3. Cách dùng `child(...)`: gốc trước, nhánh con sau

Đây là cấu trúc dễ hiểu nhất:

~~~java
SpringApplicationBuilder rootBuilder =
        new SpringApplicationBuilder(ParentConfig.class)
                .web(WebApplicationType.NONE);

SpringApplicationBuilder childBuilder =
        rootBuilder.child(ChildConfig.class)
                .web(WebApplicationType.NONE);

ConfigurableApplicationContext child = childBuilder.run(args);
ConfigurableApplicationContext parent = rootBuilder.context();
~~~

Đoạn này là một phần chương trình, cần các lớp `ParentConfig` và `ChildConfig` hợp lệ. `WebApplicationType.NONE` tránh mở web server để tập trung quan sát BeanFactory và vòng đời.

**Điều gì xảy ra khi `childBuilder.run(args)`?**

1. Boot nhận biết builder của child có parent.
2. Nếu parent chưa chạy, parent được khởi chạy trước với arguments được chuyển theo builder.
3. Child được gắn với parent context đã có.
4. Child được cấu hình và refresh theo các source của riêng nó.
5. `run(...)` trả về **child context**; `rootBuilder.context()` là cách lấy riêng parent context.

Nếu cùng một bean type chỉ được khai báo trong parent, child có thể lấy bằng `child.getBean(Type.class)` thông qua hierarchical lookup. Nếu child có định nghĩa cùng tên, bản định nghĩa ở child có thể che bean ở parent trong quá trình lookup; tuy nhiên chuyện tiêm theo type vẫn cần xét số lượng candidate và qualifier, không nên coi mọi trường hợp trùng type đều tự động được giải quyết.

Đừng xem `child(...)` là sao chép parent. Parent và child là **hai container** có quan hệ lookup, không phải một container duy nhất với hai tên.

## 4. Cách dùng `parent(...)`: chú ý builder trả về

Có hai nhóm tình huống.

### Tạo parent từ lớp cấu hình

Khi đã có child builder:

~~~java
SpringApplicationBuilder childBuilder =
        new SpringApplicationBuilder(ChildConfig.class)
                .web(WebApplicationType.NONE);

SpringApplicationBuilder parentBuilder =
        childBuilder.parent(ParentConfig.class)
                .web(WebApplicationType.NONE);

ConfigurableApplicationContext child = childBuilder.run(args);
ConfigurableApplicationContext parent = parentBuilder.context();
~~~

`parent(Class<?>... sources)` thêm parent ở trên child. Vì nó **trả về parent builder**, lời gọi `.web(NONE)` trong phép gán ở trên áp dụng cho parent; child đã có `web(NONE)` riêng. Giữ cả hai biến giúp code dễ theo dõi và dễ đóng theo thứ tự.

### Dùng parent đã chạy

Nếu parent được xây dựng trước theo một vòng đời riêng:

~~~java
ConfigurableApplicationContext parent =
        new SpringApplicationBuilder(ParentConfig.class)
                .web(WebApplicationType.NONE)
                .run(args);

ConfigurableApplicationContext child =
        new SpringApplicationBuilder(ChildConfig.class)
                .web(WebApplicationType.NONE)
                .parent(parent)
                .run(args);
~~~

Ở overload nhận `ConfigurableApplicationContext`, `parent(parent)` **trả về builder hiện tại**, vì nó gắn một context đã chạy. Đây là đoạn minh họa; trong code thật cần `try/finally` để đóng child trước parent nếu một trong các bước thất bại.

Lợi ích của dạng này là chia sẻ một parent đã được tạo và duy trì bởi code khác. Đổi lại, bạn phải quy định rất rõ **chủ sở hữu parent**: child chỉ “mượn” bean/tài nguyên từ parent, không được tự ý quyết định khi nào parent kết thúc khi còn những child khác đang dùng.

## 5. Cách dùng `sibling(...)`: hai nhánh cùng cha

Một sibling không phải “con của child hiện tại”. Nó là **một child khác của cùng parent**.

~~~text
parentBuilder
    |
    +-- alphaBuilder  ----- sibling(...) -----> betaBuilder
    |         |                              |
    |     Child A                          Child B
    +----------- cùng Parent context --------+
~~~

Giả sử ta đã có:

~~~java
SpringApplicationBuilder parentBuilder =
        new SpringApplicationBuilder(ParentConfig.class)
                .web(WebApplicationType.NONE);

SpringApplicationBuilder alphaBuilder =
        parentBuilder.child(AlphaConfig.class)
                .web(WebApplicationType.NONE);
~~~

Có thể tạo sibling như sau:

~~~java
SpringApplicationBuilder betaBuilder =
        alphaBuilder.sibling(new Class<?>[] {BetaConfig.class}, args)
                .web(WebApplicationType.NONE);

ConfigurableApplicationContext beta = betaBuilder.run(args);
ConfigurableApplicationContext alpha = alphaBuilder.context();
ConfigurableApplicationContext parent = parentBuilder.context();
~~~

Ở overload `sibling(new Class<?>[]{...}, args)`, **việc gọi `sibling(...)` có thể đã chạy parent và alpha** nếu chúng chưa hoạt động. Do đó `alphaBuilder.context()` có thể lấy được context mà không cần gọi `alphaBuilder.run(args)` riêng lần nữa. Gọi `betaBuilder.run(args)` là bước khởi chạy beta.

**Vì sao phải lưu cả ba builder?** Vì mỗi builder giữ reference đến một context khác nhau. Nếu chỉ giữ biến trỏ tới `betaBuilder`, mã cleanup khó biết chắc các context đã khởi tạo ở bước side effect là những context nào.

Nếu dùng overload ngắn:

~~~java
SpringApplicationBuilder betaBuilder = alphaBuilder.sibling(BetaConfig.class);
~~~

API có thể tự chạy alpha và parent với **arguments rỗng** nếu chưa chạy. Nếu chương trình cần `--spring.profiles.active=dev` hoặc cấu hình từ command line ngay khi parent/alpha khởi động, hãy gọi overload nhận `args` hoặc chủ động chạy các context trước khi tạo sibling. Không kỳ vọng lời gọi `betaBuilder.run(args)` về sau sẽ tự động làm thay đổi các context đã được khởi chạy.

## 6. Ví dụ Java hoàn chỉnh: parent và hai sibling chia sẻ một bean

Ví dụ dưới đây tạo đúng **ba context**: parent chứa bộ đếm dùng chung; child A và child B mỗi bên chứa một service riêng. Nó kiểm chứng hướng tra cứu bean và cho thấy đóng A không khiến B hay parent ngừng hoạt động.

Tạo file `src/main/java/com/example/hierarchy/HierarchyDemo.java`:

~~~java
package com.example.hierarchy;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class HierarchyDemo {

    private HierarchyDemo() {
    }

    public static void main(String[] args) {
        SpringApplicationBuilder parentBuilder =
                new SpringApplicationBuilder(ParentConfig.class)
                        .web(WebApplicationType.NONE);

        SpringApplicationBuilder alphaBuilder =
                parentBuilder.child(AlphaConfig.class)
                        .web(WebApplicationType.NONE);

        SpringApplicationBuilder betaBuilder = null;

        try {
            // Lệnh sibling có thể khởi chạy parent và alpha.
            // Overload có args chuyển args cho những app được chạy sớm.
            betaBuilder = alphaBuilder
                    .sibling(new Class<?>[] {BetaConfig.class}, args)
                    .web(WebApplicationType.NONE);

            // Khởi chạy beta, lấy các context đã được builder tạo.
            ConfigurableApplicationContext beta =
                    betaBuilder.run(args);
            ConfigurableApplicationContext alpha =
                    alphaBuilder.context();
            ConfigurableApplicationContext parent =
                    parentBuilder.context();

            SharedCounter counterA = alpha.getBean(SharedCounter.class);
            SharedCounter counterB = beta.getBean(SharedCounter.class);

            System.out.println(
                    "A va B cung cha: "
                            + (alpha.getParent() == beta.getParent()));
            System.out.println(
                    "Parent so huu counter: "
                            + parent.containsLocalBean("sharedCounter"));
            System.out.println(
                    "A va B chung counter: " + (counterA == counterB));
            System.out.println(
                    "B thay alphaTask: " + beta.containsBean("alphaTask"));

            System.out.println(
                    "Gia tri tu A: "
                            + alpha.getBean(AlphaTask.class).next());
            System.out.println(
                    "Gia tri tu B: "
                            + beta.getBean(BetaTask.class).next());

            // Dong A trong khi beta va parent van dang song.
            alpha.close();

            System.out.println("A active: " + alpha.isActive());
            System.out.println("B active: " + beta.isActive());
            System.out.println(
                    "Gia tri tu B sau khi dong A: "
                            + beta.getBean(BetaTask.class).next());
        } finally {
            // Dong theo thu tu child beta -> child alpha -> parent.
            // Moi finally luon thu dong context tiep theo, ke ca khi
            // mot buoc dong khac nem exception.
            try {
                closeIfActive(
                        betaBuilder == null ? null : betaBuilder.context());
            } finally {
                try {
                    closeIfActive(alphaBuilder.context());
                } finally {
                    closeIfActive(parentBuilder.context());
                }
            }
        }
    }

    private static void closeIfActive(
            ConfigurableApplicationContext context) {
        if (context != null && context.isActive()) {
            context.close();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ParentConfig {

        @Bean(destroyMethod = "close")
        SharedCounter sharedCounter() {
            return new SharedCounter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AlphaConfig {

        @Bean
        AlphaTask alphaTask(SharedCounter counter) {
            return new AlphaTask(counter);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BetaConfig {

        @Bean
        BetaTask betaTask(SharedCounter counter) {
            return new BetaTask(counter);
        }
    }

    public static final class SharedCounter implements AutoCloseable {

        private final AtomicInteger value = new AtomicInteger();

        int next() {
            return value.incrementAndGet();
        }

        @Override
        public void close() {
            System.out.println("Parent counter da duoc dong");
        }
    }

    public static final class AlphaTask {

        private final SharedCounter counter;

        public AlphaTask(SharedCounter counter) {
            this.counter = counter;
        }

        int next() {
            return counter.next();
        }
    }

    public static final class BetaTask {

        private final SharedCounter counter;

        public BetaTask(SharedCounter counter) {
            this.counter = counter;
        }

        int next() {
            return counter.next();
        }
    }
}
~~~

Đây là một **file Java đầy đủ**; các lớp cấu hình được đặt dưới dạng `public static` nested classes để không cần tạo nhiều file nhỏ. Dự án cần có Spring Boot starter, nhưng không cần HTTP server. Ta dùng các `@Configuration` cụ thể làm primary sources thay vì `@SpringBootApplication` để tránh component scan vô tình đưa toàn bộ cấu hình A, B và parent vào cùng một context.

Nếu bạn cần một dự án Gradle độc lập, `build.gradle` tối thiểu cho ví dụ:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.hierarchy.HierarchyDemo'
}
~~~

Chạy từ thư mục dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `.\gradlew.bat bootRun`. Nếu chưa tạo wrapper, cần chuẩn bị Gradle và dự án Spring Boot trước; riêng `javac HierarchyDemo.java` không đủ vì code cần Spring Boot/Spring Framework trên classpath.

Bỏ qua banner và các log do Spring Boot in thêm, **những dòng do chương trình tự in** xuất hiện theo thứ tự:

~~~text
A va B cung cha: true
Parent so huu counter: true
A va B chung counter: true
B thay alphaTask: false
Gia tri tu A: 1
Gia tri tu B: 2
A active: false
B active: true
Gia tri tu B sau khi dong A: 3
Parent counter da duoc dong
~~~

Tại sao có kết quả này?

1. Parent tạo đúng một bean `sharedCounter`. A và B không tự định nghĩa bean này nên có thể lấy từ parent; phép so sánh reference cho `true`.
2. A tạo `alphaTask`, B tạo `betaTask`. B tra cứu theo tên `alphaTask` không tìm thấy vì bean này chỉ nằm trong sibling A.
3. Hai service cùng gọi `next()` trên một `SharedCounter` của parent nên bộ đếm tăng từ 1 lên 2 rồi 3.
4. `alpha.close()` đánh dấu A ngừng hoạt động, còn beta và parent vẫn hoạt động. B vẫn dùng được counter của parent.
5. Khối `finally` đóng B, bỏ qua A vì A đã đóng, rồi đóng parent. Chỉ khi parent đóng, destroy callback của `sharedCounter` mới in `Parent counter da duoc dong`.

Trong lần chạy thực tế, log về việc khởi tạo nhiều Spring application có thể xen giữa các dòng trên. Vì `WebApplicationType.NONE` và chỉ có một luồng chính thực thi lời gọi đến bộ đếm, các giá trị 1, 2, 3 trong ví dụ này là xác định.

## 7. Bean visibility: hướng nhìn một chiều và ghi đè ở child

Một cây context có thể hình dung theo quy tắc tra cứu:

~~~text
Child A: tim bean o A -> khong co thi tim o Parent
Child B: tim bean o B -> khong co thi tim o Parent
Parent:  tim bean o Parent; khong tu tim o A/B
Child A: khong tu tim bean chi ton tai o Child B
~~~

Bảng sau giúp phân biệt các câu hỏi:

| Câu hỏi | Kết quả thông thường |
|---|---|
| A có lấy được `SharedCounter` chỉ được đăng ký ở parent không? | Có, thông qua ancestor bean factory. |
| B có lấy được chính instance đó không? | Có, nếu B dùng bean ở parent và không khai báo bản riêng. |
| B có tự lấy được `AlphaTask` chỉ đăng ký ở A không? | Không. |
| Parent có tự lấy `BetaTask` chỉ đăng ký ở B không? | Không. |
| A định nghĩa bean trùng tên với parent thì sao? | Bean ở A có thể che bean cùng tên trong parent khi lookup từ A. |
| Hai child cùng có bean tên `client` thì có xung đột tên không? | Không chỉ vì cùng tên; hai bean registry độc lập. |
| Bean singleton có tồn tại đúng một lần trên toàn JVM không? | Không. Singleton thông thường thuộc container sở hữu bean; chỉ khi dùng một bean của parent mới là một instance được các child chia sẻ. |

Các phương thức giúp kiểm tra:

~~~java
alpha.containsLocalBean("sharedCounter"); // false
alpha.containsBean("sharedCounter");      // true
parent.containsLocalBean("sharedCounter");// true
beta.containsBean("alphaTask");          // false
~~~

Đây là đoạn minh họa trong bối cảnh ví dụ ở trên. `containsLocalBean` kiểm tra chính container đó; `containsBean` có thể tính tới bean từ ancestor.

**Cảnh báo khi cấu hình:** Nếu parent chứa `@ComponentScan` quá rộng, parent có thể tạo luôn bean dự kiến dành riêng cho child. Nếu child cũng scan toàn bộ package của parent, một số bean có thể bị tạo hai lần. Vì vậy khi thiết kế phân cấp, chọn ranh giới package và các lớp `@Configuration` có chủ đích. Việc đặt `@SpringBootApplication` ở cả ba context với cùng package gốc rất dễ tạo cấu hình trùng lặp khó hiểu.

## 8. `Environment`, profiles và tham số không hoàn toàn độc lập

Mặc dù mỗi context có bean registry riêng, cơ chế builder có thể **sao chép hoặc chia sẻ thiết lập environment** giữa các node. Theo API `SpringApplicationBuilder`, khi tạo child, default arguments và environment được truyền xuống theo ngữ nghĩa của builder; khi thêm parent, các thiết lập liên quan có thể được truyền lên. Boot cũng có những quy tắc riêng khi cấu hình profile/property source trong hierarchy.

Vì vậy:

- Đừng tự suy luận A và B có bộ profiles hoặc `application.properties` hoàn toàn tách biệt chỉ vì chúng là hai context.
- Gọi `profiles("dev")` ở builder cần được đánh giá trên **toàn hierarchy** vì method này có thể ảnh hưởng parent/children. Kiểm tra `Environment.getActiveProfiles()` ở từng context sau khi chạy.
- Một property cùng tên có thể xuất hiện ở nhiều property source. Ưu tiên cấu hình phải được kiểm tra theo thực tế Boot đang xử lý, đặc biệt khi kết hợp command line và defaults.
- Dùng overload `sibling(Class[], args)` nếu cần parent/child đầu tiên nhận args ngay khi sibling kích hoạt khởi chạy chúng.
- Với `parent(ConfigurableApplicationContext)`, parent đã có `Environment` và lifecycle riêng; child không được mặc nhiên sửa cấu hình đã được parent áp dụng trước đó.

Ví dụ minh họa cách quan sát environment:

~~~java
System.out.println(
        java.util.Arrays.toString(
                parent.getEnvironment().getActiveProfiles()));
System.out.println(
        java.util.Arrays.toString(
                alpha.getEnvironment().getActiveProfiles()));
System.out.println(
        java.util.Arrays.toString(
                beta.getEnvironment().getActiveProfiles()));
~~~

Đoạn này sử dụng biến từ ví dụ mục 6. Không nên giả định mảng profiles giống nhau hay khác nhau trước khi đã định nghĩa rõ nguồn cấu hình và kiểm tra ở từng context.

Nếu yêu cầu nghiệp vụ đòi cách ly cấu hình tuyệt đối, môi trường JVM riêng hoặc process riêng có thể thích hợp hơn một Spring hierarchy.

## 9. Khi phân cấp có web server

Spring Boot tự xác định `WebApplicationType` theo classpath nếu bạn không đặt tường minh. Khi xây dựng hierarchy chứa Spring MVC hoặc WebFlux, tài liệu Boot khuyến nghị **đặt các web component ở child context**, còn parent cung cấp các service/configuration dùng chung.

Chẳng hạn, về mặt kiến trúc:

~~~text
Parent (NONE)
 +-- DataSource / Service dùng chung
 |
 +-- Child API A (SERVLET, server.port=8081)
 +-- Child API B (SERVLET, server.port=8082)
~~~

Đây chỉ là **sơ đồ triển khai**, không phải cấu hình runnable hoàn chỉnh. Khi có nhiều web child thực sự khởi động máy chủ nhúng riêng, phải bảo đảm chúng không bind cùng một địa chỉ và cổng. Nếu hai child đều cố mở 8080, một child có thể thất bại vì cổng đã sử dụng.

Một số lưu ý khác:

- Parent nên tập trung vào những bean không phụ thuộc servlet context/request scope; đặt controller, servlet filter và cấu hình web ở child tương ứng.
- Mỗi web child có thể tạo máy chủ nhúng riêng. Đóng child có thể dừng server của child đó, trong khi các sibling còn hoạt động.
- Nếu nhiều child dùng chung một `DataSource`, pool từ parent sẽ tồn tại cho tới khi parent đóng. Đừng đóng pool trước khi tất cả child đã ngừng sử dụng.
- Đừng tự tin rằng đặt `.properties("server.port=8081")` trên builder luôn thắng command-line arguments: nó là default property, cần kiểm tra giá trị có hiệu lực.
- Kỹ thuật nhiều web context trong một JVM có chi phí và độ phức tạp vận hành; thường chỉ dùng khi có yêu cầu vòng đời hoặc cách ly bean rõ ràng.

Nếu chỉ cần chia logic thành nhiều chức năng API, **một context với các package hoặc module code khác nhau** thường dễ vận hành hơn.

## 10. Vòng đời: parent khởi động trước, parent đóng sau

Với một hierarchy do builder tạo và chạy, quan hệ phụ thuộc tự nhiên là:

~~~text
START:
  Parent -> Child A -> Child B
  (A có thể được sibling() tự chạy trước khi B.run())

STOP:
  Child B -> Child A -> Parent
~~~

Đây là **thứ tự được chủ động thiết kế**, không phải lời hứa Spring sẽ luôn tự đóng mọi node trong cây đúng một lượt khi bạn đóng bất kỳ node nào.

Vì sao parent nên đóng cuối? Child có thể đang dùng bean do parent sở hữu như pool kết nối, scheduler, cache hoặc authentication service. Đóng parent sớm khiến các reference mà child đang giữ trỏ tới tài nguyên đã bị shutdown, dù `child.isActive()` vẫn trả `true`.

Các trường hợp cần phân biệt:

- **Đóng A:** A hủy những singleton do A sở hữu; B và parent không tự bị đóng.
- **Đóng parent:** parent hủy bean do parent sở hữu. Các child chưa đóng có thể vẫn tồn tại nhưng trở nên lỗi vì phụ thuộc đã hủy.
- **Đóng B sau A:** B chạy lifecycle cleanup độc lập; những bean có nguồn gốc parent không nên bị B tự hủy như tài nguyên riêng.
- **Cùng một resource được khai báo quyền hủy ở nhiều context:** có nguy cơ double-close hoặc context này làm hỏng tài nguyên mà context kia vẫn dùng.

Ví dụ mục 6 đặt `@Bean(destroyMethod="close")` **chỉ tại parent**. A và B chỉ giữ reference, không đăng ký thêm quyền destroy cho cùng object. Đây là điểm quan trọng khi chia sẻ connection pool, executor hoặc file handle.

Với tác vụ chạy nền, trước khi đóng parent cần dừng nhận việc mới, xử lý hoặc huỷ những việc đang chạy theo chính sách ứng dụng, rồi đóng các context phụ thuộc. Nếu parent giữ một `ExecutorService` mà worker của B vẫn submit task, đóng parent trước có thể gây `RejectedExecutionException` hoặc mất công việc.

### Dùng `try/finally` khi có nhiều node

Khởi tạo sibling có side effect, nên đoạn code tạo sibling cũng nên nằm **bên trong vùng cleanup**. Ví dụ mục 6 thiết kế điều đó bằng cách tạo parent builder và alpha builder, sau đó bao cả `sibling(...)` và `run(...)` trong `try/finally`. Nếu khởi chạy B thất bại, những context parent và A đã khởi động vẫn được xem xét đóng.

Với hierarchy phức tạp hơn, có thể giữ danh sách những node đã khởi tạo thành công và đóng theo thứ tự phụ thuộc ngược, đồng thời báo cáo exception khi cleanup. Không nên gọi `System.exit(...)` để dừng một child vì lệnh đó tác động toàn JVM.

## 11. Sự kiện Spring có thể truyền từ child lên parent

Spring hỗ trợ propagation của một số `ApplicationEvent` từ child lên các ancestor. Điều này có hệ quả: một listener đăng ký ở parent có thể quan sát cả sự kiện của parent **lẫn** sự kiện đi lên từ child.

Ví dụ, với các event liên quan lifecycle/context, listener của parent có thể nhận nhiều event cùng type nhưng từ các context khác nhau. Nếu xử lý không phân biệt nguồn, bạn có thể ghi log trùng, đếm startup sai hoặc thực hiện cleanup nhầm.

Đối với listener nhận `ApplicationContextEvent` (như `ContextRefreshedEvent`), có thể kiểm tra:

~~~java
if (event.getApplicationContext() == ownContext) {
    // Chỉ xử lý event xuất phát từ context của listener.
}
~~~

Đây là đoạn logic minh họa: `event` và `ownContext` phải được khai báo trong một listener thực tế. Với Spring Boot startup event có cung cấp context, dùng API truy cập context phù hợp của event rồi so với context đang quản lý.

**Không coi mọi event là tín hiệu một node độc lập khởi động lần nữa.** Một event từ child đi lên parent có thể khiến listener ở parent được gọi thêm. Đây là khác biệt đáng chú ý khi so sánh hierarchy với hai context hoàn toàn không có quan hệ cha–con.

## 12. Runner, bean lifecycle và điều kiện khởi động

Khi `SpringApplicationBuilder` khởi chạy một node, node đó có quá trình `SpringApplication.run(...)`, refresh, gọi startup runner và phát các event liên quan. Với nhiều node, quá trình này có thể xảy ra nhiều lần.

Trong ví dụ mục 6 không có `CommandLineRunner` để output dễ kiểm chứng. Trong ứng dụng thực tế:

- Một runner được khai báo ở context nào sẽ có quan hệ lifecycle với context đó; đừng mặc nhiên cho rằng mọi runner chỉ chạy một lần trong toàn JVM.
- Các bean `@Scheduled` hoặc message consumer được đăng ký ở nhiều child có thể chạy song song hoặc trùng việc trên cùng queue/data store.
- Một context khởi chạy thất bại trong lúc `sibling(...)` đã khởi tạo parent và child trước đó thì không có nghĩa mọi context sẽ tự rollback cùng lúc; code điều phối cần cleanup những node đã chạy.
- Bean phụ thuộc parent có thể được tạo trong child trước khi child ready; việc parent đã refresh không chứng minh child đã ready.

Khi cần readiness cho từng web child, kiểm tra trạng thái của đúng child thay vì chỉ nhìn `ApplicationReadyEvent` của parent. Nếu chia sẻ datasource hoặc bus, tính healthy của parent cũng chưa đủ để bảo đảm mọi child đều sẵn sàng nhận traffic.

## 13. Khi nào chọn parent–child–sibling?

| Nhu cầu | Lựa chọn hợp lý |
|---|---|
| Chia sẻ một tập bean lõi nhưng nhiều nhóm tính năng có vòng đời riêng | Parent chứa bean dùng chung; mỗi nhóm là child. |
| Hai module độc lập cùng dùng chung service nền tảng, không nhìn bean riêng của nhau | Hai sibling cùng parent. |
| Gắn một context mới vào context nền tảng đã chạy | `parent(ConfigurableApplicationContext)`. |
| Chỉ cần gộp các controller/service trong một ứng dụng web | Một context thường đơn giản hơn. |
| Mỗi nhóm phải có CPU/memory, quyền, fault isolation độc lập | Các process/service riêng; hierarchy trong cùng JVM không tạo cách ly process. |
| Muốn thử nhiều bộ cấu hình trong một tiến trình | Context riêng, chú ý môi trường và tài nguyên chia sẻ. |

Tổ chức parent–child chỉ có giá trị khi ranh giới bean và vòng đời có ý nghĩa thực tế. Không nên tạo cây context chỉ để thay thế cách chia package hoặc dependency injection thông thường.

## 14. Checklist thiết kế và lỗi hay gặp

**Lỗi 1 — Gọi `parent(...).run(args)` rồi tưởng đang chạy child.**

Hãy nhớ overload nhận class source trả về **parent builder**. Lưu child builder riêng hoặc bắt đầu từ parent rồi gọi `child(...).run(args)`.

**Lỗi 2 — Tưởng `sibling(...)` không làm gì trước `run()`.**

API có side effect: có thể khởi chạy current application và parent. Chọn overload nhận `args` khi cần truyền tham số startup sớm; quản lý cleanup ngay cả khi `sibling(...)` ném exception.

**Lỗi 3 — Mong sibling A tự lấy bean riêng của sibling B.**

Lookup bình thường chỉ đi lên ancestor. Đưa bean thực sự cần chia sẻ lên parent hoặc thiết kế một giao diện giao tiếp rõ ràng; không dựa vào sibling lookup ngầm.

**Lỗi 4 — Quét cùng một package quá rộng ở parent và child.**

Có thể tạo duplicate bean, duplicate listener, duplicate scheduler hoặc làm mất ranh giới cấu hình. Chọn source class, scan base package và auto-configuration đúng phạm vi.

**Lỗi 5 — Đóng parent trước khi các child hoàn tất.**

Child có thể tiếp tục active nhưng dependency chung đã bị hủy. Thường đóng các child trước rồi mới đóng parent; nếu có công việc nền, dừng và chờ xử lý theo hợp đồng nghiệp vụ.

**Lỗi 6 — Tưởng environment/profiles của các node hoàn toàn cách ly.**

Builder có cơ chế chia sẻ/điều phối environment/default arguments. Hãy in hoặc kiểm tra properties và active profiles ở từng context để xác nhận.

**Lỗi 7 — Cả hai web child khởi động trên cùng cổng.**

Mỗi server nhúng cần địa chỉ/cổng hợp lệ; tách cổng hoặc đổi kiến trúc. Nhiều context không làm HTTP port tự chia sẻ.

**Lỗi 8 — Parent listener xử lý một sự kiện từ child như của chính parent.**

Kiểm tra source context của event và lọc đúng node. Một số application event có thể truyền lên ancestor.

### Tài liệu tham khảo

- Spring Boot 3.3, `SpringApplicationBuilder` Javadoc: https://docs.spring.io/spring-boot/docs/3.3.0/api/org/springframework/boot/builder/SpringApplicationBuilder.html
- Spring Boot 3.3, `SpringApplication` và phân cấp context: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Ghi nhớ:** `child(...)` tạo một node con, `parent(...)` thêm node cha (lưu ý builder trả về), `sibling(...)` tạo một node ngang cấp có cùng parent và **có thể khởi chạy node hiện tại ngay khi được gọi**. Các child nhìn lên parent để dùng chung bean, sibling không tự nhìn vào nhau. Thiết kế tốt phải xác định chính xác **context sở hữu bean, context nhận arguments, context nào đã được khởi chạy, và ai đóng từng context**.
