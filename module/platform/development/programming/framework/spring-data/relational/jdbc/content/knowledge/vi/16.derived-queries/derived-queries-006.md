# In, NotIn và xử lý tập tham số rỗng

Trong Spring Data JDBC, các từ khóa suy diễn truy vấn **§In§** và **§NotIn§** cho phép lọc một thuộc tính theo một tập giá trị được truyền vào repository. Ví dụ, ứng dụng có thể tìm sản phẩm có trạng thái thuộc tập §ACTIVE§ hoặc §PENDING§, hoặc tìm sản phẩm có trạng thái không nằm trong danh sách bị loại trừ.

Cú pháp repository khá ngắn, nhưng khi tham số là collection, có một số tình huống cần xử lý rõ ràng:

- Collection có phần tử: Spring Data JDBC tạo điều kiện §IN§ hoặc §NOT IN§ và bind các giá trị.
- Collection rỗng: SQL list parameter không được bảo đảm hoạt động giống nhau trên mọi database; không nên truyền collection rỗng trực tiếp xuống repository.
- Collection là §null§: khác hoàn toàn collection rỗng và cần có hợp đồng đầu vào riêng.
- Collection chứa phần tử §null§: có thể làm điều kiện §NOT IN§ cho kết quả bất ngờ do logic ba giá trị của SQL.
- Cột được truy vấn có giá trị SQL §NULL§: cả §IN§ và §NOT IN§ đều chịu quy tắc so sánh với NULL.

Bài học giải thích cách khai báo query method, ý nghĩa của tập tham số, cách xử lý collection rỗng ở tầng service và các tình huống SQL NULL thường gặp.

## 1. In và NotIn trong truy vấn suy diễn

Spring Data JDBC phân tích tên phương thức repository để tạo điều kiện truy vấn. Hai từ khóa được dùng khi tham số đại diện cho một tập giá trị:

| Từ khóa | Ví dụ phương thức | Điều kiện logic |
| --- | --- | --- |
| §In§ | §findByStatusIn(Collection<String> statuses)§ | §status IN (:statuses)§ |
| §NotIn§ | §findByStatusNotIn(Collection<String> statuses)§ | §status NOT IN (:statuses)§ |

Giả sử bảng §products§ có các trạng thái §ACTIVE§, §PENDING§, §DISCONTINUED§. Khi truyền danh sách §["ACTIVE", "PENDING"]§:

- §In§ trả về sản phẩm có trạng thái là ACTIVE **hoặc** PENDING.
- §NotIn§ trả về sản phẩm có trạng thái không phải ACTIVE và cũng không phải PENDING, theo quy tắc SQL NULL được giải thích ở phần sau.

### 1.1. Ví dụ SQL tương ứng

§§§sql
-- In
SELECT *
FROM products
WHERE status IN ('ACTIVE', 'PENDING');

-- NotIn
SELECT *
FROM products
WHERE status NOT IN ('ACTIVE', 'PENDING');
§§§

§In§ tương đương với việc kiểm tra một giá trị có thuộc tập cho trước hay không. §NotIn§ phủ định điều kiện thành viên đó.

Không nên nhầm §NotIn§ với §Not§ trên một giá trị đơn:

§§§java
List<Product> findByStatusNot(String status);

List<Product> findByStatusNotIn(Collection<String> statuses);
§§§

Phương thức thứ nhất so sánh với **một giá trị**; phương thức thứ hai so sánh với **một tập giá trị**.

## 2. Khai báo repository với In và NotIn

Giả sử aggregate root có thuộc tính §status§:

§§§java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
        @Id Long id,
        String name,
        String status
) {
}
§§§

Repository:

§§§java
import java.util.Collection;
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<Product> findByStatusIn(Collection<String> statuses);

    List<Product> findByStatusNotIn(Collection<String> statuses);
}
§§§

Spring Data JDBC suy diễn query từ tên method:

§§§text
findByStatusIn(statuses)
       |
       v
WHERE status IN (:statuses)

findByStatusNotIn(statuses)
       |
       v
WHERE status NOT IN (:statuses)
§§§

Các tham số collection được mở rộng thành danh sách bind parameters phù hợp với số phần tử. Ví dụ danh sách hai phần tử có thể tạo SQL dạng:

§§§sql
WHERE status IN (?, ?)
§§§

Giá trị vẫn được bind qua JDBC, không nên nối chuỗi đầu vào vào SQL. Cách bind tham số vừa tránh SQL injection vừa giúp database xử lý giá trị đúng kiểu.

### 2.1. Điều kiện áp dụng query derivation

Query derivation của Spring Data JDBC có giới hạn riêng. Nó phù hợp với các thuộc tính đơn giản có thể dùng trong §WHERE§ của aggregate root mà không cần join sang quan hệ khác.

Ví dụ §status§ là property trực tiếp của §Product§:

§§§java
List<Product> findByStatusIn(Collection<String> statuses);
§§§

Nếu muốn suy diễn theo thuộc tính của một aggregate được tham chiếu hoặc một entity con nằm trong collection, không nên giả định Spring Data JDBC sẽ tự tạo join như một ORM. Hãy xem xét query SQL tường minh hoặc custom repository cho trường hợp đó.

## 3. Tập tham số có phần tử

Với tập không rỗng, ý nghĩa tương đối trực tiếp.

Giả sử dữ liệu:

§§§text
id | name          | status
---+---------------+--------------
1  | Keyboard      | ACTIVE
2  | Mouse         | PENDING
3  | Monitor       | DISCONTINUED
4  | Webcam        | ACTIVE
5  | USB Hub       | NULL
§§§

Gọi:

§§§java
List<Product> products =
        repository.findByStatusIn(List.of("ACTIVE", "PENDING"));
§§§

Kết quả gồm Keyboard, Mouse và Webcam. Các hàng có trạng thái DISCONTINUED hoặc NULL không được chọn.

Gọi:

§§§java
List<Product> products =
        repository.findByStatusNotIn(List.of("ACTIVE", "PENDING"));
§§§

Với SQL thông thường, kết quả gồm Monitor có trạng thái DISCONTINUED. Hàng Webcam/Keyboard/Mouse bị loại vì khớp danh sách; hàng USB Hub có status NULL cũng bị loại do phép so sánh trả về UNKNOWN.

Điểm về NULL rất quan trọng và sẽ được phân tích riêng ở phần 8.

## 4. Tập tham số rỗng không phải một danh sách bình thường

Một collection rỗng có kích thước bằng 0:

§§§java
List<String> statuses = List.of();

System.out.println(statuses.isEmpty()); // true
§§§

Về mặt nghiệp vụ, nó có thể có nhiều ý nghĩa:

- Người dùng không chọn trạng thái nào.
- Người dùng muốn kết quả không chứa bất kỳ trạng thái nào.
- Người dùng không muốn loại trừ trạng thái nào.
- Bộ lọc chưa được cung cấp hoặc chưa được khởi tạo.

Những ý nghĩa này không giống nhau. Repository không thể tự đoán hợp đồng API hoặc ý định của người dùng.

### 4.1. Tập rỗng với In

Theo logic tập hợp, không có phần tử nào thuộc tập rỗng. Vì vậy, nếu yêu cầu nghiệp vụ là “tìm sản phẩm có status thuộc danh sách đã chọn” và danh sách không có phần tử, kết quả hợp lý là **không có sản phẩm nào**.

Có thể biểu diễn ở tầng service bằng cách trả về collection rỗng ngay:

§§§java
public List<Product> findByStatuses(
        Collection<String> statuses
) {
    if (statuses.isEmpty()) {
        return List.of();
    }

    return repository.findByStatusIn(statuses);
}
§§§

Cách này không phát SQL vô ích và làm rõ ý nghĩa của bộ lọc.

Nhưng nếu giao diện quy định “người dùng chưa chọn status nghĩa là không áp dụng bộ lọc”, thì phải bỏ qua điều kiện và gọi truy vấn không lọc:

§§§java
public List<Product> searchByOptionalStatuses(
        Collection<String> statuses
) {
    if (statuses == null || statuses.isEmpty()) {
        return findAllProducts();
    }

    return repository.findByStatusIn(statuses);
}
§§§

Đây là một hợp đồng khác. **Empty IN có thể mang nghĩa no matches hoặc no filter tùy nghiệp vụ**, nhưng cần quyết định trước khi gọi repository.

### 4.2. Tập rỗng với NotIn

Theo logic tập hợp, không có giá trị nào bị loại trừ nếu tập loại trừ rỗng. Vì vậy, nếu nghiệp vụ là “tìm mọi sản phẩm trừ những trạng thái nằm trong danh sách”, danh sách rỗng có nghĩa **không loại trừ gì cả**. Service có thể bỏ điều kiện và trả về tất cả sản phẩm:

§§§java
public List<Product> findByStatusesNotIn(
        Collection<String> excludedStatuses
) {
    if (excludedStatuses.isEmpty()) {
        return findAllProducts();
    }

    return repository.findByStatusNotIn(excludedStatuses);
}
§§§

Nếu nghiệp vụ của ứng dụng định nghĩa danh sách rỗng là “không có lựa chọn hợp lệ, trả về không kết quả”, thì phải trả collection rỗng theo hợp đồng đó. Không có một ý nghĩa API duy nhất cho mọi ứng dụng.

### 4.3. Vì sao không truyền collection rỗng thẳng xuống repository?

Spring Data JDBC tạo query có named parameter dạng §IN (:statuses)§ hoặc §NOT IN (:statuses)§. Tầng Spring JDBC mở rộng collection thành các placeholder JDBC.

Khi collection không có phần tử, không có placeholder nào để mở rộng. Câu SQL có thể trở thành dạng:

§§§sql
WHERE status IN ()
§§§

hoặc:

§§§sql
WHERE status NOT IN ()
§§§

Cú pháp danh sách rỗng không được hỗ trợ đồng nhất bởi mọi hệ quản trị cơ sở dữ liệu. Có database chấp nhận một dạng, có database báo lỗi cú pháp; không nên dựa vào hành vi của một dialect để xây dựng logic ứng dụng có thể chạy trên database khác.

Tài liệu Spring Framework của §NamedParameterUtils§ cảnh báo rằng danh sách bind parameters không nên rỗng; danh sách rỗng hoặc quá lớn không được bảo đảm hỗ trợ và phụ thuộc vendor. Vì vậy, **hãy xử lý collection rỗng trước khi gọi query method**.

## 5. Phân biệt null collection, empty collection và collection có phần tử

Ba đầu vào sau khác nhau:

§§§java
Collection<String> a = null;
Collection<String> b = List.of();
Collection<String> c = List.of("ACTIVE", "PENDING");
§§§

| Đầu vào | Ý nghĩa ở Java | Cần quyết định ở tầng service |
| --- | --- | --- |
| §null§ | Không có object collection để xử lý. | Từ chối, hiểu là filter bị bỏ qua, hoặc xử lý theo hợp đồng API. |
| Collection rỗng | Có collection nhưng không có phần tử. | Với IN thường là no matches; với NOT IN thường là exclude nothing; có thể khác nếu API quy định no filter. |
| Collection có phần tử | Có tập giá trị để bind. | Gọi repository sau khi chuẩn hóa và kiểm tra dữ liệu. |

Không nên viết:

§§§java
if (statuses == null || statuses.isEmpty()) {
    return List.of();
}
§§§

một cách máy móc cho mọi query. Đối với §NotIn§, điều kiện đó có thể sai nghiệp vụ: danh sách rỗng thường có nghĩa là không loại trừ sản phẩm nào, tức là trả về tất cả.

Hãy định nghĩa hợp đồng của từng use case, không dùng một helper xử lý rỗng chung cho cả §In§ và §NotIn§ nếu chúng có semantics khác nhau.

### 5.1. Ví dụ API tìm kiếm

Giả sử API nhận bộ lọc:

§§§json
{
  "statuses": []
}
§§§

Có ít nhất hai cách hiểu:

- **Filter mode:** mảng rỗng nghĩa là không có trạng thái nào được chọn, trả về không kết quả.
- **Optional filter mode:** mảng rỗng nghĩa là người dùng chưa lọc theo status, trả về mọi trạng thái.

Cả hai đều có thể hợp lý. Backend cần ghi rõ contract và xử lý trước repository. Không nên để một cú pháp SQL tình cờ quyết định hành vi API.

## 6. Chuẩn hóa và kiểm tra tập tham số trước khi query

Tầng service là nơi phù hợp để:

- Kiểm tra collection có null hay không.
- Xử lý collection rỗng theo hợp đồng nghiệp vụ.
- Loại bỏ giá trị trùng nếu trùng không mang ý nghĩa.
- Kiểm tra phần tử null.
- Giới hạn kích thước danh sách nếu API có giới hạn.
- Chuẩn hóa enum, mã trạng thái hoặc ID trước khi gọi repository.

Ví dụ một helper chỉ chấp nhận collection không null, không chứa phần tử null và loại bỏ phần tử trùng:

§§§java
import java.util.Collection;
import java.util.List;
import java.util.Objects;

private static List<String> normalizeStatuses(
        Collection<String> statuses
) {
    Objects.requireNonNull(statuses, "statuses must not be null");

    if (statuses.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException(
                "statuses must not contain null"
        );
    }

    return statuses.stream()
            .map(String::trim)
            .filter(value -> !value.isEmpty())
            .distinct()
            .toList();
}
§§§

Nếu chuỗi rỗng không hợp lệ, có thể ném exception thay vì loại bỏ; quyết định phải thống nhất với hợp đồng API. Đừng âm thầm biến một input không hợp lệ thành một tập khác nếu điều đó có thể làm thay đổi kết quả nghiệp vụ.

### 6.1. Xử lý In

§§§java
public List<Product> findByStatuses(
        Collection<String> requestedStatuses
) {
    List<String> statuses = normalizeStatuses(requestedStatuses);

    if (statuses.isEmpty()) {
        return List.of();
    }

    return repository.findByStatusIn(statuses);
}
§§§

Đây là contract “tập rỗng nghĩa là không có trạng thái nào được chọn, nên không có kết quả”.

Nếu API dùng empty collection để chỉ “không áp dụng bộ lọc”, hãy trả về truy vấn không lọc thay vì §List.of()§.

### 6.2. Xử lý NotIn

Với contract “tập rỗng nghĩa là không loại trừ gì”, có thể viết:

§§§java
public List<Product> findByExcludedStatuses(
        Collection<String> requestedExcludedStatuses
) {
    List<String> excluded =
            normalizeStatuses(requestedExcludedStatuses);

    if (excluded.isEmpty()) {
        return findAllProducts();
    }

    return repository.findByStatusNotIn(excluded);
}
§§§

Phương thức §findAllProducts()§ là helper chuyển kết quả §CrudRepository.findAll()§ thành §List§ nếu repository không dùng §ListCrudRepository§:

§§§java
private List<Product> findAllProducts() {
    List<Product> result = new ArrayList<>();
    repository.findAll().forEach(result::add);
    return result;
}
§§§

Nếu dự án đang dùng §ListCrudRepository§, có thể nhận §List§ trực tiếp từ §findAll()§. Hãy dùng kiểu repository phù hợp với phiên bản Spring Data Commons của dự án.

### 6.3. Giới hạn kích thước tập

Một danh sách hàng nghìn ID có thể tạo hàng nghìn bind parameters. Cần cân nhắc:

- Giới hạn số phần tử được nhận từ API.
- Chia thành batch nếu semantics cho phép và tổng hợp kết quả đúng cách.
- Dùng temporary/staging table rồi join khi tập lớn.
- Dùng array parameter hoặc table-valued parameter nếu database hỗ trợ và có custom mapping phù hợp.
- Dùng một bảng quan hệ hoặc query model phù hợp thay vì truyền một danh sách cực lớn.

Spring Framework ghi rõ danh sách bind parameters nên được giới hạn ở khoảng 100 phần tử hoặc ít hơn để tránh phụ thuộc vendor; đây là hướng dẫn thận trọng của API named-parameter, **không phải một giới hạn cứng giống nhau cho mọi database**. Database và driver còn có giới hạn bind parameter riêng.

## 7. Ví dụ repository và service hoàn chỉnh

Aggregate:

§§§java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
        @Id Long id,
        String name,
        String status
) {
}
§§§

Repository:

§§§java
import java.util.Collection;
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<Product> findByStatusIn(Collection<String> statuses);

    List<Product> findByStatusNotIn(Collection<String> statuses);
}
§§§

Service:

§§§java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> findMatchingStatuses(
            Collection<String> requestedStatuses
    ) {
        List<String> statuses = normalize(requestedStatuses);

        // Contract: empty IN means no status matches.
        if (statuses.isEmpty()) {
            return List.of();
        }

        return repository.findByStatusIn(statuses);
    }

    public List<Product> findNotMatchingStatuses(
            Collection<String> requestedExcludedStatuses
    ) {
        List<String> excluded = normalize(requestedExcludedStatuses);

        // Contract: empty NOT IN means exclude nothing.
        if (excluded.isEmpty()) {
            return findAll();
        }

        return repository.findByStatusNotIn(excluded);
    }

    private List<String> normalize(Collection<String> values) {
        Objects.requireNonNull(values, "values must not be null");

        if (values.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                    "Filter values must not contain null"
            );
        }

        return values.stream()
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .distinct()
                .toList();
    }

    private List<Product> findAll() {
        List<Product> products = new ArrayList<>();
        repository.findAll().forEach(products::add);
        return products;
    }
}
§§§

Service này thể hiện hai semantics khác nhau:

- §findMatchingStatuses(empty)§ trả danh sách rỗng.
- §findNotMatchingStatuses(empty)§ bỏ điều kiện loại trừ và trả tất cả sản phẩm.

Nếu API quy định empty là “filter không được cung cấp”, cả hai luồng có thể cần gọi §findAll()§. Hãy sửa nhánh service theo contract thật của ứng dụng.

## 8. SQL NULL trong cột được lọc

Ngay cả khi collection tham số không rỗng, §IN§ và §NOT IN§ vẫn bị ảnh hưởng bởi giá trị SQL NULL ở cột.

SQL dùng **logic ba giá trị**: §TRUE§, §FALSE§ và §UNKNOWN§. Điều kiện §WHERE§ chỉ giữ hàng khi biểu thức là §TRUE§; §FALSE§ và §UNKNOWN§ đều không được chọn.

Giả sử §status§ có thể là NULL:

§§§sql
SELECT *
FROM products
WHERE status NOT IN ('ACTIVE', 'PENDING');
§§§

Hàng có §status IS NULL§ không được chọn, vì phép so sánh với NULL cho kết quả UNKNOWN.

### 8.1. Bảng kết quả logic

Với tập §('ACTIVE', 'PENDING')§:

| Giá trị cột | §status IN (...)§ | §status NOT IN (...)§ |
| --- | --- | --- |
| §'ACTIVE'§ | TRUE | FALSE |
| §'PENDING'§ | TRUE | FALSE |
| §'DISCONTINUED'§ | FALSE | TRUE |
| §NULL§ | UNKNOWN | UNKNOWN |

Nếu yêu cầu nghiệp vụ của §NotIn§ là “không thuộc danh sách hoặc chưa có trạng thái”, phải viết điều kiện thêm:

§§§sql
SELECT *
FROM products
WHERE status NOT IN ('ACTIVE', 'PENDING')
   OR status IS NULL;
§§§

Nếu muốn chỉ lấy những hàng có status khác NULL và không nằm trong danh sách:

§§§sql
SELECT *
FROM products
WHERE status IS NOT NULL
  AND status NOT IN ('ACTIVE', 'PENDING');
§§§

Không nên mặc định §NotIn§ có nghĩa “mọi giá trị khác danh sách, kể cả NULL”. SQL không diễn giải như vậy.

### 8.2. Cột NULL với In

§IN§ cũng không tự tìm các hàng có cột NULL:

§§§sql
SELECT *
FROM products
WHERE status IN ('ACTIVE', 'PENDING');
§§§

Nếu muốn lấy cả các sản phẩm chưa có status:

§§§sql
SELECT *
FROM products
WHERE status IN ('ACTIVE', 'PENDING')
   OR status IS NULL;
§§§

Nếu cần truy vấn này thường xuyên, có thể tạo method derived phù hợp với điều kiện OR trên cùng property nếu cú pháp và phiên bản hỗ trợ, hoặc dùng §@Query§ tường minh.

## 9. Phần tử NULL bên trong collection tham số

Một trường hợp khác với cột NULL là **collection đầu vào chứa một phần tử Java null**.

Ví dụ:

§§§java
List<String> statuses =
        Arrays.asList("ACTIVE", null);
§§§

Khi mở rộng thành SQL, điều kiện có thể tương đương:

§§§sql
WHERE status NOT IN ('ACTIVE', NULL)
§§§

Với §status = 'DISCONTINUED'§, database phải đánh giá:

§§§text
'DISCONTINUED' <> 'ACTIVE'  -> TRUE
'DISCONTINUED' <> NULL      -> UNKNOWN

TRUE AND UNKNOWN            -> UNKNOWN
§§§

Vì §WHERE§ chỉ nhận TRUE, hàng DISCONTINUED cũng bị loại. Một giá trị NULL trong danh sách §NOT IN§ có thể làm các hàng không khớp thông thường không được trả về như mong đợi.

Với §IN§, phần tử NULL cũng không có nghĩa “hãy tìm các hàng có cột NULL”. Ví dụ §status IN ('ACTIVE', NULL)§ vẫn không trả về hàng có status NULL; kết quả so sánh ở hàng đó là UNKNOWN.

**Khuyến nghị:** không đưa null vào collection của §In§/§NotIn§. Hãy tách yêu cầu tìm NULL thành điều kiện §IS NULL§ riêng.

Nếu muốn lọc trạng thái ACTIVE hoặc NULL:

§§§sql
WHERE status = 'ACTIVE'
   OR status IS NULL
§§§

Nếu muốn lọc những trạng thái không phải ACTIVE, nhưng vẫn loại NULL:

§§§sql
WHERE status IS NOT NULL
  AND status <> 'ACTIVE'
§§§

Nếu muốn lọc những trạng thái không phải ACTIVE và giữ cả NULL:

§§§sql
WHERE status <> 'ACTIVE'
   OR status IS NULL
§§§

### 9.1. Vì sao service nên từ chối null element?

Từ chối null giúp tránh một query có semantics khó đoán đối với người gọi:

§§§java
if (statuses.stream().anyMatch(Objects::isNull)) {
    throw new IllegalArgumentException(
            "Use an explicit null predicate instead of null in the IN list"
    );
}
§§§

Nếu contract của ứng dụng muốn bỏ qua các phần tử null, có thể filter chúng ra trước khi query, nhưng cần làm rõ điều đó trong API. Không nên âm thầm coi null như một giá trị có thể khớp SQL NULL.

## 10. NULL collection parameter khác NULL element

Ba tình huống sau phải được xử lý riêng:

§§§java
Collection<String> statuses = null;              // Collection null
Collection<String> empty = List.of();            // Collection rỗng
Collection<String> containsNull =
        Arrays.asList("ACTIVE", null);            // Có phần tử null
§§§

| Tình huống | Vấn đề | Xử lý khuyến nghị |
| --- | --- | --- |
| Collection null | Không rõ caller bỏ filter hay gửi input không hợp lệ. | Xác định contract; thường validate/reject hoặc xử lý như filter absent ở service. |
| Collection rỗng | Không có placeholder cho IN list. | Xử lý theo semantics nghiệp vụ trước khi gọi repository. |
| Collection chứa null | SQL three-valued logic có thể làm NOT IN không trả kết quả mong đợi. | Từ chối, loại bỏ có chủ đích hoặc biểu diễn NULL bằng điều kiện riêng. |

Đừng dùng §null§ và collection rỗng như hai cách viết tương đương của “không lọc”. Chúng là hai trạng thái đầu vào khác nhau và nên có hợp đồng API riêng.

## 11. Kết hợp In/NotIn với điều kiện khác

Query derivation cho phép kết hợp điều kiện bằng §And§ và §Or§ khi các thuộc tính nằm trong phạm vi hỗ trợ.

Ví dụ:

§§§java
List<Product> findByStatusInAndActiveTrue(
        Collection<String> statuses
);

List<Product> findByStatusNotInAndCategoryId(
        Collection<String> excludedStatuses,
        Long categoryId
);
§§§

Ý nghĩa:

§§§sql
WHERE status IN (:statuses)
  AND active = TRUE
§§§

và:

§§§sql
WHERE status NOT IN (:excludedStatuses)
  AND category_id = :categoryId
§§§

Tuy nhiên, nếu collection rỗng, service vẫn cần xử lý trước khi gọi các method này. Chẳng hạn §In(empty)§ có thể khiến toàn bộ điều kiện AND không thể có kết quả; §NotIn(empty)§ có thể bỏ riêng điều kiện NOT IN nhưng vẫn giữ điều kiện category.

Không nên bỏ toàn bộ query chỉ vì một tập tham số rỗng nếu các điều kiện còn lại vẫn có ý nghĩa. Hãy xây dựng contract cho từng bộ lọc.

### 11.1. Ví dụ tìm theo category và danh sách trạng thái

§§§java
public List<Product> findProducts(
        Long categoryId,
        Collection<String> statuses
) {
    List<String> normalized = normalize(statuses);

    if (normalized.isEmpty()) {
        return List.of();
    }

    return repository.findByCategoryIdAndStatusIn(
            categoryId,
            normalized
    );
}
§§§

Nếu status filter là tùy chọn, có thể cần hai method hoặc custom query để bỏ riêng predicate status khi danh sách rỗng. Không nên gọi method §In§ với list rỗng rồi hy vọng database tự hiểu là bỏ filter.

## 12. Khi tập tham số quá lớn

§IN§ và §NOT IN§ rất tiện cho tập nhỏ, nhưng không phải cách tối ưu cho mọi kích thước.

Ví dụ một request truyền 20.000 ID có thể dẫn đến:

- Một SQL statement rất dài.
- Rất nhiều bind parameters.
- Chạm giới hạn parameter của database/driver.
- Tăng chi phí parse/plan SQL.
- Tăng bộ nhớ và thời gian truyền dữ liệu.
- Khó tận dụng plan cache nếu số lượng placeholder thay đổi liên tục.

Một số hướng xử lý:

| Quy mô/tình huống | Hướng cân nhắc |
| --- | --- |
| Tập nhỏ, vài giá trị | Derived query §In§/§NotIn§ thường phù hợp. |
| Tập vừa, có giới hạn rõ | Validate kích thước; kiểm tra giới hạn DB/driver. |
| Tập lớn, cần chia batch | Chia tập thành nhiều truy vấn và hợp nhất kết quả theo semantics cẩn thận. |
| Tập rất lớn hoặc được tái sử dụng | Đưa ID vào staging/temp table rồi JOIN. |
| Database hỗ trợ array/table-valued parameter | Dùng tính năng riêng của database qua custom repository/conversion phù hợp. |
| Dữ liệu đầu vào vốn là một quan hệ nghiệp vụ | Mô hình hóa thành bảng quan hệ thay vì truyền danh sách khổng lồ. |

### 12.1. Chia batch không đơn giản với NotIn

Với §In§, chia tập thành các batch có thể lấy kết quả từng batch rồi hợp nhất, nếu không có pagination/sort/limit gây trùng hoặc sai thứ tự.

Với §NotIn§, không thể đơn giản chạy nhiều truy vấn §NOT IN§ theo từng batch rồi hợp nhất:

§§§text
NOT IN (batch A)
AND NOT IN (batch B)
§§§

Để loại toàn bộ phần tử của hai batch, điều kiện phải được kết hợp bằng AND. Nếu hợp nhất kết quả của các truy vấn bằng OR/union, có thể trả lại các hàng cần loại trừ. Cần thiết kế query và phép hợp nhất theo đúng logic tập hợp.

Đối với tập loại trừ lớn, staging table hoặc bảng tham chiếu thường dễ kiểm soát hơn việc ghép hàng trăm truy vấn §NOT IN§.

## 13. Khi nào dùng derived query, khi nào dùng @Query?

Derived query rõ ràng khi điều kiện đơn giản:

§§§java
List<Product> findByStatusIn(Collection<String> statuses);

List<Product> findByStatusNotIn(Collection<String> statuses);
§§§

Nếu cần biểu diễn điều kiện phức tạp như:

§§§sql
WHERE status NOT IN (:excluded)
   OR status IS NULL
§§§

có thể dùng §@Query§:

§§§java
import java.util.Collection;
import java.util.List;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
        SELECT id, name, status
        FROM products
        WHERE status NOT IN (:excluded)
           OR status IS NULL
        """)
List<Product> findByStatusNotInOrStatusIsNull(
        @Param("excluded") Collection<String> excluded
);
§§§

Đây là ví dụ cho trường hợp §excluded§ đã được kiểm tra **không rỗng và không chứa null** ở service. Nếu collection rỗng, vẫn cần nhánh xử lý trước repository; §@Query§ không tự giải quyết vấn đề empty list.

Khi dùng query string, cần trả về các cột phù hợp với mapping của aggregate. Với query này, §id§, §name§ và §status§ là toàn bộ thuộc tính của §Product§ trong ví dụ.

Nếu cần điều kiện động tùy theo nhiều filter, custom repository hoặc query builder có thể phù hợp hơn một method name dài.

## 14. Những lỗi thường gặp

**“In với list rỗng luôn trả về danh sách rỗng.”** Đây là semantics mong muốn ở tầng nghiệp vụ theo logic tập hợp, nhưng SQL list rỗng không được hỗ trợ đồng nhất. Hãy trả collection rỗng ở service thay vì gửi list rỗng xuống repository.

**“NotIn với list rỗng luôn trả về tất cả hàng.”** Không nên dựa vào SQL §NOT IN ()§. Nếu nghiệp vụ là không loại trừ gì, bỏ predicate và gọi truy vấn phù hợp.

**“Null collection cũng giống empty collection.”** Không. Null có thể nghĩa là filter absent hoặc input sai; empty là collection có tồn tại nhưng không có phần tử.

**“Đưa null vào danh sách là cách tìm cột NULL.”** Không đúng. Dùng §IS NULL§ hoặc §OR status IS NULL§.

**“NotIn tự trả về cả các hàng có cột NULL.”** Không đúng. §NULL NOT IN (...)§ cho kết quả UNKNOWN và bị loại bởi WHERE, trừ khi viết thêm điều kiện IS NULL.

**“Có thể bỏ qua việc kiểm tra phần tử null.”** Không nên. Một phần tử null trong §NOT IN§ có thể làm các hàng khác không được chọn như mong đợi.

**“Spring Data JDBC tự loại bỏ giá trị trùng.”** Không nên giả định. Nếu tập đầu vào có nhiều phần tử giống nhau và điều đó không mang ý nghĩa, có thể chuẩn hóa bằng §distinct()§ trước khi gọi repository.

**“Danh sách càng lớn càng tốt vì chỉ là một câu SQL.”** Không đúng. Database và driver có giới hạn bind parameters; SQL quá lớn có thể chậm và tốn tài nguyên.

**“Dùng NotIn để thay cho điều kiện null.”** Không đúng. §NOT IN§ và §IS NOT NULL§ là hai điều kiện khác nhau.

**“Derived query tự join đến mọi property.”** Không đúng trong Spring Data JDBC. Query derivation có giới hạn về property có thể dùng trực tiếp trong WHERE mà không cần join.

## 15. Quy trình xử lý In/NotIn an toàn

Khi nhận một tập tham số để truy vấn, hãy thực hiện:

1. **Xác định contract:** empty có nghĩa no matches, no filter hay exclude nothing?
2. **Kiểm tra collection null:** reject hoặc chuyển thành trạng thái filter absent theo hợp đồng.
3. **Kiểm tra phần tử null:** từ chối hoặc xử lý riêng bằng predicate IS NULL.
4. **Chuẩn hóa giá trị:** trim/convert enum/deduplicate nếu nghiệp vụ cho phép.
5. **Xử lý collection rỗng:** quyết định kết quả ngay ở service, không gọi repository với list rỗng.
6. **Giới hạn kích thước:** tránh vượt giới hạn database/driver.
7. **Gọi query method:** dùng In/NotIn cho tập nhỏ và thuộc tính root đơn giản.
8. **Xem xét SQL NULL ở cột:** nếu cần bao gồm NULL, thêm predicate tường minh.
9. **Đo truy vấn:** với tập lớn, kiểm tra execution plan và cân nhắc staging table hoặc custom SQL.

§§§mermaid
flowchart TD
    A["Nhận Collection filter"] --> B{"Collection null?"}
    B -->|Yes| C["Reject hoặc xử lý filter absent<br/>theo API contract"]
    B -->|No| D{"Có phần tử null?"}
    D -->|Yes| E["Reject hoặc tách predicate IS NULL"]
    D -->|No| F["Chuẩn hóa / distinct / validate size"]
    F --> G{"Collection rỗng?"}
    G -->|Yes| H{"In hay NotIn<br/>và contract là gì?"}
    H --> I["In: no matches hoặc bỏ filter"]
    H --> J["NotIn: exclude nothing hoặc theo contract"]
    G -->|No| K["Gọi repository In / NotIn"]
    K --> L["Đánh giá SQL NULL ở cột"]
    L --> M["Trả kết quả"]
§§§

## 16. Bài tập thực hành

Tạo bảng §products§ với các cột §id§, §name§ và §status§. Thêm dữ liệu gồm ACTIVE, PENDING, DISCONTINUED và một hàng có status NULL.

### Bài 1: In với tập có phần tử

1. Khai báo §findByStatusIn(Collection<String> statuses)§.
2. Truyền §["ACTIVE", "PENDING"]§.
3. Xác nhận chỉ các trạng thái thuộc danh sách được trả về.

### Bài 2: NotIn với tập có phần tử

1. Khai báo §findByStatusNotIn(Collection<String> statuses)§.
2. Truyền §["ACTIVE", "PENDING"]§.
3. Quan sát hàng DISCONTINUED được trả về.
4. Quan sát hàng có status NULL bị loại.
5. Viết query có thêm §OR status IS NULL§ và so sánh.

### Bài 3: Collection rỗng

1. Gọi service §findMatchingStatuses(List.of())§.
2. Xác nhận service trả list rỗng theo contract no matches mà không gọi repository.
3. Gọi §findNotMatchingStatuses(List.of())§.
4. Xác nhận service bỏ predicate và trả tất cả sản phẩm theo contract exclude nothing.
5. Thử thay contract empty thành no filter và điều chỉnh nhánh service.

### Bài 4: Collection null

1. Truyền §null§ cho service.
2. Xác nhận đầu vào bị từ chối hoặc xử lý theo contract đã chọn.
3. Không để lỗi null phát sinh muộn trong quá trình tạo SQL.

### Bài 5: Collection chứa null

1. Truyền §["ACTIVE", null]§ cho method NotIn.
2. Quan sát logic SQL ba giá trị.
3. Thay bằng validation từ chối null.
4. Nếu nghiệp vụ muốn bao gồm status NULL, viết predicate §OR status IS NULL§ riêng.

### Bài 6: Tập lớn

1. Thử danh sách ID có số lượng tăng dần.
2. Quan sát số placeholder và giới hạn database/driver.
3. So sánh truy vấn IN list với staging table hoặc giải pháp database-specific nếu tập lớn.
4. Ghi lại execution plan và thời gian cho cùng dữ liệu.

## 17. Ghi nhớ

- §In§ tạo điều kiện §property IN (:values)§; §NotIn§ tạo §property NOT IN (:values)§.
- Spring Data JDBC hỗ trợ hai từ khóa này trong query derivation với tham số collection.
- Collection có phần tử được mở rộng thành các bind parameters JDBC; không nối chuỗi đầu vào vào SQL.
- Collection rỗng không được bảo đảm hỗ trợ đồng nhất bởi database. Hãy xử lý ở service trước khi gọi repository.
- Theo logic tập hợp, §In(empty)§ thường mang nghĩa không có kết quả; §NotIn(empty)§ thường mang nghĩa không loại trừ gì. Hợp đồng API có thể chọn semantics khác nhưng phải được xác định rõ.
- Collection null, collection rỗng và collection chứa null là ba tình huống khác nhau.
- SQL NULL trong collection tham số hoặc trong cột có thể làm §IN§/§NOT IN§ trả UNKNOWN; §WHERE§ không giữ hàng UNKNOWN.
- Dùng §IS NULL§/§IS NOT NULL§ khi cần xử lý giá trị NULL; không đưa null vào danh sách để thay thế predicate đó.
- Danh sách quá lớn có thể vượt giới hạn bind parameters hoặc làm query kém hiệu quả; cân nhắc batch, staging table hoặc cơ chế riêng của database.
- Query derivation của Spring Data JDBC giới hạn ở các property có thể dùng trong WHERE mà không cần join.

Khi sử dụng §In§ và §NotIn§, điều cần kiểm soát không chỉ là cú pháp tên method mà còn là **ý nghĩa của tập tham số**. Xác định rõ collection rỗng, null collection, phần tử null và SQL NULL giúp truy vấn có kết quả nhất quán giữa môi trường và đúng với hợp đồng nghiệp vụ.

## Tài liệu tham khảo

- [Spring Data Relational — Query Methods (JDBC)](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Framework — NamedParameterUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterUtils.html)
- [Spring Data Relational — Query Predicate Keywords](https://docs.spring.io/spring-data/relational/reference/repositories/query-keywords-reference.html)

