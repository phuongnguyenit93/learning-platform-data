# @MockitoSpyBean và quan sát hành vi của bean thật

Trong một integration test dùng Spring, đôi khi ta muốn giữ một bean thật để kiểm tra hành vi của nó, đồng thời quan sát xem thành phần khác có gọi bean đó đúng cách hay không. Mockito spy đáp ứng nhu cầu này: lời gọi mặc định vẫn chạy phương thức thật, còn test có thể xác minh tương tác hoặc thay thế có chọn lọc một phương thức.

Spring Framework 6.2 bổ sung annotation `@MockitoSpyBean` để đăng ký spy ngay trên bean trong ApplicationContext. Nhờ đó, các bean khác được inject cùng spy đã được Spring quản lý. Test có thể quan sát luồng cộng tác trong context mà không phải tự tạo một đối tượng Mockito bên ngoài rồi hy vọng ứng dụng đang dùng đúng instance đó.

Điểm cần nhớ là spy vẫn thực thi logic thật theo mặc định. Vì vậy, khi dùng spy, test phải quan tâm đến dữ liệu đầu vào, side effect và trạng thái mà phương thức thật có thể thay đổi.

## Spy bean hoạt động như thế nào?

Một mock thường thay thế hành vi của dependency bằng hành vi do test định nghĩa. Một spy giữ hành vi thật của đối tượng và cho phép quan sát hoặc stubbing một số lời gọi cụ thể.

| Cơ chế | Hành vi mặc định | Mục tiêu thường gặp |
|---|---|---|
| Mockito mock / Spring `@MockitoBean` | Không chạy logic thật; trả về giá trị mặc định hoặc giá trị được stub | Cô lập unit đang kiểm tra khỏi dependency |
| Mockito spy / Spring `@MockitoSpyBean` | Gọi phương thức thật nếu chưa stub | Quan sát bean thật và xác minh cách các thành phần cộng tác |
| Mockito `@Spy` | Spy một object do test tạo hoặc cung cấp | Kiểm tra một object trong phạm vi test thuần Mockito |
| Spring Boot `@SpyBean` | Cơ chế spy bean trong context của Spring Boot ở các phiên bản Boot cũ | Tương tự, nhưng thuộc API của Spring Boot |

Với `@MockitoSpyBean`, Spring tìm bean phù hợp trong ApplicationContext và bọc bean đó bằng Mockito spy. Những thành phần được inject bean từ context sẽ nhận spy đã đăng ký. Điều này giúp test quan sát các lời gọi thực sự đi qua ranh giới bean trong ứng dụng.

~~~mermaid
flowchart TD
    A["ApplicationContext"] --> B["InvoiceService"]
    A --> C["TaxCalculator bean"]
    C --> D["Mockito spy bao quanh bean thật"]
    B -->|Gọi calculateTax| D
    D --> E["Chạy phương thức thật nếu chưa stub"]
    E --> F["Mockito ghi nhận tương tác"]
    F --> G["Test assert kết quả và verify lời gọi"]
~~~

Spy không tự động biến mọi object cùng kiểu trong JVM thành spy. Nó áp dụng cho bean được Spring chọn trong context tương ứng. Một object được tạo bằng `new TaxCalculator()` bên ngoài ApplicationContext vẫn là object riêng và không được annotation này thay thế.

## Khai báo @MockitoSpyBean

`@MockitoSpyBean` thuộc package:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
~~~

Annotation được dùng trên field của test class để chỉ định bean cần spy. Ví dụ:

~~~java
@SpringJUnitConfig(InvoiceTestConfig.class)
class InvoiceServiceTest {

    @Autowired
    private InvoiceService invoiceService;

    @MockitoSpyBean
    private TaxCalculator taxCalculator;

    @Test
    void calculatesInvoiceUsingRealTaxCalculator() {
        BigDecimal total = invoiceService.total(new BigDecimal("100.00"));

        assertThat(total).isEqualByComparingTo("110.00");
        verify(taxCalculator).calculateTax(new BigDecimal("100.00"));
    }
}
~~~

Trong ví dụ này, `InvoiceService` là bean thật được lấy từ ApplicationContext. `TaxCalculator` cũng bắt đầu từ bean thật, sau đó Spring bọc bean đó bằng spy. Khi `invoiceService.total(...)` gọi `calculateTax(...)`, phương thức thật được thực thi và Mockito ghi nhận lời gọi để test có thể xác minh.

`@MockitoSpyBean` cần một bean hiện có để bọc. Nếu context không có bean phù hợp, Spring không thể tạo một spy thay thế theo cách mock bean có thể làm; việc khởi tạo test context sẽ thất bại. Điều này phù hợp với ý nghĩa của spy: test muốn quan sát một triển khai thật đã được cấu hình.

## Ví dụ đầy đủ: quan sát một bean thật

Giả sử service hóa đơn gọi một bean tính thuế:

~~~java
import java.math.BigDecimal;

class TaxCalculator {

    BigDecimal calculateTax(BigDecimal netAmount) {
        return netAmount.multiply(new BigDecimal("0.10"));
    }
}

class InvoiceService {

    private final TaxCalculator taxCalculator;

    InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    BigDecimal total(BigDecimal netAmount) {
        BigDecimal tax = taxCalculator.calculateTax(netAmount);
        return netAmount.add(tax);
    }
}
~~~

Cấu hình Spring tạo hai bean thật:

~~~java
@Configuration
class InvoiceTestConfig {

    @Bean
    TaxCalculator taxCalculator() {
        return new TaxCalculator();
    }

    @Bean
    InvoiceService invoiceService(TaxCalculator taxCalculator) {
        return new InvoiceService(taxCalculator);
    }
}
~~~

Test có thể xác nhận kết quả nghiệp vụ và tương tác với bean tính thuế:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

@SpringJUnitConfig(InvoiceTestConfig.class)
class InvoiceServiceSpyTest {

    @Autowired
    private InvoiceService invoiceService;

    @MockitoSpyBean
    private TaxCalculator taxCalculator;

    @Test
    void callsRealTaxCalculator() {
        BigDecimal total = invoiceService.total(new BigDecimal("100.00"));

        assertThat(total).isEqualByComparingTo("110.00");
        verify(taxCalculator).calculateTax(new BigDecimal("100.00"));
    }
}
~~~

Test chứng minh hai điều:

1. Kết quả tổng tiền là 110.00 khi bean tính thuế thật áp dụng mức 10%.
2. `InvoiceService` đã gọi `TaxCalculator.calculateTax()` với số tiền trước thuế là 100.00.

Nếu chỉ assert kết quả, ta biết kết quả đúng nhưng chưa trực tiếp xác nhận collaborator được gọi với đối số mong muốn. Nếu chỉ verify lời gọi, ta biết có tương tác nhưng chưa chứng minh kết quả nghiệp vụ cuối cùng đúng. Kết hợp assertion và verify khi cả hai điều đều thuộc hợp đồng cần kiểm tra sẽ làm ý định test rõ ràng.

## Stubbing có chọn lọc nhưng vẫn giữ bean thật

Một spy có thể thay thế kết quả của một phương thức cụ thể trong test. Các phương thức khác tiếp tục chạy logic thật.

Ví dụ, muốn kiểm tra cách `InvoiceService` xử lý một mức thuế do một chính sách đặc biệt cung cấp:

~~~java
import static org.mockito.Mockito.doReturn;

@Test
void usesTaxValueProvidedByCollaborator() {
    doReturn(new BigDecimal("5.00"))
        .when(taxCalculator)
        .calculateTax(new BigDecimal("100.00"));

    BigDecimal total = invoiceService.total(new BigDecimal("100.00"));

    assertThat(total).isEqualByComparingTo("105.00");
    verify(taxCalculator).calculateTax(new BigDecimal("100.00"));
}
~~~

Trong test này, `InvoiceService` vẫn là bean thật. Spy chặn riêng lời gọi `calculateTax(100.00)` và trả về 5.00 theo cấu hình test. Điều này hữu ích khi muốn kiểm tra nhánh xử lý ở service với một kết quả collaborator xác định, trong khi vẫn giữ phần còn lại của Spring context và logic thật.

### Vì sao nên dùng doReturn khi stubbing spy?

Với mock thông thường, cách viết sau thường quen thuộc:

~~~java
when(mock.calculateTax(amount)).thenReturn(expectedTax);
~~~

Khi áp dụng trực tiếp lên spy, biểu thức `mock.calculateTax(amount)` trong lời gọi `when(...)` có thể thực thi phương thức thật ngay trong lúc thiết lập stub. Nếu phương thức thật truy cập database, gọi HTTP, thay đổi trạng thái hoặc ném exception, việc chuẩn bị test có thể gây side effect hoặc thất bại trước khi test bắt đầu.

Với spy, nên ưu tiên cú pháp `doReturn(...).when(spy).method(...)`:

~~~java
doReturn(expectedTax)
    .when(taxCalculator)
    .calculateTax(amount);
~~~

Các biến thể tương tự gồm `doThrow(...)`, `doNothing()`, `doAnswer(...)` và `doCallRealMethod()`. Chúng cho phép thiết lập hành vi mà không cần gọi phương thức thật trong bước stubbing.

Ví dụ muốn kiểm tra service xử lý lỗi do collaborator phát sinh:

~~~java
doThrow(new IllegalStateException("Tax service unavailable"))
    .when(taxCalculator)
    .calculateTax(new BigDecimal("100.00"));

assertThatThrownBy(() ->
    invoiceService.total(new BigDecimal("100.00"))
).isInstanceOf(IllegalStateException.class);
~~~

Trong ví dụ này, spy ném exception theo cấu hình test cho lời gọi cụ thể. Test có thể xác nhận cách service phản ứng khi collaborator phát sinh lỗi.

## Xác minh tương tác với Mockito

Sau khi hành vi chạy, Mockito cung cấp các API để xác nhận spy đã nhận lời gọi nào:

~~~java
verify(taxCalculator).calculateTax(amount);
verify(taxCalculator, times(1)).calculateTax(amount);
verify(taxCalculator, never()).calculateTax(otherAmount);
verifyNoMoreInteractions(taxCalculator);
~~~

Các lựa chọn thường dùng:

| API | Ý nghĩa |
|---|---|
| `verify(spy).method(...)` | Xác nhận phương thức được gọi ít nhất một lần |
| `times(n)` | Xác nhận số lần gọi chính xác |
| `never()` | Xác nhận phương thức không được gọi |
| `atLeastOnce()` | Xác nhận có ít nhất một lần gọi |
| `atMost(n)` | Xác nhận không vượt quá số lần chỉ định |
| `ArgumentCaptor` | Thu thập đối số thực tế để kiểm tra |

Ví dụ dùng `ArgumentCaptor`:

~~~java
ArgumentCaptor<BigDecimal> amountCaptor =
    ArgumentCaptor.forClass(BigDecimal.class);

invoiceService.total(new BigDecimal("100.00"));

verify(taxCalculator).calculateTax(amountCaptor.capture());

assertThat(amountCaptor.getValue())
    .isEqualByComparingTo("100.00");
~~~

Captor phù hợp khi đối số truyền sang collaborator là một phần quan trọng của hợp đồng. Tránh xác minh mọi lời gọi nội bộ hoặc thứ tự gọi không có ý nghĩa đối với hành vi cần kiểm thử. Nếu test phụ thuộc quá chặt vào chi tiết triển khai, một refactor không đổi hành vi có thể làm test thất bại.

## Chọn đúng bean khi có nhiều ứng viên

Nếu ApplicationContext có nhiều bean cùng kiểu, Spring cần xác định bean nào sẽ được spy. Field-level `@MockitoSpyBean` dùng kiểu của field để tìm ứng viên; tên field có thể được dùng như một qualifier fallback khi cần phân biệt.

Có thể chỉ định rõ bean bằng `@Qualifier`:

~~~java
@SpringJUnitConfig(PaymentTestConfig.class)
class PaymentServiceTest {

    @Autowired
    private PaymentService paymentService;

    @MockitoSpyBean
    @Qualifier("remotePaymentGateway")
    private PaymentGateway paymentGateway;
}
~~~

Nếu có hai bean `PaymentGateway` nhưng test muốn quan sát `remotePaymentGateway`, qualifier giúp việc chọn bean rõ ràng. Cần kiểm tra bean name, qualifier và profile đang hoạt động nếu Spring báo có nhiều ứng viên hoặc không tìm thấy bean.

Không nên thêm một bean trùng kiểu chỉ để làm cho annotation chọn được. Hãy xác định bean mà service thực sự sử dụng và đặt qualifier tương ứng.

## Spy bean và AOP proxy

Trong ứng dụng Spring, bean có thể được bọc bởi proxy do transaction, caching, security hoặc aspect khác. Khi spy một bean đã được proxy, test cần hiểu lời gọi đang đi qua proxy hay đang tác động trực tiếp tới target.

Một số lưu ý:

- Nếu cần xác minh hành vi ở ranh giới bean mà service khác gọi, hãy quan sát bean được inject trong ApplicationContext.
- Nếu phương thức được gọi qua Spring AOP proxy, các interceptor có thể tham gia trước hoặc sau lời gọi thật.
- Self-invocation, tức một phương thức trong cùng object gọi phương thức khác trên chính `this`, thường không đi qua proxy Spring AOP. Do đó, test không nên suy luận rằng mọi lời gọi nội bộ đều kích hoạt transaction hoặc aspect.
- Stubbing phương thức trên spy có thể làm thay đổi hành vi thật mà proxy hoặc bean phụ thuộc mong đợi; chỉ stub phần cần kiểm soát.
- Với bean có proxy phức tạp, cần xác định test đang verify reference nào và lời gọi có thực sự đi qua reference đó không.

Spy hữu ích để quan sát một bean, nhưng không thay thế test dành riêng cho transaction, security hoặc caching. Nếu mục tiêu là chứng minh interceptor hoạt động, hãy kiểm tra kết quả qua proxy ở một test có cấu hình phù hợp.

## Reset spy giữa các test

Spring quản lý spy bean trong context và mặc định reset Mockito spy sau mỗi test method theo chính sách reset của bean override. Điều này giúp các lời gọi và stubbing từ một test không vô tình ảnh hưởng test tiếp theo, ngay cả khi ApplicationContext được cache và dùng lại.

Vì spy được gắn với bean trong context, không nên tự tạo lại spy hoặc thay reference trong từng test method. Hãy để Spring quản lý vòng đời và dùng annotation trên test class.

Nếu test class dùng chung context với class khác, hãy lưu ý bean spy thuộc context được chia sẻ. Việc reset giúp dọn trạng thái Mockito như stubbing và invocation history; nó không tự hoàn tác side effect mà phương thức thật đã thực hiện. Ví dụ, nếu phương thức spy ghi database, gửi message hoặc thay đổi singleton state, reset Mockito không xóa dữ liệu đó. Side effect vẫn cần transaction rollback, fixture cleanup hoặc cơ chế cô lập riêng.

## Phân biệt @MockitoSpyBean, @MockitoBean và @Spy

Ba annotation/cơ chế thường bị nhầm:

~~~java
@MockitoBean
private PaymentGateway paymentGateway;
~~~

`@MockitoBean` tạo mock bean để thay thế bean trong context. Lời gọi không chạy logic thật trừ khi test stub hoặc cấu hình gọi phương thức thật.

~~~java
@MockitoSpyBean
private PaymentGateway paymentGateway;
~~~

`@MockitoSpyBean` bọc bean hiện có bằng spy. Lời gọi chạy logic thật theo mặc định và có thể được verify hoặc stub có chọn lọc.

~~~java
@Spy
private PaymentGateway paymentGateway = new PaymentGateway();
~~~

`@Spy` của Mockito tạo spy cho object thuộc phạm vi test. Bản thân annotation Mockito không yêu cầu Spring thay bean trong ApplicationContext. Nếu service Spring đang giữ một bean khác, spy field này có thể không quan sát được lời gọi mà service thực hiện.

Vì vậy, khi mục tiêu là theo dõi một bean mà các bean khác trong Spring context đang sử dụng, `@MockitoSpyBean` là lựa chọn phù hợp. Khi chỉ cần spy một object cục bộ trong unit test thuần Mockito, `@Spy` có thể đủ.

## Phân biệt với @SpyBean của Spring Boot

Các phiên bản Spring Boot trước đây cung cấp `@SpyBean` trong package của Boot Test. Spring Framework 6.2 bổ sung `@MockitoSpyBean` trong chính Spring TestContext Framework như một phần của cơ chế bean override.

Khi đọc một codebase, hãy kiểm tra phiên bản Spring Framework và Spring Boot để chọn API phù hợp. Với ứng dụng dùng Spring Framework 6.2 trở lên, có thể dùng `org.springframework.test.context.bean.override.mockito.MockitoSpyBean`. Dự án cũ hơn có thể tiếp tục dùng API `@SpyBean` mà phiên bản Boot đang cung cấp hoặc dùng Mockito spy theo cách thủ công.

Không nên import nhầm hai annotation chỉ vì tên gần giống nhau. IDE có thể tự động chọn import không đúng package nếu cả Spring Boot Test và Spring Test đều có trên classpath.

## Những giới hạn và tình huống cần thận trọng

Spy chạy phương thức thật, vì vậy test cần có môi trường đủ an toàn cho các side effect của phương thức đó. Trước khi spy, hãy cân nhắc:

- Phương thức có ghi database hoặc gọi transaction không?
- Phương thức có gọi HTTP, gửi message hoặc ghi file không?
- Bean có giữ trạng thái mutable dùng chung giữa test method không?
- Phương thức có phụ thuộc vào thời gian, thread-local hoặc request context không?
- Bean có bị proxy bởi AOP hoặc có nhiều implementation cùng kiểu không?
- Test có thực sự cần xác minh tương tác đó, hay chỉ cần kiểm tra kết quả công khai?

Mockito không thể thay thế mọi loại method. Khả năng spy/stub các phương thức final phụ thuộc mock maker và cấu hình Mockito của dự án; phương thức private hoặc static không được spy theo cách thông thường như một lời gọi instance. Với các API khó quan sát, có thể cần thay đổi thiết kế dependency hoặc kiểm tra hành vi qua public boundary.

Không dùng spy để kiểm tra chi tiết nội bộ chỉ vì Mockito cho phép verify. Nếu mục tiêu nghiệp vụ có thể được xác nhận qua kết quả đầu ra, assertion kết quả thường bền vững hơn assertion vào mọi lời gọi bên trong.

## Ví dụ kiểm tra không gọi collaborator khi đầu vào không hợp lệ

Spy cũng hữu ích khi muốn xác nhận một bean thật không bị gọi trong một nhánh nghiệp vụ:

~~~java
@Test
void doesNotCalculateTaxForNegativeAmount() {
    assertThatThrownBy(() ->
        invoiceService.total(new BigDecimal("-1.00"))
    ).isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(taxCalculator);
}
~~~

Test giả định `InvoiceService` kiểm tra số tiền âm trước khi gọi `TaxCalculator`. Vì `taxCalculator` là spy, `verifyNoInteractions` xác nhận service không gọi collaborator trong nhánh đầu vào không hợp lệ. Phương thức thật của tax calculator không bị thực thi trong test này.

Kiểm tra không tương tác có ý nghĩa khi hợp đồng yêu cầu bỏ qua collaborator. Nếu lời gọi nội bộ không ảnh hưởng hành vi hoặc tài nguyên, không cần ràng buộc test vào nó.

## Cách lựa chọn và sử dụng spy có chủ đích

Hãy bắt đầu từ mục tiêu cần quan sát. Nếu cần giữ bean thật và xác minh bean khác gọi nó đúng cách, dùng `@MockitoSpyBean`. Nếu muốn thay toàn bộ dependency để cô lập unit, dùng `@MockitoBean`. Nếu chỉ cần spy một object cục bộ ngoài Spring context, dùng `@Spy` của Mockito.

Khi dùng `@MockitoSpyBean`, hãy bảo đảm bean đã tồn tại trong context, chọn đúng ứng viên bằng kiểu và qualifier, để phương thức thật chạy khi phù hợp, và dùng `doReturn`/ `doThrow` khi cần stub để tránh vô tình gọi phương thức thật trong bước thiết lập. Xác minh các tương tác thuộc hợp đồng, đồng thời quản lý side effect của phương thức thật bằng transaction hoặc cleanup thích hợp.

Một spy tốt giúp test nhìn thấy cách các bean thật cộng tác trong ApplicationContext mà vẫn giữ được quyền kiểm soát đối với một số lời gọi. Dùng đúng phạm vi sẽ giúp phát hiện lỗi wiring và lỗi phối hợp mà mock thuần có thể che khuất, đồng thời giữ test tập trung vào hành vi cần chứng minh.
