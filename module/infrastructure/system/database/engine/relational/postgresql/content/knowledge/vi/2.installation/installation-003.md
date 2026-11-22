# Khởi tạo cụm dữ liệu bằng initdb và lựa chọn mã hóa, locale trong PostgreSQL

Sau khi cài các tệp chương trình PostgreSQL, máy tính đã có những công cụ như `postgres`, `psql` và `initdb`, nhưng **chưa chắc đã có một cụm dữ liệu sẵn sàng phục vụ truy vấn**. Trước khi PostgreSQL lưu bảng, quản lý người dùng và nhận kết nối, cần có một thư mục dữ liệu được khởi tạo với cấu trúc hệ thống phù hợp.

`initdb` là công cụ thực hiện bước đó. Khi chạy, nó tạo **database cluster** (cụm dữ liệu PostgreSQL), các database nền tảng và những tệp cấu hình ban đầu. Đây cũng là thời điểm quan trọng để quyết định **mã hóa ký tự (encoding)** và **locale** mặc định, vì những lựa chọn này ảnh hưởng khả năng lưu tiếng Việt, cách sắp xếp chuỗi, xử lý chữ hoa/chữ thường và hành vi của các database được tạo sau đó.

Bài học hướng dẫn cách chuẩn bị môi trường, chạy `initdb`, chọn `UTF8` và locale phù hợp, hiểu sự khác nhau giữa `libc` và `ICU`, xác minh kết quả, cũng như tránh các lỗi khiến phải khởi tạo lại cụm hoặc di chuyển dữ liệu về sau.

## 1. Hiểu đúng “cluster” trong PostgreSQL

Trong ngữ cảnh `initdb`, **database cluster** là **tập hợp các database được quản lý bởi một PostgreSQL server instance và dùng chung một thư mục dữ liệu**. Từ “cluster” ở đây không tự động có nghĩa là một cụm nhiều máy chủ có high availability, failover hay replication.

Ví dụ:

~~~text
Máy chủ PostgreSQL (một instance)
│
├── PGDATA: /srv/pg-demo/data
│   ├── base/
│   ├── global/
│   ├── pg_wal/
│   ├── PG_VERSION
│   ├── postgresql.conf
│   ├── pg_hba.conf
│   └── pg_ident.conf
│
├── database: postgres
├── database: template0
├── database: template1
└── database: app_db       ← có thể được tạo sau
~~~

Các thành phần cần phân biệt:

| Khái niệm | Vai trò |
| --- | --- |
| **PostgreSQL binaries** | Chương trình đã cài, ví dụ `initdb`, `postgres`, `pg_ctl`, `psql` |
| **PGDATA** | Đường dẫn thư mục chứa dữ liệu và metadata của một instance |
| **Database cluster** | Tập database do cùng một instance quản lý |
| **Database** | Không gian chứa schema, table, view, function... của một ứng dụng hoặc mục đích |
| **Role** | Danh tính/quyền truy cập bên trong một cluster |
| **PostgreSQL server** | Tiến trình mở cluster, quản lý dữ liệu và nhận kết nối |

`initdb` **khởi tạo thư mục dữ liệu**, không phải lệnh khởi động server. Sau khi `initdb` thành công, cần dùng `pg_ctl` hoặc trình quản lý dịch vụ tương ứng để khởi chạy PostgreSQL.

### initdb tạo những gì?

Một lần chạy thành công thường tạo:

- Những database nền tảng: `postgres`, `template0` và `template1`.
- Các tệp cấu hình, trong đó có `postgresql.conf` và `pg_hba.conf`.
- Những cấu trúc lưu trữ như `base`, `global` và thư mục write-ahead log `pg_wal`.
- Role siêu người dùng ban đầu (*bootstrap superuser*).
- Các bảng hệ thống và thông tin cần thiết để server hoạt động.

Không nên chỉnh sửa trực tiếp các tệp dữ liệu hay những file trong `base/` và `global/` để “đổi” encoding hoặc locale. Những thay đổi thiết kế ở mức database phải thực hiện bằng các công cụ và câu lệnh PostgreSQL được hỗ trợ.

## 2. Chuẩn bị trước khi chạy initdb

### 2.1. Xác định phiên bản PostgreSQL và đường dẫn công cụ

Trên Linux, sau khi cài PostgreSQL bằng gói hệ điều hành, chương trình `initdb` có thể nằm trong một thư mục theo phiên bản, chẳng hạn:

~~~bash
/usr/lib/postgresql/16/bin/initdb --version
/usr/lib/postgresql/16/bin/initdb --help
~~~

Đường dẫn `/usr/lib/postgresql/16/bin` là **ví dụ** thường gặp trên Debian/Ubuntu với PostgreSQL 16. Bản khác hoặc PostgreSQL biên dịch từ mã nguồn có thể đặt công cụ ở vị trí khác. Không được dùng `initdb` của phiên bản 16 để khởi tạo một thư mục dữ liệu định dành cho server phiên bản lớn khác mà không xác minh tính tương thích.

Khi PostgreSQL được cài bằng trình quản lý gói, hệ điều hành có thể đã **tạo sẵn cluster**. Trước khi khởi tạo thêm, hãy xác nhận đường dẫn dữ liệu, instance và cổng đang sử dụng để tránh thao tác nhầm một cluster có dữ liệu thật.

### 2.2. Chọn đường dẫn PGDATA an toàn

Ví dụ dành riêng cho bài thực hành:

~~~text
/srv/pg-demo/
    data/          ← PGDATA mới, phải trống
    server.log     ← nơi pg_ctl ghi log thử nghiệm
~~~

Quy tắc:

1. Thư mục PGDATA chưa chứa dữ liệu của một cluster khác.
2. Chủ sở hữu và quyền truy cập phù hợp với tài khoản hệ điều hành chạy PostgreSQL.
3. Có đủ dung lượng đĩa cho dữ liệu, WAL, chỉ mục và tăng trưởng sau này.
4. Vị trí lưu trữ phù hợp với chính sách sao lưu và bảo vệ dữ liệu.
5. Không đặt PGDATA trong kho mã nguồn, thư mục đồng bộ tệp hoặc vị trí có thể bị xóa bởi tác vụ dọn dẹp tạm thời.

Trên hệ điều hành Unix/Linux, `initdb` và server **không được chạy dưới tài khoản root**. Chúng thường chạy bằng tài khoản hệ điều hành chuyên dụng như `postgres`.

### 2.3. Kiểm tra locale hệ điều hành

Với locale do thư viện `libc` cung cấp, PostgreSQL phụ thuộc vào locale mà hệ điều hành nhận biết. Trên Linux có thể xem:

~~~bash
locale
locale -a
~~~

Ví dụ một máy có thể liệt kê:

~~~text
C
C.utf8
en_US.utf8
vi_VN.utf8
~~~

Đây chỉ là **minh họa**: tên thực tế có thể là `C.UTF-8`, `C.utf8` hoặc cách viết khác. Locale `vi_VN.UTF-8` có thể **chưa được cài**. Nếu yêu cầu một locale không tồn tại hoặc không phù hợp với encoding được chọn, `initdb` có thể báo lỗi.

Trong môi trường container hoặc máy chủ tối giản, đôi khi chỉ có `C` và một biến thể UTF-8 cơ bản. Khi đó, đừng sao chép máy móc `--locale=vi_VN.UTF-8` chỉ vì ứng dụng lưu dữ liệu tiếng Việt.

## 3. Encoding và locale không phải một thứ

Hai khái niệm có liên quan nhưng khác nhiệm vụ:

| Thuộc tính | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| **Encoding** | Cách biểu diễn và lưu ký tự dưới dạng byte | `UTF8` |
| **Locale / collation** | Quy tắc so sánh và sắp xếp chuỗi, một số quy tắc phân loại ký tự | `C`, `C.UTF-8`, `vi_VN.UTF-8` hoặc ICU `vi-VN` |
| **Client encoding** | Cách client mã hóa văn bản gửi tới/nhận từ PostgreSQL | `UTF8` |

Một chuỗi như `'Đà Nẵng'` có thể lưu đầy đủ bằng encoding `UTF8`, nhưng vị trí của nó trong kết quả `ORDER BY ten` còn phụ thuộc vào **quy tắc collation**, không chỉ encoding.

~~~sql
-- Ví dụ khi đã kết nối tới PostgreSQL:
SELECT 'Đà Nẵng'::text AS city_name;
~~~

Nếu database dùng UTF-8, nội dung Unicode có thể được lưu mà không cần đổi sang ASCII. Nhưng điều này không tự quy định rằng chữ `Đ` phải được xếp ở vị trí nào trong bảng chữ cái tiếng Việt.

### 3.1. Vì sao UTF8 thường là lựa chọn mặc định tốt?

`UTF8` hỗ trợ Unicode và phù hợp với phần lớn ứng dụng đa ngôn ngữ, API web và dữ liệu có dấu:

~~~text
Họ tên:       Nguyễn Thị Mai
Địa chỉ:      Đà Nẵng
Sản phẩm:     Cà phê rang xay
Ký hiệu:      €  ¥  ✓
~~~

Nên chọn `UTF8` trừ khi có lý do tích hợp rất cụ thể đòi hỏi encoding khác. PostgreSQL hỗ trợ nhiều encoding, nhưng không phải mọi tổ hợp **encoding + locale libc** đều hợp lệ.

**Cần tránh nhầm `SQL_ASCII` với UTF-8.** `SQL_ASCII` không xác nhận đầy đủ encoding cho dữ liệu byte có giá trị cao; nó không phải phương án thay thế an toàn cho việc lưu Unicode đa ngôn ngữ.

### 3.2. Encoding của server khác encoding của client

Sau khi PostgreSQL chạy, kiểm tra:

~~~sql
SHOW server_encoding;
SHOW client_encoding;
~~~

- `server_encoding` phản ánh encoding của **database đang kết nối**, không đơn thuần là một cấu hình toàn bộ mọi database trong cluster.
- `client_encoding` phản ánh cách phiên client trao đổi chuỗi với server.

PostgreSQL có thể chuyển đổi encoding giữa client và database khi cặp mã hóa hỗ trợ chuyển đổi. Tuy nhiên, chọn `UTF8` thống nhất ở cả hai đầu thường giảm rủi ro lỗi ký tự trong ứng dụng hiện đại.

## 4. Các nhóm locale quan trọng

Khi dùng locale của hệ điều hành, PostgreSQL quan tâm tới những danh mục locale như:

| Danh mục | Ý nghĩa chính |
| --- | --- |
| `LC_COLLATE` | Quy tắc sắp xếp và so sánh văn bản |
| `LC_CTYPE` | Phân loại ký tự, một số hành vi chuyển chữ hoa/chữ thường |
| `LC_MESSAGES` | Ngôn ngữ thông báo lỗi/thông báo hệ thống |
| `LC_MONETARY` | Quy ước định dạng tiền tệ |
| `LC_NUMERIC` | Quy ước định dạng số trong những hàm/chế độ liên quan |
| `LC_TIME` | Quy ước hiển thị ngày/giờ trong những hàm định dạng liên quan |

Hai danh mục đặc biệt quan trọng cho **cách dữ liệu văn bản hoạt động** là `LC_COLLATE` và `LC_CTYPE`.

### 4.1. LC_COLLATE tác động tới ORDER BY

~~~sql
SELECT name
FROM customers
ORDER BY name;
~~~

Các tên có dấu, chữ hoa/chữ thường và ký tự đặc biệt có thể được xếp khác nhau dưới các collation khác nhau. Điều này ảnh hưởng tới:

- Thứ tự hiển thị trên màn hình, báo cáo và kết quả truy vấn.
- Khóa chỉ mục B-tree của dữ liệu văn bản và các phép so sánh có liên quan.
- Một số thao tác nhóm, đối chiếu và quy tắc duy nhất tùy kiểu collation.

Nếu yêu cầu sắp xếp tiếng Việt theo ngôn ngữ, hãy đánh giá một collation phù hợp như ICU `vi-VN` hoặc locale libc tiếng Việt có sẵn. Nếu yêu cầu thứ tự đơn giản và dễ dự đoán theo byte, collation `C` là một lựa chọn khác nhưng **không tương đương thứ tự bảng chữ cái tiếng Việt**.

### 4.2. LC_CTYPE tác động tới xử lý ký tự

LC_CTYPE có liên quan tới các thao tác phân loại ký tự và chuyển đổi chữ. Ví dụ:

~~~sql
SELECT
    lower('ABC') AS lower_value,
    upper('abc') AS upper_value;
~~~

Với ký tự ngoài ASCII, kết quả có thể phụ thuộc vào quy tắc locale/ctype và kiểu collation được sử dụng. Do đó, hai database cùng encoding `UTF8` chưa chắc có hành vi xử lý chữ giống nhau nếu dùng cấu hình locale khác.

### 4.3. LC_MESSAGES, LC_NUMERIC, LC_TIME không thay thế kiểu dữ liệu

`LC_MESSAGES` có thể thay đổi ngôn ngữ thông báo của server; `LC_TIME` có thể tác động một số biểu diễn ngày/giờ được định dạng; `LC_NUMERIC` liên quan cách trình bày số trong các hàm phù hợp.

Chúng **không thay đổi cấu trúc lưu trữ nội tại** của kiểu `numeric` hay `timestamp`. Một giá trị số không biến thành kiểu văn bản chỉ vì đổi locale định dạng.

Tùy chọn `--locale` của `initdb` có thể thiết lập mặc định cho các danh mục locale; một số danh mục có thể cấu hình lại sau. Riêng việc đổi **LC_COLLATE và LC_CTYPE mặc định của database đã tồn tại** không đơn giản như chỉnh một tham số phiên.

## 5. Các lựa chọn locale thường gặp

### 5.1. Locale C

~~~text
--locale=C
--encoding=UTF8
~~~

`C` là locale truyền thống, thường có sẵn. Collation `C` sử dụng thứ tự đơn giản dựa trên byte và có tính chất dễ dự đoán, nhưng không mang quy tắc sắp xếp theo tiếng Việt. Có thể kết hợp `C` với encoding `UTF8` để **lưu dữ liệu Unicode**, song những thao tác phân loại ký tự dựa vào locale C có đặc điểm riêng, đặc biệt với ký tự ngoài ASCII.

### 5.2. C.UTF-8 / C.utf8

Ở một số hệ điều hành, có locale `C.UTF-8` hoặc `C.utf8`, kết hợp môi trường xử lý UTF-8 với các tính chất kiểu C. Nhưng **không phải hệ điều hành nào cũng có cùng tên hoặc cùng đặc tính triển khai**.

~~~bash
locale -a
~~~

Chỉ dùng `--locale=C.UTF-8` nếu hệ điều hành thực sự nhận biết locale ấy. Khi cần sắp xếp theo ngôn ngữ, đừng xem `C.UTF-8` đương nhiên tương đương `vi_VN.UTF-8`.

### 5.3. Locale ngôn ngữ từ libc

Ví dụ:

~~~text
vi_VN.UTF-8
en_US.UTF-8
~~~

Chúng được hệ điều hành cung cấp, vì thế cách xử lý collation có thể phụ thuộc vào phiên bản libc và dữ liệu locale của hệ thống. Khi nâng cấp hệ điều hành, cần quan tâm tới thay đổi quy tắc sắp xếp của collation và tác động tới các chỉ mục văn bản.

### 5.4. ICU

**ICU** (*International Components for Unicode*) cung cấp quy tắc collation Unicode theo ngôn ngữ, có thể hữu ích khi cần tính nhất quán sắp xếp đa ngôn ngữ hơn là phụ thuộc hoàn toàn vào locale libc của host.

PostgreSQL hỗ trợ ICU trong các bản được biên dịch với tính năng tương ứng. Cú pháp tùy chọn khởi tạo cluster bằng ICU có trong PostgreSQL 15 trở lên:

~~~bash
initdb \
  --locale-provider=icu \
  --icu-locale=vi-VN \
  --encoding=UTF8 \
  --locale=C.UTF-8 \
  -D /srv/pg-icu-demo/data
~~~

Đây là **mẫu cấu hình**, chưa bao gồm quyền hệ điều hành và thiết lập xác thực. Cần điều chỉnh đường dẫn và locale libc hỗ trợ trên host, kiểm tra bản PostgreSQL có ICU, và **không chạy lại trên PGDATA đã được khởi tạo**.

ICU không có nghĩa mọi phép so sánh chuỗi tự động bỏ qua dấu hoặc phân biệt hoa/thường theo một cách duy nhất. Các thuộc tính collation, tính xác định (*deterministic*) và cách tạo collation cụ thể có thể làm thay đổi hành vi; phải kiểm thử với dữ liệu thật.

## 6. Những tùy chọn initdb cần biết

Cú pháp cơ bản:

~~~bash
initdb -D /duong/dan/pgdata [cac_tuy_chon]
~~~

Các tham số thường gặp:

| Tùy chọn | Công dụng |
| --- | --- |
| `-D` hoặc `--pgdata` | Đường dẫn thư mục dữ liệu cần khởi tạo |
| `-E UTF8` hoặc `--encoding=UTF8` | Chọn encoding mặc định cho database mẫu |
| `--locale=...` | Chọn locale mặc định theo môi trường/cấu hình nhà cung cấp locale |
| `--lc-collate=...` | Chọn LC_COLLATE khi dùng nhóm thiết lập libc phù hợp |
| `--lc-ctype=...` | Chọn LC_CTYPE |
| `--locale-provider=libc` | Dùng nhà cung cấp locale kiểu libc |
| `--locale-provider=icu` | Dùng ICU nếu phiên bản và bản build hỗ trợ |
| `--icu-locale=...` | Chọn ICU locale cho cluster dùng ICU |
| `-U postgres` hoặc `--username=postgres` | Chọn tên role siêu người dùng ban đầu |
| `--auth-local=...` | Chọn phương thức xác thực cho kết nối local |
| `--auth-host=...` | Chọn phương thức xác thực cho kết nối qua host |
| `--pwprompt` | Yêu cầu nhập mật khẩu cho role quản trị ban đầu |
| `--data-checksums` | Bật checksum trang dữ liệu lúc khởi tạo, phục vụ phát hiện một số dạng hỏng trang |

Một số tùy chọn phụ thuộc phiên bản. Trước khi áp dụng nguyên văn, chạy `initdb --help` bằng **đúng binary của server cần tạo** để đối chiếu.

### Chọn username lúc initdb

Role siêu người dùng của PostgreSQL được tạo ở bước initdb. Mặc định tên role thường theo tên người dùng hệ điều hành đã chạy `initdb`; có thể chỉ định `--username=postgres` để rõ ràng.

Đây là **role của PostgreSQL**, không phải tài khoản hệ điều hành. Trên Linux, tài khoản hệ điều hành `postgres` chạy server còn role database `postgres` xác thực và phân quyền trong PostgreSQL; hai khái niệm có thể cùng tên nhưng khác lớp quản lý.

## 7. Thực hành: khởi tạo cluster dùng UTF8 và libc locale

Ví dụ này dành cho Linux dùng PostgreSQL 16 trong thư mục `/usr/lib/postgresql/16/bin`. Nó tạo **instance riêng** trên cổng `55432`, không can thiệp cluster dịch vụ đã có ở cổng `5432`.

### Bước 1. Chuẩn bị thư mục do postgres sở hữu

Chạy trong shell với quyền quản trị hệ điều hành:

~~~bash
sudo install -d -o postgres -g postgres -m 0700 /srv/pg-demo
~~~

Thư mục cha `/srv/pg-demo` thuộc về tài khoản `postgres`. Khi chạy `initdb`, công cụ sẽ tạo thư mục con `data` nếu cần và gán quyền phù hợp. Nếu đã có thư mục `data`, nó phải **rỗng** và có ownership/permission thích hợp.

### Bước 2. Kiểm tra locale khả dụng

~~~bash
locale -a
~~~

Trong ví dụ này giả sử máy có locale `C.UTF-8`. Nếu không có, **không chạy nguyên văn lệnh bên dưới**. Có thể lựa chọn locale được hệ điều hành hỗ trợ, hoặc dùng `--locale=C --encoding=UTF8` khi chính sách sắp xếp cho phép.

### Bước 3. Chạy initdb

~~~bash
sudo -u postgres /usr/lib/postgresql/16/bin/initdb \
  -D /srv/pg-demo/data \
  --encoding=UTF8 \
  --locale=C.UTF-8 \
  --locale-provider=libc \
  --username=postgres \
  --auth-local=peer \
  --auth-host=scram-sha-256 \
  --pwprompt
~~~

Công cụ sẽ hỏi mật khẩu cho role quản trị `postgres`. Hãy nhập bí mật mạnh và lưu theo quy trình quản lý bí mật của tổ chức; **không đưa mật khẩu thật vào đoạn lệnh hoặc mã nguồn**.

Phân tích các lựa chọn:

1. `-D` tạo PGDATA riêng cho bài thực hành.
2. `--encoding=UTF8` đặt encoding mặc định của các database khởi tạo.
3. `--locale=C.UTF-8` chọn locale trên hệ điều hành nếu có.
4. `--locale-provider=libc` dùng nhà cung cấp libc.
5. `--auth-local=peer` cho phép xác thực trên Unix socket bằng danh tính hệ điều hành theo quy tắc peer.
6. `--auth-host=scram-sha-256` yêu cầu xác thực SCRAM cho các bản ghi host mà `initdb` tạo.
7. `--pwprompt` bảo đảm role quản trị ban đầu có mật khẩu được thiết lập khi khởi tạo.

**Lưu ý:** `peer` là cơ chế đặc thù cho kết nối Unix-domain socket trên hệ điều hành hỗ trợ; trên Windows hoặc môi trường không hỗ trợ peer, cần chọn cơ chế khác. Những phương thức xác thực cụ thể phải phù hợp chính sách vận hành. `initdb` sẽ tạo các quy tắc ban đầu trong `pg_hba.conf`, nhưng người quản trị vẫn cần rà soát quyền kết nối mạng, TLS và những dòng cấu hình phát sinh sau đó.

### Bước 4. Khởi động instance thử nghiệm

~~~bash
sudo -u postgres /usr/lib/postgresql/16/bin/pg_ctl \
  -D /srv/pg-demo/data \
  -o "-p 55432 -k /srv/pg-demo" \
  -l /srv/pg-demo/server.log \
  start
~~~

Ở đây:

- `-D` trỏ về đúng PGDATA đã khởi tạo.
- `-o "-p 55432"` chuyển cổng sang `55432` để tránh xung đột với server khác.
- `-k /srv/pg-demo` đặt thư mục Unix socket cho instance thử nghiệm.
- `-l` chỉ nơi ghi log startup/server.

Thư mục socket `/srv/pg-demo` trong bài được giới hạn quyền, nên những người dùng hệ điều hành khác có thể không truy cập được; điều đó phù hợp cho demo quản trị dưới tài khoản `postgres`. Cấu hình dịch vụ thực tế có thể đặt socket ở thư mục chung được bảo vệ bằng quyền hệ điều hành phù hợp.

Nếu lệnh start thất bại, kiểm tra `server.log`, cổng, quyền thư mục và đường dẫn binary. **Không xóa PGDATA để “thử lại” khi chưa hiểu nguyên nhân**, đặc biệt trên server có dữ liệu thật.

### Bước 5. Kết nối và xác minh

~~~bash
sudo -u postgres /usr/lib/postgresql/16/bin/psql \
  -h /srv/pg-demo \
  -p 55432 \
  -U postgres \
  -d postgres
~~~

Trong `psql`, chạy:

~~~sql
SELECT version();
SHOW server_encoding;
SHOW client_encoding;
SHOW lc_collate;
SHOW lc_ctype;
SHOW lc_messages;
~~~

Ví dụ kết quả mong đợi cho những thông số chính:

~~~text
server_encoding  = UTF8
lc_collate       = C.UTF-8
lc_ctype         = C.UTF-8
~~~

Chuỗi locale hiển thị có thể khác về cách viết chữ hoa/chữ thường hoặc tên alias tùy hệ điều hành.

Xem danh sách database mẫu trong `psql`:

~~~text
\l+
~~~

Hoặc truy vấn:

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
ORDER BY datname;
~~~

Trên các phiên bản có nhiều nhà cung cấp locale, cột metadata của `pg_database` và màn hình `\l+` còn có thể cho biết locale provider và ICU locale. Tên trường metadata phụ thuộc phiên bản PostgreSQL, nên không nên dựa vào một tên cột ICU duy nhất cho mọi bản.

### Bước 6. Dừng instance thử nghiệm đúng cách

Sau khi học xong:

~~~bash
sudo -u postgres /usr/lib/postgresql/16/bin/pg_ctl \
  -D /srv/pg-demo/data \
  -m fast \
  stop
~~~

`-m fast` yêu cầu server dừng bằng cách ngắt các phiên còn hoạt động và rollback giao dịch chưa hoàn tất. Lệnh này chỉ dành cho **instance thử nghiệm** đã khởi tạo ở trên; không dùng nhầm với PGDATA của hệ thống đang chạy thật.

## 8. Phương án khác: khởi tạo cluster với ICU locale

Khi cần sắp xếp theo quy tắc ngôn ngữ cụ thể, có thể cân nhắc ICU. Ví dụ cho PostgreSQL 16 **được build với ICU**, trên host có libc locale `C.UTF-8`:

~~~bash
sudo install -d -o postgres -g postgres -m 0700 /srv/pg-icu-demo

sudo -u postgres /usr/lib/postgresql/16/bin/initdb \
  -D /srv/pg-icu-demo/data \
  --encoding=UTF8 \
  --locale-provider=icu \
  --icu-locale=vi-VN \
  --locale=C.UTF-8 \
  --username=postgres \
  --auth-local=peer \
  --auth-host=scram-sha-256 \
  --pwprompt
~~~

Điểm khác:

- `--locale-provider=icu` yêu cầu ICU làm nhà cung cấp collation mặc định cho database được khởi tạo.
- `--icu-locale=vi-VN` chọn locale ICU hướng tới ngôn ngữ tiếng Việt.
- `--locale=C.UTF-8` trong ví dụ vẫn cung cấp giá trị locale libc thích hợp cho những danh mục còn liên quan, vì chọn ICU **không khiến mọi thiết lập locale libc của hệ thống biến mất**.

Hai ví dụ libc và ICU dùng **hai PGDATA độc lập**. Không được chạy lệnh ICU lên `/srv/pg-demo/data` đã khởi tạo bằng libc nhằm “đổi nhà cung cấp locale” của cluster ấy.

### ICU có mặc định sắp đúng mọi cách ứng dụng mong muốn?

Không. Chẳng hạn ứng dụng có thể muốn:

- Phân biệt chữ hoa và chữ thường.
- Không phân biệt chữ hoa/chữ thường khi tìm kiếm.
- Phân biệt dấu tiếng Việt.
- Gom một số biến thể văn bản thành cùng giá trị khi tìm kiếm.

Các nhu cầu này không phải một thiết lập duy nhất. ICU locale là điểm bắt đầu cho quy tắc collation; khi tạo collation cụ thể, có thể cần cân nhắc strength, tính xác định và tác động đến so sánh/index. Trước khi sử dụng trong khóa duy nhất hoặc tìm kiếm quan trọng, hãy kiểm thử bằng tập dữ liệu tiếng Việt thực tế.

## 9. Thử sự khác biệt về thứ tự sắp xếp

Sau khi kết nối tới database thực hành, tạo bảng thử:

~~~sql
CREATE TABLE place_names (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL
);

INSERT INTO place_names (name)
VALUES
    ('An'),
    ('Ánh'),
    ('Anh'),
    ('Đà Nẵng'),
    ('Da Nang'),
    ('Cần Thơ'),
    ('Can Tho'),
    ('Bình Định');
~~~

So sánh:

~~~sql
-- Sắp xếp theo collation mặc định của cột/database.
SELECT name
FROM place_names
ORDER BY name;

-- Ép phép sắp xếp dùng collation C có sẵn trong PostgreSQL.
SELECT name
FROM place_names
ORDER BY name COLLATE "C";
~~~

Kết quả thứ tự có thể khác nhau tùy locale mặc định mà database đang dùng. `COLLATE "C"` yêu cầu quy tắc C cho biểu thức sắp xếp này, **không thay đổi collation mặc định đã được gắn cho toàn bộ database**.

Nếu database đang dùng locale C, hai truy vấn có thể cho thứ tự giống nhau. Vì vậy, muốn so sánh rõ libc tiếng Việt, C và ICU, hãy dùng những database/collation thực sự khác nhau và cùng một tập dữ liệu.

### Kiểm tra collation hiện có

~~~sql
SELECT
    collname,
    collprovider,
    collcollate,
    collctype
FROM pg_collation
WHERE collname IN ('C', 'POSIX')
ORDER BY collname;
~~~

Các cột metadata như `collprovider` giúp nhận biết nhà cung cấp collation; khi dùng ICU, một số trường thông tin và cách hiển thị locale phụ thuộc phiên bản. Để tìm tất cả collation ICU được cài, có thể truy vấn có chọn lọc từ `pg_collation` sau khi xác nhận phiên bản hỗ trợ.

## 10. Vai trò của template0 và template1

Ngay sau `initdb`, cluster có:

| Database | Ý nghĩa |
| --- | --- |
| `postgres` | Database thông dụng dùng cho kết nối quản trị ban đầu |
| `template1` | Mẫu mặc định để `CREATE DATABASE` sao chép |
| `template0` | Mẫu chuẩn không dành cho thay đổi thông thường; hữu ích khi tạo database với encoding/locale khác mẫu mặc định theo quy tắc cho phép |

Khi chạy:

~~~sql
CREATE DATABASE app_db;
~~~

PostgreSQL thường sao chép từ `template1`. Encoding và các thuộc tính locale mặc định của database mới thường kế thừa từ mẫu đó.

### Vì sao không dễ đổi locale khi dùng template1?

Giả sử `template1` có encoding `UTF8` và locale libc `C.UTF-8`. Nếu bạn muốn tạo database mới sử dụng libc locale `vi_VN.UTF-8`, việc sao chép từ một mẫu có cấu hình không tương thích có thể bị từ chối. Đó là lý do PostgreSQL cung cấp `template0` làm điểm bắt đầu chuẩn cho trường hợp cần chọn encoding/locale khác.

Ví dụ **chỉ chạy khi hệ điều hành hỗ trợ `vi_VN.UTF-8`**:

~~~sql
CREATE DATABASE viet_app
    WITH
    TEMPLATE template0
    ENCODING 'UTF8'
    LC_COLLATE 'vi_VN.UTF-8'
    LC_CTYPE 'vi_VN.UTF-8';
~~~

Lệnh này tạo một database mới, không đổi collation của database đã tồn tại. Các cài đặt locale và encoding phải tương thích với provider cũng như môi trường PostgreSQL.

### Tạo database dùng ICU

Với PostgreSQL 15+ có hỗ trợ ICU, có thể cân nhắc cú pháp:

~~~sql
CREATE DATABASE viet_icu
    WITH
    TEMPLATE template0
    ENCODING 'UTF8'
    LOCALE_PROVIDER icu
    ICU_LOCALE 'vi-VN';
~~~

Phải kiểm tra tài liệu/cú pháp của **phiên bản PostgreSQL đang chạy**, vì những tùy chọn locale provider trong `CREATE DATABASE` và metadata hệ thống đã phát triển qua các phiên bản.

**Thông điệp cần nhớ:** quyết định ở `initdb` là **mặc định ban đầu cho các database hệ thống và mẫu**. Nó ảnh hưởng cách database mới kế thừa cấu hình, nhưng không có nghĩa mọi database tạo sau đều bắt buộc phải dùng đúng một collation giống nhau.

## 11. Chọn cấu hình cho từng nhu cầu

| Tình huống | Hướng chọn | Cần cân nhắc |
| --- | --- | --- |
| Ứng dụng web đa ngôn ngữ | `UTF8` | Đồng bộ client encoding và xử lý Unicode |
| Cần thứ tự byte đơn giản, dễ dự đoán | `UTF8` + collation `C` | Không tự mang thứ tự bảng chữ cái tiếng Việt |
| Máy chỉ có locale C và biến thể UTF-8 cơ bản | `UTF8` + locale có sẵn | Kiểm tra `locale -a`; không giả định có `vi_VN.UTF-8` |
| Cần sắp xếp văn bản tiếng Việt theo quy tắc ngôn ngữ | Cân nhắc `vi_VN.UTF-8` (libc) hoặc ICU `vi-VN` | Kiểm thử thứ tự, hiệu năng, độ tương thích hệ điều hành/ICU |
| Cần chuyển dữ liệu giữa nhiều hệ điều hành | Ưu tiên `UTF8`, chủ động kiểm soát collation | Locale libc có thể khác giữa host; ICU cũng có phiên bản quy tắc |
| Hệ thống có chỉ mục văn bản và yêu cầu ổn định lâu dài | Lập kế hoạch quản lý collation version | Sau nâng cấp thư viện locale có thể cần xử lý chỉ mục chịu ảnh hưởng |

Không có câu trả lời “locale nào tốt nhất cho tất cả ứng dụng”. Một hệ thống quản lý mã đơn và tên kỹ thuật có thể ưu tiên `C`; hệ thống danh bạ hoặc từ điển tiếng Việt có thể cần collation theo ngôn ngữ. Điều quan trọng là lựa chọn có chủ đích và kiểm thử trước khi đưa dữ liệu thật vào cluster.

## 12. Có thể đổi encoding hoặc locale sau khi initdb không?

### 12.1. Không đổi tùy ý LC_COLLATE / LC_CTYPE của database hiện tại

Các lựa chọn này gắn với cách database được tạo và ảnh hưởng tới thứ tự chỉ mục văn bản. Đừng nghĩ có thể sửa một dòng trong `postgresql.conf` hoặc chạy `SET lc_collate = ...` là chuyển toàn bộ bảng và chỉ mục sang quy tắc sắp xếp mới.

Thông thường, nếu cần thay đổi **mặc định** encoding/locale của một database đang có dữ liệu, phải lên kế hoạch:

1. Kiểm tra encoding, locale provider và collation hiện hành.
2. Tạo database đích mới với cấu hình mong muốn (có thể dùng `template0`).
3. Di chuyển dữ liệu bằng phương pháp xuất/nhập hoặc migration tương thích.
4. Đảm bảo index, constraint, kết quả so sánh, tìm kiếm và tính duy nhất phù hợp.
5. Chuyển ứng dụng sau khi đã kiểm thử và có phương án rollback.

Các thao tác liên quan thay đổi encoding/locale không nên được thực hiện trực tiếp lên database sản xuất khi chưa có backup và phương án chuyển đổi.

### 12.2. Database encoding và client_encoding khác cách thay đổi

`client_encoding` có thể điều chỉnh theo phiên để trao đổi văn bản:

~~~sql
SET client_encoding = 'UTF8';
SHOW client_encoding;
~~~

Điều này **không chuyển encoding lưu trữ** của database đang mở. `server_encoding` là thuộc tính của database, còn `client_encoding` là cách client giao tiếp với server.

### 12.3. Nâng cấp ICU/libc có thể ảnh hưởng collation

Quy tắc so sánh chuỗi có thể thay đổi khi nâng cấp hệ điều hành, libc hoặc ICU. Nếu quy tắc sort thay đổi, một chỉ mục B-tree trên dữ liệu văn bản xây dựng theo quy tắc cũ có thể không còn phản ánh đúng thứ tự mới.

PostgreSQL có cơ chế theo dõi **collation version** đối với những provider/trường hợp được hỗ trợ. Khi có cảnh báo khác biệt phiên bản collation, cần kiểm tra, tái tạo các đối tượng bị ảnh hưởng (thường là `REINDEX` những chỉ mục liên quan) và làm mới metadata phiên bản theo đúng quy trình. **Chỉ xác nhận metadata là mới mà chưa xử lý chỉ mục không đủ bảo đảm tính nhất quán**.

Đây là một lý do quan trọng để ghi lại **phiên bản PostgreSQL, hệ điều hành và thư viện locale** trong thông tin vận hành của cluster.

## 13. Bảo mật và quyền truy cập lúc khởi tạo

`initdb` không chỉ tạo thư mục; nó còn sinh cấu hình xác thực ban đầu. Khi đặt cụm dữ liệu vào môi trường thực tế, không nên bỏ qua các tùy chọn này.

### 13.1. Tránh cấu hình trust ngoài phạm vi kiểm soát

Xác thực `trust` cho phép những kết nối khớp quy tắc xác thực truy cập mà không cần mật khẩu. Tùy hoàn cảnh, nó có thể hữu ích ở một môi trường bị cô lập hoàn toàn, nhưng không nên là lựa chọn mặc định cho môi trường có nhiều người hoặc kết nối mạng.

Mẫu thực hành đã chọn:

~~~text
--auth-local=peer
--auth-host=scram-sha-256
--pwprompt
~~~

Ý nghĩa là:

- Kết nối socket nội bộ được xác thực theo danh tính hệ điều hành.
- Kết nối theo các dòng host do initdb tạo dùng cơ chế mật khẩu SCRAM.
- Role quản trị được yêu cầu đặt mật khẩu.

`pg_hba.conf` quyết định **ai có thể thử đăng nhập từ đâu và theo phương thức gì**; `postgresql.conf` có các thiết lập như `listen_addresses` và `port`. Các lớp firewall, TLS và quyền ứng dụng vẫn cần quản lý riêng.

### 13.2. Không lưu mật khẩu quản trị trong script

Trong ví dụ, `--pwprompt` cho phép nhập mật khẩu khi khởi tạo. Ngoài cách này, `initdb` có tùy chọn đọc mật khẩu từ tệp được bảo vệ; nếu dùng tự động hóa, nên tích hợp kho bí mật và kiểm soát permission/file lifecycle thay vì để plaintext trong command history hoặc repository.

### 13.3. Quyền hệ điều hành trên PGDATA

Thư mục PGDATA chứa bảng và metadata quan trọng. Không dùng quyền truy cập rộng rãi như `chmod 777` để xử lý lỗi khởi động. Hãy xác minh owner, group và chế độ quyền đáp ứng yêu cầu PostgreSQL; giới hạn truy cập theo tài khoản dịch vụ và nhóm vận hành được ủy quyền.

## 14. Lỗi thường gặp khi chạy initdb

### 14.1. Chạy initdb dưới root

**Hiện tượng:** công cụ báo không được chạy bởi root.

**Nguyên nhân:** PostgreSQL yêu cầu cluster thuộc về tài khoản hệ điều hành không đặc quyền.

**Cách xử lý:** tạo tài khoản dịch vụ phù hợp và chạy `initdb` bằng tài khoản đó:

~~~bash
sudo -u postgres /usr/lib/postgresql/16/bin/initdb \
  -D /srv/pg-demo/data \
  --encoding=UTF8 \
  --locale=C
~~~

Đây chỉ là minh họa cách chạy đúng owner; trong cấu hình thực hành hoàn chỉnh hãy dùng thêm các tùy chọn xác thực an toàn đã trình bày.

### 14.2. Thư mục dữ liệu không rỗng

**Hiện tượng:** `initdb` từ chối vì PGDATA chứa tệp hoặc một cluster khác.

**Nguyên nhân:** `initdb` được thiết kế để khởi tạo một cluster mới, **không ghi đè** dữ liệu đang có.

**Cách xử lý:** xác minh chính xác path và owner. Nếu đó là cluster thật, không xóa và không initdb lại. Nếu đang làm lab và muốn tạo mới, chọn một đường dẫn chưa dùng sau khi đã kiểm tra rõ trạng thái dữ liệu.

### 14.3. Locale không tồn tại

**Hiện tượng:** lỗi liên quan `invalid locale name` hoặc không thiết lập được locale.

**Nguyên nhân:** locale chưa được cung cấp bởi hệ điều hành, tên khác, hoặc môi trường container thiếu dữ liệu locale.

**Cách xử lý:**

~~~bash
locale -a
~~~

Sau đó chọn đúng tên đang có, cài thêm locale bằng công cụ hệ điều hành nếu được phép, hoặc dùng `C` với `UTF8` khi phù hợp với yêu cầu. **Không đổi sang `SQL_ASCII` chỉ để né lỗi tên locale**.

### 14.4. Encoding không tương thích locale

**Hiện tượng:** `initdb` từ chối tổ hợp encoding/locale.

**Nguyên nhân:** locale hệ điều hành có yêu cầu encoding không tương thích với mã hóa được chọn trong trường hợp dùng libc.

**Cách xử lý:** xem tên locale và encoding tương ứng. Với ứng dụng hiện đại, một locale UTF-8 khả dụng cùng `--encoding=UTF8` thường là hướng phù hợp.

### 14.5. Cổng PostgreSQL đã được sử dụng

**Hiện tượng:** `initdb` thành công nhưng `pg_ctl start` thất bại và log cho biết không thể bind cổng.

**Nguyên nhân:** một server khác đã lắng nghe cổng mặc định.

**Cách xử lý:** chạy instance lab trên cổng riêng, ví dụ `55432`, hoặc thay đổi cổng trong cấu hình sau khi xác định đúng instance. **Đừng dừng dịch vụ PostgreSQL hiện tại** chỉ để chạy ví dụ.

### 14.6. Không kết nối được dù server đã chạy

Kiểm tra:

- Cổng, host hoặc Unix socket directory mà client sử dụng.
- Role database có tồn tại không.
- Dòng xác thực trong `pg_hba.conf` có cho phép kiểu kết nối đó không.
- `listen_addresses`, firewall và TLS nếu truy cập qua mạng.
- Mật khẩu hoặc danh tính hệ điều hành khi dùng `peer`.

Ví dụ `psql -h 127.0.0.1` sử dụng kết nối TCP nên **khác** với `psql -h /srv/pg-demo` dùng Unix socket; quy tắc `pg_hba.conf` áp dụng có thể khác.

### 14.7. Chỉnh locale rồi cho rằng chỉ mục tự cập nhật

Một database có hàng triệu khóa văn bản không được đổi an toàn sang quy tắc sort khác chỉ bằng chỉnh file cấu hình. Cần kiểm soát quá trình tạo database/migration, collation version và xây lại chỉ mục liên quan khi cần.

## 15. Bài tập thực hành

Các bài tập tập trung vào việc giải thích cấu hình và lập kế hoạch, không yêu cầu thao tác trên cơ sở dữ liệu sản xuất.

**Bài 1.** Phân biệt ý nghĩa của `initdb` và `pg_ctl start`. Sau khi `initdb` thành công, ứng dụng đã có thể kết nối PostgreSQL ngay chưa?

**Bài 2.** Một ứng dụng lưu họ tên tiếng Việt và tên sản phẩm đa ngôn ngữ. Vì sao `UTF8` thường phù hợp? `UTF8` có tự bảo đảm thứ tự tên tiếng Việt trong `ORDER BY` không?

**Bài 3.** Một máy Linux chỉ liệt kê `C` và `C.utf8` qua `locale -a`. Người quản trị chạy `initdb --locale=vi_VN.UTF-8` và bị lỗi. Cần kiểm tra và xử lý điều gì?

**Bài 4.** Hãy viết câu lệnh `initdb` tạo cluster mới tại `/srv/pg-exercise/data` với encoding UTF8, locale C, user quản trị `postgres`, xác thực local peer và host SCRAM. Giả sử người dùng hệ điều hành hiện tại là `postgres`.

**Bài 5.** Nêu hai câu `SHOW` xác định encoding của database và collation mặc định. Nêu một cách xem danh sách database mẫu sau khi initdb.

**Bài 6.** Tại sao không nên dùng `template1` theo cách mặc định khi muốn tạo database libc `vi_VN.UTF-8` từ một cluster có template1 với locale `C.UTF-8`? `template0` có vai trò gì?

**Bài 7.** Sau khi nâng cấp hệ điều hành, PostgreSQL cảnh báo phiên bản collation thay đổi. Có nên chỉ tắt cảnh báo rồi tiếp tục dùng chỉ mục cũ không?

**Bài 8.** Một lập trình viên muốn “đổi database đang tồn tại sang UTF8” bằng cách chạy `SET client_encoding='UTF8'`. Lệnh này thay đổi điều gì và không thay đổi điều gì?

### Đáp án tham khảo

**Bài 1:** `initdb` tạo cluster và các tệp dữ liệu; `pg_ctl start` khởi động server trên PGDATA đó. Sau khi chỉ chạy `initdb`, chưa có tiến trình server nhận kết nối.

**Bài 2:** UTF8 hỗ trợ Unicode, giúp lưu tiếng Việt và nhiều ngôn ngữ. Quy tắc sắp xếp là vấn đề của locale/collation, không được quyết định chỉ bởi encoding.

**Bài 3:** xem chính xác locale đang khả dụng và cài/khai báo locale tiếng Việt nếu môi trường cho phép. Nếu chính sách ứng dụng không cần quy tắc sắp xếp tiếng Việt ở mức mặc định, có thể cân nhắc `C.utf8` hoặc `C` kết hợp `UTF8`, hiểu rõ khác biệt.

**Bài 4:**

~~~bash
initdb \
  -D /srv/pg-exercise/data \
  --encoding=UTF8 \
  --locale=C \
  --username=postgres \
  --auth-local=peer \
  --auth-host=scram-sha-256 \
  --pwprompt
~~~

Thư mục đích phải trống hoặc chưa tồn tại, có đủ quyền và dung lượng; không chạy lệnh dưới root.

**Bài 5:**

~~~sql
SHOW server_encoding;
SHOW lc_collate;
~~~

Trong `psql`, chạy `\l+`; hoặc truy vấn `pg_database`. Có thể kiểm tra thêm `SHOW lc_ctype;` và `SHOW client_encoding;` khi cần.

**Bài 6:** `CREATE DATABASE` mặc định sao chép `template1` và chịu những ràng buộc tương thích encoding/locale. `template0` là mẫu chuẩn giúp tạo database với lựa chọn phù hợp khác mặc định khi PostgreSQL cho phép.

**Bài 7:** không. Cần xác minh collation version, xem các index/đối tượng chịu ảnh hưởng, tái tạo khi cần và cập nhật metadata đúng quy trình. Chỉ tắt hoặc xóa dấu cảnh báo không sửa được thứ tự chỉ mục cũ.

**Bài 8:** `SET client_encoding='UTF8'` đổi mã hóa trao đổi văn bản của **phiên client**. Nó không chuyển encoding lưu trữ `server_encoding` của database hiện có.

## 16. Danh sách kiểm tra trước khi đưa cluster vào sử dụng

| Nhóm | Câu hỏi cần trả lời |
| --- | --- |
| Phiên bản | `initdb` và `postgres` có thuộc cùng bản phù hợp không? |
| Dữ liệu | PGDATA có trống, đúng owner và nơi lưu trữ an toàn không? |
| Encoding | Đã chọn `UTF8` hoặc encoding tương thích yêu cầu ứng dụng chưa? |
| Locale | Hệ điều hành/ICU có hỗ trợ locale dự kiến không? |
| Provider | Đã chủ động chọn `libc` hay `ICU` theo nhu cầu sắp xếp chưa? |
| LC_COLLATE / LC_CTYPE | Đã kiểm tra tác động tới so sánh, tìm kiếm và index văn bản chưa? |
| Xác thực | `pg_hba.conf`, phương thức xác thực và role quản trị ban đầu có an toàn không? |
| Kết nối | Server sẽ chạy trên đúng cổng, socket, host và phạm vi mạng chưa? |
| Quan sát | Có thể xác minh `server_encoding`, `lc_collate`, `lc_ctype` và database mẫu chưa? |
| Vận hành | Đã lên kế hoạch backup, log, giám sát và nâng cấp collation version chưa? |

**Ghi nhớ:** `initdb` không chỉ tạo một thư mục rỗng có vài tệp cấu hình. Nó thiết lập **nền tảng lưu trữ và các giá trị mặc định cho những database đầu tiên** của PostgreSQL. Chọn `UTF8` để lưu Unicode, lựa chọn locale/provider để xác định cách xử lý văn bản, và xác minh chúng ngay khi khởi tạo sẽ tránh nhiều chi phí sửa đổi về sau. Nếu muốn thay đổi encoding hoặc collation mặc định của database đã tồn tại, hãy lập kế hoạch tạo database đích và migration thích hợp thay vì cố chỉnh trực tiếp PGDATA.
