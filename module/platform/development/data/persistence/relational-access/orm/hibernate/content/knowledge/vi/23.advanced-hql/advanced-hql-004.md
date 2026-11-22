# Các phép toán tập hợp khi phiên bản hỗ trợ

Khi truy vấn dữ liệu, đôi khi ta cần kết hợp kết quả của nhiều câu SELECT độc lập thành một tập kết quả chung. Ví dụ, một màn hình tìm kiếm cần hiển thị cả email khách hàng và email nhà cung cấp; một báo cáo cần lấy những mã sản phẩm xuất hiện trong cả hai nguồn; hoặc một quy trình cần tìm các tài khoản có trong danh sách hoạt động nhưng không nằm trong danh sách bị khóa.

SQL giải quyết nhóm nhu cầu này bằng **set operations**: `UNION`, `INTERSECT` và `EXCEPT`. Hibernate Query Language (HQL) hiện đại hỗ trợ các toán tử này, cùng các biến thể `ALL`, khi phiên bản Hibernate và database dialect phù hợp. Jakarta Persistence 3.2 cũng đưa các toán tử này vào JPQL chuẩn. Với các phiên bản JPA cũ hơn, không nên mặc định cú pháp set operation là JPQL portable.

Bài học thuộc chương **HQL nâng cao** của module *Data Persistence Relational Access ORM Hibernate*. Nội dung tập trung vào ý nghĩa tập hợp, khác biệt giữa loại bỏ và giữ bản sao, điều kiện tương thích giữa các nhánh SELECT, cách kết hợp truy vấn, giới hạn theo phiên bản và lựa chọn thay thế khi môi trường chưa hỗ trợ.

## 1. Set operation làm việc trên toàn bộ kết quả SELECT

Một câu SELECT tạo ra một result set. Set operation nhận kết quả của hai hoặc nhiều truy vấn SELECT và kết hợp chúng theo quy tắc tập hợp.

~~~text
Query A ──► Result set A ──┐
                           ├── Set operation ──► Result set cuối
Query B ──► Result set B ──┘
~~~

Ví dụ SQL:

~~~sql
SELECT email FROM customers
UNION
SELECT email FROM suppliers;
~~~

Câu lệnh trên không JOIN hai bảng theo khóa ngoại. Nó lấy các giá trị email từ hai kết quả rồi kết hợp chúng.

Trong HQL/JPQL, ta truy vấn **entity và thuộc tính Java** thay vì tên bảng/cột SQL:

~~~hql
select c.email
from Customer c
union
select s.email
from Supplier s
~~~

Các toán tử áp dụng lên **toàn bộ các hàng kết quả** của từng nhánh, không phải phép so sánh giữa hai biểu thức đơn lẻ như `=`, `IN` hay `LIKE`.

## 2. Các khái niệm cần nắm

| Khái niệm | Ý nghĩa |
| --- | --- |
| Result set | Các hàng do một truy vấn SELECT tạo ra |
| Projection | Các giá trị/cột được chọn trong mỗi hàng kết quả |
| Duplicate elimination | Loại bỏ những hàng trùng nhau theo toàn bộ projection |
| Multiplicity | Số lần một hàng xuất hiện trong kết quả |
| Set | Tập hợp không quan tâm số lần xuất hiện |
| Bag/multiset | Tập kết quả có thể chứa nhiều lần cùng một giá trị |

Một điểm quan trọng: việc xác định hai hàng trùng nhau dựa trên **toàn bộ các cột được SELECT**, không chỉ ID hoặc một cột mà lập trình viên quan tâm.

Ví dụ, hai hàng:

| email | source |
| --- | --- |
| an@example.test | CUSTOMER |
| an@example.test | SUPPLIER |

không trùng nếu truy vấn chọn cả `email` và `source`, dù email giống nhau. Nếu chỉ SELECT `email`, chúng có thể bị coi là cùng một hàng khi dùng toán tử loại trùng.

## 3. Các toán tử được hỗ trợ

HQL hiện đại và Jakarta Persistence 3.2 định nghĩa các biến thể sau:

| Toán tử | Ý nghĩa | Xử lý duplicate |
| --- | --- | --- |
| `UNION` | Hợp hai kết quả | Loại hàng trùng |
| `UNION ALL` | Hợp hai kết quả | Giữ mọi lần xuất hiện |
| `INTERSECT` | Phần giao của hai kết quả | Loại hàng trùng |
| `INTERSECT ALL` | Phần giao theo multiplicity | Giữ số lần khớp tối thiểu |
| `EXCEPT` | Hàng có ở trái nhưng không có ở phải | Loại hàng trùng |
| `EXCEPT ALL` | Hiệu theo multiplicity | Trừ số lần xuất hiện ở phải khỏi trái |

Các toán tử không có `ALL` mặc định loại bỏ bản sao. `ALL` yêu cầu giữ lại hoặc xử lý số lần xuất hiện theo quy tắc multiset.

Không nhầm `EXCEPT` với `MINUS` trong một số dialect SQL. Trong HQL/JPQL, từ khóa cho phép trừ tập hợp là `EXCEPT`.

## 4. Ví dụ dữ liệu để hình dung kết quả

Giả sử hai truy vấn cùng trả về một cột `code`.

**Kết quả A:**

| code |
| --- |
| A |
| A |
| A |
| B |
| B |
| C |

**Kết quả B:**

| code |
| --- |
| A |
| B |
| B |
| B |
| D |

Ta có thể mô tả kết quả:

| Phép toán | Kết quả | Giải thích |
| --- | --- | --- |
| A `UNION` B | A, B, C, D | Mỗi giá trị chỉ còn một lần |
| A `UNION ALL` B | A, A, A, A, B, B, B, B, C, D | Giữ tất cả lần xuất hiện |
| A `INTERSECT` B | A, B | Chỉ giữ giá trị có ở cả hai, loại duplicate |
| A `INTERSECT ALL` B | A, B, B | Số lần xuất hiện bằng min(countA, countB) |
| A `EXCEPT` B | C | Chỉ có ở A và không có ở B |
| A `EXCEPT ALL` B | A, A, C | Số lần xuất hiện bằng max(countA - countB, 0) |

Trong ví dụ:

- A có ba lần `A`, B có một lần `A`, nên `INTERSECT ALL` giữ một `A` và `EXCEPT ALL` giữ hai `A`.
- A có hai lần `B`, B có ba lần `B`, nên giao giữ hai `B` và hiệu không còn `B`.
- `C` chỉ có trong A nên nằm trong hiệu A trừ B.
- `D` chỉ có trong B nên không xuất hiện trong A trừ B.

Đây là cách tư duy quan trọng khi chọn `ALL`: **đừng chỉ hỏi giá trị nào xuất hiện, hãy hỏi mỗi giá trị được phép xuất hiện bao nhiêu lần.**

## 5. Tương thích phiên bản: HQL, JPQL và database dialect

Tên bài có cụm “khi phiên bản hỗ trợ” vì cú pháp set operation phụ thuộc nhiều tầng.

| Nền tảng | Khả năng |
| --- | --- |
| Hibernate ORM 5.x và HQL cũ | Không nên mặc định HQL hỗ trợ set operators; thường cần native SQL hoặc cách viết khác |
| Hibernate ORM 6.x | HQL hiện đại hỗ trợ UNION, INTERSECT, EXCEPT và các biến thể ALL trong các phiên bản có tài liệu tương ứng; kiểm tra đúng minor version đang dùng |
| Hibernate ORM 7.x | HQL tiếp tục hỗ trợ các set operators; API/query compiler và dialect cần tương thích |
| Jakarta Persistence 3.1 trở xuống | JPQL chuẩn chưa định nghĩa set operators; cú pháp này không portable theo chuẩn cũ |
| Jakarta Persistence 3.2 | JPQL chuẩn bổ sung UNION, UNION ALL, INTERSECT, INTERSECT ALL, EXCEPT và EXCEPT ALL; Criteria API cũng được mở rộng |
| Database/dialect | Phải hỗ trợ toán tử SQL tương ứng hoặc có khả năng dịch phù hợp |

Các tài liệu HQL của Hibernate 6.2, 6.3, 6.4, 6.5, 6.6 và 7.x mô tả set operations. Jakarta Persistence 3.2 đưa các toán tử vào ngôn ngữ truy vấn chuẩn; provider cần hỗ trợ đặc tả 3.2 để ứng dụng có tính portable theo JPQL 3.2.

### Tách biệt ba câu hỏi tương thích

Khi một query không chạy, hãy xác định:

1. **Parser/query language:** Hibernate version có hiểu cú pháp HQL/JPQL đó không?
2. **Compliance mode:** Ứng dụng có bật strict JPA query compliance khiến HQL extension bị từ chối không?
3. **Database dialect:** Dialect và database có hỗ trợ SQL operator được sinh ra không?

Ví dụ Hibernate có thể hiểu `INTERSECT ALL` ở tầng HQL nhưng database/dialect cụ thể không hỗ trợ biến thể đó. Kết quả là lỗi khi dịch SQL hoặc khi database thực thi, dù cú pháp đã được parser chấp nhận.

### Strict JPA query compliance

Hibernate có tùy chọn:

~~~properties
hibernate.jpa.compliance.query=true
~~~

Tùy chọn này yêu cầu HQL tuân thủ phần ngôn ngữ được chuẩn JPA hỗ trợ. Một extension HQL ngoài phiên bản JPA mà ứng dụng đang dùng có thể bị từ chối.

Với Hibernate kết hợp Jakarta Persistence 3.2, set operations đã thuộc JPQL chuẩn. Với stack cũ hơn dùng JPA 3.1 hoặc thấp hơn, không nên giả định set operations là portable chỉ vì một phiên bản Hibernate cụ thể có thể chấp nhận HQL extension.

**Hãy đối chiếu phiên bản Hibernate, API Jakarta Persistence, cấu hình compliance và dialect thực tế.** Không nâng cấp riêng dependency API mà bỏ qua provider hoặc database.

## 6. Điều kiện để ghép hai truy vấn

Các nhánh SELECT phải có cấu trúc kết quả tương thích.

Theo Jakarta Persistence 3.2, provider bắt buộc hỗ trợ trường hợp:

- Các nhánh có cùng số lượng select item.
- Các item tương ứng có cùng kiểu theo quy tắc đặc tả; hoặc
- Các item là entity type có chung một entity type cha trong hierarchy.

Ví dụ hợp lệ về số lượng và kiểu:

~~~jpql
select c.email
from Customer c
union
select s.email
from Supplier s
~~~

Hai nhánh cùng trả một giá trị kiểu String.

Ví dụ không tương thích:

~~~jpql
select c.email, c.displayName
from Customer c
union
select s.email
from Supplier s
~~~

Nhánh đầu trả hai cột, nhánh thứ hai chỉ trả một cột.

Ví dụ khác có thể không tương thích:

~~~jpql
select c.email
from Customer c
union
select p.createdAt
from PurchaseOrder p
~~~

Một nhánh trả String, nhánh kia trả LocalDateTime. Dù database có thể ép kiểu trong một số câu SQL, query language cần kiểm tra type compatibility theo quy tắc JPA/Hibernate.

### Số lượng cột và thứ tự cột đều quan trọng

Giả sử:

~~~jpql
select c.id, c.email
from Customer c
union
select s.id, s.email
from Supplier s
~~~

Hai nhánh có cùng arity và cùng kiểu tương ứng. Nhưng nếu đảo thứ tự:

~~~jpql
select c.id, c.email
from Customer c
union
select s.email, s.id
from Supplier s
~~~

thì vị trí thứ nhất và thứ hai không còn tương thích. Set operation ghép các cột **theo vị trí**, không ghép theo tên alias.

### Alias không thay thế type compatibility

Alias giúp đặt tên cho projection/order by, nhưng không thể làm hai kiểu dữ liệu khác nhau trở nên tương thích. Hãy thiết kế select list có cùng ý nghĩa, thứ tự và kiểu trước khi thêm alias.

## 7. UNION: hợp kết quả và loại duplicate

Một màn hình cần danh sách email của khách hàng active và nhà cung cấp được phê duyệt. Hai loại entity nằm ở hai bảng khác nhau nhưng đều có thuộc tính email kiểu String.

~~~java
List<String> emails = em.createQuery(
    """
    select c.email
    from Customer c
    where c.active = true

    union

    select s.email
    from Supplier s
    where s.approved = true
    """,
    String.class
).getResultList();
~~~

Nếu `an@example.test` xuất hiện ở cả hai nhánh, `UNION` chỉ trả một giá trị email trong kết quả.

SQL được dịch có thể tương đương:

~~~sql
SELECT c.email
FROM customers c
WHERE c.active = true

UNION

SELECT s.email
FROM suppliers s
WHERE s.approved = true;
~~~

Database thường phải thực hiện thao tác loại trùng, ví dụ sort hoặc hash aggregate. Vì vậy `UNION` có thể tốn tài nguyên hơn `UNION ALL`.

### Khi nào UNION phù hợp?

- Nhiều nguồn dữ liệu có cùng cấu trúc projection.
- Kết quả nghiệp vụ cần danh sách giá trị duy nhất.
- Cần hợp các nhánh SELECT độc lập mà không muốn viết logic ghép và loại trùng ở Java.
- Có thể để database xử lý set semantics trên dữ liệu lớn.

Nếu nghiệp vụ muốn mỗi nguồn đóng góp một bản ghi riêng dù email giống nhau, UNION không phù hợp; hãy dùng UNION ALL.

## 8. UNION ALL: giữ mọi lần xuất hiện

Giả sử báo cáo cần đếm tất cả lượt phát sinh email trong hai nguồn, không loại bỏ bản sao:

~~~java
List<String> allEmails = em.createQuery(
    """
    select c.email
    from Customer c
    where c.createdAt >= :fromTime

    union all

    select s.email
    from Supplier s
    where s.createdAt >= :fromTime
    """,
    String.class
)
.setParameter("fromTime", fromTime)
.getResultList();
~~~

Nếu cùng email xuất hiện trong cả hai bảng, kết quả có thể chứa email đó hai lần.

### Vì sao UNION ALL thường nhanh hơn UNION?

`UNION ALL` không yêu cầu loại trùng toàn bộ kết quả. Database có thể nối kết quả của các nhánh mà không cần bước distinct toàn cục.

Nếu ứng dụng sau đó chỉ cần đếm, UNION ALL giữ đúng số lần xuất hiện. Nếu dùng UNION, số lượng sẽ giảm khi có duplicate, làm thay đổi ý nghĩa thống kê.

**Đừng dùng UNION mặc định theo thói quen.** Chọn toán tử dựa trên việc duplicate có mang ý nghĩa nghiệp vụ hay không.

## 9. INTERSECT: tìm phần chung

Giả sử ứng dụng có hai nguồn:

- Customer có đăng ký nhận bản tin.
- Contact nằm trong danh sách marketing được phép gửi.

Muốn tìm email xuất hiện ở cả hai nguồn:

~~~java
List<String> eligibleEmails = em.createQuery(
    """
    select c.email
    from Customer c
    where c.active = true

    intersect

    select m.email
    from MarketingContact m
    where m.consentGranted = true
    """,
    String.class
).getResultList();
~~~

`INTERSECT` chỉ trả những giá trị có trong cả hai kết quả và loại duplicate.

~~~text
Customer emails:  an@x.test, binh@x.test, chi@x.test
Marketing list:   an@x.test, chi@x.test, dung@x.test

INTERSECT:
                  an@x.test, chi@x.test
~~~

### INTERSECT khác JOIN thế nào?

JOIN kết hợp hàng dựa trên điều kiện liên kết giữa các nguồn. INTERSECT so sánh toàn bộ projection của hai result set theo semantics tập hợp.

Nếu chỉ cần xác định entity Customer có ít nhất một dòng liên quan thỏa điều kiện, `EXISTS` hoặc JOIN có thể phù hợp hơn. INTERSECT hữu ích khi bản thân hai kết quả độc lập cần so sánh theo set semantics.

## 10. INTERSECT ALL: giao theo số lần xuất hiện

`INTERSECT ALL` giữ multiplicity bằng số lần xuất hiện ít hơn giữa hai nhánh.

~~~text
A = [A, A, A, B, B, C]
B = [A, B, B, B, D]

A INTERSECT ALL B = [A, B, B]
~~~

Số lần của mỗi giá trị trong kết quả:

~~~text
count(result, x) = min(count(A, x), count(B, x))
~~~

Dùng khi duplicate có ý nghĩa và cần giữ số lần khớp. Ví dụ một báo cáo đối soát hai nguồn có nhiều dòng giống nhau, và số lần xuất hiện là dữ liệu cần so sánh.

Không phải mọi database dialect đều hỗ trợ `INTERSECT ALL`. Hãy kiểm tra khả năng của database/version cụ thể; nếu không có, cần thiết kế query thay thế hoặc xử lý dữ liệu trong một quy trình phù hợp.

## 11. EXCEPT: lấy phần có ở trái nhưng không có ở phải

Một hệ thống có danh sách khách hàng active và danh sách email bị chặn. Muốn tìm email active không xuất hiện trong danh sách block:

~~~java
List<String> allowedEmails = em.createQuery(
    """
    select c.email
    from Customer c
    where c.active = true

    except

    select b.email
    from BlockedEmail b
    """,
    String.class
).getResultList();
~~~

`EXCEPT` có hướng: kết quả là **nhánh trái trừ nhánh phải**.

~~~text
Active:   an@x.test, binh@x.test, chi@x.test
Blocked:  binh@x.test, dung@x.test

Active EXCEPT Blocked:
          an@x.test, chi@x.test
~~~

Đảo hai nhánh sẽ cho kết quả khác:

~~~text
Blocked EXCEPT Active:
  dung@x.test
~~~

### EXCEPT khác NOT IN/NOT EXISTS thế nào?

`EXCEPT` làm việc trên toàn bộ result set và áp dụng duplicate semantics. `NOT EXISTS` hoặc `NOT IN` là predicate trong một query.

Nếu hai nhánh chỉ so sánh một key, NOT EXISTS thường có thể diễn đạt tương đương về membership và dễ kết hợp với entity root. Nhưng phải chú ý:

- `NOT IN` có thể có kết quả bất ngờ khi subquery chứa NULL.
- `NOT EXISTS` thường dễ kiểm soát null semantics hơn.
- EXCEPT loại duplicate theo mặc định; query entity/projection có thể giữ multiplicity khác nếu dùng ALL.
- Kế hoạch thực thi và index có thể khác nhau.

Không thay EXCEPT bằng NOT IN một cách máy móc nếu cột so sánh có thể NULL.

## 12. EXCEPT ALL: trừ multiplicity

`EXCEPT ALL` giữ những lần xuất hiện còn lại ở nhánh trái sau khi trừ số lần có ở nhánh phải:

~~~text
A = [A, A, A, B, B, C]
B = [A, B, B, B, D]

A EXCEPT ALL B = [A, A, C]
~~~

Quy tắc:

~~~text
count(result, x) = max(count(A, x) - count(B, x), 0)
~~~

Ví dụ này khác `EXCEPT`:

- `EXCEPT` chỉ quan tâm A có ở bên trái và không có bên phải hay không, nên kết quả là C.
- `EXCEPT ALL` còn quan tâm số lần xuất hiện, nên hai bản sao A vẫn còn sau khi trừ một bản sao A ở bên phải.

`EXCEPT ALL` cũng phụ thuộc khả năng hỗ trợ của database dialect.

## 13. Hợp ba hoặc nhiều nhánh

Set operation có thể kết hợp nhiều truy vấn:

~~~java
List<String> contacts = em.createQuery(
    """
    select c.email from Customer c where c.active = true
    union
    select s.email from Supplier s where s.approved = true
    union
    select p.email from Partner p where p.enabled = true
    """,
    String.class
).getResultList();
~~~

Kết quả là tập email duy nhất từ ba nguồn.

Nếu cần giữ duplicate từ mọi nguồn:

~~~hql
select c.email from Customer c
union all
select s.email from Supplier s
union all
select p.email from Partner p
~~~

Khi ghép nhiều nhánh, hãy kiểm tra:

- Tất cả select list có cùng số item không?
- Kiểu tương ứng có tương thích không?
- Mỗi nhánh có điều kiện lọc đúng không?
- Duplicate có cần giữ không?
- Có cần ngoặc để thể hiện thứ tự kết hợp không?
- Có cần ORDER BY ở kết quả cuối không?

Không dựa vào thứ tự vật lý mà database trả kết quả nếu query không có ORDER BY.

## 14. Hợp các nhánh có cùng entity type

Set operation cũng có thể trả entity thay vì scalar, khi các nhánh select entity có type tương thích.

~~~java
List<Customer> customers = em.createQuery(
    """
    select c
    from Customer c
    where c.active = true

    union

    select c
    from Customer c
    where c.vip = true
    """,
    Customer.class
).getResultList();
~~~

Một khách hàng vừa active vừa VIP có thể thỏa cả hai nhánh, nhưng `UNION` loại duplicate entity result theo set semantics.

Trong persistence context, entity trả về vẫn chịu quy tắc identity của JPA/Hibernate. Tuy nhiên, khi mục tiêu là hợp các tập ID hoặc tạo báo cáo, projection scalar/DTO thường dễ kiểm soát hơn việc hợp entity graph.

Jakarta Persistence 3.2 cho phép provider hỗ trợ các nhánh trả entity type có chung entity type cha trong hierarchy, nếu đáp ứng điều kiện đặc tả. Điều đó không có nghĩa mọi hai entity bất kỳ đều có thể UNION.

Hãy xác định rõ:

- Các entity có chung mapped entity superclass/root entity phù hợp không?
- Result type cuối là entity type nào?
- Provider/version đang dùng có hỗ trợ cách projection đó không?
- Database mapping/inheritance strategy có thể dịch query không?

Nếu không chắc, hãy trả về DTO với các cột chung như ID, loại đối tượng và tên hiển thị.

### Entity result có tự động fetch association không?

Không. Set operation chỉ kết hợp result set. Association của entity trả về vẫn tuân theo fetch mapping, entity graph và query fetch plan. Không nhầm UNION entity với JOIN FETCH association.

## 15. Ghép dữ liệu khác entity thành một DTO chung

Một use case thường gặp là tìm cả Customer và Supplier theo tên. Hai entity có các trường khác nhau nhưng cùng cần hiển thị trong một danh sách kết quả.

~~~java
public record ContactRow(
    String sourceType,
    Long sourceId,
    String displayName,
    String email
) {
}
~~~

JPQL 3.2/HQL có thể biểu diễn projection cùng cấu trúc:

~~~java
List<Object[]> rows = em.createQuery(
    """
    select 'CUSTOMER', c.id, c.displayName, c.email
    from Customer c
    where c.active = true

    union all

    select 'SUPPLIER', s.id, s.displayName, s.email
    from Supplier s
    where s.approved = true
    """,
    Object[].class
).getResultList();
~~~

Mỗi hàng có bốn cột với kiểu tương ứng giống nhau: String, Long, String, String. Map từng hàng sang DTO bằng code Java rõ ràng.

Một số provider/version hỗ trợ constructor expression trong từng nhánh set query; nhưng nếu cần portable và dễ kiểm soát type, scalar projection cùng arity thường đơn giản hơn. Hãy xác nhận constructor expression trên stack đang dùng trước khi dựa vào nó.

## 16. Parameter trong nhiều nhánh

Named parameter giúp tránh ghép chuỗi đầu vào trực tiếp vào query.

~~~java
List<String> emails = em.createQuery(
    """
    select c.email
    from Customer c
    where c.createdAt >= :cutoff

    union

    select s.email
    from Supplier s
    where s.createdAt >= :cutoff
    """,
    String.class
)
.setParameter("cutoff", cutoff)
.getResultList();
~~~

Cùng một named parameter được dùng ở hai nhánh và bind một giá trị chung.

Nếu mỗi nhánh có điều kiện riêng:

~~~java
List<String> results = em.createQuery(
    """
    select c.email
    from Customer c
    where c.region = :customerRegion

    union

    select s.email
    from Supplier s
    where s.country = :supplierCountry
    """,
    String.class
)
.setParameter("customerRegion", region)
.setParameter("supplierCountry", country)
.getResultList();
~~~

Không nối dữ liệu người dùng trực tiếp vào query string. Cần đặt parameter có tên rõ ràng và type phù hợp với các biểu thức trong từng nhánh.

## 17. ORDER BY áp dụng cho kết quả chung

Một set result không có thứ tự mặc định. Nếu muốn sắp xếp danh sách hợp nhất, hãy đặt ORDER BY cho query expression cuối:

~~~java
List<String> emails = em.createQuery(
    """
    select c.email as address
    from Customer c
    where c.active = true

    union

    select s.email as address
    from Supplier s
    where s.approved = true

    order by address
    """,
    String.class
).getResultList();
~~~

ORDER BY cuối sắp xếp tập kết quả đã hợp nhất. Không nên cho rằng thứ tự các nhánh SELECT quyết định thứ tự output.

Một số database yêu cầu sort expression của query có set operation phải tham chiếu select item hoặc alias được chọn. Để portable hơn:

- Dùng alias cho các projection.
- Chỉ sort theo cột đã được chọn nếu database yêu cầu.
- Tránh tham chiếu một biểu thức chỉ tồn tại trong một nhánh.
- Kiểm tra SQL mà Hibernate sinh ra trên dialect thực tế.

### ORDER BY trong từng nhánh

Nếu cần giới hạn hoặc sắp xếp riêng một nhánh trước khi hợp, cú pháp thường cần ngoặc và support từ query language/dialect. Không phải database nào cũng cho phép ORDER BY/LIMIT tùy ý bên trong mỗi operand của set operation.

Thông thường, hãy lọc trong từng nhánh bằng WHERE/GROUP BY, sau đó ORDER BY một lần ở cuối. Nếu cần top-N riêng cho từng nhánh, dùng derived query/CTE/subquery khi Hibernate và dialect hỗ trợ, hoặc tách thành truy vấn riêng.

## 18. LIMIT/OFFSET và phân trang kết quả hợp nhất

Sau khi hợp các nhánh, có thể cần phân trang:

~~~java
List<String> page = em.createQuery(
    """
    select c.email as address
    from Customer c
    where c.active = true

    union

    select s.email as address
    from Supplier s
    where s.approved = true

    order by address
    """,
    String.class
)
.setFirstResult(0)
.setMaxResults(50)
.getResultList();
~~~

`setFirstResult` và `setMaxResults` áp dụng cho kết quả cuối của query. Cần có ORDER BY ổn định nếu muốn trang kế tiếp không bị xáo trộn giữa các lần chạy.

Với offset pagination, nếu dữ liệu thay đổi giữa các request, bản ghi có thể dịch chuyển giữa các trang. Với tập kết quả lớn, keyset pagination hoặc chiến lược phân trang riêng có thể phù hợp hơn.

Nếu một query branch cần giới hạn riêng trước UNION, đừng đặt `setMaxResults` trên toàn Query Java rồi nghĩ rằng nó áp dụng riêng từng nhánh; nó giới hạn result set cuối.

## 19. Thứ tự ưu tiên và dấu ngoặc

Khi ghép nhiều toán tử, thứ tự đánh giá có thể ảnh hưởng kết quả. Theo ngữ nghĩa SQL và Jakarta Persistence 3.2:

- `INTERSECT` và `INTERSECT ALL` có độ ưu tiên cao hơn `UNION`, `UNION ALL`, `EXCEPT` và `EXCEPT ALL`.
- `UNION` và `EXCEPT` cùng nhóm ưu tiên và kết hợp từ trái sang phải.
- Ngoặc làm rõ nhóm kết quả cần xử lý trước.

Ví dụ:

~~~sql
A UNION B INTERSECT C
~~~

được hiểu theo precedence là:

~~~text
A UNION (B INTERSECT C)
~~~

Không nên dựa vào trí nhớ khi query dài. Viết rõ nhóm cần tính trước:

~~~hql
select x.code from SourceA x
union
(
    select y.code from SourceB y
    intersect
    select z.code from SourceC z
)
~~~

Cú pháp ngoặc cho từng operand phải phù hợp parser/dialect. Khi cần portable, hãy kiểm tra query trên đúng phiên bản Hibernate/JPA.

Ví dụ khác:

~~~text
(A UNION B) EXCEPT C
~~~

và:

~~~text
A UNION (B EXCEPT C)
~~~

không nhất thiết trả cùng kết quả. Hãy dùng ngoặc để thể hiện ý nghĩa nghiệp vụ thay vì để precedence mặc định quyết định hộ.

## 20. NULL và duplicate elimination

Trong SQL, `NULL` không bằng một giá trị thông thường theo phép so sánh `=`. Tuy nhiên, duplicate elimination của set operation sử dụng quy tắc so sánh hàng của SQL, trong đó các hàng có NULL ở cùng vị trí có thể được coi là trùng để loại duplicate.

Ví dụ:

~~~text
A = [NULL, NULL, "x"]
B = [NULL, "y"]

A UNION B
  → [NULL, "x", "y"]  (theo semantics set)
~~~

Với INTERSECT và EXCEPT, NULL cũng tham gia theo quy tắc set comparison của database.

Điều này khác với predicate:

~~~sql
WHERE email = NULL
~~~

Predicate trên không đúng cách; phải dùng `IS NULL`. Đừng dùng quy tắc NULL của WHERE để suy luận trực tiếp cách database loại duplicate trong UNION/INTERSECT/EXCEPT.

Nếu kết quả cần phân biệt hai nguồn có email NULL, hãy thêm source discriminator vào projection. Khi đó hai hàng có source khác nhau không còn trùng theo toàn bộ select list.

## 21. DISTINCT trong nhánh và set operator

Có thể viết:

~~~hql
select distinct c.email
from Customer c
union
select distinct s.email
from Supplier s
~~~

Nhưng `UNION` vốn đã loại duplicate trên kết quả chung. DISTINCT riêng trong từng nhánh có thể dư thừa nếu mục tiêu duy nhất là loại duplicate cuối cùng.

Ngược lại:

~~~hql
select distinct c.email
from Customer c
union all
select distinct s.email
from Supplier s
~~~

vẫn giữ một bản sao email từ Customer và một bản sao từ Supplier nếu chúng giống nhau. DISTINCT chỉ loại trùng **trong mỗi nhánh**, còn UNION ALL giữ kết quả của các nhánh.

Hãy xác định phạm vi duplicate cần loại:

- Duplicate trong từng nguồn?
- Duplicate giữa các nguồn?
- Duplicate toàn bộ sau khi hợp?
- Hay cần giữ đầy đủ multiplicity?

Chọn DISTINCT/UNION/UNION ALL theo đúng câu trả lời.

## 22. Criteria API trong Jakarta Persistence 3.2

Jakarta Persistence 3.2 mở rộng Criteria API để biểu diễn set operations, bên cạnh cú pháp JPQL dạng chuỗi. Các API set query phụ thuộc type và interface của phiên bản 3.2; không nên copy một ví dụ Criteria từ Hibernate-specific API rồi coi là tương thích với mọi JPA version.

Nguyên tắc thiết kế vẫn giống JPQL:

- Mỗi query operand có select list tương thích.
- Các select item tương ứng có kiểu tương thích.
- Dùng `union`, `intersect` hoặc `except` theo semantics cần thiết.
- Chọn biến thể ALL khi cần giữ multiplicity.
- Áp dụng ordering/limit theo API/provider hỗ trợ.

Nếu dự án dùng Jakarta Persistence 3.1, các phương thức Criteria set operations của 3.2 không có sẵn. Khi nâng cấp, cần đồng bộ version API và implementation/provider.

Với query tĩnh, JPQL dễ đọc hơn. Criteria phù hợp khi query được xây dựng động từ nhiều điều kiện và ứng dụng cần type-safe construction. Không cần chuyển một query đơn giản thành Criteria chỉ để dùng một toán tử.

## 23. Database dialect có thể giới hạn set operator

Hibernate dịch HQL/JPQL sang SQL theo dialect. Khả năng hỗ trợ không chỉ phụ thuộc parser.

Các khác biệt thường gặp:

- Database hỗ trợ `UNION` và `UNION ALL` nhưng chưa hỗ trợ `INTERSECT ALL`.
- Database hỗ trợ `INTERSECT`/`EXCEPT` nhưng không có biến thể ALL.
- Set operator được hỗ trợ ở top-level nhưng hạn chế trong subquery/CTE.
- Cú pháp giới hạn/sắp xếp trong từng nhánh khác nhau.
- Một số dialect cần cast tường minh để các nhánh có cùng SQL type.
- Hibernate dialect có thể có phương thức mô tả hỗ trợ operator hoặc render SQL khác biệt.

Mô hình thực thi:

~~~text
HQL / JPQL
    ↓ parser + type checking
Hibernate query model
    ↓ SQL translation theo Dialect
SQL UNION / INTERSECT / EXCEPT
    ↓
Database version
~~~

Nếu database không hỗ trợ toán tử cần dùng, có thể gặp lỗi khi Hibernate dịch hoặc khi gửi SQL tới server. Hãy kiểm tra tài liệu dialect và database version; đừng giả định một query chạy được trên PostgreSQL sẽ chạy nguyên trạng trên mọi database.

### Cần test gì khi đổi database?

- Parser HQL/JPQL có chấp nhận query không?
- SQL được sinh có đúng toán tử không?
- Mỗi nhánh có cùng SQL type không?
- ORDER BY, LIMIT/OFFSET và ngoặc có đúng dialect không?
- Duplicate semantics có giống yêu cầu nghiệp vụ không?
- Query plan có dùng index/strategy hợp lý không?

## 24. Dùng HQL/JPQL qua EntityManager

Ví dụ thực thi UNION:

~~~java
TypedQuery<String> query = em.createQuery(
    """
    select c.email from Customer c where c.active = true
    union
    select s.email from Supplier s where s.approved = true
    """,
    String.class
);

List<String> result = query.getResultList();
~~~

Có thể bind parameter như các query JPQL thông thường:

~~~java
TypedQuery<String> query = em.createQuery(
    """
    select c.email from Customer c where c.createdAt >= :start
    union all
    select s.email from Supplier s where s.createdAt >= :start
    """,
    String.class
);

query.setParameter("start", start);
List<String> result = query.getResultList();
~~~

Dùng `TypedQuery<T>` để chỉ định kiểu projection khi select list có một item. Với nhiều select item, có thể dùng `Object[]` hoặc `Tuple`, tùy cấu trúc kết quả và provider.

### Dùng Hibernate Session

~~~java
List<String> result = session.createQuery(
    """
    select c.email from Customer c where c.active = true
    union
    select s.email from Supplier s where s.approved = true
    """,
    String.class
).getResultList();
~~~

Session API cũng sử dụng HQL query parser/translator. Khác biệt về method API không làm thay đổi semantics set operator.

## 25. Khi phiên bản chưa hỗ trợ: lựa chọn thay thế

Nếu stack dùng JPA cũ hoặc Hibernate HQL chưa hỗ trợ, có một số cách.

### Cách A — Hai truy vấn và ghép trong Java

~~~java
List<String> customerEmails = em.createQuery(
    "select c.email from Customer c where c.active = true",
    String.class
).getResultList();

List<String> supplierEmails = em.createQuery(
    "select s.email from Supplier s where s.approved = true",
    String.class
).getResultList();

List<String> combined = new ArrayList<>(customerEmails);
combined.addAll(supplierEmails);
~~~

Cách này tương đương ý tưởng UNION ALL về việc giữ bản sao. Nếu cần semantics UNION, dùng một cấu trúc loại duplicate có thứ tự phù hợp:

~~~java
Set<String> unique = new LinkedHashSet<>(customerEmails);
unique.addAll(supplierEmails);

List<String> combinedDistinct = new ArrayList<>(unique);
~~~

Lưu ý hai truy vấn có thể đọc dữ liệu ở hai thời điểm khác nhau nếu không có transaction/isolation phù hợp. Việc ghép ở Java cũng kéo dữ liệu qua network và tốn bộ nhớ; không thích hợp cho tập kết quả rất lớn.

### Cách B — Native SQL

Nếu database hỗ trợ set operators nhưng JPQL/provider version chưa có:

~~~java
@SuppressWarnings("unchecked")
List<String> emails = em.createNativeQuery(
    """
    SELECT email FROM customers WHERE active = true
    UNION
    SELECT email FROM suppliers WHERE approved = true
    """
).getResultList();
~~~

Native SQL dùng tên bảng/cột thật, phụ thuộc schema và dialect. Nếu kết quả là entity hoặc DTO, cần result mapping phù hợp; ví dụ trên chỉ trả scalar email.

### Cách C — OR predicate khi hai nhánh cùng một nguồn

Nếu hai nhánh đều truy vấn cùng entity/table và projection giống nhau:

~~~jpql
select c.email
from Customer c
where c.active = true or c.vip = true
~~~

có thể thay cho:

~~~jpql
select c.email from Customer c where c.active = true
union
select c.email from Customer c where c.vip = true
~~~

Nhưng cần chú ý semantics: OR trả một hàng cho mỗi hàng nguồn thỏa predicate, còn UNION loại duplicate trên projection. Nếu nhiều entity có cùng email, kết quả hai cách có thể khác nhau.

### Cách D — EXISTS / NOT EXISTS cho membership

INTERSECT có thể được diễn đạt bằng EXISTS trong một số bài toán:

~~~jpql
select c.email
from Customer c
where exists (
    select m.id
    from MarketingContact m
    where m.email = c.email
)
~~~

EXCEPT có thể dùng NOT EXISTS:

~~~jpql
select c.email
from Customer c
where not exists (
    select b.id
    from BlockedEmail b
    where b.email = c.email
)
~~~

Các cách này hữu ích khi muốn lấy entity/scalar từ một nguồn và kiểm tra sự hiện diện ở nguồn khác. Nhưng chúng không tự động tương đương mọi UNION/INTERSECT/EXCEPT, đặc biệt khi duplicate multiplicity là yêu cầu. Hãy so sánh semantics trước khi thay thế.

## 26. Hiệu năng: UNION hay UNION ALL?

`UNION` phải loại duplicate. Database có thể dùng sort, hash hoặc chiến lược khác. `UNION ALL` có thể tránh bước loại duplicate, nên thường ít tốn tài nguyên hơn.

Nhưng tốc độ phụ thuộc:

- Số hàng của từng nhánh.
- Số cột và kích thước dữ liệu projection.
- Index và điều kiện WHERE.
- Database optimizer.
- Khả năng song song hóa.
- Cardinality và phân bố duplicate.
- Việc set operation nằm trong subquery hay CTE.
- Kết quả có cần sort hoặc paginate không.

Một cách tối ưu phổ biến là chỉ SELECT những cột cần so sánh. Nếu cần hợp email, đừng lấy toàn bộ entity có hàng chục cột chỉ để sau đó đọc field email.

### Đừng loại duplicate quá sớm

Nếu kết quả cần giữ số lượt phát sinh, UNION có thể làm sai báo cáo. Ngược lại, nếu UI cần danh sách email duy nhất, UNION ALL sẽ làm người dùng thấy nhiều bản sao không mong muốn.

Hiệu năng phải theo sau **đúng semantics**. Đừng chọn ALL chỉ vì nhanh hơn nếu yêu cầu cần loại duplicate.

## 27. Kết hợp set operation với pagination và count

Khi phân trang kết quả hợp nhất, cần đếm theo đúng semantics cuối cùng:

~~~hql
select c.email from Customer c
union
select s.email from Supplier s
order by 1
~~~

Nếu cần tổng số hàng sau khi loại duplicate, count của từng nhánh rồi cộng lại **không tương đương** count của UNION:

~~~text
count(A UNION B) != count(A) + count(B)
~~~

vì các giá trị trùng giữa hai nhánh chỉ tính một lần.

Với UNION ALL, nếu không có giới hạn/điều kiện phức tạp, tổng số hàng bằng tổng multiplicity của các nhánh. Với INTERSECT/EXCEPT, count cần tuân thủ quy tắc giao/trừ.

Một query count trên set expression có thể cần derived table/CTE và support của Hibernate/dialect. Nếu query quá phức tạp, cân nhắc một native SQL hoặc thiết kế báo cáo riêng thay vì viết count sai semantics.

## 28. Set operation không phải JOIN

Hai cơ chế thường bị nhầm vì đều kết hợp dữ liệu.

| Đặc điểm | JOIN | Set operation |
| --- | --- | --- |
| Kết hợp theo | Điều kiện liên hệ giữa hàng | Kết quả của nhiều SELECT |
| Cấu trúc hàng | Có thể tạo thêm cột từ nhiều bảng | Các nhánh phải có select list tương thích |
| Ví dụ | Order JOIN Customer theo customer_id | Email Customer UNION email Supplier |
| Dùng cho | Object graph, liên kết quan hệ, lọc | Hợp/giao/trừ các result set |
| Duplicate | Có thể nhân hàng do cardinality join | Theo quy tắc set/bag operator |
| Điều kiện | ON/WHERE và association | Điều kiện riêng trong từng nhánh |

Nếu hai bảng có quan hệ FK và mục tiêu là lấy tên khách hàng cùng đơn hàng, JOIN thường phù hợp. Nếu muốn hợp danh sách mã từ hai bảng độc lập, set operation phù hợp hơn.

## 29. Các lỗi thường gặp

| Lỗi hoặc kết quả bất ngờ | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query báo parser error tại UNION | Hibernate/JPQL version chưa hỗ trợ hoặc strict compliance | Kiểm tra Hibernate, Jakarta Persistence và compliance setting |
| Query parse được nhưng database báo syntax error | Dialect/database không hỗ trợ operator | Kiểm tra database version và dialect |
| UNION trả ít hàng hơn dự kiến | UNION loại duplicate | Dùng UNION ALL nếu cần giữ multiplicity |
| UNION ALL trả nhiều hàng lặp | ALL giữ mọi lần xuất hiện | Dùng UNION nếu cần tập giá trị duy nhất |
| Nhánh SELECT không tương thích | Khác số cột hoặc kiểu tương ứng | Chuẩn hóa projection và thứ tự item |
| Hợp entity type báo lỗi | Entity không có common compatible type | Dùng scalar/DTO projection hoặc cùng entity type |
| EXCEPT cho kết quả ngược kỳ vọng | Đảo vị trí trái/phải | Nhớ EXCEPT là trái trừ phải |
| INTERSECT ALL không chạy | Dialect không hỗ trợ biến thể ALL | Dùng fallback hoặc query khác |
| ORDER BY lỗi | Sort item không hợp lệ sau set operation | Dùng select alias/cột được chọn và sort cuối |
| Kết quả không ổn định thứ tự | Không có ORDER BY | Thêm ORDER BY phù hợp |
| Count sai | Cộng count từng nhánh thay vì count set cuối | Đếm trên query expression sau khi áp dụng set semantics |
| OR thay UNION nhưng duplicate khác | Khác semantics loại duplicate | So sánh projection và multiplicity |
| NOT IN bỏ mất hàng vì NULL | Subquery có NULL | Cân nhắc NOT EXISTS |
| Query chậm sau UNION | Sort/hash loại duplicate hoặc projection quá rộng | Xem execution plan, giảm cột, cân nhắc ALL nếu đúng nghiệp vụ |
| Native query chạy nhưng entity state không phù hợp | Mapping result hoặc persistence context không đồng bộ | Dùng scalar mapping/refresh/clear theo tình huống |

## 30. Quy trình chẩn đoán query set operation

~~~mermaid
flowchart TD
    A["Viết query có UNION / INTERSECT / EXCEPT"] --> B{"Hibernate / JPQL version hỗ trợ?"}
    B -- "Không" --> C["Native SQL, query riêng hoặc EXISTS/OR phù hợp"]
    B -- "Có" --> D{"Strict JPA compliance có cho phép?"}
    D -- "Không" --> C
    D -- "Có" --> E{"Các nhánh cùng số cột và kiểu tương thích?"}
    E -- "Không" --> F["Chuẩn hóa projection / cast hợp lệ"]
    E -- "Có" --> G{"Dialect và database hỗ trợ operator?"}
    G -- "Không" --> C
    G -- "Có" --> H["Bind parameter, ORDER BY, pagination"]
    H --> I["Kiểm tra SQL, kết quả và execution plan"]
~~~

Khi lỗi, phân biệt lỗi parser, lỗi type checking và lỗi SQL database. Chúng xuất hiện ở những tầng khác nhau và cần cách sửa khác nhau.

## 31. Bài tập tình huống

**Bài 1 — Hai nguồn email.** Customer và Supplier đều có email kiểu String. Muốn lấy email duy nhất từ hai nguồn. Chọn toán tử nào?

**Đáp án:** `UNION`, vì duplicate giữa hai nhánh phải được loại bỏ.

**Bài 2 — Báo cáo số lượt đăng ký.** Một email có thể xuất hiện nhiều lần và mỗi lần đều cần được tính. Chọn gì?

**Đáp án:** `UNION ALL`, vì multiplicity mang ý nghĩa thống kê.

**Bài 3 — Hai danh sách người dùng.** Muốn tìm email có trong cả danh sách active và danh sách được cấp quyền. Chọn gì?

**Đáp án:** `INTERSECT` nếu cần các giá trị chung duy nhất; `INTERSECT ALL` nếu cần giữ multiplicity theo số lần xuất hiện.

**Bài 4 — Khách hàng không nằm trong danh sách block.** Dùng phép nào?

**Đáp án:** `CustomerEmails EXCEPT BlockedEmails`. Vị trí hai nhánh rất quan trọng.

**Bài 5 — Hai nhánh trả String và LocalDateTime.** Có thể UNION trực tiếp không?

**Đáp án:** Không nên. Các select item tương ứng cần kiểu tương thích; chuẩn hóa projection/cast theo quy tắc provider và database.

**Bài 6 — Một nhánh trả hai cột, nhánh còn lại một cột.** Có thể ghép không?

**Đáp án:** Không. Các nhánh phải có cùng số select item.

**Bài 7 — Hibernate 6.x chạy UNION nhưng JPA 3.1 compliance mode từ chối. Vì sao?

**Đáp án:** Hibernate HQL có thể hỗ trợ extension ngoài JPQL cũ; strict compliance giới hạn query theo chuẩn JPA mà ứng dụng đang dùng. JPA 3.2 đưa set operators vào chuẩn.

**Bài 8 — UNION ALL chạy nhưng INTERSECT ALL lỗi trên database. Vì sao?

**Đáp án:** Database/dialect có thể hỗ trợ một biến thể nhưng không hỗ trợ biến thể khác. Kiểm tra support của operator cụ thể.

**Bài 9 — Muốn lấy customer active hoặc VIP. Có cần UNION không?

**Đáp án:** Nếu cùng entity/table và projection giống nhau, một WHERE với OR thường đơn giản hơn. Nhưng phải so sánh duplicate semantics nếu projection không unique.

**Bài 10 — EXCEPT trả kết quả khác NOT IN. Có thể do đâu?

**Đáp án:** NULL và duplicate semantics. NOT IN có thể chịu ảnh hưởng của NULL trong subquery; hãy xem xét NOT EXISTS và kiểm tra tập giá trị.

**Bài 11 — Đã UNION nhưng thứ tự không đúng.**

**Đáp án:** Set result không có thứ tự mặc định. Thêm ORDER BY ở query expression cuối.

**Bài 12 — Đếm số hàng bằng cách cộng count của hai nhánh UNION.**

**Đáp án:** Sai nếu hai nhánh có duplicate. Cần đếm kết quả UNION cuối sau khi loại trùng.

**Bài 13 — Ghép Customer và Supplier thành một danh sách entity chung.**

**Đáp án:** Chỉ khi hai entity có kiểu tương thích/common entity type theo mapping và provider. Nếu không, chọn projection DTO với các cột chung.

**Bài 14 — JPA 3.1 chưa hỗ trợ set operations portable.**

**Đáp án:** Dùng native SQL nếu database hỗ trợ, hai truy vấn ghép ở Java, hoặc EXISTS/OR khi semantics tương đương.

## 32. Bảng chọn toán tử nhanh

| Yêu cầu | Toán tử | Duplicate |
| --- | --- | --- |
| Hợp hai danh sách, mỗi giá trị chỉ một lần | `UNION` | Loại |
| Hợp hai danh sách, giữ mọi bản ghi | `UNION ALL` | Giữ |
| Chỉ lấy giá trị xuất hiện ở cả hai | `INTERSECT` | Loại |
| Lấy phần giao và giữ số lần khớp tối thiểu | `INTERSECT ALL` | Giữ multiplicity giao |
| Lấy giá trị có ở trái nhưng không ở phải | `EXCEPT` | Loại |
| Trừ số lần xuất hiện bên phải khỏi bên trái | `EXCEPT ALL` | Giữ multiplicity còn lại |
| Kiểm tra một entity có liên quan hay không | `EXISTS` / JOIN | Theo query entity |
| Lọc cùng một nguồn theo nhiều điều kiện | `OR` | Theo hàng nguồn |
| Lấy dữ liệu từ database cũ không hỗ trợ HQL set | Native SQL hoặc query riêng | Do cách triển khai quyết định |

## 33. Nguyên tắc cần nhớ

1. **Set operation kết hợp toàn bộ result set**, không phải join hàng theo FK.
2. **UNION loại duplicate, UNION ALL giữ duplicate.** Chọn theo ý nghĩa nghiệp vụ và multiplicity.
3. **INTERSECT tìm phần chung, EXCEPT lấy phần trái trừ phần phải.** Đảo nhánh EXCEPT làm thay đổi kết quả.
4. **ALL thay đổi cách xử lý số lần xuất hiện.** INTERSECT ALL dùng multiplicity nhỏ hơn; EXCEPT ALL trừ multiplicity.
5. **Các nhánh phải có cùng số select item và kiểu tương ứng tương thích.** Alias không sửa được sai lệch kiểu.
6. **JPA 3.2 chuẩn hóa UNION, INTERSECT và EXCEPT.** JPA cũ không có tính portable tương tự; HQL hiện đại có thể cung cấp extension tùy Hibernate version.
7. **Parser, strict compliance và dialect là ba tầng tương thích khác nhau.** Query parse được chưa chắc database thực thi được.
8. **Set result không có thứ tự mặc định.** Dùng ORDER BY ở kết quả cuối nếu cần thứ tự ổn định.
9. **Không cộng count từng nhánh để thay count của UNION distinct.** Duplicate làm thay đổi số lượng.
10. **Khi stack cũ chưa hỗ trợ, chọn fallback có cùng semantics.** Native SQL, hai query ghép Java, OR, EXISTS hoặc NOT EXISTS đều có trade-off.
11. **Không chọn UNION ALL chỉ vì nhanh hơn.** Nó chỉ đúng nếu duplicate cần được giữ.
12. **Đo execution plan trên database thực tế.** Sort, hash, index, dialect và kích thước dữ liệu quyết định hiệu năng.

Khi hiểu rõ các phép hợp, giao và hiệu giữa result set, ta có thể diễn đạt những truy vấn nhiều nguồn dữ liệu ngay trong HQL/JPQL. Điều quan trọng là chọn đúng semantics duplicate, bảo đảm các nhánh tương thích kiểu và xác nhận phiên bản provider/database hỗ trợ trước khi đưa query vào ứng dụng.
