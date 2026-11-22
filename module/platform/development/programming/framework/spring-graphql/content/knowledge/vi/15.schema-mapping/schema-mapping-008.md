# Mapping interface field trong Spring for GraphQL

GraphQL interface mô tả một nhóm field chung mà nhiều object type cùng cung cấp. Khi client truy vấn một field thông qua interface, server vẫn phải phân giải field đó trên object cụ thể đang được trả về. Trong Spring for GraphQL, `@SchemaMapping` có thể được dùng để triển khai một field chung ở cấp interface, giúp các object type triển khai interface dùng lại cùng một resolver.

Mapping interface field đặc biệt hữu ích khi nhiều loại object có chung một thuộc tính được tính toán hoặc lấy từ service khác, chẳng hạn `displayLabel`, `createdBy`, `permissions` hoặc `category`. Thay vì viết cùng một resolver cho từng object type, ta đặt mapping tại interface và nhận source object thông qua một Java interface hoặc kiểu chung phù hợp.

Sau bài này, bạn có thể:

- Khai báo interface và field chung trong GraphQL SDL.
- Hiểu cách object type triển khai interface và kế thừa hợp đồng field.
- Viết resolver dùng chung bằng `@SchemaMapping` với `typeName` là interface.
- Nhận source object qua Java interface hoặc kiểu cha phù hợp.
- Phân biệt mapping field với TypeResolver.
- Xử lý field arguments, mapping riêng cho object type và lỗi runtime.
- Tránh N+1 khi field chung cần tải dữ liệu từ service/repository.
- Kiểm thử interface field mapping bằng `GraphQlTester`.

## 1. Interface field là gì?

GraphQL interface là một abstract type định nghĩa tập field mà các object type triển khai nó phải cung cấp. Ví dụ, một hệ thống catalog có thể trả về sách và tác giả. Cả hai đều có ID và nhãn hiển thị, nhưng các field đặc thù của chúng khác nhau.

```graphql
interface CatalogEntry {
    id: ID!
    label: String!
}

type Book implements CatalogEntry {
    id: ID!
    label: String!
    title: String!
}

type Author implements CatalogEntry {
    id: ID!
    label: String!
    name: String!
}

type Query {
    catalogEntries: [CatalogEntry!]!
}
```

`CatalogEntry` công bố hai field chung là `id` và `label`. `Book` và `Author` phải có các field này với kiểu tương thích, đồng thời có thể bổ sung field riêng như `title` hoặc `name`.

Client có thể truy vấn field chung trực tiếp trên interface:

```graphql
query {
    catalogEntries {
        __typename
        id
        label
    }
}
```

Nếu cần field đặc thù, client dùng inline fragment:

```graphql
query {
    catalogEntries {
        __typename
        id
        label
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

## 2. Hợp đồng field của interface

Object type triển khai interface phải cung cấp mọi field mà interface khai báo. Tên field, argument bắt buộc và kiểu dữ liệu phải tương thích với hợp đồng interface. Kiểu trả về của object có thể cụ thể hơn khi GraphQL cho phép covariance; object không được làm hợp đồng yếu đi theo cách khiến operation hợp lệ trên interface trở thành không hợp lệ trên object.

Ví dụ interface có argument:

```graphql
interface Searchable {
    summary(maxLength: Int = 80): String!
}

type Book implements Searchable {
    summary(maxLength: Int = 80): String!
    title: String!
}

type Author implements Searchable {
    summary(maxLength: Int = 80): String!
    name: String!
}
```

Argument `maxLength` là một phần của hợp đồng field. Các object type phải triển khai field `summary` tương thích với interface. Một object có thể có thêm argument tùy chọn riêng, nhưng client truy vấn thông qua interface chỉ có thể sử dụng các argument được công bố trên interface.

## 3. Khi nào cần mapping tường minh?

Nếu field interface tương ứng trực tiếp với property hoặc accessor trên source object, GraphQL Java có thể đọc giá trị bằng default property data fetcher. Ví dụ source có `id()` hoặc `getId()` và schema có field `id`, ta thường không cần viết resolver riêng.

Mapping tường minh hữu ích khi field:

- Được tính từ nhiều thuộc tính của source object.
- Cần gọi application service hoặc gateway.
- Có logic chuyển đổi, định dạng hoặc quy tắc nghiệp vụ.
- Có argument ảnh hưởng đến cách tạo giá trị.
- Không tồn tại dưới dạng property trực tiếp trên Java source.

Trong ví dụ catalog, `label` có thể được tính khác nhau tùy loại entry: với sách dùng tiêu đề, với tác giả dùng tên hiển thị. Ta có thể triển khai một resolver chung tại interface thay vì lặp logic cho `Book` và `Author`.

## 4. Chuẩn bị Java model dùng chung

Java model có thể khai báo một interface biểu diễn các phần tử catalog:

```java
public interface CatalogEntryView {
    String id();
}
```

Các kiểu cụ thể triển khai interface đó:

```java
public record BookView(
        String id,
        String title) implements CatalogEntryView {
}

public record AuthorView(
        String id,
        String name) implements CatalogEntryView {
}
```

Java interface và GraphQL interface là hai khái niệm độc lập. Java interface giúp controller nhận một source type chung; SDL vẫn phải khai báo `CatalogEntry`, `Book`, `Author` và quan hệ `implements`. Tên Java `CatalogEntryView` không bắt buộc phải trùng tên GraphQL `CatalogEntry`.

Root resolver trả về các object triển khai Java interface:

```java
@Controller
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public List<CatalogEntryView> catalogEntries() {
        return catalogService.findEntries();
    }
}
```

## 5. Mapping field chung bằng @SchemaMapping

Để xử lý `CatalogEntry.label`, khai báo `@SchemaMapping` với `typeName` là tên GraphQL interface:

```java
@Controller
public class CatalogEntryController {

    private final CatalogLabelService catalogLabelService;

    public CatalogEntryController(CatalogLabelService catalogLabelService) {
        this.catalogLabelService = catalogLabelService;
    }

    @SchemaMapping(typeName = "CatalogEntry", field = "label")
    public String label(CatalogEntryView source) {
        return catalogLabelService.labelFor(source);
    }
}
```

Method được ánh xạ tới field `label` trên interface `CatalogEntry`. Source object là instance cụ thể như `BookView` hoặc `AuthorView`, nhưng tham số Java nhận kiểu chung `CatalogEntryView`. Spring for GraphQL dùng mapping interface cho các object type triển khai interface đó, vì vậy logic field chung có thể được dùng lại.

Có thể lược bỏ `field` nếu tên method trùng tên field và vẫn giữ `typeName` tường minh:

```java
@SchemaMapping(typeName = "CatalogEntry")
public String label(CatalogEntryView source) {
    return catalogLabelService.labelFor(source);
}
```

Trong ví dụ đầu tiên, khai báo cả `typeName` và `field` giúp người đọc thấy rõ mapping đang nhắm tới field nào của interface. Khi dùng mapping ở cấp interface, nên chỉ rõ tên GraphQL interface để tránh framework suy luận từ tên Java interface không trùng với SDL.

## 6. Đặt logic theo loại source trong service

Resolver có thể chuyển source object đến service để áp dụng quy tắc hiển thị:

```java
@Service
public class CatalogLabelService {

    public String labelFor(CatalogEntryView source) {
        if (source instanceof BookView book) {
            return book.title();
        }

        if (source instanceof AuthorView author) {
            return author.name();
        }

        throw new IllegalArgumentException(
                "Unsupported catalog entry: " + source.getClass().getName());
    }
}
```

Với ví dụ nhỏ, service có thể dùng `instanceof` để phân biệt hai kiểu. Khi số loại entry tăng hoặc logic trở nên phức tạp, cân nhắc polymorphism trong domain model, strategy theo loại, mapper riêng hoặc một application service điều phối. Tránh để controller chứa nhiều nhánh nghiệp vụ nếu các quy tắc đó có thể được tái sử dụng ở nơi khác.

Nếu field `label` chỉ đơn giản trả về property đã có trên mỗi source object, hãy cân nhắc bỏ resolver và dùng default property fetcher. Mapping chung chỉ đáng tạo khi có logic thực sự cần thực thi.

## 7. Field arguments trên interface mapping

Interface field có thể nhận argument như field của object type. Ví dụ:

```graphql
interface CatalogEntry {
    id: ID!
    label(maxLength: Int = 80): String!
}

type Book implements CatalogEntry {
    id: ID!
    label(maxLength: Int = 80): String!
    title: String!
}

type Author implements CatalogEntry {
    id: ID!
    label(maxLength: Int = 80): String!
    name: String!
}
```

Resolver nhận source object và argument:

```java
@SchemaMapping(typeName = "CatalogEntry", field = "label")
public String label(
        CatalogEntryView source,
        @Argument("maxLength") Integer maxLength) {

    String value = catalogLabelService.labelFor(source);
    int limit = maxLength != null ? maxLength : 80;

    return value.length() <= limit
            ? value
            : value.substring(0, limit);
}
```

Client có thể truyền argument khi chọn field qua interface:

```graphql
query {
    catalogEntries {
        id
        label(maxLength: 24)
    }
}
```

Giá trị default trong SDL được GraphQL áp dụng khi argument bị bỏ qua. Nếu cần phân biệt argument bị bỏ qua với giá trị null được truyền rõ ràng, có thể dùng `ArgumentValue<T>` theo cơ chế argument binding của Spring for GraphQL. Với ví dụ này, cả hai trường hợp đều có thể dùng giới hạn mặc định nếu đó là semantics mong muốn.

Đoạn code cần kiểm tra `maxLength` hợp lệ, chẳng hạn không âm và không vượt một ngưỡng tối đa. Default value trong schema không thay thế validation nghiệp vụ.

## 8. Mapping cụ thể cho một object type

Có trường hợp phần lớn object type dùng logic chung nhưng một loại cần hành vi riêng. Ví dụ `Book.label` cần thêm mã sách, còn `Author.label` chỉ dùng tên tác giả.

Có thể tạo mapping cụ thể cho field của object type:

```java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "label")
    public String bookLabel(BookView book) {
        return book.title() + " (" + book.id() + ")";
    }
}
```

Khi thiết kế đồng thời mapping interface và mapping cụ thể, hãy bảo đảm mỗi field/object coordinate có một resolver rõ ràng và kiểm tra hành vi thực tế bằng schema integration test. Mapping cụ thể là lựa chọn khi field cần logic riêng theo object type; không nên đăng ký nhiều handler trùng coordinate rồi phụ thuộc vào thứ tự quét controller.

Một cách tổ chức khác là để interface resolver gọi một strategy theo loại source. Cách đó giữ một mapping duy nhất và tập trung việc lựa chọn hành vi trong service. Chọn cách phù hợp với mức độ khác biệt và khả năng tái sử dụng logic.

## 9. Mapping field interface khác TypeResolver

Hai thành phần này thường cùng xuất hiện khi một query trả về interface, nhưng chúng giải quyết hai vấn đề khác nhau:

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| TypeResolver | Xác định object Java thuộc object type GraphQL nào | `BookView` → `Book`, `AuthorView` → `Author` |
| `@SchemaMapping` trên interface | Lấy giá trị cho một field chung của interface | Tính `CatalogEntry.label` |

Ví dụ operation:

```graphql
query {
    catalogEntries {
        __typename
        id
        label
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

Luồng xử lý gồm hai bước riêng:

1. TypeResolver xác định `BookView` là GraphQL type `Book` hoặc `AuthorView` là `Author`, để GraphQL biết concrete type và xử lý inline fragment.
2. Field resolver cho `CatalogEntry.label` cung cấp giá trị `label` trên từng object cụ thể.

Mapping field không thay thế TypeResolver. Ngược lại, TypeResolver chỉ chọn kiểu cụ thể, không tự tính giá trị cho field `label`. Nếu runtime đã có type resolver mặc định phù hợp, không cần đăng ký thêm chỉ vì có interface field mapping; nếu không, cấu hình resolver tường minh bằng `RuntimeWiringConfigurer`.

## 10. Nhiều interface và field chung

Một object type có thể triển khai nhiều interface:

```graphql
interface Node {
    id: ID!
}

interface Auditable {
    createdAt: String!
}

type Book implements Node & Auditable {
    id: ID!
    createdAt: String!
    title: String!
}
```

Có thể tổ chức resolver riêng cho mỗi interface:

```java
@Controller
public class NodeController {

    @SchemaMapping(typeName = "Node", field = "id")
    public String id(NodeView source) {
        return source.id();
    }
}
```

```java
@Controller
public class AuditableController {

    @SchemaMapping(typeName = "Auditable", field = "createdAt")
    public Instant createdAt(AuditableView source) {
        return source.createdAt();
    }
}
```

Các ví dụ giả định Java source type triển khai những interface tương ứng. Nếu object type không có cùng Java abstraction, có thể dùng kiểu source chung rộng hơn hoặc viết resolver cụ thể cho object type đó.

Không nhất thiết phải viết resolver cho field chỉ để chuyển tiếp một getter. Default property fetcher thường đủ cho `id` hoặc `createdAt` nếu accessor tương ứng đã có. Mapping tường minh phù hợp hơn với field cần tính toán, chuyển đổi hoặc gọi service.

## 11. Field mapping và batch loading

Một interface field có thể cần truy cập service ngoài hoặc repository. Ví dụ mọi `CatalogEntry` đều có field `owner`, nhưng owner cần được tải từ một service theo `ownerId`.

Resolver đơn lẻ:

```java
@SchemaMapping(typeName = "CatalogEntry", field = "owner")
public OwnerView owner(CatalogEntryView source) {
    return ownerService.findByEntryId(source.id()).orElse(null);
}
```

Nếu query trả về nhiều catalog entry, cách này có thể tạo N+1 lời gọi. Khi đó, hãy dùng DataLoader hoặc cơ chế batch phù hợp để gom các ID thành một lần truy vấn. Có thể tổ chức batch loader theo source interface nếu mọi loại entry dùng chung quy tắc lấy owner; nếu các loại có quan hệ khác nhau, đăng ký loader hoặc mapping riêng theo từng loại.

Nguyên tắc quan trọng là không để một resolver chung che giấu việc gọi repository riêng cho từng source object. Hãy đo số lần gọi service, query database và độ trễ trước/sau khi thêm batching. Nếu service đã có API nhận danh sách ID, `@BatchMapping` hoặc DataLoader có thể kết nối trực tiếp với API đó.

## 12. Validation, authorization và lỗi của interface field

Field được khai báo trên interface vẫn là field của API công khai. Quy tắc authorization phải áp dụng khi client truy vấn field qua interface hoặc qua concrete object type. Không giả định rằng client chỉ truy vấn field chung nên dữ liệu không nhạy cảm.

Nếu `label` được tạo từ dữ liệu mà một số người dùng không được xem, service mà resolver gọi cần kiểm tra quyền dựa trên security context và resource cụ thể. Không dùng `__typename`, fragment hoặc việc client có chọn field nào làm điều kiện bảo vệ.

Nếu resolver ném exception, GraphQL xử lý lỗi tại field đang được phân giải. Nullability của field interface và các field cha quyết định phạm vi null propagation. Ví dụ `label: String!` không thể trả null; nếu resolver trả null hoặc lỗi, GraphQL sẽ phát execution error và null lan lên field cha gần nhất cho phép null.

Hãy giữ thông điệp lỗi trả về client ở mức phù hợp, đồng thời ghi log chi tiết ở server. Nếu field có thể không có giá trị theo nghiệp vụ, khai báo nullable thay vì ép non-null rồi thường xuyên trả null.

## 13. Kiểm thử interface field mapping

`GraphQlTester` có thể kiểm tra cùng một field chung trên nhiều concrete type. Ví dụ:

```java
graphQlTester.document("""
        query {
            catalogEntries {
                __typename
                id
                label
            }
        }
        """)
    .execute()
    .path("catalogEntries[0].label")
    .entity(String.class)
    .isEqualTo("Spring GraphQL in Practice");
```

Nên kiểm tra thêm một phần tử `Author` để xác nhận mapping chung hoạt động với mọi object type triển khai interface:

```java
graphQlTester.document("""
        query {
            catalogEntries {
                __typename
                label
            }
        }
        """)
    .execute()
    .path("catalogEntries[1].label")
    .entity(String.class)
    .isEqualTo("Nguyen An");
```

Các trường hợp quan trọng:

1. Mỗi concrete type đều nhận đúng giá trị field chung.
2. Inline fragment vẫn lấy đúng field riêng của từng object type.
3. `__typename` phản ánh concrete type mong đợi.
4. Argument của interface field được bind đúng và default value hoạt động.
5. Mapping cụ thể không xung đột với mapping interface.
6. Source object không được hỗ trợ tạo lỗi có thể chẩn đoán.
7. Field nullable/non-null tuân theo hợp đồng khi service trả null hoặc ném lỗi.
8. Authorization được kiểm tra trên từng loại source phù hợp.
9. Batch loader giảm số lần truy cập service/repository khi có nhiều object.

Nên có integration test khởi tạo schema thật để kiểm tra mapping interface. Unit test gọi trực tiếp method Java không đủ để xác nhận annotation được nối đúng với interface field trong GraphQL schema.

## 14. Những lỗi thường gặp

- **Nhầm Java interface với GraphQL interface:** Java interface chỉ là kiểu source; SDL phải khai báo interface và object type `implements`.
- **Quên field trên object type:** mỗi object triển khai interface phải cung cấp field chung với kiểu tương thích.
- **Dùng sai `typeName`:** `typeName` phải là tên GraphQL interface trong SDL, không phải tên class Java.
- **Dùng `@SchemaMapping` nhưng source parameter không phù hợp:** tham số source phải nhận được object thực tế mà root/parent resolver trả về.
- **Cho rằng interface mapping là TypeResolver:** mapping field lấy giá trị; TypeResolver xác định concrete object type.
- **Viết resolver cho mọi field đơn giản:** nếu property fetcher đã đọc được accessor, mapping tường minh có thể không cần thiết.
- **Đăng ký mapping trùng coordinate:** dễ tạo cấu hình khó dự đoán. Mỗi field/object coordinate nên có một handler rõ ràng.
- **Gọi service một lần cho từng source:** có thể tạo N+1. Dùng batch API hoặc DataLoader.
- **Bỏ qua quyền truy cập trên interface field:** mọi field được công bố vẫn phải được bảo vệ ở server.
- **Không kiểm thử từng concrete type:** resolver có thể hoạt động với `Book` nhưng thất bại với `Author` do source model hoặc type resolution khác nhau.

## 15. Quy trình triển khai mapping interface field

Khi thêm một field chung cho nhiều object type, hãy thực hiện:

1. Xác định những object type có cùng ngữ nghĩa field và khai báo GraphQL interface phù hợp.
2. Bảo đảm mọi object type triển khai interface đều định nghĩa field với kiểu và argument tương thích.
3. Xây dựng Java source interface hoặc kiểu cha chung mà các object trả về có thể triển khai.
4. Dùng default property fetcher nếu field chỉ đọc trực tiếp từ source; nếu cần logic, viết `@SchemaMapping(typeName = "InterfaceName", field = "fieldName")`.
5. Nhận source object bằng kiểu Java chung và chuyển logic nghiệp vụ sang service khi cần.
6. Kiểm tra TypeResolver riêng biệt để GraphQL nhận diện đúng concrete object type.
7. Nếu field tải dữ liệu cho nhiều object, dùng batch service, `@BatchMapping` hoặc DataLoader để tránh N+1.
8. Bảo vệ field bằng authorization và xác định nullability/error semantics.
9. Kiểm thử cùng field trên tất cả concrete type, bao gồm fragment, argument và `__typename`.

Mapping interface field giúp triển khai một field chung cho nhiều object type mà không lặp resolver. Trong Spring for GraphQL, `@SchemaMapping` với `typeName` là tên interface cho phép controller cung cấp logic dùng chung dựa trên source object. Khi tách rõ field mapping khỏi TypeResolver, giữ hợp đồng SDL nhất quán và kiểm thử trên từng concrete type, API có thể mở rộng thêm object type mà vẫn duy trì hành vi field chung dễ hiểu.

## Tài liệu tham khảo

- [GraphQL Specification — Interfaces](https://spec.graphql.org/October2021/#sec-Interfaces)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Schema Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.schema-mapping)
- [GraphQL Java — TypeResolver](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/TypeResolver.html)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
