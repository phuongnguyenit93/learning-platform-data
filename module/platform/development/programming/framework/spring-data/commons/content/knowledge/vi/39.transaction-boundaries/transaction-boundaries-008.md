# Optimistic locking, retry và yêu cầu idempotency theo store

## 1. Ba cơ chế giải quyết ba vấn đề khác nhau

Một dịch vụ nhận yêu cầu giữ một suất học cuối cùng. Hai request cùng đọc số suất còn lại bằng 1, rồi cùng ghi kết quả bằng 0. Nếu cả hai đều báo thành công, ứng dụng đã bán hai suất dù dữ liệu cuối cùng vẫn trông hợp lệ.

Optimistic locking giúp phát hiện việc dữ liệu đã thay đổi kể từ lúc đọc. Retry cho phép thực hiện lại một lần thử khi loại lỗi đó có thể phục hồi. Idempotency giúp một yêu cầu logic bị gửi lặp không tạo tác dụng nghiệp vụ lặp. Ba cơ chế cần phối hợp nhưng không thay thế nhau.

| Cơ chế | Câu hỏi chính | Không tự bảo đảm |
| --- | --- | --- |
| Optimistic locking | Bản ghi có còn ở phiên bản tôi đã đọc không? | Cùng một request chỉ được xử lý một lần |
| Retry | Có thể thực hiện lại công việc sau lỗi tạm thời không? | Lần trước chắc chắn chưa commit |
| Idempotency | Gửi lại cùng yêu cầu có tạo thêm tác dụng nghiệp vụ không? | Hai yêu cầu khác nhau không tranh chấp cùng dữ liệu |

Trong Spring Data Commons, repository, CRUD và metadata cung cấp cách tổ chức truy cập dữ liệu dùng chung. Semantics của version, transaction, ghi có điều kiện và thông báo lỗi vẫn phụ thuộc Spring Data module cùng datastore thực tế. Không nên suy ra rằng một annotation hoặc một phương thức `save()` sẽ có cùng bảo đảm trên mọi kho.

## 2. Optimistic locking dựa trên phiên bản như thế nào?

### 2.1. Từ đọc đến ghi có điều kiện

Giả sử bản ghi tồn kho có trạng thái:

```text
id = 42
available = 1
version = 7
```

Hai tiến trình cùng đọc phiên bản 7. Khi ghi, điều kiện không chỉ là đúng ID mà còn phải đúng phiên bản đã đọc:

```sql
-- Minh họa compare-and-set cho một cơ sở dữ liệu quan hệ.
UPDATE stock
SET available = :new_available,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

Luồng cạnh tranh có thể diễn ra như sau:

```text
A đọc: available=1, version=7
B đọc: available=1, version=7
A ghi với điều kiện version=7 -> thành công, version thành 8
B ghi với điều kiện version=7 -> không còn khớp
```

Trong đường ghi có hỗ trợ optimistic locking, kết quả không khớp được diễn giải thành xung đột, thường thông qua một exception thuộc họ `OptimisticLockingFailureException` sau khi được tầng tích hợp dịch exception phù hợp.

Câu SQL chỉ minh họa cơ chế. Tên cột, cách cập nhật version và đường phát hiện lỗi do provider hoặc module quyết định. Không tự viết SQL tương tự rồi mặc định nó sẽ tạo đúng exception của repository.

### 2.2. Xung đột bảo vệ dữ liệu, không quyết định nghiệp vụ thay ứng dụng

Khi B gặp xung đột, ứng dụng cần đọc lại trạng thái mới. Nếu suất đã hết, kết quả nghiệp vụ hợp lệ là từ chối đăng ký, không phải tiếp tục ghi bằng mọi giá.

Với thông tin cá nhân được sửa trên màn hình, retry tự động còn có thể không phù hợp. Người dùng sửa từ một bản dữ liệu cũ cần biết có thay đổi khác để quyết định hợp nhất. Việc âm thầm đọc lại rồi ghi toàn bộ dữ liệu từ form cũ có thể ghi đè thay đổi mới mà optimistic locking vừa phát hiện.

Do đó, cần phân biệt:

- **Lệnh có thể tính lại:** giữ một suất nếu vẫn còn, cộng một lượng vào bộ đếm, chuyển trạng thái khi điều kiện còn đúng.
- **Bản cập nhật dựa trên snapshot của người dùng:** thay nội dung bằng giá trị từ biểu mẫu đã mở trước đó; thường cần trả xung đột hoặc cơ chế hợp nhất có chủ đích.

## 3. Version phải được ánh xạ và quản lý đúng theo module

### 3.1. Ví dụ riêng cho Spring Data JPA

Với JPA hiện đại dùng Jakarta Persistence, trường version sử dụng `jakarta.persistence.Version`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
class Stock {

    @Id
    private Long id;

    @Version
    private Long version;

    private int available;

    protected Stock() {
    }

    void decrease(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        if (available < quantity) {
            throw new IllegalStateException("Không đủ tồn kho");
        }
        available -= quantity;
    }

    int getAvailable() {
        return available;
    }
}
```

```java
interface StockRepository extends CrudRepository<Stock, Long> {
}
```

Các đoạn mã lược bỏ import của repository và cấu hình ứng dụng. Provider JPA quản lý version cho entity đã được mapping. Không tự tăng version trong phương thức `decrease()` để mô phỏng công việc của provider.

Trong đường cập nhật JPA, xung đột có thể chỉ xuất hiện khi flush hoặc commit. Vì vậy, một lời gọi `save()` trả về chưa chứng minh lần thử đã thành công. Phạm vi bắt lỗi để retry phải bao gồm cả việc hoàn tất transaction.

### 3.2. So sánh các store thường gặp

| Module hoặc kiểu truy cập | Cơ chế cần hiểu | Hệ quả khi thiết kế retry |
| --- | --- | --- |
| Spring Data JPA | Version do JPA provider quản lý với annotation JPA; kiểm tra có thể xảy ra khi flush/commit | Bỏ lần thử thất bại, dùng persistence context và transaction phù hợp cho lần thử mới |
| Spring Data MongoDB | Các đường thao tác có hỗ trợ `org.springframework.data.annotation.Version` dùng version trong điều kiện ghi | Xác nhận thao tác cụ thể có kiểm tra version và dùng write concern có xác nhận phù hợp |
| Spring Data JDBC | Version trên aggregate root được hỗ trợ trong đường ghi aggregate tương ứng | Đọc lại aggregate và tính lại lệnh; không giả định mọi SQL tùy biến đều kiểm tra version |
| Spring Data R2DBC | Có hỗ trợ version trong đường cập nhật entity tương ứng; kết quả và lỗi đi qua publisher | Retry phải đăng ký lại một lần thử có đọc mới và ranh giới reactive transaction phù hợp |
| Truy cập key-value như Redis | Không suy ra hỗ trợ optimistic locking của repository chỉ từ annotation dùng chung; có thể cần primitive có điều kiện riêng | Nếu dùng WATCH/MULTI/EXEC hoặc cơ chế tương đương, phải hiểu điều kiện hủy, phạm vi connection và cách chạy lại |

Bảng không có nghĩa mọi phiên bản, mọi API và mọi kiểu thao tác trong một module đều có cùng hành vi. Trước khi chọn chiến lược, xác định đúng đường ghi: repository tiêu chuẩn, template, custom query, bulk operation hay driver trực tiếp.

Một số điểm cần chú ý:

- Với MongoDB, ghi không được xác nhận có thể khiến lỗi optimistic locking không được quan sát đáng tin cậy. Cần write concern có xác nhận và mức bảo đảm phù hợp yêu cầu hệ thống.
- Với MongoDB, tính nguyên tử của một thao tác trên một document không tự bao phủ một tập document hoặc một collection idempotency riêng.
- Với JPA, bulk update hoặc SQL trực tiếp có thể bỏ qua cơ chế version và lifecycle của từng entity nếu câu lệnh không chủ động xử lý chúng.
- Với JDBC/R2DBC, custom statement cũng cần điều kiện version và cách đánh giá số dòng ảnh hưởng nếu thiết kế dựa vào compare-and-set.
- Giá trị version ban đầu và cách nhận biết entity mới phụ thuộc module, kiểu field và mapping. Không gán một giá trị khởi đầu tùy ý để dùng chung cho mọi kho.

Đối tượng trả về từ `save()` cũng cần được sử dụng đúng. Một số đường lưu có thể trả đối tượng khác hoặc đối tượng đã cập nhật metadata; không mặc định bản tham chiếu đầu vào luôn phản ánh version mới nhất.

## 4. Retry đúng phạm vi: thực hiện lại một đơn vị công việc

### 4.1. Vì sao chỉ gọi lại `save()` thường sai?

Mẫu sau giữ nguyên dữ liệu đã đọc cũ:

```text
đọc Stock phiên bản 7
trừ 1 trên đối tượng đó
save thất bại do phiên bản hiện tại là 8
gọi lại save trên chính đối tượng phiên bản 7
```

Việc gọi lại không tạo ra một quyết định nghiệp vụ mới. Nó có thể tiếp tục thất bại hoặc, nếu người viết cố sửa version bằng tay, ghi đè trạng thái mới bằng dữ liệu tính từ snapshot cũ.

Một lần thử đúng thường bao gồm:

1. Bắt đầu transaction mới nếu đơn vị công việc cần transaction.
2. Đọc trạng thái hiện tại từ nguồn có độ nhất quán phù hợp.
3. Kiểm tra lại điều kiện nghiệp vụ.
4. Tính thay đổi từ trạng thái vừa đọc.
5. Ghi và hoàn tất transaction.
6. Khi có xung đột thuộc loại được phép retry, bỏ lần thử đó rồi thực hiện lại từ đầu.

Với đường ghi nguyên tử trên một document, không nhất thiết phải mở transaction nhiều document chỉ để có optimistic locking. Tuy nhiên, vẫn cần đọc lại hoặc tính lại lệnh đúng cách khi điều kiện ghi thất bại.

### 4.2. Vòng retry nên bao ngoài ranh giới transaction

```text
Retry orchestration
    -> lần thử 1: begin -> read -> validate -> write -> commit/rollback
    -> nếu lỗi được phép retry: đợi theo chính sách
    -> lần thử 2: begin -> read mới -> validate lại -> write -> commit/rollback
```

Nếu vòng retry nằm bên trong cùng một transaction đã thất bại, transaction đó có thể đã bị đánh dấu rollback-only hoặc persistence context không còn phù hợp để tiếp tục. Bắt exception rồi tiếp tục ghi không biến nó thành transaction mới.

Nếu dùng annotation retry cùng `@Transactional`, cần hiểu thứ tự interceptor, lời gọi qua proxy và propagation. Hai annotation đặt cạnh nhau không tự chứng minh rằng mỗi lần thử có transaction mới.

### 4.3. Ví dụ imperative với `TransactionTemplate`

Ví dụ sau dành cho một **đơn vị nghiệp vụ độc lập dùng JPA**. Vòng retry ở ngoài `TransactionTemplate.execute()`, nên có thể bắt cả xung đột xuất hiện lúc commit. Mã lược bỏ import; transaction manager được truyền vào phải đúng với repository.

```java
@Service
class StockAdjustmentService {

    private final StockRepository stocks;
    private final TransactionTemplate transactions;

    StockAdjustmentService(
            StockRepository stocks,
            PlatformTransactionManager transactionManager) {
        this.stocks = stocks;
        this.transactions = new TransactionTemplate(transactionManager);
        this.transactions.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
    }

    public int decreaseAvailable(Long stockId, int quantity) {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                Integer remaining = transactions.execute(status -> {
                    Stock stock = stocks.findById(stockId)
                        .orElseThrow(() ->
                            new IllegalArgumentException("Không có tồn kho"));

                    stock.decrease(quantity);
                    Stock saved = stocks.save(stock);
                    return saved.getAvailable();
                });

                return Objects.requireNonNull(remaining);
            } catch (OptimisticLockingFailureException conflict) {
                if (attempt == maxAttempts) {
                    throw conflict;
                }
            }
        }

        throw new IllegalStateException("Không thể đi tới nhánh này");
    }
}
```

`REQUIRES_NEW` ở đây thể hiện mỗi lần thử là một transaction độc lập. Nó cũng có nghĩa transaction ngoài, nếu có, bị tạm ngưng và kết quả lần thử có thể commit trước transaction ngoài. Không dùng mẫu này để vô tình tách việc trừ tồn kho khỏi một giao dịch lớn hơn vốn cần nguyên tử với các thay đổi khác. Khi nghiệp vụ gồm nhiều bước phải cùng thành công, toàn bộ đơn vị đó cần nằm trong phạm vi được thực hiện lại.

Ví dụ giới hạn ba lần thử và chỉ bắt xung đột optimistic locking. Mã chưa thêm backoff, observability hay idempotency cho request bên ngoài. Một lần gọi mới sau khi lần gọi trước đã thành công vẫn trừ thêm tồn kho; đây là điều phải giải quyết riêng ở thiết kế API.

## 5. Phân loại lỗi trước khi quyết định retry

| Tình huống | Có thể retry tự động không? | Điều kiện cần |
| --- | --- | --- |
| Xung đột version, lần thử đã được rollback | Thường có thể với lệnh tính lại được | Đọc lại dữ liệu và kiểm tra lại nghiệp vụ |
| Không đủ tồn kho sau khi đọc lại | Thường không | Trả kết quả nghiệp vụ phù hợp |
| Dữ liệu đầu vào không hợp lệ | Không nên | Sửa yêu cầu trước khi gửi lại |
| Deadlock hoặc lỗi serialization được store xác nhận đã hủy transaction | Có thể theo phân loại lỗi cụ thể | Transaction mới, giới hạn lần thử và xem xét toàn bộ đơn vị công việc |
| Timeout hoặc mất kết nối lúc commit | Không được mặc định chạy lại mù | Kết quả có thể chưa biết; cần tra cứu bằng định danh thao tác hoặc idempotency key |
| Xung đột khi sửa biểu mẫu từ snapshot cũ | Không nên tự retry bằng cách ghi đè | Cho phép người dùng tải lại/hợp nhất theo chính sách |
| Lỗi mapping, sai schema hoặc thiếu quyền | Thường không | Sửa nguyên nhân cấu hình hoặc dữ liệu |

Retry tất cả `Exception` làm tăng tải và che lỗi vĩnh viễn. Lỗi trùng khóa cũng không luôn có cùng ý nghĩa: nó có thể là request lặp theo idempotency key hoặc là vi phạm một khóa nghiệp vụ khác. Cần phân loại đúng ràng buộc và thao tác gây lỗi.

Đặc biệt, **không nhận được phản hồi** khác với **chưa có tác dụng nghiệp vụ**. Khi server đã commit rồi mất kết nối trước khi trả response, client chỉ nhìn thấy lỗi mạng. Retry an toàn cần một cách nhận diện rằng cùng yêu cầu đã được thực hiện.

## 6. Chính sách retry có giới hạn

Một chính sách nên xác định:

- Những loại lỗi cụ thể được retry.
- Số lần thử tối đa, phân biệt rõ lần đầu và số lần retry.
- Tổng thời gian cho phép, deadline và cách dừng khi request bị hủy.
- Backoff cùng jitter để các tiến trình cạnh tranh không đồng loạt thử lại.
- Phạm vi transaction và dữ liệu phải đọc lại.
- Cách quan sát tỷ lệ xung đột, số lần thử và kết quả cuối.

Không nên giữ transaction hoặc connection trong lúc ngủ chờ backoff. Hoàn tất rollback và giải phóng phạm vi lần thử trước rồi mới chờ.

Khi một bản ghi trở thành điểm tranh chấp nóng, tăng số lần retry có thể làm tình hình nặng hơn. Cần xem xét thay đổi cách mô hình hóa aggregate, dùng cập nhật nguyên tử có điều kiện, giảm cạnh tranh hoặc chọn cơ chế khóa/isolation phù hợp với datastore.

Nếu lỗi xảy ra liên tục vì đọc từ một nguồn replica bị trễ, retry ngay trên cùng nguồn cũ có thể tiếp tục tạo xung đột. Chiến lược đọc của lần thử mới phải phù hợp với yêu cầu nhất quán và cơ chế đọc/ghi của store.

## 7. Idempotency: nhận diện cùng một yêu cầu logic

### 7.1. Version không phải idempotency key

Giả sử client gửi lệnh `reserve(42, 1)`. Server xử lý thành công, nhưng response bị mất. Client gửi lại và server đọc được version mới. Lệnh thứ hai có thể hoàn toàn hợp lệ về optimistic locking, rồi trừ thêm một suất.

Version nhận diện trạng thái của dữ liệu. Idempotency key nhận diện một yêu cầu nghiệp vụ. Hai loại định danh này có mục đích khác nhau.

Đối với API giữ suất, client có thể gửi:

```http
POST /reservations
Idempotency-Key: reserve-request-8f2c
Content-Type: application/json

{
  "courseId": 42,
  "quantity": 1
}
```

Giá trị key chỉ là minh họa. Server cần đặt phạm vi key rõ ràng, chẳng hạn theo tenant, loại thao tác và client đã được xác thực. Một key trùng giữa hai tenant không được làm lộ hoặc trả nhầm kết quả của tenant khác.

Nếu cùng key nhưng payload khác, không nên im lặng dùng kết quả cũ. Cần từ chối theo hợp đồng API. Có thể lưu dấu vân tay payload đã chuẩn hóa các trường nghiệp vụ liên quan; hash của chuỗi JSON thô có thể khác chỉ vì thứ tự field hoặc khoảng trắng.

### 7.2. Lưu kết quả và thay đổi nghiệp vụ trong cùng phạm vi nguyên tử

Với cơ sở dữ liệu quan hệ hỗ trợ transaction phù hợp, một thiết kế có thể dùng bản ghi yêu cầu với các thông tin:

| Field | Vai trò |
| --- | --- |
| `tenant_id`, `operation`, `request_key` | Định danh yêu cầu với ràng buộc duy nhất phù hợp |
| `payload_fingerprint` | Phát hiện dùng lại key cho nội dung khác |
| `result_reference` hoặc response cần lưu | Trả lại kết quả của lần xử lý đã thành công |
| Thời điểm tạo/hoàn tất | Theo dõi và quản lý vòng đời |

Luồng khái quát cho một lần thử:

```text
Begin transaction
    -> chiếm quyền xử lý key bằng thao tác được bảo vệ bởi uniqueness
    -> đọc lại dữ liệu nghiệp vụ
    -> kiểm tra điều kiện và thực hiện thay đổi
    -> lưu kết quả gắn với key
    -> lưu outbox nếu có thông báo cần phát lại
Commit
```

Nếu optimistic locking làm transaction rollback, bản ghi key trong cùng transaction cũng rollback. Lần thử mới có thể thực hiện lại toàn bộ công việc. Nếu commit thành công nhưng response bị mất, lần gọi sau tìm thấy kết quả đã lưu và trả lại mà không thực hiện tác dụng nghiệp vụ lần nữa.

Hai request cùng key có thể cạnh tranh tại ràng buộc duy nhất. Nếu một request đang xử lý, request còn lại có thể phải chờ hoặc nhận trạng thái đang xử lý theo hợp đồng. Không được thấy chưa có bản ghi đã commit rồi tự kết luận rằng request đầu chưa bắt đầu.

Sau lỗi trùng khóa, một số hệ quản trị hoặc cơ chế transaction không cho phép tiếp tục dùng transaction đó. Việc đọc kết quả đã tồn tại cần thực hiện sau khi hoàn tất rollback, trong phạm vi phù hợp, thay vì bắt lỗi rồi tiếp tục truy vấn ngay một cách mặc định.

Mô hình trên mô tả lưu kết quả thành công. Chính sách lưu lỗi nghiệp vụ, thời gian giữ key và cách xử lý key đã hết hạn cần được quyết định riêng. Nếu key bị xóa quá sớm, một request gửi lại muộn có thể bị thực hiện lần nữa.

### 7.3. Không giả định log idempotency luôn nguyên tử với dữ liệu

Nếu lưu key vào Redis nhưng giữ suất ở một cơ sở dữ liệu khác, hai thao tác không tự thành một transaction chung. Có thể xảy ra:

- Đã lưu key nhưng chưa thay đổi nghiệp vụ, khiến request bị chặn dù công việc chưa hoàn tất.
- Đã thay đổi nghiệp vụ nhưng chưa lưu kết quả, khiến request lặp tạo thêm tác dụng.

Cần thiết kế trạng thái, lease, phục hồi và đối soát nếu chọn cơ chế phối hợp riêng. Một bản ghi `IN_PROGRESS` được commit trước công việc cũng cần quy tắc xử lý khi tiến trình chết; nó không tương đương với thiết kế mọi thay đổi cùng nằm trong một transaction.

Trong MongoDB, nếu thông tin chống lặp và dữ liệu nghiệp vụ có thể nằm trong một document và được sửa bằng một thao tác nguyên tử phù hợp, thiết kế có thể tận dụng phạm vi đó. Nếu nằm ở nhiều document/collection, phải xét transaction hoặc cơ chế phối hợp thực tế mà deployment hỗ trợ.

## 8. Không đưa tác dụng phụ bên ngoài vào vòng retry một cách vô điều kiện

Ví dụ sai về mặt thiết kế:

```text
lần thử:
    đọc tồn kho
    gửi email xác nhận
    lưu thay đổi
    commit gặp optimistic conflict
retry:
    gửi email lần nữa
```

Transaction của datastore không tự thu hồi email, HTTP request hay message đã gửi. Đổi thứ tự thành gửi ngay sau `save()` cũng chưa đủ, vì commit có thể xảy ra sau đó.

Nếu cần gửi thông báo bền vững, có thể lưu outbox cùng thay đổi nghiệp vụ trong một transaction có khả năng bao phủ cả hai. Worker đọc outbox, gửi thông báo và retry theo cơ chế riêng. Worker có thể gửi lặp khi dừng sau gửi nhưng trước khi đánh dấu đã gửi, nên phía nhận hoặc tác vụ gửi vẫn cần định danh và chính sách chống lặp.

Nếu cổng thanh toán hoặc dịch vụ ngoài hỗ trợ idempotency key, nên truyền một định danh ổn định cho cùng tác vụ logic qua các lần thử. Không sinh key mới ở mỗi lần retry, vì như vậy phía ngoài sẽ hiểu là các tác vụ khác nhau.

Không nên hứa hẹn xử lý đúng một lần trên toàn hệ thống chỉ từ một vòng retry hoặc một unique key cục bộ. Cần mô tả rõ phạm vi bảo đảm: một datastore, một aggregate, một API hay cả chuỗi tích hợp.

## 9. Reactive retry phải bao quanh pipeline của lần thử mới

Với Spring Data R2DBC hoặc đường reactive khác, retry là việc đăng ký lại vào publisher. Publisher được đăng ký lại phải thực sự đọc mới, tính lại và có ranh giới transaction phù hợp.

Ví dụ dạng cấu trúc, lược bỏ phần cài đặt `reserveOnce()`:

```java
return Mono.defer(() ->
        transactionalOperator.transactional(reserveOnce(command))
    )
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(50))
            .filter(OptimisticLockingFailureException.class::isInstance)
    );
```

Ví dụ giả định `reserveOnce(command)` tạo toàn bộ luồng đọc, kiểm tra và ghi; operator dùng reactive transaction manager đúng; không có transaction bao ngoài làm các lần thử vô tình tham gia cùng một phạm vi đã thất bại. Hai lần retry ở đây tương ứng tối đa ba lần đăng ký thực hiện, tính cả lần đầu.

`Mono.defer` giúp xây dựng công việc cho mỗi subscription. Nó không tự làm dữ liệu an toàn nếu `reserveOnce()` vẫn sử dụng một entity đã đọc và sửa từ bên ngoài. Cần tránh tái dùng mutable state hoặc publisher đã cache kết quả đọc cũ giữa các lần thử.

Không gọi `subscribe()` thủ công bên trong `reserveOnce()` để chạy một phần công việc tách rời. Khi đó, transaction, lỗi và retry của pipeline ngoài có thể không còn bao phủ phần đã tách. Các tác dụng phụ bên ngoài trong pipeline cũng cần chính sách idempotency như mô hình imperative.

## 10. Giới hạn của optimistic locking đối với bất biến nghiệp vụ

### 10.1. Version thường bảo vệ đơn vị được ghi

Hai giao dịch cập nhật hai bản ghi khác nhau có thể đều qua kiểm tra version, nhưng cùng vi phạm một điều kiện tổng hợp trên nhiều bản ghi. Ví dụ, mỗi giao dịch đọc tổng số suất của nhiều nhóm rồi tăng một nhóm khác nhau, làm tổng vượt giới hạn chung.

Đây không đơn thuần là mất cập nhật trên cùng một hàng. Có thể cần:

- Mô hình aggregate hoặc bản ghi điều phối chung cho bất biến.
- Ràng buộc tại datastore khi biểu diễn được.
- Cập nhật nguyên tử có điều kiện hoặc khóa phù hợp.
- Isolation mạnh hơn và xử lý lỗi tương ứng nếu store hỗ trợ.

Chọn biện pháp phải dựa trên truy cập thực tế, không chỉ thêm version vào mọi entity.

### 10.2. Uniqueness cần cơ chế riêng

Derived query như `existsByEmail()` rồi `save()` vẫn có khoảng cạnh tranh giữa kiểm tra và ghi. Hai entity mới chưa có cùng version để xung đột với nhau. Ràng buộc hoặc unique index đúng phạm vi vẫn cần thiết nếu yêu cầu là không trùng email.

Query by example, projection và thao tác đọc theo repository không tự biến chuỗi kiểm tra rồi ghi thành một thao tác nguyên tử. Phân trang hoặc sắp xếp cũng không tạo khóa hay snapshot nhất quán cho toàn bộ tập dữ liệu nếu store không cung cấp bảo đảm đó.

### 10.3. Cập nhật trực tiếp phải duy trì cùng quy ước

Một lệnh SQL tùy biến có thể kết hợp điều kiện nghiệp vụ với version:

```sql
UPDATE stock
SET available = available - :quantity,
    version = version + 1
WHERE id = :id
  AND version = :expected_version
  AND available >= :quantity;
```

Nếu không có dòng được cập nhật, nguyên nhân có thể là không tồn tại ID, version đã đổi hoặc không đủ tồn kho. Cần phân loại theo hợp đồng nghiệp vụ; không mặc định mọi kết quả 0 đều là cùng một lỗi để retry.

Đường ghi trực tiếp này cũng cần xử lý audit field và trạng thái entity đã tải nếu có persistence context. Không giả định callback/auditing của repository tự chạy cho SQL tùy biến. Khi nhiều đường ghi cùng tồn tại, tất cả phải tuân thủ quy ước version và các bất biến mà hệ thống dựa vào.

## 11. Phân tích tình huống giữ suất có request lặp

Giả sử khóa học còn một suất và có hai yêu cầu **khác nhau**: `R-A` và `R-B`.

1. Cả hai lần thử đọc cùng version.
2. `R-A` ghi và commit thành công, lưu kết quả idempotency của chính nó.
3. `R-B` gặp xung đột; lần thử đó rollback.
4. `R-B` đọc lại trong lần thử mới và thấy không còn suất, nên trả kết quả hết suất.
5. Client của `R-A` mất response rồi gửi lại cùng key.
6. Server trả kết quả đã lưu của `R-A`, không giữ thêm suất.

Optimistic locking bảo vệ cạnh tranh giữa hai yêu cầu khác nhau. Idempotency bảo vệ khi cùng yêu cầu bị gửi lại. Retry giúp `R-B` đưa ra quyết định từ trạng thái mới, nhưng không bắt buộc biến quyết định đó thành thành công.

Nếu phiên bản ứng dụng cho phép request `R-A` gửi lại với số lượng khác nhưng cùng key, server cần từ chối xung đột nội dung. Nếu thời gian lưu key đã hết, hợp đồng API phải làm rõ giới hạn chống lặp và cách tra cứu giao dịch cũ.

## 12. Câu hỏi kiểm chứng thiết kế

Trước khi đưa phương án vào sử dụng, cần mô tả kết quả mong đợi cho các tình huống:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Hai tiến trình cập nhật cùng version | Chỉ thao tác khớp điều kiện được chấp nhận; xung đột được nhận biết |
| Retry sau xung đột | Dữ liệu được đọc lại, nghiệp vụ được kiểm tra lại, transaction trước đã kết thúc |
| Lỗi chỉ xuất hiện khi commit | Vòng retry bắt được lỗi ở đúng ranh giới |
| Cùng key gửi đồng thời | Một tác dụng nghiệp vụ trong phạm vi bảo đảm; các caller nhận kết quả nhất quán theo hợp đồng |
| Cùng key nhưng payload khác | Bị từ chối, không âm thầm tái sử dụng kết quả |
| Response mất sau commit | Gửi lại cùng key tra được kết quả đã hoàn tất |
| Dừng tiến trình trước/sau gửi thông báo | Có cách phục hồi và xử lý khả năng gửi lặp |
| Custom hoặc bulk update | Quy ước version, audit và ràng buộc không bị bỏ qua ngoài ý muốn |

Thông tin vận hành hữu ích gồm tên thao tác, định danh request an toàn, số lần thử, loại lỗi, thời gian thực hiện và kết quả cuối. Tránh ghi payload nhạy cảm hoặc thông tin xác thực vào log. Tỷ lệ retry tăng cao có thể là dấu hiệu điểm nóng dữ liệu, không chỉ là một lỗi cần tăng giới hạn.

## 13. Bài tập vận dụng

Một API đặt chỗ dùng repository với version và tối đa ba lần thử. Khi gặp bất kỳ exception nào, hệ thống gửi lại toàn bộ công việc, bao gồm gọi cổng thanh toán. Mỗi lần thử sinh một idempotency key mới. Bản ghi chống lặp được lưu ở một store khác sau khi đặt chỗ đã commit.

Hãy chỉ ra:

1. Những loại lỗi nào không nên retry tự động.
2. Vì sao cần bắt được lỗi ở commit và đọc lại dữ liệu trong lần thử mới.
3. Vì sao key mới mỗi lần thử không chống được tác dụng lặp ở dịch vụ ngoài.
4. Khoảng hở giữa commit đặt chỗ và ghi bản ghi chống lặp.
5. Cách chọn phạm vi nguyên tử, kết quả idempotency và cơ chế outbox hoặc đối soát phù hợp với store.

Một phương án hợp lý phải làm rõ cả hai chiều: hai yêu cầu khác nhau tranh cùng tài nguyên và cùng một yêu cầu được gửi lại nhiều lần. Nó cũng phải mô tả cách xử lý khi không biết lần trước đã commit hay chưa.

## 14. Điểm cần nhớ

Optimistic locking phát hiện xung đột trạng thái; retry thực hiện lại một đơn vị công việc có thể phục hồi; idempotency kiểm soát tác dụng của một yêu cầu bị lặp. Lần retry nên dùng trạng thái mới, ranh giới giao dịch mới khi cần và một chính sách giới hạn rõ ràng.

Trong Spring Data, version annotation, thời điểm phát hiện lỗi, transaction và ghi có điều kiện phải được hiểu theo module cùng datastore. Bảo đảm cuối cùng chỉ có giá trị khi mọi đường ghi, tác dụng phụ và cơ chế chống lặp cùng tuân thủ phạm vi mà thiết kế đã xác định.
