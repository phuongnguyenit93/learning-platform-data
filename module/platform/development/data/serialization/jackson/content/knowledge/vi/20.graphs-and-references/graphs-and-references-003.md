# Cắt vòng tham chiếu bằng thiết kế DTO hoặc bỏ thuộc tính

Trong Java, các object có thể tham chiếu lẫn nhau. Một User có danh sách Post, trong khi mỗi Post lại giữ tham chiếu đến User đã tạo ra nó. Mô hình này hợp lý trong bộ nhớ, nhưng khi Jackson serialize toàn bộ object graph thành JSON, nó có thể đi theo các tham chiếu lặp lại mãi:

~~~text
User
  |
  +-- posts
        |
        +-- Post
              |
              +-- author
                    |
                    +-- posts
                          |
                          +-- Post
                                |
                                +-- author
                                      ...
~~~

JSON là một cấu trúc cây, còn object graph trong Java có thể là đồ thị có chu trình. Nếu không kiểm soát quan hệ hai chiều, Jackson có thể gặp lỗi vòng tham chiếu, đệ quy quá sâu hoặc tạo payload lặp dữ liệu rất lớn.

Có hai hướng xử lý phổ biến:

- **Thiết kế DTO theo góc nhìn của API**: chỉ đưa vào response những dữ liệu cần thiết, thường thay object tham chiếu ngược bằng một DTO tóm tắt hoặc ID.
- **Bỏ qua thuộc tính gây vòng lặp**: dùng annotation như @JsonIgnore hoặc @JsonIgnoreProperties để ngăn Jackson đi theo một nhánh không cần thiết.

Jackson còn có các cơ chế chuyên biệt như @JsonManagedReference/@JsonBackReference và @JsonIdentityInfo khi cần giữ một phần quan hệ object graph. Việc chọn cơ chế phụ thuộc vào hình dạng JSON mà consumer cần, khả năng deserialize ngược và hợp đồng API.

## 1. Vì sao object graph có thể tạo vòng tham chiếu?

Một mô hình quan hệ hai chiều thường xuất hiện trong ứng dụng quản lý dữ liệu:

~~~java
public class User {
    private Long id;
    private String name;
    private List<Post> posts;

    // constructors, getters, setters
}

public class Post {
    private Long id;
    private String title;
    private User author;

    // constructors, getters, setters
}
~~~

User giữ danh sách bài viết. Mỗi Post lại giữ tác giả là User. Nếu user có post và post trỏ lại đúng user đó, hai object tạo thành chu trình.

Ví dụ tạo object:

~~~java
User user = new User(1L, "Linh");
Post post = new Post(10L, "Jackson basics", user);

user.setPosts(List.of(post));
~~~

Quan hệ trong bộ nhớ:

~~~text
user ──posts[0]──> post
  ^                  |
  |                  |
  +------author------+
~~~

Khi gọi:

~~~java
String json = mapper.writeValueAsString(user);
~~~

Jackson bắt đầu ghi User, sau đó đi vào posts, ghi Post, tiếp tục đi vào author và gặp lại User. Nếu không có quy tắc quản lý tham chiếu, quá trình có thể lặp lại.

Đây không phải lỗi cú pháp của JSON đầu vào. Nó là vấn đề khi chuyển một đồ thị object có chu trình sang định dạng JSON vốn không có tham chiếu object trực tiếp.

Cần phân biệt:

- **Vòng tham chiếu thật**: một object có thể đi theo các tham chiếu và quay lại chính nó.
- **Dữ liệu lồng sâu nhưng không có chu trình**: mỗi nhánh kết thúc, nhưng có thể tạo JSON rất lớn.
- **Cùng một object được tham chiếu từ nhiều nơi**: graph có shared reference nhưng chưa chắc có chu trình. Jackson có thể serialize lặp object ở nhiều nhánh nếu không dùng object identity.

Cách xử lý cần dựa trên cấu trúc thực tế, không chỉ dựa vào việc thấy hai class tham chiếu nhau.

## 2. Thiết kế DTO để cắt graph theo nhu cầu response

Với API, response DTO thường là cách dễ kiểm soát nhất. DTO mô tả dữ liệu consumer cần nhận, thay vì serialize nguyên entity hoặc domain object.

Ví dụ, response danh sách bài viết của một user có thể chỉ cần ID và tiêu đề của từng bài. Không cần đưa toàn bộ author trở lại bên trong mỗi Post.

~~~java
public record UserResponse(
    Long id,
    String name,
    List<PostSummaryResponse> posts
) {}

public record PostSummaryResponse(
    Long id,
    String title
) {}
~~~

Mapper chuyển từ entity sang DTO:

~~~java
public UserResponse toUserResponse(User user) {
    List<PostSummaryResponse> posts = user.getPosts().stream()
        .map(post -> new PostSummaryResponse(
            post.getId(),
            post.getTitle()
        ))
        .toList();

    return new UserResponse(
        user.getId(),
        user.getName(),
        posts
    );
}
~~~

JSON đầu ra:

~~~json
{
  "id": 1,
  "name": "Linh",
  "posts": [
    {
      "id": 10,
      "title": "Jackson basics"
    }
  ]
}
~~~

Không có thuộc tính author trong PostSummaryResponse, vì vậy graph được cắt tại ranh giới DTO. Jackson chỉ serialize các trường của DTO; nó không quay lại entity User ban đầu.

Nếu một endpoint cần thông tin tác giả trong từng bài viết, hãy dùng DTO tóm tắt tác giả:

~~~java
public record AuthorSummaryResponse(
    Long id,
    String name
) {}

public record PostResponse(
    Long id,
    String title,
    AuthorSummaryResponse author
) {}
~~~

AuthorSummaryResponse không chứa danh sách posts. Như vậy response vẫn thể hiện quan hệ cần thiết nhưng không tạo chu trình.

Nguyên tắc thiết kế là mỗi DTO biểu diễn một góc nhìn hữu hạn. Khi một object con cần tham chiếu ngược đến object cha, hãy quyết định API thực sự cần toàn bộ object cha, một số field tóm tắt hay chỉ ID.

## 3. Cắt vòng tham chiếu bằng DTO ID

Trong nhiều API, một tham chiếu ngược chỉ cần ID:

~~~java
public record PostResponse(
    Long id,
    String title,
    Long authorId
) {}
~~~

Mapping:

~~~java
public PostResponse toPostResponse(Post post) {
    return new PostResponse(
        post.getId(),
        post.getTitle(),
        post.getAuthor().getId()
    );
}
~~~

JSON:

~~~json
{
  "id": 10,
  "title": "Jackson basics",
  "authorId": 1
}
~~~

Cách này có một số lợi ích:

- JSON nhỏ và dễ cache.
- Không lặp thông tin User trong mọi Post.
- Không tạo vòng tham chiếu.
- Consumer có thể gọi endpoint khác nếu cần chi tiết tác giả.
- Hợp đồng thể hiện rõ quan hệ bằng ID.

Nếu API cần cả thông tin tóm tắt lẫn ID, có thể tạo một AuthorSummaryResponse nhỏ. Hãy tránh tái sử dụng một DTO quá lớn chứa các quan hệ quay ngược không cần thiết.

## 4. Dùng @JsonIgnore để bỏ thuộc tính gây vòng lặp

Nếu chỉ cần loại bỏ một thuộc tính khỏi JSON, @JsonIgnore là cách đơn giản:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Post {
    private Long id;
    private String title;

    @JsonIgnore
    private User author;

    // getters and setters
}
~~~

Khi serialize Post, Jackson bỏ qua author. Nhờ đó, quá trình không đi ngược từ Post về User.

Một cách khác là đặt annotation trên getter:

~~~java
@JsonIgnore
public User getAuthor() {
    return author;
}
~~~

Jackson kết hợp metadata của field, getter, setter và constructor thành một logical property. Vì vậy, nên đặt annotation nhất quán ở đúng accessor/property mà ứng dụng đang dùng và kiểm tra cả chiều serialize lẫn deserialize.

JSON đầu ra chỉ còn:

~~~json
{
  "id": 10,
  "title": "Jackson basics"
}
~~~

@JsonIgnore thường ảnh hưởng đến cả serialization và deserialization của logical property. Nếu ứng dụng cần nhận author khi đọc JSON nhưng không muốn phát author ra response, hãy chọn chính sách truy cập rõ ràng thay vì giả định @JsonIgnore chỉ bỏ field ở chiều ghi.

## 5. Bỏ property khỏi output nhưng vẫn cho phép input

@JsonProperty(access = JsonProperty.Access.WRITE_ONLY) cho phép Jackson nhận property khi deserialize nhưng không ghi nó ra JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public class PostRequest {
    private Long id;
    private String title;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private User author;

    // getters and setters
}
~~~

Với WRITE_ONLY:

- Deserialization: Jackson có thể gán author từ JSON.
- Serialization: Jackson không đưa author vào output.

Ngược lại, READ_ONLY thường cho phép serialize property nhưng không nhận giá trị từ input JSON.

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private Long calculatedScore;
~~~

Access control hữu ích khi cùng một kiểu được dùng ở nhiều chiều, nhưng request và response riêng biệt thường dễ hiểu hơn. Không nên dùng một entity làm cả request model lẫn response model chỉ để giảm số class nếu hai chiều có chính sách dữ liệu khác nhau.

Lưu ý: WRITE_ONLY chỉ ngăn property được serialize; nó không tự cắt các quan hệ khác trong object graph nếu chúng vẫn được truy cập qua một nhánh khác.

## 6. Dùng @JsonIgnoreProperties cho một nhóm thuộc tính

@JsonIgnoreProperties cho phép bỏ qua một hoặc nhiều tên property:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties({"author", "internalNotes"})
public class Post {
    private Long id;
    private String title;
    private User author;
    private String internalNotes;

    // getters and setters
}
~~~

Khi serialize Post, các property được liệt kê sẽ bị bỏ qua. Annotation có thể đặt ở cấp class hoặc property tùy phạm vi cần áp dụng.

Ví dụ bỏ thuộc tính trên một property lồng:

~~~java
public class PostContainer {
    @JsonIgnoreProperties({"posts"})
    private User author;
}
~~~

Ở ví dụ này, khi serialize author qua property đó, Jackson bỏ qua posts của User. Đây là cách cắt nhánh tham chiếu ở một điểm cụ thể.

Có thêm allowGetters và allowSetters để điều chỉnh hướng truy cập:

~~~java
@JsonIgnoreProperties(
    value = {"author"},
    allowSetters = true
)
public class Post {
    private User author;
}
~~~

allowSetters = true cho phép ghi property trong quá trình deserialize, trong khi property vẫn bị bỏ qua khi serialize. Điều này gần với một property chỉ nhận input.

Hãy phân biệt allowGetters và allowSetters:

- allowGetters = true: cho phép đọc property để serialize dù tên nằm trong danh sách ignore.
- allowSetters = true: cho phép gán property khi deserialize dù tên nằm trong danh sách ignore.

Nếu chỉ muốn bỏ một property duy nhất, @JsonIgnore hoặc @JsonProperty(access = ...) thường rõ hơn. @JsonIgnoreProperties phù hợp khi cần bỏ nhiều property hoặc áp dụng chính sách trên một kiểu/property cụ thể.

## 7. Dùng @JsonManagedReference và @JsonBackReference cho quan hệ hai chiều

Jackson cung cấp cặp annotation dành cho quan hệ parent/child hai chiều:

- @JsonManagedReference đánh dấu phía forward/parent được serialize bình thường.
- @JsonBackReference đánh dấu phía back-reference/child quay về parent; phía này không được serialize.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonBackReference;
import com.fasterxml.jackson.annotation.JsonManagedReference;

public class User {
    private Long id;
    private String name;

    @JsonManagedReference
    private List<Post> posts;

    // getters and setters
}

public class Post {
    private Long id;
    private String title;

    @JsonBackReference
    private User author;

    // getters and setters
}
~~~

Khi serialize User:

~~~json
{
  "id": 1,
  "name": "Linh",
  "posts": [
    {
      "id": 10,
      "title": "Jackson basics"
    }
  ]
}
~~~

posts vẫn được ghi, nhưng author không được ghi nên vòng tham chiếu bị cắt.

Khác với @JsonIgnore, cặp managed/back reference còn hỗ trợ khôi phục quan hệ ngược khi deserialize. Khi Jackson tạo User và các Post từ JSON, nó có thể gán User đang chứa danh sách làm author của từng Post tương ứng.

Ví dụ:

~~~java
User user = mapper.readValue(json, User.class);

Post firstPost = user.getPosts().get(0);

assertSame(user, firstPost.getAuthor());
~~~

Điều này hữu ích khi JSON biểu diễn một cây cha/con và quan hệ ngược chỉ tồn tại trong mô hình Java.

### Đặt tên reference khi có nhiều quan hệ

Nếu class có nhiều quan hệ hai chiều, hãy đặt tên cặp reference để Jackson ghép đúng:

~~~java
public class User {
    @JsonManagedReference("user-posts")
    private List<Post> posts;

    @JsonManagedReference("user-comments")
    private List<Comment> comments;
}

public class Post {
    @JsonBackReference("user-posts")
    private User author;
}

public class Comment {
    @JsonBackReference("user-comments")
    private User author;
}
~~~

Tên trong @JsonManagedReference và @JsonBackReference phải khớp nhau cho cùng một cặp. Các cặp khác nhau cần tên khác nhau.

Back reference được thiết kế cho property đơn tham chiếu về parent, không phải một collection hoặc Map chứa nhiều parent. Hãy dùng managed/back reference cho quan hệ parent-child phù hợp; với graph phức tạp hơn, cân nhắc DTO hoặc object identity.

## 8. Khi nào @JsonManagedReference/@JsonBackReference không phù hợp?

Cặp annotation này phù hợp khi có một hướng chính để serialize và một hướng ngược chỉ cần phục hồi trong object Java. Nó không phải giải pháp tổng quát cho mọi graph.

Không nên chọn nó một cách máy móc khi:

- Một child có thể thuộc nhiều parent.
- Quan hệ là nhiều-nhiều và cả hai phía đều cần xuất hiện.
- Consumer cần tham chiếu ngược trong JSON.
- Graph không có cấu trúc parent-child rõ ràng.
- Nhiều đường khác nhau dẫn đến cùng một object và cần giữ identity.
- Cấu trúc API yêu cầu biểu diễn tham chiếu bằng ID.

Trong các trường hợp đó, DTO với ID hoặc @JsonIdentityInfo thường phù hợp hơn.

Ngoài ra, nếu dùng immutable object hoặc constructor creator, cần kiểm tra khả năng gán back-reference theo đúng kiểu và phiên bản Jackson. Cặp annotation không làm cho mọi kiểu object bất biến tự động có thể khôi phục quan hệ.

## 9. Dùng @JsonIdentityInfo khi cần giữ object identity

Nếu consumer cần nhận biết hai nhánh đang tham chiếu đến cùng một object, có thể dùng object identity thay vì bỏ tham chiếu ngược.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class User {
    private Long id;
    private String name;
    private List<Post> posts;

    // getters and setters
}
~~~

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class Post {
    private Long id;
    private String title;
    private User author;

    // getters and setters
}
~~~

Jackson ghi object đầy đủ khi gặp lần đầu, sau đó có thể dùng object ID để tham chiếu lại object đã được ghi. JSON có thể chứa ID thay vì mở rộng User thêm một lần nữa tại nhánh author.

Cơ chế này giữ được quan hệ identity nhưng làm wire format phức tạp hơn. Consumer cần hiểu quy tắc object ID và tham chiếu; không phải mọi hệ thống JSON đều tự động giải quyết các ID này thành object.

Nếu API chỉ cần một response đơn giản, DTO vẫn thường dễ hiểu hơn. Dùng @JsonIdentityInfo khi việc giữ identity của graph là một phần thực sự cần thiết của hợp đồng.

## 10. Dùng DTO và annotation ở những lớp khác nhau

Không nhất thiết phải chọn một cơ chế duy nhất cho toàn ứng dụng. Một thiết kế thường dùng:

- Entity/domain model giữ quan hệ hai chiều vì nghiệp vụ hoặc ORM cần.
- DTO quyết định dữ liệu public được phép xuất.
- @JsonIgnore có thể bảo vệ một property nội bộ khỏi bị serialize ngoài ý muốn.
- @JsonManagedReference/@JsonBackReference phù hợp với một số luồng binding parent-child.
- @JsonIdentityInfo chỉ dùng khi consumer cần tham chiếu object identity.

Ví dụ entity:

~~~java
public class UserEntity {
    private Long id;
    private String name;
    private List<PostEntity> posts;
}

public class PostEntity {
    private Long id;
    private String title;
    private UserEntity author;
}
~~~

DTO API:

~~~java
public record UserDetailResponse(
    Long id,
    String name,
    List<PostDetailResponse> posts
) {}

public record PostDetailResponse(
    Long id,
    String title,
    Long authorId
) {}
~~~

Mapper:

~~~java
public UserDetailResponse toResponse(UserEntity user) {
    return new UserDetailResponse(
        user.getId(),
        user.getName(),
        user.getPosts().stream()
            .map(post -> new PostDetailResponse(
                post.getId(),
                post.getTitle(),
                post.getAuthor().getId()
            ))
            .toList()
    );
}
~~~

DTO định nghĩa rõ API cần gì. Entity vẫn có thể giữ quan hệ hai chiều cho persistence hoặc domain logic, nhưng Jackson không serialize trực tiếp entity.

## 11. Lưu ý với JPA/Hibernate và lazy loading

Trong ứng dụng dùng JPA/Hibernate, entity thường có quan hệ hai chiều và proxy lazy. Serialize entity trực tiếp có thể gây ra nhiều vấn đề cùng lúc:

- Vòng tham chiếu do quan hệ hai chiều.
- LazyInitializationException nếu session đã đóng khi Jackson truy cập getter.
- N+1 query khi serialize làm phát sinh việc tải từng quan hệ.
- Payload lớn vì Jackson đi qua nhiều quan hệ.
- Lộ field persistence hoặc dữ liệu nội bộ không thuộc API.

@JsonIgnore có thể ngăn Jackson truy cập một property cụ thể, nhưng không giải quyết toàn bộ vấn đề thiết kế response hoặc truy vấn. @JsonManagedReference/@JsonBackReference cũng không tự kiểm soát lazy loading và số lượng truy vấn.

DTO projection cho phép service lấy đúng dữ liệu cần thiết bằng query hoặc mapper. Khi tạo DTO, hãy kiểm soát transaction và fetch plan để không vô tình truy vấn từng phần tử trong vòng lặp.

Nếu dùng entity làm API model vì lý do đặc biệt, hãy xác định rõ property nào được serialize, quan hệ nào được tải và dữ liệu nào được phép công khai.

## 12. Cẩn thận với Lombok và các phương thức đệ quy

Vòng tham chiếu không chỉ ảnh hưởng Jackson. Nếu dùng Lombok @Data trên entity có quan hệ hai chiều, equals(), hashCode() hoặc toString() được sinh có thể đi qua các quan hệ và đệ quy.

Ví dụ User.toString() in posts, mỗi Post.toString() lại in author, dẫn đến vòng lặp tương tự. Điều này có thể xảy ra ngay cả trước khi Jackson serialize.

Với entity có quan hệ, hãy cân nhắc @ToString.Exclude, @EqualsAndHashCode.Exclude hoặc tự định nghĩa equals/hashCode theo khóa phù hợp. Tránh đưa toàn bộ quan hệ hai chiều vào toString hoặc phép so sánh object.

@JsonIgnore chỉ điều khiển Jackson; nó không tự loại property khỏi equals(), hashCode() hoặc toString() được sinh bởi thư viện khác.

## 13. Kiểm thử việc cắt vòng tham chiếu

Test cần xác nhận JSON có cấu trúc mong đợi và không lặp nhánh không cần thiết.

Ví dụ kiểm tra DTO:

~~~java
@Test
void userResponseDoesNotExpandAuthorBackReference() throws Exception {
    User user = new User(1L, "Linh");
    Post post = new Post(10L, "Jackson basics", user);
    user.setPosts(List.of(post));

    UserResponse response = mapper.toUserResponse(user);

    String json = mapper.writeValueAsString(response);
    JsonNode tree = mapper.readTree(json);

    assertEquals(1, tree.path("id").asLong());
    assertEquals(
        "Jackson basics",
        tree.path("posts").get(0).path("title").asText()
    );
    assertFalse(tree.path("posts").get(0).has("author"));
}
~~~

Với @JsonIgnore, kiểm tra property bị bỏ khỏi output:

~~~java
String json = mapper.writeValueAsString(post);
JsonNode tree = mapper.readTree(json);

assertFalse(tree.has("author"));
~~~

Với managed/back reference, kiểm tra cả serialize và deserialize:

~~~java
String json = mapper.writeValueAsString(user);
User restored = mapper.readValue(json, User.class);

assertSame(restored, restored.getPosts().get(0).getAuthor());
~~~

Test cuối chỉ phù hợp với mô hình mutable parent-child và cấu hình reference tương ứng. Nếu dùng nhiều reference pair, hãy kiểm tra từng cặp riêng để bảo đảm tên reference không bị ghép nhầm.

Không nên chỉ kiểm tra rằng serialize không ném exception. Hãy xác nhận payload không chứa dữ liệu ngoài hợp đồng, quan hệ cần thiết vẫn được biểu diễn và deserialization có hành vi đúng như yêu cầu.

## 14. Chọn cơ chế theo mục tiêu

| Nhu cầu | Cách xử lý nên cân nhắc |
|---|---|
| API chỉ cần một phần dữ liệu của entity | Thiết kế request/response DTO. |
| Nhánh tham chiếu ngược không cần trong JSON | @JsonIgnore. |
| Bỏ nhiều property khỏi một kiểu | @JsonIgnoreProperties. |
| Không ghi property nhưng vẫn nhận input | @JsonProperty(access = WRITE_ONLY) hoặc allowSetters phù hợp. |
| Quan hệ parent-child hai chiều và cần khôi phục back reference | @JsonManagedReference/@JsonBackReference. |
| Cần giữ identity và tham chiếu object trong graph | @JsonIdentityInfo. |
| Cần tham chiếu giữa các resource API | Dùng ID hoặc URI trong DTO. |
| Entity JPA có lazy relation và vòng lặp | DTO projection cùng fetch plan rõ ràng. |

Trước khi chọn, hãy trả lời:

1. Consumer cần dữ liệu nào ở mỗi nhánh?
2. Tham chiếu ngược có cần xuất ra JSON không?
3. Khi deserialize, có cần khôi phục quan hệ Java không?
4. Một object có thể được tham chiếu từ nhiều nhánh không?
5. Cấu trúc có phải quan hệ parent-child đơn giản không?
6. DTO có thể cắt graph theo đúng hợp đồng mà không làm mất thông tin cần thiết không?

## Kết luận

Vòng tham chiếu xuất hiện khi object graph Java có những tham chiếu quay lại object đã đi qua. JSON là cấu trúc cây nên không thể biểu diễn trực tiếp chu trình object theo cách tự nhiên; serialize nguyên entity có thể dẫn đến lỗi hoặc payload lặp không cần thiết.

Với API, DTO thường là cách rõ ràng nhất để cắt graph: chỉ đưa dữ liệu cần thiết và thay tham chiếu ngược bằng ID hoặc DTO tóm tắt. Khi cần bỏ một property, dùng @JsonIgnore, @JsonIgnoreProperties hoặc quyền truy cập của @JsonProperty. Với quan hệ parent-child cần khôi phục khi deserialize, cân nhắc @JsonManagedReference/@JsonBackReference; khi cần giữ object identity, xem xét @JsonIdentityInfo. Hãy kiểm tra cả hai chiều, đặc biệt với entity JPA và các quan hệ lazy, để JSON phản ánh đúng hợp đồng mà không phụ thuộc vào toàn bộ graph nội bộ.

