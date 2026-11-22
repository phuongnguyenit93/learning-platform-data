# Phân biệt môi trường học tập, kiểm thử và sản xuất khi cài đặt PostgreSQL

Cùng một câu lệnh `CREATE TABLE` có thể chạy trên máy cá nhân, trong pipeline kiểm thử hoặc trên máy chủ phục vụ hàng nghìn người dùng. Nhưng **mức độ an toàn của thao tác phụ thuộc môi trường đang kết nối**, chứ không phụ thuộc câu lệnh trông đơn giản đến đâu. Xóa và tạo lại một database thực hành thường là việc bình thường; làm như vậy với database sản xuất có thể gây gián đoạn nghiêm trọng hoặc mất dữ liệu không thể khôi phục đúng thời điểm.

Khi học cài đặt PostgreSQL, mục tiêu không chỉ là khởi động server thành công. Người học cần biết phân biệt rõ:

- **Môi trường học tập/phát triển cục bộ** (*local learning/development*): nơi thử cú pháp và xây chức năng.
- **Môi trường kiểm thử tự động** (*test/CI*): nơi dữ liệu có thể được tạo lại có kiểm soát để xác nhận hành vi.
- **Môi trường tích hợp/tiền sản xuất** (*integration/staging/pre-production*): nơi thử cách các thành phần hoạt động cùng nhau trong cấu hình gần sản xuất.
- **Môi trường sản xuất** (*production*): nơi dữ liệu thật, cam kết dịch vụ, bảo mật và khả năng phục hồi là ưu tiên hàng đầu.

Bài học đưa ra mô hình phân tách môi trường, ví dụ cài PostgreSQL cho mục đích học và test, các bước xác minh mình đang kết nối tới đâu, quy tắc quản lý dữ liệu và credential, cùng các điều kiện trước khi đưa một thay đổi lên production. Các ví dụ là hướng dẫn thực hành cho PostgreSQL hiện đại; cần đối chiếu phiên bản, hệ điều hành và hạ tầng cụ thể trước khi áp dụng.

## 1. Vì sao phải phân biệt môi trường ngay từ lúc cài đặt?

Hãy hình dung một lập trình viên đang thử chức năng đăng ký tài khoản. Để chạy lại dữ liệu mẫu, người đó có đoạn SQL:

~~~sql
TRUNCATE TABLE app.users RESTART IDENTITY CASCADE;
~~~

Trong **database thử nghiệm được dành riêng**, câu lệnh này có thể là một phần của quá trình làm sạch dữ liệu. Nhưng nếu connection string vô tình trỏ tới production, nó có thể xóa hàng loạt bản ghi và các bảng phụ thuộc qua `CASCADE`. PostgreSQL không biết “ý định của người viết là đang thử nghiệm” chỉ vì máy client là laptop.

Phân tách môi trường giúp giảm các rủi ro:

1. **Mất dữ liệu:** lệnh test hoặc seed phá hủy dữ liệu thật.
2. **Lộ dữ liệu:** bản sao từ production chứa email, số điện thoại, khóa API hoặc thông tin cá nhân được đưa lên máy học tập không đủ bảo vệ.
3. **Khác biệt cấu hình:** truy vấn chạy được trên local nhưng thất bại ở production do phiên bản, extension, quyền hoặc timeout khác nhau.
4. **Hiệu năng sai lệch:** test trên 20 dòng dữ liệu không phản ánh table scan hoặc lock contention với hàng triệu dòng.
5. **Rủi ro bảo mật:** dùng tài khoản `postgres` có quyền cao cho cả ứng dụng và người học.
6. **Không thể tái lập:** mỗi máy tạo bảng thủ công khác nhau, khiến lỗi chỉ xuất hiện ở một môi trường.
7. **Khó phục hồi:** không có backup kiểm chứng hoặc không biết lúc nào nên dùng rollback, restore hay failover.

Vì vậy, **môi trường không chỉ là tên database**. Nó là sự kết hợp của hạ tầng, dữ liệu, người được truy cập, quyền, cấu hình, quy trình triển khai, bảo vệ, giám sát và mục tiêu sẵn sàng.

## 2. So sánh nhanh các loại môi trường

| Tiêu chí | Học tập / local | Test tự động / CI | Staging / tiền sản xuất | Production |
| --- | --- | --- | --- | --- |
| Mục tiêu chính | Học SQL, thử tính năng, debug | Xác minh mã và migration lặp lại được | Diễn tập tích hợp và phát hành | Phục vụ nghiệp vụ thật |
| Dữ liệu | Giả lập, ít, có thể xóa | Tự động seed, độc lập giữa test | Đại diện về cấu trúc/khối lượng; được ẩn danh nếu xuất phát từ dữ liệu thật | Dữ liệu nghiệp vụ chính thức |
| Cách cấp phát | PostgreSQL local, container, instance lab | Database/container tạm cho từng job hoặc suite | Instance quản lý riêng, càng gần cấu hình production càng tốt | Instance/cluster được quản trị theo yêu cầu vận hành |
| Quyền | Người học có thể có quyền tạo bảng trong lab | Role test giới hạn đúng database test | Role như production, tách quyền migration | Least privilege nghiêm ngặt, audit truy cập |
| Tái tạo dữ liệu | Có thể reset có chủ đích | Ưu tiên tự động và idempotent | Reset có kế hoạch, không tùy tiện giữa các nhóm dùng chung | Không reset bằng test script |
| Backup | Tùy giá trị dữ liệu học | Thường không cần backup mỗi run nếu dữ liệu tái tạo được | Cần cho dữ liệu/cấu hình có giá trị và các diễn tập liên quan | Bắt buộc theo RPO/RTO, có thử restore |
| Giám sát | Log và công cụ đơn giản | Kết quả test, log container | Metric, trace, log để tìm vấn đề trước phát hành | Alert, SLO, incident response và runbook |
| Bảo mật mạng | Chỉ local khi có thể | CI network tách biệt | Hạn chế truy cập như production | Private network, TLS, chính sách xác thực chặt |
| Tác động sự cố | Thường ảnh hưởng một người học | Ảnh hưởng pipeline | Ảnh hưởng kiểm thử/tập dượt triển khai | Ảnh hưởng khách hàng, doanh thu và dữ liệu |

Đây là **mô hình mục tiêu**, không phải mọi tổ chức đều có đúng bốn tầng ngay từ ngày đầu. Một dự án nhỏ có thể bắt đầu bằng local + test + production, nhưng **không nên dùng production làm nơi kiểm thử phá hủy dữ liệu**. Khi số người phát triển, số tích hợp và mức rủi ro tăng, staging riêng trở nên cần thiết.

### 2.1. Sơ đồ luồng phát hành

~~~mermaid
flowchart LR
    L["Local<br/>thử SQL và code"] --> T["Test/CI<br/>tạo DB tạm và test"]
    T --> S["Staging<br/>kiểm tra tích hợp"]
    S --> P["Production<br/>triển khai có kiểm soát"]
    M["Migration trong Git"] --> T
    M --> S
    M --> P
    D["Dữ liệu giả lập / đã ẩn danh"] --> L
    D --> T
    D --> S
    P -. "không sao chép trực tiếp dữ liệu nhạy cảm" .-> D
~~~

Một điểm đặc biệt của mô hình: **cùng bộ migration được thử rồi được triển khai qua từng môi trường**, chứ không sửa tay một bảng ở local, một bảng khác trên staging và một phiên bản nữa ở production.

## 3. Database, schema và PostgreSQL cluster: khác nhau về mức cách ly

Trong PostgreSQL, các khái niệm này không thể dùng thay thế tùy ý:

| Đơn vị | Ý nghĩa | Mức cách ly |
| --- | --- | --- |
| **Schema** | Không gian tên như `public`, `sales` nằm trong một database | Phân tách tên/quyền object; **vẫn cùng database** |
| **Database** | Không gian dữ liệu có tên mà client kết nối vào, như `shop_dev` | Phân tách bảng/schema trong cùng một PostgreSQL instance; **vẫn chia sẻ tài nguyên instance** |
| **PostgreSQL instance/cluster** | Một server PostgreSQL quản lý nhiều database và các thiết lập/cấu trúc chung | Chia sẻ tiến trình, WAL, memory, cấu hình instance và một số tài nguyên hệ thống |
| **Máy ảo/container/managed deployment riêng** | Ranh giới triển khai và quản trị ở mức hạ tầng | Có thể cách ly mạnh hơn nếu network, storage, identity và quyền được tách |

Ví dụ đặt `shop_dev` và `shop_prod` làm hai database trong cùng một instance có thể giảm nguy cơ truy vấn nhầm tên bảng, nhưng **không phải cách ly hoàn toàn**:

- Chúng dùng chung CPU, RAM, I/O, disk và giới hạn connection của server.
- Một tài khoản superuser có thể tác động tới cả hai.
- Sự cố instance hoặc đầy ổ đĩa có thể ảnh hưởng cả hai.
- Những cấu hình như `shared_buffers`, `max_connections` và `wal_level` thuộc instance, không độc lập trên mỗi database.

Vì thế, đối với **production**, nên có ranh giới hạ tầng và quyền rõ ràng so với môi trường học/test. Với học tập trên một máy, nhiều database trên cùng instance vẫn hữu ích, nhưng phải hiểu giới hạn của cách ly này.

## 4. Chặng học tập: cài PostgreSQL để thử SQL mà không ảnh hưởng hệ thống khác

Có nhiều lựa chọn hợp lệ:

1. **Cài PostgreSQL trực tiếp** trên máy cá nhân: phù hợp muốn hiểu service, file cấu hình, `psql`, quyền của hệ điều hành và vận hành cơ bản.
2. **Chạy PostgreSQL trong container**: thuận tiện tạo/xóa môi trường lab độc lập, cố định phiên bản và dựng lại nhanh.
3. **Dùng instance lab trên cloud**: phù hợp bài tập kết nối từ xa, TLS và vận hành managed service, nhưng có chi phí và yêu cầu kiểm soát mạng.

Đối với người mới, container cục bộ thường giúp giảm việc chỉnh sửa hệ thống máy. Tuy vậy, container **không tự làm mọi thứ an toàn**: nếu publish cổng ra mọi interface, dùng mật khẩu yếu trên mạng chung hoặc gắn nhầm volume sản xuất thì vẫn có rủi ro.

### 4.1. Ví dụ chạy một PostgreSQL lab bằng Docker

Đây là ví dụ **chỉ để học trên máy cục bộ** với phiên bản hình ảnh được chỉ định tường minh:

~~~bash
docker run --name pg-learning-41 \
  -e POSTGRES_USER=lab_admin \
  -e POSTGRES_PASSWORD=lab-only-change-me \
  -e POSTGRES_DB=learning_db \
  -p 127.0.0.1:5541:5432 \
  -v pg-learning-41-data:/var/lib/postgresql/data \
  -d postgres:17
~~~

Đây là lệnh có cú pháp xuống dòng kiểu Bash; trên PowerShell/Windows nên viết một dòng hoặc chuyển sang cú pháp nối dòng tương thích. Chỉ chạy khi đã cài Docker và bảo đảm tên container/volume chưa tồn tại.

Giải thích:

- `postgres:17` cố định dòng major version trong ví dụ, tránh thay đổi major bất ngờ do dùng tag `latest`. Khi cần triển khai tái lập nghiêm ngặt, có thể pin thêm bản patch/digest theo chính sách image.
- `POSTGRES_DB=learning_db` tạo database ban đầu khi **data directory đang trống**.
- `-p 127.0.0.1:5541:5432` chỉ ánh xạ cổng đến loopback trên máy host, giảm việc vô tình mở PostgreSQL ra mạng.
- `pg-learning-41-data` là Docker volume bền vững: xóa container **không tự xóa volume**; điều này tốt cho việc học nhưng cần nhớ khi muốn reset.
- Mật khẩu `lab-only-change-me` là **giá trị minh họa, không dùng cho dịch vụ thật**, và cách truyền secret qua biến môi trường/CLI có thể bị nhìn thấy bởi công cụ hoặc người có quyền quản trị hệ thống. Production cần secret manager/cơ chế bảo mật thích hợp.

Kiểm tra kết nối ngay trong container:

~~~bash
docker exec -it pg-learning-41 \
  psql -U lab_admin -d learning_db
~~~

Hoặc từ máy host đã cài `psql`:

~~~bash
psql -h 127.0.0.1 -p 5541 -U lab_admin -d learning_db
~~~

Không cần quyền superuser của hệ điều hành để học mọi cú pháp SQL; role `lab_admin` có quyền cao trong **instance lab** chỉ nên dùng tại đây, không được tái sử dụng cho production.

### 4.2. Kiểm tra đúng server và database sau khi kết nối

Trong `psql`:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS connected_role,
    current_setting('server_version') AS postgres_version,
    current_setting('port') AS server_port,
    current_setting('TimeZone') AS session_timezone;
~~~

Và meta-command:

~~~text
\conninfo
\l
\dn
~~~

`\conninfo` cung cấp thông tin kết nối hiện tại; `\l` liệt kê database và `\dn` liệt kê schema mà role có quyền quan sát. Các lệnh bắt đầu bằng dấu `\` là **psql meta-command**, không phải SQL gửi được nguyên xi qua JDBC.

Khi dùng kết nối qua proxy hoặc load balancer, tên host/cổng client thấy có thể khác địa chỉ thực của database backend. Nếu cần xác nhận database đích, hãy kết hợp connection profile, hạ tầng, thông tin người dùng, TLS và những câu truy vấn metadata thay vì chỉ tin vào tên môi trường trong prompt.

### 4.3. Tạo một schema để thực hành

~~~sql
CREATE SCHEMA IF NOT EXISTS sandbox;

CREATE TABLE IF NOT EXISTS sandbox.notes (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT notes_title_nonblank
        CHECK (length(btrim(title)) > 0)
);

INSERT INTO sandbox.notes (title)
VALUES ('Học PostgreSQL trong môi trường riêng');

SELECT note_id, title, created_at
FROM sandbox.notes
ORDER BY note_id;
~~~

Các bước trên là thao tác **thực tế có ghi dữ liệu vào database học tập**. `CREATE TABLE IF NOT EXISTS` không xác minh bảng đang tồn tại có cấu trúc đúng như câu lệnh mong muốn; khi quản lý ứng dụng có migration, cần migration kiểm soát phiên bản thay vì chỉ bỏ qua xung đột tên.

### 4.4. Dọn môi trường lab đúng phạm vi

Để dừng container mà vẫn giữ dữ liệu:

~~~bash
docker stop pg-learning-41
~~~

Để khởi động lại:

~~~bash
docker start pg-learning-41
~~~

Nếu chủ động muốn xóa **container lab**:

~~~bash
docker rm -f pg-learning-41
~~~

Lệnh này không mặc định xóa named volume `pg-learning-41-data`. **Lệnh xóa volume sau sẽ làm mất toàn bộ dữ liệu PostgreSQL trong volume lab đó**; chỉ chạy sau khi xác nhận đây đúng là volume thử nghiệm và không còn dữ liệu cần giữ:

~~~bash
docker volume rm pg-learning-41-data
~~~

Không áp dụng những thao tác container/volume này lên hệ thống người khác hoặc hạ tầng production. Bản sao dữ liệu quan trọng phải có backup và quy trình khôi phục trước khi xóa.

## 5. Test tự động: database phải tái lập được và độc lập

Môi trường **test** không chỉ là “database dev có thêm vài hàng”. Test tốt cần có khả năng:

- Tạo dữ liệu đầu vào xác định trước.
- Kiểm tra kết quả đúng/sai theo điều kiện đã thiết kế.
- Chạy lại nhiều lần không phụ thuộc dữ liệu từ lần trước.
- Không ghi vào production hoặc database của thành viên khác.
- Dọn tài nguyên sau test, hoặc quản lý vòng đời môi trường riêng nếu cần điều tra lỗi.

Ví dụ hệ thống bán hàng có hai bảng `customers` và `orders`. Khi kiểm thử tính toàn vẹn, nên dùng transaction và rollback trong **database test riêng**:

~~~sql
BEGIN;

CREATE TEMP TABLE test_customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);

INSERT INTO test_customers (customer_id, email)
VALUES (1, 'demo@example.test');

SELECT count(*) AS expected_one
FROM test_customers;

ROLLBACK;
~~~

Ở đây `CREATE TEMP TABLE` tạo bảng tạm cho session hiện hành, còn `ROLLBACK` hoàn tác thay đổi trong transaction. Ví dụ minh họa một kiểu thử nghiệm độc lập; với integration test cần kiểm thử ràng buộc trên **schema thật của ứng dụng**, phải chạy migration thực tế trong một database test rồi nạp fixture tương ứng, không thay thế hoàn toàn bằng temporary table tự tạo khác schema.

### 5.1. Tạo database test riêng cho mỗi job

Trong CI, một chiến lược phổ biến là:

~~~text
CI job A -> PostgreSQL service A -> database test_a -> schema migration -> fixtures -> tests -> cleanup
CI job B -> PostgreSQL service B -> database test_b -> schema migration -> fixtures -> tests -> cleanup
~~~

Hai job không chia sẻ cùng một database ghi dữ liệu. Khi mỗi job có một container/instance ngắn hạn, thao tác `DROP DATABASE` chỉ nên được cho phép trong vòng đời **tài nguyên do chính job đó tạo** và đã xác định đúng danh tính.

Nếu CI không thể dùng container mới cho mỗi run, cần một chiến lược đặt tên database độc nhất, quyền chỉ trong phạm vi test, cleanup có kiểm tra và giới hạn tối đa tài nguyên. Không cho job test tài khoản có quyền xóa database khác trên cùng server.

### 5.2. Chiến lược dữ liệu test

| Cách chuẩn bị | Dùng khi nào | Lưu ý |
| --- | --- | --- |
| **Seed cố định** | Kiểm tra logic và kết quả mong đợi rõ ràng | Dễ tái lập; số lượng nhỏ |
| **Factory sinh dữ liệu** | Nhiều biến thể input/quan hệ | Phải đảm bảo ràng buộc và làm sạch mỗi test |
| **Property-based testing** | Khám phá các trường hợp biên | Ghi lại seed ngẫu nhiên để tái hiện lỗi |
| **Dữ liệu gần thật đã ẩn danh** | Thử tích hợp, thống kê, hiệu năng | Cần chính sách xử lý dữ liệu nhạy cảm |
| **Snapshot khối lượng lớn** | Kiểm tra migration, kế hoạch truy vấn | Tốn tài nguyên; đảm bảo schema/version đúng |

Tránh dùng một snapshot chứa dữ liệu cá nhân chưa ẩn danh để “test cho giống production” trên laptop hoặc runner không được bảo vệ. Những trường như email, số điện thoại, địa chỉ, khóa đăng nhập, token và dữ liệu thanh toán cần chính sách giảm thiểu/ẩn danh phù hợp. **Chỉ đổi tên file dump không phải ẩn danh dữ liệu**.

### 5.3. Giới hạn của cách rollback mỗi test

Nhiều framework mở transaction cho mỗi test, rồi rollback sau khi assertion xong. Cách này hữu ích, nhưng không đủ để kiểm tra mọi trường hợp:

1. **Sequence/identity** không có hành vi rollback giống dữ liệu bảng: giá trị sequence đã phát có thể không quay lại, nên đừng kỳ vọng ID bắt đầu từ 1 sau mỗi test.
2. Test có **nhiều connection** không tự cùng một transaction; dữ liệu chưa commit ở connection A thường không hiển thị cho B.
3. Test transaction bọc ngoài có thể **che lỗi commit** vì code ứng dụng thực tế không commit trong quá trình test.
4. Tác dụng ra ngoài database như message queue, file hoặc HTTP request không được rollback cùng PostgreSQL.
5. Một lỗi SQL trong transaction có thể đặt transaction PostgreSQL vào trạng thái aborted; để tiếp tục cần rollback hoặc dùng savepoint thích hợp.

Do đó cần cả unit test, integration test trên PostgreSQL thật, test commit/rollback và test đồng thời theo phạm vi nghiệp vụ.

### 5.4. Ví dụ kiểm tra ràng buộc ở test

~~~sql
BEGIN;

CREATE TEMP TABLE test_products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL CHECK (price > 0)
);

INSERT INTO test_products (product_id, sku, price)
VALUES (1, 'SKU-001', 120000.00);

SAVEPOINT before_invalid_insert;

-- Lỗi cố ý: unique_violation, SQLSTATE 23505.
INSERT INTO test_products (product_id, sku, price)
VALUES (2, 'SKU-001', 130000.00);

-- Sau lỗi cần thực hiện bằng cùng session:
ROLLBACK TO SAVEPOINT before_invalid_insert;

SELECT count(*) AS expected_one
FROM test_products;

ROLLBACK;
~~~

Đây là **mẫu thao tác tương tác**: client phải tiếp tục gửi câu `ROLLBACK TO SAVEPOINT` sau câu gây lỗi. Một số runner hoặc script bật “dừng ngay khi SQL lỗi” sẽ dừng trước dòng rollback; khi đó test framework phải bắt exception và tự rollback theo cơ chế của nó. `SAVEPOINT` minh họa cách khôi phục một phần transaction để kiểm tra lỗi, không có nghĩa production code luôn nên nuốt lỗi và tiếp tục.

## 6. Staging: giống production ở những thuộc tính quyết định hành vi

Môi trường **staging** là nơi chạy thử bản phát hành trước production. Nó không cần giống production tuyệt đối về số CPU hay hàng terabyte dữ liệu, nhưng phải phản ánh những yếu tố có thể làm thay đổi kết quả:

| Khía cạnh | Nên giống production ở staging đến mức nào? |
| --- | --- |
| PostgreSQL major version | Nên cùng major và kiểm soát minor/patch; hạn chế lệch tính năng hoặc planner |
| Extension | Cùng loại, cùng phiên bản tương thích khi phụ thuộc tính năng |
| Schema và migration | Cùng chuỗi migration; thử migration từ trạng thái gần production |
| Quyền role | Kiểm thử bằng role ứng dụng thực, tránh dùng superuser che lỗi |
| Encoding/collation | Tương thích các quy tắc so sánh, sắp xếp và unique key |
| `search_path` và TimeZone | Được cấu hình/đặt rõ để tránh tên bảng và diễn giải thời gian khác nhau |
| TLS và đường kết nối | Thử các yêu cầu xác thực, proxy, pooling, timeouts và routing |
| Dữ liệu | Đủ dạng và khối lượng đại diện, ẩn danh nếu lấy từ production |
| Migration/DDL lock | Thử ảnh hưởng lên truy vấn đồng thời, không chỉ xem script chạy thành công |
| Backup/restore | Có khả năng diễn tập phù hợp với yêu cầu hệ thống |
| Monitoring | Có log/metric đủ quan sát khác biệt khi phát hành |

Sự khác biệt giữa staging và production phải được **ghi nhận rõ**. Ví dụ staging chỉ có 10.000 dòng trong khi production có 200 triệu dòng thì việc index scan trong staging không chứng minh truy vấn đó đủ nhanh ở production.

### 6.1. Khi nào dùng bản sao dữ liệu production?

Nhu cầu kiểm tra kế hoạch truy vấn hoặc migration trên dữ liệu đại diện là hợp lý, nhưng rủi ro bảo mật cao. Quy trình gợi ý:

1. Có mục đích rõ ràng và được phép sao chép theo chính sách tổ chức.
2. Chỉ lấy các bảng/trường cần thiết, giảm dữ liệu trước khi chuyển nếu có thể.
3. **Ẩn danh hoặc tổng hợp** dữ liệu cá nhân bằng quy tắc được phê duyệt; kiểm tra dữ liệu còn nhận diện được qua các trường kết hợp hay không.
4. Không chuyển credential, token, secret, password hash hoặc dữ liệu thanh toán không cần thiết.
5. Mã hóa dữ liệu khi truyền và lưu; giới hạn người và ứng dụng được truy cập.
6. Định rõ thời hạn lưu, cách xóa và audit truy cập.

Đừng cho rằng `pg_dump` tự làm sạch dữ liệu: nó sao chép logic dữ liệu từ database mà user có quyền đọc. Các lựa chọn `--exclude-table` hoặc lọc một số đối tượng không tự giải quyết quyền riêng tư của những trường còn lại.

### 6.2. Staging không phải nơi chạy các test phá hủy tùy ý

Staging thường là tài nguyên **dùng chung giữa nhiều nhóm**, có các luồng dịch vụ phụ thuộc nhau. Nếu mỗi người tự chạy `DROP SCHEMA ... CASCADE` để reset, người khác có thể mất môi trường kiểm thử.

Một chiến lược phù hợp là:

- Có cửa sổ reset hoặc pipeline tái tạo staging được thông báo.
- Tách dữ liệu test theo tenant hoặc namespace khi ứng dụng hỗ trợ.
- Ghi rõ phiên bản schema, build ứng dụng và tập dữ liệu đang có.
- Có khả năng lấy lại trạng thái trước thay đổi lớn nếu môi trường staging có giá trị.

Staging vẫn là **non-production** về mục tiêu phục vụ, nhưng không đồng nghĩa mọi thao tác đều được phép vô điều kiện.

## 7. Production: mục tiêu là ổn định, bảo mật và khả năng phục hồi

Production chứa dữ liệu và workload mà người dùng thực sự phụ thuộc. Thiết kế và cấu hình phải đáp ứng cam kết nghiệp vụ, không chỉ chạy qua một bộ test.

Các yêu cầu nền tảng thường gồm:

- Hạ tầng và quyền truy cập tách khỏi môi trường học/test.
- Quy trình tạo schema và migration có version, review và cơ chế kiểm soát triển khai.
- Đường kết nối bảo mật: network policy, TLS, xác thực và quản lý secret.
- Role ứng dụng theo **least privilege**; không sử dụng superuser cho request thông thường.
- Backup tự động, retention có kế hoạch và **thử khôi phục** định kỳ.
- Cảnh báo và giám sát disk, CPU, I/O, session, lock, replication (nếu có), WAL và autovacuum.
- Công cụ kiểm soát tải, timeout, giới hạn connection và ứng phó khi hệ thống không sẵn sàng.
- Quy trình phát hành và rollback/forward-fix cùng người chịu trách nhiệm cụ thể.
- Tài liệu RPO/RTO và diễn tập khôi phục hoặc failover phù hợp.

### 7.1. Không dùng cấu hình làm giảm độ bền dữ liệu để “tăng tốc”

PostgreSQL có các cấu hình ảnh hưởng đến việc ghi WAL, flush và đồng bộ dữ liệu xuống storage. Trong production thông thường, **không vô hiệu hóa các cơ chế bảo vệ độ bền** như `fsync` hoặc `full_page_writes` chỉ vì benchmark nhỏ cho kết quả nhanh hơn. Cấu hình `synchronous_commit` cũng cần hiểu rõ đánh đổi giữa độ trễ và khả năng mất transaction gần thời điểm sự cố.

Có thể xem một số giá trị:

~~~sql
SHOW fsync;
SHOW full_page_writes;
SHOW synchronous_commit;
SHOW wal_level;
SHOW max_connections;
~~~

Mặc định và giá trị đang chạy phải được đánh giá cùng mục tiêu an toàn dữ liệu, loại storage, topology standby và quy trình backup. Không sao chép một bộ tham số tối ưu hóa từ blog hoặc local sang production mà chưa đo và kiểm thử.

### 7.2. Connection pool và sự khác nhau về tải

Trong local, một người học có thể mở hai kết nối rồi làm việc. Production có nhiều instance ứng dụng, mỗi instance mở pool:

~~~text
Ứng dụng A: 20 connections
Ứng dụng B: 20 connections
Ứng dụng C: 20 connections
--------------------------------
Tổng tiềm năng: 60 connections
~~~

Nếu mỗi ứng dụng lại có nhiều replica/container, tổng kết nối tăng nhanh. Cấu hình pool phải xét `max_connections`, bộ nhớ theo session, dạng truy vấn, transaction lâu, proxy như PgBouncer (nếu dùng) và tài nguyên thực tế; không phải “pool càng to càng nhanh”.

Trong môi trường production, cần theo dõi **active/idle/idle in transaction** và thời gian chờ lấy connection. Session `idle in transaction` kéo dài có thể giữ snapshot/lock, làm khó autovacuum và tạo bloat.

### 7.3. Quản lý thời gian và múi giờ

Một lỗi dễ bỏ sót khi phát hành là local và production có `TimeZone` khác nhau. PostgreSQL hỗ trợ `TIMESTAMP WITHOUT TIME ZONE` và `TIMESTAMPTZ` với ngữ nghĩa khác nhau. Với mốc sự kiện, nên có quy ước nhất quán, thường dùng `TIMESTAMPTZ` và chuẩn hóa cách hiển thị trong ứng dụng.

Kiểm tra:

~~~sql
SHOW TimeZone;

SELECT
    now() AS current_instant,
    now() AT TIME ZONE 'UTC' AS utc_wall_time;
~~~

`TIMESTAMPTZ` đại diện mốc thời gian và được hiển thị theo múi giờ của session; nó không lưu kèm múi giờ gốc mà user đã chọn. Khi thử dữ liệu gần thời điểm đổi múi giờ hoặc chuyển ngày, cần xác định rõ kỳ vọng nghiệp vụ thay vì dựa vào giờ local của laptop.

## 8. Tách cấu hình kết nối theo môi trường

Ứng dụng thường có các giá trị theo môi trường:

~~~text
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD / secret reference
DB_SSL_MODE
DB_POOL_SIZE
DB_CONNECT_TIMEOUT
DB_STATEMENT_TIMEOUT
APPLICATION_ENV
~~~

Không nên sửa cứng URL trong source code mỗi lần triển khai. Ưu tiên cấu hình riêng và secret injection được quản lý; không commit file chứa mật khẩu thật vào Git.

Ví dụ minh họa:

| Thuộc tính | Local | Test/CI | Staging | Production |
| --- | --- | --- | --- | --- |
| Host | `127.0.0.1` | Service riêng trong CI | `pg-stg.internal` | `pg-prod.internal` |
| Port | `5541` | `5432` nội bộ | Theo hạ tầng | Theo hạ tầng |
| Database | `learning_db` | `test_<run_id>` | `shop_staging` | `shop` |
| Role | `lab_admin` / `lab_app` | `test_runner` | `shop_app_staging` | `shop_app_prod` |
| Dữ liệu | Giả | Fixture | Đại diện, đã kiểm soát | Thật |
| Secret | Chỉ dùng cho lab | Secret ngắn hạn | Secret tách riêng | Secret production có bảo vệ/rotation |

Các host trên chỉ là tên ví dụ. **Tên database hoặc biến `APPLICATION_ENV=production` không phải bằng chứng đủ để kết luận đang kết nối đúng production**. Việc nhận diện phải dựa vào connection profile được quản lý, danh tính server, hạ tầng, quyền và bước kiểm chứng ở deployment pipeline.

### 8.1. Kiểm tra context trước khi chạy migration hoặc tác vụ nguy hiểm

Một bộ lệnh read-only để người vận hành xác nhận:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    session_user AS authenticated_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version,
    current_setting('application_name') AS application_name;
~~~

`inet_server_addr()` có thể trả `NULL` nếu kết nối qua Unix-domain socket; trong các môi trường có proxy, địa chỉ trả về có thể chưa đủ phân biệt hạ tầng. Nên kết hợp với danh tính deployment, profile đã xác thực và policy access thay vì dựa vào một dòng thông tin.

Trong `psql`, có thể bật dừng khi gặp lỗi cho script triển khai:

~~~bash
psql \
  -h pg-stg.internal \
  -U migration_user \
  -d shop_staging \
  -v ON_ERROR_STOP=1 \
  -f migration.sql
~~~

Đây là **ví dụ chạy migration có ghi dữ liệu vào staging**; đừng chạy khi `migration.sql` không được review hoặc môi trường chưa được xác nhận. `ON_ERROR_STOP=1` làm psql dừng khi có lỗi SQL, nhưng không tự đảm bảo mọi lệnh trước đó đã rollback; cần cấu trúc transaction phù hợp và phân loại những DDL không thể chạy trong transaction.

### 8.2. Dùng quyền hạn làm hàng rào bảo vệ

Một cơ chế ngăn thao tác nhầm hiệu quả hơn chỉ dựa vào ý thức là **không cấp quyền không cần thiết**:

- CI test role chỉ có thể tạo/sửa/xóa trong database test thuộc job.
- Developer role trên production (nếu được phép kết nối) có thể chỉ đọc metadata hoặc dữ liệu được phê duyệt.
- Application role không có quyền `DROP TABLE` hoặc `ALTER TABLE`.
- Migration role được cấp quyền đặc biệt qua pipeline có phê duyệt và lịch sử audit.
- Account dùng để backup có quyền đủ cho backup, không dùng như superuser cho mọi tác vụ.

Trong PostgreSQL, có thể thiết kế role nhóm sở hữu object và các role đăng nhập nhận quyền thông qua `GRANT`. Cần lưu ý **role ownership**, quyền `CREATE` trên schema, quyền trên sequence và quyền mặc định của object mới. Chỉ cấp `SELECT` trên table chưa chắc đủ cho mọi tác vụ có `INSERT ... RETURNING` hoặc thao tác sequence.

### 8.3. Không đặt mọi môi trường trong cùng một credential

Dùng cùng mật khẩu/role cho test, staging và production làm tăng nguy cơ **lateral access**: credential rò rỉ từ runner hoặc laptop có thể mở đường truy cập production. Hãy phân tách:

1. Credential và vòng đời secret.
2. ACL/firewall/network path.
3. Quyền role và ownership của database.
4. Cơ chế log và giám sát truy cập.
5. Nhóm người/ứng dụng được phép thực thi thao tác ghi hoặc quản trị.

Các ranh giới này giúp một lỗi ở môi trường học/test không tự lan sang dữ liệu thật.

## 9. Migration: cùng một lược đồ qua nhiều môi trường

Mục tiêu của migration là để cấu trúc database có thể **tái lập và nâng cấp được**, thay vì mọi người chỉnh bằng tay.

Ví dụ hai phiên bản:

~~~sql
-- V001__create_products.sql
CREATE TABLE app.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL CHECK (price > 0)
);
~~~

~~~sql
-- V002__add_active_flag.sql
ALTER TABLE app.products
ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
~~~

Các ví dụ này **giả định schema `app` đã được tạo** bằng một migration trước đó hoặc do database owner chuẩn bị. Đây là cách minh họa quản lý version; không phải file SQL tự chạy được trên schema chưa tồn tại nếu bỏ qua điều kiện tiên quyết.

Lộ trình:

~~~text
Commit migration trong Git
        |
        v
Chạy trên database test mới + test tự động
        |
        v
Chạy trên staging có dữ liệu đại diện
        |
        v
Review kết quả, thời gian, lock, rollback plan
        |
        v
Triển khai trên production qua pipeline có quyền phù hợp
        |
        v
Quan sát ứng dụng và database sau triển khai
~~~

### 9.1. Không phải mọi ALTER TABLE đều rẻ

Một migration chạy trong vài mili giây trên bảng 50 dòng có thể chờ lock hoặc yêu cầu cập nhật lượng dữ liệu lớn trên bảng production. PostgreSQL có nhiều DDL hỗ trợ transaction, nhưng vẫn cần hiểu mức khóa và chi phí riêng:

- Thêm cột có thể rẻ trong một số trường hợp, nhưng thay kiểu cột hoặc cập nhật dữ liệu lớn có thể phải rewrite.
- Tạo index thông thường có thể ảnh hưởng thao tác ghi; `CREATE INDEX CONCURRENTLY` cho phép tiếp tục nhiều thao tác ghi nhưng có các điều kiện và giới hạn riêng.
- `CREATE INDEX CONCURRENTLY` không được chạy bên trong transaction block tường minh.
- Kiểm tra khóa ngoại/ràng buộc trên bảng lớn có thể tốn thời gian; có thể có chiến lược `NOT VALID` rồi `VALIDATE CONSTRAINT` khi phù hợp.
- Cần đánh giá `lock_timeout`, `statement_timeout` và cơ chế retry của migration, tránh giữ khóa quá lâu.

Ví dụ SQL dành cho một bảng **đã tồn tại và được xác nhận trên staging**:

~~~sql
CREATE INDEX CONCURRENTLY idx_products_active
ON app.products (is_active);
~~~

Không có đảm bảo index đơn cột trên boolean `is_active` sẽ mang lại lợi ích với mọi phân bố dữ liệu; ví dụ nhằm minh họa cú pháp DDL có yêu cầu vận hành đặc biệt, không phải khuyến nghị tối ưu chỉ mục cho bảng thật.

### 9.2. Triển khai thay đổi không tương thích

Thay vì xóa hoặc đổi tên cột đang được ứng dụng cũ dùng trong một lần phát hành, có thể chọn chiến lược:

1. **Expand:** thêm cấu trúc mới mà code cũ vẫn chạy được.
2. **Migrate/backfill:** chuyển dữ liệu dần theo batch có giới hạn.
3. **Switch:** triển khai ứng dụng đọc/ghi bằng cấu trúc mới.
4. **Contract:** sau khi chắc chắn không còn consumer cũ, mới bỏ cấu trúc cũ.

Chuỗi này đặc biệt quan trọng khi staging và production có nhiều instance ứng dụng chạy không đồng thời đổi version. Migration “chạy SQL thành công” chưa chứng minh ứng dụng cũ/mới cùng hoạt động an toàn trong thời gian chuyển tiếp.

## 10. Backup và khôi phục: test, staging, production khác nhau thế nào?

### 10.1. Mục tiêu backup phải xuất phát từ giá trị dữ liệu

Ở local, mất một database seed tự tạo có thể chỉ mất vài phút dựng lại. Ở production, mất dữ liệu đơn hàng mới nhất có thể là sự cố kinh doanh lớn. Hai chỉ tiêu cần thống nhất:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất tính theo thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa cần để khôi phục dịch vụ.

Ví dụ “RPO 15 phút, RTO 2 giờ” chỉ là yêu cầu minh họa. Không thể bảo đảm các chỉ tiêu bằng việc “có một file dump hôm qua”; cơ chế backup/WAL, lưu trữ, nhân lực và tốc độ restore phải đáp ứng.

### 10.2. pg_dump/pg_restore cho database nhỏ và thử logic

Một bản backup logic ở định dạng custom:

~~~bash
pg_dump \
  -h 127.0.0.1 -p 5541 -U lab_admin \
  -d learning_db \
  -F c \
  -f learning_db.dump
~~~

Tạo database **khôi phục riêng** trên môi trường lab, sau đó restore:

~~~bash
createdb \
  -h 127.0.0.1 -p 5541 -U lab_admin \
  learning_restore

pg_restore \
  -h 127.0.0.1 -p 5541 -U lab_admin \
  -d learning_restore \
  --no-owner --no-privileges \
  --exit-on-error \
  learning_db.dump
~~~

Đây là **quy trình thử khôi phục**, không phải lệnh dùng để ghi đè production. Database `learning_restore` cần tồn tại dưới dạng trống, người dùng phải có quyền tạo database, và nội dung dump/extension/role cần tương thích với môi trường restore.

`pg_dump` sao lưu logic một database; nó không tự bao gồm mọi đối tượng toàn cục của cluster như role, toàn bộ file cấu hình hay lịch sử WAL. Với dữ liệu thật, phải có kế hoạch phù hợp cho các thành phần bổ sung này.

### 10.3. Production có thể cần base backup và WAL archive

Với yêu cầu **point-in-time recovery (PITR)**, PostgreSQL có thể sử dụng base backup và chuỗi WAL đã lưu trữ đầy đủ để replay tới thời điểm mong muốn. Điều này đòi hỏi cấu hình, dung lượng lưu trữ, mã hóa, monitoring và thử restore riêng.

~~~mermaid
flowchart LR
    A["Base backup ở T0"] --> B["WAL archive T0→T1"]
    B --> C["WAL archive T1→T2"]
    C --> D["Khôi phục base backup + replay WAL"]
    D --> E["Trạng thái tại thời điểm mục tiêu"]
~~~

**Replication không thay thế backup.** Một thao tác `DELETE` nhầm hoặc một migration sửa sai dữ liệu trên primary có thể được gửi sang standby rất nhanh. Standby giúp sẵn sàng và có thể hỗ trợ một số yêu cầu đọc, nhưng không tạo bản lịch sử bất biến để phục hồi mọi lỗi logic.

Ở staging, diễn tập restore từ backup đã được xử lý an toàn là một cách kiểm tra cả quy trình hạ tầng và ứng dụng. Mọi dữ liệu thật đưa vào môi trường không phải production vẫn phải qua chính sách bảo vệ dữ liệu.

### 10.4. Tiêu chí backup theo từng môi trường

| Môi trường | Tiêu chí thực tế |
| --- | --- |
| Lab | Dữ liệu seed có thể tái tạo; nếu có bài tập giá trị thì tạo backup tùy nhu cầu |
| Test/CI | Dữ liệu được dựng lại; log và artifact lỗi có thời hạn lưu phù hợp |
| Staging | Có snapshot/restore cho diễn tập quan trọng; không giữ dữ liệu nhạy cảm không cần thiết |
| Production | Chính sách backup + WAL/PITR tùy RPO, retention, lưu trữ ngoài failure domain, kiểm thử restore và audit |

## 11. Quan sát PostgreSQL và độ sâu kiểm thử theo môi trường

Mỗi môi trường cần quan sát khác nhau:

- **Local:** xem log server, lỗi `psql` và kết quả truy vấn.
- **CI:** thu log startup, migration, test và container khi job thất bại.
- **Staging:** bật metric/tracing đủ để so sánh với production; thử alert và hành vi khi thiếu kết nối.
- **Production:** giám sát liên tục theo SLO, có ngưỡng cảnh báo, on-call và quy trình xử lý sự cố.

Một số truy vấn đọc trạng thái:

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks,
    blks_read,
    blks_hit
FROM pg_stat_database
WHERE datname = current_database();
~~~

Và những session có transaction đang mở:

~~~sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Các bộ đếm ở `pg_stat_database` là số tích lũy theo thống kê, không phải số sự kiện trong một giây. `pg_stat_activity` cũng có giới hạn nhìn thấy một số chi tiết theo role; quyền quan sát cần được cấp theo chính sách bảo mật, không mặc định cho mọi tài khoản.

### 11.1. Môi trường test cần kiểm thử những lỗi mà local dễ bỏ qua

Ví dụ:

- Hai request cùng cập nhật một bản ghi: phát sinh deadlock, lost update hoặc serialization failure ra sao?
- Một transaction có câu lệnh bị `23505` có rollback toàn bộ hay vẫn cố commit?
- Ứng dụng làm gì khi connection timeout ngay lúc `COMMIT` và không biết transaction đã thành công chưa?
- Migration có giữ khóa quá lâu khi đang có truy vấn ghi đồng thời không?
- Role app có thực sự bị từ chối khi thử `DROP TABLE` hoặc đọc schema bị cấm không?
- Backup phục hồi lại được ràng buộc, sequence, extension và dữ liệu cần thiết không?

Đây không phải những điều cần thử một cách tùy tiện trên production. Cần mô phỏng có kiểm soát trên test/staging và dùng kết quả đó để chuẩn bị runbook cho production.

### 11.2. Khác biệt về hiệu năng do dữ liệu

Một câu lệnh:

~~~sql
EXPLAIN
SELECT *
FROM app.products
WHERE is_active = TRUE;
~~~

có thể dùng `Seq Scan` trên bảng vài chục dòng. Điều đó có thể là quyết định tốt của planner. Ở bảng vài chục triệu dòng, kế hoạch còn phụ thuộc phân bố `is_active`, index, số cột cần đọc và thống kê.

Trong môi trường test/staging dùng dữ liệu đại diện:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, price
FROM app.products
WHERE is_active = TRUE;
~~~

`EXPLAIN (ANALYZE, BUFFERS)` **thực thi câu SELECT** để đo thời gian và page/buffer activity. Nó có thể gây tải nặng nếu bảng lớn. Với câu DML, `EXPLAIN ANALYZE` cũng có thể thực sự thay đổi dữ liệu; vì vậy phải xác định mức rủi ro trước khi đo trên bất kỳ môi trường nào.

Nếu cần đánh giá tải production, có thể dùng số liệu truy vấn thực từ monitoring hoặc bản sao dữ liệu được phép xử lý trong môi trường hiệu năng riêng, không mặc định chạy các thử nghiệm phá tải trực tiếp trên production.

## 12. Ngăn “nhầm môi trường” bằng nhiều lớp bảo vệ

Không có một câu SQL thần kỳ khiến production tuyệt đối không bị thao tác nhầm. Nên sử dụng **defense in depth**:

### 12.1. Lớp nhận diện

- Đặt tên connection profile khác nhau và hiển thị rõ môi trường trong công cụ SQL.
- Phân biệt endpoint/network thật, không chỉ tên `DB_NAME`.
- Trước thao tác quan trọng, đọc `current_database()`, `current_user` và thông tin hạ tầng.
- Gắn application_name riêng cho nguồn kết nối để hỗ trợ phân tích log/metric.

Ví dụ ở client:

~~~sql
SET application_name = 'postgres-learning-lesson-41';

SELECT
    current_database(),
    current_user,
    current_setting('application_name');
~~~

Giá trị `application_name` phục vụ quan sát, **không phải cơ chế xác thực danh tính**: client có quyền phù hợp có thể tự đặt chuỗi này.

### 12.2. Lớp giới hạn quyền

- Test user không có quyền trên production.
- Application user chỉ có DML trên đối tượng cần thiết.
- Migration user không phải credential được nhúng trong image ứng dụng để chạy suốt ngày.
- Quyền `DROP`/`ALTER` gắn với ownership và vai trò quản trị riêng.
- Hành động có ảnh hưởng lớn cần phê duyệt/quy trình được ghi lại.

### 12.3. Lớp hạ tầng

- Local chỉ bind cổng loopback hoặc private network.
- CI dùng network/service tách biệt và database riêng theo job.
- Staging và production tách network policy, tài khoản cloud, namespace hoặc deployment boundary tùy mức rủi ro.
- Credential staging không truy cập được production.
- Dùng TLS và xác thực server khi kết nối qua các mạng yêu cầu bảo mật.

### 12.4. Lớp quy trình

- Migration được code review và chạy thử.
- Script phá hủy dữ liệu chỉ chạy trong môi trường dành cho mục đích đó, có xác minh tài nguyên đích.
- Backup/restore test được thực hiện trước các thay đổi lớn theo yêu cầu.
- Có khả năng dừng rollout nếu metric suy giảm và có phương án fix-forward/rollback phù hợp.
- Mọi lần chạy từ CI/CD có log danh tính job, version migration, tài khoản và môi trường đích.

Một **bảng kiểm trước thao tác có rủi ro**:

| Câu hỏi | Nếu chưa trả lời được |
| --- | --- |
| Tôi đang ở server/instance nào và database nào? | Dừng lại để xác nhận |
| Tài khoản hiện tại có quyền gì? | Kiểm tra bằng kết nối và chính sách quyền |
| Dữ liệu ở môi trường này có thể bị xóa không? | Không dùng lệnh reset khi chưa có phép |
| Script đã được thử trên database riêng chưa? | Chạy thử ở test/staging trước |
| Có backup/restore phù hợp nếu thao tác sai không? | Không thực hiện thay đổi lớn trên production |
| Có người chịu trách nhiệm theo dõi sau thay đổi không? | Bổ sung ownership và giám sát |

## 13. Kịch bản tình huống: chọn đúng môi trường

### Tình huống A — Học thử ràng buộc khóa ngoại

Bạn muốn cố tình chèn một đơn hàng tham chiếu khách hàng không tồn tại để xem lỗi `23503`. Môi trường hợp lý là **lab hoặc test**; không phải production. Trong lab, có thể dùng schema dành riêng, tạo dữ liệu giả và rollback sau khi thử.

### Tình huống B — Kiểm tra migration thêm cột trên bảng lớn

Bạn cần xem migration có làm khóa bảng lâu, tương thích hai phiên bản ứng dụng và hoàn thành trong thời gian cho phép không. Bắt đầu bằng **integration test** trên database khởi tạo sạch để kiểm tra cú pháp, sau đó **staging** với lượng dữ liệu và tải đại diện. Production chỉ nhận migration qua quy trình được duyệt.

### Tình huống C — Thử lỗi mất kết nối trong lúc ghi

Bạn muốn biết application rollback, retry và idempotency ra sao khi database tạm thời không sẵn sàng. Dùng test environment có khả năng chủ động ngắt mạng, restart container hoặc mô phỏng fault; không tự restart primary production để thử.

### Tình huống D — Điều tra truy vấn production chậm

Dữ liệu thật đang khiến một truy vấn mất vài giây. Dùng metric/slow query và `EXPLAIN` để hiểu hiện trạng; nếu cần `EXPLAIN ANALYZE` hoặc thử index trên nhiều dữ liệu, cân nhắc staging/performance environment có dữ liệu đại diện và kế hoạch thử nghiệm an toàn. Không suy ra kế hoạch production từ local vài dòng.

### Tình huống E — Diễn tập phục hồi backup

Một bản backup production cần được kiểm chứng. Phục hồi vào **môi trường tách biệt**, có quyền và dung lượng phù hợp, dữ liệu được bảo vệ. Không restore chồng lên database production hiện có để “xem file có đọc được không”.

### Tình huống F — Thêm một extension PostgreSQL

Một thư viện ứng dụng cần extension, ví dụ `pg_trgm`. Trước hết xác nhận extension có sẵn trên phiên bản/server và quyền cài đặt; cài thử trên local/test, kiểm tra migration và compatibility trên staging rồi mới lên production.

~~~sql
-- Ví dụ thực hành trên database mà bạn có quyền quản lý.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pg_trgm';
~~~

Đừng giả định mọi managed service hỗ trợ mọi extension hoặc cho ứng dụng cài extension bằng role thông thường. Quy trình phê duyệt extension còn liên quan bảo mật và khả năng nâng cấp PostgreSQL.

## 14. Sai lầm phổ biến khi tổ chức môi trường PostgreSQL

| Sai lầm | Vì sao rủi ro? | Cách cải thiện |
| --- | --- | --- |
| Dùng production để thử `TRUNCATE`/`DROP` | Phá dữ liệu và làm ngừng ứng dụng | Lab/CI database riêng, least privilege |
| Dùng một user `postgres` cho cả app và test | Quyền quá rộng, khó audit | Role riêng theo môi trường và nhiệm vụ |
| Chỉ tách `shop_dev` và `shop_prod` trong một instance rồi coi là độc lập | Vẫn chia sẻ resources và failure domain | Tách deployment/network/secret khi cần bảo vệ production |
| Dùng `postgres:latest` trong CI | Major version có thể đổi khi kéo image mới | Pin major/patch/digest theo policy |
| Dùng dữ liệu production thật trên laptop | Rủi ro riêng tư, lộ secret | Seed giả hoặc dữ liệu được xử lý/ẩn danh |
| Test luôn phụ thuộc database dùng chung | Test flaky, ảnh hưởng nhau, không tái lập | Database/container tạm theo job/suite |
| Mọi test chỉ rollback trên một connection | Có thể che lỗi commit, concurrency và external effect | Có test commit thực, multi-connection và idempotency |
| Staging khác production về schema/extension | Lỗi chỉ xuất hiện lúc go-live | Cùng migration, quản lý khác biệt cấu hình |
| Đổi cấu trúc thủ công trên production | Môi trường drift, khó audit/khôi phục | Migration có version và review |
| Bật `fsync=off` cho production để tăng tốc | Có thể làm tăng nguy cơ mất/hỏng dữ liệu khi crash | Giữ chính sách durability đã đánh giá |
| Có pg_dump nhưng chưa thử restore | Không biết backup có đủ và dùng được không | Restore định kỳ vào môi trường biệt lập |
| Có standby nên bỏ backup | Lỗi logic được sao chép theo | Backup + PITR theo RPO/RTO |
| Pool size tăng vô hạn | Cạn connection, memory và tranh chấp tăng | Đo tải, giới hạn pool và timeout |
| Đồng nhất tên môi trường với xác thực | Đặt tên sai vẫn có thể truy cập DB thật | Xác thực bằng network, credential, danh tính instance |
| Thực hiện lệnh dọn lab khi chưa biết volume nào | Có thể xóa dữ liệu không thuộc lab | Xác minh rõ tên container/volume và dữ liệu sở hữu |

## 15. Bài tập thực hành và tiêu chí đánh giá

### Bài tập 1 — Nhận diện bốn môi trường

Cho bốn mục tiêu:

1. Chạy `INSERT` với dữ liệu sai để quan sát mã lỗi.
2. Kiểm thử lại tất cả migration trên database trống mỗi lần push code.
3. Diễn tập nâng PostgreSQL và đo tác động khóa DDL trước phát hành.
4. Phục vụ đơn hàng thật với backup, alert và phân quyền nghiêm ngặt.

Hãy chọn lần lượt **local/lab**, **test/CI**, **staging**, **production**, và giải thích vì sao môi trường còn lại không phải lựa chọn phù hợp nhất cho mục tiêu đó.

### Bài tập 2 — Phân biệt mức cách ly

Giả sử PostgreSQL instance chứa hai database `shop_dev` và `shop_prod`. Hãy trả lời:

- Hai database có dùng chung CPU và disk của instance không?
- Một tài khoản superuser có thể thao tác cả hai không?
- Nếu disk chứa WAL đầy, có thể chỉ `shop_dev` bị ảnh hưởng hay không?
- Cần thêm những ranh giới nào nếu muốn bảo vệ production khỏi lỗi trên máy dev?

**Gợi ý:** database và schema là ranh giới tên/quyền ở tầng SQL, không hoàn toàn cách ly failure domain và tài nguyên của instance.

### Bài tập 3 — Dựng một lab an toàn

Chạy PostgreSQL trong container dùng một port host chỉ bind `127.0.0.1`, tạo database `learning_db`, schema `sandbox` và bảng `sandbox.notes`. Kết nối bằng `psql`, chạy `SELECT current_database(), current_user` và `\conninfo` để xác minh. Khi xong, dừng container nhưng giữ volume; giải thích vì sao dữ liệu vẫn còn khi start lại.

### Bài tập 4 — Kiểm thử lỗi trong transaction

Tạo bảng tạm có `UNIQUE`, chèn mã `SKU-001` rồi dùng savepoint thử chèn trùng. Quan sát SQLSTATE `23505` và dùng `ROLLBACK TO SAVEPOINT` để tiếp tục truy vấn. Giải thích điều gì xảy ra nếu không rollback sau khi statement thất bại.

### Bài tập 5 — So sánh phiên bản và quyền

Lập bảng ghi `server_version`, extension, `TimeZone`, `search_path` và role ở local/staging/production (chỉ lấy metadata được phép). Chỉ ra khác biệt nào có thể ảnh hưởng:

- Kiểu/cú pháp migration.
- Kết quả so sánh chuỗi, mã duy nhất và sắp xếp.
- Định dạng thời điểm khi đọc.
- Quyền `CREATE INDEX`, `ALTER TABLE` và quyền DML của ứng dụng.

### Bài tập 6 — Xây kế hoạch test dữ liệu gần production

Một truy vấn chỉ chậm ở bảng 10 triệu dòng. Đề xuất cách tạo dữ liệu có quy mô và phân bố đại diện **không dùng thông tin nhạy cảm không được phép**, điều kiện đo `EXPLAIN (ANALYZE, BUFFERS)` và các metric cần so trước/sau một index.

### Bài tập 7 — Thử backup và restore

Tạo dump từ `learning_db` bằng `pg_dump -F c`, phục hồi vào `learning_restore`, kiểm tra bảng `sandbox.notes` và số dòng. Giải thích vì sao việc nhìn thấy file `.dump` chưa đủ chứng minh có thể khôi phục toàn bộ hệ thống production.

### Bài tập 8 — Review một tình huống triển khai

Một lập trình viên muốn gửi trực tiếp script:

~~~sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
~~~

vào connection profile có tên “Test” nhưng URL thật trỏ đến production. Hãy chỉ ra các hàng rào cần có để sự cố không xảy ra: profile/hạ tầng, mạng, role, quyền, confirmation, workflow migration, backup và audit. **Không chạy hai lệnh trên**; đây là tình huống phân tích rủi ro.

## 16. Checklist trước khi chuyển từ học tập sang vận hành thật

| Câu hỏi | Khi nào coi là đạt? |
| --- | --- |
| Có biết chính xác server/database hiện tại? | Connection được xác minh bằng nhiều nguồn, không chỉ tên profile |
| Schema có thể tái tạo? | Migration từ đầu trên database trống thành công |
| Test có độc lập và chạy lại được? | Có fixture và cleanup tự động; test không chia sẻ database production |
| Dữ liệu ngoài production có an toàn? | Không chứa secret/dữ liệu cá nhân không được phép; có kiểm soát truy cập |
| Cấu hình và phiên bản có nhất quán? | Khác biệt được kiểm soát, test compatibility trên staging |
| Ứng dụng có xử lý lỗi giao dịch? | Rollback/commit rõ ràng, retry/idempotency phù hợp |
| Quyền truy cập có giới hạn? | Role app/test/migration/backup riêng, không lạm dụng superuser |
| Migration được kiểm chứng? | Có test, staging và kế hoạch theo dõi/khôi phục |
| Có backup và thử restore? | Có bằng chứng khôi phục vào môi trường riêng thành công |
| Có kiểm soát tải và cảnh báo? | Connection, disk, locks, WAL, backup, autovacuum được theo dõi |
| Có người vận hành chịu trách nhiệm? | Runbook, lịch trực và cơ chế xử lý sự cố được thống nhất |
| Có mục tiêu phục hồi? | RPO/RTO gắn với quy trình backup/PITR/failover được kiểm thử |

## 17. Kết luận

**Môi trường học tập** ưu tiên khám phá, thực hành và khả năng tái tạo; **môi trường test** ưu tiên kết quả tự động, dữ liệu xác định và cô lập; **staging** ưu tiên mô phỏng đặc tính quan trọng của production trước phát hành; **production** ưu tiên bảo vệ dữ liệu, độ sẵn sàng và phục hồi sau sự cố.

Khác biệt không chỉ ở số dòng hay tên database. Điều quyết định là **ranh giới hạ tầng, quyền và secret, dữ liệu được phép sử dụng, cấu hình, migration, sao lưu, giám sát và trách nhiệm vận hành**. Một lệnh SQL có thể hoàn toàn đúng về cú pháp nhưng sai nghiêm trọng khi chạy ở môi trường không phù hợp.

Trước khi thực hiện bất cứ thao tác ghi/xóa/đổi schema nào, hãy xác nhận **mình đang kết nối tới đâu, đang dùng quyền nào, dữ liệu có giá trị gì và cách khôi phục nếu thất bại**. Đó là thói quen cốt lõi để học PostgreSQL một cách an toàn và phát triển dần thành một hệ thống có thể vận hành đáng tin cậy.
