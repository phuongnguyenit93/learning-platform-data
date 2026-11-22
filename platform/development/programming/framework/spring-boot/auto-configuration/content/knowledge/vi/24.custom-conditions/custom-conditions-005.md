# Annotation điều kiện riêng và cách đọc tham số annotation

## Mục tiêu học tập

Spring Boot cung cấp nhiều annotation điều kiện như \`@ConditionalOnClass\`, \`@ConditionalOnProperty\`, \`@ConditionalOnBean\` và \`@ConditionalOnMissingBean\`. Khi thư viện có quy tắc kích hoạt đặc thù mà các annotation có sẵn không biểu đạt rõ, ta có thể tạo **annotation điều kiện riêng** bằng \`@Conditional\` và một lớp triển khai \`Condition\`.

Điểm quan trọng là condition không chỉ cần biết có khớp hay không. Nó còn phải đọc được các tham số mà người viết annotation truyền vào, ví dụ danh sách region được phép, tên feature, mode hoặc class cần kiểm tra. Spring cung cấp \`AnnotatedTypeMetadata\` để condition đọc annotation trên class hoặc method, kể cả annotation được tạo bằng cách compose từ annotation khác.

Bài học này xây dựng annotation \`@ConditionalOnRegion\` có tham số, đọc các giá trị đó bằng metadata, hỗ trợ annotation tổng hợp qua \`@AliasFor\`, và kiểm chứng bằng \`ApplicationContextRunner\`.

Sau bài học, bạn có thể:

- Phân biệt \`@Conditional\`, \`Condition\`, \`ConditionContext\` và \`AnnotatedTypeMetadata\`.
- Tạo annotation điều kiện có thuộc tính và gắn vào class hoặc \`@Bean\` method.
- Đọc đúng tham số annotation bằng \`getAnnotationAttributes(...)\`.
- Hiểu merged annotation và cách \`@AliasFor\` chuyển thuộc tính từ annotation tổng hợp.
- Chọn cách đọc class-valued attributes và repeatable annotations phù hợp.
- Viết condition an toàn, không khởi tạo bean hoặc tạo side effect trong lúc đánh giá.
- Kiểm thử nhánh khớp, không khớp, property bị thiếu và annotation tổng hợp.

## 1. Khi nào cần annotation điều kiện riêng?

Dùng annotation có sẵn khi quy tắc có thể diễn đạt trực tiếp:

~~~java
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ConditionalOnProperty(
        prefix = "acme.codec",
        name = "enabled",
        havingValue = "true")
@ConditionalOnBean(MeterRegistry.class)
~~~

Nếu nhiều module lặp lại cùng một quy tắc nghiệp vụ, ví dụ chỉ bật một adapter khi region của ứng dụng nằm trong danh sách được thư viện hỗ trợ, một annotation chuyên biệt sẽ làm contract dễ đọc hơn:

~~~java
@ConditionalOnRegion({"eu", "apac"})
class RegionalAcmeAutoConfiguration {
}
~~~

Annotation này biểu đạt trực tiếp ý định. Các class dùng nó không cần biết tên property, cách chuẩn hóa chuỗi hoặc cách so sánh region. Những chi tiết đó được tập trung trong một condition.

Ví dụ khác có thể cần annotation riêng:

- Chỉ bật integration khi tenant thuộc một nhóm được hỗ trợ.
- Chọn adapter theo cloud provider hoặc deployment mode.
- Bật một bean khi ứng dụng dùng protocol nằm trong danh sách cho phép.
- Kiểm tra resource có version hoặc format nhất định.
- Kết hợp nhiều thuộc tính annotation để biểu đạt một policy.

Không nên viết condition riêng chỉ để bọc một annotation có sẵn mà không tăng độ rõ ràng. Annotation chuyên biệt có giá trị khi nó tạo ra một contract ổn định, tái sử dụng được và có thể được kiểm thử độc lập.

## 2. Cơ chế cơ bản: @Conditional gọi Condition.matches

Spring định nghĩa annotation \`@Conditional\` để gắn một hoặc nhiều lớp condition vào một thành phần cần đăng ký:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface Conditional {
    Class<? extends Condition>[] value();
}
~~~

Đoạn trên mô tả cấu trúc rút gọn của annotation trong Spring Framework. Trong ứng dụng, ta thường không khai báo \`@Conditional\` trực tiếp mỗi lần; thay vào đó, ta đặt nó trên annotation điều kiện riêng.

Một condition triển khai interface:

~~~java
public interface Condition {
    boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata);
}
~~~

Hai tham số quan trọng:

| Tham số | Cung cấp thông tin gì? | Ví dụ sử dụng |
| --- | --- | --- |
| \`ConditionContext\` | Environment, registry, bean factory, resource loader và class loader | Đọc property, xem bean definitions, kiểm tra class/resource |
| \`AnnotatedTypeMetadata\` | Metadata của class hoặc method đang được kiểm tra | Đọc tham số annotation trên configuration class hoặc \`@Bean\` method |

\`matches\` trả về \`true\` khi thành phần được phép đăng ký, và \`false\` khi condition phủ quyết việc đăng ký.

**Metadata là thông tin của phần tử đang được kiểm tra.** Nếu annotation đặt trên class \`@Configuration\`, metadata mô tả class đó. Nếu annotation đặt trên một method \`@Bean\`, metadata mô tả method đó. Vì vậy, cùng một condition có thể tái sử dụng ở cả cấp class và cấp bean method.

## 3. ConditionContext: đọc môi trường và hạ tầng container

\`ConditionContext\` cung cấp năm nguồn thông tin:

| Phương thức | Nội dung | Lưu ý |
| --- | --- | --- |
| \`getEnvironment()\` | Environment hiện tại | Đọc property và active profiles |
| \`getRegistry()\` | BeanDefinitionRegistry | Kiểm tra/đăng ký ở mức bean definition nếu thật sự cần |
| \`getBeanFactory()\` | ConfigurableListableBeanFactory | Có thể là \`null\` nếu không có bean factory phù hợp |
| \`getResourceLoader()\` | ResourceLoader | Tìm resource |
| \`getClassLoader()\` | ClassLoader | Tìm hoặc tải class; có thể là \`null\` nếu không có system class loader |

Ví dụ đọc property:

~~~java
String region = context.getEnvironment().getProperty("acme.region");
~~~

Ví dụ kiểm tra resource:

~~~java
boolean found = context.getResourceLoader()
        .getResource("classpath:acme/schema.json")
        .exists();
~~~

Ví dụ lấy class loader:

~~~java
ClassLoader classLoader = context.getClassLoader();
~~~

Nếu cần kiểm tra bean, ưu tiên các annotation có sẵn như \`@ConditionalOnBean\` hoặc \`@ConditionalOnMissingBean\`. Nếu logic phức tạp thật sự cần đọc registry, hãy làm việc với bean definitions, không lấy instance của bean.

### 3.1. Điều condition không nên làm

Condition được đánh giá trong giai đoạn xử lý đăng ký thành phần. Spring quy định condition phải tuân theo các giới hạn tương tự \`BeanFactoryPostProcessor\` và **không được tương tác với bean instances**.

Tránh:

- Gọi \`context.getBean(...)\` để tạo hoặc lấy bean trong condition.
- Gọi database, HTTP endpoint hoặc dịch vụ bên ngoài.
- Ghi file, tạo resource hoặc thay đổi trạng thái ứng dụng.
- Dựa vào thời gian hiện tại hoặc dữ liệu thay đổi liên tục để quyết định đăng ký bean.
- Lưu trạng thái mutable trong instance condition để dùng giữa nhiều lần đánh giá.

Nên giữ condition nhẹ, xác định được từ metadata, Environment, classpath, resource và bean definitions. Điều này giúp kết quả ổn định và tránh tạo vòng khởi tạo bean.

## 4. AnnotatedTypeMetadata: đọc tham số annotation

\`AnnotatedTypeMetadata\` là abstraction để đọc annotation trên class hoặc method mà không cần lấy instance của thành phần đó.

Các phương thức thường dùng:

| Phương thức | Kết quả |
| --- | --- |
| \`isAnnotated(annotationName)\` | Kiểm tra annotation trực tiếp hoặc meta-annotation có mặt không |
| \`getAnnotationAttributes(annotationName)\` | Lấy Map tên thuộc tính → giá trị, có hỗ trợ merged annotations |
| \`getAnnotationAttributes(annotationName, classValuesAsString)\` | Lấy thuộc tính và có thể chuyển class value thành tên class |
| \`getAllAnnotationAttributes(annotationName)\` | Lấy thuộc tính của tất cả lần xuất hiện phù hợp dưới dạng MultiValueMap |
| \`getAnnotations()\` | Truy cập MergedAnnotations để xử lý nâng cao |

Ví dụ:

~~~java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                ConditionalOnRegion.class.getName());

String[] regions = (String[]) attributes.get("value");
boolean matchIfMissing =
        (Boolean) attributes.get("matchIfMissing");
~~~

Giá trị trong Map phản ánh kiểu khai báo của annotation:

- \`String\` → \`String\`.
- \`boolean\` → \`Boolean\`.
- \`int\` → \`Integer\`.
- \`String[]\` → \`String[]\`.
- \`Class<?>\` → giá trị class, trừ khi chọn chế độ trả về tên class.
- Enum → instance enum tương ứng.

Đừng ép kiểu tùy tiện. Hãy đối chiếu kiểu lấy ra với kiểu thuộc tính trong annotation và xử lý trường hợp metadata không có annotation.

### 4.1. Kiểm tra trước khi đọc

Một cách viết an toàn:

~~~java
String annotationName = ConditionalOnRegion.class.getName();

if (!metadata.isAnnotated(annotationName)) {
    return false;
}

Map<String, Object> attributes =
        metadata.getAnnotationAttributes(annotationName);

if (attributes == null) {
    return false;
}
~~~

Trong một condition được kích hoạt bởi chính annotation đó, việc thiếu attributes thường chỉ ra cấu trúc annotation không như mong đợi. Trả về \`false\` giúp tránh \`NullPointerException\`, nhưng trong thư viện lớn, một lỗi cấu hình annotation có thể đáng được phát hiện sớm bằng test hoặc thông báo rõ hơn.

### 4.2. Vì sao getAnnotationAttributes hỗ trợ annotation tổng hợp?

Spring sử dụng merged annotation model. Nếu một annotation khác được meta-annotate bằng \`@ConditionalOnRegion\`, metadata có thể tìm annotation gốc trong hierarchy và trả về thuộc tính đã được merge.

Đặc biệt, \`@AliasFor\` có thể ánh xạ thuộc tính của annotation tổng hợp tới thuộc tính của annotation meta. Đây là cách làm cho annotation tổng hợp có API ngắn gọn nhưng condition vẫn đọc được một bộ thuộc tính thống nhất.

### 4.3. getAllAnnotationAttributes có một khác biệt quan trọng

\`getAllAnnotationAttributes\` trả về thuộc tính của tất cả annotation cùng loại được tìm thấy, thường hữu ích khi xử lý annotation lặp lại. Tuy nhiên, phương thức này **không áp dụng attribute overrides từ composed annotations**.

Khi cần một bộ thuộc tính đã merge và có \`@AliasFor\`, ưu tiên \`getAnnotationAttributes\`. Với repeatable annotations trong Spring Framework 6.1, có thể dùng \`getMergedRepeatableAnnotationAttributes(...)\` để nhận từng bộ thuộc tính đã merge trong annotation hierarchy.

## 5. Tạo annotation điều kiện có tham số

Ta xây dựng contract:

~~~java
@ConditionalOnRegion({"eu", "apac"})
class RegionalFeatureConfiguration {
}
~~~

Ý nghĩa:

- Property \`acme.region\` có giá trị \`eu\` hoặc \`apac\`: condition khớp.
- Property thiếu hoặc trống: condition không khớp theo default.
- Property có giá trị khác: condition không khớp.
- Có thể bật \`matchIfMissing=true\` nếu muốn cho phép thiếu property.

**Tệp:** \`ConditionalOnRegion.java\`

~~~java
package example.region;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnRegionCondition.class)
public @interface ConditionalOnRegion {

    String[] value() default {};

    boolean matchIfMissing() default false;
}
~~~

Các điểm cần chú ý:

1. \`@Target(TYPE, METHOD, ANNOTATION_TYPE)\` cho phép dùng annotation trên configuration class, bean method và làm meta-annotation của annotation khác.
2. \`@Retention(RUNTIME)\` để Spring đọc annotation metadata khi xử lý cấu hình.
3. \`@Documented\` giúp annotation xuất hiện trong Javadoc của phần tử sử dụng.
4. \`@Conditional(OnRegionCondition.class)\` kết nối annotation với implementation.
5. \`value()\` là danh sách giá trị được phép; cú pháp rút gọn \`@ConditionalOnRegion({"eu","apac"})\` dùng thuộc tính có tên \`value\`.
6. \`matchIfMissing\` công bố chính sách khi property không tồn tại hoặc trống.

Không bắt buộc phải dùng tên thuộc tính là \`value\`. Nếu dùng \`regions()\`, người gọi sẽ viết \`@ConditionalOnRegion(regions = {"eu", "apac"})\`. Chọn tên dễ hiểu và giữ ổn định vì annotation công khai là một phần API của thư viện.

## 6. Triển khai Condition và đọc thuộc tính

**Tệp:** \`OnRegionCondition.java\`

~~~java
package example.region;

import java.util.Arrays;
import java.util.Locale;
import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class OnRegionCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String annotationName = ConditionalOnRegion.class.getName();

        Map<String, Object> attributes =
                metadata.getAnnotationAttributes(annotationName);

        if (attributes == null) {
            return ConditionOutcome.noMatch(
                    "ConditionalOnRegion attributes were not found");
        }

        String[] allowedRegions = (String[]) attributes.get("value");
        boolean matchIfMissing =
                (Boolean) attributes.get("matchIfMissing");

        String configuredRegion =
                context.getEnvironment().getProperty("acme.region");

        if (configuredRegion == null || configuredRegion.isBlank()) {
            if (matchIfMissing) {
                return ConditionOutcome.match(
                        "acme.region is missing and matchIfMissing is true");
            }
            return ConditionOutcome.noMatch(
                    "acme.region is missing or blank");
        }

        String actualRegion = configuredRegion.trim()
                .toLowerCase(Locale.ROOT);

        boolean matches = Arrays.stream(allowedRegions)
                .filter(region -> region != null && !region.isBlank())
                .map(region -> region.trim().toLowerCase(Locale.ROOT))
                .anyMatch(actualRegion::equals);

        if (matches) {
            return ConditionOutcome.match(
                    "acme.region '" + configuredRegion
                            + "' is in the allowed region list");
        }

        return ConditionOutcome.noMatch(
                "acme.region '" + configuredRegion
                        + "' is not in " + Arrays.toString(allowedRegions));
    }
}
~~~

Đây là implementation cho Spring Boot 3.3 và Java 17+. Các quyết định được thực hiện:

- Dùng \`getAnnotationAttributes\` để đọc thuộc tính đã merge.
- Dùng \`Environment\` để đọc \`acme.region\`.
- Chuẩn hóa chữ hoa/thường bằng \`Locale.ROOT\` để kết quả không phụ thuộc locale của máy.
- Xem property null hoặc chỉ có khoảng trắng là thiếu.
- Cho phép thiếu chỉ khi annotation đặt \`matchIfMissing=true\`.
- Trả về thông báo match/no-match có lý do.

### 6.1. Vì sao kế thừa SpringBootCondition?

Spring Framework chỉ yêu cầu condition triển khai \`Condition.matches(...)\`. Spring Boot cung cấp \`SpringBootCondition\` như một base class cho condition dùng trong hệ sinh thái Boot.

Khi kế thừa \`SpringBootCondition\`, ta cài đặt \`getMatchOutcome(...)\` và trả về \`ConditionOutcome.match(...)\` hoặc \`ConditionOutcome.noMatch(...)\`. Boot dùng kết quả này để ghi nhận và log lý do đánh giá, giúp Condition Evaluation Report dễ chẩn đoán hơn.

Nếu muốn viết condition dùng chung cho Spring Framework mà không phụ thuộc Boot, hãy triển khai trực tiếp \`Condition\` và trả về boolean. Khi đó tự thiết kế logging/diagnostic nếu ứng dụng cần. Với một thư viện auto-configuration dành riêng cho Boot, \`SpringBootCondition\` thường thuận tiện hơn.

### 6.2. Điều gì xảy ra khi condition được đặt trên method?

Cùng một lớp condition có thể nhận metadata từ class hoặc method:

~~~java
@AutoConfiguration
@ConditionalOnRegion({"eu", "apac"})
class RegionalAutoConfiguration {

    @Bean
    RegionalClient regionalClient() {
        return new RegionalClient();
    }

    @Bean
    @ConditionalOnRegion(
            value = {"us"},
            matchIfMissing = true)
    UsFallbackClient usFallbackClient() {
        return new UsFallbackClient();
    }
}
~~~

- Annotation trên class quyết định toàn bộ configuration class có được xử lý hay không.
- Annotation trên bean method quyết định bean method đó có được đăng ký hay không.
- Nếu class-level condition không khớp, các bean method bên trong class không được đăng ký qua nhánh đó.
- Nếu class-level condition khớp, từng method-level condition vẫn được đánh giá độc lập.

Trong code thực tế, hãy đặt condition ở cấp nhỏ nhất đúng với phạm vi policy. Nếu toàn bộ nhóm bean chỉ hợp lệ trong EU/APAC, đặt ở class. Nếu chỉ một bean riêng cần điều kiện, đặt ở method.

## 7. Annotation tổng hợp và @AliasFor

Một thư viện có thể tạo annotation ngắn hơn cho một tập region thường dùng:

~~~java
@ConditionalOnRegions({"eu", "apac"})
class EuropeAndAsiaConfiguration {
}
~~~

**Tệp:** \`ConditionalOnRegions.java\`

~~~java
package example.region;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;

@Target({
        ElementType.TYPE,
        ElementType.METHOD,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@ConditionalOnRegion
public @interface ConditionalOnRegions {

    @AliasFor(
            annotation = ConditionalOnRegion.class,
            attribute = "value")
    String[] value() default {};

    @AliasFor(
            annotation = ConditionalOnRegion.class,
            attribute = "matchIfMissing")
    boolean matchIfMissing() default false;
}
~~~

Ở đây:

- \`@ConditionalOnRegions\` được meta-annotate bằng \`@ConditionalOnRegion\`.
- \`value()\` của annotation tổng hợp alias tới \`value()\` của annotation meta.
- \`matchIfMissing()\` alias tới thuộc tính cùng tên.
- Khi condition gọi \`metadata.getAnnotationAttributes(ConditionalOnRegion.class.getName())\`, Spring trả về các giá trị đã merge, kể cả giá trị được override qua annotation tổng hợp.

**Default values phải tương thích.** Giá trị mặc định của thuộc tính alias nên tương ứng với default của thuộc tính meta. Ví dụ trên dùng mảng rỗng và \`false\` ở cả hai tầng.

### 7.1. Khi nào dùng @AliasFor?

Dùng \`@AliasFor\` khi muốn người dùng annotation tổng hợp điều chỉnh thuộc tính của annotation meta. Nó hữu ích cho:

- Rút gọn một cấu hình phổ biến.
- Đổi tên thuộc tính cho hợp ngôn ngữ nghiệp vụ.
- Cho phép annotation cấp cao điều khiển một hoặc nhiều tham số condition.
- Kết hợp nhiều annotation nền tảng thành một annotation công khai.

Nếu annotation tổng hợp luôn có một policy cố định, không cần alias. Có thể chỉ đặt giá trị cố định ở meta-annotation và không công bố thêm thuộc tính.

### 7.2. Đọc annotation trực tiếp hay annotation meta?

Nếu condition luôn tìm \`ConditionalOnRegion\`, hãy đọc đúng tên đó:

~~~java
metadata.getAnnotationAttributes(
        ConditionalOnRegion.class.getName());
~~~

Không đọc \`ConditionalOnRegions\` trong condition nếu mục tiêu là hỗ trợ cả annotation gốc lẫn annotation tổng hợp. Tên annotation meta cho phép một implementation xử lý nhiều cách sử dụng, trong khi merged metadata đã hợp nhất các alias.

## 8. Đọc class-valued attributes mà không tải class sớm

Một annotation khác có thể nhận kiểu class:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Conditional(OnSupportedTypesCondition.class)
public @interface ConditionalOnSupportedTypes {
    Class<?>[] value();
}
~~~

Khi đọc thuộc tính, có hai lựa chọn:

~~~java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                ConditionalOnSupportedTypes.class.getName());
Class<?>[] types = (Class<?>[]) attributes.get("value");
~~~

Cách này trả về class references. Nếu các class có thể thuộc dependency tùy chọn và không nên được resolve quá sớm, dùng overload:

~~~java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                ConditionalOnSupportedTypes.class.getName(),
                true);

String[] classNames = (String[]) attributes.get("value");
~~~

Tham số \`classValuesAsString=true\` yêu cầu Spring chuyển class-valued attributes thành tên class dạng chuỗi thay vì trả về Class object. Điều này hữu ích khi condition chỉ cần kiểm tra class loader hoặc truyền tên class cho một API khác.

Đối với optional dependency, không để class tùy chọn xuất hiện trong chữ ký của configuration class hoặc method mà JVM có thể phải resolve trước khi condition bảo vệ được nó. Dùng class name trong metadata và tách configuration class có classpath condition khi cần.

## 9. Repeatable annotation và nhiều lần khai báo

Nếu một phần tử có thể nhận nhiều annotation cùng loại, Java cho phép khai báo annotation repeatable:

~~~java
@Repeatable(ConditionalOnRegions.List.class)
public @interface ConditionalOnRegions {
    String value();

    @Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @interface List {
        ConditionalOnRegions[] value();
    }
}
~~~

Ví dụ:

~~~java
@ConditionalOnRegions("eu")
@ConditionalOnRegions("apac")
class RegionalConfiguration {
}
~~~

Khi xử lý repeatable annotation, đừng giả định \`getAnnotationAttributes\` luôn trả về tất cả lần xuất hiện. Phương thức đó phù hợp để lấy một bộ thuộc tính merged của annotation tìm được.

Spring Framework 6.1 bổ sung \`getMergedRepeatableAnnotationAttributes(...)\` để lấy tập thuộc tính của các annotation repeatable trong hierarchy, có hỗ trợ \`@AliasFor\`. Cần chỉ định annotation type và container type tương ứng.

Nếu nhiều annotation có ý nghĩa kết hợp logic (AND/OR), hãy công bố semantics rõ:
- AND: tất cả region/policy phải cùng thỏa.
- OR: chỉ cần một region/policy thỏa.
- Một annotation có danh sách giá trị thường dễ hiểu hơn nếu logic là “một trong các region được phép”.

Không dùng repeatable annotation nếu người đọc không thể dự đoán cách các lần khai báo được kết hợp.

## 10. Kiểm thử bằng ApplicationContextRunner

Một condition đúng cần được kiểm tra ở nơi Spring thật sự đọc annotation metadata và đăng ký bean. Có thể dùng \`ApplicationContextRunner\` để tạo context nhỏ cho từng trường hợp.

Các trường hợp tối thiểu:

| Trường hợp | Property | Annotation | Kết quả |
| --- | --- | --- | --- |
| Region hợp lệ | \`eu\` | \`{"eu","apac"}\` | Bean được đăng ký |
| Region khác | \`us\` | \`{"eu","apac"}\` | Bean không được đăng ký |
| Property thiếu | Không có | \`matchIfMissing=false\` | Không đăng ký |
| Property thiếu | Không có | \`matchIfMissing=true\` | Đăng ký |
| Annotation tổng hợp | \`apac\` | \`@ConditionalOnRegions({"eu","apac"})\` | Đăng ký |
| Method-level condition | \`eu\` | Hai bean có policy khác nhau | Chỉ bean phù hợp được đăng ký |

**Tệp:** \`src/test/java/example/region/OnRegionConditionTest.java\`

~~~java
package example.region;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class OnRegionConditionTest {

    @Test
    void classLevelConditionMatchesAllowedRegion() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ClassRegionAutoConfiguration.class))
                .withPropertyValues("acme.region=APAC")
                .run(context ->
                        assertThat(context).hasSingleBean(RegionFeature.class));
    }

    @Test
    void classLevelConditionRejectsUnsupportedRegion() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ClassRegionAutoConfiguration.class))
                .withPropertyValues("acme.region=us")
                .run(context ->
                        assertThat(context).doesNotHaveBean(RegionFeature.class));
    }

    @Test
    void methodLevelConditionsAreEvaluatedIndependently() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MethodRegionAutoConfiguration.class))
                .withPropertyValues("acme.region=eu")
                .run(context -> {
                    assertThat(context).hasSingleBean(EuropeFeature.class);
                    assertThat(context).doesNotHaveBean(UsFallbackFeature.class);
                });
    }

    @Test
    void matchIfMissingControlsTheMissingPropertyCase() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MethodRegionAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(EuropeFeature.class);
                    assertThat(context).hasSingleBean(UsFallbackFeature.class);
                });
    }

    @Test
    void composedAnnotationAttributesAreMerged() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ComposedRegionAutoConfiguration.class))
                .withPropertyValues("acme.region=apac")
                .run(context ->
                        assertThat(context).hasSingleBean(ComposedRegionFeature.class));
    }

    static class RegionFeature {
    }

    static class EuropeFeature {
    }

    static class UsFallbackFeature {
    }

    static class ComposedRegionFeature {
    }

    @AutoConfiguration
    @ConditionalOnRegion({"eu", "apac"})
    static class ClassRegionAutoConfiguration {

        @Bean
        RegionFeature regionFeature() {
            return new RegionFeature();
        }
    }

    @AutoConfiguration
    static class MethodRegionAutoConfiguration {

        @Bean
        @ConditionalOnRegion({"eu", "apac"})
        EuropeFeature europeFeature() {
            return new EuropeFeature();
        }

        @Bean
        @ConditionalOnRegion(
                value = {"us"},
                matchIfMissing = true)
        UsFallbackFeature usFallbackFeature() {
            return new UsFallbackFeature();
        }
    }

    @AutoConfiguration
    @ConditionalOnRegions({"eu", "apac"})
    static class ComposedRegionAutoConfiguration {

        @Bean
        ComposedRegionFeature composedRegionFeature() {
            return new ComposedRegionFeature();
        }
    }
}
~~~

### 10.1. Giải thích từng test

- \`classLevelConditionMatchesAllowedRegion\`: annotation trên class đọc danh sách region; giá trị \`APAC\` được chuẩn hóa và khớp \`apac\`.
- \`classLevelConditionRejectsUnsupportedRegion\`: property \`us\` không nằm trong danh sách, nên configuration class bị bỏ qua.
- \`methodLevelConditionsAreEvaluatedIndependently\`: method EU/APAC được đăng ký; method US không được đăng ký.
- \`matchIfMissingControlsTheMissingPropertyCase\`: property thiếu khiến method EU/APAC không khớp, nhưng method US có \`matchIfMissing=true\` được đăng ký.
- \`composedAnnotationAttributesAreMerged\`: condition đọc thuộc tính của \`@ConditionalOnRegion\` qua annotation tổng hợp \`@ConditionalOnRegions\`; giá trị alias được merge đúng.

Các test chỉ kiểm tra bean registration. Chúng không tạo kết nối mạng hoặc gọi dịch vụ ngoài.

### 10.2. Dependency và lệnh chạy

Yêu cầu Java 17+, Spring Boot 3.3.x, JUnit 5 và AssertJ. Trong Gradle Groovy DSL, giả sử version được quản lý bằng Spring Boot plugin hoặc BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.region.OnRegionConditionTest"

# Windows
gradlew.bat test --tests "example.region.OnRegionConditionTest"
~~~

**Kết quả kỳ vọng:** năm test PASS. Test dùng assertion, không có \`System.out.println\`, vì vậy không có stdout nội dung cố định của ứng dụng. Gradle/JUnit sẽ hiển thị số test pass/fail theo cấu hình logging của dự án.

Đây là mã ví dụ dành cho Spring Boot 3.3 và Java 17+; cần chạy trong module thực tế để xác nhận dependency version, package và cấu hình build của dự án. Mã được review theo API đã dẫn, chưa được thực thi trong module hiện tại.

## 11. Chẩn đoán condition không khớp

Nếu bean không xuất hiện, kiểm tra theo thứ tự:

1. Annotation có được gắn lên đúng class hoặc method không?
2. Annotation có \`@Retention(RUNTIME)\` không?
3. Annotation có \`@Conditional(OnRegionCondition.class)\` hoặc meta-annotation chain hợp lệ không?
4. \`metadata.getAnnotationAttributes(...)\` có trả về Map không?
5. Thuộc tính có đúng tên và kiểu không?
6. Property có được đặt trong Environment tại thời điểm condition chạy không?
7. Giá trị có khoảng trắng, chữ hoa/thường hoặc định dạng không như mong đợi không?
8. Nếu dùng composed annotation, \`@AliasFor\` có đúng target attribute, đúng kiểu và default tương thích không?
9. Condition được đặt ở class-level hay method-level? Có phải một class-level condition đã loại toàn bộ cấu hình trước khi method được xét không?
10. Auto-configuration có được đưa vào context và thứ tự xử lý có phù hợp không?

### 11.1. Bật Condition Evaluation Report

Với ứng dụng Spring Boot, chạy:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot có thể hiển thị Condition Evaluation Report. Nếu condition kế thừa \`SpringBootCondition\` và trả về \`ConditionOutcome\` có message, log sẽ giải thích vì sao condition khớp hoặc không khớp.

Một message tốt cần cho biết:
- Property nào được đọc.
- Giá trị thực tế là gì.
- Các giá trị mong đợi là gì.
- Property bị thiếu có được chấp nhận hay không.

Tránh message chung chung như “condition failed”. Một câu giải thích cụ thể giúp người sử dụng starter tự xử lý mà không phải debug framework.

## 12. ConfigurationCondition: khi cần chọn phase đánh giá

\`Condition\` cơ bản được đánh giá ngay trước khi bean definition liên quan được đăng ký. Nếu logic cần kiểm soát rõ **giai đoạn parse configuration** hay **giai đoạn register bean**, Spring cung cấp \`ConfigurationCondition\`.

Hai phase:

| Phase | Thời điểm |
| --- | --- |
| \`PARSE_CONFIGURATION\` | Khi một \`@Configuration\` class đang được parse; nếu không khớp, class không được thêm vào |
| \`REGISTER_BEAN\` | Khi đăng ký một bean thông thường; tất cả configuration classes đã được parse |

Một condition triển khai \`ConfigurationCondition\` phải cung cấp thêm:

~~~java
@Override
public ConfigurationPhase getConfigurationPhase() {
    return ConfigurationPhase.REGISTER_BEAN;
}
~~~

Không chọn phase tùy ý. Nếu condition chỉ đọc property hoặc tham số annotation, \`Condition\` thông thường thường đủ. Nếu condition phụ thuộc bean definitions được đăng ký bởi các configuration classes, hãy xem xét phase và thứ tự auto-configuration. Với các trường hợp phổ biến, ưu tiên annotation có sẵn như \`@ConditionalOnBean\` thay vì tự viết logic registry phức tạp.

## 13. Lỗi thường gặp khi viết annotation điều kiện riêng

1. **Quên \`@Retention(RUNTIME)\`.** Metadata runtime không thể đọc annotation theo cách mong muốn.
2. **Không thêm \`ElementType.ANNOTATION_TYPE\` khi annotation cần được dùng làm meta-annotation.** Annotation tổng hợp sẽ không biên dịch hoặc không thể được áp dụng như thiết kế.
3. **Đọc sai annotation name.** Condition tìm annotation khác với annotation đang được gắn; dùng tên đầy đủ từ \`YourAnnotation.class.getName()\`.
4. **Ép kiểu thuộc tính không đúng.** \`String[]\` bị ép thành \`String\` hoặc Boolean bị đọc thành chuỗi; kiểm tra đúng kiểu khai báo.
5. **Không xử lý property thiếu.** Condition vô tình bật/tắt feature ngoài ý muốn; định nghĩa rõ \`matchIfMissing\`.
6. **So sánh chuỗi không chuẩn hóa.** \`EU\`, \`eu\` và \` eu \` có thể cho kết quả khác nhau; công bố quy tắc normalize và thực hiện nhất quán.
7. **Dùng \`getAllAnnotationAttributes\` khi cần alias merge.** Phương thức này không áp dụng override từ composed annotation; dùng \`getAnnotationAttributes\` cho merged attributes.
8. **Dùng reflection để lấy annotation instance khi chỉ cần metadata.** Việc đó có thể buộc tải class hoặc làm mất lợi ích metadata; ưu tiên \`AnnotatedTypeMetadata\`.
9. **Gọi \`getBean\` trong condition.** Có thể khởi tạo bean quá sớm và tạo vòng phụ thuộc; kiểm tra metadata/bean definitions.
10. **Gọi dịch vụ ngoài trong condition.** Startup phụ thuộc mạng, kết quả không ổn định và khó test; chuyển kiểm tra runtime sang component phù hợp.
11. **Đặt condition quá rộng.** Một method-level policy có thể vô tình được đặt ở class-level và loại cả configuration.
12. **Không kiểm thử annotation tổng hợp.** Code trực tiếp hoạt động nhưng alias không được merge; thêm test cho composed annotation.
13. **Không kiểm thử property thiếu.** Default của annotation có thể thay đổi hành vi; có test riêng cho \`matchIfMissing\`.
14. **Tạo condition mutable hoặc giữ cache theo context.** Một instance condition có thể được dùng ở nhiều lần đánh giá; giữ implementation stateless.
15. **Không cung cấp lý do no-match.** Người dùng không biết property/annotation nào khiến bean bị bỏ qua; dùng \`SpringBootCondition\` và \`ConditionOutcome\` khi viết Boot integration.

## 14. Checklist review một custom condition

- [ ] Annotation có target đúng (TYPE, METHOD, ANNOTATION_TYPE nếu cần).
- [ ] Retention là RUNTIME.
- [ ] Annotation được meta-annotate bằng \`@Conditional\`.
- [ ] Tên và kiểu thuộc tính có ý nghĩa rõ ràng.
- [ ] Default value và hành vi khi property thiếu được tài liệu hóa.
- [ ] Condition đọc attributes qua \`AnnotatedTypeMetadata\`.
- [ ] Merged attributes được dùng nếu có composed annotation.
- [ ] \`@AliasFor\` có target, kiểu và default hợp lệ.
- [ ] Condition chỉ đọc Environment/metadata/registry cần thiết.
- [ ] Không lấy bean instance hoặc gọi I/O trong condition.
- [ ] Có test class-level, method-level, match/no-match và missing property.
- [ ] Có test composed annotation nếu API hỗ trợ alias.
- [ ] Có message chẩn đoán nếu dùng Spring Boot auto-configuration.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Trong \`Condition.matches(context, metadata)\`, metadata mô tả điều gì?

**Đáp án:** Metadata của class hoặc method đang được kiểm tra. Vì vậy condition có thể dùng cho cả configuration class và \`@Bean\` method.

**Câu 2.** Cách lấy tham số \`value\` của \`@ConditionalOnRegion\` là gì?

**Đáp án:** Gọi \`metadata.getAnnotationAttributes(ConditionalOnRegion.class.getName())\`, sau đó đọc \`attributes.get("value")\` và ép kiểu theo khai báo \`String[]\`.

**Câu 3.** Vì sao dùng \`getAnnotationAttributes\` khi có \`@AliasFor\`?

**Đáp án:** Phương thức này trả về merged annotation attributes và hỗ trợ alias trong annotation hierarchy. \`getAllAnnotationAttributes\` không áp dụng override từ composed annotation.

**Câu 4.** Một condition có nên gọi \`context.getBean(MyService.class)\` để xem service đã hoạt động chưa?

**Đáp án:** Không. Condition không nên tương tác với bean instances. Hãy kiểm tra bean definitions hoặc dùng \`@ConditionalOnBean\` khi chỉ cần biết bean có tồn tại.

**Câu 5.** Khi property không tồn tại, condition nên xử lý thế nào?

**Đáp án:** Theo contract của annotation. Ví dụ \`matchIfMissing=false\` thì không khớp; \`true\` thì khớp. Phải kiểm thử cả hai trường hợp.

**Câu 6.** Khi nào nên dùng \`SpringBootCondition\` thay vì triển khai \`Condition\` trực tiếp?

**Đáp án:** Khi condition thuộc auto-configuration của Spring Boot và muốn có \`ConditionOutcome\`, log lý do match/no-match và hỗ trợ chẩn đoán trong Condition Evaluation Report.

## 16. Ghi nhớ

Một custom condition có ba phần gắn kết:

- **Annotation** định nghĩa contract và tham số mà người dùng khai báo.
- **AnnotatedTypeMetadata** cung cấp giá trị annotation đã được Spring đọc và merge, bao gồm meta-annotation và \`@AliasFor\`.
- **ConditionContext** cung cấp Environment và hạ tầng container để quyết định có đăng ký bean hay không.

Hãy giữ condition stateless, nhanh và không tạo side effect. Dùng \`getAnnotationAttributes\` để đọc một bộ giá trị đã merge; dùng overload class-values-as-string khi cần tránh resolve class-valued attributes; dùng API repeatable phù hợp khi annotation có thể xuất hiện nhiều lần. Với auto-configuration Spring Boot, kế thừa \`SpringBootCondition\` để cung cấp lý do match/no-match và giúp người dùng chẩn đoán.

### Tài liệu Spring Framework và Spring Boot chính thức

- [Spring Framework 6.1 — Condition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html)
- [Spring Framework 6.1 — ConditionContext Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html)
- [Spring Framework 6.1 — AnnotatedTypeMetadata Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html)
- [Spring Framework 6.1 — ConfigurationCondition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html)
- [Spring Boot 3.3 — SpringBootCondition Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html)
- [Spring Boot 3.3 — ConditionOutcome Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html)
