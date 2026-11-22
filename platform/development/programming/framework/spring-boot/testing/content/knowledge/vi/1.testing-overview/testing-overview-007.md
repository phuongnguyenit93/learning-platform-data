# Kiểm thử hành vi quan sát được và tránh bám chặt cách hiện thực

Trong Spring Boot, kiểm thử có giá trị khi cho biết **hệ thống có giữ đúng cam kết với người sử dụng hoặc thành phần gọi nó hay không**. Một bài test có thể “xanh” nhưng ít giá trị nếu chỉ xác nhận lớp A đã gọi phương thức B; ngược lại, test tốt vẫn đúng khi ta đổi thuật toán, tách lớp hoặc tối ưu truy vấn mà kết quả người dùng nhận được không đổi.

**Sau bài này, bạn có thể:** xác định ranh giới quan sát được của một chức năng; chuyển yêu cầu thành ca kiểm thử theo đầu vào–đầu ra–lỗi–tác dụng phụ; viết unit test và web slice test bảo vệ hành vi; biết lúc nào nên kiểm tra tương tác với dependency; và nhận diện các assertion khiến test vỡ chỉ vì refactor.

## 1. “Hành vi quan sát được” là gì?

Đó là điều mà một bên sử dụng chức năng có thể nhận biết hoặc được quyền phụ thuộc vào theo **contract** (hợp đồng hành vi). “Bên sử dụng” có thể là khách hàng HTTP API, một lớp gọi public method, consumer của sự kiện, hoặc một hệ thống bên ngoài.

| Ranh giới kiểm thử | Hành vi đáng kiểm chứng | Chi tiết thường không cần cố định |
|---|---|---|
| HTTP API | Status, cấu trúc và ý nghĩa JSON, validation, quyền truy cập, header theo hợp đồng | Tên method controller, số lần controller gọi service, DTO mapper nội bộ |
| Public service | Giá trị trả về, loại lỗi đã quy định, trạng thái được thay đổi, yêu cầu gửi qua cổng bên ngoài | Tên private method, vòng lặp hay stream, số object tạm |
| Persistence | Dữ liệu lưu/đọc được, ràng buộc nghiệp vụ, tính nguyên tử khi có yêu cầu | SQL sinh ra, tên helper, số lần gọi repository nếu không có contract hiệu năng |
| Messaging/remote API | Sự kiện hoặc yêu cầu thật sự phải gửi, nội dung, khóa idempotency khi được quy định | Cách tạo payload, tên lớp adapter, thao tác mapping trung gian |

Ví dụ: yêu cầu “khách hàng thành viên được giảm 10%, tổng tiền làm tròn đến hai chữ số thập phân” tạo ra hợp đồng về **số tiền cuối cùng**. Nó không yêu cầu code phải có một method `applyDiscount()`, dùng phép nhân trực tiếp hay tra bảng tỷ lệ. Test ràng buộc method nội bộ đó sẽ báo lỗi sai khi refactor hợp lệ.

**Phân biệt quan trọng:** “Quan sát được” không nhất thiết chỉ là `return`. Đơn hàng được lưu, email đã được yêu cầu gửi, giao dịch bị từ chối, hoặc sự kiện được phát ra cũng là kết quả có ý nghĩa. Ta có thể kiểm tra tương tác ở **cổng giao tiếp bên ngoài** khi chính tương tác đó là kết quả nghiệp vụ.

## 2. Đi từ yêu cầu đến ca kiểm thử

Trước khi chọn `@SpringBootTest` hay Mockito, hãy viết hợp đồng bằng câu cụ thể:

1. **Given:** trạng thái ban đầu và dữ liệu đầu vào hợp lệ/không hợp lệ là gì?
2. **When:** thao tác public hoặc request nào được thực hiện?
3. **Then:** kết quả nào phải quan sát được? Có phải kiểm tra cả lỗi, dữ liệu bền vững hoặc thông điệp gửi đi?
4. **Ngoài hợp đồng:** thay đổi nào của hiện thực nên được phép mà không làm test thất bại?

Ví dụ với chức năng báo giá:

| Tình huống | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Khách thường | `subtotal=100.00`, `member=false` | `100.00` |
| Thành viên | `subtotal=100.00`, `member=true` | `90.00` |
| Làm tròn | `subtotal=1.05`, `member=true` | `0.95`, quy tắc HALF_UP |
| Giá trị biên hợp lệ | `subtotal=0.00` | `0.00` |
| Dữ liệu nghiệp vụ sai | Tổng tiền âm hoặc `null` ở service | `IllegalArgumentException` |
| HTTP sai kiểu | `subtotal=abc` | HTTP `400 Bad Request` |

Chọn các ca biểu diễn **nhóm hành vi khác nhau**: bình thường, biên, nhánh quyết định, lỗi, và tác dụng phụ quan trọng. Đừng viết hàng chục test chỉ vì code có hàng chục nhánh nội bộ; cũng đừng chỉ thử happy path rồi bỏ qua lỗi khách hàng thực sự gặp.

Tên test nên nói rõ điều phải đúng, ví dụ `memberReceivesTenPercentDiscount` hoặc `rejectsNegativeSubtotal`, thay vì `callsHelperMethod`. Mỗi test nên có kết quả kiểm chứng rõ ràng; test chỉ chạy phương thức mà không assert hoặc verify điều gì đáng quan sát rất dễ tạo cảm giác an toàn giả.

## 3. Ví dụ 1 — unit test hành vi nghiệp vụ, không cần khởi động Spring

Giả sử ứng dụng Spring Boot có hai dependency `spring-boot-starter-web` và `spring-boot-starter-test`, dùng Java 17+. Ta đặt hai file trong package `com.example.testing`.

**`src/main/java/com/example/testing/QuoteService.java`**

```java
package com.example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private static final BigDecimal MEMBER_FACTOR = new BigDecimal("0.90");

    public BigDecimal quote(BigDecimal subtotal, boolean member) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }

        BigDecimal factor = member ? MEMBER_FACTOR : BigDecimal.ONE;
        return subtotal.multiply(factor).setScale(2, RoundingMode.HALF_UP);
    }
}
```

**`src/test/java/com/example/testing/QuoteServiceTest.java`**

```java
package com.example.testing;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class QuoteServiceTest {
    private final QuoteService service = new QuoteService();

    @ParameterizedTest
    @CsvSource({
        "100.00, false, 100.00",
        "100.00, true, 90.00",
        "19.99, true, 17.99",
        "1.05, true, 0.95",
        "0.00, true, 0.00"
    })
    void returnsContractedAmount(String input, boolean member, String expected) {
        BigDecimal actual = service.quote(new BigDecimal(input), member);

        assertThat(actual).isEqualByComparingTo(new BigDecimal(expected));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThatThrownBy(() -> service.quote(new BigDecimal("-1.00"), true))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsNullSubtotal() {
        assertThatThrownBy(() -> service.quote(null, false))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

**Vì sao đây là test theo hành vi?** Mỗi assertion bám vào số tiền hoặc loại lỗi mà người gọi service nhận được. Không có `verify(service).someInternalMethod()`, không đo số phép nhân, không đọc trường private. Nếu đổi cách biểu diễn tỷ lệ giảm giá mà hợp đồng vẫn giữ nguyên, test vẫn pass. `isEqualByComparingTo` so sánh giá trị số của `BigDecimal`; `BigDecimal.equals` còn so cả scale, nên chỉ nên dùng `equals` khi chính scale cũng là phần hợp đồng.

Đây là **unit test thuần**: không có `@SpringBootTest`, database hay HTTP server. Annotation `@Service` giúp lớp được phát hiện khi chạy ứng dụng, nhưng không buộc ta phải bật Spring context khi chỉ kiểm tra thuật toán thuần.

Mẫu **Arrange – Act – Assert** hiện diện rõ: chuẩn bị `BigDecimal`, gọi `quote`, rồi xác nhận giá trị. Với exception, hành vi được quan sát là ngoại lệ mà method public ném ra; nếu văn bản thông báo lỗi chưa là hợp đồng, chỉ cần kiểm tra đúng loại ngoại lệ, tránh cố định nguyên văn thông điệp có thể thay đổi.

## 4. Ví dụ 2 — bảo vệ HTTP contract bằng `@WebMvcTest`

Khi gọi qua HTTP, yêu cầu khác với unit test của service: Spring MVC phải bind query parameter, tạo response JSON và chuyển lỗi thành HTTP status phù hợp. Ta kiểm tra **request/response**, không kiểm tra controller đã gọi helper nào.

**`src/main/java/com/example/testing/QuoteController.java`**

```java
package com.example.testing;

import java.math.BigDecimal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {
    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @GetMapping
    public QuoteResponse getQuote(
            @RequestParam BigDecimal subtotal,
            @RequestParam(defaultValue = "false") boolean member) {
        return new QuoteResponse(service.quote(subtotal, member));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiError handleInvalidSubtotal(IllegalArgumentException error) {
        return new ApiError(error.getMessage());
    }

    public record QuoteResponse(BigDecimal total) {}
    public record ApiError(String message) {}
}
```

**`src/test/java/com/example/testing/QuoteControllerWebTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
@Import(QuoteService.class)
class QuoteControllerWebTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void exposesMemberQuoteThroughHttp() throws Exception {
        mvc.perform(get("/api/quotes")
                .param("subtotal", "100.00")
                .param("member", "true"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.total").value(90.0));
    }

    @Test
    void mapsNegativeSubtotalToBadRequest() throws Exception {
        mvc.perform(get("/api/quotes")
                .param("subtotal", "-1.00"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").isNotEmpty());
    }

    @Test
    void rejectsUnparsableSubtotal() throws Exception {
        mvc.perform(get("/api/quotes")
                .param("subtotal", "abc"))
            .andExpect(status().isBadRequest());
    }
}
```

Ở đây `@WebMvcTest` khởi tạo lát cắt Spring MVC thay vì toàn bộ ứng dụng; `@Import(QuoteService.class)` cung cấp service thật đơn giản cho controller. Kiểm thử xác nhận định tuyến, bind dữ liệu, serialization và HTTP error mapping. Nó không khóa test vào số lần gọi service hoặc tên method Java. Nếu dự án bật Spring Security, hãy cấu hình authentication/CSRF theo hợp đồng API; không tắt filter tùy tiện chỉ để test “xanh”.

Lưu ý sự khác nhau giữa hai lỗi: `subtotal=abc` không chuyển được thành `BigDecimal` nên Spring MVC thường phản hồi `400` ngay ở bước bind; `subtotal=-1.00` chuyển đổi được nhưng vi phạm quy tắc nghiệp vụ, nên controller trong ví dụ có `@ExceptionHandler` trả `400`. Nếu ứng dụng không có ánh xạ lỗi nghiệp vụ tương ứng, đừng mặc định kỳ vọng mọi `IllegalArgumentException` tự động trở thành `400`.

Bộ test này bảo vệ những thuộc tính HTTP đã thể hiện rõ trong yêu cầu. Khi API còn phải bảo đảm quyền truy cập, header, kiểu lỗi, phân trang hoặc idempotency, hãy đưa các thuộc tính đó vào bài test riêng. Tránh snapshot nguyên cả response khi chỉ một số trường thực sự là hợp đồng: thêm trường JSON hợp lệ không nên làm hỏng test nếu client vẫn hoạt động đúng.

## 5. Khi nào `verify(...)` của Mockito là hợp lý?

Một tương tác **có thể chính là tác dụng phụ cần được bảo vệ**. Ví dụ sau khi người dùng hoàn tất đăng ký, ứng dụng phải gửi yêu cầu phát một email chào mừng. Nếu email sender là cổng ra của hệ thống, ta có thể kiểm tra lời gọi gửi email vì đó là contract của use case.

Đoạn sau là ví dụ riêng; các lớp ở cùng package, không liên quan đến `QuoteService`:

```java
package com.example.testing;

interface MailPort {
    void sendWelcome(String email);
}

final class WelcomeNotifier {
    private final MailPort mailPort;

    WelcomeNotifier(MailPort mailPort) {
        this.mailPort = mailPort;
    }

    void notifyRegistration(String email) {
        mailPort.sendWelcome(email);
    }
}
```

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class WelcomeNotifierTest {
    @Test
    void requestsWelcomeEmailForNewRegistrant() {
        MailPort mailPort = mock(MailPort.class);
        WelcomeNotifier notifier = new WelcomeNotifier(mailPort);

        notifier.notifyRegistration("an@example.com");

        verify(mailPort).sendWelcome("an@example.com");
    }
}
```

Lệnh `verify` ở đây kiểm tra lệnh gửi qua cổng bên ngoài, là kết quả của hành động. Nếu nghiệp vụ quy định “không gửi email khi đầu vào không hợp lệ”, kiểm tra **không có tương tác** với cổng trong nhánh đó cũng có ý nghĩa. Với luồng thực tế, có thể dùng fake/adapter ghi nhận yêu cầu, hoặc test tích hợp với message broker giả lập khi cần kiểm chứng khả năng giao hàng.

Ngược lại, các assertion như “controller gọi mapper hai lần”, “service gọi private helper trước validator” hay “repository chạy chính xác ba method theo đúng thứ tự” thường ràng buộc **cách viết code**. Chỉ kiểm tra số lần hoặc thứ tự nếu đó thật sự là yêu cầu: ví dụ không thu tiền hai lần, thứ tự hai sự kiện có ý nghĩa nghiệp vụ, hay giới hạn số truy vấn là mục tiêu hiệu năng đã định nghĩa.

**Quy tắc chọn mock:** mock phụ thuộc nằm ngoài phạm vi test để chủ động tạo tình huống (remote API trả lỗi, timeout, hết hàng); giữ thật phần thuật toán đang được kiểm tra. Mock luôn chính phương thức mình muốn kiểm thử rồi assert giá trị mock trả về là kiểm tra thiết lập của mock, không chứng minh logic sản phẩm.

## 6. Refactor không được làm test “đỏ” nếu contract không đổi

Một test tốt có tính **chịu được refactor** (refactoring resilience). Hãy đặt câu hỏi: “Nếu hôm nay chuyển từ vòng lặp sang stream, tách một helper, thay adapter lưu dữ liệu hoặc đổi tên method nội bộ, nhưng đầu ra và tác dụng phụ vẫn đúng, bài test có còn pass không?”

| Kiểm thử dễ vỡ | Cách kiểm chứng bền hơn |
|---|---|
| `verify(spy).calculateDiscount()` | Assert tổng tiền cuối cùng theo nhiều trường hợp |
| Assert DTO bằng cách soi mọi field nội bộ, kể cả field không công bố | Assert các trường thực sự là HTTP/API contract |
| `verify(repository, times(2)).findById(...)` vì code hiện có hai lần tìm | Assert kết quả nghiệp vụ và trạng thái lưu trữ đúng; đo số query riêng nếu có yêu cầu hiệu năng |
| Assert đúng thông điệp exception dù chưa có đặc tả wording | Assert loại lỗi, mã HTTP hoặc mã lỗi public; chỉ khóa câu chữ khi được công bố |
| Dựa vào `Thread.sleep(500)`, thời gian máy hoặc thứ tự test | Tiêm `Clock`, fake scheduler, kiểm soát dữ liệu và trạng thái độc lập |
| Test đọc trường `private` qua reflection | Kiểm tra public behavior hoặc tác dụng phụ; tách logic thật sự thành thành phần có contract nếu cần |

Ví dụ, `QuoteService` có thể được sửa để lấy phần trăm từ cấu hình, dùng một chiến lược tính giá hoặc chia nhỏ thành nhiều lớp. Miễn các ca bảng đầu vào–kết quả vẫn đúng, test nghiệp vụ không cần chỉnh. Nhưng nếu yêu cầu đổi từ “giảm 10%” sang “giảm 15%”, test **phải thất bại** cho đến khi cập nhật hợp đồng và code; đó là thất bại hữu ích.

Đừng hiểu “không bám cách hiện thực” thành “không được kiểm tra kiến trúc”. Một số đặc tính kỹ thuật cũng là contract khi đã có yêu cầu: transaction phải rollback nguyên vẹn, dữ liệu nhạy cảm không xuất hiện trong HTTP response, không phát sự kiện trùng lặp, API phải idempotent, hoặc số truy vấn phải nằm dưới ngưỡng. Lúc đó, chọn phép đo và cấp test phù hợp để kiểm chứng chính đặc tính đó.

## 7. Test ổn định với thời gian, dữ liệu và môi trường

Test phụ thuộc thời gian thực, random hoặc mạng ngoài rất dễ thất bại ngẫu nhiên. Hành vi vẫn có thể được kiểm thử mà không phụ thuộc lúc test chạy: inject `java.time.Clock` và cố định thời điểm trong test. Ví dụ:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;

public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
```

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ExpiryPolicyTest {
    @Test
    void expiresExactlyAtDeadline() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");
        Clock clock = Clock.fixed(now, ZoneOffset.UTC);
        ExpiryPolicy policy = new ExpiryPolicy(clock);

        assertThat(policy.expired(now)).isTrue();
        assertThat(policy.expired(now.plusSeconds(1))).isFalse();
    }
}
```

Ở thời điểm đúng bằng deadline, chính sách trong ví dụ xem là đã hết hạn; một giây sau deadline vẫn còn hiệu lực. Test thể hiện **quy tắc biên**, không chờ đồng hồ chạy hoặc phụ thuộc múi giờ máy.

Tương tự, với UUID/random có thể tiêm nguồn sinh dữ liệu; với HTTP bên ngoài có thể dùng fake server, WireMock hoặc một adapter kiểm soát được; với database dùng dữ liệu fixture độc lập và rollback/cleanup có chủ đích. Một test chỉ pass khi chạy sau test khác là dấu hiệu trạng thái rò rỉ, không phải hành vi mong muốn.

## 8. Chọn đúng mức kiểm thử trong Spring Boot

Không phải hành vi nào cũng cần `@SpringBootTest`:

| Mức | Dùng khi muốn bảo vệ | Công cụ gợi ý |
|---|---|---|
| Unit | Thuật toán, nhánh nghiệp vụ, validation trong service | JUnit 5, AssertJ, Mockito ở dependency boundary |
| Web slice | Routing, binding, validation, JSON, status, controller advice, security MVC | `@WebMvcTest` + `MockMvc` |
| Persistence slice | Mapping JPA, constraint, query, transaction với database phù hợp | `@DataJpaTest`; Testcontainers khi cần DB giống thực tế |
| Integration | Tương tác các bean, cấu hình và thành phần thật trong một luồng | `@SpringBootTest`; `MockMvc` hoặc HTTP client khi cần |
| End-to-end | Hành trình bên ngoài gồm các hệ thống đã kết nối | Môi trường kiểm thử tích hợp và kiểm soát dữ liệu |

Hãy dùng mức **nhỏ nhất vẫn quan sát được hợp đồng cần bảo vệ**. Test unit nhanh cho nhiều biến thể; test slice cho Spring MVC/JPA; test tích hợp có chọn lọc cho đường đi xuyên nhiều thành phần. Không dùng `@SpringBootTest` cho một phép tính thuần, cũng không dùng unit test mock hoàn toàn repository để kết luận JPA query thật đã đúng.

Khi kiểm tra lỗi, nêu rõ nơi lỗi phát sinh và nơi lỗi được ánh xạ: service có thể ném `IllegalArgumentException`; API cần `400` thì phải có lớp xử lý HTTP thích hợp. Với bảo mật, `401`/`403`, authentication và authorization là phần hành vi quan sát được, nên test các tình huống được phép và bị từ chối theo hợp đồng sản phẩm.

## 9. Chạy ví dụ và hiểu kết quả

Trong một module Spring Boot dùng Gradle/Groovy, bảo đảm có các dependency tương ứng (nếu module đã có thì không khai báo lặp):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đặt đúng tên file/class/package như ví dụ. Chạy từ thư mục Gradle project có task `test` (với multi-project, thêm đường dẫn task module phù hợp):

```bash
./gradlew test --tests com.example.testing.QuoteServiceTest --tests com.example.testing.QuoteControllerWebTest --tests com.example.testing.WelcomeNotifierTest --tests com.example.testing.ExpiryPolicyTest
```

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`. Các test dùng JUnit 5; `spring-boot-starter-test` cung cấp AssertJ và Mockito. Kết quả mong đợi: các phương thức test đều pass; Gradle báo `BUILD SUCCESSFUL` khi project được cấu hình đúng và các dependency được tải thành công. Không có một dòng stdout cố định của chương trình nghiệp vụ, vì ví dụ là JUnit test, không phải ứng dụng `main()` in ra console. Nếu ứng dụng đang bật Spring Security hoặc có cấu hình web đặc thù, web slice test cần cấu hình phù hợp với API thực tế như đã nêu ở mục 4.

Bạn có thể tự kiểm nghiệm tính chịu refactor: sửa nội bộ phép tính thành một helper mới nhưng giữ kết quả, chạy lại test và xác nhận test không phải sửa. Sau đó cố ý đổi hệ số thành `0.80` mà không đổi yêu cầu: test `100.00,true,90.00` phải thất bại. Đó là khác biệt giữa **test bắt hồi quy hành vi** và **test bắt đổi cách viết code**.

## 10. Checklist trước khi chấp nhận một test

- [ ] Tên test thể hiện quy tắc nghiệp vụ hoặc contract công khai.
- [ ] Có Given/When/Then rõ; assertion xác nhận đầu ra, lỗi, trạng thái hoặc tác dụng phụ đáng quan sát.
- [ ] Có ca giá trị biên, dữ liệu không hợp lệ và nhánh có ý nghĩa; không chỉ happy path.
- [ ] Không verify helper, số lần mapping hay thứ tự gọi nội bộ trừ khi có lý do thuộc hợp đồng.
- [ ] Mock/fake phụ thuộc bên ngoài; phần logic cần bảo vệ vẫn được chạy thật.
- [ ] Test không phụ thuộc đồng hồ thực, mạng công cộng, thứ tự chạy, dữ liệu thừa hoặc log ngẫu nhiên.
- [ ] Cấp test đủ để quan sát điều được khẳng định (unit, web slice, persistence hay integration).
- [ ] Có thể refactor an toàn mà test vẫn pass; khi hành vi sai, test thất bại rõ nguyên nhân.

**Câu hỏi tự kiểm:** Nếu lập trình viên thay toàn bộ nội bộ của service nhưng API response, trạng thái dữ liệu, lỗi và sự kiện đã cam kết vẫn giống trước, test nào nên pass? Những test nào sẽ fail dù người dùng không thấy thay đổi? Hãy giữ nhóm đầu làm lớp bảo vệ chính, và xem lại lý do tồn tại của nhóm sau.

**Thông điệp cốt lõi:** Kiểm thử tốt khóa chặt **điều hệ thống phải làm** và để ngỏ **cách hệ thống làm điều đó**. Chính ranh giới này giúp test vừa phát hiện hồi quy vừa không cản trở refactor.