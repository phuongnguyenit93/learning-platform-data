# Ràng buộc CHECK và lựa chọn cách khai báo phù hợp

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase hỗ trợ quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Mục tiêu học tập còn bao gồm migration có kiểm chứng, rollback, phối hợp nhiều môi trường, tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Khóa và chỉ mục**, tập trung vào **ràng buộc CHECK**: CHECK bảo vệ quy tắc dữ liệu nào, khác gì với NOT NULL, UNIQUE hoặc FOREIGN KEY, và nên khai báo nó bằng change type của Liquibase hay SQL tùy chỉnh trong từng tình huống.

Sau khi học, bạn cần có khả năng:

- Diễn giải đúng điều kiện CHECK, đặc biệt cách SQL xử lý giá trị NULL.
- Chọn giữa CHECK ở định nghĩa bảng, thêm CHECK vào bảng hiện hữu và sử dụng SQL riêng theo DBMS.
- Xác định những khả năng phụ thuộc **phiên bản Liquibase, gói tính năng/giấy phép và DBMS**, tránh giả định một cú pháp chạy được ở mọi môi trường.
- Thiết kế quy trình phát hiện dữ liệu vi phạm trước khi tạo constraint, bổ sung constraint và xác minh thực tế.
- Xử lý bảng lớn, triển khai nhiều giai đoạn, rollback và các khác biệt giữa các hệ quản trị.
- Review changeset trong CI/CD để phát hiện constraint thiếu, sai biểu thức hoặc không được database thực thi.

## 2. CHECK là gì?

**CHECK constraint** là một quy tắc do cơ sở dữ liệu kiểm tra khi dữ liệu được INSERT hoặc UPDATE, dựa trên biểu thức điều kiện liên quan đến hàng dữ liệu. Nếu biểu thức **FALSE**, thao tác thường bị từ chối vì vi phạm constraint. CHECK giúp bảo vệ dữ liệu ngay tại tầng database, kể cả khi có nhiều ứng dụng hoặc job dữ liệu cùng ghi vào một bảng.

Ví dụ:

~~~sql
CREATE TABLE order_item (
    id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(18, 2) NOT NULL,
    CONSTRAINT ck_order_item_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT ck_order_item_unit_price_nonnegative
        CHECK (unit_price >= 0)
);
~~~

Khi INSERT một hàng có quantity bằng 0 hoặc unit_price âm, database sẽ báo lỗi vi phạm constraint nếu hệ quản trị và phiên bản đang dùng thực thi CHECK theo đúng cách được mong đợi.

CHECK có thể biểu diễn điều kiện trên một cột hoặc nhiều cột trong cùng hàng:

~~~sql
ALTER TABLE order_item
ADD CONSTRAINT ck_order_item_discount_valid
CHECK (discount_amount IS NULL
       OR (discount_amount >= 0 AND discount_amount <= unit_price * quantity));
~~~

Giả sử bảng đã có cột discount_amount, điều kiện trên cho phép không có giảm giá, hoặc yêu cầu mức giảm không âm và không vượt quá giá trị hàng. Đây là một ví dụ quy tắc tính toán; khi dùng số thập phân, cần kiểm tra precision, scale và cách làm tròn theo quy tắc nghiệp vụ.

**CHECK không thay thế logic ứng dụng:** ứng dụng vẫn nên đưa ra thông báo rõ ràng, kiểm tra đầu vào sớm và xử lý lỗi constraint; database đóng vai trò hàng rào cuối cùng để ngăn ghi dữ liệu không hợp lệ.

## 3. Điểm quan trọng nhất: logic ba giá trị và NULL

Trong SQL, phép so sánh với NULL thường cho kết quả **UNKNOWN**, không phải TRUE hay FALSE. CHECK theo ngữ nghĩa SQL thông dụng **chấp nhận TRUE hoặc UNKNOWN** và chỉ từ chối trường hợp biểu thức là **FALSE**.

Xét:

~~~sql
CHECK (quantity > 0)
~~~

| quantity | Kết quả biểu thức | CHECK có thể chấp nhận? |
|---|---|---|
| 5 | TRUE | Có |
| 0 | FALSE | Không |
| -3 | FALSE | Không |
| NULL | UNKNOWN | Có, nếu cột được phép NULL |

Nếu nghiệp vụ yêu cầu quantity phải có giá trị dương, cần thêm **NOT NULL**:

~~~sql
quantity INTEGER NOT NULL,
CONSTRAINT ck_quantity_positive CHECK (quantity > 0)
~~~

Một cách khác là viết CHECK (quantity IS NOT NULL AND quantity > 0), nhưng về thiết kế schema, **NOT NULL tường minh** thường rõ nghĩa hơn và được công cụ quản trị nhận diện trực tiếp.

### NULL trong điều kiện nhiều cột

Giả sử chỉ cho phép ngày kết thúc khi ngày bắt đầu đã được xác định:

~~~sql
CHECK (ended_at IS NULL OR ended_at >= started_at)
~~~

Nếu ended_at khác NULL nhưng started_at là NULL, nhánh so sánh có thể cho UNKNOWN, khiến CHECK vẫn được chấp nhận. Nếu started_at bắt buộc tồn tại, hãy khai báo started_at NOT NULL hoặc bổ sung logic rõ ràng trong biểu thức.

**Bài học:** đừng suy diễn rằng CHECK có so sánh sẽ mặc nhiên cấm NULL. Khi review constraint, luôn thử đủ các trường hợp TRUE, FALSE và UNKNOWN.

## 4. CHECK khác các ràng buộc và chỉ mục khác như thế nào?

| Công cụ | Mục đích chính | Ví dụ phù hợp |
|---|---|---|
| **NOT NULL** | Cấm giá trị NULL | email bắt buộc có giá trị |
| **CHECK** | Bảo vệ điều kiện logic trên một hàng | quantity > 0; ended_at >= started_at |
| **UNIQUE** | Chặn giá trị khóa trùng theo quy tắc của DBMS | username không được lặp |
| **PRIMARY KEY** | Nhận diện duy nhất mỗi hàng | order_item.id |
| **FOREIGN KEY** | Bảo đảm tham chiếu đến hàng của bảng khác | order.customer_id tham chiếu customer.id |
| **INDEX** | Hỗ trợ truy vấn hoặc thực thi một số ràng buộc đặc biệt | Index theo customer_id, created_at |
| **Kiểm tra ở ứng dụng** | Phản hồi sớm và diễn giải lỗi nghiệp vụ | Báo rõ lý do dữ liệu không hợp lệ |

CHECK **không bảo đảm duy nhất**, **không thay thế FOREIGN KEY** và **không tự tạo index phục vụ truy vấn**. Một số quy tắc như “mỗi khách hàng chỉ có một địa chỉ mặc định” cần UNIQUE có điều kiện hoặc mô hình dữ liệu khác tùy DBMS; CHECK thông thường không thể đếm các hàng khác để giải quyết.

Đặt CHECK đúng chỗ: quy tắc nên mang tính cục bộ của một hàng và database có thể kiểm tra ổn định khi hàng đó được ghi.

## 5. Những kiểu biểu thức CHECK thường gặp

### 5.1. Miền giá trị số

~~~sql
CHECK (quantity BETWEEN 1 AND 999)
CHECK (discount_percent >= 0 AND discount_percent <= 100)
CHECK (credit_limit >= 0)
~~~

Với số thập phân, cần thống nhất kiểu DECIMAL/NUMERIC thay vì dùng kiểu số thực dấu phẩy động cho tiền khi yêu cầu so sánh chính xác.

### 5.2. Tập trạng thái nhỏ và ổn định

~~~sql
CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
~~~

Cách này phù hợp khi tập trạng thái nhỏ, tương đối ổn định và có thể quản lý qua migration. Nếu trạng thái được thêm thường xuyên, có metadata riêng hoặc quan hệ tham chiếu, **bảng lookup + FOREIGN KEY** có thể phù hợp hơn.

### 5.3. Quan hệ giữa các cột trong một hàng

~~~sql
CHECK (closed_at IS NULL OR closed_at >= opened_at)
CHECK (min_price <= max_price)
~~~

Nhớ kiểm tra NULL: nếu min_price và max_price bắt buộc, định nghĩa NOT NULL riêng. Nếu một cột được phép thiếu, điều kiện nên mô tả rõ trạng thái thiếu đó.

### 5.4. Quy tắc có điều kiện theo trạng thái

~~~sql
CHECK (
    status <> 'PAID'
    OR paid_at IS NOT NULL
)
~~~

Đây là quy tắc “nếu trạng thái PAID thì phải có paid_at”. Có thể cần quy tắc đối xứng khác nếu dữ liệu ở trạng thái khác không được có paid_at.

### 5.5. Những biểu thức nên thận trọng hoặc tránh

- Hàm không ổn định theo thời gian, timezone hoặc cấu hình phiên làm việc.
- Hàm tự viết đọc bảng khác, phụ thuộc dữ liệu bên ngoài hoặc có tác dụng phụ.
- Biểu thức thay đổi ngữ nghĩa khi nâng cấp DBMS.
- Kiểm tra phức tạp mà đội ngũ khó xác định cách xử lý NULL, collation hoặc các kiểu dữ liệu khác nhau.
- Quy tắc nghiệp vụ phụ thuộc nhiều hàng, nhiều bảng hoặc tác động đồng thời mà CHECK thông thường không thể bảo đảm.

CHECK tốt là biểu thức **đơn giản, xác định, kiểm thử được và gần với bất biến dữ liệu**.

## 6. Ba cách khai báo CHECK trong dự án Liquibase

Khi lựa chọn cách khai báo, cần xét ít nhất ba yếu tố:

1. **Đang tạo bảng mới hay thêm constraint vào bảng có dữ liệu?**
2. **Phiên bản Liquibase và gói tính năng đang dùng hỗ trợ change type hoặc thuộc tính CHECK nào?**
3. **DBMS đích hỗ trợ cú pháp, hành vi và thao tác rollback nào?**

### Cách A: khai báo cùng định nghĩa bảng hoặc cột

Khi tạo bảng từ đầu, diễn đạt constraint ngay trong schema definition giúp reviewer thấy toàn bộ ràng buộc của bảng trong một nơi. Tùy phiên bản và edition Liquibase, các thuộc tính CHECK trong định nghĩa cột (chẳng hạn checkConstraint khi khả dụng) có thể được hỗ trợ ở change type có cấu trúc.

Ví dụ minh họa **chỉ áp dụng khi phiên bản/edition và DBMS xác nhận hỗ trợ thuộc tính này**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001
      author: schema-team
      changes:
        - createTable:
            tableName: inventory_item
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: quantity
                  type: INT
                  constraints:
                    nullable: false
                    checkConstraint: "quantity >= 0"
~~~

Ví dụ cho thấy **vị trí muốn khai báo**; đừng mặc định phần checkConstraint được mọi bản Liquibase Community nhận biết. Trước khi sử dụng, hãy kiểm tra tài liệu tương thích của bản đang cài, xác thực bằng **validate**, tạo **update-sql** và xác nhận database thật sự có constraint sau update. Nếu thuộc tính không được hỗ trợ, dùng change type dành riêng cho CHECK (nếu khả dụng) hoặc SQL tùy chỉnh.

**Ưu điểm:** mô tả schema gọn, dễ thấy ràng buộc cùng cột. **Giới hạn:** khả năng hỗ trợ thuộc tính và tên constraint có thể khác theo Liquibase/DBMS; với biểu thức nhiều cột, khai báo ở cấp bảng thường dễ đọc hơn.

### Cách B: change type addCheckConstraint nếu phiên bản/edition hỗ trợ

Một số bản phân phối/edition Liquibase cung cấp **addCheckConstraint** (có thể nằm trong nhóm tính năng Liquibase Secure). Cần xác nhận entitlement, bản Liquibase cụ thể và hỗ trợ của DBMS trước khi dùng trong dự án.

Ví dụ về dạng khai báo có cấu trúc khi tính năng khả dụng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-002
      author: schema-team
      changes:
        - addCheckConstraint:
            tableName: inventory_item
            constraintName: ck_inventory_item_quantity_nonnegative
            constraintBody: "quantity >= 0"
~~~

Với change type này, Liquibase có thể hỗ trợ cách sinh SQL tương ứng cho DBMS được liệt kê trong tài liệu của chính phiên bản đó. Không nên giả định có auto rollback trên mọi DBMS; cần khai báo hoặc kiểm tra rollback theo cơ chế được hỗ trợ.

**Ưu điểm:** ý định tạo CHECK và tên constraint thể hiện rõ ở metadata; thuận lợi nếu có nhiều hệ quản trị được hỗ trợ chính thức. **Giới hạn:** phụ thuộc tính năng được cấp, version, hỗ trợ DBMS và mức biểu đạt của change type.

### Cách C: sử dụng SQL tùy chỉnh theo DBMS

Khi change type CHECK không sẵn có hoặc cần cú pháp đặc thù của DBMS, dùng **sql** hoặc **sqlFile** trong changeset. Đây là cách chủ động và dễ kiểm soát SQL thực thi, nhưng sẽ phụ thuộc hệ quản trị và đòi hỏi khai báo rollback tương ứng.

Ví dụ PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-003
      author: schema-team
      dbms: postgresql
      comment: Ràng buộc số lượng tồn kho không âm
      changes:
        - sql:
            sql: >
              ALTER TABLE public.inventory_item
              ADD CONSTRAINT ck_inventory_item_quantity_nonnegative
              CHECK (quantity >= 0)
      rollback:
        - sql:
            sql: >
              ALTER TABLE public.inventory_item
              DROP CONSTRAINT ck_inventory_item_quantity_nonnegative
~~~

Đây là một changeset cho PostgreSQL, có SQL và rollback tương ứng. Nếu dự án phải hỗ trợ thêm MySQL, SQL Server hoặc Oracle, cần khai báo cách triển khai **tương đương về ý nghĩa** cho từng DBMS hoặc chọn change type có hỗ trợ, thay vì chỉ dùng dbms: postgresql rồi vô tình bỏ qua ràng buộc ở các môi trường khác.

**Ưu điểm:** linh hoạt, biểu đạt được DDL riêng của DBMS, có thể dùng những tính năng như NOT VALID trên PostgreSQL. **Giới hạn:** cần kiểm tra thủ công SQL, rollback, cú pháp identifier, quoting và khả năng tương thích.

## 7. Bảng quyết định chọn cách khai báo

| Tình huống | Lựa chọn nên đánh giá trước | Điểm phải kiểm tra |
|---|---|---|
| Bảng mới, CHECK đơn giản | Khai báo ngay khi tạo bảng nếu được hỗ trợ | Edition, thuộc tính CHECK, tên constraint, SQL sinh ra |
| Bảng đã tồn tại, cần thêm CHECK | addCheckConstraint khi khả dụng | Gói tính năng, DBMS, dữ liệu hiện có, rollback |
| Liquibase không có change type CHECK phù hợp | sql/sqlFile riêng cho DBMS | Cú pháp, dbms filter, rollback, kiểm thử trên DB đích |
| CHECK cần nhiều cột trong cùng hàng | Constraint cấp bảng hoặc addCheckConstraint/sql | NULL semantics, kiểu cột, biểu thức xác định |
| Bảng lớn cần trì hoãn kiểm tra dữ liệu cũ | DDL riêng DBMS, ví dụ PostgreSQL NOT VALID | Dữ liệu mới phải được kiểm tra, thời điểm VALIDATE |
| Hệ thống hỗ trợ nhiều DBMS | Change type chính thức nếu hỗ trợ, hoặc nhiều changeset có dbms rõ | Ngữ nghĩa tương đương trên từng DBMS |
| Quy tắc cần uniqueness hoặc khóa ngoại | UNIQUE/FK/unique index theo mục tiêu | CHECK không thay thế tính duy nhất và tham chiếu |
| Quy tắc cần đọc nhiều hàng/bảng | Thiết kế dữ liệu, constraint khác hoặc cơ chế phù hợp | Tránh ép CHECK làm việc không được bảo đảm |

Đây là **khung lựa chọn**, không phải bảng cam kết mọi lệnh đều chạy được ở tất cả phiên bản. Trong nội bộ dự án, nên ghi rõ phiên bản Liquibase và DBMS làm chuẩn kiểm thử.

## 8. Đặt tên constraint để quản trị thay đổi

Tên CHECK nên mang ý nghĩa nghiệp vụ, ổn định và có thể tìm kiếm trong log:

~~~text
ck_<table>_<meaning>
ck_order_item_quantity_positive
ck_order_item_unit_price_nonnegative
ck_purchase_order_total_nonnegative
ck_subscription_end_after_start
~~~

Lợi ích của tên tường minh:

- Dễ nhận diện lỗi trong log ứng dụng khi INSERT/UPDATE vi phạm.
- Dễ truy vấn catalog của database để kiểm tra constraint có tồn tại và có hợp lệ hay không.
- Dễ viết rollback đúng đối tượng.
- Dễ quản lý thay đổi khi CHECK phải được thay thế bằng biểu thức mới.

Không nên tùy tiện đổi tên hoặc chỉnh sửa changeset đã chạy: Liquibase nhận diện changeset qua **id, author và đường dẫn changelog**, đồng thời kiểm tra checksum. Muốn thay đổi quy tắc CHECK, thêm changeset mới làm rõ thao tác thay thế hoặc điều chỉnh.

Đối với tên dài, kiểm tra giới hạn độ dài identifier của DBMS. Trên PostgreSQL, identifier có giới hạn độ dài byte ở cấu hình thông thường; tên quá dài có thể bị cắt và gây nhầm lẫn.

## 9. Kiểm tra dữ liệu trước khi thêm CHECK

**Quan trọng:** thêm một CHECK vào bảng đang có dữ liệu có thể thất bại ngay nếu database yêu cầu xác thực dữ liệu hiện hữu và có hàng vi phạm.

Giả sử sẽ thêm:

~~~sql
CHECK (total_amount >= 0)
~~~

Với cột total_amount cho phép NULL, truy vấn phát hiện **hàng có giá trị âm**:

~~~sql
SELECT id, total_amount
FROM purchase_order
WHERE total_amount < 0;
~~~

Nếu nghiệp vụ còn yêu cầu giá trị bắt buộc có mặt, phải kiểm tra cả NULL:

~~~sql
SELECT id, total_amount
FROM purchase_order
WHERE total_amount IS NULL OR total_amount < 0;
~~~

Hai truy vấn không tương đương, vì **CHECK (total_amount >= 0) vẫn chấp nhận NULL**. Nếu cần cấm NULL, dùng thêm NOT NULL hoặc biểu thức CHECK rõ ràng.

### Thứ tự xử lý dữ liệu

1. Khảo sát schema hiện tại: kiểu cột, nullability, giá trị mặc định và constraint đã có.
2. Xác định biểu thức CHECK và tập giá trị được phép theo nghiệp vụ.
3. Chạy truy vấn tìm dữ liệu vi phạm trên bản sao có dữ liệu tương ứng.
4. Thống nhất cách sửa dữ liệu sai: cập nhật, loại bỏ, bổ sung dữ liệu hoặc đưa vào quy trình xử lý thủ công.
5. Chạy backfill hoặc sửa dữ liệu bằng changeset riêng, có kiểm chứng và kế hoạch rollback.
6. Tạo CHECK sau khi dữ liệu đã đáp ứng điều kiện, hoặc dùng phương án kiểm tra theo giai đoạn nếu DBMS hỗ trợ.
7. Xác nhận constraint đã được database ghi nhận và hoạt động đúng.

**Không đặt onFail: MARK_RAN chỉ vì dữ liệu chưa đạt**. MARK_RAN có thể đánh dấu changeset như đã chạy dù không tạo constraint, khiến lịch sử triển khai che giấu quy tắc chưa được bảo vệ.

## 10. Ví dụ migration an toàn trên bảng đã có dữ liệu

Giả sử bảng **purchase_order** đã có cột total_amount kiểu DECIMAL và cần bảo đảm giá trị không âm.

### Bước 1: khảo sát chất lượng dữ liệu

~~~sql
SELECT COUNT(*) AS negative_count
FROM public.purchase_order
WHERE total_amount < 0;
~~~

Không tự động biến giá trị âm thành 0 nếu chưa có xác nhận nghiệp vụ, bởi đó có thể là bản ghi hoàn tiền hoặc điều chỉnh kế toán có ý nghĩa.

### Bước 2: kiểm tra điều kiện trước DDL

Khi xây dựng changeset, dùng precondition cấp changeset để dừng nếu bảng chưa có:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-004
      author: schema-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: purchase_order
        - sqlCheck:
            expectedResult: "0"
            sql: >
              SELECT COUNT(*)
              FROM public.purchase_order
              WHERE total_amount < 0
      changes:
        - sql:
            sql: >
              ALTER TABLE public.purchase_order
              ADD CONSTRAINT ck_purchase_order_total_nonnegative
              CHECK (total_amount >= 0)
      rollback:
        - sql:
            sql: >
              ALTER TABLE public.purchase_order
              DROP CONSTRAINT ck_purchase_order_total_nonnegative
~~~

Đây là ví dụ cho PostgreSQL. **onFail: HALT** dừng nếu tiền điều kiện không đạt; **onError: HALT** dừng nếu không đánh giá được điều kiện. Cần chắc rằng cột total_amount tồn tại, đúng kiểu và tên constraint chưa bị dùng cho biểu thức khác; ví dụ này không thay thế kiểm tra toàn bộ schema.

Precondition có thể giảm rủi ro nhưng không loại bỏ hoàn toàn race condition giữa bước kiểm tra và bước DDL khi hệ thống có ghi dữ liệu đồng thời. DDL chính là nơi database bảo vệ bất biến.

### Bước 3: xác minh sau triển khai

- Kiểm tra changeset được ghi trong DATABASECHANGELOG theo kết quả mong đợi.
- Xác nhận tên constraint và biểu thức thật sự có trong catalog.
- Thử INSERT/UPDATE có giá trị hợp lệ và không hợp lệ trên database thử nghiệm.
- Kiểm tra application log khi database từ chối dữ liệu.
- Theo dõi lock, thời gian thực thi và ảnh hưởng giao dịch trong môi trường đích.

## 11. Bảng lớn: thêm CHECK theo giai đoạn với PostgreSQL

Khi bảng lớn đang phục vụ người dùng, việc thêm CHECK kèm kiểm tra toàn bộ dữ liệu cũ có thể tốn thời gian và gây ảnh hưởng vận hành. **PostgreSQL** hỗ trợ cách bổ sung CHECK bằng **NOT VALID**, sau đó **VALIDATE CONSTRAINT** trong bước riêng.

Ví dụ:

~~~sql
ALTER TABLE public.purchase_order
ADD CONSTRAINT ck_purchase_order_total_nonnegative
CHECK (total_amount >= 0) NOT VALID;
~~~

Sau khi thêm constraint với NOT VALID, PostgreSQL **kiểm tra các hàng mới hoặc hàng bị thay đổi** theo quy tắc CHECK, nhưng chưa chứng nhận tất cả hàng cũ đều hợp lệ. Khi dữ liệu cũ đã được khảo sát/sửa, chạy:

~~~sql
ALTER TABLE public.purchase_order
VALIDATE CONSTRAINT ck_purchase_order_total_nonnegative;
~~~

Có thể chia hai thao tác thành hai changeset để kiểm soát từng bước và quan sát trạng thái:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-005
      author: schema-team
      dbms: postgresql
      comment: Bảo vệ ghi mới trong khi chuẩn bị xác thực dữ liệu cũ
      changes:
        - sql:
            sql: >
              ALTER TABLE public.purchase_order
              ADD CONSTRAINT ck_purchase_order_total_nonnegative
              CHECK (total_amount >= 0) NOT VALID
      rollback:
        - sql:
            sql: >
              ALTER TABLE public.purchase_order
              DROP CONSTRAINT ck_purchase_order_total_nonnegative

  - changeSet:
      id: 2026-11-19-006
      author: schema-team
      dbms: postgresql
      comment: Xác minh toàn bộ dữ liệu cũ đáp ứng CHECK
      changes:
        - sql:
            sql: >
              ALTER TABLE public.purchase_order
              VALIDATE CONSTRAINT ck_purchase_order_total_nonnegative
~~~

Đối với changeset chỉ làm VALIDATE, cần **thiết kế rollback theo mục tiêu triển khai**: việc xác thực thành công không phải một đối tượng độc lập dễ đảo ngược về NOT VALID bằng một câu lệnh chuẩn đơn giản. Không tự tuyên bố changeset này có rollback đầy đủ. Nếu cần rollback release, có thể phải cân nhắc xóa constraint bằng thao tác được kiểm soát hoặc lựa chọn forward fix tùy trạng thái và yêu cầu nghiệp vụ.

**NOT VALID không có nghĩa constraint luôn bỏ qua mọi dữ liệu**, cũng không có nghĩa quá trình tạo/validate hoàn toàn không gây lock. Cần thử trên phiên bản PostgreSQL, dữ liệu và tải tương tự production; đánh giá loại khóa, độ dài chạy và cửa sổ triển khai trước khi áp dụng.

## 12. Những khác biệt DBMS cần kiểm tra

Các hệ quản trị phổ biến không giống nhau về cách khai báo, thực thi và thay đổi CHECK.

| Hệ quản trị | Lưu ý chính |
|---|---|
| **PostgreSQL** | Hỗ trợ CHECK; có NOT VALID và VALIDATE CONSTRAINT cho triển khai theo giai đoạn; DDL nhiều trường hợp nằm trong transaction |
| **MySQL** | CHECK được thực thi từ các phiên bản 8.0.16 trở lên; một số phiên bản cũ chấp nhận cú pháp nhưng không thực thi như mong đợi |
| **SQL Server** | Có CHECK và cơ chế quản lý constraint không được xác thực/trusted; cần kiểm tra trạng thái trong catalog sau migration |
| **Oracle** | Hỗ trợ CHECK và các chế độ enable/validate tương ứng; chú ý hành vi DDL và commit riêng của Oracle |
| **SQLite** | Hỗ trợ CHECK khi tạo bảng; các khả năng ALTER TABLE để thêm constraint có hạn chế, có thể cần tái tạo bảng |

Các thông tin trên là định hướng thiết kế; **khả năng chính xác phải kiểm tra theo phiên bản DBMS và Liquibase đang dùng**. Ví dụ, không thể mặc định một changelog SQL chứa NOT VALID của PostgreSQL chạy trên MySQL hoặc SQL Server.

Đối với dự án hỗ trợ nhiều DBMS, có hai cách chủ yếu:

1. **Change type có cấu trúc** khi Liquibase edition/version và DBMS hỗ trợ; kiểm tra SQL riêng cho từng DBMS.
2. **Changeset SQL theo DBMS** với dbms filter và SQL tương đương về ý nghĩa. Bảo đảm mọi DBMS được hỗ trợ đều có lối thực thi constraint phù hợp.

Đừng dùng một changeset chỉ dành cho PostgreSQL rồi xem migration đã hoàn thành trên các hệ quản trị khác nếu bất biến dữ liệu là yêu cầu bắt buộc.

## 13. CHECK, dữ liệu cũ và quy trình expand-contract

Thêm CHECK mạnh hơn có thể phá vỡ một phiên bản ứng dụng cũ vẫn ghi dữ liệu theo quy tắc trước đây.

Ví dụ, hiện trạng ứng dụng cũ ghi status trong tập NEW, PAID, CANCELLED; phiên bản mới muốn ràng buộc chỉ còn NEW và PAID. Nếu loại CANCELLED quá sớm, các instance ứng dụng chưa nâng cấp có thể gặp lỗi ghi.

Quy trình có thể là:

1. Phân tích mọi ứng dụng, job và pipeline đang ghi vào bảng.
2. Bổ sung mã ứng dụng để ngừng tạo dữ liệu không còn hợp lệ.
3. Di chuyển và chuẩn hóa dữ liệu cũ theo nghiệp vụ.
4. Chờ xác nhận các phiên bản cũ đã ngừng ghi.
5. Thêm hoặc siết CHECK trong migration mới.
6. Kiểm tra các truy vấn, alert và phản ứng của ứng dụng trước lỗi constraint.

Với kiến trúc triển khai rolling, **tương thích ứng dụng và schema** quan trọng ngang với sự đúng đắn của một changeset riêng lẻ.

## 14. Thay đổi hoặc bỏ CHECK đã phát hành

Một CHECK đang tồn tại là một phần của hợp đồng dữ liệu. Khi cần thay đổi, thường không sửa changeset gốc đã triển khai; thay vào đó tạo changeset mới.

Một quy trình thay đổi từ constraint A sang B:

1. Xác định biểu thức hiện tại và kết quả mới mong muốn.
2. Kiểm tra dữ liệu có vi phạm B không, cùng tác động đối với các phiên bản ứng dụng đang hoạt động.
3. Thiết kế thứ tự thao tác phù hợp DBMS: có thể cần drop constraint cũ rồi add constraint mới, hoặc dùng cơ chế khác nếu được hỗ trợ.
4. Thiết kế rollback rõ ràng: nếu quay lại biểu thức cũ, dữ liệu mới phát sinh trong thời gian dùng B có còn hợp lệ với A không?
5. Chạy thử trên bản sao database có dữ liệu thực tế, đặc biệt khi thay đổi siết chặt điều kiện.
6. Lưu lịch sử changeset mới, không ghi đè changeset cũ hoặc xóa lịch sử DATABASECHANGELOG.

Trên PostgreSQL, ví dụ thay đổi CHECK có thể gồm:

~~~sql
ALTER TABLE public.inventory_item
DROP CONSTRAINT ck_inventory_item_quantity_nonnegative;

ALTER TABLE public.inventory_item
ADD CONSTRAINT ck_inventory_item_quantity_positive
CHECK (quantity > 0);
~~~

Nếu quantity hiện có bằng 0, lệnh thêm constraint mới sẽ thất bại. Hai câu lệnh trên chỉ minh họa logic thay đổi, không phải script production hoàn chỉnh; cần xác định transaction, dữ liệu, thứ tự, lock và rollback trước khi chạy.

**Không dùng clear-checksums để né validate khi changeset cũ bị sửa.** Bảo toàn lịch sử tạo điều kiện tái tạo database mới và nâng cấp database đã tồn tại theo cùng chuỗi thay đổi.

## 15. Precondition và nguy cơ MARK_RAN sai

Precondition giúp xác minh tiền đề trước khi tạo CHECK, ví dụ bảng phải tồn tại, cột phải có đúng kiểu, không có hàng vi phạm.

Nhưng cần phân biệt:

- **HALT:** dừng nếu điều kiện bắt buộc không đạt.
- **WARN:** cảnh báo và vẫn cho phép thực hiện thay đổi, chỉ phù hợp với kiểm tra mang tính quan sát.
- **CONTINUE:** bỏ qua changeset trong lần hiện tại, giữ khả năng xét lại sau; có thể để release thiếu constraint.
- **MARK_RAN:** đánh dấu changeset đã hoàn thành mà không thực thi SQL; dễ che giấu constraint chưa tồn tại hoặc tồn tại sai biểu thức.

Nếu phát hiện constraint cùng tên đã tồn tại, **không nên tự động MARK_RAN**. Trước hết phải so sánh schema, tên bảng, biểu thức CHECK và trạng thái xác thực/thực thi constraint. Một constraint có tên đúng nhưng biểu thức khác có thể khiến dữ liệu vi phạm quy tắc mà ứng dụng mong đợi.

Trên PostgreSQL, có thể kiểm tra thông tin constraint bằng catalog:

~~~sql
SELECT n.nspname AS schema_name,
       t.relname AS table_name,
       c.conname AS constraint_name,
       c.convalidated,
       pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname = 'purchase_order'
  AND c.contype = 'c';
~~~

Đây là truy vấn **chỉ đọc** hỗ trợ đối chiếu constraint. Không nên dựa vào tên constraint đơn thuần để kết luận dữ liệu đã được bảo vệ đúng.

## 16. Rollback của CHECK cần hiểu đúng

Thêm CHECK rồi rollback bằng **DROP CONSTRAINT** thường chỉ **bỏ quy tắc bảo vệ dữ liệu**. Thao tác đó không làm mọi dữ liệu quay trở lại trạng thái trước khi áp dụng.

Ví dụ:

~~~sql
ALTER TABLE public.purchase_order
DROP CONSTRAINT ck_purchase_order_total_nonnegative;
~~~

Sau khi xóa constraint, database có thể lại cho phép các giá trị mà trước đó bị chặn. Không có dữ liệu nào tự được phục hồi hoặc đảo ngược chỉ nhờ lệnh này.

Khi viết rollback, cần trả lời:

- Đối tượng được xóa có đúng constraint do changeset tạo không?
- Nếu dùng nhiều DBMS, cú pháp xóa CHECK có giống nhau không?
- Nếu rollback một release có nhiều thay đổi phụ thuộc constraint, thứ tự rollback có an toàn không?
- Nếu thay constraint A bằng B, có thể quay lại A sau khi dữ liệu đã được ghi theo B không?
- Constraint có đang ở trạng thái NOT VALID hoặc chưa được xác thực toàn bộ không?
- Có cần forward fix thay vì rollback do nguy cơ dữ liệu/ứng dụng không tương thích?

Liquibase có thể hỗ trợ auto rollback cho một số change type, nhưng **không mặc định rằng CHECK nào cũng được tự hoàn tác đúng ở mọi edition/DBMS**. Với SQL tùy chỉnh, nên khai báo rollback tường minh và kiểm chứng SQL rollback trên hệ quản trị đích.

## 17. Quy trình kiểm chứng trong Spring Boot và CI/CD

Spring Boot có thể dùng Liquibase để cập nhật schema khi ứng dụng khởi động, hoặc dự án có thể chạy migration trong một bước CI/CD được điều phối. Dù dùng cách nào, một CHECK mới cần được kiểm chứng như một hợp đồng dữ liệu.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Quy trình triển khai khuyến nghị:

1. **Review nghiệp vụ:** biểu thức CHECK có đúng phạm vi, xử lý NULL và dữ liệu hiện hữu?
2. **Kiểm tra khả năng hỗ trợ:** Liquibase edition/version và DBMS có chấp nhận change type/SQL được chọn?
3. **Dữ liệu cũ:** truy vấn phát hiện hàng vi phạm, thống nhất backfill và xác nhận cách xử lý.
4. **Chạy validate và tạo SQL dự kiến:** đối chiếu SQL trên đúng DBMS, không dựa vào YAML như bằng chứng cuối cùng.
5. **Thử trên database mới và bản sao database đã có lịch sử:** kiểm tra lỗi khi thêm CHECK và khả năng nâng cấp.
6. **Kiểm tra constraint thực tế:** xem tên, biểu thức, trạng thái thực thi/xác thực và hành vi từ chối dữ liệu sai.
7. **Đánh giá tải hệ thống:** lock, scan dữ liệu, thời gian DDL và giao dịch theo DBMS.
8. **Review rollback/forward fix:** xác định cách khôi phục khi lệnh tạo hoặc xác thực constraint thất bại.
9. **Triển khai có kiểm soát:** bảo đảm không có nhiều đầu mối migration chạy chồng chéo.
10. **Hậu kiểm:** so sánh DATABASECHANGELOG với trạng thái database và theo dõi lỗi ứng dụng.

Các lệnh CLI phổ biến khi đã cung cấp cấu hình kết nối và changelog:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

**validate** kiểm tra những vấn đề Liquibase có thể xác định; **status** cho biết changeset chờ chạy; **update-sql** giúp review SQL; **update** triển khai; **history** hỗ trợ đối chiếu lịch sử. Chúng không thay thế bài thử INSERT/UPDATE với giá trị đúng và sai, cũng không tự chứng minh hiệu năng trên bảng production.

### Checklist dành cho reviewer

- [ ] CHECK thực sự phù hợp hơn NOT NULL, UNIQUE, FOREIGN KEY hoặc ràng buộc khác.
- [ ] Biểu thức chỉ phụ thuộc dữ liệu được phép và có ngữ nghĩa ổn định.
- [ ] Đã kiểm tra logic TRUE/FALSE/UNKNOWN và trường hợp NULL.
- [ ] Tên constraint rõ nghĩa, ổn định, không xung đột.
- [ ] Chọn change type theo Liquibase edition/version và DBMS thực tế.
- [ ] Có kết quả kiểm tra dữ liệu cũ và hướng xử lý khi phát hiện giá trị vi phạm.
- [ ] Có precondition phù hợp, ưu tiên HALT nếu không chắc trạng thái database.
- [ ] SQL dự kiến đã được review, nhất là khi dùng sql/sqlFile riêng cho DBMS.
- [ ] Đã chạy thử trên database trống và database có DATABASECHANGELOG cũ.
- [ ] Đã kiểm tra constraint trong catalog sau khi áp dụng.
- [ ] Đã đánh giá lock, scan, dữ liệu lớn và khả năng triển khai theo giai đoạn.
- [ ] Rollback hoặc forward fix đã được thiết kế và kiểm chứng.

## 18. Tình huống thực hành

### Bài toán

Ứng dụng đặt hàng có bảng purchase_order gồm các cột:

~~~text
id              BIGINT, primary key
status          VARCHAR(20), NOT NULL
total_amount    DECIMAL(18, 2), NOT NULL
created_at      TIMESTAMP, NOT NULL
paid_at         TIMESTAMP, nullable
~~~

Yêu cầu nghiệp vụ:

1. total_amount không được âm.
2. status chỉ nằm trong NEW, PAID, CANCELLED.
3. Nếu status là PAID thì paid_at phải có giá trị.
4. paid_at nếu có phải không sớm hơn created_at.
5. Bảng có hàng triệu dòng và có các phiên bản ứng dụng đang chạy đồng thời.

### Phân tích đề xuất

Có thể thiết kế các CHECK với tên riêng:

~~~sql
CHECK (total_amount >= 0)

CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))

CHECK (status <> 'PAID' OR paid_at IS NOT NULL)

CHECK (paid_at IS NULL OR paid_at >= created_at)
~~~

NOT NULL của total_amount, status và created_at phải được khai báo độc lập. CHECK thứ tư phụ thuộc created_at bắt buộc có giá trị; nếu created_at nullable thì phải bổ sung kiểm tra tương ứng.

Một kế hoạch triển khai:

1. Khảo sát các giá trị total_amount âm, status ngoài danh sách, PAID thiếu paid_at, paid_at trước created_at.
2. Điều tra và chỉnh dữ liệu theo quy tắc nghiệp vụ, không tự gán tất cả dữ liệu lỗi về một giá trị mặc định.
3. Đảm bảo ứng dụng đang chạy không còn ghi những hàng vi phạm.
4. Dùng change type CHECK có cấu trúc khi edition/version/DBMS hỗ trợ, hoặc SQL DDL phù hợp.
5. Với PostgreSQL và bảng lớn, cân nhắc NOT VALID trước, sau đó xử lý dữ liệu cũ và VALIDATE CONSTRAINT ở bước có thể giám sát.
6. Kiểm tra hành vi database khi ghi từng trường hợp hợp lệ và không hợp lệ.
7. Theo dõi lịch sử DATABASECHANGELOG và xác minh constraint trong catalog.
8. Chuẩn bị rollback hoặc forward fix và đánh giá ảnh hưởng khi tắt constraint.

### Câu hỏi tự kiểm tra

- Nếu total_amount cho phép NULL, CHECK (total_amount >= 0) có tự cấm NULL không? **Không**.
- CHECK (status IN (...)) có thay thế UNIQUE(status) không? **Không**; nhiều hàng được phép có cùng trạng thái.
- Có thể dùng CHECK để bảo đảm customer_id tồn tại ở bảng customer không? **Không phù hợp**; dùng FOREIGN KEY.
- Khi có dữ liệu cũ vi phạm, có nên MARK_RAN changeset tạo CHECK không? **Không**, trừ tình huống khác đã được chứng minh tương đương và được review; ở đây quy tắc còn thiếu.
- Nếu CHECK đã chạy ở staging, có nên sửa trực tiếp changeset để thêm một trạng thái mới không? **Không**; tạo changeset mới.
- Nếu DBMS chấp nhận khai báo CHECK nhưng không thực thi, validate thành công có đủ làm bằng chứng không? **Không**; phải kiểm tra trên database thực tế.

## 19. Ghi nhớ

**CHECK** phù hợp để database bảo vệ điều kiện trên hàng dữ liệu như miền số, tập trạng thái, giới hạn tỷ lệ và quan hệ giữa các cột. Nhưng CHECK chỉ từ chối biểu thức **FALSE**; trường hợp **UNKNOWN** do NULL cần được xử lý có chủ đích bằng NOT NULL hoặc logic kiểm tra rõ ràng.

Với Liquibase, cách khai báo phụ thuộc tình huống: có thể đưa CHECK vào định nghĩa bảng nếu tính năng được hỗ trợ; dùng **addCheckConstraint** khi phiên bản/edition cho phép; hoặc dùng **sql/sqlFile** khi cần chủ động cú pháp DBMS. Hãy kiểm tra tính khả dụng thay vì giả định mọi bản Liquibase và mọi hệ quản trị đều tương thích.

Một migration CHECK đáng tin cậy phải có **biểu thức đúng, tên constraint rõ ràng, kiểm tra dữ liệu cũ, SQL được review, xác minh constraint thực tế, kế hoạch rollback và lịch sử changeset ổn định**. Khi nhiều môi trường hoặc nhiều phiên bản ứng dụng cùng hoạt động, chất lượng thiết kế và quy trình triển khai quan trọng không kém cú pháp tạo constraint.
