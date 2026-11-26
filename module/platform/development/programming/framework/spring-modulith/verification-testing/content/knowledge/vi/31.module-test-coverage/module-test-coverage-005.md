# Độ bao phủ code và giới hạn đối với module boundary

Trong chương **Coverage theo module** của **SPRING_MODULITH_VERIFICATION_TESTING**, mục tiêu không dừng ở con số phần trăm test đã chạy qua code. Ta cần chứng minh hai thuộc tính độc lập: hành vi quan trọng của từng module được kiểm thử, và cấu trúc phụ thuộc giữa các module tuân thủ kiến trúc Spring Modulith. Bài học kết hợp đo coverage, kiểm chứng bằng **ApplicationModules**, kiểm thử **@ApplicationModuleTest**, sự kiện, cơ sở dữ liệu và quality gate trong CI để hạn chế hồi quy.

## 1. Phân biệt độ bao phủ code với độ đúng của module boundary

**Code coverage** cho biết phần nào của mã được thực thi khi chạy một tập kiểm thử. **Module boundary** là quy tắc về những gì module khác được phép nhìn thấy, gọi đến hoặc phụ thuộc. Hai câu hỏi này có đối tượng đo khác nhau:

| Câu hỏi | Bằng chứng thích hợp | Không thể kết luận chỉ từ bằng chứng đó |
| --- | --- | --- |
| Dòng code và nhánh điều kiện đã được chạy? | JaCoCo line/branch coverage | Assertion có đúng, tình huống nghiệp vụ đủ hay chưa |
| Module orders có phụ thuộc hợp lệ vào inventory? | ApplicationModules.verify() | Đơn hàng được xử lý đúng khi inventory hết hàng |
| Bean trong module có khởi tạo và phối hợp được? | @ApplicationModuleTest | Mọi hệ thống ngoài, DB hay transaction đều hoạt động đúng |
| Event có được phát ra và xử lý sau commit? | Kiểm thử event, transaction và tích hợp | Chỉ số line coverage một mình có thể xác nhận điều này |

Ví dụ: 100% line coverage của một service vẫn có thể đi kèm với import trực tiếp một repository thuộc gói nội bộ của module khác. Ngược lại, ApplicationModules.verify() có thể vượt qua trong khi nhánh xử lý hàng hết tồn kho hoàn toàn chưa được kiểm thử. Vì vậy cần **ít nhất hai quality gate riêng**: gate kiến trúc và gate kiểm thử hành vi/coverage.

## 2. Hiểu đúng các chỉ số coverage trước khi đặt ngưỡng

JaCoCo thường cung cấp **instruction**, **line**, **branch**, **method** và **class coverage**. Khi nói về rủi ro nghiệp vụ, hai chỉ số được theo dõi nhiều nhất là:

- **Line coverage**: tỷ lệ dòng có bytecode đã được thực thi. Một dòng được tính là có coverage không có nghĩa mọi biểu thức trên dòng đó đã được kiểm tra.
- **Branch coverage**: tỷ lệ nhánh bytecode của các cấu trúc quyết định như if và switch đã được đi qua. Nó không đồng nghĩa với mọi tổ hợp điều kiện hoặc mọi trường hợp ngoại lệ.

Ví dụ, với điều kiện:

~~~java
if (unitPrice < 0 || quantity <= 0) {
    throw new IllegalArgumentException("Invalid quote");
}
return Math.multiplyExact(unitPrice, quantity);
~~~

Một test với giá hợp lệ và số lượng dương chỉ đi qua đường thành công. Muốn kiểm tra đầy đủ ý nghĩa điều kiện cần thêm ít nhất trường hợp **giá âm**, **số lượng không hợp lệ**, và nếu nghiệp vụ yêu cầu thì **tràn số** ở phép nhân. Dù các test này cho coverage cao, chúng vẫn chưa chứng minh rằng module khác chỉ gọi qua public API.

**Diễn giải ngưỡng:** 80% hay 90% là mục tiêu quản trị để phát hiện thay đổi đáng ngờ, không phải bảo đảm chất lượng. Đánh giá số dòng/nhánh chưa được kiểm tra cùng mức độ rủi ro, đặc biệt ở xử lý thanh toán, transaction, phát event và kiểm soát truy cập.

## 3. Xác định module cần đo trước khi đọc báo cáo

Giả sử ứng dụng Spring Boot có lớp khởi động tại **com.example.shop.ShopApplication** và hai module trực tiếp dưới package gốc:

~~~text
com.example.shop
├── ShopApplication
├── orders
│   ├── OrderQuoteService
│   └── internal
│       └── ...
└── inventory
    ├── StockAvailability
    └── internal
        └── ...
~~~

Theo cách phát hiện module mặc định của Spring Modulith, **orders** và **inventory** là các application module. Các kiểu nằm trong package gốc của module thường tạo thành API mặc định; các package con như **inventory.internal** là chi tiết nội bộ, trừ khi được công bố có chủ đích bằng named interface.

Khi theo dõi coverage theo module:

1. Liệt kê module theo mô hình Spring Modulith thực tế, thay vì tự suy rằng một package bất kỳ là một module.
2. Ánh xạ class thuộc module vào báo cáo JaCoCo, tính cả package con và code nghiệp vụ cần thiết.
3. Phân biệt **coverage toàn ứng dụng**, **coverage theo package** và **coverage tổng hợp đúng theo module**; đây không phải ba phép đo tự động tương đương.
4. Xem riêng test đơn vị, test module và test tích hợp; nếu nhiều task hoặc source set tạo file thực thi JaCoCo khác nhau, báo cáo phải được cấu hình để thu thập đúng tập test.

Nếu dự án dùng module được khai báo tường minh, nested module hoặc named interface, tên package trong báo cáo JaCoCo có thể không đủ để suy ra ranh giới kiến trúc. Hãy dùng định nghĩa module thực tế làm nguồn đối chiếu.

## 4. Phản ví dụ: coverage cao nhưng phụ thuộc sai ranh giới

Giả sử module **inventory** có một kiểu public là **StockJpaRepository** ở package **com.example.shop.inventory.internal**. Kiểu public này vẫn là **internal đối với Spring Modulith** vì vị trí package của nó.

~~~java
// com/example/shop/orders/CheckoutService.java
package com.example.shop.orders;

import com.example.shop.inventory.internal.StockJpaRepository;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final StockJpaRepository repository;

    public CheckoutService(StockJpaRepository repository) {
        this.repository = repository;
    }
}
~~~

Java có thể biên dịch đoạn phụ thuộc trên nếu interface/class repository được khai báo public. Test của CheckoutService thậm chí có thể chạy qua mọi dòng bằng mock. Nhưng **orders** đã biết chi tiết persistence của **inventory**, khiến refactor inventory làm hỏng orders và vi phạm quy tắc chỉ sử dụng API được công bố.

Hướng sửa là định nghĩa hợp đồng ở package API của inventory rồi để inventory tự triển khai hợp đồng:

~~~java
// com/example/shop/inventory/StockAvailability.java
package com.example.shop.inventory;

public interface StockAvailability {
    boolean available(String sku);
}
~~~

~~~java
// com/example/shop/orders/CheckoutService.java
package com.example.shop.orders;

import com.example.shop.inventory.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final StockAvailability stockAvailability;

    public CheckoutService(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    public boolean canCheckout(String sku) {
        return stockAvailability.available(sku);
    }
}
~~~

Ví dụ này giả định inventory cung cấp một Spring bean triển khai StockAvailability. Sau khi sửa, test hành vi của orders vẫn cần xác nhận kết quả true/false, còn test kiến trúc phải xác nhận không còn tham chiếu đến **inventory.internal**. Không thể thay một loại kiểm tra bằng loại kia.

## 5. Kiểm chứng ranh giới bằng ApplicationModules trong JUnit

Đặt một test kiến trúc ở package gốc của ứng dụng để CI phát hiện import nội bộ, phụ thuộc vòng và những quy tắc module được cấu hình:

~~~java
// src/test/java/com/example/shop/ModuleArchitectureTests.java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void respectsDeclaredModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**ApplicationModules.of(...)** tạo mô hình module từ ứng dụng; **verify()** kiểm tra các quy tắc kiến trúc Spring Modulith, trong đó có việc truy cập API module hợp lệ và phụ thuộc vòng. Đây là một test JUnit bình thường: khi thất bại, tác vụ chạy test phải thất bại và chặn quality gate.

Nếu orders chỉ được phép phụ thuộc inventory, có thể khai báo trong file **com/example/shop/orders/package-info.java**:

~~~java
@ApplicationModule(allowedDependencies = "inventory")
package com.example.shop.orders;

import org.springframework.modulith.ApplicationModule;
~~~

**allowedDependencies** giới hạn module đích được phép phụ thuộc; nó **không** biến toàn bộ package con của inventory thành API public. Nếu thực sự cần công bố API nằm ở package con, hãy định nghĩa **@NamedInterface** tại package đó và tham chiếu tên interface trong quy tắc phụ thuộc. Không mở rộng API chỉ để test kiến trúc vượt qua.

## 6. Đo hành vi một module với @ApplicationModuleTest

**@ApplicationModuleTest** khởi tạo một test context có phạm vi module chứa test, phù hợp để kiểm chứng bean và hành vi Spring thực tế mà không cần mặc định mở toàn bộ ứng dụng. Để quan sát coverage có ý nghĩa, service phải có nhánh nghiệp vụ và test phải có assertion.

~~~java
// src/main/java/com/example/shop/orders/OrderQuoteService.java
package com.example.shop.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderQuoteService {

    public int quote(int unitPrice, int quantity) {
        if (unitPrice < 0 || quantity <= 0) {
            throw new IllegalArgumentException("Invalid quote");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

~~~java
// src/test/java/com/example/shop/orders/OrderQuoteModuleTests.java
package com.example.shop.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderQuoteModuleTests {

    @Autowired
    OrderQuoteService quotes;

    @Test
    void calculatesQuote() {
        assertEquals(600, quotes.quote(200, 3));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class, () -> quotes.quote(-1, 3));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(IllegalArgumentException.class, () -> quotes.quote(200, 0));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> quotes.quote(Integer.MAX_VALUE, 2));
    }
}
~~~

Test đặt trong **com.example.shop.orders** để Spring Modulith nhận diện đúng module. Ở chế độ mặc định **STANDALONE**, module được khởi tạo chủ yếu bằng các bean của chính nó. Khi cần chạy cả các module phụ thuộc trực tiếp, dùng **@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)**; khi cần tất cả phụ thuộc bắc cầu, cân nhắc **ALL_DEPENDENCIES**. Chỉ mở rộng phạm vi khi kịch bản thật sự yêu cầu, vì test quá rộng dễ che giấu coupling.

Test trên là ví dụ kiểm tra logic và wiring của module; muốn có tỷ lệ coverage, vẫn phải chạy công cụ đo như JaCoCo. Annotation **@ApplicationModuleTest** tự nó không tính coverage và không thay cho **ApplicationModules.verify()**.

## 7. Chọn kịch bản test theo rủi ro tại ranh giới

Một module thường có nhiều đường đi cần kiểm chứng hơn số dòng code gợi ý. Dùng ma trận này khi bổ sung test:

| Điểm tương tác | Test tối thiểu | Lỗ hổng nếu chỉ nhìn coverage |
| --- | --- | --- |
| API orders gọi inventory | Có hàng, hết hàng, lỗi từ inventory | Có chạy qua lời gọi nhưng không kiểm tra contract, timeout hoặc lỗi |
| Validation ở đầu vào | Giá trị hợp lệ, dữ liệu thiếu hoặc không hợp lệ | Dòng if được chạy nhưng một nhánh quan trọng chưa có assertion |
| Thay đổi trạng thái | Trạng thái trước/sau và quy tắc bất biến | Test có thể chỉ gọi method rồi kết thúc |
| Event liên module | Loại event, payload, consumer nhận, xử lý lặp | Test chỉ thấy lời gọi publishEvent |
| Persistence | Lưu và đọc lại, unique constraint, rollback | Dùng mock repository nên không kiểm tra DB thực |
| Transaction và tích hợp | Commit, rollback, retry, thất bại của phụ thuộc | Line coverage thường không phản ánh thời điểm side effect |

Ưu tiên kiểm thử **hợp đồng công khai** giữa module, bao gồm trường hợp thất bại. Với mô-đun có hành vi phức tạp, phủ 100% các dòng đơn giản nhưng bỏ qua sự cố sau commit là chiến lược thiếu an toàn.

## 8. Coverage sự kiện: publish chưa có nghĩa consumer xử lý đúng

Ở phía producer, có thể ghi nhận event bằng hạ tầng test của Spring Framework. Ví dụ dưới đây dùng Java record và Spring event publisher:

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {
}
~~~

~~~java
// com/example/shop/orders/OrderCreationService.java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderCreationService {

    private final ApplicationEventPublisher events;

    public OrderCreationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void create(UUID orderId) {
        events.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

~~~java
// src/test/java/com/example/shop/orders/OrderEventsTests.java
package com.example.shop.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

@ApplicationModuleTest
@RecordApplicationEvents
class OrderEventsTests {

    @Autowired
    OrderCreationService orders;

    @Autowired
    ApplicationEvents events;

    @Test
    void publishesOrderPlacedWithCorrectId() {
        UUID id = UUID.randomUUID();

        orders.create(id);

        assertEquals(1L, events.stream(OrderPlaced.class)
                .filter(event -> event.orderId().equals(id))
                .count());
    }
}
~~~

Test này chứng minh producer công bố đúng event trong ngữ cảnh kiểm thử. Nó **chưa** chứng minh một listener ở module khác đã thực thi thành công, transaction đã commit, hoặc event publication được xử lý bền vững. Với luồng bất đồng bộ, có thể dùng **Scenario** của Spring Modulith để kích hoạt hành vi, chờ event/điều kiện kết thúc và xác nhận kết quả; với luồng **@TransactionalEventListener(phase = AFTER_COMMIT)** cần test có commit thực sự, không dựa trên test transaction bị rollback tự động.

Đặc biệt ở giao tiếp bất đồng bộ, bổ sung test idempotency, retry, xử lý event trùng và phục hồi sau lỗi nếu đó là cam kết của hệ thống. Số dòng listener được chạy không xác định được các tính chất ấy.

## 9. Coverage với repository, database và transaction

Test unit có mock repository hữu ích để kiểm tra phân nhánh dịch vụ, nhưng không kiểm tra được query, ánh xạ JPA, constraint hay thứ tự commit. Với module có persistence:

1. Dùng **@ApplicationModuleTest** cho luồng nghiệp vụ cần bean Spring và repository thật của module; cấu hình datasource/test profile phù hợp.
2. Dùng **Testcontainers** hoặc môi trường DB kiểm thử tương đương khi hành vi phụ thuộc vào engine thật, migration, transaction isolation hay constraint đặc thù.
3. Sau thao tác ghi, xác minh trạng thái đọc lại từ persistence context mới hoặc sau khi flush/clear nếu cần; tránh assertion chỉ nhìn object Java đang còn trong bộ nhớ.
4. Kiểm tra rollback khi nghiệp vụ lỗi và side effect/event sau commit bằng một test có transaction boundary rõ ràng.

Ví dụ tình huống đáng kiểm tra: khi tạo đơn nhưng ghi thanh toán thất bại, transaction có giữ lại đơn ở trạng thái không hợp lệ không? Khi nhập hai đơn cùng mã idempotency, unique constraint thực tế có chặn trùng không? Khi inventory trả lỗi, orders có chuyển trạng thái và phát event đúng hay không? Các câu hỏi này không thể được kết luận chỉ từ tỷ lệ line coverage.

Hãy phân biệt **test module với DB giả lập**, **test module với DB thật**, và **test tích hợp nhiều module** trong báo cáo. Mỗi nhóm trả lời một loại rủi ro khác nhau và có thể cần cấu hình source set/JaCoCo khác nhau để đưa vào báo cáo tổng.

## 10. Báo cáo JaCoCo và quality gate trong CI

Với dự án dùng **Gradle Groovy DSL** và JUnit Jupiter, có thể cấu hình JaCoCo tương tự ví dụ sau (giả sử plugin Java/Spring và các dependency test đã được thiết lập):

~~~groovy
plugins {
    id 'jacoco'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.test
    reports {
        html.required = true
        xml.required = true
    }
}

tasks.named('jacocoTestCoverageVerification') {
    dependsOn tasks.test
    violationRules {
        rule {
            element = 'PACKAGE'
            includes = [
                'com.example.shop.orders',
                'com.example.shop.orders.*'
            ]
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

**Lưu ý về cách đo:** ví dụ trên đặt ngưỡng cho các package khớp mẫu; nó không tự tạo một chỉ số coverage gộp chính xác cho toàn bộ application module orders. Nếu muốn gate tổng hợp theo module, phải xác định rõ tập class thuộc module, hợp nhất execution data của các test task liên quan và tính ngưỡng trên tập đó. Đừng báo cáo coverage của riêng package gốc rồi gọi đó là coverage của mọi package con.

Trong CI của một dự án dùng Gradle, một bước có thể chạy:

~~~yaml
- name: Verify tests, module boundaries and coverage
  run: ./gradlew check jacocoTestReport
~~~

Gate sẽ bảo vệ module boundary **chỉ khi** test **ModuleArchitectureTests** thực sự được task **test** phát hiện và chạy. Gate coverage sẽ bảo vệ tỷ lệ đặt trước **chỉ khi** JaCoCo nhận đúng execution data và task verification được nối vào **check**. Nếu test tích hợp nằm ở task riêng, thêm task đó vào pipeline và kết hợp dữ liệu đo phù hợp. Kiểm tra cả XML/HTML report và kết quả test thay vì chỉ tin nhãn bước CI.

## 11. Checklist nghiệm thu và bài tập tự kiểm

Dùng checklist sau để rà soát một thay đổi có tác động đến nhiều application module:

- [ ] Mô hình module được nhận diện đúng theo Spring Modulith; package API/internal được ghi nhận rõ.
- [ ] Có JUnit test gọi **ApplicationModules.of(...).verify()** và test đó chạy trong CI.
- [ ] Không có import trực tiếp vào package internal của module khác; các phụ thuộc được phép đã khai báo đúng.
- [ ] Test **@ApplicationModuleTest** nằm trong package của module và chọn bootstrap mode phù hợp.
- [ ] Các nhánh thành công, dữ liệu không hợp lệ và lỗi từ dependency có assertion cụ thể.
- [ ] Event được kiểm tra ít nhất ở payload; nếu có consumer/after-commit, có test tích hợp xác minh kết quả thực.
- [ ] Hành vi persistence/transaction quan trọng được kiểm chứng với DB thích hợp.
- [ ] Báo cáo JaCoCo thu thập đúng test task, phân biệt package coverage và module coverage.
- [ ] Ngưỡng trong CI thất bại khi cố tình thêm vi phạm boundary hoặc làm giảm coverage dưới ngưỡng.
- [ ] Nhóm xem lại các nhánh chưa bao phủ dựa trên rủi ro, không chỉ tối ưu phần trăm.

**Bài tập ngắn:** Bắt đầu từ ví dụ orders/inventory. (1) Tạo interface công khai StockAvailability ở inventory và implementation trong inventory.internal. (2) Viết test đơn vị hoặc module cho hai trường hợp còn hàng/hết hàng. (3) Tạm thay constructor của CheckoutService bằng dependency đến một kiểu public trong inventory.internal; quan sát rằng test hành vi vẫn có thể pass nhưng **ModuleArchitectureTests** phải fail. (4) Sửa lại dependency qua StockAvailability, chạy lại test, xem báo cáo JaCoCo cho orders và giải thích những hành vi nào vẫn chưa được bảo đảm.

**Tiêu chí hoàn thành:** giải thích được vì sao coverage cao không bảo vệ module boundary; chỉ ra bằng chứng của từng quality gate; viết được một test **ApplicationModules.verify()**, một test **@ApplicationModuleTest** có assertion, và nêu rõ trường hợp cần test event/DB/tích hợp bổ sung.
