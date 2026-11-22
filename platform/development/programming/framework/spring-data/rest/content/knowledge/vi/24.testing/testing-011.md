# Kiểm tra ETag khi hai máy khách cập nhật đồng thời

## Mục tiêu

Bài thực hành này kiểm chứng rằng hai máy khách có thể cùng đọc một tài nguyên Spring Data REST, nhưng máy khách dùng dữ liệu cũ không thể ghi đè thay đổi mới hơn của máy khách còn lại. Cơ chế sử dụng ETag trong response và điều kiện If-Match trong request ghi.

Sau bài này, người học có thể:

- Giải thích ETag và optimistic locking ở mức HTTP.
- Cấu hình trường phiên bản cho entity được Spring Data REST xuất bản.
- Mô phỏng hai máy khách đọc cùng một phiên bản rồi cập nhật theo thứ tự.
- Xác nhận request dùng ETag cũ bị từ chối bằng HTTP 412 Precondition Failed.
- Xử lý xung đột bằng cách tải trạng thái mới, đối chiếu và gửi lại thay đổi đã hợp nhất.

## 1. Cơ chế ETag và cập nhật có điều kiện

ETag (Entity Tag) là một mã định danh đại diện cho một phiên bản của tài nguyên HTTP. Server trả ETag trong response, thường dưới dạng chuỗi có dấu ngoặc kép, ví dụ:

~~~http
HTTP/1.1 200 OK
ETag: "0"
Content-Type: application/hal+json
~~~

Client lưu nguyên giá trị header này cùng URI của tài nguyên. Khi muốn thay đổi tài nguyên, client gửi lại giá trị đó trong header If-Match:

~~~http
If-Match: "0"
~~~

Server chỉ thực hiện PUT, PATCH hoặc DELETE nếu ETag hiện tại của tài nguyên khớp với If-Match. Nếu tài nguyên đã được cập nhật và ETag đã thay đổi, điều kiện không còn đúng; Spring Data REST trả về HTTP 412 Precondition Failed. Request bị từ chối để tránh ghi đè thay đổi mà client chưa đọc.

ETag không phải khóa bi quan và không giữ tài nguyên trong trạng thái khóa khi client đang chỉnh sửa. Đây là cơ chế kiểm tra phiên bản tại thời điểm ghi, thường được gọi là optimistic concurrency control.

### Vai trò của @Version

Spring Data REST lấy thông tin phiên bản từ metadata của datastore. Với entity JPA, đánh dấu thuộc tính phiên bản bằng jakarta.persistence.Version. Với các module Spring Data khác, dùng org.springframework.data.annotation.Version khi datastore tương ứng hỗ trợ cơ chế này.

Ví dụ entity JPA tối giản:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Item {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private String name;

    protected Item() {
    }

    public Item(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Repository có thể được Spring Data REST xuất bản trực tiếp:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ItemRepository extends JpaRepository<Item, Long> {
}
~~~

Với cấu hình mặc định, tài nguyên item có URI dạng /items/{id}. Tên collection và URI có thể thay đổi nếu repository được cấu hình bằng @RepositoryRestResource hoặc ứng dụng đặt base path riêng.

Khi tạo hoặc cập nhật entity, persistence provider quản lý thuộc tính version. Không để client tự tăng version và không dùng giá trị version trong JSON làm điều kiện ghi thay cho ETag. Client cần lưu đúng giá trị header ETag mà server đã trả về.

## 2. Diễn tiến khi hai máy khách cùng chỉnh sửa

Giả sử tài nguyên /items/1 đang có ETag là "0". Máy khách A và máy khách B đều đọc tài nguyên trước khi có lần ghi nào xảy ra.

~~~mermaid
sequenceDiagram
    participant A as Máy khách A
    participant B as Máy khách B
    participant S as Spring Data REST

    A->>S: GET /items/1
    S-->>A: 200 OK, ETag "0"
    B->>S: GET /items/1
    S-->>B: 200 OK, ETag "0"
    Note over A,B: Cả hai đang sửa cùng một phiên bản
    A->>S: PATCH + If-Match "0"
    S-->>A: 2xx, tài nguyên được cập nhật
    Note over S: ETag chuyển sang phiên bản mới
    B->>S: PATCH + If-Match "0"
    S-->>B: 412 Precondition Failed
    B->>S: GET /items/1
    S-->>B: 200 OK, dữ liệu và ETag mới
    Note over B: Đối chiếu thay đổi rồi mới gửi lại
~~~

| Bước | Máy khách | Điều kiện và kết quả |
|---|---|---|
| 1 | A đọc tài nguyên | Nhận ETag hiện tại, ví dụ "0" |
| 2 | B đọc cùng tài nguyên | Cũng nhận ETag "0" |
| 3 | A cập nhật | Gửi If-Match: "0"; server chấp nhận và tạo phiên bản mới |
| 4 | B cập nhật | Vẫn gửi If-Match: "0"; server từ chối bằng 412 |
| 5 | B đồng bộ lại | GET tài nguyên, so sánh dữ liệu và ETag mới, sau đó quyết định cách hợp nhất |

Đây là một phép thử tái hiện xung đột đồng thời theo góc nhìn của người dùng: hai client cùng giữ một snapshot, nhưng một client đã ghi trước client kia. Không cần để hai request ghi chạy đúng cùng một mili giây mới kiểm tra được lỗi stale update.

## 3. Thực hành bằng HTTP và curl

Giả sử ứng dụng đang chạy tại http://localhost:8080 và tài nguyên cần thử là http://localhost:8080/items/1. Thay URI này bằng link item thực tế được phát hiện từ HAL hoặc cấu hình repository của ứng dụng.

### 3.1. Hai client cùng đọc

Mở hai terminal độc lập, đại diện cho client A và client B. Chạy GET ở cả hai terminal:

~~~bash
curl -i http://localhost:8080/items/1
~~~

Kiểm tra response của cả hai:

- Status là 200 OK.
- Response có header ETag.
- Hai client nhận cùng giá trị ETag nếu chưa có cập nhật xen giữa.
- Lưu nguyên giá trị header, gồm cả dấu ngoặc kép. Không tự bỏ dấu ngoặc kép, không tự tính ETag từ JSON và không giả định giá trị luôn là "0".

Ví dụ minh họa: cả A và B cùng nhận ETag: "0". Giá trị thực tế phụ thuộc trạng thái dữ liệu và datastore.

### 3.2. Client A cập nhật bằng ETag đã đọc

Client A gửi PATCH với ETag vừa nhận. Ví dụ dưới đây giả định giá trị ETag là "0" và entity có thuộc tính name:

~~~bash
curl -i -X PATCH http://localhost:8080/items/1 -H 'Accept: application/json' -H 'Content-Type: application/json' -H 'If-Match: "0"' -d '{"name":"Updated by A"}'
~~~

Thay "0" bằng đúng giá trị ETag đã nhận trong response GET. Với cấu hình Spring Data REST mặc định, request cập nhật thành công trả về 200 OK hoặc 204 No Content tùy cấu hình response body và header Accept. Response cập nhật có thể cung cấp ETag mới; có thể GET lại tài nguyên để xác nhận phiên bản mới.

### 3.3. Client B gửi bản cập nhật cũ

Client B vẫn giữ ETag cũ từ lần GET đầu tiên. Gửi một thay đổi khác nhưng giữ nguyên If-Match:

~~~bash
curl -i -X PATCH http://localhost:8080/items/1 -H 'Accept: application/json' -H 'Content-Type: application/json' -H 'If-Match: "0"' -d '{"name":"Updated by B"}'
~~~

Request của B phải nhận HTTP 412 Precondition Failed vì ETag hiện tại đã khác "0". Server không áp dụng nội dung cập nhật cũ này. Trong ví dụ, dữ liệu của A vẫn được giữ.

### 3.4. Client B xử lý xung đột

Sau 412, B không gửi lại nguyên request với ETag cũ. B cần:

1. GET lại đúng URI của tài nguyên.
2. Đọc dữ liệu mới nhất và ETag mới.
3. So sánh các trường B định sửa với dữ liệu mà A đã ghi.
4. Quyết định giữ thay đổi của A, giữ thay đổi của B hoặc hợp nhất cả hai theo quy tắc nghiệp vụ.
5. Gửi request mới với If-Match mang ETag mới.

Không tự động retry một payload cũ mà chưa hợp nhất dữ liệu. Làm như vậy có thể biến thao tác xử lý xung đột thành một lần ghi đè mới.

## 4. Kiểm thử tích hợp bằng MockMvc

Có thể kiểm tra contract HTTP của Spring Data REST bằng MockMvc trong test Spring Boot. Test dưới đây giả định:

- Ứng dụng đã có spring-boot-starter-data-rest, Spring Data JPA và cấu hình datasource cho test.
- ItemRepository được Spring Data REST xuất bản.
- Endpoint item mặc định là /items/{id}.
- Item có trường name và trường version được đánh dấu @Version.
- Dữ liệu test được lưu trước khi gửi các request HTTP.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ItemEtagConcurrencyTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ItemRepository itemRepository;

    @Test
    void rejectsUpdateFromClientUsingStaleEtag() throws Exception {
        Item item = itemRepository.save(new Item("Initial"));
        String uri = "/items/" + item.getId();

        // Client A đọc phiên bản hiện tại.
        MvcResult responseA = mockMvc.perform(get(uri))
            .andExpect(status().isOk())
            .andReturn();

        String etagA = responseA.getResponse().getHeader(HttpHeaders.ETAG);
        assertThat(etagA).isNotBlank();

        // Client B cũng đọc trước khi bất kỳ client nào cập nhật.
        MvcResult responseB = mockMvc.perform(get(uri))
            .andExpect(status().isOk())
            .andReturn();

        String etagB = responseB.getResponse().getHeader(HttpHeaders.ETAG);
        assertThat(etagB).isEqualTo(etagA);

        // A ghi bằng ETag hợp lệ.
        mockMvc.perform(patch(uri)
                .header(HttpHeaders.IF_MATCH, etagA)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Updated by A"}
                    """))
            .andExpect(status().isOk());

        // ETag phải thay đổi sau lần ghi thành công.
        MvcResult responseAfterA = mockMvc.perform(get(uri))
            .andExpect(status().isOk())
            .andReturn();

        String currentEtag = responseAfterA.getResponse()
            .getHeader(HttpHeaders.ETAG);

        assertThat(currentEtag).isNotBlank().isNotEqualTo(etagA);

        // B dùng snapshot cũ nên request bị từ chối.
        mockMvc.perform(patch(uri)
                .header(HttpHeaders.IF_MATCH, etagB)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Updated by B"}
                    """))
            .andExpect(status().isPreconditionFailed());

        // Thay đổi của A vẫn còn trong tài nguyên.
        mockMvc.perform(get(uri))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Updated by A"));
    }
}
~~~

Nếu cấu hình ứng dụng trả về 204 No Content cho PATCH dù đã đặt Accept, thay assertion status của request A theo cấu hình thực tế (ví dụ isNoContent hoặc is2xxSuccessful). Nếu repository đổi collection path, thay URI /items/{id}. Test phải dùng hai giá trị ETag đã lấy từ response; không tự dựng ETag trong test.

### Các trường hợp nên có trong bộ test

| Trường hợp | Kết quả cần quan sát |
|---|---|
| GET item có @Version | 200 và có ETag |
| Hai client GET trước lần ghi | Hai ETag bằng nhau |
| Client A ghi với ETag hiện tại | Request thành công |
| Sau khi A ghi | ETag mới khác ETag cũ |
| Client B ghi với ETag cũ | 412 Precondition Failed |
| GET sau request bị từ chối | Dữ liệu của A vẫn còn |
| Client B GET lại và ghi với ETag mới | Request có thể thành công nếu không có cập nhật xen giữa |

Bài test trên cố ý tạo hai snapshot giống nhau rồi gửi hai lần ghi theo thứ tự xác định. Nếu cần kiểm tra race condition ở tầng database, hãy bổ sung test chạy hai request ghi song song sau một barrier, cả hai cùng mang ETag đã đọc. Khi đó cần xác nhận chỉ một thay đổi được lưu và thay đổi còn lại không ghi đè dữ liệu. Nếu hai request cùng vượt qua bước so sánh HTTP trước khi transaction commit, datastore có thể phát sinh OptimisticLockingFailureException; hãy kiểm tra exception mapping của ứng dụng để xác định status HTTP mà API công bố cho tình huống race ở tầng lưu trữ. Contract stale If-Match tuần tự được Spring Data REST mô tả rõ là 412.

## 5. Phân biệt 412 với 304

Hai status code này phục vụ hai mục đích khác nhau:

- 412 Precondition Failed: request thay đổi dữ liệu có điều kiện, chẳng hạn PATCH kèm If-Match, không thỏa điều kiện phiên bản. Server không thực hiện thay đổi.
- 304 Not Modified: GET kèm If-None-Match có ETag trùng với phiên bản hiện tại. Server báo client có thể dùng bản cache và không gửi lại representation.

Không dùng If-None-Match thay cho If-Match khi cập nhật. If-None-Match chủ yếu hỗ trợ truy vấn có điều kiện và cache; If-Match bảo vệ thao tác ghi khỏi dữ liệu cũ.

## 6. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| GET không có ETag | Entity chưa có trường version được nhận diện, endpoint không đi qua Spring Data REST hoặc header bị proxy loại bỏ | Kiểm tra @Version đúng loại annotation, metadata entity, endpoint item và response thực tế |
| Request đầu tiên đã nhận 412 | Client lưu ETag cũ, URI không đúng tài nguyên đã đọc hoặc tài nguyên đã bị cập nhật trước khi gửi | GET lại đúng URI, lấy ETag mới và đối chiếu dữ liệu trước khi ghi |
| Client B ghi thành công dù dùng dữ liệu cũ | Request thiếu If-Match, header bị client/proxy bỏ, dùng If-Match: * hoặc custom endpoint không kiểm tra điều kiện | Kiểm tra request thực gửi, không dùng wildcard khi cần so khớp phiên bản, xác nhận request đi qua cơ chế ETag của Spring Data REST |
| Nhận 400 hoặc 415 khi PATCH | JSON không hợp lệ hoặc Content-Type không được endpoint hỗ trợ | Kiểm tra body và Content-Type. Spring Data REST hỗ trợ application/json, application/hal+json, application/patch+json và application/merge-patch+json cho PATCH |
| Nhận 405 Method Not Allowed | Repository không xuất bản phương thức save hoặc thao tác tương ứng bị cấu hình tắt | Kiểm tra repository interface và cấu hình exported của phương thức |
| Nhận OptimisticLockingFailureException khi có race thật | Hai transaction cùng đọc một version rồi cùng ghi; datastore phát hiện một transaction dùng version cũ | Xác nhận trường @Version được datastore quản lý, kiểm tra transaction và ánh xạ exception thành lỗi API phù hợp |
| Client liên tục retry và vẫn nhận 412 | Client tiếp tục gửi ETag cũ sau khi server đã thay đổi tài nguyên | GET lại, hợp nhất thay đổi, sau đó gửi request mới với ETag mới |

Một số lưu ý khi debug:

- So sánh header ETag trong response GET với header If-Match của request ghi. Giá trị cần được giữ nguyên, bao gồm dấu ngoặc kép và mọi tiền tố nếu có.
- ETag là token opaque đối với client. Không giả định nó luôn là số tăng tuần tự hoặc luôn bắt đầu từ 0.
- If-Match dùng phép so sánh strong theo HTTP. Không chuyển ETag thành weak validator dạng W/ rồi gửi lại.
- If-Match: * chỉ yêu cầu tài nguyên hiện tồn tại; nó không xác nhận client đang giữ đúng phiên bản đã đọc.
- Luôn gắn ETag với đúng URI tài nguyên mà client đã GET. Không dùng ETag của item khác.
- Nếu có custom controller hoặc custom repository method, cần kiểm tra riêng xem đường xử lý đó có thực thi điều kiện If-Match và kiểm soát version hay không.

## 7. Checklist hoàn thành bài thực hành

- [ ] Entity có thuộc tính version và datastore hỗ trợ optimistic locking.
- [ ] GET tài nguyên item trả về header ETag.
- [ ] Hai client đọc cùng URI trước khi ghi và nhận cùng ETag.
- [ ] Client A gửi PATCH hoặc PUT kèm If-Match hợp lệ và cập nhật thành công.
- [ ] ETag sau lần ghi của A khác ETag ban đầu.
- [ ] Client B gửi request với ETag cũ và nhận 412 Precondition Failed.
- [ ] GET lại xác nhận dữ liệu của A không bị request cũ của B ghi đè.
- [ ] Client B có thể đọc phiên bản mới, hợp nhất dữ liệu và gửi request với ETag mới.

## Tài liệu tham khảo chính thức

1. [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): cách Spring Data REST tạo ETag từ thuộc tính @Version, dùng If-Match cho PUT/PATCH/DELETE và trả 412 khi ETag không còn khớp.
2. [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): URI item resource, các HTTP method được hỗ trợ và media type của PATCH.
3. [Spring Data Commons — @Version API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Version.html): ý nghĩa của thuộc tính version trong optimistic locking.
4. [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): conditional request, ETag và phân biệt 304 với 412 trong Spring MVC.
5. [RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1) và [412 Precondition Failed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.13): ngữ nghĩa chuẩn HTTP cho điều kiện ghi và phản hồi khi điều kiện không thỏa.
