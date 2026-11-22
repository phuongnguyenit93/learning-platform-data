# Phối hợp bộ lọc ở changelog, changeset và lệnh thực thi

## 1. Bài toán: cùng một changelog nhưng không phải thay đổi nào cũng chạy

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase được dùng để quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai. Mục tiêu thực hành còn gồm migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một dự án thường cần dùng **một nguồn changelog được quản lý phiên bản** nhưng lựa chọn những thay đổi thích hợp với từng lần triển khai: tạo schema dùng chung ở mọi nơi, nạp dữ liệu thử nghiệm ở development, thực hiện một bước đặc biệt trên PostgreSQL, hoặc chỉ bật tính năng mới ở một đợt phát hành.

Liquibase hỗ trợ lựa chọn changeset bằng nhiều lớp điều kiện. Chúng xuất hiện ở **changelog khi include file**, ở **changeset khi khai báo thuộc tính**, và ở **lệnh thực thi khi chọn context/label**. Ngoài ra còn có điều kiện theo DBMS, precondition và lịch sử đã chạy. Nếu chỉ hiểu từng công cụ riêng lẻ mà không biết chúng kết hợp thế nào, một lệnh `update` có thể chạy quá nhiều changeset, bỏ sót bước nền tảng hoặc đánh dấu lịch sử không đúng với trạng thái thực tế.

Bài này tập trung vào cách tổ chức và phối hợp các lớp lọc trong cùng một quy trình triển khai. Sau bài học, bạn có thể giải thích vì sao một changeset được chọn hoặc bị loại, thiết kế điều kiện rõ ràng cho nhiều môi trường và kiểm chứng tập thay đổi dự kiến trước khi cho phép pipeline chạy migration.

## 2. Mô hình tổng quát của quá trình chọn changeset

Một cách nhìn thực hành là coi mỗi changeset đi qua các bước kiểm tra:

```text
Root changelog
      |
      v
include / includeAll của changelog cha
      |    (contextFilter và labels kế thừa, nếu có)
      v
changeset được khai báo trong file con
      |    (contextFilter, labels, dbms)
      v
Bộ lọc ở lần chạy Liquibase
      |    (--context-filter, --label-filter; DBMS đích)
      v
Đối chiếu DATABASECHANGELOG
      |    (chưa chạy, hoặc được phép chạy lại?)
      v
Precondition và các điều kiện thực thi
      |
      +---- không đạt / không được chọn --> bỏ qua, cảnh báo hoặc dừng
      |
      v
Thực hiện thay đổi và ghi nhận lịch sử
```

Sơ đồ thể hiện cách phân tích nguyên nhân, không cam kết thứ tự thực thi nội bộ của mọi phiên bản Liquibase. Quan trọng là **một changeset chỉ được áp dụng khi tập hợp các điều kiện liên quan cho phép**, đồng thời Liquibase xét lịch sử đã triển khai. Precondition là một phép kiểm tra trạng thái; nó có thể dừng hoặc điều chỉnh hành vi xử lý changeset, chứ không đơn thuần là nhãn chọn môi trường.

Ba tầng cấu hình cần phân biệt:

| Tầng | Cấu hình thường gặp | Phạm vi tác động | Trách nhiệm |
|---|---|---|---|
| Changelog cha | `contextFilter`, `labels` trên `include`/`includeAll` | Các changeset được nạp từ file/thư mục được include | Khoanh vùng một nhóm migration |
| Changeset | `contextFilter`, `labels`, `dbms`, `preConditions` | Một changeset cụ thể | Diễn đạt điều kiện mà thay đổi cần tuân thủ |
| Lệnh chạy | `--context-filter`, `--label-filter`, kết nối database | Lần chạy `update`, `status` hoặc `update-sql` tương ứng | Quyết định tập môi trường/nhãn được kích hoạt |

Tùy phiên bản Liquibase, tên thuộc tính và khả năng gắn bộ lọc trên `include` có thể khác. Các ví dụ dùng cách viết `contextFilter` và tham số CLI `--context-filter` phổ biến ở Liquibase hiện đại; khi triển khai thật, cần đối chiếu phiên bản đang dùng, đặc biệt nếu dự án trước đây sử dụng tên `context` hoặc tham số `--contexts`.

## 3. Context: điều kiện mô tả nơi hoặc tình huống changeset được phép chạy

### 3.1. Khai báo contextFilter trên changeset

Ví dụ, changeset nạp dữ liệu giả lập chỉ dành cho development:

```yaml
databaseChangeLog:
  - changeSet:
      id: 010-seed-demo-customer
      author: db-team
      contextFilter: dev
      changes:
        - insert:
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 9001
              - column:
                  name: email
                  value: demo@example.invalid
      rollback:
        - delete:
            tableName: customer
            where: "id = 9001"
```

`contextFilter: dev` mô tả điều kiện của changeset. Khi một lần chạy chỉ chọn context `prod`, changeset này thường bị loại vì không khớp. Khi chạy với context `dev`, nó có thể được chọn nếu các điều kiện khác cũng phù hợp.

**Điểm dễ sai:** nếu không truyền bộ lọc context vào lệnh, Liquibase thông thường vẫn chạy những changeset có `contextFilter`, kể cả changeset gắn `dev`. Gắn context `dev` một mình **không** bảo đảm rằng lệnh `update` thiếu cấu hình sẽ bỏ qua dữ liệu thử nghiệm. Cần đặt chính sách gọi Liquibase rõ ràng và dùng cơ chế yêu cầu lựa chọn tường minh khi thực sự cần.

### 3.2. Dấu @ yêu cầu context được chỉ định tường minh

Nếu một changeset chỉ được chạy khi người vận hành chủ động chọn context, có thể dùng tiền tố `@`:

```yaml
databaseChangeLog:
  - changeSet:
      id: 020-prod-one-time-adjustment
      author: db-team
      contextFilter: "@prod"
      changes:
        - sql:
            sql: "UPDATE feature_flags SET enabled = TRUE WHERE code = 'new-checkout'"
      rollback:
        - sql:
            sql: "UPDATE feature_flags SET enabled = FALSE WHERE code = 'new-checkout'"
```

Khai báo `"@prod"` yêu cầu chỉ định context tương ứng trong lần chạy; nếu không chọn context một cách tường minh, changeset sẽ không được thực thi. Đây là khác biệt quan trọng so với `contextFilter: prod`.

Ví dụ nêu thao tác UPDATE đơn giản để minh họa cú pháp; rollback chỉ đúng nếu giá trị trước đó được biết và không bị người dùng/hệ thống khác thay đổi trong thời gian giữa hai lần triển khai. Khi dùng cho dữ liệu thực tế, cần xác minh bản ghi đích, chụp giá trị trước và thiết kế rollback phù hợp.

### 3.3. Kết hợp context bằng biểu thức

Context filter hỗ trợ biểu thức với toán tử logic như `and`, `or`, `!` (phủ định), dấu ngoặc và dấu phẩy như cách biểu diễn OR trong ngữ cảnh hỗ trợ. Ví dụ:

```yaml
contextFilter: "dev or test"
```

Diễn giải là changeset thuộc các tình huống dev hoặc test. Một điều kiện phức tạp hơn:

```yaml
contextFilter: "(dev or test) and !legacy"
```

Ý định là chỉ chọn khi có dev hoặc test và không chọn legacy. Khi dùng phủ định và biểu thức kết hợp, phải kiểm tra chúng với tập context CLI thực tế. Đặc biệt, không nên suy diễn rằng thay đổi thứ tự từ khóa hoặc bỏ dấu ngoặc luôn giữ nguyên nghĩa.

Trong XML, cùng ý định có thể được biểu diễn qua thuộc tính trên `changeSet`; trong JSON và YAML, dùng thuộc tính tương ứng của đối tượng changeset. Formatted SQL có cú pháp chú thích riêng và phạm vi hỗ trợ tùy phiên bản/edition.

## 4. Label: đánh dấu nhóm chức năng hoặc đợt phát hành

Context thường gắn với môi trường hoặc tình huống chạy, còn **label** có thể đại diện cho module, nhóm tính năng, đợt triển khai hoặc mức độ ưu tiên. Đây là **quy ước thiết kế**, Liquibase không ép label phải mang ý nghĩa cụ thể.

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 030-add-checkout-column
      author: db-team
      labels: checkout-v2
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: checkout_version
                  type: varchar(20)
      rollback:
        - dropColumn:
            tableName: orders
            columnName: checkout_version
```

Khi chạy Liquibase với `--label-filter=checkout-v2`, changeset gắn nhãn `checkout-v2` có thể được chọn nếu những điều kiện còn lại cũng đạt. Một changeset không có label thường không bị loại chỉ vì lần chạy có `--label-filter`; điều này hữu ích cho những migration nền tảng chạy chung.

Bộ lọc nhãn ở lệnh chạy có thể dùng biểu thức logic, chẳng hạn:

```bash
liquibase --label-filter="checkout-v2 and !deprecated" status --verbose
```

Không nên dùng label để thay thế kiểm tra trạng thái schema hay bảo vệ dữ liệu production. Label cho biết **ý định chọn tập thay đổi**. Nó không xác nhận bảng đã tồn tại, dữ liệu hợp lệ hay ứng dụng đã tương thích. Những vấn đề đó cần được giải quyết bằng trình tự migration, precondition, kiểm thử và kế hoạch triển khai.

### 4.1. Context và label có hai trách nhiệm khác nhau

Ví dụ thay đổi chỉ phù hợp với môi trường production và thuộc tính năng checkout:

```yaml
databaseChangeLog:
  - changeSet:
      id: 040-checkout-production-step
      author: db-team
      contextFilter: "@prod"
      labels: checkout-v2
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: checkout_ready
                  type: boolean
                  defaultValueBoolean: false
```

Khi người vận hành chọn `prod` và lọc nhãn `checkout-v2`, cả hai loại điều kiện đều phù hợp. Nếu chỉ chọn nhãn mà không kích hoạt context `prod`, tiền tố `@` ngăn changeset chạy. Nếu chọn `dev`, changeset không khớp context cho dù label đúng. Tầng label và tầng context cần được phối hợp, chứ không phải một tầng tự động ghi đè tầng còn lại.

## 5. Bộ lọc trên include và includeAll ở changelog cha

Changelog gốc có thể nạp nhiều file con. Khi thuộc tính lọc được khai báo trên `include`/`includeAll` ở phiên bản hỗ trợ, nó bổ sung điều kiện cho **tập changeset trong các file được nạp**.

Giả sử cấu trúc:

```text
db/changelog/
├── db.changelog-master.yaml
├── common/
│   └── 001-core-schema.yaml
├── seed/
│   └── 010-seed-demo.yaml
└── features/
    └── 020-checkout.yaml
```

Root changelog:

```yaml
databaseChangeLog:
  - include:
      file: common/001-core-schema.yaml
      relativeToChangelogFile: true

  - include:
      file: seed/010-seed-demo.yaml
      relativeToChangelogFile: true
      contextFilter: "dev or test"
      labels: "seed"

  - include:
      file: features/020-checkout.yaml
      relativeToChangelogFile: true
      labels: "checkout-v2"
```

Ý nghĩa thiết kế:

- Thay đổi nền tảng trong `common` không nhận thêm context/label từ root; nó có thể chạy ở mọi môi trường nếu không bị điều kiện bên trong hoặc lệnh chạy loại.
- Các changeset trong `seed/010-seed-demo.yaml` chịu bộ lọc context của include và nhãn `seed` ở cấp include.
- Các changeset trong `features/020-checkout.yaml` nhận nhãn nhóm `checkout-v2` từ include; mỗi changeset vẫn có thể khai báo thêm điều kiện riêng.

Việc thêm context/label trên `include` có tác dụng *ràng buộc thêm* các changeset được include, không tự sửa phần khai báo changeset bên trong. Với cây include nhiều cấp, các bộ lọc có thể được truyền xuống theo cơ chế nối điều kiện; hãy xem chúng như những điều kiện đồng thời cần thỏa, rồi kiểm chứng trên phiên bản Liquibase cụ thể bằng `status` và `update-sql`.

### 5.1. Kết hợp bộ lọc cha và con

Giả sử file `seed/010-seed-demo.yaml` có:

```yaml
databaseChangeLog:
  - changeSet:
      id: 010-seed-demo
      author: db-team
      contextFilter: dev
      labels: sample-data
      changes:
        - insert:
            tableName: seed_marker
            columns:
              - column:
                  name: marker
                  value: "development"
```

Tại root, file này chỉ được include cho `dev or test` và được gắn nhãn `seed`. Tại changeset, context là `dev` và label là `sample-data`. Có thể diễn giải điều kiện hiệu lực như sau:

```text
Context hiệu lực = (dev OR test) AND dev
Label hiệu lực   = seed AND sample-data
```

Nghĩa là changeset này dành cho dev, và hai lớp label đều mô tả tập thay đổi. Đây là cách diễn đạt logic để review thiết kế; cách cung cấp biểu thức label ở CLI phải được kiểm thử tương ứng với cách Liquibase kết hợp thuộc tính trong phiên bản đang dùng. Đừng chỉ thấy file nằm trong thư mục `seed` rồi cho rằng mọi context đều có thể chạy nó.

### 5.2. includeAll và chính sách thư mục

Một root có thể đặt điều kiện cho cả thư mục:

```yaml
databaseChangeLog:
  - includeAll:
      path: seed-data
      relativeToChangelogFile: true
      contextFilter: "dev or test"
      labels: "seed"
```

Liquibase sẽ xử lý các changelog hợp lệ được tìm trong thư mục theo cơ chế `includeAll`; việc gắn bộ lọc không thay cho quản lý thứ tự file, tình trạng trùng tên hoặc loại tài nguyên. Khi các changeset có phụ thuộc chặt chẽ, `include` tường minh dễ review hơn. Tránh bỏ file SQL thường/CSV vào thư mục `includeAll` nếu chúng không phải changelog hợp lệ.

Cấu hình filter ở cấp include/includeAll không nhất thiết được hỗ trợ giống nhau ở mọi phiên bản Liquibase. Dự án cần khóa phiên bản Liquibase giữa các môi trường, kiểm tra cú pháp bằng `validate` và quan sát tập changeset được chọn trước khi triển khai.

## 6. Bộ lọc dbms độc lập với context và label

Thuộc tính `dbms` trên changeset giới hạn hệ quản trị cơ sở dữ liệu mục tiêu:

```yaml
databaseChangeLog:
  - changeSet:
      id: 050-postgres-index
      author: db-team
      dbms: postgresql
      labels: performance
      changes:
        - sql:
            sql: "CREATE INDEX idx_orders_created_at ON orders (created_at)"
      rollback:
        - sql:
            sql: "DROP INDEX idx_orders_created_at"
```

Khai báo `dbms: postgresql` làm changeset chỉ phù hợp khi Liquibase kết nối tới PostgreSQL. Một lệnh có context/label phù hợp nhưng đang kết nối MySQL vẫn không chạy changeset này. Thuộc tính `dbms` không được quyết định bởi tên environment hay label; Liquibase nhận diện DBMS qua kết nối database.

Có thể khai báo nhiều DBMS hoặc phủ định theo cú pháp Liquibase hỗ trợ, chẳng hạn chuỗi phân tách bằng dấu phẩy hoặc `!mysql`. Tuy nhiên, với SQL đặc thù từng hệ quản trị, nên dùng điều kiện đơn giản, rõ ràng và kiểm chứng trên đúng DBMS đích. Không dùng `dbms` thay thế context: cùng là PostgreSQL nhưng dev và production vẫn có nhu cầu khác nhau.

### 6.1. Ma trận điều kiện tổng hợp

Với một changeset có:

```yaml
contextFilter: "@prod"
labels: checkout-v2
dbms: postgresql
```

Diễn giải một số tình huống:

| Database đích | Context được chọn | Label filter được chọn | Kết quả dự kiến |
|---|---|---|---|
| PostgreSQL | `prod` | `checkout-v2` | Được chọn nếu chưa chạy và các điều kiện khác đạt |
| PostgreSQL | `dev` | `checkout-v2` | Không chọn vì context không khớp |
| PostgreSQL | Không chỉ định | `checkout-v2` | Không chọn vì `@prod` yêu cầu chỉ định tường minh |
| MySQL | `prod` | `checkout-v2` | Không chọn vì `dbms` không khớp |
| PostgreSQL | `prod` | `another-feature` | Không chọn vì label không khớp |

Bảng minh họa giả định không có bộ lọc bổ sung ở include, precondition không cản trở và changeset chưa chạy. Nếu không truyền `--label-filter`, những changeset có nhãn vẫn có thể được chạy; tương tự, context thiếu tiền tố `@` thường không tự loại changeset khi lệnh không chỉ định context filter.

## 7. Lệnh thực thi quyết định tập được chọn

Changelog mô tả phạm vi dự kiến, nhưng **lệnh chạy** mới cho biết môi trường thực sự chọn context và label nào. Ví dụ CLI với Liquibase hỗ trợ tham số hiện đại:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --context-filter=dev \
  --label-filter=seed \
  status --verbose
```

Lệnh này kiểm tra changeset pending theo bộ lọc dev và nhãn seed, trong điều kiện các tham số kết nối và cơ chế tìm changelog đã được cấu hình. Trước khi dùng trong pipeline, cần chỉ rõ file cấu hình, database URL, credentials và search path/classpath thích hợp. Ví dụ này chỉ minh họa bộ lọc, không bao gồm thông tin kết nối thật.

Một lần triển khai khác:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --context-filter=prod \
  --label-filter=checkout-v2 \
  update-sql
```

Lệnh `update-sql` cho phép review SQL dự kiến trước khi thực thi thật. Sau khi được kiểm duyệt, lệnh `update` phải dùng **cùng root changelog, database đích, context, label và phiên bản Liquibase** để kết quả kiểm tra đại diện cho lần chạy thực tế.

Đối với biểu thức có dấu cách hoặc ký tự điều khiển của shell, luôn dùng dấu nháy:

```bash
liquibase --context-filter="prod and !legacy" --label-filter="checkout-v2 and !deprecated" status --verbose
```

Các lệnh ở trên là ví dụ cú pháp CLI. Trong môi trường có phiên bản Liquibase cũ, tham số context có thể là `--contexts`; hãy xác nhận bằng tài liệu và trợ giúp của phiên bản đang cài. Trong Spring Boot, có thể cấu hình context/label qua các thuộc tính `spring.liquibase.contexts` và `spring.liquibase.label-filter` theo phiên bản Spring Boot hỗ trợ. Cần bảo đảm các giá trị CLI và cấu hình ứng dụng không khác nhau về ý nghĩa lựa chọn.

### 7.1. Không truyền bộ lọc có phải là “không chạy changeset có nhãn” không?

Không. Một hiểu nhầm thường gặp là “đã gắn context hoặc labels trên changeset thì mặc nhiên thay đổi đó chỉ chạy khi CLI có filter”. Thực tế, khi không có bộ lọc tại lần chạy, Liquibase thường **không giới hạn** các changeset chỉ vì chúng có context hay label. Ngoại lệ đáng chú ý là quy tắc `@` cho context yêu cầu được chọn tường minh.

Ví dụ:

| Changeset khai báo | Lần chạy không truyền context/label | Lần chạy chọn `dev` (giả sử không có label filter) |
|---|---|---|
| Không có context, không có label | Có thể chạy | Có thể chạy |
| `contextFilter: dev` | Có thể chạy | Có thể chạy |
| `contextFilter: prod` | Có thể chạy | Bị loại do context không khớp |
| `contextFilter: "@prod"` | Không chọn | Không chọn |
| `labels: seed` | Có thể chạy | Có thể chạy nếu các điều kiện khác cho phép |

Các ô “có thể chạy” nghĩa là được xét tiếp theo lịch sử và điều kiện thực thi, không bảo đảm lệnh SQL sẽ được thực hiện. Do đặc điểm này, pipeline nên luôn cung cấp filter rõ ràng khi dùng bộ lọc để tách môi trường, và dùng `@` cho thay đổi cần hành động kích hoạt tường minh.

## 8. Precondition khác bộ lọc context và label ở điểm nào?

Bộ lọc context/label/dbms lựa chọn changeset theo cấu hình và loại database. **Precondition** kiểm tra điều kiện tại thời điểm chạy: đối tượng schema có tồn tại, dữ liệu có đạt điều kiện, DBMS có phù hợp, hoặc một changeset trước đó đã được ghi nhận hay chưa.

Ví dụ, một changeset chỉ nên chạy khi bảng nguồn đã tồn tại:

```yaml
databaseChangeLog:
  - changeSet:
      id: 060-add-order-constraint
      author: db-team
      contextFilter: "@prod"
      labels: "hardening"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: customer_id
      changes:
        - addNotNullConstraint:
            tableName: orders
            columnName: customer_id
            columnDataType: bigint
```

Logic nghiệp vụ:

1. Changeset được lựa chọn theo context `prod`, label và DBMS.
2. Khi changeset được xử lý, precondition kiểm tra bảng và cột.
3. Nếu điều kiện thiếu, `onFail: HALT` dừng quá trình cập nhật.
4. Nếu điều kiện đạt, Liquibase tiếp tục thao tác thêm ràng buộc; thao tác thực tế vẫn có thể thất bại nếu dữ liệu hiện có chứa NULL.

Precondition `columnExists` **không chứng minh** mọi giá trị `customer_id` đều khác NULL. Trước khi thêm ràng buộc cần kiểm tra và backfill dữ liệu nếu cần. Đó là lý do bộ lọc, precondition và kiểm chứng dữ liệu không thể thay thế nhau.

### 8.1. Hành vi onFail

Các hành vi thường dùng ở cấp changeset:

- `HALT`: dừng migration; phù hợp với điều kiện tiên quyết bắt buộc.
- `WARN`: cảnh báo và tiếp tục theo cơ chế của Liquibase.
- `CONTINUE`: bỏ qua changeset ở lần chạy hiện tại; có thể thử lại về sau.
- `MARK_RAN`: không chạy nội dung nhưng đánh dấu changeset đã chạy trong lịch sử.

`MARK_RAN` chỉ thích hợp khi trạng thái đích đã tương đương với kết quả mong muốn. Dùng nó chỉ để pipeline “xanh” dù một cột hoặc constraint còn thiếu có thể tạo ra khoảng cách giữa lịch sử và schema thực tế. `onError` giải quyết lỗi trong quá trình đánh giá precondition, khác với `onFail` khi đánh giá cho kết quả không đạt.

Precondition đặt ở cấp changelog có phạm vi và tập hành vi hỗ trợ khác cấp changeset. Vì vậy cần phân biệt mục đích: precondition toàn cục dùng để kiểm tra điều kiện của quá trình áp dụng toàn changelog; precondition của changeset kiểm tra điều kiện của thay đổi cụ thể.

## 9. Lịch sử DATABASECHANGELOG vẫn là yếu tố quyết định có chạy lại hay không

Các bộ lọc chỉ tác động đến **tập changeset được xem xét** trong lần chạy. Một changeset đủ điều kiện nhưng đã được ghi nhận trong `DATABASECHANGELOG` thường được bỏ qua khi chạy `update` lần tiếp theo.

Danh tính changeset được xác định bởi `id`, `author` và đường dẫn logic của changelog. Bảng `DATABASECHANGELOG` ghi các thông tin đó cùng checksum và thời điểm/kiểu thực thi. Ví dụ truy vấn đọc lịch sử:

```sql
SELECT ID, AUTHOR, FILENAME, DATEEXECUTED, EXECTYPE, MD5SUM
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
```

Giả sử một changeset `contextFilter: dev` đã từng được chạy trên database production vì pipeline quên truyền filter. Sau đó thêm `--context-filter=prod` vào pipeline sẽ ngăn những lần chọn không phù hợp trong tương lai, nhưng **không tự hoàn tác** thay đổi đã chạy. Cần kiểm tra trạng thái thực của schema/dữ liệu và thiết kế migration bù hoặc rollback đúng quy trình.

Tương tự, đổi context/label không có nghĩa Liquibase sẽ tự chạy lại changeset trước đó đã áp dụng. Những thuộc tính như `runAlways` hoặc `runOnChange` có quy tắc chạy lại riêng; không nên dùng chúng để chữa một lỗi lựa chọn filter. Checksum giúp phát hiện thay đổi trong nội dung đã ghi lịch sử, không bảo vệ toàn bộ vấn đề logic context/label.

Một nguyên tắc quan trọng: **đừng sửa changeset lịch sử đã triển khai chỉ để thay đổi ý định phát hành**. Nếu cần một thao tác mới ở production hoặc một bước dữ liệu mới cho test, tạo changeset mới với bộ định danh và bộ lọc thích hợp. Trường hợp bắt buộc điều chỉnh filter trên changeset cũ cần đánh giá tác động lên các database có lịch sử khác nhau và kiểm chứng checksum theo phiên bản đang dùng.

## 10. Tình huống phối hợp bộ lọc trong dự án nhiều môi trường

### 10.1. Migration dùng chung trên mọi môi trường

Các thay đổi cấu trúc nền tảng như tạo bảng hoặc bổ sung cột cần cho mọi môi trường nên được khai báo trong nhóm chung, tránh gắn context `dev`/`prod` khi không cần. Điều này giúp các changeset phụ thuộc không gặp cảnh thiếu bảng ở một môi trường do thiếu context.

```yaml
databaseChangeLog:
  - include:
      file: common/001-create-orders.yaml
      relativeToChangelogFile: true
```

Đừng gắn filter chỉ vì thư mục chứa file có tên liên quan môi trường. Hãy đặt filter theo yêu cầu thực tế của thay đổi.

### 10.2. Dữ liệu thử nghiệm chỉ dành cho dev và test

Dữ liệu giả lập cần tách khỏi schema chung. Có thể dùng `include` với `contextFilter: "dev or test"` và nhãn `sample-data`. Đồng thời pipeline phải luôn truyền context thích hợp; nếu muốn ngăn chạy khi quên filter, cân nhắc thiết kế bảo vệ tường minh, kiểm thử biểu thức và quy trình điều phối lệnh. Không dựa riêng vào việc changeset “mang context dev” để bảo vệ production.

Nên định nghĩa dữ liệu seed idempotent khi có thể, dùng khóa không va chạm với dữ liệu nghiệp vụ và có rollback đúng phạm vi. Nếu seed có nguy cơ phá dữ liệu, cân nhắc tách nó thành pipeline riêng có bước xác nhận môi trường.

### 10.3. Thay đổi production có chủ đích

Một data correction chạy một lần ở production có thể được gắn `contextFilter: "@prod"` và label `data-fix-2026`. Pipeline sản xuất cần chọn `prod` tường minh và review các changeset có nhãn liên quan.

Trường hợp này cần thêm precondition hoặc bước kiểm tra SQL để bảo vệ trạng thái dữ liệu; `@prod` chỉ xác nhận việc lựa chọn context, không chứng minh người chạy đã chọn đúng database URL. Một lệnh mang context prod nhưng trỏ nhầm dev vẫn có thể áp dụng thay đổi trên dev. Các thông tin kết nối và secret cần được kiểm soát tách biệt.

### 10.4. Thay đổi chỉ dành cho PostgreSQL

Đánh dấu `dbms: postgresql` nếu SQL dùng cú pháp PostgreSQL. Điều kiện context/label vẫn có thể áp dụng đồng thời nếu thay đổi chỉ dành cho một đợt triển khai nhất định. Không nên coi `dbms` là một tên môi trường: staging cũng có thể dùng PostgreSQL giống production.

### 10.5. Triển khai theo từng tính năng

Một schema dùng chung có thể là tiền đề của hai feature flag. Thay đổi mở rộng schema có thể chạy trong nhóm common để tương thích ứng dụng, còn bước bật tính năng hoặc nạp dữ liệu chuyên biệt có label riêng. Khi lập kế hoạch rollback, phải hiểu rằng lọc label ở lần triển khai không tự tạo quan hệ phụ thuộc giữa changeset; thứ tự và tính tương thích phải được thiết kế trực tiếp.

## 11. Spring Boot và CI/CD: đặt bộ lọc ở đâu để tránh lệch cấu hình?

Với Spring Boot có Liquibase tích hợp, root changelog thường được cấu hình qua `spring.liquibase.change-log`. Ví dụ:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    contexts: dev
    label-filter: seed
```

Cấu hình trên minh họa cách chọn filter ở ứng dụng; tên thuộc tính có thể khác tùy phiên bản Spring Boot/Liquibase, vì vậy cần kiểm tra binding thực tế khi nâng cấp. Trong môi trường nhiều profile, có thể sử dụng cấu hình riêng cho từng môi trường hoặc truyền giá trị qua biến môi trường, nhưng root changelog và logic lựa chọn phải nhất quán.

Với CI/CD, một cách tổ chức là có bước migration riêng:

1. Pipeline xác định database đích và cấu hình xác thực từ secret store.
2. Chọn phiên bản changelog đã được build và kiểm thử.
3. Khai báo context/label dựa trên môi trường hoặc đợt phát hành; không để giá trị thiếu ngoài ý định.
4. Chạy `validate` để kiểm tra cấu trúc changelog.
5. Chạy `status --verbose` với đúng filter để xem tập pending.
6. Chạy `update-sql` với đúng filter, kết nối và DBMS để review SQL.
7. Chỉ khi tập thay đổi đúng dự kiến mới chạy `update` bằng cùng cấu hình.
8. Đối chiếu `DATABASECHANGELOG` và kiểm tra trạng thái schema/dữ liệu sau migration.

Nếu dùng đồng thời Spring Boot tự chạy Liquibase và pipeline cũng chạy migration, cần thống nhất nơi chịu trách nhiệm chính để tránh chồng chéo thời điểm triển khai. Liquibase có `DATABASECHANGELOGLOCK` để điều phối các tiến trình, nhưng nó không sửa được sai sót chọn nhầm context hoặc database.

Có thể xây dựng một bảng cấu hình vận hành minh bạch:

| Môi trường | Context truyền vào | Label dùng khi cần | Đặc điểm |
|---|---|---|---|
| Local development | `dev` | `seed` | Dữ liệu thử nghiệm có thể được chọn |
| Test tích hợp | `test` | `seed` hoặc `integration` | Kiểm tra kịch bản đầy đủ, dùng database riêng |
| Staging | `staging` | Nhãn đợt phát hành | Mô phỏng migration production |
| Production | `prod` | Nhãn đã duyệt | Kiểm soát tập changeset và SQL dự kiến |

Bảng trên là **quy ước minh họa**, không phải tên context bắt buộc của Liquibase. Giá trị thật phải trùng với những context/label mà changelog khai báo. Những thay đổi không gắn filter vẫn có thể xuất hiện ở nhiều môi trường; đây thường là hành vi mong muốn cho schema nền tảng.

## 12. Các lỗi phối hợp bộ lọc và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Bước xác minh |
|---|---|---|
| Dữ liệu dev chạy vào production | Pipeline không truyền context filter; changeset chỉ khai báo `dev` mà không yêu cầu tường minh | Kiểm tra lệnh thực tế, context hiệu lực và lịch sử |
| Changeset không chạy dù có nhãn đúng | Context ở changeset hoặc include không khớp; `@` chưa được chọn; DBMS khác | Đối chiếu cả ba tầng lọc và database đích |
| Schema thiếu bảng tiền đề | Changeset tạo bảng bị lọc, nhưng changeset phụ thuộc vẫn được chọn | Xem include/context/labels của cả hai bước, không chỉ bước bị lỗi |
| Chọn label khác nhưng thay đổi vẫn chạy | Changeset không có label hoặc filter chưa được truyền | Kiểm tra thuộc tính thực tế và tham số lệnh |
| Staging và production có tập pending khác nhau | Lịch sử `DATABASECHANGELOG`, filter hoặc DBMS khác nhau | So sánh ID/AUTHOR/FILENAME, context/label và kết nối |
| Precondition báo HALT dù filter đúng | Trạng thái schema/dữ liệu chưa đạt điều kiện | Kiểm tra điều kiện và bước migration tiền đề |
| Changeset đã chạy không chạy lại khi đổi context | Lịch sử đã ghi nhận changeset; bộ lọc không điều khiển replay | Kiểm tra `DATABASECHANGELOG`; thiết kế changeset bổ sung nếu cần |
| `status` và `update` cho kết quả khác | Khác root changelog, DBMS, kết nối, context, label, phiên bản hoặc thời điểm lịch sử thay đổi | So sánh toàn bộ cấu hình và log của từng lệnh |

Khi chẩn đoán, hãy đi từ một changeset cụ thể và trả lời lần lượt: *Nó nằm ở file nào? File được include bởi những filter nào? Changeset có điều kiện gì? Lệnh chạy truyền những filter nào? Kết nối đang tới DBMS và database nào? Changeset đã nằm trong lịch sử chưa? Precondition có đạt không?* Cách này tìm được nguyên nhân thực thay vì thử xóa bộ lọc cho đến khi migration chạy được.

## 13. Bài tập phân tích trước khi thực thi

Cho root changelog:

```yaml
databaseChangeLog:
  - include:
      file: common/001-schema.yaml
      relativeToChangelogFile: true
  - include:
      file: seed/002-demo.yaml
      relativeToChangelogFile: true
      contextFilter: "dev or test"
      labels: seed
```

File `common/001-schema.yaml` có changeset không khai báo context hoặc label. File `seed/002-demo.yaml` có một changeset `contextFilter: dev`, `labels: demo`, chưa được ghi trong lịch sử. Giả định database đích là PostgreSQL và không có điều kiện khác.

**Câu hỏi A:** Lần chạy chọn context `dev` và label filter phù hợp cả hai nhãn ở nhóm seed thì những thay đổi nào được xét? **Gợi ý:** changeset chung vẫn được xét; changeset seed đáp ứng context ở include và changeset, đồng thời cần khớp logic label hiệu lực.

**Câu hỏi B:** Lần chạy chỉ chọn context `test` thì chuyện gì xảy ra? **Gợi ý:** changeset chung vẫn được xét. Changeset seed mang context `dev` nên không thỏa cả tầng cha và con dù include cho phép test.

**Câu hỏi C:** Lần chạy không chỉ định context hoặc label có chắc loại seed không? **Đáp án:** Không. Các context/label thông thường không tự bảo vệ khi không truyền filter, vì vậy cần thiết kế cách kích hoạt tường minh hoặc chặn thiếu cấu hình ở pipeline.

**Câu hỏi D:** Nếu file schema chung đã chạy từ hôm trước thì có được tạo bảng lại không? **Đáp án:** Thường không. Liquibase đối chiếu `DATABASECHANGELOG` và bỏ qua changeset đã được ghi nhận hợp lệ, trừ khi có cơ chế chạy lại được cấu hình.

Có thể dùng `validate`, `status --verbose` và `update-sql` trong môi trường thử nghiệm để kiểm tra các kết luận này với phiên bản Liquibase hiện dùng. Không cần chạy `update` vào database thật chỉ để thử biểu thức lọc.

## 14. Checklist review cho một bộ lọc phối hợp

- [ ] Root changelog và các `include`/`includeAll` có thứ tự, đường dẫn và filter rõ ràng.
- [ ] Đã phân biệt context (tình huống/môi trường) và label (nhóm tính năng/phát hành).
- [ ] Biểu thức context/label có dấu ngoặc và toán tử phù hợp, được kiểm chứng ở phiên bản Liquibase sử dụng.
- [ ] Đã xem xét cách các điều kiện từ include và changeset được kết hợp.
- [ ] Các changeset nền tảng không bị lọc mất trong khi changeset phụ thuộc vẫn chạy.
- [ ] Những migration cần kích hoạt tường minh có cơ chế phù hợp, chẳng hạn context `@prod` và guard trong pipeline.
- [ ] Giá trị context/label tại lệnh chạy không bị bỏ trống ngoài ý định.
- [ ] Thuộc tính `dbms` khớp hệ quản trị thực tế; SQL đặc thù được kiểm tra trên đúng DBMS.
- [ ] Precondition kiểm tra trạng thái cần thiết và có hành vi `onFail` an toàn.
- [ ] Đã xem xét lịch sử `DATABASECHANGELOG` của môi trường đích, không suy đoán từ môi trường khác.
- [ ] Các bước `status`, `update-sql` và `update` dùng thống nhất root changelog, filter, database và phiên bản.
- [ ] Rollback hoặc migration bù đã được chuẩn bị cho các thay đổi dữ liệu/ràng buộc quan trọng.
- [ ] Có cách điều tra khi một changeset bị bỏ qua hoặc chạy ngoài dự kiến.

Phối hợp bộ lọc ở changelog, changeset và lệnh thực thi là bài toán thiết kế **tập thay đổi được phép áp dụng**. Changelog cha xác định phạm vi nhóm, changeset mô tả điều kiện riêng, lệnh chạy kích hoạt lựa chọn của từng môi trường, còn DBMS, precondition và lịch sử triển khai xác định điều kiện thực tế. Thiết kế tốt phải khiến tập changeset dự kiến có thể được giải thích, kiểm chứng trước khi cập nhật và truy vết được sau khi triển khai.

