# profile của link

Trong Spring HATEOAS, `Link` không chỉ chứa URI và relation. Một link còn có thể mang metadata giúp client hiểu rõ hơn về tài nguyên đích. Một thuộc tính như vậy là `profile`: nó cung cấp URI nhận diện profile ngữ nghĩa của tài nguyên mà link trỏ tới.

Profile mô tả những quy ước, ràng buộc hoặc phần mở rộng bổ sung áp dụng cho biểu diễn tài nguyên. Ví dụ, một API có thể công bố tài nguyên sách theo profile `book`, trong đó định nghĩa ý nghĩa của trường `isbn`, quy tắc chuẩn hóa tên tác giả và cách diễn giải trạng thái xuất bản. Client hiểu profile có thể xử lý biểu diễn theo các quy ước bổ sung đó; client chưa biết profile vẫn có thể xử lý tài nguyên theo ngữ nghĩa cơ bản của media type.

Spring HATEOAS cung cấp `Link.withProfile(String)` để gắn profile vào link và `Link.getProfile()` để đọc giá trị này. Khi serialize theo HAL, profile của link được biểu diễn bằng thuộc tính `profile` trong Link Object. Cần phân biệt thuộc tính này với relation có tên `profile`: hai cơ chế có liên quan nhưng trả lời những câu hỏi khác nhau.

Sau bài học, bạn có thể:

- Giải thích profile ngữ nghĩa là gì và nó bổ sung điều gì cho media type.
- Phân biệt `Link.profile` với link relation `profile`.
- Gắn profile vào link bằng `withProfile(...)` và đọc bằng `getProfile()`.
- Tạo link có profile bằng Spring HATEOAS và kiểm tra kết quả HAL.
- Thiết kế URI profile ổn định, mô tả rõ hợp đồng và hỗ trợ client chưa biết profile.
- Tránh dùng profile thay cho relation, media type hoặc cơ chế phân quyền.

## 1. Profile trong hypermedia là gì?

Media type mô tả định dạng và ngữ nghĩa cơ bản của một biểu diễn. Ví dụ:

- `application/json`: dữ liệu JSON.
- `application/hal+json`: JSON theo quy ước hypermedia HAL.

Tuy nhiên, media type không định nghĩa toàn bộ quy tắc của từng miền nghiệp vụ. Hai API cùng trả HAL JSON có thể dùng các trường và quy ước khác nhau. Profile giúp nhận diện phần ngữ nghĩa bổ sung đó mà không cần tạo một media type mới cho mọi biến thể.

Ví dụ, API thư viện có thể công bố một biểu diễn sách theo profile:

~~~text
https://api.example.com/profiles/book
~~~

Tài liệu profile có thể mô tả:

- `isbn` là mã ISBN-13 đã chuẩn hóa.
- `publicationDate` dùng ngày theo ISO 8601.
- `status` chỉ nhận các giá trị DRAFT, PUBLISHED hoặc ARCHIVED.
- `author` là quan hệ đến biểu diễn tác giả.
- Các quy tắc bổ sung khi client hiển thị hoặc xử lý dữ liệu sách.

Profile không thay đổi ý nghĩa cơ bản của media type. Nó bổ sung quy ước mà client hiểu profile có thể dùng để xử lý biểu diễn chính xác hơn. Một client không hiểu profile vẫn phải có khả năng xử lý biểu diễn theo hợp đồng cơ bản của media type.

### 1.1. Profile được nhận diện bằng URI

Profile được nhận diện bằng URI. URI đó đóng vai trò định danh; nó không bắt buộc phải là một trang có thể truy cập bằng HTTP. Tuy nhiên, với API có client bên ngoài, nên cung cấp tài liệu tại URI profile để lập trình viên có thể tìm hiểu các quy ước.

Một URI profile nên:

- Ổn định trong thời gian dài.
- Có ý nghĩa rõ ràng và không tái sử dụng cho hợp đồng khác.
- Mô tả những quy ước bổ sung một cách cụ thể.
- Có thể được tài liệu hóa bằng HTML, JSON hoặc định dạng máy đọc được.
- Được quản lý như một phần của hợp đồng API.

Không nên dùng URI profile làm URI của từng bản ghi. Ví dụ, URI profile `https://api.example.com/profiles/book` nhận diện hợp đồng của biểu diễn sách; URI `https://api.example.com/books/42` nhận diện một cuốn sách cụ thể.

### 1.2. Profile không thay thế media type

Media type và profile có vai trò riêng:

| Thuộc tính | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Media type | Biểu diễn được mã hóa theo định dạng nào? | `application/hal+json` |
| Profile | Quy ước ngữ nghĩa bổ sung nào áp dụng? | `https://api.example.com/profiles/book` |
| Relation | Tài nguyên đích liên quan với tài nguyên hiện tại như thế nào? | `author`, `self`, `reviews` |
| href | Client truy cập URI nào? | `/books/42` |

Không dùng profile để nói rằng nội dung là JSON hay HAL. Đó là trách nhiệm của media type. Cũng không dùng profile để thay thế relation: relation cho biết lý do có liên kết, còn profile mô tả ngữ nghĩa của biểu diễn ở đích liên kết.

## 2. Thuộc tính profile của một Link

Spring HATEOAS biểu diễn liên kết bằng lớp `org.springframework.hateoas.Link`. Ngoài href và rel, lớp này hỗ trợ các metadata như:

- `type`: gợi ý media type của biểu diễn tại URI đích.
- `title`: nhãn dễ đọc cho liên kết.
- `hreflang`: ngôn ngữ của tài nguyên đích.
- `name`: tên bổ sung để phân biệt các link cùng relation.
- `deprecation`: URI cung cấp thông tin về việc link sẽ bị ngừng hỗ trợ.
- `profile`: URI nhận diện profile của tài nguyên đích.

Ví dụ, một link đến tác giả có thể cho biết đích là HAL JSON theo profile tác giả:

~~~json
{
  "_links": {
    "author": {
      "href": "https://api.example.com/authors/17",
      "type": "application/hal+json",
      "profile": "https://api.example.com/profiles/author",
      "title": "Tác giả của cuốn sách"
    }
  }
}
~~~

Client có thể đọc metadata trước khi truy cập URI. `type` gợi ý định dạng biểu diễn được mong đợi; `profile` gợi ý những quy ước bổ sung áp dụng cho biểu diễn của tác giả.

### 2.1. Profile của link mô tả tài nguyên đích

Đây là điểm quan trọng nhất: thuộc tính `profile` trong một Link Object mô tả profile của tài nguyên ở `href`.

Ví dụ:

~~~json
{
  "id": "42",
  "title": "REST in Practice",
  "_links": {
    "author": {
      "href": "/authors/17",
      "profile": "https://api.example.com/profiles/author"
    }
  }
}
~~~

Profile `author` áp dụng cho biểu diễn tại `/authors/17`. Nó không có nghĩa tài nguyên sách hiện tại tuân theo profile tác giả. Tài nguyên hiện tại là sách; link author trỏ đến một tài nguyên tác giả.

Tương tự, nếu link self có profile:

~~~json
{
  "id": "42",
  "title": "REST in Practice",
  "_links": {
    "self": {
      "href": "/books/42",
      "profile": "https://api.example.com/profiles/book"
    }
  }
}
~~~

Thì profile đó mô tả biểu diễn của chính tài nguyên sách tại URI self.

### 2.2. Profile là metadata tùy chọn

Không phải mọi link đều cần profile. Chỉ thêm profile khi nó giúp client hiểu hợp đồng của tài nguyên đích. Một link đến trang trợ giúp đơn giản có thể không cần profile. Một link đến một tài nguyên nghiệp vụ có cấu trúc và quy ước riêng có thể có profile hữu ích.

Không nên gắn một profile chỉ vì API có định nghĩa URI profile. Hãy bảo đảm profile đó thực sự áp dụng cho biểu diễn đích của link.

## 3. Gắn profile bằng Spring HATEOAS

Spring HATEOAS cung cấp phương thức:

~~~java
Link withProfile(@Nullable String profile)
~~~

Phương thức nhận URI profile dạng chuỗi và trả về một `Link` mới với thuộc tính profile được cập nhật. `Link` là value object; các phương thức `with...` tạo bản sao có metadata mới. Vì vậy, cần gán kết quả trả về vào biến hoặc nối lời gọi tiếp theo.

### 3.1. Tạo Link với profile

~~~java
private static final String AUTHOR_PROFILE =
    "https://api.example.com/profiles/author";

Link authorLink = Link.of("/authors/17", "author")
    .withType("application/hal+json")
    .withProfile(AUTHOR_PROFILE)
    .withTitle("Tác giả của cuốn sách");
~~~

Trong ví dụ:

- `Link.of(..., "author")` tạo link với relation author.
- `withType(...)` mô tả media type dự kiến của tài nguyên đích.
- `withProfile(...)` gắn profile của tài nguyên đích.
- `withTitle(...)` thêm nhãn dễ đọc.

Có thể tạo link từ controller mapping thay vì ghi URI thủ công:

~~~java
private static final String BOOK_PROFILE =
    "https://api.example.com/profiles/book";

Link selfLink = linkTo(
    methodOn(BookController.class).one(bookId)
).withSelfRel()
 .withType("application/hal+json")
 .withProfile(BOOK_PROFILE);
~~~

Các import chính:

~~~java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Lời gọi `methodOn` mô tả phương thức controller và tham số để Spring HATEOAS dựng URI theo mapping. Nó không thực thi logic nghiệp vụ của controller.

### 3.2. Đọc profile từ Link

Có thể lấy profile đã gắn bằng `getProfile()`:

~~~java
String profile = authorLink.getProfile();
~~~

Giá trị có thể là `null` nếu link không có profile. Vì vậy, khi xử lý link từ nguồn không hoàn toàn nằm trong quyền kiểm soát của ứng dụng, hãy kiểm tra giá trị trước khi dùng:

~~~java
String profile = authorLink.getProfile();

if (profile != null) {
    profileRegistry.lookup(profile)
        .ifPresent(profileDefinition -> process(authorLink, profileDefinition));
}
~~~

Ví dụ giả định ứng dụng có `profileRegistry` để tra cứu các profile mà client biết. Không nên tải và thực thi tùy tiện mọi URI profile nhận được từ API. Profile URI là dữ liệu hợp đồng; client có thể so khớp với danh sách profile được hỗ trợ hoặc đọc tài liệu theo chính sách của ứng dụng.

### 3.3. Cập nhật hoặc bỏ profile

Vì `withProfile` trả về Link mới, có thể thay profile bằng một giá trị khác:

~~~java
Link revised = authorLink.withProfile(
    "https://api.example.com/profiles/author-v2"
);
~~~

Để xóa profile, API cho phép truyền `null`:

~~~java
Link withoutProfile = authorLink.withProfile(null);
~~~

Khi thay đổi profile của một link đã công bố, cần xem đó là thay đổi hợp đồng. Client có thể dựa vào URI profile cũ để áp dụng quy tắc xử lý. Hãy duy trì profile cũ hoặc cung cấp lộ trình chuyển đổi nếu các client đang sử dụng nó.

## 4. Phân biệt Link.profile và relation profile

Spring HATEOAS cho phép tạo một link với relation bất kỳ, bao gồm relation có tên `profile`. Điều này liên quan đến RFC 6906, định nghĩa relation type `profile`. RFC 6906 là tài liệu Informational của RFC Series, không phải tiêu chuẩn Internet Standards Track.

Hai trường hợp sau có ý nghĩa khác nhau.

### 4.1. Thuộc tính profile của link

Dùng `withProfile(...)` khi muốn nói rằng tài nguyên tại href tuân theo một profile:

~~~java
Link author = Link.of("/authors/17", "author")
    .withProfile("https://api.example.com/profiles/author");
~~~

HAL:

~~~json
{
  "_links": {
    "author": {
      "href": "/authors/17",
      "profile": "https://api.example.com/profiles/author"
    }
  }
}
~~~

Ở đây, `author` là relation; thuộc tính `profile` mô tả biểu diễn tại URI đích.

### 4.2. Relation có tên profile

Dùng relation `profile` khi muốn biểu diễn hiện tại công bố rằng nó tuân theo một profile:

~~~java
Link profileDocumentation = Link.of(
    "https://api.example.com/profiles/book",
    "profile"
).withTitle("Quy ước biểu diễn sách");

model.add(profileDocumentation);
~~~

HAL:

~~~json
{
  "id": "42",
  "title": "REST in Practice",
  "_links": {
    "self": {
      "href": "/books/42"
    },
    "profile": {
      "href": "https://api.example.com/profiles/book",
      "title": "Quy ước biểu diễn sách"
    }
  }
}
~~~

Relation `profile` cho biết biểu diễn hiện tại tuân theo profile được nhận diện bởi URI đích. Theo RFC 6906, URI này chủ yếu là định danh; nó có thể trỏ đến tài liệu có thể truy cập, nhưng không bắt buộc phải dereference được.

### 4.3. So sánh nhanh

| Cách khai báo | Câu hỏi được trả lời | Phạm vi profile |
|---|---|---|
| `link.withProfile(uri)` | Tài nguyên ở href tuân theo profile nào? | Tài nguyên đích của link |
| `Link.of(profileUri, "profile")` | Biểu diễn hiện tại tuân theo profile nào? | Biểu diễn chứa link |
| `link.withRel("author")` | Tài nguyên đích là gì so với nguồn? | Không khai báo profile |
| `link.withType("application/hal+json")` | Định dạng nào được mong đợi ở đích? | Không khai báo profile |

Không nên thay `withProfile(uri)` bằng `withRel("profile")` theo thói quen. Hãy xác định bạn đang mô tả profile của tài nguyên đích hay công bố profile của biểu diễn hiện tại.

## 5. Tích hợp profile vào assembler

Giả sử API thư viện có DTO sách và tác giả. Profile sách và tác giả được định nghĩa riêng:

~~~java
public record BookRepresentation(
    UUID id,
    String title,
    String isbn,
    String status
) {}

public record AuthorRepresentation(
    UUID id,
    String displayName
) {}
~~~

Assembler tạo link self cho sách và link author có profile riêng:

~~~java
@Component
public class BookModelAssembler
        implements RepresentationModelAssembler<Book, EntityModel<BookRepresentation>> {

    private static final String BOOK_PROFILE =
        "https://api.example.com/profiles/book";

    private static final String AUTHOR_PROFILE =
        "https://api.example.com/profiles/author";

    @Override
    public EntityModel<BookRepresentation> toModel(Book book) {
        UUID id = book.getId();
        UUID authorId = book.getAuthor().getId();

        Link self = linkTo(
            methodOn(BookController.class).one(id)
        ).withSelfRel()
         .withType("application/hal+json")
         .withProfile(BOOK_PROFILE);

        Link author = linkTo(
            methodOn(AuthorController.class).one(authorId)
        ).withRel("author")
         .withType("application/hal+json")
         .withProfile(AUTHOR_PROFILE);

        return EntityModel.of(
            new BookRepresentation(
                id,
                book.getTitle(),
                book.getIsbn(),
                book.getStatus().name()
            ),
            self,
            author
        );
    }
}
~~~

Khi serialize HAL, mỗi link mang profile tương ứng với kiểu biểu diễn tại đích:

~~~json
{
  "id": "42",
  "title": "REST in Practice",
  "isbn": "9780132350884",
  "status": "PUBLISHED",
  "_links": {
    "self": {
      "href": "/books/42",
      "type": "application/hal+json",
      "profile": "https://api.example.com/profiles/book"
    },
    "author": {
      "href": "/authors/17",
      "type": "application/hal+json",
      "profile": "https://api.example.com/profiles/author"
    }
  }
}
~~~

Profile của link self mô tả biểu diễn sách; profile của link author mô tả biểu diễn tác giả. Không dùng profile sách cho link tác giả chỉ vì link đó nằm trong biểu diễn sách.

Các kiểu `Book`, `BookController`, `AuthorController` và DTO là thành phần miền của ví dụ. Trong dự án thực tế, thay bằng kiểu và mapping tương ứng.

## 6. Thiết kế tài liệu profile

Một profile hữu ích cần nói rõ các quy ước bổ sung mà client có thể áp dụng. Ví dụ, tài liệu tại `https://api.example.com/profiles/book` có thể mô tả:

| Thành phần | Quy ước |
|---|---|
| `id` | Định danh sách, dạng UUID |
| `isbn` | ISBN-13 đã chuẩn hóa, không chứa dấu phân cách |
| `title` | Tiêu đề hiển thị, không rỗng |
| `status` | DRAFT, PUBLISHED hoặc ARCHIVED |
| `author` | Link relation đến tài nguyên tác giả |
| `reviews` | Link relation đến collection đánh giá |

Profile có thể được công bố dưới dạng tài liệu HTML cho lập trình viên, JSON Schema hoặc một tài liệu máy đọc được khác. Định dạng tài liệu là quyết định của API; RFC 6906 không quy định một schema cụ thể cho nội dung profile.

### 6.1. Profile không phải schema validation tự động

Gắn URI profile vào link không làm Spring tự kiểm tra nội dung có tuân theo profile hay không. Spring HATEOAS chỉ lưu metadata và serialize nó. Việc xác thực dữ liệu phải được thực hiện ở các tầng phù hợp:

- Bean Validation kiểm tra các ràng buộc dữ liệu đầu vào.
- Service hoặc domain kiểm tra quy tắc nghiệp vụ.
- JSON Schema hoặc công cụ hợp đồng có thể mô tả cấu trúc biểu diễn.
- Contract test kiểm tra response thực tế phù hợp với profile đã công bố.

Profile giúp client nhận biết quy ước. Nó không tự thực thi các quy ước đó.

### 6.2. Có thể kết hợp nhiều profile

Một biểu diễn có thể tuân theo nhiều profile bổ sung. Ví dụ, một tài nguyên sách có thể tuân theo profile book cơ bản và profile digital-publication cho các trường liên quan đến xuất bản điện tử.

Cần chọn cách công bố nhiều profile nhất quán với media type và định dạng hypermedia được dùng. RFC 6906 cho phép biểu diễn liên kết đến nhiều profile. Trong khi đó, `Link.withProfile(String)` nhận một chuỗi cho thuộc tính profile của một link. Không nên tự nối nhiều URI vào chuỗi này nếu hợp đồng media type không định nghĩa rõ cách phân tích danh sách.

## 7. Profile và khả năng tiến hóa API

Profile hữu ích khi API muốn bổ sung quy ước mà vẫn giữ media type và ngữ nghĩa cơ bản ổn định. Tuy nhiên, profile cũng là một phần hợp đồng mà client có thể phụ thuộc.

Một số nguyên tắc thiết kế:

1. Dùng URI riêng cho từng profile có ý nghĩa khác nhau.
2. Không thay đổi âm thầm ngữ nghĩa của URI profile đã công bố.
3. Nếu quy ước thay đổi không tương thích, tạo profile mới và xác định lộ trình chuyển đổi.
4. Duy trì khả năng xử lý cơ bản cho client không hiểu profile.
5. Không dùng profile làm cơ chế cấp quyền hoặc xác thực.
6. Bảo đảm profile gắn với link mô tả đúng tài nguyên đích.
7. Tài liệu hóa cách profile liên hệ với relation và media type.

Ví dụ, khi profile book-v1 yêu cầu `status` chỉ có ba giá trị, việc thêm một trạng thái mới có thể ảnh hưởng client đã triển khai logic dựa trên profile đó. Nếu thay đổi có ý nghĩa không tương thích, nên phát hành profile book-v2 hoặc xác định rõ cách mở rộng để client cũ bỏ qua giá trị chưa biết.

Không nên thay đổi nội dung tài liệu profile tại cùng URI theo cách làm client cũ diễn giải khác đi. URI profile nên giữ tính ổn định như một định danh của hợp đồng.

## 8. Kiểm thử profile trong phản hồi HAL

Kiểm thử nên xác nhận profile được gắn đúng vào link, không chỉ kiểm tra URI và relation.

Ví dụ kiểm tra link self và author:

~~~java
@WebMvcTest(BookController.class)
@Import(BookModelAssembler.class)
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    BookService service;

    @Test
    void publishesProfilesForLinkTargets() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        given(service.getRequired(id)).willReturn(bookWithAuthor(id));

        mvc.perform(get("/books/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.profile")
                .value("https://api.example.com/profiles/book"))
            .andExpect(jsonPath("$._links.author.profile")
                .value("https://api.example.com/profiles/author"));
    }
}
~~~

Các import chính:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Fixture `bookWithAuthor(id)` là hàm dựng dữ liệu kiểm thử của ứng dụng. Ngoài ví dụ trên, nên kiểm tra:

- Link không có profile không tự xuất hiện trường profile trong HAL.
- Profile của link self mô tả đúng biểu diễn của tài nguyên hiện tại.
- Profile của link quan hệ mô tả đúng kiểu tài nguyên đích.
- Relation profile được serialize riêng khi API công bố profile của biểu diễn hiện tại.
- Profile URI không bị nhầm với href của tài nguyên cụ thể.
- Việc thay đổi profile được xem xét như thay đổi hợp đồng và có kiểm thử tương thích.

Có thể kiểm thử trực tiếp value object mà không cần chạy HTTP:

~~~java
Link link = Link.of("/authors/17", "author")
    .withProfile("https://api.example.com/profiles/author");

assertEquals(
    "https://api.example.com/profiles/author",
    link.getProfile()
);
~~~

MockMvc xác minh quá trình serialize link trong ứng dụng Spring MVC. Kiểm thử value object xác nhận metadata được tạo đúng trước khi serialize. Hai loại kiểm thử bổ sung cho nhau.

## 9. Lỗi thường gặp khi sử dụng profile

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm profile với relation | Client không xác định được ý nghĩa của link | Phân biệt vai trò của rel và profile |
| Gắn profile nguồn vào mọi link | Profile không khớp tài nguyên đích | Chọn profile theo kiểu biểu diễn tại href |
| Dùng profile thay media type | Client không biết định dạng dữ liệu | Khai báo type và profile riêng |
| Xem profile URI luôn là URL phải tải | Client có thể thực hiện request không cần thiết | Coi URI trước hết là định danh |
| Cho rằng Spring tự validate profile | Dữ liệu sai quy ước vẫn có thể được trả về | Dùng validation và contract test |
| Thay đổi nội dung profile cũ âm thầm | Client cũ có thể xử lý sai | Giữ profile ổn định hoặc phát hành profile mới |
| Dùng profile như quyền truy cập | Tạo hiểu nhầm về bảo mật | Xác thực và phân quyền ở server |
| Gắn cùng profile cho các loại đích khác nhau | Metadata gây hiểu nhầm | Kiểm tra profile theo từng target resource |

## 10. Quy trình áp dụng profile cho Link

Khi thêm profile vào API Spring HATEOAS, có thể thực hiện theo trình tự:

1. Xác định quy ước ngữ nghĩa bổ sung mà client cần biết.
2. Định nghĩa URI profile ổn định và viết tài liệu cho nó.
3. Xác định profile mô tả biểu diễn hiện tại hay tài nguyên đích của một link.
4. Nếu mô tả đích, dùng `Link.withProfile(uri)`.
5. Nếu công bố profile của biểu diễn hiện tại, thêm link với relation `profile`.
6. Dùng `withType(...)` riêng nếu cần mô tả media type của đích.
7. Kiểm tra profile không làm thay đổi ngữ nghĩa cơ bản của media type.
8. Kiểm thử profile ở cấp Link và trong HAL response.
9. Quản lý thay đổi profile như thay đổi hợp đồng API.

## 11. Kết luận

Thuộc tính `profile` của Spring HATEOAS Link cung cấp URI nhận diện các quy ước ngữ nghĩa bổ sung của tài nguyên tại href. API dùng `withProfile(...)` để tạo metadata và `getProfile()` để đọc giá trị đó. Khi serialize theo HAL, thuộc tính profile xuất hiện trong Link Object và giúp client nhận diện profile của tài nguyên đích.

Cần phân biệt rõ thuộc tính `Link.profile` với relation `profile` theo RFC 6906. Thuộc tính profile mô tả target resource của link; relation profile công bố profile mà biểu diễn chứa link tuân theo. Khi URI profile ổn định, được tài liệu hóa và gắn đúng phạm vi, Spring HATEOAS có thể giúp API công bố hợp đồng ngữ nghĩa rõ ràng hơn mà vẫn giữ media type và khả năng tương thích cơ bản.

## Tài liệu tham khảo

- [Spring HATEOAS — Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html): các phương thức `withProfile` và `getProfile`.
- [RFC 6906 — The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906): khái niệm profile và relation `profile`.
- [JSON Hypertext Application Language — HAL draft](https://datatracker.ietf.org/doc/html/draft-kelly-json-hal-09): thuộc tính profile của HAL Link Object.

