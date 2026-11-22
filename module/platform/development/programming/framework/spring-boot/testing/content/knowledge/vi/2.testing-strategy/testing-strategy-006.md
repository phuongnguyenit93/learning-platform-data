# Arrange–Act–Assert và Given–When–Then: mô tả hành vi khi kiểm thử Spring Boot

## Mục tiêu

Sau bài này, bạn có thể diễn đạt một yêu cầu thành tình huống kiểm thử có đầu vào và kết quả quan sát được; tổ chức mã JUnit theo **Arrange–Act–Assert (AAA)**; viết mô tả **Given–When–Then (GWT)** để người đọc hiểu hành vi nghiệp vụ; và chọn đúng thứ cần xác nhận ở mức unit test, web slice test hoặc integration test.

Hai cách diễn đạt bổ trợ nhau: **GWT nói hệ thống phải làm gì trong một hoàn cảnh; AAA tổ chức mã kiểm thử để chứng minh điều đó.** Chúng không thay thế việc xác định yêu cầu, chọn dữ liệu biên và đặt assertion đúng.

## 1. Hai mô hình và cách ánh xạ

| AAA – cấu trúc mã test | GWT – ngôn ngữ hành vi | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Arrange** | **Given** | Trạng thái ban đầu, dữ liệu, đối tượng, dependency và tiền điều kiện là gì? |
| **Act** | **When** | Người dùng hoặc hệ thống thực hiện hành động nào? |
| **Assert** | **Then** | Kết quả quan sát được và quy tắc nào phải đúng? |

**Arrange** tạo đúng bối cảnh của tình huống: đối tượng cần kiểm thử (SUT – system under test), dữ liệu đầu vào, dependency giả lập khi thực sự cần, trạng thái cơ sở dữ liệu hoặc yêu cầu HTTP. Chỉ dựng những thứ liên quan đến kết quả mong đợi; đừng giấu dữ liệu quan trọng trong một bộ fixture quá lớn.

**Act** gọi hành vi đang kiểm tra, thường là **một hành động logic** (một phương thức, một HTTP request, một lệnh hoặc một bước chuyển trạng thái). Nếu hành vi vốn là quy trình nhiều bước, có thể có nhiều thao tác nhưng phải thể hiện rõ chuỗi điều kiện và kết quả; không trộn các hành vi độc lập vào một test.

**Assert** kiểm tra kết quả đã cam kết với bên gọi: giá trị trả về, exception thuộc hợp đồng, HTTP status/body/header, trạng thái đã lưu, sự kiện phát ra hoặc tác động quan sát được. Assertion phải thất bại khi quy tắc bị vi phạm. Kiểm tra số lần gọi mock chỉ hữu ích nếu tương tác đó chính là hợp đồng cần bảo vệ.

Trong GWT, **Given** thường diễn đạt tiền điều kiện bằng ngôn ngữ miền nghiệp vụ; **When** diễn đạt sự kiện kích hoạt; **Then** nêu kết quả có thể kiểm chứng. Có thể dùng **And/But** để bổ sung điều kiện hoặc kết quả, nhưng vẫn nên giữ một ý nghĩa hành vi nhất quán.

### AAA và GWT khác nhau ở đâu?

- AAA là **cách bố trí mã** trong một phương thức kiểm thử. Bạn có thể dùng AAA với JUnit 5, Mockito, MockMvc, kiểm thử cơ sở dữ liệu hoặc kiểm thử thuần Java.
- GWT là **cách mô tả ví dụ về hành vi** để developer, tester và người hiểu nghiệp vụ cùng thảo luận. Có thể viết GWT bằng văn bản, tên test, comment hoặc Gherkin.
- Viết ba comment `Given/When/Then` không tự khiến test trở thành BDD. BDD (Behavior-Driven Development) nhấn mạnh việc thống nhất ví dụ và tiêu chí chấp nhận giữa các vai trò; công cụ như Cucumber chỉ là một lựa chọn tự động hóa.
- Gherkin dạng `Feature/Scenario/Given/When/Then` là đặc tả đọc được. Muốn chạy tự động qua Cucumber cần cấu hình runner và step definitions tương ứng; viết file `.feature` riêng không đủ.

## 2. Từ yêu cầu nghiệp vụ đến tình huống có thể kiểm chứng

Giả sử có quy tắc: **khách VIP giảm 10% trên tổng tiền hợp lệ, khách thường không được giảm; số tiền cuối cùng có hai chữ số thập phân và làm tròn HALF_UP; tổng tiền âm bị từ chối**.

Đừng bắt đầu bằng việc đoán tên method hay số lần gọi repository. Hãy viết ví dụ dễ kiểm tra:

~~~gherkin
Feature: Tính số tiền cuối cùng

  Scenario: Khách VIP được giảm 10%
    Given tổng tiền trước giảm là 100.00
    And khách hàng là VIP
    When hệ thống tính tiền cuối cùng
    Then số tiền cuối cùng là 90.00

  Scenario: Tổng tiền âm không hợp lệ
    Given tổng tiền trước giảm là -1.00
    When hệ thống tính tiền cuối cùng
    Then yêu cầu bị từ chối vì tổng tiền không hợp lệ
~~~

Ở tình huống đầu, **Given** mô tả `100.00` và `VIP`, **When** là tính tiền, **Then** là `90.00`. Tình huống thứ hai mô tả một kết quả lỗi, nhưng không áp đặt chi tiết kỹ thuật như tên exception nếu đang viết yêu cầu cho nghiệp vụ. Khi triển khai test ở tầng Java, ta mới ánh xạ quy tắc từ chối sang loại exception đã được thiết kế.

Một tập ví dụ nên bổ sung đường đi thông thường và trường hợp biên: khách thường, tổng bằng 0, làm tròn số lẻ và đầu vào không hợp lệ. Mỗi tình huống phải cho biết **đầu vào cụ thể và kết quả kỳ vọng cụ thể**, thay vì chỉ viết “hệ thống hoạt động đúng”.

## 3. Ví dụ JUnit 5 đầy đủ: cùng một hành vi, hai cách đọc

Trong một ứng dụng Spring Boot dùng Java 17+ với `spring-boot-starter-test`, đặt hai tệp sau đúng đường dẫn. Đây là **unit test của quy tắc tính tiền**: tạo service trực tiếp, không khởi động Spring ApplicationContext và không cần web server.

**`src/main/java/com/example/testing/DiscountCalculator.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Service;

@Service
public class DiscountCalculator {

    public BigDecimal finalAmount(BigDecimal subtotal, boolean vip) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be non-negative");
        }

        BigDecimal multiplier = vip
                ? new BigDecimal("0.90")
                : BigDecimal.ONE;

        return subtotal.multiply(multiplier)
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

`BigDecimal` giữ phép tính tiền theo số thập phân, tránh dùng `double` để so sánh giá trị tiền. Nhân với `0.90` nghĩa là giữ 90% sau giảm; `setScale(2, HALF_UP)` đặt rõ chính sách làm tròn. Annotation `@Service` cho phép Spring quản lý class trong ứng dụng thực, nhưng không buộc unit test dưới đây phải mở Spring context.

**`src/test/java/com/example/testing/DiscountCalculatorTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DiscountCalculatorTest {

    @Test
    void givenVip_whenCalculatingFinalAmount_thenAppliesTenPercentDiscount() {
        // Arrange / Given
        DiscountCalculator calculator = new DiscountCalculator();
        BigDecimal subtotal = new BigDecimal("100.00");

        // Act / When
        BigDecimal actual = calculator.finalAmount(subtotal, true);

        // Assert / Then
        assertEquals(new BigDecimal("90.00"), actual);
    }

    @ParameterizedTest
    @CsvSource({
        "100.00, false, 100.00",
        "0.00, true, 0.00",
        "50.00, true, 45.00"
    })
    void givenValidSubtotal_whenCalculating_thenReturnsExpectedAmount(
            String subtotal, boolean vip, String expected) {
        // Arrange / Given
        DiscountCalculator calculator = new DiscountCalculator();

        // Act / When
        BigDecimal actual = calculator.finalAmount(
                new BigDecimal(subtotal), vip);

        // Assert / Then
        assertEquals(new BigDecimal(expected), actual);
    }

    @Test
    void givenFractionalSubtotal_whenCalculating_thenRoundsHalfUp() {
        // Arrange / Given
        DiscountCalculator calculator = new DiscountCalculator();

        // Act / When
        BigDecimal actual = calculator.finalAmount(
                new BigDecimal("10.05"), true);

        // Assert / Then: 10.05 * 0.90 = 9.045 -> 9.05
        assertEquals(new BigDecimal("9.05"), actual);
    }

    @Test
    void givenNegativeSubtotal_whenCalculating_thenRejectsInput() {
        // Arrange / Given
        DiscountCalculator calculator = new DiscountCalculator();
        BigDecimal invalidSubtotal = new BigDecimal("-1.00");

        // Act + Assert / When + Then
        assertThrows(IllegalArgumentException.class,
                () -> calculator.finalAmount(invalidSubtotal, false));
    }
}
~~~

**Phân tích bài test VIP:** đối tượng `calculator` và tổng tiền `100.00` là Arrange/Given; lời gọi `finalAmount(…, true)` là Act/When; so sánh đúng `90.00` là Assert/Then. Người đọc thấy quy tắc kiểm thử từ tên method, đầu vào và assertion mà không cần đọc thuật toán giảm giá.

**Phân tích bài test lỗi:** `assertThrows` bao lấy hành động cần phát sinh exception, nên Act và Assert xuất hiện cùng một biểu thức. Đây là cách chuẩn khi **exception chính là kết quả mong đợi**, không phải vi phạm quy tắc AAA. Không dùng `try/catch` rồi bỏ qua exception: test đó có thể “đỗ” ngay cả khi hành động không ném lỗi.

**Lưu ý về BigDecimal:** `assertEquals` dùng `equals`, vì thế `90.0` và `90.00` không bằng nhau dù có cùng giá trị số học. Ở đây service luôn `setScale(2)`, còn expected cũng có hai chữ số thập phân, nên so sánh chính xác và nhất quán. Nếu hợp đồng không yêu cầu scale, hãy quyết định cách so sánh giá trị số học một cách có chủ đích (ví dụ dùng `compareTo`), đừng sửa expected tùy tiện cho test “xanh”.

Trong dự án Spring Boot đã khai báo dependency kiểm thử, Gradle Groovy thường có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy từ thư mục Gradle project chứa các test (hoặc chọn đúng subproject trong multi-project):

~~~bash
./gradlew test
~~~

Trên Windows PowerShell dùng `.\gradlew.bat test`. Test thành công được runner báo là passed; **các method trên không tự in stdout**. Không suy ra test đã chạy chỉ vì mã có annotation `@Test`: cấu hình JUnit Platform và dependency test phải sẵn sàng. Bộ mẫu gồm ba lần chạy của parameterized test và ba method `@Test`, tức **6 lượt kiểm tra** khi chạy toàn bộ class.

## 4. Chọn ranh giới quan sát trong Spring Boot

AAA và GWT không gắn với một annotation duy nhất. Cùng câu chuyện nghiệp vụ có thể được kiểm ở nhiều tầng; điểm **Assert/Then** thay đổi theo hợp đồng của tầng đó:

| Ranh giới test | Arrange/Given | Act/When | Assert/Then |
| --- | --- | --- | --- |
| **Unit test** service/domain | Đối tượng, dữ liệu, mock thật sự cần | Gọi phương thức | Giá trị, exception, trạng thái hoặc tương tác có ý nghĩa |
| **Web slice test** với `@WebMvcTest`, `MockMvc` | Request, cấu hình controller, dependency giả lập | Gửi HTTP request giả lập | HTTP status, JSON, header, validation/error response |
| **Integration test** với `@SpringBootTest` và hạ tầng phù hợp | Spring context, bản ghi ban đầu, cấu hình test | Chạy một luồng qua nhiều bean/lớp | Hành vi xuyên tầng, dữ liệu đã lưu, transaction, response hoặc sự kiện quan sát được |

**Ví dụ minh họa tại tầng HTTP** (không phải class độc lập): giả sử ứng dụng có endpoint `GET /api/quotes?subtotal=100.00&vip=true` trả JSON `{"total":"90.00"}`. Trong test đã được cấu hình `MockMvc`, một kịch bản có thể viết:

~~~java
@Test
void givenVipQuote_whenRequestingQuote_thenReturnsDiscountedTotal()
        throws Exception {
    // Given: endpoint và dependency đã được cấu hình trong test fixture

    // When + Then: thực hiện request và kiểm tra response
    mockMvc.perform(get("/api/quotes")
            .param("subtotal", "100.00")
            .param("vip", "true"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.total").value("90.00"));
}
~~~

Snippet này **giả định** đã có controller, tuyến API đúng như mô tả, đối tượng `mockMvc`, import của JUnit/MockMvc, và cấu hình dependency phù hợp; nó minh họa cách diễn đạt AAA/GWT ở tầng web, **không phải chương trình chạy độc lập**. `mockMvc.perform(…)` là Act; các `andExpect(…)` là Assert. Nếu service được mock ở web slice, hãy cấu hình kết quả mock ở Arrange. Khi đó test khẳng định cách controller ánh xạ request/response, **không chứng minh thuật toán giảm giá thật**; thuật toán đã có unit test riêng.

Với `@SpringBootTest`, chỉ sử dụng khi cần xác minh sự cộng tác thực sự giữa nhiều bean, cấu hình, database hoặc giao dịch. Test tích hợp cần trạng thái dữ liệu độc lập và dọn dẹp hợp lý; AAA/GWT giúp bộc lộ các tiền điều kiện đó. Không bật toàn bộ Spring context chỉ để kiểm tra một phép tính thuần Java.

## 5. Viết một test dễ đọc và thực sự có khả năng phát hiện lỗi

**Bắt đầu bằng Then.** Trước khi code, hãy trả lời: “Nếu tính năng hỏng, assertion nào sẽ chuyển từ pass sang fail?” Với quy tắc VIP, `actual = 90.00` cần được so với con số đã xác định độc lập trong ví dụ; không tính expected bằng chính công thức đang được kiểm thử, vì hai bên có thể cùng sai.

**Giữ một hành vi chính cho một test.** Một test có thể có nhiều assertion cùng phục vụ một kết quả, ví dụ HTTP `201 Created`, `Location` và body của một thao tác tạo tài nguyên. Nhưng test không nên vừa kiểm đăng ký, đăng nhập, đổi mật khẩu và xóa người dùng nếu chúng là các hợp đồng tách biệt. Với quy trình nhiều bước không thể tách, đặt tên thể hiện toàn bộ chuỗi hành vi.

**Tên test mô tả điều kiện – hành động – kết quả.** Ví dụ `givenNegativeSubtotal_whenCalculating_thenRejectsInput` thông tin hơn `testCalculate1` hoặc `shouldWork`. Không bắt buộc dùng đúng ba từ tiếng Anh; quan trọng là nêu điều kiện, hành vi và mong đợi. Tên chỉ nói về implementation (`callsRepositoryTwice`) làm người học bỏ lỡ ý nghĩa nghiệp vụ, trừ khi số lần gọi thực sự là quy tắc cần kiểm tra.

**Giữ Arrange nhỏ và tường minh.** Các dữ liệu quyết định kết quả nên hiển thị tại test. Dùng `@BeforeEach` cho khởi tạo giống nhau thật sự, factory/test builder cho object phức tạp, nhưng tránh helper ẩn thay đổi tình huống. Dùng tên dữ liệu biểu đạt ý nghĩa: `invalidSubtotal`, `vipCustomer`, `existingOrder` thay vì `x`, `a1`.

**Chọn assertion theo contract.** Service trả tiền thì kiểm đúng tiền; controller thì kiểm HTTP contract; repository thì kiểm trạng thái truy xuất/lưu; event publisher thì kiểm sự kiện nếu sự kiện là kết quả cam kết. `verify(mock).save(…)` không tự chứng minh dữ liệu được lưu thật trong database; ngược lại, kiểm database thật ở một unit test thuần mock là sai ranh giới.

**Giữ test độc lập và ổn định.** Không phụ thuộc thứ tự chạy test, thời gian hệ thống, random không cố định, network thật hoặc dữ liệu của một bài khác. Nếu hành vi phụ thuộc đồng hồ, đưa `Clock` vào dependency có thể kiểm soát; nếu phụ thuộc bên ngoài, chọn fake/mock hoặc hạ tầng integration test ổn định. Với xử lý bất đồng bộ, phải chờ điều kiện bằng cơ chế có timeout rõ ràng thay vì `Thread.sleep` cố định rồi đoán đã hoàn tất.

## 6. Những trường hợp cần thiết kế rõ ràng

| Tình huống | Given / Arrange | When / Act | Then / Assert |
| --- | --- | --- | --- |
| Đường đi chính | VIP, tổng 100.00 | Tính tiền | 90.00 |
| Nhánh khác | Không VIP, tổng 100.00 | Tính tiền | 100.00 |
| Biên bằng 0 | VIP, tổng 0.00 | Tính tiền | 0.00 |
| Chính sách làm tròn | VIP, tổng 10.05 | Tính tiền | 9.05 theo HALF_UP |
| Dữ liệu không hợp lệ | Tổng -1.00 | Tính tiền | `IllegalArgumentException` theo thiết kế service |

Dùng `@ParameterizedTest` cho **cùng một quy tắc với nhiều bộ dữ liệu**, như nhánh VIP/không VIP và biên bằng 0 ở ví dụ. Dùng method `@Test` riêng nếu hành vi hoặc loại kết quả khác đáng kể, như trả giá trị so với ném exception. Không nhét mọi điều kiện vào một method dài với nhiều nhánh `if`, vì khi fail sẽ khó thấy trường hợp nào bị hỏng.

Với endpoint Spring Boot, một “Then yêu cầu bị từ chối” có thể được ánh xạ thành HTTP `400 Bad Request` nếu API contract quy định như vậy; bản thân unit test đang kiểm `IllegalArgumentException` của service. **Đừng áp đặt rằng mọi exception service mặc nhiên trở thành HTTP 400**: cần có validation hoặc exception handling đã thiết kế tại tầng web.

## 7. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao gây hại | Cách sửa |
| --- | --- | --- |
| AAA chỉ có tên/comment, không có assertion | Không phát hiện hành vi sai | Viết Then có kết quả quan sát được |
| Expected tính bằng lại chính thuật toán trong SUT | Cùng lỗi logic ở cả expected và actual có thể vẫn pass | Dùng ví dụ đầu vào–đầu ra độc lập, đã thống nhất |
| Arrange quá nhiều mock, fixture và trạng thái | Che nguyên nhân test fail, tạo phụ thuộc vào implementation | Chỉ chuẩn bị tiền điều kiện thiết yếu |
| Act chứa nhiều hành vi không liên quan | Không biết lỗi đến từ bước nào | Mỗi test một hành vi chính hoặc một quy trình có tên rõ |
| Assertion chỉ kiểm `not null` khi nghiệp vụ cần giá trị chính xác | Test pass dù kết quả sai | Assert đúng giá trị, trạng thái hoặc contract |
| Chỉ `verify` lời gọi nội bộ trong khi hợp đồng là output | Refactor vô hại cũng làm test gãy | Ưu tiên output; verify tương tác khi tương tác là yêu cầu |
| Test phụ thuộc thứ tự, đồng hồ hoặc dữ liệu dùng chung | Kết quả thất thường khi chạy CI/song song | Fixture độc lập, kiểm soát dependency, rollback/cleanup |
| GWT mô tả chi tiết code thay vì hành vi | Người không đọc code không hiểu kịch bản | Viết Given/When/Then bằng khái niệm miền nghiệp vụ |
| Coi Gherkin là test chạy được mà không gắn step definitions | Có đặc tả nhưng không có kiểm chứng tự động | Phân biệt tài liệu GWT, JUnit test và bộ chạy Cucumber |

Một cách tự kiểm tra giá trị của test là **thử tưởng tượng một lỗi có chủ đích**: đổi tỷ lệ VIP từ 10% thành 5%, hoặc bỏ kiểm tra số âm. Test liên quan phải fail. Nếu vẫn pass, Then/assertion hoặc ranh giới kiểm thử đang thiếu một phần yêu cầu.

## 8. Quy trình áp dụng trong công việc

1. **Chọn một quy tắc cụ thể** từ yêu cầu (ví dụ giảm 10% cho VIP); xác định đầu ra mà người dùng/hệ thống bên ngoài quan sát được.
2. **Viết Given–When–Then bằng dữ liệu cụ thể**, sau đó liệt kê trường hợp thường, trường hợp biên và trường hợp lỗi. Nếu kết quả còn mơ hồ, làm rõ yêu cầu trước khi tự động hóa.
3. **Chọn mức test phù hợp**: unit để kiểm logic; web slice để kiểm HTTP mapping; integration để kiểm phối hợp thực và lưu trữ.
4. **Viết mã theo AAA** và đặt tên theo hành vi. Ở Arrange chuẩn bị bối cảnh tối thiểu; ở Act kích hoạt hành vi; ở Assert đối chiếu kết quả đã định nghĩa độc lập.
5. **Chạy test, quan sát lỗi, rà lại độ tin cậy**. Đảm bảo test fail khi quy tắc bị phá, pass khi code đúng; giữ dữ liệu độc lập để CI có thể lặp lại.

### Bài tự luyện

Hãy mở rộng yêu cầu mẫu với quy tắc **chỉ khách VIP được giảm tiền và tổng tiền `null` bị từ chối**. Viết một câu GWT cho mỗi hành vi, rồi thêm JUnit test theo AAA. Với `subtotal = null`, method `finalAmount` ở ví dụ phải ném `IllegalArgumentException`; với khách thường và tổng `100.00`, kết quả phải là `100.00`. Sau đó thử sửa tạm hệ số VIP trong code để xác nhận test VIP thực sự phát hiện sai lệch, rồi hoàn nguyên.

**Ghi nhớ:** GWT biến quy tắc thành tình huống rõ ràng; AAA biến tình huống thành phép kiểm chứng có cấu trúc. Giá trị của bài test nằm ở **Then/Assert đúng hợp đồng và có khả năng phát hiện lỗi**, không nằm ở việc có đủ ba nhãn trong comment.