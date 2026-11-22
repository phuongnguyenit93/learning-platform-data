# JSON path, JSON_EXTRACT, toán tử -> và ->>

MySQL lưu tài liệu JSON trong kiểu dữ liệu JSON và cung cấp JSON path để định vị một giá trị bên trong tài liệu. Khi biết đường dẫn, bạn có thể dùng JSON_EXTRACT để lấy giá trị, toán tử -> như cách viết ngắn của JSON_EXTRACT, và toán tử ->> để lấy giá trị ở dạng văn bản đã bỏ dấu nháy JSON. Ba cách viết này giúp truy vấn dữ liệu bán cấu trúc mà không phải tách toàn bộ tài liệu thành nhiều cột ngay từ đầu.

Trong module DATABASE_MYSQL, bài học này tập trung vào cú pháp JSON path, cách đi qua object và array, xử lý wildcard và nhiều đường dẫn, phân biệt SQL NULL với JSON null, cũng như lựa chọn giữa JSON_EXTRACT, -> và ->>. Cuối bài có ví dụ lập chỉ mục cho các thuộc tính JSON thường được lọc để tránh quét tài liệu trên mọi hàng.

## 1. Chuẩn bị bảng JSON để thực hành

Kiểu JSON của MySQL kiểm tra tính hợp lệ của tài liệu khi ghi và lưu dữ liệu theo định dạng nội bộ tối ưu cho việc truy cập thành phần. Một cột JSON có thể chứa object, array, string, number, boolean hoặc JSON null ở cấp gốc.

Kiểu dữ liệu JSON có từ MySQL 5.7.8. Toán tử -> được hỗ trợ từ MySQL 5.7.9 và toán tử ->> từ MySQL 5.7.13. Nếu hệ thống chạy phiên bản cũ hơn, dùng JSON_EXTRACT và JSON_UNQUOTE(JSON_EXTRACT(...)) theo khả năng phiên bản.

Tạo bảng ví dụ:

~~~sql
CREATE TABLE customer_profiles (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    profile JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
~~~

Thêm một số tài liệu:

~~~sql
INSERT INTO customer_profiles (profile)
VALUES
(
    '{
      "name": "Lan",
      "age": 29,
      "address": {
        "city": "Da Nang",
        "country": "VN"
      },
      "tags": ["premium", "newsletter"],
      "orders": [
        {"sku": "KB-100", "amount": 850000},
        {"sku": "MS-200", "amount": 320000}
      ],
      "preferences": {
        "nickname": null,
        "language": "vi"
      }
    }'
),
(
    '{
      "name": "Minh",
      "age": 35,
      "address": {
        "city": "Ha Noi",
        "country": "VN"
      },
      "tags": ["business"],
      "orders": [],
      "preferences": {
        "language": "en"
      }
    }'
);
~~~

Đọc tài liệu:

~~~sql
SELECT customer_id, profile
FROM customer_profiles;
~~~

Tài liệu đầu có object lồng nhau, array, số, chuỗi và JSON null. Tài liệu thứ hai không có thuộc tính preferences.nickname. Hai tình huống này sẽ giúp phân biệt giá trị JSON null với đường dẫn không tồn tại.

## 2. JSON path bắt đầu từ ký hiệu $

JSON path là biểu thức chỉ vị trí trong tài liệu JSON. Trong MySQL, ký hiệu $ đại diện cho gốc tài liệu. Các phần tiếp theo chọn member của object hoặc phần tử của array.

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| $ | Toàn bộ tài liệu | $ |
| $.name | Member name ở object gốc | $.name |
| $.address.city | Member lồng nhau | $.address.city |
| $.orders[0] | Phần tử đầu tiên của array | $.orders[0] |
| $.orders[1].sku | Member của phần tử thứ hai | $.orders[1].sku |
| $.tags[*] | Tất cả phần tử của array | $.tags[*] |
| $.address.* | Các member trực tiếp trong object address | $.address.* |

Chỉ số array bắt đầu từ 0. Vì vậy $.orders[0] là phần tử đầu tiên, còn $.orders[1] là phần tử thứ hai.

Tên member trong object JSON phân biệt chữ hoa và chữ thường. Nếu tài liệu có key CustomerName, path $.customername không trỏ đến cùng key.

## 3. Truy cập object lồng nhau

Dùng dấu chấm để đi từ object này sang member của object con:

~~~sql
SELECT
    customer_id,
    JSON_EXTRACT(profile, '$.name') AS customer_name,
    JSON_EXTRACT(profile, '$.address.city') AS city,
    JSON_EXTRACT(profile, '$.address.country') AS country
FROM customer_profiles;
~~~

JSON_EXTRACT trả về giá trị JSON. Vì vậy chuỗi có thể hiển thị với dấu nháy kép bao quanh, ví dụ "Lan". Đây là biểu diễn JSON, không phải chuỗi SQL đã được unquote.

Có thể lấy cả object con:

~~~sql
SELECT JSON_EXTRACT(profile, '$.address')
FROM customer_profiles;
~~~

Kết quả là một object JSON chứa city và country. Path $ lấy toàn bộ tài liệu; path $.address lấy riêng object address.

## 4. Key có dấu cách hoặc ký tự đặc biệt

Khi tên member không phù hợp với cách viết member thông thường, đặt tên trong dấu nháy kép trong path:

~~~sql
SELECT JSON_EXTRACT(
    '{"shipping address":{"city":"Hue"}}',
    '$."shipping address".city'
) AS shipping_city;
~~~

Tương tự, key có dấu chấm trong tên phải được trích dẫn để dấu chấm không bị hiểu thành dấu phân cấp:

~~~sql
SELECT JSON_EXTRACT(
    '{"contact.email":"lan@example.com"}',
    '$."contact.email"'
) AS contact_email;
~~~

Trong SQL, path là chuỗi nên còn chịu quy tắc escape của string literal. Khi key chứa dấu nháy kép hoặc dấu gạch chéo ngược, cần escape đúng cả ở tầng SQL và tầng JSON path. Nếu ứng dụng tạo path từ tên key do người dùng nhập, hãy kiểm soát việc escape thay vì nối chuỗi tùy tiện.

## 5. Truy cập phần tử array

Array JSON được truy cập bằng chỉ số trong ngoặc vuông:

~~~sql
SELECT
    JSON_EXTRACT(profile, '$.orders[0].sku') AS first_sku,
    JSON_EXTRACT(profile, '$.orders[1].amount') AS second_amount
FROM customer_profiles;
~~~

Để lấy toàn bộ array:

~~~sql
SELECT JSON_EXTRACT(profile, '$.orders')
FROM customer_profiles;
~~~

Để lấy một phần tử:

~~~sql
SELECT JSON_EXTRACT(profile, '$.tags[0]')
FROM customer_profiles;
~~~

Chỉ số ngoài phạm vi không làm MySQL tự tạo phần tử mới. Nếu path không tìm thấy giá trị, JSON_EXTRACT trả SQL NULL. Hãy kiểm tra đường dẫn và độ dài array nếu logic yêu cầu phần tử bắt buộc.

## 6. Wildcard trong JSON path

Wildcard cho phép chọn nhiều member hoặc phần tử:

- .* chọn các member trực tiếp của object.
- [*] chọn tất cả phần tử trực tiếp của array.
- ** là recursive descent, dùng để tìm member ở các mức lồng nhau theo phần path tiếp theo.

Ví dụ lấy SKU của mọi đơn hàng:

~~~sql
SELECT JSON_EXTRACT(profile, '$.orders[*].sku') AS all_skus
FROM customer_profiles;
~~~

Kết quả của path có wildcard được trả về dưới dạng array chứa các giá trị khớp. Nếu array nguồn rỗng hoặc không có phần tử khớp, kết quả có thể là array rỗng tùy biểu thức path.

Wildcard object:

~~~sql
SELECT JSON_EXTRACT(profile, '$.address.*') AS address_values
FROM customer_profiles;
~~~

Recursive descent có thể tìm member cùng tên ở các độ sâu khác nhau:

~~~sql
SELECT JSON_EXTRACT(
    '{"item":{"sku":"A-1"},"nested":{"item":{"sku":"B-2"}}}',
    '$**.sku'
) AS all_skus;
~~~

Wildcard hữu ích khi cấu trúc lồng nhau không cố định, nhưng kết quả có thể lớn. Không dùng path quá rộng cho tài liệu lớn nếu ứng dụng chỉ cần một vài thuộc tính cụ thể.

## 7. JSON_EXTRACT: hàm lấy giá trị JSON

Cú pháp:

~~~sql
JSON_EXTRACT(json_doc, path[, path] ...)
~~~

Tham số đầu là tài liệu JSON hoặc biểu thức trả về JSON. Mỗi path xác định vị trí cần lấy. Hàm trả về JSON, không tự động chuyển chuỗi JSON thành chuỗi SQL không có dấu nháy.

Ví dụ:

~~~sql
SELECT
    JSON_EXTRACT(profile, '$.name') AS name_json,
    JSON_EXTRACT(profile, '$.age') AS age_json,
    JSON_EXTRACT(profile, '$.address.city') AS city_json
FROM customer_profiles;
~~~

JSON_EXTRACT có thể lấy object, array, string, number, boolean hoặc JSON null. Nếu path hợp lệ nhưng không khớp giá trị nào, kết quả là SQL NULL. Nếu tài liệu hoặc đối số path là SQL NULL, hàm cũng có thể trả SQL NULL.

Path sai cú pháp không tương đương với path không tồn tại: path không hợp lệ có thể làm câu lệnh báo lỗi. Vì vậy, dữ liệu path động cần được kiểm tra trước khi dùng.

## 8. Truyền nhiều path vào JSON_EXTRACT

JSON_EXTRACT cho phép truyền nhiều path trong một lần gọi:

~~~sql
SELECT JSON_EXTRACT(
    profile,
    '$.name',
    '$.age',
    '$.address.city'
) AS selected_values
FROM customer_profiles;
~~~

Khi truyền nhiều path, các giá trị khớp được tự động bọc trong một array theo thứ tự các path đã truyền. Ví dụ với tài liệu đầu, kết quả có dạng:

~~~json
["Lan", 29, "Da Nang"]
~~~

Điều này khác với gọi JSON_EXTRACT chỉ có một path, khi hàm trả trực tiếp giá trị tại path đó. Path không khớp không tạo một phần tử JSON null giả trong array kết quả; nếu không path nào khớp, hàm trả SQL NULL. Hãy kiểm tra kết quả khi trộn path bắt buộc và path tùy chọn.

## 9. Toán tử -> là cách viết ngắn của JSON_EXTRACT

Toán tử -> giúp truy cập JSON path ngắn gọn:

~~~sql
SELECT
    profile -> '$.name' AS name_json,
    profile -> '$.address.city' AS city_json,
    profile -> '$.orders[0].sku' AS first_sku_json
FROM customer_profiles;
~~~

Về ý nghĩa, biểu thức:

~~~sql
profile -> '$.name'
~~~

tương đương:

~~~sql
JSON_EXTRACT(profile, '$.name')
~~~

Toán tử -> vẫn trả về giá trị JSON. Nếu giá trị là string, kết quả giữ biểu diễn JSON có dấu nháy kép. Nếu cần chuỗi văn bản để hiển thị, nối chuỗi hoặc so sánh với giá trị SQL, hãy cân nhắc ->> hoặc JSON_UNQUOTE.

Trong cú pháp toán tử, vế trái phải là định danh cột và vế phải là path dạng chuỗi literal. Nếu biểu thức bên trái phức tạp hoặc path cần được truyền động, dùng JSON_EXTRACT tường minh khi phù hợp với cú pháp và phiên bản MySQL. Không nối path do người dùng nhập vào câu SQL mà không validate và escape.

## 10. Toán tử ->> lấy giá trị đã unquote

Toán tử ->> là cách viết ngắn của:

~~~sql
JSON_UNQUOTE(JSON_EXTRACT(json_doc, path))
~~~

Ví dụ:

~~~sql
SELECT
    profile -> '$.name' AS name_json,
    profile ->> '$.name' AS name_text,
    profile ->> '$.address.city' AS city_text
FROM customer_profiles;
~~~

Với giá trị JSON string "Lan":

- profile -> '$.name' trả biểu diễn JSON "Lan".
- profile ->> '$.name' trả chuỗi Lan không có dấu nháy JSON.

Với số hoặc boolean, ->> trả biểu diễn văn bản của giá trị. Nó không tự biến chuỗi số thành kiểu số SQL; khi cần tính toán hoặc so sánh theo miền số, hãy CAST rõ ràng.

Với object hoặc array, kết quả vẫn là văn bản biểu diễn JSON của object/array. ->> không làm phẳng cấu trúc lồng nhau.

## 11. So sánh ba cách viết

| Cách viết | Ý nghĩa | Kết quả |
|---|---|---|
| JSON_EXTRACT(profile, '$.name') | Hàm lấy giá trị theo path | JSON |
| profile -> '$.name' | Toán tử rút gọn của JSON_EXTRACT | JSON |
| profile ->> '$.name' | JSON_UNQUOTE(JSON_EXTRACT(...)) | Văn bản đã bỏ dấu nháy JSON |

Chọn cách viết theo mục tiêu:

- Dùng JSON_EXTRACT khi cần nhiều path hoặc muốn thể hiện rõ hàm đang được gọi.
- Dùng -> khi truy vấn một path đơn giản và muốn giữ kiểu JSON.
- Dùng ->> khi cần lấy scalar ở dạng text cho hiển thị hoặc chuyển kiểu.

Đừng dùng ->> chỉ vì kết quả trông dễ đọc hơn. Nếu cần so sánh số, ngày hoặc boolean, phải chuyển đổi và xác thực kiểu dữ liệu theo quy tắc nghiệp vụ.

## 12. Phân biệt SQL NULL, JSON null và path không tồn tại

Đây là một khác biệt quan trọng khi truy vấn JSON:

- SQL NULL là trạng thái không có giá trị SQL.
- JSON null là một giá trị hợp lệ bên trong tài liệu JSON.
- Path không tồn tại nghĩa là tài liệu không có member hoặc phần tử được yêu cầu; JSON_EXTRACT trả SQL NULL.

Với tài liệu đầu:

~~~sql
SELECT
    JSON_EXTRACT(profile, '$.preferences.nickname') AS nickname,
    JSON_EXTRACT(profile, '$.preferences.timezone') AS timezone
FROM customer_profiles
WHERE customer_id = 1;
~~~

nickname tồn tại và có giá trị JSON null. timezone không tồn tại nên kết quả là SQL NULL.

Có thể kiểm tra sự tồn tại của path:

~~~sql
SELECT
    JSON_CONTAINS_PATH(
        profile,
        'one',
        '$.preferences.nickname'
    ) AS has_nickname,
    JSON_CONTAINS_PATH(
        profile,
        'one',
        '$.preferences.timezone'
    ) AS has_timezone
FROM customer_profiles
WHERE customer_id = 1;
~~~

JSON_CONTAINS_PATH trả 1 nếu có ít nhất một path được tìm thấy với mode one, trả 0 nếu không có path nào khớp. Mode all yêu cầu tất cả path truyền vào phải tồn tại.

Kiểm tra JSON null bằng JSON_TYPE:

~~~sql
SELECT
    JSON_TYPE(
        JSON_EXTRACT(profile, '$.preferences.nickname')
    ) AS nickname_type,
    JSON_TYPE(
        JSON_EXTRACT(profile, '$.preferences.timezone')
    ) AS timezone_type
FROM customer_profiles
WHERE customer_id = 1;
~~~

Với nickname, JSON_TYPE trả chuỗi NULL để chỉ kiểu JSON null. Với timezone không tồn tại, JSON_EXTRACT trả SQL NULL nên JSON_TYPE cũng trả SQL NULL. Đừng chỉ dùng IS NULL nếu cần phân biệt hai trường hợp.

## 13. Kiểm tra kiểu dữ liệu trước khi chuyển đổi

JSON_TYPE cho biết kiểu của giá trị JSON:

~~~sql
SELECT
    JSON_TYPE(JSON_EXTRACT(profile, '$.name')) AS name_type,
    JSON_TYPE(JSON_EXTRACT(profile, '$.age')) AS age_type,
    JSON_TYPE(JSON_EXTRACT(profile, '$.tags')) AS tags_type
FROM customer_profiles;
~~~

Các kết quả thường gặp gồm OBJECT, ARRAY, STRING, INTEGER, DOUBLE, DECIMAL, BOOLEAN và NULL. Giá trị thiếu path tạo SQL NULL chứ không phải một JSON type.

Nếu ứng dụng kỳ vọng age là số nhưng tài liệu có thể chứa chuỗi "29", hãy kiểm tra JSON_TYPE hoặc CAST có chủ đích. Không mặc định rằng mọi tài liệu đều tuân thủ cùng schema chỉ vì cột có kiểu JSON.

Ví dụ chuyển age sang số nguyên:

~~~sql
SELECT
    customer_id,
    CAST(profile ->> '$.age' AS UNSIGNED) AS age_number
FROM customer_profiles;
~~~

CAST giúp xác định kiểu kết quả SQL. Tuy nhiên, dữ liệu không hợp lệ hoặc không thể chuyển đổi có thể tạo warning, kết quả không như mong đợi hoặc lỗi tùy ngữ cảnh và SQL mode. Với dữ liệu đầu vào không đáng tin cậy, cần kiểm tra kiểu và miền giá trị trước khi dùng trong phép tính.

## 14. Lọc hàng bằng JSON path

Có thể dùng JSON_EXTRACT hoặc -> trong WHERE:

~~~sql
SELECT customer_id, profile ->> '$.name' AS customer_name
FROM customer_profiles
WHERE profile ->> '$.address.city' = 'Da Nang';
~~~

Với thuộc tính số:

~~~sql
SELECT customer_id
FROM customer_profiles
WHERE CAST(profile ->> '$.age' AS UNSIGNED) >= 30;
~~~

Với phần tử array, JSON_CONTAINS có thể kiểm tra một giá trị JSON có nằm trong tài liệu hay không:

~~~sql
SELECT customer_id
FROM customer_profiles
WHERE JSON_CONTAINS(profile, '"premium"', '$.tags');
~~~

JSON_CONTAINS là hàm kiểm tra cấu trúc/giá trị JSON; nó không đồng nghĩa với việc tìm chuỗi con bằng LIKE. Chọn hàm theo đúng ý nghĩa dữ liệu.

Khi dùng CAST trong WHERE, MySQL có thể phải tính biểu thức cho nhiều hàng nếu không có index phù hợp. Nếu một path thường xuyên xuất hiện trong điều kiện lọc, hãy cân nhắc generated column hoặc functional index phù hợp phiên bản.

## 15. Lập chỉ mục cho thuộc tính JSON thường truy vấn

Cột JSON không được lập chỉ mục trực tiếp như một cột số hoặc chuỗi thông thường để tìm mọi giá trị con tùy ý. Một cách phổ biến là tạo generated column trích xuất path cần dùng rồi lập chỉ mục cột đó.

Ví dụ tạo cột city:

~~~sql
ALTER TABLE customer_profiles
    ADD COLUMN city VARCHAR(80)
        GENERATED ALWAYS AS (
            profile ->> '$.address.city'
        ) STORED,
    ADD INDEX idx_customer_profiles_city (city);
~~~

Truy vấn có thể lọc theo city:

~~~sql
SELECT customer_id
FROM customer_profiles
WHERE city = 'Da Nang';
~~~

Generated column làm rõ kiểu SQL và cho phép tạo index thông thường. STORED lưu giá trị sinh ra trong hàng; VIRTUAL tính giá trị khi đọc nhưng vẫn có thể được lập chỉ mục theo các quy tắc generated column của MySQL.

Với thuộc tính số, khai báo kiểu số và CAST rõ ràng:

~~~sql
ALTER TABLE customer_profiles
    ADD COLUMN age_number INT
        GENERATED ALWAYS AS (
            CAST(profile ->> '$.age' AS UNSIGNED)
        ) STORED,
    ADD INDEX idx_customer_profiles_age (age_number);
~~~

Trước khi triển khai, bảo đảm dữ liệu JSON hiện có có age chuyển đổi được và nằm trong miền INT. Nếu tài liệu thiếu age hoặc chứa kiểu không phù hợp, hãy định nghĩa hành vi mong muốn và kiểm tra dữ liệu trước khi thêm generated column.

## 16. Generated column và functional index

Generated column phù hợp khi:

- Một path được dùng trong nhiều truy vấn.
- Cần gán kiểu SQL rõ ràng như VARCHAR, INT hoặc DECIMAL.
- Muốn đặt tên thuộc tính JSON như một cột nghiệp vụ dễ đọc.
- Muốn index và thống kê optimizer trên thuộc tính đó.

MySQL 8.0.13 trở lên còn hỗ trợ functional key parts để lập chỉ mục trên biểu thức. Tuy nhiên, biểu thức JSON cần được viết với kiểu và collation rõ ràng; generated column thường dễ quan sát và tái sử dụng hơn.

Ví dụ minh họa functional index cho giá trị chuỗi:

~~~sql
CREATE INDEX idx_profile_city_expression
ON customer_profiles (
    (CAST(profile ->> '$.address.city' AS CHAR(80)))
);
~~~

Khả năng dùng index phụ thuộc biểu thức truy vấn khớp với biểu thức index, kiểu dữ liệu và collation. Dùng EXPLAIN để xác nhận optimizer thực sự chọn index; việc tạo index thành công không bảo đảm mọi câu truy vấn sẽ dùng nó.

## 17. JSON path trong SELECT, WHERE và ORDER BY

JSON path có thể xuất hiện ở nhiều phần truy vấn:

~~~sql
SELECT
    customer_id,
    profile ->> '$.name' AS customer_name,
    CAST(profile ->> '$.age' AS UNSIGNED) AS age_number
FROM customer_profiles
WHERE profile ->> '$.address.country' = 'VN'
ORDER BY CAST(profile ->> '$.age' AS UNSIGNED) DESC;
~~~

Trong ví dụ này, cùng một path age được trích xuất và chuyển kiểu ở SELECT và ORDER BY. Nếu truy vấn này chạy thường xuyên trên bảng lớn, generated column age_number và city/country có thể giúp truy vấn rõ hơn và có cơ hội dùng index.

Tránh viết path khác nhau cho cùng một thuộc tính do không thống nhất chữ hoa/thường hoặc tên key. Một quy ước JSON schema ổn định giúp giảm lỗi truy vấn và dễ bảo trì index.

## 18. Nhiều path và wildcard có thể làm tăng kích thước kết quả

JSON_EXTRACT có thể trả object hoặc array lớn nếu path lấy cả nhánh tài liệu hoặc dùng wildcard. Điều đó làm tăng lượng dữ liệu truyền qua mạng và công việc parse ở ứng dụng.

Ví dụ:

~~~sql
-- Lấy cả object address.
SELECT JSON_EXTRACT(profile, '$.address')
FROM customer_profiles;

-- Chỉ lấy city.
SELECT profile ->> '$.address.city'
FROM customer_profiles;
~~~

Nếu ứng dụng chỉ cần city, chọn path cụ thể giúp giảm kích thước kết quả. Khi path wildcard khớp nhiều phần tử, kiểm tra số lượng phần tử và tránh trả toàn bộ array nếu chỉ cần một thống kê.

## 19. Lỗi thường gặp khi dùng JSON path và toán tử

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng $.orders[1] nhưng mong phần tử đầu | Array đánh chỉ số từ 0 | Dùng [0] cho phần tử đầu |
| Key có dấu cách nhưng viết $.shipping address | Path không phân tích key như mong đợi | Dùng $."shipping address" |
| So sánh JSON string với text không đúng kiểu | JSON_EXTRACT trả JSON có dấu nháy | Dùng ->> hoặc JSON_UNQUOTE |
| Dùng ->> rồi nghĩ kết quả là số | Kết quả là text | CAST sang kiểu số sau khi kiểm tra dữ liệu |
| Coi JSON null là SQL NULL | Hai trạng thái khác nhau | Kết hợp JSON_CONTAINS_PATH và JSON_TYPE |
| Không phân biệt path sai với path thiếu | Path sai cú pháp có thể báo lỗi; path hợp lệ nhưng thiếu trả SQL NULL | Validate path và kiểm tra sự tồn tại |
| Dùng wildcard trên tài liệu rất lớn | Kết quả có thể là array lớn | Chọn path hẹp và giới hạn dữ liệu |
| Lọc JSON trên bảng lớn nhưng không có index | Biểu thức được tính cho nhiều hàng | Dùng generated column hoặc functional index |
| Nghĩ JSON path không phân biệt hoa thường | Tên member JSON phân biệt hoa thường | Dùng đúng tên key |
| Nối path từ input không escape | Key có ký tự đặc biệt làm sai path hoặc thay đổi ý nghĩa | Escape và validate member name |

## 20. Quy trình chọn cách truy xuất

1. Xác định tài liệu JSON và key cần lấy.
2. Viết path bắt đầu bằng $, kiểm tra từng member và chỉ số array.
3. Nếu key có dấu cách hoặc dấu chấm, dùng cú pháp member được trích dẫn.
4. Dùng JSON_EXTRACT để kiểm tra giá trị JSON trước.
5. Chọn -> nếu cần biểu diễn JSON; chọn ->> nếu cần văn bản.
6. Dùng JSON_TYPE để kiểm tra kiểu nếu dữ liệu có thể không đồng nhất.
7. Phân biệt JSON null, SQL NULL và path không tồn tại.
8. CAST rõ ràng khi cần số hoặc kiểu SQL khác.
9. Nếu path xuất hiện thường xuyên trong WHERE/ORDER BY, cân nhắc generated column hoặc functional index.
10. Dùng EXPLAIN để xác nhận kế hoạch và đo trên dữ liệu đại diện.
11. Kiểm tra phiên bản MySQL và cú pháp path trước khi triển khai.
12. Giữ quy ước tên key và schema JSON nhất quán giữa các dịch vụ.

## 21. Bài tập thực hành

1. Tạo bảng customer_profiles và chèn hai tài liệu JSON mẫu ở đầu bài.
2. Dùng JSON_EXTRACT lấy name, age và address.city.
3. Lấy toàn bộ object address và phần tử đầu tiên của orders.
4. Dùng path $."shipping address".city trên tài liệu có key chứa dấu cách.
5. Dùng wildcard $.orders[*].sku để lấy danh sách SKU.
6. Gọi JSON_EXTRACT với hai hoặc ba path và quan sát kết quả array tự động.
7. So sánh profile -> '$.name' với profile ->> '$.name'.
8. Dùng JSON_TYPE để phân biệt STRING, INTEGER, ARRAY, OBJECT và JSON null.
9. Dùng JSON_CONTAINS_PATH để phân biệt nickname có giá trị JSON null với timezone không tồn tại.
10. Lọc khách hàng theo city và age; CAST age thành kiểu số trước khi so sánh.
11. Tạo generated column city và index; dùng EXPLAIN kiểm tra truy vấn theo city.
12. Tạo generated column age_number, kiểm tra dữ liệu đầu vào rồi lập chỉ mục.
13. So sánh truy vấn lấy cả object address với truy vấn chỉ lấy address.city về kích thước kết quả.
14. Giải thích khi nào nên dùng JSON_EXTRACT, -> và ->> trong một API đọc hồ sơ khách hàng.

Bạn hoàn thành bài khi viết được JSON path chính xác cho object và array, phân biệt được kết quả JSON với văn bản đã unquote, xử lý đúng JSON null và path không tồn tại, đồng thời biết đưa thuộc tính JSON thường lọc vào generated column có index. JSON linh hoạt ở tầng lưu trữ nhưng truy vấn hiệu quả vẫn cần kiểu dữ liệu, path và chỉ mục được thiết kế rõ ràng.
