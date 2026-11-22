# Khóa lạc quan tại kho dữ liệu và điều kiện HTTP tại REST API

## 1. Mục tiêu

Khi nhiều client cùng đọc và cập nhật một resource, một client có thể vô tình ghi đè thay đổi mới hơn của client khác. Spring Data cung cấp cơ chế **optimistic locking** để phát hiện xung đột khi lưu entity. Spring Data REST kết nối cơ chế đó với HTTP conditional request thông qua ETag và các header If-Match, If-None-Match.

Hai lớp này phối hợp như sau:

- **Ở tầng persistence:** trường version được kiểm tra khi cập nhật hoặc xóa. Nếu dữ liệu trong database đã đổi kể từ lúc entity được đọc, thao tác có thể thất bại.
- **Ở tầng HTTP:** server trả ETag cho resource có version. Client gửi lại ETag bằng If-Match khi muốn thay đổi resource, để server chỉ thực hiện nếu resource vẫn ở phiên bản mà client đã đọc.
- **Với cache:** client gửi If-None-Match khi GET lại cùng resource. Nếu ETag chưa đổi, server có thể trả 304 Not Modified và không gửi lại representation.

Mục tiêu là tránh lost update và giảm dữ liệu truyền khi client đọc lại resource chưa thay đổi.

## 2. Optimistic locking là gì?

Optimistic locking giả định xung đột cập nhật không xảy ra thường xuyên. Thay vì khóa bản ghi trong suốt thời gian người dùng chỉnh sửa, hệ thống lưu một version marker và kiểm tra marker đó khi ghi.

Ví dụ hai client cùng đọc Customer có version 5:

1. Client A đọc version 5.
2. Client B cũng đọc version 5.
3. Client A cập nhật thành công; version tăng lên 6.
4. Client B gửi bản cập nhật dựa trên dữ liệu version 5.
5. Persistence layer phát hiện version trong database hiện là 6, nên từ chối ghi của B.

Nếu không có kiểm tra version, dữ liệu mới do A ghi có thể bị B ghi đè bằng một bản cũ. Đây là lỗi lost update.

Optimistic locking phù hợp khi xung đột tương đối hiếm và thời gian người dùng giữ bản dữ liệu để chỉnh sửa có thể dài. Nó tránh phải giữ database lock trong toàn bộ thời gian đó.

## 3. Khai báo version field

Với Spring Data JPA, dùng annotation jakarta.persistence.Version trên một thuộc tính của entity:

    import jakarta.persistence.Entity;
    import jakarta.persistence.GeneratedValue;
    import jakarta.persistence.Id;
    import jakarta.persistence.Version;

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
        private String email;

        @Version
        private Long version;

        // getters and setters
    }

JPA provider quản lý version field. Khi entity được lưu thành công, version được tăng theo cơ chế của provider. Không tự tăng version trong controller hoặc service; việc đó có thể phá vỡ cơ chế kiểm tra đồng thời.

Với các Spring Data module không dùng JPA, có thể dùng annotation org.springframework.data.annotation.Version tương ứng với store module. Spring Data REST dựa vào persistent entity metadata của store để nhận diện version property.

Chỉ thêm trường có tên version mà không đánh dấu annotation phù hợp chưa đủ để bật optimistic locking. Annotation phải đúng với persistence technology đang dùng.

## 4. Persistence layer kiểm tra version như thế nào?

Với JPA, khi cập nhật entity có version, provider tạo câu UPDATE có điều kiện theo cả ID và version hiện tại. SQL minh họa:

    UPDATE customer
       SET name = ?,
           email = ?,
           version = 6
     WHERE id = 42
       AND version = 5;

Nếu đúng một hàng được cập nhật, thao tác có thể thành công. Nếu không có hàng nào khớp, có thể bản ghi đã bị cập nhật hoặc xóa bởi transaction khác. JPA provider phát OptimisticLockException; Spring có thể dịch lỗi này thành OptimisticLockingFailureException ở tầng data access.

Câu SQL trên chỉ minh họa nguyên tắc. Câu lệnh thực tế, thời điểm flush và thời điểm exception xuất hiện phụ thuộc provider, transaction và database.

Với Spring Data JDBC/Relational, Spring Data cũng hỗ trợ optimistic locking bằng version property trên aggregate root. Khi version không còn khớp, thao tác save có thể ném OptimisticLockingFailureException. Chi tiết câu lệnh phụ thuộc store module.

Trong JPA, xung đột có thể chỉ được phát hiện tại flush hoặc commit. Vì vậy, không nên giả định exception luôn xảy ra ngay tại dòng gọi save. Transaction boundary và rollback rule quyết định trạng thái cuối cùng.

## 5. ETag trong Spring Data REST

ETag (Entity Tag) là một HTTP validator đại diện cho trạng thái của resource. Spring Data REST sử dụng version property được store metadata nhận diện để tạo ETag cho resource.

Ví dụ response:

    GET /customers/42
    Accept: application/hal+json

    HTTP/1.1 200 OK
    Content-Type: application/hal+json
    ETag: "5"

    {
      "name": "An Nguyen",
      "email": "an@example.com",
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/42"
        }
      }
    }

Giá trị 5 chỉ là ví dụ minh họa khi version hiện tại là 5. Hãy dùng chính xác ETag header mà server trả về. Client nên coi ETag là một token opaque, không tự tính hoặc sửa nội dung của nó.

Khi resource thay đổi và version tăng, ETag được trả về cho representation mới cũng thay đổi. Client có thể dùng token này để phát hiện dữ liệu đã cũ.

ETag của một item resource không nên bị dùng thay cho ETag của resource khác. Hãy gắn ETag với đúng URI/resource mà client đã lấy.

## 6. If-Match bảo vệ PUT, PATCH và DELETE

Khi client muốn thay đổi resource, gửi ETag đã nhận trong header If-Match:

    PATCH /customers/42
    Content-Type: application/merge-patch+json
    Accept: application/hal+json
    If-Match: "5"

    {
      "name": "An Nguyen Updated"
    }

Server chỉ thực hiện thao tác nếu ETag hiện tại của resource khớp với giá trị If-Match. Nếu resource vẫn ở version 5, request có thể được chấp nhận và response sẽ mang ETag mới, ví dụ:

    HTTP/1.1 200 OK
    ETag: "6"

Nếu một client khác đã cập nhật resource trước đó và version hiện tại là 6, request gửi If-Match với token version 5 không còn hợp lệ. Spring Data REST trả:

    HTTP/1.1 412 Precondition Failed

Đây là cách phát hiện stale update ở HTTP boundary. Client biết bản dữ liệu mình đang sửa đã cũ và cần tải lại resource, so sánh thay đổi rồi quyết định cách hợp nhất.

Spring Data REST cũng hỗ trợ conditional PUT và DELETE theo cùng nguyên tắc. Hãy dùng ETag từ lần GET gần nhất của chính resource đang được thay đổi.

Không gửi ETag của một Customer khác, một URL khác hoặc một query khác. Nếu API yêu cầu conditional write, client cần giữ token theo từng resource.

## 7. Kịch bản hai client cùng cập nhật

Giả sử A và B cùng đọc Customer 42:

    Client A                         Server                         Client B
       |                               |                               |
       |--- GET /customers/42 -------> |                               |
       |<-- 200, ETag: "5" ------------|                               |
       |                               | <------ GET /customers/42 ---|
       |                               | ------ 200, ETag: "5" ------->|
       |                               |                               |
       |--- PATCH, If-Match: "5" ----> |                               |
       |<-- 200, ETag: "6" ------------|                               |
       |                               |                               |
       |                               | <--- PATCH, If-Match: "5" ----|
       |                               | ------ 412 Precondition Failed|
       |                               |                               |

Client A cập nhật trước nên version đổi từ 5 sang 6. Client B vẫn giữ ETag 5; server từ chối thay đổi của B để không ghi đè dữ liệu mới.

Sau 412, client B nên:

1. GET lại resource để nhận representation và ETag mới.
2. So sánh dữ liệu hiện tại với thay đổi người dùng đã nhập.
3. Hợp nhất thủ công hoặc theo quy tắc nghiệp vụ nếu có thể.
4. Gửi request mới với If-Match mới sau khi người dùng hoặc logic nghiệp vụ chấp thuận.

Không tự động gửi lại cùng payload với ETag mới mà không kiểm tra. Làm như vậy có thể ghi đè thay đổi của client A và vô hiệu hóa mục đích của optimistic locking.

## 8. If-None-Match giúp GET tiết kiệm dữ liệu

If-None-Match dùng cho conditional GET. Client lưu ETag nhận được từ lần GET trước và gửi lại khi muốn kiểm tra resource có thay đổi không:

    GET /customers/42
    Accept: application/hal+json
    If-None-Match: "6"

Nếu ETag hiện tại vẫn khớp, server có thể trả:

    HTTP/1.1 304 Not Modified

Response 304 không cần gửi lại body resource. Client giữ representation đã cache và biết rằng bản đang lưu vẫn hợp lệ theo validator.

Nếu resource đã thay đổi, server trả representation mới với status thành công và ETag mới:

    HTTP/1.1 200 OK
    ETag: "7"

    {
      "name": "An Nguyen Updated",
      "email": "an@example.com"
    }

Dùng ETag cho đúng resource và đúng URI. Khi request có query parameter hoặc biến thể representation khác, không tùy tiện dùng validator lấy từ một request khác.

## 9. Phân biệt If-Match và If-None-Match

| Header | Thường dùng cho | Điều kiện | Kết quả điển hình |
|---|---|---|---|
| If-Match | PUT, PATCH, DELETE | Chỉ thay đổi nếu ETag hiện tại khớp | Thực hiện thao tác hoặc 412 |
| If-None-Match | GET | Chỉ gửi representation nếu ETag không khớp | 200 với body mới hoặc 304 |
| If-Modified-Since | GET | Kiểm tra resource có thay đổi sau thời điểm đã biết | 200 với body mới hoặc 304 |

If-Match giải quyết xung đột cập nhật. If-None-Match chủ yếu tránh tải lại nội dung không thay đổi. Hai header có mục tiêu khác nhau dù cùng dùng ETag.

Spring Data REST cũng hỗ trợ Last-Modified và If-Modified-Since trong các conditional request phù hợp. Với tài nguyên có version property, ETag thường là validator phù hợp cho optimistic locking vì nó gắn trực tiếp với version marker.

## 10. Ví dụ kiểm thử bằng curl

Đầu tiên GET resource và lưu ETag:

    curl -i \
      -H 'Accept: application/hal+json' \
      http://localhost:8080/customers/42

Đọc header ETag trong response. Giả sử server trả ETag là giá trị version 5.

Thử cập nhật với version hiện tại:

    curl -i -X PATCH \
      -H 'Accept: application/hal+json' \
      -H 'Content-Type: application/merge-patch+json' \
      -H 'If-Match: "5"' \
      -d '{"name":"An Nguyen Updated"}' \
      http://localhost:8080/customers/42

Sau khi cập nhật thành công, response trả ETag mới. Thử gửi lại request với ETag cũ để mô phỏng client stale; kết quả mong đợi theo conditional behavior là 412 Precondition Failed.

Thử conditional GET với ETag mới nhất:

    curl -i \
      -H 'Accept: application/hal+json' \
      -H 'If-None-Match: "6"' \
      http://localhost:8080/customers/42

Nếu resource chưa thay đổi kể từ ETag 6, server có thể trả 304 Not Modified.

Các giá trị version và ETag trong lệnh chỉ là ví dụ. Hãy sao chép header thực tế từ response trước đó. Định dạng Content-Type của PATCH cũng cần khớp với cấu hình endpoint và media type mà ứng dụng hỗ trợ.

## 11. Kiểm thử optimistic locking ở tầng repository

Có thể kiểm tra bằng hai transaction hoặc hai entity instance đại diện cho hai client:

1. Đọc cùng một entity ở hai persistence context.
2. Cập nhật và commit instance thứ nhất.
3. Thử lưu instance thứ hai dựa trên version cũ.
4. Xác nhận lần lưu thứ hai thất bại với optimistic locking exception.
5. Xác nhận dữ liệu cuối cùng giữ thay đổi đã commit đầu tiên.

Ví dụ kiểm tra ở mức khái niệm:

    Customer first = repository.findById(id).orElseThrow();
    Customer second = repository.findById(id).orElseThrow();

    first.setName('Updated by A');
    repository.saveAndFlush(first);

    second.setName('Updated by B');

    assertThatThrownBy(() -> {
        repository.saveAndFlush(second);
    }).isInstanceOf(OptimisticLockingFailureException.class);

Test trên chỉ đúng khi hai entity được đọc trong persistence context độc lập hoặc bị detach/refresh phù hợp. Nếu cùng một persistence context trả lại cùng object instance, test sẽ không mô phỏng được hai client độc lập.

Với JPA, có thể dùng hai transaction và hai EntityManager để kiểm soát rõ ràng trạng thái version. Hãy flush để buộc provider thực thi UPDATE và phát hiện xung đột trước khi assertion kết thúc.

## 12. Integration test ETag qua Spring Data REST

Integration test nên xác nhận cả HTTP headers và trạng thái dữ liệu.

Ví dụ luồng kiểm thử với MockMvc:

    MvcResult firstGet = mockMvc.perform(
            get('/customers/{id}', id)
                .accept('application/hal+json'))
        .andExpect(status().isOk())
        .andReturn();

    String etag = firstGet.getResponse()
        .getHeader(HttpHeaders.ETAG);

    assertThat(etag).isNotBlank();

Dùng ETag vừa nhận để cập nhật:

    mockMvc.perform(patch('/customers/{id}', id)
            .header(HttpHeaders.IF_MATCH, etag)
            .contentType('application/merge-patch+json')
            .accept('application/hal+json')
            .content('{"name":"Updated"}'))
        .andExpect(status().is2xxSuccessful());

Lấy ETag mới sau update, rồi gửi lại một request dùng ETag cũ:

    mockMvc.perform(patch('/customers/{id}', id)
            .header(HttpHeaders.IF_MATCH, etag)
            .contentType('application/merge-patch+json')
            .content('{"name":"Stale update"}'))
        .andExpect(status().isPreconditionFailed());

Kiểm tra GET có If-None-Match:

    mockMvc.perform(get('/customers/{id}', id)
            .header(HttpHeaders.IF_NONE_MATCH, newEtag)
            .accept('application/hal+json'))
        .andExpect(status().isNotModified());

Đây là skeleton minh họa. Cần tạo entity trước test, dùng đúng PATCH media type, và xác nhận endpoint cùng phiên bản Spring Data REST thực tế hỗ trợ các thao tác đó. Không hard-code ETag 5 hoặc 6; luôn lấy token từ response.

## 13. Những giới hạn và lỗi thường gặp

**Quên version annotation**

Một thuộc tính tên version nhưng không được đánh dấu đúng annotation có thể không bật optimistic locking hoặc ETag. Dùng JPA @Version cho JPA và Spring Data @Version cho store module tương ứng.

**Tự tăng version**

Không tự sửa version trong controller hoặc client. Persistence framework quản lý việc tăng version sau thao tác thành công.

**Bỏ qua If-Match khi cập nhật**

Client gửi payload dựa trên dữ liệu cũ có thể ghi đè thay đổi mới nếu không dùng conditional write. Với resource versioned, hãy giữ và gửi ETag của lần đọc gần nhất.

**Dùng sai ETag**

ETag là validator của một representation/resource cụ thể. Không dùng token của resource khác hoặc tự tạo token từ version field.

**Xem 412 là lỗi server**

412 Precondition Failed thường là xung đột điều kiện mà client cần xử lý: tải dữ liệu mới, hợp nhất thay đổi và gửi lại khi phù hợp.

**Nhầm 304 với response rỗng thông thường**

304 Not Modified là kết quả conditional GET. Client nên dùng representation đã cache; không parse response như JSON body mới.

**Cho rằng AfterSave luôn đã commit**

ETag và version phản ánh trạng thái resource qua persistence metadata. Tuy nhiên, transaction boundary vẫn quyết định khi nào dữ liệu được commit. Không suy ra commit chỉ từ việc một callback sau save đã chạy.

**Không kiểm tra transaction**

Optimistic locking exception có thể xuất hiện tại flush hoặc commit. Integration test phải chạy qua transaction boundary phù hợp và xác nhận rollback/persistence state.

## 14. Bài tập thực hành

Với Customer resource có id, name, email và version:

1. Thêm version property với JPA @Version.
2. Khởi động ứng dụng và GET một Customer resource.
3. Kiểm tra response có ETag header hay không.
4. Lưu ETag cùng self URI trong client state.
5. Gửi PATCH với If-Match bằng ETag vừa nhận.
6. Xác nhận update thành công và response trả ETag mới.
7. Gửi request thứ hai với ETag cũ; xác nhận server trả 412.
8. GET lại resource, so sánh dữ liệu mới với thay đổi client đang giữ và thực hiện merge theo nghiệp vụ.
9. GET với If-None-Match bằng ETag mới nhất; xác nhận 304 nếu resource chưa thay đổi.
10. Viết repository test mô phỏng hai persistence context cùng sửa một entity.
11. Viết MockMvc integration test cho success, stale update và conditional GET.
12. Thử xóa resource bằng If-Match và xác nhận version cũ không xóa được resource đã thay đổi.

Câu hỏi tự kiểm tra:

- Optimistic locking phát hiện lost update bằng cách nào?
- JPA @Version khác Spring Data @Version ở phạm vi sử dụng ra sao?
- Spring Data REST dùng version property để tạo ETag như thế nào?
- Khi nào client cần gửi If-Match?
- Vì sao stale ETag dẫn tới 412?
- If-None-Match giúp giảm dữ liệu truyền như thế nào?
- Vì sao không được tự tăng version hoặc tự tạo ETag?
- Vì sao test cần mô phỏng hai persistence context hoặc hai client độc lập?

## 15. Ghi nhớ

- Optimistic locking phát hiện xung đột ghi bằng version marker.
- JPA dùng jakarta.persistence.Version; các Spring Data store khác có thể dùng org.springframework.data.annotation.Version.
- Persistence layer kiểm tra version khi cập nhật và tăng version khi lưu thành công.
- Spring Data REST dùng version property được nhận diện để tạo ETag cho resource.
- PUT, PATCH và DELETE có thể được conditionalize bằng If-Match.
- ETag không khớp dẫn tới HTTP 412 Precondition Failed.
- GET với If-None-Match có thể trả 304 Not Modified khi resource chưa đổi.
- Dùng đúng ETag của đúng resource; không tự tạo hoặc chỉnh token.
- Sau 412, tải dữ liệu mới và hợp nhất thay đổi trước khi thử lại.
- Kiểm thử cả exception ở repository layer, HTTP headers và trạng thái persistence.

## Tài liệu tham khảo

- Spring Data REST Reference — Conditional Operations with Headers: https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html
- Spring Data Commons — Version: https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/annotation/Version.html
- Jakarta Persistence — Optimistic Locking and Version: https://jakarta.ee/specifications/persistence/
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html