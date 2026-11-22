# Kiểu địa chỉ mạng, bit và kiểu hình học tích hợp trong PostgreSQL

Trong PostgreSQL, dữ liệu không chỉ có `INTEGER`, `TEXT`, `BOOLEAN` và `TIMESTAMP`. Hệ quản trị còn cung cấp những **kiểu dữ liệu chuyên biệt** để lưu địa chỉ IP, dải mạng, địa chỉ phần cứng, chuỗi bit và các hình học phẳng hai chiều. Những kiểu này có quy tắc kiểm tra dữ liệu, toán tử và hàm riêng, giúp câu SQL phản ánh đúng bản chất thông tin hơn so với việc lưu mọi thứ bằng `TEXT`.

Ví dụ, khi lưu địa chỉ IP dạng chuỗi, câu truy vấn phải tự xử lý cú pháp IPv4/IPv6 và việc một địa chỉ có thuộc mạng `192.168.10.0/24` hay không. Với kiểu `inet` và `cidr`, PostgreSQL có toán tử cho bài toán đó. Khi lưu tám cờ tính năng trong một chuỗi bit, kiểu `bit(8)` cho phép thao tác AND, OR, XOR và dịch bit. Khi quản lý một tọa độ `(x, y)`, kiểu `point` cùng các toán tử hình học có thể tính khoảng cách Euclid trực tiếp.

Bài học thuộc chương **Kiểu dữ liệu** của module **Database Engine Relational PostgreSQL**, trình bày ba nhóm:

1. **Kiểu mạng:** `inet`, `cidr`, `macaddr` và `macaddr8`.
2. **Kiểu bit:** `bit(n)`, `bit varying(n)`, các toán tử bitwise và thao tác trên từng bit.
3. **Kiểu hình học tích hợp:** `point`, `line`, `lseg`, `box`, `path`, `polygon` và `circle`.

Ngoài cú pháp, bài học làm rõ **ngữ nghĩa lưu trữ, kiểm tra dữ liệu, index, giới hạn và cách chọn kiểu** cho một thiết kế lược đồ thực tế. Những ví dụ dùng dữ liệu giả hoặc địa chỉ dành cho mạng nội bộ/tài liệu; không cần kết nối Internet hay thiết bị thật.

> Các kiểu hình học trong chương là **kiểu tích hợp của PostgreSQL**, không phải `geometry`/`geography` từ extension PostGIS. Chúng phục vụ các phép tính hình học phẳng cơ bản, **không tự hiểu hệ tọa độ địa lý, SRID, mét hay khoảng cách trên bề mặt Trái Đất**.

## 1. Vì sao chọn kiểu chuyên biệt thay vì TEXT?

Giả sử ta có bảng ghi truy cập:

~~~sql
CREATE TABLE access_log_text (
    log_id BIGINT PRIMARY KEY,
    client_ip TEXT NOT NULL
);
~~~

Bảng này chấp nhận cả chuỗi hợp lệ `192.168.10.12` lẫn chuỗi không phải IP như `hello-world`. Muốn kiểm tra một địa chỉ thuộc mạng nào, ứng dụng phải tự parse hoặc dùng những phép biến đổi chuỗi phức tạp.

Một thiết kế khác:

~~~sql
CREATE TABLE access_log_typed (
    log_id BIGINT PRIMARY KEY,
    client_ip INET NOT NULL
);
~~~

Khi chèn địa chỉ không hợp lệ, PostgreSQL có thể từ chối ngay tại ranh giới kiểu dữ liệu. Đồng thời:

~~~sql
SELECT
    log_id,
    client_ip
FROM access_log_typed
WHERE client_ip <<= CIDR '192.168.10.0/24';
~~~

là một câu SQL có ý nghĩa rõ ràng: tìm IP nằm trong hoặc bằng phạm vi mạng được chỉ định, theo semantics của toán tử mạng PostgreSQL.

Lợi ích của kiểu chuyên biệt:

- **Kiểm tra định dạng và miền giá trị** khi nhập dữ liệu.
- **Biểu diễn ngữ nghĩa** rõ ràng hơn tên cột đơn thuần.
- **Toán tử chuyên biệt** cho các tình huống không thích hợp với so sánh chuỗi.
- **Hàm chuyển đổi và truy vấn metadata** tương ứng.
- **Khả năng đánh chỉ mục** cho những phép toán được operator class hỗ trợ.
- **Giảm mã tự triển khai** parse/so sánh trong mỗi ứng dụng.

Nhưng chuyên biệt không đồng nghĩa luôn tốt hơn: ví dụ `bit(8)` khó bảo trì nếu mỗi bit mang ý nghĩa nghiệp vụ bí mật không được tài liệu hóa; kiểu `point` không đủ để làm hệ thống GIS đo khoảng cách theo mét trên toàn cầu.

## 2. Tổng quan các kiểu trong bài

| Kiểu | Biểu diễn | Ví dụ | Tình huống điển hình |
|---|---|---|---|
| `inet` | Địa chỉ IPv4/IPv6, có thể kèm độ dài prefix | `192.168.10.15/24`, `2001:db8::1` | IP client, host, endpoint |
| `cidr` | Một dải mạng IPv4/IPv6 chuẩn hóa theo prefix | `192.168.10.0/24` | ACL, subnet, route policy |
| `macaddr` | Địa chỉ MAC 48 bit | `08:00:2b:01:02:03` | Nhận diện phần cứng trong mạng phù hợp |
| `macaddr8` | Định danh dạng MAC/EUI-64 64 bit | `08:00:2b:ff:fe:01:02:03` | Địa chỉ phần cứng/EUI-64 |
| `bit(n)` | Chuỗi đúng `n` bit | `B'10100101'` | Cờ bit cố định, mã nhị phân ngắn |
| `bit varying(n)` | Chuỗi bit dài tối đa `n` bit | `B'101'` | Chuỗi bit có độ dài thay đổi |
| `point` | Tọa độ phẳng `(x,y)` | `(3,4)` | Vị trí trên mặt phẳng |
| `line` | Đường thẳng vô hạn | `{1,-1,0}` | Quan hệ giữa đường thẳng |
| `lseg` | Đoạn thẳng có hai đầu mút | `[(0,0),(3,4)]` | Đoạn đường/biên tuyến tính |
| `box` | Hình chữ nhật có cạnh song song trục tọa độ | `((0,0),(10,10))` | Hộp bao, kiểm tra giao nhau |
| `path` | Chuỗi điểm tạo đường mở hoặc khép kín | `[(0,0),(2,2),(4,0)]` | Đường đi phẳng |
| `polygon` | Đa giác phẳng | `((0,0),(4,0),(4,3),(0,3))` | Vùng hình học đơn giản |
| `circle` | Đường tròn theo tâm và bán kính | `<(0,0),5>` | Vùng bao hình tròn |

Số và ký hiệu trong bảng chỉ là ví dụ. Khi lưu các hình học phẳng, **đơn vị của tọa độ do ứng dụng quy định**, không do PostgreSQL tự suy ra.

## 3. Chuẩn bị môi trường thực hành

Cần có một PostgreSQL server và quyền tạo schema/bảng trong **database học tập riêng**. Có thể kết nối bằng `psql`, pgAdmin hoặc client hỗ trợ SQL.

Kiểm tra môi trường:

~~~sql
SELECT
    version() AS postgres_version,
    current_database() AS database_name,
    current_user AS role_name;
~~~

Trong bài, ta sử dụng schema `typed_lab` để phân biệt với bảng của ứng dụng khác:

~~~sql
CREATE SCHEMA typed_lab;
~~~

Lệnh này chạy một lần. Nếu schema đã tồn tại, PostgreSQL báo lỗi; không tự xóa schema thật chỉ để làm lại bài. Bạn có thể dùng database lab mới hoặc chọn tên schema riêng.

Các ví dụ `SELECT` sử dụng literal và không cần schema đều có thể thực hiện ngay. Phần tạo bảng sẽ dùng tên đầy đủ như `typed_lab.allowed_network` để không phụ thuộc `search_path`.

## 4. inet: kiểu địa chỉ IP có thể kèm prefix

`inet` lưu một địa chỉ IPv4 hoặc IPv6, với một **network prefix length** tùy chọn.

Ví dụ:

~~~sql
SELECT
    INET '192.168.10.15'       AS ipv4_host,
    INET '192.168.10.15/24'    AS ipv4_with_prefix,
    INET '2001:db8::1'        AS ipv6_host,
    INET '2001:db8::1/64'     AS ipv6_with_prefix;
~~~

Đối với địa chỉ host không ghi prefix, PostgreSQL hiểu host mask đầy đủ tương ứng: thường `/32` cho IPv4 và `/128` cho IPv6.

**Điểm cốt lõi:** `inet` có thể giữ địa chỉ host **có bit host khác 0 dù prefix ngắn hơn**. Vì vậy `192.168.10.15/24` là giá trị hợp lệ của `inet`, có cả địa chỉ host và prefix.

### 4.1. inet không chỉ dành cho IPv4

`inet` hỗ trợ IPv4 và IPv6 trong cùng một cột. Một ứng dụng có thể dùng:

~~~sql
CREATE TABLE typed_lab.access_event (
    event_id BIGINT PRIMARY KEY,
    remote_ip INET NOT NULL,
    event_name TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL
);
~~~

Nhờ vậy không cần hai cột `ipv4_address` và `ipv6_address` cho một trường có cùng ý nghĩa “địa chỉ IP của client”.

Tuy nhiên, một số chính sách kiểm tra hoặc index vẫn cần phân biệt IPv4/IPv6 qua hàm `family()`.

### 4.2. Giá trị hợp lệ và không hợp lệ

Ví dụ hợp lệ:

~~~sql
SELECT INET '10.20.30.40';
SELECT INET '2001:db8:0:1::1234';
~~~

Ví dụ không hợp lệ, **không chạy chung với script nạp dữ liệu thành công**:

~~~sql
-- Dự kiến lỗi: octet IPv4 ngoài miền cho phép.
-- SELECT INET '192.168.10.999';

-- Dự kiến lỗi: không phải địa chỉ IPv4/IPv6 hợp lệ.
-- SELECT INET 'not-an-ip';
~~~

Việc PostgreSQL chấp nhận một literal mạng còn phụ thuộc cú pháp đầu vào của kiểu; ứng dụng nên thống nhất định dạng chuẩn và không tự sáng chế cách cắt chuỗi.

## 5. cidr: kiểu dành cho dải mạng

`cidr` biểu diễn một **network address** cùng độ dài prefix, trong đó các bit phía host phải phù hợp với ranh giới của mạng.

Ví dụ:

~~~sql
SELECT
    CIDR '192.168.10.0/24' AS office_subnet,
    CIDR '10.0.0.0/8'      AS private_subnet,
    CIDR '2001:db8::/32'  AS ipv6_documentation_network;
~~~

Một dải `192.168.10.0/24` bao gồm các địa chỉ IPv4 có 24 bit đầu tương ứng với mạng đó.

Khác với `inet`:

~~~sql
-- Hợp lệ vì inet có thể chứa địa chỉ host + prefix:
SELECT INET '192.168.10.15/24';

-- Không phù hợp kiểu cidr vì có bit host khác 0:
-- SELECT CIDR '192.168.10.15/24';
~~~

PostgreSQL yêu cầu giá trị `cidr` khớp ranh giới mạng; literal chứa bit host không thích hợp có thể bị từ chối.

### 5.1. Khi nào dùng inet và khi nào dùng cidr?

| Câu hỏi | Ưu tiên |
|---|---|
| “Request này xuất phát từ IP nào?” | `inet` |
| “Máy chủ có IP nào trên interface?” | `inet` |
| “Subnet nào được phép truy cập?” | `cidr` |
| “Dải mạng nào thuộc vùng quản trị A?” | `cidr` |
| “Cần lưu host và subnet mask cùng nhau?” | `inet` |
| “Cần tránh lưu một dải mạng có bit host khác 0?” | `cidr` |

Không lưu một cột `cidr` tên `client_ip` rồi sử dụng nó như mã định danh host nếu ứng dụng thực tế cần phân biệt từng địa chỉ trong cùng mạng.

### 5.2. Prefix length không phải số octet

IPv4 có 32 bit; `/24` nghĩa là 24 bit đầu thuộc prefix, không phải 24 byte. IPv6 có 128 bit; `/64` nghĩa là 64 bit đầu.

~~~text
IPv4: 192.168.10.15/24
      11000000 10101000 00001010 | 00001111
      <-------- 24 bits ---------> | <-8 bits->

CIDR network: 192.168.10.0/24

IPv6: 2001:db8::1/64
      Prefix dài 64 bit trong địa chỉ 128 bit
~~~

Không tự dùng phép cắt chuỗi theo dấu chấm để xử lý IPv6; định dạng của IPv6 có nhiều cách rút gọn hợp lệ.

## 6. Hàm xử lý địa chỉ mạng

PostgreSQL có nhóm hàm thao tác trực tiếp trên `inet`/`cidr`.

### 6.1. host(), network(), masklen(), family()

~~~sql
SELECT
    host(INET '192.168.10.15/24') AS host_text,
    network(INET '192.168.10.15/24') AS network_part,
    masklen(INET '192.168.10.15/24') AS prefix_length,
    family(INET '192.168.10.15/24') AS address_family;
~~~

Ý nghĩa:

- `host()` trả về phần địa chỉ host dưới dạng văn bản theo cách hàm biểu diễn.
- `network()` trả về địa chỉ mạng tương ứng theo prefix.
- `masklen()` trả độ dài prefix.
- `family()` cho biết họ địa chỉ: `4` với IPv4, `6` với IPv6.

Kỳ vọng hợp lý: host là `192.168.10.15`, network là `192.168.10.0/24`, độ dài mask là `24`, họ địa chỉ là `4`.

### 6.2. broadcast(), netmask(), hostmask()

~~~sql
SELECT
    broadcast(INET '192.168.10.15/24') AS broadcast_address,
    netmask(INET '192.168.10.15/24') AS subnet_mask,
    hostmask(INET '192.168.10.15/24') AS host_mask;
~~~

Đối với IPv4 `/24`, các giá trị tương ứng giúp nhìn thấy mạng theo cách quen thuộc: địa chỉ broadcast `192.168.10.255`, subnet mask `255.255.255.0` và host mask `0.0.0.255`.

Không suy rằng khái niệm broadcast IPv4 hoạt động y hệt trong IPv6; các hàm thao tác địa chỉ được định nghĩa ở mức kiểu dữ liệu, nhưng semantics mạng thực tế khác nhau.

### 6.3. inet_same_family() và inet_merge()

~~~sql
SELECT
    inet_same_family(
        INET '192.168.1.10',
        INET '192.168.2.20'
    ) AS same_ip_family;

SELECT
    inet_merge(
        INET '192.168.10.0/24',
        INET '192.168.11.0/24'
    ) AS covering_network;
~~~

`inet_same_family` giúp kiểm tra hai địa chỉ thuộc cùng họ IPv4/IPv6. `inet_merge` có thể tạo dải CIDR nhỏ nhất bao trùm hai phạm vi đầu vào, hữu ích khi phân tích quy tắc mạng.

**Cần cẩn thận:** dải bao trùm nhỏ nhất có thể chứa thêm IP không nằm trong hai subnet ban đầu. Không tự hợp nhất policy ACL chỉ vì hai prefix trông gần nhau; phải kiểm tra tác động bảo mật.

## 7. Toán tử chứa/được chứa của kiểu mạng

Các toán tử mạng cho phép kiểm tra dải địa chỉ mà không tự xử lý bit bằng tay.

| Toán tử | Ý nghĩa cơ bản |
|---|---|
| `<<` | Bên trái **nằm trong một cách nghiêm ngặt** bên phải |
| `<<=` | Bên trái **nằm trong hoặc bằng** bên phải |
| `>>` | Bên trái **chứa nghiêm ngặt** bên phải |
| `>>=` | Bên trái **chứa hoặc bằng** bên phải |
| `&&` | Hai phạm vi địa chỉ có phần giao nhau |
| `=`, `<>` | So sánh bằng/khác theo semantics kiểu mạng |
| `<`, `<=`, `>`, `>=` | So sánh theo thứ tự mà PostgreSQL định nghĩa cho kiểu mạng |

Ví dụ:

~~~sql
SELECT
    INET '192.168.10.15' << CIDR '192.168.10.0/24'
        AS host_strictly_inside,

    INET '192.168.10.15' <<= CIDR '192.168.10.0/24'
        AS host_inside_or_equal,

    CIDR '192.168.10.0/24' >>= INET '192.168.10.15'
        AS subnet_contains_host,

    CIDR '192.168.10.0/24' && CIDR '192.168.10.128/25'
        AS ranges_overlap;
~~~

Các phép thử trên đều có kết quả **TRUE** theo định nghĩa chứa/bao phủ các dải tương ứng.

### 7.1. Phân biệt << với <<=
 
~~~sql
SELECT
    CIDR '10.20.0.0/16' << CIDR '10.20.0.0/16'
        AS strict_containment,

    CIDR '10.20.0.0/16' <<= CIDR '10.20.0.0/16'
        AS inclusive_containment;
~~~

Hai dải bằng nhau **không** thỏa quan hệ chứa nghiêm ngặt (`<<`), nhưng thỏa quan hệ chứa-hoặc-bằng (`<<=`).

Khi viết ACL hay kiểm tra subnet, lựa chọn sai giữa hai toán tử này có thể loại bỏ những kết quả hợp lệ.

### 7.2. Không nhầm thứ tự so sánh với IP “gần nhau”

Toán tử so sánh thứ tự của `inet`/`cidr` phục vụ quy tắc sắp xếp của PostgreSQL, **không đại diện cho khoảng cách mạng hoặc tuyến đường tối ưu**.

Muốn biết địa chỉ thuộc subnet, dùng toán tử containment. Muốn đánh giá độ ưu tiên của nhiều route, định nghĩa rõ chính sách như **longest prefix match** thay vì chỉ `ORDER BY remote_ip`.

## 8. Thiết kế bảng subnet và địa chỉ truy cập

Tạo bảng các phạm vi mạng được phép:

~~~sql
CREATE TABLE typed_lab.allowed_network (
    network_id INTEGER PRIMARY KEY,
    network_name TEXT NOT NULL,
    network_block CIDR NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO typed_lab.allowed_network
    (network_id, network_name, network_block)
VALUES
    (1, 'Office', CIDR '192.168.10.0/24'),
    (2, 'Office management', CIDR '192.168.10.128/25'),
    (3, 'Internal services', CIDR '10.20.0.0/16'),
    (4, 'IPv6 lab', CIDR '2001:db8:100::/48');

INSERT INTO typed_lab.access_event
    (event_id, remote_ip, event_name, observed_at)
VALUES
    (1001, INET '192.168.10.15', 'login',
        TIMESTAMPTZ '2026-03-01 08:00:00+00'),
    (1002, INET '192.168.10.200', 'read',
        TIMESTAMPTZ '2026-03-01 08:10:00+00'),
    (1003, INET '10.20.1.9', 'write',
        TIMESTAMPTZ '2026-03-01 08:20:00+00'),
    (1004, INET '2001:db8:100::8', 'login',
        TIMESTAMPTZ '2026-03-01 08:30:00+00'),
    (1005, INET '203.0.113.22', 'read',
        TIMESTAMPTZ '2026-03-01 08:40:00+00');
~~~

Các mạng dùng trong ví dụ gồm dải private và dải dành cho tài liệu. Chúng không phải policy bảo mật có thể sao chép trực tiếp lên production.

### 8.1. Tìm log thuộc một subnet

~~~sql
SELECT
    event_id,
    remote_ip,
    event_name
FROM typed_lab.access_event
WHERE remote_ip <<= CIDR '192.168.10.0/24'
ORDER BY event_id;
~~~

Kết quả là event `1001` và `1002`.

### 8.2. JOIN IP với mạng cho phép

~~~sql
SELECT
    e.event_id,
    e.remote_ip,
    n.network_name,
    n.network_block
FROM typed_lab.access_event AS e
JOIN typed_lab.allowed_network AS n
    ON e.remote_ip <<= n.network_block
WHERE n.enabled = TRUE
ORDER BY e.event_id, n.network_id;
~~~

Một IP có thể khớp **nhiều mạng lồng nhau**. Ví dụ `192.168.10.200` nằm trong cả `192.168.10.0/24` và `192.168.10.128/25`. Do đó JOIN có thể tạo nhiều dòng cho cùng một event.

Nếu nghiệp vụ cần **một kết quả ưu tiên** thay vì toàn bộ subnet phù hợp, phải xác định quy tắc.

### 8.3. Longest prefix match bằng LATERAL

~~~sql
SELECT
    e.event_id,
    e.remote_ip,
    matched.network_name,
    matched.network_block
FROM typed_lab.access_event AS e
LEFT JOIN LATERAL (
    SELECT
        n.network_name,
        n.network_block
    FROM typed_lab.allowed_network AS n
    WHERE n.enabled = TRUE
      AND e.remote_ip <<= n.network_block
    ORDER BY
        masklen(n.network_block) DESC,
        n.network_id
    LIMIT 1
) AS matched ON TRUE
ORDER BY e.event_id;
~~~

Giải thích:

- `LATERAL` cho phép truy vấn con dùng `e.remote_ip` của từng hàng.
- `masklen DESC` ưu tiên prefix dài hơn, tương ứng mạng cụ thể hơn.
- `n.network_id` giúp thứ tự ổn định nếu có nhiều bản ghi cùng mức prefix.
- `LEFT JOIN` vẫn giữ event không thuộc bất kỳ subnet đã bật nào.

Trong ứng dụng firewall/router thật, còn nhiều yếu tố chính sách khác như deny/allow priority, direction, protocol và default deny. **Longest prefix match chỉ là một quy tắc lựa chọn mạng**, không thay thế một policy engine hoàn chỉnh.

## 9. Index cho inet và cidr

PostgreSQL hỗ trợ các phương thức chỉ mục và operator class khác nhau. Việc chọn index phải dựa vào **toán tử truy vấn** và phiên bản PostgreSQL thực tế.

Cho truy vấn bằng hoặc sắp xếp theo IP:

~~~sql
CREATE INDEX idx_access_event_ip
ON typed_lab.access_event (remote_ip);
~~~

Đây là B-tree index thông thường. Nó hữu ích cho những điều kiện như `remote_ip = INET '192.168.10.15'` khi lượng dữ liệu và độ chọn lọc khiến planner thấy có lợi.

Với những câu truy vấn containment của `inet`/`cidr`, các operator class chuyên biệt trên **SP-GiST hoặc GiST** có thể phù hợp trên phiên bản hỗ trợ. Ví dụ về một hướng cần đánh giá:

~~~sql
-- Dùng trên bản PostgreSQL có opclass SP-GiST phù hợp.
CREATE INDEX idx_allowed_network_spgist
ON typed_lab.allowed_network
USING spgist (network_block);
~~~

Không suy rằng index nào cũng hỗ trợ mọi toán tử; phải đối chiếu operator class của server hiện tại và xem `EXPLAIN`.

~~~sql
EXPLAIN
SELECT event_id
FROM typed_lab.access_event
WHERE remote_ip <<= CIDR '192.168.10.0/24';
~~~

Trên bảng ví dụ chỉ có vài hàng, sequential scan có thể là lựa chọn tối ưu và **không chứng minh index bị lỗi**. Để đánh giá index, cần số lượng hàng, độ phân bố mạng và kiểu truy vấn đại diện workload.

### 9.1. Lưu ý về dữ liệu mạng và quyền riêng tư

IP có thể được coi là dữ liệu liên quan người dùng tùy bối cảnh. Khi lưu:

- Chỉ giữ thông tin cần thiết cho mục đích vận hành.
- Quy định retention phù hợp.
- Hạn chế ai được đọc log IP.
- Không dựa vào địa chỉ IP làm danh tính người dùng vĩnh viễn.
- Xem xét NAT, proxy, IPv6 privacy addresses và header do client cung cấp.

Nếu hệ thống ở sau reverse proxy, địa chỉ IP thực của client cần được xác định từ **chuỗi proxy tin cậy và cấu hình mạng**, không lấy một header do client tùy ý đặt rồi coi là chứng cứ.

## 10. macaddr: địa chỉ phần cứng 48 bit

`macaddr` lưu một địa chỉ MAC 6 byte (48 bit), thường được biểu diễn thành sáu nhóm hexadecimal.

Ví dụ:

~~~sql
SELECT
    MACADDR '08:00:2b:01:02:03' AS device_mac,
    MACADDR '08-00-2b-01-02-03' AS same_device_form;
~~~

PostgreSQL chấp nhận nhiều dạng biểu diễn đầu vào hợp lệ và chuẩn hóa giá trị theo định dạng xuất của kiểu.

Điều quan trọng:

- `macaddr` có miền dữ liệu và phép so sánh dành riêng cho địa chỉ phần cứng.
- Một địa chỉ MAC không phải địa chỉ IP.
- MAC là thông tin ở phạm vi liên kết mạng thích hợp, không phải một địa chỉ định tuyến xuyên Internet như IPv4/IPv6.
- MAC có thể bị thay đổi, giả mạo hoặc ngẫu nhiên hóa bởi thiết bị/hệ điều hành.
- Không dùng MAC đơn lẻ làm bằng chứng xác thực người dùng hoặc thiết bị.

Ví dụ bảng lưu thiết bị trong một hệ thống quản trị nội bộ:

~~~sql
CREATE TABLE typed_lab.device (
    device_id BIGINT PRIMARY KEY,
    asset_name TEXT NOT NULL,
    hardware_address MACADDR,
    feature_flags BIT(8) NOT NULL DEFAULT B'00000000',
    location_2d POINT
);

INSERT INTO typed_lab.device
    (device_id, asset_name, hardware_address, feature_flags, location_2d)
VALUES
    (
        201, 'Switch A',
        MACADDR '08:00:2b:01:02:03',
        B'10000100',
        point(2, 3)
    ),
    (
        202, 'Sensor B',
        MACADDR '02:11:22:33:44:55',
        B'01000001',
        point(7, 9)
    );
~~~

Cột `location_2d` chỉ là tọa độ phẳng trong sơ đồ tòa nhà giả định, **không phải kinh độ/vĩ độ hay bản đồ thực**.

## 11. macaddr8: địa chỉ phần cứng/EUI-64 64 bit

`macaddr8` biểu diễn định danh phần cứng 8 byte (64 bit), thường được dùng với những ngữ cảnh EUI-64 tương ứng.

~~~sql
SELECT
    MACADDR8 '08:00:2b:ff:fe:01:02:03'
        AS eui64_sample;
~~~

PostgreSQL có thể nhận một số dạng đầu vào 6 byte và chuyển theo quy tắc hỗ trợ của kiểu `macaddr8`, nhưng **không nên coi mọi chuỗi 48 bit và 64 bit là cùng một định danh vật lý** nếu hệ thống chưa xác định chính sách chuẩn hóa.

Bảng so sánh:

| Tiêu chí | macaddr | macaddr8 |
|---|---|---|
| Chiều dài định danh | 48 bit | 64 bit |
| Ví dụ biểu diễn | `08:00:2b:01:02:03` | `08:00:2b:ff:fe:01:02:03` |
| Mục đích | MAC/EUI-48 | EUI-64 hoặc biểu diễn tương ứng |
| Có thay thế inet/cidr không? | Không | Không |
| Có đủ để xác thực danh tính? | Không | Không |

Nếu ứng dụng không quản lý MAC/EUI-64 thật, không cần thêm cột `macaddr` chỉ để “có thêm địa chỉ mạng”. Địa chỉ MAC của người truy cập website từ xa thường **không khả dụng** ở tầng HTTP thông thường.

## 12. Bit string: một chuỗi bit khác số nguyên thế nào?

PostgreSQL có kiểu **bit string** để lưu chuỗi các giá trị 0/1.

Ví dụ:

~~~sql
SELECT
    B'1010' AS bits_4,
    B'00001111' AS bits_8,
    X'AF' AS bits_from_hex;
~~~

Các literal:

- `B'1010'` là literal nhị phân gồm 4 bit.
- `X'AF'` là literal hexadecimal biểu diễn các bit tương ứng.
- `bit` và `varbit` là kiểu chuỗi bit, không phải kiểu số nguyên thông thường.

Bit string khác integer ở chỗ **độ dài và vị trí bit là một phần ngữ nghĩa quan trọng**. Ví dụ `B'0010'` có 4 bit; số nguyên 2 không ghi nhớ cách biểu diễn có hai bit 0 ở đầu.

Một số ứng dụng:

- Cờ tính năng đã được quy định vị trí bit.
- Trường bitmap trong giao thức.
- Mẫu bit ngắn trong dữ liệu kỹ thuật.
- Kết quả encode của một thuật toán có định dạng cố định.
- Bộ dấu hiệu thiết bị được ánh xạ tới các bit cụ thể.

Với vài thuộc tính nghiệp vụ độc lập, nhiều cột `BOOLEAN` có thể dễ đọc và truy vấn hơn một bitmap.

## 13. bit(n): chuỗi có đúng n bit

`BIT(n)` yêu cầu một giá trị có độ dài đúng `n` bit khi được gán theo quy tắc kiểu.

Ví dụ:

~~~sql
CREATE TABLE typed_lab.bit_demo (
    demo_id INTEGER PRIMARY KEY,
    status_mask BIT(8) NOT NULL
);

INSERT INTO typed_lab.bit_demo
    (demo_id, status_mask)
VALUES
    (1, B'00001111'),
    (2, B'10101010');
~~~

Một giá trị `BIT(8)` có 8 vị trí; ví dụ 00001111 và 10101010 đều hợp lệ.

### 13.1. Dữ liệu ngắn hoặc dài hơn độ dài khai báo

Gán một bit string không đúng độ dài cột có thể bị từ chối:

~~~sql
-- Ví dụ có thể lỗi do không đúng chiều dài BIT(8):
-- INSERT INTO typed_lab.bit_demo VALUES (3, B'101');

-- Ví dụ có thể lỗi do có hơn 8 bit:
-- INSERT INTO typed_lab.bit_demo VALUES (4, B'101010101');
~~~

Khi **cast tường minh** sang `bit(n)`, PostgreSQL có quy tắc riêng về **đệm bit 0 ở bên phải hoặc cắt phần dư phía phải**:

~~~sql
SELECT
    B'101'::BIT(8) AS explicitly_padded,
    B'110011001'::BIT(8) AS explicitly_truncated;
~~~

Kết quả tương ứng theo quy tắc cast là chuỗi 8 bit. Điều này khác với giả định “ép kiểu sẽ luôn báo lỗi nếu sai chiều dài”.

**Vì cast có thể làm mất thông tin**, không nên ép kiểu tường minh mọi đầu vào không đúng chiều dài chỉ để tránh lỗi. Với dữ liệu giao thức, hãy kiểm tra chiều dài và quy tắc padding trước.

### 13.2. Có thể không chỉ định n không?

Trong PostgreSQL, `BIT` không chỉ rõ độ dài có mặc định chiều dài theo quy tắc kiểu, thường là **1 bit**. Vì vậy nếu cần cờ 8 bit, nên viết `BIT(8)` rõ ràng.

Không suy rằng `BIT` không chỉ định độ dài sẽ có khả năng lưu bit string dài tùy ý. Trường hợp đó cần `BIT VARYING`.

## 14. bit varying(n) và varbit(n): độ dài có thể thay đổi

`BIT VARYING(n)`, thường viết `VARBIT(n)`, cho phép chiều dài từ 0 đến tối đa `n` bit theo giới hạn tương ứng.

Ví dụ:

~~~sql
CREATE TABLE typed_lab.bit_payload (
    payload_id INTEGER PRIMARY KEY,
    bit_payload BIT VARYING(16) NOT NULL
);

INSERT INTO typed_lab.bit_payload
    (payload_id, bit_payload)
VALUES
    (1, B'1'),
    (2, B'101010'),
    (3, B'0000000011111111');
~~~

Các hàng trên có độ dài khác nhau, đều không vượt 16 bit.

Nếu cần chiều dài thay đổi mà không đặt giới hạn cụ thể, PostgreSQL hỗ trợ dạng `BIT VARYING` không chỉ rõ `n` theo giới hạn chung của hệ thống.

### 14.1. Khi nào nên dùng BIT VARYING?

- Độ dài dữ liệu là một phần thông tin quan trọng.
- Payload ngắn không nhất thiết phải padding thành fixed width.
- Nhiều giá trị có số bit khác nhau trong cùng cột.
- Quy tắc xử lý đã định nghĩa rõ độ dài được phép.

Nếu tất cả bản ghi đều phải chứa một bitmap đúng 8 bit, `BIT(8)` giúp schema diễn đạt ràng buộc rõ hơn.

### 14.2. BIT VARYING không tự thay thế BYTEA

`BYTEA` lưu chuỗi byte nhị phân; `BIT VARYING` lưu một chuỗi bit có chiều dài có thể không chia hết cho 8.

Nếu xử lý file hoặc payload nhị phân lớn theo byte, `BYTEA` có thể phù hợp hơn. Nếu cần chính xác **5 hoặc 13 bit**, bit string thể hiện độ dài ở mức bit tự nhiên hơn.

Đừng chọn `VARBIT` chỉ vì dữ liệu “nhị phân”. Phải xét thao tác cần thực hiện và hệ sinh thái driver/ứng dụng.

## 15. Toán tử bitwise của PostgreSQL

Các toán tử phổ biến:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `&` | AND theo bit | `B'1010' & B'1100'` |
| `\|` | OR theo bit | `B'1010' \| B'1100'` |
| `#` | XOR theo bit | `B'1010' # B'1100'` |
| `~` | NOT, đảo từng bit | `~ B'1010'` |
| `<<` | Dịch trái, giữ chiều dài bit string | `B'1010' << 1` |
| `>>` | Dịch phải, giữ chiều dài bit string | `B'1010' >> 2` |
| `\|\|` | Nối hai chuỗi bit | `B'10' \|\| B'01'` |

Kết quả:

~~~sql
SELECT
    B'1010' & B'1100' AS and_bits,       -- 1000
    B'1010' | B'1100' AS or_bits,        -- 1110
    B'1010' # B'1100' AS xor_bits,       -- 0110
    ~ B'1010' AS not_bits,              -- 0101
    B'1010' << 1 AS shifted_left,        -- 0100
    B'1010' >> 2 AS shifted_right,       -- 0010
    B'10' || B'01' AS concatenated_bits; -- 1001
~~~

**Độ dài quan trọng:** với các toán tử bitwise nhị phân như AND/OR/XOR, hai toán hạng bit string phải có chiều dài phù hợp. Không mặc định PostgreSQL tự padding cho hai chuỗi có độ dài khác nhau.

### 15.1. Toán tử << ở nhóm mạng và nhóm bit khác nhau

Trong phần mạng:

~~~sql
SELECT INET '192.168.10.15' << CIDR '192.168.10.0/24';
~~~

`<<` mang nghĩa **nằm trong mạng một cách nghiêm ngặt**.

Trong phần bit:

~~~sql
SELECT B'1010' << 1;
~~~

`<<` mang nghĩa **dịch chuỗi bit sang trái**.

PostgreSQL chọn semantics dựa vào **kiểu của toán hạng**. Đây là ví dụ vì sao kiểu dữ liệu là một phần của ngữ nghĩa SQL, không chỉ là cách lưu byte.

## 16. Các hàm làm việc với bit string

### 16.1. bit_length() và octet_length()

~~~sql
SELECT
    bit_length(B'10101') AS number_of_bits,
    octet_length(B'10101') AS storage_bytes_for_value;
~~~

`bit_length` biểu diễn số bit có ý nghĩa của chuỗi. `octet_length` cho biết số byte theo cách hàm đo biểu diễn chuỗi tương ứng; không suy rằng kết quả đó bằng tổng chi phí lưu một tuple và index trong PostgreSQL.

### 16.2. get_bit() và set_bit()

~~~sql
SELECT
    get_bit(B'1010', 0) AS first_bit,
    get_bit(B'1010', 1) AS second_bit,
    set_bit(B'1010', 1, 1) AS new_bit_string;
~~~

Đối với bit string, vị trí `0` là bit ở **bên trái**. Vì vậy:

- `get_bit(B'1010', 0)` trả `1`.
- `get_bit(B'1010', 1)` trả `0`.
- `set_bit(B'1010', 1, 1)` tạo `B'1110'`.

Vị trí ngoài phạm vi chuỗi có thể gây lỗi; giá trị bit mới phải phù hợp 0/1. Nên lưu bảng tài liệu mô tả từng vị trí thay vì để ý nghĩa bit nằm trong đầu người viết ứng dụng.

### 16.3. bit_count()

Trong các phiên bản PostgreSQL có hỗ trợ `bit_count`, có thể đếm số bit 1:

~~~sql
SELECT bit_count(B'101101') AS one_bits;
~~~

Giá trị mẫu có bốn bit 1. Nếu môi trường sử dụng PostgreSQL cũ, cần kiểm tra sự tồn tại của hàm trước khi dùng trong SQL chung; không nên cho rằng mọi phiên bản đều có cùng danh sách hàm.

## 17. Thiết kế feature flags bằng BIT(8)

Trong `typed_lab.device`, ta có:

~~~sql
feature_flags BIT(8) NOT NULL DEFAULT B'00000000'
~~~

Giả sử quy ước:

~~~text
Vị trí bit (từ trái, bắt đầu 0):

  0 1 2 3 4 5 6 7
  | | | | | | | |
  | | | | | | | +-- thử nghiệm
  | | | | | | +---- hỗ trợ báo cáo
  | | | | | +------ hiệu chỉnh
  | | | | +-------- dự phòng
  | | | +---------- dự phòng
  | | +------------ GPS nội bộ
  | +-------------- hỗ trợ cảnh báo
  +---------------- cho phép giám sát
~~~

Đây chỉ là mapping giả định cho bài thực hành; trong ứng dụng thực, mỗi bit phải có **tài liệu ổn định và version tương thích**.

### 17.1. Kiểm tra một cờ

~~~sql
SELECT
    device_id,
    asset_name,
    get_bit(feature_flags, 0) = 1 AS monitoring_enabled,
    get_bit(feature_flags, 1) = 1 AS alerts_enabled
FROM typed_lab.device
ORDER BY device_id;
~~~

Đặc tính đọc dữ liệu: vị trí 0 là bit bên trái nên thiết bị 201 có cờ giám sát bật khi `feature_flags = B'10000100'`.

### 17.2. Bật một cờ bằng OR

~~~sql
UPDATE typed_lab.device
SET feature_flags = feature_flags | B'01000000'
WHERE device_id = 201
RETURNING device_id, feature_flags;
~~~

Mask `B'01000000'` bật bit thứ 1 từ trái. OR bảo toàn các bit đã bật khác.

### 17.3. Tắt một cờ bằng AND NOT

~~~sql
UPDATE typed_lab.device
SET feature_flags = feature_flags & ~ B'01000000'
WHERE device_id = 201
RETURNING device_id, feature_flags;
~~~

Bit thứ 1 được đặt về 0; các bit khác được giữ theo mask. Độ dài hai toán hạng đều 8 bit.

### 17.4. Vì sao cập nhật trực tiếp trong SQL tốt hơn đọc-sửa-ghi tùy tiện?

Một ứng dụng có thể:

1. `SELECT feature_flags`.
2. Tính bitmap mới trong Java.
3. `UPDATE` toàn bộ bitmap.

Nếu hai transaction cùng thao tác dựa vào giá trị cũ, một transaction có thể ghi đè thay đổi của transaction kia.

Với các phép bật/tắt một bit, viết trực tiếp:

~~~sql
UPDATE typed_lab.device
SET feature_flags = set_bit(feature_flags, 0, 1)
WHERE device_id = 201;
~~~

giúp cập nhật dựa trên giá trị của hàng trong statement, phối hợp với row locking của PostgreSQL. Tuy nhiên vẫn phải thiết kế transaction và concurrency nếu nhiều cờ có ràng buộc liên quan hoặc nghiệp vụ yêu cầu kiểm tra trước khi cập nhật.

## 18. Có nên lưu trạng thái nghiệp vụ bằng bitmask?

Có ba lựa chọn phổ biến:

**Nhiều cột BOOLEAN:**

~~~sql
CREATE TABLE feature_boolean_demo (
    device_id BIGINT PRIMARY KEY,
    monitoring_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    alerts_enabled BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

**Một cột BIT(8):**

~~~sql
CREATE TABLE feature_bit_demo (
    device_id BIGINT PRIMARY KEY,
    feature_flags BIT(8) NOT NULL DEFAULT B'00000000'
);
~~~

**Bảng quan hệ tính năng:**

~~~sql
CREATE TABLE device_feature_demo (
    device_id BIGINT NOT NULL,
    feature_code TEXT NOT NULL,
    PRIMARY KEY (device_id, feature_code)
);
~~~

| Tiêu chí | BOOLEAN columns | BIT(n) | Bảng quan hệ |
|---|---|---|---|
| Dễ đọc SQL | Cao | Cần biết bit position | Cao khi JOIN |
| Thêm tính năng mới | Có thể cần ALTER TABLE | Dễ nếu còn bit trống, khó nếu hết | Thường thêm hàng |
| Ràng buộc mỗi tính năng | Dễ đặt constraint | Phải dùng biểu thức/logic | Linh hoạt với metadata |
| Truy vấn theo tên tính năng | Trực tiếp | Phải mask/get_bit | Theo feature_code |
| Tương thích protocol bitmap | Cần chuyển đổi | Tự nhiên | Cần encode |
| Số lượng tính năng thay đổi | Không thuận tiện nếu rất nhiều | Bị giới hạn kích thước/mapping | Phù hợp hơn nếu nhiều và động |

**Khuyến nghị thiết kế:** dùng `BIT(n)` khi ý nghĩa bit **cố định, được công bố rõ hoặc liên quan định dạng/protocol**. Với trạng thái nghiệp vụ thường xuyên thêm/bớt và cần truy vấn dễ đọc, BOOLEAN hoặc mô hình quan hệ thường dễ bảo trì hơn.

## 19. Các lỗi thường gặp của kiểu bit

### 19.1. Nhầm độ dài với giá trị số

`B'0001'` và `B'1'` có độ dài khác nhau. Đừng tự coi chúng bằng nhau chỉ vì nếu chuyển sang số nguyên đều có thể biểu diễn giá trị 1.

### 19.2. Tính mask với thứ tự bit không thống nhất

Một số giao thức quy ước bit 0 là bit phải nhất, trong khi `get_bit` trên bit string PostgreSQL dùng thứ tự từ trái. Nếu ứng dụng Java dùng phép dịch trên số nguyên, cần xác định **bit numbering** khi chuyển giữa hai biểu diễn.

### 19.3. Trộn phép & với kiểu boolean

~~~sql
-- Ví dụ truy vấn đúng trên BIT(8):
SELECT *
FROM typed_lab.device
WHERE (feature_flags & B'10000000') = B'10000000';
~~~

`&` trả một bit string, không phải BOOLEAN. Phép so sánh với mask mới tạo điều kiện `WHERE` boolean.

### 19.4. Nhầm BIT(n) với giới hạn giá trị không dấu

`BIT(8)` là chuỗi 8 bit, không tự là số nguyên 0–255 trong mọi biểu thức. Khi cần số học và bitwise integer, kiểu số nguyên có thể phù hợp hơn; khi cần chuỗi vị trí bit cố định, dùng BIT.

## 20. Kiểu hình học tích hợp: mục đích và phạm vi

PostgreSQL cung cấp các kiểu hình học **hai chiều trên mặt phẳng**:

~~~text
point   : một điểm (x, y)
line    : đường thẳng kéo dài vô hạn
lseg    : đoạn thẳng hữu hạn giữa hai điểm
box     : hình chữ nhật theo hai góc
path    : dãy điểm nối thành đường mở hoặc kín
polygon : vùng đa giác
circle  : vùng/đường tròn theo tâm và bán kính
~~~

Các kiểu này dùng những biểu diễn và toán tử hình học có sẵn của PostgreSQL.

**Giới hạn cần nhớ:**

- Không có hệ tọa độ địa lý/SRID được lưu kèm một cách tự động.
- Phép tính khoảng cách cơ bản là **Euclid trong hệ tọa độ phẳng**.
- Đơn vị độ dài/diện tích tùy ứng dụng quy định.
- Không tự xử lý biến dạng bề mặt Trái Đất.
- Không thay thế PostGIS cho phần lớn nhu cầu GIS chuyên nghiệp.
- Cần xem khả năng index/operator class của từng kiểu, không giả định tất cả giống nhau.

Một kho chứa hàng có bản đồ mặt bằng tính bằng mét có thể dùng `point`. Một hệ thống tính quãng đường thực giữa hai thành phố theo kinh độ/vĩ độ thì **không nên** dùng trực tiếp khoảng cách Euclid giữa hai cặp số độ.

## 21. point: một tọa độ phẳng (x, y)

`point` biểu diễn một điểm hai chiều.

~~~sql
SELECT
    POINT '(3,4)' AS p1,
    point(3, 4) AS p2;
~~~

Có thể dùng literal có kiểu hoặc hàm xây dựng từ hai số.

Ví dụ bảng cảm biến:

~~~sql
CREATE TABLE typed_lab.sensor (
    sensor_id INTEGER PRIMARY KEY,
    sensor_name TEXT NOT NULL,
    position POINT NOT NULL,
    coverage CIRCLE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO typed_lab.sensor
    (sensor_id, sensor_name, position, coverage)
VALUES
    (
        301, 'Sensor near gate',
        point(2, 3),
        circle(point(2, 3), 5)
    ),
    (
        302, 'Sensor in warehouse',
        point(8, 6),
        circle(point(8, 6), 4)
    ),
    (
        303, 'Sensor in corridor',
        point(12, 2),
        circle(point(12, 2), 3)
    );
~~~

Trong ví dụ, tọa độ được hiểu là đơn vị mặt bằng tùy ý, chẳng hạn mét trên bản vẽ đã xác định hệ trục. Không sử dụng dữ liệu này làm vị trí GPS thực.

### 21.1. Tính khoảng cách giữa hai điểm

PostgreSQL hỗ trợ toán tử khoảng cách `<->` cho `point`:

~~~sql
SELECT
    point(0, 0) <-> point(3, 4)
        AS planar_distance;
~~~

Theo hình học phẳng:

\[
d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}
\]

Với `(0,0)` và `(3,4)`, kết quả là **5** đơn vị tọa độ.

Ví dụ tìm sensor gần vị trí quan sát:

~~~sql
SELECT
    sensor_id,
    sensor_name,
    position,
    position <-> point(5, 5) AS distance_units
FROM typed_lab.sensor
WHERE active = TRUE
ORDER BY
    position <-> point(5, 5),
    sensor_id
LIMIT 3;
~~~

Kết quả khoảng cách là khoảng cách **trên mặt phẳng của ứng dụng**. Nếu tọa độ là số độ longitude/latitude, số này **không phải khoảng cách mét**.

### 21.2. Phép cộng/trừ điểm không tự mô hình hóa đường đi

Một `point` chỉ là tọa độ. Nó không biết hành lang bị chặn, chướng ngại vật hoặc tuyến đường thực tế. Điểm có thể gần theo đường thẳng nhưng xa về mặt di chuyển; cần mô hình mạng đường đi/thuật toán thích hợp nếu ứng dụng yêu cầu điều hướng.

## 22. line và lseg: đường thẳng vô hạn so với đoạn hữu hạn

**`line`** biểu diễn một đường thẳng vô hạn trong mặt phẳng.

**`lseg`** biểu diễn đoạn thẳng giữa hai đầu mút.

Ví dụ:

~~~sql
SELECT
    LINE '{1,-1,0}' AS diagonal_line,
    LSEG '[(0,0),(3,4)]' AS finite_segment;
~~~

Với đường thẳng, dạng hệ số có thể hiểu theo phương trình:

\[
Ax+By+C=0
\]

Ví dụ `{1,-1,0}` là đường `x-y=0`.

Với đoạn thẳng `[(0,0),(3,4)]`, hai đầu mút là (0,0) và (3,4); độ dài đoạn thẳng là 5 đơn vị.

~~~sql
SELECT
    length(LSEG '[(0,0),(3,4)]')
        AS segment_length;
~~~

### 22.1. Khi nào dùng line, khi nào dùng lseg?

- `line`: mô hình quan hệ hướng hoặc một đường thẳng kéo dài vô hạn.
- `lseg`: đoạn từ A đến B có giới hạn thực tế.
- `path`: nhiều đoạn liên tục nối qua các điểm.
- `polygon`: vùng khép kín có nội thất theo semantics của kiểu.

Một đường đi qua 10 điểm không nên bị ép thành một `lseg` duy nhất vì như vậy mất các điểm trung gian.

## 23. box: hình chữ nhật song song hai trục

`box` là hình chữ nhật được xác định bởi hai góc đối diện, có cạnh song song trục tọa độ.

~~~sql
SELECT
    box(point(0, 0), point(10, 10))
        AS room_box;
~~~

Ví dụ tính diện tích:

~~~sql
SELECT
    area(
        box(point(0, 0), point(10, 10))
    ) AS box_area;
~~~

Kết quả là **100 đơn vị diện tích**.

### 23.1. Kiểm tra một điểm trong box

~~~sql
SELECT
    box(point(0, 0), point(10, 10))
        @> point(3, 4) AS contains_point;
~~~

Toán tử `@>` có thể biểu diễn quan hệ **chứa** với các kiểu hình học hỗ trợ tổ hợp toán hạng tương ứng.

### 23.2. Kiểm tra hai box giao nhau

~~~sql
SELECT
    box(point(0, 0), point(10, 10))
        && box(point(8, 8), point(15, 15))
        AS boxes_overlap;
~~~

Hai box có vùng giao nên kết quả là TRUE.

Không tự gán ý nghĩa “giao nhau” của hai hình bất kỳ cho mọi tổ hợp kiểu: các toán tử hình học tích hợp có **signature được hỗ trợ** riêng, cần kiểm tra tài liệu và phiên bản PostgreSQL thực tế.

### 23.3. Box phù hợp cho bài toán nào?

- Kiểm tra vùng bao đơn giản.
- Lọc sơ bộ những vị trí hoặc đối tượng nằm trong một hình chữ nhật.
- Lưu hộp bao (bounding box) của vật thể trong không gian 2D.
- Giảm số phép kiểm tra phức tạp hơn khi ứng dụng có nhiều đối tượng.

Box của PostgreSQL không tự mô hình hóa hình chữ nhật bị xoay góc so với trục tọa độ; nếu đối tượng bị xoay, hộp bao trục song song có thể lớn hơn vùng thật.

## 24. path: một đường qua nhiều điểm

`path` là chuỗi các điểm nối tiếp nhau. PostgreSQL phân biệt **đường mở** và **đường kín**.

Ví dụ:

~~~sql
SELECT
    PATH '[(0,0),(2,2),(4,0)]'
        AS open_path,

    PATH '((0,0),(2,2),(4,0))'
        AS closed_path;
~~~

Trong định dạng literal thông thường:

- Dấu ngoặc vuông `[ ... ]` biểu diễn path mở.
- Dấu ngoặc tròn `( ... )` ở cấu trúc ngoài biểu diễn path kín.

Có thể hỏi đường mở hay kín:

~~~sql
SELECT
    isopen(PATH '[(0,0),(2,2),(4,0)]')
        AS open_flag,

    isclosed(PATH '((0,0),(2,2),(4,0))')
        AS closed_flag;
~~~

Một path **khép kín** không tự đồng nghĩa với polygon trong mọi phép toán và index. `path` mô tả đường nối qua các điểm; `polygon` mô hình hóa vùng đa giác.

### 24.1. Thực tế lưu path

Nếu ứng dụng lưu tuyến đường gồm nhiều điểm, cần quyết định:

- Mọi đường có cùng hệ tọa độ không?
- Có cần giữ chiều dài từng đoạn?
- Có cần truy vấn các điểm thành phần độc lập không?
- Có cần tìm kiếm đường giao nhau hoặc khoảng cách tới tuyến không?
- Có cần thay thế bằng PostGIS hoặc mô hình mạng đường đi không?

Không chọn `path` chỉ vì dữ liệu có nhiều tọa độ; một bảng riêng chứa các điểm với `sequence_no` đôi khi dễ cập nhật và truy vấn từng chặng hơn.

## 25. polygon: vùng đa giác hai chiều

`polygon` biểu diễn một đa giác phẳng bằng danh sách các đỉnh.

~~~sql
SELECT
    POLYGON '((0,0),(4,0),(4,3),(0,3))'
        AS rectangle_polygon;
~~~

Ví dụ diện tích:

~~~sql
SELECT
    area(
        POLYGON '((0,0),(4,0),(4,3),(0,3))'
    ) AS polygon_area;
~~~

Hình chữ nhật có chiều rộng 4 và chiều cao 3 nên diện tích là **12 đơn vị vuông**.

### 25.1. Khác biệt giữa box và polygon

- `box` luôn là hình chữ nhật trục song song, xác định bằng hai góc.
- `polygon` có thể có nhiều đỉnh và biểu diễn vùng không phải hình chữ nhật.
- `box` phù hợp làm hộp bao và nhiều phép lọc đơn giản.
- `polygon` linh hoạt hơn cho những vùng có biên dạng bất kỳ trong phạm vi semantics mà kiểu hỗ trợ.

Với các vùng địa lý thật, polygon trên mặt phẳng không đủ để biết hệ tọa độ, đơn vị, phép chiếu và độ cong Trái Đất. Cần công cụ GIS phù hợp khi bài toán đòi hỏi.

### 25.2. Chất lượng dữ liệu đa giác

Trước khi dùng polygon cho quyết định nghiệp vụ quan trọng, ứng dụng cần xác định:

- Thứ tự đỉnh có đúng không?
- Các cạnh có tự giao nhau không?
- Điểm biên có được tính là nằm trong vùng không?
- Các giá trị tọa độ có cùng đơn vị không?
- Có yêu cầu lỗ (holes), nhiều vùng rời nhau hoặc topology phức tạp không?

Những nhu cầu phức tạp như polygon có nhiều lỗ, kiểm tra topology chuẩn hóa hoặc thao tác địa lý chuyên sâu thường cần PostGIS. Không coi việc PostgreSQL parse được một giá trị `polygon` là bằng chứng vùng đáp ứng mọi quy tắc hình học của ứng dụng.

## 26. circle: tâm và bán kính

`circle` biểu diễn một đường tròn/vùng tròn theo tâm và bán kính, trong hệ tọa độ phẳng.

~~~sql
SELECT
    CIRCLE '<(0,0),5>' AS circle_literal,
    circle(point(0, 0), 5) AS circle_constructed;
~~~

Một vòng tròn có tâm (0,0) và bán kính 5 được biểu diễn dễ dàng hơn bằng `circle` so với tự dựng nhiều điểm trên polygon.

Ví dụ diện tích hình tròn:

~~~sql
SELECT
    area(circle(point(0, 0), 5))
        AS circle_area;
~~~

Về toán học:

\[
A=\pi r^2
\]

với `r=5`, diện tích khoảng `78.54` đơn vị vuông. Đây là kết quả xấp xỉ do tính toán số thực, không phải kết quả kế toán tiền tệ.

### 26.1. Kiểm tra điểm nằm trong vùng tròn

~~~sql
SELECT
    circle(point(0, 0), 6) @> point(3, 4)
        AS contains_point;
~~~

Khoảng cách từ tâm tới điểm là 5, nhỏ hơn bán kính 6 nên kết quả là TRUE.

### 26.2. Tìm sensor có vùng phủ một vị trí

~~~sql
SELECT
    sensor_id,
    sensor_name,
    coverage
FROM typed_lab.sensor
WHERE active = TRUE
  AND coverage @> point(5, 5)
ORDER BY sensor_id;
~~~

Ở đây `coverage` là vòng phủ phẳng giả định. Việc một cảm biến thực tế có phủ được vị trí nào còn phụ thuộc tường, nhiễu, hướng lắp đặt và đơn vị đo; hình tròn là **mô hình đơn giản**, không phải một mô phỏng vật lý đầy đủ.

## 27. Một số toán tử và hàm hình học nên biết

Những toán tử/hàm thường gặp:

| Phép toán | Ý nghĩa | Ví dụ |
|---|---|---|
| `<->` | Khoảng cách giữa các đối tượng trong tổ hợp hỗ trợ | `point(0,0) <-> point(3,4)` |
| `@>` | Bên trái chứa bên phải, với kiểu hỗ trợ | `box(...) @> point(...)` |
| `<@` | Bên trái nằm trong bên phải, với kiểu hỗ trợ | `point(...) <@ box(...)` |
| `&&` | Hai hình giao/overlap trong tổ hợp hỗ trợ | `box(...) && box(...)` |
| `area()` | Diện tích cho kiểu hình phù hợp | `area(box(...))` |
| `length()` | Độ dài cho kiểu đường phù hợp | `length(lseg(...))` |
| `center()` | Tâm của hình phù hợp | `center(box(...))` |
| `npoints()` | Số điểm trong path/polygon theo hàm hỗ trợ | `npoints(path_value)` |

**Không có nghĩa mọi toán tử có trong bảng áp dụng cho tất cả `point`, `circle`, `polygon` và `line`.** PostgreSQL có ma trận toán tử theo cặp kiểu. Khi chuyển từ một kiểu sang kiểu khác, phải thử cú pháp/hàm chính xác.

### 27.1. Kiểm tra bằng pg_type và pg_operator khi cần

Có thể kiểm tra kiểu và operator có trên instance:

~~~sql
SELECT
    typname,
    typtype
FROM pg_catalog.pg_type
WHERE typname IN (
    'inet', 'cidr', 'macaddr', 'macaddr8',
    'bit', 'varbit',
    'point', 'line', 'lseg', 'box',
    'path', 'polygon', 'circle'
)
ORDER BY typname;
~~~

Thông tin catalog giúp nhận biết kiểu hiện có. Với những phép toán chuyên biệt, công cụ `psql` cũng hỗ trợ tra cứu danh sách hàm/toán tử và mô tả loại đối số theo cơ chế client. Không nên tự tạo phép toán bằng cách ép chuỗi nếu PostgreSQL đã hỗ trợ toán tử thích hợp.

## 28. Index hình học: GiST và truy vấn khoảng cách

Các truy vấn hình học khác với lookup equality thông thường:

- Tìm điểm gần vị trí x.
- Tìm box giao nhau.
- Tìm vùng chứa một điểm.
- Tìm vài đối tượng gần nhất.

PostgreSQL có các operator class cho những kiểu hình học nhất định trên **GiST**, và trong một số trường hợp **SP-GiST**, tùy kiểu/toán tử/phiên bản.

Ví dụ GiST index cho cột `point`:

~~~sql
CREATE INDEX idx_sensor_position_gist
ON typed_lab.sensor
USING gist (position);
~~~

Một truy vấn gần nhất:

~~~sql
SELECT
    sensor_id,
    sensor_name,
    position
FROM typed_lab.sensor
ORDER BY position <-> point(5, 5)
LIMIT 2;
~~~

Với operator class hỗ trợ tìm kiếm nearest-neighbor, PostgreSQL có thể dùng GiST index cho thứ tự khoảng cách trong những trường hợp phù hợp.

Kiểm tra:

~~~sql
EXPLAIN
SELECT sensor_id, position
FROM typed_lab.sensor
ORDER BY position <-> point(5, 5)
LIMIT 2;
~~~

Vì bảng demo có ba hàng, PostgreSQL có thể chọn scan/sort thay vì index. Điều đó hoàn toàn bình thường: planner có quyền chọn chiến lược ít chi phí hơn theo thống kê.

### 28.1. Không tạo index “một kiểu dùng cho mọi truy vấn”

GiST có thể hỗ trợ những toán tử hình học nhất định, nhưng:

- Không phải mọi toán tử đều dùng chung một operator class.
- Index có chi phí khi INSERT/UPDATE/DELETE.
- Độ phân bố không gian ảnh hưởng hiệu quả.
- Kiểu point, box và polygon có khả năng index khác nhau.
- Một bài toán GIS thực tế có thể cần `geometry`/`geography` của PostGIS với index/tính năng khác.

Nên bắt đầu từ truy vấn thực tế và `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện, thay vì chỉ nhìn vào việc index được tạo thành công.

## 29. Kiểu hình học PostgreSQL và PostGIS khác nhau thế nào?

Đây là ranh giới quan trọng.

**Kiểu hình học tích hợp của PostgreSQL:**

- Có sẵn trong hệ quản trị.
- Hỗ trợ những hình học phẳng cơ bản.
- Phù hợp với dữ liệu tọa độ mặt phẳng, bản vẽ/đồ họa kỹ thuật đơn giản.
- Không lưu hệ quy chiếu địa lý/SRID như mô hình GIS chuyên biệt.
- Tập phép toán không nhằm thay thế toàn bộ GIS.

**PostGIS (extension):**

- Bổ sung các kiểu và hàm không gian chuyên sâu, tiêu biểu là `geometry` và `geography`.
- Có khả năng mô hình hóa hệ tọa độ/SRID và thực hiện nhiều phân tích không gian hơn.
- Hỗ trợ nhiều hình phức tạp và phép tính chuyên biệt theo tính năng/phiên bản.
- Phù hợp hơn khi cần GIS, truy vấn không gian lớn, hệ tọa độ chuẩn, diện tích/khoảng cách địa lý và chuyển hệ quy chiếu.

Ví dụ **không nên** viết:

~~~sql
-- Đây chỉ là khoảng cách Euclid của hai cặp số,
-- không phải km giữa hai vị trí địa lý.
SELECT point(106.7, 10.8) <-> point(105.8, 21.0);
~~~

Giá trị hai tọa độ trong ví dụ giống longitude/latitude, nhưng kết quả được đo bằng **độ tọa độ phẳng**, không phải mét hay km.

Khi yêu cầu tính khoảng cách thực trên Trái Đất, cần xác định SRID, đơn vị, thuật toán và chọn công cụ GIS phù hợp thay vì nhân kết quả với một hằng số quy đổi cố định.

## 30. Kiểu số và độ chính xác trong hình học

Các kiểu hình học tích hợp làm việc với tọa độ số thực, có thể gặp sai số biểu diễn và tính toán.

Ví dụ một phép tính diện tích:

~~~sql
SELECT
    area(circle(point(0, 0), 5)) AS area_value;
~~~

Kết quả là số thực xấp xỉ giá trị toán học. Không dùng trực tiếp kết quả kiểu này để hạch toán tiền với yêu cầu thập phân chính xác.

Khi ứng dụng kiểm tra hai điểm “gần bằng nhau”, nên định nghĩa ngưỡng sai số theo đơn vị:

~~~sql
SELECT
    (point(1.0, 1.0) <-> point(1.000001, 1.0)) < 0.001
        AS near_enough;
~~~

Ngưỡng `0.001` chỉ có ý nghĩa khi đã thống nhất đơn vị tọa độ. Không nên dùng một epsilon cố định cho mọi hệ thống hoặc mọi tỉ lệ.

## 31. Chọn kiểu theo ngữ nghĩa ứng dụng, không theo hình thức chuỗi

Một số trường hợp dễ nhầm:

| Dữ liệu đầu vào | Kiểu thường cân nhắc | Vì sao |
|---|---|---|
| `192.168.1.10` là IP của request | `inet` | Là một host IPv4 |
| `192.168.1.0/24` là subnet ACL | `cidr` | Là một dải mạng |
| `2001:db8::1` là IPv6 | `inet` | Cùng cột có thể lưu IPv4/IPv6 |
| `08:00:2b:01:02:03` là MAC | `macaddr` | Địa chỉ phần cứng 48 bit |
| 8 bit cờ protocol | `bit(8)` | Cố định chiều dài và bit position |
| Bitmap có độ dài thay đổi tới 128 bit | `bit varying(128)` | Không bắt buộc mọi hàng dài 128 bit |
| Địa điểm trên mặt bằng nhà xưởng | `point` | Tọa độ phẳng |
| Vùng tròn phủ cảm biến trên bản vẽ | `circle` | Tâm và bán kính |
| Vùng chữ nhật trên mặt phẳng | `box` | Hộp bao theo trục |
| Ranh giới nhiều đỉnh trên mặt phẳng | `polygon` | Vùng đa giác đơn giản |
| Vị trí GPS có SRID và tính khoảng cách mét | PostGIS `geometry`/`geography` khi phù hợp | Bài toán địa lý, không phải point phẳng thuần |
| Dữ liệu file nhị phân theo byte | `bytea` | Cấu trúc byte thay vì bit string |

Không dùng `cidr` cho một URL, không dùng `macaddr` cho địa chỉ IP, không dùng `bit(8)` để chứa chuỗi “đúng/sai” dễ đọc khi các cờ thay đổi thường xuyên và không dùng `point` thay cho hệ tọa độ địa lý nếu bài toán cần GIS.

## 32. Truy vấn kết hợp dữ liệu mạng, bit và hình học

Giả sử muốn biết thiết bị nào có bật giám sát và nằm gần vị trí xác định:

~~~sql
SELECT
    device_id,
    asset_name,
    hardware_address,
    feature_flags,
    location_2d,
    location_2d <-> point(0, 0) AS planar_distance
FROM typed_lab.device
WHERE get_bit(feature_flags, 0) = 1
  AND location_2d IS NOT NULL
ORDER BY
    location_2d <-> point(0, 0),
    device_id;
~~~

SQL trên minh họa ba loại dữ liệu trong cùng một bảng thiết bị:

- `hardware_address` là MAC, không phải thông tin địa lý.
- `feature_flags` là bitmask được giải thích theo mapping ứng dụng.
- `location_2d` là vị trí phẳng để tính khoảng cách.

Nếu thiết bị được định danh bằng IP thay vì MAC, cần một cột `inet` riêng và hiểu quan hệ thiết bị–IP có thể là **một-nhiều hoặc thay đổi theo thời gian** (ví dụ DHCP, nhiều interface).

### 32.1. Thiết kế quan hệ giữa IP, MAC và thiết bị

Một thiết bị có thể:

- Có nhiều địa chỉ IPv4/IPv6.
- Thay địa chỉ IP theo thời điểm.
- Có nhiều card mạng/MAC.
- Có địa chỉ MAC randomization.
- Kết nối qua proxy/NAT khiến log server thấy IP khác thiết bị thật.

Vì vậy không nên gộp mọi thứ thành một cột `device_address TEXT UNIQUE`.

Một mô hình chặt hơn có thể có bảng `device`, `device_interface`, `assigned_ip` và `assignment_history`, với constraint/time range phù hợp. Sử dụng `inet` cho IP và `macaddr`/`macaddr8` cho định danh giao diện khi ý nghĩa thực sự tương ứng.

## 33. Chuyển đổi từ TEXT sang kiểu chuyên biệt

Giả sử hệ thống cũ có:

~~~sql
CREATE TABLE typed_lab.import_ip_text (
    id INTEGER PRIMARY KEY,
    ip_text TEXT NOT NULL
);

INSERT INTO typed_lab.import_ip_text
    (id, ip_text)
VALUES
    (1, '192.168.10.12'),
    (2, '2001:db8::8'),
    (3, 'not-a-real-ip');
~~~

Không nên chạy thẳng:

~~~sql
-- Dự kiến lỗi vì có giá trị không hợp lệ:
-- ALTER TABLE typed_lab.import_ip_text
-- ALTER COLUMN ip_text TYPE INET
-- USING ip_text::inet;
~~~

Giá trị `not-a-real-ip` không chuyển được sang `inet`. Muốn migration:

1. Xác định các quy tắc đầu vào được phép.
2. Khảo sát dữ liệu và tìm giá trị không hợp lệ.
3. Làm sạch dữ liệu hoặc tách bản ghi lỗi theo nghiệp vụ.
4. Thử migration trên staging.
5. Cập nhật code/driver/ORM nếu có thay đổi kiểu cột.
6. Chạy chuyển đổi với kế hoạch lock/downtime hoặc migration theo đợt.
7. Kiểm tra dữ liệu và index sau khi chuyển.

### 33.1. Tránh ép kiểu toàn bảng không kiểm soát

Một câu `ALTER COLUMN ... TYPE INET USING ...` trên bảng lớn có thể tác động nhiều hàng, yêu cầu khóa mạnh và thời gian chuyển đổi dài. Với production, cần đánh giá kế hoạch migration theo từng giai đoạn thay vì chỉ dựa trên một câu lệnh chạy được ở bảng demo.

### 33.2. Dữ liệu network có thể canonicalize khi ghi

Cách PostgreSQL hiển thị lại IPv6 hoặc MAC có thể chuẩn hóa biểu diễn. Vì vậy nếu ứng dụng dựa vào **chuỗi đầu vào ban đầu nguyên văn** để audit hoặc ký số, cần lưu một trường raw string riêng có kiểm soát, bên cạnh trường typed đã chuẩn hóa.

Trường typed là nguồn phục vụ so sánh mạng; trường raw (nếu thật sự cần) phục vụ truy vết, không dùng để xác định subnet.

## 34. JDBC và các kiểu không phổ thông

Trong Java/JDBC, các kiểu PostgreSQL chuyên biệt có thể không ánh xạ trực tiếp vào một kiểu Java chuẩn đơn giản như `String` hoặc `Integer`.

Những điểm cần chú ý:

- PostgreSQL JDBC driver có cơ chế xử lý kiểu riêng của server.
- Framework ORM có thể cần mapping tùy chỉnh hoặc converter.
- `inet`/`cidr` phải được parse/serialize theo dạng hợp lệ.
- `bit`/`varbit` có thể cần kiểm soát độ dài và cách ánh xạ Java.
- `point`/`circle` có thể cần thư viện hoặc đối tượng chuyên biệt của driver.
- Nếu gửi `?` parameter không rõ kiểu, PostgreSQL có thể cần cast tường minh để biết kiểu mong đợi.

Ví dụ SQL dùng tham số với cast kiểu:

~~~sql
SELECT
    event_id,
    remote_ip
FROM typed_lab.access_event
WHERE remote_ip <<= CAST(? AS CIDR);
~~~

Trong ứng dụng JDBC, dấu `?` là parameter marker; cách bind có thể là chuỗi biểu diễn CIDR phù hợp với driver, sau đó PostgreSQL cast sang kiểu `cidr`. Không ghép trực tiếp input mạng vào SQL bằng nối chuỗi.

Một ví dụ Java JDBC đơn giản kiểm tra kiểu IP qua text parameter:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class NetworkQueryDemo {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("POSTGRES_JDBC_URL");
        String user = System.getenv("POSTGRES_USER");
        String password = System.getenv("POSTGRES_PASSWORD");

        String sql = """
            SELECT event_id, remote_ip::text
            FROM typed_lab.access_event
            WHERE remote_ip <<= CAST(? AS CIDR)
            ORDER BY event_id
            """;

        try (Connection con =
                 DriverManager.getConnection(url, user, password);
             PreparedStatement ps = con.prepareStatement(sql)) {

            ps.setString(1, "192.168.10.0/24");

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getLong(1) + " " + rs.getString(2)
                    );
                }
            }
        }
    }
}
~~~

Ví dụ sử dụng **Java text blocks** (Java 15+) và giả định PostgreSQL JDBC driver tương thích có trên classpath. Mật khẩu không được nhúng vào mã nguồn. Đây là một mẫu minh họa, không thay thế cấu hình TLS, connection pool và truy vấn an toàn của ứng dụng thật.

## 35. NULL và ràng buộc khi dùng kiểu chuyên biệt

Kiểu dữ liệu chỉ bảo đảm một giá trị **không NULL** được biểu diễn đúng theo kiểu, không tự quyết định cột có bắt buộc điền hay không.

Ví dụ:

~~~sql
CREATE TABLE typed_lab.network_policy (
    policy_id BIGINT PRIMARY KEY,
    network_block CIDR NOT NULL,
    policy_action TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_network_policy_action
        CHECK (policy_action IN ('allow', 'deny'))
);
~~~

Ở đây:

- `CIDR` kiểm tra tính hợp lệ của dải mạng.
- `NOT NULL` yêu cầu phải có giá trị.
- `CHECK` giới hạn policy action.
- `PRIMARY KEY` xác định định danh hàng.

Tương tự, với kiểu `point`:

~~~sql
-- Trường position có thể nullable nếu chưa biết vị trí.
-- Nếu bắt buộc phải có tọa độ, dùng POINT NOT NULL.
~~~

Kiểu `point` **không tự ngăn giá trị NULL** và không biết tọa độ đó có nằm trong vùng hợp lệ của bản vẽ hay không. Có thể thêm constraint/logic kiểm tra miền tọa độ theo ứng dụng.

## 36. Những sai lầm phổ biến

### Sai lầm 1 — Dùng TEXT cho mọi IP

Ứng dụng phải tự parse và kiểm tra network containment.

**Cách tốt hơn:** dùng `inet`/`cidr` khi cột thực sự chứa IP/dải mạng, kết hợp constraints phù hợp.

### Sai lầm 2 — Nhầm inet và cidr

Đặt giá trị `192.168.10.15/24` vào `cidr` như thể đó là một network chuẩn.

**Cách tốt hơn:** `inet` cho host kèm prefix; `cidr` cho network address có bit host phù hợp.

### Sai lầm 3 — Dùng << thay <<= khi cần gồm chính mạng đó

Hai subnet bằng nhau không thỏa strict containment.

**Cách tốt hơn:** chọn toán tử theo ý nghĩa nghiêm ngặt hay bao gồm bằng nhau.

### Sai lầm 4 — Coi địa chỉ IP là danh tính vĩnh viễn

NAT, VPN, proxy và DHCP làm quan hệ giữa IP và người dùng/thiết bị thay đổi.

**Cách tốt hơn:** lưu ID nghiệp vụ riêng, IP phục vụ quan sát theo thời gian.

### Sai lầm 5 — Nghĩ có thể lấy MAC của mọi client web

MAC thường không được truyền xuyên router tới server ứng dụng Internet.

**Cách tốt hơn:** chỉ dùng `macaddr`/`macaddr8` khi nguồn dữ liệu thực sự có định danh giao diện liên quan.

### Sai lầm 6 — Dùng MAC làm khóa bảo mật

MAC có thể bị spoof hoặc randomize.

**Cách tốt hơn:** dùng cơ chế xác thực/ủy quyền thích hợp, không dựa vào MAC đơn lẻ.

### Sai lầm 7 — Nhầm BIT(8) với số nguyên 8 bit

`BIT(8)` là chuỗi có chiều dài 8, không tự hành xử như kiểu integer trong mọi phép toán.

**Cách tốt hơn:** xác định dùng bitmask hay số học trước khi chọn kiểu.

### Sai lầm 8 — Không thống nhất thứ tự bit

Client coi bit 0 là bên phải trong khi `get_bit` trên bit string tính từ bên trái.

**Cách tốt hơn:** ghi rõ mapping và kiểm thử chuyển đổi giữa Java và PostgreSQL.

### Sai lầm 9 — Ép kiểu bit(n) làm mất thông tin

Explicit cast có thể pad/cắt bit thay vì báo lỗi.

**Cách tốt hơn:** kiểm tra chiều dài đầu vào trước khi cast nếu cần toàn vẹn bit.

### Sai lầm 10 — Dùng bitmask cho quá nhiều cờ nghiệp vụ động

Một bitmap không được version hóa dễ trở nên khó đọc và phá tương thích.

**Cách tốt hơn:** cân nhắc BOOLEAN hoặc bảng quan hệ theo feature code.

### Sai lầm 11 — Dùng point để tính km từ longitude/latitude

`<->` trả khoảng cách Euclid theo đơn vị tọa độ, không phải khoảng cách địa lý.

**Cách tốt hơn:** dùng PostGIS hoặc công cụ GIS phù hợp cho dữ liệu có SRID và phép đo địa lý.

### Sai lầm 12 — Coi box là polygon bất kỳ

`box` là hình chữ nhật song song trục tọa độ, không phải mọi vùng có biên tùy ý.

**Cách tốt hơn:** dùng `polygon` hoặc PostGIS khi cần vùng phức tạp.

### Sai lầm 13 — Không thống nhất đơn vị tọa độ

Một cảm biến dùng mét, cảm biến khác dùng pixel nhưng cùng lưu `point`.

**Cách tốt hơn:** quy định đơn vị/hệ trục ở schema, tài liệu và ràng buộc/mapping của ứng dụng.

### Sai lầm 14 — Coi GiST luôn được planner sử dụng

Bảng nhỏ có thể scan tuần tự rẻ hơn.

**Cách tốt hơn:** dùng `EXPLAIN` với dữ liệu/tải đại diện và chọn index theo operator class.

### Sai lầm 15 — Lưu chuỗi mạng raw nhưng so sánh bằng text

IPv6 có thể có nhiều biểu diễn văn bản tương đương.

**Cách tốt hơn:** so sánh kiểu `inet`/`cidr`; chỉ giữ raw text nếu thực sự có mục đích audit.

### Sai lầm 16 — Không kiểm tra dữ liệu trước khi đổi TEXT sang INET

Một chuỗi sai khiến migration lỗi.

**Cách tốt hơn:** rà soát, làm sạch và thử chuyển đổi trên staging.

## 37. Quy trình chọn kiểu dữ liệu cho một bảng mới

Khi gặp một trường thông tin mới, làm theo các bước:

**Bước 1 — Xác định ý nghĩa thực.** Đó là host IP, dải mạng, phần cứng 48/64 bit, bitmap hay tọa độ phẳng?

**Bước 2 — Xác định các phép toán cần thực hiện.** So sánh bằng, containment, prefix match, bitwise flag, tìm điểm gần nhất hay giao nhau giữa các hình?

**Bước 3 — Chọn kiểu rõ nghĩa.** `inet` cho IP, `cidr` cho mạng, `macaddr`/`macaddr8` cho định danh phù hợp, `bit`/`varbit` cho chuỗi bit, `point`/`box`/`circle`/`polygon` cho hình phẳng.

**Bước 4 — Đặt ràng buộc.** `NOT NULL`, `CHECK`, `UNIQUE`, foreign key và quy ước độ dài/đơn vị.

**Bước 5 — Tài liệu hóa miền giá trị.** Prefix, bit position, đơn vị đo, hệ trục và các điều kiện hợp lệ.

**Bước 6 — Kiểm tra client/ORM.** Dữ liệu có serialize/deserialize đúng không? Có cần cast tham số không?

**Bước 7 — Thử index và workload.** Xem `EXPLAIN`, operator class, độ chọn lọc và chi phí cập nhật.

**Bước 8 — Thiết kế vận hành dữ liệu.** Quyền truy cập IP/MAC, retention của log, và khả năng migration khi ứng dụng phát triển.

Điểm cốt lõi là **chọn kiểu theo phép toán và ý nghĩa dữ liệu**, không chỉ dựa trên cách giá trị nhìn giống một chuỗi ký tự.

## 38. Bài tập thực hành

### Bài 1 — inet hay cidr?

Phân loại bốn giá trị: IP người dùng `192.168.1.7`, dải `192.168.1.0/24`, host IPv6 `2001:db8::7` và ACL dải IPv6 `2001:db8::/32`.

**Gợi ý:** host dùng `inet`; network dùng `cidr`.

### Bài 2 — Host và network

Viết SQL dùng `host()` và `network()` trên `INET '10.20.30.45/24'`. Hai kết quả khác nhau thế nào?

**Gợi ý:** host vẫn là 10.20.30.45, phần network tương ứng 10.20.30.0/24.

### Bài 3 — Strict containment

Vì sao `CIDR '10.0.0.0/8' << CIDR '10.0.0.0/8'` không đúng, trong khi dùng `<<=` thì đúng?

**Gợi ý:** nghiêm ngặt khác bao gồm bằng nhau.

### Bài 4 — JOIN với hai subnet lồng nhau

IP `192.168.10.200` trùng với bao nhiêu subnet trong bảng `typed_lab.allowed_network` của ví dụ?

**Gợi ý:** khớp Office /24 và Office management /25. JOIN thường có hai dòng.

### Bài 5 — Longest prefix match

Viết SQL chọn một subnet có prefix dài nhất cho mỗi event.

**Gợi ý:** `LEFT JOIN LATERAL` và `ORDER BY masklen(network_block) DESC LIMIT 1`.

### Bài 6 — MAC không phải IP

Vì sao không nên dùng `macaddr` để lưu IP client HTTP?

**Gợi ý:** MAC thuộc tầng liên kết mạng, thường không có trong request qua Internet; IP và MAC là những loại địa chỉ khác nhau.

### Bài 7 — Xác định độ dài bit

So sánh `BIT(8)` và `BIT VARYING(8)` khi lưu `B'101'`.

**Gợi ý:** fixed-width yêu cầu đúng số bit theo quy tắc gán; varying cho phép độ dài ngắn hơn.

### Bài 8 — Kết quả AND, OR, XOR

Tính:

~~~sql
SELECT
    B'1100' & B'1010',
    B'1100' | B'1010',
    B'1100' # B'1010';
~~~

**Gợi ý:** kết quả lần lượt 1000, 1110 và 0110.

### Bài 9 — Vị trí bit

`get_bit(B'10101010', 0)` trả bao nhiêu? Vì sao?

**Gợi ý:** trả 1; bit thứ 0 ở phía trái của bit string.

### Bài 10 — Bật/tắt cờ

Viết UPDATE để bật bit vị trí 2 trong `feature_flags BIT(8)` mà không thay các bit khác.

**Gợi ý:** `set_bit(feature_flags, 2, 1)`.

### Bài 11 — Lỗi mapping cờ

Một bên Java đánh số bit từ phải và một bên PostgreSQL dùng `get_bit` từ trái. Điều gì có thể xảy ra?

**Gợi ý:** hai bên bật/đọc nhầm tính năng, tạo lỗi nghiệp vụ dù chuỗi có 8 bit hợp lệ.

### Bài 12 — Khoảng cách điểm

Tính khoảng cách từ `point(0,0)` tới `point(6,8)` bằng `<->`.

**Gợi ý:** 10 đơn vị tọa độ.

### Bài 13 — Box và polygon

Khi nào `box` đủ để biểu diễn vùng, và khi nào cần `polygon`?

**Gợi ý:** box cho hình chữ nhật song song hai trục; polygon cho nhiều đỉnh và vùng phức tạp hơn.

### Bài 14 — Path mở/kín

Nhận diện hai literal:

~~~sql
SELECT
    PATH '[(0,0),(1,1),(2,0)]',
    PATH '((0,0),(1,1),(2,0))';
~~~

**Gợi ý:** ngoặc vuông là path mở; ngoặc tròn ngoài là path khép kín.

### Bài 15 — Đường tròn

Viết SQL kiểm tra point(3,4) có nằm trong circle tâm (0,0), bán kính 6 không.

**Gợi ý:** `circle(point(0,0),6) @> point(3,4)`.

### Bài 16 — Đơn vị khoảng cách

Ứng dụng có cặp longitude/latitude. Vì sao không thể dùng trực tiếp kết quả `point(x1,y1) <-> point(x2,y2)` làm số km?

**Gợi ý:** hai tọa độ là góc độ trên Trái Đất, trong khi toán tử trả khoảng cách phẳng.

### Bài 17 — GiST index

Tạo GiST index trên `typed_lab.sensor(position)` và dùng `EXPLAIN` cho truy vấn tìm 3 sensor gần point(5,5). Tại sao bảng nhỏ có thể không dùng index?

**Gợi ý:** sequential scan và sort có thể rẻ hơn khi dữ liệu rất ít.

### Bài 18 — Migration TEXT → INET

Bảng cũ có một hàng `not-a-real-ip`. Điều gì xảy ra nếu ép cả cột thành `inet` mà không làm sạch dữ liệu?

**Gợi ý:** chuyển đổi lỗi ở hàng không hợp lệ, cần profiling và migration có kiểm soát.

### Bài 19 — Thiết kế schema

Thiết kế bảng quản lý thiết bị với ID, một địa chỉ IP hiện tại, một MAC optional và cờ 16 bit.

**Gợi ý:** `BIGINT`/`INTEGER` cho ID, `INET` cho IP, `MACADDR` cho MAC, `BIT(16)` cho cờ; sau đó xét nhu cầu lưu lịch sử IP.

### Bài 20 — Chọn kiểu cho GIS

Ứng dụng muốn tìm các điểm giao hàng cách cửa hàng không quá 5 km theo bề mặt Trái Đất, dùng kinh độ/vĩ độ. `point` tích hợp có đủ không?

**Gợi ý:** không nên dùng trực tiếp cho khoảng cách km; cân nhắc PostGIS `geography`/`geometry` và hệ quy chiếu/thuật toán phù hợp.

## 39. Tổng kết

- **`inet`** lưu địa chỉ IPv4/IPv6, có thể kèm prefix và vẫn giữ host bits; **`cidr`** dùng cho dải mạng chuẩn theo prefix.
- Các toán tử **`<<`, `<<=`, `>>`, `>>=`, `&&`** giúp kiểm tra phạm vi mạng; chúng không đồng nghĩa với toán tử shift trên bit string.
- Các hàm **`host`, `network`, `masklen`, `family`** hỗ trợ phân tích địa chỉ mà không phải tự cắt chuỗi.
- **`macaddr`** biểu diễn định danh phần cứng 48 bit và **`macaddr8`** biểu diễn định danh 64 bit; chúng không thay IP hoặc xác thực thiết bị.
- **`BIT(n)`** giữ chiều dài cố định, **`BIT VARYING(n)`/`VARBIT(n)`** cho chuỗi dài tới giới hạn; explicit cast có thể pad/cắt bit.
- Toán tử bit **AND/OR/XOR/NOT/shift** cùng `get_bit` và `set_bit` giúp thao tác bitmap, nhưng phải thống nhất vị trí bit và độ dài.
- Những kiểu hình học tích hợp gồm **`point`, `line`, `lseg`, `box`, `path`, `polygon`, `circle`**, phục vụ phép tính trên mặt phẳng hai chiều.
- Khoảng cách **`<->`** của point là Euclid theo đơn vị tọa độ; **không phải km địa lý** khi đầu vào là longitude/latitude.
- PostgreSQL có **GiST/SP-GiST và B-tree operator classes** cho những tổ hợp kiểu/toán tử nhất định; cần chọn theo workload và kiểm tra `EXPLAIN`.
- Chọn kiểu theo **ngữ nghĩa dữ liệu và phép toán**, đồng thời thiết kế ràng buộc, index, mapping driver, retention và quyền truy cập phù hợp.
- Khi bài toán cần hệ quy chiếu, chuyển hệ tọa độ, khoảng cách địa lý hoặc GIS phức tạp, hãy đánh giá **PostGIS** thay vì mặc định các kiểu hình học tích hợp là đủ.

Những kiểu chuyên biệt của PostgreSQL phát huy giá trị khi **ý nghĩa của dữ liệu được thể hiện ngay trong schema**. Một cột `inet` nói rõ “đây là địa chỉ IP”, `cidr` nói “đây là một mạng”, `bit(8)` nói “đây là chuỗi tám bit có vị trí xác định”, và `point` nói “đây là tọa độ phẳng”. Khi chọn đúng kiểu và hiểu ranh giới của nó, truy vấn dễ diễn đạt, dữ liệu được kiểm tra gần nơi lưu trữ và ứng dụng ít phải tự xây lại những phép xử lý đã có sẵn trong PostgreSQL.
