# Context hierarchy và phạm vi cấu hình cha, con

## 1. Hiểu đúng chủ đề trong Spring TestContext

Một **context hierarchy** là quan hệ giữa **hai hoặc nhiều đối tượng `ApplicationContext` riêng biệt**: context cấp dưới (child) có thể tra cứu bean ở context cấp trên (parent) khi không tìm được bean phù hợp ở chính mình. Mỗi context có tập bean definition, vòng đời bean và phạm vi cấu hình riêng. Spring TestContext Framework cho phép khai báo quan hệ đó trong bài kiểm thử tích hợp bằng `@ContextHierarchy` kết hợp với `@ContextConfiguration`.

Điểm quan trọng nhất là **hướng tra cứu không đối xứng**:

- **Child → parent:** child dùng được bean của parent thông qua cơ chế tra cứu bean theo cây context.
- **Parent ↛ child:** parent không tự động nhìn thấy bean chỉ được định nghĩa ở child.
- **Child A ↛ child B:** hai context con cùng một parent không tự nhìn thấy bean riêng của nhau.
- **Bean trùng tên:** bean cục bộ ở child có thể **che khuất (shadow)** bean cùng tên ở parent trong quá trình tra cứu qua child; bean trong parent vẫn tồn tại và được parent sử dụng bình thường.

Mục tiêu bài học: hiểu cấu trúc, định nghĩa hierarchy trong bài test Java 17+/Spring Boot, kiểm tra phạm vi bean thật bằng JUnit Jupiter, phân biệt kế thừa cấu hình và kế thừa Java class, và biết tác động của hierarchy lên context cache, `@DirtiesContext`, profile, bean override và Spring MVC.

### 1.1. Trường hợp nào cần hierarchy?

Một context duy nhất đủ cho phần lớn unit test, slice test và integration test Spring Boot. Hierarchy có ý nghĩa khi **ứng dụng thật sự tổ chức các context theo cấp**, chẳng hạn:

1. **Spring MVC kiểu root/DispatcherServlet:** root context chứa service, repository, kết nối hạ tầng; một DispatcherServlet có child `WebApplicationContext` chứa controller, handler mapping và MVC configuration.
2. **Nhiều web context dùng chung nền tảng:** hai servlet/nhóm endpoint cùng thấy dịch vụ của một root nhưng có controller và cấu hình web riêng.
3. **Spring Batch hoặc ứng dụng module hóa:** cấu hình infrastructure nằm ở parent, từng job/module có child context riêng.
4. **Kiểm thử cấu trúc phân tầng cụ thể:** cần chứng minh bean thuộc đúng cấp, child được thừa hưởng cái gì và một thay đổi trong child không làm sai phạm vi của parent.

**Không suy ra rằng mọi ứng dụng Spring Boot tự động có root + child.** Nhiều ứng dụng Boot Servlet thông thường chạy trong một application context. Việc dùng `@SpringBootTest`, `@WebMvcTest` hoặc tổ chức package thành nhiều tầng không tự động tạo context hierarchy. Chỉ khai báo hierarchy khi thiết kế runtime hoặc tình huống kiểm thử thực sự cần.

## 2. Sơ đồ và quy tắc nhìn thấy bean

Hãy tưởng tượng một parent và hai child:

```text
                      Parent ApplicationContext
                    ┌─────────────────────────────┐
                    │ dataSource                  │
                    │ paymentRepository           │
                    │ paymentService              │
                    │ label = "SHARED"            │
                    └───────────┬─────────────────┘
                                │
                  ┌─────────────┴──────────────┐
                  │                            │
          Child A Context               Child B Context
       ┌──────────────────┐          ┌──────────────────┐
       │ restController   │          │ soapEndpoint     │
       │ label = "REST"   │          │ label = "SOAP"   │
       └──────────────────┘          └──────────────────┘

Child A: thấy paymentService, restController; tra label => "REST".
Child B: thấy paymentService, soapEndpoint; tra label => "SOAP".
Parent: không tự thấy restController hay soapEndpoint;
        tra label tại parent vẫn nhận "SHARED".
```

Đây là **sơ đồ khái niệm**, không phải một chương trình triển khai. Trong hierarchy thực, child A và child B là hai đối tượng context khác nhau, có cùng một parent; chúng không biến thành một context gộp.

| Câu hỏi | Ở parent | Ở child |
|---|---|---|
| Có thể tra cứu bean chỉ khai báo tại parent? | Có, cục bộ | Có, thông qua ancestor nếu không bị shadow |
| Có thể tra cứu bean chỉ khai báo tại child? | Không | Có, cục bộ |
| Bean cùng tên tồn tại ở parent và child? | Tra cứu tại parent lấy parent | Tra cứu tại child ưu tiên bean cục bộ |
| Một singleton trong parent có cùng instance khi child truy cập? | Tại parent | Tra cứu từ child có thể trả đúng singleton của parent, nếu không bị che |
| Bean thuộc child có tự xuất hiện tại sibling child? | Không liên quan | Không, sibling không phải ancestor |

### 2.1. Tách biệt bean registration và bean lookup

Khi gọi `child.getBean("paymentService")`, Spring có thể không tìm được tên đó trong child và tiếp tục tìm ở parent. **Điều này không có nghĩa bean đã được copy/đăng ký lại vào child.**

Vì vậy hai API có ý nghĩa khác nhau:

- `child.containsBean("paymentService")` có thể là `true`: tên đó có thể được phân giải khi xét cả parent.
- `child.containsLocalBean("paymentService")` có thể là `false`: chính child không đăng ký bean mang tên đó.
- `child.getParent()` trả context cha trực tiếp; khi là root thì giá trị là `null`.

Muốn kiểm tra “bean đặt đúng cấp”, hãy dùng `containsLocalBean(...)` hoặc trực tiếp tra cứu tại `getParent()` khi phù hợp. Chỉ `@Autowired` thành công chưa chứng minh bean được định nghĩa tại child.

### 2.2. Bean trùng tên không đồng nghĩa lỗi override trong cùng context

Nếu cả parent và child đều có bean tên `label`, child có thể che bean parent theo quy tắc tra cứu theo tên. Parent không bị sửa, và cả hai context vẫn quản lý instance riêng.

Khác biệt cần nhớ:

- **Trùng tên ở hai context khác nhau:** hợp lệ về mặt quan hệ parent/child; tra cứu ở child ưu tiên local.
- **Trùng tên giữa hai bean definition trong cùng một context:** có thể bị từ chối hoặc phụ thuộc chính sách bean definition overriding của chính context đó.
- **Trùng kiểu nhưng khác tên:** khi autowire theo type, có thể gặp nhiều candidate và `NoUniqueBeanDefinitionException`. Tên, `@Qualifier`, `@Primary`, và vị trí bean trong hierarchy đều có thể ảnh hưởng cách chọn. Không áp dụng quy tắc “có child nên mọi bean type ở parent bị bỏ qua” một cách máy móc.

**Phạm vi** ở đây trước hết là *phạm vi đăng ký và tra cứu giữa các context*, không phải `singleton/prototype/request/session scope`. Một bean `singleton` chỉ mang tính singleton trong **bean factory/context đang sở hữu nó**; một parent singleton được child sử dụng vẫn thuộc parent.

## 3. `@ContextHierarchy` và `@ContextConfiguration` khai báo điều gì?

Trong Spring TestContext, `@ContextHierarchy` nhận một hoặc nhiều phần tử `@ContextConfiguration`. Mỗi phần tử mô tả **một cấp context**, theo thứ tự từ parent ở trước đến child ở sau:

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "parent",
        classes = ParentConfig.class),
    @ContextConfiguration(
        name = "child",
        classes = ChildConfig.class)
})
class HierarchyIntegrationTest {
    // Các test dùng ApplicationContext con được nạp.
}
```

Đây là **đoạn minh họa cấu hình**, giả định các class config đã tồn tại. Ý nghĩa:

1. TestContext load `ParentConfig` vào context cấp parent.
2. Load `ChildConfig` vào context cấp child, với parent trỏ tới context đã tạo ở bước 1.
3. `SpringExtension` tích hợp Spring TestContext với JUnit Jupiter, thực hiện dependency injection, lifecycle callbacks và hỗ trợ cache.
4. `@Autowired ApplicationContext` trong test thông thường nhận **context thấp nhất (child)** của hierarchy.
5. `name = "parent"/"child"` đặt **tên cấp hierarchy**, có ích khi một test subclass muốn merge/override đúng cấp; đó **không phải tên bean**.

Bạn có thể dùng `classes = ...` để cung cấp các class `@Configuration`, hoặc `locations = ...` cho XML config nếu hệ thống dùng XML. Một hierarchy có thể chứa các cấp dùng kiểu tài nguyên khác nhau; khi **merge cùng một cấp** qua kế thừa test class, loại tài nguyên ở cấp đó cần nhất quán.

**Đừng nhầm với:**

- `@ContextConfiguration(classes = {A.class, B.class})`: nhiều config class đóng góp vào **một** context (nếu không có hierarchy).
- `@Import(B.class)`: kéo thêm định nghĩa bean vào cấu hình hiện tại; không tạo context con.
- `@Nested` trong JUnit: lồng test class về mặt tổ chức test; không tự tạo cấp Spring context.
- `@Configuration` class kế thừa một class khác: kế thừa Java/config; không mặc nhiên tạo quan hệ `ApplicationContext.getParent()`.

## 4. Ví dụ hoàn chỉnh Java 17+: kiểm tra bean ở parent/child

Ví dụ bên dưới chỉ cần **một file test** trong một dự án Spring Boot có JUnit Jupiter, Spring TestContext và Spring Context. Nó không cần controller, server, database hay Docker. Mục tiêu là kiểm chứng chính xác cấu trúc context bằng mã chạy được, thay vì chỉ đọc mô tả.

### 4.1. Cấu hình dự án để chạy

Với dự án Spring Boot Gradle Groovy DSL **đã có Spring Boot plugin, repositories và dependency management phù hợp**, bảo đảm có starter và starter test:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Hoặc trong Maven, test dependency thuộc `pom.xml` của dự án:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Một Spring Boot application thực tế thường đã có starter production. Các snippet là **phần bổ sung dependency**, không phải build file hoàn chỉnh; đừng khai báo duplicate dependency. Chạy từ đúng module chứa test.

### 4.2. File test độc lập

Tạo file **`src/test/java/com/example/testing/context/ContextHierarchyTest.java`**:

```java
package com.example.testing.context;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.ContextHierarchy;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "parent",
        classes = ContextHierarchyTest.ParentConfig.class),
    @ContextConfiguration(
        name = "child",
        classes = ContextHierarchyTest.ChildConfig.class)
})
class ContextHierarchyTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    GreetingSettings settings;

    @Autowired
    GreetingService service;

    @Test
    void childCanUseParentBeanButParentCannotSeeChildBean() {
        ApplicationContext parent = context.getParent();
        assertNotNull(parent);

        assertEquals("Xin chào Linh", service.greet("Linh"));

        // Bean nằm tại parent nhưng được child phân giải.
        assertTrue(context.containsBean("greetingSettings"));
        assertFalse(context.containsLocalBean("greetingSettings"));
        assertTrue(parent.containsLocalBean("greetingSettings"));
        assertSame(parent.getBean(GreetingSettings.class), settings);

        // Bean được khai báo chỉ tại child.
        assertTrue(context.containsLocalBean("greetingService"));
        assertFalse(parent.containsBean("greetingService"));
    }

    @Test
    void childBeanWithSameNameShadowsParentBean() {
        ApplicationContext parent = context.getParent();
        assertNotNull(parent);

        assertEquals("CHILD", context.getBean("label", String.class));
        assertEquals("PARENT", parent.getBean("label", String.class));
        assertTrue(context.containsLocalBean("label"));
        assertTrue(parent.containsLocalBean("label"));
    }

    record GreetingSettings(String prefix) {}

    static final class GreetingService {
        private final GreetingSettings settings;

        GreetingService(GreetingSettings settings) {
            this.settings = settings;
        }

        String greet(String name) {
            return settings.prefix() + " " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ParentConfig {
        @Bean
        GreetingSettings greetingSettings() {
            return new GreetingSettings("Xin chào");
        }

        @Bean("label")
        String parentLabel() {
            return "PARENT";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ChildConfig {
        @Bean
        GreetingService greetingService(GreetingSettings settings) {
            return new GreetingService(settings);
        }

        @Bean("label")
        String childLabel() {
            return "CHILD";
        }
    }
}
```

**Kết quả mong đợi:** **2 phương thức `@Test` thành công** trên Spring Framework có hỗ trợ `@ContextHierarchy` và JUnit Jupiter. File không in gì ra stdout; số lượng test trong console/report tùy build tool. Một test khẳng định child dùng được bean cấu hình tại parent nhưng parent không nhìn thấy bean chỉ có ở child; test còn lại khẳng định shadowing theo **tên**.

Chạy trên Linux/macOS:

```bash
# Dự án Gradle
./gradlew test --tests "com.example.testing.context.ContextHierarchyTest"

# Hoặc dự án Maven dùng Surefire/JUnit Jupiter
./mvnw -Dtest=ContextHierarchyTest test
```

Chọn đúng lệnh theo loại dự án, không mặc định cả hai wrapper đều tồn tại. Trên Windows PowerShell có thể dùng `.\gradlew.bat test --tests "com.example.testing.context.ContextHierarchyTest"` hoặc `.\mvnw.cmd "-Dtest=ContextHierarchyTest" test`. Nếu Maven surefire plugin hoặc Gradle test task không nhận test, cần kiểm tra cấu hình JUnit Platform và source set/test selector trước khi kết luận hierarchy sai.

### 4.3. Giải thích đường đi trong bài test

- TestContext dựng **ParentConfig** thành một parent context chứa bean `greetingSettings` và bean tên `label` với giá trị `PARENT`.
- TestContext dựng **ChildConfig** thành một child context với bean `greetingService` và bean tên `label` với giá trị `CHILD`.
- Khi Spring tạo `greetingService(GreetingSettings settings)` tại child, kiểu `GreetingSettings` được tìm trong parent; constructor của `GreetingService` nhận bean đó.
- `@Autowired GreetingSettings settings` trên test nhận instance parent cung cấp. `assertSame` kiểm tra đây là **cùng instance**, vì bean mặc định là singleton trong parent.
- `context.containsBean("greetingSettings")` là `true`, nhưng `context.containsLocalBean("greetingSettings")` là `false`: child tra được bean qua parent, nhưng **không sở hữu bean definition đó**.
- `parent.containsBean("greetingService")` là `false`: không có đường tra ngược từ parent xuống child.
- Hai bean `label` ở **hai context khác nhau**, vì vậy truy vấn trên child trả `CHILD` còn truy vấn trên parent trả `PARENT`. Đây là shadowing trong quan hệ context, không phải trùng bean definition trong một factory.

Nếu ví dụ báo lỗi startup, hãy đọc nguyên nhân gốc. Một bean ở parent nhận dependency của bean chỉ có ở child sẽ không thể được tạo bằng cơ chế tra cứu thông thường; hãy đặt dependency dùng chung ở parent hoặc sửa hướng phụ thuộc của thiết kế.

## 5. Phạm vi cấu hình cha và con: nên đặt bean ở đâu?

Một cách phân chia phổ biến:

| Loại thành phần | Parent thường quản lý | Child thường quản lý |
|---|---|---|
| Dịch vụ nghiệp vụ dùng chung | Service, policy, repository, transaction infrastructure | Bean đặc thù endpoint/job/module |
| Hạ tầng kết nối | DataSource, HTTP client, message client chia sẻ nếu cần | Cấu hình riêng một servlet/module |
| Web MVC | Chỉ các thành phần dùng chung thích hợp | Controller, handler mappings, MVC adapters |
| Cấu hình thử nghiệm | Shared test fixture/config cho các child | Bean test đặc thù từng child |
| Trạng thái | Shared singleton thực sự có chủ đích | Bean cục bộ theo phạm vi riêng |

Đây là **quy tắc thiết kế gợi ý**, không phải luật Spring cứng cho mọi loại bean. Các component chỉ nên đặt ở parent nếu thực sự được nhiều child dùng chung và không cần phụ thuộc ngược vào bean của child.

### 5.1. Quan hệ phụ thuộc phải đi đúng chiều

**Hợp lý:** service được tạo tại child cần repository tại parent. Child có thể phân giải repository từ ancestor.

**Có vấn đề:** service được tạo tại parent cần controller chỉ có tại child. Parent không có đường biết về child trong quá trình resolve dependency; autowiring thường sẽ thất bại. Nếu parent cần callback hoặc interface, hãy đưa một contract dùng chung ở parent và thiết kế cơ chế đăng ký thích hợp; không đơn giản dời mọi bean xuống parent để che lỗi.

### 5.2. Dùng đúng scope khi kiểm tra

Một bean `singleton` do parent sở hữu có thể được nhiều child sử dụng cùng một instance; nếu có state mutable và test thay đổi state đó, các test dùng chung parent có thể ảnh hưởng nhau. Việc thêm context con **không tự cô lập state mutable của parent**.

Ở chiều ngược lại, nếu hai child tự khai báo cùng một bean kiểu `CacheService`, chúng thường có instance độc lập do thuộc hai factory khác nhau (với scope singleton mặc định). Tuy nhiên, nếu bên trong bean dùng static field, external DB/Redis hoặc singleton ngoài JVM, sự cô lập context **không bảo đảm** cô lập tài nguyên đó.

### 5.3. Parent/child khác với `BeanDefinition` inheritance

Spring XML có khái niệm “child bean definition kế thừa định nghĩa parent bean” qua thuộc tính XML `parent`. Đó là **kế thừa metadata của bean definition**, hoàn toàn khác với quan hệ **hai `ApplicationContext`** và `getParent()`. Khi đọc chữ “parent/child” trong tài liệu Spring, cần xác định đang nói đến đối tượng context, cấu hình class, hay bean definition.

## 6. Kế thừa hierarchy qua lớp test: merge và override đúng cấp

Spring TestContext cho phép khai báo một phần hierarchy ở **test superclass** rồi bổ sung/điều chỉnh ở **test subclass**. Kỹ thuật này khác với Java class inheritance về nghiệp vụ; nó chỉ mô tả cấu hình context mà Spring TestContext sẽ nạp cho lớp test cuối cùng.

### 6.1. Đặt tên mỗi cấp để merge chính xác

**Minh họa, giả sử các config class đã tồn tại; không phải chương trình độc lập:**

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "parent", classes = SharedConfig.class),
    @ContextConfiguration(
        name = "child", classes = WebConfig.class)
})
abstract class BaseWebIntegrationTest {
}

@ContextHierarchy(
    @ContextConfiguration(
        name = "child", classes = ExtraWebConfig.class)
)
class ExtendedWebIntegrationTest extends BaseWebIntegrationTest {
}
```

Ở subclass, Spring **merge config của cấp có tên `child`**. Kết quả về ý tưởng:

- Parent dùng `SharedConfig` giống base.
- Child được cấu hình từ `WebConfig` **và** `ExtraWebConfig`.
- Không tự sinh ra cấp thứ ba chỉ vì subclass cũng có `@ContextHierarchy`.
- Nếu `ExtraWebConfig` định nghĩa bean trùng tên với `WebConfig` trong **cùng child context**, cần xem lại chính sách overriding và cấu hình, thay vì tưởng đó là shadowing giữa hai cấp.

Tên cấp là một hợp đồng khi kế thừa. Nếu subclass đặt tên mới không trùng cấp mong muốn, Spring có thể hình thành một cấp khác; điều đó làm thay đổi dependency graph và tốc độ load context.

### 6.2. Ghi đè cấu hình ở đúng cấp bằng `inheritLocations = false`

Giả sử base có hierarchy parent/child như trên, nhưng test subclass cần thay **toàn bộ cấu hình child** bằng cấu hình thử nghiệm khác:

```java
@ContextHierarchy(
    @ContextConfiguration(
        name = "child",
        classes = AlternativeWebConfig.class,
        inheritLocations = false)
)
class AlternativeWebIntegrationTest extends BaseWebIntegrationTest {
}
```

Ý nghĩa: cấp `child` dùng `AlternativeWebConfig` thay vì kế thừa thêm `WebConfig` từ base; parent vẫn giữ `SharedConfig`. Giá trị mặc định `inheritLocations = true` khiến config cùng cấp được kết hợp trong điều kiện hợp lệ. Thuộc tính `inheritInitializers` điều khiển kế thừa initializers riêng và có quy tắc tương ứng; đừng đánh đồng hai thuộc tính.

**Điểm cần nhớ:** `inheritLocations = false` chỉ ảnh hưởng **kế thừa cấu hình của cấp được đặt tên** trong test class hierarchy, không có nghĩa “xóa parent ApplicationContext” và cũng không có nghĩa xóa bean đang tồn tại trong runtime app.

### 6.3. Implicit parent context qua superclass

Spring TestContext còn có tình huống một superclass chỉ khai báo `@ContextConfiguration` thông thường, sau đó subclass khai báo `@ContextHierarchy`. Trong ví dụ tài liệu chính thức, cấu hình của superclass có thể trở thành **parent context ngầm định** của các child context ở subclasses. Vì vậy cần đọc cả annotations trên superclass khi điều tra hierarchy; không chỉ xem annotation ở test class hiện tại.

Với code mới, nên **đặt tên rõ cấp `parent` và `child`** khi có nhu cầu mở rộng qua inheritance. Điều này giảm nhầm lẫn giữa “gộp cấu hình vào một context” và “thêm cấp vào hierarchy”.

## 7. Spring MVC: root và DispatcherServlet context

Kiến trúc Spring MVC truyền thống có thể có:

- **Root `WebApplicationContext`:** service, repository và hạ tầng dùng chung, thường được tạo bởi `ContextLoaderListener`.
- **Child `WebApplicationContext`:** controller, handler mapping và cấu hình riêng của `DispatcherServlet`.

Trong bài test tích hợp mô phỏng kiểu kiến trúc này, có thể dùng `@WebAppConfiguration` kết hợp `@ContextHierarchy`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(
        name = "root", classes = SharedWebRootConfig.class),
    @ContextConfiguration(
        name = "dispatcher", classes = MvcDispatcherConfig.class)
})
class MvcHierarchyIntegrationTest {

    @Autowired
    WebApplicationContext webContext;

    // Có thể cấu hình MockMvc dựa trên child WebApplicationContext.
}
```

Đây là **snippet minh họa**: cần các config class, import Spring Test/MVC và controller của dự án mới chạy được. Trong môi trường `@WebAppConfiguration` phù hợp, `webContext` được inject là **child/lowest WebApplicationContext**, nên có thể nhìn thấy controller của child và service từ root.

**Phân biệt Spring Boot:** một Boot web application thường dùng một context do auto-configuration tạo; nó **không bắt buộc** tái hiện kiến trúc hai context root/dispatcher truyền thống. Không thêm `@ContextHierarchy` vào mọi `@SpringBootTest` hay `@WebMvcTest` chỉ vì đó là web test. Nếu đang dùng MockMvc trong Boot, cơ chế `@AutoConfigureMockMvc` có thể đủ cho mục tiêu kiểm chứng HTTP.

Khi ứng dụng thật có nhiều DispatcherServlet hoặc context phân cấp được khai báo rõ, test hierarchy có thể phản ánh kiến trúc đó. Hãy dùng tên cấp sát nghĩa (ví dụ `root`, `apiServlet`) và đảm bảo mỗi config class được nạp vào **đúng cấp**.

## 8. Spring TestContext cache khi dùng hierarchy

Spring TestContext Framework **cache các `ApplicationContext` đã nạp** trong cùng tiến trình thử nghiệm, để các lớp test có cấu hình tương đương không phải dựng lại mọi bean. Với hierarchy, các cấp cấu hình có thể được cache và tái sử dụng riêng theo khóa phù hợp.

Ví dụ hai nhóm test:

```text
Context hierarchy cho Test A: SharedConfig -> RestConfig
Context hierarchy cho Test B: SharedConfig -> SoapConfig

Nếu khóa cache của parent tương thích:
    cùng parent SharedConfig có thể được tái sử dụng;
    RestConfig và SoapConfig tạo các child khác nhau.
```

Đây là **mô hình cache có điều kiện**, không hứa mọi test cùng tên config class chắc chắn dùng chung cùng object: cache key còn bị ảnh hưởng bởi loader, initializers, active profiles, property sources, context customizers, parent configuration và các yếu tố liên quan. Context cache có giới hạn dung lượng và có thể bị evict.

### 8.1. Lợi ích và rủi ro khi tái sử dụng parent

Lợi ích: tiết kiệm startup cho bean hạ tầng đắt tiền, giảm thời gian CI khi nhiều child cùng dùng parent.

Rủi ro: nếu test thay đổi state mutable của một singleton trong parent, các test sau có thể chịu ảnh hưởng. `@ContextHierarchy` và cache không phải cơ chế “reset dữ liệu”. Đối với database/Redis/queue, cần fixture và cleanup đúng phạm vi; một context mới không bảo đảm DB không còn dữ liệu.

**Cách làm tốt:** giữ context config bất biến, dữ liệu test độc lập, tránh sửa static field hoặc singleton dùng chung. Chỉ đánh dấu context dirty khi test thực sự làm hỏng context state theo nghĩa không thể tái sử dụng an toàn.

### 8.2. `@DirtiesContext` với `hierarchyMode`

Spring cung cấp `@DirtiesContext` để đánh dấu một context không thể tái sử dụng; framework loại context liên quan khỏi cache và đóng chúng theo chế độ phù hợp.

Khi đã khai báo hierarchy, có hai thuật toán quan trọng:

| Chế độ | Tác động lên cache | Khi nào cân nhắc |
|---|---|---|
| `EXHAUSTIVE` (mặc định cho hierarchy) | Loại cả các subhierarchy có chung tổ tiên thích hợp với context hiện tại; phạm vi có thể rộng | Parent/shared infrastructure bị thay đổi, cần đảm bảo toàn bộ nhánh liên quan sạch |
| `CURRENT_LEVEL` | Loại context ở **cấp thấp nhất nhìn thấy từ test hiện tại** và các context trong subhierarchy của cấp đó; giữ các ancestor không bị ảnh hưởng | Test chỉ làm hỏng state riêng của child, muốn giữ parent sạch để tái sử dụng |

**Minh họa** trên một test đã khai báo hierarchy như phần 4:

```java
@Test
@DirtiesContext(
    hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL
)
void mutatesChildOnlyState() {
    // Tác vụ thực sự làm dirty state ở child.
}
```

Đây là **snippet minh họa**, không phải test chạy độc lập. Ở chế độ `CURRENT_LEVEL`, “current level” là cấp thấp nhất mà lớp test đang thấy; nếu test inject child, thường là child đó. Nếu context có descendant dưới cấp hiện tại, các descendant liên quan cũng bị loại. Chế độ `EXHAUSTIVE` có thể ảnh hưởng các hierarchy khác chia sẻ tổ tiên, nên có chi phí lớn hơn.

**Không thêm `@DirtiesContext` vô điều kiện vào mọi test** để “đảm bảo độc lập”. Điều đó khiến context tải lại liên tục, che giấu fixture kém và làm bộ test chậm. Chỉ chọn `hierarchyMode = CURRENT_LEVEL` khi có bằng chứng state dirty nằm ở child; nếu parent thực sự bị thay đổi, giữ parent trong cache có thể khiến test khác sai.

## 9. Bean override và mock phải trúng đúng cấp

Trong một bài Spring TestContext, bạn có thể muốn thay một dependency bằng fake/mock để cô lập lỗi. Với hierarchy, phải biết **bean thật nằm ở cấp nào** và **override áp dụng vào cấp nào**.

### 9.1. Các phiên bản hỗ trợ `contextName`

Trong **Spring Framework 6.2+**, cơ chế bean overriding cho test cung cấp các annotation như `@MockitoBean`, `@MockitoSpyBean` và `@TestBean`. Với hierarchy, có thể chỉ định `contextName` trùng với `name` trên `@ContextConfiguration` để giới hạn override vào một cấp:

```java
@ContextHierarchy({
    @ContextConfiguration(
        name = "parent", classes = SharedConfig.class),
    @ContextConfiguration(
        name = "child", classes = FeatureConfig.class)
})
class FeatureIntegrationTest {

    @MockitoBean(contextName = "child")
    FeatureGateway featureGateway;
}
```

**Đây chỉ là snippet minh họa**, không phải test độc lập: cần test extension, config class, field type và Spring Framework phiên bản hỗ trợ. Nó mô tả ý định thay bean `FeatureGateway` ở cấp `child`.

Trong các dự án Spring Boot **3.3.x dùng Spring Framework 6.1.x**, `@MockitoBean` chưa có; trước đây Boot cung cấp `@MockBean`/`@SpyBean` riêng (Boot bắt đầu deprecate các annotation đó từ 3.4). Không sao chép `@MockitoBean(contextName=...)` vào project cũ rồi kết luận Mockito không mock được. Hãy đọc đúng tài liệu version đang dùng.

### 9.2. Vì sao cần cấp cụ thể?

Nếu một kiểu bean có cả ở parent và child, hoặc bạn muốn override bean được định nghĩa ở một cấp duy nhất, cấu hình mock không rõ scope có thể thay sai bean hoặc ảnh hưởng nhiều cấp. Với `@MockitoBean/@MockitoSpyBean` ở Spring Framework mới, một override không giới hạn `contextName` có thể được xem xét ở các cấp hierarchy; chỉ rõ tên giúp tránh ý nghĩa quá rộng.

Cần phân biệt:

- `@Mock` của Mockito tạo mock trong lớp test; **không tự thay bean trong Spring context**.
- `@MockitoBean`/`@MockBean` là cơ chế override bean trong test context theo framework/version.
- Stub của mock parent có thể ảnh hưởng **mọi child đang dùng parent đó**, nếu test context/cache tái sử dụng parent; vì vậy phải quản lý reset/stubbing và tránh rò state.
- Bean cục bộ ở child có thể che bean parent cùng tên; nếu mock ở parent nhưng child có bean cùng tên, đường tra cứu qua child có thể không đi tới mock parent.

Không dùng “mock được” làm bằng chứng cấu hình đúng: phải assert đúng bean đang được inject vào SUT và đúng level đang chịu tác động.

## 10. Profile, property và phạm vi cấu hình

Các annotation/nguồn cấu hình như `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource` và `@Configuration` ảnh hưởng cách nạp context. Trong hierarchy, **không nên suy ra property/profile từ tên cấp**. Tên `parent` và `child` trong `@ContextConfiguration` chỉ hỗ trợ định danh hierarchy level; chúng không tạo profile tương ứng.

### 10.1. Câu hỏi cần kiểm chứng

1. Bean config class nào được load vào parent và child?
2. Bean có `@Profile("test")` có được đăng ký ở context mong muốn khi test active profile không?
3. Property source và precedence nào thật sự có tác dụng ở từng context? Có parent environment được merge vào child không?
4. Test class có kế thừa `@ActiveProfiles` hoặc `@TestPropertySource` từ superclass không?
5. Một context đã nằm trong cache với cấu hình/properties khác thì test hiện tại có nhận context đó hay phải dựng mới?

**Ví dụ giả định:** parent khai báo `DataSource` còn child khai báo controller. Nếu child cần URL DB khác cho test nhưng parent đã tạo `DataSource` dựa trên property khác, chỉ thay property trong child sau khi parent được khởi tạo **không làm bean parent tự xây lại**. Hãy cung cấp cấu hình/override vào đúng thời điểm và đúng cấp sở hữu bean.

### 10.2. Giảm lệch giữa local IDE và CI

Một test hierarchy có thể pass trong IDE nhưng fail trên CI nếu profile, biến môi trường, JDK, config resource path, database hoặc mock override khác. Đối chiếu:

- Cùng tập config class/location và cùng annotation trên test superclass.
- Cùng active profiles, test properties và dependency version.
- Cùng JVM/test runner; cùng context loader có khả năng nạp hierarchy.
- Cùng chính sách cache, parallel execution và fixture state.

Để debug, có thể ghi log tên bean và parent context trong môi trường test, tránh ghi secrets. Dùng `context.getParent()`, `containsLocalBean` và `containsBean` để thu hẹp **đúng level chứa bean**, thay vì đoán từ stacktrace dài.

## 11. Các lỗi thường gặp và cách truy nguyên

| Hiện tượng | Nguyên nhân khả dĩ | Hướng khắc phục |
|---|---|---|
| Test lấy `context.getParent() == null` | Chỉ load một context; hierarchy không được khai báo/nhận đúng | Kiểm tra `@ContextHierarchy`, extension và test bootstrapper |
| `NoSuchBeanDefinitionException` khi tạo bean ở parent | Parent phụ thuộc vào bean chỉ có ở child | Di chuyển dependency chung lên parent hoặc sửa chiều phụ thuộc |
| Child không thấy bean parent | Parent không nạp config mong muốn, profile chưa kích hoạt hoặc bean bị shadow | Kiểm tra config thực nạp và local bean names |
| Cùng tên bean trả kết quả khác giữa hai level | Shadowing theo tên, hoàn toàn có thể là chủ đích | Tra trực tiếp parent và child; assert đúng hợp đồng |
| `NoUniqueBeanDefinitionException` ở child | Có nhiều bean cùng type với các tên khác nhau và không có quy tắc chọn rõ | Dùng `@Qualifier`/`@Primary` hoặc chỉnh cấu hình |
| Lỗi bean overriding khi gộp config | Hai bean definition cùng tên nằm trong **một context** | Đổi tên/định nghĩa hoặc sửa cách merge level; không nhầm với shadowing |
| Subclass có ba context thay vì hai | `@ContextHierarchy` bổ sung level khác tên hoặc inheritance không như dự định | Đặt `name` nhất quán, đọc annotations của superclass |
| Child vẫn có bean config cũ sau test subclass | Mặc định `inheritLocations = true` merge config cùng named level | Dùng `inheritLocations = false` khi thực sự muốn thay config của level |
| Cache rất chậm hoặc parent luôn load lại | `@DirtiesContext` quá rộng, đổi profile/properties/customizers gây cache miss | Xem lại cache key, phạm vi dirty, state dùng chung |
| Test mock sai cấp của hierarchy | Override áp dụng nhiều level hoặc bị local bean shadow | Dùng cơ chế override có scope theo version; assert bean thực được inject |
| Test context MVC thiếu servlet infrastructure | Thiếu `@WebAppConfiguration` hoặc web context config không phù hợp | Dùng đúng web test setup và config root/dispatcher |
| Spring Boot `@SpringBootTest` không tạo root/child như mong muốn | Boot không tự tạo hierarchy chỉ vì có web starter | Chỉ sử dụng hierarchy khi app/runtime cần, thiết lập test chính xác |

### 11.1. Chẩn đoán theo trình tự có thể tái lập

Nếu test `@ContextHierarchy` fail:

1. **Xác định lỗi xảy ra khi nào:** compile test, nạp config class, refresh bean factory, dependency injection, hay assertion.
2. **Đọc root cause đầu tiên có ý nghĩa:** `BeanCreationException` thường là wrapper; cần tìm lỗi gốc về bean definition, profile, property hoặc ambiguity.
3. **Xác minh số cấp:** `@Autowired ApplicationContext`, kiểm tra `getParent()` và tiếp tục lên ancestor; không mặc định luôn có đúng hai cấp.
4. **Xác minh sở hữu bean:** dùng `containsLocalBean` ở từng cấp và so với `containsBean`.
5. **Xác minh config inheritance:** đọc `@ContextHierarchy` trên superclass và subclass, so sánh `name`, `inheritLocations`, `classes/locations`.
6. **Chỉ khi cần mới xem cache:** context có bị dirty, test thay singleton state hay tạo nhiều biến thể cấu hình không?
7. **Chạy lại bằng build wrapper:** chắc chắn cùng module, profile và những property cần thiết với CI.

Đừng sửa lỗi bằng cách bật bean overriding toàn cục hoặc thêm `@DirtiesContext` vào mọi test. Hai cách đó có thể làm test chạy qua tạm thời nhưng che vấn đề phân cấp hoặc sự chia sẻ trạng thái.

## 12. Những hiểu lầm cần phân biệt

**“Child thấy bean parent nên bean đó đã thuộc child.”** Sai. Child có thể resolve bean từ parent; `containsLocalBean` giúp xác nhận nơi đăng ký thật.

**“Parent có thể @Autowired controller ở child.”** Thông thường sai. Parent được tạo trước, không có cơ chế lookup ngược xuống child qua bean factory.

**“Hai child cùng parent tự thấy bean của nhau.”** Sai. Chúng chỉ chia sẻ thứ ancestor cung cấp.

**“Hai bean cùng tên ở parent và child chắc chắn gây lỗi duplicate.”** Sai nếu chúng thuộc hai context khác nhau; lỗi duplicate trong cùng bean factory là vấn đề khác.

**“Java extends một test base đồng nghĩa đã có context hierarchy.”** Sai. Phải đọc cách `@ContextConfiguration`/`@ContextHierarchy` được khai báo và kế thừa.

**“Tên level `child` là tên bean.”** Sai. Level name cho TestContext merge/override; bean name do `@Bean` và cơ chế đặt tên bean quyết định.

**“@DirtiesContext chỉ xóa một bean bị thay đổi.”** Sai. Framework đánh dấu context và xử lý **context cache**, không xóa một bean đơn lẻ.

**“@DirtiesContext(CURRENT_LEVEL) luôn làm sạch mọi dữ liệu.”** Sai. Nó bỏ context tại level hiện hành và các descendant thích hợp khỏi cache; database, file, message queue bên ngoài hoặc parent singleton vẫn có thể giữ state.

**“@SpringBootTest tự xây root + DispatcherServlet child.”** Không mặc định. Hierarchy có cấu trúc cụ thể; Boot test đơn context vẫn phổ biến.

## 13. Bài tập để tự kiểm chứng

### Bài tập A — Tại sao kết quả tra cứu khác nhau?

Cho parent có `@Bean("paymentMode")` trả `"NORMAL"`, child khai báo bean cùng tên trả `"SANDBOX"`. Hãy dự đoán:

- `child.getBean("paymentMode")`;
- `parent.getBean("paymentMode")`;
- `child.containsLocalBean("paymentMode")`;
- `parent.containsLocalBean("paymentMode")`.

**Đáp án:** lần lượt là `"SANDBOX"`, `"NORMAL"`, `true` và `true`. Hai bean nằm ở **hai context khác nhau** nên không tự thay thế nhau.

### Bài tập B — Kiểm tra bean ở cấp nào

Cho child dùng được `sharedRepository` nhưng test cần chứng minh bean thực nằm tại parent. Hãy viết hai assertion:

```java
assertTrue(child.containsBean("sharedRepository"));
assertFalse(child.containsLocalBean("sharedRepository"));
```

Đoạn này **giả định** đối tượng `child` là `ApplicationContext` hợp lệ và test có import `assertTrue/assertFalse` của JUnit. Nếu muốn chứng minh chặt hơn, thêm `assertTrue(child.getParent().containsLocalBean("sharedRepository"))` sau khi xác nhận parent không null.

### Bài tập C — Merge hay override?

Base test khai báo:

```java
@ContextHierarchy({
    @ContextConfiguration(name = "parent", classes = SharedConfig.class),
    @ContextConfiguration(name = "child", classes = WebConfig.class)
})
abstract class BaseTest {
}
```

Hai khai báo subclass **khác nhau**:

```java
// Merge thêm vào cấp child:
@ContextHierarchy(
    @ContextConfiguration(
        name = "child",
        classes = ExtraWebConfig.class))
class MergeTest extends BaseTest {
}

// Thay cấu hình cấp child:
@ContextHierarchy(
    @ContextConfiguration(
        name = "child",
        classes = AlternativeWebConfig.class,
        inheritLocations = false))
class ReplaceTest extends BaseTest {
}
```

Đây là **snippets để đọc ngữ nghĩa**, không phải ví dụ chạy độc lập. Hãy tự trả lời: cả hai subclass có giữ parent không, có phát sinh cấp thứ ba không, và config cũ của child có còn không?

**Đáp án:** cả hai giữ parent `SharedConfig` và cùng mục tiêu cấp được đặt tên `child`. `MergeTest` giữ `WebConfig` rồi bổ sung `ExtraWebConfig`; `ReplaceTest` dùng `AlternativeWebConfig` thay cấu hình child kế thừa. Không phát sinh cấp thứ ba khi dùng cùng tên cấp.

### Bài tập D — Chọn dirty mode

Hai test hierarchy cùng dùng một parent context và các child khác nhau. Một test sửa **duy nhất** state mutable trong child, parent không đổi. Cân nhắc `@DirtiesContext(hierarchyMode = CURRENT_LEVEL)` để bỏ context đang dirty và giữ ancestor. Nếu test sửa singleton parent, việc giữ parent trong cache là nguy cơ; cần lựa chọn cách cô lập/cleanup phù hợp hoặc dirty ở phạm vi rộng hơn.

### Checklist trước khi hoàn tất một hierarchy test

- [ ] Nắm rõ ứng dụng thực có cần nhiều `ApplicationContext` hay chỉ một context.
- [ ] Mỗi cấp được mô tả bằng đúng `@ContextConfiguration`, thứ tự parent → child.
- [ ] Khi subclass cần merge/override, `name` nhất quán giữa các cấp.
- [ ] Hiểu `inheritLocations` và không nhầm merge với tạo level mới.
- [ ] Bean dùng chung được sở hữu ở ancestor thích hợp, child không ép parent phụ thuộc ngược.
- [ ] Phân biệt `containsBean`, `containsLocalBean` và `getParent()`.
- [ ] Xử lý trùng tên (shadowing) và trùng kiểu (ambiguity) theo hợp đồng.
- [ ] Context cache và phạm vi `@DirtiesContext` không khiến test khác mất độc lập.
- [ ] Bean override/mock áp dụng vào đúng level và đúng version Spring.
- [ ] Profile, property, config resource và build tool trên IDE/CI đã được đối chiếu.
- [ ] Ví dụ/thử nghiệm kiểm tra behavior thật, không chỉ `assertNotNull(context)`.
- [ ] Chạy được test đơn lẻ và full suite; phát hiện đúng lỗi cấu hình theo context level.

## 14. Ghi nhớ để áp dụng đúng

Trong Spring TestContext, `@ContextHierarchy` là công cụ tạo **nhiều context có quan hệ parent/child thật**. Bean parent có thể được child tra cứu, child bean không chảy ngược lên parent, và bean cục bộ cùng tên tại child có thể che bean parent mà không xóa bean parent. Trong test class hierarchy, **tên cấp + quy tắc kế thừa** quyết định merge hay override cấu hình. Cache và `@DirtiesContext` có thể ảnh hưởng nhiều context, nên cần chọn phạm vi đúng với state thực sự bị thay đổi.

Giá trị học tập quan trọng nhất không phải thuộc lòng annotation, mà là biết **bean nào thuộc cấp nào, ai có thể nhìn thấy ai, context nào đang được inject và context nào đang được cache/dirtied**. Khi trả lời được bốn câu hỏi đó bằng assertion cụ thể, bạn có thể thiết kế và debug các test phân cấp một cách đáng tin.

## Tài liệu tham khảo chính thức

- [Spring Framework — Context Hierarchies (TestContext)](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/hierarchies.html): cú pháp, kiến trúc parent/child, merge và override named hierarchy levels.
- [Spring Framework — @ContextHierarchy](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-contexthierarchy.html): định nghĩa annotation và ví dụ Java/Kotlin.
- [Spring Framework — Context Configuration Inheritance](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/inheritance.html): `inheritLocations` và `inheritInitializers`.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): dirty context cache và `hierarchyMode`.
- [Spring Framework Javadoc — DirtiesContext.HierarchyMode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/annotation/DirtiesContext.HierarchyMode.html): phạm vi chính xác của `EXHAUSTIVE` và `CURRENT_LEVEL`.
- [Spring Framework — Bean Overrides in Context Hierarchies](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/hierarchies.html#testcontext-ctx-management-ctx-hierarchies-bean-overrides): `contextName` của `@MockitoBean`/`@MockitoSpyBean` trên framework hỗ trợ.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): TestContext integration và khả năng kiểm thử Boot.
