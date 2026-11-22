# Phân biệt tạo mới với khôi phục đối tượng từ dữ liệu đã lưu

Trong Domain-Driven Design (DDD), một Entity hoặc Aggregate có thể xuất hiện trong bộ nhớ theo hai con đường khác nhau: được tạo mới vì một sự kiện nghiệp vụ vừa phát sinh, hoặc được khôi phục từ dữ liệu đã tồn tại để tiếp tục xử lý. Hai con đường này có thể tạo ra cùng một kiểu đối tượng trong chương trình, nhưng ý nghĩa nghiệp vụ và trách nhiệm của chúng không giống nhau.

Khi tạo mới, hệ thống bắt đầu một vòng đời mới. Nó cấp identity, áp dụng điều kiện khởi tạo, đặt trạng thái ban đầu và có thể ghi nhận một sự kiện như OrderPlaced. Khi khôi phục, hệ thống đang dựng lại một đối tượng đã tồn tại. Identity, trạng thái, thời điểm và các dữ liệu đã lưu phải được giữ nguyên. Việc khôi phục không được giả vờ rằng một nghiệp vụ mới vừa xảy ra.

Phân biệt rõ **creation** và **reconstitution** giúp tránh lỗi phát event lặp, gửi thông báo ngoài ý muốn, ghi đè trạng thái cũ bằng giá trị mặc định hoặc áp dụng sai quy tắc hiện tại lên dữ liệu lịch sử. Đây là một phần quan trọng khi thiết kế Entity, Aggregate, Factory, Repository và vòng đời của domain object.

## 1. Hai tình huống, hai ý nghĩa

Hãy xét một đơn hàng trực tuyến.

Khách hàng gửi yêu cầu đặt hàng lần đầu. Hệ thống cần kiểm tra thông tin, tạo OrderId, khởi tạo đơn ở trạng thái ban đầu và ghi nhận việc đặt hàng. Đây là **tạo mới**.

Một giờ sau, nhân viên mở màn hình chi tiết đơn. Ứng dụng đọc bản ghi đã lưu và dựng lại đối tượng Order để hiển thị hoặc thực hiện hành động tiếp theo. Đây là **khôi phục**.

| Khía cạnh | Tạo mới (Creation) | Khôi phục (Reconstitution) |
|---|---|---|
| Ý nghĩa | Bắt đầu một thực thể hoặc aggregate mới | Dựng lại thực thể đã tồn tại |
| Identity | Tạo identity mới theo quy tắc | Giữ nguyên identity đã lưu |
| Trạng thái | Khởi tạo trạng thái ban đầu hợp lệ | Khôi phục trạng thái hiện có |
| Thời điểm | Ghi nhận thời điểm tạo mới | Giữ nguyên thời điểm lịch sử |
| Giá trị mặc định | Có thể áp dụng default nghiệp vụ | Không thay thế dữ liệu đã lưu bằng default mới |
| Kiểm tra | Kiểm tra điều kiện để bắt đầu nghiệp vụ | Kiểm tra tính toàn vẹn của dữ liệu được khôi phục |
| Domain Event | Có thể tạo event phản ánh nghiệp vụ mới | Không phát lại event chỉ vì tải đối tượng |
| Side effect | Có thể khởi tạo quy trình sau commit | Không tự gửi email, thu tiền hoặc gọi dịch vụ ngoài |
| Nơi điều phối | Factory hoặc hành vi tạo mới của domain, được gọi từ application use case | Repository hoặc persistence mapper |

Cả hai có thể trả về một object cùng class Order, nhưng không nên dùng chung một đường khởi tạo khiến ý nghĩa của chúng bị trộn lẫn.

## 2. Tạo mới là một hành vi nghiệp vụ

Tạo mới không đơn giản là gọi constructor và gán vài field. Trong nhiều domain, việc bắt đầu một đối tượng phải thỏa các điều kiện nghiệp vụ.

Ví dụ, để đặt một đơn hàng, doanh nghiệp có thể yêu cầu:

- Có khách hàng hợp lệ.
- Có ít nhất một dòng hàng.
- Số lượng của từng dòng lớn hơn 0.
- Giá được xác định theo chính sách áp dụng tại thời điểm đặt.
- Địa chỉ giao hàng đáp ứng yêu cầu của phương thức vận chuyển.
- Đơn được tạo trong phạm vi kênh bán hàng được phép.

Các điều kiện này không nhất thiết đều nằm trong constructor. Một số cần dữ liệu từ hệ thống khác hoặc cần application service điều phối trước khi gọi factory. Tuy nhiên, domain model phải bảo vệ các invariant thuộc phạm vi của nó.

### Tạo identity mới

Identity phải duy nhất và ổn định trong phạm vi bounded context. Factory có thể nhận identity đã được application cấp hoặc tự tạo identity tùy thiết kế.

    public record OrderId(UUID value) {
        public OrderId {
            Objects.requireNonNull(value, "value");
        }

        public static OrderId newId() {
            return new OrderId(UUID.randomUUID());
        }
    }

Không nên dùng email, tên khách hàng hoặc thời điểm tạo làm identity nếu các giá trị đó có thể thay đổi hoặc không bảo đảm duy nhất.

### Khởi tạo trạng thái hợp lệ

Một đơn hàng mới thường bắt đầu ở DRAFT hoặc PLACED, tùy ngôn ngữ và quy trình của doanh nghiệp. Factory nên tạo đối tượng ở một trạng thái có ý nghĩa, không để caller tự gán các field để lắp ráp một trạng thái tùy ý.

    public static Order draft(
            OrderId id,
            CustomerId customerId,
            Instant createdAt
    ) {
        return new Order(
                id,
                customerId,
                List.of(),
                OrderStatus.DRAFT,
                createdAt,
                null,
                0
        );
    }

Nếu việc tạo đơn đã đồng nghĩa với việc khách hàng gửi đơn chính thức, factory có thể mang tên place(...) và tạo trạng thái tương ứng. Tên factory nên diễn đạt đúng hành vi nghiệp vụ thay vì tên kỹ thuật chung chung như createObject().

## 3. Factory giúp bảo vệ điều kiện tạo mới

Factory là nơi phù hợp để tập trung quy tắc khởi tạo khi việc tạo object cần nhiều dữ liệu, nhiều bước kiểm tra hoặc một ý nghĩa nghiệp vụ cụ thể.

Factory có thể là:

- Constructor khi quy tắc khởi tạo đơn giản.
- Static factory method trên Entity hoặc Aggregate.
- Một Domain Factory riêng khi việc tạo cần phối hợp nhiều đối tượng hoặc có thuật toán phức tạp.
- Application service điều phối dữ liệu cần thiết rồi gọi factory của domain.

Không phải lúc nào cũng cần tạo một class OrderFactory. Nếu một static factory method trên Order diễn đạt đủ rõ, một class riêng có thể chỉ làm tăng số lượng abstraction.

### Ví dụ factory đặt đơn

    public static Order place(
            OrderId id,
            CustomerId customerId,
            List<OrderLine> lines,
            Instant placedAt
    ) {
        Objects.requireNonNull(id);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(lines);
        Objects.requireNonNull(placedAt);

        if (lines.isEmpty()) {
            throw new EmptyOrderException();
        }

        List<OrderLine> validLines = List.copyOf(lines);

        return new Order(
                id,
                customerId,
                validLines,
                OrderStatus.PLACED,
                placedAt,
                null,
                0
        );
    }

Factory trên kiểm tra điều kiện để bắt đầu một đơn hàng. Các điều kiện như khách hàng có đang được phép mua hay giá có còn hiệu lực có thể cần application service hoặc domain policy phối hợp trước khi gọi factory.

Không nên nhồi mọi truy vấn database hoặc HTTP call vào factory. Factory thuộc domain nên tập trung vào việc tạo một mô hình hợp lệ từ dữ liệu và chính sách đã được cung cấp.

## 4. Khôi phục là dựng lại trạng thái đã tồn tại

Reconstitution là quá trình chuyển dữ liệu đã lưu thành một domain object có thể tiếp tục được sử dụng. Mục tiêu là tái tạo đúng identity và trạng thái trước khi lưu.

Một đơn hàng được khôi phục cần giữ:

- OrderId đã tồn tại.
- Khách hàng và các dòng hàng đã được ghi nhận.
- Trạng thái hiện tại.
- Thời điểm tạo, xác nhận, hủy hoặc hoàn tất.
- Các giá trị nghiệp vụ đã chốt, chẳng hạn đơn giá tại thời điểm đặt.
- Version hoặc metadata cần cho optimistic concurrency.
- Các dữ liệu cần thiết khác để tiếp tục bảo vệ invariant.

Không được tạo identity mới, đặt lại trạng thái thành DRAFT, thay thời điểm tạo bằng thời điểm hiện tại hoặc tính lại giá theo bảng giá hôm nay nếu nghiệp vụ yêu cầu giữ nguyên giá lịch sử.

### Ví dụ snapshot

Một persistence mapper có thể chuyển dữ liệu đã lưu thành snapshot:

    public record OrderSnapshot(
            UUID id,
            UUID customerId,
            List<OrderLineSnapshot> lines,
            String status,
            Instant createdAt,
            Instant confirmedAt,
            long version
    ) {
    }

Snapshot là biểu diễn dữ liệu cần để dựng lại aggregate. Nó không nhất thiết phải trùng cấu trúc bảng database; có thể được tạo từ nhiều bảng hoặc nhiều bản ghi.

### Khôi phục không phải tạo mới lần nữa

    static Order reconstitute(OrderSnapshot snapshot) {
        validatePersistedSnapshot(snapshot);

        return new Order(
                new OrderId(snapshot.id()),
                new CustomerId(snapshot.customerId()),
                snapshot.lines().stream()
                        .map(OrderLine::reconstitute)
                        .toList(),
                OrderStatus.valueOf(snapshot.status()),
                snapshot.createdAt(),
                snapshot.confirmedAt(),
                snapshot.version()
        );
    }

Phương thức reconstitute khôi phục các giá trị đã lưu. Nó không gọi place(), không tạo OrderId mới và không phát OrderPlaced.

Trong một số codebase, phương thức này có thể là package-private hoặc chỉ được gọi bởi repository mapper. Điều đó giúp hạn chế việc application code tùy ý dựng lại aggregate từ dữ liệu không đáng tin cậy.

## 5. Không áp dụng default mới lên dữ liệu đã lưu

Default có ý nghĩa trong lúc tạo mới. Khi khôi phục, dữ liệu đã lưu là nguồn để tái tạo trạng thái.

Ví dụ, giả sử phiên bản đầu của hệ thống tạo đơn với currency là VND. Sau này doanh nghiệp hỗ trợ nhiều loại tiền và default mới của hệ thống là USD.

Nếu mapper khôi phục một đơn cũ mà field currency bị thiếu rồi tự gán default hiện tại USD, đơn hàng lịch sử có thể bị diễn giải sai. Giá trị mặc định mới không thể thay thế ý nghĩa của dữ liệu tại thời điểm tạo.

Cần phân biệt:

- **Default nghiệp vụ lúc tạo:** giá trị được chọn khi một entity mới bắt đầu.
- **Giá trị persisted:** dữ liệu đã được ghi nhận cho entity hiện có.
- **Migration/backfill:** thay đổi dữ liệu cũ theo một quyết định có chủ đích.
- **Fallback khi đọc:** cách xử lý có kiểm soát khi dữ liệu cũ thiếu field hoặc chưa có phiên bản mới.

Nếu dữ liệu lịch sử thiếu field do schema cũ, hãy dùng migration hoặc một quy tắc tương thích được xác định rõ. Không nên để một default ngầm trong constructor âm thầm thay đổi ý nghĩa của dữ liệu.

## 6. Kiểm tra dữ liệu khi reconstitution

Khôi phục không có nghĩa là tin mọi byte trong database đều hợp lệ. Dữ liệu có thể bị hỏng, thiếu field, sai kiểu, bị ghi bởi phiên bản cũ hoặc chịu ảnh hưởng của một bug trước đây.

Tuy nhiên, cần phân biệt kiểm tra tính toàn vẹn với kiểm tra điều kiện để tạo mới.

### Structural integrity

Các điều kiện cấu trúc cơ bản thường phải được kiểm tra:

- Identity không được null.
- Trạng thái phải ánh xạ được hoặc có cách xử lý phiên bản cũ.
- Các trường bắt buộc theo schema phải hiện diện.
- Collection và value object phải được dựng đúng kiểu.
- Version không được có giá trị bất hợp lý.
- Quan hệ dữ liệu cần thiết phải được tải đầy đủ theo aggregate mapping.

Nếu snapshot không thể biểu diễn một aggregate có ý nghĩa, repository nên báo lỗi dữ liệu hoặc lỗi khôi phục rõ ràng. Không nên tự động thay bằng một object mới.

### Invariant và dữ liệu lịch sử

Có những invariant phải đúng ở mọi thời điểm, chẳng hạn identity tồn tại hoặc số lượng không âm. Nhưng một số quy tắc nghiệp vụ thay đổi theo thời gian.

Ví dụ, năm trước doanh nghiệp cho phép một loại đơn có cách xử lý đặc biệt. Chính sách hiện tại đã bỏ loại đó. Khi khôi phục đơn cũ, không nên từ chối tải chỉ vì đơn không thỏa quy tắc dành cho đơn mới ngày hôm nay.

Cần xác định:

- Invariant nào phải đúng với mọi dữ liệu ở mọi phiên bản?
- Quy tắc nào chỉ áp dụng cho giao dịch mới kể từ một ngày hiệu lực?
- Dữ liệu cũ có cần migration hay chỉ cần được giữ để đọc?
- Có hành vi nào bị cấm với dữ liệu lịch sử nhưng vẫn cần cho phép tra cứu?
- Khi một entity cũ được thay đổi, những quy tắc hiện tại nào được áp dụng?

Không có một câu trả lời chung cho mọi domain. Chính sách tương thích dữ liệu cần được làm rõ với chuyên gia nghiệp vụ.

## 7. Không phát lại Domain Event khi khôi phục

Đây là một khác biệt quan trọng giữa creation và reconstitution.

Khi một đơn hàng mới được đặt, OrderPlaced có thể là sự kiện nghiệp vụ cần được ghi nhận. Các consumer có thể dùng event để bắt đầu fulfillment, gửi thông báo hoặc cập nhật read model.

Khi repository tải lại đơn hàng để hiển thị, việc phát OrderPlaced lần nữa sẽ khiến các consumer hiểu nhầm rằng khách hàng vừa đặt một đơn mới.

| Hoạt động | Có nên phát creation event? | Lý do |
|---|---|---|
| Tạo đơn mới bằng hành vi place() | Có thể có | Một sự kiện nghiệp vụ mới thực sự xảy ra |
| Tải đơn từ database | Không | Chỉ khôi phục trạng thái đã tồn tại |
| Refresh Aggregate | Không | Không có nghiệp vụ mới chỉ vì đọc lại |
| Khôi phục từ snapshot | Không | Snapshot là trạng thái đã ghi nhận |
| Replay event để dựng state | Không phát lại ra broker | Event đang được dùng làm input để tái dựng |
| Thực hiện hành vi mới như cancel() | Có thể có | Một sự kiện mới xảy ra nếu hành vi thành công |

Domain Event có thể được lưu trong bộ nhớ của aggregate hoặc application unit of work. Repository/publisher chỉ chuyển event ra ngoài khi transaction chứa thay đổi tương ứng commit thành công.

Không nên đặt logic phát event trong constructor chung được gọi cả khi tạo mới và khôi phục.

## 8. Tránh side effect khi khôi phục

Constructor hoặc mapper không nên tự thực hiện các hành động bên ngoài như:

- Gửi email hoặc SMS.
- Gọi payment provider.
- Gửi request đến hệ thống vận chuyển.
- Publish message lên broker.
- Ghi audit event với ý nghĩa "đối tượng vừa được tạo".
- Tạo reservation hoặc cấp phát tài nguyên.
- Tự động lưu lại entity chỉ vì nó vừa được load.

Các thao tác trên có thể xảy ra khi một hành vi nghiệp vụ thành công, nhưng không phải là tác dụng phụ của việc dựng object.

Một quy tắc thực tế là: **đọc dữ liệu và khôi phục object phải không làm thay đổi thế giới bên ngoài**. Nếu việc load một đơn hàng khiến hệ thống gửi thêm email hoặc thu tiền lần nữa, ranh giới giữa persistence và nghiệp vụ đã bị phá vỡ.

## 9. Repository chịu trách nhiệm khôi phục Aggregate

Repository cung cấp giao diện truy cập Aggregate theo ngôn ngữ domain. Khi gọi findById, caller mong nhận được Aggregate đã được khôi phục đầy đủ để tiếp tục làm việc.

    public interface OrderRepository {
        Optional<Order> findById(OrderId id);

        void save(Order order);
    }

Implementation thuộc Infrastructure có thể:

1. Đọc bản ghi order.
2. Đọc các dòng hàng thuộc aggregate.
3. Chuyển dữ liệu persistence thành snapshot hoặc trực tiếp mapping.
4. Gọi cơ chế reconstitution.
5. Trả Aggregate về application layer.

Repository che giấu chi tiết database và cách dữ liệu được phân tán qua bảng. Domain model không cần biết dùng JPA, JDBC, document database hay một cơ chế lưu trữ khác.

### Phân biệt repository và factory

| Thành phần | Trách nhiệm |
|---|---|
| Domain Factory | Tạo đối tượng mới từ dữ liệu và điều kiện nghiệp vụ |
| Repository | Tìm, lưu và khôi phục Aggregate đã tồn tại |
| Persistence Mapper | Chuyển đổi giữa record/snapshot và domain object |
| Application Service | Điều phối use case, gọi factory hoặc repository theo tình huống |

Repository không nên giả vờ rằng dữ liệu tìm thấy là một đối tượng mới. Factory không nên tải một entity đã tồn tại chỉ để gọi constructor như thể nó vừa được tạo.

## 10. ORM và constructor của Entity

Một số ORM cần constructor không tham số hoặc dùng reflection để khôi phục object. Cơ chế đó là chi tiết persistence, nhưng có thể ảnh hưởng đến cách tổ chức domain model.

Cần lưu ý:

- ORM có thể khởi tạo object rồi gán field theo mapping.
- Constructor không tham số không đồng nghĩa với factory tạo mới về mặt nghiệp vụ.
- Setter public để ORM dùng có thể vô tình cho phép application sửa trạng thái tùy ý.
- Annotation persistence đặt trực tiếp trên entity có thể làm domain phụ thuộc framework.
- Lazy loading có thể khiến object được khôi phục chưa có đủ dữ liệu để thực hiện một số hành vi.
- Callback như PostLoad không nên phát Domain Event hoặc gọi dịch vụ bên ngoài.

Có thể dùng persistence model riêng rồi map sang domain model để giữ ranh giới rõ hơn. Với dự án nhỏ hoặc mô hình đơn giản, dùng ORM trực tiếp trên domain object cũng có thể là lựa chọn thực tế, nhưng cần kiểm soát các tác động đến constructor, field access và lifecycle callback.

Không nên ép một kiến trúc phức tạp chỉ để tránh mọi annotation. Điều cần bảo vệ là quy tắc nghiệp vụ không bị ORM điều khiển và reconstitution không tạo side effect.

## 11. Ví dụ hoàn chỉnh: Creation và Reconstitution trong một Aggregate

Đoạn mã dưới đây minh họa hai đường vào riêng biệt. Constructor nội bộ nhận toàn bộ trạng thái; factory nghiệp vụ và phương thức khôi phục quyết định cách sử dụng constructor đó.

    public final class Order {
        private final OrderId id;
        private final CustomerId customerId;
        private final List<OrderLine> lines;
        private OrderStatus status;
        private final Instant createdAt;
        private final Instant confirmedAt;
        private final long version;
        private final List<DomainEvent> domainEvents = new ArrayList<>();

        private Order(
                OrderId id,
                CustomerId customerId,
                List<OrderLine> lines,
                OrderStatus status,
                Instant createdAt,
                Instant confirmedAt,
                long version
        ) {
            this.id = Objects.requireNonNull(id);
            this.customerId = Objects.requireNonNull(customerId);
            this.lines = List.copyOf(lines);
            this.status = Objects.requireNonNull(status);
            this.createdAt = Objects.requireNonNull(createdAt);
            this.confirmedAt = confirmedAt;
            this.version = version;
        }

        public static Order place(
                CustomerId customerId,
                List<OrderLine> lines,
                Instant now
        ) {
            if (lines == null || lines.isEmpty()) {
                throw new EmptyOrderException();
            }

            Order order = new Order(
                    OrderId.newId(),
                    customerId,
                    lines,
                    OrderStatus.PLACED,
                    now,
                    null,
                    0
            );

            order.domainEvents.add(
                    new OrderPlaced(order.id, now)
            );

            return order;
        }

        static Order reconstitute(OrderSnapshot snapshot) {
            validatePersistedSnapshot(snapshot);

            return new Order(
                    new OrderId(snapshot.id()),
                    new CustomerId(snapshot.customerId()),
                    snapshot.lines().stream()
                            .map(OrderLine::reconstitute)
                            .toList(),
                    OrderStatus.valueOf(snapshot.status()),
                    snapshot.createdAt(),
                    snapshot.confirmedAt(),
                    snapshot.version()
            );
        }

        private static void validatePersistedSnapshot(
                OrderSnapshot snapshot
        ) {
            Objects.requireNonNull(snapshot);
            Objects.requireNonNull(snapshot.id());
            Objects.requireNonNull(snapshot.customerId());
            Objects.requireNonNull(snapshot.lines());
            Objects.requireNonNull(snapshot.status());
            Objects.requireNonNull(snapshot.createdAt());

            if (snapshot.version() < 0) {
                throw new CorruptOrderDataException(
                        "Negative aggregate version"
                );
            }
        }

        public List<DomainEvent> domainEvents() {
            return List.copyOf(domainEvents);
        }

        public void clearDomainEvents() {
            domainEvents.clear();
        }

        public OrderId id() {
            return id;
        }

        public OrderStatus status() {
            return status;
        }

        public long version() {
            return version;
        }
    }

Ví dụ có một số điểm cần chú ý:

- place() tạo identity mới và khởi tạo trạng thái nghiệp vụ.
- place() ghi nhận OrderPlaced vì một hành vi mới vừa xảy ra.
- reconstitute() dùng identity, status, timestamp và version đã lưu.
- reconstitute() không tạo event và không gọi dịch vụ ngoài.
- validatePersistedSnapshot() kiểm tra dữ liệu khôi phục có cấu trúc tối thiểu hợp lệ.
- Constructor không public để caller không tùy ý dựng Aggregate từ một tổ hợp field bất kỳ.

Trong hệ thống thực tế, domainEvents nên dùng một kiểu DomainEvent cụ thể; event cần được lưu/publish theo transaction và có thể cần metadata như event ID, occurredAt, correlation ID.

## 12. Khôi phục từ dữ liệu nhiều bảng

Một Aggregate không nhất thiết được lưu trong một bảng. Ví dụ Order có thể được lưu trong:

    orders
      id
      customer_id
      status
      created_at
      confirmed_at
      version

    order_lines
      id
      order_id
      product_id
      quantity
      unit_price

Khi khôi phục, repository cần tải phần dữ liệu thuộc Aggregate boundary và dựng lại một Order hoàn chỉnh.

    public Optional<Order> findById(OrderId id) {
        return orderJpaRepository.findById(id.value())
                .map(orderRow -> {
                    List<OrderLineRow> lineRows =
                            lineJpaRepository.findByOrderId(id.value());

                    OrderSnapshot snapshot =
                            mapper.toSnapshot(orderRow, lineRows);

                    return Order.reconstitute(snapshot);
                });
    }

Nếu OrderLine là thành phần bên trong Aggregate, repository không nên trả từng line cho application để application tự ghép lại và bỏ qua invariant của Order.

Cũng cần cân nhắc lazy loading. Nếu một hành vi của Order cần toàn bộ line để kiểm tra tổng số lượng, repository phải bảo đảm dữ liệu cần thiết đã được tải trong phạm vi unit of work phù hợp. Không nên để Aggregate thực hiện hành vi khi các thành phần cần thiết chưa được khôi phục đầy đủ.

## 13. Reconstitution và Event Sourcing

Khôi phục từ snapshot/database và tái dựng từ event là hai cách khác nhau để tạo lại trạng thái của một Aggregate đã tồn tại.

### Khôi phục từ snapshot hoặc relational database

Repository đọc trạng thái hiện tại đã lưu và mapping thành Aggregate. Đây là cách phổ biến trong hệ thống dùng state-based persistence.

### Tái dựng từ event stream

Với Event Sourcing, trạng thái hiện tại được tính bằng cách áp dụng lần lượt các event đã lưu lên một Aggregate mới hoặc một state ban đầu.

    OrderPlaced
        ↓
    OrderLineAdded
        ↓
    OrderConfirmed
        ↓
    ShipmentStarted
        ↓
    ShipmentCompleted

Khi replay event, handler dùng event để dựng lại state. Việc replay không được phát lại những event tương tự ra broker hoặc gọi side effect như gửi email. Event đang là dữ liệu đầu vào của quá trình tái dựng, không phải một nghiệp vụ mới vừa xảy ra.

Nếu có snapshot để giảm thời gian replay, hệ thống khôi phục snapshot trước rồi áp dụng các event tiếp theo. Snapshot và event stream cần có version/schema compatibility rõ ràng.

Không phải hệ thống DDD nào cũng cần Event Sourcing. Domain Event có thể được dùng để tích hợp và audit trong khi trạng thái hiện tại vẫn được lưu trong bảng thông thường.

## 14. Dữ liệu cũ và thay đổi mô hình

Domain model có thể thay đổi theo thời gian. Một snapshot được lưu bởi phiên bản phần mềm cũ có thể không chứa field mới hoặc dùng tên trạng thái đã được thay đổi.

Ví dụ, phiên bản cũ dùng SUBMITTED, phiên bản mới dùng PLACED. Khi khôi phục, mapper cần biết cách ánh xạ giá trị cũ sang mô hình hiện tại nếu hai giá trị có cùng ý nghĩa nghiệp vụ.

Có thể dùng:

- Database migration để cập nhật dữ liệu trước khi ứng dụng mới đọc.
- Mapper tương thích ngược để đọc schema cũ.
- Snapshot version để chọn logic chuyển đổi.
- Adapter cho dữ liệu lịch sử khi chưa thể migration toàn bộ.
- Quy trình sửa dữ liệu có kiểm soát và audit.

Không nên dùng enum mapping trực tiếp cho dữ liệu lịch sử nếu có khả năng giá trị cũ không còn tồn tại; cần xử lý lỗi hoặc mapping version rõ ràng. Tương tự, không nên tự điền giá trị mới mà không xác định ý nghĩa nghiệp vụ.

Migration là một thay đổi dữ liệu có chủ đích. Reconstitution là quá trình đọc và dựng lại dữ liệu đã được chấp nhận. Không nên âm thầm biến reconstitution thành migration.

## 15. Quy tắc nào được kiểm tra ở mỗi đường?

Có thể chia việc kiểm tra thành các lớp trách nhiệm:

| Kiểm tra | Khi tạo mới | Khi khôi phục |
|---|---|---|
| Identity | Tạo identity mới hoặc xác nhận identity được cấp hợp lệ | Bảo toàn identity đã lưu |
| Required fields | Kiểm tra dữ liệu đầu vào và điều kiện tạo | Kiểm tra snapshot có đủ dữ liệu cần thiết |
| Business preconditions | Kiểm tra điều kiện để bắt đầu nghiệp vụ | Không chạy lại như thể nghiệp vụ đang được bắt đầu |
| Initial state | Thiết lập trạng thái ban đầu | Khôi phục trạng thái hiện có |
| Current invariants | Bảo vệ các invariant khi tạo và thay đổi | Kiểm tra các invariant cấu trúc cần luôn đúng; xử lý dữ liệu lịch sử theo chính sách |
| Defaults | Áp dụng default nghiệp vụ hiện hành | Giữ dữ liệu đã lưu; không áp dụng default mới một cách ngầm định |
| Domain events | Có thể tạo event cho nghiệp vụ vừa xảy ra | Không phát event creation khi chỉ load |
| External side effects | Chỉ thực hiện theo use case và sau commit thích hợp | Không thực hiện do load |
| Version | Khởi tạo version ban đầu | Khôi phục version để kiểm soát concurrency |

Bảng này không có nghĩa bỏ qua mọi invariant khi khôi phục. Một Aggregate không được phép tồn tại trong trạng thái cấu trúc không thể biểu diễn. Nhưng quy tắc chỉ áp dụng cho giao dịch mới không nên tự động dùng để từ chối toàn bộ dữ liệu lịch sử.

## 16. Những lỗi dễ gặp

### Gọi factory tạo mới khi load dữ liệu

Repository đọc bản ghi cũ nhưng gọi Order.place(...). Kết quả có thể tạo ID mới, đặt lại trạng thái hoặc phát OrderPlaced thêm lần nữa.

### Dùng constructor chung với default

Constructor tự đặt status là DRAFT, createdAt là thời điểm hiện tại hoặc currency theo cấu hình mới. Khi khôi phục, những default đó ghi đè ý nghĩa dữ liệu lịch sử.

### Phát event trong constructor

Constructor được gọi cả khi tạo mới và khôi phục. Nếu nó phát event, mọi lần load có thể kích hoạt consumer như thể nghiệp vụ mới xảy ra.

### Gọi API hoặc gửi thông báo trong quá trình load

Đọc một Aggregate không nên thu tiền, gửi email hoặc tạo shipment. Side effect cần được gắn với hành vi nghiệp vụ và quản lý theo transaction/workflow.

### Khôi phục object một phần

Repository chỉ tải root nhưng bỏ qua child entity cần thiết cho invariant. Aggregate có vẻ hợp lệ nhưng khi hành vi chạy lại thiếu dữ liệu hoặc lazy loading phát sinh lỗi ngoài dự kiến.

### Áp quy tắc mới lên mọi dữ liệu lịch sử

Một chính sách mới có thể khiến dữ liệu cũ không còn thỏa điều kiện tạo giao dịch. Cần phân biệt quy tắc bất biến xuyên thời gian với chính sách có hiệu lực theo giai đoạn.

### Tự sửa dữ liệu sai trong constructor

Nếu snapshot có dữ liệu bất thường, constructor âm thầm đổi giá trị để object "hợp lệ" có thể che giấu lỗi và làm mất bằng chứng. Hãy báo lỗi rõ hoặc dùng một quy trình migration/repair có kiểm soát.

### Cho phép application tự dựng Aggregate tùy ý

Nếu constructor hoặc setter mở công khai, nhiều use case có thể tạo ra những tổ hợp trạng thái không hợp lệ. Hãy giới hạn đường tạo và khôi phục ở factory/repository phù hợp.

## 17. Kiểm thử creation và reconstitution riêng biệt

Hai đường khởi tạo có mục tiêu kiểm thử khác nhau. Không nên dùng một test constructor duy nhất để kết luận cả hai đều đúng.

### Kiểm thử tạo mới

- Identity được tạo đúng và không trùng theo cơ chế đã chọn.
- Trạng thái ban đầu đúng.
- Required fields được kiểm tra.
- Điều kiện nghiệp vụ để bắt đầu được thực thi.
- Default nghiệp vụ được áp dụng đúng thời điểm.
- Event được tạo khi hành vi nghiệp vụ tương ứng xảy ra.
- Không thể tạo object ở trạng thái khởi đầu không hợp lệ.

### Kiểm thử khôi phục

- Identity được giữ nguyên.
- Trạng thái và timestamp được khôi phục chính xác.
- Version được bảo toàn.
- Child entities và value objects được dựng đầy đủ.
- Không phát lại event tạo mới.
- Không gửi email, gọi API hoặc thực hiện side effect.
- Dữ liệu thiếu hoặc hỏng được xử lý rõ ràng.
- Snapshot cũ được mapping theo chính sách tương thích.
- Việc khôi phục không tự áp dụng default mới.

Ví dụ test:

    class OrderReconstitutionTest {

        @Test
        void restoresIdentityStatusAndVersionWithoutCreationEvent() {
            OrderSnapshot snapshot = samplePlacedOrderSnapshot();

            Order order = Order.reconstitute(snapshot);

            assertEquals(snapshot.id(), order.id().value());
            assertEquals(OrderStatus.PLACED, order.status());
            assertEquals(snapshot.version(), order.version());
            assertTrue(order.domainEvents().isEmpty());
        }

        @Test
        void rejectsSnapshotWithoutIdentity() {
            OrderSnapshot snapshot = snapshotWithoutId();

            assertThrows(
                    CorruptOrderDataException.class,
                    () -> Order.reconstitute(snapshot)
            );
        }
    }

Ví dụ test cần được điều chỉnh theo constructor và kiểu dữ liệu thực tế. Ngoài unit test, có thể cần repository integration test để xác nhận mapper tải đủ dữ liệu từ database và không phát side effect khi đọc.

## 18. Checklist thiết kế

Trước khi hoàn thiện đường tạo mới và khôi phục, hãy kiểm tra:

- Đã phân biệt rõ use case tạo mới với use case đọc Aggregate chưa?
- Factory có diễn đạt đúng hành vi nghiệp vụ khởi tạo không?
- Identity mới được tạo theo quy tắc của bounded context chưa?
- Trạng thái ban đầu và các precondition đã được xác định chưa?
- Repository có giữ nguyên identity, status, timestamp và version khi khôi phục không?
- Reconstitution có tách khỏi factory tạo mới không?
- Constructor có vô tình áp default mới lên dữ liệu đã lưu không?
- Domain Event có chỉ được tạo khi nghiệp vụ mới thực sự xảy ra không?
- Load/refresh có tránh side effect bên ngoài không?
- Aggregate có được khôi phục đầy đủ trong boundary cần thiết không?
- Dữ liệu lịch sử và schema version cũ có chính sách tương thích không?
- Invariant nào phải đúng mọi thời điểm và quy tắc nào chỉ áp dụng cho giao dịch mới đã được phân biệt chưa?
- Lỗi dữ liệu hỏng có được phát hiện và báo rõ không?
- Creation test và reconstitution test có được viết riêng không?

## 19. Kết luận

Tạo mới và khôi phục đều tạo ra một domain object trong bộ nhớ, nhưng chỉ tạo mới mới bắt đầu một vòng đời nghiệp vụ. Creation phải thiết lập identity, trạng thái ban đầu và các điều kiện để nghiệp vụ bắt đầu. Reconstitution phải bảo toàn identity, trạng thái, thời điểm và version đã tồn tại để đối tượng có thể tiếp tục hoạt động.

Khi tách hai đường này, Factory chịu trách nhiệm tạo đối tượng mới theo quy tắc domain; Repository và mapper chịu trách nhiệm khôi phục đối tượng đã lưu. Việc đọc dữ liệu không phát lại creation event, không áp dụng default mới và không kích hoạt side effect.

Sự phân biệt này giữ cho vòng đời Entity nhất quán, giúp Aggregate bảo vệ invariant và khiến persistence trở thành một chi tiết có thể thay đổi mà không làm sai lệch ý nghĩa nghiệp vụ.
