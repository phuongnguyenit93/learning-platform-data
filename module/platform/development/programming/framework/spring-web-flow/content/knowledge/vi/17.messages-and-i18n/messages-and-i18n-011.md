# Kiểm thử mã thông báo thay vì phụ thuộc một bản dịch

Trong chương **Thông báo và ngôn ngữ**, bài này trình bày cách kiểm thử thông báo của một flow Spring Web Flow bằng mã thông báo ổn định thay vì so sánh nguyên văn câu chữ đã dịch. Với module **SPRING_WEB_FLOW**, state, event, transition và subflow điều khiển hành trình nhiều bước; form binding và validation tạo ra các thông báo gắn với trường dữ liệu hoặc kết quả nghiệp vụ. Khi ứng dụng hỗ trợ nhiều ngôn ngữ, nội dung hiển thị có thể thay đổi theo locale, nhưng mã thông báo mô tả ý nghĩa của lỗi cần giữ ổn định để kiểm thử không bị gắn chặt với một bản dịch.

Một bài kiểm thử chỉ so sánh câu “Mã bưu chính không hợp lệ” sẽ dễ hỏng khi nhóm nội dung sửa câu chữ, thay cách viết hoa hoặc điều chỉnh bản dịch tiếng Anh. Điều cần xác nhận là validator phát đúng mã lỗi, thông báo được gắn với đúng trường, mức độ phù hợp và có thể được phân giải theo locale đang hoạt động.

## Mã thông báo và câu dịch là hai lớp khác nhau

Một thông báo thường có hai phần:

- **Message code:** định danh ổn định cho một ý nghĩa, ví dụ SHIPPING_POSTAL_CODE_INVALID.
- **Localized message:** câu chữ hiển thị cho người dùng theo ngôn ngữ và vùng, ví dụ bản tiếng Việt hoặc tiếng Anh.

Mã thông báo là hợp đồng giữa logic nghiệp vụ, validation, resource bundle và kiểm thử. Câu dịch là nội dung trình bày, có thể được biên tập mà không cần thay đổi logic.

| Lớp | Ví dụ | Có nên thay đổi khi biên tập bản dịch? |
|---|---|---|
| Message code | SHIPPING_POSTAL_CODE_INVALID | Không |
| Field source | postalCode | Không, trừ khi model field thay đổi có chủ đích |
| Arguments | độ dài tối thiểu, tên loại dịch vụ | Chỉ khi hợp đồng tham số thay đổi |
| Severity | error, warning, info | Chỉ khi ý nghĩa xử lý thay đổi |
| Bản dịch tiếng Việt | “Mã bưu chính không hợp lệ” | Có thể |
| Bản dịch tiếng Anh | “The postal code is invalid” | Có thể |

Ví dụ, cùng một mã SHIPPING_POSTAL_CODE_INVALID có thể được phân giải thành câu tiếng Việt hoặc tiếng Anh. Nếu kiểm thử so sánh nguyên văn một câu, nó đang kiểm tra quyết định biên tập nội dung thay vì kiểm tra hợp đồng của flow.

~~~mermaid
flowchart TD
    A["Người dùng gửi form"] --> B["Flow nhận event"]
    B --> C["Validator kiểm tra dữ liệu"]
    C --> D["Tạo message code + source + arguments + severity"]
    D --> E["MessageContext"]
    E --> F["MessageSource và locale hiện tại"]
    F --> G["Câu dịch được phân giải"]
    G --> H["View hiển thị lỗi"]
    I["Unit test"] --> J["Kiểm tra message code và source"]
    K["Integration test"] --> L["Kiểm tra message được phân giải và hiển thị"]
~~~

Kiểm thử nên kiểm tra đúng lớp đang chịu trách nhiệm. Validator chịu trách nhiệm chọn mã lỗi và trường liên quan; MessageSource chịu trách nhiệm phân giải mã theo locale; view chịu trách nhiệm trình bày thông báo. Tách các hợp đồng này giúp xác định lỗi nhanh hơn.

## Thiết kế message code ổn định

Một message code tốt mô tả ý nghĩa nghiệp vụ hoặc lỗi, không mô tả câu dịch hay vị trí giao diện. Có thể dùng quy ước phân cấp theo miền nghiệp vụ, đối tượng và tình huống.

Ví dụ:

| Message code | Ý nghĩa |
|---|---|
| BOOKING_RECIPIENT_REQUIRED | Thiếu tên người nhận |
| SHIPPING_POSTAL_CODE_INVALID | Mã bưu chính không hợp lệ |
| SHIPPING_ADDRESS_UNSUPPORTED | Địa chỉ nằm ngoài vùng phục vụ |
| PAYMENT_METHOD_EXPIRED | Phương thức thanh toán đã hết hạn |
| CHECKOUT_ORDER_UNAVAILABLE | Đơn hàng không còn khả dụng |

Một số nguyên tắc:

1. Dùng một mã cho một ý nghĩa ổn định. Nếu cùng một lỗi xuất hiện ở nhiều view-state, hãy tái sử dụng mã đó.
2. Không đưa câu dịch vào mã, chẳng hạn MESSAGE_MA_BUU_CHINH_KHONG_HOP_LE.
3. Không gắn mã với tên màn hình hoặc nút bấm, chẳng hạn REVIEW_PAGE_ERROR.
4. Dùng mã riêng khi hai tình huống cần cách xử lý khác nhau, dù câu hiển thị có thể giống nhau.
5. Giữ tên mã nhất quán về chữ hoa/thường và quy ước phân tách.
6. Nếu đổi mã đã được dùng trong resource bundle hoặc kiểm thử, cập nhật các nơi tham chiếu như một thay đổi hợp đồng có chủ đích.

Không cần tạo mã riêng cho mọi biến thể câu chữ. Nếu hai thông báo có cùng ý nghĩa và cùng cách xử lý, một mã với arguments có thể đủ. Nếu người dùng cần hành động khác nhau hoặc mức độ lỗi khác nhau, nên dùng mã riêng.

## Đặt message trong Spring Web Flow

Spring Web Flow cung cấp MessageContext để action và validator thêm thông báo trong quá trình thực thi flow. Message có thể gắn với source, severity, code và arguments. View có thể hiển thị thông báo tổng quát hoặc thông báo gắn với một trường form.

Ví dụ validator có thể thêm lỗi cho trường postalCode:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;

public class ShippingValidator {

    public void validatePostalCode(
            String postalCode,
            MessageContext messageContext) {

        if (postalCode == null || !postalCode.matches("[0-9]{5,6}")) {
            messageContext.addMessage(
                new MessageBuilder()
                    .error()
                    .source("postalCode")
                    .code("SHIPPING_POSTAL_CODE_INVALID")
                    .defaultText("Mã bưu chính không hợp lệ")
                    .build()
            );
        }
    }
}
~~~

Trong ví dụ, source là postalCode nên view có thể gắn lỗi với control tương ứng. Code là định danh mà resource bundle dùng để tìm câu dịch. Default text cung cấp nội dung dự phòng nếu không tìm được mã trong MessageSource đã cấu hình. Bản dịch không nên được dùng làm định danh trong kiểm thử.

Flow gọi validator trong transition:

~~~xml
<view-state id="shipping"
            view="checkout/shipping"
            model="checkout">
    <binder>
        <binding property="postalCode" required="true" />
        <binding property="recipient" required="true" />
    </binder>

    <transition on="continue" to="review">
        <evaluate expression="shippingValidator.validatePostalCode(checkout.postalCode, messageContext)" />
    </transition>
</view-state>
~~~

Đây là ví dụ minh họa cách gắn lỗi với MessageContext. Trong flow thực tế, validator cần điều phối kết quả hợp lệ và không hợp lệ để flow chỉ chuyển tới review khi không còn lỗi chặn. Có thể dùng validator tích hợp với Spring Binding hoặc kiểm tra MessageContext trong action để giữ người dùng ở view-state hiện tại. Không nên giả định rằng chỉ gọi một phương thức thêm message là tự động ngăn mọi transition; điều kiện chuyển state phải được thiết kế rõ.

## Resource bundle cho nhiều locale

Message code được phân giải qua MessageSource của Spring. Ứng dụng thường có một bundle mặc định và các bundle theo locale. Ví dụ:

~~~properties
# messages.properties
SHIPPING_POSTAL_CODE_INVALID=The postal code is invalid.
BOOKING_RECIPIENT_REQUIRED=Recipient name is required.
SHIPPING_ADDRESS_UNSUPPORTED=The address is outside the service area.
~~~

~~~properties
# messages_vi.properties
SHIPPING_POSTAL_CODE_INVALID=Mã bưu chính không hợp lệ.
BOOKING_RECIPIENT_REQUIRED=Vui lòng nhập tên người nhận.
SHIPPING_ADDRESS_UNSUPPORTED=Địa chỉ nằm ngoài khu vực phục vụ.
~~~

Một cấu hình MessageSource có thể dùng ResourceBundleMessageSource:

~~~java
import org.springframework.context.MessageSource;
import org.springframework.context.support.ResourceBundleMessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MessageConfiguration {

    @Bean
    public MessageSource messageSource() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();

        source.setBasename("messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);
        return source;
    }
}
~~~

Cách đặt tên bundle và cách xác định locale phải thống nhất với cấu hình Spring MVC của ứng dụng. Locale có thể đến từ session, cookie, request parameter hoặc cơ chế khác đã chọn. Điều quan trọng là locale dùng để render view và locale dùng để phân giải message phải nhất quán trong cùng request.

Khi thêm một message code mới, hãy cập nhật các bundle được hỗ trợ. Nếu một locale chưa có bản dịch, ứng dụng cần có fallback đã định nghĩa và kiểm thử được. Không nên để một mã chưa phân giải xuất hiện nguyên văn trước người dùng mà không có chủ ý.

## Kiểm thử validator bằng message code

Ở lớp validator, kiểm tra mã lỗi và source giúp bảo đảm logic phát đúng loại thông báo. Không cần khẳng định câu tiếng Việt hay tiếng Anh phải giống một chuỗi cố định.

Một cách dễ kiểm thử là tách việc xác định lỗi nghiệp vụ thành một kết quả nhỏ có chứa code và field. Ví dụ:

~~~java
public record ValidationIssue(
        String code,
        String field) {
}
~~~

Validator có thể trả về các issue để một adapter đưa chúng vào MessageContext:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShippingRules {

    public List<ValidationIssue> validate(String postalCode) {
        List<ValidationIssue> issues = new ArrayList<>();

        if (postalCode == null || !postalCode.matches("[0-9]{5,6}")) {
            issues.add(new ValidationIssue(
                    "SHIPPING_POSTAL_CODE_INVALID",
                    "postalCode"));
        }

        return issues;
    }
}
~~~

Bài kiểm thử đơn vị chỉ kiểm tra hợp đồng của validator:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ShippingRulesTest {

    private final ShippingRules rules = new ShippingRules();

    @Test
    void invalidPostalCodeProducesStableIssueCode() {
        var issues = rules.validate("12A");

        assertEquals(1, issues.size());
        assertEquals(
                "SHIPPING_POSTAL_CODE_INVALID",
                issues.get(0).code());
        assertEquals("postalCode", issues.get(0).field());
    }
}
~~~

Nếu nhóm không muốn tạo ValidationIssue riêng, có thể dùng test double hoặc mock MessageContext để ghi nhận MessageResolver được thêm vào. Cách cụ thể phụ thuộc phiên bản Spring Binding và API kiểm thử của dự án. Dù chọn cách nào, mục tiêu vẫn là xác nhận validator chọn đúng code, source và arguments; không phụ thuộc câu dịch cuối cùng.

## Kiểm thử MessageSource mà không khóa vào câu dịch

Một bài kiểm thử resource bundle có thể xác nhận mã tồn tại ở các locale hỗ trợ và được phân giải thành nội dung hiển thị. Kiểm thử không cần biết câu dịch cụ thể là gì.

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.util.List;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.context.MessageSource;
import org.springframework.context.support.ResourceBundleMessageSource;

class MessageBundleTest {

    private MessageSource messageSource() {
        ResourceBundleMessageSource source =
                new ResourceBundleMessageSource();
        source.setBasename("messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);
        return source;
    }

    @Test
    void postalCodeMessageExistsForSupportedLocales() {
        MessageSource source = messageSource();
        String code = "SHIPPING_POSTAL_CODE_INVALID";

        List<Locale> locales = List.of(
                Locale.ENGLISH,
                Locale.forLanguageTag("vi"));

        for (Locale locale : locales) {
            String text = source.getMessage(code, null, locale);

            assertFalse(text.isBlank());
            assertNotEquals(code, text);
        }
    }
}
~~~

Bài kiểm thử này xác nhận mỗi locale phân giải được mã thành một nội dung không rỗng và không trả lại chính mã. Khi người biên tập sửa “Mã bưu chính không hợp lệ” thành “Vui lòng kiểm tra mã bưu chính”, bài kiểm thử vẫn qua vì hợp đồng message code không thay đổi.

Với thông báo có tham số, kiểm thử nên xác nhận mã được phân giải và placeholder đã được thay bằng argument. Ví dụ bundle có thể chứa:

~~~properties
SHIPPING_MINIMUM_DAYS=Delivery takes at least {0} business days.
~~~

~~~properties
# messages_vi.properties
SHIPPING_MINIMUM_DAYS=Thời gian giao hàng tối thiểu là {0} ngày làm việc.
~~~

Kiểm thử có thể truyền số ngày và xác nhận kết quả không còn placeholder chưa phân giải. Nếu định dạng số hoặc ngày thay đổi theo locale, hãy kiểm tra theo quy tắc định dạng thay vì so sánh nguyên văn toàn bộ câu.

## Kiểm thử view và flow ở mức tích hợp

Kiểm thử đơn vị validator chưa đủ để xác nhận thông báo đến đúng view. Một bài kiểm thử tích hợp nên đi qua đường đi thực tế:

1. Khởi chạy flow và mở view-state có form.
2. Gửi dữ liệu không hợp lệ cùng event tiếp tục.
3. Xác nhận flow vẫn ở view-state cần sửa.
4. Xác nhận message được gắn với source của trường tương ứng.
5. Xác nhận view hiển thị một phần tử lỗi cho trường đó.
6. Chạy lại cùng kịch bản với locale khác.
7. Xác nhận mã lỗi, source và hành vi flow không đổi giữa các locale.

Trong kiểm thử giao diện, có thể xác nhận phần tử lỗi tồn tại, có nội dung và được gắn với đúng field. Không nên so sánh toàn bộ text hiển thị nếu mục tiêu của test là hành vi flow. Kiểm thử nội dung biên tập có thể tồn tại riêng, nhưng cần được quản lý như kiểm thử nội dung theo locale thay vì trộn vào mọi bài kiểm thử nghiệp vụ.

Ví dụ một ma trận kiểm thử:

| Kịch bản | Locale | Điều cần xác nhận |
|---|---|---|
| Postal code sai định dạng | vi | Flow giữ ở shipping; lỗi gắn với postalCode |
| Postal code sai định dạng | en | Cùng code và source; flow giữ ở shipping |
| Thiếu tên người nhận | vi | Code BOOKING_RECIPIENT_REQUIRED xuất hiện |
| Địa chỉ ngoài vùng phục vụ | en | Code SHIPPING_ADDRESS_UNSUPPORTED xuất hiện và transition không đi tiếp |
| Mã chưa có bản dịch riêng | locale fallback | Fallback đúng cấu hình; không lộ mã thô ngoài dự kiến |

## Những điều không nên kiểm thử bằng chuỗi bản dịch

Một số assertion dễ tạo ra bài test giòn:

~~~java
assertEquals(
    "Mã bưu chính không hợp lệ",
    response.getContentAsString());
~~~

Assertion này có thể thất bại khi nhóm sửa dấu câu, thay cách xưng hô hoặc điều chỉnh bản dịch. Nó cũng có thể thất bại khi thêm HTML bao quanh thông báo dù hành vi không đổi.

Thay vào đó, hãy kiểm tra:

- Validator phát đúng message code.
- Message được gắn với đúng source hoặc field.
- Severity phù hợp với lỗi.
- Arguments được truyền đúng và được phân giải.
- Flow ở đúng state sau khi validation thất bại.
- MessageSource phân giải được code theo các locale được hỗ trợ.
- View có vùng thông báo tương ứng và nội dung không rỗng.
- Fallback cho locale thiếu bản dịch hoạt động theo cấu hình.

Nếu yêu cầu sản phẩm bắt buộc một cụm từ chính xác, hãy đặt assertion đó trong bộ kiểm thử nội dung riêng cho locale tương ứng. Khi đó người sửa bản dịch biết họ đang thay đổi nội dung được kiểm soát, còn các bài test flow vẫn tập trung vào hành vi nghiệp vụ.

## Quản lý thay đổi message code

Message code cũng là một phần của hợp đồng. Đổi code có thể ảnh hưởng đến validator, bundle, view, tài liệu vận hành và test. Khi cần đổi mã:

1. Tìm tất cả nơi phát mã và nơi định nghĩa bản dịch trong phạm vi dự án.
2. Xác định liệu đây là đổi tên thuần túy hay thay đổi ý nghĩa lỗi.
3. Nếu đổi tên nhưng giữ ý nghĩa, cập nhật các bundle và test cùng một thay đổi.
4. Nếu cần tương thích với snapshot hoặc client cũ, có thể giữ alias trong một khoảng chuyển tiếp.
5. Xóa mã cũ sau khi xác nhận không còn nơi sử dụng.
6. Chạy kiểm thử cho mọi locale được hỗ trợ.

Không tái sử dụng một mã cũ cho ý nghĩa mới. Một test đang kiểm tra code có thể vẫn qua dù thông điệp đã mang ý nghĩa khác nếu nhóm đổi nội dung mà không đổi mã. Vì vậy, code phải có ý nghĩa ổn định và tên mã cần được rà soát trong review.

## Chẩn đoán lỗi thông báo

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| View hiển thị mã thay vì câu dịch | Không tìm thấy key trong bundle hoặc basename sai | Kiểm tra tên bundle, key và locale |
| Tiếng Việt hiển thị ký tự lỗi | Encoding resource bundle không đúng | Kiểm tra UTF-8 và cấu hình MessageSource |
| Một locale có thông báo, locale khác không có | Bundle locale thiếu key hoặc fallback chưa đúng | So sánh danh sách key giữa các bundle |
| Thông báo xuất hiện ở sai trường | Source trong MessageBuilder không khớp field | Kiểm tra source và binding path |
| Test hỏng sau khi sửa câu dịch | Test nghiệp vụ đang so sánh nguyên văn nội dung | Chuyển assertion sang code, source và hành vi |
| Flow vẫn chuyển state dù có lỗi | Điều kiện transition không kiểm tra kết quả validation | Kiểm tra cơ chế chặn transition khi có message severity error |
| Argument hiển thị nguyên dạng placeholder | Số lượng hoặc thứ tự arguments không khớp mẫu | Kiểm tra code, arguments và MessageFormat |

Khi xử lý lỗi, lần theo đường đi từ validator tới MessageContext, MessageSource, locale hiện tại rồi đến view. Nếu code đúng nhưng câu dịch sai, vấn đề thuộc bundle hoặc locale. Nếu code sai, vấn đề nằm ở logic validation hoặc adapter đưa lỗi vào MessageContext. Nếu view không hiển thị lỗi, kiểm tra source và binding của form.

## Checklist cho nhóm phát triển

Trước khi hoàn thiện một flow có hỗ trợ nhiều ngôn ngữ, hãy rà soát:

- [ ] Mỗi lỗi nghiệp vụ có message code ổn định và có ý nghĩa rõ.
- [ ] Code không chứa câu dịch, tên màn hình hoặc chi tiết trình bày.
- [ ] Validator gắn đúng source, severity và arguments.
- [ ] Các bundle hỗ trợ có key tương ứng.
- [ ] MessageSource dùng đúng basename và encoding.
- [ ] Locale phân giải message nhất quán với locale render view.
- [ ] Unit test kiểm tra code và source, không phụ thuộc câu dịch.
- [ ] Bundle test xác nhận key phân giải được ở các locale hỗ trợ.
- [ ] Integration test xác nhận flow ở đúng state và view hiển thị đúng field error.
- [ ] Fallback và trường hợp thiếu key có hành vi được xác định.
- [ ] Thay đổi code được cập nhật đồng bộ ở validator, bundle và test.

## Ghi nhớ

- Message code là định danh ổn định; câu dịch là nội dung có thể thay đổi theo locale.
- Kiểm thử validator bằng code, source, severity và arguments để giữ test độc lập với biên tập bản dịch.
- Dùng MessageSource để xác nhận các locale hỗ trợ có thể phân giải mã thông báo.
- Kiểm thử tích hợp cần xác nhận flow giữ đúng state và view gắn lỗi với đúng field.
- Chỉ kiểm tra nguyên văn bản dịch trong bộ kiểm thử nội dung riêng khi sản phẩm thực sự yêu cầu câu chữ chính xác.

