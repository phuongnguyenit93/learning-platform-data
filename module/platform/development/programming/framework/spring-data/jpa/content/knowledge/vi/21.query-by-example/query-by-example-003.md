# So khớp chuỗi, phân biệt chữ hoa thường và giá trị NULL

Khi truy vấn dữ liệu văn bản bằng Spring Data JPA, cần xác định rõ ứng dụng muốn so khớp chính xác, tìm chuỗi con, tìm theo tiền tố hay bỏ qua khác biệt chữ hoa/thường. JPQL cung cấp các toán tử và hàm chuỗi như LIKE, LOWER, UPPER, TRIM, CONCAT và LOCATE. Tuy nhiên, kết quả còn chịu ảnh hưởng của collation trong database, quy tắc Unicode và cách xử lý giá trị NULL.

NULL là trường hợp đặc biệt: phép so sánh với NULL bằng =, <>, LIKE hoặc NOT LIKE không trả về TRUE mà cho kết quả UNKNOWN. Vì vậy, phải dùng IS NULL hoặc IS NOT NULL khi cần kiểm tra giá trị vắng mặt. Bài học này trình bày cách chọn phép so khớp, viết derived query và JPQL, xử lý ký tự wildcard an toàn, phân biệt null với chuỗi rỗng, và kiểm thử hành vi trên database mục tiêu.

## 1. Các kiểu so khớp chuỗi thường gặp

Một yêu cầu tìm kiếm có thể mang nhiều ý nghĩa:

| Nhu cầu | Ví dụ với tên | Cách truy vấn thường dùng |
|---|---|---|
| Khớp chính xác | An chỉ khớp An | = |
| Bắt đầu bằng | An, Anh, Anny | LIKE 'An%' |
| Kết thúc bằng | Minh An, Tuấn An | LIKE '%An' |
| Chứa chuỗi con | Hoàng An, An Bình | LIKE '%An%' |
| Không phân biệt hoa/thường | an, An, AN | LOWER/UPPER hoặc IgnoreCase |
| Không có giá trị | name là NULL | IS NULL |
| Có giá trị | name khác NULL | IS NOT NULL |

Trước khi viết query, hãy thống nhất ý nghĩa nghiệp vụ. Tìm kiếm chính xác khác tìm kiếm gần đúng; tìm chuỗi con khác tìm theo tiền tố; bỏ qua phân biệt hoa thường khác bỏ qua dấu tiếng Việt.

## 2. So khớp chính xác bằng dấu bằng

JPQL dùng = để so sánh hai giá trị:

~~~java
@Query("""
    select c
    from Customer c
    where c.email = :email
    """)
Optional<Customer> findByExactEmail(
    @Param("email") String email
);
~~~

Điều kiện này yêu cầu giá trị email khớp theo quy tắc so sánh của database và kiểu cột. Việc có phân biệt hoa/thường hay không có thể phụ thuộc collation.

Với derived query, Spring Data có thể tạo query từ tên method:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Dùng phép so sánh chính xác khi tìm mã, email hoặc định danh mà nghiệp vụ yêu cầu khớp toàn bộ giá trị. Đừng dùng LIKE chỉ vì muốn tránh xử lý khoảng trắng hoặc chữ hoa/thường; hãy định nghĩa quy tắc chuẩn hóa rõ ràng.

## 3. LIKE và hai ký tự wildcard

LIKE dùng mẫu chuỗi để so khớp:

- Dấu phần trăm (%) đại diện cho không hoặc nhiều ký tự.
- Dấu gạch dưới (_) đại diện cho đúng một ký tự.

Ví dụ:

~~~sql
-- Bắt đầu bằng An
WHERE name LIKE 'An%'

-- Kết thúc bằng An
WHERE name LIKE '%An'

-- Chứa An ở bất kỳ vị trí nào
WHERE name LIKE '%An%'

-- An theo sau bởi đúng một ký tự
WHERE name LIKE 'An_'
~~~

JPQL cũng dùng LIKE:

~~~jpql
select c
from Customer c
where c.name like :pattern
~~~

Nếu truyền pattern là An%, query tìm các tên bắt đầu bằng An. Nếu truyền %An%, query tìm tên có chứa An ở bất kỳ vị trí nào.

LIKE không tự động có nghĩa là không phân biệt hoa/thường. Điều đó tùy collation và database. Muốn quy định rõ hơn, dùng LOWER/UPPER hoặc collation phù hợp.

## 4. Derived query với Containing, StartingWith và EndingWith

Spring Data JPA hỗ trợ các keyword tạo mẫu LIKE từ tên method:

~~~java
List<Customer> findByNameContaining(String fragment);

List<Customer> findByNameStartingWith(String prefix);

List<Customer> findByNameEndingWith(String suffix);

List<Customer> findByNameLike(String pattern);
~~~

Ý nghĩa:

- Containing thêm wildcard ở cả hai phía của tham số.
- StartingWith thêm wildcard phía cuối.
- EndingWith thêm wildcard phía đầu.
- Like nhận mẫu pattern do caller truyền vào.

Ví dụ:

~~~java
repository.findByNameContaining("An");
repository.findByNameStartingWith("An");
repository.findByNameEndingWith("An");
repository.findByNameLike("An%");
~~~

Các method đầu tiên biểu diễn ý định tìm chuỗi con, tiền tố và hậu tố. Với Like, caller chịu trách nhiệm cung cấp wildcard đúng.

Spring Data JPA có cơ chế escape ký tự wildcard trong đối số của một số derived query dùng LIKE như Containing, StartingWith và EndingWith, để ký tự % hoặc _ do người dùng nhập được xem như ký tự cần tìm thay vì wildcard. Escape character có thể được cấu hình trong @EnableJpaRepositories theo phiên bản Spring Data đang dùng. Nếu dùng @Query thủ công, hãy tự thiết kế và kiểm thử quy tắc escape.

## 5. Không phân biệt hoa/thường với IgnoreCase

Spring Data hỗ trợ keyword IgnoreCase cho derived query:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);

List<Customer> findByNameContainingIgnoreCase(String fragment);

List<Customer> findByNameStartingWithIgnoreCase(String prefix);
~~~

IgnoreCase yêu cầu so sánh chuỗi không phân biệt hoa/thường. Spring Data JPA thường diễn đạt việc này bằng hàm UPPER trên thuộc tính và tham số trong query được tạo.

Ví dụ, với chính sách case-insensitive, các giá trị An, AN và an có thể được xem là tương đương khi tìm kiếm.

IgnoreCase chỉ phù hợp với thuộc tính chuỗi. Không áp dụng cho số, ngày hoặc kiểu dữ liệu không phải String.

Không nên giả định IgnoreCase cũng bỏ qua dấu. So sánh không phân biệt hoa/thường và so sánh không phân biệt dấu là hai yêu cầu khác nhau.

## 6. Dùng LOWER hoặc UPPER trong JPQL

Nếu viết @Query, có thể dùng LOWER hoặc UPPER ở cả hai phía:

~~~java
@Query("""
    select c
    from Customer c
    where lower(c.email) = lower(:email)
    """)
Optional<Customer> findByEmailCaseInsensitive(
    @Param("email") String email
);
~~~

Tìm chuỗi con không phân biệt hoa/thường:

~~~java
@Query("""
    select c
    from Customer c
    where lower(c.name) like lower(concat('%', :keyword, '%'))
    """)
List<Customer> searchNameIgnoreCase(
    @Param("keyword") String keyword
);
~~~

LOWER chuyển chuỗi sang chữ thường theo quy tắc của database. UPPER chuyển sang chữ hoa. Dùng cùng một hàm ở hai phía giúp so sánh không phụ thuộc cách người dùng nhập hoa hay thường trong nhiều trường hợp.

Đây là cách biểu diễn phổ biến và dễ đọc, nhưng không đảm bảo mọi ngôn ngữ Unicode có cùng kết quả trên mọi database. Hàm LOWER/UPPER được thực hiện ở database, không nhất thiết dùng đúng quy tắc locale của Java.

Nếu yêu cầu tìm kiếm đa ngôn ngữ nghiêm ngặt, hãy kiểm thử các ký tự đặc biệt và cấu hình collation phù hợp.

## 7. Phân biệt case-insensitive và accent-insensitive

Không phân biệt hoa/thường có nghĩa An và an được xem là tương đương theo quy tắc so sánh.

Không phân biệt dấu có nghĩa các dạng như a và á có thể được xem là tương đương. Đây là chính sách khác.

LOWER và UPPER chỉ thay đổi dạng chữ theo quy tắc chuyển hoa/thường; chúng không phải hàm loại bỏ dấu. Vì vậy, lower(name) không tự biến Nguyễn thành Nguyen.

Muốn tìm không phân biệt dấu, có thể cần:

- Collation accent-insensitive của database.
- Hàm hoặc extension riêng của hệ quản trị.
- Một cột tìm kiếm đã chuẩn hóa dấu được duy trì đồng bộ.
- Công cụ full-text search hoặc search engine phù hợp.

Các giải pháp này có tính phụ thuộc database hoặc kiến trúc. Không giả định JPQL chuẩn có một hàm portable để bỏ dấu tiếng Việt.

## 8. Collation quyết định cách database so sánh chuỗi

Collation quy định nhiều đặc điểm của phép so sánh và sắp xếp chuỗi, chẳng hạn:

- Có phân biệt hoa/thường hay không.
- Có phân biệt dấu hay không.
- Quy tắc so sánh theo locale.
- Cách xử lý một số ký tự Unicode.

Ví dụ, một cột có collation case-insensitive có thể xem An và an là bằng nhau ngay cả khi query dùng dấu =. Một cột có collation case-sensitive có thể phân biệt chúng.

Hành vi mặc định khác nhau giữa hệ quản trị, phiên bản, cấu hình database và cấu hình từng cột. MySQL thường dùng collation theo charset/cấu hình cột; PostgreSQL thường phân biệt hoa/thường với phép so sánh thông thường và có extension ILIKE; SQL Server phụ thuộc collation của database hoặc column. Đây chỉ là mô tả định hướng, không thay thế việc kiểm tra cấu hình thực tế.

Hãy xác định collation của cột cần tìm kiếm trước khi kết luận một query có phân biệt hoa/thường hay không.

## 9. Ký tự wildcard do người dùng nhập

Một lỗi phổ biến là cho rằng bind parameter đã giải quyết mọi vấn đề khi tìm kiếm LIKE.

Bind parameter giúp tách dữ liệu khỏi cấu trúc query, tránh ghép trực tiếp input vào JPQL/SQL. Tuy nhiên, nếu người dùng nhập % hoặc _, hai ký tự này vẫn có ý nghĩa wildcard trong LIKE. Kết quả có thể rộng hơn điều người dùng mong muốn.

Ví dụ người dùng tìm mã 50%OFF. Nếu truyền trực tiếp pattern %50%OFF%, dấu % trong dữ liệu tìm kiếm có thể được hiểu là wildcard, không phải ký tự phần trăm cần tìm.

Nếu yêu cầu tìm chuỗi literal, phải escape ký tự wildcard.

## 10. Escape wildcard trong JPQL

JPQL LIKE hỗ trợ mệnh đề ESCAPE. Ví dụ dùng dấu chấm than (!) làm ký tự escape:

~~~jpql
select c
from Customer c
where c.name like :pattern escape '!'
~~~

Trước khi bind, cần chuyển đổi:

- ! thành !!
- % thành !%
- _ thành !_

Sau đó mới thêm wildcard ở hai đầu nếu muốn tìm chuỗi con.

Ví dụ Java:

~~~java
public final class LikePattern {

    private LikePattern() {
    }

    public static String containsLiteral(String value) {
        String escaped = value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");

        return "%" + escaped + "%";
    }
}
~~~

Repository:

~~~java
@Query("""
    select c
    from Customer c
    where lower(c.name) like lower(:pattern) escape '!'
    """)
List<Customer> searchNameLiteral(
    @Param("pattern") String pattern
);
~~~

Service gọi:

~~~java
String pattern = LikePattern.containsLiteral(keyword);
List<Customer> matches = repository.searchNameLiteral(pattern);
~~~

Ví dụ nếu keyword là 50%OFF, pattern sau escape là %50!%OFF%. Hai dấu % ngoài cùng vẫn có nghĩa tìm chuỗi con; dấu !% ở giữa có nghĩa ký tự phần trăm literal.

Nếu dùng ký tự escape khác, phải thống nhất giữa code escape và mệnh đề ESCAPE. Hãy kiểm thử các trường hợp có chính ký tự escape, %, _, chuỗi rỗng và ký tự Unicode.

## 11. Không ghép input trực tiếp vào JPQL hoặc SQL

Không tạo query bằng cách nối chuỗi người dùng:

~~~java
// Không an toàn và khó kiểm soát cú pháp:
String jpql =
    "select c from Customer c where c.name like '%"
    + keyword + "%'";
~~~

Cách đúng là bind parameter:

~~~java
@Query("""
    select c
    from Customer c
    where c.name like :pattern
    """)
List<Customer> searchByPattern(
    @Param("pattern") String pattern
);
~~~

Parameter binding ngăn input trở thành một phần cú pháp JPQL/SQL. Với LIKE, vẫn phải escape wildcard nếu muốn so khớp literal như phần trước.

Không dùng tên property, tên cột hoặc biểu thức sort do người dùng gửi làm bind parameter; đó là cấu trúc query. Hãy whitelist các trường và biểu thức được phép.

## 12. Các hàm chuỗi JPQL hữu ích

JPQL chuẩn cung cấp một số hàm chuỗi phổ biến:

| Hàm | Công dụng | Ví dụ |
|---|---|---|
| LOWER(x) | Chuyển sang chữ thường | lower(c.name) |
| UPPER(x) | Chuyển sang chữ hoa | upper(c.email) |
| TRIM(x) | Loại khoảng trắng ở đầu/cuối theo quy tắc hàm | trim(c.name) |
| CONCAT(a, b) | Nối chuỗi | concat(c.firstName, c.lastName) |
| LENGTH(x) | Độ dài chuỗi | length(c.name) |
| LOCATE(pattern, x) | Tìm vị trí chuỗi con | locate('An', c.name) |
| SUBSTRING(x, start, length) | Lấy chuỗi con | substring(c.code, 1, 3) |

LOCATE trả vị trí bắt đầu theo quy tắc chỉ số bắt đầu từ 1; trả 0 nếu không tìm thấy. Cú pháp và overload chi tiết cần theo phiên bản Jakarta Persistence và provider.

Ví dụ tìm tên có ít nhất một ký tự sau khi trim:

~~~jpql
select c
from Customer c
where length(trim(c.name)) > 0
~~~

Các hàm chuỗi có thể trả NULL nếu đầu vào là NULL. Không dùng LOWER, TRIM hoặc LENGTH để thay thế IS NULL khi cần kiểm tra giá trị vắng mặt.

## 13. NULL không giống chuỗi rỗng hoặc khoảng trắng

Ba trạng thái cần phân biệt:

| Giá trị | Ý nghĩa |
|---|---|
| NULL | Không có giá trị |
| Chuỗi rỗng | Có giá trị String nhưng không chứa ký tự |
| Chuỗi chỉ có khoảng trắng | Có ký tự, nhưng không có nội dung nhìn thấy |

Trong Java:

~~~java
String a = null;
String b = "";
String c = "   ";
~~~

Ba giá trị này không giống nhau. c.isBlank() có thể trả true, nhưng c không phải null và cũng không phải chuỗi rỗng.

Trong database, NULL được xử lý theo logic SQL. Chuỗi rỗng thường là giá trị riêng trên PostgreSQL và MySQL. Oracle Database có hành vi đặc biệt coi chuỗi ký tự có độ dài bằng 0 như NULL trong nhiều ngữ cảnh SQL. Vì vậy, kiểm thử trên H2 không đảm bảo kết quả giống Oracle.

Nếu nghiệp vụ muốn coi chuỗi rỗng hoặc chỉ có khoảng trắng là chưa nhập, hãy chuẩn hóa dữ liệu trước khi lưu hoặc dùng điều kiện phù hợp. Đừng tự động xem NULL, chuỗi rỗng và khoảng trắng là một trạng thái nếu domain không quy định như vậy.

## 14. Logic ba giá trị khi so sánh với NULL

SQL và JPQL sử dụng ba giá trị logic:

- TRUE
- FALSE
- UNKNOWN

Phép so sánh thông thường với NULL thường trả về UNKNOWN:

| Biểu thức | Kết quả |
|---|---|
| NULL = NULL | UNKNOWN |
| NULL <> 'An' | UNKNOWN |
| NULL LIKE '%An%' | UNKNOWN |
| NULL NOT LIKE '%An%' | UNKNOWN |
| NULL IS NULL | TRUE |
| NULL IS NOT NULL | FALSE |

WHERE chỉ giữ hàng có điều kiện TRUE. Hàng có điều kiện FALSE hoặc UNKNOWN đều bị loại.

Vì vậy, các điều kiện sau không đúng để kiểm tra null:

~~~jpql
where c.name = null
~~~

~~~jpql
where c.name <> null
~~~

Hãy viết:

~~~jpql
where c.name is null
~~~

hoặc:

~~~jpql
where c.name is not null
~~~

Đây là quy tắc quan trọng khi kết hợp tìm kiếm chuỗi với dữ liệu có thể thiếu.

## 15. LIKE và NOT LIKE khi thuộc tính là NULL

Giả sử Customer có name nullable. Truy vấn:

~~~jpql
select c
from Customer c
where c.name like :pattern
~~~

sẽ không trả Customer có name NULL, vì phép LIKE với NULL cho UNKNOWN.

Tương tự:

~~~jpql
select c
from Customer c
where c.name not like :pattern
~~~

cũng không trả Customer có name NULL. NOT UNKNOWN vẫn là UNKNOWN, không trở thành TRUE.

Nếu nghiệp vụ muốn lấy các Customer có tên không chứa từ khóa hoặc chưa có tên, cần viết rõ:

~~~jpql
select c
from Customer c
where c.name not like :pattern
   or c.name is null
~~~

Nếu muốn tìm tên chứa từ khóa hoặc tên chưa được nhập:

~~~jpql
select c
from Customer c
where c.name like :pattern
   or c.name is null
~~~

Hãy xác định null có được xem là một nhóm kết quả riêng hay phải bị loại khỏi tìm kiếm.

## 16. Spring Data derived query và tham số NULL

Với derived query dùng phép bằng, Spring Data JPA có thể chuyển tham số null thành điều kiện IS NULL. Với keyword Not và tham số null, query có thể được diễn giải thành IS NOT NULL.

Ví dụ:

~~~java
List<Customer> findByName(String name);

List<Customer> findByNameIsNull();

List<Customer> findByNameIsNotNull();

List<Customer> findByNameNot(String name);
~~~

Nếu gọi findByName(null), derived query equality có thể tìm các hàng name IS NULL. Nếu gọi findByNameNot(null), hành vi tương ứng là name IS NOT NULL.

Dù vậy, dùng tên method IsNull và IsNotNull tường minh thường dễ đọc hơn khi null là một yêu cầu nghiệp vụ quan trọng. Đừng suy luận rằng hành vi này giống với một @Query có điều kiện c.name = :name; trong JPQL viết tay, tham số null ở phép = vẫn tạo UNKNOWN.

Các keyword Containing, StartingWith, EndingWith và IgnoreCase mô tả cách tạo predicate chuỗi; chúng không tự biến NULL thành chuỗi rỗng hoặc bỏ qua bộ lọc.

## 17. Tìm kiếm không phân biệt hoa/thường và xử lý NULL

Nếu name có thể NULL, query:

~~~jpql
where lower(c.name) = lower(:name)
~~~

không khớp hàng có name NULL. Hàm LOWER trên NULL cho NULL, phép so sánh tiếp tục cho UNKNOWN.

Nếu cần tìm Customer có tên bằng giá trị truyền vào và hỗ trợ trường hợp tìm NULL, có thể dùng hai nhánh rõ ràng:

~~~jpql
where (:name is null and c.name is null)
   or (:name is not null and lower(c.name) = lower(:name))
~~~

Ý nghĩa:

- Khi name parameter là NULL, chỉ lấy entity có c.name NULL.
- Khi parameter có giá trị, so sánh case-insensitive.
- Hai nhánh phân biệt rõ tìm NULL với tìm chuỗi có nội dung.

Nếu muốn null parameter có nghĩa bỏ qua bộ lọc, đó là một yêu cầu khác và cần viết theo mẫu optional filter ở phần sau.

## 18. Bộ lọc tùy chọn có tham số NULL

Một API tìm kiếm có thể cho phép bỏ qua điều kiện tên khi người dùng không nhập keyword.

Ví dụ:

~~~java
@Query("""
    select c
    from Customer c
    where (:keyword is null
           or lower(c.name) like lower(:pattern) escape '!')
    """)
List<Customer> searchOptionalName(
    @Param("keyword") String keyword,
    @Param("pattern") String pattern
);
~~~

Service chuẩn bị pattern:

~~~java
String pattern = keyword == null
    ? null
    : LikePattern.containsLiteral(keyword);

return repository.searchOptionalName(keyword, pattern);
~~~

Khi keyword là NULL, vế đầu TRUE nên bộ lọc tên được bỏ qua. Khi keyword có giá trị, query áp dụng LIKE không phân biệt hoa/thường và escape wildcard.

Nếu cần tìm các hàng có name NULL, không dùng cùng một ý nghĩa với null parameter bỏ qua filter. Hãy tạo method riêng hoặc thêm một tham số biểu diễn chế độ tìm kiếm.

Khi có nhiều bộ lọc tùy chọn, các biểu thức OR có thể làm query khó tối ưu. Cân nhắc Spring Data Specification, Criteria API hoặc query động để chỉ thêm predicate khi người dùng thực sự nhập điều kiện.

## 19. Chuẩn hóa input ở tầng service

Một quy tắc tìm kiếm tốt thường bắt đầu bằng chuẩn hóa đầu vào:

~~~java
public String normalizeKeyword(String keyword) {
    if (keyword == null) {
        return null;
    }

    String normalized = keyword.strip();

    return normalized.isEmpty() ? null : normalized;
}
~~~

Đoạn code dùng String.strip() của Java 11 trở lên để bỏ khoảng trắng theo Unicode ở hai đầu. Nếu ứng dụng chạy Java 17+, API này có sẵn.

Cần quyết định:

- Input chỉ có khoảng trắng được xem là không có bộ lọc hay là chuỗi cần tìm?
- Có chuẩn hóa Unicode NFC/NFD không?
- Có chuyển hoa/thường ở Java hay để database xử lý bằng LOWER/UPPER?
- Có giữ khoảng trắng bên trong chuỗi không?
- Có phân biệt dấu không?

Không chuẩn hóa tùy tiện. Ví dụ mã định danh có thể cần giữ nguyên chữ hoa/thường hoặc khoảng trắng có ý nghĩa. Quy tắc chuẩn hóa phải phù hợp domain và nhất quán khi lưu lẫn tìm kiếm.

## 20. Ảnh hưởng đến index và hiệu năng

Các điều kiện chuỗi có chi phí khác nhau:

~~~jpql
where c.email = :email
~~~

So sánh chính xác thường dễ tận dụng index B-tree trên cột email hơn.

~~~jpql
where lower(c.email) = lower(:email)
~~~

Áp dụng hàm lên cột có thể khiến database không dùng được index thông thường theo cách mong muốn, tùy optimizer và database. Có thể cần functional index trên lower(email), collation phù hợp hoặc cột normalized.

~~~jpql
where c.name like 'An%'
~~~

Tìm theo tiền tố có thể tận dụng index trong một số database và collation.

~~~jpql
where c.name like '%An%'
~~~

Wildcard đầu chuỗi thường khiến index B-tree thông thường khó hỗ trợ hiệu quả. Với tìm kiếm chuỗi con quy mô lớn, cân nhắc full-text search, trigram index hoặc search engine phù hợp.

Một số hướng tối ưu:

- Kiểm tra execution plan thay vì đoán từ cú pháp.
- Tạo index theo điều kiện truy vấn thực tế.
- Cân nhắc functional index cho LOWER/UPPER nếu database hỗ trợ.
- Chuẩn hóa dữ liệu vào cột tìm kiếm riêng nếu cần.
- Dùng full-text search khi nghiệp vụ cần tìm từ, token, stemming hoặc ranking.
- Giới hạn page size và số kết quả trả về.
- Tránh chạy tìm kiếm chuỗi con trên bảng rất lớn mà không có chiến lược index phù hợp.

Không hy sinh quy tắc nghiệp vụ chỉ để tận dụng index. Trước hết xác định semantics chính xác, sau đó tối ưu query và schema.

## 21. Ví dụ repository tổng hợp

~~~java
package example.repository;

import example.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByNameContainingIgnoreCase(String fragment);

    List<Customer> findByNameStartingWithIgnoreCase(String prefix);

    List<Customer> findByNameIsNull();

    List<Customer> findByNameIsNotNull();

    @Query("""
        select c
        from Customer c
        where lower(c.name) = lower(:name)
        """)
    List<Customer> findExactNameIgnoreCase(
        @Param("name") String name
    );

    @Query("""
        select c
        from Customer c
        where c.name like :pattern escape '!'
        """)
    List<Customer> findByLiteralNamePattern(
        @Param("pattern") String pattern
    );

    @Query("""
        select c
        from Customer c
        where (:keyword is null
               or lower(c.name) like lower(:pattern) escape '!')
        """)
    List<Customer> searchOptionalName(
        @Param("keyword") String keyword,
        @Param("pattern") String pattern
    );
}
~~~

Các method trên minh họa ba cách:

- Derived query cho các thao tác thường gặp và tên method dễ đọc.
- JPQL @Query khi cần điều khiển biểu thức, ESCAPE hoặc optional filter.
- Service chuẩn hóa input và tạo pattern trước khi gọi repository.

Trong code thực tế, hãy chọn một cách nhất quán theo độ phức tạp. Không cần tạo @Query cho một điều kiện đơn giản mà derived query đã thể hiện rõ.

## 22. Kiểm thử so khớp chuỗi và NULL

Một bộ integration test nên chuẩn bị dữ liệu:

| Customer | name | email |
|---|---|---|
| 1 | An | an@example.com |
| 2 | AN | AN@example.com |
| 3 | Nguyễn An | n.an@example.com |
| 4 | An%Pro | percent@example.com |
| 5 | An_Pro | underscore@example.com |
| 6 | NULL | null-name@example.com |
| 7 | Chuỗi rỗng | empty@example.com |
| 8 | Chỉ có khoảng trắng | spaces@example.com |

Kiểm tra:

1. Exact match theo chính sách collation của database.
2. IgnoreCase cho tên có chữ hoa/thường khác nhau.
3. Containing, StartingWith và EndingWith.
4. Wildcard % và _ trong input được escape nếu cần literal matching.
5. Ký tự escape được escape chính xác.
6. LIKE không trả hàng có giá trị NULL.
7. NOT LIKE cũng không tự động bao gồm NULL.
8. IS NULL và IS NOT NULL trả đúng nhóm dữ liệu.
9. Optional filter với keyword null bỏ qua điều kiện theo đúng thiết kế.
10. Tìm chuỗi rỗng khác với tìm NULL trên database phân biệt hai trạng thái.
11. Dữ liệu tiếng Việt có dấu và Unicode được xử lý theo collation mong muốn.
12. Query không tạo SQL injection và không cho phép input thay đổi cấu trúc query.

Nên chạy test trên cùng database với production. H2 có thể khác PostgreSQL, MySQL, Oracle hoặc SQL Server về collation, case sensitivity, empty string và hàm chuỗi.

## 23. Lỗi thường gặp và cách khắc phục

**1. IgnoreCase vẫn không cho kết quả như mong đợi**

Kiểm tra kiểu property có phải String không, SQL được sinh, collation và quy tắc Unicode. IgnoreCase không đồng nghĩa accent-insensitive.

**2. LIKE trả quá nhiều kết quả**

Kiểm tra input có chứa % hoặc _ không. Escape wildcard nếu muốn so khớp literal.

**3. LIKE không tìm được chuỗi có ký tự % hoặc _**

Dùng mệnh đề ESCAPE và escape input trước khi thêm wildcard tìm chuỗi con.

**4. = NULL không tìm được bản ghi**

Dùng IS NULL. Phép so sánh với NULL tạo UNKNOWN.

**5. NOT LIKE vẫn bỏ qua các hàng có giá trị NULL**

Đây là hành vi logic ba giá trị. Nếu cần lấy cả NULL, thêm OR property IS NULL.

**6. Tham số null làm optional filter không đúng**

Xác định null nghĩa là bỏ qua filter hay tìm giá trị NULL. Hai yêu cầu cần predicate khác nhau.

**7. Chuỗi rỗng bị xử lý như NULL trên môi trường production**

Kiểm tra database. Oracle có semantics khác với PostgreSQL và MySQL đối với chuỗi ký tự rỗng.

**8. LOWER làm query chậm**

Kiểm tra execution plan và index. Cân nhắc functional index hoặc cột normalized nếu workload cần.

**9. Tìm kiếm tiếng Việt bỏ dấu không hoạt động**

LOWER/UPPER không loại dấu. Cần collation accent-insensitive, extension hoặc chiến lược chuẩn hóa riêng.

**10. Dùng query hoạt động trên H2 nhưng lỗi ở production**

So sánh database engine, collation, hàm và cú pháp. Chạy integration test trên database thực tế.

## 24. Quy trình thiết kế tìm kiếm chuỗi

Khi thêm chức năng tìm kiếm, hãy thực hiện theo thứ tự:

1. Xác định khớp chính xác, tiền tố, hậu tố hay chuỗi con.
2. Quyết định có phân biệt hoa/thường hay không.
3. Quyết định có phân biệt dấu tiếng Việt hay không.
4. Kiểm tra collation của cột và database.
5. Xác định input NULL, chuỗi rỗng và khoảng trắng có ý nghĩa gì.
6. Chọn derived query, JPQL @Query hoặc Criteria API.
7. Với LIKE, escape % và _ nếu muốn tìm literal.
8. Dùng bind parameter, không nối input vào query.
9. Xử lý IS NULL/IS NOT NULL riêng với phép LIKE hoặc equality.
10. Phân biệt null parameter bỏ qua filter với null parameter tìm dữ liệu null.
11. Kiểm tra index và execution plan.
12. Viết integration test với dữ liệu hoa/thường, dấu, wildcard, NULL và chuỗi rỗng.
13. Chạy test trên database mục tiêu.

## 25. Checklist tự đánh giá

- [ ] Tôi phân biệt được exact match, prefix, suffix và substring.
- [ ] Tôi hiểu % và _ trong LIKE.
- [ ] Tôi biết dùng Containing, StartingWith, EndingWith và Like.
- [ ] Tôi biết dùng IgnoreCase trong derived query.
- [ ] Tôi biết dùng LOWER/UPPER trong JPQL.
- [ ] Tôi phân biệt case-insensitive và accent-insensitive.
- [ ] Tôi hiểu collation quyết định cách so sánh chuỗi.
- [ ] Tôi biết escape wildcard bằng ESCAPE.
- [ ] Tôi luôn bind parameter và không nối input vào query.
- [ ] Tôi biết các hàm chuỗi JPQL phổ biến.
- [ ] Tôi phân biệt NULL, chuỗi rỗng và chuỗi khoảng trắng.
- [ ] Tôi hiểu logic UNKNOWN khi so sánh với NULL.
- [ ] Tôi dùng IS NULL và IS NOT NULL đúng chỗ.
- [ ] Tôi hiểu hành vi tham số null của derived query khác với JPQL viết tay.
- [ ] Tôi phân biệt bỏ qua filter với tìm giá trị NULL.
- [ ] Tôi hiểu LOWER/LIKE có thể ảnh hưởng khả năng dùng index.
- [ ] Tôi có integration test trên database production.

## 26. Câu hỏi ôn tập

**1. LIKE khác = thế nào?**

= so sánh giá trị theo quy tắc của database; LIKE so khớp mẫu chuỗi có wildcard % và _.

**2. Containing khác Like thế nào?**

Containing tự thêm wildcard hai đầu để tìm chuỗi con. Like nhận pattern do caller cung cấp.

**3. IgnoreCase có bỏ dấu tiếng Việt không?**

Không. IgnoreCase chỉ xử lý khác biệt hoa/thường theo cơ chế provider/database. Bỏ dấu cần collation hoặc giải pháp riêng.

**4. Vì sao phải escape % và _ trong input?**

Vì hai ký tự này là wildcard của LIKE. Nếu không escape, chúng có thể mở rộng kết quả ngoài ý muốn khi người dùng muốn tìm literal.

**5. Vì sao name = NULL không tìm được hàng có name NULL?**

Phép so sánh với NULL tạo UNKNOWN. Dùng IS NULL.

**6. NOT LIKE có bao gồm hàng NULL không?**

Không. NOT UNKNOWN vẫn là UNKNOWN. Muốn bao gồm NULL, thêm điều kiện OR name IS NULL.

**7. Null parameter trong derived query có giống null parameter trong @Query không?**

Không hoàn toàn. Spring Data có thể diễn giải derived equality với null thành IS NULL; JPQL viết tay với name = :name vẫn dùng logic SQL và không khớp NULL. Hãy viết predicate tường minh.

**8. Vì sao optional filter và tìm NULL phải tách biệt?**

Vì null có thể có nghĩa không áp dụng điều kiện hoặc có nghĩa tìm những hàng không có giá trị. Hai ý nghĩa tạo query khác nhau và cần được biểu diễn riêng.

**9. Vì sao LOWER(name) có thể làm query chậm?**

Hàm được áp dụng lên cột có thể khiến index thông thường không được tận dụng theo cách mong muốn. Functional index hoặc cột normalized có thể giúp, tùy database.

**10. Khi nào nên dùng full-text search?**

Khi yêu cầu vượt quá so khớp chuỗi con đơn giản, chẳng hạn tìm token, từ liên quan, ranking, stemming hoặc tập dữ liệu lớn.

Thiết kế tìm kiếm chuỗi tốt bắt đầu từ semantics rõ ràng: loại so khớp, quy tắc hoa/thường, dấu, wildcard và cách hiểu NULL. Khi những quy tắc này được thể hiện tường minh trong repository và được kiểm thử trên database mục tiêu, kết quả tìm kiếm sẽ dễ dự đoán và bảo trì hơn.

## Tài liệu tham khảo

- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Repository Query Keywords](https://docs.spring.io/spring-data/jpa/reference/repositories/query-keywords-reference.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
