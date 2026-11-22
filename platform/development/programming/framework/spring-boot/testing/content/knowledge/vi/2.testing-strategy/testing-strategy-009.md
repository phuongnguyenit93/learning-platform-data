# Đặt tên ca kiểm thử theo tình huống và kết quả

## 1. Tên ca kiểm thử là mô tả ngắn của hành vi cần chứng minh

Trong một dự án Spring Boot, tên test xuất hiện ở mã nguồn, cây kết quả JUnit, log CI và báo cáo khi kiểm thử thất bại. Một tên tốt cho phép người đọc hiểu **hệ thống đang ở tình huống nào**, **thực hiện hành động gì** và **điều gì phải xảy ra**, ngay cả trước khi mở thân hàm test.

Ví dụ:

- `test1()`: không biết đang kiểm tra chức năng nào.
- `testReserve()`: biết thao tác, nhưng không rõ tình huống và kết quả.
- `reserve_whenStockIsSufficient_decreasesStockAndReturnsTrue()`: biết thao tác `reserve`, điều kiện đủ tồn kho và kết quả mong đợi.
- `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock()`: thể hiện rõ hành vi từ chối và bảo toàn dữ liệu.

Tên test nên hoạt động như một **câu đặc tả hành vi có thể kiểm chứng**: nếu bài test thất bại, người đọc nhận ra quy tắc nào đang bị vi phạm mà không phải đoán.

Mục tiêu không phải nhét mọi câu lệnh hay mọi assertion vào tên. Hãy nêu **tình huống phân biệt ca này với ca khác** và **kết quả nghiệp vụ quan trọng nhất**. Khi cần thêm ngữ cảnh, dùng `@DisplayName`, tên nhóm `@Nested`, dữ liệu parameterized test hoặc mô tả trong tài liệu kiểm thử.

## 2. Công thức đặt tên: tình huống + hành động + kết quả

Một ca kiểm thử thường có ba thành phần: Given/Arrange (điều kiện ban đầu), When/Act (hành động), Then/Assert (kết quả mong đợi). Tên test phản ánh các thành phần đó bằng cách diễn đạt súc tích.

Hai mẫu phổ biến, đều hợp lệ:

1. **`<action>_when<Scenario>_<ExpectedResult>`** — chẳng hạn `reserve_whenQuantityExceedsStock_returnsFalse`.
2. **`should<ExpectedResult>_when<Scenario>`** — chẳng hạn `shouldRejectReservation_whenStockIsInsufficient`. Thao tác đôi khi được thể hiện qua tên lớp test hoặc ngữ cảnh.

Nếu dự án ưu tiên thứ tự Given–When–Then, có thể viết `given<Context>_when<Action>_then<Outcome>`, ví dụ `givenNoStock_whenReservingOne_thenReturnsFalse`. Mẫu này chi tiết hơn nhưng dễ thành quá dài; chỉ sử dụng khi ngữ cảnh phức tạp và giúp tăng độ rõ.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Tình huống** | Dữ liệu/trạng thái/điều kiện đặc biệt nào làm nên ca này? | `whenStockIsInsufficient` |
| **Hành động** | Phương thức, endpoint hoặc hành vi nào đang được thử? | `reserve` |
| **Kết quả mong đợi** | Hệ thống trả về, thay đổi hoặc giữ nguyên điều gì? | `returnsFalseWithoutChangingStock` |

Một tên như `reserve_whenStockIsInsufficient` mới chỉ có tình huống; thêm kết quả sẽ phân biệt rõ việc hệ thống phải từ chối, ném lỗi hay đưa vào hàng chờ. Ngược lại, `reserve_returnsFalse` thiếu tình huống nên chưa giải thích **khi nào** việc trả về `false` là đúng.

**Nguyên tắc quan trọng:** tên phải phù hợp với hợp đồng được kiểm tra bằng assertion. Nếu tên nói “không thay đổi tồn kho”, thân test cần kiểm chứng giá trị tồn kho sau thao tác; nếu tên nói “ném exception”, test phải khẳng định exception mong đợi.

## 3. Từ quy tắc nghiệp vụ đến danh sách tên test

Giả sử một service quản lý tồn kho có yêu cầu:

> Đặt trước số lượng dương. Nếu đủ hàng, hệ thống chấp nhận và trừ tồn kho; nếu thiếu hàng, hệ thống từ chối, không trừ tồn; số lượng bằng 0 hoặc âm là đầu vào không hợp lệ.

Từ quy tắc đó có thể tách các tình huống độc lập:

| ID | Tình huống trước hành động | Hành động | Kết quả mong đợi | Tên test có ý nghĩa |
| --- | --- | --- | --- | --- |
| TC-01 | Còn 5, cần đặt 2 | `reserve(2)` | Trả `true`, còn 3 | `reserve_whenStockIsSufficient_returnsTrueAndDecreasesStock` |
| TC-02 | Còn 1, cần đặt 2 | `reserve(2)` | Trả `false`, vẫn còn 1 | `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock` |
| TC-03 | Còn 2, cần đặt đúng 2 | `reserve(2)` | Trả `true`, còn 0 | `reserve_whenQuantityEqualsStock_depletesStock` |
| TC-04 | Còn 5, yêu cầu 0 | `reserve(0)` | Ném `IllegalArgumentException`, vẫn còn 5 | `reserve_whenQuantityIsZero_throwsIllegalArgumentException` |
| TC-05 | Còn 5, yêu cầu âm | `reserve(-1)` | Ném `IllegalArgumentException`, vẫn còn 5 | `reserve_whenQuantityIsNegative_throwsIllegalArgumentException` |

Mỗi tên nhấn mạnh một **điều kiện kích hoạt** và **điều phải đúng sau hành động**. Không nên dùng tên `reserve_success()` cho mọi trường hợp thành công, vì “đủ hàng thông thường” và “số lượng vừa khớp tồn kho” kiểm tra hai tình huống khác nhau, đặc biệt là ranh giới.

Khi tên quá dài, hãy chọn một kết quả tiêu biểu trong tên và giữ các assertion liên quan trong thân test; ví dụ `reserve_whenQuantityEqualsStock_depletesStock` vẫn có thể assert giá trị trả về là `true`. Chỉ yêu cầu độ cụ thể đủ để **định vị hành vi bị hỏng**.

## 4. Ví dụ đầy đủ với Java 17 và JUnit 5 trong dự án Spring Boot

Giả sử một dự án Spring Boot sử dụng Java 17+, Spring Boot Starter Test và JUnit Jupiter. Lớp service dưới đây tự chứa logic nghiệp vụ để minh họa cách đặt tên theo tình huống/kết quả. Đây là **unit test**; không cần khởi động toàn bộ Spring ApplicationContext chỉ để kiểm tra thuật toán thuần Java.

**Tệp `src/main/java/com/example/testing/StockReservationService.java`:**

~~~java
package com.example.testing;

public final class StockReservationService {
    private int availableStock;

    public StockReservationService(int initialStock) {
        if (initialStock < 0) {
            throw new IllegalArgumentException("Initial stock must be non-negative");
        }
        this.availableStock = initialStock;
    }

    public boolean reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (quantity > availableStock) {
            return false;
        }
        availableStock -= quantity;
        return true;
    }

    public int availableStock() {
        return availableStock;
    }
}
~~~

Hợp đồng của `reserve` đã được xác định rõ: số lượng không hợp lệ gây exception; thiếu hàng trả về `false`; đủ hàng trả về `true` và trừ kho. Tên các test sau dựa trên hợp đồng đó.

**Tệp `src/test/java/com/example/testing/StockReservationServiceTest.java`:**

~~~java
package com.example.testing;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StockReservationServiceTest {

    @Test
    @DisplayName("Đủ tồn kho: đặt hàng thành công và giảm số lượng còn lại")
    void reserve_whenStockIsSufficient_returnsTrueAndDecreasesStock() {
        // Given
        StockReservationService service = new StockReservationService(5);

        // When
        boolean accepted = service.reserve(2);

        // Then
        assertTrue(accepted);
        assertEquals(3, service.availableStock());
    }

    @Test
    @DisplayName("Thiếu tồn kho: từ chối đặt hàng và giữ nguyên tồn")
    void reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock() {
        StockReservationService service = new StockReservationService(1);

        boolean accepted = service.reserve(2);

        assertFalse(accepted);
        assertEquals(1, service.availableStock());
    }

    @Test
    @DisplayName("Đặt đúng số lượng còn lại: hết hàng sau khi đặt")
    void reserve_whenQuantityEqualsStock_depletesStock() {
        StockReservationService service = new StockReservationService(2);

        boolean accepted = service.reserve(2);

        assertTrue(accepted);
        assertEquals(0, service.availableStock());
    }

    @Test
    @DisplayName("Đặt số lượng bằng 0: phát sinh lỗi và không trừ tồn kho")
    void reserve_whenQuantityIsZero_throwsIllegalArgumentException() {
        StockReservationService service = new StockReservationService(5);

        assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve(0)
        );
        assertEquals(5, service.availableStock());
    }
}
~~~

Các hàm test có tên theo hành vi. Annotation `@DisplayName` bổ sung câu tiếng Việt dễ đọc trên báo cáo JUnit; tên phương thức Java vẫn giúp tìm kiếm và điều hướng trong IDE. Chẳng hạn khi test `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock` thất bại, người đọc biết ngay cần xem hành vi **thiếu hàng nhưng không được thay đổi tồn**.

Trong dự án Gradle Spring Boot có plugin và repositories đã cấu hình, bảo đảm dependency và test runner tương ứng trong `build.gradle` (cú pháp Groovy):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Từ thư mục dự án có Gradle Wrapper, chạy:

~~~bash
./gradlew test --tests "com.example.testing.StockReservationServiceTest"
~~~

Trên Windows dùng `gradlew.bat test --tests "com.example.testing.StockReservationServiceTest"`. Nếu mọi assertion đúng, Gradle báo task test thành công; nội dung log cụ thể phụ thuộc phiên bản Gradle và cấu hình dự án, nên không nên gán một chuỗi stdout cố định.

**Lưu ý về phạm vi:** ví dụ Java/JUnit trên chạy trong dự án có dependency JUnit 5 phù hợp; lệnh `javac` đơn lẻ không biên dịch lớp test nếu thiếu classpath JUnit. Service tự thân chỉ dùng Java 17. Dùng `@SpringBootTest` hoặc test slice như `@WebMvcTest` khi mục tiêu thực sự cần Spring context; cách đặt tên theo tình huống và kết quả vẫn giữ nguyên.

## 5. Đặt tên cho nhiều bộ dữ liệu bằng parameterized test

Khi **cùng một quy tắc** được kiểm tra với nhiều bộ dữ liệu, `@ParameterizedTest` giúp tránh lặp thân test. Tên phương thức diễn tả quy tắc tổng quát; tên từng lượt chạy có thể đưa giá trị đầu vào và kết luận mong đợi vào báo cáo.

Ví dụ thêm một phương thức vào lớp `StockReservationServiceTest` ở trên, với các import `org.junit.jupiter.params.ParameterizedTest` và `org.junit.jupiter.params.provider.CsvSource`:

~~~java
@ParameterizedTest(
        name = "[{index}] Tồn {0}, đặt {1}: từ chối và giữ nguyên tồn kho"
)
@CsvSource({
        "0, 1",
        "1, 2",
        "3, 4"
})
void reserve_whenRequestedQuantityExceedsStock_returnsFalseWithoutChangingStock(
        int initialStock,
        int quantity
) {
    StockReservationService service = new StockReservationService(initialStock);

    boolean accepted = service.reserve(quantity);

    assertFalse(accepted);
    assertEquals(initialStock, service.availableStock());
}
~~~

Đây là **đoạn thêm vào lớp test**, không phải tệp Java độc lập. Mỗi dòng `@CsvSource` tạo một invocation. Placeholder `{index}` là số thứ tự lượt chạy, `{0}` và `{1}` là giá trị tham số được JUnit đưa vào display name. Ví dụ một lượt có tên “Tồn 1, đặt 2: từ chối và giữ nguyên tồn kho”.

Không gom các tình huống có kết quả/ngoại lệ khác nhau vào cùng một tên mơ hồ. Trường hợp số lượng `0` ném exception là một hành vi khác với trường hợp số lượng vượt tồn trả về `false`; nên có tên test hoặc tập dữ liệu riêng.

## 6. Đặt tên cho kiểm thử HTTP và Spring Boot

Test service và test HTTP có **ranh giới quan sát khác nhau**. Tên test nên phản ánh hợp đồng mà tầng đó chịu trách nhiệm:

| Tình huống HTTP | Kết quả mong đợi | Tên gợi ý |
| --- | --- | --- |
| Yêu cầu lấy bản ghi có ID tồn tại | HTTP 200 và payload đúng | `getItem_whenIdExists_returns200WithItem` |
| ID không tồn tại | HTTP 404 | `getItem_whenIdDoesNotExist_returns404` |
| JSON body thiếu trường bắt buộc và request bị validation từ chối | HTTP 400, không tạo dữ liệu | `createItem_whenRequiredFieldIsMissing_returns400` |
| Người dùng chưa xác thực gọi tài nguyên được bảo vệ | HTTP 401 theo cấu hình bảo mật | `getProfile_whenUnauthenticated_returns401` |
| Người dùng đã xác thực nhưng thiếu quyền | HTTP 403 theo chính sách áp dụng | `deleteItem_whenPermissionIsMissing_returns403` |

Các tên trên là **mẫu gợi ý theo hợp đồng giả định**. HTTP 401/403, validation status và payload phải phù hợp với Spring Security, controller advice và yêu cầu thực tế của hệ thống; không mặc định mọi ứng dụng trả cùng mã trong mọi tình huống.

Ví dụ với MockMvc, method test có thể mang tên `getItem_whenIdDoesNotExist_returns404`; thân test phải gọi đúng endpoint trong bối cảnh ID vắng mặt và assert `status().isNotFound()`. Nếu dependency phải stub/mock, trạng thái “không tìm thấy” cần được thiết lập đúng trong Arrange. Tên test không tự tạo điều kiện ban đầu thay cho dữ liệu test.

Đối với kiểm thử tích hợp, tên nên mô tả hành vi nhìn từ bên ngoài hoặc trạng thái bền vững: `createOrder_whenRequestIsValid_persistsOrderAndReturns201`. Chỉ nêu “persists” nếu test thực sự kiểm tra trạng thái được lưu, không chỉ mock lời gọi `repository.save(...)` rồi suy ra đã lưu vào database.

## 7. Tên phương thức và tên hiển thị trong báo cáo

JUnit Jupiter hỗ trợ hai cấp mô tả:

- **Tên phương thức test:** là định danh ổn định trong mã nguồn; ví dụ `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock`. Dùng cách đặt tên nhất quán của đội, thường viết tiếng Anh và chữ ASCII để dễ tìm kiếm, lọc test và sử dụng công cụ.
- **`@DisplayName`:** là chuỗi dễ đọc khi hiển thị kết quả; có thể dùng tiếng Việt với dấu, ví dụ “Thiếu tồn kho → từ chối đặt và giữ nguyên tồn”. Nó không thay thế assertion và không biến hai test có hành vi khác nhau thành một ca.

Khi có nhiều test liên quan, `@Nested` có thể nhóm các tình huống theo chức năng hoặc ngữ cảnh; ví dụ `@DisplayName("Khi đặt hàng")` cho nhóm, các test con đặt tên “Đủ tồn kho…” hoặc “Thiếu tồn kho…”. Dù nhóm đã thể hiện hành động, tên từng ca vẫn cần **tình huống và kết quả riêng**, để khi chạy lẻ hoặc xem log vẫn hiểu lý do thất bại.

Không cần đặt cả hai tên dài y hệt nhau. Có thể để tên Java mô tả logic cho lập trình viên và display name diễn đạt tự nhiên cho người đọc báo cáo.

## 8. Chọn độ chi tiết phù hợp

Tên nên chỉ rõ **điều kiện phân biệt**, không chứa toàn bộ fixture hay mọi bước setup.

**Chưa đủ cụ thể:**

- `testService()`: không biết chức năng, tình huống hay kỳ vọng.
- `reserve_shouldWork()`: “work” không phải kết quả đo được.
- `createOrder_returnsSuccess()`: “success” chưa nêu trạng thái hoặc điều kiện.
- `testException()`: không biết điều gì gây lỗi, loại lỗi nào.

**Cụ thể và hữu ích hơn:**

- `reserve_whenStockIsSufficient_decreasesStock`.
- `reserve_whenQuantityIsZero_throwsIllegalArgumentException`.
- `createOrder_whenRequestIsValid_returns201WithOrderId`.
- `authenticate_whenPasswordIsIncorrect_rejectsCredentials`.

**Quá gắn với chi tiết cài đặt:** `reserve_whenStockIsInsufficient_callsRepositoryFindByIdTwice`. Nếu số lần gọi repository không phải hợp đồng được yêu cầu, tên như vậy mô tả cách triển khai thay vì quy tắc nghiệp vụ. Khi tối ưu code, test có thể gãy dù hành vi bên ngoài vẫn đúng.

**Quá nhiều thông tin:** tên liệt kê mười trường dữ liệu, mọi lệnh mock và mọi bước assertion. Hãy chuyển các chi tiết đó vào Arrange và assertion, hoặc dùng display name, dữ liệu test và nhóm test. Một tên dài chỉ đáng giữ nếu mỗi phần đều giúp phân biệt một quy tắc quan trọng.

Tên method cần được đổi khi hợp đồng/expected result thay đổi. Nếu trước đây thiếu hàng trả về `false` nhưng yêu cầu mới là ném `InsufficientStockException`, không giữ tên `returnsFalse` rồi sửa assertion; phải cập nhật tên để bộ test không đưa ra mô tả sai.

## 9. Những lỗi thường gặp khi đặt tên test

1. **Đặt tên theo số thứ tự hoặc lịch sử viết:** `test2()`, `newTest()`, `fixBug()`. Sửa thành hành vi cụ thể; ID ticket có thể đặt trong comment hoặc metadata báo cáo.
2. **Chỉ nêu chức năng:** `calculateTotal()`. Bổ sung tình huống và kết quả, như `calculateTotal_whenCartIsEmpty_returnsZero`.
3. **Chỉ nêu điều kiện:** `whenUserHasNoPermission()`. Cần nói hệ thống sẽ từ chối thế nào, ví dụ `deleteItem_whenPermissionIsMissing_returns403`.
4. **Chỉ nêu kết quả:** `shouldThrowException()`. Cần nói điều kiện gây lỗi và loại exception cụ thể.
5. **Tên và assertion mâu thuẫn:** tên “doesNotModifyBalance” nhưng không kiểm tra balance. Đồng bộ tên với kỳ vọng thực sự được xác minh.
6. **Giấu nhiều ca độc lập trong một test:** tên chỉ nói “success” nhưng thân test thử cả thành công, thất bại và exception. Tách theo tình huống để báo cáo cho biết trường hợp nào hỏng.
7. **Tên phụ thuộc kỹ thuật dễ đổi:** tên theo tên mock, thứ tự gọi hàm nội bộ hoặc chi tiết persistence không thuộc hợp đồng. Đặt lại theo kết quả bên ngoài có thể quan sát.
8. **Không nhất quán giữa các nhóm:** một nơi dùng `testSomething`, nơi khác dùng `should...When...`, nơi khác dùng `given...when...then...`. Thống nhất một mẫu chủ đạo ở cấp module/nhóm, nhưng ưu tiên tên dễ hiểu hơn việc ép khuôn máy móc.

## 10. Quy trình đặt tên thực tế trước khi code

**Bước 1 — Viết câu mô tả tình huống:** “Khi số lượng đặt vượt tồn kho”.

**Bước 2 — Xác định hành động:** “Gọi `reserve(quantity)`”.

**Bước 3 — Chốt kết quả cần assert:** “Hệ thống trả về `false` và không trừ tồn kho”.

**Bước 4 — Ghép thành tên có thể tìm kiếm:** `reserve_whenStockIsInsufficient_returnsFalseWithoutChangingStock`.

**Bước 5 — So khớp với thân test:** Arrange tạo tồn kho ít hơn số lượng đặt; Act gọi đúng `reserve`; Assert kiểm tra cả kết quả trả về và số lượng còn lại.

**Bước 6 — Đọc tên khi tưởng tượng test FAIL:** tên có giúp xác định điều kiện và hợp đồng bị vi phạm không? Nếu chưa, bổ sung phần còn thiếu hoặc tách test.

Có thể tự kiểm bằng checklist:

- [ ] Tên cho biết chức năng/hành động được kiểm tra hoặc ngữ cảnh nhóm đã nêu rõ điều đó.
- [ ] Tên chỉ ra **khi nào** hành vi xảy ra (dữ liệu, trạng thái, quyền, ranh giới, lỗi).
- [ ] Tên chỉ ra **kết quả mong đợi** cụ thể và có thể kiểm tra.
- [ ] Assertion thực sự xác minh nội dung mà tên hứa hẹn.
- [ ] Các ca khác nhau có tên đủ khác nhau để định vị lỗi từ báo cáo JUnit/CI.
- [ ] Tên mô tả hành vi nghiệp vụ ổn định, tránh chi tiết triển khai không thuộc hợp đồng.
- [ ] Test dữ liệu tham số có display name phân biệt từng lượt khi hữu ích.
- [ ] Tên Java, display name và hành vi hiện tại không mâu thuẫn.

**Ghi nhớ:** đặt tên test theo **tình huống → hành động → kết quả** biến bộ kiểm thử thành một tài liệu hành vi có thể thực thi. Người đọc biết trường hợp nào đang được chứng minh, và khi test thất bại có thể xác định ngay quy tắc nào cần điều tra.