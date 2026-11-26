# Nội dung của trang

`PagedModel<T>` là kiểu biểu diễn hypermedia của Spring HATEOAS dành cho một trang trong collection. Nó chứa các phần tử của trang hiện tại, metadata mô tả vị trí và kích thước trang, cùng các link giúp client điều hướng đến trang đầu, trang trước, trang tiếp theo hoặc trang cuối khi những trang đó tồn tại.

Khi API trả về một danh sách nhỏ, một collection có thể được biểu diễn bằng `CollectionModel<T>`. Khi tập dữ liệu lớn và cần chia thành nhiều trang, `PagedModel<T>` bổ sung thông tin phân trang. Trong Spring Data, `Page<T>` thường là kết quả truy vấn ở tầng dữ liệu; `PagedResourcesAssembler` chuyển kết quả đó thành `PagedModel<D>` phù hợp để công bố qua API.

Bài học tập trung vào nội dung của một trang: phần tử nào thuộc trang hiện tại, metadata có ý nghĩa gì, link phân trang được tạo ra như thế nào và client nên sử dụng chúng ra sao. Bạn cũng sẽ thực hành chuyển `Page<T>` thành `PagedModel<D>`, tạo một trang thủ công, xử lý trang rỗng và kiểm thử phản hồi HAL.

Sau bài học, bạn có thể:

- Phân biệt `Page<T>` của Spring Data với `PagedModel<T>` của Spring HATEOAS.
- Giải thích ba phần chính của biểu diễn trang: content, page metadata và links.
- Đọc các trường size, number, totalElements và totalPages.
- Chuyển từng phần tử của trang thành representation có link bằng `RepresentationModelAssembler`.
- Dùng `PagedResourcesAssembler` để tạo `PagedModel` từ kết quả truy vấn.
- Khởi tạo `PagedModel` thủ công khi không dùng Spring Data.
- Thiết kế nội dung trang ổn định, an toàn và dễ điều hướng.
- Kiểm thử nội dung, metadata, relation và media type của phản hồi phân trang.

## 1. Một trang gồm những gì?

Giả sử API quản lý sách có 95 cuốn sách. Client yêu cầu trang thứ hai, mỗi trang 20 phần tử:

~~~http
GET /books?page=1&size=20&sort=title,asc HTTP/1.1
Accept: application/hal+json
~~~

Spring Data dùng chỉ số trang bắt đầu từ 0, vì vậy `page=1` là trang thứ hai. Server trả nội dung của trang đó cùng metadata và link điều hướng.

Một phản hồi HAL minh họa:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": "21",
        "title": "Designing Web APIs",
        "_links": {
          "self": {
            "href": "https://api.example.com/books/21"
          }
        }
      },
      {
        "id": "22",
        "title": "REST in Practice",
        "_links": {
          "self": {
            "href": "https://api.example.com/books/22"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/books?page=1&size=20&sort=title,asc"
    },
    "first": {
      "href": "https://api.example.com/books?page=0&size=20&sort=title,asc"
    },
    "prev": {
      "href": "https://api.example.com/books?page=0&size=20&sort=title,asc"
    },
    "next": {
      "href": "https://api.example.com/books?page=2&size=20&sort=title,asc"
    },
    "last": {
      "href": "https://api.example.com/books?page=4&size=20&sort=title,asc"
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

Đây là cấu trúc minh họa. Nội dung thực tế và các link phụ thuộc vào dữ liệu, cấu hình relation, request hiện tại và phiên bản thư viện. Ba phần cần phân biệt:

1. `_embedded`: các phần tử thuộc trang hiện tại. Mỗi phần tử có thể là một biểu diễn có link riêng.
2. `page`: metadata mô tả trang, chẳng hạn kích thước trang, số phần tử toàn bộ và chỉ số trang hiện tại.
3. `_links`: các URI để truy cập lại trang hiện tại hoặc điều hướng sang trang khác.

Metadata trả lời câu hỏi “trang này có vị trí và kích thước như thế nào?”. Link trả lời câu hỏi “client có thể đi đến đâu tiếp theo?”. Chỉ có metadata không đủ để client điều hướng mà không tự dựng URI; chỉ có link cũng không cho client biết tổng số phần tử hoặc số trang.

## 2. Phân biệt Page và PagedModel

Hai kiểu dữ liệu có tên và vai trò gần nhau nhưng thuộc hai lớp kiến trúc khác nhau.

| Kiểu | Thư viện | Vai trò |
|---|---|---|
| `Page<T>` | Spring Data | Kết quả truy vấn có nội dung trang và thông tin phân trang |
| `Pageable` | Spring Data | Mô tả yêu cầu trang, kích thước và sắp xếp |
| `PageMetadata` | Spring HATEOAS | Metadata phân trang được công bố trong biểu diễn |
| `PagedModel<T>` | Spring HATEOAS | Mô hình hypermedia chứa nội dung trang, metadata và link |
| `PagedResourcesAssembler<T>` | Spring Data Web | Chuyển `Page<T>` thành `PagedModel<D>` |

`Page<T>` thường được service hoặc repository trả về. Nó có thể cung cấp:

- `getContent()`: danh sách phần tử trong trang.
- `getNumber()`: chỉ số trang hiện tại, bắt đầu từ 0.
- `getSize()`: kích thước trang được yêu cầu.
- `getNumberOfElements()`: số phần tử thực tế trong trang hiện tại.
- `getTotalElements()`: tổng số phần tử phù hợp với truy vấn.
- `getTotalPages()`: tổng số trang.
- `hasNext()` và `hasPrevious()`: cho biết còn trang kế tiếp hoặc trang trước.

`PagedModel<T>` không thực hiện truy vấn cơ sở dữ liệu và không tự chia danh sách thành các trang. Nó là mô hình biểu diễn để serialize kết quả phân trang cùng link hypermedia.

Luồng xử lý thường gặp:

~~~text
HTTP request
    |
    v
Controller nhận Pageable
    |
    v
Service / Repository truy vấn Page<Book>
    |
    v
PagedResourcesAssembler chuyển Page<Book>
    |        và BookModelAssembler
    v
PagedModel<EntityModel<BookRepresentation>>
    |
    v
HAL response
~~~

Phân chia trách nhiệm như vậy giúp tầng dữ liệu tập trung truy vấn, assembler tập trung chuyển đổi member và tầng web trả về biểu diễn hypermedia.

## 3. Nội dung trang và phần tử bên trong

Nội dung của một `PagedModel<T>` là tập hợp các phần tử thuộc trang hiện tại. Kiểu `T` quyết định mức độ thông tin và liên kết có trong mỗi phần tử.

### 3.1. Trang chứa DTO thuần

Một trang có thể chứa các DTO:

~~~java
PagedModel<BookRepresentation> pageModel;
~~~

Cách này phù hợp khi client chỉ cần dữ liệu của từng phần tử và link ở cấp trang. Tuy nhiên, nếu client cần mở chi tiết từng cuốn sách, nó có thể phải dựa vào ID để tự dựng URI.

### 3.2. Trang chứa EntityModel

Khi từng member cần có link riêng, dùng:

~~~java
PagedModel<EntityModel<BookRepresentation>> pageModel;
~~~

Mỗi phần tử có thể chứa link self, author, reviews hoặc một hành động theo trạng thái. Trang cũng có link phân trang ở cấp collection.

Ví dụ cấu trúc:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": "21",
        "title": "Designing Web APIs",
        "_links": {
          "self": {
            "href": "https://api.example.com/books/21"
          },
          "author": {
            "href": "https://api.example.com/authors/17"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/books?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/books?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 35,
    "totalPages": 2,
    "number": 0
  }
}
~~~

Link self của member trỏ đến một cuốn sách. Link self của trang trỏ đến collection với các tham số truy vấn đang áp dụng. Hai link cùng tên relation nhưng nằm ở hai cấp biểu diễn khác nhau.

### 3.3. Chọn relation cho nội dung nhúng

HAL dùng relation để đặt tên collection trong `_embedded`. Có thể khai báo relation cho DTO:

~~~java
@Relation(value = "book", collectionRelation = "books")
public record BookRepresentation(
    UUID id,
    String title,
    String authorName
) {}
~~~

Annotation `@Relation` nằm trong package `org.springframework.hateoas.server.core`. Với ví dụ này, relation collection dự kiến là `books`. Tên relation là một phần hợp đồng mà client đọc, vì vậy cần giữ nhất quán và kiểm thử sau khi thay đổi DTO hoặc cấu hình relation.

Nếu không khai báo rõ, Spring HATEOAS có thể suy ra relation từ kiểu dữ liệu hoặc cấu hình relation provider. Đối với API công khai, nên kiểm soát tên relation thay vì để client phụ thuộc vào tên class Java.

## 4. Metadata của PagedModel

Metadata trang được biểu diễn bởi lớp lồng `PagedModel.PageMetadata`. Bốn trường quan trọng là:

| Trường | Ý nghĩa |
|---|---|
| `size` | Kích thước trang được yêu cầu hoặc giới hạn |
| `number` | Chỉ số trang hiện tại, bắt đầu từ 0 trong mô hình phân trang Spring |
| `totalElements` | Tổng số phần tử phù hợp với truy vấn |
| `totalPages` | Tổng số trang theo kích thước trang |

Ví dụ metadata:

~~~java
PagedModel.PageMetadata metadata =
    new PagedModel.PageMetadata(
        20,  // size
        1,   // number: trang thứ hai
        95,  // totalElements
        5    // totalPages
    );
~~~

Với 95 phần tử và kích thước 20, tổng số trang là 5. Các chỉ số trang hợp lệ là 0, 1, 2, 3 và 4. Trang cuối cùng có thể không đủ 20 phần tử.

### 4.1. Phân biệt size và số phần tử thực tế

`size` không nhất thiết bằng số phần tử được trả về trong trang hiện tại. Ví dụ, client yêu cầu size 20 nhưng trang cuối chỉ còn 15 phần tử. Khi đó:

- `size` có thể là 20.
- `numberOfElements` của đối tượng `Page` là 15.
- `totalElements` là tổng số bản ghi của toàn bộ kết quả.

Đừng dùng `size` để kết luận trang hiện tại luôn có đúng từng ấy phần tử. Hãy đọc danh sách content hoặc `getNumberOfElements()` nếu cần biết số phần tử thực tế.

### 4.2. Tổng số trang và tập hợp rỗng

Nếu tổng số phần tử bằng 0, tổng số trang thường bằng 0 trong kết quả Spring Data. Khi đó không có trang dữ liệu nào chứa phần tử. Một response phân trang rỗng vẫn có thể là biểu diễn hợp lệ của collection và có link self.

Không nên tự đặt `totalPages = 1` chỉ vì endpoint đã được gọi. Hãy giữ metadata nhất quán với kết quả truy vấn và cách phân trang được ứng dụng công bố.

### 4.3. Metadata không thay thế link

Từ `number` và `totalPages`, client có thể tính toán trang tiếp theo. Nhưng nếu client phải tự dựng URI, nó sẽ phải biết tên query parameter, cách giữ filter, sort, context path và quy tắc đánh số trang.

Với hypermedia, client nên tìm relation `next`, `prev`, `first` hoặc `last` trong `_links` và theo href được cung cấp. Metadata có ích để hiển thị “trang 2 trên 5”, thanh tiến trình hoặc số lượng kết quả; link được dùng để điều hướng.

## 5. Tạo PagedModel từ Spring Data

Trong ứng dụng dùng Spring Data, cách phổ biến là để repository hoặc service trả về `Page<T>`, sau đó dùng `PagedResourcesAssembler` để tạo biểu diễn.

### 5.1. Khai báo DTO và assembler cho member

DTO công khai:

~~~java
@Relation(value = "book", collectionRelation = "books")
public record BookRepresentation(
    UUID id,
    String title,
    String authorName
) {}
~~~

Assembler tạo `EntityModel<BookRepresentation>` cho từng cuốn sách:

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
            linkTo(methodOn(BookController.class).one(id)).withSelfRel()
        );
    }
}
~~~

`RepresentationModelAssembler` chịu trách nhiệm chuyển từng member và tạo link self của member. `PagedResourcesAssembler` chịu trách nhiệm đóng gói trang, tạo metadata và link phân trang ở cấp collection. Nếu cần thêm link nghiệp vụ ở cấp trang, hãy bổ sung sau khi chuyển đổi và giữ nguyên các tham số filter/sort hiện tại.

### 5.2. Controller nhận Pageable

Spring MVC có thể bind các query parameter như `page`, `size` và `sort` vào `Pageable`. Ví dụ:

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
    public PagedModel<EntityModel<BookRepresentation>> all(
            Pageable pageable,
            PagedResourcesAssembler<Book> pagedAssembler) {

        Page<Book> page = service.findAll(pageable);
        return pagedAssembler.toModel(page, assembler);
    }

    @GetMapping("/{id}")
    public EntityModel<BookRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(service.getRequired(id));
    }
}
~~~

Các kiểu import chính:

~~~java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
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

`PagedResourcesAssembler` thuộc Spring Data Web; `PagedModel` thuộc Spring HATEOAS. Vì vậy, ví dụ cần dependency Spring Data phù hợp cùng Spring HATEOAS, thường được quản lý thông qua Spring Boot starter và dependency management của dự án.

### 5.3. Chuyển Page thành PagedModel

Dòng quan trọng là:

~~~java
return pagedAssembler.toModel(page, assembler);
~~~

Thao tác này:

1. Đọc các phần tử trong `Page<Book>`.
2. Gọi `BookModelAssembler` để chuyển từng `Book` thành `EntityModel<BookRepresentation>`.
3. Lấy metadata phân trang từ `Page`.
4. Tạo link phân trang dựa trên request hiện tại và cấu hình web.
5. Trả về `PagedModel<EntityModel<BookRepresentation>>`.

Nếu không truyền assembler, một overload khác có thể dùng khi kiểu phần tử đã là representation phù hợp. Khi cần link self cho từng member, truyền assembler giúp kiểm soát cách tạo biểu diễn.

### 5.4. Giữ bộ lọc và sắp xếp trong link

Giả sử endpoint hỗ trợ lọc theo tác giả:

~~~http
GET /books?authorId=17&page=1&size=20&sort=title,asc
~~~

Khi tạo link next, client cần tiếp tục duyệt cùng tập hợp đã lọc và sắp xếp. Link do assembler tạo dựa trên request hiện tại có thể giữ lại các query parameter đó. Nếu ứng dụng tự tạo link, phải bảo đảm các điều kiện truy vấn vẫn được giữ khi chuyển trang.

Không nên để client lấy href next rồi thêm query parameter tùy ý bằng cách nối chuỗi. Nếu cần thay đổi điều kiện lọc, client nên bắt đầu một request collection mới với điều kiện mới.

## 6. Tạo PagedModel thủ công

Không phải ứng dụng nào cũng dùng Spring Data. Khi đã có danh sách content và biết metadata, có thể tạo `PagedModel` trực tiếp.

Ví dụ:

~~~java
List<EntityModel<BookRepresentation>> content = List.of(
    bookAssembler.toModel(firstBook),
    bookAssembler.toModel(secondBook)
);

PagedModel.PageMetadata metadata =
    new PagedModel.PageMetadata(20, 1, 95, 5);

PagedModel<EntityModel<BookRepresentation>> model =
    PagedModel.of(content, metadata, selfLink, firstLink, prevLink, nextLink, lastLink);
~~~

`PagedModel.of(...)` nhận content, metadata và các link cần công bố. Cách này hữu ích khi dữ liệu đến từ một API bên ngoài, một nguồn tổng hợp hoặc một bộ máy truy vấn không trả về `Page<T>`.

Khi tự tạo model, ứng dụng chịu trách nhiệm bảo đảm metadata và link nhất quán:

- Content phải tương ứng với trang được mô tả.
- `number` phải đúng chỉ số trang.
- `size` phải khớp quy ước kích thước trang được công bố.
- `totalElements` và `totalPages` phải được tính từ cùng tập kết quả.
- Trang đầu không có link prev.
- Trang cuối không có link next.
- Link self phải đại diện đúng truy vấn hiện tại.
- Các link first, prev, next và last phải giữ lại filter và sort.

Không tạo link next chỉ dựa vào việc trang hiện tại có đủ phần tử. Nếu hệ thống không biết có trang tiếp theo hay không, cần dựa vào metadata hoặc cursor từ nguồn dữ liệu để quyết định.

## 7. Điều hướng giữa các trang

Các relation phân trang thường dùng:

| Relation | Ý nghĩa |
|---|---|
| `self` | Trang hiện tại |
| `first` | Trang đầu tiên |
| `prev` | Trang ngay trước |
| `next` | Trang ngay sau |
| `last` | Trang cuối cùng |

Ví dụ, với 95 phần tử và size 20:

| Chỉ số trang | Vị trí | Link thường có |
|---:|---|---|
| 0 | Trang đầu | self, first, next, last |
| 1 | Trang giữa | self, first, prev, next, last |
| 2 | Trang giữa | self, first, prev, next, last |
| 3 | Trang giữa | self, first, prev, next, last |
| 4 | Trang cuối | self, first, prev, last |

Các relation thực tế có thể được lược bỏ khi không có trang tương ứng. Client nên kiểm tra sự hiện diện của relation thay vì giả định mọi trang đều có đủ năm link.

### 7.1. Client đi theo href

Một client HAL có thể thực hiện quy trình:

1. Gửi GET đến entry point hoặc URI collection đã biết.
2. Đọc `_embedded.books` để hiển thị content.
3. Đọc metadata `page` để hiển thị vị trí và tổng số kết quả.
4. Tìm `next` trong `_links`.
5. Nếu link tồn tại, gửi GET đến href của link đó.
6. Lặp lại cho đến khi không còn link next.

Client không cần biết trang tiếp theo có query parameter nào, hoặc server dùng offset, cursor hay cách mã hóa khác. Client cần hiểu relation và định dạng hypermedia mà API công bố.

### 7.2. Trang đầu và trang cuối

Ở trang đầu, relation prev thường vắng mặt. Ở trang cuối, relation next thường vắng mặt. Nếu client đang ở trang đầu và không có link prev, giao diện có thể vô hiệu hóa thao tác “Trước”. Tương tự, không có link next nghĩa là client không thể đi tiếp theo luồng hiện tại.

Đừng phát một link next trỏ về chính trang hiện tại để lấp chỗ trống. Điều đó có thể khiến client lặp vô hạn.

### 7.3. Thay đổi dữ liệu trong lúc duyệt trang

Offset pagination có thể gây lặp hoặc bỏ sót phần tử nếu collection thay đổi trong lúc client chuyển từ trang này sang trang khác. Ví dụ, một bản ghi mới được thêm vào đầu collection có thể làm các phần tử dịch chuyển vị trí.

Để giảm rủi ro:

- Dùng thứ tự sắp xếp xác định, có tie-breaker duy nhất như ID.
- Tránh sort không ổn định khi các phần tử có cùng giá trị sắp xếp.
- Với dữ liệu thay đổi liên tục, cân nhắc cursor hoặc keyset pagination.
- Nếu cần ảnh chụp nhất quán, thiết kế snapshot hoặc token truy vấn phù hợp.

`PagedModel` biểu diễn nội dung và metadata của trang; nó không tự bảo đảm snapshot nhất quán giữa nhiều request.

## 8. Trang rỗng và trang vượt phạm vi

Một collection có thể không có phần tử, hoặc client có thể yêu cầu một trang vượt quá phạm vi hiện có.

### 8.1. Collection rỗng

Nếu truy vấn không tìm thấy bản ghi nào, `Page<T>` có thể có:

- Content rỗng.
- `totalElements = 0`.
- `totalPages = 0`.

Server vẫn có thể trả `PagedModel` với link self. Client cần phân biệt collection rỗng với endpoint không tồn tại.

### 8.2. Trang vượt quá phạm vi

Ví dụ, collection có 95 phần tử, size 20, nhưng client yêu cầu `page=10`. Hợp đồng API cần quyết định cách xử lý:

- Trả trang rỗng với metadata phản ánh trang yêu cầu.
- Chuẩn hóa về trang cuối và trả link self tương ứng.
- Trả lỗi nếu trang vượt phạm vi được xem là request không hợp lệ.

Không có một lựa chọn duy nhất đúng cho mọi API. Điều quan trọng là hành vi được tài liệu hóa và kiểm thử. Tránh trả content của trang cuối nhưng metadata lại ghi number là 10, vì client sẽ hiểu sai vị trí của nội dung.

### 8.3. Giới hạn kích thước trang

Không nên cho phép client yêu cầu size tùy ý rất lớn. Hãy cấu hình kích thước mặc định và tối đa để kiểm soát chi phí truy vấn, bộ nhớ và response payload. Nếu client yêu cầu vượt giới hạn, API có thể giới hạn về giá trị tối đa hoặc trả lỗi theo hợp đồng.

## 9. Lọc, sắp xếp và bảo toàn nội dung trang

Một trang chỉ có ý nghĩa khi content, metadata và các link cùng mô tả một tập kết quả.

Ví dụ request:

~~~http
GET /books?category=architecture&page=0&size=10&sort=publishedAt,desc
~~~

Trong trường hợp này:

- Content chỉ chứa sách thuộc category architecture.
- Metadata totalElements và totalPages được tính trên tập đã lọc.
- Link self giữ category, page, size và sort hiện tại.
- Link next thay đổi page nhưng giữ các điều kiện còn lại.

Nếu metadata được tính trên toàn bộ sách nhưng content đã lọc theo category, client sẽ nhận được thông tin tổng số sai. Tương tự, nếu link next làm mất filter, client sẽ chuyển sang một tập dữ liệu khác khi duyệt trang.

Các tham số sort cần được giới hạn vào danh sách thuộc tính công khai. Không nên nối tên cột do client gửi trực tiếp vào SQL hoặc truy vấn động mà không xác thực.

## 10. Kiểm thử nội dung và metadata của PagedModel

Kiểm thử phân trang cần xác nhận các phần tử trong content, metadata và link điều hướng.

Ví dụ với controller dùng `PagedResourcesAssembler`, service trả về một `Page<Book>`:

~~~java
@WebMvcTest(BookController.class)
@Import(BookModelAssembler.class)
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    BookService service;

    @Test
    void returnsPageContentMetadataAndNavigationLinks() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        Page<Book> page = new PageImpl<>(
            List.of(book(id)),
            PageRequest.of(0, 20, Sort.by("title").ascending()),
            45
        );

        given(service.findAll(any(Pageable.class))).willReturn(page);

        mvc.perform(get("/books")
                .param("page", "0")
                .param("size", "20")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.page.size").value(20))
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$.page.totalElements").value(45))
            .andExpect(jsonPath("$.page.totalPages").value(3))
            .andExpect(jsonPath("$._embedded.books[0]._links.self.href")
                .value(endsWith("/books/" + id)))
            .andExpect(jsonPath("$._links.next.href").exists());
    }
}
~~~

Fixture `book(id)` và các kiểu miền là thành phần do ứng dụng kiểm thử định nghĩa. Tên relation `books` phải khớp cấu hình relation của DTO.

Các import chính cho phần test:

~~~java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Trong ứng dụng thực tế, test slice có thể cần import cấu hình Spring Data Web hoặc cấu hình assembler tùy cách dự án đăng ký bean. Hãy giữ test setup tương ứng với cấu hình ứng dụng đang dùng.

### 10.1. Kiểm thử trang đầu và trang cuối

Trang đầu không nên có link prev:

~~~java
.andExpect(jsonPath("$._links.prev").doesNotExist());
~~~

Trang cuối không nên có link next:

~~~java
.andExpect(jsonPath("$._links.next").doesNotExist());
~~~

### 10.2. Kiểm thử collection rỗng

Với kết quả rỗng, xác nhận metadata và link self:

~~~java
.andExpect(jsonPath("$.page.totalElements").value(0))
.andExpect(jsonPath("$.page.totalPages").value(0))
.andExpect(jsonPath("$._links.self.href").exists());
~~~

Không nên mặc định `_embedded.books` luôn có mặt khi content rỗng. Cách serialize collection rỗng có thể phụ thuộc cấu hình relation và serializer.

### 10.3. Kiểm thử filter và sort trong link

Gửi request có filter và sort, sau đó kiểm tra link self/next giữ lại các query parameter theo hợp đồng. Có thể kiểm tra URI đầy đủ hoặc parse query string để tránh phụ thuộc thứ tự các tham số.

## 11. Lỗi thường gặp khi thiết kế PagedModel

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Nhầm Page với PagedModel | Dùng kiểu kết quả truy vấn trực tiếp làm hợp đồng API | Chuyển Page qua PagedResourcesAssembler |
| Chỉ trả content, bỏ metadata | Client không biết vị trí và tổng số trang | Dùng PagedModel khi cần phân trang |
| Chỉ trả metadata, không có link | Client phải tự dựng URI | Phát relation điều hướng phù hợp |
| Dùng number bắt đầu từ 1 trong khi Spring Data bắt đầu từ 0 | Sai lệch trang và link | Thống nhất chỉ số zero-based |
| Dùng size như số phần tử thực tế | Hiển thị sai số phần tử ở trang cuối | Dùng content size hoặc numberOfElements |
| Metadata không khớp filter | Tổng số trang sai | Tính content và metadata trên cùng tập kết quả |
| Link next làm mất filter hoặc sort | Client chuyển sang tập kết quả khác | Giữ query parameters trong link |
| Tạo next ở trang cuối | Client có thể lặp điều hướng | Chỉ phát link khi trang tiếp theo tồn tại |
| Không giới hạn size | Truy vấn và response quá lớn | Đặt size mặc định và tối đa |
| Không có thứ tự sắp xếp ổn định | Phần tử có thể lặp hoặc mất giữa các trang | Dùng sort có tie-breaker duy nhất |

## 12. Quy trình xây dựng phản hồi PagedModel

Khi tạo endpoint phân trang, có thể thực hiện theo trình tự:

1. Xác định collection và các tham số lọc/sắp xếp được hỗ trợ.
2. Nhận `Pageable` từ request và giới hạn kích thước trang.
3. Truy vấn dữ liệu để nhận `Page<T>`.
4. Tạo DTO công khai cho từng member.
5. Dùng `RepresentationModelAssembler` để tạo link cho từng member.
6. Dùng `PagedResourcesAssembler` để chuyển Page thành PagedModel.
7. Xác nhận metadata phản ánh đúng tập kết quả đã lọc.
8. Xác nhận các link self, first, prev, next và last giữ đúng query.
9. Kiểm thử trang đầu, trang giữa, trang cuối, trang rỗng và trang vượt phạm vi.
10. Kiểm tra hiệu năng truy vấn, giới hạn size và tính ổn định của sort.

## 13. Kết luận

`PagedModel<T>` biểu diễn một trang hypermedia gồm nội dung các phần tử, metadata phân trang và các link điều hướng. Nội dung cho biết những member nào nằm trong trang hiện tại; metadata mô tả vị trí, kích thước và tổng số kết quả; link cho phép client đi đến trang khác mà không cần tự dựng URI.

Trong ứng dụng Spring Data, `Page<T>` là kết quả truy vấn còn `PagedResourcesAssembler` chuyển nó thành `PagedModel<D>`. Kết hợp assembler cho từng member giúp mỗi phần tử có link riêng, trong khi PagedResourcesAssembler tạo metadata và link ở cấp trang. Khi content, metadata và query parameters nhất quán, client có thể duyệt collection qua HAL một cách ổn định và dễ thích nghi với thay đổi cách triển khai.

