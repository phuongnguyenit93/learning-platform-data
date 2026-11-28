# So sánh mô hình đồ thị với mô hình quan hệ và tài liệu

## Mục tiêu

Sau bài học này, bạn có thể:

- Mô tả cách mô hình đồ thị, mô hình quan hệ và mô hình tài liệu biểu diễn cùng một miền nghiệp vụ.
- Giải thích sự khác nhau giữa phép nối bảng, duyệt quan hệ và truy vấn tài liệu lồng nhau.
- Nhận biết khi nào dữ liệu có nhiều liên kết khiến mô hình đồ thị trở thành lựa chọn phù hợp.
- Hiểu Spring Data Neo4j ánh xạ node và relationship vào đối tượng Java như thế nào.

Spring Data Neo4j là lớp hỗ trợ làm việc với Neo4j trong ứng dụng Spring. Để sử dụng nó hiệu quả, trước hết cần hiểu mô hình property graph của Neo4j khác gì với hai cách tổ chức dữ liệu phổ biến khác: mô hình quan hệ và mô hình tài liệu.

## 1. Cùng một miền nghiệp vụ, ba cách biểu diễn

Giả sử ứng dụng quản lý phim cần lưu diễn viên, phim và vai diễn. Một diễn viên có thể tham gia nhiều phim; một phim có thể có nhiều diễn viên; mỗi lần tham gia có thể mang tên vai diễn khác nhau. Ta muốn trả lời những câu hỏi như:

- Diễn viên An đã tham gia những phim nào?
- Những diễn viên nào từng cùng đóng phim với An?
- Có thể đi từ An đến Bình qua một hoặc nhiều phim hay không?

Ba mô hình đều có thể lưu dữ liệu này, nhưng cấu trúc lưu trữ và cách truy vấn sẽ khác nhau.

### Mô hình quan hệ

Mô hình quan hệ tổ chức dữ liệu thành bảng. Mỗi bảng mô tả một loại thực thể hoặc một quan hệ nghiệp vụ; hàng biểu diễn bản ghi và cột biểu diễn thuộc tính. Khóa chính định danh bản ghi, còn khóa ngoại liên kết các bảng.

Ví dụ, miền phim có thể được biểu diễn bằng ba bảng:

| Bảng | Một số cột | Ý nghĩa |
|---|---|---|
| `person` | `id`, `name` | Thông tin diễn viên |
| `movie` | `id`, `title` | Thông tin phim |
| `acted_in` | `person_id`, `movie_id`, `role` | Quan hệ diễn viên tham gia phim và vai diễn |

`acted_in.person_id` tham chiếu `person.id`, còn `acted_in.movie_id` tham chiếu `movie.id`. Quan hệ nhiều-nhiều được biểu diễn qua bảng liên kết. Để tìm phim của một diễn viên, cơ sở dữ liệu kết hợp các bảng bằng phép `JOIN`:

~~~sql
SELECT m.title
FROM person p
JOIN acted_in a ON a.person_id = p.id
JOIN movie m ON m.id = a.movie_id
WHERE p.name = 'An'
ORDER BY m.title;
~~~

Mô hình quan hệ phù hợp khi dữ liệu có cấu trúc rõ, các quy tắc toàn vẹn cần được thể hiện chặt chẽ bằng khóa và ràng buộc, và ứng dụng thường truy vấn theo tập bản ghi hoặc tổng hợp trên nhiều bảng. SQL cung cấp hệ sinh thái phong phú cho báo cáo, thống kê và giao dịch.

Khi câu hỏi cần đi qua nhiều tầng liên kết, truy vấn thường phải nối thêm bảng. Điều này không có nghĩa `JOIN` luôn chậm; hệ quản trị quan hệ có thể tối ưu phép nối rất tốt. Tuy nhiên, câu truy vấn và cấu trúc bảng có thể trở nên khó đọc, khó thay đổi khi đường đi qua dữ liệu ngày càng đa dạng hoặc có độ sâu thay đổi.

### Mô hình tài liệu

Mô hình tài liệu lưu mỗi đối tượng dưới dạng một tài liệu, thường có cấu trúc gần với JSON. Các trường có thể chứa giá trị đơn, mảng hoặc tài liệu con. Thay vì chuẩn hóa mọi phần thành bảng riêng, ta có thể gom dữ liệu thường được đọc cùng nhau vào một tài liệu.

Ví dụ một tài liệu diễn viên có thể chứa danh sách vai diễn:

~~~json
{
  "_id": "person-42",
  "name": "An",
  "actingCredits": [
    {
      "movieId": "movie-7",
      "movieTitle": "The Matrix",
      "role": "Neo"
    },
    {
      "movieId": "movie-8",
      "movieTitle": "John Wick",
      "role": "John Wick"
    }
  ]
}
~~~

Nếu màn hình hồ sơ diễn viên thường hiển thị toàn bộ vai diễn, việc nhúng `actingCredits` vào tài liệu `person` có thể giúp đọc dữ liệu trong một lần truy vấn. Nhưng nếu thông tin phim được lưu lặp lại trong nhiều tài liệu diễn viên, khi tên phim thay đổi ứng dụng phải cập nhật nhiều nơi. Ta có thể thay phần nhúng bằng `movieId` tham chiếu đến tài liệu phim, nhưng khi đó việc lấy đầy đủ thông tin phim cần thêm một bước tra cứu hoặc phép kết hợp mà hệ quản trị tài liệu hỗ trợ.

Vì vậy, mô hình tài liệu thường phát huy hiệu quả khi dữ liệu được truy cập theo từng aggregate hoặc tài liệu tương đối độc lập, cấu trúc thuộc tính có thể linh hoạt và các trường lồng nhau thường được đọc, ghi cùng nhau. Việc nhúng hay tham chiếu cần dựa trên cách ứng dụng truy cập dữ liệu, kích thước tài liệu và yêu cầu cập nhật.

### Mô hình đồ thị

Neo4j sử dụng mô hình property graph. Mô hình này có ba thành phần chính:

- **Node** biểu diễn thực thể, chẳng hạn `Person` hoặc `Movie`.
- **Relationship** biểu diễn liên kết có hướng và có kiểu giữa hai node, chẳng hạn `ACTED_IN`.
- **Property** là các cặp tên và giá trị gắn trên node hoặc relationship.

Cùng dữ liệu ví dụ trên có thể biểu diễn như sau:

~~~text
(An:Person)-[:ACTED_IN {role: "Neo"}]->(TheMatrix:Movie)
(An:Person)-[:ACTED_IN {role: "John Wick"}]->(JohnWick:Movie)
~~~

`ACTED_IN` là một relationship thực sự trong đồ thị, không phải một cột chứa mã tham chiếu. Nó có kiểu, hướng và có thể mang thuộc tính như `role`. Nếu Bình cũng tham gia `The Matrix`, ta thêm một relationship từ node Bình đến node phim. Hai diễn viên có thể được xác định là từng cộng tác bằng cách tìm các đường đi qua node phim chung.

Truy vấn Cypher tìm phim của An có thể viết ngắn gọn theo mẫu đồ thị:

~~~cypher
MATCH (p:Person {name: 'An'})-[:ACTED_IN]->(m:Movie)
RETURN m.title AS title
ORDER BY title
~~~

Cypher mô tả mẫu node và relationship cần khớp. Khi cần tìm người từng đóng chung với An, ta tiếp tục đi qua node phim:

~~~cypher
MATCH (an:Person {name: 'An'})-[:ACTED_IN]->(m:Movie)<-[:ACTED_IN]-(colleague:Person)
WHERE colleague <> an
RETURN DISTINCT colleague.name AS name
ORDER BY name
~~~

Đường đi trong truy vấn phản ánh trực tiếp ý nghĩa nghiệp vụ: An tham gia một phim, và một diễn viên khác cũng tham gia phim đó. Khi số bước quan hệ thay đổi, Cypher có thể biểu diễn việc duyệt nhiều bước bằng các mẫu đường đi phù hợp.

## 2. Khác biệt cốt lõi giữa ba mô hình

| Khía cạnh | Quan hệ | Tài liệu | Đồ thị |
|---|---|---|---|
| Đơn vị lưu trữ chính | Hàng trong bảng | Tài liệu | Node và relationship |
| Cách biểu diễn liên kết | Khóa ngoại và bảng liên kết | Nhúng tài liệu con hoặc lưu tham chiếu | Relationship có kiểu và hướng |
| Truy vấn liên kết | `JOIN` giữa các bảng | Đọc trường lồng nhau, tra cứu hoặc kết hợp tài liệu | Khớp mẫu và duyệt đường đi |
| Cấu trúc dữ liệu | Thường có schema rõ ràng | Linh hoạt theo từng tài liệu | Nhãn, kiểu relationship và property |
| Trường hợp thường phù hợp | Giao dịch có cấu trúc, báo cáo, tổng hợp | Aggregate độc lập, dữ liệu lồng nhau, cấu trúc thay đổi | Quan hệ dày đặc, truy vấn nhiều bước, phân tích kết nối |

Điểm khác biệt quan trọng nhất của đồ thị là relationship được lưu và xử lý như thành phần hạng nhất. Trong mô hình quan hệ, liên kết được thể hiện gián tiếp qua giá trị khóa và phép nối. Trong mô hình tài liệu, liên kết thường được thể hiện bằng cấu trúc nhúng hoặc tham chiếu. Trong mô hình đồ thị, đường nối giữa các thực thể là một phần trực tiếp của cấu trúc dữ liệu.

Điều đó không làm cho đồ thị tự động nhanh hơn trong mọi tình huống. Một truy vấn lọc đơn giản trên một bảng có thể rất tự nhiên trong cơ sở dữ liệu quan hệ; đọc một tài liệu đã gom sẵn dữ liệu có thể rất hiệu quả trong cơ sở dữ liệu tài liệu. Lợi thế của đồ thị thường xuất hiện khi câu hỏi nghiệp vụ tập trung vào việc khám phá các mối liên hệ và đường đi qua nhiều thực thể.

## 3. Chọn mô hình theo cách ứng dụng sử dụng dữ liệu

Không nên chọn cơ sở dữ liệu chỉ vì cấu trúc dữ liệu trông giống một sơ đồ. Hãy bắt đầu từ các thao tác đọc, ghi và quy tắc nghiệp vụ quan trọng nhất.

**Chọn mô hình quan hệ khi** dữ liệu có cấu trúc ổn định, quan hệ và ràng buộc cần kiểm soát chặt, nhiều thao tác cập nhật cần giao dịch nhất quán, hoặc hệ thống thường chạy báo cáo và tổng hợp theo các chiều dữ liệu. Ví dụ điển hình là quản lý hóa đơn, thanh toán, tồn kho và các nghiệp vụ kế toán.

**Chọn mô hình tài liệu khi** ứng dụng thường tải hoặc cập nhật một đối tượng cùng các phần dữ liệu con của nó; cấu trúc giữa các đối tượng có thể khác nhau; và các truy vấn chủ yếu tập trung trong phạm vi một tài liệu hoặc aggregate. Ví dụ có thể là hồ sơ cấu hình, nội dung bài viết, hoặc dữ liệu sản phẩm có thuộc tính thay đổi theo nhóm hàng.

**Chọn mô hình đồ thị khi** mối quan hệ giữa các thực thể là trọng tâm của nghiệp vụ, và ứng dụng thường xuyên hỏi về kết nối trực tiếp, kết nối gián tiếp, đường đi hoặc các cụm liên kết. Ví dụ gồm mạng xã hội, gợi ý sản phẩm dựa trên hành vi và quan hệ, quản lý mạng lưới cung ứng, phát hiện gian lận qua các tài khoản liên quan, hoặc quản lý phụ thuộc giữa dịch vụ.

Một số câu hỏi giúp nhận diện bài toán có tính đồ thị:

1. Người dùng có thường hỏi “A liên quan đến ai/cái gì?” thay vì chỉ hỏi “bản ghi A có giá trị nào?” không?
2. Một kết quả có phụ thuộc vào nhiều bước liên kết, và số bước có thay đổi theo yêu cầu không?
3. Relationship có ý nghĩa nghiệp vụ riêng, có thuộc tính, loại hoặc hướng cần truy vấn không?
4. Những truy vấn quan trọng có thường xuyên tìm các thực thể chung, đường đi hoặc nhóm liên kết không?

Nếu phần lớn câu trả lời là có, mô hình đồ thị đáng được đánh giá. Nếu quan hệ chỉ là vài khóa ngoại đơn giản và truy vấn chủ yếu đọc từng thực thể, mô hình quan hệ có thể đáp ứng gọn hơn. Nếu dữ liệu thường được đọc theo từng tài liệu độc lập, mô hình tài liệu có thể phù hợp hơn.

## 4. Spring Data Neo4j ánh xạ mô hình đồ thị vào Java

Khi đã chọn Neo4j, Spring Data Neo4j (SDN) giúp ánh xạ node và relationship sang các lớp Java, đồng thời cung cấp repository và khả năng chạy Cypher. SDN không biến đồ thị thành các bảng quan hệ; các annotation mô tả cách đối tượng Java tương ứng với cấu trúc đồ thị.

Ví dụ, một diễn viên có thể tham gia nhiều phim. Ta biểu diễn `Person` và `Movie` bằng node, còn `ActingCredit` là lớp mô tả relationship `ACTED_IN` có thêm thuộc tính `role`:

~~~java
@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Relationship(type = "ACTED_IN", direction = Relationship.Direction.OUTGOING)
    private List<ActingCredit> actingCredits = new ArrayList<>();
}

@Node("Movie")
public class Movie {
    @Id
    @GeneratedValue
    private Long id;

    private String title;
}

@RelationshipProperties
public class ActingCredit {
    @RelationshipId
    private Long id;

    private String role;

    @TargetNode
    private Movie movie;
}
~~~

Các annotation chính có ý nghĩa như sau:

- `@Node` đánh dấu lớp được ánh xạ thành node; giá trị trong annotation là nhãn node.
- `@Id` xác định trường định danh của entity; `@GeneratedValue` yêu cầu SDN tạo giá trị định danh theo cơ chế được cấu hình.
- `@Relationship` khai báo kiểu và hướng relationship được ánh xạ vào thuộc tính của node.
- `@RelationshipProperties` đánh dấu lớp mô tả relationship có thuộc tính riêng.
- `@TargetNode` chỉ node ở đầu đích của relationship được mô tả.
- `@RelationshipId` là định danh nội bộ mà SDN dùng để nhận diện relationship entity.

Ví dụ trên tập trung minh họa cấu trúc ánh xạ; trong ứng dụng thực tế cần bổ sung constructor, getter/setter hoặc cơ chế truy cập phù hợp với cách tổ chức mã nguồn. Với định danh cần ổn định qua nhiều hệ thống hoặc lần xuất/nhập dữ liệu, hãy cân nhắc dùng mã định danh nghiệp vụ do ứng dụng quản lý thay vì phụ thuộc vào định danh nội bộ của cơ sở dữ liệu.

Repository cho phép thực hiện các thao tác phổ biến và khai báo truy vấn Cypher khi cần mô tả rõ đường đi trong đồ thị:

~~~java
public interface PersonRepository extends Neo4jRepository<Person, Long> {
    Optional<Person> findOneByName(String name);

    @Query("""
        MATCH (p:Person {name: $name})-[:ACTED_IN]->(m:Movie)
        RETURN m
        ORDER BY m.title
        """)
    List<Movie> findMoviesByActorName(String name);
}
~~~

Phương thức dẫn xuất như `findOneByName` phù hợp với truy vấn đơn giản theo thuộc tính. `@Query` hữu ích khi truy vấn phụ thuộc vào một mẫu relationship cụ thể, cần nhiều bước duyệt hoặc cần kiểm soát hình dạng kết quả. Tham số `$name` được truyền từ phương thức repository, giúp tách dữ liệu đầu vào khỏi chuỗi truy vấn.

Ở tầng dịch vụ, có thể gom nhiều thao tác đọc/ghi cần tính nhất quán vào một giao dịch Spring:

~~~java
@Service
public class FilmographyService {
    private final PersonRepository people;

    public FilmographyService(PersonRepository people) {
        this.people = people;
    }

    @Transactional(readOnly = true)
    public List<Movie> moviesOf(String actorName) {
        return people.findMoviesByActorName(actorName);
    }
}
~~~

`@Transactional` cho phép Spring quản lý ranh giới giao dịch theo cấu hình Neo4j của ứng dụng. Khi một nghiệp vụ gồm nhiều thao tác cần thành công hoặc thất bại cùng nhau, hãy đặt ranh giới giao dịch ở tầng dịch vụ để thể hiện trọn vẹn nghiệp vụ. Với truy vấn chỉ đọc, có thể đánh dấu `readOnly = true` khi phù hợp với cấu hình và mục đích của thao tác.

## 5. Lưu ý về hiệu năng và tính nhất quán

Mô hình đồ thị giúp diễn đạt các đường đi tự nhiên, nhưng hiệu năng vẫn phụ thuộc vào cách thiết kế và truy vấn. Một số nguyên tắc thực tế:

- **Định danh điểm bắt đầu hiệu quả.** Tạo index hoặc constraint cho các thuộc tính thường dùng để tìm node bắt đầu, chẳng hạn mã diễn viên hoặc email. Sau khi tìm được node bắt đầu, Neo4j có thể duyệt các relationship liên quan.
- **Giới hạn phạm vi duyệt.** Chỉ khớp các kiểu relationship, nhãn và độ sâu cần thiết. Tránh truy vấn đường đi không giới hạn trên đồ thị lớn nếu nghiệp vụ không yêu cầu.
- **Chú ý node có bậc kết nối rất cao.** Một node có hàng triệu relationship có thể làm truy vấn mở rộng quá nhiều nhánh. Hãy xem xét bộ lọc, hướng relationship, giới hạn độ sâu và cách chia nhỏ truy vấn.
- **Chỉ tải dữ liệu cần dùng.** Ánh xạ một entity cùng nhiều relationship có thể tạo đồ thị đối tượng lớn. Với màn hình hoặc API chỉ cần vài trường, cân nhắc projection hoặc truy vấn Cypher trả về đúng dữ liệu cần thiết.
- **Kiểm tra kế hoạch thực thi.** Dùng `EXPLAIN` để xem kế hoạch và `PROFILE` để đo các thao tác thực tế trên dữ liệu đại diện. Đánh giá bằng số lượng node/relationship được duyệt và thời gian thực thi, không chỉ bằng độ ngắn của câu Cypher.
- **Đặt quy tắc toàn vẹn ở đúng nơi.** Dùng constraint của Neo4j cho các yêu cầu như tính duy nhất của mã nghiệp vụ; kiểm tra quy tắc nhiều thực thể hoặc quy tắc phức tạp ở tầng nghiệp vụ khi constraint không diễn đạt được.

Trong hệ thống thực tế, các mô hình có thể cùng tồn tại. Một dịch vụ có thể dùng cơ sở dữ liệu quan hệ cho giao dịch tài chính, cơ sở dữ liệu tài liệu cho nội dung linh hoạt và Neo4j cho các truy vấn quan hệ nhiều bước. Cách kết hợp này làm tăng yêu cầu đồng bộ và vận hành dữ liệu, vì vậy chỉ nên áp dụng khi lợi ích truy vấn hoặc mô hình nghiệp vụ đủ rõ.

## 6. Kết luận

Mô hình quan hệ tổ chức dữ liệu quanh bảng và khóa; mô hình tài liệu tổ chức dữ liệu quanh tài liệu hoặc aggregate; mô hình đồ thị tổ chức dữ liệu quanh node và relationship. Mỗi mô hình giải quyết tốt một nhóm kiểu truy cập khác nhau.

Với Spring Data Neo4j, hãy bắt đầu bằng việc xác định thực thể nào là node, mối liên kết nào cần trở thành relationship và thuộc tính nào thuộc về node hay relationship. Sau đó chọn repository cho thao tác đơn giản, dùng Cypher cho truy vấn đường đi cụ thể, quản lý giao dịch ở tầng dịch vụ và đo kế hoạch thực thi trên dữ liệu gần với thực tế. Cách tiếp cận này giúp mô hình đồ thị phản ánh đúng nghiệp vụ thay vì chỉ chuyển nguyên cấu trúc bảng hoặc tài liệu sang Neo4j.
