# Chuỗi, số nguyên, số thực, boolean và giới hạn miền giá trị

Khi ánh xạ entity bằng Spring Data Neo4j (SDN), kiểu Java của mỗi thuộc tính cần phù hợp với kiểu property mà Neo4j lưu trữ và quy tắc nghiệp vụ của ứng dụng. Chuỗi, số nguyên, số thực và boolean là những kiểu cơ bản thường xuất hiện trong node. Tuy nhiên, chọn đúng kiểu dữ liệu mới chỉ là bước đầu: một số lượng tồn kho còn phải không âm, điểm đánh giá phải nằm trong khoảng cho phép, tên phải có độ dài hợp lý và trạng thái bắt buộc phải được cung cấp.

Bài học này giải thích cách chọn kiểu Java, giới hạn lưu trữ của Neo4j, cách biểu diễn giá trị thiếu, cách kiểm tra miền giá trị bằng Bean Validation và cách bảo vệ dữ liệu khi ghi qua repository hoặc Cypher.

## Kiểu property trong Neo4j và kiểu Java trong SDN

Neo4j lưu property dưới các kiểu dữ liệu nguyên thủy mà graph database hỗ trợ. SDN chuyển đổi giữa kiểu Java trong entity và kiểu property tương ứng khi đọc hoặc ghi node.

| Kiểu Java thường dùng | Kiểu property Neo4j | Ví dụ |
|---|---|---|
| **String** | **STRING** | "Neo4j" |
| **Integer**, **int** | **INTEGER** | 42 |
| **Long**, **long** | **INTEGER** | 9000000000 |
| **Float**, **float** | **FLOAT** | 3.14 |
| **Double**, **double** | **FLOAT** | 3.1415926535 |
| **Boolean**, **boolean** | **BOOLEAN** | true |

Neo4j không lưu riêng kiểu Integer và Long: cả hai đều được lưu thành số nguyên 64-bit. Tương tự, property FLOAT của Neo4j là số thực 64-bit theo dạng double precision. Nếu dùng Java Float, độ chính xác đã bị giới hạn ở 32-bit trước khi giá trị được ghi; với dữ liệu số thực cần độ chính xác tốt hơn, thường nên chọn Double.

Kiểu Java cần được chọn theo ý nghĩa và phạm vi dữ liệu. Một số lượng hàng hóa nhỏ có thể vừa Integer, nhưng số đếm lớn, số tiền tính theo đơn vị nhỏ nhất hoặc giá trị có thể vượt giới hạn 32-bit nên cân nhắc Long. Đối với cờ bật/tắt, dùng Boolean. Đối với tên, mã và nội dung văn bản, dùng String.

## Chuỗi: nội dung, độ dài và chuẩn hóa

String phù hợp với dữ liệu văn bản như tên, mã sản phẩm, email, trạng thái dạng mã và mô tả ngắn. Neo4j lưu chuỗi dưới kiểu STRING; không nên lưu một giá trị số dưới dạng chuỗi nếu cần so sánh số học, sắp xếp theo giá trị hoặc tính tổng.

Ví dụ, mã sản phẩm nên là chuỗi vì nó là mã nhận diện, có thể chứa chữ cái, số 0 ở đầu hoặc dấu phân cách:

~~~cypher
CREATE (:Product {
    sku: "SKU-00042",
    name: "Graph Database Handbook",
    status: "ACTIVE"
});
~~~

Nếu lưu sku dưới kiểu số, giá trị 00042 có thể mất các số 0 đầu và mã không còn giữ đúng định dạng. Mã định danh, số điện thoại, mã bưu chính và số tài khoản thường nên được xem là chuỗi nếu ứng dụng không thực hiện phép tính số học trên chúng.

### Độ dài và nội dung hợp lệ

Một chuỗi có thể hợp lệ về kiểu nhưng sai quy tắc nghiệp vụ. Ví dụ:

- Tên sản phẩm không được để trống và có thể giới hạn tối đa 120 ký tự.
- SKU phải theo định dạng mã đã thống nhất.
- Email cần được kiểm tra định dạng trước khi lưu.
- Mã trạng thái chỉ được nhận các giá trị nằm trong tập trạng thái hợp lệ.

Có thể dùng Jakarta Bean Validation trên request DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    String name,

    @NotBlank
    @Size(max = 32)
    @Pattern(regexp = "[A-Z0-9-]+")
    String sku
) {
}
~~~

@NotBlank từ chối chuỗi null, rỗng hoặc chỉ chứa khoảng trắng. @Size giới hạn độ dài. @Pattern kiểm tra định dạng bằng biểu thức chính quy. Các annotation này chỉ có tác dụng khi tầng ứng dụng thực sự kích hoạt Bean Validation, ví dụ controller dùng @Valid trên request body và dự án có dependency validation tương ứng.

~~~java
@PostMapping("/products")
public Product create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
~~~

Nên chuẩn hóa dữ liệu chuỗi trước khi áp dụng quy tắc duy nhất: trim khoảng trắng ngoài, thống nhất chữ hoa/chữ thường cho mã không phân biệt hoa thường và chuẩn hóa Unicode nếu nghiệp vụ yêu cầu. Neo4j so sánh chuỗi theo giá trị được lưu; SKU-42 và sku-42 là hai giá trị khác nhau. Nếu mã phải duy nhất không phân biệt hoa thường, có thể lưu thêm thuộc tính chuẩn hóa như skuNormalized và đặt uniqueness constraint trên thuộc tính đó.

### Chuỗi rỗng, null và property không tồn tại

Trong Neo4j, property có giá trị null không được lưu như một property. Trong Cypher, câu lệnh SET p.description = null loại bỏ property description khỏi node. Chuỗi rỗng "" là một giá trị chuỗi có thật và khác với property không tồn tại.

Ba trường hợp sau có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa |
|---|---|
| p.description = "Useful book" | Có mô tả |
| p.description = "" | Có property nhưng nội dung rỗng |
| Không có p.description | Chưa cung cấp hoặc không áp dụng |

Hãy quyết định rõ trường nào bắt buộc và trường nào tùy chọn. Với trường bắt buộc, kiểm tra bằng @NotBlank hoặc quy tắc tương đương. Với trường tùy chọn, tránh tự thay giá trị thiếu bằng chuỗi rỗng nếu điều đó làm mất ý nghĩa “chưa biết”.

## Số nguyên: số lượng, bộ đếm và giá trị rời rạc

Neo4j lưu số nguyên dưới kiểu INTEGER có dấu 64-bit. Phạm vi lưu trữ là:

\[
-2^{63} \leq n \leq 2^{63}-1
\]

Tức là từ -9,223,372,036,854,775,808 đến 9,223,372,036,854,775,807. Java int chỉ có phạm vi 32-bit, còn long có phạm vi 64-bit. Nếu dùng Integer, giá trị vẫn phải nằm trong giới hạn của Java int dù Neo4j có thể lưu số lớn hơn.

Các trường phù hợp với số nguyên:

- Số lượng tồn kho.
- Số lượt xem, số lần thử hoặc bộ đếm.
- Số thứ tự, số lượng sản phẩm trong đơn.
- Giá tiền theo đơn vị nhỏ nhất khi quy tắc tiền tệ và độ chính xác đã được xác định.
- Khối lượng tính theo gram hoặc khoảng cách tính theo đơn vị nguyên đã chọn.

Ví dụ entity sản phẩm:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    private String sku;

    private String name;
    private Long stockQuantity;
    private Long priceVnd;
    private Long weightGrams;

    protected Product() {
    }

    public Product(
            String sku,
            String name,
            Long stockQuantity,
            Long priceVnd,
            Long weightGrams) {
        this.sku = sku;
        this.name = name;
        this.stockQuantity = stockQuantity;
        this.priceVnd = priceVnd;
        this.weightGrams = weightGrams;
    }

    public String getSku() {
        return sku;
    }

    public Long getStockQuantity() {
        return stockQuantity;
    }

    public void setStockQuantity(Long stockQuantity) {
        this.stockQuantity = stockQuantity;
    }
}
~~~

Trong ví dụ, stockQuantity là số lượng nguyên, priceVnd là số tiền theo đơn vị đồng Việt Nam và weightGrams là khối lượng theo gram. Cách biểu diễn bằng đơn vị nguyên tránh sai số dấu phẩy động trong các phép tính tiền. Nếu ứng dụng hỗ trợ nhiều loại tiền tệ, hãy lưu mã tiền tệ và xác định số chữ số thập phân theo quy tắc của từng loại tiền; không mặc định mọi tiền tệ đều có hai chữ số thập phân.

### Giới hạn kiểu và giới hạn nghiệp vụ

Giới hạn lưu trữ của kiểu dữ liệu khác với giới hạn mà domain cho phép. Neo4j và Java có thể lưu số âm, nhưng số lượng tồn kho thường không được âm. Một số lượng có thể nằm trong phạm vi Long nhưng nghiệp vụ chỉ cho phép tối đa một triệu đơn vị.

Ví dụ, domain quy định:

| Thuộc tính | Kiểu đề xuất | Miền giá trị |
|---|---|---|
| stockQuantity | Long | 0 đến 1.000.000 |
| priceVnd | Long | 0 đến giới hạn kinh doanh đã xác định |
| weightGrams | Long | Lớn hơn 0 |
| retryCount | Integer | 0 đến 10 |

Không nên dựa vào kiểu Long để kết luận số lượng tồn kho hợp lệ. Kiểu dữ liệu chỉ ngăn giá trị vượt giới hạn kỹ thuật; ứng dụng cần kiểm tra giới hạn nghiệp vụ.

## Số thực: đo lường, điểm số và sai số dấu phẩy động

Neo4j lưu số thực bằng kiểu FLOAT 64-bit. Trong Java, Double thường là lựa chọn phù hợp để ánh xạ trực tiếp kiểu này. Số thực hữu ích cho các giá trị đo lường hoặc kết quả tính toán như:

- Điểm đánh giá trung bình.
- Tỷ lệ hoặc xác suất.
- Nhiệt độ, tọa độ hoặc số đo có phần thập phân.
- Trọng số hoặc hệ số trong thuật toán.

Trong entity **Product** đã khai báo ở trên, có thể thêm thuộc tính điểm đánh giá trung bình:

~~~java
private Double averageRating;
~~~

Nếu điểm đánh giá chỉ nằm trong khoảng 0 đến 5, Double vẫn có thể lưu giá trị 7.8 hoặc -1.0. Do đó, cần kiểm tra miền giá trị:

~~~java
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

public record UpdateRatingRequest(
    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("5.0")
    Double averageRating
) {
}
~~~

### Không dùng FLOAT cho tiền cần độ chính xác tuyệt đối

Số dấu phẩy động biểu diễn nhiều số thập phân theo dạng gần đúng nhị phân. Vì vậy, các phép tính tiền như cộng, trừ hoặc so sánh có thể gặp sai số làm tròn nếu dùng Float hoặc Double.

Không nên lưu trực tiếp giá trị tiền cần chính xác bằng Double. Có thể lưu số tiền bằng số nguyên theo đơn vị nhỏ nhất đã xác định, ví dụ priceVnd = 199000, hoặc dùng một quy ước decimal được chuẩn hóa và chuyển đổi rõ ràng ở tầng ứng dụng. Khi cần số chữ số thập phân tùy ý, BigDecimal phù hợp cho tính toán trong Java, nhưng Neo4j không có property decimal nguyên thủy tương ứng; cần quyết định cách serialize và khôi phục giá trị trước khi ánh xạ.

Không làm tròn dữ liệu tùy tiện khi lưu. Hãy xác định scale, quy tắc rounding và đơn vị ngay từ hợp đồng dữ liệu, rồi dùng nhất quán trong API, service và truy vấn.

## Boolean: cờ đúng hoặc sai

Boolean trong Java ánh xạ thành property BOOLEAN của Neo4j. Kiểu này phù hợp với cờ đơn giản:

- active: tài khoản có đang hoạt động không.
- published: nội dung đã được công bố chưa.
- verified: thông tin đã được xác minh chưa.
- deleted: bản ghi đã được đánh dấu xóa chưa.

Ví dụ:

~~~cypher
CREATE (:Account {
    accountId: "ACC-1042",
    active: true,
    verified: false
});
~~~

Boolean chỉ có hai giá trị thực sự: true và false. Nếu cần biểu diễn trạng thái thứ ba như “chưa xác định”, không nên ép nó thành false. Hãy quyết định dùng property tùy chọn (không có giá trị khi chưa biết), enum trạng thái hoặc một mô hình trạng thái rõ ràng.

### boolean hay Boolean?

| Kiểu Java | Có thể null? | Phù hợp khi |
|---|---|---|
| boolean | Không | Giá trị luôn bắt buộc và luôn có true/false |
| Boolean | Có | Cần phân biệt true, false và chưa có giá trị |

Primitive boolean mặc định là false, vì vậy nếu không gán giá trị, ứng dụng có thể vô tình ghi nhận trạng thái false dù nghiệp vụ muốn biểu diễn “chưa thiết lập”. Dùng Boolean khi cần phân biệt giá trị chưa được cung cấp với false. Dùng Bean Validation @NotNull nếu API yêu cầu client phải gửi cờ này.

## Kiểm tra miền giá trị bằng Bean Validation

Bean Validation giúp kiểm tra dữ liệu đầu vào tại biên ứng dụng trước khi ghi vào Neo4j. Một số annotation thường dùng:

| Annotation | Công dụng | Ví dụ |
|---|---|---|
| @NotNull | Giá trị không được null | Trạng thái bắt buộc |
| @NotBlank | Chuỗi không được null, rỗng hoặc chỉ có khoảng trắng | Tên sản phẩm |
| @Size(min, max) | Giới hạn độ dài chuỗi hoặc kích thước collection | SKU tối đa 32 ký tự |
| @Min, @Max | Giới hạn số nguyên | Tồn kho từ 0 đến 1.000.000 |
| @Positive, @PositiveOrZero | Số phải dương hoặc không âm | Khối lượng, số lượng |
| @DecimalMin, @DecimalMax | Giới hạn giá trị số thập phân | Điểm đánh giá từ 0 đến 5 |
| @Pattern | Kiểm tra chuỗi theo regex | Mã chỉ gồm chữ hoa, số và dấu gạch nối |

Ví dụ request đầy đủ cho thao tác tạo sản phẩm:

~~~java
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    String name,

    @NotBlank
    @Size(max = 32)
    @Pattern(regexp = "[A-Z0-9-]+")
    String sku,

    @NotNull
    @Min(0)
    @Max(1_000_000)
    Long stockQuantity,

    @NotNull
    @Min(0)
    Long priceVnd,

    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("5.0")
    Double averageRating,

    @NotNull
    Boolean active
) {
}
~~~

Khi controller nhận request, kích hoạt validation bằng @Valid:

~~~java
@PostMapping
public Product create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
~~~

Để các annotation hoạt động, dự án cần có implementation Bean Validation, thường được cung cấp qua starter validation của Spring Boot. Hãy đặt validation ở tầng nhận dữ liệu và service để các luồng ghi khác nhau dùng chung quy tắc. Nếu một tác vụ import hoặc batch không đi qua controller, tác vụ đó vẫn phải gọi validator hoặc kiểm tra dữ liệu trước khi ghi.

Bean Validation không tự động bảo vệ mọi lệnh Cypher. Một script chạy trực tiếp trong Neo4j, một công cụ ETL hoặc một dịch vụ khác có thể ghi dữ liệu mà không đi qua controller. Vì vậy, cần có thêm quy tắc ở tầng database và quy trình kiểm tra dữ liệu.

## Bảo vệ kiểu dữ liệu bằng constraint của Neo4j

Neo4j hỗ trợ các constraint như uniqueness, existence và property type constraint. Chúng có thể bảo vệ một số quy tắc ở tầng database ngay cả khi dữ liệu được ghi từ nhiều ứng dụng.

Ví dụ uniqueness constraint cho SKU:

~~~cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;
~~~

Với các phiên bản và edition Neo4j hỗ trợ property type constraint, có thể yêu cầu property tồn tại dưới một kiểu nhất định, ví dụ:

~~~cypher
CREATE CONSTRAINT product_stock_type IF NOT EXISTS
FOR (p:Product)
REQUIRE p.stockQuantity IS :: INTEGER;
~~~

Khả năng sử dụng property type constraint và property existence constraint phụ thuộc phiên bản, edition và môi trường Neo4j. Kiểm tra tài liệu của phiên bản DBMS đang triển khai trước khi đưa chúng vào migration. Uniqueness constraint không đồng nghĩa với constraint kiểm tra miền giá trị.

Neo4j không cung cấp một biểu thức CHECK tổng quát tương đương SQL để khai báo mọi điều kiện như stockQuantity >= 0 hoặc averageRating <= 5. Những giới hạn min/max cần được kiểm tra ở tầng ứng dụng, trong các đường import và trong các quy trình ghi dữ liệu được kiểm soát. Có thể dùng truy vấn kiểm tra để phát hiện dữ liệu vi phạm:

~~~cypher
MATCH (p:Product)
WHERE p.stockQuantity IS NULL
   OR p.stockQuantity < 0
   OR p.stockQuantity > 1000000
RETURN p.sku, p.stockQuantity;
~~~

Truy vấn này tìm sản phẩm thiếu số lượng tồn kho hoặc có số lượng ngoài miền 0 đến 1.000.000. Có thể chạy định kỳ như một bước kiểm tra chất lượng dữ liệu, đặc biệt sau import hoặc migration.

## Đảm bảo cùng một quy tắc ở Repository và Cypher

Repository và Cypher đều có thể ghi property. Nếu chỉ controller kiểm tra dữ liệu, các lệnh ghi khác có thể tạo giá trị không hợp lệ. Hãy gom quy tắc nghiệp vụ ở service hoặc validator dùng chung, rồi bảo đảm các tác vụ import và Cypher trực tiếp tuân theo cùng hợp đồng.

Ví dụ cập nhật tồn kho nên kiểm tra đầu vào trước khi gọi repository:

~~~java
@Transactional
public Product updateStock(String sku, long newQuantity) {
    if (newQuantity < 0 || newQuantity > 1_000_000) {
        throw new IllegalArgumentException("Stock quantity is outside the allowed range");
    }

    Product product = products.findById(sku)
        .orElseThrow(() -> new ProductNotFoundException(sku));

    product.setStockQuantity(newQuantity);
    return products.save(product);
}
~~~

Nếu dùng Cypher trực tiếp, dùng tham số và chỉ ghi sau khi điều kiện đã được kiểm tra trong luồng xử lý:

~~~cypher
MATCH (p:Product {sku: $sku})
WHERE $newQuantity >= 0
  AND $newQuantity <= 1000000
SET p.stockQuantity = $newQuantity
RETURN p;
~~~

Nếu điều kiện không thỏa mãn, truy vấn không cập nhật node và không trả về kết quả. Service cần kiểm tra số bản ghi được cập nhật để phân biệt SKU không tồn tại với số lượng không hợp lệ. Với thao tác quan trọng, hãy trả lỗi nghiệp vụ rõ ràng thay vì âm thầm coi trường hợp không có kết quả là thành công.

## Chuyển đổi và làm sạch dữ liệu cũ

Khi đổi kiểu property, không nên chuyển dữ liệu ngay mà chưa kiểm kê. Ví dụ, một hệ thống cũ có thể lưu stockQuantity dưới dạng chuỗi "120"; entity mới lại khai báo Long. Cần xác định các giá trị không chuyển đổi được, giá trị null, khoảng trắng và số nằm ngoài miền trước khi migration.

Có thể tìm các giá trị không phải chuỗi chữ số bằng Cypher:

~~~cypher
MATCH (p:Product)
WHERE p.stockQuantityText IS NOT NULL
  AND NOT p.stockQuantityText =~ '^[0-9]+$'
RETURN p.sku, p.stockQuantityText;
~~~

Sau khi dữ liệu đã được kiểm tra và xử lý, có thể chuyển đổi bằng toInteger() trong một migration có kiểm soát:

~~~cypher
MATCH (p:Product)
WHERE p.stockQuantityText IS NOT NULL
SET p.stockQuantity = toInteger(p.stockQuantityText)
RETURN count(p) AS migrated;
~~~

Không chạy migration này nếu chưa xử lý các giá trị sai định dạng hoặc vượt phạm vi số nguyên. Hãy sao lưu, thử trên bản sao dữ liệu, xác minh số lượng node đã chuyển và chỉ xóa property cũ sau khi ứng dụng mới đọc đúng dữ liệu.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Lưu mã SKU hoặc số điện thoại dưới kiểu số | Mất số 0 đầu hoặc định dạng ký tự | Dùng String |
| Lưu số lượng dưới kiểu String | So sánh và sắp xếp có thể theo thứ tự từ điển | Dùng Integer hoặc Long |
| Dùng Double cho tiền cần độ chính xác tuyệt đối | Sai số dấu phẩy động khi tính toán | Dùng số nguyên theo đơn vị tiền nhỏ nhất đã xác định |
| Chỉ dựa vào Long để kiểm tra tồn kho không âm | Vẫn có thể lưu giá trị âm | Thêm validation miền giá trị |
| Dùng primitive boolean cho trạng thái có thể chưa biết | Giá trị mặc định false che mất trạng thái chưa thiết lập | Dùng Boolean hoặc enum trạng thái |
| Coi chuỗi rỗng giống property không tồn tại | Mất phân biệt giữa “đã nhập rỗng” và “chưa cung cấp” | Quy định rõ null, empty và required |
| Chỉ validate ở controller | Batch hoặc Cypher trực tiếp có thể ghi dữ liệu sai | Dùng validator/service chung và kiểm tra các đường ghi khác |
| Giả định constraint kiểu dữ liệu kiểm tra được min/max | Giá trị đúng kiểu nhưng sai miền vẫn được ghi | Kiểm tra min/max trong ứng dụng và quy trình dữ liệu |

## Bài tập thực hành

Với entity Product trong một hệ thống bán hàng, hãy chọn kiểu dữ liệu và miền giá trị cho các thuộc tính sau:

1. sku: mã có thể chứa chữ, số và số 0 ở đầu.
2. name: tên sản phẩm bắt buộc, tối đa 120 ký tự.
3. stockQuantity: số lượng tồn kho, từ 0 đến 1.000.000.
4. priceVnd: giá tiền tính bằng đồng Việt Nam, không âm.
5. averageRating: điểm đánh giá trung bình từ 0 đến 5.
6. active: cờ sản phẩm đang được kinh doanh; xác định xem trạng thái này có được phép chưa thiết lập hay không.

Sau đó thực hiện các bước:

- Khai báo entity với kiểu Java phù hợp và repository có kiểu ID đúng với thuộc tính @Id.
- Tạo request DTO dùng Bean Validation để kiểm tra chuỗi, số nguyên, số thực và boolean.
- Tạo uniqueness constraint cho SKU và cân nhắc property type constraint nếu phiên bản Neo4j hỗ trợ.
- Viết một truy vấn kiểm tra các sản phẩm có tồn kho âm hoặc điểm đánh giá vượt giới hạn.
- Thử ghi dữ liệu qua repository và Cypher với các giá trị hợp lệ, không hợp lệ để xác nhận mọi đường ghi đều tuân thủ quy tắc.

Khi thiết kế property trong Spring Data Neo4j, hãy chọn kiểu Java phù hợp với kiểu Neo4j, phân biệt giới hạn kỹ thuật với giới hạn nghiệp vụ và xác định rõ cách xử lý giá trị thiếu. Kiểm tra ở tầng ứng dụng kết hợp constraint phù hợp của Neo4j giúp dữ liệu nhất quán ngay cả khi có nhiều nguồn ghi khác nhau.

