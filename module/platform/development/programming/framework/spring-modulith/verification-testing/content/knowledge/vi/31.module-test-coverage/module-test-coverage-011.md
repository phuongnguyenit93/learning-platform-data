# Theo dõi khoảng trống kiểm thử theo rủi ro

Trong chương **Coverage theo module**, mục tiêu của việc theo dõi khoảng trống kiểm thử là trả lời một câu hỏi thực dụng: **rủi ro nghiệp vụ hoặc kiến trúc nào chưa có bằng chứng kiểm thử đủ mạnh để chặn hồi quy?** Một module có 90% line coverage vẫn có thể bị tính phí hai lần, phát sự kiện trước khi giao dịch commit hoặc truy cập trực tiếp implementation của module khác.

Với **SPRING_MODULITH_VERIFICATION_TESTING**, ta phối hợp `ApplicationModules.verify()` để kiểm tra ranh giới và quy tắc phụ thuộc; `@ApplicationModuleTest` với Java/JUnit để bảo vệ hành vi trong module; kiểm thử cơ sở dữ liệu, sự kiện và tích hợp để xác nhận các hiệu ứng sau commit; cuối cùng dùng **quality gate CI** để ngăn một khoảng trống rủi ro cao bị bỏ quên. Bài tập trung vào **quy trình lập, cập nhật và đóng khoảng trống theo rủi ro** chứ không lặp lại phần nhập môn Spring Modulith.

Ví dụ xuyên suốt là module `orders` của một ứng dụng bán hàng. Các API và quy tắc dưới đây là **hợp đồng minh họa cần triển khai trong ứng dụng mẫu**; không mặc định đây là hành vi của mọi hệ thống đặt hàng.

## 1. Xác định đơn vị coverage bằng kịch bản rủi ro

Khi lập kế hoạch test cho một application module, một file test hoặc một class Java không phải đơn vị phản ánh rủi ro tốt nhất. Hãy dùng **kịch bản có thể quan sát ở ranh giới**:

> Với điều kiện X, khi caller thực hiện hành động Y qua public API, hệ thống phải bảo đảm kết quả Z; nếu Z sai, hậu quả kinh doanh là H.

Với `orders`, một số kịch bản là:

- Cùng `requestId` được gửi lại sau timeout phải trả về **cùng order ID**, tránh tạo hai đơn.
- Số lượng bằng 0 phải bị từ chối; không được tạo đơn hợp lệ từ đầu vào này.
- Đơn xác nhận phải đọc được trong một giao dịch khác sau commit.
- Xác nhận lặp không được publish hai `OrderConfirmed` cho cùng đơn nếu hợp đồng quy định phát đúng một lần.
- Consumer `shipping` phải nhận được thông tin xác nhận sau commit và không tạo hai yêu cầu giao hàng khi nhận event trùng.
- Module khác không được import `orders.internal`, dù các bài test nghiệp vụ vẫn có thể xanh.

Sáu kịch bản trên cần **các lớp bằng chứng khác nhau**. Test public API không tự chứng minh listener bất đồng bộ đã chạy; `ApplicationModules.verify()` không tự chứng minh idempotency hoặc transaction thực tế.

Mỗi kịch bản trong sổ theo dõi nên có ít nhất: mã rủi ro, module sở hữu, hậu quả nếu sai, cách tái hiện, loại kiểm thử mong đợi, mức ưu tiên, trạng thái bằng chứng, người phụ trách và hạn xử lý nếu có.

## 2. Chấm điểm ưu tiên có thể giải thích, tránh chạy theo tỷ lệ dòng

Một rubric đơn giản cho nhóm gồm:

- **Impact (I), 1–5:** 1 là bất tiện nhỏ, 5 là mất tiền, dữ liệu sai nghiêm trọng hoặc gián đoạn dịch vụ quan trọng.
- **Likelihood (L), 1–5:** 1 là rất hiếm trong ngữ cảnh hiện tại, 5 là thường xuyên hoặc dễ tái hiện.
- **Điểm ưu tiên R = I × L:** từ 1 đến 25. Điểm càng cao thì khoảng trống càng cần được xử lý sớm.

Đây là **rubric minh họa do nhóm tự đặt**, không phải thuật toán hoặc tiêu chuẩn Spring Modulith. Nên lưu lý do định tính: tần suất endpoint, lịch sử incident, khả năng retry, thay đổi gần đây, mức độ phụ thuộc vào broker/database hoặc số lượng consumer. Khi thiếu dữ liệu, ghi `UNKNOWN` thay vì tự gán điểm thấp.

Một cách phân nhóm có thể dùng:

| Điểm R | Mức ưu tiên gợi ý | Quy tắc xử lý minh họa |
| --- | --- | --- |
| 15–25 | Cao | Phải có test xác nhận tại lớp phù hợp và kết quả chạy trong CI trước khi chấp nhận thay đổi liên quan |
| 8–14 | Trung bình | Bổ sung test trong đợt thay đổi gần nhất hoặc có owner và thời hạn cụ thể |
| 1–7 | Thấp | Theo dõi, cân nhắc sampling/test tổng hợp; tăng ưu tiên nếu lịch sử lỗi thay đổi |

**Phân biệt “cần test” với “cần thêm một bài test”.** Nếu một integration test đã chứng minh trực tiếp kết quả sau commit và chạy ổn định, không nhất thiết tạo thêm test giống hệt ở một class khác. Ngược lại, một test chỉ assert controller trả HTTP 200 không đủ chứng minh “đơn không bị tạo hai lần”.

## 3. Lập risk register và tìm khoảng trống có bằng chứng

Bảng ví dụ sau giả định nhóm đã kiểm tra code và có bằng chứng chạy test tương ứng. Trạng thái ở cột cuối **chỉ để minh họa cách ghi**, không phải kết quả đã chạy trong bài học này.

| ID | Rủi ro của `orders` | I | L | R | Bằng chứng cần có | Trạng thái ví dụ |
| --- | --- | ---: | ---: | ---: | --- | --- |
| R-01 | Retry cùng `requestId` tạo hai đơn | 5 | 4 | **20** | API idempotency + kiểm tra dữ liệu | Verified |
| R-02 | Event `OrderConfirmed` không đến `shipping` sau commit | 5 | 3 | **15** | Integration test publisher → consumer | **Gap** |
| R-03 | Số lượng không hợp lệ được chấp nhận | 4 | 4 | **16** | `@ApplicationModuleTest` nhánh lỗi | Verified |
| R-04 | Xác nhận xong nhưng dữ liệu không bền sau commit | 4 | 3 | **12** | DB test hai transaction | Verified |
| R-05 | Xác nhận lặp publish event hai lần | 4 | 3 | **12** | `PublishedEvents` xác nhận số lần phát | Verified |

Quy ước trạng thái nên tách rõ:

| Trạng thái | Ý nghĩa | Có tính là đã được bảo vệ? |
| --- | --- | --- |
| **Gap** | Không có test phù hợp hoặc không có bằng chứng chạy | Không |
| **Partial** | Test chỉ bao phủ một phần, môi trường thiếu thành phần quan trọng hoặc còn bỏ sót nhánh lỗi | Không, cho đến khi điều kiện chấp nhận được xác nhận |
| **Verified** | Có assertion đúng rủi ro, test pass trong môi trường phù hợp, có bằng chứng từ lần chạy được chấp nhận | Có |
| **Regressed** | Test từng pass nhưng nay thất bại hoặc không còn được chạy | Không |

Một test mới được viết vào repository **chưa tự động thành Verified**. Chỉ chuyển trạng thái sau khi test chạy thành công, assertion thực sự đánh trúng rủi ro và CI/job có thể tái hiện được.

Ở ví dụ, **R-02** là khoảng trống phải ưu tiên dù bốn test khác đã xanh: event đã được publish không đồng nghĩa consumer đã xử lý sau commit. Đây cũng là lý do phải có một người sở hữu cụ thể và hành động tiếp theo, chẳng hạn “bổ sung integration test với giao dịch commit và dữ liệu `shipping` quan sát được”.

## 4. Nối từng rủi ro với lớp kiểm thử phù hợp

Một kịch bản rủi ro nên được kiểm chứng ở lớp **thấp nhất nhưng vẫn nhìn thấy hậu quả cần ngăn**. Chọn test chỉ vì nó chạy nhanh có thể dẫn đến kết luận sai.

| Rủi ro | Lớp kiểm thử ưu tiên | Điều phải quan sát | Điều test này chưa thể khẳng định |
| --- | --- | --- | --- |
| R-03 — đầu vào sai | `@ApplicationModuleTest` hoặc unit test public service | Exception/kết quả lỗi, không chấp nhận đầu vào | Tính bền dữ liệu và commit |
| R-01 — retry tạo trùng | Module test + persistence assertion | Cùng ID, không thêm bản ghi | Retry từ hạ tầng/broker bên ngoài |
| R-04 — dữ liệu sau commit | Module test với DB, giao dịch tách biệt | Có thể đọc đúng trạng thái từ transaction mới | Quy tắc isolation/concurrency chưa được test |
| R-05 — event phát lặp | `PublishedEvents` của Spring Modulith | Kiểu, payload và số event được publish | Consumer đã commit hoặc xử lý thành công |
| R-02 — consumer sau commit | Integration test thực, consumer được bootstrap | Quan sát kết quả từ `shipping` sau commit | Các kiểu hỏng khác chưa đưa vào tình huống |
| Sai chiều phụ thuộc | JUnit gọi `ApplicationModules.verify()` | Vi phạm API/cycle/allowed dependencies trong đồ thị tĩnh | Logic nghiệp vụ, SQL truy cập bảng ngoài, broker runtime |

Dùng thêm kiểm thử hợp đồng của API ngoài (HTTP/message) nếu caller nằm ngoài ứng dụng. **Line/branch coverage và mutation testing là tín hiệu bổ trợ**: chúng có thể gợi ý vùng chưa được thực thi hoặc assertion yếu, nhưng không thay thế risk register vì không mô tả hậu quả nghiệp vụ.

Đối với rủi ro cao liên quan đến rollback, double charge, mất event hoặc mất dữ liệu, một integration test chậm hơn thường vẫn đáng chạy trong pipeline phù hợp.

## 5. Định nghĩa public API để đặt các assertion rủi ro

Dùng một hợp đồng đơn giản của module `orders`. Các file minh họa dưới đây thuộc package API `com.acme.shop.orders`:

**`Orders.java`**

```java
package com.acme.shop.orders;

import java.util.Optional;
import java.util.UUID;

public interface Orders {

    UUID open(UUID requestId, String sku, int quantity);

    OrderView confirm(UUID orderId);

    Optional<OrderView> get(UUID orderId);
}
```

**`OrderStatus.java` và `OrderView.java`**

```java
package com.acme.shop.orders;

public enum OrderStatus {
    DRAFT, CONFIRMED
}
```

```java
package com.acme.shop.orders;

import java.util.UUID;

public record OrderView(
        UUID orderId,
        String sku,
        int quantity,
        OrderStatus status
) {
}
```

**`OrderConfirmed.java`**

```java
package com.acme.shop.orders;

import java.util.UUID;

public record OrderConfirmed(UUID orderId) {
}
```

Hợp đồng ví dụ quy định:

1. `open(requestId, sku, quantity)` từ chối `quantity <= 0` bằng `IllegalArgumentException`.
2. Gọi `open` lặp với **cùng request ID và cùng payload** phải trả lại cùng order ID. Request ID trùng nhưng payload khác cần một quy tắc xử lý riêng.
3. `confirm(orderId)` đổi đơn từ `DRAFT` sang `CONFIRMED`; xác nhận lặp không phát lại event.
4. `get(orderId)` trả về trạng thái đã lưu; một module khác chỉ cần biết các kiểu công khai này.
5. Khi chuyển trạng thái thành công, module publish một `OrderConfirmed`; trách nhiệm xử lý sau commit của `shipping` được kiểm chứng ở lớp integration.

Các interface/record là **contract ví dụ**. Để chạy các test bên dưới, dự án mẫu phải có Spring bean triển khai `Orders`, repository/transaction và cấu hình database phù hợp. Bài này chỉ trình bày mã kiểm chứng và cách theo dõi gap, không tuyên bố các test tự chạy khi chưa có implementation.

## 6. Ưu tiên viết `@ApplicationModuleTest` cho R-01, R-03 và R-05

Đặt JUnit 5 test trong `src/test/java/com/acme/shop/orders/OrdersRiskTests.java` để Spring Modulith nhận biết phạm vi module từ package test.

```java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrdersRiskTests {

    @Autowired Orders orders;

    @Test
    void r01_sameRequestDoesNotCreateAnotherOrder() {
        UUID requestId = UUID.randomUUID();

        UUID first = orders.open(requestId, "SKU-01", 2);
        UUID retry = orders.open(requestId, "SKU-01", 2);

        assertThat(retry).isEqualTo(first);
        assertThat(orders.get(first)).contains(
                new OrderView(first, "SKU-01", 2, OrderStatus.DRAFT));
    }

    @Test
    void r03_rejectsInvalidQuantity() {
        assertThatThrownBy(() ->
                orders.open(UUID.randomUUID(), "SKU-01", 0))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void r05_confirmPublishesOneEventDespiteRetry(
            PublishedEvents events
    ) {
        UUID id = orders.open(
                UUID.randomUUID(), "SKU-01", 2);

        orders.confirm(id);
        orders.confirm(id);

        assertThat(events.ofType(OrderConfirmed.class)
                .matching(OrderConfirmed::orderId, id))
                .hasSize(1);
    }
}
```

**Bằng chứng thực sự mà các assertion tạo ra:**

- R-01 kiểm tra idempotency qua ID và API `get`. Nếu tiêu chí chấp nhận còn yêu cầu **chính xác một hàng dữ liệu**, bổ sung persistence assertion qua repository test nội bộ hoặc SQL phù hợp; hiện tại không được kết luận đã chứng minh số bản ghi chỉ bằng hai assertion.
- R-03 kiểm tra loại lỗi theo contract. Khi đánh giá rủi ro “không ghi dữ liệu sau lỗi”, cần thêm assertion trạng thái database hoặc số lượng bản ghi.
- R-05 kiểm tra một event đã được publish, kể cả khi gọi confirm lại. `PublishedEvents` **không kiểm tra** rằng consumer đã xử lý thành công và không đồng nghĩa event được gửi qua message broker.

Trong `@ApplicationModuleTest`, mode bootstrap mặc định hướng đến module đang xét. Nếu nó phụ thuộc vào hệ thống ngoài, hãy dùng fake/test double cho adapter rõ ràng hoặc mở rộng phạm vi có lý do; không tăng toàn bộ context chỉ để một bài test xanh.

**Hành động trong risk register:** chỉ ghi R-01/R-03/R-05 là Verified sau khi chạy được test trên implementation thật và bổ sung bằng chứng còn thiếu nếu mô tả rủi ro đòi hỏi nhiều hơn các assertion hiện tại.

## 7. Với R-04, kiểm chứng tính bền sau commit

Kịch bản “đã xác nhận nhưng mất trạng thái” cần nhìn thấy kết quả từ **một giao dịch mới**; một assertion đọc lại trong persistence context hiện tại có thể quá yếu.

```java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@ApplicationModuleTest
class OrdersPersistenceRiskTests {

    @Autowired Orders orders;
    @Autowired PlatformTransactionManager transactionManager;

    @Test
    void r04_confirmedStateSurvivesCommit() {
        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        UUID id = tx.execute(status ->
                orders.open(UUID.randomUUID(), "SKU-01", 2));

        assertThat(id).isNotNull();

        tx.executeWithoutResult(status -> orders.confirm(id));

        OrderView observed = tx.execute(status ->
                orders.get(id).orElseThrow());

        assertThat(observed.status())
                .isEqualTo(OrderStatus.CONFIRMED);
    }
}
```

Bài test **không đặt `@Transactional` ở class/method test**. Với transaction manager thông thường, mỗi lời gọi `TransactionTemplate.execute(...)` mở và hoàn tất transaction riêng nếu chưa có transaction bao ngoài. Điều này giúp xác nhận dữ liệu đã commit trước khi đọc lại.

Cần cấu hình DB test tách khỏi production, chạy migration/schema và dùng repository thật; `@ApplicationModuleTest` có thể tự bootstrap module, nhưng **không tự cấp sẵn database phù hợp**. Nếu module có nhiều transaction manager, phải chọn đúng manager của dữ liệu đang kiểm tra.

R-04 chỉ được xem là đã khép khi test thực sự pass và phản ánh quy tắc lưu trữ của hệ thống. Test này chưa bao phủ deadlock, race condition, rollback khi mất kết nối hoặc read replica chậm; các rủi ro đó cần ID riêng nếu tác động đáng kể.

## 8. R-02: đo đường event sau commit đến consumer

Đây là trường hợp dễ bị báo coverage quá mức: `PublishedEvents` chứng minh publisher phát `OrderConfirmed`, nhưng không chứng minh consumer `shipping` đã nhận, xử lý và lưu kết quả **sau commit**.

Với một consumer được thiết kế dùng `@ApplicationModuleListener`, integration test cần:

1. Bootstrap publisher và consumer thật trong cùng một Spring Boot test context hoặc cấu hình tích hợp phù hợp.
2. Tạo đơn và xác nhận qua public API trong những giao dịch **commit thật**.
3. Đọc kết quả từ API/query đáng tin cậy do `shipping` cung cấp.
4. Nếu xử lý bất đồng bộ, đợi điều kiện với timeout và fail khi không đạt; không dùng `Thread.sleep` như một assertion.
5. Nếu rủi ro có retry, kiểm tra thêm consumer idempotent khi cùng event được giao lại.

Ví dụ JUnit định hướng tích hợp, giả sử dự án đã có API `ShipmentQuery` của module `shipping` và dependency Awaitility:

```java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import com.acme.shop.orders.Orders;
import com.acme.shop.shipping.ShipmentQuery;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class OrdersShippingIntegrationTests {

    @Autowired Orders orders;
    @Autowired ShipmentQuery shipments;
    @Autowired PlatformTransactionManager transactionManager;

    @Test
    void r02_shippingObservesConfirmationAfterCommit() {
        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        UUID id = tx.execute(status ->
                orders.open(UUID.randomUUID(), "SKU-01", 2));

        tx.executeWithoutResult(status -> orders.confirm(id));

        await().atMost(Duration.ofSeconds(10))
                .untilAsserted(() ->
                        assertThat(shipments.requestCount(id))
                                .isEqualTo(1));
    }
}
```

`ShipmentQuery.requestCount(UUID)` trong ví dụ là **contract minh họa cần tồn tại trong ứng dụng mẫu**. Nếu consumer gửi message ra broker bên ngoài, test phải khởi động/test được broker hoặc adapter tương ứng; `@SpringBootTest` một mình chưa bảo đảm hạ tầng đó hoạt động.

Cần tránh `@Transactional` bao ngoài toàn test vì transaction rollback có thể ngăn listener phụ thuộc vào after-commit được kích hoạt. Đối với rủi ro giao event lặp, chạy thêm một test mô phỏng *at-least-once delivery* và assert `requestCount(id) == 1` sau nhiều lần xử lý.

**Trạng thái R-02 vẫn là Gap** cho đến khi môi trường, consumer thật và assertion sau commit đã được kiểm chứng. Việc viết khung test trên trang tài liệu chưa đủ để chuyển trạng thái.

## 9. Đừng bỏ quên rủi ro ranh giới kiến trúc

Các rủi ro runtime ở trên không bảo đảm chiều phụ thuộc được giữ đúng. Một thay đổi có thể không làm hỏng kết quả đơn hàng nhưng khiến `shipping` import `orders.internal.OrderRepository`, tạo coupling khó kiểm thử về sau.

Dùng một test JUnit riêng:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void rejectsInvalidModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ShopApplication` là lớp Spring Boot gốc của ví dụ. `ApplicationModules.verify()` kiểm chứng các quy tắc kiến trúc Spring Modulith hỗ trợ, trong đó có **dependency cycle**, truy cập qua API module và giới hạn phụ thuộc được khai báo. Nó kiểm chứng đồ thị tĩnh của các application module được phát hiện; không tự thấy được mọi quan hệ runtime qua SQL trực tiếp, reflection hoặc message broker.

Với legacy app, bài test toàn cục có thể đỏ vì các vi phạm **cũ, chưa liên quan** đến thay đổi đang xét. Khi đó lập baseline có bằng chứng, giao owner và kế hoạch xử lý từng vi phạm. Không diễn giải `verify()` đỏ thành lỗi của mọi module, cũng không tuyên bố đạt quality gate kiến trúc nếu vẫn tồn tại các cycle chưa xử lý.

Có thể thêm dòng riêng trong sổ rủi ro:

| ID | Rủi ro kiến trúc | Bằng chứng | Điều kiện đóng |
| --- | --- | --- | --- |
| R-ARCH-01 | Caller truy cập `orders.internal` | `ApplicationModules.verify()` + vị trí import gây lỗi | Caller chỉ còn dùng API hợp lệ và test kiến trúc pass khi baseline toàn cục được xử lý |

`@ApplicationModule(allowedDependencies = ...)` có thể siết module được phép phụ thuộc, nhưng **không xóa vòng phụ thuộc hiện hữu**. Một test business xanh không thay thế kiểm chứng ranh giới.

## 10. Theo dõi coverage theo trọng số rủi ro và đặt quality gate

Báo cáo nên có **hai lớp kết quả**: tình trạng của từng gap và tổng quan giúp ưu tiên. Tỷ lệ line coverage đứng riêng vì nó đo một thứ khác.

Với rubric ở mục 2, có thể tính:

\[
\text{Risk-weighted verified coverage}
= \frac{\sum R_i \text{ của kịch bản Verified}}
{\sum R_i \text{ của mọi kịch bản trong phạm vi}} \times 100\%.
\]

Từ bảng ví dụ mục 3: tổng trọng số là `20 + 15 + 16 + 12 + 12 = 75`; bốn rủi ro được minh họa là Verified có tổng `20 + 16 + 12 + 12 = 60`. Khi đó coverage theo trọng số là **60/75 = 80%**.

**80% không có nghĩa là đạt.** R-02 có điểm 15 và chưa có integration test; một quality gate có thể quy định “không còn Gap hoặc Regressed với R ≥ 15 ở các luồng vừa thay đổi”. Ngưỡng đó cũng là chính sách minh họa của nhóm, không phải quy tắc sẵn có của Spring Modulith.

Để sổ gap phục vụ quyết định, mỗi dòng cần cập nhật tối thiểu:

- `riskId`, `module`, `scenario`, `impact`, `likelihood`, `score`;
- `testId` hoặc đường dẫn test/JUnit method, **assertion chứng minh điều gì**;
- `state`: Gap / Partial / Verified / Regressed;
- `evidence`: link CI job, commit, kết quả chạy, môi trường test và ngày xác nhận;
- `owner`, `nextAction`, `dueDate` cho trạng thái chưa Verified.

Khi test bị vô hiệu hóa, flaky liên tục, chỉ chạy thủ công hoặc thay đổi khiến assertion không còn đo đúng rủi ro, chuyển trạng thái về Partial/Regressed; **không giữ số phần trăm đẹp trên báo cáo**. Khi thêm tính năng, dữ liệu hay consumer mới, cập nhật risk register trước khi mặc định rằng coverage hiện tại vẫn đủ.

Ví dụ quality gate cho Maven, với tên lớp minh họa trong bài:

```bash
./mvnw -B -Dtest=OrdersRiskTests,OrdersPersistenceRiskTests test
./mvnw -B -Dtest=OrdersShippingIntegrationTests test
./mvnw -B -Dtest=ModuleArchitectureTests test
```

Các lệnh trên là mẫu; cần chạy bằng đúng build tool, dependency, database và broker test của dự án. Trong CI thực tế, kết quả JUnit sẽ kiểm tra **test pass/fail**; điều kiện “mọi R ≥ 15 đã Verified” chỉ có hiệu lực nếu nhóm có thêm bước đọc/đối chiếu risk register. Không thể mặc định Maven tự hiểu mức độ rủi ro từ tên method.

Ưu tiên phản hồi nhanh: module test ở mỗi pull request, integration test theo rủi ro và hạ tầng, architecture verification khi baseline toàn cục đã xanh. Nếu baseline đang đỏ, ghi nhận rõ để sửa và chuyển gate về trạng thái bắt buộc; không che kết quả thực tế bằng việc bỏ bài test.

## 11. Checklist rà soát gap và bài thực hành

Dùng checklist này khi review thay đổi có ảnh hưởng tới application module:

- [ ] Mỗi luồng nghiệp vụ quan trọng được mô tả bằng điều kiện, hành động, kết quả và hậu quả nếu sai.
- [ ] Đã gắn owner và bằng chứng cho điểm Impact/Likelihood; không mặc định “chưa biết” là rủi ro thấp.
- [ ] Đã chọn lớp test đúng hậu quả: API, DB sau commit, event publisher, consumer tích hợp hoặc ranh giới kiến trúc.
- [ ] Các rủi ro điểm cao có test với assertion đủ mạnh và đã **thực sự pass** trong môi trường đại diện.
- [ ] `PublishedEvents` được dùng để xác nhận publisher; listener/consumer sau commit có bằng chứng riêng nếu rủi ro yêu cầu.
- [ ] Test persistence tách ranh giới transaction; không vô tình kiểm tra dữ liệu chưa commit.
- [ ] Đã xét retry, duplicate request, event trùng, rollback và bất thường concurrency nếu chúng có hậu quả đáng kể.
- [ ] `ApplicationModules.verify()` có kết quả/baseline rõ; không có import vượt API hoặc dependency cycle mới bị bỏ qua.
- [ ] Risk register ghi `Gap/Partial/Verified/Regressed`, test ID, CI evidence, owner và việc tiếp theo.
- [ ] Coverage tổng hợp không che rủi ro cao còn mở; các điều kiện quality gate đều thực thi được và phản ánh kết quả thật.

**Bài thực hành 45–60 phút:** trên một ứng dụng Spring Modulith có module `orders`, lập ít nhất năm rủi ro với Impact/Likelihood và bằng chứng; chọn hai rủi ro cao nhất còn Gap. Viết một `@ApplicationModuleTest` để khóa idempotency hoặc validation và một kiểm thử liên quan DB/event đúng mức độ rủi ro. Chạy các test trên code thật, lưu link CI và cập nhật trạng thái từng dòng. Cuối cùng chạy `ApplicationModules.verify()`, ghi lại vi phạm toàn cục còn tồn tại và tính lại coverage theo trọng số.

**Tiêu chí nghiệm thu:** sổ rủi ro chỉ ra **khoảng trống nào cần xử lý trước, ai chịu trách nhiệm, test nào cung cấp bằng chứng và điều kiện nào mới cho phép đóng gap**. Việc báo cáo coverage giúp ngăn lỗi nghiệp vụ và phụ thuộc sai tái xuất hiện, thay vì chỉ tăng một tỷ lệ phần trăm trên dashboard.

