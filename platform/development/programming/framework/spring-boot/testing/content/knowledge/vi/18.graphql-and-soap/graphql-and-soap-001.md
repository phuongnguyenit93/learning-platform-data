# @GraphQlTest và phạm vi resolver, controller được kiểm thử

## 1. @GraphQlTest dùng để làm gì?

Trong Spring Boot, GraphQL API không trực tiếp ánh xạ mỗi method của controller thành một REST URL. Một GraphQL document được phân tích theo **schema**, được kiểm tra kiểu và variables, rồi GraphQL execution gọi các **data fetcher/resolver** tương ứng: @QueryMapping cho root query, @MutationMapping cho mutation, @SchemaMapping cho nested fields và các mapping liên quan. Một unit test gọi controller.bookById("b1") trực tiếp không chứng minh được rằng GraphQL operation thực sự gọi đúng resolver, hay schema, field, argument và nullability đã được cấu hình đúng.

**@GraphQlTest** là test slice của Spring Boot dành cho Spring GraphQL. Nó cấu hình hạ tầng GraphQL và các controller được chọn, cho phép gửi operation bằng **GraphQlTester** mà **không khởi động HTTP server hay WebSocket transport**. Nó giúp test mapping/schema nhanh hơn @SpringBootTest đầy đủ, đồng thời thực thi nhiều phần của GraphQL engine hơn một unit test Java thuần.

**Mục tiêu sau bài học:** bạn phân biệt được test slice và full HTTP integration; hiểu controller nào được chọn; cung cấp @MockBean cho collaborator nằm ngoài slice; kiểm tra @QueryMapping, @SchemaMapping, @Argument, selection set, nullable field và errors; dùng GraphQlTester.document/documentName/variable/execute/path; và quyết định khi nào cần chuyển sang HttpGraphQlTester với RANDOM_PORT.

**Phiên bản mẫu:** Java 17, Spring Boot **3.3.5**, Spring for GraphQL/GraphQL Java do Spring Boot BOM quản lý, Gradle, JUnit Jupiter, Mockito. Ở phiên bản 3.3, @GraphQlTest nằm trong **org.springframework.boot.test.autoconfigure.graphql**, @MockBean nằm trong **org.springframework.boot.test.mock.mockito**. Ở các phiên bản mới hơn, đặc biệt từ Spring Boot 3.4, cơ chế mock được chuyển hướng sang @MockitoBean; không trộn package của các phiên bản trong project này.

**Ngữ cảnh cha “GraphQL và SOAP”:** @GraphQlTest là công cụ dành cho GraphQL; nó **không** tự kiểm tra SOAP @Endpoint, WSDL hoặc SOAP XML envelope. Đó là phạm vi của Spring Web Services/SOAP testing khác.

## 2. Phạm vi controller và các bean được nạp

| Thành phần | Mặc định trong @GraphQlTest? | Ý nghĩa |
|---|---|---|
| GraphQL schema, GraphQlSource, execution infrastructure | Có, theo test auto-configuration | Có thể thực thi GraphQL document |
| GraphQlTester khi có spring-graphql-test | Có | Gửi operation không qua HTTP |
| @Controller GraphQL được chọn | Có | @QueryMapping/@SchemaMapping đăng ký resolver |
| Controller khác nếu chỉ chọn một class | Không | Slice có thể tập trung vào một controller |
| RuntimeWiringConfigurer, converters, JsonComponent, Instrumentation, DataFetcherExceptionResolver, GraphQlSourceBuilderCustomizer | Được filter của Boot 3.3 cho phép | Cấu hình/wiring GraphQL phù hợp |
| **@Service, @Repository** thông thường | **Không được quét tự động** | Cần mock hoặc import bean |
| @ConfigurationProperties thông thường | Không tự quét | Có thể cần @EnableConfigurationProperties |
| HTTP server, servlet filters, cookies, auth transport | **Không** | Không chứng minh /graphql có thể kết nối mạng |
| Database/external systems | Không mặc định | Không phải persistence/E2E test |

Khai báo chỉ định rõ phạm vi:

~~~java
@GraphQlTest(BookGraphQlController.class)
class BookGraphQlControllerSliceTest {
    // Controller Book thật, collaborator theo fixture của test.
}
~~~

Nếu viết **@GraphQlTest** không có class selector, slice quét các controllers GraphQL thuộc bộ lọc mặc định. Việc chỉ định một controller giúp tránh tải controller khác với dependencies không liên quan. Nhưng nó **không tự cắt bỏ fields khác khỏi schema.graphqls**: schema và danh sách resolver beans là hai khái niệm riêng. Một field có trong SDL không chứng minh @Controller tương ứng đã xuất hiện.

**@GraphQlTest không thay thế @WebMvcTest.** Cả hai là slice tests, nhưng @WebMvcTest kiểm tra Spring MVC request mapping bằng MockMvc, còn @GraphQlTest kiểm tra GraphQL schema và data fetchers bằng GraphQlTester. Một GraphQL @Controller có thể chứa @QueryMapping chứ không chứa @GetMapping hoặc @PostMapping trên từng field.

## 3. Cơ chế schema, resolver và selection set

Schema mẫu:

~~~graphql
type Query {
  bookById(id: ID!): Book
  systemStatus: String!
}

type Book {
  id: ID!
  title: String!
  stock: Int!
  stockLabel: String!
}
~~~

- **Query.bookById** cần một argument **id: ID!**. Nếu thiếu hoặc null, GraphQL engine có thể trả lỗi trước khi resolver chạy.
- Return **Book** không có dấu ! nên nullable: không tìm thấy Book có thể trả null mà không phải HTTP 404.
- Field **stockLabel: String!** yêu cầu một String nếu được chọn trên Book tồn tại.
- **systemStatus** được một controller thứ hai phụ trách, tiện để test phạm vi controller được chọn.
- Những trường id/title/stock có Java getters; stockLabel cần @SchemaMapping.

Ví dụ resolver:

~~~java
@Controller
class BookGraphQlController {

    @QueryMapping
    Book bookById(@Argument("id") String id) {
        return catalog.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "stockLabel")
    String stockLabel(Book book) {
        return catalog.labelForStock(book.getStock());
    }
}
~~~

Đây là snippet ý tưởng; file đầy đủ phía dưới có field và constructor. @QueryMapping mặc định ánh xạ Query.bookById theo method name, @SchemaMapping(typeName="Book",field="stockLabel") xử lý nested field và nhận **Book source object**.

**Selection set quyết định handler nào chạy.** Với document:

~~~graphql
{
  bookById(id: "b1") {
    id
    title
  }
}
~~~

GraphQL cần root resolver và các field id/title, **không cần gọi stockLabel**. Test đúng phải có assertion trên kết quả và **verify(catalog, never()).labelForStock(anyInt())**. Khi bổ sung stockLabel vào query, nested resolver mới được gọi. Đây là cơ sở để hiểu lazy field fetching và rủi ro N+1; nó không đồng nghĩa slice đã kiểm tra được số truy vấn SQL thật khi service bị mock.

**GraphQL errors khác HTTP error:** parse/validation/coercion failure và data fetching failure có thể xuất hiện trong mảng GraphQL response **errors**. Trong @GraphQlTest không có HTTP request nên không assert được HTTP status. Với GraphQL over HTTP, errors ở body không tự đồng nghĩa HTTP 404/500; status cụ thể phụ thuộc trường hợp và transport contract. Luôn kiểm tra đúng tầng.

## 4. Dự án thực hành hoàn chỉnh Spring Boot 3.3.5

Ví dụ:
- Book b1: title **Spring GraphQL Patterns**, stock=5, stockLabel **IN_STOCK**.
- Book b2: title **Testing GraphQL**, stock=0, stockLabel **OUT_OF_STOCK**.
- Book không tồn tại: bookById trả null.
- SystemStatusGraphQlController trả **READY** cho Query.systemStatus.
- Service thực dùng Map.of bất biến; slice tests mock service, HTTP tests dùng service thật.

### 4.1. Cấu trúc

~~~text
settings.gradle
build.gradle
src/main/resources/graphql/schema.graphqls
src/main/java/demo/graphql/GraphQlApplication.java
src/main/java/demo/graphql/Book.java
src/main/java/demo/graphql/BookCatalogService.java
src/main/java/demo/graphql/BookGraphQlController.java
src/main/java/demo/graphql/SystemStatusGraphQlController.java
src/test/resources/graphql-test/bookById.graphql
src/test/java/demo/graphql/BookGraphQlControllerSliceTest.java
src/test/java/demo/graphql/SystemStatusGraphQlSliceTest.java
src/test/java/demo/graphql/GraphQlFullHttpTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'graphql-test-scope-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Các dependencies có chủ đích:** starter-graphql nạp Spring for GraphQL và GraphQL Java; starter-web cung cấp Spring MVC/embedded Tomcat để full HTTP test kết nối /graphql. spring-graphql-test chứa GraphQlTester. starter-webflux trong testImplementation cung cấp WebTestClient client support cho HttpGraphQlTester khi production web server vẫn là MVC theo ưu tiên mặc định của Spring Boot. starter-test cung cấp JUnit Jupiter, Mockito, AssertJ. Dependency versions do BOM quản lý, tránh tự chọn các phiên bản Spring GraphQL không tương thích.

### 4.2. Schema và query fixture

**src/main/resources/graphql/schema.graphqls**

~~~graphql
type Query {
  bookById(id: ID!): Book
  systemStatus: String!
}

type Book {
  id: ID!
  title: String!
  stock: Int!
  stockLabel: String!
}
~~~

**src/test/resources/graphql-test/bookById.graphql**

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
    stock
    stockLabel
  }
}
~~~

Spring Boot tìm *.graphqls/*.gqls dưới **src/main/resources/graphql/** theo mặc định. GraphQlTester.documentName("bookById") lại tìm operation fixture dưới **classpath:graphql-test/**. Hai vị trí này khác nhau; không đưa schema vào graphql-test rồi kỳ vọng ứng dụng load, cũng không đưa query fixture vào graphql/ rồi kỳ vọng documentName tự tìm.

### 4.3. Application, model và service

**src/main/java/demo/graphql/GraphQlApplication.java**

~~~java
package demo.graphql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlApplication {

    public static void main(String[] args) {
        SpringApplication.run(GraphQlApplication.class, args);
    }
}
~~~

**src/main/java/demo/graphql/Book.java**

~~~java
package demo.graphql;

public final class Book {

    private final String id;
    private final String title;
    private final int stock;

    public Book(String id, String title, int stock) {
        this.id = id;
        this.title = title;
        this.stock = stock;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public int getStock() {
        return stock;
    }
}
~~~

Book có getters cho GraphQL Java default property fetching của id/title/stock. Không có getter stockLabel nên field đó chỉ được cung cấp bởi @SchemaMapping. Các fields Java final giúp fixture bất biến.

**src/main/java/demo/graphql/BookCatalogService.java**

~~~java
package demo.graphql;

import java.util.Map;

import org.springframework.stereotype.Service;

@Service
public class BookCatalogService {

    private final Map<String, Book> books = Map.of(
            "b1", new Book("b1", "Spring GraphQL Patterns", 5),
            "b2", new Book("b2", "Testing GraphQL", 0)
    );

    public Book findById(String id) {
        return books.get(id);
    }

    public String labelForStock(int stock) {
        return stock > 0 ? "IN_STOCK" : "OUT_OF_STOCK";
    }
}
~~~

Đây là service thật trong full context. Nó không có database hoặc mutable shared state. Trong @GraphQlTest, @Service **không được scan mặc định**, nên phải có @MockBean để controller nhận dependency.

### 4.4. Hai controllers

**src/main/java/demo/graphql/BookGraphQlController.java**

~~~java
package demo.graphql;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {

    private final BookCatalogService catalog;

    public BookGraphQlController(BookCatalogService catalog) {
        this.catalog = catalog;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return catalog.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "stockLabel")
    public String stockLabel(Book book) {
        return catalog.labelForStock(book.getStock());
    }
}
~~~

**src/main/java/demo/graphql/SystemStatusGraphQlController.java**

~~~java
package demo.graphql;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class SystemStatusGraphQlController {

    @QueryMapping
    public String systemStatus() {
        return "READY";
    }
}
~~~

Đây là các @Controller cho GraphQL engine, không phải REST controllers. Root Book resolver nhận GraphQL argument id; nested resolver nhận parent Book. Controller Status không inject service nào, giúp chứng minh một slice riêng không cần mock BookCatalogService.

## 5. BookGraphQlControllerSliceTest — 7 phương thức @Test

**src/test/java/demo/graphql/BookGraphQlControllerSliceTest.java**

~~~java
package demo.graphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@GraphQlTest(BookGraphQlController.class)
class BookGraphQlControllerSliceTest {

    @Autowired
    GraphQlTester tester;

    @Autowired
    ApplicationContext context;

    @MockBean
    BookCatalogService catalog;

    @Test
    void loadsSelectedControllerAndMock() {
        assertThat(context.getBeansOfType(
                BookGraphQlController.class)).hasSize(1);
        assertThat(context.getBeansOfType(
                SystemStatusGraphQlController.class)).isEmpty();
        assertThat(mockingDetails(catalog).isMock()).isTrue();
    }

    @Test
    void resolvesRootAndNestedFieldUsingQueryDocument() {
        when(catalog.findById("b1"))
                .thenReturn(new Book(
                        "b1", "Spring GraphQL Patterns", 5));
        when(catalog.labelForStock(5))
                .thenReturn("IN_STOCK");

        tester.documentName("bookById")
                .variable("id", "b1")
                .execute()
                .path("bookById.stockLabel")
                .entity(String.class)
                .isEqualTo("IN_STOCK");

        verify(catalog).findById("b1");
        verify(catalog).labelForStock(5);
    }

    @Test
    void unselectedNestedFieldIsNotFetched() {
        when(catalog.findById("b1"))
                .thenReturn(new Book(
                        "b1", "Spring GraphQL Patterns", 5));

        tester.document("""
                {
                  bookById(id: "b1") {
                    id
                    title
                  }
                }
                """)
                .execute()
                .path("bookById.title")
                .entity(String.class)
                .isEqualTo("Spring GraphQL Patterns");

        verify(catalog).findById("b1");
        verify(catalog, never()).labelForStock(anyInt());
    }

    @Test
    void absentBookIsAValidNullField() {
        tester.document("""
                {
                  bookById(id: "absent") { id }
                }
                """)
                .execute()
                .path("bookById")
                .valueIsNull();

        verify(catalog).findById("absent");
    }

    @Test
    void missingRequiredVariableCreatesGraphqlError() {
        tester.document("""
                query FindBook($id: ID!) {
                  bookById(id: $id) { id }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isNotEmpty());

        verifyNoInteractions(catalog);
    }

    @Test
    void outOfStockInvokesFieldResolver() {
        when(catalog.findById("b2"))
                .thenReturn(new Book(
                        "b2", "Testing GraphQL", 0));
        when(catalog.labelForStock(0))
                .thenReturn("OUT_OF_STOCK");

        tester.document("""
                {
                  bookById(id: "b2") {
                    stock
                    stockLabel
                  }
                }
                """)
                .execute()
                .path("bookById.stockLabel")
                .entity(String.class)
                .isEqualTo("OUT_OF_STOCK");

        verify(catalog).findById("b2");
        verify(catalog).labelForStock(0);
    }

    @Test
    void nullParentDoesNotInvokeNestedResolver() {
        tester.document("""
                {
                  bookById(id: "missing") {
                    stockLabel
                  }
                }
                """)
                .execute()
                .path("bookById")
                .valueIsNull();

        verify(catalog).findById("missing");
        verify(catalog, never()).labelForStock(anyInt());
    }
}
~~~

**Tại sao bảy test đều quan trọng?**

1. **Bean scope:** Có Book controller, không có Status controller; BookCatalogService là Mockito mock do @MockBean cung cấp.
2. **GraphQL document:** documentName đọc đúng query fixture, variable id được @Argument bind; root/nested resolver đều chạy và mock interactions được verify.
3. **Selection set:** Không chọn stockLabel ⇒ nested resolver không chạy. Test chứng minh điều đó bằng never(), không chỉ nhìn JSON.
4. **Nullable field:** Mock chưa stub cho "absent" trả null; schema bookById: Book cho phép null, nên valueIsNull() hợp lệ.
5. **Required variable:** Thiếu $id: ID! dẫn đến GraphQL errors trước controller; verifyNoInteractions chứng minh service chưa được gọi. Không so sánh exact error text dễ đổi theo GraphQL Java version.
6. **Out of stock:** b2 có stock=0; field resolver được gọi và trả OUT_OF_STOCK.
7. **Null parent:** Book null thì không có source object cho stockLabel; nested resolver không chạy.

**Lưu ý quan trọng:** Một Book tồn tại nhưng stockLabel: String! được resolve thành null **khác** với Book nullable không tồn tại: GraphQL có thể báo non-null violation và null bubbling trong trường hợp đầu. Khi mock nested collaborator, phải stub đúng nếu query yêu cầu field non-null.

**@MockBean vs @Mock:** @MockBean Spring Boot 3.3 đăng ký một bean mock cho Spring container để controller được inject. @Mock của MockitoExtension chỉ tạo test field, không tự trở thành Spring bean. Spring Boot thông thường reset @MockBean sau mỗi method theo MockReset.AFTER, không cần Mockito.reset thủ công hoặc test order.

## 6. SystemStatusGraphQlSliceTest — 2 phương thức @Test

**src/test/java/demo/graphql/SystemStatusGraphQlSliceTest.java**

~~~java
package demo.graphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.ApplicationContext;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

@GraphQlTest(SystemStatusGraphQlController.class)
class SystemStatusGraphQlSliceTest {

    @Autowired
    GraphQlTester tester;

    @Autowired
    ApplicationContext context;

    @Test
    void excludesBookControllerAndCatalogService() {
        assertThat(context.getBeansOfType(
                SystemStatusGraphQlController.class)).hasSize(1);
        assertThat(context.getBeansOfType(
                BookGraphQlController.class)).isEmpty();
        assertThat(context.getBeansOfType(
                BookCatalogService.class)).isEmpty();
    }

    @Test
    void executesStatusResolver() {
        tester.document("{ systemStatus }")
                .execute()
                .path("systemStatus")
                .entity(String.class)
                .isEqualTo("READY");
    }
}
~~~

Ở đây không cần mock BookCatalogService: controller được chọn độc lập và Book controller vắng mặt. Schema vẫn có Book/bookById, nhưng operation test chỉ chọn systemStatus và resolver của nó tồn tại. Một slice không yêu cầu thực thi tất cả schema fields nếu query không chọn chúng.

Nếu @GraphQlTest không có controller selector và scan cả hai controllers, dependency của Book controller phải được cung cấp dù bạn chỉ viết test status. Việc chọn controller rõ ràng thường làm context nhỏ và dễ chẩn đoán hơn.

## 7. GraphQlFullHttpTest — 3 phương thức test HTTP thật

Để xác nhận transport /graphql và service thật, chuyển sang @SpringBootTest(RANDOM_PORT).

**src/test/java/demo/graphql/GraphQlFullHttpTest.java**

~~~java
package demo.graphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphQlFullHttpTest {

    @Autowired
    HttpGraphQlTester tester;

    @Test
    void bookQueryUsesActualCatalogService() {
        tester.document("""
                {
                  bookById(id: "b1") {
                    title
                    stockLabel
                  }
                }
                """)
                .execute()
                .path("bookById.stockLabel")
                .entity(String.class)
                .isEqualTo("IN_STOCK");
    }

    @Test
    void fullContextIncludesStatusController() {
        tester.document("{ systemStatus }")
                .execute()
                .path("systemStatus")
                .entity(String.class)
                .isEqualTo("READY");
    }

    @Test
    void missingBookIsNullableOverHttp() {
        tester.document("""
                {
                  bookById(id: "missing") { id }
                }
                """)
                .execute()
                .path("bookById")
                .valueIsNull();
    }
}
~~~

Theo tài liệu Spring Boot 3.3, khi spring-graphql-test và WebTestClient dependencies phù hợp trên test classpath, @SpringBootTest(RANDOM_PORT) tự cấu hình HttpGraphQlTester hướng tới embedded server đang chạy. **Khác với @GraphQlTest**, request này đi qua HTTP transport. Full app tải BookCatalogService thật (Map.of) và cả hai controllers.

**Giới hạn:** Không có database, security, proxy hay WebSocket subscription trong ví dụ. Đừng coi ba HTTP tests này là bằng chứng cho persistence, login, CSRF, WebSocket handshake hoặc production deployment. Muốn thử các yêu cầu ấy phải thêm cấu hình và test riêng.

## 8. Chạy test, kiểm đếm và xem báo cáo

| Test class | Số @Test methods | Phạm vi |
|---|---:|---|
| BookGraphQlControllerSliceTest | **7** | Book resolver + mocked service |
| SystemStatusGraphQlSliceTest | **2** | Controller trạng thái |
| GraphQlFullHttpTest | **3** | Full HTTP + service thật |
| **Tổng** | **12** | 9 slice tests + 3 HTTP tests |

Đây là **12 phương thức test từ đúng ba source classes trên**, không tính các snippet minh họa nằm ngoài. Dự án có test khác thì tổng của Gradle có thể cao hơn. Không cần test order: mỗi test slice stub riêng, service thật bất biến.

Dùng Gradle Wrapper nếu có:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu tự tạo file mà chưa có Wrapper, ./gradlew chưa tồn tại; dùng Gradle tương thích tạo wrapper hoặc chạy gradle test. Báo cáo HTML thường tại **build/reports/tests/test/index.html**. Chạy riêng:

~~~bash
./gradlew test --tests demo.graphql.BookGraphQlControllerSliceTest
./gradlew test --tests demo.graphql.SystemStatusGraphQlSliceTest
./gradlew test --tests demo.graphql.GraphQlFullHttpTest
~~~

Với @GraphQlTest controller sets khác nhau, Spring TestContext có thể có cache keys riêng. Với RANDOM_PORT, full app cần khởi động embedded server. Đó là khác biệt chủ đích, không phải lỗi test.

## 9. GraphQlTester API cần sử dụng đúng

**document(String):** Gửi GraphQL operation text inline:

~~~java
tester.document("""
        {
          bookById(id: "b1") { title }
        }
        """)
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Patterns");
~~~

Snippet phải chạy trong test đã stub service hoặc dùng service thật; nếu mock chưa stub findById("b1"), Book có thể null khiến assertion fail.

**documentName(String):** Lấy file query theo tên từ classpath graphql-test/. Tên bookById đọc bookById.graphql được tạo ở phần 4. Đây là test operation, không phải schema.graphqls.

**variable(String,Object):** Truyền GraphQL variables đúng schema thay vì nối chuỗi input:

~~~java
tester.document("""
        query FindBook($id: ID!) {
          bookById(id: $id) { title }
        }
        """)
    .variable("id", "b1")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Patterns");
~~~

**path(...):** Đường dẫn tương đối với phần **data** của GraphQL response; path("bookById.title") tương ứng data.bookById.title. **valueIsNull()** khác **pathDoesNotExist()**: null là field có mặt với null, còn path không có có thể do operation không chọn field hoặc schema/data shape khác.

**errors():** GraphQL response có thể chứa errors ngay cả khi có data một phần. Nếu chủ động test lỗi:

~~~java
tester.document("""
        query FindBook($id: ID!) {
          bookById(id: $id) { id }
        }
        """)
    .execute()
    .errors()
    .satisfy(errors -> assertThat(errors).isNotEmpty());
~~~

errors().satisfy(...) nhận danh sách và đánh dấu chúng đã được kiểm tra. **errors().expect(predicate).verify()** yêu cầu có lỗi khớp predicate; **filter(predicate).verify()** bỏ qua lỗi nếu có nhưng không yêu cầu nó xuất hiện. Không filter mọi lỗi vô điều kiện vì sẽ che bug. Đừng khẳng định mọi GraphQL error tương đương HTTP 400/404/500.

## 10. Các mapping/resolver khác và ranh giới test

| Mapping hoặc extension | @GraphQlTest kiểm chứng được | Chưa kiểm chứng |
|---|---|---|
| **@QueryMapping** | Root query, argument binding, output/errors | HTTP auth, DB thật |
| **@MutationMapping** | Mutation resolver, mocked collaborators | DB commit/transaction/security |
| **@SchemaMapping** | Nested fields, source object, selection set | SQL N+1 khi repository bị mock |
| **@BatchMapping** | Batch field invocation trên selected objects | Performance DB nếu không dùng repo thật |
| **@SubscriptionMapping** | Publisher execution với tester phù hợp | WebSocket/RSocket transport |
| **RuntimeWiringConfigurer** | Custom scalar/data fetcher nếu bean có trong slice | Wiring ngoài slice |
| **DataFetcherExceptionResolver** | GraphQL error mapping ở execution layer | HTTP status/error page |
| **@GraphQlExceptionHandler** | Handler nếu controller/advice được nạp | Không giống MVC REST @ExceptionHandler |

Một schema dùng custom scalar như DateTime có thể fail startup nếu không đăng ký RuntimeWiringConfigurer đúng chỗ. Nếu bean này nằm trong @Configuration bị filter của slice loại, dùng **@Import** config cần thiết hoặc @TestConfiguration nhỏ. Không tự dùng @SpringBootTest để “chữa mọi lỗi missing bean” nếu mục tiêu chỉ là controller slice.

**ControllerAdvice trong GraphQL:** Có thể chứa @GraphQlExceptionHandler tùy thiết kế. Đừng giả định mọi @ControllerAdvice của REST được @GraphQlTest quét và áp dụng. Hãy kiểm tra chính bean handler có trong slice hay chưa; @Import một advice phù hợp nếu test error mapping cần nó.

**@MockBean vs @Mock vs @Import:**
- @MockBean Boot 3.3 tạo **Spring bean mock**, phục vụ wiring của controller do Spring tạo.
- @Mock của MockitoExtension tạo **Mockito field** trong test, không tự inject vào Spring ApplicationContext.
- @Import mang bean/config thật vào slice, phù hợp formatter hoặc wiring cần test; tránh nhập cả app kéo database/external services không cần.
- Unit test không tạo Spring context thì tự new controller(fakeService), nhanh nhưng **không xác minh schema/mapping**.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| @Autowired GraphQlTester không có bean | Thiếu spring-graphql-test/auto-config | Thêm test dependency đúng phiên bản |
| Context thiếu BookCatalogService | @Service bị loại khỏi slice | @MockBean hoặc @Import |
| Đã @Mock nhưng controller vẫn thiếu dependency | Mockito field không là Spring bean | @MockBean Boot 3.3 |
| Schema không khởi tạo | schema.graphqls thiếu/sai type/custom scalar | Kiểm tra graphql/** và RuntimeWiringConfigurer |
| Query field không tìm thấy | SDL và document không khớp | So field/argument names |
| documentName không tìm thấy | File ở sai path/extension | graphql-test/bookById.graphql |
| Controller khác vắng mặt | @GraphQlTest chỉ chọn một class | Chọn controller đúng hoặc slice khác |
| Root field null | Mock chưa stub hoặc service trả null | Kiểm nullable contract/fixture |
| Nested resolver không chạy | Field không trong selection set, parent null hoặc typeName sai | Kiểm schema, query và @SchemaMapping |
| Resolver trả null cho String! | Non-null violation | Stub/logic đúng, test GraphQL errors |
| Lỗi variable ID! trước khi service chạy | GraphQL coercion/validation | .errors().satisfy, verifyNoInteractions |
| Slice pass nhưng /graphql HTTP fail | @GraphQlTest không chạy HTTP transport | RANDOM_PORT + HttpGraphQlTester |
| HttpGraphQlTester không autowire | Thiếu WebTestClient deps hoặc sai test mode | starter-webflux test + RANDOM_PORT |
| Global advice không chạy | Advice không nằm trong bean filter | @Import/kiểm classpath |
| Test pass riêng nhưng fail suite | Fixture/mock/global state không cách ly | Tạo dữ liệu riêng, không phụ thuộc order |

**Quy trình debug:** kiểm schema → kiểm @GraphQlTest selector → kiểm các controller beans → cung cấp collaborator → gửi query tối thiểu → xem GraphQL errors trước data path → kiểm nested field selection → chỉ nâng lên HTTP/full context khi rủi ro yêu cầu.

## 12. Lựa chọn giữa slice và full integration

Chọn **@GraphQlTest** khi cần:
- Schema field, GraphQL syntax và argument binding.
- Phân biệt các @Controller trong slice.
- @QueryMapping/@SchemaMapping và selection set.
- GraphQL nullability và error mapping.
- Cô lập collaborator để test presentation layer.

Chọn **@SpringBootTest(RANDOM_PORT) + HttpGraphQlTester** khi cần:
- Xác nhận HTTP POST /graphql, port thật và codec/headers.
- Security filter/authentication, session/cookies/CSRF.
- Full bean wiring và service/repository thật.
- Error handling qua transport, status và content type.
- Tích hợp external services hoặc persistence bằng test environment riêng.

Đặc biệt, **@Transactional trên JUnit test method không tự rollback các database transactions đã commit bởi server request qua HTTP**, vì test client và server xử lý trong threads/transaction scopes khác nhau. Nếu mutation ghi dữ liệu, cần test DB/cleanup có chủ đích hoặc Testcontainers.

## 13. Bài tập

1. Viết thêm @GraphQlTest không có class selector; kiểm tra vì sao phải thỏa Book controller dependency dù query chỉ chọn systemStatus.
2. Thay selection set từ id/title sang id/title/stockLabel và dùng Mockito.verify chứng minh nested resolver chạy khi được chọn.
3. Thay stockLabel: String! bằng String nullable; thiết kế test phân biệt null field và GraphQL errors.
4. Thêm @MutationMapping createBook với argument input type; test slice với mock và full integration có DB cleanup.
5. Tạo custom DateTime scalar. Khi slice không có RuntimeWiringConfigurer, sửa test bằng @Import đúng bean.
6. Viết test thiếu ID! variable, kiểm errors và verifyNoInteractions.
7. Thêm Spring Security vào HTTP app và chứng minh @GraphQlTest không thay thế được kiểm thử /graphql transport auth.
8. Giải thích tại sao @GraphQlTest không phải test SOAP @Endpoint/WSDL.

## 14. Tham khảo

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @GraphQlTest, scope, @MockBean, tester variants.
- [Spring Boot 3.3 — Spring for GraphQL](https://docs.spring.io/spring-boot/3.3/reference/web/spring-graphql.html): starter, schema file và HTTP transport.
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html): document, variables, path và errors.
- [Spring for GraphQL 1.3 — GraphQlTester.Errors](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Errors.html): expect/filter/satisfy/verify.
- [Spring for GraphQL 1.3 — GraphQlTester.Path](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Path.html): entity/valueIsNull/pathDoesNotExist.
- [Spring for GraphQL — Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html): @QueryMapping, @SchemaMapping, @Argument.
- [Spring Guide — Building a GraphQL Service](https://spring.io/guides/gs/graphql-server): schema, controller và GraphQlTester.

**Kết luận:** @GraphQlTest là **GraphQL execution slice**, không phải HTTP server test. Chỉ định controller, dùng @MockBean cho collaborator ngoài slice, và GraphQlTester xác minh schema/argument, root/nested resolver, selection set, null và errors. Khi cần full bean wiring hoặc HTTP /graphql, dùng @SpringBootTest(RANDOM_PORT) cùng HttpGraphQlTester.