# Phân biệt giao ước được tài liệu hóa với chi tiết triển khai có thể thay đổi

## 1. Mục tiêu: đọc mã nguồn mà không biến giả định thành cam kết

Khi đọc Spring Boot Auto Configuration, bạn thường gặp hai nhóm thông tin:

- **Giao ước được tài liệu hóa (documented contract):** hành vi, API, thuộc tính cấu hình, điều kiện và điểm mở rộng được tài liệu/Javadoc chính thức mô tả để người dùng có thể dựa vào.
- **Chi tiết triển khai (implementation detail):** cách một phiên bản cụ thể hiện thực giao ước đó, ví dụ lớp trợ giúp nội bộ, thuật toán, thứ tự gọi method private, tên biến, cấu trúc collection, nội dung log hoặc cách một helper đang được viết.

Một chi tiết triển khai có thể giải thích chính xác điều gì đang xảy ra trong phiên bản bạn đang đọc. Tuy nhiên, nếu Spring Boot chưa cam kết chi tiết đó trong tài liệu/API được hỗ trợ, ứng dụng không nên phụ thuộc vào nó như một hợp đồng lâu dài.

Ví dụ, tài liệu Spring Boot 3.3 mô tả `@ConditionalOnProperty` kiểm tra property và cung cấp `havingValue`/`matchIfMissing`. Đó là giao ước có thể sử dụng. Việc phiên bản 3.3.13 dùng một lớp condition nội bộ, helper so sánh chuỗi hoặc thứ tự gọi các hàm riêng bên trong chỉ giải thích **cách hiện thực**, không tự động trở thành API mà ứng dụng nên gọi trực tiếp.

Bài học này giúp bạn:

1. Nhận biết nguồn nào xác định giao ước.
2. Đọc source để giải thích hành vi nhưng không phụ thuộc quá mức vào chi tiết nội bộ.
3. Thiết kế test dựa trên hành vi công khai, không khóa test vào log hoặc tên class nội bộ.
4. Đánh giá thay đổi khi nâng Spring Boot.
5. Ghi rõ điều gì được tài liệu bảo đảm, điều gì chỉ được quan sát ở một phiên bản và điều gì còn là giả thuyết.

**Phạm vi ví dụ:** Spring Boot 3.3.13, Spring Framework 6.1 và Java 17+. Khi dùng phiên bản khác, hãy mở tài liệu/Javadoc đúng phiên bản đang chạy trước khi kết luận.

## 2. Giao ước được tài liệu hóa là gì?

Một giao ước được tài liệu hóa là mô tả có nguồn chính thức, phạm vi và điều kiện áp dụng rõ ràng. Trong Spring Boot Auto Configuration, thường gặp các dạng sau.

### 2.1. Public annotation và thuộc tính có Javadoc

Ví dụ:

```java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

Khi đọc Javadoc, hãy kiểm tra:

- Annotation áp dụng cho loại phần tử nào (`@Target`).
- Giá trị mặc định của từng thuộc tính (`Default`).
- Ý nghĩa của `havingValue` và `matchIfMissing`.
- Phiên bản API xuất hiện (`Since`).
- Trạng thái deprecated và API thay thế nếu có.
- Liên kết tới annotation, condition hoặc phần tài liệu liên quan.

Thuộc tính có mô tả rõ trong Javadoc giúp người dùng biết điều gì được hỗ trợ. Không cần sao chép cách Spring Boot cài đặt so khớp bên trong vào mã ứng dụng.

### 2.2. Reference Guide

Reference Guide giải thích cách dùng API trong bối cảnh lớn hơn: cách auto-configuration được phát hiện, cách condition hoạt động, cách khai báo starter, cách kiểm thử, cách cấu hình property và các giới hạn đã biết.

Ví dụ, tài liệu phát triển auto-configuration của Spring Boot 3.3 mô tả:

- Cách liệt kê ứng viên trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Cách sử dụng `@AutoConfiguration`, `@ConditionalOnClass` và `@ConditionalOnMissingBean`.
- Cách kiểm thử với `ApplicationContextRunner`.
- Cách thêm cấu hình người dùng và property vào context thử nghiệm.
- Cách sử dụng `ConditionEvaluationReportLoggingListener` để ghi condition report ở INFO hoặc DEBUG.

Đây là hướng dẫn sử dụng được công bố. Khi tài liệu mô tả một hành vi cụ thể, hãy giữ nguyên điều kiện áp dụng của nó; đừng mở rộng thành cam kết cho những tình huống tài liệu không nói tới.

### 2.3. API công khai và điểm mở rộng có chủ đích

Một API công khai thường có tên/package, chữ ký và Javadoc có thể tra cứu. Nhưng **public trong Java không tự động đồng nghĩa “được khuyến nghị làm điểm mở rộng cho mọi ứng dụng”**.

Cần đọc thêm:

- Mục đích của class/interface và phần `See Also` trong Javadoc.
- Class có được tài liệu hướng dẫn ứng dụng sử dụng hay không.
- Có ghi chú nào chỉ rõ internal, experimental, deprecated hoặc for removal không.
- API có constructor/extension hook được công bố để người dùng triển khai hay chỉ là đối tượng framework tự tạo.
- Phiên bản tài liệu mà API thuộc về.

Ví dụ, `ApplicationContextRunner` được Spring Boot giới thiệu rõ trong hướng dẫn test auto-configuration. Đây là công cụ mà người viết starter có thể dựa vào để kiểm thử. Một helper nội bộ tình cờ có modifier `public` nhưng không được hướng dẫn như extension point không nên được chọn làm nền tảng cho thư viện riêng chỉ vì code có thể import.

### 2.4. Configuration properties và metadata

Với property, cần phân biệt:

- **Giao ước cấu hình:** tên key, kiểu dữ liệu, mặc định, ý nghĩa và điều kiện sử dụng được mô tả trong reference guide/Javadoc.
- **Configuration metadata:** metadata hỗ trợ IDE gợi ý tên property, kiểu, giá trị mặc định, description và deprecation khi có.
- **Chi tiết binder/validator:** cách một phiên bản bind, convert, validate hoặc tạo đối tượng nội bộ.

Metadata hữu ích khi tra cứu, nhưng không nên coi một file metadata đơn lẻ là toàn bộ tài liệu hành vi. Hãy kiểm tra mô tả property và phần reference guide tương ứng, đặc biệt khi property có điều kiện hoặc liên quan đến một nhóm cấu hình.

Ví dụ, nếu tài liệu mô tả `demo.feature.enabled` là boolean và mặc định false, đó là điều người dùng có thể cấu hình theo giao ước. Cách binder chuyển chuỗi thành boolean, helper nào được gọi và object trung gian nào được tạo là chuyện triển khai, trừ khi API công khai mô tả cụ thể.

## 3. Chi tiết triển khai thường gặp khi đọc source code

Những chi tiết sau có thể hữu ích để hiểu phiên bản hiện tại, nhưng không nên mặc nhiên xem chúng là cam kết tương thích.

| Chi tiết quan sát trong source | Vì sao có thể thay đổi | Cách dùng đúng |
| --- | --- | --- |
| Tên lớp condition/helper nội bộ | Có thể đổi tên, tách, gộp hoặc thay thế | Đọc để hiểu lý do; dùng annotation/API công khai trong ứng dụng |
| Method private/package-private và thứ tự gọi | Refactor có thể đổi cấu trúc mà không đổi hành vi công khai | Dùng làm dấu vết debug cho đúng phiên bản |
| Cấu trúc map/list nội bộ và khóa lưu trữ | Framework có thể đổi representation | Không truy cập reflection để sửa dữ liệu nội bộ |
| Tên bean tự sinh khi không được cam kết | Bean naming strategy hoặc cấu trúc cấu hình có thể đổi | Chỉ phụ thuộc tên khi tên là một phần hợp đồng được đặt rõ |
| Thứ tự log, nội dung message, dấu câu và indentation | Logging formatter/diagnostic có thể thay đổi | Đọc để chẩn đoán, không assert toàn bộ log như API |
| Tên source trong condition report được ghép từ class/method | Cách report biểu diễn source có thể đổi | Ưu tiên assert bean behavior và condition result cần thiết |
| Thuật toán sort nội bộ | Có thể được tối ưu hoặc thay đổi khi giữ nguyên contract | Chỉ dựa vào thứ tự nếu API/tài liệu công bố semantics |
| Field, cache, flag hoặc sentinel riêng | Là lựa chọn hiện thực của phiên bản hiện tại | Không truy cập bằng reflection hoặc package-private workaround |
| Số lần helper được gọi | Có thể đổi do cache, lazy init hoặc refactor | Không dùng số lần gọi nội bộ làm hợp đồng nếu không có API callback |
| Thứ tự khởi tạo tình cờ trong một test | Có thể khác theo context, dependency hoặc phiên bản | Khai báo dependency/ordering đúng API, test hành vi thực tế |

**Điểm quan trọng:** chi tiết nội bộ không nhất thiết sai hoặc vô ích. Nó chỉ có phạm vi cam kết hẹp hơn. Có thể dùng nó để trả lời “tại sao Boot 3.3.13 làm như vậy?”, nhưng không nên viết thư viện khác dựa vào nó nếu không có cam kết tương thích.

## 4. Phân biệt bằng một ví dụ Auto Configuration

Giả sử starter có tính năng gửi thông báo. Giao ước mong muốn:

- Chỉ bật khi `demo.notification.enabled=true`.
- Nếu người dùng chưa tự cung cấp `NotificationSender`, starter đăng ký implementation mặc định.
- Nếu người dùng đã cung cấp bean phù hợp, starter nhường quyền.
- Nếu tính năng bị tắt, không có bean do auto-configuration này tạo ra.

### 4.1. Phần giao ước công khai

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.notification",
    name = "enabled",
    havingValue = "true"
)
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationSender.class)
    NotificationSender notificationSender() {
        return new DefaultNotificationSender();
    }
}
```

Đây là ví dụ mã cho một starter; `NotificationSender` và `DefaultNotificationSender` là kiểu của thư viện. Những hành vi người dùng cần biết:

1. Property phải là true để lớp cấu hình khớp.
2. Nếu đã có bean `NotificationSender` phù hợp được biết đến tại thời điểm condition được xét, bean mặc định sẽ back off.
3. Nếu property false hoặc missing với mặc định `matchIfMissing=false`, auto-configuration không tạo bean.
4. Ứng dụng có thể thay thế hành vi bằng cách đăng ký bean `NotificationSender` của riêng mình.

Các annotation và thuộc tính được Javadoc/reference guide mô tả. Đây là nền tảng để viết test và tài liệu cho starter.

### 4.2. Những điều không được tự suy diễn

Từ đoạn code trên, không được kết luận rằng:

- Spring luôn gọi một method private cụ thể trước method khác.
- Tên bean mặc định bắt buộc luôn là `notificationSender` trong mọi cách đăng ký cấu hình.
- Một class condition nội bộ cụ thể sẽ luôn được dùng trong các bản tương lai.
- Log phải chứa nguyên văn một câu message, đúng thứ tự dòng hoặc đúng indentation.
- Mọi bean `NotificationSender` trong toàn bộ hệ thống đều do auto-configuration này đăng ký.
- Bean instance chắc chắn được khởi tạo tại đúng thời điểm lớp cấu hình được xử lý.

Nếu một hành vi không được giao ước mô tả, hãy xem đó là điều cần kiểm chứng ở phiên bản cụ thể, không phải cam kết của starter.

## 5. Thứ bậc nguồn thông tin khi đọc mã nguồn

Khi có mâu thuẫn giữa những gì bạn quan sát trong source và những gì người dùng được hướng dẫn, hãy ghi rõ phiên bản và phạm vi. Một quy trình đánh giá hữu ích:

1. **Reference Guide đúng phiên bản:** hành vi người dùng được hướng dẫn, điều kiện và giới hạn.
2. **Javadoc/API đúng phiên bản:** chữ ký, giá trị mặc định, semantics của annotation/method và trạng thái deprecated.
3. **Configuration changelog, release notes và migration guide:** thay đổi giữa các phiên bản, property thêm/bỏ/đổi, API deprecated và thay thế.
4. **Test công khai của framework và ví dụ tài liệu:** bằng chứng bổ sung về cách nhà phát triển dự định sử dụng API; vẫn cần đối chiếu tài liệu và phiên bản.
5. **Source code của đúng tag/commit:** giải thích cách phiên bản cụ thể hiện thực giao ước, phát hiện bug hoặc hiểu trường hợp tài liệu chưa giải thích.
6. **Log/stack trace/quan sát runtime:** bằng chứng về một lần chạy cụ thể, không tự trở thành contract chung.

Thứ tự này là quy trình đánh giá độ tin cậy, không phải tuyên bố source code kém quan trọng. Khi tìm bug, source và stack trace rất quan trọng. Khi thiết kế public API cho ứng dụng, giao ước được tài liệu hóa mới là điểm tựa.

### 5.1. Tra cứu đúng phiên bản

Đừng mở Javadoc phiên bản mới nhất rồi dùng nó để giải thích ứng dụng đang chạy Boot 3.3. Hãy xác định version thực tế từ dependency management hoặc runtime, sau đó mở đúng tài liệu.

Ví dụ:

- Spring Boot 3.3.13: `https://docs.spring.io/spring-boot/3.3/api/java/`
- Spring Boot 3.4.x: dùng Javadoc/reference của 3.4.x.
- Spring Boot 3.5.x: dùng Javadoc/reference của 3.5.x.

Nếu đang kiểm tra bản patch cụ thể, ưu tiên tài liệu cùng dòng version và kiểm tra release notes của patch. Các minor line khác nhau có thể thay đổi API hoặc behavior được công bố.

### 5.2. Dùng source code để xác minh có kiểm soát

Khi cần đọc implementation:

1. Xác định đúng artifact và version (ví dụ `spring-boot-autoconfigure:3.3.13`).
2. Mở source JAR hoặc tag tương ứng, không dựa vào nhánh `main` khi đang phân tích Boot 3.3.
3. Bắt đầu từ API/annotation công khai đang quan sát, lần theo condition/helper được gọi.
4. Ghi lại chi tiết nào giải thích kết quả, nhưng đánh dấu đó là implementation detail nếu tài liệu không cam kết.
5. Đối chiếu test và release notes để xem behavior có thay đổi ở bản sau không.
6. Khi báo cáo, phân biệt “theo tài liệu” và “source 3.3.13 hiện đang làm”.

Không cần sao chép hoặc gọi trực tiếp class nội bộ trong code ứng dụng để chứng minh bạn đã hiểu nó. Source là công cụ điều tra, không nhất thiết là dependency cho sản phẩm.

## 6. Spring Boot có thể thay đổi gì giữa các phiên bản?

Không nên hiểu “documented contract” là bất biến vĩnh viễn. Giao ước được hỗ trợ vẫn có thể được điều chỉnh theo chính sách tương thích, phiên bản major/minor và deprecation.

Theo chính sách hỗ trợ phiên bản Spring Boot:

- Patch releases được kỳ vọng giữ tương thích ngược với các patch trước **nhiều nhất có thể**.
- Minor và major releases **có thể** có thay đổi API không tương thích ngược.
- Khi khả thi, API cũ được giữ lại và đánh dấu deprecated để báo trước việc không còn được khuyến nghị.
- Spring Boot có chính sách deprecation riêng; hãy xem `@Deprecated`, Javadoc `@deprecated`, phiên bản deprecated và phiên bản dự kiến removal.

Đây là chính sách và định hướng tương thích, không phải lời hứa rằng mọi dependency, mọi property hoặc mọi hành vi phụ thuộc bên thứ ba đều bất biến.

### 6.1. Deprecated không đồng nghĩa đã bị xóa

Ví dụ một API có thể được đánh dấu:

```java
/**
 * @deprecated since 3.3.0 for removal in 3.5.0
 */
@Deprecated(since = "3.3.0", forRemoval = true)
public void oldMethod() {
}
```

Đây chỉ là ví dụ minh họa cú pháp. Với API thật, hãy đọc chính xác `since`, `forRemoval` và Javadoc replacement. Không tự suy ra version removal chỉ từ thời điểm bạn nhìn thấy cảnh báo compiler.

Khi gặp deprecated:

1. Tìm alternative được ghi trong Javadoc.
2. Kiểm tra phiên bản mà alternative xuất hiện.
3. Xem migration guide/release notes của version mục tiêu.
4. Thay thế và chạy test trên cả version hiện tại lẫn version nâng cấp nếu dự án hỗ trợ nhiều version.
5. Không trì hoãn vô hạn nếu API đã ghi rõ for removal.

### 6.2. Release notes và configuration changelog có giá trị gì?

Release notes ghi các thay đổi nổi bật, deprecation và hướng dẫn nâng cấp. Configuration changelog liệt kê property được thêm, bỏ hoặc đổi giữa các phiên bản.

Ví dụ Spring Boot 3.3 có thay đổi một số property, dependency được nâng cấp và một số API được deprecated. Những thay đổi này cho thấy **một property hoặc dependency đang dùng hôm nay không mặc nhiên có cùng trạng thái ở minor line sau**.

Khi nâng cấp, đừng chỉ sửa lỗi compile. Hãy kiểm tra cả property binding, default value, condition outcome và behavior trong context.

## 7. Viết test theo giao ước, không theo chi tiết nội bộ

Test tốt bảo vệ điều mà người dùng starter quan tâm: bean có xuất hiện đúng lúc không, giá trị có đúng không, bean người dùng có được ưu tiên không.

### 7.1. Ví dụ test hành vi công khai

Test bằng `ApplicationContextRunner`:

```java
class NotificationAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    NotificationAutoConfiguration.class
                )
            );

    @Test
    void createsDefaultSenderWhenEnabledAndMissing() {
        this.contextRunner
            .withPropertyValues("demo.notification.enabled=true")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(NotificationSender.class);

                assertThat(context.getBean(NotificationSender.class))
                    .isInstanceOf(DefaultNotificationSender.class);
            });
    }

    @Test
    void backsOffWhenUserProvidesSender() {
        this.contextRunner
            .withPropertyValues("demo.notification.enabled=true")
            .withUserConfiguration(UserSenderConfiguration.class)
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(NotificationSender.class);

                assertThat(context.getBean(NotificationSender.class))
                    .isInstanceOf(CustomNotificationSender.class);
            });
    }

    @Test
    void doesNotCreateSenderWhenDisabled() {
        this.contextRunner
            .withPropertyValues("demo.notification.enabled=false")
            .run(context ->
                assertThat(context)
                    .doesNotHaveBean(NotificationSender.class)
            );
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSenderConfiguration {

        @Bean
        NotificationSender customNotificationSender() {
            return new CustomNotificationSender();
        }
    }
}
```

Đây là **snippet minh họa**; các interface/class sender và import JUnit/AssertJ cần có trong module thực tế. `NotificationAutoConfiguration` là auto-configuration được chọn tường minh trong runner. Spring Boot hướng dẫn dùng `ApplicationContextRunner` để tạo context riêng cho từng tổ hợp user configuration, Environment và condition.

Các assertion ở đây bám vào contract:

- Bật property và không có bean người dùng → có một sender mặc định.
- Bật property và có bean người dùng → sender của người dùng được giữ lại.
- Tắt property → không có sender từ auto-configuration.

### 7.2. Test dễ vỡ vì khóa vào implementation

Các kiểm tra sau thường không nên là contract test của ứng dụng:

```text
- Assert nguyên văn toàn bộ log condition.
- Assert class helper nội bộ có tên chính xác.
- Assert private method được gọi đúng N lần.
- Assert thứ tự nội bộ của các source trong report khi thứ tự đó không được công bố.
- Assert tên bean tự sinh khi tên đó không được đặt thành hợp đồng.
- Dùng reflection để đọc field nội bộ của Spring Boot.
```

Ví dụ, nếu log message thay đổi nhưng bean vẫn được đăng ký đúng, test dựa trên message sẽ thất bại giả. Ngược lại, nếu bean không còn xuất hiện mà message vẫn giống trước, test chỉ kiểm log có thể bỏ sót bug.

### 7.3. Khi nào được test condition report?

`ConditionEvaluationReport` và `ConditionEvaluationReportLoggingListener` có Javadoc công khai trong Spring Boot. Bạn có thể dùng chúng cho chẩn đoán hoặc test chuyên sâu khi mục tiêu thực sự là condition reporting.

Tuy nhiên, đừng biến mọi chi tiết biểu diễn report thành giao ước của ứng dụng. Ưu tiên:

- Assert bean presence/absence.
- Assert behavior/configuration value.
- Khi cần kiểm tra condition, đọc outcome có cấu trúc thay vì so sánh toàn bộ chuỗi log.
- Chỉ assert source key/message nếu chính dự án bạn đã chủ động coi chúng là contract và chấp nhận bảo trì khi nâng Boot.

## 8. Quy trình phân loại một phát hiện khi đọc mã

Mỗi khi thấy một đoạn code đáng chú ý, hãy tự trả lời các câu hỏi sau.

### 8.1. Phát hiện này thuộc loại nào?

| Loại phát hiện | Dấu hiệu | Cách ghi kết luận |
| --- | --- | --- |
| **Documented contract** | Có mô tả rõ trong reference guide/Javadoc đúng phiên bản | “Spring Boot 3.3 tài liệu hóa rằng…” |
| **Public API chưa đủ ngữ cảnh** | Class/method public nhưng chưa thấy hướng dẫn dùng hoặc mục đích mở rộng | “API có thể truy cập; cần xác nhận đây là extension point được hỗ trợ…” |
| **Implementation detail** | Private/package-private helper, field, thuật toán, log formatting | “Trong source 3.3.13 hiện tại, implementation…” |
| **Observed behavior** | Quan sát qua một test hoặc một lần chạy | “Trong kịch bản này, kết quả quan sát được là…” |
| **Hypothesis** | Suy luận chưa có tài liệu/test chứng minh | “Giả thuyết cần kiểm chứng…” |
| **Project contract** | Dự án tự định nghĩa qua interface, docs, tests, config | “Starter của dự án quy định…” |

Phân loại giúp người đọc biết mức độ tin cậy và phạm vi áp dụng của kết luận.

### 8.2. Ví dụ cách viết báo cáo chính xác

**Không rõ phạm vi:**

> Spring Boot luôn chạy condition X trước condition Y vì source hiện tại gọi X trước Y.

**Có phạm vi và bằng chứng:**

> Tài liệu Spring Boot 3.3 quy định auto-configuration được sắp xếp theo quan hệ before/after. Trong source 3.3.13, lớp helper hiện tại thực hiện việc sắp xếp theo một thuật toán cụ thể. Thuật toán là chi tiết triển khai; test của starter chỉ phụ thuộc vào kết quả bean được tài liệu hỗ trợ.

Cách viết thứ hai tách bạch contract và bằng chứng source, giúp người review không nhầm quan sát phiên bản thành bảo đảm cho mọi phiên bản.

## 9. Checklist khi review hoặc nâng phiên bản

Khi review auto-configuration hoặc nâng Spring Boot:

1. **Xác định version thật:** kiểm dependency management, BOM và runtime artifact.
2. **Đọc tài liệu đúng version:** reference guide và Javadoc của API đang sử dụng.
3. **Kiểm release notes:** tìm deprecation, property change, dependency upgrade và thay đổi behavior.
4. **Kiểm migration guide:** xem yêu cầu nâng version major/minor.
5. **Phân loại dependency vào internals:** xác định source nào là API dùng trực tiếp và source nào chỉ đang giải thích implementation.
6. **Rà soát deprecation:** đọc alternative và removal version; không bỏ qua cảnh báo forRemoval.
7. **Chạy contract tests:** property true/false/missing, class present/absent, bean user/default, web/non-web và các tình huống thực tế của starter.
8. **Không khóa test vào log:** chỉ kiểm report/message khi đó là mục tiêu riêng của test.
9. **Kiểm dependency graph:** Boot có thể nâng version thư viện bên thứ ba; API của dependency đó cũng có thể thay đổi.
10. **Ghi rõ phạm vi kết luận:** version, source, test case và điều chưa được xác minh.

Một bảng review ngắn có thể dùng trong PR:

| Phát hiện | Nguồn bằng chứng | Phân loại | Test cần có |
| --- | --- | --- | --- |
| Property `demo.notification.enabled=true` bật sender | Boot 3.3 reference/Javadoc | Documented contract của starter | enabled/disabled/missing |
| Bean người dùng khiến default back off | `@ConditionalOnMissingBean` docs | Documented contract | user bean override |
| Tên helper condition nội bộ | Source tag 3.3.13 | Implementation detail | Không assert tên helper |
| Message log có câu cụ thể | Một lần chạy test | Observed behavior | Không assert toàn văn log |
| Property mới bị deprecated | Changelog/Javadoc | Versioned migration contract | Test cấu hình mới và cũ theo version hỗ trợ |

## 10. Bài tập tự kiểm tra

**Câu 1.** Javadoc của `@ConditionalOnProperty` mô tả `havingValue` và `matchIfMissing`. Đây là contract hay implementation detail?  
**Đáp án:** Contract được tài liệu hóa của API ở phiên bản tương ứng. Ứng dụng có thể dựa vào semantics đó trong phạm vi version được hỗ trợ.

**Câu 2.** Bạn thấy source Boot 3.3.13 dùng một class condition package-private để xử lý annotation. Có nên import class đó vào starter riêng?  
**Đáp án:** Không nên. Đó là chi tiết nội bộ; dùng annotation/API công khai và kiểm tra kết quả qua context test.

**Câu 3.** Test của bạn assert log condition phải có chính xác dấu câu, indentation và tên source. Khi nâng Boot patch, log thay đổi nhưng bean vẫn đúng. Test có đang kiểm đúng contract không?  
**Đáp án:** Không, trừ khi chính log format là contract của sản phẩm. Hãy assert bean và outcome có ý nghĩa; dùng log để chẩn đoán.

**Câu 4.** Một class có modifier `public`. Điều đó có đủ chứng minh nó là extension point ổn định không?  
**Đáp án:** Không. Cần kiểm Javadoc, reference guide, mục đích API và deprecation/compatibility policy.

**Câu 5.** Tài liệu 3.3 nói API A được hỗ trợ, nhưng source 3.3.13 hiện thực bằng helper B. Ở ứng dụng của bạn nên gọi A hay B?  
**Đáp án:** Gọi API A được tài liệu hóa. Helper B chỉ dùng để hiểu implementation của đúng version.

**Câu 6.** Một property bị deprecated trong minor release. Có thể đợi đến lúc compile lỗi mới đổi không?  
**Đáp án:** Không nên. Đọc `since`, `forRemoval`, replacement và release notes; lên kế hoạch chuyển đổi trước version removal.

**Câu 7.** Một test với `ApplicationContextRunner` chứng minh default bean được tạo khi property bật. Nó có bảo đảm Spring Boot luôn dùng cùng thuật toán condition nội bộ không?  
**Đáp án:** Không. Test chứng minh hành vi quan sát được trong tổ hợp cấu hình và version test; implementation có thể thay đổi mà contract vẫn được giữ.

**Câu 8.** Khi source hiện tại và tài liệu có vẻ mâu thuẫn, nên báo cáo thế nào?  
**Đáp án:** Ghi rõ version, API, đoạn tài liệu và quan sát source/test; xác định đó là bug, tài liệu chưa đầy đủ hay một giả thuyết cần kiểm chứng. Không âm thầm biến implementation thành contract.

## 11. Ghi nhớ và tài liệu tham khảo

- **Tài liệu và Javadoc đúng version** xác định cách người dùng được phép dựa vào API.
- **Source code** giải thích cách một phiên bản cụ thể thực hiện giao ước; private/helper/field/log formatting không tự trở thành contract.
- Modifier `public` không tự bảo đảm một class là extension point được hỗ trợ.
- Spring Boot cố gắng giữ tương thích ở patch releases; minor/major có thể có breaking API changes. Theo dõi deprecation và migration guide.
- Test nên bảo vệ **hành vi**: bean có/không có, giá trị cấu hình, back off và condition outcome có ý nghĩa; tránh khóa vào chi tiết report/log.
- Khi báo cáo, phân loại rõ: documented contract, public API cần xác minh, implementation detail, observed behavior, hypothesis và project contract.

Tài liệu chính thức:

1. Spring Boot — [Supported Versions and Release Compatibility](https://github.com/spring-projects/spring-boot/wiki/Supported-Versions).
2. Spring Boot 3.3 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
3. Spring Boot 3.3 — [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).
4. Spring Boot 3.3 — [Spring Boot API Javadoc 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/).
5. Spring Boot — [Deprecations Policy](https://github.com/spring-projects/spring-boot/wiki/Deprecations).
6. Spring Boot 3.3 — [Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes).
7. Spring Boot 3.3 — [Configuration Changelog](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Configuration-Changelog).
8. Spring Boot 3.3.13 — [`@ConditionalOnProperty` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
