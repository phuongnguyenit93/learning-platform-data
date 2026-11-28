# Phát dữ liệu bằng consumer.accept và loại phần tử bằng cách không phát

Trong `Stream.mapMulti`, mapper gửi dữ liệu đầu ra bằng cách gọi `consumer.accept(value)` trên Consumer được truyền vào. Mỗi lần gọi `accept` tạo một phần tử cho Stream kết quả. Nếu mapper không gọi `accept`, phần tử nguồn hiện tại không tạo ra phần tử đầu ra.

Cơ chế này cho phép một phần tử nguồn tạo ra không, một hoặc nhiều kết quả. Nó đặc biệt phù hợp khi cần duyệt dữ liệu con, kiểm tra nhiều điều kiện hoặc phát kết quả theo nhiều nhánh. Bài học này tập trung vào cách phát và loại phần tử đúng cách, đồng thời phân biệt trường hợp nên dùng `mapMulti` với `filter` hoặc `flatMap`.

## 1. accept là thao tác phát một phần tử

Trong mapper của `mapMulti`, tham số thứ hai là một Consumer. Ta có thể đặt tên tham số này là `consumer`, `emit`, `output` hoặc một tên mô tả rõ ý nghĩa:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2);

List<Integer> result = numbers.stream()
    .<Integer>mapMulti((number, consumer) -> {
        consumer.accept(number);
    })
    .toList();
```

Lệnh `consumer.accept(number)` gửi giá trị `number` xuống pipeline. Mapper không cần tạo danh sách kết quả và cũng không cần trả về giá trị. Stream nhận từng giá trị được phát và chuyển nó đến thao tác tiếp theo.

Mỗi lần gọi `accept` tương ứng với một phần tử đầu ra:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2);

List<Integer> result = numbers.stream()
    .<Integer>mapMulti((number, consumer) -> {
        consumer.accept(number);
        consumer.accept(number * 10);
    })
    .toList();
```

Nếu nguồn là `[1, 2]`, kết quả là `[1, 10, 2, 20]`. Mapper đã gọi `accept` hai lần cho mỗi phần tử nguồn, nên mỗi phần tử đóng góp hai kết quả.

## 2. Không gọi accept để loại phần tử

Nếu mapper kết thúc mà không gọi Consumer, phần tử nguồn hiện tại không tạo ra phần tử đầu ra. Đây là cách loại phần tử trong `mapMulti`.

Ví dụ, chỉ phát các số dương:

```java
import java.util.List;

List<Integer> numbers = List.of(-3, 0, 4, 8, -1);

List<Integer> positives = numbers.stream()
    .<Integer>mapMulti((number, consumer) -> {
        if (number > 0) {
            consumer.accept(number);
        }
    })
    .toList();
```

Kết quả:

```text
[4, 8]
```

Với `-3`, `0` và `-1`, điều kiện không đúng nên mapper không gọi `accept`. Những phần tử này không xuất hiện trong Stream kết quả.

Tuy nhiên, nếu yêu cầu chỉ là giữ các phần tử thỏa điều kiện mà không chuyển đổi hay phát thêm dữ liệu, `filter` thường thể hiện ý định rõ hơn:

```java
List<Integer> positives = numbers.stream()
    .filter(number -> number > 0)
    .toList();
```

Hãy dùng ví dụ `mapMulti` để hiểu cơ chế không phát kết quả; trong mã ứng dụng, ưu tiên `filter` cho thao tác lọc đơn giản.

## 3. Dùng return để kết thúc lần xử lý hiện tại

Trong lambda mapper, có thể dùng `return` để kết thúc sớm việc xử lý phần tử nguồn hiện tại. Vì mapper có kiểu trả về `void`, `return` không mang theo giá trị:

```java
import java.util.List;

record Product(String sku, int quantity, boolean discontinued) {}

List<Product> products = List.of(
    new Product("BOOK-01", 4, false),
    new Product("PEN-02", 0, false),
    new Product("BAG-03", 2, true),
    new Product("NOTE-04", 3, false)
);

List<String> availableSkus = products.stream()
    .<String>mapMulti((product, consumer) -> {
        if (product.discontinued()) {
            return;
        }

        if (product.quantity() <= 0) {
            return;
        }

        consumer.accept(product.sku());
    })
    .toList();
```

Kết quả:

```text
[BOOK-01, NOTE-04]
```

Hai lệnh `return` chỉ kết thúc lần gọi mapper của sản phẩm hiện tại. Chúng không dừng toàn bộ Stream. Các sản phẩm tiếp theo vẫn được xử lý khi pipeline tiêu thụ dữ liệu.

Có thể viết cùng quy tắc bằng một điều kiện kết hợp:

```java
List<String> availableSkus = products.stream()
    .<String>mapMulti((product, consumer) -> {
        if (!product.discontinued() && product.quantity() > 0) {
            consumer.accept(product.sku());
        }
    })
    .toList();
```

Cả hai cách đều hợp lệ. Dùng `return` sớm khi nó giúp giảm độ lồng nhau và làm phần xử lý chính dễ đọc hơn.

## 4. Một phần tử nguồn có thể phát nhiều kết quả

Một phần tử nguồn có thể chứa nhiều giá trị con. Mapper duyệt các giá trị đó và gọi `accept` cho từng giá trị thỏa điều kiện.

Ví dụ, mỗi bài viết có nhiều thẻ. Ta muốn lấy các thẻ không rỗng từ tất cả bài viết:

```java
import java.util.List;

record Article(String title, List<String> tags) {}

List<Article> articles = List.of(
    new Article("Java Streams", List.of("java", "streams", "backend")),
    new Article("Records", List.of("java", "", "language")),
    new Article("Platform", List.of())
);

List<String> tags = articles.stream()
    .<String>mapMulti((article, consumer) -> {
        for (String tag : article.tags()) {
            if (tag != null && !tag.isBlank()) {
                consumer.accept(tag);
            }
        }
    })
    .toList();
```

Kết quả:

```text
[java, streams, backend, java, language]
```

Bài viết đầu tiên phát ba phần tử, bài viết thứ hai phát hai phần tử và bài viết cuối cùng không phát phần tử nào. Thẻ rỗng cũng bị bỏ qua vì mapper không gọi `accept` cho thẻ đó.

Ví dụ này thể hiện rõ lợi ích của `mapMulti`: việc duyệt danh sách con và phát từng giá trị được thực hiện trực tiếp trong mapper, không cần tạo một Stream mới cho mỗi bài viết.

## 5. Có thể phát kết quả theo nhiều nhánh điều kiện

Một phần tử nguồn có thể tạo ra các loại kết quả khác nhau tùy theo điều kiện. Mỗi nhánh gọi `accept` khi cần phát giá trị:

```java
import java.util.List;

record Payment(String id, long amount, boolean refunded) {}

List<Payment> payments = List.of(
    new Payment("P-100", 250_000, false),
    new Payment("P-101", 80_000, true),
    new Payment("P-102", 1_500_000, false)
);

List<String> notices = payments.stream()
    .<String>mapMulti((payment, consumer) -> {
        if (payment.refunded()) {
            consumer.accept(payment.id() + ": refunded");
            return;
        }

        if (payment.amount() >= 1_000_000) {
            consumer.accept(payment.id() + ": high value");
            consumer.accept(payment.id() + ": review required");
        } else {
            consumer.accept(payment.id() + ": normal");
        }
    })
    .toList();
```

Kết quả:

```text
[
  P-100: normal,
  P-101: refunded,
  P-102: high value,
  P-102: review required
]
```

Thanh toán đã hoàn tiền phát một thông báo rồi kết thúc lần xử lý hiện tại. Thanh toán giá trị cao phát hai thông báo. Thanh toán thông thường phát một thông báo.

Khi một nhánh cần phát nhiều giá trị, chỉ cần gọi `accept` nhiều lần. Không cần gộp các giá trị thành một collection trước khi gửi xuống pipeline.

## 6. Không phát và phát null là hai việc khác nhau

Không gọi `accept` nghĩa là không có phần tử đầu ra từ nhánh đó. Gọi `accept(null)` lại là gửi một giá trị null xuống pipeline:

```java
consumer.accept(null); // Có phát một phần tử, giá trị của nó là null.
return;                // Không phát thêm phần tử nào trong lần mapper này.
```

Không nên dùng `null` như tín hiệu thay thế cho việc không phát dữ liệu. Nếu một giá trị không hợp lệ hoặc không có kết quả, hãy bỏ qua lời gọi `accept`. Giá trị null có thể khiến các thao tác phía sau như gọi phương thức trên phần tử hoặc sắp xếp theo comparator không xử lý null bị lỗi.

Ví dụ kiểm tra trước khi phát:

```java
import java.util.Arrays;
import java.util.List;

List<String> sourceNames = Arrays.asList(" Ana ", "", null, "Binh ");

List<String> names = sourceNames.stream()
    .<String>mapMulti((name, consumer) -> {
        if (name != null && !name.isBlank()) {
            consumer.accept(name.trim());
        }
    })
    .toList();
```

Chỉ tên hợp lệ mới được phát. Các giá trị null hoặc chuỗi trống không tạo phần tử trong kết quả.

## 7. Thứ tự và phần tử trùng lặp

Trong Stream có encounter order, các lần gọi `accept` trong một mapper phát kết quả theo đúng thứ tự được gọi. Thứ tự xử lý phần tử nguồn cũng được pipeline có thứ tự duy trì ở các thao tác đầu ra có bảo toàn encounter order.

Ví dụ:

```java
import java.util.List;

List<String> result = List.of("A", "B").stream()
    .<String>mapMulti((value, consumer) -> {
        consumer.accept(value + "1");
        consumer.accept(value + "2");
    })
    .toList();
```

Kết quả là:

```text
[A1, A2, B1, B2]
```

`mapMulti` không tự loại bỏ phần tử trùng lặp. Nếu nhiều lần gọi `accept` gửi cùng một giá trị, các lần phát đó vẫn tạo ra các phần tử riêng:

```java
import java.util.List;

List<String> values = List.of("java", "java").stream()
    .<String>mapMulti((value, consumer) -> {
        consumer.accept(value);
        consumer.accept(value);
    })
    .toList();
```

Kết quả là `[java, java, java, java]`. Nếu muốn loại trùng, hãy thêm `distinct()` vào pipeline:

```java
import java.util.List;

List<String> uniqueValues = List.of("java", "java").stream()
    .<String>mapMulti((value, consumer) -> {
        consumer.accept(value);
        consumer.accept(value);
    })
    .distinct()
    .toList();
```

## 8. Kết hợp việc phát dữ liệu với các thao tác tiếp theo

Các phần tử được phát qua `accept` tiếp tục đi qua pipeline như những phần tử Stream bình thường. Có thể lọc, chuyển đổi, loại trùng hoặc thu thập chúng ở các bước tiếp theo:

```java
List<String> normalizedTags = articles.stream()
    .<String>mapMulti((article, consumer) -> {
        for (String tag : article.tags()) {
            if (tag != null && !tag.isBlank()) {
                consumer.accept(tag);
            }
        }
    })
    .map(String::toLowerCase)
    .distinct()
    .sorted()
    .toList();
```

Các bước có trách nhiệm riêng:

1. `mapMulti` duyệt thẻ và phát thẻ hợp lệ.
2. `map` chuẩn hóa chữ thường.
3. `distinct` loại các giá trị trùng.
4. `sorted` sắp xếp kết quả.
5. `toList` tiêu thụ pipeline và tạo danh sách.

Cách chia thành các thao tác nhỏ giúp quy tắc phát dữ liệu không bị trộn lẫn với quy tắc chuẩn hóa, loại trùng hoặc sắp xếp.

## 9. So sánh không phát với filter và flatMap

Các thao tác sau có thể cho kết quả tương tự trong một số trường hợp, nhưng cách diễn đạt khác nhau:

| Nhu cầu | Thao tác phù hợp |
|---|---|
| Chỉ giữ hoặc loại phần tử hiện tại | `filter` |
| Chuyển mỗi phần tử thành đúng một giá trị | `map` |
| Phát không, một hoặc nhiều giá trị qua Consumer | `mapMulti` |
| Chuyển mỗi phần tử thành một Stream rồi làm phẳng | `flatMap` |

Ví dụ lọc số dương:

```java
import java.util.List;

List<Integer> numbers = List.of(-3, 0, 4, 8, -1);

numbers.stream()
    .filter(number -> number > 0);
```

Ví dụ dùng `mapMulti` để phát các số dương:

```java
import java.util.List;

List<Integer> numbers = List.of(-3, 0, 4, 8, -1);

numbers.stream()
    .<Integer>mapMulti((number, consumer) -> {
        if (number > 0) {
            consumer.accept(number);
        }
    });
```

Hai pipeline cho kết quả tương đương, nhưng `filter` ngắn và mô tả đúng ý định lọc hơn. `mapMulti` có giá trị khi mỗi phần tử nguồn cần thực hiện một logic phát kết quả phức tạp hơn, chẳng hạn duyệt danh sách con hoặc có nhiều nhánh phát.

Với dữ liệu con đã có dưới dạng Stream, `flatMap` có thể diễn đạt tự nhiên:

```java
List<String> allTags = articles.stream()
    .flatMap(article -> article.tags().stream())
    .toList();
```

Nếu cần lọc thẻ null hoặc rỗng trong quá trình duyệt, có thể dùng `mapMulti` để kiểm tra và phát trực tiếp. Hãy chọn cách viết dễ đọc nhất cho cấu trúc dữ liệu và quy tắc nghiệp vụ cụ thể.

## 10. Đặc tính lazy và xử lý song song

`mapMulti` là thao tác trung gian. Mapper chỉ chạy khi terminal operation tiêu thụ pipeline, ví dụ `toList()`, `count()` hoặc `findFirst()`. Nếu terminal operation có thể dừng sớm, pipeline có thể không xử lý mọi phần tử nguồn.

Trong parallel Stream, mapper của các phần tử nguồn khác nhau có thể chạy đồng thời. Vì vậy, không nên dùng một collection mutable dùng chung để lưu kết quả từ mapper. Hãy phát kết quả qua Consumer và để pipeline thực hiện các bước xử lý, thu thập phù hợp.

Không giữ Consumer để gọi sau khi mapper kết thúc hoặc chuyển nó sang tác vụ bất đồng bộ. Hãy gọi `accept` ngay trong lần thực thi mapper tương ứng.

## 11. Lỗi thường gặp

**Nghĩ rằng không gọi accept là lỗi.** Không gọi Consumer là cách hợp lệ để một phần tử nguồn tạo ra không phần tử đầu ra.

**Gọi accept với null để biểu thị không có kết quả.** Đây vẫn là một lần phát phần tử. Nếu muốn loại dữ liệu, hãy bỏ qua lời gọi `accept`.

**Dùng return với ý nghĩa dừng toàn bộ Stream.** `return` trong mapper chỉ kết thúc lần xử lý phần tử nguồn hiện tại. Pipeline vẫn tiếp tục với dữ liệu còn lại nếu terminal operation cần.

**Quên rằng mỗi lần accept tạo một phần tử.** Nếu gọi `accept` trong vòng lặp, số phần tử đầu ra phụ thuộc số lần vòng lặp chạy và điều kiện bên trong.

**Dùng mapMulti cho thao tác lọc đơn giản.** Khi chỉ cần giữ hoặc bỏ phần tử hiện tại, `filter` dễ đọc và thể hiện ý định tốt hơn.

**Tự thêm kết quả vào collection bên ngoài.** Hãy dùng Consumer để phát kết quả và các collector hoặc terminal operation để thu thập dữ liệu.

## 12. Ghi nhớ

- Gọi `consumer.accept(value)` để phát một phần tử đầu ra.
- Gọi `accept` nhiều lần để phát nhiều phần tử.
- Không gọi `accept` để phần tử nguồn không tạo kết quả.
- Dùng `return` để kết thúc sớm lần gọi mapper hiện tại khi cần.
- Không dùng `accept(null)` thay cho việc không phát dữ liệu.
- Ưu tiên `filter` khi chỉ cần lọc; chọn `mapMulti` khi cần phát không, một hoặc nhiều giá trị bằng logic xử lý trực tiếp.

Khi nắm rõ mối quan hệ giữa số lần gọi `accept` và số phần tử đầu ra, ta có thể kiểm soát chính xác dữ liệu được đưa vào các bước tiếp theo của Stream pipeline.

