# JUnit assertions và nhóm nhiều điều kiện kiểm chứng

Một bài kiểm thử không trở nên có ích chỉ vì phương thức được gọi mà không ném lỗi. **Assertion** là điểm mà test diễn đạt chính xác điều gì phải đúng: kết quả, lỗi, cấu trúc dữ liệu hay tác dụng phụ mà người gọi được quyền kỳ vọng. Trong ứng dụng Spring Boot, biết chọn assertion và nhóm các kiểm chứng liên quan giúp test báo sai lệch rõ ràng, giảm thời gian tìm nguyên nhân, đồng thời tránh ràng buộc quá mức vào chi tiết triển khai.

JUnit Jupiter (JUnit 5) cung cấp các assertion trong `org.junit.jupiter.api.Assertions` như `assertEquals`, `assertTrue`, `assertThrows` và đặc biệt `assertAll` để kiểm tra **nhiều điều kiện độc lập trong cùng một tình huống**. Bài này giải thích cách chọn assertion, hành vi khi assertion thất bại, cách nhóm điều kiện, xử lý exception, dữ liệu collection và tình huống web test trong Spring Boot.

**Sau bài học, bạn có thể:**

- Viết Given–When–Then với assertion có chủ đích, phân biệt giá trị và danh tính object.
- Dùng assertion đúng cho số, chuỗi, collection, array, ngoại lệ và kết quả không ném lỗi.
- Hiểu `assertAll` chạy các `Executable` và tổng hợp nhiều lỗi, khác với các `assertEquals` gọi liên tiếp.
- Nhóm assertion liên quan theo hành vi mà không biến test thành một kịch bản khó chẩn đoán.
- Áp dụng JUnit 5 và Spring MVC `MockMvc` để kiểm tra các thuộc tính của kết quả.
- Nhận biết lỗi thường gặp: expected/actual bị đảo, so sánh `BigDecimal` sai ý nghĩa, dùng `assertTrue` mơ hồ, quá nhiều chi tiết phụ, phụ thuộc thời gian và assertion chỉ xác minh mock.

## 1. Assertion nằm ở đâu trong một test?

Một test rõ ràng thường theo ba bước:

1. **Given (Arrange):** Tạo dữ liệu và trạng thái ban đầu phù hợp với một yêu cầu cụ thể.
2. **When (Act):** Thực thi hành động hoặc lời gọi public cần kiểm tra.
3. **Then (Assert):** Kiểm tra đầu ra, ngoại lệ, trạng thái được thay đổi hoặc tương tác với cổng ra nếu đó là kết quả đã cam kết.

Ví dụ yêu cầu: “Khi đăng ký tên có khoảng trắng hai đầu, hệ thống bỏ khoảng trắng, kích hoạt hồ sơ và gán vai trò USER”. Một bài test tốt gọi hành vi đăng ký thật rồi kiểm tra **tên, trạng thái, vai trò**. Việc controller gọi một helper tên `normalizeName` hay service sử dụng `String.strip` không phải là hợp đồng công khai, trừ khi yêu cầu riêng quy định cách xử lý đó.

**Assertion thất bại** sẽ báo lỗi test (thường là `AssertionFailedError` hoặc dạng lỗi assertion tổng hợp). **Ngoại lệ không mong đợi** trong hành động cũng khiến test thất bại, kể cả khi không có assertion phía sau. Vì vậy cần xác nhận hành vi có ý nghĩa, không viết các kiểm tra thừa chỉ để có thật nhiều assertion.

Ví dụ khung minh họa:

```java
// Khung minh họa: data/action là các giá trị được chuẩn bị trong test cụ thể.
var result = service.perform(action);       // When
assertEquals(expected, result.value());      // Then
```

Đây là đoạn minh họa, không phải chương trình biên dịch độc lập. Các ví dụ đầy đủ ở phần sau khai báo lớp và kiểu dữ liệu thật.

## 2. Những assertion JUnit Jupiter thường dùng

Hầu hết test import tĩnh từ `org.junit.jupiter.api.Assertions`:

```java
import static org.junit.jupiter.api.Assertions.*;
```

Với code production, nên import rõ những assertion được dùng để người đọc dễ thấy phụ thuộc, nhưng import wildcard vẫn hợp lệ trong ví dụ học tập.

| Assertion | Ý nghĩa | Lưu ý |
|---|---|---|
| `assertEquals(expected, actual)` | Hai giá trị bằng nhau theo ngữ nghĩa `equals`/overload tương ứng | Tham số **expected trước, actual sau**; chú ý `BigDecimal` và số thực |
| `assertNotEquals(unexpected, actual)` | Hai giá trị khác nhau | Khác nhau không bảo đảm giá trị đúng mong đợi |
| `assertTrue(condition)`, `assertFalse(condition)` | Điều kiện boolean đúng hoặc sai | Ưu tiên assertion chuyên biệt nếu nó cho thông báo rõ hơn |
| `assertNull(value)`, `assertNotNull(value)` | Kiểm tra null | Chỉ `not null` thường chưa đủ để bảo vệ một kết quả nghiệp vụ |
| `assertSame(expected, actual)` | Cùng một tham chiếu object | Không tương đương `equals`; chỉ dùng khi identity thuộc hợp đồng |
| `assertNotSame(unexpected, actual)` | Không phải cùng tham chiếu | Hai object khác instance vẫn có thể bằng nhau về giá trị |
| `assertArrayEquals(expected, actual)` | So sánh nội dung array, kể cả array nguyên thủy | `assertEquals` trên array thường kiểm tra tham chiếu |
| `assertIterableEquals(expected, actual)` | So sánh các phần tử của Iterable theo thứ tự | Nếu yêu cầu không quy định thứ tự, chọn cách kiểm tra không phụ thuộc thứ tự |
| `assertLinesMatch(expectedLines, actualLines)` | So sánh dòng với hỗ trợ pattern theo quy tắc JUnit | Dành cho output nhiều dòng có cấu trúc |
| `assertInstanceOf(Type.class, value)` | Kiểm tra kiểu runtime và trả về giá trị đã cast | Chỉ khóa kiểu cụ thể khi kiểu là phần contract |
| `assertThrows(Type.class, executable)` | Hành động phải ném loại lỗi được chỉ định hoặc subclass | Kết quả trả về là exception để kiểm chứng thêm nếu cần |
| `assertThrowsExactly(Type.class, executable)` | Phải ném **chính xác** loại lỗi đó | Chặt hơn; cân nhắc có cần từ chối subclass không |
| `assertDoesNotThrow(executable)` | Hành động không được ném lỗi | Thường nên assert luôn kết quả nghiệp vụ nếu có |
| `assertAll(heading, executable...)` | Kiểm tra các điều kiện và tổng hợp nhiều lỗi | Không dùng để bỏ qua lỗi; nhóm các điều kiện cùng hành vi |
| `assertTimeout(duration, executable)` | Thời gian hoàn tất không vượt thời lượng quy định | Không ngắt tác vụ khi quá thời hạn; dễ phụ thuộc tốc độ CI |

Các overload còn cho truyền **thông báo lỗi** dạng chuỗi hoặc `Supplier<String>`. Supplier chỉ được gọi khi assertion cần tạo thông điệp, tránh chi phí dựng chuỗi trên đường test thành công.

Ví dụ với thông báo rõ phạm vi:

```java
assertEquals("Linh", profile.displayName(),
        () -> "Tên đã chuẩn hóa phải là Linh");
```

Nếu test sai, báo cáo chỉ đúng trường không khớp. Tránh message chung chung như `"test failed"` vì không giúp tìm nguyên nhân.

## 3. Vì sao nhiều assertion liên tiếp có thể che mất các lỗi khác?

Xét một hồ sơ đăng ký có ba điều kiện: tên được chuẩn hóa, trạng thái hoạt động, vai trò USER. Viết các assertion liên tiếp là hợp lệ:

```java
assertEquals("Linh", profile.displayName());
assertTrue(profile.enabled());
assertIterableEquals(List.of("USER"), profile.roles());
```

Nhưng nếu câu đầu sai, JUnit dừng phương thức test tại đó; hai câu tiếp theo **chưa được chạy**. Sau khi sửa lỗi tên, lần chạy tiếp theo có thể lộ ra lỗi trạng thái hoặc vai trò. Trong một đối tượng kết quả có nhiều thuộc tính liên quan, cách này làm vòng lặp sửa lỗi kéo dài.

`assertAll` giải quyết chính vấn đề đó:

```java
assertAll("hồ sơ sau đăng ký",
        () -> assertEquals("Linh", profile.displayName()),
        () -> assertTrue(profile.enabled()),
        () -> assertIterableEquals(List.of("USER"), profile.roles()));
```

JUnit thực thi các lambda `Executable` được đưa vào, **thu thập các assertion thất bại** và báo thành một lỗi tổng hợp khi có nhiều failure. Các lambda còn lại vẫn có cơ hội được kiểm tra ngay cả khi một điều kiện trước đó sai. Báo cáo thường chứa tên nhóm và từng failure; định dạng chi tiết tùy phiên bản JUnit/IDE.

**Điều cần hiểu chính xác:**

- `assertAll` không tự đoán field nào phải kiểm tra; bạn vẫn phải viết từng assertion có ý nghĩa.
- Nó không thay đổi logic nghiệp vụ hay biến một test sai thành pass. Nếu một hoặc nhiều kiểm chứng fail, toàn bộ test fail.
- Các lambda nên độc lập và **chỉ đọc kết quả đã tạo**. Đừng để lambda thứ nhất sửa dữ liệu mà lambda thứ hai cần.
- Nếu hành động chính `service.register(...)` ném exception **trước** lời gọi `assertAll`, việc nhóm assertion không diễn ra; exception vẫn làm test fail. Đó là đúng nếu success path kỳ vọng không ném lỗi.
- Trong một số lỗi nghiêm trọng không thể tiếp tục (ví dụ dạng lỗi JVM không thể phục hồi), không nên giả định mọi lambda nhất thiết sẽ hoàn tất; `assertAll` chủ yếu dành cho lỗi assertion bình thường.
- Không gộp tất cả test của một module vào một `assertAll` khổng lồ. Một test nên diễn đạt một hành vi/tình huống; nhóm các thuộc tính liên quan của **cùng kết quả**.

## 4. Ví dụ Java 17+ đầy đủ: service đăng ký hồ sơ

Giả sử module Spring Boot 3.x dùng Java 17+, có `spring-boot-starter-web` và `spring-boot-starter-test`. Tình huống:

- Tên được loại bỏ khoảng trắng ở hai đầu.
- Đăng ký thành công tạo hồ sơ có `enabled=true`.
- Người dùng thường có vai trò `USER`; quản trị viên có `USER` và `ADMIN` theo thứ tự đó.
- Tên `null`, rỗng hoặc chỉ có whitespace bị từ chối bằng `IllegalArgumentException`.

Đặt file **`src/main/java/com/example/assertions/ProfileService.java`**:

```java
package com.example.assertions;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    public Profile register(String name, boolean admin) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        String normalized = name.strip();
        List<String> roles = admin
                ? List.of("USER", "ADMIN")
                : List.of("USER");

        return new Profile(normalized, true, roles);
    }

    public record Profile(
            String displayName,
            boolean enabled,
            List<String> roles) {
    }
}
```

`record` tạo các accessor `displayName()`, `enabled()`, `roles()`; không cần dùng getter kiểu `getDisplayName()`. `String.strip` và `String.isBlank` có trong Java 11+, nên Java 17 chạy được. `List.of` trả danh sách immutable; đây là lựa chọn đơn giản cho ví dụ, không phải yêu cầu chung của mọi ứng dụng.

Đặt file test **`src/test/java/com/example/assertions/ProfileServiceTest.java`**:

```java
package com.example.assertions;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProfileServiceTest {
    private final ProfileService service = new ProfileService();

    @Test
    void registersNormalUserWithExpectedState() {
        ProfileService.Profile profile =
                service.register("  Linh  ", false);

        assertAll("hồ sơ người dùng thường",
                () -> assertEquals("Linh", profile.displayName()),
                () -> assertTrue(profile.enabled()),
                () -> assertIterableEquals(
                        List.of("USER"), profile.roles()));
    }

    @Test
    void registersAdminWithBothRoles() {
        ProfileService.Profile profile =
                service.register("An", true);

        assertAll("hồ sơ quản trị",
                () -> assertEquals("An", profile.displayName()),
                () -> assertAll("quyền và trạng thái",
                        () -> assertTrue(profile.enabled()),
                        () -> assertFalse(profile.roles().isEmpty())),
                () -> assertIterableEquals(
                        List.of("USER", "ADMIN"), profile.roles()));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "  \t  "})
    void rejectsBlankNames(String invalidName) {
        assertThrows(IllegalArgumentException.class,
                () -> service.register(invalidName, false));
    }
}
```

**Đọc kết quả từng test:**

- `registersNormalUserWithExpectedState` kiểm tra ba điều kiện của cùng hành vi đăng ký; nếu tên và roles cùng sai, `assertAll` có thể cho thấy cả hai ở một lần chạy.
- `registersAdminWithBothRoles` minh họa **assertAll lồng nhau**. Nhóm `quyền và trạng thái` chứa hai assertion; nhóm ngoài vẫn bao quát tất cả thuộc tính của kết quả.
- `rejectsBlankNames` dùng `@ParameterizedTest` cùng `@NullAndEmptySource` và `@ValueSource` để kiểm tra các dạng đầu vào không hợp lệ. Mỗi input tạo một lần chạy tham số riêng. `assertThrows` chứng minh service thật ném lỗi như cam kết.
- Vì chỉ kiểm tra logic thuần, các unit test này **không cần `@SpringBootTest`**. Spring annotation `@Service` cho runtime không làm thay đổi khả năng test trực tiếp bằng `new`.

Chú ý `@NullAndEmptySource` cung cấp `null` và chuỗi rỗng; `@ValueSource` bổ sung chuỗi chứa dấu cách/tab. `String.isBlank` nhận biết các trường hợp này. Nếu thông báo exception không thuộc contract, **không nên assert nguyên văn** `"name must not be blank"`, vì thay wording không nên phá test. Nếu API công khai mã lỗi hoặc message cố định, hãy kiểm tra đúng mã/message đó ở boundary thích hợp.

## 5. Vì sao `assertAll` tốt hơn một `assertTrue` chứa nhiều biểu thức?

Một kiểu test khó chẩn đoán:

```java
// Phản ví dụ: nếu thất bại, rất khó biết field nào sai.
assertTrue(profile.enabled()
        && profile.displayName().equals("Linh")
        && profile.roles().contains("USER"));
```

Vì ba điều kiện bị gộp thành một boolean, báo cáo chỉ biết `false`. Với `assertAll` và assertion chuyên biệt:

```java
assertAll("registered profile",
        () -> assertTrue(profile.enabled()),
        () -> assertEquals("Linh", profile.displayName()),
        () -> assertTrue(profile.roles().contains("USER"),
                "Hồ sơ phải có quyền USER"));
```

Mỗi sai lệch có ngữ cảnh. Đặc biệt, `assertEquals` thường hiển thị giá trị **expected** và **actual**; `assertTrue` chỉ có boolean nên cần message để chỉ ra điều được mong đợi. Nếu danh sách vai trò phải đúng toàn phần và thứ tự là contract, `assertIterableEquals` còn diễn đạt chính xác hơn phép `contains`.

Nhưng đừng lạm dụng assertAll để luôn có nhiều assert: nếu một test chỉ cần khẳng định HTTP trả `403`, một assertion về status là đủ. **Nhiều assertion chỉ có ý nghĩa khi mỗi assertion bảo vệ một thuộc tính thực sự cần kiểm tra.**

## 6. Cách đọc lỗi tổng hợp và lựa chọn nhóm

Giả sử **chỉ để minh họa một lần thất bại**, dữ liệu thực là tên “Linh”, `enabled=true`, nhưng test lại mong “An” và `enabled=false`:

```java
// Phản ví dụ cố ý fail; KHÔNG thêm vào suite xanh ở mục 4.
assertAll("hồ sơ sau đăng ký",
        () -> assertEquals("An", profile.displayName()),
        () -> assertFalse(profile.enabled()),
        () -> assertIterableEquals(List.of("USER"), profile.roles()));
```

JUnit có thể báo một `MultipleFailuresError` chứa hai sai lệch: tên mong “An” nhưng nhận “Linh”, và trạng thái mong false nhưng nhận true. Điều kiện vai trò vẫn được thực thi; nếu đúng thì không có failure cho vai trò. Thông báo cụ thể và stack trace phụ thuộc phiên bản JUnit và IDE, nên không nên viết test phụ thuộc chính chuỗi trình bày của `MultipleFailuresError`.

**Nhóm theo ý nghĩa nghiệp vụ, không theo số dòng code.** Chẳng hạn, kiểm tra thông tin đơn hàng:

```java
// Minh họa: order và receipt là kết quả đã được tạo ở bước When.
assertAll("đơn hàng được xác nhận",
        () -> assertAll("thông tin đơn hàng",
                () -> assertEquals("CONFIRMED", order.status()),
                () -> assertEquals(2, order.lines().size())),
        () -> assertAll("biên nhận",
                () -> assertEquals("VND", receipt.currency()),
                () -> assertTrue(receipt.total().signum() >= 0)));
```

Đây là **đoạn minh họa**, không phải file Java độc lập: các kiểu `order` và `receipt` không được định nghĩa ở ví dụ này. Ưu điểm của nested group là báo cáo lỗi theo ngữ cảnh. Nếu nội dung thuộc hai chức năng độc lập (ví dụ đăng ký và xóa tài khoản), nên viết **hai test** để mỗi test có nguyên nhân và fixture riêng.

Trong trường hợp test yêu cầu thao tác thay đổi trạng thái theo bước, đừng cố cho mọi bước nằm trong một `assertAll`: việc kiểm chứng sau từng thao tác có thể cần fail sớm để không làm hỏng dữ liệu đầu vào của bước tiếp theo. `assertAll` có ích nhất với nhiều điều kiện **độc lập trên cùng kết quả**.

## 7. `assertThrows`, `assertThrowsExactly` và `assertDoesNotThrow`

Kiểm thử hành vi lỗi cũng là kiểm thử contract. `assertThrows` nhận loại exception kỳ vọng và lambda chứa hành động phải ném lỗi:

```java
IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.register("  ", false));
```

Hàm trả về **chính exception bắt được**. Sau đó chỉ assert thêm code/message/thuộc tính của nó nếu những chi tiết ấy thực sự được quy định.

Phân biệt:

- `assertThrows(RuntimeException.class, executable)` **chấp nhận** `RuntimeException` và mọi subclass phù hợp.
- `assertThrowsExactly(RuntimeException.class, executable)` chỉ chấp nhận **đúng lớp RuntimeException**; nếu code ném `IllegalArgumentException` thì assertion thứ hai fail.
- `assertDoesNotThrow(() -> operation())` xác nhận hành động không ném exception, và với overload trả giá trị có thể nhận lại kết quả.

Ví dụ sử dụng đúng với service:

```java
ProfileService.Profile result = assertDoesNotThrow(
        () -> service.register("Mai", false));
assertEquals("Mai", result.displayName());
```

Tuy nhiên, một test đã gọi `register` rồi assert đầu ra sẽ tự fail nếu exception không mong đợi xảy ra. `assertDoesNotThrow` hữu ích khi “không ném exception” là điều cần nhấn mạnh, hoặc muốn bọc một đoạn thực thi có thông báo lỗi riêng. Đừng dùng nó để thay thế tất cả assertion về đầu ra.

**Lỗi thường gặp:** đặt `assertThrows` quanh method khác với hành động muốn test, hoặc gọi method trước khi vào lambda. Phải truyền:

```java
assertThrows(IllegalArgumentException.class,
        () -> service.register("", false));
```

Không được gọi `service.register("", false)` trước rồi mới truyền kết quả vào assertion; exception sẽ thoát ra trước khi JUnit có thể kiểm tra loại lỗi.

## 8. So sánh collection, array, object identity và tiền tệ

Các assertion trông gần giống nhau nhưng mang ngữ nghĩa khác:

### 8.1. So sánh array và list

```java
int[] expected = {1, 2, 3};
int[] actual = {1, 2, 3};
assertArrayEquals(expected, actual);

List<String> roles = List.of("USER", "ADMIN");
assertIterableEquals(List.of("USER", "ADMIN"), roles);
```

`assertArrayEquals` kiểm tra nội dung array; `assertEquals` với hai array riêng biệt thường kiểm tra identity do array Java không override `equals`. Với `Iterable`, `assertIterableEquals` so sánh các phần tử tương ứng theo thứ tự.

Nếu business chỉ yêu cầu hai vai trò tồn tại mà **không quy định thứ tự**, assert nguyên thứ tự có thể tạo test dễ vỡ. Khi đó có thể dùng cách so sánh dạng set:

```java
assertEquals(Set.of("USER", "ADMIN"), Set.copyOf(profile.roles()));
```

Ví dụ trên yêu cầu `import java.util.Set;` nếu đặt trong file Java riêng. Hãy cân nhắc phần tử trùng lặp: chuyển sang `Set` loại bỏ duplicates, nên cách này **không thể** phát hiện role bị lặp. Nếu không cho phép trùng, assert thêm kích thước hoặc dùng phép so sánh multiset phù hợp.

### 8.2. So sánh object value và identity

```java
String first = new String("hi");
String second = new String("hi");

assertEquals(first, second);   // Giá trị chuỗi giống nhau
assertNotSame(first, second);  // Hai object riêng biệt
```

`assertSame` phù hợp khi cùng object là một phần yêu cầu, chẳng hạn cache bắt buộc trả cùng instance; bình thường, test nội dung/value là quan trọng hơn. Tránh test singleton/identity khi sản phẩm chỉ cam kết giá trị.

### 8.3. So sánh `BigDecimal` và số thực

`BigDecimal.equals` tính cả **scale**:

```java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

assertNotEquals(a, b);         // equals khác vì scale 1 và 2
assertEquals(0, a.compareTo(b)); // Giá trị số bằng nhau
```

Trong ví dụ này cần `import java.math.BigDecimal;`. Nếu scale không thuộc hợp đồng, dùng `compareTo` hoặc AssertJ `isEqualByComparingTo`; nếu phải giữ đúng hai chữ số thập phân, nên assert cả scale.

Với phép tính số thực `double`, đừng cố so bằng chính xác khi thuật toán có sai số làm tròn:

```java
assertEquals(0.3, 0.1 + 0.2, 0.0000001);
```

`delta` là dung sai được chọn theo yêu cầu; không tùy tiện chọn rất lớn khiến test bỏ qua sai lệch có ý nghĩa. Với tính tiền nghiệp vụ, thường dùng `BigDecimal` và quy tắc làm tròn rõ ràng, thay vì dựa vào `double`.

## 9. Nhóm assertion trong kiểm thử HTTP của Spring Boot

Kết quả HTTP có nhiều điều kiện cùng có ý nghĩa: status, content type, JSON field và mã lỗi. Trong Spring MVC, `MockMvc` cung cấp `andExpect` cho từng `ResultMatcher`, và `andExpectAll` để tổng hợp các kiểm chứng. **`andExpectAll` của MockMvc không phải `Assertions.assertAll`**, nhưng cả hai phục vụ việc báo nhiều sai lệch trong một kết quả.

Để thử end-to-end ở tầng MVC, đặt file **`src/main/java/com/example/assertions/ProfileController.java`**:

```java
package com.example.assertions;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {
    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @PostMapping
    public ProfileService.Profile register(
            @RequestParam String name,
            @RequestParam(defaultValue = "false") boolean admin) {
        return service.register(name, admin);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorResponse invalidName(IllegalArgumentException ignored) {
        return new ErrorResponse("INVALID_NAME");
    }

    public record ErrorResponse(String code) {
    }
}
```

Đặt file **`src/test/java/com/example/assertions/ProfileControllerWebTest.java`**:

```java
package com.example.assertions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
@Import(ProfileService.class)
class ProfileControllerWebTest {
    @Autowired
    MockMvc mvc;

    @Test
    void registrationReturnsExpectedHttpContract() throws Exception {
        mvc.perform(post("/api/profiles")
                .param("name", "  Linh  ")
                .param("admin", "true"))
            .andExpectAll(
                status().isOk(),
                content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                jsonPath("$.displayName").value("Linh"),
                jsonPath("$.enabled").value(true),
                jsonPath("$.roles[0]").value("USER"),
                jsonPath("$.roles[1]").value("ADMIN"));
    }

    @Test
    void invalidNameReturnsPublicErrorCode() throws Exception {
        mvc.perform(post("/api/profiles")
                .param("name", "   "))
            .andExpectAll(
                status().isBadRequest(),
                jsonPath("$.code").value("INVALID_NAME"));
    }
}
```

Ở đây:

- `@WebMvcTest(ProfileController.class)` tạo context chứa phần MVC cần cho controller, thay vì khởi động tất cả thành phần ứng dụng.
- `@Import(ProfileService.class)` đưa service thật, đơn giản vào slice; không cần mock logic đang cần bảo vệ.
- `andExpectAll` kiểm tra các thuộc tính HTTP được công bố; nếu nhiều matcher sai, kết quả kiểm thử có thể hiển thị nhiều thất bại.
- `@ExceptionHandler` trong ví dụ chuyển lỗi nghiệp vụ thành HTTP 400; Spring không tự biến **mọi** `IllegalArgumentException` của service thành response 400 nếu không có cơ chế mapping phù hợp.
- Response của method `@PostMapping` mặc định là HTTP 200 vì ví dụ chưa cấu hình `@ResponseStatus(CREATED)`. Nếu API thiết kế trả 201, cần sửa contract và controller/test tương ứng.

**Điều kiện để chạy:** module có lớp `@SpringBootApplication` được Spring Boot test tìm thấy theo cấu trúc package thông thường và các dependency đã khai báo; nếu bật Spring Security, cần cấu hình mock principal/CSRF và quyền theo hợp đồng thực tế. Không vô hiệu hóa security chỉ để đạt xanh. Trong ứng dụng có Spring Security, request POST có thể bị từ chối nếu thiếu CSRF token; đó là vấn đề cấu hình test security, không phải lỗi của `assertAll`.

Cũng cần phân biệt web slice test với integration test: `@WebMvcTest` có thể xác nhận mapping và JSON, nhưng không chứng minh persistence/transaction của toàn bộ ứng dụng. Khi muốn kiểm tra dữ liệu lưu thật, cần chọn cấp kiểm thử phù hợp.

## 10. `assertAll` không có nghĩa “càng nhiều kiểm chứng càng tốt”

Có hai mặt của việc nhóm assertion.

**Tốt:** Kiểm tra nhiều thuộc tính **cùng một đối tượng kết quả** hoặc một response: tên, trạng thái, vai trò; status, content type, mã lỗi. Mỗi assertion tương đối độc lập, thông điệp sai lệch rõ.

**Dễ gây vấn đề:** Đặt nhiều hành động thay đổi trạng thái bên trong các lambda như tạo đơn, thanh toán, hủy đơn rồi đọc kết quả. Nếu thanh toán fail, lambda hủy đơn vẫn chạy trong `assertAll` và có thể làm trạng thái khó hiểu hoặc tạo tác dụng phụ. Với nhiều hành động phụ thuộc nhau, chia thành test tương ứng, hoặc cho phép fail sớm tại bước tiền điều kiện quan trọng.

Ví dụ **nên tránh**:

```java
// Phản ví dụ: nhiều thao tác có side effect trong một nhóm assertion.
assertAll("toàn bộ quy trình",
        () -> assertTrue(paymentService.charge(order)),
        () -> assertTrue(shippingService.dispatch(order)),
        () -> assertTrue(refundService.refund(order)));
```

Đây là **mã minh họa không độc lập**; các biến `order`, `paymentService`, `shippingService`, `refundService` chưa được khai báo. Ngoài ra, logic “thu tiền, giao hàng rồi hoàn tiền” không phải một kịch bản thử nghiệm tốt nếu nghiệp vụ không yêu cầu như vậy.

**Cách tốt hơn:** setup và act một lần, lấy kết quả, rồi nhóm điều kiện **chỉ đọc**; khi cần nhiều hành động theo thứ tự, phân chia test hoặc kiểm tra tiền điều kiện trước. Kết quả của test phải dễ hiểu khi nó thất bại.

Một số quan sát thực dụng:

- Một test có **một mục tiêu hành vi** có thể có nhiều assertions.
- Không bắt buộc một test chỉ có đúng một assertion.
- Nếu nhóm assertion có 20–30 thuộc tính không liên quan, test có thể đang ôm quá nhiều contract.
- Nếu group chứa các assertion lặp cùng ý nghĩa, hãy xóa phần thừa.
- Nếu test cần truy cập private field hoặc kiểm tra helper để có thêm assertion, hãy xem liệu đó có thực sự là yêu cầu hay không.

## 11. Những lỗi phổ biến khi viết assertion

### 11.1. Đảo `expected` và `actual`

```java
assertEquals("Linh", profile.displayName()); // Đúng: expected trước
```

Khi đảo thứ tự, test vẫn có thể bắt lỗi, nhưng báo cáo IDE cho expected/actual ngược, khiến chẩn đoán khó hiểu.

### 11.2. Assertion quá chung chung

```java
assertNotNull(profile); // Chưa chứng minh tên, trạng thái hay roles.
```

Nếu contract yêu cầu đầy đủ thuộc tính, assert thêm từng phần có ý nghĩa. Với giá trị được tạo có ý nghĩa mặc định, chỉ not-null có thể bỏ sót bug lớn.

### 11.3. So sánh kiểu dữ liệu sai ngữ nghĩa

```java
assertEquals(new BigDecimal("10.00"), new BigDecimal("10.0"));
```

Đoạn này **cố ý fail** vì `BigDecimal.equals` so cả scale. Nếu muốn so giá trị số, dùng `compareTo`; nếu scale là một yêu cầu, kiểm tra đúng scale.

### 11.4. Dùng `assertTrue` với biểu thức phức tạp

```java
assertTrue(a != null && a.isValid() && a.getCount() == 2);
```

Đây là **đoạn minh họa**, biến `a` chưa được khai báo. Test có thể fail mà không chỉ rõ điều kiện nào sai. Hãy tách thành assertion chuyên biệt, dùng message hoặc `assertAll`.

### 11.5. Cố định cả những chi tiết không thuộc contract

Không nên assert full stack trace, log debug, private method name, thứ tự field JSON không được cam kết, hay toàn bộ response snapshot nếu API chỉ quy định một số trường. Test như vậy thường fail khi refactor hợp lệ.

### 11.6. Chỉ kiểm tra điều mock đã trả về

```java
// Phản ví dụ: serviceMock là mock đã được cấu hình trả "ok".
assertEquals("ok", serviceMock.process(input));
```

Nếu đối tượng được kiểm tra chỉ là mock, logic thật không chạy. Mock/fake nên đặt ở **dependency bên ngoài** phạm vi test; đối tượng nghiệp vụ cần bảo vệ phải là implementation thật.

### 11.7. Bắt exception không có nghĩa đúng nội dung lỗi

`assertThrows(Exception.class, ...)` quá rộng thường chấp nhận cả lỗi hạ tầng không liên quan. Ưu tiên loại lỗi cụ thể được contract định nghĩa, ví dụ `IllegalArgumentException` hoặc exception nghiệp vụ. `assertThrowsExactly` chỉ khi tính chính xác của lớp exception là quan trọng; dùng quá chặt sẽ làm test vỡ do subclass hợp lệ.

### 11.8. Assertion timeout tùy tiện

`assertTimeout(Duration.ofMillis(10), ...)` có thể fail trên CI chậm dù thuật toán đúng. Với kiểm thử chức năng, không nên biến runtime của một máy ngẫu nhiên thành contract. Nếu performance/SLA là yêu cầu, đo ở môi trường phù hợp, mẫu đủ rộng và ngân sách thời gian được định nghĩa rõ.

### 11.9. Điều kiện phụ thuộc nhau trong `assertAll`

Nếu lambda thứ nhất sửa `profile`, lambda thứ hai đọc `profile` sau khi nó bị sửa, việc nhóm có thể làm kết quả bất ngờ. Chỉ dùng `assertAll` khi các kiểm tra độc lập trên dữ liệu đã chuẩn bị; không coi thứ tự lambda là công cụ thực thi nghiệp vụ.

### 11.10. Không kiểm tra hành vi biên và lỗi

Một test chỉ với đầu vào hợp lệ phổ biến có thể bỏ qua `null`, chuỗi rỗng, trùng dữ liệu hoặc vượt giới hạn. Dùng `@ParameterizedTest` cho các biến thể cùng quy tắc, và `assertThrows` cho những lỗi được yêu cầu.

## 12. Assertion về thời gian: dùng đúng phạm vi

JUnit Jupiter có `assertTimeout` và `assertTimeoutPreemptively`. Hai hàm này có ý nghĩa khác nhau:

- `assertTimeout(duration, executable)` chạy hành động và kiểm tra thời lượng sau khi nó hoàn tất; nó **không cắt ngang tác vụ** khi quá hạn.
- `assertTimeoutPreemptively(duration, executable)` thực hiện tác vụ trong thread riêng và có thể đánh dấu test thất bại khi vượt thời hạn. Thay đổi thread có hệ quả cho `ThreadLocal`, transaction context và thành phần gắn với thread.
- Trong Spring test dùng `@Transactional`, thread mới có thể **không tham gia cùng transaction** được test framework quản lý. Vì vậy phải rất cẩn trọng với `assertTimeoutPreemptively` nếu hành động có tác dụng phụ trên database: rollback như mong đợi có thể không xảy ra.

Ví dụ cú pháp minh họa:

```java
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertTimeout;

// Trong phương thức @Test, với service đã chuẩn bị:
assertTimeout(Duration.ofSeconds(2),
        () -> service.register("Lan", false));
```

Đây là đoạn minh họa: không nên sao chép giới hạn hai giây như một SLA mặc định; giới hạn phải có lý do. Đặc biệt, các test business logic thuần ở phần 4 không cần thêm timeout chỉ để “trông đầy đủ”.

Khi kiểm thử thời gian nghiệp vụ (hạn sử dụng voucher), **inject `Clock`** để cố định thời điểm và kiểm tra biên thay vì đợi đồng hồ thực. Đây là hai loại test khác nhau: một loại đo **thời lượng thực thi**, loại kia kiểm tra **quy tắc thời gian**.

## 13. Chạy ví dụ trong module Spring Boot

Với một Gradle project có Spring Boot plugin/BOM được cấu hình, các dependency cần thiết:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` ở Spring Boot 3.x cung cấp JUnit Jupiter, AssertJ, Mockito và các thành phần Spring Test thông dụng. Nếu module đã có dependency, không thêm trùng. Các file Java ở phần 4 và 9 cần đúng đường dẫn/package như đã ghi; dự án cần cấu hình Spring Boot test bootstrap và security phù hợp để web slice hoạt động.

Chạy từ dự án có Gradle wrapper:

```bash
./gradlew test --tests com.example.assertions.ProfileServiceTest --tests com.example.assertions.ProfileControllerWebTest
```

Trên Windows PowerShell, dùng `.\gradlew.bat`. Nếu dự án có nhiều Gradle module, thay task `test` bằng đường dẫn test task chính xác của module chứa ví dụ, rồi giữ các filter `--tests`. Để chạy toàn bộ test module, dùng task `test` tương ứng không có filter.

**Kết quả kỳ vọng:** Các test unit `ProfileServiceTest` kiểm tra thành công ba điều kiện hồ sơ, các trường hợp đầu vào không hợp lệ đều ném `IllegalArgumentException`, và web slice phản hồi HTTP 200/400 theo controller minh họa. Nếu test chạy qua trong project đã cấu hình đúng, Gradle báo `BUILD SUCCESSFUL`. Đây là **kết quả kỳ vọng từ mã**, không phải tuyên bố đã chạy trên một repository cụ thể; không có stdout nghiệp vụ cố định vì ví dụ là JUnit test.

Xem báo cáo do Gradle tạo ở `build/reports/tests/test/index.html` và dữ liệu máy đọc được tại `build/test-results/test/` (đường dẫn tính từ build directory của module). Khi assertion fail, đọc expected/actual và heading của nhóm trước khi xem stack trace sâu hơn.

## 14. Bài tập thực hành

### Bài tập A — sửa một test khó chẩn đoán

Cho đối tượng `Profile` sau đăng ký. Đoạn test:

```java
assertTrue(profile.enabled()
        && profile.roles().contains("USER")
        && profile.displayName().equals("Linh"));
```

Hãy viết lại bằng `assertAll("registered profile", ...)` với ba assertion độc lập. Gợi ý: `assertTrue` cho trạng thái/role và `assertEquals` cho tên. Khi cố ý đổi tên thành “Minh” và bỏ role “USER”, hãy xem JUnit hiển thị bao nhiêu lỗi; không cần phụ thuộc vào chuỗi stack trace.

### Bài tập B — phân biệt so sánh giá trị và identity

Với `new String("hi")` tạo hai object khác nhau nhưng có nội dung bằng nhau, `assertEquals` và `assertSame` cho kết quả giống hay khác? Giải thích tại sao. Sau đó thử `BigDecimal("1.0")` so với `BigDecimal("1.00")` bằng `equals` và `compareTo`.

### Bài tập C — kiểm tra lỗi

Viết một parameterized test cho tên `null`, `""`, `" "` và `"\t"`. Dùng `assertThrows(IllegalArgumentException.class, ...)`. Nếu yêu cầu bổ sung nói API phải trả mã lỗi `INVALID_NAME`, xác định cần thêm unit test, web test hay cả hai để bảo vệ đúng boundary.

### Bài tập D — quyết định nhóm hay tách test

Một scenario tạo tài khoản, gửi email, kích hoạt sau callback và kiểm tra hóa đơn. Nếu mỗi bước phụ thuộc bước trước, có nên đưa mọi thao tác vào một `assertAll` không? Vì sao? Gợi ý: phân biệt **nhiều thuộc tính của một kết quả** với **nhiều hành động có tác dụng phụ**.

## 15. Checklist khi viết và review assertion

- [ ] Test mô tả một quy tắc/hành vi đáng bảo vệ; không chỉ kiểm tra gọi method.
- [ ] Với `assertEquals`, expected đứng trước actual, kiểu so sánh phù hợp (giá trị số, scale, identity).
- [ ] Assertion chuyên biệt thể hiện kỳ vọng rõ hơn một biểu thức `assertTrue` dài.
- [ ] Có kiểm tra biên, đầu vào lỗi, trạng thái hoặc side effect khi đó là contract.
- [ ] `assertAll` nhóm nhiều điều kiện độc lập của **cùng kết quả**; lambda không có side effect ngoài ý muốn.
- [ ] Các assertion thất bại có tên nhóm và message đủ để xác định sai ở đâu.
- [ ] `assertThrows` kiểm tra đúng loại lỗi và đúng hành động; message chỉ bị khóa khi là contract.
- [ ] So sánh collection xét đúng yêu cầu thứ tự và duplicates.
- [ ] Không assert private helper, log debug, implementation call count nếu không thuộc contract.
- [ ] Không dùng timeout tùy tiện hoặc preemptive timeout gây vấn đề transaction/thread.
- [ ] Unit test không khởi động Spring vô cớ; web slice test kiểm tra response HTTP khi cần.
- [ ] Test failure hữu ích cho việc chẩn đoán, và refactor hợp lệ không làm test đỏ vô cớ.

**Điểm cần nhớ:** `assertAll` giúp nhìn thấy **nhiều sai lệch của cùng một kết quả trong một lần chạy**, nhưng chất lượng test đến từ việc chọn đúng các điều kiện cần bảo vệ. Assertion tốt có ý nghĩa nghiệp vụ, thông báo rõ, so sánh đúng ngữ nghĩa dữ liệu và đủ ổn định để sống cùng code qua nhiều lần thay đổi.