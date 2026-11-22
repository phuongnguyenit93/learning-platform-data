# Duy trì thứ tự bằng `@OrderBy` và `@OrderColumn`

Trong Spring Data JPA, một quan hệ tập hợp có thể chứa nhiều phần tử nhưng **thứ tự đọc lại từ cơ sở dữ liệu không tự nhiên được bảo đảm**. Chỉ khai báo `List<T>` chưa đủ để nói với JPA rằng vị trí phần tử phải được lưu bền vững. Hai annotation chuẩn Jakarta Persistence giải quyết hai nhu cầu khác nhau:

- **`@OrderBy`:** mỗi lần nạp tập hợp, sắp xếp theo **giá trị thuộc tính đã lưu của phần tử** (chẳng hạn `priority`, `createdAt`, `name`). Ứng dụng chịu trách nhiệm thay đổi các thuộc tính tạo nên thứ tự.
- **`@OrderColumn`:** lưu **vị trí của phần tử trong một `List`** vào cột chỉ số riêng. Persistence provider theo dõi việc thêm, xóa, đổi chỗ và cập nhật chỉ số khi đồng bộ xuống database.

Bài này tập trung vào hai annotation trong các quan hệ `@OneToMany`, `@ManyToMany` và `@ElementCollection`; ví dụ dùng Java 17+, Spring Data JPA theo hệ `jakarta.persistence`.

## 1. Vì sao thứ tự của collection cần được khai báo?

Giả sử một phòng ban có ba nhân viên và mã Java dùng `List<Employee>`. Lần đầu thêm vào danh sách theo thứ tự “Bình, An, Chi” không có nghĩa lần truy vấn sau database sẽ trả về đúng thứ tự ấy. Trong SQL, thứ tự kết quả chỉ được xác định khi có quy tắc sắp xếp phù hợp; thứ tự vật lý, khóa chính, hoặc thứ tự insert không phải hợp đồng ứng dụng.

Có hai cách định nghĩa yêu cầu nghiệp vụ:

1. **Thứ tự suy ra từ dữ liệu:** “Nhân viên có `priority` nhỏ hơn xuất hiện trước; nếu bằng nhau thì theo `id`.” Đây là trường hợp của `@OrderBy`. Khi đổi `priority`, vị trí hiển thị có thể đổi khi tải lại collection.
2. **Thứ tự do người dùng sắp đặt:** “Trong playlist, bài hát thứ ba được kéo lên đầu, dù tiêu đề không thay đổi.” Đây là trường hợp của `@OrderColumn`. Database cần nhớ vị trí 0, 1, 2… của từng phần tử trong *collection đó*.

Lưu ý: `@OrderBy` không phải annotation Spring Data riêng và cũng không phải phương thức `findAll(Sort)` của repository. Cả `@OrderBy` lẫn `@OrderColumn` ở đây thuộc package `jakarta.persistence`.

## 2. So sánh trước khi chọn

| Tiêu chí | `@OrderBy` | `@OrderColumn` |
| --- | --- | --- |
| Nguồn tạo thứ tự | Thuộc tính đã được ánh xạ của phần tử | Cột vị trí riêng của collection |
| Cột vị trí mới | Không cần | Có, ví dụ `track_position` |
| Ai cập nhật thứ tự? | Ứng dụng cập nhật thuộc tính như `priority` | JPA provider cập nhật chỉ số khi `List` thay đổi |
| Khi gọi `Collections.swap`/`List.sort` | Không tự tạo thứ tự bền vững theo vị trí trong list | Có thể đổi thứ tự bền vững nếu list đang được quản lý và transaction được flush |
| Dữ liệu phù hợp | Danh sách sắp theo tên, ngày, mức ưu tiên | Playlist, bước trong quy trình, chương có thể kéo thả |
| Kiểu collection thường dùng | `List`; cũng có thể dùng trong một số mapping `Set` hoặc element collection | `List` có vị trí |
| Tính ổn định với giá trị trùng | Cần thêm khóa phụ để phân định | Chỉ số định vị từng phần tử |
| Chi phí khi di chuyển phần tử | Thường cập nhật thuộc tính làm khóa sắp xếp | Có thể phải cập nhật chỉ số của nhiều dòng |

**Quy tắc chọn:** Nếu thứ tự được tính từ *giá trị của bản ghi*, chọn `@OrderBy`. Nếu thứ tự là *dữ liệu độc lập cần lưu của chính danh sách*, chọn `@OrderColumn`.

## 3. `@OrderBy`: sắp theo thuộc tính của entity liên quan

Cú pháp cơ bản:

```java
@OrderBy("priority ASC, id ASC")
private List<Employee> employees = new ArrayList<>();
```

Giá trị annotation tham chiếu **tên thuộc tính Java được JPA ánh xạ**, không phải tên cột SQL. Có thể ghi nhiều thuộc tính cách nhau bằng dấu phẩy và hướng `ASC`/`DESC`; nếu bỏ hướng thì mặc định là `ASC`. `@OrderBy` không có đối số (hoặc giá trị rỗng) trên quan hệ tới entity có nghĩa là sắp tăng theo khóa chính của entity liên quan.

### 3.1. Ví dụ `@OneToMany` hai chiều

Hai đoạn sau là **hai file Java trong cùng package `demo.ordering`**, sử dụng bên trong dự án đã cấu hình Jakarta Persistence/Spring Data JPA; chúng không phải chương trình `main` độc lập.

**`Department.java`**

```java
package demo.ordering;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "departments")
public class Department {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "department",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    @OrderBy("priority ASC, id ASC")
    private List<Employee> employees = new ArrayList<>();

    protected Department() {}

    public Long getId() { return id; }
    public List<Employee> getEmployees() { return employees; }

    public void addEmployee(Employee employee) {
        employees.add(employee);
        employee.assignDepartment(this);
    }
}
```

**`Employee.java`**

```java
package demo.ordering;

import jakarta.persistence.*;

@Entity
@Table(name = "employees")
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private int priority;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    protected Employee() {}

    public Employee(String name, int priority) {
        this.name = name;
        this.priority = priority;
    }

    void assignDepartment(Department department) {
        this.department = department;
    }

    public String getName() { return name; }
    public int getPriority() { return priority; }
    public void setPriority(int priority) { this.priority = priority; }
}
```

Ví dụ thêm nhân viên theo thứ tự gọi hàm: “Bình” ưu tiên 30, “An” ưu tiên 10, “Chi” ưu tiên 20. Sau khi persist, flush và **nạp lại collection từ persistence context mới**, thứ tự theo `@OrderBy` sẽ là **An → Chi → Bình**, vì `10 < 20 < 30`. SQL do provider sinh ra có thể tương đương:

```sql
SELECT e.*
FROM employees e
WHERE e.department_id = ?
ORDER BY e.priority ASC, e.id ASC;
```

Đây là SQL **minh họa về ý nghĩa**; câu SQL thực tế phụ thuộc phiên bản Hibernate, fetch strategy và database. Không nên kỳ vọng Java `List` vừa thêm phần tử sẽ tự được sắp lại ngay lập tức trong bộ nhớ: quy tắc `@OrderBy` được áp dụng khi **collection được truy xuất/nạp**.

Ở mapping hai chiều, `Employee.department` là phía sở hữu khóa ngoại vì `Department.employees` khai báo `mappedBy`. Hàm `addEmployee` cập nhật cả hai phía để tránh trạng thái đối tượng thiếu nhất quán; `@OrderBy` không thay thế việc đồng bộ quan hệ.

### 3.2. Đặc điểm cần hiểu

- **Không có chỉ số thứ tự độc lập.** Nếu sửa `Employee.priority`, thứ tự khi đọc lại có thể thay đổi; chỉ đổi chỗ hai phần tử của Java `List` mà giữ nguyên `priority` thì không tạo ra thứ tự mới trong database.
- **Thêm khóa phụ khi có giá trị bằng nhau.** `@OrderBy("priority ASC")` không đảm bảo thứ tự giữa hai nhân viên cùng `priority`. Thêm `id ASC` giúp ổn định kết quả nếu `id` là duy nhất.
- **Tên trong biểu thức là thuộc tính JPA.** Nếu trường `priority` được ánh xạ tới cột `priority_no` bằng `@Column(name = "priority_no")`, vẫn dùng `@OrderBy("priority ASC")`.
- **Có thể theo thuộc tính embedded.** Ví dụ `@OrderBy("address.city ASC, id ASC")` nếu `address` là embeddable và `city` là thuộc tính lưu được, có thể so sánh.
- **Không phải biểu thức SQL tùy ý.** Tránh đưa `LOWER(name)`, bí danh bảng hoặc tên cột vật lý vào `jakarta.persistence.OrderBy`. Biểu thức SQL riêng là tính năng khác của provider và kém di động.
- **Thứ tự của một collection không đồng nghĩa thứ tự mọi truy vấn.** Gọi trực tiếp `employeeRepository.findAll()` vẫn cần `Sort` hoặc `ORDER BY` riêng nếu yêu cầu kết quả truy vấn có thứ tự.

### 3.3. `@OrderBy` trên `@ElementCollection`

Với collection chứa **giá trị cơ bản** (ví dụ `String`), có thể chỉ định hướng theo chính giá trị phần tử:

```java
@ElementCollection
@CollectionTable(
    name = "team_tags",
    joinColumns = @JoinColumn(name = "team_id")
)
@Column(name = "tag")
@OrderBy("ASC")
private List<String> tags = new ArrayList<>();
```

Ở đây `@OrderBy("ASC")` sắp theo giá trị chuỗi; không viết tên cột SQL `tag` trong biểu thức. Với collection embeddable, chỉ định thuộc tính embeddable, và có thể dùng dấu chấm cho embedded lồng nhau, ví dụ `@OrderBy("postalCode.zip ASC")` khi mapping thực sự có đường dẫn đó.

Cả hai trường hợp đều là **sắp theo giá trị**, không lưu vị trí thao tác kéo thả của người dùng.

## 4. `@OrderColumn`: lưu vị trí của từng phần tử `List`

Khi thứ tự trong list chính là dữ liệu nghiệp vụ, cần cột chỉ số:

```java
@ElementCollection
@OrderColumn(name = "track_position")
private List<String> tracks = new ArrayList<>();
```

Theo Jakarta Persistence, cột thứ tự có kiểu **số nguyên**, các giá trị sau khi đồng bộ là liên tiếp và phần tử đầu tiên ở vị trí **0**. Provider quản lý cột này; không cần và thông thường không nên tự ánh xạ nó thành một trường của entity phần tử.

`@OrderColumn` có thể dùng cho `@OneToMany`, `@ManyToMany` hoặc `@ElementCollection`. Cột vị trí nằm trong bảng phù hợp với cách ánh xạ quan hệ: bảng phần tử, bảng con hoặc bảng liên kết.

### 4.1. Ví dụ playlist với `@ElementCollection`

Đây là mapping đơn giản giúp thấy rõ thứ tự mà không phải xử lý đồng bộ hai phía của `@OneToMany`.

**`Playlist.java`** (trong package `demo.ordering`)

```java
package demo.ordering;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "playlists")
public class Playlist {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "playlist_tracks",
        joinColumns = @JoinColumn(name = "playlist_id")
    )
    @Column(name = "track_title", nullable = false)
    @OrderColumn(name = "track_position")
    private List<String> tracks = new ArrayList<>();

    protected Playlist() {}

    public Playlist(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public List<String> getTracks() { return tracks; }

    public void addTrack(String title) {
        tracks.add(title);
    }

    public void removeTrack(int index) {
        tracks.remove(index);
    }

    public void moveTrack(int from, int to) {
        if (from == to) {
            return;
        }
        String selected = tracks.remove(from);
        tracks.add(to, selected);
    }
}
```

Ví dụ sau khi lưu playlist 42, bảng `playlist_tracks` có ý nghĩa như sau:

| playlist_id | track_position | track_title |
| ---: | ---: | --- |
| 42 | 0 | Mở đầu |
| 42 | 1 | Phần giữa |
| 42 | 2 | Kết thúc |

Khi gọi `moveTrack(2, 0)` trên một `Playlist` **đang được quản lý trong transaction**, thứ tự list trở thành `[Kết thúc, Mở đầu, Phần giữa]`. Đến lúc flush, provider duy trì các vị trí tương ứng `0, 1, 2`. Tùy mapping, provider và database, SQL có thể là nhiều lệnh `UPDATE` hoặc xóa/chèn lại một số dòng; không ràng buộc chính xác số câu SQL với ví dụ này.

`moveTrack` minh họa thao tác với các chỉ số hợp lệ: `from` và `to` nằm trong khoảng `0` tới `size - 1`. Thao tác gọi với chỉ số không hợp lệ sẽ ném `IndexOutOfBoundsException`. Trong nghiệp vụ thật, kiểm tra dữ liệu đầu vào, quyền sửa playlist và transaction trước khi thao tác.

### 4.2. Sử dụng qua Spring Data JPA trong transaction

**`PlaylistRepository.java`**

```java
package demo.ordering;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PlaylistRepository
        extends JpaRepository<Playlist, Long> {
}
```

**`PlaylistService.java`**

```java
package demo.ordering;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaylistService {
    private final PlaylistRepository repository;

    public PlaylistService(PlaylistRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void moveTrack(Long playlistId, int from, int to) {
        Playlist playlist = repository.findById(playlistId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Playlist not found"));
        playlist.moveTrack(from, to);
    }
}
```

`@Transactional` giữ entity và collection ở trạng thái được quản lý trong lúc thay đổi. Khi transaction hoàn tất, dirty checking/flush của JPA xử lý cập nhật. Với entity đã managed, `save()` sau mỗi thao tác nhỏ thường không cần thiết; `save()` cũng không thay thế transaction hợp lệ trong các tình huống cập nhật collection.

Nếu thay đổi một list đã detached ngoài persistence context rồi không merge hoặc nạp/quản lý lại đúng cách, đừng giả định vị trí đã được ghi xuống database.

### 4.3. Kiểm thử **sau khi flush và clear**

Một assertion chỉ kiểm tra `playlist.getTracks()` ngay sau `moveTrack()` sẽ vẫn đúng ngay cả khi ánh xạ persistence bị sai. Cần nạp lại dữ liệu từ database:

**`PlaylistOrderingTest.java`** — ví dụ cho dự án Spring Boot 3.x có `spring-boot-starter-data-jpa`, H2 dành cho test và `spring-boot-starter-test`.

```java
package demo.ordering;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class PlaylistOrderingTest {
    @Autowired
    TestEntityManager entityManager;

    @Autowired
    PlaylistRepository repository;

    @Test
    void orderSurvivesReloadAndMove() {
        Playlist playlist = new Playlist("Ví dụ");
        playlist.addTrack("Mở đầu");
        playlist.addTrack("Phần giữa");
        playlist.addTrack("Kết thúc");

        entityManager.persistAndFlush(playlist);
        Long id = playlist.getId();
        entityManager.clear();

        Playlist loaded = repository.findById(id).orElseThrow();
        assertThat(loaded.getTracks()).containsExactly(
                "Mở đầu", "Phần giữa", "Kết thúc");

        loaded.moveTrack(2, 0);
        entityManager.flush();
        entityManager.clear();

        Playlist reloaded = repository.findById(id).orElseThrow();
        assertThat(reloaded.getTracks()).containsExactly(
                "Kết thúc", "Mở đầu", "Phần giữa");
    }
}
```

Đặt các file vào package được ứng dụng Spring Boot quét, cung cấp database test và dependency tương ứng; chạy `./mvnw test` trên Linux/macOS hoặc `mvnw.cmd test` trên Windows (nếu dự án dùng Maven Wrapper). Đây là các file trong **một dự án Spring Boot đã thiết lập**, không phải ví dụ có thể chạy bằng `javac` đơn lẻ không có dependency. Assertion đầu xác nhận thứ tự ban đầu tồn tại sau khi nạp lại; assertion thứ hai xác nhận vị trí mới cũng tồn tại sau flush/clear.

## 5. Quan hệ `@OneToMany` và `@ManyToMany`: cột vị trí đặt ở đâu?

Với collection entity, chiến lược bảng phụ thuộc quyền sở hữu quan hệ.

**`@OneToMany` một chiều dùng bảng liên kết** (một mẫu mapping hợp lệ):

```java
@OneToMany(cascade = CascadeType.ALL)
@OrderColumn(name = "item_position")
private List<Item> items = new ArrayList<>();
```

Provider có thể dùng bảng liên kết chứa mã cha, mã `Item` và `item_position`. Nếu mapping có `@JoinColumn` cụ thể, cấu trúc lưu vị trí có thể khác. Không giả định luôn có bảng liên kết nếu chưa đọc mapping/schema thực tế.

**`@ManyToMany` phía sở hữu**:

```java
@ManyToMany
@JoinTable(
    name = "course_students",
    joinColumns = @JoinColumn(name = "course_id"),
    inverseJoinColumns = @JoinColumn(name = "student_id")
)
@OrderColumn(name = "student_position")
private List<Student> students = new ArrayList<>();
```

Chỉ số ở đây biểu diễn vị trí của một sinh viên trong **danh sách của từng course**, không phải một thứ tự toàn cục của `Student`. Một sinh viên có thể xuất hiện ở vị trí khác nhau trong các course khác nhau.

**Thận trọng với `mappedBy`:** Khi mapping dùng `@OneToMany(mappedBy = "...")` hoặc `@ManyToMany(mappedBy = "...")`, phía có `mappedBy` không sở hữu liên kết. Một số cách dùng `@OrderColumn` trên collection phía ngược được Hibernate hỗ trợ theo loại quan hệ và phiên bản, nhưng có khác biệt về tính di động giữa provider; đặc biệt không mặc nhiên áp dụng cách này cho `@ManyToMany(mappedBy = "...")`. Muốn cấu hình bền vững giữa các provider, ưu tiên vị trí ở mapping sở hữu collection và kiểm thử DDL, flush và readback. Nếu chỉ cần sắp theo thuộc tính của phần tử ở phía `mappedBy`, `@OrderBy` thường đơn giản hơn.

## 6. Những giới hạn và tác động lên thiết kế

### 6.1. Không dùng đồng thời hai annotation cho một collection

`@OrderBy` và `@OrderColumn` phản ánh hai nguồn thứ tự khác nhau. Theo Jakarta Persistence, khi một collection có `@OrderColumn` thì quy tắc `@OrderBy` **không được sử dụng** cho collection đó. Hãy chọn một mô hình rõ ràng; đừng kỳ vọng vừa có thứ tự kéo thả tùy ý, vừa tự sắp theo `priority` trên cùng mapping.

Nếu yêu cầu là “ưu tiên theo nhóm, nhưng trong mỗi nhóm được kéo thả”, cần mô hình hóa thêm thuộc tính nhóm và chỉ số thứ tự riêng, cùng logic cập nhật và truy vấn phù hợp, thay vì ghép hai annotation rồi trông đợi provider tự giải quyết xung đột.

### 6.2. Chi phí ghi khi thay đổi list

Với `@OrderColumn`, chèn một phần tử ở đầu hoặc xóa ở giữa có thể làm đổi vị trí nhiều phần tử kế tiếp. Trên list lớn, provider có thể thực hiện nhiều lệnh SQL; cần quan sát log/metrics trong môi trường thử nghiệm, kiểm tra index và cách flush. Không tự viết một loạt `UPDATE` chỉ số song song với quản lý của JPA khi chưa xác định rõ quyền sở hữu dữ liệu.

Với `@OrderBy`, việc sort lúc đọc có thể cần database xử lý `ORDER BY`; cân nhắc index trên khóa ngoại và các cột thường dùng sắp xếp khi dữ liệu lớn. Index nào hiệu quả phụ thuộc hệ quản trị và truy vấn thực tế, cần xác nhận bằng execution plan.

### 6.3. Giao dịch, concurrency và nhất quán

- Giữ thao tác thay đổi collection trong **transaction**. Với `@OrderColumn`, kiểm chứng sau flush/clear và sau transaction mới, thay vì chỉ nhìn list trong RAM.
- Hai người đồng thời kéo thả cùng một danh sách có thể gây tình huống cập nhật cạnh tranh hoặc người lưu sau ghi đè thứ tự. Cân nhắc khóa lạc quan (`@Version` trên aggregate phù hợp), phiên bản payload hoặc quy tắc conflict; kiểm thử cơ chế cập nhật collection của provider thực tế.
- Không sửa chỉ số trong database bằng script ngoài ứng dụng mà bỏ qua sự liên tục hoặc quan hệ cha–con. Việc cần làm với dữ liệu đã tồn tại là backfill theo từng cha thành các vị trí `0..n-1` và kiểm tra trùng/chỗ trống trước khi đưa mapping vào dùng.
- Trên `@OneToMany` hai chiều, helper thêm/xóa phần tử phải bảo toàn hai phía quan hệ; vị trí trong list không sửa được khóa ngoại nếu object graph bị sai.

### 6.4. Khi chỉ cần sắp một truy vấn

Nếu endpoint trả danh sách nhân viên toàn hệ thống theo tên, nên dùng repository query với `Sort` hoặc `Pageable`:

```java
employeeRepository.findAll(
    org.springframework.data.domain.Sort.by(
        org.springframework.data.domain.Sort.Order.asc("priority"),
        org.springframework.data.domain.Sort.Order.asc("id")
    )
);
```

Đây là ví dụ **đoạn mã gọi repository**, không phải chương trình độc lập. `Sort` áp dụng cho **truy vấn ấy**; `@OrderBy` áp dụng khi JPA nạp **một collection đã ánh xạ**. Tránh fetch join nhiều collection rồi phân trang một cách tùy tiện: cách ORM xử lý số hàng, trùng lặp hoặc phân trang có thể không tương ứng một trang aggregate theo mong muốn.

## 7. Lỗi phổ biến và cách nhận diện

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `List` đọc lại theo thứ tự khác lúc thêm | Chỉ khai báo `List`, chưa có hợp đồng lưu/sắp thứ tự | Chọn `@OrderBy` hoặc `@OrderColumn` theo nghiệp vụ |
| Kéo thả list dùng `@OrderBy` nhưng đọc lại quay về thứ tự cũ | Thứ tự phụ thuộc thuộc tính entity, không phụ thuộc vị trí vừa swap | Đổi thuộc tính sắp xếp, hoặc chuyển sang vị trí lưu bằng `@OrderColumn` |
| Dùng `@OrderBy("priority_no")` nhưng field Java tên `priority` | Nhầm tên cột SQL và tên thuộc tính JPA | Dùng `@OrderBy("priority")` |
| Hai phần tử cùng khóa sắp xếp đảo chỗ | Không có thứ tự phụ trợ khi giá trị trùng | Thêm khóa duy nhất như `id ASC` |
| `@OrderColumn` mất tác dụng sau một lần cập nhật | Thay đổi ngoài transaction/đã detached/chưa flush hoặc mapping không quản lý collection như mong muốn | Kiểm tra state, transaction, owning side và test flush/clear/readback |
| Sau xóa phần tử giữa list, nhiều SQL `UPDATE` | Provider phải duy trì dãy vị trí liên tiếp | Đánh giá tần suất thao tác, kích thước list, index và log SQL |
| Khởi động hoặc lưu báo lỗi cột `item_position` | Schema thiếu cột, sai tên/kiểu, dữ liệu cũ chưa backfill | Đồng bộ mapping với migration có kiểm thử và backfill đúng từng cha |
| Dùng `@OrderColumn` trên quan hệ ngược `mappedBy` và lệ thuộc provider | Mapping order column không di động trong mọi cấu hình | Dùng mapping sở hữu được hỗ trợ hoặc chọn `@OrderBy`, kiểm thử với provider triển khai |

Không nhầm `jakarta.persistence.OrderBy` với API sắp xếp chuyên biệt của Hibernate hoặc `org.springframework.data.domain.Sort`. Không có `@OrderBy`/`@OrderColumn` cũng không đồng nghĩa “thứ tự sẽ theo `id`”: không được dựa vào thứ tự tình cờ của kết quả SQL.

## 8. Quy trình áp dụng thực tế

1. Viết rõ yêu cầu: **theo thuộc tính** hay **theo vị trí do người dùng định nghĩa**. Với thay đổi thứ tự được phép, xác định nguồn sự thật khi ghi.
2. Chọn mapping quan hệ (`@OneToMany`, `@ManyToMany`, `@ElementCollection`), phía sở hữu và collection type. Dùng `List` cho trường hợp cần chỉ số vị trí.
3. Với `@OrderBy`, khai báo thuộc tính Java và khóa phụ quyết định thứ tự khi hòa; với `@OrderColumn`, khai báo tên cột vị trí và chuẩn bị migration/backfill nếu bảng đã có dữ liệu.
4. Cập nhật object graph trong transaction. Với quan hệ hai chiều, cập nhật cả hai phía.
5. Tạo integration test lưu → flush → clear → tải lại → kiểm tra danh sách; thêm test di chuyển, chèn ở đầu, xóa ở giữa và nhiều cha khác nhau. Đối với `@OrderBy`, sửa giá trị thuộc tính sắp rồi kiểm chứng thứ tự khi nạp lại.
6. Kiểm tra SQL và chi phí khi collection lớn; kiểm tra cạnh tranh cập nhật nếu người dùng có thể sửa thứ tự đồng thời.

### Bài tập tự kiểm tra

**Bài 1.** Một phòng ban phải hiển thị nhân viên theo `priority` tăng dần và `id` tăng dần khi cùng mức ưu tiên. Đáp án: `@OrderBy("priority ASC, id ASC")` trên collection entity; không cần cột vị trí.

**Bài 2.** Một người dùng đổi thứ tự ba mục trong checklist từ `[A, B, C]` thành `[C, A, B]` mà không đổi tên/mã các mục. Đáp án: ánh xạ `List` với `@OrderColumn`; đổi chỗ list trong transaction rồi flush. Khi lưu, cột chỉ số phải thể hiện `C=0, A=1, B=2` theo từng checklist.

**Bài 3.** Tại sao unit test chỉ gọi `assertEquals(List.of("C", "A", "B"), playlist.getTracks())` ngay sau `moveTrack` chưa chứng minh mapping đúng? Đáp án: nó chỉ kiểm tra thao tác list trong RAM; phải flush, clear, nạp lại từ database và so sánh.

## 9. Ghi nhớ và tài liệu đối chiếu

- `@OrderBy`: **sắp theo giá trị**, không lưu vị trí riêng. Ưu tiên khi thứ tự là hệ quả của các thuộc tính nghiệp vụ.
- `@OrderColumn`: **lưu vị trí của list**, provider duy trì chỉ số bắt đầu từ 0 và liên tiếp. Ưu tiên khi người dùng có thể tự đổi thứ tự.
- Cả hai đều thuộc Jakarta Persistence; Spring Data JPA dùng các mapping này cùng Hibernate hoặc provider JPA được cấu hình. Để chứng minh đúng, hãy luôn **ghi rồi nạp lại** trong integration test.

Tài liệu chuẩn và giải thích chuyên sâu:
- Jakarta Persistence 3.2 — `OrderBy`: https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/orderby
- Jakarta Persistence 3.2 — `OrderColumn`: https://javadoc.io/static/jakarta.persistence/jakarta.persistence-api/3.2.0/jakarta.persistence/jakarta/persistence/OrderColumn.html
- Hibernate ORM User Guide — Collections/Ordered Lists: https://docs.hibernate.org/orm/6.6/userguide/html_single/#collections
