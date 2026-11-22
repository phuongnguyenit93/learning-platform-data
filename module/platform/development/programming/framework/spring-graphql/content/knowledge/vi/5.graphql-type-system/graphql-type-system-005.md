# Interface type

Trong GraphQL, `interface` mô tả một tập field chung mà nhiều object type có thể cùng triển khai. Nó hữu ích khi API trả về nhiều loại đối tượng khác nhau nhưng các đối tượng đó có một số thuộc tính chung, chẳng hạn sách và phim đều có mã định danh, tiêu đề và ngày phát hành.

Client có thể truy vấn các field chung thông qua interface mà không cần biết trước object type cụ thể. Khi cần dữ liệu riêng của từng loại, client dùng inline fragment hoặc named fragment. Server xác định object type thực tế của mỗi kết quả để GraphQL thực thi đúng các field được chọn.

Trong Spring for GraphQL, schema SDL khai báo interface và các object type triển khai nó; controller hoặc resolver cung cấp dữ liệu, còn runtime type resolver giúp GraphQL xác định kiểu cụ thể khi cần.

## 1. Interface type giải quyết vấn đề gì?

Giả sử một ứng dụng thư viện số quản lý sách và tạp chí. Hai loại nội dung có những field khác nhau, nhưng đều có mã định danh và tiêu đề. Nếu không có interface, client phải gọi các query riêng hoặc xử lý hai cấu trúc độc lập dù phần lớn giao diện hiển thị giống nhau.

Ta có thể mô hình hóa phần dữ liệu chung bằng interface:

```graphql
interface Publication {
    id: ID!
    title: String!
}

type Book implements Publication {
    id: ID!
    title: String!
    author: String!
}

type Magazine implements Publication {
    id: ID!
    title: String!
    issueNumber: Int!
}
```

`Publication` công bố hợp đồng gồm `id` và `title`. `Book` và `Magazine` phải triển khai các field đó, đồng thời có thể bổ sung field riêng như `author` hoặc `issueNumber`.

Interface là một abstract output type. Nó không phải object có thể được tạo trực tiếp trong response. Khi một field có kiểu `Publication`, giá trị thực tế phải thuộc một object type cụ thể triển khai interface đó.

## 2. Khai báo interface trong SDL

Cú pháp cơ bản:

```graphql
interface InterfaceName {
    fieldA: String!
    fieldB(argument: ID): Int
}
```

Một interface có thể khai báo field và argument giống object type. Các object type triển khai interface bằng từ khóa `implements`:

```graphql
interface Node {
    id: ID!
}

type Customer implements Node {
    id: ID!
    name: String!
}

type Order implements Node {
    id: ID!
    status: String!
}
```

Khi một object type triển khai interface, nó phải cung cấp tất cả field mà interface yêu cầu với kiểu tương thích. Object type có thể khai báo thêm field riêng. Nếu một object triển khai nhiều interface, có thể liệt kê chúng bằng dấu `&`:

```graphql
interface Timestamped {
    createdAt: String!
}

type Customer implements Node & Timestamped {
    id: ID!
    createdAt: String!
    name: String!
}
```

Trong ví dụ này, `Customer` phải thỏa cả hợp đồng `Node` lẫn `Timestamped`.

## 3. Quy tắc tương thích giữa interface và object type

Khi thiết kế interface, cần giữ hợp đồng nhất quán giữa interface và các kiểu triển khai.

- Object type phải có mọi field được khai báo trong interface.
- Field tương ứng phải có cùng tên và các argument được interface khai báo phải có cùng tên, kiểu và giá trị mặc định.
- Kiểu output của object field phải giống hoặc tương thích theo hướng cụ thể hơn so với kiểu của interface field. Ví dụ interface trả `String` thì object có thể trả `String!`.
- Object type được phép thêm field riêng để mô tả dữ liệu đặc thù.
- Object type không được thêm argument bắt buộc mà client truy vấn qua interface không thể cung cấp; argument bổ sung phải là tùy chọn.

Ví dụ hợp lệ về kiểu output cụ thể hơn:

```graphql
interface SearchResult {
    title: String
}

type Book implements SearchResult {
    title: String!
    isbn: String!
}
```

`String!` là kiểu cụ thể hơn `String`: mọi giá trị hợp lệ của `String!` cũng là giá trị hợp lệ của `String`. Chiều ngược lại không đúng, vì `String` có thể là null.

Ví dụ không hợp lệ:

```graphql
interface SearchResult {
    title: String!
}

type Book implements SearchResult {
    title: String
}
```

Object `Book` có thể trả `null` cho `title`, trong khi interface cam kết field này không null. Schema không thể bảo đảm hợp đồng mà interface công bố.

Một interface nên chứa những field thực sự có ý nghĩa đối với mọi kiểu triển khai. Nếu phải thêm nhiều field giả hoặc trả về giá trị không tự nhiên chỉ để thỏa interface, hãy xem lại ranh giới trừu tượng.

## 4. Dùng interface làm kiểu trả về

Interface thường xuất hiện ở kiểu trả về của field trong query hoặc field lồng nhau. Ví dụ:

```graphql
interface Media {
    id: ID!
    title: String!
}

type Movie implements Media {
    id: ID!
    title: String!
    durationMinutes: Int!
}

type Series implements Media {
    id: ID!
    title: String!
    seasonCount: Int!
}

type Query {
    media(id: ID!): Media
    searchMedia(keyword: String!): [Media!]!
}
```

`media` có thể trả về một `Movie` hoặc `Series`. `searchMedia` có thể trả về danh sách gồm nhiều kiểu concrete khác nhau. Từ góc nhìn schema, client biết chắc mọi phần tử đều có `id` và `title`.

Interface là output type nên có thể dùng làm kiểu trả về cho field, kể cả phần tử trong list. Không dùng interface làm argument hoặc field của input object. GraphQL có các input type riêng như scalar, enum và input object để mô tả dữ liệu client gửi lên.

## 5. Truy vấn interface và dùng inline fragment

Client có thể chọn field chung trực tiếp trên interface:

```graphql
query {
    searchMedia(keyword: "spring") {
        id
        title
    }
}
```

Nếu muốn lấy field chỉ có ở một object type, dùng inline fragment:

```graphql
query {
    searchMedia(keyword: "spring") {
        id
        title
        ... on Movie {
            durationMinutes
        }
        ... on Series {
            seasonCount
        }
    }
}
```

GraphQL chỉ thực thi phần fragment phù hợp với kiểu concrete của kết quả. Một phần tử có kiểu `Movie` sẽ có `durationMinutes`; phần tử kiểu `Series` sẽ có `seasonCount`.

Có thể dùng named fragment để tái sử dụng selection set:

```graphql
fragment MediaSummary on Media {
    id
    title
}

query SearchMedia($keyword: String!) {
    searchMedia(keyword: $keyword) {
        ...MediaSummary
        ... on Movie {
            durationMinutes
        }
        ... on Series {
            seasonCount
        }
    }
}
```

Fragment `MediaSummary` áp dụng trên interface `Media`, vì vậy chỉ chọn các field mà interface bảo đảm. Fragment cụ thể trên `Movie` hoặc `Series` mới có thể truy cập field riêng của từng object type.

## 6. Xác định kiểu concrete bằng `__typename`

Với một interface, client thường cần biết kiểu object thực tế để hiển thị đúng giao diện hoặc xử lý kết quả. GraphQL cung cấp meta-field `__typename`:

```graphql
query {
    searchMedia(keyword: "spring") {
        __typename
        id
        title
    }
}
```

Response có thể chứa các phần tử khác kiểu:

```json
{
  "data": {
    "searchMedia": [
      {
        "__typename": "Movie",
        "id": "m-101",
        "title": "Spring Journey"
      },
      {
        "__typename": "Series",
        "id": "s-205",
        "title": "The Framework"
      }
    ]
  }
}
```

`__typename` trả về tên GraphQL object type thực tế, không phải tên Java class. Nó hữu ích khi client cache entity, phân nhánh giao diện hoặc xử lý dữ liệu đa hình.

## 7. Runtime type resolution trong GraphQL Java

Khi field có kiểu interface, GraphQL runtime cần xác định object type cụ thể của mỗi giá trị trước khi thực thi các field được chọn. Quá trình này gọi là type resolution.

Ví dụ resolver của `searchMedia` trả về một danh sách Java gồm `Movie` và `Series`. GraphQL cần biết phần tử thứ nhất tương ứng với GraphQL type `Movie`, phần tử thứ hai tương ứng với `Series`.

Có hai hướng phổ biến:

1. Cung cấp `TypeResolver` cho interface để dựa vào đối tượng Java thực tế và trả về `GraphQLObjectType` tương ứng.
2. Cấu hình cơ chế `isTypeOf` trên các object type để xác định một giá trị có thuộc kiểu đó hay không.

Nếu không có cơ chế nhận diện phù hợp, query chọn field qua interface có thể gặp lỗi kiểu không xác định khi thực thi.

## 8. Cấu hình TypeResolver với Spring for GraphQL

Trong Spring for GraphQL, có thể đăng ký `RuntimeWiringConfigurer` để cấu hình type resolver cho interface. Ví dụ schema dùng `Media`, `Movie` và `Series` ở phần trên.

Các kiểu Java biểu diễn dữ liệu:

```java
public interface MediaItem {
    String id();
    String title();
}

public record Movie(
    String id,
    String title,
    int durationMinutes
) implements MediaItem {}

public record Series(
    String id,
    String title,
    int seasonCount
) implements MediaItem {}
```

Đăng ký type resolver:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer mediaTypeResolver() {
        return builder -> builder.type("Media", typeWiring ->
            typeWiring.typeResolver(environment -> {
                Object source = environment.getObject();

                if (source == null) {
                    throw new IllegalStateException("Media source must not be null");
                }
                if (source instanceof Movie) {
                    return environment.getSchema().getObjectType("Movie");
                }
                if (source instanceof Series) {
                    return environment.getSchema().getObjectType("Series");
                }

                throw new IllegalStateException(
                    "Unsupported Media implementation: " +
                    source.getClass().getName()
                );
            })
        );
    }
}
```

`RuntimeWiringConfigurer` cho phép bổ sung cấu hình runtime vào quá trình tạo GraphQL schema. Resolver đọc đối tượng nguồn bằng `environment.getObject()`, kiểm tra kiểu Java rồi lấy object type tương ứng từ schema.

Trong dự án thực tế, nên xử lý trường hợp `source` null một cách có chủ đích nếu mô hình dữ liệu có thể trả null. Với field interface được khai báo non-null, resolver của field cha cũng phải bảo đảm trả về một giá trị hợp lệ.

Controller có thể trả về các implementation cụ thể:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class MediaController {

    private final MediaService mediaService;

    public MediaController(MediaService mediaService) {
        this.mediaService = mediaService;
    }

    @QueryMapping
    public List<MediaItem> searchMedia(@Argument String keyword) {
        return mediaService.search(keyword);
    }
}
```

Các field chung như `id` và `title` có thể được đọc từ property hoặc accessor của đối tượng. Nếu cần logic lấy dữ liệu riêng, có thể ánh xạ field bằng `@SchemaMapping`. Type resolver vẫn chịu trách nhiệm xác định object type thực tế cho interface.

## 9. Interface và Union khác nhau thế nào?

Cả interface và union đều cho phép một field trả về nhiều object type concrete. Điểm khác biệt là interface công bố một hợp đồng field chung, còn union chỉ liệt kê các kiểu có thể xuất hiện.

| Tiêu chí | Interface | Union |
| --- | --- | --- |
| Khai báo field chung | Có | Không |
| Object type triển khai | Dùng `implements` | Được liệt kê bằng `=` và `\|` |
| Truy vấn field trực tiếp | Có thể chọn field của interface | Phải dùng fragment để chọn field của object type |
| Phù hợp khi | Các kiểu có cùng một hợp đồng dữ liệu | Các kiểu khác nhau nhưng cùng là kết quả của một field |

Ví dụ union:

```graphql
union SearchHit = Book | Author

type Query {
    search(keyword: String!): [SearchHit!]!
}
```

Client phải dùng fragment để lấy field:

```graphql
query {
    search(keyword: "GraphQL") {
        ... on Book {
            id
            title
        }
        ... on Author {
            id
            name
        }
    }
}
```

Nếu `Book` và `Author` cùng có một hợp đồng field thực sự ổn định như `id` và `displayName`, interface có thể diễn đạt tốt hơn. Nếu chúng không có field chung có ý nghĩa, union thường phù hợp hơn.

## 10. Những lỗi thường gặp khi dùng interface

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Object type thiếu field của interface | Chưa triển khai đủ hợp đồng | Bổ sung field và kiểu tương thích |
| Object field yếu hơn interface field | Ví dụ interface khai báo `String!` nhưng object trả `String` | Điều chỉnh nullability hoặc hợp đồng interface |
| Dùng interface trong input object | Interface là output type | Khai báo input object riêng |
| Query field riêng trực tiếp trên interface | Field đó chỉ tồn tại ở concrete type | Dùng inline fragment hoặc named fragment |
| Runtime không nhận diện được kiểu concrete | Thiếu hoặc cấu hình sai type resolver | Đăng ký `TypeResolver` hoặc cơ chế `isTypeOf` phù hợp |
| Interface chứa quá nhiều field không dùng chung | Trừu tượng hóa sai ranh giới | Chia interface hoặc dùng union |
| Dùng tên Java class làm giả định về GraphQL type | Tên hai hệ thống không nhất thiết giống nhau | Ánh xạ rõ Java implementation sang GraphQL object type |

Khi thêm một implementation mới, cần cập nhật schema, runtime type resolution và kiểm thử query có fragment tương ứng. Nếu bỏ sót resolver, lỗi có thể chỉ xuất hiện khi client nhận đúng loại dữ liệu mới.

## 11. Khi nào nên dùng interface?

Interface phù hợp khi các điều kiện sau xuất hiện cùng nhau:

- Nhiều object type có một tập field chung ổn định và có ý nghĩa nghiệp vụ.
- Client cần truy vấn danh sách hoặc một kết quả có thể thuộc nhiều kiểu concrete.
- Giao diện cần hiển thị field chung trước, sau đó mở rộng theo từng loại.
- Các kiểu triển khai có thể tuân thủ cùng quy tắc về định danh, nullability và cách đọc dữ liệu.

Không nên tạo interface chỉ vì hai object tình cờ có cùng một field. Hãy cân nhắc ý nghĩa của hợp đồng: nếu `id` của hai kiểu có phạm vi hoặc cách sử dụng hoàn toàn khác nhau, việc gom chúng vào một interface có thể làm client hiểu sai.

## 12. Checklist trước khi công bố interface

- Interface chỉ chứa field thực sự chung cho các implementation?
- Mỗi object type đã triển khai đủ field và argument tương thích?
- Nullability của field output có giữ đúng cam kết của interface?
- Field trả về interface có thể resolve thành object type cụ thể?
- Query mẫu đã dùng fragment cho field riêng của từng kiểu?
- Client có cần `__typename` để phân nhánh hoặc cache không?
- Có kiểm thử cho mọi implementation và trường hợp kiểu không được hỗ trợ không?

`interface` giúp GraphQL schema biểu diễn một hợp đồng chung cho nhiều object type. Client truy vấn hợp đồng đó một cách ổn định, còn inline fragment cho phép lấy dữ liệu riêng theo từng kiểu. Trong Spring for GraphQL, phần quan trọng là trả về đúng đối tượng Java và cấu hình type resolution phù hợp để GraphQL biết concrete type cần dùng. Khi hợp đồng chung phản ánh đúng miền nghiệp vụ, interface giúp API đa hình rõ ràng và dễ mở rộng.
