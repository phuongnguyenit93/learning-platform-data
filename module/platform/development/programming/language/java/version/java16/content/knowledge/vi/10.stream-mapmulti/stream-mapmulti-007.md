# Tách mapper thành method reference có chữ ký rõ ràng

Mapper của `Stream.mapMulti` có nhiệm vụ nhận một phần tử nguồn và phát không, một hoặc nhiều giá trị xuống pipeline bằng một `Consumer`. Khi logic phát kết quả ngắn, lambda trực tiếp thường dễ đọc. Khi logic dài hơn, được dùng lại hoặc thuộc về kiểu dữ liệu nguồn, ta có thể tách nó thành một phương thức riêng rồi truyền method reference vào `mapMulti`.

Điều quan trọng là chữ ký phương thức được tham chiếu phải tương thích với functional interface `BiConsumer` mà `mapMulti` yêu cầu. Với Stream nguồn kiểu `T` và Stream kết quả kiểu `R`, dạng chữ ký dễ nhận biết nhất là:

```java
void emitResults(T source, Consumer<R> downstream)
```

Phương thức nhận phần tử nguồn trước, Consumer phát kết quả sau và gọi `accept` cho từng giá trị cần gửi xuống pipeline.

## 1. Nhắc lại chữ ký mapper của mapMulti

Phương thức generic trên `Stream<T>` có chữ ký:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Mapper là một `BiConsumer`, vì vậy nó nhận hai đối số và không trả về kết quả trực tiếp:

1. Đối số thứ nhất là phần tử nguồn kiểu `T`.
2. Đối số thứ hai là Consumer dùng để phát phần tử kết quả kiểu `R`.

Một lambda tương ứng có dạng (đoạn mã minh họa bên trong một pipeline):

```java
source.<String>mapMulti((element, emit) -> {
    emit.accept(element.toString());
});
```

Ta có thể chuyển phần thân lambda thành một phương thức có cùng hai tham số, sau đó thay lambda bằng method reference. Cách này giữ nguyên cách hoạt động của pipeline; chỉ thay đổi nơi đặt logic mapper.

## 2. Tách mapper thành static method

Ví dụ, mỗi đơn hàng có nhiều dòng hàng và ta muốn phát SKU của những dòng có số lượng dương. Logic này có thể được đặt trong một static method:

```java
import java.util.List;
import java.util.function.Consumer;

record LineItem(String sku, int quantity) {}
record Order(List<LineItem> items) {}

class OrderMapper {
    static void emitAvailableSkus(
        Order order,
        Consumer<String> emit
    ) {
        for (LineItem item : order.items()) {
            if (item.quantity() > 0) {
                emit.accept(item.sku());
            }
        }
    }

    static List<String> collectSkus(List<Order> orders) {
        return orders.stream()
            .<String>mapMulti(OrderMapper::emitAvailableSkus)
            .toList();
    }
}
```

Method reference:

```java
OrderMapper::emitAvailableSkus
```

được dùng ở vị trí mapper của `mapMulti`. Chữ ký phương thức `emitAvailableSkus(Order, Consumer<String>)` tương thích với mapper nhận một `Order` và một Consumer phát `String`.

Với mỗi đơn hàng, Stream gọi phương thức này một lần. Phương thức duyệt các dòng hàng và gọi `emit.accept` cho từng SKU hợp lệ. Đơn hàng không có dòng hàng hợp lệ sẽ không phát phần tử đầu ra.

## 3. Chữ ký phương thức phải khớp thứ tự tham số

Thứ tự tham số rất quan trọng. `mapMulti` truyền phần tử nguồn trước và Consumer sau. Vì vậy, helper method cũng nên nhận tham số theo thứ tự đó:

```java
import java.util.List;
import java.util.function.Consumer;

record Product(String name) {}

class ProductMapper {
    static void emitLabels(
        Product product,
        Consumer<String> emit
    ) {
        emit.accept(product.name());
        emit.accept("product=" + product.name());
    }

    static List<String> labels(List<Product> products) {
        return products.stream()
            .<String>mapMulti(ProductMapper::emitLabels)
            .toList();
    }
}
```

Một phương thức chỉ nhận Consumer mà không nhận phần tử nguồn không thể thay thế trực tiếp mapper theo dạng static reference này. Tương tự, phương thức nhận Consumer trước rồi mới nhận phần tử nguồn không khớp thứ tự tham số của functional descriptor.

Hãy kiểm tra ba điểm khi tạo helper method:

- Tham số thứ nhất nhận được kiểu phần tử nguồn.
- Tham số thứ hai nhận được Consumer tương thích với kiểu phần tử đầu ra.
- Phương thức thực hiện việc phát kết quả bằng `accept`.

## 4. Dùng unbound instance method reference

Nếu logic phát kết quả thuộc về chính đối tượng nguồn, ta có thể định nghĩa phương thức trên kiểu của phần tử đó. Khi ấy method reference dạng `TypeName::instanceMethod` có thể dùng trực tiếp.

Ví dụ, mỗi bài viết tự biết cách phát các thẻ hợp lệ của nó:

```java
import java.util.List;
import java.util.function.Consumer;

record Article(String title, List<String> tags) {
    void emitTags(Consumer<String> emit) {
        for (String tag : tags) {
            if (tag != null && !tag.isBlank()) {
                emit.accept(tag.trim());
            }
        }
    }
}

class ArticleSearch {
    static List<String> allTags(List<Article> articles) {
        return articles.stream()
            .<String>mapMulti(Article::emitTags)
            .toList();
    }
}
```

Ở đây, `Article::emitTags` là unbound instance method reference. Đối số thứ nhất do Stream truyền vào trở thành đối tượng nhận lời gọi phương thức; đối số thứ hai được truyền vào tham số `emit`.

Có thể hiểu cách ánh xạ như sau:

| Mapper cần nhận | Phương thức trên Article |
|---|---|
| `Article article` | Receiver của `article.emitTags(...)` |
| `Consumer<String> emit` | Tham số của `emitTags` |

Cách viết này phù hợp khi việc phát các giá trị con là trách nhiệm tự nhiên của đối tượng nguồn. Nếu quy tắc phát kết quả thuộc về một lớp xử lý riêng, static helper hoặc mapper object có thể thể hiện trách nhiệm rõ hơn.

## 5. Dùng bound instance method reference

Một lựa chọn khác là đặt logic trong một đối tượng xử lý riêng và truyền method reference gắn với instance đó bằng cú pháp `this::methodName` hoặc `mapper::methodName`.

Ví dụ, một chính sách cảnh báo quyết định các thông báo cần phát cho từng phép đo:

```java
import java.util.List;
import java.util.function.Consumer;

record Measurement(String sensorId, double temperature) {}

class AlertPolicy {
    void emitAlerts(
        Measurement measurement,
        Consumer<String> emit
    ) {
        if (measurement.temperature() >= 80.0) {
            emit.accept(
                measurement.sensorId() + ": high temperature"
            );
        }

        if (measurement.temperature() <= 0.0) {
            emit.accept(
                measurement.sensorId() + ": low temperature"
            );
        }
    }

    List<String> collectAlerts(List<Measurement> measurements) {
        return measurements.stream()
            .<String>mapMulti(this::emitAlerts)
            .toList();
    }
}
```

`this::emitAlerts` giữ lại đối tượng `AlertPolicy` hiện tại làm receiver. Mỗi lần mapper được gọi, Stream truyền `Measurement` và Consumer vào phương thức đó.

Bound method reference hữu ích khi helper cần sử dụng cấu hình hoặc trạng thái bất biến của một đối tượng xử lý. Nếu đối tượng giữ trạng thái mutable, hãy cân nhắc việc Stream có thể chạy song song và gọi mapper đồng thời trên nhiều phần tử nguồn.

## 6. So sánh ba cách viết method reference

Cùng một chữ ký mapper có thể được kết nối theo những cách khác nhau:

| Cách viết | Ý nghĩa |
|---|---|
| `OrderMapper::emitAvailableSkus` | Tham chiếu static method; hai tham số được truyền trực tiếp |
| `Article::emitTags` | Unbound instance method; phần tử nguồn làm receiver |
| `this::emitAlerts` | Bound instance method; đối tượng hiện tại làm receiver |

Cả ba đều có thể phù hợp với vị trí mapper nếu chữ ký thực tế tương thích với `BiConsumer<T, Consumer<R>>`.

Chọn cách đặt logic dựa trên trách nhiệm của nó:

- Dùng static method khi quy tắc không cần trạng thái instance.
- Dùng unbound instance method khi đối tượng nguồn tự chịu trách nhiệm phát dữ liệu của nó.
- Dùng bound instance method khi một đối tượng xử lý giữ chính sách hoặc cấu hình cần thiết để phát kết quả.

## 7. Khi nào nên giữ lambda trực tiếp?

Không cần tách mọi mapper thành phương thức riêng. Với logic ngắn, chỉ dùng một lần và dễ hiểu, lambda trực tiếp thường giúp người đọc nắm được toàn bộ pipeline tại cùng một vị trí:

```java
import java.util.List;

record User(String name, boolean active) {}

List<User> users = List.of(
    new User("An", true),
    new User("Binh", false),
    new User("Chi", true)
);

List<String> names = users.stream()
    .<String>mapMulti((user, emit) -> {
        if (user.active()) {
            emit.accept(user.name());
        }
    })
    .toList();
```

Nên cân nhắc method reference khi:

- Mapper có nhiều dòng xử lý hoặc nhiều nhánh.
- Cùng quy tắc phát kết quả được dùng trong nhiều pipeline.
- Logic phát dữ liệu có tên nghiệp vụ riêng.
- Muốn kiểm tra hoặc đọc riêng quy tắc phát kết quả.
- Kiểu của tham số nguồn và Consumer cần được thể hiện rõ qua chữ ký phương thức.

Nếu tách phương thức làm người đọc phải nhảy qua nhiều lớp mà không tăng khả năng hiểu, lambda ngắn có thể là lựa chọn tốt hơn.

## 8. Kết hợp method reference với type witness

Khi kiểu đầu ra cần được chỉ rõ, có thể đặt type witness ngay trước `mapMulti` dù mapper được truyền bằng method reference:

Tiếp tục dùng kiểu `Order` và `OrderMapper` đã khai báo ở mục 2:

```java
List<Order> orders = List.of(
    new Order(List.of(new LineItem("BOOK-01", 2))),
    new Order(List.of(new LineItem("PEN-02", 0)))
);

List<String> skus = orders.stream()
    .<String>mapMulti(OrderMapper::emitAvailableSkus)
    .toList();
```

Ở đây, `<String>` xác định kiểu phần tử của Stream kết quả. Nó cũng giúp chữ ký mục tiêu của method reference rõ ràng hơn: phương thức được tham chiếu cần tương thích với mapper nhận `Order` và `Consumer<String>`.

Không phải lúc nào cũng cần type witness. Nếu kiểu kết quả được suy luận rõ từ chữ ký phương thức và ngữ cảnh, có thể bỏ nó. Hãy dùng chỉ định kiểu tường minh khi trình biên dịch cần thêm thông tin hoặc khi muốn hợp đồng kiểu dễ đọc hơn.

## 9. Chọn kiểu kết quả chung khi phát nhiều kiểu con

Khi helper phát các giá trị thuộc nhiều kiểu con, hãy khai báo Consumer theo kiểu chung phù hợp. Chẳng hạn, cả `String` và `StringBuilder` đều có thể được phát qua `Consumer<CharSequence>`:

```java
import java.util.List;
import java.util.function.Consumer;

record Article(String title) {}

class ArticleMapper {
    static void emitArticleTitles(
        Article article,
        Consumer<CharSequence> emit
    ) {
        emit.accept(article.title());
        emit.accept(new StringBuilder(article.title()));
    }

    static List<CharSequence> allTitles(List<Article> articles) {
        return articles.stream()
            .<CharSequence>mapMulti(ArticleMapper::emitArticleTitles)
            .toList();
    }
}
```

`<CharSequence>` xác định kiểu phần tử của Stream kết quả. Khi dùng helper generic hoặc có overload, hãy cân nhắc chỉ định type witness để xác định `R`. Nếu có nhiều phương thức cùng tên, chữ ký overload cần được phân biệt rõ. Tên helper riêng cho từng quy tắc thường giúp tránh mơ hồ tốt hơn việc dựa vào suy luận phức tạp.

## 10. Những lỗi thường gặp

**Sai thứ tự tham số.** Mapper nhận phần tử nguồn trước, Consumer sau. Hãy khai báo helper method theo đúng thứ tự này.

**Trả về Stream thay vì phát qua Consumer.** Mapper của `mapMulti` là `BiConsumer`. Helper được dùng làm mapper nên thực hiện việc phát giá trị qua `accept`, không cần tạo Stream con và trả về.

**Dùng nhầm method reference của Consumer.** `Consumer::accept` tham chiếu đến phương thức nhận một giá trị trên một Consumer đã có. Nó không tự trở thành mapper nhận phần tử nguồn cùng Consumer downstream. Hãy tham chiếu đến helper method có đủ hai tham số tương ứng.

**Không khớp kiểu đầu ra.** Nếu Stream kết quả là `Stream<String>`, tham số Consumer của helper phải nhận được Consumer tương thích với `String`, và các giá trị phát ra phải tương thích với kiểu đó.

**Overload gây mơ hồ.** Nhiều helper cùng tên nhưng khác kiểu tham số có thể làm method reference khó được phân giải. Dùng tên riêng hoặc chỉ định kiểu kết quả rõ ràng khi cần.

**Dùng bound reference với trạng thái mutable không an toàn.** Nếu parallel Stream gọi mapper đồng thời, instance được capture bởi `this::method` có thể được nhiều lần gọi dùng chung. Tránh thay đổi trạng thái chung trong helper hoặc bảo đảm việc truy cập được thiết kế an toàn.

## 11. Ghi nhớ

- Mapper của `mapMulti` tương thích với `BiConsumer<T, Consumer<R>>`.
- Chữ ký helper dễ đọc nhất thường là `void method(T source, Consumer<R> emit)`.
- Static method reference dùng dạng `ClassName::method`.
- Unbound instance method reference có thể dùng phần tử nguồn làm receiver, ví dụ `Article::emitTags`.
- Bound instance method reference giữ receiver cụ thể, ví dụ `this::emitAlerts`.
- Type witness `.<String>mapMulti(...)` có thể kết hợp với method reference để làm rõ kiểu kết quả.
- Chỉ tách mapper khi tên phương thức, khả năng tái sử dụng hoặc độ phức tạp làm mã dễ hiểu hơn.

Khi chữ ký helper khớp với mapper của `mapMulti`, method reference giúp pipeline gọn hơn và đặt quy tắc phát dữ liệu vào một phương thức có tên rõ ràng, dễ đọc và dễ tái sử dụng.

