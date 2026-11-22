# Interface trong schema

Trong GraphQL, client thường cần truy vấn những object có một số thuộc tính chung nhưng vẫn có dữ liệu riêng theo từng loại. Ví dụ, hệ thống danh mục có thể quản lý sách, tác giả và tạp chí. Tất cả đều có mã định danh và tên hiển thị, nhưng sách có tiêu đề và ISBN, tác giả có tiểu sử, còn tạp chí có số phát hành. Nếu chỉ dùng object type riêng lẻ, client phải biết trước từng loại để chọn field. **Interface** cho phép schema định nghĩa một hợp đồng field chung mà nhiều object type cùng triển khai.

Interface là một abstract output type trong GraphQL. Nó mô tả các field mà mọi object type triển khai phải cung cấp. Khi một field trong schema trả về interface, giá trị thực tế lúc thực thi vẫn là một object type cụ thể. Nhờ đó, API có thể công bố một kiểu trả về chung trong khi vẫn giữ được dữ liệu chuyên biệt của từng loại object.

Trong Spring for GraphQL, interface được khai báo bằng SDL, các object Java cụ thể được resolver trả về, và GraphQL runtime xác định object type tương ứng khi thực thi. Với interface hoặc union, việc ánh xạ object Java sang GraphQL object type được thực hiện thông qua **TypeResolver**, có thể đăng ký bằng **RuntimeWiringConfigurer**.

## Khai báo interface bằng SDL

Dùng từ khóa **interface** để khai báo interface và danh sách field chung:

~~~graphql
interface CatalogItem {
  id: ID!
  name: String!
}

type Book implements CatalogItem {
  id: ID!
  name: String!
  title: String!
  isbn: String
}

type Author implements CatalogItem {
  id: ID!
  name: String!
  biography: String
}

type Magazine implements CatalogItem {
  id: ID!
  name: String!
  issueNumber: Int!
}
~~~

Trong ví dụ:

- **CatalogItem** là interface, định nghĩa hai field chung id và name.
- **Book**, **Author** và **Magazine** là các object type triển khai interface.
- Mỗi object type phải khai báo các field của interface với kiểu tương thích.
- Mỗi object type có thể bổ sung field riêng, chẳng hạn isbn, biography hoặc issueNumber.

Từ khóa **implements** thể hiện object type cam kết thực hiện hợp đồng của interface. Schema không tạo một object tên CatalogItem để lưu dữ liệu; nó dùng interface làm kiểu trừu tượng để mô tả những object cụ thể có thể được trả về.

## Interface là hợp đồng field chung

Client có thể truy vấn trực tiếp những field được khai báo trên interface mà không cần biết object thực tế là loại nào:

~~~graphql
type Query {
  catalogItem(id: ID!): CatalogItem
  catalogItems: [CatalogItem!]!
}
~~~

Operation sau hoạt động với mọi object type triển khai CatalogItem:

~~~graphql
query Catalog {
  catalogItems {
    id
    name
  }
}
~~~

Vì id và name nằm trong hợp đồng của interface, GraphQL biết rằng cả Book, Author và Magazine đều có thể trả về hai field này. Client có thể viết một query dùng chung để hiển thị danh sách danh mục.

Interface chỉ công bố phần giao nhau giữa các kiểu triển khai. Nếu client cần field riêng của Book, chẳng hạn isbn, thì không thể chọn trực tiếp field đó trên CatalogItem. Client cần dùng inline fragment với type condition on Book. Đây là cách GraphQL giữ hợp đồng chung ổn định mà vẫn cho phép truy cập dữ liệu chuyên biệt.

## Quy tắc khi object type triển khai interface

Schema phải bảo đảm object type thực sự đáp ứng hợp đồng interface. Một số quy tắc quan trọng:

1. **Phải có đầy đủ field của interface.** Nếu CatalogItem khai báo id và name, mọi object type triển khai phải có cả hai field.
2. **Kiểu output phải tương thích.** Field của object phải có kiểu bằng hoặc là kiểu con hợp lệ của kiểu được khai báo trên interface. Ví dụ, nếu interface trả về một interface hoặc union, object có thể trả về một object type cụ thể phù hợp.
3. **Argument đã khai báo phải được giữ nguyên.** Object type phải cung cấp các argument của field interface với cùng tên và kiểu.
4. **Không thêm argument bắt buộc mới.** Object có thể bổ sung argument tùy chọn hoặc có giá trị mặc định, nhưng không được buộc client cung cấp thêm argument mà hợp đồng interface không yêu cầu.
5. **Có thể thêm field riêng.** Những field không nằm trong interface được phép khai báo trên object type cụ thể.

Ví dụ interface có argument:

~~~graphql
interface CatalogItem {
  id: ID!
  name: String!
  relatedItems(limit: Int = 10): [CatalogItem!]!
}

type Book implements CatalogItem {
  id: ID!
  name: String!
  relatedItems(limit: Int = 10): [CatalogItem!]!
  isbn: String
}
~~~

Book phải giữ argument limit với kiểu Int và giá trị mặc định tương thích với hợp đồng. Nếu Book khai báo thêm language: String thì đây là argument tùy chọn nên client gọi qua interface không bắt buộc truyền nó. Nếu Book thêm region: String! mà không có default value, implementation sẽ yêu cầu thông tin mà client không biết từ hợp đồng interface; schema không hợp lệ.

Các quy tắc này giúp client viết query dựa trên interface mà không cần biết chi tiết từng implementation. Nếu một implementation thay đổi field hoặc argument không tương thích, schema validation sẽ phát hiện vấn đề trước khi ứng dụng phục vụ operation.

## Interface là output type

Interface có thể được sử dụng làm kiểu trả về của field, bao gồm field của Query, Mutation, Subscription hoặc field lồng nhau. Nó cũng có thể được bọc trong list và non-null:

~~~graphql
type Query {
  item(id: ID!): CatalogItem
  items: [CatalogItem!]!
}

type Mutation {
  renameItem(id: ID!, name: String!): CatalogItem
}
~~~

Interface không phải kiểu đầu vào. Không thể khai báo argument như find(item: CatalogItem) hoặc input object có field kiểu CatalogItem. Nếu cần nhận dữ liệu từ client, hãy định nghĩa input object type riêng với scalar, enum hoặc input object phù hợp. Phân biệt input và output giúp hợp đồng API rõ ràng và tránh cho client gửi lên những object nội bộ mà server không muốn chấp nhận.

## Truy vấn field chung và field riêng

Với field trả về interface, client có thể chọn field chung trực tiếp và dùng inline fragment cho field riêng:

~~~graphql
query Catalog {
  catalogItems {
    id
    name
    __typename
    ... on Book {
      title
      isbn
    }
    ... on Author {
      biography
    }
    ... on Magazine {
      issueNumber
    }
  }
}
~~~

**__typename** là meta-field do GraphQL cung cấp, cho biết object type thực tế của mỗi phần tử. Inline fragment giới hạn các field được chọn theo kiểu cụ thể. Nếu phần tử là Book, response có title và isbn; nếu là Author, response có biography.

Ví dụ response:

~~~json
{
  "data": {
    "catalogItems": [
      {
        "id": "book-101",
        "name": "Spring in Action",
        "__typename": "Book",
        "title": "Spring in Action",
        "isbn": "9781617297571"
      },
      {
        "id": "author-12",
        "name": "Craig Walls",
        "__typename": "Author",
        "biography": "Software developer and author"
      }
    ]
  }
}
~~~

Inline fragment không lọc phần tử khỏi danh sách. Nó chỉ quyết định field nào được phân giải cho từng object. Nếu client cần lọc danh sách theo loại, hãy cung cấp argument hoặc field tìm kiếm có quy tắc lọc rõ ràng.

## Ánh xạ interface vào Java trong Spring for GraphQL

SDL mô tả interface và object type; phía Java có thể dùng một interface để biểu diễn phần hợp đồng chung:

~~~java
public interface CatalogItem {
    String id();
    String name();
}

public record Book(
        String id,
        String name,
        String title,
        String isbn) implements CatalogItem {
}

public record Author(
        String id,
        String name,
        String biography) implements CatalogItem {
}

public record Magazine(
        String id,
        String name,
        int issueNumber) implements CatalogItem {
}
~~~

Service có thể trả về một implementation cụ thể hoặc một tập hợp các implementation:

~~~java
public interface CatalogService {
    CatalogItem findById(String id);
    List<CatalogItem> findAll();
}
~~~

Controller ánh xạ root field Query:

~~~java
@Controller
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public CatalogItem catalogItem(@Argument String id) {
        return catalogService.findById(id);
    }

    @QueryMapping
    public List<CatalogItem> catalogItems() {
        return catalogService.findAll();
    }
}
~~~

Khi catalogItem trả về một Book, GraphQL cần biết object đó tương ứng với GraphQL object type Book; khi trả về Author, runtime cần nhận diện kiểu Author. Việc này đặc biệt quan trọng vì kiểu trả về được khai báo là CatalogItem, không phải một object type cụ thể.

## Đăng ký TypeResolver

GraphQL Java dùng TypeResolver để xác định object type thực tế cho interface. Spring for GraphQL cung cấp **ClassNameTypeResolver**, hỗ trợ ánh xạ class Java sang tên object type trong SDL.

Ví dụ cấu hình mapping tường minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.ClassNameTypeResolver;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlTypeConfiguration {

    @Bean
    RuntimeWiringConfigurer catalogItemTypeResolver() {
        ClassNameTypeResolver typeResolver = new ClassNameTypeResolver();
        typeResolver.addMapping(Book.class, "Book");
        typeResolver.addMapping(Author.class, "Author");
        typeResolver.addMapping(Magazine.class, "Magazine");

        return builder -> builder.type(
                "CatalogItem",
                typeWiring -> typeWiring.typeResolver(typeResolver)
        );
    }
}
~~~

RuntimeWiringConfigurer được Spring Boot phát hiện khi khởi tạo GraphQL runtime. Cấu hình trên gắn type resolver cho interface CatalogItem. Khi GraphQL nhận một object Java thuộc lớp Book, Author hoặc Magazine, resolver trả về object type tương ứng trong schema.

Tên trong addMapping phải trùng tên object type SDL. Nếu class name đã theo đúng quy ước và không có package hoặc hậu tố làm sai tên GraphQL, có thể dùng quy tắc mặc định của ClassNameTypeResolver; mapping tường minh giúp schema ổn định hơn khi tên class Java khác tên public API.

Nếu cần quy tắc phức tạp hơn, có thể cài đặt graphql.schema.TypeResolver trực tiếp. Resolver nhận TypeResolutionEnvironment, kiểm tra object nguồn và trả về GraphQLObjectType phù hợp. Không nên dựa vào một thuộc tính tùy tiện hoặc tên class không ổn định nếu domain có nhiều implementation hoặc proxy.

## Field của interface và @SchemaMapping

Field được khai báo trên interface là một phần hợp đồng chung. Object type triển khai có thể lấy giá trị từ property accessor mặc định nếu Java object có thuộc tính tương ứng. Khi field cần truy vấn dữ liệu hoặc thực hiện logic, Spring for GraphQL cho phép khai báo resolver bằng @SchemaMapping.

Ví dụ interface có field relatedItems:

~~~graphql
interface CatalogItem {
  id: ID!
  name: String!
  relatedItems: [CatalogItem!]!
}
~~~

Một resolver có thể xử lý field trên các source object triển khai interface:

~~~java
@Controller
public class CatalogItemController {

    private final CatalogService catalogService;

    public CatalogItemController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @SchemaMapping(typeName = "Book", field = "relatedItems")
    public List<CatalogItem> relatedItemsForBook(Book book) {
        return catalogService.findRelated(book.id());
    }

    @SchemaMapping(typeName = "Author", field = "relatedItems")
    public List<CatalogItem> relatedItemsForAuthor(Author author) {
        return catalogService.findRelated(author.id());
    }
}
~~~

Ở đây field relatedItems được ánh xạ riêng cho hai object type cụ thể. Cả hai phương thức có thể gọi cùng một service dùng chung, nhưng mỗi resolver nhận source object đúng kiểu. Với field có property accessor sẵn, GraphQL có thể đọc trực tiếp giá trị mà không cần resolver. Với field cần truy vấn dữ liệu, hãy đăng ký data fetcher trên object type cụ thể và kiểm thử operation cho từng implementation để chắc chắn field được phân giải đúng.

## Interface có thể được triển khai bởi nhiều kiểu

Một object type có thể triển khai nhiều interface. Ví dụ, một nội dung trong hệ thống vừa có thể được định danh như Node, vừa có thông tin thời gian cập nhật:

~~~graphql
scalar DateTime

interface Node {
  id: ID!
}

interface Auditable {
  createdAt: DateTime!
  updatedAt: DateTime!
}

type Book implements Node & Auditable {
  id: ID!
  createdAt: DateTime!
  updatedAt: DateTime!
  title: String!
}
~~~

Book phải đáp ứng hợp đồng của cả Node và Auditable. Client có thể truy vấn field chung theo interface tương ứng, trong khi field title vẫn chỉ có trên Book. Nhiều interface hữu ích khi các khái niệm nghiệp vụ chia sẻ những nhóm hành vi độc lập.

GraphQL cũng hỗ trợ interface triển khai interface khác ở các phiên bản schema/runtime phù hợp. Khi sử dụng khả năng này, cần bảo đảm phiên bản GraphQL Java mà Spring Boot quản lý hỗ trợ cú pháp và quy tắc tương ứng; object type cuối cùng vẫn phải triển khai đầy đủ các field bắt buộc từ toàn bộ interface trong chuỗi kế thừa.

## Interface và Union khác nhau thế nào?

Interface và union đều là abstract output type, nhưng cách mô tả hợp đồng khác nhau:

| Tiêu chí | Interface | Union |
| --- | --- | --- |
| Field chung | Có các field được khai báo trong interface | Không khai báo field nghiệp vụ chung |
| Object member | Object type triển khai bằng implements | Object type được liệt kê trong định nghĩa union |
| Truy vấn field | Chọn trực tiếp field chung; dùng fragment cho field riêng | Dùng inline fragment để chọn field của từng object |
| Mục đích | Biểu diễn các object có chung hợp đồng | Gom các object khác loại vào một kết quả |

Chọn interface khi các kiểu có một tập field chung có ý nghĩa trong domain. Chọn union khi cần biểu diễn nhiều loại kết quả mà không có hợp đồng field chung đáng kể. Không nên tạo interface chỉ để ép những kiểu không liên quan có một field chung hình thức.

## Lỗi thường gặp khi triển khai interface

Một số lỗi thường gặp trong quá trình xây dựng schema và resolver:

- Object type thiếu field bắt buộc của interface hoặc khai báo kiểu field không tương thích.
- Object type bỏ argument của interface, đổi kiểu argument hoặc thêm argument bắt buộc mới.
- Dùng interface làm input argument hoặc field của input object.
- Resolver trả về một class Java không có mapping sang object type GraphQL cụ thể.
- Type resolver trả về tên object type không tồn tại hoặc không thuộc tập implementation của interface.
- Client chọn field riêng của implementation trực tiếp trên interface mà không dùng inline fragment.
- Field chung được khai báo trên interface nhưng resolver hoặc property accessor không cung cấp giá trị tương ứng.

Khi debug, kiểm tra theo thứ tự: SDL có hợp lệ không; object type có thực hiện đầy đủ hợp đồng không; Java resolver trả về class nào; TypeResolver có ánh xạ class đó đúng không; cuối cùng operation có dùng fragment cho field riêng không. Có thể thêm __typename vào query để quan sát kiểu cụ thể mà runtime đang trả về.

## Bảo mật và hiệu năng

Interface giúp client truy vấn nhiều kiểu object qua một hợp đồng chung, nhưng không tự tạo ra quyền truy cập chung cho mọi implementation. Một người dùng có thể được phép đọc Book nhưng không được đọc Author trong một số ngữ cảnh. Hãy kiểm tra quyền ở resolver, service hoặc tầng truy cập dữ liệu theo từng object và field. Không công bố field nhạy cảm trên interface nếu mọi implementation không thể bảo đảm cùng chính sách truy cập.

Field lồng nhau trên interface cũng có thể gây N+1. Ví dụ, query trả về nhiều CatalogItem rồi lấy relatedItems cho từng phần tử có thể tạo một lần truy vấn riêng cho mỗi item. Spring for GraphQL hỗ trợ @BatchMapping và DataLoader để gom các lần tải liên quan. Cần thiết kế batch query thực sự ở tầng repository/service, phân trang danh sách và giới hạn độ sâu hoặc độ phức tạp operation.

Khi kiểm thử, hãy tạo dữ liệu cho từng object type triển khai và xác minh:

- Query field chung hoạt động trên tất cả implementation.
- Query field riêng chỉ xuất hiện trong fragment đúng type.
- __typename trả về đúng tên object type.
- Resolver và type resolver xử lý đúng từng implementation.
- Quyền truy cập được áp dụng theo từng loại dữ liệu.
- Batch loading hoạt động khi truy vấn danh sách nhiều object.

Interface là cách GraphQL mô tả một hợp đồng output chung cho nhiều object type. Trong Spring for GraphQL, SDL định nghĩa hợp đồng, Java model thể hiện các implementation, controller và service cung cấp dữ liệu, còn TypeResolver giúp runtime nhận diện object type thực tế. Khi các phần này nhất quán, client có thể xây dựng query linh hoạt mà vẫn hiểu rõ những field chung và field riêng của từng loại dữ liệu.
