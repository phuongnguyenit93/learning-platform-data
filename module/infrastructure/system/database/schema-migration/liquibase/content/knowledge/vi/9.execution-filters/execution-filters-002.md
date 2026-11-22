# Contexts và cách phân nhóm mục đích thực thi trong Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với **changelog, changeset, precondition, checksum và lịch sử triển khai**; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi một changelog được dùng chung cho nhiều môi trường và nhiều quy trình triển khai, câu hỏi tiếp theo là: *changeset nào nên chạy trong lần triển khai này?* **Contexts** là một trong những cơ chế giúp trả lời câu hỏi đó.

Contexts đặc biệt hữu ích cho dữ liệu mẫu, fixture kiểm thử, thao tác chỉ phục vụ một chế độ chạy hoặc một mục đích triển khai đã được lựa chọn rõ ràng. Chúng cần được thiết kế cẩn thận: một context thông thường **không mặc nhiên ngăn changeset chạy khi không truyền bộ lọc**, và contexts cũng không thay thế việc kiểm tra trạng thái database, quản lý quyền hay quy trình phê duyệt production.

## 1. Context là gì, giải quyết vấn đề nào?

**Context** là nhãn gắn với changeset để Liquibase quyết định changeset có đủ điều kiện được xem xét thực thi trong một lần chạy hay không. Người vận hành hoặc hệ thống CI/CD chọn tập context cho lần chạy; Liquibase đối chiếu tập đó với **biểu thức context** ở changeset.

Ví dụ, một nhóm có ba loại thay đổi:

1. **Schema bắt buộc**: tạo bảng, thêm cột, tạo khóa để ứng dụng hoạt động ở mọi môi trường.
2. **Dữ liệu hỗ trợ phát triển/kiểm thử**: tạo user giả, đơn hàng mẫu, fixture hoặc dữ liệu phục vụ test tích hợp.
3. **Thao tác có chủ đích**: nạp dữ liệu demo cho một buổi trình diễn hoặc chạy một bước bảo trì được phê duyệt riêng.

Một changelog có thể chứa cả ba loại, nhưng không phải lần chạy nào cũng cần dữ liệu demo hoặc fixture. Với contexts, nhóm giữ một chuỗi migration có thể review, đồng thời chọn những changeset tùy chọn cần áp dụng trong từng lần chạy.

```text
Changelog được quản lý trong Git
        |
        +-- 001: Tạo bảng sản phẩm (bắt buộc)
        |
        +-- 002: Nạp dữ liệu demo    [@demo-data]
        |
        +-- 003: Tạo fixture test    [@test-fixtures]
        |
        +-- 004: Thêm cột bắt buộc (không có context)
        |
        v
Lệnh Liquibase + context được chọn
        |
        v
Lọc changeset chưa chạy -> kiểm tra điều kiện -> thực thi -> ghi lịch sử
```

Context là một điều kiện lựa chọn changeset, không phải một database riêng, một transaction riêng hay một ranh giới bảo mật. Với changeset đã được ghi là thực thi trong `DATABASECHANGELOG`, việc đổi context ở lần chạy sau không làm nó tự động chạy lại, trừ khi có cấu hình/thuộc tính chuyên biệt làm thay đổi hành vi thực thi.

## 2. Phân biệt `contextFilter`, context truyền khi chạy và tên gọi theo phiên bản

Hai phía của bộ lọc có nhiệm vụ khác nhau:

| Vị trí | Ví dụ | Ý nghĩa |
|---|---|---|
| Trong changeset | `contextFilter: "@demo-data"` | Quy định điều kiện context để changeset đủ điều kiện chạy |
| Trên Liquibase CLI | `--context-filter=demo-data` | Chọn context cho lần chạy CLI |
| Trong Spring Boot | `spring.liquibase.contexts: demo-data` | Cấu hình context mà ứng dụng truyền cho Liquibase |

Trong các phiên bản Liquibase hiện đại, thuộc tính changeset thường được viết là `contextFilter`, còn tham số CLI thường là `--context-filter`. Nhiều ví dụ hoặc phiên bản cũ dùng tên `context` trong changelog hay `--contexts` trên CLI. Khi làm việc với dự án thật, hãy kiểm tra tài liệu của **phiên bản Liquibase đang chạy**; không sao chép tên tham số từ tài liệu của bản khác rồi suy ra rằng chúng luôn là bí danh tương đương.

Ví dụ cấu trúc tối giản:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-product"
      author: "database-team"
      changes:
        - createTable:
            tableName: product
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: sku
                  type: VARCHAR(64)
                  constraints:
                    nullable: false
                    unique: true

  - changeSet:
      id: "002-seed-demo-product"
      author: "database-team"
      contextFilter: "@demo-data"
      changes:
        - insert:
            tableName: product
            columns:
              - column:
                  name: id
                  valueNumeric: 900001
              - column:
                  name: sku
                  value: "DEMO-001"
      rollback:
        - delete:
            tableName: product
            where: "sku = 'DEMO-001'"
```

Changeset `001` không có context, vì việc tạo bảng là bắt buộc. Changeset `002` có `@demo-data`: đây là kiểu **yêu cầu chọn context tường minh**, phù hợp với dữ liệu chỉ phục vụ demo. Giá trị `@demo-data` cần đặt trong dấu nháy trong YAML; không để ký tự `@` đứng đầu một scalar không có dấu nháy.

## 3. Quy tắc quan trọng nhất: thiếu bộ lọc không có nghĩa là chỉ chạy thay đổi chung

Một điểm rất dễ gây hiểu nhầm là cách Liquibase xử lý khi **không truyền context filter lúc chạy**.

- Changeset **không khai báo context** có thể chạy trong mọi lần cập nhật nếu chưa được thực thi.
- Changeset khai báo context thông thường, ví dụ `contextFilter: "dev"`, **vẫn có thể chạy khi lần cập nhật không truyền context filter**.
- Changeset khai báo context có tiền tố `@`, ví dụ `contextFilter: "@demo-data"`, yêu cầu context đó được chọn tường minh mới đủ điều kiện chạy.

Bảng dưới đây minh họa với các changeset **chưa được ghi nhận đã thực thi**, bỏ qua các điều kiện khác như `dbms`, precondition và lỗi SQL:

| `contextFilter` ở changeset | Không truyền filter lúc chạy | Chạy với `demo-data` | Chạy với `prod` |
|---|---|---|---|
| Không khai báo | Chạy | Chạy | Chạy |
| `"dev"` | Chạy | Bỏ qua | Bỏ qua |
| `"prod"` | Chạy | Bỏ qua | Chạy |
| `"@demo-data"` | Bỏ qua | Chạy | Bỏ qua |
| `"@test-fixtures"` | Bỏ qua | Bỏ qua | Bỏ qua |

**Hệ quả thực tiễn:** gắn `contextFilter: "dev"` vào một changeset chứa dữ liệu thử nghiệm chưa đủ để bảo đảm nó không chạy trên production. Nếu job production quên truyền bộ lọc, Liquibase vẫn có thể chọn changeset đó. Đối với dữ liệu tùy chọn phải có thao tác bật rõ ràng, hãy dùng `@` và kiểm tra kế hoạch cập nhật trước khi thực thi.

Tiền tố `@` không phải quyền truy cập hay cơ chế xác thực. Nếu cấu hình production vô tình truyền `demo-data`, changeset tương ứng vẫn có thể chạy. Vì vậy cần kết hợp cấu hình môi trường, review thay đổi, giới hạn quyền và kiểm tra trạng thái thực tế thay vì coi context là một hàng rào an toàn tuyệt đối.

## 4. Biểu thức context: OR, AND, NOT và ngoặc

Liquibase hỗ trợ biểu thức context để một changeset có thể đáp ứng nhiều trường hợp. Trong changelog YAML, viết biểu thức thành chuỗi để tránh ký tự có ý nghĩa với YAML:

```yaml
contextFilter: "dev OR test"
```

Ví dụ biểu thức:

| Biểu thức | Ý định |
|---|---|
| `"dev"` | Dành cho lần chạy có context `dev`; với lần chạy không có filter, vẫn lưu ý quy tắc ở mục 3 |
| `"dev OR test"` | Cho phép khi chọn `dev` hoặc `test` |
| `"dev AND seed"` | Chỉ phù hợp khi cả `dev` và `seed` được chọn |
| `"dev AND !prod"` | Yêu cầu `dev` và không chọn `prod` |
| `"(dev OR test) AND seed"` | Nhóm điều kiện rõ ràng để tránh nhầm thứ tự ưu tiên |
| `"@seed-data"` | Yêu cầu chọn tường minh `seed-data` |

Liquibase hỗ trợ cú pháp ngăn cách bằng dấu phẩy trong một số biểu thức context, thường dùng với ý nghĩa OR. Để bài dễ đọc và giảm hiểu nhầm, nên viết tường minh `OR`, `AND`, `!` và dấu ngoặc khi cần điều kiện phức tạp. Tên context nên ngắn, không dấu, nhất quán giữa changelog và cấu hình triển khai.

**Phân biệt hai thao tác:** viết `contextFilter: "dev OR test"` trong changeset là yêu cầu ở phía changelog; truyền `--context-filter=dev,test` ở CLI là chọn context ở phía lần chạy. Không nên tự suy luận rằng kết hợp biểu thức và tập context luôn hoạt động như mong muốn khi có nhiều toán tử; hãy tạo một database kiểm thử và dùng lệnh xem danh sách thay đổi/SQL để kiểm chứng.

### 4.1. Ví dụ có hai điều kiện cùng cần thỏa

Giả sử việc nạp dữ liệu mẫu chỉ được phép trong môi trường dev khi pipeline chủ động bật `seed`:

```yaml
databaseChangeLog:
  - changeSet:
      id: "010-load-dev-sample"
      author: "database-team"
      contextFilter: "dev AND seed"
      changes:
        - insert:
            tableName: product
            columns:
              - column:
                  name: id
                  valueNumeric: 900002
              - column:
                  name: sku
                  value: "DEV-SAMPLE"
      rollback:
        - delete:
            tableName: product
            where: "sku = 'DEV-SAMPLE'"
```

Ví dụ này minh họa phép AND, nhưng vẫn cần nhớ rằng **nếu không có context filter ở lần chạy, một biểu thức không có `@` có thể được Liquibase chấp nhận**. Đối với tác vụ chỉ được bật tường minh, nên thiết kế context opt-in đơn giản như `"@dev-seed"` và chỉ cấp context `dev-seed` từ một job được kiểm soát. Đừng phụ thuộc vào biểu thức phức tạp như cơ chế chặn production.

### 4.2. Cần kiểm tra logic phủ định

Biểu thức như `"!prod"` rất dễ bị hiểu sai nếu mặc định rằng môi trường không truyền context nào tương đương với `prod`. Không có bộ lọc được cung cấp không nhất thiết mang ý nghĩa rằng nhóm đang triển khai vào một môi trường an toàn để chạy mọi thay đổi khác production.

Đối với dữ liệu demo hoặc destructive maintenance, **tránh dùng phủ định `!prod` làm lớp bảo vệ duy nhất**. Sử dụng một context opt-in rõ mục đích, cộng với kiểm tra loại môi trường và phê duyệt ở CI/CD. Với điều kiện bắt buộc gắn với trạng thái database, hãy dùng precondition phù hợp.

## 5. Phân nhóm theo mục đích thực thi thay vì chỉ theo tên môi trường

Gắn một changeset đơn thuần là `dev` hoặc `prod` có vẻ tiện, nhưng một lần triển khai có thể có nhiều mục đích độc lập. Ví dụ, dev cần cả fixture và demo; staging đôi khi cần demo dữ liệu ẩn danh; production cần schema bắt buộc nhưng không được nạp fixture.

Thiết kế contexts theo **mục đích có thể lựa chọn độc lập**:

| Nhóm mục đích | Tên context gợi ý | Cách dùng |
|---|---|---|
| Thay đổi schema bắt buộc | Không đặt context | Tất cả môi trường nhận cùng tập schema cần thiết |
| Dữ liệu thử nghiệm phục vụ test tích hợp | `@test-fixtures` | Chỉ bật trong job kiểm thử được phép nạp fixture |
| Dữ liệu giới thiệu tính năng | `@demo-data` | Chỉ bật khi có nhu cầu demo |
| Dữ liệu khởi tạo phục vụ phát triển cục bộ | `@local-seed` | Chỉ bật ở cấu hình phát triển có kiểm soát |
| Tác vụ bảo trì tùy chọn | `@maintenance` | Bật bởi job bảo trì và phê duyệt riêng; review SQL kỹ |

Một schema update cần thiết cho ứng dụng không nên bị khóa trong `@prod` chỉ vì hiện tại được triển khai lên production. Khi đó dev và test có thể bỏ lỡ thay đổi cần thiết; schema bắt đầu lệch nhau và lỗi chỉ lộ ra khi phát hành. Giữ các thay đổi cốt lõi không có context, trừ khi có lý do thiết kế cụ thể và đã kiểm tra luồng phát hành.

Tên context `prod` cũng không chứng minh kết nối JDBC đang trỏ đến production. Liquibase sử dụng tên do người vận hành truyền, nên chọn context và chọn database là hai quyết định khác nhau. Database đích phải được xác nhận bằng URL/schema/tài khoản, và quyền thực thi phải phù hợp.

### 5.1. Ví dụ master changelog có các nhóm rõ ràng

Có thể tổ chức như sau:

```text
db/changelog/
├── master.yaml
└── changes/
    ├── 001-create-product.yaml
    ├── 002-add-product-price.yaml
    ├── 003-seed-demo-product.yaml
    └── 004-seed-test-fixtures.yaml
```

Master khai báo thứ tự cố định:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-product.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-product-price.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-seed-demo-product.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/004-seed-test-fixtures.yaml
      relativeToChangelogFile: true
```

Trong file `003-seed-demo-product.yaml`, gắn `contextFilter: "@demo-data"` vào changeset tương ứng. Trong file `004-seed-test-fixtures.yaml`, gắn `contextFilter: "@test-fixtures"`. Hai file đầu chỉ chứa changeset bắt buộc và không cần context. Một lần chạy production không chọn context nào sẽ áp dụng những thay đổi cốt lõi chưa chạy và bỏ qua các changeset yêu cầu `@`.

Ưu điểm của cấu trúc này là người review thấy rõ thứ tự và mục đích của từng file. Tuy nhiên, **thư mục hoặc tên file không tự lọc execution**: việc files được `include` chỉ có nghĩa Liquibase đọc chúng. Quyết định có chạy hay không nằm ở từng changeset và các điều kiện của lần triển khai.

## 6. Phối hợp contexts với `include`, `includeAll` và các bộ lọc khác

Trong các phiên bản hỗ trợ cấu hình context trên `include` hoặc `includeAll`, có thể giới hạn một nhóm changelog được include, ví dụ để đánh dấu nhiều changeset thuộc cùng một nhóm. Khi phối hợp context ở cấp include và cấp changeset, Liquibase có thể kết hợp các điều kiện. Cần xác minh cách kết hợp và phạm vi ảnh hưởng trong reference của đúng phiên bản đang sử dụng.

Để tài liệu đào tạo và lịch sử triển khai dễ hiểu, bài này ưu tiên đặt `contextFilter` trực tiếp tại changeset, nơi người đọc dễ thấy mục đích của thay đổi. Nếu nhóm quyết định đặt filter cấp include để tránh lặp, hãy kiểm tra từng changeset được nạp, đặc biệt khi có include lồng nhau hoặc `includeAll`.

So sánh với các cơ chế khác:

| Cơ chế | Điều nó quyết định | Ví dụ |
|---|---|---|
| **Context** | Thay đổi có được chọn trong lần chạy với mục đích/ngữ cảnh hiện tại không? | Chỉ nạp `@test-fixtures` khi chạy test |
| **Label** | Thay đổi có được chọn theo nhãn phát hành, nhóm tính năng hoặc nhãn quản lý không? | Chọn các changeset có label liên quan một đợt phát hành |
| **`dbms`** | Changeset áp dụng cho hệ quản trị database nào? | SQL đặc thù `postgresql` |
| **Precondition** | Trạng thái/điều kiện database có phù hợp để thực thi không? | Xác minh bảng chưa tồn tại, phiên bản schema hoặc truy vấn dữ liệu |
| **`DATABASECHANGELOG`** | Changeset đã được ghi nhận thực thi hay chưa? | Tránh thực thi lại một changeset bình thường |

Những cơ chế này có thể cùng tác động đến một changeset. Chẳng hạn, changeset `@test-fixtures` chỉ được chọn khi bật context phù hợp; nhưng nếu precondition yêu cầu một bảng phải tồn tại mà bảng đó thiếu, changeset vẫn có thể dừng hoặc xử lý theo `onFail`. Nếu changeset đã chạy, việc đổi context thông thường không làm nó trở thành một thay đổi mới.

**Không dùng context thay cho kiểm tra DBMS**: một lệnh chạy với context `postgres` không chứng minh kết nối đang sử dụng PostgreSQL. Với SQL đặc thù, dùng thuộc tính `dbms` hoặc precondition thích hợp. **Không dùng context thay cho quyền database**: runner vẫn phải đăng nhập với tài khoản được cấp quyền tương ứng.

## 7. Chạy và kiểm chứng context bằng Liquibase CLI

Giả sử `liquibase.properties` đã có JDBC URL, driver, thông tin xác thực phù hợp và đường dẫn `changeLogFile`. Trong các phiên bản hỗ trợ `--context-filter`, có thể chạy:

```bash
# Xem SQL dự kiến cho schema cốt lõi và dữ liệu demo được chọn tường minh
liquibase --defaults-file=liquibase.properties \
  --context-filter=demo-data update-sql

# Chỉ cập nhật sau khi đã review SQL và đúng database đích
liquibase --defaults-file=liquibase.properties \
  --context-filter=demo-data update
```

Đối với một lần cập nhật test có fixture:

```bash
liquibase --defaults-file=liquibase.properties \
  --context-filter=test-fixtures update-sql
liquibase --defaults-file=liquibase.properties \
  --context-filter=test-fixtures update
```

Nếu chỉ muốn áp dụng schema cốt lõi và bỏ qua những thay đổi opt-in:

```bash
liquibase --defaults-file=liquibase.properties update-sql
liquibase --defaults-file=liquibase.properties update
```

Khi dùng changelog đã thiết kế theo `@demo-data` và `@test-fixtures`, một lượt không truyền context sẽ bỏ qua các changeset opt-in đó. Nhưng **nếu trong changelog có `contextFilter: "dev"` thông thường**, lượt không truyền context vẫn có thể chạy changeset này. Phải review toàn bộ changelog khi xác định kết quả của một lần triển khai.

### 7.1. Kiểm tra trước và sau khi `update`

Một quy trình có thể áp dụng tại môi trường kiểm thử:

1. Xác nhận URL, schema và tài khoản database đích; không dựa vào tên context để đoán môi trường.
2. Chạy `validate` để kiểm tra cấu trúc changelog và checksum của changeset đã thực thi.
3. Kiểm tra danh sách changeset chờ chạy bằng `status` (nếu phiên bản hỗ trợ, dùng chế độ verbose) với cùng context filter mà lần `update` sẽ dùng.
4. Chạy `update-sql` với **cùng filter** và review SQL được sinh ra, đặc biệt các lệnh `INSERT`, `UPDATE`, `DELETE` và DDL không đảo ngược được.
5. Chạy `update` trên database thử nghiệm và xác minh dữ liệu, schema cùng lịch sử trong `DATABASECHANGELOG`.
6. Lặp lại lệnh với cùng context; xác nhận những changeset bình thường đã chạy không bị thực thi lần nữa.

Ví dụ:

```bash
liquibase --defaults-file=liquibase.properties validate

liquibase --defaults-file=liquibase.properties \
  --context-filter=test-fixtures status --verbose

liquibase --defaults-file=liquibase.properties \
  --context-filter=test-fixtures update-sql
```

Vị trí tham số và tên option có thể thay đổi giữa các phiên bản CLI. Nếu lệnh báo option không hợp lệ, hãy tra cứu `liquibase --help` và tài liệu chính thức của đúng phiên bản thay vì đổi cấu hình một cách ngẫu nhiên.

### 7.2. Kiểm chứng lịch sử thực thi

Sau khi chạy, truy vấn bảng lịch sử (ví dụ với database cho phép truy vấn tên bảng/cột không phân biệt chữ hoa khi không trích dẫn):

```sql
SELECT ID, AUTHOR, FILENAME, CONTEXTS, EXECTYPE, MD5SUM, DATEEXECUTED
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
```

`DATABASECHANGELOG` lưu những changeset đã thực thi và metadata liên quan, bao gồm thông tin context của changeset. Cột `CONTEXTS` phản ánh context gắn với changeset trong lịch sử, **không nên dùng nó như bằng chứng độc lập rằng một job đã truyền tham số runtime cụ thể nào**. Muốn kiểm toán chính xác lần triển khai, lưu thêm cấu hình pipeline đã áp dụng, phiên bản Liquibase, artifact, môi trường và log đã loại bỏ bí mật.

## 8. Cấu hình contexts trong Spring Boot

Khi Spring Boot tự chạy Liquibase lúc khởi động, thuộc tính cấu hình thường dùng là `spring.liquibase.contexts`. Ví dụ cho một profile phát triển có chủ đích nạp demo:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/master.yaml
    contexts: demo-data
```

Trong môi trường kiểm thử, có thể dùng profile cấu hình tương ứng để chọn `test-fixtures`:

```yaml
spring:
  liquibase:
    contexts: test-fixtures
```

Với production, không nên mặc định truyền tất cả context. Nếu toàn bộ dữ liệu tùy chọn đã dùng quy ước `@`, việc không cấu hình context sẽ khiến những changeset đó không được chọn. Tuy nhiên, thay đổi cấu hình phải được kiểm chứng bằng `update-sql` và thử trên môi trường staging tương đương.

Lưu ý khác biệt: `spring.liquibase.contexts` là **property của Spring Boot**, còn `--context-filter` là **tham số Liquibase CLI**. Dù hai cách cuối cùng đều truyền context cho Liquibase, không được mặc định CLI sẽ đọc file `application.yml` hoặc Spring Boot sẽ tự nhận mọi tham số CLI. Mỗi đường chạy cần cấu hình rõ ràng.

Nếu CI/CD đã có một job chạy Liquibase CLI trước khi triển khai ứng dụng, cần xác định ứng dụng Spring Boot có tiếp tục chạy Liquibase khi khởi động hay không. Hai tiến trình cùng đụng vào một database có thể tranh khóa; ngay cả khi Liquibase có cơ chế khóa, cấu hình context khác nhau giữa hai tiến trình có thể tạo thứ tự thực thi khó dự đoán. Chọn một nơi chịu trách nhiệm migration cho từng giai đoạn triển khai và thống nhất version, changelog, context, schema cùng tài khoản.

## 9. Cách đưa context vào CI/CD nhiều môi trường

Thiết kế pipeline theo **mục đích thực thi được phê duyệt**:

| Job | Database mục tiêu | Context được chọn | Kết quả mong đợi |
|---|---|---|---|
| Build/kiểm tra cấu trúc | Database test hoặc bản sao dùng cho validation | Không chọn context tùy chọn | Kiểm tra schema bắt buộc và changelog |
| Integration test | Database được tạo riêng cho test | `test-fixtures` | Schema bắt buộc và fixture cần thiết cho test |
| Demo | Database demo được cấp phép | `demo-data` | Schema bắt buộc và dữ liệu demo |
| Production migration | Production được xác nhận qua cấu hình/approval | Không bật context demo/test | Schema bắt buộc, bỏ qua changeset `@demo-data` và `@test-fixtures` |
| Maintenance riêng | Database đích xác định và job đã phê duyệt | `maintenance` | Chỉ thêm thay đổi bảo trì opt-in cùng thay đổi bắt buộc còn chờ |

Các dòng mô tả **quy ước đề xuất**, không phải cơ chế môi trường có sẵn của Liquibase. Nếu pipeline production truyền nhầm `test-fixtures`, Liquibase không tự biết rằng đó là production để bác bỏ. Cần chặn lỗi từ pipeline, policy, bảo mật tài khoản, review SQL và kiểm tra precondition cho những trường hợp phù hợp.

Với dữ liệu seed chỉ phục vụ phát triển/kiểm thử, nên ưu tiên database riêng, dữ liệu giả hoặc dữ liệu đã ẩn danh. Không dựa vào context để áp dụng dữ liệu kiểm thử vào production hoặc vô tình tạo thông tin đăng nhập giả có thể bị lợi dụng.

Ví dụ logic một pipeline:

```text
1. Chọn artifact changelog được review
2. Xác thực DB URL + schema + quyền của environment
3. Lấy contexts từ cấu hình job được kiểm soát
4. Chạy validate, status, update-sql với chính contexts đó
5. Review SQL và xác nhận approval khi cần
6. Chạy update với cùng artifact, contexts và kết nối
7. Kiểm tra schema, dữ liệu, DATABASECHANGELOG và log triển khai
```

Để tránh lệch hành vi, cùng một job nên dùng **một nguồn cấu hình context** cho preview và update. Nếu preview dùng `test-fixtures` nhưng update vô tình bỏ filter, các changeset context thông thường khác có thể được chọn ngoài dự tính.

## 10. Contexts, thứ tự triển khai và phụ thuộc giữa changesets

Liquibase vẫn xử lý các changeset theo thứ tự changelog đối với những changeset đủ điều kiện. Khi một changeset bị lọc, nó có thể được áp dụng ở một lần chạy sau nếu context phù hợp được chọn và changeset vẫn chưa được ghi nhận đã thực thi.

Ví dụ:

```text
001: Tạo bảng customer          [không context]
002: Seed customer demo         [@demo-data]
003: Thêm cột customer.status   [không context]
```

Một lượt production không chọn context có thể chạy `001` rồi `003`, bỏ qua `002`. Sau đó một lượt demo trên database phù hợp có thể chạy `002` muộn hơn, khi cột `status` đã tồn tại. Nếu dữ liệu của `002` giả định schema cũ, SQL có thể lỗi hoặc không còn đúng nghiệp vụ. Context **không bảo đảm rằng thứ tự logic của các changeset được chọn muộn vẫn an toàn**.

Vì thế:

- Thiết kế các changeset tùy chọn độc lập hoặc tương thích với mọi schema đích mà chúng có thể gặp.
- Tránh để schema cốt lõi phụ thuộc vào dữ liệu chỉ chạy trong `@demo-data` hay `@test-fixtures`.
- Khi seed phụ thuộc vào một schema cụ thể, kiểm tra bằng precondition/kiểm thử hoặc thiết kế seed để có thể chạy ở thời điểm dự kiến.
- Xem `update-sql` với từng tập context cần hỗ trợ, không chỉ một lần chạy mặc định.
- Không chỉnh changeset đã triển khai để sửa phụ thuộc; bổ sung changeset mới và lên kế hoạch cập nhật những database đã có lịch sử.

Các thay đổi có khả năng ảnh hưởng dữ liệu lớn nên được tách theo các bước nhỏ có thể quan sát. Context chỉ chọn changeset; nó không giải quyết việc backfill nhiều triệu hàng, lock lâu, transaction của DBMS hay rollback mất dữ liệu.

## 11. Context, rollback và checksum

**Rollback:** Nếu một changeset tùy chọn đã chạy, nó vẫn là một phần của lịch sử database. Khi cần hoàn tác, phải chọn phương án rollback tương ứng và kiểm tra ảnh hưởng dữ liệu. Không nên cho rằng gỡ context khỏi một lần chạy sẽ xóa dữ liệu demo đã được nạp. Bộ lọc dùng khi chạy update không phải là lệnh hoàn tác.

Ví dụ changeset nạp fixture:

```yaml
databaseChangeLog:
  - changeSet:
      id: "020-add-test-fixture"
      author: "database-team"
      contextFilter: "@test-fixtures"
      changes:
        - insert:
            tableName: product
            columns:
              - column:
                  name: id
                  valueNumeric: 900020
              - column:
                  name: sku
                  value: "TEST-FIXTURE-020"
      rollback:
        - delete:
            tableName: product
            where: "sku = 'TEST-FIXTURE-020'"
```

Rollback bằng `delete` có thể phù hợp với một database kiểm thử được kiểm soát; nếu bản ghi đã được các bảng khác tham chiếu, câu lệnh xóa có thể thất bại do khóa ngoại hoặc làm mất dữ liệu nghiệp vụ. Vì vậy phải thử rollback trên đúng trạng thái database dự kiến.

**Checksum và lịch sử:** Liquibase xác định một changeset thông thường bằng `id`, `author` và đường dẫn changelog (hoặc đường dẫn logic được cấu hình). Sau khi chạy, Liquibase lưu thông tin execution và checksum trong `DATABASECHANGELOG`. Đổi nội dung changeset đã chạy có thể gây lỗi checksum; đổi context sau khi chạy **không biến nó thành một changeset mới**. Một số thay đổi thuộc metadata có thể không ảnh hưởng checksum trong từng phiên bản; vẫn không nên sửa context của changeset đã chạy mà không review toàn bộ tác động triển khai.

Khi phát hiện một changeset tùy chọn đã chạy nhầm môi trường, trước tiên xác minh dữ liệu, người dùng, phụ thuộc và bản ghi lịch sử. Không xóa `DATABASECHANGELOG`, sửa checksum hoặc chạy rollback hàng loạt chỉ để che lỗi cấu hình. Thiết kế một migration bù an toàn, có phê duyệt khi cần, và bổ sung kiểm thử cho filter để ngăn tái diễn.

## 12. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra và xử lý |
|---|---|---|
| Dữ liệu demo chạy khi không bật context | Chỉ dùng `contextFilter: "dev"` và job không truyền context | Xác nhận semantics không-filter; dùng `@demo-data` cho opt-in và review preview |
| Bật context nhưng fixture vẫn không xuất hiện | Sai tên context, changeset đã chạy, còn precondition/DBMS filter | Xem `status`, `DATABASECHANGELOG`, log và context thực tế của job |
| Chạy production nhưng migration cốt lõi bị bỏ qua | Gắn nhầm context lên thay đổi bắt buộc | Rà soát phân nhóm; giữ schema cốt lõi không có context trừ khi có lý do rõ ràng |
| CLI chạy đúng nhưng Spring Boot có kết quả khác | Cấu hình `--context-filter` và `spring.liquibase.contexts` không đồng nhất | So sánh context, version, changelog, DB URL và schema ở hai đường chạy |
| `--context-filter` không được CLI nhận | Phiên bản Liquibase sử dụng tên option khác | Kiểm tra `--help` và tài liệu của đúng phiên bản trước khi đổi cú pháp |
| Changeset được chọn nhưng SQL thất bại | Context chỉ lọc, không kiểm tra dữ liệu và quyền | Dùng `update-sql`, precondition và thử trên DBMS tương đương |
| Bật context mới mà không có changeset nào chạy | Changeset từng chạy rồi hoặc không còn pending | Kiểm tra `DATABASECHANGELOG` và `id`/`author`/`FILENAME` |
| Thêm fixture sau một số migration cốt lõi khiến dữ liệu lỗi | Changeset tùy chọn được chạy muộn hơn thứ tự nghiệp vụ mong đợi | Thiết kế fixture tương thích schema mới và kiểm tra trên database đã có lịch sử |
| Không còn bật context nhưng dữ liệu fixture vẫn tồn tại | Tắt filter không phải rollback | Dùng kế hoạch cleanup/rollback riêng có kiểm chứng |

## 13. Bài thực hành: kiểm tra ma trận context

Hãy dùng một database PostgreSQL hoặc DBMS thử nghiệm khác có thể tạo lại, với một changelog gồm:

1. `001-create-product`: tạo bảng `product`, không khai báo context.
2. `002-seed-demo-product`: chèn sản phẩm demo, gắn `contextFilter: "@demo-data"`.
3. `003-seed-test-fixture`: chèn sản phẩm kiểm thử, gắn `contextFilter: "@test-fixtures"`.

Mỗi lượt trong bảng dưới đây nên được chạy trên **database trắng độc lập**, hoặc tạo lại database giữa các lượt; nếu dùng chung một database, lịch sử các changeset đã chạy sẽ làm kết quả khó so sánh.

| Lượt thử | Context runtime | Kết quả mong đợi trên database mới |
|---|---|---|
| A | Không truyền | Chỉ có bảng `product`; không có demo hoặc fixture |
| B | `demo-data` | Có bảng `product` và dòng demo; không có fixture |
| C | `test-fixtures` | Có bảng `product` và fixture; không có demo |
| D | `demo-data,test-fixtures` | Có bảng `product`, demo và fixture |
| E | `prod` | Chỉ có bảng `product`; các changeset `@` không khớp đều bị bỏ qua |

Khi làm bài, thực hiện các bước:

1. Dùng `validate` để kiểm tra cú pháp và cấu trúc YAML.
2. Dùng `status` và `update-sql` với filter tương ứng để xác nhận danh sách thay đổi sẽ được chọn.
3. Dùng `update` trên từng database thử nghiệm.
4. Truy vấn bảng `product` và `DATABASECHANGELOG` để đối chiếu kết quả thật.
5. Chạy lại cùng một context và xác nhận các changeset bình thường không tự thực thi lần nữa.
6. Thử chuyển context từ A sang B **trên cùng một database riêng**: kiểm tra changeset `002` có thể được áp dụng muộn mà không chạy lại `001`.
7. Thử rollback của dữ liệu demo hoặc fixture sau khi xác minh bản ghi độc lập và không bị tham chiếu bởi dữ liệu khác.

### Checklist trước khi merge một changelog dùng contexts

- [ ] Những thay đổi schema thiết yếu có được chạy ở mọi môi trường cần hỗ trợ không?
- [ ] Các changeset demo, fixture và maintenance có context opt-in khi cần bật tường minh không?
- [ ] Nhóm đã hiểu quy tắc **không truyền context filter** và tác dụng của `@` chưa?
- [ ] Tên context có ổn định, rõ mục đích và được cấu hình nhất quán trong CLI/Spring Boot/CI chưa?
- [ ] Đã kiểm thử `update-sql` cho tất cả tập context quan trọng chưa?
- [ ] Những changeset được chạy muộn có tương thích schema hiện tại không?
- [ ] Đã tách việc chọn context khỏi việc xác nhận DB URL/schema, quyền truy cập và trạng thái DB chưa?
- [ ] Đã review precondition, rollback, lịch sử `DATABASECHANGELOG` và checksum chưa?
- [ ] Dữ liệu thử nghiệm có được giới hạn trong database phù hợp, có phương án xóa/khôi phục riêng không?

**Kết luận:** Contexts giúp phân nhóm changeset theo **mục đích thực thi**, cho phép dùng cùng changelog trong nhiều quy trình. Thiết kế hiệu quả nhất là để những thay đổi schema bắt buộc chạy nhất quán, đặt các thay đổi tùy chọn dưới context opt-in rõ ràng, xác minh cùng bộ lọc ở `status`/`update-sql`/`update`, và luôn kiểm tra lịch sử migration, precondition cũng như rollback trước khi đưa vào môi trường quan trọng. Đây là cách phối hợp context với các cơ chế còn lại của `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` để triển khai có thể kiểm chứng và tái lập.
