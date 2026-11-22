# Ngăn lỗi lan rộng và giữ trạng thái nhất quán

Giả sử người dùng đặt mua một sản phẩm còn đúng một chiếc trong kho. Hệ thống trừ tồn kho, gọi cổng thanh toán, cập nhật trạng thái đơn hàng rồi gửi thông báo. Nếu cổng thanh toán chậm hoặc một câu lệnh lưu dữ liệu thất bại giữa chừng, điều gì sẽ xảy ra? Đơn có thể được báo thành công dù chưa thanh toán; tồn kho có thể bị trừ hai lần; hoặc lỗi của một dịch vụ ngoài khiến toàn bộ yêu cầu bị treo.

**Độ tin cậy của mã nguồn không chỉ là ít phát sinh lỗi; nó còn là khả năng giới hạn tác động của lỗi và giữ dữ liệu ở trạng thái hợp lệ khi lỗi xảy ra.** Đây là một thuộc tính quan trọng trong `CODE_QUALITY_FUNDAMENTALS`: mã đáng tin cậy phải cho người bảo trì thấy rõ bất biến nghiệp vụ, ranh giới lỗi và hành vi khôi phục. Các quy tắc này đồng thời giúp mã dễ hiểu và dễ thay đổi mà không tạo ra lỗi dây chuyền.

Sau bài học, bạn có thể:

- Nhận diện lỗi bị lan rộng giữa các thành phần và trạng thái không nhất quán do xử lý dở dang.
- Xác định bất biến (*invariant*) và ranh giới cần bảo vệ khi cập nhật dữ liệu.
- Áp dụng kiểm tra đầu vào, giao dịch, giới hạn thời gian, cô lập phụ thuộc và xử lý lỗi có chủ đích.
- Hiểu vai trò, giới hạn của retry, idempotency, outbox và cơ chế bù trừ.
- Viết tình huống kiểm thử để xác nhận hệ thống vẫn có hành vi đúng khi một bước thất bại.

## 1. Hai dạng tác hại cần ngăn chặn

### Lỗi lan rộng (*failure propagation*)

Lỗi lan rộng xảy ra khi một sự cố trong thành phần A làm các thành phần không trực tiếp liên quan cũng không thể phục vụ công việc của mình. Ví dụ:

1. Dịch vụ gửi email phản hồi rất chậm.
2. Luồng tạo đơn hàng đợi gửi email đồng bộ, không có thời hạn chờ.
3. Các luồng xử lý yêu cầu bị chiếm giữ ngày càng nhiều.
4. Hệ thống không còn đủ tài nguyên để nhận đơn mới, dù cơ sở dữ liệu và quy tắc đặt hàng vẫn hoạt động.

Sự cố ban đầu ở chức năng phụ đã trở thành sự cố của chức năng chính. Một số hình thức lan rộng phổ biến gồm timeout dây chuyền, chiếm hết thread/connection, hàng đợi tăng không giới hạn, retry dồn dập, lỗi runtime bị ném xuyên qua các tầng không có xử lý phù hợp và dữ liệu lỗi truyền sang hệ thống khác.

### Trạng thái không nhất quán (*inconsistent state*)

Trạng thái không nhất quán là trạng thái vi phạm quy tắc mà hệ thống cần duy trì. Ví dụ:

- Tồn kho còn lại là `-1` dù ứng dụng không cho phép bán quá số lượng hiện có.
- Đơn hàng mang trạng thái `PAID` nhưng không có bằng chứng thanh toán hợp lệ.
- Tiền đã trừ ở tài khoản nguồn nhưng chưa ghi tăng vào tài khoản đích.
- Một mã yêu cầu được xử lý hai lần, tạo hai lệnh thu tiền.

Hệ thống có thể bị không nhất quán **ngay cả khi mọi thành phần đều chạy nhanh**: chỉ cần thứ tự cập nhật sai, thiếu transaction, kiểm tra cạnh tranh không nguyên tử hoặc xử lý lặp mà không nhận ra.

| Góc nhìn | Lỗi lan rộng | Trạng thái không nhất quán |
| --- | --- | --- |
| Câu hỏi chính | “Một lỗi có kéo hỏng chức năng khác không?” | “Sau lỗi, dữ liệu còn thỏa quy tắc không?” |
| Ví dụ | Gửi email chậm làm nghẽn tạo đơn | Đơn được đánh dấu giao thành công khi chưa trừ kho |
| Biện pháp thường dùng | Timeout, cô lập tài nguyên, giới hạn tải, degrade có kiểm soát | Bất biến, transaction, chuyển trạng thái hợp lệ, idempotency |
| Rủi ro nếu xử lý sai | Mất khả dụng trên phạm vi rộng | Sai dữ liệu, khó đối soát, mất niềm tin |

Hai vấn đề liên quan nhau nhưng cần phân tích riêng. Timeout ngăn một lời gọi treo quá lâu, **không tự hoàn tác** các thay đổi mà lời gọi đã thực hiện. Transaction giúp nhiều thao tác dữ liệu cùng thành công hoặc cùng thất bại, **không tự bảo vệ** ứng dụng khỏi cạn tài nguyên do quá nhiều yêu cầu đồng thời.

## 2. Bắt đầu từ bất biến và ranh giới nghiệp vụ

Một **bất biến** là điều kiện phải đúng tại các thời điểm quan sát hợp lệ của hệ thống. Ví dụ với kho hàng:

- Số lượng khả dụng không âm.
- Mỗi mã yêu cầu giữ hàng chỉ ghi nhận một lần.
- Tổng số lượng khả dụng và số lượng đã giữ không vượt nguồn hàng được quản lý (nếu không có nghiệp vụ nhập/xuất bổ sung).

Với đơn hàng:

- Đơn `CANCELED` không thể được giao.
- Chuyển sang `PAID` cần dựa vào kết quả thanh toán đã được xác nhận.
- Mọi thay đổi trạng thái đều phải tuân theo những chuyển trạng thái được cho phép.

Hãy diễn đạt bất biến dưới dạng có thể kiểm chứng, thay vì ghi chung chung “dữ liệu phải đúng”. Từ đó, xác định **ranh giới nhất quán**: những thay đổi nào buộc phải được chấp nhận hoặc từ chối như một đơn vị?

Ví dụ, khi chuyển 200.000 đồng giữa hai tài khoản ở **cùng một cơ sở dữ liệu hỗ trợ transaction**, việc trừ và cộng tiền nên thuộc cùng một transaction. Ngược lại, ghi đơn hàng vào database và gửi email qua mạng là hai hệ thống độc lập; một database transaction không làm cho email tự động được hoàn tác.

Một công thức rà soát hữu ích:

> Trước thao tác, bất biến nào phải đúng? Sau khi thao tác thành công, bất biến nào phải đúng? Nếu thất bại ở **bất kỳ bước nào**, hệ thống được phép ở trạng thái nào?

Không phải mọi dữ liệu liên quan đều cần nhất quán tức thời. Ví dụ trạng thái đơn hàng là nguồn sự thật quan trọng, còn số lượt xem sản phẩm có thể cập nhật muộn. Việc chọn mức nhất quán phải bắt nguồn từ yêu cầu nghiệp vụ và hậu quả khi thông tin chậm đồng bộ.

## 3. Kiểm tra tại ranh giới và xử lý lỗi minh bạch

Giới hạn tác hại của lỗi bắt đầu từ việc không cho dữ liệu không hợp lệ đi sâu vào các bước có tác dụng phụ.

### Validate trước khi thay đổi trạng thái

Một thao tác đặt hàng cần kiểm tra dữ liệu bắt buộc, số lượng dương, mã sản phẩm hợp lệ và quyền thực hiện trước khi ghi đơn, trừ kho hoặc gửi thông báo. Việc validate sớm giúp lỗi rõ nguyên nhân và tránh cập nhật dở dang.

Tuy nhiên, **kiểm tra trước rồi cập nhật sau** có thể vẫn sai khi nhiều yêu cầu chạy đồng thời. Hai request cùng nhìn thấy một sản phẩm còn hàng rồi đều trừ kho. Với dữ liệu chia sẻ, điều kiện kiểm tra và thao tác ghi cần được đồng bộ hoặc thực hiện nguyên tử ở tầng lưu trữ.

### Không “nuốt” lỗi để tạo vẻ thành công

Ví dụ cách xử lý nguy hiểm:

```java
try {
    paymentGateway.charge(payment);
} catch (Exception ignored) {
    // Cho đơn hàng tiếp tục như đã thanh toán.
}
order.markPaid();
```

Lỗi thanh toán đã bị biến thành trạng thái `PAID` sai. Một cách thiết kế rõ hơn là chỉ đánh dấu đã thanh toán khi nhận được xác nhận hợp lệ; với lỗi chưa xác định kết quả, ghi trạng thái chờ đối soát:

```text
Yêu cầu thu tiền
    |
    +-- Xác nhận thành công --> PAID
    |
    +-- Bị từ chối rõ ràng --> PAYMENT_FAILED
    |
    +-- Timeout / kết quả không rõ --> PAYMENT_PENDING_RECONCILIATION
```

Timeout chỉ cho biết phía gọi chưa nhận được kết quả đúng hạn. Cổng thanh toán **có thể đã thực hiện thu tiền** trước khi kết nối bị ngắt. Vì vậy, từ timeout không thể kết luận “chưa thu tiền” để tự ý gửi lại một lệnh mới.

### Phân biệt lỗi theo cách khôi phục

| Loại lỗi | Ví dụ | Hành vi thường phù hợp |
| --- | --- | --- |
| Đầu vào không hợp lệ | Số lượng đặt bằng 0 | Từ chối sớm, trả thông báo có ý nghĩa |
| Xung đột nghiệp vụ | Không đủ tồn kho | Không ghi một phần; trả kết quả xung đột |
| Phụ thuộc tạm thời không khả dụng | Dịch vụ phụ bị gián đoạn | Timeout, thử lại có giới hạn nếu thao tác an toàn |
| Kết quả bên ngoài không xác định | Timeout sau khi gửi yêu cầu thanh toán | Giữ trạng thái chưa chắc chắn, tra cứu hoặc đối soát |
| Lỗi lập trình/bất biến | Trạng thái không thể xảy ra | Báo lỗi rõ, ghi log phù hợp, tránh che giấu bằng giá trị mặc định |

Ngoại lệ nên được xử lý ở nơi có đủ thông tin để đưa ra quyết định. Một tầng repository thường không nên bắt mọi `Exception` rồi trả `null`, vì tầng nghiệp vụ sẽ khó phân biệt “không tìm thấy” với “database không hoạt động”. Khi chuyển ngoại lệ sang kiểu lỗi ứng dụng, giữ lại nguyên nhân gốc để phục vụ chẩn đoán.

Các tài nguyên như `Connection`, `ResultSet`, stream hoặc file cần được đóng đúng cách bằng `try-with-resources`; tránh để lỗi giữa chừng giữ mãi kết nối và gây lan rộng do cạn pool.

## 4. Giữ trạng thái bộ nhớ nhất quán khi có lỗi

Xét dịch vụ giữ hàng trong **một tiến trình Java**. Nếu sửa `available` trước rồi mới tạo bản ghi giữ hàng, một ngoại lệ khi ghi bản ghi có thể khiến số lượng tồn kho giảm mà không biết hàng được giữ cho ai.

Một thiết kế nhỏ, dễ kiểm chứng là **chuẩn bị trạng thái mới đầy đủ rồi thay thế một lần**:

```java
import java.util.HashMap;
import java.util.Map;

record StockState(int available, Map<String, Integer> reservations) {}

final class StockService {
    private StockState state;

    StockService(int initialStock) {
        if (initialStock < 0) {
            throw new IllegalArgumentException("Stock cannot be negative");
        }
        state = new StockState(initialStock, Map.of());
    }

    public synchronized void reserve(String requestId, int quantity) {
        if (requestId == null || requestId.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid reservation");
        }

        StockState current = state;
        Integer previousQuantity = current.reservations().get(requestId);

        if (previousQuantity != null) {
            if (previousQuantity != quantity) {
                throw new IllegalStateException("Request ID reused with different quantity");
            }
            return; // Cùng request ID và cùng nội dung: không giữ hàng lần hai.
        }

        if (current.available() < quantity) {
            throw new IllegalStateException("Insufficient stock");
        }

        Map<String, Integer> nextReservations =
                new HashMap<>(current.reservations());
        nextReservations.put(requestId, quantity);

        StockState next = new StockState(
                current.available() - quantity,
                Map.copyOf(nextReservations)
        );
        state = next;
    }

    public synchronized int available() {
        return state.available();
    }
}
```

Đoạn mã sử dụng Java 17. Một lần giữ hàng có ba tính chất quan trọng:

1. **Kiểm tra bất biến:** số lượng yêu cầu phải dương và không vượt tồn kho.
2. **Chuẩn bị trước khi công bố:** tạo bản sao dữ liệu và `StockState` mới trước khi gán `state`. Ngoại lệ thông thường trong giai đoạn chuẩn bị không làm đổi trạng thái đang dùng.
3. **Đồng bộ truy cập:** `synchronized` bao phủ cả kiểm tra và cập nhật, tránh hai thread cùng giữ vượt số lượng còn lại.

Việc dùng `Map.copyOf` giúp bản đồ đã lưu trong trạng thái mới không bị sửa từ bên ngoài. Với một `requestId` xuất hiện lần hai, hàm trả về mà không trừ thêm hàng; nếu cùng ID nhưng số lượng khác, hàm từ chối vì không thể coi hai yêu cầu là một.

**Giới hạn:** trạng thái này chỉ ở bộ nhớ của một đối tượng trong một tiến trình. Khởi động lại ứng dụng sẽ mất dữ liệu; nhiều instance không chia sẻ cùng khóa `synchronized`. Để bảo vệ tồn kho thật khi có nhiều máy chủ, cần cơ chế nguyên tử tại nơi lưu trữ chung, chẳng hạn transaction và câu lệnh cập nhật có điều kiện trong database.

## 5. Giao dịch database: cập nhật cùng thành công hoặc cùng thất bại

Với hai số dư trong cùng database giao dịch, mục tiêu là:

- Không trừ tiền nếu tài khoản nguồn không đủ số dư.
- Không chỉ trừ một bên khi tài khoản đích không tồn tại.
- Nếu transaction thất bại trước khi commit, những thay đổi trong transaction phải được rollback.

Ví dụ Java với JDBC và một bảng `accounts(id, balance_vnd)`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

final class TransferService {
    private final DataSource dataSource;

    TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    void transfer(long fromId, long toId, long amountVnd) throws SQLException {
        if (fromId <= 0 || toId <= 0 || fromId == toId || amountVnd <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement debit = connection.prepareStatement(
                        "UPDATE accounts SET balance_vnd = balance_vnd - ? " +
                        "WHERE id = ? AND balance_vnd >= ?")) {
                    debit.setLong(1, amountVnd);
                    debit.setLong(2, fromId);
                    debit.setLong(3, amountVnd);
                    if (debit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Source not found or insufficient balance");
                    }
                }

                try (PreparedStatement credit = connection.prepareStatement(
                        "UPDATE accounts SET balance_vnd = balance_vnd + ? " +
                        "WHERE id = ?")) {
                    credit.setLong(1, amountVnd);
                    credit.setLong(2, toId);
                    if (credit.executeUpdate() != 1) {
                        throw new IllegalStateException("Destination not found");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

Ý chính nằm ở ba chỗ:

- Hai lệnh `UPDATE` dùng **cùng connection và transaction**.
- Phép trừ có điều kiện `balance_vnd >= ?` được database đánh giá tại thời điểm cập nhật, tránh kiểu kiểm tra số dư bằng `SELECT` rồi ghi độc lập trong một luồng cạnh tranh.
- Nếu một bước không thực hiện được, thao tác ném lỗi và yêu cầu `rollback()`; chỉ công bố thành công sau `commit()`.

Đây là ví dụ minh họa nguyên lý, cần thêm các biện pháp theo hệ quản trị cơ sở dữ liệu và yêu cầu thực tế: dùng kiểu tiền có giới hạn rõ ràng (ví dụ `DECIMAL/NUMERIC`), ràng buộc `CHECK` khi được hỗ trợ, chính sách khóa/độ cô lập thích hợp, xử lý deadlock và lỗi kết nối, bản ghi giao dịch để đối soát, và bảo vệ khỏi xử lý trùng yêu cầu. Không nên dựa duy nhất vào điều kiện kiểm tra trong Java để thực thi bất biến đồng thời.

**Lưu ý về kết quả không chắc chắn:** nếu kết nối mất ngay khi gửi `commit()`, phía ứng dụng có thể không biết database đã commit thành công hay chưa. Không nên tự động chạy lại lệnh chuyển tiền như một lệnh hoàn toàn mới. Cần định danh yêu cầu duy nhất và đối soát kết quả đã ghi.

Transaction của một database cũng **không tự bao trùm** email, HTTP call, message broker hay database khác. Giữ connection và transaction mở trong lúc gọi mạng lâu có thể khóa dữ liệu, chiếm connection và làm hệ thống kém tin cậy.

## 6. Kiểm soát ranh giới lỗi giữa các thành phần

### 6.1. Timeout: không chờ vô hạn

Mỗi lời gọi tới dịch vụ ngoài cần có thời hạn phù hợp với ngân sách thời gian của yêu cầu phía trên. Nên cân nhắc timeout kết nối, timeout đọc phản hồi và timeout cho toàn bộ công việc, theo khả năng của thư viện sử dụng.

Nếu hệ thống có ngân sách 2 giây để trả kết quả, lời gọi phụ thuộc không thể dùng một timeout 10 giây mà vẫn kỳ vọng đáp ứng mục tiêu đó. Hãy dành thời gian cho xử lý nội bộ và trường hợp thất bại.

Timeout ngăn phía gọi chờ vô hạn nhưng **không chắc đã hủy công việc bên ngoài**. Cần phân biệt “tôi không nhận được kết quả” với “phía kia chắc chắn chưa thực hiện”.

### 6.2. Giới hạn tài nguyên và cô lập tải

Một chức năng phụ bị chậm không nên sử dụng hết thread, connection hay bộ nhớ dành cho chức năng chính. Những kỹ thuật thường dùng:

- Pool thực thi hoặc semaphore riêng cho lời gọi có rủi ro cao (*bulkhead*).
- Giới hạn số công việc đồng thời và độ dài hàng đợi; từ chối sớm khi quá tải.
- Giới hạn số lần thử lại và số lời gọi đang chờ.
- Phân tách xử lý tác dụng phụ không thiết yếu sang công việc bất đồng bộ có giám sát.

Ví dụ: gửi email xác nhận có thể dùng hàng đợi để việc tạo đơn không phải đợi nhà cung cấp email. Nhưng hàng đợi cũng cần giới hạn dung lượng, chính sách xử lý khi đầy và cách theo dõi thông báo chưa gửi. Chuyển sang bất đồng bộ **không tự xóa rủi ro**; nó chuyển rủi ro sang bước vận hành khác.

### 6.3. Circuit breaker và suy giảm chức năng có kiểm soát

Nếu một phụ thuộc liên tục thất bại, *circuit breaker* có thể tạm ngừng gọi mới trong một khoảng thời gian và thử phục hồi có kiểm soát. Cơ chế này hữu ích khi lỗi lặp gây tốn tài nguyên, nhưng cần ngưỡng, thời gian mở và đo lường dựa vào đặc tính thực tế. Nó không thay thế timeout hoặc thiết kế đúng trạng thái.

*Graceful degradation* là giữ lại phần chức năng có thể phục vụ an toàn. Chẳng hạn, nếu dịch vụ gợi ý sản phẩm lỗi, trang sản phẩm vẫn có thể hiển thị mà không có gợi ý. Ngược lại, nếu không xác minh được thanh toán, **không được mặc định coi thanh toán thành công** để tiếp tục giao hàng.

Quy tắc quyết định là: chức năng nào mang tính bổ trợ có thể bỏ qua, và chức năng nào bắt buộc phải thành công để bảo vệ bất biến nghiệp vụ?

## 7. Retry: phục hồi lỗi tạm thời nhưng không nhân đôi tác dụng phụ

Retry có ích khi lỗi có khả năng thoáng qua, như quá tải ngắn hạn hoặc kết nối bị gián đoạn. Tuy nhiên, mỗi lần thử lại tăng tải lên phụ thuộc đang gặp sự cố. Retry thiếu giới hạn có thể tạo “bão retry”, khiến một lỗi nhỏ trở thành lỗi lan rộng.

Một chính sách retry có trách nhiệm cần xác định:

1. **Lỗi nào có thể thử lại:** ví dụ phản hồi quá tải tạm thời; không thử lại đầu vào sai hay lỗi nghiệp vụ chắc chắn.
2. **Có an toàn khi lặp thao tác không:** truy vấn đọc và yêu cầu tạo thanh toán có tính chất rất khác.
3. **Số lần và thời gian tối đa:** mỗi tầng không nên tự nhân số lần retry mà không xét tổng ngân sách.
4. **Khoảng cách giữa các lần:** thường dùng backoff tăng dần và jitter để tránh nhiều client thử lại cùng lúc.
5. **Kết quả cuối cùng:** nếu hết số lần thử, ghi trạng thái phù hợp, báo lỗi rõ và có cơ chế đối soát khi cần.

| Hoạt động | Retry có an toàn? | Lý do |
| --- | --- | --- |
| Đọc dữ liệu không gây tác dụng phụ | Thường có, trong ngân sách | Lặp phép đọc thường không tạo thêm giao dịch |
| Yêu cầu thanh toán mới, không có khóa chống trùng | Không nên retry mù | Kết quả lần đầu có thể đã thành công |
| Gửi lệnh giữ hàng bằng ID duy nhất được lưu bền vững | Có thể, nếu server hỗ trợ idempotency thật sự | Lần lặp trả về kết quả của yêu cầu ban đầu |
| Gửi email | Có thể gửi trùng nếu thử lại | Cần quyết định yêu cầu tránh trùng ở mức nghiệp vụ |
| Lỗi dữ liệu nhập không hợp lệ | Không | Thử lại cùng dữ liệu không giải quyết nguyên nhân |

### Idempotency: lặp lại mà không thực hiện tác dụng phụ lần nữa

Một thao tác *idempotent* khi thực hiện lặp với cùng định danh và nội dung yêu cầu có hiệu quả nghiệp vụ như một lần thực hiện. Ví dụ:

```text
POST /payments
Idempotency-Key: checkout-8fa2
Amount: 200000 VND

Lần 1: xử lý thanh toán và lưu kết quả cho khóa checkout-8fa2
Lần 2: nhận lại cùng khóa + cùng nội dung -> trả kết quả đã ghi
Lần 3: cùng khóa nhưng số tiền khác -> từ chối xung đột
```

Để bảo đảm tính chất này trong nhiều instance, khóa idempotency, trạng thái và kết quả phải được lưu **bền vững** ở phía xử lý, với ràng buộc duy nhất và thao tác nguyên tử phù hợp. Chỉ kiểm tra `if (seenIds.contains(id))` ở bộ nhớ từng máy là không đủ.

Idempotency cần được thiết kế từ đầu đến cuối khi thao tác tác động hệ thống khác: bên gọi có thể lặp, mạng có thể mất phản hồi, hàng đợi có thể phát lại và bên nhận cần nhận diện thông điệp đã xử lý. “Exactly once” theo nghĩa không thể có bất kỳ lần xử lý lặp nào giữa các hệ thống thường không phải điều có thể giả định chỉ nhờ dùng message broker.

## 8. Nhất quán khi công việc vượt qua nhiều hệ thống

### Vấn đề gửi sự kiện sau khi lưu dữ liệu

Xét đoạn xử lý:

```text
1. COMMIT đơn hàng vào database
2. Publish OrderCreated lên message broker
```

Nếu tiến trình dừng sau bước 1, đơn hàng đã tồn tại nhưng sự kiện không được gửi. Đảo thứ tự cũng không giải quyết được: nếu gửi sự kiện trước rồi lưu đơn hàng thất bại, bên nhận có thể xử lý một đơn chưa tồn tại.

### Transactional outbox

Một lựa chọn thường dùng là lưu bản ghi nghiệp vụ và bản ghi thông điệp vào **cùng một transaction trong một database**:

```text
Transaction database:
  +-- INSERT orders (...)
  +-- INSERT outbox_messages (event_id, payload, status)
  +-- COMMIT

Worker độc lập:
  +-- Đọc thông điệp chưa gửi
  +-- Gửi sang broker
  +-- Đánh dấu đã gửi

Consumer:
  +-- Dùng event_id để nhận diện xử lý lặp
  +-- Cập nhật dữ liệu của mình
```

Nhờ transaction, hoặc cả đơn hàng và sự kiện chờ gửi cùng được lưu, hoặc cả hai cùng không được lưu. Worker có thể gửi lại khi gặp lỗi. Nhưng nếu broker đã nhận sự kiện rồi worker hỏng trước khi đánh dấu đã gửi, sự kiện **có thể được gửi lần nữa**. Vì thế consumer vẫn cần xử lý trùng an toàn.

Outbox tăng độ tin cậy nhưng thêm công việc: worker, theo dõi backlog, retry, xử lý thông điệp lỗi và dọn dữ liệu theo chính sách lưu giữ. Chỉ nên đưa cơ chế này vào khi có nhu cầu thực sự bảo đảm liên kết giữa cập nhật dữ liệu và phát thông điệp.

### Quy trình nhiều bước và bù trừ

Khi một giao dịch nghiệp vụ trải qua nhiều dịch vụ độc lập, ta không thể mặc nhiên dùng một transaction database để rollback toàn bộ. Có thể mô hình hóa quy trình với các trạng thái trung gian và hành động bù trừ (*compensation*):

```text
ORDER_CREATED
    |
    v
STOCK_RESERVED
    |
    +-- Thanh toán thành công --> PAID --> FULFILLMENT_READY
    |
    +-- Thanh toán bị từ chối --> RELEASE_STOCK --> CANCELED
    |
    +-- Kết quả chưa rõ --> PAYMENT_PENDING_RECONCILIATION
```

Đây là một phác thảo của quy trình kiểu *Saga*. Bù trừ không phải phép “quay ngược thời gian”: việc hoàn tiền có thể thất bại hoặc bị trì hoãn, và gửi email đã tới khách hàng thì không thể thu hồi. Quy trình phải lưu đủ trạng thái để tiếp tục, thử lại có kiểm soát và đối soát khi cần.

**Nhất quán cuối cùng** (*eventual consistency*) là chấp nhận một số thành phần cập nhật lệch thời điểm nhưng hội tụ về trạng thái đúng theo cơ chế đồng bộ. Điều này không cho phép vi phạm mọi bất biến: các ràng buộc quan trọng như không bán âm tồn kho hoặc không ghi nhận thanh toán khi chưa xác thực vẫn cần được bảo vệ tại điểm sở hữu dữ liệu.

## 9. Chuyển trạng thái rõ ràng để chặn sai lệch nghiệp vụ

Với quy trình đơn hàng, hãy định nghĩa những chuyển trạng thái được phép. Ví dụ:

| Trạng thái hiện tại | Sự kiện hợp lệ | Trạng thái tiếp theo |
| --- | --- | --- |
| `CREATED` | Giữ hàng thành công | `STOCK_RESERVED` |
| `STOCK_RESERVED` | Thanh toán được xác nhận | `PAID` |
| `STOCK_RESERVED` | Thanh toán bị từ chối | `CANCEL_PENDING_RELEASE` |
| `CANCEL_PENDING_RELEASE` | Giải phóng hàng thành công | `CANCELED` |
| `PAID` | Bàn giao cho vận chuyển thành công | `FULFILLING` |

Hệ thống cần từ chối chuyển thẳng `CREATED → FULFILLING` nếu nghiệp vụ bắt buộc giữ hàng và thanh toán trước đó. Trạng thái `CANCEL_PENDING_RELEASE` cho biết đang có công việc bù trừ; ghi ngay `CANCELED` trước khi giải phóng hàng thành công có thể che giấu phần việc chưa hoàn tất.

Khi nhiều worker hoặc nhiều request cùng cố cập nhật một đơn, dùng cơ chế kiểm soát đồng thời như phiên bản bản ghi (*optimistic locking*), update có điều kiện theo trạng thái hoặc transaction với khóa phù hợp. Ví dụ:

```sql
UPDATE orders
SET status = 'PAID', version = version + 1
WHERE id = :order_id
  AND status = 'STOCK_RESERVED'
  AND version = :expected_version;
```

Chỉ số dòng cập nhật bằng 1 cho thấy điều kiện chuyển trạng thái đã khớp. Nếu bằng 0, cần đọc lại và xác định đó là yêu cầu lặp, xung đột hay trạng thái không hợp lệ. Đây là mô tả logic: cú pháp tham số `:order_id` phụ thuộc công cụ truy cập database.

Không nên sửa trạng thái chỉ bằng lệnh cập nhật không điều kiện từ dữ liệu client gửi lên. Client có thể giữ phiên bản cũ hoặc gửi yêu cầu hai lần, trong khi trạng thái thật đã thay đổi.

## 10. Quan sát và kiểm thử khả năng chịu lỗi

Hành vi khi thành công chỉ là một phần của chất lượng mã. Một hệ thống đáng tin cậy cần được kiểm tra ở các điểm có thể thất bại.

### Ma trận tình huống kiểm thử

| Điểm gây lỗi | Điều cần xác nhận |
| --- | --- |
| Dữ liệu đặt hàng sai | Không tạo bản ghi hay trừ kho; lỗi trả về rõ ràng |
| Hai request giữ cùng sản phẩm cuối cùng | Tối đa một request thành công; tồn kho không âm |
| Một bước trong transaction chuyển tiền thất bại | Không chỉ trừ tài khoản nguồn |
| Timeout sau khi gửi lệnh thanh toán | Không tự đánh dấu thành công hoặc gửi thanh toán mới thiếu kiểm soát |
| Gửi thông điệp outbox thất bại | Thông điệp còn được lưu để thử lại |
| Consumer nhận cùng sự kiện hai lần | Tác dụng phụ nghiệp vụ không nhân đôi |
| Dịch vụ gợi ý sản phẩm ngừng hoạt động | Các chức năng cốt lõi vẫn hoạt động trong mức tải cho phép |
| Cạn giới hạn xử lý của dịch vụ phụ | Có từ chối/giảm tải có kiểm soát, không nghẽn toàn bộ ứng dụng |

Ví dụ kiểm thử hành vi cơ bản cho `StockService` (JUnit 5):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class StockServiceTest {
    @Test
    void rejectedReservationDoesNotChangeStock() {
        StockService stock = new StockService(2);

        assertThrows(IllegalStateException.class,
                () -> stock.reserve("order-1", 3));

        assertEquals(2, stock.available());
    }

    @Test
    void repeatedRequestIsAppliedOnce() {
        StockService stock = new StockService(3);

        stock.reserve("order-7", 2);
        stock.reserve("order-7", 2);

        assertEquals(1, stock.available());
        assertThrows(IllegalStateException.class,
                () -> stock.reserve("order-7", 1));
        assertEquals(1, stock.available());
    }
}
```

Các test này xác minh bất biến trong một luồng. Để đánh giá cạnh tranh, bổ sung kiểm thử đồng thời có phối hợp điểm bắt đầu và xác nhận tổng số lần giữ hàng không vượt số lượng ban đầu. Với lưu trữ thật, dùng test tích hợp trên hệ quản trị thực tế để kiểm tra transaction, độ cô lập, khóa và các ràng buộc; không thể suy luận toàn bộ hành vi cạnh tranh chỉ từ unit test mock.

### Log, metric và truy vết

Khi xảy ra lỗi, cần đủ thông tin để xác định công đoạn nào thất bại và liệu nghiệp vụ đã hoàn tất hay chưa:

- Gắn `requestId`, `orderId`, `eventId` hoặc correlation ID phù hợp giữa các tầng.
- Theo dõi tỷ lệ timeout, lỗi theo phụ thuộc, số retry, độ dài hàng đợi, số thông điệp outbox chưa gửi và thời gian xử lý.
- Ghi trạng thái nghiệp vụ trước và sau chuyển đổi quan trọng, cùng nguyên nhân từ chối.
- Đặt cảnh báo cho tồn đọng hoặc bất biến bị vi phạm; đừng chỉ đếm lỗi HTTP 500.

Không ghi mật khẩu, mã truy cập, số thẻ thanh toán hay dữ liệu nhạy cảm vào log. Cũng không cần log cùng một ngoại lệ đầy đủ ở mọi tầng: chọn nơi xử lý hoặc ranh giới thích hợp để ghi, giữ correlation ID và nguyên nhân gốc để tránh nhiễu.

## 11. Những cách sửa lỗi tưởng đúng nhưng làm hệ thống kém tin cậy

**Bắt `Exception` rồi trả kết quả mặc định “thành công”.** Đây là cách che giấu lỗi và làm sai trạng thái. Chỉ dùng fallback nếu giá trị thay thế được nghiệp vụ cho phép và người gọi có thể hiểu ý nghĩa của nó.

**Retry mọi lỗi vô thời hạn.** Điều này tăng tải, che giấu lỗi lập trình và có thể nhân đôi tác dụng phụ. Chọn lỗi có khả năng phục hồi, ngân sách và khóa chống trùng phù hợp.

**Gọi HTTP ngoài trong transaction dài.** Trong lúc chờ mạng, transaction có thể giữ khóa và connection, gây tác động dây chuyền. Tách bước ngoài thành trạng thái và luồng phối hợp riêng khi cần.

**Chỉ kiểm tra điều kiện trong Java rồi tin rằng dữ liệu luôn đúng.** Với nhiều tiến trình, bất biến phải được bảo vệ tại điểm chung sở hữu dữ liệu bằng câu lệnh nguyên tử, khóa, transaction hoặc ràng buộc database.

**Giả định “gửi một lần” nghĩa là “xử lý một lần”.** Khi kết nối mất sau khi phía nhận đã xử lý, phía gửi có thể gửi lại. Cần thiết kế idempotency cho thao tác có tác dụng phụ.

**Đánh đồng timeout với thất bại chắc chắn.** Với thanh toán hay chuyển tiền, kết quả có thể chưa xác định. Cần trạng thái đối soát thay vì tự động thực hiện lại.

**Đồng bộ mọi dữ liệu bằng mọi giá.** Không phải mọi phép cập nhật đều cần transaction phân tán. Cần xác định dữ liệu nào phải nhất quán tức thời và dữ liệu nào được cập nhật muộn theo quy tắc rõ ràng.

## 12. Thực hành ra quyết định theo mức độ rủi ro

Khi đánh giá một luồng nghiệp vụ, có thể làm theo trình tự:

1. **Liệt kê tác dụng phụ:** ghi database, giữ hàng, thu tiền, gửi sự kiện, thông báo.
2. **Viết bất biến:** điều gì không được xảy ra dù có lỗi giữa chừng.
3. **Đánh dấu ranh giới:** thao tác nào chung transaction; phụ thuộc nào là HTTP hoặc message broker; thành phần nào có thể chậm hay ngừng hoạt động.
4. **Chọn cơ chế tối thiểu phù hợp:** validate, đồng bộ/cập nhật nguyên tử, transaction, timeout, giới hạn tải, trạng thái trung gian, idempotency.
5. **Định nghĩa cách khôi phục:** retry khi an toàn, đối soát khi kết quả chưa rõ, bù trừ khi một bước đã cam kết ở hệ thống khác.
6. **Kiểm thử theo điểm gây lỗi:** tiêm lỗi vào từng bước và xác minh bất biến, phản hồi, log và khả năng tiếp tục xử lý.

Không phải ứng dụng nhỏ nào cũng cần circuit breaker, Saga hay outbox. Nếu cập nhật chỉ nằm trong một database, transaction và bất biến rõ ràng có thể giải quyết phần lớn vấn đề. Nếu có nhiều dịch vụ bên ngoài hoặc cần bảo đảm sự kiện đi cùng dữ liệu, những cơ chế phức tạp hơn có thể mang lại giá trị. **Độ phức tạp của cơ chế phải tương xứng với rủi ro và hậu quả của lỗi.**

### Câu hỏi vận dụng

**Tình huống A:** API tạo đơn ghi đơn hàng thành công nhưng email xác nhận thất bại. Yêu cầu nghiệp vụ chỉ bắt buộc lưu đơn; email có thể gửi muộn. Bạn sẽ giữ email trong luồng đồng bộ hay chuyển sang cơ chế có khả năng gửi lại? Nếu chuyển, nơi nào lưu công việc chưa gửi và làm sao tránh gửi trùng ngoài ý muốn?

**Tình huống B:** Người dùng nhấn “Thanh toán” hai lần. Lần đầu timeout, lần thứ hai trả thành công. Bạn có bằng chứng chắc chắn lần đầu chưa thu tiền không? Cần lưu và truyền định danh nào để tra cứu, đối soát và chống thu hai lần?

**Tình huống C:** Hai server cùng đọc “còn một sản phẩm”, rồi đều chấp nhận giữ hàng. Vì sao `synchronized` trên từng server không đủ? Bạn sẽ dùng câu lệnh cập nhật có điều kiện hoặc cơ chế đồng thời nào tại điểm lưu dữ liệu chung?

**Tình huống D:** Dịch vụ gợi ý sản phẩm trả lỗi liên tục. Khi nào có thể ẩn vùng gợi ý, khi nào cần giới hạn số request tới phụ thuộc, và chỉ số nào cho thấy lỗi đã lan sang chức năng đặt hàng?

Với mỗi tình huống, hãy phác thảo trạng thái trước, tác dụng phụ đã hoàn tất, điểm lỗi và trạng thái chấp nhận được sau lỗi. Cách trả lời cần dựa trên bất biến nghiệp vụ và bằng chứng về rủi ro, thay vì chọn một design pattern theo thói quen.

## 13. Ghi nhớ

Để mã nguồn đáng tin cậy, dễ hiểu và dễ thay đổi, cần làm rõ **phần nào được phép thất bại**, **phần nào bắt buộc giữ nhất quán** và **cách hệ thống tiếp tục khi kết quả chưa chắc chắn**.

- Ngăn lỗi lan rộng bằng ranh giới rõ, timeout, giới hạn tải và suy giảm chức năng an toàn.
- Giữ trạng thái nhất quán bằng bất biến, thao tác nguyên tử, transaction và chuyển trạng thái hợp lệ.
- Dùng retry có giới hạn và idempotency cho thao tác có thể được gửi lặp.
- Với nhiều hệ thống, thiết kế trạng thái trung gian, cơ chế đối soát và phát lại an toàn; transaction của một database không thể bảo đảm cho mọi tác dụng phụ bên ngoài.
- Kiểm thử các điểm thất bại và trường hợp cạnh tranh, bởi “chạy đúng khi mọi thứ đều hoạt động” chưa đủ để đánh giá độ tin cậy.

Thiết kế tốt giúp một lỗi nhỏ **dừng lại ở đúng ranh giới của nó** và để lại trạng thái mà hệ thống có thể giải thích, kiểm chứng và phục hồi.
