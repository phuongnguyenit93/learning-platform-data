# Giới hạn của API Commons khi thao tác nhiều hệ thống dữ liệu

## Mục tiêu và phạm vi

Spring Data Commons cung cấp một ngôn ngữ chung cho nhiều tác vụ dữ liệu: repository, CRUD, derived query, phân trang, sắp xếp, projection và auditing. Nhờ đó, mã ứng dụng có thể dùng các hình thức API quen thuộc khi làm việc với nhiều store.

Sự thống nhất của API không tạo ra một hệ thống lưu trữ thống nhất. Hai repository có cùng phương thức `save` vẫn có thể ghi vào hai backend có giao dịch, mô hình nhất quán, kiểu định danh và cách xử lý lỗi khác nhau.

Bài học thuộc chương **Ranh giới giao dịch**, giúp bạn:

- Xác định phần bảo đảm mà Commons cung cấp và phần thuộc trách nhiệm của từng store.
- Phân tích lỗi khi một use case ghi vào nhiều hệ thống.
- Phân biệt giao dịch cục bộ, giao dịch phân tán và quy trình nhất quán cuối cùng.
- Áp dụng outbox, xử lý lặp an toàn và bù trừ đúng phạm vi.
- Hiểu giới hạn của truy vấn, phân trang, projection và metadata khi dữ liệu nằm ở nhiều nơi.

Ví dụ dùng database quan hệ làm nguồn dữ liệu chính, một document store để xây read model và một hệ thống tìm kiếm. Đây là mô hình minh họa; Commons không bắt buộc ứng dụng phải sử dụng kiến trúc đó.

## 1. API chung không đồng nghĩa chung bảo đảm thực thi

Ở mức abstraction, bạn có thể gặp:

```java
<S extends T> S save(S entity);
Optional<T> findById(ID id);
void deleteById(ID id);
```

Các chữ ký quen thuộc giúp tổ chức mã theo repository. Chúng không tự quy định rằng:

- Các repository dùng chung một connection hoặc session.
- Hai backend cùng commit hoặc cùng rollback.
- Một lần đọc ở hệ thống B lập tức thấy lần ghi vừa hoàn tất ở hệ thống A.
- Hai kiểu ID có cùng cách mã hóa.
- Tất cả store hỗ trợ cùng isolation, khóa hoặc transaction nhiều bản ghi.
- Một query có thể tự join dữ liệu giữa các backend.

Có thể hình dung ba tầng bảo đảm:

| Tầng | Ví dụ bảo đảm |
|---|---|
| Hợp đồng API | Có phương thức tìm theo ID, kiểu kết quả biểu diễn không tìm thấy |
| Store và tài nguyên cụ thể | Atomicity một document, transaction trong một database, khả năng khóa |
| Quy trình ứng dụng | Đồng bộ read model, retry, phát hiện xử lý trùng và bù trừ khi nhiều bước thất bại |

Commons giúp ở tầng abstraction. Tính đúng của một quy trình xuyên hệ thống cần được thiết kế thêm ở hai tầng còn lại.

## 2. Bắt đầu bằng invariant và nguồn dữ liệu có thẩm quyền

Giả sử chức năng tạo đơn hàng liên quan ba hệ thống:

```text
OrderService
    |
    +-- SQL: đơn hàng và các dòng hàng
    |
    +-- Document store: màn hình tổng hợp đơn hàng
    |
    +-- Search engine: tìm kiếm theo từ khóa
```

Không nên bắt đầu bằng việc gọi ba phương thức `save`. Trước hết, cần xác định dữ liệu nào quyết định tính đúng của nghiệp vụ.

Ví dụ:

| Dữ liệu hoặc invariant | Nơi chịu trách nhiệm |
|---|---|
| Đơn hàng và dòng hàng phải hợp lệ cùng nhau | Database SQL của dịch vụ đơn hàng |
| Mã đơn hàng là duy nhất | Ràng buộc trong nguồn dữ liệu chính |
| Read model hiển thị trạng thái gần nhất đã đồng bộ | Document store |
| Chỉ mục hỗ trợ tìm kiếm | Search engine |
| Trạng thái thanh toán đã được xác nhận | Hệ thống thanh toán tương ứng |

Read model và chỉ mục có thể là dữ liệu dẫn xuất. Khi chúng chậm cập nhật, đơn hàng vẫn tồn tại ở nguồn chính.

Ngược lại, nếu “không được tạo đơn nếu không giữ được tồn kho” là yêu cầu nghiệp vụ, tồn kho không còn là một bản sao phục vụ tìm kiếm. Nó cần một quy trình phối hợp có trạng thái, không thể chỉ coi như tác vụ cập nhật chỉ mục.

Nguồn dữ liệu có thẩm quyền phải được chỉ rõ cho từng quyết định. Tránh để database A và B cùng tự coi mình là nguồn chính cho cùng một trường mà không có quy tắc giải quyết xung đột.

## 3. Vì sao một annotation không bao phủ mọi repository?

Xét đoạn mã minh họa:

```java
@Transactional(transactionManager = "ordersTx")
public Order create(CreateOrder command) {
    Order saved = sqlOrders.save(Order.from(command));

    orderViews.save(OrderView.from(saved));

    searchOrders.save(SearchOrder.from(saved));

    return saved;
}
```

Giả định:

- `sqlOrders` dùng JPA và database SQL do `ordersTx` quản lý.
- `orderViews` dùng MongoDB riêng.
- `searchOrders` dùng một hệ thống tìm kiếm riêng.

Nếu `ordersTx` chỉ là transaction manager cục bộ của SQL, annotation trên không tự đăng ký MongoDB và search engine vào một giao dịch chung.

Một tình huống có thể xảy ra:

```text
1. SQL bắt đầu giao dịch.
2. Repository SQL thực hiện thay đổi trong giao dịch đó.
3. Document store lưu read model thành công.
4. Search engine báo lỗi.
5. Giao dịch SQL rollback theo quy tắc lỗi.

Trạng thái cuối:
- SQL không có đơn hàng đã commit.
- Document store có thể vẫn có read model của đơn đó.
- Search engine chưa có kết quả tương ứng.
```

Thay đổi thứ tự gọi chỉ thay đổi kiểu trạng thái dở dang có thể xuất hiện. Nó không tạo ra atomicity xuyên ba backend.

Ngay cả khi cả ba lời gọi đều trả về thành công, vẫn cần xét thời điểm commit của giao dịch SQL. Commit có thể thất bại sau khi service đã hoàn thành phần thân phương thức.

## 4. Hai transaction manager vẫn là hai ranh giới

Một ứng dụng có thể cấu hình:

- `ordersTx` cho database đơn hàng.
- `catalogTx` cho database danh mục.
- Một manager khác cho document store nếu backend và cấu hình hỗ trợ giao dịch.

Điều đó cho phép quản lý từng tài nguyên đúng cách. Nó không tự tạo một cơ chế commit toàn cục.

Ví dụ service A gọi service B:

```text
Service A: giao dịch ordersTx
    |
    +-- Service B: giao dịch catalogTx
            |
            +-- commit catalogTx
    |
    +-- A phát sinh lỗi
            |
            +-- rollback ordersTx
```

Nếu B đã commit một giao dịch cục bộ độc lập, rollback của A không tự hoàn tác dữ liệu của B.

Cần phân biệt:

| Cơ chế | Phạm vi bảo đảm |
|---|---|
| Một local transaction manager | Tài nguyên mà manager đó thực sự quản lý |
| Nhiều manager cục bộ | Nhiều ranh giới độc lập nếu không có cơ chế phối hợp phù hợp |
| Commit lần lượt từng tài nguyên | Có thể thất bại giữa chừng và để lại kết quả một phần |
| Giao dịch phân tán có coordinator | Chỉ áp dụng cho các tài nguyên và giao thức có hỗ trợ, được cấu hình đúng |
| Saga hoặc workflow | Phối hợp các bước cục bộ, theo dõi trạng thái và thực hiện xử lý tiếp hoặc bù trừ |

Propagation như `REQUIRED` hoặc `REQUIRES_NEW` không biến các manager cục bộ bất kỳ thành một transaction manager phân tán.

### Vị trí của JTA và các giao thức phối hợp

Một hệ thống có thể dùng hạ tầng như JTA với các tài nguyên tương thích để thực hiện giao dịch phân tán. Khả năng đó đến từ transaction infrastructure, driver, backend và cấu hình tài nguyên.

Không thể kết luận rằng một repository tham gia được giao dịch phân tán chỉ vì nó kế thừa interface của Commons.

Ngược lại, cũng không nên phát biểu rằng mọi giao dịch nhiều database đều bất khả thi. Câu hỏi đúng là: những tài nguyên cụ thể này có hỗ trợ cơ chế phối hợp đã chọn không, và chúng đã được tham gia đúng chưa?

## 5. Gán repository đúng store chỉ là bước cấu hình đầu tiên

Khi có nhiều module Spring Data trên classpath, cần làm rõ repository nào thuộc store nào.

Ví dụ:

```java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<Order, UUID> {
}
```

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderViewRepository
        extends MongoRepository<OrderView, String> {
}
```

Ứng dụng cũng cần cấu hình phạm vi scan, mapping và tài nguyên của từng nhóm repository phù hợp. Một interface chỉ kế thừa abstraction chung có thể cần thêm thông tin để module xác định đúng store khi nhiều module cùng tham gia.

Tránh dùng việc gắn annotation của nhiều store lên cùng một domain type như một cách “tự động đồng bộ”. Mapping cho hai backend không tạo ra cơ chế sao chép, giao dịch chung hoặc giải quyết xung đột.

Một cách tổ chức rõ ràng là phân biệt:

- Domain hoặc aggregate dùng cho quyết định nghiệp vụ.
- Entity được lưu trong nguồn chính.
- Document dùng cho read model.
- Document dùng cho chỉ mục tìm kiếm.
- Dữ liệu sự kiện dùng để chuyển thay đổi giữa các hệ thống.

Các kiểu có thể chia sẻ thông tin, nhưng cần chuyển đổi có chủ đích. Repository metadata chỉ giúp framework hiểu cấu trúc của từng loại repository; nó không chứng minh các bản sao luôn nhất quán.

## 6. Lỗi xuyên hệ thống không chỉ có thành công hoặc thất bại

Một lời gọi mạng có thể kết thúc với trạng thái không chắc chắn:

```text
Ứng dụng gửi yêu cầu ghi
    |
Backend ghi thành công
    |
Phản hồi bị mất do kết nối đứt
    |
Ứng dụng nhận timeout
```

Ứng dụng không thể chỉ từ timeout mà kết luận backend chưa ghi.

Bảng phân tích tối thiểu cho hai bước A và B:

| Tình huống | Điều có thể đã xảy ra | Rủi ro nếu retry thiếu thiết kế |
|---|---|---|
| A chưa hoàn tất, B chưa được gọi | Chưa biết A đã commit hay chưa nếu mất phản hồi | Tạo trùng dữ liệu ở A |
| A commit, B lỗi rõ ràng | Có dữ liệu ở A, chưa có ở B | Bản sao bị thiếu |
| A commit, B timeout | B có thể đã ghi hoặc chưa ghi | Bị ghi hoặc phát tác dụng phụ lặp |
| A và B thành công, tiến trình dừng trước khi ghi nhận kết quả | Dữ liệu có thể đủ, trạng thái workflow chưa cập nhật | Chạy lại cả quy trình |
| B nhận các cập nhật sai thứ tự | B có thể ghi đè trạng thái mới bằng trạng thái cũ | Read model lùi phiên bản |

Do đó, chiến lược xử lý cần có định danh thao tác, trạng thái tiến trình và cách kiểm tra kết quả. Một khối `try/catch` bao quanh nhiều repository không đủ để giải quyết các tình huống này.

## 7. Outbox: ghi ý định đồng bộ trong cùng giao dịch với nguồn chính

Nếu document store và search engine là dữ liệu dẫn xuất, có thể tách phần ghi nguồn chính khỏi phần đồng bộ.

```text
Trong một giao dịch SQL:
    ghi Order
    ghi OutboxEvent
    commit cùng nhau

Sau commit:
    relay đọc sự kiện đã commit
    gửi sự kiện
    consumer cập nhật read model và chỉ mục
```

Điều kiện cốt lõi là bản ghi nghiệp vụ và outbox nằm trong cùng phạm vi giao dịch thật sự. Ghi order vào SQL rồi ghi “outbox” sang một database độc lập không giải quyết được khoảng trống giữa hai lần ghi.

### 7.1. Dữ liệu một sự kiện outbox

Một bản ghi có thể chứa:

| Trường | Mục đích |
|---|---|
| `eventId` | Nhận diện duy nhất sự kiện và phát hiện xử lý trùng |
| `aggregateId` | Nhận diện aggregate nguồn |
| `aggregateRevision` | Thứ tự thay đổi nghiệp vụ của aggregate khi cần |
| `eventType` | Loại sự kiện |
| `schemaVersion` | Phiên bản cấu trúc payload |
| `payload` | Dữ liệu cần cho consumer |
| `occurredAt` | Thời điểm được ghi nhận, phục vụ quan sát |
| Trạng thái chuyển phát | Theo dõi relay theo thiết kế cụ thể |

`aggregateRevision` trong ví dụ là revision nghiệp vụ được quản lý rõ ràng. Không mặc định đó là giá trị `@Version` của JPA đã được tăng ở mọi thời điểm gọi `save`.

`occurredAt` cũng không phải cơ chế sắp thứ tự toàn cục đáng tin cậy giữa các máy.

### 7.2. Service chỉ ghi dữ liệu thuộc ranh giới cục bộ

```java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public PlaceOrderService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional(transactionManager = "ordersTx")
    public UUID place(CreateOrder command) {
        Order saved = orders.save(Order.create(command));

        OutboxEvent event = OutboxEvent.orderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                saved.getBusinessRevision(),
                saved.toEventPayload());

        outbox.save(event);

        return saved.getId();
    }
}
```

Ví dụ giả định:

- `OrderRepository` và `OutboxRepository` đều là repository SQL dùng cùng tài nguyên của `ordersTx`.
- Domain đã kiểm tra dữ liệu và khởi tạo business revision đúng.
- Các entity, kiểu lệnh và phương thức chuyển payload đã được định nghĩa phù hợp.
- Mapping, schema và khả năng tham gia giao dịch đã được cấu hình.

Service không cập nhật trực tiếp read model trong transaction này. Nó ghi một ý định bền vững để đồng bộ sau khi dữ liệu nguồn đã commit.

Nếu có transaction bao ngoài, commit cuối cùng vẫn theo ranh giới ngoài đó. Không công bố đơn hàng đã commit chỉ vì phần thân phương thức đã trả về.

## 8. Outbox vẫn cần xử lý chuyển phát lặp

Outbox giải quyết việc ghi dữ liệu nguồn cùng ý định phát sự kiện. Nó không tự làm cho thao tác gửi sự kiện và ghi nhận “đã gửi” trở thành nguyên tử với broker hoặc consumer.

Ví dụ relay:

```text
1. Đọc sự kiện chưa chuyển phát.
2. Gửi sự kiện thành công.
3. Tiến trình dừng trước khi đánh dấu đã chuyển phát.
4. Khởi động lại và gửi lại cùng sự kiện.
```

Việc gửi lại cùng `eventId` phải được dự kiến trong thiết kế.

Nếu đổi thứ tự thành “đánh dấu đã gửi rồi mới gửi”, tiến trình có thể dừng giữa hai bước khiến sự kiện không được gửi nhưng đã bị bỏ qua. Vì vậy không thể chỉ đổi thứ tự để có bảo đảm đúng một lần.

Relay cần chính sách phù hợp về:

- Cách nhiều instance nhận việc để tránh tranh chấp không kiểm soát.
- Khôi phục công việc khi một instance dừng.
- Retry có giới hạn tốc độ và khoảng chờ.
- Phát hiện sự kiện lỗi kéo dài.
- Theo dõi độ trễ và số sự kiện tồn đọng.
- Lưu giữ hoặc dọn dữ liệu sau khi đáp ứng yêu cầu vận hành.

Chiến lược khóa, lease hoặc đọc log thay đổi phụ thuộc backend và công cụ triển khai. Commons không cung cấp một thuật toán relay phổ quát cho mọi store.

## 9. Consumer phải xử lý lặp và thứ tự một cách có chủ đích

### 9.1. Idempotency không chỉ là bắt lỗi trùng ID

Một consumer cần xác định phạm vi của thao tác lặp. Ví dụ, áp dụng cùng sự kiện hai lần phải có tác dụng như áp dụng một lần.

Cách sau có race condition:

```text
if eventId chưa được xử lý:
    tăng tổng số đơn hàng
    đánh dấu eventId đã xử lý
```

Hai consumer có thể cùng kiểm tra trước khi một bên kịp đánh dấu. Tiến trình cũng có thể dừng sau khi tăng tổng nhưng trước khi ghi dấu.

Nếu dùng inbox để nhận diện sự kiện đã xử lý, việc ghi dấu và cập nhật trạng thái nghiệp vụ cần nằm trong cùng transaction của consumer, kèm ràng buộc hoặc thao tác nguyên tử phù hợp.

```text
Giao dịch cục bộ của consumer:
    nhận quyền xử lý eventId bằng cơ chế chống trùng
    cập nhật dữ liệu đích
    commit cả hai
```

Nếu store đích không hỗ trợ transaction cho các bản ghi cần cập nhật, phải đổi cách lưu, dùng thao tác idempotent khác hoặc chấp nhận một quy trình khôi phục riêng. Không thể mặc định inbox ở một database sẽ bảo vệ nguyên tử cho cập nhật ở database khác.

### 9.2. Snapshot và delta có quy tắc khác nhau

Xét hai sự kiện:

```text
revision 10: trạng thái đầy đủ của đơn hàng
revision 11: trạng thái đầy đủ của đơn hàng
```

Nếu read model đã ở revision 11, nó có thể bỏ qua snapshot revision 10 theo một phép cập nhật có điều kiện nguyên tử.

Với delta, chẳng hạn “tăng số lượng thêm 2”, việc bỏ qua một revision bị thiếu có thể làm sai kết quả. Consumer phải có cách phát hiện khoảng trống, xử lý đúng thứ tự hoặc tái dựng từ nguồn chính.

Không sử dụng mô hình “revision lớn hơn thì ghi đè” cho mọi loại sự kiện mà chưa phân biệt snapshot và delta.

### 9.3. Cập nhật phiên bản phải nguyên tử

Một chuỗi “đọc revision hiện tại, so sánh trong Java, rồi ghi” vẫn có thể bị hai consumer xen kẽ.

Cần cơ chế phù hợp ở store đích, chẳng hạn:

- Conditional update hoặc compare-and-set.
- Optimistic concurrency của backend.
- Transaction cục bộ.
- Tuần tự hóa công việc theo aggregate cùng cơ chế khôi phục thích hợp.

Khóa optimistic của entity ở SQL không tự bảo vệ document trong MongoDB hoặc bản ghi trong search engine.

### 9.4. Xóa cũng cần chống dữ liệu cũ quay lại

Nếu read model bị xóa hoàn toàn, một sự kiện cũ đến muộn có thể tạo lại nó. Tùy yêu cầu, cần giữ tombstone hoặc metadata revision để consumer biết rằng một lần xóa mới hơn đã xảy ra.

Định danh aggregate, vòng đời tái tạo và quy tắc tái sử dụng ID phải rõ ràng. `deleteById` trên một repository không tự xử lý những vấn đề đồng bộ này.

## 10. Retry yêu cầu cả hợp đồng idempotency ở đầu vào

Xử lý sự kiện trùng không giải quyết hoàn toàn việc người dùng gửi lại yêu cầu tạo đơn hàng.

Ví dụ:

```text
Client gửi yêu cầu tạo đơn.
Server commit thành công.
Phản hồi bị mất.
Client gửi lại cùng yêu cầu.
```

Nếu mỗi lần server đều tạo order ID và event ID mới, outbox vẫn hoạt động đúng nhưng có thể có hai đơn hàng hợp lệ về mặt kỹ thuật.

Khi use case cần chống tạo trùng, có thể dùng khóa idempotency của yêu cầu với các điều kiện:

- Phạm vi khóa rõ ràng, chẳng hạn theo khách hàng hoặc tenant.
- Có ràng buộc nguyên tử ngăn hai yêu cầu cùng chiếm khóa.
- Liên kết khóa với dữ liệu yêu cầu hoặc fingerprint phù hợp.
- Lưu kết quả hoặc trạng thái xử lý để trả lại khi yêu cầu được gửi lại.
- Phối hợp bản ghi idempotency với dữ liệu nghiệp vụ trong cùng ranh giới khi cần.

Một khóa giống nhau nhưng payload khác nhau phải có quy tắc xử lý rõ ràng; không được âm thầm coi là cùng thao tác.

Idempotency là tính chất của một thao tác trong phạm vi đã định nghĩa. Nó không được tạo ra chỉ bằng cách chọn `CrudRepository` hoặc dùng UUID.

## 11. Saga: dùng cho nhiều bước nghiệp vụ có trạng thái riêng

Outbox phù hợp để đưa thay đổi đã commit ra các hệ thống khác. Khi nhiều hệ thống cùng thực hiện quyết định nghiệp vụ, thường cần một workflow rõ ràng hơn.

Ví dụ:

```text
Tạo đơn trạng thái PENDING
    |
Giữ tồn kho
    |
Yêu cầu thanh toán
    |
Xác nhận đơn
```

Nếu bước thanh toán thất bại sau khi giữ tồn kho, quy trình có thể cần giải phóng phần tồn kho đã giữ và chuyển đơn sang trạng thái phù hợp.

Một saga điều phối các transaction cục bộ và các bước xử lý tiếp hoặc bù trừ. Nó không tạo ra cùng một rollback vật lý trên tất cả backend.

| Thao tác đã xảy ra | Xử lý tiếp hoặc bù trừ có thể cần |
|---|---|
| Đã giữ tồn kho | Giải phóng reservation theo quy tắc của kho |
| Đã thu tiền | Thực hiện quy trình hoàn tiền được hệ thống thanh toán hỗ trợ |
| Đã gửi thông báo | Có thể gửi thông báo điều chỉnh; không thể “chưa từng gửi” |
| Đã xác nhận giao hàng | Phải xử lý theo trạng thái thực tế, có thể cần can thiệp nghiệp vụ |

Bù trừ cũng có thể thất bại hoặc phải retry. Vì thế workflow cần lưu trạng thái bền vững, nhận diện các bước đã thực hiện và có cách xử lý trường hợp chưa kết thúc.

Không nên dùng `catch` rồi gọi `delete` ngược trên mọi repository để giả lập saga. Lệnh xóa đó có thể không tương đương một hành động bù trừ hợp lệ và còn có thể thất bại.

## 12. Đọc dữ liệu xuyên store không có snapshot chung tự động

Giả sử ứng dụng đọc:

1. Đơn hàng từ SQL.
2. Trạng thái giao hàng từ một dịch vụ khác.
3. Read model khách hàng từ MongoDB.

Ngay cả khi từng lần đọc đều thành công, các giá trị có thể phản ánh những thời điểm khác nhau.

Ví dụ:

```text
t1: đọc Order ở trạng thái PAID
t2: hệ thống khác chuyển Order sang CANCELLED
t3: đọc Shipment ở trạng thái vừa cập nhật
```

Kết quả tổng hợp không mặc nhiên đại diện cho một thời điểm nhất quán chung.

Một transaction chỉ bao SQL không tạo snapshot cho lời gọi MongoDB hoặc HTTP. Projection của Spring Data cũng chỉ mô tả dữ liệu cần trả về theo khả năng query và mapping của store tương ứng; nó không tạo một distributed snapshot.

Cách xử lý phụ thuộc hợp đồng đọc:

- Dùng một read model đã tổng hợp cho màn hình chấp nhận độ trễ.
- Đọc trực tiếp nguồn có thẩm quyền cho quyết định cần trạng thái mới nhất.
- Đưa revision hoặc thời điểm cập nhật vào kết quả khi thông tin đó hữu ích.
- Thiết kế một giao thức kiểm tra tính hợp lệ khi cần tránh quyết định dựa trên dữ liệu đã cũ.

Không dùng trạng thái hiển thị từ chỉ mục tìm kiếm làm bằng chứng duy nhất rằng một thao tác nghiệp vụ nhạy với thay đổi vẫn hợp lệ.

## 13. Pageable, Sort và count không tự kết hợp thành truy vấn liên store

Giả sử cần tìm:

> Các đơn hàng có khách VIP trong MongoDB, sắp xếp theo tổng tiền ở SQL, rồi lấy 20 kết quả đầu.

Một cách dễ sai:

```text
Lấy 20 đơn hàng đầu từ SQL theo tổng tiền.
Đọc khách hàng từ MongoDB.
Lọc lại khách VIP trong Java.
Trả kết quả như một trang 20 phần tử.
```

Cách này chỉ lọc tập đã bị giới hạn. Nó có thể bỏ qua những đơn hợp lệ nằm ngoài 20 bản ghi đầu và không cung cấp đúng tổng số kết quả phù hợp.

Các vấn đề khác:

- Ghép hai trang cục bộ không tự tạo một trang toàn cục.
- Cộng count của các store có thể đếm trùng cùng thực thể.
- Một `Sort` yêu cầu property không tồn tại trong store đang query không tự biến thành remote join.
- Thứ tự của `findAllById` không nên được mặc định trùng với thứ tự ID đầu vào nếu hợp đồng cụ thể không bảo đảm.
- Dữ liệu thay đổi trong lúc tổng hợp có thể làm phần dữ liệu và count lệch nhau.

Các hướng thiết kế có thể gồm:

| Nhu cầu | Cách tổ chức phù hợp để xem xét |
|---|---|
| Tìm kiếm đa điều kiện xuyên nguồn | Read model hoặc chỉ mục đã chứa các trường cần lọc và sắp xếp |
| Trang chi tiết cho một số ID đã biết | Batch lookup và ghép kết quả theo ID rõ ràng |
| Báo cáo có mốc dữ liệu xác định | Snapshot hoặc pipeline dữ liệu có quy tắc thời điểm rõ ràng |
| Quyết định nghiệp vụ cần tính đúng tức thời | Đọc và xác nhận ở nguồn chịu trách nhiệm cho invariant |

Thuật toán trộn kết quả từ nhiều nguồn chỉ đúng khi có những giả định về thứ tự, tính đầy đủ và trạng thái dữ liệu. Kiểu `Page` hoặc `Slice` không cung cấp những giả định đó thay ứng dụng.

## 14. Định danh, auditing và metadata cũng có giới hạn

### 14.1. ID cần hợp đồng chuyển đổi

Một ID ở SQL có thể được biểu diễn bằng UUID, trong khi document store lưu nó dưới dạng chuỗi hoặc một trường riêng.

Cần xác định:

- Đó là ID nghiệp vụ dùng chung hay ID kỹ thuật của từng bản sao?
- Tenant có phải một phần của khóa không?
- Cách chuẩn hóa chữ hoa, chữ thường hoặc định dạng có quan trọng không?
- ID được tái sử dụng hay luôn biểu diễn một thực thể duy nhất trong vòng đời hệ thống?
- Consumer tìm bản sao bằng trường nào?

Generics `Repository<T, ID>` mô tả kiểu ID ở một repository. Nó không kiểm tra tính tương đương của ID giữa hai backend.

### 14.2. Auditing không phải đồng hồ commit toàn cục

Các metadata như người tạo, ngày tạo và ngày sửa giúp truy vết thay đổi theo tích hợp của từng store.

Chúng không tự chứng minh:

- Hai lần ghi đã commit cùng nhau.
- Thứ tự nghiệp vụ giữa các máy trùng với thứ tự timestamp.
- Một sự kiện đã được áp dụng ở mọi consumer.
- Một thao tác đã hoàn tất ở hệ thống bên ngoài.

Nếu một tiến trình đồng bộ ghi read model, cần quyết định auditor biểu diễn người dùng gốc, tài khoản dịch vụ hay cả hai dưới các trường riêng. Không âm thầm đánh mất nguồn gốc thay đổi khi chuyển hệ thống.

### 14.3. Version và schema version có mục đích khác nhau

| Metadata | Câu hỏi nó giúp trả lời |
|---|---|
| Optimistic locking version | Bản ghi có bị thay đổi cạnh tranh theo cơ chế của store này không? |
| Aggregate revision | Thay đổi nghiệp vụ này nằm ở vị trí nào trong chuỗi của aggregate? |
| Event schema version | Payload có cấu trúc nào để consumer giải mã? |
| Correlation ID | Những hoạt động nào thuộc cùng một luồng xử lý? |
| Event ID | Đây có phải sự kiện đã từng được nhận không? |

Không dùng một trường version duy nhất rồi mặc định nó giải quyết cả khóa cạnh tranh, thứ tự sự kiện và tương thích schema.

## 15. Hợp đồng API cần phản ánh tiến trình thật

Nếu ghi nguồn chính đã commit nhưng read model chưa cập nhật, API nên diễn đạt đúng trạng thái đó.

Ví dụ một kết quả nghiệp vụ có thể cung cấp:

```json
{
  "orderId": "4c72d5e2-448d-4fe4-ae59-31713e17022e",
  "orderState": "PENDING",
  "operationId": "op-2026-001"
}
```

Các trạng thái và mã định danh này phải được lưu hoặc suy ra từ mô hình xử lý thật. Không gán trạng thái thành công toàn cục chỉ vì lời gọi đầu tiên đã thành công.

Việc chọn HTTP status phụ thuộc hợp đồng cụ thể: tạo tài nguyên nguồn chính đã hoàn tất và tiếp nhận một workflow chưa hoàn tất là hai tình huống cần được mô tả rõ.

Khi đọc theo ID vừa được tạo, có thể hướng người gọi về nguồn chính hoặc một endpoint trạng thái phù hợp. Tránh yêu cầu client lập tức tìm trong chỉ mục đang đồng bộ rồi coi kết quả chưa xuất hiện là tạo thất bại.

Nếu ứng dụng chấp nhận nhất quán cuối cùng, cần nói rõ phần nào có thể chậm, cách quan sát tiến trình và trường hợp nào được retry.

## 16. Khôi phục và đối soát là một phần của thiết kế

Một hệ thống đồng bộ cần có khả năng phát hiện bản sao bị thiếu hoặc sai, kể cả khi đường xử lý bình thường đã có retry.

Ví dụ các thao tác đối soát:

- So sánh revision của read model với nguồn chính theo từng aggregate.
- Phát hiện sự kiện tồn đọng quá lâu.
- Tìm workflow chưa đi tới trạng thái kết thúc.
- Tái dựng chỉ mục từ dữ liệu nguồn.
- Kiểm tra các bản sao không còn aggregate nguồn tương ứng.
- Theo dõi tỷ lệ sự kiện trùng, sai thứ tự và không giải mã được.

Tái dựng read model phải xét cập nhật xảy ra trong thời gian tái dựng. Một bản quét cũ ghi đè lên dữ liệu mới có thể tạo sai lệch mới nếu thiếu quy tắc revision hoặc chuyển đổi thế hệ dữ liệu.

Các số liệu hữu ích gồm độ trễ đồng bộ, thời gian mắc kẹt của workflow và số công việc cần can thiệp. Chỉ đếm “repository không ném exception” không đo được tính nhất quán xuyên hệ thống.

## 17. Chọn cách phối hợp theo bảo đảm cần có

| Yêu cầu chính | Hướng thiết kế cần đánh giá |
|---|---|
| Nhiều thay đổi trong cùng tài nguyên phải nguyên tử | Một transaction cục bộ có phạm vi phù hợp |
| Nhiều tài nguyên cần atomicity và có hỗ trợ giao thức phối hợp | Transaction infrastructure phân tán tương thích, cấu hình và vận hành đúng |
| Cập nhật dữ liệu dẫn xuất sau khi nguồn chính commit | Outbox hoặc cơ chế chuyển thay đổi bền vững, consumer xử lý lặp |
| Nhiều hệ thống thực hiện các bước nghiệp vụ độc lập | Saga hoặc workflow có trạng thái và xử lý bù trừ |
| Truy vấn kết hợp dữ liệu nhiều nguồn thường xuyên | Read model hoặc chỉ mục tổng hợp có hợp đồng độ trễ |
| Yêu cầu mạng được gửi lại mà không tạo tác dụng lặp | Hợp đồng idempotency với lưu trạng thái và ràng buộc nguyên tử |

Các cơ chế có thể kết hợp. Một saga có thể dùng outbox để phát sự kiện cho từng bước. Một consumer có thể dùng transaction cục bộ để cập nhật inbox cùng dữ liệu đích.

Điều cần giữ rõ là phạm vi của từng bảo đảm. Không có một interface Commons duy nhất tự thay thế mọi cơ chế trong bảng.

## 18. Bài thực hành

Thiết kế một chức năng tạo đơn có SQL là nguồn chính và document store là read model:

1. Liệt kê invariant nào phải được bảo vệ trong transaction SQL.
2. Viết luồng ghi order cùng outbox bằng hai repository dùng chung tài nguyên.
3. Định nghĩa event ID, aggregate ID, business revision và schema version.
4. Mô tả cách relay khôi phục sau khi gửi thành công nhưng chưa ghi nhận đã gửi.
5. Thiết kế consumer chịu được cùng sự kiện gửi hai lần.
6. Mô tả cách xử lý revision 12 đến trước revision 11 cho sự kiện snapshot và cho sự kiện delta.
7. Thiết kế cách chống tạo trùng khi client gửi lại yêu cầu sau timeout.
8. Xác định endpoint dùng để đọc trạng thái ngay sau khi tạo đơn.
9. Giải thích vì sao lấy một trang SQL rồi lọc theo dữ liệu MongoDB không tự tạo đúng trang toàn cục.
10. Đưa ra cách phát hiện và sửa read model bị thiếu.

Các tình huống cần phân tích bao gồm tiến trình dừng sau commit nguồn chính, mất phản hồi mạng, consumer xử lý xong nhưng chưa xác nhận thông điệp và lỗi bù trừ. Với mỗi tình huống, hãy chỉ ra dữ liệu bền vững nào giúp quy trình tiếp tục.

## 19. Những điều cần nắm vững

Spring Data Commons thống nhất cách diễn đạt nhiều thao tác dữ liệu, nhưng không thống nhất giao dịch, thời điểm quan sát hay khả năng truy vấn của các backend.

Khi nhiều hệ thống cùng tham gia, hãy xác định nguồn có thẩm quyền, phạm vi atomicity thực sự và trạng thái có thể xuất hiện khi một bước thất bại. Sau đó chọn transaction, outbox, idempotency, workflow và read model theo bảo đảm mà nghiệp vụ cần.

Một thiết kế đúng phải giải thích được cách tiếp tục sau lỗi và cách nhận biết dữ liệu đã đồng bộ. Chỉ có nhiều lời gọi repository trả về thành công chưa đủ để chứng minh điều đó.
