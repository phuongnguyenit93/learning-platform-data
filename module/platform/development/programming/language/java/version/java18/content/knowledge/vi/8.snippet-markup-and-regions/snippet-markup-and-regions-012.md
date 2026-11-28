# Region có tên và không tên khi áp dụng markup cho nhiều dòng

## Mục tiêu bài học

Trong Javadoc snippet, markup comment mặc định chỉ tác động lên dòng chứa comment. Khi muốn làm nổi bật, thay thế hoặc liên kết văn bản trên nhiều dòng, ta mở một **region**. Region có thể **không tên (anonymous)** hoặc **có tên (named)**.

Hai cách này dùng chung cơ chế phạm vi của các markup tag `@highlight`, `@replace` và `@link`. Region có tên giúp chỉ rõ cặp điểm bắt đầu/kết thúc; region không tên ngắn gọn khi phạm vi đơn giản và được đóng theo thứ tự gần nhất trước.

Tính năng snippet được đưa vào Javadoc từ Java 18 qua JEP 413 và tiếp tục được hỗ trợ trong JDK hiện đại. Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`, vốn tập trung vào những thay đổi Java 18 còn có ích trên JDK hiện tại.

Sau bài học, bạn có thể:

- Mở region không tên bằng thuộc tính `region` không có giá trị và đóng bằng `@end`.
- Mở region có tên bằng `region=name` và đóng đúng bằng `@end region=name`.
- Chọn giữa region có tên và không tên theo độ phức tạp của ví dụ.
- Hiểu cách region lồng nhau được đóng theo thứ tự và vì sao region chồng lấn cần tên.
- Kết hợp nhiều markup action trong một region mà vẫn giữ rõ phạm vi.
- Phân biệt region dùng làm phạm vi của markup action với region được `{@snippet}` chọn từ file external.
- Kiểm tra phạm vi thực tế qua HTML do `javadoc` sinh ra.

## 1. Vì sao markup cần region?

Markup comment thông thường áp dụng lên **dòng chứa comment**:

~~~java
/**
 * Chỉ làm nổi bật tên phương thức trên dòng khai báo:
 * {@snippet :
 *     String normalized = input.strip(); // @highlight substring="strip" type=bold
 *     System.out.println(normalized);
 * }
 */
public class CurrentLineExample {
}
~~~

Trong HTML, `strip` được làm nổi bật. Dòng `System.out.println(normalized);` không bị tác động bởi markup đó vì nó nằm ở dòng khác.

Khi muốn áp dụng một thao tác cho nhiều dòng, hãy thêm thuộc tính `region` vào markup tag và đóng phạm vi bằng `@end`:

~~~java
/**
 * Làm nổi bật các lần xuất hiện của normalized trong một đoạn:
 * {@snippet :
 *     // @highlight region substring="normalized" type=bold :
 *     String normalized = input.strip();
 *     boolean empty = normalized.isBlank();
 *     System.out.println(normalized);
 *     // @end
 * }
 */
public class RegionExample {
}
~~~

Markup `@highlight region` mở một vùng tác động. `@end` đóng vùng đó. Bộ chọn `substring="normalized"` được áp dụng trên toàn bộ nội dung trong vùng, nên các lần xuất hiện phù hợp ở cả ba dòng được làm nổi bật.

**Region là một khoảng dòng**, không phải một khối cú pháp Java. Javadoc không cần phân tích cặp ngoặc nhọn để xác định phạm vi; các marker markup mới quyết định điểm bắt đầu và kết thúc.

## 2. Region không tên (anonymous region)

Một region không tên được mở bằng markup tag có thuộc tính `region` nhưng không gán giá trị:

~~~java
// @highlight region substring="text" type=highlighted
~~~

Region kết thúc bằng marker không tên:

~~~java
// @end
~~~

Ví dụ đầy đủ:

~~~java
/**
 * Minh họa một region không tên:
 * {@snippet :
 *     public static void main(String... args) { // @highlight region substring="text" type=highlighted
 *         var text = "";                        // @replace substring='""' replacement=" ... "
 *         System.out.println(text);
 *     }                                         // @end
 * }
 */
public class AnonymousRegionExample {
}
~~~

Nội dung được sinh ra có dạng:

~~~java
public static void main(String... args) {
    var text =  ... ;
    System.out.println(text);
}
~~~

Trong ví dụ:

1. `@highlight region` bắt đầu region không tên ngay tại dòng chứa markup comment.
2. Phạm vi kéo dài đến marker `@end` tương ứng.
3. `substring="text"` chọn mọi lần xuất hiện của chữ `text` trong phạm vi; kiểu nhấn mạnh là `highlighted`.
4. `@replace` ở dòng khai báo biến là một markup action riêng, chỉ thay literal `""` trên dòng đó.
5. Các markup comment bị loại khỏi khối mã hiển thị.

Không cần đặt tên khi chỉ có một region đơn giản và marker kết thúc có thể ghép rõ ràng theo thứ tự mở/đóng.

### 2.1. Cách đóng region không tên

Marker `@end` không có tên sẽ đóng **region được mở gần nhất mà chưa có marker kết thúc tương ứng**.

Với các region lồng nhau, điều đó có nghĩa là đóng theo thứ tự ngược với lúc mở (last-in, first-out):

~~~java
void process(String input) { // @highlight region substring="process" type=bold
    if (input == null) {     // @highlight region substring="input" type=highlighted
        throw new IllegalArgumentException("input");
    }                        // @end
    System.out.println(input);
}                            // @end
~~~

- `@end` thứ nhất đóng region trong bắt đầu ở dòng `if`.
- `@end` thứ hai đóng region ngoài bắt đầu ở dòng khai báo method.
- Hai region không cần tên nếu thứ tự lồng nhau rõ ràng.

Nếu bỏ một marker `@end`, vùng ngoài có thể kéo dài xa hơn dự kiến hoặc cấu trúc region không còn như người viết định nghĩa. Vì vậy, hãy đếm cặp mở/đóng khi dùng nhiều region không tên.

## 3. Region có tên (named region)

Một region có tên được mở bằng thuộc tính `region` kèm giá trị:

~~~java
// @highlight region=R1 substring="text" type=highlighted
~~~

Và đóng bằng marker có cùng tên:

~~~java
// @end region=R1
~~~

Ví dụ:

~~~java
/**
 * Minh họa một region có tên:
 * {@snippet :
 *     public static void main(String... args) { // @highlight region=R1 substring="text" type=highlighted
 *         var text = "";                        // @replace substring='""' replacement=" ... "
 *         System.out.println(text);
 *     }                                         // @end region=R1
 * }
 */
public class NamedRegionExample {
}
~~~

Nội dung được sinh ra giống ví dụ region không tên ở mục trước. Việc đặt tên **không làm thay đổi cách hiển thị**; nó làm rõ marker mở nào tương ứng với marker đóng nào.

Có thể dùng tên dễ hiểu hơn thay cho `R1`:

~~~java
// @highlight region="text-usage" substring="text" type=highlighted
...
// @end region="text-usage"
~~~

Tên region là nhãn do người viết tài liệu chọn. Nên dùng tên mô tả ý nghĩa hoặc mục đích, chẳng hạn `validation`, `request`, `cleanup`, `text-usage`.

### 3.1. Khi nào nên đặt tên?

Region có tên phù hợp khi:

- File có nhiều region cùng tồn tại.
- Có các region lồng nhau hoặc chồng lấn.
- Điểm bắt đầu và kết thúc cách xa nhau.
- Người bảo trì cần nhận biết phạm vi bằng tên mà không phải đếm marker.
- Một vùng được tham chiếu từ nhiều snippet hoặc được dùng để giải thích riêng một thao tác.

Tên giúp đọc và review source dễ hơn. Nó không làm thay đổi nội dung mã được hiển thị, miễn là phạm vi được đánh dấu tương đương.

### 3.2. Tên ở marker mở và marker đóng phải tương ứng

Ví dụ hợp lệ:

~~~java
// @highlight region="request" substring="request" type=bold
var request = buildRequest();
// @end region="request"
~~~

Ví dụ sai mục đích:

~~~java
// @highlight region="request" substring="request" type=bold
var request = buildRequest();
// @end region="response"
~~~

Marker `@end region="response"` không đóng region `request`. Hãy dùng cùng tên ở hai đầu để Javadoc ghép đúng phạm vi.

## 4. So sánh region có tên và không tên

| Tiêu chí | Region không tên | Region có tên |
| --- | --- | --- |
| Mở vùng | `@highlight region`, `@replace region` hoặc `@link region`. | Thêm giá trị, ví dụ `region=validation`. |
| Đóng vùng | `@end`. | `@end region=validation`. |
| Cách ghép marker | Đóng region chưa đóng gần nhất. | Đóng region có tên tương ứng. |
| Độ ngắn | Ngắn hơn. | Dài hơn một chút. |
| Vùng lồng nhau | Có thể dùng, nhưng phải theo dõi thứ tự mở/đóng. | Rõ ràng hơn khi đọc source. |
| Vùng chồng lấn | Không đủ thông tin để ghép cặp một cách tường minh. | Cần dùng tên để xác định từng cặp. |
| Bảo trì file dài | Phù hợp với phạm vi nhỏ, cấu trúc đơn giản. | Phù hợp khi có nhiều vùng hoặc marker xa nhau. |

**Tên region không tạo ra hiệu ứng trình bày riêng.** Nếu cùng một phạm vi, cùng markup action và cùng selector, region có tên và không tên cho kết quả HTML như nhau. Sự khác biệt nằm ở cách định danh và ghép cặp marker.

## 5. Region là phạm vi của markup action

Các markup tag có thể mở region để áp dụng hành động qua nhiều dòng:

- `@highlight region`: làm nổi bật nội dung trong region.
- `@replace region`: thay văn bản trong region.
- `@link region`: tạo liên kết trên văn bản trong region.

Nếu có `substring` hoặc `regex`, selector được tìm trong toàn bộ phạm vi. Nếu không có selector, hành động áp dụng cho toàn bộ scope theo quy tắc của từng markup tag.

### 5.1. Một region, nhiều lần xuất hiện cần làm nổi bật

~~~java
/**
 * Nhấn mọi lần xuất hiện của input trong phần kiểm tra:
 * {@snippet :
 *     // @highlight region="validation" substring="input" type=bold :
 *     if (input == null) {
 *         throw new IllegalArgumentException("input");
 *     }
 *     boolean empty = input.isBlank();
 *     // @end region="validation"
 * }
 */
public class HighlightRegionExample {
}
~~~

Region `validation` bắt đầu ở dòng `if` và kết thúc sau dòng kiểm tra `isBlank`. Mọi lần xuất hiện của chữ `input` trong vùng được làm nổi bật, bao gồm cả tên biến và phần chữ bên trong thông báo lỗi. Markup chọn văn bản, không phân tích ngữ nghĩa Java.

### 5.2. Thay văn bản trong region

~~~java
/**
 * Lược bỏ phần cài đặt chi tiết:
 * {@snippet :
 *     // @replace region="implementation" substring="calculateDetailed" replacement="calculate" :
 *     int first = calculateDetailedFirst(input);
 *     int second = calculateDetailedSecond(first);
 *     return combine(first, second);
 *     // @end region="implementation"
 * }
 */
public class ReplaceRegionExample {
}
~~~

Mọi lần xuất hiện của `calculateDetailed` trong region được thay bằng `calculate`. Các phần khác của dòng được giữ nguyên. Region có tên giúp xác định rõ phạm vi mà phép thay thế tác động.

### 5.3. Liên kết các lần xuất hiện trong region

~~~java
/**
 * Các lời gọi strip() trong vùng đều trỏ tới cùng API:
 * {@snippet :
 *     // @link region="normalization" substring="strip()" target="java.lang.String#strip()" :
 *     String name = input.strip();
 *     String city = rawCity.strip();
 *     String country = rawCountry.strip();
 *     // @end region="normalization"
 * }
 */
public class LinkRegionExample {
}
~~~

`substring="strip()"` được tìm trong toàn bộ region. Mỗi lần xuất hiện phù hợp trở thành liên kết đến `String.strip()`. Nếu selector bị bỏ, toàn bộ scope của `@link` sẽ được liên kết; điều đó thường không phù hợp với một đoạn mã nhiều dòng.

## 6. Region lồng nhau

Region có thể nằm bên trong region khác. Với vùng lồng nhau, có thể dùng tên hoặc không tên; đặt tên thường giúp dễ theo dõi hơn khi phạm vi có nhiều tầng.

Ví dụ:

~~~java
/**
 * Ví dụ xử lý request với một vùng kiểm tra lồng trong method:
 * {@snippet :
 *     public Response handle(Request request) { // @highlight region="method" substring="handle" type=bold
 *         if (request == null) {                 // @highlight region="validation" substring="request" type=highlighted
 *             throw new IllegalArgumentException("request");
 *         }                                      // @end region="validation"
 *         return service.execute(request);
 *     }                                          // @end region="method"
 * }
 */
public class NestedRegionExample {
}
~~~

Ở đây:

- Region `method` bao trùm method `handle`.
- Region `validation` nằm bên trong `method` và chỉ bao trùm phần kiểm tra request.
- `@end region="validation"` đóng vùng trong.
- `@end region="method"` đóng vùng ngoài.

Có thể thay hai tên bằng hai region không tên và hai marker `@end`, miễn là các vùng được đóng đúng thứ tự gần nhất trước. Khi file dài, tên giúp người đọc hiểu ngay region nào đang được đóng.

### 6.1. Ví dụ nested region không tên

~~~java
/**
 * Hai region không tên được lồng theo thứ tự:
 * {@snippet :
 *     void process(String input) { // @highlight region substring="process" type=bold
 *         if (input == null) {    // @highlight region substring="input" type=highlighted
 *             throw new IllegalArgumentException("input");
 *         }                       // @end
 *         System.out.println(input);
 *     }                           // @end
 * }
 */
public class AnonymousNestedRegionExample {
}
~~~

Marker `@end` đầu tiên đóng region trong bắt đầu ở dòng `if`. Marker thứ hai đóng region ngoài bắt đầu ở dòng khai báo method. Đây là cách dùng hợp lệ, nhưng khi thêm hoặc di chuyển marker, người bảo trì phải giữ đúng thứ tự lồng nhau.

## 7. Region chồng lấn

Hai region **chồng lấn** khi một region bắt đầu trước region kia, nhưng kết thúc sau region kia. Đây không phải cấu trúc lồng nhau hoàn toàn.

Ví dụ về các khoảng dòng:

~~~text
Region A:  [----------------------]
Region B:          [----------------------]
                    <---- phần giao ---->
~~~

Với các region chồng lấn, phải dùng **tên region** để ghép chính xác marker bắt đầu và kết thúc. Region không tên dựa vào quy tắc đóng region chưa đóng gần nhất, nên không diễn đạt rõ quan hệ chồng lấn.

Ví dụ file external:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class OverlappingRegions {
    public void send(HttpClient client, URI uri)
            throws IOException, InterruptedException {
        // @start region="setup"
        String endpoint = uri.toString();
        // @start region="request"
        HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
                .GET()
                .build();
        // @end region="setup"
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        // @end region="request"
    }
}
~~~

Các khoảng:

- `setup` bắt đầu trước và kết thúc ở dòng `@end region="setup"`.
- `request` bắt đầu bên trong `setup` nhưng kết thúc sau `setup`.
- Phần tạo request nằm trong cả hai region, nên hai vùng chồng lấn.

Có thể tham chiếu hai vùng trong các snippet khác nhau:

~~~java
/**
 * Chuẩn bị endpoint và request:
 * {@snippet file="OverlappingRegions.java" region="setup"}
 *
 * Tạo request và gửi nhận response:
 * {@snippet file="OverlappingRegions.java" region="request"}
 */
public class OverlappingRegionsDoc {
}
~~~

Tên region cho phép Javadoc xác định chính xác marker đóng tương ứng dù thứ tự kết thúc không giống thứ tự bắt đầu. Đây là trường hợp không nên dùng region không tên.

## 8. Phân biệt region của markup action với region được chọn bởi `{@snippet}`

Thuộc tính `region` xuất hiện ở hai ngữ cảnh. Cần xác định đúng mục tiêu:

| Cách viết | Mục đích |
| --- | --- |
| `// @highlight region=validation substring="input"` … `// @end region=validation` | Mở phạm vi để **markup action** làm nổi bật văn bản qua nhiều dòng. |
| `// @start region="validation"` … `// @end region="validation"` | Đánh dấu một vùng trong nội dung snippet, thường dùng để tham chiếu từ external snippet. |
| `{@snippet file="Example.java" region="validation"}` | Chọn vùng `validation` để **đưa vào khối mã hiển thị**. |

Hai dạng đầu đều định nghĩa ranh giới region, nhưng cách dùng gắn với markup action và cách dùng chọn nội dung external có vai trò khác nhau.

Ví dụ với external file:

File `snippet-files/ValidationExample.java`:

~~~java
public class ValidationExample {
    public static void validate(String input) {
        // @start region="validation"
        if (input == null) {
            throw new IllegalArgumentException("input");
        }
        if (input.isBlank()) {
            throw new IllegalArgumentException("blank");
        }
        // @end region="validation"
    }
}
~~~

File Javadoc:

~~~java
/**
 * Chỉ trích phần kiểm tra:
 * {@snippet file="ValidationExample.java" region="validation"}
 */
public class ValidationApiDoc {
}
~~~

Trong trường hợp này, `@start`/`@end` xác định đoạn mã được `{@snippet}` lấy ra. Nếu muốn áp dụng highlight trên nhiều dòng trong snippet, có thể thêm markup action `@highlight region` riêng theo phạm vi phù hợp.

Một lưu ý quan trọng: khi dùng `@highlight region`, `@replace region` hoặc `@link region`, chính markup tag đó mở region cho action. Không cần thêm `@start region` trùng tên chỉ để mở cùng phạm vi action; hãy dùng marker mở/đóng đúng theo một cơ chế nhất quán.

## 9. Quy tắc chọn cách đặt tên

| Tình huống | Cách nên dùng | Lý do |
| --- | --- | --- |
| Một region duy nhất, ngắn, không lồng nhau | Không tên | Ít cú pháp, dễ nhìn. |
| Một region bao trùm region khác | Có tên nếu cần dễ bảo trì; không tên vẫn hợp lệ khi đóng LIFO rõ ràng. | Tên giảm việc phải đếm marker. |
| Nhiều region chồng lấn | Có tên | Cần ghép đúng cặp mở/đóng. |
| Một file external được dùng ở nhiều vị trí | Có tên cho vùng được tham chiếu | Thuộc tính `region` của `{@snippet}` cần tên vùng cụ thể. |
| Markup comment dài, nhiều selector | Có tên | Giúp xác định scope khi đọc source. |
| Ví dụ ngắn trong inline snippet | Không tên thường đủ | Không có nhu cầu tham chiếu vùng từ tag khác. |

Đừng đặt tên chỉ để trang trí. Tên có ích khi giúp xác định phạm vi hoặc làm rõ mối quan hệ giữa các marker. Nếu một region đơn giản có thể được đọc dễ dàng bằng một cặp `region`/`@end`, dạng không tên vẫn hoàn toàn phù hợp.

## 10. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mở `@highlight region` nhưng quên `@end`. | Region không có điểm kết thúc tương ứng. | Thêm `@end` hoặc `@end region=name` đúng với loại region. |
| Mở `region=validation` nhưng đóng bằng `@end region=request`. | Tên marker không tương ứng. | Dùng cùng tên ở điểm bắt đầu và kết thúc. |
| Dùng `@end` khi đang có nhiều region không tên. | `@end` đóng region chưa đóng gần nhất, có thể không phải vùng bạn định đóng nếu thứ tự bị sai. | Theo dõi thứ tự LIFO hoặc đặt tên cho các vùng. |
| Dùng region không tên để tạo vùng chồng lấn. | Không thể ghép tường minh cặp marker khi thứ tự kết thúc khác thứ tự bắt đầu. | Dùng tên riêng cho từng vùng chồng lấn. |
| Nghĩ tên region làm thay đổi kết quả HTML. | Tên chỉ giúp ghép marker và nhận diện phạm vi. | So sánh cùng một phạm vi có tên/không tên; nội dung hiển thị không đổi. |
| Nghĩ `@highlight region` chỉ tô dòng có comment. | Thuộc tính `region` mở rộng phạm vi đến `@end`. | Kiểm tra toàn bộ các dòng trong vùng. |
| Nghĩ `@start region` tự làm nổi bật nội dung. | Marker chỉ xác định ranh giới vùng; nó không tự tạo highlight. | Dùng `@highlight` nếu muốn định dạng nội dung. |
| Dùng `region` của `{@snippet}` để thay thế `region` của `@highlight`. | Một cái chọn nội dung external; một cái xác định phạm vi hành động. | Xác định rõ mục tiêu trước khi đặt thuộc tính. |
| Đặt selector quá rộng trong region. | `substring` hoặc `regex` có thể khớp nhiều vị trí hơn dự kiến. | Kiểm tra các lần khớp và thu hẹp selector. |
| Dùng nhiều markup action chồng lấn mà không kiểm tra. | Các hiệu ứng có thể làm kết quả khó đọc hoặc liên kết trùng có thể gây lỗi. | Tách vùng hoặc chọn selector không giao nhau; sinh Javadoc để xác minh. |

## 11. Kiểm chứng bằng `javadoc`

Tạo một class chứa ví dụ region có tên và không tên:

~~~java
/**
 * Kiểm tra hai cách mở region:
 *
 * {@snippet :
 *     public static void run(String input) { // @highlight region substring="run" type=bold
 *         if (input == null) {               // @highlight region=validation substring="input" type=highlighted
 *             throw new IllegalArgumentException("input");
 *         }                                  // @end region=validation
 *         System.out.println(input);
 *     }                                      // @end
 * }
 */
public class RegionNameCheck {
}
~~~

Trong ví dụ:

- Region không tên mở ở dòng khai báo `run` và kết thúc ở marker `@end` cuối cùng.
- Region có tên `validation` mở ở dòng `if` và đóng ở `@end region=validation`.
- Hai vùng lồng nhau; named region được đóng rõ ràng, anonymous region được đóng theo thứ tự gần nhất trước.

Chạy trong thư mục chứa file:

~~~bash
javadoc -d docs RegionNameCheck.java
~~~

Mở `docs/RegionNameCheck.html` và xác nhận:

1. Comment markup không xuất hiện trong khối mã.
2. Tên `run` được làm nổi bật trong phạm vi region ngoài.
3. Các lần xuất hiện của `input` trong vùng `validation` được làm nổi bật.
4. Dòng sau `@end region=validation` không còn thuộc phạm vi region trong.
5. Dòng sau `@end` cuối cùng không thuộc phạm vi region ngoài.

Nếu cần kiểm tra region chồng lấn, đặt file external vào `snippet-files`, tạo hai vùng có tên, rồi dùng hai `{@snippet file=... region=...}` để hiển thị từng vùng. So sánh phần mã được trích ra với điểm bắt đầu/kết thúc trong file source.

**Đừng chỉ kiểm tra tên marker trong source.** Kết quả HTML mới xác nhận phạm vi đã được xử lý đúng và selector đã áp dụng lên đúng nội dung.

## 12. Bài tập tự đánh giá

### Bài 1 — Region không tên đóng ở đâu?

~~~java
// @highlight region substring="value" type=bold
String value = input.strip();
System.out.println(value);
// @end
System.out.println("done");
~~~

**Đáp án:** Region bắt đầu ở dòng có markup `@highlight region` và kết thúc tại `@end`. Dòng `System.out.println("done");` ở sau marker không thuộc phạm vi.

### Bài 2 — Sửa tên region

~~~java
// @highlight region=validation substring="input" type=bold
if (input == null) {
    throw new IllegalArgumentException("input");
}
// @end region=request
~~~

**Đáp án:** Đổi marker cuối thành `@end region=validation` để khớp tên đã mở.

### Bài 3 — Hai region lồng nhau không tên

Có thể dùng hai marker `@end` không tên cho hai region lồng nhau không?

**Đáp án:** Có. Marker `@end` đầu tiên đóng region chưa đóng gần nhất (region trong); marker thứ hai đóng region ngoài. Cách này dựa vào thứ tự LIFO.

### Bài 4 — Region chồng lấn

Một region A bắt đầu ở dòng 1, region B bắt đầu ở dòng 3, A kết thúc ở dòng 5 và B kết thúc ở dòng 7. Nên dùng named hay anonymous region?

**Đáp án:** Dùng named region để ghép chính xác cặp A và B. Các region chồng lấn phải được đặt tên.

### Bài 5 — Marker có tự tạo highlight không?

File có:

~~~java
// @start region="main"
String value = input.strip();
// @end region="main"
~~~

Nội dung có tự được làm nổi bật không?

**Đáp án:** Không. `@start` và `@end` chỉ đánh dấu ranh giới. Muốn làm nổi bật, cần thêm `@highlight` với selector và kiểu phù hợp.

### Bài 6 — Phân biệt hai cách dùng region

`@highlight region=main` và `{@snippet file="Example.java" region="main"}` có cùng mục đích không?

**Đáp án:** Không. `@highlight region` xác định phạm vi nhiều dòng để làm nổi bật. `region` trên `{@snippet}` chọn phần nội dung external được đưa vào tài liệu.

## Tổng kết

- Region là khoảng dòng dùng làm phạm vi cho markup action hoặc để chọn nội dung snippet.
- Region không tên mở bằng `region` không có giá trị và đóng bằng `@end`; marker kết thúc đóng region chưa đóng gần nhất.
- Region có tên mở bằng `region=name` và đóng bằng `@end region=name`. Tên giúp xác định rõ cặp marker nhưng không làm thay đổi đầu ra.
- Region có thể lồng nhau. Region lồng nhau không bắt buộc phải có tên, nhưng tên giúp source dễ bảo trì.
- Region chồng lấn phải dùng tên để xác định quan hệ giữa các cặp mở/đóng.
- `@highlight`, `@replace` và `@link` đều có thể dùng `region` để áp dụng action trên nhiều dòng.
- `@start region`/`@end` thường định nghĩa vùng để external snippet tham chiếu; `region` trên `{@snippet}` chọn nội dung; `region` trên markup action xác định phạm vi hành động.
- Hãy chạy `javadoc` và kiểm tra HTML để xác nhận điểm bắt đầu, kết thúc và nội dung được xử lý đúng.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Guide: Snippets, JDK 26, mục Regions](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): ví dụ region không tên, region có tên, nested regions và overlapping regions.
2. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục Regions](https://download.java.net/java/early_access/jdk27/docs/specs/javadoc/doc-comment-spec.html#snippet): quy tắc mở region bằng `@start` hoặc markup action có thuộc tính `region`; quy tắc đóng bằng `@end` và `@end region=name`.
3. [Oracle — JavaDoc Guide, JDK 26, mục Markup Comments](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html#markup-comments): phạm vi của `@highlight`, `@replace` và `@link` khi có hoặc không có `region`.
4. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): tính năng snippet và markup comment được đưa vào Java 18.
