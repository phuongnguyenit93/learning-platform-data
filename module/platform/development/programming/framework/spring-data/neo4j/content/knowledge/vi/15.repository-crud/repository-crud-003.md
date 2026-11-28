# save, saveAll và ý nghĩa đối tượng trả về

Trong Spring Data Neo4j (SDN), `save` và `saveAll` là hai thao tác repository cơ bản để ghi entity vào Neo4j. `save` nhận một entity và trả về entity đã lưu; `saveAll` nhận một tập entity và trả về các entity tương ứng sau khi lưu. Giá trị trả về rất quan trọng vì SDN có thể tạo một instance mới, đặc biệt khi entity bất biến cần nhận ID được sinh tự động.

Vì vậy, hãy luôn giữ kết quả của `save` hoặc `saveAll`. Đừng giả định object đầu vào luôn được sửa tại chỗ, và cũng đừng hiểu `saveAll` là cam kết rằng toàn bộ dữ liệu được ghi bằng một câu Cypher duy nhất. Muốn kiểm soát tính nguyên tử, hãy xác định ranh giới transaction ở tầng service; muốn tối ưu lô lớn, hãy đo truy vấn thực tế và chọn cách ghi phù hợp.

## 1. Repository cung cấp save và saveAll

Repository imperative thường kế thừa `Neo4jRepository`:

```java
public interface MovieRepository extends Neo4jRepository<Movie, Long> {
}
```

`Neo4jRepository<Movie, Long>` khai báo repository quản lý entity `Movie` với kiểu ID `Long`. Các phương thức ghi phổ biến được kế thừa từ Spring Data repository:

```java
<S extends T> S save(S entity);

<S extends T> Iterable<S> saveAll(Iterable<S> entities);
```

Với repository trên, `T` là `Movie`. `save` trả về một entity cùng kiểu cụ thể `S`; `saveAll` trả về `Iterable<S>`. Đây là các entity đã qua quá trình lưu và có thể là những instance khác với object đầu vào.

| Phương thức | Đầu vào | Kết quả | Trường hợp dùng |
|---|---|---|---|
| `save(entity)` | Một entity | Entity đã lưu | Tạo hoặc cập nhật một đối tượng miền |
| `saveAll(entities)` | Một `Iterable` entity | `Iterable` các entity đã lưu | Ghi một nhóm entity cùng loại |

Hai phương thức này là API ghi theo entity. Chúng không thay thế câu truy vấn Cypher chuyên biệt khi cần cập nhật một vài property, tổng hợp dữ liệu hoặc ghi khối lượng lớn theo một cấu trúc riêng.

## 2. save: giữ lại entity được trả về

Ví dụ entity dùng ID nội bộ Neo4j được sinh tự động:

```java
@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    public Movie(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Ghi entity mới:

```java
Movie input = new Movie("The Graph Journey");

Movie saved = movieRepository.save(input);
Long movieId = saved.getId();

System.out.println("Saved movie ID: " + movieId);
```

`@Id` đánh dấu property định danh và `@GeneratedValue` yêu cầu SDN sinh giá trị ID theo cấu hình. `saved` là kết quả cần dùng cho các bước tiếp theo. Với entity mutable, SDN có thể gán ID vào instance đầu vào. Với entity immutable, SDN có thể trả về instance mới chứa ID; `input.getId()` khi đó vẫn có thể là `null`.

Có thể dùng ID từ entity trả về để truy vấn lại:

```java
Movie loaded = movieRepository.findById(saved.getId())
        .orElseThrow(() -> new IllegalArgumentException("Movie not found"));
```

Không viết theo kiểu bỏ kết quả:

```java
movieRepository.save(input);
Long movieId = input.getId(); // Không an toàn với entity immutable
```

Thói quen gán kết quả vào biến giúp code hoạt động đúng với cả entity mutable lẫn immutable, đồng thời làm rõ rằng ID và trạng thái mapping cần đọc từ đối tượng đã lưu.

## 3. save có nghĩa là tạo mới hay cập nhật?

Tên `save` bao hàm cả việc tạo entity mới và cập nhật entity đã tồn tại. SDN cần xác định trạng thái mới/cũ của entity trước khi chọn cách ghi.

Với ID được sinh và chưa có giá trị, entity thường được nhận diện là mới. Sau khi lưu, entity có ID và lần lưu tiếp theo có thể được xử lý như thao tác cập nhật. Nếu ứng dụng tự gán ID trước khi lưu, cần đặc biệt chú ý cách Spring Data nhận diện trạng thái mới.

### Entity dùng ID được sinh

```java
@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
}
```

Khi `id` chưa có, SDN có thể xem entity là mới và tạo node. Khi entity đã có ID, thao tác `save` ghi trạng thái entity theo mapping của SDN.

### Entity dùng business ID do ứng dụng cấp

```java
@Node("Movie")
public class Movie {

    @Id
    private String id;

    @Version
    private Long version;

    private String title;
}
```

Nếu ID đã được gán trước khi gọi `save`, chỉ nhìn vào ID sẽ không đủ để phân biệt entity mới với entity đã tồn tại. Trường `@Version` nullable cho phép Spring Data nhận diện trạng thái mới thông qua version chưa được khởi tạo; SDN quản lý việc gán và tăng version. Không tự gán hoặc tăng `version` trong code nghiệp vụ.

Sau khi entity đã tồn tại, version được dùng cho optimistic locking. Nếu một transaction khác cập nhật entity trước, thao tác lưu dựa trên version cũ có thể thất bại thay vì âm thầm ghi đè dữ liệu mới.

Nếu dùng business ID, nên tạo unique constraint tương ứng trong Neo4j:

```cypher
CREATE CONSTRAINT movie_id IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.id IS UNIQUE;
```

Unique constraint bảo vệ tính duy nhất ở tầng database. Nó không thay thế cơ chế nhận diện entity mới/cũ của SDN.

## 4. Ý nghĩa đối tượng trả về với entity bất biến

Entity bất biến không cho phép thay đổi field sau khi khởi tạo. Khi SDN sinh ID, nó cần một cách tạo instance mới có ID vừa nhận. Một class có thể cung cấp wither:

```java
@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private final Long id;

    private final String title;

    public Movie(String title) {
        this(null, title);
    }

    @PersistenceCreator
    public Movie(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Movie withId(Long id) {
        return new Movie(id, title);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

`withId` trả về một instance mới, giữ nguyên `title` và nhận ID mới. `@PersistenceCreator` chỉ rõ constructor được dùng để khởi tạo entity từ dữ liệu đọc. Khi lưu:

```java
Movie input = new Movie("The Graph Journey");
Movie saved = movieRepository.save(input);

Long id = saved.getId();
// input vẫn có thể giữ id == null
```

Nếu tiếp tục truyền `input` vào một thao tác khác, ứng dụng có thể làm mất ID vừa sinh hoặc khiến SDN xem object như một entity mới. Dùng `saved` hoặc ID lấy từ `saved`.

Với Java record, nguyên tắc tương tự nhưng accessor là tên component:

```java
@Node("Movie")
public record Movie(
        @Id @GeneratedValue Long id,
        String title) {

    public Movie withId(Long id) {
        return new Movie(id, title);
    }
}
```

```java
Movie saved = movieRepository.save(new Movie(null, "The Graph Journey"));
Long id = saved.id();
```

Điểm cốt lõi của `save` không phải object đầu vào có bị sửa hay không; đó là repository trả về entity biểu diễn kết quả lưu. Luôn sử dụng giá trị trả về để code không phụ thuộc vào cách SDN tạo object.

## 5. saveAll: ghi một nhóm entity

Khi có nhiều phim cần lưu, dùng `saveAll`:

```java
List<Movie> input = List.of(
        new Movie("The Graph Journey"),
        new Movie("Neo4j in Practice"),
        new Movie("Connected Worlds")
);

Iterable<Movie> savedMovies = movieRepository.saveAll(input);

for (Movie movie : savedMovies) {
    System.out.println(movie.getId() + " - " + movie.getTitle());
}
```

`saveAll` trả về `Iterable<Movie>`, vì vậy có thể duyệt kết quả để lấy ID, ghi log hoặc tạo DTO. Đừng giả định từng phần tử trả về luôn chính là cùng object tham chiếu trong danh sách `input`; quy tắc dùng entity trả về cũng áp dụng cho từng phần tử.

Nếu cần danh sách để xử lý tiếp, có thể chuyển kết quả thành `List`:

```java
List<Movie> savedList = StreamSupport
        .stream(savedMovies.spliterator(), false)
        .toList();
```

Ví dụ dùng `StreamSupport` của Java và `toList()` của các phiên bản Java hỗ trợ phương thức này. Với phiên bản Java cũ hơn, có thể thu thập bằng `Collectors.toList()`.

### Kiểm tra đầu vào và kết quả

- `entities` phải là một `Iterable` hợp lệ; không truyền `null`.
- Không đưa phần tử `null` vào iterable.
- Iterable rỗng không có entity nào để lưu; ứng dụng có thể xử lý kết quả rỗng như một trường hợp hợp lệ.
- Kết quả là `Iterable` entity đã lưu, không phải danh sách ID.
- Nếu cần ID, hãy duyệt các entity trả về và đọc ID theo accessor hoặc getter tương ứng.

Ví dụ tạo danh sách ID:

```java
Iterable<Movie> saved = movieRepository.saveAll(input);

List<Long> ids = StreamSupport.stream(saved.spliterator(), false)
        .map(Movie::getId)
        .toList();
```

Nếu entity dùng UUID kiểu `String`, đổi kiểu danh sách thành `List<String>` và dùng `Movie::getId` tương ứng.

## 6. saveAll không đồng nghĩa một câu lệnh bulk Cypher

`saveAll` là abstraction của Spring Data cho việc lưu nhiều entity. Tên phương thức không cam kết rằng SDN sẽ tạo một câu Cypher duy nhất, một round-trip mạng duy nhất hoặc một cơ chế bulk insert cụ thể. Cách triển khai và số câu lệnh phụ thuộc phiên bản SDN, cấu trúc entity, relationship cần ghi và driver.

Vì vậy, cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Gọi `saveAll` | Gửi một nhóm entity qua API repository |
| Bulk query | Một truy vấn Cypher xử lý nhiều hàng dữ liệu, thường dùng `UNWIND` |
| Batch/chunk | Chia dữ liệu lớn thành nhiều nhóm có kích thước kiểm soát |
| Transaction | Xác định phạm vi các thao tác cùng commit hoặc rollback |

Nếu dữ liệu có vài chục entity và cần mapping quan hệ theo mô hình miền, `saveAll` thường là API dễ dùng. Nếu cần ghi hàng trăm nghìn hoặc hàng triệu dòng, hãy đo thời gian, bộ nhớ, số round-trip và kích thước transaction trên dữ liệu đại diện. Có thể dùng `Neo4jClient` hoặc driver để thực thi Cypher dạng `UNWIND`:

```cypher
UNWIND $rows AS row
MERGE (m:Movie {id: row.id})
SET m.title = row.title,
    m.releaseYear = row.releaseYear;
```

Truy vấn này nhận danh sách map qua tham số `$rows`, rồi xử lý từng map trong một lần thực thi Cypher. `MERGE` được chọn theo business ID; cần unique constraint trên `Movie.id` để bảo vệ tính duy nhất. Cách ghi này phù hợp với dữ liệu phẳng và có thể kiểm soát trực tiếp, nhưng ứng dụng phải tự chịu trách nhiệm mapping, validation, quan hệ và semantics cập nhật.

Không nên thay repository bằng bulk Cypher chỉ vì muốn giảm số lời gọi. Hãy chọn theo nhu cầu: mapping entity và relationship phong phú, hay kiểm soát trực tiếp một phép ghi tập trung.

## 7. Transaction khi dùng save và saveAll

Các thao tác CRUD của Spring Data Neo4j được thực thi trong transaction do transaction manager quản lý. Khi một nghiệp vụ gồm nhiều thao tác repository và cần tất cả cùng thành công hoặc cùng thất bại, đặt `@Transactional` ở service để tạo ranh giới nghiệp vụ rõ ràng.

```java
@Service
public class CatalogService {

    private final MovieRepository movieRepository;
    private final ActorRepository actorRepository;

    public CatalogService(
            MovieRepository movieRepository,
            ActorRepository actorRepository) {
        this.movieRepository = movieRepository;
        this.actorRepository = actorRepository;
    }

    @Transactional
    public List<Movie> importMovies(List<Movie> movies) {
        Iterable<Movie> saved = movieRepository.saveAll(movies);

        List<Movie> result = StreamSupport
                .stream(saved.spliterator(), false)
                .toList();

        // Các thao tác repository tiếp theo trong service
        // có thể tham gia cùng transaction.
        return result;
    }
}
```

Ví dụ cho thấy ranh giới transaction ở service. Nếu trong cùng phương thức có thêm thao tác lưu diễn viên, các thao tác repository dùng cùng transaction manager có thể tham gia cùng transaction đó. Khi một lỗi làm transaction rollback, thay đổi trong transaction cũng bị rollback.

Một lời gọi `saveAll` có thể tự chạy theo transaction cấu hình cho phương thức repository. Tuy nhiên, nếu nghiệp vụ gồm nhiều lời gọi repository hoặc cập nhật thêm dữ liệu khác, không nên để mỗi thao tác có ranh giới commit độc lập. Hãy đặt `@Transactional` ở service để thể hiện rõ toàn bộ đơn vị công việc.

ID đã được gán trong object trước khi transaction commit không chứng minh dữ liệu đã bền vững. Nếu commit thất bại, caller không nên trả response thành công chỉ vì đã đọc được ID từ object trong bộ nhớ.

### Lô lớn và thời gian transaction

Một transaction quá lớn có thể giữ tài nguyên lâu, tăng lượng dữ liệu phải rollback và ảnh hưởng các thao tác đồng thời. Với nhập dữ liệu lớn, cân nhắc chia thành chunk:

```java
for (List<Movie> chunk : partition(movies, 500)) {
    catalogService.importMovieChunk(chunk);
}
```

`partition` là hàm minh họa chia danh sách thành các nhóm có tối đa 500 phần tử; cần triển khai theo thư viện hoặc tiện ích của ứng dụng. Mỗi lời gọi `importMovieChunk` có thể là một transaction riêng nếu được đặt `@Transactional` ở service proxy. Chọn kích thước chunk dựa trên benchmark và giới hạn tài nguyên, không mặc định 500 là tối ưu cho mọi hệ thống.

## 8. saveAll và relationship trong entity graph

SDN ánh xạ không chỉ property của node mà còn relationship được khai báo trong entity. Khi lưu entity có trường `@Relationship`, SDN xử lý phần đồ thị thuộc mapping của entity đó theo trạng thái object.

Ví dụ `Movie` có danh sách diễn viên:

```java
@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @Relationship(type = "FEATURES", direction = Relationship.Direction.OUTGOING)
    private Set<Actor> actors = new HashSet<>();
}
```

Khi lưu nhiều phim bằng `saveAll`, SDN cần xử lý các node và relationship được mô hình hóa trong từng entity. Điều đó không có nghĩa mọi node có thể đi tới trong toàn graph đều tự động được tải hoặc ghi. Kết quả phụ thuộc vào entity mapping và dữ liệu có trong object.

Đặc biệt, tránh lấy một projection hoặc entity chỉ được tải một phần, rồi dùng `save`/`saveAll` như thể nó là toàn bộ aggregate. Các relationship không có trong object có thể dẫn đến kết quả đồng bộ không như mong muốn. Dùng projection cho truy vấn chỉ đọc; khi cập nhật aggregate, tải đủ phần dữ liệu mà thao tác cần quản lý.

## 9. save và saveAll trong reactive SDN

Reactive repository có chữ ký trả về publisher thay vì kết quả đồng bộ. Thường gặp:

```java
Mono<Movie> save(Movie entity);

<S extends Movie> Flux<S> saveAll(Iterable<S> entities);
```

Ví dụ đọc ID từ entity sau khi lưu:

```java
public Mono<Long> createMovie(String title) {
    return reactiveMovieRepository.save(new Movie(title))
            .map(Movie::getId);
}
```

Với nhiều entity:

```java
public Flux<Long> createMovies(List<Movie> movies) {
    return reactiveMovieRepository.saveAll(movies)
            .map(Movie::getId);
}
```

Publisher chỉ thực thi khi có subscriber. Hãy nối xử lý ID bằng `map`, `flatMap` hoặc toán tử reactive phù hợp. Không gọi `.block()` hay tự `subscribe()` trong service reactive thông thường chỉ để lấy ID; điều đó làm đứt chuỗi non-blocking và có thể gây lỗi trên event loop.

Reactive transaction sử dụng `ReactiveNeo4jTransactionManager` và transaction context của Reactor. Không trộn imperative repository với reactive flow nếu chưa thiết kế rõ cách chuyển đổi và ranh giới transaction.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi `save` nhưng bỏ qua giá trị trả về | Mất ID hoặc state mới của entity immutable | Gán và dùng entity trả về |
| Dùng object đầu vào để lấy ID | Có thể đọc `null` với entity bất biến | Đọc ID trên kết quả `save` |
| Nghĩ `save` chỉ tạo mới | Không hiểu đúng thao tác lưu entity hiện hữu | Nắm cơ chế xác định newness và `@Version` |
| Gán business ID nhưng không thiết kế newness | Entity mới có thể bị xử lý như entity đã tồn tại | Dùng `@Version` nullable và unique constraint phù hợp |
| Cho rằng `saveAll` trả về danh sách ID | Sai kiểu kết quả và bỏ qua entity đã lưu | Duyệt `Iterable` rồi lấy ID từ từng entity |
| Cho rằng `saveAll` luôn là một bulk query | Kỳ vọng hiệu năng không có trong hợp đồng API | Đo thực tế; dùng `UNWIND` khi cần bulk Cypher có kiểm soát |
| Lưu aggregate chỉ được tải một phần | Có thể làm sai property hoặc relationship | Dùng projection cho đọc và tải đủ aggregate khi ghi |
| Chia một nghiệp vụ thành nhiều transaction độc lập | Một phần nghiệp vụ có thể commit khi phần khác thất bại | Đặt `@Transactional` ở service |
| Gọi `.block()` trong reactive service | Chặn luồng xử lý | Dùng pipeline `Mono`/`Flux` |

## 11. Checklist trước khi dùng save hoặc saveAll

1. Repository đã khai báo đúng entity type và ID type chưa?
2. Entity dùng ID được sinh hay business ID do ứng dụng cấp?
3. Nếu entity bất biến, đã có wither phù hợp và code có giữ kết quả `save` chưa?
4. Nếu dùng business ID, SDN có đủ thông tin để nhận diện entity mới/cũ, chẳng hạn `@Version` nullable, chưa?
5. `saveAll` có nhận iterable không chứa `null` và kết quả đã được xử lý đúng chưa?
6. Nghiệp vụ có cần nhiều thao tác cùng commit hoặc rollback không? Nếu có, transaction đã đặt ở service chưa?
7. Entity graph có chứa đầy đủ các property và relationship mà thao tác ghi cần quản lý không?
8. Với lô lớn, đã đo số truy vấn, thời gian, bộ nhớ và kích thước transaction chưa?
9. Nếu dùng reactive repository, xử lý kết quả có giữ nguyên pipeline non-blocking không?

## 12. Tự kiểm tra

1. `save` trả về entity hay ID? Vì sao nên giữ đối tượng trả về?
2. Khác biệt trong việc nhận ID giữa entity mutable và immutable là gì?
3. Vì sao `@Version` hữu ích khi entity dùng business ID được gán trước?
4. `saveAll` nhận kiểu đầu vào và trả về kiểu kết quả nào?
5. Có thể suy ra `saveAll` luôn thực thi một câu Cypher duy nhất không? Vì sao?
6. Khi nào cần đặt `@Transactional` ở service thay vì chỉ dựa vào transaction của repository?
7. Vì sao không nên lưu một entity được tạo từ projection chỉ đọc một phần?
8. Cách lấy ID từ kết quả `saveAll` trong reactive repository khác gì so với repository imperative?

Khi hiểu đúng `save`, `saveAll` và ý nghĩa của entity trả về, người học có thể ghi một hoặc nhiều node qua repository, nhận đúng ID được sinh, kiểm soát transaction và chọn cách ghi phù hợp với kích thước dữ liệu trong ứng dụng Spring Data Neo4j.
