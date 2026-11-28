# Thuộc tính id và cách nhận diện snippet trong HTML được sinh ra

## 1. Mục tiêu và bối cảnh

JEP 413 đưa thẻ `{@snippet ...}` vào Javadoc từ **JDK 18** để trình bày ví dụ mã trong tài liệu API. Ngoài nội dung mã, một snippet còn có thể có thuộc tính `id`. Thuộc tính này đặt một định danh cho ví dụ, giúp người viết tài liệu, người đọc và công cụ xử lý tài liệu tìm đúng snippet trong source và trong HTML được sinh ra.

Sau bài học, bạn có thể:

- Khai báo `id` trong inline, external và hybrid snippet.
- Hiểu vị trí của `id` trong HTML được Standard Doclet tạo ra.
- Dùng fragment URL để dẫn trực tiếp đến một snippet.
- Phân biệt `id` với `region`, tên tệp và ID của phần tử API.
- Chọn ID ổn định, duy nhất và tránh xung đột với các anchor do Javadoc tạo.
- Kiểm tra ID trong HTML thực tế và hiểu giới hạn của Standard Doclet.

Thuộc tính `id` là một phần của cú pháp snippet đã có từ JDK 18 và vẫn được hỗ trợ trên JDK hiện đại. Nó **không làm thay đổi nội dung mã**, không chọn dòng cần hiển thị và không tự tạo tiêu đề hoặc kiểu trình bày cho snippet.

## 2. Khai báo thuộc tính id

Thuộc tính `id` được viết sau tên thẻ `snippet` dưới dạng `id=giá_trị`. Có thể đặt giá trị trong dấu nháy đơn hoặc nháy kép:

~~~java
/**
 * Ví dụ tạo mã đơn hàng:
 *
 * {@snippet id="snippet-order-create" :
 * String code = OrderCode.create("order", 42);
 * System.out.println(code);
 * }
 */
~~~

Trong đó:

- `snippet` mở một thẻ mã minh họa.
- `id="snippet-order-create"` đặt tên định danh cho snippet.
- Dấu hai chấm `:` mở đầu phần thân inline.
- Phần thân chứa mã được trình bày trong tài liệu.

Tên ID nên thể hiện mục đích của ví dụ, ví dụ `snippet-order-create`, `snippet-parse-date` hoặc `snippet-properties-server`. Dùng chữ thường và dấu gạch nối để dễ đọc, dễ tìm trong HTML và ít nguy cơ trùng với ID do Javadoc sinh ra.

### Thuộc tính id là tùy chọn

Nếu không khai báo `id`, snippet vẫn được xử lý và hiển thị bình thường:

~~~java
/**
 * {@snippet :
 * System.out.println("Hello");
 * }
 */
~~~

Không có `id` thì bạn không có một fragment định danh do mình đặt để liên kết ổn định đến snippet đó. Vì vậy, với ví dụ được tham chiếu nhiều lần trong tài liệu, được liên kết từ trang khác hoặc được công cụ bên ngoài phân tích, nên khai báo ID rõ ràng.

### Giá trị thuộc tính

Giống các thuộc tính snippet khác, giá trị có thể là một định danh đơn giản hoặc chuỗi đặt trong dấu nháy. Không có escape sequence trong giá trị thuộc tính. Vì vậy, hãy chọn tên ngắn, không có khoảng trắng và không cần ký tự escape:

~~~java
{@snippet id=snippet-order-create :
    // ...
}

{@snippet id='snippet-order-create' :
    // ...
}

{@snippet id="snippet-order-create" :
    // ...
}
~~~

Ba cách trên thể hiện các dạng viết giá trị thuộc tính. Trong tài liệu thực tế, mỗi snippet cần một ID riêng trên trang HTML chứa nó.

## 3. id xuất hiện ở đâu trong HTML?

Theo Documentation Comment Specification của Standard Doclet, nếu snippet có `id` thì giá trị đó được đặt vào thuộc tính HTML `id` trên **phần tử ngoài cùng được sinh ra để biểu diễn snippet**.

Điểm này rất quan trọng: không nên giả định ID luôn nằm trực tiếp trên thẻ `pre` chứa mã. Standard Doclet có thể tạo một lớp phần tử bao quanh khối mã để chứa bố cục, nút sao chép hoặc các thành phần trình bày khác. ID được gắn vào phần tử ngoài cùng đại diện cho snippet.

Ví dụ Javadoc:

~~~java
/**
 * Ví dụ tạo mã đơn hàng:
 *
 * {@snippet id="snippet-order-create" :
 * String code = OrderCode.create("order", 42);
 * System.out.println(code);
 * }
 */
~~~

Trong HTML được sinh ra, hãy tìm chuỗi:

~~~html
id="snippet-order-create"
~~~

Đó là dấu hiệu nhận diện snippet trong DOM. Cấu trúc phần tử bao quanh, tên class CSS và vị trí của phần tử mã bên trong có thể phụ thuộc phiên bản Standard Doclet hoặc giao diện tài liệu. Giá trị ID là điểm tham chiếu ổn định hơn các class CSS phục vụ bố cục.

### Standard Doclet sử dụng id như thế nào?

Cần phân biệt hai việc:

- **Standard Doclet:** chuyển ID vào HTML và đặt nó trên phần tử ngoài cùng của snippet. ID không làm thay đổi nội dung, không tự chọn region, không tự tô sáng và không tự tạo một liên kết nhìn thấy được.
- **Công cụ khác hoặc mã tài liệu:** có thể đọc ID để nhận diện snippet cụ thể, phân tích mã ví dụ, lập chỉ mục hoặc tạo liên kết đến vị trí của snippet.

Nói cách khác, ID là một **mốc nhận diện trong tài liệu**. Việc sử dụng mốc đó để điều hướng hoặc phân tích là trách nhiệm của liên kết HTML, công cụ hoặc quy trình xử lý tài liệu.

## 4. Dùng id để tạo liên kết trực tiếp đến snippet

Khi HTML đã có phần tử mang `id="snippet-order-create"`, trình duyệt có thể điều hướng đến vị trí đó bằng URL fragment `#snippet-order-create`.

### Liên kết trong cùng trang

Trong traditional documentation comment, có thể viết liên kết HTML:

~~~java
/**
 * Xem <a href="#snippet-order-create">ví dụ tạo mã đơn hàng</a>.
 *
 * {@snippet id="snippet-order-create" :
 * String code = OrderCode.create("order", 42);
 * System.out.println(code);
 * }
 */
~~~

Khi người đọc nhấp vào liên kết, trình duyệt tìm phần tử có ID tương ứng trong trang hiện tại và cuộn đến vị trí đó.

URL fragment có dạng:

~~~text
OrderService.html#snippet-order-create
~~~

Phần trước dấu `#` là trang HTML; phần sau là ID của snippet trong trang đó.

### Liên kết từ trang khác

Nếu trang `OrderService.html` chứa snippet, một trang khác có thể liên kết đến:

~~~html
<a href="OrderService.html#snippet-order-create">
    Ví dụ tạo mã đơn hàng
</a>
~~~

Đường dẫn tương đối phải được tính theo vị trí của trang chứa liên kết trong cây thư mục HTML do Javadoc sinh ra. Khi viết tài liệu trong cùng một trang, fragment `#snippet-order-create` là đủ.

### Dùng Javadoc link tag với URI fragment trên JDK mới

Từ JDK 23, cú pháp tham chiếu của Standard Doclet hỗ trợ fragment URI tùy ý bằng dấu hai thăng `##`. Vì vậy, có thể dùng Javadoc link tag để liên kết đến snippet ID:

~~~java
/**
 * Xem {@link OrderService##snippet-order-create ví dụ tạo mã đơn hàng}.
 */
~~~

Cú pháp này tạo liên kết đến fragment trong trang tài liệu của `OrderService`. Nó hữu ích khi muốn dùng cơ chế liên kết Javadoc thay vì viết HTML anchor trực tiếp.

Nếu dự án cần tương thích với JDK cũ hơn chưa hỗ trợ dạng tham chiếu `##fragment`, dùng HTML `<a href="#...">` hoặc URL fragment thông thường. Cần sinh tài liệu bằng JDK mục tiêu để xác nhận cách liên kết được hỗ trợ.

## 5. Chọn ID ổn định và tránh xung đột

Một trang Javadoc đã có nhiều ID do Standard Doclet tạo cho lớp, phương thức, trường, tiêu đề và các vị trí điều hướng khác. ID của snippet cần tránh trùng với những định danh này.

Documentation Comment Specification khuyến nghị ID do người dùng đặt nên chứa ít nhất một ký tự **không hợp lệ trong Java identifier**, chẳng hạn dấu gạch nối `-`. Khuyến nghị này giúp giảm khả năng xung đột với các ID được dùng cho vị trí của khai báo chương trình. Vì thế, `snippet-order-create` phù hợp hơn `snippetOrderCreate` hoặc `OrderService`.

Ví dụ nên dùng:

~~~java
{@snippet id="snippet-order-create" :
    // ...
}

{@snippet id="snippet-order-parse-response" :
    // ...
}

{@snippet id="snippet-properties-server" :
    // ...
}
~~~

Các dạng sau dễ gây xung đột hoặc khó quản lý:

~~~java
{@snippet id="create" :
    // ...
}

{@snippet id="OrderService" :
    // ...
}

{@snippet id="processOrder" :
    // ...
}
~~~

Các tên này chỉ gồm ký tự có thể xuất hiện trong Java identifier, hoặc trùng với tên khai báo. Dùng tiền tố `snippet-` và dấu gạch nối làm ý định rõ ràng hơn.

### Quy tắc đặt ID nên áp dụng

| Quy tắc | Ví dụ | Lý do |
| --- | --- | --- |
| Dùng tiền tố có nghĩa | `snippet-` | Nhìn tên là biết ID dành cho snippet. |
| Dùng dấu gạch nối | `snippet-order-create` | Tránh xung đột với ID của phần tử chương trình. |
| Nêu mục đích, không nêu vị trí | `snippet-parse-response` | Có thể di chuyển snippet trong source mà không cần đổi tên. |
| Duy nhất trong trang | Mỗi snippet có ID riêng | Fragment URL cần xác định một đích duy nhất. |
| Giữ ổn định qua các lần sửa tài liệu | Giữ `snippet-order-create` khi chỉ sửa nội dung mã | Liên kết cũ không bị hỏng khi nội dung thay đổi. |

HTML yêu cầu giá trị `id` xác định duy nhất một phần tử trong tài liệu. Javadoc chuyển giá trị được khai báo sang HTML; người viết cần quản lý tính duy nhất và kiểm tra khi thêm snippet mới. Không nên dựa vào giả định rằng công cụ sẽ tự đổi tên ID trùng hoặc luôn phát hiện mọi xung đột.

## 6. Phân biệt id, region, file và class

Các thuộc tính này cùng xuất hiện trong cú pháp snippet nhưng giải quyết những vấn đề khác nhau.

| Thành phần | Mục đích | Tác động |
| --- | --- | --- |
| `id` | Nhận diện một snippet trong source và HTML. | Đặt ID lên phần tử ngoài cùng đại diện snippet trong HTML. |
| `region` | Chọn một vùng có tên trong tệp external. | Quyết định đoạn mã nào được trích ra để hiển thị. |
| `file` | Chỉ định tệp văn bản chứa snippet. | Xác định nguồn nội dung bên ngoài. |
| `class` | Chỉ định lớp Java chứa snippet external. | Xác định tệp nguồn Java được dùng làm nguồn snippet. |

Ví dụ external snippet có cả `id` và `region`:

~~~java
/**
 * Ví dụ xác thực dữ liệu:
 *
 * {@snippet
 *     file="OrderExamples.java"
 *     id="snippet-order-validation"
 *     region="validation"
 * }
 */
~~~

Trong tệp `OrderExamples.java`:

~~~java
package example;

public class OrderExamples {
    public static void main(String[] args) {
        // @start region=validation
        int quantity = 3;
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        // @end region=validation
    }
}
~~~

Ở đây:

- `file` chỉ ra nguồn chứa ví dụ.
- `region` chọn vùng `validation` bên trong tệp.
- `id` đặt mốc HTML cho snippet được tạo từ vùng đó.

Tên region có thể được tái sử dụng theo quy tắc vùng trong tệp nguồn; ID của snippet lại cần duy nhất trên trang HTML. Không dùng chung một giá trị cho hai mục đích nếu điều đó làm người đọc nhầm lẫn.

## 7. Nhận diện snippet bằng công cụ kiểm tra HTML

Sau khi chạy Javadoc, có thể kiểm tra ID theo các bước sau:

1. Tìm trang HTML của lớp hoặc thành viên chứa chú thích có snippet.
2. Mở trang trong trình duyệt và dùng công cụ Developer Tools để kiểm tra DOM.
3. Tìm chuỗi ID, ví dụ `snippet-order-create`.
4. Xác nhận phần tử chứa ID bao quanh đúng khối snippet cần nhận diện.
5. Mở URL có fragment `#snippet-order-create` để kiểm tra trình duyệt điều hướng đến đúng vị trí.
6. Nếu trang được sinh lại sau khi đổi JDK hoặc theme, kiểm tra lại DOM và liên kết.

Có thể tìm trong file HTML được sinh ra bằng công cụ tìm kiếm văn bản:

~~~powershell
Select-String -Path ".uilddocsexampleOrderService.html" -Pattern 'id="snippet-order-create"'
~~~

Lệnh này chỉ tìm chuỗi ID trong file HTML. Kết quả giúp xác nhận Javadoc đã chuyển ID vào tài liệu; nó không xác nhận rằng liên kết từ trang khác đã đúng đường dẫn.

### Khi không tìm thấy ID

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy ID trong HTML. | Thẻ snippet không khai báo `id` hoặc trang HTML chưa được tạo lại. | Kiểm tra source và chạy lại Javadoc. |
| ID xuất hiện nhưng liên kết không đến đúng snippet. | `href` dùng sai fragment hoặc ID trùng. | So sánh chính xác giá trị `href` và `id` trong DOM. |
| Liên kết từ trang khác bị sai. | Đường dẫn tương đối đến file HTML không đúng. | Kiểm tra URL đầy đủ gồm đường dẫn trang và fragment. |
| ID nằm trên phần tử wrapper, không nằm trên `pre`. | Standard Doclet gắn ID vào phần tử ngoài cùng đại diện snippet. | Kiểm tra toàn bộ DOM của khối snippet thay vì chỉ tìm thẻ `pre`. |
| Đổi theme làm selector CSS không còn đúng. | Công cụ dựa vào class CSS nội bộ của giao diện. | Dùng ID được khai báo thay cho class phục vụ bố cục. |

## 8. Bài tập thực hành

### Bài tập 1: Đặt ID cho nhiều snippet

Một lớp `OrderService` có ba ví dụ: tạo đơn hàng, kiểm tra trạng thái và phân tích phản hồi. Hãy đặt ba ID duy nhất theo quy tắc:

- Có tiền tố `snippet-`.
- Có dấu gạch nối.
- Thể hiện mục đích của từng ví dụ.
- Không trùng tên lớp hoặc tên phương thức.

Gợi ý: `snippet-order-create`, `snippet-order-status` và `snippet-order-response-parse`.

### Bài tập 2: Tạo liên kết đến snippet

Thêm `id="snippet-order-create"` vào một inline snippet. Tạo liên kết HTML `<a href="#snippet-order-create">` ở đầu comment. Sinh Javadoc và kiểm tra khi nhấp liên kết, trang có cuộn đến đúng khối mã không.

Nếu dùng JDK 23 trở lên, thử thêm Javadoc link tag:

~~~java
{@link OrderService##snippet-order-create ví dụ tạo đơn hàng}
~~~

So sánh URL được sinh ra với fragment ID của snippet.

### Bài tập 3: Phân biệt id và region

Tạo một tệp external có hai vùng `validation` và `serialization`. Tham chiếu vùng `validation` bằng `region="validation"`, đồng thời đặt `id="snippet-order-validation"` cho snippet đó. Giải thích vì sao đổi tên region trong tệp ngoài có thể cần sửa thuộc tính region, còn đổi ID ảnh hưởng đến các liên kết HTML đang tham chiếu.

### Bài tập 4: Kiểm tra xung đột ID

Tạo hai snippet cùng trang với ID giống nhau. Sinh HTML và kiểm tra DOM. Sau đó đổi tên một ID để đảm bảo mỗi fragment chỉ trỏ đến một phần tử. Cuối cùng, thử đặt ID chỉ gồm tên Java identifier và thay bằng ID có dấu gạch nối để hiểu khuyến nghị của đặc tả.

**Tự kiểm:** ID được khai báo đúng; mỗi snippet có một ID riêng; ID nằm trên phần tử ngoài cùng; liên kết fragment đi đúng vị trí; ID không bị nhầm với region hoặc file; HTML sau khi sinh được kiểm tra thực tế.

## 9. Ghi nhớ

- **`id` đặt tên cho một snippet**, giúp nhận diện nó trong source và HTML được sinh ra.
- **Standard Doclet đặt ID lên phần tử ngoài cùng đại diện snippet**, không nhất thiết là thẻ `pre` chứa mã.
- **ID là mốc fragment HTML.** Dùng `href="#snippet-id"` hoặc cú pháp tham chiếu URI fragment được hỗ trợ để liên kết đến ví dụ.
- **Dùng ID duy nhất và có dấu gạch nối.** Điều này giảm xung đột với ID Javadoc tự tạo cho khai báo chương trình.
- **`id` khác `region`.** Region chọn nội dung trong tệp external; ID nhận diện khối snippet được sinh ra.
- **Kiểm tra DOM và URL sau khi chạy Javadoc.** Đừng phụ thuộc vào class CSS hoặc giả định về cấu trúc wrapper của một theme cụ thể.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle – JDK 26 Javadoc Snippets Guide, mục Attributes](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, snippet id và HTML identifiers](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle – JDK 26 Documentation Comment Specification, References và URI fragments](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).

