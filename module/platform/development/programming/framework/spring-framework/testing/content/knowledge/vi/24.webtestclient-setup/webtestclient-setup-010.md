# Tái sử dụng cấu hình client mà vẫn cô lập dữ liệu mỗi bài

## 1. Hai loại trạng thái cần tách riêng

Trong bộ kiểm thử Spring WebFlux, có thể dùng cùng một cấu hình **WebTestClient** cho nhiều test: base URL, default headers, codec, filter, timeout và cách kết nối tới ứng dụng. Tái sử dụng cấu hình giúp các test gửi request theo cùng một chuẩn và tránh lặp lại phần thiết lập.

Dữ liệu mà mỗi test tạo ra lại cần độc lập. Một test không nên đọc nhầm bản ghi do test khác tạo, phụ thuộc thứ tự chạy hoặc xóa dữ liệu của test khác khi cleanup.

Hãy phân biệt hai nhóm:

- **Cấu hình client:** những thiết lập dùng chung và ổn định như URL gốc, media type mặc định, codec và filter không giữ trạng thái theo test.
- **Dữ liệu và trạng thái test:** id, bản ghi, token, mock expectation, cache key, event hoặc message được tạo riêng cho một lần chạy test.

Có thể dùng một WebTestClient đã build cho nhiều request. Mỗi test tạo dữ liệu riêng và gửi request riêng. Nếu một test cần thay đổi cấu hình client, hãy tạo một client mới từ client nền bằng **mutate()** rồi **build()**; không thay đổi một builder dùng chung trong lúc các test đang chạy.

## 2. WebTestClient và các cách kết nối tới ứng dụng

**WebTestClient** cung cấp API gửi request và assertion response tương tự WebClient, đồng thời tích hợp các assertion dành cho test. Có thể kết nối tới ứng dụng theo nhiều cách:

| Cách bind | Dùng khi nào | Đặc điểm |
|---|---|---|
| **bindToController(...)** | Test một hoặc vài controller WebFlux | Tạo mock WebFlux stack tập trung vào controller |
| **bindToRouterFunction(...)** | Test functional endpoint | Dùng RouterFunction được cung cấp |
| **bindToApplicationContext(...)** | Test cấu hình WebFlux trong application context | Dùng các thành phần được đăng ký trong context, không mở socket thật |
| **bindToServer()** | Test một server đang chạy | Gửi HTTP qua connector tới địa chỉ thật |

Ví dụ tạo client gắn với WebFlux application context:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient baseClient = WebTestClient
        .bindToApplicationContext(applicationContext)
        .configureClient()
        .baseUrl("/api")
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
        )
        .build();
~~~

Client này dùng mock web infrastructure của Spring. Nó phù hợp để kiểm tra mapping, filter, controller, codec và response contract trong application context.

Nếu cần kết nối tới server đang chạy, có thể tạo client theo địa chỉ HTTP:

~~~java
WebTestClient serverClient = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
        )
        .build();
~~~

Trong integration test Spring Boot, thường không cần tự quản lý cổng. Có thể để Spring Boot khởi chạy server trên cổng ngẫu nhiên và inject WebTestClient đã được cấu hình.

## 3. Tạo một cấu hình nền và tái sử dụng client

### Với application context mock

Nếu nhiều test cùng dùng một WebFlux application context, có thể tạo client nền một lần trong test fixture hoặc test configuration.

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import org.junit.jupiter.api.BeforeEach;

abstract class BaseWebFluxTest {

    @Autowired
    protected ApplicationContext applicationContext;

    protected WebTestClient client;

    @BeforeEach
    void configureClient() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .configureClient()
                .baseUrl("/api")
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE
                )
                .build();
    }
}
~~~

Các lớp test kế thừa fixture này có cùng cách thiết lập client. Nếu application context được Spring Test cache giữa các test class, việc tạo client từ context không yêu cầu khởi tạo lại toàn bộ ứng dụng cho từng method.

Nếu muốn giữ một client nền và tạo biến thể khi cần, có thể build client nền rồi dùng **mutate()**:

~~~java
WebTestClient baseClient = WebTestClient
        .bindToApplicationContext(applicationContext)
        .configureClient()
        .baseUrl("/api")
        .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
        .build();

WebTestClient shortTimeoutClient = baseClient.mutate()
        .responseTimeout(java.time.Duration.ofSeconds(3))
        .build();
~~~

**mutate()** tạo một builder từ cấu hình của client hiện có. Gọi **build()** tạo client mới với thay đổi riêng. Client nền vẫn có thể được tái sử dụng cho các test khác.

### Với máy chủ Spring Boot thật

Khi cần gửi request qua embedded server, có thể dùng cấu hình sau:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.beans.factory.annotation.Autowired;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoteApiIntegrationTest {

    @Autowired
    WebTestClient client;
}
~~~

Spring Boot khởi chạy server trên cổng ngẫu nhiên và cung cấp WebTestClient đã kết nối tới server đó. Cùng một client có thể được dùng cho nhiều request trong class test.

Không nên nhầm hai kiểu client: client bind vào application context mock không kiểm tra socket hoặc embedded server; client được cấu hình qua server thật mới kiểm tra request/response trên HTTP connector.

## 4. WebTestClient sau khi build có thể được tái sử dụng

Sau khi gọi **build()**, WebTestClient là một client đã được cấu hình để thực hiện các exchange. Có thể dùng cùng instance cho nhiều request:

~~~java
client.get()
        .uri("/health")
        .exchange()
        .expectStatus().isOk();

client.get()
        .uri("/version")
        .exchange()
        .expectStatus().isOk();
~~~

Mỗi lần gọi **get()**, **post()**, **put()** hoặc **delete()** tạo một request specification mới. Các assertion của exchange đó gắn với response của request tương ứng.

Điều cần tránh là dùng chung một **WebTestClient.Builder** mutable rồi thay đổi header, filter hoặc timeout trong lúc các test chạy song song. Hãy hoàn tất cấu hình và build client trước khi dùng. Nếu cần một cấu hình khác, tạo client mới từ client nền bằng **mutate()**.

Cũng không nên lưu một request specification hoặc response result vào field dùng chung để nhiều test tiếp tục sửa hoặc đọc. Hãy tạo request specification và xử lý response ngay trong test method.

## 5. Thay đổi theo từng request mà không làm bẩn client nền

Những giá trị thay đổi theo test thường là dữ liệu của request, không phải cấu hình client. Ví dụ correlation id, tenant id, user token hoặc id của test run nên được gắn vào request cụ thể:

~~~java
String testRunId = java.util.UUID.randomUUID().toString();

client.get()
        .uri("/notes/{id}", noteId)
        .headers(headers -> headers.set("X-Test-Run", testRunId))
        .exchange()
        .expectStatus().isOk();
~~~

Header chỉ được gắn vào request này. Request kế tiếp không tự động nhận giá trị **X-Test-Run**.

Nếu một test cần cấu hình client-level riêng, ví dụ timeout khác hoặc filter bổ sung, hãy tạo biến thể:

~~~java
WebTestClient testClient = client.mutate()
        .responseTimeout(java.time.Duration.ofSeconds(2))
        .build();
~~~

Không nên gọi **defaultHeader()** trên builder dùng chung cho từng test để truyền dữ liệu riêng. Default header thuộc cấu hình client và có thể tồn tại trên các request sau đó. Với dữ liệu theo test, dùng **headers(...)** trên request builder.

### Filter dùng chung nên không giữ trạng thái theo test

Filter hữu ích để ghi log, thêm header chung hoặc đo thời gian exchange. Nhưng filter được cấu hình trên client dùng chung có thể được gọi đồng thời bởi nhiều test.

Một filter an toàn nên dựa vào request hiện tại và tránh giữ dữ liệu test trong biến mutable toàn cục. Nếu filter cần correlation id, có thể đọc header của request hoặc dùng Reactor Context theo đúng luồng reactive. Tránh ghi mọi request vào một **ArrayList** dùng chung rồi để các test tự đọc/xóa vì các test có thể ghi đè hoặc đọc lẫn dữ liệu của nhau.

## 6. Cô lập dữ liệu bằng id riêng cho mỗi test

Tái sử dụng client không có nghĩa các test phải dùng chung dữ liệu. Một cách đơn giản là tạo id duy nhất cho từng test, lưu fixture bằng id đó, gửi request chỉ tới fixture đó, rồi xóa đúng fixture trong cleanup.

Ví dụ dưới đây giả định ứng dụng có reactive repository và endpoint GET một note theo id:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoteApiIntegrationTest {

    @Autowired
    private WebTestClient client;

    @Autowired
    private NoteRepository noteRepository;

    @Test
    void shouldReturnOnlyTheNoteCreatedForThisTest() {
        String noteId = UUID.randomUUID().toString();
        String title = "note-" + noteId;

        noteRepository.save(new Note(noteId, title)).block();

        try {
            client.get()
                    .uri("/api/notes/{id}", noteId)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            org.springframework.http.MediaType.APPLICATION_JSON)
                    .expectBody()
                    .jsonPath("$.id").isEqualTo(noteId)
                    .jsonPath("$.title").isEqualTo(title);
        } finally {
            noteRepository.deleteById(noteId).block();
        }
    }
}
~~~

Điểm quan trọng trong ví dụ:

1. **noteId** được tạo mới cho mỗi lần chạy test, nên không đụng id của test khác.
2. Test chỉ truy vấn fixture mà chính nó tạo.
3. Cleanup xóa đúng **noteId**, không xóa toàn bộ bảng.
4. Khối **finally** chạy cleanup cả khi assertion thất bại.

Gọi **block()** ở test method là cách đơn giản để hoàn tất thao tác setup/cleanup reactive trước khi test kết thúc. Không gọi **block()** bên trong WebFlux event loop hoặc trong code xử lý request. Trong một bộ test reactive lớn, có thể viết setup và cleanup bằng Reactor chain và dùng **StepVerifier**; nguyên tắc cô lập dữ liệu vẫn giữ nguyên.

Nếu test kiểm tra endpoint tạo mới dữ liệu, hãy lấy id trả về từ response rồi cleanup đúng id đó. Không nên dựa vào một id cố định dùng chung giữa nhiều lần chạy hoặc nhiều worker CI.

## 7. Cô lập bằng namespace thay vì xóa toàn bộ dữ liệu

Một số hệ thống không thể dễ dàng tạo id riêng cho mọi loại dữ liệu. Khi đó, có thể gắn một test namespace vào dữ liệu:

~~~java
String testNamespace = "test-" + UUID.randomUUID();

client.post()
        .uri("/api/jobs")
        .header("X-Test-Namespace", testNamespace)
        .bodyValue(new CreateJobRequest("import"))
        .exchange()
        .expectStatus().isCreated();
~~~

Ứng dụng cần có cơ chế test phù hợp để namespace đó đi vào khóa lưu trữ, tenant hoặc metadata của fixture. Header chỉ có ý nghĩa nếu ứng dụng thực sự xử lý nó; thêm một header trong test tự nó không cách ly database.

Các lựa chọn phổ biến:

- Dùng UUID hoặc sequence riêng cho từng fixture.
- Thêm tenant/test-run key vào dữ liệu nếu ứng dụng hỗ trợ multi-tenant.
- Dùng schema hoặc database riêng cho mỗi test suite hoặc mỗi CI worker.
- Dùng container database riêng cho từng suite khi cần isolation mạnh.
- Cleanup theo tập id do test tạo, thay vì gọi **deleteAll()** trên dữ liệu dùng chung.

Không nên dùng **deleteAll()** trong cleanup của một test chạy song song với test khác trên cùng database. Nó có thể xóa fixture của test chưa hoàn tất.

## 8. Vì sao @Transactional không luôn rollback được request WebTestClient?

Một hiểu nhầm phổ biến là đặt **@Transactional** trên test method thì mọi dữ liệu mà endpoint tạo ra sẽ tự rollback khi test kết thúc.

Điều đó không đúng với request HTTP tới server thật. Test method và request được server xử lý là hai luồng công việc độc lập. Request server có transaction riêng theo service/repository và transaction context của nó; transaction của test method không tự truyền qua ranh giới HTTP.

Trong WebFlux, transaction reactive thường gắn với Reactor Context, không dựa vào ThreadLocal như cách dùng transaction imperative truyền thống. Một transaction trên test method không tự được gắn vào Reactor Context của request do WebTestClient gửi tới.

Ngay cả khi WebTestClient bind trực tiếp vào application context mock và không mở socket, request vẫn được xử lý như một exchange riêng. Không nên mặc định transaction test bao bọc transaction trong request pipeline.

Vì vậy, với integration test dùng WebTestClient, hãy ưu tiên:

- Setup fixture trước request.
- Dùng id hoặc namespace riêng.
- Cleanup đúng dữ liệu sau request.
- Dùng database/schema/container riêng nếu cần isolation ở mức cao hơn.

**@Transactional** vẫn hữu ích cho các test gọi repository/service trực tiếp trong cùng transaction được quản lý bởi test framework. Chỉ cần hiểu ranh giới của nó trước khi áp dụng cho request qua WebTestClient.

## 9. Mock và service state cũng phải độc lập

Với controller slice, thường mock service để test HTTP mapping và response:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(NoteController.class)
class NoteControllerTest {

    @Autowired
    private WebTestClient client;

    @MockBean
    private NoteService noteService;

    @Test
    void shouldReturnTheRequestedNote() {
        String noteId = "note-a";
        when(noteService.findById(noteId))
                .thenReturn(Mono.just(new NoteResponse(noteId, "title-a")));

        client.get()
                .uri("/api/notes/{id}", noteId)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(noteId)
                .jsonPath("$.title").isEqualTo("title-a");
    }
}
~~~

Trong Spring Boot 3.3, **@MockBean** là cách quen thuộc để thay bean trong application context bằng Mockito mock. Spring Boot mặc định reset mock sau mỗi test method theo cấu hình reset của annotation. Dù vậy, mỗi test vẫn nên khai báo rõ stub cần dùng, không phụ thuộc thứ tự test hoặc dữ liệu do test trước để lại.

Nếu mock có **Answer** giữ bộ đếm, danh sách event hoặc mutable object, cần bảo đảm state đó chỉ thuộc test hiện tại. Một mock được reset không tự dừng tác vụ async còn đang chạy và cũng không xóa dữ liệu mà tác vụ đó đã ghi vào database.

Không nên dùng một singleton fake service có mutable collection chung cho nhiều test song song nếu không có cơ chế đồng bộ và reset rõ ràng. Khi cần kiểm tra event hoặc request đã nhận, dùng captor hoặc recorder có vòng đời giới hạn trong test đó.

## 10. Chạy test song song mà không rò rỉ dữ liệu

Khi JUnit hoặc CI chạy nhiều test đồng thời, client nền có thể được chia sẻ nhưng fixture phải được phân vùng.

Các nguyên tắc thực tế:

- Tạo id riêng trong từng test method.
- Không dùng chung một field mutable để lưu id của test đang chạy.
- Không cleanup bằng cách xóa toàn bộ bảng, cache hoặc queue.
- Dùng request header hoặc tenant key chỉ khi ứng dụng thật sự hỗ trợ phân vùng tương ứng.
- Filter và callback dùng chung không được giữ mutable state theo từng test.
- Không phụ thuộc test chạy trước để tạo dữ liệu cho test chạy sau.
- Đóng stream, subscription và tài nguyên async trong cleanup.
- Nếu test dùng một resource bên ngoài không thể phân vùng, tắt parallel cho nhóm test đó hoặc cấp resource riêng.

JUnit mặc định tạo một instance test class cho mỗi test method. Nếu đổi sang **@TestInstance(PER_CLASS)**, các field instance được chia sẻ giữa các method; cần đặc biệt cẩn thận với các field như current id, mutable header map, mock recorder hoặc test fixture.

Với test chạy song song, một **WebTestClient** đã build có thể được tái sử dụng nếu cấu hình và filter của nó không giữ state mutable dùng chung. Cần cô lập dữ liệu và request-specific state ở từng test.

## 11. Khi nào cần tạo client mới?

Không phải mỗi test đều cần một client instance mới. Chọn theo loại thay đổi:

| Nhu cầu | Cách làm |
|---|---|
| Cùng base URL, codec, filter và default header | Tái sử dụng client đã build |
| Header hoặc token khác nhau cho một request | Đặt header trên request builder |
| Timeout khác cho một nhóm test | Dùng **client.mutate().responseTimeout(...).build()** |
| Cần thêm filter riêng cho một test | Tạo client mới bằng **mutate()** rồi **build()** |
| Kết nối tới mock application context và server thật | Tạo client theo bind mode tương ứng |
| Dữ liệu database khác nhau | Tạo fixture id/namespace riêng, không cần client mới |
| Cần cấu hình TLS hoặc connector khác | Tạo client mới với connector và cấu hình tương ứng |

Một client mới không tự làm sạch database, cache hoặc mock state. Ngược lại, cùng một client không khiến dữ liệu của các test bị dùng chung nếu mỗi test tạo fixture độc lập và request không mang state thừa.

## 12. Tránh các cách cô lập dễ gây lỗi

| Cách làm | Vấn đề | Cách thay thế |
|---|---|---|
| Tạo một builder static rồi sửa header trong từng test | Builder mutable có thể bị nhiều test thay đổi đồng thời | Build client nền một lần; header riêng đặt trên request |
| Dùng một id cố định trong mọi test | Test phụ thuộc thứ tự và dữ liệu cũ | Dùng UUID hoặc namespace riêng |
| Gọi deleteAll() sau mỗi test | Có thể xóa dữ liệu của test chạy song song | Xóa đúng id hoặc namespace của test |
| Dùng @Transactional và giả định HTTP request sẽ rollback cùng test | Transaction không tự đi qua ranh giới request | Cleanup tường minh hoặc database riêng |
| Dùng filter ghi state vào collection singleton | Nhiều request có thể ghi và đọc lẫn nhau | Filter stateless hoặc recorder theo test |
| Dùng @DirtiesContext để xóa dữ liệu | Reload context không đồng nghĩa reset database, Redis hoặc queue | Cleanup đúng resource bên ngoài |
| Chia sẻ response result hoặc request specification giữa test | Response và request có vòng đời riêng | Tạo và assert exchange trong từng test method |

**@DirtiesContext** có thể hữu ích khi một test làm hỏng trạng thái của Spring context và cần tạo context mới. Đây không phải cơ chế cleanup database tổng quát; việc reload context cũng tốn thời gian và có thể làm bộ test chậm hơn đáng kể.

## 13. Một mẫu tổ chức test có thể mở rộng

Có thể gom cấu hình client nền vào một fixture dùng chung, còn dữ liệu test được tạo tại method:

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.reactive.server.WebTestClient;

abstract class BaseApiIntegrationTest {

    @Autowired
    protected WebTestClient client;

    protected String newTestId() {
        return UUID.randomUUID().toString();
    }
}
~~~

Một test cụ thể tự tạo và dọn dữ liệu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class NoteApiIntegrationTest extends BaseApiIntegrationTest {

    @Autowired
    private NoteRepository noteRepository;

    @Test
    void shouldReadItsOwnNote() {
        String id = newTestId();
        Note note = new Note(id, "title-" + id);

        noteRepository.save(note).block();

        try {
            client.get()
                    .uri("/api/notes/{id}", id)
                    .exchange()
                    .expectStatus().isOk()
                    .expectBody()
                    .jsonPath("$.id").isEqualTo(id);
        } finally {
            noteRepository.deleteById(id).block();
        }
    }
}
~~~

Lớp cơ sở chỉ chia sẻ cấu hình client và helper tạo id. Mỗi test method sở hữu fixture của mình. Nếu một test cần client có timeout khác hoặc filter bổ sung, test có thể tạo biến thể bằng **client.mutate()** mà không sửa client nền.

Trong một dự án có nhiều loại endpoint, có thể có một fixture cho mock-bound WebFlux context và một fixture cho server thật. Tên và cách sử dụng nên thể hiện rõ cấp độ test để người đọc không nhầm một test mock context với một HTTP integration test.

Tái sử dụng WebTestClient giúp thống nhất cách gửi request và assertion. Tính độc lập của mỗi test đến từ fixture riêng, request riêng, cleanup có phạm vi và việc tránh chia sẻ mutable state giữa các lần chạy.

