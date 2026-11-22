# @AliasFor khi cần công khai thuộc tính cấu hình

Trong Spring, annotation tổ hợp (composed annotation) gom nhiều annotation cấu hình thành một giao diện có ý nghĩa rõ ràng. Một nhóm integration test có thể luôn cần SpringExtension, cấu hình ApplicationContext, profile integration và property dành riêng cho test.

Khi tạo annotation mới chỉ mang các annotation meta, người dùng annotation đó chưa thể truyền giá trị vào thuộc tính của annotation meta. `@AliasFor` giải quyết vấn đề này bằng cách khai báo một thuộc tính của annotation tổ hợp là bí danh của thuộc tính khác trong chính annotation đó hoặc của thuộc tính thuộc meta-annotation.

Nhờ vậy, annotation tổ hợp giữ được chính sách chung và vẫn công khai những lựa chọn mà từng test class cần thay đổi. Spring TestContext Framework hiểu alias khi tổng hợp metadata để xây dựng cấu hình test.

## Annotation tổ hợp và nhu cầu công khai thuộc tính

Giả sử nhiều test class lặp lại cấu hình sau:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PersistenceTestConfig.class)
@ActiveProfiles("integration")
@TestPropertySource(properties = "feature.audit.enabled=false")
class CustomerRepositoryTest {
    // ...
}
~~~

Có thể gom các annotation chung thành một annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@ExtendWith(SpringExtension.class)
@ContextConfiguration
@ActiveProfiles("integration")
@TestPropertySource
public @interface PersistenceIntegrationTest {
}
~~~

Sau đó test class chỉ cần viết:

~~~java
@PersistenceIntegrationTest
class CustomerRepositoryTest {
    // ...
}
~~~

Cách này giảm lặp, nhưng test class chưa thể truyền class cấu hình hoặc property riêng qua annotation mới. Nếu chỉ thêm một thuộc tính tên là `classes` vào annotation mới, Spring cũng không tự đoán rằng nó phải ánh xạ tới `@ContextConfiguration.classes`. `@AliasFor` thiết lập quan hệ đó một cách tường minh.

## Hai loại alias chính

`@AliasFor` thuộc package `org.springframework.core.annotation`:

~~~java
import org.springframework.core.annotation.AliasFor;
~~~

Có hai cách dùng phổ biến:

1. **Alias trong cùng annotation:** hai thuộc tính của một annotation biểu diễn cùng giá trị, ví dụ `value` và `locations`.
2. **Alias tới meta-annotation:** thuộc tính của annotation tổ hợp công khai một thuộc tính của annotation meta, ví dụ `classes` của annotation mới ánh xạ tới `classes` của `@ContextConfiguration`.

`@AliasFor` không phải cơ chế ánh xạ tùy ý giữa hai annotation bất kỳ. Với alias tới meta-annotation, annotation đích phải nằm trong meta-annotation hierarchy của annotation tổ hợp để Spring có thể tổng hợp metadata.

## Alias giữa hai thuộc tính trong cùng annotation

Một annotation có thể cung cấp hai tên cho cùng một thuộc tính. Trường hợp quen thuộc là `value` để viết ngắn gọn và một tên mô tả rõ hơn để mã nguồn dễ đọc.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TestResources {

    @AliasFor("locations")
    String[] value() default {};

    @AliasFor("value")
    String[] locations() default {};
}
~~~

Hai thuộc tính `value` và `locations` là alias tường minh của nhau. Người dùng có thể chọn một trong hai cách viết:

~~~java
@TestResources("/test-context.xml")
class XmlContextTest {
}

@TestResources(locations = "/test-context.xml")
class AnotherXmlContextTest {
}
~~~

Với alias nội bộ, cần khai báo quan hệ hai chiều: mỗi thuộc tính trỏ tới thuộc tính còn lại. Hai thuộc tính phải có cùng kiểu trả về và cùng giá trị mặc định. Ví dụ, một thuộc tính kiểu `String[]` không thể alias với thuộc tính kiểu `String`.

## Alias tới thuộc tính của meta-annotation

Trường hợp quan trọng khi xây dựng annotation dùng lại là đưa một thuộc tính của annotation meta ra annotation bên ngoài.

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.core.annotation.AliasFor;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.TestPropertySource;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@ExtendWith(SpringExtension.class)
@ContextConfiguration
@ActiveProfiles("integration")
@TestPropertySource
public @interface PersistenceIntegrationTest {

    @AliasFor(
        annotation = ContextConfiguration.class,
        attribute = "classes"
    )
    Class<?>[] classes() default {};

    @AliasFor(
        annotation = ContextConfiguration.class,
        attribute = "locations"
    )
    String[] locations() default {};

    @AliasFor(
        annotation = TestPropertySource.class,
        attribute = "properties"
    )
    String[] properties() default {};

    @AliasFor(
        annotation = TestPropertySource.class,
        attribute = "locations"
    )
    String[] propertyLocations() default {};
}
~~~

Các thuộc tính của annotation tổ hợp được ánh xạ như sau:

| Thuộc tính công khai | Thuộc tính meta được ánh xạ | Mục đích |
|---|---|---|
| classes | ContextConfiguration.classes | Khai báo class cấu hình Java |
| locations | ContextConfiguration.locations | Khai báo resource cấu hình, chẳng hạn XML |
| properties | TestPropertySource.properties | Truyền inline property cho test |
| propertyLocations | TestPropertySource.locations | Chỉ định file property dành cho test |

Test class có thể sử dụng annotation mới và truyền cấu hình riêng:

~~~java
@PersistenceIntegrationTest(
    classes = CustomerPersistenceConfig.class,
    properties = {
        "feature.audit.enabled=true",
        "customer.search.page-size=20"
    }
)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void loadsCustomerRepository() {
        assertThat(customerRepository).isNotNull();
    }
}
~~~

Khi Spring TestContext Framework tổng hợp annotation, giá trị `classes` được chuyển tới `@ContextConfiguration.classes`, còn các property được chuyển tới `@TestPropertySource.properties`. Profile `integration` vẫn đến từ meta-annotation `@ActiveProfiles("integration")`.

Như vậy, annotation tổ hợp giữ cấu hình chung ở một nơi nhưng vẫn cho từng test class cung cấp phần cấu hình riêng. Người dùng không cần lặp lại toàn bộ các annotation meta.

## Cấu hình cố định và cấu hình có thể tùy chỉnh

Không phải mọi thuộc tính của meta-annotation đều cần đưa ra ngoài. Annotation tổ hợp thường có hai nhóm:

- **Thuộc tính cố định:** chính sách mà nhóm test phải tuân theo, ví dụ luôn bật profile integration hoặc luôn đăng ký SpringExtension.
- **Thuộc tính được công khai:** lựa chọn thay đổi giữa các test class, ví dụ class cấu hình, property hoặc resource location.

Trong ví dụ trên, `@ActiveProfiles("integration")` là cấu hình cố định. Annotation không khai báo alias cho `profiles`, nên test class không thể thay profile qua `@PersistenceIntegrationTest`.

Nếu muốn profile cũng tùy chỉnh được, hãy để meta-annotation không đặt giá trị cố định rồi công khai thuộc tính alias:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.test.context.ActiveProfiles;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ActiveProfiles
public @interface ProfiledIntegrationTest {

    @AliasFor(
        annotation = ActiveProfiles.class,
        attribute = "profiles"
    )
    String[] profiles() default {};
}
~~~

Sử dụng:

~~~java
@ProfiledIntegrationTest(profiles = {"integration", "customer"})
class CustomerIntegrationTest {
}
~~~

Thuộc tính `profiles` của annotation tổ hợp ánh xạ tới `@ActiveProfiles.profiles`. Mặc định của alias là mảng rỗng, tương ứng với mặc định của thuộc tính meta. Khi test class truyền profile, Spring dùng giá trị đó để xây dựng danh sách profile hoạt động.

Chỉ công khai những thuộc tính mà người sử dụng thực sự cần thay đổi. Đưa toàn bộ thuộc tính của mọi meta-annotation ra ngoài làm annotation tổ hợp phức tạp và khó bảo trì.

## Quy tắc khi khai báo alias

Spring kiểm tra các quy tắc alias khi tổng hợp annotation. Nếu khai báo không nhất quán, việc đọc annotation hoặc tạo TestContext có thể thất bại.

### 1. Alias nội bộ phải khai báo hai chiều

Ví dụ hợp lệ:

~~~java
public @interface ResourceConfig {

    @AliasFor("locations")
    String[] value() default {};

    @AliasFor("value")
    String[] locations() default {};
}
~~~

Hai thuộc tính cùng kiểu `String[]`, cùng giá trị mặc định và trỏ lẫn nhau.

### 2. Kiểu trả về phải tương thích chính xác

Nếu thuộc tính đích là `Class<?>[]`, thuộc tính alias cũng phải là `Class<?>[]`. Nếu đích là `String[]`, alias phải là `String[]`.

Ví dụ không hợp lệ:

~~~java
public @interface InvalidTestConfig {

    @AliasFor(
        annotation = ContextConfiguration.class,
        attribute = "classes"
    )
    String[] classes() default {};
}
~~~

Thuộc tính alias có kiểu `String[]`, còn `ContextConfiguration.classes` có kiểu `Class<?>[]`. Spring không thể tổng hợp hai giá trị khác kiểu.

### 3. Giá trị mặc định phải khớp

Khi alias tới meta-annotation, giá trị mặc định của thuộc tính alias phải bằng giá trị mặc định được khai báo trên thuộc tính đích.

Ví dụ, `ContextConfiguration.classes()` có mặc định là mảng class rỗng, vì vậy alias cũng cần mặc định là mảng rỗng:

~~~java
@AliasFor(
    annotation = ContextConfiguration.class,
    attribute = "classes"
)
Class<?>[] classes() default {};
~~~

Nếu alias tới thuộc tính boolean có mặc định `true`, alias cũng phải khai báo mặc định `true`. Quy tắc này so sánh với giá trị mặc định trong định nghĩa annotation đích, không phải giá trị cụ thể được đặt trên một instance meta-annotation.

### 4. Annotation đích phải nằm trong meta-annotation hierarchy

Khai báo sau có ý nghĩa vì `@ContextConfiguration` được đặt trên annotation tổ hợp:

~~~java
@ContextConfiguration
public @interface ConfiguredTest {

    @AliasFor(
        annotation = ContextConfiguration.class,
        attribute = "classes"
    )
    Class<?>[] classes() default {};
}
~~~

Nếu annotation đích không nằm trong meta-annotation hierarchy của annotation tổ hợp, Spring không có đường ánh xạ hợp lệ để tổng hợp giá trị.

### 5. Tên thuộc tính đích phải tồn tại

Giá trị `attribute` phải trùng tên một thuộc tính thật của annotation đích. Dùng tên sai hoặc trỏ tới annotation không có thuộc tính đó sẽ làm Spring không thể tổng hợp metadata.

Nên viết rõ annotation và thuộc tính đích:

~~~java
@AliasFor(
    annotation = ContextConfiguration.class,
    attribute = "classes"
)
Class<?>[] configClasses() default {};
~~~

Cách viết này cho người đọc biết thuộc tính được ánh xạ tới đâu.

## value và attribute trong @AliasFor

`@AliasFor` có hai thuộc tính `value` và `attribute` là alias của nhau. Vì vậy, hai cách sau tương đương khi trỏ tới thuộc tính trong cùng annotation:

~~~java
@AliasFor("locations")
String[] value() default {};
~~~

~~~java
@AliasFor(attribute = "locations")
String[] value() default {};
~~~

Khi trỏ tới meta-annotation, nên viết rõ annotation đích và tên thuộc tính:

~~~java
@AliasFor(
    annotation = ContextConfiguration.class,
    attribute = "classes"
)
Class<?>[] classes() default {};
~~~

Nếu bỏ `annotation`, Spring hiểu alias là alias tới thuộc tính trong chính annotation hiện tại. Nếu muốn trỏ tới meta-annotation, cần chỉ rõ annotation đích.

## Alias không thay đổi ý nghĩa của thuộc tính gốc

`@AliasFor` chỉ thiết lập quan hệ giữa các tên thuộc tính. Nó không thay đổi cách annotation meta xử lý giá trị.

Alias tới `@ContextConfiguration.locations` vẫn khai báo resource location để Spring nạp ApplicationContext. Alias tới `@TestPropertySource.properties` vẫn cung cấp inline property cho môi trường test. Alias tới `@ActiveProfiles.profiles` vẫn tuân theo quy tắc kế thừa profile và cách Spring xây dựng context.

`@AliasFor` không tự bật profile, không tạo bean và không nạp context. Nó chỉ công khai một thuộc tính cấu hình qua tên khác.

## Spring tổng hợp alias khi đọc annotation như thế nào?

Java reflection có thể đọc annotation được khai báo trực tiếp trên một element, nhưng việc hợp nhất thuộc tính từ nhiều lớp meta-annotation và áp dụng alias là chức năng của Spring merged annotation model.

Spring cung cấp các API như `MergedAnnotations`, `AnnotatedElementUtils` và `AnnotationUtils` để tìm và tổng hợp annotation. TestContext Framework cũng dùng cơ chế này khi đọc annotation cấu hình test.

Ví dụ đọc annotation đã tổng hợp:

~~~java
MergedAnnotation<ContextConfiguration> merged =
    MergedAnnotations.from(
        CustomerRepositoryTest.class,
        MergedAnnotations.SearchStrategy.TYPE_HIERARCHY
    ).get(ContextConfiguration.class);

Class<?>[] classes = merged.getClassArray("classes");
~~~

Khi test class được đánh dấu `@PersistenceIntegrationTest(classes = CustomerPersistenceConfig.class)`, merged annotation của `ContextConfiguration` có thể trả về class cấu hình đã được alias chuyển tới.

Không nên chỉ dùng `getDeclaredAnnotation(ContextConfiguration.class)` trên test class rồi kết luận cấu hình không tồn tại nếu annotation được đặt gián tiếp qua annotation tổ hợp. Hãy dùng API có khả năng tìm meta-annotation và tổng hợp alias khi cần đọc cấu hình theo cách Spring xử lý.

## Kết hợp alias với annotation tổ hợp nhiều tầng

Một annotation tổ hợp có thể được xây dựng từ các annotation tổ hợp khác. Spring hỗ trợ tìm annotation qua meta-annotation hierarchy và tổng hợp thuộc tính theo các alias được khai báo.

Ví dụ, annotation nền cho integration test có thể được dùng trong annotation chuyên biệt cho repository:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@PersistenceIntegrationTest
public @interface JdbcRepositoryTest {

    @AliasFor(
        annotation = PersistenceIntegrationTest.class,
        attribute = "classes"
    )
    Class<?>[] classes() default {};

    @AliasFor(
        annotation = PersistenceIntegrationTest.class,
        attribute = "properties"
    )
    String[] properties() default {};
}
~~~

Test class dùng annotation tầng ngoài:

~~~java
@JdbcRepositoryTest(
    classes = CustomerPersistenceConfig.class,
    properties = "customer.repository.cache=false"
)
class CustomerRepositoryTest {
}
~~~

Khi tạo annotation nhiều tầng, cần bảo đảm đường alias rõ ràng và các thuộc tính có kiểu/default phù hợp ở từng tầng. Một chuỗi meta-annotation quá sâu hoặc có nhiều thuộc tính trùng tên dễ làm người đọc khó biết giá trị cuối cùng đến từ đâu. Annotation tầng ngoài nên công khai đúng những lựa chọn cần thiết.

## Xử lý xung đột và giá trị được khai báo nhiều nơi

Khi cấu hình có thể đến từ annotation tổ hợp, superclass, meta-annotation hoặc annotation trực tiếp trên test class, cần hiểu cách Spring tổng hợp metadata và thứ tự tìm annotation.

Một số nguyên tắc thực hành:

- Alias xác định hai tên biểu diễn cùng một thuộc tính; nó không phải quy tắc ưu tiên độc lập.
- Giá trị được khai báo qua alias được xử lý như giá trị của thuộc tính meta tương ứng.
- Tránh cấu hình mâu thuẫn cùng một thuộc tính qua nhiều đường khác nhau.
- Với cấu hình kế thừa như `@ActiveProfiles` hoặc `@TestPropertySource`, các quy tắc merge/inherit của chính annotation đó vẫn có hiệu lực.
- Khi cần biết giá trị cuối cùng, hãy kiểm tra merged annotation hoặc `Environment` của ApplicationContext.

Ví dụ, nếu annotation tổ hợp cố định `@ActiveProfiles("integration")` nhưng đồng thời công khai alias để test class truyền profile khác, cần xác định rõ profile là chính sách cố định hay lựa chọn của từng class. Thiết kế rõ ràng ngay từ đầu giúp tránh cấu hình khó đoán.

## Khi nào nên dùng @AliasFor?

| Nhu cầu | Có nên dùng? | Lý do |
|---|---|---|
| Gom nhiều annotation Spring thành một annotation dễ dùng | Có | Công khai thuộc tính cần thiết từ meta-annotation |
| Cho phép value và locations là hai tên tương đương | Có | Tạo alias nội bộ tường minh |
| Đổi tên tùy ý một thuộc tính không có quan hệ meta-annotation | Không | AliasFor không phải mapping tổng quát |
| Cố định profile cho mọi test trong một nhóm | Không cần | Đặt giá trị trực tiếp trên ActiveProfiles meta |
| Cho mỗi test class chọn class cấu hình qua annotation tổ hợp | Có | Alias tới ContextConfiguration.classes |
| Đọc annotation meta qua reflection Java thuần | Không giải quyết trực tiếp | Dùng Spring merged annotation APIs |

Không cần tạo annotation tổ hợp cho một test class duy nhất. Annotation dùng lại có giá trị khi nhiều class thực sự chia sẻ cùng chính sách cấu hình và cần một giao diện đơn giản, ổn định.

## Những lỗi thường gặp

**Khai báo alias nhưng quên meta-annotation.** Thuộc tính của annotation mới không tự động ánh xạ tới Spring. Hãy đặt annotation đích trên annotation tổ hợp và khai báo `@AliasFor` với đúng class, attribute.

**Kiểu alias khác kiểu thuộc tính đích.** Ví dụ dùng `String` để alias tới `Class<?>[]`. Kiểu phải tương thích chính xác.

**Giá trị mặc định không khớp.** Khi alias tới meta-annotation, default của thuộc tính mới phải bằng default của thuộc tính đích. Với alias nội bộ, hai thuộc tính phải có cùng default.

**Chỉ khai báo một phía của alias nội bộ.** Cặp alias tường minh trong cùng annotation cần trỏ lẫn nhau.

**Nhầm alias với cấu hình cố định.** Nếu mọi test phải dùng profile integration, đặt profile trên meta-annotation. Chỉ alias profile khi người dùng annotation tổ hợp cần quyền thay đổi nó.

**Đọc annotation bằng reflection trực tiếp rồi bỏ sót meta-annotation.** Dùng Spring merged annotation APIs khi cần kết quả đã hợp nhất.

**Công khai quá nhiều thuộc tính.** Annotation tổ hợp nên đưa ra các lựa chọn có ý nghĩa cho người sử dụng, không nhất thiết sao chép toàn bộ API của tất cả meta-annotation.

**Kỳ vọng alias tự thay đổi bean hoặc context.** Alias chỉ chuyển giá trị cấu hình. Spring vẫn cần chạy quy trình TestContext để tạo ApplicationContext từ cấu hình đã tổng hợp.

## Cách thiết kế annotation dùng lại

Khi xây dựng annotation cấu hình cho một nhóm test, hãy bắt đầu bằng việc xác định những điều luôn giống nhau và những điều từng test class cần quyết định.

1. Chọn các annotation nền cần gom, chẳng hạn `@ExtendWith(SpringExtension.class)`, `@ContextConfiguration`, `@ActiveProfiles` và `@TestPropertySource`.
2. Đặt giá trị cố định trực tiếp trên meta-annotation nếu đó là chính sách chung.
3. Khai báo thuộc tính trong annotation mới cho những lựa chọn cần công khai.
4. Dùng `@AliasFor(annotation = ..., attribute = "...")` để nối từng thuộc tính tới đúng meta-annotation.
5. Giữ kiểu trả về và giá trị mặc định khớp với thuộc tính đích.
6. Nếu hai tên trong annotation mới cùng biểu diễn một giá trị, khai báo alias nội bộ hai chiều.
7. Sử dụng annotation tổ hợp trên test class và để Spring TestContext Framework tổng hợp cấu hình.
8. Khi cần chẩn đoán, đọc merged annotation hoặc kiểm tra Environment của ApplicationContext.

Một annotation tổ hợp tốt thể hiện chính sách test bằng một tên có ý nghĩa, đồng thời chỉ công khai các lựa chọn cần thiết. `@AliasFor` là cầu nối giữa giao diện đơn giản đó và các thuộc tính cấu hình của Spring. Khi khai báo đúng quan hệ, kiểu và giá trị mặc định, Spring có thể hợp nhất metadata nhất quán và tạo TestContext theo cấu hình mà test class yêu cầu.
