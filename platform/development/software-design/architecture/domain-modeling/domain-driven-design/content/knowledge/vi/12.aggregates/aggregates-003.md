# Xác định bất biến cần được bảo vệ trong cùng giao dịch

Trong Domain-Driven Design (DDD), **Aggregate** là một ranh giới nhất quán của mô hình miền. Nó gom một Aggregate Root cùng các đối tượng liên quan để bảo vệ những điều kiện nghiệp vụ phải luôn đúng khi một thay đổi được ghi nhận. Các đối tượng bên ngoài chỉ yêu cầu thay đổi thông qua Aggregate Root; root kiểm tra quy tắc và điều phối cập nhật trước khi trạng thái mới được lưu.

Một quyết định quan trọng khi thiết kế Aggregate là xác định **invariant** nào cần được bảo vệ trong cùng một giao dịch. Nếu một quy tắc đòi hỏi nhiều dữ liệu phải thay đổi nguyên tử, các dữ liệu đó có thể cần nằm trong cùng ranh giới Aggregate. Nếu một quy tắc có thể được phối hợp qua nhiều bước và chấp nhận trạng thái tạm thời, nó có thể phù hợp với quy trình hoặc chính sách xuyên Aggregate thay vì mở rộng một Aggregate thật lớn.

Ví dụ, trong quản lý tồn kho, số lượng đã giữ không được vượt quá số lượng có thể đáp ứng. Hai yêu cầu giữ hàng đồng thời không được cùng đọc một lượng tồn cũ rồi cùng xác nhận khiến tồn khả dụng âm. Quy tắc này cần được bảo vệ tại nơi sở hữu tồn kho bằng một thao tác có kiểm soát đồng thời. Trong khi đó, việc một đơn hàng được giao thành công và hóa đơn được phát hành có thể liên quan nhiều context và cần một quy trình phối hợp.

Bài học này trình bày cách nhận diện invariant, phân biệt chúng với validation thông thường, xác định ranh giới nhất quán, hiện thực giao dịch và xử lý các quy tắc vượt qua nhiều Aggregate.

## 1. Invariant là gì?

**Invariant** là điều kiện nghiệp vụ phải luôn đúng đối với mô hình trong phạm vi mà nó bảo vệ. Khi một hành động được chấp nhận và giao dịch hoàn tất, invariant phải tiếp tục được thỏa mãn.

Ví dụ:

- Số lượng hàng đã giữ không được vượt quá lượng hàng có thể đáp ứng.
- Một đơn hàng đã xác nhận phải có ít nhất một dòng hàng.
- Tổng tiền của đơn phải được tính từ các dòng hàng theo chính sách giá và thuế đã áp dụng.
- Một khoản phân bổ không được vượt quá hạn mức được cấp.
- Một kỳ hợp đồng đã đóng không được nhận thêm giao dịch thuộc kỳ đó, trừ quy trình điều chỉnh được cho phép.
- Một reservation đã giải phóng không thể được giải phóng lần nữa như một hành động mới.

Invariant không chỉ là điều kiện dữ liệu hợp lệ. Nó phản ánh một sự thật mà nghiệp vụ yêu cầu phải được giữ vững. Nếu vi phạm, mô hình có thể đưa ra quyết định sai, mất tiền, bán vượt hàng, phá vỡ cam kết hoặc làm sai lịch sử giao dịch.

### 1.1. Invariant được kiểm tra tại thời điểm nào?

Trong mô hình miền, một đối tượng có thể đi qua các bước nội bộ khi thực hiện một hành vi. Điều cần bảo đảm là trạng thái được công bố và commit phải hợp lệ. Ví dụ, phương thức có thể tính toán các giá trị tạm thời, nhưng không được để một giao dịch hoàn tất với `reservedQuantity` lớn hơn `onHandQuantity`.

Invariant thường được kiểm tra:

- Khi tạo Aggregate hoặc khôi phục dữ liệu vào mô hình miền.
- Trước hoặc trong hành vi làm thay đổi trạng thái liên quan.
- Khi hoàn tất giao dịch và lưu Aggregate.
- Khi xử lý cạnh tranh cập nhật để tránh một trạng thái hợp lệ riêng lẻ nhưng sai khi xét đồng thời.

Kiểm tra trong constructor hoặc method là cần thiết, nhưng chưa đủ nếu nhiều giao dịch đồng thời có thể ghi đè kết quả của nhau. Tính nhất quán còn phụ thuộc vào cơ chế transaction và concurrency control ở tầng lưu trữ.

## 2. Phân biệt invariant với validation và business rule

Các khái niệm này có liên quan nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Input validation | Kiểm tra dữ liệu đầu vào có đúng định dạng và đủ điều kiện cơ bản không | Mã SKU không rỗng, số lượng là số dương |
| Business rule | Quy tắc nghiệp vụ quyết định hành động hoặc kết quả | Khách hàng hạng Gold được hưởng chính sách giảm giá |
| Invariant | Điều kiện phải được duy trì trong ranh giới nhất quán | Tổng số lượng giữ không vượt quá tồn có thể đáp ứng |
| Authorization | Kiểm tra chủ thể có quyền thực hiện hành động không | Chỉ nhân viên được phân quyền mới điều chỉnh tồn |
| Process policy | Điều phối hành động khi một sự kiện xảy ra | Khi thanh toán được ghi nhận, yêu cầu xác nhận đơn nếu đơn còn hiệu lực |

Một business rule có thể tạo thành invariant nếu nó phải luôn đúng trong một ranh giới giao dịch. Nhưng không phải mọi rule đều là invariant. Ví dụ, “gửi email sau khi đơn được xác nhận” là một policy hoặc hành động hậu xử lý, không phải điều kiện cấu trúc phải luôn đúng bên trong Order Aggregate.

Tương tự, kiểm tra số lượng lớn hơn 0 là validation hoặc một quy tắc của Value Object. Quy tắc “tổng lượng đã giữ không vượt lượng có thể đáp ứng” là invariant của mô hình tồn kho vì nó phụ thuộc vào nhiều giá trị và phải được bảo vệ khi các yêu cầu cạnh tranh.

## 3. Vì sao invariant quyết định ranh giới Aggregate?

Aggregate không nên được hình thành chỉ bằng cách nhóm các đối tượng có quan hệ hoặc có cùng tên miền. Ranh giới nên xuất phát từ những quy tắc cần được bảo vệ nhất quán.

Hãy đặt câu hỏi:

- Những dữ liệu nào phải được đọc và thay đổi cùng nhau để một quyết định hợp lệ?
- Nếu chỉ cập nhật một phần dữ liệu, trạng thái trung gian có thể vi phạm quy tắc nào?
- Ai chịu trách nhiệm quyết định thay đổi đó?
- Có cần đảm bảo tất cả thay đổi được commit hoặc rollback cùng nhau không?
- Quy tắc có thể được thực hiện bằng một bước đặt chỗ, xác nhận hoặc bù trừ không?
- Có thể chấp nhận trạng thái tạm thời trong khi các Aggregate khác được cập nhật không?

Nếu nhiều đối tượng phải cùng thay đổi nguyên tử để bảo vệ một invariant, chúng là ứng viên để nằm trong cùng Aggregate. Nếu chúng có vòng đời và quyền sở hữu riêng, việc tham chiếu qua ID và phối hợp bằng sự kiện có thể phù hợp hơn.

### 3.1. Ranh giới nhất quán không phải ranh giới toàn bộ quy trình

Một quy trình đặt hàng có thể gồm tạo đơn, giữ hàng, thu tiền, đóng gói, giao hàng và phát hành hóa đơn. Không có nghĩa tất cả dữ liệu này phải nằm trong một Aggregate. Mỗi phần có thể có invariant riêng:

- Order Aggregate bảo vệ dòng hàng, trạng thái và tổng tiền theo chính sách của đơn.
- Inventory Aggregate bảo vệ lượng hàng khả dụng và reservation.
- Payment Aggregate bảo vệ giao dịch và trạng thái ghi nhận tiền.
- Shipment Aggregate bảo vệ kiện hàng và tiến trình bàn giao.

Quy trình tổng thể điều phối các Aggregate qua command, event và các bước xử lý. Một bước thất bại có thể dẫn đến retry, đối soát hoặc hành động bù trừ.

## 4. Cách khám phá invariant từ nghiệp vụ

Không nên bắt đầu bằng câu hỏi “Aggregate này có những field nào?”. Hãy bắt đầu từ các quyết định nghiệp vụ có hậu quả nếu sai.

### 4.1. Tìm quyết định cần được bảo vệ

Hỏi chuyên gia nghiệp vụ:

- Điều gì tuyệt đối không được xảy ra?
- Khi nào một hành động phải bị từ chối?
- Có hai yêu cầu đồng thời nào có thể khiến kết quả sai không?
- Những giá trị nào phải luôn khớp nhau?
- Khi thay đổi một giá trị, những giá trị nào bắt buộc phải thay đổi theo?
- Nếu quy tắc bị vi phạm, hậu quả đối với khách hàng, tài chính hoặc vận hành là gì?
- Ai có quyền tạo ngoại lệ và ngoại lệ có cần được ghi nhận không?

Yêu cầu người tham gia kể một tình huống thật: đơn vượt tồn, khoản chi vượt hạn mức, hai người cùng phê duyệt hoặc một giao dịch được ghi nhận hai lần. Tình huống cụ thể thường làm lộ invariant rõ hơn một danh sách thuộc tính.

### 4.2. Tìm điều kiện trước và sau hành động

Với mỗi command, ghi:

- **Precondition:** điều kiện cần có trước khi hành động được chấp nhận.
- **Hành động:** quyết định hoặc phép biến đổi được thực hiện.
- **Postcondition:** kết quả phải đúng sau khi hành động hoàn tất.
- **Invariant liên quan:** điều kiện phải tiếp tục đúng sau mọi hành động hợp lệ.

Ví dụ command `ReserveStock`:

| Thành phần | Nội dung minh họa |
|---|---|
| Precondition | Số lượng yêu cầu dương; SKU và địa điểm hợp lệ; reservation chưa được xử lý với cùng request ID |
| Hành động | Tạo reservation và tăng lượng đã giữ |
| Postcondition | Reservation được ghi nhận; lượng đã giữ được cập nhật |
| Invariant | Lượng đã giữ không vượt lượng tồn có thể đáp ứng |
| Kết quả từ chối | Không đủ hàng, yêu cầu trùng không tương thích hoặc trạng thái không cho phép |

Precondition của một command không tự động là invariant. Ví dụ “người gọi có quyền” có thể được kiểm tra ở application/security boundary; còn số lượng giữ không vượt khả năng đáp ứng phải được bảo vệ trong mô hình tồn kho và giao dịch lưu trữ.

### 4.3. Tìm giá trị biên và trường hợp đồng thời

Với mỗi quy tắc định lượng hoặc thời gian, kiểm tra:

- Giá trị thấp hơn giới hạn.
- Đúng bằng giới hạn.
- Cao hơn giới hạn.
- Hai yêu cầu cùng đọc trạng thái trước khi cập nhật.
- Một yêu cầu được gửi lại sau timeout.
- Dữ liệu hoặc sự kiện đến muộn.
- Một phần thao tác thành công nhưng phần còn lại thất bại.

Ví dụ, nếu tồn khả dụng là 5, hai yêu cầu cùng giữ 4 đơn vị không thể đều thành công. Kiểm tra đơn lẻ mỗi request trên snapshot cũ có thể cho kết quả sai; cần cơ chế bảo vệ khi commit.

## 5. Xác định Aggregate Root và các đối tượng bên trong

Sau khi nhận diện invariant, nhóm mới quyết định đối tượng nào cần nằm trong Aggregate.

### 5.1. Aggregate Root là điểm vào duy nhất

Aggregate Root là Entity có identity và chịu trách nhiệm bảo vệ invariant của Aggregate. Các đối tượng bên ngoài yêu cầu thay đổi thông qua root, thay vì sửa trực tiếp child entity hoặc collection nội bộ.

Ví dụ một `Order` có thể chứa:

- `OrderLine` là entity con hoặc thành phần có identity trong phạm vi đơn.
- `Money`, `ProductReference`, `Quantity` là Value Object.
- Trạng thái đơn và các quy tắc xác nhận/hủy.

Nếu một dòng hàng thay đổi số lượng, root có thể kiểm tra trạng thái đơn, số lượng hợp lệ và cập nhật tổng tiền hoặc các thông tin liên quan. Consumer không tự sửa collection `lines` từ bên ngoài.

### 5.2. Tham chiếu Aggregate khác bằng identity

Thông thường, một Aggregate nên tham chiếu Aggregate khác bằng ID thay vì giữ toàn bộ object graph. Ví dụ Order lưu `CustomerId` và `WarehouseId`, không cần nhúng toàn bộ Customer Aggregate hoặc Warehouse Aggregate vào trong Order.

Điều này giúp:

- Tránh một giao dịch vô tình cập nhật nhiều Aggregate.
- Giữ quyền sở hữu trạng thái rõ ràng.
- Giảm tải object graph và phụ thuộc mô hình.
- Cho phép mỗi Aggregate có vòng đời và cơ chế concurrency riêng.

Nếu cần thông tin từ Aggregate khác, application service có thể truy vấn hoặc gọi contract phù hợp rồi truyền dữ liệu cần thiết vào hành vi. Cần xác định rõ dữ liệu nào là snapshot, dữ liệu tham chiếu hay quyết định có thẩm quyền.

### 5.3. Không đưa mọi đối tượng liên quan vào một Aggregate

Một đơn hàng có thể liên quan đến khách hàng, sản phẩm, tồn kho, thanh toán, vận chuyển và hóa đơn. Nếu nhúng tất cả vào một Aggregate, mỗi thay đổi nhỏ đều có thể yêu cầu nạp và khóa một lượng dữ liệu lớn, đồng thời tạo giao dịch dài và cạnh tranh cao.

Chỉ giữ các đối tượng cần thiết để bảo vệ invariant của root. Quan hệ nghiệp vụ không đồng nghĩa với quan hệ sở hữu trong Aggregate.

## 6. Ví dụ: bảo vệ invariant của tồn kho

Giả sử Inventory Context quản lý lượng hàng tại từng địa điểm. Quy tắc nghiệp vụ là không được giữ nhiều hàng hơn số lượng có thể đáp ứng.

### 6.1. Định nghĩa invariant

Gọi:

- (H): số lượng hàng hiện có được tính cho mục đích phân bổ.
- (R): tổng số lượng đang được giữ và chưa giải phóng/xuất kho.
- (A): số lượng khả dụng.

Ta có:

\[
A = H - R
\]

Invariant:

\[
H \geq 0,\quad R \geq 0,\quad R \leq H
\]

Vì vậy (A \geq 0). Nếu nghiệp vụ có hàng đang hỏng, hàng bị khóa, hàng an toàn hoặc hàng chưa kiểm định, công thức cần mở rộng để phản ánh chính xác định nghĩa `available` của context. Không nên dùng một công thức giản lược nếu các loại tồn có ý nghĩa khác nhau.

### 6.2. Chọn ranh giới Aggregate

Một lựa chọn có thể là `StockItem` Aggregate cho một SKU tại một địa điểm. Root quản lý số lượng và các reservation đang hoạt động cần thiết để bảo vệ invariant. Khóa định danh Aggregate có thể là cặp `(SKU, LocationId)`.

Các thao tác như giữ hàng, giải phóng reservation và ghi nhận xuất kho đi qua root. Một đơn hàng chỉ giữ `ReservationId` hoặc tham chiếu phù hợp; nó không trực tiếp sửa lượng tồn.

Nếu số lượng reservation rất lớn, không nhất thiết phải tải toàn bộ lịch sử vào Aggregate. Có thể giữ tổng số đang hoạt động và thiết kế dữ liệu reservation riêng, nhưng mọi thao tác làm thay đổi tổng phải đi qua một cơ chế nhất quán có cùng quyền sở hữu và kiểm soát concurrency. Ranh giới logic phải được bảo vệ dù dữ liệu vật lý có thể được lưu ở nhiều bảng.

### 6.3. Hành vi domain

```java
public final class StockItem {
    private final Sku sku;
    private final LocationId locationId;
    private int onHand;
    private int reserved;

    public StockItem(Sku sku, LocationId locationId, int onHand, int reserved) {
        if (onHand < 0 || reserved < 0 || reserved > onHand) {
            throw new IllegalArgumentException("Invalid stock state");
        }
        this.sku = sku;
        this.locationId = locationId;
        this.onHand = onHand;
        this.reserved = reserved;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        int available = onHand - reserved;
        if (quantity > available) {
            throw new InsufficientStockException(sku, locationId);
        }
        reserved += quantity;
    }

    public void release(int quantity) {
        if (quantity <= 0 || quantity > reserved) {
            throw new IllegalArgumentException("Invalid release quantity");
        }
        reserved -= quantity;
    }

    public int available() {
        return onHand - reserved;
    }
}
```

Ví dụ rút gọn để minh họa hành vi và invariant. Trong hệ thống thực tế, cần thêm identity reservation, trạng thái, idempotency, ghi nhận xuất kho, điều chỉnh tồn và kiểm soát đồng thời. Nếu `release` cần xác định reservation cụ thể, nên nhận `ReservationId` và kiểm tra trạng thái của reservation thay vì chỉ giảm một con số tùy ý.

### 6.4. Thực hiện trong một giao dịch

Application service tải Aggregate, gọi hành vi và lưu thay đổi trong một transaction:

```java
@Transactional
public ReservationResult reserve(ReserveStockCommand command) {
    StockItem stock = stockRepository.getForUpdate(
            command.sku(), command.locationId());

    stock.reserve(command.quantity());

    Reservation reservation = Reservation.create(
            command.reservationId(),
            command.orderId(),
            command.quantity());

    reservationRepository.save(reservation);
    stockRepository.save(stock);

    return ReservationResult.accepted(reservation.id());
}
```

Đoạn code này chỉ đúng nếu `StockItem` và reservation được ghi trong cùng một ranh giới giao dịch có kiểm soát, hoặc có thiết kế khác bảo vệ tổng số lượng một cách nguyên tử. Nếu reservation nằm trong một kho dữ liệu độc lập và việc lưu hai nơi không thể atomic, cần điều chỉnh mô hình hoặc dùng cơ chế nhất quán phù hợp. Không nên cho rằng chỉ có annotation `@Transactional` là mọi resource đều được commit cùng nhau.

## 7. Bảo vệ invariant khi có nhiều yêu cầu đồng thời

Một Aggregate có method kiểm tra đúng vẫn có thể bị vi phạm nếu hai giao dịch cùng đọc một trạng thái cũ và cùng ghi kết quả mới.

Giả sử tồn khả dụng là 5:

1. Transaction A đọc `available = 5` và yêu cầu giữ 4.
2. Transaction B cũng đọc `available = 5` và yêu cầu giữ 4.
3. Cả hai đều vượt qua kiểm tra trong bộ nhớ.
4. Nếu cả hai cùng ghi mà không có concurrency control, tổng lượng giữ có thể thành 8.

Đây là race condition. Cần bảo vệ invariant ở thời điểm commit, không chỉ lúc chạy method.

### 7.1. Pessimistic locking

Pessimistic locking khóa bản ghi hoặc tài nguyên cần cập nhật để giao dịch khác phải chờ. Ví dụ `SELECT ... FOR UPDATE` có thể khóa hàng tồn kho tương ứng trong một transaction.

Phù hợp khi cạnh tranh cao và thời gian giữ khóa có thể kiểm soát. Cần chú ý deadlock, timeout, thứ tự lấy khóa và không giữ transaction quá lâu.

### 7.2. Optimistic locking

Optimistic locking dùng version hoặc cơ chế so sánh trạng thái khi ghi. Nếu một giao dịch khác đã cập nhật trước, lần ghi hiện tại thất bại và có thể được retry sau khi tải trạng thái mới.

Ví dụ với JPA:

```java
@Entity
public class StockItemRecord {
    @Id
    private String id;

    @Version
    private long version;

    private int onHand;
    private int reserved;
}
```

`@Version` giúp phát hiện một số xung đột cập nhật trên cùng bản ghi. Ứng dụng cần xử lý optimistic lock exception phù hợp: tải lại, đánh giá lại điều kiện và thử lại có giới hạn hoặc trả kết quả xung đột. Không được lặp lại mù quáng một command có tác động bên ngoài.

### 7.3. Constraint ở database

Database constraint như `CHECK (reserved >= 0 AND reserved <= on_hand)` có thể là lớp bảo vệ bổ sung. Nó hữu ích để ngăn dữ liệu sai ngay cả khi có đường ghi ngoài ứng dụng. Tuy nhiên, constraint không thay thế hành vi domain vì nó không diễn đạt đầy đủ ý nghĩa, thông báo lỗi và quy trình xử lý nghiệp vụ.

Với một quy tắc cần kiểm tra nhiều bản ghi, cần thiết kế transaction isolation, khóa hoặc mô hình dữ liệu phù hợp. Một `CHECK` trên từng dòng không tự bảo vệ tổng hợp qua nhiều dòng nếu database không hỗ trợ điều kiện đó theo cách cần thiết.

## 8. Phân biệt invariant nội bộ với quy tắc xuyên Aggregate

Một số quy tắc liên quan nhiều Aggregate nhưng không nhất thiết phải được bảo vệ bằng một transaction duy nhất.

Ví dụ:

- Một khách hàng không được có tổng dư nợ vượt hạn mức tín dụng.
- Một đơn hàng chỉ được giao sau khi thanh toán được ghi nhận và hàng đã sẵn sàng.
- Một chương trình khuyến mãi có ngân sách tổng cho nhiều đơn hàng.
- Một khách hàng chỉ được có một yêu cầu đang hoạt động cho một loại dịch vụ.

Trước tiên hãy xác định quy tắc cần **nhất quán ngay lập tức** hay có thể **nhất quán cuối cùng** sau một quy trình phối hợp.

### 8.1. Khi quy tắc phải được bảo vệ ngay lập tức

Nếu hai thao tác đồng thời có thể làm vượt hạn mức hoặc gây thiệt hại không thể chấp nhận, cần có một điểm quyết định nguyên tử. Có thể:

- Đặt một Aggregate sở hữu hạn mức và số tiền đã cam kết.
- Tạo cơ chế reservation/authorization để giữ trước một phần hạn mức.
- Dùng transaction hoặc locking trên tài nguyên có thẩm quyền.
- Thiết kế lại mô hình để quy tắc cần nhất quán nằm trong một ranh giới rõ.

Ví dụ, thay vì mỗi Order tự đọc hạn mức Customer rồi tự cộng khoản mới, Credit Account Aggregate có thể thực hiện `reserveCredit(amount)` và bảo vệ tổng đã cam kết. Mỗi đơn giữ một `CreditReservationId`; khi đơn bị hủy, reservation được giải phóng qua một hành vi riêng.

### 8.2. Khi có thể chấp nhận nhất quán cuối cùng

Nếu quy trình cho phép một khoảng thời gian chờ và có cách xử lý khi bước sau thất bại, có thể dùng event và process manager/saga để phối hợp. Ví dụ, sau khi đơn được xác nhận, hệ thống gửi yêu cầu tạo shipment; khi shipment được tạo, một event thông báo lại Sales. Trong thời gian chờ, đơn có thể ở trạng thái `AwaitingFulfillment`.

Không nên giả định event tự động bảo đảm invariant xuyên Aggregate. Event có thể trễ, trùng hoặc thất bại khi tiêu thụ. Quy trình cần idempotency, retry, theo dõi trạng thái, timeout và hành động bù trừ.

### 8.3. Không dùng một Aggregate khổng lồ để né phối hợp

Đưa Customer, Order, Payment, Inventory và Shipment vào cùng một Aggregate có thể làm giao dịch lớn, khóa rộng và quyền sở hữu mơ hồ. Nó cũng khiến các phần có nhịp thay đổi khác nhau bị buộc phải thay đổi cùng nhau.

Nếu nghiệp vụ thực sự yêu cầu một invariant xuyên nhiều dữ liệu phải được bảo vệ tức thời, hãy xem xét lại mô hình và cơ chế lưu trữ một cách có chủ đích. Nhưng đừng mở rộng Aggregate chỉ để tránh phải thiết kế quy trình phối hợp.

## 9. Phân loại quy tắc trước khi quyết định ranh giới

Một bảng phân loại giúp nhóm tránh gom mọi business rule vào Aggregate:

| Loại quy tắc | Phạm vi thường phù hợp | Cách bảo vệ gợi ý |
|---|---|---|
| Giá trị đơn lẻ hợp lệ | Value Object | Constructor/factory và phép toán bất biến |
| Quan hệ giữa các thuộc tính của một entity | Entity hoặc Aggregate | Hành vi và invariant trong mô hình |
| Nhiều entity cần thay đổi nguyên tử | Một Aggregate | Aggregate Root và transaction |
| Quy tắc liên quan nhiều Aggregate có reservation | Aggregate sở hữu tài nguyên được đặt chỗ | Reservation/authorization và quy trình phối hợp |
| Quy trình nhiều bước qua context | Application/process manager/saga | Event, command, retry và compensation |
| Quyền truy cập | Security/application boundary | Authorization policy và kiểm tra quyền |
| Giới hạn dữ liệu cuối cùng | Database | Constraint, unique index và transaction isolation |

Đây là hướng dẫn lựa chọn, không phải luật cứng. Cần xét ý nghĩa nghiệp vụ, tần suất thay đổi, yêu cầu đồng bộ và khả năng phục hồi của từng trường hợp.

## 10. Cách viết hành vi để invariant luôn được bảo vệ

Aggregate Root nên cung cấp các hành vi diễn đạt ngôn ngữ nghiệp vụ. Thay vì công khai setter cho mọi field, hãy cung cấp command method với điều kiện và kết quả rõ ràng.

Ví dụ:

```java
order.addLine(productId, quantity, unitPrice);
order.confirm(paymentReference);
order.cancel(cancellationReason);
```

Các method này có thể kiểm tra:

- Trạng thái hiện tại có cho phép hành động không?
- Giá trị mới có hợp lệ không?
- Các đối tượng liên quan có thỏa invariant không?
- Có cần cập nhật nhiều thành phần bên trong Aggregate không?
- Có cần ghi nhận domain event sau khi thay đổi thành công không?

Không nên viết API kiểu `setStatus("CONFIRMED")` nếu việc xác nhận đòi hỏi nhiều điều kiện nghiệp vụ. Một method `confirm()` diễn đạt ý nghĩa và giữ quy tắc ở đúng nơi.

### 10.1. Bất biến phải được bảo vệ ở mọi đường vào

Một Aggregate có thể được tạo từ command, import dữ liệu, job nền, consumer event hoặc phục hồi từ database. Không được chỉ kiểm tra invariant ở REST controller. Các đường vào khác có thể bỏ qua controller.

Hãy đặt quy tắc trong mô hình miền và bảo đảm dữ liệu được khôi phục cũng hợp lệ. Nếu cần xử lý dữ liệu legacy không hợp lệ, nên có quy trình migration/repair riêng thay vì âm thầm bỏ qua invariant trong mọi lần load.

## 11. Giao dịch và ranh giới Aggregate

Một transaction database thường là cơ chế kỹ thuật để lưu thay đổi của Aggregate Root và các đối tượng bên trong một cách nguyên tử. Nhưng ranh giới Aggregate là quyết định mô hình miền; transaction là cách hiện thực một phần quyết định đó.

### 11.1. Một command, một Aggregate chính

Một quy tắc thực hành phổ biến là mỗi command thay đổi một Aggregate chính. Application service tải root, gọi hành vi và lưu nó. Các Aggregate khác được tham chiếu bằng ID hoặc được phối hợp qua quy trình.

Điều này không có nghĩa một transaction không bao giờ được cập nhật nhiều Aggregate. Một số hệ thống có thể cần điều đó, nhưng nếu thường xuyên phải làm vậy, cần kiểm tra xem ranh giới Aggregate có phản ánh đúng invariant hay không.

### 11.2. Domain Event và transactional outbox

Khi Aggregate thay đổi, nó có thể ghi nhận domain event. Để công bố sự kiện ra broker mà không mất sự nhất quán giữa database và message broker, có thể dùng transactional outbox: lưu thay đổi Aggregate và bản ghi outbox trong cùng transaction; một tiến trình khác gửi message và đánh dấu đã xử lý.

Outbox giúp tránh trường hợp database commit thành công nhưng gửi event thất bại, hoặc gửi event rồi database rollback. Consumer vẫn cần idempotency vì message có thể được gửi lại.

### 11.3. Không giữ transaction quá lâu

Không nên mở transaction database rồi gọi một dịch vụ mạng chậm trong khi vẫn giữ khóa. Hãy cân nhắc tách bước: ghi nhận ý định hoặc reservation, commit, gọi hệ thống ngoài và xử lý kết quả bằng một bước tiếp theo. Quy trình cụ thể phụ thuộc vào invariant và mức độ nhất quán nghiệp vụ yêu cầu.

## 12. Ví dụ: Aggregate Order bảo vệ invariant của đơn hàng

Giả sử Order Aggregate có các quy tắc:

- Đơn ở trạng thái Draft mới được thêm hoặc xóa dòng hàng.
- Đơn muốn xác nhận phải có ít nhất một dòng hàng.
- Số lượng mỗi dòng phải lớn hơn 0.
- Tổng tiền được tính từ các dòng hàng theo chính sách giá đã áp dụng.
- Đơn đã giao không thể bị hủy như một đơn chưa xử lý.

Một cách tổ chức có thể là:

```text
Order (Aggregate Root)
├── OrderId
├── OrderStatus
├── OrderLine (child entity)
│   ├── ProductReference (Value Object)
│   ├── Quantity (Value Object)
│   └── UnitPrice (Money Value Object)
├── ShippingAddress (Value Object)
└── Total (Money Value Object)
```

Ví dụ hành vi:

```java
public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    public void addLine(OrderLine line) {
        ensureDraft();
        Objects.requireNonNull(line, "line");
        lines.add(line);
    }

    public void confirm() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("An order needs at least one line");
        }
        status = OrderStatus.CONFIRMED;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is not editable");
        }
    }
}
```

Ví dụ rút gọn, bỏ qua constructor, total calculation, event collection và persistence. Trong hệ thống thật, `OrderLine` nên tự bảo vệ các quy tắc thuộc nó; Order Root bảo vệ các quy tắc liên quan toàn đơn. Nếu tổng tiền cần snapshot giá, cần lưu rõ giá áp dụng tại thời điểm đặt hàng thay vì đọc giá hiện tại từ Product Context mỗi lần tính lại.

## 13. Xử lý lỗi và kết quả không xác định

Khi một command bị từ chối vì invariant, hệ thống cần trả một kết quả đủ rõ để caller biết điều gì có thể làm tiếp. Ví dụ, `InsufficientStock` có thể dẫn đến đề xuất giảm số lượng hoặc chọn địa điểm khác.

Phân biệt:

- **Business rejection:** yêu cầu không thỏa quy tắc; không nên retry vô hạn.
- **Concurrency conflict:** trạng thái đã thay đổi bởi giao dịch khác; có thể tải lại và đánh giá lại.
- **Transient infrastructure failure:** timeout hoặc lỗi kết nối; retry theo chính sách phù hợp.
- **Unknown outcome:** caller không biết hành động đã commit hay chưa; cần truy vấn theo request ID hoặc đối soát.

Không nên biến mọi lỗi thành một exception chung rồi retry. Một yêu cầu giữ hàng bị từ chối vì hết tồn không thể được giải quyết bằng retry liên tục nếu không có thay đổi về tồn kho.

## 14. Các sai lầm thường gặp khi xác định invariant

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Xem mọi business rule là invariant của một Aggregate | Aggregate phình to và giao dịch xuyên miền | Phân biệt invariant nội bộ với policy/quy trình xuyên Aggregate |
| Nhóm đối tượng theo quan hệ dữ liệu | Ranh giới không phản ánh yêu cầu nhất quán | Bắt đầu từ quy tắc phải được bảo vệ cùng nhau |
| Đặt mọi entity liên quan vào một Aggregate | Object graph lớn, khóa rộng và cạnh tranh cao | Tham chiếu Aggregate khác bằng ID |
| Chỉ kiểm tra trong controller | Job hoặc consumer có thể bỏ qua quy tắc | Bảo vệ invariant trong mô hình miền và cơ chế lưu trữ |
| Nghĩ method check là đủ | Race condition vẫn có thể làm sai khi commit | Dùng locking, versioning hoặc transaction isolation phù hợp |
| Cho phép setter công khai | Trạng thái có thể thay đổi ngoài hành vi nghiệp vụ | Cung cấp command method trên Aggregate Root |
| Dùng event để giả định giao dịch nguyên tử xuyên context | Có khoảng thời gian không nhất quán và có thể thất bại | Thiết kế state machine, retry, idempotency và compensation |
| Dựa hoàn toàn vào database constraint | Mất ngữ nghĩa và thông báo nghiệp vụ | Kết hợp domain model với constraint làm lớp bảo vệ bổ sung |
| Retry mọi lỗi | Lặp hành động hoặc gây tải không cần thiết | Phân loại business rejection, conflict và lỗi hạ tầng |
| Không kiểm tra dữ liệu khi load | Aggregate cũ có thể vi phạm invariant | Xác minh dữ liệu và có quy trình migration/repair |

## 15. Checklist xác định invariant và ranh giới giao dịch

Trước khi hoàn tất thiết kế Aggregate, hãy kiểm tra:

- [ ] Invariant được viết thành điều kiện cụ thể và có thể kiểm tra.
- [ ] Có ví dụ hợp lệ, không hợp lệ và giá trị biên.
- [ ] Đã xác định hành động nào có thể làm thay đổi invariant.
- [ ] Đã xác định Aggregate Root chịu trách nhiệm bảo vệ quy tắc.
- [ ] Các đối tượng cần thay đổi nguyên tử nằm trong cùng ranh giới hợp lý.
- [ ] Aggregate khác được tham chiếu bằng ID hoặc hợp đồng rõ ràng.
- [ ] Đã phân biệt invariant với validation, authorization và process policy.
- [ ] Đã xác định quy tắc cần nhất quán ngay và quy tắc có thể nhất quán cuối cùng.
- [ ] Có cơ chế transaction và concurrency control phù hợp.
- [ ] Có xử lý idempotency, retry, timeout và kết quả chưa xác định khi cần.
- [ ] Domain event được ghi nhận sau khi hành động nghiệp vụ thành công.
- [ ] Có kiểm thử domain, persistence và tình huống cập nhật đồng thời.
- [ ] Có cách xử lý dữ liệu legacy không thỏa invariant.

## 16. Kết nối với các khái niệm DDD khác

Invariant là đầu mối quan trọng để xác định Aggregate và Aggregate Root. Entity cung cấp identity và vòng đời; Value Object biểu diễn giá trị bất biến; Aggregate Root bảo vệ các quy tắc cần duy trì trong cùng ranh giới nhất quán. Repository nạp và lưu Aggregate như một đơn vị, còn Domain Event thông báo các thay đổi nghiệp vụ có ý nghĩa sau khi chúng được ghi nhận.

Ở mức ứng dụng, Application Service điều phối command, transaction và repository. Khi quy tắc vượt qua nhiều Aggregate hoặc bounded context, Context Map và các mẫu tích hợp giúp xác định quan hệ, quyền sở hữu và cách phối hợp. Có thể dùng process manager hoặc saga để quản lý quy trình nhiều bước, nhưng phải thiết kế trạng thái, retry và hành động bù trừ rõ ràng.

Một Aggregate tốt không phải Aggregate chứa nhiều dữ liệu nhất. Nó là ranh giới nhỏ và rõ, đủ để bảo vệ những invariant cần được duy trì nhất quán khi một hành động nghiệp vụ hoàn tất. Xác định đúng invariant trước khi chọn cấu trúc đối tượng giúp mô hình vừa bảo vệ được nghiệp vụ, vừa tránh giao dịch lớn và phụ thuộc không cần thiết.
