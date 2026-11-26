# Chuyển lỗi lưu trữ thành lỗi có ý nghĩa với tầng gọi

Khi ứng dụng đọc hoặc ghi dữ liệu, cơ sở dữ liệu và thư viện persistence có thể phát sinh nhiều loại lỗi: vi phạm ràng buộc, xung đột cập nhật đồng thời, mất kết nối, hết thời gian chờ hoặc lỗi cấu hình. Những lỗi này thường mang chi tiết của SQL, JDBC, JPA hay hệ quản trị cơ sở dữ liệu. Tầng gọi cần hiểu điều gì đã xảy ra với thao tác nghiệp vụ để quyết định phản hồi, thử lại hay yêu cầu người dùng xử lý.

Trong phạm vi SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED, mục tiêu là học tổ chức phần mềm theo kiến trúc phân tầng. Với chương **Tầng truy cập dữ liệu**, bài học này tập trung vào ranh giới chuyển đổi lỗi: tầng truy cập dữ liệu nhận biết lỗi công nghệ lưu trữ, chuyển chúng thành kết quả hoặc ngoại lệ có ý nghĩa đối với hợp đồng mà tầng ứng dụng sử dụng. Tầng ứng dụng và tầng trình bày tiếp tục chịu trách nhiệm diễn giải ý nghĩa của lỗi theo ca sử dụng và giao thức bên ngoài.

## 1. Vì sao cần chuyển đổi lỗi tại ranh giới lưu trữ?

Giả sử một ca sử dụng tạo đơn hàng gọi repository để lưu dữ liệu. Khi cơ sở dữ liệu báo vi phạm unique constraint, driver có thể trả mã lỗi riêng của nhà cung cấp; Hibernate có thể bọc lỗi đó trong exception của mình; Spring có thể dịch tiếp thành một exception thuộc họ DataAccessException. Nếu exception công nghệ này đi thẳng qua mọi tầng, service ứng dụng và controller sẽ phải biết chi tiết về JPA, Hibernate hoặc SQL.

Điều đó tạo ra một số vấn đề:

- Tầng ứng dụng phụ thuộc vào công nghệ lưu trữ và khó thay adapter.
- Tầng trình bày có thể vô tình trả tên bảng, câu SQL, địa chỉ máy chủ hoặc thông báo nội bộ cho client.
- Cùng một tình huống nghiệp vụ có thể được xử lý khác nhau ở các endpoint vì mỗi controller tự bắt exception riêng.
- Chính sách thử lại dễ bị áp dụng sai, chẳng hạn thử lại lỗi dữ liệu không hợp lệ hoặc bỏ qua xung đột cập nhật.

Tầng truy cập dữ liệu nên che giấu chi tiết công nghệ và đưa ra một hợp đồng lỗi ổn định. Hợp đồng đó có thể là kết quả có kiểu, ngoại lệ theo ngữ nghĩa hoặc kết hợp cả hai. Điều quan trọng là tầng gọi biết thao tác thất bại theo cách nào và có thể xử lý ra sao.

~~~mermaid
flowchart LR
    DB["Database / JDBC / JPA"]
    TECH["Lỗi công nghệ<br/>SQLState, vendor code,<br/>Hibernate exception"]
    ADAPTER["Data access adapter<br/>phân loại và chuyển đổi"]
    CONTRACT["Hợp đồng lỗi ổn định<br/>AlreadyExists / Conflict /<br/>Unavailable / StorageFailure"]
    APP["Application use case"]
    API["Presentation / HTTP"]
    DB --> TECH --> ADAPTER --> CONTRACT --> APP --> API
~~~

Mũi tên mô tả hướng thông tin lỗi được truyền lên. Nó không có nghĩa tầng truy cập dữ liệu được quyền quyết định mã HTTP. Adapter biết thao tác lưu trữ thất bại vì lý do gì; tầng ứng dụng biết ý nghĩa của lý do đó đối với ca sử dụng; tầng trình bày biết cách biểu diễn kết quả theo giao thức.

## 2. Phân biệt lỗi lưu trữ với kết quả nghiệp vụ

Không phải mọi tình huống không có dữ liệu hoặc không thể lưu đều là lỗi kỹ thuật.

Ví dụ, phương thức tìm đơn hàng có thể trả về Optional.empty khi mã đơn hàng không tồn tại. Đây là một kết quả bình thường của truy vấn. Tầng ứng dụng quyết định trường hợp đó có nghĩa là “không tìm thấy đơn hàng” trong ca sử dụng hiện tại hay không.

Ngược lại, nếu truy vấn không thể chạy vì mất kết nối cơ sở dữ liệu, đó là lỗi hạ tầng. Nếu cập nhật thất bại vì version của bản ghi đã thay đổi bởi một giao dịch khác, đó là xung đột đồng thời. Nếu một unique constraint cụ thể bị vi phạm, đó có thể là một xung đột có ý nghĩa nghiệp vụ, chẳng hạn mã đơn hàng đã được sử dụng.

| Tình huống | Ý nghĩa ở ranh giới dữ liệu | Tầng gọi có thể làm gì |
|---|---|---|
| Không tìm thấy bản ghi | Trả về kết quả rỗng như Optional.empty | Quyết định có chuyển thành NotFound cho ca sử dụng hay không |
| Vi phạm unique constraint đã biết | Giá trị định danh hoặc khóa nghiệp vụ đã tồn tại | Báo xung đột hoặc yêu cầu chọn giá trị khác |
| Optimistic locking thất bại | Bản ghi đã được thay đổi sau lần đọc trước | Yêu cầu tải lại, hợp nhất hoặc thử lại toàn bộ thao tác nếu phù hợp |
| Kết nối hoặc dịch vụ lưu trữ tạm thời không khả dụng | Không thể hoàn thành thao tác do tài nguyên lưu trữ | Có thể thử lại có giới hạn nếu thao tác an toàn |
| Lỗi mapping, schema hoặc câu lệnh không mong đợi | Adapter hoặc cấu hình lưu trữ có vấn đề | Báo lỗi hệ thống, ghi log và điều tra |
| Dữ liệu đầu vào vi phạm quy tắc nghiệp vụ trước khi lưu | Yêu cầu không hợp lệ | Trả lỗi nghiệp vụ; không cần giả vờ đây là lỗi cơ sở dữ liệu |

Một khóa ngoại bị vi phạm không tự động có nghĩa là “khách hàng không tồn tại”. Nó có thể xuất hiện do dữ liệu bị xóa giữa lúc kiểm tra và lúc ghi, do mapping sai hoặc do lỗi lập trình. Chỉ chuyển thành lỗi nghiệp vụ cụ thể khi adapter có đủ căn cứ nhận biết constraint và hợp đồng của ca sử dụng xác định ý nghĩa đó.

## 3. Thiết kế hợp đồng lỗi mà tầng ứng dụng có thể hiểu

Hợp đồng của repository nên mô tả khả năng lưu trữ ở mức nghiệp vụ mà tầng ứng dụng cần, không đưa kiểu exception của nhà cung cấp cơ sở dữ liệu vào chữ ký. Ví dụ:

~~~java
public interface OrderRepository {
    Optional<Order> findById(UUID orderId);

    void save(Order order);
}
~~~

Nếu thao tác thất bại, adapter có thể ném các ngoại lệ theo ngữ nghĩa. Các ngoại lệ này thuộc lớp hợp đồng mà tầng ứng dụng biết:

~~~java
public class OrderAlreadyExistsException extends RuntimeException {
    public OrderAlreadyExistsException(UUID orderId, Throwable cause) {
        super("Order already exists: " + orderId, cause);
    }
}

public class OrderWriteConflictException extends RuntimeException {
    public OrderWriteConflictException(UUID orderId, Throwable cause) {
        super("Order was changed concurrently: " + orderId, cause);
    }
}

public class OrderStorageUnavailableException extends RuntimeException {
    public OrderStorageUnavailableException(Throwable cause) {
        super("Order storage is temporarily unavailable", cause);
    }
}

public class OrderStorageFailureException extends RuntimeException {
    public OrderStorageFailureException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Các lớp ngoại lệ trong ví dụ có thể được đặt trong package hợp đồng ứng dụng hoặc package dùng chung được quản lý rõ ràng. Tên và số lượng ngoại lệ cần phản ánh những trường hợp tầng gọi thực sự có thể xử lý. Không nên tạo hàng chục lớp ngoại lệ chỉ để đổi tên từng mã lỗi SQL.

Khi chuyển đổi, hãy giữ exception gốc làm cause. Cause giúp ghi log và điều tra nguyên nhân kỹ thuật mà không bắt tầng gọi phải phụ thuộc vào kiểu cụ thể đó. Thông điệp của ngoại lệ mới nên mô tả tình huống ở mức hợp đồng, không nhúng thông tin nhạy cảm như mật khẩu kết nối, câu SQL hoặc hostname.

Một số thao tác có thể dùng kiểu kết quả thay cho exception. Ví dụ, tìm theo ID có thể trả Optional; một lệnh có khả năng bị từ chối theo quy tắc thường xuyên có thể trả một kiểu kết quả gồm Success hoặc Rejected. Lỗi hạ tầng bất ngờ thường vẫn phù hợp với exception. Hãy chọn cách biểu diễn dựa trên việc tình huống đó là kết quả dự kiến của ca sử dụng hay là sự cố khiến thao tác không thể hoàn tất.

## 4. Nhận biết và phân loại exception từ Spring/JPA

Trong ứng dụng Java dùng Spring, các tầng persistence có thể phát sinh exception từ JDBC, JPA provider hoặc Hibernate. Spring cung cấp họ DataAccessException để chuẩn hóa nhiều lỗi truy cập dữ liệu thành các loại runtime exception độc lập tương đối với nhà cung cấp.

Một số loại thường gặp:

- **DataIntegrityViolationException:** thao tác vi phạm ràng buộc dữ liệu, chẳng hạn unique, not-null hoặc foreign key. Kiểu này chưa đủ để kết luận chính xác đó là lỗi trùng mã.
- **DuplicateKeyException:** biểu thị lỗi khóa bị trùng trong các adapter có thể nhận diện tình huống đó.
- **OptimisticLockingFailureException:** cập nhật hoặc xóa thất bại vì dữ liệu đã thay đổi theo cơ chế khóa lạc quan.
- **TransientDataAccessException:** lỗi được phân loại là có tính tạm thời; một số trường hợp có thể thử lại.
- **DataAccessResourceFailureException:** tài nguyên truy cập dữ liệu gặp lỗi, chẳng hạn kết nối hoặc tài nguyên lưu trữ không sẵn sàng.
- **DataAccessException:** lớp cơ sở cho nhiều lỗi truy cập dữ liệu của Spring; nếu chỉ biết đến loại tổng quát này, không nên tự suy diễn nguyên nhân nghiệp vụ.

Với các bean repository được cấu hình exception translation, Spring có thể chuyển exception của persistence provider thành exception thuộc họ DataAccessException. Spring Data cũng sử dụng các kiểu exception đã được chuẩn hóa cho nhiều thao tác repository. Cơ chế cụ thể phụ thuộc cách cấu hình ứng dụng và loại API persistence đang dùng.

Không nên bắt mọi RuntimeException rồi chuyển thành OrderStorageUnavailableException. NullPointerException, lỗi mapping trong mã adapter hoặc lỗi lập trình không phải bằng chứng rằng cơ sở dữ liệu tạm thời ngừng hoạt động. Chỉ phân loại các loại lỗi mà adapter nhận diện được; các lỗi không xác định phải giữ nguyên ngữ cảnh và đi qua xử lý lỗi hệ thống phù hợp.

## 5. Ví dụ chuyển đổi lỗi trong JPA adapter

Giả sử tầng ứng dụng gọi OrderRepository, còn adapter dùng Spring Data JPA để lưu entity. Adapter có thể gọi saveAndFlush khi cần phát hiện sớm một số lỗi constraint trong phạm vi phương thức:

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;
    private final OrderConstraintClassifier classifier;

    public JpaOrderRepository(
            SpringDataOrderJpaRepository jpa,
            OrderConstraintClassifier classifier) {
        this.jpa = jpa;
        this.classifier = classifier;
    }

    @Override
    public void save(Order order) {
        try {
            jpa.saveAndFlush(OrderEntity.from(order));
        } catch (OptimisticLockingFailureException ex) {
            throw new OrderWriteConflictException(order.id(), ex);
        } catch (DataIntegrityViolationException ex) {
            if (classifier.isOrderIdUniqueViolation(ex)) {
                throw new OrderAlreadyExistsException(order.id(), ex);
            }
            throw new OrderStorageFailureException(
                "Could not persist order", ex
            );
        } catch (TransientDataAccessException
                 | DataAccessResourceFailureException ex) {
            throw new OrderStorageUnavailableException(ex);
        } catch (DataAccessException ex) {
            throw new OrderStorageFailureException(
                "Could not persist order", ex
            );
        }
    }
}
~~~

Đây là ví dụ minh họa; cần import các exception Spring tương ứng và triển khai OrderConstraintClassifier theo công nghệ lưu trữ thực tế. Classifier phải nhận diện constraint đã biết bằng metadata đáng tin cậy như tên constraint, mã lỗi hoặc SQLState phù hợp với driver. Không nên dò chuỗi thông báo lỗi tự do vì thông điệp có thể thay đổi theo phiên bản, ngôn ngữ hoặc nhà cung cấp.

Điểm quan trọng trong đoạn mã:

1. Optimistic locking được bắt trước nhóm lỗi tạm thời tổng quát để chuyển thành xung đột cập nhật có ý nghĩa.
2. DataIntegrityViolationException chỉ được chuyển thành OrderAlreadyExistsException khi classifier xác nhận đúng unique constraint liên quan đến mã đơn hàng.
3. Các lỗi integrity khác không bị gán nhầm thành trùng mã. Chúng được giữ ở nhóm lỗi lưu trữ tổng quát hoặc có thể được phân loại riêng nếu hợp đồng thật sự cần.
4. Lỗi tài nguyên và lỗi tạm thời được chuyển thành lỗi lưu trữ không khả dụng; tầng gọi có thể cân nhắc retry theo chính sách.
5. Lỗi DataAccessException chưa nhận diện được giữ nguyên cause và được biểu diễn là lỗi lưu trữ tổng quát.

Không phải dự án nào cũng cần classifier tùy chỉnh. Nếu Spring Data hoặc driver đã cung cấp một exception đủ cụ thể và ổn định cho tình huống cần xử lý, có thể dùng trực tiếp ở adapter rồi chuyển sang ngoại lệ hợp đồng. Nếu adapter không thể phân biệt an toàn, hãy dùng nhóm lỗi tổng quát thay vì đoán.

## 6. Lưu ý về lỗi xuất hiện khi flush hoặc commit

Một điểm dễ bỏ sót là thao tác save không phải lúc nào cũng thực hiện SQL ngay. Với JPA, entity có thể chỉ được đưa vào persistence context; câu lệnh SQL được gửi khi flush. Một số constraint chỉ được kiểm tra khi flush hoặc khi transaction commit.

Gọi saveAndFlush có thể buộc persistence context đồng bộ sớm và làm cho nhiều lỗi xuất hiện ngay trong phương thức repository. Tuy vậy, flush **không đồng nghĩa với commit**. Transaction vẫn có thể thất bại sau đó do constraint trì hoãn, lỗi kết nối, deadlock hoặc vấn đề từ transaction manager.

Nếu transaction được đặt bằng @Transactional trên application service, Spring thường gọi phương thức qua proxy. Phương thức service có thể đã chạy xong phần thân; sau đó proxy mới commit transaction. Vì thế, try/catch bên trong phần thân phương thức không bắt được mọi lỗi chỉ xuất hiện tại thời điểm commit.

Có hai cách tổ chức thường gặp:

- Giữ transaction khai báo ở application service và có một ranh giới bên ngoài proxy để chuyển các lỗi commit đã nhận diện. Lớp xử lý HTTP có thể ánh xạ lỗi hợp đồng đã chuyển đổi, đồng thời có fallback an toàn cho lỗi transaction chưa phân loại.
- Dùng một transaction boundary rõ ràng, chẳng hạn TransactionTemplate, rồi đặt việc chuyển đổi lỗi ở bên ngoài lời gọi execute. Khối try/catch bao quanh execute có thể nhìn thấy cả lỗi trong callback lẫn lỗi phát sinh khi commit do template thực hiện.

Không nên thêm @Transactional ở nhiều lớp một cách tùy tiện. Hãy xác định ai sở hữu transaction, propagation nào được dùng và exception được chuyển đổi ở ranh giới nào. Nếu commit thất bại sau khi phương thức repository đã trả về, adapter không thể tự bắt lỗi đó bằng catch quanh riêng lệnh save.

## 7. Tầng ứng dụng diễn giải lỗi theo ca sử dụng

Ngoại lệ do adapter tạo ra là hợp đồng mà tầng ứng dụng có thể sử dụng. Tầng ứng dụng quyết định ý nghĩa của chúng đối với hành động đang thực hiện.

Ví dụ, nếu tạo đơn hàng với một mã do hệ thống cấp và mã đó đã tồn tại, tầng ứng dụng có thể chuyển tình huống thành kết quả từ chối vì xung đột. Nếu lỗi lưu trữ tạm thời xảy ra, tầng ứng dụng có thể để exception truyền lên để một chính sách retry ở ranh giới thích hợp xử lý. Nếu một truy vấn trả Optional.empty, tầng ứng dụng có thể ném OrderNotFoundException vì ca sử dụng yêu cầu đơn hàng phải tồn tại.

Không nên biến một lỗi kỹ thuật thành lỗi nghiệp vụ chỉ để làm response dễ đọc. Ví dụ, database không khả dụng không có nghĩa là đơn hàng không tồn tại; lỗi foreign key không luôn có nghĩa là khách hàng đã bị xóa; timeout không chứng minh thao tác ghi chưa xảy ra.

Một thao tác có thể thất bại ở phía client nhưng đã commit thành công ở phía server nếu kết nối bị mất ngay sau commit. Đây là trạng thái kết quả không chắc chắn. Với lệnh tạo đơn hàng hoặc thanh toán, idempotency key hoặc một mã yêu cầu duy nhất được lưu cùng kết quả có thể giúp client gửi lại mà không tạo tác động trùng lặp.

## 8. Ánh xạ lỗi hợp đồng sang HTTP

Tầng truy cập dữ liệu không nên phụ thuộc vào HttpStatus. Sau khi lỗi đã mang ý nghĩa của ca sử dụng, tầng trình bày có thể chuyển nó thành response theo hợp đồng API:

| Lỗi mà tầng ứng dụng hiểu | Phản hồi HTTP thường phù hợp | Ý nghĩa với client |
|---|---|---|
| OrderAlreadyExistsException | 409 Conflict | Mã đơn hàng đã được sử dụng; cần chọn mã khác hoặc tra cứu đơn đã tạo |
| OrderWriteConflictException | 409 Conflict; đôi khi 412 Precondition Failed nếu dùng điều kiện HTTP | Dữ liệu đã thay đổi; cần tải lại trước khi cập nhật |
| OrderStorageUnavailableException | 503 Service Unavailable | Dịch vụ tạm thời không thể hoàn tất thao tác; có thể thử lại theo hướng dẫn |
| OrderStorageFailureException | 500 Internal Server Error | Có lỗi máy chủ; client không được nhận chi tiết kỹ thuật |
| OrderNotFoundException từ tầng ứng dụng | 404 Not Found | Tài nguyên được yêu cầu không tồn tại |

Mã HTTP cụ thể phụ thuộc hợp đồng API. Ví dụ, một xung đột cập nhật có thể dùng 412 nếu client gửi If-Match và điều kiện không còn đúng. Một lỗi nghiệp vụ khác có thể dùng 422 nếu API đã chọn cách biểu diễn đó. Điều quan trọng là cùng một loại tình huống phải có cách phản hồi nhất quán.

Ví dụ với Spring MVC:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderAlreadyExistsException.class)
    ResponseEntity<ApiError> handleDuplicate(OrderAlreadyExistsException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError("ORDER_ALREADY_EXISTS",
                               "Mã đơn hàng đã tồn tại"));
    }

    @ExceptionHandler(OrderWriteConflictException.class)
    ResponseEntity<ApiError> handleConflict(OrderWriteConflictException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError("ORDER_WRITE_CONFLICT",
                               "Đơn hàng đã thay đổi; hãy tải lại dữ liệu"));
    }

    @ExceptionHandler(OrderStorageUnavailableException.class)
    ResponseEntity<ApiError> handleUnavailable(
            OrderStorageUnavailableException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError("STORAGE_UNAVAILABLE",
                               "Dịch vụ tạm thời không khả dụng"));
    }
}
~~~

Ví dụ chỉ trình bày một số trường hợp. Trong hệ thống thật, cần có handler cho lỗi lưu trữ tổng quát và lỗi không mong đợi, đồng thời ghi log phía máy chủ. Response không nên chứa SQL, tên bảng, tên máy chủ, stack trace, thông tin đăng nhập hoặc thông điệp thô từ driver.

## 9. Retry: chỉ thử lại khi hiểu rõ tính chất lỗi

Một số lỗi có thể tự hết sau một khoảng thời gian, chẳng hạn database tạm thời mất kết nối hoặc giao dịch bị deadlock. Tuy nhiên, retry không phải phản xạ mặc định cho mọi exception.

| Nhóm lỗi | Có nên retry tự động? | Lưu ý |
|---|---|---|
| Validation hoặc vi phạm quy tắc dữ liệu cố định | Không | Dữ liệu đầu vào phải được sửa |
| Unique constraint đã xác nhận | Không | Thử lại cùng dữ liệu thường tiếp tục thất bại |
| Optimistic locking conflict | Có điều kiện | Thường phải đọc lại, hợp nhất và chạy lại toàn bộ thao tác nghiệp vụ |
| Timeout hoặc lỗi tài nguyên tạm thời | Có thể | Dùng số lần giới hạn, backoff và jitter |
| Lỗi mapping/schema hoặc lỗi không xác định | Không tự động | Cần điều tra; retry có thể làm tăng tải mà không giải quyết nguyên nhân |

Retry nên được đặt ở tầng có đủ ngữ cảnh để biết toàn bộ thao tác có thể thực hiện lại an toàn hay không. Với transaction, thường phải retry toàn bộ đơn vị công việc trong transaction mới, không chỉ gọi lại một câu lệnh save sau khi transaction cũ đã rollback.

Một chính sách retry nên có số lần tối đa, khoảng chờ tăng dần, jitter và giới hạn tổng thời gian. Tránh retry đồng thời ở nhiều tầng vì số lần thử có thể nhân lên ngoài dự kiến. Với thao tác không idempotent, cần idempotency key hoặc cơ chế chống xử lý trùng trước khi tự động thử lại.

Đặc biệt, khi kết nối bị ngắt trong lúc commit, ứng dụng có thể không biết transaction đã được commit hay chưa. Không nên kết luận rằng thao tác chắc chắn thất bại rồi tạo một bản ghi mới. Hãy thiết kế mã yêu cầu duy nhất, tra cứu trạng thái hoặc cơ chế khử trùng lặp phù hợp với nghiệp vụ.

## 10. Kiểm thử việc chuyển đổi lỗi

Kiểm thử cần xác nhận cả hai điều: adapter phân loại lỗi đúng và tầng gọi nhận được hợp đồng ổn định.

| Loại kiểm thử | Cách thực hiện | Điều cần xác nhận |
|---|---|---|
| Unit test cho classifier | Cung cấp các exception mẫu với constraint hoặc mã lỗi đã biết | Chỉ constraint được hỗ trợ mới được phân loại thành lỗi nghiệp vụ tương ứng |
| Unit test cho adapter | Mock Spring Data repository để ném các exception cụ thể | Adapter chuyển đúng sang OrderAlreadyExists, OrderWriteConflict, OrderStorageUnavailable hoặc OrderStorageFailure |
| Integration test persistence | Dùng database kiểm thử để vi phạm unique/FK hoặc optimistic locking | Exception thực tế được Spring/JPA phát sinh và adapter xử lý đúng |
| Test tầng ứng dụng | Dùng repository giả lập ném ngoại lệ hợp đồng | Ca sử dụng phản ứng đúng và không phụ thuộc exception của Hibernate |
| MVC test | Gọi endpoint khi use case ném từng ngoại lệ hợp đồng | HTTP status, error code và nội dung response nhất quán |
| Transaction test | Tạo lỗi chỉ xuất hiện khi flush hoặc commit | Ranh giới xử lý nhận được lỗi đúng thời điểm và transaction được rollback theo mong đợi |

Mock một DataAccessException trong unit test không chứng minh database thật sẽ phát sinh đúng loại exception đó. Với các quy tắc phụ thuộc constraint, SQLState, lock hoặc hành vi commit, cần ít nhất một integration test dùng database tương thích với môi trường triển khai.

Kiểm thử cũng nên xác nhận rằng cause gốc vẫn được giữ để điều tra và response bên ngoài không để lộ thông tin nội bộ. Không nên kiểm tra nội dung thông điệp vendor cụ thể như một hợp đồng công khai của ứng dụng.

## 11. Checklist khi thêm một phép chuyển đổi lỗi

Trước khi thêm catch hoặc tạo exception mới, hãy trả lời:

- Lỗi này là kết quả nghiệp vụ dự kiến hay sự cố của công nghệ lưu trữ?
- Adapter có đủ bằng chứng để phân loại chính xác không, hay đang suy đoán từ thông điệp lỗi?
- Tên lỗi mới có diễn đạt điều tầng gọi cần biết và có giữ cause gốc không?
- Lỗi có thể xuất hiện trong save, flush hay chỉ khi commit?
- Tầng nào sở hữu retry và thao tác có idempotent không?
- Tầng trình bày đã ánh xạ lỗi theo hợp đồng API mà không tiết lộ chi tiết lưu trữ chưa?
- Có kiểm thử xác nhận exception thực tế từ provider/database và hành vi rollback không?

Một thiết kế tốt giữ cho tầng truy cập dữ liệu chịu trách nhiệm hiểu công nghệ lưu trữ, tầng ứng dụng chịu trách nhiệm hiểu ca sử dụng, và tầng trình bày chịu trách nhiệm biểu diễn kết quả ra bên ngoài. Khi ranh giới này rõ ràng, có thể thay đổi JPA, JDBC hoặc hệ quản trị cơ sở dữ liệu mà không buộc toàn bộ ứng dụng phải học lại cách xử lý từng mã lỗi của nhà cung cấp.
