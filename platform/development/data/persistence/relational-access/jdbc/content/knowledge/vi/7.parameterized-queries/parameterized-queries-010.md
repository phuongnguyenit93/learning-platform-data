# Xử lý ký tự đại diện trong điều kiện LIKE bằng JDBC

## 1. Vấn đề: tham số hóa vẫn cần hiểu quy tắc của LIKE

Trong **JDBC (Java Database Connectivity)**, ứng dụng Java truy vấn cơ sở dữ liệu quan hệ bằng các API như `Connection`, `PreparedStatement` và `ResultSet`. Khi tìm kiếm chuỗi, một điều kiện thường gặp là:

~~~sql
SELECT id, display_name
FROM app_user
WHERE display_name LIKE ?;
~~~

Dấu hỏi `?` là **placeholder của JDBC**: ứng dụng truyền giá trị bằng `PreparedStatement.setString(...)`. Cách này tách **dữ liệu** ra khỏi **cấu trúc câu SQL**, giúp tránh SQL injection do việc ghép trực tiếp chuỗi đầu vào vào câu lệnh.

Tuy nhiên, giá trị của tham số vẫn có thể mang **ý nghĩa đặc biệt bên trong cú pháp mẫu của `LIKE`**. Ví dụ:

~~~java
String input = "50%";
statement.setString(1, "%" + input + "%");
~~~

Tham số thực tế trở thành `%50%%`. Ký tự `%` do người dùng nhập đã được database coi là **ký tự đại diện**, nên truy vấn có thể khớp các chuỗi như `"500 sản phẩm"` thay vì chỉ các chuỗi thật sự chứa dấu phần trăm `"50%"`.

Vì vậy, một bài toán tìm kiếm bằng `LIKE` cần giải quyết **hai trách nhiệm riêng**:

1. **Bind tham số:** truyền mẫu qua `PreparedStatement` thay vì nối dữ liệu vào SQL.
2. **Escape ký tự đại diện:** quyết định ký tự `%` và `_` của **đầu vào người dùng** là dữ liệu chữ hay là toán tử của mẫu tìm kiếm.

**Mục tiêu bài học:** Tạo mẫu `LIKE` đúng ý định tìm kiếm, xử lý các ký tự `%`, `_` và chính ký tự escape, chọn cách kiểm thử trên driver/DBMS cụ thể và không nhầm escaping của Java, SQL literal với escaping của `LIKE`.

## 2. Cách SQL LIKE diễn giải ký tự đại diện

Trong SQL thông dụng, `LIKE` kiểm tra một giá trị ký tự có phù hợp với **mẫu** hay không.

| Ký tự trong mẫu | Ý nghĩa thông dụng | Ví dụ mẫu | Có thể khớp |
| --- | --- | --- | --- |
| `%` | Bất kỳ chuỗi ký tự nào, kể cả chuỗi rỗng. | `'Lan%'` | `Lan`, `Lan Anh`. |
| `_` | Một ký tự theo quy tắc so khớp của DBMS. | `'A_'` | `An`, `A1`. |
| Ký tự thường | Khớp chính ký tự đó, theo collation/so sánh của DBMS. | `'Lan'` | `Lan`, tùy collation có thể có biến thể chữ hoa/thường. |
| Ký tự escape được khai báo | Đổi ký tự đặc biệt ngay sau thành ký tự cần khớp theo nghĩa đen. | `'50!%' ESCAPE '!'` | Chuỗi `50%`. |

Ví dụ với cột `title`:

~~~sql
-- Bắt đầu bằng Java (có thể là chỉ một từ Java)
WHERE title LIKE 'Java%'

-- Chứa Java ở bất kỳ vị trí nào
WHERE title LIKE '%Java%'

-- Có đúng một ký tự nằm giữa A và C
WHERE title LIKE 'A_C'

-- Chứa ký tự phần trăm thực sự
WHERE title LIKE '%!%%' ESCAPE '!'
~~~

**Ghi chú về tính di động:** Ý nghĩa `%` và `_` nói trên là cơ sở phổ biến, nhưng xử lý Unicode, dấu cách cuối chuỗi, hoa/thường và tập ký tự mở rộng phụ thuộc DBMS, kiểu dữ liệu và collation. Ví dụ, không nên suy từ một `_` rằng mọi hệ quản trị đều đếm các ký tự Unicode phức tạp giống nhau.

### 2.1. Một số tình huống dễ nhầm

Giả sử bảng có những giá trị sau:

| ID | `title` |
| --- | --- |
| 1 | `100% cotton` |
| 2 | `1000 cotton` |
| 3 | `file_name` |
| 4 | `fileXname` |
| 5 | `Hello! Java` |
| 6 | `O'Brien` |
| 7 | `50%_off!` |

Nếu muốn tìm **chuỗi chữ `100%`**, mẫu `%100%%` có thể khớp **cả ID 1 và ID 2** do `%` ở giữa là wildcard. Nếu muốn tìm **chuỗi chữ `file_name`**, mẫu `%file_name%` cũng có thể khớp `fileXname` do dấu gạch dưới là wildcard.

Đây là lỗi về **ngữ nghĩa tìm kiếm**, không nhất thiết là SQL injection. Ngay cả khi `PreparedStatement` đã bind an toàn, các ký tự wildcard vẫn có hiệu lực nếu bạn không escape chúng.

## 3. Xác định ý định tìm kiếm trước khi tạo mẫu

Trước khi viết hàm tạo pattern, hãy quyết định API của bạn có ý định gì.

| Chế độ | Ý nghĩa | Ví dụ với đầu vào `cat` |
| --- | --- | --- |
| **Contains** | Cột chứa đúng chuỗi người dùng gõ ở một vị trí bất kỳ. | `%cat%` |
| **Starts with** | Cột bắt đầu bằng đúng chuỗi người dùng gõ. | `cat%` |
| **Ends with** | Cột kết thúc bằng đúng chuỗi người dùng gõ. | `%cat` |
| **Literal LIKE** | Cột khớp chuỗi người dùng gõ mà không có wildcard thêm. | `cat` |
| **Advanced pattern search** | Người dùng được phép chủ động dùng `%` / `_` làm wildcard. | `c_t%` theo cú pháp cho phép. |

Trong hầu hết ô tìm kiếm thông thường, người dùng mong chờ **tìm chuỗi theo nghĩa đen**. Khi họ gõ `"50%"`, dấu `%` thường là nội dung của sản phẩm, không phải câu lệnh “khớp vô số ký tự”.

Ngược lại, công cụ tìm kiếm nâng cao có thể cho phép cú pháp wildcard có chủ đích. Đây là một **hợp đồng API khác**. Không dùng một hàm escape luôn luôn rồi quảng cáo rằng ô tìm kiếm vẫn hỗ trợ wildcard: hành vi đã thay đổi.

**Nguyên tắc:** Chọn chính sách trước, sau đó tạo mẫu. Đừng tự đoán rằng ký tự `*` do người dùng gõ phải biến thành `%`; việc chuyển đổi cú pháp wildcard của người dùng là một bước xử lý riêng cần tài liệu và kiểm thử.

## 4. Dùng ESCAPE để tìm phần trăm và gạch dưới theo nghĩa đen

SQL hỗ trợ khai báo một ký tự **escape** cho `LIKE`. Ví dụ dùng dấu chấm than `!`:

~~~sql
SELECT id, title
FROM search_demo
WHERE title LIKE ? ESCAPE '!';
~~~

Trong mẫu này:

- `!%` nghĩa là **ký tự phần trăm** thật.
- `!_` nghĩa là **dấu gạch dưới** thật.
- `!!` nghĩa là **dấu chấm than** thật.
- `%` và `_` không đứng sau dấu escape vẫn có vai trò wildcard như bình thường.

Ví dụ:

| Ý định | Mẫu được bind | Giải thích |
| --- | --- | --- |
| Chứa ký tự `%` | `%!%%` | `%` đầu/cuối là wildcard; `!%` ở giữa là dấu phần trăm thật. |
| Chứa `file_name` | `%file!_name%` | `!_` là ký tự gạch dưới thật. |
| Chứa `Hello!` | `%Hello!!%` | `!!` đại diện cho dấu `!` theo nghĩa đen. |
| Chứa `50%_off!` | `%50!%!_off!!%` | Escape lần lượt phần trăm, gạch dưới và chấm than. |
| Bắt đầu bằng `100%` | `100!%%` | `!%` là nội dung cần tìm; `%` cuối cho phép hậu tố bất kỳ. |

### 4.1. Vì sao chọn dấu `!` thay vì dấu gạch chéo ngược?

Dấu `\` dễ gây nhầm vì có thể xuất hiện ở **ba tầng khác nhau**:

1. Escaping của chuỗi **Java source**, ví dụ `"\\"` để viết một ký tự backslash.
2. Escaping của **SQL string literal**, có thể khác theo DBMS và cấu hình.
3. Escaping của **mẫu `LIKE`**, do `ESCAPE` hoặc mặc định riêng của DBMS điều khiển.

Dùng `ESCAPE '!'` và bind pattern bằng `setString(...)` làm ví dụ dễ hiểu hơn: chỉ cần quản lý quy tắc `!%`, `!_`, `!!` mà không phải tính số dấu `\` tại nhiều tầng.

**Dù dùng ký tự nào, cần nhất quán.** Nếu SQL khai báo `ESCAPE '!'` thì hàm escape đầu vào **phải** dùng `!`; không được dùng hàm thêm `\` nhưng SQL lại yêu cầu `!`.

### 4.2. Kiểm tra khả năng hỗ trợ của driver/DBMS

Có thể tra cứu:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    if (!metadata.supportsLikeEscapeClause()) {
        throw new SQLFeatureNotSupportedException(
                "DBMS/driver không công bố hỗ trợ LIKE ESCAPE");
    }
}
~~~

Trong đoạn trích này cần import `java.sql.Connection`, `java.sql.DatabaseMetaData`, `java.sql.SQLFeatureNotSupportedException` và sử dụng `javax.sql.DataSource` do ứng dụng cung cấp.

`DatabaseMetaData.supportsLikeEscapeClause()` là **tín hiệu về khả năng hỗ trợ cú pháp**, chưa chứng minh mọi ký tự escape, mọi collation hay mọi truy vấn đều có cùng hành vi. Với môi trường quan trọng, nên thực thi một truy vấn kiểm thử thực tế có ký tự `%`, `_` và `!` trước khi đưa vào production.

JDBC cũng định nghĩa **escape processing syntax**, có dạng:

~~~sql
SELECT id, title
FROM search_demo
WHERE title LIKE ? {escape '!'};
~~~

Driver có thể dịch escape syntax JDBC sang cú pháp mà DBMS hỗ trợ khi tính năng JDBC escape processing được bật. Không trộn lẫn hai cách viết trong cùng SQL. Ví dụ chính của bài dùng trực tiếp `ESCAPE '!'`, vì cách này phổ biến ở nhiều DBMS; nếu driver đích yêu cầu cú pháp khác, dùng đúng tài liệu và kiểm thử driver đó.

## 5. Viết hàm escape đúng: xử lý cả ký tự escape

Một hàm thường sai là:

~~~java
// THIẾU: chưa xử lý chính dấu ! trong chuỗi đầu vào.
static String incompleteEscape(String text) {
    return text.replace("%", "!%")
               .replace("_", "!_");
}
~~~

Nếu người dùng gõ `Hello!`, mẫu trở thành `Hello!`. Ký tự `!` cuối có thể bị driver xem như escape chưa có ký tự theo sau; tùy DBMS, kết quả có thể không đúng hoặc câu truy vấn báo lỗi.

### 5.1. Cách ngắn gọn: thay theo thứ tự

~~~java
static String escapeLikeLiteral(String input) {
    return input.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
}
~~~

Việc thay dấu `!` **trước** có ý nghĩa: nếu thêm dấu `!` để escape `%` rồi lại thay tất cả `!` ở bước sau, bạn sẽ vô tình nhân đôi cả các dấu escape mới sinh ra.

Đầu ra của hàm chỉ là **phần nội dung theo nghĩa đen đã escape**. Bước thêm wildcard của chế độ contains/prefix/suffix nên thực hiện **sau đó**.

### 5.2. Cách tổng quát: duyệt từng ký tự

Cách sau tránh tạo nhiều chuỗi trung gian và làm rõ quy tắc:

~~~java
import java.util.Objects;

public final class LikePatterns {
    private LikePatterns() {}

    private static final char ESCAPE = '!';

    public enum MatchMode {
        CONTAINS,
        STARTS_WITH,
        ENDS_WITH,
        LITERAL
    }

    public static String escapeLiteral(String input) {
        Objects.requireNonNull(input, "input");

        StringBuilder out = new StringBuilder(input.length());
        for (int i = 0; i < input.length(); i++) {
            char ch = input.charAt(i);
            if (ch == ESCAPE || ch == '%' || ch == '_') {
                out.append(ESCAPE);
            }
            out.append(ch);
        }
        return out.toString();
    }

    public static String pattern(String input, MatchMode mode) {
        String literal = escapeLiteral(input);

        return switch (Objects.requireNonNull(mode, "mode")) {
            case CONTAINS    -> "%" + literal + "%";
            case STARTS_WITH -> literal + "%";
            case ENDS_WITH   -> "%" + literal;
            case LITERAL     -> literal;
        };
    }
}
~~~

Hàm `pattern(...)` không nhận hay sinh SQL: nó chỉ tạo **một giá trị** để bind vào placeholder. Quy tắc `ESCAPE '!'` vẫn được khai báo cố định ở câu SQL.

Việc duyệt `char` trong Java giữ nguyên các mã UTF-16 không phải ký tự đặc biệt; nó không thực hiện chuẩn hóa Unicode hay quyết định collation. Cách DBMS so sánh chữ có dấu, chữ hoa/thường và ký tự Unicode phức tạp là một vấn đề khác.

### 5.3. Ví dụ kết quả

| Đầu vào | `escapeLiteral(input)` | `pattern(input, CONTAINS)` |
| --- | --- | --- |
| `Java` | `Java` | `%Java%` |
| `100%` | `100!%` | `%100!%%` |
| `file_name` | `file!_name` | `%file!_name%` |
| `Hello!` | `Hello!!` | `%Hello!!%` |
| `50%_off!` | `50!%!_off!!` | `%50!%!_off!!%` |
| `O'Brien` | `O'Brien` | `%O'Brien%` |
| Chuỗi rỗng | Chuỗi rỗng | `%%` |

Dấu nháy đơn trong `O'Brien` **không cần được “escape SQL” thủ công trong Java** khi dùng `PreparedStatement.setString(...)`. Giá trị này không bị ghép vào cấu trúc câu SQL; driver thực hiện binding. Ngược lại, dấu `%` và `_` vẫn cần được xử lý **nếu muốn tìm literal** vì chúng nằm trong giá trị mẫu `LIKE`.

Chuỗi rỗng cần chính sách riêng: trong chế độ contains, `%%` thường khớp mọi chuỗi **không NULL**. Nếu không muốn một ô tìm kiếm rỗng trả rất nhiều hàng, hãy từ chối hoặc xử lý rõ ở tầng API.

## 6. Ví dụ repository JDBC hoàn chỉnh

Ví dụ dùng Java 17+, một bảng `app_user(id, display_name)` và `DataSource` đã cấu hình đúng driver. API dưới đây nhận ý định **tìm chuỗi con theo nghĩa đen**, không coi ký tự `%` hay `_` của người dùng là wildcard.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class UserSearchRepository {
    private final DataSource dataSource;

    public record UserRow(long id, String displayName) {}

    public UserSearchRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public List<UserRow> findContaining(String searchText)
            throws SQLException {
        Objects.requireNonNull(searchText, "searchText");

        // Quy ước API: không chạy tìm kiếm khi chuỗi rỗng.
        if (searchText.isEmpty()) {
            return List.of();
        }

        String sql = """
                SELECT id, display_name
                FROM app_user
                WHERE display_name LIKE ? ESCAPE '!'
                ORDER BY id
                """;

        String pattern = LikePatterns.pattern(
                searchText, LikePatterns.MatchMode.CONTAINS);

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            // Bind MỘT giá trị pattern, không ghép searchText vào SQL.
            ps.setString(1, pattern);

            try (ResultSet rs = ps.executeQuery()) {
                List<UserRow> users = new ArrayList<>();

                while (rs.next()) {
                    users.add(new UserRow(
                            rs.getLong("id"),
                            rs.getString("display_name")));
                }

                return List.copyOf(users);
            }
        }
    }
}
~~~

Hàm `LikePatterns.pattern(...)` được định nghĩa ở mục trước; đặt hai lớp vào source của ứng dụng hoặc điều chỉnh package/import tương ứng trước khi biên dịch.

Điểm cần quan sát:

1. Cấu trúc SQL chứa **`LIKE ? ESCAPE '!'` cố định**.
2. Hàm `escapeLiteral` biến các wildcard người dùng gõ thành chuỗi literal.
3. Chế độ `CONTAINS` chỉ thêm hai wildcard **do ứng dụng chủ động cấp**.
4. `setString(1, pattern)` bind toàn bộ pattern thành **một tham số**.
5. `ResultSet` được đọc thành `List<UserRow>` khi `Connection` còn mở; các tài nguyên được đóng bằng `try-with-resources`.

### 6.1. Cách gọi từ tầng service

~~~java
UserSearchRepository repository =
        new UserSearchRepository(dataSource);

List<UserSearchRepository.UserRow> users =
        repository.findContaining("50%_off!");

for (UserSearchRepository.UserRow user : users) {
    System.out.println(user.id() + " - " + user.displayName());
}
~~~

Giá trị pattern được bind là `%50!%!_off!!%`. SQL có `ESCAPE '!'`, nên dấu `%`, dấu `_` và dấu `!` **bên trong chuỗi người dùng nhập** được tìm như dữ liệu, trong khi hai dấu phần trăm do ứng dụng thêm vẫn là wildcard.

**Giới hạn của ví dụ:** Phương thức đọc hết các hàng khớp vào bộ nhớ. Với dữ liệu lớn, hãy thêm phân trang, giới hạn kết quả và sắp xếp xác định bằng cú pháp phù hợp với DBMS; không xem việc escape wildcard là giải pháp hiệu năng.

## 7. Phân biệt ba lớp escaping khi viết mã Java

Đây là nguồn gây nhầm lẫn rất phổ biến:

~~~mermaid
flowchart TD
    A[Đầu vào người dùng: 50%_off!] --> B[Escape LIKE literal]
    B --> C[50!%!_off!!]
    C --> D[Thêm wildcard do API quyết định]
    D --> E[%50!%!_off!!%]
    E --> F[PreparedStatement.setString]
    F --> G[SQL: LIKE ? ESCAPE '!']
    G --> H[DBMS so khớp mẫu và dữ liệu]
~~~

**Lớp 1: Java source.** Nếu viết chuỗi có backslash trong mã nguồn, Java cần cú pháp escape của riêng nó. Điều này không tự tạo escape `LIKE`.

**Lớp 2: SQL text/literal.** SQL chứa `ESCAPE '!'` như một phần **cú pháp cố định**, chứ không phải nối giá trị người dùng vào câu lệnh.

**Lớp 3: SQL LIKE pattern.** Giá trị truyền qua `setString(...)` được DBMS giải thích là **mẫu**, trong đó `%`, `_` và `!` có ý nghĩa theo `ESCAPE`.

### 7.1. Những ví dụ sai và nguyên nhân

~~~java
// SAI: dữ liệu không được bind; SQL injection và sai cú pháp.
String sql = "SELECT * FROM app_user WHERE display_name LIKE '%"
        + userInput + "%'";

// SAI về ngữ nghĩa literal: prepared statement chống SQL injection,
// nhưng % và _ người dùng nhập vẫn là wildcard.
ps.setString(1, "%" + userInput + "%");

// SAI: Pattern.quote dùng cho regex của Java, không dành cho SQL LIKE.
ps.setString(1, "%" + Pattern.quote(userInput) + "%");

// ĐÚNG với ý định literal contains (SQL dùng ESCAPE '!').
ps.setString(1, LikePatterns.pattern(
        userInput, LikePatterns.MatchMode.CONTAINS));
~~~

Trong đoạn so sánh, `Pattern.quote(...)` thuộc `java.util.regex.Pattern`. Java regex có metacharacter và quy tắc escaping **khác** `LIKE`; chẳng hạn, `.` và `*` không phải ký tự đại diện theo cú pháp `LIKE` chuẩn.

### 7.2. Không “escape dấu nháy đơn” hai lần

Có người cố gắng xử lý `O'Brien` bằng:

~~~java
String escaped = input.replace("'", "''");
ps.setString(1, "%" + escaped + "%");
~~~

Khi bind bằng `PreparedStatement`, việc nhân đôi dấu nháy đơn theo cách trên thường **làm thay đổi dữ liệu cần tìm** thành chuỗi có hai dấu nháy đơn. Quy tắc nhân đôi nháy đơn dành cho **SQL string literal viết trực tiếp trong text SQL**; còn với tham số JDBC, hãy để driver bind nguyên chuỗi đầu vào.

Escape `%`, `_` và ký tự escape cho `LIKE` là một bước riêng, không phải cơ chế thay thế việc bind an toàn.

## 8. Trường hợp người dùng thực sự muốn nhập wildcard

Trong công cụ tìm kiếm nâng cao, bạn có thể thiết kế một chế độ **pattern search**, nơi `%` và `_` do người dùng nhập là cú pháp có chủ đích. Ví dụ:

~~~text
Đầu vào:  A_%  -> Tìm chuỗi bắt đầu bằng A, có ít nhất một ký tự tiếp theo.
Đầu vào:  10%  -> Tìm chuỗi bắt đầu bằng 10.
~~~

Ở chế độ này, không thể luôn gọi `escapeLiteral(input)` vì nó sẽ vô hiệu hóa wildcard người dùng muốn dùng. Có hai phương án thiết kế:

- **Cho phép SQL LIKE pattern có kiểm soát:** bind nguyên pattern, chỉ cho người dùng hiểu đúng cú pháp `%` / `_` / escape, giới hạn độ dài mẫu, số kết quả và tài nguyên truy vấn. Bind bằng `PreparedStatement` vẫn bắt buộc.
- **Định nghĩa cú pháp tìm kiếm riêng:** ví dụ `*` là wildcard nhiều ký tự, `?` là wildcard một ký tự, `\*` là dấu sao theo nghĩa đen. Cần viết parser phân biệt wildcard có chủ đích và ký tự literal trước khi chuyển sang `LIKE`. Không chỉ gọi `replace("*", "%")` nếu có thể nhập các ký tự escape/wildcard khác.

Nên dùng **API rõ chế độ**, ví dụ `searchLiteralContains(term)` và `searchByPattern(pattern)`, để người dùng và người bảo trì không phải đoán ý nghĩa của `%`.

**Rủi ro hiệu năng và truy cập dữ liệu:** Pattern như `%` hoặc `%%` có thể khớp rất nhiều hàng, khiến database quét dữ liệu lớn. Parameter binding ngăn cấu trúc SQL bị chèn tùy ý nhưng **không ngăn một pattern tốn kém hoặc quá rộng**. Cần giới hạn truy vấn và phân quyền riêng.

## 9. Sự khác nhau giữa các hệ quản trị

JDBC là lớp API chung, nhưng biểu thức `LIKE` chạy ở DBMS. Khi chuyển ứng dụng giữa PostgreSQL, MySQL, MariaDB, SQL Server, Oracle hoặc SQLite, cần kiểm tra cú pháp `ESCAPE` và ngữ nghĩa so khớp của hệ cụ thể.

| Khía cạnh | Điểm cần xác minh trên DBMS/driver đích |
| --- | --- |
| `ESCAPE '!'` | Hệ quản trị có hỗ trợ escape clause không? Driver có xử lý JDBC escape syntax riêng không? |
| Tính phân biệt hoa/thường | Collation của cột, database, kết nối và các toán tử riêng có thể thay đổi kết quả `LIKE`. |
| Dấu/Unicode | Các collation có thể so sánh dấu, ký tự ghép, độ rộng ký tự và case theo những cách khác nhau. |
| Ký tự đặc biệt bổ sung | **SQL Server** còn có cú pháp pattern trong dấu ngoặc vuông `[ ... ]`; việc tìm dấu `[` theo nghĩa đen cần xử lý theo quy tắc SQL Server. |
| Backslash | Một số DBMS có quy tắc mặc định liên quan dấu `\`; khi chọn escape `!`, vẫn cần kiểm chứng trên server và cấu hình thật. |
| Trailing spaces | Một số phép so khớp phụ thuộc kiểu `CHAR`/`VARCHAR` và cách DBMS xử lý dấu cách cuối chuỗi. |
| Index | Prefix/contains pattern có kế hoạch thực thi khác nhau; collation và biểu thức trên cột ảnh hưởng khả năng dùng index. |

### 9.1. PostgreSQL

PostgreSQL có `LIKE` và toán tử `ILIKE` để so khớp không phân biệt hoa/thường theo quy tắc của PostgreSQL. Nếu chọn `ILIKE`, giá trị đầu vào vẫn cần escape wildcard khi ý định tìm kiếm là literal.

~~~sql
-- Cú pháp đặc thù PostgreSQL:
SELECT id, title
FROM search_demo
WHERE title ILIKE ? ESCAPE '!';
~~~

Không suy rằng mọi DBMS có `ILIKE` hoặc kết quả Unicode/collation giống PostgreSQL. Nếu cần tìm kiếm không dấu hoặc full-text, đó là yêu cầu riêng vượt quá xử lý wildcard của `LIKE`.

### 9.2. MySQL và MariaDB

Tính phân biệt hoa/thường thường phụ thuộc **collation**. Một cột sử dụng collation không phân biệt hoa/thường có thể khiến `LIKE 'java%'` khớp cả `Java` và `JAVA`. Đừng giả định rằng đổi từ máy phát triển sang production sẽ cho cùng kết quả nếu collation khác.

Dùng ký tự escape được chỉ định rõ như `ESCAPE '!'` giúp tránh lệ thuộc một phần vào cách diễn giải dấu backslash mặc định, nhưng vẫn phải thử trên phiên bản server và driver thực tế.

### 9.3. Microsoft SQL Server

Trong SQL Server, `LIKE` còn có cú pháp nhóm ký tự như `[abc]` hoặc loại trừ ký tự trong dấu ngoặc vuông. Vì thế, một hàm chỉ escape `%`, `_`, `!` là **chưa đủ để bảo đảm mọi đầu vào đều literal** khi dùng SQL Server và cho phép ký tự `[`.

Với SQL Server, cần bổ sung quy tắc escaping dấu ngoặc mở theo cú pháp `ESCAPE` được hỗ trợ hoặc cơ chế khác đã được tài liệu hóa, rồi kiểm thử các chuỗi như `"[A]"`, `"50[kg]"` và `"[%]"`. Tránh tự sửa pattern theo những giả định đã kiểm chứng trên DBMS khác.

### 9.4. Oracle, SQLite và các DBMS khác

Các hệ quản trị này có cú pháp `LIKE` nhưng những điểm như collation, biến thể toán tử, hàm xử lý chữ hoa/thường, kiểu dữ liệu và khả năng tối ưu index không hoàn toàn tương đương. Để viết ứng dụng có thể chuyển DBMS, nên:

1. Tập trung quy tắc escape và tạo pattern ở một chỗ.
2. Lưu phiên bản driver/DBMS được hỗ trợ trong cấu hình dự án.
3. Chạy **integration test của chính dữ liệu mẫu và câu SQL** trên từng DBMS mục tiêu.

## 10. Ký tự NULL, chuỗi rỗng và dấu cách

Điều kiện:

~~~sql
WHERE display_name LIKE ?
~~~

không làm một hàng có `display_name IS NULL` khớp với mẫu `%`. Theo logic ba giá trị của SQL, biểu thức `NULL LIKE '...'` cho kết quả **UNKNOWN**, không phải `TRUE`.

Điều đó khác với:

- Cột chứa **chuỗi rỗng**, có thể khớp với `%` tùy DBMS.
- Chuỗi chỉ có **dấu cách**, thường có thể khớp `%` nhưng kết quả so sánh chính xác còn phụ thuộc kiểu dữ liệu/collation.
- Người dùng không truyền tham số và yêu cầu **không áp dụng bộ lọc**.

### 10.1. Thiết kế chính sách API tường minh

Bạn có thể chọn một trong ba cách đối với đầu vào rỗng:

1. **Trả kết quả rỗng** mà không truy vấn, như ví dụ `findContaining("")`.
2. **Bỏ điều kiện LIKE** khi màn hình có chức năng “xem tất cả”, nhưng phải phân trang và kiểm soát quyền.
3. **Báo lỗi validation** nếu từ khóa rỗng không hợp lệ.

Đừng để `"%%"` tự quyết định ngầm rằng toàn bộ dữ liệu đều được công bố. Nếu muốn lọc hàng có `NULL`, cần điều kiện SQL riêng như `IS NULL` hoặc logic bộ lọc được thiết kế rõ.

**Không tự động `trim()`/`strip()` nếu dấu cách là một phần của nội dung cần tìm.** Ví dụ người dùng muốn tìm tên sản phẩm có hai dấu cách liên tiếp thì việc chuẩn hóa tùy tiện sẽ đổi nghĩa.

### 10.2. Unicode và chuẩn hóa văn bản

Nếu nghiệp vụ cho rằng hai chuỗi có dấu được biểu diễn bằng những chuỗi Unicode khác nhau phải tương đương, `escapeLiteral` không giải quyết yêu cầu đó. Cần thiết kế quy tắc normalize/collation/index phù hợp và kiểm thử trên DBMS thật. Đừng coi `LIKE` là công cụ tìm kiếm ngôn ngữ tự nhiên đầy đủ.

## 11. Hiệu năng: pattern đúng vẫn có thể chậm

Phép escape đúng giải quyết **tính đúng đắn của từ khóa**; nó không tự bảo đảm truy vấn nhanh.

| Dạng pattern | Khả năng tối ưu thường gặp |
| --- | --- |
| `term%` | Có cơ hội tận dụng index theo tiền tố trong một số DBMS/collation/cấu hình. |
| `%term` | Thường khó dùng index B-tree thông thường để tìm trực tiếp bằng tiền tố. |
| `%term%` | Thường phải quét nhiều dữ liệu; cân nhắc chỉ mục chuyên dụng nếu đây là use case chính. |
| `%` hoặc `%%` | Có thể khớp rất nhiều hàng không NULL; nguy cơ trả dữ liệu rộng. |
| `LOWER(column) LIKE ...` | Dùng hàm trên cột có thể ảnh hưởng index thường; kiểm tra expression/function index nếu DBMS hỗ trợ. |

Khi tìm contains là tính năng thường xuyên trên bảng lớn, hãy xem xét khả năng **trigram/text index, full-text search hoặc search engine** phù hợp với DBMS và yêu cầu của ứng dụng. Những giải pháp này có cú pháp và ngữ nghĩa riêng, không nên áp dụng như phép thay thế tự động cho `LIKE`.

Biện pháp thực tế:

- **Giới hạn kết quả ở server**, kèm phân trang và sắp xếp xác định. Cú pháp `LIMIT`, `FETCH FIRST` và `OFFSET/FETCH` có thể khác theo DBMS.
- Giới hạn độ dài từ khóa theo nghiệp vụ, dùng timeout và phân quyền phù hợp.
- Xem execution plan và chỉ số thực tế trên dữ liệu đại diện; đo độ trễ p95/p99 nếu truy vấn là phần chính của API.
- Nếu dùng chế độ wildcard nâng cao, cân nhắc rate limit/quota để tránh pattern quá rộng.
- Kiểm tra tác động của collation và hàm chuyển chữ trước khi kết luận vì sao index không được dùng.

**Ví dụ tối ưu không tương đương:** Thay `LIKE '%java%'` bằng `LIKE 'java%'` có thể làm truy vấn nhanh hơn, nhưng nó **đổi yêu cầu từ “chứa” thành “bắt đầu bằng”**. Chỉ được đổi khi sản phẩm chấp nhận thay đổi ngữ nghĩa.

## 12. Kiểm thử: xác minh mẫu được tạo trước rồi mới thử database

### 12.1. Kiểm tra hàm escape thuần Java

Hàm `escapeLiteral` dễ kiểm thử không cần DB. Một số ca cần có:

| Input | Kết quả `escapeLiteral` kỳ vọng | Vì sao |
| --- | --- | --- |
| `abc` | `abc` | Không có ký tự đặc biệt. |
| `%` | `!%` | Escape percent. |
| `_` | `!_` | Escape underscore. |
| `!` | `!!` | Escape chính dấu escape. |
| `!%_` | `!!!%!_` | Ba ký tự đặc biệt liên tiếp. |
| `100% cotton` | `100!% cotton` | Phần trăm là chữ. |
| `file_name` | `file!_name` | Gạch dưới là chữ. |
| `O'Brien` | `O'Brien` | Nháy đơn không cần chỉnh khi JDBC bind. |
| `Java 😀` | `Java 😀` | Không làm thay đổi Unicode không phải wildcard. |

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class LikePatternsTest {
    @Test
    void escapesWildcardAndEscapeCharacter() {
        assertEquals("!%", LikePatterns.escapeLiteral("%"));
        assertEquals("!_", LikePatterns.escapeLiteral("_"));
        assertEquals("!!", LikePatterns.escapeLiteral("!"));
        assertEquals("!!!%!_", LikePatterns.escapeLiteral("!%_"));
        assertEquals("100!% cotton",
                LikePatterns.escapeLiteral("100% cotton"));
        assertEquals("O'Brien",
                LikePatterns.escapeLiteral("O'Brien"));
    }

    @Test
    void addsApplicationWildcardsAfterEscaping() {
        assertEquals("%50!%!_off!!%", LikePatterns.pattern(
                "50%_off!",
                LikePatterns.MatchMode.CONTAINS));

        assertEquals("file!_name%", LikePatterns.pattern(
                "file_name",
                LikePatterns.MatchMode.STARTS_WITH));

        assertEquals("%100!%", LikePatterns.pattern(
                "100%",
                LikePatterns.MatchMode.ENDS_WITH));
    }
}
~~~

Test thuần Java xác minh **phép chuyển pattern**; nó chưa kiểm chứng SQL driver diễn giải `ESCAPE '!'` như mong đợi.

### 12.2. Integration test với bảng dữ liệu mẫu

Có thể tạo một bảng kiểm thử riêng; cú pháp DDL/insert cần điều chỉnh nếu DBMS sử dụng quy tắc tạo bảng đặc thù:

~~~sql
CREATE TABLE search_demo (
    id INTEGER PRIMARY KEY,
    title VARCHAR(100)
);

INSERT INTO search_demo(id, title) VALUES (1, '100% cotton');
INSERT INTO search_demo(id, title) VALUES (2, '1000 cotton');
INSERT INTO search_demo(id, title) VALUES (3, 'file_name');
INSERT INTO search_demo(id, title) VALUES (4, 'fileXname');
INSERT INTO search_demo(id, title) VALUES (5, 'Hello! Java');
INSERT INTO search_demo(id, title) VALUES (6, 'O''Brien');
INSERT INTO search_demo(id, title) VALUES (7, '50%_off!');
~~~

Để kiểm tra câu SQL, dùng `PreparedStatement`:

~~~java
String sql = """
        SELECT id
        FROM search_demo
        WHERE title LIKE ? ESCAPE '!'
        ORDER BY id
        """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setString(1, LikePatterns.pattern(
            "file_name", LikePatterns.MatchMode.CONTAINS));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("id"));
        }
    }
}
~~~

Với dữ liệu mẫu, kỳ vọng tìm literal contains (giả sử collation không làm các giá trị khác trùng nghĩa):

| Đầu vào | Pattern bind | ID kỳ vọng |
| --- | --- | --- |
| `100%` | `%100!%%` | 1 |
| `file_name` | `%file!_name%` | 3 |
| `Hello!` | `%Hello!!%` | 5 |
| `O'Brien` | `%O'Brien%` | 6 |
| `50%_off!` | `%50!%!_off!!%` | 7 |

Nếu tìm `100%` mà nhận cả ID 2, khả năng cao là phần trăm trong input chưa được escape thành literal. Nếu tìm `file_name` mà nhận ID 4, dấu gạch dưới chưa được escape đúng hoặc SQL không áp dụng clause như dự kiến.

**Cần test trên DBMS thật:** Các bài test in-memory chỉ xác minh DBMS in-memory đó; chúng không bảo đảm hành vi PostgreSQL, MySQL, MariaDB hoặc SQL Server production trùng khớp. Đặc biệt bổ sung test bracket nếu nhắm tới SQL Server, cũng như test case/collation cho dữ liệu Unicode của hệ thống.

### 12.3. Test hành vi khi input không hợp lệ

Ngoài các case có kết quả, cần quyết định và kiểm tra:

- `null` input: API ném lỗi rõ ràng, không ngầm biến thành chuỗi `"null"`.
- Chuỗi rỗng: API trả rỗng, bỏ filter hoặc validation error theo hợp đồng.
- Chỉ dấu `%`, chỉ dấu `_` và chỉ dấu `!`: kết quả phải là tìm các ký tự literal nếu dùng chế độ contains.
- Nhiều dấu escape liên tiếp: không được nhân đôi sai thứ tự.
- Từ khóa rất dài: giới hạn theo nghiệp vụ để tránh pattern quá tốn kém.
- Từ khóa có nháy đơn, dấu nháy kép, backslash và Unicode: vẫn bind thành một giá trị, không nối vào SQL.
- Cột NULL và chuỗi rỗng: hành vi khớp cần được mô tả rõ.

## 13. Xử lý lỗi và chẩn đoán khi LIKE không hoạt động

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra đầu tiên |
| --- | --- | --- |
| Tìm `100%` trả cả `1000` | Bind chứa `%` chưa escape. | In/ghi mẫu đã ẩn dữ liệu nhạy cảm, xem hàm escape và SQL `ESCAPE`. |
| Tìm `file_name` trả `fileXname` | `_` bị hiểu là wildcard. | Xác minh `!_` trong tham số bind. |
| Tìm `Hello!` không ra kết quả hoặc lỗi | Không escape chính dấu `!`. | Xác minh `!!`. |
| `LIKE ESCAPE` báo lỗi cú pháp | DBMS/driver không hỗ trợ cú pháp, ký tự escape không hợp lệ hoặc SQL viết sai. | Kiểm tra `supportsLikeEscapeClause()`, driver docs, SQL tối thiểu. |
| Tìm chữ hoa/thường khác kết quả mong đợi | Collation hoặc kiểu dữ liệu khác môi trường. | So collation DB/cột, version server và toán tử dùng. |
| Chỉ sai khi có dấu `[` | SQL Server có cú pháp pattern bằng ngoặc vuông. | Bổ sung escaping đặc thù SQL Server và integration test. |
| Query đúng nhưng rất chậm | Leading wildcard, bảng lớn hoặc không dùng được index phù hợp. | EXPLAIN/query plan, số hàng, index, giới hạn kết quả. |
| Không tìm thấy bản ghi có `NULL` | Logic ba giá trị của SQL. | Kiểm tra có yêu cầu `IS NULL` hay không. |
| Dùng `Pattern.quote` nhưng không khớp | Nhầm SQL LIKE với Java regex. | Thay bằng hàm escaping cho `LIKE`. |

Khi chẩn đoán bằng log, tránh ghi toàn bộ từ khóa người dùng nếu đó có thể là dữ liệu nhạy cảm. Có thể ghi **chế độ tìm kiếm, loại DBMS, tên truy vấn logic, độ dài input, số hàng, thời gian** và mã lỗi `SQLState`/mã lỗi hãng. Nếu cần ghi mẫu thực tế để debug, hãy dùng môi trường test với dữ liệu giả.

Không giải quyết lỗi bằng cách bỏ `ESCAPE '!'` hoặc tắt `PreparedStatement`. Những thao tác đó có thể khiến kết quả rộng hơn dự kiến hoặc làm mất cơ chế chống SQL injection.

## 14. Quy trình thiết kế API tìm kiếm nhất quán

Một API tìm kiếm JDBC có thể được thiết kế theo các bước:

1. **Xác định hợp đồng tìm kiếm:** literal contains, prefix, suffix hay pattern nâng cao. Ghi rõ người dùng có được dùng wildcard hay không.
2. **Xác định DBMS/driver:** kiểm tra `ESCAPE`, collation, các wildcard đặc thù và giới hạn kiểu dữ liệu.
3. **Chọn ký tự escape:** ví dụ `!`; cố định ký tự đó trong SQL và helper tạo pattern.
4. **Escape phần dữ liệu người dùng:** xử lý `%`, `_`, ký tự escape và ký tự riêng của DBMS khi cần.
5. **Thêm wildcard của ứng dụng sau escaping:** ví dụ `%literal%` cho contains.
6. **Bind bằng `PreparedStatement.setString()`:** không nối từ khóa người dùng vào SQL.
7. **Định nghĩa chính sách null/rỗng/độ dài:** tránh vô ý biến đầu vào rỗng thành tìm mọi bản ghi.
8. **Giới hạn tài nguyên và truy cập:** phân trang ở server, quyền dữ liệu, timeout và quan sát độ trễ.
9. **Kiểm thử trên DBMS thật:** gồm ký tự đặc biệt, Unicode/collation, dữ liệu rỗng và kế hoạch truy vấn.
10. **Ghi nhận quyết định:** lưu rõ tên helper, SQL escape clause và phiên bản DBMS/driver đã thử nghiệm.

~~~mermaid
flowchart LR
    A[Input người dùng] --> B{Chế độ tìm kiếm?}
    B -->|Literal| C[Escape %, _, !]
    B -->|Pattern nâng cao| D[Phân tích cú pháp wildcard được phép]
    C --> E[Thêm wildcard theo mode]
    D --> E
    E --> F[PreparedStatement.setString]
    F --> G[LIKE ? ESCAPE '!']
    G --> H[DBMS trả các hàng phù hợp]
~~~

Lưu ý sơ đồ: ở chế độ pattern nâng cao, phần xử lý cú pháp phải giữ đúng sự khác biệt giữa wildcard được phép và ký tự literal. Nếu parser chưa được thiết kế, nên cung cấp duy nhất chế độ literal để tránh kết quả bất ngờ.

## 15. Checklist khi làm việc với điều kiện LIKE

- [ ] Biết chính xác người dùng muốn tìm **literal text** hay được phép nhập **wildcard pattern**.
- [ ] Sử dụng `PreparedStatement` và placeholder cho **giá trị pattern**.
- [ ] Với literal search, escape ít nhất `%`, `_` và **chính ký tự escape**.
- [ ] Giữ đồng bộ giữa hàm escape và cú pháp `ESCAPE '!'`.
- [ ] Thêm `%` do ứng dụng chủ động cấp **sau khi escape** đầu vào.
- [ ] Không dùng `Pattern.quote()`, HTML escaping hay SQL quote escaping thay cho LIKE escaping.
- [ ] Không tự nhân đôi dấu nháy đơn khi bind giá trị bằng `setString(...)`.
- [ ] Xác minh wildcard bổ sung của DBMS, đặc biệt ngoặc vuông của SQL Server.
- [ ] Định nghĩa đầu vào rỗng, `NULL`, collation, case sensitivity và Unicode theo nghiệp vụ.
- [ ] Giới hạn kết quả, phân trang và xem query plan cho `%term%` trên bảng lớn.
- [ ] Kiểm thử các chuỗi `100%`, `file_name`, `Hello!`, `O'Brien` và Unicode trên DBMS đích.
- [ ] Giữ `ResultSet`/`PreparedStatement`/`Connection` trong `try-with-resources`; không trả tài nguyên JDBC đã đóng.

**Ghi nhớ:** `PreparedStatement` giúp bind dữ liệu an toàn nhưng **không tự làm vô hiệu ký tự đại diện của `LIKE`**. Khi tìm chuỗi theo nghĩa đen, hãy escape đúng các ký tự `%`, `_` và ký tự escape, sau đó mới thêm wildcard theo mục đích contains/prefix/suffix. Cấu trúc SQL luôn cố định, pattern luôn được bind bằng JDBC và hành vi phải được xác minh trên hệ quản trị cơ sở dữ liệu thực tế.
