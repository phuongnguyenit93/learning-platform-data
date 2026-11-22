# Hợp đồng về kết quả, tác dụng phụ và ngoại lệ

> **Chương:** Tính đúng đắn  
> **Học phần:** CODE_QUALITY_FUNDAMENTALS — Hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

Một phương thức Java biên dịch thành công và trả về giá trị “có vẻ hợp lý” vẫn có thể sai. Nó có thể lưu nhầm dữ liệu, gửi thông báo hai lần, thay đổi trạng thái trước khi báo lỗi hoặc trả về một giá trị mà người gọi hiểu theo nghĩa khác. Để đánh giá **tính đúng đắn** (*correctness*), cần xác định chính xác hành vi mà mã đã hứa với người gọi.

**Hợp đồng của phương thức** (*method contract*) mô tả những gì người gọi được phép giả định về **giá trị trả về**, **tác dụng phụ** và **ngoại lệ**, trong các điều kiện đầu vào và trạng thái đã xác định. Hợp đồng là căn cứ để cài đặt, kiểm thử, review và thay đổi mã mà không phá vỡ kỳ vọng của thành phần sử dụng.

Sau bài học, bạn có thể:

- Diễn đạt tiền điều kiện, hậu điều kiện và bất biến của một thao tác.
- Phân biệt hợp đồng về kết quả, trạng thái bị thay đổi và cách báo thất bại.
- Thiết kế hành vi rõ ràng khi phương thức ném ngoại lệ, kể cả trường hợp đã có tác dụng phụ.
- Viết kiểm thử xác nhận **toàn bộ hành vi quan sát được**, thay vì chỉ kiểm tra giá trị `return`.

## 1. Hợp đồng trả lời những câu hỏi nào?

Một phương thức thường có hai khả năng kết thúc: **trả về bình thường** hoặc **kết thúc bằng ngoại lệ**. Trong cả hai trường hợp, mã có thể đã tạo ra tác động quan sát được.

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ với thao tác thêm hàng vào giỏ |
| --- | --- | --- |
| **Tiền điều kiện** (*precondition*) | Đầu vào và trạng thái nào được chấp nhận? | Số lượng phải dương; đơn giá không âm |
| **Kết quả** (*result*) | Khi thành công, trả về gì; đơn vị và ý nghĩa là gì? | Tổng tiền mới, tính bằng VND |
| **Tác dụng phụ** (*side effect*) | Khi thành công, trạng thái hoặc thế giới bên ngoài thay đổi ra sao? | Tổng tiền và số lượng trong giỏ tăng |
| **Ngoại lệ** (*exception*) | Khi nào thất bại, báo lỗi gì? | Đối số sai hoặc phép tính vượt miền số |
| **Bảo đảm khi thất bại** | Nếu có ngoại lệ, phần nào đã thay đổi, phần nào vẫn giữ nguyên? | Giỏ hàng không thay đổi nếu thao tác không hoàn tất |
| **Bất biến** (*invariant*) | Điều gì phải đúng trước và sau mọi thao tác hợp lệ? | Tổng tiền và số lượng không âm |

Có thể diễn đạt hợp đồng ngắn gọn:

```text
Nếu tiền điều kiện được thỏa mãn
    và thao tác trả về bình thường:
        hậu điều kiện phải đúng.

Nếu thao tác thất bại:
    ngoại lệ hoặc kết quả lỗi phải tuân theo quy ước,
    đồng thời trạng thái sau lỗi phải đáp ứng mức bảo đảm đã công bố.
```

**Tiền điều kiện không tự quy định cách xử lý đầu vào sai.** Hợp đồng cần nói rõ phương thức sẽ ném ngoại lệ, trả kết quả lỗi, hay coi đó là hành vi nằm ngoài phạm vi bảo đảm. Với API được sử dụng rộng rãi, nên xác định trường hợp này một cách minh bạch.

Hợp đồng khác với chi tiết cài đặt: người gọi cần biết *điều gì được bảo đảm*, không nhất thiết cần biết thuật toán sử dụng vòng lặp, stream hay cấu trúc dữ liệu nào.

## 2. Hợp đồng về kết quả trả về

### 2.1. Kết quả cần có nghĩa xác định

Xét một phương thức tính số tiền cần thanh toán sau khi áp dụng giảm giá:

```java
public static long calculatePayableVnd(long subtotalVnd, long discountVnd) {
    if (subtotalVnd < 0L || discountVnd < 0L || discountVnd > subtotalVnd) {
        throw new IllegalArgumentException("Invalid subtotal or discount");
    }
    return subtotalVnd - discountVnd;
}
```

Có thể mô tả hợp đồng như sau:

- **Tiền điều kiện hợp lệ:** `subtotalVnd >= 0` và `0 <= discountVnd <= subtotalVnd`.
- **Kết quả thành công:** `payableVnd = subtotalVnd - discountVnd`; đơn vị là đồng Việt Nam.
- **Hậu điều kiện:** `0 <= payableVnd <= subtotalVnd`.
- **Tác dụng phụ:** không thay đổi trạng thái dùng chung, không ghi dữ liệu, không gọi dịch vụ khác.
- **Ngoại lệ:** ném `IllegalArgumentException` khi đối số vi phạm điều kiện đã nêu; không có tác dụng phụ trước khi ném.

Với miền đầu vào hợp lệ trên, phép trừ không tràn kiểu `long`: hai toán hạng không âm và số trừ không lớn hơn số bị trừ. Nhưng nhận định này chỉ đúng **trong phạm vi hợp đồng đã nêu**. Nếu sau đó hàm phải xử lý tiền âm để biểu diễn hoàn trả, hợp đồng và cách tính cần được thiết kế lại.

### 2.2. Giá trị đặc biệt phải được quy định rõ

Một API tìm kiếm người dùng có thể chọn:

```java
Optional<User> findUserById(String userId);
```

Trong thiết kế này, `Optional.empty()` có thể được quy ước là **không tìm thấy**, còn lỗi kết nối kho dữ liệu là một thất bại riêng. Nhưng phải công bố quy ước đó; không thể suy ra rằng mọi `Optional.empty()` đều là tình huống bình thường ở mọi API.

Cần xác định rõ ý nghĩa của các trường hợp dễ nhầm:

| Giá trị hoặc tình huống | Câu hỏi hợp đồng phải làm rõ |
| --- | --- |
| `null` | Có được phép trả về không; nếu có, biểu thị điều gì? |
| Danh sách rỗng | “Không có dữ liệu” hay “không tải được dữ liệu”? |
| `false` | Từ chối hợp lệ, không tìm thấy, hay lỗi thực thi? |
| `0` | Số lượng thực sự bằng 0 hay mã báo lỗi? |
| `Optional.empty()` | Chỉ là không tìm thấy hay còn bao gồm trạng thái khác? |
| Giá trị tiền hoặc thời gian | Đơn vị, quy tắc làm tròn và giới hạn miền giá trị là gì? |

Không có một dạng trả về đúng cho mọi trường hợp. Điều quan trọng là **tránh một giá trị mang nhiều nghĩa không phân biệt được** và giữ nhất quán giữa tài liệu, tên phương thức và hành vi thực tế.

### 2.3. Thuộc tính của đối tượng trả về cũng là hợp đồng

Khi trả về danh sách, bản đồ hoặc đối tượng, cần cân nhắc người gọi có được sửa chúng không. Ví dụ:

```java
public List<String> getSupportedRegions() {
    return List.copyOf(supportedRegions);
}
```

`List.copyOf(...)` tạo một danh sách không cho phép thêm, xóa hoặc thay thế phần tử qua tham chiếu trả về. Tuy nhiên, tính không thể sửa của **cấu trúc danh sách** không tự động làm các phần tử bên trong bất biến nếu đó là đối tượng có thể thay đổi. Trong ví dụ `String` là bất biến nên rủi ro này không phát sinh theo cách đó.

Nếu phương thức trả về tham chiếu trực tiếp đến cấu trúc nội bộ có thể sửa, việc sửa danh sách ở phía người gọi có thể trở thành một tác dụng phụ ngoài ý muốn. Hợp đồng nên nói rõ quyền sở hữu và khả năng thay đổi của dữ liệu trả về.

## 3. Hợp đồng về tác dụng phụ

**Tác dụng phụ** là những thay đổi quan sát được ngoài giá trị trả về: cập nhật trường của đối tượng, sửa collection truyền vào, ghi cơ sở dữ liệu, gửi thông điệp, gọi hệ thống thanh toán, tạo tệp hoặc phát sự kiện.

So sánh:

```java
long newTotalVnd = currentTotalVnd + lineAmountVnd;
```

với:

```java
order.setTotalVnd(order.getTotalVnd() + lineAmountVnd);
orderRepository.save(order);
eventPublisher.publishOrderUpdated(order.getId());
```

Đoạn đầu chỉ tính một giá trị trong phạm vi biểu thức. Đoạn sau có thể thay đổi đối tượng `order`, lưu dữ liệu và phát thông điệp. Để xác minh tính đúng đắn của đoạn thứ hai, kiểm tra `order.getTotalVnd()` thôi là chưa đủ.

### 3.1. Làm rõ cái gì được thay đổi và thay đổi khi nào

Một hợp đồng cho thao tác `confirmOrder(orderId)` có thể phải nói rõ:

1. Đơn hàng chỉ được chuyển từ `PENDING` sang `CONFIRMED` khi thỏa điều kiện nào.
2. Có ghi thời điểm xác nhận, giữ chỗ tồn kho hoặc phát sự kiện không.
3. Nếu gọi hai lần với cùng đơn hàng, lần thứ hai có trả kết quả như lần đầu, bỏ qua, hay báo lỗi.
4. Nếu lưu trạng thái thành công nhưng phát sự kiện thất bại, hệ thống ghi nhận và xử lý ra sao.

Ở đây, **thứ tự** và **số lần** tác động có thể quan trọng ngang với giá trị trả về.

### 3.2. Phân biệt hàm không có tác dụng phụ và thao tác thay đổi trạng thái

Một hàm thuần (*pure function*) cho cùng đầu vào sẽ cho cùng kết quả và không tạo ra tác dụng phụ quan sát được. Các phép tính giá trị thuần thường dễ kiểm thử và suy luận hơn.

Tuy nhiên, không phải nghiệp vụ nào cũng có thể hoặc nên viết hoàn toàn thuần. Lưu đơn hàng, gửi email và cập nhật tồn kho đều cần tác dụng phụ. Chất lượng ở đây phụ thuộc vào việc **làm rõ, giới hạn và kiểm soát** tác dụng phụ, thay vì chỉ cố loại bỏ chúng.

### 3.3. Tính lặp lại an toàn (*idempotency*)

Một thao tác được gọi là *idempotent* khi thực hiện lại cùng thao tác không làm thay đổi kết quả trạng thái theo cách khác với thực hiện một lần, trong những điều kiện đã xác định. Ví dụ “đặt trạng thái đơn hàng thành `CANCELLED`” có thể được thiết kế idempotent; “trừ thêm 10.000 đồng” thì thông thường không.

Idempotency đặc biệt quan trọng khi một yêu cầu có thể được gửi lại sau timeout. **Idempotent về trạng thái không nhất thiết đồng nghĩa mọi phản hồi đều giống hệt nhau**; API cần mô tả riêng kết quả trả về và ngoại lệ của lần gọi lặp.

## 4. Hợp đồng về ngoại lệ

Ngoại lệ là một phần của giao diện hành vi. Người gọi phải biết **lỗi nào có thể xuất hiện, lỗi đó có nghĩa gì và trạng thái hệ thống còn bảo đảm điều gì**.

Trong Java, có thể gặp:

| Tình huống | Cách biểu diễn thường gặp | Điểm cần làm rõ |
| --- | --- | --- |
| Tham số vi phạm điều kiện API | `IllegalArgumentException` | Tham số nào không hợp lệ; có phát sinh tác dụng phụ không |
| Trạng thái hiện tại không cho phép thao tác | `IllegalStateException` hoặc ngoại lệ nghiệp vụ | Ví dụ đơn hàng đã khóa; thao tác có bị từ chối hoàn toàn không |
| Tính toán số nguyên vượt giới hạn | `ArithmeticException` | Có thể gây thay đổi một phần dữ liệu trước khi lỗi không |
| Không tìm thấy bản ghi trong thao tác tìm kiếm | `Optional.empty()` hoặc một lỗi được quy ước | “Không có” có phải một kết quả nghiệp vụ hợp lệ không |
| I/O hoặc phụ thuộc bên ngoài gặp sự cố | Ngoại lệ phù hợp với API, có thể là checked hoặc unchecked | Có thể thử lại không; yêu cầu trước đó đã được hệ thống ngoài xử lý chưa |

**Checked exception** (ví dụ `IOException`) phải được khai báo hoặc xử lý theo quy tắc biên dịch Java; **unchecked exception** (ví dụ `IllegalArgumentException`) thì không bắt buộc khai báo trong `throws`. Đây là khác biệt về cơ chế ngôn ngữ, **không phải căn cứ duy nhất** để quyết định cách diễn đạt lỗi. Việc chọn kiểu ngoại lệ phải phù hợp với khả năng người gọi xử lý và phong cách API.

Một vài nguyên tắc:

- Không dùng ngoại lệ cho một kết quả bình thường nếu một giá trị kết quả rõ nghĩa sẽ dễ sử dụng hơn; nhưng một lỗi vi phạm hợp đồng vẫn có thể cần ngoại lệ.
- Không bắt `Exception` rồi âm thầm bỏ qua khi người gọi cần biết thao tác đã thất bại.
- Không chuyển mọi lỗi về `null` hoặc `false` nếu cách đó xóa mất sự khác biệt giữa các nguyên nhân.
- Khi bọc ngoại lệ, nên giữ lại nguyên nhân gốc bằng `cause` nếu nó phục vụ việc chẩn đoán, đồng thời không làm lộ chi tiết nhạy cảm qua thông điệp công khai.
- Không tuyên bố “thất bại thì không có tác dụng phụ” nếu chưa kiểm soát được toàn bộ đường đi của thao tác.

## 5. Ba mức bảo đảm về trạng thái khi xảy ra ngoại lệ

Trong những hệ thống có trạng thái, điều quan trọng không chỉ là *có ném lỗi hay không*, mà còn là *trạng thái sau khi ném lỗi*.

| Kiểu bảo đảm | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| **Không làm hỏng bất biến** (*basic guarantee*) | Đối tượng vẫn hợp lệ và có thể tiếp tục sử dụng, dù một số trạng thái đã thay đổi | Xử lý được một phần lô dữ liệu rồi báo lỗi, các phần đã xử lý vẫn hợp lệ |
| **Không thay đổi trạng thái khi thất bại** (*strong guarantee*) | Thao tác thất bại có tác động tương đương như chưa thực hiện, trong phạm vi trạng thái đã cam kết | Tính xong tất cả giá trị mới trước khi cập nhật giỏ; nếu tràn số, giỏ giữ nguyên |
| **Không phát sinh ngoại lệ** (*no-throw guarantee*) | Thao tác theo thiết kế không để ngoại lệ thoát ra trong điều kiện đã nêu | Một phương thức thao tác bộ nhớ đơn giản được thiết kế để luôn hoàn thành trong miền hợp lệ |

Đây là **những cách mô tả mức bảo đảm**, không phải cơ chế Java tự động cung cấp cho mọi phương thức. Mức bảo đảm phải xét cả tác dụng phụ ngoài đối tượng nếu phương thức có gọi dịch vụ khác.

Trong ứng dụng thực tế, việc bảo đảm không ném bất kỳ ngoại lệ nào dưới mọi điều kiện có thể không khả thi (ví dụ lỗi nghiêm trọng của JVM). Vì vậy, không nên hứa một bảo đảm tuyệt đối khi không thể thực hiện hoặc xác minh nó.

## 6. Ví dụ Java hoàn chỉnh: giỏ hàng và hợp đồng nhất quán

Giả sử có một lớp lưu tổng tiền và tổng số sản phẩm của giỏ. Quy tắc nghiệp vụ ví dụ:

- Đơn giá tính bằng VND và không âm.
- Số lượng thêm vào phải **lớn hơn 0**.
- Khi thêm thành công, tổng tiền tăng bằng `unitPriceVnd * quantity` và tổng số sản phẩm tăng bằng `quantity`.
- Nếu đối số không hợp lệ hoặc phép tính số nguyên vượt phạm vi, **cả hai trường trạng thái đều giữ nguyên**.
- Các phương thức truy cập trên cùng đối tượng được đồng bộ để tránh xen kẽ giữa các lệnh thêm và đọc trạng thái.

### 6.1. Một cách viết dễ tạo trạng thái sai

```java
public long addItem(long unitPriceVnd, int quantity) {
    totalItems += quantity;
    totalVnd += unitPriceVnd * quantity;
    return totalVnd;
}
```

Đoạn này chưa kiểm tra đầu vào âm, có thể tràn số nguyên âm thầm và có thể tăng số lượng ngay cả khi tính tiền gặp vấn đề. Nó chưa thể hiện hợp đồng rõ ràng cho tình huống thất bại.

### 6.2. Tính và kiểm tra trước, cập nhật sau

```java
public final class CartTotals {
    private long totalVnd;
    private int totalItems;

    /**
     * Thêm một nhóm sản phẩm và trả về tổng tiền mới (VND).
     *
     * <p>Khi thành công, tổng tiền và số lượng sản phẩm được tăng tương ứng.
     * Nếu phương thức ném một trong các ngoại lệ đã nêu, hai trường trạng thái
     * không thay đổi.</p>
     *
     * @param unitPriceVnd đơn giá không âm, tính bằng VND
     * @param quantity số sản phẩm cần thêm, phải lớn hơn 0
     * @return tổng tiền mới sau khi thêm thành công
     * @throws IllegalArgumentException nếu đơn giá âm hoặc số lượng không dương
     * @throws ArithmeticException nếu phép nhân hoặc cộng vượt miền số nguyên
     */
    public synchronized long addItem(long unitPriceVnd, int quantity) {
        if (unitPriceVnd < 0L || quantity <= 0) {
            throw new IllegalArgumentException("Invalid price or quantity");
        }

        long lineTotalVnd = Math.multiplyExact(unitPriceVnd, (long) quantity);
        long updatedTotalVnd = Math.addExact(totalVnd, lineTotalVnd);
        int updatedTotalItems = Math.addExact(totalItems, quantity);

        // Chỉ cập nhật sau khi tất cả phép tính đã thành công.
        totalVnd = updatedTotalVnd;
        totalItems = updatedTotalItems;
        return updatedTotalVnd;
    }

    public synchronized long getTotalVnd() {
        return totalVnd;
    }

    public synchronized int getTotalItems() {
        return totalItems;
    }
}
```

Tại sao ví dụ này dễ xác minh hợp đồng hơn?

1. **Giá trị trả về rõ nghĩa:** `addItem(...)` trả về tổng tiền mới sau thao tác thành công, không phải đơn giá hoặc tổng tiền của một dòng hàng.
2. **Tác dụng phụ được giới hạn:** chỉ hai trường `totalVnd` và `totalItems` bị thay đổi. Không có ghi cơ sở dữ liệu hay lời gọi ngoài lớp trong ví dụ.
3. **Các ngoại lệ có chủ đích:** `IllegalArgumentException` cho tham số không hợp lệ và `ArithmeticException` khi phát hiện tràn số bằng `Math.multiplyExact` / `Math.addExact`.
4. **Thất bại không làm đổi trạng thái:** cả ba phép tính đều hoàn tất trước hai phép gán; không có ngoại lệ thông thường nào được dự kiến trong các phép gán trường nguyên thủy.
5. **Bất biến được giữ:** từ trạng thái ban đầu 0 và chỉ dùng phương thức trên để cập nhật, tổng tiền và số lượng không âm; kiểm tra tràn số tránh quay vòng thành số âm.
6. **Đồng bộ nhất quán:** `synchronized` bảo vệ các lời gọi qua cùng đối tượng `CartTotals`, để thao tác thêm và các phương thức đọc không xen kẽ theo cách thấy trạng thái cập nhật dở.

Phạm vi bảo đảm cần được hiểu chính xác: ví dụ không thực hiện giao dịch mạng, không thay đổi trạng thái bên ngoài và không giải quyết nhiều giỏ hàng ở nhiều tiến trình. `synchronized` trên một đối tượng Java **không thay thế** giao dịch cơ sở dữ liệu hay cơ chế đồng bộ phân tán.

### 6.3. Các kịch bản cần kiểm thử

| Kịch bản | Kết quả | Trạng thái |
| --- | --- | --- |
| Thêm 3 sản phẩm, mỗi sản phẩm 15.000 VND | Trả 45.000 VND | `totalVnd = 45000`, `totalItems = 3` |
| Sau đó thêm 2 sản phẩm, mỗi sản phẩm 5.000 VND | Trả 55.000 VND | `totalVnd = 55000`, `totalItems = 5` |
| Đơn giá âm | `IllegalArgumentException` | Giữ nguyên |
| Số lượng bằng 0 | `IllegalArgumentException` | Giữ nguyên |
| Nhân hoặc cộng bị tràn số | `ArithmeticException` | Giữ nguyên |

Ví dụ một số kiểm thử bằng JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CartTotalsTest {
    @Test
    void successfulAddReturnsNewTotalAndUpdatesBothFields() {
        CartTotals cart = new CartTotals();

        assertEquals(45_000L, cart.addItem(15_000L, 3));
        assertEquals(55_000L, cart.addItem(5_000L, 2));
        assertEquals(55_000L, cart.getTotalVnd());
        assertEquals(5, cart.getTotalItems());
    }

    @Test
    void invalidQuantityThrowsAndKeepsState() {
        CartTotals cart = new CartTotals();
        cart.addItem(10_000L, 2);

        assertThrows(IllegalArgumentException.class,
                () -> cart.addItem(500L, 0));

        assertEquals(20_000L, cart.getTotalVnd());
        assertEquals(2, cart.getTotalItems());
    }

    @Test
    void overflowingAdditionThrowsAndKeepsState() {
        CartTotals cart = new CartTotals();
        cart.addItem(Long.MAX_VALUE, 1);

        assertThrows(ArithmeticException.class,
                () -> cart.addItem(1L, 1));

        assertEquals(Long.MAX_VALUE, cart.getTotalVnd());
        assertEquals(1, cart.getTotalItems());
    }
}
```

Các kiểm thử này kiểm tra cả **kết quả thành công**, **ngoại lệ** và **trạng thái sau ngoại lệ**. Chúng là những ví dụ đại diện, chưa chứng minh mọi trường hợp. Nếu triển khai trong dự án thật, cần xét thêm các yêu cầu liên quan đến concurrency, giới hạn nghiệp vụ về số lượng và những thành phần khác sử dụng lớp.

## 7. Ngoại lệ sau tác dụng phụ: trường hợp giao tiếp nhiều hệ thống

Xem luồng đơn giản hóa:

```java
paymentGateway.charge(orderId, payableVnd);
orderRepository.markPaid(orderId);
```

Nếu `charge(...)` đã thu tiền thành công nhưng `markPaid(...)` ném ngoại lệ, phương thức bao quanh có thể thất bại trong khi **tiền vẫn đã bị thu**. Nếu `charge(...)` bị timeout, người gọi cũng chưa chắc biết cổng thanh toán đã xử lý yêu cầu hay chưa.

Vì thế, hợp đồng của thao tác thanh toán phải nói rõ:

- Kết quả “thành công” có nghĩa là đã thu tiền, đã ghi đơn hàng hay cả hai?
- Nếu phương thức ném ngoại lệ, có thể đã thu tiền không?
- Gọi lại với cùng `orderId` và khóa idempotency có thể tạo giao dịch trùng không?
- Khi trạng thái thanh toán và đơn hàng không đồng bộ, cơ chế đối soát và phục hồi là gì?

Chỉ đưa hai lệnh trên vào một `try/catch` không khiến chúng trở thành một giao dịch nguyên tử. Transaction của cơ sở dữ liệu cũng không tự hoàn tác tác dụng đã xảy ra tại cổng thanh toán bên ngoài. Tùy hệ thống, có thể cần **khóa idempotency, ghi nhận trạng thái bền vững, đối soát, retry có kiểm soát hoặc thao tác bù**; tất cả phải được thiết kế theo giao thức và rủi ro thực tế.

Đối với API có tác dụng phụ bên ngoài, đôi khi không thể hứa “ném ngoại lệ là chưa làm gì”. **Một hợp đồng trung thực về trạng thái chưa chắc chắn** giúp người gọi lựa chọn bước xử lý an toàn hơn một lời hứa sai.

## 8. Viết tài liệu hợp đồng cho phương thức Java

Một hợp đồng thực dụng có thể xuất hiện trong Javadoc, tài liệu API, đặc tả nghiệp vụ hoặc kiểm thử. Điều quan trọng là những nguồn này phải nhất quán.

Khi viết Javadoc, có thể dùng cấu trúc:

```java
/**
 * Tính số tiền phải trả sau giảm giá, đơn vị VND.
 *
 * <p>Đầu vào hợp lệ khi subtotalVnd >= 0 và
 * 0 <= discountVnd <= subtotalVnd. Không thay đổi trạng thái.</p>
 *
 * @param subtotalVnd tổng tiền hàng trước khoản giảm đang xét
 * @param discountVnd khoản giảm áp dụng
 * @return subtotalVnd - discountVnd, trong khoảng [0, subtotalVnd]
 * @throws IllegalArgumentException nếu đầu vào không hợp lệ
 */
public static long calculatePayableVnd(long subtotalVnd, long discountVnd) {
    if (subtotalVnd < 0 || discountVnd < 0 || discountVnd > subtotalVnd) {
        throw new IllegalArgumentException("Invalid subtotal or discount");
    }
    return subtotalVnd - discountVnd;
}
```

Cần bảo đảm mô tả **chỉ hứa những gì mã thực sự làm**. Nếu một phương thức chuyển sang có ghi dữ liệu, trả về `Optional` thay vì `null`, hoặc thay loại ngoại lệ, đây có thể là thay đổi hợp đồng ảnh hưởng đến người gọi. Khi sửa API công khai, nên kiểm tra các nơi sử dụng và quy tắc tương thích trước khi phát hành.

Tài liệu không cần dài cho một phương thức hiển nhiên. Nhưng hợp đồng càng có rủi ro lớn hoặc hành vi thất bại càng khó suy luận, càng cần nói rõ kết quả và tác dụng phụ.

## 9. Kiểm thử tính đúng đắn theo hợp đồng

Một chiến lược kiểm thử tốt phải xuất phát từ **điều được hứa**, thay vì viết bài kiểm tra chỉ vì biết cách cài đặt.

| Phần hợp đồng | Câu hỏi kiểm thử | Ví dụ |
| --- | --- | --- |
| Tiền điều kiện | Đầu vào đúng và sai được xử lý như đã mô tả không? | Số lượng 0 bị từ chối |
| Kết quả | Giá trị trả về có đúng nghĩa, đơn vị và miền không? | Tổng tiền mới = tổng cũ + tiền dòng hàng |
| Tác dụng phụ | Chính xác những trạng thái nào thay đổi? | Cả số lượng và tổng tiền cùng được tăng |
| Ngoại lệ | Kiểu và hoàn cảnh xuất hiện có đúng không? | Tràn số sinh `ArithmeticException` |
| Trạng thái sau thất bại | Có giữ được mức bảo đảm đã hứa không? | Khi tràn số, giỏ giữ nguyên |
| Bất biến | Điều kiện cốt lõi có đúng sau mỗi thao tác không? | Không có tổng tiền hoặc số lượng âm |
| Tương tác | Các hệ thống khác nhìn thấy kết quả phù hợp không? | Tiền thu khớp tiền lưu trong đơn hàng |

Nên kiểm tra trường hợp biên (0, ngưỡng vừa đủ, vượt ngưỡng một đơn vị), trạng thái chuyển tiếp, đầu vào bất thường và tình huống phụ thuộc lỗi khi chúng có liên quan. Với hành vi phụ thuộc môi trường, cần nêu rõ phạm vi bằng chứng: một unit test không chứng minh tính nguyên tử của giao dịch liên dịch vụ.

### Kiểm thử bất biến qua nhiều thao tác

Ngoài việc thử từng phương thức độc lập, có thể chạy một chuỗi thao tác hợp lệ rồi kiểm tra bất biến sau mỗi bước. Ví dụ, tổng số lượng trong `CartTotals` không được giảm khi chỉ có thao tác thêm; tổng tiền không âm và không được giảm nếu mọi đơn giá đều không âm. Những thuộc tính này hữu ích khi số lượng kịch bản vượt quá một danh sách ví dụ cố định.

## 10. Những ngộ nhận và lỗi thiết kế thường gặp

### “Có kết quả đúng là phương thức đúng”

Chưa đủ. Một thao tác có thể trả đúng số tiền nhưng ghi hai bản ghi thanh toán hoặc để đối tượng vào trạng thái mâu thuẫn.

### “Ném ngoại lệ nghĩa là chưa có gì xảy ra”

Chỉ đúng khi hợp đồng thực sự bảo đảm điều đó. Một lời gọi mạng có thể thành công ở phía nhận trước khi phía gửi gặp timeout.

### “Bắt tất cả ngoại lệ rồi trả về giá trị mặc định sẽ làm API dễ dùng”

Cách này dễ đánh đồng lỗi với kết quả hợp lệ. Ví dụ trả `0` sau lỗi tính tiền có thể bị hiểu là đơn hàng miễn phí. Cần phân biệt đúng những trạng thái mà người gọi phải xử lý.

### “Không cần nói rõ tác dụng phụ vì tên phương thức đã đủ”

Tên `saveOrder()` có thể gợi ý ghi dữ liệu, nhưng không nói rõ có phát sự kiện, giữ tồn kho hay có thể ghi một phần khi thất bại. Người gọi cần hợp đồng cho những tác động có ý nghĩa.

### “Đổi kiểu ngoại lệ chỉ là refactor nội bộ”

Người gọi có thể dựa vào loại ngoại lệ để hiển thị thông báo, retry hoặc rollback. Thay đổi cách báo lỗi có thể phá hợp đồng ngay cả khi kết quả thành công không đổi.

### “Hợp đồng càng chặt càng tốt”

Hợp đồng nên chính xác, nhưng không nên hứa các chi tiết cài đặt không cần thiết. Nếu một API hứa thứ tự phần tử dù nghiệp vụ không đòi hỏi, việc đổi cấu trúc dữ liệu sau này có thể trở thành thay đổi không tương thích. Chỉ cam kết những đặc tính người gọi cần để sử dụng đúng.

## 11. Bài tập: phát hiện vi phạm hợp đồng

Giả sử ví điện tử có số dư không âm. Một phương thức rút tiền được viết như sau:

```java
long withdraw(long amountVnd) {
    balanceVnd -= amountVnd;
    if (balanceVnd < 0) {
        throw new IllegalStateException("Insufficient balance");
    }
    return balanceVnd;
}
```

Hãy phân tích:

1. Khi `amountVnd > balanceVnd` trước khi gọi, phương thức sẽ ném ngoại lệ nhưng trạng thái bị thay đổi ra sao?
2. Nếu `amountVnd` âm, phép trừ sẽ có ý nghĩa gì? Hợp đồng nên quy định thế nào?
3. Khi phép trừ kiểu `long` bị tràn số, hành vi có còn đúng không?
4. Hãy viết lại để **kiểm tra trước khi cập nhật**; nêu rõ kiểu ngoại lệ cho số tiền không hợp lệ và thiếu số dư.
5. Viết ba nhóm kiểm thử: thành công, đầu vào không hợp lệ, số dư không đủ. Ở hai trường hợp lỗi, kiểm tra số dư giữ nguyên.

Giả sử đối tượng chỉ được truy cập tuần tự trong bài tập. Nếu hỗ trợ nhiều luồng hoặc lưu số dư ở cơ sở dữ liệu, cần bổ sung hợp đồng đồng thời và bảo đảm cập nhật nguyên tử phù hợp với hệ thống đó.

Một thiết kế hợp đồng có thể phát biểu:

> Với `amountVnd > 0` và `balanceVnd >= amountVnd`, thao tác trả số dư mới và trừ số tiền đúng một lần. Với số tiền không dương, ném `IllegalArgumentException`; với số dư không đủ, ném `IllegalStateException`. Trong hai tình huống thất bại này, số dư không thay đổi.

Thông qua bài tập, hãy phân biệt ba câu hỏi: **trả về gì khi thành công**, **thay đổi gì** và **điều gì còn đúng khi thất bại**. Đây là ba mặt phải được kiểm tra cùng nhau.

## Ghi nhớ

Tính đúng đắn của một phương thức là sự phù hợp với **toàn bộ hợp đồng quan sát được**: tiền điều kiện, kết quả, tác dụng phụ, ngoại lệ, bất biến và bảo đảm khi thất bại. Hãy viết hợp đồng đủ rõ để người gọi biết cách sử dụng, người review biết điều cần đối chiếu và kiểm thử có thể chứng minh các hành vi quan trọng. Khi thay đổi mã, kiểm tra cả những điều mã trả về **lẫn những điều mã đã làm**.
