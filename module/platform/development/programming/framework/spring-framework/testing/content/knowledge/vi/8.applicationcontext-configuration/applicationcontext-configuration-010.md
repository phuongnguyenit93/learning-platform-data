# @ContextHierarchy cho quan hệ cha con

Spring TestContext Framework có thể tạo một ApplicationContext cho test, nhưng một số ứng dụng có cấu trúc nhiều tầng context. Ví dụ, một context gốc chứa service, repository và hạ tầng dùng chung; một context con chứa controller, handler hoặc các bean chỉ thuộc một module web. Trong cấu trúc đó, context con cần sử dụng bean của context cha, trong khi context cha không nên phụ thuộc ngược vào bean chỉ tồn tại ở context con.

**@ContextHierarchy** cho phép khai báo một chuỗi ApplicationContext có quan hệ cha con cho bài kiểm thử Spring. Mỗi cấp trong chuỗi được mô tả bằng một **@ContextConfiguration**. Spring TestContext Framework nạp các cấp theo thứ tự, thiết lập quan hệ parent-child và cung cấp context ở cấp cuối cho test.

Bài học này trình bày cách khai báo hierarchy bằng Java hoặc XML, cách bean được phân giải giữa các cấp, cách chia sẻ cấu hình qua các test class kế thừa, và cách quản lý cache cũng như vòng đời của hierarchy.

## 1. Vì sao cần quan hệ cha con giữa các ApplicationContext?

Một ứng dụng Spring có thể tổ chức bean theo nhiều phạm vi. Trong ứng dụng web truyền thống, một cấu trúc quen thuộc là:

- **Root context**: service, repository, transaction manager, data source, business component và các bean dùng chung.
- **Web context**: controller, MVC configuration, view resolver, handler interceptor và các bean chỉ phục vụ tầng web.

Web context cần gọi service ở root context. Tuy nhiên, service và repository không cần biết controller nào đang sử dụng chúng. Việc chia thành hai context giúp ranh giới phụ thuộc rõ ràng hơn.

Một cấu trúc tổng quát có thể biểu diễn như sau:

~~~text
Parent ApplicationContext
    |
    +-- OrderRepository
    +-- PaymentGateway
    +-- OrderService
    +-- TransactionManager
          |
          v
Child ApplicationContext
    |
    +-- OrderController
    +-- WebExceptionHandler
    +-- WebConfiguration
~~~

Context con có thể tra cứu bean từ context cha. Context cha không thể tra cứu bean chỉ được đăng ký trong context con. Quan hệ này giúp tầng phía trên sử dụng dịch vụ ở tầng dưới theo hướng phụ thuộc một chiều.

Trong test, nếu cần xác minh nhiều tầng context phối hợp đúng, ta có thể khai báo hierarchy bằng **@ContextHierarchy** thay vì gộp tất cả cấu hình vào một ApplicationContext.

## 2. @ContextHierarchy hoạt động như thế nào?

**@ContextHierarchy** là annotation của Spring TestContext Framework. Nó nhận một mảng các annotation **@ContextConfiguration**. Mỗi phần tử mô tả cấu hình của một cấp context trong hierarchy.

Ví dụ tối giản:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(classes = RootConfig.class),
    @ContextConfiguration(classes = WebConfig.class)
})
class OrderWebContextTest {
}
~~~

Spring tạo hai context:

1. Context thứ nhất từ RootConfig. Đây là context cha.
2. Context thứ hai từ WebConfig. Đây là context con và được thiết lập parent là context thứ nhất.

Thứ tự các phần tử trong **@ContextHierarchy** rất quan trọng: cấu hình đầu tiên là cấp cha ở trên cùng, cấu hình tiếp theo là cấp con của cấp đứng ngay trước nó.

Nếu khai báo ba phần tử, context thứ hai là con của context thứ nhất, context thứ ba là con của context thứ hai. Vì vậy, một hierarchy có thể có nhiều hơn hai cấp khi kiến trúc thực sự cần.

### Mỗi cấp có cấu hình riêng

Mỗi **@ContextConfiguration** có thể chỉ định class cấu hình Java, resource XML, initializer hoặc context loader phù hợp. Ví dụ:

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = InfrastructureConfig.class),
    @ContextConfiguration(classes = ApplicationConfig.class),
    @ContextConfiguration(classes = WebConfig.class)
})
~~~

Trong ví dụ này, ba context lần lượt đại diện cho hạ tầng, ứng dụng và tầng web. Các bean ở cấp con có thể sử dụng bean ở những cấp cha phía trên thông qua cơ chế phân giải bean của Spring.

**@ContextHierarchy** không phải một cách viết ngắn cho nhiều class cấu hình trong cùng context. Nó yêu cầu Spring tạo nhiều ApplicationContext có quan hệ parent-child. Nếu chỉ muốn đăng ký nhiều cấu hình vào cùng một context, hãy dùng nhiều class trong thuộc tính classes của **@ContextConfiguration**, hoặc dùng **@Import**.

## 3. Quy tắc tra cứu bean giữa context cha và con

Quan hệ cha con của ApplicationContext dựa trên khả năng tra cứu bean qua BeanFactory cha.

- Context con trước tiên tìm bean trong phạm vi của chính nó.
- Nếu không tìm thấy bean phù hợp ở cấp con, nó có thể tiếp tục tìm trong context cha.
- Việc tra cứu có thể tiếp tục lên các cấp cha cao hơn.
- Context cha không thể đi xuống để lấy bean được đăng ký riêng trong context con.

Ví dụ, RootConfig khai báo service:

~~~java
@Configuration
class RootConfig {

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }
}
~~~

WebConfig khai báo controller cần OrderService:

~~~java
@Configuration
class WebConfig {

    @Bean
    OrderController orderController(OrderService orderService) {
        return new OrderController(orderService);
    }
}
~~~

Khi Spring tạo OrderController trong context con, nó có thể phân giải tham số OrderService từ context cha. Vì vậy, controller dùng được service dù service không được đăng ký lại trong WebConfig.

### Bean cùng tên ở context con

Nếu context cha và context con có bean cùng tên, context con có thể định nghĩa bean riêng với tên đó. Khi tra cứu từ context con, bean ở cấp con được ưu tiên; bean cha vẫn tồn tại trong context cha.

Điều này có thể hữu ích khi test muốn thay một collaborator ở tầng con. Tuy nhiên, việc che khuất bean cha cần được thực hiện có chủ đích vì nó có thể khiến người đọc khó biết bean nào đang được sử dụng.

Không nên dựa vào việc trùng tên để thay bean một cách ngầm định nếu cấu hình dự án có thể dùng cơ chế rõ ràng hơn như profile, test configuration hoặc bean override.

### Vì sao không đưa tất cả bean vào context cha?

Nếu controller được đặt ở root context, các context con có thể vô tình nhận được bean web không cần thiết. Điều đó làm ranh giới kiến trúc mờ đi và có thể gây lỗi khi ứng dụng có nhiều web context hoặc nhiều DispatcherServlet.

Hãy đặt bean vào cấp thấp nhất trong hierarchy mà tất cả consumer cần dùng. Bean dùng chung đặt ở context cha; bean đặc thù của một module đặt ở context con tương ứng.

## 4. Ví dụ cấu hình cha con bằng Java

Giả sử ứng dụng có OrderService dùng repository, còn OrderController dùng OrderService. Ta muốn test wiring của hai tầng context.

Cấu hình cha:

~~~java
@Configuration
class RootConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

Cấu hình con:

~~~java
@Configuration
class WebConfig {

    @Bean
    OrderController orderController(OrderService orderService) {
        return new OrderController(orderService);
    }
}
~~~

Test khai báo hierarchy:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class OrderControllerContextTest {

    @Autowired
    private OrderController orderController;

    @Test
    void createsControllerWithServiceFromParentContext() {
        assertNotNull(orderController);

        OrderView view = orderController.find("order-18");

        assertEquals("order-18", view.id());
    }
}
~~~

Spring nạp RootConfig trước, sau đó tạo context con từ WebConfig với context cha đã có. OrderController được tạo trong context con, còn OrderService và OrderRepository đến từ context cha.

Test inject OrderController từ context cuối cùng của hierarchy. Việc gọi controller trong ví dụ này là minh họa cho wiring; trong ứng dụng web, nếu muốn kiểm tra mapping HTTP, request và response, hãy dùng cấu hình web phù hợp cùng MockMvc hoặc một test web chuyên biệt.

## 5. Cấu hình hierarchy bằng XML

Nếu ứng dụng sử dụng XML, mỗi cấp có thể chỉ định một hoặc nhiều resource.

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        locations = "classpath:root-context.xml"
    ),
    @ContextConfiguration(
        name = "web",
        locations = "classpath:web-context.xml"
    )
})
class LegacyWebContextTest {
}
~~~

Ví dụ root-context.xml:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderRepository"
          class="example.persistence.InMemoryOrderRepository"/>

    <bean id="orderService"
          class="example.order.OrderService">
        <constructor-arg ref="orderRepository"/>
    </bean>
</beans>
~~~

Ví dụ web-context.xml:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderController"
          class="example.web.OrderController">
        <constructor-arg ref="orderService"/>
    </bean>
</beans>
~~~

Bean orderService được khai báo ở root context. Khi Spring tạo bean orderController ở context con, tham chiếu đến orderService có thể được phân giải qua parent BeanFactory.

Resource XML phải có trên test runtime classpath. Nếu không tìm thấy resource, context sẽ không khởi tạo được. Hãy đặt file trong thư mục test resources phù hợp với cấu trúc build của dự án.

## 6. Kết hợp context hierarchy với cấu hình web

Trong ứng dụng Spring MVC, một mô hình phổ biến là root context chứa service và persistence, còn web context chứa controller và MVC infrastructure.

Một test có thể dùng **@WebAppConfiguration** để yêu cầu Spring tạo WebApplicationContext và cung cấp môi trường Servlet giả lập cho web test. Ví dụ về khai báo:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebMvcConfig.class
    )
})
class OrderWebApplicationContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;
}
~~~

Trong cấu hình thực tế, WebMvcConfig sẽ khai báo hoặc import các thành phần MVC cần thiết. RootConfig chứa các service và repository dùng chung.

Nếu muốn kiểm tra HTTP request qua Spring MVC, có thể tạo MockMvc từ WebApplicationContext:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebMvcConfig.class
    )
})
class OrderMvcHierarchyTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void returnsOrderFromParentService() throws Exception {
        mockMvc.perform(get("/orders/order-18"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("order-18"));
    }
}
~~~

Đây là dạng cấu hình cho Spring MVC TestContext. Test cần có controller và các thành phần web được đăng ký trong web context; service và repository cần có ở root context. Các import, bean và test data cụ thể tùy theo ứng dụng.

**@WebAppConfiguration** thiết lập môi trường web cho TestContext. Nó không tự tạo toàn bộ MVC configuration, không tự đăng ký controller và cũng không khởi chạy một HTTP server thật. Nếu cần xác minh server được khởi động và xử lý request qua cổng mạng, hãy dùng một kiểu integration test phù hợp với ứng dụng.

## 7. Dùng nhiều cấp context trong một hierarchy

Không bắt buộc hierarchy chỉ có root và web. Một ứng dụng có thể cần ba cấp hoặc hơn, nhưng chỉ nên chia khi mỗi cấp có một phạm vi bean và quan hệ phụ thuộc rõ ràng.

Ví dụ:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "infrastructure",
        classes = InfrastructureConfig.class
    ),
    @ContextConfiguration(
        name = "application",
        classes = ApplicationConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebConfig.class
    )
})
class FullModuleHierarchyTest {
}
~~~

Trong mô hình này:

- InfrastructureConfig chứa DataSource, repository adapter, clock hoặc các bean kỹ thuật.
- ApplicationConfig chứa service nghiệp vụ và các use case.
- WebConfig chứa controller, MVC configuration và web-specific component.

Context ở cấp application có thể dùng bean từ infrastructure. Context ở cấp web có thể dùng bean từ application và infrastructure thông qua chuỗi parent.

Không nên chia context chỉ để tạo ra nhiều tầng cho đẹp. Mỗi cấp làm tăng số cấu hình cần quản lý và có thể làm việc chẩn đoán lỗi khởi tạo phức tạp hơn. Nếu các bean không cần ranh giới cha con, một context duy nhất với nhiều class cấu hình thường đơn giản hơn.

## 8. Kế thừa và hợp nhất hierarchy giữa các test class

Một lợi ích quan trọng của **@ContextHierarchy** là khả năng chia sẻ cấu hình giữa các test class trong cùng một hệ thống kế thừa.

Ví dụ, class cơ sở khai báo root và web context:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = BaseWebConfig.class
    )
})
abstract class BaseWebTests {
}
~~~

Test cho trang quản trị có thể bổ sung cấu hình ở cấp web:

~~~java
@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = AdminWebConfig.class
    )
})
class AdminWebTests extends BaseWebTests {
}
~~~

Các hierarchy được kế thừa và hợp nhất theo mặc định. Thuộc tính **name** của từng **@ContextConfiguration** giúp Spring nhận diện cấp nào cần hợp nhất. Trong ví dụ, cấp root được kế thừa; cấu hình có tên web ở lớp con được ghép vào cấp web tương ứng.

Điều này cho phép nhiều test class dùng chung cấu hình root mà vẫn có thể bổ sung cấu hình riêng ở cấp con.

### Vì sao nên đặt name cho từng cấp?

Khi hierarchy được kế thừa, tên cấp giúp diễn đạt rõ cấu hình nào thuộc cùng một vị trí logic. Ví dụ:

- root: bean dùng chung của ứng dụng.
- web: cấu hình MVC.
- admin: cấu hình dành cho khu vực quản trị.

Tên phải nhất quán giữa các lớp muốn hợp nhất cùng cấp. Nếu các tên không khớp hoặc hierarchy có cấu trúc khác nhau, việc hợp nhất có thể không tạo ra kết quả mà người viết mong đợi.

Nếu không đặt tên, Spring dựa vào vị trí các cấp trong hierarchy để xử lý việc kế thừa. Với cấu trúc có nhiều lớp và nhiều cấp, đặt tên tường minh giúp dễ hiểu hơn.

### Khi nào không muốn kế thừa hierarchy?

Theo mặc định, cấu hình hierarchy có thể được kế thừa từ superclass. Nếu một test class cần định nghĩa hierarchy riêng, không muốn kế thừa các cấu hình cha, có thể cấu hình **inheritLocations = false** trên **@ContextHierarchy**:

~~~java
@ContextHierarchy(
    value = {
        @ContextConfiguration(
            name = "root",
            classes = IsolatedRootConfig.class
        ),
        @ContextConfiguration(
            name = "web",
            classes = IsolatedWebConfig.class
        )
    },
    inheritLocations = false
)
class IsolatedWebTests extends BaseWebTests {
}
~~~

Cách này hữu ích khi lớp con cần một hierarchy độc lập. Hãy dùng nó có chủ đích vì cấu hình cha không còn được hợp nhất theo cách mặc định.

## 9. Context hierarchy và TestContext cache

Tạo ApplicationContext có thể tốn thời gian vì Spring phải xử lý bean definition, tạo singleton, chạy post-processor, kết nối các phụ thuộc và thực hiện bước khởi tạo.

Spring TestContext Framework có context cache để tái sử dụng context giữa các test có cấu hình tương thích. Với hierarchy, các context của từng cấp được quản lý theo cấu hình đã hợp nhất và quan hệ cha con tương ứng.

Ví dụ, hai test class có cùng cấu hình root và cùng cấu hình web có thể chia sẻ các context tương ứng thay vì tạo lại toàn bộ mỗi lần.

Các yếu tố như class cấu hình, resource locations, initializer, active profiles, property source, context customizer, context loader và parent context có thể ảnh hưởng đến việc một context có thể được tái sử dụng hay không.

### Tận dụng cache

- Dùng chung cấu hình root cho các test thực sự có cùng yêu cầu.
- Giữ tên và thứ tự hierarchy ổn định.
- Tránh tạo nhiều biến thể property hoặc profile không cần thiết.
- Hạn chế thay đổi trạng thái singleton bean trong test.
- Không đánh dấu context dirty nếu chỉ cần dọn dữ liệu test.

Cache giúp giảm thời gian khởi tạo nhưng không làm các context trở thành một context duy nhất. Mỗi cấp vẫn có bean registry và lifecycle riêng.

### Chú ý trạng thái mutable

Bean singleton trong context cha có thể được dùng bởi nhiều test class và nhiều context con. Nếu test sửa trạng thái của bean đó mà không khôi phục, test khác có thể nhận trạng thái còn sót lại.

Ví dụ, một fake repository trong root context lưu đơn hàng trong Map. Nếu nhiều test dùng chung root context, dữ liệu từ test trước có thể ảnh hưởng đến test sau. Có thể giải quyết bằng cách tạo dữ liệu riêng, dọn dữ liệu sau test, dùng repository có transaction phù hợp hoặc thiết kế fixture độc lập.

Không nên dựa vào thứ tự test để đảm bảo trạng thái đúng.

## 10. @DirtiesContext trong context hierarchy

**@DirtiesContext** đánh dấu ApplicationContext là không còn phù hợp để tái sử dụng. Spring TestContext sẽ loại context liên quan khỏi cache và đóng nó khi phù hợp.

Khi test sử dụng hierarchy, cần quyết định phạm vi context bị đánh dấu dirty. Thuộc tính **hierarchyMode** của **@DirtiesContext** hỗ trợ hai chế độ:

- **EXHAUSTIVE**: chế độ mặc định; loại context hiện tại cùng các context liên quan trong hierarchy theo phạm vi exhaustive.
- **CURRENT_LEVEL**: chỉ loại context ở cấp hiện tại được gắn với test.

Ví dụ:

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS,
    hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL
)
class AdminWebTests extends BaseWebTests {
}
~~~

Nếu chỉ có trạng thái ở web context bị làm bẩn, CURRENT_LEVEL có thể giúp giữ lại context cha đang còn hợp lệ. Nếu trạng thái thay đổi ảnh hưởng đến cả hierarchy, cần loại các context liên quan theo chế độ phù hợp.

Không nên dùng **@DirtiesContext** như một cách dọn mọi dữ liệu test. Nó quản lý vòng đời ApplicationContext, không thay thế việc rollback transaction, xóa dữ liệu database, dừng container hoặc thu hồi message đã gửi ra broker.

Việc loại context cha cũng có thể khiến các context con phụ thuộc vào nó cần được tạo lại. Hãy xem xét phạm vi phụ thuộc trước khi chọn hierarchyMode.

## 11. Khác nhau giữa hierarchy và nhiều cấu hình trong cùng context

Một nhầm lẫn phổ biến là khai báo nhiều class cấu hình trong **@ContextConfiguration** rồi nghĩ rằng Spring tạo nhiều context. Thực tế, nhiều class cấu hình trong cùng một khai báo thường được nạp vào cùng ApplicationContext.

So sánh:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
    RootConfig.class,
    WebConfig.class
})
class SingleContextTest {
}
~~~

Trong ví dụ này, RootConfig và WebConfig cùng đóng góp bean definition cho một context.

Trong khi đó:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(classes = RootConfig.class),
    @ContextConfiguration(classes = WebConfig.class)
})
class ParentChildContextTest {
}
~~~

Ví dụ thứ hai tạo hai context có quan hệ parent-child.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Nhiều class cấu hình cùng tạo một context | @ContextConfiguration(classes = {...}) |
| Chia bean thành nhiều module nhưng không cần quan hệ cha con | @Import hoặc nhiều class cấu hình |
| Context con cần dùng bean từ context cha | @ContextHierarchy |
| Nhiều test class kế thừa các cấp context chung | @ContextHierarchy kết hợp name |
| Chỉ cần thay một bean trong test context | Cơ chế test bean override hoặc cấu hình test phù hợp |

Chỉ dùng hierarchy khi quan hệ cha con là một phần của cấu trúc cần kiểm tra hoặc cần tái hiện. Nếu chỉ muốn chia file cấu hình cho dễ đọc, **@Import** thường đủ.

## 12. Những lỗi thường gặp khi dùng @ContextHierarchy

### Đặt bean ở sai cấp

Nếu controller được khai báo ở root context nhưng phụ thuộc vào một bean chỉ tồn tại ở child context, Spring không thể phân giải dependency theo hướng child-to-parent. Hãy đặt bean tiêu thụ ở cấp con hoặc đưa dependency dùng chung lên cấp cha phù hợp.

### Cho rằng context cha nhìn thấy bean con

Quan hệ tra cứu đi từ con lên cha. Không có cơ chế tự động để parent tra cứu bean ở child. Nếu service cần một collaborator, collaborator đó phải được đăng ký ở context cha hoặc được truyền qua một thiết kế phụ thuộc phù hợp.

### Khai báo trùng bean và vô tình che khuất

Một bean ở child có thể che khuất bean cùng tên ở parent trong quá trình tra cứu từ child. Điều này có thể gây ra hành vi khó hiểu nếu test không biết bean nào được sử dụng. Hãy đặt tên và phạm vi bean có chủ đích, tránh trùng tên không cần thiết.

### Nhầm nhiều config với nhiều context

Nhiều class trong thuộc tính classes không tự tạo hierarchy. Cần dùng **@ContextHierarchy** với một **@ContextConfiguration** cho mỗi cấp.

### Sai thứ tự các cấp

Cấp đầu tiên là cha trên cùng, cấp tiếp theo là con. Nếu đảo thứ tự, dependency có thể không phân giải được vì bean cần thiết lại nằm ở context con.

### Kế thừa cấu hình ngoài ý muốn

Nếu superclass đã khai báo hierarchy, subclass có thể kế thừa và hợp nhất cấu hình. Hãy dùng tên cấp rõ ràng và cân nhắc **inheritLocations = false** khi cần một hierarchy độc lập.

### Dùng @DirtiesContext quá rộng

Loại toàn bộ hierarchy có thể làm nhiều context phải khởi tạo lại, khiến test suite chậm. Hãy chọn hierarchy mode theo cấp thực sự bị làm bẩn.

### Tạo hierarchy phức tạp hơn nhu cầu

Mỗi cấp làm tăng độ phức tạp cấu hình, cache và chẩn đoán. Nếu test không cần phân biệt bean cha và con, một context đơn giản sẽ dễ duy trì hơn.

## 13. Quy trình thiết kế hierarchy cho một bài test

Khi quyết định dùng **@ContextHierarchy**, hãy xác định ranh giới trước khi viết annotation:

1. Xác định bean nào được nhiều module hoặc nhiều tầng dùng chung.
2. Đặt các bean dùng chung vào context cha.
3. Đặt bean đặc thù của module vào context con.
4. Xác định các dependency đi từ child lên parent.
5. Chọn Java configuration, XML hoặc initializer cho từng cấp.
6. Khai báo hierarchy theo thứ tự cha trước, con sau.
7. Dùng name cho các cấp cần hợp nhất qua test class kế thừa.
8. Kiểm tra context được inject vào test là cấp cuối phù hợp với hành vi cần xác minh.
9. Quản lý test data và singleton state để test không phụ thuộc thứ tự.
10. Chỉ dùng @DirtiesContext khi context thực sự bị làm bẩn và chọn phạm vi loại cache phù hợp.

Ví dụ tổng hợp với ba cấp:

~~~java
@Configuration
class InfrastructureConfig {

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-06-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }
}
~~~

~~~java
@Configuration
class ApplicationConfig {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            Clock clock) {
        return new OrderService(repository, clock);
    }
}
~~~

~~~java
@Configuration
class WebConfig {

    @Bean
    OrderController orderController(OrderService orderService) {
        return new OrderController(orderService);
    }
}
~~~

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "infrastructure",
        classes = InfrastructureConfig.class
    ),
    @ContextConfiguration(
        name = "application",
        classes = ApplicationConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebConfig.class
    )
})
class OrderHierarchyTest {

    @Autowired
    private OrderController orderController;

    @Test
    void wiresWebApplicationToParentServices() {
        assertNotNull(orderController);

        OrderView result = orderController.find("order-18");

        assertEquals("order-18", result.id());
    }
}
~~~

Khi Spring xử lý cấu hình này, OrderRepository và Clock được tạo ở cấp infrastructure; OrderService được tạo ở cấp application và nhận dependency từ parent; OrderController được tạo ở cấp web và nhận OrderService từ context cha.

Ví dụ minh họa nguyên tắc wiring. Trong dự án thực tế, repository, controller và dữ liệu test cần được định nghĩa theo model và hợp đồng thực của ứng dụng.

## 14. Khi nào nên và không nên dùng @ContextHierarchy?

Nên dùng khi:

- Ứng dụng có root context và một hoặc nhiều child context thực sự.
- Các context con cần chia sẻ bean hạ tầng hoặc service từ context cha.
- Test cần xác minh wiring và khả năng phân giải bean giữa các cấp.
- Nhiều test class cần chia sẻ một phần hierarchy và bổ sung cấu hình ở cấp riêng.
- Cần tái hiện cấu trúc nhiều DispatcherServlet hoặc nhiều vùng web có context riêng.

Không cần dùng khi:

- Tất cả bean có thể cùng tồn tại trong một ApplicationContext.
- Việc tách cấu hình chỉ nhằm tổ chức file hoặc package.
- Test chỉ kiểm tra logic service thuần Java.
- Không có dependency hoặc yêu cầu lifecycle nào cần quan hệ cha con.

Một hierarchy tốt phản ánh ranh giới kiến trúc thực tế. Nó giúp test xác nhận bean được đặt đúng cấp, dependency được phân giải theo đúng hướng và cấu hình có thể chia sẻ giữa các test. Khi hierarchy không mang lại lợi ích cụ thể, một ApplicationContext đơn giản thường dễ hiểu, nhanh và dễ bảo trì hơn.

**@ContextHierarchy** là công cụ để mô tả nhiều ApplicationContext có quan hệ cha con trong Spring TestContext Framework. Bằng cách khai báo từng cấp bằng **@ContextConfiguration**, đặt bean theo phạm vi sử dụng, đặt tên cấp khi cần kế thừa và quản lý context cache có chủ đích, test có thể tái hiện đúng cấu trúc nhiều tầng của ứng dụng mà vẫn giữ được sự tách biệt giữa các module.

