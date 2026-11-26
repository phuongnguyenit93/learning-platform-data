# Kiểm tra tính tương thích cú pháp trước khi dùng tính năng Cypher mới

Khi dùng Neo4j để lưu trữ **property graph**, lập trình viên thường viết truy vấn Cypher để tìm node, duyệt relationship, lọc thuộc tính và truy vấn đường đi. Một cú pháp mới có thể giúp câu truy vấn ngắn gọn, dễ đọc hoặc mạnh hơn, nhưng không phải mọi máy chủ Neo4j, chế độ ngôn ngữ Cypher, driver và môi trường triển khai đều hỗ trợ cùng một tập tính năng.

Bài này hướng dẫn kiểm tra có hệ thống **một tính năng Cypher mới trước khi đưa vào ứng dụng**. Kết quả mong muốn là bằng chứng rằng truy vấn được phiên bản đích chấp nhận, có ngữ nghĩa đúng, chạy được qua đường kết nối thật và có phương án xử lý khi môi trường chưa tương thích.

## 1. Vì sao cần kiểm tra trước khi sử dụng?

Giả sử nhóm phát triển dùng một cách khai báo biến mới trong subquery. Truy vấn chạy ở máy cá nhân nhưng thất bại trên môi trường kiểm thử vì máy chủ có phiên bản cũ hơn. Hoặc truy vấn được Neo4j Browser chấp nhận nhưng ứng dụng Spring Data Neo4j lại dùng sai tham số, dẫn đến lỗi khi thực thi.

Tính tương thích ở đây có nhiều lớp:

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Cú pháp (parser)** | Máy chủ đích có hiểu từ khóa, dấu ngoặc và cấu trúc câu lệnh không? | `CALL (p) { ... }` có được nhận diện? |
| **Ngữ nghĩa (semantic)** | Câu lệnh hợp lệ về biến, kiểu dữ liệu, phạm vi và quy tắc Cypher không? | Biến `p` có được đưa vào subquery đúng cách? |
| **Tính năng của máy chủ** | Function, procedure, index hoặc thành phần mở rộng cần dùng có tồn tại và được cấp quyền không? | `SHOW FUNCTIONS` có thấy function mong muốn? |
| **Thực thi** | Truy vấn hoạt động với dữ liệu, tham số và giao dịch thực tế không? | Giá trị trả về có đúng khi một node không có relationship? |
| **Tích hợp** | Java Driver, Spring Data Neo4j và cách định tuyến truy vấn có hoạt động như kỳ vọng không? | Truy vấn qua session chỉ định database có thành công? |
| **Hiệu năng** | Execution plan và chi phí duyệt đồ thị có chấp nhận được không? | Truy vấn có quét quá nhiều node hoặc mở rộng quan hệ quá rộng? |

**Biên dịch cú pháp thành công không đồng nghĩa ứng dụng đã tương thích hoàn toàn.** Ví dụ, `EXPLAIN` có thể phân tích và lập kế hoạch truy vấn, nhưng chưa chứng minh kết quả trên dữ liệu thực hoặc hiệu năng của truy vấn.

## 2. Xác định môi trường và ranh giới phiên bản

Trước khi chọn cú pháp mới, cần ghi rõ môi trường nào sẽ chạy câu lệnh: Neo4j Desktop, một instance tự quản lý, Neo4j Aura hay một cụm Neo4j; cơ sở dữ liệu nào; các ứng dụng Java nào đang kết nối; và môi trường nào có phiên bản thấp nhất.

### 2.1. Lấy thông tin phiên bản máy chủ

Trong Neo4j Browser, Cypher Shell hoặc công cụ có quyền chạy truy vấn, có thể thử:

```cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
```

Kết quả giúp nhận diện phiên bản Neo4j và edition mà kết nối hiện tại nhìn thấy. Tính khả dụng và quyền gọi procedure có thể thay đổi theo bản phát hành và cấu hình triển khai. Nếu lệnh không được phép, lấy phiên bản từ giao diện quản trị hoặc thông tin vận hành do nhóm phụ trách cơ sở dữ liệu xác nhận.

Trong **cluster**, một kết nối tới một server không phải là bằng chứng rằng *mọi* thành viên đang cùng phiên bản. Đặc biệt khi rolling upgrade, hãy kiểm tra máy chủ có thể nhận truy vấn theo cả tuyến đọc và tuyến ghi. Với hệ thống dùng nhiều database, phải kiểm tra đúng database đích.

### 2.2. Phân biệt phiên bản Neo4j với phiên bản ngôn ngữ Cypher

Tên phiên bản sản phẩm Neo4j và tên chế độ ngôn ngữ Cypher là hai khái niệm liên quan nhưng không đồng nhất. Những bản phát hành mới có thể cung cấp lựa chọn như **Cypher 5** và **Cypher 25**; khả năng chọn chế độ, cú pháp hợp lệ và mặc định cụ thể phụ thuộc vào phiên bản Neo4j đang sử dụng.

Khi tài liệu mô tả một tính năng mới, cần xác nhận đồng thời:

1. Phiên bản Neo4j **đầu tiên** hỗ trợ tính năng đó.
2. Chế độ ngôn ngữ Cypher có yêu cầu riêng hay không.
3. Tính năng đã được phát hành ổn định, còn thử nghiệm, bị cảnh báo deprecation hay đã thay đổi ngữ nghĩa.
4. Phiên bản tối thiểu của từng môi trường **dev → test → staging → production**.
5. Các phần phụ thuộc như procedure, plugin, quyền và Java Driver.

**Không tự thêm tiền tố `CYPHER 25` để “bật” tính năng trên máy chủ cũ.** Nếu phiên bản máy chủ không hiểu chế độ này, chính tiền tố đó cũng gây lỗi. Chỉ sử dụng tùy chọn phiên bản ngôn ngữ khi đã xác nhận máy chủ hỗ trợ và cú pháp lựa chọn đúng với tài liệu của bản đó.

### 2.3. Đối chiếu đúng nguồn tài liệu

Lập một dòng kiểm tra cho mỗi tính năng muốn áp dụng, lấy thông tin từ *Cypher Manual*, *Operations Manual* và ghi chú phát hành chính thức tương ứng với phiên bản triển khai. Đừng dùng mặc định tài liệu của bản Neo4j mới nhất để khẳng định một bản Neo4j cũ hỗ trợ cùng cú pháp.

Một mẫu ghi nhận ngắn:

| Mục | Giá trị cần điền |
| --- | --- |
| Tính năng mới | Tên cấu trúc Cypher, function hoặc procedure |
| Cú pháp mẫu | Truy vấn tối thiểu lấy từ tài liệu của phiên bản đích |
| Phiên bản và chế độ được hỗ trợ | Ghi rõ theo tài liệu chính thức |
| Môi trường cần hỗ trợ | Dev, test, staging, production và từng cluster |
| Câu lệnh cũ thay thế | Truy vấn tương đương nếu bản đích chưa hỗ trợ |
| Bằng chứng kiểm thử | Kết quả `EXPLAIN`, chạy thử và kiểm tra ứng dụng |

## 3. Quy trình kiểm tra một cú pháp Cypher mới

Một quy trình thực tế nên đi từ **ít phụ thuộc nhất đến gần production nhất**.

### Bước 1 — Chọn một cấu trúc cụ thể

Khoanh đúng cú pháp muốn thử, ví dụ cách khai báo biến được đưa vào `CALL` subquery. Tránh kiểm tra cùng lúc nhiều tính năng mới trong một truy vấn dài, vì khi có lỗi sẽ khó biết nguyên nhân nằm ở đâu.

Mô tả ngắn:

- Cú pháp cũ đang dùng là gì?
- Cú pháp mới giải quyết vấn đề nào?
- Truy vấn dùng trong màn hình/API nào?
- Những phiên bản nào của Neo4j phải chạy được?

### Bước 2 — Tạo truy vấn tối thiểu

Rút truy vấn còn các thành phần bắt buộc để parser nhận diện cú pháp mới. Khi đã có một ví dụ tối thiểu chạy được, mới thêm điều kiện, sắp xếp, tham số, index và logic nghiệp vụ.

### Bước 3 — Dùng `EXPLAIN` trước

Đặt `EXPLAIN` trước truy vấn để Neo4j phân tích cú pháp, kiểm tra các quy tắc ngữ nghĩa cần thiết và dựng execution plan **mà không thực thi câu lệnh**:

```cypher
EXPLAIN
MATCH (p:Person)
RETURN p.name AS name
LIMIT 5;
```

Nếu truy vấn chưa hợp lệ, Neo4j có thể báo lỗi như token không hợp lệ, biến không tồn tại, kiểu dữ liệu không phù hợp hoặc function/procedure chưa được nhận diện. Ghi lại **toàn bộ mã lỗi, thông báo, phiên bản và câu truy vấn**, vì một dòng “syntax error” đơn lẻ không đủ để tìm nguyên nhân.

Đối với truy vấn có tham số, truyền giá trị mẫu với **đúng tên và kiểu** khi kiểm tra. Khả năng lập kế hoạch có thể phụ thuộc vào tham số, dạng biểu thức và phiên bản máy chủ.

### Bước 4 — Đọc cảnh báo và execution plan

Một truy vấn được `EXPLAIN` chấp nhận vẫn có thể sinh cảnh báo. Ví dụ:

- Nhãn node, loại relationship hoặc thuộc tính chưa tồn tại trong schema/dữ liệu mẫu.
- Cú pháp vẫn chạy nhưng đã bị cảnh báo **deprecated**.
- Việc dùng một function, procedure hay cách lập kế hoạch nào đó có giới hạn.
- Plan xuất hiện thao tác quét rộng hoặc mở rộng nhiều relationship.

Cần phân biệt **lỗi chặn truy vấn** với **notification/cảnh báo**. Cảnh báo không phải lúc nào cũng khiến truy vấn thất bại, nhưng cảnh báo deprecation là tín hiệu cần tính đến trước khi nâng cấp phiên bản.

### Bước 5 — Kiểm tra hành vi ở môi trường thử nghiệm

Chạy truy vấn thật trên dataset đại diện, trong đúng database, với đủ trường hợp: dữ liệu có kết quả, không có kết quả, giá trị `null`, property thiếu, nhiều relationship, đường đi dài và tham số không hợp lệ.

Nếu truy vấn có `CREATE`, `MERGE`, `SET` hoặc `DELETE`, hãy dùng dữ liệu thử có thể khôi phục và giao dịch phù hợp. **`PROFILE` thực sự thực thi truy vấn**, nên không chạy `PROFILE` cho câu lệnh ghi trên production nếu chưa kiểm soát ảnh hưởng. Khi chỉ cần xem plan và khả năng lập kế hoạch, ưu tiên `EXPLAIN`.

### Bước 6 — Kiểm tra qua ứng dụng và triển khai

Chạy cùng truy vấn từ Java Driver hoặc Spring Data Neo4j đang được dự án sử dụng. Kiểm tra tham số, cách ánh xạ kết quả, transaction, database đích và định tuyến trong cluster. Chỉ phát hành sau khi toàn bộ môi trường cần hỗ trợ có bằng chứng đạt yêu cầu hoặc đã có phương án tương thích.

## 4. Ví dụ: kiểm tra cú pháp khai báo biến trong `CALL` subquery

Giả sử đồ thị có các node `:Person` và relationship `:KNOWS`. Ta muốn đếm số người một người quen biết.

Trong những phiên bản Neo4j hỗ trợ **variable scope clause**, truy vấn có thể đưa biến từ truy vấn ngoài vào subquery bằng `CALL (p) { ... }`:

```cypher
EXPLAIN
MATCH (p:Person)
CALL (p) {
  MATCH (p)-[:KNOWS]->(f:Person)
  RETURN count(f) AS friendCount
}
RETURN p.name AS personName, friendCount
ORDER BY personName;
```

Ở đây:

- `MATCH (p:Person)` xác định node đầu vào.
- `CALL (p)` khai báo rõ biến `p` được đưa vào phạm vi subquery.
- `MATCH (p)-[:KNOWS]->(f:Person)` duyệt quan hệ từ `p` đến `f`.
- `count(f)` đếm node phù hợp và trả về `friendCount`.
- `RETURN` cuối sử dụng kết quả subquery ở phạm vi bên ngoài.

Cú pháp khai báo biến trong `CALL (...)` được giới thiệu trong dòng Neo4j 5.x về sau; **không thể suy từ việc máy chủ chạy “Neo4j 5” mà kết luận mọi bản 5.x đều nhận cú pháp đó**. Hãy đối chiếu mốc hỗ trợ và dùng `EXPLAIN` trên chính phiên bản đang triển khai.

Nếu một môi trường chưa hỗ trợ cách khai báo trên, một biến thể sử dụng **importing `WITH`** có thể phù hợp với các phiên bản cũ hơn:

```cypher
EXPLAIN
MATCH (p:Person)
CALL {
  WITH p
  MATCH (p)-[:KNOWS]->(f:Person)
  RETURN count(f) AS friendCount
}
RETURN p.name AS personName, friendCount
ORDER BY personName;
```

Hai truy vấn biểu diễn cùng ý định trong ví dụ này, nhưng việc dùng importing `WITH` còn tùy phiên bản và trạng thái deprecation của chế độ Cypher đích. Vì vậy, hãy kiểm tra **từng biến thể** ở những môi trường được yêu cầu hỗ trợ; không xem biến thể cũ là phương án vĩnh viễn cho mọi phiên bản tương lai.

### Dữ liệu minh họa để kiểm tra kết quả

Chỉ chạy phần tạo dữ liệu dưới đây trên **database thử nghiệm** hoặc một môi trường cô lập:

```cypher
CREATE (an:Person {name: 'An'})
CREATE (binh:Person {name: 'Bình'})
CREATE (chi:Person {name: 'Chi'})
CREATE (an)-[:KNOWS]->(binh)
CREATE (an)-[:KNOWS]->(chi);
```

Với dataset chỉ gồm ba người và hai quan hệ này, kết quả mong đợi là:

| personName | friendCount |
| --- | ---: |
| An | 2 |
| Bình | 0 |
| Chi | 0 |

Do subquery sử dụng `count(f)` là biểu thức tổng hợp, kết quả đếm bằng 0 vẫn có thể được trả về đối với người không có relationship phù hợp. Kiểm tra thực tế giúp phát hiện sai khác ngữ nghĩa mà riêng bước xác nhận parser không thể đảm bảo.

**Lưu ý:** Các lệnh `CREATE` bên trên sẽ thêm dữ liệu mỗi lần chạy. Dùng database test sạch hoặc xóa dữ liệu mẫu có chủ đích; không chạy lặp trên kho dữ liệu thật.

## 5. Phân biệt lỗi không tương thích với lỗi khác

Thông báo lỗi thường gợi ý nơi cần kiểm tra tiếp theo:

| Hiện tượng | Nguyên nhân có thể | Việc cần làm |
| --- | --- | --- |
| `Invalid input` / không nhận diện token | Parser không hỗ trợ cú pháp hoặc truy vấn viết sai | Kiểm tra cú pháp tối thiểu và mốc hỗ trợ của máy chủ |
| `Variable ... not defined` | Biến ngoài phạm vi, khai báo subquery thiếu hoặc viết sai tên | Kiểm tra `WITH`, `CALL (...)` và phạm vi biến |
| Function hoặc procedure không tồn tại | Tính năng không có ở bản đích, plugin thiếu, sai tên hoặc bị giới hạn quyền | Tra `SHOW FUNCTIONS` / `SHOW PROCEDURES` và tài liệu đúng bản |
| Truy vấn lập kế hoạch được nhưng chạy lỗi | Dữ liệu, kiểu tham số, ép kiểu hoặc quyền truy cập không phù hợp | Chạy test với tham số/dữ liệu đại diện |
| Chạy được nhưng có deprecation notification | Cú pháp còn nhận nhưng đã có lộ trình thay đổi | Lên kế hoạch chuyển sang cú pháp được khuyến nghị |
| Chạy tốt ở dev nhưng lỗi ở production | Lệch phiên bản, khác chế độ Cypher, khác database hoặc thành phần plugin | Đối chiếu ma trận môi trường và định tuyến thực tế |
| Kết quả đúng nhưng chậm | Plan, index, độ chọn lọc hoặc kích thước đồ thị khác | Đọc `EXPLAIN`; dùng `PROFILE` có kiểm soát trên dữ liệu phù hợp |

Ví dụ, thiếu index thường ảnh hưởng đến **hiệu năng**; không nên tự kết luận một truy vấn `MATCH` báo cảnh báo về index là “sai cú pháp”. Tương tự, một procedure không chạy vì thiếu quyền không nhất thiết chứng tỏ phiên bản máy chủ không hỗ trợ procedure đó.

### Kiểm tra các thành phần sẵn có

Tùy phiên bản và quyền tài khoản, có thể dùng:

```cypher
SHOW FUNCTIONS;
```

```cypher
SHOW PROCEDURES;
```

```cypher
SHOW INDEXES;
```

```cypher
SHOW CONSTRAINTS;
```

Các lệnh này giúp khảo sát function/procedure/schema hiện có; **chúng không thay thế việc thử đúng lời gọi** với đối số và chế độ Cypher đích. Các procedure mở rộng cũng phụ thuộc vào việc cài đặt plugin và cấu hình bảo mật riêng của môi trường.

## 6. Kiểm tra qua Java Driver và Spring Data Neo4j

Một truy vấn chạy trong Neo4j Browser có thể vẫn thất bại từ ứng dụng vì khác user, database, cách truyền tham số hoặc transaction. Với các hệ thống Java, nên có phép thử tích hợp qua cùng driver và cấu hình đang dùng.

Ví dụ dùng **Neo4j Java Driver có API `executeRead`**, chạy `EXPLAIN` từ application:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.summary.ResultSummary;

public class CypherCompatibilityCheck {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        String query = """
            EXPLAIN
            MATCH (p:Person)
            CALL (p) {
              MATCH (p)-[:KNOWS]->(f:Person)
              RETURN count(f) AS friendCount
            }
            RETURN p.name AS personName, friendCount
            """;

        try (Driver driver = GraphDatabase.driver(
                    uri, AuthTokens.basic(username, password));
             Session session = driver.session(
                    SessionConfig.forDatabase("neo4j"))) {
            ResultSummary summary = session.executeRead(
                tx -> tx.run(query).consume()
            );

            System.out.println("Plan available: " + summary.hasPlan());
            summary.notifications().forEach(notification ->
                System.out.println(
                    notification.code() + ": " + notification.description()
                )
            );
        }
    }
}
```

Ý nghĩa phép thử:

- `SessionConfig.forDatabase("neo4j")` yêu cầu dùng database được chỉ định; thay bằng tên database thật.
- `executeRead` gửi truy vấn qua tuyến đọc và chính sách kết nối mà ứng dụng sử dụng.
- `consume()` nhận thông tin tổng kết để xem execution plan và notification.
- Nếu cú pháp không hợp lệ, driver trả về lỗi từ máy chủ; cần lưu mã lỗi và thông điệp.
- Đoạn mã dùng Java hỗ trợ text block và phiên bản Neo4j Java Driver có các API minh họa. Với driver khác đời, điều chỉnh theo tài liệu API đang dùng.

Đây là **phép thử tương thích cú pháp**, nên truy vấn có `EXPLAIN`. Khi muốn xác nhận dữ liệu trả về, bỏ `EXPLAIN` và kiểm tra các record trong một bài kiểm thử riêng, trên database thử nghiệm.

Trong Spring Data Neo4j, cần kiểm tra thêm câu Cypher trong `@Query`, tên tham số `$externalId` có khớp với tên phương thức/`@Param` hay không, entity mapping và transaction được Spring quản lý. Ví dụ:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.externalId = $externalId
    RETURN p
    """)
Optional<Person> findPerson(
    @Param("externalId") String externalId
);
```

Ví dụ repository minh họa cách đối chiếu tham số và mapping; nó không sử dụng cấu trúc `CALL (p)`. Nếu định đưa cú pháp mới vào repository thực tế, phải có bài kiểm thử gọi **chính phương thức repository đang được thay đổi**, với phiên bản server và driver thật.

## 7. Các bẫy tương thích thường gặp

### 7.1. Cho rằng mọi máy chủ có cùng tính năng

Một hệ thống có dev ở phiên bản mới nhưng production ở phiên bản thấp hơn sẽ gặp lỗi khi tính năng mới chỉ được thử trên dev. Ma trận hỗ trợ nên ghi rõ phiên bản từng môi trường, không chỉ ghi “đều dùng Neo4j”.

### 7.2. Nhầm tính năng của Cypher với procedure từ plugin

Truy vấn `CALL some.procedure(...)` có thể phụ thuộc vào plugin hoặc quyền cấu hình, trong khi cấu trúc `CALL { ... }` là cú pháp Cypher. Chúng có thể đều xuất hiện sau từ khóa `CALL` nhưng điều kiện tương thích khác nhau.

### 7.3. Dùng tham số ở vị trí cú pháp không hỗ trợ

Tham số thường dùng cho **giá trị dữ liệu**:

```cypher
MATCH (p:Person)
WHERE p.name = $name
RETURN p;
```

Không mặc nhiên giả định mọi phiên bản đều cho phép viết tên label hoặc relationship bằng một tham số thông thường, ví dụ `MATCH (n:$label)`. Hỗ trợ cấu trúc label/type động thay đổi theo phiên bản và có cú pháp riêng. Khi chưa hỗ trợ, hãy dùng các biến thể truy vấn định sẵn được chọn từ danh sách cho phép ở tầng ứng dụng; không ghép trực tiếp input không tin cậy vào chuỗi Cypher.

### 7.4. Kiểm tra cú pháp bằng `PROFILE` trên dữ liệu thật

`PROFILE` chạy truy vấn để thu số liệu thực thi. Đối với câu lệnh cập nhật, việc này có thể **làm thay đổi đồ thị**. Chỉ dùng `PROFILE` trên dữ liệu và môi trường đã kiểm soát, sau khi truy vấn vượt qua bước `EXPLAIN` và bài kiểm tra chức năng.

### 7.5. Bỏ qua cảnh báo deprecation

Một câu lệnh có thể đang hoạt động nhưng xuất hiện cảnh báo rằng cú pháp sẽ thay đổi hoặc bị loại bỏ. Hãy lưu cảnh báo và đặt kế hoạch chuyển đổi; không chờ đến lần nâng cấp lớn tiếp theo mới phát hiện vấn đề.

### 7.6. Kiểm tra chỉ một đường đi của ứng dụng

Một ứng dụng có thể dùng phiên kết nối đọc, ghi, nhiều database, chạy qua load balancer hoặc nhiều pod. Cần kiểm tra từ nơi thực thi **thực tế**, với quyền của service account thực tế. Nếu môi trường có nhiều máy chủ, phải xét cả trường hợp máy chủ định tuyến đến thành viên khác phiên bản trong lúc nâng cấp.

## 8. Đưa kiểm tra tương thích vào quy trình phát triển

Một nhóm phát triển có thể đặt ngưỡng chấp nhận rõ ràng cho pull request sử dụng cú pháp Cypher mới.

| Giai đoạn | Thử nghiệm | Tiêu chí đạt |
| --- | --- | --- |
| Thiết kế | Đọc tài liệu bản phát hành và liệt kê các môi trường | Có phiên bản tối thiểu, chế độ Cypher và fallback nếu cần |
| Thử cú pháp | `EXPLAIN` trên phiên bản thấp nhất phải hỗ trợ | Không có lỗi cú pháp/ngữ nghĩa; cảnh báo được đánh giá |
| Thử chức năng | Chạy trên database test có trường hợp biên | Kết quả và thay đổi dữ liệu đúng kỳ vọng |
| Thử tích hợp | Java Driver/Spring Data Neo4j gửi truy vấn qua cấu hình thật | Tham số, mapping, database, quyền và transaction đúng |
| Thử hiệu năng | Xem plan; đo trong staging khi cần | Không phát sinh suy giảm vượt ngưỡng dự án |
| Triển khai | So sánh phiên bản/chế độ Cypher trước release | Tất cả môi trường được yêu cầu đã đạt hoặc có lựa chọn tương thích |

Một cách triển khai trong CI là có test chạy với **phiên bản thấp nhất được hỗ trợ** và thêm một môi trường theo phiên bản đích mới. Nếu sản phẩm thực sự cần hỗ trợ hai cú pháp, lưu hai truy vấn tường minh trong code và kiểm tra lựa chọn cú pháp theo cấu hình/khả năng đã được xác nhận. Tránh tự động “thử sai rồi đổi câu lệnh” đối với các câu lệnh ghi vì retry không được kiểm soát có thể làm lặp tác động dữ liệu.

### Mẫu phiếu kiểm tra trước khi merge

```text
Tính năng Cypher mới: ..............................
Truy vấn / commit: .................................
Neo4j tối thiểu phải hỗ trợ: .......................
Chế độ ngôn ngữ Cypher: ...........................
Tài liệu / release note đối chiếu: ...............
Kết quả EXPLAIN: PASS / FAIL
Notification quan trọng: ..........................
Dataset và test chức năng: PASS / FAIL
Java Driver / Spring Data test: PASS / FAIL
Cluster / database / quyền đã kiểm tra: ..........
Fallback hoặc yêu cầu nâng cấp: ...................
Người xác nhận / ngày kiểm tra: ...................
```

## 9. Bài thực hành tự kiểm tra

**Bối cảnh:** Một API cần trả số người quen của mỗi `Person`. Nhóm muốn đổi từ importing `WITH` trong subquery sang `CALL (p)` để cách đưa biến vào phạm vi con rõ ràng hơn.

1. Xác định phiên bản Neo4j của dev và staging, đồng thời ghi chế độ Cypher mà mỗi môi trường hỗ trợ.
2. Chạy `EXPLAIN` với cả hai biến thể trong mục 4. Lưu thông điệp lỗi hoặc notification nếu có.
3. Trên database test sạch, tạo ba node và hai quan hệ như ví dụ; chạy truy vấn không có `EXPLAIN`, so sánh kết quả với bảng kỳ vọng.
4. Chạy truy vấn mới qua Java Driver hoặc phương thức Spring Data Neo4j thực tế, sử dụng đúng database và tài khoản ứng dụng.
5. Nếu bản staging chưa chấp nhận cú pháp mới, chọn **giữ cú pháp tương thích đã kiểm thử** hoặc **nâng cấp máy chủ theo kế hoạch**; ghi rõ lý do trong pull request.
6. Khi nâng cấp xong, chạy lại kiểm tra cho từng môi trường thay vì suy luận từ kết quả trên máy dev.

**Câu hỏi tự đánh giá:**

- Tại sao một truy vấn chạy được trong Neo4j Browser vẫn có thể lỗi khi ứng dụng Java gọi?
- `EXPLAIN` chứng minh được những gì? Điều gì bắt buộc phải kiểm tra bằng truy vấn thực thi?
- Nếu `EXPLAIN` chấp nhận truy vấn nhưng trả deprecation notification, bạn có nên coi đó là “đã hoàn toàn tương thích lâu dài” không?
- Vì sao hỗ trợ **Neo4j 5.x** không đủ để khẳng định mọi cú pháp xuất hiện trong các bản 5.x đều khả dụng?

## 10. Kết luận

Khi tiếp cận một tính năng Cypher mới, hãy **xác nhận mốc phiên bản và chế độ ngôn ngữ**, **thử câu lệnh tối thiểu bằng `EXPLAIN`**, **đọc cảnh báo**, rồi **kiểm tra kết quả thực tế và đường kết nối của ứng dụng**. Đối với hệ thống Neo4j có nhiều môi trường hoặc cluster, tính tương thích phải được chứng minh ở phiên bản thấp nhất cần hỗ trợ, kể cả giai đoạn nâng cấp.

Quy trình này giúp tận dụng cú pháp Cypher mới để truy vấn node, relationship và đường đi trong property graph mà vẫn kiểm soát được rủi ro khi tích hợp với Java Driver, Spring Data Neo4j và môi trường vận hành.
