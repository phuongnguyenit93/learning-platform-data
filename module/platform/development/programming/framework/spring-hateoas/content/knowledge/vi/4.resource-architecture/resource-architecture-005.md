# Resource collection

Resource collection (tập hợp tài nguyên) là một tài nguyên đại diện cho một nhóm tài nguyên thành viên có cùng loại hoặc cùng vai trò trong miền nghiệp vụ. Ví dụ, `/books` có thể đại diện cho tập hợp sách trong thư viện, còn `/books/42` định danh một cuốn sách cụ thể. Collection có URI, biểu diễn và các thao tác riêng; nó không chỉ là một mảng JSON được trả về từ controller.

Trong REST, collection là một tài nguyên có thể được đọc, lọc, phân trang, tạo thành viên mới và cung cấp liên kết đến các thành viên. Spring HATEOAS hỗ trợ mô hình hóa collection bằng `CollectionModel`, `PagedModel`, `EntityModel` và `RepresentationModelAssembler`. Những kiểu này giúp dữ liệu, metadata và liên kết điều hướng được tổ chức trong cùng một biểu diễn hypermedia.

Bài học tập trung vào kiến trúc collection trong API Spring HATEOAS: thiết kế URI collection và member, biểu diễn tập hợp, thêm link, phân trang và lọc, xử lý collection rỗng, kiểm soát thao tác ghi và kiểm thử hợp đồng HAL.

Sau bài học, bạn có thể:

- Phân biệt collection resource với member resource và một mảng dữ liệu đơn thuần.
- Thiết kế URI và HTTP method cho việc đọc, tạo, cập nhật và xóa thành viên.
- Dùng CollectionModel, EntityModel và RepresentationModelAssembler để xây dựng biểu diễn.
- Tạo link điều hướng cho collection và các thành viên.
- Thiết kế lọc, sắp xếp và phân trang mà vẫn giữ được ngữ nghĩa hypermedia.
- Kiểm thử biểu diễn HAL, quan hệ link và các trường hợp collection rỗng hoặc có phân trang.

## 1. Collection là một tài nguyên

Giả sử một ứng dụng quản lý thư viện. Người dùng cần xem danh sách sách, mở chi tiết một cuốn sách, lọc theo tác giả và thêm sách mới. Có thể tổ chức tài nguyên như sau:

| URI | Tài nguyên được nhận diện |
|---|---|
| `/books` | Collection sách |
| `/books/42` | Một cuốn sách |
| `/authors/17` | Một tác giả |
| `/categories/fiction/books` | Collection sách thuộc danh mục fiction |

Collection `/books` có định danh và biểu diễn riêng. Biểu diễn của nó có thể chứa danh sách thành viên, tổng số phần tử, điều kiện lọc đang áp dụng và các liên kết điều hướng. Mỗi member như `/books/42` vẫn có URI riêng để client truy cập trực tiếp.

Một collection có thể chứa toàn bộ thành viên hoặc chỉ một phần của tập hợp. Khi dữ liệu lớn, server thường trả một trang kết quả và link đến trang tiếp theo. Do đó, phản hồi collection không nhất thiết chứa mọi bản ghi trong cơ sở dữ liệu.

### 1.1. Collection resource và member resource

Hai loại tài nguyên có vai trò khác nhau:

- Collection resource đại diện cho tập hợp, cung cấp các thao tác ở cấp tập hợp như truy vấn, lọc, phân trang hoặc tạo thành viên.
- Member resource đại diện cho một phần tử cụ thể, cung cấp các thao tác trên phần tử như xem, cập nhật hoặc xóa.

Ví dụ, `GET /books` đọc collection, còn `GET /books/42` đọc một member. Khi client gửi `POST /books`, server có thể tạo một member mới trong collection và trả về URI của member đó qua header Location.

Collection không nhất thiết phải là một bảng cơ sở dữ liệu. Nó có thể là kết quả tổng hợp từ nhiều nguồn, một tập hợp ảo theo quyền người dùng, hoặc một view được lọc theo điều kiện. URI công khai mô tả tài nguyên trong hợp đồng API; cách server truy vấn hoặc lưu trữ dữ liệu là chi tiết triển khai.

### 1.2. Biểu diễn collection không chỉ là danh sách

Một phản hồi đơn giản có thể chỉ chứa dữ liệu:

~~~json
[
  {
    "id": "42",
    "title": "REST in Practice"
  },
  {
    "id": "43",
    "title": "Designing Web APIs"
  }
]
~~~

Client nhìn thấy các phần tử nhưng không nhận được thông tin điều hướng theo ngữ nghĩa. Nó có thể phải tự tạo URI từ ID, tự biết đường dẫn trang kế tiếp hoặc đọc tài liệu tĩnh để biết thao tác tạo sách.

Biểu diễn hypermedia mô tả collection và các liên kết của nó:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/books"
    },
    "create": {
      "href": "https://api.example.com/books"
    }
  },
  "_embedded": {
    "books": [
      {
        "id": "42",
        "title": "REST in Practice",
        "_links": {
          "self": {
            "href": "https://api.example.com/books/42"
          }
        }
      },
      {
        "id": "43",
        "title": "Designing Web APIs",
        "_links": {
          "self": {
            "href": "https://api.example.com/books/43"
          }
        }
      }
    ]
  }
}
~~~

Đây là ví dụ HAL minh họa. Tên relation trong `_embedded` phụ thuộc cấu hình relation của ứng dụng. Mỗi member có thể có link self riêng; collection cũng có link self và các link thao tác ở cấp tập hợp.

## 2. Thiết kế URI và thao tác HTTP cho collection

Một quy ước phổ biến là dùng danh từ số nhiều cho URI collection và định danh thành viên bằng path segment:

~~~text
/books
/books/{bookId}
~~~

Quy ước này dễ đọc và giúp phân biệt collection với member. Tuy nhiên, điều quan trọng hơn là URI phải ổn định và có ngữ nghĩa nhất quán. Không nên để client phụ thuộc vào tên bảng hoặc tên class Java.

### 2.1. Các thao tác phổ biến

| Request | Tài nguyên đích | Ý nghĩa |
|---|---|---|
| `GET /books` | Collection | Đọc tập hợp hoặc một trang của tập hợp |
| `POST /books` | Collection | Yêu cầu tạo một member mới |
| `GET /books/42` | Member | Đọc một cuốn sách |
| `PUT /books/42` | Member | Thay thế biểu diễn member |
| `PATCH /books/42` | Member | Cập nhật một phần member |
| `DELETE /books/42` | Member | Xóa member |

Không phải mọi collection đều hỗ trợ tất cả thao tác. Một collection chỉ đọc có thể chỉ cung cấp GET. Một số collection cho phép POST tạo member nhưng không cho phép client cập nhật hoặc xóa trực tiếp.

### 2.2. Tạo member thông qua collection

Khi client gửi POST đến collection, server có thể tạo member mới:

~~~http
POST /books HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "title": "REST in Practice",
  "authorId": "17"
}
~~~

Nếu tạo thành công, phản hồi thường dùng 201 Created và Location trỏ đến member mới:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.com/books/42
Content-Type: application/hal+json

{
  "id": "42",
  "title": "REST in Practice",
  "_links": {
    "self": {
      "href": "https://api.example.com/books/42"
    },
    "collection": {
      "href": "https://api.example.com/books"
    }
  }
}
~~~

Client có thể truy cập URI trong Location để đọc biểu diễn đầy đủ. Nếu response body đã chứa biểu diễn hypermedia của member thì client có thể dùng ngay link self.

POST thường không có tính idempotent mặc định. Nếu client gửi lại cùng request vì timeout, server có thể tạo hai cuốn sách. Với thao tác tạo cần hỗ trợ retry, ứng dụng có thể sử dụng idempotency key hoặc một định danh do client cung cấp theo hợp đồng được thiết kế rõ.

### 2.3. Collection và member có thể có quyền khác nhau

Quyền đọc collection không đồng nghĩa người dùng có quyền đọc mọi member. Tương tự, có quyền xem member không đồng nghĩa được cập nhật hoặc xóa nó. Server có thể lọc collection theo quyền và chỉ phát các link phù hợp với vai trò hiện tại.

Ví dụ, nhân viên thư viện có thể thấy link `edit` và `delete`, trong khi người đọc chỉ thấy `self` và `reviews`. Dù link không được công bố, endpoint vẫn phải kiểm tra quyền ở phía server khi request được gửi trực tiếp.

## 3. Mô hình collection trong Spring HATEOAS

Spring HATEOAS cung cấp các kiểu dữ liệu để biểu diễn tài nguyên đơn lẻ và tập hợp tài nguyên.

| Kiểu | Mục đích |
|---|---|
| `RepresentationModel<T>` | Lớp cơ sở để gắn link vào một biểu diễn |
| `EntityModel<T>` | Bao một đối tượng nội dung cùng các link |
| `CollectionModel<T>` | Bao một tập hợp các biểu diễn cùng link ở cấp collection |
| `PagedModel<T>` | Biểu diễn tập hợp có metadata phân trang |
| `Link` | Biểu diễn một URI cùng relation |
| `RepresentationModelAssembler<T, D>` | Chuyển đối tượng miền hoặc DTO thành mô hình hypermedia |

Điểm cần nhớ: `CollectionModel` đại diện cho collection resource; từng phần tử bên trong có thể là DTO thuần hoặc một mô hình có link như `EntityModel`. Khi mỗi member cần link riêng, dùng `CollectionModel<EntityModel<BookRepresentation>>` là một lựa chọn rõ ràng.

### 3.1. Định nghĩa DTO công khai

Không nên mặc định serialize trực tiếp JPA entity thành API representation. DTO giúp kiểm soát trường nào được công bố và tách hợp đồng API khỏi cấu trúc persistence.

~~~java
public record BookRepresentation(
    UUID id,
    String title,
    String authorName
) {}
~~~

Một DTO có thể được đánh dấu relation để định nghĩa tên dùng trong collection embedding:

~~~java
@Relation(value = "book", collectionRelation = "books")
public record BookRepresentation(
    UUID id,
    String title,
    String authorName
) {}
~~~

Annotation `@Relation` thuộc package `org.springframework.hateoas.server.core`. Tên relation cần nhất quán với hợp đồng mà client sử dụng. Nếu ứng dụng có chiến lược relation riêng, hãy định nghĩa rõ và kiểm thử tên relation được serialize.

### 3.2. Tạo member bằng RepresentationModelAssembler

Assembler chuyển đối tượng miền thành `EntityModel` và thêm link self cùng link về collection:

~~~java
@Component
public class BookModelAssembler
        implements RepresentationModelAssembler<Book, EntityModel<BookRepresentation>> {

    @Override
    public EntityModel<BookRepresentation> toModel(Book book) {
        UUID id = book.getId();

        return EntityModel.of(
            new BookRepresentation(
                id,
                book.getTitle(),
                book.getAuthor().getName()
            ),
            linkTo(methodOn(BookController.class).one(id)).withSelfRel(),
            linkTo(methodOn(BookController.class).all())
                .withRel(IanaLinkRelations.COLLECTION)
        );
    }
}
~~~

Assembler tập trung việc chuyển đổi và tạo link. Controller không cần lặp lại cách xây link cho mỗi nơi trả về một member. Nếu biểu diễn member cần link theo trạng thái, ví dụ `publish` hoặc `archive`, assembler có thể bổ sung link dựa trên trạng thái nghiệp vụ.

### 3.3. Tạo CollectionModel

Controller có thể trả collection bằng cách sử dụng `toCollectionModel`:

~~~java
@RestController
@RequestMapping("/books")
public class BookController {

    private final BookService service;
    private final BookModelAssembler assembler;

    public BookController(BookService service, BookModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<BookRepresentation>> all() {
        return assembler.toCollectionModel(service.findAll())
            .add(linkTo(methodOn(BookController.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    public EntityModel<BookRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(service.getRequired(id));
    }
}
~~~

Các import chính:

~~~java
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.hateoas.server.core.Relation;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Các kiểu `Book` và `BookService` là thành phần miền của ví dụ. Trong dự án thật, thay bằng model và service tương ứng.

Phương thức `toCollectionModel` gọi assembler cho từng phần tử rồi gom các mô hình thành một collection. Link self được thêm ở cấp collection; link self của mỗi member được tạo trong `toModel`. Hai cấp link này phục vụ hai mục đích khác nhau.

Nếu controller chỉ trả về `CollectionModel<BookRepresentation>`, collection vẫn có thể có link cấp tập hợp, nhưng các phần tử không tự có link riêng. Chọn kiểu trả về theo nhu cầu điều hướng của client.

## 4. Link ở cấp collection và member

Một biểu diễn collection thường có các nhóm link khác nhau:

- Link điều hướng collection: `self`, `next`, `prev`, `first`, `last`.
- Link quan hệ với tài nguyên khác: `search`, `categories`, `authors`.
- Link thao tác ở cấp collection: `create`, `import` hoặc `bulk-update`, nếu nghiệp vụ hỗ trợ.
- Link ở cấp member: `self`, `author`, `reviews`, `edit`, `delete`.

Không phải tất cả link đều phải xuất hiện trong mọi phản hồi. Link nên phản ánh khả năng và quyền hiện tại. Nếu collection chỉ đọc, không phát link create. Nếu một member đã bị lưu trữ, không phát link edit nếu nghiệp vụ không cho phép sửa.

### 4.1. Relation chuẩn và relation tùy chỉnh

Spring HATEOAS cung cấp `IanaLinkRelations` cho các relation chuẩn được hỗ trợ, ví dụ:

~~~java
.withRel(IanaLinkRelations.SELF)
.withRel(IanaLinkRelations.COLLECTION)
~~~

Các quan hệ theo miền như `create`, `publish`, `archive` hoặc `reviews` là custom relation. Cần xác định ý nghĩa của chúng trong hợp đồng API. Với API công khai, có thể dùng URI relation để định nghĩa ngữ nghĩa lâu dài hoặc CURIE để rút gọn tên quan hệ trong HAL.

Không nên dùng cùng một relation cho hai hành động khác nhau. Client cần có thể diễn giải rel độc lập với URI cụ thể.

### 4.2. Collection rỗng vẫn là một tài nguyên

Collection không mất đi khi chưa có member. Ví dụ `GET /books` có thể trả về một collection rỗng với link self và link create nếu người dùng được phép thêm sách.

Client không nên suy ra collection không tồn tại chỉ vì danh sách phần tử rỗng. Cần phân biệt:

- Collection tồn tại nhưng chưa có member: thường trả 200 với biểu diễn collection rỗng.
- Member không tồn tại: endpoint member thường trả 404.
- Collection không tồn tại hoặc không được công bố: phản hồi tùy hợp đồng API, có thể là 404.

Với HAL, serializer có thể thể hiện các member trong `_embedded`. Khi collection rỗng, phần embedded có thể không xuất hiện hoặc được biểu diễn như mảng rỗng tùy cách serialize. Client nên xử lý cả trường hợp không có member mà vẫn đọc các link cấp collection.

## 5. Lọc và sắp xếp collection

Collection thường hỗ trợ query parameters để client chọn một tập con hoặc thứ tự mong muốn:

~~~http
GET /books?author=17&sort=title,asc HTTP/1.1
Accept: application/hal+json
~~~

Các tham số truy vấn là một phần của URI biểu diễn collection đã lọc. Link self trong phản hồi nên trỏ đến chính biến thể collection đang được trả về, bao gồm các điều kiện lọc và sắp xếp có hiệu lực.

Ví dụ, controller có thể nhận các tham số:

Đây là biến thể của phương thức `all()` ở ví dụ controller trước: khi hỗ trợ lọc, thay chữ ký không tham số bằng chữ ký nhận các query parameter này.

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.web.bind.annotation.RequestParam;

@GetMapping
public CollectionModel<EntityModel<BookRepresentation>> all(
        @RequestParam(required = false) UUID authorId,
        @RequestParam(defaultValue = "title") String sort) {

    List<Book> books = service.findBooks(authorId, sort);

    return assembler.toCollectionModel(books)
        .add(linkTo(methodOn(BookController.class).all(authorId, sort))
            .withSelfRel());
}
~~~

Khi tạo link self bằng `methodOn`, Spring HATEOAS lấy URI từ mapping và các tham số được truyền vào. Điều này tránh ghép query string thủ công. Nếu có nhiều tham số tùy chọn, hãy giữ một cách biểu diễn nhất quán cho giá trị mặc định và các điều kiện đang áp dụng.

Cần xác thực và giới hạn các tham số lọc/sắp xếp ở server. Không nhận tên cột tùy ý rồi nối trực tiếp vào câu SQL. Nên ánh xạ các lựa chọn công khai như `title`, `createdAt` sang thuộc tính được phép sắp xếp.

## 6. Phân trang với PagedModel

Khi collection có nhiều member, trả tất cả trong một response có thể làm tăng độ trễ, bộ nhớ và lưu lượng mạng. Phân trang giới hạn số phần tử mỗi lần đọc và cho phép client đi qua tập hợp theo từng trang.

Một request có thể dùng query parameters:

~~~http
GET /books?page=0&size=20&sort=title,asc HTTP/1.1
Accept: application/hal+json
~~~

Phản hồi phân trang thường cần:

- Nội dung của trang hiện tại.
- Metadata như số trang hiện tại, kích thước trang, tổng số phần tử và tổng số trang.
- Link đến trang đầu, trước, hiện tại, tiếp theo và cuối cùng khi phù hợp.

### 6.1. Dùng PagedResourcesAssembler của Spring Data

Nếu ứng dụng sử dụng Spring Data, có thể dùng `PagedResourcesAssembler` để chuyển `Page<T>` thành `PagedModel<D>`. Ví dụ:

~~~java
@GetMapping
public PagedModel<EntityModel<BookRepresentation>> all(
        Pageable pageable,
        PagedResourcesAssembler<Book> pagedAssembler) {

    Page<Book> page = service.findAll(pageable);
    return pagedAssembler.toModel(page, assembler);
}
~~~

Trong ví dụ, `assembler` là `BookModelAssembler` đã định nghĩa ở phần trước. `PagedResourcesAssembler` tạo biểu diễn phân trang và các link điều hướng dựa trên request hiện tại. Kiểu này thuộc Spring Data Web, vì vậy ứng dụng cần có dependency Spring Data phù hợp; nó không chỉ đến từ Spring HATEOAS độc lập.

Các import liên quan thường dùng:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
~~~

Spring Data có thể tự tích hợp phân trang với Spring MVC trong ứng dụng Spring Boot đã cấu hình web support. Hãy kiểm tra cấu hình thực tế nếu Pageable hoặc PagedResourcesAssembler không được inject.

### 6.2. Hiểu link phân trang

Một phản hồi HAL phân trang có thể có cấu trúc minh họa như sau:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": "42",
        "title": "REST in Practice",
        "_links": {
          "self": {
            "href": "https://api.example.com/books/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/books?page=1&size=20"
    },
    "first": {
      "href": "https://api.example.com/books?page=0&size=20"
    },
    "prev": {
      "href": "https://api.example.com/books?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/books?page=2&size=20"
    },
    "last": {
      "href": "https://api.example.com/books?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 95,
    "totalPages": 5,
    "number": 1
  }
}
~~~

Đây là ví dụ về cấu trúc, không phải response cố định cho mọi phiên bản hoặc cấu hình serializer. Trang đầu không có link prev; trang cuối không có link next. Client nên kiểm tra sự hiện diện của relation thay vì tự tính số trang và ghép URI.

Nếu tập hợp thay đổi trong lúc client duyệt qua các trang, offset pagination có thể khiến phần tử bị lặp hoặc bị bỏ qua. Với tập dữ liệu cập nhật liên tục, có thể cân nhắc cursor/keyset pagination. Khi đó, link next chứa cursor do server tạo và client chỉ cần theo link đó.

## 7. Collection và khả năng tiến hóa hợp đồng

Collection thường thay đổi theo thời gian: thêm bộ lọc, thay đổi cách phân trang, thêm metadata hoặc thay đổi đường dẫn nội bộ. Hypermedia giúp giảm phụ thuộc của client vào cấu trúc URI khi client sử dụng relation và href được trả về.

Một số nguyên tắc:

1. Giữ relation ổn định về ngữ nghĩa. Nếu `next` có nghĩa là trang kế tiếp, không đổi nó thành một hành động khác.
2. Cho phép client bỏ qua relation chưa biết. Client cũ có thể tiếp tục sử dụng các link mà nó hiểu.
3. Không yêu cầu client phân tích href để lấy page number, ID hoặc filter. Hãy coi href là URI opaque.
4. Duy trì các trường dữ liệu công khai hoặc có chiến lược versioning khi thay đổi không tương thích.
5. Khi đổi cấu trúc URI, cập nhật link sinh ra từ controller hoặc cấu hình để client vẫn đi theo relation.
6. Kiểm tra link có đúng host, scheme và context path công khai khi API chạy sau proxy hoặc gateway.

Nếu client chỉ dùng các query parameter được lập trình cứng, việc đổi tên tham số `page` thành `cursor` có thể phá vỡ client. Nếu client đi theo link next do server cung cấp, server có thể thay đổi cách mã hóa vị trí tiếp theo mà không buộc client phải hiểu cấu trúc đó.

Hypermedia không tự giải quyết mọi vấn đề tương thích. Thay đổi tên trường dữ liệu, kiểu dữ liệu hoặc ý nghĩa relation vẫn có thể phá vỡ client. Cần xem xét hợp đồng dữ liệu và hành vi cùng với link.

## 8. Kiểm thử collection bằng MockMvc

Kiểm thử collection cần xác nhận cả dữ liệu và cấu trúc hypermedia. Với endpoint `GET /books`, có thể kiểm tra status, media type, link self và link self của member:

~~~java
@WebMvcTest(BookController.class)
@Import(BookModelAssembler.class)
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    BookService service;

    @Test
    void returnsCollectionWithNavigationLinks() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        given(service.findAll()).willReturn(List.of(book(id)));

        mvc.perform(get("/books").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._embedded.books[0]._links.self.href")
                .value(endsWith("/books/" + id)));
    }
}
~~~

Fixture `book(id)` là hàm dựng đối tượng miền trong test. Tên `books` trong đường dẫn JSON phụ thuộc relation collection đã được cấu hình, chẳng hạn bằng `@Relation(collectionRelation = "books")`.

Các import thường dùng trong test:

~~~java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Với collection rỗng, kiểm tra response vẫn có status phù hợp và link self. Không bắt buộc giả định serializer luôn phát `_embedded.books` dưới dạng mảng rỗng; nên xác nhận đúng quy ước mà ứng dụng công bố.

Với collection phân trang, kiểm tra metadata page và các relation điều hướng tương ứng. Ở trang đầu, không nên có prev; ở trang cuối, không nên có next. Ngoài ra, kiểm thử request tạo member để xác nhận 201 Created và Location trỏ đúng URI member.

## 9. Lỗi thường gặp khi thiết kế collection

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả mảng JSON thuần cho collection cần điều hướng | Client không khám phá được link collection hoặc member | Dùng CollectionModel và EntityModel khi phù hợp |
| Chỉ có link self ở collection | Client vẫn phải tự ghép URI member | Thêm link self cho từng member |
| Dùng link collection thay cho link member | Client không biết URI của phần tử cụ thể | Phát link member theo từng biểu diễn |
| Trả toàn bộ dữ liệu không giới hạn | Tăng tải và độ trễ | Hỗ trợ phân trang hoặc cursor |
| Tự tạo link next bằng chuỗi | Có thể mất filter, sort hoặc context path | Dùng assembler hoặc PagedResourcesAssembler |
| Collection rỗng bị coi là không tồn tại | Client hiểu sai trạng thái tài nguyên | Trả biểu diễn collection rỗng theo hợp đồng |
| Phát link create cho người không có quyền | Giao diện client hiển thị thao tác không phù hợp | Phát link theo quyền và vẫn kiểm tra quyền ở server |
| Dùng relation không nhất quán | Client khó diễn giải liên kết | Định nghĩa và giữ ổn định relation |
| Coi pagination metadata là link điều hướng | Client phải tự tạo URI cho trang kế tiếp | Phát các relation first, prev, next, last |

## 10. Quy trình thiết kế một collection resource

Khi xây dựng collection mới, có thể thực hiện theo trình tự:

1. Xác định collection đại diện cho nhóm tài nguyên nào và ai được truy cập.
2. Chọn URI collection và URI member ổn định.
3. Xác định thao tác nào được hỗ trợ ở cấp collection và cấp member.
4. Thiết kế DTO công khai cho member và metadata của collection.
5. Dùng RepresentationModelAssembler để tạo biểu diễn member cùng link self và link liên quan.
6. Dùng CollectionModel để trả collection; dùng PagedModel khi cần phân trang.
7. Xác định relation cho collection, member, thao tác và điều hướng.
8. Giữ filter, sort và pagination trong link self/next để client theo link.
9. Kiểm thử collection có dữ liệu, collection rỗng, trang đầu/cuối, quyền truy cập và thao tác tạo member.
10. Đánh giá khả năng tương thích khi đổi relation, query parameters hoặc cấu trúc biểu diễn.

## 11. Kết luận

Resource collection là một tài nguyên có URI, biểu diễn và các thao tác ở cấp tập hợp. Nó liên kết các member resource nhưng vẫn có ngữ nghĩa riêng: collection có thể được đọc, lọc, phân trang và dùng để tạo member mới. Một API hypermedia cần thể hiện cả link ở cấp collection lẫn link ở cấp member để client khám phá được workflow.

Spring HATEOAS cung cấp CollectionModel, EntityModel, PagedModel và RepresentationModelAssembler để tổ chức các biểu diễn đó. Khi relation rõ ràng, link phản ánh trạng thái và các link phân trang được tạo đúng, client có thể duyệt collection mà không phụ thuộc vào cấu trúc URI nội bộ. Server vẫn chịu trách nhiệm giới hạn truy vấn, kiểm tra quyền và bảo vệ các thao tác ghi.

