# `@highlight`: làm nổi bật cả dòng hoặc phần văn bản được chọn

## Phạm vi và kết quả học tập

Trong Java 18, **JEP 413** bổ sung thẻ `{@snippet}` cho Javadoc. Tính năng này vẫn được chuẩn hóa trong công cụ `javadoc` của các JDK hiện đại. Khi viết tài liệu API, ta thường muốn người đọc chú ý vào câu lệnh quan trọng, một biến, chuỗi ký tự, hoặc các lần xuất hiện của một biểu thức. **Markup tag `@highlight`** được thiết kế cho công việc đó.

Bài học thuộc chủ đề **Markup và region** của module `JAVA_VERSION_JAVA18`. Sau khi học, bạn có thể:

- Dùng `@highlight` để nhấn mạnh **toàn bộ dòng** mà không chỉnh sửa mã nguồn ví dụ.
- Dùng `substring` khi biết chính xác đoạn chữ cần làm nổi bật và `regex` khi cần nhận diện theo mẫu.
- Chọn cách thể hiện bằng `type=bold`, `type=italic` hoặc `type=highlighted`.
- Mở rộng phạm vi tô nổi bật qua nhiều dòng bằng `region`, đóng vùng đúng chỗ bằng `@end`.
- Đọc dấu `:` cuối markup comment để xác định chính xác **dòng nào bị tác động**.
- Tạo và kiểm tra Javadoc đầu ra thay vì suy đoán hiệu ứng từ file nguồn.

Bài này chỉ dùng những khả năng của `@snippet`/`@highlight` còn hữu ích và được tài liệu JDK hiện hành mô tả. `@highlight` **chỉ thay đổi cách trình bày đoạn mã trong HTML của Javadoc**; nó không đổi mã Java, kết quả chương trình, hoặc thời gian chạy.

## 1. Cú pháp và quy tắc áp dụng

Một markup comment Java thường nằm sau câu lệnh:

~~~java
int maxAttempts = 3; // @highlight substring="maxAttempts"
~~~

Phần `// @highlight substring="maxAttempts"` là chỉ dẫn cho bộ tạo tài liệu. Khi xuất ra trang HTML, `javadoc` lược bỏ **markup comment**, vẫn hiển thị câu lệnh `int maxAttempts = 3;` và làm nổi bật chữ `maxAttempts`. Comment Java thông thường không phải markup, ví dụ `// Đơn vị: lần thử`, vẫn có thể được giữ lại.

Cú pháp tổng quát:

~~~text
// @highlight [substring="chuỗi" | regex="biểu_thức"] [type="kiểu"] [region="tên_vùng"]
~~~

Các thuộc tính được dùng theo ý nghĩa sau:

| Thành phần | Ý nghĩa | Nếu bỏ qua |
| --- | --- | --- |
| `@highlight` | Yêu cầu đánh dấu phần mã tương ứng trong đầu ra Javadoc. | Không có thao tác tô nổi bật. |
| `substring="..."` | Chọn **tất cả lần xuất hiện** của một chuỗi ký tự đúng như đã viết trong phạm vi tác động. | Nếu đồng thời không có `regex`, toàn bộ phạm vi được tô. |
| `regex="..."` | Chọn các đoạn khớp với biểu thức chính quy (theo cú pháp `java.util.regex.Pattern`). | Nếu đồng thời không có `substring`, toàn bộ phạm vi được tô. |
| `type="bold"` | Trình bày phần khớp dưới kiểu **in đậm**. | Công cụ dùng kiểu làm nổi bật mặc định. |
| `type="italic"` | Trình bày phần khớp dưới kiểu *in nghiêng*. | Công cụ dùng kiểu làm nổi bật mặc định. |
| `type="highlighted"` | Đánh dấu phần khớp bằng kiểu `highlighted` của stylesheet Javadoc. | Công cụ dùng kiểu làm nổi bật mặc định. |
| `region` hoặc `region="tên"` | Bắt đầu phạm vi tác động **nhiều dòng**, kéo dài đến `@end` tương ứng. | Chỉ tác động lên dòng chứa markup comment, hoặc dòng kế nếu có dấu `:`. |

`substring` và `regex` là hai cách **thay thế nhau** để chỉ định văn bản; trong ví dụ thông thường, chỉ dùng một trong hai. Khi không dùng cả hai, `@highlight` áp dụng cho **toàn bộ dòng** hoặc **toàn bộ region**.

**Điểm cần nhớ:** Đơn vị mặc định là **một dòng**. Muốn một chỉ dẫn có hiệu lực qua nhiều dòng, hãy dùng `region` và ghép đúng marker kết thúc `@end`.

## 2. Cách 1 — Làm nổi bật toàn bộ dòng

Khi không có `substring` hoặc `regex`, công cụ đánh dấu cả dòng mã.

Xét file `HighlightLineDoc.java`:

~~~java
/**
 * Minh họa một dòng cần chú ý:
 *
 * {@snippet :
 *     boolean allowed = count > 0; // @highlight
 *     System.out.println(allowed);
 * }
 */
public class HighlightLineDoc {
}
~~~

Người đọc tài liệu sẽ thấy **nội dung văn bản** của khối mã:

~~~java
boolean allowed = count > 0;
System.out.println(allowed);
~~~

Điểm khác biệt khi xem bằng trình duyệt: **toàn bộ dòng `boolean allowed = count > 0;` được làm nổi bật**, trong khi dòng `println` giữ kiểu thông thường. Dòng `boolean ...` vẫn được giữ; phần `// @highlight` biến mất khỏi đầu ra.

Hãy dùng cách này để nhấn mạnh một dòng kiểm tra điều kiện, câu lệnh khởi tạo hoặc lời gọi API quan trọng trong một ví dụ ngắn.

### Dòng chứa chỉ dẫn và dấu `:`

Mặc định `@highlight` áp dụng cho **dòng có comment**:

~~~java
int timeout = 500; // @highlight
~~~

Nếu muốn chỉ dẫn đứng trên một dòng riêng và tác động vào **dòng ngay sau**, đặt dấu hai chấm ở cuối markup comment:

~~~java
// @highlight :
int timeout = 500;
~~~

Hai ví dụ cùng làm nổi bật toàn dòng `int timeout = 500;`. Comment điều khiển không xuất hiện trong khối mã đã sinh. Nếu bỏ dấu `:` khỏi ví dụ thứ hai, đừng cho rằng `@highlight` sẽ tự chuyển sang dòng dưới: theo mặc định nó chỉ áp dụng cho chính dòng có comment.

## 3. Cách 2 — Chọn chính xác một chuỗi bằng `substring`

`substring` nhận **chuỗi nguyên văn**, không phải biểu thức chính quy. Nếu văn bản được chọn xuất hiện nhiều lần trong dòng, **mọi lần xuất hiện** trong phạm vi đều được đánh dấu.

~~~java
/**
 * {@snippet :
 *     int size = 2; // @highlight substring="size"
 *     String sizeText = "size=" + size; // @highlight substring="size"
 * }
 */
public class HighlightSubstringDoc {
}
~~~

Văn bản hiển thị trong Javadoc:

~~~java
int size = 2;
String sizeText = "size=" + size;
~~~

Trong dòng đầu, `size` là biến được tô nổi bật. Ở dòng thứ hai, `size` có mặt **ba lần**: trong tên `sizeText`, trong chuỗi `"size="` và trong biểu thức `+ size`. Cả ba đều phù hợp với `substring="size"`. Công cụ so khớp **văn bản nguồn**, không phân tích ngữ nghĩa rằng đâu là tên biến và đâu là chuỗi ký tự.

Một số quy tắc thực hành:

- `substring="count"` khớp chính xác đoạn chữ `count`, kể cả khi nó nằm trong `counter` hoặc `getCount` nếu chữ hoa/thường phù hợp.
- So khớp phân biệt chữ hoa/thường theo cách thông thường: `substring="ID"` không đồng nghĩa `substring="id"`.
- Dùng dấu nháy đơn hoặc kép để chứa chuỗi có dấu cách, ví dụ `substring='new value'`.
- Nếu cần ranh giới từ, hoặc chọn tên thuộc một nhóm mẫu, dùng `regex` ở phần tiếp theo.

### Lồng thêm kiểu hiển thị `type`

~~~java
int size = 2; // @highlight substring="size" type="bold"
~~~

Phần `size` được đánh dấu bằng loại `bold`. Các lựa chọn hợp lệ là `bold`, `italic` và `highlighted`. Loại hiển thị được chuyển thành CSS class để stylesheet của Javadoc quyết định cách vẽ cụ thể; màu nền hoặc sắc độ có thể thay đổi theo stylesheet và chủ đề của tài liệu.

Khi đã có nhiều kiểu trong một trang API, nên dùng nhất quán: ví dụ `bold` cho tên phương thức được giải thích, `highlighted` cho dòng hoặc từ khóa cần chú ý mạnh.

## 4. Cách 3 — Chọn theo mẫu bằng `regex`

Khi ví dụ có nhiều biến giống nhau nhưng khác hậu tố, `regex` giúp chọn đúng những đoạn phù hợp mẫu.

~~~java
/**
 * {@snippet :
 *     int item1 = 10, item2 = 20; // @highlight regex='item[0-9]+'
 *     int total = item1 + item2;
 * }
 */
public class HighlightRegexDoc {
}
~~~

Văn bản của khối mã hiển thị:

~~~java
int item1 = 10, item2 = 20;
int total = item1 + item2;
~~~

Ở dòng đầu, cả `item1` và `item2` được làm nổi bật. Dòng thứ hai **không** bị tác động vì markup comment chỉ nằm trên dòng đầu và không khai báo `region`.

| Bạn muốn chọn | Chỉ dẫn phù hợp | Vì sao |
| --- | --- | --- |
| Mọi lần xuất hiện của chữ `item`, kể cả trong `item1` | `@highlight substring="item"` | Khớp chuỗi nguyên văn. |
| Tên có tiền tố `item` và số theo sau | `@highlight regex='item[0-9]+'` | `[0-9]+` yêu cầu một hay nhiều chữ số. |
| Chuỗi `error` hoặc `warning` | `@highlight regex='error|warning'` | `|` biểu thị hai nhánh lựa chọn. |
| Toàn bộ dòng | `@highlight` | Không cần tạo mẫu nhận diện. |

**Cẩn thận với độ rộng của regex:** `regex='.*'` có thể chọn cả dòng và chuỗi rỗng, trong khi `regex='item[0-9]+'` mô tả mục tiêu cụ thể hơn. Các ký tự đặc biệt của regex như dấu chấm, dấu ngoặc và dấu cộng có thể đổi ý nghĩa nếu không escape thích hợp. Khi viết regex cho Javadoc, nên thử với ví dụ có trường hợp khớp và không khớp, rồi kiểm tra tài liệu HTML thực tế.

Ví dụ, muốn tô nổi bật chỉ biểu thức `count + 1` trong dòng:

~~~java
int next = count + 1; // @highlight regex='count \+ 1'
~~~

Ở đây dấu `\+` trong regex có nghĩa là **dấu cộng theo nghĩa đen**. Nếu viết `+` mà không escape, dấu cộng sẽ trở thành toán tử lặp của regex. Mẫu này được đặt trong markup comment của snippet nên không phải là chuỗi literal Java được truyền vào phương thức; không tự ý nhân đôi backslash như khi viết Java string.

## 5. Dùng `region` để tô nổi bật nhiều dòng

Nếu `@highlight` chỉ xuất hiện trên một dòng, các dòng sau sẽ không tự được đánh dấu. `region` mở rộng phạm vi tác động đến marker `@end` tương ứng.

### 5.1. Region có tên

Đây là ví dụ inline snippet trong `HighlightRegionDoc.java`:

~~~java
/**
 * Các dòng sử dụng biến sum được làm nổi bật:
 *
 * {@snippet :
 *     // @highlight region="sumCalc" substring="sum" :
 *     int sum = 0;
 *     sum += 5;
 *     System.out.println(sum);
 *     // @end region="sumCalc"
 *     System.out.println("done");
 * }
 */
public class HighlightRegionDoc {
}
~~~

Phần văn bản của khối mã sinh ra:

~~~java
int sum = 0;
sum += 5;
System.out.println(sum);
System.out.println("done");
~~~

Ở ba dòng đầu, mọi chữ `sum` khớp `substring="sum"` đều được đánh dấu. Dòng `System.out.println("done");` đứng **sau** `@end region="sumCalc"`, nên không thuộc phạm vi tô nổi bật. Dòng marker mở và đóng không xuất hiện trong đoạn mã đã hiển thị.

Cần phân biệt ba thành phần:

1. `@highlight region="sumCalc" ...` vừa bắt đầu một vùng tác động của chính `@highlight`, vừa xác định hành vi tô nổi bật.
2. Dấu `:` ở cuối comment khiến phạm vi bắt đầu tại dòng `int sum = 0;` ngay sau chỉ dẫn.
3. `@end region="sumCalc"` kết thúc vùng có tên; các dòng tiếp theo không chịu tác động của chỉ dẫn đó.

**Không cần** thêm một `@start region="sumCalc"` khác cho ví dụ này. Bản thân `@highlight` có thuộc tính `region` đã mở vùng cần đánh dấu; thêm marker mở khác cùng tên dễ làm các cặp vùng khó theo dõi.

### 5.2. Region không đặt tên

Nếu không cần tham chiếu vùng bằng tên, có thể viết gọn:

~~~java
/**
 * {@snippet :
 *     int result = 1; // @highlight region type="bold"
 *     result += 2;
 *     System.out.println(result);
 *     // @end
 *     System.out.println("completed");
 * }
 */
public class AnonymousRegionDoc {
}
~~~

Vì không có `substring`/`regex`, **toàn bộ nội dung trong region** được tô nổi bật kiểu `bold`: dòng khai báo `result`, dòng cộng thêm và dòng in giá trị. Dòng `System.out.println("completed");` nằm ngoài vùng nên không được tô.

`@end` không kèm tên đóng vùng mở gần nhất chưa được đóng. Với tài liệu nhiều vùng, dùng tên rõ nghĩa sẽ dễ kiểm tra hơn.

### 5.3. Phân biệt hai loại `region`

Có hai mục đích thường gặp và chúng không đồng nhất:

| Cú pháp | Vai trò |
| --- | --- |
| `{@snippet file="Example.java" region="part"}` | **Chọn những dòng nào** trong file ngoài được đưa vào khối mã hiển thị. |
| `// @highlight region="focus" substring="value"` … `// @end region="focus"` | **Chọn phạm vi áp dụng tô nổi bật** trong nội dung snippet. |

Chọn region trên `{@snippet}` quyết định **nội dung được trích ra**. Mở region bằng `@highlight` quyết định **định dạng** của phần nội dung tương ứng. Nếu cần vừa chọn phần file, vừa làm nổi bật một số từ, hai cơ chế có thể kết hợp; cần quản lý các marker có tên để tránh nhầm phạm vi.

## 6. Ví dụ external snippet có thể kiểm tra riêng

Với ví dụ thực tế trong thư viện, file snippet ngoài hữu ích vì có thể biên dịch riêng và giữ cho mô tả API gọn hơn.

Giả sử cấu trúc thư mục:

~~~text
HighlightDoc.java
snippet-files/
└── CounterExample.java
~~~

File `HighlightDoc.java`:

~~~java
/**
 * Minh họa cách tăng bộ đếm:
 *
 * {@snippet file="CounterExample.java" region="increment"}
 */
public class HighlightDoc {
}
~~~

File `snippet-files/CounterExample.java`:

~~~java
public class CounterExample {
    public static int next(int input) {
        // @start region="increment"
        int current = input + 1; // @highlight substring="current" type="bold"
        return current;         // @highlight substring="current" type="bold"
        // @end region="increment"
    }
}
~~~

Khi tạo tài liệu cho `HighlightDoc`, phần **văn bản mã** được trích ra là:

~~~java
int current = input + 1;
return current;
~~~

Cả hai chữ `current` được tô nổi bật kiểu `bold` ở từng dòng. Các dòng khai báo lớp/phương thức, cặp marker `@start`/`@end` và comment `@highlight` không xuất hiện trong khối mã của tài liệu.

Ở ví dụ này:

- `region="increment"` trong `{@snippet}` chọn phần mã có tên `increment`.
- Hai `@highlight` độc lập, mỗi tag đánh dấu đúng **một dòng**.
- File `CounterExample.java` còn giữ cấu trúc lớp và phương thức đầy đủ, thích hợp để biên dịch riêng bằng `javac`. Nội dung được trích trong Javadoc có thể chỉ là một **mảnh mã**.

Không nên đánh giá tính đúng của nội dung chỉ từ bản hiển thị: với external snippet, có thể kiểm tra cả file ví dụ độc lập, sau đó xác nhận đoạn trích và cách tô nổi bật trong HTML.

## 7. Khi dấu `:` đặc biệt hữu ích

Một số định dạng không cho phép đặt comment sau cùng một dòng dữ liệu. Ví dụ file `.properties` chỉ dùng comment bắt đầu từ đầu dòng bằng `#`. Với snippet có `lang="properties"`, dùng dấu `:` ở cuối dòng comment điều khiển:

~~~java
/**
 * {@snippet lang="properties" :
 *     # @highlight substring="localhost" :
 *     service.host=localhost
 *     service.port=8080
 * }
 */
public class PropertiesHighlightDoc {
}
~~~

Kết quả văn bản trong Javadoc:

~~~properties
service.host=localhost
service.port=8080
~~~

Chỉ `localhost` trên dòng `service.host` được làm nổi bật. Dấu `:` chuyển tác động của markup comment sang **dòng tiếp theo**, phù hợp với cú pháp `.properties`. Khi chèn markup vào snippet của định dạng khác, hãy dùng ký hiệu comment đúng với định dạng đó; Java thường dùng `//`.

Dấu `:` có thể dùng cho comment của markup tag khác trong snippet; riêng trong bài này, nó giúp xác định đúng **dòng được tô nổi bật** mà không sửa nội dung của dòng dữ liệu.

## 8. Những lỗi thường gặp và cách sửa

| Vấn đề | Hiện tượng hoặc nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Ghi `// @highlight` trên dòng riêng nhưng quên `:`. | Dòng dưới không tự nhận chỉ dẫn vì mặc định comment tác động lên chính dòng chứa nó. | Đặt comment ở cuối dòng cần tô, hoặc thêm `:`. |
| Muốn nhấn tên biến `count` nhưng dùng `substring="c"`. | Nhiều phần không liên quan có thể được chọn. | Chọn chuỗi đủ cụ thể hoặc dùng `regex`. |
| Muốn khớp riêng `id` nhưng dùng `substring="id"`. | Có thể khớp cả chữ `id` nằm trong tên dài hơn. | Dùng regex với ranh giới phù hợp, rồi kiểm tra kết quả. |
| Viết `regex='error+'` để tìm cả `error` lẫn `errors`. | Dấu `+` chỉ lặp ký tự `r` trước nó; không biểu thị hậu tố tùy chọn `s`. | Dùng mẫu phù hợp như `errors?`. |
| Dùng `region` nhưng quên `@end`. | Vùng không có cặp kết thúc hợp lệ; Javadoc có thể báo lỗi. | Đóng region ngay sau dòng cuối cần tác động. |
| Dùng `@start region="x"` và nghĩ toàn bộ vùng mặc nhiên được tô nổi bật. | `@start` chỉ đánh dấu vùng, tự nó không yêu cầu tô nổi bật. | Đặt `@highlight` với phạm vi và thuộc tính cần thiết. |
| Dùng `@highlight` để làm biến `count` có giá trị khác. | `@highlight` chỉ thay đổi cách hiển thị trong tài liệu. | Muốn đổi hành vi thực thi phải sửa mã Java; muốn đổi chữ hiển thị trong snippet thì xem `@replace`. |
| Chọn `type` không hợp lệ. | `javadoc` có thể báo lỗi về markup. | Chỉ dùng `bold`, `italic`, `highlighted`. |
| Đọc source và mặc định hiệu ứng hiển thị đã đúng. | Regex, vùng hoặc stylesheet có thể khác mong đợi. | Sinh Javadoc và xem trang thực tế. |

Về chất lượng tài liệu: chỉ làm nổi bật đúng điểm cần truyền đạt. Nếu tất cả các dòng đều được nhấn mạnh, người đọc khó biết đâu là thao tác quan trọng; với đoạn dài, cân nhắc giới hạn vùng và dùng `substring`/`regex` cụ thể.

## 9. Thực hành kiểm tra bằng `javadoc`

Tạo file `HighlightDoc.java` chứa mã sau:

~~~java
/**
 * Ví dụ minh họa cách chọn đoạn cần nhấn mạnh.
 *
 * {@snippet :
 *     int retryCount = 3; // @highlight substring="retryCount" type="bold"
 *     int delayMs = 100;   // @highlight
 *     System.out.println(retryCount);
 * }
 */
public class HighlightDoc {
}
~~~

Trong terminal ở thư mục chứa file, chạy:

~~~bash
javadoc -d docs HighlightDoc.java
~~~

Sau đó mở `docs/HighlightDoc.html`. Hãy đối chiếu ba điều:

1. Dòng `int retryCount = 3;` còn nguyên văn, chữ `retryCount` được làm nổi bật kiểu `bold`.
2. Dòng `int delayMs = 100;` được làm nổi bật toàn dòng.
3. Dòng `System.out.println(retryCount);` không được tô nổi bật vì hai markup tag ở trên chỉ tác động vào dòng chứa chính chúng.

Đồng thời kiểm tra đoạn mã trên trang HTML không còn các comment `// @highlight ...`. Đây là **bằng chứng trực tiếp** rằng markup comment chỉ hướng dẫn cách trình bày.

Muốn kiểm tra external snippet ở mục 6, đặt hai file đúng cấu trúc đã chỉ ra rồi sinh:

~~~bash
javadoc -d docs HighlightDoc.java
~~~

Trong file này, thay nội dung `HighlightDoc.java` bằng phiên bản **external** ở mục 6 trước khi chạy, để tránh khai báo trùng lớp. Để kiểm tra tính biên dịch của file ví dụ riêng, có thể dùng:

~~~bash
javac snippet-files/CounterExample.java
~~~

Việc sinh Javadoc và việc biên dịch Java phục vụ **hai kiểm tra độc lập**: tài liệu phải hiển thị đúng phần cần nhấn mạnh, còn mã nguồn ví dụ nên hợp lệ nếu được thiết kế thành file Java hoàn chỉnh.

## 10. Câu hỏi tự kiểm tra

### Câu 1 — Dòng nào được nhấn?

~~~java
int retries = 2; // @highlight
int delay = 100;
~~~

**Đáp án:** Chỉ dòng `int retries = 2;` được làm nổi bật toàn bộ; dòng `delay` không có chỉ dẫn nên không được tô.

### Câu 2 — Mấy vị trí được nhấn?

~~~java
String codeText = "code=" + code; // @highlight substring="code"
~~~

**Đáp án:** Có ba lần xuất hiện chuỗi `code` trong dòng này: ở `codeText`, trong `"code="` và ở biến `code`. Cả ba đều được đánh dấu; `substring` không phân biệt ngữ nghĩa của tên biến với chuỗi ký tự.

### Câu 3 — Region có tên hoạt động thế nào?

~~~java
// @highlight region="calc" regex='value[0-9]+' :
int value1 = 1;
int value2 = 2;
// @end region="calc"
int value3 = 3;
~~~

**Đáp án:** `value1` và `value2` được tô nổi bật. Dòng cuối chứa `value3` nằm ngoài region `calc` nên không bị tác động. Marker mở/đóng không được đưa vào khối mã hiển thị.

### Câu 4 — Khác nhau giữa `@highlight` và `@replace`?

**Đáp án:** `@highlight` nhấn mạnh phần văn bản nhưng giữ nguyên nội dung chữ hiển thị. `@replace` thay thế một phần chữ trong **đầu ra hiển thị** của snippet. Cả hai đều không tự sửa file nguồn Java.

## Tổng kết

- `@highlight` là **markup tag của Javadoc snippet**, được giới thiệu từ Java 18 và còn được hỗ trợ trong JDK hiện đại.
- Không có `substring`/`regex` thì nhấn **toàn dòng**; có `substring` thì nhấn các chuỗi nguyên văn; có `regex` thì nhấn các phần khớp mẫu.
- `type` chọn loại nhấn mạnh: `bold`, `italic`, `highlighted`.
- Phạm vi mặc định là **một dòng**. `region` kết hợp `@end` cho phép làm nổi bật **nhiều dòng**; dấu `:` chuyển chỉ dẫn sang dòng kế tiếp.
- Hãy kiểm tra tài liệu HTML do `javadoc` sinh ra, vì mã nguồn chỉ chứa chỉ dẫn, chưa thể hiện trực quan kiểu nhấn mạnh.

## Nguồn tham khảo chính thức

- [Oracle — JavaDoc Documentation Comment Specification, JDK 26, mục Snippet/Highlighting](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html#snippet): cú pháp và phạm vi của `@highlight`, `substring`, `regex`, `region`, `type`.
- [Oracle — JavaDoc Guide: Snippets, JDK 26](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): ví dụ inline/external, xử lý comment, dấu `:` và vùng.
- [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): nguồn gốc của `{@snippet}` từ Java 18.
