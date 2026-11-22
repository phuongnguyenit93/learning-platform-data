# Hàm dựng sẵn, hàm SQL và đăng ký hàm mở rộng

HQL cho phép gọi hàm trong biểu thức `SELECT`, `WHERE`, `ORDER BY`, `GROUP BY` và nhiều vị trí khác. Có ba nhóm cần phân biệt:

1. **Hàm chuẩn của JPQL/Jakarta Persistence** như `lower`, `upper`, `length`, `substring`, `trim`, `abs`, `sqrt`, `mod`, `coalesce`, `nullif`, `concat`, `locate`, `current_date`, `current_time`, `current_timestamp` và các hàm aggregate.
2. **Hàm HQL/Hibernate bổ sung** như các hàm xử lý chuỗi, số, ngày giờ, collection, JSON, window/ordered-set functions và những hàm được Hibernate nhận diện theo phiên bản/dialect.
3. **Hàm SQL riêng của database** như `date_trunc`, `jsonb_extract_path_text`, `regexp_replace`, `string_agg`, `array_agg` hoặc hàm do tổ chức tự tạo.

Một hàm SQL có sẵn trong database chưa chắc Hibernate biết tên, cú pháp và kiểu trả về của nó. Có thể gọi hàm bằng `function('tên_hàm', ...)` trong cú pháp portable của JPQL hoặc dùng cú pháp HQL `function(...)`; khi cần Hibernate hiểu hàm như một thành phần ngôn ngữ có kiểu, khả năng kiểm tra và dịch theo dialect, có thể **đăng ký hàm mở rộng** qua `FunctionContributor` và `FunctionRegistry`.

Bài học giải thích cách chọn đúng loại hàm, viết truy vấn an toàn, kiểm soát kiểu dữ liệu/null, đăng ký hàm trong Hibernate hiện đại, kiểm thử SQL được sinh và quản lý khác biệt giữa các DBMS.

## 1. Hàm trong HQL được xử lý ở đâu?

Ví dụ:

```hql
select lower(c.email)
from Customer c
where length(c.email) > 10
```

HQL không gửi nguyên văn đoạn query này cho database. Hibernate phân tích query thành mô hình truy vấn, kiểm tra entity/attribute và biểu thức, sau đó dịch sang SQL phù hợp với dialect.

Luồng khái niệm:

```text
HQL/JPQL
  |
  v
Parser + Semantic Query Model
  |
  v
Kiểm tra entity, path, hàm và kiểu dữ liệu
  |
  v
SQL AST + Dialect/function rendering
  |
  v
SQL + bind parameters
  |
  v
JDBC driver
  |
  v
Database
```

Ví dụ HQL:

```hql
select lower(c.email)
from Customer c
```

có thể thành SQL:

```sql
select lower(c.email)
from customers c;
```

Nhưng một hàm có cú pháp khác giữa database có thể được Hibernate dịch thành SQL khác. Vì vậy HQL function không đơn giản là “ghép chuỗi tên SQL vào query”.

### 1.1. Hàm nhận entity attribute, không phải tên cột tùy ý

Trong HQL:

```hql
select lower(c.email)
from Customer c
```

`c.email` là thuộc tính Java được ánh xạ, không nhất thiết trùng tên cột vật lý. Hibernate dùng metadata mapping để tạo SQL.

Không viết tên cột SQL vào HQL:

```hql
-- Sai nếu email_address chỉ là tên cột DB, không phải attribute Java
select lower(c.email_address)
from Customer c
```

Trừ khi entity thực sự có property `email_address`, path expression phải dùng tên attribute trong mô hình entity.

### 1.2. Hàm không thay thế query parameter

Giá trị đầu vào nên được bind:

```java
em.createQuery("""
    select c
    from Customer c
    where lower(c.email) = lower(:email)
    """, Customer.class)
  .setParameter("email", email)
  .getResultList();
```

Không nối dữ liệu người dùng vào query string. Binding bảo vệ giá trị khỏi SQL injection và giữ query plan có thể tái sử dụng tốt hơn.

## 2. Nhóm hàm chuẩn của JPQL

Jakarta Persistence định nghĩa tập hàm portable để query có thể chạy trên nhiều provider/database, miễn là kiểu dữ liệu và semantics phù hợp.

### 2.1. Hàm chuỗi

| Hàm | Mục đích | Ví dụ |
| --- | --- | --- |
| `CONCAT(a, b)` | Nối hai chuỗi | `concat(c.firstName, c.lastName)` |
| `SUBSTRING(s, start, length)` | Lấy chuỗi con; vị trí bắt đầu theo semantics JPQL | `substring(c.code, 1, 3)` |
| `TRIM(s)` | Loại khoảng trắng ở đầu/cuối | `trim(c.name)` |
| `LOWER(s)` | Chuyển thành chữ thường | `lower(c.email)` |
| `UPPER(s)` | Chuyển thành chữ hoa | `upper(c.email)` |
| `LENGTH(s)` | Độ dài chuỗi | `length(c.name)` |
| `LOCATE(pattern, s[, start])` | Vị trí chuỗi con | `locate('@', c.email)` |

Ví dụ:

```hql
select c.id, upper(trim(c.name))
from Customer c
where locate('@', c.email) > 0
```

`LOCATE` theo JPQL trả vị trí bắt đầu theo quy ước chỉ số từ 1; nếu không tìm thấy, kết quả là 0. Đừng nhầm với `String.indexOf()` trong Java, vốn bắt đầu từ 0.

### 2.2. Hàm số học

| Hàm | Mục đích |
| --- | --- |
| `ABS(x)` | Giá trị tuyệt đối |
| `SQRT(x)` | Căn bậc hai |
| `MOD(x, y)` | Phần dư |
| `SIZE(collection)` | Số phần tử của collection-valued association |

Ví dụ:

```hql
select p
from Product p
where abs(p.price - :targetPrice) < :tolerance
```

```hql
select p.name, mod(p.stock, 10)
from Product p
```

`SIZE(p.reviews)` là hàm collection chuẩn JPQL trên collection association. Nó không giống `employees.size()` trong Java; nó là biểu thức query và provider sẽ dịch sang SQL phù hợp, thường có subquery/count.

### 2.3. Hàm ngày giờ chuẩn

```hql
select current_date, current_time, current_timestamp
from Customer c
```

Các hàm chuẩn:

- `CURRENT_DATE`
- `CURRENT_TIME`
- `CURRENT_TIMESTAMP`

Kiểu Java/SQL tương ứng phụ thuộc phiên bản Jakarta Persistence và mapping temporal; dùng đúng kiểu kết quả khi tạo typed query hoặc projection. Hàm lấy thời gian thường dựa vào clock của database, không nhất thiết giống `LocalDateTime.now()` của JVM.

### 2.4. Hàm null và lựa chọn giá trị

```hql
select coalesce(c.displayName, c.email, 'Unknown')
from Customer c
```

- `COALESCE(a, b, ...)`: trả biểu thức đầu tiên khác null.
- `NULLIF(a, b)`: trả null nếu hai biểu thức bằng nhau; nếu khác nhau trả giá trị thứ nhất.

Ví dụ tránh chia cho 0:

```hql
select o.total / nullif(o.itemCount, 0)
from OrderSummary o
```

Cần đảm bảo kiểu toán học/SQL phù hợp; `NULLIF` làm mẫu số thành null khi bằng 0, nên kết quả phép chia có thể là null thay vì lỗi chia cho 0. Cách xử lý null trong kết quả vẫn phải theo business rule.

### 2.5. Hàm aggregate

Các hàm aggregate chuẩn:

- `COUNT`
- `SUM`
- `AVG`
- `MIN`
- `MAX`

Ví dụ:

```hql
select c.status, count(c), avg(c.creditLimit)
from Customer c
group by c.status
having count(c) >= :minimum
```

Lưu ý:

- `COUNT` thường trả kiểu số nguyên dài theo JPQL.
- `SUM`/`AVG` có kiểu kết quả phụ thuộc kiểu đầu vào và đặc tả.
- `COUNT(expression)` bỏ qua giá trị null; `COUNT(*)`/`COUNT(entity)` có semantics khác theo query.
- Aggregate thường bỏ qua null, trừ `COUNT`/case đặc biệt.
- Không dùng `select c, count(c)` mà thiếu `GROUP BY` phù hợp nếu database/query language yêu cầu nhóm.

### 2.6. `CASE` cũng là biểu thức hữu ích

`CASE` không phải SQL function, nhưng thường được dùng cùng hàm:

```hql
select c.id,
       case
           when c.creditLimit >= 100000 then 'PREMIUM'
           when c.creditLimit >= 10000 then 'STANDARD'
           else 'BASIC'
       end
from Customer c
```

Có thể kết hợp:

```hql
select upper(
    case when c.displayName is null then c.email
         else c.displayName
    end
)
from Customer c
```

Đảm bảo các nhánh `CASE` có kiểu kết quả tương thích để Hibernate và database suy luận kiểu đúng.

## 3. Một số hàm HQL/Hibernate bổ sung

HQL hiện đại hỗ trợ nhiều hàm hơn tập JPQL cơ bản. Danh sách cụ thể phụ thuộc Hibernate version và dialect.

Ví dụ các nhóm có thể gặp:

| Nhóm | Hàm/biểu thức ví dụ | Công dụng |
| --- | --- | --- |
| Chuỗi | `replace`, `left`, `right`, `repeat`, `pad`, `reverse` | Biến đổi văn bản |
| Số học | `ceiling`, `floor`, `round`, `sign`, `power`, `log`, `exp` | Tính toán số |
| Ngày giờ | `extract`, `year`, `month`, `day`, `hour`, `minute`, `second`, `truncate` | Lấy thành phần hoặc làm tròn thời gian |
| Collection | `element`, `index`, `key`, `value`, `entry`, `elements`, `indices` | Truy vấn collection/map |
| Kiểu dữ liệu | `cast`, `str` | Chuyển đổi biểu thức |
| Null/logic | `coalesce`, `nullif`, `ifnull` (tùy dialect/function) | Xử lý null |
| Database-specific | `json_value`, `json_query`, `array_contains` hoặc hàm tương ứng | Truy vấn kiểu dữ liệu riêng DB |

Không phải mọi tên trong bảng đều là cú pháp portable giữa mọi version/dialect. Khi cần dùng trong dự án, hãy đối chiếu HQL reference của Hibernate đang chạy và generated SQL.

### 3.1. `EXTRACT` và các hàm thành phần thời gian

Ví dụ HQL hiện đại:

```hql
select extract(year from o.createdAt)
from PurchaseOrder o
```

Có thể viết gọn bằng hàm thành phần trong các phiên bản HQL hỗ trợ:

```hql
select year(o.createdAt), month(o.createdAt)
from PurchaseOrder o
```

`extract` biểu đạt việc lấy một phần của temporal value. Tên field như `year`, `month`, `day`, `hour`, `minute`, `second` không phải bind parameter thông thường; đó là cú pháp của biểu thức.

Nếu database có hàm `date_part` hoặc `date_trunc`, HQL có thể dịch biểu thức tương ứng theo dialect hoặc cần gọi function riêng. Không mặc định mọi DB hỗ trợ cùng một temporal function.

### 3.2. `CAST`

```hql
select cast(o.orderNumber as Integer)
from PurchaseOrder o
```

Dùng `CAST` khi cần đổi kiểu biểu thức. Tên kiểu HQL không nhất thiết là tên SQL type của từng DBMS; Hibernate ánh xạ kiểu đích sang SQL dialect.

Chỉ cast khi dữ liệu thực sự có thể chuyển đổi. Nếu `orderNumber` chứa `"PO-10"`, cast sang Integer sẽ thất bại ở database.

### 3.3. `STR` và biểu thức chuyển kiểu

Trong HQL, `str(x)` có thể được dùng để biểu diễn giá trị dưới dạng chuỗi trong những phiên bản hỗ trợ. Với query cần tính portable hoặc kiểu kết quả rõ ràng, ưu tiên `cast()` theo kiểu HQL phù hợp và kiểm tra semantics.

### 3.4. Hàm xử lý chuỗi mở rộng

Ví dụ:

```hql
select replace(lower(c.email), 'old-domain.com', 'new-domain.com')
from Customer c
```

`replace` có thể được hỗ trợ trong HQL/dialect hiện đại, nhưng nếu query cần chạy trên nhiều DBMS, hãy kiểm tra cách dịch và collation/case behavior.

## 4. Gọi hàm SQL có sẵn bằng `function()`

Nếu database có hàm mà JPQL không định nghĩa, có thể dùng cú pháp:

```hql
function('function_name', arg1, arg2, ...)
```

Ví dụ với PostgreSQL:

```hql
select function('date_trunc', 'month', o.createdAt)
from PurchaseOrder o
```

Hoặc gọi một hàm custom trong database:

```hql
select function('normalize_customer_code', c.code)
from Customer c
```

Cú pháp `function()` cho phép nêu tên hàm database và các đối số. Hibernate dịch lời gọi xuống SQL; database phải thực sự có hàm tương ứng và nhận kiểu đối số phù hợp.

### 4.1. `function()` không tự tạo hàm trong database

Đoạn HQL:

```hql
select function('normalize_customer_code', c.code)
from Customer c
```

chỉ gọi hàm có tên đó. Nó không tạo stored function, không tự cài extension PostgreSQL và không tự triển khai logic trong database.

Nếu hàm chưa tồn tại, database báo lỗi khi thực thi SQL. Cần triển khai DDL/function bằng migration phù hợp.

### 4.2. Tên hàm không phải bind parameter

Không viết:

```hql
select function(:functionName, c.code)
from Customer c
```

và mong parameter hóa identifier/function name. SQL parameter thường dùng cho **giá trị**, không thay thế tên function, tên bảng hoặc tên cột. Function name phải là một phần cấu trúc query đã được kiểm soát.

Nếu cần chọn một trong vài hàm, dùng whitelist ở code và tạo query tương ứng; không ghép tên do người dùng gửi trực tiếp.

### 4.3. Kiểu kết quả của hàm

Khi Hibernate không có metadata cho function, việc suy luận kiểu kết quả có thể bị giới hạn. Điều này ảnh hưởng:

- Typed query như `createQuery(..., String.class)`.
- Projection vào record/DTO.
- So sánh function result với giá trị khác.
- Arithmetic trên function result.
- Chuyển kiểu khi database trả numeric/temporal/vendor type.

Nếu cần kiểu rõ ràng, có thể dùng `cast()` hoặc đăng ký function descriptor với return type phù hợp. Không giả định mọi function trả `String`.

## 5. HQL `function()` và native SQL khác nhau

| Tiêu chí | HQL `function()` | Native SQL |
| --- | --- | --- |
| FROM/entity root | Dùng entity và association mapping | Dùng bảng/view và tên cột SQL |
| Function call | Gọi function của database | Gọi function trong SQL trực tiếp |
| Path expression | Dùng `o.customer.name` | Dùng join/column SQL |
| Portability | HQL/JPQL query giữ phần lớn entity semantics, nhưng function vẫn phụ thuộc DB | Phụ thuộc SQL dialect nhiều hơn |
| Result mapping | Có thể trả entity/scalar/tuple theo HQL | Cần result mapping phù hợp |
| Kiểm tra kiểu | Hibernate hiểu nhiều phần query, nhưng function lạ có thể thiếu metadata | SQL parser/database kiểm tra nhiều hơn khi chạy |
| Dùng khi | Chỉ cần một function riêng trong query ORM | Query phụ thuộc sâu vào cú pháp/feature database |

Ví dụ HQL:

```hql
select o.id, function('date_trunc', 'day', o.createdAt)
from PurchaseOrder o
```

Native SQL PostgreSQL:

```sql
select id, date_trunc('day', created_at)
from purchase_orders;
```

Native SQL phù hợp khi query cần CTE/vendor syntax/JSON operator/window feature đặc thù mà HQL không biểu đạt tiện lợi. Nhưng không chuyển sang native query chỉ vì một hàm đơn lẻ; `function()` hoặc function registration có thể giữ query ở mức entity model.

## 6. Đăng ký hàm mở rộng trong Hibernate hiện đại

Khi ứng dụng dùng cùng một function nhiều nơi, cần Hibernate biết:

- Tên logic của hàm trong HQL.
- Cách render SQL theo dialect.
- Số lượng/kiểu đối số.
- Kiểu kết quả.
- Những quy tắc kiểm tra/định dạng phù hợp.

Hibernate cung cấp **`FunctionContributor`** và **`FunctionRegistry`** để đăng ký function descriptor.

Ví dụ một function đơn giản `normalize_code()` được ánh xạ tới SQL `lower(trim(?1))`.

```java
package com.example.persistence;

import org.hibernate.boot.model.FunctionContributions;
import org.hibernate.boot.model.FunctionContributor;
import org.hibernate.type.StandardBasicTypes;

public class AppFunctionContributor implements FunctionContributor {

    @Override
    public void contributeFunctions(FunctionContributions contributions) {
        var stringType = contributions
            .getTypeConfiguration()
            .getBasicTypeRegistry()
            .resolve(StandardBasicTypes.STRING);

        contributions.getFunctionRegistry().registerPattern(
            "normalize_code",
            "lower(trim(?1))",
            stringType
        );
    }
}
```

Sau khi đăng ký, HQL có thể gọi:

```hql
select normalize_code(c.code)
from Customer c
```

Function registry hiểu `normalize_code` là function logic; SQL được render theo pattern đã đăng ký.

**Đây là ví dụ API Hibernate hiện đại; hãy kiểm tra đúng version Hibernate trong dự án.** Một số overload/kiểu đăng ký có thể thay đổi giữa các major versions.

### 6.1. `registerPattern()` hoạt động thế nào?

```java
registerPattern(
    "normalize_code",
    "lower(trim(?1))",
    stringType
);
```

- `"normalize_code"` là tên được dùng trong HQL.
- `"lower(trim(?1))"` là SQL pattern.
- `?1` là đối số thứ nhất theo vị trí trong function descriptor.
- `stringType` mô tả kiểu kết quả Hibernate nên sử dụng.

Khi HQL:

```hql
select normalize_code(c.code)
from Customer c
```

được dịch, Hibernate render SQL tương tự:

```sql
select lower(trim(c.code))
from customers c;
```

Không dùng placeholder `?1` như parameter JDBC do ứng dụng tự bind; đây là placeholder của function pattern trong API Hibernate.

### 6.2. Đăng ký function theo service loader

Một cách phổ biến để Hibernate phát hiện `FunctionContributor` là Java `ServiceLoader`.

Tạo file:

```text
src/main/resources/META-INF/services/org.hibernate.boot.model.FunctionContributor
```

Nội dung file là tên fully qualified class:

```text
com.example.persistence.AppFunctionContributor
```

Đảm bảo file được đóng gói trong artifact và class có thể load. Nếu contributor nằm trong module/JAR khác, kiểm tra classpath và cơ chế service loading của runtime.

Không chỉ tạo class mà quên service file; khi đó Hibernate có thể không gọi `contributeFunctions()` và HQL báo function chưa được đăng ký.

### 6.3. Không đăng ký lại tên hàm built-in tùy tiện

Hibernate đã đăng ký nhiều function theo dialect và HQL. Nếu contributor dùng cùng tên để ghi đè, có thể thay đổi semantics hoặc gây xung đột. Chọn namespace riêng như `app_normalize_code`, ghi rõ mục đích và kiểm thử trên từng dialect.

## 7. Đăng ký function với `register()` và descriptor

`registerPattern()` phù hợp với hàm có SQL rendering đơn giản. Nếu function cần kiểm tra đối số, return type động, argument type resolver, function kind hoặc SQL rendering phức tạp, cần đăng ký descriptor phù hợp.

API khái niệm:

```java
contributions.getFunctionRegistry().register(
    "app_function",
    functionDescriptor
);
```

`functionDescriptor` thường được xây dựng từ các builder/descriptor API trong package Hibernate query function. Tên builder và method cụ thể thay đổi theo version, vì vậy nên dùng Javadoc của Hibernate đang chạy thay vì sao chép một snippet từ major version khác.

Các nhu cầu nâng cao có thể gồm:

- `StandardFunctionReturnTypeResolvers` để xác định kiểu trả về.
- `StandardFunctionArgumentTypeResolvers` để suy luận/kiểm tra kiểu đối số.
- `ArgumentsValidator` để kiểm tra số lượng và kiểu tham số.
- `FunctionRenderingSupport`/SQL AST rendering cho cú pháp vendor-specific.
- Pattern khác nhau theo dialect.
- Function kind như normal, aggregate hoặc ordered-set/window tùy API.

Không cần tạo custom descriptor phức tạp cho một hàm chỉ có thể biểu diễn bằng `registerPattern()`.

### 7.1. Tại sao return type quan trọng?

Giả sử hàm:

```sql
calculate_tax(amount, rate)
```

trả numeric. Nếu Hibernate coi kết quả là String, query:

```hql
select calculate_tax(o.total, :rate) + 1
from PurchaseOrder o
```

có thể không được kiểm tra/biên dịch đúng hoặc gặp lỗi type conversion.

Đăng ký descriptor với kiểu trả về phù hợp giúp Hibernate hiểu biểu thức trong Semantic Query Model và SQL AST.

Không chọn `StandardBasicTypes.DOUBLE` chỉ vì muốn query chạy. Return type phải khớp với kết quả database, precision/scale và domain type cần dùng.

## 8. Tùy biến theo dialect/database

Giả sử cần hàm logic `app_truncate_day(timestamp)`:

- PostgreSQL có `date_trunc('day', timestamp)`.
- SQL Server có thể dùng biểu thức chuyển đổi kiểu ngày giờ.
- Một database khác có thể dùng `trunc(timestamp)` hoặc cú pháp riêng.

Không thể đăng ký một pattern SQL duy nhất rồi giả định mọi dialect hiểu nó.

Có các lựa chọn:

1. **Dùng hàm HQL chuẩn** như `truncate`/`extract` nếu Hibernate version hỗ trợ và semantics tương đương.
2. Đăng ký contributor/dialect-specific descriptor phù hợp từng DBMS.
3. Dùng một stored function cùng tên được triển khai trên mọi DBMS trong phạm vi ứng dụng.
4. Viết query native riêng theo từng dialect nếu feature thực sự không portable.
5. Tránh custom SQL function nếu phép biến đổi có thể làm ở Java mà không gây tải thừa hoặc sai pagination/filtering.

### 8.1. Tách logic theo dialect

Có thể dùng dialect được chọn để đăng ký descriptor tương ứng thông qua cơ chế bootstrap/integration phù hợp của Hibernate. Một contributor có thể kiểm tra thông tin service/function contributions và chọn renderer theo dialect, nhưng API truy cập dialect và builder thay đổi theo version.

Không hardcode tên class dialect cũ như `PostgreSQL95Dialect` vào mọi Hibernate 6/7 project. Các version mới dùng dialect detection/class naming khác. Hãy xem dialect runtime thực tế và Javadoc tương ứng.

### 8.2. Một tên function ổn định, nhiều SQL rendering

Một cách thiết kế tốt là cho HQL dùng tên logic:

```hql
select app_truncate_day(o.createdAt)
from PurchaseOrder o
```

Mỗi DBMS có renderer tương ứng:

```text
PostgreSQL  → date_trunc('day', ?1)
DBMS B      → <biểu thức ngày tương ứng>
DBMS C      → stored function app_truncate_day(?1)
```

Query nghiệp vụ không cần chứa SQL vendor syntax. Đây là một trong những lý do đăng ký function descriptor hữu ích.

## 9. Đăng ký function và custom Dialect

Trong các phiên bản Hibernate cũ, một số hướng dẫn đăng ký SQL function yêu cầu subclass `Dialect` và ghi đè `initializeFunctionRegistry()` hoặc dùng `MetadataBuilderContributor`.

Các hướng dẫn này có thể vẫn cần cho codebase cũ, nhưng với Hibernate hiện đại, **`FunctionContributor` là extension point chuyên biệt** cho function contributions.

Không copy ví dụ `registerFunction()` từ Hibernate 5 sang Hibernate 6/7 mà không kiểm tra. Những API như `SQLFunction`, `StandardSQLFunction`, `registerFunction()` cũ có thể đã thay đổi hoặc không còn là hướng đăng ký được khuyến nghị.

| Cách tiếp cận | Thường phù hợp |
| --- | --- |
| `FunctionContributor` | Đăng ký function mở rộng trong Hibernate hiện đại |
| `FunctionRegistry.registerPattern()` | Function SQL có thể mô tả bằng pattern |
| Custom function descriptor | Function cần validation/type/rendering phức tạp |
| Custom Dialect | Cần tùy biến dialect sâu hoặc tích hợp vendor behavior |
| `MetadataBuilderContributor` | Bootstrap extension trong một số codebase/version cũ; kiểm tra API hiện tại |
| `Dialect.registerFunction()` kiểu cũ | Hướng dẫn Hibernate legacy; không copy nguyên trạng sang 6/7 |

## 10. Hàm aggregate và custom aggregate

Hàm aggregate nhận nhiều rows và trả kết quả theo nhóm:

```hql
select c.status, count(c), sum(c.creditLimit)
from Customer c
group by c.status
```

Hibernate có nhiều aggregate chuẩn và các hàm mở rộng theo version/database. Một số DBMS cung cấp:

- `string_agg` / `listagg`
- `array_agg`
- `json_agg` / `json_arrayagg`
- `percentile_cont`
- `mode`
- `median`

HQL hiện đại có hỗ trợ một số ordered-set aggregate/window function với cú pháp tương ứng; tên và mức hỗ trợ tùy version/dialect.

### 10.1. Ordered-set aggregate

Một dạng khái niệm:

```hql
select percentile_cont(0.5)
       within group (order by p.price)
from Product p
```

Hàm percentile tính phân vị dựa trên thứ tự các giá trị. Cú pháp và kiểu trả về cần đối chiếu HQL reference và DB dialect. Nếu database không hỗ trợ, Hibernate không thể tự tạo ra semantics tương đương chỉ bằng việc nhận tên hàm.

### 10.2. `FILTER` trên aggregate

Một số HQL/database hỗ trợ lọc rows đầu vào của aggregate:

```hql
select
    count(o),
    count(o) filter (where o.status = 'PAID')
from PurchaseOrder o
```

Nếu version/dialect không hỗ trợ cú pháp FILTER, có thể dùng conditional aggregation:

```hql
select
    count(o),
    sum(case when o.status = 'PAID' then 1 else 0 end)
from PurchaseOrder o
```

Đây là dạng dễ thích nghi hơn với nhiều DBMS. Kiểm tra kiểu trả về của `SUM` và ép kiểu phù hợp nếu cần.

## 11. Window functions trong HQL hiện đại

Window function tính giá trị trên một cửa sổ rows mà không gộp toàn bộ nhóm thành một row như aggregate `GROUP BY`.

Ví dụ SQL:

```sql
SELECT
    order_no,
    customer_id,
    total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at DESC
    ) AS row_num
FROM purchase_orders;
```

Trong HQL hiện đại, có thể biểu đạt một số window functions theo cú pháp được Hibernate hỗ trợ:

```hql
select
    o.orderNumber,
    row_number() over (
        partition by o.customer.id
        order by o.createdAt desc
    )
from PurchaseOrder o
```

Các function thường gặp:

- `row_number()`
- `rank()`
- `dense_rank()`
- `lag(...)`
- `lead(...)`
- `first_value(...)`
- `last_value(...)`
- Aggregate functions với `over(...)`.

Window functions rất hữu ích cho ranking, top-N per group, running totals và so sánh row liền trước/sau. Nhưng hỗ trợ cú pháp phụ thuộc Hibernate version/dialect; nếu query cần portable trên provider khác, cân nhắc native SQL hoặc query projection riêng.

### 11.1. Window function khác GROUP BY

```text
GROUP BY:
  nhiều rows → một row cho mỗi group

WINDOW:
  mỗi input row vẫn tồn tại
  + thêm giá trị tính trên các rows cùng partition/window
```

Ví dụ ranking các order mới nhất theo customer vẫn giữ từng order, trong khi `GROUP BY customer` chỉ trả một row cho mỗi customer.

## 12. Hàm JSON và kiểu dữ liệu đặc thù

Một số DBMS hỗ trợ JSON functions, ví dụ PostgreSQL:

```sql
jsonb_extract_path_text(payload, 'customer', 'tier')
```

hoặc các database hỗ trợ SQL/JSON:

```sql
json_value(payload, '$.customer.tier')
```

Trong HQL có thể gọi function đã đăng ký hoặc `function()` theo tên database:

```hql
select function(
    'jsonb_extract_path_text',
    e.payload,
    'customer',
    'tier'
)
from EventLog e
```

Tùy kiểu mapping `payload`, Hibernate có thể bind/convert JSON như một kiểu vendor-specific hoặc type do ứng dụng cấu hình.

Không mặc định mọi DBMS hỗ trợ cùng function name/JSON path syntax. Nếu JSON là phần quan trọng của domain, cân nhắc Hibernate JSON mapping, database migration, index expression và function descriptor phù hợp.

### 12.1. JSON function và index

Một query:

```hql
where function('jsonb_extract_path_text', e.payload, 'tier') = :tier
```

có thể không sử dụng index bình thường trên cột `payload` nếu DB cần tính function cho từng row. Tùy database, cần expression index/generated column hoặc JSON path index phù hợp.

Hàm trong WHERE không tự nhiên “miễn phí”; xem `EXPLAIN`/query plan trên database thật.

## 13. Hàm có thể làm mất khả năng dùng index

Ví dụ:

```hql
select c
from Customer c
where lower(c.email) = lower(:email)
```

Nếu database chỉ có B-tree index thường trên `email`, biểu thức `lower(email)` có thể không dùng index đó theo cách mong muốn, tùy optimizer.

Các lựa chọn:

- Tạo function-based/expression index trên `lower(email)` nếu DBMS hỗ trợ.
- Chuẩn hóa email khi ghi và query theo giá trị normalized.
- Dùng collation/case-insensitive type phù hợp.
- Dùng cột normalized riêng nếu domain cần.
- Xem query plan thật trước khi tối ưu.

Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_customers_lower_email
ON customers (lower(email));
```

Đây là DDL riêng PostgreSQL, không portable.

Tương tự, `date(created_at) = :date` có thể cản trở index trên timestamp. Thường có thể dùng khoảng thời gian:

```hql
where o.createdAt >= :start
  and o.createdAt < :end
```

để database tìm theo range index phù hợp, với ranh giới thời gian đã được tính đúng timezone/business zone.

## 14. Null semantics khi gọi hàm

Hàm SQL thường có semantics null riêng. Nhiều hàm scalar trả null khi một đối số quan trọng là null:

```hql
select lower(c.displayName)
from Customer c
```

Nếu `displayName` null, kết quả có thể null.

Dùng:

```hql
select coalesce(lower(c.displayName), lower(c.email))
from Customer c
```

để có fallback rõ ràng.

### 14.1. Không nhầm NULL với chuỗi rỗng

- `NULL`: không có giá trị.
- `''`: chuỗi có độ dài 0.
- `'   '`: chuỗi chứa khoảng trắng.

`trim('   ')` có thể trả chuỗi rỗng, không tự biến nó thành null. Nếu cần coi chuỗi rỗng là không có dữ liệu, có thể kết hợp `nullif(trim(...), '')`:

```hql
select coalesce(
    nullif(trim(c.displayName), ''),
    c.email
)
from Customer c
```

### 14.2. Database có thể khác nhau về collation và Unicode

`lower()`/`upper()` chịu ảnh hưởng collation/locale và quy tắc Unicode của database. Không giả định kết quả byte-for-byte giống `String.toLowerCase()` Java trong mọi locale.

Nếu cần so sánh case-insensitive theo chuẩn nghiệp vụ, định nghĩa normalization/collation rõ ràng và test dữ liệu Unicode thực tế.

## 15. Kiểu trả về và ép kiểu trong query

Khi gọi hàm, cần biết kiểu mà Hibernate và database mong đợi.

Ví dụ:

```hql
select cast(o.total as BigDecimal)
from PurchaseOrder o
```

Hoặc function custom:

```hql
select app_tax(o.total, :rate)
from PurchaseOrder o
```

Nếu function registry khai báo return type sai, lỗi có thể xuất hiện ở:

- Query compilation/type checking.
- JDBC extraction/conversion.
- DTO constructor projection.
- Arithmetic/comparison.
- Runtime cast trong code Java.

Với projection typed:

```java
List<BigDecimal> totals = em.createQuery("""
    select cast(o.total as BigDecimal)
    from PurchaseOrder o
    """, BigDecimal.class)
  .getResultList();
```

Cần bảo đảm `BigDecimal.class` khớp kiểu thực tế Hibernate trả về.

### 15.1. Numeric precision và scale

`SUM(DECIMAL)` có thể trả precision/scale khác cột gốc theo DBMS. Đừng ép mọi kết quả tiền tệ sang `double`/`Double`; dùng `BigDecimal` và quy tắc rounding rõ ràng.

Function custom có thể trả `NUMERIC`, `DECIMAL`, `BIGINT`, `DOUBLE PRECISION` hoặc kiểu vendor. Descriptor cần phản ánh kết quả thực tế.

### 15.2. Temporal return types

Hàm truncate/extract/date arithmetic có thể trả `DATE`, `TIMESTAMP`, `INTEGER` hoặc kiểu khác tùy function. Đừng map `date_trunc()` thành `LocalDate` nếu database thực sự trả timestamp. Kiểm tra JDBC type, Hibernate type và DTO projection.

## 16. Parameter binding cho hàm

Ví dụ an toàn:

```java
List<Customer> customers = em.createQuery("""
    select c
    from Customer c
    where function('normalize_customer_code', c.code) = :code
    """, Customer.class)
  .setParameter("code", normalizedCode)
  .getResultList();
```

Không nối chuỗi:

```java
// Tránh:
String hql =
    "select c from Customer c where c.name = '" + userInput + "'";
```

Với function name, column, operator hoặc sort direction do người dùng chọn, parameter binding không thể thay identifier. Hãy dùng whitelist:

```java
String functionName = switch (requestedMode) {
    case "NORMALIZED" -> "app_normalize";
    case "RAW" -> "app_identity";
    default -> throw new IllegalArgumentException("Unsupported mode");
};
```

Sau đó dùng query template được kiểm soát hoặc các query riêng. Không cho người dùng truyền tùy ý SQL function name vào `function()`.

## 17. Function registration và kiểm thử trên nhiều dialect

Nếu ứng dụng hỗ trợ PostgreSQL và SQL Server, cùng một HQL function logic có thể cần renderer riêng.

Một chiến lược:

```text
HQL: app_truncate_day(order.createdAt)
           |
           +-- PostgreSQL descriptor
           |       → date_trunc('day', ?1)
           |
           +-- SQL Server descriptor
                   → CONVERT(date, ?1)
```

Điều cần test:

- Function có đăng ký khi bootstrap không?
- Query parser nhận tên function không?
- Số lượng/kiểu argument có đúng không?
- SQL renderer đúng dialect không?
- Database thực sự có function/extension cần thiết không?
- Return type JDBC/Hibernate có đúng không?
- Null và edge cases có semantics nhất quán không?
- Function trong `WHERE`/`ORDER BY` có query plan chấp nhận được không?

Không dùng H2 làm bằng chứng duy nhất cho PostgreSQL function. Testcontainers với đúng DBMS/major version giúp phát hiện khác biệt về function, JSON, date arithmetic, collation và return types.

## 18. Viết integration test cho function custom

Giả sử đã đăng ký:

```hql
app_normalize_code(c.code)
```

Test có thể thực hiện:

```java
@Test
void registeredFunctionCanBeUsedInHql() {
    try (EntityManager em = emf.createEntityManager()) {
        String normalized = em.createQuery("""
            select app_normalize_code(c.code)
            from Customer c
            where c.id = :id
            """, String.class)
            .setParameter("id", 10L)
            .getSingleResult();

        assertEquals("abc-123", normalized);
    }
}
```

Test fixture cần:

- Bootstrap `EntityManagerFactory` với `FunctionContributor` được discover.
- Đưa service descriptor vào test runtime classpath.
- Seed `Customer#10` với code tương ứng.
- Database có SQL function/SQL expression được descriptor render.
- Kiểm tra result type và null behavior.

Nếu function được render thành `lower(trim(?1))`, không cần tạo stored function trong database. Nếu descriptor render `normalize_customer_code(?1)`, DB phải có stored function đó.

### 18.1. Test contributor được discover

Một lỗi thường gặp là class contributor tồn tại nhưng service file không được đóng gói. Có thể kiểm tra bootstrap logs hoặc thực thi một HQL query gọi function.

Nếu query báo “unrecognized function” hoặc semantic function resolution error, kiểm tra:

1. Tên interface `org.hibernate.boot.model.FunctionContributor`.
2. Fully qualified class trong `META-INF/services`.
3. Artifact/JAR có file service resource.
4. Contributor có constructor truy cập được theo service loader.
5. Version Hibernate có extension point/API tương ứng.
6. Không có lỗi trong `contributeFunctions()`.

## 19. Function trong Criteria API

Jakarta Criteria API có `CriteriaBuilder.function()`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<String> cq = cb.createQuery(String.class);

Root<Customer> customer = cq.from(Customer.class);

Expression<String> normalized = cb.function(
    "normalize_customer_code",
    String.class,
    customer.get("code")
);

cq.select(normalized);

List<String> codes = em.createQuery(cq).getResultList();
```

Đây là cách gọi function theo tên từ Criteria API. Tuy nhiên, Criteria API không tự đảm bảo function có trên database hoặc Hibernate đã biết return type/SQL rendering đặc biệt. Đăng ký function Hibernate vẫn hữu ích khi cần metadata/renderer riêng.

`String.class` là kiểu kết quả mà Criteria query mong muốn; nó phải phù hợp với function thật.

## 20. Function trong projection và DTO

Có thể dùng function trong constructor projection:

```java
public record CustomerSummary(
    Long id,
    String normalizedCode
) {}
```

HQL:

```hql
select new com.example.dto.CustomerSummary(
    c.id,
    app_normalize_code(c.code)
)
from Customer c
```

Với record projection qua API typed/dynamic instantiation, cú pháp hỗ trợ phụ thuộc Hibernate version và cách constructor mapping. Đảm bảo function return type khớp tham số constructor.

Nếu function chỉ phục vụ formatting để hiển thị, đôi khi xử lý ở Java sau khi lấy dữ liệu đơn giản hơn. Nhưng nếu function dùng trong WHERE, ORDER BY, GROUP BY hoặc pagination, phải cân nhắc semantics database để tránh thay đổi kết quả.

## 21. Hàm trong WHERE, ORDER BY và GROUP BY

Function không chỉ dùng trong SELECT.

### 21.1. WHERE

```hql
select c
from Customer c
where lower(c.email) = :normalizedEmail
```

### 21.2. ORDER BY

```hql
select c
from Customer c
order by lower(c.displayName), c.id
```

### 21.3. GROUP BY

```hql
select lower(c.status), count(c)
from Customer c
group by lower(c.status)
```

### 21.4. HAVING

```hql
select lower(c.status), count(c)
from Customer c
group by lower(c.status)
having count(c) >= :minimum
```

Nếu function có thể trả null, hãy xét null grouping/order semantics. Nếu query cần ổn định pagination, thêm tie-breaker unique như `id` vào ORDER BY.

## 22. Hàm ngày giờ và timezone

Hàm temporal dễ tạo lỗi nghiệp vụ khi ứng dụng chạy ở nhiều timezone.

Ví dụ:

```hql
select current_timestamp
from PurchaseOrder o
```

Thời điểm có thể lấy theo database/session timezone semantics. Trong khi Java:

```java
Instant.now()
```

lấy clock của JVM và biểu diễn instant. Hai giá trị có thể khác do clock skew hoặc timezone conversion.

Khi lọc đơn theo ngày nghiệp vụ:

```hql
where o.createdAt >= :start
  and o.createdAt < :end
```

tính `start` và `end` trong Java theo timezone nghiệp vụ rồi bind parameter thường rõ ràng hơn:

```java
Instant start = businessDate.atStartOfDay(zone).toInstant();
Instant end = businessDate.plusDays(1).atStartOfDay(zone).toInstant();
```

Cách này tránh phụ thuộc vào `date(created_at)` và có thể dùng index range tốt hơn. Phải xác định mapping timestamp và database session timezone.

## 23. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| HQL báo không nhận diện function | Function chưa có trong HQL registry hoặc sai tên/cú pháp | Dùng built-in, `function()` hoặc đăng ký contributor |
| SQL chạy nhưng DB báo function không tồn tại | Database chưa cài stored function/extension | Triển khai migration/extension cần thiết |
| Typed query lỗi chuyển kiểu | Return type descriptor không đúng | Đăng ký return type đúng hoặc cast phù hợp |
| Query chạy trên PostgreSQL nhưng lỗi SQL Server | Function/cú pháp vendor-specific | Renderer theo dialect hoặc native query riêng |
| Contributor không được gọi | Thiếu `META-INF/services` hoặc classpath sai | Kiểm tra service loading và artifact |
| `function()` trả kiểu không rõ | Hibernate không có descriptor đủ metadata | Đăng ký descriptor hoặc cast |
| Function name injection | Ghép tên function từ input | Whitelist identifier/function names |
| `lower(column)` chậm | Index thường không phù hợp expression | Expression index/normalized column, xem EXPLAIN |
| Date filter bỏ qua index | Áp function lên cột timestamp trong WHERE | Dùng range predicate |
| `trim()` vẫn trả giá trị không như mong đợi | Null/empty/Unicode whitespace khác nhau | Xác định semantics và test dữ liệu |
| Aggregate trả precision khác | DBMS type derivation khác | Dùng BigDecimal, cast/rounding rõ |
| JSON function lỗi | DBMS/type/path syntax khác | Kiểm tra mapping, dialect và database function |
| HQL cũ dùng `registerFunction()` không biên dịch | API Hibernate major version đã đổi | Chuyển sang FunctionContributor/API tương ứng |
| Criteria function không hoạt động | Criteria gọi tên nhưng DB không có function/renderer | Đăng ký function hoặc dùng function native đúng DB |

## 24. Quy trình chọn cách gọi hàm

Trước khi thêm một function vào HQL, xác định:

**Bước 1 — Có hàm chuẩn JPQL không?** Nếu có, ưu tiên để query portable hơn.

**Bước 2 — HQL version có built-in phù hợp không?** Kiểm tra HQL reference/Javadoc đúng Hibernate version.

**Bước 3 — Hàm chỉ tồn tại trong database?** Có thể dùng `function('name', ...)` nếu cú pháp/return type đủ đơn giản.

**Bước 4 — Dùng lặp lại ở nhiều query?** Cân nhắc `FunctionContributor` để có tên logic, type metadata và SQL rendering tập trung.

**Bước 5 — Có khác biệt dialect?** Đăng ký renderer theo dialect hoặc dùng stored function cùng contract trên các DBMS.

**Bước 6 — Return type là gì?** Kiểm tra kiểu SQL, Hibernate type, Java projection và precision.

**Bước 7 — Null/collation/timezone có quan trọng không?** Định nghĩa rõ semantics và test edge cases.

**Bước 8 — Function ảnh hưởng index không?** Xem query plan và cân nhắc expression index/range predicates.

**Bước 9 — Có dùng user input trong cấu trúc query không?** Bind values; whitelist function/identifier names.

**Bước 10 — Kiểm thử trên DBMS thật.** Xác nhận bootstrap registration, SQL, kết quả và performance.

## 25. Bài tập tình huống

### Bài 1 — Chuẩn hóa email

Viết HQL tìm customer theo email không phân biệt chữ hoa/thường.

**Đáp án:**

```hql
select c
from Customer c
where lower(c.email) = lower(:email)
```

### Bài 2 — Lấy năm tạo order

Dùng hàm HQL hiện đại lấy năm từ `createdAt`.

**Đáp án:**

```hql
select extract(year from o.createdAt)
from PurchaseOrder o
```

Kiểm tra Hibernate version/dialect nếu dùng query trên DBMS khác nhau.

### Bài 3 — Giá trị fallback

Nếu `displayName` null hoặc chuỗi trắng, dùng email.

**Đáp án minh họa:**

```hql
select coalesce(
    nullif(trim(c.displayName), ''),
    c.email
)
from Customer c
```

### Bài 4 — Gọi function riêng database

Database có `normalize_customer_code(code)`. Gọi trong HQL như thế nào?

**Đáp án:**

```hql
select function('normalize_customer_code', c.code)
from Customer c
```

Function phải tồn tại trong database.

### Bài 5 — Function dùng nhiều nơi

Cùng một logic `lower(trim(code))` xuất hiện trong 50 query. Nên cân nhắc gì?

**Đáp án:** Đăng ký tên logic bằng `FunctionContributor`/`FunctionRegistry` nếu muốn tập trung type/rendering và tái sử dụng; hoặc dùng built-in expression trực tiếp nếu không cần extension.

### Bài 6 — Contributor không được phát hiện

HQL báo `app_normalize_code` chưa biết dù class contributor đã có. Kiểm tra gì?

**Đáp án:** Service descriptor `META-INF/services/org.hibernate.boot.model.FunctionContributor`, FQCN, classpath, JAR resources và Hibernate version.

### Bài 7 — Function return type

Custom function trả `NUMERIC`, nhưng query khai báo `String.class`. Nguy cơ?

**Đáp án:** Semantic/type mismatch hoặc lỗi JDBC extraction/DTO projection. Đăng ký kiểu numeric phù hợp hoặc cast rõ ràng.

### Bài 8 — Date filtering

Muốn lấy order trong một ngày nghiệp vụ và tận dụng index timestamp. Nên dùng `date(createdAt) = :date` hay range?

**Đáp án:** Thường dùng `createdAt >= :start AND createdAt < :end`, với biên được tính theo timezone nghiệp vụ.

### Bài 9 — Function name từ người dùng

Có nên truyền trực tiếp query parameter vào `function(:name, c.code)`?

**Đáp án:** Không. Function name là cấu trúc query, không phải value parameter. Dùng whitelist các function được cho phép.

### Bài 10 — HQL chạy nhưng SQL lỗi

`function('jsonb_extract_path_text', ...)` được parse, nhưng database báo function không tồn tại. Nguyên nhân?

**Đáp án:** HQL chỉ phát lời gọi; DBMS/schema cần có function/extension và kiểu đối số đúng.

## 26. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — HQL functions](https://docs.hibernate.org/stable/orm/querylanguage/html_single/#hql-functions): built-in functions, function invocation, aggregate và biểu thức HQL.
- [Hibernate ORM User Guide — HQL](https://docs.hibernate.org/stable/orm/querylanguage/html_single/): cú pháp HQL, kiểu dữ liệu, function, window/ordered-set expressions và query semantics.
- [Hibernate ORM Javadoc — `FunctionContributor`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/boot/model/FunctionContributor.html): extension point đăng ký function trong Hibernate.
- [Hibernate ORM Javadoc — `FunctionContributions`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/boot/model/FunctionContributions.html): truy cập function registry, type configuration và dialect-related contributions.
- [Hibernate ORM Javadoc — `SqmFunctionRegistry`](https://docs.hibernate.org/stable/orm/javadocs/org/hibernate/query/sqm/function/SqmFunctionRegistry.html): đăng ký function descriptor/pattern và lookup function.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): JPQL built-in functions, `FUNCTION` invocation, Criteria API và query expressions.
- [Jakarta Persistence 3.2 — `CriteriaBuilder.function`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/criteria/CriteriaBuilder.html): gọi database function trong Criteria API.
- [PostgreSQL Documentation — String Functions](https://www.postgresql.org/docs/current/functions-string.html): semantics các hàm chuỗi PostgreSQL.
- [PostgreSQL Documentation — Date/Time Functions](https://www.postgresql.org/docs/current/functions-datetime.html): temporal functions, timezone và date arithmetic.

`FunctionContributor`, `FunctionRegistry` và nhiều hàm HQL mở rộng là Hibernate-specific. Các hàm SQL vendor-specific phụ thuộc DBMS. Luôn đối chiếu tài liệu đúng Hibernate major version và database dialect của ứng dụng; các snippet đăng ký descriptor nâng cao có thể cần điều chỉnh theo API version.

## Kết luận

HQL cung cấp các hàm chuẩn JPQL cho chuỗi, số, ngày giờ, null và aggregate; Hibernate bổ sung nhiều biểu thức/hàm nâng cao; database lại có những hàm riêng như JSON, date truncation, aggregation hoặc stored function của ứng dụng. Khi chỉ cần gọi một hàm database đơn giản, `function('name', ...)` có thể đủ. Khi cần một tên logic tái sử dụng, return type rõ ràng hoặc SQL rendering theo dialect, hãy đăng ký hàm qua `FunctionContributor` và `FunctionRegistry` của Hibernate hiện đại.

Hãy chọn hàm dựa trên **semantics, kiểu trả về, null behavior, portability và query plan**. Bind giá trị bằng parameter, whitelist tên function/identifier, kiểm tra index khi áp hàm lên cột, và integration test trên DBMS thực tế. Một query parse thành công chưa bảo đảm function tồn tại trong database, kiểu dữ liệu đúng hoặc hiệu năng tốt; generated SQL và kết quả trên đúng Hibernate version/dialect mới là bằng chứng cần xác nhận.
