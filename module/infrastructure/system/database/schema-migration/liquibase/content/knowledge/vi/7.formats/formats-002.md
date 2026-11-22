# Viết changelog YAML và tránh lỗi kiểu dữ liệu, thụt dòng

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Changelog YAML là một cách phổ biến để mô tả những thay đổi đó. YAML dễ đọc nhưng **thụt dòng, dấu gạch đầu dòng và cách biểu diễn giá trị đều có ý nghĩa**: một dòng đặt sai cấp có thể khiến Liquibase không đọc được file, hiểu sai nội dung changeset hoặc sinh SQL ngoài dự kiến.

Bài này đi từ cấu trúc YAML hợp lệ, cách Liquibase diễn giải kiểu dữ liệu, các lỗi thụt dòng thường gặp đến quy trình kiểm chứng trước khi áp dụng migration. Các ví dụ minh họa chủ yếu dùng PostgreSQL; với hệ quản trị khác, cần đối chiếu khả năng hỗ trợ kiểu dữ liệu và SQL được sinh ra.

## 1. Phân biệt ba lớp kiểm tra

Một changelog có thể hợp lệ ở lớp này nhưng sai ở lớp khác:

| Lớp | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| **Cú pháp YAML** | File có được phân tích thành mapping, sequence và scalar hợp lệ không? | Thiếu thụt dòng, dùng tab để thụt, dấu `:` không đúng chỗ |
| **Cấu trúc Liquibase** | Các phần tử YAML có đúng `databaseChangeLog`, `changeSet`, `changes`, `columns` và thuộc tính change type không? | Dùng `changeSets` thay `changeSet`, đặt `tableName` sai cấp |
| **Ngữ nghĩa database** | SQL được tạo có phù hợp DBMS, schema và dữ liệu thực tế không? | Kiểu dữ liệu không được hỗ trợ, tạo bảng đã tồn tại, vi phạm khóa ngoại |

Một YAML parser thông thường có thể xác nhận cú pháp mà không biết quy tắc Liquibase. Ngược lại, `liquibase validate` giúp phát hiện nhiều lỗi cấu trúc và lịch sử changeset nhưng không thay thế bước xem SQL và kiểm thử trên database tương đương đích.

## 2. Hiểu cấu trúc cơ bản của một changelog YAML

Trong YAML:

- **Mapping** là tập cặp `khóa: giá trị`, ví dụ `tableName: customer`.
- **Sequence** là danh sách mà mỗi phần tử thường bắt đầu bằng `-`, ví dụ danh sách changeset hoặc danh sách cột.
- **Scalar** là một giá trị đơn, như chuỗi, số, boolean hoặc `null`.
- **Thụt dòng** cho biết phần tử nào thuộc phần tử cha. YAML dùng khoảng trắng; không dùng ký tự tab để thụt dòng.

Cây cấu trúc thường gặp của Liquibase:

```text
databaseChangeLog                     (mapping gốc)
└── - changeSet                        (một phần tử trong danh sách)
    ├── id                             (định danh changeset)
    ├── author                         (người/tập thể tạo)
    ├── preConditions                  (điều kiện trước khi thực thi, nếu có)
    ├── changes                        (danh sách thay đổi)
    │   └── - createTable              (một change type)
    │       ├── tableName
    │       └── columns                (danh sách cột)
    │           └── - column
    │               ├── name
    │               ├── type
    │               └── constraints
    └── rollback                       (các bước đảo ngược, nếu có)
```

Không phải mọi thay đổi đều cần `columns`; cấu trúc bên trong `changes` phụ thuộc vào change type. Tên khóa Liquibase phải viết đúng chữ hoa/chữ thường theo tài liệu, chẳng hạn `databaseChangeLog`, `changeSet`, `createTable`, `tableName`, `autoIncrement`, `defaultValueBoolean`.

## 3. Changelog mẫu hoàn chỉnh: tạo bảng và dữ liệu ban đầu

Giả sử ta cần bảng `app_customer` có mã tự tăng, email, trạng thái hoạt động và thời điểm tạo. Lưu nội dung sau vào `db/changelog/001-create-customer.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-customer"
      author: "database-team"
      comment: "Tạo bảng khách hàng cho ví dụ Liquibase"
      preConditions:
        - onFail: HALT
        - not:
            - tableExists:
                tableName: app_customer
      changes:
        - createTable:
            tableName: app_customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: active
                  type: BOOLEAN
                  defaultValueBoolean: true
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  defaultValueComputed: CURRENT_TIMESTAMP
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: app_customer
```

Điều cần nhận ra trong ví dụ:

1. `databaseChangeLog:` là khóa gốc, giá trị của nó là một **danh sách**. Dấu `-` trước `changeSet` mở đầu một phần tử danh sách đó.
2. `id` và `author` nằm **bên trong** `changeSet`. Chúng cùng đường dẫn changelog góp phần xác định changeset trong `DATABASECHANGELOG`.
3. `preConditions` là danh sách các điều kiện. `not` phủ định kết quả `tableExists`; `onFail: HALT` yêu cầu dừng nếu điều kiện không đạt.
4. `changes` là danh sách các change type. Ở đây chỉ có một `createTable`, nhưng có thể có nhiều thay đổi và Liquibase sẽ xử lý theo thứ tự được khai báo.
5. `columns` là danh sách các phần tử `column`. `constraints` là mapping thuộc **từng cột**, không thuộc `createTable` nói chung.
6. `autoIncrement`, `primaryKey`, `nullable`, `unique` và `defaultValueBoolean` là các thuộc tính có ý nghĩa kiểu dữ liệu; chúng cần giá trị boolean phù hợp.
7. `rollback` của ví dụ xóa cả bảng. Chỉ thực hành rollback này trên database thử nghiệm vì dữ liệu trong bảng sẽ bị mất.

Ví dụ sử dụng những change type chung nhưng SQL cụ thể của `autoIncrement`, kiểu `BOOLEAN`, `TIMESTAMP` và `CURRENT_TIMESTAMP` vẫn phụ thuộc DBMS. Cần xem `update-sql` và kiểm thử trên đúng hệ quản trị, phiên bản máy chủ và phiên bản Liquibase đang dùng.

## 4. Quy tắc thụt dòng và dấu `-`

Để bài dễ đọc, nên thống nhất **hai khoảng trắng cho một cấp** trong toàn bộ changelog. YAML cho phép các mức thụt hợp lệ khác nhau, nhưng sử dụng một quy ước nhất quán giúp tránh lỗi. Dấu tab không phải ký tự thụt dòng hợp lệ theo cách dùng YAML thông thường.

### 4.1. Mapping thuộc cấp cha nào?

**Sai:** `columns` bị đặt cùng cấp với `createTable` thay vì là thuộc tính của `createTable`:

```yaml
changes:
  - createTable:
      tableName: app_customer
    columns:
      - column:
          name: id
          type: BIGINT
```

**Đúng:** `columns` và `tableName` cùng là thuộc tính của `createTable`:

```yaml
changes:
  - createTable:
      tableName: app_customer
      columns:
        - column:
            name: id
            type: BIGINT
```

Ở ví dụ sai, trình phân tích YAML vẫn có thể tạo ra một mapping hợp lệ, nhưng Liquibase nhìn thấy `columns` ở vị trí không mong đợi. Vì vậy cần phân biệt lỗi **cú pháp YAML** và lỗi **cấu trúc Liquibase**.

### 4.2. Danh sách luôn cần dấu gạch đầu dòng

**Sai:** Hai phần tử `column` không được khai báo thành danh sách:

```yaml
columns:
  column:
    name: id
    type: BIGINT
  column:
    name: email
    type: VARCHAR(255)
```

Đây còn là ví dụ về **khóa trùng nhau** trong một mapping. Tùy YAML parser, file có thể bị từ chối hoặc một khóa che mất khóa kia. Không dựa vào hành vi ghi đè khóa trùng.

**Đúng:**

```yaml
columns:
  - column:
      name: id
      type: BIGINT
  - column:
      name: email
      type: VARCHAR(255)
```

Tương tự, một changelog chứa nhiều changeset cần nhiều phần tử `- changeSet:` và một changeset có nhiều thay đổi cần nhiều phần tử dưới `changes:`.

### 4.3. Dấu `-` mở một phần tử mới, không phải trang trí

**Sai:** Đặt `author` thành một phần tử khác thay vì thuộc tính của cùng changeset:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-customer"
  - author: "database-team"
```

**Đúng:**

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-customer"
      author: "database-team"
```

Nếu không chắc đang ở cấp nào, hãy hình dung giá trị sau khóa là mapping hay sequence. Ví dụ `changes` chứa danh sách, nên bắt buộc có dấu `-` trước mỗi `createTable`, `addColumn`, `insert` hoặc change type khác.

## 5. YAML scalar: chuỗi, số, boolean, null và ngày giờ

YAML không xem mọi thứ sau dấu `:` là chuỗi. Một số giá trị không được đặt trong dấu nháy có thể được parser suy luận thành số, boolean, null hoặc timestamp. Quy tắc suy luận còn phụ thuộc phiên bản YAML và thư viện parser mà Liquibase sử dụng. Vì vậy cần **chủ động biểu diễn kiểu giá trị**.

| Dữ liệu cần biểu diễn | Ví dụ nên dùng | Vì sao |
|---|---|---|
| Mã changeset | `id: "001-create-customer"` | Giữ `id` là chuỗi, bảo toàn số 0 đầu và định dạng mong muốn |
| Tác giả | `author: "database-team"` | Tường minh kiểu chuỗi |
| Văn bản có dấu `:` | `comment: "Lý do: tạo bảng"` | Tránh dấu `:` kèm khoảng trắng bị hiểu như ranh giới khóa/giá trị |
| Chuỗi giống boolean | `value: "false"` | Khi cột thực sự là chuỗi, giữ nguyên chữ `false` |
| Thuộc tính boolean | `autoIncrement: true`, `nullable: false` | Giao đúng giá trị boolean cho thuộc tính Liquibase |
| Số nguyên | `valueNumeric: 42` | Dùng thuộc tính Liquibase dành cho giá trị số |
| Số thập phân cần giữ định dạng | `valueNumeric: "19.90"` | Giữ biểu diễn thập phân ở tầng YAML rồi để Liquibase xử lý kiểu numeric |
| Ngày giờ | `valueDate: "2026-11-19T09:30:00"` | Tránh để YAML tự suy luận timestamp khi mục tiêu là giá trị gửi cho Liquibase |
| Chuỗi có ký tự `#` đầu tiên | `value: "#pending"` | Tránh `#` bị hiểu là comment |
| Chuỗi có số 0 đầu | `value: "000123"` | Không đánh mất số 0 trong mã định danh nghiệp vụ |

YAML 1.1 và 1.2 có khác biệt về một số chuỗi đặc biệt như `yes`, `no`, `on`, `off`. Không nên đưa các từ này dưới dạng bare scalar khi cần chúng là chuỗi. Đặt trong dấu nháy để giảm phụ thuộc vào parser. `true`/`false` cho thuộc tính boolean nên dùng dạng boolean rõ ràng như trong ví dụ đã trình bày.

Một trường hợp khác: `null`, `~` và giá trị rỗng có thể mang nghĩa null ở tầng YAML. Chúng không nhất thiết tương đương với chuỗi văn bản `"null"` hay lệnh SQL `NULL`. Khi cập nhật dữ liệu về SQL `NULL`, phải kiểm tra change type và thuộc tính Liquibase hỗ trợ thay vì thử thay `value: null` một cách cảm tính.

### 5.1. `id` là mã định danh, không phải phép tính

Nên viết:

```yaml
id: "2026-11-19-add-email"
author: "db-team"
```

Đừng dùng giá trị không nháy có hình dạng ngày (`2026-11-19`), số 0 đầu (`001`), số ở dạng mũ (`1e3`) rồi trông đợi YAML giữ chính xác văn bản gốc. Thói quen đặt dấu nháy cho `id`, `author`, label hoặc mã nghiệp vụ giúp giảm sự khác biệt giữa các parser.

### 5.2. Đừng nhầm `type` của cột với kiểu scalar của YAML

```yaml
- column:
    name: amount
    type: DECIMAL(19, 4)
```

`type` ở đây là thuộc tính của Liquibase mô tả kiểu cột database. Giá trị `DECIMAL(19, 4)` được đưa cho Liquibase xử lý và ánh xạ sang DBMS; nó không có nghĩa YAML đang lưu một số thập phân. Có thể đặt `type: "DECIMAL(19,4)"` để diễn đạt rõ kiểu chuỗi. Việc DBMS có hỗ trợ kiểu này hay không là một bước xác minh riêng.

Một cột `VARCHAR(12)` có thể chứa chuỗi `"000123"`, nhưng nếu bạn đưa giá trị đó qua thuộc tính numeric hoặc để YAML tự biến nó thành số, dữ liệu có thể mất số 0 đầu trước khi vào database.

## 6. Phân biệt thuộc tính nhận dữ liệu và thuộc tính tạo mặc định

Liquibase cung cấp những thuộc tính biểu diễn các loại giá trị khác nhau trong `column`. Ý nghĩa của thuộc tính còn phụ thuộc change type như `createTable`, `addColumn`, `insert` hoặc `update`:

| Thuộc tính | Ý nghĩa thường gặp | Lưu ý |
|---|---|---|
| `value` | Giá trị chuỗi được ghi cho cột | Dùng dấu nháy khi chuỗi trông giống số, boolean hoặc ký tự đặc biệt |
| `valueNumeric` | Giá trị số cần ghi | Không dùng cho mã có số 0 đầu; cần phù hợp precision/scale của cột |
| `valueBoolean` | Giá trị boolean cần ghi | Dùng `true` hoặc `false`; xác minh kiểu boolean theo DBMS |
| `valueDate` | Giá trị ngày hoặc thời điểm | Đặt chuỗi định dạng rõ ràng, kiểm tra timezone và kiểu cột đích |
| `valueComputed` | Biểu thức do database tính | Là biểu thức SQL, cần tương thích DBMS |
| `defaultValue` | Giá trị mặc định dạng chuỗi khi tạo/sửa cột | Áp dụng cho các hàng mới theo hành vi của DBMS |
| `defaultValueNumeric` | Giá trị mặc định số | Đặt theo kiểu số mong muốn |
| `defaultValueBoolean` | Giá trị mặc định boolean | Viết `true`/`false`, không nhầm với chuỗi `"true"` |
| `defaultValueDate` | Giá trị mặc định ngày/giờ | Cần xác minh khả năng của change type và DBMS |
| `defaultValueComputed` | Biểu thức mặc định tính tại database | Ví dụ `CURRENT_TIMESTAMP`; không tương đương với chuỗi chữ đó |

Ví dụ tạo bảng có mặc định boolean:

```yaml
- createTable:
    tableName: feature_flag
    columns:
      - column:
          name: flag_key
          type: VARCHAR(80)
          constraints:
            primaryKey: true
            nullable: false
      - column:
          name: enabled
          type: BOOLEAN
          defaultValueBoolean: false
          constraints:
            nullable: false
```

Ví dụ chèn một bản ghi trong changeset tiếp theo:

```yaml
- changeSet:
    id: "002-add-flag"
    author: "database-team"
    changes:
      - insert:
          tableName: feature_flag
          columns:
            - column:
                name: flag_key
                value: "NEW_CHECKOUT"
            - column:
                name: enabled
                valueBoolean: true
    rollback:
      - delete:
          tableName: feature_flag
          where: "flag_key = 'NEW_CHECKOUT'"
```

Đoạn thứ hai là một phần tử `changeSet` cần đặt **dưới danh sách `databaseChangeLog`**. Không đặt trực tiếp `- changeSet` ở gốc file nếu thiếu `databaseChangeLog:`. `defaultValueBoolean: false` mô tả mặc định của cột; `valueBoolean: true` mô tả giá trị cụ thể được ghi khi `insert` — hai mục đích khác nhau.

`rollback` dùng `delete` với điều kiện cụ thể để xóa đúng dữ liệu mẫu. Trên database dùng chung, nên cân nhắc khả năng hàng đã được ứng dụng sử dụng hoặc thay đổi sau triển khai trước khi thiết kế rollback dữ liệu; một thao tác đảo ngược về mặt kỹ thuật không bảo đảm an toàn về nghiệp vụ.

## 7. Các ký tự đặc biệt dễ làm thay đổi ý nghĩa YAML

Khi một giá trị chứa `:`, `#`, `{}`, `[]`, dấu nháy, xuống dòng hoặc ký tự mang nghĩa trong YAML, hãy cân nhắc đặt nó trong dấu nháy hoặc dùng block scalar. Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: "003-seed-status"
      author: "db-team"
      comment: "Trạng thái: khởi tạo dữ liệu, mã #003"
      changes:
        - insert:
            tableName: feature_flag
            columns:
              - column:
                  name: flag_key
                  value: "#beta:2026"
              - column:
                  name: enabled
                  valueBoolean: false
      rollback:
        - delete:
            tableName: feature_flag
            where: "flag_key = '#beta:2026'"
```

Dấu `#` mở comment khi ở vị trí phù hợp theo cú pháp YAML. Một chuỗi như `"Mã: 007"` cần được giữ nguyên thay vì để `: ` bị diễn giải như phần của mapping. Không có lý do gì để bỏ dấu nháy ở các chuỗi nghiệp vụ chỉ để giảm vài ký tự.

### 7.1. SQL nhiều dòng: ưu tiên `|` hoặc `|-`

Khi cần SQL đặc thù PostgreSQL, có thể viết:

```yaml
databaseChangeLog:
  - changeSet:
      id: "004-normalize-email"
      author: "database-team"
      dbms: postgresql
      changes:
        - sql:
            sql: |-
              UPDATE app_customer
              SET email = LOWER(email)
              WHERE email IS NOT NULL;
```

`|-` giữ nguyên các xuống dòng bên trong và loại bỏ ký tự xuống dòng cuối khối. Dấu `|` giữ xuống dòng cuối; dạng `>` có thể gộp các xuống dòng thành khoảng trắng, vì thế không nên chọn `>` nếu SQL phụ thuộc ranh giới dòng, comment dạng `--` hoặc cú pháp nhiều câu lệnh. Hãy kiểm tra cách Liquibase tách statement (`splitStatements`) và delimiter theo DBMS nếu SQL phức tạp.

Ví dụ trên cố ý chưa khai báo `rollback`: việc chuyển email thành chữ thường không có thao tác đảo ngược tổng quát vì không thể suy ra cách viết hoa ban đầu. Chỉ chạy trên database thử nghiệm có thể khôi phục. Trong hệ thống thật, cần phương án backup hoặc migration bù, và phải đánh giá nguy cơ hai địa chỉ email khác nhau trước đó trở thành trùng nhau khi chuẩn hóa.

### 7.2. Dấu nháy trong chuỗi

YAML có hai cách thông dụng để biểu diễn chuỗi:

```yaml
comment: "Chuỗi chứa dấu nháy đơn: 'ready'"
comment: 'Chuỗi chứa dấu nháy kép: "ready"'
```

Đây là **hai ví dụ riêng**, không phải hai khóa `comment` được đặt cạnh nhau trong cùng một mapping. Nếu dùng nháy đơn ở ngoài và muốn có dấu nháy đơn bên trong, viết hai dấu nháy đơn liên tiếp để escape. Với nháy kép ở ngoài, ký tự `\` tham gia escape và cần được xử lý đúng. Đặc biệt cẩn thận với đường dẫn Windows có dấu `\`; trong changelog tài nguyên, ưu tiên dấu `/`.

## 8. `include`, biến tham số và lỗi kiểu dữ liệu giữa các file

Một changelog lớn thường chia thành nhiều file để review và theo dõi lịch sử:

```yaml
databaseChangeLog:
  - include:
      file: "changes/001-create-customer.yaml"
      relativeToChangelogFile: true
  - include:
      file: "changes/002-add-feature-flag.yaml"
      relativeToChangelogFile: true
```

Thuộc tính `relativeToChangelogFile: true` giúp các đường dẫn trong ví dụ được tính từ thư mục chứa changelog cha, giảm phụ thuộc working directory khi chạy CLI hoặc đóng gói Spring Boot. Mỗi file được include vẫn cần một cấu trúc `databaseChangeLog:` hợp lệ; không thể đặt trần `- changeSet` trong một file changelog độc lập.

Với giá trị khác nhau theo môi trường, có thể dùng tham số Liquibase thay vì tạo nhiều bản changelog khác nhau:

```yaml
databaseChangeLog:
  - changeSet:
      id: "005-create-audit-table"
      author: "database-team"
      changes:
        - createTable:
            schemaName: "${appSchema}"
            tableName: app_audit
            columns:
              - column:
                  name: audit_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
      rollback:
        - dropTable:
            schemaName: "${appSchema}"
            tableName: app_audit
```

Trong ví dụ, `${appSchema}` là **tham số Liquibase được cung cấp từ cấu hình triển khai**, không phải phép thay thế biến do YAML tự thực hiện. Đưa tham số vào cả chiều `changes` và `rollback` để hai thao tác dùng cùng schema. Nếu giá trị tham số thiếu hoặc không hợp lệ, migration có thể chạy sai schema hoặc thất bại; kiểm tra giá trị đã phân giải trước khi triển khai. Không dùng chuỗi SQL động nhận trực tiếp giá trị không được kiểm soát cho tên schema, tên bảng hoặc biểu thức SQL.

`includeAll` cũng là lựa chọn khi muốn Liquibase tự tìm các file trong một thư mục. Khi dùng cách này, phải quy ước tên và kiểm tra thứ tự nạp, bảo đảm không vô tình đưa file tạm vào artifact. Các changeset đã chạy phải giữ nguyên `id`, `author` và đường dẫn định danh; chuyển file giữa các thư mục có thể ảnh hưởng cách Liquibase nhận diện lịch sử. Nếu cần thay đổi layout, xem xét `logicalFilePath` và đối chiếu cột `FILENAME` của bảng `DATABASECHANGELOG` trước khi chuyển.

## 9. Những lỗi chỉ lộ ra khi chạy trên database

YAML đúng cú pháp vẫn có thể tạo ra migration sai. Một số trường hợp tiêu biểu:

| Trường hợp | Hệ quả | Cách phòng tránh |
|---|---|---|
| `type: VARCHAR(10)` nhưng dữ liệu dài hơn | Vi phạm giới hạn cột hoặc cắt dữ liệu tùy DBMS | Kiểm tra độ dài dữ liệu thật và SQL sinh ra |
| `nullable: false` trên cột mới của bảng đã có dữ liệu | Migration có thể thất bại vì hàng cũ chưa có giá trị | Thiết kế default/backfill trước khi ràng buộc `NOT NULL` |
| `valueNumeric` cho mã `"000123"` | Mất số 0 đầu hoặc sai kiểu dữ liệu nghiệp vụ | Dùng `VARCHAR` và `value` cho mã định danh dạng văn bản |
| `defaultValueComputed: CURRENT_TIMESTAMP` | Cách diễn giải biểu thức có thể khác giữa DBMS | Kiểm tra tương thích DBMS và `update-sql` |
| `autoIncrement: true` | SQL sinh ra và cơ chế cấp giá trị khác nhau giữa DBMS | Xác minh hỗ trợ change type, kiểu cột và driver |
| Cột boolean nhưng dùng `value: "false"` | Có thể tạo dữ liệu/SQL sai kiểu tùy DBMS | Dùng `valueBoolean: false` khi thay đổi đòi kiểu boolean |
| `sql` nhiều statement nhưng delimiter sai | Liquibase có thể tách lệnh không đúng | Kiểm tra `splitStatements`, `endDelimiter` và đặc điểm DBMS |
| `dropTable` trong rollback | Xóa cả dữ liệu thật khi rollback | Chỉ dùng khi chấp nhận mất dữ liệu hoặc có phương án khôi phục |

Với thay đổi dữ liệu lớn, không nên gộp việc tạo bảng, backfill toàn bộ hàng và thêm ràng buộc chặt vào một changeset khó rollback. Tách các giai đoạn, xem xét khóa bảng, dung lượng log và khả năng transaction của DBMS; chạy thử trên dữ liệu có khối lượng gần production.

## 10. Quy trình phát hiện lỗi trước khi `update`

Thực hiện các kiểm tra theo thứ tự từ rẻ đến đắt:

1. **Đọc lại cấu trúc YAML**: xác nhận không có tab, khóa trùng, dấu `-` thiếu hoặc cấp mapping sai. Bật YAML lint trong IDE nếu có.
2. **Xem đúng đường dẫn changelog**: kiểm tra root file, các `include`, `sqlFile` và file đóng gói trong artifact.
3. **Chạy Liquibase `validate`** với phiên bản thực tế để phát hiện lỗi cấu trúc, thay đổi checksum và những vấn đề Liquibase có thể kiểm tra trước.
4. **Chạy `status`** để xem danh sách changeset dự kiến còn chờ, nhất là khi database đã có lịch sử.
5. **Chạy `update-sql`** và review các câu lệnh DDL/DML, tên schema, constraint, kiểu dữ liệu và thứ tự thay đổi.
6. **Chạy `update` trên database thử nghiệm** có cùng loại và phiên bản DBMS với môi trường đích; xác minh schema và dữ liệu bằng truy vấn.
7. **Kiểm tra chạy lại và rollback** trên môi trường có thể tạo lại, rồi đối chiếu `DATABASECHANGELOG` và trạng thái database.

Ví dụ khi thông tin kết nối và JDBC driver đã được khai báo trong `liquibase.properties`:

```bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status
liquibase --defaults-file=liquibase.properties update-sql
liquibase --defaults-file=liquibase.properties update
```

Thứ tự và cú pháp tùy phiên bản CLI; hãy dùng một phiên bản Liquibase đã cố định trong dự án. **Chỉ chạy `update` sau khi hai bước kiểm tra và review SQL đã đạt**, trên database đúng mục tiêu. Không đặt mật khẩu database hoặc license key trong changelog, commit hay câu lệnh được ghi công khai; cấp qua secret manager hoặc cơ chế cấu hình an toàn.

Sau khi chạy, kiểm tra lịch sử:

```sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE, MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
```

Trong PostgreSQL, tên không đặt trong dấu nháy kép thường được quy về chữ thường; với DBMS khác, tên và schema của bảng metadata có thể có quy tắc riêng. Việc một changeset đã ghi vào lịch sử không thay thế kiểm tra nghiệp vụ: cần truy vấn đúng bảng, cột và dữ liệu mong đợi.

### 10.1. Đừng sửa changeset đã chạy để chữa lỗi định dạng

Sau khi một changeset được triển khai, Liquibase sử dụng định danh gồm `id`, `author` và đường dẫn file, cùng checksum, để kiểm tra lịch sử. Một thay đổi thụt dòng thuần túy không nhất thiết làm checksum đổi, nhưng việc đặt sai cấp làm thay đổi **nội dung mà Liquibase hiểu** có thể gây lỗi validation hoặc hành vi khác. Không dựa vào giả định mọi thay đổi whitespace đều vô hại.

Nếu phát hiện sai dữ liệu hoặc sai cấu trúc sau khi triển khai, tạo **changeset mới** để sửa. Nếu việc đổi đường dẫn hoặc `logicalFilePath` làm thay đổi định danh, phải đối chiếu `FILENAME` trong `DATABASECHANGELOG` trước khi khắc phục. Không tùy tiện xóa checksum, xóa bảng lịch sử hoặc đánh dấu thay đổi là đã chạy để bỏ qua nguyên nhân.

## 11. Bảng tra cứu lỗi YAML/Liquibase phổ biến

| Thông báo hoặc triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| YAML parser báo không tìm thấy `:` hoặc mapping không hợp lệ | Dòng trước/sau vị trí lỗi, dấu nháy, tab, dấu `: ` trong chuỗi | Sửa cú pháp, dùng khoảng trắng và quote chuỗi có ký tự đặc biệt |
| `Unexpected node`, thuộc tính không được nhận diện | Tên khóa và cấp thụt của `changeSet`, `changes`, `columns`, `constraints` | Đối chiếu reference của đúng change type và phiên bản Liquibase |
| Chỉ tạo một cột dù khai báo nhiều cột | Danh sách `columns` có thiếu dấu `- column:` hoặc khóa bị trùng | Viết lại thành sequence rõ ràng, xác minh bằng `update-sql` |
| Boolean/string bị chuyển kiểu | Giá trị `true`, `false`, `yes`, `on`, `000123`, `null` không được quote đúng | Phân biệt scalar YAML với `value*`/`defaultValue*` của Liquibase |
| `Changelog file not found` | Root, đường dẫn include, `relativeToChangelogFile`, classpath | Xác minh file và đường dẫn trong artifact thật |
| Migration lỗi khi tạo bảng/cột | Schema, quyền, kiểu dữ liệu, dữ liệu tồn tại, SQL sinh ra | Kiểm tra với DBMS đích, precondition và trình tự migration |
| Checksum thay đổi | Changeset đã chạy bị chỉnh nội dung hoặc cách nạp khác trước | So sánh changelog với lịch sử; tạo changeset mới khi cần sửa |
| Migration chỉ lỗi khi đóng gói JAR | Resource YAML/SQL thiếu hoặc đường dẫn phụ thuộc thư mục source | Đặt tài nguyên vào classpath và xác minh nội dung package |

## 12. Bài thực hành tự kiểm tra

Hãy tạo một database dùng riêng cho luyện tập, rồi thực hiện:

1. Lưu changelog đầy đủ ở mục 3 với một `id` và `author` ổn định. Chạy `validate` và xem `update-sql`.
2. Chủ động tạo một bản sao nội dung lỗi bằng cách di chuyển `columns:` ngang cấp với `createTable:`. Xem thông báo của validator, sau đó khôi phục cấu trúc đúng **trước khi thực thi**.
3. Thêm một changeset `insert` với cột chuỗi có giá trị `"000123"` và cột boolean có `valueBoolean: false`. Dùng câu lệnh `SELECT` để xác minh dữ liệu thực sự lưu đúng kiểu.
4. Thử dùng một chuỗi có `:` và `#` trong trường `comment` hoặc `value`; đặt dấu nháy để bảo toàn nội dung mong muốn.
5. Xác nhận `DATABASECHANGELOG` ghi đúng changeset và chạy lại `update` không thực thi lần nữa những changeset đã hoàn thành.
6. Trên database thử nghiệm có thể tạo lại, kiểm tra SQL rollback và thử rollback sau khi hiểu rõ tác động; xác minh trạng thái database và lịch sử sau rollback.

### Checklist trước khi merge changelog YAML

- [ ] File có một gốc `databaseChangeLog:` và đúng cấu trúc danh sách.
- [ ] Chỉ dùng khoảng trắng để thụt; mapping và sequence nằm đúng cấp.
- [ ] Không có khóa trùng nhau hoặc dấu `-` thừa/thiếu.
- [ ] Các tên thuộc tính Liquibase viết đúng và được phiên bản đang chạy hỗ trợ.
- [ ] `id`, `author`, mã có số 0 đầu, ngày giờ và chuỗi đặc biệt được biểu diễn rõ kiểu.
- [ ] Thuộc tính `value*`, `defaultValue*`, `type`, `constraints` phù hợp ý nghĩa mong muốn.
- [ ] SQL nhiều dòng dùng block scalar phù hợp và được review delimiter.
- [ ] Các file `include`/`sqlFile` có trong artifact và tham chiếu đúng đường dẫn.
- [ ] Đã chạy `validate`, xem `update-sql` và kiểm thử trên DBMS tương đương.
- [ ] Changeset đã chạy được giữ ổn định về định danh, nội dung và lịch sử.
- [ ] Rollback có kế hoạch rõ ràng và đã được thử trên database có thể khôi phục.

Một changelog YAML đáng tin cậy cần đúng cả cú pháp YAML, cấu trúc Liquibase và hành vi trên database. Viết rõ kiểu giá trị, thụt dòng nhất quán, kiểm tra SQL trước khi áp dụng và bảo toàn lịch sử changeset là nền tảng để dùng Liquibase an toàn qua môi trường phát triển, kiểm thử, Spring Boot và CI/CD.
