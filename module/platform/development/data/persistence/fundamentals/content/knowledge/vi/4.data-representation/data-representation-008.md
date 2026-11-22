# Phân biệt null, thiếu trường, chuỗi rỗng và giá trị mặc định

Trong chương **Biểu diễn dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một quyết định nhỏ về giá trị của trường dữ liệu có thể ảnh hưởng đến tính đúng đắn của toàn bộ luồng lưu trữ. Một trường **không xuất hiện** trong yêu cầu, xuất hiện với giá trị **`null`**, chứa **chuỗi rỗng `""`**, hoặc nhận **giá trị mặc định** có thể dẫn tới bốn hành động nghiệp vụ khác nhau. Nếu ứng dụng Java gom chúng làm một, hệ thống có thể xóa nhầm thông tin, áp dụng cấu hình sai, bỏ sót validation hoặc mất dấu nguồn gốc dữ liệu khi tiến hóa lược đồ.

Bài học này nối kết biểu diễn dữ liệu ở API/JSON, kiểu dữ liệu Java, schema và truy vấn SQL, cũng như ranh giới persistence. Việc phân biệt các trạng thái giúp thiết kế giao dịch chính xác, xử lý lỗi kết nối và cập nhật đồng thời, đồng thời hỗ trợ kiểm toán, bảo mật, migration và tối ưu hiệu năng theo mục tiêu của mô-đun.

**Kết quả cần đạt:** sau bài học, người học có thể:

- Giải thích ngữ nghĩa của `null`, *thiếu trường*, `""` và *giá trị mặc định* ở từng lớp.
- Nhận ra khi nào chuyển đổi JSON → Java → SQL làm mất thông tin về trạng thái đầu vào.
- Thiết kế hợp đồng `POST`, `PUT` và `PATCH` rõ ràng, đặc biệt đối với xóa giá trị và cập nhật một phần.
- Dùng JDBC và ràng buộc database để lưu các trạng thái hợp lệ mà không gây ghi đè vô ý.
- Xử lý schema migration, truy vấn `NULL`, validation và kiểm thử các trường hợp biên.

## 1. Bốn khái niệm có ý nghĩa khác nhau

Giả sử ứng dụng quản lý hồ sơ người dùng có trường `bio` (giới thiệu bản thân) và `locale` (ngôn ngữ giao diện). Các payload sau **không tương đương**:

~~~json
{}
~~~

~~~json
{"bio": null}
~~~

~~~json
{"bio": ""}
~~~

~~~json
{"locale": "vi-VN"}
~~~

| Trạng thái | Biểu diễn minh họa | Ý nghĩa tiềm năng | Điểm cần làm rõ |
| --- | --- | --- | --- |
| **Thiếu trường (absent/missing)** | JSON không có key `bio` | Bên gửi không cung cấp trường này | Khi tạo mới có thể áp dụng default; khi PATCH thường giữ nguyên |
| **`null` tường minh** | `"bio": null` | Không có giá trị, chưa biết hoặc yêu cầu xóa giá trị | Các ý nghĩa khác nhau cần được quy định trong hợp đồng |
| **Chuỗi rỗng** | `"bio": ""` | Có một giá trị kiểu chuỗi với độ dài bằng 0 | Có thể hợp lệ, hoặc bị từ chối nếu nghiệp vụ yêu cầu nội dung |
| **Giá trị mặc định** | `"locale": "vi-VN"` hoặc do hệ thống tự gán | Giá trị được chọn theo chính sách khi thiếu đầu vào | Cần biết ai áp dụng và vào thời điểm nào |

**Giá trị mặc định không phải một kiểu dữ liệu thứ tư tương tự `null` hay `""`.** Nó là *quy tắc lựa chọn giá trị*. Sau khi áp dụng mặc định, giá trị được lưu có thể là chuỗi, số, boolean, hoặc thậm chí `NULL` nếu thiết kế cho phép. Ví dụ `"locale": "vi-VN"` có thể đến từ người dùng chủ động chọn hoặc từ chính sách mặc định; **không thể biết nguồn gốc chỉ từ chuỗi đã lưu**.

### 1.1. Ví dụ nghiệp vụ để tránh đồng nhất sai

- **Tiểu sử:** thiếu `bio` trong một bản cập nhật có thể nghĩa là “giữ nguyên”; `null` nghĩa “xóa tiểu sử”; `""` là “tiểu sử có nội dung rỗng” nếu hợp đồng chấp nhận.
- **Mã giảm giá:** thiếu `couponCode` nghĩa “không gửi mã”; `""` có thể là input không hợp lệ; `null` có thể nghĩa “bỏ mã đã chọn”. Cần quy định riêng ở từng API.
- **Số lượng:** `quantity = 0` là số không, khác với `null` hoặc thiếu trường. Không được gán mặc định 1 khi người dùng cố ý gửi 0 nếu 0 có ý nghĩa.
- **Cờ cấu hình:** `enabled = false` là một lựa chọn tường minh, khác với “chưa cung cấp”. Java primitive `boolean` mặc định `false` có thể làm mất phân biệt này khi deserialize.
- **Giá trị không biết và không áp dụng:** ngày giao hàng “chưa biết” và “không giao hàng vì lấy tại cửa hàng” có thể cần trạng thái riêng; dùng `NULL` cho cả hai sẽ khó phân tích và báo cáo.

Việc chọn ngữ nghĩa là quyết định **của miền nghiệp vụ**. Không có quy tắc chung rằng mọi `null` đều xóa, mọi chuỗi rỗng đều sai hoặc mọi trường vắng mặt đều phải nhận default.

## 2. Trạng thái thay đổi khi đi qua nhiều lớp

~~~mermaid
flowchart LR
    A["JSON request: missing / null / empty / value"] --> B["API parse + validation"]
    B --> C["Java DTO / command"]
    C --> D["Domain policy: giữ, xóa, đặt, mặc định"]
    D --> E["Repository / SQL"]
    E --> F[("Database: NULL hoặc giá trị đã lưu")]
    F --> G["Đọc / serialization"]
    G --> H["JSON response"]
~~~

**Vị trí có đủ thông tin nhất để phân biệt “thiếu” với “`null`” thường là ngay khi phân tích payload đầu vào**. Nếu deserialize cả hai thành một trường Java mang giá trị `null`, các lớp phía sau không thể biết ban đầu người gửi có cung cấp key hay không. Tương tự, sau khi database đã áp dụng default `vi-VN`, ta không thể suy ra người dùng đã chọn hay hệ thống chọn nếu không lưu thêm metadata.

| Lớp | Thiếu trường có tồn tại không? | Có gì dễ bị mất? |
| --- | --- | --- |
| JSON object | Có: không có key | Một serializer có thể bỏ key null nên làm thay đổi hợp đồng |
| Java DTO thông thường | Thường không còn phân biệt nếu dùng một field `String` | Key thiếu và JSON null cùng thành Java `null` |
| Java `Map` / JSON tree | Có thể dùng `containsKey` hoặc kiểm tra key | `map.get(key) == null` không phân biệt hai trường hợp |
| Bảng SQL quan hệ | Bản ghi có cột thuộc schema; giá trị cột có thể `NULL` | Không lưu được “key vắng mặt ở request” nếu không có metadata |
| Document store | Tùy hệ quản trị, có thể lưu field vắng mặt và field null riêng | Truy vấn, index và schema của từng sản phẩm có thể xử lý khác nhau |
| JSON response | Tùy quy tắc serialize | `null` có thể bị lược bỏ, khiến client hiểu là chưa gửi |

**Thiếu trường là thuộc tính của cấu trúc đầu vào hoặc tài liệu**, còn `NULL` là dấu hiệu giá trị SQL chưa xác định/không có theo ngữ nghĩa ba giá trị của SQL. Đừng xem hai khái niệm giống nhau chỉ vì một ORM biểu diễn cả hai bằng Java `null`.

## 3. Hợp đồng tạo mới, thay thế và cập nhật một phần

Ý nghĩa của một payload phụ thuộc **loại thao tác**. Giả sử đã có hồ sơ:

~~~json
{"bio": "Lập trình Java", "locale": "en-US"}
~~~

### 3.1. POST: tạo bản ghi mới

Khi tạo mới:

- Thiếu `locale`: hệ thống có thể áp dụng mặc định `vi-VN` theo chính sách đã công bố.
- `"locale": null`: nếu trường bắt buộc không null thì trả lỗi validation; không tự động coi như thiếu nếu hợp đồng không nói vậy.
- `"locale": ""`: là chuỗi rỗng, thường không hợp lệ với mã ngôn ngữ.
- `"locale": "en-US"`: chọn giá trị do client gửi nếu hợp lệ.

Với `bio` không bắt buộc, có thể cho phép cả thiếu và `null` khi tạo mới, nhưng cả hai có thể cùng trở thành SQL `NULL`. Nếu cần theo dõi sự khác biệt ban đầu, phải lưu một thuộc tính bổ sung như `bio_provided`, sự kiện yêu cầu hoặc nhật ký nguồn gốc.

### 3.2. PUT: thay thế biểu diễn tài nguyên

`PUT` thường được dùng cho thao tác thay thế toàn bộ biểu diễn tài nguyên tại URI, nhưng hành vi cụ thể đối với thuộc tính thiếu phải được quy định bởi **hợp đồng API**. Một API có thể yêu cầu mọi trường bắt buộc đều hiện diện; trường không bắt buộc bị bỏ qua có thể nhận default hoặc bị xóa khi thay thế. **Không mặc nhiên lấy quy tắc của PATCH áp cho PUT.**

Ví dụ, nếu API quy định PUT cần `locale` và `bio`, việc thiếu `bio` phải được xử lý theo hợp đồng thay thế đó, thay vì lặng lẽ giữ giá trị cũ như một PATCH.

### 3.3. PATCH: sửa một phần

Với một **hợp đồng PATCH do ứng dụng định nghĩa** cho `bio`, có thể quy định:

| Payload PATCH | Kết quả `bio` từ giá trị cũ `"Lập trình Java"` |
| --- | --- |
| `{}` | Giữ `"Lập trình Java"`; không tăng version nếu không có trường nào đổi |
| `{"bio": null}` | Xóa giá trị, lưu SQL `NULL` |
| `{"bio": ""}` | Lưu chuỗi rỗng nếu nghiệp vụ cho phép |
| `{"bio": "Học persistence"}` | Lưu giá trị mới |
| `{"bio": 123}` | Trả lỗi kiểu dữ liệu, không ghi |

Ở chuẩn **JSON Merge Patch (RFC 7396)**, key vắng mặt thường giữ nguyên, còn key có `null` nghĩa là loại bỏ thành viên khỏi tài liệu JSON đích. Nếu trường được ánh xạ xuống SQL, API có thể diễn giải hành động loại bỏ đó thành `NULL` hoặc một trạng thái khác theo domain. **Không nên dùng Merge Patch nếu cần thể hiện một giá trị `null` thực sự là dữ liệu cần lưu mà không xóa field.** Trong trường hợp ấy, có thể dùng **JSON Patch (RFC 6902)** với các thao tác phân biệt `remove` và `replace` (giá trị `null`), hoặc một hợp đồng command riêng.

Ví dụ JSON Patch:

~~~json
[
  {"op": "replace", "path": "/bio", "value": null}
]
~~~

Khác với:

~~~json
[
  {"op": "remove", "path": "/bio"}
]
~~~

Ý nghĩa khi chuyển sang cột quan hệ vẫn cần do ứng dụng xác định. Cần khai báo đúng kiểu nội dung (media type) và tránh trộn lẫn các ngữ nghĩa PATCH trong cùng endpoint.

## 4. Phân biệt thiếu key và JSON null trong Java

Giả sử dùng Jackson JSON Tree. Phương thức `get("bio")` trả **Java `null`** nếu key không tồn tại, nhưng trả một `NullNode` nếu JSON có `"bio": null`. Đây là lúc có thể giữ đúng ý định.

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public final class BioInputParser {
    public enum Action { UNCHANGED, CLEAR, SET }

    public record BioChange(Action action, String value) {}

    public static BioChange parse(JsonNode request) {
        if (request == null || !request.isObject()) {
            throw new IllegalArgumentException("JSON object required");
        }

        JsonNode field = request.get("bio");
        if (field == null) {
            return new BioChange(Action.UNCHANGED, null);
        }
        if (field.isNull()) {
            return new BioChange(Action.CLEAR, null);
        }
        if (!field.isTextual()) {
            throw new IllegalArgumentException("bio must be text or null");
        }
        return new BioChange(Action.SET, field.textValue());
    }
}
~~~

Với cách này:

- `{}` → `UNCHANGED`.
- `{"bio": null}` → `CLEAR`.
- `{"bio": ""}` → `SET` với giá trị `""`; `textValue()` không biến nó thành null.
- `{"bio": "abc"}` → `SET` với `"abc"`.

Quy tắc business có thể kiểm tra độ dài, danh sách ký tự hoặc cho phép `""` ở bước sau. Tránh viết `request.path("bio").asText()` rồi coi kết quả là đầy đủ thông tin: `path()` có thể trả `MissingNode`, còn `asText()` làm mất thông tin về kiểu gốc và sự hiện diện khi xử lý thiếu/null một cách không cẩn thận.

### 4.1. Vì sao DTO một trường có thể không đủ?

~~~java
record UpdateProfileRequest(String bio) {}
~~~

Khi deserialize thông thường, `{}` và `{"bio": null}` đều có thể cho `bio() == null`. Sau bước ấy, đoạn code `if (request.bio() != null) update(...)` sẽ **không thể xóa giá trị bằng null tường minh**. Ngược lại, đoạn code `update(request.bio())` sẽ **xóa nhầm khi key vắng mặt**.

Nếu API cần phân biệt, hãy dùng JSON tree, một kiểu *field presence* riêng (ví dụ `Missing`, `ExplicitNull`, `Value<T>`), hoặc cơ chế binding đã được kiểm chứng có lưu trạng thái field. `Optional<T>` có ích để biểu thị có/không có giá trị ở một số API nội bộ, nhưng bản thân nó **không tự phân biệt đủ ba trạng thái: thiếu, null tường minh và giá trị** khi được dùng như một field DTO.

### 4.2. Primitive và wrapper khi JSON đầu vào là số/boolean

Java `int` có giá trị mặc định `0`, `boolean` có `false`; chúng không chứa `null`. Nếu DTO dùng primitive, đầu vào thiếu hoặc `null` có thể bị ánh xạ thành giá trị mặc định hoặc bị từ chối tùy cấu hình thư viện, làm lẫn với người dùng cố ý gửi `0`/`false`.

Với các trường cần phân biệt “không cung cấp”, ưu tiên biểu diễn giữ được presence, ví dụ `JsonNode`, wrapper kết hợp cờ hiện diện, hoặc một loại command riêng. Cấu hình deserializer phải quy định rõ hành vi khi gặp `null` cho primitive và số không hợp lệ.

## 5. SQL: NULL khác chuỗi rỗng, DEFAULT khác NULL

Trong hệ quản trị quan hệ, giá trị **SQL `NULL` không phải chuỗi `'NULL'`, không phải `''` và không phải số 0**. Khi dùng PostgreSQL, có thể minh họa:

~~~sql
CREATE TABLE profile_settings (
    profile_id UUID PRIMARY KEY,
    bio TEXT NULL,
    locale TEXT NOT NULL DEFAULT 'vi-VN',
    version BIGINT NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT locale_not_blank CHECK (length(trim(locale)) > 0)
);
~~~

Giả sử các ID hợp lệ và chưa tồn tại:

~~~sql
-- Bỏ qua bio và locale: bio thành NULL; locale nhận default.
INSERT INTO profile_settings(profile_id) VALUES (:id_a);

-- Gửi NULL tường minh cho bio, locale được áp default.
INSERT INTO profile_settings(profile_id, bio)
VALUES (:id_b, NULL);

-- Lưu chuỗi rỗng cho bio: bio IS NOT NULL.
INSERT INTO profile_settings(profile_id, bio)
VALUES (:id_c, '');

-- Chỉ định dùng default của locale một cách tường minh.
INSERT INTO profile_settings(profile_id, locale)
VALUES (:id_d, DEFAULT);

-- Lỗi NOT NULL: gửi NULL tường minh cho locale không kích hoạt default.
INSERT INTO profile_settings(profile_id, locale)
VALUES (:id_e, NULL);
~~~

Các `:id_*` là ký hiệu tham số minh họa, không phải cú pháp JDBC trực tiếp; với JDBC dùng `?` và bind giá trị. Trong PostgreSQL, **default của cột được áp dụng khi cột không được đưa vào INSERT hoặc khi dùng `DEFAULT`**, còn gửi SQL `NULL` tường minh không có nghĩa “lấy default”. Khi `bio` không có default riêng, giá trị được điền là SQL `NULL` nếu cột cho phép.

**Lưu ý tính di động:** một số DBMS, đáng chú ý Oracle Database ở nhiều phiên bản, xử lý chuỗi ký tự rỗng như `NULL` với kiểu chuỗi thông thường. Vì vậy **không áp dụng máy móc kết luận PostgreSQL `'' != NULL` cho mọi hệ quản trị**; cần kiểm chứng ngữ nghĩa của database đang dùng.

### 5.1. SQL có logic ba giá trị

So sánh với `NULL` bằng `=` hoặc `<>` không trả `TRUE`/ `FALSE` như so sánh chuỗi bình thường mà thường trả **UNKNOWN**:

~~~sql
-- Sai khi muốn chọn các hàng có bio là SQL NULL:
SELECT profile_id FROM profile_settings WHERE bio = NULL;

-- Đúng:
SELECT profile_id FROM profile_settings WHERE bio IS NULL;

-- Chọn chuỗi rỗng (trên PostgreSQL):
SELECT profile_id FROM profile_settings WHERE bio = '';

-- Chọn có bio và không rỗng:
SELECT profile_id
FROM profile_settings
WHERE bio IS NOT NULL AND bio <> '';
~~~

Trong điều kiện `WHERE`, chỉ hàng có predicate đánh giá thành `TRUE` mới được chọn; `FALSE` và `UNKNOWN` đều không được chọn. Cũng cần phân biệt:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `COUNT(*)` | Đếm mọi hàng thỏa `WHERE` |
| `COUNT(bio)` | Đếm hàng có `bio IS NOT NULL`; chuỗi rỗng được tính là có giá trị theo PostgreSQL |
| `COALESCE(bio, '')` | Thay null thành chuỗi rỗng **trong kết quả biểu thức**, làm mất phân biệt ở tầng truy vấn đó |
| `NULLIF(bio, '')` | Chuyển chuỗi rỗng thành NULL trong kết quả biểu thức; chỉ dùng khi yêu cầu nghiệp vụ chủ động gộp |

Không nên dùng `COALESCE` hoặc `NULLIF` chỉ để “đỡ xử lý null” nếu báo cáo cần phân biệt *không có dữ liệu* và *đã cung cấp chuỗi rỗng*. Tùy kiểu truy vấn và DBMS, bọc cột trong hàm cũng có thể ảnh hưởng khả năng dùng index; hãy kiểm tra execution plan.

## 6. Ghi PATCH xuống JDBC mà không làm mất trạng thái

Sau khi phân tích JSON thành `BioChange`, tầng persistence có thể xử lý ba hành động riêng biệt. Ví dụ dưới dùng `profile_settings` trong PostgreSQL, có kiểm soát phiên bản để chống cập nhật đè lên dữ liệu mới. Nó chỉ cập nhật `bio`; những trường khác phải có command và validation riêng.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.UUID;
import javax.sql.DataSource;

public final class ProfileWriter {
    public enum Outcome { UNCHANGED, UPDATED, NOT_FOUND_OR_CONFLICT }

    private final DataSource dataSource;

    public ProfileWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Outcome patchBio(
            UUID profileId,
            long expectedVersion,
            BioInputParser.BioChange change) throws SQLException {

        if (change.action() == BioInputParser.Action.UNCHANGED) {
            return Outcome.UNCHANGED;
        }

        String sql = """
                UPDATE profile_settings
                SET bio = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = ? AND version = ?
                """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int updated;
                try (PreparedStatement statement = connection.prepareStatement(sql)) {
                    if (change.action() == BioInputParser.Action.CLEAR) {
                        statement.setNull(1, Types.VARCHAR);
                    } else {
                        statement.setString(1, change.value()); // "" vẫn là chuỗi rỗng
                    }
                    statement.setObject(2, profileId);
                    statement.setLong(3, expectedVersion);
                    updated = statement.executeUpdate();
                }

                if (updated != 1) {
                    connection.rollback();
                    return Outcome.NOT_FOUND_OR_CONFLICT;
                }
                connection.commit();
                return Outcome.UPDATED;
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

**Điều đoạn mã bảo đảm:** key thiếu không dẫn đến câu lệnh UPDATE; null tường minh đặt cột `bio` thành SQL `NULL`; chuỗi rỗng được bind nguyên dạng; cập nhật chỉ xảy ra khi phiên bản khớp. Giao dịch rollback nếu câu lệnh lỗi; việc tăng `version` và đổi `updated_at` là một phần của cùng UPDATE.

**Điều chưa được minh họa đầy đủ:** xác thực và phân quyền, giới hạn độ dài, xác nhận `bio` có thật sự thay đổi hay không, audit/outbox và xử lý retry. Nếu giá trị mới giống giá trị cũ, ví dụ trên vẫn tăng version; sản phẩm cần quy ước rõ có coi đó là một thay đổi nghiệp vụ hay không. `NOT_FOUND_OR_CONFLICT` cần được tầng ứng dụng phân biệt nếu API muốn trả 404 hoặc 409. Lỗi kết nối ngay lúc `COMMIT` có thể khiến client không biết lệnh đã thành công hay chưa; với thao tác cần idempotency, hãy dùng request ID và đọc lại trạng thái đáng tin cậy thay vì gửi lại mù quáng.

### 6.1. ORM và SQL default không luôn phối hợp như mong đợi

Ví dụ, một entity có `locale == null` khi tạo mới **không bảo đảm** ORM sẽ bỏ cột `locale` khỏi `INSERT`; nhiều ORM đưa cột đó vào SQL với giá trị `NULL`. Khi đó ràng buộc `NOT NULL` có thể báo lỗi dù database khai báo `DEFAULT 'vi-VN'`.

Nếu muốn gán mặc định ở tầng ứng dụng, hãy làm trong chính sách tạo mới với giá trị đã xác thực. Nếu muốn dùng default của database, cần xác minh SQL mà ORM phát ra và cơ chế lấy lại giá trị được database sinh. Không để default của controller, ORM và DB xung đột âm thầm; chọn một điểm sở hữu quy tắc và diễn giải rõ với các điểm còn lại.

## 7. Validation: thiếu, null, rỗng và trắng không cùng một lỗi

Một trường `displayName` bắt buộc có thể có những quy tắc khác `bio` tự chọn:

| Input cho `displayName` khi tạo mới | Cách xử lý minh họa | Lý do |
| --- | --- | --- |
| Thiếu key | Trả lỗi thiếu trường | Không có thông tin bắt buộc |
| `null` | Trả lỗi không được null | Trường bắt buộc có giá trị |
| `""` | Trả lỗi rỗng | Chuỗi không có ký tự |
| `"   "` | Trả lỗi toàn khoảng trắng | Có độ dài nhưng không có nội dung có nghĩa |
| `" An "` | Có thể chuẩn hóa thành `"An"` theo hợp đồng | Chính sách trim phải nhất quán |
| `"An"` | Chấp nhận | Đáp ứng yêu cầu |

Tránh dùng quy tắc `if (value == null || value.isBlank())` cho mọi trường. Nó có thể phù hợp với tên hiển thị bắt buộc nhưng sai với `bio` nếu chuỗi rỗng được phép, hoặc sai với mã xác thực nơi khoảng trắng là ký tự có ý nghĩa. Java `String.isBlank()` kiểm tra chuỗi rỗng/toàn ký tự whitespace theo quy tắc của Java; nó không thay thế đầy đủ chuẩn hóa Unicode và validation nghiệp vụ.

Với số và boolean, **`0` và `false` là các giá trị hợp lệ về mặt kiểu**. Validation phải kiểm tra ranh giới nghiệp vụ (`quantity > 0`, hay `discountRate >= 0`), không coi các giá trị “falsy” là thiếu. Khi biểu diễn trong JSON, chuỗi `"0"` và số `0` cũng là hai kiểu khác nhau; việc tự động ép kiểu cần được quản lý.

## 8. Giá trị mặc định: ai quyết định và vào lúc nào?

Mặc định có thể xuất hiện ở nhiều nơi:

| Vị trí áp dụng | Ví dụ | Rủi ro nếu dùng thiếu kiểm soát |
| --- | --- | --- |
| Giao diện | Form chọn `vi-VN` trước khi người dùng thao tác | Backend tưởng người dùng đã chủ động chọn |
| API / application service | Khi tạo hồ sơ thiếu `locale`, gán `vi-VN` | Các đường ghi qua batch/import có thể dùng quy tắc khác |
| ORM / mapping | Khởi tạo giá trị trong constructor/entity | Khi object được map từ request có thể ghi đè ý định null |
| Database | `locale TEXT DEFAULT 'vi-VN'` | Default chỉ áp dụng trong những trường hợp DB định nghĩa; UPDATE/NULL tường minh khác |
| Đọc / hiển thị | `COALESCE(locale, 'vi-VN')` | Chỉ che dữ liệu thiếu ở phía đọc, không sửa nguồn |

Để nhất quán, hãy định nghĩa **ai có thẩm quyền chọn default**, dùng cùng chính sách cho API, công việc nhập dữ liệu và migration. Nếu default có thể đổi theo thời gian (ví dụ ngôn ngữ mặc định thay từ `vi-VN` sang `en-US`), cần quyết định **lưu giá trị đã chốt** hay **tính theo chính sách hiện hành mỗi lần đọc**:

- **Default được chốt khi tạo:** lưu `locale = 'vi-VN'`; các bản ghi cũ giữ nguyên sau khi chính sách đổi.
- **Default được tính khi đọc:** lưu trạng thái “chưa chọn” và khi hiển thị lấy chính sách hiện tại; người dùng có thể thấy giá trị đổi khi chính sách đổi.
- **Default có nguồn gốc:** nếu cần phân biệt lựa chọn của người dùng và mặc định, lưu thêm `locale_origin` (ví dụ `USER`, `DEFAULT_POLICY`) hoặc một biểu diễn tương đương.

Không có cách nào suy ra chính xác nguồn của `'vi-VN'` từ chính giá trị `'vi-VN'` mà không có dữ liệu bổ sung.

## 9. Tiến hóa schema và dữ liệu lịch sử

Giả sử hệ thống trước đây không lưu `locale`. Sau khi thêm trường với mặc định `vi-VN`, cần tránh kết luận mọi khách hàng cũ **đã chọn** tiếng Việt. Đó là giá trị được gán theo quy tắc mới, không phải dữ kiện lịch sử đã được xác thực.

Quy trình migration nên được thiết kế theo từng giai đoạn:

1. **Mở rộng schema:** thêm cột theo cách tương thích với mã ứng dụng cũ; ban đầu có thể cho phép `NULL`.
2. **Định nghĩa semantics:** phân biệt trường chưa từng được cung cấp, giá trị hiện không biết và người dùng chủ động chọn giá trị. Nếu cần, bổ sung trường nguồn gốc.
3. **Cập nhật đường ghi:** yêu cầu mới và dữ liệu import gán giá trị theo cùng một quy tắc; không để mỗi service tự đặt một default khác nhau.
4. **Backfill có bằng chứng:** nếu có dấu vết lựa chọn thực tế, điền theo nguồn; nếu không có, dùng trạng thái unknown hoặc default đã công bố mà không gán nhầm “user-selected”.
5. **Ràng buộc và triển khai:** chỉ siết `NOT NULL` sau khi dữ liệu và các phiên bản ứng dụng đã tương thích. Thử rolling deployment và rollback.
6. **Đối soát:** đo số hàng `NULL`, số hàng rỗng, số được gán default, số bị validation từ chối; theo dõi ảnh hưởng đến báo cáo và chỉ mục.

Trong một số DBMS, thêm cột `NOT NULL DEFAULT ...` có thể điền hoặc biểu diễn giá trị mặc định cho dữ liệu cũ mà không qua từng lệnh UPDATE theo cách thông thường. Điều đó có thể hợp lệ về kỹ thuật nhưng vẫn không chứng minh người dùng cũ đã cung cấp giá trị; **migration của schema không tự giải quyết provenance của dữ liệu**.

### 9.1. Nếu chuyển từ `""` sang `NULL`

Đội phát triển có thể muốn chuẩn hóa cột `bio`: trước đây chuỗi rỗng biểu thị “không có tiểu sử”, giờ muốn dùng SQL `NULL`.

~~~sql
-- Ví dụ PostgreSQL; chỉ chạy sau khi xác nhận nghiệp vụ cho phép gộp hai trạng thái.
UPDATE profile_settings
SET bio = NULL
WHERE bio = '';
~~~

Câu lệnh **làm mất phân biệt** giữa chuỗi rỗng và null trong dữ liệu đã lưu. Trước khi chạy, phải xác định ứng dụng, dashboard, xuất dữ liệu và API có phụ thuộc vào sự phân biệt ấy hay không; sao lưu, thử trên dữ liệu đại diện và có kế hoạch rollback. Đó là migration ngữ nghĩa, không chỉ chỉnh kiểu cột.

## 10. Truy vấn, chỉ mục và chi phí của cách biểu diễn

Việc có nhiều trạng thái ảnh hưởng đến điều kiện truy vấn và thống kê:

- **Báo cáo:** `COUNT(bio)` không đếm SQL `NULL` nhưng có thể đếm chuỗi rỗng, gây hiểu lầm “bao nhiêu hồ sơ đã có tiểu sử”.
- **Bộ lọc:** `WHERE bio IS NULL` khác `WHERE bio = ''`. Nếu cả hai mang nghĩa “chưa có tiểu sử” thì hãy định nghĩa quy tắc hợp nhất trong truy vấn hoặc làm sạch nguồn một cách có chủ đích.
- **Chỉ mục:** tùy DBMS, index có cách xử lý `NULL` và điều kiện độc nhất khác nhau. PostgreSQL hỗ trợ partial index như `WHERE bio IS NOT NULL`; không nên giả định mọi hệ quản trị có cùng semantics.
- **Tính chọn lọc:** nếu 99% hàng có giá trị `NULL`, một truy vấn tìm số ít hàng có dữ liệu có thể hưởng lợi từ chỉ mục phù hợp, nhưng hiệu quả phải được kiểm tra bằng query plan và số liệu thật.
- **Phân tích đầu vào:** lưu được trạng thái thiếu/null/rỗng có thể làm tăng số loại giá trị nhưng giúp giải thích chất lượng dữ liệu; nếu gộp vô điều kiện, thông tin sẽ mất.

Ví dụ truy vấn tình trạng hồ sơ trên PostgreSQL:

~~~sql
SELECT
    COUNT(*) AS total_profiles,
    COUNT(*) FILTER (WHERE bio IS NULL) AS no_bio,
    COUNT(*) FILTER (WHERE bio = '') AS empty_bio,
    COUNT(*) FILTER (WHERE bio IS NOT NULL AND bio <> '') AS nonempty_bio
FROM profile_settings;
~~~

Nếu hợp đồng quy định chỉ chuỗi không rỗng và không toàn khoảng trắng mới là “đã điền”, cần bổ sung điều kiện phù hợp. Nhưng thay đổi định nghĩa chỉ số phải được thảo luận với chủ sở hữu nghiệp vụ, không âm thầm đổi một câu SQL trong dashboard.

## 11. Bảo mật, audit và khôi phục

Phân biệt trạng thái đầu vào cũng liên quan đến an toàn dữ liệu:

- **Chỉ cho phép sửa trường đã được cấp quyền:** client gửi `{"isAdmin": null}` hay bỏ trường đó không được tự động vượt qua kiểm soát quyền. Dùng allowlist field và xác thực ở application service.
- **Không ghi payload nhạy cảm bừa bãi:** token, mật khẩu, dữ liệu cá nhân có thể xuất hiện trong JSON; nếu cần audit, ghi loại thao tác, actor, thời gian, request ID và sự khác biệt đã được che/mã hóa theo chính sách.
- **Ghi đúng ý định:** log nên phân biệt “không sửa”, “xóa giá trị” và “đặt giá trị rỗng” khi nghiệp vụ cần truy vết. Chỉ lưu giá trị cuối có thể không đủ để giải thích thay đổi.
- **Đồng thời:** với PATCH nhiều trường, hãy dùng version hoặc cơ chế khóa thích hợp để không ghi đè thao tác của người dùng khác. Việc thiếu key không được làm thay đổi cột đó.
- **Sao lưu/khôi phục:** nếu đã ghi đè dữ liệu bằng default sai hoặc biến hàng loạt `""` thành `NULL`, khôi phục có thể cần backup/PITR và nhật ký audit. Replica có thể đã nhận và đồng bộ sai lầm tương tự.
- **Xử lý lỗi kết nối:** nếu client không biết PATCH đã commit hay chưa, hãy đối soát bằng request ID/phiên bản, áp dụng idempotency khi cần, rồi mới thử lại.

**Ghi nhớ về audit:** “payload không có key” và “yêu cầu đặt key thành null” là hai hành động khác nhau. Nếu hệ thống bắt buộc điều tra ai đã xóa trường, log phải giữ được sự phân biệt này ngay khi nhận command, trước khi nó bị rút gọn vào một cột SQL nullable.

## 12. Bài tập tình huống: cập nhật hồ sơ và thay đổi default

Ứng dụng Java có dữ liệu hiện tại:

~~~json
{"bio": "Thích đọc sách", "locale": "en-US", "marketingOptIn": false}
~~~

Tổ chức yêu cầu:

1. Endpoint PATCH phải cho phép giữ nguyên, xóa và đặt `bio` thành chuỗi rỗng.
2. Người dùng có thể chọn `marketingOptIn = false` và hệ thống không được hiểu là “chưa chọn”.
3. Từ tháng tới, giá trị mặc định của `locale` khi tạo hồ sơ mới sẽ chuyển từ `vi-VN` sang `en-US`.
4. Cần thống kê số người **chủ động chọn** ngôn ngữ, tách khỏi số người được gán mặc định.

**Câu hỏi:**

- Với các PATCH `{}`, `{"bio": null}`, `{"bio": ""}` và `{"bio": "A"}`, trạng thái `bio` cuối cùng nên là gì?
- Nếu JSON `{"marketingOptIn": false}` được gán vào primitive `boolean`, thông tin nào có thể mất khi đem so với `{}`?
- Có thể dùng duy nhất cột `locale` để biết liệu người dùng chủ động chọn `en-US` hay ứng dụng chọn default không?
- Sau khi chính sách default đổi, có nên tự động cập nhật tất cả hồ sơ đang lưu `vi-VN` thành `en-US` không?
- Chọn ít nhất sáu ca kiểm thử bảo đảm xử lý đúng yêu cầu và cập nhật đồng thời.

**Hướng giải:**

| PATCH `bio` | Kết quả từ `"Thích đọc sách"` | SQL tương ứng |
| --- | --- | --- |
| `{}` | Giữ `"Thích đọc sách"` | Không ghi cột `bio` |
| `{"bio": null}` | SQL `NULL` | `SET bio = NULL` |
| `{"bio": ""}` | `""` | `SET bio = ''` |
| `{"bio": "A"}` | `"A"` | `SET bio = 'A'` |

Đối với `marketingOptIn`, cần biểu diễn presence để không gộp vắng mặt với `false`. Đối với `locale`, muốn biết nguồn lựa chọn phải lưu `locale_origin` hoặc sự kiện tương đương. Không tự động sửa giá trị cũ nếu ngữ nghĩa đã chốt của hồ sơ là “giữ lựa chọn hiện tại”; chính sách default mới có thể chỉ áp dụng khi tạo hồ sơ sau thời điểm thay đổi. Các bài test cần gồm **thiếu/null/rỗng/giá trị hợp lệ/kiểu không hợp lệ**, cập nhật cạnh tranh bằng version, xử lý khi mất kết nối lúc commit và kiểm tra truy vấn thống kê.

## 13. Checklist khi thiết kế trường dữ liệu

- [ ] Đã định nghĩa **thiếu**, **null**, **rỗng**, **mặc định** và giá trị thông thường cho trường này.
- [ ] Có hợp đồng rõ ràng cho POST, PUT và PATCH; quy định trường bị bỏ qua có được giữ nguyên không.
- [ ] Input parser/DTO còn giữ presence khi nghiệp vụ cần phân biệt missing với null.
- [ ] Validation kiểm tra kiểu và nghĩa nghiệp vụ; không gộp `0` hoặc `false` với thiếu.
- [ ] Java và SQL có quy tắc null/default nhất quán, được xác minh với ORM/driver và DBMS đang dùng.
- [ ] Giao dịch và cơ chế đồng thời bảo vệ việc cập nhật một phần; không vô ý ghi đè trường khác.
- [ ] Có quy ước lưu nguồn default khi cần biết user-selected hay system-assigned.
- [ ] Truy vấn, `COUNT`, `COALESCE`, index và báo cáo giữ đúng ngữ nghĩa các trạng thái.
- [ ] Migration/backfill không tự suy đoán dữ liệu lịch sử và có kiểm thử rollback/restore.
- [ ] Audit, phân quyền, retry và backup bảo vệ dữ liệu khỏi thay đổi sai hoặc mất thông tin.

**Ghi nhớ:** **Thiếu trường** mô tả dữ liệu chưa được cung cấp trong cấu trúc; **`null`** thể hiện một giá trị chưa xác định/không có theo hợp đồng; **`""`** là một chuỗi hợp lệ về kiểu nhưng có độ dài bằng 0; **mặc định** là quy tắc chọn giá trị khi điều kiện đã định thỏa mãn. Với persistence trong Java, điều quan trọng là giữ được phân biệt đó tới khi nghiệp vụ quyết định **giữ nguyên, xóa, đặt giá trị hay áp dụng mặc định**, rồi ghi một cách nhất quán và có thể kiểm chứng.
