# Đặt tên thể hiện điều kiện và hành vi

Tên bài kiểm thử là một phần của tài liệu kỹ thuật của ứng dụng. Khi một test thất bại trong IDE hoặc CI, người đọc thường nhìn tên test trước khi mở phần thân phương thức. Một tên tốt cho biết tình huống nào đang được kiểm tra và hệ thống được kỳ vọng phản ứng ra sao. Nhờ đó, nhóm phát triển có thể hiểu phạm vi của lỗi, nhận ra quy tắc nghiệp vụ đang được bảo vệ và tìm đúng nơi cần điều tra.

Trong dự án Spring, điều này càng quan trọng vì một bài kiểm thử có thể bao phủ nhiều lớp: controller, security filter, service, repository, transaction, cache hoặc tác vụ nền. Tên như `testOrder()` không cho biết test đang kiểm tra điều gì trong số đó. Tên như `returnsForbiddenWhenCallerDoesNotOwnOrder()` diễn đạt rõ điều kiện và kết quả cần bảo vệ.

## 1. Tên test cần trả lời điều gì?

Một tên test hữu ích thường làm rõ ba ý:

1. **Điều kiện hoặc bối cảnh:** dữ liệu, trạng thái, quyền của người gọi, cấu hình hoặc sự cố đang tồn tại.
2. **Hành vi được kích hoạt:** thao tác hoặc lời gọi mà test thực hiện.
3. **Kết quả mong đợi:** điều hệ thống phải làm, phải trả về hoặc phải tránh làm.

Không phải tên nào cũng cần ghi đủ ba ý bằng một câu dài. Hãy ưu tiên thông tin giúp phân biệt test này với các test khác trong cùng nhóm.

| Tên chưa rõ | Tên thể hiện điều kiện và hành vi | Điều người đọc nhận biết được |
| --- | --- | --- |
| `testCreateOrder()` | `createsDraftOrderWhenCartContainsAvailableItems()` | Đơn nháp được tạo khi giỏ có mặt hàng còn khả dụng |
| `testInvalidAddress()` | `rejectsCheckoutWhenShippingAddressIsMissing()` | Checkout bị từ chối khi thiếu địa chỉ giao hàng |
| `testGetOrder()` | `returnsNotFoundWhenOrderDoesNotExist()` | API trả về 404 khi mã đơn không tồn tại |
| `testPermission()` | `returnsForbiddenWhenCallerDoesNotOwnOrder()` | Người gọi không sở hữu đơn hàng bị từ chối truy cập |
| `testRollback()` | `rollsBackInventoryReservationWhenOrderPersistenceFails()` | Giữ tồn kho được hoàn tác nếu lưu đơn thất bại |
| `testCache()` | `evictsProductCacheWhenProductIsUpdated()` | Cache sản phẩm bị xóa sau khi cập nhật |

Các tên ở cột bên phải cho biết quy tắc hoặc tình huống, nên có thể đọc độc lập trong báo cáo kiểm thử. Tên ở cột bên trái chỉ nói rằng một phương thức nào đó đã được chạy.

## 2. Chọn một quy ước đặt tên nhất quán

Java cho phép đặt tên phương thức test bằng camelCase. Nhóm có thể chọn một trong các dạng sau, miễn là dùng nhất quán và không làm mất thông tin về hành vi.

### Dạng hành vi + điều kiện

Mẫu thường dùng:

```text
<expectedBehavior>When<condition>
```

Ví dụ:

```java
@Test
void createsDraftOrderWhenCartContainsAvailableItems() {
    // Arrange, act, assert
}

@Test
void rejectsCheckoutWhenShippingAddressIsMissing() {
    // Arrange, act, assert
}

@Test
void returnsForbiddenWhenCallerDoesNotOwnOrder() {
    // Arrange, act, assert
}
```

Dạng này phù hợp khi điều kiện là yếu tố quan trọng để hiểu kết quả. Từ đầu tên, người đọc thấy hành vi; phần `When...` mô tả hoàn cảnh làm hành vi đó xảy ra.

### Dạng given – when – then

Mẫu này diễn đạt rõ bối cảnh, hành động và kết quả:

```text
given<condition>When<action>Then<expectedResult>
```

Ví dụ:

```java
@Test
void givenExpiredTokenWhenRequestingProfileThenReturnsUnauthorized() {
    // Arrange: tạo token hết hạn
    // Act: gọi endpoint hồ sơ
    // Assert: xác nhận HTTP 401
}
```

Dạng này hữu ích với luồng có nhiều bước hoặc nhiều điều kiện cần phân biệt. Tuy nhiên, tên có thể trở nên rất dài. Nếu `given`, `when` và `then` đã được thể hiện rõ trong cấu trúc `@Nested` hoặc trong tên nhóm, không cần lặp lại mọi từ trong từng phương thức.

### Dạng method_condition_expectedResult

Một số nhóm thích đặt tên theo phương thức hoặc thao tác đang được kiểm tra:

```text
<method>_<condition>_<expectedResult>
```

Ví dụ:

```java
@Test
void findByEmail_unknownEmail_returnsEmpty() {
    // ...
}

@Test
void reserveStock_insufficientQuantity_throwsInsufficientStockException() {
    // ...
}
```

Dạng này có thể dễ quét trong một class chứa nhiều trường hợp cho cùng API. Đổi lại, tên có dấu gạch dưới thường không đồng nhất với camelCase phổ biến trong Java. Hãy theo quy ước hiện có của repository nếu nhóm đã chọn một kiểu.

## 3. Viết điều kiện đủ cụ thể

Điều kiện là phần giúp người đọc hiểu test đang mô phỏng tình huống nào. Những từ như `invalid`, `error`, `failed` hoặc `empty` thường quá chung nếu không có đối tượng đi kèm.

Hãy chỉ rõ loại dữ liệu hoặc trạng thái:

| Điều kiện chung chung | Điều kiện cụ thể hơn |
| --- | --- |
| `WhenInvalidInput` | `WhenQuantityIsZero` |
| `WhenUserIsInvalid` | `WhenUserHasNoOrderReadPermission` |
| `WhenDataIsMissing` | `WhenShippingAddressIsMissing` |
| `WhenRequestFails` | `WhenPaymentGatewayTimesOut` |
| `WhenOrderIsBad` | `WhenOrderIsAlreadyCancelled` |
| `WhenCacheChanges` | `WhenProductIsUpdated` |

Điều kiện nên phản ánh dữ liệu hoặc trạng thái có ý nghĩa đối với hành vi. Ví dụ, nếu một endpoint trả 403 vì người dùng không sở hữu đơn hàng, tên test nên nói về quyền sở hữu; chỉ ghi `whenUserIsInvalid` có thể khiến người đọc hiểu nhầm rằng tài khoản hoặc token bị lỗi.

Với ứng dụng Spring, điều kiện có thể nằm ở nhiều tầng:

- HTTP: thiếu header, sai content type, body không hợp lệ hoặc path variable không tồn tại.
- Bảo mật: chưa xác thực, thiếu role, token hết hạn hoặc không sở hữu tài nguyên.
- Nghiệp vụ: giỏ hàng rỗng, số lượng vượt tồn kho hoặc đơn đã bị hủy.
- Dữ liệu: bản ghi chưa tồn tại, email trùng hoặc quan hệ entity không hợp lệ.
- Hạ tầng: database mất kết nối, dịch vụ ngoài timeout hoặc message được gửi lại.
- Cấu hình: profile không bật bean, property thiếu hoặc cache được cấu hình với TTL khác nhau.

Đừng đưa mọi chi tiết của fixture vào tên. `whenCustomer42WithAddressAtDistrict7CreatesOrder()` thường mô tả dữ liệu thử nghiệm hơn là điều kiện nghiệp vụ. Nếu mã khách hàng cụ thể không ảnh hưởng quy tắc, hãy gọi nó là `whenCustomerHasValidShippingAddress`.

## 4. Gọi tên hành vi theo góc nhìn của hợp đồng

Phần hành vi nên mô tả điều hệ thống cam kết với caller hoặc với thành phần phụ thuộc. Ưu tiên động từ rõ nghĩa:

- `creates`, `updates`, `deletes`, `persists`, `loads` cho thao tác dữ liệu.
- `returns`, `respondsWith`, `maps` cho API và chuyển đổi dữ liệu.
- `rejects`, `denies`, `throws`, `fails` cho trường hợp bị từ chối hoặc phát sinh lỗi.
- `publishes`, `schedules`, `retries`, `acknowledges` cho event và xử lý nền.
- `evicts`, `reuses`, `expires` cho cache.
- `commits`, `rollsBack` cho transaction.

Ví dụ:

```java
@Test
void returnsNotFoundWhenOrderDoesNotExist() {
    // ...
}

@Test
void throwsInsufficientStockExceptionWhenRequestedQuantityExceedsAvailableStock() {
    // ...
}

@Test
void publishesOrderCreatedEventAfterTransactionCommits() {
    // ...
}
```

Tên test nên thể hiện kết quả có thể quan sát được. `callsRepository()` chỉ mô tả một tương tác nội bộ; nó không cho biết kết quả nghiệp vụ. Nếu mục tiêu thật sự là bảo đảm repository được gọi với một điều kiện cụ thể, hãy nêu rõ lý do hoặc dữ liệu có ý nghĩa, chẳng hạn `loadsOrderByIdWhenOrderDetailsAreRequested`.

Không nên để tên phụ thuộc vào cách triển khai nếu hợp đồng không yêu cầu cách đó. Nếu test bảo vệ việc người dùng chỉ xem được đơn của mình, tên `returnsForbiddenWhenCallerDoesNotOwnOrder` vẫn đúng dù nhóm thay đổi từ một repository query sang một authorization service.

## 5. Tên test và cấu trúc Arrange – Act – Assert

Tên và phần thân test cần cùng mô tả một kịch bản. Một cách tổ chức phổ biến là:

1. **Arrange:** chuẩn bị điều kiện được nêu trong tên.
2. **Act:** thực hiện hành động được nêu trong tên.
3. **Assert:** xác nhận kết quả được nêu trong tên.

Ví dụ kiểm thử service:

```java
@Test
void rejectsCheckoutWhenShippingAddressIsMissing() {
    // Arrange
    Cart cart = cartWithAvailableItems();
    CheckoutCommand command = new CheckoutCommand(cart, null);

    // Act + Assert
    assertThrows(
        MissingShippingAddressException.class,
        () -> checkoutService.checkout(command)
    );
}
```

Tên test nêu điều kiện thiếu địa chỉ và hành vi từ chối checkout. Phần Arrange tạo đúng điều kiện đó; phần Act gọi checkout; phần Assert xác nhận exception tương ứng.

Ví dụ kiểm thử HTTP với Spring MVC:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsBadRequestWhenQuantityIsZero() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId":"book-1", "quantity":0}
                    """))
            .andExpect(status().isBadRequest());
    }
}
```

Tên cho biết input cụ thể và kết quả HTTP. Khi người đọc thấy test thất bại, họ biết cần xem validation của request tạo đơn, thay vì phải mở phần thân để đoán test đang kiểm tra endpoint nào.

Nếu tên nói `returnsBadRequest` nhưng assertion chỉ kiểm tra rằng một mock service được gọi, tên và nội dung đã lệch nhau. Hãy để tên phản ánh điều mà assertion thực sự xác nhận.

## 6. Dùng `@DisplayName` để làm tên dễ đọc

JUnit Jupiter cho phép đặt tên hiển thị bằng `@DisplayName`. Tên phương thức vẫn tuân theo cú pháp Java, còn tên hiển thị có thể là một câu tự nhiên, có dấu và có khoảng trắng.

```java
@Test
@DisplayName("Trả về 403 khi người gọi không sở hữu đơn hàng")
void returnsForbiddenWhenCallerDoesNotOwnOrder() throws Exception {
    // ...
}
```

`@DisplayName` hữu ích khi báo cáo kiểm thử được đọc bởi cả người không quen quy ước đặt tên tiếng Anh trong mã. Nhóm có thể dùng tên phương thức tiếng Anh ổn định và tên hiển thị tiếng Việt để mô tả tình huống.

Có thể đặt tên hiển thị cho class hoặc nhóm lồng nhau:

```java
@DisplayName("Kiểm thử API đơn hàng")
class OrderControllerTest {

    @Nested
    @DisplayName("Khi người gọi chưa xác thực")
    class UnauthenticatedCaller {

        @Test
        @DisplayName("Trả về 401 khi yêu cầu danh sách đơn hàng")
        void returnsUnauthorizedWhenListingOrders() throws Exception {
            // ...
        }
    }
}
```

Tên hiển thị của nhóm cung cấp bối cảnh chung; tên phương thức bổ sung hành động và kết quả. Tránh lặp nguyên văn cả câu ở class, nested class và method vì báo cáo sẽ dài mà không thêm thông tin.

JUnit cũng hỗ trợ `@DisplayNameGeneration`, ví dụ `DisplayNameGenerator.ReplaceUnderscores`, để chuyển tên phương thức có dấu gạch dưới thành tên hiển thị dễ đọc. Nếu dùng cơ chế này, hãy ghi nhận quy ước trong nhóm và tránh trộn nhiều cách sinh tên trong cùng một test suite.

## 7. Dùng `@Nested` để gom các điều kiện có chung bối cảnh

`@Nested` trong JUnit Jupiter cho phép tổ chức test theo ngữ cảnh. Điều này hữu ích khi một service hoặc controller có nhiều hành vi phụ thuộc vào trạng thái ban đầu.

```java
@DisplayName("OrderService")
class OrderServiceTest {

    @Nested
    @DisplayName("Khi đơn hàng đang ở trạng thái PENDING")
    class PendingOrder {

        @Test
        void cancelsOrderWhenCustomerRequestsCancellation() {
            // ...
        }

        @Test
        void rejectsShipmentWhenPaymentHasNotCompleted() {
            // ...
        }
    }

    @Nested
    @DisplayName("Khi đơn hàng đã bị hủy")
    class CancelledOrder {

        @Test
        void rejectsCancellationWhenOrderIsAlreadyCancelled() {
            // ...
        }
    }
}
```

Tên nested class diễn đạt bối cảnh chung, còn mỗi test nói hành vi xảy ra trong bối cảnh đó. Cấu trúc này giúp giảm độ dài tên phương thức mà vẫn giữ đủ thông tin khi đọc báo cáo theo cây.

Chỉ nên tạo nhóm lồng nhau khi các test thật sự có chung trạng thái hoặc ngữ cảnh. Không cần tạo một cấp nested cho mỗi method, cũng không nên để nhiều cấp lồng nhau khiến người đọc phải mở rộng nhiều tầng mới biết test nói về điều gì.

## 8. Đặt tên cho kiểm thử tham số hóa

Khi cùng một quy tắc được kiểm tra với nhiều bộ dữ liệu, `@ParameterizedTest` giúp tránh sao chép nhiều phương thức gần giống nhau. Tên test cần nêu quy tắc chung, còn tên hiển thị của từng lần chạy nên bổ sung giá trị đầu vào để phân biệt trường hợp thất bại.

Ví dụ kiểm tra số lượng không hợp lệ:

```java
@ParameterizedTest(name = "[{index}] từ chối số lượng {0}")
@ValueSource(ints = {0, -1})
void rejectsNonPositiveQuantity(int quantity) {
    assertThrows(
        InvalidQuantityException.class,
        () -> orderService.createOrder("book-1", quantity)
    );
}
```

Tên phương thức `rejectsNonPositiveQuantity` mô tả quy tắc. Tên hiển thị như `[1] từ chối số lượng 0` và `[2] từ chối số lượng -1` cho biết bộ dữ liệu nào làm test thất bại.

Với `@CsvSource`, có thể đưa cả đầu vào và kết quả kỳ vọng vào tên lần chạy:

```java
@ParameterizedTest(name = "quantity={0} thì trả về {1}")
@CsvSource({
    "0, INVALID",
    "-1, INVALID",
    "1, ACCEPTED"
})
void classifiesRequestedQuantity(int quantity, String expectedStatus) {
    assertEquals(expectedStatus, orderService.classifyQuantity(quantity));
}
```

Tên tham số hóa nên ngắn và giúp xác định dữ liệu gây lỗi. Không cần đưa mọi cột của fixture vào chuỗi hiển thị; chỉ chọn giá trị có liên quan trực tiếp đến quy tắc đang kiểm tra.

Với `@MethodSource`, dữ liệu có thể là object phức tạp. Hãy cung cấp tên hoặc mô tả ngắn có ý nghĩa cho từng bộ dữ liệu nếu báo cáo mặc định chỉ hiển thị biểu diễn khó đọc của object. Có thể dùng `Arguments` với một trường hợp đại diện rõ ràng, hoặc tách thành các test riêng nếu từng tình huống có ý nghĩa nghiệp vụ khác nhau.

## 9. Đặt tên cho test lỗi và ngoại lệ

Test lỗi thường có nhiều điều kiện hơn test thành công. Tên nên cho biết lỗi đến từ đâu và hệ thống cần phản ứng thế nào.

Ví dụ:

```java
@Test
void returnsServiceUnavailableWhenPaymentGatewayTimesOut() {
    // ...
}

@Test
void retriesPaymentRequestWhenGatewayReturnsTemporaryServerError() {
    // ...
}

@Test
void doesNotRetryPaymentWhenGatewayRejectsInvalidCard() {
    // ...
}

@Test
void rollsBackOrderCreationWhenInventoryReservationFails() {
    // ...
}
```

Những tên này phân biệt timeout, lỗi máy chủ tạm thời, dữ liệu thẻ không hợp lệ và lỗi giữ tồn kho. Chúng giúp người đọc nhận ra chính sách retry hoặc rollback đang được bảo vệ.

Nếu test kiểm tra exception, hãy nêu loại kết quả quan trọng. Ví dụ `throwsInsufficientStockExceptionWhenRequestedQuantityExceedsAvailableStock` có giá trị hơn `throwsExceptionWhenInvalid`. Nếu loại exception không phải hợp đồng cần bảo vệ, có thể mô tả kết quả bên ngoài như `returnsConflictWhenStockIsInsufficient`.

Không đưa chi tiết của mock vào tên như `throwsExceptionWhenMockRepositoryReturnsNull`. Hãy mô tả tình huống ở góc nhìn nghiệp vụ hoặc hợp đồng: `returnsNotFoundWhenOrderDoesNotExist`.

## 10. Tên test cho các lớp Spring khác nhau

Tên test cần phù hợp với trách nhiệm của lớp đang được kiểm tra. Một số ví dụ thường gặp:

| Loại test | Ví dụ tên | Trọng tâm được thể hiện |
| --- | --- | --- |
| Service unit test | `calculatesOrderTotalIncludingApplicableDiscount()` | Quy tắc tính toán nghiệp vụ |
| Controller slice test | `returnsBadRequestWhenRequestBodyIsInvalid()` | Mapping HTTP và validation |
| Security test | `returnsForbiddenWhenCallerLacksOrderPermission()` | Chính sách phân quyền |
| Repository test | `findByEmailReturnsEmptyWhenNoAccountMatches()` | Kết quả truy vấn khi không có bản ghi |
| Transaction test | `rollsBackInventoryChangesWhenOrderSaveFails()` | Tính nguyên tử của nghiệp vụ |
| Cache test | `reusesCachedProductWhenSameProductIsRequested()` | Hành vi cache khi đọc lặp |
| Async test | `completesReportGenerationWhenBackgroundTaskIsScheduled()` | Kết quả của tác vụ nền |
| Event test | `publishesOrderCreatedEventAfterSuccessfulCommit()` | Thời điểm phát event |
| Integration test | `createsOrderThroughHttpAndPersistsItInDatabase()` | Luồng phối hợp qua nhiều thành phần |

Tên class cũng nên cho biết phạm vi: `OrderServiceTest`, `OrderControllerTest`, `OrderRepositoryTest`, `OrderSecurityTest` hoặc `OrderFlowIntegrationTest`. Khi class có nhiều nhóm trách nhiệm, cân nhắc tách class để mỗi file có một chủ đề rõ ràng.

Với `@SpringBootTest`, tên test không nên mặc định dùng từ `integration` chỉ vì context được khởi tạo. Hãy mô tả hành vi mà bài kiểm thử thực sự xác nhận. Nếu test chạy toàn bộ luồng từ HTTP đến database, tên có thể nói rõ cả hai đầu; nếu chỉ kiểm tra một property được inject, tên nên nêu cấu hình đó.

## 11. Phân biệt tên test mô tả hành vi với tên mô tả cách cài đặt

Tên test thường tồn tại lâu hơn một implementation cụ thể. Nếu tên ghi chi tiết nội bộ, một refactor không đổi hành vi cũng khiến tên trở nên sai.

| Tên thiên về implementation | Tên thiên về hành vi |
| --- | --- |
| `callsSaveMethodOnRepository()` | `persistsNewOrderWhenCheckoutSucceeds()` |
| `usesSecondMockResponse()` | `retriesRequestAfterTemporaryGatewayFailure()` |
| `invokesCacheManagerEvict()` | `evictsProductCacheWhenProductIsUpdated()` |
| `callsMapperConvert()` | `returnsOrderResponseWithCustomerDetails()` |
| `setsBooleanFlagToFalse()` | `marksOrderAsCancelledWhenCancellationIsAccepted()` |

Có những test chủ đích kiểm tra tương tác với dependency, chẳng hạn xác nhận không gửi email khi giao dịch bị từ chối. Khi đó, tên có thể nhắc đến hành động bên ngoài vì nó là hợp đồng có ý nghĩa:

```java
@Test
void doesNotSendConfirmationEmailWhenPaymentIsDeclined() {
    // ...
}
```

Điều cần tránh là đưa tên class mock, số lần gọi nội bộ hoặc tên biến fixture vào tiêu đề nếu chúng không giúp hiểu hành vi.

## 12. Tránh các kiểu tên gây nhiễu

Một số thói quen khiến báo cáo test khó đọc:

- **Tên chỉ có số thứ tự:** `test1`, `test2`, `testCase03` không nói test đang bảo vệ điều gì.
- **Tên lặp từ `test`:** `testCreateOrderTest` thêm chữ mà không thêm ý nghĩa; annotation `@Test` đã xác định đây là test.
- **Tên quá rộng:** `handlesError`, `validatesRequest`, `worksCorrectly` không nêu điều kiện hoặc kết quả.
- **Tên quá dài:** chép toàn bộ fixture, ID và từng bước triển khai vào một phương thức khiến phần quan trọng khó nhận ra.
- **Tên khẳng định nhiều điều:** `createsOrderAndSendsEmailAndUpdatesStockAndPublishesEvent` có thể che giấu một test đang kiểm tra quá nhiều hành vi.
- **Tên không khớp assertion:** tên nói trả 404 nhưng test chỉ xác nhận service được gọi.
- **Tên gắn với chi tiết tạm thời:** tên chứa tên mock, thứ tự gọi hoặc tên helper khiến refactor làm tiêu đề sai dù hành vi không đổi.
- **Dùng từ mơ hồ:** `valid`, `invalid`, `success`, `failure` mà không chỉ rõ điều gì hợp lệ hoặc thất bại.

Nếu tên trở nên quá dài, hãy xem xét liệu test có đang kết hợp nhiều kịch bản hay không. Tách test khi các trường hợp có điều kiện hoặc kết quả khác nhau. Nếu các trường hợp chỉ khác giá trị dữ liệu nhưng cùng một quy tắc, dùng kiểm thử tham số hóa và hiển thị giá trị đầu vào trong tên lần chạy.

## 13. Tên test phải khớp với phạm vi và assertion

Một test có thể mang tên nghe rất thuyết phục nhưng vẫn không chứng minh điều tên đó tuyên bố. Tên là mô tả ý định; assertion mới là bằng chứng.

Ví dụ, tên `rollsBackOrderWhenPaymentFails` cần có một phép kiểm tra cho thấy trạng thái dữ liệu thực sự không được commit hoặc được hoàn tác theo thiết kế. Chỉ kiểm tra rằng `paymentGateway.charge()` ném exception chưa chứng minh transaction của database đã rollback.

Tương tự, `returnsForbiddenWhenCallerDoesNotOwnOrder` nên thực hiện request qua đường bảo mật đang được dùng và xác nhận response 403. Nếu test chỉ gọi trực tiếp một method service mà không có security context, nó chưa kiểm tra được toàn bộ hợp đồng HTTP được nêu trong tên.

Khi xem lại tên, hãy đối chiếu từng phần:

| Phần của tên | Câu hỏi đối chiếu với test |
| --- | --- |
| Điều kiện | Fixture hoặc cấu hình có thật sự tạo đúng tình huống đó không? |
| Hành động | Test có gọi đúng thao tác hoặc ranh giới được mô tả không? |
| Kết quả | Assertion có xác nhận kết quả đó một cách trực tiếp không? |
| Phạm vi | Test có chạy qua lớp Spring cần thiết để chứng minh hành vi không? |

Nếu một tên nêu nhiều kết quả, hãy chắc rằng test xác nhận tất cả kết quả đó. Nếu chỉ một kết quả là mục tiêu chính, bỏ phần phụ khỏi tên hoặc tách thành test khác để báo cáo lỗi rõ ràng hơn.

## 14. Tổ chức tên theo một bộ quy tắc của nhóm

Một nhóm phát triển có thể thống nhất một quy ước ngắn gọn trong hướng dẫn đóng góp hoặc tài liệu kiểm thử. Quy ước nên trả lời các điểm sau:

1. Dùng camelCase theo dạng `behaviorWhenCondition`, hay dùng `method_condition_expectedResult`?
2. Có dùng `@DisplayName` tiếng Việt cho báo cáo hay không?
3. Khi nào dùng `@Nested` để đưa bối cảnh lên tên nhóm?
4. Với test tham số hóa, giá trị nào cần xuất hiện trong tên từng lần chạy?
5. Có cần ghi mã ticket hoặc ID nghiệp vụ trong tên không? Thông thường chỉ nên ghi khi ID là một phần của hợp đồng hoặc giúp truy vết cần thiết.

Một quy ước thực tế có thể là:

- Tên phương thức dùng tiếng Anh, camelCase, bắt đầu bằng động từ mô tả kết quả.
- Điều kiện quan trọng được nối bằng `When...`.
- Dùng `@DisplayName` tiếng Việt khi báo cáo cần thân thiện với cả nhóm phát triển và QA.
- Dùng `@Nested` cho bối cảnh chung như trạng thái đơn hàng hoặc trạng thái xác thực.
- Tên tham số hóa hiển thị giá trị đầu vào làm thay đổi kết quả.
- Không thêm tiền tố `test` và không mô tả chi tiết mock trong tên.

Ví dụ bộ tên nhất quán cho một luồng checkout:

```java
@DisplayName("CheckoutService")
class CheckoutServiceTest {

    @Test
    @DisplayName("Tạo đơn nháp khi giỏ hàng có sản phẩm còn hàng")
    void createsDraftOrderWhenCartContainsAvailableItems() {
        // ...
    }

    @Test
    @DisplayName("Từ chối checkout khi giỏ hàng rỗng")
    void rejectsCheckoutWhenCartIsEmpty() {
        // ...
    }

    @Test
    @DisplayName("Không gửi yêu cầu thanh toán khi địa chỉ giao hàng bị thiếu")
    void doesNotRequestPaymentWhenShippingAddressIsMissing() {
        // ...
    }

    @Test
    @DisplayName("Hoàn tác giữ tồn kho khi lưu đơn hàng thất bại")
    void rollsBackInventoryReservationWhenOrderPersistenceFails() {
        // ...
    }
}
```

Các tên trong ví dụ diễn đạt các tình huống khác nhau: thành công, dữ liệu rỗng, thiếu thông tin và lỗi giữa luồng. Khi CI hiển thị một test thất bại, nhóm có thể xác định ngay kịch bản liên quan.

## 15. Quy trình đặt tên trước khi viết test

Có thể đặt tên ngay khi xác định kịch bản, trước khi viết phần thân test. Cách làm này giúp làm rõ mục tiêu và phát hiện sớm những kịch bản còn mơ hồ.

**Bước 1: Viết điều kiện bằng ngôn ngữ nghiệp vụ.** Ví dụ: người dùng đã đăng nhập nhưng không sở hữu đơn hàng.

**Bước 2: Nêu hành động.** Người dùng gửi request xem chi tiết đơn hàng.

**Bước 3: Nêu kết quả mong đợi.** API từ chối với HTTP 403.

**Bước 4: Ghép thành tên.** `returnsForbiddenWhenCallerDoesNotOwnOrder`.

**Bước 5: Viết Arrange – Act – Assert để chứng minh tên.** Tạo danh tính người dùng, tạo đơn thuộc người khác, gọi endpoint và kiểm tra status 403.

**Bước 6: Kiểm tra tên trong báo cáo.** Người chưa đọc mã nguồn có thể hiểu test đang bảo vệ chính sách nào không? Nếu không, hãy bổ sung điều kiện hoặc kết quả còn thiếu.

Quy trình này cũng giúp phân biệt một test thực sự cần thiết với một test chỉ lặp lại tên phương thức production. `createOrder()` không phải một kịch bản kiểm thử; `createsDraftOrderWhenCartContainsAvailableItems()` là một kỳ vọng có điều kiện cụ thể.

## 16. Ví dụ chuyển từ yêu cầu sang tên test

Giả sử yêu cầu của hệ thống là: khách hàng chỉ được xem đơn hàng thuộc tài khoản của mình. Có thể tách thành các kịch bản có tên rõ ràng:

| Điều kiện | Hành động | Kết quả | Tên gợi ý |
| --- | --- | --- | --- |
| Người dùng đã xác thực và sở hữu đơn | Xem chi tiết đơn | Trả về 200 và thông tin đơn | `returnsOrderDetailsWhenCallerOwnsOrder()` |
| Người dùng đã xác thực nhưng không sở hữu đơn | Xem chi tiết đơn | Trả về 403 | `returnsForbiddenWhenCallerDoesNotOwnOrder()` |
| Người dùng chưa xác thực | Xem chi tiết đơn | Trả về 401 | `returnsUnauthorizedWhenCallerIsNotAuthenticated()` |
| Mã đơn không tồn tại | Xem chi tiết đơn | Trả về 404 theo chính sách API | `returnsNotFoundWhenOrderDoesNotExist()` |
| Người dùng sở hữu đơn nhưng đơn đã bị xóa mềm | Xem chi tiết đơn | Không hiển thị đơn đã xóa | `hidesSoftDeletedOrderWhenDetailsAreRequested()` |

Các kịch bản này có thể thuộc cùng một class `OrderControllerSecurityTest` hoặc được tổ chức bằng `@Nested` theo trạng thái xác thực và quyền sở hữu. Tên cho biết rõ lý do của mỗi kết quả, giúp báo cáo phân biệt lỗi authentication, authorization và truy vấn dữ liệu.

## 17. Những câu hỏi tự kiểm tra khi đặt tên

Trước khi hoàn tất một test, hãy đọc tên và tự hỏi:

- Tên có nêu tình huống cụ thể thay vì chỉ nói `valid` hoặc `invalid` không?
- Người đọc có nhận ra hành vi mà ứng dụng phải thực hiện không?
- Kết quả được nêu có thể quan sát và được assertion xác nhận không?
- Tên có mô tả quy tắc nghiệp vụ hoặc hợp đồng của lớp đang kiểm tra không?
- Nếu implementation thay đổi nhưng hành vi giữ nguyên, tên có còn đúng không?
- Nếu test thất bại trong CI, tên có giúp khoanh vùng vấn đề mà không cần mở ngay phần thân không?
- Với test tham số hóa, báo cáo có hiển thị dữ liệu gây lỗi không?
- Có thể rút gọn tên bằng cách đưa bối cảnh chung vào `@Nested` mà vẫn dễ hiểu không?

Tên test tốt giúp biến bộ kiểm thử thành một bản mô tả có thể đọc được về hành vi của ứng dụng Spring. Mỗi tên cần nêu rõ điều kiện quan trọng và kết quả được mong đợi; phần thân test phải tạo đúng điều kiện, thực hiện hành động và xác nhận kết quả ấy. Khi nhóm duy trì một quy ước thống nhất, báo cáo từ JUnit, IDE và CI sẽ trở thành tài liệu hữu ích cho việc phát triển, rà soát và xử lý lỗi.
