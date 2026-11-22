# Ràng buộc tham số theo vị trí và theo tên với @Param

## 1. Vì sao phải bind tham số?

Repository query thường nhận dữ liệu từ request hoặc từ logic nghiệp vụ: email, trạng thái, khoảng thời gian, mã khách hàng, danh sách ID... Những giá trị này cần được truyền vào query một cách an toàn và đúng kiểu.

Spring Data JPA hỗ trợ hai cách bind tham số chính trong JPQL:

- **Theo vị trí (positional):** query tham chiếu tham số bằng chỉ số như `?1`, `?2`.
- **Theo tên (named):** query tham chiếu tham số bằng tên như `:email`, `:status`; method dùng `@Param` để liên kết tên query với tham số Java.

Bind parameter giúp provider gửi giá trị riêng với cấu trúc query, thường thông qua prepared statement. Không nối chuỗi input trực tiếp vào JPQL/SQL vì có nguy cơ SQL injection, lỗi escaping và khó tái sử dụng statement.

## 2. Bind theo vị trí với ?1, ?2

Trong JPQL, positional parameter được đánh số bắt đầu từ 1. `?1` tương ứng tham số method thứ nhất, `?2` tương ứng tham số thứ hai:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("select c from Customer c where c.email = ?1 and c.status = ?2")
    Optional<Customer> findByEmailAndStatus(String email, CustomerStatus status);
}
```

Thứ tự trong method signature phải khớp chỉ số trong query. Nếu đổi thứ tự tham số Java mà không đổi query, giá trị có thể được bind nhầm vị trí hoặc provider báo lỗi kiểu dữ liệu.

Một positional parameter có thể được dùng nhiều lần bằng cùng chỉ số:

```java
@Query("""
    select c from Customer c
    where c.email = ?1 or c.backupEmail = ?1
    """)
List<Customer> findByPrimaryOrBackupEmail(String email);
```

Không dùng positional parameter trộn với named parameter trong cùng một JPQL query. Chọn một kiểu nhất quán để query dễ đọc và tránh lỗi binding.

## 3. Bind theo tên với @Param

Named parameter thường dễ bảo trì hơn khi query có nhiều tham số hoặc method signature có thay đổi thứ tự. Dùng `:parameterName` trong JPQL và `@Param("parameterName")` trên tham số Java:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("""
        select c from Customer c
        where c.email = :email
          and c.status = :status
        """)
    Optional<Customer> findCustomer(
        @Param("email") String email,
        @Param("status") CustomerStatus status
    );
}
```

`@Param` thuộc package `org.springframework.data.repository.query.Param`. Tên trong annotation phải khớp chính xác với tên sau dấu `:` trong query; tên phân biệt chữ hoa/chữ thường. Không ghi dấu `:` trong giá trị annotation.

Ví dụ này vẫn hoạt động nếu đổi thứ tự các tham số trong method mà giữ đúng mapping `@Param`. Tuy nhiên, nên giữ signature dễ đọc và kiểm thử query để tránh lỗi khi refactor.

## 4. Có bắt buộc phải dùng @Param không?

Spring Data có thể khám phá tên tham số Java trong một số cấu hình nếu class được biên dịch với metadata tên tham số, ví dụ tùy chọn compiler `-parameters`. Khi tên được khám phá thành công, query có thể tham chiếu trực tiếp tên method parameter mà không cần annotation.

Ví dụ:

```java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findByEmail(String email);
```

Để tránh phụ thuộc vào cấu hình compiler, phiên bản framework hoặc metadata khi build, `@Param` tường minh là cách rõ ràng và ổn định cho repository query có named parameter. Khi codebase đã có quy ước khác, hãy áp dụng nhất quán và xác nhận compiler giữ parameter names.

Không nhầm `@Param` với annotation validation như `@NotNull` hoặc annotation web như `@RequestParam`. `@Param` chỉ liên kết tên tham số method với placeholder trong repository query.

## 5. So sánh positional và named parameter

| Tiêu chí | Positional (`?1`) | Named (`:name` + `@Param`) |
| --- | --- | --- |
| Cách liên kết | Theo thứ tự tham số | Theo tên được khai báo |
| Đọc query | Khó nhận ra ý nghĩa khi có nhiều vị trí | Tên thể hiện vai trò của giá trị |
| Đổi thứ tự tham số method | Có thể làm binding sai nếu không cập nhật query | Mapping vẫn đúng nếu tên `@Param` giữ nguyên |
| Phù hợp | Query ngắn, ít tham số | Query nhiều tham số hoặc cần dễ bảo trì |

Với query có một tham số, positional binding ngắn gọn. Với query có nhiều điều kiện, named parameter thường dễ review hơn vì người đọc biết mỗi giá trị được dùng cho điều kiện nào.

## 6. Bind tham số cho điều kiện IN

Tham số collection có thể dùng với `IN` trong JPQL:

```java
@Query("select c from Customer c where c.status in :statuses")
List<Customer> findByStatuses(
    @Param("statuses") Collection<CustomerStatus> statuses
);
```

Provider sẽ bind các phần tử collection vào điều kiện. Cần định nghĩa rõ trường hợp collection rỗng: ứng dụng muốn trả danh sách rỗng, bỏ bộ lọc hay từ chối request? Không dựa vào cách từng provider/database xử lý `IN ()`. Có thể kiểm tra collection ở service trước khi gọi repository.

Với danh sách rất lớn, cần lưu ý giới hạn số bind parameter của database/driver. Có thể chia batch, dùng bảng tạm, table-valued parameter hoặc cơ chế phù hợp với database nếu truy vấn cần hàng nghìn giá trị.

## 7. Bind tham số cho LIKE

Với `LIKE`, tham số chứa pattern. Có thể tự tạo pattern ở service hoặc dùng `concat` trong JPQL:

```java
@Query("""
    select c from Customer c
    where lower(c.name) like lower(concat('%', :keyword, '%'))
    """)
List<Customer> searchByName(
    @Param("keyword") String keyword
);
```

Trong ví dụ, `%` ở hai phía cho phép tìm chuỗi con. Nếu người dùng nhập ký tự `%` hoặc `_`, các ký tự này là wildcard của LIKE; nếu nghiệp vụ muốn tìm ký tự literal, cần escape theo cú pháp LIKE và khai báo ký tự escape phù hợp.

Không nối input trực tiếp vào chuỗi query. Hãy bind giá trị và xử lý wildcard theo đúng semantics của tìm kiếm.

## 8. Giá trị null và kiểu dữ liệu

Bind `null` không đồng nghĩa tự động bỏ điều kiện. Ví dụ `c.status = :status` với `status = null` không trả các hàng có status null theo cách so sánh thông thường; trong SQL, phép so sánh với NULL là UNKNOWN. Nếu cần tìm giá trị null, dùng `IS NULL` hoặc viết predicate riêng.

Ví dụ query tùy chọn:

```java
@Query("""
    select c from Customer c
    where (:status is null or c.status = :status)
    """)
List<Customer> searchByOptionalStatus(
    @Param("status") CustomerStatus status
);
```

Đây là cách đơn giản cho ít filter, nhưng nhiều biểu thức `:param is null or ...` có thể làm query khó tối ưu và một số tổ hợp kiểu dữ liệu/null gây vấn đề suy luận kiểu tùy provider/database. Với nhiều filter tùy chọn, cân nhắc Specification hoặc Querydsl để chỉ thêm predicate cần thiết.

Kiểu tham số Java nên tương thích với thuộc tính Entity: enum với enum, `Instant`/`LocalDate` với thuộc tính thời gian phù hợp, số với số. Tránh chuyển giá trị thành chuỗi chỉ để bind cho tiện; điều đó có thể làm mất type safety hoặc ảnh hưởng khả năng dùng index.

## 9. Pageable, Sort và các tham số đặc biệt

`Pageable`, `Sort` và `Limit` (nếu phiên bản Spring Data hỗ trợ) là các special parameter được Spring Data xử lý riêng. Chúng không phải placeholder thông thường như `:email` hoặc `?1` trong query.

```java
@Query("select c from Customer c where c.status = :status")
Page<Customer> findPageByStatus(
    @Param("status") CustomerStatus status,
    Pageable pageable
);
```

Không viết `:pageable` hoặc `?2` để bind nguyên đối tượng Pageable vào JPQL. Spring Data dùng nó để áp dụng phân trang/sort cho query. Khi dùng native query hoặc query có `ORDER BY` cố định, kiểm tra cách phiên bản Spring Data đang xử lý sort động và count query.

Không cho phép input không tin cậy trở thành tên cột, tên bảng, toán tử hoặc đoạn `ORDER BY` bằng cách bind parameter. Bind parameter chỉ thay thế **giá trị**, không thay thế cấu trúc SQL. Với sort động, dùng `Sort`/`Pageable` và allow-list các thuộc tính hợp lệ.

## 10. Native SQL và tính di động

JPQL hỗ trợ named parameter `:name` và positional parameter `?1`. Với native SQL, cú pháp placeholder và mức hỗ trợ named parameter phụ thuộc hợp đồng JPA, Spring Data và provider cụ thể.

Ví dụ native query positional thường gặp trong Spring Data JPA:

```java
@Query(
    value = "select * from customer where email = ?1",
    nativeQuery = true
)
Optional<Customer> findNativeByEmail(String email);
```

Native query phải dùng tên bảng/cột vật lý. Theo tính di động của JPA, positional parameters là lựa chọn an toàn cho native SQL; named parameter trong native query có thể được provider như Hibernate hỗ trợ nhưng không nên mặc định rằng mọi provider đều hỗ trợ giống nhau. Nếu dùng named native parameter, hãy kiểm tra tài liệu và integration test trên provider/database thực tế.

## 11. Tham số không thể thay thế identifier hoặc cú pháp query

Không thể bind tên cột hoặc tên bảng như một giá trị:

```java
// Không thể dùng :columnName để thay tên cột trong JPQL.
@Query("select c from Customer c order by :columnName")
```

`:columnName` ở vị trí đó là một giá trị parameter, không biến thành identifier. Tương tự, không thể bind từ khóa `ASC`, tên function hoặc đoạn điều kiện SQL.

Nếu cần sort theo một số cột do người dùng chọn, ánh xạ lựa chọn sang danh sách thuộc tính được cho phép rồi tạo `Sort`/`Pageable`. Không ghép trực tiếp chuỗi từ request vào JPQL hoặc native SQL.

## 12. Lỗi thường gặp khi binding

**Named parameter not bound.** Kiểm tra mọi placeholder `:name` có tham số method tương ứng và `@Param("name")` viết đúng chính tả/case.

**Không tìm thấy parameter name.** Thêm `@Param` tường minh hoặc xác nhận build có giữ parameter metadata bằng `-parameters`.

**Positional parameter index out of range.** Đếm từ 1 trong JPQL và bảo đảm `?1`, `?2` khớp method arguments.

**Bind nhầm kiểu.** Kiểm tra kiểu Java có tương thích thuộc tính Entity và kiểu dữ liệu database; tránh truyền chuỗi cho enum/số/thời gian khi không cần.

**IN với collection rỗng gây lỗi hoặc kết quả lạ.** Xử lý collection rỗng trước khi gọi repository theo quy tắc nghiệp vụ.

**Truy vấn với null không tìm được hàng null.** Dùng `IS NULL` hoặc predicate riêng; `= :param` với null không có nghĩa là `IS NULL`.

**LIKE trả kết quả rộng hơn dự kiến.** Kiểm tra wildcard `%` và `_`, escape semantics và việc chuẩn hóa chữ hoa/thường.

**Native query hoạt động trên Hibernate nhưng lỗi khi đổi provider.** Kiểm tra cú pháp placeholder và mức hỗ trợ named parameter của provider; ưu tiên positional binding portable khi cần tương thích.

**Muốn bind tên cột hoặc ORDER BY.** Parameter chỉ dành cho giá trị; dùng allow-list và cấu trúc query phù hợp cho identifier/sort.

## 13. Checklist sử dụng @Param

- Với JPQL, chọn positional `?1` hoặc named `:name`; không trộn hai kiểu trong cùng query.
- Dùng `@Param("name")` tường minh cho named parameter để tránh phụ thuộc metadata compiler.
- Bảo đảm tên `@Param` khớp chính xác placeholder.
- Kiểm tra thứ tự khi dùng positional binding; chỉ số JPQL bắt đầu từ 1.
- Xác định semantics của null, collection rỗng và wildcard LIKE.
- Dùng kiểu Java tương thích với thuộc tính Entity.
- Xử lý `Pageable`/`Sort` như special parameter, không bind chúng như giá trị query.
- Không ghép input vào tên cột, tên bảng hoặc cú pháp SQL.
- Với native query, kiểm tra cú pháp và khả năng hỗ trợ của provider/database.

Named parameter với `@Param` thường dễ đọc và ít phụ thuộc thứ tự method arguments hơn positional binding. Positional binding vẫn hữu ích cho query ngắn. Dù chọn cách nào, hãy bind giá trị đúng kiểu, định nghĩa rõ trường hợp null/rỗng và không dùng parameter để thay thế cấu trúc query.