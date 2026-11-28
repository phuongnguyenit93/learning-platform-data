# readOnly và ảnh hưởng đến định tuyến truy vấn đọc–ghi

Trong Spring Data Neo4j (SDN), thuộc tính `readOnly` của `@Transactional` mô tả chế độ truy cập mà transaction cần sử dụng. Với transaction đồng bộ, `@Transactional(readOnly = true)` cho Spring biết công việc hiện tại chỉ đọc dữ liệu. Neo4j transaction manager sử dụng thông tin này để mở transaction ở access mode đọc; khi kết nối dùng routing driver, access mode có thể ảnh hưởng đến máy chủ Neo4j được chọn để thực thi truy vấn.

Điểm quan trọng là định tuyến đọc–ghi diễn ra ở cấp transaction và phụ thuộc vào cấu hình driver cùng topology Neo4j. `readOnly` không phải một bộ phân tích Cypher tự động nhìn từng câu lệnh để quyết định chuyển câu đọc sang reader và câu ghi sang writer. Ứng dụng cần khai báo đúng ranh giới giao dịch để toàn bộ thao tác trong transaction có cùng chế độ truy cập.

## 1. Access mode đọc và ghi trong Neo4j

Neo4j Java Driver có hai access mode chính:

- `AccessMode.READ`: transaction được khai báo là chỉ đọc.
- `AccessMode.WRITE`: transaction có thể thực hiện thao tác ghi.

Trong môi trường Neo4j đơn lẻ, hai chế độ vẫn mô tả ý định truy cập của transaction, nhưng không có cụm máy chủ để phân phối truy vấn giữa các vai trò. Trong cụm Neo4j có routing, driver sử dụng access mode cùng routing table để chọn máy chủ phù hợp.

Ở mức khái niệm:

| Loại transaction | Access mode | Đích thực thi trong cụm có routing |
|---|---|---|
| Transaction chỉ đọc | `READ` | Máy chủ có vai trò phục vụ đọc theo routing table |
| Transaction đọc–ghi | `WRITE` | Máy chủ có vai trò nhận ghi, thường là primary/leader của database |

Tên vai trò cụ thể và cách routing table được phân phối phụ thuộc phiên bản Neo4j và topology cụm. Ứng dụng nên để driver xử lý routing thay vì tự chọn địa chỉ một máy chủ reader hoặc writer.

## 2. `readOnly = true` được SDN sử dụng như thế nào?

Khi một phương thức imperative được gọi qua Spring transaction proxy, transaction manager nhận transaction definition từ `@Transactional`. Với `readOnly = true`, Neo4j transaction manager mở transaction có access mode đọc. Các thao tác SDN tham gia transaction đó sẽ dùng session/transaction đã gắn với access mode đọc.

Ví dụ một service chỉ đọc:

~~~java
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonQueryService {

    private final PersonRepository people;

    public PersonQueryService(PersonRepository people) {
        this.people = people;
    }

    @Transactional(readOnly = true)
    public Optional<Person> findByPersonKey(String personKey) {
        return people.findByPersonKey(personKey);
    }
}
~~~

Transaction bắt đầu khi lời gọi đi qua proxy. SDN mở transaction đọc, repository thực hiện truy vấn trong transaction đó, rồi transaction được đóng khi phương thức kết thúc. Nếu cấu hình dùng routing driver và cụm có các máy chủ phục vụ đọc, access mode `READ` cho phép driver định tuyến transaction tới đích đọc phù hợp.

Không có `@Transactional(readOnly = true)`, transaction manager không nhận được chỉ thị đọc từ annotation này. Với transaction mặc định, access mode thường là ghi để bảo đảm có thể thực hiện các thao tác cập nhật.

## 3. Cấu hình URI để driver hỗ trợ routing

Muốn driver định tuyến trong cụm Neo4j, ứng dụng cần dùng URI routing phù hợp, thường là scheme `neo4j://` hoặc scheme bảo mật tương ứng. Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  neo4j:
    uri: neo4j://neo4j-router.example.com:7687
    authentication:
      username: neo4j
      password: secret-from-environment
    database: neo4j
~~~

`neo4j://` yêu cầu driver sử dụng cơ chế routing và lấy routing table từ cụm. Địa chỉ ban đầu có thể là một router hoặc điểm vào cụm; driver khám phá các địa chỉ được phép phục vụ đọc và ghi.

Phân biệt với kết nối trực tiếp:

| URI scheme | Cách kết nối | Ý nghĩa đối với read/write routing |
|---|---|---|
| `neo4j://` | Routing driver | Có thể chọn đích đọc hoặc ghi dựa trên access mode |
| `bolt://` | Kết nối Bolt trực tiếp tới một endpoint | Không có cơ chế routing cụm của driver |
| `neo4j+s://` | Routing driver với TLS và xác minh chứng chỉ | Routing tương tự `neo4j://`, có bảo mật TLS |
| `neo4j+ssc://` | Routing driver với TLS dùng chứng chỉ tự ký theo cấu hình driver | Chỉ dùng khi chính sách bảo mật môi trường cho phép |
| `bolt+s://` | Kết nối trực tiếp Bolt có TLS | Kết nối bảo mật trực tiếp, không phải routing driver |

Nếu dùng `bolt://` để kết nối thẳng tới một máy chủ, `readOnly = true` vẫn mô tả access mode của transaction nhưng không thể khiến driver tự tìm một máy chủ đọc khác. Muốn có read/write routing giữa các thành viên cụm, cần cấu hình routing URI và topology hỗ trợ.

Không cấu hình ứng dụng bằng địa chỉ của một reader cụ thể rồi kỳ vọng driver tự chuyển sang writer khi cần ghi. Hãy dùng điểm vào routing của cụm và để driver theo routing table.

## 4. Transaction đọc và transaction ghi ở tầng service

Một cách tổ chức rõ ràng là phân biệt service method chỉ đọc với service method thay đổi graph:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional(readOnly = true)
    public PersonView getProfile(String personKey) {
        Person person = people.findByPersonKey(personKey)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));

        return new PersonView(person.getPersonKey(), person.getName());
    }

    @Transactional
    public void rename(String personKey, String newName) {
        Person person = people.findByPersonKey(personKey)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));

        person.rename(newName);
        people.save(person);
    }
}
~~~

Trong ví dụ:

- `getProfile` dùng transaction đọc.
- `rename` dùng transaction mặc định có quyền ghi.
- Các thao tác repository được gọi bên trong method tham gia transaction của service.

Đặt ranh giới ở service giúp một use case có nhiều lần đọc và ghi vẫn dùng đúng transaction. Ví dụ, khi cập nhật một node cùng relationship liên quan, toàn bộ thao tác cần ghi nên nằm trong một transaction ghi để cùng commit hoặc rollback.

## 5. Access mode được chọn khi transaction bắt đầu

Access mode được xác định khi transaction được mở. Các câu lệnh chạy trong cùng transaction dùng chung access mode. Vì vậy, nếu transaction bắt đầu ở chế độ đọc thì một câu lệnh ghi xuất hiện sau đó không làm transaction tự động chuyển sang writer.

Ví dụ không phù hợp:

~~~java
@Transactional(readOnly = true)
public void loadThenUpdate(String personKey, String newName) {
    Person person = people.findByPersonKey(personKey)
        .orElseThrow();

    person.rename(newName);
    people.save(person);
}
~~~

Phương thức này khai báo transaction chỉ đọc nhưng lại gọi `save`. Trong cấu hình SDN/driver sử dụng read access mode, thao tác ghi không phù hợp với transaction và có thể bị server từ chối. Driver không tự tách riêng câu lệnh ghi để gửi tới writer.

Hãy bỏ `readOnly = true` nếu use case có ghi:

~~~java
@Transactional
public void loadThenUpdate(String personKey, String newName) {
    Person person = people.findByPersonKey(personKey)
        .orElseThrow();

    person.rename(newName);
    people.save(person);
}
~~~

Nếu một use case thật sự cần đọc từ reader rồi ghi trên writer, hãy thiết kế thành các transaction riêng với ranh giới rõ ràng và cân nhắc yêu cầu nhất quán dữ liệu. Không cố chuyển access mode ở giữa một transaction đang hoạt động.

## 6. `readOnly` ở class và method

Có thể đặt `@Transactional(readOnly = true)` ở cấp class để mặc định các method là đọc:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CatalogService {

    public CatalogView findCatalog(String code) {
        // Truy vấn đọc.
        return loadCatalog(code);
    }

    @Transactional
    public void renameCatalog(String code, String newName) {
        // Method này cần transaction ghi khi được gọi độc lập qua proxy.
        updateCatalog(code, newName);
    }
}
~~~

Annotation ở method ghi đè metadata ở cấp class cho lời gọi đó. Tuy nhiên, điều này chỉ giúp method mở transaction ghi khi nó thực sự bắt đầu một transaction mới qua proxy. Nếu method ghi được gọi từ bên trong một transaction đọc đang hoạt động và propagation là `REQUIRED`, nó sẽ tham gia transaction đọc hiện tại; annotation bên trong không thể đổi access mode của transaction đã mở.

Nếu một bước thực sự cần transaction độc lập, `REQUIRES_NEW` có thể tạm ngưng transaction bên ngoài và mở transaction mới. Chỉ dùng cách này khi việc commit độc lập là đúng nghiệp vụ; nó không còn bảo đảm toàn bộ use case cùng rollback.

## 7. Custom query và Neo4jClient cũng phải theo transaction

`@Transactional(readOnly = true)` có tác dụng khi truy vấn được thực thi trong transaction do Spring quản lý. Cả repository method, `Neo4jTemplate` và `Neo4jClient` được cấu hình để tham gia transaction SDN đều có thể dùng cùng access mode.

Ví dụ custom query đọc bằng `Neo4jClient`:

~~~java
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class PersonReadRepository {

    private final Neo4jClient neo4jClient;

    public PersonReadRepository(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional(readOnly = true)
    public List<String> findActiveNames() {
        return neo4jClient.query("""
                MATCH (p:Person)
                WHERE p.active = true
                RETURN p.name AS name
                ORDER BY p.name
                """)
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) -> record.get("name").asString())
            .all();
    }
}
~~~

Không tự mở một `Driver` session hoặc transaction khác bên trong method này nếu mong muốn truy vấn dùng access mode đọc của Spring. Một session tự tạo độc lập không tự tham gia transaction gắn với thread hiện tại.

Với repository query method tự khai báo, đừng giả định tất cả đều tự có transaction chỉ vì repository kế thừa `Neo4jRepository`. Hãy đặt transaction ở service hoặc khai báo rõ trên method cần một ranh giới giao dịch cụ thể.

## 8. `readOnly` không thay thế quyền bảo mật

`readOnly = true` là thông tin về ý định truy cập của transaction và là đầu vào cho access mode/routing. Không dùng nó như cơ chế phân quyền người dùng:

- Không thay thế tài khoản Neo4j chỉ có quyền đọc.
- Không thay thế kiểm tra authorization ở tầng service.
- Không đảm bảo mọi đường truy cập khác trong ứng dụng đều không thể ghi.
- Không ngăn một ứng dụng khác có thông tin xác thực ghi truy cập database.

Nếu một thành phần chỉ được phép đọc, hãy cấp cho nó tài khoản hoặc role Neo4j có quyền phù hợp. Có thể kết hợp quyền database với `readOnly = true`: quyền database là lớp bảo vệ, còn transaction read-only giúp ứng dụng định tuyến và thể hiện đúng ý định truy cập.

## 9. Nhất quán khi đọc sau khi ghi

Trong cụm Neo4j, một transaction đọc có thể được định tuyến tới máy chủ phục vụ đọc. Nếu ứng dụng vừa ghi rồi ngay lập tức đọc lại, hãy bảo đảm thao tác đọc có quan hệ nhân quả với lần ghi trước.

Driver và SDN có cơ chế bookmark để duy trì causal consistency giữa các transaction khi dùng đúng cấu hình và cùng luồng quản lý bookmark. Bookmark cho biết transaction đọc cần quan sát ít nhất những thay đổi đã được xác nhận trước đó. Không tự ý tạo session/driver độc lập rồi bỏ qua bookmark nếu use case cần đọc ngay dữ liệu vừa ghi.

Nếu hệ thống có nhiều instance hoặc nhiều service cùng truy cập graph, hãy xác định rõ cách chia sẻ bookmark và transaction context theo kiến trúc triển khai. Không giả định mọi truy vấn đọc từ reader bất kỳ đều tự thấy một lần ghi vừa hoàn tất nếu luồng causal consistency không được duy trì.

## 10. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `readOnly = true` cho method có `save` | Transaction mở ở access mode đọc có thể từ chối thao tác ghi | Đánh dấu method ghi bằng transaction có quyền ghi |
| Nghĩ driver tự phân loại từng câu Cypher | Query ghi trong transaction đọc không tự chuyển sang writer | Chọn access mode đúng ở ranh giới transaction |
| Dùng `bolt://` nhưng kỳ vọng routing cụm | Kết nối trực tiếp không khám phá reader/writer | Dùng routing URI `neo4j://` hoặc scheme bảo mật tương ứng |
| Đặt `readOnly = true` ở class rồi gọi method ghi trong transaction đọc bên ngoài | Method ghi tham gia transaction đã mở, không đổi access mode | Bắt đầu use case ghi bằng transaction ghi; chỉ dùng `REQUIRES_NEW` khi cần commit độc lập |
| Dùng `readOnly` như quyền bảo mật | Các đường truy cập khác vẫn có thể ghi | Dùng database role và authorization |
| Tự mở session driver trong method transactional | Session riêng không tự tham gia transaction Spring | Dùng client/template được SDN quản lý hoặc tích hợp transaction rõ ràng |
| Đọc ngay sau ghi nhưng bỏ qua bookmark | Reader có thể chưa quan sát thay đổi theo yêu cầu causal | Duy trì bookmark/causal consistency trong luồng truy cập |
| Cho rằng `readOnly` luôn chọn một server khác | Single instance hoặc direct Bolt không có lựa chọn routing | Kiểm tra URI và topology trước khi kỳ vọng read/write splitting |

## 11. Quy trình kiểm tra định tuyến đọc–ghi

1. Xác định môi trường là một Neo4j server đơn lẻ hay cụm có routing.
2. Kiểm tra URI: dùng routing scheme nếu muốn driver chọn đích đọc/ghi từ routing table.
3. Đặt `@Transactional(readOnly = true)` cho use case chỉ đọc và transaction mặc định cho use case có ghi.
4. Bảo đảm repository, `Neo4jTemplate` và `Neo4jClient` tham gia cùng transaction manager SDN.
5. Kiểm tra method ghi không bị gọi bên trong transaction đọc hiện có với propagation `REQUIRED`.
6. Kiểm tra routing table, server role và log driver trong môi trường cụm để xác nhận đích thực thi.
7. Kiểm thử trường hợp đọc, ghi và đọc sau ghi; xác nhận causal consistency nếu cần.
8. Dùng database privilege để bảo vệ quyền đọc/ghi thay vì dựa riêng vào annotation.

## 12. Tự kiểm tra

1. `readOnly = true` ảnh hưởng tới access mode của Neo4j transaction như thế nào?
2. Vì sao access mode được chọn ở cấp transaction thay vì tự thay đổi theo từng câu Cypher?
3. Khác biệt giữa `neo4j://` và `bolt://` đối với routing là gì?
4. Điều gì xảy ra nếu một method `readOnly = true` gọi `repository.save(...)`?
5. Vì sao method ghi có `@Transactional` vẫn có thể tham gia transaction đọc của caller?
6. `readOnly` có thay thế quyền database chỉ đọc không?
7. Bookmark giúp ích gì khi đọc từ reader sau khi một transaction ghi đã commit?

`readOnly` giúp SDN truyền đúng ý định truy cập vào Neo4j transaction manager. Khi kết hợp với routing driver và cụm Neo4j, access mode đọc/ghi cho phép driver chọn đích phù hợp. Hãy thiết kế transaction theo use case, dùng routing URI khi cần phân phối đọc–ghi và bảo đảm các thao tác ghi không tham gia nhầm một transaction chỉ đọc.
