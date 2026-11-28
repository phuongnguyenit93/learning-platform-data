# External snippet với file: tách ví dụ khỏi comment tài liệu

## 1. Mục tiêu và bối cảnh

JEP 413 đưa thẻ `{@snippet ...}` vào Javadoc từ **JDK 18**. Tính năng này vẫn được hỗ trợ trên JDK hiện đại, giúp tài liệu API trình bày ví dụ mã rõ ràng, có thể chọn vùng và tái sử dụng. Khi nội dung dài, có cú pháp khó đặt trong comment hoặc cần được biên dịch/chạy như mã nguồn thật, **external snippet** là lựa chọn phù hợp.

External snippet lấy nội dung từ một tệp riêng hoặc từ một lớp Java. Trong comment Javadoc, tác giả khai báo nguồn bằng thuộc tính `file` hoặc `class`. Nhờ vậy, comment mô tả API không phải chứa toàn bộ mã minh họa.

Sau bài học, bạn có thể:

- Giải thích external snippet và phân biệt với inline/hybrid snippet.
- Tổ chức tệp trong thư mục `snippet-files` theo package chứa Javadoc.
- Dùng `--snippet-path` khi muốn lưu ví dụ ở một thư mục riêng.
- Chọn `file` cho tệp văn bản có cấu trúc và `class` cho nguồn Java.
- Trích một phần tệp bằng `region` và markup comment.
- Biên dịch/chạy ví dụ external riêng với việc tạo tài liệu Javadoc.

Bài này nằm trong chương **Javadoc snippet** của module `JAVA_VERSION_JAVA18`. Mục tiêu của chương là hiểu các tính năng Java 18 vẫn hữu ích trên JDK hiện đại, trong đó có cách viết ví dụ API có thể kiểm chứng. External snippet là một phần của JEP 413, không phải API runtime mới.

## 2. External snippet là gì?

Một external snippet là nội dung của thẻ `{@snippet ...}` được lấy từ **một tệp hoặc một lớp Java riêng**. Trong comment tài liệu, thẻ chỉ tham chiếu đến nguồn:

~~~java
/**
 * Ví dụ sử dụng:
 *
 * {@snippet file="OrderExamples.java"}
 */
public class OrderService {
}
~~~

Không có dấu hai chấm, dòng mới mở đầu phần thân hoặc nội dung mã inline trong thẻ. Standard Doclet tìm tệp được chỉ định, đọc nội dung và tạo khối mã trong trang HTML.

External snippet có các đặc điểm:

- Nội dung được lưu độc lập với comment Javadoc.
- Có thể chứa nhiều dòng, block comment `/* ... */`, string literal hoặc ký tự mà inline snippet không thể biểu diễn an toàn trong traditional comment.
- Một tệp có thể chứa nhiều vùng, mỗi vùng được tham chiếu bởi một thẻ snippet khác nhau.
- Có thể chứa Java source hoặc dạng văn bản có cấu trúc khác như Properties, JSON, XML hay HTML.
- Có thể được biên dịch và chạy riêng nếu tệp chứa mã nguồn thực thi phù hợp.

Standard Doclet không biên dịch hoặc chạy snippet khi tạo Javadoc. Việc tách mã ra tệp ngoài giúp các công cụ build và test thông thường có thể kiểm tra ví dụ dễ hơn.

## 3. Vì sao nên tách ví dụ khỏi comment tài liệu?

Inline snippet tiện cho đoạn mã ngắn, nhưng có những giới hạn do nội dung nằm bên trong comment `/** ... */`:

- Không thể chứa chuỗi `*/` vì cặp ký tự này kết thúc comment bên ngoài.
- Unicode escape trong mã nguồn được xử lý trước khi Javadoc đọc comment.
- Dấu ngoặc nhọn trong nội dung inline phải cân bằng và lồng đúng thứ tự.

Những giới hạn này gây khó khăn khi ví dụ cần:

- Block comment Java.
- Regex hoặc glob chứa chuỗi `*/`.
- String literal, text block hoặc dữ liệu JSON có dấu ngoặc phức tạp.
- Một lớp Java hoàn chỉnh có import, constructor, main và nhiều phương thức.
- Nhiều vùng mã cần tái sử dụng ở các phần khác nhau của tài liệu.

External snippet lấy nội dung từ tệp nằm ngoài comment bao quanh, nên không bị các giới hạn cú pháp inline nói trên. Ví dụ sau có thể đặt nguyên vẹn trong tệp riêng:

~~~java
String glob = "reports/*.csv";
String regex = "a.*/b";

/* Một block comment trong ví dụ. */
System.out.println(regex);
~~~

Trong inline snippet nằm trong traditional documentation comment, cặp `*/` sẽ đóng comment. Với external snippet, Javadoc đọc nội dung từ tệp riêng nên có thể trình bày nguyên vẹn các dòng đó.

## 4. Tổ chức thư mục snippet-files

Cách đơn giản nhất là đặt thư mục `snippet-files` bên cạnh mã nguồn package chứa comment có thẻ snippet.

Ví dụ cấu trúc:

~~~text
src/
└── example/
    ├── OrderService.java
    └── snippet-files/
        ├── OrderExamples.java
        ├── OrderProperties.properties
        └── samples/
            └── response.json
~~~

Trong cấu trúc này:

- `OrderService.java` chứa Javadoc có thẻ `{@snippet ...}`.
- `snippet-files/` là thư mục chứa nguồn snippet cho package đó.
- `OrderExamples.java` là ví dụ Java.
- `OrderProperties.properties` là ví dụ cấu hình.
- `samples/response.json` là tệp JSON nằm trong thư mục con của nguồn snippet.

Standard Doclet tự tìm thư mục `snippet-files` theo package chứa thẻ. Với cấu trúc cục bộ như trên, thường **không cần** truyền thêm tùy chọn tìm kiếm khi chạy Javadoc.

### Ví dụ comment tham chiếu tệp

Trong `src/example/OrderService.java`:

~~~java
package example;

/**
 * Các ví dụ liên quan đến đơn hàng:
 *
 * {@snippet file="OrderExamples.java"}
 *
 * Cấu hình mặc định:
 *
 * {@snippet file="OrderProperties.properties"}
 *
 * Phản hồi API:
 *
 * {@snippet file="samples/response.json"}
 */
public class OrderService {
}
~~~

Đường dẫn trong thuộc tính `file` là đường dẫn tương đối từ thư mục snippet root tương ứng. Vì vậy:

- `OrderExamples.java` trỏ đến `snippet-files/OrderExamples.java`.
- `OrderProperties.properties` trỏ đến `snippet-files/OrderProperties.properties`.
- `samples/response.json` trỏ đến `snippet-files/samples/response.json`.

Không cần đưa tiền tố `snippet-files/` vào giá trị `file` khi dùng thư mục cục bộ theo package. Hãy dùng đường dẫn tương đối ngắn từ thư mục gốc snippet.

### Lưu ý với hệ thống build

Một số hệ thống build có thể hiểu nhầm thư mục `snippet-files` là một phần của package hierarchy hoặc đưa tệp trong đó vào tập nguồn Java chính. Đây là thư mục phụ dành cho nội dung snippet, không phải một package Java. Nếu công cụ build không xử lý đúng cấu trúc này, hãy chuyển các tệp snippet sang một thư mục riêng và cấu hình `--snippet-path`.

## 5. Dùng --snippet-path cho thư mục ngoài package

Khi muốn lưu ví dụ ở một vị trí riêng, không nằm trong package source, có thể truyền đường dẫn gốc bằng tùy chọn `--snippet-path` của lệnh `javadoc`.

Ví dụ cấu trúc:

~~~text
project/
├── src/
│   └── example/
│       └── OrderService.java
└── snippets/
    ├── OrderExamples.java
    ├── OrderProperties.properties
    └── samples/
        └── response.json
~~~

Trong Javadoc, vẫn tham chiếu bằng đường dẫn tương đối từ thư mục được cấu hình:

~~~java
/**
 * Ví dụ tạo đơn hàng:
 *
 * {@snippet file="OrderExamples.java" region=create-order}
 *
 * Cấu hình:
 *
 * {@snippet file="OrderProperties.properties" region=server}
 */
public class OrderService {
}
~~~

Chạy Javadoc từ thư mục gốc dự án:

~~~sh
javadoc --snippet-path snippets -d build/docs -sourcepath src example
~~~

Tùy chọn `--snippet-path snippets` cho Standard Doclet biết nơi tìm các tệp external. Giá trị `file` vẫn là đường dẫn tương đối bên trong thư mục gốc đó.

Có thể chỉ định nhiều đường dẫn snippet theo cú pháp tùy chọn của Javadoc, phân cách bằng dấu phân tách đường dẫn của hệ điều hành. Trên Windows, dấu phân tách thường là dấu chấm phẩy; trên Linux/macOS thường là dấu hai chấm. Khi cấu hình build đa nền tảng, nên để build tool xử lý danh sách đường dẫn thay vì hard-code dấu phân cách.

**Không nên dùng đường dẫn tuyệt đối gắn với máy cá nhân** trong thuộc tính `file`. Đường dẫn tương đối trong `snippet-files` hoặc `--snippet-path` giúp tài liệu có thể được sinh lại trên máy khác và trong CI.

## 6. Chọn file hay class?

Có hai cách chỉ định nguồn external:

| Thuộc tính | Nguồn | Khi nào dùng |
| --- | --- | --- |
| `file` | Tệp theo đường dẫn tương đối | Dùng cho Java source hoặc tệp văn bản có cấu trúc như Properties, JSON, XML, HTML. |
| `class` | Tên lớp Java | Dùng khi nguồn snippet là một tệp Java được xác định qua tên lớp. |

### Dùng file

`file` phù hợp khi bạn muốn chỉ rõ tên tệp và có thể dùng cho cả Java source lẫn dữ liệu không phải Java:

~~~java
/**
 * Ví dụ Java:
 *
 * {@snippet file="OrderExamples.java"}
 *
 * Cấu hình:
 *
 * {@snippet file="OrderProperties.properties"}
 */
~~~

Với tệp không phải Java, `file` là cách chỉ định nguồn cần dùng. Javadoc trình bày nội dung có cấu trúc trong khối mã HTML; nó không phân tích hay thực thi ngữ nghĩa của định dạng đó.

### Dùng class cho Java source

Nếu tệp ngoài là mã Java, có thể tham chiếu bằng tên lớp:

~~~java
/**
 * Ví dụ tạo đơn hàng:
 *
 * {@snippet class=OrderExamples}
 */
~~~

Standard Doclet dùng tên lớp để xác định tệp Java trong hệ thống thư mục snippet. Ví dụ trong hướng dẫn chính thức là `{@snippet class=HelloWorld}`, tham chiếu nguồn `snippet-files/HelloWorld.java` đặt dưới thư mục package chứa comment có thẻ snippet. Dùng tên lớp đơn giản làm giá trị `class`; nếu muốn chỉ rõ đường dẫn tệp hoặc nguồn không phải Java, dùng `file`.

Không dùng `class` cho tệp JSON, Properties hoặc văn bản thuần; các định dạng đó không phải lớp Java. Dùng `file` cho chúng.

## 7. Trích một phần tệp bằng region

Nếu external file chứa nhiều ví dụ, không nhất thiết phải hiển thị toàn bộ tệp. Có thể đánh dấu từng vùng bằng markup comment `@start` và `@end` rồi chọn vùng bằng thuộc tính `region`.

Tệp `snippet-files/OrderExamples.java`:

~~~java
package example;

public final class OrderExamples {
    private OrderExamples() {
    }

    public static void main(String[] args) {
        // @start region=create-order
        String id = OrderService.createOrder("customer-42");
        if (!"order:customer-42".equals(id)) {
            throw new AssertionError(id);
        }
        // @end region=create-order

        // @start region=cancel-order
        OrderService.cancelOrder("order-42");
        // @end region=cancel-order
    }
}
~~~

Tham chiếu riêng từng vùng trong Javadoc:

~~~java
/**
 * Tạo đơn hàng:
 *
 * {@snippet file="OrderExamples.java" region=create-order}
 *
 * Hủy đơn hàng:
 *
 * {@snippet file="OrderExamples.java" region=cancel-order}
 */
~~~

Kết quả:

- Snippet thứ nhất chỉ hiển thị phần nằm trong vùng `create-order`.
- Snippet thứ hai chỉ hiển thị phần nằm trong vùng `cancel-order`.
- Các dòng `@start` và `@end` là markup comment nên không xuất hiện trong mã được hiển thị.

Một external file có thể chứa nhiều vùng để các phần tài liệu khác nhau tham chiếu lại. Tên vùng cần thống nhất giữa comment markup và thuộc tính `region`.

### Vùng lồng nhau và vùng chồng lấp

Các region có thể lồng nhau. Với vùng lồng nhau, có thể đặt tên hoặc không đặt tên tùy nhu cầu. Nếu các vùng chồng lấp nhưng không lồng nhau, cần dùng tên để xác định cặp bắt đầu/kết thúc tương ứng.

Khi tài liệu có nhiều snippet lấy từ cùng một tệp, hãy dùng tên region mô tả mục đích như `create-order`, `validate-customer` hoặc `serialize-response`. Tránh tên chung chung như `part1`, `part2` nếu tài liệu được duy trì lâu dài.

## 8. Markup comment trong external file

Markup comment điều khiển cách Javadoc trình bày snippet. Chúng có thể làm nổi bật một phần văn bản, tạo liên kết đến API hoặc thay thế một đoạn hiển thị. Các comment markup được loại bỏ khỏi kết quả HTML.

Ví dụ trong tệp Java:

~~~java
// @start region=create-order
String id = OrderService.createOrder("customer-42"); // @highlight substring="createOrder"
System.out.println(id);
// @end region=create-order
~~~

Thẻ tham chiếu:

~~~java
{@snippet file="OrderExamples.java" region=create-order}
~~~

Markup comment có thể nằm cuối dòng mã hoặc ở một dòng riêng. Nếu comment kết thúc bằng dấu hai chấm, chỉ thị được áp dụng cho dòng ngay sau đó:

~~~java
// @highlight substring="createOrder" :
String id = OrderService.createOrder("customer-42");
~~~

Với Java, markup thường dùng comment dòng `//`. Với tệp Properties, comment markup phải bắt đầu bằng `#` ở đầu dòng sau khoảng trắng. Không giả định cú pháp comment của một ngôn ngữ có thể dùng cho định dạng khác.

### Markup không phải nội dung chương trình

Markup comment được viết để Standard Doclet xử lý. Nó không xuất hiện trong snippet cuối cùng. Vì vậy, nếu một comment có ý nghĩa thực sự với người đọc hoặc là một phần của ví dụ, hãy dùng comment bình thường không bắt đầu bằng một tên markup được nhận diện hoặc viết lời giải thích bên ngoài snippet.

Đừng nhầm markup comment với comment mã nguồn thông thường. Markup có tên được Standard Doclet nhận diện sẽ bị xử lý; comment không được nhận diện như markup sẽ có thể xuất hiện nguyên văn trong kết quả.

## 9. Ví dụ thực tế hoàn chỉnh: API đơn hàng

Giả sử API có hai thao tác tạo và hủy đơn hàng. Tệp `src/example/OrderService.java`:

~~~java
package example;

/**
 * API thao tác đơn hàng.
 *
 * <p>Ví dụ tạo đơn hàng:
 *
 * {@snippet file="OrderExamples.java" region=create-order}
 */
public final class OrderService {
    private OrderService() {
    }

    /**
     * Tạo mã đơn hàng cho khách hàng.
     *
     * @param customerId mã khách hàng không được null hoặc trống
     * @return mã đơn hàng có dạng order:customerId
     * @throws IllegalArgumentException nếu customerId null hoặc trống
     */
    public static String createOrder(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId must not be blank");
        }
        return "order:" + customerId;
    }

    /** Hủy đơn hàng theo mã. */
    public static void cancelOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
    }
}
~~~

Tệp `src/example/snippet-files/OrderExamples.java`:

~~~java
package example;

public final class OrderExamples {
    private OrderExamples() {
    }

    public static void main(String[] args) {
        // @start region=create-order
        String id = OrderService.createOrder("customer-42");
        if (!"order:customer-42".equals(id)) {
            throw new AssertionError(id);
        }
        // @end region=create-order

        // @start region=cancel-order
        OrderService.cancelOrder("order:customer-42");
        // @end region=cancel-order
    }
}
~~~

Từ thư mục gốc dự án, tạo Javadoc:

~~~sh
javadoc -d build/docs -sourcepath src example
~~~

Vì tệp nằm trong `src/example/snippet-files`, Standard Doclet tìm thấy nó theo cấu trúc package và không cần `--snippet-path`.

Biên dịch cả API và lớp ví dụ:

~~~sh
javac -d build/classes src/example/OrderService.java src/example/snippet-files/OrderExamples.java
~~~

Chạy ví dụ:

~~~sh
java -cp build/classes example.OrderExamples
~~~

Chương trình kết thúc bình thường nếu kết quả tạo đơn hàng đúng và thao tác hủy không phát sinh lỗi. Đây là kiểm chứng riêng đối với mã ví dụ. Lệnh `javadoc` chỉ tạo trang tài liệu; nó không thay thế bước biên dịch hoặc chạy.

### Kiểm tra nội dung HTML

Sau khi tạo tài liệu, mở trang `OrderService.html` và xác nhận:

- Phần ví dụ tạo đơn hàng hiển thị đúng vùng `create-order`.
- Các comment `@start` và `@end` không xuất hiện.
- Mã có thụt lề và xuống dòng đúng.
- Nút sao chép snippet sao chép đúng nội dung.
- Khi sửa tệp external, chạy lại Javadoc để cập nhật trang HTML.

## 10. Khi nào dùng external, inline hoặc hybrid?

| Dạng | Đặc điểm | Nên dùng khi |
| --- | --- | --- |
| Inline | Nội dung nằm trực tiếp trong comment Javadoc. | Ví dụ ngắn, dễ đọc ngay cạnh mô tả API. |
| External | Nội dung nằm trong tệp/lớp riêng, thẻ chỉ tham chiếu nguồn. | Ví dụ dài, nhiều vùng, có block comment hoặc cần biên dịch/chạy riêng. |
| Hybrid | Vừa có nội dung inline vừa tham chiếu tệp ngoài. | Muốn người đọc source thấy mã tại chỗ, đồng thời đối chiếu với tệp ví dụ. |

Hybrid snippet yêu cầu kết quả xử lý nội dung inline và external phải khớp nhau; nếu khác, Standard Doclet báo lỗi. Vì vậy, thường nên phát triển ví dụ dưới dạng inline hoặc external trước, rồi chỉ chuyển thành hybrid khi nội dung đã ổn định.

Với phần lớn ví dụ dài có thể chạy được, external snippet là lựa chọn dễ kiểm thử và bảo trì. Không cần dùng hybrid nếu việc duy trì hai bản nội dung không mang lại lợi ích rõ ràng.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Javadoc không tìm thấy tệp. | Sai tên hoặc đặt tệp ngoài `snippet-files` mà chưa cấu hình `--snippet-path`. | Kiểm tra đường dẫn tương đối và thư mục gốc tìm kiếm. |
| Tham chiếu sai vùng. | Tên `region` trong thẻ khác với tên `@start`/`@end`. | Đối chiếu chính xác tên vùng và cặp mở/đóng. |
| Toàn bộ tệp xuất hiện thay vì phần mong muốn. | Thiếu thuộc tính `region`. | Khai báo region tương ứng trong thẻ snippet. |
| Tệp Properties hiển thị comment markup. | Dùng comment cuối dòng kiểu Java thay vì comment `#` ở đầu dòng. | Dùng cú pháp markup comment phù hợp với Properties. |
| Ví dụ external hiển thị nhưng không biên dịch. | Javadoc chỉ đọc và trình bày tệp; chưa chạy compiler. | Biên dịch và chạy riêng tệp Java. |
| Build tool coi `snippet-files` là package. | Công cụ build quét thư mục snippet như source package thông thường. | Dùng thư mục snippet riêng và cấu hình `--snippet-path`. |
| Đường dẫn hoạt động trên một máy nhưng lỗi trên máy khác. | Dùng đường dẫn tuyệt đối hoặc cấu trúc thư mục cục bộ. | Dùng đường dẫn tương đối và đưa nguồn snippet vào repository. |
| Hybrid snippet báo lỗi không khớp. | Nội dung inline và kết quả xử lý external khác nhau. | Đồng bộ hai bản hoặc tiếp tục dùng external thuần. |

## 12. Quy trình xây dựng external snippet có thể kiểm chứng

1. **Xác định mục tiêu ví dụ:** mô tả API, cấu hình hay dữ liệu cần trình bày.
2. **Chọn nguồn:** Java source có thể dùng `class` hoặc `file`; dữ liệu có cấu trúc dùng `file`.
3. **Đặt tệp đúng chỗ:** dùng `snippet-files` trong package hoặc thư mục riêng với `--snippet-path`.
4. **Tách vùng cần hiển thị:** dùng `@start region=name` và `@end region=name` nếu tệp chứa nhiều ví dụ.
5. **Thêm markup cần thiết:** highlight, link hoặc replace bằng comment phù hợp ngôn ngữ.
6. **Tham chiếu từ Javadoc:** khai báo `file` hoặc `class` và `region` khi cần.
7. **Tạo tài liệu:** chạy Javadoc trên JDK mục tiêu, kiểm tra lỗi đường dẫn và vùng.
8. **Biên dịch/chạy ví dụ:** dùng `javac` và `java` hoặc parser phù hợp với loại tệp.
9. **Đồng bộ khi API thay đổi:** cập nhật hợp đồng, nguồn snippet và kiểm thử cùng một thay đổi.

## 13. Bài tập thực hành

### Bài tập 1: Tạo external snippet từ Java source

Tạo package `example` có lớp `OrderService` và thư mục `snippet-files`. Đặt một lớp `OrderExamples.java` trong đó, đánh dấu vùng `create-order` và tham chiếu bằng:

~~~java
{@snippet file="OrderExamples.java" region=create-order}
~~~

Tạo Javadoc và xác nhận chỉ phần vùng được chọn xuất hiện.

### Bài tập 2: Dùng --snippet-path

Di chuyển tệp ví dụ sang thư mục `snippets` ở ngoài source package. Chạy Javadoc với `--snippet-path snippets`. Giữ nguyên đường dẫn tương đối trong thuộc tính `file` và kiểm tra tài liệu vẫn tìm thấy nguồn.

### Bài tập 3: So sánh file và class

Với tệp Java `OrderExamples.java`, viết hai cách tham chiếu: `file="OrderExamples.java"` và `class=OrderExamples`. Với tệp `application.properties`, dùng `file`. Giải thích vì sao `class` chỉ phù hợp với nguồn Java.

### Bài tập 4: Kiểm chứng hành vi

Trong vùng `create-order`, gọi API và kiểm tra kết quả bằng `if` cùng `AssertionError`. Cố ý thay đổi chuỗi kỳ vọng để chương trình thất bại. Quan sát rằng Javadoc vẫn có thể tạo tài liệu trong khi bước chạy ví dụ phát hiện sai lệch.

### Bài tập 5: Trình bày ký tự đặc biệt

Đưa một block comment và một string literal chứa `*/` vào tệp external. Tham chiếu tệp bằng `file`. Giải thích vì sao nội dung này không thể đặt trực tiếp trong inline snippet của traditional documentation comment.

**Tự kiểm:** tệp nằm đúng thư mục; đường dẫn tương đối hợp lệ; region khớp; markup comment bị loại khỏi output; ví dụ được biên dịch/chạy riêng; tài liệu và hành vi API không mâu thuẫn.

## 14. Ghi nhớ

- **External snippet lấy mã từ tệp hoặc lớp Java riêng.** Thẻ Javadoc chỉ cần tham chiếu bằng `file` hoặc `class`.
- **`snippet-files` là vị trí mặc định theo package.** Dùng `--snippet-path` khi nguồn snippet nằm ở thư mục riêng.
- **`file` dùng cho tệp văn bản có cấu trúc; `class` dùng cho nguồn Java.** Chọn thuộc tính theo loại nguồn.
- **`region` cho phép tái sử dụng một tệp cho nhiều ví dụ.** Các vùng được đánh dấu bằng `@start` và `@end`.
- **External snippet có thể chứa nội dung không thể nhúng inline**, như block comment hoặc chuỗi `*/`.
- **Javadoc không kiểm thử snippet.** Hãy biên dịch, chạy hoặc xác thực nguồn riêng bằng công cụ phù hợp.
- **Giữ đường dẫn tương đối và cấu trúc nguồn trong repository** để tài liệu có thể sinh lại trên máy khác và trong CI.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle – JDK 26 Javadoc Snippets Guide, mục External Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, External snippets](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle – JDK 26 The javadoc Command, tùy chọn --snippet-path](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html).

