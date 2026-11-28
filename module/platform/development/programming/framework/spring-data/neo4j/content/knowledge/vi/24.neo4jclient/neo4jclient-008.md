# Chọn database cho một thao tác client

## Mục tiêu

Sau bài học này, bạn có thể:

- Chọn database đích cho một câu query cụ thể bằng Neo4jClient.
- Phân biệt database selection với tham số Cypher dùng để lọc property.
- Dùng cùng một client để chạy các query trên những database khác nhau.
- Áp dụng lựa chọn database cho thao tác đọc, ghi và luồng reactive.
- Quản lý tên database đầu vào bằng danh sách cho phép.
- Hiểu mối liên hệ giữa database selection, transaction và DatabaseSelectionProvider.

## 1. Vì sao một ứng dụng cần chọn database theo từng thao tác?

Neo4j hỗ trợ nhiều database trên cùng một DBMS. Một ứng dụng có thể dùng database riêng cho từng tenant, tách dữ liệu vận hành và lưu trữ, hoặc đọc dữ liệu từ một database danh mục dùng chung.

Ví dụ một nền tảng có ba database:

| Database | Dữ liệu |
|---|---|
| tenant_north | Người dùng và đơn hàng của tenant phía Bắc |
| tenant_south | Người dùng và đơn hàng của tenant phía Nam |
| catalog | Danh mục sản phẩm dùng chung |

Nếu mọi query đều sử dụng database mặc định, ứng dụng không thể chủ động chọn nơi đọc hoặc ghi theo tenant hay mục đích nghiệp vụ.

Spring Data Neo4j cung cấp Neo4jClient để chạy Cypher trực tiếp. Fluent API của client cho phép gắn một query với database đích bằng phương thức **in(String databaseName)**.

Điểm quan trọng: database được chọn cho một query là thông tin ở cấp client/session. Nó khác với tham số Cypher như **$personId**, **$city** hoặc **$status**, vốn chỉ cung cấp giá trị cho điều kiện truy vấn.

## 2. Cách dùng in(databaseName)

Luồng cơ bản:

1. Gọi **client.query(...)** để khai báo Cypher.
2. Gọi **in(databaseName)** để chọn database cho query đó.
3. Bind các tham số Cypher nếu cần.
4. Gọi **fetch()** để đọc kết quả hoặc **run()** để thực thi query không cần record trả về.

Ví dụ:

~~~java
Collection<Map<String, Object>> people = client
    .query("""
        MATCH (p:Person)
        RETURN p.personId AS personId, p.fullName AS fullName
        ORDER BY p.fullName
        """)
    .in("tenant_north")
    .fetch()
    .all();
~~~

Trong ví dụ:

- **query(...)** tạo một query tìm Person.
- **in("tenant_north")** chọn database tenant_north.
- **fetch().all()** lấy tất cả record.
- Client imperative trả về Collection của Map, mỗi Map tương ứng một record Cypher.

Phương thức **in(...)** được gọi sau khi khai báo query và trước bước thực thi. Một query chỉ được gắn với một database đích. API chuyển sang kiểu query specification đã gắn database, vì vậy không dùng **in(...)** lần nữa để đổi database cho cùng query.

### Không gọi in khi muốn dùng database mặc định

Nếu không chỉ định database, client sử dụng database mặc định theo cấu hình và ngữ cảnh kết nối:

~~~java
Collection<Map<String, Object>> people = client
    .query("MATCH (p:Person) RETURN p")
    .fetch()
    .all();
~~~

Có thể truyền **null** vào **in(null)** để chọn database mặc định:

~~~java
Collection<Map<String, Object>> people = client
    .query("MATCH (p:Person) RETURN p")
    .in(null)
    .fetch()
    .all();
~~~

Không truyền chuỗi rỗng **""**; tên database rỗng không hợp lệ. Khi muốn dùng database mặc định, cách rõ ràng nhất thường là bỏ qua **in(...)**.

Nếu biết database đích, chỉ định tên rõ ràng giúp driver tránh phải hỏi máy chủ để xác định home database trong một số cấu hình kết nối.

## 3. Truyền tham số Cypher độc lập với database

Tên database không phải tham số property trong Cypher. Không viết query kiểu **MATCH (p:Person) WHERE p.database = $database** để lựa chọn database vật lý. Điều kiện đó chỉ lọc một property tên database nếu dữ liệu có property như vậy.

Ví dụ một service chọn database theo tenant và tìm Person theo thành phố:

~~~java
import java.util.Collection;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

@Service
public class TenantPeopleReader {

    private final Neo4jClient client;

    public TenantPeopleReader(Neo4jClient client) {
        this.client = client;
    }

    public Collection<Map<String, Object>> findPeople(
            String databaseName,
            String city
    ) {
        return client.query("""
                MATCH (p:Person)
                WHERE p.city = $city
                RETURN p.personId AS personId,
                       p.fullName AS fullName
                ORDER BY p.fullName
                """)
            .in(databaseName)
            .bind(city).to("city")
            .fetch()
            .all();
    }
}
~~~

Ở đây có hai loại đầu vào riêng biệt:

| Giá trị | Cách truyền | Vai trò |
|---|---|---|
| databaseName | **.in(databaseName)** | Chọn database thực thi query |
| city | **.bind(city).to("city")** | Tham số Cypher dùng trong điều kiện WHERE |

Tách riêng hai khái niệm này giúp query an toàn và dễ đọc. Không ghép tên database hoặc giá trị người dùng trực tiếp vào chuỗi Cypher.

## 4. Chọn database theo tenant một cách có kiểm soát

Trong ứng dụng nhiều tenant, request có thể mang tenant key. Không nên chuyển thẳng một chuỗi tùy ý từ request thành database name. Hãy tra tenant key qua cấu hình hoặc registry đáng tin cậy.

Ví dụ dùng danh sách cho phép:

~~~java
private static final Map<String, String> TENANT_DATABASES = Map.of(
    "north", "tenant_north",
    "south", "tenant_south"
);

private String resolveDatabase(String tenantKey) {
    String databaseName = TENANT_DATABASES.get(tenantKey);

    if (databaseName == null) {
        throw new IllegalArgumentException("Unknown tenant");
    }

    return databaseName;
}
~~~

Sau đó:

~~~java
public Collection<Map<String, Object>> findPeople(
        String tenantKey,
        String city
) {
    String databaseName = resolveDatabase(tenantKey);

    return client.query("""
            MATCH (p:Person)
            WHERE p.city = $city
            RETURN p.personId AS personId, p.fullName AS fullName
            """)
        .in(databaseName)
        .bind(city).to("city")
        .fetch()
        .all();
}
~~~

Cách làm này có ba lợi ích:

- Người gọi chỉ chọn tenant key mà ứng dụng công nhận.
- Tên database được quản lý ở một nơi.
- Ứng dụng có thể kiểm tra quyền truy cập tenant trước khi chạy query.

**Neo4jClient.verifyDatabaseName(...)** có thể giúp kiểm tra và chuẩn hóa định dạng tên database theo yêu cầu của driver. Tuy nhiên, kiểm tra định dạng không chứng minh database đã tồn tại hoặc tài khoản kết nối có quyền truy cập. Ứng dụng vẫn phải kiểm tra tenant và quyền truy cập theo quy tắc của mình.

## 5. Dùng cùng một Neo4jClient cho nhiều database

Không cần tạo một Neo4jClient mới cho từng database. Có thể dùng cùng client bean và chọn database trên từng query:

~~~java
Collection<Map<String, Object>> northPeople = client
    .query("MATCH (p:Person) RETURN p.personId AS id")
    .in("tenant_north")
    .fetch()
    .all();

Collection<Map<String, Object>> southPeople = client
    .query("MATCH (p:Person) RETURN p.personId AS id")
    .in("tenant_south")
    .fetch()
    .all();

Collection<Map<String, Object>> products = client
    .query("MATCH (p:Product) RETURN p.sku AS sku")
    .in("catalog")
    .fetch()
    .all();
~~~

Mỗi chuỗi gọi **query(...).in(...).fetch()** là một thao tác độc lập với database được chỉ định trong thao tác đó. Việc chọn tenant_north không thay đổi database mặc định của Neo4jClient và cũng không làm các query tiếp theo tự động chuyển sang tenant_north.

Đây là cách phù hợp khi một service cần đọc dữ liệu tenant và danh mục chung bằng cùng một kết nối Driver.

## 6. Chọn database cho thao tác ghi

**in(...)** áp dụng cho cả query đọc và query ghi. Ví dụ cập nhật thông tin Person trong database của tenant:

~~~java
import org.neo4j.driver.ResultSummary;

public ResultSummary renamePerson(
        String databaseName,
        String personId,
        String newName
) {
    return client.query("""
            MATCH (p:Person {personId: $personId})
            SET p.fullName = $newName
            """)
        .in(databaseName)
        .bind(personId).to("personId")
        .bind(newName).to("newName")
        .run();
}
~~~

**run()** thực thi query và trả về **ResultSummary**, phù hợp với thao tác không cần đọc record. Summary có thể cung cấp counters để biết có bao nhiêu node, relationship hoặc property đã bị thay đổi.

Chú ý chọn đúng database trước khi chạy lệnh ghi. Nếu chọn nhầm database, câu Cypher vẫn có thể hợp lệ nhưng dữ liệu sẽ được cập nhật ở nơi khác với mong muốn.

## 7. Chọn database với ReactiveNeo4jClient

SDN có hai API client:

- **Neo4jClient** cho luồng imperative.
- **ReactiveNeo4jClient** cho luồng reactive.

Cả hai có fluent API tương tự để khai báo query, bind tham số và chọn database. Tuy nhiên, hai interface không tương thích trực tiếp với nhau.

Ví dụ reactive:

~~~java
Flux<Map<String, Object>> people = reactiveClient
    .query("""
        MATCH (p:Person)
        WHERE p.city = $city
        RETURN p.personId AS personId, p.fullName AS fullName
        """)
    .in("tenant_north")
    .bind("Ha Noi").to("city")
    .fetch()
    .all();
~~~

Điểm khác biệt là reactive query chỉ thực sự tương tác với database khi publisher được subscribe. Vì vậy, việc tạo biến Flux chưa có nghĩa dữ liệu đã được lấy.

Không gọi block hoặc subscribe tùy tiện bên trong một luồng reactive đang được quản lý. Hãy trả publisher về tầng gọi hoặc kết hợp nó với pipeline reactive của ứng dụng.

## 8. Quan hệ giữa database selection và transaction

Neo4jClient được thiết kế để tham gia transaction do Spring quản lý. Khi dùng **@Transactional**, cần lưu ý:

- Client phải dùng cùng instance Driver với Neo4jTransactionManager để có thể đồng bộ với transaction đang mở.
- Transaction được mở cho một database cụ thể; không coi **in(...)** là thao tác chuyển một transaction đang chạy sang database khác.
- Nếu service dùng database theo tenant, hãy bảo đảm database được chọn cho query nhất quán với database mà transaction manager đã chọn.
- Nếu một nghiệp vụ cần thao tác trên nhiều database, hãy thiết kế ranh giới transaction và xử lý nhất quán riêng cho từng database; không giả định một transaction Neo4j thông thường sẽ bao trùm tất cả database.

Ví dụ service đọc dữ liệu trong transaction:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)
public Collection<Map<String, Object>> findTenantPeople(
        String databaseName,
        String city
) {
    return client.query("""
            MATCH (p:Person)
            WHERE p.city = $city
            RETURN p.personId AS personId, p.fullName AS fullName
            """)
        .in(databaseName)
        .bind(city).to("city")
        .fetch()
        .all();
}
~~~

Ví dụ này giả định transaction được cấu hình để làm việc với chính databaseName đó. Với hệ thống tenant, việc xác định database nên diễn ra trước khi mở transaction và được truyền nhất quán qua service/repository.

Nếu ứng dụng dùng Spring Boot starter, thường nên inject bean Neo4jClient do starter cung cấp. Không tạo Driver mới cho từng query; việc tạo client với Driver khác có thể làm mất khả năng tham gia transaction hiện có.

## 9. Phân biệt in(...) với DatabaseSelectionProvider

Hai cơ chế đều liên quan đến database selection nhưng phục vụ phạm vi khác nhau:

| Cơ chế | Phạm vi | Khi nên dùng |
|---|---|---|
| **Neo4jClient.query(...).in(databaseName)** | Một query cụ thể của client | Một thao tác cần chọn database đích rõ ràng |
| **DatabaseSelectionProvider** | Lựa chọn database mặc định cho repository/template và cho client nếu được cấu hình provider | Ứng dụng muốn SDN chọn database theo ngữ cảnh cho nhiều thao tác |
| Không chỉ định database | Database mặc định theo cấu hình client/driver và server | Ứng dụng chỉ dùng database mặc định |

**DatabaseSelectionProvider** có thể trả về database cố định hoặc chọn database theo ngữ cảnh. Với repository và template, provider được hỏi trước mỗi lần tương tác với server; client cũng có thể được cấu hình với provider làm lựa chọn mặc định. Nếu ngữ cảnh thay đổi không nhất quán, ứng dụng có thể đọc thiếu dữ liệu hoặc ghi vào database ngoài ý muốn.

Khi chỉ cần chọn database cho một query Neo4jClient, **in(...)** thể hiện ý định ngay tại nơi thực thi và dễ kiểm tra hơn.

## 10. Không dùng USE thay cho lựa chọn database của client

Có thể gặp cú pháp Cypher:

~~~cypher
USE tenant_north
MATCH (p:Person)
RETURN p
~~~

Tuy nhiên, khi dùng Neo4jClient, hãy ưu tiên chọn database bằng **.in("tenant_north")**. Database selection ở client/session giúp driver định tuyến đến database đích. Trong môi trường cluster, dùng USE có thể yêu cầu server-side routing và khiến truy vấn phải được định tuyến lại.

Ngoài ra, tên database là thành phần chọn session, không phải một giá trị property để bind bằng **$database**. Hãy giữ tên database ngoài chuỗi Cypher và chọn nó qua API client.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Query chạy trên database không mong muốn | Bỏ qua in(...) và client dùng database mặc định | Chỉ định database rõ ràng cho query |
| Query không thể chọn database | Truyền chuỗi rỗng | Dùng tên hợp lệ hoặc bỏ qua in(...) để dùng mặc định |
| Không tìm thấy dữ liệu | Chọn nhầm database hoặc tenant key ánh xạ sai | Kiểm tra tenant registry và database đích |
| Không thể truy cập database | Database không tồn tại hoặc tài khoản thiếu quyền | Kiểm tra database và quyền của tài khoản kết nối |
| Dùng in(...) hai lần | Cố đổi database sau khi query đã được gắn database | Tạo query specification mới cho database khác |
| Query có $database nhưng không chuyển database | Dùng tham số Cypher như thể đó là session database | Gọi .in(databaseName) |
| Transaction không tham gia như mong đợi | Client dùng Driver khác hoặc database không khớp transaction | Dùng chung Driver và đồng bộ database selection |
| Reactive query chưa chạy | Publisher chưa được subscribe | Kết hợp publisher vào pipeline reactive |
| Dữ liệu tenant bị lẫn | Lấy database name trực tiếp từ request mà không kiểm tra | Dùng tenant registry/allowlist và kiểm tra quyền |

## 12. Bài tập thực hành

Giả sử DBMS có hai database **tenant_north** và **tenant_south**. Mỗi database có các node Person với property personId, fullName và city.

Thực hiện:

1. Inject một Neo4jClient vào service.
2. Viết query tìm Person theo city và chọn tenant_north bằng in(...).
3. Thực hiện cùng query trên tenant_south.
4. So sánh kết quả và giải thích vì sao cùng câu Cypher có thể trả dữ liệu khác nhau.
5. Bind city bằng .bind(city).to("city"); không ghép giá trị vào chuỗi query.
6. Viết query cập nhật fullName và gọi .run() trên database được chọn.
7. Thử bỏ in(...) để quan sát database mặc định.
8. Thử truyền tên database không hợp lệ và quan sát lỗi.
9. Tạo tenant registry để chỉ cho phép tenant key đã biết.
10. Nếu dùng @Transactional, xác định database mà transaction manager chọn và bảo đảm client query sử dụng cùng database.

Câu hỏi tự kiểm tra:

- in(databaseName) được gọi ở giai đoạn nào của fluent API?
- Vì sao tên database không thể bind như một property parameter?
- Điều gì xảy ra nếu bỏ qua in(...)?
- Có thể dùng cùng một Neo4jClient cho nhiều database không?
- DatabaseSelectionProvider khác in(...) ở phạm vi nào?
- Vì sao không nên lấy trực tiếp tên database từ request?
- Một transaction đang mở có thể được chuyển database chỉ bằng cách gọi in(...) hay không?

## Kết luận

Để chọn database cho một thao tác Neo4jClient, khai báo query rồi gọi .in(databaseName) trước khi bind tham số và thực thi. Nếu không chỉ định database, client dùng lựa chọn mặc định; in(null) cũng chọn mặc định, còn chuỗi rỗng không hợp lệ.

Hãy dùng tenant registry hoặc allowlist để ánh xạ tenant key sang database được phép truy cập. Giữ tên database tách khỏi tham số Cypher, dùng cùng Driver với transaction manager, và bảo đảm query trong một transaction nhắm đến database phù hợp. Nếu cần lựa chọn database mặc định cho nhiều thao tác repository hoặc template, hãy tìm hiểu DatabaseSelectionProvider; còn với một query client riêng lẻ, in(...) là cách trực tiếp và rõ ràng.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2: Neo4jClient — Selecting the target database](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Data Neo4j API: Neo4jClient.UnboundRunnableSpec.in](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/Neo4jClient.UnboundRunnableSpec.html)
- [Spring Data Neo4j API: DatabaseSelectionProvider](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/core/DatabaseSelectionProvider.html)
- [Neo4j Java Driver Manual: Session configuration and database selection](https://neo4j.com/docs/java-manual/current/transactions/)
