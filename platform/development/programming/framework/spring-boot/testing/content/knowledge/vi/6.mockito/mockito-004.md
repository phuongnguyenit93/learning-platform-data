# Mockito ArgumentMatchers, `eq` và quy tắc dùng matcher nhất quán

## 1. Mục tiêu của bài học

Khi kiểm thử một service trong Spring Boot, chúng ta thường dùng Mockito để giả lập repository, HTTP client, payment gateway hoặc adapter khác. Một lệnh stub phải trả lời **với những đối số nào thì mock trả kết quả đã định**; một lệnh verify phải trả lời **đã có lời gọi nào với những đối số thỏa điều kiện**. `ArgumentMatchers` cung cấp cách diễn đạt những điều kiện ấy.

Ví dụ, khi service gửi một lệnh thu tiền gồm mã đơn hàng, số tiền và ghi chú:

- Mã đơn hàng phải **đúng chính xác** `ORD-42`.
- Số tiền có thể là **bất kỳ giá trị `long`** khi ta chỉ cần cô lập kết quả từ gateway.
- Ghi chú có thể **rỗng (`null`)** nếu hợp đồng cho phép.
- Lúc xác minh nghiệp vụ, số tiền thực tế có thể phải đúng **120.000 VND**, chứ không chỉ là “bất kỳ số tiền”.

Mockito có các matcher `eq("ORD-42")`, `anyLong()`, `nullable(String.class)`, `isNull()`, `argThat(...)`… nhưng chúng không phải giá trị Java thông thường để đặt ở mọi nơi. Mockito ghi nhận matcher theo lời gọi, và có một quy tắc quan trọng: **nếu dùng matcher cho một đối số của lời gọi được stub hoặc verify, tất cả đối số của lời gọi đó phải được cung cấp qua matcher**. Đây là nguyên nhân phổ biến của `InvalidUseOfMatchersException`.

Sau bài này, bạn có thể:

1. Chọn đúng giữa literal, `eq`, `anyX`, `isNull`, `nullable` và matcher tự định nghĩa.
2. Dùng matcher nhất quán trong `when(...).thenReturn(...)`, `verify(...)` và `doReturn(...).when(...)`.
3. Hiểu vì sao `eq(...)` **không** giống việc truyền một đối số thật, dù kiểm tra cùng điều kiện bằng nhau.
4. Phân biệt kiểu so sánh bằng `equals` và cùng tham chiếu bằng `same`.
5. Viết test có ý nghĩa với Java 17, JUnit Jupiter và Mockito, tránh stub quá rộng khiến bug lọt qua.
6. Đọc lỗi mismatch, lỗi dùng matcher sai, lỗi strict stubbing và chọn cách sửa đúng.

## 2. Matcher giải quyết bài toán gì?

Giả sử một interface gateway có chữ ký:

```java
String charge(String orderId, long amount, String note);
```

Để stub một lời gọi chính xác, Mockito cho phép truyền literal:

```java
when(gateway.charge("ORD-42", 120_000L, "gift"))
        .thenReturn("TX-99");
```

Lệnh trên chỉ áp dụng với những đối số tương đương theo cách Mockito so sánh thông thường. Nếu test muốn cố định order ID nhưng không quan tâm số tiền và ghi chú, có thể dùng matcher:

```java
when(gateway.charge(
        eq("ORD-42"),
        anyLong(),
        nullable(String.class)
)).thenReturn("TX-99");
```

Ở đây ba đối số đều là matcher:

- `eq("ORD-42")` khớp giá trị chuỗi chính xác.
- `anyLong()` khớp bất kỳ `long` (và `Long` khác `null` ở chữ ký nhận wrapper).
- `nullable(String.class)` khớp `String` hoặc `null`.

Mockito sử dụng cùng cơ chế khi xác minh:

```java
verify(gateway).charge(
        eq("ORD-42"),
        eq(120_000L),
        isNull()
);
```

Một cách hiểu dễ nhớ:

| Việc | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Stubbing | `when(mock.find(...)).thenReturn(value)` | Nếu lời gọi thật khớp matcher, cung cấp câu trả lời đã định |
| Verification | `verify(mock).save(...)` | Khẳng định có lời gọi đã xảy ra thỏa matcher |
| Literal | `verify(mock).send("A", 1)` | Đúng giá trị `"A"` và `1`, không cần matcher |
| `eq` | `verify(mock).send(eq("A"), anyInt())` | Giữ điều kiện bằng nhau trong lời gọi có matcher |
| `argThat` | `verify(mock).send(eq("A"), intThat(n -> n > 0))` | Áp dụng một điều kiện kiểm tra riêng |

Matcher **không thực thi lời gọi production**. Stub chỉ định hành vi của mock, verify kiểm tra lịch sử tương tác trên mock; logic thực trong service vẫn phải được chạy qua bước Act.

## 3. Quy tắc bắt buộc: đã dùng matcher thì dùng cho **mọi đối số**

Đây là trọng tâm của bài học. Xét interface:

```java
interface BillingPort {
    String charge(String orderId, long amount, String note);
}
```

### 3.1. Hai cách đúng

**Cách A — không dùng matcher nào:**

```java
when(port.charge("ORD-42", 120_000L, "gift"))
        .thenReturn("TX-1");

verify(port).charge("ORD-42", 120_000L, "gift");
```

**Cách B — tất cả đối số đều là matcher:**

```java
when(port.charge(
        eq("ORD-42"),
        anyLong(),
        anyString()
)).thenReturn("TX-1");

verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        eq("gift")
);
```

`eq` cũng là một matcher. Khi muốn giữ một đối số cụ thể trong cùng lời gọi có `anyLong()`, bọc giá trị đó bằng `eq(...)`. Không nhất thiết mọi matcher phải cùng loại; chỉ cần **tất cả vị trí đối số** đều được biểu diễn bằng matcher.

### 3.2. Hai cách sai

```java
// SAI: một literal trộn với hai matcher trong cùng lời gọi.
when(port.charge("ORD-42", anyLong(), anyString()))
        .thenReturn("TX-1");

// SAI: một matcher trộn với literal ở phần còn lại.
verify(port).charge(eq("ORD-42"), 120_000L, "gift");
```

Các dòng trên là **ví dụ lỗi có chủ đích**, không được chép vào test chạy thành công. Khi Mockito ghi nhận một số matcher không tương ứng số đối số, nó có thể ném `org.mockito.exceptions.misusing.InvalidUseOfMatchersException` và chỉ ra số matcher mong đợi/đã ghi nhận.

Bản sửa:

```java
when(port.charge(eq("ORD-42"), anyLong(), anyString()))
        .thenReturn("TX-1");

verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        eq("gift")
);
```

**Điều cần phân biệt:** Quy tắc nhất quán áp dụng trong **một lần gọi phương thức** đang được stub/verify, không bắt bạn phải sử dụng matcher trong mọi lời gọi ở toàn bộ test. Một test có thể dùng literal ở lời gọi thứ nhất và matcher ở lời gọi thứ hai, miễn từng lời gọi tự nhất quán.

### 3.3. Tại sao Mockito yêu cầu như vậy?

Các hàm `any()`, `eq()`, `argThat()` ghi lại điều kiện so khớp trong cơ chế matcher nội bộ của Mockito, rồi trả **giá trị giả** để Java biên dịch được lời gọi phương thức. Tùy loại, giá trị đó có thể là `null`, `0`, `false` hoặc giá trị giả khác. Giá trị Java trả về **không phải chính matcher**.

Vì matcher được ghi nhận tách khỏi các đối số Java được truyền tới phương thức mock, Mockito cần đối chiếu đúng số matcher với số đối số của lời gọi đó. Nếu trộn matcher với literal, không còn một danh sách matcher đồng nhất để diễn giải lời gọi.

Hệ quả quan trọng:

- Không lưu `String order = eq("ORD-42")` rồi dùng `order` như dữ liệu production.
- Không dùng `anyLong()` để tạo số tiền mẫu hoặc gọi vào service thật.
- Không gọi matcher ngoài ngữ cảnh stubbing/verification của Mockito; matcher có thể để lại trạng thái ghi nhận và làm một lệnh Mockito sau đó báo lỗi.
- Không kỳ vọng `eq("A")` trả chính chuỗi `"A"`. Nó là biểu thức phục vụ Mockito, không phải hàm trả về giá trị giữ nguyên.

## 4. `eq(...)`: khớp bằng giá trị, không phải tham chiếu

`ArgumentMatchers.eq(expected)` diễn đạt điều kiện đối số thực tế **bằng** `expected`. Với object, sự tương đương dựa trên ngữ nghĩa `equals` của kiểu; với primitive, so sánh giá trị.

Ví dụ:

```java
verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        eq("gift")
);
```

Nếu ba đối số đều là giá trị cụ thể, dòng sau thường dễ đọc hơn và cũng hợp lệ:

```java
verify(port).charge("ORD-42", 120_000L, "gift");
```

Vậy **khi nào thật sự cần `eq`?** Khi ít nhất một đối số khác của **cùng lời gọi** được kiểm tra bằng matcher:

```java
verify(port).charge(
        eq("ORD-42"),   // Cụ thể.
        anyLong(),      // Linh hoạt.
        isNull()        // Phải là null.
);
```

### 4.1. `eq` so với `same`

Giả sử dùng Java 17 record:

```java
record Address(String city, String street) {}

Address expected = new Address("HCM", "Le Loi");
Address actual = new Address("HCM", "Le Loi");
```

`expected` và `actual` là hai instance khác nhau nhưng record có `equals` theo các thành phần của record:

- `eq(expected)` có thể khớp `actual` vì hai record bằng nhau theo giá trị.
- `same(expected)` chỉ khớp **đúng cùng instance**.
- `refEq(expected)` có thể dùng so sánh bằng reflection trong một số trường hợp thiếu `equals`, nhưng chỉ nên dùng có chủ đích; thường tốt hơn tạo value object có `equals/hashCode` đúng.

Trong đa số service test, contract quan tâm **dữ liệu được chuyển qua ranh giới**, vì vậy `eq` hoặc so sánh field là phù hợp hơn `same`. Kiểm tra reference identity chỉ nên dùng khi chính hợp đồng yêu cầu chuyển nguyên một instance, ví dụ một cache/trình quản lý object có identity đặc biệt.

### 4.2. So sánh object phức tạp

Nếu `PaymentRequest` là record gồm `orderId`, `amount` và `currency`, có thể xác minh:

```java
verify(paymentPort).pay(
        eq(new PaymentRequest("ORD-42", 120_000L, "VND"))
);
```

Đây là **đoạn minh họa**, yêu cầu `paymentPort` và record `PaymentRequest` của dự án. Nó phù hợp khi **mọi trường của object** đều thuộc contract.

Nếu request chứa timestamp, generated ID hoặc metadata không ổn định, đừng ép `eq` cho toàn bộ object chỉ để sau đó phải sửa test liên tục. Dùng `argThat` để chọn field quan trọng hoặc `ArgumentCaptor` để kiểm tra riêng các trường.

**Không nhầm `eq` với `assertEquals`:** `eq` khai báo điều kiện đối số cho Mockito; `assertEquals` của JUnit kiểm tra một kết quả đã quan sát được.

## 5. Bảng các matcher phổ biến và ngữ nghĩa `null`

Sự khác nhau giữa `any()` và matcher có kiểm tra kiểu là điểm dễ gây lỗi giả. Các ngữ nghĩa dưới đây được ghi rõ trong API Mockito 5.x và phù hợp cho Java 17.

| Matcher | Điều kiện khớp | Có khớp `null`? | Dùng khi nào |
| --- | --- | --- | --- |
| `eq("A")` | Giá trị bằng `"A"` | Không, trừ khi expected là `null` | Giữ giá trị cụ thể trong lời gọi có matcher |
| `eq(5L)` | Giá trị `long` bằng 5 | Không áp dụng cho primitive | Số cụ thể phải đúng |
| `any()` | Bất kỳ đối số tham chiếu; lưu ý varargs | **Có** | Không quan tâm object, kể cả `null` |
| `any(String.class)` | Instance của `String` | **Không** | Bất kỳ `String` không null |
| `anyString()` | `String` không null | **Không** | Chuỗi bất kỳ, kể cả chuỗi rỗng |
| `anyInt()` / `anyLong()` | Primitive hoặc wrapper tương ứng không null | **Không** với wrapper | Số bất kỳ đúng kiểu |
| `anyList()` / `anyMap()` | Collection/map đúng loại không null | **Không** | Không quan tâm phần tử, chỉ cần container khác null |
| `isNull()` | Chính xác `null` | **Có, chỉ null** | Đối số bắt buộc null |
| `notNull()` | Bất kỳ đối số khác null | **Không** | Contract yêu cầu có giá trị |
| `nullable(String.class)` | `String` hoặc `null` | **Có** | Tham số được phép bỏ trống |
| `startsWith("PRE-")` | Chuỗi bắt đầu bằng prefix | Không | ID có prefix |
| `contains("x")` | Chuỗi chứa đoạn con | Không | Metadata/câu mô tả có token |
| `argThat(predicate)` | Điều kiện tự định nghĩa | Tùy predicate | Kiểm tra field/pattern đặc thù |
| `same(object)` | Cùng tham chiếu với object mẫu | Có thể so reference null nhưng dùng `isNull` rõ hơn | Contract về instance identity |

**Chọn đúng theo mục đích:**

- Muốn nhận **bất kỳ chuỗi không null**: `anyString()`.
- Muốn nhận **chuỗi hoặc null**: `nullable(String.class)` (rõ ý hơn `any()`).
- Muốn nhận **chỉ null**: `isNull()`.
- Muốn nhận **đúng chuỗi "ORD-42"**: `eq("ORD-42")` nếu đang kết hợp matcher, hoặc literal nếu không.
- Muốn nhận **số nguyên dương**: `intThat(value -> value > 0)`; `anyInt()` cũng khớp 0 và số âm.
- Muốn nhận **đúng một collection có phần tử cụ thể**: `eq(List.of(...))` hoặc matcher kiểm tra nội dung, không dùng `anyList()` nếu nội dung quan trọng.

**Cảnh báo:** `any()` không có kiểu có thể khớp `null` đối với đối số object thông thường, nhưng theo Mockito 5 nó **không còn tự động khớp cả varargs như một nhóm**. Với phương thức varargs, xem mục 11 và chọn matcher rõ mục tiêu phần tử hay cả mảng.

## 6. Ví dụ đầy đủ, chạy được với Java 17 + JUnit Jupiter + Mockito

Ví dụ này dùng service thật và interface gateway được mock, không cần Spring context. Nó cho thấy matcher dùng ở stubbing, verification, kiểm tra `null` và kết quả nghiệp vụ.

### 6.1. Tệp production

**`src/main/java/example/CheckoutService.java`:**

```java
package example;

import java.util.Objects;

public final class CheckoutService {
    public interface PaymentPort {
        String charge(String orderId, long amountInVnd, String note);
    }

    public record Receipt(String orderId, String transactionId) {}

    private final PaymentPort paymentPort;

    public CheckoutService(PaymentPort paymentPort) {
        this.paymentPort = Objects.requireNonNull(paymentPort);
    }

    public Receipt checkout(String orderId, long amountInVnd, String note) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountInVnd <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        String transactionId =
                paymentPort.charge(orderId, amountInVnd, note);

        return new Receipt(orderId, transactionId);
    }
}
```

Class dùng Java 17 record và constructor injection thủ công. Không cần annotation Spring, vì mục tiêu là học matcher độc lập với framework.

### 6.2. Tệp test hoàn chỉnh

**`src/test/java/example/CheckoutServiceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.ArgumentMatchers.longThat;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.ArgumentMatchers.startsWith;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CheckoutServiceTest {
    @Test
    void allowsNullableNoteWhileKeepingOrderIdExact() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        when(gateway.charge(
                eq("ORD-42"),
                anyLong(),
                nullable(String.class)
        )).thenReturn("TX-9");

        var service = new CheckoutService(gateway);
        CheckoutService.Receipt receipt =
                service.checkout("ORD-42", 120_000L, null);

        assertEquals("ORD-42", receipt.orderId());
        assertEquals("TX-9", receipt.transactionId());
        verify(gateway).charge(
                eq("ORD-42"),
                eq(120_000L),
                isNull()
        );
    }

    @Test
    void usesExactLiteralArgumentsWhenNoMatcherIsNeeded() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        when(gateway.charge(
                "ORD-43", 50_000L, "gift"
        )).thenReturn("TX-10");

        var service = new CheckoutService(gateway);
        var receipt = service.checkout(
                "ORD-43", 50_000L, "gift");

        assertEquals("TX-10", receipt.transactionId());
        verify(gateway).charge("ORD-43", 50_000L, "gift");
    }

    @Test
    void verifiesBusinessConstraintsWithCustomMatchers() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        when(gateway.charge(
                eq("ORD-44"),
                anyLong(),
                startsWith("campaign-")
        )).thenReturn("TX-11");

        var service = new CheckoutService(gateway);
        var receipt = service.checkout(
                "ORD-44", 80_000L, "campaign-2026");

        assertEquals("TX-11", receipt.transactionId());
        verify(gateway).charge(
                eq("ORD-44"),
                longThat(value -> value > 0),
                argThat(note -> note != null
                        && note.endsWith("-2026"))
        );
    }

    @Test
    void typedStringMatcherDoesNotAcceptNull() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        when(gateway.charge(
                eq("ORD-45"),
                anyLong(),
                anyString()
        )).thenReturn("TX-non-null");

        assertNull(gateway.charge("ORD-45", 100L, null));
        assertEquals(
                "TX-non-null",
                gateway.charge("ORD-45", 100L, "ok")
        );
    }

    @Test
    void rejectsInvalidAmountBeforeCallingGateway() {
        var gateway = mock(CheckoutService.PaymentPort.class);
        var service = new CheckoutService(gateway);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout("ORD-46", 0L, "gift"));
        verifyNoInteractions(gateway);
    }
}
```

**Lưu ý QA mã:** Các test ở trên dùng `mock(...)` trực tiếp nên không cần `MockitoExtension` hoặc Spring để khởi tạo mock. Các import dùng API Mockito 5.x/JUnit Jupiter; `longThat` có kiểu primitive `long`. Tệp `CheckoutService.java` và tệp test có package/class tương ứng với đường dẫn; đoạn minh họa lỗi ở mục 3 **không** nằm trong test này.

### 6.3. Dependency và cách chạy

Trong dự án Spring Boot 3.x đã quản lý các phiên bản bằng Spring Boot BOM, Gradle Groovy DSL thường khai báo:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là đoạn thêm vào **build hiện có**, không phải một `build.gradle` độc lập: dự án còn cần `java` plugin, repositories và BOM, Spring Boot plugin hoặc cách quản lý dependency tương đương. Với Maven starter test:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dùng JUnit và Mockito **không qua Spring Boot**, hãy khai báo rõ `junit-jupiter`, `mockito-core` và JUnit Platform launcher/engine theo BOM hoặc version tương thích của build đó.

Trong thư mục dự án có Gradle wrapper:

```bash
./gradlew test --tests example.CheckoutServiceTest
```

Trên Windows:

```powershell
.\gradlew.bat test --tests example.CheckoutServiceTest
```

Kết quả mong đợi: **5 test pass**; không có stdout nghiệp vụ cố định vì test chỉ dùng assertions. Phần hiển thị task/timing cụ thể phụ thuộc phiên bản Gradle và môi trường.

Điểm cần học từ từng test:

| Test | Stubbing | Verification | Rủi ro được chứng minh |
| --- | --- | --- | --- |
| `allowsNullableNote...` | `eq` + `anyLong` + `nullable` | `eq` + `eq` + `isNull` | Giữ ID cụ thể, cho phép ghi chú null, kiểm tra số tiền thực |
| `usesExactLiteral...` | Tất cả literal | Tất cả literal | Không cần matcher khi mọi đối số chính xác |
| `verifiesBusinessConstraints...` | Matcher theo prefix | `longThat` + `argThat` | Ràng buộc nghiệp vụ thay vì chỉ “bất kỳ” |
| `typedStringMatcher...` | `anyString()` | Kiểm tra đầu ra mock | `null` không khớp matcher chuỗi có kiểu |
| `rejectsInvalidAmount...` | Không stub | `verifyNoInteractions` | Dữ liệu sai không gọi hệ thống ngoài |

**Giới hạn:** Test đầu chỉ chứng minh `PaymentPort` được gọi với đối số đúng và response từ mock được service chuyển qua. Nó không chứng minh hệ thống thanh toán thật chạy, request HTTP thật đúng hoặc dữ liệu được commit vào database. Đó là chủ đề của các test tích hợp rộng hơn.

## 7. Lựa chọn `eq`, `any`, `isNull`, `nullable` trong thực tế

### 7.1. `anyString()` không thay cho `nullable(String.class)`

Một số API cho phép ghi chú null:

```java
// Chỉ khớp note là String khác null:
when(port.charge(eq("ORD-1"), anyLong(), anyString()))
        .thenReturn("TX-1");

// Khớp cả note là String lẫn null:
when(port.charge(eq("ORD-1"), anyLong(), nullable(String.class)))
        .thenReturn("TX-1");

// Chỉ khớp note là null:
when(port.charge(eq("ORD-1"), anyLong(), isNull()))
        .thenReturn("TX-1");
```

Các dòng trên là **phương án độc lập**, không nên khai báo tất cả ba stub vào cùng một test chỉ để thử matcher, vì stub sau có thể che/đụng stub trước và strict stubbing có thể báo stub không dùng. Đặt từng trường hợp trong test riêng hoặc so sánh ý nghĩa trước khi triển khai.

Matcher không giúp xác định **hợp đồng cho phép null hay không**. Nếu logic service không chấp nhận null, hãy xác minh service từ chối đúng thay vì làm stub permissive hơn để test xanh.

### 7.2. `any()` có thể quá rộng

```java
verify(port).charge(any(), anyLong(), any());
```

Câu trên có thể pass dù order ID sai hoặc note sai, và nó không chặn null cho hai tham số reference. Nếu mã đơn hàng thuộc yêu cầu quan trọng, chọn `eq("ORD-42")`:

```java
verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        nullable(String.class)
);
```

Viết matcher **hẹp vừa đủ theo hợp đồng**: stubbing có thể mềm ở một số đầu vào để không bị ràng buộc vào chi tiết vô nghĩa; verification cần đủ chặt ở những field rủi ro cao để phát hiện regression.

### 7.3. Khi không cần matcher, hãy dùng literal

```java
verify(port).charge("ORD-42", 120_000L, "gift");
```

Trực tiếp, dễ đọc và hoàn toàn hợp lệ. Đừng biến mọi giá trị thành `eq` theo thói quen nếu lời gọi không có matcher nào khác. Quy tắc “mọi đối số phải là matcher” là **quy tắc có điều kiện**: chỉ kích hoạt khi **có ít nhất một matcher trong cùng lời gọi**.

## 8. `argThat`: diễn đạt ràng buộc dựa trên đối số

`argThat(ArgumentMatcher<T>)` cho phép kiểm tra một điều kiện tùy chỉnh, thường dùng khi object có nhiều field và chỉ vài field là quan trọng.

Ví dụ interface ngoài service:

```java
interface NotificationPort {
    void publish(String topic, Notice notice);
}

record Notice(String orderId, long amount, String currency) {}
```

Đoạn verify minh họa:

```java
verify(notifier).publish(
        eq("payment.completed"),
        argThat(notice ->
                notice != null
                && notice.orderId().equals("ORD-42")
                && notice.amount() == 120_000L
                && notice.currency().equals("VND"))
);
```

Đoạn này **không độc lập**: cần `NotificationPort`, `Notice`, mock `notifier` và lời gọi trong Act. Vì đối số thứ nhất dùng `eq`, đối số thứ hai cũng dùng matcher `argThat`; quy tắc nhất quán được giữ.

### 8.1. Tránh điều kiện null gây lỗi

Sai:

```java
// Rủi ro NullPointerException nếu note là null.
argThat(note -> note.startsWith("promo-"))
```

An toàn hơn:

```java
argThat(note -> note != null && note.startsWith("promo-"))
```

Nếu null là một trường hợp **được phép** theo hợp đồng, dùng điều kiện tương ứng thay vì mặc định loại null:

```java
argThat(note -> note == null || note.startsWith("promo-"))
```

### 8.2. Primitive và generic type

`argThat` là matcher dạng generic trả về đối số tham chiếu, trong khi `int`/`long` là primitive. Với tham số nguyên thủy, các phiên bản Mockito hiện đại có matcher chuyên biệt:

```java
verify(port).charge(
        eq("ORD-42"),
        longThat(value -> value >= 100_000L),
        anyString()
);
```

Dùng `longThat` thay vì một `argThat` sinh boxing/unboxing không phù hợp có thể tạo NullPointerException do giá trị giả dùng để biên dịch. Với `int`, dùng `intThat(...)`. Nếu chỉ cần giá trị cụ thể, `eq(120_000L)` còn rõ hơn.

### 8.3. Khi nào không nên dùng `argThat`?

Nếu predicate quá dài hoặc có nhiều nhánh, thất bại test thường khó chẩn đoán. Khi cần xem và assert nhiều field sau lời gọi, hãy chọn `ArgumentCaptor`. Nếu dữ liệu là immutable record có `equals` chính xác và toàn bộ trường đều thuộc hợp đồng, `eq(new Notice(...))` có thể đơn giản hơn predicate.

Matcher nên là **điều kiện thuần**, không ghi database, không đổi state, không gửi network hoặc làm tăng counter. Mockito có thể đánh giá matcher trong các thao tác nội bộ mà test không nên phụ thuộc số lần predicate được gọi.

## 9. `ArgumentCaptor`: lấy đối số ra để assert từng thuộc tính

Captor rất hữu ích khi service tạo object phong phú: event, request HTTP, email, DTO. Ta muốn xác minh có lời gọi gửi event và sau đó kiểm tra từng trường.

Ví dụ kiểm thử một producer sự kiện:

```java
// Đoạn minh họa: giả sử đã có mock notifier và record Notice.
Notice sent = new Notice("ORD-42", 120_000L, "VND");
notifier.publish("payment.completed", sent);

ArgumentCaptor<Notice> noticeCaptor =
        ArgumentCaptor.forClass(Notice.class);

verify(notifier).publish(
        eq("payment.completed"),
        noticeCaptor.capture()
);

Notice captured = noticeCaptor.getValue();
assertEquals("ORD-42", captured.orderId());
assertEquals(120_000L, captured.amount());
assertEquals("VND", captured.currency());
```

Với imports `org.mockito.ArgumentCaptor`, `org.mockito.Mockito.verify` và `org.junit.jupiter.api.Assertions.assertEquals`. Đây là **đoạn trong một test đã khởi tạo mock**, chưa phải file Java độc lập. Trong `verify(...)`, `capture()` là matcher, nên đối số topic đi cùng phải là `eq(...)` nếu dùng matcher.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Một object khớp toàn bộ bằng `equals` | `eq(expected)` hoặc literal |
| Một vài tiêu chí ngắn | `argThat(...)` |
| Nhiều trường cần assertion rõ ràng | `ArgumentCaptor` |
| Muốn xem toàn bộ các lần gọi | `captor.getAllValues()` kèm verify count |
| Chỉ cần đối số khác null | `notNull()` hoặc `any(Type.class)` |

Mockito khuyến nghị ưu tiên captor trong **verification** hơn **stubbing**. Captor trong stub thường khiến luồng test khó đọc và nếu lời gọi không xảy ra, không có dữ liệu để xem. Với stubbing theo điều kiện, dùng `argThat` hoặc matcher đã có.

## 10. Matcher trong `when`, `verify`, `doReturn` và `doThrow`

Quy tắc nhất quán áp dụng ở mọi nơi Mockito cần diễn giải lời gọi mock.

### 10.1. Stubbing có kết quả

```java
when(port.charge(eq("ORD-42"), anyLong(), isNull()))
        .thenReturn("TX-9");
```

### 10.2. Verification

```java
verify(port).charge(eq("ORD-42"), eq(120_000L), isNull());
```

Theo mặc định, `verify(mock).method(...)` xác minh lời gọi phù hợp **chính xác một lần**. Nếu nghiệp vụ cần kiểm tra số lần:

```java
verify(port, times(2)).charge(
        eq("ORD-42"), anyLong(), nullable(String.class)
);
```

Đây là **ví dụ mô tả cú pháp**, không phải assertion đúng cho mọi trường hợp thanh toán: nếu hợp đồng chỉ cho thu tiền một lần, `times(2)` là sai về nghiệp vụ. Việc Mockito khớp matcher không quyết định thế nào là hành vi đúng; đặc tả nghiệp vụ quyết định.

### 10.3. `doReturn` với spy hoặc stubbing khác

```java
doReturn("TX-9").when(port)
        .charge(eq("ORD-42"), anyLong(), isNull());
```

Với một mock thông thường, cách này có thể thay cho `when(...).thenReturn(...)`. Với **spy**, `when(spy.method(...))` có thể thực sự gọi method gốc ngay lúc thiết lập stub; `doReturn(...).when(spy).method(...)` tránh thực thi method gốc trong quá trình stub. Tránh dùng spy khi không cần thiết; ưu tiên mock ranh giới rõ hoặc tạo fake đơn giản.

### 10.4. `doThrow` cho method `void`

```java
// Minh họa với interface AuditPort { void record(String type, long amount); }
doThrow(new IllegalStateException("audit unavailable"))
        .when(auditPort)
        .record(eq("PAYMENT"), anyLong());
```

Đoạn này cần `auditPort` là mock đúng interface. Với void method, `when(auditPort.record(...))` không biên dịch do return type là `void`; dùng họ `doThrow`/`doAnswer`/`doNothing` khi phù hợp.

Để dùng các cú pháp trên, imports thường thuộc `org.mockito.Mockito` cho `when`, `verify`, `doReturn`, `doThrow`, `times`; và `org.mockito.ArgumentMatchers` cho `eq`, `anyLong`, `isNull`.

## 11. Những trường hợp cần cẩn thận: overloaded method, varargs, generic

### 11.1. Phương thức overloaded

Giả sử interface có hai overload:

```java
void send(String message);
void send(int code);
```

Lệnh `send(any())` có thể không chọn overload như mong muốn trong một số khai báo phức tạp; `anyString()` chỉ rõ muốn `String`, `anyInt()` chỉ rõ `int`.

Với overload nhận nhiều kiểu reference, `any()` không có type có thể làm trình biên dịch Java báo **ambiguous method call**. Hãy chọn `any(String.class)` hoặc cast/type witness phù hợp thay vì cố giải bằng thay đổi logic test. Mockito không làm thay đổi cơ chế Java chọn overload tại compile time.

### 11.2. Tham số varargs

Giả sử:

```java
interface TagPort {
    void attach(String id, String... tags);
}
```

Varargs được Java thể hiện bằng mảng nhưng Mockito 5 thay đổi ngữ nghĩa matching varargs so với Mockito cũ:

- Muốn matcher **toàn bộ mảng varargs**: dùng `any(String[].class)` ở vị trí mảng.
- Muốn kiểm tra **một phần tử vararg**: dùng matcher `String` tại vị trí phần tử của lời gọi phù hợp.
- Nếu số lượng hoặc nội dung tag thuộc contract, `eq(new String[] {...})` có thể cần lưu ý cách so sánh mảng; thường dùng `ArgumentCaptor`/assertion phù hợp hoặc xác minh từng phần tử qua cú pháp rõ ràng.

Ví dụ minh họa với một mock `tags`:

```java
verify(tags).attach(eq("ORD-42"), any(String[].class));
```

Ví dụ này khớp một đối số mảng `String[]` không null theo Mockito 5; không có nghĩa nó xác minh số lượng tag hoặc nội dung từng tag. Nếu chính ranh giới cần đúng hai tag, hãy dùng matcher/assertion nhắm vào số lượng và giá trị cụ thể. Khi di chuyển test từ Mockito 4 lên 5, kiểm tra lại các stub/verify dựa trên `any()` của varargs theo tài liệu phiên bản đã resolve.

### 11.3. Generic collections

Với `List<String>`, `anyList()` khớp danh sách không null nhưng không chứng minh phần tử nào. Khi code test cần bảo đảm danh sách chứa một SKU cụ thể, dùng `argThat(list -> list != null && list.contains("SKU-7"))` hoặc captor rồi assert chi tiết.

Lưu ý quy tắc type inference của Java và chữ ký method. Một matcher quá chung như `any()` có thể khiến code khó đọc hoặc chọn overload sai; matcher có kiểu rõ ràng thường tốt hơn.

## 12. Kiểm tra giá trị thật: đừng để matcher quá rộng che lỗi

Giả sử service bị bug truyền `amount = 0` vào payment gateway nhưng test dùng:

```java
verify(port).charge(anyString(), anyLong(), any());
```

Test có thể vẫn pass. `anyLong()` không có nghĩa “long hợp lệ”, nó khớp cả 0 và số âm.

Nếu hợp đồng yêu cầu số tiền **đúng bằng 120.000**:

```java
verify(port).charge(
        eq("ORD-42"),
        eq(120_000L),
        nullable(String.class)
);
```

Nếu hợp đồng chỉ yêu cầu số tiền **dương** nhưng không cố định số:

```java
verify(port).charge(
        eq("ORD-42"),
        longThat(amount -> amount > 0L),
        nullable(String.class)
);
```

Hai assertion phục vụ hai hợp đồng khác nhau. Matcher cho stubbing có thể rộng để định nghĩa phản hồi của mock, nhưng verification phải tập trung vào output/effect mà bài test cần chứng minh.

**Quy tắc lựa chọn thực dụng:**

1. Nếu mọi đối số phải đúng giá trị cụ thể, dùng literal hoặc so sánh expected object.
2. Nếu chỉ một vài đối số cần linh hoạt, dùng `eq` ở phần cố định và matcher ở phần còn lại.
3. Nếu cần null rõ ràng, dùng `isNull` hoặc `nullable` thay vì mơ hồ `any()`.
4. Nếu điều kiện nghiệp vụ đặc thù, dùng `argThat`/`intThat`/`longThat`.
5. Nếu cần kiểm tra một object giàu thông tin, dùng `ArgumentCaptor`, assert các trường quan trọng và tránh ràng buộc metadata không ổn định.

## 13. Phân biệt Mockito matcher với Spring Boot bean override

Trong Spring Boot, có hai việc độc lập:

- **Cung cấp bean giả trong Spring TestContext**: ở Spring Boot 3.3 thường dùng `@MockBean`; với Spring Framework 6.2+ có `@MockitoBean`, và các phiên bản Boot mới khuyến nghị cơ chế này.
- **Diễn đạt điều kiện trên đối số của lời gọi mock**: dùng `ArgumentMatchers.eq`, `anyLong`, `argThat`… từ Mockito.

Ví dụ minh họa với Spring Framework có `@MockitoBean`:

```java
@SpringBootTest
class PaymentFlowTest {
    @MockitoBean
    PaymentPort paymentPort;

    @Test
    void processesOrder() {
        when(paymentPort.charge(
                eq("ORD-42"),
                anyLong(),
                isNull()
        )).thenReturn("TX-9");

        // Gọi một use case bean thật, sau đó assert kết quả.
    }
}
```

Đây là **khung minh họa**, chưa phải test độc lập: `PaymentPort` cần là kiểu bean phù hợp, phải có `@SpringBootApplication` hoặc test context đúng, phải gọi use case thật và thêm assertions. Đừng sao chép trực tiếp rồi coi test trống là đã xác minh hành vi.

`@MockBean`/`@MockitoBean` quyết định **bean nào trong Spring context là mock**; chúng không thay đổi quy tắc matcher. Trộn literal và matcher sai vẫn ném lỗi Mockito trong Spring Boot y như với JUnit thuần. Ngược lại, lỗi `NoSuchBeanDefinitionException` hoặc thiếu Spring context không tự động là `InvalidUseOfMatchersException`.

Trong test unit thuần, ưu tiên `mock(PaymentPort.class)` và truyền bằng constructor như mục 6; không cần khởi động Spring chỉ để dùng `eq` hoặc `verify`.

## 14. Đọc và sửa lỗi thường gặp

### 14.1. `InvalidUseOfMatchersException`

Triệu chứng thường gồm thông báo kiểu “N matchers expected, M recorded” hoặc giải thích matcher được dùng ngoài verification/stubbing.

**Nguyên nhân thường gặp:**

- Trộn literal với matcher trong cùng lời gọi nhiều đối số.
- Gọi `eq()`/`any()` trước để lưu vào biến hoặc đưa matcher vào lời gọi của **đối tượng thật** thay vì mock.
- Dùng matcher ở biểu thức phụ không phải đối số trực tiếp của lời gọi Mockito.
- Sử dụng matcher sau một helper khác khiến Mockito lưu trạng thái matcher không đúng vị trí.
- Dùng matcher generic cho primitive làm phát sinh null unboxing hoặc lỗi overload.

**Cách điều tra:**

1. Xác định dòng `when(...)`, `verify(...)` hoặc `doReturn(...).when(...)` được báo.
2. Đếm số đối số **thực** của method ở chữ ký đã chọn.
3. Nếu bất kỳ đối số nào có matcher, chuyển **toàn bộ** đối số còn lại sang matcher (thường `eq(...)`) hoặc bỏ hết matcher nếu mọi đối số cố định.
4. Tìm mọi lời gọi `any/eq/argThat` ngoài ngữ cảnh Mockito ngay trước lỗi; chúng có thể làm stack matcher lệch.
5. Chạy lại test nhỏ nhất; không cố chữa bằng `lenient()` hoặc đổi Spring context nếu nguyên nhân là matcher.

### 14.2. Stubbing không khớp nên mock trả giá trị mặc định

Một mock chưa được stub cho lời gọi cụ thể thường trả default, ví dụ `null` cho `String` và `0` cho primitive; một số kiểu có giá trị mặc định đặc thù tùy Mockito. Ví dụ `anyString()` **không** khớp `null`:

```java
when(port.charge(eq("ORD-42"), anyLong(), anyString()))
        .thenReturn("TX-9");

// Nếu note là null, stub trên không khớp.
String result = port.charge("ORD-42", 120_000L, null);
```

`result` sẽ là `null` với mock trả `String` theo default answer thông thường, trừ khi mock đã được cấu hình khác. Nếu `null` là đầu vào hợp lệ, đổi sang `nullable(String.class)` hoặc `isNull()` theo yêu cầu. Nếu đầu vào null là bug, hãy sửa đường gọi và bổ sung assertion thay vì làm stub rộng hơn để che bug.

### 14.3. `Wanted but not invoked` / `Arguments are different!`

Mockito đã có hoặc chưa có các lời gọi, nhưng `verify(...)` không tìm thấy invocation thỏa matcher.

- Kiểm tra service đã thật sự được chạy trong Act chưa.
- Kiểm tra đúng instance mock được truyền vào service.
- So sánh expected ID, amount, note, khoảng trắng, casing, object `equals` và null.
- Nếu verification dùng `anyLong()` mà vẫn lỗi, nguyên nhân có thể ở đối số khác (`eq`/`isNull`) hoặc method khác.
- Chỉ nới matcher khi contract thực sự linh hoạt; không dùng `any()` để xóa một lỗi nghiệp vụ quan trọng.

### 14.4. `UnnecessaryStubbingException` và `PotentialStubbingProblem`

Khi dùng `@ExtendWith(MockitoExtension.class)`, strict stubbing có thể thông báo:

- **Unused stubbing:** test đã khai báo stub nhưng không có luồng nào cần dùng.
- **Stubbing argument mismatch:** code gọi cùng phương thức với các đối số khác những gì stub được thiết lập trong điều kiện strictness phù hợp.

Đây **không nhất thiết** là lỗi “một lời gọi trộn literal và matcher”. Ngay cả một stub viết đúng cú pháp matcher có thể thừa hoặc quá hẹp.

Sửa bằng cách bỏ stub không dùng, đặt stub trong test thực sự cần hoặc đối chiếu lại dữ liệu được gọi. `lenient()` chỉ nên dành cho trường hợp có lý do rõ ràng, không phải giải pháp mặc định làm test xanh.

### 14.5. Spy gọi code thật khi stub

`when(spy.method(anyString()))` có thể gọi method thật với giá trị giả của matcher trong quá trình stubbing, gây side effect hoặc lỗi. Với spy, dùng:

```java
doReturn(expected).when(spy)
        .method(anyString());
```

Đây là **mẫu tổng quát**, không phải chương trình độc lập; `spy` và `expected` cần khởi tạo theo kiểu cụ thể. Kết hợp cùng quy tắc matcher nếu `method` có nhiều đối số.

### 14.6. Lỗi Mockito phiên bản, Java hoặc inline mock maker

`ClassNotFoundException`, `NoSuchMethodError`, agent instrumentation warning trên JDK mới hoặc lỗi mock class final có thể liên quan dependency/bytecode tooling. Kiểm tra phiên bản Mockito được Spring Boot BOM quản lý, Byte Buddy, Java thực tế và `testRuntimeClasspath`; không quy mọi lỗi này về `eq`. Số phiên bản và support khác nhau theo dòng Spring Boot; dùng các phiên bản tương thích với build hiện tại.

## 15. Bài tập: sửa các lời gọi sai

Cho interface:

```java
interface TransferGateway {
    boolean transfer(String source, String target, long amount);
}
```

Dưới đây là các đoạn độc lập. Hãy phân loại đúng/sai, giải thích.

### Bài A

```java
when(gateway.transfer("A", anyString(), anyLong()))
        .thenReturn(true);
```

**Sai:** trộn literal `"A"` với hai matcher. Sửa:

```java
when(gateway.transfer(eq("A"), anyString(), anyLong()))
        .thenReturn(true);
```

### Bài B

```java
verify(gateway).transfer("A", "B", 50L);
```

**Đúng:** không dùng matcher nào và kiểm tra ba giá trị cụ thể. Không cần bọc mọi thứ bằng `eq`.

### Bài C

```java
verify(gateway).transfer(eq("A"), eq("B"), anyLong());
```

**Đúng về cú pháp matcher**, nhưng có thể **quá rộng** về hợp đồng. Nếu chuyển đúng 50 là yêu cầu then chốt, dùng `eq(50L)` thay cho `anyLong()`.

### Bài D

```java
when(gateway.transfer(eq("A"), anyString(), 50L))
        .thenReturn(true);
```

**Sai:** `50L` là literal trong lời gọi đã có matcher. Sửa:

```java
when(gateway.transfer(eq("A"), anyString(), eq(50L)))
        .thenReturn(true);
```

### Bài E

```java
String source = eq("A");
boolean done = realGateway.transfer(source, "B", 50L);
```

**Sai về cách dùng matcher:** `eq("A")` không trả dữ liệu dùng trong business code; nó ghi matcher cho Mockito và trả dummy. Hãy truyền `"A"` trực tiếp vào đối tượng thật; không dùng matcher ngoài stubbing/verification.

### Bài F

```java
verify(gateway).transfer(
        eq("A"), eq("B"), longThat(n -> n > 0)
);
```

**Đúng về matcher** và có ý nghĩa nếu contract yêu cầu số tiền dương, không yêu cầu một số tiền cố định. Nếu chuyển 50 mới là đúng, test này chưa đủ mạnh.

### Bài G — `null`

Giả sử `target` có thể null trong một API legacy (không khuyến nghị thiết kế chuyển tiền như vậy):

```java
when(gateway.transfer(eq("A"), anyString(), anyLong()))
        .thenReturn(true);
```

Matcher `anyString()` **không** khớp `null`. Nếu thật sự cần khớp cả null, thay bằng `nullable(String.class)`; nếu chỉ null, dùng `isNull()`. Tuy nhiên trong miền chuyển tiền thật, target null có thể là input bất hợp lệ; phải kiểm thử service từ chối và không phát sinh chuyển tiền thay vì chấp nhận mù quáng.

## 16. Bài tập thực hành trong dự án Spring Boot

### Thực hành 1 — Matcher và ranh giới logic

Dùng hai tệp Java ở mục 6:

1. Chạy toàn bộ `CheckoutServiceTest`.
2. Thay stub trong `allowsNullableNoteWhileKeepingOrderIdExact` từ `nullable(String.class)` sang `anyString()`.
3. Chạy lại: request có note null không còn khớp, `transactionId` không còn là `TX-9`, assertion tương ứng phải đỏ.
4. Khôi phục `nullable(String.class)` và chạy lại.

Học viên phải giải thích được **vì sao** từ một matcher đều là kiểu `String` mà null lại tạo kết quả khác.

### Thực hành 2 — Quy tắc tất cả đối số

Trong một test sandbox, tạm đổi:

```java
when(gateway.charge(
        eq("ORD-42"), anyLong(), nullable(String.class)
)).thenReturn("TX-9");
```

thành:

```java
when(gateway.charge(
        "ORD-42", anyLong(), nullable(String.class)
)).thenReturn("TX-9");
```

Dự đoán `InvalidUseOfMatchersException`. Ghi lại số đối số, số matcher và dòng sửa đúng. Sau đó hoàn nguyên; không giữ test có lỗi cố ý trong CI.

### Thực hành 3 — Chứng minh matcher quá rộng

Sửa tạm `CheckoutService.checkout` để gọi gateway với `amountInVnd = 1L` thay vì số người dùng yêu cầu. So sánh hai verification:

```java
verify(gateway).charge(eq("ORD-42"), anyLong(), isNull());
```

và:

```java
verify(gateway).charge(eq("ORD-42"), eq(120_000L), isNull());
```

Verification thứ nhất có thể vẫn pass, verification thứ hai phải fail. Khôi phục code. Kết luận: matcher phải phản ánh **rủi ro muốn bắt**, không chỉ tiện để viết test.

### Thực hành 4 — Captor thay cho predicate dài

Giả sử service gửi event gồm `orderId`, `customerId`, `amount`, `currency`, `createdAt`. Viết verification dùng `eq("payment.completed")` và `ArgumentCaptor<Event>` ở đối số payload, sau đó assert bốn field nghiệp vụ. Với `createdAt` được tạo động, chỉ so sánh theo contract (hoặc dùng injected `Clock`) thay vì hard-code timestamp.

### Thực hành 5 — Review pull request

Một đồng đội đề xuất:

```java
verify(emailGateway).send(anyString(), anyString(), anyString());
```

Nếu đây là email xác nhận đơn hàng, cần thảo luận ba điều: recipient có phải đúng địa chỉ khách hàng, subject có cần từ khóa hoặc template ID cố định, body có cần đúng order ID? Có thể thay `anyString()` bằng `eq(...)`, `contains(...)`, `argThat(...)` hoặc captor theo contract. Không mặc định mỗi field đều phải exact nếu nội dung được phép thay đổi theo locale/template.

## 17. Checklist khi review matcher trong test Mockito

- [ ] Tôi biết **phương thức mock** nào đang được stub/verify và có bao nhiêu đối số thực.
- [ ] Nếu có ít nhất một matcher, **mọi đối số của cùng lời gọi** đều dùng matcher.
- [ ] Với giá trị cố định đi cùng matcher khác, tôi dùng `eq(...)`.
- [ ] Nếu tất cả giá trị cố định, tôi có thể dùng literal cho dễ đọc.
- [ ] Tôi phân biệt `eq` (giá trị) với `same` (instance).
- [ ] Tôi phân biệt `any()` (có thể khớp null) và matcher có kiểu (`anyString()`, `any(Class)`… thường không khớp null).
- [ ] Tôi dùng `isNull`/`nullable` theo hợp đồng về null.
- [ ] Tôi không truyền giá trị trả về của matcher cho code thật hoặc lưu vào biến dữ liệu.
- [ ] `argThat` có điều kiện thuần, chống null khi cần và không có side effect.
- [ ] Với primitive, tôi dùng matcher primitive thích hợp thay vì vô tình unbox `null`.
- [ ] Với object phức tạp, tôi cân nhắc captor + assertion field thay vì predicate quá dài.
- [ ] Tôi kiểm tra ranh giới quan trọng bằng matcher **đủ hẹp** để bắt lỗi nghiệp vụ.
- [ ] Tôi biết strict stubbing mismatch, missing invocation và `InvalidUseOfMatchersException` là các vấn đề khác nhau.
- [ ] Tôi đã xác minh Mockito/JUnit trên đúng test classpath, đúng module và phiên bản Spring Boot phù hợp.
- [ ] Test có assert output/state quan trọng, không chỉ verify một lời gọi không liên quan contract.

## 18. Tổng kết

Ba nguyên tắc cần nhớ:

**1. Trong một lời gọi được stub hoặc verify: hoặc không dùng matcher nào, hoặc dùng matcher cho tất cả đối số.** Khi cần giữ giá trị cố định giữa các matcher khác, dùng `eq(value)`.

**2. Chọn matcher dựa vào hợp đồng.** `anyLong()` không bảo đảm số tiền dương hay chính xác; `anyString()` không khớp null; `nullable(String.class)` có thể khớp null. `argThat` và captor chỉ nên thêm khi mang lại bằng chứng tốt hơn.

**3. Matcher là cơ chế mô tả lời gọi mock, không phải dữ liệu Java.** Nó ghi nhận điều kiện bên trong Mockito và trả dummy value. Không sử dụng matcher ngoài stubbing/verification, không trộn matcher với literal, và không làm test quá rộng để che lỗi.

## Tài liệu gốc nên tra cứu theo phiên bản Mockito của dự án

- Mockito 5.x, `ArgumentMatchers` JavaDoc (quy tắc tất cả đối số, `eq`, `any`, `nullable`): https://www.javadoc.io/doc/org.mockito/mockito-core/5.21.0/org.mockito/org/mockito/ArgumentMatchers.html
- Mockito 5.x, `ArgumentCaptor` JavaDoc: https://www.javadoc.io/doc/org.mockito/mockito-core/5.21.0/org.mockito/org/mockito/ArgumentCaptor.html
- Mockito 5.x, `Mockito` JavaDoc (stubbing, verification, spy, argument matching): https://www.javadoc.io/doc/org.mockito/mockito-core/5.21.0/org.mockito/org/mockito/Mockito.html
- Mockito JUnit Jupiter extension: https://www.javadoc.io/doc/org.mockito/mockito-junit-jupiter/
- JUnit User Guide: https://docs.junit.org/current/user-guide/
- Spring Boot Testing: https://docs.spring.io/spring-boot/reference/testing/
