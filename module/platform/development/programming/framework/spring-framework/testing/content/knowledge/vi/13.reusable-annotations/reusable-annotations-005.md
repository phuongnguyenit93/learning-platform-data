# @NestedTestConfiguration để kiểm soát kế thừa cấu hình

JUnit Jupiter cho phép đặt các test class bên trong một test class khác bằng annotation **@Nested**. Cách tổ chức này giúp nhóm các tình huống kiểm thử quanh một hành vi hoặc một trạng thái chung. Trong khi đó, Spring TestContext Framework có thể kế thừa cấu hình kiểm thử từ enclosing class để các nested test dùng chung cấu hình và môi trường Spring.

Kế thừa cấu hình giúp giảm lặp lại, nhưng đôi khi một nested class cần một ApplicationContext, profile, property hoặc cấu hình kiểm thử riêng. Nếu mọi annotation của lớp bên ngoài đều tiếp tục ảnh hưởng đến nested class, việc tạo một test độc lập trong cùng cây lồng nhau có thể trở nên khó khăn.

**@NestedTestConfiguration** cho phép kiểm soát cách Spring TestContext xử lý annotation kiểm thử từ các enclosing class. Hai chế độ chính là:

- **INHERIT:** nested test class kế thừa annotation kiểm thử từ enclosing class. Đây là chế độ mặc định.
- **OVERRIDE:** nested test class không kế thừa annotation kiểm thử từ enclosing class; nó sử dụng cấu hình được khai báo trong chính nhánh test của nó.

Annotation này đặc biệt hữu ích khi kết hợp JUnit Jupiter @Nested với các cấu hình Spring như @SpringJUnitConfig, @SpringJUnitWebConfig, @ContextConfiguration, @ActiveProfiles, @TestPropertySource và các annotation TestContext khác.

## 1. Vấn đề kế thừa cấu hình trong nested test

Giả sử một nhóm test kiểm tra chức năng quản lý sản phẩm:

~~~java
@SpringJUnitConfig(ProductTestConfig.class)
class ProductServiceTests {

    @Autowired
    ProductService productService;

    @Nested
    class SearchTests {
        @Test
        void finds_products_by_name() {
            // ...
        }
    }

    @Nested
    class UpdateTests {
        @Test
        void updates_product_price() {
            // ...
        }
    }
}
~~~

Hai nested class thuộc cùng cây test với ProductServiceTests. Theo mặc định, Spring TestContext kế thừa cấu hình kiểm thử từ enclosing class. Vì vậy, nested test có thể dùng cấu hình ProductTestConfig mà không phải lặp lại @SpringJUnitConfig.

Điều này hữu ích khi các nhóm test cùng cần:

- Một ApplicationContext đã cấu hình các bean dùng chung.
- Cùng active profile.
- Cùng test property source.
- Cùng các TestExecutionListener hoặc thiết lập TestContext.
- Cùng cấu hình web hoặc database.

Nhưng giả sử UpdateTests cần một context riêng với repository giả hoặc profile khác. Nếu cấu hình từ lớp ngoài tiếp tục được kế thừa, nested test có thể nhận cả cấu hình mà nó không cần. Khi đó, @NestedTestConfiguration giúp chỉ định cách xử lý phần cấu hình đến từ enclosing class.

## 2. @NestedTestConfiguration là gì?

@NestedTestConfiguration thuộc Spring TestContext Framework:

~~~java
import org.springframework.test.context.NestedTestConfiguration;
import org.springframework.test.context.NestedTestConfiguration.EnclosingConfiguration;
~~~

Annotation này khai báo chế độ kế thừa annotation kiểm thử từ enclosing test class. Nó có thể được đặt trên test class hoặc sử dụng như meta-annotation trong một annotation tổng hợp.

Khai báo cơ bản:

~~~java
@NestedTestConfiguration(EnclosingConfiguration.INHERIT)
class ProductServiceTests {
}
~~~

Hoặc:

~~~java
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
class IsolatedNestedTests {
}
~~~

Annotation không tự tạo ApplicationContext, không thay đổi JUnit lifecycle và không quyết định một test class có được chạy hay không. Nó hướng dẫn Spring TestContext có tiếp nhận annotation kiểm thử từ lớp bao quanh hay không.

### 2.1. Hai chế độ

| Chế độ | Hành vi | Khi phù hợp |
| --- | --- | --- |
| INHERIT | Kế thừa annotation kiểm thử từ enclosing class | Nested tests cùng dùng cấu hình chung |
| OVERRIDE | Không kế thừa annotation kiểm thử từ enclosing class | Nested test cần cấu hình riêng hoặc cần cô lập khỏi cấu hình bên ngoài |

INHERIT là mặc định nếu không có cấu hình khác. Vì vậy, nhiều test class hiện có dùng @Nested vẫn hoạt động mà không cần thêm @NestedTestConfiguration.

### 2.2. Annotation có thể được kế thừa qua class hierarchy

@NestedTestConfiguration có thể được khai báo trên test class hoặc superclass. Chế độ được khai báo có thể áp dụng cho các nested test class trong phạm vi class hierarchy tương ứng. Điều này giúp một nhóm test lớn thống nhất cách xử lý enclosing configuration.

Nếu chỉ một nhánh nested cần hành vi khác, có thể khai báo chế độ phù hợp ở nhánh đó. Hãy đặt annotation gần nơi cần hiểu rõ tác động để người đọc nhận biết được vì sao cấu hình bên ngoài được kế thừa hoặc bị bỏ qua.

## 3. INHERIT: kế thừa cấu hình từ enclosing class

Với INHERIT, Spring TestContext tìm annotation kiểm thử trên enclosing class và đưa chúng vào quá trình xây dựng cấu hình cho nested test.

Ví dụ:

~~~java
@SpringJUnitConfig(ProductTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "catalog.page-size=20")
class ProductServiceTests {

    @Autowired
    ProductService productService;

    @Nested
    class SearchTests {

        @Test
        void uses_shared_product_configuration() {
            // Có thể dùng ProductService và cấu hình từ lớp ngoài.
        }
    }

    @Nested
    class DetailTests {

        @Test
        void loads_product_details() {
            // Cũng dùng cấu hình chung nếu không có cấu hình khác.
        }
    }
}
~~~

Trong ví dụ, các nested test kế thừa cấu hình Spring và profile từ ProductServiceTests. Property catalog.page-size cũng thuộc cấu hình kiểm thử của chúng.

Không phải mọi annotation đều hợp nhất theo cùng một cách. @NestedTestConfiguration quyết định có kế thừa annotation từ enclosing class hay không; sau đó từng annotation Spring áp dụng quy tắc merge riêng của nó.

Ví dụ:

- @ContextConfiguration có các thuộc tính như inheritLocations và inheritInitializers để điều khiển kế thừa cấu hình từ superclass.
- @ActiveProfiles có inheritProfiles để điều khiển việc kế thừa profile theo class hierarchy.
- @TestPropertySource có quy tắc kết hợp resource locations và inline properties.

Những quy tắc đó vẫn có ý nghĩa. @NestedTestConfiguration không thay thế các thuộc tính kế thừa riêng của từng annotation.

### 3.1. Nested class bổ sung cấu hình

Một nested test có thể kế thừa cấu hình chung và bổ sung cấu hình riêng:

~~~java
@SpringJUnitConfig(ProductTestConfig.class)
@ActiveProfiles("test")
class ProductServiceTests {

    @Nested
    @TestPropertySource(properties = "catalog.search-mode=exact")
    class ExactSearchTests {
        @Test
        void searches_using_exact_mode() {
            // ...
        }
    }
}
~~~

Trong chế độ INHERIT, nested test nhận annotation từ enclosing class và annotation được khai báo tại chính nó. Các nguồn property được hợp nhất theo quy tắc của @TestPropertySource.

Điều này hữu ích khi các nhóm test cùng dùng một nền tảng context nhưng cần một số cấu hình bổ sung để biểu diễn tình huống cụ thể.

## 4. OVERRIDE: bỏ kế thừa annotation từ enclosing class

Với OVERRIDE, Spring TestContext không kế thừa annotation kiểm thử từ enclosing class. Nested test cần khai báo cấu hình mà nó thực sự sử dụng.

Ví dụ:

~~~java
@SpringJUnitConfig(ProductTestConfig.class)
class ProductServiceTests {

    @Nested
    class StandardSearchTests {
        @Test
        void searches_with_default_configuration() {
            // Kế thừa cấu hình ProductTestConfig.
        }
    }

    @Nested
    @NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
    @SpringJUnitConfig(AlternativeProductTestConfig.class)
    class IsolatedSearchTests {

        @Test
        void searches_with_alternative_configuration() {
            // Dùng cấu hình được khai báo trong nhánh này.
        }
    }
}
~~~

IsolatedSearchTests không kế thừa cấu hình kiểm thử từ ProductServiceTests. Nó khai báo AlternativeProductTestConfig riêng. Điều này giúp nhánh test biểu đạt một môi trường độc lập.

Nếu nested class không khai báo cấu hình cần thiết sau khi chọn OVERRIDE, Spring có thể không tìm thấy context configuration hoặc không thể tạo context. OVERRIDE không tự tạo một context mặc định hoàn chỉnh; nó chỉ thay đổi quy tắc kế thừa từ enclosing class.

### 4.1. Khi nào dùng OVERRIDE?

OVERRIDE phù hợp khi nested test:

- Cần một ApplicationContext khác với lớp ngoài.
- Cần profile hoặc property source riêng, không muốn kế thừa cấu hình ngoài.
- Cần kiểm tra một cấu hình lỗi hoặc cấu hình tối thiểu độc lập.
- Dùng một tập bean khác, chẳng hạn thay adapter hoặc bật/tắt một feature.
- Cần tránh annotation bên ngoài ảnh hưởng đến nhánh test.

Hãy dùng OVERRIDE khi sự độc lập là một phần có chủ đích của thiết kế test. Nếu nested class chỉ cần thêm một property hoặc một profile theo cách merge được hỗ trợ, INHERIT có thể đơn giản hơn.

### 4.2. OVERRIDE không phải là xóa mọi quan hệ kế thừa

OVERRIDE nói về annotation kiểm thử từ enclosing class. Nó không thay đổi mọi quy tắc kế thừa của Java, JUnit hoặc Spring.

Cần phân biệt:

- Kế thừa annotation từ enclosing class: do @NestedTestConfiguration kiểm soát.
- Kế thừa annotation từ superclass: chịu ảnh hưởng của cơ chế kế thừa của từng annotation và các thuộc tính riêng.
- Kế thừa test method hoặc lifecycle theo JUnit: do JUnit Jupiter quản lý.
- Kế thừa cấu hình bean giữa các context cha/con: do cấu hình context hierarchy quản lý.

Ví dụ, @ContextConfiguration(inheritLocations = false) kiểm soát việc kế thừa locations từ superclass theo quy tắc của annotation đó. Nó không phải cách thay thế trực tiếp cho @NestedTestConfiguration(OVERRIDE), vốn điều khiển annotation từ enclosing class.

## 5. Cấu hình mặc định toàn cục

Mặc định của Spring TestContext là INHERIT. Có thể thay đổi mặc định cho toàn bộ test JVM bằng system property:

~~~text
-Dspring.test.enclosing.configuration=override
~~~

Giá trị hợp lệ là:

- inherit
- override

Ví dụ cấu hình trong Gradle:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty(
        "spring.test.enclosing.configuration",
        "override"
    )
}
~~~

Với Maven Surefire, có thể truyền system property qua cấu hình plugin hoặc tham số JVM tương ứng:

~~~xml
<systemPropertyVariables>
    <spring.test.enclosing.configuration>override</spring.test.enclosing.configuration>
</systemPropertyVariables>
~~~

System property phải có hiệu lực trong test JVM trước khi Spring TestContext xử lý test class. Đặt nó trong một property source của application context không có cùng ý nghĩa, vì đây là thiết lập điều khiển cách framework phát hiện annotation kiểm thử.

### 5.1. Chọn mặc định toàn cục hay chọn từng class?

Nếu phần lớn test trong dự án cần kế thừa cấu hình từ enclosing class, giữ mặc định INHERIT thường dễ hiểu.

Nếu dự án muốn mọi nested test tự khai báo cấu hình riêng, có thể đặt mặc định toàn cục là OVERRIDE. Sau đó, những test class cần chia sẻ cấu hình có thể khai báo INHERIT một cách tường minh.

Ví dụ:

~~~java
@NestedTestConfiguration(EnclosingConfiguration.INHERIT)
@SpringJUnitConfig(SharedTestConfig.class)
class SharedContextTests {
    @Nested
    class NestedFeatureTests {
        // Kế thừa cấu hình chung.
    }
}
~~~

Khi thay đổi mặc định toàn cục, hãy cân nhắc ảnh hưởng đến toàn bộ test suite. Một số nested class có thể đang dựa vào cấu hình ngoài mà không khai báo lại. Thay đổi property có thể khiến chúng không còn nạp context như trước.

### 5.2. Annotation tường minh giúp người đọc hiểu test

Khi dự án có nhiều nhóm test với mục đích khác nhau, khai báo @NestedTestConfiguration trực tiếp trên class có thể làm ý định rõ ràng hơn. Điều này đặc biệt hữu ích khi một test class được chia sẻ qua nhiều module hoặc được mở rộng bởi các test class khác.

Không cần thêm annotation ở mọi nơi nếu mặc định dự án đã rõ ràng và nhất quán. Hãy dùng nó khi muốn ghi lại một quyết định khác với mặc định hoặc khi phạm vi kế thừa không hiển nhiên.

## 6. Annotation nào chịu ảnh hưởng?

@NestedTestConfiguration tác động đến cách Spring TestContext xử lý annotation kiểm thử trên enclosing class. Các nhóm annotation thường gặp gồm:

| Nhóm | Ví dụ | Nội dung có thể được kế thừa |
| --- | --- | --- |
| Context bootstrap | @BootstrapWith, @ContextConfiguration | Bộ bootstrap và nguồn cấu hình context |
| Web context | @WebAppConfiguration | Cấu hình web application context |
| Profile | @ActiveProfiles | Profile hoạt động |
| Property | @TestPropertySource | Resource và property inline |
| Test execution | @TestExecutionListeners | Listener của TestContext |
| Lifecycle/context state | @DirtiesContext | Quy tắc đánh dấu context dirty |
| Transaction | @Transactional, @Commit, @Rollback | Cấu hình transaction cho test |
| SQL test support | @Sql, @SqlConfig, @SqlMergeMode | Script SQL và cách thực thi |
| Event/application test support | Các annotation TestContext liên quan | Cấu hình được framework hỗ trợ kế thừa |
| Bean override | @MockitoBean, @MockitoSpyBean và các khai báo override tương ứng | Bean override metadata trong cấu hình test |

Phạm vi chính xác của annotation được Spring hỗ trợ có thể phụ thuộc phiên bản và module tích hợp. Hãy xem Javadoc của phiên bản Spring đang dùng khi test dựa vào một annotation cụ thể. Không nên suy luận rằng mọi annotation của JUnit hoặc mọi annotation Java đều bị @NestedTestConfiguration điều khiển.

### 6.1. Annotation JUnit không đồng nghĩa annotation TestContext

@Nested là annotation của JUnit Jupiter để xác định nested test class. @Test, @BeforeEach, @AfterEach và các extension annotation thuộc cơ chế JUnit.

@NestedTestConfiguration điều khiển việc Spring TestContext kế thừa annotation kiểm thử từ enclosing class. Nó không thay đổi quy tắc phát hiện test method của JUnit hoặc biến một class thông thường thành nested test.

SpringExtension vẫn phải được đăng ký theo cách phù hợp, ví dụ qua @SpringJUnitConfig hoặc @ExtendWith(SpringExtension.class). Nếu cấu hình test class bị thay đổi bởi OVERRIDE, hãy bảo đảm nested class vẫn có cách kích hoạt Spring TestContext cần thiết.

## 7. Kết hợp với @SpringJUnitConfig

@SpringJUnitConfig là composed annotation kết hợp SpringExtension và ContextConfiguration. Khi đặt trên outer test class, nested test mặc định có thể kế thừa cấu hình đó.

Ví dụ:

~~~java
@SpringJUnitConfig(classes = CatalogTestConfig.class)
class CatalogTests {

    @Autowired
    CatalogService catalogService;

    @Nested
    class FindTests {

        @Test
        void finds_existing_item() {
            assertThat(catalogService.findById("SKU-1"))
                .isPresent();
        }
    }
}
~~~

Nếu FindTests cần cấu hình riêng:

~~~java
@Nested
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
@SpringJUnitConfig(classes = CatalogIsolatedTestConfig.class)
class FindTests {

    @Autowired
    CatalogService catalogService;
}
~~~

Điều quan trọng là nested test phải có cấu hình và extension cần thiết cho mục tiêu của nó. Khi dùng annotation composed, hãy nhớ rằng annotation tổng hợp có thể mang theo nhiều metadata Spring cùng lúc.

### 7.1. Cấu hình context và cấu hình test không phải một thứ

@NestedTestConfiguration không tự quyết định bean nào tồn tại trong context. Nó quyết định annotation từ enclosing class có tham gia vào cấu hình test hay không. Sau đó, @ContextConfiguration hoặc @SpringJUnitConfig mới xác định context được nạp từ đâu.

Ví dụ:

- INHERIT cho phép nested class nhận @SpringJUnitConfig từ outer class.
- OVERRIDE bỏ phần annotation đó khỏi quá trình kế thừa từ enclosing class.
- Nếu nested class khai báo @SpringJUnitConfig khác, Spring dùng cấu hình được khai báo ở nhánh đó.

## 8. Kết hợp với @SpringJUnitWebConfig

@SpringJUnitWebConfig kết hợp SpringExtension, ContextConfiguration và WebAppConfiguration. Vì vậy, nested web test cũng chịu ảnh hưởng của @NestedTestConfiguration.

Ví dụ:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
class WebControllerTests {

    @Autowired
    WebApplicationContext context;

    @Nested
    class PublicEndpointTests {
        // Kế thừa web context từ lớp ngoài.
    }

    @Nested
    @NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
    @SpringJUnitWebConfig(classes = AdminWebTestConfig.class)
    class AdminEndpointTests {
        // Dùng web configuration riêng.
    }
}
~~~

PublicEndpointTests có thể dùng chung WebApplicationContext được cấu hình ở lớp ngoài. AdminEndpointTests chọn OVERRIDE và khai báo cấu hình web riêng.

Nếu hai nhánh tạo context khác nhau, Spring có thể tạo các cache entry khác nhau. Nếu chúng có cùng cấu hình đã hợp nhất, TestContext có thể tái sử dụng context theo cơ chế cache thông thường.

## 9. Kết hợp với @ActiveProfiles và @TestPropertySource

Một trường hợp phổ biến là outer class đặt profile và property dùng chung, còn nested class thay đổi môi trường.

### 9.1. INHERIT với profile được hợp nhất

~~~java
@SpringJUnitConfig(classes = FeatureTestConfig.class)
@ActiveProfiles("test")
class FeatureTests {

    @Nested
    @ActiveProfiles("search")
    class SearchTests {
        @Test
        void uses_search_profile() {
            // ...
        }
    }
}
~~~

Trong chế độ INHERIT, profile từ enclosing class có thể được kế thừa và kết hợp theo quy tắc @ActiveProfiles. Mặc định, @ActiveProfiles có cơ chế kế thừa profile từ superclass; khi nested class khai báo profile riêng, hãy kiểm tra quy tắc merge và thuộc tính inheritProfiles của phiên bản Spring đang dùng.

Nếu muốn nested test dùng profile hoàn toàn độc lập, có thể dùng OVERRIDE và khai báo profile riêng:

~~~java
@Nested
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
@SpringJUnitConfig(classes = SearchOnlyTestConfig.class)
@ActiveProfiles("search")
class SearchTests {
}
~~~

### 9.2. INHERIT với property bổ sung

~~~java
@SpringJUnitConfig(classes = FeatureTestConfig.class)
@TestPropertySource(properties = "feature.enabled=true")
class FeatureTests {

    @Nested
    @TestPropertySource(properties = "feature.mode=fast")
    class FastModeTests {
        @Test
        void uses_fast_mode() {
            // ...
        }
    }
}
~~~

Nested class kế thừa property source từ enclosing class và bổ sung property riêng theo quy tắc của @TestPropertySource. Nếu cần thay toàn bộ nguồn property của nhánh nested, hãy xem xét OVERRIDE và khai báo nguồn mới rõ ràng.

## 10. Tác động đến ApplicationContext cache

TestContext Framework cache ApplicationContext theo cấu hình đã hợp nhất. @NestedTestConfiguration ảnh hưởng đến những annotation được đưa vào quá trình hợp nhất, vì vậy nó có thể gián tiếp ảnh hưởng context cache.

Ví dụ:

- Hai nested class dùng INHERIT và nhận cùng cấu hình từ outer class có thể dùng chung context.
- Một nested class dùng OVERRIDE và nạp cấu hình riêng có thể tạo context khác.
- Thay đổi active profiles, property source hoặc bean override có thể tạo cache key khác.

Không phải cứ có nested class là Spring tạo context mới. Context được tái sử dụng khi cấu hình đã hợp nhất tương đương và context còn trong cache.

### 10.1. Context cache không thay thế cô lập dữ liệu

Các nested test dùng chung context có thể cùng truy cập singleton bean. Nếu bean chứa mutable state, test phải reset state hoặc thiết kế bean stateless.

Database state, file, message và hệ thống ngoài không tự được làm sạch bởi context cache. Hãy dùng transaction, fixture, cleanup hoặc resource riêng.

### 10.2. Dùng OVERRIDE có thể tăng số context

Nếu mỗi nested class khai báo một cấu hình riêng, Spring có thể phải tạo nhiều context. Điều này có thể làm suite chậm hơn.

Hãy dùng context riêng khi test thực sự cần môi trường khác. Nếu chỉ cần thay một đầu vào nghiệp vụ, hãy truyền dữ liệu vào test thay vì tạo một cấu hình Spring mới.

## 11. Phân biệt enclosing class với superclass

Đây là điểm dễ nhầm khi có cả nested test và test class kế thừa.

Giả sử:

~~~java
abstract class BaseCatalogTests {
    // Cấu hình hoặc thiết lập chung theo superclass.
}

@SpringJUnitConfig(CatalogTestConfig.class)
class CatalogTests extends BaseCatalogTests {

    @Nested
    class SearchTests {
        // Nested test bên trong CatalogTests.
    }
}
~~~

Có hai quan hệ khác nhau:

1. CatalogTests kế thừa BaseCatalogTests theo Java class hierarchy.
2. SearchTests nằm bên trong CatalogTests theo quan hệ enclosing class.

@NestedTestConfiguration kiểm soát việc Spring TestContext kế thừa annotation từ quan hệ enclosing class. Các thuộc tính như inheritLocations hoặc inheritProfiles điều khiển quy tắc kế thừa riêng của annotation trong class hierarchy. Không nên dùng một cơ chế để suy luận thay cho cơ chế còn lại.

### 11.1. Khi superclass cũng có @NestedTestConfiguration

Nếu superclass hoặc enclosing test class khai báo @NestedTestConfiguration, chế độ đó có thể được kế thừa qua class hierarchy nhờ đặc tính của annotation. Hãy đặt chế độ ở một base test class khi toàn bộ nhóm test cần cùng một chính sách.

Nếu một lớp con cần thay đổi chính sách, có thể khai báo @NestedTestConfiguration trực tiếp trên lớp con. Cách này làm quyết định cục bộ rõ ràng và tránh thay đổi mặc định cho các test không liên quan.

## 12. Dùng @NestedTestConfiguration như meta-annotation

Các nhóm test có thể cần một chính sách kế thừa thống nhất. Có thể tạo composed annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
public @interface IsolatedNestedTests {
}
~~~

Sau đó:

~~~java
@IsolatedNestedTests
class PaymentTests {
    @Nested
    class ProviderTests {
        // Nhánh nested tuân theo chính sách OVERRIDE.
    }
}
~~~

Meta-annotation giúp đóng gói một quy ước dùng chung. Chỉ nên tạo khi có nhiều test class thực sự cần cùng chính sách và tên annotation diễn đạt được ý nghĩa. Với một trường hợp đơn lẻ, khai báo @NestedTestConfiguration trực tiếp thường dễ đọc hơn.

## 13. Các lỗi thường gặp

### Nested class không còn nhận cấu hình Spring

Nếu chọn OVERRIDE nhưng quên khai báo cấu hình riêng, Spring có thể không tìm thấy cấu hình context hoặc không tạo được bean cần thiết. Hãy kiểm tra annotation tổng hợp, cấu hình classes/locations và SpringExtension.

### Nghĩ rằng OVERRIDE xóa mọi cấu hình từ superclass

OVERRIDE điều khiển annotation từ enclosing class. Kế thừa Java và quy tắc riêng của từng annotation vẫn cần được xem xét độc lập.

### Dùng inheritLocations thay cho @NestedTestConfiguration

inheritLocations điều khiển kế thừa resource locations trong @ContextConfiguration theo class hierarchy. Nó không thay thế chính sách kế thừa annotation từ enclosing test class.

### Đặt @NestedTestConfiguration ở sai phạm vi

Nếu annotation đặt trên một superclass hoặc outer class, chế độ có thể ảnh hưởng nhiều nested test hơn dự kiến. Hãy đặt annotation gần nhánh cần thay đổi và xem xét phạm vi class hierarchy.

### Tạo nhiều context không cần thiết

Mỗi nested class khai báo profile hoặc property khác nhau có thể làm context cache key khác nhau. Chỉ tạo context riêng khi môi trường kiểm thử thực sự khác.

### Nhầm @NestedTestConfiguration với JUnit @Nested

@Nested của JUnit xác định nested test class. @NestedTestConfiguration điều khiển Spring TestContext inheritance. Hai annotation bổ sung cho nhau và không thể thay thế nhau.

### Cho rằng mọi annotation Java đều bị điều khiển

Annotation này dành cho annotation kiểm thử được Spring TestContext xử lý. Nó không thay đổi mọi annotation của JUnit hoặc framework khác.

## 14. Quy trình chọn INHERIT hay OVERRIDE

**Bước 1 – Xác định cấu hình outer class.** Ghi lại context configuration, profile, property source, listener, transaction và bean override mà lớp ngoài khai báo.

**Bước 2 – Xác định nested test cần gì.** Nested test có dùng chung bean và môi trường hay cần một context riêng?

**Bước 3 – Chọn INHERIT nếu cấu hình chung là có chủ đích.** Cho phép Spring kế thừa annotation từ enclosing class và dùng quy tắc merge riêng của từng annotation.

**Bước 4 – Chọn OVERRIDE nếu cần độc lập.** Ngăn Spring kế thừa annotation kiểm thử từ enclosing class và khai báo đầy đủ cấu hình cho nhánh nested.

**Bước 5 – Kiểm tra superclass riêng biệt.** Xem các thuộc tính inheritLocations, inheritProfiles và quy tắc Java inheritance có ảnh hưởng không.

**Bước 6 – Kiểm tra extension.** Bảo đảm SpringExtension được đăng ký theo cách phù hợp để nested test dùng Spring TestContext.

**Bước 7 – Quan sát context cache.** Nếu cấu hình khác nhau, chấp nhận context riêng; nếu cấu hình tương đương, để TestContext tái sử dụng cache.

**Bước 8 – Chạy test độc lập và theo suite.** Xác nhận nested test không phụ thuộc trạng thái hoặc thứ tự của nhánh khác.

## 15. Bảng quyết định nhanh

| Câu hỏi | Lựa chọn |
| --- | --- |
| Nested tests dùng chung cấu hình outer class? | INHERIT |
| Nested test cần bổ sung property hoặc annotation có thể merge? | Thường dùng INHERIT |
| Nested test cần context/profile độc lập? | OVERRIDE và khai báo cấu hình riêng |
| Muốn đổi mặc định cho toàn bộ test JVM? | System property spring.test.enclosing.configuration |
| Chỉ muốn ngừng kế thừa locations từ superclass? | Xem inheritLocations của @ContextConfiguration |
| Muốn thay đổi JUnit nested lifecycle? | Dùng cơ chế JUnit Jupiter, không phải @NestedTestConfiguration |
| Muốn nhiều nested test dùng một chính sách? | Đặt annotation ở base/outer class hoặc tạo meta-annotation |

## Kết luận

@NestedTestConfiguration cho phép Spring TestContext kiểm soát việc kế thừa annotation kiểm thử từ enclosing class của JUnit Jupiter nested tests. INHERIT là mặc định và phù hợp khi các nhánh test chia sẻ cấu hình. OVERRIDE giúp một nhánh nested độc lập với annotation của lớp bao quanh và tự khai báo context, profile hoặc property cần thiết.

Hãy phân biệt cơ chế này với kế thừa Java từ superclass, quy tắc merge riêng của @ContextConfiguration hoặc @ActiveProfiles, và lifecycle do JUnit quản lý. Khi chọn đúng phạm vi, nested tests có thể tái sử dụng cấu hình chung ở nơi phù hợp, tạo context riêng khi cần và giữ cho mục tiêu của từng nhánh kiểm thử rõ ràng.
