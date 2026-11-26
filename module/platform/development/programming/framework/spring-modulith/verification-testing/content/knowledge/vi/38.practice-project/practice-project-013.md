# Ghi report và chẩn đoán một test thất bại

Đây là **dự án thực hành** trong `SPRING_MODULITH_VERIFICATION_TESTING`: rèn kỹ năng đọc một kết quả JUnit thất bại, truy nguyên từ assertion đến luồng tương tác giữa các module Spring Modulith và ghi lại report có thể tái hiện. Bài chỉ theo dõi **một lỗi cụ thể**: module `inventory` nhận sự kiện đặt hàng nhưng lưu số lượng giữ chỗ sai. Bài thực hành sử dụng `@ApplicationModuleTest`, `Scenario`, JPA và báo cáo Surefire; `ApplicationModules.verify()` là bước kiểm tra ranh giới bổ trợ khi xác nhận bản sửa.

Các lớp ứng dụng dưới đây là **mã mẫu của dự án thực hành**, không phải API có sẵn của Spring Modulith. Các đoạn log là **kết quả dự kiến khi cố ý cài lỗi**, không phải log được chạy trong tài liệu này. Bạn cần có ứng dụng Spring Boot 3.x với Java 17+, Spring Data JPA, H2 (test runtime), Spring Modulith Test, JUnit 5 và AssertJ; quản lý phiên bản phụ thuộc bằng Spring Boot/Spring Modulith BOM tương thích. Đặt lớp ứng dụng `ShopApplication` trong package `com.example.shop`, hai module trực tiếp dưới package gốc là `ordering` và `inventory`.

## 1. Xác định yêu cầu, test cần đỏ và bằng chứng phải bàn giao

**Yêu cầu nghiệp vụ:** khi `ordering` phát `OrderPlaced(orderId, quantity=3)` trong một transaction **đã commit**, listener thuộc `inventory` phải tạo một `Reservation` có cùng `orderId` và `quantity=3`. Mỗi `orderId` trong bài chỉ được tạo một bản ghi.

| Thành phần | Quy ước cho bài thực hành |
| --- | --- |
| Đầu vào | Sự kiện `OrderPlaced(UUID orderId, int quantity)` với `quantity=3` |
| Kết quả mong đợi | `Reservation.orderId` khớp và `Reservation.quantity == 3` |
| Test mục tiêu | `ReservationOnOrderPlacedTest.savesExactQuantity` |
| Lỗi được cài | Listener lưu `event.quantity() - 1`, vì vậy kết quả là `2` |
| Báo cáo bàn giao | Lệnh tái hiện, môi trường/commit, failure excerpt, nguyên nhân gốc, diff sửa, kết quả chạy lại |

Giữ cố định đầu vào và oracle (`expected=3`) trong suốt quá trình chẩn đoán. Không sửa assertion thành `isEqualTo(2)` chỉ để test xanh. Bài đạt yêu cầu khi chỉ ra được sự khác nhau giữa **triệu chứng** (expected 3, actual 2) và **nguyên nhân** (phép trừ trong listener), đồng thời ghi được bằng chứng sau khi sửa.

## 2. Chuẩn bị hai module và hợp đồng sự kiện

Cấu trúc package tối thiểu:

```text
com.example.shop
├── ShopApplication.java
├── ordering
│   └── OrderPlaced.java            # Public API của module ordering
└── inventory
    ├── Reservation.java
    ├── ReservationRepository.java
    ├── ReserveOnOrderPlaced.java
    └── ReservationOnOrderPlacedTest.java  # Trong src/test/java
```

Đặt event công khai ở **package gốc của module** `ordering`, để module `inventory` không phải import từ package nội bộ:

```java
// com/example/shop/ordering/OrderPlaced.java
package com.example.shop.ordering;

import java.util.UUID;

public record OrderPlaced(UUID orderId, int quantity) {}
```

Dùng một entity JPA để có trạng thái thật mà test có thể truy vấn:

```java
// com/example/shop/inventory/Reservation.java
package com.example.shop.inventory;

import jakarta.persistence.*;
import java.util.UUID;

@Entity
@Table(name = "reservations", uniqueConstraints =
        @UniqueConstraint(name = "uk_reservation_order", columnNames = "order_id"))
public class Reservation {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "order_id", nullable = false)
    private UUID orderId;

    @Column(nullable = false)
    private int quantity;

    protected Reservation() {}

    public Reservation(UUID orderId, int quantity) {
        this.orderId = orderId;
        this.quantity = quantity;
    }

    public UUID getOrderId() { return orderId; }
    public int getQuantity() { return quantity; }
}
```

```java
// com/example/shop/inventory/ReservationRepository.java
package com.example.shop.inventory;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ReservationRepository extends JpaRepository<Reservation, UUID> {
    Optional<Reservation> findByOrderId(UUID orderId);
}
```

Với bài lab, cấu hình H2 riêng cho test và tạo schema từ các entity (ví dụ `spring.jpa.hibernate.ddl-auto=create-drop` trong profile test). Không dùng database production để cài lỗi. Ràng buộc unique theo `order_id` giúp kết quả kiểm tra không bị nhầm với bản ghi trùng lặp.

## 3. Cài đúng một lỗi trong listener cần chẩn đoán

Listener của module `inventory` sử dụng `@ApplicationModuleListener`, hoạt động theo cơ chế transactional event listener và mặc định bất đồng bộ. Lệnh `save` vẫn chạy được nên đây là **lỗi nghiệp vụ**, không phải lỗi compile hoặc khởi tạo context:

```java
// com/example/shop/inventory/ReserveOnOrderPlaced.java
package com.example.shop.inventory;

import com.example.shop.ordering.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ReserveOnOrderPlaced {

    private final ReservationRepository reservations;

    ReserveOnOrderPlaced(ReservationRepository reservations) {
        this.reservations = reservations;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        // BUG CỐ Ý: lệch 1 so với quantity nhận từ module ordering.
        reservations.save(new Reservation(event.orderId(), event.quantity() - 1));
    }
}
```

Không cài thêm lỗi thiếu annotation, sai package hay xóa repository trong cùng lượt; như vậy chỉ có một biến gây lỗi để report có thể quy được nguyên nhân. Giữ event `OrderPlaced` trong API công khai: lỗi cần tìm là phép chuyển dữ liệu, không phải vi phạm phụ thuộc module.

## 4. Viết test tích hợp có assertion và transaction commit thật

Đặt lớp test trong package `com.example.shop.inventory` để `@ApplicationModuleTest` khởi động module chứa listener. Sử dụng `TransactionTemplate` để sự kiện được phát trong transaction và **commit** trước khi `Scenario` chờ tác dụng phụ của listener. Không đặt `@Transactional` lên test method vì rollback mặc định có thể khiến listener `AFTER_COMMIT` không chạy.

```java
// src/test/java/com/example/shop/inventory/ReservationOnOrderPlacedTest.java
package com.example.shop.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.ordering.OrderPlaced;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@ApplicationModuleTest
class ReservationOnOrderPlacedTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired ReservationRepository reservations;

    @Test
    void savesExactQuantity(Scenario scenario) {
        UUID orderId = UUID.randomUUID();
        OrderPlaced event = new OrderPlaced(orderId, 3);

        scenario.stimulate(() -> new TransactionTemplate(transactionManager)
                    .executeWithoutResult(tx -> publisher.publishEvent(event)))
                .andWaitForStateChange(() -> reservations.findByOrderId(orderId))
                .andVerify(found -> {
                    Reservation saved = found.orElseThrow();
                    assertThat(saved.getOrderId()).isEqualTo(orderId);
                    assertThat(saved.getQuantity())
                            .as("Số lượng đặt giữ phải bằng quantity của OrderPlaced")
                            .isEqualTo(event.quantity());
                });
    }
}
```

`Scenario.andWaitForStateChange(...)` chờ `Optional<Reservation>` chuyển từ rỗng sang có giá trị; `andVerify(...)` mới là nơi kiểm tra **nội dung**. Khi listener lưu số lượng `2`, test sẽ thất bại tại assertion. Nếu listener không chạy, test có thể thất bại vì chờ quá hạn; đó là một **kiểu lỗi khác**, cần phân biệt trong report. `PublishedEvents` chỉ chứng minh phía phát event, không thay thế assertion trên database của listener.

## 5. Tái hiện một test thất bại và giữ nguyên chứng cứ

Giả định dự án dùng Maven Wrapper và Surefire để chạy JUnit 5. Trong thư mục gốc dự án, chạy đúng test mục tiêu:

```powershell
# Windows PowerShell
.\mvnw.cmd "-Dtest=ReservationOnOrderPlacedTest" test
```

```bash
# Linux/macOS
./mvnw -Dtest=ReservationOnOrderPlacedTest test
```

Lưu lại command, đường dẫn module, mã commit hiện tại, phiên bản Java/Maven/Spring và thời điểm chạy. Sau khi test hoàn tất, lấy từ báo cáo Surefire (thường ở `target/surefire-reports/`) tên test, tổng số test chạy, failure message và stack trace. Không chỉnh sửa log gốc trước khi chụp phần liên quan vào report.

Ví dụ **log dự kiến** khi lỗi ở mục 3 được kích hoạt (câu chữ và tên báo cáo thực tế thay đổi theo phiên bản):

```text
ReservationOnOrderPlacedTest.savesExactQuantity  FAILED
Số lượng đặt giữ phải bằng quantity của OrderPlaced
expected: 3
 but was: 2
Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
```

Nếu máy của bạn cho ra `Errors: 1` vì context hoặc database không khởi động, **chưa** thể kết luận lỗi lệch số lượng; xử lý lỗi môi trường đó trước và tái hiện lại đúng case. Không tuyên bố đã chạy thành công chỉ dựa trên output minh họa.

## 6. Đọc failure report theo thứ tự để không chữa nhầm lỗi

Trong `target/surefire-reports`, file `TEST-com.example.shop.inventory.ReservationOnOrderPlacedTest.xml` (tên có thể khác theo cấu hình) thường chứa testcase, failure type, message và stack trace. Đọc cả console và báo cáo XML; đối chiếu trường `tests`, `failures`, `errors`, `skipped` để chắc chắn **test mục tiêu thật sự được chạy**.

| Dấu hiệu trong kết quả | Hướng điều tra tiếp theo |
| --- | --- |
| `expected: 3, actual: 2` sau khi tìm thấy entity | Oracle đã chạy; truy dữ liệu trong listener hoặc phép biến đổi `quantity` |
| Hết thời gian chờ `Scenario` | Kiểm tra bean listener, phase `AFTER_COMMIT`, transaction và repository trước khi xét payload |
| `Failed to load ApplicationContext` | Kiểm tra dependency, component scan, datasource và cấu hình module; chưa phải failure của assertion |
| `Tests run: 0` hoặc test bị `skipped` | Kiểm tra discovery của JUnit/Surefire, annotation và tham số chạy; không được ghi là test xanh |

Với case bài này, tập trung vào dòng thất bại của `savesExactQuantity` và assertion `saved.getQuantity() == event.quantity()`. Phần lớn stack trace framework có thể lược khi viết tóm tắt, nhưng cần giữ đường dẫn tới log đầy đủ để người khác có thể mở rộng.

## 7. Lần dấu vết từ đầu vào đến trạng thái database

Đi ngược từ **giá trị sai** thay vì đoán theo tên test. Lập bảng đối chiếu các điểm quan sát cho cùng một `orderId`:

| Điểm quan sát | Giá trị mong đợi | Giá trị ở mã có lỗi | Ý nghĩa |
| --- | --- | --- | --- |
| Test tạo `new OrderPlaced(id, 3)` | `3` | `3` | Fixture đúng |
| `publishEvent(event)` trong transaction đã commit | Event mang `3` | Event mang `3` | Kích thích đúng đầu vào |
| Listener `on(OrderPlaced)` | Truyền `3` xuống repository | Tính `3 - 1` | Vị trí biến đổi sai |
| `Reservation` đọc từ database | `quantity=3` | `quantity=2` | Assertion phát hiện sai lệch |

Thứ tự kiểm tra thực tế: xác nhận `orderId` của entity bằng ID từ test; nếu có bản ghi, kiểm tra `getQuantity()`; sau đó xem dòng tạo `new Reservation(...)` trong listener. Có thể đặt breakpoint vào `on(...)` hoặc bật log SQL theo cấu hình test để xác nhận truy vấn. Log SQL là bằng chứng bổ sung, **không thay thế** assertion so sánh giá trị nghiệp vụ.

**Kết luận chẩn đoán của bài:** `@ApplicationModuleListener` đã tạo được bản ghi cho đúng đơn hàng, nhưng phép `event.quantity() - 1` làm sai hợp đồng truyền nguyên số lượng. Lỗi nằm ở logic mapping của listener `inventory`; không có bằng chứng cho thấy `ApplicationModules.verify()` hay bộ đếm coverage là nguyên nhân. Đừng sửa cấu hình transaction hoặc tăng timeout khi test đã quan sát được bản ghi với sai giá trị.

## 8. Viết report ngắn, có thể kiểm chứng và tái hiện

Một report tốt trả lời đủ bốn câu hỏi: **điều gì sai, bằng chứng ở đâu, vì sao sai và đã kiểm tra bản sửa thế nào**. Mẫu sau chứa các giá trị minh họa của case; điền thông tin phiên bản/commit/đường dẫn thực tế sau khi chạy:

```markdown
# Test Failure Report — ReservationOnOrderPlacedTest.savesExactQuantity

- Trạng thái: FAIL trước sửa; PASS sau sửa (chỉ ghi PASS khi đã chạy lại).
- Môi trường: Java <version>; Spring Boot <version>; Spring Modulith <version>.
- Revision: <git-commit>; thời điểm chạy: <timestamp>; OS: <os>.
- Lệnh tái hiện: ./mvnw -Dtest=ReservationOnOrderPlacedTest test
- Artifact: target/surefire-reports/TEST-...ReservationOnOrderPlacedTest.xml

## Yêu cầu và triệu chứng
OrderPlaced(orderId=<uuid>, quantity=3) phải tạo Reservation.quantity=3.
Ví dụ lỗi được cài: assertion expected=3, actual=2; 1 failed test.

## Bằng chứng và nguyên nhân
- Fixture phát event quantity=3 trong transaction đã commit.
- Scenario tìm thấy Reservation của cùng orderId.
- Listener tạo Reservation(event.orderId(), event.quantity() - 1).
- Root cause: mapping quantity bị trừ 1 trước khi persist.

## Sửa và xác minh
- Fix: dùng event.quantity() nguyên vẹn khi tạo Reservation.
- Targeted test: <command, actual tests/failures/errors/skipped>.
- Full suite/architecture gate: <command, actual outcome>.
- Phạm vi chưa kiểm chứng: <nếu có, ghi rõ>.
```

Các trường `<...>` là chỗ cần điền bằng dữ liệu quan sát được, không tự suy diễn. Gắn stack trace gọn ở phần bằng chứng và giữ report đầy đủ trong artifact CI; không chép thông tin nhạy cảm từ database hay token vào báo cáo.

## 9. Sửa nguyên nhân tối thiểu và chạy xác minh

Chỉ thay **một biểu thức** trong `ReserveOnOrderPlaced`:

```diff
 @ApplicationModuleListener
 public void on(OrderPlaced event) {
-    reservations.save(new Reservation(event.orderId(), event.quantity() - 1));
+    reservations.save(new Reservation(event.orderId(), event.quantity()));
 }
```

Chạy lại lệnh mục 5 trên code đã sửa và đọc số liệu thực tế của Surefire. Trong bài lab này, kết quả cần đạt là `savesExactQuantity` **PASS**, một bản ghi đúng `orderId`, `quantity=3`, không có failures/errors; không chấp nhận “PASS” nếu test không được discover. Sau đó chạy toàn bộ JUnit theo cấu hình dự án, ví dụ `./mvnw -B verify`, và bảo đảm gate kiến trúc cũng chạy:

```java
@Test
void moduleBoundariesRemainValid() {
    ApplicationModules.of(ShopApplication.class).verify();
}
```

Phần test kiến trúc trên cần đặt trong class JUnit được Surefire/Failsafe phát hiện và thêm import của `ApplicationModules` cùng `ShopApplication`. `verify()` kiểm tra phụ thuộc giữa các module; nó không thay thế assertion trên dữ liệu `Reservation`. Khi đưa vào CI, cấu hình báo cáo kiểm thử như một artifact và làm build thất bại khi có test đỏ; với test tích hợp đặt tên `*IT` phải có Failsafe hoặc runner tương ứng.

## 10. Checklist nghiệm thu và bài tập mở rộng có kiểm soát

Chỉ kết thúc dự án thực hành khi đã tự xác nhận:

- [ ] Test `savesExactQuantity` thực sự được runner chạy; đã ghi số test/failure/error/skipped.
- [ ] Lưu command, môi trường, revision, timestamp và đường dẫn báo cáo XML/console.
- [ ] Phân biệt lỗi assertion `expected 3/actual 2` với lỗi timeout, không tải được context hay test bị skip.
- [ ] Chỉ ra được một dòng mã nguồn tạo sai giá trị; có bằng chứng xuyên từ event đến entity.
- [ ] Report nêu yêu cầu, cách tái hiện, triệu chứng, nguyên nhân, thay đổi tối thiểu và kết quả **thực chạy** sau sửa.
- [ ] Test đọc được dữ liệu từ repository thật và kiểm tra cả `orderId`, `quantity`.
- [ ] Chạy lại test mục tiêu và full suite/quality gate, hoặc ghi rõ phần nào chưa chạy cùng lý do.
- [ ] Hoàn nguyên mọi lỗi cố ý khác; không giữ cấu hình debug hay dữ liệu thử trong môi trường dùng chung.

**Bài tập nối tiếp (vẫn dùng cùng test):** tạm xóa annotation `@ApplicationModuleListener`, chạy lại và so sánh báo cáo *timeout* với báo cáo *assertion mismatch*. Hoàn nguyên annotation rồi tạm cho publisher phát event trong transaction rollback; mô tả vì sao listener `AFTER_COMMIT` không tạo reservation. Cuối cùng khôi phục transaction commit và bản sửa đúng, chạy lại để có kết quả PASS. Mỗi lần thay đổi chỉ một yếu tố; report phải nêu bằng chứng riêng cho kiểu thất bại mới, tránh dùng lại kết luận “mapping sai” khi dấu hiệu không còn khớp.

**Sản phẩm cuối:** một report dựa trên log thực tế, xác định được nguyên nhân gốc của **một** JUnit failure và một bản sửa nhỏ làm test đỏ chuyển xanh sau khi chạy lại. Đó là quy trình truy nguyên hồi quy có thể áp dụng cho test sự kiện, database và ranh giới module của Spring Modulith.
