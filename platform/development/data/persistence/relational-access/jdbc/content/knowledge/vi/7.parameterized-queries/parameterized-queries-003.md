# Phân biệt tham số giá trị và cấu trúc câu SQL trong JDBC

Trong ứng dụng Java truy cập cơ sở dữ liệu quan hệ bằng **JDBC (Java Database Connectivity)**, câu SQL thường có phần cố định và phần thay đổi theo yêu cầu: mã sản phẩm cần tìm, khoảng giá, cột dùng để sắp xếp, danh sách mã cần lọc hoặc tên bảng cần thao tác. Tuy nhiên, không phải mọi thành phần “thay đổi” đều có thể đưa vào **tham số truy vấn**.

Phân biệt quan trọng nhất là:

- **Giá trị dữ liệu (value):** Dùng dấu giữ chỗ **?** trong câu SQL và truyền giá trị bằng các phương thức **setXxx(...)** của **PreparedStatement**.
- **Cấu trúc SQL (structure):** Tên bảng, tên cột, toán tử, từ khóa, hướng sắp xếp và các đoạn biểu thức SQL phải được xác định bằng **cú pháp SQL hợp lệ**, không thể thay thế bằng một dấu **?** để “biến nó thành mã SQL”.

Nhầm lẫn hai loại này có thể khiến câu SQL không hợp lệ, cho ra kết quả sai hoặc mở đường cho **SQL injection** khi ứng dụng nối trực tiếp chuỗi đầu vào vào cấu trúc câu lệnh. Bài học thuộc chương **Truy vấn tham số** này giải thích cách xác định ranh giới và xử lý an toàn những phần SQL cần thay đổi.

## 1. Một câu SQL gồm cấu trúc và giá trị

Xét truy vấn tìm các sản phẩm trong một danh mục, có giá không vượt quá mức yêu cầu:

~~~sql
SELECT id, name, price
FROM products
WHERE category_id = ? AND price <= ?
ORDER BY price ASC
~~~

Trong đó:

| Thành phần | Thuộc loại | Có thể dùng tham số **?**? |
| --- | --- | --- |
| **products** | Tên bảng | Không |
| **id**, **name**, **price**, **category_id** | Tên cột | Không |
| **SELECT**, **FROM**, **WHERE**, **AND**, **ORDER BY**, **ASC** | Từ khóa và cấu trúc SQL | Không |
| **=**, **<=** | Toán tử so sánh | Không thể dùng **?** để thay toán tử |
| Mã danh mục (ví dụ **12**) | Giá trị dữ liệu | Có |
| Giá tối đa (ví dụ **499000.00**) | Giá trị dữ liệu | Có |

Phía Java chỉ cần gán dữ liệu vào hai vị trí **?**, theo thứ tự từ trái sang phải:

~~~java
String sql = """
        SELECT id, name, price
        FROM products
        WHERE category_id = ? AND price <= ?
        ORDER BY price ASC
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, categoryId);
    statement.setBigDecimal(2, maxPrice);

    try (ResultSet results = statement.executeQuery()) {
        while (results.next()) {
            System.out.println(results.getString("name"));
        }
    }
}
~~~

Ví dụ trên dùng **text block** của Java 15 trở lên; ở Java cũ hơn có thể dùng chuỗi thường. Biến **connection**, **categoryId** và **maxPrice** do ngữ cảnh ứng dụng cung cấp. Chỉ số tham số JDBC **bắt đầu từ 1**, không phải 0.

Driver JDBC nhận câu SQL và các giá trị được bind, sau đó chuyển chúng đến cơ sở dữ liệu bằng cơ chế thích hợp. Chi tiết prepare phía client hay server phụ thuộc driver và hệ quản trị cơ sở dữ liệu; điều quan trọng đối với lập trình viên là các giá trị được truyền theo kiểu **dữ liệu** thay vì nối thành đoạn cú pháp SQL.

## 2. Dấu **?** là một giá trị, không phải một mảnh SQL

Một số cách dùng thường gây nhầm lẫn:

~~~sql
-- ĐÚNG: ? đứng ở vị trí giá trị so sánh.
SELECT id, name FROM products WHERE id = ?;

-- KHÔNG ĐÚNG: ? không thể thay tên bảng.
SELECT id, name FROM ? WHERE id = ?;

-- KHÔNG ĐÚNG VỀ Ý ĐỊNH: ? không chọn được tên cột.
SELECT id, name FROM products WHERE ? = ?;

-- KHÔNG ĐÚNG: ? không thể thay toán tử bằng chuỗi ">=".
SELECT id, name FROM products WHERE price ? ?;

-- KHÔNG ĐÚNG VỀ Ý ĐỊNH: ? không thay được từ khóa ASC/DESC.
SELECT id, name FROM products ORDER BY price ?;
~~~

Trong biểu thức **WHERE ? = ?**, nếu hệ quản trị chấp nhận câu SQL, cả hai **?** vẫn là **hai giá trị**. Truyền chuỗi **"price"** vào tham số thứ nhất sẽ tạo phép so sánh với một giá trị chuỗi, **không biến nó thành tham chiếu tới cột price**.

Tương tự, ở một số cơ sở dữ liệu, câu **ORDER BY ?** có thể được chấp nhận nhưng tham số được hiểu như một **hằng số**; vì vậy nó không sắp xếp theo tên cột mà người dùng nhập. Ở hệ quản trị khác câu này có thể bị từ chối. Không dựa vào hành vi này để xây dựng tính năng sắp xếp.

Một nhầm lẫn nữa là đặt dấu hỏi chấm bên trong dấu nháy:

~~~sql
-- SAI: '?' chỉ là ký tự ? trong một chuỗi SQL.
SELECT id FROM products WHERE name = '?';

-- ĐÚNG: dấu ? là placeholder ở ngoài dấu nháy.
SELECT id FROM products WHERE name = ?;
~~~

Khi đã dùng PreparedStatement, **không tự thêm dấu nháy** quanh giá trị chuỗi: **setString(...)** sẽ đưa dữ liệu vào đúng vị trí tham số.

## 3. Vì sao phân biệt này liên quan trực tiếp đến SQL injection?

Giả sử ứng dụng cho phép người dùng tìm sản phẩm theo tên. Đoạn mã sau tạo SQL bằng cách nối trực tiếp dữ liệu:

~~~java
// Không an toàn nếu name đến từ đầu vào không tin cậy.
String sql = "SELECT id FROM products WHERE name = '" + name + "'";
Statement statement = connection.createStatement();
ResultSet results = statement.executeQuery(sql);
~~~

Giá trị **name** có thể chứa dấu nháy đơn, từ khóa SQL hoặc một đoạn điều kiện. Khi nối chuỗi, dữ liệu có khả năng bị diễn giải thành **cấu trúc câu lệnh**.

Thay vào đó:

~~~java
String sql = "SELECT id FROM products WHERE name = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, name);
    try (ResultSet results = statement.executeQuery()) {
        // Xử lý kết quả.
    }
}
~~~

Nếu người dùng nhập chuỗi có dấu nháy hoặc các từ như **OR**, **UNION**, driver vẫn xử lý toàn bộ chuỗi đó như **giá trị của name**. Đây là một lợi ích bảo mật trọng tâm của parameterized query.

Tuy nhiên, một PreparedStatement **không bảo vệ các đoạn SQL được ứng dụng nối trước đó**:

~~~java
// NGUY HIỂM: sortColumn được nối trực tiếp vào cấu trúc SQL.
String sql = "SELECT id, name FROM products ORDER BY " + sortColumn;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    try (ResultSet results = statement.executeQuery()) {
        // ...
    }
}
~~~

Mặc dù dùng PreparedStatement, **sortColumn** vẫn được hiểu là mã SQL. Việc tạo PreparedStatement không tự biến chuỗi đã nối thành dữ liệu an toàn. Cần xử lý các thành phần cấu trúc bằng **tập giá trị được phép (allowlist)** hoặc các mẫu SQL cố định.

## 4. Trường hợp phổ biến: chọn cột và hướng **ORDER BY**

Ứng dụng thường cho phép sắp xếp danh sách theo **tên**, **giá** hoặc **ngày tạo**, theo thứ tự **tăng dần/giảm dần**. Tên cột và từ khóa **ASC/DESC** đều thuộc **cấu trúc SQL**, không thể bind bằng **setString()**.

Giải pháp là ánh xạ giá trị đầu vào sang **các đoạn SQL cố định do chương trình định nghĩa**:

~~~java
private static String allowedOrderColumn(String sortBy) {
    switch (sortBy) {
        case "name":
            return "name";
        case "price":
            return "price";
        case "created":
            return "created_at";
        default:
            throw new IllegalArgumentException("Cột sắp xếp không hợp lệ");
    }
}

private static String allowedDirection(String direction) {
    if ("asc".equalsIgnoreCase(direction)) {
        return "ASC";
    }
    if ("desc".equalsIgnoreCase(direction)) {
        return "DESC";
    }
    throw new IllegalArgumentException("Chiều sắp xếp không hợp lệ");
}
~~~

Sử dụng:

~~~java
String column = allowedOrderColumn(sortBy);
String direction = allowedDirection(sortDirection);

String sql = "SELECT id, name, price FROM products " +
             "WHERE category_id = ? ORDER BY " + column + " " + direction;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, categoryId);
    try (ResultSet results = statement.executeQuery()) {
        while (results.next()) {
            System.out.println(results.getString("name"));
        }
    }
}
~~~

Trong đoạn này, hai biến **column** và **direction** chỉ có thể chứa chuỗi SQL **định sẵn** được trả về từ hàm kiểm tra. Giá trị **categoryId** vẫn được bind bằng **?**. Cách tổ chức này tách rõ hai trách nhiệm:

1. **Quyết định cấu trúc hợp lệ:** Chọn tên cột và từ khóa sắp xếp từ tập cố định.
2. **Gán dữ liệu:** Dùng phương thức setLong hoặc setXxx thích hợp cho tham số.

Không nên chỉ kiểm tra tên cột bằng regex rồi mặc định có thể dùng mọi tên hợp lệ về cú pháp. Regex có thể từ chối ký tự nguy hiểm nhưng **không quyết định cột nào người dùng được phép truy cập**. Allowlist còn thể hiện yêu cầu nghiệp vụ và phạm vi truy cập dữ liệu.

## 5. Đổi tên bảng, schema hoặc cột một cách an toàn

Đôi khi ứng dụng chọn bảng theo phiên bản lưu trữ, loại báo cáo hoặc phân vùng dữ liệu. Một placeholder không thay thế được tên bảng:

~~~sql
-- Không hợp lệ: dấu ? không biểu diễn định danh bảng.
SELECT id, created_at FROM ? WHERE created_at >= ?;
~~~

Nếu thực sự cần chọn bảng ở thời điểm chạy, hãy ánh xạ từ giá trị nghiệp vụ sang **định danh cố định**:

~~~java
private static String allowedTable(String reportType) {
    switch (reportType) {
        case "orders":
            return "order_reports";
        case "returns":
            return "return_reports";
        default:
            throw new IllegalArgumentException("Loại báo cáo không hợp lệ");
    }
}

String table = allowedTable(reportType);
String sql = "SELECT id, created_at FROM " + table +
             " WHERE created_at >= ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setTimestamp(1, since);
    try (ResultSet results = statement.executeQuery()) {
        // Đọc báo cáo.
    }
}
~~~

Tương tự đối với tên **schema**, **cột**, **JOIN** và **hàm SQL**: chỉ đưa vào câu lệnh những thành phần đã được ứng dụng lựa chọn và cho phép. Không coi việc thêm dấu nháy định danh hay escape một chuỗi bất kỳ là phương án thay thế hoàn chỉnh cho allowlist và kiểm tra quyền.

Trong hệ thống nhiều tenant, việc lựa chọn schema/bảng còn liên quan đến **phân quyền và cô lập dữ liệu**. Dữ liệu chỉ nên đi đến bảng/schema mà tenant đang đăng nhập được phép sử dụng, dù tên định danh đó trông hợp lệ.

## 6. Điều kiện lọc tùy chọn: cấu trúc thay đổi, giá trị vẫn được bind

Một chức năng tìm kiếm có thể nhận **trạng thái** và **giá tối đa** tùy chọn. Khi không có bộ lọc, SQL không cần điều kiện tương ứng. Có thể ghép các **đoạn cấu trúc SQL cố định** rồi bind các giá trị được chọn:

~~~java
public static void searchProducts(
        Connection connection,
        String status,                 // null nghĩa là bỏ qua bộ lọc
        java.math.BigDecimal maxPrice  // null nghĩa là bỏ qua bộ lọc
) throws SQLException {
    StringBuilder sql = new StringBuilder(
            "SELECT id, name, price FROM products WHERE 1 = 1");

    if (status != null) {
        sql.append(" AND status = ?");
    }
    if (maxPrice != null) {
        sql.append(" AND price <= ?");
    }
    sql.append(" ORDER BY id");

    try (PreparedStatement statement = connection.prepareStatement(sql.toString())) {
        int index = 1;
        if (status != null) {
            statement.setString(index++, status);
        }
        if (maxPrice != null) {
            statement.setBigDecimal(index++, maxPrice);
        }

        try (ResultSet results = statement.executeQuery()) {
            while (results.next()) {
                System.out.println(results.getLong("id"));
            }
        }
    }
}
~~~

Ở đây **WHERE 1 = 1**, **AND status = ?** và **AND price <= ?** là các đoạn **cố định trong mã nguồn**. Biến đầu vào chỉ quyết định **có thêm bộ lọc đã cho phép hay không**; nó không trở thành một chuỗi điều kiện SQL tùy ý. Thứ tự bind phải khớp với thứ tự dấu **?** xuất hiện trong câu SQL cuối cùng.

Có thể tổ chức bộ lọc bằng phương thức riêng, builder hoặc thư viện hỗ trợ truy vấn để giữ mã dễ đọc khi nhiều điều kiện. Điều quan trọng vẫn là **cấu trúc được kiểm soát, giá trị được bind**.

## 7. Mệnh đề **IN** với số phần tử biến đổi

Giả sử người dùng cần lấy nhiều sản phẩm theo danh sách ID. Câu SQL cho ba ID:

~~~sql
SELECT id, name FROM products WHERE id IN (?, ?, ?)
~~~

Một dấu **?** tương ứng với **một biểu thức giá trị**, không có nghĩa là cả danh sách giá trị. Do đó:

~~~sql
-- Không diễn giải chuỗi "1,2,3" thành ba số độc lập.
SELECT id, name FROM products WHERE id IN (?);
~~~

Nếu bind chuỗi **"1,2,3"** vào dấu **?**, DB nhận **một chuỗi**, không phải ba tham số. Không nối trực tiếp các ID do người dùng cung cấp vào SQL để “giải quyết” vấn đề này.

Cách thông dụng là tạo **đúng số lượng placeholder**, rồi bind từng ID:

~~~java
public static java.util.List<Long> findExistingIds(
        Connection connection, java.util.List<Long> ids) throws SQLException {
    if (ids == null) {
        throw new IllegalArgumentException("ids không được null");
    }
    if (ids.isEmpty()) {
        return java.util.Collections.emptyList();
    }
    if (ids.size() > 500) {
        throw new IllegalArgumentException("Danh sách ID quá lớn");
    }

    String placeholders = String.join(
            ", ", java.util.Collections.nCopies(ids.size(), "?"));
    String sql = "SELECT id FROM products WHERE id IN (" + placeholders + ")";
    java.util.List<Long> found = new java.util.ArrayList<>();

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        for (int i = 0; i < ids.size(); i++) {
            statement.setLong(i + 1, ids.get(i));
        }

        try (ResultSet results = statement.executeQuery()) {
            while (results.next()) {
                found.add(results.getLong("id"));
            }
        }
    }
    return found;
}
~~~

Chuỗi ghép vào SQL chỉ gồm các ký hiệu **?** và dấu phẩy mà chương trình tự tạo; **không chứa nội dung ID đầu vào**. Mỗi ID vẫn được bind riêng. Đoạn mã xử lý cả danh sách rỗng (không tạo **IN ()**, vì có cơ sở dữ liệu không chấp nhận cú pháp này) và chặn danh sách vượt ngưỡng ví dụ 500 phần tử.

Giới hạn số tham số tùy driver/hệ quản trị. Với danh sách rất lớn, có thể cần chia nhỏ truy vấn, dùng bảng tạm hoặc một loại tham số mảng/bảng mà DB hỗ trợ. Không có một giới hạn hoặc cú pháp chung cho mọi JDBC driver.

## 8. **LIKE**, **NULL**, ngày giờ và phân trang: vẫn là giá trị, nhưng có ngữ nghĩa SQL

Các trường hợp sau không yêu cầu người dùng tự dựng cấu trúc SQL, nhưng giá trị được bind vẫn cần hiểu đúng ngữ nghĩa:

### 8.1. Tìm kiếm bằng **LIKE**

~~~java
String sql = "SELECT id, name FROM products WHERE name LIKE ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, prefix + "%");
    // executeQuery() và đọc ResultSet.
}
~~~

Tham số là **giá trị mẫu tìm kiếm**; dấu **%** do ứng dụng thêm vào có nghĩa khớp nhiều ký tự trong biểu thức **LIKE**. Nếu **prefix** do người dùng nhập chứa ký tự **%** hoặc **_**, các ký tự đó vẫn có ý nghĩa wildcard theo quy tắc SQL, dù giá trị được bind an toàn khỏi SQL injection.

Nếu yêu cầu là tìm đúng chuỗi ký tự người dùng nhập, cần **escape wildcard** theo cú pháp DB, ví dụ với ký tự escape **!** nếu hệ quản trị hỗ trợ mệnh đề tiêu chuẩn **ESCAPE**:

~~~java
String literal = userText.replace("!", "!!")
                         .replace("%", "!%")
                         .replace("_", "!_");

String sql = "SELECT id, name FROM products " +
             "WHERE name LIKE ? ESCAPE '!'";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "%" + literal + "%");
    // executeQuery() và đọc ResultSet.
}
~~~

Hành vi đối sánh, chữ hoa/chữ thường và cú pháp escape có thể khác nhau giữa các hệ quản trị; cần kiểm tra dialect được sử dụng.

### 8.2. Giá trị SQL **NULL**

**NULL** vẫn là một giá trị SQL đặc biệt, nhưng phép so sánh SQL có quy tắc riêng:

~~~sql
-- Không dùng để kiểm tra cột có NULL.
SELECT id FROM products WHERE deleted_at = ?;

-- Nếu muốn lấy các hàng có deleted_at là NULL:
SELECT id FROM products WHERE deleted_at IS NULL;
~~~

Ngay cả khi bind NULL vào **deleted_at = ?**, biểu thức so sánh cũng không trở thành điều kiện **IS NULL**. Nếu cần thay đổi giữa tìm giá trị và tìm NULL, chọn **mẫu điều kiện** phù hợp rồi bind các giá trị khi có.

Để bind NULL có chỉ rõ kiểu SQL, có thể dùng **setNull(index, java.sql.Types.TIMESTAMP)** hoặc overload **setObject** có truyền kiểu, tùy API/driver.

### 8.3. Ngày giờ, số và dữ liệu nhị phân

Cấu trúc SQL giữ cố định:

~~~sql
SELECT id FROM orders WHERE created_at >= ? AND total_amount <= ?
~~~

Các giá trị thay đổi được bind bằng kiểu tương ứng, chẳng hạn **setTimestamp(1, ...)**, **setBigDecimal(2, ...)**. Không nên nối các chuỗi ngày tháng hoặc số tiền vào câu SQL rồi phụ thuộc vào định dạng hệ điều hành và cơ sở dữ liệu. Có thể dùng các kiểu thời gian của **java.time** với **setObject** theo JDBC 4.2 nếu driver hỗ trợ loại Java/SQL tương ứng.

### 8.4. **LIMIT** và **OFFSET**

Số lượng hàng và vị trí phân trang là những **giá trị số**, nhưng vị trí có thể bind phụ thuộc cú pháp SQL của từng DB:

~~~sql
-- Ví dụ trên DB/driver hỗ trợ bind trong LIMIT và OFFSET:
SELECT id, name FROM products ORDER BY id LIMIT ? OFFSET ?
~~~

Nếu dialect hỗ trợ, ứng dụng có thể **setInt(1, pageSize)** và **setLong(2, offset)**, sau khi kiểm tra pageSize > 0, giới hạn pageSize và đảm bảo offset không âm/không tràn khi tính toán. Không mặc định cú pháp này chạy trên mọi DB: một số hệ quản trị dùng **FETCH FIRST**, **OFFSET ... ROWS** hoặc cấu trúc khác.

## 9. Phân biệt ba thao tác: bind dữ liệu, lựa chọn cấu trúc, và kiểm tra quyền

Một ứng dụng an toàn cần giải quyết ba vấn đề khác nhau:

| Việc cần làm | Công cụ phù hợp | Ví dụ |
| --- | --- | --- |
| **Truyền giá trị dữ liệu** | Placeholder **?** và **PreparedStatement.setXxx(...)** | categoryId, maxPrice, email, ngày tạo |
| **Chọn cấu trúc SQL hợp lệ** | Allowlist, enum, câu SQL cố định, query builder | Cột sort, hướng ASC/DESC, loại báo cáo |
| **Kiểm tra quyền/nghiệp vụ** | Kiểm tra ở service/repository, cơ chế phân quyền DB | Người dùng được xem đơn hàng của tenant nào? |

**Parameterized query không tự động kiểm tra quyền truy cập.** Ví dụ, câu **WHERE tenant_id = ?** tách dữ liệu an toàn khỏi cú pháp, nhưng ứng dụng vẫn phải lấy tenantId từ ngữ cảnh đã xác thực và kiểm tra quyền thích hợp. Bind một tenantId do người dùng tùy ý nhập không tự tạo ra bảo mật phân tách tenant.

Cũng không nên dùng allowlist để cho phép những cấu trúc SQL không phù hợp nghiệp vụ. Danh sách tên cột, bảng và câu lệnh được cho phép cần được quyết định theo thiết kế truy cập dữ liệu và quyền của người dùng.

## 10. Những sai lầm cần tránh

| Lỗi thường gặp | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng **FROM ?** để chọn tên bảng | Placeholder không biểu diễn định danh bảng. | Ánh xạ giá trị nghiệp vụ sang bảng được cho phép. |
| Dùng **ORDER BY ?** với tên cột | Có thể sắp theo hằng số hoặc bị DB từ chối. | Chọn tên cột từ allowlist cố định. |
| Dùng **WHERE price ? ?** để chọn toán tử | Tham số không thay thế toán tử SQL. | Chọn biểu thức/toán tử cố định từ tập được phép. |
| Nối **sortColumn** vào SQL mà không kiểm tra | Có thể tạo SQL injection tại phần cấu trúc. | Allowlist cột, hướng sắp xếp, expression. |
| Dùng **IN (?)** và bind chuỗi **"1,2,3"** | DB nhận một giá trị thay vì ba giá trị. | Tạo nhiều placeholder hoặc dùng cơ chế mảng/bảng chuyên biệt. |
| Dùng **'? '** hoặc **'?'** làm placeholder | Dấu hỏi trong literal không phải marker. | Đặt **?** ngoài dấu nháy. |
| Bind **NULL** rồi dùng **= ?** để tìm NULL | Không có hành vi như **IS NULL**. | Chọn điều kiện IS NULL khi thích hợp. |
| Dùng **LIKE ?** và tưởng **%**, **_** luôn là ký tự thường | Các wildcard vẫn có ý nghĩa trong LIKE. | Escape mẫu khi cần tìm kiếm nguyên văn. |
| Tin rằng mọi JDBC driver hỗ trợ **LIMIT ? OFFSET ?** | SQL có thể không hợp lệ theo dialect. | Xác minh cú pháp và khả năng bind của DB/driver. |
| Dùng PreparedStatement rồi cho rằng mọi phần SQL đã an toàn | Chuỗi cấu trúc nối vào trước prepare vẫn được hiểu như SQL. | Kiểm soát cấu trúc trước khi tạo PreparedStatement. |

## 11. Cách ra quyết định khi viết truy vấn động

~~~mermaid
flowchart TD
    A[Thành phần nào của truy vấn cần thay đổi?] --> B{Là giá trị dữ liệu?}
    B -- Có --> C[Dùng placeholder ? và setXxx]
    B -- Không --> D{Là cấu trúc SQL được phép thay đổi?}
    D -- Có --> E[Ánh xạ lựa chọn sang đoạn SQL cố định]
    D -- Không --> F[Từ chối yêu cầu]
    C --> G[Kiểm tra kiểu, giới hạn và quyền]
    E --> G
    G --> H[Tạo PreparedStatement và thực thi]
~~~

Ví dụ quyết định:

1. **Lọc theo email:** Email là giá trị → **WHERE email = ?** và **setString**.
2. **Sắp xếp theo giá:** Tên cột là cấu trúc → allowlist **price**, sau đó nối chuỗi cố định **ORDER BY price**.
3. **Chuyển giữa tăng và giảm dần:** **ASC/DESC** là từ khóa → kiểm tra lựa chọn và dùng chuỗi cố định.
4. **Lọc theo danh sách ID:** Số lượng placeholder tạo từ số phần tử, từng ID vẫn dùng **setLong**.
5. **Thêm điều kiện tùy chọn:** Chỉ nối những mệnh đề SQL được định nghĩa sẵn, rồi bind giá trị tương ứng.

## 12. Câu hỏi tự kiểm tra

1. Vì sao **setString(1, "price")** không khiến **ORDER BY ?** sắp xếp theo cột price?
2. Trong một truy vấn cần chọn bảng từ ba bảng cố định, phương án an toàn để chọn tên bảng là gì?
3. Vì sao nối chuỗi tên cột không tin cậy vào SQL vẫn nguy hiểm ngay cả khi ứng dụng gọi **prepareStatement()**?
4. Với danh sách bốn ID, cần bao nhiêu placeholder cho **IN** và phải bind ra sao?
5. Điều kiện **WHERE deleted_at = ?** với tham số NULL có thay thế được **IS NULL** không?
6. Khác biệt giữa việc **bind dữ liệu an toàn** và **kiểm tra quyền truy cập dữ liệu** là gì?

**Ghi nhớ:** Trong JDBC, **PreparedStatement** nhận **giá trị** qua các tham số được bind đúng kiểu và vị trí; nó không dùng dấu **?** để thay tên bảng, tên cột, từ khóa, toán tử hay cả một mệnh đề SQL. Khi cấu trúc cần thay đổi, hãy chọn từ các phần SQL **cố định, được phép và đã kiểm tra quyền**, rồi bind riêng những giá trị dữ liệu. Ranh giới này giúp truy vấn đúng ngữ nghĩa, dễ bảo trì và giảm nguy cơ SQL injection.
