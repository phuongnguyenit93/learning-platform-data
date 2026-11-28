# Xử lý OptimisticLockingFailureException bằng tải lại dữ liệu

Trong ứng dụng dùng Spring Data Neo4j (SDN), nhiều request có thể cùng đọc và cập nhật một node. Nếu hai request tải entity ở cùng một phiên bản, request lưu trước sẽ cập nhật phiên bản trong database. Request còn lại vẫn giữ dữ liệu cũ nên không được phép ghi đè âm thầm thay đổi mới. SDN báo lỗi `OptimisticLockingFailureException` để ứng dụng nhận biết xung đột.

Cách xử lý phù hợp là tải lại entity trong một transaction mới, áp dụng lại ý định nghiệp vụ trên dữ liệu mới nhất rồi thử lưu lại với số lần giới hạn. Không tiếp tục lưu object cũ đã mang version lỗi thời. Việc tải lại giúp ứng dụng có cơ hội hợp nhất thay đổi hoặc xác định rằng yêu cầu ban đầu không còn hợp lệ.

## 1. Vì sao xuất hiện optimistic locking failure?

Optimistic locking phù hợp khi xung đột không thường xuyên và ứng dụng muốn tránh khóa dữ liệu trong suốt thời gian người dùng chỉnh sửa. SDN hỗ trợ cơ chế này bằng annotation `@Version` trên một thuộc tính kiểu `Long`.

Ví dụ hai request cùng đọc một người:

1. Request A đọc entity với `version = 4`.
2. Request B cũng đọc entity với `version = 4`.
3. A cập nhật tên và lưu thành công; SDN tăng version trong database lên `5`.
4. B sửa object cũ vẫn có `version = 4` rồi gọi `save`.
5. SDN phát hiện version không còn khớp và ném `OptimisticLockingFailureException`.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Neo4j
    A->>DB: Đọc Person (version 4)
    B->>DB: Đọc Person (version 4)
    A->>DB: Save version 4
    DB-->>A: Thành công, version 5
    B->>DB: Save version 4
    DB-->>B: OptimisticLockingFailureException
~~~

Lỗi này không nhất thiết là sự cố hạ tầng. Nó là tín hiệu rằng dữ liệu đã thay đổi kể từ lần đọc của request hiện tại. Ứng dụng cần quyết định có thể tự hợp nhất và thử lại hay phải yêu cầu người dùng giải quyết xung đột.

## 2. Khai báo `@Version` trên entity

Để SDN kiểm tra version khi cập nhật, entity cần có một thuộc tính được đánh dấu `@Version`:

~~~java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String personKey;
    private String name;

    @Version
    private Long version;

    protected Person() {
    }

    public Person(String personKey, String name) {
        this.personKey = personKey;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getPersonKey() {
        return personKey;
    }

    public String getName() {
        return name;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
~~~

`@Version` thuộc package `org.springframework.data.annotation.Version`. SDN quản lý giá trị này: version được khởi tạo khi tạo entity mới và tự tăng khi cập nhật thành công. Không tự gán hoặc tăng version trong code nghiệp vụ.

Repository dùng để tải entity mới nhất:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, Long> {

    Optional<Person> findByPersonKey(String personKey);
}
~~~

`personKey` trong ví dụ là khóa nghiệp vụ cần được bảo đảm duy nhất bằng constraint ở Neo4j. Nếu dùng business ID thay cho generated ID, SDN cũng yêu cầu trường `@Version` để nhận biết entity mới hay đã tồn tại.

## 3. Không lưu lại object cũ sau khi xung đột

Khi nhận `OptimisticLockingFailureException`, object vừa lưu vẫn chứa snapshot cũ. Trường `version` của object đó không đại diện cho version hiện tại trong database. Không nên:

- Gọi `save` lặp lại trên cùng object cũ.
- Tự tăng trường version để làm cho lần lưu tiếp theo có vẻ hợp lệ.
- Bỏ qua lỗi rồi báo cho caller rằng cập nhật đã thành công.
- Dùng dữ liệu cũ để thay thế toàn bộ entity mới tải về.

Hãy tải lại entity từ repository, nhận version mới nhất, rồi áp dụng lại thao tác nghiệp vụ. Nếu entity đã bị xóa, lần tải lại sẽ không tìm thấy; đây là tình huống cần xử lý như bản ghi không còn tồn tại, không phải tiếp tục retry mù quáng.

## 4. Tải lại và thử lưu trong transaction mới

Một lần lưu bị optimistic locking failure thường làm transaction hiện tại thất bại hoặc bị đánh dấu rollback. Vì vậy, không nên bắt exception bên trong cùng transaction rồi tải lại và tiếp tục dùng transaction đó như thể chưa có lỗi.

Một cách tổ chức rõ ràng là tách bộ điều phối retry khỏi bean thực hiện một lần cập nhật:

- Bean điều phối không giữ transaction đang hoạt động trong suốt vòng lặp retry.
- Mỗi lần thử gọi một bean khác có `@Transactional`.
- Nếu lần thử thất bại, transaction của bean cập nhật rollback trước khi exception được bắt ở bộ điều phối.
- Lần thử tiếp theo gọi lại bean cập nhật, mở transaction mới và tải entity mới.

Bean thực hiện một lần cập nhật:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class PersonUpdateAttempt {

    private final PersonRepository people;

    public PersonUpdateAttempt(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public Person rename(String personKey, String newName) {
        Person person = people.findByPersonKey(personKey)
            .orElseThrow(() -> new IllegalArgumentException(
                "Person not found: " + personKey
            ));

        person.rename(newName);
        return people.save(person);
    }
}
~~~

Mỗi lần gọi `rename` qua Spring proxy sẽ có một transaction cho thao tác tải–sửa–lưu. Nếu `save` ném optimistic locking failure, transaction đó kết thúc bằng rollback và exception được chuyển về caller.

## 5. Bộ điều phối retry có giới hạn

Bộ điều phối bắt exception bên ngoài transaction của lần thử và gọi lại bean cập nhật. Ví dụ sau giới hạn tối đa ba lần thử và tăng nhẹ thời gian chờ:

~~~java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private static final int MAX_ATTEMPTS = 3;

    private final PersonUpdateAttempt updateAttempt;

    public PersonService(PersonUpdateAttempt updateAttempt) {
        this.updateAttempt = updateAttempt;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public Person renameWithRetry(String personKey, String newName) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                return updateAttempt.rename(personKey, newName);
            } catch (OptimisticLockingFailureException ex) {
                if (attempt == MAX_ATTEMPTS) {
                    throw ex;
                }

                try {
                    Thread.sleep(20L * attempt);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Retry interrupted while updating person", interrupted
                    );
                }
            }
        }

        throw new IllegalStateException("Unreachable retry state");
    }
}
~~~

`Propagation.NOT_SUPPORTED` bảo đảm bộ điều phối không tiếp tục chạy bên trong transaction đang hoạt động. Nếu caller có transaction, Spring tạm ngưng transaction đó trong thời gian retry; mỗi lần gọi `PersonUpdateAttempt.rename` sẽ bắt đầu transaction riêng. Vì vậy, không gọi phương thức này nếu nghiệp vụ yêu cầu thay đổi của nó phải commit hoặc rollback cùng transaction bên ngoài đang bị tạm ngưng.

Trong hệ thống có tải cao, có thể dùng backoff tăng dần kèm jitter để giảm khả năng nhiều request xung đột lại cùng một thời điểm. Số lần thử phải hữu hạn. Nếu vẫn xung đột sau giới hạn, hãy trả lỗi phù hợp lên tầng trên để người dùng hoặc quy trình nghiệp vụ quyết định bước tiếp theo.

## 6. Retry phải tải lại và áp dụng lại ý định nghiệp vụ

Điều quan trọng nhất không phải chỉ là gọi `save` lần nữa, mà là thực hiện lại toàn bộ chu trình:

~~~mermaid
flowchart TD
    A[Bắt đầu một lần thử] --> B[Tải entity mới nhất]
    B --> C[Kiểm tra điều kiện nghiệp vụ]
    C --> D[Áp dụng command lên entity mới]
    D --> E[Save]
    E -->|Thành công| F[Commit và trả kết quả]
    E -->|Version xung đột| G[Rollback transaction]
    G --> H{Còn lượt thử?}
    H -->|Có| A
    H -->|Không| I[Trả lỗi xung đột]
~~~

Ví dụ `rename` nhận `newName` như một command độc lập. Khi retry, service tải người mới nhất rồi đặt tên theo command đó. Cách này có thể đúng nếu quy tắc nghiệp vụ cho phép yêu cầu mới nhất thắng sau khi xác nhận các điều kiện khác.

Với thao tác phụ thuộc giá trị cũ, cần tính lại kết quả trên entity vừa tải. Ví dụ tăng số điểm thêm 10 phải đọc số điểm mới nhất rồi cộng 10, thay vì lưu lại một số điểm tuyệt đối được tính từ snapshot cũ. Tương tự, khi thêm thành viên vào collection relationship, hãy tải aggregate mới nhất rồi kiểm tra thành viên đã có hay chưa trước khi thêm.

## 7. Phân biệt retry tự động và giải quyết xung đột nghiệp vụ

Tải lại dữ liệu không tự quyết định thay đổi nào nên thắng. Hãy chọn chính sách theo loại thao tác:

| Loại thao tác | Cách xử lý sau khi tải lại | Lưu ý |
|---|---|---|
| Cập nhật độc lập như đặt một trường theo command mới | Áp dụng lại giá trị command lên entity mới | Chỉ phù hợp nếu chính sách cho phép giá trị mới ghi đè |
| Cập nhật tăng/giảm dựa trên giá trị hiện tại | Tính lại phép biến đổi trên giá trị mới nhất | Không dùng kết quả đã tính từ snapshot cũ |
| Thêm phần tử vào collection | Kiểm tra lại phần tử đã tồn tại rồi mới thêm | Tránh tạo quan hệ trùng theo nghiệp vụ |
| Chuyển trạng thái có điều kiện | Kiểm tra lại trạng thái hiện tại và luật chuyển trạng thái | Nếu trạng thái không còn hợp lệ, dừng và báo conflict |
| Hai người cùng sửa một trường cần người dùng lựa chọn | Trả thông tin xung đột lên tầng API | Không tự động ghi đè thay đổi của người khác |

Ví dụ, nếu người dùng A đổi tên thành `Lan` và người dùng B đổi tên thành `Minh`, retry của B có thể ghi `Minh` sau khi tải version mới. Đây là chính sách last-write-wins ở tầng ứng dụng. Nếu nghiệp vụ không chấp nhận điều đó, cần so sánh giá trị người dùng đã đọc với giá trị hiện tại và yêu cầu xác nhận thay vì tự retry.

## 8. Khi entity không còn tồn tại hoặc điều kiện đã thay đổi

Sau khi xung đột, lần tải lại có thể trả về `Optional.empty()` vì một request khác đã xóa entity. Cũng có thể entity vẫn còn nhưng trạng thái đã thay đổi khiến command không còn hợp lệ.

Hãy phân biệt các kết quả:

- **Entity còn tồn tại và command vẫn hợp lệ:** có thể áp dụng lại và thử lưu.
- **Entity đã bị xóa:** trả `NotFound` hoặc kết quả nghiệp vụ tương ứng.
- **Entity còn tồn tại nhưng luật nghiệp vụ không còn thỏa:** trả conflict hoặc validation error; không tiếp tục retry.
- **Xung đột tiếp diễn:** kết thúc sau số lần thử tối đa và báo lỗi để caller xử lý.

Không chuyển mọi lỗi thành retry. Lỗi kết nối, lỗi cú pháp Cypher, lỗi quyền truy cập hoặc validation không được giải quyết bằng cách tải lại entity.

## 9. Cẩn thận với side effect bên ngoài transaction

Retry có thể chạy cùng một command nhiều lần. Vì vậy, không gửi email, gọi thanh toán, phát sự kiện không idempotent hoặc gọi HTTP sang hệ thống khác bên trong method được retry nếu side effect đó không được kiểm soát.

Một cách tổ chức an toàn hơn:

1. Thực hiện cập nhật graph trong transaction.
2. Khi transaction commit thành công, phát side effect ở bước riêng.
3. Nếu cần bảo đảm sự kiện không bị mất giữa commit và publish, dùng transactional outbox hoặc cơ chế phát sự kiện có tính idempotent.

Nếu retry cả thao tác gửi email, người nhận có thể nhận nhiều email dù chỉ có một lần cập nhật graph thành công. Chỉ retry các thao tác có thể thực hiện lại an toàn hoặc đã có idempotency key phù hợp.

## 10. Custom Cypher và `@Version`

Optimistic locking tự động của SDN dựa trên metadata entity và được áp dụng khi lưu entity qua repository hoặc template theo cơ chế mapping. Nếu tự viết Cypher cập nhật node trực tiếp, không giả định câu lệnh đó tự thực hiện kiểm tra `@Version`.

Với custom Cypher, nếu muốn compare-and-set, cần đưa version mong đợi vào điều kiện và tăng version trong cùng câu lệnh:

~~~cypher
MATCH (p:Person {personKey: $personKey})
WHERE p.version = $expectedVersion
SET p.name = $newName,
    p.version = p.version + 1
RETURN p.version AS version;
~~~

Nếu không có record trả về, version không khớp hoặc node không còn tồn tại; ứng dụng cần phân biệt hai tình huống bằng một lần đọc phù hợp. Không trộn cập nhật version thủ công bằng Cypher với `repository.save` mà không có quy ước nhất quán, vì hai cơ chế cùng quản lý một version có thể khiến ứng dụng phát sinh xung đột ngoài dự kiến.

## 11. Kiểm thử tình huống optimistic locking

Một bài kiểm thử tích hợp có thể mô phỏng hai bản sao entity cùng version:

1. Lưu một `Person` có `@Version`.
2. Đọc entity thành hai object riêng `first` và `second`.
3. Sửa và lưu `first`; xác nhận save thành công và version tăng.
4. Sửa `second` rồi gọi save; xác nhận nhận `OptimisticLockingFailureException`.
5. Tải lại entity bằng repository; xác nhận version và dữ liệu phản ánh thay đổi của `first`.
6. Áp dụng command của `second` lên entity mới và lưu trong transaction mới.
7. Xác nhận kết quả cuối đúng theo chính sách hợp nhất đã chọn.

Ngoài trường hợp retry thành công, hãy kiểm tra entity bị xóa giữa hai lần thử, command không còn hợp lệ và số lần xung đột vượt quá giới hạn. Các kiểm thử này giúp xác nhận ứng dụng không ghi đè dữ liệu mới bằng snapshot cũ.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Lưu lại object cũ sau khi nhận exception | Version vẫn lỗi thời nên tiếp tục xung đột | Tải entity mới trong transaction mới |
| Tự tăng trường `version` trong Java | Bỏ qua cơ chế version do SDN quản lý và có thể gây sai lệch | Để SDN tự quản lý `@Version` |
| Bắt exception trong transaction đã lỗi rồi tiếp tục ghi | Transaction có thể đã rollback hoặc rollback-only | Bắt lỗi bên ngoài transaction của lần thử |
| Chỉ retry câu `save` mà không tải lại | Vẫn sử dụng snapshot cũ | Retry toàn bộ chu trình load–validate–modify–save |
| Retry vô hạn | Tăng tải và có thể không bao giờ kết thúc | Giới hạn số lần thử, thêm backoff |
| Retry cả lỗi validation hoặc lỗi kết nối | Lặp lại lỗi không thể giải quyết bằng tải lại | Chỉ retry optimistic locking failure đã xác định |
| Áp dụng lại command mà không kiểm tra nghiệp vụ | Có thể ghi đè thay đổi hợp lệ của người khác | Tính lại điều kiện và chọn chính sách conflict |
| Gửi side effect trong khối retry | Email hoặc sự kiện có thể bị phát nhiều lần | Tách side effect khỏi lần thử hoặc dùng outbox/idempotency |
| Dùng custom Cypher nhưng bỏ qua version | Ghi trực tiếp có thể không được bảo vệ bởi `@Version` của SDN | Tự triển khai compare-and-set hoặc dùng entity persistence |

## 13. Quy trình xử lý đề xuất

1. Khai báo `@Version` trên entity cần optimistic locking và không sửa version bằng tay.
2. Khi `save` phát sinh `OptimisticLockingFailureException`, kết thúc và rollback transaction của lần thử.
3. Bắt lỗi ở tầng điều phối bên ngoài transaction đó.
4. Mở transaction mới, tải entity hiện tại từ repository.
5. Kiểm tra entity còn tồn tại và command vẫn hợp lệ.
6. Áp dụng lại ý định nghiệp vụ lên entity mới, sau đó gọi `save`.
7. Retry với số lần hữu hạn và backoff phù hợp.
8. Nếu vẫn xung đột hoặc không thể hợp nhất, trả lỗi lên tầng trên để xử lý rõ ràng.
9. Chỉ phát side effect sau khi cập nhật graph commit thành công.

## 14. Tự kiểm tra

1. Vì sao hai request cùng tải entity với một version có thể khiến một request nhận `OptimisticLockingFailureException`?
2. `@Version` được SDN quản lý như thế nào khi lưu thành công?
3. Vì sao không nên retry bằng cách gọi `save` lại trên object cũ?
4. Vì sao cần bắt exception bên ngoài transaction đã thất bại?
5. Một lần retry đúng cần thực hiện lại những bước nào?
6. Khi nào nên tự retry và khi nào cần trả xung đột cho người dùng?
7. Vì sao không nên gửi email hoặc gọi dịch vụ thanh toán bên trong khối retry?
8. Khi dùng custom Cypher để cập nhật entity có version, cần bảo đảm điều gì?

`OptimisticLockingFailureException` cho biết snapshot đang lưu đã cũ so với dữ liệu trong Neo4j. Hãy kết thúc transaction thất bại, tải lại entity trong transaction mới, kiểm tra lại luật nghiệp vụ rồi áp dụng command trên dữ liệu mới nhất. Retry có giới hạn chỉ phù hợp khi thao tác có thể thực hiện lại an toàn; nếu không thể tự hợp nhất, hãy để tầng nghiệp vụ xử lý xung đột một cách minh bạch.

Tài liệu tham khảo: [Spring Data Neo4j – Metadata-based Mapping, Optimistic locking](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html).
