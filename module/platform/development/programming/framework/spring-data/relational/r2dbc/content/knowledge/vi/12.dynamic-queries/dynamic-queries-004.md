# Điều kiện null, chuỗi rỗng và tìm kiếm theo mẫu

Khi xây dựng truy vấn động với Spring Data R2DBC, cần phân biệt rõ ba trường hợp thường bị gộp chung: **giá trị SQL NULL**, **chuỗi rỗng** và **chuỗi chỉ chứa khoảng trắng**. Chúng có ý nghĩa khác nhau trong SQL và có thể tạo ra kết quả khác nhau khi lọc dữ liệu.

Spring Data R2DBC cung cấp Query và Criteria để diễn đạt điều kiện theo metadata entity. Có thể dùng isNull() và isNotNull() cho giá trị NULL, is("") cho chuỗi rỗng, và like(pattern) cho tìm kiếm theo mẫu. Khi điều kiện phụ thuộc dữ liệu đầu vào, ứng dụng có thể thêm từng Criteria vào truy vấn thay vì tạo nhiều câu SQL riêng.

## 1. Phân biệt NULL, chuỗi rỗng và chuỗi trắng

Giả sử bảng customer có cột email kiểu VARCHAR. Một hàng có thể chứa các trạng thái sau:

| Giá trị trong cột | Ý nghĩa | Ví dụ |
|---|---|---|
| NULL | Không có giá trị hoặc chưa được cung cấp | email chưa biết |
| Chuỗi rỗng | Có giá trị dạng chuỗi nhưng độ dài bằng 0 | '' |
| Chuỗi trắng | Có một hoặc nhiều ký tự khoảng trắng | '   ' |
| Chuỗi thông thường | Có nội dung | 'an@example.com' |

Trong Java, các trường hợp tương ứng có thể là:

~~~java
String missing = null;
String empty = "";
String blank = "   ";
String value = "an@example.com";
~~~

Chúng không tương đương:

- null biểu diễn sự vắng mặt của một giá trị.
- "" là một đối tượng String có độ dài bằng 0.
- "   " có độ dài lớn hơn 0 nhưng không chứa ký tự ngoài khoảng trắng theo cách Java định nghĩa blank.
- Một chuỗi thông thường chứa dữ liệu cần tìm hoặc so sánh.

Không nên tự động chuyển tất cả các trường hợp thành null hoặc chuỗi rỗng nếu nghiệp vụ cần phân biệt chúng. Hãy thống nhất quy tắc chuẩn hóa dữ liệu ở tầng ứng dụng và schema.

### 1.1. SQL NULL có logic ba giá trị

Trong SQL, phép so sánh với NULL không trả về TRUE hoặc FALSE như so sánh thông thường. Nó trả về UNKNOWN.

Ví dụ:

~~~sql
email = NULL
email <> NULL
NOT (email = 'an@example.com')
~~~

Các biểu thức trên không kiểm tra NULL theo cách mong muốn. Với giá trị NULL, phép so sánh thông thường tạo ra UNKNOWN; điều kiện WHERE chỉ giữ các hàng mà biểu thức là TRUE.

Để kiểm tra NULL, dùng:

~~~sql
email IS NULL
email IS NOT NULL
~~~

Ví dụ:

~~~sql
SELECT id, email
FROM customer
WHERE email IS NULL;
~~~

Câu truy vấn trả về các hàng chưa có email. Muốn lấy các hàng đã có giá trị email, dùng IS NOT NULL.

### 1.2. Chuỗi rỗng được so sánh như một giá trị

Trên các hệ quản trị phân biệt chuỗi rỗng và NULL, điều kiện:

~~~sql
email = ''
~~~

tìm các hàng có chuỗi rỗng. Nó không tìm các hàng có NULL.

Điều này có thể quan trọng khi dữ liệu được ghi từ nhiều nguồn: form có thể gửi chuỗi rỗng, API có thể gửi null, còn một tác vụ import có thể ghi khoảng trắng.

Một lưu ý về tính portable: Oracle xử lý chuỗi ký tự có độ dài bằng 0 như NULL đối với kiểu ký tự thông thường. Vì vậy, truy vấn phân biệt NULL và chuỗi rỗng không cho cùng kết quả trên mọi hệ quản trị. Hãy kiểm tra hành vi của database mục tiêu khi thiết kế schema và quy tắc tìm kiếm.

### 1.3. Chuỗi chỉ có khoảng trắng

Chuỗi "   " không giống chuỗi rỗng trong Java và thường cũng không giống NULL trong database.

Có thể kiểm tra chuỗi trắng ở tầng Java:

~~~java
if (value == null) {
    // Không có giá trị.
} else if (value.isEmpty()) {
    // Chuỗi có độ dài bằng 0.
} else if (value.isBlank()) {
    // Chỉ có ký tự trắng theo định nghĩa của Java.
}
~~~

Nếu muốn tìm các hàng có chuỗi rỗng hoặc chỉ chứa khoảng trắng trong SQL, có thể dùng biểu thức TRIM tùy theo database:

~~~sql
WHERE email IS NOT NULL
  AND TRIM(email) = ''
~~~

TRIM thường loại bỏ khoảng trắng ở hai đầu theo quy tắc database. Định nghĩa whitespace, ký tự Unicode và collation có thể khác nhau; không nên giả định TRIM xử lý mọi ký tự trắng giống String.isBlank() của Java.

## 2. Dùng Criteria để kiểm tra NULL

Trong Spring Data Relational, Criteria mô tả điều kiện truy vấn. Với R2dbcEntityTemplate, có thể dùng isNull() và isNotNull() để tạo điều kiện tương ứng.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    String email
) {}
~~~

### 2.1. Tìm hàng có giá trị NULL

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(
    Criteria.where("email").isNull()
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Điều kiện này tương ứng với kiểm tra email IS NULL. Nên dùng isNull() thay vì truyền null vào is(null), vì cách viết tường minh thể hiện đúng ý định và tránh nhầm với so sánh bằng thông thường.

### 2.2. Tìm hàng không có NULL

~~~java
Query query = Query.query(
    Criteria.where("email").isNotNull()
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Điều kiện isNotNull() lấy các hàng có giá trị email. Giá trị đó có thể là chuỗi rỗng hoặc chuỗi trắng nếu dữ liệu cho phép; isNotNull() không có nghĩa là chuỗi có nội dung hữu ích.

### 2.3. Tìm chuỗi rỗng

~~~java
Query query = Query.query(
    Criteria.where("email").is("")
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Đây là phép so sánh bằng chuỗi rỗng, không phải kiểm tra NULL. Trên database coi chuỗi rỗng là NULL, kết quả sẽ tuân theo hành vi riêng của hệ quản trị đó.

### 2.4. Kết hợp NULL và chuỗi rỗng

Nếu nghiệp vụ coi cả NULL và chuỗi rỗng là “chưa cung cấp email”, có thể diễn đạt hai điều kiện bằng OR:

~~~java
Criteria missingEmail =
    Criteria.where("email").isNull()
        .or("email").is("");

Query query = Query.query(missingEmail);
~~~

Điều kiện tương ứng về mặt ý nghĩa:

~~~sql
WHERE email IS NULL OR email = ''
~~~

Hãy chỉ gộp hai trạng thái khi nghiệp vụ thực sự xem chúng là một. Nếu hệ thống cần phân biệt người dùng bỏ trống trường với nguồn dữ liệu không gửi trường, hãy giữ hai trạng thái riêng.

## 3. Điều kiện tùy chọn trong truy vấn động

Một bộ lọc tìm kiếm thường có nhiều tham số tùy chọn. Ví dụ màn hình tìm khách hàng có thể cho phép nhập tên, email và trạng thái hoạt động. Người dùng không nhập một trường thường có nghĩa là bỏ qua điều kiện đó.

Không nên tạo điều kiện so sánh bằng null cho mọi tham số. Nếu tham số không được cung cấp, hãy bỏ điều kiện tương ứng. Nếu người dùng muốn tìm những hàng có cột NULL, hãy thêm điều kiện isNull() rõ ràng.

Ví dụ:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Customer> searchCustomers(
        Long tenantId,
        String name,
        String email) {

    Criteria criteria =
        Criteria.where("tenantId").is(tenantId);

    if (name != null && !name.isBlank()) {
        criteria = criteria.and("fullName")
            .like("%" + name.trim() + "%");
    }

    if (email != null && !email.isBlank()) {
        criteria = criteria.and("email")
            .is(email.trim());
    }

    Query query = Query.query(criteria);

    return template.select(Customer.class)
        .matching(query)
        .all();
}
~~~

Trong ví dụ, tenantId là điều kiện bắt buộc. Điều kiện tên và email chỉ được thêm khi đầu vào có nội dung. Cách này tránh việc một tham số không được gửi vô tình biến thành điều kiện tìm NULL hoặc chuỗi rỗng.

### 3.1. Phân biệt “không lọc” và “tìm NULL”

Một API tìm kiếm đôi khi cần ba trạng thái cho một trường:

1. Không áp dụng bộ lọc.
2. Chỉ lấy hàng có giá trị NULL.
3. Lọc theo một giá trị cụ thể.

Nếu chỉ dùng một biến String mà null vừa có nghĩa “không gửi bộ lọc” vừa có nghĩa “tìm NULL”, ứng dụng không thể phân biệt hai ý định.

Có thể biểu diễn trạng thái lọc bằng enum:

~~~java
public enum EmailFilterMode {
    ANY,
    IS_NULL,
    EQUALS
}
~~~

Sau đó xây dựng Criteria theo trạng thái:

~~~java
Criteria criteria =
    Criteria.where("tenantId").is(tenantId);

switch (emailFilterMode) {
    case ANY -> {
        // Không thêm điều kiện email.
    }
    case IS_NULL ->
        criteria = criteria.and("email").isNull();
    case EQUALS -> {
        if (emailValue == null) {
            throw new IllegalArgumentException(
                "emailValue is required for EQUALS"
            );
        }
        criteria = criteria.and("email").is(emailValue);
    }
}
~~~

Cách biểu diễn này làm rõ ý định của caller. Với API phức tạp hơn, có thể dùng một kiểu Filter riêng để chứa mode và value thay vì nhiều tham số rời rạc.

### 3.2. Chính sách xử lý chuỗi rỗng ở đầu vào

Trước khi thêm điều kiện, cần quyết định chuỗi rỗng có ý nghĩa gì:

- Bỏ qua bộ lọc: không thêm Criteria.
- Tìm đúng chuỗi rỗng: dùng is("").
- Tìm NULL: dùng isNull().
- Tìm chuỗi chỉ có khoảng trắng: dùng chính sách trim/blank rõ ràng hoặc biểu thức database thích hợp.

Ví dụ, nếu ứng dụng xem chuỗi trắng là không nhập:

~~~java
if (name != null && !name.isBlank()) {
    criteria = criteria.and("fullName")
        .like("%" + name.trim() + "%");
}
~~~

Nếu cần phân biệt chuỗi rỗng với chuỗi trắng, không dùng isBlank() để gộp chúng. Có thể kiểm tra isEmpty() và isBlank() riêng theo quy tắc nghiệp vụ.

## 4. Tìm kiếm theo mẫu với LIKE

SQL LIKE dùng mẫu để so khớp chuỗi. Trong Spring Data R2DBC, Criteria.like(pattern) cho phép tạo điều kiện này mà vẫn dùng cơ chế bind tham số của Spring.

Hai ký tự wildcard phổ biến:

- % khớp với không hoặc nhiều ký tự.
- _ khớp chính xác một ký tự.

Ví dụ:

| Pattern | Ý nghĩa | Ví dụ khớp |
|---|---|---|
| 'An%' | Bắt đầu bằng An | An, Anh, An Nguyen |
| '%An' | Kết thúc bằng An | Tran, Nguyen An |
| '%An%' | Có chứa An | An, Nguyen An, An Binh |
| 'A_' | A và thêm đúng một ký tự | An, Ab |
| 'A__' | A và thêm đúng hai ký tự | Anh, An1 |

### 4.1. Tìm kiếm bắt đầu bằng một chuỗi

~~~java
String prefix = "Ng";

Query query = Query.query(
    Criteria.where("fullName")
        .like(prefix + "%")
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Pattern Ng% tìm các tên bắt đầu bằng Ng.

### 4.2. Tìm kiếm kết thúc bằng một chuỗi

~~~java
String suffix = "An";

Query query = Query.query(
    Criteria.where("fullName")
        .like("%" + suffix)
);
~~~

Pattern %An tìm các tên kết thúc bằng An.

### 4.3. Tìm kiếm chuỗi xuất hiện ở bất kỳ vị trí nào

~~~java
String keyword = "An";

Query query = Query.query(
    Criteria.where("fullName")
        .like("%" + keyword + "%")
);
~~~

Pattern %An% tìm các tên có chứa An ở bất kỳ vị trí nào.

### 4.4. Không để chuỗi rỗng tạo pattern khớp quá rộng

Nếu keyword là chuỗi rỗng, pattern % + keyword + % trở thành %%. Mẫu này có thể khớp với hầu hết giá trị chuỗi không NULL, làm truy vấn rộng hơn dự kiến.

Vì vậy, hãy kiểm tra đầu vào trước khi tạo pattern:

~~~java
if (keyword == null || keyword.isBlank()) {
    return Flux.empty();
}
~~~

Hoặc nếu nghiệp vụ quy định bỏ qua điều kiện keyword, hãy không thêm Criteria đó và thực hiện truy vấn theo các điều kiện còn lại. Hai cách có ý nghĩa khác nhau: trả rỗng có nghĩa không tìm kiếm khi thiếu keyword; bỏ điều kiện có nghĩa tìm theo các bộ lọc khác.

## 5. LIKE và tìm kiếm chuỗi literal

Bind tham số giúp ngăn dữ liệu đầu vào trở thành một phần cú pháp SQL. Tuy nhiên, bind tham số không tự làm mất ý nghĩa wildcard của % và _ trong LIKE.

Ví dụ người dùng nhập chuỗi 100%:

- Nếu nối trực tiếp vào pattern %100%%, ký tự % do người dùng nhập vẫn là wildcard.
- Nếu yêu cầu tìm đúng ký tự %, cần escape ký tự đó theo cú pháp LIKE của database.

Tương tự, dấu gạch dưới _ là wildcard một ký tự và cũng cần được escape khi muốn tìm đúng ký tự _.

### 5.1. Escape wildcard trong SQL

Một cách phổ biến là chọn ký tự ! làm ký tự escape:

~~~sql
SELECT id, full_name
FROM customer
WHERE full_name LIKE :pattern ESCAPE '!'
~~~

Trước khi bind, escape chính ký tự ! rồi đến % và _:

~~~java
private String escapeLikeLiteral(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
~~~

Tìm chuỗi literal ở bất kỳ vị trí nào:

~~~java
String term = "100%_ready";
String pattern = "%" + escapeLikeLiteral(term) + "%";

return databaseClient.sql("""
        SELECT id, full_name
        FROM customer
        WHERE full_name LIKE :pattern ESCAPE '!'
        """)
    .bind("pattern", pattern)
    .map((row, metadata) ->
        new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class),
            null
        )
    )
    .all();
~~~

Ví dụ dùng DatabaseClient để thể hiện rõ mệnh đề ESCAPE. Cú pháp ESCAPE và cách biểu diễn ký tự escape cần được xác nhận với hệ quản trị mục tiêu. Nếu dùng Criteria.like(), hãy kiểm tra SQL mà dialect tạo ra và khả năng chỉ định escape của phiên bản Spring Data đang dùng; không giả định mọi API LIKE đều tự escape wildcard.

### 5.2. Phân biệt SQL injection với wildcard

Hai vấn đề này khác nhau:

- SQL injection xảy ra khi dữ liệu đầu vào bị ghép vào cú pháp SQL. Dùng bind parameter để tách dữ liệu khỏi câu lệnh.
- Wildcard LIKE là hành vi hợp lệ của mẫu tìm kiếm. Dù đã bind parameter, % và _ vẫn có thể mở rộng kết quả.

Do đó, tìm kiếm literal cần cả bind parameter lẫn escape wildcard. Không dùng nối chuỗi để tạo câu SQL từ dữ liệu đầu vào.

## 6. Tìm kiếm không phân biệt chữ hoa/chữ thường

Hành vi so sánh chữ hoa/thường phụ thuộc collation và hệ quản trị. Một số database dùng collation không phân biệt hoa thường theo mặc định; database khác phân biệt.

Cách biểu diễn tương đối phổ biến là chuyển cả cột và pattern về cùng dạng:

~~~sql
SELECT id, full_name
FROM customer
WHERE LOWER(full_name) LIKE LOWER(:pattern)
~~~

Với DatabaseClient:

~~~java
String pattern = "%" + keyword.trim() + "%";

return databaseClient.sql("""
        SELECT id, full_name
        FROM customer
        WHERE LOWER(full_name) LIKE LOWER(:pattern)
        """)
    .bind("pattern", pattern)
    .map((row, metadata) ->
        new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class),
            null
        )
    )
    .all();
~~~

Một số lưu ý:

- LOWER/UPPER và collation có thể có quy tắc khác nhau đối với ngôn ngữ, dấu và Unicode.
- Áp dụng hàm lên cột có thể khiến database không sử dụng index B-tree thông thường; nếu tìm kiếm là chức năng quan trọng, cân nhắc functional index hoặc collation phù hợp.
- PostgreSQL có toán tử ILIKE, nhưng đây là cú pháp riêng của PostgreSQL và không portable.
- Không nên giả định ignore-case ở tầng Java giống với quy tắc so sánh của database.

## 7. Kết hợp nhiều kiểu điều kiện trong một truy vấn

Một bộ lọc thực tế có thể kết hợp điều kiện bắt buộc, điều kiện NULL, giá trị chính xác và LIKE.

Ví dụ:

~~~java
public Flux<Customer> search(
        Long tenantId,
        String keyword,
        Boolean active,
        boolean emailMissingOnly) {

    Criteria criteria =
        Criteria.where("tenantId").is(tenantId);

    if (keyword != null && !keyword.isBlank()) {
        criteria = criteria.and("fullName")
            .like("%" + keyword.trim() + "%");
    }

    if (active != null) {
        criteria = criteria.and("active").is(active);
    }

    if (emailMissingOnly) {
        criteria = criteria.and("email").isNull();
    }

    Query query = Query.query(criteria)
        .limit(50);

    return template.select(Customer.class)
        .matching(query)
        .all();
}
~~~

Ở đây:

- tenantId luôn được áp dụng.
- keyword chỉ tạo điều kiện LIKE khi có nội dung.
- active chỉ được áp dụng khi caller cung cấp true hoặc false.
- emailMissingOnly thêm điều kiện IS NULL khi được bật.

Boolean wrapper Boolean cho phép phân biệt null (không lọc) với true và false. Nếu dùng boolean primitive, ứng dụng không có trạng thái “không được cung cấp”.

Khi có nhiều trạng thái cho một trường, hãy dùng enum hoặc filter object thay vì để null mang nhiều ý nghĩa khác nhau.

## 8. Kết hợp OR và AND đúng logic

Criteria có thể kết hợp nhiều điều kiện. Cần chú ý thứ tự và nhóm logic vì AND và OR có độ ưu tiên khác nhau trong SQL.

Ví dụ muốn tìm khách hàng có email NULL hoặc chuỗi rỗng, đồng thời phải thuộc một tenant:

~~~java
Criteria emailMissing =
    Criteria.where("email").isNull()
        .or("email").is("");

Criteria criteria =
    Criteria.where("tenantId").is(tenantId)
        .and(emailMissing);

Query query = Query.query(criteria);
~~~

Ý nghĩa mong muốn:

~~~sql
WHERE tenant_id = :tenantId
  AND (email IS NULL OR email = '')
~~~

Khi tạo điều kiện phức tạp, hãy kiểm tra SQL được sinh ra để chắc chắn các nhánh OR được nhóm trong ngoặc đúng như nghiệp vụ. Không chỉ dựa vào cách code được thụt dòng.

Nếu API Criteria của phiên bản đang dùng không biểu diễn được nhóm điều kiện mong muốn một cách rõ ràng, có thể chuyển sang DatabaseClient với SQL tường minh và bind tham số.

## 9. Dùng derived query trong Repository

Với các điều kiện phổ biến, Spring Data R2DBC có thể tạo truy vấn từ tên phương thức repository.

Ví dụ:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByEmailIsNull();

    Flux<Customer> findByEmailIsNotNull();

    Flux<Customer> findByFullNameContaining(String fragment);

    Flux<Customer> findByFullNameStartingWith(String prefix);

    Flux<Customer> findByFullNameEndingWith(String suffix);
}
~~~

Tên phương thức diễn đạt điều kiện:

- IsNull: tìm giá trị NULL.
- IsNotNull: tìm giá trị khác NULL.
- Containing: tìm chuỗi có chứa fragment.
- StartingWith: tìm chuỗi bắt đầu bằng prefix.
- EndingWith: tìm chuỗi kết thúc bằng suffix.

Các keyword và cách tạo pattern cần được xác nhận theo phiên bản Spring Data R2DBC. Khi cần điều kiện động phức tạp, nhóm AND/OR hoặc quy tắc escape riêng, Query/Criteria hoặc DatabaseClient thường thể hiện ý định rõ hơn.

## 10. Chuẩn hóa dữ liệu trước khi lưu

Một cách giảm độ phức tạp của truy vấn là quyết định quy tắc lưu dữ liệu ngay từ đầu.

Ví dụ, API có thể chọn một trong các chính sách:

- Không nhận email: lưu NULL.
- Nhận chuỗi rỗng: chuyển thành NULL hoặc từ chối request.
- Nhận chuỗi chỉ có khoảng trắng: trim rồi xem là rỗng.
- Email có nội dung: trim, kiểm tra định dạng và lưu giá trị chuẩn hóa.

Ví dụ hàm chuẩn hóa:

~~~java
private String normalizeOptionalText(String value) {
    if (value == null) {
        return null;
    }

    String normalized = value.trim();

    return normalized.isEmpty() ? null : normalized;
}
~~~

Hàm này gộp chuỗi rỗng và chuỗi trắng thành null. Chỉ áp dụng nếu đó là chính sách nghiệp vụ; không dùng cho trường cần giữ nguyên khoảng trắng có ý nghĩa.

Chuẩn hóa ở tầng ghi giúp giảm số dạng dữ liệu cần xử lý khi tìm kiếm. Tuy nhiên, nếu database đã có dữ liệu cũ với nhiều dạng khác nhau, vẫn cần truy vấn bao phủ các trạng thái đó hoặc thực hiện migration dữ liệu.

## 11. Hiệu năng của truy vấn LIKE và NULL

Một số điểm cần cân nhắc khi truy vấn trên bảng lớn:

### 11.1. LIKE có wildcard đầu chuỗi

Điều kiện:

~~~sql
full_name LIKE 'An%'
~~~

có thể tận dụng index B-tree trong nhiều hệ quản trị và cấu hình phù hợp.

Trong khi đó:

~~~sql
full_name LIKE '%An%'
~~~

thường khó sử dụng index B-tree thông thường vì wildcard đứng đầu. Tùy database, có thể cần full-text search, trigram index hoặc giải pháp tìm kiếm chuyên biệt.

### 11.2. Hàm trên cột

Điều kiện:

~~~sql
LOWER(full_name) LIKE LOWER(:pattern)
~~~

có thể không dùng index thông thường trên full_name. Nếu cần tìm kiếm không phân biệt hoa thường ở quy mô lớn, hãy cân nhắc functional index hoặc collation phù hợp với database.

### 11.3. IS NULL và IS NOT NULL

Database có thể sử dụng index để hỗ trợ kiểm tra NULL tùy loại index, thống kê và optimizer. Hãy đo bằng EXPLAIN trên dữ liệu gần với production thay vì suy đoán chỉ từ cú pháp.

### 11.4. Tránh pattern quá rộng

Pattern %% có thể trả về rất nhiều hàng. Luôn kiểm tra đầu vào, giới hạn số kết quả và phân trang. Không tải toàn bộ bảng về ứng dụng rồi lọc bằng Java nếu database có thể thực hiện điều kiện đó.

## 12. Những lỗi thường gặp

### 12.1. Dùng is(null) để kiểm tra NULL

So sánh bằng null không diễn đạt đúng phép kiểm tra NULL trong SQL. Hãy dùng isNull().

### 12.2. Nghĩ rằng isNotNull() loại chuỗi rỗng

isNotNull() vẫn có thể trả về chuỗi rỗng hoặc chuỗi trắng. Nếu cần loại cả hai, phải thêm điều kiện tương ứng và cân nhắc khác biệt database.

### 12.3. Tham số null vừa có nghĩa bỏ lọc vừa có nghĩa tìm NULL

Hai ý định này khác nhau. Dùng enum hoặc filter object để biểu diễn rõ trạng thái bộ lọc.

### 12.4. LIKE với chuỗi rỗng tạo pattern quá rộng

Pattern %% có thể khớp hầu hết giá trị không NULL. Hãy kiểm tra chuỗi đầu vào trước khi thêm điều kiện.

### 12.5. Nghĩ bind parameter sẽ escape wildcard

Bind parameter giúp an toàn về cú pháp SQL nhưng không biến % và _ thành ký tự literal trong LIKE. Nếu cần tìm chính xác ký tự đó, phải escape theo cú pháp database.

### 12.6. Giả định mọi database xử lý chuỗi rỗng giống nhau

Oracle coi chuỗi rỗng như NULL đối với kiểu ký tự thông thường; các hệ quản trị khác có thể phân biệt. Kiểm thử trên database thực tế của ứng dụng.

### 12.7. Tìm kiếm không phân biệt hoa thường nhưng không xem xét index

LOWER(cột) có thể làm thay đổi kế hoạch sử dụng index. Với bảng lớn, hãy xem execution plan và chọn collation/index phù hợp.

### 12.8. Không nhóm điều kiện OR

Khi kết hợp tenant filter với (email IS NULL OR email = ''), phải bảo đảm nhóm OR nằm trong ngoặc. Nếu không, có thể trả về dữ liệu ngoài tenant.

## 13. Nguyên tắc triển khai

- Dùng isNull() và isNotNull() cho giá trị SQL NULL.
- Dùng is("") khi cần tìm đúng chuỗi rỗng trên database phân biệt trạng thái đó với NULL.
- Quyết định rõ chuỗi trắng được giữ, trim, từ chối hay chuyển thành NULL.
- Phân biệt tham số không được gửi với yêu cầu tìm giá trị NULL.
- Bỏ qua điều kiện khi filter không được cung cấp; chỉ thêm isNull() khi caller thực sự muốn lọc NULL.
- Dùng like(pattern) cho tìm kiếm theo mẫu và hiểu ý nghĩa của % và _.
- Bind tham số để tránh SQL injection; escape wildcard riêng khi cần tìm literal.
- Kiểm tra collation, Unicode và hành vi chuỗi rỗng trên database mục tiêu.
- Nhóm điều kiện AND/OR rõ ràng, đặc biệt khi có tenant hoặc phạm vi truy cập bắt buộc.
- Giới hạn kết quả và kiểm tra hiệu năng của pattern có wildcard đầu chuỗi.
- Dùng derived repository query cho điều kiện đơn giản; dùng Criteria hoặc DatabaseClient khi cần truy vấn động phức tạp hơn.

## 14. Ghi nhớ

NULL biểu diễn sự vắng mặt của giá trị và phải được kiểm tra bằng IS NULL hoặc IS NOT NULL. Chuỗi rỗng là một giá trị chuỗi riêng trên nhiều hệ quản trị; chuỗi trắng lại là một trường hợp khác cần chính sách chuẩn hóa. LIKE dùng % và _ làm wildcard, nên tìm kiếm literal cần escape các ký tự đó dù giá trị đã được bind an toàn.

Trong Spring Data R2DBC, Query và Criteria giúp xây dựng các điều kiện này ở mức entity. Hãy để tham số không được cung cấp làm mất điều kiện tương ứng, biểu diễn yêu cầu tìm NULL một cách tường minh, và chọn DatabaseClient khi cần SQL/ESCAPE hoặc logic database cụ thể. Quy tắc rõ ràng ngay từ đầu giúp truy vấn động có kết quả dễ dự đoán và giữ được tính portable ở mức phù hợp.

