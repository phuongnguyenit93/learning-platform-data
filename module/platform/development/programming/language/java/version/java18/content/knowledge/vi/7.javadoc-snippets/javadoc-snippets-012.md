# Thư mục snippet-files theo package và phân biệt với thư mục doc-files

## 1. Mục tiêu và bối cảnh

JEP 413 bổ sung thẻ `{@snippet ...}` cho Javadoc từ **JDK 18**. Tính năng này tiếp tục được hỗ trợ trên JDK hiện đại, cho phép tài liệu API lấy ví dụ từ tệp bên ngoài, chọn vùng mã và áp dụng markup comment. Khi dùng external snippet, vị trí lưu tệp rất quan trọng: Standard Doclet cần biết đâu là nguồn snippet để đọc và đâu là tài nguyên tài liệu cần đưa vào website.

Hai thư mục có tên gần giống nhưng có mục đích khác nhau:

- `snippet-files` chứa **nguồn nội dung cho thẻ `{@snippet}`**. Javadoc tìm và xử lý các tệp ở đây để tạo khối mã trong HTML.
- `doc-files` chứa **tài liệu và tài nguyên phụ trợ của package**, chẳng hạn hình ảnh, trang HTML/Markdown và tệp có thể liên kết từ nội dung Javadoc.

Sau bài học, bạn có thể:

- Đặt đúng hai thư mục bên cạnh source của package.
- Giải thích Standard Doclet tìm external snippet trong `snippet-files` như thế nào.
- Phân biệt việc Javadoc xử lý snippet với việc đưa tài nguyên `doc-files` vào website tài liệu.
- Dùng `--snippet-path` khi build tool không xử lý được thư mục snippet cục bộ.
- Chọn `file`, `class` và `region` theo đúng nguồn nội dung.
- Kiểm tra liên kết, hình ảnh và snippet sau khi chạy Javadoc.

Bài thuộc chương **Javadoc snippet** của module `JAVA_VERSION_JAVA18`. Nội dung chỉ tập trung vào cách tổ chức nguồn tài liệu vẫn áp dụng trên JDK hiện đại; `snippet-files` và `doc-files` đều là cơ chế của Standard Doclet, không phải API runtime của ứng dụng.

## 2. Hai thư mục nằm cạnh source của package

Giả sử package `p` có lớp `Main` chứa comment Javadoc. Cấu trúc thư mục điển hình:

~~~text
src/
└── p/
    ├── Main.java
    ├── doc-files/
    │   ├── architecture.png
    │   └── usage.html
    └── snippet-files/
        ├── Snippets.java
        └── application.properties
~~~

Cả hai thư mục đều nằm dưới thư mục package `p`, cùng cấp với `Main.java`:

- `doc-files/architecture.png` là hình ảnh dùng trong trang tài liệu.
- `doc-files/usage.html` là một tài liệu phụ trợ có thể được đưa vào website Javadoc.
- `snippet-files/Snippets.java` là nguồn Java để thẻ snippet tham chiếu bằng `class`.
- `snippet-files/application.properties` là nguồn cấu hình để thẻ snippet tham chiếu bằng `file`.

Vị trí cùng cấp không có nghĩa hai thư mục thay thế cho nhau. Standard Doclet sử dụng tên thư mục để xác định cách xử lý nội dung.

## 3. snippet-files: nguồn cho external snippet

`snippet-files` là thư mục tìm kiếm mặc định cho external snippet trong package. Khi comment Javadoc của một lớp thuộc package `p` dùng `{@snippet}`, Standard Doclet có thể tìm tệp external dưới `p/snippet-files` mà không cần khai báo thêm `--snippet-path`, miễn là Javadoc đã biết source path tương ứng.

Ví dụ trong `src/p/Main.java`:

~~~java
package p;

/**
 * Ví dụ đọc dữ liệu:
 *
 * {@snippet class=Snippets region=read-file}
 *
 * Cấu hình máy chủ:
 *
 * {@snippet file="application.properties" region=server}
 */
public class Main {
}
~~~

Nguồn Java nằm tại `src/p/snippet-files/Snippets.java`:

~~~java
package p;

import java.nio.file.Files;
import java.nio.file.Path;

public class Snippets {
    public static void main(String[] args) throws Exception {
        // @start region=read-file
        String content = Files.readString(Path.of("input.txt"));
        System.out.println(content);
        // @end region=read-file
    }
}
~~~

Tệp cấu hình nằm tại `src/p/snippet-files/application.properties`:

~~~properties
# @start region=server
server.port=8080
server.host=localhost
# @end region=server
~~~

Trong hai thẻ trên:

- `class=Snippets` yêu cầu Standard Doclet lấy nội dung từ nguồn Java `Snippets.java`.
- `file="application.properties"` chỉ định tệp Properties theo đường dẫn tương đối từ snippet root.
- `region` giới hạn phần nội dung được hiển thị.
- Các comment `@start` và `@end` được xử lý như markup; chúng không xuất hiện trong khối mã kết quả.

Standard Doclet đọc và xử lý các tệp này để dựng snippet trong trang HTML. Đây không phải thao tác sao chép nguyên thư mục như với tài nguyên phụ trợ.

### Một package có thể có nhiều tệp snippet

Bạn có thể lưu nhiều nguồn Java và nhiều định dạng văn bản trong cùng thư mục:

~~~text
p/
├── Main.java
└── snippet-files/
    ├── Snippets.java
    ├── ExternalExamples.java
    ├── application.properties
    ├── response.json
    └── sql/
        └── find-orders.sql
~~~

Thẻ `{@snippet class=...}` dành cho nguồn Java được xác định theo tên lớp. Với Properties, JSON, SQL hoặc văn bản khác, dùng `file` và đường dẫn tương đối phù hợp. Một tệp có thể chứa nhiều vùng để các đoạn tài liệu khác nhau tái sử dụng.

## 4. doc-files: tài liệu và tài nguyên phụ trợ

`doc-files` dành cho các tài nguyên bổ sung được dùng trong trang tài liệu package hoặc lớp. Ví dụ thường gặp:

- Hình ảnh, sơ đồ kiến trúc, ảnh chụp màn hình.
- Trang HTML hoặc Markdown giải thích dài hơn comment API.
- Tệp văn bản, ví dụ tải xuống hoặc tài liệu tham khảo được liên kết từ trang Javadoc.
- Các tài nguyên tĩnh mà nội dung Javadoc cần tham chiếu.

Trong JDK hiện đại, Standard Doclet hỗ trợ tài liệu bổ sung của package trong `doc-files`, bao gồm tệp HTML và Markdown. Các tài nguyên như hình ảnh có thể được tham chiếu từ comment bằng đường dẫn tương đối.

Ví dụ `Main.java`:

~~~java
package p;

/**
 * Sơ đồ tổng quan:
 *
 * <img src="doc-files/architecture.png" alt="Sơ đồ kiến trúc package p">
 *
 * Xem thêm <a href="doc-files/usage.html">hướng dẫn sử dụng</a>.
 */
public class Main {
}
~~~

Khi tạo tài liệu, đường dẫn `doc-files/architecture.png` trỏ đến tài nguyên được đặt dưới thư mục `doc-files` tương ứng của package. Javadoc giữ tài nguyên ở vị trí tương ứng trong cây đầu ra để liên kết trong HTML có thể truy cập được.

### doc-files không phải nguồn snippet mặc định

Giả sử tệp `application.properties` được đặt ở:

~~~text
src/p/doc-files/application.properties
~~~

Thẻ sau không tự động biến `doc-files` thành nơi tìm external snippet:

~~~java
{@snippet file="application.properties"}
~~~

Thuộc tính `file` được giải quyết theo snippet root: thư mục `snippet-files` của package hoặc một thư mục được cấu hình bằng `--snippet-path`. `doc-files` có vai trò khác và không tự động trở thành snippet search path.

Nếu cần cùng một nội dung vừa xuất hiện dưới dạng snippet đã xử lý vừa được cung cấp như tệp tài nguyên có thể tải/mở trực tiếp, hãy xác định rõ hai cách sử dụng. Đặt nguồn snippet trong `snippet-files` hoặc snippet path; đặt bản tài nguyên cần phân phối trong `doc-files` và liên kết đến nó. Có thể tổ chức việc đồng bộ hai bản bằng build tool của dự án.

## 5. So sánh trực tiếp snippet-files và doc-files

| Tiêu chí | `snippet-files` | `doc-files` |
| --- | --- | --- |
| Mục đích | Cung cấp nguồn cho thẻ `{@snippet}`. | Cung cấp tài liệu và tài nguyên phụ trợ cho website Javadoc. |
| Cách tham chiếu | `file` hoặc `class` trong thẻ snippet. | URL tương đối trong HTML, ví dụ `doc-files/architecture.png`. |
| Xử lý bởi Standard Doclet | Đọc nội dung, trích region, xử lý markup và dựng snippet. | Đưa tài nguyên vào cây đầu ra; HTML/Markdown có thể được dùng làm tài liệu bổ sung theo quy tắc Standard Doclet. |
| Nội dung thường gặp | Java, Properties, JSON, XML, SQL, văn bản có cấu trúc. | Hình ảnh, sơ đồ, trang HTML/Markdown, tệp phụ trợ. |
| Có region/markup snippet? | Có, theo cú pháp markup phù hợp với ngôn ngữ nguồn. | Không tự động; tài nguyên không được xử lý như external snippet chỉ vì nằm trong thư mục này. |
| Tùy chọn tìm kiếm riêng | Có thể dùng `--snippet-path` để chỉ định snippet root khác. | Theo cấu trúc `doc-files` của package và cơ chế tài liệu phụ trợ của Standard Doclet. |
| Kết quả | Nội dung snippet được nhúng vào trang API. | Tài nguyên hoặc trang bổ sung có URL riêng trong website tài liệu. |

Cách nhớ đơn giản: **snippet-files là nơi Javadoc đọc ví dụ để dựng snippet; doc-files là nơi đặt tài liệu và tài nguyên để website Javadoc sử dụng.**

## 6. Cấu hình source path và snippet path

Để tìm `snippet-files` cục bộ, Javadoc phải biết vị trí source của package. Ví dụ từ thư mục gốc dự án:

~~~sh
javadoc -sourcepath src -d build/docs p
~~~

Với cấu trúc `src/p/snippet-files`, Standard Doclet tìm các tệp snippet tương ứng với package. Không cần thêm `--snippet-path` trong trường hợp mặc định này.

Nếu build tool không xử lý đúng thư mục `snippet-files` cục bộ, có thể chuyển nguồn snippet sang một cây thư mục riêng:

~~~text
project/
├── src/
│   └── p/
│       └── Main.java
└── snippets/
    ├── Snippets.java
    └── application.properties
~~~

Sau đó chỉ định thư mục gốc tìm kiếm:

~~~sh
javadoc -sourcepath src --snippet-path snippets -d build/docs p
~~~

Trong trường hợp này, `file` và `class` vẫn tham chiếu theo tên tệp/lớp tương ứng trong snippet root. `--snippet-path` bổ sung nơi tìm external snippet; nó không thay thế `-sourcepath` dùng để tìm source của package được tài liệu hóa.

### Vì sao một số build tool gặp vấn đề với snippet-files?

Tên `snippet-files` có dấu gạch nối nên không phải định danh Java hợp lệ. Một số build tool có thể quét thư mục này như thể nó là thư mục package con của package bao ngoài. Khi đó, công cụ có thể báo lỗi hoặc xử lý sai cây source.

Tài liệu Oracle lưu ý trường hợp này và khuyến nghị dùng một thư mục snippet riêng cùng `--snippet-path` nếu không thể dùng thư mục cục bộ. Đây là vấn đề cách build tool phân loại cây source; bản thân thư mục `snippet-files` vẫn là cách tổ chức mặc định được Standard Doclet hỗ trợ.

### Dự án nhiều module

Trong dự án Java module, cấu hình source path có thể cần dùng `--module-source-path` thay cho `-sourcepath`, tùy cách tổ chức source. Dù vậy, nguyên tắc phân biệt vẫn giữ nguyên: `doc-files` chứa tài nguyên tài liệu của package, còn external snippet được tìm trong snippet root mặc định hoặc qua `--snippet-path`. Hãy kiểm tra lệnh Javadoc thực tế của cấu hình build dự án.

## 7. Ví dụ hoàn chỉnh dùng cả hai thư mục

Cấu trúc:

~~~text
project/
└── src/
    └── p/
        ├── Main.java
        ├── doc-files/
        │   ├── architecture.png
        │   └── usage.html
        └── snippet-files/
            ├── Snippets.java
            └── application.properties
~~~

Tệp `src/p/Main.java`:

~~~java
package p;

/**
 * Tài liệu lớp Main.
 *
 * <p>Sơ đồ:
 * <img src="doc-files/architecture.png" alt="Sơ đồ kiến trúc">
 *
 * <p>Hướng dẫn chi tiết:
 * <a href="doc-files/usage.html">Mở hướng dẫn sử dụng</a>.
 *
 * <p>Ví dụ Java:
 * {@snippet class=Snippets region=load}
 *
 * <p>Cấu hình máy chủ:
 * {@snippet file="application.properties" region=server}
 */
public class Main {
}
~~~

Tệp `src/p/snippet-files/Snippets.java`:

~~~java
package p;

import java.nio.file.Files;
import java.nio.file.Path;

public class Snippets {
    public static void main(String[] args) throws Exception {
        // @start region=load
        String content = Files.readString(Path.of("input.txt"));
        System.out.println(content);
        // @end region=load
    }
}
~~~

Tệp `src/p/snippet-files/application.properties`:

~~~properties
# @start region=server
server.port=8080
server.host=localhost
# @end region=server
~~~

Sinh tài liệu từ thư mục gốc dự án:

~~~sh
javadoc -sourcepath src -d build/docs p
~~~

Sau khi chạy, kiểm tra:

- Trang `build/docs/p/Main.html` hiển thị sơ đồ từ `doc-files/architecture.png`.
- Liên kết hướng dẫn mở đúng `doc-files/usage.html`.
- Snippet Java chỉ hiển thị vùng `load`.
- Snippet Properties chỉ hiển thị vùng `server`.
- Các comment markup `@start` và `@end` không xuất hiện trong snippet.

Ví dụ này cho thấy hai thư mục có thể cùng tồn tại trong một package và phục vụ hai mục đích riêng trong cùng trang tài liệu.

## 8. Quy trình chọn đúng thư mục

Trước khi thêm một tệp vào cây source, hãy xác định cách tài liệu sẽ sử dụng tệp đó:

1. **Muốn nội dung xuất hiện dưới dạng khối mã được xử lý?** Đặt nguồn trong `snippet-files` hoặc snippet root được cấu hình bằng `--snippet-path`.
2. **Muốn một hình ảnh, trang hướng dẫn hoặc tài nguyên có URL riêng?** Đặt tài nguyên trong `doc-files`.
3. **Muốn trích một phần nguồn?** Đặt markup region trong external snippet và tham chiếu bằng `region`.
4. **Muốn dùng cùng nội dung trong snippet và dưới dạng tệp tải trực tiếp?** Xác định cả nguồn snippet lẫn tài nguyên phân phối; quản lý việc đồng bộ bằng build tool.
5. **Build tool quét nhầm snippet-files như package?** Chuyển snippet sang cây riêng và dùng `--snippet-path`.
6. **Dự án nhiều module?** Kiểm tra source path/module source path và snippet path trong lệnh Javadoc của build.
7. **Sinh lại tài liệu trong CI:** dùng đường dẫn tương đối, kiểm tra file tồn tại và giữ các nguồn cần thiết trong repository.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `{@snippet file=...}` không tìm thấy tệp trong doc-files. | `doc-files` không phải snippet root mặc định. | Chuyển tệp sang `snippet-files` hoặc cấu hình thư mục chứa nó bằng `--snippet-path`. |
| Hình ảnh không xuất hiện trong trang Javadoc. | Đường dẫn URL không tương ứng với tài nguyên trong `doc-files` hoặc sai chữ hoa/thường. | Kiểm tra vị trí tệp và đường dẫn tương đối từ trang HTML. |
| Tệp snippet bị build tool xem như package. | Công cụ quét nhầm `snippet-files` trong cây source. | Dùng snippet root riêng và `--snippet-path`. |
| Snippet hiển thị toàn bộ tệp. | Chưa khai báo `region` hoặc tên vùng không khớp. | Thêm cặp `@start`/`@end` và thuộc tính region đúng tên. |
| Comment markup xuất hiện trong mã hiển thị. | Comment không đúng cú pháp của định dạng hoặc chỉ thị không được nhận diện. | Dùng markup comment phù hợp ngôn ngữ và kiểm tra cú pháp tag. |
| Trang HTML trong doc-files không được liên kết đúng. | Dùng URL như thể tệp nằm cạnh trang API thay vì trong doc-files. | Dùng đường dẫn `doc-files/...` tương ứng. |
| Javadoc tìm thấy source nhưng không tìm thấy snippet. | Source path đúng nhưng snippet root chưa được cấu hình hoặc đặt sai package. | Kiểm tra `snippet-files` hoặc `--snippet-path`. |

## 10. Bài tập thực hành

### Bài tập 1: Phân loại tệp

Với các tệp sau, hãy chọn thư mục phù hợp và giải thích:

- `architecture.png` được nhúng vào trang API.
- `usage.html` là hướng dẫn cài đặt bổ sung.
- `Snippets.java` chứa ví dụ có vùng `region`.
- `application.properties` được hiển thị bằng `{@snippet}`.
- `response.json` cần được trích một vùng có tên.

**Gợi ý:** hai tài nguyên đầu thuộc `doc-files`; ba nguồn cuối thuộc `snippet-files` hoặc một snippet root riêng.

### Bài tập 2: Sửa đường dẫn snippet

Đặt `application.properties` trong `src/p/doc-files` rồi thử tham chiếu bằng `{@snippet file="application.properties"}`. Quan sát việc tìm tệp. Sau đó chuyển nó sang `src/p/snippet-files` hoặc cấu hình đúng thư mục bằng `--snippet-path` và tạo lại Javadoc.

### Bài tập 3: Dùng cả hai thư mục

Tạo package `p` có `Main.java`, một hình ảnh trong `doc-files` và một tệp `Snippets.java` trong `snippet-files`. Trong Javadoc, nhúng hình ảnh bằng HTML và tham chiếu source bằng `{@snippet class=Snippets}`. Sinh tài liệu và kiểm tra cả hai nội dung.

### Bài tập 4: Xử lý build tool

Nếu build tool quét nhầm `snippet-files` như package, chuyển các tệp sang thư mục `snippets` bên ngoài source tree. Chạy Javadoc với `--snippet-path snippets`. Giải thích vì sao `-sourcepath` và `--snippet-path` giải quyết hai nhiệm vụ tìm kiếm khác nhau.

**Tự kiểm:** biết vị trí của hai thư mục; không dùng doc-files như snippet root mặc định; phân biệt tài nguyên được liên kết với nội dung snippet được xử lý; đã sinh Javadoc và kiểm tra URL, hình ảnh cùng các vùng mã.

## 11. Ghi nhớ

- **`snippet-files` dành cho external snippet.** Standard Doclet đọc tệp, xử lý markup và tạo khối mã trong trang API.
- **`doc-files` dành cho tài liệu và tài nguyên phụ trợ.** Hình ảnh, trang HTML/Markdown và tệp liên kết được tổ chức dưới thư mục này.
- **Hai thư mục thường nằm cạnh source của cùng package**, nhưng không thay thế nhau.
- **`file` và `class` tìm nguồn trong snippet root**, không tự động tìm trong `doc-files`.
- **`--snippet-path` cung cấp snippet root riêng** khi build tool không xử lý được thư mục cục bộ.
- **`-sourcepath` tìm source package; `--snippet-path` tìm external snippet.** Hai tùy chọn có mục đích khác nhau.
- **Kiểm tra HTML được sinh ra.** Đường dẫn tài nguyên, hình ảnh, trang phụ trợ và nội dung snippet cần được xác nhận sau khi chạy Javadoc.

## Tài liệu chính thống

- [Oracle – JDK 26 Javadoc Snippets Guide, mục External Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, mục External snippets và tài liệu package trong doc-files](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle – JDK 26 JavaDoc Guide, chương External Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/javadoc-guide.pdf).
- [Oracle – JDK 26 The javadoc Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html).

