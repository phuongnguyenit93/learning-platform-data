# comparing, comparingInt và các bộ so sánh theo khóa

Khi sắp xếp một danh sách sản phẩm, ta có thể muốn sắp theo tên, số lượng tồn, giá hoặc điểm đánh giá. Đối tượng vẫn là `Product`, nhưng **khóa sắp xếp** được lấy từ một thuộc tính hoặc phép tính trên đối tượng đó.

Các phương thức `Comparator.comparing(...)`, `comparingInt(...)`, `comparingLong(...)` và `comparingDouble(...)` giúp biểu đạt quy tắc này: chỉ ra cách lấy khóa, rồi dùng quy tắc phù hợp để so sánh các khóa. Không cần lặp lại toàn bộ mã so sánh hai đối tượng mỗi khi thay tiêu chí.

Trong bài, “khóa” là giá trị phục vụ so sánh, không mặc nhiên là khóa chính, mã duy nhất hay khóa của một `Map`.

## 1. Mô hình: lấy khóa rồi so sánh khóa

Giả sử mỗi sản phẩm có số lượng tồn kho kiểu `int`:

~~~java
// Đoạn mã minh họa; Product là kiểu có phương thức stock() trả int.
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);
~~~

Khi gọi:

~~~java
// left và right là hai Product không null.
int result = byStock.compare(left, right);
~~~

Có thể hình dung ba bước:

1. Lấy `left.stock()`.
2. Lấy `right.stock()`.
3. So sánh hai giá trị `int` để quyết định thứ tự của hai sản phẩm.

Một cách viết dài hơn, có cùng ý nghĩa so sánh trong trường hợp này:

~~~java
Comparator<Product> byStock =
        (left, right) -> Integer.compare(left.stock(), right.stock());
~~~

Dấu của kết quả có ý nghĩa:

| Kết quả `compare(left, right)` | Ý nghĩa theo comparator |
| --- | --- |
| Âm | `left` đứng trước `right`. |
| Bằng `0` | Hai đối tượng ngang nhau theo các tiêu chí comparator đang xét. |
| Dương | `left` đứng sau `right`. |

Không kiểm tra comparator chỉ bằng `result == -1` hoặc `result == 1`. Hợp đồng dùng dấu, không yêu cầu mọi comparator chỉ trả đúng ba giá trị `-1, 0, 1`.

Việc tạo comparator không tự thay đổi danh sách:

~~~java
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);

// Chưa có thao tác sắp xếp nào xảy ra ở dòng trên.
products.sort(byStock); // Đến đây mới sắp xếp danh sách có thể sửa.
~~~

Bài này dùng các API có từ Java 8 và ví dụ chương trình hoàn chỉnh chạy được trên Java 17 trở lên. Chữ ký các biến thể được đối chiếu với [Java SE 17 Comparator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

## 2. comparing với thứ tự tự nhiên của khóa

Dạng một tham số nhận hàm lấy khóa có kiểu triển khai `Comparable`:

~~~java
static <T, U extends Comparable<? super U>>
Comparator<T> comparing(
        Function<? super T, ? extends U> keyExtractor
)
~~~

Đây là chữ ký API để đọc hiểu, không phải phương thức cần tự viết trong ứng dụng.

- `T`: kiểu đối tượng được sắp xếp, chẳng hạn `Product`.
- `U`: kiểu khóa lấy ra, chẳng hạn `String`.
- `keyExtractor`: hàm nhận đối tượng và trả khóa.
- Kết quả vẫn là `Comparator<T>`, không phải `Comparator<U>`.

Ví dụ:

~~~java
// Product.name() trả String.
Comparator<Product> byName = Comparator.comparing(Product::name);
~~~

`Product` không cần triển khai `Comparable<Product>`. Chỉ khóa `String` của dạng `comparing` này cần có thứ tự tự nhiên.

Method reference `Product::name` biểu đạt cách lấy tên từ một sản phẩm. Trong ngữ cảnh này, nó tương đương với lambda:

~~~java
Comparator<Product> byName =
        Comparator.comparing((Product product) -> product.name());
~~~

Comparator so sánh sản phẩm theo các chuỗi tên. Nó không “sắp xếp các trường bên trong từng Product”, không đổi tên và không tạo một danh sách tên thay cho danh sách sản phẩm.

### Các loại khóa đối tượng thường gặp

Có thể lấy `String`, `LocalDate`, `Instant`, `BigDecimal` hoặc một kiểu khác có thứ tự phù hợp. Chỉ chọn được API chưa đủ: phải xác nhận thứ tự của khóa đúng với nghiệp vụ.

Ví dụ, thứ tự tự nhiên của `String` không tự trở thành thứ tự ngôn ngữ tiếng Việt. Nếu cần sắp tên theo quy tắc ngôn ngữ, phải xác định một quy tắc so sánh phù hợp thay vì giả định `String.compareTo` giải quyết mọi trường hợp.

## 3. comparing với comparator riêng cho khóa

Dạng hai tham số tách rõ cách lấy khóa và cách so sánh khóa:

~~~java
static <T, U>
Comparator<T> comparing(
        Function<? super T, ? extends U> keyExtractor,
        Comparator<? super U> keyComparator
)
~~~

Trong dạng này, khóa không bắt buộc phải tự triển khai `Comparable`, vì đã có `keyComparator` chỉ ra cách so sánh.

Ví dụ so sánh tên không phân biệt chữ hoa–thường:

~~~java
Comparator<Product> byNameIgnoringCase =
        Comparator.comparing(
                Product::name,
                String.CASE_INSENSITIVE_ORDER
        );
~~~

Có hai comparator với hai vai trò:

- `String.CASE_INSENSITIVE_ORDER` so sánh **hai khóa String**.
- `byNameIgnoringCase` so sánh **hai Product**, sau khi lấy tên của chúng.

Không truyền `Comparator<Product>` vào vị trí comparator cho khóa `String`. Kiểu của comparator phụ thuộc vào thứ được so sánh ở từng tầng.

### Khi khóa là một kiểu không có thứ tự tự nhiên

Giả sử một chương trình có:

~~~java
// Minh họa các khai báo trong một lớp; cần import java.util.Comparator.
record Category(int rank, String label) {}
record Item(String code, Category category) {}

Comparator<Category> categoryOrder =
        Comparator.comparingInt(Category::rank)
                .thenComparing(Category::label);

Comparator<Item> itemOrder =
        Comparator.comparing(Item::category, categoryOrder);
~~~

`Category` không khai báo `implements Comparable<Category>`. Vì vậy, `Comparator.comparing(Item::category)` một tham số không có đủ cơ sở để dùng thứ tự tự nhiên của `Category`.

Dạng hai tham số giải quyết đúng vấn đề: lấy `Category` từ `Item`, rồi so sánh bằng `categoryOrder`. Các ví dụ này giả định đối tượng và khóa không `null`; cách xử lý `null` được trình bày riêng ở dưới.

## 4. comparingInt: khóa int, đối tượng vẫn là T

Chữ ký:

~~~java
static <T> Comparator<T> comparingInt(
        ToIntFunction<? super T> keyExtractor
)
~~~

`ToIntFunction<T>` là hàm nhận một `T` và trả một giá trị nguyên thủy `int`. So với dạng `Function<T, Integer>`, nó không cần biểu diễn khóa bằng đối tượng `Integer`.

~~~java
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);
~~~

Chọn `comparingInt` khi khóa tự nhiên của bài toán là `int`, chẳng hạn số lượng, số lần thử hoặc độ dài chuỗi.

Có thể lấy khóa bằng một phép tính:

~~~java
Comparator<Product> byNameLength =
        Comparator.comparingInt(product -> product.name().length());
~~~

Ở đây, sản phẩm có tên ngắn hơn đứng trước. Hai tên khác nhau nhưng cùng độ dài sẽ được comparator xem là ngang nhau nếu chưa thêm tiêu chí phụ.

### comparing với int có nhất thiết sai không?

Không. Đoạn sau có thể biên dịch:

~~~java
Comparator<Product> boxed =
        Comparator.comparing(Product::stock);
~~~

Vì `comparing` cần khóa đối tượng, giá trị `int` có thể được boxing thành `Integer`, rồi so sánh bằng thứ tự tự nhiên của `Integer`.

Tuy nhiên, khi ý định rõ là so sánh số nguyên thủy, `comparingInt` diễn đạt trực tiếp hơn và tránh yêu cầu boxing của đường so sánh khóa. Không nên từ đó khẳng định mọi chương trình chắc chắn nhanh hơn một mức cố định: chi phí thực tế còn phụ thuộc dữ liệu, số lần so sánh, JVM và các công việc khác trong hàm lấy khóa.

Quan trọng hơn, `comparingInt` **không** biến `Comparator<Product>` thành một comparator dành cho `Integer`, và không làm thay đổi kiểu dữ liệu lưu trong danh sách.

## 5. Các biến thể cho long và double

| Kiểu khóa phù hợp | API tạo comparator | Kiểu hàm lấy khóa |
| --- | --- | --- |
| Đối tượng có thứ tự tự nhiên | `comparing(extractor)` | `Function<? super T, ? extends U>` |
| Đối tượng với quy tắc so sánh riêng | `comparing(extractor, keyComparator)` | `Function` cùng comparator cho khóa |
| `int` | `comparingInt(extractor)` | `ToIntFunction<? super T>` |
| `long` | `comparingLong(extractor)` | `ToLongFunction<? super T>` |
| `double` | `comparingDouble(extractor)` | `ToDoubleFunction<? super T>` |

Ví dụ:

~~~java
Comparator<Product> byPrice =
        Comparator.comparingLong(Product::priceInCents);

Comparator<Product> byRating =
        Comparator.comparingDouble(Product::rating);
~~~

Chọn API theo kiểu khóa và ý nghĩa dữ liệu. Đừng ép một giá trị `long` thành `int` chỉ để dùng `comparingInt`; việc thu hẹp kiểu có thể làm mất thông tin và đổi thứ tự.

Tương tự, không chuyển dữ liệu cần độ chính xác nguyên vẹn từ `long` sang `double` một cách tùy tiện. Chữ ký chấp nhận một phép chuyển kiểu không có nghĩa phép chuyển đó giữ nguyên ý nghĩa của mọi giá trị.

Với tiền trong ví dụ chương trình, `priceInCents` là một giá trị `long` tính theo đơn vị nhỏ nhất của hệ thống mẫu. Đây là quyết định mô hình dữ liệu của ví dụ, không phải quy tắc bắt buộc mọi ứng dụng tiền tệ đều phải dùng `long`.

`comparingDouble` thực hiện so sánh số theo hành vi so sánh `double` của Java. Nếu miền dữ liệu có `NaN`, vô cực hoặc hai dạng zero, cần xác định liệu các giá trị đó có hợp lệ với nghiệp vụ không. Không tự viết comparator bằng cách trừ hai `double` rồi ép sang `int`: hai số khác nhau có thể bị biến thành kết quả bằng `0`, chưa kể các giá trị đặc biệt.

Không có nhóm factory riêng tên `comparingBoolean`, `comparingFloat` hay `comparingShort` trong interface `Comparator`. Với khóa kiểu khác, chọn cách ánh xạ hoặc comparator thích hợp và nói rõ ý nghĩa thứ tự. Chẳng hạn, `float` có thể được mở rộng sang `double` để so sánh, còn thứ tự ưu tiên của một trạng thái boolean thường nên được diễn đạt theo yêu cầu nghiệp vụ.

## 6. Không dùng phép trừ để thay phép so sánh số

Cách viết dễ mắc lỗi:

~~~java
Comparator<Product> unsafe =
        (left, right) -> left.stock() - right.stock();
~~~

Phép trừ `int` có thể tràn. Với:

~~~text
left.stock()  = Integer.MIN_VALUE
right.stock() = Integer.MAX_VALUE
~~~

Về giá trị, bên trái nhỏ hơn bên phải. Nhưng phép trừ `int` trong Java cho kết quả `1`, khiến comparator trả dấu dương và khẳng định điều ngược lại.

Cách viết an toàn cho tiêu chí này:

~~~java
Comparator<Product> byStock =
        Comparator.comparingInt(Product::stock);

// Hoặc khi thật sự cần viết lambda:
Comparator<Product> byStockExplicit =
        (left, right) -> Integer.compare(left.stock(), right.stock());
~~~

Với `long`, cũng không viết:

~~~java
// Ví dụ sai: có thể tràn ở phép trừ hoặc mất thông tin khi ép về int.
Comparator<Product> unsafePrice =
        (left, right) -> (int) (left.priceInCents() - right.priceInCents());
~~~

Dùng `comparingLong` hoặc `Long.compare`. Mục tiêu là tạo dấu so sánh đúng, không phải lấy chênh lệch số học rồi hy vọng dấu vẫn đúng sau mọi phép biến đổi.

## 7. Thêm tiêu chí phụ bằng thenComparing

Nếu chỉ sắp theo số lượng tồn, nhiều sản phẩm có cùng `stock`. Khi muốn cùng số lượng thì theo mã:

~~~java
Comparator<Product> byStockThenCode =
        Comparator.comparingInt(Product::stock)
                .thenComparing(Product::code);
~~~

Quá trình so sánh:

1. So sánh `stock`.
2. Nếu kết quả khác `0`, dùng kết quả đó.
3. Chỉ khi `stock` bằng nhau, mới xét `code`.

Đây là so sánh lần lượt theo tiêu chí, không phải cộng các kết quả so sánh hoặc cộng giá trị các khóa.

Những biến thể có tên tương ứng giúp nối thêm khóa nguyên thủy:

~~~java
Comparator<Product> order =
        Comparator.comparing(Product::category)
                .thenComparingInt(Product::stock)
                .thenComparingLong(Product::priceInCents)
                .thenComparingDouble(Product::rating)
                .thenComparing(Product::code);
~~~

Ví dụ này giả định `category` và `code` không `null`; nó minh họa cú pháp, không phải quy tắc sắp xếp bắt buộc của một ứng dụng bán hàng.

Cũng có thể chỉ định quy tắc riêng cho khóa phụ:

~~~java
Comparator<Product> order =
        Comparator.comparingInt(Product::stock)
                .thenComparing(
                        Product::name,
                        String.CASE_INSENSITIVE_ORDER
                )
                .thenComparing(Product::code);
~~~

Nếu hai sản phẩm ngang nhau theo tất cả các khóa đã chọn, comparator trả `0`. Không nên tự thêm một tiêu chí ngẫu nhiên để “bắt buộc khác nhau”; hãy xác định đúng yêu cầu về thứ tự và định nghĩa tương đương của dữ liệu.

## 8. Giảm dần: reversed đặt ở đâu thì đảo phần đó

Giảm dần theo số lượng tồn, sau đó tăng dần theo giá:

~~~java
Comparator<Product> stockDescPriceAsc =
        Comparator.comparingInt(Product::stock)
                .reversed()
                .thenComparingLong(Product::priceInCents)
                .thenComparing(Product::code);
~~~

`reversed()` ở đây chỉ đảo comparator số lượng đã tạo trước đó. Các tiêu chí nối sau vẫn theo chiều tăng dần.

Ngược lại:

~~~java
Comparator<Product> allDesc =
        Comparator.comparingInt(Product::stock)
                .thenComparingLong(Product::priceInCents)
                .thenComparing(Product::code)
                .reversed();
~~~

Dòng cuối đảo **toàn bộ chuỗi** comparator đã được ghép, gồm cả giá và mã.

Cần đọc chuỗi từ trái sang phải theo các comparator đã được hình thành, không chỉ đếm số lần có từ `reversed`.

Với khóa đối tượng, có thể đảo riêng khóa bằng dạng hai tham số:

~~~java
Comparator<Product> nameDescending =
        Comparator.comparing(Product::name, Comparator.reverseOrder());
~~~

Đây là chiều ngược của thứ tự tự nhiên của tên. Nó không thay thế một quy tắc so sánh ngôn ngữ hoặc quy tắc không phân biệt chữ hoa–thường nếu nghiệp vụ cần những quy tắc đó.

## 9. Null của phần tử và null của khóa là hai vấn đề

Xét một danh sách có thể chứa:

- Một `Product` không `null`, nhưng `product.category()` trả `null`.
- Chính phần tử `Product` là `null`.

Hai trường hợp thất bại ở hai tầng khác nhau.

### Khóa có thể null

Muốn sản phẩm chưa có nhóm đứng cuối:

~~~java
Comparator<Product> byCategory =
        Comparator.comparing(
                Product::category,
                Comparator.nullsLast(Comparator.naturalOrder())
        ).thenComparing(Product::code);
~~~

Comparator bọc bên trong là `Comparator<String>` dành cho khóa `category`. Nó xử lý `null` của khóa.

Đoạn mã chưa xử lý một phần tử `Product` là `null`: khi cần gọi `Product::category` trên phần tử đó, vẫn có lỗi.

### Phần tử cũng có thể null

Bọc comparator hoàn chỉnh ở ngoài:

~~~java
Comparator<Product> safe =
        Comparator.nullsLast(byCategory);
~~~

Tầng ngoài xử lý `null` của `Product`. Với các sản phẩm khác `null`, nó giao việc so sánh cho `byCategory`.

Một cấu trúc dễ nhớ:

~~~text
null của Product?
    -> comparator bọc bên ngoài

Product tồn tại nhưng category null?
    -> comparator dành cho khóa category
~~~

Nếu `code` cũng có thể `null`, tiêu chí phụ `thenComparing(Product::code)` cần có chính sách `null` riêng. Một tầng xử lý `null` cho `category` không tự bao phủ mọi khóa khác.

### Hàm lấy khóa lồng nhau

Với biểu thức như:

~~~java
product -> product.category().label()
~~~

Nếu `category()` trả `null`, lỗi xảy ra ngay trong hàm lấy khóa, trước khi comparator của khóa có thể xử lý giá trị trả về.

Cần chọn một trong các thiết kế phù hợp:

- Không cho phép thiếu `category` và kiểm tra dữ liệu từ trước.
- Cho hàm lấy khóa trả `null` khi thiếu đối tượng trung gian, rồi dùng comparator hỗ trợ `null`.
- So sánh trực tiếp đối tượng `Category` bằng một comparator có xử lý `null`.

Không dùng chuỗi rỗng hoặc một giá trị số tùy ý để thay `null` nếu điều đó làm lẫn “thiếu dữ liệu” với một dữ liệu hợp lệ.

### Đảo thứ tự có thể đổi vị trí null

Đảo một comparator đã đặt `null` ở cuối sẽ đảo cả quan hệ đó, làm `null` về đầu.

Nếu muốn khóa khác `null` giảm dần nhưng `null` vẫn đứng cuối, hãy đặt:

~~~java
Comparator<Product> categoryDescendingNullLast =
        Comparator.comparing(
                Product::category,
                Comparator.nullsLast(Comparator.reverseOrder())
        );
~~~

Đây là một lý do nữa để xác định rõ vị trí của từng lớp bọc.

## 10. Kiểu generic, lambda và suy luận kiểu

Method reference thường làm kiểu rõ ràng:

~~~java
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);
~~~

Trong một số chuỗi gọi phức tạp, lambda không có kiểu tham số rõ ràng có thể khiến trình biên dịch chưa suy ra `Product` ở điểm cần thiết. Có thể cung cấp thông tin kiểu bằng một trong hai cách:

~~~java
Comparator<Product> first =
        Comparator.comparingInt((Product product) -> product.stock())
                .reversed();

Comparator<Product> second =
        Comparator.<Product>comparingInt(product -> product.stock())
                .reversed();
~~~

Không sửa lỗi suy luận bằng cách dùng raw type `Comparator` rồi ép kiểu. Cách đó làm mất kiểm tra kiểu mà generic vốn cung cấp.

Với dạng `comparing` hai tham số, nhớ rằng `T` là kiểu phần tử còn `U` là kiểu khóa. Hàm lấy khóa và comparator của khóa phải thống nhất về `U`.

Dùng `var` không có nghĩa Java luôn đoán được kiểu phần tử từ một lambda chưa được định kiểu. Khi thiếu ngữ cảnh, hãy dùng method reference có kiểu rõ, kiểu tham số lambda, hoặc đối số kiểu tường minh.

## 11. Hàm lấy khóa cần ổn định và có chi phí phù hợp

Các factory không hứa chỉ gọi hàm lấy khóa đúng một lần cho mỗi phần tử trong toàn bộ quá trình sort. Sort có thể so sánh cùng phần tử nhiều lần.

Vì vậy, tránh hàm lấy khóa:

- Gọi mạng hoặc truy vấn cơ sở dữ liệu.
- Đọc giá trị thời gian hiện tại để quyết định thứ tự.
- Thay đổi thuộc tính của đối tượng mỗi lần được gọi.
- Phụ thuộc một biến toàn cục đang thay đổi.
- Tạo giá trị ngẫu nhiên.

Nếu khóa thay đổi giữa các lần so sánh, tính nhất quán của comparator có thể bị phá vỡ. Nếu khóa chỉ đắt đỏ nhưng ổn định, thời gian sort có thể bị chi phối bởi việc tính lại khóa.

Với khóa tính toán tốn kém, cân nhắc tính trước thành dữ liệu phụ dùng trong lần sắp xếp:

~~~java
// Minh họa ý tưởng, không phải chương trình độc lập.
record RankedProduct(Product product, int computedRank) {}

Comparator<RankedProduct> order =
        Comparator.comparingInt(RankedProduct::computedRank)
                .thenComparing(value -> value.product().code());
~~~

Bước tạo các `RankedProduct` sẽ tính khóa theo quy tắc nghiệp vụ, rồi sort chỉ đọc lại khóa đã có. Cách này tăng bộ nhớ và cần xác định thời điểm chụp dữ liệu. Không nên thêm bộ nhớ đệm toàn cục chỉ để tránh tính lại mà bỏ qua việc khóa có thể thay đổi.

Các factory cũng không bảo vệ khóa khỏi thay đổi sau khi đã đưa phần tử vào một `TreeSet` hoặc cấu trúc dựa trên comparator. Nếu khóa quyết định vị trí bị thay đổi tại chỗ, phải cập nhật cấu trúc theo một quy trình đúng, thay vì chờ comparator tự di chuyển đối tượng.

## 12. Chương trình hoàn chỉnh

Lưu thành **KeyComparatorDemo.java**. Dữ liệu mẫu dùng:

- `name`: khóa `String`.
- `stock`: khóa `int`.
- `priceInCents`: khóa `long`.
- `rating`: khóa `double`.
- `category`: khóa `String` có thể `null`.
- `code`: tiêu chí phụ để kết quả trong ví dụ được xác định rõ.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class KeyComparatorDemo {
    record Product(
            String code,
            String name,
            int stock,
            long priceInCents,
            double rating,
            String category
    ) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("P3", "banana", 4, 250L, 4.6, "food"),
                new Product("P1", "Apple", 10, 500L, 4.2, "food"),
                new Product("P4", "cable", 4, 1000L, 4.8, null),
                new Product("P2", "apple", 4, 300L, 4.2, "tools")
        );

        Comparator<Product> byName = Comparator.comparing(Product::name);
        Comparator<Product> byNameIgnoringCase =
                Comparator.comparing(
                        Product::name,
                        String.CASE_INSENSITIVE_ORDER
                ).thenComparing(Product::code);

        Comparator<Product> byStockThenCode =
                Comparator.comparingInt(Product::stock)
                        .thenComparing(Product::code);

        Comparator<Product> byPrice =
                Comparator.comparingLong(Product::priceInCents)
                        .thenComparing(Product::code);

        Comparator<Product> byRatingDescending =
                Comparator.comparingDouble(Product::rating)
                        .reversed()
                        .thenComparing(Product::code);

        Comparator<Product> byStockDescendingThenPrice =
                Comparator.comparingInt(Product::stock)
                        .reversed()
                        .thenComparingLong(Product::priceInCents)
                        .thenComparing(Product::code);

        Comparator<Product> wholeOrderReversed =
                Comparator.comparingInt(Product::stock)
                        .thenComparingLong(Product::priceInCents)
                        .thenComparing(Product::code)
                        .reversed();

        Comparator<Product> byNullableCategory =
                Comparator.comparing(
                        Product::category,
                        Comparator.nullsLast(Comparator.naturalOrder())
                ).thenComparing(Product::code);

        printCodes("Name natural", products, byName);
        printCodes("Name ignoring case", products, byNameIgnoringCase);
        printCodes("Stock then code", products, byStockThenCode);
        printCodes("Price", products, byPrice);
        printCodes("Rating descending", products, byRatingDescending);
        printCodes("Stock descending, price ascending",
                products, byStockDescendingThenPrice);
        printCodes("Whole chain reversed", products, wholeOrderReversed);
        printCodes("Category nulls last", products, byNullableCategory);

        List<Product> includingNull = new ArrayList<>(products);
        includingNull.add(null);

        printCodes("Null elements last",
                includingNull, Comparator.nullsLast(byNullableCategory));

        System.out.println("Original = " + codes(products));

        Product min = new Product(
                "MIN", "min", Integer.MIN_VALUE, 0L, 0.0, "demo");
        Product max = new Product(
                "MAX", "max", Integer.MAX_VALUE, 0L, 0.0, "demo");

        Comparator<Product> bad =
                (left, right) -> left.stock() - right.stock();
        Comparator<Product> safe =
                Comparator.comparingInt(Product::stock);

        System.out.println("Subtraction sign = "
                + Integer.signum(bad.compare(min, max)));
        System.out.println("comparingInt sign = "
                + Integer.signum(safe.compare(min, max)));
    }

    private static void printCodes(
            String label,
            List<Product> source,
            Comparator<? super Product> order
    ) {
        List<Product> copy = new ArrayList<>(source);
        copy.sort(order);
        System.out.println(label + " = " + codes(copy));
    }

    private static List<String> codes(List<Product> products) {
        List<String> result = new ArrayList<>();
        for (Product product : products) {
            result.add(product == null ? "<null>" : product.code());
        }
        return result;
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 KeyComparatorDemo.java
java KeyComparatorDemo
~~~

Stdout:

~~~text
Name natural = [P1, P2, P3, P4]
Name ignoring case = [P1, P2, P3, P4]
Stock then code = [P2, P3, P4, P1]
Price = [P3, P2, P1, P4]
Rating descending = [P4, P3, P1, P2]
Stock descending, price ascending = [P1, P3, P2, P4]
Whole chain reversed = [P1, P4, P2, P3]
Category nulls last = [P1, P3, P2, P4]
Null elements last = [P1, P3, P2, P4, <null>]
Original = [P3, P1, P4, P2]
Subtraction sign = 1
comparingInt sign = -1
~~~

### Giải thích các kết quả quan trọng

- Hai dòng tên có cùng dãy mã trong bộ dữ liệu mẫu, nhưng quy tắc khác nhau: `"Apple"` và `"apple"` được so sánh khác theo thứ tự tự nhiên; quy tắc không phân biệt hoa–thường xem chúng ngang nhau và dùng mã làm tiêu chí phụ.
- Khi sắp theo tồn kho rồi mã, nhóm tồn `4` đứng trước nhóm tồn `10`; trong nhóm tồn `4`, mã lần lượt là `P2, P3, P4`.
- Giá tăng dần là `250, 300, 500, 1000`, tương ứng `P3, P2, P1, P4`.
- Điểm giảm dần đặt `P4` trước `P3`. `P1` và `P2` cùng điểm `4.2`, nên mã giải quyết thứ tự.
- Với tồn kho giảm dần rồi giá tăng dần, `P1` đứng đầu; nhóm tồn `4` đi theo giá `250, 300, 1000`.
- Đảo cả chuỗi làm nhóm tồn `4` đi theo chiều ngược của giá tăng dần, nên kết quả là `P4, P2, P3`.
- Nhóm `category == null` đứng sau các nhóm có tên; một phần tử `Product == null` được xử lý bởi comparator bọc ngoài và đứng cuối cùng.
- `printCodes` tạo bản sao trước khi sort. Dòng `Original` xác nhận danh sách nguồn giữ nguyên dãy mã ban đầu.
- Hai dòng cuối chứng minh bằng dữ liệu biên: phép trừ cho dấu `1` sai ý nghĩa, còn `comparingInt` cho dấu `-1` đúng với quan hệ `MIN_VALUE < MAX_VALUE`.

## 13. Comparator chỉ theo khóa và ý nghĩa compare bằng 0

Nếu chỉ dùng:

~~~java
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);
~~~

thì mọi sản phẩm có cùng tồn kho đều có thể cho kết quả so sánh bằng `0`, dù khác mã, tên hoặc giá.

Với việc sort một danh sách, điều này không tự xóa bớt sản phẩm. Một phép sắp xếp ổn định giữ thứ tự tương đối trước sort của những phần tử được comparator xem là ngang nhau.

Nhưng nếu dùng comparator đó cho `TreeSet<Product>`, cấu trúc dùng kết quả so sánh để xác định vị trí tương đương. Hai sản phẩm cùng tồn kho có thể chỉ chiếm một vị trí trong tập hợp. Vì vậy, một comparator hợp lý cho **trình bày danh sách theo một tiêu chí** chưa chắc hợp lý cho **tập hợp xác định tính duy nhất**.

Chỉ thêm `thenComparing(Product::code)` khi mã thực sự là tiêu chí phân biệt phù hợp. Nếu cần comparator nhất quán với `equals`, phải đối chiếu toàn bộ định nghĩa `equals` của kiểu dữ liệu, không chỉ thêm một trường rồi cho rằng mọi trường hợp đều được giải quyết.

## 14. Kiểm tra một comparator theo khóa

Bắt đầu bằng dữ liệu nhỏ để người đọc có thể tự tính kết quả:

1. Hai phần tử có khóa khác nhau.
2. Hai phần tử có khóa chính bằng nhau nhưng khóa phụ khác nhau.
3. Hai phần tử ngang nhau theo toàn bộ tiêu chí.
4. Giá trị `int` hoặc `long` ở hai biên nếu có xử lý số.
5. Khóa `null`, đối tượng `null`, và đối tượng trung gian `null` nếu miền dữ liệu cho phép.
6. Thứ tự giảm dần với `null` để kiểm tra phạm vi `reversed()`.

Có thể kiểm tra các thuộc tính của quan hệ so sánh:

- Đổi chỗ hai đối tượng phải đảo dấu, trừ trường hợp cả hai chiều đều bằng `0`.
- Nếu `a` đứng sau `b`, `b` đứng sau `c`, thì `a` phải đứng sau `c`.
- Nếu `a` và `b` ngang nhau, chúng phải có cùng quan hệ về dấu khi được so với một `c` khác.

Với các factory, lỗi thường nằm ở quy tắc khóa, dữ liệu, lớp bọc hoặc chuỗi kết hợp hơn là ở việc tự viết thuật toán so sánh. Kiểm thử cần phản ánh đúng quy tắc nghiệp vụ, không chỉ chứng minh danh sách có thể chạy qua `sort`.

## 15. Lỗi thường gặp

| Cách viết hoặc cách hiểu | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Gọi `comparing` rồi nghĩ danh sách đã được sort | Mới chỉ tạo một comparator | Truyền comparator cho thao tác cần nó. |
| Dùng `comparingInt` với lambda trả `long` | Sai kiểu khóa hoặc phải ép kiểu gây mất dữ liệu | Dùng `comparingLong`. |
| Dùng phép trừ làm kết quả so sánh | Có thể tràn số hoặc mất thông tin | Dùng factory số nguyên thủy hoặc hàm `compare`. |
| Dùng `comparing` một tham số cho khóa không có `Comparable` | Không có thứ tự tự nhiên để dùng | Truyền thêm comparator cho khóa. |
| Chỉ bọc `nullsLast` ở ngoài | Xử lý phần tử `null`, chưa xử lý khóa `null` | Đặt quy tắc ở từng tầng thực sự có thể thiếu dữ liệu. |
| Chỉ bọc `nullsLast` ở comparator khóa | Không ngăn gọi extractor trên phần tử `null` | Bọc comparator đối tượng nếu cần. |
| Gọi `reversed` cuối chuỗi trong khi chỉ muốn giảm một khóa | Đảo toàn bộ thứ tự đã ghép | Đảo comparator thành phần trước khi nối tiêu chí tiếp theo. |
| Khóa phụ đắt đỏ được tính sẵn cho mọi lần so sánh dù chưa cần | Tăng chi phí và có thể tạo tác dụng phụ | Dùng chuỗi comparator đúng ý nghĩa; cân nhắc tính trước khóa ở cấp dữ liệu khi phù hợp. |
| Đổi khóa của phần tử khi nó nằm trong cấu trúc có thứ tự | Vị trí cấu trúc không tự được cập nhật | Thiết kế thao tác lấy ra, cập nhật và thêm lại hoặc dùng dữ liệu bất biến. |
| Dùng comparator của danh sách cho TreeSet mà không xét tính duy nhất | Có thể mất những phần tử có khóa bằng nhau | Xác định lại quan hệ tương đương hoặc chọn cấu trúc khác. |

## 16. Thực hành

1. Thêm quy tắc: tên không phân biệt hoa–thường tăng dần, tồn kho giảm dần, rồi mã tăng dần. Viết comparator và giải thích phạm vi mỗi lần `reversed`.
2. Viết comparator cho sản phẩm theo độ dài tên, rồi tên theo thứ tự tự nhiên. Nêu các trường hợp phải xử lý nếu tên có thể `null`.
3. Sửa ví dụ để `category` giảm dần nhưng khóa `null` vẫn đứng cuối, còn phần tử `null` đứng đầu.
4. Tạo hai sản phẩm khác mã nhưng cùng tồn kho. So sánh kết quả khi dùng comparator theo tồn cho `List` và cho `TreeSet`.
5. Tạo một kiểu khóa không triển khai `Comparable`; viết comparator cho khóa rồi dùng dạng hai tham số của `comparing`.
6. Nếu khóa là một điểm đánh giá phải tính rất tốn kém, hãy thiết kế cách chụp khóa một lần cho mỗi phần tử trong một lượt xử lý và nêu cách xử lý khi dữ liệu gốc thay đổi.

Trước khi chọn factory, hãy trả lời ba câu: đang so sánh kiểu đối tượng nào, khóa lấy ra có kiểu gì, và quy tắc nào quyết định thứ tự giữa các khóa đó. Sau đó mới xét tiêu chí phụ, chiều tăng–giảm và chính sách dữ liệu thiếu.
