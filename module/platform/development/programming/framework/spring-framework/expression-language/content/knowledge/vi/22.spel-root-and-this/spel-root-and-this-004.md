# Thay đổi active context object trong collection expression của SpEL

Trong Spring Expression Language (SpEL), **active context object** là đối tượng hiện tại mà một phần của biểu thức đang được đánh giá trên đó. Biến đặc biệt `#this` tham chiếu đối tượng hiện tại này; `#root` luôn tham chiếu root object ban đầu của lần đánh giá.

Khi expression đi vào một collection operation như selection hoặc projection, SpEL lần lượt đặt từng phần tử của collection làm active context object để đánh giá điều kiện hoặc expression con. Vì vậy, `#this` thay đổi theo phần tử đang được xử lý, còn `#root` vẫn giữ nguyên. Hiểu rõ sự khác nhau này giúp truy cập đúng property khi biểu thức có nhiều cấp collection.

## 1. Phân biệt root object và active context object

EvaluationContext có một root object được dùng làm điểm bắt đầu khi đánh giá expression. SpEL cung cấp hai tham chiếu đặc biệt:

- `#root`: root object ban đầu của lần đánh giá.
- `#this`: active context object tại vị trí hiện tại trong quá trình đánh giá.

Ở ngoài collection operation, `#this` thường chính là root object. Khi expression đi vào selection hoặc projection, active context object chuyển sang phần tử hiện tại của collection. `#root` không đổi theo sự chuyển đổi đó.

Ví dụ, giả sử root object là một catalog có property `products`:

    #root.products

Ở cấp ngoài, có thể truy cập property của root trực tiếp:

    products

Khi đánh giá predicate bên trong selection:

    products.?[price > 100]

SpEL đánh giá `price > 100` trên từng product. Trong predicate, `#this` là product đang được xét, nên biểu thức có thể viết tường minh:

    products.?[#this.price > 100]

Hai cách viết tương đương trong ngữ cảnh này. Dùng `#this` giúp thấy rõ property `price` thuộc phần tử hiện tại, đặc biệt khi biểu thức có nhiều cấp lồng nhau.

## 2. Active context object trong selection

Selection dùng các toán tử để lọc phần tử theo predicate:

| Toán tử | Ý nghĩa | Kết quả |
|---|---|---|
| `.?[condition]` | Chọn tất cả phần tử phù hợp | Collection các phần tử phù hợp |
| `.^[condition]` | Chọn phần tử phù hợp đầu tiên | Một phần tử hoặc null |
| `.$[condition]` | Chọn phần tử phù hợp cuối cùng | Một phần tử hoặc null |

Trong mỗi predicate, active context object là phần tử đang được kiểm tra. Vì vậy, có thể truy cập property trực tiếp hoặc qua `#this`.

Ví dụ:

    #root.products.?[price >= #root.minimumPrice]

Giả sử root object có property `products` và `minimumPrice`. Trong predicate:

- `price` được đọc từ product hiện tại.
- `#this` là product hiện tại.
- `#root.minimumPrice` được đọc từ catalog ban đầu.

Nếu muốn viết rõ cả hai phía:

    #root.products.?[
        #this.price >= #root.minimumPrice
    ]

Cách viết này tránh nhầm lẫn giữa property của phần tử và property của root object.

## 3. Active context object trong projection

Projection áp dụng một expression lên từng phần tử và tạo collection kết quả mới. Toán tử projection là `.![expression]`.

Ví dụ lấy tên của mọi product:

    #root.products.![name]

Trong expression con `name`, active context object là từng product. Có thể viết tường minh:

    #root.products.![#this.name]

Nếu cần kết hợp nhiều property của phần tử:

    #root.products.![
        #this.name + ' - ' + #this.category
    ]

Mỗi lần projection xử lý một product, `#this` trỏ tới product đó. Khi chuyển sang product tiếp theo, active context object được cập nhật tương ứng. Root object vẫn là catalog ban đầu trong suốt quá trình.

Selection và projection có mục đích khác nhau: selection giữ lại các phần tử gốc thỏa điều kiện, còn projection tạo các giá trị mới từ expression áp dụng trên từng phần tử.

## 4. Truy cập property của root bên trong collection expression

Một lỗi thường gặp là viết tên property của root trực tiếp bên trong predicate, dù active context object lúc đó đã là một phần tử collection.

Ví dụ:

    #root.products.?[price >= minimumPrice]

Trong predicate, SpEL tìm `minimumPrice` trên product hiện tại. Nếu Product không có property đó, expression sẽ lỗi. Nếu Product tình cờ cũng có property cùng tên, biểu thức có thể chạy nhưng lại so sánh với giá trị của product thay vì catalog.

Hãy tham chiếu root rõ ràng:

    #root.products.?[
        price >= #root.minimumPrice
    ]

Quy tắc cần nhớ:

- Tên property không có tiền tố trong predicate/projection thường được giải quyết trên active context object.
- `#this.property` cũng truy cập property của active context object.
- `#root.property` luôn truy cập property của root object ban đầu.
- `#variable` truy cập biến được đăng ký trong EvaluationContext; biến không tự thay đổi khi active context object thay đổi.

Khi hai object có property trùng tên, dùng `#this` và `#root` tường minh để thể hiện đúng nguồn dữ liệu.

## 5. Biến trong EvaluationContext không bị thay đổi theo #this

Biến được đăng ký bằng `setVariable` có phạm vi riêng trong EvaluationContext. Việc collection operation đổi active context object không làm thay đổi giá trị của biến.

Ví dụ:

    context.setVariable("minimumPrice", new BigDecimal("100"));

    #root.products.?[
        price >= #minimumPrice
    ]

Trong predicate, `#this` là product hiện tại, còn `#minimumPrice` vẫn là biến do ứng dụng đăng ký. Có thể dùng biến để truyền ngưỡng, cấu hình hoặc dữ liệu đầu vào cần dùng chung cho mọi phần tử.

Phân biệt ba nguồn dữ liệu giúp biểu thức dễ đọc:

| Cú pháp | Nguồn |
|---|---|
| `#this` | Active context object hiện tại |
| `#root` | Root object ban đầu |
| `#threshold` | Biến tên threshold trong EvaluationContext |

## 6. Active context object trong collection lồng nhau

Khi collection operation được lồng nhau, mỗi operation có active context object riêng theo phần tử đang xử lý ở cấp đó. Khi một selection hoặc projection bên trong chạy, `#this` chuyển sang phần tử của collection bên trong. Sau khi operation bên trong hoàn tất, expression bên ngoài tiếp tục trong ngữ cảnh của phần tử ngoài đang được xử lý.

Ví dụ một catalog chứa departments, mỗi department có employees:

    #root.departments.![
        employees.?[active].![name]
    ]

Có thể đọc theo từng tầng:

1. Projection ngoài duyệt từng department; active context object của expression ngoài là department.
2. Selection trong `employees` duyệt từng employee; trong predicate `active`, `#this` là employee hiện tại.
3. Projection trong cùng lấy `name` của từng employee phù hợp; `#this` tiếp tục là employee đang được projection xử lý.
4. Kết quả là một collection lồng nhau, mỗi department tương ứng với danh sách tên nhân viên đang active.

Nếu cần tham chiếu root object từ bất kỳ tầng nào, vẫn dùng `#root`. Không dùng `#this` với giả định rằng nó luôn đại diện cho phần tử ở collection ngoài cùng.

Với biểu thức lồng sâu, hãy định dạng mỗi collection operation thành một khối riêng và dùng `#this` tường minh trong predicate quan trọng. Nếu logic cần đồng thời giữ nhiều object cha/con để so sánh, cân nhắc tính một phần dữ liệu trong Java và truyền kết quả qua biến thay vì tạo một expression quá khó theo dõi.

## 7. Collection expression trên Map

Khi selection hoặc projection chạy trên Map, active context object là entry đang được xử lý. Trong predicate, có thể truy cập key và value bằng các tên `key` và `value`.

Ví dụ chọn các entry có value lớn hơn 80:

    #root.scores.?[value >= 80]

Trong predicate này, `#this` đại diện cho Map.Entry hiện tại; `key` là khóa và `value` là giá trị của entry.

Có thể viết rõ:

    #root.scores.?[
        #this.value >= #root.minimumScore
    ]

Projection trên Map cũng đánh giá expression trên từng entry:

    #root.scores.![value]

Kết quả projection là collection các value. Nếu cần dùng cả key và value, hãy tham chiếu `#this.key` và `#this.value` hoặc tạo một object kết quả phù hợp.

Lưu ý thứ tự duyệt phụ thuộc vào implementation của Map. Nếu kết quả cần ổn định theo insertion hoặc theo key, hãy dùng Map có thứ tự xác định.

## 8. Ví dụ đầy đủ trong Java

Ví dụ sau dùng root object là một catalog. Expression lọc các product có giá đạt ngưỡng của catalog, sau đó projection lấy tên:

    public class Catalog {
        private BigDecimal minimumPrice;
        private List<Product> products;

        public BigDecimal getMinimumPrice() {
            return minimumPrice;
        }

        public List<Product> getProducts() {
            return products;
        }
    }

    public class Product {
        private String name;
        private BigDecimal price;

        public String getName() {
            return name;
        }

        public BigDecimal getPrice() {
            return price;
        }
    }

    Catalog catalog = loadCatalog();

    StandardEvaluationContext context =
            new StandardEvaluationContext(catalog);

    ExpressionParser parser = new SpelExpressionParser();

    List<?> names = parser.parseExpression(
            "products.?[price >= #root.minimumPrice].![#this.name]"
    ).getValue(context, List.class);

Trong selection, `#this` lần lượt là từng Product và `#root` vẫn là Catalog. Projection sau selection tiếp tục dùng từng Product đã được giữ lại làm active context object để lấy `name`.

Có thể dùng `#this` tường minh ngay trong selection:

    #root.products.?[
        #this.price >= #root.minimumPrice
    ].![#this.name]

Cách viết này dài hơn một chút nhưng rất hữu ích khi expression có nhiều property trùng tên hoặc được đọc bởi người chưa quen với quy tắc active context.

## 9. Lỗi thường gặp

- **Cho rằng #this luôn là root:** bên trong selection/projection, `#this` chuyển sang phần tử hiện tại.
- **Dùng property root không có #root:** trong predicate, tên property được tra cứu trên phần tử hiện tại; hãy dùng `#root.property` cho root.
- **Nhầm biến với property:** biến phải có tiền tố `#`; giá trị biến không thay đổi khi active context đổi.
- **Quên ngữ cảnh lồng nhau:** trong collection operation bên trong, `#this` đại diện phần tử của collection trong.
- **Giả định #root thay đổi theo từng phần tử:** root luôn là object ban đầu của lần đánh giá.
- **Nhầm Map với List:** selection trên Map xử lý Map.Entry; dùng `key` và `value` để truy cập entry.
- **Dùng expression quá lồng sâu:** tách logic thành biến hoặc xử lý một phần trong Java nếu cần tham chiếu nhiều cấp object.

## 10. Ghi nhớ

Trong SpEL, `#this` là active context object và có thể thay đổi khi expression đi vào selection hoặc projection của collection. Mỗi phần tử đang được xử lý trở thành context object cho predicate hoặc projection expression tương ứng. `#root` luôn giữ root object ban đầu; biến `#variable` cũng giữ nguyên giá trị đã đăng ký trong EvaluationContext. Dùng tên property trực tiếp hoặc `#this.property` cho phần tử hiện tại, và dùng `#root.property` khi cần đọc dữ liệu từ root. Với collection lồng nhau hoặc Map, xác định rõ active context ở từng tầng để tránh truy cập nhầm object.
