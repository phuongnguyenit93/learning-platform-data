# Đưa verify vào build sau khi module model ổn định

Trong chương **Refactoring an existing app** của **SPRING_MODULITH_VERIFICATION_TESTING**, một bước quyết định khi chuyển ứng dụng Spring Boot cũ sang Spring Modulith là biến **kiểm chứng ranh giới module** thành điều kiện bắt buộc của build. Sau khi đã tổ chức package, xác định API công khai và thống nhất quy tắc phụ thuộc, `ApplicationModules.verify()` phải chạy tự động mỗi khi có thay đổi. Nếu cấu trúc bị xâm phạm, build và quality gate trong CI cần thất bại trước khi code được hợp nhất.

Mục tiêu không chỉ là thêm một phương thức test: cần chọn **thời điểm model đủ ổn định**, kết nối test đúng vào vòng đời build, chứng minh test thực sự được thực thi, kiểm soát các ngoại lệ của ứng dụng cũ và kết hợp `@ApplicationModuleTest`, kiểm thử event, DB, tích hợp để phòng hồi quy hành vi. Ví dụ dùng Java 17+, JUnit Jupiter, Spring Boot 3.x và Spring Modulith; tên package giả định ứng dụng `com.example.shop` với module `orders` và `inventory`.

## 1. Xác định tiêu chí “module model ổn định”

**Ổn định** không có nghĩa kiến trúc không thể thay đổi nữa. Nó có nghĩa nhóm đã quyết định đủ rõ các ranh giới để mỗi lần vi phạm là một tín hiệu đáng tin cậy, không còn là nhiễu do chia module tạm thời.

| Tiêu chí đầu vào | Câu hỏi phải trả lời được | Bằng chứng nên lưu trong PR |
| --- | --- | --- |
| Điểm gốc phát hiện module | Lớp Spring Boot application ở package nào? Những package nào được nhận là application module? | Cây package đã duyệt và kết quả kiểm tra mô hình |
| Quyền sở hữu nghiệp vụ | Ai sở hữu đơn hàng, tồn kho, dữ liệu và giao dịch? | Sơ đồ module và use case chính |
| API công khai | Module khác được gọi kiểu và hợp đồng nào? | Danh sách facade, event, interface công khai |
| Phụ thuộc được phép | `orders` được phụ thuộc `inventory` hay các module nào nữa? | Quy tắc `allowedDependencies` và lý do |
| Giao tiếp đồng bộ/bất đồng bộ | Khi nào gọi API, khi nào phát/nhận event? | Hợp đồng event, transaction và lỗi |
| Di sản chưa xử lý | Có vòng phụ thuộc, truy cập package nội bộ hay shared database nào đang tồn tại? | Danh sách nợ kiến trúc có owner |
| Kịch bản hành vi chuẩn | Những kết quả nào phải được bảo toàn qua refactor? | Test chấp nhận cho đường đi quan trọng |

Ví dụ đơn giản:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java         # API công khai của module orders
│   └── internal
│       └── OrderJpaRepository.java
└── inventory
    ├── StockAvailability.java   # API công khai của module inventory
    └── internal
        └── StockJpaRepository.java
~~~

Trong mô hình package mặc định, các package trực tiếp dưới root được nhận diện là application module; các package con như `inventory.internal` thuộc chi tiết triển khai, trừ khi đã công bố named interface. Không tự suy “cứ public Java là API module”: phạm vi API theo Spring Modulith còn phụ thuộc vị trí package và cấu hình module.

**Điều kiện bật gate bắt buộc:** mô hình đã được review, không còn vi phạm đang được coi là “tạm chấp nhận mà không có kế hoạch”, và bộ luật kiểm chứng đồng nhất giữa máy lập trình viên với CI. Nếu vẫn còn lỗi kiến trúc hợp lệ đang cần migrate, dùng giai đoạn quan sát có hạn định trước khi biến gate thành bắt buộc; không giảm độ nghiêm ngặt của luật chỉ để lấy build xanh.

## 2. Chốt quy tắc kiến trúc thành một hợp đồng kiểm thử

Spring Modulith dựng mô hình application module từ điểm gốc ứng dụng và phân tích phụ thuộc giữa các module. Kiểm chứng cấu trúc giúp phát hiện các trường hợp như **phụ thuộc vòng** hoặc **tham chiếu vượt qua API được công bố**, đồng thời áp dụng những hạn chế phụ thuộc mà nhóm đã khai báo.

| Quy tắc | Ví dụ vi phạm | Hướng sửa đúng |
| --- | --- | --- |
| Tránh phụ thuộc vòng | `orders → inventory → orders` | Tách API/ownership hoặc dùng event với hướng phụ thuộc rõ |
| Chỉ dùng API của module khác | `orders` phụ thuộc `inventory.internal.StockJpaRepository` | Dùng facade/interface được công bố bởi inventory |
| Tôn trọng `allowedDependencies` | `orders` gọi trực tiếp một module ngoài danh sách | Điều chỉnh thiết kế hoặc cập nhật luật sau review kiến trúc |
| Không phình API tùy tiện | Chuyển toàn bộ `internal` lên package root để test pass | Công bố riêng contract thực sự cần thiết |

Điểm quan trọng: `verify()` kiểm tra **quan hệ có thể quan sát được ở cấp cấu trúc Java**, không kiểm tra database isolation, event có được xử lý sau commit hay không, cũng không tự biết kết quả nghiệp vụ của một use case có chính xác. Do đó phải giữ separate regression tests cho hành vi.

Tạo một lớp kiểm thử kiến trúc đặt tại package gốc:

~~~java
// src/test/java/com/example/shop/ModuleArchitectureTests.java
package com.example.shop;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    @Tag("architecture")
    void preservesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là **JUnit Jupiter test**, nên build sẽ thất bại khi assertion/verification ném lỗi, miễn là task test được cấu hình và thực sự chạy lớp này. Test không cần khởi động toàn bộ Spring application context; phép phân tích kiến trúc được thực hiện từ mô hình module của `ShopApplication`. Mẫu package và tên `ShopApplication` phải khớp ứng dụng thật.

## 3. Củng cố API và quy tắc phụ thuộc trước khi khóa build

Giả sử orders được phép hỏi inventory về khả năng giữ hàng nhưng không được biết cách inventory truy cập database. Công bố hợp đồng trong package API của inventory:

~~~java
// src/main/java/com/example/shop/inventory/StockAvailability.java
package com.example.shop.inventory;

public interface StockAvailability {
    boolean canReserve(String sku, int quantity);
}
~~~

Orders sử dụng hợp đồng ấy qua constructor injection:

~~~java
// src/main/java/com/example/shop/orders/OrderReservationService.java
package com.example.shop.orders;

import com.example.shop.inventory.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class OrderReservationService {

    private final StockAvailability availability;

    public OrderReservationService(StockAvailability availability) {
        this.availability = availability;
    }

    public boolean reserveAllowed(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return availability.canReserve(sku, quantity);
    }
}
~~~

Giả định inventory đăng ký một bean triển khai `StockAvailability`. Nếu nhóm quyết định orders chỉ được phụ thuộc inventory, khai báo ranh giới tại `src/main/java/com/example/shop/orders/package-info.java`:

~~~java
@ApplicationModule(allowedDependencies = "inventory")
package com.example.shop.orders;

import org.springframework.modulith.ApplicationModule;
~~~

`allowedDependencies` giới hạn **module đích** được phép tham chiếu; nó **không** công bố mọi kiểu trong `inventory.internal`. Nếu muốn công bố có chủ đích một package con cho nhiều module khác sử dụng, Spring Modulith hỗ trợ **named interface**:

~~~java
// src/main/java/com/example/shop/inventory/spi/package-info.java
@NamedInterface("reservation")
package com.example.shop.inventory.spi;

import org.springframework.modulith.NamedInterface;
~~~

Khi các kiểu công khai được đặt trong package `inventory.spi` và nhóm muốn orders chỉ dùng named interface này, có thể khai báo `@ApplicationModule(allowedDependencies = "inventory::reservation")` trong `orders/package-info.java`. Đây là **phương án thay thế** cho khai báo `"inventory"` phía trên, dùng khi thực tế có nhiều interface/khối API cần hạn chế chi tiết; tránh để đồng thời hai định nghĩa mâu thuẫn ở một package. Hãy giữ API công khai nhỏ, ổn định và độc lập với loại repository bên dưới.

## 4. Bảo đảm JUnit và dependency test có mặt trong dự án

Test ở mục 2 chỉ được chạy nếu framework kiểm thử, engine và Spring Modulith test dependency nằm trên test classpath. Với **Gradle Groovy DSL** và Spring Boot dependency management đã cấu hình, có thể dùng:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Ví dụ giả định dự án đã import **Spring Modulith BOM** hoặc cơ chế quản lý phiên bản tương ứng. Nếu chưa có, phải cấu hình version management nhất quán với phiên bản Spring Boot, không để build tự suy ra dependency version. Sau đó kiểm tra tên JUnit test class và việc test engine phát hiện method:

~~~text
ModuleArchitectureTests
  preservesModuleBoundaries()
~~~

Một test có code chính xác nhưng bị bỏ qua do package nhầm, task dùng JUnit 4 runner hoặc bộ lọc test là **gate vô hiệu**. Không coi `BUILD SUCCESSFUL` là bằng chứng đủ nếu chưa quan sát được tên test, tổng số test đã thực thi và kết quả verification trong báo cáo.

Với Maven, khai báo dependency test tương ứng và đảm bảo phiên bản Surefire hỗ trợ JUnit Jupiter:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Lớp có hậu tố `Tests` được Maven Surefire nhận diện theo naming pattern mặc định của bản plugin hiện đại. Trong build Maven chuẩn, `mvn -B verify` chạy pha test trước pha verify. Nếu dự án tùy chỉnh include/exclude hay profile, phải chứng minh `ModuleArchitectureTests` không bị bỏ qua. Không phụ thuộc vào việc developer nhớ chạy một lệnh thủ công khác.

## 5. Kết nối verify vào vòng đời Gradle check

Có hai cách hợp lệ. **Cách đơn giản**: đặt `ModuleArchitectureTests` trong source set `test`, chạy JUnit Platform, và để `check` (thuộc Java plugin) phụ thuộc `test`. Cấu hình tối thiểu:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}

// Với Java plugin: check đã phụ thuộc test theo mặc định.
// CI chạy: ./gradlew clean check
~~~

Khi suite test lớn, có thể tạo **task riêng** để kiến trúc chạy nhanh và được báo cáo độc lập. Dùng JUnit tag để tránh chạy hai lần cùng một test:

~~~groovy
// build.gradle trong project chứa ShopApplication
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'architecture'
    }
}

tasks.register('architectureTest', Test) {
    group = 'verification'
    description = 'Verify Spring Modulith boundaries'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'architecture'
    }
}

tasks.named('check') {
    dependsOn tasks.named('architectureTest')
}
~~~

Mẫu này giả định dự án đã áp dụng **Java plugin** để có `sourceSets.test`, và `ModuleArchitectureTests` đã được gắn `@Tag("architecture")`. Với cấu hình trên:

- `test` chạy các test thông thường và loại tag architecture.
- `architectureTest` chạy test có tag architecture, dùng chung code đã compile của source set test.
- `check` kéo theo cả test thông thường và architecture test (qua dependency mặc định của Java plugin và dòng `dependsOn`).

Có thể chạy `./gradlew architectureTest` để xem kết quả gate kiến trúc độc lập, hoặc `./gradlew clean check` để kiểm tra toàn bộ. Trong multi-project Gradle, phải đăng ký task tại **đúng subproject có ứng dụng và test**, ví dụ `:shop-app:check`; đặt cấu hình ở root nhưng không áp dụng xuống project chứa test sẽ không tạo gate như mong muốn.

## 6. Tích hợp vào CI và bảo đảm gate có quyền chặn merge

Build local và CI phải thực thi **cùng lệnh, cùng tập test, cùng ruleset**. Ví dụ một đoạn job GitHub Actions đã có `gradlew` trong repository:

~~~yaml
name: Verify application modules
on: [push, pull_request]

jobs:
  module-verification:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - uses: gradle/actions/setup-gradle@v4
      - name: Build, architecture and regression tests
        run: ./gradlew --no-daemon clean check
~~~

Đây là ví dụ cấu hình, không ngụ ý repository thực tế đang dùng GitHub Actions, Gradle hay JDK 21. Với CI đang có, điều kiện cốt lõi là:

1. **Trigger** áp dụng cho branch/PR cần bảo vệ.
2. **Task** được gọi đúng từ project chứa architecture test.
3. **Exit code** khác 0 làm job thất bại; job phải được cấu hình là required check nếu muốn chặn merge.
4. **Báo cáo JUnit/Gradle** còn truy vết được test `preservesModuleBoundaries` đã chạy.
5. Không vô tình bật tùy chọn bỏ qua lỗi như `continue-on-error` hoặc `-x architectureTest` trong pipeline bắt buộc.

Nếu dùng Maven, áp dụng cùng logic qua `mvn -B verify`, kiểm tra Surefire reports và trạng thái required job. Chỉ thêm file workflow mà không đánh dấu status check là bắt buộc có thể khiến CI đỏ nhưng PR vẫn được hợp nhất, tùy chính sách repository.

## 7. Chứng minh gate phát hiện vi phạm bằng phép thử âm

Sau khi setup, thực hiện một **negative control** trên branch tạm (không đưa lỗi cố ý vào main). Chọn một kiểu `public` nằm trong `com.example.shop.inventory.internal`; thêm tham chiếu thật từ orders tới kiểu đó, chẳng hạn field có type là kiểu internal:

~~~java
// Đoạn mã CỐ Ý SAI, chỉ để thử gate rồi gỡ bỏ
package com.example.shop.orders;

import com.example.shop.inventory.internal.StockJpaRepository;

final class BoundaryCanary {
    private StockJpaRepository forbiddenDependency;
}
~~~

Ví dụ giả định `StockJpaRepository` có modifier public để Java cho phép field tham chiếu. Đặt field thật để phụ thuộc xuất hiện trong bytecode; **một lệnh import không dùng** có thể bị compiler loại bỏ nên không phải phép thử đáng tin.

Sau đó xác nhận chuỗi kết quả:

~~~text
Trước khi cấy lỗi:
  architectureTest = PASS
  check            = PASS

Cấy field phụ thuộc inventory.internal:
  architectureTest = FAIL (module boundary violation)
  check            = FAIL
  CI required job  = FAIL (PR bị chặn)

Gỡ lỗi cố ý:
  architectureTest = PASS
  check            = PASS
~~~

Nếu code biên dịch nhưng test vẫn xanh, phải truy nguyên: sai root package, `inventory.internal` đã được công bố nhầm, test không được chọn bởi JUnit tag, task không kết nối vào `check`, hoặc pipeline thực thi project khác. Nếu field không compile thì lỗi thuộc Java accessibility, không phải bằng chứng `ApplicationModules.verify()` đã phát hiện vi phạm. Lưu log và tên test vào bằng chứng kiểm thử gate.

Ngoài thử truy cập internal, có thể cấy một phụ thuộc vòng hoặc phụ thuộc đến module ngoài `allowedDependencies`. Chỉ chọn một lỗi mỗi lần để xác định rule nào thực sự chặn build; xóa sạch canary sau thử nghiệm.

## 8. Kết hợp @ApplicationModuleTest để bảo vệ hành vi sau refactor

Gate kiến trúc chứng minh hướng phụ thuộc hợp lệ, nhưng không chứng minh hành vi module vẫn đúng. Sau khi thay `orders` gọi repository nội bộ bằng API inventory, cần kiểm tra contract ứng dụng theo hai mức: test domain/service trong module, và test tích hợp các tác động liên module.

Ví dụ một service trong orders phát event khi xác nhận, với quy tắc phải giữ hàng trước:

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

    public void confirm(UUID id, boolean stockReserved) {
        if (!stockReserved) {
            throw new IllegalStateException("Stock reservation required");
        }
        events.publishEvent(new OrderConfirmed(id));
    }
}
~~~

JUnit `@ApplicationModuleTest` đặt cùng package module orders:

~~~java
// src/test/java/com/example/shop/orders/OrderConfirmationTests.java
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
class OrderConfirmationTests {

    @Autowired
    OrderConfirmation confirmation;

    @Autowired
    ApplicationEvents recordedEvents;

    @Test
    void publishesEventWithMatchingOrderId() {
        UUID orderId = UUID.randomUUID();

        confirmation.confirm(orderId, true);

        assertEquals(1L, recordedEvents.stream(OrderConfirmed.class)
                .filter(event -> orderId.equals(event.orderId()))
                .count());
    }

    @Test
    void rejectsConfirmationWithoutReservation() {
        UUID orderId = UUID.randomUUID();

        assertThrows(IllegalStateException.class,
                () -> confirmation.confirm(orderId, false));
        assertEquals(0L, recordedEvents.stream(OrderConfirmed.class)
                .filter(event -> orderId.equals(event.orderId()))
                .count());
    }
}
~~~

Ví dụ xác minh **event được publish trong test context**, không chứng minh consumer xử lý thành công, event sau commit, persistence hay idempotency. Khi flow thật ghi database và dùng listener `@TransactionalEventListener(phase = AFTER_COMMIT)`, bổ sung test với commit thực tế và kiểm tra trạng thái DB/consumer. Với luồng bất đồng bộ, cần chờ điều kiện quan sát có timeout hữu hạn; với transaction bị rollback, xác minh event không tạo side effect sai.

Nếu test `@ApplicationModuleTest` cần dựng các module phụ thuộc trực tiếp, cân nhắc `@ApplicationModuleTest(mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES)`. Mở rộng phạm vi phải có lý do; test quá rộng có thể làm regression suite chậm và che giấu việc module không độc lập như thiết kế.

## 9. Xử lý ứng dụng cũ chưa hết vi phạm mà không vô hiệu hóa quality gate

Trong legacy application, nhiều package chưa thể tách chỉ trong một PR. Thay vì xóa `verify()` hoặc mở tất cả package thành API, dùng lộ trình minh bạch:

| Giai đoạn | Trạng thái kiến trúc | Cơ chế kiểm soát |
| --- | --- | --- |
| A – quan sát | Chưa đạt ruleset đã duyệt | Chạy verification trong job phân tích, lưu lỗi và owner; chưa gắn làm required check |
| B – sửa theo lát cắt | Xử lý từng module/cạnh phụ thuộc | Test module và regression tests bảo vệ từng lần chuyển đổi |
| C – sạch ở phạm vi đã khóa | Toàn bộ boundary thuộc phạm vi bắt buộc pass | Bật `verify()` trong `check` và required CI job |
| D – duy trì | Thêm tính năng hoặc tách module mới | Mọi PR tiếp tục phải pass cùng quy tắc, review thay đổi API/ruleset |

Trong giai đoạn A–B, nếu cần chấp nhận tạm một quan hệ, phải có **quyết định kiến trúc, người chịu trách nhiệm và hạn xử lý**. Khi dùng named interface/`allowedDependencies`, chỉ công bố contract thực sự có chủ đích; không mở quy tắc rộng chỉ để xóa cảnh báo. Đặc biệt, đừng tuyên bố “module boundary được bảo vệ toàn repo” khi job `verify` chưa phải điều kiện bắt buộc.

Khi phân nhánh gradual refactor, tránh hai tình trạng: nhóm mới thêm vi phạm trong phần đang được dọn dẹp, hoặc nhóm dọn sửa contract gây regression chưa được test. Đặt checklist “không tăng vi phạm đã biết” cho review giai đoạn B và làm sạch dứt điểm trước khi chuyển C. Nếu muốn tự động hóa baseline từng phần, phải sử dụng cơ chế báo cáo/quy tắc được thiết kế và xác minh riêng; `ApplicationModules.verify()` tự thân là phép kiểm chứng fail/pass, **không phải công cụ tự loại trừ một danh sách vi phạm có sẵn**.

## 10. Vận hành gate: tối ưu thời gian, độ tin cậy và khả năng điều tra

Sau khi bật required check, theo dõi những chỉ số giúp duy trì niềm tin vào verification:

| Chỉ số vận hành | Dấu hiệu bất thường | Hành động |
| --- | --- | --- |
| Tỷ lệ test được phát hiện | `architectureTest` chạy 0 test | Kiểm tra tag, package, JUnit Platform, test classpath |
| Thời gian architecture task | Tăng mạnh qua mỗi release | Kiểm tra cấu hình test task, cache/CI runner, số module được phân tích |
| Tỷ lệ fail do vi phạm thật | Cùng lỗi xuất hiện liên tiếp | Làm rõ contract và cải thiện feedback tại PR |
| Test flakiness | Rerun cùng commit đổi kết quả | Tách nguyên nhân môi trường, DB, async tests; không tự bỏ qua test |
| Lỗi lọt qua nhưng kiến trúc pass | Hành vi DB/event/transaction sai | Bổ sung test hợp đồng và tích hợp, không đổ lỗi sai cho `verify()` |
| Thay đổi ruleset | Vi phạm biến mất sau sửa config | Review diff của `allowedDependencies`/named interfaces độc lập |

Phân tích một build fail theo thứ tự: **compile được không → architecture test có chạy không → lỗi là quan hệ phụ thuộc nào → module model nhận diện thế nào → thay đổi code hay luật nào gây ra**. Không sửa lỗi bằng cách gỡ `@Tag`, xóa test, dùng `-x architectureTest` hoặc đánh dấu job “allow failure” trên đường merge bắt buộc.

Cần lưu JUnit XML, báo cáo task Gradle/Maven, commit hash, phiên bản JDK/Spring Modulith và bằng chứng negative control. Trường hợp mô hình module thay đổi có chủ ý (tách module, đổi named interface) phải review quy tắc và test cùng lúc. Quality gate tốt có phản hồi **đọc được và làm lại được**, không chỉ báo một màu đỏ.

## 11. Checklist đưa verify vào build và bài tập thực hành

Dùng checklist sau trong PR khóa kiến trúc:

- [ ] Package root và danh sách application module được xác nhận bằng mô hình Spring Modulith thực tế.
- [ ] API công khai, named interface và `allowedDependencies` được duyệt; không công bố implementation để lách luật.
- [ ] Có `ModuleArchitectureTests` dùng `ApplicationModules.of(ShopApplication.class).verify()`.
- [ ] JUnit Platform và dependency test được cấu hình; kết quả report chứng minh method verification đã chạy.
- [ ] `check` (hoặc pha Maven `verify`) phụ thuộc đúng test kiến trúc tại đúng subproject.
- [ ] CI chạy cùng command với local, exit code làm job fail và job là required check khi merge.
- [ ] Negative control tạo **tham chiếu bytecode thực** tới internal package làm gate đỏ; gỡ lỗi rồi gate xanh.
- [ ] Regression tests bảo vệ contract module; event, DB, transaction và listener sau commit có test tích hợp khi liên quan.
- [ ] Không còn vi phạm chưa được xử lý trong phạm vi gate bắt buộc; ngoại lệ có owner và thời hạn.
- [ ] Test không bị skip/quarantine, build report cho biết số test và nguyên nhân fail.
- [ ] Khi thay module model/ruleset, diff được review như thay đổi kiến trúc, kèm cập nhật bài kiểm chứng.

**Bài tập có thể làm trực tiếp trên dự án mẫu:**

1. Đặt `ShopApplication` tại `com.example.shop`, tạo module `orders` và `inventory`, công bố `StockAvailability` và giới hạn orders chỉ phụ thuộc inventory.
2. Thêm `ModuleArchitectureTests`, cấu hình Gradle `architectureTest` và nối `check`; chạy riêng architecture task, sau đó chạy `clean check` và xem tên test trong report.
3. Cấy field `BoundaryCanary` tham chiếu một kiểu public nằm ở `inventory.internal`; xác nhận architecture task thất bại **do boundary violation** và CI chặn merge. Gỡ field rồi kiểm tra lại.
4. Đặt `OrderConfirmationTests` bằng `@ApplicationModuleTest`, xác minh đúng event khi có reservation và không có event khi bị từ chối. Nếu có DB/listener thật, bổ sung test sau commit tương ứng.
5. Giả lập một PR có chủ đích thay đổi API module; giải thích cần thay contract/`allowedDependencies` thế nào và tại sao phải review sự thay đổi luật thay vì chỉ làm xanh build.

**Tiêu chí hoàn thành:** người học chỉ ra được khi nào module model đã đủ ổn định để khóa bằng verification; tạo được test `ApplicationModules.verify()` chạy tự động trong build/CI; chứng minh được gate phát hiện vi phạm bằng negative control; bảo toàn hành vi bằng module/integration tests và vận hành quality gate mà không làm yếu ranh giới kiến trúc.
