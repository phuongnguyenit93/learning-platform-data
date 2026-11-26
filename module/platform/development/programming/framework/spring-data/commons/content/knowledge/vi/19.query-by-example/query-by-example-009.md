# Giới hạn nhóm điều kiện, quan hệ, collection và thuộc tính lồng nhau

Query by Example (QBE) thích hợp khi yêu cầu tìm kiếm có thể mô tả bằng một đối tượng mẫu và các quy tắc so khớp thuộc tính. Khi yêu cầu xuất hiện nhóm AND/OR lồng nhau, điều kiện trên phần tử collection hoặc phép duyệt quan hệ phức tạp, cần kiểm tra xem QBE còn diễn đạt đúng ý định hay không.

Trong Spring Data Commons, `Example`, `ExampleMatcher` và `QueryByExampleExecutor` cung cấp abstraction dùng chung. Store module mới là thành phần chuyển các abstraction đó thành truy vấn thực tế. Vì vậy, cần phân biệt hai câu hỏi: **matcher có biểu diễn được điều kiện không**, và **store đang dùng có hỗ trợ cấu trúc dữ liệu, mapping cùng phép truy vấn đó không**.

Bài học này xây dựng ranh giới sử dụng QBE, giải thích những hiểu nhầm thường gặp với quan hệ và thuộc tính lồng nhau, đồng thời minh họa cách chuyển sang cơ chế phù hợp khi yêu cầu vượt quá khả năng của Example.

## 1. Từ probe đến các điều kiện thuộc tính

Một Example bao gồm probe và matcher:

```java
Example<Employee> example = Example.of(probe, matcher);
```

Probe cung cấp giá trị. Matcher quy định những đường dẫn cần bỏ qua, cách xử lý `null`, quy tắc so khớp chuỗi và cách kết hợp các điều kiện tham gia.

Giả sử sau khi áp dụng matcher và mapping, ba điều kiện thuộc tính còn lại là:

```text
P1: status bằng "ACTIVE"
P2: fullName chứa "An"
P3: address.city bằng "Huế"
```

Hai cách kết hợp cơ bản là:

| Matcher | Cách hiểu |
| --- | --- |
| `matchingAll()` | `P1 AND P2 AND P3` |
| `matchingAny()` | `P1 OR P2 OR P3` |

Một Example không cung cấp API để lắp ghép cây biểu thức tùy ý như:

```text
P1 AND (P2 OR P3)
```

Đây là giới hạn về khả năng biểu diễn điều kiện, tồn tại ngay cả khi cơ sở dữ liệu bên dưới hoàn toàn hỗ trợ truy vấn phức tạp đó. Không thể khắc phục bằng cách đổi mapping hoặc thêm getter vào probe.

QBE cũng không phải một ngôn ngữ truy vấn tổng quát. Không nên giả định một giá trị mẫu có thể tự diễn đạt các yêu cầu như khoảng số, phép phủ định, phép tổng hợp, truy vấn con hoặc điều kiện tồn tại phần tử.

## 2. Mô hình dùng để thảo luận

Các ví dụ sử dụng mô hình nhân viên sau:

| Kiểu | Thuộc tính đáng chú ý |
| --- | --- |
| `Employee` | `Long id`, `String fullName`, `String status`, `Boolean active`, `Integer level` |
| `Employee` | `Department department`, `Address address` |
| `Employee` | `Set<String> skills`, `List<WorkItem> workItems` |
| `Department` | `Long id`, `String code`, `String name` |
| `Address` | `String city`, `String country` |
| `WorkItem` | `Long id`, `String state`, `Integer priority` |

Các đoạn mã giả định mỗi lớp có constructor không tham số cùng getter/setter thích hợp. `Boolean` và `Integer` được dùng để biểu diễn bộ lọc không được cung cấp bằng `null`.

Đây là mô hình khái niệm, không phải một mapping có thể dùng nguyên trạng cho mọi kho dữ liệu. Trong phần minh họa JPA, giả định `Employee` và `Department` là entity, `address` là đối tượng nhúng và `workItems` là quan hệ collection được mapping hợp lệ. Trong kho tài liệu, một số đối tượng có thể được nhúng vào tài liệu thay vì tồn tại dưới dạng quan hệ giữa các bảng.

Repository QBE ở mức Commons có thể được công bố như sau, nếu store hỗ trợ:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface EmployeeRepository
        extends CrudRepository<Employee, Long>,
                QueryByExampleExecutor<Employee> {
}
```

Các đoạn tạo Example sử dụng:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
```

Việc repository trả về nhiều bản ghi không liên quan đến khả năng lọc một thuộc tính collection bên trong mỗi bản ghi. Đây là hai vấn đề khác nhau.

## 3. Nhóm điều kiện: AND hoặc OR phẳng không thay cho cây biểu thức

Yêu cầu nghiệp vụ:

> Chỉ tìm nhân viên ACTIVE và đồng thời thỏa ít nhất một trong hai tiêu chí: tên chứa An hoặc thành phố là Huế.

Biểu thức đúng là:

```text
status = "ACTIVE"
AND (fullName chứa "An" OR address.city = "Huế")
```

Nếu đưa cả ba giá trị vào probe và dùng `matchingAll()`, truy vấn trở thành:

```text
status = "ACTIVE"
AND fullName chứa "An"
AND address.city = "Huế"
```

Kết quả bị thu hẹp: nhân viên ACTIVE tên An ở Hà Nội đáng lẽ được chọn nhưng lại bị loại.

Nếu đổi sang `matchingAny()`, truy vấn trở thành:

```text
status = "ACTIVE"
OR fullName chứa "An"
OR address.city = "Huế"
```

Kết quả bị mở rộng: nhân viên INACTIVE ở Huế vẫn có thể được chọn.

| Nhân viên | Trạng thái | Tên chứa An? | Ở Huế? | Điều kiện nghiệp vụ | matchingAll | matchingAny |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | ACTIVE | Có | Không | Chọn | Loại | Chọn |
| E2 | ACTIVE | Không | Có | Chọn | Loại | Chọn |
| E3 | INACTIVE | Không | Có | Loại | Loại | Chọn |
| E4 | ACTIVE | Có | Có | Chọn | Chọn | Chọn |

Cấu hình matcher theo từng thuộc tính, ví dụ dùng `contains()` cho tên, chỉ thay đổi cách so khớp giá trị. Nó không tạo một nhóm OR bên trong nhóm AND.

Tương tự, một field chuỗi chứa văn bản `"An OR Bình"` chỉ là dữ liệu chuỗi để so khớp theo matcher. Nó không trở thành hai nhánh logic. QBE không diễn giải nội dung probe như một biểu thức truy vấn.

## 4. Thuộc tính lồng nhau khác với nhóm điều kiện lồng nhau

Hai cách dùng từ “lồng nhau” cần được tách rõ:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Đường dẫn thuộc tính lồng nhau | `address.city` | Đi tới giá trị bên trong cấu trúc đối tượng |
| Nhóm điều kiện lồng nhau | `A AND (B OR C)` | Kết hợp các predicate theo cây logic |

Việc store hỗ trợ đường dẫn `address.city` không có nghĩa matcher hỗ trợ nhóm `(B OR C)`.

### Ví dụ lọc thuộc tính lồng nhau

Giả sử store hỗ trợ mapping và phép duyệt `address.city` trong QBE:

```java
Address address = new Address();
address.setCity("Huế");

Employee probe = new Employee();
probe.setAddress(address);
probe.setStatus("ACTIVE");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
        .withIgnorePaths("id", "skills", "workItems")
        .withMatcher("address.city",
                ExampleMatcher.GenericPropertyMatchers.exact().ignoreCase());

Example<Employee> example = Example.of(probe, matcher);
Iterable<Employee> result = repository.findAll(example);
```

Ý định là `status` khớp chính xác ACTIVE và `address.city` khớp Huế theo cấu hình không phân biệt hoa thường mà store hỗ trợ. Các thuộc tính tham chiếu khác vẫn `null` và bị bỏ qua.

`withMatcher("address.city", ...)` cấu hình đường dẫn, không tự điền giá trị cho `address.city`. Nếu probe không có đối tượng `address`, việc thêm cấu hình matcher không tạo ra đối tượng cha và không tự sinh tiêu chí thành phố.

Các đường dẫn là tên thuộc tính miền. Nếu cột lưu thành phố tên `city_name` nhưng thuộc tính Java vẫn là `city`, cấu hình vẫn dùng `address.city`, không phải `address.city_name`.

## 5. Quan hệ đơn trị: có thể được hỗ trợ, cần hiểu phép duyệt

Trong mô hình JPA, các quan hệ đơn trị như `@ManyToOne` hoặc `@OneToOne` có thể tham gia QBE khi được store module hỗ trợ. Ví dụ tìm nhân viên thuộc phòng ban có mã ENG:

```java
Department department = new Department();
department.setCode("ENG");

Employee probe = new Employee();
probe.setDepartment(department);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
        .withIgnorePaths("id", "department.id", "skills", "workItems");

Example<Employee> example = Example.of(probe, matcher);
Iterable<Employee> result = repository.findAll(example);
```

Ở đây mã phòng ban là giá trị mẫu trên đường dẫn `department.code`. Đối tượng `Department` mới được tạo chỉ làm probe cho truy vấn; không cần lưu nó chỉ để tìm kiếm. Không gọi thao tác ghi dữ liệu nhằm làm cho đối tượng mẫu “hợp lệ” như một entity đã được quản lý.

Tuy nhiên, cần hiểu các giới hạn sau:

- Phép duyệt quan hệ có thể cần join ở tầng store. Loại join, cách xử lý quan hệ vắng mặt và các trường hợp OR không do một cấu hình Commons tổng quát kiểm soát đầy đủ.
- Gán nguyên một `Department` đã đọc từ cơ sở dữ liệu vào probe có thể kéo theo `id`, `name` và các thuộc tính khác thành tiêu chí. Khi đó không còn chỉ tìm theo `code`.
- Getter, constructor hoặc các trường primitive trong mô hình liên quan có thể cung cấp thêm giá trị mặc định, tạo điều kiện ngoài ý muốn.
- Đồ thị quan hệ hai chiều có thể tạo chu trình. Không dùng nguyên đồ thị entity phức tạp làm probe và trông chờ QBE tự bỏ qua mọi nhánh không liên quan.

Nên dựng một probe nhỏ từ dữ liệu tìm kiếm đã được kiểm soát. Các trường metadata như version, thời gian tạo và người cập nhật cũng cần được cân nhắc nếu xuất hiện trong đồ thị probe. Auditing không tự đánh dấu các trường đó là bỏ qua trong QBE.

### Lọc theo quan hệ không đồng nghĩa nạp quan hệ

Lọc nhân viên theo `department.code` là yêu cầu chọn bản ghi. Nó không đồng thời chỉ định rằng toàn bộ phòng ban hay collection công việc phải được nạp theo một chiến lược cụ thể.

Không dùng `withMatcher("department.code", ...)` như một thay thế cho fetch plan, entity graph hoặc tối ưu truy cập quan hệ. Nếu sau truy vấn, việc đọc các thuộc tính lazy phát sinh thêm truy vấn, cần giải quyết theo cơ chế tải dữ liệu của store. Projection và chiến lược nạp dữ liệu cũng là các quyết định riêng với việc matcher diễn đạt điều kiện nào.

## 6. null ở đối tượng cha và đường dẫn con

Xét hai probe khác nhau:

```java
Employee first = new Employee();
first.setAddress(null);
```

```java
Address emptyAddress = new Address();

Employee second = new Employee();
second.setAddress(emptyAddress);
```

Probe thứ nhất không có đối tượng cha. Probe thứ hai có đối tượng cha nhưng các giá trị con đang `null`. Không nên coi chúng luôn tạo cùng một truy vấn trên mọi store.

Với chính sách bỏ qua `null`, các giá trị `null` thường không trở thành điều kiện. Nhưng cách duyệt một đối tượng nhúng, một association hoặc một tài liệu con vẫn phụ thuộc module và mapping.

Khi bật `withIncludeNullValues()`, không được suy luận rằng:

```text
address = null
```

luôn tương đương:

```text
address.city = null AND address.country = null
```

Trong cơ sở dữ liệu quan hệ, quan hệ không tồn tại, khóa ngoại null và một đối tượng nhúng có các cột null là những tình huống cần phân tích theo mapping. Trong cơ sở dữ liệu tài liệu, field cha không tồn tại, field cha bằng null và tài liệu con có các field null cũng có thể khác nhau.

Nếu ý định là tìm nhân viên không có phòng ban, hoặc tìm tài liệu có `address.city` bị thiếu nhưng `address` vẫn tồn tại, cần kiểm tra API nào của store biểu diễn chính xác điều kiện đó. Không suy diễn từ tên `withIncludeNullValues()` rằng mọi yêu cầu về tồn tại và vắng mặt đều được hỗ trợ.

Tương tự, `withIgnorePaths("address.city")` chỉ loại đường dẫn thành phố khỏi phép so khớp. Nó không loại mọi thuộc tính khác của `address`. Nếu mục tiêu là bỏ qua cả nhánh, cần cấu hình đường dẫn cha phù hợp và xác nhận hành vi trên mapping đang dùng.

## 7. Collection: đối tượng mẫu không diễn đạt phép lượng hóa phần tử

Một collection trong đối tượng miền thường dẫn đến các câu hỏi như:

```text
skills chứa "Java"
workItems có ít nhất một phần tử state = OPEN
mọi workItems đều có priority >= 8
không có workItems nào bị BLOCKED
workItems có ít nhất 3 phần tử
```

Đây là các yêu cầu về phần tử, số lượng hoặc phép lượng hóa. Không thể mặc nhiên diễn đạt chúng bằng cách gán một collection mẫu vào probe.

```java
Employee probe = new Employee();
probe.setSkills(java.util.Set.of("Java"));

Example<Employee> example = Example.of(probe);
// Không được kết luận: truy vấn này có nghĩa skills chứa Java.
```

Tương tự, thêm một `WorkItem` vào `probe.workItems` không phải cú pháp QBE dùng chung để sinh điều kiện `EXISTS` trên quan hệ một-nhiều.

Đặc biệt trong QBE của JPA, không coi collection hoặc map là các thuộc tính được hỗ trợ để xây dựng phép so khớp phần tử theo cách trên. Với store khác, cần kiểm tra hỗ trợ cụ thể; nếu có hành vi so khớp array hoặc tài liệu đặc thù, cũng không nên coi đó là hợp đồng portable của Spring Data Commons.

### Các cách hiểu sai thường gặp

| Cách làm | Kết luận không hợp lệ |
| --- | --- |
| Đặt `skills = {"Java"}` | Chắc chắn là kiểm tra collection có chứa Java |
| Đặt `workItems` có một phần tử mẫu | Chắc chắn là tồn tại phần tử khớp mẫu |
| Đặt collection rỗng | Chắc chắn là tìm những bản ghi có collection rỗng |
| Đặt collection `null` và bật INCLUDE | Chắc chắn là kiểm tra không có phần tử |
| Cấu hình `withMatcher("workItems.state", ...)` | Tự tạo phép duyệt mọi phần tử và truy vấn EXISTS |
| Dùng `matchingAll()` với nhiều thuộc tính phần tử | Bảo đảm mọi thuộc tính khớp trên cùng một phần tử |

Một đường dẫn dùng dấu chấm không tự bổ sung ngữ nghĩa “ít nhất một phần tử”. Collection rỗng cũng không đồng nghĩa với giá trị scalar null. Cần API có toán tử rõ ràng cho yêu cầu đó.

## 8. Cùng một phần tử hay các phần tử khác nhau?

Yêu cầu “có công việc OPEN với priority ít nhất 8” cần được hiểu là hai điều kiện áp dụng lên **cùng một công việc**.

Giả sử một nhân viên có:

| Công việc | state | priority |
| --- | --- | --- |
| W1 | OPEN | 2 |
| W2 | DONE | 9 |

Nhân viên này không thỏa yêu cầu, vì không có phần tử nào vừa OPEN vừa có priority ít nhất 8.

Hai biểu thức sau không tương đương:

```text
EXISTS workItem: state = OPEN AND priority >= 8
```

```text
(EXISTS workItem: state = OPEN)
AND (EXISTS workItem: priority >= 8)
```

Biểu thức thứ hai cho phép W1 đáp ứng điều kiện đầu và W2 đáp ứng điều kiện sau. QBE không cung cấp API tổng quát để khai báo phạm vi biến phần tử và cấu trúc EXISTS này.

Trong SQL, ý định có thể được minh họa bằng một truy vấn con tương quan. Tên bảng và cột sau chỉ dùng để giải thích:

```sql
SELECT e.*
FROM employee e
WHERE EXISTS (
    SELECT 1
    FROM work_item w
    WHERE w.employee_id = e.id
      AND w.state = 'OPEN'
      AND w.priority >= 8
)
```

Trong MongoDB, điều kiện trên cùng một phần tử array thường cần toán tử như `$elemMatch` nếu dữ liệu được nhúng theo cấu trúc thích hợp. Không coi hai điều kiện trên hai đường dẫn array là tự động bảo đảm cùng phần tử.

Tách rõ yêu cầu “cùng phần tử”, “mọi phần tử” và “các phần tử có thể khác nhau” trước khi lựa chọn API. Sai lệch ở đây là sai ngữ nghĩa nghiệp vụ, không chỉ là vấn đề hiệu năng.

## 9. Các cấu hình matcher không mở rộng ngôn ngữ truy vấn

`ExampleMatcher` có nhiều cấu hình hữu ích, nhưng mỗi cấu hình có phạm vi riêng:

| Cấu hình | Công dụng | Không cung cấp |
| --- | --- | --- |
| `matchingAll()` | Kết hợp các điều kiện được xét theo AND | Nhóm AND/OR lồng nhau tùy ý |
| `matchingAny()` | Kết hợp các điều kiện được xét theo OR | Ràng buộc bắt buộc nằm ngoài nhóm OR |
| `contains()` cho chuỗi | Chọn cách so khớp nội dung chuỗi nếu store hỗ trợ | Kiểm tra membership trong collection |
| `withIgnorePaths(...)` | Loại các đường dẫn khỏi Example | Join, EXISTS hoặc điều kiện âm |
| `withIncludeNullValues()` | Đưa null vào phép so khớp theo store | Mọi dạng kiểm tra tồn tại field hoặc collection rỗng |
| `withTransformer(...)` | Biến đổi hoặc loại giá trị mẫu của thuộc tính | Trả về một cây Criteria hay một predicate tùy ý |

Ví dụ, transformer có thể dùng để chuẩn hóa giá trị tìm kiếm. Nó không biến `level = 8` trong probe thành `level >= 8`. Muốn so sánh khoảng cần cơ chế truy vấn có hỗ trợ toán tử đó.

Matcher cũng không phải nơi áp đặt đầy đủ các ràng buộc như `tenantId = hiện tại AND (A OR B)` bằng cách chuyển toàn bộ Example sang `matchingAny()`. Điều kiện bắt buộc và nhánh tùy chọn cần được giữ đúng cấu trúc logic trong một API phù hợp; tầng kiểm soát truy cập cần bảo vệ phạm vi dữ liệu tương ứng.

## 10. Chuyển sang Specification trong bối cảnh JPA

Khi ứng dụng dùng Spring Data JPA, `Specification` là một lựa chọn cho điều kiện động cần nhóm logic hoặc join rõ ràng. Đây là khả năng của module JPA, không phải hợp đồng bắt buộc của mọi Spring Data store.

### 10.1. Giữ nguyên nhóm AND/OR

Repository công bố khả năng Specification:

```java
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.repository.CrudRepository;

public interface EmployeeJpaRepository
        extends CrudRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {
}
```

Với giả định `address` là đối tượng nhúng của entity `Employee`, điều kiện nghiệp vụ ở phần trước có thể được biểu diễn như sau:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

Specification<Employee> activeAndNameOrCity = (root, query, cb) ->
        cb.and(
                cb.equal(root.get("status"), "ACTIVE"),
                cb.or(
                        cb.like(
                                cb.lower(root.<String>get("fullName")),
                                "%an%"),
                        cb.equal(root.get("address").get("city"), "Huế")
                )
        );

Page<Employee> page = jpaRepository.findAll(
        activeAndNameOrCity,
        PageRequest.of(0, 20, Sort.by("id")));
```

Các giá trị trong ví dụ là hằng để tập trung vào nhóm điều kiện. Với đầu vào thực tế cho biểu thức LIKE, cần quy định cách xử lý các ký tự wildcard theo yêu cầu tìm kiếm.

Cấu trúc của predicate phản ánh trực tiếp `ACTIVE AND (tên OR thành phố)`. Nếu `address` là association thay vì đối tượng nhúng, cần thiết kế phép join tương ứng; không sao chép nguyên cách truy cập đường dẫn mà bỏ qua mapping.

### 10.2. Điều kiện trên cùng phần tử của quan hệ collection

Giả sử `workItems` là association collection hợp lệ của entity `Employee`. Có thể dùng một join duy nhất cho hai điều kiện trên công việc:

```java
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import org.springframework.data.jpa.domain.Specification;

Specification<Employee> hasOpenHighPriorityWorkItem =
        (root, query, cb) -> {
            Join<Employee, WorkItem> item =
                    root.join("workItems", JoinType.INNER);

            query.distinct(true);

            return cb.and(
                    cb.equal(item.get("state"), "OPEN"),
                    cb.ge(item.<Integer>get("priority"), 8)
            );
        };
```

Ví dụ áp dụng hai điều kiện lên cùng biến join `item`. `distinct` thể hiện yêu cầu loại nhân viên bị lặp khi có nhiều công việc cùng khớp; cách thực thi và chi phí cần được đánh giá trên truy vấn thực tế.

Đây là đoạn minh họa cho truy vấn đọc qua API Specification của JPA dùng namespace `jakarta.persistence`. Không xem nó là mã dùng chung cho MongoDB hay mọi thế hệ dependency. Khi cần phân trang hoặc tối ưu với collection lớn, nên cân nhắc truy vấn EXISTS thay cho join và kiểm tra cả truy vấn lấy dữ liệu lẫn truy vấn đếm.

## 11. Chọn cơ chế theo store và loại yêu cầu

| Yêu cầu | QBE có phù hợp? | Hướng xử lý |
| --- | --- | --- |
| Lọc tùy chọn trên một số thuộc tính scalar bằng giá trị mẫu | Thường phù hợp | QBE với matcher rõ ràng |
| So khớp thuộc tính trong đối tượng nhúng | Có thể phù hợp | QBE nếu store hỗ trợ mapping và đường dẫn |
| Lọc theo quan hệ đơn trị | Phụ thuộc store | Kiểm tra QBE của module; dùng API khác nếu cần kiểm soát join |
| `A AND (B OR C)` | Không biểu diễn trực tiếp bằng một matcher phẳng | Specification, Querydsl hoặc truy vấn khai báo rõ theo module |
| So sánh khoảng, phủ định hoặc điều kiện tổng hợp | Không coi probe là đủ | Chọn API có toán tử tương ứng |
| Tồn tại phần tử collection cùng thỏa nhiều điều kiện | Không có ngữ nghĩa QBE dùng chung | EXISTS, join hoặc toán tử array thích hợp |
| Lọc dữ liệu nằm ở tài liệu khác | Không suy ra từ việc có object reference trong Java | Dùng cơ chế truy vấn, tham chiếu hoặc aggregation mà store hỗ trợ |
| Báo cáo có group, aggregate, nhiều nguồn dữ liệu | Thường vượt phạm vi QBE | Truy vấn chuyên biệt theo store và mô hình kết quả riêng |

Một derived query method phù hợp khi điều kiện đơn giản, ổn định và tên method vẫn dễ đọc. Đừng chuyển một biểu thức động phức tạp sang tên method quá dài chỉ để tránh dùng API truy vấn rõ ràng.

Với MongoDB, `Criteria`, truy vấn khai báo hoặc aggregation có thể phù hợp tùy yêu cầu. Việc `address` được nhúng trong cùng tài liệu khác với `department` là một tham chiếu sang tài liệu khác. Không suy luận rằng QBE sẽ tự thực hiện một phép join chỉ vì mô hình Java có `Department department`.

Với JPA, Specification, Querydsl hoặc truy vấn `@Query` là các lựa chọn cần cân nhắc theo dependency và kiến trúc hiện có. Chọn cơ chế đơn giản nhất có thể biểu diễn đúng yêu cầu, rồi tối ưu dựa trên mapping, chỉ mục và dữ liệu thực tế.

## 12. Không dùng lọc sau truy vấn để che giới hạn của QBE

Một cách xử lý dễ xuất hiện là dùng QBE để tìm gần đúng, rồi lọc phần còn lại bằng Java:

```java
// Ý tưởng cần tránh nếu xem đây là truy vấn phân trang hoàn chỉnh:
// 1. Đọc một page bằng QBE.
// 2. Lọc tiếp nhóm điều kiện hoặc collection trong bộ nhớ.
// 3. Trả lại page và totalElements ban đầu.
```

Giả sử truy vấn ban đầu trả 20 nhân viên nhưng chỉ 6 người thỏa điều kiện sau lọc. Cách xử lý này có thể gây ra:

- Page chỉ còn 6 phần tử dù các bản ghi hợp lệ khác vẫn nằm ở page sau.
- `totalElements` phản ánh điều kiện QBE ban đầu, không phản ánh điều kiện nghiệp vụ cuối cùng.
- Kết quả sắp xếp và phân trang không còn được tính trên toàn bộ tập bản ghi hợp lệ.
- Việc duyệt quan hệ lazy để lọc collection có thể phát sinh nhiều truy vấn bổ sung.

Tương tự, chạy hai Example rồi hợp nhất kết quả để giả lập OR đòi hỏi xử lý trùng lặp, thứ tự, phân trang và tổng số bản ghi. Phép hợp nhất đơn giản trên hai page riêng không tạo thành một page đúng của tập hợp kết quả cuối.

Lọc trong bộ nhớ có thể hợp lý cho một tập dữ liệu nhỏ đã chủ động nạp đầy đủ và không có hợp đồng phân trang từ cơ sở dữ liệu. Tuy nhiên, đó là một quyết định kiến trúc cần được mô tả rõ, không phải khả năng biểu diễn mới của QBE.

## 13. Các tình huống để tự kiểm tra lựa chọn API

### Tình huống A: tìm nhân viên theo thông tin tùy chọn

Đầu vào gồm `status`, `active` và `address.city`; mỗi trường không truyền thì không lọc. Các điều kiện được truyền đều phải thỏa.

QBE là ứng viên phù hợp nếu store hỗ trợ `address.city`. Dùng `matchingAll()`, xử lý `null` rõ ràng và tạo probe nhỏ. Xác định riêng trường hợp không có bộ lọc nào để tránh một truy vấn quá rộng ngoài ý muốn.

### Tình huống B: ACTIVE và thỏa tên hoặc thành phố

Điều kiện là `status = ACTIVE AND (nameMatch OR cityMatch)`.

Một matcher phẳng không biểu diễn đúng nhóm logic. Chuyển sang API hỗ trợ kết hợp predicate hoặc truy vấn có cấu trúc rõ ràng.

### Tình huống C: có công việc OPEN và ưu tiên cao

Điều kiện áp dụng lên cùng một phần tử của `workItems`.

Không tạo collection một phần tử trong probe để giả lập EXISTS. Chọn API diễn đạt cùng phần tử, kiểm soát khả năng nhân bản bản ghi và kiểm tra kết quả phân trang nếu có.

### Tình huống D: lọc phòng ban nhưng cần trả tên phòng ban ngay

Đây là hai yêu cầu: điều kiện lọc theo quan hệ và hình dạng dữ liệu hoặc chiến lược tải kết quả.

QBE có thể đáp ứng phần lọc nếu store hỗ trợ quan hệ đó. Phần lấy dữ liệu liên quan cần được thiết kế riêng bằng khả năng projection, fetch hoặc truy vấn của store. Việc lọc thành công không chứng minh chiến lược tải đã tối ưu.

### Tình huống E: tìm bản ghi không có địa chỉ

Trước tiên cần định nghĩa “không có”: quan hệ null, các cột nhúng null, field không tồn tại hay tài liệu con rỗng.

Chỉ sau khi xác định đúng trạng thái lưu trữ mới chọn cấu hình QBE hoặc truy vấn riêng. Không dùng một giá trị `null` trong probe như một ký hiệu chung cho mọi trường hợp vắng mặt.

## 14. Những điểm cần giữ khi thiết kế repository

QBE phát huy hiệu quả khi đối tượng mẫu phản ánh một tập điều kiện thuộc tính tương đối đơn giản. Đường dẫn lồng nhau có thể được hỗ trợ, nhưng không tự mang theo nhóm logic, phép duyệt collection, chiến lược tải quan hệ hoặc phép join qua mọi loại kho dữ liệu.

Trước khi mở rộng repository, hãy viết điều kiện nghiệp vụ thành biểu thức rõ ràng: nhóm nào bắt buộc, nhánh nào thay thế, điều kiện nào áp dụng lên cùng một phần tử và dữ liệu nằm trong cùng bản ghi hay ở quan hệ khác. Sau đó đối chiếu với khả năng của Commons và store module đang dùng.

Nếu không biểu diễn được điều kiện một cách trực tiếp và kiểm chứng được, nên chuyển sang API truy vấn phù hợp. Cách lựa chọn này giữ đúng ngữ nghĩa tìm kiếm, metadata phân trang và phạm vi dữ liệu khi ứng dụng phát triển.
