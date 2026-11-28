# External snippet với class: tham chiếu tệp nguồn Java theo tên lớp

## 1. Mục tiêu và bối cảnh

JEP 413 đưa thẻ `{@snippet ...}` vào Javadoc từ **JDK 18**. Tính năng này tiếp tục được hỗ trợ trên JDK hiện đại, giúp tài liệu API trình bày ví dụ mã có thể tái sử dụng, chọn vùng và kiểm chứng riêng. Với external snippet, nội dung được đặt trong tệp nguồn Java bên ngoài comment tài liệu. Thuộc tính `class` cho phép tham chiếu tệp đó bằng tên lớp.

Bài học tập trung vào cách dùng `class` để Standard Doclet tìm đúng tệp Java, cách tổ chức thư mục, cách chọn vùng `region` và cách kiểm tra ví dụ. Sau bài này, bạn có thể:

- Giải thích `class` trỏ đến nguồn Java bên ngoài như thế nào.
- Viết thẻ `{@snippet class=HelloWorld}` và xác định tệp tương ứng.
- Tổ chức nguồn trong `snippet-files` cùng package với lớp có comment Javadoc.
- Dùng `--snippet-path` khi lưu nguồn snippet ở cây thư mục riêng.
- Kết hợp `class` với `region` và markup comment.
- Phân biệt tham chiếu theo tên lớp với tham chiếu theo đường dẫn bằng `file`.
- Biên dịch/chạy ví dụ độc lập và kiểm tra HTML do Javadoc tạo ra.

Bài này thuộc chương **Javadoc snippet** của module `JAVA_VERSION_JAVA18`. Module tập trung vào các thay đổi từ Java 18 vẫn hữu ích trên JDK hiện đại; `{@snippet}` là tính năng tài liệu API được giới thiệu ở JDK 18, không phải API runtime dùng trong ứng dụng.

## 2. class tham chiếu đến tệp nguồn Java

Một external snippet có thể tham chiếu đến nguồn bằng tên lớp:

~~~java
/**
 * Chương trình minh họa:
 *
 * {@snippet class=HelloWorld}
 */
public class Main {
}
~~~

Standard Doclet dùng giá trị `class` để tìm tệp Java có tên tương ứng. Với ví dụ trên, tệp nguồn là `HelloWorld.java` trong vị trí snippet được cấu hình.

Đây là cơ chế **tìm tệp nguồn để trích nội dung**, không phải tra cứu một lớp đã biên dịch trong classpath. Javadoc không nạp lớp, không dùng reflection và không chạy phương thức `main` khi xử lý `class=HelloWorld`. Tệp `.java` có thể được biên dịch riêng nếu muốn kiểm tra ví dụ.

Ví dụ nội dung tệp:

~~~java
public class HelloWorld {
    /**
     * Chương trình Hello World.
     */
    public static void main(String... args) {
        System.out.println("Hello, World!");
    }
}
~~~

Thẻ external snippet không cần dấu hai chấm, dòng mới và phần thân inline. Standard Doclet đọc tệp nguồn, xử lý markup nếu có và trình bày nội dung trong HTML.

### Quy tắc đặt tên cơ bản

Trong cách dùng thông dụng được tài liệu Javadoc minh họa:

- `class` nhận tên lớp Java, ví dụ `HelloWorld`.
- Tệp nguồn tương ứng có tên `HelloWorld.java`.
- Không ghi phần mở rộng `.java` trong giá trị `class`.
- Không đặt đường dẫn thư mục vào `class`; vị trí tệp được xác định qua cấu trúc thư mục snippet.
- Tên lớp nên là tên lớp cấp cao nhất rõ ràng, phù hợp với tên tệp.

Ví dụ:

| Thuộc tính | Tệp nguồn tương ứng |
| --- | --- |
| `class=HelloWorld` | `HelloWorld.java` |
| `class=ExternalSnippets` | `ExternalSnippets.java` |
| `class=OrderExamples` | `OrderExamples.java` |

Dùng tên lớp đơn giản như trong hướng dẫn Standard Doclet. Nếu cần chỉ định trực tiếp đường dẫn hoặc tệp không phải Java, dùng `file`.

## 3. Đặt tệp trong snippet-files cùng package

Cách mặc định là tạo thư mục `snippet-files` bên trong thư mục package chứa tệp nguồn có comment `{@snippet}`.

Ví dụ, lớp tài liệu là `p.Main`:

~~~text
src/
└── p/
    ├── Main.java
    └── snippet-files/
        └── HelloWorld.java
~~~

Trong `src/p/Main.java`:

~~~java
package p;

/**
 * Ví dụ chương trình:
 *
 * {@snippet class=HelloWorld}
 */
public class Main {
}
~~~

Trong `src/p/snippet-files/HelloWorld.java`:

~~~java
public class HelloWorld {
    public static void main(String... args) {
        System.out.println("Hello, World!");
    }
}
~~~

Ở đây:

- `Main.java` là source file có comment Javadoc.
- `snippet-files` là thư mục dành cho các tệp snippet của package `p`.
- `HelloWorld.java` là tệp Java mà `class=HelloWorld` tham chiếu.
- Tên thư mục `snippet-files` là quy ước của Standard Doclet, không phải tên package Java.

Standard Doclet tự tìm nguồn theo cấu trúc này. Với cách tổ chức mặc định, không cần thêm tùy chọn tìm kiếm riêng cho snippet.

### Package khác nhau có snippet-files riêng

Nếu tài liệu có nhiều package, mỗi package có thể có thư mục snippet riêng nằm cạnh source của package đó:

~~~text
src/
├── p/
│   ├── Main.java
│   └── snippet-files/
│       └── HelloWorld.java
└── q/
    ├── OrderService.java
    └── snippet-files/
        └── OrderExamples.java
~~~

Comment trong `p.Main` có thể tham chiếu `class=HelloWorld`; comment trong `q.OrderService` có thể tham chiếu `class=OrderExamples`. Đặt tệp đúng package giúp nguồn ví dụ đi cùng phần tài liệu sử dụng nó và dễ bảo trì.

## 4. Dùng --snippet-path khi không thể đặt thư mục cục bộ

Một số hệ thống build không xử lý tốt thư mục `snippet-files` nằm bên trong cây package source. Chúng có thể quét nhầm thư mục này như một phần của package hierarchy. Khi đó, chuyển các tệp snippet sang cây thư mục riêng và truyền gốc tìm kiếm qua `--snippet-path`.

Ví dụ:

~~~text
project/
├── src/
│   └── p/
│       └── Main.java
└── snippet-files/
    └── HelloWorld.java
~~~

Thẻ trong `Main.java` vẫn tham chiếu theo tên lớp:

~~~java
package p;

/**
 * Ví dụ:
 *
 * {@snippet class=HelloWorld}
 */
public class Main {
}
~~~

Tạo tài liệu từ thư mục gốc dự án:

~~~sh
javadoc --snippet-path snippet-files -d build/docs -sourcepath src p
~~~

Trong lệnh này:

- `-sourcepath src` giúp Javadoc tìm source của package `p`.
- `--snippet-path snippet-files` bổ sung thư mục tìm kiếm cho external snippet.
- `class=HelloWorld` vẫn là tên lớp nguồn; nó không biến thành đường dẫn `snippet-files/HelloWorld.java`.

Giá trị `--snippet-path` là thư mục gốc tìm kiếm snippet. Khi dùng đường dẫn này, hãy tổ chức nguồn theo layout được Standard Doclet mong đợi và kiểm tra bằng lệnh Javadoc thực tế của dự án.

### Không dùng đường dẫn máy cá nhân

Tránh gắn đường dẫn tuyệt đối như `C:\Users\...\HelloWorld.java` vào tài liệu. `class` không phải tham số nhận đường dẫn. Hãy đưa tệp vào repository trong `snippet-files` hoặc thư mục tìm kiếm được cấu hình, để máy phát triển và CI cùng tìm được nguồn.

## 5. class và file giải quyết hai nhu cầu khác nhau

Standard Doclet cung cấp hai cách xác định nguồn external:

| Thuộc tính | Cách tham chiếu | Phạm vi |
| --- | --- | --- |
| `class` | Tên lớp Java, ví dụ `class=HelloWorld` | Tệp nguồn Java có tên tương ứng. |
| `file` | Đường dẫn tương đối, ví dụ `file="samples/response.json"` | Java source và các dạng văn bản có cấu trúc khác như Properties, JSON, XML, HTML hoặc text. |

Dùng `class` khi:

- Ví dụ được tổ chức thành một tệp Java có tên lớp rõ ràng.
- Muốn tham chiếu nguồn bằng tên lớp thay vì ghi đường dẫn.
- Tệp có thể biên dịch/chạy độc lập hoặc được dùng trong quy trình kiểm thử Java.
- Tên lớp và tên tệp đã được thống nhất trong dự án.

Dùng `file` khi:

- Nội dung không phải Java, chẳng hạn `application.properties` hoặc `response.json`.
- Muốn chọn một đường dẫn tương đối cụ thể.
- Tên tệp không phù hợp với cách tham chiếu bằng tên lớp.
- Cần tham chiếu tài nguyên dạng text mà không có khai báo lớp.

Ví dụ:

~~~java
/**
 * Nguồn Java:
 * {@snippet class=HelloWorld}
 *
 * Dữ liệu cấu hình:
 * {@snippet file="application.properties"}
 *
 * Phản hồi JSON:
 * {@snippet file="samples/response.json"}
 */
~~~

Không dùng `class` như một cách thay thế cho `file` khi nội dung không phải tệp Java. Ngược lại, `file` vẫn có thể tham chiếu Java source nếu muốn dùng đường dẫn cụ thể.

## 6. Trích vùng mã bằng class và region

Một tệp Java có thể chứa nhiều ví dụ. Nếu chỉ muốn hiển thị một phần, dùng thuộc tính `region` cùng với `class`.

Thẻ trong Javadoc:

~~~java
/**
 * Phần xử lý yêu cầu:
 *
 * {@snippet class=OrderExamples region=validate-order}
 */
~~~

Tệp `snippet-files/OrderExamples.java`:

~~~java
public class OrderExamples {
    public static void main(String[] args) {
        // @start region=validate-order
        int quantity = 3;
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        // @end region=validate-order
    }
}
~~~

Standard Doclet chỉ đưa nội dung nằm trong vùng `validate-order` vào snippet. Các dòng `@start` và `@end` là markup comment nên không xuất hiện trong mã hiển thị.

Một tệp có thể chứa nhiều vùng để tái sử dụng:

~~~java
public class OrderExamples {
    public static void main(String[] args) {
        // @start region=validate-order
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        // @end region=validate-order

        // @start region=create-order
        String orderId = OrderService.create("customer-42");
        System.out.println(orderId);
        // @end region=create-order
    }
}
~~~

Các thẻ tương ứng:

~~~java
/**
 * Kiểm tra dữ liệu:
 * {@snippet class=OrderExamples region=validate-order}
 *
 * Tạo đơn hàng:
 * {@snippet class=OrderExamples region=create-order}
 */
~~~

Nên dùng tên region mô tả mục đích như `validate-order`, `create-order` hoặc `serialize-response`. Tên vùng phải khớp giữa thuộc tính `region` và markup `@start`/`@end`.

### Region lồng nhau và region chồng lấp

Standard Doclet hỗ trợ region lồng nhau. Các vùng chồng lấp nhưng không lồng nhau cần được đặt tên để xác định đúng cặp bắt đầu/kết thúc. Khi nhiều snippet dùng cùng một tệp, tên region rõ nghĩa giúp tránh chọn nhầm đoạn mã.

Không đặt cùng một tên region cho những vùng không liên quan nếu điều đó khiến người đọc không biết thẻ đang trích phần nào. Khi thay đổi tên region trong tệp nguồn, cần cập nhật mọi thuộc tính `region` tham chiếu đến tên cũ.

## 7. Markup comment trong tệp nguồn được tham chiếu bằng class

Markup comment là comment cuối dòng trong ngôn ngữ của snippet, chứa chỉ thị như `@highlight`, `@link`, `@replace`, `@start` và `@end`. Với Java, chúng thường được viết bằng comment `//`.

Ví dụ:

~~~java
public class HelloWorld {
    public static void main(String... args) {
        System.out.println("Hello, World!"); // @highlight substring="Hello"
    }
}
~~~

Thẻ:

~~~java
{@snippet class=HelloWorld}
~~~

Markup comment được Standard Doclet xử lý và loại khỏi nội dung hiển thị. Dòng lệnh vẫn được giữ, phần `Hello` được đánh dấu.

Có thể đặt markup comment trên dòng riêng và kết thúc bằng dấu hai chấm để chỉ thị áp dụng cho dòng kế tiếp:

~~~java
// @highlight substring="println" :
System.out.println("Hello, World!");
~~~

### Markup không thay thế kiểm thử Java

Markup chỉ điều khiển cách trình bày. `@highlight` không xác nhận phương thức có tồn tại; `@link` tạo liên kết tài liệu; `@replace` thay nội dung hiển thị. Chúng không biên dịch, không chạy và không kiểm tra hợp đồng của mã.

Nếu ví dụ dùng một API cụ thể, hãy bảo đảm import, tên lớp, chữ ký phương thức và kết quả mong đợi phù hợp với phiên bản JDK hoặc thư viện mà dự án sử dụng.

## 8. Ví dụ hoàn chỉnh: tham chiếu HelloWorld bằng class

Cấu trúc dự án:

~~~text
project/
└── src/
    └── p/
        ├── Main.java
        └── snippet-files/
            └── HelloWorld.java
~~~

Tệp `src/p/Main.java`:

~~~java
package p;

/**
 * Chương trình mẫu.
 *
 * {@snippet class=HelloWorld}
 */
public class Main {
}
~~~

Tệp `src/p/snippet-files/HelloWorld.java`:

~~~java
public class HelloWorld {
    /**
     * In lời chào ra đầu ra chuẩn.
     */
    public static void main(String... args) {
        System.out.println("Hello, World!");
    }
}
~~~

Sinh Javadoc từ thư mục gốc dự án:

~~~sh
javadoc -d build/docs -sourcepath src p
~~~

Standard Doclet tìm tệp `HelloWorld.java` trong thư mục `snippet-files` tương ứng và đưa nội dung vào trang tài liệu của `p.Main`.

Có thể biên dịch tệp snippet riêng:

~~~sh
javac -d build/classes src/p/snippet-files/HelloWorld.java
~~~

Vì ví dụ `HelloWorld` ở đây không khai báo package, có thể chạy:

~~~sh
java -cp build/classes HelloWorld
~~~

Kết quả:

~~~text
Hello, World!
~~~

Ví dụ trên minh họa một source file độc lập. Trong dự án thực tế, nếu snippet phụ thuộc vào lớp/package của ứng dụng, hãy tổ chức package, import và classpath phù hợp rồi biên dịch bằng cấu hình build tương ứng.

## 9. Quy trình kiểm tra class reference

Khi một snippet không được tìm thấy hoặc hiển thị sai, kiểm tra theo thứ tự:

1. **Xác định lớp có comment Javadoc:** ví dụ `p.Main`.
2. **Xác định thư mục snippet root:** mặc định là `snippet-files` dưới thư mục package chứa source có thẻ.
3. **Kiểm tra tên lớp:** `class=HelloWorld` phải tương ứng với tệp `HelloWorld.java`.
4. **Kiểm tra phạm vi tìm kiếm:** nếu tệp ở cây riêng, truyền đúng `--snippet-path`.
5. **Kiểm tra region:** nếu dùng `region`, tên phải khớp với `@start region=...` và `@end region=...`.
6. **Sinh lại Javadoc:** dùng cùng source path và snippet path như build thực tế.
7. **Kiểm tra HTML:** xác nhận khối mã đúng nội dung, đúng vùng và markup comment đã được xử lý.
8. **Biên dịch/chạy riêng:** dùng `javac` và `java` để kiểm tra ví dụ Java nếu mục tiêu là mã có thể thực thi.

### Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Javadoc không tìm thấy class snippet. | Tệp không ở `snippet-files` đúng package hoặc ngoài `--snippet-path`. | Kiểm tra vị trí nguồn và cấu hình gốc tìm kiếm. |
| `class=HelloWorld` không tìm được tệp. | Tên lớp và tên tệp không khớp. | Dùng tên lớp cấp cao nhất tương ứng với tên tệp Java. |
| Ghi `class=HelloWorld.java` nhưng lỗi. | Thuộc tính `class` nhận tên lớp, không nhận tên tệp có phần mở rộng. | Dùng `class=HelloWorld`. |
| Ghi đường dẫn trong `class` nhưng không được tìm thấy. | `class` không phải thuộc tính đường dẫn. | Dùng `file` nếu cần chỉ định đường dẫn tương đối. |
| Tệp JSON/Properties không được tham chiếu bằng class. | Nội dung không phải nguồn Java có tên lớp. | Dùng `file`. |
| Chỉ hiển thị một phần không đúng. | Tên `region` không khớp hoặc cặp markup sai. | Kiểm tra `@start`, `@end` và thuộc tính region. |
| Snippet hiển thị nhưng không biên dịch. | Javadoc chỉ đọc và trình bày source. | Biên dịch/chạy tệp riêng với dependency và classpath phù hợp. |
| Build tool quét nhầm thư mục snippet. | Công cụ xử lý `snippet-files` như package source. | Dùng cây riêng và `--snippet-path`. |

## 10. Bài tập thực hành

### Bài tập 1: Tạo tham chiếu class cơ bản

Tạo lớp tài liệu `p.Main` và tệp `snippet-files/HelloWorld.java`. Thêm `{@snippet class=HelloWorld}` vào Javadoc. Sinh tài liệu và xác nhận toàn bộ source class được hiển thị.

### Bài tập 2: Trích vùng main

Trong `HelloWorld.java`, đánh dấu vùng `main` quanh phương thức `main` bằng `@start region=main` và `@end region=main`. Thay thẻ bằng `{@snippet class=HelloWorld region=main}`. Kiểm tra kết quả chỉ còn nội dung trong vùng.

### Bài tập 3: Chuyển sang --snippet-path

Di chuyển tệp nguồn snippet ra ngoài package tree. Cấu hình thư mục gốc bằng `--snippet-path` rồi tạo lại Javadoc. Giữ tham chiếu theo tên lớp và xác nhận Standard Doclet tìm được tệp.

### Bài tập 4: So sánh class và file

Với tệp Java `HelloWorld.java`, thử `class=HelloWorld` và `file="HelloWorld.java"`. Ghi lại khác biệt về cách chỉ định nguồn. Sau đó tạo `response.json` và tham chiếu bằng `file`; giải thích vì sao không dùng `class` cho JSON.

### Bài tập 5: Kiểm chứng hành vi

Thêm một phép kiểm tra kết quả vào vùng `main`, ví dụ so sánh đầu ra hoặc ném `AssertionError` nếu giá trị không đúng. Biên dịch và chạy tệp bằng `javac`/`java`. Thay đổi giá trị kỳ vọng để quan sát lỗi kiểm thử, rồi giải thích vì sao bước tạo Javadoc không phát hiện sai lệch đó.

**Tự kiểm:** class value là tên lớp; tên tệp tương ứng có phần mở rộng `.java`; vị trí snippet đúng; region khớp; Javadoc sinh HTML thành công; ví dụ được biên dịch/chạy riêng khi cần.

## 11. Ghi nhớ

- **`class` tham chiếu nguồn Java bằng tên lớp.** Ví dụ `class=HelloWorld` tìm tệp `HelloWorld.java` trong vị trí snippet được cấu hình.
- **`snippet-files` là vị trí mặc định theo package.** Đặt thư mục này bên cạnh source có comment Javadoc.
- **`--snippet-path` bổ sung gốc tìm kiếm.** Dùng khi hệ thống build không thể dùng thư mục snippet-files cục bộ.
- **`region` chọn một phần của tệp Java.** Dùng `@start` và `@end` để đánh dấu vùng có tên.
- **`class` khác `file`.** Class dành cho nguồn Java theo tên lớp; file dùng đường dẫn tương đối và hỗ trợ nội dung không phải Java.
- **Javadoc không biên dịch hay chạy snippet.** Kiểm tra riêng bằng compiler, runtime và test phù hợp.
- **Giữ nguồn ví dụ trong repository và dùng đường dẫn tương đối.** Cấu trúc ổn định giúp tài liệu được sinh lại trên máy khác và trong CI.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle – JDK 26 Javadoc Snippets Guide, mục External Snippets và Basic External Snippet](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, External snippets](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle – JDK 26 The javadoc Command, tùy chọn --snippet-path](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html).

