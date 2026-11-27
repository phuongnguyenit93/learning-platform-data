# Lọc violation bằng detectViolations()

Khi kiểm tra kiến trúc bằng Spring Modulith, có lúc nhóm cần xem toàn bộ violation, phân loại chúng và tạm thời chấp nhận một ngoại lệ đã được ghi nhận trong kế hoạch migration. Gọi ApplicationModules.verify() sẽ ném exception ngay khi phát hiện vi phạm. Nếu cần xử lý kết quả trước khi quyết định build có thất bại hay không, hãy dùng ApplicationModules.detectViolations().

Phương thức này trả về một đối tượng Violations. Ta có thể xem thông điệp, lọc tập violation bằng predicate rồi gọi throwIfPresent() để ném exception nếu vẫn còn vi phạm cần xử lý. Điểm quan trọng của bài thực hành là hiểu đúng chiều lọc: filter() giữ lại các violation mà predicate trả về true. Vì vậy, muốn loại một ngoại lệ đã được duyệt, predicate phải trả về false cho ngoại lệ đó.

Trong SPRING_MODULITH_MODULE_MODEL, bài lab dùng một hệ thống cửa hàng giả lập có module order, inventory và catalog. Ta sẽ cố ý tạo một dependency tới package internal, đọc kết quả, loại đúng một vi phạm chuyển tiếp có phạm vi hẹp, xác nhận một vi phạm khác vẫn làm test thất bại, rồi gỡ ngoại lệ khi migration hoàn tất.

## 1. Mục tiêu thực hành

Sau bài lab, bạn có thể:

- Tạo ApplicationModules từ lớp ứng dụng.
- Dùng detectViolations() để thu thập các lỗi kiến trúc mà không ném exception ngay.
- Đọc các message bằng getMessages() và kiểm tra tập kết quả bằng hasViolations().
- Hiểu Violation và Violations khác nhau như thế nào.
- Dùng filter(Predicate<Violation>) để giữ lại những lỗi cần tiếp tục xử lý.
- Dùng Violation.hasMessageContaining() để nhận diện một ngoại lệ cụ thể.
- Gọi throwIfPresent() để giữ build thất bại nếu còn vi phạm chưa được chấp nhận.
- Viết test bảo đảm ngoại lệ tạm thời không che một lỗi mới.
- Loại bỏ bộ lọc ngoại lệ sau khi migration kết thúc.

## 2. Bối cảnh bài lab

Ứng dụng ShopApplication có ba application module:

~~~text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryAvailability.java
│   └── internal
│       └── InventoryRepository.java
├── order
│   └── internal
│       └── LegacyStockLookup.java
└── catalog
    ├── ProductCatalog.java
    └── internal
        └── ProductRepository.java
~~~

Module inventory công bố InventoryAvailability tại package gốc. InventoryRepository nằm trong package internal và không phải API mà module khác được phép sử dụng.

Module catalog cũng có API ProductCatalog tại package gốc; ProductRepository nằm trong package internal để phục vụ implementation của catalog.

Trong lúc chuyển đổi hệ thống legacy, lớp LegacyStockLookup vẫn đang truy cập trực tiếp InventoryRepository. Nhóm đã ghi nhận đây là ngoại lệ tạm thời với mã công việc ARCH-142, dự kiến loại bỏ sau khi chuyển xong caller cũ.

~~~java
package com.example.shop.inventory;

public interface InventoryAvailability {

    int availableQuantity(String sku);
}
~~~

~~~java
package com.example.shop.inventory.internal;

public interface InventoryRepository {

    int availableQuantity(String sku);
}
~~~

~~~java
package com.example.shop.catalog;

public interface ProductCatalog {

    boolean exists(String productId);
}
~~~

~~~java
package com.example.shop.catalog.internal;

public interface ProductRepository {

    boolean exists(String productId);
}
~~~

~~~java
package com.example.shop.order.internal;

import com.example.shop.inventory.internal.InventoryRepository;
import org.springframework.stereotype.Component;

@Component
class LegacyStockLookup {

    private final InventoryRepository repository;

    LegacyStockLookup(InventoryRepository repository) {
        this.repository = repository;
    }

    int availableQuantity(String sku) {
        return repository.availableQuantity(sku);
    }
}
~~~

Vì inventory là module đóng và InventoryRepository thuộc package internal, dependency trên vi phạm encapsulation. Đây là violation có thật. Việc tạm lọc nó trong bài lab chỉ minh họa cách quản lý một ngoại lệ đã được duyệt; mục tiêu cuối cùng vẫn là chuyển caller sang InventoryAvailability.

## 3. Chuẩn bị architecture test

Tạo test trong source set test của ứng dụng:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Chạy test và quan sát kết quả. Nếu có dependency tới package internal, verify() sẽ ném exception mô tả các violation được phát hiện.

Hãy đọc toàn bộ message. Đừng chỉ sửa class đầu tiên được nhắc tới vì một lần verification có thể tìm thấy nhiều dependency sai cùng lúc.

## 4. Thu thập violation bằng detectViolations()

Thay verify() bằng detectViolations():

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

class ModularityTests {

    @Test
    void detectsModuleViolations() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        Violations violations = modules.detectViolations();

        violations.getMessages().forEach(System.out::println);
    }
}
~~~

detectViolations() thực thi các verification và trả về Violations thay vì ném exception ngay khi có lỗi. Ta có thể đọc kết quả rồi mới quyết định cách xử lý.

Một số API quan trọng:

| API | Ý nghĩa |
|---|---|
| ApplicationModules.detectViolations() | Chạy verification và trả về tập Violations |
| ApplicationModules.detectViolations(options) | Chạy verification theo VerificationOptions được truyền vào |
| Violations.hasViolations() | Cho biết tập có còn violation hay không |
| Violations.getMessages() | Trả về danh sách message của các violation |
| Violations.filter(predicate) | Trả về tập chỉ gồm các violation khớp predicate |
| Violations.throwIfPresent() | Ném chính đối tượng Violations nếu tập còn vi phạm |
| Violation.getMessage() | Lấy message của một violation |
| Violation.hasMessageContaining(text) | Kiểm tra message có chứa đoạn text hay không |

ApplicationModules.detectViolations() luôn thực thi verification khi được gọi. Điều này khác với verify(), vốn tránh chạy lại nếu verification trên cùng instance đã được thực hiện. Vì vậy, nếu muốn xem kết quả cụ thể sau khi thay đổi VerificationOptions, hãy gọi detectViolations(options) với options cần kiểm tra.

## 5. Kiểm tra trạng thái tập violation

Không phải lần chạy nào cũng có lỗi. Dùng hasViolations() để phân biệt:

~~~java
Violations violations =
        ApplicationModules.of(ShopApplication.class).detectViolations();

if (violations.hasViolations()) {
    System.out.println("Phát hiện lỗi kiến trúc:");
    violations.getMessages().forEach(System.out::println);
} else {
    System.out.println("Không phát hiện violation.");
}
~~~

getMessages() trả về danh sách thông điệp để hiển thị trong log hoặc báo cáo test. Có thể dùng số lượng message để hỗ trợ chẩn đoán:

~~~java
int messageCount = violations.getMessages().size();
System.out.println("Số message: " + messageCount);
~~~

Không nên dựa vào số message để suy ra số dependency sai trong mọi trường hợp. Một violation tổng hợp có thể chứa nhiều chi tiết. Hãy đọc nội dung message và source reference trước khi phân loại.

## 6. Hiểu đúng chiều hoạt động của filter()

Đây là điểm quan trọng nhất của bài lab.

~~~java
Violations filtered = violations.filter(predicate);
~~~

filter() giữ lại các violation mà predicate trả về true. Nó không có nghĩa là “lọc bỏ những gì predicate chọn”.

Ví dụ, nếu muốn chỉ giữ lỗi có nhắc tới LegacyStockLookup:

~~~java
Violations onlyLegacy = violations.filter(
        violation -> violation.hasMessageContaining("LegacyStockLookup"));
~~~

Kết quả onlyLegacy chỉ còn các violation khớp điều kiện. Nếu gọi onlyLegacy.throwIfPresent(), các violation này vẫn làm test thất bại.

Để bỏ qua một ngoại lệ đã được chấp nhận và giữ lại mọi lỗi khác, cần đảo predicate:

~~~java
Violations remaining = violations.filter(
        violation -> !isApprovedTemporaryException(violation));
~~~

Trong ví dụ này:

- Predicate trả về false cho violation đã được chấp nhận, vì vậy violation đó bị loại khỏi kết quả.
- Predicate trả về true cho các violation còn lại, vì vậy chúng tiếp tục được giữ lại.
- throwIfPresent() chỉ ném exception nếu tập remaining vẫn còn lỗi.

Nếu quên dấu phủ định, bộ lọc sẽ giữ đúng ngoại lệ cần bỏ qua và loại những lỗi khác. Đây là lỗi logic nguy hiểm vì test có thể cho kết quả ngược với mục đích của nhóm.

## 7. Nhận diện ngoại lệ hẹp bằng Violation.hasMessageContaining()

Trong API của Spring Modulith, Violation biểu diễn một lỗi kiến trúc riêng lẻ. Có thể dùng hasMessageContaining() để nhận diện một đoạn thông điệp cụ thể.

Định nghĩa predicate cho ngoại lệ của bài lab:

~~~java
import org.springframework.modulith.core.Violation;

private static boolean isApprovedTemporaryException(Violation violation) {
    return violation.hasMessageContaining("LegacyStockLookup")
            && violation.hasMessageContaining("InventoryRepository");
}
~~~

Predicate yêu cầu cả tên consumer LegacyStockLookup và kiểu nội bộ InventoryRepository cùng xuất hiện trong message. Điều kiện này hẹp hơn nhiều so với việc bỏ qua mọi violation có nhắc tới module order hoặc inventory.

Đoạn text cần được xác nhận từ message thực tế trên phiên bản Spring Modulith mà dự án đang sử dụng. Nếu message không chứa tên đơn giản như ví dụ, hãy điều chỉnh theo đoạn ổn định có trong diagnostic thực tế.

Không dùng một điều kiện quá rộng như:

~~~java
private static boolean isApprovedTemporaryException(Violation violation) {
    return violation.hasMessageContaining("order");
}
~~~

Điều kiện trên có thể vô tình bỏ qua nhiều lỗi khác của module order, kể cả lỗi mới xuất hiện sau này.

## 8. Kết hợp detectViolations(), filter() và throwIfPresent()

Đây là mẫu xử lý chính của bài:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violation;
import org.springframework.modulith.core.Violations;

class ModularityTests {

    @Test
    void ignoresOnlyApprovedLegacyViolation() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        Violations detected = modules.detectViolations();

        detected.getMessages().forEach(System.out::println);

        Violations remaining = detected.filter(
                violation -> !isApprovedTemporaryException(violation));

        remaining.throwIfPresent();
    }

    private static boolean isApprovedTemporaryException(Violation violation) {
        return violation.hasMessageContaining("LegacyStockLookup")
                && violation.hasMessageContaining("InventoryRepository");
    }
}
~~~

Luồng xử lý:

~~~mermaid
flowchart TD
    A["ApplicationModules.detectViolations()"] --> B["Violations"]
    B --> C["In và xem getMessages()"]
    C --> D["filter(predicate)"]
    D --> E{"Violation có khớp ngoại lệ đã duyệt?"}
    E -->|Có| F["Predicate false: loại khỏi tập còn lại"]
    E -->|Không| G["Predicate true: giữ lại"]
    F --> H["Tập remaining"]
    G --> H
    H --> I{"Còn violation?"}
    I -->|Không| J["throwIfPresent() kết thúc bình thường"]
    I -->|Có| K["throwIfPresent() ném Violations"]
~~~

Mẫu này không sửa dependency sai. Nó chỉ cho phép pipeline tiếp tục trong thời gian ngoại lệ đã được chấp thuận còn tồn tại. Nhóm vẫn cần có issue, người phụ trách và thời hạn để xóa ngoại lệ.

## 9. Bảo đảm bộ lọc không che lỗi mới

Một bộ lọc tốt phải chứng minh được hai điều:

1. Ngoại lệ đã duyệt được loại khỏi tập còn lại.
2. Một violation khác vẫn được giữ và khiến test thất bại.

Để kiểm tra điều thứ hai, tạo thêm một dependency sai có chủ đích, chẳng hạn một lớp trong order truy cập ProductRepository thuộc catalog.internal. Khi đó, message mới không khớp đồng thời LegacyStockLookup và InventoryRepository.

~~~java
package com.example.shop.order.internal;

import com.example.shop.catalog.internal.ProductRepository;
import org.springframework.stereotype.Component;

@Component
class LegacyProductLookup {

    private final ProductRepository repository;

    LegacyProductLookup(ProductRepository repository) {
        this.repository = repository;
    }
}
~~~

Chạy lại test:

- Violation LegacyStockLookup → InventoryRepository được loại khỏi tập remaining.
- Violation LegacyProductLookup → ProductRepository không khớp ngoại lệ.
- remaining.hasViolations() trả về true.
- remaining.throwIfPresent() ném exception và test thất bại.

Đây là kết quả mong muốn. Bộ lọc cho phép đúng một ngoại lệ và vẫn giữ hàng rào cho mọi lỗi khác.

## 10. Viết assertion cho kết quả sau lọc

Có thể viết test rõ hơn bằng JUnit:

Các method test dưới đây được đặt trong class ModularityTests ở cùng package com.example.shop. Dùng các import sau cho cả ba ví dụ:

~~~java
package com.example.shop;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;
~~~

~~~java
@Test
void filtersOnlyTheApprovedLegacyDependency() {
    Violations detected =
            ApplicationModules.of(ShopApplication.class).detectViolations();

    assertTrue(detected.hasViolations(),
            "Fixture cần có violation legacy đã biết");

    Violations remaining = detected.filter(
            violation -> !isApprovedTemporaryException(violation));

    assertTrue(remaining.hasViolations(),
            "Fixture thứ hai cần chứng minh lỗi ngoài ngoại lệ vẫn còn");

    remaining.getMessages().forEach(System.out::println);
}
~~~

Test trên giả định fixture đã có cả ngoại lệ được duyệt và một lỗi khác. Nếu chỉ có một ngoại lệ, assertion remaining.hasViolations() phải là false. Hãy thiết kế fixture rõ ràng thay vì dùng cùng một assertion cho hai trạng thái khác nhau.

Một test riêng cho trường hợp chỉ có ngoại lệ:

~~~java
@Test
void leavesNoViolationsWhenOnlyApprovedExceptionExists() {
    Violations detected =
            ApplicationModules.of(ShopApplication.class).detectViolations();

    Violations remaining = detected.filter(
            violation -> !isApprovedTemporaryException(violation));

    assertFalse(remaining.hasViolations());
    remaining.throwIfPresent();
}
~~~

Một test khác cho trường hợp có violation ngoài ngoại lệ:

~~~java
@Test
void stillFailsWhenAnUnexpectedViolationExists() {
    Violations detected =
            ApplicationModules.of(ShopApplication.class).detectViolations();

    Violations remaining = detected.filter(
            violation -> !isApprovedTemporaryException(violation));

    assertTrue(remaining.hasViolations());
    assertThrows(Violations.class, remaining::throwIfPresent);
}
~~~

Hai ví dụ này là hai trạng thái fixture khác nhau. Không đặt cả hai test trên cùng một cấu trúc source nếu cấu trúc đó luôn tạo đồng thời hai violation.

## 11. Lọc theo message có giới hạn gì?

Violation cung cấp message và phương thức hasMessageContaining(), vì vậy lọc theo message là cách thực tế để nhận diện một ngoại lệ cụ thể. Tuy nhiên, message vẫn là nội dung chẩn đoán và có thể thay đổi khi phiên bản thư viện hoặc cách diễn đạt diagnostic thay đổi.

Khi dùng message để lọc:

- Chọn chuỗi đủ đặc trưng cho đúng dependency.
- Kết hợp nhiều điều kiện khi cần phân biệt consumer và provider.
- Không dùng từ chung như order, inventory, internal hoặc dependency một mình.
- Khi nâng phiên bản Spring Modulith, kiểm tra lại message và test filter.
- Nếu message thay đổi, cập nhật predicate sau khi xác nhận violation vẫn là cùng một ngoại lệ.

Không nên phân tích message thành một parser tổng quát cho mọi violation. Bộ lọc chỉ nên xử lý một ngoại lệ đã biết, không trở thành hệ thống suy đoán nguyên nhân lỗi.

## 12. Không biến ngoại lệ tạm thời thành chính sách lâu dài

Một filter được đưa vào test có thể khiến violation đã biết không còn chặn build. Vì vậy, ngoại lệ phải được quản lý giống một khoản nợ kỹ thuật:

| Thông tin | Ví dụ |
|---|---|
| Consumer | LegacyStockLookup |
| Provider | inventory |
| Reference nội bộ | InventoryRepository |
| Lý do | Caller cũ chưa được chuyển sang API module |
| Mã theo dõi | ARCH-142 |
| Owner | Nhóm phụ trách order migration |
| Hạn xử lý | Release đã thống nhất trong kế hoạch migration |
| Điều kiện xóa filter | Không còn reference tới InventoryRepository |

Khi điều kiện hoàn tất đạt được:

1. Chuyển LegacyStockLookup sang InventoryAvailability.
2. Xóa import tới inventory.internal.InventoryRepository.
3. Xóa predicate isApprovedTemporaryException().
4. Gọi ApplicationModules.verify() hoặc detectViolations().throwIfPresent() không có ngoại lệ.
5. Xóa issue migration khi code và kiểm tra đã hoàn tất.

Đừng chỉ xóa filter rồi xem test thất bại là xong. Hãy sửa dependency trong source trước để ranh giới module thực sự được tuân thủ.

## 13. Khi nào dùng detectViolations() và khi nào dùng verify()?

| Nhu cầu | API phù hợp |
|---|---|
| Chỉ cần test pass/fail theo tất cả quy tắc | verify() |
| Cần xem từng violation trước khi quyết định | detectViolations() |
| Cần tạm bỏ qua một ngoại lệ đã duyệt | detectViolations().filter(...).throwIfPresent() |
| Cần hiển thị toàn bộ message trong báo cáo | detectViolations().getMessages() |
| Cần chạy verification với tập ArchRule bổ sung | detectViolations(options) |
| Cần xác nhận tập sau lọc rỗng | hasViolations() rồi throwIfPresent() |

detectViolations() không thay thế verify() trong mọi trường hợp. Nó cung cấp quyền kiểm soát kết quả trước khi ném exception. Nếu không có ngoại lệ cần xử lý, verify() vẫn là cách ngắn gọn để bảo vệ module boundary.

## 14. Kiểm tra ảnh hưởng của VerificationOptions

Mặc định, verification có thể bao gồm các rule bổ sung tùy theo classpath, chẳng hạn jMolecules verification khi thư viện tương ứng hiện diện.

Nếu bài lab cần dùng options, có thể truyền options vào detectViolations():

~~~java
import org.springframework.modulith.core.VerificationOptions;

VerificationOptions options = VerificationOptions.defaults();

Violations violations =
        ApplicationModules.of(ShopApplication.class)
                .detectViolations(options);
~~~

Nếu thêm ArchRule tùy chỉnh, hãy xác định rõ muốn giữ rule bổ sung mặc định hay thay thế chúng. andAdditionalVerifications() đăng ký rule mới bên cạnh các rule mặc định; withAdditionalVerifications() định nghĩa lại tập additional verification. Không thay đổi options chỉ để làm biến mất violation mà chưa xác định nguồn của nó.

Khi so sánh hai lần chạy, ghi lại classpath và options. Nếu classpath khác nhau, tập verification có thể khác nhau dù source không thay đổi.

## 15. Bài tập tự thực hành

### Bài tập A — Quan sát toàn bộ violation

1. Tạo ApplicationModules từ ShopApplication.
2. Gọi detectViolations().
3. In tất cả message.
4. Xác nhận hasViolations() phản ánh đúng trạng thái.
5. Ghi lại consumer, provider và package trong từng message.

Kết quả mong đợi: bạn có thể xác định chính xác dependency nào đang vi phạm mà không phải đọc toàn bộ stack trace.

### Bài tập B — Lọc đúng một ngoại lệ

1. Tạo predicate nhận diện LegacyStockLookup và InventoryRepository.
2. Gọi filter() với predicate phủ định.
3. In getMessages() của tập còn lại.
4. Gọi throwIfPresent().

Kết quả mong đợi: ngoại lệ ARCH-142 không còn trong tập remaining; mọi violation khác vẫn được giữ.

### Bài tập C — Chứng minh lỗi mới không bị che

1. Thêm LegacyProductLookup tham chiếu catalog.internal.ProductRepository.
2. Chạy detectViolations().
3. Dùng lại predicate của bài tập B.
4. Xác nhận remaining.hasViolations() là true.
5. Xác nhận throwIfPresent() ném Violations.

Kết quả mong đợi: bộ lọc không loại bỏ lỗi mới của catalog.

### Bài tập D — Gỡ ngoại lệ

1. Chuyển LegacyStockLookup sang InventoryAvailability.
2. Xóa dependency tới InventoryRepository.
3. Xóa predicate ngoại lệ và mã ARCH-142 khỏi test.
4. Chạy module verification không có filter.

Kết quả mong đợi: test pass mà không cần ngoại lệ.

## 16. Tiêu chí nghiệm thu bài lab

Bài lab hoàn tất khi:

- [ ] Có thể tạo module model từ ShopApplication.
- [ ] Có ít nhất một violation được tạo có chủ đích.
- [ ] Đã in và đọc getMessages().
- [ ] Hiểu hasViolations() và throwIfPresent().
- [ ] Hiểu filter() giữ các phần tử predicate chấp nhận.
- [ ] Predicate ngoại lệ nhận diện đúng cả consumer và provider.
- [ ] Violation đã duyệt được loại khỏi tập remaining.
- [ ] Violation không liên quan vẫn khiến test thất bại.
- [ ] Ngoại lệ có mã theo dõi, owner và điều kiện kết thúc.
- [ ] Sau migration, filter được xóa và verification chạy không ngoại lệ.

## 17. Lỗi thường gặp khi lọc violation

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng filter(v -> isApproved(v)) rồi throwIfPresent() | Giữ lại đúng violation muốn bỏ qua | Dùng phủ định để giữ các lỗi còn lại |
| Lọc theo tên module quá chung | Che cả lỗi mới trong module đó | Kết hợp consumer và provider cụ thể |
| Không đọc getMessages() trước khi viết predicate | Predicate không khớp hoặc khớp nhầm | In diagnostic thực tế trước |
| Bỏ qua toàn bộ additional verification | Mất các rule kiến trúc có giá trị | Chỉ lọc violation cụ thể |
| Không kiểm tra hasViolations() sau lọc | Không biết tập còn lỗi hay đã rỗng | Kiểm tra trạng thái trước throwIfPresent() |
| Giữ ngoại lệ mãi mãi | Dependency sai trở thành bình thường | Có owner, issue và điều kiện xóa |
| Chỉ kiểm tra test pass với ngoại lệ | Không chứng minh lỗi khác vẫn bị bắt | Thêm fixture tạo violation thứ hai |
| Lọc message bằng chuỗi mong manh | Có thể sai sau khi nâng version | Dùng đoạn đặc trưng và kiểm tra lại khi nâng cấp |

## 18. Kết luận

ApplicationModules.detectViolations() cho phép thu thập và xử lý các lỗi kiến trúc trước khi quyết định ném exception. Đối tượng Violations cung cấp getMessages(), hasViolations(), filter() và throwIfPresent(); mỗi Violation có thể được kiểm tra qua message hoặc hasMessageContaining().

Hãy nhớ rằng filter() giữ lại các phần tử khớp predicate. Muốn bỏ qua một ngoại lệ đã được duyệt, predicate phải trả về false cho ngoại lệ đó và true cho các violation còn lại. Bộ lọc cần nhận diện hẹp, có owner và thời hạn; test phải chứng minh một violation khác vẫn làm thất bại. Khi migration kết thúc, sửa dependency trong source, xóa filter và khôi phục verification đầy đủ. Như vậy, detectViolations() trở thành công cụ quản lý chuyển tiếp có kiểm soát thay vì cơ chế che giấu lỗi kiến trúc.

## Tài liệu tham khảo

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [ApplicationModules API — Spring Modulith 1.4.13](https://docs.spring.io/spring-modulith/docs/1.4.13/api/org/springframework/modulith/core/ApplicationModules.html)
- [Violations API — Spring Modulith 1.4.13](https://docs.spring.io/spring-modulith/docs/1.4.13/api/org/springframework/modulith/core/Violations.html)
- [Violation API — Spring Modulith 1.4.13](https://docs.spring.io/spring-modulith/docs/1.4.13/api/org/springframework/modulith/core/Violation.html)
