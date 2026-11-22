# Mockito: verify, số lần gọi và thứ tự khi hành vi yêu cầu

## 1. Từ kiểm tra kết quả đến kiểm tra tương tác

Với một hàm thuần như cộng hai số, cách kiểm thử trực tiếp nhất là gọi hàm rồi so sánh **giá trị trả về**:

```java
assertEquals(5, calculator.add(2, 3));
```

Nhưng nhiều thao tác trong ứng dụng Spring Boot tạo ra **side effect** qua dependency: gửi lệnh thanh toán, ghi sự kiện audit, phát message, gửi email hoặc gọi một hệ thống bên ngoài. Khi đó, một kết quả trả về đúng chưa chắc đủ chứng minh hành vi đã diễn ra chính xác.

Mockito cung cấp **interaction verification** qua `verify(...)` để trả lời các câu hỏi như:

- Có gọi cổng thanh toán cho đơn hàng hợp lệ không?
- Đã gọi **đúng một lần**, hay vô tình tính tiền hai lần?
- Khi dữ liệu sai, có **không** gọi dịch vụ bên ngoài không?
- Có kiểm tra quyền **trước khi** thực hiện thao tác nhạy cảm không?
- Khi retry gặp lỗi tạm thời, số lần thử có đúng giới hạn và dừng ngay khi thành công không?

**Nguyên tắc quan trọng:** chỉ xác minh tương tác khi *sự tương tác, số lần gọi hoặc thứ tự gọi* là một phần của hành vi cần bảo vệ. Với logic có đầu ra hoặc trạng thái quan sát được, ưu tiên assertion trên kết quả/trạng thái. Lạm dụng `verify` để kiểm tra mọi lời gọi nội bộ sẽ khiến test dễ vỡ khi refactor dù hành vi bên ngoài không đổi.

Ví dụ: “Không được tính tiền hai lần” là hợp đồng quan trọng, vì vậy `verify(paymentGateway, times(1)).charge(...)` có giá trị. Ngược lại, việc service gọi một hàm getter nội bộ một hay hai lần hiếm khi là hợp đồng nghiệp vụ.

### Các vai trò khác nhau

| Thành phần | Vai trò | Nó chứng minh điều gì? |
| --- | --- | --- |
| JUnit Jupiter `@Test`, assertion | Chạy test và so sánh kỳ vọng | Kết quả, trạng thái, exception |
| Mockito `@Mock` và `when(...).thenReturn(...)` | Tạo collaborator giả và định nghĩa phản hồi | Điều kiện đầu vào để kiểm thử service |
| Mockito `verify(...)` | Quan sát lời gọi đã ghi nhận trên mock | Có gọi, gọi với tham số gì, số lần bao nhiêu |
| Mockito `InOrder` | Kiểm tra thứ tự giữa các lời gọi cần có | A xảy ra trước B theo hợp đồng test |
| Spring Boot Test | Dựng Spring context hoặc test slice khi cần | Wiring/framework behavior; không tự thay thế Mockito assertions |

Test Java thuần dùng Mockito **không cần** `@SpringBootTest`. Nếu muốn xác minh một Spring bean đã được mock trong context, dùng cơ chế tạo hoặc thay bean phù hợp phiên bản Spring Boot; phần cuối bài phân biệt rõ điều này.

## 2. Cơ chế của `verify`: Mockito ghi nhận invocation

Mock là object do Mockito tạo ra. Khi code đang kiểm thử gọi một phương thức trên mock, Mockito lưu **invocation**: đối tượng, tên phương thức, đối số, thứ tự tương đối và thông tin liên quan. Sau khi thực thi hành vi thật của service, test dùng `verify` để kiểm tra những invocation đó.

```text
Arrange:
  Tạo mock PaymentGateway
  Cấu hình phản hồi nếu cần: when(gateway.charge(...)).thenReturn(...)

Act:
  checkoutService.checkout(orderId)
      └── paymentGateway.charge(orderId, amount)
          Mockito ghi nhận invocation

Assert / Verify:
  assertTrue(result)
  verify(paymentGateway, times(1)).charge(orderId, amount)
      └── Mockito tìm invocation đã ghi; sai kỳ vọng → test FAIL
```

`verify(mock).method(...)` **không có nghĩa là gọi method một lần nữa**. Đây là cú pháp để Mockito so sánh expectation với các invocation đã ghi nhận. Vì vậy test phải chạy **Act trước Verify**.

Một invocation có thể được kiểm tra về cả **đối số** lẫn **số lần**. Stubbing và verification là hai việc khác nhau:

- `when(gateway.charge(...)).thenReturn("tx-1")`: quy định mock sẽ trả về gì nếu có lời gọi tương ứng.
- `verify(gateway).charge(...)`: kiểm tra lời gọi có thật sự xảy ra hay không.
- Stubbing không tự bảo đảm service đã gọi dependency; verification không tự bảo đảm giá trị trả về hoặc trạng thái cuối cùng đúng.
- `assertEquals(...)` vẫn cần khi nghiệp vụ có kết quả quan sát được.

Nếu gọi `verify` trên object thật không phải mock/spy, Mockito sẽ báo sử dụng sai đối tượng. Nếu service đang giữ **instance khác** với mock được test verify, test cũng không thể suy diễn rằng lời gọi trên instance thật đã được ghi lại.

## 3. Cú pháp `verify` và các VerificationMode

API cơ bản:

```java
verify(mock).method(expectedArgument);
verify(mock, times(1)).method(expectedArgument);
```

Hai dòng là **hai cách tương đương** để kiểm tra method được gọi đúng một lần với đối số khớp. Trong test thực tế thường chỉ dùng **một** trong hai, không cần lặp verification giống nhau.

| Cú pháp | Điều kiện để PASS | Khi nào dùng |
| --- | --- | --- |
| `verify(mock).send("id")` | Có đúng **1** invocation phù hợp | Một lần gọi là hợp đồng |
| `verify(mock, times(2)).send("id")` | Có đúng **2** invocation phù hợp | Retry/2 giai đoạn được thiết kế |
| `verify(mock, times(0)).send("id")` | Không có invocation phù hợp | Chặn side effect |
| `verify(mock, never()).send("id")` | Tương đương `times(0)` | Diễn đạt rõ “không được gọi” |
| `verify(mock, atLeastOnce()).send("id")` | Có **ít nhất 1** invocation phù hợp | “Đã từng xảy ra” là đủ |
| `verify(mock, atLeast(2)).send("id")` | Có **tối thiểu 2** invocation phù hợp | Số lần tối thiểu quan trọng |
| `verify(mock, atMost(3)).send("id")` | Có **tối đa 3** invocation phù hợp, kể cả **0** | Giới hạn trên, đi kèm kiểm tra hành vi cần xảy ra |
| `verify(mock, only()).send("id")` | Invocation này là **interaction duy nhất** trên mock | Mock tuyệt đối không được có tương tác khác |
| `verifyNoInteractions(mock)` | Không có bất kỳ interaction nào trên mock | Đường đi lỗi không đụng dependency |
| `verifyNoMoreInteractions(mock)` | Không còn invocation **chưa được verify** trên mock | Khi test thực sự cần hợp đồng không có thêm tương tác |

Dấu `...` trong bảng đại diện cho đối số thực, không phải ký hiệu Java để copy nguyên văn. Trong file Java cần import static:

```java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.atLeast;
import static org.mockito.Mockito.atMost;
import static org.mockito.Mockito.only;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
```

### `times(1)` khác `atLeastOnce()` như thế nào?

Giả sử một bug khiến cổng thanh toán bị gọi hai lần:

- `verify(gateway, times(1)).charge(...)` → **FAIL**, phát hiện rủi ro tính tiền hai lần.
- `verify(gateway, atLeastOnce()).charge(...)` → **PASS**, bởi hai lần cũng là “ít nhất một lần”.

Nếu “exactly once” quan trọng, phải chọn `times(1)`. Dùng `atLeastOnce()` để làm test qua dễ dàng có thể làm yếu hợp đồng nghiệp vụ.

### `atMost(3)` không chứng minh đã gọi lần nào

Nếu mock chưa được gọi, `verify(mock, atMost(3)).send(...)` vẫn PASS. Muốn diễn đạt “ít nhất một lần, nhiều nhất ba lần”:

```java
verify(mock, atLeastOnce()).send("event-1");
verify(mock, atMost(3)).send("event-1");
```

Đoạn trên là **mẫu áp dụng** với biến `mock` được khai báo trước; không phải class Java độc lập. Trong nghiệp vụ retry cố định, kiểm tra `times(expectedAttempts)` rõ ràng hơn một khoảng lỏng.

### `never()` theo đối số và `verifyNoInteractions()` theo cả mock

```java
verify(gateway, never()).charge("invalid-order", 2000);
```

Điều này chỉ cấm lời gọi `charge("invalid-order", 2000)`. Nó **không** chứng minh gateway chưa bị gọi với đối số khác. Nếu đường đi lỗi không được gọi gateway dưới **bất kỳ** tham số nào, dùng:

```java
verifyNoInteractions(gateway);
```

Chọn cấp độ khẳng định phù hợp: “không tính tiền cho mã đơn hàng này” khác với “không được tương tác với hệ thống thanh toán”.

## 4. Dự án mẫu Java 17+ với JUnit Jupiter và Mockito

Các ví dụ hoàn chỉnh dưới đây dùng Gradle Java, JUnit Jupiter và MockitoExtension; không cần server Spring Boot hoặc database. Điều kiện: **JDK 17+**, Gradle tương thích và có kết nối tới Maven Central trong lần tải dependency đầu tiên. Các phiên bản chỉ minh họa một cấu hình tương thích cụ thể, không được khẳng định là bản mới nhất.

Cấu trúc thư mục:

```text
mockito-verification-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/com/example/testing/
    ├── CheckoutWorkflowTest.java
    └── RetrySenderTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'mockito-verification-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'org.mockito:mockito-junit-jupiter:5.15.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Nếu dự án có Gradle Wrapper, chạy `./gradlew test` trên Linux/macOS hoặc `gradlew.bat test` trên Windows. Nếu chưa có Wrapper và máy đã cài Gradle, dùng `gradle test`. `mockito-junit-jupiter` hỗ trợ `@ExtendWith(MockitoExtension.class)`; nó kéo các thư viện Mockito cần thiết và không bắt buộc Spring context.

Trong **ứng dụng Spring Boot đã cấu hình quản lý dependency**, `spring-boot-starter-test` thường cung cấp JUnit và Mockito. Khi thêm test mới vào Boot project, dùng BOM của Boot hiện có, tránh ép các phiên bản khác chỉ để học `verify`.

## 5. Ví dụ hoàn chỉnh: xác minh đúng một lần và thứ tự nghiệp vụ

Bài toán: xử lý một đơn hàng theo quy tắc sau:

1. Kiểm tra số tiền phải dương.
2. Gọi cổng phê duyệt đơn hàng.
3. Chỉ khi được phê duyệt mới gọi gateway tính tiền.
4. Chỉ sau khi gateway trả về transaction ID mới gửi biên nhận.
5. Với đơn bị từ chối hoặc số tiền sai, **không** được tính tiền hay gửi biên nhận.

Hợp đồng này có **thứ tự** và **side effect** thực sự quan trọng. Ta tạo ba interface đại diện dependency và một class Java service nhỏ. Mockito mock ba interface; service là object thật.

`src/test/java/com/example/testing/CheckoutWorkflowTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutWorkflowTest {

    interface ApprovalService {
        boolean isApproved(String orderId);
    }

    interface PaymentGateway {
        String charge(String orderId, int amountInCents);
    }

    interface ReceiptSender {
        void send(String orderId, String transactionId);
    }

    static final class CheckoutWorkflow {
        private final ApprovalService approval;
        private final PaymentGateway payment;
        private final ReceiptSender receipts;

        CheckoutWorkflow(
                ApprovalService approval,
                PaymentGateway payment,
                ReceiptSender receipts) {
            this.approval = approval;
            this.payment = payment;
            this.receipts = receipts;
        }

        boolean execute(String orderId, int amountInCents) {
            if (amountInCents <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }

            if (!approval.isApproved(orderId)) {
                return false;
            }

            String transactionId =
                    payment.charge(orderId, amountInCents);
            receipts.send(orderId, transactionId);
            return true;
        }
    }

    @Mock
    ApprovalService approval;

    @Mock
    PaymentGateway payment;

    @Mock
    ReceiptSender receipts;

    private CheckoutWorkflow workflow() {
        return new CheckoutWorkflow(approval, payment, receipts);
    }

    @Test
    void approvedOrderChargesOnceBeforeSendingReceipt() {
        // Arrange
        when(approval.isApproved("order-1")).thenReturn(true);
        when(payment.charge("order-1", 2500)).thenReturn("tx-99");

        // Act
        boolean accepted = workflow().execute("order-1", 2500);

        // Assert trạng thái/đầu ra
        assertTrue(accepted);

        // Verify đúng một lần, đúng tham số
        verify(approval, times(1)).isApproved("order-1");
        verify(payment, times(1)).charge("order-1", 2500);
        verify(receipts, times(1)).send("order-1", "tx-99");

        // Verify thứ tự là hợp đồng: approve -> charge -> receipt
        InOrder order = inOrder(approval, payment, receipts);
        order.verify(approval).isApproved("order-1");
        order.verify(payment).charge("order-1", 2500);
        order.verify(receipts).send("order-1", "tx-99");

        // Hợp đồng còn đòi không gọi thêm thao tác nào.
        verifyNoMoreInteractions(approval, payment, receipts);
    }

    @Test
    void rejectedOrderNeverChargesOrSendsReceipt() {
        when(approval.isApproved("order-2")).thenReturn(false);

        boolean accepted = workflow().execute("order-2", 2500);

        assertFalse(accepted);
        verify(approval).isApproved("order-2");
        verifyNoInteractions(payment, receipts);
    }

    @Test
    void invalidAmountDoesNotCallAnyDependency() {
        assertThrows(
                IllegalArgumentException.class,
                () -> workflow().execute("order-3", 0)
        );

        verifyNoInteractions(approval, payment, receipts);
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.testing.CheckoutWorkflowTest'
```

**Kết quả kỳ vọng: 3 test PASS.** Không có stdout cố định trong test. Gradle có thể hiển thị tên các test PASS theo cấu hình `testLogging`; báo cáo HTML mặc định ở `build/reports/tests/test/index.html`.

### Vì sao test đầu kiểm tra cả giá trị, số lần và thứ tự?

- `assertTrue(accepted)` xác nhận service trả về “đơn được chấp nhận”.
- `verify(..., times(1))` xác nhận mỗi side effect được thực hiện **chính xác một lần**.
- `InOrder` xác nhận approval xảy ra trước charge, và charge trước receipt.
- `verifyNoMoreInteractions(...)` kiểm tra không còn tương tác chưa được xác minh trên ba mock. Sử dụng ở đây có chủ đích vì hợp đồng quy định không được phát sinh tương tác khác.

Trong một service thực, có thể có thêm logging, metrics hoặc các lời gọi phụ không thuộc hợp đồng test. Khi đó việc kiểm tra **mọi tương tác** là quá khắt khe; chỉ giữ verification quan trọng, và tránh `verifyNoMoreInteractions` nếu thay đổi nội bộ hợp lệ không nên làm test FAIL.

### Vì sao test thứ hai không cần InOrder?

Khi approval trả `false`, chỉ cần chứng minh kết quả bị từ chối và **payment/receipt không bị gọi**. Với hai mock không có tương tác, thứ tự không có ý nghĩa. Viết thêm `InOrder` ở đây không tạo bằng chứng mới.

### Vì sao test thứ ba dùng `verifyNoInteractions`?

Dữ liệu sai phải bị chặn **trước khi chạm bất kỳ hệ thống bên ngoài nào**. Đây là một negative contract quan trọng, và `verifyNoInteractions(approval, payment, receipts)` diễn đạt chính xác hơn việc verify từng method cụ thể với `never()`.

## 6. `InOrder`: xác minh thứ tự khi thứ tự là hợp đồng

Mockito không mặc nhiên quan tâm thứ tự gọi khi dùng `verify` thường:

```java
verify(payment).charge("order-1", 2500);
verify(receipts).send("order-1", "tx-99");
```

Hai lời verify trên **chỉ nói rằng cả hai đã xảy ra**. Nếu service gửi biên nhận trước khi tính tiền, hai câu lệnh vẫn có thể PASS nếu chúng đều được gọi một lần.

Khi cần đảm bảo “tính tiền xong mới gửi biên nhận”, dùng:

```java
InOrder order = inOrder(payment, receipts);
order.verify(payment).charge("order-1", 2500);
order.verify(receipts).send("order-1", "tx-99");
```

Đây là **đoạn trích** từ class ở mục 5, không phải ví dụ độc lập. `InOrder` theo dõi thứ tự thực tế của các invocation trên **những mock được truyền cho nó**. Lời gọi tới collaborator không nằm trong danh sách đó không tự được xét.

### Thứ tự tương đối khác với “không có lời gọi xen giữa”

Hai verification liên tiếp bằng `InOrder` không khẳng định hai lời gọi ở sát nhau theo thời gian. Một lời gọi audit hoặc log có thể xen giữa mà hợp đồng vẫn giữ nguyên:

```text
approved(order) → audit("approved") → charge(order) → audit("charged")
                → sendReceipt(order)
```

Nếu chỉ quan tâm `approved < charge < sendReceipt`, không nên bắt test thất bại chỉ vì service thêm audit. Cần chọn **những interaction có ý nghĩa nghiệp vụ**.

### `InOrder.verifyNoMoreInteractions()` có giới hạn quan trọng

Trong một `InOrder`, `verifyNoMoreInteractions()` chủ yếu kiểm tra không có invocation chưa được verify **sau invocation cuối cùng đã verify** trong thứ tự đó. Nó không tương đương hoàn toàn với `Mockito.verifyNoMoreInteractions(mock1, mock2)`, vốn kiểm tra mọi invocation chưa được verify trên các mock.

Ví dụ nếu trước lời gọi đầu tiên đã có một invocation không được verify, `InOrder.verifyNoMoreInteractions()` có thể không phát hiện nó. Khi yêu cầu là **không có interaction nào khác ở bất kỳ vị trí nào**, dùng `verifyNoMoreInteractions(mock1, mock2, ...)` sau những lời verify cần thiết, như ví dụ checkout ở mục 5.

Không cần máy móc gắn cả hai kiểu `verifyNoMoreInteractions` vào tất cả test. Chúng phục vụ những hợp đồng kiểm tra khác nhau và có thể làm test quá phụ thuộc implementation.

### Có bắt buộc gọi theo đúng thứ tự khai báo trong test không?

`verify` thường có thể đặt theo thứ tự tiện đọc, không phụ thuộc thứ tự các method được service gọi. Chỉ khi dùng `InOrder` thì thứ tự verification mới là kỳ vọng có ý nghĩa.

Ví dụ một test assert `verify(receipts)` trước `verify(payment)` **không** có nghĩa là Mockito yêu cầu gửi biên nhận trước khi tính tiền. Đó chỉ là thứ tự các câu lệnh verify trong mã test.

## 7. Số lần gọi với retry: chọn `times(n)` theo hành vi

Giả sử hệ thống gửi một event đến message gateway. Khi gateway ném lỗi tạm thời, service thử lại với tối đa **3 lần**; nếu thành công ở lần đầu, không gửi thêm. Đây là nơi số lần gọi thực sự là một phần của contract.

Ví dụ đầy đủ sau dùng một exception riêng để mô tả lỗi retryable; không cần network hay broker thật.

`src/test/java/com/example/testing/RetrySenderTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;

@ExtendWith(MockitoExtension.class)
class RetrySenderTest {

    interface MessageGateway {
        void publish(String eventId);
    }

    static final class TransientFailure extends RuntimeException {
    }

    static final class RetrySender {
        private final MessageGateway gateway;

        RetrySender(MessageGateway gateway) {
            this.gateway = gateway;
        }

        void publishWithRetry(String eventId) {
            for (int attempt = 1; attempt <= 3; attempt++) {
                try {
                    gateway.publish(eventId);
                    return; // Thành công thì dừng ngay.
                } catch (TransientFailure ex) {
                    if (attempt == 3) {
                        throw ex;
                    }
                }
            }
        }
    }

    @Mock
    MessageGateway gateway;

    @Test
    void retriesTwiceThenSucceedsOnThirdAttempt() {
        doThrow(new TransientFailure())
                .doThrow(new TransientFailure())
                .doNothing()
                .when(gateway).publish("event-1");

        new RetrySender(gateway).publishWithRetry("event-1");

        verify(gateway, times(3)).publish("event-1");
        verifyNoMoreInteractions(gateway);
    }

    @Test
    void successfulFirstAttemptDoesNotRetry() {
        new RetrySender(gateway).publishWithRetry("event-2");

        verify(gateway, times(1)).publish("event-2");
        verifyNoMoreInteractions(gateway);
    }

    @Test
    void failsAfterAtMostThreeAttempts() {
        doThrow(new TransientFailure())
                .when(gateway).publish("event-3");

        assertThrows(
                TransientFailure.class,
                () -> new RetrySender(gateway)
                        .publishWithRetry("event-3")
        );

        verify(gateway, times(3)).publish("event-3");
    }
}
```

Chạy:

```bash
./gradlew test --tests 'com.example.testing.RetrySenderTest'
```

**Kết quả kỳ vọng: 3 test PASS.** Cộng với ba test ở phần checkout, bộ ví dụ có tổng cộng **6 test PASS** khi chạy `./gradlew test`.

Giải thích:

- Test 1 dùng `doThrow(...).doThrow(...).doNothing().when(gateway).publish(...)` để mô phỏng lần 1 và 2 bị lỗi tạm thời, lần 3 thành công. Lệnh `verify(..., times(3))` chứng minh đúng ba attempt.
- Test 2 không cấu hình phản hồi: void method trên Mockito mock mặc định không làm gì và không ném exception, nên service dừng sau **một lần**. Điều này bảo vệ quy tắc “thành công thì không retry”.
- Test 3 cho mock ném cùng loại exception ở mọi lần gọi, xác nhận exception được truyền ra ngoài khi vượt số lần thử, đồng thời kiểm tra đúng ba attempt.

**Chú ý:** dùng `times(3)` ở test 3 mạnh hơn `atMost(3)` vì nó bảo vệ cả việc service không bỏ cuộc quá sớm. Nếu hợp đồng chỉ yêu cầu tối đa ba lần nhưng cho phép dừng tùy điều kiện, assertion cần phản ánh đúng chính sách đã duyệt.

### Có nên verify từng lần retry bằng `InOrder`?

Nếu ba attempt đều là **cùng một method và cùng một đối số**, số lần được verify bằng `times(3)` đã đủ cho phần lớn test retry. Thứ tự các attempt cùng loại là điều hiển nhiên do invocation được ghi theo thời gian; `InOrder` chỉ hữu ích thêm khi mỗi lần thử phải xen giữa các thao tác khác theo hợp đồng, ví dụ audit "retrying", tăng backoff hoặc refresh token trước lần gọi kế tiếp.

Không nên gắn số lần gọi cố định vào một thuật toán có jitter, parallel request hoặc caching nếu contract thực sự không hứa hẹn con số đó. Với xử lý bất đồng bộ, cần đợi đến trạng thái hoàn thành trước khi verify hoặc dùng API timeout phù hợp ở phần sau.

## 8. Xác minh đối số: không chỉ đếm lời gọi

Một verification phải khớp **method và argument**. Đếm đúng một lần nhưng sai `orderId` hoặc sai số tiền vẫn có thể là lỗi nghiêm trọng.

### 8.1. Đối số chính xác

```java
verify(payment).charge("order-1", 2500);
```

Phù hợp khi contract quy định rõ đối số, như ID và số tiền tính bằng cents.

### 8.2. Argument matcher

Trong tình huống chỉ một số thuộc tính quan trọng:

```java
verify(payment).charge(
        eq("order-1"),
        intThat(amount -> amount > 0)
);
```

Đây là **đoạn minh họa** cần mock `payment` và import `org.mockito.ArgumentMatchers.eq`, `intThat`. Khi đã dùng matcher cho một đối số của một invocation, các đối số còn lại cũng phải dùng matcher, ví dụ `eq(...)`; không trộn `eq("order-1")` với literal `2500` trong cùng lời gọi. Mockito sẽ ném `InvalidUseOfMatchersException` nếu trộn không đúng.

Đừng dùng `any()` cho toàn bộ đối số chỉ để test PASS. Nếu mã đơn hàng, giá trị tiền hoặc người nhận có ý nghĩa nghiệp vụ, verify nên kiểm tra cụ thể.

### 8.3. ArgumentCaptor để kiểm tra dữ liệu thực sự được gửi đi

Khi message phức tạp, chỉ so sánh một thuộc tính bằng captor có thể rõ ràng hơn việc so sánh toàn bộ object. Giả sử:

```java
interface NotificationGateway {
    void publish(String destination, String payload);
}
```

Đoạn dưới đây áp dụng **sau khi service thật đã gọi mock `notifications`**, không phải chương trình độc lập:

```java
ArgumentCaptor<String> payload =
        ArgumentCaptor.forClass(String.class);

verify(notifications, times(1))
        .publish(eq("orders"), payload.capture());

assertTrue(payload.getValue().contains("order-1"));
```

Cần import `org.mockito.ArgumentCaptor`, matcher `eq` và assertion JUnit tương ứng. Nếu method được gọi nhiều lần, `capture()` với verification `times(n)` và `getAllValues()` giúp kiểm tra các giá trị theo thứ tự được ghi nhận. Khi cần so sánh một object phức tạp, cân nhắc equality theo contract hoặc AssertJ recursive comparison thay vì verify quá nhiều method của object.

**Quan trọng:** Captor/matcher giúp kiểm tra đúng dữ liệu đã gửi; chúng không thay thế việc kiểm tra số lần và thứ tự nếu những yêu cầu đó cũng thuộc hợp đồng.

## 9. Hai kiểu negative verification: `never` và không tương tác

Tình huống xác nhận không có side effect thường quan trọng hơn chỉ xác nhận đường đi thành công:

- Input thiếu quyền → không gọi payment gateway.
- Dữ liệu validation lỗi → không publish event.
- Khách hàng chưa đồng ý → không gửi thông báo.
- Retry đã thành công → không gửi tiếp.
- Không tìm thấy đối tượng → không gọi bước tiếp theo.

Chọn biểu thức theo mức độ cam kết:

```java
verify(payment, never()).charge("order-9", 1000);
```

Cấm **một lời gọi cụ thể**; nếu service gọi `charge("order-10", 1000)` thì câu verify vẫn PASS.

```java
verifyNoInteractions(payment);
```

Cấm **mọi tương tác trên payment mock**. Chỉ dùng nếu việc gọi bất kỳ method nào trên collaborator này đều bị cấm trong đường đi đó.

```java
verify(payment).charge("order-1", 1000);
verifyNoMoreInteractions(payment);
```

Yêu cầu có **một interaction đã verify**, và không còn tương tác chưa được verify nào khác. Đây khác với `verifyNoInteractions`: mock đã được gọi một lần nên `verifyNoInteractions(payment)` sẽ FAIL.

Một test không thể chứng minh “toàn ứng dụng không phát sinh side effect” chỉ bằng `verifyNoInteractions` trên một mock: nó chỉ quan sát **các mock mà test kiểm soát**. Hành vi của object thật, hệ thống ngoài hoặc dependency khác cần test phù hợp.

### Không dùng `verifyNoMoreInteractions` mặc định

Mẫu sau thường làm test giòn:

```java
verify(repository).save(order);
verifyNoMoreInteractions(repository, auditLogger, metrics);
```

Nếu contract chỉ cần “đã lưu order đúng”, một lời gọi metrics mới hoặc tìm thêm dữ liệu hợp lệ có thể khiến test FAIL không đáng. Ngược lại, nếu contract là “không được gọi cổng tính tiền lần thứ hai” thì nên verify đúng phương thức đó với `times(1)` hoặc kiểm tra mock tương ứng có đúng các interaction được cho phép.

Dùng negative verification có chủ đích khi cần **ngăn hành vi có hại** hoặc **bảo vệ invariant**.

## 10. Mockito trong Spring Boot: verify trên đúng mock được inject

Trong ứng dụng Spring Boot, câu hỏi cốt lõi không thay đổi: **service đang sử dụng mock nào?**

### 10.1. Test thuần không dùng Spring context

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock
    PaymentGateway gateway;

    @Test
    void chargesOnce() {
        OrderService service = new OrderService(gateway);

        service.checkout("order-1");

        verify(gateway, times(1)).charge("order-1");
    }
}
```

Đây là **đoạn minh họa gắn với OrderService/PaymentGateway có sẵn**, không phải mã độc lập. Cần điều chỉnh chữ ký method theo contract thực tế. Cách này kiểm tra Java object được dựng trực tiếp, không nạp Spring context, phù hợp với unit test.

### 10.2. Test một Spring bean thật với mock bean

Trong **Spring Boot 3.3.x**, có thể dùng `@MockBean` để thay Spring bean trong test context:

```java
@SpringBootTest
class OrderServiceSpringTest {
    @Autowired
    OrderService orderService;

    @MockBean
    PaymentGateway paymentGateway;

    @Test
    void callsGatewayOnce() {
        orderService.checkout("order-1");

        verify(paymentGateway, times(1)).charge("order-1");
    }
}
```

Đây cũng là **đoạn tích hợp vào ứng dụng có sẵn**. Cần import `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.boot.test.mock.mockito.MockBean`, JUnit `@Test` và các method Mockito; chữ ký gateway chỉ minh họa. Test có thể cần stubbing và cấu hình khác để service đi qua nhánh thanh toán.

Trong Boot 3.3.x, `@MockBean` tạo/thay bean trong Spring context để bean service thực sự sử dụng Mockito mock. `@Mock` trong một test Spring **không tự động** thay bean chỉ vì field có cùng type. Với Spring Framework 6.2 / Spring Boot 3.4 trở lên, `@MockitoBean` là API thay thế mới; dùng annotation đúng phiên bản dự án.

### 10.3. Controller slice

`@WebMvcTest` kết hợp MockMvc và mock bean của service thường phù hợp để kiểm tra mapping, status, JSON và xác minh controller đã gọi service đúng đầu vào. Nhưng không nên dùng verify service quá chi tiết nếu HTTP response đã chứng minh đủ; một HTTP test không cần kiểm tra mọi method nội bộ của controller.

### 10.4. Mockito strict stubbing không phải verification count

`MockitoExtension` có thể phát hiện stubbing không dùng hoặc stub có vấn đề với strictness mặc định. Đây là **cơ chế chất lượng cấu hình mock**, khác với kiểm tra `verify(mock, times(...))`. Đừng hiểu việc không xuất hiện `UnnecessaryStubbingException` là đã bảo đảm side effect xảy ra đúng số lần.

## 11. Những lỗi Mockito verification dễ gặp

### 11.1. Verify trước khi hành vi xảy ra

**Sai về thứ tự logic:**

```java
verify(gateway).charge("order-1", 2500);
service.checkout("order-1");
```

Mockito chưa có invocation để đối chiếu ở bước verify. Cấu trúc đúng: **Arrange → Act → Assert/Verify**.

### 11.2. Verify nhầm mock hoặc sai instance

```java
PaymentGateway mockGateway = mock(PaymentGateway.class);
OrderService service = new OrderService(new RealPaymentGateway());

service.checkout("order-1");
verify(mockGateway).charge("order-1");
```

Đây là **phản ví dụ minh họa** giả định các class đã tồn tại. Nếu service dùng instance thật khác mock, lời verify sẽ FAIL và test có thể vô tình thực hiện side effect thật. Hãy inject chính mock mà test cần quan sát, hoặc dùng Spring mock bean để thay dependency trong context.

### 11.3. Chỉ kiểm tra có gọi, bỏ quên gọi trùng

`verify(mock, atLeastOnce()).send(...)` cho phép gửi nhiều lần. Khi hợp đồng là “gửi chính xác một lần”, phải dùng `verify(mock, times(1))`. Đây đặc biệt quan trọng với thanh toán, tạo đơn hàng, phát sự kiện trùng hoặc gửi email không được lặp.

### 11.4. Chỉ kiểm tra số lần mà bỏ qua tham số

`verify(payment, times(1)).charge(anyString(), anyInt())` có thể PASS khi method bị gọi cho sai đơn hoặc sai số tiền. Chỉ nới matcher ở những thuộc tính thật sự không quan trọng. Cần kiểm tra trường dữ liệu nghiệp vụ tương ứng.

### 11.5. Dùng `InOrder` cho chi tiết không thuộc hợp đồng

Một service có thể kiểm tra cache rồi đọc repository, hoặc đọc repository rồi cập nhật cache, nhưng cả hai đều trả kết quả đúng. Nếu thứ tự đó không ảnh hưởng nghiệp vụ, `InOrder` làm test quá phụ thuộc implementation. Chỉ verify order cho ràng buộc thực sự: authorize trước charge, persist trước publish khi giao dịch yêu cầu, hoặc release resource sau use.

### 11.6. Nhầm “cùng số lần” với “đúng thứ tự”

`verify(a).first()` và `verify(b).second()` không chứng minh `first` đi trước `second`. Muốn kiểm tra trình tự, tạo `InOrder(a, b)` qua `inOrder(a, b)` rồi verify tuần tự.

### 11.7. Hiểu nhầm `verifyNoMoreInteractions`

Sau khi verify một method, `verifyNoMoreInteractions(mock)` sẽ FAIL nếu mock có lời gọi khác chưa được verify, kể cả lời gọi hợp lệ mà test không quan tâm. Không sửa bằng cách thêm verify cho mọi lời gọi vô nghĩa; trước hết xác định hợp đồng có thực sự cấm các interaction đó không.

### 11.8. Stub không dùng bị báo lỗi

MockitoExtension có thể ném `UnnecessaryStubbingException` khi test setup một stub nhưng nhánh được kiểm thử không dùng nó. Đây không phải lỗi `verify`; cách xử lý thường là bỏ stub hoặc chuyển stubbing vào đúng test cần nó. Tránh `lenient()` đại trà.

### 11.9. Verify trên spy có thể gây tác dụng thật ngoài ý muốn

Spy bọc object thật nên các method không được stub có thể chạy logic thật khi được gọi. `verify(spy).method(...)` kiểm tra invocation đã ghi, nhưng việc **Act** trước đó có thể đã chạy DB/network nếu spy tham chiếu collaborator thật. Ngoài ra, `when(spy.method()).thenReturn(...)` có thể gọi method thật trong quá trình stubbing; với spy thường cân nhắc `doReturn(...).when(spy).method()`. Unit test nên ưu tiên mock collaborator và dùng object thật cho class đang kiểm thử.

### 11.10. Static method và constructor không phải mock thông thường

`verify(mock)` dùng cho invocation trên mock/spy instance. Mockito cũng có API scoped mocking cho static/construction với `MockedStatic`/`MockedConstruction` trong những trường hợp phù hợp, nhưng cơ chế khác và cần đóng scope đúng cách. Không cố verify một lời gọi static trên object thường bằng `verify(mock)`. Ưu tiên DI để dependency kiểm thử dễ kiểm soát khi thiết kế ứng dụng cho phép.

### 11.11. Không đồng bộ: verify quá sớm

Một service có thể trả về trước khi worker thread gửi event. Gọi `verify(mock)` ngay sau đó có thể FAIL dù event được gửi sau vài mili giây. Mockito có verification mode như `timeout(millis)`:

```java
verify(events, timeout(1000).times(1)).publish("order-1");
```

Đây là **đoạn minh họa** cần một mock `events` và import `org.mockito.Mockito.timeout`. Nó đợi tới khi điều kiện đạt được trong giới hạn thời gian, nhưng không chứng minh không có lời gọi đến muộn **sau** thời điểm kiểm tra đã thành công. Với hành vi bất đồng bộ, giải pháp ổn định hơn thường là **đợi completion signal/`Future`/`CompletableFuture` của tác vụ** rồi verify; tránh `Thread.sleep(...)` cố định và test flaky. Nếu hợp đồng yêu cầu không có lời gọi bổ sung sau cả quá trình, chờ quá trình thật sự kết thúc trước `times(1)`.

### 11.12. Đọc sai thông báo lỗi

Những thông báo Mockito thường gặp:

| Dấu hiệu | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `Wanted but not invoked` | Không có invocation khớp | Object mock đã được inject đúng chưa? Có đi qua nhánh gọi không? |
| `TooManyActualInvocations` | Số lần thực tế vượt kỳ vọng | Retry/loop/double request có hợp lệ không? |
| `TooFewActualInvocations` | Số lần thực tế thấp hơn kỳ vọng | Có early return/exception hoặc chưa await async không? |
| `ArgumentsAreDifferent` | Có lời gọi nhưng đối số không đúng | Kiểm tra ID, amount, matcher, transform input |
| `VerificationInOrderFailure` | Thứ tự không khớp kỳ vọng | Thứ tự nào là contract, thứ tự nào chỉ là implementation? |
| `NoInteractionsWanted` | Có interaction chưa được cho phép | Có dùng `verifyNoMoreInteractions` quá chặt không? |
| `UnnecessaryStubbingException` | Stub không được dùng | Xóa stubbing thừa hoặc sửa nhánh test |

Tên exception/thông báo cụ thể có thể khác theo phiên bản Mockito và tình huống. Đọc **wanted invocation**, **actual invocation** và vị trí lời gọi trong stack trace để xác định nguyên nhân, thay vì chỉ sửa câu verify cho PASS.

## 12. Thiết kế test ít giòn: xác minh cái gì?

Xem ba cách kiểm tra một nghiệp vụ “đơn được duyệt thì tính tiền một lần và gửi biên nhận”:

**Kiểm tra không đủ:**

```java
assertTrue(workflow.execute("order-1", 2500));
```

Trạng thái thành công không đảm bảo không charge hai lần hay không gửi receipt trước charge.

**Kiểm tra đúng hợp đồng:**

```java
assertTrue(workflow.execute("order-1", 2500));
verify(payment, times(1)).charge("order-1", 2500);

InOrder order = inOrder(payment, receipts);
order.verify(payment).charge("order-1", 2500);
order.verify(receipts).send("order-1", "tx-99");
```

Đây là **đoạn minh họa rút gọn**: giả định đã tạo/stub mock và workflow theo ví dụ hoàn chỉnh. Nó kiểm tra giá trị, đúng một lần và trình tự có ý nghĩa.

**Kiểm tra quá chi tiết:**

```java
verify(logger).debug("starting");
verify(cache).get("order-1");
verify(orderRepository).findById("order-1");
verify(metrics).increment("approved");
verify(payment).charge("order-1", 2500);
verify(logger).debug("done");
verifyNoMoreInteractions(logger, cache, orderRepository, metrics, payment);
```

Đây là **phản ví dụ** để nhận diện verification giòn; các mock và service không nằm trong project chạy độc lập. Thêm cache, đổi log hoặc cải tiến metrics có thể làm test FAIL dù hành vi thanh toán không đổi. Nếu những tương tác đó không có yêu cầu nghiệp vụ độc lập, đừng khóa chặt thứ tự/số lần của chúng.

### Ma trận quyết định nhanh

| Bản chất yêu cầu | Assertion/verification nên ưu tiên |
| --- | --- |
| “Tổng tiền đúng” | `assertEquals(expected, actual)` |
| “Input lỗi phải bị từ chối” | `assertThrows(...)` và nếu cần `verifyNoInteractions(...)` |
| “Chỉ tính tiền một lần” | `verify(payment, times(1)).charge(...)` |
| “Không gửi thông báo nếu chưa phê duyệt” | `verifyNoInteractions(notifier)` hoặc `never()` có mục đích |
| “Phải authorize trước charge” | `InOrder(authorizer, payment)` |
| “Retry tối đa ba lần rồi báo lỗi” | Assert exception + `times(expectedAttempts)` trong tình huống cụ thể |
| “Phải phát message chứa orderId đúng” | `verify` đối số cụ thể hoặc `ArgumentCaptor` |
| “Controller trả HTTP 201 đúng JSON” | Assertion status/body qua MockMvc; chỉ verify service khi cần hợp đồng gọi |

Viết test sao cho FAIL truyền đạt một **vi phạm hành vi**, không chỉ một thay đổi nội bộ vô hại.

## 13. Checklist QA cho một bài test dùng verify

Trước khi chấp nhận test:

1. **Đã chạy hành vi thật của class cần kiểm thử?** Test có gọi SUT, không chỉ stub rồi verify không?
2. **Mockito mock là cùng instance được SUT sử dụng?** Nếu là Spring bean, đã mock đúng bean trong context chưa?
3. **Cần assert output/state không?** `verify` chỉ quan sát lời gọi; nó không đảm bảo kết quả trả về.
4. **Số lần nào đúng theo contract?** `times(1)`, `times(n)`, `never()` hay khoảng `atLeast/atMost`?
5. **Đối số có đủ chính xác?** Đừng dùng `any()` khi sai ID/amount sẽ là lỗi.
6. **Thứ tự có thực sự quan trọng?** Dùng `InOrder` chỉ khi phụ thuộc nghiệp vụ/consistency cần nó.
7. **Negative path có cấm side effect?** `verifyNoInteractions` trên collaborator quan trọng nếu có yêu cầu.
8. **Có kiểm tra quá mức?** `verifyNoMoreInteractions` và verify mọi helper call có làm test giòn không?
9. **Test có asynchronous behavior?** Chờ đúng tín hiệu hoàn thành trước khi verify.
10. **Có đọc báo cáo và số lượng test?** Đảm bảo test được thực thi, không bị `@Disabled` hoặc lọc bỏ.

### Thực hành đề xuất

Dùng hai test class hoàn chỉnh:

```bash
./gradlew test --tests 'com.example.testing.CheckoutWorkflowTest'
./gradlew test --tests 'com.example.testing.RetrySenderTest'
./gradlew test
```

Bài tập tự làm:

1. Trong `CheckoutWorkflow.execute`, cố ý gọi `payment.charge` **hai lần** khi đơn được phê duyệt; dự đoán test nào FAIL và thông báo vì sao.
2. Đảo thứ tự gửi receipt và charge (điều chỉnh code minh họa cho phù hợp); xem `InOrder` phát hiện vi phạm contract như thế nào.
3. Với đơn bị từ chối, thêm một lời gọi vô tình tới payment; xác nhận `verifyNoInteractions(payment, receipts)` FAIL.
4. Trong `RetrySender`, đổi `attempt <= 3` thành `attempt <= 2`; xác định vì sao test kỳ vọng ba attempt FAIL.
5. Thử dùng `atLeastOnce()` thay `times(1)` trong test “charge once”; giải thích vì sao assertion yếu hơn.
6. Bỏ `verifyNoMoreInteractions` khỏi happy path và thảo luận trường hợp refactor nào nên được phép thêm interaction nội bộ mà không làm fail test.

## 14. Ghi nhớ

- **`verify(mock).method(args)` = đúng một invocation khớp**, tương đương `times(1)`.
- **`times(n)`** dùng khi số lần là hợp đồng; **`never()`** cấm invocation được chỉ định.
- **`verifyNoInteractions(mock)`** cấm mọi interaction trên mock; **`verifyNoMoreInteractions(mock)`** cấm mọi invocation còn chưa được verify.
- **`InOrder`** chỉ có giá trị khi thứ tự thật sự quan trọng. `verify` thường không kiểm tra thứ tự.
- **Argument matchers/captors** làm rõ nội dung được gửi tới collaborator.
- **Mockito kiểm tra tương tác quan sát được của mock**; không tự chứng minh nghiệp vụ hoàn chỉnh, side effect bên ngoài hoặc Spring dependency injection.
- Hãy xác minh **hành vi đã được yêu cầu**, giữ test dễ hiểu, đủ mạnh để phát hiện bug và ít phụ thuộc chi tiết implementation.

### Tham khảo kỹ thuật

- [Mockito Javadoc — Mockito.verify, times, never, InOrder, verifyNoInteractions](https://site.mockito.org/javadoc/current/org/mockito/Mockito.html).
- [Mockito GitHub — tài liệu và mã nguồn](https://github.com/mockito/mockito).
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/).
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/).
