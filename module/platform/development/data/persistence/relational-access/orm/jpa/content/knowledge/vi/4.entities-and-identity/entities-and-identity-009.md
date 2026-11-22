# Xử lý entity trong Set khi khóa được sinh sau thời điểm tạo

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Entity và định danh

Một entity JPA thường được đưa vào `Set` để tránh phần tử trùng lặp, chẳng hạn danh sách sinh viên đăng ký một lớp học hoặc tập đối tượng được xử lý trong một đơn vị nghiệp vụ. Vấn đề xuất hiện khi khóa chính (`id`) **chưa có lúc tạo object** và chỉ được provider gán sau `persist`, `flush` hoặc lúc thực thi `INSERT`. Nếu `hashCode()` phụ thuộc trực tiếp vào `id`, cùng một object có thể đổi mã băm ngay sau khi đã được thêm vào `HashSet`. Khi đó `contains()` và `remove()` có thể trả kết quả sai, dù object vẫn thực sự có trong tập hợp.

Bài này giải thích nguyên nhân từ hợp đồng Java `equals()/hashCode()`, phân biệt định danh JPA với tính đồng nhất của object, rồi trình bày cách lựa chọn chiến lược equality ổn định khi entity tham gia `Set`.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích tại sao mã băm của phần tử **không nên thay đổi** khi phần tử đang ở trong `HashSet` hoặc `HashMap`.
- Phân biệt reference identity (`==`), entity identity (loại entity + khóa chính) và business identity (khóa nghiệp vụ).
- Mô tả thời điểm `@GeneratedValue` có thể gán giá trị `id` cho entity mới.
- Tái hiện lỗi `HashSet.contains(entity) == false` sau khi JPA gán ID.
- Viết `equals()` sử dụng ID khi không `null`, kết hợp `hashCode()` ổn định trong vòng đời entity.
- Chọn giữa object identity mặc định, generated ID, business key bất biến và ID do ứng dụng cấp từ đầu tùy yêu cầu.
- Nhận biết các vấn đề bổ sung với Hibernate proxy, kế thừa entity, detached entity và quan hệ dùng `Set`.
- Tránh những cách sửa sai như dùng `@Data` của Lombok cho toàn bộ entity hoặc đổi `hashCode()` theo từng trạng thái.

## 2. Kiến thức nền: Set xác định phần tử trùng nhau thế nào?

Trong Java, `Set` là một interface: tập hợp không chứa hai phần tử được xem là bằng nhau theo hợp đồng equality của phần tử. `HashSet` thường dựa vào bảng băm để tăng tốc tìm kiếm.

Giả sử:

```java
Set<String> names = new HashSet<>();
names.add("An");
names.add(new String("An"));

System.out.println(names.size()); // 1
```

Hai chuỗi là hai object riêng nhưng `equals()` trả về `true`, nên `Set` chỉ giữ một phần tử.

### 2.1. Hợp đồng `equals()` và `hashCode()`

`equals()` phải tuân thủ các tính chất quen thuộc:

- **Reflexive:** `x.equals(x)` là `true`.
- **Symmetric:** nếu `x.equals(y)` thì `y.equals(x)`.
- **Transitive:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
- **Consistent:** kết quả ổn định khi những thông tin dùng để so sánh không thay đổi.
- **Non-null:** `x.equals(null)` là `false`.

Hợp đồng giữa hai phương thức:

> Nếu `a.equals(b)` là `true`, bắt buộc `a.hashCode() == b.hashCode()`.

Chiều ngược lại **không bắt buộc**: hai object có cùng hash code vẫn có thể khác nhau.

Trong một `HashSet`, việc tra cứu sử dụng mã băm để tìm vùng lưu trữ rồi kiểm tra equality. Khi mã băm của object thay đổi sau khi object đã được thêm vào tập hợp, cấu trúc lưu trữ không tự tổ chức lại theo hash mới. Đó là nguyên nhân của lỗi khó nhìn thấy.

### 2.2. Ví dụ Java thuần: thay đổi trường tham gia hash

Ví dụ chưa cần JPA, chỉ dùng một object có ID ban đầu là `null`:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class BadKey {
    Long id;

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof BadKey)) return false;
        return Objects.equals(id, ((BadKey) other).id);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(id);
    }
}

public class Demo {
    public static void main(String[] args) {
        BadKey key = new BadKey();
        Set<BadKey> set = new HashSet<>();

        set.add(key);
        System.out.println(set.contains(key)); // true

        key.id = 42L; // Mô phỏng database/provider gán ID.
        System.out.println(set.contains(key)); // Có thể là false.
        System.out.println(set.size());         // Vẫn là 1.
    }
}
```

`BadKey` còn chứa một lỗi khác: hai object mới đều có `id == null` cũng bị xem là bằng nhau. Điều này không phù hợp với nhiều entity JPA, vì hai bản ghi chưa được tạo không tự nhiên là cùng một entity chỉ vì chưa có khóa.

## 3. Vì sao JPA làm vấn đề rõ ràng hơn?

Entity thường khai báo khóa sinh tự động:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Student {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Student() {}

    public Student(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

Khi code gọi `new Student("An")`, field `id` thường là `null`. Sau đó:

```java
Student student = new Student("An");    // id == null
students.add(student);                 // Set tính hash lần đầu

em.persist(student);                   // Entity chuyển thành managed
em.flush();                            // Có thể cần để bảo đảm INSERT hoàn tất
                                       // và generated ID đã có trong ví dụ
```

Thời điểm provider thực sự gán ID phụ thuộc chiến lược sinh khóa và implementation:

| Chiến lược / cách cấp ID | Diễn biến điển hình | Điều cần nhớ |
|---|---|---|
| `GenerationType.IDENTITY` | Database tạo khóa khi `INSERT`; provider có thể phải chạy insert sớm để lấy ID | Đừng giả định ID chỉ có sau `commit()` |
| `GenerationType.SEQUENCE` | Provider lấy giá trị sequence trước insert, có thể ngay khi `persist()` | ID có thể đã có trước khi hàng được commit |
| `GenerationType.TABLE` | Provider dùng bảng hỗ trợ sinh ID | Thời điểm lấy ID do provider và chiến lược quản lý quyết định |
| `GenerationType.UUID` / UUID do provider sinh (nếu khả dụng) | ID có thể xuất hiện trong quá trình persist | Vẫn có thể ban đầu là `null` khi vừa `new` |
| ID do ứng dụng tự cấp trong constructor | Khóa đã có ngay khi object được tạo | Chỉ an toàn cho hash nếu khóa không thay đổi sau khi thêm vào Set |

Do đó, cách dạy “ID chỉ có sau `flush`” không đúng cho mọi provider và chiến lược. Điểm chung cần xử lý là **ID có thể chuyển từ `null` sang giá trị được gán khi object đã nằm trong Set**.

### 3.1. Dòng thời gian của lỗi

```text
t0  Student s = new Student("An")
       id = null
       hashCode() = hash(null) = H0

t1  set.add(s)
       HashSet đặt s vào vùng tương ứng H0

t2  em.persist(s) / em.flush()
       provider gán id = 42
       hashCode() = hash(42) = H1

t3  set.contains(s)
       HashSet tìm trong vùng H1
       s vẫn nằm trong vùng H0
       => có thể trả false
```

Không phải `HashSet` bị hỏng, cũng không phải Hibernate “đánh mất” entity: mã của ứng dụng đã thay đổi trạng thái dùng để tính hash trong thời gian phần tử đang ở trong bảng băm.

Ngoài `contains()`, lỗi còn có thể xuất hiện ở `remove()`:

```java
boolean removed = set.remove(s); // Có thể false sau khi id đổi.
```

Về mặt API, nếu phần tử thay đổi theo cách ảnh hưởng equality trong lúc ở trong Set, hành vi của Set không còn được bảo đảm theo ý định. Không nên dựa vào việc hash mới vô tình trùng hash cũ hay việc một lần chạy vẫn thấy `contains() == true`.

## 4. Ba loại identity cần tách biệt

Trước khi viết `equals()`, hãy quyết định “hai entity bằng nhau” nghĩa là gì trong mô hình.

### 4.1. Reference identity

```java
Student a = new Student("An");
Student b = new Student("An");

System.out.println(a == b); // false
```

`a == b` chỉ đúng khi hai biến tham chiếu cùng một object Java. Mặc định `Object.equals()` cũng dùng ý nghĩa này, và `Object.hashCode()` ổn định đối với cùng object trong một lần chạy.

### 4.2. Entity identity (loại entity + ID)

```text
Student(id=42) từ EntityManager A
Student(id=42) từ EntityManager B
```

Hai object có thể là hai instance Java khác nhau nhưng cùng đại diện bản ghi `students.id = 42`. Nếu cần `Set` nhận ra chúng là một entity, equality chỉ dựa trên `==` sẽ không đủ.

Lưu ý JPA có *persistence context identity map*: trong cùng một persistence context, cùng một entity type + ID tương ứng một managed instance. Nhưng điều đó không bảo đảm cùng Java reference **qua hai persistence context**, sau `detach()` hay khi tải lại.

### 4.3. Business identity

Khóa nghiệp vụ là thông tin có ý nghĩa và ổn định đối với domain, ví dụ mã quốc gia ISO được quản trị có quy tắc hoặc mã định danh bất biến được cấp ngay khi tạo object.

```text
Product(code = "SKU-1001")
```

Nếu business key vừa **bất biến**, vừa **duy nhất**, bạn có thể dùng nó cho `equals()/hashCode()`. Nhưng field như `name`, `email`, `price` hoặc `status` thường có thể thay đổi hoặc có điều kiện unique phức tạp. Dùng các field ấy làm hash key rồi sửa giá trị khi object ở trong Set sẽ tạo lại cùng một loại lỗi.

**Một database surrogate key** (ID tự tăng) và **một khóa nghiệp vụ** (SKU) giải quyết hai nhu cầu khác nhau; không nhất thiết chúng phải cùng tham gia equality.

## 5. Cách sai phổ biến: hashCode dựa trực tiếp vào ID phát sinh muộn

Xét implementation dễ gặp:

```java
@Entity
public class Student {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // ... constructor, getter ...

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Student)) return false;
        Student that = (Student) other;
        return id != null && id.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(id); // Có vấn đề.
    }
}
```

`equals()` đã xử lý hai transient entity đúng hơn bằng cách chỉ so sánh ID khi ID khác `null`, nhưng `hashCode()` vẫn thay đổi ngay khi JPA gán ID:

```text
new Student       -> id=null -> hash=0
managed Student   -> id=42   -> hash=42
```

Vì vậy **chỉ sửa `equals()` chưa đủ**. Cần xem cả mã băm trong toàn bộ vòng đời của entity.

### 5.1. Một bẫy khác: null bằng null

Đoạn này còn nguy hiểm hơn:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Student)) return false;
    Student that = (Student) other;
    return java.util.Objects.equals(id, that.getId());
}
```

Hai entity mới có `id == null` đều được xem là bằng nhau:

```java
Student an = new Student("An");
Student binh = new Student("Binh");

Set<Student> students = new HashSet<>();
students.add(an);
students.add(binh);

System.out.println(students.size()); // Có thể chỉ còn 1!
```

Với chiến lược equality dựa trên database ID, hai object transient khác nhau **không được xem là bằng nhau chỉ vì cùng chưa có ID**.

## 6. Giải pháp thông dụng: equals theo ID đã có, hashCode ổn định

Với entity có database-generated ID và yêu cầu so sánh cùng identity qua persistence context, một mẫu thường dùng là:

1. Nếu cùng tham chiếu thì bằng nhau.
2. Nếu khác loại entity thì không bằng nhau.
3. Nếu ID chưa được gán thì hai object khác tham chiếu không bằng nhau.
4. Khi ID đã có, so sánh hai ID.
5. `hashCode()` luôn trả về một giá trị ổn định theo loại entity, **không phụ thuộc ID**.

Ví dụ entity `Student` độc lập, không có phân cấp kế thừa JPA:

```java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "students")
public class Student {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false)
    private String name;

    protected Student() {
        // JPA cần constructor không tham số.
    }

    public Student(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String name) {
        this.name = name;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }

        if (!(other instanceof Student)) {
            return false;
        }

        Student that = (Student) other;
        return getId() != null && getId().equals(that.getId());
    }

    @Override
    public int hashCode() {
        return Student.class.hashCode();
    }
}
```

Trong mẫu trên, hai instance của `Student` có cùng non-null ID được xem là bằng nhau. `hashCode()` lấy mã băm của **literal class cố định**, không lấy `getClass()` của object tại runtime, nên không thay đổi khi object chuyển trạng thái mới → managed → detached.

Với JPA/Hibernate proxy và mô hình kế thừa phức tạp, định nghĩa "cùng loại entity" phải được cân nhắc kỹ hơn (xem phần 10). Mẫu ở đây phù hợp làm điểm khởi đầu cho một entity type độc lập như `Student`.

### 6.1. Vì sao cách này không vi phạm hợp đồng hash?

Giả sử:

```java
Student first = ...;  // id=42
Student second = ...; // id=42, instance khác
```

Vì `first.equals(second) == true` và cả hai cùng trả `Student.class.hashCode()`, điều kiện “bằng nhau phải cùng hash” được bảo đảm.

Ngược lại:

```java
Student first = ...;  // id=42
Student other = ...;  // id=99
```

Hai entity có cùng hash vẫn hợp lệ vì `equals()` phân biệt chúng. `HashSet` kiểm tra equality trong vùng hash nên vẫn lưu được cả hai.

### 6.2. Lúc ID đổi thì chuyện gì xảy ra?

```text
Trước persist:
  id=null
  equals(other transient)=false
  hashCode()=Student.class.hashCode()

Sau persist / ID được cấp:
  id=42
  equals(other có id=42)=true
  hashCode()=Student.class.hashCode()
```

Hash không thay đổi. Tập hợp vẫn tìm được object đang nằm trong vùng hash cũ vì vùng đó cũng chính là vùng hash mới.

Cần phân biệt hai loại ổn định:

- **Hash ổn định:** đạt được với hash theo class cố định.
- **Quan hệ equals ổn định tuyệt đối:** không thể bảo đảm với mọi tình huống nếu ID thay từ null sang giá trị, hoặc nếu hai entity khác nhau bị gán nhầm cùng ID.

Mẫu này giải quyết vấn đề thay đổi **hash bucket** khi generated ID xuất hiện. Khi một entity bắt đầu có ID, nó cũng có thể trở nên bằng với một entity khác đã có cùng ID; vì vậy vẫn không nên để hai đại diện của cùng bản ghi cùng sống độc lập trong một Set theo cách khó kiểm soát. Tốt nhất là quản lý thực thể nhất quán và tránh sửa ID thủ công.

### 6.3. Không sử dụng hash theo `getId()` chỉ sau khi có khóa

Cách sau trông có vẻ hợp lý nhưng không giải quyết lỗi:

```java
@Override
public int hashCode() {
    return id == null ? 31 : id.hashCode();
}
```

Giá trị vẫn đổi từ `31` thành một mã băm khác sau khi ID được sinh. Bất kỳ cấu trúc băm nào đang giữ entity đều có thể bị ảnh hưởng. Hash phải ổn định **từ trước khi thêm vào Set** cho tới khi loại bỏ khỏi Set.

## 7. Thí nghiệm thực tế với EntityManager và HashSet

Để quan sát, tạo persistence unit tên `studentsPU` dùng `RESOURCE_LOCAL`, Hibernate/JPA provider tương thích và bảng `students`. Có thể dùng H2 in-memory trong bài thực hành. Tên và mapping class `Student` sử dụng phiên bản từ phần 6.

```java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

import java.util.HashSet;
import java.util.Set;

public class StudentSetDemo {

    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("studentsPU");

        try {
            EntityManager em = emf.createEntityManager();

            try {
                EntityTransaction tx = em.getTransaction();
                tx.begin();

                try {
                    Student student = new Student("An");
                    Set<Student> students = new HashSet<>();

                    students.add(student);

                    System.out.println("Before persist:");
                    System.out.println("id = " + student.getId());
                    System.out.println("contains = " + students.contains(student));

                    em.persist(student);
                    em.flush();

                    System.out.println("After ID generation:");
                    System.out.println("id = " + student.getId());
                    System.out.println("contains = " + students.contains(student));
                    System.out.println("size = " + students.size());

                    tx.commit();

                    System.out.println("After commit:");
                    System.out.println("contains = " + students.contains(student));
                } catch (RuntimeException failure) {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                    throw failure;
                }
            } finally {
                em.close();
            }
        } finally {
            emf.close();
        }
    }
}
```

Kỳ vọng với mẫu `hashCode()` cố định: `contains(student)` vẫn là `true` trước và sau khi sinh khóa. Thời điểm ID xuất hiện có thể sớm hơn lời gọi `flush()` vì `IDENTITY` đôi khi cần insert ngay khi persist.

`EntityManager` được tạo/đóng trong `try/finally` và transaction được kết thúc bằng commit hoặc rollback. Tách chuyện **đóng context** khỏi chuyện **ổn định hash**: dù entity detached sau `em.close()`, tập hợp Java vẫn có thể giữ tham chiếu của nó.

> **Lưu ý thực hành:** `persistence.xml` phải khai báo đúng `studentsPU` và entity `demo.Student`, đồng thời project cần thư viện JPA provider và JDBC driver phù hợp. Đây là ví dụ thao tác EntityManager thuần, không phải mã quản lý transaction dành cho Spring `@Transactional`.

### 7.1. So sánh khi dùng phiên bản hashCode sai

Nếu tạm thay `Student.hashCode()` bằng:

```java
@Override
public int hashCode() {
    return java.util.Objects.hashCode(getId());
}
```

Và lại chạy chương trình theo thứ tự **thêm vào Set trước khi JPA cấp ID**, kết quả `contains` sau gán ID có thể thay đổi. Tác động phụ thuộc bucket, nhưng đây đã là một vi phạm điều kiện an toàn để dùng object mutable trong `HashSet`.

Không nên sửa Set bằng cách xóa rồi thêm lại khi provider gán ID, vì nhiều đường đi (persist/flush, cascade, association) có thể làm việc đổi khóa khó theo dõi. Chọn hash ổn định hoặc thay đổi chiến lược lưu object sẽ đáng tin cậy hơn.

## 8. Hai entity mới có cùng dữ liệu: Set nên xử lý thế nào?

Cho hai sinh viên chưa có ID:

```java
Student an1 = new Student("An");
Student an2 = new Student("An");

Set<Student> students = new HashSet<>();

students.add(an1);
students.add(an2);

System.out.println(students.size()); // 2
```

Với equality theo generated ID, chúng là **hai entity mới độc lập**. Cùng tên không chứng minh cùng một thực thể nghiệp vụ. Khi được persist, chúng có thể nhận hai ID khác nhau và tồn tại dưới dạng hai hàng, trừ khi database có ràng buộc nghiệp vụ ngăn điều đó.

`Set` không thay thế cho `UNIQUE` constraint trong database. Nếu không cho phép hai sinh viên cùng mã trường hoặc hai sản phẩm cùng SKU, phải biểu diễn quy tắc đó rõ ràng bằng khóa nghiệp vụ, validation và constraint phù hợp.

### 8.1. Nếu cần khử trùng lặp ngay từ trước khi persist

Có ba hướng cần cân nhắc:

1. Có **business key bất biến** được cấp sẵn và bảo đảm duy nhất: equality theo business key có thể phù hợp.
2. Dùng **ID bất biến do ứng dụng cấp ngay khi tạo** (chẳng hạn UUID) nếu thiết kế cho phép: có thể tính hash từ ID ổn định đó.
3. Nếu nhu cầu chỉ là loại trùng trong một thao tác import theo cột nghiệp vụ, xây một `Set<String>` hoặc `Map<String, DTO>` chứa khóa import, thay vì ép equals của mọi entity theo dữ liệu mutable.

Không nên biến `name` thành identity chỉ để đạt `Set.size() == 1` nếu cùng tên là một trường hợp hợp lệ.

## 9. Chọn chiến lược equals/hashCode theo yêu cầu ứng dụng

Không tồn tại một implementation duy nhất tối ưu cho mọi domain. Đầu tiên cần hỏi: **tập hợp này cần coi hai entity ở hai persistence context là một phần tử không?**; **entity có khóa ổn định ngay khi new không?**

| Chiến lược | Cách hoạt động | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|---|
| **Mặc định `Object.equals/hashCode`** | Bằng nhau khi cùng Java reference | Hash ổn định; đơn giản; tránh nhầm transient entity | Detached entity và bản được tải lại ở context khác không bằng nhau |
| **ID sinh bởi database + hash theo ID** | Hash phụ thuộc `@GeneratedValue` | Phân bố hash tốt khi ID ổn định | Sai khi đã thêm vào Set trước khi ID được gán |
| **ID sinh bởi database + hash cố định theo entity type** | Equals theo ID khác null; hash không đổi | Hỗ trợ cùng ID qua context và giữ ổn định khi persist | Nhiều object chung một bucket; xử lý proxy/kế thừa cần chủ ý |
| **Business key bất biến** | Equals/hash theo mã nghiệp vụ ổn định từ lúc new | Có thể khử trùng lặp transient entity theo nghiệp vụ | Khóa phải thực sự immutable và duy nhất; phải thiết kế rõ |
| **ID do ứng dụng gán ngay từ đầu** | UUID/canonical ID xuất hiện khi tạo object | Có định danh ổn định trước persist | Cần thiết kế ID và cách database/provider ánh xạ phù hợp |

### 9.1. Lựa chọn A: Giữ equality mặc định

Nếu ứng dụng chỉ cần tập hợp quản lý **đúng các object Java đang giữ**, không trộn entity detached với entity được load lại, bạn có thể không override `equals()` và `hashCode()`:

```java
@Entity
public class Enrollment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Không override equals()/hashCode().
}
```

Đây không mặc nhiên là sai. Nhưng với domain cần so sánh entity cùng ID qua nhiều persistence context, mặc định có thể gây phần tử trùng về mặt database trong Set.

### 9.2. Lựa chọn B: Business key bất biến

Giả sử entity `Country` có mã ISO cố định, được cấp trước khi persist và **không thể sửa sau khi tạo**:

```java
@Entity
public class Country {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "iso_code", nullable = false,
            unique = true, updatable = false, length = 2)
    private String isoCode;

    protected Country() {}

    public Country(String isoCode) {
        this.isoCode = java.util.Objects.requireNonNull(isoCode);
    }

    public String getIsoCode() {
        return isoCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Country)) return false;
        Country that = (Country) other;
        return isoCode.equals(that.getIsoCode());
    }

    @Override
    public int hashCode() {
        return isoCode.hashCode();
    }
}
```

Ví dụ mang tính khái niệm: ứng dụng cần quy định mã luôn chuẩn hóa (ví dụ uppercase), tồn tại ngay sau khi tạo và không thể đổi; constructor không tham số dành cho JPA có thể khiến field chưa khởi tạo ở giai đoạn nội bộ của provider. Trong hệ thống thật, cần thiết kế validation và bất biến ở mức nghiệp vụ, không chỉ trông vào `updatable = false`.

Nếu người dùng có thể đổi mã hoặc nếu business key được xác định sau khi entity đã ở trong Set, chiến lược này lại gặp đúng lỗi mutable hash.

### 9.3. Lựa chọn C: ID được cấp tại thời điểm tạo

Nếu ID là UUID do ứng dụng tạo ngay khi new, có thể sử dụng ID ổn định trong `hashCode()`:

```java
@Entity
public class Document {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private java.util.UUID id;

    protected Document() {
        // Dành cho JPA.
    }

    public Document(String title) {
        this.id = java.util.UUID.randomUUID();
        this.title = title;
    }

    @Column(nullable = false)
    private String title;

    public java.util.UUID getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Document)) return false;
        Document that = (Document) other;
        return id != null && id.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return id == null ? Document.class.hashCode() : id.hashCode();
    }
}
```

Lưu ý ví dụ chỉ an toàn theo tiền đề **mọi object nghiệp vụ được đưa vào Set đều đã có UUID và không bao giờ sửa ID**. Trong vòng đời khởi tạo của JPA, `id` có thể tạm thời là `null` ở một số thời điểm. Nếu có luồng dùng object khi ID còn null, hash vẫn có thể thay đổi; phải thiết kế tránh điều đó. `@GeneratedValue` không xuất hiện ở đây vì ID do ứng dụng cấp.

## 10. Hibernate proxy và entity inheritance: đừng bỏ qua loại thực thể

Hibernate thường dùng proxy hoặc kỹ thuật tăng cường bytecode để trì hoãn tải dữ liệu. Một proxy có thể là object thuộc subclass sinh ra lúc chạy:

```java
Student student = em.find(Student.class, id);
Student reference = em.getReference(Student.class, id);
```

Nếu implement:

```java
if (getClass() != other.getClass()) {
    return false;
}
```

thì một object `Student` và proxy của `Student` có thể có runtime class khác, dù cùng bản ghi. Phương án dùng `instanceof Student` trong ví dụ phần 6 tránh sự khác biệt subclass thông thường đối với một entity type độc lập.

Tuy nhiên, `instanceof` cũng có điểm cần cân nhắc nếu mô hình kế thừa JPA:

```text
Person (entity cha)
  |
  +-- Student (entity con)
  |
  +-- Teacher (entity con)
```

Nếu hai entity subclass cùng dùng ID theo một phân cấp có chung identity, bạn phải định nghĩa ý nghĩa equality theo **persistent entity type**, không chỉ dựa vào class Java hoặc khóa số. Ngược lại, nếu các entity type độc lập có ID bằng nhau, chúng không được tự động xem là cùng bản ghi.

### 10.1. Tránh lựa chọn class runtime một cách thiếu nhất quán

Ví dụ có thể sai:

```java
@Override
public int hashCode() {
    return getClass().hashCode();
}
```

Với proxy subclass, mã băm runtime có thể khác với entity thật. Dù ID trùng nhau, nếu `equals()` cho rằng chúng bằng nhau mà hash khác, hợp đồng `equals/hashCode` bị vi phạm.

Một số implementation dựa trên Hibernate dùng API provider như `Hibernate.getClass(entity)` hoặc kiểm tra `HibernateProxy` để xác định persistent class. Cách đó có thể phụ thuộc phiên bản Hibernate, trạng thái proxy và có thể tác động đến khởi tạo lazy. Khi cần hỗ trợ proxy và hierarchy phức tạp, hãy chọn implementation phù hợp với **provider/phiên bản đang dùng** và xác định rõ loại entity được phép so sánh.

Mẫu `Student.class.hashCode()` của phần 6 cố tình dùng class literal cố định, nên **không bị đổi theo proxy subclass**. Với entity có inheritance, cần một chính sách equality nhất quán xuyên suốt hierarchy; không sao chép máy móc từ một entity con sang entity cha khi chúng có quan hệ kế thừa.

### 10.2. Hạn chế truy cập trường của proxy trực tiếp

Trong `equals()`, sử dụng `that.getId()` thường dễ tương thích với proxy hơn đọc trực tiếp `that.id`. Trong nhiều provider và cấu hình, ID của proxy có thể được truy cập mà không cần tải toàn bộ entity, nhưng không nên coi hành vi tối ưu đó là bảo đảm cho mọi provider.

Tuyệt đối tránh lôi kéo association lazy vào `equals()` hoặc `hashCode()`:

```java
// Không nên xây equality kiểu này:
return java.util.Objects.equals(name, that.name)
    && java.util.Objects.equals(orders, that.orders);
```

Việc đó có thể làm chạy thêm SQL, gặp lỗi do context đã đóng hoặc gây đệ quy với quan hệ hai chiều. Equality của entity cần dựa trên **identity được chọn**, không phải toàn bộ graph.

## 11. Set trong association JPA: vì sao lỗi lan ra ứng dụng?

Entity có thể là phần tử của `Set` thuần Java hoặc collection association do JPA provider quản lý:

```java
@Entity
public class Course {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    private Set<Student> students = new HashSet<>();

    // ...
}
```

Khi thêm `Student` vào `course.students` **trước khi Student được cấp ID**, việc dùng hash theo ID có thể khiến:

- `course.getStudents().contains(student)` trả kết quả bất ngờ sau persist.
- `course.getStudents().remove(student)` thất bại dù sinh viên đang có trong collection.
- Logic thêm/xóa thành viên ở tầng domain hành xử sai; kết quả đồng bộ quan hệ xuống database có thể khó dự đoán.
- Snapshot và dirty checking collection do provider quản lý trở nên khó kiểm soát khi equality/hash của phần tử thay đổi.

Ví dụ:

```java
Student student = new Student("An");
Course course = new Course();

course.addStudent(student); // Nội bộ sử dụng Set<Student>.

// Trong một transaction phù hợp, khi Student được persist
// và ID đổi từ null -> có giá trị:
em.persist(student);

// Với hash code thay đổi, thao tác sau có thể không tìm được:
course.removeStudent(student);
```

`Course` trong đoạn này là một ví dụ giả định có constructor và hai phương thức `addStudent/removeStudent` bọc `Set`, không phải class hoàn chỉnh có thể chạy ngay. Việc persist quan hệ còn phụ thuộc **owning side, cascade và transaction**. Hash ổn định giải quyết tính đúng đắn của Set, nhưng **không tự động ghi association** hay thay thế ràng buộc khóa ngoại/bảng nối.

### 11.1. Đừng nhầm “Set ngăn trùng” với “database không có bản ghi trùng”

`HashSet` chống trùng theo `equals()` của object đang ở trong collection. Database chống trùng theo khóa chính, unique constraint và quy tắc quan hệ:

| Tình huống | Điều gì quyết định chống trùng? |
|---|---|
| Thêm cùng Java reference hai lần vào HashSet | Set và equality |
| Thêm hai detached entity cùng database ID | Chiến lược `equals()/hashCode()` |
| Tạo hai entity mới có cùng tên | Business validation và unique constraint nếu domain yêu cầu |
| Ghi hai hàng vào bảng liên kết quan hệ | Constraint/PK/unique trên join table và mapping |
| Nhiều transaction cùng tạo bản ghi cùng business key | Constraint database và xử lý lỗi giao dịch |

Không nên dựa vào Set để thay thế constraint database trong hệ thống có truy cập đồng thời.

### 11.2. Một kỹ thuật thực dụng: tập khóa thay vì tập entity

Trong một số use case chỉ cần nhận biết ID đã xử lý, dữ liệu có thể được lưu bằng:

```java
Set<Long> processedStudentIds = new HashSet<>();
```

Tập ID không gặp vấn đề entity proxy/lifecycle, **miễn là ID đã tồn tại và bất biến khi thêm vào Set**. Khi entity còn transient và ID chưa có, không thể dùng mã `null` như một định danh duy nhất; lúc này cần một business key ổn định hoặc khóa tạm riêng cho quá trình xử lý.

Đây là lựa chọn tốt cho logic batch, deduplication, hoặc kiểm tra thuộc một nhóm nếu hệ thống chỉ cần identity, không cần giữ managed entity.

## 12. Vì sao không nên dùng `@Data` để sinh equals/hashCode cho entity?

Lombok `@Data` thường sinh `equals()`, `hashCode()` và `toString()` dựa trên các field của class. Với entity, điều này có thể đưa các trường không phù hợp vào identity:

```java
// Cần cân nhắc rất kỹ; ví dụ không khuyến nghị:
@Data
@Entity
public class Student {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @OneToMany(mappedBy = "student")
    private Set<Enrollment> enrollments;
}
```

Các nguy cơ:

1. `id` sinh muộn làm hash thay đổi.
2. `name` thay đổi trong nghiệp vụ cũng làm hash thay đổi.
3. `enrollments` có thể khiến hash/equality tải dữ liệu lazy, tốn truy vấn hoặc gặp lỗi ngoài persistence context.
4. Quan hệ hai chiều có thể khiến `toString()/equals()/hashCode()` đệ quy.
5. Hai transient entity có các giá trị field giống nhau có thể bị coi là cùng một entity dù chưa có database identity.

Nếu dùng Lombok, cân nhắc chỉ dùng các annotation hỗ trợ getter/setter/constructor cần thiết, và chủ động viết `equals()/hashCode()` theo chính sách identity. Không suy luận rằng `@EqualsAndHashCode(onlyExplicitlyIncluded = true)` tự động giải quyết vấn đề khi include field `id` mutable; cách tính hash vẫn phải được xem xét.

## 13. Hiệu năng: hashCode cố định có làm HashSet chậm?

Vì mọi `Student` cùng trả `Student.class.hashCode()`, tất cả cùng đi vào một nhóm hash. `HashSet` vẫn đúng về mặt ngữ nghĩa, nhưng tra cứu có thể tốn thời gian hơn so với hash phân bố tốt, nhất là khi Set chứa rất nhiều phần tử.

Cần nhìn bài toán thực tế:

- Nếu mỗi Set chỉ có vài chục hoặc vài trăm entity, ưu tiên correctness thường hợp lý.
- Nếu một Set rất lớn, hàng trăm nghìn entity, hash cố định có thể trở thành nút thắt; nên đo hiệu năng và cân nhắc thiết kế dữ liệu khác.
- Trong một persistence context, số managed entity quá lớn cũng gây áp lực bộ nhớ và dirty checking; không nên coi Set khổng lồ là lựa chọn mặc định.
- Nếu ứng dụng có **immutable business key** hoặc **immutable ID được cấp trước khi đưa vào Set**, hash theo khóa đó vừa ổn định vừa phân bố tốt.

Trên các phiên bản Java hiện đại, `HashMap` có cơ chế xử lý va chạm phức tạp hơn một danh sách liên kết đơn giản ở một số điều kiện, nhưng không nên dựa vào nó để bảo đảm hiệu năng khi mọi phần tử cố ý có cùng mã băm.

Điểm cần giữ: **đúng về hợp đồng equality trước**, sau đó lựa chọn data structure, scope và khóa phù hợp với kích thước dữ liệu.

## 14. Kiểm thử hành vi quan trọng

Một entity có generated ID và dùng trong Set nên được kiểm tra bằng những kịch bản phản ánh vòng đời thật. Không chỉ kiểm tra khi đã có ID.

### 14.1. Hai entity mới phải độc lập

```java
@Test
void twoTransientStudentsRemainDistinct() {
    Student a = new Student("An");
    Student b = new Student("An");

    Set<Student> set = new HashSet<>();
    set.add(a);
    set.add(b);

    assertEquals(2, set.size());
}
```

### 14.2. Cùng object phải còn trong Set sau khi ID được gán

```java
@Test
void generatedIdMustNotBreakSetLookup() {
    Student student = new Student("An");
    Set<Student> set = new HashSet<>();
    set.add(student);

    EntityTransaction tx = em.getTransaction();
    tx.begin();
    try {
        em.persist(student);
        em.flush();

        assertNotNull(student.getId());
        assertTrue(set.contains(student));
        assertTrue(set.remove(student));
        assertTrue(set.isEmpty());

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) tx.rollback();
        throw ex;
    }
}
```

`em` ở đây là EntityManager resource-local được fixture tích hợp tạo và đóng đúng vòng đời. `@Test` và `assert...` giả sử dự án có JUnit. Kịch bản này có giá trị hơn một unit test chỉ tự gán ID bằng reflection, vì có bước sinh khóa thực tế từ provider/database.

### 14.3. Detached và managed instance cùng ID

```java
Student detached = ...; // Lấy từ context A đã đóng.
Student managed = em.find(Student.class, detached.getId());

assertNotSame(detached, managed);
assertEquals(detached, managed);
assertEquals(detached.hashCode(), managed.hashCode());
```

Để phép so sánh phản ánh hai object khác nhau, fixture cần chắc chắn entity `detached` đã ra khỏi context A, còn `managed` được lấy qua context B. Không giả định `assertNotSame` luôn đúng nếu lấy cả hai trong cùng persistence context.

### 14.4. Đổi field nghiệp vụ không làm đổi hash

```java
Student student = new Student("An");
int before = student.hashCode();

student.rename("An Nguyen");

assertEquals(before, student.hashCode());
```

### 14.5. Kiểm thử proxy và kế thừa nếu ứng dụng có dùng

Nếu provider tạo proxy, kiểm tra equality đối xứng giữa entity thật và một reference cùng ID, đồng thời kiểm tra hash giống nhau. Nếu entity có hierarchy, thêm trường hợp subclass khác nhau và ID trùng nhau theo cách provider lưu identity. Định nghĩa kỳ vọng trước khi viết `equals()` cho hierarchy để tránh kết quả bất đối xứng.

**Đây là các kịch bản kiểm tra được đề xuất cho bài học**, không phải lời khẳng định đã chạy test trong một project cụ thể.

## 15. Câu hỏi tình huống thường gặp

### “Tại sao Set.size() vẫn bằng 1 nhưng contains() lại false?”

`HashSet` vẫn giữ một entry. Khi field tham gia `hashCode()` thay đổi, vị trí lưu entry không tự cập nhật. `size()` đếm số phần tử đang lưu; `contains()` tra cứu theo hash hiện tại nên có thể không tìm thấy entry ở bucket cũ.

### “Nếu thêm entity vào Set sau khi persist thì có hết lỗi không?”

Nếu chắc chắn ID đã được cấp và không bao giờ thay đổi nữa, hash theo ID có thể ổn định trong khoảng thời gian entity nằm trong Set. Tuy nhiên, cascade persist, workflow tạo graph mới và thao tác trên transient entity rất dễ khiến quy tắc “chỉ thêm sau khi có ID” bị vi phạm. Thiết kế phải phù hợp với toàn bộ các đường đi thực tế.

### “Có nên set id thủ công ngay sau new để hash không đổi?”

Không tùy tiện tự gán ID cho entity dùng `@GeneratedValue` rồi giả định provider sẽ chấp nhận. Nếu chọn ID do ứng dụng quản lý, phải thiết kế mapping và cơ chế tạo khóa tương ứng ngay từ đầu, rồi bảo đảm ID bất biến.

### “Có thể dùng Objects.hash(id) nếu equals chỉ so ID không null?”

Vẫn có lỗi đổi hash khi ID từ null thành non-null. Hợp đồng `equals()` đúng không bảo đảm cấu trúc `HashSet` hoạt động đúng nếu hash của phần tử đang lưu bị thay đổi.

### “Có phải tất cả entity JPA đều bắt buộc override equals/hashCode?”

Không. Nếu yêu cầu chỉ là nhận biết cùng Java object trong một persistence context, mặc định `Object.equals/hashCode` có thể đủ. Cần override khi domain và collection thực sự yêu cầu cùng database identity được nhận diện qua các context hoặc khi dùng khóa nghiệp vụ ổn định. Một implementation sai còn nguy hiểm hơn không override.

### “HashCode theo class có làm hai entity có cùng ID nhưng khác bảng bằng nhau?”

Không nếu `equals()` kiểm tra đúng loại entity. Mã băm trùng **không khiến hai object bằng nhau**; `HashSet` vẫn dùng `equals()` để phân biệt. Với hierarchy hoặc proxy, định nghĩa loại entity phải nhất quán.

### “Dùng List thay Set có tránh được không?”

`ArrayList` không dùng hash bucket, nên không gặp riêng lỗi phần tử “lạc bucket” khi hash thay đổi. Nhưng `List.contains` và `List.remove(Object)` vẫn dùng `equals()`, có thể bị ảnh hưởng nếu equality thay đổi; ngoài ra `List` cho phép phần tử trùng. Đổi sang List chỉ phù hợp nếu đúng ngữ nghĩa domain, không phải cách thay thế cho chính sách identity được xác định cẩn thận.

### “Đóng EntityManager có làm hashCode thay đổi không?”

Với mã `Student.hashCode()` cố định, không. Đóng context thường khiến entity managed thành detached, nhưng object Java và ID đã có vẫn tồn tại. Nếu tự viết hash dựa trên association/proxy bị tải lazy, có thể phát sinh lỗi ngoài context; đó là lý do nên giữ equality độc lập với graph.

## 16. Bài thực hành tổng hợp

Hãy xây một màn hình “ghi danh sinh viên vào lớp” với:

- `Student`: ID sinh tự động, tên có thể sửa.
- `Course`: ID sinh tự động, có danh sách sinh viên.
- Service có thao tác thêm sinh viên mới vào `Set<Student>` trước khi JPA lưu.
- Một use case khác tải lại sinh viên bằng EntityManager mới rồi thử kiểm tra membership.
- Cơ sở dữ liệu có bảng liên kết khóa ngoại phù hợp nếu dùng quan hệ many-to-many.

Thực hiện theo thứ tự:

1. Viết phiên bản `Student.hashCode()` tính từ generated ID. Quan sát `contains`/`remove` khi gọi persist.
2. Thay bằng implementation ổn định ở phần 6. Giữ nguyên workflow và quan sát lại.
3. Thêm hai `Student` mới có cùng tên; giải thích tại sao `Set` vẫn chứa cả hai.
4. Tải một `Student` từ persistence context khác; giải thích khi nào hai instance được xem là bằng nhau.
5. Đổi tên một `Student` đã nằm trong Set; kiểm tra thao tác lookup và remove.
6. Bổ sung một unique business key giả định và quyết định có nên chuyển equality sang key đó không.
7. Viết ghi chú ngắn phân biệt sự bất biến của hash key với tính bất biến của dữ liệu nghiệp vụ.
8. Xác định khóa ngoại/bảng nối, cascade và transaction độc lập với bài toán Set.

Khi quan sát SQL, nhớ rằng JPA có thể thực hiện `INSERT` trước `commit` để cấp ID. Vì vậy ghi lại **thời điểm ID từ null chuyển thành non-null**, đồng thời so sánh hash của cùng object trước và sau mốc đó.

## 17. Những nguyên tắc cần ghi nhớ

| Tình huống | Hành động phù hợp |
|---|---|
| Entity có generated ID, được thêm vào HashSet trước khi persist | Không tính hash từ field ID sẽ thay đổi |
| Hai transient entity cùng `id == null` | Không mặc nhiên coi chúng bằng nhau |
| Cần nhận diện cùng entity qua context | Cân nhắc equals theo ID đã có và hash ổn định |
| Không cần equality theo database ID | Có thể giữ Object equality mặc định |
| Có business key bất biến và duy nhất | Có thể dùng equality/hash theo business key |
| Có ID do ứng dụng cấp ngay khi tạo | Có thể hash theo ID nếu tuyệt đối không sửa khóa khi nằm trong Set |
| Có Hibernate proxy hoặc inheritance | Xác định nhất quán persistent entity type; tránh hash runtime class tùy ý |
| Entity có collection quan hệ | Tránh đưa association mutable/lazy vào equals/hashCode |
| Dùng Lombok cho entity | Không dùng `@Data` như giải pháp mặc định cho equality |
| Tập rất lớn và hash cố định | Cân nhắc khóa bất biến khác, Set khóa thuần hoặc cấu trúc phù hợp và đo hiệu năng |

**Ý chính:** Với entity JPA có khóa chính phát sinh sau thời điểm tạo, *identity của entity có thể ổn định về mặt database sau khi persist, nhưng hash code của object phải được thiết kế ổn định ngay từ lúc object bắt đầu tham gia Set*. Nếu muốn so sánh entity bằng generated ID, dùng so sánh ID khác `null` kết hợp hash không phụ thuộc ID là một lựa chọn phổ biến; nếu bài toán yêu cầu khác, hãy chọn reference identity hoặc một khóa bất biến được cấp sẵn, rồi áp dụng thống nhất trong mọi vòng đời entity.

