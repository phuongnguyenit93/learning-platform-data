# JSONPath response

Khi kiểm thử GraphQL API, chỉ xác nhận request không ném exception là chưa đủ. Test cần kiểm tra dữ liệu server trả về: một field có đúng giá trị không, object lồng nhau có đúng cấu trúc không, danh sách có đủ phần tử không và field nào bị null khi resolver gặp lỗi.

Spring for GraphQL cung cấp **GraphQlTester** với API **path(...)** để đọc response bằng **JSONPath**. JSONPath cho phép chọn một giá trị, một property lồng nhau hoặc nhiều phần tử trong array. Sau khi chọn path, test có thể chuyển dữ liệu thành Java type để assert bằng **entity(...)**, **entityList(...)**, hoặc so sánh JSON trực tiếp.

Bài này tập trung vào cách dùng JSONPath với GraphQlTester: cú pháp path tương đối với data, truy cập nested object và list, wildcard và filter, alias, kiểm tra giá trị null hoặc path không tồn tại, chuyển đổi thành Java object, so sánh JSON, xử lý GraphQL errors và kiểm thử partial data.

## 1. JSONPath response là gì?

GraphQL response thường có cấu trúc JSON:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": "Spring for GraphQL",
      "author": {
        "name": "An Nguyen"
      }
    }
  }
}
~~~

Trong test, có thể cần đọc title của book, name của author, danh sách title của nhiều book, phần tử đầu tiên hoặc một phần tử thỏa điều kiện, và field có giá trị null hay không.

JSONPath là cú pháp biểu thức để truy cập các vị trí trong JSON. Với GraphQlTester, method **path(String)** nhận một JSONPath expression và trả về API cho phép kiểm tra giá trị tại vị trí đó.

Ví dụ:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-01") {
                id
                title
            }
        }
        """)
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

Path book.title chọn field title bên trong object book ở phần data của response.

## 2. Chuẩn bị GraphQlTester

Thêm dependency kiểm thử Spring for GraphQL:

~~~gradle
testImplementation("org.springframework.graphql:spring-graphql-test")
~~~

Khi dùng Spring Boot dependency management, nên để BOM của Spring Boot quản lý phiên bản tương thích thay vì tự chọn một phiên bản spring-graphql-test khác với spring-graphql.

**GraphQlTester** là abstraction chung cho việc gửi request và kiểm tra response. API request và JSONPath assertion giống nhau giữa các transport; cách tạo tester phụ thuộc vào nơi test được thực thi.

Các implementation thường dùng:

| Tester | Phạm vi |
|---|---|
| ExecutionGraphQlServiceTester | Gọi trực tiếp ExecutionGraphQlService, không cần HTTP |
| WebGraphQlTester | Gọi qua WebGraphQlHandler và WebGraphQlInterceptor chain |
| HttpGraphQlTester | Gửi request qua HTTP bằng WebTestClient |
| WebSocketGraphQlTester | Gửi request qua WebSocket |
| RSocketGraphQlTester | Gửi request qua RSocket |

Ví dụ tạo tester ở server-side, không đi qua transport:

~~~java
GraphQlTester graphQlTester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);
~~~

Ví dụ tạo tester qua HTTP tới server đang chạy:

~~~java
WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080/graphql")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);
~~~

Nếu cần kiểm tra HTTP headers, authentication, CORS hoặc interceptor, hãy dùng tester ở đúng tầng transport. Nếu chỉ cần kiểm tra GraphQL execution và dữ liệu trả về, ExecutionGraphQlServiceTester thường gọn hơn.

## 3. Path trong GraphQlTester tương đối với data

Đây là quy tắc quan trọng nhất khi viết JSONPath response:

**GraphQlTester.path(...) bắt đầu từ phần data của GraphQL response.**

Với response:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": "Spring for GraphQL"
    }
  }
}
~~~

Path đúng:

~~~java
.path("book.title")
~~~

Không cần thêm prefix data:

~~~java
// Không dùng data.book.title
// Không cần bắt đầu bằng $.data.book.title
~~~

Một path có thể là tên field root của operation, ví dụ book, hoặc một biểu thức JSONPath như books[*].title.

Điều này khác với việc tự parse toàn bộ JSON response bằng một thư viện JSONPath thông thường, nơi expression thường bắt đầu từ root JSON document.

## 4. Truy cập nested object

Giả sử schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  name: String!
  email: String
}
~~~

Client query:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    author {
      name
      email
    }
  }
}
~~~

Có thể kiểm tra từng nested field:

~~~java
graphQlTester.document(document)
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("book-01")
    .path("book.author.name")
    .entity(String.class)
    .isEqualTo("An Nguyen");
~~~

Khi cần kiểm tra nhiều field dưới cùng một object, dùng overload path có callback:

~~~java
graphQlTester.document(document)
    .execute()
    .path("book", book -> {
        book.path("id")
                .entity(String.class)
                .isEqualTo("book-01");

        book.path("title")
                .entity(String.class)
                .isEqualTo("Spring for GraphQL");

        book.path("author.name")
                .entity(String.class)
                .isEqualTo("An Nguyen");
    });
~~~

Trong callback, các path tiếp theo được tính tương đối với object book. Cách này giúp nhóm assertion theo một phần của response và tránh lặp lại prefix.

## 5. Truy cập phần tử trong array

Giả sử query trả về nhiều sách:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

Response minh họa:

~~~json
{
  "data": {
    "books": [
      {
        "id": "book-01",
        "title": "Spring for GraphQL",
        "author": {
          "name": "An Nguyen"
        }
      },
      {
        "id": "book-02",
        "title": "GraphQL in Practice",
        "author": {
          "name": "Binh Tran"
        }
      }
    ]
  }
}
~~~

JSONPath hỗ trợ truy cập theo index:

~~~java
.path("books[0].title")
.entity(String.class)
.isEqualTo("Spring for GraphQL");
~~~

Index bắt đầu từ 0. Có thể đọc phần tử tiếp theo bằng books[1].title.

Truy cập index phù hợp khi thứ tự là một phần của contract cần kiểm tra. Nếu API không cam kết thứ tự, nên kiểm tra tập giá trị hoặc điều kiện của từng phần tử thay vì phụ thuộc vào index.

## 6. Dùng wildcard để lấy nhiều giá trị

Wildcard **[*]** chọn tất cả phần tử trong array tại vị trí đó.

Ví dụ lấy title của mọi sách:

~~~java
graphQlTester.document("""
        query {
            books {
                title
            }
        }
        """)
    .execute()
    .path("books[*].title")
    .entityList(String.class)
    .contains(
            "Spring for GraphQL",
            "GraphQL in Practice");
~~~

Path books[*].title trả về một tập hợp giá trị title từ các phần tử trong books.

Có thể kiểm tra số phần tử:

~~~java
.path("books[*].title")
.entityList(String.class)
.hasSize(2);
~~~

Hoặc kiểm tra đúng thứ tự và đúng toàn bộ nội dung:

~~~java
.path("books[*].title")
.entityList(String.class)
.containsExactly(
        "Spring for GraphQL",
        "GraphQL in Practice");
~~~

Một số assertion phổ biến của EntityList:

| Method | Ý nghĩa |
|---|---|
| hasSize(n) | Danh sách có đúng n phần tử |
| hasSizeGreaterThan(n) | Có nhiều hơn n phần tử |
| hasSizeLessThan(n) | Có ít hơn n phần tử |
| contains(...) | Có chứa các giá trị, không yêu cầu đúng thứ tự |
| containsExactly(...) | Có đúng các giá trị theo đúng thứ tự |
| doesNotContain(...) | Không chứa các giá trị được chỉ định |
| singleElement() | Xác nhận list có đúng một phần tử và trả assertion cho phần tử đó |

## 7. Dùng filter expression trong JSONPath

JSONPath hỗ trợ filter để chọn các phần tử thỏa điều kiện.

Ví dụ, query trả về các sách có pageCount và title:

~~~graphql
query {
  books {
    id
    title
    pageCount
  }
}
~~~

Có thể chọn sách có hơn 300 trang:

~~~java
graphQlTester.document(document)
    .execute()
    .path("books[?(@.pageCount > 300)].title")
    .entityList(String.class)
    .contains("GraphQL in Practice");
~~~

Trong filter:

- Dấu ? bắt đầu biểu thức điều kiện.
- @ đại diện cho phần tử hiện tại.
- pageCount là property của phần tử.
- > 300 là điều kiện lọc.

Ví dụ kiểm tra các sách đã xuất bản:

~~~java
.path("books[?(@.published == true)].id")
.entityList(String.class)
.hasSizeGreaterThan(0);
~~~

Filter chỉ có thể sử dụng field thực sự xuất hiện trong GraphQL response. Nếu document không chọn pageCount hoặc published, JSONPath không thể lọc theo những field đó.

Không nên dùng filter expression quá phức tạp cho mọi assertion. Khi logic lọc khó đọc, có thể decode list thành Java object rồi dùng assertion bằng AssertJ.

## 8. JSONPath với alias trong GraphQL

GraphQL cho phép client đặt alias cho field:

~~~graphql
query {
  featuredBook: book(id: "book-01") {
    id
    title
  }
}
~~~

Response sử dụng alias làm key:

~~~json
{
  "data": {
    "featuredBook": {
      "id": "book-01",
      "title": "Spring for GraphQL"
    }
  }
}
~~~

Vì JSONPath đọc response thực tế, test phải dùng alias:

~~~java
.path("featuredBook.title")
.entity(String.class)
.isEqualTo("Spring for GraphQL");
~~~

Không dùng tên schema field book trong path nếu response key đã được thay bằng featuredBook.

## 9. Chuyển đổi một path thành Java object

Khi object có nhiều field hoặc có cấu trúc lồng nhau, có thể chuyển path thành một Java type.

DTO:

~~~java
public record BookView(
        String id,
        String title,
        AuthorView author) {
}

public record AuthorView(
        String name,
        String email) {
}
~~~

Test:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-01") {
                id
                title
                author {
                    name
                    email
                }
            }
        }
        """)
    .execute()
    .path("book")
    .entity(BookView.class)
    .satisfies(book -> {
        assertThat(book.id()).isEqualTo("book-01");
        assertThat(book.title()).isEqualTo("Spring for GraphQL");
        assertThat(book.author().name()).isEqualTo("An Nguyen");
    });
~~~

Các cách assertion trên Entity:

- isEqualTo(expected): so sánh object với giá trị mong đợi.
- isNotEqualTo(other): xác nhận object khác giá trị chỉ định.
- matches(predicate): kiểm tra object bằng predicate.
- satisfies(consumer): chạy nhiều assertion trên object.
- get(): lấy object đã decode để dùng trong assertion khác.

Chuyển thành DTO phù hợp khi test cần kiểm tra nhiều thuộc tính cùng lúc. Nếu chỉ cần một scalar, dùng entity(String.class), entity(Integer.class) hoặc type phù hợp sẽ đơn giản hơn.

## 10. Kiểm tra kiểu dữ liệu generic

Nếu response path là object có generic type, dùng **ParameterizedTypeReference** để giữ thông tin kiểu khi decode.

Ví dụ:

~~~java
ParameterizedTypeReference<Map<String, Object>> mapType =
        new ParameterizedTypeReference<>() {};

graphQlTester.document(document)
    .execute()
    .path("book.metadata")
    .entity(mapType)
    .satisfies(metadata ->
            assertThat(metadata).containsKey("language"));
~~~

Với list các generic type, GraphQlTester cũng cung cấp overload entityList(ParameterizedTypeReference). Chọn kiểu Java rõ ràng giúp tránh cast thủ công và lỗi ClassCastException.

## 11. So sánh JSON tại một path

Khi cần kiểm tra cấu trúc JSON của một object, có thể dùng **matchesJson(...)**:

~~~java
graphQlTester.document(document)
    .execute()
    .path("book")
    .matchesJson("""
            {
              "id": "book-01",
              "title": "Spring for GraphQL"
            }
            """);
~~~

Phương thức này so sánh JSON tại path với JSON mong đợi. Việc so sánh không phụ thuộc cách xuống dòng hoặc khoảng trắng trong JSON.

Để dùng matchesJson, cần có thư viện JSONassert trên test classpath. Hãy kiểm tra dependency test của dự án nếu gặp lỗi thiếu JSONassert.

So sánh JSON hữu ích khi muốn kiểm tra một phần cấu trúc response. Nếu chỉ cần kiểm tra vài field, dùng path(...).entity(...) thường làm test dễ đọc hơn và ít phụ thuộc vào toàn bộ shape của object.

## 12. Phân biệt null và path không tồn tại

GraphQL response có thể có một field được chọn nhưng giá trị là null:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "author": null
    }
  }
}
~~~

Test:

~~~java
.path("book.author")
.valueIsNull();
~~~

Trong khi đó, nếu query không chọn field author, response có thể không có key author:

~~~json
{
  "data": {
    "book": {
      "id": "book-01"
    }
  }
}
~~~

Test:

~~~java
.path("book.author")
.pathDoesNotExist();
~~~

Hai trường hợp có ý nghĩa khác nhau:

| Assertion | Ý nghĩa |
|---|---|
| valueIsNull() | Path tồn tại nhưng giá trị là null |
| pathDoesNotExist() | Không có path/key tương ứng trong response |
| hasValue() | Path có giá trị khác null; với list, list phải không rỗng |

Không dùng pathDoesNotExist để kiểm tra resolver trả null. Nếu field được chọn và resolver trả null, hãy dùng valueIsNull.

## 13. Kiểm tra response có partial data và GraphQL errors

GraphQL cho phép response chứa cả data và errors. Ví dụ field author có lỗi nhưng title vẫn được resolve:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải tác giả",
      "path": ["book", "author"]
    }
  ]
}
~~~

Khi response có errors, GraphQlTester yêu cầu test phải kiểm tra hoặc lọc errors trước khi đi tới data path. Nếu không, việc gọi path(...) có thể thất bại để nhắc test rằng lỗi chưa được xử lý.

Ví dụ kiểm tra lỗi mong đợi và partial data:

~~~java
graphQlTester.document(document)
    .execute()
    .errors()
    .expect(error ->
            error.getMessage().contains("Không thể tải tác giả"))
    .verify()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

Sau khi xác nhận error mong đợi, test vẫn có thể kiểm tra các field còn lại trong data.

### filter và expect khác nhau

**filter(...)** đánh dấu một loại lỗi là có thể bỏ qua. Filter không yêu cầu lỗi đó phải xuất hiện.

~~~java
.errors()
.filter(error -> error.getMessage().contains("expected warning"))
.verify()
~~~

**expect(...)** khai báo lỗi cần có. Nếu không có lỗi nào khớp predicate, assertion thất bại.

~~~java
.errors()
.expect(error -> error.getMessage().contains("Không thể tải tác giả"))
.verify()
~~~

Chỉ lọc các lỗi đã được dự kiến rõ ràng. Nếu filter tất cả errors, test có thể che giấu lỗi mới phát sinh.

### Dùng satisfy để kiểm tra toàn bộ errors

Có thể kiểm tra danh sách errors trực tiếp:

~~~java
.errors()
.satisfy(errors ->
        assertThat(errors)
                .anyMatch(error ->
                        error.getMessage().contains("Không thể tải tác giả")));
~~~

Lưu ý: satisfy đánh dấu các errors đã được kiểm tra và cho phép tiếp tục đọc data. Vì vậy, trong callback nên kiểm tra đầy đủ các lỗi mà test quan tâm.

## 14. Kiểm tra mutation không có response data

Một số mutation trả về scalar hoặc payload không cần kiểm tra bằng JSONPath phức tạp. Nếu mục tiêu chỉ là xác nhận request không có GraphQL errors, dùng **executeAndVerify()**:

~~~java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-01")
        }
        """)
    .executeAndVerify();
~~~

executeAndVerify thực thi request và xác nhận response không có errors. Nếu cần kiểm tra giá trị trả về, hãy dùng execute() rồi đi tới path tương ứng.

Ví dụ:

~~~java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-01")
        }
        """)
    .execute()
    .path("archiveBook")
    .entity(Boolean.class)
    .isEqualTo(true);
~~~

## 15. JSONPath không thay thế GraphQL selection set

JSONPath chỉ có thể đọc những gì đã xuất hiện trong response.

Ví dụ GraphQL document:

~~~graphql
query {
  books {
    id
    title
  }
}
~~~

Test có thể đọc books[*].title, nhưng không thể đọc books[*].author.name nếu query không chọn author và name.

Khi path không tồn tại, hãy kiểm tra theo thứ tự:

1. GraphQL document đã chọn field cần đọc chưa?
2. Có alias làm thay đổi key trong response không?
3. Field có nằm trong object cha đúng như schema không?
4. Resolver trả null hay response thực sự không có key?
5. Có GraphQL errors hoặc null propagation làm parent object thành null không?

JSONPath không truy cập schema trực tiếp và không tự thực thi field. Nó chỉ truy vấn JSON response đã nhận.

## 16. Chọn assertion phù hợp

Không phải test nào cũng cần một JSONPath expression phức tạp. Hãy chọn cách assertion theo mục tiêu:

| Mục tiêu | Cách dùng |
|---|---|
| Kiểm tra một scalar | path(...).entity(Type.class) |
| Kiểm tra object | path(...).entity(Dto.class) |
| Kiểm tra list | path(...).entityList(Type.class) |
| Kiểm tra một nested field | path(parent.child) |
| Kiểm tra nhiều field cùng object | path(parent, callback) |
| Kiểm tra mọi phần tử list | path(items[*].field) |
| Lọc phần tử theo điều kiện | JSONPath filter expression |
| Kiểm tra null | valueIsNull() |
| Kiểm tra key không có | pathDoesNotExist() |
| Kiểm tra JSON shape | matchesJson(...) |
| Kiểm tra partial data có lỗi dự kiến | errors().expect(...).verify() rồi path(...) |

Ưu tiên assertion thể hiện rõ contract của API. Nếu thứ tự list không được bảo đảm, dùng contains hoặc kiểm tra bằng predicate thay vì containsExactly.

## 17. Những lỗi thường gặp khi dùng JSONPath response

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Path không tìm thấy field | Thêm sai prefix data hoặc sai tên field | Nhớ path bắt đầu từ data |
| Path dùng tên schema nhưng response không có | GraphQL field có alias | Dùng alias làm key trong JSONPath |
| Không đọc được nested field | Query chưa chọn nested field | Bổ sung field vào selection set |
| path(...) thất bại dù data có giá trị | Response chứa errors chưa được kiểm tra | Dùng errors().verify(), expect hoặc satisfy trước |
| valueIsNull thất bại | Path không tồn tại thay vì null | Dùng pathDoesNotExist khi key bị thiếu |
| entityList không decode được | Path không trả array hoặc type không khớp | Kiểm tra JSON shape và Java type |
| Filter trả list rỗng | Field dùng trong filter chưa được chọn hoặc predicate sai | Kiểm tra selection set và biểu thức |
| Test phụ thuộc thứ tự không ổn định | Resolver/repository không cam kết ordering | Assert tập giá trị hoặc sắp xếp có chủ đích |
| matchesJson báo thiếu thư viện | JSONassert không có trên test classpath | Thêm dependency JSONassert phù hợp |
| Test bỏ qua lỗi ngoài dự kiến | Error filter quá rộng | Chỉ filter lỗi cụ thể đã được chấp nhận |
| Test mutation không cần data bị rườm rà | Dùng execute rồi không assert path | Dùng executeAndVerify nếu chỉ cần xác nhận không có lỗi |

## 18. Quy trình viết JSONPath response assertion

Khi kiểm thử GraphQL response:

1. Xác định field và cấu trúc JSON mà GraphQL operation trả về.
2. Viết document có selection set chứa đúng field cần kiểm tra.
3. Gửi request bằng GraphQlTester và gọi execute().
4. Xác nhận hoặc xử lý errors trước khi đi tới data path.
5. Viết JSONPath tương đối với data, không thêm prefix data.
6. Dùng index khi thứ tự là contract; dùng wildcard hoặc filter khi cần chọn nhiều phần tử.
7. Chuyển path thành scalar, DTO hoặc list bằng entity/entityList.
8. Kiểm tra null và path không tồn tại bằng assertion tương ứng.
9. Kiểm tra partial data khi operation có lỗi dự kiến.
10. Dùng matchesJson khi cần so sánh cấu trúc JSON và đã có JSONassert.
11. Giữ assertion tập trung vào contract API, tránh phụ thuộc chi tiết không ổn định.
12. Chạy test ở đúng tầng: execution, WebGraphQlHandler hoặc HTTP transport tùy điều cần xác minh.

JSONPath response giúp kiểm tra chính xác dữ liệu GraphQL trả về bằng các biểu thức ngắn gọn. Với GraphQlTester, mọi path đều bắt đầu từ phần data; nested object, array, wildcard, filter và alias đều có thể được kiểm tra qua path(...). Sau khi chọn path, dùng entity hoặc entityList để decode thành Java type, hoặc matchesJson để so sánh JSON. Khi response có errors, hãy xác nhận chúng trước khi đọc data; đồng thời phân biệt field null với path không tồn tại. Các quy tắc này giúp test thể hiện đúng contract của GraphQL API và phát hiện lỗi ở cả dữ liệu lẫn cấu trúc response.

## Tài liệu tham khảo

- Spring for GraphQL — Testing: https://docs.spring.io/spring-graphql/reference/testing.html
- GraphQlTester API — Traversable và Path: https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Traversable.html
- Jayway JsonPath: https://github.com/json-path/JsonPath
- JSONassert: https://jsonassert.skyscreamer.org/

