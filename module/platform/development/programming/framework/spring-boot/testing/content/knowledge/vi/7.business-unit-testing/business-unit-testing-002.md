# Giả lập repository và kiểm chứng quy tắc nghiệp vụ trong unit test Spring Boot

## 1. Mục tiêu: kiểm tra nghiệp vụ mà không phụ thuộc cơ sở dữ liệu

Trong ứng dụng Spring Boot, một service thường nhận dữ liệu đầu vào, kiểm tra điều kiện nghiệp vụ, đọc dữ liệu qua repository, tính toán kết quả và yêu cầu repository lưu thay đổi. Nếu mọi bài test service đều cần khởi động Spring context và database, việc chạy test trở nên chậm, phụ thuộc môi trường và khó xác định nguyên nhân khi thất bại.

**Mock repository** là một đối tượng giả do thư viện như Mockito tạo ra để thay cho repository thực ở ranh giới của service. Ta có thể quy định repository giả trả dữ liệu nào (`stubbing`), thực thi service **thật** và xác minh service đã:

1. Lấy đúng dữ liệu cần cho quyết định nghiệp vụ.
2. Áp dụng đúng các quy tắc, ngưỡng và nhánh ngoại lệ.
3. Tạo đúng đối tượng cần lưu hoặc gửi sang phụ thuộc.
4. Chỉ gọi repository ở những trường hợp được phép; không lưu gì khi đầu vào không hợp lệ.
5. Trả về giá trị hoặc ném ngoại lệ đúng theo hợp đồng.

Ví dụ: hóa đơn của khách hàng **VIP**, còn hoạt động, được giảm 10% khi tổng tiền gốc **từ 500.000 đồng trở lên**. Khách hàng thường không được giảm. Khách bị khóa hoặc không tồn tại phải bị từ chối và **không tạo hóa đơn**.

Unit test có thể kiểm tra đầy đủ các quyết định trên bằng `Mockito.mock`, `@Mock`, `when(...).thenReturn(...)`, `verify(...)` và `ArgumentCaptor`, mà không cần database thật.

**Ranh giới cần nhớ:** Nếu `verify(invoiceRepository).save(invoice)` đạt, điều đó chứng minh service **đã yêu cầu lưu** đối tượng trên mock, chưa chứng minh SQL đúng, transaction commit, entity mapping hợp lệ hay bản ghi thực sự tồn tại trong database.

## 2. Phân biệt các vai trò trước khi viết test

| Thành phần | Vai trò trong bài test | Nên dùng thật hay giả? |
|---|---|---|
| `InvoiceService` | Chứa nhánh logic cần kiểm chứng (SUT: system under test) | **Thật** |
| `CustomerRepository` | Cung cấp dữ liệu khách hàng cho service | Mock, trả `Optional<Customer>` theo từng tình huống |
| `InvoiceRepository` | Nhận yêu cầu lưu hóa đơn | Mock, kiểm tra dữ liệu được chuyển vào `save` |
| `Customer`, `Invoice`, enum `CustomerTier` | Dữ liệu/giá trị của nghiệp vụ | **Thật**, tạo fixture rõ ràng |
| JUnit Jupiter | Chạy test và assert kết quả | Framework kiểm thử |
| Mockito | Tạo mock, stub và xác minh tương tác | Framework hỗ trợ |
| Spring ApplicationContext / database | Hạ tầng cần cho integration test | Không cần cho unit test minh họa |

Repository trong sản phẩm thật có thể là một interface kế thừa `JpaRepository`, `CrudRepository` hoặc cổng lưu trữ riêng. Trong unit test, điều cần giữ là **hợp đồng mà service sử dụng**: phương thức đọc trả dữ liệu hoặc không tìm thấy, phương thức ghi nhận entity sẽ lưu. Mockito không yêu cầu repository thật phải kết nối tới database để tạo mock.

Không mock chính `InvoiceService`: làm vậy chỉ kiểm tra hành vi được lập trình trong mock, bỏ qua nhánh nghiệp vụ đang muốn bảo vệ.

## 3. Xác định hợp đồng nghiệp vụ và các ca cần test

Giả sử ứng dụng quản lý hóa đơn có quy tắc sau:

- `customerId` phải dương và `subtotal` phải lớn hơn 0.
- Khách hàng phải tồn tại trong repository.
- Khách hàng phải đang hoạt động (`active == true`).
- Chỉ khách có `tier == VIP` và `subtotal >= 500_000` mới được giảm 10% giá trị `subtotal`.
- Khách `REGULAR` không được giảm, kể cả khi tổng tiền đạt ngưỡng.
- `payable = subtotal - discount`.
- Với yêu cầu hợp lệ, service tạo một `Invoice`, gọi `invoiceRepository.save(invoice)` đúng một lần và trả về kết quả lưu.
- Với yêu cầu không hợp lệ, không tìm thấy khách hoặc khách bị khóa, service không gọi repository lưu hóa đơn.

Bảng ca kiểm thử:

| Tình huống | Dữ liệu repository giả | Kết quả mong đợi | Tương tác cần kiểm tra |
|---|---|---|---|
| VIP đúng ngưỡng 500.000 | Khách tồn tại, `active=true`, `VIP` | Giảm 50.000; phải trả 450.000 | Gọi `findById`, lưu đúng `Invoice` một lần |
| VIP dưới ngưỡng 499.999 | Khách VIP hoạt động | Không giảm; phải trả 499.999 | Lưu hóa đơn không giảm |
| REGULAR 800.000 | Khách thường hoạt động | Không giảm; phải trả 800.000 | Lưu hóa đơn đúng |
| Khách không tồn tại | `Optional.empty()` | Ngoại lệ không tìm thấy | Không gọi `save` |
| Khách bị khóa | Khách tồn tại nhưng `active=false` | Ngoại lệ trạng thái | Không gọi `save` |
| ID không hợp lệ hoặc subtotal không dương | Không cần truy vấn | `IllegalArgumentException` | Không tương tác với cả hai repository |

Một test chỉ kiểm tra phép tính tiền mà bỏ qua `save` sẽ không phát hiện việc service tạo hóa đơn với dữ liệu khác rồi lưu sai. Ngược lại, chỉ `verify(save(any()))` không chứng minh số tiền giảm đúng. Cần kết hợp **assertion giá trị nghiệp vụ** và **verification ở ranh giới repository**.

## 4. Ví dụ Java 17+ hoàn chỉnh: service thật, repository mock

Các tệp sau đặt trong một dự án Spring Boot sử dụng Java 17+ và dependency test gồm JUnit Jupiter, Mockito, Mockito JUnit Jupiter extension (thường có qua `spring-boot-starter-test`). Ví dụ tập trung vào unit test nên không khởi động Spring, JPA hay database.

### 4.1. Mã nghiệp vụ

Tệp: `src/main/java/com/example/testing/InvoiceService.java`.

Các enum, record và interface không khai báo `public` được đặt chung tệp để ví dụ có thể biên dịch ngay với một tệp production; trong ứng dụng thực tế có thể tách chúng thành những tệp riêng.

```java
package com.example.testing;

import java.util.NoSuchElementException;
import java.util.Optional;

enum CustomerTier {
    REGULAR, VIP
}

record Customer(long id, boolean active, CustomerTier tier) {}

record Invoice(
        long customerId,
        int subtotal,
        int discount,
        int payable) {}

interface CustomerRepository {
    Optional<Customer> findById(long customerId);
}

interface InvoiceRepository {
    Invoice save(Invoice invoice);
}

public final class InvoiceService {
    private final CustomerRepository customers;
    private final InvoiceRepository invoices;

    public InvoiceService(
            CustomerRepository customers,
            InvoiceRepository invoices) {
        this.customers = customers;
        this.invoices = invoices;
    }

    public Invoice issue(long customerId, int subtotal) {
        if (customerId <= 0 || subtotal <= 0) {
            throw new IllegalArgumentException("Invalid invoice input");
        }

        Customer customer = customers.findById(customerId)
                .orElseThrow(() ->
                        new NoSuchElementException("Customer not found"));

        if (!customer.active()) {
            throw new IllegalStateException("Customer inactive");
        }

        int discount = customer.tier() == CustomerTier.VIP
                && subtotal >= 500_000
                ? subtotal / 10
                : 0;

        Invoice invoice = new Invoice(
                customerId,
                subtotal,
                discount,
                subtotal - discount);

        return invoices.save(invoice);
    }
}
```

Giải thích các quyết định quan trọng:

- Dữ liệu đầu vào được kiểm tra **trước** khi gọi repository. Vì vậy, trường hợp `subtotal <= 0` phải không có tương tác dữ liệu.
- `findById` trả `Optional<Customer>`. `Optional.empty()` được chuyển thành ngoại lệ nghiệp vụ của ví dụ; không gọi `get()` khi chưa biết có giá trị.
- Khách bị khóa bị chặn trước khi gọi `save`.
- Ngưỡng dùng `>= 500_000`, nên trường hợp **đúng 500.000** được giảm.
- `Invoice` là Java record: `equals` so giá trị từng component, tiện dùng trong assertion.
- `issue` trả chính giá trị repository `save` trả về. Trong unit test, ta phải cấu hình câu trả lời này nếu muốn một `Invoice` thay cho giá trị mặc định của mock.

Ví dụ dùng `int` như đơn vị đồng nguyên để tập trung vào phép thử, chiết khấu chia nguyên (`subtotal / 10`). Với hệ thống có tiền lẻ, nhiều loại tiền hoặc quy tắc làm tròn khác, nên dùng kiểu tiền tệ/`BigDecimal` và kiểm thử chính sách làm tròn riêng. Không suy rộng công thức mẫu thành quy tắc kế toán chung.

### 4.2. Test sử dụng @Mock và MockitoExtension

Tệp: `src/test/java/com/example/testing/InvoiceServiceTest.java`.

```java
package com.example.testing;

import java.util.NoSuchElementException;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class InvoiceServiceTest {

    @Mock
    CustomerRepository customers;

    @Mock
    InvoiceRepository invoices;

    private InvoiceService service;

    @BeforeEach
    void setUp() {
        service = new InvoiceService(customers, invoices);
    }

    @Test
    void vipAtThresholdGetsDiscountAndIsSavedOnce() {
        when(customers.findById(7L)).thenReturn(Optional.of(
                new Customer(7L, true, CustomerTier.VIP)));

        when(invoices.save(any(Invoice.class)))
                .thenAnswer(call -> call.getArgument(0));

        Invoice result = service.issue(7L, 500_000);

        assertAll("VIP at exact threshold",
                () -> assertEquals(7L, result.customerId()),
                () -> assertEquals(500_000, result.subtotal()),
                () -> assertEquals(50_000, result.discount()),
                () -> assertEquals(450_000, result.payable()));

        ArgumentCaptor<Invoice> captor =
                ArgumentCaptor.forClass(Invoice.class);

        verify(customers).findById(7L);
        verify(invoices, times(1)).save(captor.capture());

        Invoice saved = captor.getValue();
        assertEquals(result, saved);
        verifyNoMoreInteractions(customers, invoices);
    }

    @Test
    void vipBelowThresholdGetsNoDiscount() {
        when(customers.findById(7L)).thenReturn(Optional.of(
                new Customer(7L, true, CustomerTier.VIP)));

        when(invoices.save(any(Invoice.class)))
                .thenAnswer(call -> call.getArgument(0));

        Invoice result = service.issue(7L, 499_999);

        assertEquals(0, result.discount());
        assertEquals(499_999, result.payable());

        verify(invoices).save(
                new Invoice(7L, 499_999, 0, 499_999));
    }

    @Test
    void regularCustomerGetsNoVipDiscount() {
        when(customers.findById(9L)).thenReturn(Optional.of(
                new Customer(9L, true, CustomerTier.REGULAR)));

        when(invoices.save(any(Invoice.class)))
                .thenAnswer(call -> call.getArgument(0));

        Invoice result = service.issue(9L, 800_000);

        assertEquals(0, result.discount());
        assertEquals(800_000, result.payable());
        verify(invoices).save(
                new Invoice(9L, 800_000, 0, 800_000));
    }

    @Test
    void missingCustomerNeverSavesInvoice() {
        when(customers.findById(20L))
                .thenReturn(Optional.empty());

        assertThrows(NoSuchElementException.class,
                () -> service.issue(20L, 500_000));

        verify(customers).findById(20L);
        verifyNoInteractions(invoices);
    }

    @Test
    void inactiveCustomerNeverSavesInvoice() {
        when(customers.findById(11L)).thenReturn(Optional.of(
                new Customer(11L, false, CustomerTier.VIP)));

        assertThrows(IllegalStateException.class,
                () -> service.issue(11L, 500_000));

        verify(customers).findById(11L);
        verifyNoInteractions(invoices);
    }

    @Test
    void invalidInputDoesNotAccessRepositories() {
        assertThrows(IllegalArgumentException.class,
                () -> service.issue(0L, 500_000));

        assertThrows(IllegalArgumentException.class,
                () -> service.issue(7L, 0));

        verifyNoInteractions(customers, invoices);
    }
}
```

**Điểm cần hiểu trong code:**

- `@ExtendWith(MockitoExtension.class)` khởi tạo các trường `@Mock` trước từng test, tích hợp vòng đời JUnit Jupiter và hỗ trợ phát hiện stubbing không cần thiết.
- `@BeforeEach` tạo **service thật** với hai mock; không dùng Spring `@Autowired` hay `@SpringBootTest` chỉ để kiểm tra phép tính.
- `when(customers.findById(7L)).thenReturn(Optional.of(...))` tạo đầu vào có kiểm soát cho nhánh VIP.
- `when(invoices.save(any(Invoice.class))).thenAnswer(call -> call.getArgument(0))` làm mock trả chính đối tượng được truyền vào. Điều này mô phỏng **hợp đồng test lựa chọn**, không mô phỏng việc database thực tự cấp ID hoặc commit.
- `ArgumentCaptor` cho phép đọc `Invoice` mà service yêu cầu lưu và đối chiếu với giá trị trả về; `verify(..., times(1))` xác minh số lần ghi.
- Các trường hợp lỗi **không stub save**, vì hành vi đúng yêu cầu service không gọi save; `verifyNoInteractions(invoices)` sẽ đỏ nếu service vi phạm.
- `verifyNoMoreInteractions` trong ca đầu tiên có chủ đích bảo vệ rằng không có lời gọi bổ sung; đừng lạm dụng trong test chỉ cần kiểm chứng kết quả nghiệp vụ, vì nó có thể khiến test giòn theo cách tổ chức nội bộ.

Với cấu hình đã nêu, **sáu test được thiết kế để đạt**. Không có đoạn `stdout` từ phương thức production hay test; Maven/Gradle cung cấp log và báo cáo theo phiên bản runner, nên không dự đoán nguyên văn log của dự án thực tế. Test được chạy trên service minh họa, không phải một ứng dụng Spring Boot được khởi tạo hoàn chỉnh.

### 4.3. Chạy bài test

Với Gradle wrapper trên Linux/macOS:

```bash
./gradlew test --tests "com.example.testing.InvoiceServiceTest"
```

Với Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.InvoiceServiceTest"
```

Với Maven wrapper trên Linux/macOS:

```bash
./mvnw -Dtest=InvoiceServiceTest test
```

Với Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=InvoiceServiceTest test
```

Điều kiện: dự án cấu hình JUnit Platform/Surefire tương thích với JUnit Jupiter; trong Gradle thường có `useJUnitPlatform()`. Sau khi chạy, xem báo cáo thực tế (`build/reports/tests/test/index.html` với Gradle task `test`, hoặc `target/surefire-reports/` với Maven Surefire). Chỉ ghi nhận `PASS` cho dự án khi đã thấy test được khám phá và thực thi thành công; một build xanh mà task test bị skip/cache chưa xác nhận chạy mới.

## 5. Ba dạng kiểm chứng phải kết hợp hợp lý

### 5.1. Kiểm chứng kết quả nghiệp vụ bằng assertion

Ví dụ:

```java
assertEquals(50_000, result.discount());
assertEquals(450_000, result.payable());
```

Đây là kiểm tra **đầu ra** của quy tắc VIP. Tên test nên mô tả bối cảnh và kỳ vọng, như `vipAtThresholdGetsDiscountAndIsSavedOnce`. Với quy tắc có ngưỡng, nên có test **dưới ngưỡng, đúng ngưỡng và trên ngưỡng** khi sự khác biệt có nguy cơ gây lỗi. Trong ví dụ, ca đúng 500.000 và dưới 499.999 đã bảo vệ lỗi `>` với `>=`; có thể thêm ca trên ngưỡng như 500.001 hoặc số lớn hơn nếu quy tắc tiền và làm tròn cần xác minh sâu hơn.

### 5.2. Kiểm chứng lời gọi repository bằng verify

```java
verify(customers).findById(7L);
verify(invoices, times(1)).save(any(Invoice.class));
```

`verify` xác minh lời gọi trên mock; mặc định `verify(mock)` mong đúng một lời gọi khớp. Nếu yêu cầu là không ghi dữ liệu khi khách bị khóa, `verifyNoInteractions(invoices)` diễn đạt hợp đồng rõ hơn việc chỉ kiểm tra exception.

Tuy nhiên, chỉ `save(any(Invoice.class))` sẽ không phát hiện một invoice có `payable` hoặc `customerId` sai. Khi cần kiểm tra dữ liệu được gửi đi, dùng đối tượng mong đợi có `equals` chuẩn hoặc `ArgumentCaptor`.

### 5.3. Kiểm chứng dữ liệu gửi đi bằng ArgumentCaptor

```java
ArgumentCaptor<Invoice> captor =
        ArgumentCaptor.forClass(Invoice.class);

verify(invoices).save(captor.capture());

Invoice saved = captor.getValue();
assertEquals(450_000, saved.payable());
assertEquals(50_000, saved.discount());
```

Captor đọc argument mà mock nhận. Nó không tự chứng minh trạng thái đã commit trong database, cũng không tự tạo snapshot sâu của một entity mutable tại thời điểm `save`. Nếu service tiếp tục sửa cùng object sau khi gọi mock, trạng thái captor đọc sau đó có thể đã đổi. Với bài test cần biết trạng thái **ngay tại thời điểm gọi**, ưu tiên value object bất biến hoặc dùng `doAnswer` để chụp snapshot những trường quan trọng tại invocation.

Cân nhắc giữa kiểm tra đầu ra và kiểm tra tương tác: không nên xác minh mọi phương thức helper nội bộ chỉ vì có thể dùng Mockito; chỉ xác minh những tương tác **thuộc hợp đồng nghiệp vụ**, chẳng hạn phải lưu đúng một hóa đơn hoặc không được lưu trong nhánh từ chối.

## 6. Stubbing repository đúng cách

### 6.1. Định nghĩa dữ liệu đầu vào cho từng test

`Optional.empty()` là dữ liệu có ý nghĩa: khách không tồn tại. Hãy stub rõ ràng:

```java
when(customers.findById(20L)).thenReturn(Optional.empty());
```

Không nên dựa vào giá trị mặc định của Mockito rồi xem như đó là tình huống nghiệp vụ được mô phỏng rõ ràng. Mock thường trả giá trị mặc định (`null`, 0, `false` hoặc giá trị rỗng tùy kiểu/thư viện), nên một test không stub `save` có thể khiến `issue` trả `null` và gây lỗi không liên quan đến quy tắc đang kiểm tra.

`thenReturn` phù hợp khi kết quả cố định. `thenAnswer` phù hợp khi kết quả phụ thuộc argument:

```java
when(invoices.save(any(Invoice.class)))
        .thenAnswer(call -> call.getArgument(0));
```

Đây là **một lựa chọn mô phỏng đơn giản** cho ví dụ có repository trả entity đã lưu. Repository thật có thể bổ sung ID, version, timestamp hoặc biến đổi entity; muốn chứng minh những hành vi đó, phải dùng test tích hợp hoặc một hợp đồng stub chính xác hơn.

### 6.2. Đừng stub quá rộng hoặc quá nhiều

Viết `when(customers.findById(anyLong()))...` cho mọi test có thể che bug service gọi **sai customerId**. Nếu ID đầu vào quan trọng, stub và verify đúng `7L`, `9L`, `20L` như ví dụ. Mọi stubbing không được dùng nên được loại bỏ; MockitoExtension có thể cảnh báo `UnnecessaryStubbingException` trong cấu hình strict stubs. Thay vì dùng `lenient()` đại trà, đặt stub chỉ ở những test thật sự cần.

Không cần stub `invoices.save` trong các ca phải bị chặn trước lưu. Nếu stub ở `@BeforeEach` cho mọi test, ca invalid/missing có thể làm phát sinh cảnh báo unused stubbing dù service đang đúng.

### 6.3. Mockito matcher phải nhất quán

Khi một phương thức có nhiều tham số và một tham số dùng matcher, các tham số còn lại cũng phải dùng matcher phù hợp như `eq(...)`, `any(...)`. Không trộn literal thô với matcher trong cùng một invocation Mockito vì có thể gây `InvalidUseOfMatchersException`.

Ví dụ minh họa với một interface giả định:

```java
verify(auditClient).record(
        eq("INVOICE_CREATED"),
        any(Invoice.class));
```

Đoạn trên chỉ minh họa cú pháp matcher trong một test đã khai báo `auditClient` và import `eq`/`any`, **không phải tệp Java độc lập**. Khi một field cần giá trị chính xác hơn `any()`, hãy dùng `eq(expected)`, `argThat` hoặc captor.

### 6.4. Các ngoại lệ do repository gây ra

Unit test cũng có thể mô phỏng lỗi phụ thuộc, ví dụ:

```java
when(invoices.save(any(Invoice.class)))
        .thenThrow(new IllegalStateException("storage unavailable"));
```

Nếu hợp đồng service yêu cầu chuyển đổi ngoại lệ hạ tầng thành lỗi nghiệp vụ, test phải gọi service và assert **đúng ngoại lệ được chuyển đổi**. Nếu service có chủ đích để ngoại lệ lan ra, test cũng có thể kiểm tra điều đó. Đừng tự suy ra service luôn phải catch exception; cách xử lý phụ thuộc hợp đồng giao dịch và kiến trúc của module.

Các đoạn mã riêng trong mục 5–6 chỉ minh họa các câu lệnh trong ngữ cảnh test đã khai báo mock/import cần thiết. Chương trình hoàn chỉnh có thể chạy nằm ở mục 4.

## 7. Không nhầm unit test repository mock với integration test của repository

Đây là ranh giới quan trọng trong Spring Boot:

| Câu hỏi | Unit test service với repository mock | Integration/repository test |
|---|---|---|
| Quy tắc giảm giá VIP được áp dụng đúng? | **Có**, dùng fixture và assertion | Có thể kiểm tra nhưng thường không cần cho phép tính thuần túy |
| Service có gọi `save` với hóa đơn đúng? | **Có**, qua `verify`/captor | Có thể quan sát dữ liệu lưu |
| Query JPA `findById` có trả đúng dữ liệu từ DB? | **Không**: đã stub kết quả | **Có**, với database/test configuration |
| Entity mapping, schema constraint, unique key có đúng? | **Không** | Kiểm tra bằng `@DataJpaTest`/test tích hợp phù hợp |
| Transaction có commit/rollback như production không? | **Không** | Cần test transaction/DB có ý nghĩa |
| Nhiều request cùng tạo hóa đơn có gây race condition không? | **Không** | Cần kiểm thử concurrent/integration với invariant phù hợp |
| Controller nhận JSON, validation, HTTP status có đúng? | **Không** | Cần web/API test tương ứng |

Trong Spring Boot, `@DataJpaTest` thường là lựa chọn phù hợp để tập trung vào repository/JPA. Với lỗi phụ thuộc hệ quản trị dữ liệu thật, nên cân nhắc Testcontainers và database giống production. `@SpringBootTest` nạp bối cảnh ứng dụng phù hợp cho test nhiều thành phần phối hợp, nhưng tốn thời gian hơn unit test thuần Java. Một `@SpringBootTest` mặc định không có nghĩa server HTTP thực đã được khởi động.

Để kiểm tra service trong Spring context bằng mock bean, phải dùng cơ chế thay thế bean phù hợp **phiên bản Spring Boot/Spring Framework**; ví dụ `@MockitoBean` được hỗ trợ trong các phiên bản tương ứng. Một trường `@Mock` độc lập bên ngoài context không tự động thay bean mà Spring đang inject. Nếu code đang kiểm tra chỉ là quy tắc nghiệp vụ, cách tạo service trực tiếp với mock thường rõ ràng và ít chi phí hơn.

## 8. Lỗi phổ biến khi giả lập repository

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Mock chính service chứa nghiệp vụ | Bỏ qua logic cần test | Tạo service thật, mock dependency của nó |
| Chỉ `verify(save(any()))` | Không phát hiện tiền/ID/field bị lưu sai | Assert data bằng `eq`, record `equals` hoặc captor |
| Chỉ assert tiền trả về | Có thể lưu entity sai hoặc lưu hai lần | Kiểm tra lời gọi `save` khi thuộc hợp đồng |
| Quên stub `save` nhưng assert giá trị trả về từ `save` | Mock có thể trả `null` | Stub kết quả phù hợp hoặc chỉ assert dữ liệu đã capture |
| Dùng `anyLong()` để stub mọi ID | Có thể bỏ qua lỗi truy vấn sai khách | Stub và verify đúng ID |
| Stub save cho mọi test ở setup | Nhánh lỗi không dùng stub, khó duy trì | Stub trong từng ca cần save |
| Bỏ qua `Optional.empty()` | Nhánh không tìm thấy chưa được bảo vệ | Thêm test missing customer và không lưu |
| Chỉ kiểm tra exception, không kiểm tra side effect | Service có thể lưu trước rồi mới ném lỗi | `verifyNoInteractions(invoices)` khi yêu cầu không ghi |
| Mock object dữ liệu như `Customer`, `Invoice` | Test mô phỏng quá nhiều và khó hiểu | Dùng giá trị/record thật |
| Cho rằng mock save chứng minh database commit | Đánh giá quá mức bằng chứng | Thêm integration test với DB thật phù hợp |
| Xác minh mọi lần gọi helper | Test giòn khi refactor hợp lệ | Verify interaction là phần của hợp đồng |
| Không test đúng ngưỡng | Dễ lọt bug `>` thay vì `>=` | Test dưới, đúng và khi cần trên ngưỡng |

## 9. Cách tổ chức test có giá trị lâu dài

**Đặt tên theo hành vi**, không theo tên hàm chung chung. `vipAtThresholdGetsDiscountAndIsSavedOnce` mô tả đầu vào, điều kiện và kết quả, dễ đọc hơn `testIssue1`.

**Mỗi test tự chuẩn bị dữ liệu tối thiểu.** Khi dùng `MockitoExtension`, mỗi test có mock riêng theo vòng đời test, giảm phụ thuộc thứ tự chạy. Không dùng repository mock toàn cục dùng chung giữa các ca trừ khi đã quản lý reset và trạng thái một cách có chủ đích.

**Kiểm tra nhánh sai quan trọng như nhánh thành công.** Service tạo hóa đơn trong trường hợp khách không hoạt động có thể gây sai lệch dữ liệu; `verifyNoInteractions` làm hợp đồng “không ghi” trở nên có thể kiểm chứng.

**Tách kiểm tra logic khỏi tích hợp thật.** Unit test nên chạy nhanh, quyết định được bằng fixture. Test repository thật nên tập trung query, mapping, constraint và transaction. Web test tập trung status/body/validation. Nhiều tầng test bổ sung cho nhau và giảm việc một test lớn hỏng vì quá nhiều lý do.

**Tránh dữ liệu ngẫu nhiên không kiểm soát.** Nếu service dùng thời gian, inject `Clock` vào service; nếu sinh UUID và contract đòi ID xác định, cân nhắc inject nguồn ID hoặc đối chiếu với dữ liệu được capture thay vì đoán UUID. Nếu có tỷ giá hoặc cấu hình chính sách, đưa chúng thành input rõ ràng cho test.

## 10. Checklist trước khi kết luận service đạt yêu cầu

- [ ] Service đang kiểm thử là instance thật; repository là đúng mock được truyền vào.
- [ ] Mỗi `when(...)` trả dữ liệu có chủ đích để kích hoạt một nhánh nghiệp vụ cụ thể.
- [ ] Có assertion cho đầu ra quan trọng: discount, payable, ngoại lệ và ranh giới giá trị.
- [ ] Có verification cho tương tác cần thiết: truy vấn đúng khách, lưu đúng hóa đơn, đúng số lần.
- [ ] Có kiểm tra **không lưu** với input sai, khách không tồn tại hoặc bị khóa.
- [ ] Dữ liệu gửi vào `save` được kiểm tra đầy đủ; không chỉ `any()`.
- [ ] Không dựa vào hành vi mock như bằng chứng database thật đã commit.
- [ ] Các test độc lập, không có stubbing thừa hoặc phụ thuộc state của ca khác.
- [ ] Có kế hoạch integration test khi rủi ro là JPA mapping, SQL, transaction hoặc hạ tầng.
- [ ] Đã chạy đúng task test và xem report của Gradle/Maven/CI trước khi tuyên bố kết quả đạt trên dự án thực tế.

**Kết luận:** Giả lập repository bằng Mockito giúp cô lập Spring Boot service để **kiểm chứng quy tắc nghiệp vụ một cách nhanh, rõ và lặp lại được**. Test tốt tạo dữ liệu repository giả theo từng tình huống, thực thi service thật, assert kết quả và verify những tương tác có ý nghĩa (đặc biệt dữ liệu được lưu và các nhánh không được lưu). Khi câu hỏi chuyển sang SQL, JPA, transaction hay database thật, hãy dùng integration test tương ứng.