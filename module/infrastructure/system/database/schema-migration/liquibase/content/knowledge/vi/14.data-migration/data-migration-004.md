# Cập nhật dữ liệu từ CSV bằng `loadUpdateData` trong Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với **changelog, changeset, precondition, checksum và lịch sử triển khai**; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ngoài thay đổi cấu trúc bảng, hệ thống thường phải chuyển đổi **dữ liệu tham chiếu**, chẳng hạn cấp độ khách hàng, bảng mã, cấu hình mặc định hoặc danh mục nghiệp vụ. Liquibase cung cấp change type `loadUpdateData` để đọc một file CSV và áp dụng dữ liệu theo cơ chế **cập nhật hàng đã có, chèn hàng chưa có**.

Bài học thuộc phần **Chuyển đổi dữ liệu**. Trọng tâm không chỉ là cú pháp `loadUpdateData`, mà còn là xác định khóa đối sánh, thiết kế CSV đáng tin cậy, quản lý lịch sử changeset, kiểm chứng các giá trị được ghi và chuẩn bị rollback khi cập nhật dữ liệu có sẵn. Các ví dụ minh họa trên PostgreSQL; cách sinh SQL, hỗ trợ tùy chọn và hành vi chuyển đổi giá trị cần được kiểm tra với phiên bản Liquibase và DBMS thực tế.

## 1. `loadUpdateData` giải quyết vấn đề gì?

Giả sử bảng `customer_tier` lưu cấu hình hạng thành viên theo mã khách hàng. Ban đầu:

| `customer_code` | `tier` | `credit_limit` | `active` |
|---|---|---:|---|
| `C001` | `BRONZE` | 10.000,00 | `true` |
| `C002` | `SILVER` | 25.000,00 | `true` |

Một file CSV phiên bản mới chứa:

| `customer_code` | `tier` | `credit_limit` | `active` |
|---|---|---:|---|
| `C001` | `GOLD` | 150.000,00 | `true` |
| `C003` | `SILVER` | 30.000,00 | `false` |

Khi sử dụng `loadUpdateData` với `primaryKey: customer_code`:

- Hàng `C001` **đã có**: Liquibase đối sánh theo `customer_code` và cập nhật các cột được cung cấp.
- Hàng `C003` **chưa có**: Liquibase chèn hàng mới, trừ khi cấu hình một chế độ chỉ cập nhật mà phiên bản đang dùng hỗ trợ.
- Hàng `C002` **không có trong CSV**: vẫn tồn tại; `loadUpdateData` **không phải** công cụ đồng bộ để xóa mọi hàng vắng mặt trong nguồn.

Đây là kiểu xử lý thường gọi là **upsert** (*update or insert*). Không nên mặc định Liquibase sử dụng đúng câu lệnh SQL `MERGE` hoặc `INSERT ... ON CONFLICT` của một DBMS cụ thể: SQL được sinh và cách thực thi phụ thuộc phiên bản/cách truy cập database. Luôn xem SQL preview nếu hành vi hoặc hiệu năng quan trọng.

### So sánh các công cụ nạp dữ liệu

| Cách làm | Hành vi chính | Dùng khi nào? |
|---|---|---|
| `loadData` | Đọc CSV và chèn dữ liệu | Nạp dữ liệu ban đầu vào bảng trống hoặc khi biết chắc các hàng chưa tồn tại |
| **`loadUpdateData`** | Tìm hàng theo khóa; cập nhật nếu có, chèn nếu chưa có | Thay đổi dữ liệu tham chiếu, seed có khóa ổn định, cập nhật cấu hình theo đợt |
| `insert` / `update` | Khai báo tường minh từng thay đổi trong changelog | Một vài giá trị nhỏ, cần điều kiện rõ và review từng dòng |
| `sql` / `sqlFile` | Thực thi SQL tự viết | Cần logic chuyển đổi phức tạp, join, biểu thức DBMS-specific hoặc thao tác khối lượng lớn có chiến lược riêng |

**Quan trọng:** “upsert” ở đây là **hành vi của một lần thực thi changeset**. Nó không đồng nghĩa với việc Liquibase tự đọc lại CSV sau mỗi lần khởi động ứng dụng. Lịch sử `DATABASECHANGELOG` vẫn quyết định changeset đã chạy hay chưa.

## 2. Thiết kế CSV như một hợp đồng dữ liệu

CSV không chứa schema hoàn chỉnh: parser nhìn thấy văn bản và phải được hướng dẫn cách tách hàng, cột, xử lý dấu nháy và chuyển kiểu. Trước khi viết changelog, cần chốt:

1. **Khóa đối sánh**: trường nào định danh một hàng? Có duy nhất và không rỗng không?
2. **Tiêu đề cột**: tên header có cố định, phân biệt chữ hoa, dấu cách, khoảng trắng hay ký tự đặc biệt không?
3. **Mã hóa**: thống nhất UTF-8; xác minh ký tự tiếng Việt, dấu phẩy và dấu nháy.
4. **Delimiter**: dùng dấu phẩy, chấm phẩy hay ký tự khác? File và changelog phải đồng nhất.
5. **Dữ liệu thiếu**: phân biệt hàng không có cột, ô trống, chuỗi rỗng, và giá trị SQL `NULL`.
6. **Giá trị số/ngày/boolean**: dùng một định dạng không phụ thuộc thiết lập locale của ứng dụng.
7. **Phạm vi cập nhật**: các cột có trong CSV có thể ghi đè dữ liệu đã được ứng dụng chỉnh sửa hay không?
8. **Quy trình phát hành**: CSV có version/commit rõ ràng và được đóng gói cùng changelog hay không?

Ví dụ CSV hợp lệ (lưu thành `customer-tiers-2026-11.csv`):

```csv
customer_code,tier,credit_limit,active,note
C001,GOLD,150000.00,true,"Khách hàng ưu tiên, đã xác minh"
C003,SILVER,30000.00,false,"Đăng ký mới"
```

Các chi tiết đáng chú ý:

- Dòng đầu là **header**, không phải dữ liệu.
- `150000.00` dùng dấu chấm làm dấu thập phân; không dùng `150.000,00` như cách hiển thị theo locale Việt Nam.
- `true`/`false` được biểu diễn nhất quán để chuyển sang boolean.
- Trường `note` đầu tiên có **dấu phẩy bên trong**, nên phải được bao bằng dấu nháy kép để parser không tách thành hai cột.
- Trong file CSV, nếu một ô chứa dấu nháy kép, theo quy ước CSV thông thường có thể viết dấu nháy kép đó hai lần bên trong giá trị được bao nháy; phải thử với parser cấu hình thực tế.
- Mã `customer_code` là **chuỗi định danh**, không phải số để tính toán. Nếu có `000123`, cần giữ nguyên số 0 đầu.

Không đưa mật khẩu, token, khóa API hay dữ liệu cá nhân nhạy cảm không cần thiết vào CSV lưu trong Git. Nếu migration cần dữ liệu thật có kiểm soát, phải dùng kênh truyền và quy trình bảo mật riêng.

## 3. Cấu trúc thư mục để CLI, Spring Boot và CI cùng tìm được CSV

Ví dụ dự án Java:

```text
src/main/resources/
└── db/
    └── changelog/
        ├── master.yaml
        ├── changes/
        │   ├── 001-create-customer-tier.yaml
        │   └── 002-upsert-customer-tier.yaml
        └── data/
            └── customer-tiers-2026-11.csv
```

File `master.yaml` có thể include các changelog con:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer-tier.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-upsert-customer-tier.yaml
      relativeToChangelogFile: true
```

Vì changelog chứa `loadUpdateData` nằm trong thư mục `changes/`, đường dẫn tương đối đến CSV là `../data/customer-tiers-2026-11.csv`. Đặt `relativeToChangelogFile: true` để Liquibase tìm CSV **từ vị trí file chứa change type**, không phụ thuộc thư mục làm việc ngẫu nhiên của CLI.

Khi chạy Spring Boot từ JAR, tên tài nguyên trên classpath thường bắt đầu bằng `db/changelog/...` chứ không có tiền tố `src/main/resources/`. Hãy đảm bảo cả YAML lẫn CSV được copy vào artifact; chỉ tồn tại trong source tree là chưa đủ.

**Lưu ý về định danh:** Liquibase nhận diện changeset bằng `id`, `author` và đường dẫn changelog (hoặc `logicalFilePath` được cấu hình). Chuyển file giữa các root classpath hoặc đổi cách chạy CLI có thể ảnh hưởng tên file trong lịch sử. Với hệ thống đã triển khai, đối chiếu `FILENAME` trong `DATABASECHANGELOG` trước khi thay đổi layout.

## 4. Chuẩn bị bảng đích và dữ liệu thử nghiệm

Để có một ví dụ tự chứa, ta tạo bảng `customer_tier` trước bằng changeset `001`. Changelog sau có thể nằm trong `changes/001-create-customer-tier.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-customer-tier"
      author: "db-team"
      changes:
        - createTable:
            tableName: customer_tier
            columns:
              - column:
                  name: customer_code
                  type: VARCHAR(24)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: tier
                  type: VARCHAR(20)
                  constraints:
                    nullable: false
              - column:
                  name: credit_limit
                  type: DECIMAL(14,2)
                  constraints:
                    nullable: false
              - column:
                  name: active
                  type: BOOLEAN
                  constraints:
                    nullable: false
              - column:
                  name: note
                  type: VARCHAR(255)
      rollback:
        - dropTable:
            tableName: customer_tier
```

Ở ví dụ này, `customer_code` là khóa chính thật của bảng. Điều đó giúp Liquibase đối sánh mỗi bản ghi và giúp DBMS cưỡng chế tính duy nhất ngay cả khi hai tiến trình ghi đồng thời.

Để quan sát cả đường **update** lẫn **insert**, trên *database thử nghiệm có thể tạo lại*, hãy chạy changeset tạo bảng trước, rồi chuẩn bị hai hàng:

```sql
INSERT INTO customer_tier
    (customer_code, tier, credit_limit, active, note)
VALUES
    ('C001', 'BRONZE', 10000.00, TRUE, 'Giá trị cũ'),
    ('C002', 'SILVER', 25000.00, TRUE, 'Không nằm trong CSV');
```

Đây là dữ liệu giả để thực hành. Trong dự án thật, bảng có thể đã có dữ liệu và không cần lệnh chèn thử này. Đừng chạy đoạn `INSERT` trên production chỉ để chứng minh migration hoạt động.

## 5. Changelog `loadUpdateData` hoàn chỉnh

File `changes/002-upsert-customer-tier.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: "002-upsert-customer-tier-2026-11"
      author: "db-team"
      comment: "Cập nhật hạng khách hàng từ CSV đã kiểm duyệt"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer_tier
      changes:
        - loadUpdateData:
            file: ../data/customer-tiers-2026-11.csv
            relativeToChangelogFile: true
            tableName: customer_tier
            primaryKey: customer_code
            separator: ","
            quotchar: '"'
            encoding: UTF-8
            columns:
              - column:
                  header: customer_code
                  name: customer_code
                  type: STRING
              - column:
                  header: tier
                  name: tier
                  type: STRING
              - column:
                  header: credit_limit
                  name: credit_limit
                  type: NUMERIC
              - column:
                  header: active
                  name: active
                  type: BOOLEAN
              - column:
                  header: note
                  name: note
                  type: STRING
```

Các thành phần quan trọng:

| Thuộc tính | Ý nghĩa | Quy tắc cần ghi nhớ |
|---|---|---|
| `file` | Đường dẫn CSV | Phải tồn tại trong runtime artifact và đọc được bởi ResourceAccessor |
| `relativeToChangelogFile` | Tìm CSV tương đối với changelog hiện tại | Giúp cấu trúc thư mục dễ chuyển giữa local/CI/JAR |
| `tableName` | Bảng được upsert | Bảng phải tồn tại, đúng schema và có các cột tương thích |
| **`primaryKey`** | Một hoặc nhiều cột dùng để đối sánh hàng | Phải có giá trị ổn định, duy nhất và được thống nhất với dữ liệu thực |
| `separator` | Ký tự ngăn cột CSV | Dấu phẩy trong ví dụ; file dùng dấu chấm phẩy phải khai báo tương ứng |
| `quotchar` | Ký tự bao trường có delimiter | Dấu nháy kép được biểu diễn bằng chuỗi YAML có dấu nháy đơn |
| `encoding` | Mã hóa ký tự | Chọn UTF-8 và kiểm tra dữ liệu tiếng Việt |
| `columns` | Ánh xạ header CSV sang cột và kiểu dữ liệu | Giúp kiểm soát tên cột và cách parse giá trị |
| `preConditions` | Kiểm tra điều kiện trước changeset | Không thay thế kiểm tra đầy đủ CSV hoặc khóa duy nhất |

`header` là tên cột trong file CSV; `name` là tên cột đích trong database. Chúng có thể giống hoặc khác nhau. Ví dụ, CSV có header `customerCode` nhưng bảng dùng `customer_code` thì có thể khai báo `header: customerCode` và `name: customer_code`.

Trong ví dụ, `type` ở phần ánh xạ CSV là cách Liquibase diễn giải **giá trị đầu vào** (như `STRING`, `NUMERIC`, `BOOLEAN`). Nó **không** tạo hoặc sửa kiểu cột database. Kiểu cột đích đã được định nghĩa bằng `createTable` hoặc tồn tại từ migration trước.

### 5.1. Kết quả mong đợi sau khi chạy

Sau một lần chạy `update` thành công trên dữ liệu thử ở mục 4:

| `customer_code` | `tier` | `credit_limit` | `active` | `note` | Hành vi |
|---|---|---:|---|---|---|
| `C001` | `GOLD` | 150000.00 | `true` | Khách hàng ưu tiên, đã xác minh | **Update** hàng cũ |
| `C002` | `SILVER` | 25000.00 | `true` | Không nằm trong CSV | **Giữ nguyên** |
| `C003` | `SILVER` | 30000.00 | `false` | Đăng ký mới | **Insert** hàng mới |

`loadUpdateData` không xóa hàng `C002` chỉ vì nó vắng trong CSV. Nếu cần đồng bộ dữ liệu kiểu “nguồn CSV là toàn bộ trạng thái mong muốn, xóa những hàng không còn có mặt”, phải thiết kế riêng logic xác định hàng dư, duyệt ảnh hưởng và thao tác xóa an toàn. Không suy rằng `loadUpdateData` có hành vi replace-all.

### 5.2. Khóa đối sánh phải bảo đảm một hàng duy nhất

`primaryKey: customer_code` đặt tên cột dùng để tìm hàng cần cập nhật. Tên thuộc tính là `primaryKey`, nhưng bài toán thiết kế vẫn phải bảo đảm **tổ hợp được dùng đối sánh nhận diện duy nhất một hàng**. Tốt nhất nó trùng khóa chính thật hoặc có unique constraint phù hợp.

Một số rủi ro:

- Hai hàng database có cùng khóa đối sánh → có thể dẫn đến cập nhật nhiều hàng hoặc kết quả không như kỳ vọng nếu DB chưa cưỡng chế uniqueness.
- Hai dòng CSV có cùng khóa → có thể gây ghi đè nhiều lần, lỗi, hoặc kết quả phụ thuộc thứ tự/cách sinh SQL; phải phát hiện và xử lý từ trước, **không dựa vào “dòng cuối thắng”**.
- Khóa trống, chứa khoảng trắng hoặc khác nhau về chữ hoa → kết quả đối sánh phụ thuộc cách parse và collation của database.
- Khóa có số 0 đầu được đọc theo kiểu numeric → `000123` có thể biến thành `123`, làm đối sánh sai.
- Khóa là giá trị dễ thay đổi như tên hiển thị → khó xác định bản ghi khi dữ liệu được chỉnh sửa.

Đối với dữ liệu theo từng tổ chức, lựa chọn khóa ghép ổn định như `tenant_id` + `code` thường đúng hơn dùng `code` đơn lẻ.

## 6. Dùng khóa ghép trong `loadUpdateData`

Giả sử bảng `tenant_config` có hai cột `tenant_id` và `config_key` được cưỡng chế duy nhất theo tổ hợp. File CSV:

```csv
tenant_id,config_key,config_value
10,theme,dark
10,timezone,Asia/Ho_Chi_Minh
11,theme,light
```

Changeset tương ứng:

```yaml
databaseChangeLog:
  - changeSet:
      id: "003-upsert-tenant-config"
      author: "db-team"
      changes:
        - loadUpdateData:
            file: ../data/tenant-config.csv
            relativeToChangelogFile: true
            tableName: tenant_config
            primaryKey: tenant_id,config_key
            encoding: UTF-8
            columns:
              - column:
                  header: tenant_id
                  name: tenant_id
                  type: NUMERIC
              - column:
                  header: config_key
                  name: config_key
                  type: STRING
              - column:
                  header: config_value
                  name: config_value
                  type: STRING
```

`primaryKey` hỗ trợ danh sách cột phân cách bằng dấu phẩy cho trường hợp khóa ghép; ở đây một mã `theme` có thể tồn tại cho nhiều tenant nhưng một tenant không được có hai dòng `theme`. Trước khi dùng ví dụ, bảng `tenant_config` phải tồn tại, có ràng buộc/khóa phù hợp, và tập dữ liệu phải được kiểm tra không trùng `(tenant_id, config_key)`.

Không dùng ký tự phân tách hoặc khoảng trắng tùy tiện trong tên cột; cần kiểm tra quy tắc phân tích `primaryKey` của phiên bản Liquibase đang dùng. Nếu trường mã chứa dấu phẩy **bên trong giá trị**, đó là chuyện của parser CSV; đừng nhầm với dấu phẩy phân cách **tên cột** trong thuộc tính `primaryKey`.

## 7. Khi nào chỉ cập nhật mà không muốn chèn?

Có những đợt migration chỉ được phép sửa cấu hình của **các hàng đã tồn tại**. Tự ý tạo bản ghi mới có thể sai nghiệp vụ. Một số phiên bản Liquibase hỗ trợ thuộc tính `onlyUpdate` của `loadUpdateData`:

```yaml
- loadUpdateData:
    file: ../data/customer-tiers-2026-11.csv
    relativeToChangelogFile: true
    tableName: customer_tier
    primaryKey: customer_code
    onlyUpdate: true
```

Đoạn trên chỉ là phần `changes` và phải được đặt trong một `changeSet` hợp lệ. Khi phiên bản Liquibase hỗ trợ tùy chọn này, nó giới hạn logic về cập nhật các hàng đã tồn tại, **không chèn** hàng chưa khớp. Nếu phiên bản trong dự án không hỗ trợ, phải chọn phương án khác (chẳng hạn `update` có điều kiện, SQL có kiểm soát hoặc nâng cấp phiên bản sau khi kiểm thử).

**Không dùng `onlyUpdate` như một cách âm thầm bỏ qua dữ liệu thiếu.** Nếu CSV tuyên bố mọi khóa đều phải có sẵn, hãy kiểm tra trước số khóa không khớp và quyết định fail migration khi có dữ liệu bất thường. “Không chèn” không có nghĩa “đã xác thực đầy đủ nguồn”.

Một số đội dùng `loadUpdateData` trong môi trường dev để seed, nhưng production chỉ cho phép cập nhật. Nếu chọn hai cấu hình thực thi khác nhau, cần mô hình hóa rõ thành các changeset/luồng deploy có kiểm soát; tránh chỉnh trực tiếp một changeset đã triển khai rồi làm thay đổi lịch sử và checksum.

## 8. Ánh xạ kiểu dữ liệu và các giá trị đặc biệt

CSV chỉ là văn bản. Khi nhập liệu, nên ghi kiểu ở mục `columns` một cách có chủ đích và kiểm thử với DBMS đích:

| Dữ liệu trong CSV | Kiểu khai báo gợi ý | Rủi ro cần kiểm tra |
|---|---|---|
| `C001`, `000123` | `STRING` | Giữ số 0 đầu, tránh ép sang số |
| `150000.00` | `NUMERIC` | Dùng dấu thập phân ổn định, kiểm tra precision/scale cột đích |
| `true`, `false` | `BOOLEAN` | Không nhầm chuỗi `"false"` với boolean; kiểm tra giá trị parser chấp nhận |
| `2026-11-19` | `DATE` nếu phù hợp | Chốt định dạng ngày; kiểm tra kiểu DATE/TIMESTAMP đích |
| Chuỗi tiếng Việt | `STRING` | UTF-8, BOM, newline và độ dài cột |
| Biểu thức SQL | Cấu hình kiểu/thuộc tính thích hợp, không coi mặc nhiên là `STRING` | Không đưa biểu thức không tin cậy từ CSV vào SQL |

### 8.1. Ô rỗng, chuỗi rỗng và `NULL`

Ba trường hợp có thể rất khác nhau:

1. Không có cột trong CSV (nhưng bảng có cột): ứng dụng database có thể dùng default cho `INSERT` nếu cột không được cung cấp.
2. Header có cột nhưng ô trống: parser/change type có thể diễn giải ô này theo quy tắc đặc thù, thường cần xem xét khả năng chuyển thành `NULL`.
3. Ô chứa các ký tự `NULL` hoặc dấu nháy bao chuỗi rỗng: **không được đoán** kết quả có phải SQL `NULL`, chuỗi `"NULL"` hay `""`.

Cách diễn giải giá trị rỗng phụ thuộc phiên bản Liquibase, loại ánh xạ cột và DBMS. Hãy tạo testcase có đủ các trường hợp: ô trống, chuỗi trống được bao nháy, chữ `NULL` và khoảng trắng. Dùng `SELECT` xác minh giá trị lưu thật; không thử điều chỉnh file chỉ dựa trên bề ngoài của CSV.

Đặc biệt nguy hiểm khi cập nhật hàng cũ: nếu một ô trống được hiểu là `NULL`, dữ liệu đang có có thể bị **xóa giá trị** ngoài ý muốn. Với dữ liệu không nên bị ghi đè, cân nhắc không đưa cột đó vào file nguồn hoặc tách logic cập nhật riêng. Đừng lấy `loadUpdateData` làm cơ chế “chỉ cập nhật trường khác null” nếu chưa xác minh rõ hành vi.

### 8.2. Dấu phẩy, dấu nháy, UTF-8 và xuống dòng

CSV có thể chứa:

```csv
customer_code,note
C010,"Khách hàng ""VIP"", ưu tiên"
C011,"Ghi chú nhiều từ, có dấu phẩy"
```

Khi dùng `separator: ","` và `quotchar: '"'`, trường có dấu phẩy bên trong được bao nháy; dấu nháy kép trong văn bản được nhân đôi theo quy tắc CSV thông thường. Nếu file dùng chấm phẩy làm delimiter, phải đổi `separator` phù hợp.

Những lỗi thường gặp:

- Excel xuất CSV theo locale khác, dùng `;` thay dấu `,`, hoặc đổi dấu thập phân.
- CSV có UTF-8 BOM khiến header đầu tiên bị nhận diện khác với `customer_code`; cần kiểm tra khả năng xử lý BOM của parser/phiên bản đang dùng.
- Trường có xuống dòng nhưng dấu nháy không hợp lệ khiến parser chia một bản ghi thành nhiều dòng.
- Dữ liệu ngày giờ chứa múi giờ hoặc định dạng địa phương mà parser/DBMS không hiểu.
- Giá trị có dấu `#` hoặc chuỗi giống `null` bị xử lý không như người viết dự kiến.

Chốt một mẫu CSV chuẩn trong repository, review file diff theo từng release và tránh chỉnh sửa qua chương trình bảng tính có thể tự động đổi kiểu hoặc chuẩn hóa mã có số 0 đầu.

## 9. Kiểm tra chất lượng nguồn trước khi áp dụng

`loadUpdateData` không thay thế một pipeline kiểm định dữ liệu. Nên xác nhận:

| Kiểm tra | Tiêu chí đạt | Phản ứng khi thất bại |
|---|---|---|
| Header | Đúng tên, không trùng, không thêm/xóa cột ngoài hợp đồng | Chặn release; sửa CSV/mapping |
| Khóa | Không rỗng, không trùng trong file, đúng format | Chặn upsert, điều tra nguồn |
| Kiểu | Số/ngày/boolean parse được, không tràn precision, đúng đơn vị | Chặn trước DML |
| Kích thước | Số hàng và dung lượng nằm trong giới hạn đã chốt | Cân nhắc chia lô hoặc công cụ nạp bulk |
| Miền giá trị | `tier` thuộc danh mục cho phép, `credit_limit >= 0` | Xác nhận ràng buộc SQL hoặc pre-validation |
| Dữ liệu đích | Khóa đối sánh là duy nhất, bảng/cột đã tồn tại | Sửa schema hoặc dữ liệu đích trước |
| Tác động ghi đè | Các cột được phép thay đổi từ nguồn CSV | Review với chủ sở hữu dữ liệu |
| Provenance | File thuộc đúng release/commit, không chứa bí mật | Dừng deploy, sửa nguồn |

Ví dụ kiểm tra dữ liệu **đích** trên PostgreSQL trước khi upsert:

```sql
SELECT customer_code, COUNT(*) AS duplicate_count
FROM customer_tier
GROUP BY customer_code
HAVING COUNT(*) > 1;
```

Nếu `customer_code` đã là primary key như ví dụ ở mục 4, database vốn ngăn dữ liệu trùng. Với bảng kế thừa chưa có PK/unique, phải làm sạch và thiết lập ràng buộc phù hợp trước khi dựa vào khóa này để upsert.

Ví dụ kiểm tra các giá trị sai nghiệp vụ trong bảng nguồn tạm, nếu quy trình ETL chọn nạp CSV vào một staging table trước:

```sql
SELECT *
FROM customer_tier_staging
WHERE customer_code IS NULL
   OR credit_limit < 0
   OR tier NOT IN ('BRONZE', 'SILVER', 'GOLD');
```

Đây là **cách kiểm tra tùy chọn khi có bảng staging**, không phải bảng do `loadUpdateData` tự tạo. Nếu migration rất lớn hoặc dữ liệu cần chuẩn hóa phức tạp, tải vào staging và đối chiếu bằng SQL có thể đáng tin cậy hơn thao tác upsert trực tiếp từ CSV.

## 10. `preConditions`: kiểm tra database trước migration

Có thể thêm precondition để bảo đảm bảng và schema mục tiêu tồn tại:

```yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - tableExists:
      tableName: customer_tier
  - columnExists:
      tableName: customer_tier
      columnName: customer_code
```

Đoạn trên là thuộc tính của `changeSet` (không phải một file changelog độc lập). `onFail: HALT` yêu cầu dừng nếu điều kiện không đạt; `onError: HALT` dừng nếu đánh giá điều kiện gặp lỗi.

Precondition có thể kiểm tra metadata DB và các điều kiện SQL, nhưng **không phải trình xác thực CSV đầy đủ**. Chẳng hạn, `tableExists` không phát hiện CSV có hai dòng trùng khóa, không xác minh từng giá trị ngày giờ và không bảo đảm dữ liệu không bị một tiến trình khác thay đổi trong lúc migration chạy.

Trong môi trường có traffic ghi, việc kiểm tra trước rồi cập nhật sau có thể gặp race condition. Ràng buộc `PRIMARY KEY`/`UNIQUE` giúp bảo vệ tính duy nhất, nhưng vẫn cần xem xét transaction, cơ chế khóa và cách ứng dụng xử lý lỗi ghi xung đột.

## 11. Một CSV đã cập nhật không có nghĩa changeset tự chạy lại

Liquibase lưu lịch sử changeset trong bảng `DATABASECHANGELOG`. Với changeset thông thường không có cấu hình chạy lại:

1. Lần `update` đầu: Liquibase xác định changeset chưa được thực thi và chạy `loadUpdateData`.
2. Sau khi chạy thành công: Liquibase ghi metadata định danh changeset cùng checksum và trạng thái.
3. Lần `update` sau: nếu changeset đã được ghi nhận, Liquibase thông thường **không thực thi lại** chỉ vì ứng dụng khởi động hay người dùng lặp lại lệnh.

Đừng coi một CSV theo đường dẫn ổn định như một bảng cấu hình “luôn đồng bộ” với database. **Sửa giá trị trong CSV sau khi changeset đã chạy** có thể làm phát sinh khác biệt kiểm tra checksum hoặc hành vi xử lý khác tùy phiên bản/change type, nhưng tuyệt đối không nên dựa vào đó như một cơ chế phát hành dữ liệu mới.

### Quy tắc khuyến nghị: dữ liệu phát hành bất biến

Ví dụ:

```text
002-upsert-customer-tier.yaml   -> customer-tiers-2026-11.csv
003-upsert-customer-tier.yaml   -> customer-tiers-2026-12.csv
```

Khi cần thay hạng hoặc hạn mức ở tháng tiếp theo, hãy tạo **changeset mới** với `id` mới và một CSV version mới, thay vì sửa nội dung changeset/CSV đã triển khai. Cách này giúp:

- Có lịch sử rõ ràng: phiên bản nào thay đổi dữ liệu nào.
- Kiểm tra diff của từng đợt và review quyền ghi đè.
- Tránh việc môi trường A đã áp dụng CSV cũ nhưng môi trường B lần đầu áp dụng CSV mới dưới cùng định danh changeset.
- Dễ tái hiện lỗi trên database thử nghiệm tương ứng release.

`runOnChange` hoặc `runAlways` có thể làm một changeset chạy lại trong một số trường hợp, nhưng **không phải lựa chọn mặc định** để “tự đồng bộ CSV”. Chúng có thể gây cập nhật lặp, ghi đè điều chỉnh phát sinh ở production và làm khó kiểm toán. Chỉ chọn sau khi hiểu chính xác semantics/checksum của phiên bản Liquibase đang dùng và đã thử đầy đủ.

## 12. Rollback và bảo toàn dữ liệu trước khi upsert

Đây là phần quan trọng nhất để tránh mất dữ liệu. `loadUpdateData` có thể vừa **chèn hàng mới** vừa **ghi đè giá trị của hàng cũ**. Liquibase không thể suy ra từ CSV mới rằng trước đó `C001` mang `tier = BRONZE`, `credit_limit = 10000.00` và ghi chú gì, nếu bạn không lưu snapshot/giá trị cũ.

Vì vậy **không mặc định có rollback tự động khôi phục đầy đủ** cho một migration kiểu này. Một rollback chỉ xóa các mã có trong CSV là **sai** nếu có mã đã tồn tại trước khi chạy: nó sẽ xóa cả hàng thật thay vì chỉ gỡ hàng mới được chèn.

### 12.1. Phân biệt ba loại tác động

| Tác động của `loadUpdateData` | Muốn đảo ngược cần gì? |
|---|---|
| Update `C001` đã tồn tại | Giá trị cũ của **từng cột bị thay đổi**, theo đúng khóa |
| Insert `C003` chưa tồn tại | Danh sách chính xác **những hàng mới chèn** trong lần chạy |
| `C002` không xuất hiện trong CSV | Không có thay đổi để rollback |

Ví dụ nếu biết chắc snapshot ngay trước migration có `C001` là `BRONZE` và `10000.00`, có thể thiết kế một rollback phục hồi `C001` và xóa riêng `C003` trên **database thử nghiệm với trạng thái đã được cố định**:

```sql
-- Minh họa tư duy rollback, KHÔNG tự động áp dụng trên production
UPDATE customer_tier
SET tier = 'BRONZE',
    credit_limit = 10000.00,
    active = TRUE,
    note = 'Giá trị cũ'
WHERE customer_code = 'C001';

DELETE FROM customer_tier
WHERE customer_code = 'C003';
```

Trong thực tế, script trên chỉ an toàn nếu xác minh `C003` thật sự được **insert** bởi migration này, không có quan hệ tham chiếu phát sinh sau đó và `C001` không được cập nhật hợp lệ bởi ứng dụng sau khi migration chạy. Khi dữ liệu đã tiếp tục biến động, rollback tự động có thể làm mất thay đổi hợp lệ.

### 12.2. Phương án phục hồi có kiểm soát

Một quy trình production tốt hơn thường gồm:

1. Trước chạy: ghi snapshot các hàng đích theo khóa CSV, phân biệt hàng đã có với khóa chưa tồn tại; bảo vệ snapshot bằng phân quyền và thời hạn lưu trữ phù hợp.
2. Chốt thời điểm và quyền ghi: nếu có traffic đồng thời, xác định phương án khóa/bảo trì hoặc thiết kế thao tác không phá dữ liệu.
3. Thực thi trên bản sao database tương đương, thử cả xử lý lỗi giữa chừng và thủ tục khôi phục.
4. Sau chạy: ghi nhận số hàng insert/update, đối chiếu giá trị và metadata `DATABASECHANGELOG`.
5. Khi cần phục hồi: quyết định rollback hoặc **forward-fix** bằng changeset mới dựa trên dữ liệu đã thay đổi sau deploy.

Với thay đổi có thể phá dữ liệu hoặc không đảo ngược đầy đủ, cần nói rõ giới hạn trong review và release notes. `rollbackCount` hay `rollbackToDate` không phải phép màu để tìm lại dữ liệu cũ đã bị ghi đè.

## 13. Transaction, hiệu năng và cạnh tranh ghi

CSV vài chục hàng dữ liệu tham chiếu khác nhiều so với CSV hàng triệu bản ghi. Những yếu tố cần đo:

- **Số hàng × số lần đối sánh**: nếu thiếu index trên khóa đối sánh, quá trình tìm hàng có thể chậm đáng kể.
- **Hỗ trợ transaction của DBMS**: cần xem cách Liquibase/driver thực thi câu lệnh và khả năng rollback khi lỗi giữa chừng.
- **Khóa và tải ghi**: update trên bảng nhiều traffic có thể tranh row lock, tăng latency hoặc deadlock.
- **WAL/redo log và replication**: cập nhật hàng loạt có thể gây log lớn và replication lag.
- **Cột có trigger/default/updated_at**: mỗi update có thể kích hoạt trigger hoặc audit; phải kiểm tra tác động ngoài những cột CSV trực tiếp.
- **Kiểu dữ liệu và index**: thay đổi các cột có index/foreign key/unique constraint thường tốn chi phí hơn.
- **Khả năng retry**: khi job lỗi, xem trạng thái transaction và lịch sử Liquibase trước khi chạy lại.

Đối với thay đổi dữ liệu lớn, cân nhắc quy trình staging table, nạp bulk theo công cụ DBMS rồi chạy `UPDATE`/`INSERT` dựa trên join đã kiểm chứng và chia lô. `loadUpdateData` thích hợp khi bản ghi có khóa rõ ràng và khối lượng nằm trong giới hạn có thể kiểm soát; không mặc định nó là phương án nhanh nhất cho mọi cỡ dữ liệu.

## 14. Chạy thử có kiểm chứng với CLI

Giả sử bạn đã khai báo kết nối JDBC, driver và changelog gốc trong `liquibase.properties`. Trên **database thử nghiệm**, thực hiện:

**Bước 1 — Chuẩn bị schema:** chỉ chạy changeset tạo bảng `001` và chuẩn bị hai hàng `C001`, `C002`. Với ví dụ master ở mục 3, có thể triển khai `001` trong một lượt riêng trước khi thêm `002` vào changelog master của bài tập.

**Bước 2 — Kiểm tra changelog:**

```bash
liquibase --defaults-file=liquibase.properties validate
```

**Bước 3 — Kiểm tra pending changesets:**

```bash
liquibase --defaults-file=liquibase.properties status
```

**Bước 4 — Xem SQL dự kiến:**

```bash
liquibase --defaults-file=liquibase.properties update-sql
```

Xem việc đối sánh khóa, cập nhật và chèn của `loadUpdateData` trong SQL preview nếu phiên bản và phương thức thực thi hỗ trợ thể hiện chi tiết. Không dùng preview như bằng chứng duy nhất cho giá trị cuối cùng: database thực tế vẫn phải được kiểm thử.

**Bước 5 — Thực thi khi đúng mục tiêu:**

```bash
liquibase --defaults-file=liquibase.properties update
```

**Bước 6 — Đối chiếu dữ liệu:**

```sql
SELECT customer_code, tier, credit_limit, active, note
FROM customer_tier
ORDER BY customer_code;
```

Kỳ vọng `C001` đổi sang `GOLD`, `C003` được tạo mới và `C002` giữ nguyên. Sau đó truy vấn lịch sử:

```sql
SELECT id, author, filename, exectype, md5sum, dateexecuted
FROM databasechangelog
WHERE id = '002-upsert-customer-tier-2026-11';
```

Tên bảng/cột metadata viết thường trong truy vấn chỉ là ví dụ phù hợp với quy tắc identifier không quote của PostgreSQL; với các DBMS khác, hãy dùng đúng schema và cách phân giải tên. Khi changeset được ghi nhận thành công, chạy `update` lần nữa phải xác minh không có thay đổi pending tương ứng. **Đừng sửa CSV chỉ để kích hoạt lại changeset.**

### 14.1. Các phép thử dữ liệu nên có

- Sửa giá trị của một khóa đã tồn tại → quan sát nhánh update.
- Thêm một khóa chưa tồn tại → quan sát nhánh insert.
- Bỏ một khóa khỏi CSV → xác minh hàng đó **không bị xóa**.
- Hai dòng CSV trùng `customer_code` → công cụ kiểm định nguồn phải chặn trước deploy.
- Thử giá trị UTF-8 có dấu phẩy và dấu nháy → kiểm tra parser giữ đúng nội dung.
- Thử mã có số 0 đầu và chuỗi trông như số → xác nhận được lưu như văn bản.
- Thử số vượt precision/scale, boolean sai, chuỗi quá dài → migration phải bị phát hiện lỗi thích hợp.
- Thử CSV rỗng, file không tồn tại và header sai → nắm rõ thông báo lỗi và trạng thái DB sau khi job dừng.
- Thử đối sánh khi khác hoa/thường, có khoảng trắng → kiểm tra collation và chính sách khóa.
- Thử chạy lại cùng changelog → xác nhận `DATABASECHANGELOG` ngăn thực thi lặp thông thường.

## 15. Chạy qua Spring Boot và CI/CD

Trong Spring Boot, cấu hình root changelog thông dụng:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/master.yaml
```

Khi build artifact, cần có ít nhất:

```text
BOOT-INF/classes/db/changelog/master.yaml
BOOT-INF/classes/db/changelog/changes/001-create-customer-tier.yaml
BOOT-INF/classes/db/changelog/changes/002-upsert-customer-tier.yaml
BOOT-INF/classes/db/changelog/data/customer-tiers-2026-11.csv
```

Đây là vị trí thường gặp trong executable Spring Boot JAR; JAR thư viện thông thường có cấu trúc khác. Nếu YAML được copy nhưng CSV bị exclude khỏi package, runtime sẽ không tìm thấy file dữ liệu. Kiểm tra resource trong **artifact đã đóng gói**, không chỉ chạy trong IDE.

Với CI/CD, nên tổ chức pipeline:

```text
Commit changelog + CSV bất biến
       |
       v
Review CSV: header, khóa, kiểu, giá trị, độ nhạy cảm
       |
       v
Build artifact + kiểm tra YAML/CSV có trong package
       |
       v
Validate + status + SQL preview trên database tương đương
       |
       v
Approval, snapshot, xác minh DB URL/schema/credentials
       |
       v
Update -> kiểm tra dữ liệu và DATABASECHANGELOG
```

Các môi trường nên dùng **cùng một bản changelog và CSV đã được review**. Khác biệt môi trường chủ yếu nằm ở JDBC URL/schema, tài khoản và secret. Nếu chỉ muốn dữ liệu seed chạy trong một số môi trường, có thể đặt `contextFilter` hoặc label có chủ đích trên changeset, nhưng cần hiểu rõ semantics bộ lọc; filter không phải cơ chế bảo mật. Không vô tình nạp dữ liệu demo hoặc thông tin giả vào production.

Nếu pipeline đã có job chạy Liquibase trước khi deploy, cần quyết định Spring Boot có còn tự chạy migration khi khởi động hay không. Tránh hai tiến trình sử dụng hai tập changelog/CSV khác nhau trên cùng database; cơ chế lock không giải quyết sự thiếu đồng nhất của artifacts.

## 16. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách khắc phục |
|---|---|---|
| `CSV file not found` | Sai đường dẫn tương đối, file không được copy vào classpath/JAR | Xác minh vị trí changelog con và `relativeToChangelogFile`, kiểm tra artifact |
| Header không được nhận diện | BOM, sai chữ hoa, khoảng trắng hoặc header thay đổi | Chốt schema CSV; kiểm tra `header`/`name` và mã hóa |
| Số/ngày/boolean không parse được | Locale, sai định dạng hoặc cấu hình `type` | Chuẩn hóa giá trị, test cột theo DBMS và phiên bản Liquibase |
| Thay vì update lại tạo thêm hàng | Khóa đối sánh không ổn định, dữ liệu không unique, collation/whitespace khác | Kiểm tra `primaryKey`, ràng buộc và các giá trị khóa nguồn/đích |
| Không có hàng mới được chèn | Bật chế độ chỉ cập nhật (nếu hỗ trợ) hoặc changeset không chạy | Kiểm tra `onlyUpdate`, `status`, context và lịch sử |
| Hàng không có trong CSV vẫn còn | Đúng thiết kế: upsert không xóa hàng vắng mặt | Thiết kế thao tác dọn riêng nếu nghiệp vụ thực sự yêu cầu |
| Dữ liệu cũ bị ghi đè ngoài ý muốn | CSV chứa cột không nên quản lý, ô rỗng bị diễn giải sai | Xem lại hợp đồng dữ liệu và phạm vi các cột được phép update |
| Thay CSV nhưng database không đổi | Changeset đã được ghi lịch sử và không chạy lại | Tạo changeset/CSV mới cho release tiếp theo |
| Checksum validation lỗi | Chỉnh sửa changeset/nguồn đã triển khai hoặc định danh khác | So sánh version cũ, giữ tính bất biến và phân tích lịch sử |
| Upsert quá chậm hoặc gây lock | Nhiều hàng, thiếu index trên khóa, tải ghi cao | Đo khối lượng và cân nhắc staging/bulk SQL |
| Không rollback lại giá trị cũ | Không có snapshot các hàng trước khi cập nhật | Lập kế hoạch snapshot/forward-fix trước triển khai |
| Chạy tốt local nhưng lỗi Spring Boot JAR | CSV bị exclude khỏi resources hoặc đường dẫn khác | Kiểm tra chính artifact cuối cùng và ResourceAccessor |

## 17. Bài thực hành tổng hợp

Trên database mới có thể tạo lại, hãy triển khai tuần tự:

1. Tạo bảng `customer_tier` bằng `001-create-customer-tier.yaml`.
2. Chèn hai hàng thử `C001`, `C002` như mục 4.
3. Lưu file CSV trong mục 2 với hàng `C001` cần sửa và hàng `C003` chưa tồn tại.
4. Viết changeset `002` đúng như mục 5; xác minh đường dẫn `../data/...` và mapping header/`type`.
5. Chạy `validate`, `status`, `update-sql` và review dữ liệu dự kiến bị ghi đè.
6. Chạy `update`; dùng `SELECT` xác nhận hai nhánh update/insert và hàng `C002` giữ nguyên.
7. Chạy lại `update`; quan sát changeset không tự chạy lần nữa nhờ lịch sử Liquibase.
8. Tạo một CSV thử có hai dòng trùng `customer_code`, một ô số dùng dấu phẩy thập phân, và một mã bắt đầu bằng số 0; xây dựng bước validation phát hiện trước khi cập nhật.
9. Trên bản sao database, lập snapshot trước upsert và diễn tập khôi phục giá trị hàng cũ mà không xóa hàng vốn đã tồn tại.
10. Tạo **changeset mới** cho một đợt dữ liệu tiếp theo, giữ nguyên file CSV và changeset đã triển khai.

### Checklist trước khi merge hoặc phát hành

- [ ] `loadUpdateData` được chọn đúng mục đích; biết rõ nó **update/insert**, không tự xóa hàng vắng trong CSV.
- [ ] `primaryKey` đối sánh ổn định, không trùng hoặc null, có ràng buộc phù hợp trên DB.
- [ ] CSV có header nhất quán, UTF-8, delimiter và quotchar chính xác.
- [ ] Kiểu `STRING`/`NUMERIC`/`BOOLEAN`/ngày giờ được kiểm tra trên DBMS đích.
- [ ] Đã kiểm tra mã có số 0 đầu, dấu phẩy trong chuỗi, giá trị rỗng và `NULL`.
- [ ] Đã có quy tắc rõ cho các cột có thể bị ghi đè từ CSV.
- [ ] Dữ liệu nguồn được kiểm định, không chứa thông tin nhạy cảm không được phép commit.
- [ ] Đã xem cấu trúc directory và xác minh CSV nằm trong artifact runtime.
- [ ] `validate`, `status`, `update-sql` và thử trên database tương đương đã đạt.
- [ ] Đã dự liệu xung đột ghi, hiệu năng, index, transaction và khối lượng log.
- [ ] Đã có snapshot/rollback hoặc kế hoạch forward-fix cho cả hàng insert lẫn update.
- [ ] Changeset/CSV đã triển khai được giữ bất biến; mỗi lần đổi dữ liệu có lịch sử mới.
- [ ] Đã xác nhận JDBC URL/schema, phân quyền và một điểm chịu trách nhiệm chạy migration trong CI/CD/Spring Boot.

**Kết luận:** `loadUpdateData` là cách hiệu quả để cập nhật dữ liệu tham chiếu từ CSV khi mỗi hàng có khóa đối sánh ổn định và dữ liệu được kiểm tra trước. Tuy nhiên, một upsert an toàn cần nhiều hơn cú pháp YAML: phải bảo vệ dữ liệu đang có, phân biệt cập nhật và chèn, chuẩn hóa kiểu, giữ CSV và changeset theo phiên bản, thử SQL trên DBMS thật và chuẩn bị phương án phục hồi. Khi kết hợp các nguyên tắc đó với precondition, checksum và lịch sử `DATABASECHANGELOG`, việc chuyển đổi dữ liệu bằng `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` có thể được review, kiểm chứng và triển khai nhất quán qua local, Spring Boot và CI/CD.
