# Danh sách listener mặc định và trách nhiệm của chúng

Spring TestContext Framework dùng TestExecutionListener để gắn các hành vi hỗ trợ vào vòng đời của một bài kiểm thử. Mỗi listener nhận callback khi test class được chuẩn bị, test instance được tạo, test method bắt đầu hoặc kết thúc. Nhờ đó, các tính năng như dependency injection cho test, quản lý ApplicationContext, transaction, chạy SQL script và ghi nhận application event có thể hoạt động nhất quán mà test không phải tự gọi từng thành phần.

Các listener mặc định được Spring đăng ký tự động khi khởi tạo TestContext. Chúng có thứ tự thực thi xác định để những việc chuẩn bị diễn ra trước khi test chạy và việc dọn dẹp diễn ra sau khi test hoàn tất. Khi cần mở rộng, ta có thể thêm listener riêng hoặc thay đổi danh sách theo cấu hình @TestExecutionListeners.

## 1. TestExecutionListener nằm ở đâu trong TestContext Framework?

TestExecutionListener là một interface của Spring, nằm trong package org.springframework.test.context. Nó là một phần của Spring TestContext Framework, không phải interface TestExecutionListener cùng tên của JUnit Platform.

Spring dùng TestContextManager để điều phối các listener. Manager giữ TestContext, cập nhật thông tin về test class, test instance, test method và exception, sau đó gọi callback tương ứng trên từng listener. Khi tích hợp với JUnit Jupiter, SpringExtension kết nối vòng đời của JUnit với TestContextManager. Các annotation như @SpringJUnitConfig đã tích hợp Spring Extension, nên thường không cần khai báo riêng @ExtendWith(SpringExtension.class) khi đã dùng annotation đó.

Một test class có thể khai báo cấu hình Spring như sau:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class CustomerServiceTest {
    @Autowired
    private CustomerService customerService;

    @Test
    void findsCustomer() {
        // Thực hiện kiểm tra với bean đã được Spring inject.
    }
}
~~~

Khi chạy test, Spring Extension tạo và sử dụng TestContextManager. Các listener được gọi ở những mốc phù hợp để chuẩn bị context, inject test instance, mở transaction hoặc thực hiện các công việc liên quan. Test class chỉ khai báo điều cần kiểm tra; phần tích hợp vòng đời được framework đảm nhiệm.

## 2. Các callback trong vòng đời test

Interface TestExecutionListener định nghĩa các callback chính sau:

| Callback | Thời điểm | Phạm vi |
|---|---|---|
| beforeTestClass | Trước khi các test method của class bắt đầu | Một lần cho test class |
| prepareTestInstance | Sau khi tạo test instance, trước khi chạy các fixture setup của test | Mỗi test instance |
| beforeTestMethod | Trước mỗi test method | Mỗi test method |
| beforeTestExecution | Ngay trước phần thân test method | Mỗi test method |
| afterTestExecution | Ngay sau phần thân test method, kể cả khi method phát sinh exception | Mỗi test method |
| afterTestMethod | Sau khi test method hoàn tất và các callback dọn dẹp method được xử lý | Mỗi test method |
| afterTestClass | Sau khi các test method của class hoàn tất | Một lần cho test class |

Hai cặp callback beforeTestMethod và beforeTestExecution, afterTestExecution và afterTestMethod phục vụ các mốc khác nhau. Chẳng hạn, listener có thể chuẩn bị transaction trước khi test method chạy, trong khi một listener khác cần đo thời gian chỉ tính phần thân test. Nếu đặt cả hai việc ở cùng một callback, phạm vi đo hoặc thời điểm kích hoạt có thể không đúng mong muốn.

Các callback bắt đầu như beforeTestClass, prepareTestInstance, beforeTestMethod và beforeTestExecution được gọi theo thứ tự listener đã sắp xếp. Các callback kết thúc như afterTestExecution, afterTestMethod và afterTestClass được gọi theo thứ tự ngược lại để việc dọn dẹp diễn ra theo chiều ngược với quá trình chuẩn bị. Cách tổ chức này tương tự nguyên tắc mở tài nguyên theo một thứ tự rồi đóng theo thứ tự ngược lại.

## 3. Danh sách listener mặc định của Spring Framework

Với Spring Framework 6.1, danh sách listener mặc định của TestContext Framework gồm tám listener theo thứ tự sau:

| Thứ tự | Listener | Trách nhiệm chính |
|---:|---|---|
| 1 | ServletTestExecutionListener | Chuẩn bị trạng thái request/response cho web test |
| 2 | DirtiesContextBeforeModesTestExecutionListener | Xử lý @DirtiesContext ở các chế độ BEFORE |
| 3 | ApplicationEventsTestExecutionListener | Ghi nhận application event trong test khi được bật |
| 4 | DependencyInjectionTestExecutionListener | Inject các phụ thuộc vào test instance |
| 5 | DirtiesContextTestExecutionListener | Xử lý @DirtiesContext ở các chế độ AFTER |
| 6 | TransactionalTestExecutionListener | Quản lý transaction do test khai báo |
| 7 | SqlScriptsTestExecutionListener | Chạy SQL script được khai báo bằng @Sql |
| 8 | EventPublishingTestExecutionListener | Phát Spring application event cho các mốc của vòng đời test |

Danh sách trên mô tả các listener thuộc Spring Framework 6.1. Danh sách thực tế phụ thuộc phiên bản Spring và các thư viện kiểm thử được đưa vào classpath. Spring Boot hoặc module mở rộng có thể bổ sung listener cho các tính năng riêng; không nên mặc định mọi listener nhìn thấy trong một dự án Spring Boot đều là listener lõi của Spring Framework.

Spring TestContext sử dụng cơ chế SpringFactoriesLoader để khám phá các TestExecutionListener được đăng ký bởi framework và các thư viện trên classpath. Các listener được sắp xếp theo thứ tự của chúng trước khi TestContextManager sử dụng. Vì vậy, dependency kiểm thử được thêm vào dự án có thể làm danh sách thực tế thay đổi mà test class không cần tự liệt kê các listener đó.

### 3.1. ServletTestExecutionListener

ServletTestExecutionListener hỗ trợ các bài kiểm thử ứng dụng web dựa trên Servlet. Khi test sử dụng cấu hình web phù hợp, listener chuẩn bị các đối tượng request và response giả, đồng thời thiết lập request attributes trong RequestContextHolder. Nhờ đó, mã ứng dụng có thể truy cập thông tin request thông qua cơ chế Spring mà không cần một Servlet container thật.

Ví dụ, một thành phần sử dụng RequestContextHolder để đọc request hiện tại có thể được kiểm tra trong môi trường mock web:

~~~java
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;

public class CurrentRequestService {
    public String currentRequestId() {
        RequestAttributes attributes =
                RequestContextHolder.currentRequestAttributes();
        return (String) attributes.getAttribute(
                "requestId",
                RequestAttributes.SCOPE_REQUEST);
    }
}
~~~

Trong web test, request context được chuẩn bị để mã ứng dụng có thể dùng API trên. Listener cũng quản lý việc dọn trạng thái request theo vòng đời test để dữ liệu của một request không rò rỉ sang test khác.

Listener này chỉ có ý nghĩa khi test có môi trường web phù hợp, ví dụ cấu hình WebApplicationContext với @WebAppConfiguration. Với unit test thông thường hoặc context không phải web, không cần tự tạo request chỉ để sử dụng listener này.

### 3.2. DirtiesContextBeforeModesTestExecutionListener

DirtiesContextBeforeModesTestExecutionListener xử lý những trường hợp @DirtiesContext yêu cầu loại bỏ context trước khi test class hoặc test method chạy. Các chế độ BEFORE thường dùng khi một test trước đó đã làm thay đổi trạng thái cấu hình của context và test hiện tại cần một context mới.

Ví dụ:

~~~java
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.BEFORE_CLASS)
class FreshContextTest {
    // Test class được chạy với context mới theo chế độ đã khai báo.
}
~~~

@DirtiesContext đánh dấu ApplicationContext là không còn phù hợp để tái sử dụng. Listener trước test xử lý các chế độ BEFORE; listener DirtiesContextTestExecutionListener ở phía sau xử lý các chế độ AFTER. Việc tách hai listener giúp Spring đặt thao tác loại bỏ context đúng mốc trong vòng đời.

Không nên dùng @DirtiesContext chỉ để xóa dữ liệu nghiệp vụ trong database. Annotation này tác động đến cache và vòng đời của ApplicationContext; dữ liệu database cần được dọn bằng transaction, SQL cleanup hoặc cơ chế dữ liệu test thích hợp.

### 3.3. ApplicationEventsTestExecutionListener

ApplicationEventsTestExecutionListener cung cấp khả năng ghi nhận các Spring application event được phát trong lúc test. Khi bật @RecordApplicationEvents, test có thể inject ApplicationEvents và truy vấn những event đã được phát trong phạm vi test.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEvent;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

class OrderCreatedEvent extends ApplicationEvent {
    OrderCreatedEvent(Object source) {
        super(source);
    }
}

@SpringJUnitConfig(TestConfiguration.class)
@RecordApplicationEvents
class OrderEventTest {
    @Autowired
    private ApplicationEvents applicationEvents;

    @Autowired
    private OrderService orderService;

    @Test
    void publishesOrderCreatedEvent() {
        orderService.createOrder();

        long count = applicationEvents
                .stream(OrderCreatedEvent.class)
                .count();

        assertEquals(1, count);
    }
}
~~~

ApplicationEvents giúp test xác nhận một hành vi hướng sự kiện đã xảy ra mà không cần tự cài một listener quan sát trong từng test. Listener quản lý bộ ghi nhận theo vòng đời test và làm cho dữ liệu event có phạm vi phù hợp với test đang chạy.

@RecordApplicationEvents là điều kiện quan trọng để bật chức năng ghi nhận. Nếu không yêu cầu ghi nhận, không nên giả định rằng mọi event trong toàn bộ context đều được lưu để test truy vấn.

### 3.4. DependencyInjectionTestExecutionListener

DependencyInjectionTestExecutionListener inject các phụ thuộc Spring vào test instance. Đây là listener khiến những trường hoặc phương thức được đánh dấu bằng annotation injection có thể nhận bean từ ApplicationContext.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class ProductServiceTest {
    @Autowired
    private ProductService productService;

    @Test
    void loadsProduct() {
        // productService đã được Spring inject vào test instance.
    }
}
~~~

Listener này thực hiện công việc autowire và khởi tạo test instance theo cơ chế của Spring. Nó thường được dùng cùng @SpringJUnitConfig, @ContextConfiguration hoặc các cấu hình TestContext khác.

Hãy phân biệt việc inject phụ thuộc vào test instance với việc inject vào bean ứng dụng. Spring container vẫn tạo và inject các bean ứng dụng theo cấu hình của nó; listener này bổ sung bước chuẩn bị cho chính đối tượng test do JUnit tạo ra.

Nếu một unit test chỉ cần kiểm tra logic của một lớp Java, có thể tạo lớp đó bằng constructor và truyền fake hoặc mock trực tiếp. Khi đó, không cần bật TestContext chỉ để inject một trường.

### 3.5. DirtiesContextTestExecutionListener

DirtiesContextTestExecutionListener xử lý các chế độ AFTER của @DirtiesContext, chẳng hạn loại bỏ context sau một test method hoặc sau một test class. Khi context bị đánh dấu dirty, Spring loại nó khỏi context cache và đóng context theo cơ chế quản lý vòng đời.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class ContextMutationTest {
    @Test
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void changesContextState() {
        // Test có thay đổi trạng thái cấu hình của context.
    }
}
~~~

Các test sau cần context tương ứng sẽ phải lấy một context mới từ cấu hình. Việc này có thể làm test chạy chậm hơn vì Spring phải khởi tạo lại bean và các thành phần liên quan.

Chỉ đánh dấu context dirty khi test thật sự làm thay đổi cấu trúc hoặc trạng thái của context theo cách ảnh hưởng đến test khác. Nếu vấn đề chỉ là dữ liệu trong một bảng, transaction rollback hoặc SQL cleanup thường phù hợp hơn.

### 3.6. TransactionalTestExecutionListener

TransactionalTestExecutionListener hỗ trợ transaction do test quản lý (test-managed transaction). Khi test class hoặc test method được đánh dấu @Transactional, listener có thể bắt đầu transaction trước test method và rollback sau khi test kết thúc theo mặc định.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

@SpringJUnitConfig(TestConfiguration.class)
@Transactional
class ProductRepositoryTest {
    @Autowired
    private ProductRepository repository;

    @Test
    void savesProductInsideTestTransaction() {
        repository.save(new Product("P-01", "Keyboard"));

        assertTrue(repository.findById("P-01").isPresent());
    }
}
~~~

Trong ví dụ, thao tác lưu và truy vấn diễn ra trong transaction của test. Sau test, dữ liệu thường được rollback nên không tồn tại như dữ liệu đã commit của ứng dụng.

Một số annotation điều khiển hành vi transaction:

- @Rollback chỉ định test transaction có rollback hay không; mặc định là rollback.
- @Commit yêu cầu commit transaction khi test hoàn tất.
- @BeforeTransaction đánh dấu phương thức chạy trước khi test-managed transaction bắt đầu.
- @AfterTransaction đánh dấu phương thức chạy sau khi test-managed transaction kết thúc.

Listener cần tìm được transaction manager phù hợp trong context. Nếu có nhiều transaction manager, cấu hình phải giúp Spring chọn đúng manager cho test. Cũng cần nhớ rằng test-managed transaction không tự động bao trùm mọi tác vụ chạy ở thread khác; các thao tác bất đồng bộ hoặc transaction do ứng dụng tự mở có thể có vòng đời riêng.

Không nên dùng @Commit tùy tiện trong test dùng chung database. Dữ liệu được commit có thể ảnh hưởng các lần chạy sau và khiến test phụ thuộc trạng thái môi trường.

### 3.7. SqlScriptsTestExecutionListener

SqlScriptsTestExecutionListener thực thi SQL script được khai báo bằng @Sql. Đây là cách chuẩn bị dữ liệu trước test hoặc dọn dữ liệu sau test mà không cần viết nhiều lệnh setup trong Java.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@Sql(
        scripts = "/sql/products-before.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class ProductSqlTest {
    @Test
    @Sql(
            scripts = "/sql/products-after.sql",
            executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
    void readsPreparedProductData() {
        // Kiểm tra dữ liệu được tạo bởi products-before.sql.
    }
}
~~~

BEFORE_TEST_METHOD là pha mặc định khi không khai báo pha khác. AFTER_TEST_METHOD thường được dùng để thực hiện script cleanup. Có thể cấu hình chi tiết hơn bằng @SqlConfig, ví dụ chọn datasource, transaction manager, encoding hoặc transaction mode.

Listener này phối hợp với transaction test khi cấu hình cho phép. Script có thể tham gia transaction hiện có hoặc được thực thi trong transaction riêng theo @SqlConfig. Do đó, cần hiểu thứ tự listener và cấu hình transaction nếu muốn dữ liệu setup được rollback cùng test hoặc cần tồn tại ngoài transaction.

@Sql có thể đặt ở cấp class hoặc method. Khi cùng tồn tại nhiều khai báo, cơ chế merge mặc định và @SqlMergeMode quyết định cách kết hợp script ở hai cấp. Hãy chọn rõ dữ liệu nền dùng chung và dữ liệu đặc thù của từng test để tránh script khó theo dõi.

### 3.8. EventPublishingTestExecutionListener

EventPublishingTestExecutionListener phát các Spring application event tương ứng với những mốc của vòng đời test. Các thành phần trong ApplicationContext có thể lắng nghe những event này bằng @EventListener hoặc cơ chế listener của Spring.

Các event được phát tương ứng với những mốc như:

- BeforeTestClassEvent
- PrepareTestInstanceEvent
- BeforeTestMethodEvent
- BeforeTestExecutionEvent
- AfterTestExecutionEvent
- AfterTestMethodEvent
- AfterTestClassEvent

Ví dụ, một thành phần có thể lắng nghe event trước khi phần thân test chạy:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.test.context.event.BeforeTestExecutionEvent;

public class TestLifecycleObserver {
    @EventListener
    public void beforeTestExecution(
            BeforeTestExecutionEvent event) {
        Class<?> testClass = event.getTestContext().getTestClass();
        System.out.println(
                "Starting test in " + testClass.getSimpleName());
    }
}
~~~

Listener này giúp tích hợp các phản ứng theo vòng đời test vào hệ thống event của Spring. Nó khác với ApplicationEventsTestExecutionListener: EventPublishingTestExecutionListener phát event mô tả vòng đời của test; ApplicationEventsTestExecutionListener hỗ trợ ghi nhận các application event do ứng dụng phát ra để test truy vấn.

## 4. Thứ tự listener ảnh hưởng đến điều gì?

Thứ tự mặc định phản ánh quan hệ phụ thuộc giữa các công việc. Một web test cần request context được chuẩn bị ở đầu vòng đời. Test instance cần được inject trước khi chạy phần kiểm tra. Transaction phải được thiết lập ở mốc phù hợp để các thao tác repository và SQL script tham gia đúng transaction. Khi test kết thúc, các listener dọn dẹp chạy theo chiều ngược lại để đóng những tài nguyên đã được mở.

Có thể hình dung trình tự chuẩn bị và kết thúc như sau:

~~~text
Chuẩn bị test
    |
    v
ServletTestExecutionListener
    |
    v
DirtiesContextBeforeModesTestExecutionListener
    |
    v
ApplicationEventsTestExecutionListener
    |
    v
DependencyInjectionTestExecutionListener
    |
    v
DirtiesContextTestExecutionListener
    |
    v
TransactionalTestExecutionListener
    |
    v
SqlScriptsTestExecutionListener
    |
    v
EventPublishingTestExecutionListener
    |
    v
Thực thi test và gọi callback kết thúc theo thứ tự ngược
~~~

Sơ đồ thể hiện thứ tự listener trong danh sách Spring Framework 6.1; không có nghĩa tất cả listener đều thực hiện công việc trong mọi test. Một listener chỉ hành động khi điều kiện hoặc annotation liên quan được đáp ứng. Ví dụ, listener transaction không mở transaction nếu test không có cấu hình transaction phù hợp; SQL listener không chạy script nếu test không khai báo @Sql.

Nếu một listener cần dữ liệu do listener khác chuẩn bị, thứ tự đăng ký có thể quyết định kết quả. Vì vậy, khi thêm listener riêng, hãy xác định rõ callback cần chạy trước hay sau listener mặc định nào. Với các callback kết thúc, hãy nhớ thứ tự gọi bị đảo ngược.

## 5. Đăng ký listener mặc định và listener tùy chỉnh

Spring tự tìm các listener mặc định từ cơ chế đăng ký của framework. Trong trường hợp thông thường, test chỉ cần khai báo cấu hình TestContext và các annotation chức năng như @Transactional, @Sql hoặc @RecordApplicationEvents; không phải liệt kê thủ công từng listener.

Khi cần thêm một listener riêng, dùng @TestExecutionListeners. Ví dụ sau đăng ký listener để ghi thời gian thực thi phần thân test:

~~~java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class TestTimingListener
        extends AbstractTestExecutionListener {

    private static final String START_TIME =
            TestTimingListener.class.getName() + ".START_TIME";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Object value = testContext.removeAttribute(START_TIME);
        if (value instanceof Long startTime) {
            long elapsedNanos = System.nanoTime() - startTime;
            System.out.printf(
                    "%s.%s took %d ns%n",
                    testContext.getTestClass().getSimpleName(),
                    testContext.getTestMethod().getName(),
                    elapsedNanos);
        }
    }
}
~~~

Có thể gắn listener vào test class:

~~~java
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.TestExecutionListeners.MergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@TestExecutionListeners(
        listeners = TestTimingListener.class,
        mergeMode = MergeMode.MERGE_WITH_DEFAULTS)
class TimedServiceTest {
    // Các test method được theo dõi thời gian thực thi.
}
~~~

Điểm quan trọng là mergeMode = MERGE_WITH_DEFAULTS. Khi khai báo listener tùy chỉnh, nếu dùng chế độ mặc định REPLACE_DEFAULTS, danh sách listener mặc định có thể bị thay thế. Khi đó, các chức năng như inject test instance, transaction hoặc chạy @Sql có thể không còn hoạt động như dự kiến. MERGE_WITH_DEFAULTS giữ listener mặc định và bổ sung listener tùy chỉnh vào danh sách.

AbstractTestExecutionListener cung cấp các triển khai rỗng cho callback, vì vậy listener chỉ cần override những mốc nó quan tâm. Nếu cần điều khiển thứ tự, có thể triển khai Ordered hoặc dùng @Order. Giá trị order nhỏ hơn được ưu tiên trước trong các callback bắt đầu; callback kết thúc được gọi theo thứ tự ngược.

Không nên tạo custom listener cho một hành vi đã có annotation hoặc extension chuyên dụng. Listener phù hợp khi cần tích hợp một quy tắc dùng chung vào vòng đời TestContext, chẳng hạn thu thập thông tin, chuẩn bị fixture đặc thù hoặc quản lý một tài nguyên dùng chung cho nhiều test.

## 6. Phân biệt listener của Spring Framework với phần mở rộng của Spring Boot

Spring Boot xây dựng trên Spring TestContext Framework và có thể bổ sung listener để hỗ trợ các tính năng kiểm thử riêng. Ví dụ, các tính năng mock bean, reset mock, REST Docs hoặc công cụ kiểm thử khác có thể đăng ký listener bổ sung thông qua module tương ứng.

Vì thế, khi quan sát một dự án Boot, danh sách listener đang chạy có thể dài hơn danh sách tám listener lõi của Spring Framework 6.1. Sự khác biệt này đến từ phiên bản Spring, phiên bản Boot và các dependency kiểm thử có mặt trên classpath.

Spring Framework 6.2 bổ sung hạ tầng bean override cho test, bao gồm các annotation như @TestBean, @MockitoBean và @MockitoSpyBean; phiên bản này có thêm BeanOverrideTestExecutionListener để xử lý cơ chế override bean. Khi đọc danh sách mặc định của một phiên bản mới hơn, cần kiểm tra đúng tài liệu hoặc mã nguồn của phiên bản đang dùng thay vì áp nguyên danh sách 6.1.

Nếu một test dùng @MockitoBean để thay bean trong ApplicationContext, đó là cơ chế bean override của Spring TestContext ở phiên bản hỗ trợ. @Mock của Mockito vẫn chỉ tạo mock trong test instance; nó không tự thay bean trong context. Phân biệt hai cơ chế giúp tránh trường hợp test có một mock nhưng service được Spring inject vẫn nhận bean thật.

## 7. Khi nào nên quan tâm đến từng listener?

Không phải test nào cũng cần hiểu chi tiết mọi listener. Có thể bắt đầu từ tính năng test đang sử dụng:

| Nhu cầu kiểm thử | Listener liên quan | Điều cần quan sát |
|---|---|---|
| Inject bean vào test class | DependencyInjectionTestExecutionListener | Test instance nhận đúng bean từ context |
| Kiểm tra code phụ thuộc request hiện tại | ServletTestExecutionListener | Request attributes và mock servlet objects sẵn sàng |
| Cần context mới trước/sau test | Hai listener DirtiesContext... | Context bị loại khỏi cache đúng thời điểm |
| Rollback dữ liệu sau test | TransactionalTestExecutionListener | Test-managed transaction và rollback |
| Chuẩn bị hoặc dọn dữ liệu SQL | SqlScriptsTestExecutionListener | Script chạy đúng pha và transaction mode |
| Kiểm tra application event | ApplicationEventsTestExecutionListener | Event được ghi nhận trong phạm vi test |
| Phản ứng theo lifecycle test | EventPublishingTestExecutionListener | Event lifecycle được phát vào Spring context |

Khi một tính năng không hoạt động, hãy kiểm tra lần lượt annotation kích hoạt, context có đúng loại hay không, listener có nằm trong danh sách thực tế hay không và thứ tự callback có phù hợp không. Ví dụ, @Transactional sẽ không tự tạo transaction nếu context thiếu transaction manager phù hợp; @Sql không thể chạy script nếu datasource không được cấu hình; @RecordApplicationEvents không ghi nhận event nếu cấu hình test không bật chức năng tương ứng.

## 8. Một số nguyên tắc khi làm việc với listener

- Dùng listener mặc định khi tính năng đã được Spring hỗ trợ qua annotation như @Autowired, @Transactional, @Sql, @DirtiesContext hoặc @RecordApplicationEvents.
- Ghi nhớ danh sách listener theo phiên bản framework; danh sách của Spring Boot có thể bao gồm phần mở rộng từ Boot và các dependency.
- Dùng MERGE_WITH_DEFAULTS khi chỉ muốn bổ sung listener tùy chỉnh mà vẫn giữ chức năng nền của TestContext.
- Chọn callback theo đúng mốc cần xử lý: chuẩn bị class, chuẩn bị test instance, trước method, trước phần thân method hoặc sau khi method kết thúc.
- Dùng AbstractTestExecutionListener nếu chỉ cần override một vài callback.
- Chọn order có chủ đích khi listener phụ thuộc dữ liệu hoặc trạng thái do listener khác tạo ra.
- Tránh lưu trạng thái mutable toàn cục trong listener; ưu tiên thuộc tính của TestContext hoặc tài nguyên có vòng đời rõ ràng.
- Dọn tài nguyên trong callback kết thúc tương ứng và bảo đảm thao tác dọn dẹp chịu được trường hợp test phát sinh exception.
- Dùng @DirtiesContext cho thay đổi ảnh hưởng đến context; dùng transaction hoặc SQL cleanup cho dữ liệu database.
- Khi kiểm tra một tính năng Spring, hãy chọn phạm vi test phù hợp. Unit test thuần Java không cần tạo TestContext nếu không có hành vi Spring nào cần xác nhận.

Các listener mặc định tạo thành lớp tích hợp giữa vòng đời của test và các dịch vụ Spring. Nắm được thứ tự và trách nhiệm của chúng giúp giải thích vì sao một test được inject bean, chạy trong transaction, nhận request giả hoặc ghi nhận event. Khi cần mở rộng, một listener tùy chỉnh có thể tham gia cùng cơ chế đó, miễn là danh sách mặc định và thứ tự callback được giữ đúng theo mục đích kiểm thử.
