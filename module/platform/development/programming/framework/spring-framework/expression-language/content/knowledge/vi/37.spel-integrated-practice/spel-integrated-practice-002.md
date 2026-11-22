# Lọc và chiếu danh sách object bằng selection và projection trong SpEL

## 1. Selection và projection giải quyết việc gì?

Spring Expression Language (SpEL) cung cấp hai thao tác collection thường dùng:

- Selection lọc các phần tử theo một điều kiện.
- Projection tạo một giá trị kết quả cho từng phần tử trong collection.

Selection dùng cú pháp `.?[condition]`. Projection dùng cú pháp `.![expression]`.

Ví dụ, từ danh sách sản phẩm, lấy các sản phẩm còn hàng rồi lấy tên của chúng:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "products.?[active and stock > 0].![name]");

List<?> names = expression.getValue(catalog, List.class);
~~~

Phần selection giữ lại những sản phẩm có active là true và stock lớn hơn 0. Phần projection đọc name của từng sản phẩm đã được giữ lại.

Hai thao tác có thể kết hợp trong một expression ngắn. Khi cần nhiều bước nghiệp vụ hoặc nhiều tầng collection lồng nhau, hãy cân nhắc tách thành các bước Java có tên rõ ràng.

## 2. Cấu trúc cú pháp

Cú pháp tổng quát:

~~~text
collection.?[selectionExpression]
collection.![projectionExpression]
~~~

Selection đánh giá điều kiện trên từng phần tử. Phần tử được giữ lại nếu điều kiện cho kết quả Boolean true.

Projection đánh giá biểu thức trên từng phần tử và thêm kết quả vào collection kết quả. Projection không lọc phần tử; mỗi phần tử đầu vào tạo ra một giá trị kết quả tương ứng.

Ví dụ:

~~~text
products.?[active]
products.![name]
products.?[stock > 0].![name]
~~~

- `products.?[active]` chọn các sản phẩm đang active.
- `products.![name]` lấy name của tất cả sản phẩm.
- `products.?[stock > 0].![name]` lọc sản phẩm còn hàng rồi lấy tên.

Hãy chọn selection khi cần giảm số phần tử và projection khi cần biến đổi phần tử thành một giá trị khác.

## 3. Chuẩn bị object graph để thực hành

Ví dụ dùng Product và Catalog. Các getter cho phép SpEL đọc property theo tên:

~~~java
public class Product {
    private final String sku;
    private final String name;
    private final String category;
    private final boolean active;
    private final int stock;
    private final BigDecimal price;

    public Product(
            String sku,
            String name,
            String category,
            boolean active,
            int stock,
            BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.category = category;
        this.active = active;
        this.stock = stock;
        this.price = price;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public boolean isActive() {
        return active;
    }

    public int getStock() {
        return stock;
    }

    public BigDecimal getPrice() {
        return price;
    }
}

public class Catalog {
    private final String owner;
    private final List<Product> products;

    public Catalog(String owner, List<Product> products) {
        this.owner = owner;
        this.products = products;
    }

    public String getOwner() {
        return owner;
    }

    public List<Product> getProducts() {
        return products;
    }
}
~~~

Tạo fixture nhỏ:

~~~java
Catalog catalog = new Catalog(
        "Lan",
        List.of(
                new Product("P-01", "Keyboard", "Computer", true, 12,
                        new BigDecimal("45.00")),
                new Product("P-02", "Mouse", "Computer", true, 0,
                        new BigDecimal("20.00")),
                new Product("P-03", "Notebook", "Stationery", false, 30,
                        new BigDecimal("5.00")),
                new Product("P-04", "Pen", "Stationery", true, 50,
                        new BigDecimal("2.50"))));
~~~

Dữ liệu có sản phẩm active và inactive, có hàng và hết hàng, thuộc nhiều category. Nhờ vậy, các điều kiện selection tạo ra kết quả dễ quan sát.

## 4. Lọc collection bằng selection

Selection giữ lại các phần tử thỏa predicate trong dấu ngoặc vuông:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("products.?[active]");

List<?> activeProducts =
        expression.getValue(catalog, List.class);

assertEquals(3, activeProducts.size());
~~~

Trong predicate, property không có tiền tố được đọc trên phần tử hiện tại. Vì vậy `active` tương đương với việc kiểm tra property active của từng Product.

Có thể viết tường minh bằng `#this`:

~~~java
Expression expression =
        parser.parseExpression("products.?[#this.active]");
~~~

Cách viết có `#this` hữu ích khi predicate có nhiều tham chiếu và cần làm rõ object hiện tại. Với điều kiện đơn giản, property trực tiếp thường gọn hơn.

## 5. Kết hợp nhiều điều kiện selection

Predicate có thể kết hợp điều kiện Boolean:

~~~java
Expression expression = parser.parseExpression(
        "products.?[active and stock > 0 and price >= 10]");

List<?> availableProducts =
        expression.getValue(catalog, List.class);
~~~

Ở đây một sản phẩm chỉ được giữ lại khi đồng thời:

- active là true.
- stock lớn hơn 0.
- price lớn hơn hoặc bằng 10.

Có thể dùng `or` và dấu ngoặc để thể hiện nhóm điều kiện:

~~~text
products.?[active and (category == 'Computer' or stock >= 40)]
~~~

Khi predicate có nhiều nhánh, hãy dùng dấu ngoặc để người đọc thấy rõ thứ tự kết hợp. Nếu điều kiện đã trở thành một quy tắc nghiệp vụ dài, chuyển predicate sang method Java có tên như isEligibleForSale.

## 6. Dùng variable làm tham số lọc

Có thể đưa ngưỡng hoặc tiêu chí lọc vào EvaluationContext thay vì nối giá trị vào expression source:

~~~java
Expression expression =
        parser.parseExpression("products.?[price >= #minimumPrice]");

StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable("minimumPrice", new BigDecimal("10.00"));

List<?> result = expression.getValue(context, List.class);
~~~

Cùng expression có thể được dùng với ngưỡng khác:

~~~java
context.setVariable("minimumPrice", new BigDecimal("40.00"));

List<?> expensiveProducts =
        expression.getValue(context, List.class);
~~~

Variable được tham chiếu bằng tiền tố `#`. Property products vẫn được đọc từ root object catalog.

Truyền dữ liệu động qua variables giúp giữ expression source ổn định, dễ parse một lần và tránh biến dữ liệu đầu vào thành cú pháp SpEL.

## 7. Lấy phần tử đầu tiên hoặc cuối cùng thỏa điều kiện

Ngoài selection thông thường, SpEL hỗ trợ selection lấy kết quả đầu tiên hoặc cuối cùng:

~~~text
collection.^[condition]
collection.$[condition]
~~~

Ví dụ:

~~~java
Expression firstAvailable = parser.parseExpression(
        "products.^[active and stock > 0]");

Expression lastAvailable = parser.parseExpression(
        "products.$[active and stock > 0]");

Product first = firstAvailable.getValue(catalog, Product.class);
Product last = lastAvailable.getValue(catalog, Product.class);
~~~

- `.^[...]` trả về phần tử đầu tiên thỏa điều kiện.
- `.$[...]` trả về phần tử cuối cùng thỏa điều kiện.

Nếu không có phần tử phù hợp, kết quả selection đầu tiên/cuối cùng là null. Hãy xử lý null trước khi truy cập property của kết quả.

Thứ tự của collection đầu vào ảnh hưởng tới kết quả đầu tiên và cuối cùng. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy bảo đảm collection có contract thứ tự rõ ràng.

## 8. Projection để lấy một property từ mỗi object

Projection áp dụng biểu thức lên từng phần tử và tạo collection kết quả:

~~~java
Expression expression =
        parser.parseExpression("products.![name]");

List<?> names = expression.getValue(catalog, List.class);

assertEquals(
        List.of("Keyboard", "Mouse", "Notebook", "Pen"),
        names);
~~~

Mỗi Product tạo ra một String tương ứng với property name. Số phần tử của kết quả projection tương ứng với số phần tử đầu vào được xử lý.

Có thể chiếu nhiều loại property:

~~~text
products.![sku]
products.![price]
products.![category]
products.![active]
~~~

Projection chỉ lấy giá trị cần dùng, giúp giảm sự phụ thuộc của phần xử lý tiếp theo vào toàn bộ object Product.

Nếu chỉ cần tên sản phẩm, dùng `products.![name]` thay vì trả toàn bộ object rồi tự lặp trong Java.

## 9. Projection để tạo giá trị tính toán

Projection không giới hạn ở việc đọc một property. Biểu thức bên trong có thể tính toán trên từng phần tử:

~~~java
Expression expression =
        parser.parseExpression("products.![price * 1.1]");

List<?> pricesWithTax =
        expression.getValue(catalog, List.class);
~~~

Có thể tạo chuỗi mô tả cho mỗi sản phẩm:

~~~text
products.![name + ' (' + category + ')']
~~~

Hoặc tạo một giá trị Boolean:

~~~text
products.![active and stock > 0]
~~~

Mỗi phần tử đầu vào tạo ra một kết quả tương ứng. Hãy giữ projection đơn giản và dễ hiểu; nếu cần tính giá phức tạp, làm tròn theo nhiều quy tắc hoặc gọi nhiều dịch vụ, nên chuyển phần tính toán sang Java.

## 10. Kết hợp selection rồi projection

Một quy trình phổ biến là lọc trước rồi chiếu giá trị:

~~~java
Expression expression = parser.parseExpression(
        "products.?[active and stock > 0].![name]");

List<?> names = expression.getValue(catalog, List.class);

assertEquals(List.of("Keyboard", "Pen"), names);
~~~

Thứ tự thao tác rất quan trọng:

1. Selection chỉ giữ sản phẩm active và còn hàng.
2. Projection lấy name từ các sản phẩm còn lại.
3. Kết quả là danh sách tên, không phải danh sách Product.

Nếu đổi thứ tự, ý nghĩa sẽ khác. Projection trước tạo ra collection giá trị name; predicate sau đó phải được viết theo kiểu dữ liệu mới, không còn truy cập property của Product.

Hãy đọc expression từ trái sang phải để xác định kiểu dữ liệu mà mỗi bước nhận và trả về.

## 11. Dùng #this và #root trong predicate

Trong selection và projection, `#this` đại diện cho phần tử hiện tại. `#root` giữ tham chiếu tới root object ban đầu của lần đánh giá.

Ví dụ predicate vừa kiểm tra owner của Catalog vừa kiểm tra giá sản phẩm:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable("expectedOwner", "Lan");
context.setVariable("minimumPrice", new BigDecimal("10.00"));

Expression expression = parser.parseExpression(
        "products.?[#root.owner == #expectedOwner "
        + "and #this.price >= #minimumPrice].![name]");

List<?> names = expression.getValue(context, List.class);
~~~

Trong predicate:

- `#root.owner` đọc owner từ Catalog.
- `#this.price` đọc price của Product hiện tại.
- `#expectedOwner` và `#minimumPrice` là variables trong context.

Khi collection operation lồng nhau, #this thay đổi theo cấp collection hiện tại. Nếu phải theo dõi nhiều cấp #this để hiểu expression, hãy tách collection trung gian thành biến Java hoặc method có tên.

## 12. Selection trên Map

SpEL cũng hỗ trợ selection trên Map. Với Map, selection giữ lại các entry thỏa điều kiện và kết quả là một Map chứa những entry được chọn.

Trong predicate, phần tử hiện tại là entry; có thể truy cập key và value:

~~~java
Map<String, Product> productsBySku = Map.of(
        "P-01", new Product("P-01", "Keyboard", "Computer",
                true, 12, new BigDecimal("45.00")),
        "P-02", new Product("P-02", "Mouse", "Computer",
                true, 0, new BigDecimal("20.00")));

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("productsBySku", productsBySku);

Expression expression = parser.parseExpression(
        "#productsBySku.?[value.active and value.stock > 0]");

Map<?, ?> available =
        expression.getValue(context, Map.class);
~~~

Ở đây `value` là value của Map.Entry hiện tại. Có thể kiểm tra key khi điều kiện phụ thuộc mã entry:

~~~text
#productsBySku.?[key.startsWith('P-') and value.active]
~~~

Projection trên Map tạo danh sách các giá trị được tính từ từng entry. Ví dụ có thể lấy tên từ value:

~~~text
#productsBySku.![value.name]
~~~

Hãy phân biệt Map với List: predicate của Map làm việc trên entry có key và value, còn predicate của List làm việc trực tiếp trên object phần tử.

## 13. Selection trên array và collection

Selection có thể dùng trên các kiểu collection được SpEL hỗ trợ, bao gồm Collection và array. Kết quả selection trên collection/array là danh sách phần tử phù hợp; với Map, kết quả là Map giữ các entry phù hợp.

Ví dụ với array:

~~~java
Product[] products = {
        new Product("P-01", "Keyboard", "Computer",
                true, 12, new BigDecimal("45.00")),
        new Product("P-02", "Mouse", "Computer",
                true, 0, new BigDecimal("20.00"))
};

Expression expression =
        parser.parseExpression("[?]"); // Chỉ minh họa array được truyền làm root.
~~~

Khi array là root object, có thể dùng selection trực tiếp trên root collection theo cú pháp phù hợp với biểu thức. Trong ứng dụng, thường dễ đọc hơn nếu array được expose qua property có tên, ví dụ `products.?[active]`.

Với collection rỗng, selection thông thường trả về collection kết quả rỗng. Projection trên collection rỗng cũng trả về collection rỗng. Điều này khác với target collection null.

## 14. Xử lý phần tử null trong collection

Collection có thể chứa phần tử null. Null-safe operator trên collection gốc không tự loại bỏ phần tử null bên trong.

Predicate nên kiểm tra phần tử trước khi đọc property:

~~~java
List<Product> products = Arrays.asList(
        new Product("P-01", "Keyboard", "Computer",
                true, 12, new BigDecimal("45.00")),
        null,
        new Product("P-02", "Mouse", "Computer",
                true, 0, new BigDecimal("20.00")));

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("products", products);

Expression expression = parser.parseExpression(
        "#products.?[#this != null and #this.active].![name]");

List<?> names = expression.getValue(context, List.class);
~~~

Điều kiện kiểm tra `#this != null` đứng trước truy cập `#this.active`. Nhờ đó, phần tử null không bị truy cập property.

Nếu projection cần giữ vị trí của phần tử null nhưng tạo giá trị null tương ứng, có thể dùng null-safe property access:

~~~text
#products.![#this?.name]
~~~

Nếu nghiệp vụ muốn bỏ phần tử null, hãy lọc trước rồi projection. Hãy xác định rõ muốn loại bỏ phần tử hay giữ lại một kết quả null.

## 15. Xử lý collection root null

Target collection null khác collection rỗng. Null-safe selection và projection được hỗ trợ từ Spring Framework 6.2:

~~~text
products?.?[active]
products?.![name]
~~~

Nếu products là null, null-safe collection operation trả về null. Nếu products là collection rỗng, kết quả là collection rỗng.

Với phiên bản Spring Framework cũ hơn 6.2, hãy kiểm tra null trong Java trước khi evaluate hoặc cung cấp collection rỗng nếu hai trạng thái có cùng ý nghĩa nghiệp vụ.

Không nên tự động biến null thành collection rỗng nếu null mang ý nghĩa “chưa tải dữ liệu” còn empty mang ý nghĩa “đã tải nhưng không có phần tử”.

## 16. Collection kết quả và kiểu dữ liệu

Selection và projection có kiểu kết quả khác nhau tùy collection đầu vào và thao tác:

| Đầu vào | Thao tác | Kết quả |
|---|---|---|
| Collection hoặc array | Selection | Danh sách phần tử phù hợp |
| Map | Selection | Map chứa entry phù hợp |
| Collection, array hoặc Map | Projection | Danh sách giá trị được chiếu |
| Collection rỗng | Selection | Collection kết quả rỗng |
| Collection rỗng | Projection | Collection kết quả rỗng |
| Collection null với null-safe operator | Selection/projection | null |

Khi gọi getValue, có thể yêu cầu kiểu List hoặc Map phù hợp:

~~~java
List<?> names = expression.getValue(context, List.class);
Map<?, ?> selectedEntries = mapExpression.getValue(context, Map.class);
~~~

Class<List> không biểu diễn kiểu generic của phần tử. Nếu ứng dụng cần List<String> cụ thể, hãy kiểm tra nội dung và kiểu từng phần tử trong test.

## 17. Kiểm thử selection bằng JUnit 5

Test nên có phần tử khớp và không khớp để chứng minh predicate hoạt động đúng:

~~~java
@Test
void selectsOnlyActiveProducts() {
    Catalog catalog = TestData.catalog();

    Expression expression = new SpelExpressionParser()
            .parseExpression("products.?[active]");

    List<?> result = expression.getValue(catalog, List.class);

    assertEquals(3, result.size());
    assertEquals("Keyboard", ((Product) result.get(0)).getName());
    assertEquals("Mouse", ((Product) result.get(1)).getName());
}
~~~

Ngoài số lượng, nên kiểm tra nội dung và thứ tự nếu thứ tự là một phần của contract collection. Một selection có thể trả về đúng số phần tử nhưng vẫn chọn sai phần tử.

Các trường hợp nên có:

- Tất cả phần tử đều khớp.
- Không phần tử nào khớp.
- Chỉ một phần tử khớp.
- Collection rỗng.
- Phần tử null nếu collection cho phép.
- Property dùng trong predicate có giá trị null.
- Giá trị variable thay đổi giữa các lần evaluate.

## 18. Kiểm thử projection bằng JUnit 5

Projection cần xác nhận mỗi phần tử đầu vào tạo ra giá trị đúng:

~~~java
@Test
void projectsProductNames() {
    Catalog catalog = TestData.catalog();

    Expression expression = new SpelExpressionParser()
            .parseExpression("products.![name]");

    List<?> names = expression.getValue(catalog, List.class);

    assertEquals(
            List.of("Keyboard", "Mouse", "Notebook", "Pen"),
            names);
}
~~~

Có thể kiểm tra projection sau selection:

~~~java
@Test
void filtersBeforeProjectingNames() {
    Catalog catalog = TestData.catalog();

    Expression expression = new SpelExpressionParser()
            .parseExpression(
                    "products.?[active and stock > 0].![name]");

    List<?> names = expression.getValue(catalog, List.class);

    assertEquals(List.of("Keyboard", "Pen"), names);
}
~~~

Test nên xác nhận thứ tự kết quả nếu collection có thứ tự. Với projection có phép tính, kiểm tra kiểu và giá trị kết quả để phát hiện chuyển đổi không mong đợi.

## 19. Kiểm thử selection đầu tiên và cuối cùng

Selection đầu tiên/cuối cùng cần có test cho trường hợp có kết quả và không có kết quả:

~~~java
@Test
void selectsFirstAndLastAvailableProduct() {
    Catalog catalog = TestData.catalog();

    Expression firstExpression =
            parser.parseExpression("products.^[active and stock > 0]");
    Expression lastExpression =
            parser.parseExpression("products.$[active and stock > 0]");

    Product first = firstExpression.getValue(catalog, Product.class);
    Product last = lastExpression.getValue(catalog, Product.class);

    assertEquals("P-01", first.getSku());
    assertEquals("P-04", last.getSku());
}
~~~

Trường hợp không có phần tử phù hợp:

~~~java
Expression expression =
        parser.parseExpression("products.^[stock < 0]");

Product result = expression.getValue(catalog, Product.class);

assertNull(result);
~~~

Không truy cập property của kết quả trước khi kiểm tra null. Nếu thứ tự đầu vào không ổn định, first/last cũng không có ý nghĩa ổn định; hãy sắp xếp dữ liệu ở Java trước khi đánh giá.

## 20. Tách selection và projection khi cần debug

Một expression kết hợp hai thao tác có thể được tách thành hai expression để xem kết quả trung gian:

~~~java
Expression selection =
        parser.parseExpression("products.?[active and stock > 0]");

Expression projection =
        parser.parseExpression("#selected.![name]");

StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

List<?> selected = selection.getValue(context, List.class);
context.setVariable("selected", selected);

List<?> names = projection.getValue(context, List.class);
~~~

Bước selection cho phép kiểm tra những Product nào được giữ lại. Bước projection cho phép kiểm tra cách lấy name từ danh sách đó.

Không cần tách mọi expression ngắn thành nhiều bước. Hãy tách khi kết quả trung gian giúp tìm lỗi hoặc khi mỗi bước có một ý nghĩa nghiệp vụ riêng.

## 21. Lỗi thường gặp

**Nhầm selection với projection**

Selection lọc phần tử; projection tạo giá trị mới cho từng phần tử. Projection không tự loại bỏ phần tử không phù hợp.

**Quên dấu chấm trước toán tử**

Cú pháp collection operation dùng dạng `.?[...]` và `.![...]`. Hãy kiểm tra dấu chấm, ký hiệu và dấu ngoặc vuông.

**Dùng property của root thay vì property phần tử**

Trong predicate, property trực tiếp thường được đọc trên phần tử hiện tại. Dùng `#root` khi cần truy cập object gốc.

**Nhầm #this và #root**

#this thay đổi theo phần tử hiện tại trong selection/projection; #root giữ root object ban đầu.

**Giả định Map giống List**

Selection trên Map trả về Map entry được chọn. Trong predicate, truy cập key và value của entry.

**Không kiểm tra phần tử null**

Collection có thể không null nhưng chứa phần tử null. Kiểm tra #this trước khi đọc property.

**Nhầm collection null với collection rỗng**

Null-safe operation trên target null trả về null; operation trên collection rỗng trả về collection rỗng.

**Chỉ kiểm tra size**

Test chỉ kiểm tra số lượng có thể bỏ sót việc chọn sai phần tử hoặc projection sai thứ tự. Kiểm tra giá trị thực tế.

**Lồng quá nhiều collection operation**

Selection/projection nhiều tầng khó theo dõi phạm vi #this. Tách thành các bước Java có tên khi expression khó đọc.

## 22. Quy trình chọn và kiểm tra expression

Khi cần lọc và biến đổi danh sách object:

1. Xác định collection nằm ở root property hay variable.
2. Xác định predicate cần giữ phần tử nào.
3. Dùng selection `.?[...]` để lọc.
4. Xác định giá trị cần lấy từ mỗi phần tử.
5. Dùng projection `.![...]` để tạo kết quả.
6. Kiểm tra #this là phần tử hiện tại và #root là root object ban đầu.
7. Xác định collection có thể null hoặc chứa phần tử null hay không.
8. Kiểm thử collection rỗng, không có phần tử khớp và nhiều phần tử khớp.
9. Xác nhận kiểu, nội dung và thứ tự kết quả.
10. Nếu cần nhiều tầng hoặc quy tắc dài, tách logic sang Java.

Quy trình này giúp expression thể hiện đúng hai việc: lọc phần tử và lấy dữ liệu cần thiết từ phần tử được giữ lại.

## 23. Ghi nhớ

- Selection dùng `.?[condition]` để giữ phần tử thỏa điều kiện.
- Projection dùng `.![expression]` để tạo một giá trị cho từng phần tử.
- Có thể nối selection rồi projection, ví dụ `products.?[active].![name]`.
- `#this` là phần tử hiện tại; `#root` là root object ban đầu.
- Dùng `.^[condition]` để lấy phần tử đầu tiên và `.$[condition]` để lấy phần tử cuối cùng phù hợp.
- Selection trên Map trả về Map entry được chọn; predicate có thể đọc key và value.
- Projection tạo danh sách giá trị từ các phần tử đầu vào.
- Collection rỗng khác collection null; null-safe collection operators có từ Spring Framework 6.2.
- Kiểm tra phần tử null trước khi đọc property.
- Test cả nội dung và thứ tự, không chỉ số lượng.
- Giữ expression ngắn; tách collection operation lồng sâu sang Java khi cần.

