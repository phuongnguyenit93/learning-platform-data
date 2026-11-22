# Phân biệt cập nhật toàn bộ và cập nhật một phần trong JDBC

Trong chương **CRUD và khóa sinh**, sau khi tạo và truy vấn bản ghi, thao tác **Update** đặt ra một câu hỏi quan trọng: khi người dùng chỉ sửa một thuộc tính, ứng dụng nên ghi lại toàn bộ dữ liệu của bản ghi hay chỉ ghi thuộc tính đã thay đổi?

Với **JDBC**, cả hai cách đều dùng câu lệnh SQL `UPDATE` qua `PreparedStatement`. Sự khác biệt nằm ở **tập cột có trong mệnh đề `SET`**, **hợp đồng dữ liệu đầu vào** và **cách kiểm soát thay đổi đồng thời**. Nắm rõ sự khác biệt này giúp ứng dụng Java truy cập cơ sở dữ liệu quan hệ an toàn, tránh vô tình xóa giá trị và giảm nguy cơ ghi đè thay đổi của người khác.

## 1. Hai kiểu cập nhật là gì?

**Cập nhật toàn bộ (full update/full replacement)** yêu cầu bên gọi cung cấp một biểu diễn đầy đủ của **các thuộc tính được phép thay thế**. Chương trình ghi giá trị mới cho tất cả các cột thuộc phạm vi đó, kể cả cột có giá trị không đổi. Nếu một thuộc tính nullable được gửi rõ ràng là `null`, giá trị trong cơ sở dữ liệu sẽ được đặt thành `NULL`.

**Cập nhật một phần (partial update/patch)** chỉ ghi các thuộc tính mà bên gọi yêu cầu thay đổi. Thuộc tính không được gửi sẽ được giữ nguyên. Một thuộc tính **có mặt với giá trị `null`** có thể mang nghĩa chủ động xóa giá trị cũ, nếu hợp đồng API và ràng buộc cột cho phép.

Đây là **hai chính sách cập nhật của ứng dụng**, không phải hai lệnh SQL khác nhau. JDBC không có phương thức `updateFull()` hay `updatePartial()` được tiêu chuẩn hóa; cả hai thường gọi `PreparedStatement.executeUpdate()`.

| Tiêu chí | Cập nhật toàn bộ | Cập nhật một phần |
| --- | --- | --- |
| Dữ liệu đầu vào | Đầy đủ các trường có thể thay thế | Chỉ các trường cần sửa |
| Cột trong SQL `SET` | Danh sách cố định các cột được thay thế | Danh sách cột dựa trên trường được gửi |
| Trường không xuất hiện | Thường là dữ liệu đầu vào không hợp lệ; không được âm thầm coi là không đổi | Giữ nguyên giá trị hiện tại |
| Trường xuất hiện với `null` | Ghi `NULL` nếu cột cho phép | Ghi `NULL` nếu có yêu cầu xóa rõ ràng |
| Rủi ro đáng chú ý | Ghi đè dữ liệu mới bằng bản sao cũ nếu thiếu kiểm soát đồng thời | Nhầm “không gửi” với “xóa giá trị”; dựng SQL động không an toàn |
| Phù hợp | Form chỉnh sửa đầy đủ, đồng bộ toàn bộ các trường được phép cập nhật | Đổi email, cập nhật trạng thái, sửa vài thuộc tính |

> **Phạm vi của “toàn bộ”:** Không phải ghi đè mọi cột trong bảng. Khóa chính `id`, dữ liệu do cơ sở dữ liệu quản lý và các trường bất biến thường **không nằm trong tập trường được thay thế**. Ví dụ: cập nhật khách hàng không làm thay đổi khóa chính hay tạo lại khóa sinh tự động.

Có thể liên hệ với API HTTP: `PUT` thường biểu diễn ý định thay thế tài nguyên, còn `PATCH` biểu diễn sửa đổi một phần. Tuy nhiên, **ý nghĩa thực tế phải do hợp đồng API quy định**; SQL và JDBC không tự suy ra ngữ nghĩa từ phương thức HTTP.

## 2. Ví dụ xuyên suốt: bảng `customers`

Giả sử bảng quan hệ có các cột:

| Cột | Kiểu minh họa | Quy tắc |
| --- | --- | --- |
| `id` | `BIGINT` | Khóa chính, không sửa |
| `full_name` | `VARCHAR(120)` | Bắt buộc |
| `email` | `VARCHAR(200)` | Bắt buộc |
| `phone` | `VARCHAR(30)` | Có thể `NULL` |
| `version` | `BIGINT` | Phiên bản phục vụ khóa lạc quan |

Lược đồ minh họa (cú pháp tạo khóa tự sinh `id` khác nhau giữa các hệ quản trị CSDL):

```sql
CREATE TABLE customers (
    id        BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email     VARCHAR(200) NOT NULL,
    phone     VARCHAR(30) NULL,
    version   BIGINT NOT NULL DEFAULT 0
);
```

Giả sử trước khi cập nhật, bản ghi có trạng thái:

```text
id = 42
full_name = "Nguyễn An"
email = "an@example.com"
phone = "0901234567"
version = 7
```

### 2.1. Cập nhật toàn bộ

Người dùng gửi một biểu diễn đầy đủ với tên mới, email mới và số điện thoại mới. SQL đặt lại **cả ba cột dữ liệu được phép cập nhật**:

```sql
UPDATE customers
SET full_name = ?,
    email = ?,
    phone = ?,
    version = version + 1
WHERE id = ? AND version = ?;
```

Thứ tự tham số: `full_name`, `email`, `phone`, `id`, `expectedVersion`. Nếu phiên bản trong bảng vẫn là `7`, câu lệnh cập nhật bản ghi và tăng `version` thành `8`. Nếu bản ghi không tồn tại hoặc phiên bản đã đổi, `executeUpdate()` trả về `0` hàng được cập nhật.

Điểm cần lưu ý: nếu bên gọi có bản sao cũ với `phone = "0901234567"` và vô tình gửi lại giá trị đó, câu lệnh sẽ ghi lại số điện thoại cũ **ngay cả khi ý định ban đầu chỉ là đổi email**. Điều kiện `version` trong ví dụ là hàng rào phát hiện dữ liệu cũ.

### 2.2. Cập nhật một phần

Nếu người dùng chỉ đổi email, SQL chỉ ghi cột `email`:

```sql
UPDATE customers
SET email = ?,
    version = version + 1
WHERE id = ? AND version = ?;
```

Các cột `full_name` và `phone` không xuất hiện trong `SET` nên **giữ nguyên**.

Nếu người dùng yêu cầu xóa số điện thoại:

```sql
UPDATE customers
SET phone = ?,
    version = version + 1
WHERE id = ? AND version = ?;
-- Tham số phone được gán SQL NULL bằng PreparedStatement.setNull(...)
```

Không được đồng nhất ba trường hợp sau:

```json
{"email": "an.moi@example.com"}
```

Chỉ đổi `email`, giữ nguyên `phone`.

```json
{"phone": null}
```

Yêu cầu xóa `phone` (chỉ hợp lệ khi hợp đồng API hỗ trợ và cột cho phép `NULL`).

```json
{}
```

Không có trường nào để cập nhật; ứng dụng nên quy định rõ đây là **no-op** hay yêu cầu không hợp lệ. Ví dụ triển khai bên dưới chọn **báo lỗi đầu vào** để tránh thực thi câu lệnh không có ý nghĩa.

## 3. Triển khai trong Java bằng `PreparedStatement`

Ví dụ dùng Java 17+ và JDBC chuẩn, nhận sẵn một `Connection`. Việc lấy kết nối từ `DataSource`, quản lý transaction và đóng kết nối thuộc trách nhiệm lớp gọi. Nhờ vậy cùng một phương thức có thể tham gia một transaction lớn hơn.

Một số nguyên tắc của ví dụ:

- **Luôn tham số hóa giá trị** bằng `?`, không ghép dữ liệu người dùng vào SQL.
- **Không tham số hóa được tên cột** bằng `?`. Khi cập nhật một phần, tên cột phải tra từ danh sách cho phép do ứng dụng định nghĩa.
- **Phân biệt trường vắng mặt với trường có giá trị `null`** bằng `Map.containsKey()` (hoặc cấu trúc dữ liệu tương đương).
- **Dùng khóa chính và phiên bản dự kiến** trong `WHERE` để tránh ghi đè một bản ghi đã bị thay đổi.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class CustomerUpdateRepository {
    private CustomerUpdateRepository() {}

    // Chỉ các trường được phép sửa mới có thể thành tên cột SQL.
    private static final Map<String, String> ALLOWED_COLUMNS = Map.of(
        "fullName", "full_name",
        "email", "email",
        "phone", "phone"
    );

    public record CustomerReplacement(
        String fullName,
        String email,
        String phone
    ) {}

    public static int updateFull(
        Connection connection,
        long id,
        long expectedVersion,
        CustomerReplacement data
    ) throws SQLException {
        if (data == null) {
            throw new IllegalArgumentException("Thiếu dữ liệu thay thế");
        }
        requireText(data.fullName(), "fullName");
        requireText(data.email(), "email");

        String sql = """
            UPDATE customers
            SET full_name = ?, email = ?, phone = ?,
                version = version + 1
            WHERE id = ? AND version = ?
            """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setString(1, data.fullName());
            ps.setString(2, data.email());
            setNullablePhone(ps, 3, data.phone());
            ps.setLong(4, id);
            ps.setLong(5, expectedVersion);
            return ps.executeUpdate();
        }
    }

    // Map chứa một khóa nghĩa là muốn sửa trường đó,
    // kể cả khi giá trị đi kèm là null.
    public static int updatePartial(
        Connection connection,
        long id,
        long expectedVersion,
        Map<String, String> changes
    ) throws SQLException {
        if (changes == null || changes.isEmpty()) {
            throw new IllegalArgumentException("Không có trường cần sửa");
        }

        List<String> assignments = new ArrayList<>();
        List<String> values = new ArrayList<>();

        for (Map.Entry<String, String> entry : changes.entrySet()) {
            String field = entry.getKey();
            String column = ALLOWED_COLUMNS.get(field);
            if (column == null) {
                throw new IllegalArgumentException(
                    "Trường không được phép sửa: " + field
                );
            }

            String value = entry.getValue();
            if (!"phone".equals(field)) {
                requireText(value, field);
            }
            assignments.add(column + " = ?");
            values.add(value);
        }

        String sql = "UPDATE customers SET "
            + String.join(", ", assignments)
            + ", version = version + 1"
            + " WHERE id = ? AND version = ?";

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            for (int i = 0; i < values.size(); i++) {
                String value = values.get(i);
                if (value == null) {
                    ps.setNull(i + 1, Types.VARCHAR);
                } else {
                    ps.setString(i + 1, value);
                }
            }
            ps.setLong(values.size() + 1, id);
            ps.setLong(values.size() + 2, expectedVersion);
            return ps.executeUpdate();
        }
    }

    private static void setNullablePhone(
        PreparedStatement ps, int index, String phone
    ) throws SQLException {
        if (phone == null) {
            ps.setNull(index, Types.VARCHAR);
        } else {
            ps.setString(index, phone);
        }
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                field + " phải có giá trị không rỗng"
            );
        }
    }
}
```

Cách gọi minh họa:

```java
// Thay thế đầy đủ các thuộc tính được phép sửa.
int updatedFull = CustomerUpdateRepository.updateFull(
    connection,
    42L,
    7L,
    new CustomerUpdateRepository.CustomerReplacement(
        "Nguyễn An",
        "an.moi@example.com",
        "0901234567"
    )
);

// Với bản ghi có version = 8 sau cập nhật thành công ở trên:
Map<String, String> changes = new java.util.HashMap<>();
changes.put("phone", null); // Chủ động xóa giá trị phone.
int updatedPartial = CustomerUpdateRepository.updatePartial(
    connection, 42L, 8L, changes
);
```

Hai lệnh trên chỉ là **hai thao tác nối tiếp minh họa**: lệnh thứ hai cần `expectedVersion = 8` nếu lệnh đầu thành công. Trong ứng dụng thực tế, hãy lấy phiên bản từ bản ghi mà người dùng đã đọc, kiểm tra kết quả và quyết định `commit`/`rollback` theo nghiệp vụ. Nếu cùng một transaction chạy nhiều cập nhật, phiên bản dự kiến phải được cập nhật tương ứng sau mỗi lần ghi thành công.

Ví dụ nhận `Map<String, String>` để tập trung vào ba trường chuỗi. Với số, ngày giờ, enum hoặc JSON, nên dùng **DTO có kiểu rõ ràng**, ánh xạ đúng `JDBC Types` và kiểm tra hợp lệ trước khi tạo SQL. Với trường nullable, DTO cập nhật một phần cần biểu diễn được **ba trạng thái**: không gửi, gửi giá trị, gửi `null`; riêng `Optional<T>` thông thường không đủ để biểu diễn cả ba nếu không có quy ước hoặc lớp bao bổ sung.

## 4. Ngăn ghi đè dữ liệu khi nhiều người cùng sửa

Giả sử hai người đọc cùng bản ghi `version = 7`:

1. **A** đổi email và lưu thành công, phiên bản tăng thành `8`.
2. **B** vẫn giữ dữ liệu đã đọc ở phiên bản `7`; B đổi số điện thoại.
3. Nếu B gửi **cập nhật toàn bộ không kiểm tra phiên bản**, email cũ trong bản sao của B có thể ghi đè email mới của A.
4. Nếu B gửi **cập nhật một phần**, email không nằm trong `SET` nên không bị ghi đè. Tuy nhiên, nếu A và B cùng đổi **một trường**, thao tác sau vẫn có thể đè thao tác trước nếu không kiểm soát đồng thời.
5. Với điều kiện `WHERE id = ? AND version = ?`, thao tác dùng phiên bản `7` sẽ cập nhật `0` hàng sau khi A đã lưu. B phải tải lại trạng thái mới và quyết định cách áp dụng thay đổi.

Đây là **optimistic locking bằng cột phiên bản**. Bản thân SQL `UPDATE` có điều kiện phiên bản thực hiện việc kiểm tra và tăng phiên bản trong cùng một câu lệnh, tránh khoảng hở giữa bước kiểm tra và bước ghi.

```mermaid
sequenceDiagram
    participant A as Người dùng A
    participant DB as Cơ sở dữ liệu
    participant B as Người dùng B
    A->>DB: Đọc id=42, version=7
    B->>DB: Đọc id=42, version=7
    A->>DB: UPDATE ... WHERE version=7
    DB-->>A: 1 hàng; version=8
    B->>DB: UPDATE ... WHERE version=7
    DB-->>B: 0 hàng; dữ liệu không bị ghi đè
    B->>DB: Tải lại bản ghi mới
```

Trong ví dụ, `executeUpdate()` trả:

- **`1`**: một bản ghi đã được cập nhật (vì `id` là khóa chính).
- **`0`**: không có bản ghi phù hợp với cả `id` và `expectedVersion`; có thể **không tồn tại** hoặc **xung đột phiên bản**. Nếu cần trả lỗi khác nhau, phải kiểm tra tồn tại bằng thao tác bổ sung phù hợp với yêu cầu nhất quán.
- **`SQLException`**: lỗi thực thi JDBC/SQL, chẳng hạn vi phạm ràng buộc hoặc mất kết nối; xử lý, rollback khi cần và ghi log có kiểm soát.

Có thể dùng một cơ chế phiên bản chặt chẽ với cả cập nhật toàn bộ và cập nhật một phần. Đây là cách đơn giản để áp dụng chính sách **phát hiện cập nhật dựa trên dữ liệu cũ**. Trong trường hợp muốn cho phép các thay đổi trên những trường độc lập diễn ra song song, cần thiết kế cơ chế giải quyết xung đột cụ thể; không nên bỏ khóa lạc quan mà không đánh giá yêu cầu nghiệp vụ.

## 5. Những lỗi thiết kế dễ gặp

### 5.1. Đồng nhất “không gửi” với `NULL`

Một bộ giải mã JSON hoặc DTO có thể trả `null` cho cả trường bị bỏ qua và trường được gửi là `null`. Nếu không lưu thông tin **trường có hiện diện hay không**, ứng dụng cập nhật một phần có thể vô tình xóa dữ liệu.

**Cách xử lý:** dùng cấu trúc mang thông tin hiện diện (ví dụ `Map.containsKey()`, `JsonNode.has()` hoặc `PatchField<T>`) và thiết kế rõ quy tắc xóa giá trị. Không dùng biểu thức như `COALESCE(?, phone)` nếu nghiệp vụ cần cho phép xóa `phone`, vì `NULL` khi đó bị hiểu thành “giữ nguyên”.

### 5.2. Nhận tên cột tùy ý từ yêu cầu bên ngoài

Sai:

```java
String sql = "UPDATE customers SET " + clientField + " = ? WHERE id = ?";
```

Nếu `clientField` lấy trực tiếp từ người dùng, câu lệnh có nguy cơ bị chèn SQL hoặc cho sửa trường ngoài thẩm quyền.

**Cách xử lý:** đổi tên trường API thành tên cột từ **allowlist** cố định; chỉ nối các tên cột đã được ứng dụng phê duyệt. `PreparedStatement` bảo vệ **giá trị tham số**, không biến tên bảng/cột tùy ý thành an toàn.

### 5.3. Quên `WHERE` hoặc quên kiểm tra số hàng cập nhật

```sql
-- Nguy hiểm: có thể sửa mọi khách hàng.
UPDATE customers SET email = ?;
```

Phải giới hạn đúng bản ghi bằng khóa chính hoặc điều kiện nghiệp vụ phù hợp. Đặc biệt, trong trường hợp dùng khóa lạc quan, **đừng xem việc chạy câu lệnh không ném ngoại lệ là cập nhật thành công**; hãy kiểm tra số hàng từ `executeUpdate()`.

### 5.4. Dùng đối tượng thiếu trường để thực hiện full update

Nếu một form chỉ gửi `email`, nhưng server đưa dữ liệu đó vào DTO thay thế đầy đủ và mặc định `phone = null`, việc full update có thể làm mất số điện thoại. Cần xác minh **đầu vào đầy đủ** cho các trường thuộc phạm vi thay thế, và phân biệt `null` hợp lệ với thuộc tính bắt buộc bị thiếu.

Đồng thời, không nên lấy các giá trị nhạy cảm hoặc do hệ thống tự quản lý (như `id`, `version`, `created_at`) từ payload rồi tự động ghi đè bằng một phép gán hàng loạt.

### 5.5. Đoán rằng partial update luôn nhanh hơn và ít khóa hơn

Partial update thường giảm số giá trị truyền và làm rõ các cột cần sửa, nhưng nhiều cơ sở dữ liệu vẫn phải xử lý cập nhật ở **mức hàng**, ghi log và chạy trigger. SQL động còn tạo nhiều hình dạng câu lệnh, ảnh hưởng đến tái sử dụng `PreparedStatement`, kế hoạch thực thi và batching.

**Cách xử lý:** chọn kiểu cập nhật theo ngữ nghĩa và yêu cầu nhất quán trước; khi cần tối ưu, hãy đo thực tế trên hệ quản trị CSDL đang dùng. Với các thao tác partial có tập cột cố định thường gặp (ví dụ chỉ cập nhật trạng thái), câu lệnh SQL cố định giúp mã rõ hơn và dễ batch hơn.

## 6. Chọn kiểu cập nhật theo tình huống

| Tình huống | Cách phù hợp | Lý do |
| --- | --- | --- |
| Lưu form chỉnh sửa hồ sơ chứa đủ mọi trường cho phép thay thế | Toàn bộ | Hợp đồng yêu cầu một biểu diễn hoàn chỉnh, dễ xác thực |
| Người dùng chỉ thay đổi email | Một phần | Không ghi lại tên và số điện thoại không liên quan |
| Xóa số điện thoại | Một phần với `phone = NULL` | Cần thể hiện rõ thao tác xóa, khác trường bị bỏ qua |
| Đồng bộ bản ghi từ nguồn chuẩn có dữ liệu đầy đủ | Toàn bộ, kèm kiểm soát phiên bản/quyền ghi | Mục tiêu là thay thế toàn bộ tập thuộc tính được quản lý |
| Cập nhật trạng thái đơn lẻ, lặp lại với tần suất cao | Một phần bằng SQL cố định | Câu lệnh rõ, ít tham số và thuận tiện sử dụng lại |
| Nhiều người cùng chỉnh sửa một khách hàng | Cả hai, kèm kiểm soát đồng thời | Partial update không tự giải quyết mọi xung đột |

Trong một **transaction**, nhiều lệnh cập nhật có thể cần thành công hoặc thất bại cùng nhau. Khi đó bên gọi quản lý `Connection.setAutoCommit(false)`, `commit()` và `rollback()`. Không tự mở connection mới bên trong mỗi phương thức repository nếu chúng phải tham gia cùng một transaction.

## 7. Tự kiểm tra bằng tình huống

**Tình huống A.** Cơ sở dữ liệu đang lưu `phone = "0901234567"`. Payload partial chỉ có `{"email":"new@example.com"}`. Sau cập nhật thành công, `phone` bằng gì?

**Đáp án:** vẫn là `"0901234567"`, vì `phone` không nằm trong `SET`.

**Tình huống B.** Payload partial có `{"phone":null}`. Cột `phone` cho phép `NULL`. Cần xử lý ra sao?

**Đáp án:** nếu API định nghĩa `null` là lệnh xóa, đưa `phone` vào `SET` và truyền `SQL NULL` bằng `setNull(..., Types.VARCHAR)`. Không tự bỏ qua trường vì giá trị là `null`.

**Tình huống C.** Lệnh có `WHERE id = 42 AND version = 7` trả về `0` hàng. Có kết luận chắc chắn khách hàng `42` không tồn tại không?

**Đáp án:** không. Khách hàng có thể còn tồn tại nhưng `version` đã thay đổi; cần xử lý trường hợp xung đột hoặc xác minh bổ sung.

**Tình huống D.** Hai yêu cầu cùng cập nhật `email` nhưng không sử dụng `version`. Partial update có đảm bảo không mất thay đổi không?

**Đáp án:** không. Nếu cả hai cập nhật cùng một cột, giá trị ghi sau vẫn có thể ghi đè giá trị trước.

## Ghi nhớ

- **Full update** thay thế toàn bộ **các trường được phép cập nhật**; yêu cầu đầu vào đầy đủ và tránh ghi lại bản sao dữ liệu đã cũ.
- **Partial update** chỉ thay đổi những trường được chỉ định; phải phân biệt rõ **không gửi trường** với **gửi `null`**.
- Với **JDBC**, cả hai đều dùng `UPDATE` và `PreparedStatement`; chỉ các **giá trị** được gắn qua placeholder `?`, còn tên cột động phải nằm trong allowlist.
- Dùng `WHERE` theo khóa chính, kiểm tra `executeUpdate()` và cân nhắc **optimistic locking** bằng `version` để bảo vệ tính toàn vẹn khi cập nhật đồng thời.
