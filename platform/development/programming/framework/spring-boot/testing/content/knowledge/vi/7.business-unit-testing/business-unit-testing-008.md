# Kiểm tra tính lũy đẳng và hành vi khi thao tác bị gọi lại

## 1. Vấn đề nghiệp vụ: một yêu cầu có thể được gửi nhiều lần

Trong ứng dụng Spring Boot, một người dùng bấm nút “Đặt hàng” hai lần; ứng dụng mobile tự gửi lại request khi mạng chập chờn; message broker giao cùng một message lần nữa; scheduler chạy lại sau khi tiến trình bị khởi động lại; hoặc client không nhận được HTTP response dù server đã xử lý xong. Những tình huống đó có thể tạo **nhiều lần gọi cho cùng một ý định nghiệp vụ**.

Nếu thao tác tạo đơn, trừ tồn kho, tính tiền hoặc phát sự kiện được thực hiện lại một cách mù quáng, hệ thống có nguy cơ tạo bản ghi trùng, trừ tồn hai lần, thu tiền hai lần hoặc gửi thông báo trùng. Vì vậy một bài **unit test nghiệp vụ** cần làm rõ: khi nhận cùng một thao tác lần thứ hai, service phải trả kết quả gì và những side effect nào được phép xảy ra?

Trong bài này, “lũy đẳng” là cách gọi phổ biến của *idempotency* (tính lặp lại không làm thay đổi thêm kết quả/trạng thái theo hợp đồng). Mục tiêu không chỉ là gọi service hai lần và thấy cả hai không ném lỗi, mà phải **đo được trạng thái cuối, kết quả trả về và số lần thực hiện side effect**.

Ví dụ kỳ vọng:

```text
Lần 1: PlaceOrder(tenant=A, key=k-01, sku=BOOK, qty=2)
  -> tạo order-42; trừ tồn kho 2 lần? KHÔNG, chỉ trừ 2 đơn vị một lần
  -> response {orderId: "order-42", status: "CREATED"}

Lần 2: cùng tenant, cùng key, cùng yêu cầu
  -> không tạo đơn mới, không trừ kho nữa
  -> trả cùng kết quả order-42 (hoặc response tương đương theo hợp đồng)

Lần 3: cùng tenant và key, nhưng qty=3
  -> báo xung đột idempotency key; không tạo/ghi thêm dữ liệu
```

**Phạm vi:** cách xác định hợp đồng và kiểm thử logic nghiệp vụ bằng Java 17+, JUnit Jupiter và Mockito; phần sau chỉ ra những bảo đảm không thể đạt được chỉ bằng unit test và nơi cần integration test với database/gateway thật.

## 2. Định nghĩa đúng: kết quả và side effect không tăng thêm

Với một thao tác C tác động lên trạng thái S, ý tưởng lũy đẳng là:

\[
C(C(S)) = C(S)
\]

Trong thực tế còn cần xác định **đầu vào nào được coi là cùng một thao tác**. Một lệnh “tăng số lượng tồn kho thêm 1” tự thân không lũy đẳng; nhưng “xử lý đúng một lần event có ID e-123 để tăng tồn kho 1” có thể trở thành lũy đẳng khi hệ thống ghi nhận ID đã xử lý.

| Thao tác | Gọi lại cùng ý định có tự lũy đẳng? | Cần kiểm tra |
| --- | --- | --- |
| `setStatus("PAID")` khi đã PAID | Có thể, nếu không phát side effect trùng | Trạng thái vẫn PAID và event chỉ phát theo hợp đồng |
| `incrementBalance(100)` | Không | Nếu cần retry an toàn phải có định danh lệnh/ledger |
| `createOrder(request)` | Không mặc nhiên | Cùng key → một order; key khác → ý định mới |
| `charge(card, amount)` | Không mặc nhiên | Một lệnh thanh toán → không thu tiền hai lần |
| `DELETE /items/{id}` | Được coi là phương thức HTTP idempotent về **hiệu ứng dự định** | Resource vắng mặt sau các lần gọi; mã status có thể khác |
| `PUT /items/{id}` với representation giống nhau | Idempotent theo ngữ nghĩa HTTP của thao tác thay thế trạng thái | Resource ở cùng trạng thái mong muốn; ghi audit có thể có hiệu ứng phụ được quy định riêng |
| `POST /orders` | Không mặc nhiên idempotent | API có thể bổ sung idempotency key và quy tắc dedup |

Đối với HTTP, một thao tác idempotent **không bắt buộc** trả status code giống hệt mọi lần. Ví dụ DELETE lần đầu có thể trả `204`, lần sau trả `404`, trong khi resource vẫn không còn tồn tại. Nếu API **đã công bố** bảo đảm replay cùng response với idempotency key, test phải kiểm tra đúng hợp đồng đó; không suy từ định nghĩa HTTP sang “response luôn giống từng byte”.

Một operation hoàn chỉnh thường có ba lớp quan sát:

1. **State invariant:** đối tượng/ledger/database không nhận thêm thay đổi sau lần xử lý đầu.
2. **Side-effect invariant:** gateway thanh toán, message publisher, email sender hoặc repository write không bị gọi trùng ngoài phạm vi cho phép.
3. **Response contract:** lần gọi lại trả kết quả đã ghi nhận, mã trạng thái phù hợp hoặc lỗi conflict nếu key bị tái sử dụng cho payload khác.

Unit test nên chọn những bất biến có thể quan sát trực tiếp trong ranh giới class đang test. Mockito verify số lần gọi sẽ hữu ích khi số lần gọi dependency là chính hợp đồng cần bảo vệ.

## 3. “Gọi lại” có nhiều nguyên nhân khác nhau

Các kịch bản thường bị gộp nhầm làm một:

- **Double click:** người dùng gửi hai request gần nhau; có thể đồng thời ở hai thread hoặc hai instance.
- **Retry do timeout:** client không biết request đầu thành công hay thất bại; kết quả có thể đã được commit trước khi kết nối đứt.
- **At-least-once delivery:** consumer nhận lại cùng event/message ID; broker không bảo đảm consumer chỉ thấy một lần.
- **Batch replay:** job chạy lại sau khi restart và đọc lại những phần tử đã xử lý.
- **Người dùng thực sự tạo thao tác mới:** cùng payload nhưng **key khác**; không được tự coi là duplicate nếu domain cho phép nhiều đơn hàng giống nhau.
- **Key cũ nhưng payload khác:** client dùng sai key; phải phát hiện xung đột thay vì trả một kết quả thuộc yêu cầu khác.

Bốn thông tin cần thống nhất trước khi viết test:

**Danh tính lệnh:** dựa vào `idempotencyKey`/message ID, business key có unique constraint, hay trạng thái domain? Một SKU và số lượng bằng nhau **không đủ** suy ra hai đơn hàng là một.

**Phạm vi key:** `(tenantId, key)`, `(userId, key)`, `(merchantId, key)` hoặc một phạm vi khác. Cùng chuỗi key của hai tenant không nhất thiết là cùng lệnh.

**Bằng chứng payload tương đương:** so sánh canonical payload/fingerprint của các trường ảnh hưởng nghiệp vụ. Không đưa header ngẫu nhiên hoặc thời điểm request không liên quan vào fingerprint; ngược lại không bỏ sót amount, currency, recipient, SKU hoặc quantity.

**Thời gian giữ kết quả:** replay được bảo đảm bao lâu? Nếu key hết hạn, thao tác sau TTL có thể được xem là yêu cầu mới theo contract. Unit test thời gian nên dùng `Clock` được inject, không dùng `Thread.sleep`.

## 4. Xác lập contract trước khi mock

Giả sử service nhận:

```text
placeOrder(tenantId, requestId, OrderRequest(sku, quantity))
```

Hợp đồng mẫu:

1. Reject `tenantId`, `requestId`, SKU rỗng hoặc quantity không hợp lệ **trước khi** gọi writer.
2. Với `(tenantId, requestId)` chưa có: thực hiện đúng một lần thao tác tạo đơn và lưu kết quả thành công.
3. Cùng tenant, key, payload: trả lại kết quả thành công trước đó; không tạo đơn lần hai.
4. Cùng tenant, key nhưng khác payload: từ chối với exception conflict; không ghi lần nữa.
5. Key khác: xem là một yêu cầu khác, dù payload giống nhau.
6. Cùng chuỗi key nhưng tenant khác: không chia sẻ dedup record.
7. Nếu lần đầu **thất bại chắc chắn trước khi side effect được commit**, lần sau được thử lại.
8. Nếu lỗi xảy ra **sau khi side effect đã commit nhưng trước khi lưu kết quả idempotency**, test bộ nhớ đơn giản **không bảo đảm** chống tạo trùng; cần thiết kế bền vững ở lớp lưu trữ/gateway.

Đừng viết test chỉ theo chi tiết code hiện tại rồi xem đó là contract: trước tiên phải biết sản phẩm mong muốn gì với thao tác lặp lại, đặc biệt lỗi, TTL và scope.

### Ma trận tình huống cần có

| Tình huống | Kết quả mong đợi | Side effect mới? |
| --- | --- | --- |
| Key mới, payload hợp lệ | Tạo kết quả lần đầu | Một lần |
| Cùng key và payload sau thành công | Replay kết quả | Không |
| Cùng key nhưng quantity/amount khác | Conflict | Không |
| Key mới với payload giống nhau | Ý định mới theo hợp đồng mẫu | Một lần mới |
| Cùng key thuộc tenant khác | Lệnh độc lập | Một lần cho tenant mới |
| Input sai | Validation error | Không |
| Thất bại trước commit rồi retry | Retry có thể thành công | Chỉ phần tạo thực sự thành công |
| Hai call cùng key đồng thời | Một logical result | Không tạo hai lần, cần kiểm tra cơ chế đồng bộ |
| Commit xong nhưng mất response | Replay kết quả sau retry | Cần lưu trữ bền vững, unit test mock chưa đủ |
| Key hết hạn | Theo retention policy đã công bố | Có thể là lệnh mới |

## 5. Dự án Java 17+ chạy được: JUnit Jupiter và Mockito

Ví dụ sau kiểm tra **một service in-memory** nhận idempotency key. Nó có thể chạy riêng mà không cần Spring context; vì thế lỗi được quy về logic nghiệp vụ thay vì cấu hình framework.

Cấu trúc:

```text
idempotency-unit-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/com/example/testing/
    └── IdempotentOrderServiceTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'idempotency-unit-demo'
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

Các phiên bản này là một **bộ minh họa cụ thể**, không khẳng định mới nhất. Dự án Spring Boot thực tế nên để BOM của Boot quản lý các dependency kiểm thử tương ứng, thường thông qua `spring-boot-starter-test`.

### Cách mô hình hóa

- `OrderRequest` là payload nghiệp vụ; `record` của Java 17 có `equals/hashCode` theo tất cả thành phần.
- `ScopedKey(tenantId, requestId)` định danh lệnh trong một tenant.
- `OrderWriter` đại diện cho **một cổng tạo đơn**. Trong unit test nó là Mockito mock; khi tích hợp thật có thể là transaction/repository service.
- `Stored` lưu **payload đã xử lý và kết quả trả về** để phát hiện re-use key không hợp lệ.
- `ConcurrentHashMap.computeIfAbsent` khiến cùng một key chỉ chạy mapping function một lần khi phần tính toán thành công trong **một JVM**, kể cả những lời gọi song song.
- Khi mapping function ném exception, entry không được lưu; lần sau có thể gọi lại writer.

Đây là **mô hình phục vụ unit test**, không phải bộ idempotency production xuyên nhiều instance. Đặc biệt, **không nên đặt HTTP/DB operation chậm trong `computeIfAbsent` ở production rồi cho rằng đã có exactly-once**: callback của map chạy trong quá trình cập nhật map, có thể giữ khóa/giảm throughput và không bảo vệ crash hoặc nhiều JVM.

## 6. Ví dụ đầy đủ: lệnh bị gọi lại vẫn chỉ ghi một lần

Tạo `src/test/java/com/example/testing/IdempotentOrderServiceTest.java`:

```java
package com.example.testing;

import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class IdempotentOrderServiceTest {

    record OrderRequest(String sku, int quantity) {
    }

    record OrderReceipt(String orderId, String sku, int quantity) {
    }

    record ScopedKey(String tenantId, String requestId) {
    }

    record Stored(OrderRequest request, OrderReceipt receipt) {
    }

    interface OrderWriter {
        OrderReceipt create(String tenantId, OrderRequest request);
    }

    static final class KeyConflictException extends RuntimeException {
        KeyConflictException() {
            super("idempotency key reused with another payload");
        }
    }

    static final class IdempotentOrderService {
        private final OrderWriter writer;
        private final ConcurrentMap<ScopedKey, Stored> completed =
                new ConcurrentHashMap<>();

        IdempotentOrderService(OrderWriter writer) {
            this.writer = Objects.requireNonNull(writer);
        }

        OrderReceipt place(
                String tenantId,
                String requestId,
                OrderRequest request) {

            if (tenantId == null || tenantId.isBlank()
                    || requestId == null || requestId.isBlank()
                    || request == null || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() <= 0) {
                throw new IllegalArgumentException("invalid order");
            }

            ScopedKey key = new ScopedKey(tenantId, requestId);

            Stored stored = completed.computeIfAbsent(
                    key,
                    ignored -> new Stored(
                            request,
                            Objects.requireNonNull(
                                    writer.create(tenantId, request)))
            );

            if (!stored.request().equals(request)) {
                throw new KeyConflictException();
            }

            return stored.receipt();
        }
    }

    private static final OrderRequest REQUEST =
            new OrderRequest("BOOK", 2);

    private static final OrderReceipt RECEIPT_1 =
            new OrderReceipt("order-42", "BOOK", 2);

    @Mock
    OrderWriter writer;

    private IdempotentOrderService service;

    @BeforeEach
    void setUp() {
        service = new IdempotentOrderService(writer);
    }

    @Test
    void sameKeyAndPayloadReplayFirstSuccess() {
        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1);

        OrderReceipt first =
                service.place("tenant-a", "req-1", REQUEST);
        OrderReceipt replay =
                service.place("tenant-a", "req-1", REQUEST);

        assertEquals(RECEIPT_1, first);
        assertEquals(first, replay);
        verify(writer, times(1)).create("tenant-a", REQUEST);
    }

    @Test
    void sameKeyWithDifferentPayloadIsRejected() {
        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1);

        service.place("tenant-a", "req-1", REQUEST);

        OrderRequest changed = new OrderRequest("BOOK", 3);

        assertThrows(
                KeyConflictException.class,
                () -> service.place("tenant-a", "req-1", changed)
        );

        verify(writer, times(1)).create("tenant-a", REQUEST);
        verify(writer, never()).create("tenant-a", changed);
    }

    @Test
    void differentKeysAreDifferentBusinessCommands() {
        OrderReceipt second =
                new OrderReceipt("order-43", "BOOK", 2);

        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1, second);

        OrderReceipt first =
                service.place("tenant-a", "req-1", REQUEST);
        OrderReceipt next =
                service.place("tenant-a", "req-2", REQUEST);

        assertNotEquals(first.orderId(), next.orderId());
        verify(writer, times(2)).create("tenant-a", REQUEST);
    }

    @Test
    void keyIsScopedPerTenant() {
        OrderReceipt tenantBReceipt =
                new OrderReceipt("order-99", "BOOK", 2);

        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1);
        when(writer.create("tenant-b", REQUEST))
                .thenReturn(tenantBReceipt);

        OrderReceipt a =
                service.place("tenant-a", "same-key", REQUEST);
        OrderReceipt b =
                service.place("tenant-b", "same-key", REQUEST);

        assertNotEquals(a.orderId(), b.orderId());
        verify(writer).create("tenant-a", REQUEST);
        verify(writer).create("tenant-b", REQUEST);
    }

    @Test
    void invalidRequestHasNoSideEffects() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.place(
                        "tenant-a", "req-1", new OrderRequest("BOOK", 0))
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> service.place(
                        "tenant-a", " ", REQUEST)
        );

        verifyNoInteractions(writer);
    }

    @Test
    void failureBeforeCommitAllowsRetry() {
        when(writer.create("tenant-a", REQUEST))
                .thenThrow(new IllegalStateException("before commit"))
                .thenReturn(RECEIPT_1);

        assertThrows(
                IllegalStateException.class,
                () -> service.place("tenant-a", "req-1", REQUEST)
        );

        OrderReceipt recovered =
                service.place("tenant-a", "req-1", REQUEST);
        OrderReceipt replay =
                service.place("tenant-a", "req-1", REQUEST);

        assertEquals(RECEIPT_1, recovered);
        assertEquals(recovered, replay);
        verify(writer, times(2)).create("tenant-a", REQUEST);
    }

    @Test
    void simultaneousCallsForSameKeyProduceOneWrite()
            throws Exception {
        when(writer.create("tenant-a", REQUEST))
                .thenReturn(RECEIPT_1);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<OrderReceipt> call = () -> {
            start.await();
            return service.place("tenant-a", "req-1", REQUEST);
        };

        try {
            Future<OrderReceipt> first = pool.submit(call);
            Future<OrderReceipt> second = pool.submit(call);
            start.countDown();

            assertEquals(RECEIPT_1, first.get(10, TimeUnit.SECONDS));
            assertEquals(RECEIPT_1, second.get(10, TimeUnit.SECONDS));
            verify(writer, times(1)).create("tenant-a", REQUEST);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy bằng Gradle Wrapper (nếu dự án có Wrapper):

```bash
./gradlew test --tests 'com.example.testing.IdempotentOrderServiceTest'
```

Trên Windows dùng:

```powershell
.\gradlew.bat test --tests "com.example.testing.IdempotentOrderServiceTest"
```

Nếu chỉ có Gradle cài sẵn, đổi `./gradlew` thành `gradle`. **Kết quả kỳ vọng: 7 phương thức test PASS** với điều kiện môi trường tải và chạy được dependencies. Bài test không in stdout cố định; báo cáo mặc định của Gradle có thể xem ở `build/reports/tests/test/index.html`. Ví dụ không sử dụng Spring context và không cần cơ sở dữ liệu.

### 6.1. Kiểm tra replay và đúng một lần

Trong `sameKeyAndPayloadReplayFirstSuccess`, ta thực sự gọi `place(...)` **hai lần** với cùng key/payload. Hai assertion:

```java
assertEquals(RECEIPT_1, first);
assertEquals(first, replay);
```

xác minh kết quả nghiệp vụ. Sau đó:

```java
verify(writer, times(1)).create("tenant-a", REQUEST);
```

xác minh writer chỉ được gọi một lần. Nếu chỉ assert kết quả mà không đo side effect, service có thể tạo hai đơn nhưng tình cờ trả cùng receipt. Nếu chỉ verify số lần mà không assert kết quả, service có thể trả sai receipt. **Cần cả hai** khi contract bao gồm cả kết quả và số lần ghi.

### 6.2. Kiểm tra trùng key nhưng khác nội dung

`sameKeyWithDifferentPayloadIsRejected` xác nhận request thứ hai không “ghi đè” ý nghĩa của key đã dùng. `record OrderRequest` so sánh theo SKU và quantity; đổi quantity 2 thành 3 tạo payload khác. Test đòi `KeyConflictException`, đồng thời dùng:

```java
verify(writer, never()).create("tenant-a", changed);
```

để chứng minh không tạo thêm order dựa trên payload bị thay đổi. Trong API HTTP, có thể ánh xạ lỗi domain này thành `409 Conflict` theo hợp đồng endpoint. Lựa chọn HTTP status là quyết định của tầng API, không mặc nhiên được chứng minh bởi unit test service.

### 6.3. Phân biệt duplicate và một lệnh mới

Hai lần gọi có payload hoàn toàn giống nhau **vẫn là hai đơn khác nhau** khi request key khác, nếu domain đã chọn key là danh tính thao tác. `differentKeysAreDifferentBusinessCommands` đòi hai lần gọi writer và orderId khác nhau. Không được đơn giản dùng hash của payload làm key cho mọi trường hợp; như vậy hai ý định đặt hàng hợp lệ với nội dung giống nhau có thể bị gộp sai.

### 6.4. Phạm vi tenant

`keyIsScopedPerTenant` kiểm tra chuỗi `same-key` ở `tenant-a` không ảnh hưởng `tenant-b`. Trong hệ thống nhiều tenant, quên scope key có thể dẫn đến trả nhầm kết quả của khách hàng khác. Một khóa duy nhất cần chứa tenant/user/merchant scope theo thiết kế bảo mật và dữ liệu thực.

### 6.5. Dữ liệu sai không gây side effect

`invalidRequestHasNoSideEffects` kiểm tra cả mã yêu cầu trắng và số lượng 0, rồi dùng `verifyNoInteractions(writer)`. Điều này bảo vệ nguyên tắc **validate trước khi mutation**; việc test ném exception đúng nhưng đã ghi xuống DB trước khi ném vẫn là lỗi.

### 6.6. Retry sau thất bại trước commit

Trong `failureBeforeCommitAllowsRetry`, mock giả lập lần đầu **chắc chắn chưa commit** và ném lỗi, lần thứ hai trả kết quả thành công. `computeIfAbsent` không lưu entry nếu lambda ném exception; do đó cùng key có thể được thử lại. Kỳ vọng writer bị gọi **hai lần thử**, nhưng chỉ lần thứ hai thành công theo giả định mô phỏng.

Nếu lần đầu thực tế đã tạo order nhưng response/ack bị mất, mô hình này không đủ an toàn: writer đã tạo side effect mà service không ghi nhớ. Đừng suy từ test này rằng mọi timeout đều có thể retry an toàn.

### 6.7. Khi hai lời gọi xảy ra đồng thời

Test `simultaneousCallsForSameKeyProduceOneWrite` thả hai task bằng `CountDownLatch` và nhận hai `Future`. Nó xác minh hai caller nhận cùng kết quả và mock writer chỉ được gọi một lần trong **cùng một service instance**.

Một lần chạy có thể không gây interleaving giống sản xuất; đây là **unit test có thực thi song song**, không phải bằng chứng toán học rằng mọi race đã được kiểm soát. Với hệ thống nhiều instance hoặc lưu bền vững, cần integration/concurrency test kiểm tra unique constraint và transaction boundaries.

## 7. Cách test hành vi lũy đẳng theo trạng thái domain

Không phải thao tác nào cũng dựa vào idempotency key. Một số hành vi diễn đạt trực tiếp bằng **state transition**:

```text
Shipment: CREATED --ship()--> SHIPPED
Shipment: SHIPPED --ship()--> SHIPPED
```

Nếu nghiệp vụ cho phép “đánh dấu đã giao” lặp lại, lần thứ hai phải giữ trạng thái SHIPPED, không giảm tồn kho hoặc phát domain event lần nữa. Test nên đặt tên như:

- `shipChangesCreatedToShipped`: lần đầu đổi state.
- `shipAgainPreservesShippedState`: gọi lần hai vẫn SHIPPED.
- `shipAgainDoesNotPublishSecondEvent`: publisher không bị gọi thêm.
- `shipFromCancelledIsRejected`: chuyển từ trạng thái không hợp lệ bị từ chối mà không phát event.

Pseudo-code thể hiện ý tưởng:

```java
if (shipment.status() == Status.SHIPPED) {
    return; // Không làm thêm transition hay side effect.
}
shipment.markShipped();
events.publishShipmentShipped(shipment.id());
```

Đây là **đoạn minh họa**, cần domain classes và infrastructure được định nghĩa đầy đủ mới chạy được. Nó hữu ích để bàn về transition lặp lại, nhưng **thứ tự state update rồi publish** trong đoạn này chưa an toàn khi publisher ném exception: trạng thái đã SHIPPED nhưng event có thể chưa phát. Với production, xem xét ghi event vào **transactional outbox** cùng transaction thay đổi trạng thái, rồi worker publish và consumer xử lý lặp an toàn.

Một mệnh lệnh như “trừ 2 sản phẩm trong kho” không trở nên lũy đẳng chỉ vì được đặt trong `if` kiểm tra state; cần xác định **đơn hàng/lệnh nào** đã áp dụng lần trừ đó, nhất là khi có nhiều đơn hàng đồng thời.

## 8. Unit test không thể tự bảo đảm exactly-once trong hệ phân tán

Ví dụ dùng `ConcurrentHashMap` chỉ giữ trạng thái trong bộ nhớ. Ba tình huống làm nó không đủ an toàn:

1. **Restart:** JVM chết thì map mất; request cũ được gửi lại sau restart có thể tạo thêm order.
2. **Scale ngang:** hai instance có hai map khác nhau; cùng key đến hai instance có thể đều tạo order.
3. **Crash giữa side effect và ghi nhận kết quả:** writer tạo xong order/thanh toán nhưng response bị lỗi; mapping chưa được lưu, lần retry lại tạo thêm.

Trình tự lỗi thường gặp:

```text
Client                 Service A               Database/Payment
  |  POST req-1           |                         |
  |---------------------->|                         |
  |                       | create/charge            |
  |                       |------------------------>|
  |                       |           COMMIT OK     |
  |                       |<------------------------|
  |      TCP timeout      X (crash trước lưu kết quả)
  |       ...                                       |
  |  POST req-1 retry     | Service B               |
  |---------------------->|                         |
  |                       | Không thấy in-memory key |
  |                       | create/charge lần 2     |
  |                       |------------------------>|
```

**“Exactly once” end-to-end là hợp đồng khó:** hệ thống không chỉ cần tránh gọi cùng code hai lần mà cần đảm bảo **hiệu ứng nghiệp vụ duy nhất** trong những ranh giới giao dịch và bên ngoài có thể lỗi từng phần. Với thanh toán, phải tận dụng idempotency key/hợp đồng của payment provider nếu có; với message processing, dùng unique key, inbox/outbox hoặc ledger trạng thái.

### Mô hình lưu bền vững thường dùng

Một bảng định danh lệnh (mang tính minh họa):

```sql
CREATE TABLE idempotency_records (
    tenant_id       VARCHAR(100) NOT NULL,
    request_key     VARCHAR(200) NOT NULL,
    request_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    response_body   TEXT,
    created_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, request_key)
);
```

Quy trình ở lớp persistence:

1. Chuẩn hóa payload và tính hash những trường ảnh hưởng nghiệp vụ.
2. Trong transaction hoặc cơ chế đồng bộ phù hợp, cố tạo **một record có unique key**.
3. Nếu key đã tồn tại, so sánh hash: khác payload → conflict; cùng payload và đã thành công → trả kết quả đã lưu.
4. Nếu đang xử lý, quy định rõ hành vi: chờ, trả in-progress/accepted hoặc retry-after; không tự thực thi song song.
5. Ghi mutation nghiệp vụ và kết quả idempotency theo ranh giới transaction bảo vệ nhất quán.
6. Nếu có event bên ngoài transaction DB, cân nhắc outbox cùng transaction và consumer idempotent.
7. Đặt chính sách retention, cleanup và xử lý key hết hạn.

Đây là **phác thảo kiến trúc**, không phải code production hoàn chỉnh: cơ chế lock, isolation, hash, unique violation, recovery từ `IN_PROGRESS`, thời gian giữ kết quả và retry cần thiết kế riêng cho database và domain. Đặc biệt không được thực hiện HTTP payment trong một DB transaction rồi mặc định rollback DB cũng hoàn tác được phía payment provider.

### Trạng thái xử lý có thể cần phân biệt

```text
NEW -> IN_PROGRESS -> SUCCEEDED
                  \-> FAILED_RETRYABLE
                  \-> FAILED_FINAL
```

Không phải mọi lỗi đều cho phép retry giống nhau. Ví dụ validation sai là lỗi cuối cùng và không nên làm side effect; timeout mạng tới gateway có thể là **outcome unknown** nên cần truy vấn trạng thái hoặc retry cùng provider idempotency key, thay vì gọi charge với key mới.

Đối với `FAILED_RETRYABLE`, chỉ chuyển lại xử lý nếu có bằng chứng thao tác trước chưa gây effect trùng, hoặc provider/storage bảo đảm dedup.

## 9. Bộ kiểm thử theo lớp: unit, integration, API

| Mức test | Câu hỏi cần chứng minh | Công cụ và cách làm |
| --- | --- | --- |
| Unit test service | Replay cùng key có trả cùng receipt và chỉ gọi writer một lần không? | JUnit Jupiter + Mockito; `verify(times(1))` |
| Unit test validation | Payload sai hoặc reuse key sai có chặn side effect không? | `assertThrows` + `verifyNoInteractions` / `never()` |
| Unit test state machine | Lặp transition có giữ trạng thái và không phát event trùng không? | Domain objects thật + mock event publisher |
| Unit test clock/TTL | Key còn hạn/hết hạn có hành vi đúng không? | Inject `Clock.fixed(...)`/fake clock; không sleep |
| Repository integration | Unique key và transaction có chặn hai insert cùng key không? | Spring Boot Test + Testcontainers database thật |
| API slice | Header idempotency key, status và body có đúng không? | `@WebMvcTest` + MockMvc + mock service |
| HTTP integration | Hai request trùng và timeout/retry xử lý đúng xuyên endpoint không? | `@SpringBootTest`, HTTP client, DB thật |
| Distributed / fault injection | Crash hoặc hai instance sau commit có nhân đôi nghiệp vụ không? | Integration/system test với persistence và failure points |

Một **unit test thành công** chứng minh logic của object trong điều kiện collaborator phản hồi như đã stub. Nó không chứng minh database transaction, message broker hoặc provider từ xa cũng đúng. Nhưng unit test rất có giá trị: khi biết rõ invariant, ta có thể bắt lỗi trùng lặp từ vòng logic trước khi đi tới integration test đắt tiền.

## 10. Thiết kế thêm các ca kiểm thử có giá trị

### 10.1. Replay cùng key nhưng không giả định object identity

Trong test `sameKeyAndPayloadReplayFirstSuccess`, so sánh `assertEquals(first, replay)` theo record value. Không cần `assertSame(first, replay)` trừ khi **chính việc trả cùng Java object instance** là hợp đồng; trong API thật, response thường được serialize/deserialise thành object mới nên object identity không có ý nghĩa.

### 10.2. Lệnh mới có payload y hệt

Đừng viết “hai payload giống nhau phải tạo một order” nếu domain cho phép người dùng đặt hai đơn hàng cùng SKU/quantity ở hai thời điểm. Test riêng với hai key giúp ngăn logic dedup sai phạm vi.

### 10.3. Retry lỗi sau commit hoặc mất acknowledgement

Unit test có thể mô phỏng gateway trả “unknown outcome”, nhưng không thể chứng minh điều đã commit ngoài process. Cần integration test với durable key và mock/fake provider có state được giữ riêng; quan sát cả sau restart/đổi instance. Assertion quan trọng: số bản ghi business và số request được provider thực sự chấp nhận.

### 10.4. Consumer message nhận duplicate

Hợp đồng có thể là `handle(Event(id="evt-7"))` hai lần chỉ cập nhật projection một lần. Dùng event ID làm khóa inbox, unique constraint trên event ID, và kiểm tra projection total không tăng thêm. Không dựa vào số lần broker gọi listener làm metric của nghiệp vụ: broker **có thể** giao lại hợp lệ.

### 10.5. Đồng thời với key khác

Hai yêu cầu khác key có thể cùng thay đổi một tài nguyên hạn chế (ví dụ hai đơn cùng mua một sản phẩm còn 1 chiếc). **Idempotency key không giải quyết oversell** giữa các lệnh khác nhau. Cần locking/optimistic version/constraint inventory độc lập, và test concurrency tại tầng repository/transaction.

### 10.6. Hiệu ứng phụ được cho phép khi replay

Hệ thống có thể ghi access log, metrics “duplicate_request” hoặc cập nhật `lastSeenAt` mỗi lần replay. Những effect phụ được cho phép không đồng nghĩa đã tạo đơn mới. Khi viết Mockito test, verify **collaborator thực hiện mutation nghiệp vụ quan trọng** đúng một lần, không nên áp `verifyNoMoreInteractions` cho cả logger/metrics nếu contract cho phép chúng chạy lại.

### 10.7. Chính sách trả lỗi lần đầu

Nhiều API chọn lưu và replay cả kết quả thất bại cuối cùng (ví dụ business rejection), trong khi lỗi transient trước commit có thể được retry. Đây là quyết định domain/API: định nghĩa rõ **thất bại nào được cache**, thất bại nào giải phóng key, và nếu outcome unknown thì hệ thống phục hồi thế nào. Mã mẫu ở mục 6 chỉ cache **thành công**.

## 11. Cạm bẫy phổ biến khi viết test lũy đẳng

**Chỉ assert status code 200/201.**  
Hai request đều trả thành công không chứng minh không tạo hai đơn. Kiểm tra orderId, số bản ghi và side effect.

**Chỉ gọi lại service sau khi đã reset object.**  
Nếu unit test tạo service mới giữa hai lần gọi, dữ liệu `Map` in-memory sẽ mất. Điều này có thể hữu ích để **chứng minh hạn chế** sau restart, nhưng không phù hợp nếu mục tiêu đang test replay trong cùng service instance. Với durable idempotency, phải kiểm tra lại bằng service instance mới dùng chung repository thật.

**Dùng `verify(times(1))` trên đúng một mock rồi kết luận toàn hệ thống exactly-once.**  
Mock chỉ quan sát lời gọi trên object mock đó; nó không biết DB đã commit, provider đã charge hay consumer khác đã xử lý. Kết luận phải giới hạn đúng ranh giới test.

**Dùng payload hash làm danh tính thao tác duy nhất.**  
Hai đơn có payload giống hệt nhưng là hai ý định độc lập sẽ bị gộp sai. Fingerprint nên được dùng **để xác minh tính nhất quán của một key đã có**, không mặc nhiên thay thế key.

**Không so sánh payload khi replay key cũ.**  
Client có thể vô tình dùng cùng key cho số tiền khác. Trả receipt cũ im lặng có thể gây sai giao dịch. Test phải phát hiện conflict và không tiếp tục mutation.

**Không gắn tenant hoặc user scope vào key.**  
Hai khách hàng cùng sinh chuỗi key phổ biến như `request-1` có thể đọc nhầm kết quả nếu bộ nhớ dedup dùng key toàn cục. Kiểm tra scope nhiều tenant.

**Cho rằng retry an toàn vì đã có `@Retryable`.**  
Cơ chế retry chỉ điều phối việc **gọi lại** sau exception; nó không tự biến lệnh không lũy đẳng thành lũy đẳng. Phải thiết kế dedup hoặc bảo đảm phía dependency nhận cùng idempotency key khi retry.

**Dùng kiểm tra `atLeastOnce()` khi hợp đồng là đúng một lần.**  
`verify(writer, atLeastOnce()).create(...)` vẫn PASS nếu writer bị gọi hai lần. Với yêu cầu tránh side effect trùng, dùng `times(1)` hoặc kiểm tra aggregate state thích hợp.

**Phụ thuộc vào thứ tự callback hoặc thread scheduling.**  
Test race dựa vào `Thread.sleep(50)` dễ flaky. Dùng latch/barrier để điều phối, nhưng vẫn cần kiểm tra ràng buộc unique/transaction trong integration test.

**Tin rằng `ConcurrentHashMap.computeIfAbsent` bảo vệ mọi process.**  
Map chỉ tồn tại trong một JVM; sau restart hoặc scale ngang, không có shared dedup. Ngoài ra mapping function có side effect từ xa không được rollback chỉ vì exception.

**Không test crash window.**  
Đường đi thành công có thể PASS nhưng server chết sau charge trước khi lưu receipt sẽ tạo charge lại. Đây là lý do hệ thống thanh toán thường cần provider-level idempotency và transaction/reconciliation.

**Bỏ quên TTL/retention.**  
Key vô hạn có thể làm kho dữ liệu tăng không kiểm soát; key hết hạn quá sớm tạo replay ngoài mong muốn. Test retention policy bằng clock giả và kiểm chứng hành vi sau mốc hết hạn.

## 12. Checklist thiết kế và kiểm tra

Trước khi hoàn tất một service cần retry an toàn, trả lời:

1. “Cùng thao tác” được định nghĩa bằng **key nào**? Key có scope theo tenant/merchant/user không?
2. Những trường nào trong payload phải giữ nguyên khi reuse key? Trường nào được phép thay đổi mà không đổi ý nghĩa nghiệp vụ?
3. Kết quả replay phải giống đến mức nào: same orderId, same domain state, same response body hay chỉ cùng hiệu ứng dự định?
4. Side effect nào tuyệt đối chỉ xảy ra một lần? Order creation, inventory mutation, charge, event, email?
5. Input sai và payload conflict có bị reject **trước khi** chạm dependency không?
6. Lỗi “chắc chắn chưa commit” và lỗi “không biết đã commit chưa” được phân biệt như thế nào?
7. Nếu hai thread/JVM nhận cùng key, unique constraint hoặc giao dịch nào phân xử?
8. Server restart có giữ được dedup record không?
9. Khi publish message, có transactional outbox và consumer idempotent nếu cần không?
10. Bao lâu mới được xóa idempotency record? Sau TTL thì replay mang ý nghĩa gì?
11. Unit test đã đo **trạng thái/kết quả và số lần side effect** chưa?
12. Integration test đã xác minh database/provider thực và ít nhất một kịch bản concurrency/failure quan trọng chưa?

## 13. Bài thực hành và cách chấm kết quả

Với class `IdempotentOrderServiceTest`:

1. Bỏ `completed.computeIfAbsent`, thay bằng gọi `writer.create(...)` trực tiếp. Chạy lại: test replay sẽ FAIL vì writer được gọi hai lần, test duplicate conflict cũng không được xử lý.
2. Đổi khóa từ `ScopedKey(tenantId, requestId)` thành chỉ `requestId`. Test `keyIsScopedPerTenant` sẽ lộ việc hai tenant cùng key không được phân biệt.
3. Bỏ bước so sánh `stored.request().equals(request)`. Test reuse key với quantity khác sẽ FAIL vì service trả receipt cũ thay vì conflict.
4. Sửa test thành `verify(writer, atLeastOnce()).create(...)` rồi cố ý gọi writer lần hai: vì sao test yếu hơn? Khôi phục `times(1)`.
5. Nâng tình huống “failed before commit” thành “writer đã tạo order rồi ném timeout”. Giải thích tại sao service in-memory có thể gọi writer lần nữa dù key giống nhau và tại sao không thể sửa chỉ bằng Mockito stubbing.
6. Đề xuất bảng DB unique key + transaction cho hệ thống hai instance; viết một integration test với hai request cùng key và xác minh đúng **một** order record.

Các mục 1–4 có thể quan sát trực tiếp với unit test. Các mục 5–6 đòi hỏi hiểu ranh giới dữ liệu thật và khả năng crash; đừng tự nhận unit test đã bao phủ chúng.

### Tài liệu tham khảo

- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/) — tổ chức unit test và assertions.
- [Mockito documentation](https://site.mockito.org/) — `verify`, `times`, `never`, strict stubbing.
- [Spring Boot testing reference](https://docs.spring.io/spring-boot/3.3/reference/testing/) — Spring Boot Test, test slices và integration test.
- [RFC 9110 — HTTP Semantics, idempotent methods](https://www.rfc-editor.org/rfc/rfc9110.html) — phân biệt idempotency của hiệu ứng dự định với HTTP response.
- [Testcontainers Java](https://java.testcontainers.org/) — môi trường database/service thật cho integration test.

## 14. Kết luận

Một thao tác lũy đẳng cần được kiểm chứng qua **cùng một ý định nghiệp vụ được gọi lại**: trạng thái không bị thay đổi thêm, không có side effect quan trọng bị nhân đôi, và response/conflict tuân theo hợp đồng. Unit test với JUnit và Mockito có thể bảo vệ rất tốt nhánh replay, validation, key scope, mismatch payload và số lần writer được gọi. Tuy nhiên, giới hạn của unit test phải được nhìn nhận rõ: tính lũy đẳng bền vững khi có timeout, crash và nhiều instance cần cơ chế lưu kết quả, unique constraint, transaction, outbox hoặc idempotency phía provider và integration test tương ứng.
