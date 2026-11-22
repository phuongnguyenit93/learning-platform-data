# Thời điểm đóng context trước hoặc sau lớp hay phương thức

Spring TestContext Framework có thể lưu ApplicationContext vào cache để nhiều test dùng chung một context đã khởi tạo. Cách làm này giúp test chạy nhanh, nhưng cũng có nghĩa trạng thái của bean singleton có thể còn tồn tại sau một test method hoặc một test class. Khi một test làm thay đổi context đến mức những test khác không thể tiếp tục dùng an toàn, Spring cung cấp annotation **@DirtiesContext** để đánh dấu context cần được loại khỏi cache và đóng lại.

@DirtiesContext cho phép chọn thời điểm xử lý context theo hai cấp:

- **Theo test method:** đóng context trước hoặc sau một method cụ thể.
- **Theo test class:** đóng context trước lớp, sau lớp, hoặc trước/sau từng test method trong lớp.

Việc chọn đúng thời điểm quyết định test nào nhận context mới, test nào có thể dùng lại context đã cache và thời điểm Spring gọi quá trình đóng bean. Bài học này tập trung vào các chế độ BEFORE_METHOD, AFTER_METHOD, BEFORE_CLASS, AFTER_CLASS, BEFORE_EACH_TEST_METHOD và AFTER_EACH_TEST_METHOD.

## 1. Vì sao cần chọn thời điểm đóng ApplicationContext?

Spring TestContext thường tái sử dụng context giữa các test có cấu hình tương đương. Ví dụ, hai test class cùng dùng @SpringBootTest với cùng cấu hình có thể nhận cùng một context được cache trong một JVM.

Điều này hữu ích vì khởi tạo context có thể tốn thời gian: Spring phải đọc cấu hình, tạo bean, inject dependency, chạy callback khởi tạo và thiết lập các thành phần hạ tầng. Nếu mỗi test method đều tạo context mới, suite có thể chậm đáng kể.

Tuy nhiên, context được chia sẻ cũng giữ trạng thái runtime. Một test có thể:

- Thay đổi field mutable của bean singleton.
- Thay đổi cấu hình hoặc đăng ký thành phần trong context theo cách không thể khôi phục.
- Thay thế hoặc làm biến đổi một bean dùng chung.
- Đóng một tài nguyên do bean quản lý.
- Khiến context không còn đại diện cho trạng thái khởi tạo mà các test khác mong đợi.

Ví dụ, một bean lưu trạng thái tạm trong bộ nhớ:

~~~java
@Component
class FeatureRegistry {

    private final Map<String, Boolean> features = new HashMap<>();

    void enable(String name) {
        features.put(name, true);
    }

    boolean isEnabled(String name) {
        return features.getOrDefault(name, false);
    }
}
~~~

Nếu một test gọi enable("checkout"), test sau dùng cùng bean có thể nhìn thấy trạng thái đó. Khi trạng thái này không thể được reset một cách đáng tin cậy, có thể đánh dấu context dirty để Spring loại context khỏi cache và tạo context mới cho lần sử dụng tiếp theo.

Không phải mọi thay đổi dữ liệu đều cần @DirtiesContext. Nếu test chỉ thêm một bản ghi trong database và có thể rollback transaction hoặc dọn dữ liệu rõ ràng, hãy dùng cơ chế cô lập dữ liệu tương ứng. @DirtiesContext dành cho tình huống cần thay mới chính Spring context.

## 2. @DirtiesContext hoạt động như thế nào?

Annotation @DirtiesContext thông báo với Spring TestContext rằng context được dùng bởi test đã bị thay đổi và không nên tiếp tục được tái sử dụng từ cache.

Khi context bị đánh dấu dirty, Spring loại nó khỏi cache và đóng context. Quá trình đóng kích hoạt lifecycle của bean, chẳng hạn callback @PreDestroy, DisposableBean.destroy() hoặc phương thức destroy được cấu hình. Khi một test tiếp theo cần cùng cấu hình, Spring tạo lại context.

Có thể hình dung vòng đời như sau:

~~~text
Test cần ApplicationContext
          |
          v
   Tìm trong context cache
          |
     +----+----+
     |         |
    Có        Không
     |         |
     v         v
Dùng context  Tạo context mới
đã cache      và đưa vào cache
     |         |
     +----+----+
          |
          v
       Chạy test
          |
          v
   @DirtiesContext?
          |
     +----+----+
     |         |
    Không      Có
     |         |
     v         v
Giữ context   Đánh dấu dirty,
trong cache   loại khỏi cache,
              đóng context
~~~

Việc đóng context không có nghĩa toàn bộ JVM bị khởi động lại. Spring chỉ xử lý ApplicationContext tương ứng. Các static field, singleton do code tự quản lý bên ngoài Spring, dữ liệu database đã commit và trạng thái của dịch vụ từ xa không tự động được reset.

## 3. Đóng context theo từng test method

Khi đặt @DirtiesContext trên một test method, thuộc tính methodMode xác định thời điểm context bị đánh dấu dirty.

Hai chế độ chính:

| MethodMode | Thời điểm | Ý nghĩa |
|---|---|---|
| BEFORE_METHOD | Trước khi method chạy | Loại context hiện có khỏi cache để method bắt đầu với context mới |
| AFTER_METHOD | Sau khi method hoàn tất | Đóng context mà method vừa sử dụng để test tiếp theo phải tạo hoặc lấy context khác |

Giá trị mặc định của methodMode là AFTER_METHOD.

### 3.1. BEFORE_METHOD: đóng context trước method

Dùng BEFORE_METHOD khi test cần một context mới ngay từ đầu vì context có thể đã bị thay đổi bởi test chạy trước đó hoặc bởi một phần setup được thực hiện trước method.

~~~java
@SpringBootTest
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(
        methodMode = DirtiesContext.MethodMode.BEFORE_METHOD
    )
    void startsWithFreshFeatureRegistry() {
        assertFalse(featureRegistry.isEnabled("checkout"));
    }
}
~~~

Trình tự ở cấp test method là:

1. Spring xử lý chế độ BEFORE_METHOD và loại context cũ khỏi cache nếu context đó đang được sử dụng.
2. Spring chuẩn bị context mới cho test.
3. Các callback @BeforeEach được thực hiện.
4. Test method chạy.
5. Các callback @AfterEach được thực hiện.
6. Context mới vẫn có thể được giữ trong cache nếu không có chế độ đóng khác áp dụng.

BEFORE_METHOD bảo đảm method nhận một context mới tại thời điểm bắt đầu. Nó không tự đóng context mới sau khi method hoàn tất. Nếu method cũng làm bẩn context và cần đóng nó ngay sau khi chạy, có thể cân nhắc chế độ AFTER_METHOD cho kịch bản tương ứng hoặc thiết kế test class với chế độ phù hợp.

Một trường hợp khác là test cần xác nhận bean được tạo lại sau khi một test khác đã làm thay đổi context. Gắn BEFORE_METHOD vào method cần trạng thái mới sẽ thể hiện rõ ranh giới đó.

### 3.2. AFTER_METHOD: đóng context sau method

Đây là chế độ mặc định khi đặt @DirtiesContext trên method. Dùng nó khi method trực tiếp thay đổi trạng thái context và các test tiếp theo không nên tái sử dụng context đó.

~~~java
@SpringBootTest
class FeatureRegistryMutationTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void changesSharedFeatureRegistry() {
        featureRegistry.enable("checkout");
        assertTrue(featureRegistry.isEnabled("checkout"));
    }
}
~~~

Có thể viết ngắn hơn vì AFTER_METHOD là mặc định:

~~~java
@Test
@DirtiesContext
void changesApplicationContextState() {
    // Thực hiện thay đổi khiến context không thể tái sử dụng an toàn.
}
~~~

Trình tự:

1. Spring chuẩn bị hoặc lấy context từ cache.
2. Các callback @BeforeEach chạy.
3. Test method chạy.
4. Các callback @AfterEach chạy.
5. Spring xử lý listener sau test method, đánh dấu context dirty và đóng nó.
6. Test tiếp theo cần cấu hình tương ứng sẽ phải tạo context mới.

Đặt @DirtiesContext trên method giúp giới hạn tác động vào test thật sự làm bẩn context. Những method khác trong cùng class có thể tiếp tục dùng context cache nếu không có annotation hoặc chế độ khác yêu cầu đóng.

### 3.3. So sánh hai chế độ method

Giả sử test class có ba method A, B và C, tất cả dùng cùng một cấu hình context:

~~~text
@DirtiesContext(BEFORE_METHOD) trên B:

A: dùng context X
B: loại X -> tạo và dùng context Y
C: có thể dùng lại Y

@DirtiesContext(AFTER_METHOD) trên B:

A: dùng context X
B: dùng X -> đóng X sau B
C: tạo và dùng context Y
~~~

Đây là cách nhìn ở mức cache. Nếu một context tương đương đã được test class khác sử dụng, thao tác dirty cũng ảnh hưởng đến lần sử dụng sau của context đó trong cùng JVM.

Chọn BEFORE_METHOD khi chính method cần được bảo vệ khỏi trạng thái còn sót lại trước đó. Chọn AFTER_METHOD khi method là nơi tạo ra trạng thái khiến context không còn dùng được sau khi nó kết thúc.

## 4. Đóng context theo từng test class

Khi đặt @DirtiesContext trên class, thuộc tính classMode xác định thời điểm xử lý context trong vòng đời của cả lớp.

Spring cung cấp bốn chế độ:

| ClassMode | Thời điểm | Phạm vi |
|---|---|---|
| BEFORE_CLASS | Trước khi test class chạy | Đóng context trước toàn bộ test method của class |
| AFTER_CLASS | Sau khi test class hoàn tất | Đóng context sau tất cả test method của class |
| BEFORE_EACH_TEST_METHOD | Trước từng test method | Làm mới context trước mỗi method trong class |
| AFTER_EACH_TEST_METHOD | Sau từng test method | Đóng context sau mỗi method trong class |

Giá trị mặc định của classMode là AFTER_CLASS.

### 4.1. BEFORE_CLASS: làm sạch trước khi lớp bắt đầu

Chọn BEFORE_CLASS khi class cần bắt đầu với context mới, ví dụ vì một test class khác đã dùng chung cấu hình và có thể làm thay đổi context trước đó.

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_CLASS)
class IsolatedApplicationContextTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void startsWithExpectedRegistryState() {
        assertFalse(featureRegistry.isEnabled("checkout"));
    }
}
~~~

Spring xử lý chế độ này trước các callback khởi tạo của test class. Sau khi loại context cũ khỏi cache, context mới được tạo khi test cần đến nó.

BEFORE_CLASS có tác dụng tại ranh giới lớp. Nếu các method trong lớp làm thay đổi context, context đó vẫn có thể được dùng chung giữa các method của chính lớp cho đến khi một chế độ khác đánh dấu dirty. Nếu muốn mỗi method nhận context mới, dùng BEFORE_EACH_TEST_METHOD.

### 4.2. AFTER_CLASS: đóng sau khi toàn bộ lớp hoàn tất

AFTER_CLASS là chế độ mặc định khi đặt @DirtiesContext ở cấp class:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyConfigurationMutationTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void changesFeatureState() {
        featureRegistry.enable("legacy-mode");
    }

    @Test
    void checksAnotherFeature() {
        // Có thể dùng cùng context trong phạm vi class.
    }
}
~~~

Sau khi tất cả test method và callback kết thúc, Spring đánh dấu context dirty và đóng nó. Các test class chạy sau không thể lấy lại context đó từ cache.

Có thể rút gọn:

~~~java
@SpringBootTest
@DirtiesContext
class ContextMutationTest {
    // ...
}
~~~

Đặt annotation ở cấp class có nghĩa toàn bộ class chịu trách nhiệm về việc context cần được đóng sau khi lớp hoàn tất. Đây là lựa chọn phù hợp khi nhiều method trong lớp cùng sử dụng một context có trạng thái bị thay đổi trong quá trình kiểm thử.

### 4.3. BEFORE_EACH_TEST_METHOD: context mới trước mỗi method

Chọn chế độ này khi các test method cần được cô lập bằng một context mới trước khi bắt đầu:

~~~java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD
)
class IndependentContextTests {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void firstScenario() {
        assertFalse(featureRegistry.isEnabled("checkout"));
        featureRegistry.enable("checkout");
    }

    @Test
    void secondScenario() {
        assertFalse(featureRegistry.isEnabled("checkout"));
    }
}
~~~

Trước mỗi test method, Spring loại context hiện tại khỏi cache. Khi method cần context, Spring tạo một context mới. Do đó, trạng thái singleton được tạo lại cho từng method.

Chế độ này có thể hữu ích khi nhiều method đều làm thay đổi bean singleton và việc reset trạng thái thủ công không đáng tin cậy. Đổi lại, context có thể phải khởi tạo nhiều lần, khiến suite chậm hơn.

### 4.4. AFTER_EACH_TEST_METHOD: đóng sau mỗi method

Chế độ này đánh dấu context dirty sau từng test method:

~~~java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class ContextMutationPerTestTests {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void enablesCheckout() {
        featureRegistry.enable("checkout");
        assertTrue(featureRegistry.isEnabled("checkout"));
    }

    @Test
    void enablesSearch() {
        featureRegistry.enable("search");
        assertTrue(featureRegistry.isEnabled("search"));
    }
}
~~~

Sau mỗi method, Spring đóng context mà method vừa dùng. Method kế tiếp sẽ cần một context mới khi chạy.

### 4.5. Phân biệt hai chế độ theo từng method ở cấp class

BEFORE_EACH_TEST_METHOD và AFTER_EACH_TEST_METHOD đều hướng tới việc mỗi method chạy trong một context riêng. Điểm khác nhau nằm ở ranh giới đầu và cuối:

~~~text
BEFORE_EACH_TEST_METHOD

Trước A: loại context cũ -> tạo context A
Chạy A
Trước B: loại context A -> tạo context B
Chạy B
Trước C: loại context B -> tạo context C
Chạy C
Context C có thể còn trong cache sau class

AFTER_EACH_TEST_METHOD

Tạo hoặc lấy context A
Chạy A -> đóng context A
Tạo hoặc lấy context B
Chạy B -> đóng context B
Tạo hoặc lấy context C
Chạy C -> đóng context C
~~~

Ở chế độ BEFORE, context có thể được giữ lại sau method cuối cùng vì không có bước AFTER tương ứng. Ở chế độ AFTER, context của method cuối cũng bị đóng sau khi method hoàn tất. Điều này có thể ảnh hưởng đến test class khác dùng cùng cấu hình ngay sau đó.

## 5. Bảng chọn nhanh theo phạm vi và thời điểm

Hai thuộc tính methodMode và classMode có phạm vi áp dụng khác nhau:

| Đặt annotation ở đâu? | Thuộc tính | Chế độ | Kết quả |
|---|---|---|---|
| Test method | methodMode | BEFORE_METHOD | Context mới trước method được đánh dấu |
| Test method | methodMode | AFTER_METHOD | Context bị đóng sau method được đánh dấu |
| Test class | classMode | BEFORE_CLASS | Context bị làm mới trước khi class bắt đầu |
| Test class | classMode | AFTER_CLASS | Context bị đóng sau khi class hoàn tất |
| Test class | classMode | BEFORE_EACH_TEST_METHOD | Context mới trước từng method trong class |
| Test class | classMode | AFTER_EACH_TEST_METHOD | Context bị đóng sau từng method trong class |

Ví dụ:

~~~java
// Method-level: chọn thời điểm bằng methodMode.
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.BEFORE_METHOD)
void needsFreshContext() {
}

// Class-level: chọn thời điểm bằng classMode.
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextChangingTests {
}
~~~

Không dùng methodMode để mô tả chế độ cấp class hoặc classMode để mô tả một method riêng. Chọn thuộc tính theo vị trí annotation giúp ý định rõ ràng và tránh nhầm phạm vi.

## 6. Thứ tự với callback của JUnit Jupiter

Thời điểm Spring xử lý @DirtiesContext có quan hệ với lifecycle callback của JUnit. Với JUnit Jupiter được tích hợp qua SpringExtension, thứ tự thường gặp cho một test method là:

~~~text
Spring beforeTestClass
    |
    +-- BEFORE_CLASS nếu được cấu hình
    |
JUnit @BeforeAll
    |
    +-- BEFORE_EACH_TEST_METHOD nếu được cấu hình ở class
    |
Spring beforeTestMethod
    |
    +-- BEFORE_METHOD nếu được cấu hình ở method
    |
JUnit @BeforeEach
    |
JUnit @Test
    |
JUnit @AfterEach
    |
Spring afterTestMethod
    |
    +-- AFTER_METHOD nếu được cấu hình ở method
    +-- AFTER_EACH_TEST_METHOD nếu được cấu hình ở class
    |
JUnit @AfterAll
    |
Spring afterTestClass
    |
    +-- AFTER_CLASS nếu được cấu hình
~~~

Điều này có ý nghĩa thực tế:

- Với BEFORE_METHOD, context được làm mới trước @BeforeEach, vì vậy setup của test method nhận bean từ context mới.
- Với AFTER_METHOD, context được xử lý sau @AfterEach, nên callback dọn dẹp của test có thể vẫn sử dụng bean từ context vừa chạy.
- Với BEFORE_CLASS, context được xử lý ở ranh giới trước các callback khởi tạo của lớp.
- Với AFTER_CLASS, context được xử lý sau khi callback @AfterAll đã hoàn tất.

Các callback Spring được thực thi thông qua TestExecutionListener. Nếu dùng JUnit 4 hoặc TestNG, thứ tự tích hợp có thể được diễn đạt bằng lifecycle của framework tương ứng; ý nghĩa của các chế độ Spring vẫn là trước hoặc sau ranh giới method/class.

## 7. Ví dụ theo dõi bean bị thay đổi

Giả sử ứng dụng có bean singleton giữ trạng thái cấu hình runtime. Một test thay đổi trạng thái và cần Spring tạo bean mới cho test tiếp theo.

~~~java
@Component
class RuntimeSwitch {

    private boolean enabled;

    boolean isEnabled() {
        return enabled;
    }

    void enable() {
        enabled = true;
    }
}
~~~

Test có thể dùng AFTER_METHOD:

~~~java
@SpringJUnitConfig(RuntimeSwitchConfig.class)
class RuntimeSwitchTest {

    @Autowired
    private RuntimeSwitch runtimeSwitch;

    @Test
    @DirtiesContext
    void changesRuntimeSwitch() {
        runtimeSwitch.enable();
        assertTrue(runtimeSwitch.isEnabled());
    }

    @Test
    void startsWithDefaultSwitchState() {
        assertFalse(runtimeSwitch.isEnabled());
    }
}
~~~

Test đầu tiên đánh dấu context dirty sau khi chạy. Khi method thứ hai cần context với cùng cấu hình, Spring tạo context mới và bean RuntimeSwitch được khởi tạo lại.

Thứ tự test method không được bảo đảm chỉ dựa vào thứ tự xuất hiện trong source. Hai method trên vẫn độc lập: nếu method thứ hai chạy trước, nó nhận trạng thái mặc định; nếu chạy sau method đầu, context đã bị loại khỏi cache và được tạo lại.

Nếu chỉ một method cần context mới trước khi chạy, có thể dùng BEFORE_METHOD trên method đó. Nếu mọi method trong class đều cần context riêng, class-level BEFORE_EACH_TEST_METHOD hoặc AFTER_EACH_TEST_METHOD có thể diễn đạt chính sách rõ hơn.

## 8. @DirtiesContext và test class kế thừa

Spring TestContext hỗ trợ cấu hình test được kế thừa từ lớp cha. Khi @DirtiesContext được đặt trên lớp cha, các test class con có thể chịu ảnh hưởng theo chính sách kế thừa annotation và cấu hình test của JUnit/Spring.

Ví dụ:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
abstract class BaseContextMutationTest {
}

class PaymentFlowTest extends BaseContextMutationTest {

    @Test
    void changesPaymentConfiguration() {
        // ...
    }
}
~~~

Lớp cơ sở có thể gom chính sách chung cho một nhóm test. Tuy nhiên, nếu chỉ một test class con làm bẩn context, đặt annotation trên đúng lớp con sẽ giới hạn tác động tốt hơn.

Khi kế thừa test class, cần xem xét:

- Annotation ở lớp cha có được kế thừa theo chính sách annotation của nó hay không.
- Lớp con có thêm cấu hình làm thay đổi context cache key không.
- Chế độ dirty ở lớp cha có làm context bị đóng sau mỗi lớp con không.
- Các lớp con có thực sự cần cùng chính sách lifecycle hay không.

Đừng dùng một base test class lớn chỉ để gom annotation nếu các lớp con có vòng đời context khác nhau. Chính sách nên đặt ở cấp gần nhất với nhóm test thực sự chia sẻ yêu cầu đó.

## 9. Context hierarchy và hierarchyMode

Một số ứng dụng kiểm thử nhiều cấp ApplicationContext, ví dụ parent context chứa service chung và child context chứa thành phần web. Trong tình huống này, @DirtiesContext có thuộc tính hierarchyMode để điều khiển phạm vi loại context khỏi cache.

Hai lựa chọn là:

- EXHAUSTIVE (mặc định): dùng thuật toán loại các context liên quan trong hierarchy để tránh tái sử dụng một phần cây context không còn phù hợp.
- CURRENT_LEVEL: giới hạn thao tác dirty ở cấp context hiện tại trong hierarchy.

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS,
    hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL
)
class WebChildContextTest {
    // ...
}
~~~

Chỉ cần quan tâm hierarchyMode khi test thực sự dùng @ContextHierarchy hoặc có parent/child context. Với ứng dụng chỉ có một context, giữ mặc định thường là đủ. Chọn phạm vi quá rộng có thể khiến nhiều context phải khởi tạo lại; chọn phạm vi quá hẹp có thể giữ lại một context cha hoặc con không còn phù hợp với trạng thái test.

## 10. Phân biệt đóng context với rollback dữ liệu

@DirtiesContext quản lý vòng đời Spring ApplicationContext. Nó không thay thế transaction rollback và không xóa dữ liệu ở mọi hệ thống bên ngoài.

| Thay đổi trong test | Cơ chế thường phù hợp |
|---|---|
| Bean singleton bị thay đổi trạng thái không thể reset an toàn | @DirtiesContext |
| Bản ghi database được tạo trong transaction test | Transaction rollback |
| File tạm được tạo trong test | Dọn file trong lifecycle cleanup |
| Dữ liệu đã commit vào database dùng chung | Xóa dữ liệu bằng fixture/cleanup hoặc database riêng |
| Message đã gửi vào broker | Queue/topic thử nghiệm và cleanup phù hợp |
| Dịch vụ ngoài có trạng thái | Fake/mock hoặc môi trường dịch vụ thử nghiệm có thể reset |

Ví dụ một repository test có transaction:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void savesProduct() {
        Product product = repository.save(new Product("Keyboard"));
        repository.flush();

        assertTrue(repository.findById(product.getId()).isPresent());
    }
}
~~~

@DataJpaTest thường chạy trong transaction được rollback sau test. Trong trường hợp này, không cần đánh dấu context dirty chỉ vì test đã lưu một entity. Nếu test thay đổi một bean singleton hoặc làm hỏng cấu hình context, đó mới là vấn đề thuộc @DirtiesContext.

## 11. Chi phí và ảnh hưởng đến context cache

Đóng context khiến lần test tiếp theo cần cấu hình tương ứng phải khởi tạo context mới. Với một ứng dụng lớn, việc này có thể tốn nhiều giây hoặc lâu hơn tùy số lượng bean, kết nối database, server và tài nguyên khởi tạo.

Nếu một class có nhiều method và dùng BEFORE_EACH_TEST_METHOD hoặc AFTER_EACH_TEST_METHOD, context có thể được tạo lại nhiều lần. Nếu nhiều class cùng đánh dấu dirty một context tương đương, các class chạy sau cũng có thể mất cơ hội tái sử dụng cache.

Một số hệ quả cần tính đến:

- Thời gian chạy suite tăng khi có nhiều context bị loại.
- Các bean có callback khởi tạo hoặc đóng sẽ được chạy lại nhiều lần.
- Kết nối pool, embedded server hoặc tài nguyên gắn với context được tạo/đóng theo vòng đời đó.
- Test có thể phát hiện lỗi khởi tạo lặp lại mà một context dùng chung lâu dài che giấu.
- Nếu context đóng không hoàn tất do tài nguyên bị giữ, lỗi cleanup có thể xuất hiện sau test.

Không nên dùng @DirtiesContext như một cách reset mặc định cho mọi test. Nếu bean có trạng thái mutable, hãy cân nhắc thiết kế API reset dành cho test, tạo instance mới trong phạm vi cần thiết, dùng fake hoặc khôi phục trạng thái trong @AfterEach. Dùng dirty context khi chính context cần được thay mới.

## 12. Những lỗi thường gặp khi chọn mode

### 12.1. Dùng AFTER_CLASS nhưng mong mỗi method có context mới

AFTER_CLASS chỉ đóng context sau khi toàn bộ test class hoàn tất. Các method trong class có thể dùng chung một context. Nếu mỗi method cần context mới, chọn BEFORE_EACH_TEST_METHOD hoặc AFTER_EACH_TEST_METHOD.

### 12.2. Dùng BEFORE_CLASS nhưng mong context được đóng sau lớp

BEFORE_CLASS làm sạch ở đầu lớp. Context được tạo cho class vẫn có thể được giữ trong cache sau khi lớp kết thúc. Muốn đóng sau lớp, dùng AFTER_CLASS.

### 12.3. Gắn BEFORE_METHOD lên method làm bẩn context sau khi chạy

BEFORE_METHOD chỉ xử lý context trước method. Nếu method tự làm thay đổi context và cần loại nó sau khi chạy, hãy chọn AFTER_METHOD hoặc chính sách cấp class phù hợp.

### 12.4. Nghĩ rằng @DirtiesContext reset database

Context có thể chứa DataSource và connection pool, nhưng đóng context không tự rollback các transaction đã commit hoặc xóa dữ liệu do test ghi vào database dùng chung. Dùng transaction, database riêng hoặc cleanup dữ liệu theo đúng phạm vi.

### 12.5. Dùng dirty context để che lỗi chia sẻ trạng thái

Nếu nhiều test liên tục cần đóng context vì một bean giữ trạng thái, có thể thiết kế bean hoặc fixture chưa phù hợp. Hãy xem trạng thái có thể được reset qua API rõ ràng hoặc chuyển sang object có scope hẹp hơn không.

### 12.6. Đóng context quá sớm khi callback cleanup còn cần bean

Với AFTER_METHOD, Spring xử lý sau callback @AfterEach. Nếu cleanup được đặt ở nơi khác hoặc dùng listener tùy chỉnh, hãy kiểm tra thứ tự listener. Không giữ reference đến bean của context đã đóng rồi sử dụng ở test tiếp theo.

### 12.7. Gắn annotation ở base class không đúng phạm vi

Một annotation cấp class ở lớp cha có thể ảnh hưởng nhiều lớp con. Nếu chỉ một lớp có thay đổi context, hãy đặt chính sách ở lớp đó để tránh tạo context mới cho các test không cần.

### 12.8. Lạm dụng BEFORE_EACH_TEST_METHOD và AFTER_EACH_TEST_METHOD

Hai chế độ này có thể làm context khởi tạo lại cho từng method. Khi suite chậm, xem lại test nào thực sự làm context dirty và chuyển sang method-level annotation nếu chỉ một vài method cần.

## 13. Chẩn đoán khi context bị đóng hoặc khởi tạo lại

Khi thấy log cho biết Spring đang đóng hoặc tạo mới context, hãy xác định test nào đánh dấu dirty và mode nào đang áp dụng.

Có thể bật log cho TestContext và context cache trong cấu hình test:

~~~properties
logging.level.org.springframework.test.context=DEBUG
logging.level.org.springframework.context=INFO
~~~

Tùy phiên bản Spring và cấu hình logging, thông tin hữu ích có thể gồm:

- Test class/method đang chạy.
- Context được tìm thấy trong cache hay phải tạo mới.
- Context bị đánh dấu dirty.
- Context bị đóng và bean destroy callback được gọi.
- Lý do context không được tái sử dụng hoặc cấu hình cache khác nhau.

Khi điều tra, kiểm tra:

1. @DirtiesContext được đặt ở method, class hay base class?
2. methodMode hoặc classMode đang dùng giá trị nào?
3. Có nested test class hoặc class kế thừa làm annotation được áp dụng ở phạm vi khác dự kiến không?
4. Test có thực sự thay đổi ApplicationContext hay chỉ thay đổi dữ liệu bên ngoài?
5. Có callback cleanup nào vẫn dùng bean sau khi context đóng không?
6. Việc tạo lại context có làm lộ lỗi cấu hình hoặc phụ thuộc tài nguyên không ổn định không?

Nếu context liên tục bị tạo lại, hãy đọc log tại thời điểm test class/method bắt đầu và kết thúc. Điều đó thường giúp tìm annotation hoặc listener đã yêu cầu đóng context.

## 14. Ví dụ tổng hợp: chọn mode theo từng tình huống

Một test class có thể dùng chính sách class-level khi toàn bộ method làm thay đổi cùng một loại context:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ApplicationModeTests {

    @Autowired
    private RuntimeSwitch runtimeSwitch;

    @Test
    void enablesMaintenanceMode() {
        runtimeSwitch.enable();
        assertTrue(runtimeSwitch.isEnabled());
    }

    @Test
    void checksAnotherRuntimeSetting() {
        // Các test trong class dùng chung context theo thiết kế.
    }
}
~~~

Nếu chỉ một method làm thay đổi context, có thể giới hạn annotation:

~~~java
@SpringBootTest
class ApplicationModeTests {

    @Autowired
    private RuntimeSwitch runtimeSwitch;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void enablesMaintenanceMode() {
        runtimeSwitch.enable();
        assertTrue(runtimeSwitch.isEnabled());
    }

    @Test
    void checksDefaultRuntimeSetting() {
        assertFalse(runtimeSwitch.isEnabled());
    }
}
~~~

Nếu mọi method cần một context sạch trước khi chạy:

~~~java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD
)
class FreshContextForEveryMethodTests {

    @Autowired
    private RuntimeSwitch runtimeSwitch;

    @Test
    void firstMethodCanChangeState() {
        runtimeSwitch.enable();
    }

    @Test
    void secondMethodStartsWithDefaultState() {
        assertFalse(runtimeSwitch.isEnabled());
    }
}
~~~

Các ví dụ dùng RuntimeSwitch để minh họa trạng thái singleton. Trong ứng dụng thật, hãy cân nhắc liệu trạng thái đó có nên tồn tại trong bean singleton hay có thể được cô lập ở một thành phần nhỏ hơn.

## 15. Quy trình quyết định thời điểm đóng context

Trước khi thêm @DirtiesContext, hãy xác định chính xác phạm vi và thời điểm:

1. **Xác định thứ bị thay đổi.** Đó có phải trạng thái của Spring context/bean singleton hay chỉ là dữ liệu database, file hoặc dịch vụ ngoài?
2. **Xác định test tạo ra thay đổi.** Chỉ một method, mọi method trong class hay một class trước đó đã làm context không còn an toàn?
3. **Chọn ranh giới.** Dùng method-level khi chỉ một method cần xử lý; dùng class-level khi chính sách áp dụng cho toàn class.
4. **Chọn thời điểm.** BEFORE khi cần context mới trước khi chạy; AFTER khi cần đóng context sau khi test đã sử dụng và thay đổi nó.
5. **Tính đến callback.** Đảm bảo setup và cleanup chạy ở thời điểm mong muốn so với việc Spring đóng context.
6. **Đánh giá chi phí.** Context có phải khởi tạo lại nhiều lần không? Có thể reset trạng thái hẹp hơn không?
7. **Xác nhận test độc lập.** Chạy test method riêng và trong suite để chắc chắn kết quả không phụ thuộc thứ tự.

Có thể dùng bảng quyết định ngắn:

| Nhu cầu | Lựa chọn |
|---|---|
| Một method cần context mới trước khi chạy | @DirtiesContext(methodMode = BEFORE_METHOD) |
| Một method làm bẩn context sau khi chạy | @DirtiesContext trên method hoặc AFTER_METHOD |
| Một class cần context mới trước khi bắt đầu | classMode = BEFORE_CLASS |
| Một class làm bẩn context và cần đóng sau cùng | classMode = AFTER_CLASS |
| Mỗi method trong class cần context mới trước khi chạy | classMode = BEFORE_EACH_TEST_METHOD |
| Đóng context sau từng method trong class | classMode = AFTER_EACH_TEST_METHOD |

## Kết luận

@DirtiesContext cho phép chọn thời điểm Spring loại ApplicationContext khỏi cache và đóng nó. BEFORE_METHOD và AFTER_METHOD áp dụng cho một test method; BEFORE_CLASS, AFTER_CLASS, BEFORE_EACH_TEST_METHOD và AFTER_EACH_TEST_METHOD áp dụng cho test class. Chọn thời điểm theo nơi trạng thái bị thay đổi và nơi cần có context sạch giúp test độc lập, đồng thời tránh khởi tạo lại context nhiều hơn mức cần thiết.
