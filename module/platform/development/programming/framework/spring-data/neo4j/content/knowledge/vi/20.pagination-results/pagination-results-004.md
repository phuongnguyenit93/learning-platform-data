# Phân trang Cypher tùy chỉnh với $skip và $limit

Khi một graph có nhiều node phù hợp với điều kiện tìm kiếm, trả toàn bộ kết quả trong một lần có thể làm tăng thời gian truy vấn, lượng dữ liệu truyền qua mạng và bộ nhớ ứng dụng. Neo4j cung cấp hai mệnh đề Cypher là **SKIP** và **LIMIT** để lấy một đoạn kết quả. Khi viết custom query cho Spring Data Neo4j (SDN), có thể bind giá trị phân trang qua hai tham số **$skip** và **$limit**.

Phân trang theo offset cần một thứ tự ổn định, một cách tính vị trí bắt đầu chính xác và một truy vấn đếm phù hợp nếu API cần tổng số trang. Với graph có relationship one-to-many, phải phân trang trên tập node gốc duy nhất trước khi mở rộng các nhánh; nếu phân trang trên các dòng đã nhân theo relationship, một entity có thể chiếm nhiều vị trí hoặc bị tách giữa các trang.

## SKIP và LIMIT trong Cypher

- **SKIP** bỏ qua số dòng đầu tiên của tập kết quả.
- **LIMIT** giới hạn số dòng tối đa được trả về sau khi bỏ qua.
- **ORDER BY** xác định thứ tự dòng trước khi phân trang.

Ví dụ lấy 20 người đầu tiên theo tên:

~~~cypher
MATCH (p:Person)
RETURN p
ORDER BY p.fullName ASC, p.employeeCode ASC
SKIP 0
LIMIT 20;
~~~

Ở đây, truy vấn sắp xếp theo tên tăng dần, sau đó theo mã nhân viên để phân biệt những người có cùng tên. **SKIP 0** nghĩa là không bỏ qua dòng nào; **LIMIT 20** lấy tối đa 20 dòng đầu tiên.

Các giá trị này có thể được truyền dưới dạng parameter:

~~~cypher
MATCH (p:Person)
RETURN p
ORDER BY p.fullName ASC, p.employeeCode ASC
SKIP $skip
LIMIT $limit;
~~~

Tên tham số trong Cypher bắt đầu bằng dấu **$**. Ứng dụng gửi giá trị cho hai tham số này khi thực thi truy vấn. Tham số giúp tái sử dụng cùng một câu Cypher cho nhiều trang và tránh nối số liệu đầu vào trực tiếp vào câu lệnh.

## Tính offset từ page và page size

API thường nhận số trang và kích thước trang, trong khi Cypher nhận số dòng cần bỏ qua. Với phân trang bắt đầu từ trang 0:

\[
skip = page \times pageSize
\]

Ví dụ với page size bằng 20:

| Page (bắt đầu từ 0) | Skip | Limit | Dòng được lấy |
|---:|---:|---:|---|
| 0 | 0 | 20 | 1–20 |
| 1 | 20 | 20 | 21–40 |
| 2 | 40 | 20 | 41–60 |
| 3 | 60 | 20 | 61–80 |

Nếu API của sản phẩm đánh số trang từ 1, cần chuyển về chỉ số bắt đầu từ 0 trước khi tính offset: **skip = (pageNumber - 1) × pageSize**. Không trộn hai quy ước vì sẽ khiến trang đầu bị bỏ mất dữ liệu hoặc hai trang liền nhau bị trùng kết quả.

Giá trị **skip** và **limit** phải là số nguyên hợp lệ. Thông thường:

- **skip** phải lớn hơn hoặc bằng 0.
- **limit** phải lớn hơn 0 đối với một trang có dữ liệu.
- **page** phải lớn hơn hoặc bằng 0 nếu API dùng zero-based indexing.
- **pageSize** cần có giới hạn tối đa do ứng dụng quy định để tránh một request yêu cầu quá nhiều dữ liệu.

Không tin trực tiếp giá trị page size từ client. Hãy kiểm tra và giới hạn nó ở tầng service hoặc controller. Khi nhân page với page size, dùng phép nhân có kiểm tra tràn số để offset không bị quay về số âm nếu giá trị đầu vào quá lớn.

## Khai báo custom query trong repository

Giả sử ứng dụng cần tìm người theo trạng thái hoạt động. Entity tối thiểu:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String fullName;
    private Boolean active;

    protected Person() {
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public String getFullName() {
        return fullName;
    }

    public Boolean getActive() {
        return active;
    }
}
~~~

Repository khai báo query nhận hai tham số phân trang:

~~~java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person)
        WHERE p.active = $active
        RETURN p
        ORDER BY p.fullName ASC, p.employeeCode ASC
        SKIP $skip
        LIMIT $limit
        """)
    List<Person> findPage(
        @Param("active") boolean active,
        @Param("skip") long skip,
        @Param("limit") long limit
    );

    @Query("""
        MATCH (p:Person)
        WHERE p.active = $active
        RETURN count(p)
        """)
    long countMatching(@Param("active") boolean active);
}
~~~

**findPage** chỉ trả các node Person trong trang hiện tại. **countMatching** dùng cùng điều kiện lọc nhưng không có SKIP hoặc LIMIT để đếm toàn bộ kết quả phù hợp. Giữ điều kiện WHERE giống nhau giữa truy vấn dữ liệu và truy vấn đếm để tổng số trang khớp với nội dung được phân trang.

Trong ví dụ, **employeeCode** được giả định là duy nhất và ổn định. Nó đóng vai trò tiêu chí sắp xếp phụ sau **fullName**. Nếu chỉ sắp xếp theo fullName, nhiều người cùng tên có thể đổi vị trí tương đối giữa các lần gọi; khi đó một người có thể xuất hiện ở hai trang hoặc bị bỏ qua.

## Bind $skip và $limit từ Java

Có thể dùng service để kiểm tra đầu vào, tính offset và ghép nội dung trang với tổng số kết quả:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

@Service
public class PersonSearchService {

    private static final int MAX_PAGE_SIZE = 100;

    private final PersonRepository people;

    public PersonSearchService(PersonRepository people) {
        this.people = people;
    }

    public Page<Person> findPeople(boolean active, int page, int pageSize) {
        if (page < 0) {
            throw new IllegalArgumentException("Page must be zero or greater");
        }

        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Page size is outside the allowed range");
        }

        long skip;
        try {
            skip = Math.multiplyExact((long) page, (long) pageSize);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException("Requested page offset is too large", ex);
        }

        List<Person> content = people.findPage(active, skip, pageSize);
        long total = people.countMatching(active);

        return new PageImpl<>(
            content,
            PageRequest.of(page, pageSize),
            total
        );
    }
}
~~~

Service thực hiện các bước:

1. Từ chối page âm.
2. Từ chối page size bằng 0 hoặc vượt quá giới hạn ứng dụng.
3. Tính **skip** bằng page nhân page size và phát hiện tràn số.
4. Truyền **skip** và **pageSize** vào custom query.
5. Chạy truy vấn đếm với cùng điều kiện lọc.
6. Tạo **Page<Person>** chứa nội dung trang, thông tin page request và tổng số kết quả.

Giá trị **MAX_PAGE_SIZE = 100** chỉ là chính sách minh họa. Hệ thống thực tế cần chọn giới hạn dựa trên kích thước entity, độ rộng graph được trả về, tải database và yêu cầu giao diện.

Ví dụ gọi service:

~~~java
Page<Person> firstPage = personSearchService.findPeople(true, 0, 20);
Page<Person> secondPage = personSearchService.findPeople(true, 1, 20);

List<Person> peopleInFirstPage = firstPage.getContent();
long totalPeople = firstPage.getTotalElements();
int totalPages = firstPage.getTotalPages();
~~~

Trang đầu truyền **page = 0**, **pageSize = 20**, vì vậy query nhận **skip = 0**, **limit = 20**. Trang thứ hai truyền **page = 1**, do đó query nhận **skip = 20**, **limit = 20**.

## Dùng tham số trong Neo4jClient

Nếu cần điều khiển query ở tầng repository tùy chỉnh, có thể bind các giá trị bằng **Neo4jClient**:

~~~java
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonPageReader {

    private final Neo4jClient neo4jClient;

    public PersonPageReader(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public List<PersonSummary> findPage(
            boolean active,
            long skip,
            long limit) {

        return neo4jClient.query("""
                MATCH (p:Person)
                WHERE p.active = $active
                RETURN p.employeeCode AS employeeCode,
                       p.fullName AS fullName
                ORDER BY p.fullName ASC, p.employeeCode ASC
                SKIP $skip
                LIMIT $limit
                """)
            .bind(active).to("active")
            .bind(skip).to("skip")
            .bind(limit).to("limit")
            .fetchAs(PersonSummary.class)
            .mappedBy((typeSystem, record) -> new PersonSummary(
                record.get("employeeCode").asString(),
                record.get("fullName").asString()
            ))
            .all();
    }
}
~~~

DTO chỉ chứa dữ liệu cần hiển thị:

~~~java
public record PersonSummary(
    String employeeCode,
    String fullName
) {
}
~~~

Với **Neo4jClient**, mỗi giá trị được bind theo tên tham số tương ứng. Cách này hữu ích khi cần ánh xạ record thành DTO, kết hợp nhiều truy vấn hoặc thực hiện logic phân trang tùy chỉnh. Cần kiểm tra **skip** và **limit** trước khi bind giống như khi gọi repository.

## Luôn có ORDER BY ổn định

Cypher không bảo đảm thứ tự kết quả nếu truy vấn không chỉ định **ORDER BY**. Vì vậy, chỉ thêm **SKIP** và **LIMIT** mà không sắp xếp là chưa đủ để tạo phân trang đáng tin cậy.

Ví dụ không ổn định:

~~~cypher
MATCH (p:Person)
RETURN p
SKIP $skip
LIMIT $limit;
~~~

Database có thể trả các dòng theo thứ tự khác nhau giữa các lần thực thi. Một người có thể xuất hiện ở trang đầu trong lần gọi này nhưng chuyển sang trang khác ở lần gọi tiếp theo.

Ví dụ ổn định hơn:

~~~cypher
MATCH (p:Person)
RETURN p
ORDER BY p.fullName ASC, p.employeeCode ASC
SKIP $skip
LIMIT $limit;
~~~

Tiêu chí sắp xếp nên bao gồm một thuộc tính duy nhất hoặc một tổ hợp thuộc tính xác định duy nhất thứ tự của các node. Trong ví dụ, nếu hai người có cùng fullName thì employeeCode phân biệt vị trí của họ.

Nếu sắp xếp theo thời gian tạo, có thể dùng thời gian cùng ID ổn định làm tiêu chí phụ:

~~~cypher
MATCH (p:Person)
RETURN p
ORDER BY p.createdAt DESC, p.employeeCode ASC
SKIP $skip
LIMIT $limit;
~~~

Điều kiện lọc, thứ tự và quy tắc xử lý giá trị null cũng cần nhất quán giữa các lần gọi trang. Nếu một thuộc tính sắp xếp có thể null, hãy xác định vị trí mong muốn của các node thiếu giá trị đó và biểu đạt rõ trong truy vấn.

## Phân trang khi truy vấn đi qua relationship

Một lỗi phổ biến là áp dụng **SKIP** và **LIMIT** sau khi mở rộng relationship one-to-many. Khi đó, Cypher phân trang trên các dòng kết hợp, không phải trên các node gốc duy nhất.

Giả sử mỗi người có thể có nhiều kỹ năng:

~~~cypher
MATCH (p:Person)-[:HAS_SKILL]->(skill:Skill)
RETURN p, skill
ORDER BY p.fullName
SKIP $skip
LIMIT $limit;
~~~

Nếu một người có năm kỹ năng, người đó có thể chiếm năm dòng. Với **LIMIT 10**, kết quả có thể chỉ chứa một vài người dù còn nhiều người khác phù hợp. Một trang kế tiếp thậm chí có thể tiếp tục chứa các kỹ năng của cùng người đó.

Nếu mục tiêu là phân trang người, hãy khử trùng và phân trang node Person trước:

~~~cypher
MATCH (p:Person)-[:HAS_SKILL]->(:Skill)
WHERE p.active = $active
WITH DISTINCT p
ORDER BY p.fullName ASC, p.employeeCode ASC
SKIP $skip
LIMIT $limit
RETURN p;
~~~

**WITH DISTINCT p** tạo tập node gốc duy nhất trước khi phân trang. Truy vấn này chỉ trả Person, vì vậy collection skills không được yêu cầu ánh xạ từ kết quả. Nếu trang cần cả kỹ năng, mở rộng quan hệ sau khi đã chọn trang:

~~~cypher
MATCH (p:Person)
WHERE p.active = $active
WITH DISTINCT p
ORDER BY p.fullName ASC, p.employeeCode ASC
SKIP $skip
LIMIT $limit

OPTIONAL MATCH (p)-[r:HAS_SKILL]->(skill:Skill)
RETURN p,
       collect(DISTINCT r) AS skillRelationships,
       collect(DISTINCT skill) AS skills
ORDER BY p.fullName ASC, p.employeeCode ASC;
~~~

Cách này chọn trang Person trước, rồi mới gom các kỹ năng của từng người trong trang. Nếu cần ánh xạ trực tiếp sang entity SDN, phải kiểm tra custom result mapping của phiên bản dự án với các node, relationship và collection trả về. Nếu chỉ cần dữ liệu màn hình, DTO/projection với danh sách tên hoặc mã kỹ năng thường có hợp đồng rõ ràng hơn.

## Truy vấn đếm phải khớp với truy vấn trang

Đối với **Page<T>**, ứng dụng thường cần tổng số phần tử để tính tổng trang. Truy vấn đếm phải dùng cùng bộ lọc như truy vấn lấy dữ liệu và không áp dụng SKIP/LIMIT.

Nếu chỉ lọc trên node Person:

~~~cypher
MATCH (p:Person)
WHERE p.active = $active
RETURN count(p);
~~~

Nếu lọc người qua relationship:

~~~cypher
MATCH (p:Person)-[:WORKS_ON]->(project:Project)
WHERE project.status = $projectStatus
RETURN count(DISTINCT p);
~~~

Dùng **count(DISTINCT p)** khi một Person có thể khớp nhiều project. Nếu dùng **count(p)** trên tập dòng đã nhân theo relationship, tổng số phần tử có thể lớn hơn số Person duy nhất.

Ví dụ truy vấn trang cho cùng điều kiện:

~~~cypher
MATCH (p:Person)-[:WORKS_ON]->(project:Project)
WHERE project.status = $projectStatus
WITH DISTINCT p
ORDER BY p.fullName ASC, p.employeeCode ASC
SKIP $skip
LIMIT $limit
RETURN p;
~~~

Truy vấn đếm và truy vấn nội dung phải giữ cùng điều kiện **project.status = $projectStatus**. Nếu một bên lọc thêm điều kiện mà bên kia không có, totalElements và nội dung trang sẽ không nhất quán.

Truy vấn count có thể tốn chi phí với graph lớn hoặc pattern nhiều relationship. Nếu giao diện chỉ cần biết còn trang tiếp theo hay không mà không cần tổng số trang, có thể cân nhắc lấy thêm một phần tử so với page size để xác định **hasNext**, thay vì luôn chạy count. Chọn kiểu phản hồi theo nhu cầu thực tế của API.

## Giới hạn của offset pagination

**SKIP/LIMIT** dễ hiểu và phù hợp với các danh sách cần điều hướng tới trang bất kỳ. Tuy nhiên, offset lớn có thể tốn tài nguyên vì database phải xác định và bỏ qua nhiều dòng trước khi trả phần dữ liệu cần thiết. Trang càng sâu, chi phí có thể càng tăng.

Offset pagination cũng có thể bị dịch chuyển khi dữ liệu thay đổi giữa hai request. Ví dụ người dùng đã đọc trang 0; trước khi họ yêu cầu trang 1, một node mới được thêm vào đầu thứ tự sắp xếp. Nếu dùng cùng offset, một node có thể xuất hiện lặp lại ở hai trang. Nếu node bị xóa ở phía trước offset, một node khác có thể bị bỏ qua.

Các biện pháp giảm rủi ro:

- Dùng **ORDER BY** ổn định với tiêu chí phân biệt duy nhất.
- Giữ điều kiện lọc và sắp xếp nhất quán giữa các request.
- Chọn page size vừa phải và giới hạn page size tối đa.
- Tránh offset quá sâu nếu dữ liệu tăng nhanh.
- Với báo cáo cần snapshot nhất quán, xác định chiến lược snapshot hoặc thời điểm dữ liệu rõ ràng.
- Với danh sách rất lớn hoặc cập nhật liên tục, cân nhắc keyset/cursor pagination.

### Khi nào nên chuyển sang keyset pagination?

Keyset pagination dùng giá trị của bản ghi cuối trang trước làm mốc cho trang tiếp theo. Ví dụ sắp xếp theo **fullName** và **employeeCode**:

~~~cypher
MATCH (p:Person)
WHERE p.active = $active
  AND (
      p.fullName > $lastFullName
      OR (
          p.fullName = $lastFullName
          AND p.employeeCode > $lastEmployeeCode
      )
  )
RETURN p
ORDER BY p.fullName ASC, p.employeeCode ASC
LIMIT $limit;
~~~

Ứng dụng gửi **lastFullName** và **lastEmployeeCode** của phần tử cuối trang trước. Truy vấn chỉ lấy các node đứng sau cặp giá trị đó theo thứ tự đã chọn. Cách này tránh phải bỏ qua toàn bộ các dòng trước offset, nhưng yêu cầu thứ tự sắp xếp có thể biểu diễn thành cursor và API quản lý cursor đúng cách.

Trang đầu tiên chưa có cursor nên cần một biến thể truy vấn không có điều kiện mốc hoặc một điều kiện được thiết kế rõ ràng cho trường hợp cursor rỗng. Không dùng chuỗi rỗng hoặc giá trị mặc định tùy tiện nếu nó làm sai thứ tự dữ liệu.

## Không bind tên thuộc tính hoặc hướng sắp xếp như parameter

Cypher parameter thay thế **giá trị**, không thay thế tên property, label, relationship type hoặc từ khóa cú pháp. Ví dụ, cách viết sau không làm cho ORDER BY trở nên động theo giá trị parameter:

~~~cypher
MATCH (p:Person)
RETURN p
ORDER BY $sortProperty
SKIP $skip
LIMIT $limit;
~~~

Ở đây **$sortProperty** được hiểu là một giá trị parameter cố định cho mọi dòng, không phải tên thuộc tính cần đọc từ từng node. Một số phiên bản Cypher có hỗ trợ cú pháp truy cập property động như **p[$sortProperty]**; hãy kiểm tra khả năng tương thích và giới hạn lựa chọn thuộc tính bằng whitelist của ứng dụng. Parameter vẫn không thể thay thế tùy ý các từ khóa hoặc hướng cú pháp như **ASC**/**DESC**, label hay relationship type. Không nối trực tiếp nội dung tùy ý từ request vào Cypher.

Với số ít lựa chọn cố định, có thể tạo các query method hoặc query template riêng cho từng thứ tự được hỗ trợ. Nếu xây dựng Cypher động bằng Neo4jClient, chỉ ghép các đoạn cú pháp lấy từ whitelist nội bộ; mọi giá trị dữ liệu vẫn phải bind bằng parameter.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng SKIP/LIMIT mà không có ORDER BY | Kết quả giữa các trang không ổn định | Sắp xếp theo thuộc tính và thêm khóa duy nhất làm tiêu chí phụ |
| Tính skip bằng page nhân pageSize nhưng page bắt đầu từ 1 | Bỏ qua sai số dòng | Chuyển page về zero-based trước khi tính |
| Cho phép pageSize tùy ý | Request có thể tải lượng dữ liệu quá lớn | Kiểm tra page size và đặt giới hạn tối đa |
| Không kiểm tra tràn số khi tính offset | Offset có thể thành giá trị không hợp lệ | Dùng phép nhân có kiểm tra tràn |
| Phân trang sau khi MATCH một-nhiều | Một node gốc chiếm nhiều dòng | WITH DISTINCT node gốc trước SKIP/LIMIT |
| Truy vấn count dùng count(*) sau relationship | Tổng số phần tử bị phóng đại | Dùng count(DISTINCT root) |
| Count query có bộ lọc khác query nội dung | TotalElements không khớp dữ liệu | Đồng bộ điều kiện lọc giữa hai query |
| Mong collection relationship tự được tải khi chỉ RETURN node gốc | Entity thiếu dữ liệu liên quan | Trả đủ relationship và endpoint hoặc dùng DTO |
| Bind tên property như một giá trị parameter | Query không tạo thứ tự động như mong đợi | Chọn cú pháp từ whitelist hoặc dùng query riêng |
| Dùng offset rất sâu cho graph lớn | Thời gian truy vấn tăng | Cân nhắc keyset/cursor pagination |

## Bài tập thực hành

Với entity Person có các thuộc tính **employeeCode**, **fullName** và **active**, hãy thực hiện:

1. Viết custom Cypher lọc người đang hoạt động, sắp xếp theo fullName và employeeCode, rồi dùng **SKIP $skip** và **LIMIT $limit**.
2. Khai báo repository method nhận **skip** và **limit** bằng **@Param**.
3. Viết service nhận page và pageSize, xác thực đầu vào, tính offset và gọi repository.
4. Viết truy vấn count có cùng điều kiện lọc và tạo kết quả **Page<Person>**.
5. Thử page 0, page 1, page cuối và page vượt tổng số trang; xác nhận nội dung và metadata.
6. Tạo graph trong đó một người có nhiều Skill; so sánh phân trang trực tiếp trên dòng relationship với phân trang trên **WITH DISTINCT p**.
7. Viết truy vấn đếm người qua relationship bằng **count(DISTINCT p)** và so sánh với **count(p)**.
8. Thêm phần mở rộng collection relationship sau bước phân trang node gốc hoặc chuyển kết quả thành DTO.
9. Thử thêm node mới trước vị trí hiện tại giữa hai request và quan sát ảnh hưởng đến offset pagination.
10. Thiết kế cursor dựa trên fullName và employeeCode, giải thích khi nào keyset pagination phù hợp hơn.

Khi phân trang Cypher tùy chỉnh trong Spring Data Neo4j, hãy bind **$skip** và **$limit** từ giá trị đã được xác thực, sắp xếp kết quả theo một thứ tự ổn định và giữ truy vấn đếm đồng nhất với truy vấn nội dung. Nếu graph có nhiều relationship, hãy chọn tập node gốc duy nhất trước khi áp dụng offset để mỗi trang đại diện đúng số entity mà API cam kết trả về.

