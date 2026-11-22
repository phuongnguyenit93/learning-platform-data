# Chuỗi, Unicode, độ dài cột và dữ liệu rỗng

Trong ứng dụng **Spring Data Relational JDBC (Spring Data JDBC)**, giá trị chuỗi đi qua nhiều lớp trước khi trở thành dữ liệu trong bảng: từ `String` của Java, qua JDBC driver, đến cột `VARCHAR` hoặc `TEXT` trong PostgreSQL/MySQL. Cùng một giá trị nhìn thấy trên màn hình có thể có số byte, số ký tự Unicode và độ dài Java khác nhau; ngoài ra, `null`, chuỗi rỗng và chuỗi chỉ có khoảng trắng đều mang ý nghĩa riêng.

Bài này hướng dẫn lựa chọn kiểu cột, lưu tiếng Việt và emoji đúng Unicode, đặt giới hạn độ dài hợp lý, thiết kế quy tắc cho dữ liệu rỗng và ánh xạ những quyết định ấy vào entity/repository của Spring Data JDBC.

## 1. Bốn câu hỏi trước khi thêm một cột chuỗi

Ví dụ hệ thống lưu hồ sơ hiển thị của khách hàng. Mỗi hồ sơ có tên hiển thị, biệt danh, giới thiệu ngắn và mã ngôn ngữ.

| Trường | Câu hỏi nghiệp vụ | Quyết định minh họa |
|---|---|---|
| `displayName` | Bắt buộc phải có tên? Giới hạn tên thế nào? | Bắt buộc, không toàn khoảng trắng, tối đa 80 ký tự |
| `nickname` | Không đặt biệt danh có hợp lệ không? | Tùy chọn; dùng `NULL` khi không đặt |
| `bio` | Có cần phân biệt “chưa viết” và “đã xóa thành rỗng”? | Cho phép cả `NULL` và `''` nếu nghiệp vụ cần |
| `localeTag` | Chọn ngôn ngữ và vùng nào để hiển thị? | Chuỗi ngắn, ví dụ `vi-VN`, bắt buộc |

Các quyết định thuộc **mô hình dữ liệu và nghiệp vụ** trước khi lựa chọn annotation. Một cột cho phép `NULL` chưa có nghĩa ứng dụng biết sự khác biệt giữa “người dùng chưa nhập” và “người dùng chủ động xóa”; ý nghĩa đó phải được quy định tại API và tầng nghiệp vụ.

~~~mermaid
flowchart LR
    Input["Form / JSON đầu vào"] --> Rules["Quy tắc nghiệp vụ<br/>trim/normalize/validate"]
    Rules --> Entity["Java String<br/>hoặc null"]
    Entity --> Repo["Spring Data JDBC<br/>Repository"]
    Repo --> Driver["JDBC driver"]
    Driver --> Column[("VARCHAR / TEXT<br/>NULL, charset, collation")]
    Column -->|"đọc"| Repo
~~~

Trong luồng này, **chuẩn hóa và kiểm tra đầu vào** nên diễn ra trước khi gọi repository; **database** vẫn cần ràng buộc để chặn dữ liệu không hợp lệ từ các nguồn ghi khác.

## 2. Các kiểu chuỗi thường dùng trong cơ sở dữ liệu quan hệ

| Kiểu SQL | Đặc tính | Khi nên dùng | Điều cần chú ý |
|---|---|---|---|
| `CHAR(n)` | Độ dài cố định, có cơ chế đệm ký tự | Mã có chiều dài thực sự cố định | Khoảng trắng đệm và so sánh cuối chuỗi tùy hệ quản trị; tránh dùng cho tên người |
| `VARCHAR(n)` | Chuỗi biến độ dài với giới hạn `n` | Tên, SKU, email, mã ngôn ngữ | Phải hiểu `n` tính theo ký tự hay byte và ràng buộc byte của DB |
| `TEXT` | Chuỗi dài, không khai báo `n` trong cú pháp kiểu | Mô tả, ghi chú, nội dung tự do | Giới hạn dung lượng, khả năng index và cách lưu khác nhau giữa DB |

**PostgreSQL:** `VARCHAR(n)` giới hạn số ký tự; `TEXT` không có giới hạn khai báo `n` và là kiểu rất thường dùng cho văn bản. `CHAR(n)` được đệm khoảng trắng đến độ dài xác định.

**MySQL 8.x:** `VARCHAR(n)` giới hạn theo số ký tự, nhưng vẫn chịu giới hạn kích thước hàng và số byte theo character set. `TEXT` thường dùng cho đoạn văn dài, song kiểu `TEXT` thông thường bị giới hạn khoảng **65.535 byte** (giới hạn thực tế đối với nội dung có thể còn chịu overhead); dữ liệu dài hơn có thể cần `MEDIUMTEXT` hoặc `LONGTEXT` theo nhu cầu. `CHAR(n)` cũng không phù hợp với tên và mô tả có độ dài biến đổi.

**Không chọn `TEXT` chỉ vì muốn khỏi nghĩ về giới hạn.** Một trường giới thiệu có thể lưu ở `TEXT` nhưng API vẫn nên giới hạn chiều dài hợp lý cho giao diện, tìm kiếm và dung lượng dữ liệu. Ngược lại, một cột `VARCHAR(80)` không tự đảm bảo đầu vào có ý nghĩa hoặc không chứa toàn khoảng trắng.

## 3. Unicode, UTF-8, UTF-16 và độ dài là những khái niệm khác nhau

**Unicode** gán mã cho các ký tự. **UTF-8** và **UTF-16** là cách biểu diễn chuỗi mã đó thành các đơn vị lưu trữ. Java `String` sử dụng các **đơn vị mã UTF-16**, trong khi PostgreSQL/MySQL thường lưu văn bản bằng bộ mã **UTF-8** (với MySQL, dùng `utf8mb4` để hỗ trợ đầy đủ Unicode).

Có ít nhất bốn cách đo “độ dài”:

1. **Byte:** số byte khi mã hóa chuỗi, ví dụ UTF-8; liên quan đến dung lượng, giới hạn kiểu cột và truyền dữ liệu.
2. **UTF-16 code unit:** đơn vị mà `String.length()` của Java đếm. Một emoji ngoài BMP thường chiếm **2** đơn vị.
3. **Unicode code point:** lượng mã Unicode, có thể đếm bằng `String.codePointCount(...)`.
4. **Grapheme cluster:** cụm ký tự người dùng nhận thấy là một biểu tượng; có thể gồm nhiều code point như emoji ghép hoặc chữ có dấu kết hợp.

| Nội dung | `String.length()` | Code point | `CHAR_LENGTH` trong SQL UTF-8 | Byte UTF-8 |
|---|---:|---:|---:|---:|
| `A` | 1 | 1 | 1 | 1 |
| `ế` (dạng một code point) | 1 | 1 | 1 | 3 |
| `🚀` | 2 | 1 | 1 | 4 |
| `e + ◌́` (chữ `e` và dấu sắc kết hợp) | 2 | 2 | 2 | 3 |
| `👩‍💻` (emoji ghép qua ZWJ) | 5 | 3 | 3 | 11 |

Trong bảng trên, `CHAR_LENGTH` có nghĩa là hàm SQL trên dữ liệu được mã hóa UTF-8 ở PostgreSQL/MySQL; nó đo **ký tự theo cách DB triển khai**, không đếm grapheme người dùng nhìn thấy. Chuỗi `👩‍💻` thường hiển thị như một emoji nhưng chứa ba code point.

Ví dụ Java:

~~~java
import java.nio.charset.StandardCharsets;

String rocket = "🚀";
System.out.println(rocket.length());                         // 2 UTF-16 units
System.out.println(rocket.codePointCount(0, rocket.length())); // 1 code point
System.out.println(rocket.getBytes(StandardCharsets.UTF_8).length); // 4 bytes

String joinedEmoji = "👩‍💻";
System.out.println(joinedEmoji.length()); // 5 UTF-16 units
System.out.println(joinedEmoji.codePointCount(
    0, joinedEmoji.length()
)); // 3 code points
~~~

Vì vậy, nếu cột `display_name VARCHAR(80)` quy định 80 ký tự, việc kiểm tra `displayName.length() <= 80` của Java **không đồng nghĩa chính xác** với cách DB giới hạn ký tự. Sử dụng `codePointCount` thường phù hợp hơn khi muốn đối chiếu giới hạn cột theo code point; nếu chính sách hướng tới số “ký tự mắt nhìn thấy” của người dùng, cần thuật toán phân đoạn **grapheme cluster**, không chỉ code point.

### Cùng một chữ có thể được mã hóa theo hai cách

Chữ `é` có thể là:

- **Dạng dựng sẵn:** một code point `U+00E9`.
- **Dạng kết hợp:** `e` (U+0065) + dấu sắc (U+0301).

Hai chuỗi có thể hiển thị giống nhau nhưng khác số code point, byte và phép so sánh nhị phân. Tùy nghiệp vụ, có thể chuẩn hóa về **Unicode NFC** trước khi kiểm tra giới hạn và lưu.

~~~java
import java.text.Normalizer;

String decomposed = "e\u0301";
String composed = Normalizer.normalize(
    decomposed, Normalizer.Form.NFC
);

System.out.println(decomposed.length());  // 2
System.out.println(composed.length());    // 1
System.out.println(composed.equals("é")); // true
~~~

Chuẩn hóa Unicode **không phải** bỏ dấu tiếng Việt. NFC giữ nội dung chữ có dấu, nhưng thống nhất một số cách biểu diễn tương đương. Việc tìm kiếm không phân biệt dấu/case là quyết định **khác** liên quan đến collation hoặc thuật toán tìm kiếm.

## 4. Cấu hình lưu và truyền Unicode trong PostgreSQL hoặc MySQL

### PostgreSQL: database và kết nối UTF8

PostgreSQL lưu chuỗi theo **database encoding**. Khi sử dụng tiếng Việt hoặc emoji, chọn database có encoding `UTF8`. Có thể kiểm tra kết nối:

~~~sql
SHOW server_encoding;
SHOW client_encoding;

SELECT
    CHAR_LENGTH('Tiếng Việt 🚀') AS characters,
    OCTET_LENGTH('Tiếng Việt 🚀') AS bytes_utf8;
~~~

Kết quả phù hợp cho môi trường UTF-8 sẽ có `server_encoding = UTF8` và `client_encoding = UTF8`. Driver PostgreSQL JDBC thực hiện chuyển đổi chuỗi Java qua giao thức và encoding kết nối; không cần tự mã hóa tên hiển thị thành byte rồi lưu vào `VARCHAR`.

Nếu khởi tạo database mới, encoding được đặt ở bước tạo database, chẳng hạn `CREATE DATABASE jdbc_lab ENCODING 'UTF8';` trong môi trường hỗ trợ cấu hình đó. Việc đổi encoding của một database có sẵn không phải đơn giản là chạy `ALTER TABLE`.

### MySQL: dùng utf8mb4 và collation có chủ đích

Trong MySQL, cấu hình **character set** và **collation** là hai việc khác nhau:

- `utf8mb4` định nghĩa bộ mã có thể lưu ký tự Unicode, bao gồm emoji 4 byte.
- `utf8mb4_0900_ai_ci` là một collation có tính chất **accent-insensitive** và **case-insensitive** trong MySQL 8.0+/8.4; nó ảnh hưởng so sánh, sắp xếp và tính duy nhất ở những cột dùng collation đó.

Có thể tạo database cho môi trường học:

~~~sql
CREATE DATABASE jdbc_lab
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

Nếu database đã tồn tại, không chạy lại lệnh `CREATE DATABASE` như một thao tác migration. Hãy kiểm tra thông tin hiện tại:

~~~sql
SHOW CREATE DATABASE jdbc_lab;
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
~~~

Khi tạo bảng, có thể chỉ định rõ `DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci`. Đối với công cụ MySQL CLI, sử dụng kết nối có mã hóa UTF-8 phù hợp, ví dụ tùy chọn `--default-character-set=utf8mb4`; đồng thời lưu file `.sql` bằng UTF-8.

**Lỗi thường gặp:** dùng bộ mã MySQL `utf8` trong các cấu hình cũ mà thực chất chỉ hỗ trợ tối đa ba byte mỗi ký tự (`utf8mb3`). Khi đó emoji 4 byte không được lưu đúng. Đối với ứng dụng mới, hãy chọn `utf8mb4`.

### Character set không quyết định mọi phép so sánh

Chẳng hạn MySQL với `utf8mb4_0900_ai_ci` có thể coi tên khác nhau về chữ hoa/chữ thường hoặc dấu là tương đương trong phép so sánh. PostgreSQL có cơ chế collation khác; hành vi phụ thuộc collation đang dùng.

Nếu cột chứa **username/mã kỹ thuật cần duy nhất**, hãy xác định chính sách so sánh và chỉ mục duy nhất riêng cho cột đó. Không tự giả định rằng `"Hoa"`, `"hoa"` và `"Hòa"` luôn được xem là ba tên khác nhau ở mọi database.

## 5. Thiết kế bảng mẫu: tên, biệt danh, giới thiệu và ngôn ngữ

Hai lược đồ dưới đây thể hiện cùng một hợp đồng nghiệp vụ. **Chọn một** theo hệ quản trị đang sử dụng. Các lệnh `CREATE TABLE` dành cho database thực hành và giả định bảng chưa tồn tại.

### PostgreSQL

~~~sql
CREATE TABLE customer_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    nickname VARCHAR(40),
    bio TEXT,
    locale_tag VARCHAR(16) NOT NULL DEFAULT 'vi-VN',

    CONSTRAINT ck_profile_display_name
        CHECK (BTRIM(display_name) <> ''),
    CONSTRAINT ck_profile_nickname
        CHECK (nickname IS NULL OR BTRIM(nickname) <> '')
);
~~~

### MySQL 8.4

~~~sql
CREATE TABLE customer_profiles (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    nickname VARCHAR(40) NULL,
    bio TEXT NULL,
    locale_tag VARCHAR(16) NOT NULL DEFAULT 'vi-VN',

    CONSTRAINT ck_profile_display_name
        CHECK (TRIM(display_name) <> ''),
    CONSTRAINT ck_profile_nickname
        CHECK (nickname IS NULL OR TRIM(nickname) <> '')
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
~~~

Giải thích các quyết định:

- **`display_name VARCHAR(80) NOT NULL`:** bắt buộc có chuỗi và chặn chuỗi dài hơn giới hạn cột.
- **`nickname VARCHAR(40) NULL`:** cho phép **`NULL`** để biểu diễn “chưa đặt biệt danh”.
- **`bio TEXT NULL`:** cho phép lưu đoạn văn Unicode; trong ví dụ, `NULL` và `''` là hai trạng thái khác nhau.
- **`locale_tag VARCHAR(16) NOT NULL DEFAULT 'vi-VN'`:** lưu mã ngôn ngữ/vùng ở dạng văn bản. Giá trị mặc định của DB chỉ được dùng khi lệnh INSERT **bỏ qua cột** hoặc yêu cầu `DEFAULT`, không áp dụng khi INSERT chỉ định `NULL`.
- **`CHECK`:** bảo vệ thêm yêu cầu không cho tên/biệt danh toàn dấu cách thông thường. Hàm `TRIM` / `BTRIM` mặc định **không phải bộ lọc mọi loại khoảng trắng Unicode**. Ứng dụng cần kiểm tra bổ sung nếu quy tắc nghiệp vụ coi tab, xuống dòng hoặc các ký tự trắng đặc biệt là rỗng.

Ví dụ chưa thêm ràng buộc `UNIQUE` trên `display_name` vì nhiều người có thể có tên giống nhau. Nếu yêu cầu định danh duy nhất, hãy dùng một trường thích hợp như username/user ID với chính sách collation rõ ràng.

## 6. Dữ liệu mẫu chứa tiếng Việt, Unicode và giá trị rỗng

Lưu script dưới dạng **UTF-8** và thực hiện sau khi bảng đã được tạo:

~~~sql
INSERT INTO customer_profiles
    (display_name, nickname, bio, locale_tag)
VALUES
    ('Nguyễn An', NULL, 'Học Spring Data JDBC 🚀', 'vi-VN'),
    ('Lê Mỹ Linh', 'Linh', '', 'vi-VN'),
    ('東京', NULL, NULL, 'ja-JP');
~~~

Trong cùng bảng có ba trường hợp:

1. `Nguyễn An` có `nickname = NULL` và `bio` chứa emoji.
2. `Lê Mỹ Linh` có biệt danh `Linh` và `bio = ''` (chuỗi rỗng, độ dài 0).
3. `東京` có `nickname = NULL` và `bio = NULL` (không có giá trị được lưu).

Các câu SQL quan sát:

~~~sql
SELECT
    id,
    display_name,
    CHAR_LENGTH(display_name) AS name_characters,
    OCTET_LENGTH(display_name) AS name_bytes,
    nickname,
    bio
FROM customer_profiles
ORDER BY id;

SELECT COUNT(*) AS no_bio_count
FROM customer_profiles
WHERE bio IS NULL;

SELECT COUNT(*) AS empty_bio_count
FROM customer_profiles
WHERE bio = '';
~~~

Khi seed đúng một lần vào bảng trống, hai câu COUNT cuối cùng đều trả về **1**: một hồ sơ có `bio IS NULL`, một hồ sơ có `bio = ''`. `CHAR_LENGTH` đếm ký tự theo DB; `OCTET_LENGTH` đếm byte, nên tên có dấu hoặc ký tự đa byte cho hai con số khác nhau.

Truy vấn phân loại trực tiếp cả ba trạng thái:

~~~sql
SELECT
    display_name,
    CASE
        WHEN bio IS NULL THEN 'NOT_PROVIDED'
        WHEN bio = '' THEN 'EMPTY_STRING'
        ELSE 'HAS_CONTENT'
    END AS bio_state
FROM customer_profiles
ORDER BY id;
~~~

Kết quả phân loại mong đợi: `Nguyễn An = HAS_CONTENT`, `Lê Mỹ Linh = EMPTY_STRING`, `東京 = NOT_PROVIDED`.

## 7. Phân biệt NULL, chuỗi rỗng và chuỗi chỉ có khoảng trắng

| Giá trị trong Java | Dữ liệu SQL có thể lưu | Ý nghĩa ví dụ | Truy vấn |
|---|---|---|---|
| `null` | `NULL` | Chưa nhập giới thiệu | `WHERE bio IS NULL` |
| `""` | `''` | Chủ động để trống giới thiệu | `WHERE bio = ''` |
| `"   "` | Chuỗi chứa dấu cách | Người dùng nhập dấu cách | `WHERE TRIM(bio) = '' AND bio IS NOT NULL` |
| `"Xin chào"` | Văn bản có nội dung | Có giới thiệu | `WHERE bio IS NOT NULL AND bio <> ''` |

Trong PostgreSQL và MySQL, chuỗi rỗng **khác** SQL `NULL`. SQL xử lý `NULL` theo logic ba giá trị: đúng, sai và **unknown**. Vì vậy:

~~~sql
-- ĐÚNG: tìm hàng chưa có giá trị.
SELECT * FROM customer_profiles WHERE bio IS NULL;

-- ĐÚNG: tìm hàng có chuỗi rỗng.
SELECT * FROM customer_profiles WHERE bio = '';

-- SAI VỀ NGỮ NGHĨA: so sánh với NULL bằng toán tử =.
SELECT * FROM customer_profiles WHERE bio = NULL;
~~~

Câu cuối không trả về các bản ghi có `bio NULL` bởi `bio = NULL` cho kết quả `UNKNOWN`. Muốn xét giá trị null phải dùng `IS NULL` hoặc `IS NOT NULL`.

Khi cần giá trị hiển thị mặc định, có thể dùng:

~~~sql
SELECT
    display_name,
    COALESCE(nickname, '(chưa đặt biệt danh)') AS nickname_for_display
FROM customer_profiles;
~~~

`COALESCE` trong truy vấn **không thay đổi giá trị lưu trữ**; nó chỉ trả về một giá trị thay thế khi expression là `NULL`. `COALESCE(nickname, '')` cũng khiến `NULL` hiển thị thành chuỗi rỗng, vì vậy chỉ dùng nếu giao diện thực sự muốn gộp hai trạng thái.

### Quy ước ở tầng API

Giả sử client cập nhật trường `bio`:

- JSON **không có thuộc tính** `bio`: có thể được hiểu là “giữ nguyên” trong một API PATCH.
- JSON có `"bio": null`: có thể được hiểu là “xóa giá trị / chưa cung cấp”.
- JSON có `"bio": ""`: có thể được hiểu là “đặt chuỗi rỗng”.

Đây là **quy ước cần được thiết kế cho API**, không phải một hành vi mặc định do Spring Data JDBC quyết định. Một DTO chỉ có thuộc tính `String bio` sẽ không tự phân biệt được “field vắng mặt” với “field có giá trị null” nếu không có cơ chế ghi nhận field presence.

Đối với `nickname` của bài này, nghiệp vụ chủ động **gộp chuỗi trống/toàn dấu cách thành `null`** trước khi lưu, để dữ liệu nhất quán. Đối với `bio`, ta giữ khác biệt giữa `NULL` và `''`. Hai lựa chọn này có thể cùng tồn tại vì mỗi trường có ý nghĩa riêng.

## 8. Ánh xạ cột chuỗi vào entity Spring Data JDBC

Spring Data JDBC ánh xạ chuỗi văn bản thông thường vào `String`. Nó không yêu cầu JPA `@Entity`, và `@Column` là annotation thuộc **Spring Data Relational**, không phải `jakarta.persistence.Column`.

Ví dụ **`CustomerProfile.java`**:

~~~java
package com.example.demo.profile;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_profiles")
public record CustomerProfile(
    @Id Long id,
    @Column("display_name") String displayName,
    String nickname,
    String bio,
    @Column("locale_tag") String localeTag
) {}
~~~

Ví dụ **`CustomerProfileRepository.java`**:

~~~java
package com.example.demo.profile;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, Long> {

    List<CustomerProfile> findByDisplayName(String displayName);
}
~~~

Giải thích:

- `@Table("customer_profiles")` xác định bảng root của aggregate đơn giản này.
- `@Id` xác định khóa chính. Khi tạo mới, đặt `id = null` và sử dụng entity được trả về bởi `save(...)` để lấy ID đã được sinh.
- `@Column("display_name")` và `@Column("locale_tag")` cho ánh xạ rõ ràng từ tên Java camelCase sang tên cột snake_case. Trường không đánh dấu `@Column` có thể được ánh xạ bằng naming strategy mặc định.
- Trường nullable trong bảng, như `nickname` và `bio`, có thể được biểu diễn bằng `String` mang giá trị Java `null`.
- Phương thức `findByDisplayName(...)` là truy vấn suy diễn từ tên phương thức; cách DB so khớp tên vẫn chịu **collation**, do đó không mặc định là phép so sánh phân biệt chữ hoa hay dấu.

**Điểm rất quan trọng:** annotation `@Column` không tự tạo `VARCHAR(80)`, không tự thêm `NOT NULL` và không tự chuẩn hóa Unicode. Trong bài này, **schema SQL** và **logic nghiệp vụ** chịu trách nhiệm về giới hạn/điều kiện dữ liệu. Nếu dùng công cụ migration như Flyway hoặc Liquibase, hãy quản lý lược đồ có phiên bản thay vì chỉ thay annotation Java.

### Ghi dữ liệu qua repository

~~~java
CustomerProfile incoming = new CustomerProfile(
    null,
    "Đỗ Khánh",
    null,
    "Thử lưu tiếng Việt và emoji 😀",
    "vi-VN"
);

CustomerProfile saved = repository.save(incoming);
Long generatedId = saved.id();

CustomerProfile loaded = repository.findById(generatedId)
    .orElseThrow();

System.out.println(loaded.displayName()); // Đỗ Khánh
~~~

Đoạn mã giả định biến `repository` là một bean `CustomerProfileRepository` đã được inject vào component của Spring Boot. Spring Data JDBC gửi giá trị chuỗi qua JDBC driver bằng cơ chế binding parameter của framework; không tự ghép nội dung tên vào chuỗi SQL.

## 9. Kiểm tra và chuẩn hóa độ dài trước khi lưu

Giới hạn database là lớp bảo vệ cuối. Tầng nghiệp vụ nên phản hồi sớm với thông báo rõ ràng, đồng thời quyết định chính sách về việc loại khoảng trắng đầu/cuối và dạng chuẩn Unicode.

Ví dụ một service xây dựng entity mới:

~~~java
package com.example.demo.profile;

import java.text.Normalizer;
import java.text.Normalizer.Form;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProfileService {

    private final CustomerProfileRepository profiles;

    public ProfileService(CustomerProfileRepository profiles) {
        this.profiles = profiles;
    }

    @Transactional
    public CustomerProfile create(
            String displayName,
            String nickname,
            String bio) {
        String name = requiredName(displayName);
        String optionalNickname = optionalNickname(nickname);

        // Giữ nguyên phân biệt bio == null và bio.equals("").
        CustomerProfile profile = new CustomerProfile(
            null, name, optionalNickname, bio, "vi-VN"
        );
        return profiles.save(profile);
    }

    private static String requiredName(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Name is required");
        }
        String value = Normalizer.normalize(raw.strip(), Form.NFC);
        int codePoints = value.codePointCount(0, value.length());
        if (value.isBlank() || codePoints > 80) {
            throw new IllegalArgumentException(
                "Name must contain 1..80 Unicode code points"
            );
        }
        return value;
    }

    private static String optionalNickname(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String value = Normalizer.normalize(raw.strip(), Form.NFC);
        if (value.isEmpty()) {
            return null;
        }
        if (value.codePointCount(0, value.length()) > 40) {
            throw new IllegalArgumentException(
                "Nickname is too long"
            );
        }
        return value;
    }
}
~~~

**Chính sách minh họa của service:**

- Tên hiển thị bắt buộc có, được loại khoảng trắng đầu/cuối theo quy tắc `String.strip()` và chuẩn hóa NFC.
- Biệt danh toàn dấu trắng được chuyển về `null`.
- Giới hạn được kiểm tra bằng **code point** sau chuẩn hóa, gần với ngữ nghĩa độ dài ký tự của `VARCHAR` hơn `String.length()`.
- `bio` được giữ nguyên để bảo toàn khác biệt giữa “chưa nhập” và “chuỗi trống”; nếu sản phẩm có giới hạn độ dài hoặc nội dung, cần thêm rule riêng.

`String.strip()` và `String.isBlank()` sử dụng định nghĩa whitespace của Java. Chúng **không bao phủ mọi ký tự có biểu diễn giống khoảng trắng**, như một số dạng non-breaking space. Nếu yêu cầu làm sạch dữ liệu nghiêm ngặt hơn, phải quy định bộ ký tự cần xử lý. Không nên tự ý xóa mọi whitespace ở giữa tên, vì khoảng trắng có thể là nội dung hợp lệ.

Đối với trường yêu cầu giới hạn **số ký tự hiển thị cho người dùng**, code point vẫn chưa đủ (emoji ghép chứa nhiều code point). Hãy chọn thuật toán đo grapheme phù hợp với sản phẩm; giới hạn cột SQL và giới hạn giao diện có thể là **hai ngưỡng khác nhau**.

### Tính byte UTF-8 nếu giới hạn lưu trữ yêu cầu

~~~java
import java.nio.charset.StandardCharsets;

String bio = "Học Spring Data JDBC 🚀";
int utf8Bytes = bio.getBytes(StandardCharsets.UTF_8).length;
System.out.println(utf8Bytes);
~~~

Đối với cột MySQL `TEXT`, giới hạn byte có thể quan trọng hơn số code point. Với dữ liệu đầu vào dài, ứng dụng có thể cần kiểm tra cả **ngưỡng nghiệp vụ** lẫn **ngưỡng kỹ thuật** của kiểu cột đang dùng.

## 10. Cấu hình kết nối Spring Boot và giữ UTF-8 xuyên suốt

Phụ thuộc Gradle cho Spring Data JDBC và driver cơ sở dữ liệu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'

    // Chọn driver của cơ sở dữ liệu đang dùng.
    runtimeOnly 'org.postgresql:postgresql'
    // Hoặc:
    // runtimeOnly 'com.mysql:mysql-connector-j'
}
~~~

Ví dụ **`application.yml`** cho PostgreSQL local:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/jdbc_lab
    username: jdbc_user
    password: localdev
  sql:
    init:
      mode: never
~~~

Khi dùng MySQL, đổi URL thành `jdbc:mysql://localhost:3306/jdbc_lab` và sử dụng driver MySQL. Giá trị `localdev` chỉ là mật khẩu ví dụ cho môi trường học; ứng dụng thực tế nên nhận thông tin kết nối từ biến môi trường hoặc cơ chế quản lý bí mật.

`spring.sql.init.mode: never` cho biết schema và seed sẽ được chạy riêng bằng SQL/migration thay vì để ứng dụng tự chạy lại mỗi lần khởi động. Đối với môi trường dự án thực tế, cấu hình khởi tạo phụ thuộc cách bạn tổ chức migration.

**Lưu ý về Unicode:** JDBC driver và database chịu trách nhiệm truyền `String` đúng encoding. Thông thường không cần gọi `new String(bytes, UTF_8)` khi đã có dữ liệu Java `String`. Nếu chuỗi bị lỗi font hoặc thành ký tự `?`, kiểm tra tuần tự nguồn HTTP/JSON, file SQL, encoding database và charset kết nối. Việc chuyển byte nhiều lần sai encoding có thể làm hỏng dữ liệu trước khi đến repository.

## 11. Dữ liệu rỗng và quá dài sẽ tạo lỗi gì?

Giả sử thực hiện các lệnh sau trong database thực hành:

~~~sql
-- Bị chặn: display_name bắt buộc, không được NULL.
INSERT INTO customer_profiles (display_name, locale_tag)
VALUES (NULL, 'vi-VN');

-- Bị chặn: chuỗi trống không đáp ứng CHECK của display_name.
INSERT INTO customer_profiles (display_name, locale_tag)
VALUES ('', 'vi-VN');

-- Bị chặn: 81 ký tự ASCII vượt quá VARCHAR(80).
INSERT INTO customer_profiles (display_name, locale_tag)
VALUES (
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    'vi-VN'
);

-- Hợp lệ: nickname không có, bio là chuỗi rỗng.
INSERT INTO customer_profiles (display_name, nickname, bio, locale_tag)
VALUES ('Trần Lan', NULL, '', 'vi-VN');
~~~

Ba lệnh đầu được viết **cố ý để gây lỗi**: hãy chạy độc lập từng câu nếu thực hành, không dán cả nhóm như một migration. Thông báo cụ thể khác nhau giữa PostgreSQL và MySQL: có thể là lỗi `NOT NULL`, `CHECK constraint` hoặc lỗi `data too long for column`.

Từ phía Java, Spring sẽ thường chuyển lỗi driver khi ghi dữ liệu thành ngoại lệ thuộc nhóm truy cập dữ liệu (ví dụ `DataIntegrityViolationException`), nhưng loại ngoại lệ chính xác phụ thuộc driver, dialect và cách framework dịch lỗi. Không nên dựa vào một thông điệp SQL cụ thể như hợp đồng API; hãy kiểm tra dữ liệu đầu vào và xử lý lỗi có kiểm soát.

### Chú ý khi thay đổi chiều dài cột

Khi nghiệp vụ đổi giới hạn tên từ 80 lên 120, **không chỉ sửa hằng số Java**. Cần migration cho database:

~~~sql
-- PostgreSQL
ALTER TABLE customer_profiles
ALTER COLUMN display_name TYPE VARCHAR(120);
~~~

~~~sql
-- MySQL
ALTER TABLE customer_profiles
MODIFY COLUMN display_name VARCHAR(120) NOT NULL;
~~~

Cập nhật cả validation, thông điệp API, tài liệu và cơ chế hiển thị. Nếu **thu hẹp** cột từ 120 xuống 80, cần đánh giá dữ liệu hiện có trước khi thực hiện migration vì bản ghi dài có thể khiến migration thất bại hoặc bị cắt tùy cấu hình SQL mode/DB.

## 12. So sánh chuỗi và tìm kiếm: case, dấu và khoảng trắng

Không thể xác định chính sách so sánh chỉ từ kiểu Java `String` hoặc tên cột `VARCHAR`. Phép tìm kiếm:

~~~java
List<CustomerProfile> results =
    repository.findByDisplayName("Nguyễn An");
~~~

được thực thi tại database và chịu quy tắc so sánh của cột/collation. Một số điểm cần quyết định:

- **Phân biệt chữ hoa/chữ thường:** `"An"` có được xem là giống `"an"` không?
- **Phân biệt dấu:** `"Hoa"` và `"Hòa"` có là hai giá trị khác nhau không?
- **Khoảng trắng đầu/cuối:** trước khi lưu, có chuẩn hóa thành một dạng hay không?
- **Unicode normalization:** `"é"` và `"e\u0301"` được xử lý nhất quán không?
- **So khớp cho định danh duy nhất:** cần một dạng canonical key hoặc collation phù hợp; không mặc định dùng tên hiển thị làm khóa duy nhất.

Ví dụ MySQL `utf8mb4_0900_ai_ci` có kiểu so sánh không phân biệt dấu và chữ hoa; PostgreSQL có nhiều lựa chọn collation và cách diễn giải khác. Nếu yêu cầu chính xác tuyệt đối theo byte/code point, hãy xác định chiến lược so sánh riêng thay vì tin vào collation mặc định của hệ thống.

Tương tự, `LIKE` dùng các ký tự `%` và `_` theo cú pháp SQL để tạo mẫu tìm kiếm. Khi nhận chuỗi từ người dùng, dùng truy vấn có **tham số bind** và escaping phù hợp thay vì nối trực tiếp đầu vào vào SQL.

## 13. Những lỗi thường gặp trong Spring Data JDBC

| Lỗi thiết kế/triển khai | Điều có thể xảy ra | Cách xử lý |
|---|---|---|
| Dùng `String.length()` để dự đoán số ký tự DB với emoji | Java đếm UTF-16 code unit, khác code point | Xác định mục tiêu đo; dùng `codePointCount` hoặc grapheme theo ngữ cảnh |
| Chọn MySQL `utf8mb3`/cấu hình `utf8` cũ | Emoji 4 byte không lưu được | Dùng `utf8mb4` cho charset bảng/connection |
| Dùng `CHAR(n)` cho tên có độ dài biến đổi | Không mong muốn về đệm khoảng trắng và so sánh | Dùng `VARCHAR(n)` hoặc `TEXT` theo yêu cầu |
| Coi `NULL` giống `''` | Mất thông tin “chưa nhập” so với “đã xóa” | Quy định rõ ý nghĩa từng trạng thái và API |
| Truy vấn `= NULL` | Không tìm được hàng có giá trị NULL | Dùng `IS NULL` |
| Chỉ dựa vào `@Column` để tạo độ dài/NOT NULL | Schema không tự có ràng buộc mong muốn | Viết DDL/migration và validation |
| Cho phép chuỗi toàn dấu trắng ở cột tên bắt buộc | Bản ghi không có nội dung hữu ích | Kiểm tra domain/service và CHECK phù hợp |
| Giới hạn TEXT theo số ký tự nhưng bỏ qua byte MySQL | Vượt giới hạn kiểu TEXT khi ký tự đa byte | Kiểm tra byte/kiểu cột theo nhu cầu |
| Tin rằng so sánh chuỗi luôn giống Java `equals` | Collation có thể không phân biệt dấu/case | Chọn collation và luật định danh cụ thể |
| Ghép trực tiếp tên người dùng vào SQL | Nguy cơ SQL injection và lỗi escaping | Dùng repository query với tham số bind |

## 14. Bài thực hành tự kiểm tra

1. Chạy `SELECT CHAR_LENGTH('🚀'), OCTET_LENGTH('🚀');` trên PostgreSQL hoặc MySQL có UTF-8/utf8mb4. Giải thích vì sao kết quả lần lượt là `1` và `4`.
2. Nạp ba hồ sơ mẫu. Truy vấn riêng hàng có `bio IS NULL` và `bio = ''`. Tại sao hai tập kết quả khác nhau?
3. Thử thêm `display_name` chứa 81 chữ `A`, rồi thử thêm tên chỉ gồm dấu cách. Xác định cột/ràng buộc nào chặn mỗi trường hợp.
4. Dùng Java in `length()` và `codePointCount(...)` cho `"🚀"`, `"e\u0301"` và `"👩‍💻"`. So sánh với `CHAR_LENGTH` của database.
5. Xây dựng chức năng tạo profile qua `ProfileService.create(...)`; thử `nickname = null`, `nickname = ""` và `nickname = "   "`. Kết quả lưu trong cả ba trường hợp theo quy tắc của service là gì?
6. Kiểm tra MySQL collation (nếu dùng MySQL) và thử truy vấn tên với khác biệt chữ hoa/dấu. Kết quả cho thấy tại sao chính sách tìm kiếm không được suy ra từ `String.equals`?
7. Đề xuất cách cập nhật API PATCH để phân biệt **field không xuất hiện**, **field có null** và **field có chuỗi rỗng** khi cập nhật `bio`.

Ví dụ câu SQL đếm ba trạng thái của `bio`:

~~~sql
SELECT
    SUM(CASE WHEN bio IS NULL THEN 1 ELSE 0 END) AS missing_bio,
    SUM(CASE WHEN bio = '' THEN 1 ELSE 0 END) AS empty_bio,
    SUM(CASE WHEN bio IS NOT NULL AND bio <> '' THEN 1 ELSE 0 END)
        AS nonempty_bio
FROM customer_profiles;
~~~

Với dữ liệu mẫu đầu tiên và chưa ghi thêm hàng nào, kết quả mong đợi là **`missing_bio = 1`, `empty_bio = 1`, `nonempty_bio = 1`**.

Điều cần hiểu khi thiết kế chuỗi trong Spring Data JDBC là: **Java `String`, Unicode, chiều dài SQL và ý nghĩa dữ liệu rỗng không phải cùng một khái niệm**. Hãy chọn kiểu cột dựa trên nội dung, dùng UTF-8/utf8mb4 để lưu Unicode đúng, xác định quy tắc giới hạn và chuẩn hóa trước khi ghi, đồng thời giữ phân biệt `NULL` với chuỗi rỗng ở những trường hợp nghiệp vụ cần.
