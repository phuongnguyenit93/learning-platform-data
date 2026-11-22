# Phiên bản chính, phiên bản phụ và cách đọc tài liệu đúng phiên bản PostgreSQL

Khi học hoặc vận hành PostgreSQL, một câu SQL có thể chạy trên máy này nhưng báo lỗi trên máy khác dù cả hai đều dùng PostgreSQL. Nguyên nhân thường không nằm ở cú pháp viết sai, mà ở **khác biệt phiên bản**: chức năng mới chỉ có từ một phiên bản chính nhất định, tài liệu đang mở mô tả phiên bản khác, hoặc môi trường đã cập nhật bản sửa lỗi mà môi trường còn lại chưa có.

PostgreSQL có quy tắc đánh số **phiên bản chính** (*major version*) và **phiên bản phụ** (*minor version*) rất rõ. Hiểu quy tắc này giúp trả lời những câu hỏi thực tế:

- Máy chủ đang chạy PostgreSQL phiên bản nào? Có giống phiên bản của công cụ `psql` trong máy cá nhân không?
- Khi đọc một ví dụ dùng `MERGE`, có chắc máy chủ của mình hỗ trợ không?
- Nâng từ `16.4` lên `16.5` khác gì nâng từ `16.4` lên `17.0`?
- Một tài liệu mang nhãn `current` trên website có phù hợp với máy chủ sản xuất không?
- Khi gặp lỗi sau nâng cấp, cần đọc release notes của bản nào, kiểm tra extension nào và tìm hướng dẫn nâng cấp nào?

Trong bài học này, các số `9.6.24`, `15.8`, `16.4`, `17.2`, `17.5` hoặc `18.1` được dùng **làm ví dụ minh họa cách đánh số**, không phải tuyên bố đâu là phiên bản mới nhất tại thời điểm đọc. Trạng thái phát hành và hỗ trợ thực tế phải được kiểm tra trên website chính thức của dự án PostgreSQL.

## 1. Vì sao phiên bản PostgreSQL quan trọng?

Một hệ quản trị cơ sở dữ liệu không đứng yên. Qua từng phiên bản, PostgreSQL thay đổi hoặc bổ sung:

1. **Ngôn ngữ SQL và tính năng:** cú pháp, kiểu dữ liệu, hàm, quyền truy cập, cơ chế lập chỉ mục, partitioning, JSON, các công cụ truy vấn.
2. **Bộ tối ưu và hành vi thực thi:** lựa chọn kế hoạch truy vấn, thống kê, cơ chế song song, cách áp dụng các biểu thức truy vấn.
3. **Khả năng quản trị và vận hành:** sao lưu, phục hồi, giám sát, replication, nâng cấp, thông số cấu hình.
4. **Sửa lỗi và bảo mật:** bản vá có thể tác động tới cách máy chủ kiểm tra đầu vào, quyền truy cập, tính đúng đắn hoặc tính ổn định.
5. **Tương thích hệ sinh thái:** extension, driver JDBC, thư viện client, công cụ migration và nền tảng hệ điều hành.

Ví dụ, `MERGE` được đưa vào PostgreSQL từ **phiên bản chính 15**. Một bài hướng dẫn dùng `MERGE` dành cho PostgreSQL 15 trở lên không thể được áp dụng nguyên văn cho PostgreSQL 14. Ngược lại, một câu `SELECT` đơn giản thường vẫn hoạt động qua nhiều phiên bản nhưng không đủ để kết luận mọi câu SQL và tính năng đều tương thích.

Do đó, trước khi sao chép lệnh từ tài liệu, cần xác định **phiên bản máy chủ thực sự xử lý lệnh đó**.

## 2. Phân biệt major version và minor version

PostgreSQL thay đổi quy tắc đặt tên phiên bản từ **PostgreSQL 10**. Đây là một khác biệt rất quan trọng khi đọc lịch sử tài liệu.

### 2.1. Từ PostgreSQL 10 trở đi

Phiên bản có dạng:

```text
MAJOR.MINOR

17.5
│  └── minor version = 5
└───── major version = 17
```

Ví dụ:

| Phiên bản | Major | Minor | Diễn giải |
| --- | ---: | ---: | --- |
| `15.8` | 15 | 8 | Một bản sửa lỗi thuộc nhánh phiên bản chính 15. |
| `16.4` | 16 | 4 | Phiên bản chính 16, bản phụ 4. |
| `16.5` | 16 | 5 | Vẫn là nhánh 16, bản phụ mới hơn `16.4`. |
| `17.2` | 17 | 2 | Phiên bản chính 17, bản phụ 2. |
| `18.1` | 18 | 1 | Phiên bản chính 18, bản phụ 1. |

Trong cách đánh số này, **chuyển `16.4 → 16.5` là cập nhật minor**, còn **`16.4 → 17.0` là nâng cấp major**.

Một bản mới thuộc cùng nhánh major thường tập trung vào sửa lỗi và bảo mật, trong khi một major mới có thể bổ sung tính năng, thay đổi hành vi hoặc định dạng lưu trữ yêu cầu quy trình nâng cấp rõ ràng.

### 2.2. Trước PostgreSQL 10

Các phiên bản cũ dùng dạng **`MAJOR_MAJOR.MINOR` theo ba thành phần**, trong đó **hai số đầu tạo thành major version**:

```text
9.6.24
│ │  └── minor version = 24
└─┴───── major version = 9.6
```

Ví dụ:

| Phiên bản | Major đúng | Minor đúng |
| --- | --- | ---: |
| `9.4.26` | 9.4 | 26 |
| `9.5.25` | 9.5 | 25 |
| `9.6.24` | 9.6 | 24 |
| `10.0` | 10 | 0 |
| `10.23` | 10 | 23 |

Với PostgreSQL 9.6, đừng nói `9` là major và `6` là minor. Theo quy tắc cũ, **`9.5 → 9.6` là nâng major**, còn **`9.6.23 → 9.6.24` là cập nhật minor**.

Sau PostgreSQL 10, con số đầu tiên chính là major. Không có quy tắc chung rằng “phần sau dấu chấm đầu tiên luôn là minor” cho toàn bộ lịch sử PostgreSQL.

### 2.3. Không xem version như số thập phân

Chuỗi phiên bản không phải số thực để đem so sánh như `16.10` với `16.9` theo phép tính thập phân. Theo thứ tự thành phần version:

```text
16.9  < 16.10
```

vì minor `10` mới hơn minor `9`. Hệ thống kiểm tra phiên bản nên phân tích theo các thành phần version hoặc dùng giá trị số được PostgreSQL cung cấp, không ép chuỗi `'16.10'` thành số thực `16.1`.

## 3. Major release và minor release khác nhau về mục tiêu

### 3.1. Major release: tính năng và thay đổi có thể ảnh hưởng ứng dụng

Một phiên bản major mới có thể chứa:

- Tính năng SQL hoặc đối tượng database mới.
- Khả năng truy vấn và tối ưu hóa mới.
- Những thay đổi về cấu hình mặc định, quản trị, replication hoặc logging.
- Những thay đổi hành vi buộc cần xem xét tương thích ngược.
- Thay đổi định dạng dữ liệu nội bộ và cách nâng cấp database cluster.

Vì thế, khi lên kế hoạch `16 → 17`, đội vận hành không chỉ hỏi “máy chủ có khởi động được không?” mà còn phải kiểm tra:

1. Release notes của PostgreSQL 17 và các điểm **migration**.
2. Các câu SQL/ORM có còn hoạt động đúng không.
3. Extension có tương thích PostgreSQL 17 không.
4. Quy trình chuyển dữ liệu sang major mới.
5. Kế hoạch rollback, backup và diễn tập khôi phục.

### 3.2. Minor release: bản vá trong cùng nhánh major

Một bản minor mới thường tập trung vào:

- Sửa lỗi ảnh hưởng kết quả hoặc tính ổn định.
- Sửa lỗ hổng bảo mật.
- Khắc phục hành vi không đúng đã được phát hiện.
- Những điều chỉnh cần thiết để duy trì một nhánh major.

Ví dụ `16.4 → 16.5` là **cập nhật minor**. Về nguyên tắc, PostgreSQL giữ khả năng tương thích của nhánh major để việc cập nhật minor không đòi hỏi chuyển đổi định dạng dữ liệu bằng `pg_upgrade` hoặc dump/restore toàn bộ database.

Điều đó **không có nghĩa cập nhật minor không bao giờ có tác động**. Một bản sửa lỗi có thể làm thay đổi kết quả của trường hợp trước đây xử lý sai, bản vá bảo mật có thể siết kiểm tra quyền, và release notes đôi khi có chỉ dẫn bổ sung. Vì vậy, nên đọc release notes của chính bản minor sẽ cài đặt.

### 3.3. Bảng so sánh

| Tiêu chí | Minor update | Major upgrade |
| --- | --- | --- |
| Ví dụ | `16.4 → 16.5` | `16.4 → 17.0` |
| Mục đích chính | Sửa lỗi, bản vá bảo mật | Tính năng mới, thay đổi lớn và sửa lỗi |
| Nhánh major | Không đổi | Thay đổi |
| Định dạng lưu trữ | Thông thường giữ tương thích trong cùng major | Có thể thay đổi |
| Cần `pg_upgrade`? | Thông thường không | Cần phương án nâng major như `pg_upgrade`, dump/restore hoặc phương án phù hợp khác |
| Cần đọc release notes? | Có, đặc biệt chú ý lỗi và hướng dẫn bản vá | Có, gồm phần thay đổi và migration |
| Mức kiểm thử | Kiểm thử hồi quy và vận hành phù hợp | Kiểm thử tính tương thích, hiệu năng, extension, migration đầy đủ hơn |
| Có phải khởi động lại server? | Thường có khi thay thế PostgreSQL binaries theo quy trình cài đặt | Có, cùng quá trình chuyển đổi sang major mới |

Một bản major và minor đều có thể quan trọng đối với bảo mật. Không nên bỏ qua cập nhật minor chỉ vì nó “không thêm tính năng”.

## 4. Xác định phiên bản máy chủ đang chạy bằng SQL

Đây là bước đầu tiên trước khi chọn tài liệu.

### 4.1. SHOW server_version

Kết nối tới đúng server PostgreSQL rồi chạy:

```sql
SHOW server_version;
```

Một kết quả minh họa có thể là:

```text
 server_version
----------------
 16.4
```

Trong một số bản phân phối, chuỗi có thể kèm thông tin gói cài đặt hoặc nhà cung cấp. Phần cần nhận diện để chọn tài liệu là **major version PostgreSQL**, trong ví dụ là `16`.

### 4.2. SELECT version()

```sql
SELECT version();
```

Hàm này có thể trả chuỗi dài, ví dụ chứa PostgreSQL version, kiến trúc hệ điều hành, compiler và thông tin build. Nó hữu ích khi chẩn đoán môi trường, nhưng không thuận tiện bằng `SHOW server_version` nếu chỉ cần một số phiên bản.

Ví dụ hình thức kết quả:

```text
PostgreSQL 16.4 on x86_64-..., compiled by ..., 64-bit
```

Nội dung chính xác phụ thuộc máy và cách PostgreSQL được đóng gói.

### 4.3. server_version_num: số nguyên phục vụ so sánh

PostgreSQL còn cung cấp biến:

```sql
SHOW server_version_num;
```

Ví dụ đối với `16.4`, kết quả là:

```text
160004
```

Với PostgreSQL 10 trở đi, cấu trúc số này có thể hiểu theo cách tổng quát:

```text
major * 10000 + minor

16.4  -> 16 * 10000 + 4 = 160004
17.5  -> 17 * 10000 + 5 = 170005
```

Đối với các phiên bản cũ trước 10, số được mã hóa theo quy tắc ba thành phần tương ứng, ví dụ `9.6.24 → 90624`. Do đó, không nên tự áp công thức dành cho PG10+ lên mọi phiên bản lịch sử.

Trong SQL, có thể dùng:

```sql
SELECT
    current_setting('server_version') AS server_version,
    current_setting('server_version_num')::integer AS server_version_num;
```

Ví dụ dùng version để quyết định một chức năng có tồn tại hay không:

```sql
SELECT
    current_setting('server_version_num')::integer >= 150000
        AS supports_merge_since_pg15;
```

Biểu thức trả `true` trên PostgreSQL 15+ và `false` trên các major trước 15. Đây chỉ là kiểm tra **điều kiện phiên bản tối thiểu**, không thay thế kiểm tra quyền, extension, cấu hình và cú pháp thực tế của ứng dụng.

### 4.4. Xác nhận đang kết nối đúng database và server

Với nhiều môi trường như local, test, staging và production, cùng một lệnh `SHOW server_version` có thể trả nhiều kết quả khác nhau. Nên ghi nhận thông tin kết nối cùng phiên bản:

```sql
SELECT
    current_database() AS database_name,
    current_user AS connected_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version;
```

Nếu kết nối qua Unix-domain socket, một số giá trị địa chỉ/cổng TCP có thể là `NULL`. Đây không phải bằng chứng server lỗi; hãy sử dụng thông tin kết nối của client hoặc công cụ quản lý tương ứng.

Trong `psql`, lệnh:

```text
\conninfo
```

giúp xem client đang kết nối đến database, user, host hoặc socket nào.

> **Nguyên tắc:** Chỉ xác nhận phiên bản sau khi đã chắc chắn câu SQL đang chạy trên **chính instance cần học, triển khai hoặc chẩn đoán**.

## 5. Phân biệt phiên bản PostgreSQL Server và các công cụ client

Một máy phát triển có thể cài nhiều thành phần PostgreSQL, mỗi thành phần có phiên bản riêng:

| Thành phần | Lệnh/cách quan sát | Ý nghĩa |
| --- | --- | --- |
| PostgreSQL Server | `SHOW server_version;` | Phiên bản engine thực thi SQL và lưu dữ liệu. |
| `psql` | `psql --version` trong terminal | Phiên bản chương trình dòng lệnh trên máy đang gọi. |
| `pg_dump` | `pg_dump --version` | Phiên bản công cụ dump. |
| `pg_restore` | `pg_restore --version` | Phiên bản công cụ restore archive. |
| `postgres` executable | `postgres --version` khi được phép truy cập binary | Phiên bản binary cài đặt, không chắc là server đang kết nối. |
| PostgreSQL JDBC Driver | Phiên bản dependency như `org.postgresql:postgresql` | Phiên bản driver Java, có vòng đời riêng với PostgreSQL Server. |
| Extension, ví dụ PostGIS | `SELECT extname, extversion FROM pg_extension;` | Phiên bản extension cài trong database, không phải phiên bản server. |

Ví dụ:

```bash
psql --version
pg_dump --version
```

Trên máy lập trình viên, `psql --version` có thể trả `psql (PostgreSQL) 17.2`, trong khi sau khi kết nối vào server:

```sql
SHOW server_version;
-- Ví dụ: 16.4
```

Không có mâu thuẫn: **client là 17.2, server là 16.4**. Khi chọn tài liệu SQL về tính năng mà server hỗ trợ, phải ưu tiên tài liệu **PostgreSQL 16**, không chọn PostgreSQL 17 chỉ vì máy cài `psql` 17.

### 5.1. Vì sao phiên bản pg_dump cần được chú ý?

Công cụ sao lưu logic có thể gặp giới hạn tương thích khác với `psql`:

- `pg_dump` thông thường có thể sao lưu từ một số server **cũ hơn** phiên bản của chính công cụ.
- `pg_dump` từ một major **cũ hơn server** không được kỳ vọng hỗ trợ đầy đủ cấu trúc/cú pháp mới của server đó và có thể từ chối thao tác.
- Khi lập kế hoạch backup/restore, chọn bộ công cụ được PostgreSQL hỗ trợ cho **phiên bản nguồn và đích**, rồi chạy thử restore thật.

Ví dụ, máy quản trị có `pg_dump` 16 mà server đang chạy PostgreSQL 17 là cấu hình cần kiểm tra ngay; đừng giả định dump thành công chỉ vì `psql` vẫn đăng nhập được.

### 5.2. Extension có phiên bản riêng

```sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
```

Ví dụ có thể thấy:

```text
 extname  | extversion
----------+-----------
 plpgsql  | 1.0
 ...
```

`extversion` của extension không phải phiên bản PostgreSQL Server. Khi nâng major, cần xác nhận extension và binary của extension hỗ trợ major mới. Một số extension còn cần bước `ALTER EXTENSION ... UPDATE` theo quy trình tương thích của chính extension; không thực hiện tùy tiện nếu chưa đọc tài liệu của extension.

Trong Java, PostgreSQL JDBC driver được phát hành theo vòng đời riêng. Một số tính năng giao thức hoặc kiểu dữ liệu có thể yêu cầu driver đủ mới, nhưng phiên bản driver **không xác định** server có hỗ trợ câu `MERGE` hay một tính năng SQL khác.

## 6. Đọc tài liệu PostgreSQL đúng phiên bản

Tài liệu PostgreSQL chính thức được tổ chức theo **major version**. Website dự án cung cấp tài liệu ở các đường dẫn có dạng:

```text
https://www.postgresql.org/docs/current/
https://www.postgresql.org/docs/17/
https://www.postgresql.org/docs/16/
https://www.postgresql.org/docs/15/
https://www.postgresql.org/docs/9.6/
```

Các đường dẫn này giúp hiểu một quy tắc quan trọng:

- `/docs/current/` trỏ tới **tài liệu của phiên bản major hiện được dự án xem là current**. Mục tiêu của đường dẫn này có thể thay đổi khi có major mới.
- `/docs/16/` là tài liệu gắn với **major 16**. Dù một major mới được phát hành, đường dẫn gắn số major vẫn phù hợp để đọc cho máy chủ 16.
- `/docs/9.6/` minh họa cách truy cập tài liệu cho major **9.6** theo cách đánh số cũ.

**Nếu server đang chạy 16.4, hãy mở `https://www.postgresql.org/docs/16/` trước.** Nếu server đang chạy 17.5, hãy mở `https://www.postgresql.org/docs/17/`. Khi muốn tìm một tính năng chỉ có ở major mới, có thể xem tài liệu mới hơn để tìm hiểu nhưng phải tách rõ phần chưa được máy chủ hiện tại hỗ trợ.

### 6.1. Major version trong URL là điều quyết định

Ví dụ có hai trang hướng dẫn `SELECT`:

```text
https://www.postgresql.org/docs/current/sql-select.html
https://www.postgresql.org/docs/16/sql-select.html
```

Trang thứ nhất có thể mô tả cú pháp của major khác, nếu `current` đã thay đổi. Trang thứ hai được neo cố định vào nhánh 16.

Đối với một tài liệu kỹ thuật nội bộ phải hoạt động lâu dài, nên **liên kết đến URL có số major rõ ràng** thay vì chỉ dùng `current`, trừ khi nội dung cố ý bàn về phiên bản mới nhất.

### 6.2. Tài liệu theo major không đồng nghĩa với ảnh chụp của từng minor

Trang `/docs/16/` không nhất thiết là một ảnh chụp bất biến của đúng `16.4`. Tài liệu của một nhánh major có thể được cập nhật trong quá trình duy trì và phát hành các bản minor.

Vì vậy:

- Để hiểu **cú pháp và chức năng chính**: dùng bộ tài liệu của major đang chạy.
- Để hiểu **một lỗi đã được sửa ở minor nào**: đọc release notes tương ứng.
- Để tái dựng **hành vi ở một minor cũ**: đối chiếu release notes giữa minor đó và các minor tiếp theo; không giả định trang hướng dẫn hiện tại của nhánh major phản ánh mọi chi tiết cũ.

Đây là lý do cần phân biệt hai loại tài liệu: **manual theo major** và **release notes theo bản phát hành**.

## 7. Tìm đúng phần tài liệu cần đọc

Khi mở manual của đúng major, có thể tìm thông tin ở các phần:

| Nhu cầu | Phần tài liệu nên tìm | Ví dụ |
| --- | --- | --- |
| Cú pháp câu SQL | SQL Commands / SQL Language | `SELECT`, `INSERT`, `MERGE`, `CREATE TABLE`. |
| Kiểu dữ liệu và hàm | Data Types, Functions and Operators | `timestamp`, `jsonb`, `date_trunc`. |
| Transaction và locking | Concurrency Control | Isolation levels, MVCC, row locking. |
| Index và hiệu năng | Indexes, Performance Tips | B-tree, `EXPLAIN`, thống kê. |
| Cấu hình máy chủ | Server Configuration | `postgresql.conf`, memory, logging. |
| Công cụ client | Client Applications | `psql`, `pg_dump`, `pg_restore`. |
| Nâng cấp | Upgrading a PostgreSQL Cluster, `pg_upgrade` | Phương pháp chuyển major. |
| Thay đổi phiên bản | Release Notes | Tính năng mới, bản vá, sửa lỗi và yêu cầu migration. |

Một số URL minh họa được neo vào major 16:

```text
Manual major 16:
https://www.postgresql.org/docs/16/

SELECT trong major 16:
https://www.postgresql.org/docs/16/sql-select.html

Ứng dụng psql trong major 16:
https://www.postgresql.org/docs/16/app-psql.html

pg_upgrade trong major 16:
https://www.postgresql.org/docs/16/pgupgrade.html
```

Để chuyển tài liệu SQL từ major 16 sang major 17, thường có thể chọn cùng một chủ đề trên trang điều hướng tài liệu của major 17. Tuy nhiên, **không được giả định mọi trang hoặc tính năng đều tồn tại ở mọi major**, bởi cấu trúc mục lục và chức năng có thể thay đổi.

### Cách đọc một trang có ví dụ SQL

Trước khi sử dụng ví dụ:

1. Xem nhãn major trong URL hoặc bộ chọn version của website.
2. Xác nhận lệnh có được giới thiệu **từ phiên bản nào**.
3. Tìm phần **Notes**, **Compatibility** hoặc giới hạn của tính năng.
4. Nếu gặp hành vi khác tài liệu, tra release notes của minor đang chạy và các bản vá liên quan.
5. Khi sử dụng trong dự án Java/ORM, kiểm tra thêm SQL sinh ra từ framework và phiên bản PostgreSQL dialect của ORM.

Đừng chỉ đọc dòng cú pháp rồi suy ra mọi tùy chọn đều dùng được ở máy chủ đang vận hành.

## 8. Release notes: nơi đọc thay đổi chính xác của bản phát hành

Manual giúp hiểu cách dùng tính năng. **Release notes** trả lời những câu hỏi khác:

- Bản major mới thêm hoặc thay đổi chức năng gì?
- Bản minor vừa phát hành sửa lỗi nào, nhất là lỗi bảo mật?
- Có bước chuyển đổi bổ sung, reindex hoặc điều chỉnh cấu hình nào được khuyến nghị không?
- Một hành vi từng là lỗi có được sửa ở bản này hay chưa?
- Có điểm nào ảnh hưởng đến tính tương thích hoặc vận hành không?

Ví dụ đường dẫn release notes gắn với một bản phát hành cụ thể có dạng:

```text
https://www.postgresql.org/docs/17/release-17-5.html
```

Ở đây `17` là **nhánh tài liệu major**, còn `17-5` trong tên trang chỉ **bản phát hành 17.5**. Dùng đường dẫn này như ví dụ về cách nhận biết cấu trúc URL của release notes, không suy ra 17.5 là phiên bản mới nhất.

### 8.1. Khi nâng minor, nên đọc những gì?

Giả sử cần cập nhật `16.4 → 16.5`:

1. Đọc release notes của `16.5`.
2. Tìm các mục liên quan lỗi bảo mật và lỗi có thể ảnh hưởng đến workload hiện tại.
3. Kiểm tra yêu cầu bổ sung của bản vá, extension hoặc hệ điều hành.
4. Xác định liệu có thao tác đặc biệt cần thực hiện hay không.
5. Thực hiện cập nhật theo hướng dẫn đóng gói và kiểm chứng `SHOW server_version` sau khi server khởi động lại.

Nếu đang ở `16.2` và muốn lên `16.5`, không chỉ đọc đúng một trang rồi quên những thay đổi trung gian. Cần xét các release notes **16.3, 16.4 và 16.5**, nhất là những lưu ý có thể áp dụng cho đường nâng cấp đang thực hiện.

### 8.2. Khi nâng major, cần đọc thêm phần Migration

Giả sử dự kiến `16.x → 17.x`. Ngoài danh sách tính năng mới, phải đọc phần **Migration to Version 17** hoặc nội dung tương đương trong release notes major 17, cùng hướng dẫn `pg_upgrade` hoặc phương pháp chuyển dữ liệu mà đội vận hành chọn.

Một tính năng mới có thể hấp dẫn, nhưng những nội dung như thay đổi mặc định, cấu hình bị đổi tên, extension chưa tương thích hoặc khác biệt trong bộ tối ưu có thể ảnh hưởng lớn hơn đến triển khai thực tế.

## 9. Minh họa: sử dụng tính năng chỉ có ở một major nhất định

### 9.1. MERGE trong PostgreSQL 15 trở lên

`MERGE` là một ví dụ rõ ràng về việc **manual mới không nhất thiết phù hợp server cũ**. Tính năng này được đưa vào PostgreSQL từ major 15.

Ví dụ:

```sql
CREATE TABLE stock_balances (
    sku text PRIMARY KEY,
    available_quantity integer NOT NULL
);

CREATE TABLE stock_changes (
    sku text PRIMARY KEY,
    incoming_quantity integer NOT NULL
);

INSERT INTO stock_balances (sku, available_quantity)
VALUES ('BOOK-SQL', 10);

INSERT INTO stock_changes (sku, incoming_quantity)
VALUES
    ('BOOK-SQL', 3),
    ('BOOK-JAVA', 5);

MERGE INTO stock_balances AS target
USING stock_changes AS source
ON target.sku = source.sku
WHEN MATCHED THEN
    UPDATE SET available_quantity =
        target.available_quantity + source.incoming_quantity
WHEN NOT MATCHED THEN
    INSERT (sku, available_quantity)
    VALUES (source.sku, source.incoming_quantity);
```

Trong PostgreSQL 15+, câu `MERGE` trên có thể dùng để cập nhật hoặc chèn dựa theo sự khớp khóa. Nếu server chạy PostgreSQL 14, nó không hỗ trợ câu `MERGE` như ví dụ.

**Cách kiểm tra trước khi học hoặc áp dụng:**

```sql
SHOW server_version;
SHOW server_version_num;
```

Nếu major nhỏ hơn 15, hãy tìm cách giải quyết khác được phiên bản đó hỗ trợ, ví dụ `INSERT ... ON CONFLICT` trong những tình huống upsert phù hợp, thay vì sao chép nguyên `MERGE`.

### 9.2. Một cú pháp có vẻ giống nhau nhưng hành vi có thể thay đổi

Không chỉ tính năng mới mới gây khác biệt. Một số major có thể thay đổi cách bộ tối ưu xử lý cùng một SQL. Chẳng hạn, từ PostgreSQL 12, cơ chế tối ưu CTE có những thay đổi quan trọng về khả năng gộp (*inlining/folding*) CTE đủ điều kiện so với hành vi thường thấy ở các phiên bản cũ.

Ví dụ:

```sql
WITH recent_orders AS (
    SELECT order_id, customer_id, created_at
    FROM orders
    WHERE created_at >= DATE '2026-01-01'
)
SELECT customer_id, COUNT(*)
FROM recent_orders
GROUP BY customer_id;
```

Câu SQL có thể đúng trên nhiều major, nhưng kế hoạch thực thi không nhất thiết giống nhau. Vì vậy, khi đọc bài tối ưu truy vấn cũ hướng dẫn “CTE luôn materialize” hoặc “CTE luôn là optimization fence”, cần kiểm tra tài liệu đúng major và xem `EXPLAIN` thực tế, thay vì dùng một quy tắc rút ra từ bản cũ cho mọi phiên bản mới.

## 10. Minor update: quy trình vận hành cơ bản

Giả sử server chạy PostgreSQL `16.4` và đội vận hành muốn lên một minor mới trong nhánh 16. Một quy trình tổng quát:

### Trước cập nhật

1. Xác nhận phiên bản đang chạy bằng `SHOW server_version` và ghi lại thông tin hệ điều hành/gói cài đặt.
2. Đọc release notes của các minor cần đi qua.
3. Xác nhận bản sao lưu gần đây và khả năng khôi phục.
4. Kiểm tra extension, driver, thư viện native và yêu cầu đặc thù của bản phân phối.
5. Lập kế hoạch thời điểm restart hoặc chuyển dịch vụ, nhất là khi hệ thống có primary/standby.

### Trong cập nhật

1. Dùng kênh cung cấp gói đáng tin cậy hoặc quy trình triển khai binary được phê duyệt.
2. Làm theo hướng dẫn của chính hệ điều hành, bản phân phối và sơ đồ replication.
3. Quản lý thời gian dừng hoặc chuyển đổi phù hợp với SLA.
4. Không giả định “cập nhật minor” là thay file mà không cần restart; phần lớn hình thức cập nhật binary đòi hỏi tiến trình server mới được khởi động để thực sự sử dụng bản đã cài.

### Sau cập nhật

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Sau đó chạy smoke tests của ứng dụng, kiểm tra log, tình trạng kết nối, thống kê replication và các câu truy vấn quan trọng.

**Điều không nên làm:** chạy `pg_upgrade` cho mỗi bản vá minor nếu tài liệu không yêu cầu. `pg_upgrade` được thiết kế cho chuyển đổi giữa các major PostgreSQL; minor update trong cùng nhánh có đường cập nhật khác.

### Trường hợp hệ thống có streaming replication

Khi có primary và standby, lịch cập nhật có thể cần phối hợp từng nút để giảm gián đoạn. Tuy nhiên, không nên tự khẳng định mọi tổ hợp bản minor khác nhau đều tương thích để chạy rolling update vô điều kiện. Cần theo hướng dẫn của PostgreSQL, gói cài đặt và công cụ HA đang sử dụng, đồng thời bảo đảm trạng thái replication và khả năng failover sau cập nhật.

## 11. Major upgrade: không chỉ cài đè binary

Nâng major PostgreSQL liên quan đến **dữ liệu lưu trữ của database cluster**, không đơn thuần là đổi số version hiển thị.

Ví dụ với `16 → 17`, cần có phương án chuyển đổi được PostgreSQL hỗ trợ:

| Phương án | Ý tưởng | Điểm cần đánh giá |
| --- | --- | --- |
| `pg_upgrade` | Sử dụng công cụ chuyển major của PostgreSQL cho cụm dữ liệu tương thích | Phiên bản binary cũ/mới, extension, dung lượng, downtime, rollback và kiểm tra sau nâng cấp. |
| Logical dump/restore | Sao lưu logic từ bản cũ rồi khôi phục vào bản mới | Thời gian dump/restore, kích thước, quyền, sequence, extension và tính tương thích của SQL/schema. |
| Phương án dựa trên logical replication | Đồng bộ dữ liệu từ môi trường major cũ sang major mới, sau đó chuyển ứng dụng | Cấu trúc bảng, sequence, DDL, mức trễ, điểm chuyển giao, tính nhất quán và ràng buộc cụ thể. |

Đừng nhầm **physical streaming replication** với một cách chuyển major tùy ý. Không thể mặc định dựng một standby PostgreSQL 17 từ physical streaming replication của primary PostgreSQL 16 rồi xem đó là phương pháp nâng cấp hỗ trợ.

### 11.1. Vai trò của pg_upgrade

`pg_upgrade` là công cụ chuyển dữ liệu giữa các major PostgreSQL theo yêu cầu và khả năng tương thích của phiên bản. Nó không tự biến mọi extension thành bản tương thích và không thay thế kiểm thử chức năng.

Ví dụ ở cấp terminal:

```bash
pg_upgrade --version
```

Lệnh trên chỉ kiểm tra **phiên bản công cụ `pg_upgrade`**, không thực hiện nâng cấp. Quy trình nâng cấp thực sự cần binary cũ/mới, data directory cũ/mới và nhiều điều kiện khác; không tự chạy `pg_upgrade` với đường dẫn phỏng đoán lên production.

Trong một kế hoạch major upgrade, cần đọc hướng dẫn **`pg_upgrade` của phiên bản đích** và release notes phần migration, không chỉ tra manual của phiên bản nguồn.

### 11.2. Sau major upgrade cần kiểm tra gì?

Một số hạng mục phổ biến:

- Dữ liệu và schema có đúng số lượng, ràng buộc, quyền và đối tượng không?
- Extension có phiên bản tương thích và cần thao tác cập nhật thêm không?
- Thống kê tối ưu truy vấn đã được xử lý theo hướng dẫn nâng cấp chưa?
- Các câu SQL quan trọng có kế hoạch khác, lỗi cú pháp hoặc lỗi quyền hay không?
- Connection pool, JDBC driver và migration tool có cần cấu hình hoặc nâng phiên bản không?
- Standby, backup, giám sát và quy trình khôi phục đã được dựng lại hoặc xác nhận phù hợp chưa?

Chỉ khi kiểm thử đầy đủ, mới có thể đánh giá major upgrade đáp ứng yêu cầu vận hành. Một server PostgreSQL mới khởi động được chưa đủ để tuyên bố ứng dụng tương thích.

## 12. Vòng đời hỗ trợ của các phiên bản PostgreSQL

Dự án PostgreSQL duy trì nhiều nhánh major song song. Theo chính sách phát hành thông thường, **mỗi major nhận hỗ trợ khoảng năm năm** từ lúc phát hành ban đầu, bao gồm các bản minor sửa lỗi/bảo mật trong thời gian hỗ trợ.

Khi nhánh đạt **end of life (EOL)**:

- Dự án không còn cung cấp các bản sửa lỗi và bảo mật chính thức cho nhánh đó theo chính sách chuẩn.
- Một lỗi bảo mật mới được công bố có thể không có bản vá chính thức dành cho major đã hết hạn.
- Việc tiếp tục vận hành đòi hỏi đánh giá rủi ro và kế hoạch nâng major thích hợp; không nên dựa vào việc “server vẫn đang chạy bình thường”.

Tra chính sách và bảng phiên bản đang được hỗ trợ tại:

```text
https://www.postgresql.org/support/versioning/
```

**Không nên ghi nhớ cứng “major mới nhất hiện tại” từ một bài học cố định.** Danh sách phiên bản được hỗ trợ, thời điểm EOL và các minor mới được phát hành tiếp tục thay đổi theo thời gian. Khi bảo trì hệ thống, cần kiểm tra thông tin chính thức tại thời điểm triển khai.

### 12.1. Có nên luôn dùng major mới nhất?

Không phải lúc nào. Quyết định cân bằng giữa:

- Yêu cầu tính năng mới.
- Thời gian hỗ trợ còn lại của major đang sử dụng.
- Tình trạng tương thích extension, driver và thư viện.
- Kinh nghiệm vận hành và quy trình thử nghiệm của tổ chức.
- Rủi ro bảo mật nếu kéo dài trên một nhánh hết hỗ trợ.

Một major vừa ra có thể có tính năng hấp dẫn nhưng hệ sinh thái ứng dụng chưa sẵn sàng. Ngược lại, bám mãi vào major quá cũ để “an toàn” có thể làm tăng rủi ro bảo mật và khó nhận hỗ trợ. Cách tiếp cận tốt hơn là có **lịch nâng major định kỳ** và **cập nhật minor kịp thời** trong nhánh đang được hỗ trợ.

## 13. So sánh phiên bản giữa các môi trường

Trong dự án Java, có thể tồn tại nhiều môi trường:

```text
Laptop developer    -> PostgreSQL 17.2
CI integration test -> PostgreSQL 16.4
Staging             -> PostgreSQL 16.5
Production          -> PostgreSQL 16.4
```

Các số này chỉ minh họa sự khác biệt. Hệ quả:

- Developer có thể viết SQL dùng tính năng chỉ có từ 17, nhưng CI và production chạy major 16.
- Staging và production cùng major 16 nhưng khác minor, nên một lỗi được vá ở staging chưa chắc đã được vá trên production.
- Một migration “chạy tốt ở máy tôi” không bảo đảm chạy đúng trên server có major thấp hơn.

### 13.1. Lựa chọn phiên bản cho môi trường kiểm thử

Khi mục tiêu là xác nhận mã có chạy trên production:

1. **Kiểm thử tương thích** nên chạy trên major thực tế của production.
2. Nếu production và staging khác minor, cần hiểu sự khác biệt, đặc biệt khi đang xác minh một bản vá.
3. Có thể bổ sung kiểm thử sớm trên major mới để chuẩn bị upgrade, nhưng không thay thế kiểm thử trên major đang phục vụ người dùng.
4. Container image, package version và bản PostgreSQL server đang chạy cần được ghi lại; tên tag động như `latest` không cung cấp khả năng tái lập ổn định.

### 13.2. Ví dụ kiểm tra đầu khởi động

Một dịch vụ Java có thể đọc `server_version_num` và từ chối khởi động nếu ứng dụng đòi hỏi major tối thiểu, hoặc ghi log để cảnh báo môi trường không đồng nhất.

Ví dụ câu SQL:

```sql
SELECT current_setting('server_version_num')::integer
       >= 150000 AS meets_minimum_pg15;
```

Nếu ứng dụng dùng `MERGE`, kiểm tra mức tối thiểu 15 giúp phát hiện sai môi trường sớm hơn. Tuy nhiên, dùng kiểm tra version như **một điều kiện trước**, không thay thế các kiểm tra schema, extension, quyền và migration.

Một quy tắc hữu ích trong CI là thực hiện test trên major thấp nhất được sản phẩm tuyên bố hỗ trợ, đồng thời chạy bộ test bổ sung trên major đích của kế hoạch nâng cấp.

## 14. Đọc câu trả lời trên Internet mà không bị nhầm phiên bản

Các blog, câu trả lời diễn đàn và đoạn code được tạo từ nguồn khác nhau có thể thuộc thời điểm và major khác nhau. Khi tìm kiếm vấn đề PostgreSQL, hãy kiểm tra:

1. **Ngày đăng và ngày cập nhật** của nội dung.
2. **Major version** được người viết nhắc tới.
3. Cú pháp và kết quả có được tài liệu chính thức của major mình dùng xác nhận không.
4. Các comment hoặc phần cập nhật có nói tính năng mới được bổ sung ở một bản sau không.
5. Tác giả đang dùng PostgreSQL thuần hay một sản phẩm tương thích PostgreSQL có giới hạn khác?

Ví dụ một bài viết có câu:

> “PostgreSQL không hỗ trợ MERGE; hãy dùng INSERT ON CONFLICT.”

Câu này có thể đúng tại thời điểm viết với những major trước 15 nhưng không còn là phát biểu khái quát đúng cho PostgreSQL 15 trở đi. Cách đọc đúng là xác định **bài viết đang mô tả major nào**.

Tương tự, một lời khuyên cũ như “CTE luôn được materialize” cần được đọc cùng bối cảnh phiên bản, vì bộ tối ưu PostgreSQL thay đổi theo các major.

## 15. Những lỗi thường gặp

| Nhầm lẫn | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| `9.6.24` có major 9, minor 6 | Trước PG10, major gồm hai phần đầu | Major là `9.6`; minor là `24`. |
| `17.2` có major 17.2 | Từ PG10, major là số đầu | Major `17`; minor `2`. |
| `16.10` cũ hơn `16.9` vì 16.10 bằng 16.1 | Version không phải số thập phân | So sánh thành phần minor 10 với 9. |
| `psql --version` là phiên bản server | Lệnh này kiểm tra client binary | Chạy `SHOW server_version` trên connection đúng. |
| Link `/docs/current/` luôn đúng cho mọi server | `current` có thể đổi major khi dự án phát hành bản mới | Chọn `/docs/{major}/` phù hợp với server. |
| Major 16 có thể dùng mọi tính năng trong manual major 17 | Tính năng có thể ra sau | Xem “introduced in version” và manual của major 16. |
| Minor update giống major upgrade | Mục tiêu và định dạng dữ liệu khác nhau | Phân biệt bản vá cùng nhánh với chuyển major. |
| Một minor không cần đọc release notes | Bản vá có thể có chỉ dẫn quan trọng | Đọc release notes của tất cả bản cập nhật liên quan. |
| Driver mới bảo đảm server có SQL mới | Driver và server có vòng đời riêng | Kiểm tra server version và thử SQL trên server đích. |
| Máy chủ chạy được là chắc chắn đang được hỗ trợ | EOL phụ thuộc chính sách dự án | Kiểm tra bảng support/versioning chính thức. |

### Lỗi 1. Chọn tài liệu theo phiên bản client

Tình huống:

```bash
psql --version
# psql (PostgreSQL) 17.2
```

Nhưng server:

```sql
SHOW server_version;
-- 16.4
```

**Kết luận:** để biết cú pháp SQL server hỗ trợ, đọc PostgreSQL 16 manual. Để hiểu option và lệnh meta của `psql` cài trên laptop, có thể cần xem tài liệu `psql` tương ứng với client 17.

### Lỗi 2. Chỉ mở release notes của major mới và bỏ qua các minor

Một dự án đang chạy `16.2` muốn cập nhật lên `16.5`. Nếu chỉ xem “PostgreSQL 16 new features” thì có thể bỏ lỡ các lỗi đã được sửa trong `16.3`, `16.4` và `16.5`. Để xử lý bug hoặc security patch, phải đọc release notes của những minor liên quan.

### Lỗi 3. Đọc bản dịch hoặc blog mà không kiểm tra nguồn

Bản dịch, tài liệu nội bộ và blog rất hữu ích để học, nhưng có thể lạc hậu. Khi gặp câu SQL cần dùng cho production, đối chiếu bản gốc chính thức và phiên bản cụ thể. Không nên sao chép lệnh thay đổi schema hoặc nâng cấp chỉ vì một ví dụ ngắn hoạt động trên môi trường thử nghiệm khác.

## 16. Bài tập thực hành

### Bài 1. Phân loại major và minor

Hãy tự điền vào bảng:

| Phiên bản | Major | Minor |
| --- | --- | --- |
| `9.6.24` | ? | ? |
| `10.23` | ? | ? |
| `16.4` | ? | ? |
| `17.2` | ? | ? |

**Đáp án:**

| Phiên bản | Major | Minor |
| --- | --- | --- |
| `9.6.24` | 9.6 | 24 |
| `10.23` | 10 | 23 |
| `16.4` | 16 | 4 |
| `17.2` | 17 | 2 |

### Bài 2. Tìm phiên bản đúng từ kết nối hiện tại

Chạy:

```sql
SELECT
    current_database(),
    current_user,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS server_version_num;
```

**Yêu cầu:** ghi lại major/minor của server, tên database và role đăng nhập. Sau đó đối chiếu với kết quả terminal:

```bash
psql --version
```

**Câu hỏi:** Hai phiên bản có giống nhau không? Nếu khác, phiên bản nào quyết định câu SQL `MERGE` có thể chạy?

**Đáp án:** phiên bản **server** quyết định hỗ trợ SQL, vì server phân tích cú pháp và thực thi câu lệnh. Phiên bản client chỉ cho biết công cụ đang dùng.

### Bài 3. Chọn bộ tài liệu

Một ứng dụng kết nối PostgreSQL `16.4`. Có ba liên kết:

```text
A. https://www.postgresql.org/docs/current/
B. https://www.postgresql.org/docs/16/
C. https://www.postgresql.org/docs/17/
```

**Câu hỏi:** Đâu là điểm bắt đầu phù hợp nhất để đọc cú pháp SQL và hành vi của server?

**Đáp án:** **B** vì server thuộc major 16. Link A chỉ dùng nếu mục tiêu là tìm hiểu tài liệu của major `current` tại thời điểm đọc; link C mô tả major 17, không phải lựa chọn mặc định cho server 16.

### Bài 4. Nâng minor hay major?

Phân loại:

1. `16.4 → 16.5`.
2. `16.4 → 17.0`.
3. `9.6.23 → 9.6.24`.
4. `9.5.25 → 9.6.0`.

**Đáp án:** 1 là minor, 2 là major, 3 là minor, 4 là major. Trường hợp 4 tuân theo quy tắc major hai số của PostgreSQL trước phiên bản 10.

### Bài 5. Dự đoán việc áp dụng MERGE

```sql
MERGE INTO stock_balances AS target
USING stock_changes AS source
ON target.sku = source.sku
WHEN MATCHED THEN
    UPDATE SET available_quantity = source.incoming_quantity
WHEN NOT MATCHED THEN
    INSERT (sku, available_quantity)
    VALUES (source.sku, source.incoming_quantity);
```

**Câu hỏi:** Câu lệnh có thể chạy nguyên bản trên PostgreSQL 14 không?

**Đáp án:** Không. `MERGE` được bổ sung từ PostgreSQL 15. Với server 14, cần cách viết khác tương thích hoặc nâng major nếu nghiệp vụ và kế hoạch vận hành cho phép.

### Bài 6. Tìm nguyên nhân lỗi sau cập nhật

Giả sử production `16.2` có một lỗi truy vấn, còn staging `16.5` không tái hiện. Bạn nên:

1. Xác nhận cả hai thực sự là PostgreSQL Server major 16, không nhầm phiên bản client.
2. Đọc release notes từ `16.3` đến `16.5` để tìm bản vá liên quan.
3. Xem cấu hình, extension, workload và dữ liệu của hai môi trường.
4. Kiểm thử trên môi trường được kiểm soát trước khi đưa minor update vào production.

Không đủ bằng chứng để kết luận lỗi chắc chắn đã được sửa chỉ từ việc hai môi trường khác minor; nhưng khác biệt minor là một đầu mối cần điều tra.

## 17. Một quy trình tra cứu nhanh có thể áp dụng hằng ngày

Khi bắt đầu một bài học PostgreSQL hoặc xử lý vấn đề thực tế:

```text
1. Xác định server và database đích
           │
           v
2. SHOW server_version;
   SHOW server_version_num;
           │
           v
3. Tách major/minor theo quy tắc:
   - >= PostgreSQL 10: major = số đầu
   - <  PostgreSQL 10: major = hai số đầu
           │
           v
4. Đọc manual /docs/<major>/ cho tính năng/cú pháp
           │
           v
5. Đọc release notes của minor/major liên quan
           │
           v
6. Đối chiếu client, extension, driver và môi trường
           │
           v
7. Thử trên môi trường đúng phiên bản trước khi triển khai
```

Ví dụ thực tế:

```sql
-- Trong kết nối SQL tới production:
SHOW server_version;
-- Giả sử kết quả: 16.4

SHOW server_version_num;
-- Giả sử kết quả: 160004
```

Từ đó:

- **Major:** 16.
- **Minor:** 4.
- **Manual chính:** `https://www.postgresql.org/docs/16/`.
- **Nếu tìm một bug hoặc security fix:** xem release notes trong nhánh 16 và các bản minor có liên quan.
- **Nếu muốn thử chức năng của major 17:** đọc thêm tài liệu/release notes 17, nhưng không áp dụng mặc nhiên lên server 16.
- **Nếu cần nâng major:** lập kế hoạch theo tài liệu nâng cấp của phiên bản đích, kiểm tra extension và phương án chuyển dữ liệu.

## 18. Kết luận

Trong PostgreSQL, cần phân biệt chính xác:

- **Từ PostgreSQL 10:** phiên bản `X.Y` có major là `X`, minor là `Y`.
- **Trước PostgreSQL 10:** phiên bản `X.Y.Z` có major là `X.Y`, minor là `Z`.
- **Minor update** chủ yếu cung cấp các bản sửa lỗi và bảo mật trong cùng major; **major upgrade** có thể bổ sung tính năng và yêu cầu quy trình chuyển dữ liệu riêng.
- **Server version** mới quyết định câu SQL được hỗ trợ; không lấy `psql --version`, JDBC driver version hay extension version thay thế.
- **Manual chính thức theo major** là điểm bắt đầu để học cú pháp, còn **release notes theo bản phát hành** giúp hiểu sửa lỗi, thay đổi và lưu ý migration.
- Đường dẫn `/docs/current/` có thể thay đổi major theo thời gian. Với một server cố định, nên ưu tiên `/docs/{major}/` và đối chiếu chính sách hỗ trợ chính thức.

Kỹ năng đọc đúng phiên bản không chỉ giúp tránh lỗi cú pháp trong lúc học. Nó còn là nền tảng để thiết kế tương thích ứng dụng, xử lý sự cố, duy trì bản vá bảo mật và lên kế hoạch nâng cấp PostgreSQL một cách có kiểm soát.
