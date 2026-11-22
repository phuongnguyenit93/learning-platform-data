# Chi phí bảo trì và cách nhận diện kiểm thử giá trị thấp

Kiểm thử tự động là một khoản đầu tư: ta bỏ thời gian viết và duy trì test để phát hiện hồi quy trước khi người dùng gặp lỗi. Nhưng một test “xanh” chưa chắc tạo ra niềm tin đáng kể. Nếu nó chỉ xác nhận giá trị đã được mock, phụ thuộc vào tên helper nội bộ, hoặc thường xuyên thất bại ngẫu nhiên, chi phí bảo trì có thể lớn hơn lợi ích.

Trong Spring Boot, chi phí này còn bao gồm tạo `ApplicationContext`, migration database, khởi chạy container, chờ phản hồi mạng, làm sạch dữ liệu và điều tra lỗi CI. **Chiến lược kiểm thử tốt tối ưu khả năng phát hiện lỗi có ý nghĩa so với chi phí bảo trì**, đồng thời giữ đủ bằng chứng rằng các hợp đồng quan trọng vẫn đúng.

Sau bài này, bạn có thể: phân loại chi phí của một bài test; phát hiện dấu hiệu test giá trị thấp; phân biệt test trùng lặp với test bổ trợ ở các cấp khác nhau; chọn unit, slice hay integration test theo rủi ro; cải thiện một test dễ vỡ; và xây dựng quy trình rà soát bộ test dựa trên bằng chứng.

## 1. Test có giá trị khi bảo vệ một hợp đồng hoặc rủi ro rõ ràng

Một **hợp đồng hành vi** là điều bên sử dụng chức năng có quyền kỳ vọng. Bên sử dụng có thể là người gọi REST API, method public của service, database consumer, message subscriber hoặc dịch vụ bên ngoài.

Hành vi có thể quan sát gồm:

- Giá trị trả về và các trường hợp biên: tiền, giới hạn, trạng thái.
- Lỗi được cam kết: loại lỗi ở service, mã HTTP và mã lỗi công khai ở API.
- Dữ liệu thay đổi: bản ghi được lưu, giao dịch được rollback, không mất dữ liệu.
- Tác dụng phụ: sự kiện đã phát, yêu cầu thanh toán hoặc email đã gửi qua cổng.
- Quyền và bảo mật: một actor được phép hay bị từ chối thao tác.

Ngược lại, tên private method, số lần gọi mapper, chọn vòng lặp hay stream, thứ tự tạo object tạm thường chỉ là **cách thực hiện**. Nếu thay đổi cách thực hiện mà hành vi vẫn đúng, các test bảo vệ hợp đồng nên tiếp tục pass.

Hãy hỏi hai câu trước khi giữ hoặc thêm một test:

1. **Một bug thực tế nào sẽ làm test này đỏ?** Ví dụ tính sai mức phí đúng tại ngưỡng miễn phí, trả HTTP 500 thay vì 400, hoặc gửi tiền hai lần.
2. **Một refactor hợp lệ nào sẽ làm test này đỏ?** Nếu chỉ tách helper, đổi tên class hay dùng adapter khác đã làm test hỏng, test có thể đang bám vào cấu trúc hơn là hành vi.

Không phải mọi contract đều là hành vi nghiệp vụ thuần. Nếu yêu cầu quy định tính idempotency, số truy vấn tối đa, atomicity hoặc thứ tự hai sự kiện, các đặc tính kỹ thuật đó cũng đáng được test.

## 2. Các lớp chi phí bảo trì

| Nhóm chi phí | Ví dụ trong Spring Boot | Tác động |
|---|---|---|
| Viết và hiểu test | Tạo fixture, setup mock phức tạp, tên test mơ hồ | Tăng thời gian review và bàn giao |
| Thực thi | Boot context, Testcontainers, database migration, HTTP/I/O | Phản hồi từ CI chậm; ít chạy test thường xuyên |
| Sửa theo mã nguồn | Thêm field nội bộ làm snapshot khác; đổi constructor hoặc helper làm `verify` fail | Refactor hợp lệ kéo theo sửa nhiều test |
| Ổn định môi trường | Dữ liệu dùng chung, timeout, `Thread.sleep`, đồng hồ, API công cộng | Test flaky, phải rerun và điều tra |
| Chẩn đoán | Assertion chỉ nói “expected true”; nhiều log hoặc fixture khó tìm | Không biết bug ở sản phẩm, test hay hạ tầng |
| Duy trì hạ tầng | Docker, dịch vụ phụ trợ, credential, cấu hình CI, database seed | Tăng công vận hành và phụ thuộc ngoài |

Có thể nghĩ theo công thức định tính:

```text
Giá trị kiểm thử ≈ rủi ro được bảo vệ
                 × khả năng phát hiện hồi quy
                 × độ tin cậy của tín hiệu

Chi phí vòng đời ≈ viết + chạy lặp lại + sửa + điều tra + hạ tầng
```

Đây là mô hình để suy nghĩ, **không phải công thức tính điểm chính xác**: rủi ro và chi phí cơ hội không thể đo đơn giản bằng một con số. Một integration test mất vài phút nhưng bảo vệ thanh toán hoặc rollback giao dịch có thể rất đáng giữ; một unit test vài mili giây chỉ xác nhận getter mặc định có thể có ít giá trị.

Ví dụ minh họa: một nhóm test làm CI tăng 5 phút mỗi lượt, chạy 30 lượt/ngày, nghĩa là thêm 150 phút thời gian job/ngày. Đó chưa phải 150 phút chờ của con người vì job có thể chạy song song. Nếu còn một failure không ổn định khiến lập trình viên mất 20 phút điều tra, chi phí nhân lực thậm chí có thể lớn hơn chi phí máy.

## 3. Dấu hiệu cho biết test có thể có giá trị thấp

Dùng bảng sau như **tín hiệu cần điều tra**, không phải quy tắc xóa tự động.

| Dấu hiệu | Vì sao tín hiệu yếu | Ngoại lệ có lý do |
|---|---|---|
| Chạy method rồi kết thúc, không assert hay xác nhận side effect | Có thể pass dù hành vi sai | Smoke test cố ý xác nhận startup không lỗi |
| Mock chính đối tượng đang kiểm thử | Assert giá trị `thenReturn` thay vì chạy logic thật | Mock dependency nằm ngoài phạm vi hành vi mới hợp lý |
| `verify` từng lời gọi nội bộ, số lần mapper/helper, thứ tự private logic | Refactor cấu trúc làm test đỏ dù kết quả đúng | Số lần thu phí, phát sự kiện hoặc giới hạn truy vấn là yêu cầu thực |
| Test giống nhau chỉ đổi tên, cùng dữ liệu/nhánh/assertion | Tăng số test mà không tăng lỗi được phát hiện | Hai tầng test có thể bảo vệ hai contract khác nhau |
| `@SpringBootTest` chỉ để kiểm tra phép tính thuần | Khởi động context đắt mà không tăng tín hiệu | Một số luồng cần chứng minh wiring, transaction hoặc cấu hình |
| Assert nguyên JSON snapshot, log debug, message exception nội bộ | Thay đổi tương thích cũng làm test hỏng | Schema, audit log hoặc thông điệp là một phần contract công khai |
| Test dùng `sleep` hoặc dựa vào giờ máy, mạng thật, thứ tự test | Dễ flaky; không phản ánh lỗi ổn định của sản phẩm | Tính thời gian có thể là contract nếu dùng clock kiểm soát được |
| Test framework đã thực hiện hành vi chuẩn không tùy biến | Kiểm tra chức năng JUnit, Java hoặc Spring thay vì code sản phẩm | Cấu hình binder/converter/security riêng vẫn cần test |
| Test đòi sửa liên tục dù yêu cầu không đổi | Phụ thuộc DTO/fixture/implementation cụ thể | Đổi contract thực sự thì test phải đổi |
| Coverage tăng nhưng assertion không liên quan | Thực thi dòng không đồng nghĩa phát hiện sai logic | Coverage vẫn hữu ích để tìm đường chưa được chạy |

**Ví dụ `contextLoads()`:** Một test khởi tạo ứng dụng thành công có thể bắt bean cycle, property thiếu hoặc lỗi auto-configuration. Nó có giá trị như smoke test. Nhưng sao chép hàng chục test khởi động cùng context mà không thêm contract mới thường gây chi phí lặp lại. Nên xem việc cache context, cấu hình từng test và mục đích của từng biến thể trước khi quyết định gộp.

**Ví dụ repository:** `when(repository.findById(id)).thenReturn(...)` rồi assert kết quả mock không chứng minh query JPA, mapping entity, constraint hoặc transaction thật. Nếu mục tiêu là SQL/JPA, cần test với database ở cấp phù hợp.

## 4. Ví dụ Java 17+ — test rất nhanh nhưng chỉ kiểm tra Mockito

Giả định module Spring Boot có quy tắc vận chuyển:

- Đơn thường dưới `200.00`: phí `15.00`.
- Đơn thường từ `200.00`: miễn phí.
- Giao nhanh: phí `30.00` ở mọi tổng tiền hợp lệ.
- `subtotal` âm hoặc `null` không hợp lệ.
- Phí trả về có hai chữ số thập phân.

**`src/main/java/com/example/shipping/ShippingFeeService.java`**

```java
package com.example.shipping;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class ShippingFeeService {
    private static final BigDecimal THRESHOLD = new BigDecimal("200.00");
    private static final BigDecimal STANDARD = new BigDecimal("15.00");
    private static final BigDecimal EXPRESS = new BigDecimal("30.00");

    public BigDecimal quote(BigDecimal subtotal, boolean express) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("Subtotal must be non-negative");
        }
        if (express) {
            return EXPRESS;
        }
        return subtotal.compareTo(THRESHOLD) >= 0
                ? new BigDecimal("0.00")
                : STANDARD;
    }
}
```

**Ví dụ test giá trị thấp** (đây là phản ví dụ, không nên dùng để bảo vệ logic):

```java
package com.example.shipping;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ShippingFeeLowValueTest {
    @Test
    void returnsWhatTheMockWasToldToReturn() {
        ShippingFeeService service = mock(ShippingFeeService.class);
        BigDecimal subtotal = new BigDecimal("200.00");
        when(service.quote(subtotal, false))
                .thenReturn(new BigDecimal("0.00"));

        BigDecimal actual = service.quote(subtotal, false);

        assertThat(actual).isEqualByComparingTo(new BigDecimal("0.00"));
    }
}
```

Mọi logic trong `ShippingFeeService.quote` đều bị bỏ qua. Dù thay code thật để đơn 200.00 thu 15.00, test mock vẫn xanh. Assertion không hề chứng minh yêu cầu “từ 200.00 miễn phí”.

Thay bằng **test trực tiếp service thật** để kiểm tra các trường hợp có ý nghĩa.

**`src/test/java/com/example/shipping/ShippingFeeServiceTest.java`**

```java
package com.example.shipping;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ShippingFeeServiceTest {
    private final ShippingFeeService service = new ShippingFeeService();

    @ParameterizedTest
    @CsvSource({
        "0.00, false, 15.00",
        "199.99, false, 15.00",
        "200.00, false, 0.00",
        "200.01, false, 0.00",
        "100.00, true, 30.00",
        "500.00, true, 30.00"
    })
    void calculatesFeeAccordingToPolicy(
            String subtotal, boolean express, String expectedFee) {
        BigDecimal actual = service.quote(new BigDecimal(subtotal), express);

        assertThat(actual).isEqualByComparingTo(new BigDecimal(expectedFee));
        assertThat(actual.scale()).isEqualTo(2);
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThatThrownBy(() -> service.quote(new BigDecimal("-0.01"), false))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsNullSubtotal() {
        assertThatThrownBy(() -> service.quote(null, true))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

**Vì sao tốt hơn?** Test chạy logic thật, bao phủ giá trị biên 199.99/200.00/200.01, cả lựa chọn giao nhanh và đầu vào lỗi. Nếu lập trình viên nhầm điều kiện `>=` thành `>`, ca đúng ngưỡng sẽ bắt lỗi. Nếu chỉ thay cấu trúc `if` hoặc trích xuất helper nhưng kết quả không đổi, test vẫn đúng.

`@Service` không bắt buộc test phải có `@SpringBootTest`; ta có thể tạo trực tiếp đối tượng Java để kiểm thử thuật toán. `BigDecimal.compareTo` so sánh giá trị số, còn `isEqualByComparingTo` dùng đúng ngữ nghĩa ấy trong AssertJ. Assertion `scale()==2` chỉ phù hợp vì **quy tắc đầu bài đã yêu cầu** hai chữ số thập phân; không nên thêm nếu scale không phải hợp đồng.

Một lỗi ngược lại cũng phổ biến: test gián tiếp mọi method private bằng reflection hoặc `spy`. Thay vì cố đóng băng chi tiết chia method, hãy tổ chức bảng dữ liệu đầu vào–kết quả theo quy tắc sản phẩm, rồi chạy toàn bộ sau refactor.

## 5. Web slice bảo vệ HTTP contract, không trùng hoàn toàn với unit test

Unit test ở trên **không** chứng minh HTTP request được bind đúng, JSON được trả đúng hoặc lỗi được map thành 400. Một web test có thể bổ sung khả năng phát hiện hồi quy ở boundary.

**`src/main/java/com/example/shipping/ShippingController.java`**

```java
package com.example.shipping;

import java.math.BigDecimal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/shipping")
public class ShippingController {
    private final ShippingFeeService service;

    public ShippingController(ShippingFeeService service) {
        this.service = service;
    }

    @GetMapping
    public ShippingResponse quote(
            @RequestParam BigDecimal subtotal,
            @RequestParam(defaultValue = "false") boolean express) {
        return new ShippingResponse(service.quote(subtotal, express));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorResponse invalidSubtotal(IllegalArgumentException ignored) {
        return new ErrorResponse("INVALID_SUBTOTAL");
    }

    public record ShippingResponse(BigDecimal fee) {}
    public record ErrorResponse(String code) {}
}
```

**`src/test/java/com/example/shipping/ShippingControllerWebTest.java`**

```java
package com.example.shipping;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ShippingController.class)
@Import(ShippingFeeService.class)
class ShippingControllerWebTest {
    @Autowired
    MockMvc mvc;

    @Test
    void exposesFeeViaHttp() throws Exception {
        mvc.perform(get("/api/shipping")
                .param("subtotal", "200.00")
                .param("express", "false"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.fee").value(0.0));
    }

    @Test
    void rejectsNegativeSubtotalViaHttp() throws Exception {
        mvc.perform(get("/api/shipping")
                .param("subtotal", "-0.01"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_SUBTOTAL"));
    }

    @Test
    void rejectsNonNumericSubtotalViaHttp() throws Exception {
        mvc.perform(get("/api/shipping")
                .param("subtotal", "abc"))
            .andExpect(status().isBadRequest());
    }
}
```

`@WebMvcTest` chỉ tạo context cho MVC; `@Import` cung cấp service thật nhỏ. Các assertion bảo vệ status, trường JSON và lỗi HTTP. Đây là **contract khác** với unit test, dù cùng dùng `subtotal=200.00`.

Ví dụ giả định một dự án Spring Boot đã có `@SpringBootApplication` trong package gốc phù hợp, đã bật MVC, và không có ràng buộc Spring Security bổ sung. Nếu có security, cần cấu hình authentication/authorization trong test đúng với API thật; không nên xóa filter chỉ vì làm test khó chạy.

Một web test chỉ `verify(service).quote(...)` mà không kiểm tra HTTP response dễ trở thành test cấu trúc controller. Hãy kiểm tra đúng điều client thấy. Ngược lại, đừng snapshot nguyên response với những trường không thuộc hợp đồng; thêm một trường tương thích không nhất thiết là hồi quy.

## 6. Khi `verify` thật sự là một test có giá trị

Gọi dependency có thể là **tác dụng phụ được yêu cầu**. Ví dụ use case đăng ký cần yêu cầu gửi một email xác minh. Mock cổng email và kiểm tra thông điệp gửi đi là hợp lý vì hệ thống không cần gửi email thật trong unit test.

**Hai đoạn mã minh họa độc lập:**

```java
package com.example.shipping;

interface VerificationMailPort {
    void send(String email, String token);
}

final class RegistrationNotifier {
    private final VerificationMailPort mail;

    RegistrationNotifier(VerificationMailPort mail) {
        this.mail = mail;
    }

    void notifyUser(String email, String token) {
        mail.send(email, token);
    }
}
```

```java
package com.example.shipping;

import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class RegistrationNotifierTest {
    @Test
    void requestsVerificationEmail() {
        VerificationMailPort mail = mock(VerificationMailPort.class);
        RegistrationNotifier notifier = new RegistrationNotifier(mail);

        notifier.notifyUser("mai@example.com", "token-123");

        verify(mail).send("mai@example.com", "token-123");
    }
}
```

`verify(mail).send(...)` ở đây kiểm tra một **cổng ra**. Nếu phải chống gửi trùng theo yêu cầu, việc xác nhận `times(1)` có thể là assertion giá trị cao. Nếu chỉ verify `mapper.toDto` hoặc số lần gọi helper nội bộ, việc test có thể đỏ khi refactor dù hành vi người dùng không đổi.

Phân biệt mức bằng chứng: unit test trên chứng minh ứng dụng **yêu cầu gửi qua cổng**; nó chưa chứng minh nhà cung cấp email thật sự nhận và chuyển thư. Contract adapter, retry hoặc giao hàng thật cần test tích hợp riêng nếu những rủi ro đó quan trọng.

## 7. Flaky test làm tăng chi phí và làm giảm độ tin cậy

**Flaky** nghĩa là cùng mã nguồn và đầu vào nhưng có thể lúc xanh lúc đỏ. Điều này khiến nhóm thường xuyên rerun CI và dần không tin cả những lỗi thật.

Các nguồn flaky phổ biến:

| Nguồn không ổn định | Biểu hiện | Hướng sửa |
|---|---|---|
| `Thread.sleep(500)` chờ bất đồng bộ | Thỉnh thoảng timeout trên CI chậm | Chờ điều kiện/tín hiệu đã quan sát với deadline rõ |
| `Instant.now()` và múi giờ máy | Lỗi vào cuối ngày hoặc đúng thời điểm biên | Inject `Clock`, cố định thời điểm và timezone |
| Dữ liệu database dùng chung | Chạy song song bị xung đột id, thứ tự test ảnh hưởng kết quả | Fixture riêng, rollback/cleanup/isolation phù hợp |
| Gọi API công cộng | Mạng lỗi, rate limit, service ngừng hoạt động | Fake server hoặc test adapter có kiểm soát |
| Random không lưu seed | Không tái hiện được input gây lỗi | Seed cố định hoặc log seed cùng dữ liệu lỗi |
| Cấu hình/môi trường thay đổi | Context cache không ổn định, port collision | Cô lập cấu hình, port và tài nguyên theo test |

Đoạn sau kiểm tra thời hạn voucher mà không chờ đồng hồ:

**`src/main/java/com/example/shipping/VoucherWindow.java`**

```java
package com.example.shipping;

import java.time.Clock;
import java.time.Instant;

public final class VoucherWindow {
    private final Clock clock;

    public VoucherWindow(Clock clock) {
        this.clock = clock;
    }

    public boolean accepts(Instant expiresAt) {
        return Instant.now(clock).isBefore(expiresAt);
    }
}
```

**`src/test/java/com/example/shipping/VoucherWindowTest.java`**

```java
package com.example.shipping;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class VoucherWindowTest {
    @Test
    void checksBeforeAtAndAfterExpiry() {
        Instant now = Instant.parse("2026-06-01T12:00:00Z");
        Clock fixedClock = Clock.fixed(now, ZoneOffset.UTC);
        VoucherWindow policy = new VoucherWindow(fixedClock);

        assertThat(policy.accepts(now.minusSeconds(1))).isFalse();
        assertThat(policy.accepts(now)).isFalse();
        assertThat(policy.accepts(now.plusSeconds(1))).isTrue();
    }
}
```

Contract ở đây là: **voucher chỉ còn hợp lệ khi thời điểm hiện tại đứng trước thời điểm hết hạn**. Test kiểm tra ba điểm biên và không phụ thuộc giờ máy.

Với async, dùng `CountDownLatch`, acknowledgment hoặc chờ điều kiện có timeout rồi assert kết quả. Với cơ sở dữ liệu, kiểm soát transaction và cleanup. Một cơ chế retry CI có thể giảm gián đoạn nhất thời khi nguyên nhân đã hiểu, nhưng không nên trở thành giải pháp vĩnh viễn che khuất nondeterminism.

## 8. Chọn đúng cấp test để giảm chi phí không cần thiết

| Cấp | Mục tiêu phù hợp | Khi nào cấp này không đủ? |
|---|---|---|
| Unit (JUnit 5, AssertJ) | Tính toán, validation, quyết định nghiệp vụ, xử lý ngoại lệ thuần | Không chứng minh Spring MVC, JPA mapping, transaction thật |
| MVC slice (`@WebMvcTest`) | Route, binding, JSON, controller advice, security ở HTTP boundary | Không chứng minh end-to-end DB và nhiều bean ngoài slice |
| JPA slice (`@DataJpaTest`) | Query, entity mapping, constraint với database thích hợp | Không chứng minh API và luồng liên hệ nhiều service |
| Integration (`@SpringBootTest`) | Bean wiring, cấu hình, transaction, tích hợp adapter | Chậm nếu dùng cho mọi phép tính nhỏ |
| End-to-end | Hành trình hệ thống và liên kết hạ tầng quan trọng | Chi phí setup và chẩn đoán cao; không phù hợp bao hết nhánh logic |

**Mức tối thiểu đủ quan sát contract** là lựa chọn tốt. Giữ hàng loạt ca tính toán ở unit test nhanh; dùng slice để kiểm tra MVC/JPA; dùng integration có chủ đích cho giao dịch, cấu hình và tích hợp. Đừng thay persistence test bằng mock repository rồi kết luận SQL thật hoạt động.

Trong Spring Boot, có thể giảm chi phí thực thi bằng cách:

1. Giữ logic thuần tách khỏi I/O để test trực tiếp.
2. Dùng `@WebMvcTest`, `@DataJpaTest` khi chỉ cần slice.
3. Tận dụng caching `ApplicationContext` của Spring Test khi cấu hình tương đồng; dùng `@DirtiesContext` chỉ khi test thật sự thay đổi context làm nó không thể tái sử dụng.
4. Xây fixture nhỏ, có tên phản ánh nghiệp vụ; tránh dựng cả hệ thống dữ liệu cho một ca đơn giản.
5. Cô lập database, port, topic, trạng thái mutable và các dependency ngoài.
6. Giữ test tích hợp cần thiết cho rủi ro mà unit mock không thể phát hiện.

Hai test cùng dùng dữ liệu 200.00 chưa chắc trùng: unit test kiểm tra ngưỡng miễn phí, web test kiểm tra query binding và JSON, integration test kiểm tra lưu giao dịch. Hãy xét **loại lỗi mỗi test bắt được**, không chỉ độ giống nhau của input.

## 9. Đo kiểm chứng bằng CI và lịch sử thay đổi

Đừng đo “giá trị thấp” chỉ bằng số test, coverage hay runtime. Theo dõi tín hiệu:

| Quan sát | Dữ liệu có thể xem | Điều cần phân tích |
|---|---|---|
| Runtime từng test/nhóm | Gradle test report, JUnit XML, CI stage | Chậm do logic, context, database hay container? |
| Tần suất rerun/failure ngẫu nhiên | Kết quả CI theo commit và môi trường | Là bug sản phẩm, flaky hay hạ tầng? |
| Test phải sửa sau mỗi refactor | PR diff, commit history, nhận xét review | Test bám implementation hay contract có thay đổi? |
| Bug production lọt qua suite | Incident, bug report, regression | Contract quan trọng nào chưa được kiểm tra? |
| Mức dễ chẩn đoán | Stack trace, assertion message, fixture, log | Test fail có chỉ ra nguyên nhân hữu ích không? |
| Độc quyền bảo vệ rủi ro | Bản đồ test–contract–tầng kiểm thử | Xóa test này có tạo lỗ hổng không? |

`JaCoCo` hoặc các chỉ số coverage cho biết đường code đã đi qua; **không đảm bảo assert bắt sai hành vi**. Mutation testing như PIT cố tình thay biểu thức/nhánh để xem test có phát hiện biến thể sai không. Dùng như một công cụ chẩn đoán để phát hiện assertion yếu, không xem mutation score là thước đo đầy đủ về giá trị nghiệp vụ.

Ví dụ ma trận đánh giá minh họa:

| Test | Rủi ro được bảo vệ | Chi phí và tín hiệu | Quyết định gợi ý |
|---|---|---|---|
| Mock `ShippingFeeService` trả 0.00 rồi assert 0.00 | Không chạy business logic | Rất nhanh nhưng vô hiệu | **Thay** bằng unit test thực |
| `quotesFeeAtThreshold` | Tính sai đúng mức miễn phí | Nhanh, ổn định, có biên | **Giữ** |
| `shippingApiReturns400` | Sai hợp đồng HTTP | Slice vừa phải, tín hiệu rõ | **Giữ** |
| 8 `contextLoads` cùng context | Kiểm tra startup giống nhau | Dễ trùng, có chi phí context | **Rà soát và gộp** khi thực sự cùng contract |
| `orderPaymentRollsBackOnFailure` | Mất tính nguyên tử giao dịch | Chậm, nhưng hậu quả lỗi lớn | **Giữ**, tối ưu setup |
| Async test dựa vào `sleep` | Event hoàn tất | Flaky, chẩn đoán kém | **Viết lại** cách chờ và assert |

Một test “đắt” không tự động có giá trị thấp. Quyết định đúng phụ thuộc **mức độ nghiêm trọng của lỗi**, khả năng test bắt lỗi, mức bổ sung so với test khác và chi phí thật.

## 10. Quy trình xử lý test giá trị thấp

**Bước 1 — Lập bản đồ yêu cầu và rủi ro.** Với một module, liệt kê quy tắc nghiệp vụ, API contract, quyền, giao dịch, hiệu năng/atomicity đã cam kết, tích hợp quan trọng. Ghi lại test nào bảo vệ từng contract.

**Bước 2 — Đọc test cùng mục đích của nó.** Xác định Given/When/Then và assertion. Tự hỏi: “Thay code đúng thành sai thì test có fail không?” và “Thay code bằng refactor hợp lệ thì test có pass không?” Đừng xem tên test hoặc green status làm bằng chứng duy nhất.

**Bước 3 — Đo chi phí có nguyên nhân.** Đọc Gradle/CI report, lịch sử flaky, PR thường phải cập nhật test; phân biệt phí khởi động context, I/O, fixture, mock setup và chi phí điều tra. Không mặc định mọi test lâu đều vô ích.

**Bước 4 — Chọn một trong bốn hướng:**

- **Giữ** test bảo vệ hợp đồng quan trọng và cho tín hiệu đáng tin; nếu tốn chi phí, tối ưu hạ tầng/fixture.
- **Viết lại** test có ý tưởng đúng nhưng mock sai đối tượng, assert chi tiết nội bộ, phụ thuộc thời gian/mạng hoặc fixture cứng.
- **Gộp** test cùng tầng, cùng contract, cùng biến thể và không thêm khả năng bắt lỗi; giữ tên/parameterization thể hiện các trường hợp.
- **Xóa** test không bảo vệ hành vi đáng kể **sau khi** đã kiểm tra các contract còn được bảo vệ hoặc rủi ro được chấp nhận có chủ đích.

**Bước 5 — Xác minh sau thay đổi.** Chạy test liên quan và suite đủ rộng; so sánh thời gian, độ ổn định, chất lượng failure message. Đánh giá xem biến thể sai nghiệp vụ có bị test bắt và refactor hợp lệ có làm test đỏ vô cớ hay không.

Ví dụ, gộp nhiều case tính phí thành một `@ParameterizedTest` có thể tăng độ rõ và giảm trùng lặp. Nhưng không xóa web test trả 400 chỉ vì service test đã kiểm tra `IllegalArgumentException`: đó là hai contract khác nhau.

## 11. Cách chạy ví dụ và xem kết quả

Với dự án Spring Boot 3.x dùng Gradle và Java 17+, các ví dụ cần `spring-boot-starter-web` cho controller và `spring-boot-starter-test` cho JUnit 5, AssertJ, Mockito và MockMvc. Nếu module đã khai báo các dependency này thì không thêm bản sao.

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đặt file đúng package và thư mục như ví dụ. Chạy trên môi trường có Gradle wrapper và cấu hình Spring Boot hợp lệ:

```bash
./gradlew test --tests com.example.shipping.ShippingFeeServiceTest --tests com.example.shipping.ShippingControllerWebTest --tests com.example.shipping.RegistrationNotifierTest --tests com.example.shipping.VoucherWindowTest
```

Trên Windows, dùng `.\gradlew.bat`. Với multi-project, thay `test` bằng task của module, chẳng hạn `:some-module:test` khi project thật có module đó. Báo cáo test mặc định thường nằm ở `build/reports/tests/test/index.html` và `build/test-results/test/` trong build directory tương ứng.

Các test ví dụ được thiết kế để pass nếu đã đặt đủ file, Spring Boot bootstrap có thể được tìm thấy từ package test, và không có security configuration bổ sung chặn request. Khi mọi test pass, Gradle dự kiến in `BUILD SUCCESSFUL`. Đây là **kết quả mong đợi theo mã ví dụ**, không phải khẳng định đã chạy trong một repository cụ thể. JUnit test không có stdout ứng dụng cố định.

Lệnh chỉ định `--tests` kiểm tra **những class được chọn**; để xác minh toàn bộ module cần chạy suite đầy đủ. Sau khi viết lại/gộp test, so sánh dữ liệu CI ở điều kiện tương đương, chú ý chất lượng chẩn đoán khi test fail.

## 12. Sai lầm thường gặp

**“Càng nhiều test càng an toàn.”** Số lượng không nói lên contract nào được bảo vệ. Một bảng test biên có assertion rõ có thể tốt hơn nhiều test lặp cùng input.

**“Test pass nghĩa là logic đúng.”** Một test của mock có thể pass khi logic thật lỗi nặng. Cần xác định đối tượng thật có được chạy và kết quả quan trọng có được kiểm chứng không.

**“Refactor làm test đỏ thì refactor sai.”** Có thể test chỉ phụ thuộc helper hoặc snapshot ngoài hợp đồng. Phải xác minh contract trước khi kết luận. Nếu contract thật sự đổi, test đỏ là đúng.

**“100% coverage là đủ.”** Coverage đo dòng chạy, không đo chất lượng assertion hay khả năng phát hiện lỗi. Điểm biên, error path và side effect phải được lựa chọn theo rủi ro.

**“Test chậm là test không đáng giữ.”** Test rollback, authorization hay tích hợp thanh toán có thể chậm nhưng rất có giá trị. Hãy tối ưu setup hoặc cấp test, không hạ yêu cầu.

**“Xóa flaky test để CI xanh.”** Một flaky test có thể bảo vệ chức năng quan trọng. Sửa nguồn nondeterminism; retry vô điều kiện có thể che lỗi thật.

**“Dùng `@SpringBootTest` cho tất cả để giống production.”** Unit test tính toán thuần không cần context. Ngược lại, dùng mock để thay mọi persistence/transaction test sẽ không chứng minh hành vi tích hợp thật.

## 13. Bài tập và checklist

Tình huống: đội phát triển đổi `ShippingFeeService` từ `if` sang chiến lược `FeePolicy`. Với các subtotal `199.99`, `200.00` và giao nhanh, kết quả vẫn như cũ. API vẫn trả `{"fee":0.00}` ở đơn đủ ngưỡng và HTTP 400 cho số âm.

1. Test nào **phải giữ xanh**? Unit test giá trị biên và test HTTP contract.
2. Test nào có thể **đỏ vô ích**? Test `verify` helper cũ, method mapper hoặc thứ tự bước nội bộ.
3. Nếu code mới thu 15.00 tại đúng 200.00, test nào bắt lỗi? Unit test ở ngưỡng (và tầng khác nếu có case đó).
4. Nếu API đổi 400 thành 500 cho đầu vào âm, test nào bắt lỗi? Web slice test.
5. Nếu một test transaction chậm nhưng phát hiện mất dữ liệu sau thanh toán thất bại, có nên xóa chỉ vì runtime? Không; cần giữ lớp bảo vệ và tối ưu cách chạy nếu phù hợp.

Checklist trước khi chấp nhận một bài test:

- [ ] Nêu rõ hợp đồng hoặc rủi ro mà test bảo vệ.
- [ ] Assertion xác nhận đầu ra, lỗi, thay đổi trạng thái hoặc side effect thật.
- [ ] Test sẽ fail khi hành vi quan trọng sai, thay vì chỉ fail khi đổi cấu trúc.
- [ ] Không mock chính logic cần kiểm tra; mock dependency ở ranh giới hợp lý.
- [ ] Không cố định private helper, số lần gọi mapper hoặc log ngoài contract.
- [ ] Có trường hợp biên và nhánh lỗi cần thiết; tránh trùng ý nghĩa với test đã có.
- [ ] Chọn đúng cấp unit/slice/integration/e2e.
- [ ] Dữ liệu, clock, mạng và trạng thái dùng chung được kiểm soát.
- [ ] Runtime, flakiness và công điều tra failure tương xứng với rủi ro được bảo vệ.
- [ ] Khi sửa/gộp/xóa test, bộ test còn lại vẫn bảo vệ các contract quan trọng.

**Ghi nhớ:** Giá trị của kiểm thử nằm ở **hồi quy quan trọng mà nó phát hiện được, nhanh và đáng tin đến đâu**, chứ không nằm ở số test hoặc độ phức tạp của fixture. Ưu tiên test hành vi có ý nghĩa, chịu được refactor, và chọn đúng tầng Spring Boot để duy trì một suite hữu ích lâu dài.