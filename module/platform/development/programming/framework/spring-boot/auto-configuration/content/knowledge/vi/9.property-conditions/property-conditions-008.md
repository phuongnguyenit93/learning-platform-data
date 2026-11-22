# Giới hạn khi kiểm tra thuộc tính danh sách hoặc phần tử có chỉ số trong Spring Boot Auto-Configuration

## 1. Vấn đề: “có danh sách” khác với “có khóa thuộc tính”

Khi viết auto-configuration, ta thường bật một bean theo cấu hình:

```java
@Bean
@ConditionalOnProperty(prefix = "demo", name = "recipients")
NotificationDispatcher notificationDispatcher() {
    return new NotificationDispatcher();
}
```

Ví dụ trên là **đoạn minh họa**, giả định lớp `NotificationDispatcher` đã có trong dự án. Ý định có thể là “chỉ đăng ký `NotificationDispatcher` nếu danh sách người nhận có ít nhất một phần tử”. Tuy nhiên, `@ConditionalOnProperty` **không kiểm tra trực tiếp nội dung một `List`**. Nó kiểm tra khóa và giá trị thuộc tính trong `Environment` tại thời điểm Spring xử lý điều kiện.

Đặc biệt, theo Javadoc Spring Boot 3.3, annotation này **không đáng tin cậy khi dùng để match collection property**: khóa cha `demo.recipients` và khóa phần tử `demo.recipients[0]` không thể coi là tương đương. Vì vậy, ứng dụng có danh sách hợp lệ nhưng condition vẫn không match.

Đây là bài học thuộc nhóm **điều kiện thuộc tính**, tập trung vào giới hạn khi dùng `@ConditionalOnProperty` với danh sách, mảng, phần tử có chỉ số và cấu hình lồng nhau.

## 2. Cơ chế của `@ConditionalOnProperty`

Ví dụ:

```java
@ConditionalOnProperty(
    prefix = "demo",
    name = "recipients",
    havingValue = "true",
    matchIfMissing = false
)
```

Các thuộc tính của annotation có ý nghĩa:

| Thuộc tính | Ý nghĩa |
|---|---|
| `prefix` | Tiền tố khóa, ví dụ `demo`. |
| `name` hoặc `value` | Tên khóa cần kiểm tra, ví dụ `recipients`; với `prefix` tạo khóa `demo.recipients`. |
| `havingValue` | So sánh **giá trị dạng chuỗi** của khóa được chỉ định; không dùng để duyệt `List`. |
| `matchIfMissing` | Kết quả nếu **khóa được kiểm tra** vắng mặt; mặc định `false`. |

Mặc định, khi không khai báo `havingValue`, condition match nếu khóa có mặt và giá trị **không bằng chuỗi `"false"`** (không phân biệt hoa/thường theo cơ chế điều kiện). Điều này không có nghĩa “giá trị khác rỗng” hay “danh sách có phần tử”. Khóa hiện diện với giá trị chuỗi rỗng cũng không tự động được hiểu là một danh sách rỗng cần bị từ chối.

Nếu `name` có nhiều khóa, **mọi khóa đều phải đạt** điều kiện; đây không phải biểu thức OR để thử một loạt cách đặt tên của list.

Một lưu ý quan trọng: `@ConditionalOnProperty` dựa vào việc có thể tìm được **khóa đang được hỏi** trong `Environment`. Ngược lại, cơ chế binding cấu hình của Spring Boot có thể tổng hợp nhiều khóa chỉ số thành `List<T>` bằng `Binder`. Hai cơ chế không tương đương.

## 3. Vì sao YAML list và `.properties` có thể cho kết quả khác?

Xét `application.yml`:

```yaml
demo:
  recipients:
    - alice@example.test
    - bob@example.test
```

Khi tải YAML vào `Environment`, các phần tử của danh sách thường được biểu diễn thành các khóa phẳng như sau:

```properties
demo.recipients[0]=alice@example.test
demo.recipients[1]=bob@example.test
```

Bản chất là tồn tại các khóa `demo.recipients[0]` và `demo.recipients[1]`. Không thể suy ra rằng `Environment` đồng thời có một giá trị chuỗi độc lập tại khóa cha `demo.recipients`.

Trong khi đó, `application.properties` cũng có thể dùng một giá trị chuỗi trên chính khóa cha:

```properties
demo.recipients=alice@example.test,bob@example.test
```

Bảng sau mô tả cách đọc **trong tình huống chỉ có đúng các khóa được nêu** và dùng `@ConditionalOnProperty(prefix = "demo", name = "recipients")` với giá trị mặc định:

| Dữ liệu trong nguồn thuộc tính | Có khóa `demo.recipients` độc lập? | Condition kiểm tra khóa cha | Có thể bind thành `List<String>`? |
|---|---|---|---|
| `demo.recipients=alice@example.test,bob@example.test` | Có | Match, vì giá trị không phải `"false"` | Có, hai phần tử |
| `demo.recipients[0]=alice@example.test` | Không | **Không match** | Có, một phần tử |
| `demo.recipients[0]=alice...` và `[1]=bob...` | Không | **Không match** | Có, hai phần tử |
| Không cấu hình `demo.recipients` | Không | Không match, mặc định `matchIfMissing=false` | Không có danh sách để bind |

Bảng chỉ nói về các nguồn thuộc tính được mô tả. Trong ứng dụng thật, khóa cha có thể đến từ nguồn khác (file profile, biến môi trường, tham số CLI), làm kết quả condition khác dự đoán nếu chỉ nhìn một file.

**Phân biệt quan trọng:**

- `Environment#getProperty("demo.recipients")` truy xuất giá trị cho một tên khóa. Đừng mặc định API này tự ghép mọi khóa có chỉ số thành một chuỗi danh sách.
- `Binder` biết cách bind ký hiệu `[index]` thành `List` theo quy tắc cấu hình của Spring Boot.
- `@ConfigurationProperties` cũng dùng cơ chế binding kiểu dữ liệu; bean cấu hình có `List<String>` hoạt động được **không chứng minh** `@ConditionalOnProperty(name = "recipients")` sẽ match.

Khi dùng YAML list trong auto-configuration, đây là nguồn gốc thường gặp của hiện tượng “đã cấu hình phần tử rồi nhưng bean không được tạo”.

## 4. Vì sao kiểm tra `[0]` không phải giải pháp tổng quát?

Có thể viết:

```java
@ConditionalOnProperty(prefix = "demo", name = "recipients[0]")
```

Điều này kiểm tra **đúng khóa** `demo.recipients[0]`. Với nguồn thuộc tính có khóa đó, condition có thể match. Tuy nhiên, nó vẫn là một phép kiểm tra **một khóa đơn**, nên:

1. Không thể khẳng định **toàn bộ danh sách đã bind thành công**.
2. Không kiểm tra kích thước danh sách, phần tử hợp lệ, giá trị blank hoặc quy tắc nghiệp vụ.
3. Phụ thuộc việc dữ liệu được biểu diễn bằng `[0]`. Nếu nguồn dùng một giá trị chuỗi trên khóa cha hoặc một cơ chế property source khác, khóa `[0]` có thể không hiện diện.
4. Với danh sách các object, `demo.routes[0]` và `demo.routes[0].url` là hai tên khác nhau. Một property source có thể chỉ đưa ra các khóa con, không có khóa cho object cha.
5. Việc khai báo nhiều chỉ số trong `name` không biến annotation thành “có ít nhất một phần tử”, vì nhiều tên mặc định được kết hợp theo logic AND.

Ví dụ `@ConditionalOnProperty(name = "routes[0].url")` chỉ trả lời câu hỏi **khóa `routes[0].url` có thỏa điều kiện hay không**. Nó không kiểm tra rằng có route hợp lệ ở các chỉ số khác, hoặc toàn bộ danh sách đã được bind và validate.

Do vậy, dùng khóa chỉ số trực tiếp chỉ thích hợp khi yêu cầu nghiệp vụ **thực sự là kiểm tra chính khóa cố định đó**, chứ không phải nhận biết một collection.

## 5. Cách làm đúng khi cần điều kiện “danh sách có ít nhất một giá trị hợp lệ”

Khi quyết định tạo bean phụ thuộc vào nội dung list, hãy viết một `Condition` riêng, bind cấu hình bằng `Binder` rồi đánh giá ý nghĩa nghiệp vụ của dữ liệu.

Ví dụ, chỉ bật bean khi `demo.recipients` có ít nhất một chuỗi **không rỗng và không chỉ chứa khoảng trắng**:

```java
import java.util.List;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class NonEmptyRecipientsCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        List<String> recipients = Binder.get(context.getEnvironment())
                .bind("demo.recipients", Bindable.listOf(String.class))
                .orElse(List.of());

        return recipients.stream()
                .anyMatch(value -> value != null && !value.isBlank());
    }
}
```

Đây là mã **hoàn chỉnh của một lớp điều kiện**, lưu vào `NonEmptyRecipientsCondition.java` trong package đã chọn và thêm khai báo `package` phù hợp. Điều kiện được gắn lên phương thức `@Bean` hoặc lớp cấu hình bằng `@Conditional(NonEmptyRecipientsCondition.class)`.

Cơ chế:

1. `ConditionContext` cung cấp `Environment` đang dùng để xử lý điều kiện.
2. `Binder.get(environment)` truy cập cách Spring Boot bind cấu hình từ các nguồn thuộc tính.
3. `bind("demo.recipients", Bindable.listOf(String.class))` thử dựng `List<String>` từ khóa cha dạng chuỗi hoặc từ các khóa `[0]`, `[1]`, ...
4. `orElse(List.of())` trả về danh sách rỗng khi không có dữ liệu bind được.
5. `anyMatch(...)` áp dụng quy tắc **ít nhất một phần tử có nội dung**. Nếu yêu cầu là tất cả phần tử hợp lệ, hãy dùng tiêu chí kiểm tra khác, ví dụ không rỗng và `allMatch(...)`.

Ví dụ trên giả định mỗi phần tử là chuỗi. Nếu cấu hình chứa object, hãy bind sang danh sách của kiểu dữ liệu phù hợp và kiểm tra những field cần thiết; không ép cấu trúc object thành `List<String>`.

**Lưu ý về lỗi cấu hình:** `Binder` có thể phát sinh lỗi binding với dữ liệu sai kiểu hoặc cấu trúc không hợp lệ. Đừng mặc định mọi lỗi phải được nuốt thành `false`; ứng dụng có thể cần báo lỗi cấu hình rõ ràng để người vận hành sửa.

## 6. Ví dụ kiểm thử chạy được: so sánh điều kiện trực tiếp với `Binder`

Dưới đây là **một tệp test Java độc lập trong dự án Spring Boot 3.3 với Java 17+ và JUnit 5**, dùng `ApplicationContextRunner`. Các class tĩnh nằm cùng tệp để dễ chạy, không cần web server.

Đặt tệp tại `src/test/java/demo/IndexedCollectionConditionTest.java`:

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.type.AnnotatedTypeMetadata;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IndexedCollectionConditionTest {

    // Điều kiện ngây thơ: chỉ hỏi Environment có khóa cha hay không.
    @Configuration(proxyBeanMethods = false)
    static class DirectPropertyConfiguration {
        @Bean
        @ConditionalOnProperty(prefix = "demo", name = "recipients")
        String directMarker() {
            return "direct";
        }
    }

    // Điều kiện phù hợp khi ý định là có ít nhất một phần tử hữu ích.
    public static final class HasRecipientsCondition implements Condition {
        @Override
        public boolean matches(
                ConditionContext context,
                AnnotatedTypeMetadata metadata) {

            List<String> recipients = Binder.get(context.getEnvironment())
                    .bind("demo.recipients", Bindable.listOf(String.class))
                    .orElse(List.of());

            return recipients.stream()
                    .anyMatch(value -> value != null && !value.isBlank());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BoundListConfiguration {
        @Bean
        @Conditional(HasRecipientsCondition.class)
        String boundMarker() {
            return "bound";
        }
    }

    @Test
    void indexedValuesDoNotMatchTheParentKey() {
        new ApplicationContextRunner()
                .withUserConfiguration(DirectPropertyConfiguration.class)
                .withPropertyValues(
                        "demo.recipients[0]=alice@example.test",
                        "demo.recipients[1]=bob@example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("directMarker"))
                );
    }

    @Test
    void binderFindsTheIndexedValues() {
        new ApplicationContextRunner()
                .withUserConfiguration(BoundListConfiguration.class)
                .withPropertyValues(
                        "demo.recipients[0]=alice@example.test",
                        "demo.recipients[1]=bob@example.test"
                )
                .run(context ->
                        assertTrue(context.containsBean("boundMarker"))
                );
    }

    @Test
    void missingListDoesNotCreateTheBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(BoundListConfiguration.class)
                .run(context ->
                        assertFalse(context.containsBean("boundMarker"))
                );
    }

    @Test
    void aBlankIndexedElementDoesNotActivateTheBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(BoundListConfiguration.class)
                .withPropertyValues("demo.recipients[0]= ")
                .run(context ->
                        assertFalse(context.containsBean("boundMarker"))
                );
    }

    @Test
    void commaSeparatedRootValueCanMatchBothConditions() {
        new ApplicationContextRunner()
                .withUserConfiguration(
                        DirectPropertyConfiguration.class,
                        BoundListConfiguration.class
                )
                .withPropertyValues(
                        "demo.recipients=alice@example.test,bob@example.test"
                )
                .run(context -> {
                    assertTrue(context.containsBean("directMarker"));
                    assertTrue(context.containsBean("boundMarker"));
                });
    }
}
```

Các test sử dụng `assertTrue`/`assertFalse` đối với **tên bean**, tránh cần lấy một `String` theo kiểu khi có hai marker cùng loại. Mỗi `ApplicationContextRunner` tạo một context riêng biệt để không lẫn property giữa các kịch bản.

### Phụ thuộc và cách chạy

Dự án Spring Boot cần dependency test thích hợp, thường có:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Chạy từ thư mục dự án Gradle:

```bash
./gradlew test --tests demo.IndexedCollectionConditionTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.IndexedCollectionConditionTest
```

**Kết quả mong đợi:** năm test đều pass. Đặc biệt, với hai khóa chỉ số, `directMarker` **không được tạo** nhưng `boundMarker` **được tạo**; khi không có list hoặc chỉ có một giá trị toàn khoảng trắng, `boundMarker` không được tạo. Kỳ vọng này dựa trên cách binding/condition được mô tả cho Spring Boot 3.3; cần chạy bộ test trên dự án thực tế để xác nhận với dependency và cấu hình đang sử dụng.

**Nếu đã có lớp condition tại mục 5:** trong mã sản phẩm, dùng lớp đó; `HasRecipientsCondition` lồng trong test chỉ để ví dụ có thể chạy độc lập.

## 7. Cách khác khi chỉ cần công tắc bật/tắt tính năng

Nếu ý định thật là “người vận hành cho phép hệ thống gửi thông báo”, một **thuộc tính boolean đơn** dễ hiểu và đáng tin hơn làm điều kiện bật bean:

```yaml
demo:
  notifications:
    enabled: true
    recipients:
      - alice@example.test
      - bob@example.test
```

```java
@Bean
@ConditionalOnProperty(
    prefix = "demo.notifications",
    name = "enabled",
    havingValue = "true"
)
NotificationDispatcher notificationDispatcher() {
    return new NotificationDispatcher();
}
```

Ở đây `NotificationDispatcher` là lớp ứng dụng giả định; đoạn Java chỉ minh họa vị trí đặt annotation trên một phương thức bean có sẵn.

Điều kiện chỉ phụ thuộc vào `demo.notifications.enabled`, không phụ thuộc cách biểu diễn list. Tuy nhiên, `enabled=true` **không đảm bảo** danh sách `recipients` có phần tử hợp lệ. Cần bind và **validate** dữ liệu cấu hình theo nhu cầu ứng dụng (ví dụ qua `@ConfigurationProperties` và Jakarta Bean Validation, nếu dự án cấu hình validation).

Lựa chọn phụ thuộc yêu cầu:

| Nhu cầu thực sự | Cách phù hợp |
|---|---|
| Bật tính năng dựa trên một cờ rõ ràng | `@ConditionalOnProperty` trên `enabled`, thường kết hợp `havingValue="true"` |
| Tạo bean khi list có phần tử hợp lệ | Custom `Condition` + `Binder` + predicate |
| Chỉ cần kiểm tra một khóa chỉ số cụ thể | Kiểm tra đúng tên `items[0]`, hiểu rõ giới hạn |
| Kiểm tra object trong list có đủ field | Bind kiểu cấu trúc tương ứng rồi validate/đánh giá field |

## 8. Các góc cạnh khi dữ liệu đến từ nhiều nguồn

### 8.1. Danh sách khác một thuộc tính scalar

`@ConditionalOnProperty` làm việc trên giá trị chuỗi được báo cáo cho khóa được chỉ định; nó không có tham số `minimumSize`, không tự gọi `isEmpty()`, không kiểm tra `List` sau binding. `havingValue="true"` không làm một phần tử `[0]` tự thỏa điều kiện trên khóa cha; `matchIfMissing=true` chỉ cho phép một khóa **thiếu** vẫn match và vì vậy càng không diễn đạt được “list không rỗng”.

### 8.2. Relaxed binding và biến môi trường

Spring Boot hỗ trợ nhiều dạng tên khi bind, nhưng không có nghĩa tất cả dạng property source đều thể hiện list giống nhau. Với object-list, tài liệu Boot mô tả quy tắc biến môi trường như sau:

```properties
my.service[0].other=abc
```

Trên hệ điều hành hỗ trợ cách đặt tên biến môi trường chuẩn, dạng tương ứng thường là `MY_SERVICE_0_OTHER`. Binder nhận biết ký hiệu này theo quy tắc riêng của source; đừng nối chuỗi hoặc dự đoán khóa mà một lệnh `Environment#getProperty` đơn lẻ sẽ nhìn thấy. Kiểm thử bằng chính dạng config sẽ được deploy là cách xác minh tốt nhất.

### 8.3. Danh sách từ nhiều property source không nhất thiết được ghép

Với list, Spring Boot quy định quy tắc ưu tiên cấu hình: cấu hình có độ ưu tiên cao hơn thường **thay thế toàn bộ list** ở độ ưu tiên thấp hơn, thay vì ghép mọi phần tử từ nhiều profile/file. Một custom condition dùng Binder sẽ đánh giá list đã được bind theo quy tắc đó. Không tự cộng các `[index]` của mọi source để phán đoán kết quả.

### 8.4. Chỉ số không liên tục và kiểu dữ liệu sai

Ký hiệu `[index]` dùng index để mô tả vị trí phần tử; cấu hình có lỗ hổng chỉ số, phần tử object thiếu field hoặc giá trị không chuyển đổi được có thể dẫn tới binding không như mong đợi, thậm chí lỗi binding. Đừng xây dựng thuật toán “tìm thấy một `[n]` bất kỳ tức là danh sách hợp lệ”. Sử dụng cấu hình liên tục, kiểu dữ liệu đúng và test riêng các trường hợp lỗi quan trọng.

### 8.5. Điều kiện được tính tại lúc đăng ký bean

Giống các condition khác, `@ConditionalOnProperty`/`@Conditional` có hiệu lực khi Spring xử lý cấu hình và đăng ký định nghĩa bean. Đổi cấu hình runtime không tự khiến bean đã bỏ qua trước đó được tạo ngay lập tức hoặc bean đang có bị xóa. Khi cần bật/tắt động trong lúc chạy, đó là thiết kế runtime riêng, không thể chỉ dựa vào annotation khởi động.

## 9. Lỗi thường gặp và cách chẩn đoán

1. **Thấy `@ConfigurationProperties` bind được list nhưng `@ConditionalOnProperty` không match.** Hai cơ chế khác nhau; xem tên khóa thực tế: `list` so với `list[0]`.
2. **Dùng `havingValue="true"` trên khóa danh sách.** Điều kiện cần giá trị scalar bằng `true`, không kiểm tra “có phần tử”.
3. **Dùng `matchIfMissing=true` để khắc phục danh sách bị bỏ sót.** Đây là thay đổi logic sang “thiếu khóa vẫn bật”, có thể tạo bean ngay cả khi không có dữ liệu.
4. **Tưởng `name={"items[0]", "items[1]"}` nghĩa là một trong hai.** Thực tế các tên phải cùng thỏa điều kiện, không diễn tả ít nhất một phần tử.
5. **Kiểm tra chỉ `items[0]` và cho rằng toàn bộ list hợp lệ.** Một khóa tồn tại không đủ để bảo đảm mọi object trong list có đủ field hoặc giá trị hữu ích.
6. **Dùng điều kiện trong khi còn thiếu dữ liệu cấu hình liên quan.** Auto-configuration nên được kiểm thử với các kiểu nguồn cấu hình mà ứng dụng hỗ trợ; nếu có thứ tự đăng ký bean hoặc nguồn cấu hình tùy biến, kiểm tra thời điểm áp dụng.
7. **Cho rằng kết quả từ file YAML duy nhất là toàn bộ dữ liệu.** Profile, CLI, biến môi trường và các property source khác có thể thay đổi giá trị và độ ưu tiên.

Để điều tra:

- Bật chế độ `--debug` khi chạy ứng dụng Spring Boot để xem báo cáo đánh giá điều kiện.
- Nếu đã sử dụng Actuator và được cấu hình phù hợp, có thể xem endpoint `/actuator/conditions`; kiểm tra condition match/no-match của auto-configuration liên quan.
- Tạo test `ApplicationContextRunner` cho ít nhất: khóa cha phân tách dấu phẩy, phần tử `[0]`, nhiều phần tử `[0]/[1]`, không có cấu hình, dữ liệu blank và profile/source có độ ưu tiên khác nhau nếu hệ thống có dùng.
- Khi binding phức tạp, test trực tiếp dữ liệu bind thành `List<T>`, rồi mới kiểm thử quyết định tạo bean. Không suy luận chỉ từ việc có `PropertySource`.

## 10. Kết luận áp dụng

**Câu hỏi đúng phải là:** “Tôi muốn biết **khóa** có mặt, hay muốn biết **danh sách sau khi bind** có dữ liệu hợp lệ?”

- Khi kiểm tra một **scalar property** (đặc biệt là cờ boolean), `@ConditionalOnProperty` phù hợp và dễ đọc.
- Khi kiểm tra **collection**, `@ConditionalOnProperty(name = "some-list")` có thể không match dù `some-list[0]` tồn tại. Javadoc Spring Boot khuyến nghị dùng custom condition cho tình huống này.
- `Binder` cùng điều kiện nghiệp vụ mới diễn đạt được “ít nhất một phần tử”, “tất cả phần tử hợp lệ” hay quy tắc phức tạp trên cấu trúc list.
- Không biến `matchIfMissing`, `havingValue` hoặc một chỉ số cố định thành cách thay thế cho kiểm tra collection.
- Phải test bằng dạng cấu hình thực tế vì YAML, `.properties`, biến môi trường và thứ tự ưu tiên nguồn thuộc tính có thể ảnh hưởng cách các khóa xuất hiện.

### Tài liệu chính thức

- Spring Boot 3.3 `ConditionalOnProperty` Javadoc — lưu ý rõ giới hạn đối với collection: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 `Binder` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot 3.3 Reference — Externalized Configuration (YAML lists, binding, property-source precedence): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
