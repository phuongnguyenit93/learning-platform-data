# DataLoader key và value

GraphQL thường trả về các object có quan hệ với nhau. Ví dụ, một query lấy 50 quyển sách và client chọn thêm field author của từng quyển. Nếu resolver của mỗi Book tự truy vấn tác giả theo authorId, server có thể thực hiện một query lấy sách và 50 query lấy tác giả. Đây là vấn đề N+1.

DataLoader gom các yêu cầu tải dữ liệu theo key thành một batch. Trong ví dụ này, **key** là authorId, còn **value** là object Author tương ứng. Mỗi resolver gọi load(authorId); DataLoader thu thập các key trong cùng nhịp thực thi rồi gọi batch loader để tải nhiều tác giả một lần. Kết quả được trả lại cho đúng resolver đã yêu cầu.

Trong Spring for GraphQL, DataLoader được tích hợp với GraphQL Java thông qua BatchLoaderRegistry, DataLoaderRegistry và các cơ chế như @BatchMapping. Hiểu rõ quan hệ key/value là điều kiện quan trọng để batch loader trả dữ liệu đúng đối tượng, đúng thứ tự và không làm sai kết quả khi thiếu dữ liệu hoặc có key trùng.

## DataLoader<K, V> biểu diễn điều gì?

DataLoader có hai tham số kiểu:

- **K (key):** giá trị dùng để xác định dữ liệu cần tải, ví dụ authorId, productId hoặc userId.
- **V (value):** dữ liệu được trả về cho key đó, ví dụ Author, Product hoặc User.

Với khai báo DataLoader<String, Author>, mỗi lần gọi load nhận một String key và trả về một kết quả Author bất đồng bộ:

~~~java
DataLoader<String, Author> authorLoader;

CompletableFuture<Author> authorFuture =
        authorLoader.load("author-12");
~~~

Key không bắt buộc phải là ID của value, nhưng phải có quy tắc ánh xạ ổn định từ key sang value. Key thường là khóa chính hoặc khóa ngoại dùng để truy vấn. Với quan hệ một-nhiều, value có thể là List<Review>:

~~~java
DataLoader<String, List<Review>> reviewsLoader;
~~~

Ở đây key là bookId, value là danh sách Review thuộc Book đó. Việc chọn kiểu value phải phản ánh cardinality của quan hệ mà resolver cần phân giải.

## Luồng key và value trong một query

Giả sử schema có Book và Author:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Model Java:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}

public record Author(
        String id,
        String name) {
}
~~~

Client yêu cầu:

~~~graphql
query {
  books {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

GraphQL thực hiện Query books, nhận danh sách Book, rồi phân giải field author cho từng phần tử. Resolver author không truy vấn repository trực tiếp; nó gửi authorId vào DataLoader:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<String, Author> authorLoader) {
        return authorLoader.load(book.authorId());
    }
}
~~~

Giả sử danh sách sách có các authorId a-1, a-2, a-1, DataLoader có thể gom các yêu cầu và tải hai tác giả duy nhất nếu cache theo key đang bật. Kết quả Author được phân phối về các field author của từng Book.

Key và value có thể hình dung như sau:

| Resolver yêu cầu | Key gửi vào | Value cần nhận |
| --- | --- | --- |
| Book 1 | a-1 | Author có ID a-1 |
| Book 2 | a-2 | Author có ID a-2 |
| Book 3 | a-1 | Cùng Author có ID a-1 |

DataLoader gom yêu cầu tải dữ liệu. Nó không tự biết cách truy vấn database; batch loader được ứng dụng đăng ký sẽ thực hiện phần đó.

## BatchLoader: kết quả phải khớp thứ tự key

GraphQL Java DataLoader hỗ trợ BatchLoader<K, V>. Batch loader nhận một danh sách key và trả về một danh sách value tương ứng:

~~~java
BatchLoader<String, Author> batchLoader = authorIds ->
        CompletableFuture.supplyAsync(() -> {
            Map<String, Author> authorsById =
                    authorRepository.findAllById(authorIds).stream()
                            .collect(Collectors.toMap(
                                    Author::id,
                                    Function.identity()));

            return authorIds.stream()
                    .map(authorsById::get)
                    .collect(Collectors.toList());
        });
~~~

Điều kiện quan trọng của BatchLoader là **vị trí value phải tương ứng với vị trí key trong danh sách đầu vào**. Nếu đầu vào là [a-1, a-2, a-3], kết quả phải có dạng [author-a1, author-a2, author-a3]. Không được trả thẳng danh sách repository nếu database trả kết quả theo thứ tự khác.

Ví dụ repository có thể trả [author-a3, author-a1] vì a-2 không tồn tại và thứ tự truy vấn không được bảo đảm. Nếu trả nguyên danh sách đó, DataLoader có thể gán sai tác giả cho resolver. Cách an toàn là lập map theo ID rồi duyệt lại danh sách key ban đầu để tạo danh sách value đúng thứ tự.

Nếu key không tìm thấy, batch loader có thể đặt null ở đúng vị trí tương ứng, miễn là kiểu GraphQL và chính sách dữ liệu cho phép. Nếu field author được khai báo Author!, null sẽ tạo GraphQL execution error và kích hoạt null propagation. Nếu field nullable, response có thể chứa author: null.

## MappedBatchLoader: trả kết quả theo map key/value

Khi repository không bảo đảm thứ tự, MappedBatchLoader<K, V> thường dễ dùng hơn. Nó nhận tập key và trả về map trong đó mỗi key ánh xạ trực tiếp tới value:

~~~java
MappedBatchLoader<String, Author> mappedLoader = authorIds ->
        CompletableFuture.supplyAsync(() ->
                authorRepository.findAllById(authorIds).stream()
                        .collect(Collectors.toMap(
                                Author::id,
                                Function.identity())));
~~~

Với cách này, thứ tự phần tử trong map không quan trọng. DataLoader tra value theo key ban đầu để phân phối cho từng lời gọi load. Nếu một key không có trong map, kết quả cho key đó là null.

So sánh:

| Tiêu chí | BatchLoader | MappedBatchLoader |
| --- | --- | --- |
| Đầu vào | Danh sách key | Tập key |
| Kết quả | Danh sách value | Map key sang value |
| Ràng buộc | Value phải cùng thứ tự với key | Mỗi value phải được đặt dưới đúng key |
| Phù hợp | Nguồn dữ liệu trả kết quả có thứ tự tương ứng | Repository trả kết quả không theo thứ tự hoặc có key bị thiếu |

Chọn mapped loader khi nguồn dữ liệu trả về các bản ghi theo thứ tự riêng hoặc có thể bỏ qua key không tìm thấy. Chọn batch loader dạng list khi có thể bảo đảm chính xác thứ tự và số lượng kết quả.

## Đăng ký mapped batch loader với Spring for GraphQL

Spring for GraphQL cung cấp BatchLoaderRegistry để đăng ký loader theo cặp kiểu key/value. Registry đăng ký định nghĩa loader và tạo DataLoader tương ứng trong registry của từng GraphQL request.

Ví dụ đăng ký loader Author:

~~~java
@Configuration
public class DataLoaderConfiguration {

    public DataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(String.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        Mono.fromSupplier(() ->
                                authorService.findByIds(authorIds)));
    }
}
~~~

Giả sử authorService.findByIds trả về Map<String, Author> với key là Author ID. Phần generic trong forTypePair phải khớp với kiểu DataLoader mà resolver yêu cầu: DataLoader<String, Author>.

Resolver lấy loader theo kiểu key/value:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<String, Author> authorLoader) {
        return authorLoader.load(book.authorId());
    }
}
~~~

Spring for GraphQL cung cấp DataLoader đã đăng ký cho resolver theo request hiện tại. Ứng dụng không cần tự tạo một DataLoader dùng chung ở mức singleton. Loader được tạo theo registry của request để cache và dữ liệu không vô tình dùng chung giữa những request hoặc người dùng khác nhau.

Nếu dùng BatchLoader dạng danh sách thay vì mapped loader, đăng ký bằng registerBatchLoader và bảo đảm danh sách value trả về có cùng thứ tự với danh sách key đầu vào. Hãy chọn một kiểu loader phù hợp với cách repository trả dữ liệu.

## DataLoader key cần có equals và hashCode ổn định

DataLoader thường cache theo key. Vì vậy, key cần có quy tắc so sánh nhất quán:

- Hai key đại diện cho cùng một dữ liệu phải được coi là bằng nhau.
- equals và hashCode phải nhất quán.
- Không thay đổi các field tham gia equals/hashCode sau khi key được đưa vào loader.

Các kiểu đơn giản như String, Long, UUID hoặc enum thường phù hợp. Nếu cần key tổng hợp, có thể dùng Java record:

~~~java
public record ProductPriceKey(
        String productId,
        String currency) {
}
~~~

Khi đó loader có thể có kiểu:

~~~java
DataLoader<ProductPriceKey, Money> priceLoader;
~~~

Key tổng hợp giúp phân biệt cùng một product nhưng khác currency. Nếu chỉ dùng productId làm key, DataLoader có thể trả nhầm giá đã được cache cho currency khác.

Không nên dùng một object mutable làm key nếu các thuộc tính quyết định equality có thể thay đổi trong quá trình xử lý. Việc key không ổn định có thể khiến cache không tìm lại được entry đã lưu hoặc tạo nhiều entry ngoài dự kiến.

## Key trùng lặp và cache

DataLoader thường bật caching theo key. Nếu nhiều resolver cùng gọi load("a-1") trong một request, DataLoader có thể dùng chung future và chỉ cần tải value một lần. Điều này giúp tránh cả N+1 lẫn việc tải lặp cùng một key.

Ví dụ:

~~~java
CompletableFuture<Author> first = authorLoader.load("a-1");
CompletableFuture<Author> second = authorLoader.load("a-1");
~~~

Hai lời gọi có cùng key trong cùng DataLoader có thể dùng chung kết quả đã đăng ký trong cache. Batch loader vì thế không nhất thiết nhận key trùng lặp khi caching được bật.

Nếu tắt caching, loader có thể nhận nhiều lần xuất hiện của cùng key tùy cấu hình và cách gọi. Với BatchLoader, danh sách đầu ra vẫn phải khớp từng vị trí key đầu vào. Với MappedBatchLoader, map chỉ có một entry cho mỗi key vì map không biểu diễn nhiều value riêng cho cùng một key.

Không nên tắt cache chỉ để xử lý lỗi mapping. Trước tiên hãy xác định key có ổn định không, batch loader có trả đúng value không và cache có được dùng đúng phạm vi request không.

## Value bị thiếu, null và lỗi tải dữ liệu

Không phải key nào cũng có value. Ví dụ Book tham chiếu authorId đã bị xóa hoặc không tồn tại. Batch loader cần có quy tắc rõ:

- Trả null cho key không tồn tại nếu schema cho phép field nullable.
- Trả lỗi nếu dữ liệu thiếu là vi phạm nghiệp vụ.
- Không tự ghép một value khác vào vị trí key bị thiếu để giữ đủ số phần tử.

Với BatchLoader, danh sách trả về phải giữ đủ vị trí cho từng key; value null có thể biểu diễn key không có dữ liệu. Với MappedBatchLoader, key không xuất hiện trong map được xem là không có value tương ứng.

Nếu batch loader phát sinh lỗi ở cấp batch, các lời gọi đang chờ trong batch có thể cùng thất bại. Nếu lỗi chỉ thuộc một key, hãy cân nhắc cách biểu diễn lỗi theo từng phần tử mà DataLoader Java hỗ trợ hoặc xử lý ở service để những key còn lại vẫn có thể trả kết quả. Không nên nuốt lỗi rồi trả một map rỗng vì client sẽ khó phân biệt dữ liệu thật sự không tồn tại với lỗi hệ thống.

## Value có thể là danh sách hoặc object phức hợp

DataLoader không giới hạn value là một object đơn. Với quan hệ một-nhiều, key có thể là bookId và value là danh sách Review:

~~~java
DataLoader<String, List<Review>> reviewsLoader;
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public CompletableFuture<List<Review>> reviews(
        Book book,
        DataLoader<String, List<Review>> reviewsLoader) {
    return reviewsLoader.load(book.id());
}
~~~

Mapped loader tương ứng có thể trả Map<String, List<Review>>, mỗi bookId ánh xạ tới danh sách review của sách đó. Nếu một sách chưa có review, hãy trả danh sách rỗng thay vì null khi schema khai báo [Review!]!.

Với dữ liệu nhiều chiều, có thể dùng record làm value hoặc key. Tuy nhiên, cần giữ mô hình đơn giản và xác định rõ ý nghĩa của từng kiểu để việc mapping dễ kiểm thử.

## Cache thuộc phạm vi request

DataLoader thường giữ cache trong suốt một GraphQL request. Khi request kết thúc, registry và cache tương ứng được loại bỏ. Nhờ đó, cùng một key có thể được tải lại trong request tiếp theo để nhận dữ liệu mới.

Spring for GraphQL tích hợp BatchLoaderRegistry với DataLoaderRegistry theo request. Tránh khai báo static DataLoader hoặc giữ DataLoader trong field singleton của controller/service vì có thể gây:

- Dữ liệu cũ được tái sử dụng giữa nhiều request.
- Cache dùng chung giữa các người dùng có quyền truy cập khác nhau.
- Tăng bộ nhớ do cache tồn tại quá lâu.
- Dữ liệu một tenant bị lộ sang tenant khác nếu key không bao gồm phạm vi tenant.

Nếu loader cần context như tenant hoặc principal, hãy dùng context của request trong batch loader và bảo đảm truy vấn dữ liệu áp dụng cùng quy tắc phân quyền. Không dựa vào việc client không biết key để bảo vệ dữ liệu.

## Làm mới cache sau mutation

Nếu một mutation thay đổi value đã được DataLoader cache trong cùng request, những lần gọi sau có thể nhận value cũ. DataLoader cung cấp thao tác quản lý cache như clear(key), clearAll() và prime(key, value).

Ví dụ sau khi cập nhật Author:

~~~java
authorLoader.clear(updatedAuthor.id())
        .prime(updatedAuthor.id(), updatedAuthor);
~~~

clear loại bỏ entry cũ; prime đưa value mới vào cache. Có thể chỉ cần clear để lần load tiếp theo tải lại dữ liệu. Việc cập nhật cache phải nhất quán với kết quả mutation và transaction: chỉ prime value mới khi ứng dụng đã xác định thay đổi thành công.

Thông thường, mỗi HTTP GraphQL request có một DataLoaderRegistry riêng. Cache refresh chủ yếu có ý nghĩa khi nhiều field trong cùng operation cùng sử dụng loader sau một thay đổi dữ liệu. Không dùng thao tác này như cache toàn cục giữa các request.

## Phân biệt DataLoader và @BatchMapping

@BatchMapping là cách khai báo batch resolver thuận tiện trong Spring for GraphQL. Framework đăng ký DataLoader phù hợp phía sau và gom các source object để gọi phương thức batch:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsFor(books);
    }
}
~~~

Trong ví dụ, source Book đóng vai trò key ở lớp batch mapping, còn Author là value. Nếu cần kiểm soát key rõ hơn, dùng BatchLoaderRegistry và DataLoader<K, V> trực tiếp như ví dụ authorId ở trên.

Chọn @BatchMapping khi mapping đơn giản từ source object sang dữ liệu liên quan. Chọn DataLoader trực tiếp khi cần dùng chung loader ở nhiều resolver, dùng key tổng hợp, kiểm soát cache hoặc đăng ký batch logic theo cặp kiểu key/value.

## Kiểm thử key và value mapping

Một batch loader cần được kiểm thử với dữ liệu có thứ tự khác nhau, key trùng và key thiếu. Ví dụ:

| Đầu vào key | Dữ liệu repository trả | Kết quả cần có |
| --- | --- | --- |
| [a-1, a-2] | [a-2, a-1] | Value vẫn được gắn đúng a-1 và a-2 |
| [a-1, a-2] | Chỉ có a-1 | a-2 nhận null hoặc lỗi theo hợp đồng |
| [a-1, a-1] | Một Author a-1 | Cả hai resolver nhận cùng value khi cache bật |
| [a-1, a-2] | Batch loader phát sinh exception | Các field liên quan nhận lỗi theo chính sách |

Có thể dùng GraphQlTester để kiểm tra kết quả end-to-end:

~~~java
graphQlTester.document("""
        query {
            books {
                id
                author {
                    id
                    name
                }
            }
        }
        """)
    .execute()
    .path("books")
    .entityList(BookView.class)
    .hasSize(3);
~~~

Ngoài response, nên kiểm tra số lần gọi repository hoặc batch service. Với nhiều Book có cùng authorId, số lần tải phải phản ánh số key duy nhất khi cache bật, thay vì số Book. Với mapped loader, đảo thứ tự kết quả repository để xác nhận map key/value vẫn đúng.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tác giả bị gán nhầm cho sách | BatchLoader trả list theo thứ tự repository thay vì thứ tự key | Tạo map theo ID rồi dựng lại list theo key đầu vào |
| Một số field author thành null | Key không có value hoặc map thiếu entry | Xác định chính sách missing key và nullability |
| Batch loader không được gọi | Resolver không dùng DataLoader hoặc loader pair chưa đăng ký đúng | Kiểm tra generic key/value và registry |
| Loader trả sai kiểu | forTypePair không khớp kiểu DataLoader trong resolver | Đồng bộ K và V ở registry và method signature |
| Cùng key vẫn truy vấn nhiều lần | Cache bị tắt, key equality không ổn định hoặc loader khác registry | Kiểm tra DataLoaderOptions và equals/hashCode |
| Dữ liệu cũ sau mutation | Cache giữ value đã tải trước khi cập nhật | clear hoặc prime key sau khi thay đổi thành công |
| Rò rỉ dữ liệu giữa request | Dùng DataLoader/cache ở scope singleton | Dùng loader được tạo từ registry theo request |
| Batch thất bại đồng loạt | Exception ở cấp batch | Phân biệt lỗi toàn batch với lỗi từng key |

## Nguyên tắc thiết kế key và value

Khi thiết kế DataLoader trong Spring for GraphQL, hãy nhớ:

1. **Chọn key theo dữ liệu cần tải.** Dùng ID hoặc record key ổn định, không dùng object mutable.
2. **Chọn value theo cardinality.** Một key có thể ánh xạ tới một object, danh sách hoặc DTO.
3. **Giữ đúng hợp đồng mapping.** BatchLoader trả list cùng thứ tự key; MappedBatchLoader trả map với key chính xác.
4. **Xử lý missing key có chủ đích.** Phân biệt null hợp lệ với dữ liệu thiếu hoặc lỗi hệ thống.
5. **Hiểu cache và key equality.** Key phải có equals/hashCode ổn định; cache mặc định hữu ích cho key trùng.
6. **Giữ loader theo request.** Dùng BatchLoaderRegistry của Spring để tránh cache dùng chung ngoài ý muốn.
7. **Làm mới cache khi cần.** clear hoặc prime sau mutation khi field tiếp theo trong cùng request cần dữ liệu mới.
8. **Kiểm thử thứ tự và key trùng.** Dữ liệu repository trả về có thể không theo thứ tự yêu cầu.

DataLoader key và value xác định cách một yêu cầu tải dữ liệu được gom và trả lại đúng resolver. Key nhận diện dữ liệu cần tải; value là kết quả tương ứng. BatchLoader dựa vào thứ tự key/value, còn MappedBatchLoader dựa vào ánh xạ trong Map. Trong Spring for GraphQL, BatchLoaderRegistry quản lý loader theo request, giúp resolver giảm N+1 mà vẫn giữ mapping chính xác, cache có phạm vi và xử lý rõ các trường hợp thiếu dữ liệu.
