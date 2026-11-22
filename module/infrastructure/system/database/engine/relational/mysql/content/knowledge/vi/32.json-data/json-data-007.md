# JSON_SET, JSON_INSERT, JSON_REPLACE và JSON_REMOVE

MySQL lưu trữ JSON dưới dạng tài liệu có cấu trúc thay vì chỉ là một chuỗi văn bản. Khi ứng dụng cần thay đổi một vài thuộc tính trong tài liệu, không nhất thiết phải tải toàn bộ JSON về ứng dụng, sửa chuỗi rồi ghi đè cả cột. Các hàm sửa JSON cho phép thực hiện thay đổi ngay trong biểu thức SQL:

- `JSON_SET()` thêm thuộc tính hoặc phần tử nếu đường dẫn chưa tồn tại, đồng thời thay thế giá trị nếu đường dẫn đã tồn tại.
- `JSON_INSERT()` chỉ thêm tại đường dẫn chưa tồn tại; nếu đường dẫn đã có giá trị thì giữ nguyên.
- `JSON_REPLACE()` chỉ thay thế giá trị tại đường dẫn đã tồn tại; nếu đường dẫn chưa có thì bỏ qua.
- `JSON_REMOVE()` xóa giá trị tại một hoặc nhiều đường dẫn.

Chọn sai hàm có thể khiến ứng dụng vô tình ghi đè cấu hình cũ, không tạo được thuộc tính mới hoặc xóa nhầm phần tử mảng. Bài học này giải thích ngữ nghĩa của từng hàm, cách MySQL đánh giá JSON path, thứ tự khi truyền nhiều cặp path-value, cách xử lý object và array, rồi áp dụng vào các câu UPDATE an toàn.

Các ví dụ hướng tới MySQL 8.4. Một số cú pháp row alias và khả năng tối ưu lưu trữ JSON có mốc phiên bản riêng; các điểm đó được ghi chú tại nơi sử dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt chính xác hành vi của JSON_SET, JSON_INSERT, JSON_REPLACE và JSON_REMOVE.
- Đọc JSON path cho object member, nested object và array index.
- Thay đổi nhiều vị trí trong cùng một tài liệu theo thứ tự xác định.
- Hiểu vì sao hàm sửa JSON không tự tạo mọi object cha còn thiếu.
- Phân biệt SQL NULL với JSON null.
- Tránh lưu một object JSON thành chuỗi JSON có dấu ngoặc kép.
- Thêm, cập nhật và xóa phần tử trong array mà không nhầm index.
- Dùng JSON_EXTRACT, JSON_TYPE và JSON_CONTAINS_PATH để kiểm tra trước khi sửa.
- Cập nhật JSON trực tiếp trong UPDATE và transaction.
- Giảm nguy cơ ghi đè thay đổi của request đồng thời.
- Hiểu điều kiện để MySQL tối ưu partial update cho cột JSON.
- Thiết kế index cho các thuộc tính JSON thường được truy vấn.
- Viết kiểm thử bao phủ đường dẫn tồn tại, không tồn tại và dữ liệu sai kiểu.

## 1. Mô hình tài liệu JSON trong MySQL

JSON là kiểu dữ liệu có kiểm tra cấu trúc. Khi insert hoặc update một cột JSON, MySQL xác thực nội dung đầu vào và từ chối tài liệu JSON không hợp lệ. MySQL lưu tài liệu theo định dạng nội bộ tối ưu cho việc truy cập thành phần; không nên coi cột JSON như một VARCHAR thông thường.

Ví dụ tài liệu hồ sơ:

    {
      "name": "An",
      "email": "an@example.test",
      "preferences": {
        "language": "en",
        "theme": "light"
      },
      "tags": ["mysql", "sql"],
      "temporary_token": "tmp-123"
    }

Tài liệu có thể gồm:

- Object: tập hợp các cặp key-value.
- Array: danh sách phần tử có thứ tự.
- String, number và boolean.
- JSON null.
- Các object hoặc array lồng nhau.

Một cột JSON không áp đặt schema nghiệp vụ cố định như các cột quan hệ. Vì vậy, ứng dụng cần thống nhất tên key, kiểu dữ liệu, ý nghĩa của trường vắng mặt và cách xử lý giá trị null.

Tạo bảng thực hành:

    CREATE TABLE customer_profile (
        customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        profile JSON NOT NULL,
        version_no BIGINT UNSIGNED NOT NULL DEFAULT 0,
        updated_at TIMESTAMP NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE = InnoDB;

Thêm một hồ sơ:

    INSERT INTO customer_profile (
        customer_id,
        profile
    )
    VALUES (
        1,
        JSON_OBJECT(
            'name', 'An',
            'email', 'an@example.test',
            'preferences',
                JSON_OBJECT(
                    'language', 'en',
                    'theme', 'light'
                ),
            'metadata', JSON_OBJECT(),
            'tags', JSON_ARRAY('mysql', 'sql'),
            'temporary_token', 'tmp-123'
        )
    );

JSON_OBJECT và JSON_ARRAY tạo giá trị JSON có cấu trúc. Cách này an toàn hơn việc ghép chuỗi JSON thủ công, đặc biệt khi giá trị có dấu ngoặc kép, ký tự escape hoặc dữ liệu Unicode.

## 2. JSON path: địa chỉ của giá trị cần sửa

Bốn hàm trong bài nhận một tài liệu JSON và một hoặc nhiều JSON path. Path chỉ ra vị trí cần thêm, thay thế hoặc xóa.

### 2.1. Root path

Ký hiệu `$` đại diện cho toàn bộ tài liệu.

    SELECT JSON_EXTRACT(
        '{"name":"An","active":true}',
        '$'
    );

### 2.2. Object member

Toán tử dấu chấm truy cập thuộc tính của object:

    $.name
    $.preferences
    $.preferences.language

Tên member trong JSON phân biệt chữ hoa và chữ thường. `$.Name` và `$.name` là hai đường dẫn khác nhau.

Nếu key có dấu chấm, dấu cách hoặc ký tự đặc biệt, dùng cú pháp key được trích dẫn:

    $."display.name"
    $."user settings".theme

Ví dụ:

    SELECT JSON_EXTRACT(
        '{"display.name":"An"}',
        '$."display.name"'
    );

### 2.3. Array index

Array dùng chỉ số bắt đầu từ 0:

    $[0]
    $.tags[1]
    $.orders[0].total

Với array:

    ["mysql", "sql", "database"]

Path `$[0]` trỏ tới `"mysql"`; `$[2]` trỏ tới `"database"`.

### 2.4. Wildcard không phù hợp với các hàm sửa JSON

JSON path có thể hỗ trợ wildcard trong một số hàm truy vấn, nhưng JSON_SET, JSON_INSERT, JSON_REPLACE và JSON_REMOVE cần đường dẫn cụ thể. Không dùng `*` hoặc `**` trong path của các hàm này.

Ví dụ path như `$.items[*].active` không phải cách để cập nhật đồng loạt mọi phần tử bằng JSON_SET. Hãy duyệt các hàng/phần tử bằng logic SQL phù hợp, hoặc chuẩn hóa dữ liệu thành bảng quan hệ nếu cần thao tác tập hợp thường xuyên.

### 2.5. Đường dẫn cha phải tồn tại

Các hàm sửa JSON không tự dựng toàn bộ cây object trung gian khi một parent object bị thiếu.

Nếu tài liệu là:

    {"name":"An"}

Thao tác:

    SELECT JSON_SET(
        '{"name":"An"}',
        '$.preferences.language',
        'vi'
    );

không tạo tự động object preferences rồi thêm language. Đường dẫn trung gian preferences chưa tồn tại nên không có vị trí để gắn thuộc tính con.

Hãy tạo object cha trước, hoặc dùng một biểu thức lồng nhau có kiểm tra kiểu. Không giả định một path sâu sẽ tự sinh tất cả node còn thiếu.

## 3. JSON_SET: thêm mới hoặc thay thế

JSON_SET(document, path, value[, path, value] ...) có hai hành vi:

- Nếu path xác định một giá trị đang tồn tại, thay giá trị đó.
- Nếu path chưa tồn tại nhưng vị trí có thể được tạo trong object/array cha hiện có, thêm giá trị mới.

Đây là hàm tổng quát khi nghiệp vụ chấp nhận cả insert lẫn replace.

### 3.1. Thay thế một giá trị đã có

Tài liệu ban đầu:

    {
      "name": "An",
      "preferences": {
        "language": "en",
        "theme": "light"
      }
    }

Thay language:

    SELECT JSON_SET(
        '{
          "name": "An",
          "preferences": {
            "language": "en",
            "theme": "light"
          }
        }',
        '$.preferences.language',
        'vi'
    );

Kết quả:

    {
      "name": "An",
      "preferences": {
        "language": "vi",
        "theme": "light"
      }
    }

Các key khác không bị thay đổi.

### 3.2. Thêm một member mới vào object cha đã tồn tại

    SELECT JSON_SET(
        '{"name":"An","preferences":{"language":"en"}}',
        '$.preferences.timezone',
        'Asia/Ho_Chi_Minh'
    );

Kết quả có thêm timezone trong preferences:

    {
      "name": "An",
      "preferences": {
        "language": "en",
        "timezone": "Asia/Ho_Chi_Minh"
      }
    }

Object preferences đã tồn tại nên MySQL có thể thêm member timezone.

### 3.3. Cập nhật cột JSON trong bảng

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1;

Hàm tạo ra giá trị JSON mới cho biểu thức SET; câu UPDATE ghi kết quả vào cột. Gọi JSON_SET trong SELECT chỉ trả về giá trị tính toán, không tự ghi thay đổi vào bảng.

### 3.4. Sửa nhiều path trong một lần gọi

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language', 'vi',
        '$.preferences.theme', 'dark',
        '$.last_updated_by', 'settings-page'
    )
    WHERE customer_id = 1;

Mỗi path-value là một cặp. Hàm có thể thay đổi nhiều vị trí trong cùng một biểu thức SQL, tránh phải gửi nhiều UPDATE riêng biệt.

### 3.5. Đối với array

Array index bắt đầu từ 0. Khi path chỉ tới phần tử đang tồn tại, JSON_SET thay phần tử đó:

    SELECT JSON_SET(
        '["mysql","sql","redis"]',
        '$[1]',
        'postgresql'
    );

Kết quả:

    ["mysql", "postgresql", "redis"]

Nếu muốn thêm phần tử ở cuối array, hãy dùng chỉ số đúng bằng độ dài array hiện tại. Với các thao tác append tổng quát, JSON_ARRAY_APPEND thường diễn đạt mục đích rõ ràng hơn JSON_SET.

## 4. JSON_INSERT: chỉ thêm khi path chưa tồn tại

JSON_INSERT(document, path, value[, path, value] ...) thêm giá trị tại vị trí chưa có. Nếu path đã xác định một giá trị, cặp đó bị bỏ qua; giá trị cũ không bị ghi đè.

### 4.1. Thêm member mới

    SELECT JSON_INSERT(
        '{"name":"An","email":"an@example.test"}',
        '$.status',
        'active'
    );

Kết quả:

    {
      "name": "An",
      "email": "an@example.test",
      "status": "active"
    }

### 4.2. Path đã tồn tại thì giữ nguyên

    SELECT JSON_INSERT(
        '{"name":"An","status":"pending"}',
        '$.status',
        'active'
    );

Kết quả vẫn là:

    {"name":"An","status":"pending"}

JSON_INSERT phù hợp với dữ liệu mặc định hoặc metadata chỉ được khởi tạo một lần. Nó không phù hợp nếu mục tiêu là luôn đồng bộ giá trị theo request mới.

### 4.3. Thêm nhiều member, bỏ qua member đã tồn tại

    SELECT JSON_INSERT(
        '{"name":"An","status":"pending"}',
        '$.status', 'active',
        '$.created_by', 'registration',
        '$.source', 'web'
    );

status giữ nguyên pending; created_by và source được thêm nếu chúng chưa tồn tại.

### 4.4. Thêm phần tử ở cuối array

Với array ba phần tử, index tiếp theo là 3:

    SELECT JSON_INSERT(
        '["mysql","sql","redis"]',
        '$[3]',
        'mongodb'
    );

Kết quả:

    ["mysql", "sql", "redis", "mongodb"]

Nếu path trỏ tới một array index đã tồn tại, JSON_INSERT không thay thế phần tử và cũng không dịch các phần tử hiện có sang phải. Để chèn vào giữa và dịch chuyển phần tử, hãy xem JSON_ARRAY_INSERT; đó là hàm khác.

### 4.5. Dùng cho khởi tạo có điều kiện

Ví dụ ứng dụng muốn bổ sung cờ beta nếu tài liệu chưa khai báo:

    UPDATE customer_profile
    SET profile = JSON_INSERT(
        profile,
        '$.flags.beta',
        TRUE
    )
    WHERE customer_id = 1;

Ví dụ này giả định object flags đã tồn tại. Nếu flags chưa tồn tại, path trung gian không tự được tạo. Hãy khởi tạo object cha trước hoặc dùng biểu thức lồng có kiểm tra kiểu.

## 5. JSON_REPLACE: chỉ thay thế path đang tồn tại

JSON_REPLACE(document, path, value[, path, value] ...) chỉ thay giá trị tại path hiện hữu. Nếu path không tồn tại, hàm bỏ qua cặp đó; không thêm member mới.

### 5.1. Thay thế giá trị hiện có

    SELECT JSON_REPLACE(
        '{"name":"An","status":"pending"}',
        '$.status',
        'active'
    );

Kết quả:

    {"name":"An","status":"active"}

### 5.2. Path chưa tồn tại thì không thêm

    SELECT JSON_REPLACE(
        '{"name":"An"}',
        '$.status',
        'active'
    );

Kết quả vẫn là:

    {"name":"An"}

JSON_REPLACE hữu ích khi nghiệp vụ chỉ cho phép sửa trường đã được khởi tạo. Nó tránh vô tình mở rộng schema tài liệu do typo trong tên path.

### 5.3. Thay nhiều giá trị đã tồn tại

    UPDATE customer_profile
    SET profile = JSON_REPLACE(
        profile,
        '$.preferences.language', 'vi',
        '$.preferences.theme', 'dark'
    )
    WHERE customer_id = 1;

Nếu language có nhưng theme không có, language vẫn được thay và theme bị bỏ qua. Không có lỗi chỉ vì một path không khớp.

### 5.4. Khi cần phát hiện path thiếu

JSON_REPLACE không báo lỗi nghiệp vụ khi path không tồn tại. Nếu ứng dụng cần phân biệt “đã cập nhật” với “không tìm thấy trường”, hãy kiểm tra trước:

    SELECT
        customer_id,
        JSON_CONTAINS_PATH(
            profile,
            'one',
            '$.preferences.theme'
        ) AS has_theme
    FROM customer_profile
    WHERE customer_id = 1;

Hoặc dùng điều kiện trong UPDATE:

    UPDATE customer_profile
    SET profile = JSON_REPLACE(
        profile,
        '$.preferences.theme',
        'dark'
    )
    WHERE customer_id = 1
      AND JSON_CONTAINS_PATH(
          profile,
          'one',
          '$.preferences.theme'
      );

Điều kiện này giúp câu UPDATE chỉ chọn tài liệu có path cần thay thế.

## 6. JSON_REMOVE: xóa member hoặc phần tử

JSON_REMOVE(document, path[, path] ...) trả về tài liệu không còn các giá trị tại path chỉ định.

### 6.1. Xóa một object member

    SELECT JSON_REMOVE(
        '{"name":"An","temporary_token":"tmp-123"}',
        '$.temporary_token'
    );

Kết quả:

    {"name":"An"}

### 6.2. Xóa nested member

    SELECT JSON_REMOVE(
        '{
          "name":"An",
          "preferences":{
            "language":"vi",
            "debug_mode":true
          }
        }',
        '$.preferences.debug_mode'
    );

Kết quả:

    {
      "name": "An",
      "preferences": {
        "language": "vi"
      }
    }

Object cha preferences vẫn còn; chỉ member debug_mode bị xóa.

### 6.3. Xóa phần tử array

    SELECT JSON_REMOVE(
        '["mysql","sql","redis","mongodb"]',
        '$[1]'
    );

Kết quả:

    ["mysql", "redis", "mongodb"]

Khi xóa một array element, các phần tử phía sau dịch sang trái và index thay đổi. Không có “lỗ trống” được giữ lại ở vị trí đã xóa.

### 6.4. Xóa nhiều path

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.temporary_token',
        '$.debug'
    )
    WHERE customer_id = 1;

Path không tồn tại được bỏ qua. Có thể truyền nhiều path trong cùng một lần gọi.

### 6.5. Xóa nhiều array index: thứ tự rất quan trọng

JSON_REMOVE đánh giá path từ trái sang phải trên tài liệu kết quả của bước trước. Khi xóa array element, các index phía sau dịch chuyển.

Giả sử:

    ["a","b","c","d"]

Xóa index 3 trước rồi index 1:

    SELECT JSON_REMOVE(
        '["a","b","c","d"]',
        '$[3]',
        '$[1]'
    );

Kết quả:

    ["a","c"]

Nếu xóa index 1 trước, array trở thành `["a","c","d"]`. Path `$[3]` tiếp theo không còn phần tử để xóa, nên kết quả còn `["a","c","d"]`.

Quy tắc thực hành: khi cần xóa nhiều index ban đầu trong cùng một array, xử lý index theo thứ tự giảm dần. Cách này hạn chế việc index của phần tử chưa xóa bị dịch chuyển trước khi path tiếp theo được áp dụng.

### 6.6. Không xóa root document

Path `$` đại diện toàn bộ tài liệu. JSON_REMOVE không cho phép xóa root document bằng path này. Nếu nghiệp vụ muốn xóa toàn bộ giá trị JSON, hãy dùng UPDATE có chủ đích để gán một JSON document khác, hoặc SQL NULL nếu schema cho phép và đó thực sự là ý nghĩa mong muốn.

## 7. Bảng so sánh bốn hàm

| Tình huống | JSON_SET | JSON_INSERT | JSON_REPLACE | JSON_REMOVE |
|---|---|---|---|---|
| Path đã tồn tại | Thay thế | Bỏ qua | Thay thế | Xóa |
| Path chưa tồn tại, parent hợp lệ | Thêm | Thêm | Bỏ qua | Bỏ qua |
| Dùng path-value pair | Có | Có | Có | Không |
| Nhiều path trong một lần gọi | Có | Có | Có | Có |
| Xóa object member | Không | Không | Không | Có |
| Xóa array element | Không | Không | Không | Có |
| Tự tạo toàn bộ parent object bị thiếu | Không | Không | Không | Không áp dụng |

Chọn nhanh:

- Muốn “đặt giá trị thành X dù đã có hay chưa” → JSON_SET.
- Muốn “chỉ khởi tạo nếu chưa có” → JSON_INSERT.
- Muốn “chỉ sửa trường đã được tạo” → JSON_REPLACE.
- Muốn “loại bỏ trường hoặc phần tử” → JSON_REMOVE.

## 8. Thứ tự đánh giá nhiều cặp path-value

JSON_SET, JSON_INSERT và JSON_REPLACE đánh giá các cặp path-value từ trái sang phải. Tài liệu sau mỗi cặp trở thành đầu vào cho cặp tiếp theo.

Ví dụ:

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile.preferences',
        JSON_OBJECT('theme', 'dark'),
        '$.profile.preferences.language',
        'vi'
    );

Đầu tiên preferences được tạo. Sau đó path language có parent hợp lệ nên được thêm.

Nếu đảo thứ tự:

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile.preferences.language',
        'vi',
        '$.profile.preferences',
        JSON_OBJECT('theme', 'dark')
    );

Cặp đầu không thể đi qua parent preferences chưa tồn tại nên không tạo language. Cặp thứ hai mới tạo preferences. Kết quả không có language.

Đối với JSON_REMOVE, path cũng được áp dụng lần lượt trên kết quả của lần xóa trước. Đây là lý do thứ tự path xóa array index phải được cân nhắc.

Nếu hai path chồng lấn, chẳng hạn một path thay cả object cha và path tiếp theo thay một member con, kết quả phụ thuộc thứ tự. Hãy viết thứ tự rõ ràng và kiểm thử trên tài liệu đại diện.

## 9. Kiểu dữ liệu của value: string không tự biến thành object JSON

Giá trị truyền vào hàm sửa JSON được chuyển thành giá trị JSON theo kiểu SQL. Một chuỗi chứa ký tự giống JSON vẫn là JSON string nếu không được parse/cast.

### 9.1. Lỗi thường gặp: lưu object thành string

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile',
        '{"language":"vi"}'
    );

Giá trị ở path profile là một JSON string có nội dung `{"language":"vi"}`, không phải object có member language.

### 9.2. Dùng CAST để đưa JSON text thành JSON value

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile',
        CAST('{"language":"vi"}' AS JSON)
    );

Kết quả:

    {"profile":{"language":"vi"}}

### 9.3. Dùng JSON_OBJECT và JSON_ARRAY

Thường nên tạo cấu trúc trực tiếp:

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile',
        JSON_OBJECT(
            'language', 'vi',
            'enabled', TRUE,
            'roles', JSON_ARRAY('reader', 'editor')
        )
    );

Kết quả chứa object, boolean và array đúng kiểu.

### 9.4. Phân biệt JSON null và SQL NULL

JSON null là một giá trị nằm bên trong tài liệu; SQL NULL là trạng thái thiếu giá trị của biểu thức/cột. Hai khái niệm này không giống nhau.

Để đặt JSON null rõ ràng:

    SELECT JSON_SET(
        '{"nickname":"An"}',
        '$.nickname',
        CAST('null' AS JSON)
    );

Kết quả:

    {"nickname": null}

Không dùng SQL NULL thay cho JSON null nếu mục tiêu là giữ một member có giá trị null. Các hàm JSON sửa đổi trả SQL NULL khi tài liệu hoặc path đầu vào là SQL NULL; hãy kiểm tra tham số nullable và dùng CAST('null' AS JSON) khi cần giá trị JSON null tường minh.

Kiểm tra sự khác nhau:

    SELECT
        JSON_TYPE(
            JSON_EXTRACT(
                '{"nickname":null}',
                '$.nickname'
            )
        ) AS json_value_type,
        JSON_EXTRACT(
            '{"nickname":null}',
            '$.missing'
        ) IS NULL AS missing_path_is_sql_null;

JSON_TYPE tại member nickname cho biết NULL theo kiểu JSON; path missing trả SQL NULL.

## 10. Tạo nested object khi parent chưa tồn tại

Đây là tình huống thường gặp trong dữ liệu cấu hình. Ví dụ tài liệu chỉ có:

    {"name":"An"}

Ứng dụng muốn đặt:

    $.preferences.notifications.email = true

Không thể chỉ gọi JSON_SET với path sâu vì preferences và notifications chưa tồn tại.

### 10.1. Khởi tạo parent object theo từng bước

Bước đầu tiên, tạo preferences nếu chưa có hoặc nếu giá trị hiện tại không phải object:

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences',
        CASE
            WHEN JSON_TYPE(
                JSON_EXTRACT(profile, '$.preferences')
            ) = 'OBJECT'
            THEN JSON_EXTRACT(profile, '$.preferences')
            ELSE JSON_OBJECT()
        END
    )
    WHERE customer_id = 1;

Biểu thức giữ nguyên preferences nếu nó đã là object; nếu thiếu hoặc có kiểu khác, nó thay bằng object rỗng. Đây là quyết định nghiệp vụ có thể làm mất giá trị preferences sai kiểu, vì vậy chỉ dùng khi ứng dụng chủ động chấp nhận chính sách chuẩn hóa đó.

Bước tiếp theo, tạo notifications object và đặt email:

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.notifications',
        CASE
            WHEN JSON_TYPE(
                JSON_EXTRACT(
                    profile,
                    '$.preferences.notifications'
                )
            ) = 'OBJECT'
            THEN JSON_EXTRACT(
                profile,
                '$.preferences.notifications'
            )
            ELSE JSON_OBJECT()
        END,
        '$.preferences.notifications.email',
        TRUE
    )
    WHERE customer_id = 1;

Hai cặp được đánh giá từ trái sang phải. Cặp đầu bảo đảm notifications là object; cặp sau thêm email.

### 10.2. Tránh ghi đè object cha ngoài ý muốn

Không dùng:

    JSON_SET(
        profile,
        '$.preferences',
        JSON_OBJECT('notifications', JSON_OBJECT('email', TRUE))
    )

nếu cần giữ preferences.language, preferences.theme hoặc các member khác. Biểu thức trên thay toàn bộ object preferences bằng object mới và làm mất các member không được truyền.

Hãy lấy object hiện tại, kiểm tra kiểu, rồi sửa member con; hoặc dùng các thao tác nhiều path theo thứ tự phù hợp.

## 11. Thao tác với array an toàn

Array có thứ tự, index bắt đầu từ 0. Khi thêm, thay hoặc xóa phần tử, cần phân biệt thao tác cập nhật vị trí với thao tác chèn làm dịch chuyển phần tử.

### 11.1. Thay một phần tử hiện có

    SELECT JSON_SET(
        '{"tags":["mysql","sql","redis"]}',
        '$.tags[1]',
        'database'
    );

Kết quả:

    {"tags":["mysql","database","redis"]}

### 11.2. Chỉ thêm nếu index chưa tồn tại

    SELECT JSON_INSERT(
        '{"tags":["mysql","sql"]}',
        '$.tags[2]',
        'redis'
    );

Kết quả:

    {"tags":["mysql","sql","redis"]}

Nếu path trỏ tới index đang tồn tại, JSON_INSERT bỏ qua; nó không đẩy phần tử hiện tại sang phải. Muốn chèn ở giữa array, dùng JSON_ARRAY_INSERT.

### 11.3. Xóa phần tử và index dịch chuyển

    SELECT JSON_REMOVE(
        '{"tags":["mysql","sql","redis"]}',
        '$.tags[0]'
    );

Kết quả:

    {"tags":["sql","redis"]}

Phần tử sql từ index 1 chuyển thành index 0.

### 11.4. Không giả định array luôn tồn tại

Trước khi sửa path như `$.tags[0]`, kiểm tra:

    SELECT
        JSON_TYPE(JSON_EXTRACT(profile, '$.tags')) AS tags_type,
        JSON_LENGTH(profile, '$.tags') AS tags_length
    FROM customer_profile
    WHERE customer_id = 1;

Nếu tags thiếu, là JSON null hoặc có kiểu scalar, câu lệnh sửa array có thể không đạt mục tiêu. Hãy xác định rõ chính sách: khởi tạo array, bỏ qua, hay từ chối dữ liệu sai schema.

## 12. Kết hợp hàm sửa với hàm kiểm tra JSON

Không phải lúc nào cũng nên gọi hàm sửa ngay. Trước khi cập nhật, các hàm đọc/kiểm tra giúp xác định path, kiểu và điều kiện nghiệp vụ.

### 12.1. JSON_CONTAINS_PATH

Kiểm tra một hoặc nhiều path có tồn tại:

    SELECT JSON_CONTAINS_PATH(
        profile,
        'one',
        '$.preferences.theme'
    )
    FROM customer_profile
    WHERE customer_id = 1;

`one` nghĩa là ít nhất một path tồn tại; `all` yêu cầu tất cả path tồn tại.

### 12.2. JSON_TYPE

Kiểm tra kiểu JSON:

    SELECT
        JSON_TYPE(
            JSON_EXTRACT(profile, '$.preferences')
        ) AS preferences_type
    FROM customer_profile
    WHERE customer_id = 1;

Kết quả có thể là OBJECT, ARRAY, STRING, INTEGER, DOUBLE, BOOLEAN hoặc NULL tùy giá trị.

### 12.3. JSON_EXTRACT và toán tử rút gọn

    SELECT
        JSON_EXTRACT(profile, '$.preferences.language'),
        profile->'$.preferences.language',
        profile->>'$.preferences.language'
    FROM customer_profile
    WHERE customer_id = 1;

`->` tương đương JSON_EXTRACT trong ngữ cảnh truy cập cột JSON. `->>` trả giá trị đã bỏ lớp JSON quoting cho kết quả scalar. Khi dùng giá trị trích xuất làm đầu vào cho hàm sửa JSON, giữ kiểu JSON nếu cần object/array; khi cần so sánh văn bản, dùng dạng unquote phù hợp.

### 12.4. JSON_LENGTH

Đếm số member hoặc phần tử:

    SELECT
        JSON_LENGTH(profile, '$.tags')
    FROM customer_profile
    WHERE customer_id = 1;

Kết quả hữu ích để xác định array hiện có bao nhiêu phần tử hoặc để kiểm tra cấu trúc trước khi thêm.

## 13. Mẫu UPDATE thực tế

Các hàm JSON thường được gọi bên trong UPDATE. Hãy xác định row bằng khóa quan hệ, dùng điều kiện để giới hạn phạm vi và chỉ thay đúng path cần thiết.

### 13.1. Cập nhật cài đặt người dùng

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.theme',
        'dark'
    )
    WHERE customer_id = 1;

### 13.2. Khởi tạo metadata nếu chưa có

    UPDATE customer_profile
    SET profile = JSON_INSERT(
        profile,
        '$.metadata.created_by',
        'registration-service'
    )
    WHERE customer_id = 1;

Lệnh này giả định metadata đã tồn tại. Nếu parent metadata chưa có, hãy tạo parent trước; JSON_INSERT không tự tạo toàn bộ object trung gian.

### 13.3. Chỉ sửa trường đã tồn tại

    UPDATE customer_profile
    SET profile = JSON_REPLACE(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1
      AND JSON_CONTAINS_PATH(
          profile,
          'all',
          '$.preferences',
          '$.preferences.language'
      );

Điều kiện bảo đảm path mục tiêu đã tồn tại. Nếu không có path, không có hàng nào được chọn để cập nhật.

### 13.4. Xóa token tạm

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.temporary_token'
    )
    WHERE customer_id = 1;

Nếu token đã không tồn tại, JSON_REMOVE giữ tài liệu không đổi.

### 13.5. Thay object con nhưng giữ phần còn lại

Nếu muốn thay riêng preferences.theme, hãy sửa đúng path con. Không thay cả profile bằng một JSON payload cũ do ứng dụng gửi lên, vì payload cũ có thể không chứa những thay đổi mới nhất ở các member khác.

## 14. Transaction và tính nhất quán

Hàm JSON không tạo transaction riêng. Khi được gọi trong UPDATE trên InnoDB, thay đổi JSON tuân theo transaction của statement và transaction hiện tại.

Ví dụ:

    START TRANSACTION;

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1;

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.temporary_token'
    )
    WHERE customer_id = 1;

    COMMIT;

Nếu một bước thất bại và ứng dụng quyết định hủy toàn bộ thao tác:

    ROLLBACK;

Không cần đọc JSON về ứng dụng rồi ghi đè toàn bộ tài liệu chỉ để đổi một member. Hãy để MySQL áp dụng phép sửa trên cột hiện tại trong UPDATE.

### 14.1. Tránh lost update từ payload cũ

Giả sử hai request cùng đọc một JSON document phiên bản 5. Request A đổi theme; request B đổi language. Nếu cả hai sửa bản JSON trong bộ nhớ ứng dụng rồi ghi đè toàn bộ cột, request ghi sau có thể xóa thay đổi của request trước.

Thay vào đó, gửi phép sửa theo path:

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.theme',
        'dark'
    )
    WHERE customer_id = 1;

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1;

Hai UPDATE được InnoDB tuần tự hóa theo khóa hàng. Vì mỗi biểu thức sửa trên giá trị cột hiện tại, thay đổi ở path khác có thể được giữ lại. Tuy nhiên, nếu hai request cùng sửa một path, vẫn cần quy tắc nghiệp vụ xác định request nào thắng.

### 14.2. Optimistic locking với version

Khi cần phát hiện dữ liệu đã đổi kể từ lần đọc của client:

    UPDATE customer_profile
    SET profile = JSON_SET(
            profile,
            '$.preferences.theme',
            'dark'
        ),
        version_no = version_no + 1
    WHERE customer_id = 1
      AND version_no = 7;

Ứng dụng kiểm tra số hàng được cập nhật:

- 1 hàng: version khớp, thay đổi thành công.
- 0 hàng: bản ghi không tồn tại hoặc version đã đổi; cần đọc lại và xử lý conflict.

Đây là cách tránh âm thầm ghi đè khi API sử dụng optimistic concurrency.

## 15. Partial update và chi phí lưu trữ JSON

JSON_SET, JSON_REPLACE và JSON_REMOVE có thể cho phép MySQL tối ưu partial update tại chỗ cho cột JSON trong các điều kiện phù hợp. Điều này không có nghĩa mọi biểu thức đều luôn chỉ ghi một phần byte.

Các điều kiện quan trọng gồm:

- Cột được cập nhật phải có kiểu JSON.
- UPDATE phải dùng một trong các hàm partial-update được hỗ trợ trực tiếp trên cột JSON đích.
- Giá trị đầu vào của phép sửa phải xuất phát từ chính cột JSON được cập nhật.
- Thay đổi phải đáp ứng giới hạn không gian và cấu trúc để storage engine áp dụng tối ưu tại chỗ.

Ví dụ có cơ hội cho partial update:

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.theme',
        'dark'
    )
    WHERE customer_id = 1;

Ví dụ thay toàn bộ tài liệu từ một payload:

    UPDATE customer_profile
    SET profile = CAST(
        '{"name":"An","preferences":{"theme":"dark"}}'
        AS JSON
    )
    WHERE customer_id = 1;

Ví dụ thứ hai là thay cả document; không nên kỳ vọng tối ưu partial update tương tự.

MySQL có các hàm hỗ trợ quan sát dung lượng:

    SELECT
        JSON_STORAGE_SIZE(profile) AS storage_bytes,
        JSON_STORAGE_FREE(profile) AS reusable_bytes
    FROM customer_profile
    WHERE customer_id = 1;

JSON_STORAGE_SIZE cho biết dung lượng lưu trữ của tài liệu JSON; JSON_STORAGE_FREE cho biết phần dung lượng trống có thể còn lại sau các partial update đủ điều kiện. Đây là thông tin chẩn đoán, không phải cam kết rằng mọi lần sửa đều tại chỗ.

Trong row-based binary logging, cấu hình PARTIAL_JSON có thể ảnh hưởng cách ghi thay đổi JSON vào binary log. Cần kiểm tra cấu hình replication và tài liệu phiên bản đang chạy trước khi thay đổi binlog_row_value_options.

Không tối ưu vi mô chỉ dựa trên tên hàm. Hãy đo kích thước tài liệu, tần suất cập nhật, số index phụ và chi phí replication trên workload thực tế.

## 16. Index cho dữ liệu JSON thường xuyên được truy vấn

Cột JSON không tự tạo index cho mọi key bên trong document. Nếu ứng dụng thường lọc theo một thuộc tính JSON, hãy cân nhắc generated column hoặc functional index.

Ví dụ thường truy vấn theo plan:

    ALTER TABLE customer_profile
    ADD COLUMN plan_code VARCHAR(30)
        GENERATED ALWAYS AS (
            profile->>'$.plan.code'
        ) STORED,
    ADD INDEX idx_customer_plan (plan_code);

Sau đó truy vấn:

    SELECT customer_id, profile
    FROM customer_profile
    WHERE plan_code = 'PRO';

Generated column giúp biểu diễn một thuộc tính JSON thành cột có kiểu và index rõ ràng. Cần chọn độ dài, collation và kiểu dữ liệu phù hợp với giá trị thực tế.

Nếu chỉ sửa JSON bằng JSON_SET nhưng không có index cho đường dẫn được lọc, các câu SELECT theo JSON_EXTRACT có thể phải đọc nhiều hàng. Không nên đưa toàn bộ thuộc tính nghiệp vụ quan trọng vào JSON nếu chúng cần join, unique constraint, foreign key hoặc truy vấn có selectivity cao.

## 17. NULL, path lỗi và dữ liệu không đúng cấu trúc

Các hàm sửa JSON không thay thế việc xác thực đầu vào. Một số lỗi thường gặp:

- Document không phải JSON hợp lệ.
- JSON path sai cú pháp.
- Dùng wildcard trong path của hàm sửa đổi.
- Truyền số lượng đối số path-value không hợp lệ.
- Path cha không tồn tại.
- Giá trị tại path có kiểu khác với giả định của ứng dụng.
- Một đối số SQL NULL khiến hàm trả SQL NULL.

Ví dụ path sai:

    SELECT JSON_SET(
        '{"name":"An"}',
        '$.preferences[',
        'vi'
    );

Path sai cú pháp sẽ gây lỗi thay vì âm thầm được sửa.

### 17.1. Kiểm tra document đầu vào

Nếu dữ liệu đến dưới dạng text trước khi ghi vào cột JSON:

    SELECT JSON_VALID(
        '{"name":"An","active":true}'
    );

JSON_VALID trả 1 nếu văn bản là JSON hợp lệ, 0 nếu không hợp lệ. Cột JSON tự xác thực khi ghi; kiểm tra này hữu ích hơn ở ranh giới nhận dữ liệu text.

### 17.2. Kiểm tra kiểu trước khi sửa

Không giả định preferences luôn là object:

    SELECT
        JSON_TYPE(
            JSON_EXTRACT(profile, '$.preferences')
        )
    FROM customer_profile
    WHERE customer_id = 1;

Nếu preferences là string hoặc array, path con như preferences.theme không mang ý nghĩa như khi parent là object. Hãy từ chối dữ liệu sai schema hoặc chuẩn hóa theo quy tắc được định nghĩa rõ.

## 18. An toàn khi path đến từ ứng dụng

Không ghép trực tiếp path từ input không tin cậy vào chuỗi SQL. Hãy:

- Dùng prepared statement cho giá trị document và path.
- Allowlist các path ứng dụng được phép sửa, ví dụ chỉ cho phép preferences.theme và preferences.language.
- Không cho client tự chọn path bất kỳ nếu thao tác đó có thể thay đổi role, permission, billing hoặc trạng thái bảo mật.
- Kiểm tra kiểu và giá trị được phép trước khi ghi.
- Giới hạn kích thước JSON payload.
- Ghi audit ở cấp nghiệp vụ cho các thay đổi nhạy cảm.

Prepared statement giúp ngăn SQL injection, nhưng không tự giải quyết việc một client có quyền sửa nhầm path nghiệp vụ. Authorization phải kiểm tra cả bản ghi và trường được phép thay đổi.

## 19. Ma trận chọn hàm theo nghiệp vụ

| Nghiệp vụ | Hàm | Lý do |
|---|---|---|
| Luôn đặt language thành giá trị mới | JSON_SET | Có thể thêm hoặc thay |
| Chỉ tạo cờ beta nếu chưa có | JSON_INSERT | Không ghi đè giá trị đã tồn tại |
| Chỉ đổi theme nếu trường đã tồn tại | JSON_REPLACE | Không tạo path mới do typo |
| Xóa token tạm sau khi sử dụng | JSON_REMOVE | Loại bỏ member |
| Sửa nhiều cài đặt cùng lúc | JSON_SET | Nhiều path-value trong một lần gọi |
| Thêm member metadata nhưng giữ member cũ | JSON_INSERT | Chỉ thêm member thiếu |
| Xóa nhiều member đã biết | JSON_REMOVE | Nhiều path trong một lần gọi |
| Chèn array element vào giữa và dịch phần tử | JSON_ARRAY_INSERT | Chuyên biệt cho thao tác chèn array |
| Append array tổng quát | JSON_ARRAY_APPEND | Chuyên biệt cho thao tác append |

Không có hàm nào thay thế hoàn toàn các hàm kia. Chọn theo điều kiện tồn tại và tác động mong muốn.

## 20. Lab thực hành: quản lý hồ sơ khách hàng

Lab này dùng bảng customer_profile đã tạo ở đầu bài. Hãy chạy trong schema thử nghiệm.

### Bước 1: xem tài liệu hiện tại

    SELECT
        customer_id,
        JSON_PRETTY(profile)
    FROM customer_profile
    WHERE customer_id = 1;

### Bước 2: đổi ngôn ngữ bằng JSON_SET

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1;

Xác nhận language đổi thành vi và theme vẫn còn.

### Bước 3: thêm member chỉ khi chưa có

    UPDATE customer_profile
    SET profile = JSON_INSERT(
        profile,
        '$.metadata.source',
        'web'
    )
    WHERE customer_id = 1;

Chạy lần thứ hai với giá trị source khác. Giá trị đầu tiên vẫn được giữ.

### Bước 4: chỉ thay trường đã tồn tại

    UPDATE customer_profile
    SET profile = JSON_REPLACE(
        profile,
        '$.preferences.theme',
        'dark',
        '$.preferences.unknown_setting',
        'ignored'
    )
    WHERE customer_id = 1;

theme đổi thành dark; unknown_setting không được thêm.

### Bước 5: xóa token

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.temporary_token'
    )
    WHERE customer_id = 1;

Kiểm tra temporary_token không còn trong tài liệu.

### Bước 6: thay phần tử array

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.tags[0]',
        'database'
    )
    WHERE customer_id = 1;

Kiểm tra phần tử thứ hai vẫn là sql.

### Bước 7: xóa phần tử array

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.tags[0]'
    )
    WHERE customer_id = 1;

Kiểm tra array còn phần tử sql và index của nó đã chuyển thành 0.

### Bước 8: kiểm tra kiểu và kích thước

    SELECT
        JSON_TYPE(profile) AS root_type,
        JSON_TYPE(
            JSON_EXTRACT(profile, '$.preferences')
        ) AS preferences_type,
        JSON_LENGTH(profile, '$.tags') AS tag_count,
        JSON_STORAGE_SIZE(profile) AS storage_bytes,
        JSON_STORAGE_FREE(profile) AS reusable_bytes
    FROM customer_profile
    WHERE customer_id = 1;

### Bước 9: kiểm tra optimistic locking

    UPDATE customer_profile
    SET profile = JSON_SET(
            profile,
            '$.preferences.theme',
            'light'
        ),
        version_no = version_no + 1
    WHERE customer_id = 1
      AND version_no = 0;

Kiểm tra số hàng được cập nhật. Nếu version_no không còn bằng 0, câu UPDATE không sửa hàng và ứng dụng phải xử lý conflict.

## 21. Các lỗi thiết kế thường gặp

- Dùng JSON_INSERT trong khi muốn luôn cập nhật giá trị.
- Dùng JSON_REPLACE rồi ngạc nhiên vì path mới không được tạo.
- Dùng JSON_SET với path sâu nhưng parent object chưa tồn tại.
- Nghĩ JSON_INSERT sẽ chèn vào giữa array và dịch các phần tử.
- Xóa array index theo thứ tự tăng dần rồi xóa nhầm phần tử.
- Nhầm JSON null với SQL NULL.
- Truyền chuỗi JSON vào value argument và vô tình lưu nó thành JSON string.
- Thay cả object cha rồi làm mất các member không được truyền.
- Gửi payload JSON cũ từ client và ghi đè thay đổi mới hơn.
- Không kiểm tra JSON_TYPE trước khi thao tác trên object hoặc array.
- Dùng wildcard path trong hàm sửa JSON.
- Ghép path không tin cậy vào SQL.
- Cho phép client sửa các path nhạy cảm mà không kiểm tra authorization.
- Lưu thuộc tính cần join, unique hoặc foreign key trong JSON chỉ vì tiện.
- Giả định mọi JSON_SET đều được tối ưu partial update.
- Không kiểm tra chi phí index, binary log và replication khi cập nhật tài liệu lớn.

## 22. Checklist trước khi triển khai

- Đã chọn đúng hàm theo ngữ nghĩa thêm, thay, chỉ thay hoặc xóa.
- Đã xác nhận JSON path đúng cú pháp và không có wildcard.
- Đã xác nhận object cha/array cha tồn tại và đúng kiểu.
- Đã xác nhận index array bắt đầu từ 0.
- Đã xác định thứ tự các path chồng lấn.
- Đã xử lý array removal theo thứ tự index giảm dần khi cần.
- Đã phân biệt SQL NULL với JSON null.
- Đã dùng CAST(... AS JSON), JSON_OBJECT hoặc JSON_ARRAY khi cần giá trị có cấu trúc.
- Đã dùng UPDATE có WHERE giới hạn đúng hàng.
- Đã dùng transaction hoặc optimistic version khi nghiệp vụ yêu cầu.
- Đã kiểm thử path tồn tại, path thiếu và parent sai kiểu.
- Đã kiểm tra giá trị sau sửa bằng JSON_EXTRACT/JSON_TYPE/JSON_PRETTY.
- Đã đánh giá generated column hoặc functional index cho path truy vấn thường xuyên.
- Đã đo partial update thay vì giả định luôn xảy ra.
- Đã dùng prepared statement và allowlist path từ ứng dụng.
- Đã kiểm thử trên dữ liệu đại diện trước khi phát hành.

## 23. Tài liệu tham khảo

- MySQL 8.4 Reference Manual — JSON Modification Functions: https://dev.mysql.com/doc/refman/8.4/en/json-modification-functions.html
- MySQL 8.4 Reference Manual — JSON Path Syntax: https://dev.mysql.com/doc/refman/8.4/en/json.html
- MySQL 8.4 Reference Manual — The JSON Data Type: https://dev.mysql.com/doc/refman/8.4/en/json.html
- MySQL 8.4 Reference Manual — Partial Updates of JSON Values: https://dev.mysql.com/doc/refman/8.4/en/json.html
- MySQL 8.4 Reference Manual — JSON Utility Functions: https://dev.mysql.com/doc/refman/8.4/en/json-utility-functions.html
- MySQL 8.4 Reference Manual — Generated Column Indexes: https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html

JSON_SET thêm hoặc thay; JSON_INSERT chỉ thêm; JSON_REPLACE chỉ thay giá trị đã tồn tại; JSON_REMOVE xóa path. Bốn hàm đánh giá path theo thứ tự trái sang phải, vì vậy path cha-con và array index có thể làm thay đổi kết quả. JSON path cần cụ thể, parent phải tồn tại và đúng kiểu, còn JSON null phải được phân biệt với SQL NULL. Khi dùng trong UPDATE, hãy sửa đúng path trên giá trị cột hiện tại, giới hạn hàng bằng WHERE, dùng transaction/version khi cần và kiểm tra chi phí lưu trữ, index cùng replication. Chọn hàm theo ý định nghiệp vụ thay vì chỉ theo tên hàm sẽ giúp tránh mất dữ liệu và giữ cấu trúc JSON nhất quán.
