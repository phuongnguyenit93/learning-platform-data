# Đo lợi ích của verification sau refactor

Trong chương **Refactoring an existing app** của **SPRING_MODULITH_VERIFICATION_TESTING**, câu hỏi cần trả lời sau khi tách một ứng dụng cũ thành các application module là: **việc verification tạo ra bằng chứng cải thiện nào, và cái giá để có bằng chứng ấy là bao nhiêu?** “Build xanh” chỉ là một quan sát tại một thời điểm. Muốn kết luận refactor có hiệu quả, cần so sánh cấu trúc phụ thuộc, khả năng phát hiện hồi quy, mức bảo toàn hành vi, thời gian phản hồi CI và rủi ro lọt lỗi trên cùng một chuẩn đo.

Bài thực hành dùng Spring Modulith để kiểm chứng ranh giới với `ApplicationModules.verify()`, dùng `@ApplicationModuleTest` để bảo vệ hợp đồng module, kiểm thử event/database/tích hợp theo rủi ro và đặt quality gate CI. Trọng tâm là **thiết kế phép đo trước/sau đáng tin cậy**; đây không phải bài giới thiệu lại các annotation hay cách viết test cơ bản.

## 1. Chuyển mục tiêu refactor thành giả thuyết kiểm chứng được

Giả sử ứng dụng bán hàng cũ có module `orders` gọi trực tiếp repository nội bộ của `inventory`, phụ thuộc vòng giữa các package và test tích hợp phải dựng gần như toàn bộ ứng dụng. Nhóm thay thế quan hệ này bằng API công khai của `inventory` và event giữa các module.

Trước khi sửa code, ghi rõ giả thuyết và dấu hiệu xác nhận:

| Giả thuyết | Bằng chứng trước/sau | Tiêu chí đánh giá |
| --- | --- | --- |
| H1: Giảm phụ thuộc sai ranh giới | Số vị trí tham chiếu API nội bộ, số chu kỳ dependency, kết quả `verify()` | Không còn vi phạm theo cùng bộ quy tắc |
| H2: Giữ nguyên hành vi có chủ đích | Cùng tập input, output, event, dữ liệu cuối và exception của các kịch bản chuẩn | Không có chênh lệch ngoài những thay đổi nghiệp vụ được duyệt |
| H3: Dễ phát hiện lỗi mới | Tỷ lệ lỗi cố ý cấy vào được test/gate chặn | Gate kiến trúc và regression test phát hiện đúng loại lỗi được giao |
| H4: Phản hồi kỹ thuật hữu ích hơn | Thời gian đến lỗi có thể hành động, độ ổn định test, chi phí vận hành | Phát hiện sớm hơn ở mức chi phí CI chấp nhận được |
| H5: Thay đổi ít lan rộng hơn | Số module và file phải sửa cho một yêu cầu tương đương | Xu hướng giảm trên các thay đổi cùng độ khó |

Một sự kiện `ApplicationModules.verify()` chuyển từ **fail** sang **pass** là bằng chứng trực tiếp cho H1, nhưng chưa chứng minh H2–H5. Tương tự, tăng line coverage chỉ chứng minh nhiều mã được thực thi hơn; không chứng minh module boundary tốt hơn.

**Định nghĩa “lợi ích”** nên gắn với mục tiêu của refactor: giảm coupling nguy hiểm, tăng khả năng thay đổi độc lập và giảm xác suất hồi quy thoát ra production. Không phải mọi chỉ số đều cần tốt lên ngay: CI có thể chạy lâu hơn khi bổ sung test DB thật, đổi lại phát hiện lỗi sớm hơn.

## 2. Chốt baseline trước khi chạm vào mã cũ

So sánh trước/sau chỉ có nghĩa khi **mẫu đo và định nghĩa không đổi**. Lưu lại hai mốc revision bất biến, ví dụ:

~~~text
baseline_revision: <commit-before-refactor>
candidate_revision: <commit-after-refactor>
java_runtime: same-major-version
spring_modulith_version: same-version-for-comparison
ci_runner: same-machine-class
test_scenarios: same-acceptance-suite-v1
architecture_rules: same-ruleset-v1
database_seed: same-fixture-and-migration-state
~~~

Các giá trị trong bảng là **mẫu metadata**, phải thay bằng số liệu thực của repository. Để so sánh công bằng:

1. Giữ cùng JDK, phiên bản Spring Modulith/ArchUnit, Gradle và cấu hình CI nếu mục tiêu là so **hai trạng thái của code**. Nếu cần nâng dependency trong refactor, phải ghi nhận đó là biến gây nhiễu và chạy thêm phép đo tách biệt khi có thể.
2. Đóng băng tập scenario chấp nhận: mã scenario, input, kết quả, dữ liệu sau commit và event mong đợi. Chỉ bổ sung scenario khi yêu cầu nghiệp vụ thật thay đổi, đồng thời phân biệt **scenario cũ** với **scenario mới** trong báo cáo.
3. Chốt cách tính “vi phạm”: số cạnh phụ thuộc cấm, số lớp tham chiếu tới internal package, số vòng phụ thuộc, hay số rule đang fail; đây là những đơn vị khác nhau.
4. Thực thi các gate mới trên bản **before** bằng cùng cấu hình kiểm chứng để có baseline đáng so sánh; test kiến trúc có thể fail là kết quả có ý nghĩa, không phải lý do bỏ ghi nhận.
5. Đo thời gian CI nhiều lần, lưu phân phối thay vì lấy một lần nhanh nhất; tách thời gian tải dependency, build, test, khởi động database và tải artifact.

**Bẫy phổ biến:** trước refactor không có architecture test, sau refactor thêm một test và kết luận “số lỗi từ 0 xuống 0”. “Chưa đo” phải ghi là **không có dữ liệu**, không được mã hóa thành zero.

## 3. Đo mức giảm phụ thuộc sai bằng ApplicationModules

Đặt một test kiến trúc trong package gốc của ứng dụng. Ví dụ `ShopApplication` nằm ở `com.example.shop`, còn `orders` và `inventory` là các package module trực tiếp dưới package ấy:

~~~java
// src/test/java/com/example/shop/ModuleArchitectureTests.java
package com.example.shop;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    @Tag("architecture")
    void respectsApplicationModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm chứng những quy tắc cấu trúc của Spring Modulith, trong đó có việc truy cập API module hợp lệ và vòng phụ thuộc, cùng các ràng buộc đã khai báo trong mô hình module. Nếu code sau refactor vẫn truy cập trực tiếp package nội bộ, test phải fail và quality gate phải chặn.

Ví dụ về một phụ thuộc cũ có thể biên dịch Java nhưng vi phạm ranh giới:

~~~java
// BEFORE: com.example.shop.orders.CheckoutService
package com.example.shop.orders;

import com.example.shop.inventory.internal.StockJpaRepository;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final StockJpaRepository stocks;

    public CheckoutService(StockJpaRepository stocks) {
        this.stocks = stocks;
    }
}
~~~

Ví dụ **giả định `StockJpaRepository` là kiểu public** trong package `inventory.internal` để Java cho phép import; các thành phần repository cụ thể không phải nội dung cần triển khai ở đây. Sau refactor, orders chỉ phụ thuộc một hợp đồng công khai:

~~~java
// com/example/shop/inventory/StockAvailability.java
package com.example.shop.inventory;

@FunctionalInterface
public interface StockAvailability {
    boolean available(String sku, int quantity);
}
~~~

~~~java
// AFTER: com/example/shop/orders/CheckoutService.java
package com.example.shop.orders;

import com.example.shop.inventory.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final StockAvailability stocks;

    public CheckoutService(StockAvailability stocks) {
        this.stocks = stocks;
    }

    public boolean canCheckout(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return stocks.available(sku, quantity);
    }
}
~~~

Một implementation bean của `StockAvailability` sẽ nằm trong `inventory` hoặc `inventory.internal`, còn orders không biết loại persistence được dùng. Nếu quy định orders **chỉ** được phụ thuộc inventory, có thể bổ sung ở `com/example/shop/orders/package-info.java`:

~~~java
@ApplicationModule(allowedDependencies = "inventory")
package com.example.shop.orders;

import org.springframework.modulith.ApplicationModule;
~~~

**Cách báo cáo đúng:** `verify()` là kiểm chứng **pass/fail**, không phải API đếm sẵn “7 lỗi kiến trúc”. Để có số vi phạm, phải dùng cùng một phương pháp thống kê có định nghĩa rõ (ví dụ xuất danh sách cặp source→target từ phép phân tích dependency hoặc đếm rule violations từ báo cáo công cụ chuyên dụng), khử trùng lặp đúng quy ước. Không suy ra số lượng từ một exception hay số dòng của log.

## 4. Chứng minh gate thật sự bắt được vi phạm bằng negative control

Một gate luôn xanh có thể do cấu hình bỏ qua test, chọn sai root package, vô tình đặt loại phụ thuộc cấm ngoài tập module hoặc không chạy đúng task. Đo **khả năng phát hiện** bằng các lỗi kiểm soát được trên branch thử nghiệm:

| Lỗi cố ý cấy | Kỳ vọng | Bằng chứng |
| --- | --- | --- |
| orders giữ một field kiểu public của `inventory.internal` | `ModuleArchitectureTests` fail | JUnit failure nêu phụ thuộc không hợp lệ |
| Tạo dependency vòng orders ↔ inventory qua các loại public | Kiểm chứng kiến trúc fail | Báo cáo/stack trace về vòng phụ thuộc |
| Gọi API của module ngoài `allowedDependencies` | Verification fail | Rule dependency hạn chế bị kích hoạt |
| Đổi payload event công khai hoặc bỏ event | Contract/event test fail | Assertion sai payload hoặc thiếu event |
| Bỏ rollback hoặc giải phóng reservation | DB/integration test fail | Trạng thái lưu hoặc side effect sai |

Với lỗi số một, **phải tạo một tham chiếu thật trong bytecode**, chẳng hạn field hoặc lời gọi đến kiểu nội bộ. Một dòng `import` không sử dụng có thể bị compiler loại bỏ và không còn làm bằng chứng phụ thuộc. Tạo lỗi trong branch tạm, chạy gate, lưu kết quả rồi **loại bỏ lỗi trước khi tích hợp code**.

Định nghĩa tỷ lệ phát hiện của negative control:

~~~text
detected_seeded_faults / total_seeded_faults
~~~

Nếu cấy 5 lỗi độc lập và gate phát hiện 4, tỷ lệ là `4/5 = 80%` cho **bộ lỗi đã cấy**, không phải xác suất hệ thống bắt được 80% lỗi tương lai. Đánh giá riêng **false positive**: một thay đổi hợp lệ bị chặn vì rule cấu hình quá chặt cũng làm giảm hiệu quả verification.

## 5. Đo bảo toàn hành vi bằng golden scenarios và @ApplicationModuleTest

Refactor kiến trúc tốt phải giữ những hợp đồng nghiệp vụ được yêu cầu giữ nguyên. Trước khi thay đổi dependency, tạo **golden scenarios** từ luồng cũ: đầu vào, kết quả trả về, exception, event, dữ liệu sau commit, trạng thái của module liên quan. Ví dụ:

| Mã scenario | Hành vi phải giữ | Điểm so sánh before/after |
| --- | --- | --- |
| `O-01` | Hàng đủ, đơn hợp lệ | Kết quả tạo đơn; một reservation hợp lệ |
| `O-02` | Hàng thiếu | Trả lỗi/loại từ chối đúng contract; không tạo đơn xác nhận |
| `O-03` | Hủy sau khi giữ hàng | Trạng thái hủy; trả hàng một lần |
| `O-04` | Giao dịch thất bại giữa chừng | Rollback/compensation đúng, không phát event thành công sai |
| `O-05` | Sự kiện lặp | Kết quả idempotent theo hợp đồng đã thống nhất |

Sau khi dựng module boundary, có thể kiểm tra contract tại cấp **module** bằng test trong package của module đó. Ví dụ tối giản về event publication mà module orders hứa cung cấp:

~~~java
// src/main/java/com/example/shop/orders/OrderConfirmed.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderConfirmed(UUID orderId) {
}
~~~

~~~java
// src/main/java/com/example/shop/orders/OrderConfirmation.java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmation {

    private final ApplicationEventPublisher events;

    public OrderConfirmation(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void confirm(UUID orderId, boolean stockReserved) {
        if (!stockReserved) {
            throw new IllegalStateException("Stock not reserved");
        }
        events.publishEvent(new OrderConfirmed(orderId));
    }
}
~~~

~~~java
// src/test/java/com/example/shop/orders/OrderConfirmationModuleTests.java
package com.example.shop.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

@ApplicationModuleTest
@RecordApplicationEvents
class OrderConfirmationModuleTests {

    @Autowired
    OrderConfirmation confirmation;

    @Autowired
    ApplicationEvents recordedEvents;

    @Test
    void confirmsByPublishingExactlyOneEvent() {
        UUID orderId = UUID.randomUUID();

        confirmation.confirm(orderId, true);

        assertEquals(1L, recordedEvents.stream(OrderConfirmed.class)
                .filter(event -> event.orderId().equals(orderId))
                .count());
    }

    @Test
    void refusesConfirmationWithoutReservation() {
        UUID orderId = UUID.randomUUID();

        assertThrows(IllegalStateException.class,
                () -> confirmation.confirm(orderId, false));
        assertEquals(0L, recordedEvents.stream(OrderConfirmed.class)
                .filter(event -> event.orderId().equals(orderId))
                .count());
    }
}
~~~

Đây là bằng chứng **publication trong test context**, không chứng minh listener xử lý sau commit, trạng thái DB hay bảo đảm exactly-once qua hạ tầng gửi nhận. Để đo scenario `O-03`–`O-05`, cần test tích hợp với DB/transaction thật, consumer phù hợp và thời điểm commit có thể quan sát. Với `@TransactionalEventListener(phase = AFTER_COMMIT)`, test tự rollback không tạo ra bằng chứng cho listener sau commit.

**Phân tích kết quả:** đánh dấu từng scenario `PASS_BEFORE`, `PASS_AFTER` và `PARITY`. Nếu yêu cầu được thay đổi có chủ đích, đánh dấu `APPROVED_CHANGE` và so với hợp đồng mới, không tính đó là hồi quy. Coverage dòng code không thay thế danh sách scenario chấp nhận.

## 6. Đo hiệu quả bảo vệ ranh giới qua thay đổi có thật

Sau refactor, quan sát các pull request có phạm vi tương đương để đánh giá độ lan tỏa của thay đổi:

- **Modules touched per change:** số application module có code production bị sửa cho một feature/bug fix; nên tách changeset thuần format/rename.
- **Cross-module files touched:** số file trong module ngoài module sở hữu tính năng bị thay đổi vì dependency chi tiết.
- **Public contract changes:** số thay đổi API công khai gây điều chỉnh caller; phân biệt thay đổi có versioning/compatibility với phá hợp đồng.
- **Boundary-violation recurrence:** số PR bị gate bắt tham chiếu internal hoặc dependency vòng, đo cùng với số PR có liên quan.
- **Review/rework effort:** số vòng sửa sau khi gate báo lỗi, thời gian từ push đầu đến khi tác giả nhận được thông báo cụ thể.

Ví dụ “thêm cách lưu trữ tồn kho” trước refactor cần sửa `inventory` và hai service trong `orders`, sau refactor chỉ cần sửa implementation bên trong `inventory`. Đó là bằng chứng **giảm phạm vi thay đổi** cho đúng loại yêu cầu này. Nhưng so sánh một PR sửa typo với một PR thay đổi transaction là không công bằng: nên phân nhóm theo độ khó, độ lớn diff và loại chức năng.

Đừng tối ưu chỉ số “số module bị sửa” bằng mọi giá. Một yêu cầu thay đổi hợp đồng giữa hai bounded context có thể hợp lệ khi phải chỉnh cả hai module; chất lượng nằm ở chỗ mối quan hệ được công bố và được kiểm thử, không phải số tuyệt đối nhỏ nhất.

## 7. Đo thời gian phản hồi và chi phí của verification trong CI

Bổ sung module test, architecture check, database và event integration test có thể làm tăng thời gian chạy pipeline. Phải đo **thời gian đến phản hồi hữu ích**, không chỉ tổng thời lượng:

| Chỉ số | Cách đo | Ý nghĩa |
| --- | --- | --- |
| Architecture gate duration | Thời gian task chứa `ModuleArchitectureTests` | Chi phí phát hiện phụ thuộc sai |
| First actionable feedback | Từ push đến lỗi đủ thông tin để tác giả sửa | Khả năng phản hồi sớm |
| Test p50/p95 | Trung vị/phân vị 95 trên nhiều CI run cùng lớp môi trường | Độ ổn định thời gian thực thi |
| Flake rate | Tỷ lệ rerun làm đổi kết quả khi code và môi trường không đổi | Chi phí nhiễu cảnh báo |
| Failure diagnosis time | Từ phát hiện fail đến xác định nguyên nhân | Giá trị của thông báo lỗi và báo cáo |
| CI cost per change | Compute time hoặc chi phí runner theo mỗi PR | Giá phải trả để bảo vệ thay đổi |

Có thể sắp xếp **test kiến trúc nhanh** và unit/module tests chạy sớm, còn DB/test tích hợp chạy ở stage tiếp theo. So sánh median/p95 trước sau khi thay đổi pipeline, đồng thời ghi rõ staging và cache để không nhầm cải thiện do cache với lợi ích kiến trúc.

**Ví dụ minh họa** (số giả định, không phải kết quả từ dự án):

| Đơn vị đo | Trước | Sau | Cách diễn giải |
| --- | ---: | ---: | --- |
| Illegal inter-module references | 7 | 0 | Chấm cùng rule và snapshot; đã loại bỏ vi phạm đã biết |
| Dependency cycles | 2 | 0 | Chấm cùng mô hình module |
| Golden scenarios đạt yêu cầu | 18/20 | 20/20 | Hai scenario được sửa hoặc bổ sung bảo vệ |
| Thời gian đến lỗi có thể xử lý (p50) | 35 phút | 12 phút | Pipeline phản hồi sớm hơn |
| Tổng thời gian pipeline (p50) | 9 phút | 14 phút | Đổi lại tốn thời gian chạy hơn |
| Lỗi liên module lọt ra production/4 tuần | 3 | 1 | Tín hiệu theo dõi, chưa đủ để kết luận quan hệ nhân quả |

Giảm thời gian đến phản hồi trong khi tổng pipeline chậm hơn **không mâu thuẫn**: gate nhanh có thể chạy ngay lúc tác giả đẩy code và chặn lỗi sớm, trong khi những test tích hợp chạy sau. Đây là cơ sở để lựa chọn cách tổ chức CI theo mức rủi ro.

## 8. Tạo quality gate có bằng chứng, không chỉ có nhãn xanh

Đảm bảo task `test` chứa `ModuleArchitectureTests` và các test module liên quan. Với dự án Gradle dùng plugin Java và JaCoCo, cấu hình mẫu:

~~~groovy
plugins {
    id 'jacoco'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
    reports {
        xml.required = true
        html.required = true
    }
}

tasks.named('jacocoTestCoverageVerification') {
    dependsOn tasks.named('test')
    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}

tasks.named('check') {
    dependsOn tasks.named('jacocoTestCoverageVerification')
}
~~~

Stage CI có thể chạy:

~~~yaml
- name: Verify architecture, module behavior and coverage
  run: ./gradlew clean check jacocoTestReport
~~~

Gate này có hiệu lực **khi test thực sự được phát hiện và chạy**; ví dụ, nếu integration tests nằm ở một task riêng `integrationTest`, phải nối task đó vào CI và xử lý JaCoCo execution data tương ứng. Ngưỡng line coverage `0.80` là ngưỡng minh họa **toàn bundle**, không có nghĩa từng module đạt 80% và không bảo đảm hành vi đúng.

Với mỗi CI run, lưu ít nhất: commit SHA, phiên bản JDK/công cụ, danh sách test đã chạy, kết quả test kiến trúc, JUnit XML, JaCoCo XML/HTML, kết quả scenario và duration của các stage. Cách lưu này cho phép phát hiện trường hợp gate “xanh” vì test quan trọng bị loại khỏi cấu hình.

Định nghĩa tiêu chí chặn merge đủ rõ để người review thực thi được: **không có violation thuộc rule bắt buộc**, **không có golden scenario quan trọng thất bại**, **không có test tích hợp bắt buộc bị bỏ qua**, và **coverage không thấp hơn ngưỡng đã phê duyệt**. Các quyết định miễn trừ phải có owner, lý do và hạn xử lý; không sửa rule để làm build xanh mà không review kiến trúc.

## 9. Chuyển dữ liệu đo thành kết luận có điều kiện

Tính thay đổi cho cùng một đơn vị và mẫu số:

~~~text
absolute_reduction = violations_before - violations_after
relative_reduction = absolute_reduction / violations_before
scenario_pass_rate = passed_required_scenarios / total_required_scenarios
seeded_fault_detection = detected_seeded_faults / total_seeded_faults
~~~

Chỉ tính tỷ lệ giảm tương đối khi `violations_before > 0`. Nếu không có dữ liệu baseline, để trống thay vì đặt zero; nếu `violations_before = 0`, có thể ghi “duy trì 0 lỗi” nhưng không nói “giảm 100%”.

Trong ví dụ mục 7, số tham chiếu liên module sai giảm từ 7 xuống 0, tương ứng giảm tuyệt đối 7 và giảm tương đối 100% **trên tập quy tắc đã đo**. Tuy nhiên, nếu đồng thời đổi cách chia module hoặc nới `allowedDependencies`, con số ấy không còn chứng minh được rằng phụ thuộc thực chất đã giảm. Báo cáo phải có diff của rule/configuration và tên các boundary đã thay đổi.

Các metric mang ý nghĩa khác nhau:

- **Kiến trúc:** chứng minh mô hình ranh giới được thực thi, nhưng không xác nhận nghiệp vụ đúng.
- **Scenario/parity:** chứng minh những hành vi có tiêu chí kiểm tra đã được giữ, nhưng không bao phủ mọi trường hợp tương lai.
- **Tốc độ phản hồi:** chứng minh developer nhận tín hiệu sớm hay muộn, nhưng không trực tiếp đo số lỗi sản phẩm.
- **Escaped defects:** phản ánh kết quả thực tế, nhưng bị ảnh hưởng bởi số người dùng, số release, số thay đổi và quy trình quan sát lỗi.

Khi dùng escaped defects, so theo cùng kỳ thời gian hoặc số lượng release/PR tương đương, đồng thời kèm số lượng thay đổi và mức nghiêm trọng của lỗi. Một tháng không có lỗi được báo cáo chưa đủ để chứng minh refactor đã ngăn mọi hồi quy.

## 10. Nhận diện phản ví dụ và rủi ro làm méo phép đo

| Tình huống | Vì sao số liệu có thể đánh lừa | Cách khắc phục |
| --- | --- | --- |
| Xóa hoặc mở rộng rule để `verify()` pass | Số lỗi giảm do đổi tiêu chuẩn | Versioning ruleset; review riêng diff của rule |
| Chia thêm module nhưng không khai báo đúng vị trí | Một số dependency không còn được tool nhận diện | Kiểm tra mô hình application module và package roots |
| Tăng coverage vì thêm getter/test không có assertion | Code được chạy nhưng không bảo vệ hành vi | Gắn test vào scenario và invariant có thể kiểm tra |
| Golden scenarios “pass” do mock mọi dependency | Không thấy lỗi DB, event sau commit hay tương tác liên module | Có test tích hợp chọn lọc với DB/transaction thật |
| Nhiều test không ổn định | Gate lúc xanh lúc đỏ, developer bỏ qua cảnh báo | Theo dõi flakiness, xử lý nguyên nhân gốc |
| PR sau refactor nhỏ hơn và đơn giản hơn | So sánh tốc độ/độ lan tỏa thiếu công bằng | Phân nhóm PR theo loại công việc và quy mô |
| Tỷ lệ lỗi production giảm trong mùa ít traffic | Tín hiệu không thể quy nguyên nhân cho verification | Chuẩn hóa theo số release, traffic hoặc số thay đổi |

Đặc biệt với Spring Modulith, “không còn import internal” **chưa chắc** đồng nghĩa ranh giới mạnh nếu nhóm chuyển mọi kiểu sang package API một cách thiếu kiểm soát. Hãy review cả độ rộng API công khai, ownership dữ liệu và sự phụ thuộc ngầm qua bảng DB/event. Verification cấu trúc phát hiện những quan hệ **biểu diễn được trong rule**, không tự biết một business contract có bị thay đổi sai hay không.

## 11. Checklist nghiệm thu và bài tập đo lợi ích

Dùng checklist sau tại buổi review sau refactor:

- [ ] Có revision **before/after**, versions công cụ và cùng bộ architecture rules để đối chiếu.
- [ ] Có danh sách module boundary đã xác định và giải thích mỗi ngoại lệ `allowedDependencies`/named interface.
- [ ] Test `ApplicationModules.of(...).verify()` chạy trong CI; có bằng chứng gate bắt được lỗi cấy thử.
- [ ] Số lỗi kiến trúc được đo bằng **định nghĩa đơn vị** nhất quán, tách khỏi kết quả pass/fail.
- [ ] Golden scenarios quan trọng có input, output, event và kết quả DB/transaction tương ứng.
- [ ] Test `@ApplicationModuleTest` bảo vệ contract nội bộ; test tích hợp bảo vệ đường đi liên module, listener và commit khi cần.
- [ ] Kiểm tra không có test quan trọng bị skip/quarantine mà không có quyết định review.
- [ ] Có thống kê time-to-feedback, p50/p95 duration và flake rate từ nhiều lần chạy.
- [ ] Theo dõi chi phí CI và tác động lan rộng của các thay đổi thực tế trong vài vòng release.
- [ ] Không trộn việc thay đổi ruleset, dependency version hoặc acceptance criteria vào một bảng “trước/sau” mà thiếu giải thích.
- [ ] Báo cáo nêu rõ kết luận **đã được chứng minh**, dấu hiệu **chưa đủ dữ liệu** và khoản đầu tư test kế tiếp.

**Bài tập có hướng dẫn:** Với hệ thống ví dụ, giả sử trước refactor có 6 tham chiếu nội bộ sai, 1 dependency cycle, 16/18 golden scenarios đạt; sau refactor là 0 tham chiếu sai, 0 cycle, 18/18 scenario đạt. CI p50 tăng từ 8 lên 12 phút, thời gian đến lỗi kiến trúc hữu ích giảm từ 25 xuống 7 phút. Hãy:

1. Tính mức giảm tuyệt đối/tương đối của vi phạm ranh giới và tỷ lệ scenario trước/sau; ghi rõ rằng các số này **giả định**.
2. Thêm `ModuleArchitectureTests` và một test `@ApplicationModuleTest` cho hợp đồng event như ví dụ; giải thích chúng kiểm tra những gì và **không** kiểm tra những gì.
3. Trên branch thử nghiệm, tạo một field dùng kiểu public trong `inventory.internal`; chứng minh verification fail; khôi phục field rồi xác minh test pass.
4. Ghi lại duration ít nhất vài CI run với cùng runner, so sánh p50/p95 thay vì một thời điểm đơn lẻ; phân tích vì sao tổng CI chậm hơn nhưng phản hồi kiến trúc nhanh hơn.
5. Kết luận có điều kiện: kiến trúc sạch hơn và kịch bản đã chọn được bảo toàn, nhưng vẫn cần bằng chứng DB/event sau commit và theo dõi escaped defects theo thời gian.

**Tiêu chí hoàn thành:** người học thiết kế được baseline so sánh có kiểm soát, sử dụng verification để chứng minh module boundary sau refactor, bảo vệ hành vi bằng module/integration tests, tính toán được chỉ số lợi ích và đánh đổi chi phí CI, đồng thời không suy diễn “build xanh” thành chứng nhận toàn bộ chất lượng ứng dụng.
