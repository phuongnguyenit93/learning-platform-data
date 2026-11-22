# @DirtiesContext khi kiểm thử làm hỏng trạng thái dùng chung

Spring TestContext Framework cache các `ApplicationContext` để nhiều bài kiểm thử có cùng cấu hình có thể dùng chung context đã khởi tạo. Cơ chế này giúp giảm thời gian chạy test, nhưng cũng có nghĩa các bean singleton và trạng thái nằm trong context có thể được giữ lại giữa nhiều test.

Nếu một bài kiểm thử làm thay đổi trạng thái của context theo cách các test sau không thể tiếp tục sử dụng an toàn, Spring cung cấp annotation `@DirtiesContext`. Annotation này đánh dấu context là không còn đáng tin cậy, yêu cầu Spring loại context khỏi cache và đóng context đó. Khi một test sau cần cùng cấu hình, Spring sẽ tạo một context mới.

## 1. Vì sao trạng thái dùng chung có thể làm test bị ảnh hưởng?

Trong một Spring `ApplicationContext`, bean singleton thường được tạo một lần và được chia sẻ cho các nơi sử dụng bean trong context đó. Nếu bean giữ trạng thái có thể thay đổi, một test có thể vô tình để lại trạng thái cho test chạy sau.

Ví dụ, một bean lưu danh sách tính năng được bật:

```java
@Component
public class FeatureRegistry {

    private final Set<String> enabledFeatures = new HashSet<>();

    public void enable(String feature) {
        enabledFeatures.add(feature);
    }

    public boolean isEnabled(String feature) {
        return enabledFeatures.contains(feature);
    }
}
```

Nếu Spring context được cache và hai test dùng chung bean này, test thứ nhất có thể thêm một feature. Test thứ hai sau đó nhìn thấy feature đó dù nó không hề chuẩn bị trạng thái này.

```text
Test A
  |
  | registry.enable("experimental")
  v
FeatureRegistry trong ApplicationContext
  |
  | trạng thái vẫn còn
  v
Test B
  |
  | isEnabled("experimental") == true
  v
Kết quả phụ thuộc test A đã chạy trước
```

Đây là một dạng rò rỉ trạng thái giữa các bài kiểm thử. Test B không còn độc lập: kết quả của nó phụ thuộc vào thứ tự hoặc những test khác đã chạy trước đó.

## 2. @DirtiesContext giải quyết điều gì?

`@DirtiesContext` đánh dấu `ApplicationContext` liên quan là dirty. Spring TestContext Framework loại context đó khỏi cache và đóng nó. Lần tiếp theo khi một test cần context có cùng cấu hình, Spring sẽ khởi tạo context mới.

Có thể dùng annotation trên test method:

```java
@SpringBootTest
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext
    void enablesTemporaryFeature() {
        featureRegistry.enable("experimental");

        assertTrue(featureRegistry.isEnabled("experimental"));
    }
}
```

Ở cấp method, mặc định Spring đánh dấu context dirty sau khi test method hoàn tất. Test có thể thay đổi bean trong lúc chạy; sau đó context được loại khỏi cache để những test cần context này không tiếp tục nhận trạng thái đã bị thay đổi.

Có thể viết rõ chế độ mặc định:

```java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void enablesTemporaryFeature() {
    // ...
}
```

Annotation cũng có thể đặt trên test class:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyConfigurationTest {
    // Các test trong class
}
```

Ở cấp class, mặc định Spring đánh dấu context dirty sau khi toàn bộ test method của class đã hoàn tất. Cách này hữu ích khi cả class có thể làm thay đổi trạng thái dùng chung và chỉ cần loại context sau khi class kết thúc.

## 3. Context được cache và tạo lại như thế nào?

Spring TestContext Framework lưu các context đã khởi tạo trong một cache. Cấu hình kiểm thử được dùng làm cơ sở xác định context có thể tái sử dụng hay không. Những test class có cấu hình tương đương có thể nhận cùng một context đã cache.

Khi `@DirtiesContext` được áp dụng, Spring loại context liên quan khỏi cache và đóng nó. Lần sử dụng tiếp theo không lấy lại instance đã bị đánh dấu dirty.

```text
Test class A
     |
     v
Tìm context trong cache
     |
     v
ApplicationContext C1
     |
     v
Test A thay đổi trạng thái dùng chung
     |
     v
@DirtiesContext đánh dấu C1 dirty
     |
     +----> Loại C1 khỏi cache
     |
     +----> Đóng C1
                 |
                 v
Test class B cần cùng cấu hình
                 |
                 v
          Không còn C1 trong cache
                 |
                 v
       Tạo ApplicationContext C2 mới
```

Context mới có các bean được khởi tạo lại theo cấu hình. Trạng thái nằm trong các instance bean của context cũ không được mang sang context mới.

Điều này không có nghĩa mọi test đều tạo một context mới. Spring vẫn tái sử dụng context giữa các test khi context chưa bị đánh dấu dirty và cấu hình cho phép dùng chung.

## 4. Các chế độ ở cấp test method

Khi đặt `@DirtiesContext` trên một test method, thuộc tính `methodMode` xác định thời điểm đánh dấu context dirty.

| MethodMode | Thời điểm | Mục đích |
|---|---|---|
| `BEFORE_METHOD` | Trước khi test method thực thi | Test cần bắt đầu với một context mới sau khi context trước đó có thể đã bị thay đổi |
| `AFTER_METHOD` | Sau khi test method thực thi | Test hiện tại làm thay đổi context và cần loại bỏ context sau khi hoàn tất |

`AFTER_METHOD` là giá trị mặc định ở cấp method.

Ví dụ:

```java
@SpringBootTest
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void enablesTemporaryFeature() {
        featureRegistry.enable("experimental");

        assertTrue(featureRegistry.isEnabled("experimental"));
    }

    @Test
    void startsWithoutExperimentalFeature() {
        assertFalse(featureRegistry.isEnabled("experimental"));
    }
}
```

Sau method đầu tiên, context bị loại khỏi cache. Khi method tiếp theo cần context, Spring tạo context mới và inject bean từ context mới vào test instance tương ứng. Vì vậy, registry bắt đầu với trạng thái ban đầu.

Dùng `BEFORE_METHOD` khi chính test hiện tại cần được bảo vệ khỏi context có thể đã bị thay đổi trước đó. Dùng `AFTER_METHOD` khi test hiện tại là nơi làm bẩn context và cần bảo đảm các test sau không tái sử dụng nó.

## 5. Các chế độ ở cấp test class

Khi đặt annotation trên class, thuộc tính `classMode` xác định thời điểm Spring đánh dấu context dirty.

| ClassMode | Thời điểm | Tình huống |
|---|---|---|
| `BEFORE_CLASS` | Trước khi test trong class bắt đầu | Class cần một context mới ngay từ đầu |
| `AFTER_CLASS` | Sau khi tất cả test method trong class kết thúc | Cả class có thể làm thay đổi context; đây là mặc định |
| `BEFORE_EACH_TEST_METHOD` | Trước từng test method | Mỗi method cần được chạy với context được làm mới |
| `AFTER_EACH_TEST_METHOD` | Sau từng test method | Mỗi method có thể làm bẩn context và cần loại nó ngay sau khi chạy |

Ví dụ làm mới context sau mỗi method:

```java
@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class FeatureRegistryIsolationTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void enablesFeatureA() {
        featureRegistry.enable("feature-a");

        assertTrue(featureRegistry.isEnabled("feature-a"));
    }

    @Test
    void enablesFeatureB() {
        featureRegistry.enable("feature-b");

        assertTrue(featureRegistry.isEnabled("feature-b"));
    }
}
```

Sau mỗi method, context bị loại khỏi cache. Mỗi test method tiếp theo sẽ cần context mới khi Spring chuẩn bị thực thi nó. Cách này giúp các method không chia sẻ trạng thái bean đã bị thay đổi bởi method trước.

Nếu chỉ cần làm sạch một lần sau khi class kết thúc, dùng `AFTER_CLASS` tiết kiệm chi phí hơn. Nếu chỉ một method làm thay đổi context, đặt annotation tại method đó thường diễn đạt phạm vi chính xác hơn.

## 6. Phân biệt method mode và class mode

Hai thuộc tính có mục đích tương tự nhưng áp dụng ở hai phạm vi khác nhau:

- `methodMode` được dùng khi `@DirtiesContext` đặt trên method.
- `classMode` được dùng khi `@DirtiesContext` đặt trên class.

Không cần khai báo cả hai trong cùng một annotation. Hãy chọn phạm vi gắn annotation theo nơi phát sinh thay đổi.

Ví dụ, nếu chỉ một method thay đổi bean singleton, có thể đặt:

```java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void changesSharedRegistry() {
    // ...
}
```

Nếu mọi test trong class đều có khả năng thay đổi context, có thể đặt ở class:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTest {
    // ...
}
```

Không nên đặt `@DirtiesContext` trên base test class một cách mặc định nếu chỉ một số lớp con thực sự làm thay đổi context. Annotation được kế thừa theo cơ chế annotation của Spring, nên phạm vi tác động có thể rộng hơn dự định. Hãy xác định rõ test class nào cần làm bẩn context.

## 7. Context hierarchy và hierarchyMode

Một số ứng dụng kiểm thử dùng nhiều tầng `ApplicationContext` có quan hệ cha–con, thường được khai báo bằng `@ContextHierarchy`. Trong trường hợp đó, việc đánh dấu một context dirty cần xác định phạm vi context nào trong hierarchy sẽ bị loại khỏi cache.

`@DirtiesContext` cung cấp thuộc tính `hierarchyMode`:

| HierarchyMode | Phạm vi |
|---|---|
| `EXHAUSTIVE` | Chế độ mặc định; loại context hiện tại và các context liên quan ở các cấp cha trong hierarchy |
| `CURRENT_LEVEL` | Chỉ loại context ở cấp hiện tại |

Ví dụ:

```java
@ContextHierarchy({
        @ContextConfiguration(classes = RootConfig.class),
        @ContextConfiguration(classes = WebConfig.class)
})
@SpringBootTest
class WebContextTest {

    @Test
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.AFTER_METHOD,
            hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL
    )
    void changesWebContext() {
        // Kiểm tra hành vi thuộc context cấp web
    }
}
```

Ví dụ minh họa lựa chọn phạm vi cho context hierarchy. Tên cấu hình và cách bootstrap thực tế phụ thuộc loại test mà dự án sử dụng.

Với `EXHAUSTIVE`, Spring xử lý việc loại context theo phạm vi đầy đủ của hierarchy từ cấp hiện tại lên các cấp cha. Điều này có thể khiến những context con khác phụ thuộc vào context cha cũng cần được tạo lại. Với `CURRENT_LEVEL`, Spring chỉ loại context ở cấp hiện tại và giữ các context cha trong cache.

Chỉ nên chọn `CURRENT_LEVEL` khi context cha vẫn hợp lệ và việc thay đổi chỉ ảnh hưởng context ở cấp hiện tại. Nếu trạng thái bị thay đổi nằm ở context cha hoặc có thể ảnh hưởng các context con khác, phạm vi mặc định `EXHAUSTIVE` an toàn hơn.

Nếu test chỉ dùng một `ApplicationContext` thông thường, không cần quan tâm đến thuộc tính này; để mặc định là đủ.

## 8. @DirtiesContext không thay thế transaction rollback

Một điểm quan trọng là `@DirtiesContext` quản lý vòng đời của Spring `ApplicationContext`. Nó không phải cơ chế rollback toàn bộ dữ liệu hoặc trạng thái bên ngoài ứng dụng.

Ví dụ, nếu test ghi một bản ghi vào database thật rồi đánh dấu context dirty, việc đóng context không tự động xóa bản ghi đó khỏi database. Database là tài nguyên độc lập với vòng đời bean trong context.

Với test dùng transaction do Spring Test quản lý, có thể dùng `@Transactional` để các thay đổi database được rollback sau test theo mặc định:

```java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void savesOrderInsideTestTransaction() {
        Order order = new Order("ORDER-42");

        orderRepository.save(order);

        assertTrue(orderRepository.findById("ORDER-42").isPresent());
    }
}
```

Trong cấu hình kiểm thử transaction tiêu chuẩn, Spring Test rollback transaction sau test method trừ khi được cấu hình commit hoặc kết thúc transaction theo cách khác. Cơ chế này phục vụ việc cô lập dữ liệu, không phải thay thế context cache.

Có thể phân biệt:

| Trạng thái cần làm sạch | Cơ chế phù hợp |
|---|---|
| Trạng thái mutable trong bean singleton của context | Reset bean hoặc dùng `@DirtiesContext` nếu cần tạo lại context |
| Thay đổi database trong test transaction | Transaction rollback |
| Dữ liệu database được commit hoặc nằm ngoài transaction test | SQL cleanup, repository cleanup hoặc chiến lược reset database |
| File, message, cache bên ngoài hoặc dịch vụ HTTP | Cơ chế cleanup riêng cho tài nguyên đó |
| Static field hoặc trạng thái JVM toàn cục | Khôi phục trạng thái bằng code test hoặc cơ chế quản lý riêng |

Khi test làm thay đổi nhiều loại tài nguyên, cần có chiến lược dọn dẹp riêng cho từng loại. Đánh dấu context dirty chỉ giải quyết phần trạng thái thuộc context.

## 9. Khi nào nên dùng @DirtiesContext?

Nên cân nhắc `@DirtiesContext` khi test thực sự làm thay đổi trạng thái của context và không thể khôi phục một cách đáng tin cậy.

Một số tình huống điển hình:

- Test đăng ký hoặc xóa bean động trong context.
- Test thay đổi cấu hình hoặc trạng thái nội bộ của context.
- Test làm thay đổi một singleton bean dùng chung và không có cách reset phù hợp.
- Test thay đổi trạng thái của thành phần Spring mà các test sau không thể tiếp tục sử dụng.
- Một test kiểm tra cấu hình đặc biệt làm context không còn đại diện cho cấu hình ban đầu.

Ví dụ, một test có thể thay đổi registry dùng chung:

```java
@SpringBootTest
class FeatureRegistryMutationTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext
    void registersTemporaryFeature() {
        featureRegistry.enable("temporary-feature");

        assertTrue(featureRegistry.isEnabled("temporary-feature"));
    }
}
```

Sau method này, Spring loại context khỏi cache. Các test khác dùng cùng cấu hình sẽ được cung cấp context mới khi cần.

Nếu bean có phương thức reset an toàn và test có thể gọi nó trong `@AfterEach`, việc reset trực tiếp thường nhanh hơn việc đóng và tạo lại toàn bộ context. `@DirtiesContext` phù hợp khi trạng thái đã thay đổi khiến context không còn đáng tin cậy, hoặc việc khôi phục từng thành phần quá phức tạp và dễ bỏ sót.

## 10. Khi nào không nên dùng @DirtiesContext?

Không nên dùng annotation này chỉ vì muốn mọi test bắt đầu với một context mới. Việc tạo lại context có thể tốn nhiều thời gian vì Spring phải nạp cấu hình, tạo bean, kết nối tài nguyên và thực hiện các bước khởi tạo liên quan.

Các trường hợp thường không cần `@DirtiesContext`:

**Fixture cục bộ bị thay đổi.** Nếu test chỉ thay đổi một object được tạo trong method, object đó sẽ không được chia sẻ với test khác. Không cần loại toàn bộ context.

**Mock được reset hoặc tạo mới đúng phạm vi.** Nếu test dùng mock riêng cho từng test instance hoặc có cơ chế reset rõ ràng, không cần đánh dấu context dirty chỉ vì mock đã nhận lời gọi.

**Database cần rollback.** Hãy dùng transaction test hoặc cleanup dữ liệu. Đóng context không đồng nghĩa xóa dữ liệu đã ghi.

**Bean có thể khôi phục an toàn.** Nếu có thể reset trạng thái bean bằng một thao tác rõ ràng trong `@AfterEach`, reset trực tiếp thường ít tốn kém hơn.

**Chỉ muốn tránh phụ thuộc thứ tự chạy.** Trước tiên hãy làm fixture và trạng thái test độc lập. Dùng `@DirtiesContext` cho mọi class có thể che giấu việc thiết kế test đang chia sẻ trạng thái không cần thiết.

## 11. Tác động đến hiệu năng của test suite

Spring context thường là một trong những phần tốn thời gian nhất của integration test. Cache giúp tránh tạo lại context khi nhiều test class có cùng cấu hình.

Khi dùng `@DirtiesContext`, context bị loại khỏi cache. Nếu nhiều test class đánh dấu cùng context dirty, Spring phải tạo context mới nhiều lần. Các bước khởi động bean, kết nối database, khởi tạo client và cấu hình có thể lặp lại.

Ví dụ:

```text
Không dùng @DirtiesContext:
  Test A ----+
  Test B ----+----> Dùng chung ApplicationContext C1
  Test C ----+

Dùng @DirtiesContext sau từng class:
  Test A ---------> C1 ----> đóng
  Test B ---------> C2 ----> đóng
  Test C ---------> C3 ----> đóng
```

Sơ đồ minh họa trường hợp các test có cấu hình tương đương. Khi context không bị đánh dấu dirty, Spring có thể tái sử dụng C1. Khi từng class làm dirty context, các lần chạy tiếp theo phải tạo context mới.

Nếu test suite có nhiều `@DirtiesContext`, thời gian chạy có thể tăng đáng kể. Hãy giới hạn annotation ở đúng test method hoặc class làm thay đổi context, và chọn mode phù hợp với thời điểm cần loại context.

Không nên xóa `@DirtiesContext` chỉ để làm suite chạy nhanh hơn nếu test thực sự làm hỏng context. Thay vào đó, hãy xem có thể reset trạng thái bean hoặc tách tài nguyên mutable ra khỏi context dùng chung hay không.

## 12. Kết hợp với test inheritance

Khi các test class kế thừa từ một base class có cấu hình Spring, cần chú ý annotation `@DirtiesContext` có thể ảnh hưởng đến các test class dùng chung cấu hình hoặc context hierarchy.

Ví dụ:

```java
@SpringBootTest
abstract class BaseIntegrationTest {

    @Autowired
    protected FeatureRegistry featureRegistry;
}

class FeatureReadTest extends BaseIntegrationTest {

    @Test
    void readsDefaultFeature() {
        assertFalse(featureRegistry.isEnabled("experimental"));
    }
}

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class FeatureMutationTest extends BaseIntegrationTest {

    @Test
    void enablesFeature() {
        featureRegistry.enable("experimental");

        assertTrue(featureRegistry.isEnabled("experimental"));
    }
}
```

Test class làm thay đổi trạng thái được đánh dấu dirty sau khi hoàn tất. Test class khác dùng cùng cấu hình sẽ cần context hợp lệ khi chạy. Spring có thể tạo context mới nếu context trước đã bị loại khỏi cache.

Nên đặt annotation tại lớp thực sự làm thay đổi context. Nếu đặt trên base class, các lớp con có thể cùng chịu tác động và làm tăng số lần khởi tạo context ngoài dự kiến.

## 13. Những lỗi thường gặp khi sử dụng @DirtiesContext

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test sau nhìn thấy trạng thái bean từ test trước | Context được tái sử dụng và bean giữ trạng thái mutable | Reset bean hoặc đánh dấu context dirty tại test làm thay đổi |
| Test suite chạy chậm sau khi thêm annotation | Context bị loại khỏi cache quá thường xuyên | Thu hẹp phạm vi annotation và chọn mode phù hợp |
| Dữ liệu database vẫn tồn tại sau khi context bị đóng | Context reset không rollback database đã commit | Dùng transaction rollback hoặc cleanup dữ liệu |
| Test vẫn thấy static state cũ | Static field nằm ngoài ApplicationContext | Khôi phục static state riêng |
| Nhiều test class phải khởi tạo lại context | Annotation đặt ở base class hoặc context hierarchy rộng | Kiểm tra vị trí annotation và hierarchyMode |
| Test không bắt đầu với context mới như mong đợi | Chọn nhầm methodMode hoặc classMode | Xác định chính xác thời điểm cần loại context |
| Bean cha/con trong context hierarchy bị khởi tạo lại ngoài dự kiến | Phạm vi mặc định EXHAUSTIVE ảnh hưởng context cha | Cân nhắc CURRENT_LEVEL nếu chỉ context hiện tại bị thay đổi |
| Test vẫn phụ thuộc thứ tự dù đã dùng annotation | Trạng thái nằm ở tài nguyên bên ngoài hoặc cơ chế cleanup khác chưa có | Xây dựng cleanup riêng cho từng tài nguyên |

Khi chẩn đoán, hãy xác định trạng thái bị thay đổi nằm ở đâu: trong bean thuộc context, trong database, trong static field hay ở dịch vụ bên ngoài. Sau đó chọn cơ chế làm sạch đúng với vòng đời của trạng thái đó.

## 14. Cách lựa chọn mode trong thực tế

Có thể chọn mode bằng cách trả lời hai câu hỏi: phạm vi test nào làm bẩn context, và thời điểm nào cần loại context?

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Một method làm bẩn context sau khi chạy | `@DirtiesContext(methodMode = AFTER_METHOD)` |
| Một method cần context mới trước khi chạy | `@DirtiesContext(methodMode = BEFORE_METHOD)` |
| Cả class làm bẩn context và chỉ cần loại sau class | `@DirtiesContext(classMode = AFTER_CLASS)` |
| Mỗi method trong class cần context mới sau khi chạy | `@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)` |
| Mỗi method phải bắt đầu sau một lần loại context | `@DirtiesContext(classMode = BEFORE_EACH_TEST_METHOD)` |
| Class cần loại context cũ trước khi bắt đầu | `@DirtiesContext(classMode = BEFORE_CLASS)` |
| Chỉ một context trong hierarchy bị thay đổi | Cân nhắc `hierarchyMode = CURRENT_LEVEL` |
| Context cha cũng có thể bị ảnh hưởng | Dùng mặc định `hierarchyMode = EXHAUSTIVE` |

Ví dụ, nếu một method duy nhất thêm bean hoặc thay đổi trạng thái singleton mà không thể reset, gắn annotation trên method thường là đủ. Nếu toàn bộ class là một nhóm test chuyên thao tác cấu hình và context cần được loại sau mỗi method, class-level `AFTER_EACH_TEST_METHOD` thể hiện ý định rõ hơn.

## 15. Quy trình điều tra khi test làm hỏng trạng thái dùng chung

Khi một test chỉ thất bại nếu chạy sau test khác, hãy lần theo trạng thái dùng chung trước khi thêm `@DirtiesContext`:

1. **Tái hiện vấn đề:** chạy test riêng lẻ và chạy cùng test suite để xác định có phụ thuộc thứ tự hay không.
2. **Xác định context có được dùng chung:** kiểm tra các test class có cấu hình Spring tương đương và có thể dùng cùng cache entry.
3. **Tìm bean hoặc tài nguyên mutable:** xem singleton, static state, cache, registry hoặc listener nào đã bị thay đổi.
4. **Xác định phạm vi thay đổi:** chỉ một method, cả class hay context hierarchy.
5. **Chọn cách khôi phục:** reset bean nếu có thể khôi phục an toàn; dùng `@DirtiesContext` nếu context không còn đáng tin cậy.
6. **Chọn thời điểm:** method mode hoặc class mode phải phản ánh lúc context cần bị loại.
7. **Kiểm tra tài nguyên ngoài context:** xác nhận database, file, message và dịch vụ bên ngoài có cleanup riêng.
8. **Chạy lại theo thứ tự khác:** bảo đảm kết quả không còn phụ thuộc vào test chạy trước.

Một bài test đáng tin cậy nên tự chuẩn bị trạng thái mà nó cần và không để lại tác động ngoài phạm vi dự kiến. `@DirtiesContext` là công cụ bảo vệ các test sau khi một bài test đã làm thay đổi context, đồng thời giúp Spring loại bỏ và tạo lại context khi cần. Dùng đúng phạm vi và thời điểm sẽ giữ được tính độc lập của test mà không làm mất lợi ích của cơ chế context caching.

