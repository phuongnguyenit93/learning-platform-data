# Bất biến nghiệp vụ trong từng đối tượng và trong một aggregate

Trong Domain-Driven Design (DDD), mô hình miền phải bảo đảm các quy tắc nghiệp vụ luôn đúng tại những ranh giới mà doanh nghiệp cam kết tính nhất quán. Những điều kiện đó được gọi là **invariant (bất biến)**. Một bất biến có thể thuộc về một Value Object, một Entity hoặc toàn bộ Aggregate. Xác định đúng phạm vi của nó giúp đặt quy tắc đúng chỗ và tránh để nhiều thành phần cùng sửa dữ liệu theo những cách không nhất quán.

Bất biến trở nên đặc biệt quan trọng khi nhiều yêu cầu được xử lý đồng thời. Hai khách hàng có thể cùng đặt đơn vị hàng cuối cùng; hai nhân viên có thể cùng duyệt một hồ sơ; hai giao dịch có thể cùng sử dụng một hạn mức. Nếu mô hình chỉ kiểm tra dữ liệu khi đọc mà không kiểm soát cập nhật đồng thời, mỗi yêu cầu riêng lẻ có thể hợp lệ nhưng kết quả kết hợp lại vi phạm quy tắc nghiệp vụ.

Bài học này trình bày cách nhận diện invariant trong từng đối tượng và trong một Aggregate, cách Aggregate Root bảo vệ ranh giới nhất quán, và cách xử lý cạnh tranh cập nhật bằng transaction, optimistic locking, pessimistic locking và các biện pháp bảo vệ ở cơ sở dữ liệu. Ví dụ xuyên suốt sử dụng nghiệp vụ giữ hàng trong kho để minh họa điều kiện không được cam kết vượt quá số lượng thực có.

## 1. Invariant là gì?

### 1.1. Bất biến là điều kiện phải luôn đúng

Invariant là một điều kiện mà mô hình miền phải bảo đảm trong suốt vòng đời của đối tượng hoặc tại ranh giới nhất quán mà Aggregate chịu trách nhiệm.

Ví dụ:

- Số lượng trong một dòng đơn hàng phải lớn hơn 0.
- Số tiền của một khoản thanh toán không được âm.
- Ngày kết thúc của một khoảng thời gian phải sau ngày bắt đầu.
- Một tài khoản không được chi tiêu vượt quá hạn mức khả dụng.
- Tổng số lượng hàng đã giữ không được vượt quá số lượng hàng hiện có.
- Một đơn hàng đã giao không thể quay lại trạng thái Nháp.

Invariant không chỉ là điều kiện kiểm tra ở giao diện. Nó phải được bảo vệ dù hành động đến từ REST API, batch job, message consumer, tác vụ quản trị hay một luồng xử lý khác.

### 1.2. Phân biệt invariant với validation và business rule

Các khái niệm có liên hệ nhưng không hoàn toàn giống nhau:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Input validation | Kiểm tra dữ liệu đầu vào có đúng định dạng và cấu trúc | Mã đơn không được để trống |
| Business rule | Quy tắc quyết định một hành động hoặc kết quả nghiệp vụ | Chỉ khách hàng đủ điều kiện mới được mua trả góp |
| Invariant | Điều kiện phải luôn được duy trì trong phạm vi mô hình | Tổng số lượng giữ không vượt quá tồn kho |
| Authorization | Kiểm tra người thực hiện có quyền làm hành động hay không | Chỉ quản lý được duyệt yêu cầu hoàn tiền |
| Process rule | Quy tắc điều phối nhiều bước hoặc nhiều bên tham gia | Chỉ khởi tạo giao hàng sau khi đơn được xác nhận |

Một business rule có thể được thực hiện như invariant nếu nó phải luôn đúng trong phạm vi một đối tượng hoặc Aggregate. Một số quy tắc khác chỉ áp dụng khi một hành động cụ thể xảy ra, hoặc cần phối hợp nhiều Aggregate, nên không thể đặt tất cả vào cùng một Entity.

### 1.3. Bất biến được đánh giá tại ranh giới nào?

Trong một phương thức, mô hình có thể thực hiện nhiều bước cập nhật nội bộ. Có thể xuất hiện trạng thái trung gian trong lúc xử lý, miễn là trạng thái đó không bị quan sát từ bên ngoài và hành động kết thúc thành công với invariant được bảo đảm. Nếu có lỗi, thay đổi phải được hủy hoặc không được lưu.

Với Aggregate, điều quan trọng là invariant phải đúng khi một thao tác nghiệp vụ hoàn tất và Aggregate được lưu. Các đối tượng bên ngoài không được nhìn thấy một Aggregate đang ở trạng thái nửa chừng.

Ví dụ, khi xác nhận giữ hàng, hệ thống có thể tạo một Reservation và cập nhật số lượng đã giữ. Hai thay đổi này phải được xem như một thao tác nhất quán. Nếu chỉ tạo Reservation mà không cập nhật số lượng, hoặc ngược lại, mô hình có thể ghi nhận một cam kết sai.

## 2. Bất biến trong từng đối tượng

Một đối tượng cần tự bảo vệ những điều kiện thuộc về ý nghĩa và trạng thái của chính nó. DDD thường sử dụng Value Object và Entity để thể hiện những trách nhiệm này.

### 2.1. Value Object bảo vệ tính hợp lệ của giá trị

Value Object được xác định bằng các thuộc tính cấu thành giá trị và thường bất biến. Điều kiện hợp lệ nên được kiểm tra khi tạo đối tượng.

Ví dụ, Quantity biểu diễn một số lượng không âm:

~~~java
public record Quantity(int value) {

    public Quantity {
        if (value < 0) {
            throw new IllegalArgumentException(
                "Quantity cannot be negative"
            );
        }
    }

    public Quantity add(Quantity other) {
        return new Quantity(
            Math.addExact(value, other.value)
        );
    }

    public Quantity subtract(Quantity other) {
        if (other.value > value) {
            throw new IllegalArgumentException(
                "Quantity cannot become negative"
            );
        }

        return new Quantity(value - other.value);
    }
}
~~~

Quantity tự bảo vệ invariant value không âm. Bên gọi không cần nhớ kiểm tra số âm ở mọi nơi.

Tuy nhiên, số lượng yêu cầu giữ hàng thường phải lớn hơn 0. Đây là một khái niệm chặt hơn Quantity không âm. Có thể dùng một Value Object riêng như PositiveQuantity, hoặc kiểm tra điều kiện lớn hơn 0 tại hành vi nghiệp vụ nhận yêu cầu. Chọn cách nào tùy vào việc điều kiện đó có ý nghĩa độc lập và được tái sử dụng trong miền hay không.

### 2.2. Entity bảo vệ trạng thái và chuyển đổi hợp lệ

Entity có danh tính và vòng đời. Nó thường bảo vệ các chuyển đổi trạng thái thuộc trách nhiệm của mình.

Ví dụ, một Reservation có thể có ba trạng thái:

- ACTIVE: đang giữ hàng.
- RELEASED: đã giải phóng hàng.
- FULFILLED: hàng đã được xuất theo giữ chỗ.

Một Reservation đã giải phóng không thể được giải phóng lần nữa như thể nó vẫn còn hoạt động. Một Reservation đã hoàn tất không thể quay lại trạng thái đang giữ.

~~~java
public enum ReservationStatus {
    ACTIVE,
    RELEASED,
    FULFILLED
}
~~~

~~~java
public final class Reservation {

    private final String id;
    private final int quantity;
    private ReservationStatus status;

    public Reservation(String id, int quantity) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                "Reservation id is required"
            );
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Reservation quantity must be positive"
            );
        }

        this.id = id;
        this.quantity = quantity;
        this.status = ReservationStatus.ACTIVE;
    }

    public void release() {
        ensureActive();
        status = ReservationStatus.RELEASED;
    }

    public void fulfill() {
        ensureActive();
        status = ReservationStatus.FULFILLED;
    }

    public boolean isActive() {
        return status == ReservationStatus.ACTIVE;
    }

    public int quantity() {
        return quantity;
    }

    private void ensureActive() {
        if (!isActive()) {
            throw new IllegalStateException(
                "Only an active reservation can change"
            );
        }
    }
}
~~~

Reservation tự bảo vệ quy tắc chuyển trạng thái của nó. Nhưng nó không thể tự bảo đảm tổng số lượng giữ trong kho không vượt quá tồn kho, vì điều kiện đó phụ thuộc vào nhiều Reservation và số lượng hàng của kho. Quy tắc tổng thể cần được bảo vệ ở phạm vi rộng hơn.

### 2.3. Constructor và factory là điểm khởi đầu, không phải toàn bộ giải pháp

Constructor hoặc factory nên tạo đối tượng ở trạng thái hợp lệ. Sau khi tạo, mọi hành vi công khai vẫn phải giữ invariant.

Nếu một Entity có setter công khai cho trạng thái, bên ngoài có thể bỏ qua các bước chuyển đổi hợp lệ. Nếu một Value Object chứa collection mutable và trả collection đó ra ngoài, bên gọi có thể thay đổi giá trị sau khi constructor đã kiểm tra.

Cần chú ý cả quá trình tải dữ liệu từ cơ sở dữ liệu. ORM có thể sử dụng constructor, reflection hoặc cơ chế mapping riêng. Dù cách tải khác nhau, mô hình vẫn cần phát hiện dữ liệu cũ không hợp lệ và không cho phép những hành vi tiếp theo làm sai lệch thêm trạng thái.

## 3. Bất biến ở cấp độ Aggregate

### 3.1. Aggregate là ranh giới nhất quán

Aggregate là một cụm đối tượng miền được xem như một đơn vị nhất quán. Aggregate Root là đối tượng gốc mà mã bên ngoài sử dụng để yêu cầu thay đổi cụm.

Aggregate Root có trách nhiệm bảo vệ invariant liên quan đến các thành phần bên trong. Những đối tượng con không nên được sửa trực tiếp từ bên ngoài để tránh bỏ qua quy tắc của toàn cụm.

Ví dụ một Order Aggregate có thể gồm:

- Order là Aggregate Root.
- OrderLine là các thành phần bên trong.
- Order kiểm tra đơn có dòng hàng hay không trước khi xác nhận.
- Order kiểm soát việc thêm, sửa và xóa dòng hàng.
- Các OrderLine không được thay đổi độc lập làm tổng tiền hoặc trạng thái đơn mất nhất quán.

### 3.2. Aggregate Root là cổng vào của thay đổi

Bên ngoài nên gọi hành vi trên Aggregate Root:

~~~java
order.changeQuantity(productId, 3);
order.confirm();
~~~

Thay vì lấy một dòng hàng rồi sửa trực tiếp:

~~~java
orderLine.setQuantity(3);
~~~

Cách thứ hai có thể bỏ qua điều kiện như chỉ đơn Nháp mới được sửa, số lượng phải dương hoặc giá trị tổng đơn phải được tính lại.

Aggregate Root cần kiểm soát các tham chiếu đến đối tượng con. Không trả về collection mutable hoặc cho phép đối tượng bên ngoài giữ một tham chiếu có thể sửa đến trạng thái nội bộ.

### 3.3. Chỉ đưa vào Aggregate những gì cần nhất quán cùng nhau

Không nên gom mọi đối tượng liên quan đến một quy trình vào một Aggregate lớn. Hãy hỏi:

- Những dữ liệu nào phải thay đổi cùng nhau?
- Bất biến nào cần được bảo đảm trong một thao tác?
- Nếu một phần thay đổi mà phần khác chưa cập nhật, nghiệp vụ có chấp nhận được không?
- Ai là người sở hữu quyết định?
- Mức độ tranh chấp cập nhật có cao không?

Aggregate càng lớn, mỗi thao tác càng phải tải và có thể khóa nhiều dữ liệu. Nó cũng làm tăng khả năng nhiều người dùng cùng cập nhật một Root. Aggregate quá nhỏ lại có thể khiến invariant bị phân tán và phải điều phối phức tạp.

Ranh giới tốt là ranh giới bảo vệ được các bất biến cần thiết với chi phí phối hợp hợp lý.

## 4. Ví dụ: giữ hàng trong kho không được vượt tồn kho

Giả sử một kho có 10 đơn vị hàng. Một số đơn vị có thể đã được giữ cho khách, phần còn lại là khả dụng để nhận yêu cầu mới.

Định nghĩa:

- onHand: số lượng hàng thực tế đang được ghi nhận trong kho.
- reserved: tổng số lượng đang được giữ bởi các Reservation còn hoạt động.
- available: số lượng có thể giữ thêm.

Ta có:

\[
available = onHand - reserved
\]

Bất biến chính:

\[
0 \le reserved \le onHand
\]

Và mọi yêu cầu giữ hàng mới phải thỏa mãn:

\[
requestedQuantity > 0
\]

\[
requestedQuantity \le available
\]

Nếu hai khách hàng cùng yêu cầu số hàng cuối cùng, việc kiểm tra đơn thuần trên dữ liệu đã đọc có thể khiến cả hai cùng được chấp nhận. Phần concurrency sẽ được phân tích ở các phần sau.

### 4.1. Chọn Aggregate theo đơn vị tồn kho

Giả sử doanh nghiệp quản lý tồn kho theo SKU và kho vật lý. Có thể xác định một Stock Aggregate cho mỗi cặp SKU và Warehouse.

Ví dụ:

- Stock(SKU-01, HCM-WH): tồn kho của sản phẩm SKU-01 tại kho HCM.
- Stock(SKU-01, DN-WH): tồn kho cùng sản phẩm tại kho Đà Nẵng.

Cách phân chia này giúp mỗi Aggregate sở hữu quy tắc giữ hàng trong phạm vi một loại hàng tại một kho. Nếu một đơn đặt nhiều SKU, việc giữ hàng có thể liên quan nhiều Aggregate; khi đó cần một quy trình điều phối phù hợp nếu nghiệp vụ yêu cầu kết quả tổng thể.

### 4.2. Mô hình Stock Aggregate

~~~java
public final class Stock {

    private final String sku;
    private final String warehouseId;
    private int onHand;

    private final Map<String, Reservation> reservations =
        new HashMap<>();

    public Stock(
        String sku,
        String warehouseId,
        int initialOnHand
    ) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }

        if (warehouseId == null || warehouseId.isBlank()) {
            throw new IllegalArgumentException(
                "Warehouse is required"
            );
        }

        if (initialOnHand < 0) {
            throw new IllegalArgumentException(
                "Initial stock cannot be negative"
            );
        }

        this.sku = sku;
        this.warehouseId = warehouseId;
        this.onHand = initialOnHand;
    }

    public void reserve(String reservationId, int quantity) {
        requirePositive(quantity);

        if (reservationId == null || reservationId.isBlank()) {
            throw new IllegalArgumentException(
                "Reservation id is required"
            );
        }

        if (reservations.containsKey(reservationId)) {
            throw new IllegalArgumentException(
                "Reservation already exists"
            );
        }

        if (availableQuantity() < quantity) {
            throw new InsufficientStockException();
        }

        reservations.put(
            reservationId,
            new Reservation(reservationId, quantity)
        );

        ensureInvariant();
    }

    public void release(String reservationId) {
        Reservation reservation =
            requireReservation(reservationId);

        reservation.release();
        ensureInvariant();
    }

    public void fulfill(String reservationId) {
        Reservation reservation =
            requireReservation(reservationId);

        int quantity = reservation.quantity();

        reservation.fulfill();
        onHand -= quantity;

        ensureInvariant();
    }

    public void receive(int quantity) {
        requirePositive(quantity);
        onHand = Math.addExact(onHand, quantity);
        ensureInvariant();
    }

    public int onHand() {
        return onHand;
    }

    public int reservedQuantity() {
        long total = reservations.values().stream()
            .filter(Reservation::isActive)
            .mapToLong(Reservation::quantity)
            .sum();

        return Math.toIntExact(total);
    }

    public int availableQuantity() {
        return onHand - reservedQuantity();
    }

    private Reservation requireReservation(String id) {
        Reservation reservation = reservations.get(id);

        if (reservation == null) {
            throw new IllegalArgumentException(
                "Reservation does not exist"
            );
        }

        return reservation;
    }

    private void ensureInvariant() {
        int reserved = reservedQuantity();

        if (onHand < 0 || reserved < 0 || reserved > onHand) {
            throw new IllegalStateException(
                "Stock invariant was violated"
            );
        }
    }

    private static void requirePositive(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
    }
}
~~~

Trong mã triển khai, đặt Reservation thành lớp lồng riêng tư bên trong Stock để mã bên ngoài không thể sửa trạng thái của nó trực tiếp:

~~~java
private static final class Reservation {

    private final String id;
    private final int quantity;
    private ReservationStatus status =
        ReservationStatus.ACTIVE;

    public Reservation(String id, int quantity) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                "Reservation id is required"
            );
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        this.id = id;
        this.quantity = quantity;
    }

    public void release() {
        ensureActive();
        status = ReservationStatus.RELEASED;
    }

    public void fulfill() {
        ensureActive();
        status = ReservationStatus.FULFILLED;
    }

    public boolean isActive() {
        return status == ReservationStatus.ACTIVE;
    }

    public int quantity() {
        return quantity;
    }

    private void ensureActive() {
        if (!isActive()) {
            throw new IllegalStateException(
                "Reservation is no longer active"
            );
        }
    }
}
~~~

Enum trạng thái:

~~~java
public enum ReservationStatus {
    ACTIVE,
    RELEASED,
    FULFILLED
}
~~~

Ví dụ lược bỏ import và constructor của InsufficientStockException. Trong triển khai thật, Reservation nên được lồng hoặc giới hạn truy cập để mã bên ngoài không thể sửa nó ngoài Aggregate Root. Các collection nội bộ cũng không được trả ra dưới dạng có thể thay đổi.

### 4.3. Những invariant được Stock bảo vệ

| Invariant | Phạm vi | Cách bảo vệ |
|---|---|---|
| Tồn kho thực tế không âm | Stock | Constructor và receive/fulfill |
| Số lượng Reservation phải dương | Reservation | Constructor |
| Reservation chỉ được chuyển từ ACTIVE | Reservation | release/fulfill kiểm tra trạng thái |
| Mỗi Reservation ID chỉ xuất hiện một lần trong Stock | Stock | reserve kiểm tra trùng ID |
| Tổng số lượng giữ không vượt tồn kho | Stock Aggregate | reserve và ensureInvariant |
| Số lượng khả dụng không âm | Stock Aggregate | Tính từ onHand trừ reserved |

Điều kiện tổng số lượng giữ không vượt tồn kho là invariant cấp Aggregate vì nó phụ thuộc vào nhiều Reservation và số lượng của Stock. Một Reservation riêng lẻ không đủ thông tin để tự bảo đảm điều kiện đó.

### 4.4. Một thao tác phải cập nhật nhất quán

Khi fulfill một Reservation, hai thay đổi cần đi cùng nhau:

1. Reservation chuyển từ ACTIVE sang FULFILLED.
2. onHand giảm theo số lượng đã xuất.

Sau khi thao tác hoàn tất, số lượng đã giữ giảm tương ứng và tồn kho thực tế cũng giảm. Số lượng khả dụng được tính lại theo dữ liệu mới.

Trong hệ thống lưu trữ, thay đổi trạng thái Reservation và số lượng onHand cần được commit trong cùng transaction của Stock Aggregate. Nếu một phần ghi thành công còn phần khác thất bại, dữ liệu có thể vi phạm invariant.

## 5. Phân biệt invariant của đối tượng và invariant của Aggregate

| Cấp độ | Điều kiện được bảo vệ | Ví dụ | Chủ thể bảo vệ |
|---|---|---|---|
| Value Object | Giá trị riêng lẻ hợp lệ | Quantity không âm, Money có currency | Constructor và hành vi của Value Object |
| Entity | Trạng thái và vòng đời hợp lệ | Reservation chỉ được giải phóng khi ACTIVE | Entity |
| Aggregate | Quan hệ giữa nhiều thành phần luôn hợp lệ | Tổng Reservation ACTIVE không vượt onHand | Aggregate Root |
| Nhiều Aggregate | Quy tắc phối hợp giữa các đơn vị nhất quán độc lập | Một đơn chỉ được thực hiện khi tất cả mặt hàng đã được giữ | Application Service, Process Manager hoặc chính sách điều phối |

Không nên đưa một invariant nhiều Aggregate vào một Entity chỉ vì muốn có một nơi kiểm tra. Cần xác định ai sở hữu từng quyết định và mức nhất quán nào thực sự cần thiết.

## 6. Vì sao kiểm tra trước khi ghi chưa đủ khi có đồng thời?

### 6.1. Race condition là gì?

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các thao tác đồng thời diễn ra.

Giả sử kho còn 3 đơn vị khả dụng. Hai yêu cầu A và B cùng muốn giữ 2 đơn vị.

~~~text
Thời điểm     Yêu cầu A                 Yêu cầu B
---------------------------------------------------------
T1            Đọc available = 3
T2                                     Đọc available = 3
T3            Kiểm tra 2 <= 3
T4                                     Kiểm tra 2 <= 3
T5            Ghi reserved = 2
T6                                     Ghi reserved = 2
---------------------------------------------------------
Kết quả mong đợi: chỉ một yêu cầu giữ được 2 đơn vị.
Nếu ghi đè hoặc cộng sai: hệ thống có thể cam kết vượt tồn kho.
~~~

Cả A và B đều kiểm tra đúng trên dữ liệu mà chúng đọc được. Nhưng dữ liệu đó đã cũ khi thao tác còn lại commit. Kiểm tra trong code đơn lẻ không bảo vệ được invariant trước cập nhật đồng thời.

### 6.2. Lost update và overselling

Một lỗi có thể xảy ra khi cả hai transaction đọc cùng giá trị rồi ghi đè kết quả của nhau. Đây là lost update.

Một lỗi khác xảy ra khi hệ thống ghi nhận hai Reservation độc lập, mỗi Reservation đều hợp lệ theo snapshot riêng, nhưng tổng số lượng giữ vượt tồn kho. Đây là overselling.

Cần kiểm soát cạnh tranh tại nơi lưu trữ và tại ranh giới Aggregate, không chỉ ở giao diện hoặc application service.

### 6.3. Invariant phải được kiểm tra lại trên trạng thái mới nhất

Khi một thao tác phát hiện xung đột, không được tự động tiếp tục với kết quả đã tính trên dữ liệu cũ.

Cách xử lý đúng thường là:

1. Phát hiện transaction không còn cập nhật được phiên bản đã đọc.
2. Hủy transaction hiện tại.
3. Tải lại Aggregate mới nhất.
4. Thực hiện lại hành vi và kiểm tra invariant.
5. Nếu điều kiện không còn thỏa mãn, trả kết quả nghiệp vụ từ chối.

Việc retry cần giới hạn số lần và phân biệt lỗi cạnh tranh tạm thời với lỗi nghiệp vụ. Không lặp vô hạn khi kho thực sự không còn đủ hàng.

## 7. Optimistic Locking — khóa lạc quan

### 7.1. Ý tưởng

Optimistic locking giả định xung đột không xảy ra thường xuyên. Nhiều transaction có thể đọc cùng một Aggregate, nhưng khi ghi, hệ thống kiểm tra phiên bản dữ liệu có còn giống lúc đọc hay không.

Một Aggregate có thể có trường version:

~~~java
public class StockRecord {
    private long version;
    // Các thuộc tính tồn kho được lưu trữ
}
~~~

Với ORM như JPA, có thể dùng:

~~~java
@Version
private long version;
~~~

Khi lưu, ORM tạo thao tác cập nhật tương đương:

~~~sql
UPDATE stock
SET on_hand = ?, reserved = ?, version = version + 1
WHERE stock_id = ? AND version = ?;
~~~

Nếu một transaction đã cập nhật phiên bản trước, câu lệnh của transaction còn lại không cập nhật được dòng nào. ORM có thể phát sinh lỗi optimistic locking.

### 7.2. Diễn biến khi hai yêu cầu cùng giữ hàng

Giả sử cả A và B đọc Stock ở version 7:

- A giữ hàng và commit thành công, version tăng lên 8.
- B cố lưu với điều kiện version vẫn là 7.
- Không có dòng nào khớp version 7, nên B nhận xung đột.
- B rollback, tải lại Stock ở version 8.
- B thử giữ hàng lại; Aggregate kiểm tra số lượng khả dụng mới và có thể từ chối.

Optimistic locking bảo vệ việc cập nhật không ghi đè lên phiên bản mà transaction khác đã thay đổi. Hành vi miền sau khi tải lại mới là nơi quyết định yêu cầu còn hợp lệ hay không.

### 7.3. Khi nào phù hợp?

Optimistic locking thường phù hợp khi:

- Xung đột cập nhật không quá thường xuyên.
- Transaction ngắn.
- Có thể tải lại và thử lại thao tác.
- Người dùng không phải chờ khóa trong thời gian dài.
- Aggregate có thể được cập nhật theo phiên bản.

Nó không loại bỏ xung đột. Nó phát hiện xung đột và yêu cầu ứng dụng xử lý.

### 7.4. Không retry một cách mù quáng

Một lần giữ hàng bị xung đột không có nghĩa chỉ cần gửi lại câu lệnh SQL cũ. Khi tải lại Aggregate, số lượng khả dụng có thể đã thay đổi.

Retry phải gọi lại hành vi miền trên trạng thái mới nhất. Nếu điều kiện không còn đúng, kết quả cần là từ chối nghiệp vụ, không phải tiếp tục ghi.

## 8. Pessimistic Locking — khóa bi quan

### 8.1. Ý tưởng

Pessimistic locking khóa bản ghi hoặc tài nguyên trong khi transaction đang xử lý. Transaction khác muốn cập nhật cùng tài nguyên phải chờ hoặc nhận lỗi tùy cấu hình.

Trong cơ sở dữ liệu quan hệ, một truy vấn có thể sử dụng SELECT ... FOR UPDATE để khóa dòng:

~~~sql
SELECT stock_id, on_hand, reserved
FROM stock
WHERE stock_id = ?
FOR UPDATE;
~~~

Transaction tải dữ liệu và giữ khóa cho đến khi commit hoặc rollback. Những transaction khác cần khóa cùng dòng phải chờ.

### 8.2. Khi nào phù hợp?

Pessimistic locking có thể phù hợp khi:

- Xung đột xảy ra thường xuyên.
- Tài nguyên có mức cạnh tranh cao.
- Chi phí retry lớn.
- Cần tuần tự hóa thao tác trên một Aggregate.
- Transaction ngắn và có thể giữ khóa trong thời gian kiểm soát được.

Ví dụ, một kho có một mặt hàng rất khan hiếm và nhiều yêu cầu đồng thời có thể cần cơ chế khóa phù hợp để tránh retry liên tục.

### 8.3. Rủi ro của khóa bi quan

Khóa làm giảm khả năng xử lý song song. Nếu transaction giữ khóa quá lâu, các yêu cầu khác phải chờ, throughput giảm và có thể xảy ra deadlock.

Cần:

- Giữ transaction ngắn.
- Không gọi dịch vụ bên ngoài khi đang giữ khóa cơ sở dữ liệu nếu có thể tránh.
- Khóa các tài nguyên theo thứ tự nhất quán khi phải khóa nhiều dòng.
- Thiết lập timeout phù hợp.
- Theo dõi thời gian chờ và deadlock.
- Có chiến lược retry cho deadlock hoặc lỗi khóa tạm thời.

Không dùng khóa bi quan chỉ để che giấu một Aggregate được thiết kế quá rộng.

## 9. So sánh Optimistic và Pessimistic Locking

| Tiêu chí | Optimistic Locking | Pessimistic Locking |
|---|---|---|
| Cách hoạt động | Phát hiện xung đột khi ghi | Ngăn transaction khác sửa tài nguyên đang khóa |
| Cơ chế thường gặp | Version / compare-and-swap | Row lock, SELECT FOR UPDATE |
| Xung đột | Transaction có thể rollback và retry | Transaction khác chờ hoặc timeout |
| Phù hợp | Xung đột thấp đến vừa, transaction ngắn | Xung đột cao hoặc cần tuần tự hóa rõ |
| Chi phí | Có thể phải thực hiện lại công việc | Có thể tăng thời gian chờ và giảm throughput |
| Rủi ro | Retry sai có thể dùng lại dữ liệu cũ | Deadlock, lock contention, giữ khóa lâu |

Không có cơ chế tốt nhất cho mọi hệ thống. Hãy đo mức độ tranh chấp, thời gian transaction và hậu quả nghiệp vụ trước khi chọn.

## 10. Cơ sở dữ liệu là lớp bảo vệ bổ sung

### 10.1. Constraint giúp bảo vệ dữ liệu trước lỗi đồng thời

Một số invariant có thể được biểu diễn bằng constraint:

~~~sql
ALTER TABLE stock
ADD CONSTRAINT chk_stock_non_negative
CHECK (on_hand >= 0);

ALTER TABLE stock
ADD CONSTRAINT chk_reserved_non_negative
CHECK (reserved >= 0);

ALTER TABLE stock
ADD CONSTRAINT chk_reserved_not_over_on_hand
CHECK (reserved <= on_hand);
~~~

Constraint là hàng rào cuối cùng giúp cơ sở dữ liệu từ chối trạng thái vi phạm. Nó không thay thế mô hình miền vì database constraint không diễn đạt đầy đủ lý do nghiệp vụ, hành vi, quyền hạn hoặc sự kiện cần phát ra.

### 10.2. Unique constraint bảo vệ tính duy nhất

Nếu mỗi Reservation ID phải duy nhất trong phạm vi một Stock, cơ sở dữ liệu có thể có unique constraint trên cặp stock_id và reservation_id.

Kiểm tra trùng trong code giúp trả thông báo dễ hiểu, nhưng hai transaction đồng thời vẫn có thể cùng vượt qua kiểm tra trước khi ghi. Unique constraint xử lý cuộc đua ở nơi lưu trữ.

### 10.3. Cập nhật có điều kiện

Với một số mô hình đơn giản, có thể dùng một câu lệnh cập nhật nguyên tử có điều kiện:

~~~sql
UPDATE stock
SET reserved = reserved + :quantity
WHERE stock_id = :stockId
  AND on_hand - reserved >= :quantity;
~~~

Nếu số dòng cập nhật là 1, yêu cầu giữ hàng đã được chấp nhận ở cấp dữ liệu. Nếu là 0, điều kiện không còn đúng hoặc bản ghi không tồn tại.

Cách này cần được tích hợp cẩn thận với việc tạo Reservation và version của Aggregate trong cùng transaction. Nếu cập nhật số lượng thành công nhưng không ghi được Reservation, dữ liệu vẫn có thể sai. Không được xem một câu SQL đơn lẻ là giải pháp đầy đủ cho mọi invariant của Aggregate.

### 10.4. Tránh để nhiều nơi cùng ghi trực tiếp

Nếu API, batch job và message consumer đều cập nhật trực tiếp cột reserved theo các cách khác nhau, quy tắc sẽ bị phân tán. Hãy có một chủ sở hữu rõ ràng cho hành vi giữ hàng và bảo đảm mọi đường ghi đều tuân theo hợp đồng đó.

## 11. Transaction và tính nhất quán của Aggregate

### 11.1. Một thao tác Aggregate nên được lưu nguyên tử

Khi một hành vi thay đổi nhiều thành phần trong Aggregate, các thay đổi cần được commit hoặc rollback cùng nhau.

Ví dụ fulfill một Reservation:

- Chuyển Reservation từ ACTIVE sang FULFILLED.
- Giảm onHand.
- Bảo đảm reserved không vượt onHand.
- Ghi nhận sự kiện nghiệp vụ tương ứng nếu cần.

Nếu chỉ một phần được lưu, trạng thái Aggregate có thể mất nhất quán.

### 11.2. Transaction boundary thường bao quanh một Aggregate

DDD khuyến khích Aggregate là ranh giới nhất quán cho các invariant cần bảo vệ đồng bộ. Một use case thường tải một Aggregate, gọi hành vi và lưu nó trong một transaction.

Không nên mở một transaction kéo dài xuyên qua nhiều dịch vụ bên ngoài. Giao tiếp mạng có thể chậm, timeout hoặc thất bại; giữ khóa database trong thời gian đó dễ gây tắc nghẽn.

### 11.3. Không nhầm transaction database với quy trình nghiệp vụ dài

Một đơn hàng có thể cần giữ hàng, ủy quyền thanh toán, xác nhận đơn và tạo giao hàng. Đây là quy trình đi qua nhiều Aggregate hoặc Bounded Context.

Không nhất thiết phải khóa tất cả dữ liệu và giữ một transaction duy nhất cho toàn bộ quy trình. Thay vào đó, mỗi Aggregate bảo vệ invariant của nó; một Process Manager hoặc Saga điều phối các bước và hành động bù trừ khi cần.

## 12. Invariant giữa nhiều Aggregate và eventual consistency

### 12.1. Khi quy tắc vượt qua ranh giới Aggregate

Giả sử một đơn hàng có ba SKU ở hai kho. Mỗi Stock Aggregate có thể giữ hàng độc lập. Nhưng doanh nghiệp muốn xác nhận toàn bộ đơn chỉ khi tất cả dòng hàng đều được giữ.

Đây là quy tắc phối hợp nhiều Aggregate. Order không nên tự sửa dữ liệu của Stock; Stock cũng không nên tự xác nhận đơn thương mại.

Một quy trình điều phối có thể:

1. Gửi yêu cầu giữ hàng cho từng Stock Aggregate.
2. Thu thập kết quả giữ hàng.
3. Nếu tất cả thành công, tiếp tục xác nhận đơn.
4. Nếu một phần thất bại, giải phóng những Reservation đã tạo theo chính sách.
5. Ghi nhận kết quả cuối cùng của quy trình.

### 12.2. Eventual consistency có thể phù hợp

Khi các Aggregate cập nhật độc lập, có thể tồn tại một khoảng thời gian mà một bên đã thay đổi còn bên khác chưa nhận được thông tin.

Đây là eventual consistency nếu hệ thống có cơ chế truyền, retry và xử lý sự kiện để các bản chiếu hoặc trạng thái liên quan hội tụ theo thời gian.

Cần xác định:

- Trạng thái chờ có ý nghĩa gì?
- Bao lâu thì phải có kết quả?
- Khi một bước không phản hồi thì xử lý thế nào?
- Có thể hủy hoặc bù trừ không?
- Người dùng nhìn thấy trạng thái nào trong lúc chờ?

Eventual consistency không có nghĩa chấp nhận dữ liệu sai vô thời hạn. Quy trình phải có trách nhiệm xử lý trạng thái treo và kết quả đến muộn.

### 12.3. Dùng Saga hoặc Process Manager để điều phối

Saga hoặc Process Manager theo dõi tiến trình nhiều bước, gửi lệnh tiếp theo và xử lý hành động bù trừ.

Ví dụ, nếu giữ được hàng ở kho A nhưng không giữ được hàng ở kho B, Process Manager có thể yêu cầu giải phóng Reservation ở kho A. Việc giải phóng cũng là một hành vi nghiệp vụ và có thể cần xử lý retry.

Saga không tạo ra một invariant toàn cục được bảo đảm nguyên tử. Nó quản lý tiến trình để hệ thống đạt kết quả nhất quán theo thời gian và chính sách đã định nghĩa.

## 13. Những sai lầm thường gặp

### Chỉ kiểm tra invariant ở giao diện

Một API hoặc job khác có thể bỏ qua giao diện. Invariant phải được bảo vệ trong mô hình và tại nơi lưu trữ phù hợp.

### Đặt mọi quy tắc vào Aggregate Root

Aggregate Root bảo vệ invariant của Aggregate, nhưng không cần chứa mọi quy tắc của doanh nghiệp. Quy tắc phối hợp nhiều Aggregate có thể thuộc Application Service, Domain Service hoặc Process Manager.

### Aggregate quá lớn

Một Aggregate quá lớn làm tăng lock contention, tải dữ liệu và khả năng xung đột. Chỉ gom những đối tượng cần bảo đảm nhất quán cùng nhau.

### Aggregate quá nhỏ

Nếu một invariant cần nhiều đối tượng nhưng các đối tượng bị chia thành nhiều Aggregate, hệ thống phải phối hợp phức tạp và có thể để lộ trạng thái trung gian mà nghiệp vụ không chấp nhận.

### Nghĩ rằng transaction tự giải quyết mọi race condition

Transaction cung cấp cơ chế cô lập và commit, nhưng kết quả phụ thuộc isolation level, câu truy vấn và chiến lược khóa. Hai transaction có thể cùng đọc một snapshot hợp lệ rồi ghi các thay đổi xung đột nếu không có kiểm soát phù hợp.

### Retry mà không tải lại dữ liệu

Retry một câu lệnh dựa trên trạng thái cũ có thể lặp lại cùng lỗi hoặc phá invariant. Cần tải lại Aggregate và gọi hành vi trên dữ liệu mới.

### Dùng pessimistic lock cho toàn bộ quy trình

Giữ khóa trong lúc gọi payment gateway hoặc dịch vụ vận chuyển có thể làm nghẽn hệ thống. Hãy giữ transaction ngắn và điều phối bước bên ngoài bằng message hoặc process manager.

### Cho rằng database constraint thay thế mô hình miền

Constraint bảo vệ dữ liệu, nhưng không diễn đạt đầy đủ ngôn ngữ và hành vi nghiệp vụ. Mô hình miền vẫn cần sở hữu quyết định.

### Phát event trước khi transaction commit

Nếu event được gửi đi nhưng transaction lưu Aggregate rollback, hệ thống bên ngoài có thể tin rằng một sự việc đã xảy ra dù dữ liệu chưa được ghi. Cần cơ chế phát event an toàn sau commit, thường cân nhắc Transactional Outbox.

## 14. Kiểm thử invariant và concurrency

### 14.1. Unit test cho invariant của đối tượng

Kiểm tra Value Object từ chối giá trị không hợp lệ:

~~~java
@Test
void quantityCannotBeNegative() {
    assertThrows(
        IllegalArgumentException.class,
        () -> new Quantity(-1)
    );
}
~~~

Kiểm tra Reservation không thể chuyển trạng thái lần thứ hai:

~~~java
@Test
void releasedReservationCannotBeFulfilled() {
    Reservation reservation = new Reservation("R-1", 2);

    reservation.release();

    assertThrows(
        IllegalStateException.class,
        reservation::fulfill
    );
}
~~~

### 14.2. Unit test cho invariant của Aggregate

~~~java
@Test
void stockCannotReserveMoreThanAvailable() {
    Stock stock = new Stock("SKU-1", "WH-HCM", 5);

    stock.reserve("R-1", 3);

    assertThrows(
        InsufficientStockException.class,
        () -> stock.reserve("R-2", 3)
    );

    assertEquals(5, stock.onHand());
    assertEquals(3, stock.reservedQuantity());
    assertEquals(2, stock.availableQuantity());
}
~~~

Test này kiểm tra hành vi quan sát được: yêu cầu thứ hai bị từ chối và trạng thái Stock vẫn hợp lệ.

### 14.3. Kiểm thử concurrency ở cấp tích hợp

Unit test tuần tự không chứng minh hệ thống an toàn khi hai transaction cùng chạy. Cần integration test với database và transaction thực tế để xác nhận:

- Hai transaction cùng đọc một version.
- Một transaction commit trước.
- Transaction còn lại gặp optimistic lock conflict hoặc phải chờ khóa.
- Sau khi tải lại, invariant vẫn đúng.
- Tổng số lượng giữ không vượt tồn kho.
- Kết quả của yêu cầu thua cuộc được trả rõ ràng.

Có thể dùng hai thread và barrier/latch để đồng bộ thời điểm đọc, sau đó cho cả hai cùng gọi reserve. Kiểm tra kết quả cuối cùng trong database, không chỉ trạng thái trong bộ nhớ của từng thread.

### 14.4. Kiểm thử property-based

Với invariant số lượng, có thể sinh nhiều chuỗi thao tác ngẫu nhiên như receive, reserve, release và fulfill. Sau mỗi thao tác thành công, xác nhận:

\[
onHand \ge 0
\]

\[
0 \le reserved \le onHand
\]

Các thao tác không hợp lệ phải bị từ chối mà không để lại trạng thái sai. Property-based testing hữu ích khi có nhiều tổ hợp hành vi và trạng thái.

## 15. Bài tập thực hành: bảo vệ hạn mức ví điện tử

Một ví điện tử có số dư khả dụng và các giao dịch đang chờ. Chính sách giả định:

- Số dư khả dụng không được âm.
- Một giao dịch chi tiêu phải có số tiền dương.
- Tổng số tiền đang giữ cho các giao dịch chờ không được vượt quá số dư hiện có.
- Một khoản giữ chỉ được giải phóng hoặc hoàn tất một lần.
- Hai yêu cầu chi tiêu đồng thời không được cùng sử dụng phần số dư cuối cùng.

Hãy thực hiện:

1. Xác định invariant thuộc Money, Transaction và Wallet Aggregate.
2. Xác định Wallet là Aggregate Root hay cần một ranh giới khác.
3. Mô tả hành vi hold, release và capture.
4. Vẽ state transition cho một khoản giữ tiền.
5. Mô tả race condition khi hai yêu cầu cùng chi tiêu số dư cuối.
6. Chọn optimistic locking hoặc pessimistic locking và giải thích.
7. Xác định constraint ở database có thể hỗ trợ bảo vệ dữ liệu.
8. Viết unit test cho invariant và integration test cho hai yêu cầu đồng thời.

### 15.1. Gợi ý phân tích

Một cách phân chia có thể là:

| Thành phần | Trách nhiệm |
|---|---|
| Money | Giá trị tiền và loại tiền hợp lệ |
| Wallet | Số dư và tổng số tiền đang giữ |
| Transaction | Vòng đời của một yêu cầu chi tiêu |
| Wallet Aggregate Root | Bảo đảm số tiền đang giữ không vượt số dư |
| Application Service | Tải Wallet, gọi hold/release/capture và lưu transaction |
| Database | Version, constraint và transaction để bảo vệ cập nhật đồng thời |

Nếu nhiều Wallet hoặc nhiều hệ thống thanh toán tham gia một giao dịch, không nên cố giữ tất cả trong một Aggregate. Cần thiết kế quy trình điều phối, trạng thái chờ và bù trừ theo chính sách.

## 16. Checklist thiết kế invariant và concurrency

Trước khi hoàn thành một Aggregate, hãy kiểm tra:

- Đã liệt kê các invariant từ ngôn ngữ và ví dụ nghiệp vụ.
- Mỗi invariant có phạm vi sở hữu rõ ràng.
- Value Object bảo vệ tính hợp lệ của giá trị ngay khi tạo.
- Entity bảo vệ trạng thái và chuyển đổi hợp lệ.
- Aggregate Root là cổng vào cho thay đổi đối tượng con.
- Không để lộ collection hoặc tham chiếu mutable làm mất quyền kiểm soát.
- Các thay đổi cần nhất quán cùng nhau được lưu trong một transaction.
- Đã xác định khả năng có hai yêu cầu đồng thời trên cùng Aggregate.
- Đã chọn optimistic hoặc pessimistic locking theo mức tranh chấp.
- Retry luôn tải lại dữ liệu và đánh giá lại invariant.
- Constraint database hỗ trợ các điều kiện có thể biểu diễn ở tầng lưu trữ.
- Các quy tắc nhiều Aggregate có cơ chế điều phối và bù trừ.
- Event chỉ được công bố theo cơ chế an toàn sau commit.
- Có unit test cho invariant và integration test cho concurrency.

## Kết luận

Invariant xác định những điều kiện mà mô hình miền phải luôn bảo đảm. Value Object bảo vệ giá trị riêng lẻ, Entity bảo vệ vòng đời và trạng thái, còn Aggregate Root bảo vệ các quy tắc liên quan đến nhiều đối tượng trong cùng một ranh giới nhất quán.

Khi có nhiều yêu cầu đồng thời, việc kiểm tra điều kiện trên dữ liệu đã đọc là chưa đủ. Hệ thống cần transaction, kiểm soát phiên bản hoặc khóa phù hợp, constraint ở database và cơ chế retry dựa trên trạng thái mới nhất. Với quy tắc vượt qua nhiều Aggregate, hãy dùng điều phối và eventual consistency theo chính sách nghiệp vụ thay vì mở một transaction dài cho toàn bộ quy trình.

Thiết kế tốt bắt đầu từ câu hỏi: điều gì phải luôn đúng, ai chịu trách nhiệm bảo vệ nó và tại thời điểm nào hệ thống cam kết kết quả? Khi trả lời rõ ba câu hỏi đó, đội phát triển có thể chọn ranh giới Aggregate và cơ chế concurrency phù hợp với nghiệp vụ.

