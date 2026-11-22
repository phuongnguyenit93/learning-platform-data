# REMAP_SCHEMA, REMAP_TABLESPACE và xử lý đối tượng đã tồn tại

Oracle Data Pump Import (impdp) có thể đưa schema, bảng và metadata từ database nguồn sang database đích. Khi chuyển môi trường, đổi tên schema hoặc tổ chức lại tablespace, dump file thường vẫn mang tên schema và tablespace ban đầu. Data Pump cung cấp các tham số remap để chuyển quyền sở hữu và vị trí lưu segment trong lúc import.

Ba tham số cần hiểu rõ là:

- **REMAP_SCHEMA**: chuyển object thuộc schema nguồn sang schema đích trong quá trình import.
- **REMAP_TABLESPACE**: chuyển object segment từ tablespace nguồn sang tablespace đích.
- **TABLE_EXISTS_ACTION**: quyết định cách nạp dữ liệu khi bảng đích đã tồn tại.

Các tham số này giải quyết những vấn đề khác nhau. REMAP_SCHEMA không tự động sửa mọi chuỗi tên schema nằm trong mã nguồn PL/SQL; REMAP_TABLESPACE không tự tạo dung lượng lưu trữ hoặc thay đổi mọi cấu hình mặc định của user; TABLE_EXISTS_ACTION chỉ điều khiển cách xử lý bảng đã tồn tại khi nạp dữ liệu. Muốn import an toàn, cần chuẩn bị user, tablespace, quyền, cấu trúc bảng và dữ liệu hiện có trước khi chạy.

## 1. Data Pump Import và bối cảnh remap

Data Pump là công cụ xuất/nhập dữ liệu và metadata của Oracle Database. Export được thực hiện bằng expdp; import bằng impdp. Dump file có thể chứa metadata, dữ liệu hoặc cả hai tùy cách export.

Một quy trình chuyển schema thường có dạng:

1. Export schema từ database nguồn thành dump file.
2. Chuyển dump file tới nơi mà Oracle DIRECTORY ở database đích có thể truy cập.
3. Chuẩn bị schema đích, tablespace, quota và quyền.
4. Chạy impdp với các tham số remap.
5. Kiểm tra log, object, dữ liệu, grants, synonym, job và dependency.
6. Kiểm thử ứng dụng trước khi chuyển traffic.

Ví dụ: database nguồn có schema SALES nằm trong tablespace SALES_DATA và SALES_INDEX. Môi trường kiểm thử cần schema SALES_TEST, dữ liệu ở APP_DATA và index ở APP_INDEX.

    Database nguồn                         Database đích
    +-------------------+                  +-------------------+
    | Schema SALES      |                  | Schema SALES_TEST |
    |                   |                  |                   |
    | SALES_DATA        |   Data Pump      | APP_DATA          |
    | SALES_INDEX       |  ------------>   | APP_INDEX         |
    |                   |                  |                   |
    +-------------------+                  +-------------------+
            |                                      ^
            | expdp                                 | impdp
            v                                      |
       dump file  ---------------------------------+

Trong ví dụ này:

- REMAP_SCHEMA=SALES:SALES_TEST thay đổi owner của object được import.
- REMAP_TABLESPACE=SALES_DATA:APP_DATA chuyển segment thuộc tablespace SALES_DATA sang APP_DATA.
- REMAP_TABLESPACE=SALES_INDEX:APP_INDEX chuyển segment thuộc SALES_INDEX sang APP_INDEX.
- TABLE_EXISTS_ACTION quyết định cách xử lý từng bảng nếu bảng tương ứng đã có ở đích.

Remap được thực hiện trong lúc import. Dump file nguồn không bị chỉnh sửa.

## 2. REMAP_SCHEMA: chuyển owner của object

Cú pháp:

    REMAP_SCHEMA=source_schema:target_schema

Ví dụ:

    REMAP_SCHEMA=SALES:SALES_TEST

Khi import, Data Pump chuyển các object thuộc schema SALES trong dump sang owner SALES_TEST. Có thể dùng tham số này để:

- Tạo bản sao schema phục vụ kiểm thử.
- Đổi tên schema khi chuyển ứng dụng sang database mới.
- Nhập dữ liệu từ nhiều schema nguồn vào các schema đích đã quy hoạch.
- Giữ database nguồn và database đích dùng tên owner khác nhau.

### 2.1. Import một schema sang schema có tên khác

Ví dụ export:

    expdp system@SOURCE
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_export.log
      SCHEMAS=SALES
      PARALLEL=4
      FILESIZE=10G

Lệnh trên được trình bày theo dạng nhiều dòng để dễ đọc. Khi chạy trong shell, có thể đặt các tham số trên một dòng hoặc dùng parameter file.

Import:

    impdp system@TARGET
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_to_test.log
      SCHEMAS=SALES
      REMAP_SCHEMA=SALES:SALES_TEST

Kết quả là các object được chọn từ SALES được tạo dưới owner SALES_TEST, theo phạm vi metadata có trong dump và các filter của import.

Nếu có nhiều schema cần đổi tên, có thể khai báo nhiều cặp REMAP_SCHEMA trong cùng job. Hãy xác định rõ nguồn và đích cho từng cặp; không dùng một mapping mơ hồ cho các schema có cùng tên ở những database khác nhau.

### 2.2. Chuẩn bị schema đích

Trong vận hành, cách dễ kiểm soát nhất là tạo trước user đích với default tablespace, temporary tablespace và quota phù hợp:

    CREATE USER sales_test
      IDENTIFIED BY "replace-with-managed-secret"
      DEFAULT TABLESPACE app_data
      TEMPORARY TABLESPACE temp
      QUOTA 5G ON app_data
      QUOTA 2G ON app_index;

    GRANT CREATE SESSION TO sales_test;

Đây là ví dụ minh họa. User import cần các quyền bổ sung phù hợp với object sẽ được tạo và cách thức chạy Data Pump. Không cấp quyền rộng hơn yêu cầu thực tế. Nếu dump chứa metadata tạo user và job được chạy với quyền phù hợp, Data Pump có thể xử lý user metadata theo nội dung dump; tuy nhiên, việc chuẩn bị trước schema đích giúp DBA kiểm soát password, quota, profile, tablespace và chính sách bảo mật.

Một số điểm phải kiểm tra:

- User đích đã tồn tại hay chưa.
- Default tablespace và temporary tablespace có đúng không.
- Quota có đủ cho table, index, LOB và partition không.
- User có quyền tạo object cần thiết hay import account có quyền thích hợp không.
- Profile, password policy, roles và system privileges có phù hợp không.
- Schema đích có chứa object từ lần import trước hay dữ liệu của ứng dụng khác không.

REMAP_SCHEMA thay đổi owner của object được import. Nó không thay thế việc thiết kế account và quyền đăng nhập cho ứng dụng.

### 2.3. Các tham chiếu schema bên trong object

Không nên xem REMAP_SCHEMA là thao tác tìm và thay mọi chuỗi tên schema trong dump.

Ví dụ, một procedure trong SALES có thể chứa tham chiếu tường minh:

    SELECT *
    FROM COMMON_CONFIG.CURRENCY_RATE;

Khi object được chuyển sang SALES_TEST, tham chiếu tới COMMON_CONFIG vẫn có thể trỏ tới schema COMMON_CONFIG. Đây có thể là hành vi mong muốn nếu schema dùng chung vẫn tồn tại, nhưng cũng có thể làm ứng dụng kiểm thử truy cập nhầm database object hoặc dữ liệu production.

Các vị trí cần rà soát sau khi remap:

- PL/SQL procedure, function, package và trigger có schema qualifier viết cứng.
- View và materialized view tham chiếu object thuộc schema khác.
- Synonym trỏ tới owner hoặc database link cũ.
- Database link, job, scheduler program và credential.
- Dynamic SQL ghép tên schema từ chuỗi.
- Grant, role, ACL và dependency giữa nhiều schema.
- Application configuration, connection string và migration script chứa tên owner cũ.

Có thể tìm tham chiếu schema trong source sau import bằng cách truy vấn data dictionary, ví dụ:

    SELECT owner, name, type, line, text
    FROM dba_source
    WHERE owner = 'SALES_TEST'
      AND UPPER(text) LIKE '%SALES.%'
    ORDER BY name, type, line;

Truy vấn chuỗi trên chỉ là bước dò tìm ban đầu. Nó có thể bỏ sót dynamic SQL được ghép qua nhiều dòng hoặc tạo false positive với tên cột và chuỗi literal. Cần kiểm tra source thực tế và biên dịch lại object.

### 2.4. Nhiều schema và quan hệ phụ thuộc

Nếu schema SALES tham chiếu tới MASTER_DATA, import riêng SALES có thể tạo được object nhưng các dependency bên ngoài vẫn cần tồn tại ở database đích.

    SALES_TEST.ORDERS
           |
           +----> MASTER_DATA.CUSTOMERS
           |
           +----> MASTER_DATA.PRODUCTS
           |
           +----> COMMON_CONFIG.CURRENCY_RATE

Trước khi remap, cần xác định schema nào là dữ liệu riêng của ứng dụng và schema nào là dữ liệu dùng chung. Có thể import các schema phụ thuộc trước, hoặc giữ nguyên owner của schema dùng chung. Tránh remap toàn bộ một cách máy móc khiến nhiều object cùng trỏ vào bản sao không đúng.

## 3. REMAP_TABLESPACE: chuyển vị trí lưu segment

Cú pháp:

    REMAP_TABLESPACE=source_tablespace:target_tablespace

Ví dụ:

    REMAP_TABLESPACE=SALES_DATA:APP_DATA
    REMAP_TABLESPACE=SALES_INDEX:APP_INDEX

Tham số này yêu cầu Data Pump đặt các segment được import từ tablespace nguồn vào tablespace đích tương ứng.

Nó hữu ích khi:

- Chuyển database sang storage layout mới.
- Tách table và index sang các tablespace riêng.
- Đưa dữ liệu production sang tablespace nhỏ hơn cho môi trường test.
- Chuẩn hóa tên tablespace giữa các môi trường.
- Di chuyển schema khỏi tablespace cũ sắp ngừng sử dụng.

### 3.1. Một mapping và nhiều mapping

Một mapping:

    REMAP_TABLESPACE=SALES_DATA:APP_DATA

Nhiều mapping:

    REMAP_TABLESPACE=SALES_DATA:APP_DATA
    REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
    REMAP_TABLESPACE=SALES_LOB:APP_LOB

Trong parameter file có thể khai báo tham số lặp lại theo cú pháp Data Pump. Hãy kiểm tra cách truyền tham số của phiên bản và shell đang sử dụng; parameter file thường dễ đọc và ít lỗi quoting hơn command line dài.

### 3.2. Tạo tablespace đích trước khi import

REMAP_TABLESPACE không phải lệnh cấp phát storage. Tablespace đích cần tồn tại và có datafile hoặc tempfile phù hợp trước khi import tạo segment.

Ví dụ:

    CREATE TABLESPACE app_data
      DATAFILE '/u02/oradata/target/app_data01.dbf'
      SIZE 2G
      AUTOEXTEND ON NEXT 256M MAXSIZE 20G;

    CREATE TABLESPACE app_index
      DATAFILE '/u03/oradata/target/app_index01.dbf'
      SIZE 1G
      AUTOEXTEND ON NEXT 128M MAXSIZE 10G;

Đường dẫn và kích thước chỉ là ví dụ. Với ASM, Oracle Managed Files hoặc cloud storage, cách tạo file có thể khác. DBA phải kiểm tra storage pool, quota, encryption, block size, autoextend và giới hạn vận hành.

### 3.3. Tablespace đích và quota của user

Có tablespace chưa đủ để user tạo segment. Cần cấp quota cho schema đích hoặc dùng chính sách quyền phù hợp:

    ALTER USER sales_test QUOTA 5G ON app_data;
    ALTER USER sales_test QUOTA 2G ON app_index;

Nếu quota không đủ, import có thể gặp lỗi khi tạo table, index hoặc LOB segment. Khi tính quota, không chỉ cộng kích thước table data. Index, LOB, partition, nested table và các segment phụ trợ cũng tiêu thụ dung lượng.

Có thể kiểm tra quota:

    SELECT
        username,
        tablespace_name,
        bytes,
        max_bytes
    FROM dba_ts_quotas
    WHERE username = 'SALES_TEST'
    ORDER BY tablespace_name;

### 3.4. Mapping tablespace không đổi default tablespace của user

REMAP_TABLESPACE tác động đến vị trí segment được import từ tablespace nguồn. Nó không nên được dùng như cách duy nhất để cấu hình default tablespace cho user đích.

Hãy đặt default tablespace riêng:

    ALTER USER sales_test DEFAULT TABLESPACE app_data;

Sau import, kiểm tra object nào vẫn nằm ở tablespace ngoài dự kiến. Một số object có thể được tạo theo default tablespace hoặc chịu ảnh hưởng của metadata và transform được sử dụng. Đừng giả định một mapping đã bao phủ mọi object và mọi cấu hình của user.

### 3.5. Table, index, LOB và partition

Một table có thể có nhiều segment: table segment, index segment, LOB segment và các partition/subpartition. Một số segment có thể nằm ở tablespace khác với table chính.

Ví dụ:

    SALES.ORDERS
      +-- Table partitions       -> SALES_DATA
      +-- Primary key index     -> SALES_INDEX
      +-- ORDER_DOCUMENT LOB    -> SALES_LOB

Nếu chỉ remap SALES_DATA sang APP_DATA, index hoặc LOB vẫn có thể được tạo theo mapping hoặc metadata khác. Hãy liệt kê các tablespace thực sự chứa object nguồn và lập mapping tương ứng.

Có thể kiểm tra segment của schema nguồn:

    SELECT
        segment_type,
        tablespace_name,
        COUNT(*) AS segment_count,
        ROUND(SUM(bytes) / 1024 / 1024) AS size_mb
    FROM dba_segments
    WHERE owner = 'SALES'
    GROUP BY segment_type, tablespace_name
    ORDER BY tablespace_name, segment_type;

Sau import, chạy truy vấn tương tự với owner SALES_TEST để đối chiếu. Đối với partitioned table, kiểm tra thêm DBA_TAB_PARTITIONS và DBA_IND_PARTITIONS nếu cần xác nhận vị trí từng partition.

### 3.6. Những gì REMAP_TABLESPACE không giải quyết

REMAP_TABLESPACE chủ yếu điều khiển metadata lưu trữ của object được import. Nó không:

- Tạo hoặc mở rộng storage vật lý.
- Cấp quota cho user.
- Tự sửa câu lệnh PL/SQL có tên tablespace viết cứng.
- Chuyển các file dữ liệu đã có sẵn ở database đích.
- Bảo đảm mọi object thuộc mọi chế độ import đều hỗ trợ remap giống nhau.
- Thay thế quy trình riêng cho transportable tablespace hoặc các hình thức di chuyển chuyên biệt.

Transportable tablespace, network import và các chế độ đặc biệt có giới hạn riêng về tham số. Khi sử dụng các chế độ này, cần kiểm tra tài liệu đúng phiên bản Oracle trước khi thiết kế mapping.

## 4. Kết hợp REMAP_SCHEMA và REMAP_TABLESPACE

Trong nhiều dự án, cần đổi cả owner lẫn tablespace. Ví dụ:

- Schema nguồn: SALES.
- Schema đích: SALES_TEST.
- Tablespace table nguồn: SALES_DATA.
- Tablespace table đích: APP_DATA.
- Tablespace index nguồn: SALES_INDEX.
- Tablespace index đích: APP_INDEX.

Parameter file có thể viết:

    DIRECTORY=DP_DIR
    DUMPFILE=sales_%U.dmp
    LOGFILE=sales_test_import.log
    SCHEMAS=SALES
    REMAP_SCHEMA=SALES:SALES_TEST
    REMAP_TABLESPACE=SALES_DATA:APP_DATA
    REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
    LOGTIME=ALL
    METRICS=YES

Chạy import:

    impdp system@TARGET PARFILE=sales_test_import.par

Parameter file giúp lưu cấu hình import có thể review, kiểm soát phiên bản và tái sử dụng. Không lưu password production trong file parameter được commit vào repository.

Trước khi chạy, hãy xác nhận:

- Dump file thuộc đúng database và schema nguồn.
- DIRECTORY object trỏ tới đúng thư mục trên máy chủ database.
- User chạy import có quyền đọc dump và ghi log.
- User SALES_TEST đã được chuẩn bị với quota và tablespace.
- APP_DATA và APP_INDEX tồn tại và còn đủ dung lượng.
- Các schema phụ thuộc đã được chuẩn bị.
- Không có dữ liệu quan trọng trong schema đích sẽ bị ghi đè ngoài dự kiến.

## 5. TABLE_EXISTS_ACTION: khi bảng đích đã tồn tại

Trong import, có thể gặp tình huống table metadata hoặc table data được nhập vào một bảng đã có ở database đích. Tham số TABLE_EXISTS_ACTION quyết định cách xử lý đối với bảng đó.

Các lựa chọn:

| Giá trị | Hành vi | Khi cân nhắc sử dụng |
|---|---|---|
| SKIP | Bỏ qua bảng đã tồn tại, không nạp dữ liệu của bảng đó | Giữ nguyên bảng và dữ liệu hiện tại |
| APPEND | Nạp thêm các hàng từ dump vào bảng hiện có | Bổ sung dữ liệu vào bảng tương thích |
| TRUNCATE | Xóa dữ liệu hiện có bằng truncate rồi nạp dữ liệu từ dump | Thay toàn bộ dữ liệu bảng nhưng giữ cấu trúc hiện có |
| REPLACE | Drop bảng hiện có, tạo lại từ metadata trong dump rồi nạp dữ liệu | Muốn thay cấu trúc và nội dung bảng bằng phiên bản trong dump |

Ví dụ:

    TABLE_EXISTS_ACTION=APPEND

Tham số này quan trọng nhất khi import data vào table đã tồn tại. Hãy đặt tường minh thay vì phụ thuộc vào default của job, đặc biệt khi import chỉ có data hoặc được chạy lại sau lỗi.

### 5.1. SKIP

SKIP giữ nguyên bảng đích và bỏ qua việc nạp bảng đó. Dữ liệu hiện có không bị xóa hay bổ sung.

Ví dụ: database đích đã có bảng SALES_TEST.COUNTRIES được quản lý riêng, và không muốn dump nguồn thay đổi dữ liệu của bảng này. SKIP có thể phù hợp nếu mục tiêu là giữ nguyên bảng.

Lưu ý: SKIP không có nghĩa mọi object phụ thuộc đều được bỏ qua. Import job vẫn có thể xử lý các object khác theo metadata và filter. Hãy đọc log để biết chính xác object nào đã được tạo, bỏ qua hoặc gặp lỗi.

### 5.2. APPEND

APPEND giữ dữ liệu hiện tại và thêm hàng từ dump vào bảng đích. Bảng đích cần có cấu trúc tương thích với dữ liệu được import.

Ví dụ:

    CONTENT=DATA_ONLY
    SCHEMAS=SALES
    REMAP_SCHEMA=SALES:SALES_TEST
    TABLE_EXISTS_ACTION=APPEND

APPEND có thể tạo duplicate về mặt nghiệp vụ nếu dữ liệu dump chứa những hàng đã có. Unique constraint có thể khiến một số hàng lỗi; nếu không có ràng buộc phù hợp, dữ liệu trùng có thể được thêm vào. Không nên chạy lại APPEND nhiều lần mà không có chiến lược kiểm soát trùng lặp.

### 5.3. TRUNCATE

TRUNCATE xóa dữ liệu trong bảng hiện có trước khi nạp dữ liệu từ dump. Nó giữ định nghĩa bảng đích, nên không tự thay thế cấu trúc bằng định nghĩa trong dump.

Ví dụ:

    CONTENT=DATA_ONLY
    TABLE_EXISTS_ACTION=TRUNCATE

TRUNCATE phù hợp khi bảng đích có cấu trúc đã được chuẩn bị đúng và muốn thay toàn bộ dữ liệu bằng snapshot trong dump. Cần kiểm tra khóa ngoại, constraint, trigger và quan hệ giữa các bảng; một số điều kiện tham chiếu có thể ngăn truncate.

Nếu import nhiều bảng có quan hệ cha/con, phải lập thứ tự và xử lý constraint phù hợp. Không được giả định Data Pump sẽ tự xử lý mọi ràng buộc nghiệp vụ theo ý muốn.

### 5.4. REPLACE

REPLACE xóa bảng đích hiện có rồi tạo lại bảng theo metadata trong dump, sau đó nạp dữ liệu. Đây là lựa chọn có tác động lớn nhất trong bốn lựa chọn.

Ví dụ:

    CONTENT=ALL
    TABLE_EXISTS_ACTION=REPLACE

Chỉ dùng REPLACE khi đã xác nhận có thể bỏ bảng cũ. Việc drop và tạo lại có thể ảnh hưởng đến index, constraint, trigger, grant và object phụ thuộc. Các object được Data Pump xử lý lại phụ thuộc phạm vi metadata, filter và chế độ import.

Không dùng REPLACE như cách chung để giải quyết mọi lỗi object already exists. TABLE_EXISTS_ACTION chỉ điều khiển hành vi đối với table đã tồn tại; nó không phải lệnh thay thế toàn bộ schema hay mọi loại object.

### 5.5. So sánh theo mục tiêu

| Mục tiêu | Hướng xử lý thường phù hợp |
|---|---|
| Giữ nguyên table đích | SKIP |
| Thêm các hàng mới vào table | APPEND |
| Thay dữ liệu nhưng giữ cấu trúc table đích | TRUNCATE |
| Thay cả định nghĩa table và dữ liệu theo dump | REPLACE |
| Chỉ tạo metadata, chưa nạp dữ liệu | CONTENT=METADATA_ONLY |
| Chỉ nạp dữ liệu vào cấu trúc đã chuẩn bị | CONTENT=DATA_ONLY |

Lựa chọn cuối cùng phải dựa trên yêu cầu đồng bộ dữ liệu và khả năng tương thích cấu trúc. Không có một giá trị TABLE_EXISTS_ACTION đúng cho mọi import.

## 6. TABLE_EXISTS_ACTION không giải quyết mọi object đã tồn tại

Một schema không chỉ có table. Nó còn có index, sequence, view, synonym, procedure, package, trigger, type, constraint, materialized view và nhiều object khác.

Nếu import gặp object đã tồn tại, Data Pump có thể ghi thông báo hoặc lỗi như object type đã tồn tại, tùy loại object và hành vi import. TABLE_EXISTS_ACTION không áp dụng chung cho toàn bộ object.

Ví dụ:

- Một sequence cùng tên đã tồn tại.
- Một package đã được tạo trước bởi release mới hơn.
- Một synonym trỏ tới owner cũ.
- Một type được tham chiếu bởi nhiều bảng.
- Một view có dependency chưa tồn tại.
- Một index đã có nhưng định nghĩa khác.
- Một grant hoặc role đã được cấu hình riêng ở đích.

Cần phân loại object conflict trước khi quyết định xử lý.

### 6.1. Lập danh sách object đã tồn tại

Có thể kiểm tra object trong schema đích:

    SELECT
        object_type,
        status,
        COUNT(*) AS object_count
    FROM dba_objects
    WHERE owner = 'SALES_TEST'
    GROUP BY object_type, status
    ORDER BY object_type, status;

Tìm tên object cụ thể:

    SELECT owner, object_name, object_type, status
    FROM dba_objects
    WHERE owner = 'SALES_TEST'
      AND object_name IN (
          'ORDERS',
          'ORDER_SEQ',
          'PKG_ORDER'
      )
    ORDER BY object_type, object_name;

Đối chiếu với metadata trong dump bằng cách tạo SQL preview hoặc đọc log của lần export/import thử nghiệm. Không nên drop object chỉ vì trùng tên; object đó có thể thuộc một release hoặc ứng dụng đang hoạt động.

### 6.2. Dùng SQLFILE để xem DDL trước khi import

Tham số SQLFILE yêu cầu Data Pump ghi DDL sẽ được thực hiện vào một file SQL thay vì thực thi phần DDL đó. Nó hữu ích để review metadata, owner, tablespace, storage clause và các object được tạo.

Ví dụ:

    impdp system@TARGET
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_preview.log
      SCHEMAS=SALES
      REMAP_SCHEMA=SALES:SALES_TEST
      REMAP_TABLESPACE=SALES_DATA:APP_DATA
      SQLFILE=sales_preview.sql

SQLFILE được ghi trong thư mục vật lý mà DIRECTORY object trỏ tới trên database server. File này là DDL preview, không phải bằng chứng rằng import thực tế chắc chắn thành công. Dữ liệu table không được nạp bằng thao tác preview.

Review file preview để phát hiện:

- Owner còn sót tên schema nguồn.
- Tablespace chưa được remap.
- DDL có thể xung đột với object đích.
- Object phụ thuộc schema khác.
- Storage clause, partition và LOB clause không phù hợp.
- Các object không muốn tạo ở môi trường đích.

### 6.3. Dùng INCLUDE và EXCLUDE có chủ đích

Data Pump hỗ trợ INCLUDE và EXCLUDE để giới hạn loại object hoặc object cụ thể được import. Chúng có thể giúp tách metadata thành nhiều giai đoạn hoặc tránh nhập một số object đã được quản lý riêng.

Ví dụ loại bỏ statistics khỏi import:

    EXCLUDE=STATISTICS

Hoặc chỉ import một số loại object cần thiết bằng INCLUDE. Tên object type, đường dẫn object path và quy tắc filter phụ thuộc chế độ import; cần kiểm tra tài liệu Data Pump cho phiên bản cụ thể.

Không dùng EXCLUDE một cách tùy tiện. Bỏ qua constraint, trigger, grant hoặc type có thể khiến dữ liệu được nạp nhưng ứng dụng hoạt động sai. Hãy ghi rõ lý do loại object và có kế hoạch tạo lại nếu cần.

## 7. Chia import thành các giai đoạn

Với schema lớn hoặc schema đích có một phần cấu trúc đã được triển khai trước, nên tách import thành các giai đoạn có thể kiểm soát.

### 7.1. Metadata-only

Tạo object và metadata trước, chưa nạp dữ liệu:

    SCHEMAS=SALES
    REMAP_SCHEMA=SALES:SALES_TEST
    REMAP_TABLESPACE=SALES_DATA:APP_DATA
    REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
    CONTENT=METADATA_ONLY

Trước khi chạy, review SQLFILE và chuẩn bị object dependency. Một số object có thể cần được tạo theo thứ tự hoặc điều chỉnh riêng.

### 7.2. Data-only

Sau khi cấu trúc đã tồn tại và được kiểm tra, nạp dữ liệu:

    SCHEMAS=SALES
    REMAP_SCHEMA=SALES:SALES_TEST
    CONTENT=DATA_ONLY
    TABLE_EXISTS_ACTION=APPEND

APPEND chỉ là ví dụ. Nếu muốn thay dữ liệu của table đã tồn tại, cân nhắc TRUNCATE sau khi kiểm tra ràng buộc; nếu muốn giữ nguyên table, dùng SKIP; nếu cần thay cấu trúc, quay lại phương án metadata import có kiểm soát.

Tách metadata và data giúp review rõ hơn, nhưng cũng tạo thêm trách nhiệm đồng bộ: cấu trúc phải tương thích với dump và không được thay đổi giữa hai giai đoạn theo cách làm sai mapping cột.

### 7.3. Kiểm tra log sau mỗi giai đoạn

Data Pump tạo log ghi nhận object được xử lý, số hàng đã nạp và lỗi. Hãy kiểm tra:

- Job có hoàn thành hay dừng ở trạng thái lỗi.
- Object nào được tạo, bỏ qua hoặc thất bại.
- Số hàng nạp của từng table.
- Lỗi quota, tablespace, quyền, constraint hoặc dependency.
- Các cảnh báo do object đã tồn tại.
- Các object invalid sau khi import.

Không kết luận import thành công chỉ vì process impdp đã kết thúc. Phải kiểm tra exit status, log và dữ liệu.

## 8. Xử lý lỗi thường gặp

### 8.1. Tablespace đích không tồn tại

Nguyên nhân: mapping trỏ tới tablespace chưa được tạo hoặc tên sai.

Cách xử lý:

1. Xác nhận mapping trong parameter file.
2. Kiểm tra DBA_TABLESPACES ở database đích.
3. Tạo tablespace với storage phù hợp.
4. Kiểm tra quota và dung lượng vật lý.
5. Chạy lại import sau khi xác định job trước đã dừng ở đâu.

Không tạo tablespace tùy tiện trên filesystem không đủ dung lượng.

### 8.2. User đích thiếu quota

Import có thể tạo được một số object nhưng thất bại khi cấp phát segment tiếp theo.

Kiểm tra:

    SELECT username, tablespace_name, bytes, max_bytes
    FROM dba_ts_quotas
    WHERE username = 'SALES_TEST';

Điều chỉnh quota sau khi ước lượng kích thước table, index, LOB và partition. Không cấp UNLIMITED TABLESPACE cho ứng dụng chỉ để né lỗi mà không đánh giá dung lượng.

### 8.3. Object already exists

Nếu log báo object đã tồn tại, xác định object type trước. Nếu là table, TABLE_EXISTS_ACTION có thể điều khiển việc nạp dữ liệu. Nếu là sequence, package, type, view hoặc object khác, cần xử lý bằng metadata import/filter hoặc dọn schema đích theo kế hoạch.

Không chạy lại import với REPLACE chỉ để xóa lỗi object already exists; có thể làm mất dữ liệu hoặc metadata đang được ứng dụng sử dụng.

### 8.4. APPEND tạo dữ liệu trùng hoặc lỗi unique constraint

APPEND không tự deduplicate. Nếu dump chứa hàng đã có, kết quả phụ thuộc constraint và cấu trúc table. Có thể phát sinh lỗi duplicate key hoặc thêm dữ liệu trùng nếu không có constraint phù hợp.

Trước khi chạy lại job:

- Xác định lần import trước đã nạp được bao nhiêu hàng.
- Đối chiếu khóa nghiệp vụ và khóa chính.
- Quyết định append phần còn thiếu, truncate rồi nạp lại hay tạo schema sạch.
- Kiểm tra transaction và trạng thái job để tránh lặp dữ liệu.

### 8.5. TRUNCATE không thực hiện được

Các ràng buộc tham chiếu và điều kiện của table có thể ngăn truncate. Hãy kiểm tra khóa ngoại, constraint và quan hệ giữa các bảng. Nếu cần, thiết kế thứ tự nạp và xử lý constraint theo quy trình đã kiểm thử.

Không disable toàn bộ constraint trên production chỉ để import chạy qua. Việc bật lại constraint phải bảo đảm dữ liệu thỏa điều kiện.

### 8.6. Object import xong nhưng INVALID

Một package, procedure, view hoặc trigger có thể được tạo nhưng không biên dịch được do dependency thiếu, owner đổi tên hoặc quyền không đủ.

Kiểm tra:

    SELECT owner, object_name, object_type, status
    FROM dba_objects
    WHERE owner = 'SALES_TEST'
      AND status = 'INVALID'
    ORDER BY object_type, object_name;

Xem lỗi biên dịch:

    SELECT owner, name, type, line, position, text
    FROM dba_errors
    WHERE owner = 'SALES_TEST'
    ORDER BY name, sequence;

Xử lý dependency, grants và tham chiếu schema; sau đó biên dịch lại object. Không coi INVALID là lỗi có thể bỏ qua nếu ứng dụng phụ thuộc vào object đó.

## 9. Quy trình mẫu chuyển schema sang môi trường test

Giả sử cần chuyển SALES từ nguồn sang SALES_TEST ở database đích, đồng thời chuyển tablespace.

### Bước 1: Khảo sát nguồn

Kiểm tra object, segment và dependency:

    SELECT object_type, COUNT(*)
    FROM dba_objects
    WHERE owner = 'SALES'
    GROUP BY object_type
    ORDER BY object_type;

    SELECT tablespace_name,
           ROUND(SUM(bytes) / 1024 / 1024) AS size_mb
    FROM dba_segments
    WHERE owner = 'SALES'
    GROUP BY tablespace_name
    ORDER BY tablespace_name;

Ghi nhận số lượng hàng của các bảng quan trọng, sequence, grants, synonym, job và các dependency ngoài schema.

### Bước 2: Export

    expdp system@SOURCE
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_export.log
      SCHEMAS=SALES
      PARALLEL=4

Đảm bảo dump hoàn tất và file có thể đọc được ở môi trường đích.

### Bước 3: Chuẩn bị đích

Tạo APP_DATA, APP_INDEX, user SALES_TEST, default tablespace, temporary tablespace và quota. Kiểm tra schema đích có object cũ hay không.

### Bước 4: Preview DDL

    impdp system@TARGET
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_preview.log
      SCHEMAS=SALES
      REMAP_SCHEMA=SALES:SALES_TEST
      REMAP_TABLESPACE=SALES_DATA:APP_DATA
      REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
      SQLFILE=sales_preview.sql

Review file SQL được tạo trên máy chủ database và kiểm tra mapping/dependency.

### Bước 5: Import

    impdp system@TARGET
      DIRECTORY=DP_DIR
      DUMPFILE=sales_%U.dmp
      LOGFILE=sales_import.log
      SCHEMAS=SALES
      REMAP_SCHEMA=SALES:SALES_TEST
      REMAP_TABLESPACE=SALES_DATA:APP_DATA
      REMAP_TABLESPACE=SALES_INDEX:APP_INDEX
      LOGTIME=ALL
      METRICS=YES

Nếu schema đích đã có table, thêm TABLE_EXISTS_ACTION theo mục tiêu đã thống nhất. Với lần import đầu vào schema sạch, không cần đặt REPLACE để ép ghi đè.

### Bước 6: Đối chiếu sau import

Kiểm tra số object và trạng thái:

    SELECT object_type, status, COUNT(*)
    FROM dba_objects
    WHERE owner = 'SALES_TEST'
    GROUP BY object_type, status
    ORDER BY object_type, status;

Kiểm tra segment:

    SELECT segment_type, tablespace_name,
           ROUND(SUM(bytes) / 1024 / 1024) AS size_mb
    FROM dba_segments
    WHERE owner = 'SALES_TEST'
    GROUP BY segment_type, tablespace_name
    ORDER BY tablespace_name, segment_type;

Đối chiếu số hàng của các bảng trọng yếu, sequence value, constraint, index, grants và dependency. Kiểm thử các luồng nghiệp vụ trên môi trường test trước khi cho ứng dụng sử dụng.

## 10. Bảo đảm tính nhất quán và an toàn khi chạy lại

Import có thể bị gián đoạn do lỗi storage, network, quota hoặc process. Một lần import lỗi không đồng nghĩa mọi thay đổi đã được rollback toàn bộ. Data Pump job có thể giữ trạng thái để attach và tiếp tục, hoặc có thể cần xử lý object đã được tạo một phần.

Trước khi chạy lại:

1. Đọc log của job trước và xác định object đã hoàn tất.
2. Kiểm tra trạng thái job Data Pump và quyết định attach/continue nếu phù hợp.
3. Kiểm tra bảng nào đã có dữ liệu và số hàng đã nạp.
4. Xác định lại TABLE_EXISTS_ACTION cho từng loại dữ liệu.
5. Xem xét tạo schema đích sạch nếu môi trường cho phép và mục tiêu là một bản copy nhất quán.
6. Không chạy APPEND lặp lại nếu chưa biết lần trước đã nạp tới đâu.

Nếu yêu cầu một bản sao nhất quán tại một thời điểm, cần phối hợp thời điểm export, transaction consistency và thay đổi dữ liệu trong quá trình chuyển. Một dump được tạo trong khi ứng dụng tiếp tục ghi dữ liệu có thể cần chiến lược đồng bộ bổ sung tùy yêu cầu cutover.

## 11. Checklist trước và sau import

### Trước import

- Xác nhận database nguồn, database đích, DBID và schema cần chuyển.
- Xác nhận dump file và DIRECTORY object.
- Kiểm tra target schema, quyền, profile, quota và default tablespace.
- Tạo tablespace đích, kiểm tra datafile và storage.
- Liệt kê mapping schema/tablespace cho table, index, LOB và partition.
- Kiểm tra object đã tồn tại trong schema đích.
- Xem DDL bằng SQLFILE nếu có thay đổi owner/tablespace hoặc schema đích không sạch.
- Chọn CONTENT và TABLE_EXISTS_ACTION theo mục tiêu.
- Bảo vệ dump, log và credential; không đưa password vào file chia sẻ.

### Sau import

- Kiểm tra exit status và toàn bộ log.
- Kiểm tra object được tạo, bỏ qua và object INVALID.
- Đối chiếu số hàng của bảng quan trọng.
- Kiểm tra segment nằm đúng tablespace.
- Kiểm tra quota, grants, roles, synonym, sequence và dependency.
- Biên dịch lại PL/SQL và view nếu cần.
- Kiểm thử ứng dụng với connection string và owner đích.
- Lưu log, parameter file đã loại bỏ bí mật và biên bản đối chiếu.

## 12. Nguyên tắc cần nhớ

- REMAP_SCHEMA đổi owner của object được import từ schema nguồn sang schema đích; nó không thay mọi chuỗi tên schema trong source code.
- REMAP_TABLESPACE đổi vị trí segment được import từ tablespace nguồn sang tablespace đích; tablespace đích và quota phải được chuẩn bị.
- TABLE_EXISTS_ACTION xử lý table đã tồn tại, không phải chiến lược xử lý chung cho mọi object trong schema.
- SKIP giữ table hiện tại; APPEND thêm hàng; TRUNCATE xóa hàng hiện tại rồi nạp; REPLACE drop và tạo lại table theo metadata trong dump.
- APPEND có thể gây trùng dữ liệu nếu chạy lại; TRUNCATE và REPLACE có tác động phá hủy dữ liệu hiện có.
- SQLFILE giúp review DDL trước import nhưng không chứng minh dữ liệu sẽ nạp thành công.
- INCLUDE và EXCLUDE cần được dùng theo object path và chế độ import phù hợp; bỏ qua object có thể làm hỏng dependency.
- Luôn kiểm tra log, object INVALID, row count, tablespace, quota và ứng dụng sau import.

Một lần chuyển schema an toàn cần kết hợp remap với chuẩn bị môi trường đích, kiểm soát object đã tồn tại và đối chiếu sau import. Hãy coi mỗi tham số là một quyết định riêng: owner nào sẽ sở hữu object, segment sẽ nằm ở đâu và dữ liệu cũ của table sẽ được giữ, nối thêm, xóa hay thay thế.
