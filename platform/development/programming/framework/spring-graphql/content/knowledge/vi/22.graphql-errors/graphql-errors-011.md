# Path của field bị lỗi trong GraphQL response

Trong GraphQL, một operation có thể phân giải nhiều field lồng nhau và trả về dữ liệu ở nhiều cấp. Khi một field gặp lỗi trong lúc thực thi, phần tử tương ứng trong mảng `errors` thường có thuộc tính `path` để chỉ ra chính xác vị trí field đó trong response. Client dùng path để liên kết lỗi với đúng phần dữ liệu bị ảnh hưởng, kể cả khi query có alias, list hoặc fragment.

`path` là đường dẫn trong kết quả GraphQL, không phải đường dẫn đến field trong schema và cũng không phải vị trí dòng/cột trong query. Nó mô tả response key và chỉ số phần tử list theo đúng cấu trúc dữ liệu được trả về. Hiểu đúng sự khác nhau giữa `path` và `locations` giúp server tạo lỗi có ngữ cảnh, còn client có thể hiển thị lỗi đúng field mà không phải phân tích nội dung message.

Sau bài này, bạn có thể:

- Đọc `path` trong một GraphQL error.
- Hiểu các segment dạng tên field và chỉ số list.
- Xác định tác động của alias lên path.
- Hiểu path khi field nằm trong nested object, list hoặc fragment.
- Phân biệt `path` với `locations` và `extensions`.
- Hiểu vì sao path vẫn chỉ field gốc khi null propagation làm lỗi lan lên parent.
- Tạo GraphQL error có path phù hợp trong Spring for GraphQL.
- Kiểm thử và dùng path ở client để xác định đúng phần response bị lỗi.

## 1. Path là gì?

`path` là một mảng các segment mô tả đường đi từ root response đến field phát sinh execution error. Segment có thể là:

- Chuỗi: response key của một field.
- Số nguyên: chỉ số của một phần tử trong list, bắt đầu từ `0`.

Ví dụ query:

```graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
```

Nếu resolver của `author` lỗi, GraphQL error có thể chứa:

```json
{
  "message": "Author could not be loaded",
  "path": ["book", "author"]
}
```

Nếu `author` đã được tải nhưng resolver của `name` lỗi, path có thể là:

```json
["book", "author", "name"]
```

Path bắt đầu từ field ở root operation và tiếp tục qua từng cấp object cho đến field gây lỗi. Nó giúp client xác định đúng vị trí mà lỗi phát sinh trong cây response.

## 2. Path dùng response key, không nhất thiết là tên field trong schema

GraphQL cho phép alias để đổi tên field trong response. Khi dùng alias, path chứa alias vì đó là key xuất hiện trong response.

Ví dụ:

```graphql
query {
    featuredBook: book(id: "book-42") {
        title
        writer: author {
            name
        }
    }
}
```

Nếu field `author` lỗi, path là:

```json
["featuredBook", "writer"]
```

Nếu field `name` lỗi, path là:

```json
["featuredBook", "writer", "name"]
```

Trong schema, field thực tế vẫn là `Query.book` và `Book.author`. Nhưng response key mà client chọn lần lượt là `featuredBook` và `writer`. Vì vậy, client phải dùng path để tra cứu response object, không thể thay mọi segment bằng tên field schema.

Điều này đặc biệt quan trọng khi cùng một field được truy vấn nhiều lần với argument khác nhau:

```graphql
query {
    newest: books(sort: NEWEST) {
        id
    }
    popular: books(sort: POPULAR) {
        id
    }
}
```

Nếu một phần tử trong `popular` gặp lỗi, path bắt đầu bằng `popular`, không phải `books`. Alias cho phép client phân biệt hai nhánh cùng gọi một field schema.

## 3. Path chứa chỉ số list

Khi một field nằm bên trong list, path chứa chỉ số của phần tử nơi lỗi phát sinh. Chỉ số bắt đầu từ `0`.

Query:

```graphql
query {
    books {
        id
        author {
            name
        }
    }
}
```

Nếu `author` của phần tử thứ ba lỗi, path có dạng:

```json
["books", 2, "author"]
```

Giải thích từng segment:

| Segment | Ý nghĩa |
| --- | --- |
| `"books"` | Root response field `books` |
| `2` | Phần tử thứ ba trong list `books` |
| `"author"` | Field `author` của phần tử đó |

Nếu resolver của `Author.name` lỗi, path có thêm segment cuối:

```json
["books", 2, "author", "name"]
```

Nếu list lồng nhau, path có thể chứa nhiều chỉ số:

```graphql
query {
    departments {
        teams {
            members {
                displayName
            }
        }
    }
}
```

Ví dụ lỗi ở `displayName` của member đầu tiên, thuộc team thứ hai, trong department thứ ba:

```json
["departments", 2, "teams", 1, "members", 0, "displayName"]
```

Client cần giữ nguyên kiểu dữ liệu của từng segment. Không chuyển tất cả segment thành string vì số nguyên biểu diễn chỉ số list, không phải tên property.

## 4. Path trong nested object

Với nhiều cấp object, mỗi field response key tạo thêm một segment. Ví dụ:

```graphql
query {
    order(id: "order-9") {
        customer {
            address {
                city
            }
        }
    }
}
```

Nếu resolver của `city` lỗi, path là:

```json
["order", "customer", "address", "city"]
```

Nếu resolver của `address` lỗi trước khi GraphQL có thể phân giải `city`, path dừng ở:

```json
["order", "customer", "address"]
```

Path chỉ đến field thực sự phát sinh lỗi. Nó không liệt kê các field con mà GraphQL chưa thể phân giải sau khi parent lỗi.

## 5. Path trong fragment

Fragment giúp tái sử dụng selection set hoặc truy vấn field theo concrete type, nhưng tên fragment không trở thành segment trong path. Path vẫn phản ánh cây response.

Ví dụ:

```graphql
fragment AuthorFields on Author {
    id
    name
}

query {
    searchResults {
        ... on Book {
            title
        }
        ...AuthorFields
    }
}
```

Nếu `name` lỗi trên phần tử thứ hai của `searchResults`, path có thể là:

```json
["searchResults", 1, "name"]
```

Path không chứa `AuthorFields` hoặc `... on Author`, vì fragment là cách tổ chức document chứ không phải object key trong response. Tương tự, inline fragment không thêm một segment vào path.

## 6. Phân biệt path và locations

`path` và `locations` đều giúp xác định lỗi, nhưng mô tả hai không gian khác nhau:

| Thuộc tính | Mô tả | Ví dụ |
| --- | --- | --- |
| `path` | Vị trí field trong response tree | `["books", 2, "author"]` |
| `locations` | Vị trí node liên quan trong GraphQL document | `[{"line": 5, "column": 9}]` |

Query có thể được viết trên nhiều dòng hoặc sử dụng fragment. `locations` giúp công cụ tìm vị trí cú pháp trong document; `path` giúp client tìm đúng vị trí dữ liệu sau khi thực thi.

Một lỗi parse hoặc validation xảy ra trước execution có thể có `locations` nhưng không có `path`, vì chưa có field response nào được phân giải. Ngược lại, execution error thường có path vì GraphQL biết field nào đang được xử lý.

Không dùng line/column để tra cứu JSON response. Cũng không dùng path để xác định dòng query cần highlight nếu client có sẵn `locations`; hai thuộc tính bổ sung cho nhau.

## 7. Phân biệt path và extensions

`extensions` chứa metadata do implementation hoặc ứng dụng cung cấp, ví dụ error code, correlation ID hoặc classification. `path` có cấu trúc chuẩn để xác định vị trí response field; `extensions` không thay thế path.

Ví dụ:

```json
{
  "message": "Author service is unavailable",
  "path": ["featuredBook", "writer"],
  "extensions": {
    "code": "UPSTREAM_UNAVAILABLE",
    "retryable": true
  }
}
```

Client có thể dùng `path` để đánh dấu field `writer` trong response và dùng `extensions.code` để chọn hành động tương ứng. Không nên nhét path tùy chỉnh vào `extensions` khi GraphQL đã có thuộc tính chuẩn `path`.

Không đưa thông tin nhạy cảm như token, stack trace hoặc SQL vào extensions. Error code cần ổn định, còn message có thể thay đổi hoặc được dịch.

## 8. Path chỉ field gốc, kể cả khi null propagation lan lên parent

Một điểm quan trọng: `path` chỉ vị trí field ban đầu gây lỗi. Nó không thay đổi để trỏ đến parent bị null do non-null propagation.

Giả sử schema:

```graphql
type Query {
    book(id: ID!): Book!
}

type Book {
    id: ID!
    author: Author!
}

type Author {
    name: String!
}
```

Query:

```graphql
query {
    book(id: "book-42") {
        author {
            name
        }
    }
}
```

Nếu resolver của `name` lỗi, path vẫn là:

```json
["book", "author", "name"]
```

Do `name`, `author` và `book` đều non-null, lỗi có thể lan lên tận root và response có `data: null`. Tuy nhiên path không trở thành `[]`, `null` hay chỉ `book`; nó vẫn chỉ field `name` nơi lỗi được phát hiện.

Nếu `author` được khai báo nullable (`author: Author`), lỗi ở `name` có thể làm `author` trở thành null nhưng vẫn giữ `book.id` và các field khác. Path vẫn là `["book", "author", "name"]`.

Client vì vậy không nên chỉ dựa vào vị trí null cuối cùng trong `data` để suy ra field gốc. Hãy dùng `errors[].path` để xác định nơi execution error phát sinh.

## 9. Request error thường không có path

Path có ý nghĩa khi GraphQL đã bắt đầu thực thi và biết field nào gặp lỗi. Các lỗi trước execution như parse, validation hoặc variable coercion thường không có path.

Ví dụ query gọi field không tồn tại:

```graphql
query {
    book(id: "book-42") {
        titel
    }
}
```

GraphQL có thể trả:

```json
{
  "errors": [
    {
      "message": "Cannot query field 'titel' on type 'Book'. Did you mean 'title'?",
      "locations": [
        { "line": 4, "column": 9 }
      ]
    }
  ]
}
```

Không có path vì field `titel` không phải field hợp lệ trong schema và resolver chưa được thực thi. Client cần xử lý lỗi document/schema thay vì cố tìm một node trong `data`.

Do đó, khi đọc GraphQL errors, hãy xem `path` là optional. Không giả định mọi error object đều có path.

## 10. Tạo error có path đúng trong Spring for GraphQL

Khi exception phát sinh trong resolver, GraphQL execution đã có `DataFetchingEnvironment`, trong đó chứa thông tin field hiện tại. Khi tự tạo `GraphQLError`, hãy dùng builder nhận environment để gắn vị trí và path của field đang thực thi.

Ví dụ với `@GraphQlExceptionHandler`:

```java
@ControllerAdvice
public class GraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleAuthorUnavailable(
            AuthorServiceUnavailableException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("Author service is temporarily unavailable")
                .extensions(Map.of("code", "AUTHOR_SERVICE_UNAVAILABLE"))
                .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` lấy execution location và path từ field đang được xử lý. GraphQL có thể đưa error vào response cùng dữ liệu của các field khác, đồng thời áp dụng null propagation theo SDL.

Nếu tạo error bằng builder không có environment, chẳng hạn `GraphqlErrorBuilder.newError()`, bạn phải tự cung cấp thông tin cần thiết nếu muốn error có path/location. Với exception phát sinh từ DataFetcher, ưu tiên builder nhận `DataFetchingEnvironment` để tránh tự dựng path sai.

Không tự tạo path bằng cách nối tên field trong controller. Khi có alias, list index hoặc nested resolver, tên schema không đủ để tái tạo response path chính xác.

## 11. Path với DataFetcherExceptionResolver

Nếu ứng dụng dùng `DataFetcherExceptionResolver` để ánh xạ exception tập trung, resolver cũng nhận `DataFetchingEnvironment` và có thể tạo lỗi gắn với field hiện tại.

Ví dụ khung xử lý:

```java
@Component
public class AuthorExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof AuthorServiceUnavailableException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.INTERNAL_ERROR)
                    .message("Author service is temporarily unavailable")
                    .extensions(Map.of("code", "AUTHOR_SERVICE_UNAVAILABLE"))
                    .build();
        }

        return null;
    }
}
```

Đây là một cách triển khai tập trung cho các lỗi từ DataFetcher. Với exception không thuộc phạm vi xử lý, resolver trả `null` để cơ chế resolver tiếp theo có thể xử lý theo hợp đồng của `DataFetcherExceptionResolverAdapter` và phiên bản Spring for GraphQL đang dùng.

Không cần vừa tạo `@GraphQlExceptionHandler` vừa tạo `DataFetcherExceptionResolver` xử lý cùng một exception. Hãy chọn một nơi chịu trách nhiệm để message, code và logging nhất quán.

## 12. Path với alias và nested resolver trong thực tế

Xét query:

```graphql
query Catalog {
    primary: books {
        id
        mainAuthor: author {
            name
        }
    }
    secondary: books {
        id
        mainAuthor: author {
            name
        }
    }
}
```

Nếu tác giả của cuốn sách thứ hai trong nhánh `secondary` lỗi ở resolver `author`, path có thể là:

```json
["secondary", 1, "mainAuthor"]
```

Nếu `Author.name` lỗi, path có thêm `name`:

```json
["secondary", 1, "mainAuthor", "name"]
```

Path phân biệt được nhánh `primary` và `secondary` dù hai nhánh cùng gọi schema field `books`. Nó cũng chỉ ra chính xác phần tử thứ hai và alias của field quan hệ.

Điều này cho thấy server không cần biết client sẽ đặt alias nào khi viết resolver. GraphQL engine tạo path từ execution hiện tại và trả nó trong error.

## 13. Client sử dụng path để xác định field lỗi

Client có thể duyệt `path` để tìm vị trí tương ứng trong response data. Ý tưởng tổng quát:

1. Đọc `error.path` và kiểm tra nó có phải array hay không.
2. Bắt đầu từ `data`.
3. Với segment string, truy cập property theo response key.
4. Với segment number, truy cập phần tử list tại chỉ số đó.
5. Đánh dấu field/nhánh bị lỗi hoặc hiển thị thông báo gần vị trí tương ứng.

Ví dụ TypeScript minh họa cách duyệt path:

```typescript
type PathSegment = string | number;

function valueAtPath(data: unknown, path: PathSegment[]): unknown {
  return path.reduce<unknown>((current, segment) => {
    if (current == null) return undefined;

    if (typeof segment === "number" && Array.isArray(current)) {
      return current[segment];
    }

    if (typeof segment === "string" && typeof current === "object") {
      return (current as Record<string, unknown>)[segment];
    }

    return undefined;
  }, data);
}
```

Đây là ví dụ định hướng; client thực tế cần xử lý trường hợp path thiếu, data null, segment không hợp lệ và cấu trúc response đã được normalize vào cache.

Không nên dùng path làm ID lâu dài cho entity. Path chỉ có ý nghĩa trong response của operation hiện tại; list có thể đổi thứ tự giữa các lần gọi và alias có thể khác nhau giữa các query.

## 14. Path và normalized client cache

Một số GraphQL client lưu object vào normalized cache theo ID, thay vì giữ nguyên cây response. Trong trường hợp đó, path vẫn mô tả vị trí trong response gốc của operation, nhưng không nhất thiết tương ứng trực tiếp với key nội bộ trong normalized cache.

Ví dụ path:

```json
["books", 2, "author", "name"]
```

có thể trỏ đến `books[2].author.name` trong response thô. Sau normalization, client có thể lưu `Book:book-42` và `Author:author-9` thành các record riêng. Client cần dùng metadata của operation và mapping từ response về cache để đánh dấu chính xác lỗi.

Không giả định mọi thư viện client xử lý `errors[].path` giống nhau. Hãy kiểm tra cách thư viện cụ thể expose GraphQL errors và partial data, nhất là khi dùng optimistic update hoặc cache normalization.

## 15. Kiểm thử path bằng GraphQlTester

`GraphQlTester` cho phép thực thi document và kiểm tra GraphQL errors. Khi cần xác nhận path, có thể đọc `GraphQLError.getPath()` trong assertion:

```java
graphQlTester.document("""
        query {
            featured: books {
                id
                writer: author {
                    name
                }
            }
        }
        """)
    .execute()
    .errors()
    .satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getPath())
                .containsExactly("featured", 0, "writer");
    });
```

Nếu exception xảy ra tại `Author.name`, assertion path cần thêm `"name"`. Path được kiểm tra phải tương ứng với field thực sự ném lỗi trong fixture của test.

Các test quan trọng:

1. Lỗi ở root field có path chỉ gồm response key root.
2. Lỗi ở nested field có đầy đủ segment cha và field con.
3. Alias được dùng trong path thay cho tên field schema.
4. List index bắt đầu từ 0 và trỏ đúng phần tử.
5. Nested list có nhiều segment số nguyên.
6. Inline fragment không xuất hiện như segment trong path.
7. Request parse/validation error có thể không có path.
8. Null propagation không thay đổi path của field gốc.
9. Error handler dùng `DataFetchingEnvironment` tạo path/location đúng.
10. Client xử lý trường hợp path không tồn tại.

Nên tạo fixture có nhiều phần tử với một phần tử cố ý lỗi để xác nhận path có index chính xác, thay vì chỉ test list một phần tử luôn có index 0.

## 16. Những lỗi thường gặp

- **Coi path là tên field trong schema:** path dùng response key, nên alias làm thay đổi segment.
- **Chuyển mọi segment thành string:** list index là số nguyên và phải được giữ đúng kiểu.
- **Đếm index từ 1:** GraphQL path dùng index list bắt đầu từ 0.
- **Dùng locations thay cho path:** locations là line/column trong document, không phải vị trí trong response.
- **Cho rằng fragment xuất hiện trong path:** fragment không phải response key.
- **Cho rằng path trỏ đến parent bị null:** path giữ field ban đầu phát sinh lỗi dù null propagation lan lên ancestor.
- **Giả định request error luôn có path:** lỗi parse/validation/coercion thường xảy ra trước execution.
- **Tự nối path bằng tên schema trong exception handler:** dễ sai khi có alias hoặc list index; dùng `DataFetchingEnvironment`.
- **Tạo GraphQLError không có execution environment:** error có thể thiếu path/location nếu không tự cung cấp.
- **Dùng path như ID lâu dài:** path chỉ có ý nghĩa trong một response cụ thể.
- **Bỏ qua partial data:** field khác có thể vẫn thành công dù một path bị lỗi.

## 17. Quy trình đọc và xử lý path

Khi GraphQL response có errors, hãy thực hiện:

1. Kiểm tra `errors` có tồn tại và mỗi error có `path` hay không.
2. Nếu có path, đọc từng segment theo đúng kiểu string hoặc integer.
3. Dùng response key để xử lý alias; không thay bằng field name trong schema.
4. Dùng integer segment để xác định phần tử list, bắt đầu từ index 0.
5. Dùng `locations` riêng để trỏ tới dòng/cột trong document nếu cần.
6. Dùng `extensions.code` để phân loại lỗi, không phân tích message.
7. Kiểm tra `data` để biết partial result còn dùng được hay đã thành null do propagation.
8. Ở server, dùng `DataFetchingEnvironment` khi tạo GraphQLError từ exception resolver.
9. Kiểm thử alias, nested object, list, fragment và non-null propagation.
10. Không lưu path như định danh ổn định của resource hoặc field qua nhiều operation.

`path` giúp GraphQL client biết lỗi xảy ra ở đâu trong response tree. Các segment string phản ánh response key, bao gồm alias; các segment số nguyên xác định vị trí phần tử list. `path` khác với `locations` trong query document và vẫn trỏ tới field gốc khi null propagation làm dữ liệu lan null lên parent. Trong Spring for GraphQL, dùng `DataFetchingEnvironment` khi tạo lỗi giúp gắn path và location đúng với execution hiện tại. Khi client đọc path như một mảng có kiểu và kết hợp nó với partial data cùng error code, lỗi field-level có thể được xử lý chính xác và nhất quán.

## Tài liệu tham khảo

- [GraphQL Specification — Errors](https://spec.graphql.org/October2021/#sec-Errors)
- [GraphQL Specification — Response Format](https://spec.graphql.org/October2021/#sec-Response-Format)
- [GraphQL Java — GraphqlErrorBuilder API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/GraphqlErrorBuilder.html)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handling)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
