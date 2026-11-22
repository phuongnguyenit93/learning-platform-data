# Biểu thức CASE, COALESCE, NULLIF và hàm chuẩn trong JPQL

JPQL cho phép biểu diễn điều kiện, xử lý giá trị null và biến đổi dữ liệu ngay trong câu truy vấn. Ba biểu thức CASE, COALESCE và NULLIF rất hữu ích khi cần phân loại kết quả, chọn giá trị thay thế hoặc tránh một phép tính không hợp lệ. JPQL cũng có các hàm chuẩn để xử lý chuỗi, số, ngày giờ, collection và dữ liệu tổng hợp.

Spring Data JPA cho phép dùng các biểu thức này trong @Query, derived query hoặc projection. Bài học này giải thích cú pháp, ngữ nghĩa, ví dụ thực tế, các giới hạn về null và kiểu dữ liệu, cùng cách kiểm thử để câu truy vấn hoạt động ổn định trên database mục tiêu.

## 1. JPQL làm việc với entity và thuộc tính Java

JPQL là ngôn ngữ truy vấn hướng đối tượng của JPA. Câu truy vấn tham chiếu entity name và thuộc tính Java, không trực tiếp dùng tên bảng hoặc tên cột vật lý.

Ví dụ, giả sử có entity Employee với các thuộc tính:

| Thuộc tính | Kiểu Java | Ý nghĩa |
|---|---|---|
| id | Long | Khóa chính |
| name | String | Tên nhân viên |
| nickname | String, có thể null | Tên hiển thị ngắn |
| code | String, có thể null | Mã nhân viên |
| salary | BigDecimal | Lương |
| bonus | BigDecimal, có thể null | Thưởng |
| active | Boolean, có thể null | Trạng thái hoạt động |
| hiredAt | LocalDateTime | Thời điểm tuyển dụng |
| department | Department | Quan hệ tới phòng ban |
| tasks | Collection<Task> | Các công việc của nhân viên |

Một JPQL đơn giản:

~~~java
@Query("select e from Employee e where e.active = true")
List<Employee> findActiveEmployees();
~~~

Employee là entity name; e.active là thuộc tính Java. Hibernate chuyển JPQL thành SQL phù hợp với database dialect. Nếu entity dùng @Entity(name = "StaffMember"), JPQL phải dùng StaffMember thay vì tên lớp Employee.

Các biểu thức và hàm JPQL có thể xuất hiện trong SELECT, WHERE, ORDER BY hoặc các vị trí mà ngữ pháp JPQL cho phép. Chúng được đánh giá bởi database thông qua SQL do provider sinh ra.

## 2. Biểu thức CASE là gì?

CASE cho phép tạo một giá trị kết quả dựa trên các điều kiện. Nó tương tự if/else trong Java nhưng được đánh giá trên từng dòng dữ liệu ở database.

JPQL hỗ trợ hai dạng:

- Simple CASE: so sánh một biểu thức với các giá trị WHEN.
- Searched CASE: kiểm tra từng điều kiện Boolean trong WHEN.

Cả hai dạng có thể có ELSE. Nếu không có ELSE và không có nhánh WHEN nào khớp, kết quả là null.

### Searched CASE

Cú pháp:

~~~sql
CASE
    WHEN condition1 THEN result1
    WHEN condition2 THEN result2
    ELSE defaultResult
END
~~~

Ví dụ phân loại nhân viên theo lương:

~~~java
@Query("""
       select e.name,
              case
                  when e.salary >= :highSalary then 'HIGH'
                  when e.salary >= :mediumSalary then 'MEDIUM'
                  else 'STANDARD'
              end
       from Employee e
       """)
List<Object[]> classifySalary(
        @Param("highSalary") BigDecimal highSalary,
        @Param("mediumSalary") BigDecimal mediumSalary);
~~~

Mỗi phần tử Object[] gồm tên nhân viên và nhãn phân loại. Các điều kiện WHEN được xét theo thứ tự; nhánh đầu tiên có điều kiện TRUE sẽ quyết định kết quả. Điều kiện FALSE hoặc UNKNOWN không được chọn.

### Simple CASE

Cú pháp:

~~~sql
CASE expression
    WHEN value1 THEN result1
    WHEN value2 THEN result2
    ELSE defaultResult
END
~~~

Ví dụ ánh xạ trạng thái:

~~~java
@Query("""
       select e.name,
              case e.status
                  when 'NEW' then 'Mới'
                  when 'ACTIVE' then 'Đang làm việc'
                  when 'LEFT' then 'Đã nghỉ'
                  else 'Không xác định'
              end
       from Employee e
       """)
List<Object[]> describeStatus();
~~~

Simple CASE phù hợp khi so sánh một thuộc tính với nhiều giá trị cụ thể. Nếu cần điều kiện lớn hơn, nhỏ hơn, kết hợp AND/OR hoặc kiểm tra null, dùng searched CASE.

## 3. CASE trong SELECT, WHERE và ORDER BY

CASE có thể tạo một giá trị hiển thị trong SELECT:

~~~java
@Query("""
       select e.name,
              case when e.active = true
                   then 'Đang hoạt động'
                   else 'Không hoạt động hoặc chưa xác định'
              end
       from Employee e
       """)
List<Object[]> employeeLabels();
~~~

Có thể dùng CASE trong WHERE để biểu diễn một điều kiện lựa chọn:

~~~java
@Query("""
       select e
       from Employee e
       where case
                 when :includeInactive = true then 1
                 when e.active = true then 1
                 else 0
             end = 1
       """)
List<Employee> searchByActivity(
        @Param("includeInactive") boolean includeInactive);
~~~

Tuy nhiên, với điều kiện lọc tùy chọn đơn giản, biểu thức OR thường dễ đọc hơn:

~~~java
@Query("""
       select e
       from Employee e
       where (:includeInactive = true or e.active = true)
       """)
List<Employee> searchByActivity(
        @Param("includeInactive") boolean includeInactive);
~~~

CASE cũng hữu ích để sắp xếp theo thứ tự nghiệp vụ:

~~~java
@Query("""
       select e
       from Employee e
       order by
           case
               when e.active = true then 0
               when e.active = false then 1
               else 2
           end,
           e.name asc
       """)
List<Employee> findOrderedByActivity();
~~~

Nhân viên active đứng trước, inactive đứng sau, giá trị null đứng cuối; trong mỗi nhóm, kết quả được sắp xếp theo tên. Thứ tự null của ORDER BY mặc định có thể khác giữa database, vì vậy CASE giúp thể hiện quy tắc rõ ràng.

## 4. CASE và kiểu dữ liệu của kết quả

Các nhánh THEN và ELSE nên trả về những kiểu tương thích. Ví dụ, nếu một nhánh trả String thì các nhánh còn lại cũng nên trả String; nếu trả số, hãy dùng các kiểu số tương thích.

Ví dụ hợp lý:

~~~sql
CASE
    WHEN e.active = true THEN 'YES'
    ELSE 'NO'
END
~~~

Ví dụ cần tránh:

~~~sql
CASE
    WHEN e.active = true THEN 'YES'
    ELSE 0
END
~~~

Một nhánh trả chuỗi, nhánh kia trả số có thể gây lỗi chuyển kiểu hoặc phụ thuộc database. Nếu cần kết quả Boolean, hãy trả true/false nhất quán; nếu cần nhãn, trả chuỗi nhất quán.

Nếu không viết ELSE, CASE trả null khi không có điều kiện nào đúng. Hãy cân nhắc rõ việc giá trị null có ý nghĩa hay không.

## 5. CASE kết hợp với hàm tổng hợp

CASE thường được kết hợp với SUM hoặc COUNT để tính số lượng theo điều kiện.

Ví dụ đếm nhân viên active:

~~~java
@Query("""
       select
           sum(case when e.active = true then 1 else 0 end),
           sum(case when e.active = false then 1 else 0 end)
       from Employee e
       """)
Object[] countActivityGroups();
~~~

Cách này tạo hai số đếm trong một truy vấn. Có thể dùng projection DTO để tránh trả Object[].

Ví dụ phân loại đơn hàng theo tổng tiền:

~~~java
@Query("""
       select
           case
               when o.total >= :largeAmount then 'LARGE'
               when o.total >= :normalAmount then 'NORMAL'
               else 'SMALL'
           end,
           count(o)
       from Order o
       group by
           case
               when o.total >= :largeAmount then 'LARGE'
               when o.total >= :normalAmount then 'NORMAL'
               else 'SMALL'
           end
       """)
List<Object[]> countOrdersByBand(
        @Param("largeAmount") BigDecimal largeAmount,
        @Param("normalAmount") BigDecimal normalAmount);
~~~

Câu truy vấn nhóm đơn hàng theo nhãn được tính từ CASE. Khi dùng CASE trong GROUP BY, hãy xác nhận cú pháp với phiên bản JPQL/provider đang dùng; nếu portability là ưu tiên, có thể tính nhãn ở tầng Java hoặc dùng projection và truy vấn phù hợp với database.

## 6. COALESCE: lấy giá trị đầu tiên khác null

COALESCE nhận từ hai biểu thức trở lên và trả về biểu thức đầu tiên không null. Nếu tất cả đều null, kết quả là null.

Cú pháp:

~~~sql
COALESCE(expression1, expression2, ...)
~~~

Ví dụ chọn tên hiển thị:

~~~java
@Query("""
       select coalesce(e.nickname, e.name, 'Chưa đặt tên')
       from Employee e
       """)
List<String> findDisplayNames();
~~~

Quy tắc:

1. Nếu nickname có giá trị, dùng nickname.
2. Nếu nickname null, dùng name.
3. Nếu cả hai null, dùng chuỗi 'Chưa đặt tên'.

COALESCE hữu ích khi dữ liệu có nhiều nguồn thay thế hoặc cột nullable.

### COALESCE trong phép tính

Ví dụ cộng lương và thưởng, trong đó bonus null được hiểu là 0:

~~~java
@Query("""
       select e.name,
              e.salary + coalesce(e.bonus, 0)
       from Employee e
       """)
List<Object[]> findTotalCompensation();
~~~

Cần bảo đảm literal 0 tương thích với kiểu số của bonus và salary. Với BigDecimal, Hibernate/database thường xử lý phép toán số tương ứng; nếu gặp vấn đề về kiểu, dùng tham số BigDecimal zero hoặc biểu thức có kiểu rõ ràng.

COALESCE không thay đổi dữ liệu trong database. Nó chỉ tạo giá trị kết quả cho câu truy vấn. Nếu bonus thực sự chưa được nhập, giá trị cột vẫn null.

## 7. COALESCE và tham số tìm kiếm tùy chọn

Một cách phổ biến để viết bộ lọc tùy chọn là:

~~~java
@Query("""
       select e
       from Employee e
       where (:departmentName is null
              or e.department.name = :departmentName)
       """)
List<Employee> searchByDepartment(
        @Param("departmentName") String departmentName);
~~~

Nếu departmentName null, điều kiện đầu đúng và bộ lọc được bỏ qua. Nếu có giá trị, truy vấn lọc theo phòng ban.

Có thể gặp cách viết dùng COALESCE:

~~~sql
e.department.name = COALESCE(:departmentName, e.department.name)
~~~

Nhưng cách này có khác biệt về ngữ nghĩa khi e.department.name là null: nếu tham số null và thuộc tính cũng null, phép so sánh vẫn là UNKNOWN. Nó cũng có thể làm query khó tận dụng index tùy database. Vì vậy, điều kiện OR tường minh thường dễ hiểu và an toàn hơn cho optional filter.

Hãy quyết định riêng ý nghĩa của null: bỏ lọc, tìm giá trị null hay báo lỗi. Không dùng COALESCE để che đi một quy tắc nghiệp vụ chưa được xác định.

## 8. NULLIF: biến hai giá trị bằng nhau thành null

NULLIF nhận hai biểu thức. Nếu chúng bằng nhau, kết quả là null; nếu không bằng nhau, kết quả là biểu thức thứ nhất.

Cú pháp:

~~~sql
NULLIF(expression1, expression2)
~~~

Ví dụ:

~~~sql
NULLIF(e.discountCode, '')
~~~

Nếu discountCode là chuỗi rỗng, kết quả là null; nếu không, kết quả giữ nguyên mã.

Ví dụ trong JPQL:

~~~java
@Query("""
       select nullif(trim(e.code), '')
       from Employee e
       """)
List<String> findNormalizedCodes();
~~~

TRIM loại khoảng trắng ở hai đầu trước. NULLIF sau đó chuyển chuỗi rỗng thành null. Đây là phép biến đổi ở kết quả truy vấn, không cập nhật cột code.

### NULLIF để tránh chia cho 0

Giả sử entity Metric có numerator và denominator:

~~~java
@Query("""
       select m.numerator / nullif(m.denominator, 0)
       from Metric m
       """)
List<BigDecimal> findSafeRatios();
~~~

Khi denominator bằng 0, NULLIF trả null. Phép chia cho null tạo kết quả null thay vì chia cho 0. Nếu denominator khác 0, truy vấn thực hiện phép chia bình thường.

Cần kiểm tra kiểu số và precision của phép chia trên database mục tiêu. Nếu nghiệp vụ yêu cầu kết quả 0 thay vì null, hãy dùng COALESCE bên ngoài:

~~~sql
COALESCE(m.numerator / NULLIF(m.denominator, 0), 0)
~~~

Khi đó kết quả null do mẫu số bằng 0 sẽ được thay bằng 0. Chỉ dùng khi 0 thực sự là quy ước nghiệp vụ; đôi khi null biểu thị "không thể tính" chính xác hơn.

## 9. Kết hợp CASE, COALESCE và NULLIF

Ba biểu thức có thể kết hợp để tạo quy tắc rõ ràng.

Ví dụ tạo nhãn cho mã nhân viên:

~~~java
@Query("""
       select
           case
               when e.active = true then
                   coalesce(nullif(trim(e.code), ''), 'NO-CODE')
               when e.active = false then 'INACTIVE'
               else 'UNKNOWN'
           end
       from Employee e
       """)
List<String> findEmployeeLabels();
~~~

Thứ tự xử lý:

1. CASE xác định nhánh theo trạng thái.
2. Nếu active, TRIM bỏ khoảng trắng đầu/cuối của code.
3. NULLIF chuyển chuỗi rỗng thành null.
4. COALESCE dùng 'NO-CODE' nếu code không có giá trị.
5. Nếu inactive hoặc active null, CASE trả nhãn tương ứng.

Việc lồng nhiều biểu thức có thể làm query khó đọc. Khi quy tắc phức tạp, cân nhắc DTO projection, service logic hoặc database view có kiểm soát.

## 10. Các hàm chuỗi chuẩn trong JPQL

JPQL cung cấp các hàm chuỗi phổ biến:

| Hàm | Ý nghĩa | Ví dụ |
|---|---|---|
| CONCAT(s1, s2) | Nối hai chuỗi | concat(e.firstName, e.lastName) |
| SUBSTRING(s, start, length) | Lấy chuỗi con | substring(e.code, 1, 3) |
| TRIM(s) | Bỏ khoảng trắng đầu/cuối | trim(e.name) |
| LOWER(s) | Chuyển thành chữ thường | lower(e.name) |
| UPPER(s) | Chuyển thành chữ hoa | upper(e.name) |
| LENGTH(s) | Độ dài chuỗi | length(e.name) |
| LOCATE(search, s[, start]) | Vị trí chuỗi con | locate('an', e.name) |

Ví dụ tìm theo tên không phân biệt hoa thường:

~~~java
@Query("""
       select e
       from Employee e
       where lower(e.name) = lower(:name)
       """)
List<Employee> findByNameIgnoreCase(@Param("name") String name);
~~~

Tìm mã có tiền tố:

~~~java
@Query("""
       select e
       from Employee e
       where substring(e.code, 1, 3) = :prefix
       """)
List<Employee> findByCodePrefix(@Param("prefix") String prefix);
~~~

LOCATE trả về vị trí bắt đầu từ 1; trả 0 nếu không tìm thấy. Ví dụ:

~~~java
@Query("select locate(:part, e.name) from Employee e")
List<Integer> locatePart(@Param("part") String part);
~~~

Một số lưu ý:

- SUBSTRING dùng vị trí bắt đầu từ 1 theo JPQL.
- LENGTH trả độ dài theo cách database xử lý chuỗi; quy tắc đếm ký tự Unicode có thể khác giữa hệ quản trị.
- LOWER/UPPER phụ thuộc collation và quy tắc ngôn ngữ của database.
- CONCAT trong JPQL chuẩn nhận hai biểu thức chuỗi; có thể lồng CONCAT nếu cần nối nhiều phần.
- TRIM có cú pháp mở rộng để chọn LEADING, TRAILING, BOTH và ký tự cần bỏ; kiểm tra provider/database khi dùng dạng nâng cao.

## 11. Các hàm số chuẩn trong JPQL

| Hàm | Ý nghĩa | Ví dụ |
|---|---|---|
| ABS(x) | Giá trị tuyệt đối | abs(e.balance) |
| SQRT(x) | Căn bậc hai | sqrt(e.score) |
| MOD(x, y) | Phần dư phép chia | mod(e.id, 2) |

Ví dụ lấy nhân viên có ID chẵn:

~~~java
@Query("select e from Employee e where mod(e.id, 2) = 0")
List<Employee> findEvenIds();
~~~

Ví dụ lọc theo giá trị tuyệt đối:

~~~java
@Query("select e from Employee e where abs(e.balance) > :limit")
List<Employee> findOutsideBalanceLimit(
        @Param("limit") BigDecimal limit);
~~~

Kiểu kết quả và giới hạn của các hàm số phụ thuộc kiểu thuộc tính và database. SQRT thường tạo kết quả số dấu phẩy động; đừng giả định nó luôn trả BigDecimal. Với phép chia, làm tròn và precision, hãy kiểm thử trên database thật.

## 12. Các hàm ngày giờ chuẩn

JPQL có các hàm thời gian hiện tại:

| Hàm | Ý nghĩa |
|---|---|
| CURRENT_DATE | Ngày hiện tại của database/session |
| CURRENT_TIME | Giờ hiện tại của database/session |
| CURRENT_TIMESTAMP | Ngày giờ hiện tại của database/session |

Ví dụ tìm nhân viên được tuyển trước thời điểm hiện tại:

~~~java
@Query("""
       select e
       from Employee e
       where e.hiredAt <= current_timestamp
       """)
List<Employee> findAlreadyHired();
~~~

Ví dụ so sánh ngày:

~~~java
@Query("""
       select e
       from Employee e
       where e.contractEndDate < current_date
       """)
List<Employee> findExpiredContracts();
~~~

Các hàm này được đánh giá ở database, vì vậy giá trị chịu ảnh hưởng timezone/session và đồng hồ của database. Nếu nghiệp vụ cần thời điểm UTC do ứng dụng kiểm soát, truyền Instant hoặc tham số thời gian rõ ràng thay vì dựa vào CURRENT_TIMESTAMP.

## 13. Các hàm collection và map

JPQL có một số biểu thức chuẩn để làm việc với collection-valued association.

**SIZE(collection)** trả số phần tử trong collection:

~~~java
@Query("""
       select e
       from Employee e
       where size(e.tasks) >= :minimumTasks
       """)
List<Employee> findBusyEmployees(
        @Param("minimumTasks") int minimumTasks);
~~~

SIZE chỉ dùng với thuộc tính collection. Tùy provider, truy vấn có thể được chuyển thành subquery hoặc biểu thức SQL tương đương. Với collection lớn và truy vấn thường xuyên, hãy kiểm tra SQL và index.

**INDEX(alias)** lấy vị trí của phần tử trong association được ánh xạ bằng @OrderColumn hoặc list có index phù hợp. Ví dụ dùng trong truy vấn với một list association:

~~~java
@Query("""
       select t
       from Employee e join e.orderedTasks t
       where index(t) = :position
       """)
List<Task> findTaskAtPosition(@Param("position") int position);
~~~

Cách dùng INDEX phụ thuộc mapping list có thứ tự và cú pháp alias của association. Nó không phải chỉ số của mọi loại collection.

Với map-valued association, JPQL có:

- KEY(mapAlias): khóa của entry.
- VALUE(mapAlias): giá trị của entry.
- ENTRY(mapAlias): entry map; thường dùng trong SELECT.

Ví dụ:

~~~java
@Query("""
       select key(m), value(m)
       from Employee e join e.attributes m
       where key(m) = :attributeName
       """)
List<Object[]> findEmployeeAttribute(
        @Param("attributeName") String attributeName);
~~~

Các hàm collection/map chỉ áp dụng đúng loại association đã được mapping; không dùng chúng như hàm xử lý chuỗi hoặc bảng tùy ý.

## 14. Hàm tổng hợp và kết hợp với CASE/COALESCE

Các hàm tổng hợp chuẩn gồm:

| Hàm | Ý nghĩa | Kiểu kết quả thường gặp |
|---|---|---|
| COUNT(x) | Đếm giá trị không null hoặc entity | Long |
| COUNT(DISTINCT x) | Đếm giá trị khác nhau | Long |
| SUM(x) | Tổng | Phụ thuộc kiểu số |
| AVG(x) | Trung bình | Double |
| MIN(x) | Giá trị nhỏ nhất | Cùng kiểu thuộc tính |
| MAX(x) | Giá trị lớn nhất | Cùng kiểu thuộc tính |

Quy tắc đáng nhớ:

- COUNT bỏ qua giá trị null; COUNT(entity) đếm entity phù hợp.
- SUM, AVG, MIN và MAX bỏ qua giá trị null.
- Nếu không có giá trị để tổng hợp, SUM/AVG/MIN/MAX thường trả null; COUNT trả 0.
- SUM trả kiểu phụ thuộc kiểu số: Long cho kiểu số nguyên thông thường, Double cho số dấu phẩy động, BigInteger cho BigInteger và BigDecimal cho BigDecimal.
- AVG trả Double theo quy tắc JPQL chuẩn.

Ví dụ tính tổng lương:

~~~java
@Query("select sum(e.salary) from Employee e")
BigDecimal totalSalary();
~~~

Ví dụ tính trung bình:

~~~java
@Query("select avg(e.salary) from Employee e")
Double averageSalary();
~~~

Ví dụ thay null khi không có bản ghi:

~~~java
@Query("select coalesce(sum(e.bonus), 0) from Employee e")
BigDecimal totalBonusOrZero();
~~~

Cần bảo đảm giá trị thay thế tương thích kiểu số của biểu thức SUM. Với hệ thống yêu cầu kiểu chặt chẽ, truyền một tham số BigDecimal zero hoặc xử lý null ở service.

Kết hợp CASE để tính số nhân viên active:

~~~java
@Query("""
       select sum(case when e.active = true then 1 else 0 end)
       from Employee e
       """)
Long countActiveEmployees();
~~~

## 15. Dùng DTO projection thay cho Object[]

Khi query trả nhiều biểu thức, Object[] khiến code phải ép kiểu theo vị trí. DTO projection rõ ràng hơn.

DTO:

~~~java
package com.example.employee;

public record EmployeeStatusView(
        Long id,
        String name,
        String statusLabel,
        String displayName
) {
}
~~~

Repository:

~~~java
@Query("""
       select new com.example.employee.EmployeeStatusView(
           e.id,
           e.name,
           case
               when e.active = true then 'ACTIVE'
               when e.active = false then 'INACTIVE'
               else 'UNKNOWN'
           end,
           coalesce(e.nickname, e.name, 'Unknown')
       )
       from Employee e
       order by e.name
       """)
List<EmployeeStatusView> findEmployeeStatusViews();
~~~

JPQL constructor expression cần tên lớp đầy đủ và thứ tự kiểu tham số phải khớp constructor. Java record có canonical constructor phù hợp với cách gọi này. Nếu dự án dùng class DTO thường, cần có constructor public tương ứng.

DTO projection giảm việc tải toàn bộ entity khi chỉ cần một số cột, đồng thời giúp API/query có kiểu trả về rõ ràng.

## 16. Dùng các biểu thức trong Spring Data repository

Ví dụ repository kết hợp CASE, COALESCE, NULLIF và hàm chuẩn:

~~~java
package com.example.employee;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e.name,
                  case
                      when e.salary >= :threshold then 'HIGH'
                      else 'STANDARD'
                  end
           from Employee e
           """)
    List<Object[]> classify(
            @Param("threshold") BigDecimal threshold);

    @Query("""
           select coalesce(e.nickname, e.name, 'Unknown')
           from Employee e
           """)
    List<String> findDisplayNames();

    @Query("""
           select nullif(trim(e.code), '')
           from Employee e
           """)
    List<String> findNormalizedCodes();

    @Query("""
           select e
           from Employee e
           where lower(e.name) like lower(concat('%', :keyword, '%'))
           """)
    List<Employee> searchName(
            @Param("keyword") String keyword);

    @Query("""
           select e
           from Employee e
           order by
               case when e.active = true then 0 else 1 end,
               upper(e.name)
           """)
    List<Employee> findSortedByActivityAndName();

    @Query("select count(e) from Employee e where mod(e.id, 2) = 0")
    Long countEvenIds();
}
~~~

Đây là các method minh họa cho một entity Employee có các thuộc tính tương ứng. Khi đưa vào dự án, bảo đảm tên entity, thuộc tính, kiểu trả về và package DTO khớp mô hình thực tế. Không cần khai báo @Query nếu derived query đã diễn đạt rõ điều kiện đơn giản.

## 17. Null semantics cần nhớ

SQL và JPQL sử dụng logic ba giá trị: TRUE, FALSE và UNKNOWN. So sánh với null bằng = hoặc <> tạo UNKNOWN. Dùng IS NULL hoặc IS NOT NULL khi cần kiểm tra null.

| Biểu thức | Ý nghĩa |
|---|---|
| e.nickname = null | Không phải cách kiểm tra null đúng |
| e.nickname is null | Thuộc tính không có giá trị |
| e.nickname is not null | Thuộc tính có giá trị |
| coalesce(e.nickname, e.name) | Chọn giá trị đầu tiên khác null |
| nullif(e.code, '') | Trả null nếu code là chuỗi rỗng |
| case when e.active = true then ... else ... end | Điều kiện UNKNOWN không khớp nhánh WHEN |

COALESCE và NULLIF không làm thay đổi dữ liệu lưu trữ. Chúng chỉ tạo kết quả trong truy vấn. Nếu muốn chuẩn hóa dữ liệu lâu dài, cần cập nhật dữ liệu bằng nghiệp vụ hoặc migration có kiểm soát.

## 18. Hàm chuẩn và FUNCTION() riêng của database

JPQL có các hàm chuẩn để tăng tính di động giữa các database. Tuy nhiên, mỗi database còn có nhiều hàm riêng. JPA cung cấp FUNCTION() để gọi hàm database/provider cụ thể:

~~~java
@Query("""
       select function('some_db_function', e.name)
       from Employee e
       """)
List<String> callDatabaseFunction();
~~~

some_db_function chỉ là tên minh họa; phải thay bằng hàm thực sự tồn tại trên database đích.

FUNCTION() là cách mở rộng, không bảo đảm truy vấn portable. Các điểm cần lưu ý:

- Cú pháp và kiểu tham số phụ thuộc database.
- Có thể cần đăng ký function trong Hibernate dialect.
- Test với H2 có thể không chạy nếu H2 không có hàm tương ứng.
- Đổi database có thể cần viết lại query.
- Không đưa tên hàm hoặc đoạn SQL tùy ý do người dùng gửi vào truy vấn.

Nếu chỉ cần chức năng chuẩn như LOWER, CONCAT, ABS hoặc CURRENT_DATE, ưu tiên hàm JPQL chuẩn.

## 19. Hiệu năng và tính di động

Biểu thức trong SELECT thường chỉ ảnh hưởng cách tạo kết quả, nhưng biểu thức trong WHERE hoặc ORDER BY có thể ảnh hưởng khả năng dùng index.

Ví dụ:

~~~sql
WHERE LOWER(name) = LOWER(?)
~~~

Nếu database không có functional index tương ứng, index thông thường trên name có thể không được tận dụng. Tương tự, lọc bằng CASE hoặc hàm trên cột có thể khiến optimizer khó sử dụng index.

Một số nguyên tắc:

- Dùng điều kiện đơn giản trên cột khi có thể.
- Tạo functional index nếu database hỗ trợ và workload chứng minh cần thiết.
- Không lạm dụng CASE trong WHERE nếu có thể diễn đạt bằng AND/OR rõ ràng.
- Kiểm tra execution plan với dữ liệu gần production.
- Dùng projection để chỉ lấy trường cần thiết.
- Phân trang khi danh sách lớn.
- Kiểm tra collation và timezone của database cho các hàm chuỗi/ngày giờ.
- Dùng FUNCTION() chỉ khi chấp nhận phụ thuộc database.
- Kiểm tra kiểu trả về của CASE/COALESCE/NULLIF trên provider đang dùng.

JPQL chuẩn cải thiện khả năng di chuyển, nhưng không có nghĩa mọi database tạo SQL hoặc hiệu năng giống nhau.

## 20. Kiểm thử các biểu thức JPQL

Dùng @DataJpaTest để kiểm tra query trên persistence layer. Test cần tạo dữ liệu đại diện cho cả trường hợp null và khác null, điều kiện đúng/sai, chuỗi rỗng và giá trị biên.

Ví dụ kiểm tra COALESCE và NULLIF:

~~~java
package com.example.employee;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void coalesceUsesFirstNonNullValue() {
        repository.save(EmployeeFixture.employee(
                "An", null, "E001", new BigDecimal("1000.00"), true));
        repository.save(EmployeeFixture.employee(
                "Binh", "Bee", "E002", new BigDecimal("1200.00"), true));

        var names = repository.findDisplayNames();

        assertThat(names).contains("An", "Bee");
    }

    @Test
    void nullifTurnsBlankCodeIntoNull() {
        repository.save(EmployeeFixture.employee(
                "An", null, "   ", new BigDecimal("1000.00"), true));

        var codes = repository.findNormalizedCodes();

        assertThat(codes).containsNull();
    }
}
~~~

EmployeeFixture ở ví dụ là factory test của dự án, tạo entity Employee với các thuộc tính đã nêu. Nếu không có fixture, tạo entity trực tiếp bằng constructor phù hợp. Test tập trung vào kết quả của truy vấn chứ không phụ thuộc implementation nội bộ của Hibernate.

Có thể bổ sung test cho:

- CASE khi điều kiện TRUE, FALSE và UNKNOWN.
- CASE không có ELSE.
- NULLIF khi hai giá trị bằng nhau và khác nhau.
- COALESCE khi tất cả đối số null.
- LOCATE khi tìm thấy và không tìm thấy.
- SUBSTRING với chỉ số bắt đầu từ 1.
- MOD với số âm hoặc mẫu số hợp lệ.
- CURRENT_DATE/CURRENT_TIMESTAMP theo timezone database.
- SUM/AVG trên tập rỗng hoặc giá trị null.
- SIZE với collection rỗng và collection có phần tử.

H2 phù hợp cho test nhanh nhưng có khác biệt về function, collation, kiểu số và ngày giờ so với PostgreSQL/MySQL. Nếu query dựa vào hành vi database cụ thể, chạy integration test trên đúng database triển khai.

## 21. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| CASE trả kiểu không tương thích | Các nhánh THEN/ELSE khác kiểu | Dùng kiểu kết quả tương thích |
| CASE trả null ngoài dự kiến | Thiếu ELSE và không nhánh WHEN nào khớp | Thêm ELSE nếu cần giá trị mặc định |
| COALESCE không thay được null | Một biểu thức trước đó không null nhưng chứa chuỗi rỗng | Kết hợp TRIM/NULLIF nếu cần |
| NULLIF không xử lý chuỗi khoảng trắng | Chỉ so sánh chuỗi nguyên bản | Dùng NULLIF(TRIM(value), '') |
| Chia cho 0 | Mẫu số không được bảo vệ | Dùng NULLIF hoặc CASE |
| JPQL không nhận tên bảng | Dùng tên bảng/cột SQL thay vì entity/thuộc tính | Dùng entity name và thuộc tính Java |
| Không tìm thấy hàm | Dùng hàm riêng của DB như thể là chuẩn JPQL | Dùng FUNCTION() có chủ đích hoặc thay bằng hàm chuẩn |
| Sai kiểu trả về | Hàm tổng hợp hoặc CASE trả kiểu khác dự kiến | Kiểm tra quy tắc kiểu JPQL và kiểu DTO |
| Query chậm sau khi dùng LOWER/CASE | Hàm trên cột làm index thường khó sử dụng | Xem execution plan và cân nhắc functional index |
| H2 test pass nhưng production fail | Hàm hoặc hành vi khác giữa database | Test trên hệ quản trị thực tế |

## 22. Checklist tự đánh giá

- [ ] Giải thích được JPQL truy vấn entity và thuộc tính Java.
- [ ] Phân biệt simple CASE và searched CASE.
- [ ] Dùng CASE trong SELECT và ORDER BY để phân loại/sắp xếp.
- [ ] Biết CASE trả null nếu không có ELSE và không nhánh nào khớp.
- [ ] Bảo đảm các nhánh CASE có kiểu kết quả tương thích.
- [ ] Dùng COALESCE để lấy giá trị đầu tiên khác null.
- [ ] Dùng NULLIF để biến hai giá trị bằng nhau thành null.
- [ ] Dùng NULLIF để bảo vệ phép chia có mẫu số bằng 0.
- [ ] Phân biệt COALESCE optional filter với điều kiện OR tường minh.
- [ ] Dùng hàm chuỗi CONCAT, SUBSTRING, TRIM, LOWER, UPPER, LENGTH, LOCATE.
- [ ] Dùng hàm số ABS, SQRT và MOD.
- [ ] Dùng CURRENT_DATE, CURRENT_TIME và CURRENT_TIMESTAMP đúng ngữ cảnh.
- [ ] Dùng SIZE, INDEX và các hàm map KEY/VALUE/ENTRY đúng loại collection.
- [ ] Hiểu kiểu trả về của COUNT, SUM, AVG, MIN và MAX.
- [ ] Dùng DTO projection cho kết quả nhiều biểu thức.
- [ ] Phân biệt hàm JPQL chuẩn với FUNCTION() riêng của database.
- [ ] Kiểm thử null, chuỗi rỗng, giá trị biên và database mục tiêu.

## 23. Kết luận

CASE giúp tạo kết quả có điều kiện ngay trong query; COALESCE chọn giá trị đầu tiên khác null; NULLIF biến hai giá trị bằng nhau thành null, thường hữu ích khi chuẩn hóa dữ liệu hoặc tránh chia cho 0. Các hàm chuỗi, số, ngày giờ, collection và tổng hợp mở rộng khả năng xử lý dữ liệu của JPQL.

Khi dùng các biểu thức này trong Spring Data JPA, hãy hiểu rõ kiểu kết quả, logic ba giá trị của SQL, cách database xử lý null và tác động của hàm lên index. Ưu tiên hàm chuẩn JPQL để giữ tính di động, dùng DTO khi trả nhiều biểu thức và kiểm thử trên đúng database khi query phụ thuộc dialect hoặc collation.
