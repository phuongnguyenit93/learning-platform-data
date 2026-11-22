# UUID và lựa chọn cách sinh định danh theo phiên bản PostgreSQL

Khi thiết kế khóa chính cho bảng PostgreSQL, một câu hỏi thường gặp là: **nên dùng số tự tăng hay UUID, và UUID nên được sinh ở đâu?** Trong các hệ thống có nhiều dịch vụ, ghi dữ liệu từ nhiều nơi, đồng bộ ngoại tuyến hoặc cần tạo ID trước khi gửi câu lệnh `INSERT`, UUID là một lựa chọn đáng cân nhắc.

Điểm dễ gây nhầm lẫn là **PostgreSQL hỗ trợ kiểu dữ liệu `uuid` từ lâu, nhưng các hàm sinh UUID tích hợp sẵn đã thay đổi theo phiên bản**. Một ví dụ dùng `uuidv7()` sẽ chạy trên PostgreSQL 18, nhưng không chạy trực tiếp trên PostgreSQL 17. Ngược lại, ví dụ cũ yêu cầu cài `pgcrypto` để dùng `gen_random_uuid()` không còn cần thiết cho mục đích sinh UUIDv4 từ PostgreSQL 13 trở lên.

Bài học giải thích bản chất của UUID, cách phân biệt các version quan trọng, lựa chọn generator tương ứng với phiên bản PostgreSQL, so sánh sinh ID tại database và ứng dụng, cùng ảnh hưởng đến primary key, index, truy vấn và migration.

## 1. UUID là gì và vì sao cần kiểu dữ liệu riêng?

**UUID (Universally Unique Identifier)** là định danh 128 bit. Một giá trị thường được hiển thị dưới dạng 32 chữ số hệ 16, chia thành các nhóm theo mẫu `8-4-4-4-12`:

~~~text
a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
~~~~~~~~-~~~~-~~~~-~~~~-~~~~~~~~~~~~
~~~

Các dấu gạch ngang là định dạng biểu diễn để dễ đọc; **giá trị UUID có kích thước logic 16 byte**, không phải 36 byte text trong kiểu PostgreSQL `uuid`.

Ví dụ tạo bảng chứa UUID do ứng dụng cung cấp:

~~~sql
CREATE TABLE example_documents (
    document_id uuid PRIMARY KEY,
    title text NOT NULL
);
~~~

Đưa vào một giá trị hợp lệ:

~~~sql
INSERT INTO example_documents (document_id, title)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
    'Tai lieu mau'
);

SELECT
    document_id,
    pg_typeof(document_id) AS id_type,
    pg_column_size(document_id) AS id_bytes
FROM example_documents;
~~~

Dự kiến `id_type` là `uuid` và kích thước bản thân giá trị UUID được lưu là **16 byte**. Kích thước tổng thể của hàng hoặc chỉ mục còn có overhead của PostgreSQL, nên không thể lấy 16 nhân số hàng làm kích thước chính xác của toàn bộ bảng.

PostgreSQL chấp nhận một số cách viết UUID ở đầu vào, chẳng hạn chữ hex hoa/thường hoặc không có dấu gạch ngang; khi xuất ra, hệ thống chuẩn hóa theo dạng thông dụng chữ thường có gạch ngang.

### UUID có thực sự “duy nhất tuyệt đối” không?

UUID được tạo theo các thuật toán có xác suất trùng rất thấp hoặc theo quy tắc định danh xác định. Nó **không phải bảo đảm toán học rằng mọi giá trị sinh ra đều khác nhau trong mọi tình huống**. Bộ sinh ngẫu nhiên lỗi, cách triển khai sai hoặc việc tái sử dụng giá trị vẫn có thể tạo trùng.

Vì vậy nếu UUID là khóa chính, vẫn cần:

~~~sql
id uuid PRIMARY KEY
~~~

hoặc một ràng buộc `UNIQUE` phù hợp. PostgreSQL sẽ phát hiện và từ chối khóa trùng.

## 2. Phân biệt kiểu uuid với thuật toán sinh UUID

Đây là hai khái niệm độc lập:

1. **Kiểu dữ liệu `uuid`:** PostgreSQL lưu và so sánh giá trị 128 bit.
2. **UUID version:** cách một giá trị được tạo ra, ví dụ ngẫu nhiên v4 hay theo thời gian v7.
3. **Generator:** hàm SQL, extension hoặc thư viện ứng dụng tạo ra một giá trị UUID.

Một cột `uuid` có thể lưu UUIDv4, UUIDv7 hoặc UUID được tạo bên ngoài database. Việc tạo cột `uuid` **không mặc nhiên khiến PostgreSQL tự sinh ID**; phải có `DEFAULT` hoặc giá trị được ứng dụng đưa vào.

~~~sql
-- Chỉ định kiểu dữ liệu, KHÔNG có default:
CREATE TABLE example_ids_manual (
    id uuid PRIMARY KEY
);

-- Chỉ định thêm biểu thức DEFAULT sinh giá trị
-- bằng hàm có trên phiên bản đang dùng:
CREATE TABLE example_ids_generated (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid()
);
~~~

Hai ví dụ tạo bảng độc lập. Câu thứ hai chỉ chạy khi `gen_random_uuid()` có sẵn, chẳng hạn PostgreSQL 13 trở lên.

## 3. Những version UUID thường gặp

UUID version được mã hóa trong định danh và quy định thuật toán sinh. Với thiết kế ứng dụng PostgreSQL, cần phân biệt ít nhất:

| UUID version | Đặc tính chính | Tình huống đáng cân nhắc |
| --- | --- | --- |
| **v1** | Dựa trên thời gian và thông tin node/MAC theo thuật toán lịch sử | Tương thích hệ thống cũ; cân nhắc nguy cơ tiết lộ thông tin |
| **v3** | Sinh xác định từ namespace + tên bằng MD5 | Tái tạo cùng ID từ cùng đầu vào trong hệ thống legacy |
| **v4** | Phần lớn bit ngẫu nhiên | ID tổng quát, không cần phụ thuộc thời gian hoặc thứ tự |
| **v5** | Sinh xác định từ namespace + tên bằng SHA-1 | Ánh xạ một khóa định danh ngoại bộ thành UUID ổn định |
| **v7** | Kết hợp timestamp theo thời gian Unix và dữ liệu khác | ID có xu hướng sắp theo thời điểm, hữu ích cho index và luồng sự kiện |

**Version không phải phiên bản PostgreSQL.** UUIDv7 là một dạng UUID, còn PostgreSQL 18 là phiên bản hệ quản trị cơ sở dữ liệu. PostgreSQL 17 vẫn lưu được giá trị UUIDv7 hợp lệ do ứng dụng tạo ra, dù **không có hàm `uuidv7()` tích hợp sẵn**.

### Minh họa bằng hai UUID

~~~text
UUIDv4:
a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
              ^
        nibble version = 4

UUIDv7:
019535d9-3df7-79fb-b466-fa907fa17f9e
              ^
        nibble version = 7
~~~

Trong chuỗi UUID chuẩn, chữ số hex đầu của nhóm thứ ba thể hiện version. Không nên tự phân tích UUID bằng cắt chuỗi trong mọi nghiệp vụ nếu đã có hàm/thư viện kiểm tra version phù hợp.

UUIDv1 có thể tiết lộ dấu vết thời gian và thông tin thiết bị từ cơ chế sinh. UUIDv7 chứa thông tin thời gian nên cũng **không nên coi là giá trị che giấu hoàn toàn thời điểm tạo**. UUIDv4 thường không biểu diễn thời gian sinh theo cách tương tự.

## 4. Bảng lựa chọn generator theo phiên bản PostgreSQL

Đây là bảng quan trọng nhất khi chọn hàm `DEFAULT` trong migration.

| PostgreSQL | Sinh UUIDv4 từ SQL | Sinh UUIDv7 từ SQL | Lưu ý |
| --- | --- | --- | --- |
| **18** | `gen_random_uuid()` hoặc `uuidv4()` tích hợp | **`uuidv7()` tích hợp** | Có thể dùng hàm `uuid_extract_version()` và `uuid_extract_timestamp()` cho v1/v7 |
| **13–17** | **`gen_random_uuid()` tích hợp** | Không có `uuidv7()` lõi | Muốn v7 cần thư viện ứng dụng hoặc extension được kiểm chứng |
| **12 trở xuống** | `pgcrypto.gen_random_uuid()` theo schema cài extension, hoặc `uuid_generate_v4()` của `uuid-ossp` | Không có `uuidv7()` lõi | Phải có extension/thư viện thích hợp; các bản quá cũ cần kế hoạch nâng cấp |

Ở dòng cuối, `pgcrypto.gen_random_uuid()` là cách mô tả **hàm `gen_random_uuid` đến từ extension pgcrypto**; schema thực tế mà extension được cài có thể không phải `pgcrypto`. Khi chạy SQL, thường gọi `gen_random_uuid()` sau khi cài extension vào schema phù hợp và cho phép tra cứu hàm qua `search_path`.

**Mốc đáng nhớ:**

- **PostgreSQL 13:** `gen_random_uuid()` trở thành hàm lõi để sinh UUIDv4.
- **PostgreSQL 18:** bổ sung `uuidv7()` sinh UUIDv7 và `uuidv4()` làm tên gọi tường minh cho UUIDv4.
- `uuid-ossp` vẫn hữu ích cho các thuật toán đặc biệt như v3/v5 hoặc tương thích hệ thống cũ.
- Không cần cài `pgcrypto` chỉ để gọi hàm lõi `gen_random_uuid()` trên PostgreSQL 13–18.

Bảng diễn tả các khả năng trong **các bản PostgreSQL chính thức**. Một hệ thống managed database, bản dựng riêng hoặc extension bên thứ ba có thể khác. Khi viết migration, luôn kiểm tra server thực tế thay vì suy từ tên thư viện trong một ví dụ trên Internet.

## 5. Kiểm tra phiên bản và hàm nào thực sự có sẵn

Trước khi chọn `DEFAULT`, kết nối tới database dự kiến và kiểm tra:

~~~sql
SELECT version();

SHOW server_version;

SHOW server_version_num;
~~~

Ví dụ `server_version_num` của PostgreSQL 18 có dạng số bắt đầu bằng `180000`, còn PostgreSQL 17 bắt đầu bằng `170000`. **Phiên bản server** quyết định những hàm SQL lõi khả dụng, không phải phiên bản `psql` đang cài trên máy cá nhân.

Trong PostgreSQL hiện đại có thể kiểm tra sự hiện diện của hàm mà **không gọi hàm không tồn tại**:

~~~sql
SELECT
    to_regprocedure('pg_catalog.gen_random_uuid()')
        AS core_uuid_v4,
    to_regprocedure('pg_catalog.uuidv4()')
        AS core_uuidv4_alias,
    to_regprocedure('pg_catalog.uuidv7()')
        AS core_uuid_v7;
~~~

Kết quả `NULL` nghĩa là không tìm thấy hàm đúng chữ ký trong schema `pg_catalog` trên server đó. Ở PostgreSQL 17, hai cột liên quan `uuidv4()` và `uuidv7()` lõi dự kiến là `NULL`; PostgreSQL 18 hỗ trợ cả ba.

Kiểm tra extension được cài trong **database hiện tại**:

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname IN ('pgcrypto', 'uuid-ossp')
ORDER BY extname;
~~~

Còn danh sách extension có thể cài từ server:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
WHERE name IN ('pgcrypto', 'uuid-ossp');
~~~

Không có extension trong `pg_extension` không đồng nghĩa tính năng UUIDv4 lõi không tồn tại. Ngược lại, tên extension xuất hiện ở `pg_available_extensions` cũng không chứng minh nó **đã được cài trong database** hoặc role của bạn được phép cài.

## 6. PostgreSQL 13–17: dùng gen_random_uuid() cho UUIDv4

Trên PostgreSQL 13 trở lên, `gen_random_uuid()` là phương án đơn giản cho khóa chính UUIDv4 do database sinh.

~~~sql
CREATE TABLE customers_v4 (
    customer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Chèn dữ liệu và để server tạo ID:

~~~sql
INSERT INTO customers_v4 (email, full_name)
VALUES ('an@example.test', 'An')
RETURNING customer_id, email;
~~~

Đầu ra chứa một UUIDv4 mới được sinh. Giá trị cụ thể **thay đổi mỗi lần chạy**; không nên ghi cứng một UUID “được kỳ vọng” cho hàm sinh ngẫu nhiên.

### Vì sao dùng DEFAULT?

Khi cột có `DEFAULT gen_random_uuid()`, một lệnh `INSERT` **không cung cấp cột ID** sẽ gọi generator để tạo giá trị:

~~~sql
INSERT INTO customers_v4 (email, full_name)
VALUES ('binh@example.test', 'Binh');
~~~

Có thể yêu cầu dùng `DEFAULT` rõ ràng:

~~~sql
INSERT INTO customers_v4 (customer_id, email, full_name)
VALUES (
    DEFAULT,
    'chi@example.test',
    'Chi'
);
~~~

Nếu ứng dụng truyền một UUID cụ thể, database dùng chính giá trị đó thay vì gọi default:

~~~sql
INSERT INTO customers_v4
    (customer_id, email, full_name)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
    'dung@example.test',
    'Dung'
);
~~~

Nếu truyền SQL `NULL` tường minh cho khóa chính, `DEFAULT` **không tự thay thế NULL**; `PRIMARY KEY` vẫn từ chối giá trị NULL. Điều này khác với việc **bỏ cột ra khỏi câu INSERT**.

### Khi nào chọn v4?

UUIDv4 phù hợp khi:

- Muốn nhiều ứng dụng hoặc nhiều database có thể tạo ID mà không cần xin số từ một sequence trung tâm.
- Không cần ID phản ánh thời điểm tạo.
- Muốn tránh phơi bày số lượng bản ghi qua ID số tăng tuần tự.
- Dữ liệu và lưu lượng ghi chưa khiến vấn đề index locality của ID ngẫu nhiên trở thành nút thắt quan trọng.

UUIDv4 **không phải token bí mật**. Dù khó đoán hơn ID tuần tự, server vẫn phải kiểm tra quyền truy cập theo người dùng/tenant khi đọc hoặc sửa bản ghi.

## 7. PostgreSQL 18: dùng uuidv7() cho định danh gần theo thời gian

PostgreSQL 18 bổ sung hàm lõi:

~~~sql
SELECT uuidv7();
~~~

Nó tạo **UUIDv7** với phần timestamp và thông tin phụ giúp các giá trị có xu hướng sắp xếp theo thời gian. Có thể dùng làm default:

~~~sql
CREATE TABLE events_v7 (
    event_id uuid PRIMARY KEY DEFAULT uuidv7(),
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Chèn sự kiện:

~~~sql
INSERT INTO events_v7 (event_type, payload)
VALUES
    ('order_created', '{"order_id":1001}'::jsonb),
    ('order_paid',    '{"order_id":1001}'::jsonb)
RETURNING event_id, event_type, created_at;
~~~

`event_id` được sinh bởi PostgreSQL 18. `created_at` vẫn được lưu riêng dù ID đã chứa timestamp, vì timestamp của UUIDv7 **không thay thế toàn bộ ngữ nghĩa thời gian nghiệp vụ**.

### Vì sao v7 thường có lợi cho B-tree index?

Một khóa chính UUIDv4 có các giá trị phân bố ngẫu nhiên trong không gian khóa, vì vậy những lần `INSERT` mới có thể đi vào nhiều vùng của B-tree index.

UUIDv7 đưa thông tin thời gian lên phần đầu định danh, nên những ID sinh gần nhau theo thời gian **có xu hướng gần nhau theo thứ tự index**. Trong một số workload ghi liên tục, điều này có thể giảm tính ngẫu nhiên của vị trí chèn, giảm page splits hoặc cải thiện cache locality so với UUIDv4.

Nhưng không có bảo đảm rằng `uuidv7()` luôn nhanh hơn:

- UUIDv7 vẫn là UUID 128 bit; không nhỏ bằng `bigint` 64 bit.
- Nhiều nguồn sinh cùng lúc, lệch đồng hồ hoặc cơ chế generator khác nhau có thể khiến thứ tự không hoàn toàn trùng với thứ tự commit.
- Hiệu quả còn phụ thuộc index, kích thước bảng, fillfactor, concurrency, WAL, autovacuum, workload đọc/ghi và cấu hình server.
- Với bảng nhỏ, khác biệt có thể không đáng kể.

**Đo trên workload thực tế** trước khi đổi toàn bộ khóa chính sang v7 chỉ vì nó được gọi là “time-ordered”.

### Các hàm bổ sung của PostgreSQL 18

~~~sql
SELECT
    uuidv4() AS random_uuid,
    uuidv7() AS time_ordered_uuid;
~~~

`uuidv4()` là tên gọi tường minh cho UUIDv4; `gen_random_uuid()` vẫn có thể dùng.

Hàm `uuidv7()` còn có tham số `shift interval` tùy chọn để dịch chuyển phần timestamp theo khoảng thời gian được cho phép. Phần lớn ứng dụng **không cần dùng shift**; không dịch timestamp tùy tiện để làm sai lệch ý nghĩa thời gian.

Để xem version và timestamp:

~~~sql
SELECT
    event_id,
    uuid_extract_version(event_id) AS uuid_version,
    uuid_extract_timestamp(event_id) AS embedded_time
FROM events_v7
ORDER BY event_id;
~~~

Với giá trị UUIDv7, `uuid_extract_version` trả `7` và `uuid_extract_timestamp` cố gắng trích phần thời gian được mã hóa trong ID.

**Lưu ý theo phiên bản:** PostgreSQL 17 đã có hàm trích version và timestamp cho **UUIDv1**; PostgreSQL 18 mở rộng khả năng trích timestamp cho **UUIDv7**. Trên PostgreSQL 17, không dùng `uuid_extract_timestamp` để suy ra thời gian từ UUIDv7 như trên 18.

### Có thể dùng ORDER BY uuid thay cho ORDER BY created_at không?

Có thể sắp `ORDER BY event_id` và với UUIDv7 sẽ nhận thứ tự có tính thời gian theo phần mã hóa của ID. Nhưng điều đó **không tương đương một bảo đảm tuyệt đối về thứ tự commit hoặc thời gian nghiệp vụ**:

- `now()` trong PostgreSQL lấy thời điểm bắt đầu transaction; nhiều bản ghi trong cùng transaction có thể có cùng `created_at`.
- ID có thể được tạo trước khi transaction commit.
- Các tiến trình/máy khác nhau có thể có đồng hồ lệch.
- Có thể import UUIDv7 từ hệ thống bên ngoài hoặc chèn ID được tạo trước.
- Thứ tự nhận event/commit và thứ tự tạo ID không luôn trùng nhau.

Nếu nghiệp vụ cần “sự kiện mới nhất”, hãy định nghĩa thứ tự dựa trên `created_at` hoặc trường sequence/event-position phù hợp, với khóa phụ phá hòa khi cần. UUIDv7 là lợi ích cho đặc tính thứ tự của ID, **không tự biến thành chứng cứ về thời điểm hoàn tất giao dịch**.

## 8. PostgreSQL 12 và trước đó: pgcrypto cho UUIDv4

Ở những phiên bản cũ trước khi `gen_random_uuid()` trở thành hàm lõi, một cách sinh UUIDv4 thông dụng là extension `pgcrypto`.

Cài extension trong **database đang kết nối**, khi server có extension và tài khoản có quyền:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

Sau đó:

~~~sql
SELECT gen_random_uuid();
~~~

Và trong schema:

~~~sql
CREATE TABLE legacy_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name text NOT NULL
);
~~~

**Không chạy `CREATE EXTENSION` trên production chỉ để làm theo tài liệu học** khi chưa biết chính sách vận hành. Extension phải có sẵn ở bản dựng server, cần quyền cài và có thể bị hạn chế trong dịch vụ PostgreSQL managed.

### Pgcrypto ở các bản mới thì sao?

Trong các bản PostgreSQL mới, `pgcrypto` vẫn chứa nhiều chức năng mật mã khác. Nhưng riêng `gen_random_uuid()` của extension được xem như wrapper/compatibility với hàm lõi đã tồn tại. Vì vậy:

- Nếu **chỉ cần UUIDv4 trên PostgreSQL ≥ 13**, ưu tiên hàm lõi `gen_random_uuid()`.
- Nếu cần các chức năng mật mã đặc thù của `pgcrypto`, extension vẫn có vai trò riêng.
- Với PostgreSQL 12 trở xuống, có thể sử dụng `pgcrypto` nếu môi trường hỗ trợ; đồng thời cần kế hoạch nâng cấp vì các major version cũ đã hết vòng đời hỗ trợ.

Cách sinh UUIDv4 **không làm thay đổi kiểu cột**: `event_id` vẫn là `uuid`. Điều thay đổi là nguồn cung cấp hàm tạo giá trị.

## 9. uuid-ossp: khi cần v1, v3, v4 hoặc v5

Extension `uuid-ossp` cung cấp các thuật toán UUID chuẩn được nhiều hệ thống sử dụng từ trước, bao gồm:

| Hàm | Ý nghĩa |
| --- | --- |
| `uuid_generate_v1()` | UUIDv1, dựa vào thời gian và thông tin node |
| `uuid_generate_v1mc()` | Biến thể v1 dùng multicast MAC ngẫu nhiên thay MAC thật |
| `uuid_generate_v3(namespace, name)` | UUIDv3 xác định theo namespace và tên |
| `uuid_generate_v4()` | UUIDv4 ngẫu nhiên |
| `uuid_generate_v5(namespace, name)` | UUIDv5 xác định theo namespace và tên |

Cài khi có lý do và quyền phù hợp:

~~~sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
~~~

Tên extension có dấu gạch ngang nên phải được **đặt trong dấu nháy kép** khi viết SQL.

Ví dụ UUIDv4 qua extension:

~~~sql
SELECT uuid_generate_v4();
~~~

Trên PostgreSQL 13+, nếu chỉ cần v4 thì cài `uuid-ossp` vì lý do này là không bắt buộc. Nhưng `uuid-ossp` có giá trị nếu cần các kiểu UUID cũ hoặc ID **xác định từ một tên**.

### UUIDv5: cùng namespace và tên cho cùng ID

~~~sql
SELECT
    uuid_generate_v5(
        uuid_ns_url(),
        'https://example.test/catalog/sku-501'
    ) AS product_uuid;
~~~

Chạy lại với **cùng namespace và cùng chuỗi tên** tạo ra **cùng UUIDv5**. Nếu tên hoặc namespace thay đổi, ID thường khác.

Đây là lựa chọn khi cần ánh xạ một danh tính ổn định bên ngoài sang UUID mà không lưu bảng đối chiếu riêng, ví dụ dựa vào một mã tài nguyên đã được chuẩn hóa.

Nhưng cần thận trọng:

- Tên đầu vào phải được chuẩn hóa theo một quy tắc rõ ràng, nhất là chữ hoa/thường, Unicode và đường dẫn.
- UUIDv5 **không phải hash chữ ký bảo mật** và không nên dùng để che giấu dữ liệu đầu vào bí mật.
- Cùng tên ở hai namespace khác nhau tạo ra UUID khác.
- Nếu mã nghiệp vụ có thể thay đổi, dùng v5 trực tiếp từ mã đó có thể dẫn đến việc cùng một thực thể được gán ID khác.
- Các thư viện khác nhau phải dùng cùng quy tắc mã hóa đầu vào để bảo đảm kết quả tương thích.

### UUIDv1 có nên dùng làm khóa chính mới?

UUIDv1 có tính chất thời gian nhưng có thể để lộ thông tin thời điểm và node/MAC tùy generator. Với hệ thống mới, thường cân nhắc **v4** cho ID ngẫu nhiên hoặc **v7** cho ID time-ordered trước khi chọn v1, trừ khi có yêu cầu tương thích rõ ràng.

`uuid-ossp` truyền thống **không phải hàm lõi `uuidv7()`**. Không nên suy rằng cài extension này sẽ tự có chức năng `uuid_generate_v7()` trên mọi phiên bản.

## 10. Muốn dùng UUIDv7 nhưng database chưa lên PostgreSQL 18?

PostgreSQL 13–17 vẫn có kiểu `uuid` và có thể **lưu UUIDv7** do một generator bên ngoài tạo ra. Những phương án thực tế:

1. **Sinh tại ứng dụng** bằng thư viện UUIDv7 tuân theo RFC 9562 và đã được kiểm chứng.
2. **Cài extension PostgreSQL bên thứ ba** cung cấp UUIDv7 nếu được DBA phê duyệt, tương thích server/managed service và đã đánh giá tính bảo mật, độ tin cậy.
3. **Nâng cấp server lên PostgreSQL 18** theo quy trình migration/upgrade thích hợp để dùng `uuidv7()` lõi.

Ví dụ một ứng dụng sinh UUIDv7 và truyền qua JDBC:

~~~java
// idV7 được tạo bởi thư viện UUIDv7 đáng tin cậy.
// Đây là giá trị java.util.UUID, không phải chuỗi SQL tự ghép.
UUID idV7 = uuidV7Generator.generate();

String sql = """
    INSERT INTO events (event_id, event_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, idV7);
    ps.setString(2, "OrderCreated");
    ps.executeUpdate();
}
~~~

Đoạn này minh họa cách bind UUID; `uuidV7Generator` là abstraction do ứng dụng cung cấp, không phải một phương thức có sẵn trong Java chuẩn. Giả định bảng `events(event_id uuid, event_name text)` đã tồn tại và phiên bản JDBC driver hỗ trợ mapping `java.util.UUID` như pgJDBC thông dụng.

**Không tự cài đặt thuật toán v7 chỉ bằng cách nối timestamp với hex ngẫu nhiên** nếu chưa kiểm tra đầy đủ bit version/variant, tính hợp lệ, entropy và concurrency. Lỗi generator có thể dẫn tới ID trùng hoặc không tuân chuẩn.

## 11. Sinh ID trong database hay trong ứng dụng?

Đây là một quyết định kiến trúc độc lập với việc chọn UUIDv4 hay UUIDv7.

| Tiêu chí | Sinh tại PostgreSQL | Sinh ở ứng dụng |
| --- | --- | --- |
| Ví dụ | `DEFAULT gen_random_uuid()` hoặc `DEFAULT uuidv7()` | Java UUID/library tạo trước `INSERT` |
| Ưu điểm | Cách sinh tập trung, mọi client cùng default | Có ID trước khi ghi DB, thuận tiện cho luồng phân tán |
| Phụ thuộc | Version/hàm/extension trên PostgreSQL | Phiên bản thư viện và cách cấu hình trên mọi client |
| Truyền ID | Có thể dùng `INSERT ... RETURNING id` | Gửi ID qua parameter, có thể dùng ngay trong message/tracing |
| Đồng nhất thuật toán | Theo database server được cấu hình | Phải bảo đảm mọi service dùng đúng generator |
| Thời gian trong ID | Đồng hồ server nếu sinh v7 ở DB | Đồng hồ của node ứng dụng nếu sinh v7 ở app |
| Rủi ro | Khác version khi deploy qua nhiều DB | Library lỗi, clock skew, cấu hình không đồng nhất |

### Database tự sinh, ứng dụng đọc lại ID

~~~sql
INSERT INTO customers_v4 (email, full_name)
VALUES ('em@example.test', 'Em')
RETURNING customer_id;
~~~

`RETURNING` giúp lấy giá trị server vừa sinh mà không cần chạy một truy vấn tìm kiếm dựa trên email sau đó.

### Ứng dụng tự sinh rồi chèn

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public static UUID createCustomer(
    Connection connection, String email, String name
) throws SQLException {
    UUID newId = UUID.randomUUID(); // UUIDv4 trong Java

    String sql = """
        INSERT INTO customers_v4 (customer_id, email, full_name)
        VALUES (?, ?, ?)
        """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setObject(1, newId);
        ps.setString(2, email);
        ps.setString(3, name);
        ps.executeUpdate();
    }
    return newId;
}
~~~

Ví dụ Java dùng `java.util.UUID.randomUUID()` để sinh **v4**, không phải v7. Nếu hệ thống cần v7 từ ứng dụng, phải thay bằng generator v7 phù hợp.

### Cần tránh điều gì khi sinh ở ứng dụng?

- Không tạo UUID bằng `Math.random()` hoặc bộ random đơn giản không đáp ứng yêu cầu của thuật toán.
- Không ghép UUID vào chuỗi SQL; dùng tham số bind.
- Không tạo UUID mới vô điều kiện mỗi lần retry nếu ID phải là idempotency key ổn định. Khi retry một thao tác đã gửi, có thể cần **tái sử dụng cùng request ID** theo thiết kế nghiệp vụ.
- Không coi `UUID.randomUUID()` là cơ chế xác thực hoặc token bảo mật.

Khi nhiều service cùng tạo ID, hãy thống nhất chính sách, giám sát xung đột và giữ `PRIMARY KEY`/`UNIQUE` tại database làm lớp kiểm soát cuối cùng.

## 12. UUID và bigint GENERATED AS IDENTITY: chọn gì?

PostgreSQL có cơ chế sinh khóa số bằng identity column:

~~~sql
CREATE TABLE customers_identity (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL UNIQUE
);
~~~

So sánh:

| Đặc tính | `bigint identity` | UUIDv4 | UUIDv7 |
| --- | --- | --- | --- |
| Kích thước giá trị | 8 byte | 16 byte | 16 byte |
| Cách sinh phổ biến | Sequence của database | Random tại DB hoặc app | Time-ordered tại DB 18+ hoặc app |
| ID có thể tạo offline độc lập | Không mặc định | Có | Có |
| Thứ tự ID có ý nghĩa thời gian | Gần theo thứ tự cấp số, nhưng không đảm bảo commit | Không | Có xu hướng theo timestamp, không đảm bảo commit |
| Chèn B-tree | Thường gần vùng cuối index | Phân tán ngẫu nhiên | Thường có tính cục bộ theo thời gian |
| Khả năng đoán ID tiếp theo | Dễ suy đoán theo chuỗi số | Khó dự đoán hơn | Có thể lộ thông tin thời gian |
| Độ đơn giản | Rất đơn giản ở hệ một DB | Hỗ trợ rộng từ nhiều hệ | Cần kiểm tra version/generator |

Không có lựa chọn “thắng” trong mọi hệ thống.

- Nếu ứng dụng chỉ ghi vào một PostgreSQL, cần ID nội bộ đơn giản, `bigint identity` có thể hiệu quả và dễ quản lý.
- Nếu ID phải được tạo ở nhiều dịch vụ/máy trước khi ghi, UUID thuận tiện hơn.
- Nếu cần UUID nhưng muốn cải thiện locality ở các bảng ghi lớn, có thể cân nhắc UUIDv7 khi generator đủ tin cậy.
- Nếu đã có khóa chính `bigint` ổn định và workload tốt, không cần thay đổi chỉ vì UUID đang phổ biến.

**Đừng dùng UUID thay quyền truy cập.** Cả khóa số và UUID đều chỉ là định danh; API vẫn phải kiểm tra chủ sở hữu/tenant.

## 13. Lưu UUID dưới kiểu uuid, không phải text tùy tiện

Giả sử cùng một ID được lưu trong hai kiểu cột:

~~~sql
CREATE TABLE bad_identifiers (
    id_text text PRIMARY KEY
);

CREATE TABLE good_identifiers (
    id uuid PRIMARY KEY
);
~~~

Với `text`, database không mặc nhiên kiểm tra dữ liệu theo cú pháp UUID. Có thể ghi các chuỗi không hợp lệ như `'abc'`, chữ hoa/thường không chuẩn hóa hoặc các định dạng khác nhau của cùng một định danh.

Với `uuid`:

- Giá trị được kiểm tra và chuẩn hóa theo kiểu UUID khi parse.
- Lưu dạng 128 bit thay vì chuỗi ký tự có overhead riêng.
- Có toán tử và B-tree operator class phù hợp.
- Client/JDBC có thể truyền kiểu `java.util.UUID`.
- Có thể dùng khóa ngoại cùng kiểu dữ liệu một cách rõ ràng.

Ví dụ:

~~~sql
SELECT
    'A0EEBC99-9C0B-4EF8-BB6D-6BB9BD380A11'::uuid
        AS canonical_uuid;
~~~

Kết quả được hiển thị theo dạng UUID chuẩn chữ thường.

### Truy vấn theo UUID đúng kiểu

~~~sql
SELECT customer_id, email
FROM customers_v4
WHERE customer_id =
      'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid;
~~~

Khi truyền từ ứng dụng, ưu tiên bind UUID:

~~~java
UUID id = UUID.fromString(inputId);

String sql =
    "SELECT email FROM customers_v4 WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("email"));
        }
    }
}
~~~

`UUID.fromString` có thể ném `IllegalArgumentException` nếu chuỗi không hợp lệ; ở lớp API cần chuyển thành lỗi đầu vào phù hợp thay vì lỗi server. Ví dụ giả định có các import JDBC và biến `connection` hợp lệ.

**Không ép cột thành text để so khớp nếu không có lý do**, như:

~~~sql
-- Không phải lựa chọn thông thường cho lookup theo khóa chính UUID:
WHERE customer_id::text = '...'
~~~

Phép ép kiểu trên cột có thể khiến B-tree index thông thường trên `customer_id` không còn được sử dụng theo cách tối ưu cho điều kiện bằng UUID. Giữ điều kiện so sánh ở kiểu `uuid` và bind tham số đúng kiểu.

## 14. UUID làm khóa ngoại và khóa ghép

UUID có thể dùng làm foreign key hoàn toàn bình thường.

~~~sql
CREATE TABLE customer_addresses_v4 (
    address_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id uuid NOT NULL
        REFERENCES customers_v4(customer_id)
        ON DELETE CASCADE,
    address_text text NOT NULL
);

CREATE INDEX idx_addresses_customer_id
ON customer_addresses_v4(customer_id);
~~~

Khi thêm địa chỉ, cần ID khách hàng thực tế đã có:

~~~sql
INSERT INTO customer_addresses_v4 (customer_id, address_text)
SELECT customer_id, '12 Example Street'
FROM customers_v4
WHERE email = 'an@example.test';
~~~

Khóa ngoại trên UUID có cùng nguyên tắc như khóa ngoại trên số: PostgreSQL kiểm tra bản ghi cha tồn tại, ngăn/xử lý việc xóa theo `ON DELETE` và bảo vệ tính toàn vẹn tham chiếu.

**Lưu ý chỉ mục:** `PRIMARY KEY` tạo index trên khóa cha; PostgreSQL **không tự tạo index trên mọi cột FK ở bảng con**. Với các truy vấn lọc theo `customer_id` hoặc khi xóa/sửa bản ghi cha, index ở phía bảng con thường hữu ích.

Nếu một bảng liên kết có hai UUID FK:

~~~sql
CREATE TABLE memberships_v4 (
    customer_id uuid NOT NULL
        REFERENCES customers_v4(customer_id),
    group_id uuid NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, group_id)
);
~~~

thì khóa chính ghép bảo đảm một cặp duy nhất. Nếu `group_id` cần tham chiếu một bảng nhóm thực, phải tạo bảng đó và thêm foreign key phù hợp; chỉ khai báo kiểu `uuid` không tự tạo quan hệ.

## 15. UUIDv4 và UUIDv7 ảnh hưởng gì tới index?

Khóa chính PostgreSQL mặc định được hỗ trợ bởi B-tree index; UUID cũng sử dụng được kiểu index này.

### UUIDv4: giá trị ngẫu nhiên

Khi `INSERT` liên tục với UUIDv4, khóa mới có thể rơi vào nhiều vị trí khác nhau trong B-tree. Ở bảng lớn và tần suất ghi cao, điều này có thể tăng hoạt động ghi/chia trang và tác động cache.

### UUIDv7: gần theo thứ tự thời gian

Với UUIDv7, phần đầu chứa thông tin thời gian nên các khóa mới có xu hướng dồn vào vùng cuối của index hơn. Đây là ưu thế tiềm năng cho các workload insert-heavy.

~~~mermaid
flowchart LR
    A["Luồng INSERT liên tục"] --> B{"Chiến lược ID"}
    B -->|"UUIDv4"| C["Khóa phân tán theo không gian UUID"]
    B -->|"UUIDv7"| D["Khóa có xu hướng tăng theo timestamp"]
    C --> E["Có thể tác động nhiều vùng B-tree"]
    D --> F["Có thể tăng locality khi ghi"]
    E --> G["Đo với workload thật"]
    F --> G
~~~

Nhưng điều này là **đặc tính xu hướng**, không phải phép đo. Không dùng một sơ đồ để kết luận 100% rằng v7 luôn nhanh hơn v4 hoặc nhỏ bằng bigint.

Các yếu tố cần đo:

1. Tốc độ `INSERT` và độ trễ transaction.
2. Kích thước và mức phân mảnh của B-tree index.
3. WAL, cache hit, I/O và page splits trong workload đại diện.
4. Tốc độ `UPDATE`/`DELETE` và số lượng foreign key liên quan.
5. Độ đồng thời, phân bố dữ liệu và tỷ lệ ghi/đọc.
6. Cách tạo ID từ nhiều service, mức lệch đồng hồ và khả năng backfill dữ liệu cũ.

Cần chạy benchmark trên một môi trường test phù hợp; không dùng một bảng vài chục hàng để suy ra kết quả cho hàng trăm triệu hàng.

## 16. UUIDv7 không thay thế trường thời gian nghiệp vụ

Do v7 chứa timestamp, có thể nghĩ rằng không cần cột `created_at`. Đây là một nhầm lẫn.

So sánh:

| Thông tin | UUIDv7 | `created_at timestamptz` |
| --- | --- | --- |
| Có thông tin thời gian | Có, trong ID | Có, tường minh |
| Ý nghĩa mặc định | Thời điểm generator dùng để sinh UUID | Theo cách ứng dụng/DB định nghĩa |
| Có thể dùng SQL time range thuận tiện | Cần trích/so sánh theo cơ chế UUID | Trực tiếp với timestamp |
| Thể hiện thời gian commit chính xác | Không | Cũng không mặc nhiên, nếu ghi bằng `now()` trước commit |
| Có thể áp dụng index range theo thời gian | Có tính sắp xếp tương đối của UUIDv7 | Có B-tree/BRIN theo timestamp khi phù hợp |
| Phù hợp làm bằng chứng audit duy nhất | Không | Cũng cần thiết kế audit và nguồn thời gian đáng tin |

Ví dụ truy vấn sự kiện theo thời gian nghiệp vụ:

~~~sql
SELECT event_id, event_type, created_at
FROM events_v7
WHERE created_at >= timestamptz '2026-11-01 00:00:00+00'
  AND created_at <  timestamptz '2026-12-01 00:00:00+00'
ORDER BY created_at, event_id;
~~~

Dùng một khoảng **nửa mở** giúp tránh giả định độ chính xác cuối ngày. Với truy vấn kiểu này, có thể cân nhắc index trên `created_at` theo workload.

`uuid_extract_timestamp` trong PostgreSQL 18 có thể hữu ích cho phân tích kỹ thuật và kiểm chứng UUIDv7, nhưng thời gian trích từ ID không nhất thiết là timestamp nghiệp vụ chính xác.

## 17. Quy trình thực hành có hai nhánh theo phiên bản

Để không gặp lỗi “function does not exist”, hãy **chọn nhánh phù hợp** thay vì chạy mọi câu lệnh trong cùng một file.

### Nhánh A: PostgreSQL 13–18, UUIDv4

Trong một database lab riêng:

~~~sql
CREATE SCHEMA IF NOT EXISTS uuid_lab;

CREATE TABLE uuid_lab.notes_v4 (
    note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    note_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO uuid_lab.notes_v4 (note_text)
VALUES
    ('Ghi chu dau tien'),
    ('Ghi chu thu hai')
RETURNING note_id, note_text;

SELECT
    note_id,
    note_text,
    pg_column_size(note_id) AS uuid_bytes
FROM uuid_lab.notes_v4
ORDER BY created_at, note_id;
~~~

Kết quả dự kiến là hai hàng, mỗi `note_id` có kiểu UUID và mỗi giá trị UUID có kích thước 16 byte. Giá trị ID sẽ khác nhau mỗi lượt.

Nếu bảng đã tồn tại do chạy lab trước, không chạy lại `CREATE TABLE` mà không xử lý trạng thái. Với lab dùng chung, nên tạo database/schema riêng theo lượt hoặc xóa bảng **chỉ khi chắc chắn đó là dữ liệu thực hành của mình**.

### Nhánh B: chỉ PostgreSQL 18, UUIDv7

~~~sql
CREATE SCHEMA IF NOT EXISTS uuid_lab;

CREATE TABLE uuid_lab.notes_v7 (
    note_id uuid PRIMARY KEY DEFAULT uuidv7(),
    note_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO uuid_lab.notes_v7 (note_text)
VALUES
    ('Su kien A'),
    ('Su kien B')
RETURNING
    note_id,
    uuid_extract_version(note_id) AS version,
    uuid_extract_timestamp(note_id) AS timestamp_in_uuid;

SELECT note_id, note_text
FROM uuid_lab.notes_v7
ORDER BY note_id;
~~~

Các giá trị mới `note_id` được sinh bằng UUIDv7. Truy vấn `uuid_extract_version` trả `7` cho các giá trị do `uuidv7()` tạo ra. Các ID có xu hướng theo thứ tự thời gian, nhưng với hai hàng được thêm gần nhau không nên khẳng định mọi timestamp khác nhau hoặc thứ tự ID là thứ tự commit chính xác.

### Nhánh C: PostgreSQL 12 trở xuống, UUIDv4 qua extension

~~~sql
-- Chỉ chạy nếu server có pgcrypto và tài khoản có quyền cài.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS uuid_lab;

CREATE TABLE uuid_lab.notes_legacy (
    note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    note_text text NOT NULL
);

INSERT INTO uuid_lab.notes_legacy (note_text)
VALUES ('Ghi chu phien ban cu')
RETURNING note_id;
~~~

Nếu `pgcrypto` không thể cài, cần xem chính sách server/managed service; không lách quyền hoặc sao chép thủ công các hàm không rõ nguồn. Có thể cân nhắc `uuid-ossp` hoặc sinh UUID ở ứng dụng.

### Kiểm tra một UUID cụ thể có hợp lệ không

~~~sql
SELECT
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid AS valid_uuid;
~~~

Một chuỗi không phải UUID hợp lệ sẽ gây lỗi ép kiểu:

~~~sql
-- Ví dụ cố ý lỗi, chạy riêng khi học xử lý lỗi.
SELECT 'not-a-uuid'::uuid;
~~~

Không dùng việc ép kiểu lỗi trực tiếp trong một script di chuyển dữ liệu production. Khi dữ liệu nguồn chưa được kiểm tra, cần một quy trình validation và xử lý dữ liệu sai trước khi đổi kiểu cột.

## 18. Chuyển một bảng đang dùng bigint sang UUID: cần kế hoạch migration

Không thể chỉ chạy:

~~~sql
-- Không phải phép chuyển đổi mặc định có ngữ nghĩa:
ALTER TABLE orders
ALTER COLUMN id TYPE uuid;
~~~

Giá trị `bigint` không tự có một ánh xạ UUID chuẩn. Nếu có bảng con đang tham chiếu `orders.id`, việc đổi khóa chính còn ảnh hưởng tất cả foreign key, ứng dụng, index, cache, API và dữ liệu liên kết.

Một kế hoạch ở mức ý tưởng:

1. **Xác định lý do:** có cần ID phân tán, giảm rủi ro đoán ID hay cải thiện index locality không?
2. **Chọn UUID version và generator** tương thích mọi server/client cần ghi.
3. **Thêm cột UUID mới** với cách backfill đã kiểm soát; cân nhắc bảng lớn và tránh khóa kéo dài.
4. **Cấp UUID cho toàn bộ bản ghi cũ** và bảo đảm unique; không sinh lại ID một cách tùy tiện khi chạy lại migration.
5. **Thêm cột UUID ở bảng con**, populate theo mapping `old_id → new_uuid` và kiểm chứng không có tham chiếu mồ côi.
6. **Tạo index/constraint đúng thứ tự**, cân nhắc kỹ thuật online/concurrent index ở nơi hỗ trợ.
7. **Chuyển ứng dụng qua dual-read/dual-write có kiểm soát** hoặc qua đợt triển khai được thiết kế phù hợp.
8. **Kiểm tra dữ liệu, khóa ngoại và rollback strategy**, rồi mới chuyển primary key chính thức.
9. **Chỉ xóa ID cũ** sau khi mọi consumer đã chuyển và có phương án khôi phục.

Một số migration có thể chọn giữ `bigint` làm **khóa chính nội bộ** và thêm `public_id uuid UNIQUE` cho API:

~~~sql
CREATE TABLE example_orders_public_id (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    order_status text NOT NULL
);
~~~

Cách này giúp giữ các foreign key nội bộ nhỏ và ổn định trong khi ứng dụng ngoài dùng UUID. Đánh đổi là phải có cả hai cột, thêm index và mapping trong code.

Không nên đổi khóa chính production chỉ vì muốn URL có vẻ ngẫu nhiên hơn. Phân quyền vẫn là yêu cầu bắt buộc, và việc thêm một external identifier có thể ít rủi ro hơn thay toàn bộ khóa quan hệ.

## 19. Kiểm chứng UUID và xử lý lỗi tại lớp ứng dụng

### Giá trị UUID không đúng định dạng

Khi ép từ `text`/`varchar` sang `uuid`, PostgreSQL sẽ kiểm tra cú pháp. Ví dụ:

~~~sql
SELECT 'not-a-uuid'::uuid;
~~~

Lỗi ép kiểu không phải “không tìm thấy bản ghi”; nó là lỗi đầu vào. Trong API nên trả lỗi validation thích hợp thay vì để SQL exception không được xử lý thành lỗi máy chủ 500.

### Trùng ID

Ngay cả nếu generator rất đáng tin cậy, database vẫn cần khóa chính. Khi `INSERT` gặp UUID đã tồn tại, PostgreSQL phát sinh lỗi vi phạm unique (SQLSTATE `23505`). Ứng dụng cần phân biệt **retry cùng thao tác** với **collision thật hoặc dữ liệu bất thường**.

Không giải quyết mọi lỗi unique bằng cách tự động sinh ID mới rồi thử lại vô hạn. Với tác vụ idempotent hoặc đã phát event chứa ID cũ, việc đổi ID có thể phá vỡ liên kết và tạo dữ liệu lặp.

### Bảo mật API

Một UUID trông khó đoán nhưng không đồng nghĩa có thể truy cập tự do:

~~~sql
SELECT order_status
FROM example_orders_public_id
WHERE public_id = $1;
~~~

Truy vấn này chưa diễn đạt điều kiện người dùng có quyền xem đơn. Cần kết hợp owner/tenant/authorization từ ngữ cảnh đã xác thực theo thiết kế hệ thống.

UUIDv7 có phần thời gian, UUIDv1 có thể tiết lộ thông tin node và thời gian; không sử dụng những UUID này như credential bí mật hoặc token xác thực.

## 20. Những sai lầm thường gặp khi chọn generator

### Sai lầm 1: PostgreSQL có kiểu uuid tức là có mọi hàm sinh UUID

Kiểu dữ liệu được hỗ trợ rộng, nhưng `uuidv7()` lõi chỉ có từ PostgreSQL 18. Kiểm tra `server_version` hoặc sự hiện diện của hàm trước khi viết migration.

### Sai lầm 2: PostgreSQL 17 cần pgcrypto để dùng gen_random_uuid()

Không cần. Từ PostgreSQL 13, `gen_random_uuid()` là hàm lõi sinh UUIDv4. `pgcrypto` có thể hữu ích vì các chức năng khác, không bắt buộc chỉ để tạo UUIDv4.

### Sai lầm 3: Cài uuid-ossp là có sẵn uuidv7()

`uuid-ossp` cung cấp những thuật toán truyền thống như v1, v3, v4, v5. Không giả định có `uuid_generate_v7()` trên PostgreSQL 17 chỉ vì extension đã cài.

### Sai lầm 4: Sinh UUIDv4 và mong ORDER BY id là thứ tự tạo

UUIDv4 ngẫu nhiên; thứ tự từ khóa `ORDER BY id` không thể hiện trình tự tạo bản ghi. Nếu cần thời gian, dùng `created_at` hoặc một cơ chế thứ tự phù hợp.

### Sai lầm 5: Dùng UUIDv7 rồi bỏ created_at

UUIDv7 cho thông tin thời gian gần đúng của generator, không thay thế thời gian nghiệp vụ, thời gian commit, audit hay chính sách sắp xếp khi có nhiều nguồn.

### Sai lầm 6: Nghĩ UUIDv7 chắc chắn nhanh hơn bigint và UUIDv4

UUIDv7 có ưu thế locality tiềm năng nhưng vẫn 16 byte, có overhead index và ảnh hưởng từ workload. Cần đo dữ liệu thật.

### Sai lầm 7: Lưu UUID trong varchar(36) vì nhìn giống chuỗi

Dùng kiểu `uuid` để PostgreSQL kiểm tra, chuẩn hóa và lưu dữ liệu hiệu quả. Chuyển sang text chỉ khi có lý do tương thích cụ thể.

### Sai lầm 8: Dùng cùng UUID làm mã bí mật để phân quyền

ID chỉ để định danh, không thay kiểm tra quyền. Tránh giả định khó đoán ID đồng nghĩa an toàn truy cập.

### Sai lầm 9: Tạo UUID mới ở mỗi lần retry bất kể trạng thái

Nếu một request đã được xử lý nhưng client mất kết nối trước khi nhận phản hồi, retry với ID mới có thể tạo bản ghi thứ hai. Cần thiết kế idempotency theo nghiệp vụ, không dựa riêng vào sự hiếm trùng UUID.

### Sai lầm 10: Bỏ qua việc rollout nhiều phiên bản database

Ứng dụng ghi vào PostgreSQL 18 dùng `uuidv7()` làm default, nhưng migration/replica hay môi trường staging chạy phiên bản thấp hơn có thể lỗi. Cần xác định phiên bản thấp nhất của server **thực thi biểu thức** và kiểm soát lộ trình nâng cấp.

### Sai lầm 11: Trích timestamp từ UUID trên mọi PostgreSQL

`uuid_extract_timestamp()` có hành vi hỗ trợ khác nhau theo version. Trên PostgreSQL 18 hỗ trợ UUIDv1/v7, còn phiên bản trước không mặc nhiên hỗ trợ v7.

### Sai lầm 12: Kết luận không có collision nên bỏ PRIMARY KEY

Thuật toán có xác suất trùng rất thấp nhưng không thay thế constraint. Với dữ liệu quan trọng, database vẫn phải kiểm soát tính duy nhất.

## 21. Bài tập thực hành

### Bài 1: Chọn generator cho PostgreSQL 16

Một bảng `api_requests` cần khóa chính UUID, server là PostgreSQL 16, không muốn cài extension. Viết DDL.

**Đáp án:**

~~~sql
CREATE TABLE api_requests (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_path text NOT NULL
);
~~~

Đây là UUIDv4 do hàm lõi sinh.

### Bài 2: Chọn generator cho PostgreSQL 18

Một bảng sự kiện ghi nhiều cần ID có xu hướng sắp theo thời gian. Viết DDL và chèn một bản ghi.

**Đáp án:**

~~~sql
CREATE TABLE audit_events (
    event_id uuid PRIMARY KEY DEFAULT uuidv7(),
    event_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO audit_events (event_type)
VALUES ('document_updated')
RETURNING event_id, created_at;
~~~

`uuidv7()` yêu cầu PostgreSQL 18 trở lên. `created_at` lưu ngữ nghĩa thời gian riêng.

### Bài 3: PostgreSQL 12 báo function gen_random_uuid does not exist

Hãy giải thích vì sao và nêu một cách xử lý hợp lệ.

**Đáp án:** Ở PostgreSQL 12, `gen_random_uuid()` không phải hàm lõi. Có thể cài `pgcrypto` (nếu khả dụng, có quyền và được phép vận hành) hoặc dùng generator khác như `uuid-ossp`/thư viện ứng dụng. Cần cân nhắc nâng cấp major version vì PostgreSQL 12 đã hết hỗ trợ.

### Bài 4: Cùng UUIDv5 được sinh hai lần có trùng không?

~~~sql
SELECT uuid_generate_v5(
    uuid_ns_url(),
    'https://example.test/items/42'
);
~~~

Nếu cùng extension, namespace và chuỗi tên không đổi, UUID được tạo **giống nhau** giữa các lượt. Nếu muốn mỗi lần chèn là một ID khác, UUIDv5 xác định theo tên không phải lựa chọn phù hợp.

### Bài 5: Vì sao UUIDv4 không phù hợp làm thứ tự bản ghi?

~~~sql
SELECT customer_id
FROM customers_v4
ORDER BY customer_id;
~~~

Bài tập: chạy lại sau khi chèn nhiều hàng. Kết quả sắp theo **giá trị UUID**, không theo thời gian tạo, vì v4 ngẫu nhiên.

### Bài 6: Phân biệt UUID và varchar

Thiết kế bảng `orders(id uuid)` và `orders_text(id varchar(36))`. Kiểu nào kiểm tra đầu vào đúng UUID tự động? Kiểu nào có giá trị logic 16 byte và operator/index tương ứng?

**Đáp án:** `uuid`. `varchar(36)` chỉ kiểm soát độ dài chuỗi và có thể chứa ký tự không phải UUID nếu không có validation riêng.

### Bài 7: UUIDv7 ở ứng dụng Java với PostgreSQL 17

Ứng dụng có thư viện tạo UUIDv7 chuẩn và PostgreSQL 17 chỉ cần lưu ID. Thiết kế cách chèn.

**Đáp án:** Cột có kiểu `uuid`; ứng dụng sinh UUIDv7 bằng thư viện và truyền qua `PreparedStatement.setObject(index, javaUuid)`. Không gọi `uuidv7()` phía SQL trên PostgreSQL 17 nếu không có extension cung cấp hàm riêng được kiểm chứng.

### Bài 8: Bảo vệ khóa ngoại

Bảng `customers_v4` có `customer_id uuid PRIMARY KEY`. Một bảng `orders_v4` có `customer_id uuid`. Ràng buộc nào cần thêm để tránh tham chiếu khách hàng không tồn tại và tránh đơn thiếu khách hàng?

**Đáp án:**

~~~sql
customer_id uuid NOT NULL
    REFERENCES customers_v4(customer_id)
~~~

Nên cân nhắc index ở phía bảng `orders_v4` theo workload, vì PostgreSQL không tự tạo mọi index trên cột FK.

### Bài 9: Nên đổi bigint cũ sang uuid toàn bộ không?

Một hệ thống có hàng trăm bảng con đang dùng `bigint` foreign key, nhưng cần public ID không dễ đoán. Hãy nêu lựa chọn ít tác động hơn.

**Gợi ý:** Giữ `bigint` làm khóa nội bộ, thêm `public_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid()` tại các bảng cần public ID, sau đó chuyển API sử dụng public ID. Vẫn cần kiểm tra phân quyền đầy đủ.

## 22. Quy trình chọn UUID theo phiên bản và yêu cầu

~~~mermaid
flowchart TD
    A["Cần ID mới"] --> B{"Phải là UUID?"}
    B -->|"Không"| C["Xem bigint IDENTITY và các khóa nghiệp vụ"]
    B -->|"Có"| D{"Muốn UUID gần theo thời gian?"}
    D -->|"Không"| E{"PostgreSQL >= 13?"}
    E -->|"Có"| F["gen_random_uuid() - UUIDv4 lõi"]
    E -->|"Không"| G["pgcrypto / uuid-ossp / ứng dụng"]
    D -->|"Có"| H{"PostgreSQL >= 18?"}
    H -->|"Có"| I["uuidv7() lõi"]
    H -->|"Không"| J["Ứng dụng/extension v7 đã được kiểm chứng"]
    F --> K["Chọn DB DEFAULT hay app generator"]
    G --> K
    I --> K
    J --> K
    K --> L["PRIMARY KEY/UNIQUE, index và quyền truy cập"]
~~~

Có thể chuyển sơ đồ thành các câu hỏi khi thiết kế thực tế:

1. **Cần định danh cục bộ hay phân tán?** Nếu chỉ cần ID trong một database, `bigint identity` có thể đủ.
2. **Cần version nào?** v4 đơn giản, phổ biến; v7 có xu hướng theo thời gian; v5 dành cho ID xác định theo tên.
3. **Server chạy phiên bản nào?** 13–17 có `gen_random_uuid()`; PostgreSQL 18 có thêm `uuidv7()` và `uuidv4()`.
4. **Ai sinh ID?** Database `DEFAULT` hoặc ứng dụng; phải nhất quán giữa các dịch vụ.
5. **Dữ liệu được lưu bằng kiểu gì?** Dùng `uuid`, không mặc định dùng text.
6. **Có yêu cầu truy vấn hay index nào?** Xem khóa ngoại, B-tree locality, `created_at`, phân trang và tổng tải ghi.
7. **Có yêu cầu bảo mật nào?** UUID không thay thế authorization, idempotency hay audit.
8. **Có cần tương thích/upgrade?** Kiểm tra môi trường staging, replica, disaster recovery và mức PostgreSQL tối thiểu mà migration phải chạy.

## 23. Tài liệu tham khảo chính thức

Để kiểm tra chính xác khi nâng cấp hoặc vận hành trên một major version cụ thể:

- [PostgreSQL 18 — UUID Type](https://www.postgresql.org/docs/18/datatype-uuid.html): kiểu dữ liệu, định dạng lưu và ý nghĩa UUID.
- [PostgreSQL 18 — UUID Functions](https://www.postgresql.org/docs/18/functions-uuid.html): `gen_random_uuid()`, `uuidv4()`, `uuidv7()` và hàm trích version/timestamp.
- [PostgreSQL 17 — UUID Functions](https://www.postgresql.org/docs/17/functions-uuid.html): các hàm lõi trước khi có `uuidv7()`.
- [PostgreSQL 13 — UUID Functions](https://www.postgresql.org/docs/13/functions-uuid.html): mốc `gen_random_uuid()` có trong lõi.
- [PostgreSQL 12 — pgcrypto](https://www.postgresql.org/docs/12/pgcrypto.html): nguồn sinh UUIDv4 ở phiên bản cũ.
- [PostgreSQL 18 — uuid-ossp](https://www.postgresql.org/docs/18/uuid-ossp.html): các hàm UUIDv1/v3/v4/v5 bổ sung.
- [PostgreSQL — Versioning Policy](https://www.postgresql.org/support/versioning/): xác định major version nào còn được hỗ trợ.

## 24. Tổng kết

**Kiểu `uuid` không đồng nghĩa với một hàm sinh UUID cố định trên mọi PostgreSQL.** Để viết migration và ứng dụng đúng, cần phân biệt phiên bản **PostgreSQL** với version **UUID**:

- **PostgreSQL 13–17:** dùng `gen_random_uuid()` lõi để sinh UUIDv4, không cần `pgcrypto` chỉ cho mục đích này.
- **PostgreSQL 18:** có thêm `uuidv7()` sinh UUIDv7 theo thời gian và `uuidv4()` là tên gọi tường minh cho v4.
- **PostgreSQL 12 trở xuống:** có thể sinh UUIDv4 qua extension `pgcrypto` hoặc `uuid-ossp` khi được phép và môi trường hỗ trợ.
- **Bất kỳ phiên bản hỗ trợ kiểu uuid nào:** có thể nhận UUID do ứng dụng tạo, kể cả UUID version mà server chưa có generator lõi.

Chọn v4 khi cần định danh ngẫu nhiên đơn giản; cân nhắc v7 khi cần UUID có tính thứ tự theo thời gian và index locality; dùng v5 cho ánh xạ namespace–name xác định. Dù chọn phương án nào, vẫn phải giữ constraint duy nhất, khóa ngoại, kiểm tra quyền và cơ chế lưu thời gian nghiệp vụ độc lập khi cần.

Một định danh tốt không chỉ đúng định dạng: nó phải tương thích phiên bản đang chạy, được sinh đáng tin cậy và phù hợp với các truy vấn, index, migration và yêu cầu vận hành của hệ thống.
