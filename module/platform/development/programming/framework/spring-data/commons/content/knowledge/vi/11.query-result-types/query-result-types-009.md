# Xây hợp đồng kết quả rõ ràng cho trường hợp rỗng hoặc lỗi

Một query không tìm thấy bản ghi và một query không thực hiện được là hai tình huống cần được biểu đạt riêng. Nếu cả hai đều bị chuyển thành danh sách rỗng hoặc `Optional.empty()`, phía gọi không còn biết dữ liệu thật sự vắng mặt hay hệ thống chưa đọc được dữ liệu.

Trong chương **Kiểu kết quả truy vấn** của Spring Data Commons (`SPRING_DATA_COMMONS`), bài này xây hợp đồng từ chữ ký repository đến cách service xử lý kết quả. Commons cung cấp các abstraction chung; kiểu trả về, mapping và exception cụ thể vẫn cần phù hợp với module kho dữ liệu đang dùng.

## 1. Bắt đầu bằng các trạng thái cần phân biệt

Với một yêu cầu tìm ticket, ít nhất có những tình huống sau:

| Tình huống | Bản chất | Ví dụ biểu đạt |
| --- | --- | --- |
| Truy vấn thành công, có dữ liệu đúng số lượng | Kết quả bình thường. | `Optional.of(ticket)`, List có phần tử. |
| Truy vấn thành công, không có dữ liệu khớp | Kết quả vắng mặt. | `Optional.empty()`, List rỗng. |
| Đầu vào không đáp ứng hợp đồng | Yêu cầu không hợp lệ. | Lỗi validation hoặc exception được quy định. |
| Có nhiều kết quả trong khi hợp đồng chỉ cho tối đa một | Sai kỳ vọng về số lượng. | Lỗi cardinality. |
| Không hoàn tất được thao tác đọc | Lỗi truy cập hoặc thực thi. | Exception hoặc tín hiệu lỗi tương ứng. |

Một kết quả rỗng chỉ đáng tin khi thao tác tương ứng đã hoàn tất thành công theo hợp đồng của nó.

Trong bài, **cardinality** là số lượng kết quả mà method cho phép: không hoặc một, đúng một theo yêu cầu nghiệp vụ, hoặc nhiều phần tử.

## 2. Chọn chữ ký theo ý nghĩa số lượng

Giả sử `Ticket` có:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh kỹ thuật. |
| `tenantId` | `String` | Tổ chức sở hữu ticket. |
| `externalRef` | `String` | Mã tham chiếu nghiệp vụ trong tenant. |
| `status` | `TicketStatus` | Ví dụ `OPEN`, `CLOSED`. |

Repository minh họa, với domain mapping và store đã được cấu hình:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;

public interface TicketRepository extends CrudRepository<Ticket, Long> {

    Optional<Ticket> findByTenantIdAndExternalRef(
        String tenantId,
        String externalRef
    );

    List<Ticket> findByTenantIdAndStatus(
        String tenantId,
        TicketStatus status
    );

    Page<Ticket> findByTenantIdAndStatus(
        String tenantId,
        TicketStatus status,
        Pageable pageable
    );
}
```

Hợp đồng của ba method khác nhau:

- Tìm theo tenant và mã tham chiếu kỳ vọng tối đa một ticket.
- Tìm theo tenant và trạng thái cho phép nhiều ticket; không có ticket là kết quả bình thường.
- Dạng phân trang cung cấp nội dung của một khoảng cùng metadata của `Page`.

`Optional<T>` biểu đạt tối đa một kết quả. Nếu không có thì trả empty; nếu có nhiều hơn một, query method có thể báo `IncorrectResultSizeDataAccessException` theo hợp đồng chung của Spring Data. Xem [Repository query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html).

Khai báo `Optional` không tạo ràng buộc unique trong database. Nếu mã tham chiếu phải duy nhất trong mỗi tenant, cần thiết kế ràng buộc phù hợp ở store khi được hỗ trợ.

## 3. Optional.empty chỉ biểu đạt sự vắng mặt

Lời gọi:

```java
Optional<Ticket> result =
    repository.findByTenantIdAndExternalRef(
        "ACME",
        "SUP-101"
    );
```

có ba diễn biến cần đọc riêng:

```text
0 ticket khớp  -> Optional.empty()
1 ticket khớp  -> Optional chứa ticket
nhiều hơn 1    -> không đáp ứng hợp đồng tối đa một
```

Ngoài ra, việc thực thi có thể ném lỗi trước khi tạo được một Optional hợp lệ.

`Optional` không phải hộp chứa cả thành công lẫn exception. Khi kho dữ liệu không truy cập được, không được suy rằng repository sẽ tự trả `Optional.empty()`.

### Không dùng get khi chưa xác định chính sách vắng mặt

```java
// Không thể hiện chính sách nghiệp vụ khi không có ticket.
Ticket ticket = result.get();
```

Nếu không có dữ liệu, cách gọi này phát sinh lỗi từ Optional thay vì một kết quả nghiệp vụ có ý nghĩa.

Tùy use case, chọn một trong hai hợp đồng rõ ràng:

```java
// Vắng mặt là một kết quả bình thường của thao tác tra cứu.
Optional<Ticket> lookupTicket(String tenantId, String externalRef);
```

hoặc:

```java
// Use case yêu cầu ticket phải tồn tại.
Ticket requireTicket(String tenantId, String externalRef);
```

Ở dạng thứ hai, service có thể dùng `orElseThrow` để tạo exception nghiệp vụ. Không cần ép repository luôn coi vắng mặt là lỗi trong mọi use case.

### Không dùng First để che dữ liệu trùng ngoài ý muốn

Đổi một query kỳ vọng duy nhất thành `findFirst...` có thể khiến hệ thống chọn một bản ghi trong nhiều bản ghi khớp, nhưng không giải quyết được việc dữ liệu vi phạm yêu cầu duy nhất.

`First` hoặc `Top` phù hợp khi nghiệp vụ thực sự yêu cầu chọn một phần tử theo tiêu chí rõ ràng, chẳng hạn ticket mới nhất. Đó là một hợp đồng khác với “mã này phải xác định duy nhất một ticket”.

## 4. Collection rỗng là kết quả bình thường của truy vấn nhiều phần tử

Ví dụ:

```java
List<Ticket> openTickets =
    repository.findByTenantIdAndStatus(
        "ACME",
        TicketStatus.OPEN
    );
```

Nếu không có ticket OPEN, danh sách rỗng mô tả đúng kết quả truy vấn. Không cần trả null hoặc thêm một đối tượng ticket giả.

Spring Data quy định các query method trả collection, các dạng collection tương ứng, wrapper và stream dùng biểu diễn rỗng phù hợp thay vì null. Xem [Null Handling of Repository Methods](https://docs.spring.io/spring-data/commons/reference/repositories/null-handling.html).

Với một kết quả List chuẩn từ hạ tầng repository:

```java
if (openTickets.isEmpty()) {
    // Không có ticket khớp truy vấn đã thực hiện thành công.
}
```

Cần giữ hợp đồng tương tự nếu tự viết custom fragment hoặc adapter. Một phần triển khai tùy chỉnh trả null có thể phá vỡ kỳ vọng mà phía gọi đang dựa vào.

`Optional<List<Ticket>>` thường tạo thêm tầng vắng mặt khó giải thích cho một tìm kiếm nhiều phần tử. Nếu List rỗng đã biểu đạt “không có phần tử”, đừng thêm Optional chỉ theo thói quen; cũng không mặc định mọi tổ hợp wrapper lồng nhau đều được module hỗ trợ.

### Kết quả tìm nhiều ID không nhất thiết đủ mọi ID yêu cầu

Hợp đồng `CrudRepository.findAllById(...)` cho phép bỏ qua các ID không tìm thấy và không bảo đảm thứ tự kết quả giống thứ tự đầu vào. Xem [API CrudRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).

Ví dụ:

```text
Yêu cầu ID:       101, 102, 999
Kết quả có thể:   ticket 102, ticket 101
ID không có:     999
```

Nếu use case yêu cầu mọi ID đều phải tồn tại, service cần so sánh tập ID yêu cầu với tập ID nhận được và quy định cách báo thiếu.

Không ghép vị trí thứ nhất của kết quả với ID thứ nhất của đầu vào. Nếu đầu vào có ID lặp, cũng cần xác định việc so sánh dựa trên tập ID duy nhất hay trên một hợp đồng khác.

## 5. Nullability và đầu vào là hai phần của cùng hợp đồng

Một query method trả trực tiếp `Ticket` có thể biểu đạt vắng mặt bằng null, hoặc bị ràng buộc không được trả null theo cấu hình nullability.

Ví dụ chữ ký riêng lẻ:

```java
Ticket findByTenantIdAndExternalRef(
    String tenantId,
    String externalRef
);
```

chưa cho người đọc đủ thông tin để bỏ qua quy ước nullability của package hoặc method.

Nếu non-null contract được bật và một kết quả vi phạm hợp đồng, hạ tầng có thể ném exception thay vì trả null. Cơ chế annotation phụ thuộc phiên bản Spring Data/Spring Framework; cần đọc cấu hình mà dự án sử dụng.

Không suy rằng chỉ đổi tiền tố `find` thành `get` tự động tạo hợp đồng “bắt buộc tồn tại”. Các method cơ sở đặc thù của module cũng có thể mang ngữ nghĩa riêng và cần được đọc theo tài liệu của chúng.

### Đầu vào null không đồng nghĩa không tìm thấy

`CrudRepository.findById(null)` vi phạm hợp đồng ID không null và ném `IllegalArgumentException`, thay vì trả `Optional.empty()`.

Tương tự, nếu service yêu cầu mã tham chiếu không được trống, mã trống là đầu vào không hợp lệ. Nó không nên được biến thành kết luận “không có ticket”.

Phân biệt:

```text
Mã hợp lệ, không khớp dữ liệu -> không tìm thấy.
Mã không đáp ứng hợp đồng    -> lỗi đầu vào.
Không đọc được kho dữ liệu   -> lỗi thao tác đọc.
```

Nếu một bộ lọc cho phép null để biểu đạt điều kiện đặc biệt, ý nghĩa đó phải được quy định riêng theo truy vấn và module; không tự mặc định null luôn có nghĩa “bỏ qua điều kiện”.

## 6. Page rỗng chưa chắc toàn bộ tập tìm kiếm rỗng

Với phân trang, cần tách hai số:

- Số phần tử trong trang hiện tại.
- Tổng số phần tử khớp điều kiện mà Page báo cáo.

Giả sử có 42 ticket khớp và kích thước trang là 20. Chỉ số trang hợp lệ có nội dung là 0, 1 và 2 trong bộ dữ liệu cố định này.

Nếu yêu cầu trang chỉ số 5, nội dung có thể rỗng dù tổng số vẫn là 42:

```text
content:          []
numberOfElements: 0
totalElements:   42
totalPages:      3
```

Do đó:

```java
page.getContent().isEmpty()
```

không đủ để kết luận không có ticket nào khớp trên toàn bộ tập tìm kiếm.

Với `Slice`, hợp đồng không cung cấp tổng số như Page. Với List có `Pageable`, bạn chỉ nhận nội dung của khoảng mà không có đầy đủ metadata phân trang.

Ứng dụng cần quy định chính sách cho trang vượt phạm vi: trả nội dung rỗng cùng metadata, điều hướng lại hoặc báo yêu cầu ngoài phạm vi theo hợp đồng API. Không tự đổi query thành công thành lỗi database.

Cũng không tạo `Page.empty(pageable)` trong nhánh bắt lỗi truy cập rồi báo rằng truy vấn thành công nhưng không có dữ liệu.

## 7. Service biến sự vắng mặt thành kết quả nghiệp vụ có chủ đích

Repository có thể giữ hợp đồng `Optional<Ticket>`, còn service quyết định use case nào yêu cầu bắt buộc tồn tại.

```java
import java.util.List;

public final class TicketService {

    private final TicketRepository repository;

    public TicketService(TicketRepository repository) {
        this.repository = repository;
    }

    public Ticket requireTicket(
        String tenantId,
        String externalRef
    ) {
        requireText(tenantId, "tenantId");
        requireText(externalRef, "externalRef");

        return repository.findByTenantIdAndExternalRef(
            tenantId,
            externalRef
        ).orElseThrow(() ->
            new TicketNotFoundException(externalRef)
        );
    }

    public List<Ticket> searchByStatus(
        String tenantId,
        TicketStatus status
    ) {
        requireText(tenantId, "tenantId");

        if (status == null) {
            throw new IllegalArgumentException("status is required");
        }

        return repository.findByTenantIdAndStatus(
            tenantId,
            status
        );
    }

    private static void requireText(String value, String name) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(name + " is required");
        }
    }

    public static final class TicketNotFoundException
            extends RuntimeException {

        public TicketNotFoundException(String externalRef) {
            super("Ticket not found: " + externalRef);
        }
    }
}
```

Đây là ví dụ chính sách service, không phải quy tắc validation mặc định của Commons:

- `requireTicket` dùng exception nghiệp vụ khi truy vấn thành công nhưng không có ticket.
- `searchByStatus` cho phép trả List rỗng.
- Đầu vào thiếu bị từ chối trước khi gọi repository.
- Lỗi từ repository không bị đổi thành not-found chỉ vì service dùng Optional.

Nếu repository ném lỗi truy cập hoặc lỗi số lượng kết quả, biểu thức `orElseThrow` không được dùng để chuyển những lỗi đó thành `TicketNotFoundException`. Nó chỉ xử lý một Optional hợp lệ đang empty.

### Tránh kiểm tra exists rồi mới đọc để biểu đạt not-found

Không cần tổ chức mặc định thành:

```text
exists?
  -> nếu có: gọi query lấy dữ liệu
  -> nếu không: báo thiếu
```

Hai lần đọc làm tăng số thao tác và dữ liệu có thể thay đổi giữa chúng. Một query trả Optional rồi áp dụng chính sách vắng mặt thường thể hiện hợp đồng rõ hơn.

Nếu use case cần bảo đảm thêm về đồng thời hoặc transaction, phải thiết kế theo khả năng module; bản thân Optional không cung cấp bảo đảm đó.

## 8. Giữ lỗi truy cập tách khỏi kết quả rỗng

Đoạn sau làm mất thông tin quan trọng:

```java
try {
    return repository.findByTenantIdAndExternalRef(
        tenantId,
        externalRef
    );
} catch (org.springframework.dao.DataAccessException ex) {
    // Sai hợp đồng: mọi lỗi đều bị biểu đạt thành không tìm thấy.
    return Optional.empty();
}
```

Tương tự:

```java
try {
    return repository.findByTenantIdAndStatus(tenantId, status);
} catch (Exception ex) {
    return java.util.Collections.emptyList();
}
```

khiến một lần đọc thất bại có cùng kết quả quan sát được với một tìm kiếm thành công không có phần tử.

Hệ phân cấp `DataAccessException` của Spring cho phép phân loại lỗi truy cập mà không buộc code ứng dụng phụ thuộc trực tiếp vào mọi API persistence cụ thể. Xem [API DataAccessException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html).

Một số hướng phân loại:

| Nhóm tình huống | Hướng xử lý hợp đồng |
| --- | --- |
| Không có kết quả theo hợp đồng tối đa một | Biểu đạt absence bằng Optional hoặc chính sách service. |
| Nhiều kết quả ngoài kỳ vọng | Giữ lỗi cardinality; xem lại dữ liệu, query hoặc ràng buộc. |
| Không truy cập được tài nguyên | Giữ lỗi thất bại thao tác, hoặc dịch sang lỗi ứng dụng riêng. |
| Cách dùng API persistence không hợp lệ | Sửa hợp đồng/cấu hình, không báo không tìm thấy. |
| Lỗi được xác định là tạm thời | Chỉ áp chính sách retry phù hợp với thao tác và nguyên nhân. |

Không phải mọi `DataAccessException` đều có cùng nguyên nhân hoặc đều được sửa bằng retry. Nếu dịch một lỗi hạ tầng sang exception ứng dụng, nên giữ `cause` để có thể chẩn đoán.

Cũng cần xét hợp đồng của method khi diễn giải một `EmptyResultDataAccessException`: nó có thể liên quan đến một kết quả bị yêu cầu non-null. Không coi tên exception như đủ thông tin để chuyển mọi trường hợp trong toàn bộ hệ thống thành “ticket không tồn tại”.

## 9. Nếu cần biểu diễn lỗi thành dữ liệu, phải có trạng thái riêng

Một ứng dụng có thể quy định lỗi ở tầng ứng dụng dưới dạng exception, hoặc dùng một kiểu kết quả tường minh. Điều quan trọng là các trạng thái không bị nhập nhằng.

Ví dụ mô hình khái niệm cho tra cứu một ticket:

```text
Found(ticket)
Missing
Failed(errorCode)
```

Các bất biến nên được giữ:

- `Found` luôn có ticket hợp lệ.
- `Missing` biểu đạt một thao tác tra cứu thành công nhưng không có ticket.
- `Failed` có mã lỗi ổn định và không giả nhận rằng dữ liệu vắng mặt.
- Đầu vào không hợp lệ có chính sách riêng, thay vì lẫn với `Missing`.

Đây là thiết kế ở tầng ứng dụng, không có nghĩa Spring Data tự hỗ trợ mọi wrapper tùy chỉnh như kiểu trả về query method.

Với API tìm kiếm nhiều phần tử, có thể biểu đạt một phản hồi thành công:

```json
{
  "items": []
}
```

Còn một phản hồi lỗi ứng dụng có cấu trúc riêng, ví dụ:

```json
{
  "code": "TICKET_QUERY_UNAVAILABLE",
  "message": "Chưa thể truy vấn ticket.",
  "requestId": "req-42"
}
```

Đây là schema minh họa. Nếu dùng HTTP, status và schema phản hồi phải được quyết định tại tầng API theo hợp đồng của ứng dụng; kiểu repository không tự quyết định chúng.

Không đưa stack trace hoặc chuỗi lỗi của driver thành thông điệp nghiệp vụ cho phía gọi. Phía vận hành vẫn cần nguyên nhân và ngữ cảnh để phân biệt số lần tìm kiếm rỗng với số lần truy cập thất bại.

Nếu hệ thống cố ý dùng dữ liệu cache hoặc kết quả dự phòng khi nguồn chính lỗi, cần biểu đạt chính sách và độ mới phù hợp; không mặc nhiên gắn nhãn “không có dữ liệu” cho một nguồn chưa đọc được.

## 10. Với kết quả đọc dần, lỗi có thể xuất hiện sau khi đã nhận một phần

Đối với List đã materialize, phía gọi thường nhận toàn bộ collection sau khi thao tác hoàn tất. Với Stream hoặc kết quả reactive được module hỗ trợ, lỗi có thể xuất hiện trong giai đoạn tiêu thụ.

Ví dụ:

```java
import java.util.stream.Stream;

try (Stream<Ticket> tickets = repository.streamByStatus(
        TicketStatus.OPEN
    )) {

    tickets.forEach(this::process);
}
```

Đây là một query method streaming minh họa, chỉ áp dụng khi module và hợp đồng tài nguyên hỗ trợ; `process` đại diện cho xử lý của ứng dụng.

Cần phân biệt:

```text
Đọc hoàn tất, không phát phần tử -> kết quả rỗng.
Chưa đọc hoàn tất, nguồn lỗi    -> thao tác thất bại.
Đã xử lý một phần, sau đó lỗi   -> có tiến độ nhưng chưa hoàn tất.
```

Bắt lỗi chỉ quanh lời gọi tạo Stream có thể bỏ lỡ lỗi phát sinh khi duyệt. Phạm vi xử lý lỗi và đóng tài nguyên phải bao trùm giai đoạn tiêu thụ.

Nếu ứng dụng công bố một kết quả hoàn chỉnh, không được báo thành công chỉ vì đã xử lý được một số phần tử trước khi nguồn lỗi. Nếu hỗ trợ kết quả từng phần hoặc tiếp tục từ checkpoint, đó phải là hợp đồng riêng có thông tin tiến độ rõ ràng.

Với reactive, tín hiệu hoàn tất không có phần tử khác với tín hiệu lỗi. Không áp dụng fallback trả nguồn rỗng theo thói quen khi lỗi cần được phía gọi biết đến.

## 11. Ghi hợp đồng ngay cạnh query method

Một mô tả hữu ích không chỉ nhắc lại tên method. Nó nêu số lượng, vắng mặt, đầu vào và lỗi có ý nghĩa với phía gọi.

Ví dụ phần khai báo trong repository:

```java
/**
 * Tìm ticket theo tenant và mã tham chiếu nghiệp vụ.
 *
 * Hợp đồng nghiệp vụ kỳ vọng mã là duy nhất trong mỗi tenant.
 * Không tìm thấy: trả Optional.empty().
 * Có nhiều kết quả: không tự chọn một ticket để trả về.
 *
 * Phía gọi phải cung cấp tenantId và externalRef hợp lệ.
 * Lỗi truy vấn không được biểu đạt thành kết quả empty.
 */
Optional<Ticket> findByTenantIdAndExternalRef(
    String tenantId,
    String externalRef
);
```

Đoạn mô tả về đầu vào cần đi cùng cơ chế thực thi phù hợp, chẳng hạn validation ở service hoặc nullability/validation được dự án hỗ trợ. Viết comment không tự khiến mọi điều kiện được kiểm tra ở runtime.

Với tìm kiếm phân trang, bổ sung:

- Điều kiện lọc và thứ tự được áp dụng.
- Chính sách trang vượt phạm vi.
- Ý nghĩa của tổng số và nội dung trang hiện tại.
- Phía nào chịu trách nhiệm validation page, size và sort.

Với custom fragment, kiểm tra phần triển khai có giữ các bất biến như không trả null cho collection và không nuốt lỗi truy cập hay không.

## 12. Kiểm chứng hợp đồng bằng những tình huống phân biệt được ý nghĩa

Không chỉ thử trường hợp có một ticket. Một ma trận kiểm chứng tối thiểu cho use case trong bài có thể là:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Một ticket khớp tenant và mã | Optional có giá trị; service require trả ticket. |
| Không có ticket khớp | Optional empty; service require tạo lỗi not-found đã quy định. |
| Hai ticket khớp một mã lẽ ra duy nhất | Không âm thầm lấy bản ghi đầu. |
| Tìm kiếm nhiều phần tử không khớp | List rỗng, không phải null. |
| ID null đưa vào findById | Lỗi hợp đồng đầu vào, không phải Optional empty. |
| Trang vượt phạm vi nhưng tập khớp còn dữ liệu | Nội dung trang rỗng được phân biệt với tổng số bằng không. |
| Thao tác đọc bị lỗi | Phía gọi thấy lỗi, không nhận kết quả rỗng giả. |
| Nguồn streaming lỗi sau vài phần tử | Không báo hoàn tất toàn bộ công việc. |
| Custom fragment hoặc mock được dùng | Kết quả giả lập giữ đúng hợp đồng kiểu trả về và lỗi. |

Ở kiểm thử service, hãy tách riêng ba kịch bản của repository: trả dữ liệu, trả biểu diễn rỗng và ném lỗi. Một test chỉ kiểm tra `Optional.empty()` chưa xác minh được nhánh lỗi truy cập.

Ở kiểm thử tích hợp, dùng module cùng loại kho dữ liệu phù hợp để xác minh những đặc tính như ràng buộc duy nhất, mapping và exception được dịch ra thực tế.

Với một phương thức mới, hãy viết trước hai câu cụ thể: “Không có dữ liệu thì phía gọi nhận gì?” và “Không đọc được dữ liệu thì phía gọi nhận gì?”. Nếu hai câu có cùng một câu trả lời mà không có chính sách nghiệp vụ rõ ràng, hợp đồng đang làm mất thông tin.
