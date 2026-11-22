# Mô phỏng hai người dùng cập nhật đồng thời với ETag

## 1. Bài toán: tránh ghi đè thay đổi của người khác

Giả sử hai người dùng A và B cùng mở một bản ghi ghi chú. Cả hai đều nhìn thấy nội dung “Bản nháp” ở cùng một thời điểm. A đổi tiêu đề thành “Bản nháp đã duyệt” và lưu trước. Vài giây sau, B lưu bản chỉnh sửa cũ với tiêu đề “Bản nháp của B”.

Nếu server chỉ nhận dữ liệu mới rồi ghi xuống database, lần lưu của B có thể âm thầm ghi đè thay đổi của A. Đây là **lost update** (mất cập nhật): người dùng sửa dựa trên một phiên bản cũ nhưng server không phát hiện dữ liệu đã thay đổi.

ETag và If-Match giải quyết vấn đề này bằng điều kiện HTTP:

1. Server trả về một mã ETag đại diện cho phiên bản hiện tại của resource.
2. Client giữ nguyên ETag cùng bản dữ liệu đã đọc.
3. Khi sửa, client gửi lại ETag trong header If-Match.
4. Server chỉ chấp nhận thay đổi nếu ETag client gửi vẫn khớp với phiên bản hiện tại.
5. Nếu một client khác đã lưu trước, client cũ nhận HTTP 412 Precondition Failed và phải tải lại, đối chiếu rồi quyết định cách hợp nhất.

Spring Data REST tích hợp cơ chế này với thuộc tính phiên bản của entity. Với Spring Data JPA, dùng @Version của Jakarta Persistence; với các module Spring Data khác, dùng org.springframework.data.annotation.Version. Khi entity được xuất thành REST resource, Spring Data REST đưa giá trị version vào response header ETag. PUT, PATCH và DELETE có thể được điều kiện hóa bằng If-Match. Nếu ETag đã cũ, server trả 412. Xem [Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html).

## 2. ETag, If-Match và @Version phối hợp như thế nào?

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| @Version | Theo dõi revision của entity trong datastore và hỗ trợ optimistic locking | version = 0, sau lần cập nhật thành công tăng thành 1 |
| ETag | Gửi validator của resource trong response HTTP | ETag: "0" |
| If-Match | Yêu cầu server chỉ thực hiện thay đổi nếu validator vẫn khớp | If-Match: "0" |
| If-None-Match | Kiểm tra GET có cần gửi lại representation hay không | Khớp ETag thì trả 304 Not Modified |
| 412 Precondition Failed | Báo điều kiện If-Match không còn đúng | Client đang giữ ETag cũ |
| 304 Not Modified | Báo representation chưa thay đổi so với ETag client gửi | Client có thể dùng cache hiện tại |

Có hai lớp bảo vệ bổ sung cho nhau:

- **Điều kiện HTTP** kiểm tra client đang sửa dựa trên revision nào. Đây là phần ngăn người dùng gửi bản chỉnh sửa cũ sau khi đã có người khác cập nhật.
- **Optimistic locking ở datastore** kiểm tra revision khi ghi. Nếu hai transaction cùng đọc một version và cùng ghi gần như đồng thời, database/persistence provider phải phát hiện transaction ghi sau đang dùng version cũ.

Với JPA, câu lệnh cập nhật entity có version về bản chất phải kiểm tra version hiện lưu trong database. Khi version không còn giống giá trị entity đã đọc, persistence provider báo optimistic lock failure thay vì ghi đè revision mới hơn. Giá trị version được persistence provider tăng lên; ứng dụng không tự đặt version mới.

### Không nhầm ETag kiểm soát ghi với ETag chỉ phục vụ cache

Spring Framework có ShallowEtagHeaderFilter để tạo ETag từ nội dung response. Filter này hữu ích cho GET và If-None-Match/304, nhưng tài liệu chỉ rõ nó không xử lý các state-changing precondition như If-Match. Đối với endpoint Spring Data REST cần tránh lost update, hãy dùng thuộc tính @Version được datastore hỗ trợ và cơ chế ETag của Spring Data REST. Không chỉ thêm ShallowEtagHeaderFilter rồi cho rằng PATCH/PUT đã được bảo vệ.

## 3. Khai báo version trên entity

Ví dụ dưới đây dùng Spring Boot 3.x, Spring Data JPA và Jakarta Persistence:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Note {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private String title;

    protected Note() {
    }

    public Note(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Một số điểm cần giữ đúng:

- Với JPA trên Spring Boot 3 trở lên, import **jakarta.persistence.Version**. Với ứng dụng Boot 2 cũ, package tương ứng là **javax.persistence.Version**.
- Với Spring Data JDBC, MongoDB và các module Spring Data khác, dùng **org.springframework.data.annotation.Version** theo hướng dẫn của module đó.
- Một entity JPA chỉ nên có một thuộc tính version. Thuộc tính phải được ánh xạ vào bảng chính của entity và dùng kiểu được Jakarta Persistence hỗ trợ, chẳng hạn int, Integer, long, Long hoặc timestamp phù hợp với phiên bản đặc tả.
- Không cho client tự cập nhật trường version trong request body. Đây là metadata do persistence provider quản lý.
- Có thể không công khai getter của version trong representation JSON nếu client chỉ cần giữ ETag header. Client không cần đọc hoặc tự tính toán con số version.
- Nếu database đã có dữ liệu, migration phải thêm và khởi tạo cột version cho các bản ghi hiện hữu. Ví dụ SQL minh họa: ALTER TABLE note ADD COLUMN version BIGINT NOT NULL DEFAULT 0;. Hãy điều chỉnh cú pháp và chiến lược backfill theo database thực tế.

Repository được Spring Data REST xuất thành collection resource:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "notes")
public interface NoteRepository extends JpaRepository<Note, Long> {
}
~~~

Với cấu hình mặc định, collection resource là /notes và item resource có dạng /notes/{id}. ETag dùng cho chỉnh sửa một bản ghi cần lấy từ **item resource**, ví dụ /notes/42, không lấy từ collection /notes.

## 4. Luồng hai người dùng A và B

Giả sử resource /notes/42 đang có ETag "0".

1. **A đọc resource.** GET /notes/42 trả nội dung hiện tại cùng ETag: "0". A giữ body và ETag này trong trạng thái chỉnh sửa.
2. **B cũng đọc resource.** GET /notes/42 trả cùng nội dung và ETag: "0". B cũng giữ revision 0.
3. **A lưu trước.** A gửi PATCH với If-Match: "0". Điều kiện đúng nên server chấp nhận cập nhật. Sau khi lưu, version tăng và response kế tiếp có ETag mới, ví dụ "1".
4. **B lưu bằng dữ liệu cũ.** B vẫn gửi If-Match: "0". Server đang có revision 1 nên từ chối request bằng 412 Precondition Failed. Nội dung A đã lưu được giữ nguyên.
5. **B xử lý xung đột.** B tải lại resource mới nhất, so sánh nội dung A đã lưu với bản nháp của mình, sau đó hợp nhất hoặc yêu cầu người dùng chọn. Chỉ gửi request mới với ETag mới sau khi đã giải quyết xung đột.

Đây là mô phỏng hai client độc lập. Hai request không cần chạy đồng thời trên hai thread để tái hiện lỗi stale update: chỉ cần cả hai cùng đọc revision cũ rồi lần lượt gửi hai request ghi. Với cuộc đua thực sự ở tầng transaction, @Version tiếp tục bảo vệ bước ghi tại datastore.

## 5. Thử trực tiếp bằng HTTP

Khởi động ứng dụng và tạo một Note có ID 42. Thay URL và ID theo dữ liệu thực tế.

### Hai client cùng đọc

Client A:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/notes/42
~~~

Client B gửi cùng GET tới đúng URI đó:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/notes/42
~~~

Cả hai response phải có ETag. Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "0"

{
  "title": "Bản nháp",
  "_links": {
    "self": {
      "href": "http://localhost:8080/notes/42"
    }
  }
}
~~~

Giá trị "0" chỉ là minh họa. Hãy sao chép nguyên văn ETag thực tế từ response, bao gồm dấu ngoặc kép nếu có. Không tự ghép ETag từ ID hoặc version trong JSON.

### A cập nhật bằng ETag vừa đọc

Ví dụ dùng PATCH với JSON Merge Patch:

~~~bash
curl -i -X PATCH \
  -H 'If-Match: "0"' \
  -H "Content-Type: application/merge-patch+json" \
  -H "Accept: application/hal+json" \
  --data '{"title":"Đã được A duyệt"}' \
  http://localhost:8080/notes/42
~~~

Trong ví dụ, thay "0" bằng ETag A thực sự nhận được. Khi điều kiện còn đúng, request được chấp nhận. Tùy cấu hình response body của Spring Data REST, update có thể trả 200 OK hoặc 204 No Content. Sau đó GET lại item resource để lấy ETag mới.

### B gửi bản chỉnh sửa dựa trên ETag cũ

B vẫn dùng ETag đã nhận trước khi A lưu:

~~~bash
curl -i -X PATCH \
  -H 'If-Match: "0"' \
  -H "Content-Type: application/merge-patch+json" \
  -H "Accept: application/hal+json" \
  --data '{"title":"Bản nháp do B sửa"}' \
  http://localhost:8080/notes/42
~~~

Kết quả mong đợi:

~~~http
HTTP/1.1 412 Precondition Failed
~~~

Kiểm tra lại GET /notes/42: tiêu đề vẫn là “Đã được A duyệt”. Request cũ của B không được phép ghi đè dữ liệu đó.

Spring Data REST cũng hỗ trợ PUT và DELETE có điều kiện bằng If-Match. PUT thay thế representation của item; PATCH chỉ cập nhật các trường được gửi. Spring Data REST chấp nhận application/json, application/hal+json, application/patch+json và application/merge-patch+json cho PATCH theo tài liệu repository resources.

## 6. Kiểm thử có thể lặp lại với MockMvc

Có thể mô phỏng hai người dùng bằng hai lần GET riêng biệt trong một test. Cả hai giữ cùng ETag ban đầu; test cho A cập nhật thành công, rồi xác nhận B dùng ETag cũ bị từ chối.

Ví dụ dùng Spring Boot 3.x, JUnit Jupiter, Spring Data JPA và Spring Data REST:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NoteEtagConcurrencyTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    NoteRepository notes;

    private Long noteId;

    @BeforeEach
    void prepareData() {
        notes.deleteAll();
        noteId = notes.saveAndFlush(new Note("Bản nháp")).getId();
    }

    @Test
    void rejectsSecondClientUsingStaleEtag() throws Exception {
        // A và B đọc cùng một item resource trước khi có cập nhật.
        String etagA = fetchEtag();
        String etagB = fetchEtag();

        assertThat(etagA).isNotBlank();
        assertThat(etagB).isEqualTo(etagA);

        // A lưu với ETag còn mới.
        mvc.perform(patch("/notes/{id}", noteId)
                .header(HttpHeaders.IF_MATCH, etagA)
                .contentType(MediaType.parseMediaType(
                    "application/merge-patch+json"))
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "title": "Đã được A duyệt"
                    }
                    """))
            .andExpect(status().is2xxSuccessful());

        // ETag hiện tại đã thay đổi sau khi A cập nhật.
        String currentEtag = fetchEtag();
        assertThat(currentEtag).isNotEqualTo(etagA);

        // B gửi bản nháp cũ cùng ETag cũ: server phải từ chối.
        mvc.perform(patch("/notes/{id}", noteId)
                .header(HttpHeaders.IF_MATCH, etagB)
                .contentType(MediaType.parseMediaType(
                    "application/merge-patch+json"))
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "title": "Bản nháp do B sửa"
                    }
                    """))
            .andExpect(status().isPreconditionFailed());

        // Thay đổi của A vẫn là dữ liệu được lưu.
        Note saved = notes.findById(noteId).orElseThrow();
        assertThat(saved.getTitle()).isEqualTo("Đã được A duyệt");
    }

    private String fetchEtag() throws Exception {
        MvcResult result = mvc.perform(
                get("/notes/{id}", noteId).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andReturn();

        return result.getResponse().getHeader(HttpHeaders.ETAG);
    }
}
~~~

Các điểm cần lưu ý khi áp dụng:

- Test dùng @SpringBootTest và @AutoConfigureMockMvc để chạy qua Spring MVC và Spring Data REST configuration thực tế. MockMvc không cần mở cổng HTTP.
- Test không gắn @Transactional lên class. Fixture được tạo bằng repository trước request và được dọn tường minh ở @BeforeEach, giúp ranh giới transaction của request rõ ràng.
- Nếu ứng dụng có Spring Security, thêm credential/role phù hợp cho từng request. Khi cần kiểm tra hai user khác nhau, gửi authentication tương ứng cho từng lượt GET/PATCH.
- Nếu response update được cấu hình trả 204, assertion is2xxSuccessful() vẫn xác nhận thao tác A thành công. Trọng tâm của test là ETag mới và stale request nhận 412.
- Cần chạy test với database hỗ trợ versioning tương ứng với môi trường ứng dụng. Nếu chỉ dùng database nhúng, nên có thêm integration test trên cùng loại database production khi dialect hoặc transaction behavior có ảnh hưởng.

MockMvc thực hiện đầy đủ Spring MVC request handling bằng mock request/response thay vì server đang chạy. Xem [Spring Framework MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html).

## 7. Xử lý 412 ở giao diện người dùng

Khi nhận 412, client không nên tự động gửi lại cùng payload với ETag mới. Làm như vậy sẽ biến thao tác kiểm soát xung đột thành một lần ghi đè mù khác.

Một luồng xử lý thân thiện hơn:

1. Giữ lại bản nháp chưa lưu của người dùng và ETag cũ.
2. Gửi GET tới đúng item URI để tải representation và ETag mới.
3. So sánh bản nháp với dữ liệu mới nhất. Có thể hiển thị giá trị trước đó, giá trị hiện tại trên server và giá trị người dùng đang nhập.
4. Cho phép người dùng bỏ bản nháp, dùng bản mới nhất hoặc hợp nhất thủ công các trường.
5. Sau khi người dùng xác nhận nội dung hợp nhất, gửi PUT/PATCH với ETag mới.
6. Nếu vẫn nhận 412, lặp lại quy trình tải mới và đối chiếu.

Không xóa bản nháp ngay khi request thất bại. Hãy giữ nó trong state của form hoặc bộ nhớ phù hợp để người dùng không mất công nhập lại.

Nếu có thể, hãy lưu ETag ngay khi nhận GET và cập nhật lại sau mỗi lần ghi thành công. Không lấy version từ body rồi tự dựng chuỗi header; giữ nguyên giá trị ETag server đã trả.

## 8. Phân biệt 412, 409, 428 và 304

| Status | Ý nghĩa trong tình huống này | Hành động phía client |
|---|---|---|
| 200 / 204 | Cập nhật thành công, tùy response-body configuration | Cập nhật dữ liệu hiển thị và lưu ETag mới nếu có |
| 304 Not Modified | GET có If-None-Match khớp ETag hiện tại | Dùng representation đã cache |
| 409 Conflict | Xung đột nghiệp vụ hoặc quy tắc domain do ứng dụng định nghĩa | Hiển thị lỗi nghiệp vụ và hướng xử lý tương ứng |
| 412 Precondition Failed | ETag trong If-Match không còn khớp | Tải dữ liệu mới và giải quyết xung đột |
| 428 Precondition Required | Server yêu cầu client phải gửi precondition nhưng request thiếu điều kiện | Gửi lại sau khi lấy validator hợp lệ |

Spring Data REST tài liệu hóa 412 khi ETag được gửi trong If-Match không còn khớp. Không nên mặc định rằng chỉ cần khai báo @Version là server sẽ tự bắt buộc mọi request PUT/PATCH/DELETE phải có If-Match và trả 428 nếu thiếu header. Nếu nghiệp vụ yêu cầu bắt buộc điều kiện cho mọi lần ghi, cần triển khai policy ở server (ví dụ filter hoặc custom endpoint) và viết test riêng cho request thiếu If-Match.

If-Match: * chỉ yêu cầu resource tồn tại. Nó không xác nhận client đang giữ revision cụ thể nào, vì vậy không dùng wildcard này để bảo vệ thao tác chỉnh sửa chống lost update.

## 9. Lưu ý khi đưa vào ứng dụng thực tế

### Dùng đúng ETag cho đúng resource

- Lấy ETag từ response của item URI mà người dùng đang chỉnh sửa.
- Giữ nguyên cả dấu ngoặc kép và tiền tố nếu server trả về.
- Không dùng ETag của collection, resource liên quan hoặc một query URI khác cho item hiện tại.
- Không tái sử dụng ETag đã cũ sau khi thao tác ghi thành công.
- Nếu không có ETag, hãy dừng thao tác ghi có điều kiện và kiểm tra cấu hình @Version, mapping repository hoặc response. Đừng tự đoán giá trị version.

### Kiểm soát mọi đường ghi dữ liệu

ETag của Spring Data REST chỉ bảo vệ các thao tác đi qua cơ chế tương ứng. Nếu ứng dụng còn có custom controller, batch job, scheduled job hoặc repository query update trực tiếp, các đường ghi đó cũng phải tôn trọng optimistic locking.

Đặc biệt, bulk update qua JPQL/SQL không đi theo vòng đời cập nhật entity thông thường. Không giả định chúng tự động áp dụng @Version như thao tác save entity. Nếu dùng bulk update, hãy thiết kế điều kiện version và tăng version một cách tường minh hoặc tải entity và cập nhật theo cơ chế versioned persistence.

Nếu representation của aggregate chứa dữ liệu từ entity liên quan, cần xác định thay đổi ở entity con có làm tăng version của aggregate root hay không. Nếu một thay đổi làm nội dung mà người dùng đang sửa thay đổi nhưng ETag của root không đổi, validator sẽ không phản ánh đúng phạm vi xung đột. Hãy chọn ranh giới aggregate và chiến lược version phù hợp.

### CORS với frontend khác origin

Nếu frontend chạy khác origin API, trình duyệt phải được phép đọc response header ETag và gửi request header If-Match. Cấu hình CORS cần:

- Expose response header ETag bằng Access-Control-Expose-Headers.
- Cho phép request header If-Match bằng Access-Control-Allow-Headers.
- Cho phép method cần dùng, chẳng hạn GET, PUT, PATCH và DELETE.
- Giới hạn origin theo domain frontend thực tế.

Nếu thiếu expose header, JavaScript có thể không đọc được ETag dù response trong DevTools có header đó. Nếu thiếu allow header, preflight có thể bị trình duyệt chặn trước khi gửi PATCH.

### Không sửa version thủ công

Version là metadata do persistence provider hoặc Spring Data datastore quản lý. Không nhận version do client gửi rồi gán trực tiếp vào entity. Nếu cần hiển thị revision trong UI, dùng ETag header làm token opaque. Đây là cách giữ cho client không phụ thuộc vào kiểu lưu trữ hoặc cách framework tạo version.

## 10. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| GET item không có ETag | Entity chưa có @Version, import annotation sai module, resource không đi qua Spring Data REST hoặc đang đọc collection | Kiểm tra version mapping và gọi đúng item URI |
| Hai client nhận ETag khác nhau dù chưa có ai cập nhật | Hai request không đọc cùng URI/resource, hoặc dữ liệu đã đổi giữa hai lần GET | Kiểm tra URI, ID và thời điểm đọc; tạo fixture ổn định trong test |
| PATCH stale vẫn thành công | Request thiếu If-Match, dùng wildcard * hoặc request đi qua custom endpoint không kiểm tra ETag | Kiểm tra request headers và đường xử lý thực tế |
| PATCH luôn trả 412 | Header đã bị sửa dấu ngoặc kép, dùng ETag từ URI khác hoặc dữ liệu đã thay đổi | Sao chép nguyên văn ETag mới nhất từ GET đúng item URI |
| A cập nhật thành công nhưng ETag không đổi | Version không được tăng, cập nhật không đi qua persistence versioning hoặc response không mang validator như dự kiến | Kiểm tra @Version, SQL/update path và response header sau khi lưu |
| UI không đọc được ETag | CORS chưa expose response header | Thêm ETag vào Access-Control-Expose-Headers |
| Browser không gửi được If-Match | CORS preflight không cho phép request header | Thêm If-Match vào Access-Control-Allow-Headers |
| Lỗi optimistic locking khi lưu từ background job | Một transaction khác đã cập nhật entity sau khi job đọc dữ liệu | Tải lại entity và quyết định retry theo nghiệp vụ; không ghi lại object cũ một cách mù quáng |
| Test không tái hiện xung đột | Mỗi client đọc lại resource sau lần ghi trước hoặc test vô tình dùng ETag mới cho cả hai | Giữ riêng ETag A và B lấy trước mọi thao tác ghi |
| Bulk update không phát hiện version cũ | JPQL/SQL bulk update bỏ qua vòng đời entity thông thường | Thêm điều kiện version và tăng version rõ ràng, hoặc cập nhật entity qua repository |
| Request thiếu If-Match vẫn được chấp nhận | Ứng dụng chưa áp dụng policy bắt buộc precondition | Nếu nghiệp vụ yêu cầu, bổ sung server-side enforcement và test status 428 |
| DELETE stale không bị từ chối | Delete không gửi If-Match hoặc endpoint tùy chỉnh bỏ qua ETag | Kiểm tra DELETE item resource và gửi validator hiện tại |

Khi debug, ghi nhận method, item URI, ETag server trả về, If-Match client gửi và status response. Không ghi nội dung nhạy cảm của entity hoặc token xác thực vào log chỉ để theo dõi xung đột.

## 11. Chạy kiểm thử

Maven:

~~~bash
./mvnw -Dtest=NoteEtagConcurrencyTests test
~~~

Gradle:

~~~bash
./gradlew test --tests '*NoteEtagConcurrencyTests'
~~~

Chạy toàn bộ test:

~~~bash
./mvnw test
~~~

hoặc:

~~~bash
./gradlew test
~~~

Nếu test cần database ngoài, khởi động database/Testcontainers theo cấu hình dự án. Hãy chạy test versioning trên datastore thật khi có khác biệt về transaction, dialect hoặc cơ chế cập nhật.

## 12. Tài liệu chính thức

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): cách @Version tạo ETag, dùng If-Match cho PUT/PATCH/DELETE, xử lý 412 và dùng If-None-Match cho GET/304.
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): URI collection/item, HTTP methods, media types và status codes của repository resource.
- [Spring Data Commons — @Version API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/annotation/Version.html): đánh dấu version property để thực hiện optimistic locking.
- [Jakarta Persistence — @Version API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Version.html): version field/property, kiểu dữ liệu và phát hiện optimistic lock failure.
- [Jakarta Persistence 3.2 — Optimistic Locking](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): nguyên tắc kiểm tra version khi cập nhật/xóa và trách nhiệm của persistence provider.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử đầy đủ Spring MVC request handling với mock request/response.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): ETag, If-None-Match, 304 và conditional request trong Spring MVC.
- [Spring Framework — Filters / Shallow ETag](https://docs.spring.io/spring/reference/web/webmvc/filters.html): giới hạn của ShallowEtagHeaderFilter đối với state-changing precondition.
- [RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1): ngữ nghĩa điều kiện If-Match và strong comparison.
