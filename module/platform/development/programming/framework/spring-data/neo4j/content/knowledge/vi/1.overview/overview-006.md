# Khi nào dùng repository, Neo4jTemplate, Neo4jClient hoặc driver trực tiếp?

Spring Data Neo4j (SDN) cung cấp nhiều cách truy cập Neo4j vì mỗi ứng dụng có mức độ phức tạp khác nhau. Có lúc ta chỉ cần lưu và tải một node entity; có lúc cần thực hiện một truy vấn Cypher nhiều nhánh rồi ánh xạ kết quả thành DTO; cũng có lúc phải kiểm soát trực tiếp session hoặc transaction của Neo4j Java Driver.

Bốn lựa chọn thường gặp là repository, `Neo4jTemplate`, `Neo4jClient` và driver trực tiếp. Chúng không phải bốn cách thay thế hoàn toàn cho nhau. Điểm quyết định là tầng ứng dụng cần làm việc với entity đã được SDN ánh xạ, cần viết Cypher linh hoạt, hay cần quyền điều khiển ở mức driver.

## Bảng chọn nhanh

| Lựa chọn | Dùng khi | Điểm mạnh | Điều cần cân nhắc |
| --- | --- | --- | --- |
| Repository | Nghiệp vụ xoay quanh aggregate/entity và các thao tác CRUD hoặc truy vấn có cấu trúc ổn định | API khai báo, dễ đọc, tích hợp sẵn với mô hình entity và transaction của Spring | Không phù hợp để nhồi nhiều truy vấn động hoặc xử lý kết quả Cypher tùy biến phức tạp |
| `Neo4jTemplate` | Cần thao tác lập trình với entity nhưng repository không diễn đạt được luồng xử lý | Dùng mapping context của SDN khi lưu, tìm và quản lý entity | Không phải lựa chọn thuận tiện nhất để đọc từng cột hoặc ánh xạ một kết quả báo cáo tùy ý |
| `Neo4jClient` | Cần kiểm soát Cypher và hình dạng kết quả, chẳng hạn projection, thống kê hoặc DTO | API truy vấn linh hoạt, bind tham số và ánh xạ từng record | Người viết truy vấn chịu trách nhiệm rõ ràng về cấu trúc Cypher và mapping kết quả |
| Neo4j Java Driver trực tiếp | Cần API mức thấp của driver hoặc cần tự kiểm soát session/transaction | Toàn quyền dùng các khả năng của driver | Phải tự quản lý vòng đời session, cách ánh xạ dữ liệu và sự phối hợp với transaction Spring |

Với phần lớn nghiệp vụ thông thường, hãy bắt đầu bằng repository. Chỉ chuyển xuống abstraction thấp hơn khi yêu cầu cụ thể cho thấy repository không còn diễn đạt rõ ràng hoặc không cung cấp đủ quyền kiểm soát.

## 1. Repository: lựa chọn mặc định cho thao tác theo entity

Repository phù hợp khi một thao tác nghiệp vụ có thể mô tả bằng các hành động trên entity hoặc aggregate root: tạo, lưu, tìm theo ID, xóa, phân trang, sắp xếp và truy vấn theo thuộc tính. SDN cung cấp `Neo4jRepository` để kết hợp các thao tác CRUD với cơ chế ánh xạ node và relationship.

Ví dụ, giả sử ứng dụng quản lý phim và diễn viên. `Movie` là node entity, còn quan hệ `ACTED_IN` nối `Person` với `Movie`:

```java
public interface MovieRepository extends Neo4jRepository<Movie, String> {

    List<Movie> findByTitleContaining(String fragment);

    @Query("""
        MATCH (m:Movie)<-[:ACTED_IN]-(p:Person {name: $personName})
        RETURN DISTINCT m
        ORDER BY m.released DESC
        """)
    List<Movie> findMoviesForActor(@Param("personName") String personName);
}
```

`findByTitleContaining` là truy vấn được suy ra từ tên phương thức và thuộc tính entity. Với truy vấn có cấu trúc Cypher ổn định, `@Query` cho phép viết rõ đường đi trong đồ thị và trả về node `m` để SDN ánh xạ thành `Movie`.

Chọn repository khi:

- Phần lớn phương thức phục vụ một entity hoặc aggregate root cụ thể.
- Truy vấn dựa trên thuộc tính entity, hoặc có một câu Cypher cố định, dễ đặt tên và kiểm thử.
- Kết quả mong muốn chủ yếu là entity hoặc projection có cấu trúc ổn định.
- Muốn giữ tầng persistence dễ đọc và để Spring quản lý việc tích hợp repository.

Repository không có nghĩa là mọi truy vấn phải được suy ra từ tên phương thức. `@Query` xử lý được nhiều trường hợp Cypher tùy chỉnh. Tuy vậy, nếu truy vấn thay đổi theo nhiều điều kiện lúc chạy, trả về một cấu trúc dữ liệu hoàn toàn khác entity, hoặc cần phối hợp nhiều thao tác truy vấn, hãy cân nhắc custom repository fragment dùng `Neo4jTemplate` hoặc `Neo4jClient`. Cách đó thường làm rõ trách nhiệm hơn một interface chứa quá nhiều phương thức đặc biệt.

## 2. `Neo4jTemplate`: thao tác entity bằng mã lệnh

`Neo4jTemplate` phù hợp khi vẫn muốn tận dụng mapping context của SDN nhưng cần điều khiển luồng persistence bằng mã Java. Nó cung cấp các thao tác như lưu entity và tìm entity theo ID; SDN xử lý việc chuyển đổi giữa đối tượng Java với dữ liệu node và relationship theo metadata đã khai báo.

Ví dụ, một service có thể nhận entity từ nhiều bước xử lý rồi lưu hoặc tải entity theo một nhánh nghiệp vụ:

```java
@Service
public class MovieCatalog {

    private final Neo4jTemplate neo4jTemplate;

    public MovieCatalog(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    public Movie save(Movie movie) {
        return neo4jTemplate.save(movie);
    }

    public Optional<Movie> findById(String id) {
        return neo4jTemplate.findById(id, Movie.class);
    }
}
```

Trong ví dụ này, service không cần tự viết câu lệnh Cypher để lưu `Movie`. Template sử dụng metadata của entity để thực hiện thao tác persistence. Điều này hữu ích khi thao tác được quyết định trong một service hoặc trong phần triển khai custom repository, thay vì phù hợp với một phương thức repository cố định.

Chọn `Neo4jTemplate` khi:

- Cần thực hiện thao tác entity theo từng bước hoặc theo điều kiện trong mã Java.
- Muốn dùng mapping và metadata của SDN để lưu, tìm hoặc xử lý entity.
- Đang triển khai custom repository fragment và muốn cung cấp một API hướng entity cho phần còn lại của ứng dụng.

Nếu yêu cầu chính là chạy một câu Cypher tùy biến và đọc các cột kết quả, `Neo4jClient` thường diễn đạt ý định trực tiếp hơn. Template cũng không tự làm cho một mô hình entity trở thành mô hình đồ thị tốt: vẫn cần khai báo node, ID và relationship phù hợp với miền nghiệp vụ.

## 3. `Neo4jClient`: kiểm soát Cypher và ánh xạ kết quả

`Neo4jClient` là lựa chọn phù hợp khi Cypher là phần quan trọng của thao tác. Nó cho phép bind tham số, thực thi câu truy vấn và ánh xạ từng record sang kiểu kết quả mong muốn. Đây là cách hữu ích cho truy vấn đi qua nhiều loại node hoặc relationship, truy vấn tổng hợp, báo cáo và projection không cần tải toàn bộ entity.

Ví dụ, màn hình thống kê cần tên phim cùng số diễn viên tham gia. Kết quả này là một DTO, không nhất thiết phải là một `Movie` entity:

```java
public record MovieStats(String title, long actorCount) {}
```

```java
@Service
public class MovieStatistics {

    private final Neo4jClient neo4jClient;

    public MovieStatistics(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Collection<MovieStats> findMovieStats() {
        return neo4jClient.query("""
                MATCH (m:Movie)
                OPTIONAL MATCH (p:Person)-[:ACTED_IN]->(m)
                RETURN m.title AS title, count(p) AS actorCount
                ORDER BY actorCount DESC
                """)
            .fetchAs(MovieStats.class)
            .mappedBy((typeSystem, record) -> new MovieStats(
                record.get("title").asString(),
                record.get("actorCount").asLong()
            ))
            .all();
    }
}
```

`OPTIONAL MATCH` giữ lại cả phim chưa có diễn viên; `count(p)` trả về số diễn viên tìm được. `mappedBy` nêu rõ cách chuyển từng record thành `MovieStats`. Nhờ vậy, truy vấn chỉ trả về hai giá trị mà màn hình cần thay vì tải cả đồ thị entity liên quan.

Khi cần truyền giá trị đầu vào, hãy bind chúng thành tham số Cypher:

```java
neo4jClient.query("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WHERE p.name = $personName
        RETURN m.title AS title
        """)
    .bind(personName).to("personName")
    .fetchAs(String.class)
    .mappedBy((typeSystem, record) -> record.get("title").asString())
    .all();
```

Bind tham số giúp tách dữ liệu đầu vào khỏi câu truy vấn và tránh ghép trực tiếp dữ liệu người dùng vào chuỗi Cypher. Tham số phù hợp cho giá trị như tên, ID, ngày hoặc ngưỡng số. Nếu cần thay đổi cấu trúc câu truy vấn, chẳng hạn tên label hoặc relationship type, hãy giới hạn lựa chọn bằng danh sách cho phép và kiểm tra đầu vào; không xem các thành phần cấu trúc đó như giá trị tham số thông thường.

Chọn `Neo4jClient` khi:

- Truy vấn cần nhiều bước `MATCH`, `OPTIONAL MATCH`, `WITH`, `UNWIND` hoặc phép tổng hợp.
- Kết quả là scalar, map hoặc DTO được tạo từ nhiều trường.
- Cần xây dựng truy vấn theo tham số nghiệp vụ và muốn kiểm soát rõ câu Cypher được gửi đi.
- Muốn tránh tải một graph entity lớn trong khi chỉ cần một phần dữ liệu cho API hoặc báo cáo.

Nếu nhiều truy vấn client cùng phục vụ một khái niệm nghiệp vụ, hãy đặt chúng sau một custom repository hoặc một service chuyên trách. Điều này giữ Cypher tập trung và giúp lớp gọi không phải biết chi tiết cấu trúc đồ thị.

## 4. Neo4j Java Driver trực tiếp: khi cần quyền điều khiển mức thấp

SDN được xây dựng trên Neo4j Java Driver. Trong ứng dụng Spring, `Neo4jClient` thường đã cung cấp đủ khả năng chạy Cypher mà vẫn hòa hợp với cấu hình và transaction của Spring. Chỉ nên dùng `Driver` trực tiếp khi một yêu cầu cụ thể cần API mức thấp mà các abstraction của SDN không diễn đạt thuận tiện, hoặc khi truy cập Neo4j nằm ngoài luồng persistence thông thường của SDN.

Ví dụ sau dùng API transaction function của Java Driver 5.x để đọc kết quả:

```java
public List<String> findPersonNames(Driver driver, String name) {
    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.executeRead(tx ->
            tx.run("""
                    MATCH (p:Person)
                    WHERE p.name = $name
                    RETURN p.name AS name
                    """, Map.of("name", name))
                .list(record -> record.get("name").asString())
        );
    }
}
```

Đoạn mã làm việc trực tiếp với `Session`, `Transaction` và `Record`. Vì không đi qua mapping của SDN, ứng dụng tự quyết định cách đọc từng `Value` và chuyển đổi kết quả. API cụ thể có thể khác giữa các phiên bản Java Driver; hãy đối chiếu ví dụ với phiên bản mà dự án đang sử dụng.

Chọn driver trực tiếp khi:

- Cần kiểm soát chi tiết cấu hình session, transaction hoặc những khả năng riêng của Java Driver.
- Có mã tích hợp Neo4j độc lập với mô hình entity và repository của SDN.
- Đang xây dựng một thành phần hạ tầng mức thấp, nơi việc tự ánh xạ và quản lý tài nguyên là chủ đích rõ ràng.

Driver là đối tượng dùng chung lâu dài và thread-safe; `Session` không nên được chia sẻ đồng thời giữa nhiều luồng và cần được đóng sau khi sử dụng. Trong Spring, hãy inject `Driver` đã được cấu hình thay vì tạo driver mới cho từng request. Mỗi session và transaction mở trực tiếp đều cần có vòng đời được quản lý rõ ràng.

Đặc biệt, đừng mặc định một transaction được mở trực tiếp bằng driver sẽ tự động tham gia transaction do `@Transactional` của Spring quản lý. Nếu một nghiệp vụ trộn thao tác repository/template/client với session tự mở, hãy xác định rõ chúng có cùng transaction hay không. Nếu không, một phần thao tác có thể commit trong khi phần còn lại rollback. Khi cần một transaction Spring thống nhất, ưu tiên repository, `Neo4jTemplate` hoặc `Neo4jClient` được cấu hình cùng `Neo4jTransactionManager`; chỉ dùng session trực tiếp khi đã thiết kế và xác minh rõ cách phối hợp transaction.

## 5. Chọn theo tình huống nghiệp vụ

Có thể áp dụng thứ tự quyết định sau:

1. **Thao tác chủ yếu trên entity hoặc aggregate root?** Dùng repository. Bắt đầu bằng CRUD và derived query; thêm `@Query` cho Cypher tĩnh, dễ hiểu.
2. **Cần thao tác entity bằng một luồng Java linh hoạt?** Dùng `Neo4jTemplate` để tiếp tục tận dụng mapping của SDN.
3. **Cần truy vấn đồ thị tùy biến hoặc kết quả không phải entity?** Dùng `Neo4jClient` để viết Cypher, bind tham số và ánh xạ record sang DTO.
4. **Cần API session/transaction mức thấp của driver?** Dùng Java Driver trực tiếp, đồng thời chịu trách nhiệm rõ ràng về tài nguyên, mapping và transaction.

Một ứng dụng có thể dùng nhiều lựa chọn. Ví dụ, `MovieRepository` phục vụ thao tác CRUD; `Neo4jClient` cung cấp truy vấn thống kê; một custom repository dùng `Neo4jTemplate` cho một luồng lưu entity đặc biệt. Các thành phần này vẫn có thể phối hợp trong cùng service. Với thao tác cần tính nguyên tử, đặt ranh giới transaction ở service và dùng cấu hình transaction manager của SDN nhất quán.

Đừng chọn abstraction chỉ dựa trên số dòng mã. Một câu Cypher dài trong `@Query` vẫn có thể phù hợp nếu nó ổn định và gắn chặt với repository. Ngược lại, một truy vấn báo cáo ngắn nhưng trả về DTO có thể rõ ràng hơn khi đặt trong adapter dùng `Neo4jClient`. Hãy để API thể hiện đúng ý định nghiệp vụ và giữ chi tiết truy vấn ở nơi dễ bảo trì.

## 6. Những điểm cần kiểm tra khi triển khai

**Ánh xạ entity và relationship.** Repository và template làm việc dựa trên metadata entity của SDN. Hãy khai báo ID, label và `@Relationship` đúng với đồ thị thực tế. Khi dùng `Neo4jClient` hoặc driver trực tiếp, kết quả Cypher cần được ánh xạ rõ ràng; đừng giả định mọi record tự trở thành một graph entity hoàn chỉnh.

**Ranh giới transaction.** Các thao tác repository, template và client được cấu hình với transaction manager của SDN có thể tham gia transaction Spring. Đặt `@Transactional` ở ranh giới nghiệp vụ cần commit hoặc rollback cùng nhau. Với driver trực tiếp, kiểm tra cách session và transaction được tạo, sử dụng và đóng để tránh vô tình tách một nghiệp vụ thành nhiều transaction.

**Tham số hóa và an toàn truy vấn.** Dùng tham số Cypher cho dữ liệu đầu vào. Tránh nối chuỗi từ dữ liệu người dùng vào câu truy vấn. Nếu cấu trúc truy vấn phải thay đổi theo lựa chọn, dùng các nhánh hoặc danh sách thành phần đã được cho phép.

**Hiệu năng truy vấn.** Chọn repository, template hay client không tự quyết định truy vấn nhanh hay chậm. Hãy trả về đúng các trường cần dùng, giới hạn kích thước kết quả, cân nhắc phân trang khi phù hợp, tạo index hoặc constraint cho thuộc tính được tra cứu thường xuyên và dùng `EXPLAIN` hoặc `PROFILE` để kiểm tra kế hoạch thực thi. Với truy vấn đồ thị, chú ý số lượng node và relationship được mở rộng, tránh vô tình trả về toàn bộ graph khi màn hình chỉ cần một vài thuộc tính.

**Ứng dụng reactive.** Nếu toàn bộ tầng dữ liệu sử dụng reactive API, hãy chọn các thành phần reactive tương ứng như `ReactiveNeo4jRepository`, `ReactiveNeo4jTemplate` và `ReactiveNeo4jClient`, đồng thời giữ luồng xử lý non-blocking. Không gọi API driver imperative theo cách blocking bên trong một pipeline reactive.

Các ví dụ trên minh họa API phổ biến của Spring Data Neo4j và Neo4j Java Driver. Tên package, kiểu trả về và một số phương thức có thể thay đổi theo phiên bản SDN/Driver; hãy dùng phiên bản dependency thực tế của dự án làm chuẩn khi triển khai.

## Kết luận

Hãy dùng repository làm điểm bắt đầu cho persistence theo entity; dùng `Neo4jTemplate` khi cần điều khiển thao tác entity bằng mã Java; dùng `Neo4jClient` khi cần kiểm soát Cypher và mapping kết quả; và chỉ truy cập driver trực tiếp khi cần quyền điều khiển mức thấp. Khi lựa chọn đúng abstraction, mô hình node/relationship, câu truy vấn và ranh giới transaction sẽ dễ hiểu, dễ kiểm tra và dễ bảo trì hơn.
