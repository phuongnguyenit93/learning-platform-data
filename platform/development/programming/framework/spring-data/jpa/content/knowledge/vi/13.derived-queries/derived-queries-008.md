# Kết hợp `And`, `Or` và giới hạn biểu diễn điều kiện có nhóm trong Spring Data JPA

Khi viết **truy vấn suy diễn từ tên phương thức** (derived query), Spring Data JPA cho phép nối nhiều điều kiện bằng `And` và `Or`. Điểm dễ sai là tên phương thức **không có cú pháp ngoặc để tự chọn cách nhóm điều kiện**. Vì vậy, phải hiểu đúng cây điều kiện mà Spring Data tạo ra, nhất là khi một yêu cầu nghiệp vụ chứa cả “và” lẫn “hoặc”.

## 1. `And` và `Or` hoạt động thế nào?

Với một repository như `JpaRepository<Customer, Long>`, phần sau `By` trong tên `findBy...` mô tả điều kiện trên các thuộc tính của entity. Ví dụ:

```java
List<Customer> findByNameAndStatus(String name, Status status);
List<Customer> findByNameOrEmail(String name, String email);
```

Hai phương thức trên tương ứng về mặt logic với:

```text
name = ?1 AND status = ?2
name = ?1 OR  email  = ?2
```

Spring Data Commons dùng bộ phân tích `PartTree`: tách biểu thức theo `Or` thành các nhánh, rồi tách từng nhánh theo `And`. Do đó, **`And` có mức ưu tiên cao hơn `Or`** trong truy vấn suy diễn. Có thể nhìn dạng tổng quát như sau:

```text
AAndBOrCAndDOrE
        ↓
(A AND B) OR (C AND D) OR E
```

Đây là quy tắc phân tích tên phương thức, không phụ thuộc vào thứ tự mà người viết *muốn* nhóm các điều kiện.

| Tên phương thức (phần sau `By`) | Điều kiện logic được hiểu |
| --- | --- |
| `NameAndStatus` | `name AND status` |
| `NameOrEmail` | `name OR email` |
| `NameAndStatusOrEmail` | `(name AND status) OR email` |
| `NameOrEmailAndStatus` | `name OR (email AND status)` |
| `NameAndStatusOrEmailAndStatus` | `(name AND status) OR (email AND status)` |

Lưu ý: bảng mô tả **logic của bộ lọc**; dấu `?1`, `?2` là cách minh họa tham số theo thứ tự, không có nghĩa tên phương thức tự tạo ra dấu ngoặc tùy ý.

## 2. Lỗi thực tế: muốn `(A OR B) AND C` nhưng viết thành `A OR (B AND C)`

Giả sử entity `Customer` có các thuộc tính:

- `name`: tên khách hàng (`String`).
- `email`: địa chỉ email (`String`).
- `status`: trạng thái (`Status`, chẳng hạn `ACTIVE` hoặc `SUSPENDED`).

Yêu cầu: **Tìm khách có tên *hoặc* email khớp dữ liệu nhập, đồng thời trạng thái phải bằng `ACTIVE`.**

Biểu thức cần có là:

```text
(name = :name OR email = :email)
AND status = :status
```

Cách viết sau **không đáp ứng** yêu cầu:

```java
List<Customer> findByNameOrEmailAndStatus(
        String name, String email, Status status);
```

Spring Data hiểu nó thành:

```text
name = ?1 OR (email = ?2 AND status = ?3)
```

Vì nhánh `name = ?1` đứng riêng bên ngoài điều kiện trạng thái, một khách hàng có tên khớp vẫn có thể được trả về dù `status` là `SUSPENDED`.

Ví dụ với tham số `name = "Lan"`, `email = "lan@example.com"`, `status = ACTIVE`:

| Bản ghi | Khớp tên (A) | Khớp email (B) | Trạng thái ACTIVE (C) | `A OR (B AND C)` | `(A OR B) AND C` |
| --- | --- | --- | --- | --- | --- |
| Lan, other@example.com, SUSPENDED | Đúng | Sai | Sai | **Đúng** | **Sai** |
| Lan, other@example.com, ACTIVE | Đúng | Sai | Đúng | Đúng | Đúng |
| Minh, lan@example.com, ACTIVE | Sai | Đúng | Đúng | Đúng | Đúng |
| Minh, other@example.com, ACTIVE | Sai | Sai | Đúng | Sai | Sai |

Hàng đầu tiên là phép thử quan trọng: hai cách đặt nhóm trả về kết quả khác nhau.

## 3. Diễn đạt một nhóm OR bằng tên phương thức: phân phối điều kiện AND

Trong đại số Boolean, ta có:

```text
(A OR B) AND C
≡ (A AND C) OR (B AND C)
```

Vì thế, có thể diễn đạt yêu cầu ở trên bằng cách lặp lại `status` trong **cả hai nhánh** của tên phương thức:

```java
List<Customer> findByNameAndStatusOrEmailAndStatus(
        String name,
        Status statusForName,
        String email,
        Status statusForEmail);
```

Cách gọi minh họa:

```java
repository.findByNameAndStatusOrEmailAndStatus(
        "Lan",
        Status.ACTIVE,
        "lan@example.com",
        Status.ACTIVE);
```

Phương thức này có logic:

```text
(name = ?1 AND status = ?2)
OR
(email = ?3 AND status = ?4)
```

Khi truyền cùng một trạng thái cho `?2` và `?4`, biểu thức tương đương với `(name OR email) AND status`. Hai tham số trạng thái **là hai vị trí riêng biệt**: nếu vô tình truyền khác nhau, ý nghĩa truy vấn cũng thay đổi.

Cách phân phối phù hợp khi chỉ có vài nhánh ngắn. Đối với nhiều nhóm lồng nhau, tên phương thức nhanh chóng trở nên dài, lặp lại thuộc tính và khó kiểm tra.

## 4. Giới hạn của tên phương thức: không đặt ngoặc nhóm tùy ý

Không thể chèn `(` và `)` vào tên derived query để yêu cầu parser đổi thứ tự ưu tiên, ví dụ không tồn tại cú pháp được hỗ trợ kiểu:

```text
findBy(NameOrEmail)AndStatus(...)
```

Đây **không phải** một derived-query method hợp lệ để biểu thị nhóm `(name OR email)`.

Cũng không thể đổi vị trí `And`, `Or` một cách tùy tiện rồi hy vọng Spring Data tự suy ra đúng ý định. Ví dụ:

```text
AOrBAndC       → A OR (B AND C)
AAndBOrC       → (A AND B) OR C
AAndCOrBAndC   → (A AND C) OR (B AND C)
```

Tuy nhiên, “không có ngoặc” **không đồng nghĩa mọi biểu thức có nhóm đều bất khả thi**. Một số có thể đổi thành dạng *OR của các nhóm AND* (dạng tuyển chuẩn, DNF) nhờ luật phân phối. Chẳng hạn:

```text
(A OR B) AND (C OR D)
≡ (A AND C) OR (A AND D) OR (B AND C) OR (B AND D)
```

Về mặt logic biểu diễn được, nhưng số nhánh và tham số lặp lại tăng nhanh. Càng nhiều nhóm `OR` kết hợp `AND`, tên phương thức càng khó đọc, khó bảo trì và dễ thiếu một tổ hợp.

Quy tắc chọn cách viết: với bộ lọc ngắn, rõ ràng, dùng derived query; khi cần nhóm phức tạp hoặc có nhiều điều kiện tùy chọn, chuyển sang truy vấn khai báo hoặc API xây dựng truy vấn.

## 5. Khi cần ngoặc tường minh: dùng `@Query` với JPQL

Với yêu cầu “(tên hoặc email) và trạng thái”, viết câu truy vấn có ngoặc thường dễ hiểu hơn. Đoạn sau là phần của một dự án đã có entity `Customer`, enum `Status` và dependency Spring Data JPA; không phải chương trình Java độc lập:

```java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where (c.name = :name or c.email = :email)
          and c.status = :status
        """)
    List<Customer> searchContactsWithStatus(
            @Param("name") String name,
            @Param("email") String email,
            @Param("status") Status status);
}
```

Điểm cần hiểu:

1. `Customer` trong JPQL là **tên entity**; `name`, `email`, `status` là **tên thuộc tính Java** của entity, không nhất thiết là tên bảng/cột SQL.
2. Dấu ngoặc bao quanh `c.name = :name or c.email = :email` thể hiện chính xác nhóm điều kiện nghiệp vụ.
3. `@Param` gắn từng tham số Java với tham số có tên trong JPQL, nên không cần truyền `status` hai lần.
4. `@Query` khai báo truy vấn trực tiếp cho phương thức; không dựa vào phép tách `And`/`Or` trong tên phương thức để dựng phần điều kiện.

Ví dụ trên giả định các tham số tìm kiếm đều khác `null`. Nếu cho phép `null` hoặc muốn “bỏ qua bộ lọc khi không nhập”, phải thiết kế rõ ngữ nghĩa của từng tham số; không được mặc định cách so sánh `= :param` trong JPQL giống hoàn toàn việc đưa `null` vào derived query.

## 6. Bộ lọc động, nhiều nhóm: dùng JPA `Specification`

Khi điều kiện thay đổi theo màn hình tìm kiếm, `Specification` cho phép dựng cây Boolean trực tiếp bằng Criteria API, với `and` và `or` được nhóm rõ ràng:

```java
import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecs {
    private CustomerSpecs() {}

    public static Specification<Customer> contactAndStatus(
            String name, String email, Status status) {
        return (root, query, cb) -> cb.and(
                cb.or(
                        cb.equal(root.get("name"), name),
                        cb.equal(root.get("email"), email)),
                cb.equal(root.get("status"), status));
    }
}
```

Repository muốn chạy `Specification` cần mở rộng thêm `JpaSpecificationExecutor<Customer>`:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerSearchRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

Khi đã có repository bean, có thể gọi:

```java
var spec = CustomerSpecs.contactAndStatus(
        "Lan", "lan@example.com", Status.ACTIVE);
var customers = customerSearchRepository.findAll(spec);
```

`cb.or(...)` là một nhóm bên trong `cb.and(...)`, đúng với `(A OR B) AND C`. Đây là **các đoạn mã tích hợp** cần đặt trong các file Java thích hợp của ứng dụng Spring Data JPA, cùng entity và dependency liên quan. Với bộ lọc có giá trị tùy chọn, hãy **chỉ thêm predicate cho tiêu chí thực sự được cung cấp**; ví dụ trên minh họa trường hợp ba tham số đều có giá trị.

Nếu nhiều giá trị `OR` đều áp dụng lên **cùng một thuộc tính**, cân nhắc keyword `In`, chẳng hạn `findByStatusIn(Collection<Status> statuses)`, thay vì viết `StatusOrStatusOr...`. `In` không thay thế việc nhóm điều kiện trên **những thuộc tính khác nhau** như `name` và `email`.

## 7. Tự kiểm chứng thứ tự ưu tiên bằng Java 17

Chương trình độc lập sau không kết nối JPA; nó dùng toán tử Boolean của Java để làm rõ hai biểu thức logic mà derived query và yêu cầu nghiệp vụ đang mô tả.

Lưu vào file `AndOrDemo.java`:

```java
public class AndOrDemo {
    record Customer(String name, String email, String status) {}

    public static void main(String[] args) {
        Customer customer = new Customer(
                "Lan", "other@example.com", "SUSPENDED");

        String name = "Lan";
        String email = "lan@example.com";
        String status = "ACTIVE";

        boolean derived = customer.name().equals(name)
                || customer.email().equals(email)
                   && customer.status().equals(status);

        boolean intended = (customer.name().equals(name)
                || customer.email().equals(email))
                && customer.status().equals(status);

        System.out.println("Derived: " + derived);
        System.out.println("Intended: " + intended);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AndOrDemo.java
java AndOrDemo
```

Kết quả chuẩn:

```text
Derived: true
Intended: false
```

Trong Java, `&&` có ưu tiên cao hơn `||` nên hai dòng tính toán mô phỏng chính xác hai cây logic. Đây là phép thử logic độc lập, **không thay thế** kiểm thử tích hợp repository với dữ liệu thật và database mà ứng dụng sử dụng.

## 8. Cách kiểm tra repository để tránh sai nghiệp vụ

Trước khi chốt một method có cả `And` và `Or`:

1. Viết điều kiện nghiệp vụ ra trước, **có ngoặc rõ ràng**, ví dụ `(A OR B) AND C`.
2. Viết lại tên phương thức thành dạng mà parser thực sự hiểu: các **nhánh OR**, mỗi nhánh gồm các **điều kiện AND**.
3. So sánh hai biểu thức bằng các tình huống đối chứng; đặc biệt kiểm tra trường hợp `A = true, B = false, C = false` để phát hiện lỗi `A OR (B AND C)`.
4. Nếu dùng phép phân phối, đối chiếu **thứ tự tham số** và giá trị của mọi tham số bị lặp lại.
5. Viết kiểm thử tích hợp Spring Data JPA (chẳng hạn `@DataJpaTest`) với bản ghi khớp tên nhưng sai trạng thái, bản ghi khớp email và đúng trạng thái, cùng bản ghi không khớp; kiểm tra tập kết quả thực sự.
6. Nếu truy vấn trở nên dài, có nhiều nhóm `OR` hoặc phải điều chỉnh thường xuyên, chuyển sang `@Query` hoặc `Specification` để thể hiện ý định rõ hơn.

**Lỗi hay gặp:** nghĩ rằng `findByNameOrEmailAndStatus` có nghĩa `(name OR email) AND status`; nhầm rằng có thể đặt dấu ngoặc ngay trong tên phương thức; phân phối thiếu một nhánh; lặp lại cùng thuộc tính nhưng truyền tham số không giống nhau; hoặc thử chỉ trên dữ liệu mà mọi khách hàng đều có trạng thái `ACTIVE` nên không phát hiện lỗi ưu tiên.

## 9. Ghi nhớ

- Trong derived query của Spring Data JPA, `And` kết hợp chặt hơn `Or`: `AOrBAndC` được hiểu là `A OR (B AND C)`.
- Tên phương thức không hỗ trợ cú pháp ngoặc để **trực tiếp** chọn nhóm Boolean tùy ý.
- `(A OR B) AND C` có thể chuyển thành `(A AND C) OR (B AND C)` nhưng phải lặp lại điều kiện và, khi cần, lặp lại tham số.
- Với điều kiện dài, nhóm phức tạp hoặc lọc động, `@Query`/JPQL và `Specification` giúp diễn đạt đúng ý định và dễ kiểm thử hơn.

### Tài liệu tham khảo

- Spring Data JPA — Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data — Repository Query Keywords: https://docs.spring.io/spring-data/jpa/reference/repositories/query-keywords-reference.html
- Spring Data Commons — `PartTree` API và cấu trúc `OrPart`: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/parser/PartTree.html
