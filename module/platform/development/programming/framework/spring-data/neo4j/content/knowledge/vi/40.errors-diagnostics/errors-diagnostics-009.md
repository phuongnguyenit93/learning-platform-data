# Optimistic locking, vi phạm constraint và deadlock

Khi nhiều request cùng cập nhật một graph Neo4j, ứng dụng có thể gặp ba nhóm lỗi khác nhau: **optimistic locking conflict**, **constraint violation** và **deadlock**. Cả ba đều có thể khiến một thao tác ghi thất bại, nhưng nguyên nhân và cách xử lý không giống nhau.

Spring Data Neo4j (SDN) hỗ trợ optimistic locking qua `@Version`. Neo4j thực thi uniqueness và các constraint khác ở cấp database. Transaction engine phát hiện deadlock khi các transaction giữ lock theo thứ tự xung đột và hủy một transaction để giải phóng tình trạng chờ vòng tròn. Muốn chẩn đoán đúng, cần nhận diện loại lỗi trước khi quyết định tải lại dữ liệu, trả conflict cho client hay retry transaction.

## 1. Phân biệt ba nhóm lỗi

| Nhóm lỗi | Nguyên nhân | Ví dụ | Hướng xử lý thường dùng |
|---|---|---|---|
| Optimistic locking conflict | Entity đã bị transaction khác cập nhật sau khi request hiện tại đọc nó | Hai người cùng sửa một `Person` với cùng version | Đọc lại dữ liệu, hợp nhất thay đổi hoặc trả conflict để người dùng xử lý |
| Constraint violation | Dữ liệu ghi vi phạm quy tắc schema của Neo4j | Hai node `Person` có cùng email đã được khai báo unique | Kiểm tra dữ liệu đầu vào, trả lỗi nghiệp vụ; không retry cùng payload |
| Deadlock | Các transaction đồng thời giữ lock và chờ tài nguyên của nhau theo thứ tự khác nhau | Transaction A cập nhật node X rồi Y; transaction B cập nhật Y rồi X | Để một transaction thất bại, giảm tranh chấp và cân nhắc retry toàn bộ transaction với giới hạn |

Không nên gom mọi lỗi ghi thành “database bận”. Optimistic locking thường biểu thị dữ liệu đã thay đổi so với lúc đọc; constraint violation biểu thị dữ liệu không hợp lệ theo schema; deadlock là xung đột đồng thời trong việc lấy lock.

## 2. Vì sao cần kiểm soát cập nhật đồng thời?

Giả sử hai request cùng đọc một node `Person`:

```text
Request A                         Request B
---------                         ---------
Đọc name = "An"                  Đọc name = "An"
Đọc version = 4                  Đọc version = 4
Đổi name thành "Anh"             Đổi name thành "Annie"
Ghi thành công, version = 5
                                  Cố ghi dựa trên version = 4
                                  Phát hiện dữ liệu đã đổi
```

Nếu không có cơ chế phát hiện xung đột, request B có thể ghi đè thay đổi của A dù B được xây dựng từ dữ liệu cũ. Đây là lost update.

Optimistic locking giả định xung đột không xảy ra thường xuyên. Nó cho phép nhiều request đọc đồng thời, sau đó kiểm tra version tại thời điểm ghi. Nếu version đã thay đổi, thao tác ghi bị từ chối thay vì âm thầm ghi đè.

## 3. Bật optimistic locking bằng @Version

SDN dùng annotation `org.springframework.data.annotation.Version` trên entity node:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Version
    private Long version;

    private String name;

    protected Person() {
    }

    public Person(String personId, String name) {
        this.personId = personId;
        this.name = name;
    }

    public String getPersonId() {
        return personId;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = newName;
    }
}
```

Với entity dùng ID do ứng dụng cấp, `Long version` có giá trị `null` trên object mới. SDN dùng version để nhận diện entity mới, sau đó quản lý giá trị version khi lưu. Dùng wrapper `Long` để trạng thái chưa có version được biểu diễn bằng `null`; kiểu primitive `long` luôn có giá trị mặc định `0` và không biểu diễn được trạng thái này theo cùng cách. Không tự tăng version trong service.

Khi đọc entity đã tồn tại, SDN hydrate cả version. Khi lưu thay đổi, SDN kiểm tra version đã đọc có còn khớp với trạng thái trong database hay không. Nếu một transaction khác đã cập nhật node, lần ghi dựa trên version cũ không thể hoàn tất như một cập nhật bình thường.

`@Version` không phải uniqueness constraint. Nó kiểm soát cập nhật cạnh tranh cho entity; constraint như `IS UNIQUE` bảo vệ quy tắc dữ liệu trước mọi client ghi vào Neo4j.

## 4. Cập nhật entity qua repository

Repository có thể dùng `save` như các thao tác thông thường:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

Service đọc entity, thay đổi property rồi lưu lại:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Person rename(String personId, String newName) {
        Person person = repository.findById(personId)
            .orElseThrow(() -> new PersonNotFoundException(personId));

        person.rename(newName);
        return repository.save(person);
    }
}
```

`PersonNotFoundException` là exception nghiệp vụ do ứng dụng định nghĩa. SDN quản lý version trong quá trình mapping và persistence; service không cần tự viết câu lệnh tăng version cho thao tác repository thông thường.

## 5. Điều gì xảy ra khi version đã cũ?

Giả sử cả hai transaction đọc entity ở version `4`:

1. Transaction A đổi tên và lưu thành công. Version được tăng lên `5`.
2. Transaction B vẫn giữ object có version `4`.
3. Khi B lưu, SDN phát hiện version trong database không còn là `4`.
4. SDN báo optimistic locking failure thay vì ghi đè dữ liệu của A.

Ở tầng Spring Data, lỗi thường được biểu diễn bằng `OptimisticLockingFailureException` thuộc `org.springframework.dao`. Đây là lỗi thuộc nhóm `ConcurrencyFailureException`.

Ví dụ xử lý ở API boundary:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OptimisticLockingFailureException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    public ApiError handleOptimisticLocking(OptimisticLockingFailureException exception) {
        return new ApiError(
            "CONCURRENT_UPDATE",
            "Dữ liệu đã được cập nhật bởi một thao tác khác. Hãy tải lại và thử lại."
        );
    }
}
```

`ApiError` là response DTO do ứng dụng định nghĩa. HTTP `409 Conflict` phù hợp khi client cần biết thao tác không thể áp dụng lên phiên bản dữ liệu hiện tại.

## 6. Nên làm gì sau optimistic locking failure?

Không nên bắt `OptimisticLockingFailureException` rồi lưu lại chính object cũ. Object đó vẫn mang version đã lỗi thời, nên lần save tiếp theo có thể tiếp tục thất bại hoặc làm mất thay đổi của request khác nếu ứng dụng bỏ qua version.

Chọn cách xử lý theo nghiệp vụ:

- **Trả conflict:** phù hợp với biểu mẫu chỉnh sửa, nơi người dùng cần xem dữ liệu mới nhất và quyết định hợp nhất.
- **Đọc lại và áp dụng lại command:** phù hợp với thay đổi độc lập có thể tính lại an toàn từ trạng thái mới nhất.
- **Hợp nhất có quy tắc:** phù hợp khi hai request thay đổi các field khác nhau và nghiệp vụ định nghĩa rõ cách kết hợp.
- **Bỏ thao tác:** phù hợp khi yêu cầu đã lỗi thời hoặc không còn cần thiết.

Ví dụ, nếu command chỉ tăng bộ đếm và nghiệp vụ cho phép cộng dồn, có thể đọc lại giá trị mới nhất rồi áp dụng phép tăng. Nếu command thay thế toàn bộ tên hoặc địa chỉ do người dùng nhập, không được tự động ghi đè dữ liệu mới nhất mà không có quyết định hợp nhất.

Optimistic locking failure không đồng nghĩa database hỏng. Nó là tín hiệu rằng dữ liệu đã thay đổi kể từ lần đọc mà request dựa vào.

## 7. Custom Cypher không tự động áp dụng @Version

`@Version` được SDN áp dụng trong entity mapping và các thao tác persistence được framework quản lý. Một câu Cypher tự viết qua `@Query`, `Neo4jClient` hoặc Neo4j Driver không tự động được SDN thêm điều kiện version hay tăng version.

Nếu cần optimistic concurrency cho custom Cypher, hãy kiểm tra version tường minh:

```cypher
MATCH (p:Person {personId: $personId})
WHERE p.version = $expectedVersion
SET p.name = $newName,
    p.version = p.version + 1
RETURN p;
```

Nếu version không khớp, query không trả node. Ứng dụng có thể ánh xạ kết quả rỗng thành conflict. Cần bảo đảm mọi đường ghi vào entity này cùng tuân theo một quy ước version; nếu một luồng cập nhật property nhưng không tăng version, các luồng optimistic locking khác có thể không phát hiện thay đổi đó.

Với query có nhiều bước, nên thực hiện kiểm tra và cập nhật trong cùng transaction. Nếu query chỉ trả kết quả rỗng, cần phân biệt entity không tồn tại với entity tồn tại nhưng version không khớp; có thể dùng một query bổ sung trong cùng transaction hoặc trả một trạng thái kết quả tường minh.

## 8. Constraint violation là lỗi dữ liệu theo schema

Constraint được Neo4j thực thi ở cấp database. Ví dụ, nếu email của mỗi `Person` phải duy nhất:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Khi hai transaction cùng cố tạo hoặc cập nhật node để có cùng email, Neo4j chỉ cho phép trạng thái cuối cùng thỏa mãn constraint. Một thao tác vi phạm sẽ thất bại.

Constraint violation khác optimistic locking:

- Optimistic locking kiểm tra entity có còn ở version mà caller đã đọc không.
- Uniqueness constraint kiểm tra giá trị property có trùng với node khác trong phạm vi label không.
- Hai request có thể đọc hai entity ở version hoàn toàn khác nhau nhưng vẫn xung đột vì cùng đặt một email.

Ví dụ, hai tài khoản `P-101` và `P-202` có version riêng. Cả hai đều có thể được cập nhật thành `same@example.com`; version của từng node không ngăn được email trùng. Uniqueness constraint mới là cơ chế bảo vệ đúng quy tắc này.

## 9. Phân biệt uniqueness, existence và node key constraint

Một uniqueness constraint không tự bắt buộc property phải tồn tại. Nếu `email` vừa bắt buộc vừa duy nhất, cần chọn constraint phù hợp với phiên bản và edition Neo4j:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS UNIQUE;
```

Property existence constraint:

```cypher
CREATE CONSTRAINT person_email_required IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS NOT NULL;
```

Node key constraint kết hợp sự tồn tại và tính duy nhất của một hoặc nhiều property:

```cypher
CREATE CONSTRAINT person_email_key IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.email) IS NODE KEY;
```

Property existence và node key constraint có yêu cầu hỗ trợ theo edition Neo4j. Hãy kiểm tra edition/version của database trước khi dùng. Trong mọi trường hợp, validation ở service giúp trả lỗi thân thiện nhưng không thay thế constraint database khi dữ liệu có thể được ghi từ nhiều client.

## 10. Xử lý lỗi khi tạo hoặc cập nhật vi phạm constraint

Với repository và template, lỗi từ Neo4j thường được dịch sang hệ thống exception truy cập dữ liệu của Spring. Constraint violation có thể xuất hiện dưới dạng `DataIntegrityViolationException` hoặc exception Spring Data/Driver có cause tương ứng, tùy đường gọi và phiên bản.

Ở API boundary, có thể chuyển lỗi vi phạm uniqueness đã xác định thành `409 Conflict` hoặc `422 Unprocessable Entity`, tùy hợp đồng API. Không nên bắt mọi `DataIntegrityViolationException` rồi trả thông báo “email đã tồn tại”, vì lỗi có thể đến từ constraint khác.

Để chẩn đoán, cần ghi nhận:

- Spring exception class ở ngoài cùng.
- Root cause và Neo4j error code nếu có.
- Tên constraint hoặc label/property được nhắc trong thông báo lỗi.
- Operation đang chạy và correlation/request ID.

Không trả nguyên stack trace, query nội bộ hoặc thông tin kết nối database cho client. Chuyển lỗi thành mã nghiệp vụ rõ ràng sau khi đã xác định đúng constraint.

## 11. Kiểm tra dữ liệu cũ trước khi tạo constraint

Nếu database đã có dữ liệu, lệnh tạo uniqueness constraint có thể thất bại khi tồn tại duplicate. Tìm các email trùng trước:

```cypher
MATCH (p:Person)
WHERE p.email IS NOT NULL
WITH p.email AS email, count(*) AS occurrences
WHERE occurrences > 1
RETURN email, occurrences
ORDER BY occurrences DESC;
```

Kiểm tra node chưa có email:

```cypher
MATCH (p:Person)
WHERE p.email IS NULL
RETURN count(p) AS peopleWithoutEmail;
```

Xử lý duplicate theo quy tắc nghiệp vụ trước khi tạo constraint. Không xóa node trùng một cách tự động nếu chúng có relationship hoặc dữ liệu phụ thuộc cần hợp nhất.

Sau khi tạo constraint, kiểm tra schema:

```cypher
SHOW CONSTRAINTS;
```

Quản lý thay đổi constraint bằng migration có phiên bản để các môi trường development, test và production có schema nhất quán.

## 12. Deadlock trong Neo4j là gì?

Neo4j dùng lock để điều phối các transaction đồng thời cập nhật graph. Deadlock có thể xảy ra khi transaction này giữ lock mà transaction khác cần, đồng thời transaction thứ hai lại giữ lock mà transaction thứ nhất đang chờ.

Ví dụ hai transaction cập nhật hai node theo thứ tự ngược nhau:

```text
Transaction A                    Transaction B
--------------                    --------------
Lấy lock node X                   Lấy lock node Y
Yêu cầu lock node Y               Yêu cầu lock node X
Chờ B nhả Y                       Chờ A nhả X
             \\                  /
              \---- Deadlock ---/
```

Neo4j phát hiện vòng chờ và hủy một transaction để giải phóng deadlock. Transaction còn lại có thể tiếp tục khi lock cần thiết được giải phóng. Ứng dụng phải xử lý transaction bị hủy như một lần thực thi thất bại.

Deadlock không giống lock timeout. Deadlock là vòng chờ được phát hiện; timeout là transaction chờ quá thời hạn cấu hình. Cả hai có thể làm transaction thất bại, nhưng cách chẩn đoán dựa trên error code và log sẽ khác nhau.

## 13. Nguyên nhân deadlock thường gặp

Một số tình huống dễ tạo tranh chấp:

- Hai transaction cập nhật cùng một tập node hoặc relationship theo thứ tự khác nhau.
- Nhiều request đồng thời chuyển trạng thái các entity có liên kết chéo.
- Transaction ghi quá lâu, giữ lock trong thời gian dài.
- Một thao tác nghiệp vụ mở rộng cập nhật nhiều node không có thứ tự nhất quán.
- Nhiều worker xử lý các batch có phần tử giao nhau.
- Query `MERGE`, `SET`, `DELETE` hoặc thao tác relationship tạo cạnh tranh trên cùng vùng graph.

Không phải cứ có nhiều request cùng đọc một node là deadlock. Deadlock thường liên quan đến các thao tác cần lock và thứ tự chiếm giữ lock. Một transaction chỉ đọc thường không tạo cùng kiểu xung đột ghi như hai transaction sửa graph.

## 14. Thiết kế thứ tự cập nhật nhất quán

Nếu một nghiệp vụ phải cập nhật nhiều node, hãy xác định một thứ tự ổn định và dùng cùng thứ tự trong mọi luồng.

Ví dụ, quy ước luôn xử lý node theo `personId` tăng dần:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> orderedIds = Stream.of(firstPersonId, secondPersonId)
    .sorted()
    .toList();

for (String personId : orderedIds) {
    updatePersonInCurrentTransaction(personId);
}
```

Ví dụ trên chỉ minh họa quy tắc sắp thứ tự ID trước khi cập nhật; `updatePersonInCurrentTransaction` là thao tác persistence do ứng dụng định nghĩa và phải tham gia cùng transaction hiện tại. Khi các luồng dùng cùng thứ tự, khả năng lấy lock theo thứ tự ngược nhau giảm đi.

Với batch, sắp xếp khóa trước khi xử lý và chia batch thành kích thước hợp lý. Không giữ transaction mở trong lúc gọi HTTP, gửi email hoặc chờ thao tác I/O bên ngoài nếu không cần thiết.

## 15. Giảm thời gian giữ lock

Để giảm xác suất deadlock và lock contention:

1. Giữ transaction ngắn, chỉ bao quanh thao tác cần tính nguyên tử.
2. Đọc và validate dữ liệu trước khi bắt đầu phần ghi nếu quy trình nghiệp vụ cho phép.
3. Chỉ cập nhật node/relationship thực sự cần thay đổi.
4. Tránh tải graph lớn rồi ghi lại toàn bộ khi chỉ cần đổi một property.
5. Chia batch ghi lớn thành batch nhỏ có ranh giới transaction rõ ràng.
6. Dùng index/constraint để tìm node gốc hiệu quả, tránh query quét quá nhiều dữ liệu.
7. Duy trì thứ tự cập nhật nhất quán giữa các code path.
8. Theo dõi transaction dài và truy vấn có số lượng DB hits bất thường.

Không chia một nghiệp vụ thành nhiều transaction nhỏ nếu điều đó làm mất tính nguyên tử mà nghiệp vụ yêu cầu. Cần cân bằng giữa phạm vi transaction, số lock và tính đúng đắn của dữ liệu.

## 16. Nhận diện deadlock qua Neo4j error code

Neo4j Driver trả mã lỗi theo phân loại lỗi của Neo4j. Deadlock thường có mã:

```text
Neo.TransientError.Transaction.DeadlockDetected
```

Tiền tố `TransientError` cho biết lỗi thuộc nhóm có thể tạm thời và một lần thực thi khác có thể thành công. Khi SDN sử dụng Spring transaction abstraction, lỗi có thể được bọc trong exception của Spring; hãy kiểm tra root cause và Neo4j error code thay vì chỉ dựa vào class ngoài cùng.

Phân biệt một số dấu hiệu:

| Dấu hiệu | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `OptimisticLockingFailureException` | Entity version không còn khớp | Reload/merge hoặc trả conflict |
| `Neo.TransientError.Transaction.DeadlockDetected` | Transaction bị hủy do deadlock | Điều chỉnh lock order, giảm transaction duration; retry có giới hạn nếu an toàn |
| `Neo.ClientError.Schema.ConstraintValidationFailed` | Ghi dữ liệu vi phạm constraint | Sửa dữ liệu hoặc xử lý xung đột nghiệp vụ; không retry cùng payload |
| Constraint violation error code | Dữ liệu vi phạm schema | Sửa input hoặc xử lý duplicate; không retry cùng payload |
| Connection/availability error | Driver không liên lạc được với server hoặc cụm | Kiểm tra connectivity, availability và retry theo chính sách transient phù hợp |

Log nên có request ID, transaction/business operation, entity ID liên quan và error code. Không ghi mật khẩu, token hoặc dữ liệu cá nhân nhạy cảm vào log.

## 17. Khi nào nên retry?

Retry phù hợp với lỗi transient có khả năng biến mất khi thực thi lại, ví dụ một transaction bị hủy do deadlock. Retry không phải cách sửa mọi lỗi ghi.

| Loại lỗi | Retry nguyên payload? | Lý do |
|---|---|---|
| Deadlock transient | Có thể, với giới hạn và backoff | Transaction bị hủy; lần thực thi mới có thể lấy lock theo trạng thái khác |
| Optimistic locking conflict | Không nên retry nguyên entity cũ | Version vẫn cũ; cần đọc lại và hợp nhất hoặc trả conflict |
| Unique constraint violation | Không | Dữ liệu vẫn vi phạm cùng quy tắc nếu gửi lại y nguyên |
| Validation/business rule error | Không | Đầu vào hoặc trạng thái nghiệp vụ cần được sửa |
| Network timeout với kết quả commit không xác định | Chỉ với idempotency strategy | Client có thể không biết transaction đã commit hay chưa |

Neo4j Java Driver có managed transaction functions như `executeRead` và `executeWrite`, có cơ chế retry một số lỗi transient. Tuy nhiên, không được suy ra rằng mọi method Spring `@Transactional` của SDN sẽ tự retry toàn bộ service method. Nếu cần retry ở tầng Spring, phải cấu hình cơ chế retry riêng và đặt nó bên ngoài transaction boundary để mỗi lần thử mở một transaction mới.

## 18. Retry toàn bộ transaction, không retry giữa chừng

Khi transaction đã bị deadlock và rollback, không tiếp tục dùng transaction/session state của lần thử thất bại. Retry phải gọi lại toàn bộ đơn vị công việc trong một transaction mới.

Một cấu trúc phù hợp là đặt retry ở facade và transaction ở một bean khác:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonWriteTransaction {

    private final PersonRepository repository;

    public PersonWriteTransaction(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void rename(String personId, String newName) {
        Person person = repository.findById(personId)
            .orElseThrow(() -> new PersonNotFoundException(personId));
        person.rename(newName);
        repository.save(person);
    }
}
```

Facade không mở transaction bao quanh retry:

```java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

@Service
public class PersonCommandFacade {

    private final RetryTemplate retryTemplate;
    private final PersonWriteTransaction writeTransaction;

    public PersonCommandFacade(
            RetryTemplate retryTemplate,
            PersonWriteTransaction writeTransaction) {
        this.retryTemplate = retryTemplate;
        this.writeTransaction = writeTransaction;
    }

    public void renameWithRetry(String personId, String newName) {
        retryTemplate.execute(context -> {
            writeTransaction.rename(personId, newName);
            return null;
        });
    }
}
```

Ví dụ này giả định ứng dụng đã cấu hình `RetryTemplate` với số lần thử nhỏ, backoff và retry policy chỉ nhận diện các exception transient đã xác minh. `PersonWriteTransaction` là bean riêng nên mỗi lần gọi đi qua transaction proxy. Không đặt `@Transactional` trên facade, nếu không các lần thử có thể cùng tham gia một transaction bên ngoài.

Ví dụ cấu hình cơ bản với Spring Retry 2.x:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class RetryConfiguration {

    @Bean
    RetryTemplate neo4jRetryTemplate() {
        return RetryTemplate.builder()
            .maxAttempts(3)
            .exponentialBackoff(100, 2.0, 1_000)
            .retryOn(TransientDataAccessException.class)
            .build();
    }
}
```

Đây là cấu hình minh họa cho ứng dụng đã thêm dependency Spring Retry. Trong production, thay điều kiện retry tổng quát bằng policy kiểm tra root cause/error code để chỉ retry deadlock hoặc các lỗi transient mà nghiệp vụ cho phép. Số lần thử trong `maxAttempts` bao gồm lần gọi đầu tiên.

Không retry tất cả `TransientDataAccessException` một cách mù quáng nếu nhóm exception đó còn chứa lỗi không phù hợp. Trong production, nên lọc theo root cause/error code, giới hạn số lần thử, thêm exponential backoff và jitter, đồng thời ghi log số lần retry.

## 19. Retry phải an toàn với side effect

Một transaction có thể bị rollback nhưng side effect ngoài Neo4j vẫn đã xảy ra. Ví dụ service gửi email rồi mới ghi graph; nếu transaction ghi gặp deadlock và retry, email có thể được gửi hai lần.

Để retry an toàn:

- Đưa side effect ra sau commit bằng transaction event phù hợp hoặc outbox pattern.
- Dùng idempotency key cho request có thể được gửi lại.
- Đảm bảo command có thể áp dụng lại mà không tạo bản ghi hoặc quan hệ trùng.
- Không tạo ID mới cho mỗi lần retry nếu nghiệp vụ cần nhận diện cùng một yêu cầu.
- Chỉ retry khi biết transaction trước đã rollback hoặc có cách xác định kết quả commit.

Đặc biệt, timeout kết nối sau khi gửi commit có thể để lại kết quả không xác định từ góc nhìn client. Không tự động gửi lại một lệnh tạo dữ liệu không idempotent nếu chưa có idempotency key hoặc bước kiểm tra trạng thái.

## 20. Kiểm thử optimistic locking

Integration test cần dùng hai transaction độc lập để chứng minh một object cũ không thể ghi đè thay đổi mới. Ý tưởng kiểm thử:

1. Tạo `Person` và lưu để có version ban đầu.
2. Trong transaction A, đọc entity và giữ object cùng version.
3. Trong transaction B, đọc cùng entity, cập nhật và commit.
4. Quay lại A, thay đổi object cũ và cố lưu.
5. Xác nhận SDN phát sinh `OptimisticLockingFailureException`.
6. Đọc lại từ transaction mới và xác nhận giá trị của B vẫn được giữ.

Không đặt toàn bộ test trong một transaction duy nhất nếu mục tiêu là mô phỏng hai transaction cạnh tranh. Có thể dùng hai Spring-managed service bean hoặc hai transaction boundary độc lập để kiểm soát thứ tự đọc/ghi.

## 21. Kiểm thử constraint violation

Integration test cho uniqueness constraint nên xác nhận database từ chối duplicate:

1. Tạo constraint trong database test hoặc dùng schema đã migrate.
2. Lưu một `Person` có email cụ thể.
3. Cố lưu `Person` khác với cùng email.
4. Xác nhận thao tác thứ hai thất bại với lỗi constraint tương ứng.
5. Đọc lại database và xác nhận chỉ có một node thỏa mãn email đó.
6. Cleanup dữ liệu theo ID duy nhất sau test.

Không chỉ kiểm tra service validation. Constraint test cần thực sự gửi thao tác ghi tới Neo4j để chứng minh database đang bảo vệ dữ liệu.

## 22. Kiểm thử và tái hiện deadlock

Deadlock là lỗi đồng thời, nên test cần nhiều transaction chạy song song trên cùng tập tài nguyên. Một kịch bản kiểm thử có thể:

1. Tạo hai node A và B.
2. Cho transaction thứ nhất cập nhật A rồi B.
3. Cho transaction thứ hai cập nhật B rồi A.
4. Dùng latch/barrier để đồng bộ thời điểm hai transaction đã lấy lock đầu tiên trước khi yêu cầu lock thứ hai.
5. Ghi nhận error code và xác nhận một transaction bị hủy.
6. Chạy lại cùng nghiệp vụ với thứ tự lock thống nhất và quan sát deadlock giảm hoặc biến mất.

Deadlock test có thể phụ thuộc timing và cấu hình server. Nên dùng integration environment cô lập, timeout hợp lý và đồng bộ bằng latch thay vì dựa vào `Thread.sleep()` để tạo race condition. Không chạy test stress nặng trên database dùng chung với developer khác.

## 23. Bảng chẩn đoán nhanh

| Triệu chứng | Kiểm tra đầu tiên | Cách xử lý |
|---|---|---|
| Save entity báo optimistic locking failure | Entity có `@Version`? Object được đọc từ lúc nào? | Đọc lại, hợp nhất command hoặc trả HTTP 409 |
| Hai entity khác nhau không có version nhưng email trùng | Có uniqueness constraint trên label/property không? | Tạo constraint và validate đầu vào |
| Tạo constraint thất bại khi deploy | Dữ liệu hiện tại có duplicate hoặc property thiếu không? | Truy vấn dữ liệu vi phạm và làm sạch trước migration |
| Neo4j báo `DeadlockDetected` | Các transaction có cập nhật cùng node/relationship theo thứ tự khác nhau? | Chuẩn hóa lock order, rút ngắn transaction, retry có giới hạn |
| Retry vẫn thất bại liên tục | Retry policy có nhận lỗi không transient? Backoff có đủ? | Lọc error code, giảm contention và giới hạn retry |
| Dữ liệu bị tạo trùng sau retry | Command không idempotent hoặc mỗi lần thử sinh ID mới | Dùng idempotency key và stable business ID |
| Custom Cypher không phát hiện version cũ | Query có điều kiện version và tăng version không? | Thêm compare-and-set tường minh hoặc dùng entity persistence API |
| Test không tái hiện xung đột | Các thao tác có thực sự chạy trong transaction độc lập và đồng thời? | Dùng hai transaction/session và barrier đồng bộ |

## 24. Quy trình xử lý optimistic locking, constraint và deadlock

1. Ghi nhận exception class, root cause và Neo4j error code.
2. Phân loại lỗi là optimistic locking, constraint violation, deadlock hay lỗi kết nối khác.
3. Với optimistic locking, đọc lại entity và quyết định hợp nhất hay trả conflict; không lưu lại object version cũ.
4. Với constraint violation, xác định constraint/label/property và kiểm tra dữ liệu đầu vào; không retry cùng payload.
5. Với deadlock, kiểm tra các transaction đang ghi vào cùng vùng graph và thứ tự lấy lock.
6. Rút ngắn transaction, chuẩn hóa thứ tự cập nhật và chia batch hợp lý.
7. Chỉ retry lỗi transient đã xác minh; retry toàn bộ transaction trong transaction mới với backoff và số lần giới hạn.
8. Bảo đảm command idempotent và side effect ngoài database không bị lặp.
9. Kiểm thử riêng version conflict, duplicate constraint và deadlock trên Neo4j integration environment.
10. Theo dõi tỷ lệ conflict, constraint error, deadlock và số lần retry để điều chỉnh thiết kế.

## 25. Ghi nhớ

`@Version` của Spring Data Neo4j bảo vệ entity khỏi lost update bằng optimistic locking. Khi entity đã thay đổi kể từ lần đọc, SDN báo `OptimisticLockingFailureException`; ứng dụng cần đọc lại, hợp nhất hoặc trả conflict thay vì ghi lại object cũ. Custom Cypher không tự động áp dụng version check, nên phải tự kiểm tra và tăng version nếu muốn giữ cùng quy tắc.

Constraint như `IS UNIQUE`, property existence hoặc node key được Neo4j thực thi ở cấp database. Constraint violation là lỗi dữ liệu theo schema, không phải lỗi version và thường không thể giải quyết bằng retry nguyên payload. Deadlock xảy ra khi transaction cạnh tranh lock theo thứ tự xung đột; Neo4j phát hiện và hủy một transaction. Hãy rút ngắn transaction, cập nhật tài nguyên theo thứ tự ổn định và chỉ retry lỗi transient đã xác minh bằng một transaction mới, có backoff, giới hạn và idempotency. Phân loại đúng ba nhóm lỗi giúp bảo vệ dữ liệu đồng thời và tránh biến một lỗi nghiệp vụ thành vòng retry vô hạn.

## Tài liệu tham khảo

- [Spring Data Neo4j – Optimistic locking](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html#mapping-optimistic-locking)
- [Neo4j Operations Manual – Locking](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Operations Manual – Deadlocks](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/#deadlocks)
- [Neo4j Cypher Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Java Driver – Error handling](https://neo4j.com/docs/java-manual/current/query-simple/#_error_handling)
