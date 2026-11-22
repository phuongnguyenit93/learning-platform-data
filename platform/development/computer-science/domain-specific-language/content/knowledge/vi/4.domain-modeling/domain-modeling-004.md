# Bất biến của miền

## 1. Bất biến của miền là gì?

Trong mô hình miền (domain model), **bất biến của miền** (domain invariant) là một quy tắc nghiệp vụ phải luôn đúng đối với mọi trạng thái hợp lệ của một đối tượng hoặc một nhóm đối tượng trong miền. Bất biến xác định điều gì được phép tồn tại trong hệ thống. Mọi thao tác làm thay đổi trạng thái đều phải bảo vệ quy tắc đó.

Ví dụ trong hệ thống ngân hàng:

- Số dư của tài khoản thanh toán không được âm nếu sản phẩm không hỗ trợ thấu chi.
- Một giao dịch rút tiền phải có số tiền dương.
- Tiền được cộng hoặc trừ phải cùng loại tiền với tài khoản.

Trong hệ thống bán hàng:

- Đơn hàng đã hủy không được tiếp tục chuyển sang trạng thái đang giao.
- Số lượng của một dòng hàng phải lớn hơn 0.
- Tổng tiền của đơn hàng phải khớp với các dòng hàng và những khoản điều chỉnh hợp lệ.

Các quy tắc này không chỉ kiểm tra dữ liệu tại một màn hình. Chúng phải được giữ đúng dù trạng thái được thay đổi qua API, tác vụ nền, lệnh quản trị hay một luồng xử lý khác.

Một cách diễn đạt ngắn gọn là: **bất biến mô tả điều gì luôn phải đúng; hành vi của mô hình miền bảo đảm điều đó tiếp tục đúng sau mỗi thay đổi hợp lệ.**

## 2. Ví dụ về bất biến trong các miền nghiệp vụ

| Miền nghiệp vụ | Bất biến tiêu biểu | Vì sao cần bảo vệ? |
|---|---|---|
| Tài khoản ngân hàng | Số dư không âm; số tiền giao dịch phải dương | Ngăn tài khoản đi vào trạng thái không được sản phẩm cho phép |
| Đơn hàng | Đơn đã hủy không thể được giao; số lượng mỗi dòng hàng phải dương | Bảo vệ vòng đời đơn hàng và tính đúng đắn của dữ liệu |
| Kho hàng | Số lượng tồn khả dụng không âm | Tránh bán hoặc phân bổ vượt lượng hàng có thể cung cấp |
| Đặt chỗ | Một ghế không có hai lượt đặt chỗ đang hiệu lực trong cùng buổi diễn | Tránh cấp cùng một tài nguyên cho nhiều khách |
| Hợp đồng | Ngày kết thúc không sớm hơn ngày bắt đầu | Bảo đảm khoảng thời gian hợp đồng có ý nghĩa |

Không phải mọi quy tắc nghiệp vụ đều là bất biến. Chẳng hạn, chính sách giảm giá có thể phụ thuộc vào chiến dịch, thời điểm, nhóm khách hàng và ngân sách còn lại. Chính sách đó quyết định một thao tác có được phép hay không trong một ngữ cảnh cụ thể. Bất biến thường mô tả điều kiện cấu trúc phải đúng đối với trạng thái hợp lệ, chẳng hạn tổng tiền không âm hoặc ngày kết thúc không đứng trước ngày bắt đầu.

## 3. Phân biệt bất biến với validation, tiền điều kiện và hậu điều kiện

Các khái niệm này liên quan với nhau nhưng có vai trò khác nhau:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Validation dữ liệu đầu vào | Dữ liệu gửi lên có đúng định dạng và kiểu cần thiết không? | Mã bưu chính có đúng định dạng; trường ngày có phân tích được không? |
| Tiền điều kiện (precondition) | Điều gì phải đúng trước khi gọi một thao tác? | Tài khoản đang hoạt động trước khi rút tiền |
| Hậu điều kiện (postcondition) | Điều gì phải đúng sau khi thao tác hoàn tất? | Số dư mới bằng số dư cũ trừ số tiền rút |
| Bất biến (invariant) | Điều gì phải luôn đúng trong mọi trạng thái hợp lệ? | Số dư tài khoản không âm |

Một quy tắc có thể xuất hiện ở nhiều góc nhìn. Với thao tác rút tiền, “số tiền rút phải lớn hơn 0” là tiền điều kiện của thao tác. “Số dư sau khi rút không âm” là điều kiện để trạng thái tài khoản vẫn hợp lệ và do đó là một phần của bất biến tài khoản. Validation ở giao diện có thể kiểm tra số tiền dương để phản hồi sớm, nhưng mô hình miền vẫn phải tự bảo vệ quy tắc.

Validation thường kiểm tra hình thức của dữ liệu bên ngoài. Bất biến diễn đạt ý nghĩa nghiệp vụ của trạng thái. Một chuỗi có thể đúng định dạng nhưng vẫn vi phạm miền: ví dụ ngày kết thúc hợp đồng được gửi theo định dạng ISO hợp lệ nhưng lại sớm hơn ngày bắt đầu.

## 4. Đặt bất biến ở đúng nơi trong mô hình miền

### 4.1. Value Object bảo vệ giá trị ngay khi được tạo

Value Object là đối tượng được xác định bởi giá trị của nó và thường không có định danh riêng. Đây là nơi phù hợp để bảo vệ những quy tắc gắn với một giá trị, ví dụ khoảng ngày, địa chỉ email, mã tiền tệ hoặc khoảng số lượng.

Ví dụ, khoảng thời gian hợp đồng phải có ngày kết thúc không sớm hơn ngày bắt đầu:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public record ContractPeriod(LocalDate start, LocalDate end) {
    public ContractPeriod {
        Objects.requireNonNull(start, "start is required");
        Objects.requireNonNull(end, "end is required");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "Contract end date cannot be before start date");
        }
    }
}
~~~

Khi một đối tượng ContractPeriod được tạo thành công, các phần còn lại của chương trình có thể dựa vào điều kiện ngày tháng này. Không cần lặp lại cùng một phép so sánh ở mọi nơi sử dụng khoảng thời gian.

### 4.2. Entity bảo vệ quy tắc gắn với vòng đời của đối tượng

Entity có định danh và trạng thái thay đổi theo thời gian. Quy tắc phụ thuộc vào trạng thái hiện tại thường được thực thi qua các hành vi có tên theo nghiệp vụ.

Ví dụ, đơn hàng chỉ được xác nhận khi đang ở trạng thái chờ xác nhận:

~~~java
public enum OrderStatus {
    DRAFT,
    PENDING_CONFIRMATION,
    CONFIRMED,
    CANCELLED
}

public final class Order {
    private final String id;
    private OrderStatus status;

    public Order(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Order id is required");
        }
        this.id = id;
        this.status = OrderStatus.DRAFT;
    }

    public void submitForConfirmation() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only a draft order can be submitted");
        }
        status = OrderStatus.PENDING_CONFIRMATION;
    }

    public void confirm() {
        if (status != OrderStatus.PENDING_CONFIRMATION) {
            throw new IllegalStateException(
                    "Only a pending order can be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status == OrderStatus.CANCELLED
                || status == OrderStatus.CONFIRMED) {
            throw new IllegalStateException(
                    "This order cannot be cancelled");
        }
        status = OrderStatus.CANCELLED;
    }

    public String id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }
}
~~~

Các phương thức trên làm rõ những chuyển trạng thái được phép. Nếu chỉ cung cấp một setter công khai cho status, bất kỳ đoạn mã nào cũng có thể đặt đơn hàng sang trạng thái tùy ý, kể cả chuyển từ CANCELLED sang CONFIRMED. Khi đó quy tắc vòng đời không còn được bảo vệ tại nơi sở hữu trạng thái.

Trong ứng dụng thực tế, cần xác định đầy đủ các chuyển trạng thái theo yêu cầu nghiệp vụ. Ví dụ có thể có thao tác hoàn tiền hoặc mở lại đơn hàng với điều kiện riêng. Không nên suy ra rằng mọi chuyển trạng thái chưa được liệt kê đều hợp lệ.

## 5. Aggregate và ranh giới bảo vệ bất biến

Trong Domain-Driven Design (DDD), **Aggregate** là một cụm đối tượng miền được xem như một đơn vị nhất quán. Aggregate Root là điểm truy cập bên ngoài để thay đổi trạng thái của cụm. Một mục tiêu quan trọng của ranh giới này là bảo vệ các bất biến cần đúng ngay sau mỗi giao dịch nghiệp vụ.

Ví dụ, một đơn hàng có thể chứa nhiều dòng hàng. Các quy tắc nội bộ có thể gồm:

- Đơn hàng phải có mã định danh.
- Mỗi dòng hàng phải có sản phẩm và số lượng dương.
- Không thể thêm dòng hàng khi đơn đã được xác nhận.
- Tổng tiền phải được tính từ các dòng hàng và những khoản điều chỉnh hợp lệ.

Nếu Order là Aggregate Root, các đối tượng bên ngoài yêu cầu thêm hoặc bỏ dòng hàng thông qua Order. Chúng không trực tiếp sửa danh sách nội bộ hoặc thay đổi số lượng của một dòng hàng sau lưng Order.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class PurchaseOrder {
    private final String id;
    private final List<OrderLine> lines = new ArrayList<>();
    private boolean confirmed;

    public PurchaseOrder(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Order id is required");
        }
        this.id = id;
    }

    public void addLine(String productId, int quantity,
                        BigDecimal unitPrice) {
        if (confirmed) {
            throw new IllegalStateException(
                    "A confirmed order cannot be changed");
        }

        OrderLine line = new OrderLine(productId, quantity, unitPrice);
        lines.add(line);
    }

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "An order must contain at least one line");
        }
        confirmed = true;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public BigDecimal total() {
        return lines.stream()
                .map(OrderLine::subtotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public String id() {
        return id;
    }

    public boolean isConfirmed() {
        return confirmed;
    }

    public record OrderLine(
            String productId,
            int quantity,
            BigDecimal unitPrice) {

        public OrderLine {
            if (productId == null || productId.isBlank()) {
                throw new IllegalArgumentException(
                        "Product id is required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "Quantity must be positive");
            }
            Objects.requireNonNull(unitPrice, "unitPrice is required");
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "Unit price cannot be negative");
            }
        }

        public BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }
}
~~~

Ví dụ này cho thấy Aggregate Root kiểm soát việc thêm dòng hàng và xác nhận đơn. Danh sách được trả ra dưới dạng bản sao không thể sửa, vì vậy mã bên ngoài không thể thêm hoặc xóa phần tử trực tiếp trong danh sách nội bộ. Dòng hàng cũng tự kiểm tra các giá trị bắt buộc khi được tạo.

Đây là ví dụ rút gọn để minh họa ranh giới nhất quán. Hệ thống thật có thể cần thêm quy tắc về tiền tệ, thuế, giảm giá, sản phẩm còn kinh doanh hay không và cách lưu ảnh chụp giá tại thời điểm đặt hàng.

### 5.1. Quy tắc nằm trong một Aggregate hay vượt qua nhiều Aggregate?

Một quy tắc có thể được kiểm tra hoàn toàn trong một Aggregate, chẳng hạn đơn hàng không được xác nhận khi chưa có dòng hàng. Những quy tắc như vậy có thể được bảo vệ trong cùng một lần thay đổi trạng thái.

Một số quy tắc liên quan đến nhiều Aggregate. Ví dụ, một ghế trong buổi diễn chỉ được có một lượt đặt chỗ đang hiệu lực. Đơn đặt chỗ và sơ đồ chỗ ngồi có thể được quản lý bởi các Aggregate khác nhau. Khi đó, chỉ kiểm tra một đối tượng trong bộ nhớ không đủ để bảo đảm không có yêu cầu đồng thời cùng đặt một ghế.

Có một số cách xử lý tùy yêu cầu nhất quán:

- Dùng một giao dịch cơ sở dữ liệu và ràng buộc duy nhất nếu dữ liệu cùng nằm trong một cơ sở dữ liệu và quy tắc có thể biểu diễn bằng khóa duy nhất.
- Dùng khóa hoặc cập nhật có điều kiện để hai yêu cầu đồng thời không cùng chiếm một tài nguyên.
- Thiết kế một Aggregate chịu trách nhiệm sở hữu tài nguyên cần phân bổ, chẳng hạn SeatReservation.
- Nếu quy trình trải qua nhiều dịch vụ và không thể có giao dịch nguyên tử chung, dùng quy trình điều phối, giữ chỗ tạm thời, xác nhận hoặc bù trừ theo chính sách nghiệp vụ.

Không nên tùy tiện mở rộng một Aggregate để chứa mọi dữ liệu liên quan. Aggregate quá lớn làm tăng tranh chấp ghi, tải dữ liệu và độ khó của giao dịch. Ranh giới nên phản ánh nơi cần bảo đảm nhất quán ngay lập tức.

## 6. Bất biến trong giao dịch và xử lý đồng thời

Một thao tác có thể kiểm tra bất biến đúng tại thời điểm đọc nhưng vẫn tạo ra trạng thái sai khi nhiều yêu cầu chạy đồng thời.

Giả sử tài khoản có số dư 100.000 đồng. Hai yêu cầu độc lập cùng đọc số dư này và mỗi yêu cầu muốn rút 80.000 đồng. Nếu cả hai đều kiểm tra trên cùng giá trị cũ rồi cùng ghi số dư mới là 20.000 đồng, hệ thống có thể chấp nhận hai lần rút dù tổng số tiền cần rút vượt số dư ban đầu. Đây là lỗi cạnh tranh (race condition).

Vì vậy, việc kiểm tra và cập nhật phải nằm trong cơ chế nhất quán phù hợp:

1. Đọc trạng thái hiện tại trong giao dịch.
2. Kiểm tra điều kiện nghiệp vụ trên trạng thái đó.
3. Thực hiện thay đổi.
4. Ghi trạng thái với khóa lạc quan, khóa bi quan hoặc cập nhật nguyên tử tùy hệ thống.
5. Nếu có xung đột, tải lại trạng thái mới và xử lý lại theo quy tắc nghiệp vụ.

Với khóa lạc quan (optimistic locking), bản ghi thường có một trường version. Khi lưu, câu lệnh cập nhật yêu cầu version vẫn bằng giá trị đã đọc; nếu một giao dịch khác đã cập nhật trước, số dòng bị ảnh hưởng bằng 0 và thao tác phải được xem là xung đột. Với khóa bi quan (pessimistic locking), hệ thống khóa dữ liệu trong thời gian giao dịch để ngăn thao tác cạnh tranh không tương thích.

Lựa chọn cơ chế phụ thuộc tải, độ nhạy của dữ liệu, cơ sở dữ liệu và mức nhất quán nghiệp vụ yêu cầu. Một phương thức Java kiểm tra điều kiện là cần thiết nhưng tự nó không giải quyết được tranh chấp giữa nhiều tiến trình.

## 7. Bảo vệ bất biến ở tầng lưu trữ

Mô hình miền là nơi thể hiện ý nghĩa và hành vi nghiệp vụ. Cơ sở dữ liệu cũng nên có các ràng buộc phù hợp để bảo vệ dữ liệu khi có nhiều đường ghi hoặc lỗi ở tầng ứng dụng.

Ví dụ:

~~~sql
CREATE TABLE account (
    id       BIGINT PRIMARY KEY,
    balance  DECIMAL(19, 2) NOT NULL,
    CONSTRAINT ck_account_balance_nonnegative
        CHECK (balance >= 0)
);

CREATE TABLE order_line (
    id          BIGINT PRIMARY KEY,
    order_id    BIGINT NOT NULL,
    quantity    INTEGER NOT NULL,
    unit_price  DECIMAL(19, 2) NOT NULL,
    CONSTRAINT ck_order_line_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT ck_order_line_price_nonnegative
        CHECK (unit_price >= 0),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_order(id)
);
~~~

Ràng buộc CHECK ngăn một số trạng thái dữ liệu không hợp lệ được ghi vào bảng. NOT NULL yêu cầu trường có giá trị; FOREIGN KEY bảo đảm tham chiếu tới bản ghi liên quan tồn tại. UNIQUE có thể bảo vệ tính duy nhất, ví dụ mỗi ghế chỉ có một bản ghi đặt chỗ đang hiệu lực nếu mô hình bảng và cơ chế chỉ mục hỗ trợ biểu diễn điều kiện đó.

Ràng buộc cơ sở dữ liệu và kiểm tra trong mô hình miền bổ sung cho nhau:

- Mô hình miền có thể đưa ra thông báo lỗi theo ngôn ngữ nghiệp vụ và bảo vệ hành vi qua mọi luồng sử dụng đúng mô hình.
- Cơ sở dữ liệu là lớp bảo vệ cuối cùng trước các đường ghi trực tiếp, lỗi ứng dụng hoặc tranh chấp giữa các giao dịch.
- Giao dịch và cơ chế đồng thời bảo đảm việc kiểm tra cùng thay đổi được thực hiện với mức nhất quán phù hợp.

Không phải bất biến nào cũng biểu diễn được bằng một ràng buộc đơn giản. Quy tắc phụ thuộc vào nhiều bản ghi, thời gian hoặc dịch vụ ngoài thường cần giao dịch, truy vấn có điều kiện hoặc quy trình nghiệp vụ chuyên biệt.

## 8. Cách xử lý khi một thao tác vi phạm bất biến

Khi một lệnh làm trạng thái trở nên không hợp lệ, mô hình miền cần từ chối thao tác trước khi công bố trạng thái mới. Cách biểu đạt lỗi nên giúp tầng ứng dụng hiểu điều gì đã xảy ra.

Ví dụ:

- Rút nhiều hơn số dư khả dụng: từ chối với lỗi nghiệp vụ như InsufficientFunds.
- Thêm dòng hàng có số lượng bằng 0: từ chối với lỗi dữ liệu miền như InvalidQuantity.
- Xác nhận một đơn đã hủy: từ chối vì chuyển trạng thái không hợp lệ.
- Hai yêu cầu cùng đặt một ghế: một yêu cầu thành công, yêu cầu còn lại nhận kết quả ghế đã được giữ hoặc đặt.

Có thể dùng exception chuyên biệt, kiểu kết quả (Result) hoặc cơ chế lỗi tương đương của ngôn ngữ và kiến trúc. Điều quan trọng là không âm thầm bỏ qua lỗi, không lưu một phần thay đổi rồi để đối tượng ở trạng thái dở dang, và không biến lỗi nghiệp vụ thành lỗi máy chủ chung chung nếu tầng giao tiếp cần phân loại phản hồi.

Trong một phương thức thay đổi phức tạp, nên tính toán và xác thực trạng thái mới trước, sau đó mới cập nhật các trường nội bộ. Nếu cần ghi nhiều bản ghi, hãy đặt chúng trong một giao dịch để khi có lỗi có thể rollback toàn bộ thay đổi liên quan.

## 9. Kiểm thử bất biến

Kiểm thử bất biến tập trung vào thuộc tính phải đúng với mọi trạng thái hợp lệ, thay vì chỉ kiểm tra một ví dụ đầu vào.

Với tài khoản ngân hàng, có thể kiểm tra:

- Không tạo được tài khoản với số dư ban đầu âm.
- Không nạp hoặc rút số tiền bằng 0 hay âm nếu quy tắc yêu cầu số tiền giao dịch dương.
- Không rút vượt số dư.
- Sau mọi thao tác thành công, số dư vẫn không âm.
- Không cộng hoặc trừ tiền khác loại tiền.
- Nếu thao tác thất bại, số dư không bị thay đổi một phần.

Ví dụ kiểm thử bằng JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class AccountTest {
    @Test
    void rejectsWithdrawalThatWouldMakeBalanceNegative() {
        Account account = new Account(
                "A-100",
                new BigDecimal("500.00"));

        assertThrows(
                InsufficientFundsException.class,
                () -> account.withdraw(new BigDecimal("600.00")));

        assertEquals(
                new BigDecimal("500.00"),
                account.balance());
    }
}
~~~

Đoạn kiểm thử giả định lớp Account có constructor, phương thức withdraw, balance và ngoại lệ InsufficientFundsException tương ứng. Nó minh họa hai điều cần xác nhận: thao tác không hợp lệ bị từ chối và trạng thái trước đó vẫn được giữ nguyên.

Ngoài kiểm thử ví dụ cụ thể, có thể dùng property-based testing để sinh nhiều giá trị đầu vào. Chẳng hạn, với mọi số dư ban đầu không âm và mọi khoản rút được chấp nhận, số dư sau thao tác phải không âm. Kiểm thử tích hợp cần xác nhận ràng buộc cơ sở dữ liệu và xử lý đồng thời hoạt động đúng khi nhiều yêu cầu cùng cập nhật một tài nguyên.

## 10. Những lỗi thiết kế thường gặp

### Chỉ kiểm tra ở giao diện

Giao diện có thể ẩn nút hoặc báo lỗi sớm, nhưng API, tác vụ nền và chương trình tích hợp vẫn có thể gọi trực tiếp. Bất biến phải được bảo vệ tại mô hình miền hoặc ranh giới giao dịch có thẩm quyền.

### Công khai setter cho mọi trường

Setter tùy ý cho phép mã bên ngoài bỏ qua quy trình nghiệp vụ. Nên cung cấp hành vi có tên rõ ràng như confirm, cancel, reserve hoặc withdraw để mô hình tự kiểm tra điều kiện.

### Lặp lại cùng một quy tắc ở nhiều nơi

Khi mỗi controller hoặc service tự kiểm tra một phần quy tắc, các luồng có thể xử lý khác nhau và dần mất nhất quán. Quy tắc cốt lõi nên nằm ở nơi sở hữu trạng thái; tầng ứng dụng điều phối thao tác và chuyển kết quả thành phản hồi phù hợp.

### Cho phép trạng thái tạm thời không hợp lệ bị quan sát

Một thao tác nhiều bước có thể vô tình cập nhật một trường rồi phát sinh lỗi trước khi cập nhật trường còn lại. Nên xác thực trước, cập nhật nguyên tử trong bộ nhớ hoặc dùng giao dịch để rollback khi cần.

### Nghĩ rằng kiểm tra trong bộ nhớ đủ cho mọi trường hợp

Đối tượng miền có thể hợp lệ khi được tải, nhưng dữ liệu trong cơ sở dữ liệu có thể thay đổi bởi một giao dịch khác. Những quy tắc chịu ảnh hưởng của cạnh tranh phải được bảo vệ bằng giao dịch, khóa, version hoặc ràng buộc lưu trữ.

### Đặt mọi quy tắc vào một Aggregate lớn

Aggregate quá lớn làm mọi thao tác phải tải và khóa nhiều dữ liệu. Chỉ nên giữ cùng một ranh giới khi các quy tắc cần được bảo đảm nhất quán ngay trong một giao dịch. Các quy trình liên quan nhiều Aggregate có thể cần điều phối và nhất quán cuối cùng.

## 11. Quy trình xác định và triển khai bất biến

Khi phân tích một miền nghiệp vụ mới, có thể thực hiện theo các bước:

1. **Tìm trạng thái không hợp lệ.** Hỏi chuyên gia nghiệp vụ điều gì tuyệt đối không được xảy ra, kể cả khi dữ liệu đi vào từ một hệ thống khác.
2. **Viết quy tắc rõ ràng.** Dùng câu có thể kiểm chứng, chẳng hạn “số lượng dòng hàng luôn lớn hơn 0” thay vì “dòng hàng phải hợp lệ”.
3. **Xác định chủ sở hữu trạng thái.** Quy tắc thuộc một Value Object, Entity hay Aggregate nào? Thành phần nào có quyền thay đổi trạng thái đó?
4. **Xác định ranh giới nhất quán.** Quy tắc có thể được giữ đúng trong một Aggregate hay cần nhiều Aggregate, giao dịch hoặc dịch vụ?
5. **Đưa hành vi vào mô hình.** Dùng constructor và phương thức nghiệp vụ để trạng thái không hợp lệ không thể được tạo hoặc lưu thông qua đường đi thông thường.
6. **Bổ sung bảo vệ ở nơi cần thiết.** Dùng transaction, version, khóa và ràng buộc cơ sở dữ liệu theo yêu cầu nhất quán.
7. **Kiểm thử cả thành công và thất bại.** Xác nhận thao tác hợp lệ giữ được bất biến, thao tác sai bị từ chối và lỗi không để lại thay đổi dở dang.

Một quy tắc tốt nên có chủ sở hữu rõ ràng và có thể được diễn đạt thành điều kiện kiểm thử. Khi yêu cầu nghiệp vụ thay đổi, nhóm phát triển có thể xác định chính xác mô hình, giao dịch và ràng buộc nào cần cập nhật.

## 12. Kết luận

Bất biến của miền là nền tảng để mô hình miền biểu diễn những trạng thái mà doanh nghiệp chấp nhận. Nó giúp dữ liệu luôn có ý nghĩa, hành vi của đối tượng có giới hạn rõ ràng và các thao tác không thể tùy tiện phá vỡ quy tắc nghiệp vụ.

Để bảo vệ bất biến, hãy đặt quy tắc gần với trạng thái mà nó chi phối, cho phép thay đổi qua các hành vi nghiệp vụ có kiểm soát, xác định Aggregate làm ranh giới nhất quán phù hợp, đồng thời dùng giao dịch và ràng buộc lưu trữ khi có nhiều luồng cập nhật. Kiểm thử cần chứng minh cả việc từ chối trạng thái sai lẫn việc giữ nguyên trạng thái khi thao tác thất bại.

Khi đọc hoặc thiết kế một mô hình miền, hãy tự hỏi: trạng thái hợp lệ phải luôn thỏa mãn điều kiện nào, đối tượng nào chịu trách nhiệm giữ điều kiện đó, và cơ chế nào bảo vệ nó khi nhiều thao tác diễn ra đồng thời? Trả lời được những câu hỏi này sẽ giúp mô hình phản ánh đúng quy tắc nghiệp vụ và giảm lỗi nhất quán trong hệ thống.
