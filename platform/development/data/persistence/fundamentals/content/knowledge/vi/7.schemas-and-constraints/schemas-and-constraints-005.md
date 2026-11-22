# Giá trị mặc định ở ứng dụng và ở kho lưu trữ

## 1. Giá trị mặc định giải quyết vấn đề gì?

Trong ứng dụng Java quản lý yêu cầu hỗ trợ, mỗi yêu cầu mới có **tiêu đề**, **trạng thái**, **độ ưu tiên**, **thời điểm tạo** và **số lần xử lý lại**. Người dùng chỉ cần nhập tiêu đề; những thông tin còn lại có thể được hệ thống khởi tạo tự động.

Ví dụ khi tạo yêu cầu “Không đăng nhập được”, hệ thống có thể áp dụng:

| Thuộc tính | Giá trị khởi tạo mong muốn | Lý do |
| --- | --- | --- |
| subject | Người dùng phải cung cấp | Không thể suy ra nội dung yêu cầu |
| status | OPEN | Yêu cầu mới chưa được xử lý |
| priority | NORMAL | Mức ưu tiên thông thường nếu chưa chọn |
| created_at | Thời điểm hệ thống ghi nhận | Phục vụ lịch sử và kiểm toán |
| attempt_count | 0 | Chưa có lần xử lý lại nào |
| assignee_id | NULL | Chưa được phân công |

Nhưng ai sẽ đặt giá trị đó? Giao diện, API Java, service nghiệp vụ hay cơ sở dữ liệu? Khi nhiều chương trình cùng ghi vào một kho lưu trữ, câu trả lời có ảnh hưởng trực tiếp đến **tính nhất quán của dữ liệu bền vững**.

**Giá trị mặc định (default value)** là giá trị hệ thống dùng khi một giá trị **không được cung cấp trong ngữ cảnh mà quy tắc mặc định áp dụng**. Cần phân biệt rõ:

- **Mặc định ở ứng dụng:** Java hoặc tầng giao diện chủ động chọn và truyền giá trị.
- **Mặc định ở kho lưu trữ:** cơ sở dữ liệu tự điền giá trị theo định nghĩa cột hoặc cơ chế sinh dữ liệu khi lệnh ghi không cung cấp giá trị cho cột theo cú pháp của hệ quản trị.
- **Giá trị được chỉ định tường minh:** người gọi yêu cầu một giá trị cụ thể, kể cả NULL nếu hợp đồng cho phép.
- **Giá trị suy ra bằng quy tắc nghiệp vụ:** phụ thuộc ngữ cảnh, quyền, trạng thái hay dữ liệu khác; không phải lúc nào cũng nên xử lý như một DEFAULT đơn giản.

Bài học thuộc chương **Lược đồ và ràng buộc** của học phần **DATA_PERSISTENCE_FUNDAMENTALS**. Đây là một phần quan trọng trong thiết kế ranh giới persistence của Java: lược đồ và ứng dụng cần có hợp đồng rõ về cách tạo dữ liệu, kiểm tra ràng buộc, chuyển đổi schema và xử lý các nguồn ghi khác nhau.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích khi nào mặc định ở Java và khi nào mặc định trong cơ sở dữ liệu được áp dụng.
2. Phân biệt **bỏ qua cột**, **ghi NULL**, **ghi giá trị cụ thể** và dùng từ khóa SQL **DEFAULT**.
3. Viết DDL và INSERT trong PostgreSQL để sử dụng mặc định đúng cách.
4. Xây dựng đường ghi JDBC và nhận lại giá trị do database thực sự sinh ra.
5. Nhận diện cách ORM, migration, thời gian hệ thống và nhiều nguồn ghi gây sai lệch mặc định.
6. Chọn vị trí đặt quy tắc mặc định phù hợp với tính toàn vẹn, bảo mật và khả năng tiến hóa lược đồ.

## 2. Một giá trị có thể đi qua nhiều lớp mặc định

Giả sử người dùng tạo yêu cầu mà không chọn độ ưu tiên. Dữ liệu có thể đi qua:

~~~mermaid
flowchart TD
    UI["Giao diện / Client"] --> API["API Java: parse và validate"]
    API --> SERVICE["Service: áp dụng quy tắc nghiệp vụ"]
    SERVICE --> REPO["Repository: tạo câu lệnh ghi"]
    REPO --> DB["Database: DEFAULT và CONSTRAINT"]
    DB --> RESULT["Bản ghi đã lưu / phản hồi API"]
~~~

Mỗi lớp có mục đích khác nhau:

| Lớp | Ví dụ mặc định | Ai chịu trách nhiệm? |
| --- | --- | --- |
| Giao diện | Hiển thị sẵn mức ưu tiên NORMAL | Hỗ trợ thao tác người dùng; không bảo đảm dữ liệu đã lưu |
| API / DTO | Nếu trường không có, chọn một ý nghĩa rõ ràng theo hợp đồng | Chuẩn hóa yêu cầu từ client |
| Service nghiệp vụ | Loại yêu cầu A mặc định HIGH, loại B mặc định NORMAL | Quy tắc phụ thuộc ngữ cảnh |
| Repository / ORM | Quyết định cột nào được đưa vào INSERT | Xác định cơ sở dữ liệu có cơ hội áp dụng DEFAULT hay không |
| Database | DEFAULT 'OPEN', DEFAULT CURRENT_TIMESTAMP | Bảo vệ giá trị khởi tạo ngay cả từ nguồn ghi ngoài Java |
| Ràng buộc dữ liệu | NOT NULL, CHECK, FOREIGN KEY | Từ chối trạng thái không hợp lệ; không tự thay bằng giá trị đúng |

Ví dụ, một form hiển thị NORMAL chưa bảo đảm rằng client bên thứ ba cũng sẽ gửi NORMAL. Ngược lại, database có **DEFAULT 'NORMAL'** nhưng Java luôn INSERT giá trị **'HIGH'** thì database sẽ lưu HIGH theo giá trị được gửi, không “thắng” Java.

**Nguyên tắc quan trọng:** mặc định không có thứ tự ưu tiên toàn cục kiểu “Java trước, database sau”. Kết quả phụ thuộc vào **đường đi thực tế của dữ liệu** và **câu lệnh INSERT/UPDATE được phát ra**.

## 3. Lược đồ minh họa trong PostgreSQL

Bài sử dụng bảng **support_ticket**. Các ví dụ SQL bên dưới dành cho **PostgreSQL**; cú pháp và hành vi chi tiết ở các hệ quản trị khác có thể khác.

~~~sql
CREATE TABLE support_ticket (
    ticket_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    subject VARCHAR(200) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')),

    priority VARCHAR(10) NOT NULL DEFAULT 'NORMAL'
        CHECK (priority IN ('LOW', 'NORMAL', 'HIGH')),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),

    assignee_id BIGINT
);
~~~

Quan sát từng cột:

- **ticket_id:** cơ sở dữ liệu sinh định danh qua cơ chế **IDENTITY**. Đây là cơ chế sinh giá trị ở kho lưu trữ; nó không đồng nghĩa với một DEFAULT chuỗi hay số cố định.
- **subject:** không có DEFAULT và có NOT NULL; ứng dụng phải cung cấp nội dung.
- **status:** mặc định OPEN, chỉ chấp nhận một trong ba trạng thái cho phép.
- **priority:** mặc định NORMAL, chỉ chấp nhận LOW/NORMAL/HIGH.
- **created_at:** giá trị thời gian được database xác định tại lúc xử lý giao dịch theo ngữ nghĩa của CURRENT_TIMESTAMP.
- **attempt_count:** bắt đầu từ 0; giá trị âm bị CHECK từ chối.
- **assignee_id:** có thể NULL và không khai báo DEFAULT. Nếu bỏ qua cột khi INSERT, giá trị của cột sẽ là NULL.

Đoạn DDL cho thấy **DEFAULT** và **constraint** có vai trò khác nhau: DEFAULT chọn giá trị khi cần; **NOT NULL** và **CHECK** từ chối giá trị không hợp lệ. DEFAULT 'OPEN' không ngăn ứng dụng cố tình INSERT một trạng thái lạ; CHECK mới làm việc đó.

### 3.1. Một dạng mặc định có thể là biểu thức

Trong PostgreSQL, biểu thức DEFAULT có thể sử dụng hằng, phép toán hoặc hàm được cho phép. Chẳng hạn:

~~~sql
created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
~~~

Cơ sở dữ liệu tính biểu thức tại thời điểm có yêu cầu áp dụng mặc định, theo ngữ nghĩa của hàm. Không phải mọi biểu thức đều phù hợp: mặc định sinh từ dữ liệu bên ngoài hoặc phụ thuộc ngữ cảnh xác thực thường cần được thực hiện ở service hoặc qua cơ chế database chuyên biệt.

Không nên nhầm **DEFAULT** với **generated column** (cột tính từ biểu thức theo quy tắc của hệ quản trị), **trigger** (logic có thể chạy theo sự kiện ghi), hoặc **IDENTITY** (sinh ID). Chúng có mục tiêu và ràng buộc khác nhau.

## 4. Bốn tình huống INSERT phải phân biệt

Đây là phần dễ gây lỗi nhất khi thiết kế mặc định.

### 4.1. Không nêu cột trong INSERT: DEFAULT được áp dụng

~~~sql
INSERT INTO support_ticket (subject)
VALUES ('Không đăng nhập được')
RETURNING ticket_id, subject, status, priority,
          created_at, attempt_count, assignee_id;
~~~

Với lược đồ trên, bản ghi mới nhận:

| Cột | Kết quả |
| --- | --- |
| subject | Không đăng nhập được |
| status | OPEN |
| priority | NORMAL |
| created_at | Thời điểm do PostgreSQL cung cấp |
| attempt_count | 0 |
| assignee_id | NULL |
| ticket_id | ID được sinh tự động |

Đây là đường đi đúng nếu muốn database chịu trách nhiệm khởi tạo status, priority, created_at và attempt_count. **RETURNING** giúp ứng dụng biết giá trị thực tế đã lưu ngay sau INSERT.

### 4.2. Nêu cột và truyền giá trị cụ thể: giá trị đó được sử dụng

~~~sql
INSERT INTO support_ticket (subject, priority)
VALUES ('Lỗi thanh toán', 'HIGH')
RETURNING ticket_id, priority;
~~~

**priority = HIGH** là lựa chọn tường minh của ứng dụng và không bị DEFAULT 'NORMAL' thay thế. **status**, **created_at** và **attempt_count** vẫn được mặc định vì không có trong danh sách cột.

Nếu giá trị được gửi vi phạm CHECK, ví dụ **priority = 'URGENT'** trong lược đồ hiện tại, PostgreSQL sẽ từ chối INSERT. Mặc định không phải cơ chế tự sửa dữ liệu không hợp lệ.

### 4.3. Nêu cột và truyền NULL: không kích hoạt DEFAULT

~~~sql
-- Thất bại do priority NOT NULL
INSERT INTO support_ticket (subject, priority)
VALUES ('Không mở được trang', NULL);
~~~

Dù cột có **DEFAULT 'NORMAL'**, truyền **NULL** là một giá trị tường minh trong SQL. PostgreSQL không tự biến NULL thành NORMAL; thay vào đó, ràng buộc **NOT NULL** được kiểm tra và thao tác thất bại.

Nếu cột cho phép NULL, câu lệnh tương tự sẽ ghi **NULL**, không ghi mặc định. Việc này ảnh hưởng quan trọng tới cách Java dùng **setNull**, đối tượng ORM có trường null và cách API diễn giải dữ liệu thiếu.

### 4.4. Dùng từ khóa DEFAULT tường minh

~~~sql
INSERT INTO support_ticket (subject, priority)
VALUES ('Yêu cầu đổi mật khẩu', DEFAULT);

-- Với một hàng đã tồn tại, chủ động đặt lại status theo mặc định hiện hành:
UPDATE support_ticket
SET status = DEFAULT
WHERE ticket_id = 42;
~~~

Từ khóa SQL **DEFAULT** yêu cầu database áp dụng biểu thức mặc định. Trong UPDATE, **SET status = DEFAULT** chủ động gán lại status, còn **UPDATE chỉ sửa subject** không tự chạy lại DEFAULT cho status.

Một điểm khác: lệnh **INSERT INTO support_ticket DEFAULT VALUES** trong PostgreSQL sẽ thất bại với lược đồ hiện tại vì **subject** không có giá trị mặc định và không được phép NULL. DEFAULT không làm tất cả cột trở thành tùy chọn.

### 4.5. Bảng quyết định hành vi

| Câu lệnh hoặc thao tác | Giá trị priority sẽ lưu |
| --- | --- |
| INSERT chỉ có subject | NORMAL |
| INSERT priority = 'HIGH' | HIGH |
| INSERT priority = DEFAULT | NORMAL |
| INSERT priority = NULL | Bị từ chối vì NOT NULL |
| UPDATE subject, bỏ qua priority | Giữ nguyên priority cũ |
| UPDATE priority = DEFAULT | Đặt về DEFAULT hiện hành |

Những quy tắc này là lý do chính phải quan sát **SQL thực tế** được repository/ORM phát ra, thay vì suy đoán chỉ từ DDL hoặc giá trị trong đối tượng Java.

## 5. Mặc định ở Java khác mặc định ở database như thế nào?

### 5.1. Java có mặc định của ngôn ngữ, nhưng không có nghĩa đó là mặc định nghiệp vụ

Java tự khởi tạo các trường (instance fields) theo giá trị mặc định ngôn ngữ:

| Kiểu trường | Giá trị khi chưa được gán |
| --- | --- |
| int, long và các số nguyên primitive | 0 |
| boolean | false |
| double, float | 0.0 |
| Kiểu tham chiếu như String, BigDecimal, Instant | null |

**Biến cục bộ** trong phương thức Java không được tự động sử dụng trước khi được khởi tạo; compiler yêu cầu chúng được gán khi cần thiết.

Số **0** mặc định của trường kiểu int chỉ là hành vi của JVM. Nó **không chứng minh** rằng số lần xử lý lại thực sự bằng 0 theo nghiệp vụ, và càng không có nghĩa database sẽ dùng DEFAULT khi ứng dụng INSERT 0.

Ví dụ lỗi thường gặp: một entity có **int attemptCount** bằng 0 ngay từ khi khởi tạo; ORM đưa cột **attempt_count = 0** vào INSERT. Database nhận giá trị tường minh 0 và không có dịp áp dụng biểu thức DEFAULT của cột đó.

### 5.2. Khởi tạo ở constructor hoặc factory

Ứng dụng có thể xác định giá trị mặc định khi tạo đối tượng. Ví dụ:

~~~java
import java.util.Objects;

enum Priority {
    LOW, NORMAL, HIGH
}

record NewTicket(String subject, Priority priority) {
    NewTicket {
        Objects.requireNonNull(subject, "subject");
        if (subject.isBlank()) {
            throw new IllegalArgumentException("subject is blank");
        }

        if (priority == null) {
            priority = Priority.NORMAL;
        }
    }
}
~~~

Khi khởi tạo **new NewTicket("Lỗi kết nối", null)**, DTO nhận **Priority.NORMAL**. Cách này phù hợp nếu hợp đồng ứng dụng quy định rằng *không chọn độ ưu tiên* đồng nghĩa *NORMAL* và ứng dụng cần sử dụng giá trị đó trước khi ghi.

Nhược điểm là mọi đường ghi khác nhau phải áp dụng quy tắc một cách đồng nhất. Nếu một ứng dụng import dữ liệu, một script SQL và một service khác không dùng constructor Java, chúng có thể tạo dữ liệu khác nếu database không bảo vệ quy tắc chung.

### 5.3. Chọn một nơi quyết định ngữ nghĩa, rồi đồng bộ các lớp

Có thể đặt **mặc định giao tiếp** ở ứng dụng và **fallback cuối cùng** ở database cùng giá trị, nhưng không được xem hai định nghĩa độc lập là hai “nguồn sự thật” ngang nhau. Cần chọn ai có quyền quyết định chính sách và có kiểm thử chống sai lệch.

Ví dụ: cả Java lẫn database đang dùng NORMAL. Sau một đợt thay đổi sản phẩm, Java đổi thành HIGH cho yêu cầu loại A nhưng database vẫn mặc định NORMAL. Điều này có thể đúng nếu yêu cầu loại A là ngoại lệ có chủ đích; cũng có thể là lỗi nếu hệ thống mong mọi yêu cầu mới đều HIGH. Phải có tài liệu phân biệt **mặc định chung** và **ngoại lệ theo ngữ cảnh**.

## 6. “Không cung cấp”, “NULL” và “xóa giá trị” ở tầng API

Một HTTP JSON payload có thể có ba trạng thái nghiệp vụ:

~~~json
{"subject": "Lỗi màn hình"}                

{"subject": "Lỗi màn hình", "priority": null}

{"subject": "Lỗi màn hình", "priority": "HIGH"}
~~~

Về ý định, các trạng thái có thể là:

1. Trường **vắng mặt**: người gọi không quyết định giá trị; có thể áp dụng mặc định.
2. Trường **có mặt với null**: người gọi yêu cầu giá trị trống, hoặc vi phạm hợp đồng nếu cột không cho phép NULL.
3. Trường **có mặt với giá trị**: yêu cầu dùng giá trị cụ thể.

Tuy nhiên, nếu bind hai payload đầu vào cùng một trường Java **String priority** thì cả hai có thể trở thành **null**. Framework deserialize không tự bảo đảm giữ được phân biệt giữa **absent** và **explicit null**.

Nếu API cần phân biệt, phải dùng một mô hình có khả năng theo dõi **presence**: ví dụ DTO có cờ **fieldPresent**, loại dữ liệu bao hàm trạng thái chưa cung cấp, hoặc API layer đọc cấu trúc JSON và kiểm tra sự tồn tại của key trước khi mapping. Tránh dựa vào một sentinel như chuỗi rỗng nếu chưa có hợp đồng rõ.

### 6.1. POST và PATCH không có mặc định giống nhau

Ở POST tạo mới, trường không được cung cấp có thể lấy giá trị mặc định.

Ở PATCH cập nhật từng phần, trường **không xuất hiện** thường có ý nghĩa **giữ nguyên giá trị hiện tại**. Trường **xuất hiện với null** có thể được hiểu là yêu cầu xóa giá trị nếu cột cho phép. Không nên áp dụng lại default của POST mỗi lần PATCH, nếu không một thao tác sửa tiêu đề có thể vô tình đổi độ ưu tiên hoặc trạng thái.

Ví dụ:

~~~json
{"subject": "Cập nhật mô tả lỗi"}
~~~

Một PATCH như vậy không nên âm thầm đặt status lại OPEN hay priority lại NORMAL. Trên SQL, việc **không SET** cột status/priority trong UPDATE sẽ giúp giữ nguyên giá trị cũ.

## 7. Để PostgreSQL sinh mặc định qua JDBC

Nếu database là nơi chịu trách nhiệm khởi tạo **priority** khi không được chỉ định, repository Java phải **bỏ cột priority ra khỏi INSERT**. Việc truyền Java null qua PreparedStatement không tương đương bỏ cột.

Ví dụ dưới đây dùng PostgreSQL **RETURNING** và pgJDBC để lấy các giá trị được lưu:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;

public final class TicketRepository {
    public record TicketCreated(
            long id,
            String status,
            String priority,
            Instant createdAt
    ) {}

    public TicketCreated insert(
            Connection connection,
            String subject,
            String requestedPriority
    ) throws SQLException {
        boolean hasPriority = requestedPriority != null;

        String sql = hasPriority
                ? """
                  INSERT INTO support_ticket (subject, priority)
                  VALUES (?, ?)
                  RETURNING ticket_id, status, priority, created_at
                  """
                : """
                  INSERT INTO support_ticket (subject)
                  VALUES (?)
                  RETURNING ticket_id, status, priority, created_at
                  """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setString(1, subject);
            if (hasPriority) {
                ps.setString(2, requestedPriority);
            }

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("INSERT returned no row");
                }

                OffsetDateTime storedTime =
                        rs.getObject("created_at", OffsetDateTime.class);

                return new TicketCreated(
                        rs.getLong("ticket_id"),
                        rs.getString("status"),
                        rs.getString("priority"),
                        storedTime.toInstant()
                );
            }
        }
    }
}
~~~

Giới hạn của ví dụ:

- **requestedPriority == null** được quy ước là **không cung cấp**. Đường ghi này không biểu diễn một yêu cầu “ghi NULL tường minh”; nếu cần, hợp đồng method phải được thiết kế phong phú hơn.
- Ứng dụng phải validate **subject** và priority theo chính sách trước khi gọi; database vẫn áp dụng NOT NULL/CHECK như lớp bảo vệ cuối.
- JDBC **PreparedStatement** giúp bind giá trị, không cần nối trực tiếp nội dung người dùng vào SQL.
- **RETURNING** là cú pháp PostgreSQL; cơ sở dữ liệu khác có cơ chế trả khóa/giá trị sinh tương ứng.
- Đoạn code nhận **Connection** từ bên ngoài; vòng đời kết nối và giao dịch do tầng gọi quản lý.
- pgJDBC cho phép đọc **TIMESTAMPTZ** dưới dạng **OffsetDateTime**; chuyển sang **Instant** giúp xử lý thời điểm tuyệt đối trong Java.

Nếu muốn database tự chọn **status** và **priority**, cần đọc lại **giá trị database thực sự trả về**. Không nên tự suy diễn các giá trị đã lưu theo constructor nếu có trigger, thay đổi default hoặc đường ghi khác.

### 7.1. Vì sao không dùng setNull để kích hoạt DEFAULT?

Đoạn sau không dùng mặc định trong lược đồ hiện tại:

~~~java
PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO support_ticket (subject, priority) VALUES (?, ?)"
);
ps.setString(1, "Lỗi đăng nhập");
ps.setNull(2, java.sql.Types.VARCHAR);
ps.executeUpdate();  // NOT NULL violation
~~~

Vì INSERT đã nêu cột priority và truyền NULL, database từ chối. Nếu muốn áp dụng mặc định, có thể dùng câu SQL bỏ cột **priority** như ví dụ ở trên, hoặc đặt **DEFAULT** đúng cú pháp SQL. Không thể bind chuỗi **"DEFAULT"** như một tham số và mong nó trở thành từ khóa SQL; giá trị đó là một chuỗi dữ liệu.

## 8. ORM: mặc định có thể bị che khuất bởi INSERT sinh tự động

Khi dùng JPA/Hibernate, câu lệnh INSERT được tạo từ các entity và mapping. Điều này có thể khác với điều người viết DDL kỳ vọng.

### 8.1. Khởi tạo trường Java

Ví dụ:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "support_ticket")
public class SupportTicketEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "ticket_id")
    private Long id;

    @Column(name = "subject", nullable = false)
    private String subject;

    @Column(name = "status", nullable = false)
    private String status = "OPEN";

    @Column(name = "priority", nullable = false)
    private String priority = "NORMAL";
}
~~~

Nếu ORM INSERT cả status và priority với các giá trị này thì **database DEFAULT** không được sử dụng cho hai cột đó. Đó có thể là thiết kế đúng nếu ứng dụng chủ động sở hữu mặc định; nhưng phải hiểu rõ nó.

Nếu bỏ initializer mà ORM vẫn đưa **status = NULL** vào INSERT, DEFAULT ở database cũng **không** có cơ hội chạy và NOT NULL có thể làm thao tác thất bại.

### 8.2. Những cơ chế phụ thuộc Hibernate

Hibernate có các tính năng như **@DynamicInsert** để sinh câu INSERT chỉ gồm một số cột có giá trị, và **@ColumnDefault** để diễn đạt default ở DDL theo cách Hibernate hỗ trợ. Chi tiết việc sinh schema, SQL và đồng bộ giá trị vào entity phụ thuộc phiên bản, mapping và cấu hình.

Một số điểm cần kiểm chứng khi áp dụng:

- **@ColumnDefault** không tự bảo đảm đối tượng Java có trường được khởi tạo và không đồng nghĩa một câu lệnh INSERT sẽ bỏ qua cột.
- **@DynamicInsert** là tính năng Hibernate, không phải annotation JPA chuẩn; việc cột null bị bỏ qua có thể làm DEFAULT ở database được áp dụng, nhưng phải xem lại hợp đồng NULL tường minh.
- **insertable = false** có thể khiến ORM bỏ cột khỏi INSERT, nhưng cũng có nghĩa ứng dụng không thể ghi giá trị tường minh qua mapping cột đó theo cách thông thường.
- Giá trị do database sinh sau INSERT không nhất thiết tự hiện ngay trong entity đang quản lý; tùy mapping và cơ chế ORM, có thể cần hỗ trợ generated value hoặc **refresh** để đồng bộ.
- Các annotation **@PrePersist**, constructor, field initializer hay builder có thể áp dụng default ở phía ứng dụng trước khi câu INSERT được tạo.

Chỉ dùng một annotation nhìn có vẻ hợp lý là chưa đủ. Khi thay đổi default, hãy **ghi log SQL trong môi trường phát triển và thử INSERT thực tế**, xác minh cột có bị đưa vào câu lệnh hay không và entity nhận lại giá trị nào.

### 8.3. Vấn đề đặc biệt với primitive

Nếu entity có **private int attemptCount;**, giá trị mặc định Java là **0**. Nhiều cách mapping sẽ INSERT **0** và không dùng DEFAULT 0 của database. Hai giá trị tình cờ giống nhau trong phiên bản đầu tiên có thể che giấu sự không nhất quán về chủ sở hữu mặc định.

Đổi DEFAULT của database từ 0 thành 1 sau này sẽ không làm những đường Java vẫn ghi 0 tự động đổi theo. Nếu 0 có ý nghĩa nghiệp vụ riêng, cần thiết kế rõ ai quyết định và cách versioning hoạt động.

## 9. Chọn nơi đặt mặc định theo bản chất dữ liệu

Không có câu trả lời “mọi giá trị mặc định đều nên ở Java” hay “đều nên ở database”. Bảng dưới là điểm xuất phát để đánh giá:

| Loại giá trị | Cách đặt thường phù hợp | Điều cần xác định |
| --- | --- | --- |
| ID được database sinh | IDENTITY hoặc cơ chế sinh ID ở database | Không kỳ vọng ID liên tục, không có khoảng trống |
| Thời điểm tạo do kho lưu trữ ghi nhận | Database DEFAULT CURRENT_TIMESTAMP | Đồng bộ cách đọc múi giờ, transaction time |
| Thời điểm sự kiện do người dùng/thiết bị quan sát | Ứng dụng truyền giá trị sự kiện, database validate | Không thay thời điểm nghiệp vụ bằng thời điểm INSERT |
| Trạng thái mới chung cho mọi nguồn ghi | DEFAULT tại database, API có thể hiển thị trước | Chính sách duy nhất, tránh sai lệch với ORM |
| Mức ưu tiên theo gói dịch vụ hoặc loại sự cố | Service nghiệp vụ | Phụ thuộc dữ liệu ngữ cảnh, cần kiểm tra quyền |
| Số lần xử lý lại ban đầu | DEFAULT 0 hoặc ứng dụng set 0 nhất quán | Không được tự thay đổi khi UPDATE không liên quan |
| Tenant ID, user ID, owner ID | Context đã xác thực, cơ chế bắt buộc phù hợp | Không lấy giá trị mặc định tùy tiện gây lộ dữ liệu |
| Quyền truy cập, vai trò | Chính sách cấp quyền minh bạch, ưu tiên an toàn | Tránh đặc quyền mặc định rộng hơn dự kiến |
| Tham số giao diện như số hàng/trang | Ứng dụng / API | Thường không cần ghi một default cố định vào mỗi hàng |
| Tiền tệ của đơn hàng | Theo hợp đồng và nghiệp vụ, có thể lưu giá trị rõ ràng | Không mặc định VND cho giao dịch đa tiền tệ nếu thiếu ngữ cảnh |

Chẳng hạn, mặc định **priority = NORMAL** ở database là hợp lý khi áp dụng chung và có nhiều nguồn ghi. Nhưng nếu ticket được phân loại theo mức cam kết dịch vụ, một service có thể cần tính priority theo tenant và loại sự cố, rồi INSERT giá trị tường minh để dữ liệu phản ánh đúng nghiệp vụ.

**Quy tắc phối hợp:** xác định **bên sở hữu chính sách**, nơi thực thi, nguồn ghi được phép và cách kiểm thử. Nếu có nhiều bản sao của mặc định, chúng phải được duy trì đồng bộ có chủ đích.

## 10. Mặc định thời gian, ID và thứ tự sự kiện

### 10.1. Đồng hồ ứng dụng và đồng hồ cơ sở dữ liệu

Hai ứng dụng Java chạy trên hai máy có thể có lệch đồng hồ. Nếu ứng dụng tự ghi:

~~~java
import java.time.Clock;
import java.time.Instant;

Instant timeFromApp = Clock.systemUTC().instant();
~~~

thời điểm được quyết định bởi máy chạy Java. Dùng **Clock** được inject vào service giúp kiểm thử thời gian và tránh phụ thuộc trực tiếp vào đồng hồ hệ thống.

Nếu database định nghĩa **created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP**, thời điểm được quyết định theo đồng hồ và ngữ nghĩa giao dịch ở database. Đây thường là lựa chọn thuận tiện để mọi nguồn ghi dùng cùng một điểm quy chiếu, nhưng **không có nghĩa** thời điểm đó chính xác tuyệt đối với thời gian thực hoặc giống hệt thời điểm client tạo sự kiện.

Trong PostgreSQL, **CURRENT_TIMESTAMP** tương ứng thời điểm bắt đầu **giao dịch hiện tại**. Các INSERT trong cùng một giao dịch dài có thể nhận cùng timestamp, kể cả xảy ra ở những thời điểm thực thi khác nhau. Nếu cần thời điểm thực tế tại mỗi lời gọi, PostgreSQL có những hàm thời gian khác như **clock_timestamp()**, với tính chất và chi phí riêng.

### 10.2. Múi giờ và kiểu dữ liệu

**TIMESTAMPTZ** trong PostgreSQL biểu diễn thời điểm tuyệt đối; giá trị hiển thị có thể phụ thuộc múi giờ phiên truy vấn. Trong Java, **Instant** phù hợp để trao đổi thời điểm tuyệt đối; **OffsetDateTime** cũng thường được driver hỗ trợ. Không nên dựa vào chuỗi hiển thị theo múi giờ cục bộ làm khóa so sánh lịch sử.

Một default kiểu **CURRENT_DATE** có thể phụ thuộc múi giờ của phiên khi diễn giải “ngày hiện tại”. Khi nghiệp vụ dùng ngày làm việc theo một khu vực, phải định nghĩa rõ zone nghiệp vụ thay vì chỉ dùng ngày của máy chủ.

### 10.3. ID không phải đồng hồ

**GENERATED ALWAYS AS IDENTITY** giúp tạo ID duy nhất theo cơ chế của PostgreSQL. ID **không nhất thiết liên tục hoặc tăng theo đúng thứ tự commit**: rollback, cache sequence và ghi đồng thời có thể làm xuất hiện khoảng trống hoặc thứ tự quan sát khác kỳ vọng.

Không dùng ID như bằng chứng chắc chắn về thời điểm tạo hay để suy ra tính liên tiếp của sự kiện. Khi cần thứ tự truy vấn, chỉ định **ORDER BY created_at, ticket_id** hoặc quy tắc nghiệp vụ phù hợp, đồng thời hiểu giới hạn của timestamp khi có đồng thời.

### 10.4. DEFAULT cho created_at không tự cập nhật updated_at

Nếu thêm cột:

~~~sql
updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
~~~

mặc định này chỉ khởi tạo giá trị khi INSERT áp dụng default. Nó **không tự cập nhật** khi chạy UPDATE sau đó.

Để phản ánh thời điểm sửa cuối, ứng dụng cần gửi **updated_at** khi cập nhật, hoặc database cần cơ chế như trigger phù hợp. Phải làm rõ trường là **thời gian tạo**, **thời gian sửa**, **thời gian sự kiện** hay **thời gian đồng bộ**, vì mỗi loại có ngữ nghĩa khác nhau.

## 11. Giá trị mặc định không thay thế ràng buộc dữ liệu

Một default hợp lệ không ngăn người ghi chủ động gửi giá trị sai.

~~~sql
-- Có DEFAULT 'OPEN', nhưng vẫn cần CHECK để chặn trạng thái không hợp lệ.
status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
    CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED'))
~~~

Các loại ràng buộc chính:

- **NOT NULL:** không cho ghi thiếu/NULL ở cột bắt buộc.
- **CHECK:** xác minh điều kiện trên giá trị, chẳng hạn attempt_count >= 0.
- **UNIQUE:** chặn trùng giá trị theo quy tắc hệ quản trị.
- **FOREIGN KEY:** bảo vệ liên kết đến bản ghi hợp lệ.
- **PRIMARY KEY:** định danh hàng duy nhất và không NULL.

**DEFAULT 0** không đảm bảo attempt_count luôn không âm; **CHECK (attempt_count >= 0)** mới ngăn ghi số âm. **DEFAULT 'OPEN'** không thể kiểm soát liệu trạng thái được phép chuyển thẳng từ OPEN sang RESOLVED hay không; điều đó là **quy tắc chuyển trạng thái** cần kiểm soát riêng.

### 11.1. Cẩn trọng với mặc định bảo mật

Không đặt mặc định “admin”, “public” hay tenant chung để làm cho INSERT dễ thành công. Nếu hệ thống không xác định được quyền sở hữu hay phạm vi truy cập từ thông tin đã xác thực, việc ghi nên bị từ chối hoặc được xử lý theo chính sách rõ ràng.

Ngay cả DEFAULT 'PRIVATE' ở database cũng chỉ là một lớp bảo vệ. Kiểm soát quyền trên **đường truy cập dữ liệu**, truy vấn và thao tác ghi vẫn cần được thực thi ở các tầng phù hợp.

### 11.2. Mặc định có thể che giấu dữ liệu bị thiếu

Ví dụ, nếu hợp đồng yêu cầu người tạo ticket phải chọn **channel** là WEB hoặc PHONE, việc đặt **DEFAULT 'WEB'** có thể khiến client gửi thiếu channel vẫn tạo ra bản ghi trông hợp lệ nhưng sai sự thật. Trong trường hợp này, dùng **NOT NULL** mà không có DEFAULT và validate ở API có thể đúng hơn.

Không nên đặt DEFAULT chỉ để giảm lỗi NOT NULL. Hãy hỏi: **“Nếu nguồn ghi thực sự không biết giá trị này, mặc định có còn trung thực với nghiệp vụ không?”**

## 12. Thay đổi mặc định khi tiến hóa schema

Giá trị mặc định thường được định nghĩa trong DDL nên thay đổi nó là một phần của **schema migration**. Ví dụ sản phẩm quyết định ticket mới phải có ưu tiên HIGH thay vì NORMAL.

Trong PostgreSQL:

~~~sql
ALTER TABLE support_ticket
ALTER COLUMN priority SET DEFAULT 'HIGH';
~~~

Sau khi migration có hiệu lực:

- Những **INSERT mới bỏ qua priority** sẽ nhận HIGH.
- Những INSERT mới có **priority = DEFAULT** cũng dùng HIGH.
- Những INSERT ghi tường minh **priority = 'NORMAL'** vẫn ghi NORMAL vì đó là giá trị hợp lệ trong CHECK.
- Những hàng **đã lưu** không tự đổi từ NORMAL sang HIGH chỉ vì chạy **SET DEFAULT**.
- Các đường ghi Java/ORM tự đặt **NORMAL** vẫn tiếp tục ghi NORMAL đến khi sửa chúng.

Nếu muốn đổi giá trị của **dữ liệu lịch sử**, đó là thao tác **backfill/update riêng** và phải dựa trên tiêu chí nghiệp vụ. Không thể giả định mọi hàng NORMAL trước đây đều là giá trị mặc định để đổi hết thành HIGH; có người dùng đã chủ động chọn NORMAL.

### 12.1. Thêm cột mới có mặc định

Khi thêm một cột nguồn tiếp nhận, muốn hàng cũ được đánh dấu **LEGACY**, còn hàng tạo mới dùng **WEB**:

~~~sql
-- Minh họa quy trình PostgreSQL; cần lập kế hoạch migration theo tải thực tế.
ALTER TABLE support_ticket
ADD COLUMN source_channel VARCHAR(16);

ALTER TABLE support_ticket
ALTER COLUMN source_channel SET DEFAULT 'WEB';

UPDATE support_ticket
SET source_channel = 'LEGACY'
WHERE source_channel IS NULL;

ALTER TABLE support_ticket
ALTER COLUMN source_channel SET NOT NULL;
~~~

Đây là **ví dụ khái niệm**. Với dữ liệu lớn và hệ thống đang ghi đồng thời, phải lên kế hoạch khóa, thời gian chạy, phân đợt backfill, xử lý client gửi NULL tường minh và điểm chuyển trạng thái áp dụng NOT NULL. Một chương trình ghi NULL trong khoảng giữa migration có thể làm sai nhãn LEGACY hoặc khiến bước SET NOT NULL thất bại.

Nếu dùng **ADD COLUMN ... DEFAULT ...** trong PostgreSQL, những hàng hiện có có thể được thể hiện với giá trị default của cột mới theo ngữ nghĩa lệnh ALTER; không nên tự đồng nhất điều đó với **ALTER COLUMN SET DEFAULT** trên cột đã tồn tại. Chi tiết tối ưu lưu trữ và rewrite bảng phụ thuộc phiên bản PostgreSQL cũng như tính chất của biểu thức default.

### 12.2. Triển khai nhiều phiên bản ứng dụng

Trong một đợt phát hành tuần tự, có thể đồng thời tồn tại:

- Phiên bản Java cũ luôn gửi NORMAL.
- Phiên bản Java mới bỏ cột priority hoặc gửi HIGH theo chính sách mới.
- Script import chỉ cung cấp subject.
- Database đã đổi DEFAULT sang HIGH.

Kết quả là mỗi nguồn ghi có thể tạo giá trị khác nhau. Cần kiểm kê **mọi writer**, sắp xếp thứ tự migration và triển khai tương thích, rồi đo dữ liệu sau phát hành. Thay đổi default trong database đơn lẻ không đảm bảo đổi hành vi toàn hệ thống.

## 13. Hiệu năng, tính quan sát và lưu trữ

Một default phổ biến như **status = OPEN** khiến nhiều hàng có cùng giá trị; điều này có thể ảnh hưởng phân bố dữ liệu và tính chọn lọc của chỉ mục. Tuy vậy, không thể kết luận “DEFAULT làm chỉ mục chậm” hay “bắt buộc phải index cột DEFAULT”. Giá trị được lưu như các giá trị khác; hiệu năng phụ thuộc truy vấn và phân bố thực tế.

Một số điểm cần cân nhắc:

- Chỉ tạo chỉ mục cho status/priority khi truy vấn, thống kê và kế hoạch thực thi chứng minh lợi ích.
- Default expression phức tạp hoặc trigger có thể thêm chi phí mỗi lần ghi; cần đo khi tải ghi lớn.
- Việc nhiều writer áp dụng mặc định khác nhau có thể được phát hiện qua thống kê phân bố trạng thái/độ ưu tiên và các log thay đổi.
- Nếu hệ thống cần biết **giá trị do người dùng chọn** hay **do mặc định sinh ra**, chỉ lưu cùng một giá trị NORMAL không đủ để phân biệt. Có thể cần trường nguồn, audit event hoặc metadata riêng như **priority_source = 'DEFAULT' / 'USER'**, theo nghiệp vụ.
- Đừng suy ra nguồn gốc giá trị từ việc nó trùng với DEFAULT hiện hành; default có thể đã thay đổi và người dùng có thể chọn đúng giá trị đó.

Đối với hệ thống cần truy vết quyết định nghiệp vụ, thiết kế audit trước khi ghi dữ liệu thường đáng tin cậy hơn việc cố suy luận nguồn gốc sau này.

## 14. Ma trận kiểm thử cho các đường ghi

Kiểm thử nên đi qua **database thật** hoặc môi trường tương thích để xác nhận hành vi DDL/driver/ORM, thay vì chỉ kiểm thử đối tượng Java được khởi tạo.

| Tình huống | Dữ liệu / thao tác | Kết quả kỳ vọng |
| --- | --- | --- |
| Tạo tối thiểu | INSERT chỉ có subject | status=OPEN, priority=NORMAL, attempt_count=0 |
| Ghi tường minh | INSERT priority='HIGH' | priority=HIGH |
| Ghi NULL | INSERT priority=NULL | Bị NOT NULL từ chối |
| Giá trị sai | INSERT status='BROKEN' | Bị CHECK từ chối |
| Đặt mặc định tường minh | INSERT priority=DEFAULT | priority=NORMAL theo lược đồ ban đầu |
| Sửa tiêu đề | UPDATE chỉ SET subject | status và priority giữ nguyên |
| Reset có chủ đích | UPDATE SET priority=DEFAULT | priority bằng default hiện hành |
| Đổi default bằng migration | ALTER COLUMN priority SET DEFAULT 'HIGH' | Hàng cũ giữ nguyên, INSERT bỏ cột nhận HIGH |
| Writer ngoài Java | Chạy trực tiếp SQL chỉ cung cấp subject | Nhận các default ở DB |
| ORM INSERT | Tạo entity rồi persist | Xác minh cột được gửi và giá trị DB trả về |
| Đồng bộ sau INSERT | Đọc RETURNING/refresh | Entity/DTO thấy ID và created_at thực sự lưu |
| Đồng hồ | Tạo nhiều hàng trong cùng giao dịch | Hiểu ngữ nghĩa CURRENT_TIMESTAMP của PostgreSQL |

Khi kiểm thử tích hợp, nên xác minh cả **kết quả persisted** lẫn **câu lệnh ghi có chủ đích**. Một bài test chỉ thấy NORMAL trong Java không chứng minh database đã áp dụng DEFAULT NORMAL.

## 15. Tình huống thực hành

### Tình huống A — Tìm nguyên nhân NULL vi phạm NOT NULL

Bảng **support_ticket** có **priority NOT NULL DEFAULT 'NORMAL'**, nhưng ứng dụng nhận lỗi “null value in column priority violates not-null constraint”.

**Gợi ý phân tích:**

1. Kiểm tra SQL thực sự được gửi: có cột priority trong danh sách INSERT không?
2. Nếu INSERT truyền NULL, DEFAULT sẽ không chạy.
3. Xác định API đang diễn giải trường vắng mặt và JSON null thế nào.
4. Chọn cách xử lý phù hợp: bỏ cột khi muốn DB default, áp dụng default trước khi ghi ở Java, hoặc từ chối null tường minh theo hợp đồng.
5. Kiểm thử lại bằng cả JDBC/ORM và lệnh SQL trực tiếp.

### Tình huống B — Hai ứng dụng lưu trạng thái mới khác nhau

Service A khởi tạo **status='OPEN'** trong constructor. Service B luôn bỏ cột status khỏi INSERT. Database có DEFAULT 'OPEN'. Sau migration đổi DB default thành 'IN_PROGRESS', hai service sẽ ghi gì?

**Đáp án:** A vẫn ghi **OPEN** nếu không được sửa, vì giá trị đi vào INSERT tường minh. B ghi **IN_PROGRESS** vì không cung cấp cột. Đây là dạng sai lệch cần phát hiện khi triển khai nhiều writer.

### Tình huống C — PATCH vô tình reset priority

API nhận:

~~~json
{"subject": "Bổ sung bước tái hiện lỗi"}
~~~

Sau PATCH, priority của ticket bất ngờ chuyển từ HIGH về NORMAL.

**Nguyên nhân có thể:** tầng service dựng lại đối tượng với constructor mặc định NORMAL hoặc thực hiện UPDATE chứa priority=NORMAL dù client không gửi trường này.

**Hướng sửa:** xử lý PATCH theo **trường có mặt**, chỉ cập nhật subject, giữ priority hiện tại; phân biệt yêu cầu thay đổi tường minh với việc trường bị bỏ qua. Không áp dụng lại default của thao tác tạo mới khi cập nhật từng phần.

### Tình huống D — Chọn nơi ghi created_at

Ứng dụng chạy trên nhiều máy, phải ghi nhận thời điểm một ticket **được database tiếp nhận**, không phải thời điểm người dùng bắt đầu nhập form. Nên đặt mặc định ở đâu?

**Đáp án gợi ý:** **DEFAULT CURRENT_TIMESTAMP** tại database là lựa chọn phù hợp cho ngữ nghĩa này, với hiểu biết về thời điểm giao dịch của PostgreSQL. Nếu muốn ghi **thời điểm sự cố thực sự xảy ra**, cần thêm trường nghiệp vụ do người dùng hoặc hệ thống nguồn cung cấp, thay vì dùng created_at.

### Tình huống E — Giá trị mặc định có thể nguy hiểm

API tạo tài khoản không cung cấp quyền truy cập. Lập trình viên đề xuất DEFAULT 'ADMIN' để tránh lỗi NOT NULL.

**Đáp án:** Đề xuất này nguy hiểm vì thiếu thông tin lại được diễn giải thành đặc quyền cao. Chính sách nên được thiết kế theo nguyên tắc quyền tối thiểu; một giá trị mặc định an toàn hoặc yêu cầu người quản trị chỉ định vai trò theo quy trình phù hợp là lựa chọn cần xem xét.

## 16. Tổng kết

**Mặc định ở ứng dụng** được áp dụng khi Java, API hoặc logic nghiệp vụ quyết định giá trị và gửi đi. **Mặc định ở kho lưu trữ** được áp dụng theo ngữ nghĩa câu lệnh ghi và DDL của database, thường khi INSERT không nêu cột hoặc sử dụng từ khóa SQL DEFAULT. **Truyền NULL tường minh không đồng nghĩa với bỏ qua cột**; NOT NULL có thể làm lệnh ghi thất bại dù cột có DEFAULT.

Thiết kế tốt phải xác định bên sở hữu chính sách khởi tạo, cách xử lý trường vắng mặt/NULL trong API, SQL do JDBC/ORM tạo ra, ngữ nghĩa thời gian và chiến lược migration. **DEFAULT** giúp khởi tạo dữ liệu nhất quán nhưng không thay cho **CHECK, NOT NULL, UNIQUE, FOREIGN KEY**, giao dịch và kiểm tra quyền. Khi nhiều ứng dụng hoặc script cùng ghi vào một kho lưu trữ, cách tốt nhất để bảo đảm hệ thống vận hành đúng là xác minh các đường ghi thực tế và đọc lại chính những giá trị đã lưu.
