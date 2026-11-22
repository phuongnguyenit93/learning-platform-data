# Biểu diễn hành vi và bất biến thay vì chỉ tập hợp thuộc tính

Trong Domain-Driven Design (DDD), mô hình miền cần diễn tả cách doanh nghiệp đưa ra quyết định và bảo đảm các quy tắc nghiệp vụ. Một đối tượng miền vì vậy không chỉ là nơi lưu các thuộc tính như mã, tên, số lượng hay trạng thái. Nó cần thể hiện những hành động có ý nghĩa nghiệp vụ, kiểm tra điều kiện để hành động hợp lệ và bảo vệ các bất biến mà doanh nghiệp yêu cầu.

Một mô hình chỉ có dữ liệu, còn mọi quyết định được thực hiện bên ngoài thông qua các câu lệnh gán thuộc tính, thường được gọi là **Anemic Domain Model (mô hình miền thiếu hành vi)**. Cách tổ chức này có thể phù hợp với một số ứng dụng CRUD đơn giản, nhưng trở nên khó kiểm soát khi nghiệp vụ có nhiều trạng thái, điều kiện, ngoại lệ và quan hệ giữa các đối tượng.

Bài học này trình bày cách xây dựng mô hình miền giàu hành vi (Rich Domain Model): đặt hành vi gần dữ liệu và quy tắc mà nó bảo vệ, thể hiện rõ chuyển trạng thái, đóng gói bất biến trong ranh giới phù hợp và để tầng ứng dụng điều phối các bước của ca sử dụng. Ví dụ xuyên suốt sử dụng một đơn hàng để minh họa cách chuyển từ tập hợp thuộc tính sang mô hình có trách nhiệm nghiệp vụ.

## 1. Từ đối tượng chứa dữ liệu đến đối tượng có trách nhiệm nghiệp vụ

### 1.1. Mô hình miền phải mô tả điều doanh nghiệp làm

Giả sử một hệ thống bán hàng có đối tượng đơn hàng với các thuộc tính:

- Mã đơn hàng.
- Danh sách dòng hàng.
- Tổng tiền.
- Trạng thái.
- Thời điểm tạo.

Nếu đối tượng chỉ cung cấp getter và setter, các lớp khác có thể tự thay đổi trạng thái, số lượng và tổng tiền. Những câu hỏi nghiệp vụ như “đơn nào được phép xác nhận?”, “đơn đã giao có được hủy không?” hoặc “đơn không có dòng hàng có thể xác nhận không?” sẽ nằm rải rác trong controller, service hoặc giao diện.

Khi quy tắc được phân tán, mỗi nơi có thể áp dụng điều kiện khác nhau. Một chức năng quên kiểm tra trạng thái, một chức năng khác cập nhật tổng tiền không đồng bộ với dòng hàng. Dữ liệu có thể vẫn đúng kiểu và không rỗng, nhưng trạng thái nghiệp vụ đã trở nên vô nghĩa.

Mô hình có hành vi đưa quyết định về nơi có đủ hiểu biết để bảo vệ quy tắc. Thay vì yêu cầu một đối tượng bên ngoài tự sửa nhiều thuộc tính, ta yêu cầu đối tượng thực hiện một hành động có ý nghĩa:

- Thêm dòng hàng.
- Thay đổi số lượng khi đơn còn được phép chỉnh sửa.
- Xác nhận đơn khi các điều kiện đã thỏa mãn.
- Hủy đơn khi chính sách cho phép.
- Đánh dấu đã bàn giao khi đơn đã được xác nhận.

Tên phương thức thể hiện ngôn ngữ nghiệp vụ và giới hạn những thay đổi có thể xảy ra.

### 1.2. Phân biệt dữ liệu, hành vi và bất biến

Ba yếu tố này liên hệ chặt chẽ nhưng có vai trò khác nhau:

| Yếu tố | Ý nghĩa | Ví dụ trong đơn hàng |
|---|---|---|
| Dữ liệu (state) | Thông tin mô tả đối tượng tại một thời điểm | Trạng thái đơn, dòng hàng, số lượng |
| Hành vi (behavior) | Hành động nghiệp vụ mà đối tượng có thể thực hiện | Xác nhận, hủy, thay đổi số lượng |
| Bất biến (invariant) | Điều kiện phải luôn đúng trong phạm vi mô hình | Số lượng dòng hàng phải lớn hơn 0; đơn rỗng không được xác nhận |

Hành vi thường làm thay đổi trạng thái, nhưng không phải mọi thay đổi trạng thái đều hợp lệ. Bất biến xác định những điều kiện mà mô hình phải giữ đúng trước và sau khi hành vi được thực hiện.

Ví dụ, trạng thái đơn hàng có thể chuyển từ Nháp sang Đã xác nhận. Nhưng chuyển từ Đã giao trở lại Nháp có thể không hợp lệ. Mô hình cần biết các chuyển đổi được phép thay vì để mã gọi bên ngoài tự gán giá trị trạng thái.

### 1.3. Mô hình miền là cách diễn đạt kiến thức nghiệp vụ

Mô hình không chỉ là bản sao cấu trúc dữ liệu từ cơ sở dữ liệu. Nó là sự trừu tượng hóa những khái niệm, quy tắc và quyết định quan trọng trong một phạm vi nghiệp vụ.

Một bảng dữ liệu có cột ORDER_STATUS không tự giải thích được:

- Những trạng thái nào tồn tại?
- Điều kiện nào cho phép chuyển từ trạng thái này sang trạng thái khác?
- Ai có quyền thực hiện chuyển đổi?
- Khi chuyển đổi, những cam kết nào được tạo ra?
- Có hành động nào phải bị từ chối?

Mô hình miền trả lời những câu hỏi đó bằng các kiểu dữ liệu, phương thức, quy tắc và mối quan hệ có ý nghĩa.

## 2. Anemic Domain Model và Rich Domain Model

### 2.1. Mô hình miền thiếu hành vi

Trong Anemic Domain Model, các lớp miền chủ yếu chứa thuộc tính và getter/setter. Logic nghiệp vụ được đặt trong các service bên ngoài. Ví dụ đơn giản:

~~~java
public class Order {
    private String id;
    private String status;
    private int totalQuantity;

    public String getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public int getTotalQuantity() {
        return totalQuantity;
    }

    public void setTotalQuantity(int totalQuantity) {
        this.totalQuantity = totalQuantity;
    }
}
~~~

Một service bên ngoài có thể thực hiện:

~~~java
public class OrderService {
    public void confirm(Order order) {
        if (order.getTotalQuantity() <= 0) {
            throw new IllegalStateException("Order is empty");
        }

        if (!"DRAFT".equals(order.getStatus())) {
            throw new IllegalStateException("Order cannot be confirmed");
        }

        order.setStatus("CONFIRMED");
    }
}
~~~

Đoạn mã có thể hoạt động, nhưng quy tắc xác nhận đơn đang nằm trong OrderService. Nếu một tác vụ khác cũng cần xác nhận đơn và quên kiểm tra điều kiện, nó có thể tạo ra hành vi không nhất quán.

Một vấn đề khác là setter cho phép mọi nơi thay đổi trạng thái mà không cần đi qua quy tắc. Mô hình không tự bảo vệ được trạng thái hợp lệ.

### 2.2. Mô hình miền giàu hành vi

Trong Rich Domain Model, đối tượng sở hữu dữ liệu cũng sở hữu những hành vi và quy tắc liên quan trực tiếp đến dữ liệu đó.

~~~java
public class Order {
    private OrderStatus status;
    private final List<OrderLine> lines = new ArrayList<>();

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be confirmed"
            );
        }

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An empty order cannot be confirmed"
            );
        }

        status = OrderStatus.CONFIRMED;
    }
}
~~~

Mã gọi bên ngoài chỉ cần yêu cầu:

~~~java
order.confirm();
~~~

Order tự kiểm tra điều kiện và thực hiện chuyển trạng thái. Bên gọi không cần biết cách bảo vệ các quy tắc nội bộ.

Điểm quan trọng không nằm ở việc chuyển vài dòng if vào một lớp khác. Hành vi phải thuộc về đối tượng hoặc dịch vụ miền có trách nhiệm và đủ hiểu biết để thực hiện quyết định đó.

### 2.3. Không phải mọi ứng dụng đều cần mô hình giàu hành vi

Rich Domain Model hữu ích khi nghiệp vụ có quy tắc, trạng thái, hành vi và các quyết định thay đổi theo bối cảnh. Với một màn hình CRUD đơn giản, dữ liệu ít quy tắc và không có vòng đời đáng kể, mô hình đơn giản có thể phù hợp hơn.

Không nên thêm nhiều lớp, interface hoặc factory chỉ để làm ứng dụng trông giống DDD. Mức độ phong phú của mô hình cần tương ứng với độ phức tạp nghiệp vụ. DDD hướng đến mô hình hóa đúng vấn đề, không phải tối đa hóa số lượng pattern.

## 3. Hành vi cần diễn đạt ý định nghiệp vụ

### 3.1. Dùng phương thức thể hiện hành động

Một phương thức tốt thường diễn đạt điều người dùng hoặc nghiệp vụ muốn làm:

- confirm()
- cancel(reason)
- addLine(product, quantity, price)
- changeQuantity(product, quantity)
- reserve()
- release()
- approve()
- reject(reason)

Tên phương thức giúp người đọc hiểu mục đích mà không phải suy luận từ một chuỗi setter.

So sánh:

~~~java
order.setStatus("CONFIRMED");
order.setConfirmedAt(now);
order.setCanEdit(false);
~~~

với:

~~~java
order.confirm();
~~~

Cách thứ hai cho phép mô hình tự quyết định những thuộc tính nào cần thay đổi, điều kiện nào phải kiểm tra và sự kiện nào cần ghi nhận.

### 3.2. Đóng gói trạng thái

Đóng gói có nghĩa là giới hạn cách bên ngoài quan sát và thay đổi trạng thái. Không nên công khai setter cho mọi thuộc tính quan trọng. Các tập hợp nội bộ cũng không nên được trả về dưới dạng có thể sửa trực tiếp.

Ví dụ:

~~~java
public List<OrderLine> lines() {
    return List.copyOf(lines.values());
}
~~~

Bên gọi nhận được một bản sao không thể thay đổi. Muốn thêm hoặc xóa dòng hàng phải gọi phương thức của Order, nơi các quy tắc liên quan được kiểm tra.

Đóng gói không chỉ là khai báo field private. Nếu đối tượng trả về một collection có thể sửa, hoặc cung cấp setter công khai cho trạng thái nghiệp vụ, quyền kiểm soát vẫn bị rò rỉ ra ngoài.

### 3.3. Hành vi nên giữ ngữ nghĩa rõ ràng

Một phương thức như update() hoặc process() quá chung chung. Nó không cho biết quyết định nghiệp vụ nào đang diễn ra.

Hãy dùng tên phản ánh mục tiêu và điều kiện:

- submitForApproval() thể hiện yêu cầu đưa hồ sơ vào quy trình phê duyệt.
- approve() thể hiện quyết định chấp thuận.
- markAsPaid() có thể gây hiểu nhầm nếu thực tế chỉ mới nhận được yêu cầu thanh toán.
- recordPaymentAuthorization() diễn đạt chính xác hơn nếu nghiệp vụ chỉ xác nhận khoản tiền được ủy quyền.

Tên gọi chính xác giúp tránh nhầm lẫn giữa yêu cầu, kết quả và trạng thái.

## 4. Bất biến nghiệp vụ (Invariant)

### 4.1. Bất biến là điều kiện phải luôn được bảo đảm

Invariant là một điều kiện mà mô hình phải duy trì đúng trong suốt vòng đời của đối tượng hoặc trong ranh giới nhất quán được xác định.

Ví dụ với đơn hàng:

- Số lượng của mỗi dòng hàng phải lớn hơn 0.
- Đơn hàng chỉ chứa các dòng hàng có cùng loại tiền tệ với đơn.
- Đơn rỗng không được xác nhận.
- Đơn đã giao không thể quay lại trạng thái Nháp.
- Đơn đã xác nhận không được thay đổi dòng hàng nếu chính sách không cho phép.

Các điều kiện này khác với một kiểm tra giao diện. Dù hành động đến từ API, batch job, message handler hay màn hình quản trị, quy tắc vẫn phải được bảo vệ.

### 4.2. Phân biệt bất biến với validation đầu vào

Không phải mọi kiểm tra dữ liệu đều là invariant.

| Loại kiểm tra | Ví dụ | Nơi thường xử lý |
|---|---|---|
| Kiểm tra cú pháp đầu vào | Chuỗi ngày tháng đúng định dạng | API boundary hoặc parser |
| Kiểm tra trường bắt buộc | Request có mã khách hàng | API/application layer và kiểu dữ liệu phù hợp |
| Kiểm tra giá trị hợp lệ | Quantity lớn hơn 0 | Value Object hoặc mô hình miền |
| Quy tắc nghiệp vụ | Chỉ đơn Nháp mới được sửa dòng hàng | Entity hoặc Aggregate |
| Bất biến của Aggregate | Tổng tiền và các dòng hàng phải nhất quán theo chính sách | Aggregate Root |
| Quy tắc phối hợp nhiều ngữ cảnh | Chỉ tiếp tục thực hiện sau khi có kết quả giữ hàng và thanh toán phù hợp | Application service hoặc Process Manager |

Một số kiểm tra có thể xuất hiện ở nhiều lớp vì mục đích khác nhau. API có thể kiểm tra sớm để trả thông báo thân thiện, nhưng mô hình miền vẫn phải bảo vệ invariant để không phụ thuộc vào việc mọi lời gọi đều đi qua API đó.

### 4.3. Bất biến phải được bảo vệ tại nơi có quyền quyết định

Nếu một quy tắc liên quan đến một đối tượng và các thành phần bên trong nó, đặt quy tắc tại Entity hoặc Aggregate phù hợp.

Ví dụ, Order kiểm soát việc xác nhận đơn vì nó sở hữu trạng thái đơn và danh sách dòng hàng. Một controller không nên tự kiểm tra rồi gán trạng thái.

Nếu quy tắc cần phối hợp nhiều Aggregate hoặc nhiều Bounded Context, không nên tạo một đối tượng khổng lồ để giữ tất cả. Hãy phân biệt:

- Invariant cần bảo đảm nguyên tử bên trong một Aggregate.
- Quy tắc phối hợp giữa nhiều Aggregate.
- Quy trình dài cần xử lý bất đồng bộ và bù trừ.
- Quy tắc thuộc một dịch vụ miền vì không có Entity nào sở hữu tự nhiên.

### 4.4. Invariant cần đúng sau mọi hành vi công khai

Một Aggregate có thể được tạo mới, tải từ repository, thay đổi qua API hoặc xử lý từ message. Mọi đường đi đều phải giữ được các điều kiện mà mô hình cam kết.

Không nên chỉ bảo vệ invariant trong constructor rồi cho phép setter bỏ qua chúng. Tương tự, không nên để một phương thức public trả về đối tượng nội bộ có thể sửa trực tiếp.

Một invariant bị vi phạm có thể khiến dữ liệu lưu trữ không còn đại diện cho một trạng thái nghiệp vụ hợp lệ. Khi tải dữ liệu cũ, cần có cơ chế phát hiện và xử lý dữ liệu không hợp lệ thay vì giả định rằng mọi bản ghi đều đúng.

## 5. Thể hiện vòng đời bằng trạng thái và chuyển đổi hợp lệ

### 5.1. Trạng thái không chỉ là một chuỗi

Dùng string tự do cho trạng thái dễ tạo ra lỗi chính tả và giá trị không hợp lệ. Có thể biểu diễn tập trạng thái bằng enum:

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED,
    SHIPPED
}
~~~

Enum giới hạn các giá trị có thể biểu diễn, nhưng không tự bảo đảm chuyển đổi hợp lệ. Vẫn cần hành vi kiểm soát vòng đời.

### 5.2. Mô tả state transition

Một sơ đồ chuyển trạng thái giúp chuyên gia và đội phát triển cùng kiểm tra quy tắc:

~~~text
          add/change/remove lines
                    |
                    v
                 DRAFT
                /     \
       cancel /       \ confirm (có dòng hàng)
             v         v
         CANCELLED  CONFIRMED
                       /  \
              cancel /    \ markShipped
                    v      v
                CANCELLED SHIPPED
~~~

Sơ đồ là ví dụ minh họa. Chính sách thực tế có thể cho phép hủy sau khi xác nhận, nhưng yêu cầu hủy có thể cần kiểm tra xem hàng đã được lấy hoặc bàn giao hay chưa.

Cần ghi rõ:

- Trạng thái bắt đầu.
- Hành động được phép.
- Điều kiện trước khi chuyển.
- Trạng thái kết quả.
- Những hành động bị cấm.
- Vai trò hoặc quyền hạn có liên quan.
- Sự kiện miền được tạo ra sau chuyển đổi.

### 5.3. Không cho phép chuyển trạng thái tùy ý

Tránh phương thức kiểu setStatus(nextStatus) nếu nó cho phép bên ngoài chọn bất kỳ trạng thái nào. Thay vào đó, cung cấp các hành vi có ý nghĩa và kiểm tra điều kiện.

~~~java
public void markShipped() {
    if (status != OrderStatus.CONFIRMED) {
        throw new IllegalStateException(
            "Only a confirmed order can be shipped"
        );
    }

    status = OrderStatus.SHIPPED;
}
~~~

Nếu có nhiều nhánh hoặc điều kiện phức tạp, có thể tách các chính sách hoặc state transition thành những thành phần dễ kiểm tra hơn. Tuy nhiên, quyền quyết định cuối cùng vẫn cần nằm ở mô hình sở hữu trạng thái.

## 6. Đặt hành vi đúng vào Entity, Value Object và Aggregate

### 6.1. Entity: hành vi gắn với một danh tính

Entity có danh tính riêng và tồn tại qua nhiều lần thay đổi trạng thái. Hai Entity có cùng thuộc tính vẫn có thể là hai đối tượng khác nhau nếu danh tính khác nhau.

Ví dụ, hai đơn hàng có cùng khách hàng, dòng hàng và tổng tiền vẫn là hai đơn khác nhau vì Order ID khác nhau.

Entity thường sở hữu hành vi làm thay đổi trạng thái của chính nó. Order có thể xác nhận hoặc hủy đơn. Account có thể khóa hoặc mở khóa tài khoản theo chính sách.

Không phải mọi Entity đều cần nhiều phương thức. Hãy đặt hành vi vào Entity khi hành vi đó phụ thuộc vào danh tính, trạng thái hoặc quy tắc thuộc trách nhiệm của Entity.

### 6.2. Value Object: hành vi dựa trên giá trị

Value Object không có danh tính độc lập; nó được xác định bởi giá trị của các thuộc tính và thường nên bất biến.

Ví dụ Money có thể cung cấp:

- Cộng hai khoản tiền cùng loại tiền tệ.
- Nhân với số lượng hợp lệ.
- So sánh giá trị.
- Từ chối phép toán giữa hai loại tiền tệ khác nhau nếu chưa có quy tắc chuyển đổi.

~~~java
public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Money amount cannot be negative"
            );
        }
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money multiply(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                "Quantity cannot be negative"
            );
        }

        return new Money(
            amount.multiply(BigDecimal.valueOf(quantity)),
            currency
        );
    }

    public static Money zero(Currency currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currencies must match"
            );
        }
    }
}
~~~

Money vừa giữ dữ liệu vừa bảo vệ quy tắc của phép toán. Bên gọi không cần tự kiểm tra loại tiền tệ trước mỗi lần cộng.

Ví dụ này minh họa cấu trúc; hệ thống tài chính thực tế còn cần quy định scale, rounding mode, đơn vị tiền tệ không có phần thập phân và quy tắc làm tròn theo nghiệp vụ.

### 6.3. Aggregate: ranh giới bảo vệ invariant

Aggregate là một cụm đối tượng miền được xem như một đơn vị nhất quán. Aggregate Root là điểm truy cập từ bên ngoài và chịu trách nhiệm bảo vệ invariant của cụm.

Ví dụ Order có thể là Aggregate Root, quản lý các OrderLine bên trong. Mã bên ngoài yêu cầu Order thêm hoặc sửa dòng hàng thông qua hành vi của Order, thay vì lấy OrderLine ra rồi thay đổi tùy ý.

Một Aggregate nên có phạm vi vừa đủ để bảo vệ các quy tắc cần nhất quán cùng nhau. Nếu gom quá nhiều đối tượng vào một Aggregate, mọi thay đổi có thể trở nên nặng nề và gây tranh chấp. Nếu chia quá nhỏ, các invariant cần được bảo vệ cùng nhau có thể bị vi phạm.

### 6.4. Repository: lưu và tải Aggregate

Repository cung cấp cách lấy và lưu Aggregate theo ngôn ngữ miền. Application layer thường dùng repository để tải Aggregate, gọi hành vi rồi lưu kết quả.

Repository không nên trở thành nơi chứa quy tắc xác nhận, hủy hoặc tính giá. Nó chịu trách nhiệm truy xuất và lưu trữ; Aggregate chịu trách nhiệm giữ trạng thái nghiệp vụ hợp lệ.

## 7. Ví dụ Java: xây dựng Order có hành vi và invariant

Ví dụ dưới đây dùng Java 17 với record cho Value Object và các kiểu dữ liệu nhỏ. Mục tiêu là minh họa cách đặt quy tắc vào mô hình. Trong dự án thực tế, mỗi public type nên nằm trong file riêng và có thể cần tích hợp với framework persistence.

Để tập trung vào mô hình, các import chuẩn như java.math.BigDecimal và các kiểu trong java.util được lược bỏ khỏi những đoạn mã minh họa.

### 7.1. Định nghĩa các kiểu miền

~~~java
public record OrderId(String value) {
    public OrderId {
        Objects.requireNonNull(value);

        if (value.isBlank()) {
            throw new IllegalArgumentException(
                "Order id is required"
            );
        }
    }
}
~~~

~~~java
public record ProductId(String value) {
    public ProductId {
        Objects.requireNonNull(value);

        if (value.isBlank()) {
            throw new IllegalArgumentException(
                "Product id is required"
            );
        }
    }
}
~~~

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED,
    SHIPPED
}
~~~

OrderLine trong ví dụ là một thành phần được quản lý bên trong Order. Nó bất biến để việc thay đổi số lượng tạo ra một giá trị mới và Order kiểm soát quá trình thay thế.

~~~java
public record OrderLine(
    ProductId productId,
    int quantity,
    Money unitPrice
) {
    public OrderLine {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(unitPrice);

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity);
    }

    public OrderLine withQuantity(int newQuantity) {
        return new OrderLine(productId, newQuantity, unitPrice);
    }
}
~~~

### 7.2. Định nghĩa sự kiện miền

Sự kiện miền biểu diễn một sự việc có ý nghĩa đã xảy ra trong mô hình.

~~~java
public interface DomainEvent {
}
~~~

~~~java
public record OrderConfirmed(
    OrderId orderId,
    Money total
) implements DomainEvent {
}
~~~

~~~java
public record OrderCancelled(
    OrderId orderId,
    String reason
) implements DomainEvent {
}
~~~

~~~java
public record OrderShipped(
    OrderId orderId
) implements DomainEvent {
}
~~~

Các event trên là ví dụ tối giản. Hệ thống thực tế có thể cần event ID, thời điểm xảy ra, phiên bản schema, correlation ID hoặc thông tin truy vết. Không đưa dữ liệu nhạy cảm vào event nếu bên nhận không cần sử dụng.

### 7.3. Xây dựng Aggregate Root

~~~java
public final class Order {

    private final OrderId id;
    private final Currency currency;
    private final Map<ProductId, OrderLine> lines =
        new LinkedHashMap<>();

    private final List<DomainEvent> domainEvents =
        new ArrayList<>();

    private OrderStatus status = OrderStatus.DRAFT;

    public Order(OrderId id, Currency currency) {
        this.id = Objects.requireNonNull(id);
        this.currency = Objects.requireNonNull(currency);
    }

    public void addLine(
        ProductId productId,
        int quantity,
        Money unitPrice
    ) {
        ensureDraft();
        ensureCurrency(unitPrice);

        if (lines.containsKey(productId)) {
            throw new IllegalArgumentException(
                "Product already exists in order"
            );
        }

        lines.put(
            productId,
            new OrderLine(productId, quantity, unitPrice)
        );
    }

    public void changeQuantity(
        ProductId productId,
        int newQuantity
    ) {
        ensureDraft();

        OrderLine current = requireLine(productId);
        lines.put(
            productId,
            current.withQuantity(newQuantity)
        );
    }

    public void removeLine(ProductId productId) {
        ensureDraft();

        if (lines.remove(productId) == null) {
            throw new IllegalArgumentException(
                "Order line does not exist"
            );
        }
    }

    public void confirm() {
        ensureDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An empty order cannot be confirmed"
            );
        }

        status = OrderStatus.CONFIRMED;
        domainEvents.add(
            new OrderConfirmed(id, total())
        );
    }

    public void cancel(String reason) {
        if (status == OrderStatus.SHIPPED) {
            throw new IllegalStateException(
                "A shipped order cannot be cancelled"
            );
        }

        if (status == OrderStatus.CANCELLED) {
            throw new IllegalStateException(
                "Order is already cancelled"
            );
        }

        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException(
                "Cancellation reason is required"
            );
        }

        status = OrderStatus.CANCELLED;
        domainEvents.add(
            new OrderCancelled(id, reason)
        );
    }

    public void markShipped() {
        if (status != OrderStatus.CONFIRMED) {
            throw new IllegalStateException(
                "Only a confirmed order can be shipped"
            );
        }

        status = OrderStatus.SHIPPED;
        domainEvents.add(new OrderShipped(id));
    }

    public Money total() {
        Money result = Money.zero(currency);

        for (OrderLine line : lines.values()) {
            result = result.add(line.subtotal());
        }

        return result;
    }

    public OrderId id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines.values());
    }

    public List<DomainEvent> pullDomainEvents() {
        List<DomainEvent> result =
            List.copyOf(domainEvents);

        domainEvents.clear();
        return result;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be modified"
            );
        }
    }

    private void ensureCurrency(Money money) {
        if (!currency.equals(money.currency())) {
            throw new IllegalArgumentException(
                "Order line currency must match order currency"
            );
        }
    }

    private OrderLine requireLine(ProductId productId) {
        OrderLine line = lines.get(productId);

        if (line == null) {
            throw new IllegalArgumentException(
                "Order line does not exist"
            );
        }

        return line;
    }
}
~~~

Phương thức pullDomainEvents trong ví dụ chỉ minh họa cách Aggregate cung cấp các sự kiện đã ghi nhận. Ứng dụng thực tế cần lưu sự kiện bền vững cùng transaction của Aggregate, chẳng hạn qua Transactional Outbox; không xóa sự kiện khỏi bộ nhớ trước khi cơ chế lưu trữ sự kiện đã tiếp nhận thành công.

### 7.4. Những invariant mà Order bảo vệ

| Invariant | Nơi bảo vệ | Cách bảo vệ |
|---|---|---|
| Mã đơn không rỗng | OrderId | Kiểm tra khi tạo Value Object |
| Mã sản phẩm không rỗng | ProductId | Kiểm tra khi tạo Value Object |
| Số lượng dòng hàng lớn hơn 0 | OrderLine | Constructor kiểm tra |
| Tiền tệ dòng hàng trùng tiền tệ đơn | Order | ensureCurrency |
| Không thêm trùng mã sản phẩm | Order | addLine kiểm tra map |
| Chỉ đơn Nháp mới được sửa | Order | ensureDraft |
| Đơn rỗng không được xác nhận | Order | confirm |
| Chỉ đơn đã xác nhận mới được giao | Order | markShipped |
| Không hủy đơn đã giao | Order | cancel |

Khi các hành vi công khai đều đi qua Aggregate Root, những điều kiện này không phụ thuộc vào việc controller hoặc application service có nhớ kiểm tra hay không.

Ví dụ chỉ minh họa một chính sách đơn hàng. Doanh nghiệp có thể cho phép chỉnh sửa đơn sau xác nhận trong một khoảng thời gian, hủy đơn sau khi đóng gói với phê duyệt, hoặc có trạng thái riêng cho giao hàng một phần. Khi đó cần điều chỉnh mô hình theo quy tắc đã xác nhận với chuyên gia.

### 7.5. Hạn chế của ví dụ và điều cần làm rõ trước khi dùng thực tế

Ví dụ trên cố ý giữ đơn giản. Một hệ thống thực tế cần làm rõ thêm:

- Giá dòng hàng là giá tại thời điểm đặt hay giá hiện tại của danh mục?
- Thuế, chiết khấu và phí vận chuyển được tính ở đâu?
- Một sản phẩm có được xuất hiện thành nhiều dòng hàng không?
- Đơn có thể giao một phần không?
- Hủy đơn sau khi đã giữ hàng có cần giải phóng Reservation không?
- Thanh toán có thể thành công sau khi đơn đã hết hạn không?
- Ai được quyền hủy hoặc xác nhận đơn?
- Sự kiện miền được lưu cùng Aggregate thế nào để tránh mất event khi tiến trình gặp sự cố?

Không nên bổ sung các quy tắc trên bằng suy đoán kỹ thuật. Chúng cần được khám phá trong miền nghiệp vụ.

## 8. Phân chia trách nhiệm giữa Domain, Application và Infrastructure

Rich Domain Model không có nghĩa mọi thứ phải nằm trong Entity. Mỗi lớp nên giữ đúng loại trách nhiệm.

### 8.1. Domain Model

Domain layer chứa khái niệm và quy tắc nghiệp vụ:

- Entity và Value Object.
- Aggregate và Aggregate Root.
- Domain Service khi hành vi không thuộc tự nhiên một Entity hoặc Value Object.
- Domain Event.
- Các chính sách và đặc tả nghiệp vụ khi cần.

Domain Model không nên phụ thuộc trực tiếp vào HTTP request, controller, SQL, message broker hoặc framework cụ thể.

### 8.2. Application Service

Application Service điều phối một ca sử dụng:

1. Nhận yêu cầu từ giao diện hoặc message handler.
2. Tải Aggregate qua repository.
3. Gọi hành vi nghiệp vụ.
4. Lưu Aggregate.
5. Điều phối việc phát hoặc xử lý sự kiện theo cơ chế của ứng dụng.
6. Trả kết quả cho bên gọi.

Ví dụ:

~~~java
public class ConfirmOrderUseCase {

    private final OrderRepository orderRepository;
    private final UnitOfWork unitOfWork;

    public ConfirmOrderUseCase(
        OrderRepository orderRepository,
        UnitOfWork unitOfWork
    ) {
        this.orderRepository = orderRepository;
        this.unitOfWork = unitOfWork;
    }

    public void execute(OrderId orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);

        order.confirm();

        orderRepository.save(order);
        unitOfWork.commit();
    }
}
~~~

Application Service không tự kiểm tra danh sách dòng hàng rồi gán trạng thái. Nó yêu cầu Order thực hiện hành vi và để Order bảo vệ invariant.

Trong triển khai thực tế, transaction boundary và phát event cần được thiết kế để tránh tình trạng lưu Aggregate thành công nhưng event bị mất, hoặc event được phát khi transaction chưa commit. Transactional Outbox là một kỹ thuật thường được cân nhắc cho trường hợp này.

### 8.3. Repository

Repository tập trung vào việc truy xuất và lưu Aggregate:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);

    void save(Order order);
}
~~~

Repository không nên có các phương thức mang logic nghiệp vụ như confirmOrder, cancelOrder hoặc calculateBusinessEligibility nếu các quyết định đó thuộc mô hình miền. Repository có thể cung cấp truy vấn phục vụ việc tìm Aggregate, nhưng hành vi vẫn được thực hiện trên Aggregate.

### 8.4. Domain Service

Một số quy tắc liên quan đến nhiều Entity hoặc Value Object mà không có đối tượng nào sở hữu tự nhiên. Khi đó có thể dùng Domain Service.

Ví dụ, tính điều kiện đủ tiêu chuẩn cho một chính sách định giá có thể cần thông tin về khách hàng, hợp đồng và sản phẩm. Nếu đây là một quyết định nghiệp vụ, có thể biểu diễn bằng dịch vụ miền với tên theo ngôn ngữ nghiệp vụ.

Domain Service nên stateless, có tên thể hiện hành vi miền và không trở thành nơi chứa toàn bộ logic chỉ vì dễ gọi. Nếu hành vi thực sự thuộc Order hoặc một Aggregate cụ thể, hãy đặt nó ở đó.

### 8.5. Infrastructure

Infrastructure thực hiện chi tiết kỹ thuật như:

- Kết nối cơ sở dữ liệu.
- ORM và mapping.
- Gửi message.
- Gọi dịch vụ thanh toán.
- Lưu trữ file.
- Ghi log và telemetry.

Infrastructure hỗ trợ mô hình miền hoạt động. Nó không nên trở thành nơi quyết định các quy tắc như đơn có được xác nhận hay không.

## 9. Cách tìm hành vi và invariant từ nghiệp vụ

Để tránh thiết kế mô hình từ phỏng đoán, hãy khám phá hành vi qua tình huống và quyết định thực tế.

### 9.1. Bắt đầu bằng động từ nghiệp vụ

Đọc lại mô tả công việc và ghi các động từ:

- Xác nhận đơn.
- Giữ hàng.
- Phê duyệt hồ sơ.
- Đánh giá rủi ro.
- Hủy yêu cầu.
- Hoàn tiền.
- Bàn giao lô hàng.

Với mỗi động từ, hỏi ai có quyền thực hiện, điều kiện trước khi thực hiện, kết quả sau hành động và lý do từ chối.

### 9.2. Tìm câu chứa từ chỉ điều kiện

Các từ thường hé lộ invariant hoặc business rule:

- Chỉ khi...
- Không được...
- Phải luôn...
- Trừ khi...
- Tối đa...
- Ít nhất...
- Trong thời hạn...
- Khi và chỉ khi...

Ví dụ: “Chỉ khi khách đã xác nhận phương án thay thế thì nhân viên mới được tiếp tục xử lý đơn.” Câu này có thể dẫn đến một hành vi xác nhận phương án và một điều kiện chuyển trạng thái.

### 9.3. Dùng ví dụ và phản ví dụ

Với mỗi quy tắc, hãy tìm:

- Một trường hợp quy tắc được áp dụng.
- Một trường hợp gần giống nhưng không áp dụng.
- Một trường hợp ngoại lệ có quyền phê duyệt đặc biệt.
- Một trường hợp dữ liệu thiếu hoặc đến muộn.

Ví dụ, nếu “đơn đã xác nhận không được sửa” là quy tắc, hãy hỏi liệu nhân viên có được sửa địa chỉ giao hàng hay không, trong điều kiện nào, và thay đổi đó có ảnh hưởng đến giá, thuế hoặc vận chuyển không.

### 9.4. Xác định phạm vi của invariant

Một điều kiện có thể thuộc nhiều phạm vi:

- Thuộc Value Object: tiền không âm, mã định danh không rỗng.
- Thuộc Entity: tài khoản đã khóa không thể tự thực hiện hành động yêu cầu quyền hoạt động.
- Thuộc Aggregate: đơn rỗng không được xác nhận.
- Thuộc quy trình nhiều Aggregate: chỉ khởi tạo giao hàng khi đã có giữ hàng và điều kiện thanh toán phù hợp.
- Thuộc nhiều Bounded Context: một quy trình phải điều phối kết quả từ các mô hình độc lập.

Xác định phạm vi giúp tránh đặt quy tắc quá thấp hoặc quá cao. Một quy tắc không nên bị lặp ở nhiều nơi mà không có một chủ sở hữu rõ ràng.

### 9.5. Viết quy tắc thành ví dụ có thể kiểm tra

Có thể dùng bảng:

| Given (điều kiện ban đầu) | When (hành động) | Then (kết quả mong đợi) |
|---|---|---|
| Đơn Nháp có ít nhất một dòng hàng | Xác nhận đơn | Đơn chuyển sang Đã xác nhận |
| Đơn Nháp không có dòng hàng | Xác nhận đơn | Hành động bị từ chối |
| Đơn đã xác nhận | Thay đổi số lượng | Hành động bị từ chối theo chính sách ví dụ |
| Đơn đã giao | Hủy đơn | Hành động bị từ chối |
| Dòng hàng có số lượng bằng 0 | Tạo dòng hàng | Không tạo được OrderLine |

Các ví dụ này có thể trở thành unit test cho mô hình miền. Khi chuyên gia thay đổi quy tắc, đội phát triển cập nhật ví dụ và kiểm thử tương ứng.

## 10. Kiểm thử hành vi và invariant

### 10.1. Kiểm thử hành vi qua API miền

Kiểm thử nên gọi các hành vi công khai, không sửa trực tiếp field nội bộ. Điều này kiểm tra cách người dùng mô hình thực sự tương tác với đối tượng.

~~~java
@Test
void shouldConfirmDraftOrderWithLines() {
    Order order = new Order(
        new OrderId("ORD-1"),
        Currency.getInstance("VND")
    );

    order.addLine(
        new ProductId("P-1"),
        2,
        new Money(
            new BigDecimal("100000"),
            Currency.getInstance("VND")
        )
    );

    order.confirm();

    assertEquals(OrderStatus.CONFIRMED, order.status());
}
~~~

~~~java
@Test
void shouldRejectConfirmationWhenOrderIsEmpty() {
    Order order = new Order(
        new OrderId("ORD-2"),
        Currency.getInstance("VND")
    );

    assertThrows(
        IllegalStateException.class,
        order::confirm
    );

    assertEquals(OrderStatus.DRAFT, order.status());
}
~~~

Bài kiểm thử thứ hai xác nhận hai điều: hành động bị từ chối và trạng thái không bị thay đổi. Một phương thức thất bại không được để lại Aggregate ở trạng thái nửa chừng.

### 10.2. Kiểm thử Value Object

Value Object nên được kiểm tra ở các phép toán và điều kiện hợp lệ:

- Money cộng hai khoản cùng tiền tệ.
- Money từ chối phép cộng khác tiền tệ.
- Quantity không chấp nhận giá trị không hợp lệ.
- Địa chỉ hoặc khoảng thời gian tuân thủ điều kiện của miền.

### 10.3. Kiểm thử chuyển trạng thái

Với mỗi trạng thái, liệt kê hành động được phép và bị cấm. Có thể tạo bảng quyết định hoặc state transition table để tránh bỏ sót nhánh.

Không cần kiểm thử mọi tổ hợp nếu chúng không có ý nghĩa nghiệp vụ. Ưu tiên các chuyển đổi hợp lệ, chuyển đổi bị cấm và các trường hợp biên quan trọng.

### 10.4. Kiểm thử ở cấp độ Aggregate và tích hợp

Unit test kiểm tra invariant nội bộ. Integration test cần xác nhận repository lưu và tải lại Aggregate mà không làm mất ý nghĩa hoặc phá vỡ trạng thái. Với event, cần kiểm tra event chỉ được công bố theo cơ chế đã thống nhất sau khi thay đổi được commit.

Không nên dùng unit test để mô phỏng lại toàn bộ logic của implementation. Kiểm thử cần xác nhận hành vi quan sát được và các cam kết nghiệp vụ.

## 11. Những sai lầm thường gặp khi mô hình hóa hành vi

### Chỉ chuyển setter thành các phương thức có tên đẹp

Một phương thức setConfirmed() vẫn là setter nếu nó chỉ gán trạng thái mà không kiểm tra điều kiện và bảo vệ quy tắc. Hành vi cần diễn đạt quyết định nghiệp vụ, không chỉ đổi tên thao tác kỹ thuật.

### Đưa tất cả logic vào một Service

Nếu mọi hành vi đều nằm trong OrderService, CustomerService hoặc một DomainManager khổng lồ, Entity vẫn chỉ là túi dữ liệu. Hãy đặt hành vi gần dữ liệu và invariant mà nó bảo vệ.

### Đưa mọi logic vào Entity

Không phải mọi quy tắc đều thuộc một Entity. Hành vi phối hợp nhiều Aggregate có thể thuộc Domain Service hoặc Application Service tùy bản chất. Việc gọi hệ thống bên ngoài và điều phối transaction thuộc application/infrastructure.

### Công khai setter để ORM dễ lưu

Tiện lợi của framework không nên làm mất khả năng bảo vệ invariant. Hãy chọn mapping, constructor hoặc factory phù hợp và giữ API miền rõ ràng. Nếu framework cần constructor hoặc accessor đặc biệt, giới hạn phạm vi truy cập theo khả năng của framework và dự án.

### Tính lại dữ liệu theo nhiều cách

Nếu tổng tiền có thể được cập nhật từ dòng hàng ở nhiều nơi, chúng có thể lệch nhau. Hãy xác định giá trị nào là nguồn sự thật, giá trị nào có thể tính lại và quy tắc làm tròn thuộc đâu.

### Dùng trạng thái tự do và cho phép chuyển tùy ý

String trạng thái cùng setter công khai dễ tạo ra giá trị sai và chuyển đổi bất hợp lệ. Dùng kiểu trạng thái rõ ràng và phương thức thể hiện hành vi.

### Bảo vệ invariant chỉ ở giao diện

Một API khác, batch job hoặc message handler có thể bỏ qua validation giao diện. Mô hình miền phải tự bảo vệ các quy tắc cốt lõi.

### Tạo Aggregate quá lớn

Đưa mọi đối tượng liên quan đến một đơn hàng vào cùng Aggregate có thể làm tăng tải, tranh chấp và khó thay đổi. Chỉ giữ trong Aggregate những gì cần được bảo đảm nhất quán cùng nhau.

### Nhầm invariant với quy trình toàn hệ thống

Một quy trình gồm nhiều Bounded Context không thể luôn được bảo vệ bằng một Aggregate. Hãy dùng điều phối, sự kiện và hành động bù trừ khi phù hợp.

## 12. Checklist xây dựng mô hình giàu hành vi

Trước khi xem một mô hình là đủ rõ, hãy kiểm tra:

- Các khái niệm chính được đặt tên theo ngôn ngữ nghiệp vụ.
- Entity có danh tính và hành vi phù hợp với vòng đời.
- Value Object có tính bất biến và bảo vệ điều kiện của giá trị.
- Aggregate Root kiểm soát các thay đổi cần bảo vệ cùng nhau.
- Không có setter công khai làm phá vỡ invariant quan trọng.
- Các collection nội bộ không bị sửa trực tiếp từ bên ngoài.
- Các hành vi có tên diễn đạt ý định nghiệp vụ.
- Mỗi hành vi kiểm tra điều kiện và chuyển trạng thái hợp lệ.
- Domain Event chỉ mô tả sự việc đã xảy ra.
- Application Service điều phối use case, không chiếm quyền sở hữu quy tắc miền.
- Repository lưu và tải Aggregate, không thay thế hành vi nghiệp vụ.
- Các quy tắc đã được chuyển thành ví dụ và kiểm thử.
- Mức độ phức tạp của mô hình phù hợp với độ phức tạp thực tế của nghiệp vụ.

## 13. Bài tập thực hành: mô hình hóa yêu cầu hoàn tiền

Một cửa hàng trực tuyến nhận yêu cầu hoàn tiền cho đơn hàng đã thanh toán. Chính sách giả định:

- Chỉ đơn đã thanh toán mới đủ điều kiện gửi yêu cầu hoàn tiền.
- Số tiền yêu cầu phải lớn hơn 0 và không vượt quá số tiền còn có thể hoàn.
- Một đơn có thể được hoàn nhiều lần nếu tổng số tiền không vượt quá giới hạn.
- Khi yêu cầu được chấp nhận, hệ thống ghi nhận một yêu cầu hoàn tiền đang chờ xử lý.
- Chỉ khi nhà cung cấp thanh toán xác nhận hoàn thành thì số tiền mới được ghi nhận là đã hoàn.

Hãy thực hiện:

1. Xác định Entity, Value Object và Aggregate phù hợp.
2. Liệt kê các invariant của từng đối tượng.
3. Đề xuất hành vi để gửi yêu cầu, chấp nhận, từ chối và ghi nhận kết quả.
4. Phân biệt lệnh yêu cầu hoàn tiền với sự kiện hoàn tiền hoàn thành.
5. Xác định trách nhiệm của Application Service và Payment Gateway Adapter.
6. Viết các trường hợp Given-When-Then cho yêu cầu hợp lệ, vượt số tiền còn lại, thanh toán chưa hoàn tất và phản hồi nhà cung cấp đến muộn.

### 13.1. Gợi ý mô hình

Có thể có:

- Payment là Aggregate sở hữu số tiền đã thu và số tiền đã hoàn.
- Money là Value Object bảo vệ loại tiền và phép toán.
- RefundRequest có thể là Entity nếu có vòng đời và danh tính riêng.
- Payment có hành vi requestRefund(amount), nhưng việc thực sự ghi nhận hoàn thành chỉ xảy ra khi nhận kết quả đã xác minh từ nhà cung cấp.

Một chính sách quan trọng là không trừ số tiền đã hoàn ngay khi chỉ gửi yêu cầu. Có thể cần theo dõi số tiền đang chờ hoàn để tránh nhiều yêu cầu đồng thời vượt quá giới hạn. Đây là invariant cần được chuyên gia xác nhận và mô hình hóa theo cách doanh nghiệp quản lý giao dịch.

### 13.2. Một số ví dụ kiểm thử

| Given | When | Then |
|---|---|---|
| Payment đã thu 1.000.000 VND, chưa có yêu cầu hoàn | Yêu cầu hoàn 300.000 VND | Yêu cầu được ghi nhận nếu chính sách cho phép |
| Payment chưa được thu tiền | Yêu cầu hoàn tiền | Bị từ chối |
| Đã hoàn thành 800.000 VND | Yêu cầu hoàn thêm 300.000 VND trên giới hạn 1.000.000 VND | Bị từ chối |
| Yêu cầu hoàn đang chờ nhà cung cấp | Callback chưa đến | Không đánh dấu đã hoàn thành |
| Nhà cung cấp xác nhận hoàn thành | Ghi nhận kết quả | Số tiền đã hoàn được cập nhật và phát sự kiện phù hợp |

Các tình huống này là dữ liệu kiểm thử cho chính sách giả định. Hệ thống thực tế cần xác nhận cách xử lý nhiều yêu cầu đang chờ, callback trùng lặp, hoàn một phần và đối soát.

## Kết luận

Mô hình miền trong DDD cần thể hiện hành vi và bảo vệ bất biến để phản ánh cách doanh nghiệp thực sự đưa ra quyết định. Entity, Value Object và Aggregate không chỉ là các cấu trúc dữ liệu; chúng là nơi diễn đạt ý nghĩa, hành động, trạng thái và điều kiện hợp lệ của miền.

Khi hành vi được đặt đúng chỗ, bên ngoài không cần tự sửa nhiều thuộc tính hoặc ghi nhớ mọi quy tắc. Application Service điều phối ca sử dụng, Repository quản lý việc lưu và tải Aggregate, còn Domain Model giữ quyền quyết định đối với các quy tắc nghiệp vụ mà nó sở hữu. Bắt đầu từ tình huống thực tế, xác định invariant, mô tả chuyển trạng thái và kiểm thử hành vi giúp mô hình trở thành ngôn ngữ có thể trao đổi giữa chuyên gia và đội phát triển.

