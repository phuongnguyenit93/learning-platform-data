# Thuộc tính lang: nhận diện Java, properties và giới hạn hỗ trợ markup theo ngôn ngữ

## 1. Mục tiêu và bối cảnh

JEP 413 đưa thẻ `{@snippet ...}` vào Javadoc từ **JDK 18** và tính năng này vẫn được hỗ trợ trên các JDK hiện đại. Snippet không chỉ chứa mã Java. Tài liệu API cũng có thể trình bày tệp cấu hình `.properties`, JSON, XML, HTML hoặc văn bản có cấu trúc khác.

Thuộc tính `lang` giúp Standard Doclet nhận biết loại nội dung snippet. Thông tin này có hai vai trò cần phân biệt:

1. Giúp Javadoc xác định kiểu comment có thể chứa **markup comment** như `@highlight`, `@link`, `@replace` và chỉ thị vùng.
2. Được chuyển tiếp vào HTML sinh ra để các công cụ khác có thể sử dụng; khi bật tô màu cú pháp, giá trị này còn giúp chọn bộ tô màu phù hợp.

Hai vai trò trên không đồng nghĩa. Một ngôn ngữ có thể được tô màu cú pháp nhưng không có cú pháp markup comment được Standard Doclet nhận diện.

Sau bài học, bạn có thể:

- Chọn `lang="java"` cho mã Java và `lang="properties"` cho cấu hình Java Properties.
- Hiểu giá trị mặc định của `lang` trong inline, external và hybrid snippet.
- Viết markup comment đúng cú pháp `//` của Java và `#` của Properties.
- Biết vì sao markup comment gắn cuối dòng không hoạt động trong tệp Properties.
- Phân biệt nhận diện markup comment với tính năng syntax highlighting cho JSON, HTML và XML.
- Chọn cách dùng region hoặc snippet không markup khi ngôn ngữ không hỗ trợ kiểu comment phù hợp.

## 2. Thuộc tính lang có ý nghĩa gì?

`lang` là một thuộc tính của thẻ snippet, được viết theo dạng `name=value`:

~~~java
/**
 * Ví dụ Java:
 *
 * {@snippet lang="java" :
 * String greeting = "Hello";
 * System.out.println(greeting);
 * }
 */
~~~

Giá trị của `lang` nhận diện loại nội dung. Với Standard Doclet:

- `java` là giá trị mặc định của **inline snippet**.
- Với **external snippet** hoặc **hybrid snippet**, giá trị mặc định được suy ra từ phần mở rộng của tệp chứa nội dung, chẳng hạn `.java` hoặc `.properties`.
- `lang` có thể được khai báo tường minh để người đọc và công cụ xử lý hiểu chính xác loại nội dung.
- Giá trị thuộc tính cũng được chuyển qua HTML sinh ra; công cụ khác có thể đọc nó để phân tích hoặc trình bày snippet.

Ví dụ inline snippet Java không ghi `lang` vẫn được hiểu là Java:

~~~java
/**
 * {@snippet :
 * int count = 3;
 * System.out.println(count);
 * }
 */
~~~

Tuy nhiên, khi tài liệu có nhiều loại snippet, nên khai báo `lang` rõ ràng. Điều đó giúp người đọc nhận biết ngay một khối là mã Java hay cấu hình Properties.

### Cú pháp giá trị thuộc tính

Giá trị có thể đặt trong dấu nháy đơn hoặc nháy kép; giá trị đơn giản có thể không cần dấu nháy:

~~~java
{@snippet lang="java" :
    System.out.println("Java");
}

{@snippet lang='properties' :
    app.name=inventory
}

{@snippet lang=java :
    System.out.println("Java");
}
~~~

Thuộc tính snippet **không hỗ trợ escape sequence bên trong giá trị**. Vì vậy, hãy dùng giá trị ngắn, rõ nghĩa như `java`, `properties` hoặc `json`; tránh cố gắng nhúng dấu nháy bằng cách escape.

## 3. Java: markup comment dùng dấu //

Với `lang="java"`, Standard Doclet nhận diện comment một dòng của Java là nơi đặt markup comment. Các chỉ thị này bắt đầu bằng `@`, ví dụ `@highlight`, `@link`, `@replace`, `@start` và `@end`.

Markup comment có thể đặt cuối dòng mã để áp dụng cho chính dòng đó:

~~~java
/**
 * {@snippet lang="java" :
 * String status = "READY"; // @highlight substring="READY"
 * System.out.println(status);
 * }
 */
~~~

Comment `// @highlight` không xuất hiện trong khối mã được sinh ra. Javadoc giữ lại câu lệnh và áp dụng hiệu ứng đánh dấu vào phần văn bản được chọn.

Nếu markup comment kết thúc bằng dấu hai chấm, nó áp dụng cho **dòng kế tiếp**:

~~~java
/**
 * {@snippet lang="java" :
 * // @highlight substring="create" :
 * String key = EventKeys.create("order", 42);
 * System.out.println(key);
 * }
 */
~~~

Cách viết này hữu ích khi dòng mã không tiện đặt comment cuối dòng hoặc khi markup có nhiều tham số. Có thể đặt nhiều markup tag trong cùng một comment nếu cần.

### Ví dụ dùng region trong Java

~~~java
/**
 * {@snippet lang="java" :
 * // @start region=validation
 * if (quantity <= 0) {
 *     throw new IllegalArgumentException("quantity must be positive");
 * }
 * // @end region=validation
 * }
 */
~~~

`@start region=validation` và `@end region=validation` xác định vùng mã. Markup comment bị loại khỏi nội dung hiển thị; các câu lệnh bên trong vùng vẫn được giữ nguyên.

Có thể dùng `region` để giới hạn phạm vi của một chỉ thị, ví dụ chỉ đánh dấu một từ trong nhiều dòng thay vì thêm comment vào từng dòng.

### Giới hạn với Java text block

Comment `//` không thể đặt bên trong nội dung của text block để làm markup comment. Trong text block, các ký tự `//` là dữ liệu văn bản, không phải comment Java.

Nếu cần đánh dấu toàn bộ một text block, đặt chỉ thị vùng bên ngoài nó:

~~~java
/**
 * {@snippet lang="java" :
 * // @start region=json-example
 * String json = """
 *     {
 *       "status": "ready"
 *     }
 *     """;
 * // @end region=json-example
 * }
 */
~~~

Dùng region giúp tránh chèn comment vào giữa dữ liệu text block. Khi cần đánh dấu một phần cụ thể bên trong text block, hãy cân nhắc chia ví dụ thành phần nhỏ hơn hoặc chọn cách trình bày khác phù hợp; không thêm `// @highlight` vào chuỗi JSON rồi mong Javadoc xem đó là comment.

## 4. Properties: markup comment phải đứng ở đầu dòng

Tệp Java Properties có cú pháp comment khác Java. Các dòng comment bắt đầu bằng ký tự `#` hoặc `!` ở vị trí đầu dòng sau khoảng trắng. Không có comment cuối dòng theo kiểu `key=value # comment`.

Standard Doclet nhận diện `properties` để hiểu markup comment theo kiểu comment dòng của định dạng này. Cách viết được tài liệu Javadoc minh họa là dùng dấu `#`:

~~~text
{@snippet lang="properties" :
# @highlight substring="server.port" :
server.port=8080
server.host=localhost
}
~~~

Comment markup nằm trên một dòng riêng và bắt đầu bằng `#`. Dấu hai chấm cuối comment khiến chỉ thị áp dụng cho dòng ngay sau nó. Khi tạo HTML, dòng comment không xuất hiện trong snippet.

### Vì sao không đặt markup ở cuối dòng cấu hình?

Cách sau **không phải** cú pháp markup comment hợp lệ của Properties:

~~~properties
server.port=8080 # @highlight substring="8080"
~~~

Trong định dạng Properties, dấu `#` chỉ mở comment khi nó là ký tự đầu tiên không phải khoảng trắng trên dòng. Ở cuối dòng `server.port=8080 # ...`, dấu `#` thuộc phần giá trị của thuộc tính, không mở comment. Vì vậy, Javadoc không coi đoạn đó là markup comment; nó có thể xuất hiện nguyên văn trong nội dung hoặc làm sai giá trị cấu hình.

Hãy viết thành hai dòng:

~~~properties
# @highlight substring="8080" :
server.port=8080
~~~

Cũng cần lưu ý rằng `!` là ký hiệu comment hợp lệ trong một tệp Properties, nhưng ví dụ markup nên dùng dạng `# @...` được tài liệu Standard Doclet minh họa rõ ràng. Đừng giả định mọi ký hiệu comment của một định dạng đều được mọi công cụ markup xử lý giống nhau.

### Ví dụ region cho một nhóm cấu hình

~~~properties
{@snippet lang="properties" :
# @start region=server
server.port=8080
server.host=localhost
server.timeout=5000
# @end region=server
}
~~~

Ở đây `@start` và `@end` cũng nằm trong comment Properties. Chúng phải đứng ở đầu dòng sau khoảng trắng, giống các markup comment khác.

## 5. External snippet cho tệp .properties

Với tệp cấu hình thật, nên đặt snippet ở tệp ngoài để có thể tái sử dụng và giữ cấu trúc gần với tệp cấu hình trong dự án.

Ví dụ cấu trúc:

~~~text
src/main/java/
└── example/
    ├── ServerConfig.java
    └── snippet-files/
        └── application.properties
~~~

Tệp `src/main/java/example/snippet-files/application.properties`:

~~~properties
# @start region=server
server.port=8080
server.host=localhost
server.timeout=5000
# @end region=server
~~~

Trong Javadoc của lớp `ServerConfig`:

~~~java
/**
 * Cấu hình máy chủ mẫu:
 *
 * {@snippet file="application.properties" lang="properties" region=server}
 */
public class ServerConfig {
}
~~~

Vì phần mở rộng là `.properties`, Standard Doclet có thể suy ra ngôn ngữ cho external snippet. Khai báo thêm `lang="properties"` làm ý định rõ ràng và bảo đảm markup comment được diễn giải theo cú pháp Properties.

Có thể bỏ `lang` trong ví dụ trên nếu muốn dùng cơ chế suy ra từ phần mở rộng:

~~~java
/**
 * {@snippet file="application.properties" region=server}
 */
~~~

Tuy vậy, nếu tệp có phần mở rộng tùy chỉnh hoặc nội dung không thể hiện rõ định dạng, hãy khai báo `lang` tường minh.

Các tệp external snippet có thể đặt trong thư mục `snippet-files` cùng package hoặc trong đường dẫn bổ sung được truyền qua tùy chọn `--snippet-path`. Đường dẫn của thuộc tính `file` được giải quyết tương đối theo một trong các vị trí đó.

## 6. Ngôn ngữ khác: syntax highlighting không đồng nghĩa markup comment

Snippet có thể chứa nội dung ngoài Java và Properties. Thuộc tính `lang` còn có thể được chuyển qua HTML để công cụ khác xử lý. Trên JDK 27, tùy chọn `--syntax-highlight` hỗ trợ tô màu cú pháp cho các định dạng:

- Java
- Properties
- JSON
- HTML
- XML

Ví dụ khai báo snippet JSON:

~~~java
/**
 * Phản hồi mẫu:
 *
 * {@snippet lang="json" :
 * {
 *   "status": "ready",
 *   "count": 3
 * }
 * }
 */
~~~

Với `lang="json"`, Javadoc có thể gắn thông tin ngôn ngữ cho khối mã để tính năng syntax highlighting xử lý khi được bật. Tuy nhiên, JSON chuẩn không có cú pháp comment; không thể đặt `// @highlight` hoặc `# @highlight` vào JSON mà vẫn giữ nội dung JSON hợp lệ.

Tương tự:

| Giá trị lang | Vai trò có thể có | Lưu ý về markup comment |
| --- | --- | --- |
| `java` | Nhận diện Java và cú pháp comment `//`. | Có thể dùng markup comment cuối dòng hoặc trên dòng riêng. |
| `properties` | Nhận diện cấu hình Properties và comment dòng `#`. | Comment phải bắt đầu ở ký tự đầu tiên không phải khoảng trắng; không có comment cuối dòng. |
| `json` | Nhận diện ngôn ngữ cho công cụ tô màu cú pháp. | JSON không có comment; không chèn markup comment vào dữ liệu. |
| `html` | Nhận diện định dạng HTML cho tô màu cú pháp. | Comment HTML `<!-- ... -->` không phải kiểu end-of-line comment Java/Properties mà Standard Doclet dùng để nhận diện markup. |
| `xml` | Nhận diện định dạng XML cho tô màu cú pháp. | Không giả định comment XML sẽ được diễn giải như markup comment của snippet. |
| `text` | Hiển thị văn bản thuần; có thể dùng để tắt syntax highlighting. | Không có cú pháp markup comment được nhận diện sẵn. |

**Điểm phân biệt quan trọng:** Standard Doclet ghi nhận `java` và `properties` là các giá trị được hỗ trợ để suy ra kiểu comment dòng cho markup. `--syntax-highlight` hỗ trợ thêm JSON, HTML và XML cho việc tô màu. Điều này không có nghĩa markup comment `@highlight` hoạt động trong mọi ngôn ngữ được tô màu.

Nếu nội dung thuộc ngôn ngữ không có kiểu comment dòng được Standard Doclet nhận diện, hãy trình bày snippet mà không chèn các comment giả. Nếu cần lựa chọn vùng hoặc đánh dấu nội dung, hãy cân nhắc tách dữ liệu, chuẩn bị một tệp ví dụ phù hợp hơn hoặc kiểm tra với công cụ/doclet khác có hỗ trợ cú pháp đó.

### Bật syntax highlighting

Trên JDK 27, có thể yêu cầu Javadoc bật tô màu cú pháp bằng tùy chọn:

~~~sh
javadoc --syntax-highlight -d build/docs src/main/java/example/ServerConfig.java
~~~

`lang` được dùng để xác định ngôn ngữ cho snippet; với external snippet, phần mở rộng tệp có thể cung cấp giá trị mặc định. Nếu muốn tắt tô màu cho một khối văn bản, tài liệu lệnh Javadoc cho phép dùng ngôn ngữ `text`.

Tùy chọn này chỉ ảnh hưởng cách hiển thị mã. Nó không xác thực cú pháp JSON, XML, Properties, không chạy ví dụ và không tự bổ sung khả năng phân tích markup comment cho các ngôn ngữ khác.

## 7. Cách chọn lang và markup trong thực tế

Hãy quyết định theo nội dung thực sự cần trình bày:

1. **Đoạn mã Java:** dùng `lang="java"`. Đặt `@highlight`, `@link` hoặc `@replace` trong comment `//`.
2. **Tệp cấu hình Java Properties:** dùng `lang="properties"`. Đặt markup trong comment `#` ở đầu dòng; dùng dấu hai chấm để áp dụng cho dòng tiếp theo.
3. **JSON, XML, HTML:** khai báo đúng ngôn ngữ để hỗ trợ syntax highlighting, nhưng không thêm comment Java hoặc Properties vào nội dung.
4. **Văn bản không có ngôn ngữ cụ thể:** dùng `lang="text"` nếu muốn hiển thị nguyên văn và không cần tô màu.
5. **Tệp ngoài có phần mở rộng không rõ ràng:** đặt `lang` tường minh thay vì phụ thuộc vào việc suy ra từ tên tệp.

Một ví dụ có thể được trình bày trong tài liệu mà không phải là tệp chạy được. Nếu snippet được dùng để minh họa hợp đồng API hoặc cấu hình triển khai, hãy kiểm tra nó bằng công cụ phù hợp: biên dịch/chạy mã Java, nạp Properties bằng API tương ứng hoặc xác thực JSON/XML bằng parser. Javadoc chỉ trình bày snippet, không thực hiện các bước kiểm tra đó.

### Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Markup comment xuất hiện nguyên văn trong snippet Java. | Viết sai cú pháp `//` hoặc tên markup tag không hợp lệ. | Kiểm tra comment và tên tag như `@highlight`, `@link`. |
| `@highlight` không được áp dụng trong Properties. | Đặt comment ở cuối dòng `key=value`. | Đưa `# @highlight ... :` lên một dòng riêng trước dòng cần đánh dấu. |
| Markup comment làm hỏng JSON. | Thêm comment `//` vào nội dung JSON. | Giữ JSON hợp lệ và không chèn markup comment. |
| HTML/XML comment không được xử lý như markup mong muốn. | Nhầm syntax highlighting với nhận diện comment markup. | Dùng snippet không markup hoặc kiểm tra hỗ trợ của doclet/công cụ riêng. |
| Tệp external hiển thị như Java dù là Properties. | Phần mở rộng không phản ánh đúng nội dung hoặc khai báo `lang` sai. | Đặt `lang="properties"` tường minh. |
| Mã được tô màu nhưng ví dụ không đúng. | Syntax highlighting chỉ trình bày, không xác thực hoặc thực thi. | Dùng parser, compiler hoặc test tương ứng. |

## 8. Bài tập thực hành

### Bài tập 1: Chọn lang

Chọn giá trị `lang` phù hợp cho từng nội dung:

1. Một phương thức Java gọi `Files.readString(path)`.
2. Tệp cấu hình có các dòng `server.port=8080` và `server.host=localhost`.
3. Phản hồi API dạng JSON có `status` và `count`.
4. Một đoạn văn bản thuần cần hiển thị nguyên văn.

**Đáp án:** (1) `java`; (2) `properties`; (3) `json`; (4) `text`. Lựa chọn này xác định cách nhận diện hoặc trình bày ngôn ngữ; nó không tự kiểm tra nội dung.

### Bài tập 2: Sửa markup trong Properties

Đoạn sau không đánh dấu được dòng cấu hình theo cách mong muốn:

~~~properties
server.port=8080 # @highlight substring="8080"
~~~

Hãy chuyển markup comment lên dòng riêng, đặt dấu `#` ở đầu dòng và thêm dấu hai chấm để áp dụng cho dòng kế tiếp. Sau đó sinh Javadoc và xác nhận comment không xuất hiện trong khối mã.

### Bài tập 3: Tạo snippet cấu hình external

Tạo tệp `application.properties` có một vùng `region=database` chứa các thuộc tính `database.url`, `database.username` và `database.pool-size`. Thêm một markup comment `# @highlight ... :` để đánh dấu dòng URL. Tham chiếu vùng bằng:

~~~java
/**
 * {@snippet file="application.properties" lang="properties" region=database}
 */
~~~

Kiểm tra rằng vùng hiển thị đúng, markup comment được ẩn và các giá trị cấu hình không bị thay đổi.

### Bài tập 4: Phân biệt markup với syntax highlighting

Tạo snippet JSON có `lang="json"` và bật `--syntax-highlight`. Thử thêm comment `// @highlight` vào nội dung. Giải thích vì sao đây không phải JSON hợp lệ và tại sao việc tô màu cú pháp không làm comment trở thành markup comment.

**Tự kiểm:** khai báo đúng lang; Java dùng `//`; Properties dùng `#` ở đầu dòng; JSON không chứa comment; phân biệt khả năng tô màu với khả năng phân tích markup; kiểm tra HTML sinh ra.

## 9. Ghi nhớ

- **`lang` nhận diện loại nội dung snippet.** Inline snippet mặc định là `java`; external/hybrid snippet mặc định suy ra từ phần mở rộng của tệp.
- **Standard Doclet nhận diện `java` và `properties` cho markup comment.** Java dùng `//`; Properties dùng comment dòng `#` ở đầu dòng.
- **Properties không hỗ trợ comment cuối dòng.** Markup phải đứng riêng và có thể dùng dấu hai chấm để áp dụng cho dòng tiếp theo.
- **Syntax highlighting và markup comment là hai chức năng khác nhau.** JDK 27 hỗ trợ tô màu Java, Properties, JSON, HTML và XML; điều đó không có nghĩa tất cả định dạng đều có cú pháp markup comment được nhận diện.
- **Javadoc chỉ trình bày snippet.** Dùng compiler, parser hoặc test phù hợp để kiểm chứng nội dung khi nó có ý nghĩa đối với API hoặc cấu hình thực tế.

## Tài liệu chính thống

- [Oracle – JDK 26 Javadoc Snippets Guide, mục Attributes, Markup Comments và Limitations of End-of-Line Comments](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle – JDK 27 The javadoc Command, tùy chọn --syntax-highlight](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html).
- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).

