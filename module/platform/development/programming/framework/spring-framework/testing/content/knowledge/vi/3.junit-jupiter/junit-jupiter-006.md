# assertAll và thông báo lỗi giúp chẩn đoán

JUnit Jupiter cung cấp `assertAll` để nhóm nhiều assertion có liên quan trong cùng một bài kiểm thử. Khi chạy nhóm này, JUnit tiếp tục thực hiện các assertion còn lại dù một assertion đã thất bại, rồi báo cáo các lỗi thu được cùng nhau. Cách tổ chức đó giúp người phát triển nhìn thấy nhiều sai lệch trong một lần chạy thay vì phải sửa từng lỗi theo kiểu chạy lại nhiều lần.

Thông báo lỗi cũng là một phần quan trọng của bài kiểm thử. Một assertion chỉ ra kết quả nào không đạt; thông báo tốt giúp người đọc hiểu kết quả đó thuộc đối tượng, trường dữ liệu hoặc điều kiện nghiệp vụ nào. Kết hợp `assertAll` với thông báo rõ nghĩa giúp kết quả kiểm thử dễ đọc và dễ chẩn đoán hơn.

## 1. Vấn đề khi chỉ dùng các assertion thông thường

JUnit Jupiter có các assertion như `assertEquals`, `assertTrue`, `assertNotNull`, `assertThrows`. Mỗi assertion kiểm tra một điều kiện. Khi assertion thất bại, nó ném ra lỗi assertion và bài test method hiện tại dừng tại đó.

Ví dụ:

```java
@Test
void returnsOrderDetails() {
    OrderResponse response = orderService.getOrder("ORDER-42");

    assertEquals("ORDER-42", response.getId());
    assertEquals(OrderStatus.CONFIRMED, response.getStatus());
    assertEquals(new BigDecimal("120000"), response.getTotal());
    assertEquals(2, response.getItems().size());
}
```

Nếu assertion đầu tiên thất bại, các assertion phía sau không được thực hiện. Người phát triển chỉ nhìn thấy lỗi đầu tiên trong lần chạy đó. Sau khi sửa lỗi và chạy lại, một lỗi khác mới có thể xuất hiện.

Điều này phù hợp khi các bước kiểm tra phụ thuộc vào nhau hoặc khi muốn dừng ngay khi một điều kiện nền tảng không đúng. Nhưng với nhiều thuộc tính độc lập của cùng một kết quả, việc dừng ở assertion đầu tiên làm chậm quá trình chẩn đoán.

## 2. assertAll hoạt động như thế nào?

`assertAll` nhận một nhóm `Executable`. Mỗi executable thường được viết bằng lambda chứa một hoặc nhiều assertion. JUnit thực thi lần lượt các executable trong nhóm, thu thập những lỗi xảy ra và sau đó báo cáo lỗi tổng hợp nếu có ít nhất một lỗi.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void returnsOrderDetails() {
    OrderResponse response = orderService.getOrder("ORDER-42");

    assertAll("order response",
            () -> assertEquals("ORDER-42", response.getId()),
            () -> assertEquals(
                    OrderStatus.CONFIRMED,
                    response.getStatus()
            ),
            () -> assertEquals(
                    new BigDecimal("120000"),
                    response.getTotal()
            ),
            () -> assertEquals(2, response.getItems().size())
    );
}
```

Nếu trạng thái, tổng tiền và số dòng hàng đều sai, JUnit có thể báo cáo cả ba lỗi trong cùng một lần chạy. Một assertion thất bại không ngăn các executable còn lại trong nhóm được thực hiện.

Luồng xử lý có thể hình dung như sau:

```text
Thực hiện hành động cần kiểm tra
              |
              v
       assertAll("...")
              |
       +------+------+
       |      |      |
       v      v      v
   Assertion A  B    C
       |      |      |
       +------+------+
              |
              v
     Thu thập các lỗi
              |
       +------+------+
       |             |
   Không có lỗi   Có lỗi
       |             |
       v             v
      PASS     Báo lỗi tổng hợp
```

Nếu tất cả assertion trong nhóm đều đạt, `assertAll` hoàn tất bình thường và test tiếp tục. Nếu có lỗi, JUnit ném `MultipleFailuresError` chứa các lỗi đã thu thập. Test method được đánh dấu thất bại và báo cáo có thể hiển thị từng lỗi thành phần.

`assertAll` không biến nhiều assertion thành nhiều test method. Chúng vẫn thuộc cùng một test case, dùng chung fixture và trạng thái của test đó. Mục đích của nó là gom các kết quả kiểm tra liên quan để chẩn đoán thuận tiện hơn.

## 3. Đặt tiêu đề cho nhóm assertion

Có thể truyền một chuỗi tiêu đề làm đối số đầu tiên:

```java
assertAll("order response",
        () -> assertEquals("ORDER-42", response.getId()),
        () -> assertEquals(OrderStatus.CONFIRMED, response.getStatus())
);
```

Tiêu đề giúp người đọc nhận ra nhóm kiểm tra đang nói về phần nào của kết quả. Nên chọn tên theo đối tượng hoặc nhóm thuộc tính, chẳng hạn:

- `order response`
- `customer profile`
- `payment result`
- `pagination metadata`

Với các bài test kiểm tra nhiều nhóm thuộc tính, có thể lồng các nhóm `assertAll` để tạo cấu trúc:

```java
assertAll("order response",
        () -> assertAll("identity",
                () -> assertEquals("ORDER-42", response.getId()),
                () -> assertEquals(
                        OrderStatus.CONFIRMED,
                        response.getStatus()
                )
        ),
        () -> assertAll("amounts",
                () -> assertEquals(
                        new BigDecimal("120000"),
                        response.getTotal()
                ),
                () -> assertEquals(
                        new BigDecimal("10000"),
                        response.getShippingFee()
                )
        )
);
```

Nhóm ngoài mô tả response, còn các nhóm con phân loại thông tin định danh và số tiền. Cấu trúc lồng nhau hữu ích khi kết quả có nhiều phần độc lập. Nếu chỉ có hai hoặc ba assertion đơn giản, một nhóm phẳng thường dễ đọc hơn.

Không nên tạo nhiều tầng nhóm chỉ để làm code trông có cấu trúc. Tiêu đề nên giúp tìm lỗi nhanh hơn; nếu người đọc phải mở qua nhiều cấp mới biết assertion đang kiểm tra gì, cấu trúc đã quá phức tạp.

## 4. Thêm thông báo cho từng assertion

Các assertion của JUnit Jupiter thường có overload nhận thông báo. Với `assertEquals`, có thể truyền thông báo sau expected và actual:

```java
assertEquals(
        OrderStatus.CONFIRMED,
        response.getStatus(),
        "order status"
);
```

Khi thất bại, báo cáo gồm thông tin expected, actual và thông báo do người viết cung cấp. Thông báo nên trả lời câu hỏi: **Assertion này đang kiểm tra điều gì?**

Ví dụ:

```java
assertAll("order response",
        () -> assertEquals(
                "ORDER-42",
                response.getId(),
                "order id"
        ),
        () -> assertEquals(
                OrderStatus.CONFIRMED,
                response.getStatus(),
                "order status"
        ),
        () -> assertEquals(
                new BigDecimal("120000"),
                response.getTotal(),
                "order total"
        )
);
```

Khi có lỗi, người đọc có thể nhận ra ngay trường nào không đúng. Nếu chỉ dùng các giá trị expected và actual, vẫn có thể suy ra điều kiện từ code, nhưng thông báo có nghĩa nghiệp vụ giúp báo cáo dễ hiểu hơn, đặc biệt khi nhiều assertion cùng so sánh kiểu dữ liệu giống nhau.

### Thông báo nên cụ thể, ngắn gọn

Thông báo như `"failed"`, `"wrong value"` hoặc `"assertion failed"` không bổ sung thông tin hữu ích. Hãy mô tả trường hoặc quy tắc:

| Thông báo kém hữu ích | Thông báo rõ nghĩa hơn |
|---|---|
| `"wrong value"` | `"order total"` |
| `"status failed"` | `"new order should be PENDING"` |
| `"not equal"` | `"customer email"` |
| `"check result"` | `"page number should be zero-based"` |

Thông báo không cần lặp lại toàn bộ expected và actual nếu JUnit đã hiển thị chúng. Nên dành thông báo cho bối cảnh hoặc ý nghĩa của điều kiện kiểm tra.

## 5. Dùng message supplier cho thông báo động

JUnit Jupiter cho phép truyền `Supplier<String>` thay vì chuỗi thông báo được tạo sẵn. Supplier chỉ được gọi khi assertion thất bại, vì vậy có thể dùng nó để tạo thông báo động mà không phải dựng chuỗi ở mỗi lần kiểm tra thành công.

```java
String orderId = "ORDER-42";

assertEquals(
        OrderStatus.CONFIRMED,
        response.getStatus(),
        () -> "unexpected status for order " + orderId
);
```

Một ví dụ khác với điều kiện boolean:

```java
assertTrue(
        response.getItems().size() > 0,
        () -> "order " + orderId + " should contain at least one item"
);
```

Supplier hữu ích khi thông báo cần đưa vào mã định danh hoặc dữ liệu ngữ cảnh. Với thông báo cố định, truyền trực tiếp chuỗi thường đơn giản và dễ đọc hơn.

Không nên đưa toàn bộ nội dung object hoặc dữ liệu nhạy cảm vào thông báo. Chỉ thêm thông tin cần thiết để xác định tình huống. Một thông báo dài, chứa nhiều dữ liệu không liên quan có thể làm báo cáo khó đọc và gây lộ thông tin trong log CI.

## 6. Kết hợp assertAll với thông báo có ý nghĩa

Ví dụ sau kết hợp tiêu đề nhóm, thông báo riêng và message supplier:

```java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void returnsExpectedOrderResponse() {
    String orderId = "ORDER-42";
    OrderResponse response = orderService.getOrder(orderId);

    assertAll("order response: " + orderId,
            () -> assertEquals(
                    orderId,
                    response.getId(),
                    "response id"
            ),
            () -> assertEquals(
                    OrderStatus.CONFIRMED,
                    response.getStatus(),
                    () -> "unexpected status for " + orderId
            ),
            () -> assertEquals(
                    new BigDecimal("120000"),
                    response.getTotal(),
                    "total amount"
            ),
            () -> assertTrue(
                    response.getItems().size() > 0,
                    () -> "order " + orderId + " should contain items"
            )
    );
}
```

Ở đây có ba cấp thông tin hỗ trợ chẩn đoán:

1. Tiêu đề `order response: ORDER-42` cho biết nhóm thuộc đơn hàng nào.
2. Thông báo của assertion cho biết thuộc tính hoặc quy tắc nào không đạt.
3. Thông tin expected và actual do assertion cung cấp cho biết giá trị cụ thể bị sai lệch.

Cấu trúc này đặc biệt hữu ích khi test chạy trong CI và người đọc chỉ có báo cáo lỗi, không trực tiếp chạy debug. Họ có thể xác định test, đối tượng và thuộc tính gặp vấn đề trước khi mở mã nguồn để điều tra sâu hơn.

## 7. Đặt điều kiện tiên quyết bên ngoài assertAll

Vì `assertAll` tiếp tục thực hiện các executable còn lại, cần cẩn thận với những assertion phụ thuộc vào một điều kiện nền tảng.

Ví dụ, nếu `response` có thể là `null`, đoạn sau có thể tạo ra nhiều lỗi khó hiểu:

```java
assertAll("response",
        () -> assertNotNull(response),
        () -> assertEquals("ORDER-42", response.getId()),
        () -> assertEquals(
                OrderStatus.CONFIRMED,
                response.getStatus()
        )
);
```

Nếu response là `null`, assertion `assertNotNull` thất bại nhưng các lambda sau vẫn được thực hiện. Chúng có thể tiếp tục ném `NullPointerException`. Khi đó báo cáo có cả lỗi null ban đầu và các lỗi phát sinh do dereference đối tượng null.

Nếu các assertion phía sau cần response tồn tại, hãy kiểm tra điều kiện tiên quyết trước:

```java
assertNotNull(response, "order response should be returned");

assertAll("order response",
        () -> assertEquals("ORDER-42", response.getId(), "response id"),
        () -> assertEquals(
                OrderStatus.CONFIRMED,
                response.getStatus(),
                "response status"
        )
);
```

Khi `response` null, test dừng tại assertion tiên quyết và thông báo tập trung vào nguyên nhân gốc. Khi response tồn tại, nhóm assertion tiếp tục kiểm tra các thuộc tính độc lập.

Có thể dùng cùng nguyên tắc với các điều kiện khác: trước khi gom assertion, hãy xác định chúng có thực sự độc lập hay cùng phụ thuộc vào một trạng thái bắt buộc.

## 8. Không đặt hành động cần kiểm tra lặp lại trong từng lambda

`assertAll` dành cho việc gom các kiểm tra. Hành động chính của test nên được thực hiện một lần trong phần Act, sau đó các lambda chỉ quan sát và xác nhận kết quả.

Cách viết dễ gây vấn đề:

```java
assertAll("reservation",
        () -> assertTrue(inventoryService.reserve("BOOK-01", 2)),
        () -> assertEquals(3, inventoryService.getAvailableQuantity("BOOK-01"))
);
```

Trong ví dụ này, lời gọi `reserve` nằm trong một lambda của nhóm, còn việc đọc số lượng ở lambda khác. Nếu một nhóm assertion khác cũng gọi hành động thay đổi trạng thái, kết quả có thể phụ thuộc vào số lần thực thi. Test sẽ khó diễn giải hơn và có nguy cơ thực hiện nghiệp vụ nhiều lần.

Cách rõ ràng hơn:

```java
boolean reserved = inventoryService.reserve("BOOK-01", 2);
int availableQuantity =
        inventoryService.getAvailableQuantity("BOOK-01");

assertAll("reservation result",
        () -> assertTrue(reserved, "reservation should succeed"),
        () -> assertEquals(
                3,
                availableQuantity,
                "remaining stock quantity"
        )
);
```

Hành động chỉ chạy một lần. Các giá trị quan sát được lưu lại trước khi assertion được thực hiện, nên mỗi lambda chỉ kiểm tra một điều kiện.

## 9. assertAll và các overload thường dùng

Trong JUnit Jupiter, `assertAll` có thể nhận các executable theo nhiều dạng:

```java
assertAll(
        () -> assertEquals("Lan", customer.getName()),
        () -> assertTrue(customer.isActive())
);
```

Hoặc có tiêu đề:

```java
assertAll("customer",
        () -> assertEquals("Lan", customer.getName()),
        () -> assertTrue(customer.isActive())
);
```

Cũng có thể truyền một collection hoặc stream các `Executable` khi danh sách kiểm tra được tạo động. Với test thông thường, dạng lambda trực tiếp thường dễ đọc hơn vì các điều kiện nằm ngay tại vị trí sử dụng.

Ví dụ kiểm tra một danh sách có thể dùng stream để tạo executable:

```java
List<Executable> checks = IntStream.range(0, expectedNames.size())
        .mapToObj(index -> (Executable) () ->
                assertEquals(
                        expectedNames.get(index),
                        actualNames.get(index),
                        "name at index " + index
                )
        )
        .toList();

assertAll("customer names", checks);
```

Cách này phù hợp khi số lượng assertion phụ thuộc vào dữ liệu. Cần bảo đảm danh sách actual có kích thước phù hợp trước khi truy cập theo index; nếu không, lỗi truy cập ngoài phạm vi có thể xuất hiện thay vì sai lệch giá trị mà test muốn chẩn đoán. Với danh sách nhỏ, cố định, các lambda viết trực tiếp thường rõ ràng hơn.

## 10. Khi nào nên dùng assertAll?

`assertAll` hữu ích khi các điều kiện cùng mô tả một kết quả và có thể được kiểm tra độc lập:

- Kiểm tra nhiều trường của một DTO hoặc response.
- Kiểm tra nhiều thuộc tính của một entity sau khi xử lý.
- Kiểm tra các phần metadata của một trang kết quả.
- Kiểm tra nhiều quy tắc định dạng trên một giá trị.
- Kiểm tra một nhóm header hoặc thuộc tính HTTP response.

Không nhất thiết phải dùng `assertAll` cho mọi test. Assertion đơn lẻ thường là lựa chọn rõ ràng nhất khi test chỉ có một điều kiện. Các assertion tuần tự cũng phù hợp khi điều kiện sau phụ thuộc vào điều kiện trước hoặc khi thất bại sớm giúp tránh lỗi dây chuyền.

Có thể cân nhắc theo câu hỏi sau:

| Tình huống | Cách viết phù hợp |
|---|---|
| Chỉ có một điều kiện | Assertion trực tiếp |
| Nhiều thuộc tính độc lập của cùng kết quả | `assertAll` |
| Điều kiện sau cần điều kiện trước đúng | Assertion tiên quyết trước, sau đó mới kiểm tra tiếp |
| Hành động làm thay đổi trạng thái | Thực hiện một lần trước nhóm assertion |
| Nhiều kiểm tra lặp theo dữ liệu | Collection/stream executable nếu giúp code rõ hơn |

Một nhóm assertion nên có quan hệ về ý nghĩa. Không nên gom các kiểm tra không liên quan chỉ vì chúng nằm trong cùng một test method. Nhóm có chủ đề rõ giúp báo cáo lỗi dễ đọc và giúp người phát triển xác định khu vực bị ảnh hưởng.

## 11. Đọc báo cáo lỗi để tìm nguyên nhân

Khi `assertAll` thất bại, hãy bắt đầu từ tiêu đề nhóm và từng lỗi thành phần. Sau đó đối chiếu expected, actual và thông báo được viết trong test.

Một cách đọc có hệ thống:

1. **Xác định test method:** biết tình huống nào đã được chạy.
2. **Đọc tiêu đề nhóm:** xác định đối tượng hoặc phần kết quả đang được kiểm tra.
3. **Xem từng lỗi:** ghi nhận assertion nào thất bại, không chỉ đếm tổng số lỗi.
4. **So sánh expected và actual:** xác định sai lệch cụ thể.
5. **Đối chiếu fixture và hành động:** tìm xem dữ liệu đầu vào hoặc kết quả xử lý có giải thích được sai lệch không.
6. **Xác định lỗi gốc:** phân biệt sai lệch độc lập với lỗi phát sinh do điều kiện tiên quyết không đạt.

Ví dụ, nếu nhóm `order response` có lỗi ở `response status` và `total amount`, điều đó cho biết cả hai thuộc tính quan sát được không khớp kỳ vọng. Chưa thể kết luận nguyên nhân nằm ở service, mapping DTO hay dữ liệu lưu trữ. Cần lần theo dữ liệu và hành động của test để xác định nơi phát sinh sai lệch.

Thông báo tốt không thay thế việc điều tra nguyên nhân. Nó rút ngắn bước định vị bằng cách cung cấp ngữ cảnh đủ cụ thể để bắt đầu.

## 12. Những lỗi thường gặp khi dùng assertAll và message

| Cách làm | Hệ quả | Cải thiện |
|---|---|---|
| Gom các assertion không liên quan | Báo cáo khó phân nhóm | Tạo nhóm theo đối tượng hoặc chủ đề |
| Tiêu đề quá chung như `"test"` | Không giúp xác định khu vực lỗi | Đặt tiêu đề mô tả response hoặc thuộc tính |
| Message chỉ ghi `"failed"` | Không bổ sung ngữ cảnh | Ghi tên trường hoặc quy tắc |
| Assertion sau dereference đối tượng có thể null | Phát sinh thêm lỗi thứ cấp | Kiểm tra điều kiện tiên quyết trước |
| Thực hiện hành động trong nhiều lambda | Có thể chạy nghiệp vụ nhiều lần | Act một lần, assert sau |
| Dùng assertAll cho mọi assertion đơn lẻ | Code dài mà không tăng thông tin | Dùng assertion trực tiếp khi phù hợp |
| Lồng quá nhiều cấp | Khó theo dõi cấu trúc báo cáo | Chỉ lồng khi có nhóm ý nghĩa thực sự |
| Đưa toàn bộ object vào message | Báo cáo dài và có thể lộ dữ liệu | Chỉ thêm định danh hoặc ngữ cảnh cần thiết |

Một bài test tốt không cần nhiều thông báo nhất có thể. Nó cần đủ thông tin để người đọc hiểu điều kiện thất bại mà không phải đoán.

## 13. Kết hợp assertAll với cấu trúc Arrange–Act–Assert

Có thể giữ bài kiểm thử dễ đọc bằng cách tách rõ ba phần:

```java
@Test
void createsConfirmedOrderResponse() {
    // Arrange
    CreateOrderCommand command = new CreateOrderCommand(
            "CUSTOMER-42",
            List.of(new OrderLineCommand("BOOK-01", 2))
    );

    // Act
    OrderResponse response = orderService.create(command);

    // Assert
    assertNotNull(response, "order response should be returned");

    assertAll("created order",
            () -> assertEquals(
                    OrderStatus.CONFIRMED,
                    response.getStatus(),
                    "initial order status"
            ),
            () -> assertEquals(
                    "CUSTOMER-42",
                    response.getCustomerId(),
                    "customer id"
            ),
            () -> assertEquals(
                    1,
                    response.getItems().size(),
                    "number of order lines"
            )
    );
}
```

Fixture và command cho biết điều kiện ban đầu. Hành động được gọi đúng một lần. Assertion tiên quyết bảo đảm response tồn tại, rồi `assertAll` kiểm tra các thuộc tính độc lập của kết quả.

Trong thực tế, tên lớp và quy tắc trạng thái phụ thuộc vào ứng dụng. Điều quan trọng là mỗi phần của test thể hiện được dữ liệu chuẩn bị, hành động và bằng chứng mong đợi.

## 14. Giá trị của thông báo lỗi trong quy trình phát triển

Bài kiểm thử tự động thường chạy trên máy lập trình viên và trong CI sau mỗi thay đổi. Khi test thất bại, người nhận báo cáo có thể không phải người viết test hoặc người thực hiện thay đổi. Tiêu đề nhóm và thông báo rõ nghĩa giúp họ hiểu bối cảnh mà không cần chạy lại ngay lập tức.

Khi kết hợp hợp lý:

- `assertAll` cho biết nhiều điều kiện nào cùng không đạt.
- Assertion message xác định ý nghĩa của từng điều kiện.
- Expected và actual thể hiện sai lệch cụ thể.
- Fixture và phần Act cho phép tái dựng tình huống.
- Tên test method cho biết hành vi đang được bảo vệ.

Các thông tin này tạo thành một báo cáo có thể hành động được. Người phát triển có thể khoanh vùng vấn đề, xem lại thay đổi liên quan và quyết định cần sửa logic, dữ liệu chuẩn bị hay chính kỳ vọng của bài kiểm thử.

JUnit Jupiter không thể tự xác định nguyên nhân nghiệp vụ của một lỗi. Người viết test cần lựa chọn nhóm assertion có ý nghĩa, đặt thông báo đúng chỗ và giữ phần chuẩn bị dễ hiểu. Khi làm được điều đó, `assertAll` giúp phát hiện nhiều sai lệch trong một lần chạy, còn thông báo lỗi giúp biến các sai lệch ấy thành thông tin rõ ràng để chẩn đoán.

