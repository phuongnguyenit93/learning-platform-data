# Dự án thực hành: Đánh giá giới hạn còn lại của bộ verification

Một bộ kiểm chứng Spring Modulith có thể chạy xanh trong CI nhưng vẫn để lọt lỗi: gọi sang module khác qua reflection, consumer xử lý trùng sự kiện, truy vấn chỉ lỗi trên PostgreSQL, hoặc một listener thất bại sau khi transaction nghiệp vụ đã commit. Bài thực hành này đặt bạn vào vai người đánh giá **phần rủi ro còn lại** sau khi nhóm đã có `ApplicationModules.verify()`, các test `@ApplicationModuleTest` và một số test tích hợp. Nhiệm vụ là đo khả năng phát hiện lỗi của bộ verification hiện có, bổ sung phép thử có giá trị và ghi nhận những giới hạn chưa thể khép lại.

Phạm vi gắn với **SPRING_MODULITH_VERIFICATION_TESTING**: xác minh ranh giới kiến trúc, quy tắc phụ thuộc, kiểm thử module, sự kiện, database và quality gate trong CI. Đây là bài đánh giá cuối dự án, vì vậy không dành thời gian dựng lại ví dụ nhập môn về module hoặc JUnit.

**Giả định dùng nhất quán trong các đoạn mã minh họa:** ứng dụng Spring Boot có root class `com.acme.shop.ShopApplication`; module `checkout` cung cấp `CheckoutService.submit(UUID orderId)` và phát `OrderPlaced(UUID orderId)`; module `billing` có `InvoiceEventHandler.on(OrderPlaced)` gọi `InvoiceService.ensureCreatedFor(UUID)` và `InvoiceRepository.countByOrderId(UUID)`. Các class nghiệp vụ này là **hợp đồng giả định của lab**, không phải API do Spring Modulith cung cấp. Khi thực hành trên codebase khác, ánh xạ tên và chuẩn bị fixture đơn hàng hợp lệ trước khi gọi `submit`. Phần import thông dụng của domain và AssertJ được ghi rõ trong những ví dụ có liên quan.

## 1. Chốt câu hỏi đánh giá và tiêu chí đầu ra

Đặt câu hỏi theo hướng có thể phản chứng: **“Nếu lỗi X xuất hiện, phép thử nào sẽ đỏ, và bằng chứng nào cho thấy nó đỏ vì đúng nguyên nhân?”** Không chấp nhận kết luận “đã phủ” chỉ vì một test có tên liên quan hoặc vì tỷ lệ line coverage cao.

Đầu ra cần nộp gồm: (1) danh mục verification hiện có và log baseline, (2) ma trận giới hạn với xác suất và tác động, (3) ít nhất ba phép thử âm tính chủ động gây lỗi (*negative probes*), (4) test tăng cường cho khoảng trống quan trọng, (5) cấu hình quality gate kèm báo cáo rủi ro còn mở. Mỗi phát hiện cần có `ID`, lời mô tả lỗi có thể xảy ra, thành phần bị ảnh hưởng, test chứng minh, mức độ ưu tiên và người chịu trách nhiệm.

Định nghĩa ba trạng thái bằng chứng:

| Trạng thái | Điều kiện được phép ghi nhận |
| --- | --- |
| **Đã bắt được lỗi** | Có thao tác tái tạo lỗi, test thất bại với assertion/violation phù hợp, hoàn nguyên lỗi và test lại xanh. |
| **Đã kiểm tra đường chạy đúng** | Test xanh trên môi trường xác định nhưng **chưa** chứng minh được sẽ đỏ khi hành vi sai. |
| **Chưa kiểm chứng** | Chưa có test, chưa chạy trên phụ thuộc thật, hoặc không giữ được log/chứng cứ. |

## 2. Khóa baseline và lập bản đồ phép thử hiện hữu

Lấy commit SHA, JDK, phiên bản Spring Boot/Modulith, profile, loại database, cấu hình chạy song song và lệnh CI làm mốc tái lập. Chạy đúng tập kiểm thử của dự án, lưu JUnit XML và log lỗi; đừng suy luận “pass” từ việc job CI kết thúc mà không thấy test nào được thực thi. Đối chiếu `tests`, `failures`, `errors`, `skipped` giữa báo cáo và số test dự kiến.

Lập danh mục kiểm thử theo *mục tiêu phát hiện*, không theo tên file:

| Lớp kiểm chứng | Bằng chứng đang tìm | Câu hỏi còn bỏ ngỏ |
| --- | --- | --- |
| `ApplicationModules.verify()` | Phát hiện vòng phụ thuộc, truy cập kiểu không được expose, vi phạm `allowedDependencies` | Có đường gọi động, reflection hoặc phụ thuộc ngoài mã Java không? |
| `@ApplicationModuleTest(STANDALONE)` | Rule nội bộ và bean wiring trong module | Mock hoặc bean thay thế có che lỗi khi chạy cùng module thật khác? |
| `DIRECT_DEPENDENCIES` / `ALL_DEPENDENCIES` | Wiring của các module phụ thuộc được bootstrap | Consumer chỉ nhận sự kiện tại runtime có được khởi tạo trong phạm vi test không? |
| Test phát/nhận sự kiện | Event contract và listener thực sự chạy | Lỗi retry, mất sự kiện, xử lý trùng, sai thứ tự hoặc transaction rollback? |
| Test repository / database | Invariant dữ liệu, migration, transaction | Có dùng H2 thay cho SQL dialect vận hành thật? |
| End-to-end / contract / CI | Tương tác qua HTTP, broker, phụ thuộc ngoài | Chạy ổn định khi latency, outage, cấu hình môi trường thay đổi? |

Ví dụ bảng baseline: `ARCH-01` có 1 test kiến trúc xanh; `EVT-02` có test phát event xanh nhưng chưa test hiệu ứng ở `billing`; `DB-03` mới chạy H2; `OPS-04` chưa có thử nghiệm consumer nhận lại cùng event. Đây chỉ là **mẫu lập hồ sơ**, không phải số đo của một dự án cụ thể.

## 3. Phân ranh giới điều mà công cụ thật sự chứng minh

`ApplicationModules.verify()` phân tích cấu trúc module từ type/package và các quy tắc khai báo; nó không chứng minh ngữ nghĩa của một khoản thanh toán, sự tồn tại của message trong broker hay số lần consumer thực thi thành công. `@ApplicationModuleTest` hỗ trợ bootstrap phần ứng dụng theo module nhưng các mode bootstrap khác nhau tạo ra phạm vi quan sát khác nhau. Một `Scenario` nhìn thấy event được phát không tự động đảm bảo giao dịch của consumer đã commit thành công.

Phân loại các điểm mù thành bốn nhóm để tránh chọn sai loại test:

1. **Ngoài đồ thị dependency tĩnh:** reflection, `Class.forName`, mã nạp động, REST client gọi service/module khác, SQL truy cập thẳng bảng thuộc module khác.
2. **Ngoài ranh giới bootstrap test:** bean được mock, module không bootstrap, listener chỉ đăng ký trong profile khác, wiring có điều kiện.
3. **Ngoài đường chạy thành công:** timeout, redelivery, crash trước/sau commit, xử lý đồng thời và dữ liệu bẩn.
4. **Ngoài môi trường test:** migration, quyền database, broker, schema của message, cấu hình secrets, thời điểm deploy và CI filter khiến test bị skip.

Với mỗi điểm mù, ghi hai câu riêng biệt: **điều test hiện tại chứng minh** và **điều nó chưa chứng minh**. Chỉ chấp nhận mở rộng coverage khi test mới nhắm chính xác phần thứ hai.

## 4. Kiểm tra lại ranh giới kiến trúc bằng phép thử âm tính

Đặt bài kiểm tra cấu trúc ở phạm vi root ứng dụng, độc lập với việc có khởi tạo Spring context hay database. Đây là test JUnit 5 thực sự có assertion, phù hợp để chạy sớm trong CI:

```java
package com.acme.shop;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

@Tag("architecture")
class ModuleArchitectureTest {

    @Test
    void obeysDeclaredModuleBoundaries() {
        assertDoesNotThrow(() ->
                ApplicationModules.of(ShopApplication.class).verify());
    }
}
```

Nếu `checkout` chỉ được dùng API công khai của `billing`, khai báo ràng buộc ở `checkout/package-info.java` và interface ở `billing/api/package-info.java` như sau (hai đoạn là ví dụ cho package đã tồn tại):

```java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "billing::api")
package com.acme.shop.checkout;
```

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.billing.api;
```

Thử cố ý cho một class `checkout` import một **public class** nằm trong `com.acme.shop.billing.internal` rồi gọi nó. Nếu code vẫn biên dịch nhưng `ModuleArchitectureTest` không đỏ, kiểm tra lại module detection, package root, tên module và việc đặt class đó vào named interface. Sau khi ghi log, hoàn nguyên thay đổi và xác nhận test xanh. Không dùng class package-private để làm phép thử này vì compiler sẽ chặn trước, khiến không đánh giá được Modulith.

Ghi lại giới hạn: kể cả khi phép thử trên thành công, `Class.forName("...")`, HTTP/gRPC và SQL không thể được coi là đã kiểm chứng bởi đồ thị type. Với các đường đó cần rule bổ sung (ví dụ ArchUnit cho quy ước truy cập) hoặc test tích hợp thực sự tại điểm giao tiếp.

## 5. Kiểm tra lại độ tin cậy của module slice

Một test `STANDALONE` có thể chứng minh policy nội bộ tốt nhưng không chứng minh `checkout` chạy được với dependency thật của `billing` hoặc `catalog`. So sánh tối thiểu hai mức bootstrap và cố ý làm sai một dependency tại lần thử riêng.

```java
package com.acme.shop.checkout;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("module")
@ApplicationModuleTest(mode = BootstrapMode.STANDALONE)
class CheckoutStandaloneTest {

    @Autowired CheckoutPolicy checkoutPolicy;

    @Test
    void rejectsNonPositiveQuantity() {
        assertThat(checkoutPolicy.canOrder(0)).isFalse();
        assertThat(checkoutPolicy.canOrder(-1)).isFalse();
    }
}
```

`CheckoutPolicy.canOrder(int)` là policy giả định của lab, cần được triển khai trong module của người học. Test này có hai assertion về quy tắc, nhưng chỉ quan sát đúng bean của slice. Bổ sung một test khác với `@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)` để dùng **dependency thật** mà checkout khai báo; assertion phải đo kết quả nghiệp vụ, chẳng hạn báo giá từ catalog, thay vì chỉ `assertThat(service).isNotNull()`. Nếu quy tắc đi qua event tới module **không được checkout phụ thuộc trực tiếp**, `DIRECT_DEPENDENCIES` không bảo đảm consumer ấy có mặt: dùng một test tích hợp toàn ứng dụng cho đường đi đó.

Phép thử âm tính: ở một nhánh tạm, làm sai cấu hình bean hoặc adapter cần thiết trong profile CI; xác nhận test wiring/behavior đỏ. Ghi rõ trường hợp test `STANDALONE` vẫn xanh trong khi test full integration đỏ: đó là bằng chứng về **giới hạn quan sát của slice**, không phải test sai.

## 6. Phân biệt “đã phát sự kiện” với “đã hoàn thành nghiệp vụ”

Đầu tiên, dùng `Scenario` để khẳng định module nguồn phát đúng loại event với correlation key có thể truy vết:

```java
package com.acme.shop.checkout;

import java.util.UUID;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@Tag("event")
@ApplicationModuleTest
class CheckoutEventContractTest {

    @Autowired CheckoutService checkout;

    @Test
    void emitsOrderPlacedWithCorrectId(Scenario scenario) {
        UUID orderId = UUID.randomUUID();
        // Fixture của lab đã tạo đơn hàng hợp lệ có ID này.
        scenario.stimulate(() -> checkout.submit(orderId))
                .andWaitForEventOfType(OrderPlaced.class)
                .matching(event -> event.orderId().equals(orderId))
                .toArrive();
    }
}
```

Đây là bằng chứng về **event được quan sát** trong test, chưa đủ để khẳng định invoice đã được lưu. Nếu nghiệp vụ kỳ vọng listener ở `billing` cập nhật repository, cần một test tích hợp qua đường chạy thật. Ví dụ bên dưới dùng Awaitility (`org.awaitility:awaitility`) để chờ hiệu ứng bất đồng bộ và assertion trên trạng thái bền vững:

```java
package com.acme.shop;

import java.time.Duration;
import java.util.UUID;
import com.acme.shop.billing.InvoiceRepository;
import com.acme.shop.checkout.CheckoutService;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Tag("integration")
@SpringBootTest
class CheckoutBillingFlowTest {

    @Autowired CheckoutService checkout;
    @Autowired InvoiceRepository invoices;

    @Test
    void persistsOneInvoiceAfterOrderPlaced() {
        UUID orderId = UUID.randomUUID();
        // Fixture tạo đơn hợp lệ; test không đặt @Transactional.
        checkout.submit(orderId);

        await().atMost(Duration.ofSeconds(10))
                .untilAsserted(() -> assertThat(
                        invoices.countByOrderId(orderId)).isEqualTo(1L));
    }
}
```

Test full context này phải thực sự tạo consumer và dùng cấu hình listener mà sản phẩm chạy. Assertion `countByOrderId == 1` chứng minh đã có hiệu ứng mong đợi tại thời điểm kiểm tra; **chưa đủ để loại trừ** một lần xử lý trùng đến muộn. `UUID` riêng từng test giúp tránh dữ liệu cũ. Không thay timeout cho điều kiện kết thúc nghiệp vụ; chỉ chờ trạng thái mong đợi. Muốn chứng minh không nhân đôi, cần kiểm thử riêng việc xử lý lại sau khi hai lượt đã hoàn tất như mục 7. Nếu listener gọi dịch vụ ngoài, dùng test contract hoặc môi trường tích hợp có thật cho endpoint đó, không coi việc event xuất hiện trong bộ nhớ là đã hoàn thành giao dịch ngoài.

## 7. Đánh giá transaction, redelivery và tính idempotent

Một test gắn `@Transactional` có thể rollback toàn bộ thay đổi sau test và vô tình che vấn đề phát event **sau commit**. Hãy thử đường chạy không bọc transaction ở lớp test, để transaction thuộc application service/listener, rồi xác nhận hiệu ứng bền vững. Phân biệt ít nhất ba thời điểm lỗi: trước khi lưu event publication, sau khi lưu nhưng trước khi consumer hoàn thành, và sau side effect nhưng trước khi đánh dấu publication hoàn tất.

Nếu consumer có thể nhận lại một `OrderPlaced`, cùng event phải không tạo hai invoice. Trong ví dụ này `InvoiceEventHandler` ủy quyền công việc cho `InvoiceService.ensureCreatedFor(UUID)`; test gọi service đồng bộ hai lần để cô lập invariant idempotency, vì gọi thẳng một listener có `@ApplicationModuleListener` có thể vẫn đi qua proxy bất đồng bộ. Cần thêm test với publication registry hoặc broker thực nhằm kiểm tra cơ chế redelivery:

```java
package com.acme.shop.billing;

import java.util.UUID;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("integration")
@SpringBootTest
class InvoiceIdempotencyTest {

    @Autowired InvoiceService invoiceService;
    @Autowired InvoiceRepository invoices;

    @Test
    void duplicateDeliveryMustNotCreateTwoInvoices() {
        UUID orderId = UUID.randomUUID();
        invoiceService.ensureCreatedFor(orderId);
        invoiceService.ensureCreatedFor(orderId);

        assertThat(invoices.countByOrderId(orderId)).isEqualTo(1L);
    }
}
```

Điều kiện của bài là service phải có cách xác định cùng một nghiệp vụ (ví dụ unique constraint theo `order_id` và xử lý duplicate an toàn). Test gọi trực tiếp service như trên **chỉ** kiểm thử logic xử lý trùng và transaction của service, không kiểm thử listener scheduling hay retry. Trong test runtime riêng, gây lỗi có kiểm soát ở lần xử lý đầu, khôi phục consumer, phát lại và kiểm tra kết quả cuối; không yêu cầu `exactly once` từ message delivery nếu ứng dụng chỉ bảo đảm *at least once*. Kiểm tra event publication registry theo storage và phiên bản được cấu hình để phân biệt **publication chưa hoàn thành** với **side effect đã xảy ra**.

## 8. Đưa persistence về đúng điều kiện vận hành

Nếu production dùng PostgreSQL nhưng test chỉ chạy H2, dấu xanh chưa kiểm chứng các sai khác như SQL syntax, lock, unique constraint, JSON type và migration. Testcontainers giúp chạy đúng database engine; Spring Boot 3.1+ có `@ServiceConnection` để cung cấp connection details cho context.

```java
package com.acme.shop;

import java.util.UUID;
import com.acme.shop.billing.InvoiceRepository;
import com.acme.shop.billing.InvoiceService;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("database")
@Testcontainers
@SpringBootTest
class InvoicePostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @Autowired InvoiceService invoiceService;
    @Autowired InvoiceRepository invoices;

    @Test
    void invoiceSurvivesRealDatabaseCommit() {
        UUID orderId = UUID.randomUUID();
        invoiceService.ensureCreatedFor(orderId); // service tự quản lý transaction

        assertThat(invoices.countByOrderId(orderId)).isEqualTo(1L);
    }
}
```

Ở đây `InvoiceService.ensureCreatedFor(UUID)` là API giả định của lab; thay bằng application service thật. Để test xác thực migration, hãy khởi động container trống, cho Flyway/Liquibase chạy **đúng script production**, rồi thực hiện insert/read/constraint test trên bảng thật. Không dùng `ddl-auto=create` thay thế migration trong phép thử đó. Với dữ liệu cần commit thật, tránh `@Transactional` trên test; thực hiện cleanup theo khóa thử nghiệm hoặc dùng container cô lập. Nếu database chạy async projection, dùng Awaitility như mục 6 và nêu rõ thời hạn chờ.

Đầu ra của mục này gồm: engine/version đã chạy, migration version, bằng chứng constraint mà DB thực sự áp dụng và loại lỗi sẽ lọt qua nếu tiếp tục chỉ dùng database giả lập.

## 9. Phần nào vẫn nằm ngoài Spring Modulith verification?

Đối với giao tiếp HTTP/gRPC, broker, batch job hoặc hệ thống danh tính bên ngoài, thêm phép thử contract tại **cổng kết nối thật**. Ví dụ, thay đổi trường bắt buộc của message ở consumer phải khiến schema/consumer contract test đỏ; thay `200` bằng `429` hoặc timeout phải kích hoạt đúng policy retry/circuit breaker. Dùng WireMock, MockWebServer, broker container hoặc môi trường staging phù hợp thay vì một mock trả kết quả thành công cố định.

Thẩm định các chiều sau bằng bảng “kịch bản → phép thử → assertion → điểm mù còn lại”:

| Kịch bản | Assertion mang giá trị | Giới hạn vẫn phải ghi nhận |
| --- | --- | --- |
| HTTP downstream timeout | Lời gọi có deadline; trạng thái đơn không chuyển nhầm sang hoàn tất | DNS/TLS/routing ở mạng triển khai thật |
| Broker gửi trùng / sai thứ tự | Một invoice cho mỗi order; state không lùi | Partition/rebalance và tải cao ở môi trường thực |
| Consumer crash sau side effect | Retry dẫn đến trạng thái cuối đúng, không nhân đôi dữ liệu | Khả năng giám sát/replay khi hạ tầng bị chia cắt |
| Cấu hình role/quyền DB sai | Startup/test migration thất bại với credential quyền tối thiểu | Chính sách cấp quyền production có thể khác |
| Client bỏ trường bắt buộc | Contract test trả 4xx hoặc báo lỗi schema rõ ràng | Phiên bản client cũ ngoài phạm vi test |

Đừng đánh dấu rủi ro đã đóng chỉ vì một phần được mock. Với mỗi phụ thuộc ngoài, nêu rõ môi trường và phiên bản đã thử, hành vi lỗi đã chủ động kích hoạt và điều không tái tạo được trong CI.

## 10. Đo *khả năng bắt lỗi* bằng negative probes

Chạy phép thử âm tính trong nhánh/worktree tạm theo thứ tự: (1) lưu baseline xanh, (2) đưa vào **một** lỗi có chủ đích, (3) chạy đúng test/gate cần bắt lỗi, (4) giữ log và assertion thất bại, (5) hoàn nguyên lỗi, (6) xác nhận xanh lại. Không merge mã tạo lỗi và không gộp nhiều thay đổi vào một probe: nếu test đỏ sẽ không biết nguyên nhân nào thực sự bị phát hiện.

| Probe | Thay đổi cố ý | Kết quả mong đợi | Nếu vẫn xanh thì điều tra |
| --- | --- | --- | --- |
| `P-ARCH` | Thêm import trực tiếp vào `billing.internal` từ `checkout` | `ApplicationModules.verify()` báo vi phạm dependency | Root package, allowed dependency, named interface, test filter |
| `P-EVENT` | Đổi correlation ID hoặc không phát `OrderPlaced` | `CheckoutEventContractTest` đỏ | Test có kích hoạt code path và `matching` đúng ID chưa? |
| `P-CONSUMER` | Bỏ lưu invoice trong listener | `CheckoutBillingFlowTest` hết hạn chờ và đỏ | Listener có nằm trong context? Có dùng repository thật không? |
| `P-REDELIVERY` | Bỏ kiểm tra trùng trong `InvoiceService` | `InvoiceIdempotencyTest` nhận count khác 1 | Unique constraint DB có chặn trước; test đang khẳng định đúng tầng nào? |
| `P-DB` | Tạm bỏ migration tạo index/constraint cần thiết | Migration/constraint integration test đỏ | Test có dùng migration thật và PostgreSQL không? |

**Bẫy cần ghi lại:** một test có thể đỏ do lỗi compile, container không khởi động hoặc thiếu secret. Đó chưa phải bằng chứng probe đã được bắt ở tầng nghiệp vụ. So khớp exception/cause với lỗi đã gieo; sửa môi trường rồi chạy lại khi cần. Với `P-REDELIVERY`, nếu unique constraint chặn duplicate nhưng listener ném exception làm retry vô hạn thì invariant count vẫn đúng song nghiệp vụ chưa đạt: cần assertion bổ sung rằng lần lặp được xử lý hoặc bỏ qua an toàn.

## 11. Thiết lập quality gate và viết báo cáo giới hạn còn mở

Sắp xếp gate theo chi phí và tốc độ phản hồi: **kiến trúc/JUnit thuần → module slice → event/DB integration → contract và thử lỗi hạ tầng**. Chạy cùng bộ lọc test ở local lẫn CI; nếu tách các `@Tag`, phải có ít nhất một pipeline bắt buộc bao phủ tất cả tag quan trọng. Bản mẫu GitHub Actions dưới đây cần thay đúng JDK, wrapper, cache và container runtime của repository:

```yaml
name: modulith-verification
on: [push, pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Run architecture, module and integration tests
        run: ./gradlew test --no-daemon
      - name: Keep JUnit evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-results
          path: '**/build/test-results/test/*.xml'
```

Quality gate chỉ được coi là có hiệu lực khi job là **required check**, không bỏ qua integration bằng profile/filter, fail khi có test lỗi, và có đường dẫn tới log/JUnit XML. Nếu test tích hợp phụ thuộc Docker mà runner không hỗ trợ, cập nhật hạ tầng chạy test hoặc đánh dấu khoảng trống; không lặng lẽ `@Disabled` để đạt màu xanh.

Tạo báo cáo cuối với mẫu một dòng cho từng giới hạn:

| ID | Kịch bản lỗi và tác động | Bằng chứng hiện có | Mức ưu tiên | Quyết định và người sở hữu |
| --- | --- | --- | --- | --- |
| `G-01` | Reflection gọi lớp internal, có thể phá ranh giới module | Static verify không nhìn thấy string-based lookup; chưa có probe | P1 | Thêm rule/scan tại điểm tạo object; kiến trúc sư module |
| `G-02` | Invoice nhân đôi khi event bị phát lại | `P-REDELIVERY` và JUnit XML; cần xác nhận runtime retry | P0 | Test registry/broker + unique constraint; chủ module billing |
| `G-03` | Migration production không tương thích SQL | Test PostgreSQL có/không chạy migration thật | P0/P1 theo dữ liệu | Khóa migration test vào CI; người phụ trách persistence |

Xếp hạng theo hậu quả thực tế và khả năng xảy ra: **P0** cho mất dữ liệu, sai tiền hoặc ranh giới bắt buộc có thể bị vi phạm; **P1** cho hồi quy nghiệp vụ/tích hợp đáng kể; **P2** cho rủi ro tác động nhỏ có biện pháp quan sát và phục hồi. Mỗi rủi ro chưa đóng cần owner, lý do chấp nhận, biện pháp giảm thiểu và thời điểm xem xét lại. Không gán “đã hết giới hạn” vì về bản chất bộ verification chỉ giảm rủi ro trong phạm vi điều kiện đã kiểm tra.

**Tiêu chí hoàn thành bài thực hành:** ma trận mô tả được ít nhất sáu khoảng trống thực tế; có tối thiểu ba negative probes tạo lỗi và hoàn nguyên được với log hai chiều; có assertion về event **và** side effect; có một kiểm tra transaction/idempotency và một bài test database theo engine production; CI lưu kết quả và chặn pull request khi test bắt buộc đỏ; báo cáo tách bạch mục đã chứng minh, mục chỉ xanh trên happy path và rủi ro còn mở. Người phản biện có thể nhìn vào ID của từng khoảng trống để tìm ngay test, log và quyết định xử lý tương ứng.
