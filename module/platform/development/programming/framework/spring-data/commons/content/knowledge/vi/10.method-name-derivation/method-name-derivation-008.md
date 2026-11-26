# Distinct, IgnoreCase và AllIgnoreCase

## 1. Ba từ khóa, ba phạm vi tác động

Tên phương thức suy diễn trong Spring Data không chỉ mô tả thuộc tính và toán tử. Nó còn có thể chứa các từ khóa làm thay đổi cách chọn kết quả hoặc so sánh giá trị. Trong nhóm này, `Distinct`, `IgnoreCase` và `AllIgnoreCase` dễ bị hiểu thành cùng một loại tùy chọn, trong khi chúng tác động đến những phần khác nhau của truy vấn.

- `Distinct` biểu đạt yêu cầu kết quả phân biệt theo cách mô-đun kho dữ liệu thực thi truy vấn.
- `IgnoreCase` yêu cầu so sánh không phân biệt hoa thường cho một điều kiện thuộc tính cụ thể.
- `AllIgnoreCase` yêu cầu áp dụng chế độ không phân biệt hoa thường cho các thuộc tính phù hợp trong phần điều kiện.

`Distinct` không phải quy tắc chuẩn hóa chuỗi. `IgnoreCase` không tự gộp các bản ghi có cùng tên. `AllIgnoreCase` cũng không tự làm cho mọi kiểu dữ liệu trở thành chuỗi hoặc đổi cách sắp xếp kết quả.

Trong Spring Data Commons, bộ phân tích tên phương thức cung cấp cấu trúc chung để nhận diện các thành phần này. Mô-đun kho dữ liệu chịu trách nhiệm chuyển cấu trúc đó thành truy vấn và xác định mức hỗ trợ thực tế. Việc một từ khóa được bộ phân tích nhận diện chưa đủ để kết luận mọi kho dữ liệu thực hiện nó giống nhau.

Bài học dùng Spring Data JPA để minh họa hành vi cụ thể. Với mô-đun khác, cần đối chiếu hỗ trợ keyword, kiểu trả về và quy tắc so sánh của mô-đun đó.

## 2. Đọc một tên phương thức theo từng phần

Xét phương thức:

```java
List<Person> findDistinctByLastNameIgnoreCase(String lastName);
```

Có thể đọc theo trình tự:

| Thành phần | Vai trò |
| --- | --- |
| `find` | Chủ đích truy xuất dữ liệu |
| `Distinct` | Yêu cầu kết quả phân biệt |
| `By` | Bắt đầu phần điều kiện |
| `LastName` | Đường dẫn thuộc tính cần so sánh |
| `IgnoreCase` | Chế độ so sánh của điều kiện trên `lastName` |

Tên phương thức không nói “lấy danh sách họ duy nhất đã chuyển thành chữ thường”. Kiểu trả về là `List<Person>`, nên đối tượng kết quả trong ví dụ JPA vẫn là entity `Person`.

So sánh với:

```java
List<Person> findByFirstNameAndLastNameAllIgnoreCase(
        String firstName, String lastName);
```

Ở đây `AllIgnoreCase` áp dụng cho các thuộc tính phù hợp trong phần điều kiện, bao gồm cả `firstName` và `lastName`. Nó không chỉ bổ nghĩa cho thuộc tính đứng ngay trước marker.

Một vị trí dễ đọc cho marker toàn phần là cuối chuỗi điều kiện, trước `OrderBy` nếu có:

```java
List<Person> findByFirstNameAndLastNameAllIgnoreCaseOrderByIdAsc(
        String firstName, String lastName);
```

Marker về hoa thường không đổi toán tử `And` thành `Or`, không thêm nhóm ngoặc và không thay đổi phạm vi dữ liệu theo người dùng hoặc tenant.

## 3. Mô hình và dữ liệu dùng trong ví dụ

Giả sử ứng dụng có entity JPA sau, dùng Jakarta Persistence:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "people")
public class Person {
    @Id
    private Long id;

    private String firstName;
    private String lastName;
    private Integer age;

    protected Person() {
    }

    public Person(Long id, String firstName, String lastName, Integer age) {
        this.id = id;
        this.firstName = firstName;
        this.lastName = lastName;
        this.age = age;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public Integer getAge() {
        return age;
    }
}
```

Dữ liệu minh họa:

| id | firstName | lastName | age |
| --- | --- | --- | --- |
| 1 | An | Tran | 25 |
| 2 | an | Tran | 25 |
| 3 | AN | tran | 31 |
| 4 | Binh | Tran | 25 |
| 5 | An | Trần | 25 |
| 6 | An | Tran | 25 |

Các bảng kết quả phía sau dùng giả định so sánh chuỗi thông thường phân biệt hoa thường và phân biệt dấu; phép chuyển hoa/thường cho phần chữ ASCII hoạt động như mong đợi. Đây là giả định để đọc ví dụ, không phải mặc định chung của mọi cơ sở dữ liệu.

Nếu collation của môi trường đã không phân biệt hoa thường hoặc không phân biệt dấu, một số kết quả so sánh có thể khác. Cần kiểm chứng trên hệ quản trị, mapping và collation của dự án thực tế.

Hai dòng có id 1 và 6 cùng giá trị tên, họ và tuổi nhưng vẫn là hai entity khác nhau. Đây là điểm quan trọng để hiểu `Distinct`.

## 4. Distinct: phân biệt cái gì?

### 4.1. Kết quả entity khác với giá trị một thuộc tính

Với repository JPA trả entity:

```java
import java.util.List;
import org.springframework.data.repository.Repository;

public interface PersonRepository extends Repository<Person, Long> {
    List<Person> findDistinctByLastName(String lastName);
}
```

Ý định truy vấn có thể hình dung bằng JPQL:

```sql
select distinct p
from Person p
where p.lastName = :lastName
```

Đây là JPQL minh họa ngữ nghĩa, không phải cam kết chuỗi SQL thực tế mà provider sẽ sinh.

Với đầu vào `"Tran"`, các entity có id 1, 2, 4 và 6 vẫn được giữ. Chúng có cùng họ nhưng khác định danh. `Distinct` không gộp chúng thành một người và không tự chọn một dòng đại diện cho họ `Tran`.

Nếu không có join làm nhân số hàng và mỗi entity vốn chỉ xuất hiện một lần, thêm `Distinct` có thể không làm thay đổi danh sách entity nhận được.

### 4.2. Vai trò khi quan hệ làm nhân số hàng

Giả sử mô hình được mở rộng với quan hệ `roles`, mỗi role có thuộc tính `name`. Một người có thể vừa là `EDITOR` vừa là `REVIEWER`.

```java
List<Person> findDistinctByRolesNameIn(Collection<String> roleNames);
```

Ví dụ này cần mô hình quan hệ và import `java.util.Collection` tương ứng. Nó minh họa tình huống join có thể tạo nhiều hàng trung gian cùng chỉ đến một người khi nhiều role khớp bộ lọc.

`Distinct` thể hiện yêu cầu kết quả entity phân biệt. Không nên coi việc một provider đã tự khử lặp trong một đường thực thi là bằng chứng rằng mọi truy vấn tương tự đều có cùng hành vi.

Cũng không nên thêm `Distinct` để che một join sai hoặc thiếu điều kiện. Trước hết phải xác định đúng quan hệ, bộ lọc và đơn vị kết quả cần trả.

### 4.3. Tên phần subject không tự chọn cột

Không nên đặt tên như `findDistinctLastNameByFirstName` rồi suy ra framework sẽ tự thực hiện `select distinct lastName`. Một phần văn bản mô tả trong subject không thay thế hợp đồng projection và cơ chế chọn dữ liệu.

Nếu muốn danh sách giá trị họ phân biệt trong JPA, có thể khai báo rõ:

```java
import java.util.List;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;

public interface PersonNameRepository extends Repository<Person, Long> {
    @Query("select distinct p.lastName from Person p")
    List<String> findDistinctLastNameValues();
}
```

Trong giả định dữ liệu và collation đã nêu, tập giá trị là `Tran`, `tran`, `Trần`. Thứ tự chưa được quy định vì truy vấn không có `order by`.

`org.springframework.data.jpa.repository.Query` là annotation của JPA, không phải annotation truy vấn chung để dùng nguyên trạng cho mọi mô-đun Spring Data.

## 5. IgnoreCase: bổ nghĩa cho một điều kiện

### 5.1. Một thuộc tính chuỗi

```java
List<Person> findByFirstNameIgnoreCase(String firstName);
```

Với đầu vào `"an"`, kết quả minh họa chứa các id 1, 2, 3, 5 và 6. Việc so sánh tên không phân biệt `An`, `an` và `AN` theo quy tắc của môi trường thực thi.

Trong Spring Data JPA, phép so sánh này thường được biểu đạt bằng cách chuyển hai phía về cùng dạng hoa/thường, chẳng hạn ý tưởng:

```sql
upper(p.firstName) = upper(:firstName)
```

Đây là cách giải thích hành vi trong JPA, không phải cam kết cách dịch giống nhau ở mọi kho dữ liệu. SQL, hàm, collation và chi tiết provider cần được kiểm tra trong cấu hình thật.

`IgnoreCase` tác động đến so sánh; nó không cập nhật dữ liệu lưu trữ. Kết quả vẫn có thể chứa nguyên các giá trị `An`, `an` hoặc `AN`.

### 5.2. Nhiều điều kiện nhưng chỉ một điều kiện bỏ qua hoa thường

```java
List<Person> findByFirstNameIgnoreCaseAndLastName(
        String firstName, String lastName);
```

Lời gọi với `("an", "Tran")` cho tập id 1, 2 và 6 theo giả định của ví dụ:

- `firstName` được so sánh không phân biệt hoa thường.
- `lastName` vẫn dùng quy tắc so sánh thông thường.
- Id 3 bị loại vì họ là `tran` thay vì `Tran` trong môi trường đang giả định phân biệt hoa thường.
- Id 5 bị loại vì họ có dấu là `Trần`.

Nếu muốn cả hai điều kiện đều bỏ qua hoa thường, có thể viết riêng marker cho từng điều kiện:

```java
List<Person> findByFirstNameIgnoreCaseAndLastNameIgnoreCase(
        String firstName, String lastName);
```

Hoặc sử dụng `AllIgnoreCase` như phần tiếp theo.

### 5.3. Kết hợp với toán tử chuỗi khác

Ở mô-đun có hỗ trợ, marker có thể kết hợp với toán tử chuỗi:

```java
List<Person> findByLastNameContainingIgnoreCase(String fragment);
```

`Containing` quyết định kiểu khớp chuỗi con; `IgnoreCase` quyết định cách xử lý hoa thường. Hai ý nghĩa cần được đọc riêng.

Không suy ra rằng mọi toán tử hoặc mọi kiểu thuộc tính đều kết hợp được với `IgnoreCase`. Cũng không coi việc bộ phân tích nhận diện tên là bằng chứng truy vấn đã được provider hỗ trợ đầy đủ.

## 6. AllIgnoreCase: áp dụng cho mọi thuộc tính phù hợp

### 6.1. Hai thuộc tính chuỗi

```java
List<Person> findByFirstNameAndLastNameAllIgnoreCase(
        String firstName, String lastName);
```

Với `("an", "tran")`, các id phù hợp là 1, 2, 3 và 6. Cả tên và họ đều so sánh không phân biệt hoa thường; id 5 vẫn không khớp theo giả định phân biệt dấu.

Với các điều kiện chuỗi trong ví dụ JPA, cách này tương đương ý định của việc đặt `IgnoreCase` cho từng điều kiện. Nó giúp tránh bỏ sót marker khi phương thức có nhiều thuộc tính cần cùng một chế độ so sánh.

### 6.2. Thuộc tính chuỗi và thuộc tính số

```java
List<Person> findByFirstNameAndAgeAllIgnoreCase(
        String firstName, Integer age);
```

Trong JPA, `firstName` là chuỗi nên có thể áp dụng chế độ không phân biệt hoa thường. `age` là số nên vẫn được so sánh bằng giá trị số theo toán tử tương ứng.

Với `("an", 25)`, tập id minh họa là 1, 2, 5 và 6. Id 3 bị loại vì tuổi là 31, không phải vì cách viết tên.

`AllIgnoreCase` không chuyển số thành chuỗi và không biến số 25 thành một giá trị có khái niệm chữ hoa/chữ thường. Từ “All” cần được hiểu cùng giới hạn “các thuộc tính phù hợp”.

Ngược lại, yêu cầu tường minh sau không phù hợp với thuộc tính `Integer` trong JPA:

```java
// Ví dụ không hợp lệ cho thuộc tính Integer trong JPA.
List<Person> findByAgeIgnoreCase(Integer age);
```

Với marker cục bộ `IgnoreCase`, JPA yêu cầu khả năng thực hiện xử lý hoa/thường cho thuộc tính tương ứng. Không nên kỳ vọng nó âm thầm bỏ qua yêu cầu này như trường hợp áp dụng toàn phần khi có thể. Thời điểm phát hiện lỗi còn phụ thuộc quá trình khởi tạo và thực thi query của ứng dụng.

### 6.3. Không suy ra IgnoreCase cho mọi kiểu được lưu thành văn bản

Một enum, UUID hoặc kiểu domain có converter có thể được lưu dưới dạng văn bản ở cơ sở dữ liệu, nhưng kiểu thuộc tính Java không nhất thiết là `String`. Điều đó không tự bảo đảm derived query hỗ trợ `IgnoreCase` trên thuộc tính ấy.

Cần đánh giá kiểu thuộc tính mà mô-đun query nhìn thấy, converter và cách thực thi. Nếu muốn tìm theo một khóa văn bản đã chuẩn hóa, có thể cần một thuộc tính hoặc truy vấn được thiết kế rõ cho mục đích đó.

## 7. Kết hợp Distinct với IgnoreCase

```java
List<Person> findDistinctByLastNameIgnoreCase(String lastName);
```

Hai marker giải quyết hai vấn đề độc lập:

1. `IgnoreCase` xác định cách so sánh `lastName` để tìm các entity phù hợp.
2. `Distinct` yêu cầu kết quả phân biệt theo biểu thức được chọn.

Với `"tran"`, tập entity minh họa có id 1, 2, 3, 4 và 6. Tất cả vẫn được giữ vì có định danh khác nhau, kể cả hai người có cùng toàn bộ giá trị tên, họ và tuổi.

Không có bước tự động chuyển tất cả họ thành `tran` rồi chỉ trả một người. Nếu cần danh sách họ đã chuẩn hóa, phải xác định một biểu thức kết quả khác.

Trong JPA, có thể khai báo rõ:

```java
@Query("select distinct lower(p.lastName) from Person p")
List<String> findDistinctLowercaseLastNames();
```

Với giả định dữ liệu và collation của bài, tập kết quả là `tran` và `trần`. Đây là các giá trị được biểu thức `lower` tạo ra, không còn là entity `Person` hoặc giá trị hiển thị nguyên gốc.

Nếu sản phẩm muốn gộp nhiều cách viết thành một nhóm nhưng vẫn hiển thị cách viết đại diện, cần thêm quy tắc chọn đại diện. Ví dụ, có thể phải ưu tiên tên đã được xác minh hoặc một bản ghi chuẩn của nghiệp vụ. Chỉ viết `Distinct` không quyết định được quy tắc đó.

## 8. CountDistinctBy không đồng nghĩa đếm giá trị thuộc tính phân biệt

Xét các phương thức:

```java
long countByLastNameIgnoreCase(String lastName);

long countDistinctByLastNameIgnoreCase(String lastName);
```

Một cách hiểu dễ sai là cho rằng phương thức thứ hai đếm số cách viết họ phân biệt. Với entity JPA đơn giản có khóa `id` như ví dụ, derived count distinct đếm định danh entity phân biệt, không tự đổi biểu thức thành `count(distinct lastName)`.

Có thể hình dung ý định truy vấn count distinct trong trường hợp này bằng JPQL:

```sql
select count(distinct p.id)
from Person p
where upper(p.lastName) = upper(:lastName)
```

Với `"tran"`, cả hai phương thức đều trả 5 trong dữ liệu minh họa: id 1, 2, 3, 4 và 6. Nếu không có join làm nhân số hàng, việc thêm distinct theo định danh không nhất thiết làm số đếm giảm.

Khi mục tiêu thực sự là đếm các giá trị họ phân biệt trên toàn bộ dữ liệu, cần diễn đạt rõ trong JPA:

```java
@Query("select count(distinct p.lastName) from Person p")
long countDistinctLastNameValues();
```

Theo giả định phân biệt hoa thường và dấu, giá trị đếm là 3: `Tran`, `tran`, `Trần`. Biểu thức đếm giá trị thuộc tính này không phải hợp đồng của `countDistinctByLastNameIgnoreCase`.

Cần phân biệt thêm:

| Câu hỏi nghiệp vụ | Đơn vị cần đếm |
| --- | --- |
| Có bao nhiêu người có họ phù hợp? | Entity hoặc định danh người |
| Có bao nhiêu giá trị họ khác nhau theo quy tắc DB? | Giá trị thuộc tính |
| Có bao nhiêu nhóm họ sau chuẩn hóa? | Khóa nhóm đã chuẩn hóa theo chính sách rõ ràng |
| Có bao nhiêu hàng quan hệ phù hợp? | Hàng hoặc cặp quan hệ, có thể khác số người |

Phép `count` trên biểu thức thuộc tính cũng có quy tắc với giá trị `null`; không nên đồng nhất nó với đếm tất cả entity. Nếu cần đếm một nhóm “chưa có họ”, hãy mô tả riêng ý nghĩa và biểu thức tương ứng.

Không nên khái quát ví dụ count distinct của JPA thành cách triển khai chung cho mọi kho dữ liệu. Mô-đun khác có thể có quy tắc hoặc giới hạn khác; kiểu khóa phức tạp và query có join cũng cần kiểm tra riêng.

## 9. Marker trong tên không tự sửa một truy vấn đã khai báo

Các marker đang học thuộc cơ chế suy diễn từ tên phương thức. Nếu một truy vấn khai báo hoặc named query được chọn để thực thi, ngữ nghĩa chính nằm trong truy vấn đó.

Ví dụ JPA sau có tên gây hiểu nhầm:

```java
@Query("select p from Person p where p.lastName = :lastName")
List<Person> findByLastNameIgnoreCase(
        @Param("lastName") String lastName);
```

Không được kỳ vọng chỉ riêng hậu tố `IgnoreCase` sẽ tự bổ sung hàm chuyển hoa/thường vào JPQL đã khai báo. Phép `=` trong query và collation thực tế quyết định cách so sánh của truy vấn này.

Nếu chủ đích là so sánh bằng một biểu thức chuyển hoa/thường trong JPA, hãy viết rõ:

```java
@Query("select p from Person p "
     + "where upper(p.lastName) = upper(:lastName)")
List<Person> searchByLastNameWithoutCase(
        @Param("lastName") String lastName);
```

Các snippet dùng `org.springframework.data.jpa.repository.Query` và `org.springframework.data.repository.query.Param` trên một interface repository phù hợp.

Tương tự, việc tên phương thức chứa `Distinct` không phải cơ chế đáng tin cậy để thêm `distinct` vào một query khai báo chưa có nó. Tên, biểu thức truy vấn và kiểu kết quả phải thể hiện cùng một hợp đồng.

Điểm này hữu ích khi sửa lỗi: trước khi phân tích từng từ khóa trong tên, hãy xác định phương thức đang thực sự dùng derived query, query khai báo hay implementation fragment.

## 10. IgnoreCase khi lọc khác IgnoreCase khi sắp xếp

Xét phương thức:

```java
List<Person> findByFirstNameAllIgnoreCaseOrderByLastNameAsc(
        String firstName);
```

`AllIgnoreCase` tác động đến phần điều kiện phù hợp, ở đây là `firstName`. Nó không biến `OrderByLastNameAsc` thành sắp xếp không phân biệt hoa thường.

Nếu cần một yêu cầu sắp xếp động như vậy, Spring Data có thể biểu đạt qua `Sort.Order`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
        Sort.Order.asc("lastName").ignoreCase(),
        Sort.Order.asc("id"));

Pageable request = PageRequest.of(0, 20, sort);
Page<Person> page = repository.findByFirstNameIgnoreCase("an", request);
```

Repository tương ứng cần phương thức:

```java
Page<Person> findByFirstNameIgnoreCase(
        String firstName, Pageable pageable);
```

Đây là yêu cầu sắp xếp cần được mô-đun và kiểu thuộc tính hỗ trợ, không phải bảo đảm mọi kho dữ liệu sẽ thực hiện giống nhau. Khóa phụ `id` giúp có thứ tự xác định khi các giá trị tên bằng nhau theo tiêu chí sắp xếp.

Cần tách rõ ba câu hỏi:

- Điều kiện nào dùng so sánh không phân biệt hoa thường?
- Kết quả có được yêu cầu phân biệt không và phân biệt theo biểu thức nào?
- Kết quả được sắp xếp theo quy tắc nào?

Không có marker nào trong ba marker của bài tự trả lời thay cho cả ba câu hỏi.

## 11. Distinct, phân trang và projection phải cùng một ngữ nghĩa

### 11.1. Trang dữ liệu và tổng đếm

Một repository JPA có thể có phương thức:

```java
Page<Person> findDistinctByLastNameIgnoreCase(
        String lastName, Pageable pageable);
```

Người gọi mong nhận một trang người phân biệt phù hợp điều kiện và tổng tương ứng với cùng tập người đó. Nếu thêm join hoặc đổi sang query khai báo, phải kiểm tra query dữ liệu và query đếm còn cùng đơn vị kết quả hay không.

Các trường hợp cần chú ý gồm:

- Query dữ liệu loại hàng trùng nhưng count đếm hàng join.
- Query đếm thiếu một điều kiện đang có ở query dữ liệu.
- Giới hạn được áp dụng ở một bước chưa phù hợp với cách khử lặp mong muốn.
- Provider có cách xử lý riêng đối với collection fetch join và phân trang.

Không nên đọc một danh sách, khử lặp bằng `Set` sau đó rồi lấy độ dài danh sách làm tổng của `Page`. Cách đó có thể làm trang thiếu phần tử, bỏ sót dữ liệu hoặc tạo tổng không đúng với toàn bộ tập phù hợp.

### 11.2. Projection không phải phép khử lặp tùy ý

Nếu đổi `List<Person>` thành projection chỉ gồm họ và tên, biểu thức select thực tế có thể thay đổi theo cơ chế projection của mô-đun. Kết luận về distinct của truy vấn trả entity không được tự áp dụng nguyên vẹn cho mọi projection.

Hai người khác id có thể cho cùng nội dung DTO. Nhưng sự giống nhau của DTO không tự quy định framework sẽ khử lặp DTO bằng `equals` ở Java. Cần kiểm tra biểu thức được chọn, cách mô-đun dựng kết quả và query đếm nếu có.

Nếu yêu cầu là “mỗi cặp họ và tên chỉ xuất hiện một lần”, hãy mô tả rõ tập giá trị đó bằng projection và query được mô-đun hỗ trợ. Đừng trả entity rồi hy vọng `Distinct` tự bỏ qua định danh.

### 11.3. Distinct cùng OrderBy có thể chịu ràng buộc của DB

Một số tổ hợp giữa `distinct`, biểu thức sắp xếp và danh sách được chọn có thể gặp giới hạn từ hệ quản trị hoặc provider. Ví dụ, sắp xếp bằng biểu thức chuyển hoa/thường phải được xem cùng biểu thức select thực tế.

Không cần suy đoán chi tiết SQL để viết mọi repository, nhưng khi tổ hợp này gây lỗi hoặc hiệu năng kém, cần kiểm tra query sinh ra và hợp đồng của kho dữ liệu. Đổi tên phương thức không thay thế bước phân tích ấy.

## 12. Collation, Unicode và chuẩn hóa dữ liệu

### 12.1. Không phân biệt hoa thường khác không phân biệt dấu

`IgnoreCase` yêu cầu bỏ qua khác biệt hoa thường. Nó không tự yêu cầu bỏ dấu, xóa khoảng trắng, gộp dấu câu hoặc sửa lỗi chính tả.

Trong giả định của bài, `Tran` và `tran` có thể cùng phù hợp một phép so sánh bỏ qua hoa thường; `Trần` vẫn là giá trị khác. Nếu collation của DB có quy tắc không phân biệt dấu, kết quả thực tế có thể rộng hơn giả định này.

Tương tự, các marker không có nghĩa tự gọi `trim`. Nếu kiểu cột hoặc quy tắc DB xử lý khoảng trắng theo cách riêng, cần hiểu hành vi đó thay vì gán nó cho `IgnoreCase`.

### 12.2. Quy tắc của DB có thể khác quy tắc trong Java

Không nên kiểm chứng truy vấn chỉ bằng cách chuyển chuỗi sang chữ thường trong Java rồi kết luận cơ sở dữ liệu phải so sánh như vậy. Hàm chuyển hoa/thường, collation và xử lý Unicode thuộc môi trường thực thi của query.

Với tên người, địa danh hoặc định danh đa ngôn ngữ, cần dữ liệu kiểm chứng đại diện cho ngôn ngữ sản phẩm hỗ trợ. Một vài cặp ASCII không chứng minh đầy đủ ngữ nghĩa Unicode.

### 12.3. Chính sách chuẩn hóa nên được đặt tên rõ

Nếu nghiệp vụ cần một khóa tìm kiếm hoặc khóa duy nhất theo quy tắc ổn định, có thể thiết kế một thuộc tính chuẩn hóa riêng. Ví dụ, `emailKey` biểu đạt khóa so sánh, còn `email` giữ giá trị hiển thị.

Khi đó cần xác định:

- Quy tắc chuẩn hóa và nơi áp dụng khi ghi dữ liệu.
- Cách xử lý dữ liệu cũ và thay đổi chính sách.
- Index hoặc ràng buộc bảo vệ khóa đó.
- Sự thống nhất giữa đường ghi, đường tìm kiếm và đường kiểm tra trùng.

Đây là quyết định mô hình dữ liệu. Thêm `IgnoreCase` vào một phương thức không thay thế toàn bộ chính sách ấy.

### 12.4. Truy vấn không phải ràng buộc duy nhất

`findDistinct...` không ngăn lưu dữ liệu trùng. `existsByEmailIgnoreCase` cũng không tự bảo đảm chỉ có một tài khoản cho mỗi email theo quy tắc nghiệp vụ.

Hai yêu cầu tạo dữ liệu đồng thời có thể cùng kiểm tra chưa tồn tại rồi cùng ghi. Nếu cần tính duy nhất, phải có cơ chế ràng buộc và xử lý xung đột phù hợp với kho dữ liệu, nhất quán với chính sách hoa/thường hoặc chuẩn hóa đã chọn.

## 13. Chi phí thực thi cần được kiểm tra

### 13.1. Hàm trên cột và index

Trong JPA, điều kiện có dạng `upper(column) = upper(parameter)` có thể có cách dùng index khác điều kiện so sánh trực tiếp trên cột. Index thông thường không tự bảo đảm tối ưu cho mọi biểu thức chuyển hoa/thường.

Tùy hệ quản trị, có thể cần index theo biểu thức, collation phù hợp hoặc một khóa chuẩn hóa được đánh index. Không có một cấu hình chung dùng nguyên trạng cho mọi kho dữ liệu.

Cần kiểm tra kế hoạch thực thi và dữ liệu đại diện. Không nên kết luận rằng cứ có `IgnoreCase` là query luôn chậm, hoặc thêm index bất kỳ là đã xử lý được vấn đề.

### 13.2. Distinct có thể tạo thêm công việc

Cơ sở dữ liệu có thể cần các bước thực thi để bảo đảm kết quả phân biệt. Chi phí phụ thuộc số hàng, độ rộng dữ liệu, join, index và bộ tối ưu.

Vì vậy, hãy thêm `Distinct` khi hợp đồng cần nó. Không dùng marker như một tùy chọn mặc định cho mọi phương thức để che việc chưa hiểu query.

### 13.3. Không tối ưu bằng cách làm sai hợp đồng

Nếu mục tiêu là danh sách họ phân biệt, một query scalar hoặc projection thích hợp có thể phù hợp hơn tải toàn bộ entity rồi xử lý trong bộ nhớ.

Tuy nhiên, khi chuyển cách thực thi phải giữ các điều kiện lọc, quy tắc chuẩn hóa, thứ tự và thông tin tổng mà người gọi thực sự cần. Giảm lượng dữ liệu bằng cách bỏ một yêu cầu không phải tối ưu cùng chức năng.

## 14. Bảng hành vi và các ca cần kiểm chứng

Các kết quả dưới đây dùng dữ liệu và giả định collation đã nêu; thứ tự các id chỉ để dễ đối chiếu, không phải thứ tự repository cam kết nếu không có sort.

| Phương thức và đối số | Kết quả mong đợi trong ví dụ |
| --- | --- |
| `findByFirstNameIgnoreCase("an")` | Id 1, 2, 3, 5, 6 |
| `findByFirstNameIgnoreCaseAndLastName("an", "Tran")` | Id 1, 2, 6 |
| `findByFirstNameAndLastNameAllIgnoreCase("an", "tran")` | Id 1, 2, 3, 6 |
| `findByFirstNameAndAgeAllIgnoreCase("an", 25)` | Id 1, 2, 5, 6 |
| `findDistinctByLastNameIgnoreCase("tran")` | Id 1, 2, 3, 4, 6 |
| `countByLastNameIgnoreCase("tran")` | 5 người |
| `countDistinctByLastNameIgnoreCase("tran")` | 5 định danh người phân biệt trong JPA minh họa |
| Query `select distinct p.lastName` | Tập `Tran`, `tran`, `Trần` |
| Query `select distinct lower(p.lastName)` | Tập `tran`, `trần` |
| Query `count(distinct p.lastName)` | 3 giá trị thuộc tính |

Khi triển khai trong dự án thực tế, nên kiểm chứng thêm:

- Chuỗi chỉ khác hoa thường và chuỗi có dấu theo ngôn ngữ được hỗ trợ.
- Hai entity khác id nhưng cùng tên, họ và tuổi.
- Quan hệ có thể tạo nhiều hàng join cho cùng entity.
- Thuộc tính số trong phương thức `AllIgnoreCase`.
- Đầu vào `null`, rỗng và có khoảng trắng theo hợp đồng phương thức.
- Query trả entity so với query scalar hoặc projection.
- Page dữ liệu, count và thứ tự khi nhiều giá trị bằng nhau.
- Query khai báo có tên chứa marker nhưng biểu thức chưa thực hiện ý định đó.

`AllIgnoreCase` không có nghĩa bỏ qua mọi tham số `null`. Derived query và query khai báo có thể xử lý `null` theo cách khác nhau; nếu ứng dụng không chấp nhận đầu vào ấy, cần kiểm tra rõ ở ranh giới phù hợp.

Kiểm thử chỉ gọi một mock repository không chứng minh được collation, hàm chuyển hoa/thường hoặc query count hoạt động đúng. Những đặc tính đó cần được kiểm chứng qua mô-đun và kho dữ liệu phù hợp.

## 15. Tình huống tự đánh giá

### A. Danh sách họ duy nhất

Sản phẩm muốn bộ chọn gồm các họ khác nhau. Repository hiện trả `List<Person>` từ `findDistinctByLastNameIgnoreCase` và giao diện lấy `lastName` của từng phần tử.

Giải thích vì sao vẫn có thể thấy nhiều mục giống nhau. Đề xuất hợp đồng kết quả phù hợp và nêu quyết định cần có về hoa/thường, dấu và cách viết hiển thị.

### B. Đếm người hay đếm họ?

Một báo cáo dùng `countDistinctByLastNameIgnoreCase("tran")` và kỳ vọng nhận 1 vì mọi người đều thuộc một nhóm họ sau khi bỏ qua hoa thường.

Xác định đơn vị đang được derived query JPA đếm, lý do kỳ vọng sai và cách mô tả lại yêu cầu trước khi viết query mới.

### C. Số cũng IgnoreCase

Một repository có `findByFirstNameAndAgeAllIgnoreCase`. Thành viên nhóm muốn đổi sang `findByFirstNameIgnoreCaseAndAgeIgnoreCase` để “tường minh hơn”.

Giải thích khác biệt với thuộc tính `Integer` trong JPA. Nêu cách diễn đạt đúng nếu chỉ tên cần bỏ qua hoa thường.

### D. Lọc đúng nhưng thứ tự chưa đúng

Tìm kiếm theo tên đã dùng `AllIgnoreCase`, nhưng giao diện nhận thứ tự họ không như mong đợi trong môi trường có cách sắp xếp phân biệt hoa thường.

Phân biệt hợp đồng lọc với hợp đồng sort. Nêu cách biểu đạt yêu cầu sắp xếp cùng khóa phụ và điều cần kiểm tra ở mô-đun kho dữ liệu.

### E. Tên phương thức và query khai báo mâu thuẫn

Một phương thức tên `findByLastNameIgnoreCase` có `@Query` chỉ so sánh `p.lastName = :lastName`. Nó trả kết quả khác giữa hai môi trường có collation khác nhau.

Giải thích vì sao tên không tự sửa query khai báo. Đề xuất cách làm rõ hợp đồng và dữ liệu kiểm chứng cần có trước khi sửa triển khai.