# Kế thừa entity, lớp trừu tượng và ánh xạ đa hình bằng label

Trong một ứng dụng quản lý nội dung, sách, video và podcast có thể có những thuộc tính riêng nhưng cùng chia sẻ các thông tin như mã định danh, tiêu đề và ngày phát hành. Nếu mỗi loại nội dung được mô hình hóa hoàn toàn độc lập, các thuộc tính và quy tắc chung sẽ bị lặp. Nếu ép tất cả vào một lớp duy nhất, entity lại chứa nhiều field chỉ có ý nghĩa với một vài loại dữ liệu.

Java giải quyết bài toán này bằng kế thừa và lớp trừu tượng. Spring Data Neo4j (SDN) ánh xạ mô hình đó vào đồ thị bằng nhiều label trên cùng một node. Label của lớp cơ sở giúp truy vấn chung; label của lớp cụ thể giúp SDN nhận diện subtype cần khởi tạo khi đọc dữ liệu. Nhờ vậy, một repository hoặc một relationship khai báo kiểu lớp cơ sở vẫn có thể trả về các object có kiểu thực tế như `Book` hoặc `Video`.

## 1. Từ mô hình Java tới label của Neo4j

Giả sử miền dữ liệu có các loại nội dung:

- `Content`: lớp cơ sở trừu tượng, chứa `id`, `title` và `publishedYear`.
- `Book`: nội dung dạng sách, có thêm `isbn` và `pageCount`.
- `Video`: nội dung dạng video, có thêm `durationMinutes` và `resolution`.

Trong Java, `Book` và `Video` kế thừa `Content`. Trong Neo4j, mỗi instance được lưu thành một node. Một node `Book` có các label `Content` và `Book`; một node `Video` có các label `Content` và `Video`:

```text
(:Content:Book {title, isbn, pageCount})
(:Content:Video {title, durationMinutes, resolution})
```

Đây là một node mang nhiều label, không phải hai node riêng được nối với nhau. Các thuộc tính chung nằm trên cùng node với thuộc tính riêng của subtype. Cách biểu diễn này cho phép truy vấn tất cả nội dung qua label `Content`, hoặc chỉ truy vấn sách qua label `Book`.

| Kiểu Java | Label của node | Dữ liệu đặc trưng |
|---|---|---|
| `Content` (abstract) | Label chung `Content` | `title`, `publishedYear` |
| `Book extends Content` | `Content`, `Book` | `isbn`, `pageCount` |
| `Video extends Content` | `Content`, `Video` | `durationMinutes`, `resolution` |

## 2. Khai báo lớp cơ sở trừu tượng

SDN yêu cầu khai báo `@Node` riêng ở từng cấp của hierarchy được ánh xạ. Annotation `@Node` không tự kế thừa từ lớp cha hoặc interface. Để hỗ trợ polymorphic mapping qua một lớp cơ sở, lớp cơ sở đó phải là abstract và được đánh dấu `@Node`.

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Content")
public abstract class Content {
    @Id
    @GeneratedValue
    private Long id;

    private String title;
    private Integer publishedYear;

    protected Content() {
    }

    protected Content(String title, Integer publishedYear) {
        this.title = title;
        this.publishedYear = publishedYear;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Integer getPublishedYear() {
        return publishedYear;
    }
}
```

`Content` là abstract nên ứng dụng không tạo trực tiếp `new Content(...)`. Lớp này vẫn là một phần của metadata mapping: `@Node("Content")` định nghĩa label chung, còn các field kế thừa được dùng khi đọc và ghi các subtype.

ID được khai báo ở lớp cơ sở nên các lớp con dùng chung cơ chế định danh. Ví dụ sử dụng `Long` với `@GeneratedValue` để minh họa ID do Neo4j quản lý. Nếu ứng dụng sử dụng khóa nghiệp vụ, hãy áp dụng quy tắc ID và optimistic locking phù hợp với SDN.

## 3. Khai báo các lớp cụ thể

Mỗi lớp cụ thể được đánh dấu `@Node` với label riêng. Label của lớp cơ sở sẽ được SDN sử dụng như label bổ sung cùng label của lớp cụ thể.

```java
import org.springframework.data.neo4j.core.schema.Node;

@Node("Book")
public class Book extends Content {
    private String isbn;
    private Integer pageCount;

    protected Book() {
        super();
    }

    public Book(String title, Integer publishedYear,
                String isbn, Integer pageCount) {
        super(title, publishedYear);
        this.isbn = isbn;
        this.pageCount = pageCount;
    }

    public String getIsbn() {
        return isbn;
    }

    public Integer getPageCount() {
        return pageCount;
    }
}
```

```java
import org.springframework.data.neo4j.core.schema.Node;

@Node("Video")
public class Video extends Content {
    private Integer durationMinutes;
    private String resolution;

    protected Video() {
        super();
    }

    public Video(String title, Integer publishedYear,
                 Integer durationMinutes, String resolution) {
        super(title, publishedYear);
        this.durationMinutes = durationMinutes;
        this.resolution = resolution;
    }

    public Integer getDurationMinutes() {
        return durationMinutes;
    }

    public String getResolution() {
        return resolution;
    }
}
```

Các lớp trên minh họa ba phần của một entity: field dùng chung ở `Content`, field riêng ở subtype và constructor gọi `super(...)` để khởi tạo thuộc tính được kế thừa. Constructor không tham số có phạm vi `protected` giúp SDN khởi tạo object khi cần; các constructor công khai là API tạo dữ liệu của ứng dụng.

Khi SDN lưu một `Book`, node được gắn label cụ thể `Book` cùng label `Content` của abstract base. Khi lưu `Video`, node có label `Video` cùng label `Content`. Label cụ thể phải phân biệt được các kiểu thực tế để SDN biết cần tạo lớp Java nào khi đọc qua `Content`.

Trong cấu hình này, `Book` hoặc `Video` là primary label vì đó là kiểu cụ thể nhất; `Content` là label bổ sung dùng để nhóm các subtype. Đây cũng là lý do nên chọn label cụ thể theo miền nghiệp vụ thay vì phụ thuộc vào tên lớp Java mặc định.

## 4. Truy vấn đa hình qua repository của lớp cơ sở

Có thể khai báo repository với kiểu domain là lớp cơ sở trừu tượng:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ContentRepository
        extends Neo4jRepository<Content, Long> {
}
```

Repository này thao tác trên miền `Content`. Khi lưu subtype, phương thức `save` vẫn nhận object cụ thể:

```java
Book book = contentRepository.save(
    new Book("Graph Databases", 2024, "978-0000000001", 320)
);

Video video = contentRepository.save(
    new Video("Cypher Basics", 2025, 42, "1080p")
);
```

Khi đọc qua repository của lớp cơ sở:

```java
List<Content> contents = contentRepository.findAll();

for (Content content : contents) {
    System.out.println(content.getTitle());

    if (content instanceof Book bookItem) {
        System.out.println(bookItem.getIsbn());
    } else if (content instanceof Video videoItem) {
        System.out.println(videoItem.getDurationMinutes());
    }
}
```

SDN dùng các label trên node để xác định concrete class và khởi tạo object tương ứng. Biến có kiểu khai báo `Content`, nhưng object bên trong danh sách có thể là `Book` hoặc `Video`. Đây là polymorphism ở tầng object mapping.

Có thể khai báo repository riêng cho một subtype khi use case chỉ làm việc với loại đó:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface BookRepository extends Neo4jRepository<Book, Long> {
}

public interface VideoRepository extends Neo4jRepository<Video, Long> {
}
```

Repository `BookRepository` truy vấn theo label cụ thể `Book`; repository `ContentRepository` dùng lớp cơ sở để làm việc với các loại nội dung đã được ánh xạ trong hierarchy.

## 5. Relationship có kiểu lớp cơ sở

Một lợi ích quan trọng của polymorphic mapping là entity khác có thể tham chiếu tới lớp cơ sở mà không cần biết subtype cụ thể. Ví dụ, một `Shelf` chứa nhiều loại nội dung:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Shelf")
public class Shelf {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Relationship(type = "CONTAINS")
    private List<Content> items = new ArrayList<>();

    protected Shelf() {
    }

    public Shelf(String name) {
        this.name = name;
    }

    public List<Content> getItems() {
        return items;
    }
}
```

Collection `items` có kiểu `Content`, vì vậy nó có thể chứa `Book` và `Video`. Khi SDN đọc `Shelf`, label của từng node đích giúp ánh xạ đúng subtype. Ứng dụng có thể duyệt `items` và xử lý theo kiểu thực tế mà không phải khai báo hai relationship collection riêng cho từng loại nội dung.

Repository tương ứng:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ShelfRepository extends Neo4jRepository<Shelf, Long> {
}
```

Ví dụ tạo shelf và thêm nhiều subtype:

```java
Shelf shelf = new Shelf("Recommended");
shelf.getItems().add(
    new Book("Graph Databases", 2024, "978-0000000001", 320)
);
shelf.getItems().add(
    new Video("Cypher Basics", 2025, 42, "1080p")
);

shelfRepository.save(shelf);
```

Đây là ví dụ minh họa việc lưu một aggregate chứa các loại node khác nhau. Trong ứng dụng thực tế, hãy quyết định rõ `Shelf` có sở hữu vòng đời của các nội dung hay chỉ tham chiếu tới những node đã tồn tại. Nếu `Book` hoặc `Video` được chia sẻ bởi nhiều shelf, có thể tải node hiện có theo ID rồi gắn relationship thay vì tạo instance mới cho mỗi shelf.

## 6. Kiểm tra label và dữ liệu bằng Cypher

Sau khi lưu các subtype qua SDN, dùng Neo4j Browser hoặc Cypher Shell để xác minh label:

```cypher
MATCH (c:Content)
RETURN c.title AS title,
       labels(c) AS labels,
       c.publishedYear AS publishedYear
ORDER BY title;
```

Truy vấn trên lấy tất cả node mang label `Content`, gồm cả `Book` và `Video`. Kết quả label dự kiến:

```text
Graph Databases  -> có label Content và Book
Cypher Basics    -> có label Content và Video
```

Thứ tự hiển thị của danh sách label có thể khác nhau; điều cần xác minh là node có đủ label chung và label cụ thể.

Chỉ tìm sách:

```cypher
MATCH (b:Book)
RETURN b.title, b.isbn, b.pageCount;
```

Chỉ tìm video:

```cypher
MATCH (v:Video)
RETURN v.title, v.durationMinutes, v.resolution;
```

Kiểm tra relationship từ shelf tới nhiều loại content:

```cypher
MATCH (s:Shelf)-[:CONTAINS]->(c:Content)
RETURN s.name AS shelf,
       c.title AS content,
       labels(c) AS contentType
ORDER BY shelf, content;
```

Khi dùng truy vấn Cypher thủ công để tạo dữ liệu mà SDN sẽ đọc, phải gắn đủ label theo hierarchy. Ví dụ:

```cypher
CREATE (:Content:Book {
    title: 'Graph Databases',
    publishedYear: 2024,
    isbn: '978-0000000001',
    pageCount: 320
});
```

Node chỉ có label `Book` có thể không được tìm thấy qua truy vấn của lớp cơ sở `Content`, bởi nó thiếu label chung. Nếu đang chuyển đổi dữ liệu cũ sang hierarchy mới, có thể bổ sung label cơ sở một cách idempotent:

```cypher
MATCH (b:Book)
SET b:Content;

MATCH (v:Video)
SET v:Content;
```

Hãy kiểm tra dữ liệu hiện có và mapping trước khi chạy migration trên môi trường thật. Đảm bảo label subtype đang đại diện đúng một concrete class được SDN quản lý.

## 7. Kế thừa nhiều cấp

Hierarchy có thể có nhiều hơn một lớp abstract. Ví dụ, video và podcast đều là nội dung số, trong khi sách giấy là nội dung vật lý:

```java
@Node("Content")
public abstract class Content {
    // ID và các thuộc tính dùng chung nhất.
}

@Node("DigitalContent")
public abstract class DigitalContent extends Content {
    // Thuộc tính chung cho nội dung số.
}

@Node("Video")
public class Video extends DigitalContent {
    // Thuộc tính riêng của video.
}
```

Với một node `Video`, các label của hierarchy có thể là `Content`, `DigitalContent` và `Video`. Query theo `Content` lấy mọi loại nội dung; query theo `DigitalContent` lấy các loại nội dung số; query theo `Video` chỉ lấy video.

Mỗi cấp trong hierarchy cần được đánh dấu `@Node` nếu tham gia mapping. Hãy đặt label sao cho thể hiện đúng nhóm nghiệp vụ và tránh dùng cùng một label cụ thể cho hai lớp Java khác nhau trong cùng mapping context.

## 8. Quy tắc thiết kế label và subtype

| Quy tắc | Lý do |
|---|---|
| Đánh dấu abstract base bằng `@Node` | SDN dùng label của base như label chung để hỗ trợ truy vấn đa hình |
| Đánh dấu từng concrete class bằng `@Node` riêng | `@Node` không tự kế thừa; subtype cần label để nhận diện kiểu thực tế |
| Dùng label cụ thể ổn định | Label là một phần schema của graph; đổi tên lớp Java không nên vô tình làm đổi schema |
| Giữ một label subtype rõ ràng cho mỗi node | SDN cần xác định concrete class khi khởi tạo object |
| Đặt thuộc tính chung ở base, thuộc tính riêng ở subtype | Tránh lặp field và tránh các field không liên quan trên mọi loại entity |
| Chỉ dùng relationship base type khi các subtype thực sự cùng vai trò nghiệp vụ | Giữ mô hình quan hệ rõ ràng và tránh ép kiểu không cần thiết |

Một số lưu ý:

- `@Node` không được kế thừa tự động. Nếu có abstract intermediate class, hãy đánh dấu class đó bằng `@Node` và chọn label phù hợp.
- Polymorphic mapping qua abstract base cần base được đánh dấu `@Node`; không giả định một lớp cha concrete bất kỳ sẽ tự động cho kết quả đa hình.
- Khi truy vấn qua label của abstract base, node cần có label chung đó và label concrete đã được ánh xạ để SDN nhận diện subtype. Dữ liệu tạo ngoài SDN cần tuân theo cùng quy ước label.
- Label không thay thế validation nghiệp vụ. Nếu một node có label `Book`, ứng dụng vẫn cần kiểm tra `isbn` hoặc `pageCount` theo yêu cầu miền dữ liệu.
- Đừng tạo một lớp con chỉ để thêm một label tùy tiện. Nếu label là metadata có thể thay đổi độc lập với kiểu Java, hãy cân nhắc cơ chế label động như `@DynamicLabels` và hiểu rõ hành vi ghi của nó.

## 9. Interface và polymorphism

SDN còn hỗ trợ một số kịch bản polymorphism qua interface. Tuy nhiên, interface không thể khai báo field định danh và do đó không phải kiểu domain hợp lệ để làm generic type của repository. Một mô hình interface cần quy ước label chung cho interface và label riêng cho từng implementation nếu có nhiều implementation khác nhau.

Với hierarchy entity cần repository, ID kế thừa, field chung và các subtype rõ ràng, abstract base class thường dễ biểu đạt hơn. Chọn interface khi mục tiêu chính là mô tả hợp đồng hành vi hoặc khi mô hình cần các implementation độc lập; khi đó phải thiết kế label theo hướng dẫn của SDN cho interface mapping.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ContentRepository.findAll()` không trả về một subtype | Node thiếu label `Content` hoặc label subtype không khớp mapping | Kiểm tra `labels(node)` và migration label |
| SDN không nhận diện concrete class | Subclass thiếu `@Node` hoặc các subtype dùng label không phân biệt | Gắn `@Node` cho từng cấp và dùng label cụ thể duy nhất |
| Lỗi khi ánh xạ abstract base | Base không được đánh dấu `@Node` hoặc dữ liệu không có label concrete phù hợp | Đánh dấu abstract base và bảo đảm mỗi node có subtype đã đăng ký |
| Field chung bị lặp trong nhiều lớp | Thuộc tính dùng chung chưa được đưa lên base class | Chuyển field và logic chung lên abstract base |
| Relationship chỉ chứa được một loại nội dung | Field relationship khai báo bằng concrete class | Dùng kiểu abstract base nếu nghiệp vụ cho phép nhiều subtype |
| Query theo subtype trả về dữ liệu ngoài dự kiến | Label cụ thể bị dùng chung hoặc được gán thủ công không đúng | Chuẩn hóa label và xác minh dữ liệu tạo từ các nguồn khác |

## 11. Tự kiểm tra

1. Vì sao một node `Book` cần cả label `Content` và `Book` trong hierarchy này?
2. Vì sao `@Node` phải được khai báo riêng ở abstract base và các lớp cụ thể?
3. Polymorphic mapping cho phép `ContentRepository.findAll()` trả về những kiểu object nào?
4. Vì sao một relationship có thể khai báo target type là `Content` dù node đích thực tế là `Book` hoặc `Video`?
5. Nếu dữ liệu được tạo bằng Cypher chỉ có label `Book`, điều gì có thể xảy ra khi truy vấn qua lớp cơ sở `Content`?
6. Khi hierarchy có abstract intermediate class `DigitalContent`, node `Video` nên có những label nào?
7. Khi nào interface phù hợp hơn abstract base class trong mô hình domain của SDN?

## Tài liệu tham khảo

- [Spring Data Neo4j — Metadata-based Mapping, mục “A note on class hierarchies”](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
