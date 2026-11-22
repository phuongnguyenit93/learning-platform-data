# Phạm vi hierarchyMode khi làm bẩn context phân cấp

Spring TestContext Framework lưu các `ApplicationContext` đã khởi tạo trong một cache để những test có cùng cấu hình có thể dùng lại context. Khi một test làm thay đổi trạng thái của context và đánh dấu nó bằng `@DirtiesContext`, Spring loại context khỏi cache và đóng nó. Ở lần chạy sau, test cần cấu hình đó sẽ được tạo context mới.

Với một context đơn, việc loại bỏ khá dễ hiểu. Với ứng dụng có nhiều tầng context được khai báo bằng `@ContextHierarchy`, một context có thể là cha của nhiều context con và các test class khác nhau có thể dùng chung một phần cây đó. Thuộc tính `hierarchyMode` của `@DirtiesContext` quyết định phạm vi cây context bị loại khỏi cache. Hai giá trị là `EXHAUSTIVE` và `CURRENT_LEVEL`; mặc định là `EXHAUSTIVE`.

## 1. Context hierarchy và cache của Spring TestContext

Một context hierarchy là cấu trúc `ApplicationContext` cha-con. Context con có thể truy cập bean ở context cha, trong khi context cha không truy cập ngược các bean chỉ tồn tại trong context con.

Một ứng dụng web có thể chia cấu hình thành context gốc chứa service, repository và các bean dùng chung, cùng context con chứa controller, handler mapping hoặc cấu hình web riêng. Spring TestContext biểu diễn cấu trúc này bằng `@ContextHierarchy` với nhiều khai báo `@ContextConfiguration`.

```java
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class WebIntegrationTests {
    // Test sử dụng cả root context và web child context.
}
```

Trong ví dụ, `WebConfig` tạo context con có `RootConfig` làm context cha. Các bean ở `WebConfig` có thể sử dụng bean từ `RootConfig`.

Khi nhiều test class dùng chung cùng cấu hình cha, Spring có thể tái sử dụng parent context trong cache. Ví dụ, một nhóm test MVC và một nhóm test API có thể có hai child context khác nhau nhưng cùng dùng một root context:

```text
                    Root context
                  (cấu hình dùng chung)
                         |
              +----------+----------+
              |                     |
              v                     v
         MVC child              API child
         (test MVC)             (test API)
              |
              v
       MVC feature child
```

Nếu test làm bẩn root context, các context con dựa vào root đó cũng có thể không còn an toàn để tái sử dụng. Nếu test chỉ làm bẩn một child context, việc xóa cả root và nhánh khác có thể khiến Spring phải khởi tạo lại nhiều context không bị ảnh hưởng. `hierarchyMode` giúp lựa chọn phạm vi xử lý phù hợp.

## 2. @DirtiesContext làm gì?

`@DirtiesContext` thông báo rằng một test đã làm thay đổi hoặc làm hỏng trạng thái của `ApplicationContext`, ví dụ thay đổi trạng thái singleton bean theo cách có thể ảnh hưởng test khác. Spring TestContext sẽ loại context theo cấu hình khỏi cache và đóng context đó.

Annotation có thể được đặt trên test method hoặc test class. Các thuộc tính điều khiển thời điểm và phạm vi có vai trò riêng:

| Thuộc tính | Điều khiển | Giá trị thường dùng |
|---|---|---|
| `methodMode` | Thời điểm làm bẩn context khi annotation đặt trên method | `BEFORE_METHOD`, `AFTER_METHOD` |
| `classMode` | Thời điểm làm bẩn context khi annotation đặt trên class | `BEFORE_CLASS`, `BEFORE_EACH_TEST_METHOD`, `AFTER_EACH_TEST_METHOD`, `AFTER_CLASS` |
| `hierarchyMode` | Phạm vi context hierarchy bị loại khỏi cache | `EXHAUSTIVE`, `CURRENT_LEVEL` |

Nếu đặt `@DirtiesContext` trên method, mặc định là `AFTER_METHOD`. Nếu đặt trên class, mặc định là `AFTER_CLASS`. `hierarchyMode` không thay đổi thời điểm làm bẩn; nó chỉ quyết định phạm vi cây context bị xóa khi hành động đó diễn ra.

Ví dụ làm bẩn context sau một test method:

```java
@Test
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.AFTER_METHOD,
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
void testThatChangesChildContextState() {
    // Thay đổi trạng thái context và cần loại child context khỏi cache.
}
```

Vì `AFTER_METHOD` là mặc định của annotation đặt trên method, có thể viết ngắn hơn:

```java
@Test
@DirtiesContext(hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
void testThatChangesChildContextState() {
    // ...
}
```

## 3. EXHAUSTIVE: xóa toàn bộ nhánh có ancestor chung

`DirtiesContext.HierarchyMode.EXHAUSTIVE` là chế độ mặc định. Thuật toán này xác định một ancestor context chung với hierarchy của test hiện tại, sau đó loại khỏi cache và đóng tất cả `ApplicationContext` nằm trong sub-hierarchy của ancestor chung đó.

Phạm vi này bao gồm:

- Context ở mức ancestor chung.
- Context hiện tại của test.
- Các context con nằm dưới context hiện tại.
- Các context thuộc hierarchy khác nhưng cùng chia sẻ ancestor chung.

Với cây ở phần trước, nếu test MVC làm bẩn context và `EXHAUSTIVE` được dùng, phạm vi có thể bao gồm toàn bộ cây:

```text
                    Root context
                         X
              +----------+----------+
              X                     X
              v                     v
         MVC child              API child
              X
              v
       MVC feature child
```

Ký hiệu `X` biểu thị context bị loại khỏi cache và đóng. Khi một test trong nhánh MVC dùng chế độ mặc định, nhánh API cũng có thể bị loại vì nó chia sẻ root context với test hiện tại.

### 3.1. Khi nào EXHAUSTIVE phù hợp?

Dùng `EXHAUSTIVE` khi trạng thái bị thay đổi có thể ảnh hưởng đến ancestor context hoặc nhiều nhánh con cùng dùng ancestor đó. Ví dụ:

- Test thay đổi singleton bean nằm trong root context.
- Test thay đổi cấu hình hoặc trạng thái dùng chung mà các child context khác phụ thuộc.
- Test làm thay đổi cấu trúc bean hoặc tài nguyên gắn với parent context.
- Không thể xác định chắc chắn thay đổi chỉ giới hạn trong một child context.

Vì đây là chế độ mặc định, chỉ cần khai báo `@DirtiesContext` là Spring áp dụng thuật toán exhaustive:

```java
@Test
@DirtiesContext
void modifiesSharedParentState() {
    // Thao tác làm thay đổi trạng thái dùng chung của hierarchy.
}
```

Ưu điểm là phạm vi làm sạch rộng, giảm nguy cơ một context con tiếp tục sử dụng parent đã bị thay đổi. Chi phí là các test ở nhánh khác có thể phải khởi tạo lại context dù bản thân nhánh đó không bị test hiện tại tác động.

## 4. CURRENT_LEVEL: xóa từ mức hiện tại trở xuống

`DirtiesContext.HierarchyMode.CURRENT_LEVEL` chỉ loại context ở mức thấp nhất của hierarchy mà test hiện tại nhìn thấy, cùng tất cả context nằm trong các sub-hierarchy của mức đó. Các ancestor ở phía trên và các nhánh ngang hàng không bị loại bởi thao tác này.

Trong ví dụ MVC/API, nếu test hiện tại nhìn thấy root và MVC child, mức thấp nhất mà test nhìn thấy là MVC child. Khi dùng `CURRENT_LEVEL`, kết quả như sau:

```text
                    Root context
                         |
              +----------+----------+
              |                     |
              v                     v
         MVC child              API child
              X
              v
       MVC feature child
              X
```

MVC child và các context con của nó bị đóng và xóa khỏi cache. Root context vẫn được giữ lại, và API child vẫn có thể tiếp tục dùng root context đang được cache.

### 4.1. Ví dụ khai báo CURRENT_LEVEL

```java
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class BaseWebTests {
    // Cấu hình hierarchy được kế thừa bởi test class con.
}

class ExtendedWebTests extends BaseWebTests {

    @Test
    @DirtiesContext(
            hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
    void dirtiesOnlyTheWebBranch() {
        // Thay đổi trạng thái chỉ thuộc web child context.
    }
}
```

Trong trường hợp này, test nhìn thấy hierarchy gồm root và web child. Mức hiện tại là web child, nên `CURRENT_LEVEL` giữ root và loại web child cùng các context con của nó.

### 4.2. Khi nào CURRENT_LEVEL phù hợp?

Dùng `CURRENT_LEVEL` khi thay đổi được cô lập ở context hiện tại hoặc nhánh con của nó, còn parent context vẫn hợp lệ và có thể được tái sử dụng. Ví dụ:

- Test thay đổi singleton bean chỉ được khai báo trong web child context.
- Test làm thay đổi state của một handler hoặc component thuộc child context.
- Nhiều test hierarchy chia sẻ root context ổn định nhưng có child context riêng.
- Muốn tránh khởi tạo lại các context ở nhánh khác khi chúng không bị ảnh hưởng.

Không nên chọn `CURRENT_LEVEL` chỉ để làm test chạy nhanh hơn nếu test đã thay đổi parent context. Khi parent bị bẩn nhưng vẫn được giữ trong cache, các context con được tạo từ parent đó có thể tiếp tục quan sát trạng thái sai. Hãy chọn phạm vi theo nơi phát sinh thay đổi và những context phụ thuộc vào nó.

## 5. So sánh hai thuật toán bằng cùng một cây context

Giả sử có một root context dùng chung, một MVC child và một API child. MVC child còn có một feature child.

| Context | `EXHAUSTIVE` khi test ở MVC child | `CURRENT_LEVEL` khi test ở MVC child |
|---|---|---|
| Root context | Bị xóa | Được giữ lại |
| MVC child hiện tại | Bị xóa | Bị xóa |
| MVC feature child | Bị xóa | Bị xóa |
| API child cùng root | Bị xóa | Được giữ lại |

Sự khác biệt chính nằm ở ancestor chung và các nhánh ngang hàng. `CURRENT_LEVEL` bắt đầu từ context thấp nhất mà test nhìn thấy rồi xóa các hậu duệ của nó. `EXHAUSTIVE` tìm ancestor chung của các hierarchy liên quan và xóa toàn bộ sub-hierarchy bên dưới ancestor đó.

Nếu test chỉ có một context, không có cây cha-con để phân biệt hai thuật toán; `hierarchyMode` chủ yếu có ý nghĩa khi dùng `@ContextHierarchy`.

## 6. Xác định “current level” trong test class hierarchy

Current level không đơn giản là class đang chứa method test. Nó là `ApplicationContext` ở mức thấp nhất trong hierarchy mà test hiện tại có thể nhìn thấy.

Ví dụ:

```java
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class),
    @ContextConfiguration(name = "feature", classes = FeatureConfig.class)
})
abstract class BaseFeatureTests {
}

class FeatureControllerTests extends BaseFeatureTests {

    @Test
    @DirtiesContext(hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
    void dirtiesFeatureContext() {
        // Test nhìn thấy root -> web -> feature.
    }
}
```

Test nhìn thấy ba mức. `feature` là mức thấp nhất, do đó `CURRENT_LEVEL` loại feature context và mọi context nằm dưới feature. Root và web context vẫn được cache.

Nếu một test class chỉ khai báo hoặc kế thừa đến mức `web`, thì `web` trở thành current level đối với test đó. Vì vậy, cùng một `hierarchyMode = CURRENT_LEVEL` có thể có phạm vi khác nhau tùy hierarchy mà test class nhìn thấy.

Khi test class kế thừa cấu hình từ base class, cần đọc toàn bộ cấu hình `@ContextHierarchy` có hiệu lực cho class con. Đừng xác định current level chỉ bằng annotation được viết trực tiếp trên class con.

## 7. Kết hợp hierarchyMode với methodMode và classMode

`hierarchyMode` chỉ xác định phạm vi xóa cache. Thời điểm xóa vẫn do `methodMode` hoặc `classMode` quyết định.

### 7.1. Làm bẩn sau một test method

```java
@Test
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.AFTER_METHOD,
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
void resetsChildContextAfterThisTest() {
    // Thay đổi trạng thái trong child context.
}
```

Test hiện tại chạy xong thì child context và các hậu duệ của nó bị loại khỏi cache. Test sau cần cùng child configuration sẽ tạo context mới; parent có thể được tái sử dụng.

### 7.2. Làm bẩn trước một test method

```java
@Test
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.BEFORE_METHOD,
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
void startsWithFreshChildContext() {
    // Test bắt đầu với child context được tạo lại.
}
```

Chế độ này hữu ích khi cần đảm bảo context đã bị test trước làm thay đổi được loại bỏ trước khi method hiện tại chạy. Nó không tự dọn database hoặc trạng thái bên ngoài ApplicationContext.

### 7.3. Làm bẩn sau mỗi method trong class

```java
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD,
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
class MutableChildContextTests {

    @Test
    void firstTest() {
        // ...
    }

    @Test
    void secondTest() {
        // ...
    }
}
```

Sau mỗi method, Spring loại current level cùng các hậu duệ. Method tiếp theo cần context đó sẽ khởi tạo lại child context. Cách này có thể tốn thời gian nếu class có nhiều test; chỉ dùng khi mỗi method thực sự làm bẩn context.

### 7.4. Làm bẩn sau class

```java
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS,
        hierarchyMode = DirtiesContext.HierarchyMode.EXHAUSTIVE)
class SharedContextMutationTests {
    // Các test làm thay đổi trạng thái dùng chung trong hierarchy.
}
```

Sau khi class hoàn tất, Spring loại các context theo thuật toán exhaustive. Cấu hình thời điểm và phạm vi nên phản ánh đúng nơi xảy ra thay đổi và các test khác bị ảnh hưởng.

## 8. Ví dụ về hai test hierarchy chia sẻ parent

Giả sử ứng dụng có một root context chứa service và repository, còn các lớp test web và API dùng cấu hình con riêng.

```java
@Configuration
class RootConfig {
    @Bean
    SharedService sharedService() {
        return new SharedService();
    }
}

@Configuration
class MvcConfig {
    @Bean
    MvcController mvcController(SharedService service) {
        return new MvcController(service);
    }
}

@Configuration
class ApiConfig {
    @Bean
    ApiHandler apiHandler(SharedService service) {
        return new ApiHandler(service);
    }
}
```

Hai test hierarchy có thể khai báo cùng root configuration:

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "mvc", classes = MvcConfig.class)
})
class MvcIntegrationTests {
}

@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "api", classes = ApiConfig.class)
})
class ApiIntegrationTests {
}
```

Khi cấu hình root giống nhau, TestContext có thể dùng chung root context trong cache. Nếu một test ở `MvcIntegrationTests` chỉ làm thay đổi bean riêng của MVC child, `CURRENT_LEVEL` giúp giữ root và API child. Nếu test làm thay đổi `SharedService` hoặc trạng thái chung trong root, `EXHAUSTIVE` an toàn hơn vì loại root và mọi context con trong các hierarchy chia sẻ ancestor đó.

Các lớp cấu hình trong ví dụ là minh họa. Để Spring nhận đúng hierarchy, các context configuration phải được khai báo với parent-child relationship phù hợp và có metadata tương thích để cache nhận diện phần root dùng chung.

## 9. Điều hierarchyMode không làm

`hierarchyMode` chỉ điều khiển việc loại `ApplicationContext` khỏi cache và đóng các context thuộc phạm vi đã chọn. Nó không thay thế cơ chế dọn dẹp cho các tài nguyên nằm ngoài vòng đời context.

Ví dụ, các hoạt động sau cần được quản lý riêng:

- Xóa bản ghi trong database hoặc rollback transaction phù hợp.
- Dừng container, server hoặc process do test khởi động.
- Xóa file tạm và thư mục test tạo ra.
- Khôi phục system property, system environment giả lập hoặc trạng thái static.
- Reset cache của thư viện bên ngoài hoặc tài nguyên dùng chung.

Đóng `ApplicationContext` có thể gọi callback hủy bean và giải phóng các tài nguyên do bean quản lý nếu chúng được cấu hình đúng. Tuy nhiên, không thể giả định mọi thay đổi bên ngoài context tự động được hoàn tác.

`@DirtiesContext` cũng không phải cách mặc định để làm sạch dữ liệu test. Nếu một test chỉ thay đổi dữ liệu database trong transaction được quản lý đúng, rollback hoặc fixture cleanup thường phù hợp hơn việc đóng và dựng lại toàn bộ context.

## 10. Ảnh hưởng đến tốc độ và độ ổn định của bộ test

Mỗi context bị loại khỏi cache có thể phải được tạo lại ở test tiếp theo. Quá trình này có thể bao gồm đọc cấu hình, tạo bean, khởi tạo connection pool, dựng server mock hoặc kết nối tới tài nguyên tích hợp.

`EXHAUSTIVE` có phạm vi rộng hơn, nên có thể khiến nhiều test ở các nhánh khác phải khởi tạo lại context. Điều đó làm tăng thời gian chạy, nhưng giúp loại bỏ các context phụ thuộc vào ancestor có khả năng đã bị thay đổi.

`CURRENT_LEVEL` có thể giữ lại parent và các nhánh ngang hàng, nhờ đó giảm số context phải tạo lại. Đổi lại, test phải bảo đảm các thay đổi thật sự chỉ giới hạn ở current level và hậu duệ của nó. Nếu thay đổi chạm tới parent mà parent vẫn được giữ trong cache, test sau có thể nhận trạng thái cũ hoặc sai.

Không nên chọn chế độ chỉ dựa vào tốc độ. Trước tiên cần xác định bean hoặc cấu hình bị thay đổi nằm ở context nào, sau đó xác định những context nào phụ thuộc vào nó. Phạm vi xóa cache phải bao phủ tất cả context có thể bị ảnh hưởng.

## 11. Những lỗi thường gặp

**Nghĩ CURRENT_LEVEL chỉ xóa đúng một context.** Thuật toán còn xóa tất cả context trong các sub-hierarchy của current level. Nếu child có nhiều tầng con, chúng cũng bị loại.

**Nghĩ EXHAUSTIVE chỉ xóa parent và nhánh hiện tại.** Thuật toán exhaustive còn bao gồm các hierarchy khác chia sẻ ancestor chung với test hiện tại. Một child context ở nhánh ngang hàng cũng có thể bị đóng.

**Dùng CURRENT_LEVEL sau khi thay đổi bean ở parent.** Parent vẫn có thể nằm trong cache và được các child context tiếp theo sử dụng. Hãy dùng phạm vi đủ rộng khi parent bị ảnh hưởng.

**Nhầm hierarchyMode với classMode hoặc methodMode.** `hierarchyMode` quyết định phạm vi xóa; `classMode` và `methodMode` quyết định thời điểm xóa.

**Không tính đến context được kế thừa từ base test class.** Current level được xác định từ hierarchy mà test hiện tại nhìn thấy, gồm cả cấu hình được kế thừa.

**Dùng @DirtiesContext để dọn database.** Đóng context không tự động rollback mọi giao dịch hoặc xóa dữ liệu đã commit. Hãy quản lý transaction và dữ liệu theo cách riêng.

**Đặt @DirtiesContext trên mọi test.** Điều này làm mất lợi ích cache và có thể khiến suite chậm đáng kể. Chỉ đánh dấu dirty khi test thật sự làm thay đổi trạng thái context.

**Giả định sibling context luôn độc lập.** Hai child có thể cùng dùng bean từ parent. Nếu parent bị thay đổi, sibling cũng có thể bị ảnh hưởng dù test không gọi trực tiếp bean trong sibling.

## 12. Quy trình chọn hierarchyMode

Khi một test trong context hierarchy cần dùng `@DirtiesContext`, hãy xác định:

1. Test hiện tại nhìn thấy những mức context nào trong `@ContextHierarchy`?
2. Mức thấp nhất mà test nhìn thấy là context nào?
3. Bean hoặc trạng thái bị thay đổi thuộc current level, một context con hay ancestor?
4. Các hierarchy khác có dùng chung ancestor context với test hiện tại không?
5. Nếu giữ parent trong cache, các child context còn lại có tiếp tục nhận trạng thái hợp lệ không?
6. Nếu xóa exhaustive, những test ở nhánh khác có phải khởi tạo lại context không?
7. Việc làm bẩn cần diễn ra trước method, sau method, sau mỗi method hay sau class?
8. Có tài nguyên ngoài ApplicationContext cần cleanup riêng không?

Có thể dùng quy tắc thực hành sau:

- Chọn `CURRENT_LEVEL` khi thay đổi được giới hạn ở context thấp nhất mà test nhìn thấy và các hậu duệ của nó; parent cùng các nhánh khác vẫn hợp lệ.
- Chọn `EXHAUSTIVE` khi thay đổi có thể ảnh hưởng ancestor chung hoặc nhiều hierarchy cùng chia sẻ ancestor đó; đây cũng là mặc định của `@DirtiesContext`.
- Chọn `methodMode` hoặc `classMode` riêng theo thời điểm cần loại context.
- Dùng transaction, cleanup fixture hoặc lifecycle callback cho dữ liệu và tài nguyên ngoài ApplicationContext.

## 13. Tài liệu tham khảo

- [Spring Framework Reference — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): mô tả cách đánh dấu context dirty và ví dụ sử dụng `CURRENT_LEVEL` trong context hierarchy.
- [DirtiesContext.HierarchyMode Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/annotation/DirtiesContext.HierarchyMode.html): định nghĩa chính xác phạm vi xóa cache của `EXHAUSTIVE` và `CURRENT_LEVEL`.
- [Spring Framework Reference — Context Hierarchies](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/hierarchies.html): cách khai báo và sử dụng context hierarchy trong test.

Hiểu đúng phạm vi `hierarchyMode` giúp tránh hai vấn đề trái ngược: giữ lại context cha đã bị thay đổi, hoặc xóa quá nhiều context khiến các test ở nhánh không liên quan phải khởi tạo lại. Hãy xác định mức context bị thay đổi, các hậu duệ và ancestor dùng chung trước khi chọn thuật toán; khi đó cache của Spring TestContext sẽ được làm sạch đúng phạm vi cần thiết.
