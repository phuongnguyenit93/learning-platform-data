# Phân biệt PagedModel của Spring Data với PagedModel của Spring HATEOAS

## 1. Vì sao hai lớp cùng tên cần được phân biệt?

Trong chương **Biểu diễn kết quả web** của module **Spring Data Commons**, kết quả repository cần được chuyển thành một hợp đồng HTTP phù hợp. Một lỗi dễ gặp là chọn nhầm `PagedModel` do IDE tự import lớp có cùng tên từ thư viện khác.

Hai tên đầy đủ cần nhớ:

~~~java
org.springframework.data.web.PagedModel
org.springframework.hateoas.PagedModel
~~~

Cả hai đều có thể biểu diễn nội dung và metadata của một trang. Tuy nhiên, chúng phục vụ hai mục tiêu khác nhau:

- **Spring Data PagedModel** cung cấp một biểu diễn DTO cho kết quả `Page`, phù hợp khi cần JSON phân trang rõ ràng với nội dung và metadata.
- **Spring HATEOAS PagedModel** là một representation model có khả năng chứa liên kết; nó phù hợp khi API công bố các quan hệ và liên kết điều hướng theo thiết kế hypermedia.

Cùng tên không có nghĩa là cùng kiểu, cùng constructor hoặc cùng hợp đồng JSON.

Sau bài học, bạn cần chọn đúng lớp, đọc đúng generic, chuyển một `Page<T>` sang biểu diễn mong muốn và kiểm tra response thực tế.

## 2. Đặt Page và hai PagedModel vào đúng tầng

~~~text
Repository hoặc template của store
                |
                v
             Page<T>
                |
        Ánh xạ nội dung sang DTO
                |
                v
          Page<BookView>
                |
       +--------+---------+
       |                  |
       v                  v
Spring Data          Spring HATEOAS
PagedModel           PagedModel
       |                  |
       v                  v
content + page       nội dung + metadata
                     + links nếu được thêm
~~~

`Page`, `Pageable`, `Sort` là abstraction thuộc Spring Data Commons. Repository hoặc template của mô-đun lưu trữ chịu trách nhiệm lấy dữ liệu theo khả năng của store.

Hai `PagedModel` nằm ở phía biểu diễn kết quả. Chúng không thay thế repository, không tự chạy truy vấn và không tự tạo một tổng số chính xác từ dữ liệu không có thông tin tổng.

Việc thay lớp response không làm một query chậm trở nên nhanh hơn. Chi phí offset, mapping, count và transaction vẫn cần được xử lý ở tầng thích hợp.

## 3. Bảng đối chiếu quan trọng

| Tiêu chí | Spring Data PagedModel | Spring HATEOAS PagedModel |
| --- | --- | --- |
| Tên đầy đủ | `org.springframework.data.web.PagedModel<T>` | `org.springframework.hateoas.PagedModel<T>` |
| Thư viện cung cấp | Spring Data Commons | Spring HATEOAS |
| Vai trò chính | DTO biểu diễn trang | Model biểu diễn collection phân trang có khả năng mang links |
| Cách tạo thường dùng | `new PagedModel<>(page)` | Assembler hoặc các factory như `PagedModel.of(...)` |
| Generic thường gặp | `PagedModel<BookView>` | `PagedModel<EntityModel<BookView>>` hoặc `PagedModel<BookModel>` |
| Nội dung JSON thông thường | `content` | Phụ thuộc media type; HAL thường dùng `_embedded` |
| Metadata thông thường | `page` | Có metadata phân trang; cách biểu diễn phụ thuộc media type |
| Khả năng chứa links qua HATEOAS RepresentationModel | Không phải mục đích của lớp này | Có |
| Tự sinh links chỉ vì tạo model | Không | Cũng không; cần assembler hoặc thêm links |
| Phải có Spring HATEOAS để dùng | Không | Có |
| Mục tiêu hợp đồng | Nội dung và metadata trang | Representation có quan hệ và điều hướng |

Không biến bảng thành một quy tắc rằng mọi API dùng HATEOAS đều phải có cùng một JSON. Hình dạng trên dây còn phụ thuộc media type, serializer, relation và cấu hình.

## 4. Spring Data PagedModel: biểu diễn trang theo DTO

### 4.1. Ví dụ dữ liệu và dịch vụ

Các đoạn ví dụ dùng Java 17 trở lên. Một DTO công khai:

~~~java
public record BookView(long id, String title) {
}
~~~

Hợp đồng dịch vụ dùng trong bài:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface BookQueryService {
    Page<BookView> search(Pageable pageable);
    BookView required(long id);
}
~~~

Đây là interface của ứng dụng, không phải một service có sẵn trong Spring Data. Implementation cần sử dụng repository hoặc template phù hợp với store.

Có thể ánh xạ entity sang DTO trước khi tạo response:

~~~java
Page<BookView> views = entities.map(
        book -> new BookView(book.getId(), book.getTitle()));
~~~

Snippet giả định `entities` là một `Page<Book>`. `Page.map` chuyển nội dung và duy trì thông tin trang tương ứng; nó không tự tạo truy vấn projection mới ở database.

### 4.2. Controller trả Spring Data PagedModel

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/plain/books")
public class PlainBookController {

    private final BookQueryService service;

    public PlainBookController(BookQueryService service) {
        this.service = service;
    }

    @GetMapping
    public PagedModel<BookView> list(Pageable pageable) {
        return new PagedModel<>(service.search(pageable));
    }
}
~~~

Điểm quyết định nằm ở import:

~~~java
import org.springframework.data.web.PagedModel;
~~~

Ví dụ cần hạ tầng Spring MVC và Spring Data Web đã được cấu hình để phân giải `Pageable`, cùng Jackson để tạo JSON.

Lớp DTO này có trong các dòng Spring Data Commons hỗ trợ cơ chế biểu diễn trang tương ứng, từ Spring Data Commons 3.3. Khi đưa ví dụ vào dự án cũ hơn, cần xác nhận phiên bản dependency trước khi dùng.

### 4.3. JSON dự kiến

Giả sử trang đầu có size 2, tổng cộng 5 phần tử:

~~~json
{
  "content": [
    {
      "id": 101,
      "title": "Repository căn bản"
    },
    {
      "id": 102,
      "title": "Phân trang dữ liệu"
    }
  ],
  "page": {
    "size": 2,
    "number": 0,
    "totalElements": 5,
    "totalPages": 3
  }
}
~~~

Đây là hình dạng điển hình với cấu hình serialization chuẩn. Nó không chứa các liên kết `self`, `next` chỉ vì nội dung là một trang.

Các con số có ý nghĩa riêng:

- `size` là kích thước trang.
- `number` là chỉ số trang nội bộ, bắt đầu từ 0.
- `totalElements` là tổng số phần tử theo kết quả `Page`.
- `totalPages` là tổng số trang được kết quả đó cung cấp.

Ở trang cuối, số phần tử trong `content` có thể nhỏ hơn `size`.

### 4.4. Quan hệ với chế độ VIA_DTO

Một ứng dụng có thể cấu hình cơ chế serialization trang của Spring Data Web:

~~~java
import static org.springframework.data.web.config.EnableSpringDataWebSupport.PageSerializationMode.VIA_DTO;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration(proxyBeanMethods = false)
@EnableSpringDataWebSupport(pageSerializationMode = VIA_DTO)
class PageRepresentationConfiguration {
}
~~~

Cơ chế này hỗ trợ biểu diễn kết quả trang qua DTO thay vì phụ thuộc trực tiếp vào cấu trúc serialization của `PageImpl`.

Trong đường cấu hình được hỗ trợ, controller có thể giữ chữ ký `Page<BookView>` và để hạ tầng chuyển biểu diễn khi serialize kết quả trang tương ứng. Cần kiểm tra nếu ứng dụng dùng một implementation `Page` riêng hoặc serializer riêng.

Các điểm không nên suy diễn:

- `VIA_DTO` không biến response thành HAL.
- `VIA_DTO` không tự thêm Spring HATEOAS navigation links.
- Nó không thay đổi cách query lấy dữ liệu hay count.
- Tùy chỉnh cấu hình web cần được phối hợp với auto-configuration hiện có.

Trả `new org.springframework.data.web.PagedModel<>(page)` là cách làm tường minh tại endpoint. Không cần bật một cơ chế toàn cục chỉ để hiểu ví dụ controller ở trên.

## 5. Spring HATEOAS PagedModel: model cho hypermedia

### 5.1. Generic cho biết phần tử thực sự được chứa

Một kết quả thường gặp là:

~~~java
org.springframework.hateoas.PagedModel<
        org.springframework.hateoas.EntityModel<BookView>>
~~~

Cách đọc từ trong ra ngoài:

1. `BookView` là dữ liệu công khai của sách.
2. `EntityModel<BookView>` có thể chứa dữ liệu sách cùng links của phần tử.
3. `PagedModel<EntityModel<BookView>>` chứa các phần tử đó, metadata trang và links ở cấp collection.

HATEOAS `PagedModel<T>` không tự bọc mọi `T` thành `EntityModel<T>`. Kiểu `T` phụ thuộc cách bạn tạo model hoặc assembler bạn sử dụng.

Nếu một dự án định nghĩa `BookModel extends RepresentationModel<BookModel>`, kết quả có thể là `PagedModel<BookModel>`. Không buộc mọi thiết kế phải dùng `EntityModel`.

### 5.2. PagedResourcesAssembler là cầu nối từ Page

Tên lớp assembler vẫn là:

~~~java
org.springframework.data.web.PagedResourcesAssembler
~~~

Điểm dễ nhầm là package của assembler thuộc Spring Data Web, nhưng kết quả nó tạo ra là **Spring HATEOAS PagedModel**.

Hai hình dạng quan trọng:

~~~java
// Phần tử được bọc thành EntityModel.
assembler.toModel(page);

// Cách tạo model của từng phần tử do itemAssembler quy định.
assembler.toModel(page, itemAssembler);
~~~

Assembler có thể dùng thông tin `Page` và ngữ cảnh web để tạo metadata cùng links điều hướng phù hợp. Links phần tử cần được thiết kế qua item assembler nếu API yêu cầu chúng.

Không chọn Spring Data `PagedModel` làm kiểu trả về cho một lời gọi assembler tạo HATEOAS model.

### 5.3. Item assembler cho sách

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class BookViewAssembler
        implements RepresentationModelAssembler<
                BookView, EntityModel<BookView>> {

    @Override
    public EntityModel<BookView> toModel(BookView book) {
        return EntityModel.of(
                book,
                linkTo(methodOn(HypermediaBookController.class)
                        .one(book.id()))
                        .withSelfRel());
    }
}
~~~

Ở đây `self` của một sách trỏ tới endpoint chi tiết. Nó khác với `self` ở cấp trang, vốn trỏ tới tài nguyên collection tại cửa sổ hiện tại.

`methodOn` được dùng để mô tả lời gọi phục vụ dựng link; không phải thực hiện truy vấn dịch vụ lấy sách ở thời điểm tạo link.

### 5.4. Controller dùng HATEOAS PagedModel

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/hypermedia/books")
public class HypermediaBookController {

    private final BookQueryService service;
    private final BookViewAssembler itemAssembler;

    public HypermediaBookController(
            BookQueryService service,
            BookViewAssembler itemAssembler) {

        this.service = service;
        this.itemAssembler = itemAssembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public PagedModel<EntityModel<BookView>> list(
            Pageable pageable,
            PagedResourcesAssembler<BookView> assembler) {

        return assembler.toModel(
                service.search(pageable),
                itemAssembler);
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<BookView> one(
            @PathVariable("id") long id) {

        return itemAssembler.toModel(service.required(id));
    }
}
~~~

Import quyết định lần này là:

~~~java
import org.springframework.hateoas.PagedModel;
~~~

Ví dụ cần Spring HATEOAS, media-type/serialization support tương ứng và tích hợp Spring Data Web hỗ trợ phân giải `PagedResourcesAssembler`. Chỉ có `spring-data-commons` không tự bảo đảm toàn bộ hạ tầng HAL đã được đăng ký.

Mỗi kiểu public được đặt trong file Java tương ứng khi triển khai thật. Các snippet cùng nhau mô tả ví dụ, không phải một file Java duy nhất.

### 5.5. HAL JSON và collection relation

Với HAL và collection relation được đặt là `books`, một phản hồi có thể mang hình dạng sau. Ví dụ rút gọn tập links để tập trung vào `self` và `next`:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": 101,
        "title": "Repository căn bản",
        "_links": {
          "self": {
            "href": "https://api.example.test/hypermedia/books/101"
          }
        }
      },
      {
        "id": 102,
        "title": "Phân trang dữ liệu",
        "_links": {
          "self": {
            "href": "https://api.example.test/hypermedia/books/102"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/hypermedia/books?page=0&size=2"
    },
    "next": {
      "href": "https://api.example.test/hypermedia/books?page=1&size=2"
    }
  },
  "page": {
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Để tên `books` là một quyết định rõ ràng thay vì phụ thuộc tên được suy ra, biến thể hypermedia có thể khai báo DTO như sau:

~~~java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "book", collectionRelation = "books")
public record BookView(long id, String title) {
}
~~~

Đây là cách khai báo thay cho record BookView trước đó trong biến thể cần HATEOAS, không phải tạo thêm một kiểu trùng tên trong cùng package.

Nếu muốn DTO dữ liệu không phụ thuộc annotation HATEOAS, ứng dụng có thể dùng representation model hoặc cơ chế relation riêng ở lớp biểu diễn.

Không cố định `_embedded.books` trong client chỉ dựa vào tên class Java mà chưa xác định relation của API. Relation là một phần hợp đồng cần được kiểm tra.

## 6. Tạo HATEOAS PagedModel thủ công không tự sinh navigation links

Có thể tạo model từ nội dung và metadata:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

Page<BookView> result = service.search(pageable);

List<EntityModel<BookView>> items = result.getContent().stream()
        .map(itemAssembler::toModel)
        .toList();

PagedModel.PageMetadata metadata = new PagedModel.PageMetadata(
        result.getSize(),
        result.getNumber(),
        result.getTotalElements(),
        result.getTotalPages());

PagedModel<EntityModel<BookView>> model =
        PagedModel.of(items, metadata);
~~~

Snippet giả định `service`, `pageable` và `itemAssembler` có từ ví dụ trước.

Cách này tạo HATEOAS model và các item model theo assembler phần tử. Nó chưa tự thêm `self`, `next`, `prev` ở cấp collection.

Muốn có navigation links, cần dùng `PagedResourcesAssembler` hoặc tự tạo links đúng chính sách API.

Nếu tạo thủ công, ứng dụng phải chịu trách nhiệm cho:

- URL cơ sở và đường dẫn endpoint.
- Tham số page, size, sort và các bộ lọc cần giữ.
- Quy ước chỉ số trang.
- Điều kiện tồn tại link next hoặc prev.
- Tính nhất quán giữa links, metadata và dữ liệu trả về.

Không nối chuỗi URL bằng cách thay toàn bộ query thành `page=...` rồi làm mất các bộ lọc đang áp dụng.

## 7. Hai kiểu không chuyển đổi được bằng cast hoặc đổi import

Java không coi hai lớp cùng tên đơn giản là tương thích.

Hai import sau không thể đồng thời cung cấp cùng tên đơn giản trong một compilation unit:

~~~java
import org.springframework.data.web.PagedModel;
import org.springframework.hateoas.PagedModel;
~~~

Nếu cần nhắc cả hai trong một đoạn code, dùng tên đầy đủ cho ít nhất một lớp:

~~~java
org.springframework.data.web.PagedModel<BookView> simple =
        new org.springframework.data.web.PagedModel<>(page);

org.springframework.hateoas.PagedModel<
        org.springframework.hateoas.EntityModel<BookView>> hypermedia =
        assembler.toModel(page);
~~~

Snippet giả định `page` là `Page<BookView>`, còn `assembler` là `PagedResourcesAssembler<BookView>`.

Các cách làm sai thường gặp:

~~~java
// Sai ý tưởng: không thể cast hai model không tương thích
// để chuyển một hợp đồng response thành hợp đồng còn lại.

// Sai import: constructor nhận Page của Spring Data model
// không phải constructor dùng chung của mọi lớp tên PagedModel.
~~~

Việc chuyển đổi đúng bắt đầu từ nguồn dữ liệu có nội dung và metadata, chẳng hạn `Page<BookView>`, rồi xây biểu diễn đích.

Đổi import của controller mà không sửa cách tạo model, generic và cấu hình serialization có thể gây lỗi biên dịch hoặc làm thay đổi response ngoài ý muốn.

## 8. Phân biệt metadata trang với hypermedia

Cả hai model có thể công bố:

~~~text
size
number
totalElements
totalPages
~~~

Điều đó không có nghĩa client sử dụng hai API theo cùng cách.

Với biểu diễn nội dung và metadata, client có thể chủ động tính tham số trang tiếp theo theo hợp đồng đã biết.

Với API hypermedia, client có thể dùng relation `next` để tiếp tục duyệt thay vì tự ghép URL. Đây là giá trị của links khi server thiết kế chúng có ý nghĩa.

Tuy nhiên:

- Có class HATEOAS không bảo đảm API đã có đầy đủ links cần thiết.
- Có links không bảo đảm client thực sự sử dụng chúng.
- Có `page` metadata không có nghĩa response là HAL.
- Một object JSON có trường tên `_links` cũng chưa đủ chứng minh toàn bộ media type và hợp đồng đã đúng.

Cần kiểm tra cả kiểu Java, cấu hình media type và response trên dây.

## 9. Những điều không model nào tự giải quyết

### 9.1. Tổng số và khả năng của store

Hai model thường được tạo từ kết quả có thông tin tổng như `Page`. Chúng không tự chứng minh count rẻ hoặc count chính xác theo yêu cầu nghiệp vụ.

Một `Slice` chỉ cung cấp thông tin về cửa sổ và khả năng còn kết quả tiếp theo; không nên bịa `totalElements` để ép nó vào một hợp đồng đòi tổng số.

Tương tự, một `List` không đủ chứng minh tổng số của toàn bộ tập dữ liệu. Có thể tạo metadata thủ công, nhưng ứng dụng phải có căn cứ cho các giá trị đã công bố.

Chọn `Page`, `Slice` hay một biểu diễn cursor là quyết định truy vấn và hợp đồng. Nó không được quyết định chỉ vì IDE gợi ý một class PagedModel.

### 9.2. Quy ước chỉ số trang

Các ví dụ trong bài dùng chỉ số nội bộ bắt đầu từ 0.

Cấu hình resolver nhận đầu vào bắt đầu từ 1 không làm `PageRequest` chuyển sang cách đánh số từ 1. Với HATEOAS assembler tích hợp resolver, cần kiểm tra cả metadata và links theo cấu hình thực tế; không tự cộng hoặc trừ một lần nữa theo phỏng đoán.

Spring Data DTO lấy thông tin từ `Page` được truyền vào; đừng mặc định một thuộc tính parse request sẽ tự đổi mọi lớp DTO phản hồi.

Nếu hợp đồng yêu cầu một quy ước riêng, hãy chọn một điểm chuyển đổi rõ ràng và kiểm tra đồng bộ request, response, links cùng tài liệu.

### 9.3. Mapping và dữ liệu nhạy cảm

Bọc `Page<Entity>` trong bất kỳ PagedModel nào không tự loại bỏ các field nhạy cảm.

Nên chọn DTO hoặc projection công khai phù hợp trước khi tạo model. Links cũng không thay thế kiểm tra quyền tại endpoint đích.

Một link chi tiết được gửi cho client không phải bằng chứng rằng mọi người dùng đều được quyền đọc tài nguyên đó.

### 9.4. Môi trường triển khai và URL công khai

Links tạo trong môi trường có reverse proxy cần phản ánh scheme, host và prefix công khai đã được cấu hình đúng.

Không coi URL nội bộ của container là URL API client phải truy cập. Đồng thời, việc tin cậy forwarded headers cần theo cấu hình hạ tầng của ứng dụng.

Chỉ dẫn ở đây là kiểm tra đường link thực tế trong môi trường triển khai; thay PagedModel không tự sửa cấu hình proxy.

### 9.5. Trang rỗng

Spring Data DTO vẫn có thể biểu diễn content rỗng cùng metadata của kết quả trang.

Ở phía HAL, relation của collection rỗng có thể cần thông tin kiểu hoặc cấu hình bổ sung, vì không còn phần tử để suy ra kiểu nội dung. Không tự kết luận `_embedded.books` luôn có mặt với một mảng rỗng ở mọi cách tạo model.

Khi cần một contract cụ thể cho trang rỗng, hãy dùng cơ chế empty-model/fallback type phù hợp của phiên bản HATEOAS và assembler đang dùng, rồi kiểm tra JSON thực tế.

## 10. Chọn biểu diễn theo nhu cầu của API

| Nhu cầu | Lựa chọn nên cân nhắc |
| --- | --- |
| JSON có content và metadata trang | Spring Data PagedModel |
| Chuẩn hóa serialization PageImpl theo cơ chế Spring Data Web | VIA_DTO, với cấu hình và phiên bản phù hợp |
| API công bố navigation links và relations | Spring HATEOAS PagedModel cùng assembler |
| Links cho từng phần tử và collection | Item assembler kết hợp PagedResourcesAssembler |
| Schema phải khớp một hợp đồng riêng đã có | DTO ứng dụng tự định nghĩa |
| Không cần tổng số | Thiết kế hợp đồng Slice hoặc cursor phù hợp |

Spring Data PagedModel không phải một HATEOAS PagedModel “thiếu cấu hình”. Nó đã có mục tiêu riêng là biểu diễn trang theo DTO.

Ngược lại, không chọn HATEOAS chỉ để có một trường `totalPages`; metadata trang cũng có thể tồn tại trong biểu diễn đơn giản hơn.

Không có yêu cầu phải thay toàn bộ endpoint của một ứng dụng bằng cùng một lớp chỉ vì cả hai dependency đều có trên classpath. Mỗi endpoint cần hợp đồng rõ ràng, và client cần biết media type nào được hỗ trợ.

## 11. Kiểm tra hợp đồng thay vì chỉ kiểm tra kiểu Java

### 11.1. Kiểm tra endpoint dùng Spring Data PagedModel

Với fixture trang đầu size 2, tổng 5 phần tử:

~~~java
mockMvc.perform(get("/plain/books")
        .param("page", "0")
        .param("size", "2")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.content[0].id").value(101))
    .andExpect(jsonPath("$.page.number").value(0))
    .andExpect(jsonPath("$.page.size").value(2))
    .andExpect(jsonPath("$.page.totalElements").value(5))
    .andExpect(jsonPath("$.page.totalPages").value(3))
    .andExpect(jsonPath("$._links").doesNotExist());
~~~

Snippet giả định MockMvc, service fixture và các static import đã được cấu hình phù hợp. Đây là ví dụ điều cần kiểm tra, không phải một test class hoàn chỉnh.

Nếu API cố ý có một envelope bổ sung, JSON path phải bám theo hợp đồng envelope đó.

### 11.2. Kiểm tra endpoint HAL

Với relation `books` đã được cấu hình:

~~~java
mockMvc.perform(get("/hypermedia/books")
        .param("page", "0")
        .param("size", "2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.books[0].id").value(101))
    .andExpect(jsonPath("$._embedded.books[0]._links.self.href").exists())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$.page.totalElements").value(5));
~~~

Ngoài sự tồn tại, cần kiểm tra href trỏ đúng endpoint và giữ các tham số cần thiết. Một link tồn tại nhưng trỏ sang host hoặc trang sai vẫn vi phạm hợp đồng.

Cũng cần xác nhận Content-Type HAL thực tế của response. Chỉ gửi Accept HAL chưa chứng minh cấu hình serialization đã đúng.

### 11.3. Ma trận tình huống

| Tình huống | Điều cần xác minh |
| --- | --- |
| Trang đầu còn kết quả tiếp theo | Metadata đúng; HAL có next phù hợp |
| Trang cuối | Không quảng bá next không tồn tại |
| Trang giữa | Links điều hướng giữ bộ lọc và sort cần thiết |
| Kết quả rỗng | Shape content/embedded đúng hợp đồng |
| DTO có ít field hơn entity | Response không lộ field ngoài hợp đồng |
| Đổi tên query parameter | Links và resolver vẫn dùng cùng quy tắc |
| Chỉ số đầu vào bắt đầu từ 1 | Request, metadata, links không lệch một trang |
| Reverse proxy | URL công khai đúng scheme, host và prefix |
| Có cả hai thư viện | Import và generic của từng endpoint vẫn đúng |
| Nâng dependency | Shape JSON và media type không thay đổi ngoài chủ đích |

Test gọi trực tiếp `new PagedModel<>(page)` chỉ chứng minh tạo object. Kiểm tra HTTP với cấu hình Jackson và media type thực tế mới giúp đánh giá hợp đồng trên dây.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Constructor không nhận Page | Import nhầm HATEOAS PagedModel | Kiểm tra tên đầy đủ của lớp |
| toModel trả kiểu không gán được | Khai báo biến bằng Spring Data PagedModel | Dùng đúng HATEOAS generic |
| Bật VIA_DTO nhưng không có links | Nhầm DTO serialization với hypermedia | Dùng HATEOAS và assembler khi cần links |
| Có HATEOAS model nhưng thiếu next | Tạo model thủ công chưa thêm navigation | Dùng assembler hoặc xây links có kiểm soát |
| Client tìm content trong HAL | Dùng schema của endpoint khác | Đọc đúng media type và relation |
| Tên embedded đổi ngoài dự kiến | Phụ thuộc relation được suy ra | Quy định relation và kiểm tra contract |
| Trang rỗng không có embedded như mong muốn | Thiếu thông tin kiểu/cấu hình empty model | Thiết kế và kiểm tra riêng trang rỗng |
| Tổng số được đặt bằng số phần tử trang | Không có thông tin tổng thực sự | Đổi hợp đồng hoặc lấy tổng có căn cứ |
| Links công khai chứa địa chỉ nội bộ | Cấu hình URL/proxy không đúng | Kiểm tra link trong môi trường triển khai |
| Dùng cast để chuyển hai model | Coi hai lớp cùng tên là cùng kiểu | Xây biểu diễn đích từ nguồn Page/metadata |

## 13. Bài thực hành

1. Tạo một dịch vụ trả `Page<BookView>` và xác định mô-đun lưu trữ có thể cung cấp dữ liệu cùng tổng số như thế nào.
2. Tạo endpoint trả `org.springframework.data.web.PagedModel<BookView>`.
3. Tạo endpoint khác trả `org.springframework.hateoas.PagedModel<EntityModel<BookView>>` qua assembler.
4. Khai báo relation công khai cho collection ở biến thể HAL.
5. So sánh `content`, `_embedded`, `page` và `_links` trên response thực tế.
6. Kiểm tra trang đầu, trang cuối và trang rỗng.
7. Kiểm tra links phần tử khác links collection ở đâu và chúng trỏ tới tài nguyên nào.
8. Giải thích vì sao đổi import hoặc bật VIA_DTO không thay thế việc thiết kế API hypermedia.

Bài thực hành đạt yêu cầu khi bạn chọn đúng **package**, đọc đúng **generic**, phân biệt được **DTO trang** với **representation có links**, và chứng minh hợp đồng HTTP bằng JSON cùng media type thực tế.
