# Xử lý thụt lề và khoảng trắng ngẫu nhiên để đoạn mã hiển thị đúng

## 1. Mục tiêu

JEP 413 bổ sung thẻ `{@snippet ...}` cho Javadoc từ **JDK 18**. Tính năng này vẫn được hỗ trợ trên JDK hiện đại, giúp trình bày ví dụ mã có cấu trúc trong tài liệu API. Khi dùng inline snippet, đoạn mã có thể bị thụt vào quá sâu, mất lề cần thiết hoặc xuất hiện khác với cách nhìn trong file nguồn.

Javadoc xử lý phần thân inline snippet theo quy tắc tương tự `String.stripIndent()`. Hiểu quy tắc này giúp giữ cấu trúc block Java, điều khiển mức thụt lề hiển thị và tránh dựa vào những dấu cách vô hình ở cuối dòng.

Sau bài học, bạn có thể:

- Xác định chính xác phần nội dung được lấy từ inline snippet.
- Giải thích cách tính mức thụt lề tối thiểu.
- Điều khiển lề hiển thị bằng vị trí dấu `}` cuối cùng.
- Nhận biết ảnh hưởng của dòng trống, trailing whitespace, tab và dấu sao đầu dòng.
- Chọn cách trình bày rõ ràng khi khoảng trắng là một phần có ý nghĩa của dữ liệu.

## 2. Phần nào được tính là nội dung snippet?

Với inline snippet, nội dung được lấy từ **dòng mới đầu tiên sau dấu hai chấm** đến dấu ngoặc nhọn phải đóng thẻ.

~~~java
/**
 * Ví dụ:
 *
 * {@snippet :
 *     int quantity = 3;
 *     int total = quantity * 5;
 *     System.out.println(total);
 * }
 */
~~~

Javadoc loại bỏ phần thụt lề ngẫu nhiên trong nội dung theo quy tắc của `String.stripIndent()`. Phần thụt lề của dòng mở thẻ không tự động quyết định lề của mã hiển thị.

Dấu `}` cuối cùng cũng có **vị trí thụt lề**. Khoảng trắng đứng trước dấu này tạo thành dòng cuối của phần nội dung và có thể tham gia xác định mức thụt lề bị loại bỏ. Vì vậy, di chuyển dấu đóng thẻ có thể làm thay đổi cách mã xuất hiện trên trang tài liệu.

## 3. Quy tắc stripIndent

`String.stripIndent()` loại bỏ phần thụt lề chung của một khối văn bản nhiều dòng. Javadoc áp dụng cùng cách xử lý cho nội dung inline snippet.

Có thể hiểu quy trình qua bốn bước:

1. Với mỗi dòng không trống, đếm số ký tự khoảng trắng ở đầu dòng.
2. Tìm số nhỏ nhất trong các mức thụt lề đó. Dòng cuối cùng cũng được tính nếu nó là dòng trống chỉ chứa khoảng trắng.
3. Loại bỏ số ký tự khoảng trắng tối thiểu khỏi đầu mỗi dòng không trống; đồng thời loại bỏ khoảng trắng ở cuối các dòng không trống.
4. Dòng trống được chuyển thành dòng rỗng; các dòng được nối lại bằng ký tự xuống dòng LF.

Ký hiệu `·` dưới đây đại diện cho một dấu cách. Các dấu chấm chỉ dùng để minh họa, không phải ký tự trong mã nguồn.

~~~text
····int count = 2;
····if (count > 0) {
········System.out.println(count);
····}
····
~~~

Mức thụt lề nhỏ nhất của các dòng có nội dung là bốn dấu cách. Dòng cuối cũng có bốn dấu cách, nên mức chung được loại bỏ là bốn. Kết quả:

~~~text
int count = 2;
if (count > 0) {
    System.out.println(count);
}
~~~

Thụt lề tương đối bên trong block vẫn được giữ lại. Javadoc bỏ phần lề chung, không làm phẳng cấu trúc mã.

### Dòng trống

Dòng trống ở giữa snippet trở thành dòng rỗng sau xử lý. Tuy nhiên, **dòng cuối trống** có vai trò đặc biệt: số khoảng trắng trước dấu đóng thẻ có thể tham gia xác định mức thụt lề tối thiểu.

Do đó, dòng trống ở giữa không giữ các dấu cách căn lề, còn vị trí của dấu `}` cuối cùng có thể làm thay đổi mức lề bị loại bỏ.

## 4. Điều khiển lề bằng dấu đóng cuối

Giả sử các dòng mã được thụt vào ba dấu cách so với dấu mở thẻ. Nếu dấu đóng thẻ ở cột đầu tiên:

~~~java
{@snippet :
   int value = 10;
   int doubled = value * 2;
   System.out.println(doubled);
}
~~~

Dòng cuối cùng có mức thụt lề bằng không. Mức thụt lề chung có thể bị giữ ở 0, vì vậy phần mã hiển thị vẫn còn ba dấu cách ở đầu mỗi dòng.

Nếu di chuyển dấu `}` cuối vào cùng mức lề với các dòng mã:

~~~java
{@snippet :
   int value = 10;
   int doubled = value * 2;
   System.out.println(doubled);
   }
~~~

Dòng cuối trống có ba dấu cách. Mức thụt lề chung lúc này là ba, nên Javadoc loại bỏ ba dấu cách đầu của các dòng mã. Kết quả bắt đầu sát lề trái:

~~~text
int value = 10;
int doubled = value * 2;
System.out.println(doubled);
~~~

| Vị trí dấu đóng cuối | Kết quả thường thấy |
| --- | --- |
| Ở cột đầu tiên | Giữ lại phần lề đang có của mã snippet. |
| Cùng mức lề với dòng mã ít thụt nhất | Loại bỏ phần lề chung, mã bắt đầu sát lề trái. |
| Thụt vào sâu hơn mức lề tối thiểu của mã | Không loại bỏ nhiều hơn mức lề tối thiểu của các dòng có nội dung. |

Hãy căn dấu đóng theo kết quả mong muốn rồi kiểm tra HTML sinh ra. Formatter hoặc người chỉnh sửa thay đổi lề của dấu `}` có thể làm thay đổi cách hiển thị dù câu lệnh Java không đổi.

## 5. Khoảng trắng sau dấu sao của Javadoc comment

Trong traditional documentation comment, các dòng thường có dạng:

~~~java
/**
 * Mô tả API.
 *
 * {@snippet :
 *     int value = 10;
 *     System.out.println(value);
 *     }
 */
~~~

Javadoc loại bỏ phần trang trí đầu dòng gồm khoảng trắng đứng trước dấu sao và dấu `*` đầu dòng. **Khoảng trắng sau dấu sao không tự động bị xóa**; chúng được giữ lại trong văn bản đã xử lý của comment. Sau đó, nội dung inline snippet tiếp tục được xử lý theo quy tắc `stripIndent()`.

Ví dụ, dòng có dạng ` *     int value = 10;` có một dấu cách sau dấu sao comment, rồi mới đến phần thụt lề mà tác giả chủ động đặt cho mã. Khoảng trắng chung này có thể được loại bỏ khi Javadoc tính mức thụt lề tối thiểu.

Để tránh nhầm lẫn:

- Giữ một dấu cách chuẩn sau dấu sao comment để source dễ đọc.
- Dùng các dấu cách bổ sung nhất quán để căn lề mã.
- Đặt dấu đóng thẻ ở vị trí phản ánh mức lề muốn giữ.
- Xem mã thực tế trong trang HTML, không chỉ nhìn source editor.

## 6. Tab và dấu cách

`stripIndent()` đếm khoảng trắng theo **số ký tự**, không theo độ rộng hiển thị trong editor. Một dấu tab được tính là một ký tự khoảng trắng, tương tự một dấu cách. Nó không tự động mở rộng tab thành bốn hoặc tám dấu cách trước khi tính.

Ví dụ minh họa:

~~~text
····String first = "A";
⇥String second = "B";
········System.out.println(first + second);
~~~

Trong đó `·` biểu thị một dấu cách và `⇥` biểu thị một ký tự tab duy nhất.

Editor có thể hiển thị tab rộng bằng nhiều dấu cách, nhưng thuật toán không tính theo số cột nhìn thấy. Khi trộn tab với space, mức thụt lề tối thiểu có thể khác điều mắt người dự đoán và tạo kết quả lệch giữa các dòng.

**Khuyến nghị:** dùng dấu cách nhất quán trong nội dung snippet, đặc biệt với các block Java lồng nhau. Nếu dự án dùng tab cho mã nguồn, hãy kiểm tra HTML sau khi Javadoc sinh tài liệu.

## 7. Khoảng trắng cuối dòng

`stripIndent()` loại bỏ khoảng trắng cuối các dòng không trống. Dòng trống được thay bằng chuỗi rỗng. Vì vậy, trailing whitespace trong inline snippet không phải cách đáng tin cậy để biểu diễn dữ liệu có ý nghĩa.

Ký hiệu `·` đại diện dấu cách:

~~~text
String label = "ready";··
String state = "open";
····
System.out.println(label);
~~~

Sau khi xử lý, khoảng trắng cuối dòng thứ nhất và dòng trống chỉ chứa khoảng trắng không còn được giữ như dữ liệu hiển thị. Nếu ví dụ cần thể hiện giá trị có khoảng trắng cuối, hãy biểu diễn rõ ràng bằng mã:

~~~java
String label = "ready ";
System.out.println("[" + label + "]");
~~~

Đối với cấu hình hoặc dữ liệu văn bản mà khoảng trắng cuối dòng có ý nghĩa, nên đặt nội dung trong tệp external phù hợp và xem HTML kết quả. Nếu mục đích là dạy về khoảng trắng, dùng ký hiệu hiển thị như `·` hoặc `<space>` sẽ rõ ràng hơn dấu cách vô hình ở cuối dòng.

## 8. Ví dụ tổng hợp

Giả sử API chuẩn hóa tên trạng thái và trả về chuỗi chữ hoa. Tài liệu muốn hiển thị một ví dụ có block kiểm tra:

~~~java
package example;

/** Chuẩn hóa tên trạng thái. */
public final class StatusNames {
    private StatusNames() {
    }

    /**
     * Chuyển tên trạng thái thành chữ hoa.
     *
     * <p>Ví dụ:
     *
     * {@snippet id="normalize-status" lang="java" :
     * String result = StatusNames.normalize(" ready ");
     * if (!"READY".equals(result)) {
     *     throw new AssertionError(result);
     * }
     *     }
     *
     * @param value tên trạng thái không null hoặc chỉ chứa khoảng trắng
     * @return tên đã loại khoảng trắng hai đầu và chuyển thành chữ hoa
     * @throws IllegalArgumentException nếu value null hoặc chỉ chứa khoảng trắng
     */
    public static String normalize(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value must not be blank");
        }
        return value.strip().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Dấu đóng snippet được đặt sâu hơn phần lề của các câu lệnh để dòng cuối trống có thể loại bỏ phần thụt lề chung. Phần lề bên trong block `if` vẫn được giữ tương đối.

Lời mô tả và các thẻ `@param`, `@return`, `@throws` vẫn xác định hợp đồng API. Snippet chỉ minh họa cách gọi và kiểm tra kết quả. Javadoc **không biên dịch hoặc chạy inline snippet**; nếu ví dụ có kết quả kỳ vọng, hãy kiểm thử riêng trên JDK dự án sử dụng.

Có thể tạo tài liệu bằng JDK 18 trở lên:

~~~sh
javadoc -encoding UTF-8 -d build/docs src/main/java/example/StatusNames.java
~~~

Sau khi chạy, mở trang tài liệu của `StatusNames` và quan sát:

- Mã có bắt đầu ở lề trái như mong muốn không?
- Các câu lệnh bên trong block `if` có còn thụt vào không?
- Có dòng trống thừa hoặc khoảng trắng cuối dòng không?
- Nút sao chép snippet có sao chép đúng đoạn mã mong đợi không?

Nếu kết quả chưa đúng, điều chỉnh dấu `}` cuối cùng hoặc chuẩn hóa space/tab rồi chạy lại Javadoc.

## 9. Quy trình xử lý khoảng trắng

1. **Xác định ranh giới snippet:** tìm dấu hai chấm mở đầu và dấu `}` đóng thẻ.
2. **Kiểm tra comment bao ngoài:** xác định dấu sao đầu dòng và khoảng trắng còn lại sau chúng.
3. **Dùng space nhất quán:** tránh trộn tab và dấu cách trong cùng một khối.
4. **Tìm dòng ít thụt lề nhất:** đây là cơ sở tính phần lề chung bị loại bỏ.
5. **Kiểm tra dòng cuối:** khoảng trắng trước dấu `}` cuối cùng có thể ảnh hưởng mức thụt lề tối thiểu.
6. **Loại bỏ trailing whitespace không cần thiết:** đừng dùng dấu cách cuối dòng để truyền đạt dữ liệu.
7. **Sinh Javadoc:** xem HTML thực tế và kiểm tra cả bố cục lẫn nội dung khi sao chép.
8. **Kiểm thử ví dụ:** biên dịch/chạy mã hoặc chuyển external snippet vào unit test nếu cần kiểm chứng hành vi.

### Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mã vẫn thụt vào dù đã căn lề. | Dấu `}` cuối ở cột đầu tiên, khiến mức lề chung là 0. | Di chuyển dấu đóng vào mức lề muốn loại bỏ. |
| Mã bị dồn sát lề trái. | Dòng cuối hoặc các dòng ít thụt lề làm mức loại bỏ lớn hơn dự định. | Kiểm tra toàn bộ các dòng, đặc biệt dấu đóng cuối. |
| Block lồng nhau bị lệch. | Các dòng dùng tab và space không đồng nhất. | Chuẩn hóa thành space và sinh lại Javadoc. |
| Dòng trống mất khoảng trắng. | Dòng trống được stripIndent chuyển thành rỗng. | Dùng ký hiệu hiển thị nếu khoảng trắng là dữ liệu cần giải thích. |
| Khoảng trắng cuối dòng biến mất. | stripIndent loại bỏ trailing whitespace của dòng không trống. | Biểu diễn khoảng trắng bằng literal/escape rõ ràng. |
| Chỉnh sửa dấu sao comment làm lề snippet đổi. | Khoảng trắng sau dấu sao vẫn là một phần nội dung trước bước stripIndent. | Giữ cách viết comment nhất quán và kiểm tra HTML. |

## 10. Bài tập thực hành

### Bài tập 1: Dự đoán kết quả

Cho snippet:

~~~text
{@snippet :
····String name = "Java";
····if (!name.isEmpty()) {
········System.out.println(name);
····}
}
~~~

Trong đó `·` là dấu cách. Hãy dự đoán số dấu cách còn lại ở đầu dòng sau khi xử lý. Giải thích vai trò của dòng cuối cùng có mức lề 0.

### Bài tập 2: Điều chỉnh dấu đóng

Chuyển dấu `}` cuối cùng vào cùng mức lề bốn dấu cách của dòng mã đầu tiên. Dự đoán kết quả sau khi stripIndent rồi mở HTML Javadoc để xác nhận.

### Bài tập 3: Nhận diện tab và space

Dòng thứ nhất có bốn dấu cách, dòng thứ hai có một tab. Vì thuật toán đếm mỗi ký tự khoảng trắng là một, mức thụt lề tối thiểu của hai dòng là bao nhiêu? Vì sao editor có thể khiến bạn nghĩ kết quả phải khác?

### Bài tập 4: Khoảng trắng cuối dòng

Viết snippet hiển thị chuỗi có một dấu cách cuối bằng literal `"ready "`. So sánh với việc đặt một dấu cách vật lý ở cuối dòng mã nguồn. Giải thích vì sao cách thứ nhất rõ ràng và ổn định hơn.

**Tự kiểm:** giải thích được stripIndent; xác định vai trò của dấu đóng cuối; phân biệt khoảng trắng sau dấu sao comment với dấu sao trang trí; không trộn tab/space; không dựa vào trailing whitespace để biểu diễn dữ liệu; đã kiểm tra HTML Javadoc.

## 11. Ghi nhớ

- **Inline snippet dùng quy tắc tương tự `String.stripIndent()`.** Phần thụt lề chung bị loại bỏ, khoảng trắng cuối dòng bị xóa và dòng trống trở thành rỗng.
- **Dấu ngoặc đóng cuối cùng tham gia điều khiển lề.** Khoảng trắng trước nó có thể quyết định mức thụt lề tối thiểu bị loại bỏ.
- **Tab được tính là một ký tự khoảng trắng**, không tự mở rộng theo số cột của editor; trộn tab và space dễ tạo kết quả bất ngờ.
- **Khoảng trắng sau dấu sao của traditional comment vẫn được giữ** trước khi áp dụng quy tắc stripIndent cho snippet.
- **Kiểm tra HTML sinh ra là bước cần thiết.** Cách nhìn trong source editor không luôn giống nội dung snippet sau xử lý.

## Tài liệu chính thống

- [Oracle – JDK 26 Javadoc Snippets Guide, mục Indentation](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – Java SE 26 String.stripIndent() API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#stripIndent()).
- [Oracle – JDK 26 Documentation Comment Specification, Traditional Documentation Comments và snippet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).

