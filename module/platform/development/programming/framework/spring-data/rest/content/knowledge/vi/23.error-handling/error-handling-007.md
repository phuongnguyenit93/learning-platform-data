# HTTP 412 Precondition Failed khi điều kiện If-Match không còn hợp lệ

## 1. Ý nghĩa của lỗi

HTTP 412 xảy ra khi một điều kiện được gửi trong request header không còn đúng với trạng thái hiện tại của resource trên server. Trong Spring Data REST, trường hợp thường gặp là client gửi một giá trị If-Match cũ sau khi resource đã được client khác cập nhật.

Đây là cơ chế optimistic concurrency control (kiểm soát đồng thời lạc quan). Nó ngăn tình huống “lost update”: hai người cùng đọc một bản ghi, người thứ nhất lưu thay đổi, rồi người thứ hai vô tình ghi đè dữ liệu mới bằng bản sao cũ.

Spring Data REST dùng ETag để đánh dấu phiên bản resource. Nếu domain object có trường version được nhận diện bằng @Version, ETag của resource được tạo từ giá trị version đó. Với Spring Data JPA, dùng annotation @Version của JPA; với các module Spring Data khác, dùng org.springframework.data.annotation.Version. Khi client gửi PUT, PATCH hoặc DELETE kèm If-Match, Spring Data REST chỉ thực hiện thao tác nếu ETag hiện tại khớp với giá trị client gửi. Nếu không khớp, request nhận HTTP 412 Precondition Failed.

## 2. Chuỗi nguyên nhân dẫn đến 412

Giả sử hai client A và B cùng đọc resource /people/42:

1. A gửi GET /people/42 và nhận ETag: "5".
2. B cũng gửi GET /people/42 và nhận ETag: "5".
3. A cập nhật resource với If-Match: "5". Điều kiện còn đúng nên thao tác thành công; server lưu phiên bản mới và trả về ETag mới, ví dụ "6".
4. B vẫn giữ bản sao cũ và gửi cập nhật với If-Match: "5".
5. ETag hiện tại đã là "6", vì vậy điều kiện If-Match của B sai. Server trả 412 và không áp dụng thay đổi của B.

Các số "5" và "6" chỉ minh họa. Giá trị ETag thực tế phụ thuộc vào persistence store và phiên bản resource. Client phải coi ETag là chuỗi opaque do server cấp, không tự phân tích hoặc tự tăng version.

## 3. Cấu hình version để Spring Data REST phát ETag

Với entity JPA, khai báo một trường version trên domain object:

    import com.fasterxml.jackson.annotation.JsonIgnore;
    import jakarta.persistence.Entity;
    import jakarta.persistence.GeneratedValue;
    import jakarta.persistence.Id;
    import jakarta.persistence.Version;

    @Entity
    public class Person {

        @Id
        @GeneratedValue
        private Long id;

        private String firstName;
        private String lastName;

        @Version
        @JsonIgnore
        private Long version;

        protected Person() {
        }

        public Person(String firstName, String lastName) {
            this.firstName = firstName;
            this.lastName = lastName;
        }

        public Long getId() {
            return id;
        }

        public String getFirstName() {
            return firstName;
        }
    }

Dùng jakarta.persistence.Version với ứng dụng Jakarta Persistence hiện đại; dự án cũ dùng javax.persistence.Version. Với Spring Data MongoDB, Cassandra hoặc module Spring Data khác, dùng org.springframework.data.annotation.Version theo tài liệu của module tương ứng.

Trường version do persistence layer quản lý. Không yêu cầu client gửi hoặc tự cập nhật trường này. @JsonIgnore là tùy chọn nếu không muốn đưa version vào JSON body; Spring Data REST vẫn có thể dùng metadata version để tạo ETag response header.

Hãy kiểm tra GET trên URI của một resource cụ thể, ví dụ /people/42. Dữ liệu nhúng trong response của collection chỉ là preview; muốn lấy ETag, hãy gọi URI self của từng item. Response thành công cần có header tương tự:

    HTTP/1.1 200 OK
    ETag: "5"
    Content-Type: application/hal+json

Nếu không có ETag, hãy kiểm tra annotation @Version có đúng loại cho persistence module hay không và trường version có nằm trên domain object được repository quản lý hay không.

## 4. Gửi request có điều kiện

Đầu tiên, đọc resource và lưu nguyên giá trị ETag từ response:

    curl -i http://localhost:8080/people/42

Giả sử response trả về ETag: "5". Dùng chính giá trị đó trong request cập nhật:

    curl -i -X PATCH http://localhost:8080/people/42 -H 'Content-Type: application/json' -H 'If-Match: "5"' --data '{"firstName":"Lan"}'

Nếu resource vẫn có ETag "5", thao tác được chấp nhận. Sau khi cập nhật, response có thể trả về ETag mới. Client nên lưu ETag mới cùng representation vừa nhận.

Để tái hiện lỗi, thực hiện một cập nhật thành công trước, sau đó gửi request thứ hai bằng ETag cũ:

    curl -i -X PATCH http://localhost:8080/people/42 -H 'Content-Type: application/json' -H 'If-Match: "5"' --data '{"firstName":"Linh"}'

Nếu cập nhật đầu tiên đã làm thay đổi version, request thứ hai nhận 412 Precondition Failed. Thay đổi trong body của request thứ hai không được ghi vào resource.

Có thể dùng cùng cơ chế với PUT và DELETE. Với PUT, gửi representation đầy đủ theo contract của endpoint. Với PATCH, chỉ gửi các trường cần thay đổi. Trong cả hai trường hợp, lấy If-Match từ ETag của lần đọc resource gần nhất.

Lưu ý:
- Giữ nguyên dấu ngoặc kép trong ETag nếu server trả về giá trị có dấu ngoặc kép. Không tự bỏ dấu hoặc nối thêm tiền tố.
- Dùng ETag cho đúng URI resource mà client đã đọc. Không dùng token của một item cho item khác hoặc tái sử dụng token từ một truy vấn khác.
- If-Match: * chỉ kiểm tra resource có tồn tại; nó không bảo vệ bản cập nhật khỏi một phiên bản cũ. Muốn phát hiện dữ liệu đã đổi, gửi ETag cụ thể.
- Không tự tăng giá trị version và không lấy trường version trong JSON để thay cho response header ETag.

## 5. Xử lý 412 ở client

412 là tín hiệu cho biết bản sao mà người dùng đang sửa đã cũ. Cách xử lý an toàn:

1. Giữ lại nội dung người dùng định lưu và hiển thị thông báo dữ liệu đã thay đổi.
2. Gọi GET lại đúng URI resource để lấy representation và ETag hiện tại.
3. So sánh bản người dùng đã sửa với bản mới trên server. Giữ lại các chỉnh sửa không xung đột và yêu cầu người dùng chọn khi cùng một trường đã bị thay đổi ở cả hai phía.
4. Sau khi hợp nhất, gửi request mới với ETag vừa lấy từ GET mới.
5. Nếu lại nhận 412, lặp lại bước đọc và hòa giải vì resource có thể tiếp tục được người khác cập nhật.

Không tự động gửi lại nguyên body cũ với ETag mới. Làm vậy sẽ bỏ qua ý nghĩa của optimistic locking và có thể ghi đè chính thay đổi mà 412 đang bảo vệ.

Ví dụ logic phía client:

    const response = await updateResource(uri, draft, oldEtag);

    if (response.status === 412) {
        const latest = await fetchResource(uri);
        showConflictResolution({
            userDraft: draft,
            serverVersion: latest.body,
            currentEtag: latest.headers.get("ETag")
        });
    }

Sau khi người dùng xác nhận bản đã hợp nhất, gửi update với currentEtag. Không phụ thuộc vào nội dung body của response 412 vì body lỗi có thể thay đổi theo cấu hình xử lý exception; dùng status code để nhận diện precondition failure.

Nếu frontend chạy khác origin với API, cấu hình CORS để browser được gửi header If-Match và đọc response header ETag. Cụ thể, Access-Control-Allow-Headers cần cho phép If-Match và Access-Control-Expose-Headers cần công khai ETag. Nếu thiếu expose header, JavaScript có thể không đọc được ETag dù header xuất hiện trong response trên mạng.

## 6. Phân biệt 412, 409 và 304

- 412 Precondition Failed: điều kiện request như If-Match không đúng với trạng thái hiện tại. Với Spring Data REST, đây là phản hồi cho cập nhật có ETag cũ.
- 409 Conflict: request xung đột với trạng thái hoặc quy tắc nghiệp vụ của resource. Đây là tình huống conflict ở cấp ứng dụng; không đồng nghĩa với If-Match thất bại.
- 304 Not Modified: response cho GET/HEAD có điều kiện cache như If-None-Match hoặc If-Modified-Since khi representation chưa đổi. 304 không phải lỗi cập nhật.

If-Match chủ yếu bảo vệ các thao tác thay đổi trạng thái. If-None-Match thường dùng để tránh tải lại representation không đổi khi GET.

## 7. Kiểm thử hồi quy

### Kiểm thử thủ công bằng hai client

1. Tạo một bản ghi và gọi GET trên URI item để lấy ETag.
2. Mở hai client A và B; cả hai đọc cùng resource và lưu cùng ETag ban đầu.
3. A gửi PATCH với ETag ban đầu. Xác nhận response thành công.
4. B gửi PATCH với ETag cũ. Xác nhận response có status 412.
5. Gọi GET để xác nhận giá trị do A lưu vẫn còn nguyên, thay đổi của B chưa được áp dụng và ETag đã đổi.
6. B đọc representation mới, hợp nhất thay đổi rồi gửi PATCH với ETag mới. Xác nhận thao tác thành công.
7. Lặp lại tình huống với DELETE để kiểm tra endpoint xóa cũng từ chối ETag cũ.

### Mẫu integration test với MockMvc

Đặt test trong Spring Boot integration context để Spring Data REST đăng ký repository endpoint thật. Ví dụ dưới đây giả định có PersonRepository, entity Person và endpoint /people/{id}; thay constructor, tên thuộc tính và đường dẫn theo ứng dụng.

    @SpringBootTest
    @AutoConfigureMockMvc
    class PersonIfMatchTests {

        @Autowired
        MockMvc mvc;

        @Autowired
        PersonRepository people;

        @Test
        void rejectsUpdateWhenIfMatchIsStale() throws Exception {
            Person person = people.save(new Person("Alice", "Nguyen"));
            String path = "/people/" + person.getId();

            String etagA = mvc.perform(get(path))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getHeader(HttpHeaders.ETAG);

            String etagB = mvc.perform(get(path))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getHeader(HttpHeaders.ETAG);

            assertThat(etagA).isNotBlank();
            assertThat(etagB).isEqualTo(etagA);

            mvc.perform(patch(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.IF_MATCH, etagA)
                    .content("{\"firstName\":\"Alicia\"}"))
                    .andExpect(status().is2xxSuccessful());

            mvc.perform(patch(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.IF_MATCH, etagB)
                    .content("{\"firstName\":\"Ally\"}"))
                    .andExpect(status().isPreconditionFailed());

            Person stored = people.findById(person.getId()).orElseThrow();
            assertThat(stored.getFirstName()).isEqualTo("Alicia");
        }
    }

Các static import thường dùng trong test:

    import static org.assertj.core.api.Assertions.assertThat;
    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

    import org.springframework.http.HttpHeaders;
    import org.springframework.http.MediaType;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.test.web.servlet.MockMvc;
    import org.junit.jupiter.api.Test;

Test xác nhận ba điều: GET resource trả về ETag; cập nhật bằng ETag hiện tại thành công; request thứ hai dùng ETag cũ nhận 412 và không ghi đè dữ liệu đã lưu. Nên bổ sung test cho DELETE với ETag cũ và test CORS nếu frontend gọi API từ origin khác.

## 8. Checklist xử lý sự cố

| Hiện tượng | Kiểm tra và cách xử lý |
|---|---|
| GET không có ETag | Gọi URI item thay vì collection; kiểm tra @Version và loại annotation đúng với persistence module. |
| Request luôn nhận 412 | Lấy lại ETag bằng GET ngay trước khi cập nhật; kiểm tra đúng URI, giữ nguyên dấu ngoặc kép và kiểm tra request thực tế có gửi If-Match. |
| Hai người cập nhật nhưng thay đổi cũ vẫn ghi đè | Xác nhận entity có version được Spring Data REST nhận diện; xác nhận client không bỏ header If-Match. |
| Browser không đọc được ETag | Cấu hình Access-Control-Expose-Headers: ETag và cho phép If-Match trong CORS preflight. |
| GET trả 304 | Kiểm tra client đang gửi If-None-Match; 304 là kết quả cache validation, khác với 412 của precondition thất bại khi cập nhật. |
| Log có ETagDoesntMatchException | Kiểm tra ETag kỳ vọng và version hiện tại của entity; exception này biểu thị ETag tính từ object không khớp ETag được yêu cầu. |

## 9. Tài liệu tham khảo

- [Spring Data REST 5.1.2 — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): cách @Version tạo ETag, dùng If-Match cho PUT/PATCH/DELETE và phản hồi 412.
- [Spring — React.js and Spring Data REST: Part 3, Conditional Operations](https://spring.io/blog/2015/09/29/react-js-and-spring-data-rest-part-3-conditional-operations/): ví dụ entity có @Version, lấy ETag từ GET item và xử lý status 412 phía client.
- [RFC 9110, Section 13.1.1 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1): cú pháp, strong comparison và quy tắc không thực hiện method khi điều kiện sai.
- [RFC 9110, Section 13.2.2 — Precedence of Preconditions](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.2.2): thứ tự đánh giá các điều kiện HTTP.
- [RFC 9110, Section 15.5.13 — 412 Precondition Failed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.13): ý nghĩa chuẩn của status 412.
- [Spring Data REST API — ETagDoesntMatchException](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/support/ETagDoesntMatchException.html): exception khi ETag tính từ object không khớp giá trị kỳ vọng.
