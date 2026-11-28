# Cấu hình --snippet-path khi ví dụ được đặt trong cây nguồn độc lập

## 1. Mục tiêu và bối cảnh

JEP 413 đưa thẻ `{@snippet ...}` vào Javadoc từ **JDK 18**. Tính năng này tiếp tục được Standard Doclet hỗ trợ trên JDK hiện đại. Với external snippet, nội dung ví dụ được lưu trong tệp riêng thay vì nằm trực tiếp trong comment tài liệu. Theo cách mặc định, các tệp này có thể đặt trong thư mục `snippet-files` của package. Khi cấu trúc dự án hoặc build tool không thuận tiện cho cách đặt đó, hãy chuyển ví dụ sang một cây thư mục độc lập và khai báo gốc tìm kiếm bằng `--snippet-path`.

Bài học tập trung vào tình huống có hai cây riêng:

- Cây `src` chứa các lớp API cần tạo Javadoc.
- Cây `snippet-src` chứa ví dụ Java, tệp cấu hình hoặc dữ liệu cần hiển thị trong snippet.

Sau bài học, bạn có thể:

- Giải thích vì sao cần tách cây snippet khỏi cây source của API.
- Cấu hình `--snippet-path` để Standard Doclet tìm tệp external.
- Phân biệt `--snippet-path` với `-sourcepath` và `--module-source-path`.
- Dùng `file` cho đường dẫn tương đối và `class` cho nguồn Java theo tên lớp.
- Kết hợp nhiều thư mục tìm kiếm, `region` và markup comment.
- Phát hiện lỗi do đường dẫn, thứ tự tìm kiếm hoặc build chạy từ thư mục khác.
- Kiểm chứng ví dụ bằng compiler/test riêng với việc tạo Javadoc.

Phạm vi chỉ gồm cách cấu hình external snippet còn áp dụng trên JDK hiện đại. `--snippet-path` là tùy chọn của Standard Doclet khi chạy `javadoc`; nó không thay đổi cách ứng dụng Java tìm class lúc runtime.

## 2. Khi nào cần một cây nguồn snippet độc lập?

Cấu trúc mặc định đặt snippet cạnh source package:

~~~text
src/
└── p/
    ├── Main.java
    └── snippet-files/
        └── Snippets.java
~~~

Cách này thuận tiện khi build tool nhận diện đúng thư mục. Tuy nhiên, một số công cụ build có thể quét `snippet-files` như một phần của cây package, dù tên thư mục này không phải định danh Java hợp lệ. Khi đó, công cụ có thể báo lỗi, phân loại sai nguồn hoặc đưa tệp ví dụ vào bước xử lý package.

Một cây snippet độc lập giải quyết tình huống này:

~~~text
project/
├── src/
│   └── p/
│       └── Main.java
├── snippet-src/
│   ├── Snippets.java
│   └── config/
│       └── server.properties
└── build/
~~~

Trong cấu trúc trên:

- `src/p/Main.java` chứa API và comment Javadoc.
- `snippet-src/Snippets.java` là nguồn Java dùng cho external snippet.
- `snippet-src/config/server.properties` là nguồn cấu hình.
- `build/` là vị trí đầu ra ví dụ; Javadoc sẽ tạo thư mục đầu ra khi chạy.

Điểm quan trọng là `snippet-src` không cần nằm trong cây package của API. Chỉ cần khai báo nó làm snippet search root khi chạy Javadoc.

## 3. --snippet-path làm nhiệm vụ gì?

Tùy chọn `--snippet-path` chỉ định một hoặc nhiều thư mục tìm kiếm các tệp dùng cho external snippet.

Cú pháp:

~~~sh
javadoc --snippet-path <snippetpathlist> ...
~~~

Ví dụ:

~~~sh
javadoc -sourcepath src --snippet-path snippet-src -d build/docs p
~~~

Ý nghĩa từng phần:

| Thành phần | Vai trò |
| --- | --- |
| `-sourcepath src` | Cho Javadoc biết nơi tìm source của package `p` cần tài liệu hóa. |
| `--snippet-path snippet-src` | Cho Standard Doclet biết nơi tìm các tệp external được thẻ snippet tham chiếu. |
| `-d build/docs` | Chọn thư mục chứa HTML được sinh ra. |
| `p` | Package cần tạo tài liệu. |

`--snippet-path` không thay thế `-sourcepath`. Hai tùy chọn phục vụ hai cây đầu vào khác nhau: một cây chứa API được tài liệu hóa, cây còn lại chứa nội dung ví dụ được nhúng vào tài liệu.

Nếu bỏ `--snippet-path`, Javadoc vẫn tìm external snippet trong thư mục `snippet-files` cục bộ của package. Nếu tệp đã chuyển sang cây độc lập, Standard Doclet không tự đoán vị trí mới; cần chỉ định gốc tìm kiếm.

## 4. Đường dẫn trong thuộc tính file được tính từ snippet root

Khi dùng `file`, giá trị thuộc tính là đường dẫn tương đối từ thư mục snippet root được tìm kiếm.

Với cấu trúc:

~~~text
snippet-src/
├── Snippets.java
└── config/
    └── server.properties
~~~

Các thẻ tương ứng:

~~~java
/**
 * Ví dụ Java:
 *
 * {@snippet file="Snippets.java" region=regex}
 *
 * Cấu hình máy chủ:
 *
 * {@snippet file="config/server.properties" lang="properties" region=server}
 */
public class Main {
}
~~~

Standard Doclet tìm:

- `Snippets.java` trong `snippet-src/Snippets.java`.
- `config/server.properties` trong `snippet-src/config/server.properties`.

Không thêm tiền tố `snippet-src/` vào giá trị `file` vì chính thư mục đó đã được khai báo làm snippet root.

Nếu đặt `file="snippet-src/config/server.properties"` trong khi root là `snippet-src`, đường dẫn có thể bị ghép thành một đường dẫn lặp cấp thư mục. Hãy luôn suy nghĩ theo quy tắc: **root là nơi tìm kiếm; file là đường dẫn tương đối bên trong root**.

### Dùng dấu gạch chéo xuôi trong thuộc tính file

Trong đường dẫn của thuộc tính `file`, dùng dấu gạch chéo xuôi `/` để phân tách thư mục:

~~~java
{@snippet file="config/server.properties" lang=properties}
~~~

Cách viết này dễ dùng chung trên Windows, Linux và macOS. Tránh ghi đường dẫn tuyệt đối gắn với một máy cá nhân, ví dụ `C:\work\project\snippet-src\...`. Đường dẫn tương đối trong repository giúp lệnh Javadoc chạy được trên máy phát triển và CI.

## 5. Dùng class khi nguồn độc lập là Java source

Với tệp Java, có thể tham chiếu bằng `class` thay cho `file`:

~~~java
/**
 * Ví dụ kiểm tra biểu thức chính quy:
 *
 * {@snippet class=Snippets region=regex}
 */
public class Main {
}
~~~

Nếu thư mục snippet root chứa `Snippets.java`, Standard Doclet có thể tìm nguồn Java theo tên lớp. Ví dụ cơ bản dùng tên lớp `HelloWorld` và tệp `HelloWorld.java`.

Chọn `class` khi:

- Nguồn là tệp Java có tên lớp rõ ràng.
- Muốn tham chiếu theo tên lớp thay vì đường dẫn tệp.
- Ví dụ được tổ chức thành một lớp Java độc lập.

Chọn `file` khi:

- Nguồn là Properties, JSON, XML, HTML hoặc văn bản có cấu trúc khác.
- Cần chỉ rõ đường dẫn tương đối, bao gồm thư mục con.
- Muốn tham chiếu một tệp Java theo đường dẫn cụ thể.

Ví dụ:

~~~java
/**
 * Nguồn Java theo tên lớp:
 * {@snippet class=Snippets}
 *
 * Tệp cấu hình theo đường dẫn:
 * {@snippet file="config/server.properties" lang=properties}
 */
~~~

`class` và `file` đều là cách tham chiếu external snippet. Cả hai đều dùng snippet search root; không nhầm `class` với việc Javadoc nạp một class đã biên dịch từ classpath. Standard Doclet đọc source để lấy nội dung hiển thị.

## 6. Ví dụ hoàn chỉnh với cây snippet-src độc lập

Cấu trúc dự án:

~~~text
project/
├── src/
│   └── p/
│       └── Main.java
├── snippet-src/
│   ├── Snippets.java
│   └── config/
│       └── server.properties
└── build/
~~~

Tệp `src/p/Main.java`:

~~~java
package p;

/**
 * Ví dụ kiểm tra regex:
 *
 * {@snippet class=Snippets region=regex}
 *
 * Cấu hình máy chủ:
 *
 * {@snippet file="config/server.properties" lang="properties" region=server}
 */
public class Main {
}
~~~

Tệp `snippet-src/Snippets.java`:

~~~java
import java.util.regex.Pattern;

public class Snippets {
    public static void main(String... args) {
        // @start region=regex
        String regex = "a.*/b";
        boolean matches = Pattern.compile(regex)
                .matcher("a123/b")
                .matches();

        if (!matches) {
            throw new AssertionError("The pattern did not match");
        }
        // @end region=regex
    }
}
~~~

Tệp `snippet-src/config/server.properties`:

~~~properties
# @start region=server
server.port=8080
server.host=localhost
server.timeout=5000
# @end region=server
~~~

Tạo tài liệu từ thư mục gốc dự án:

~~~sh
javadoc -sourcepath src --snippet-path snippet-src -d build/docs p
~~~

Lệnh này thực hiện hai việc tìm kiếm độc lập:

1. Tìm package `p` và lớp `Main` từ `src`.
2. Tìm `Snippets.java` và `config/server.properties` từ `snippet-src` để xử lý các thẻ snippet.

Kết quả mong đợi là trang `build/docs/p/Main.html` có hai khối mã: vùng `regex` trong tệp Java và vùng `server` trong tệp Properties. Các comment markup `@start` và `@end` không xuất hiện trong nội dung hiển thị.

### Kiểm chứng tệp Java riêng

Javadoc không biên dịch hoặc chạy snippet. Có thể kiểm tra tệp Java bằng compiler:

~~~sh
javac -d build/classes snippet-src/Snippets.java
java -cp build/classes Snippets
~~~

Nếu chương trình kết thúc bình thường, ví dụ regex đã vượt qua phép kiểm tra trong `main`. Nếu Javadoc tạo HTML thành công nhưng chương trình không biên dịch hoặc chạy đúng, đó là hai kết quả độc lập; cần sửa nguồn ví dụ và kiểm thử lại.

## 7. Nhiều thư mục snippet search root

`--snippet-path` nhận một danh sách thư mục. Các đường dẫn trong danh sách được phân cách bằng **path separator của hệ điều hành**:

| Hệ điều hành | Dấu phân cách | Ví dụ |
| --- | --- | --- |
| Windows | Dấu chấm phẩy `;` | `snippets;shared-snippets` |
| Linux/macOS | Dấu hai chấm `:` | `snippets:shared-snippets` |

Windows PowerShell:

~~~powershell
javadoc -sourcepath src --snippet-path "snippet-src;shared-snippets" -d build/docs p
~~~

Linux/macOS:

~~~sh
javadoc -sourcepath src --snippet-path "snippet-src:shared-snippets" -d build/docs p
~~~

Mỗi thư mục trong danh sách là một snippet root. Thuộc tính `file` vẫn là đường dẫn tương đối từ từng root có thể cung cấp tệp đó.

Ví dụ:

~~~text
project/
├── src/
│   └── p/
│       └── Main.java
├── snippet-src/
│   └── examples/
│       └── OrderExamples.java
└── shared-snippets/
    └── common/
        └── retry.properties
~~~

Trong Javadoc:

~~~java
/**
 * Ví dụ xử lý đơn hàng:
 * {@snippet file="examples/OrderExamples.java" region=create}
 *
 * Cấu hình retry dùng chung:
 * {@snippet file="common/retry.properties" lang=properties}
 */
~~~

Lệnh trên Windows:

~~~powershell
javadoc -sourcepath src --snippet-path "snippet-src;shared-snippets" -d build/docs p
~~~

Lệnh trên Linux/macOS:

~~~sh
javadoc -sourcepath src --snippet-path "snippet-src:shared-snippets" -d build/docs p
~~~

### Thứ tự tìm kiếm và tên tệp trùng nhau

Standard Doclet tìm thư mục `snippet-files` của package chứa thẻ trước, sau đó mới tìm các thư mục trong danh sách `--snippet-path`. Vì vậy:

- Nếu có một tệp cùng đường dẫn tương đối ở cả package-local `snippet-files` và snippet root độc lập, nguồn cục bộ được tìm trước.
- Nếu nhiều snippet root có cùng một đường dẫn tương đối, tránh đặt các tệp trùng tên gây mơ hồ; sắp xếp danh sách root có chủ đích và kiểm tra nội dung được chọn.
- Không dựa vào thứ tự ngẫu nhiên của filesystem. Hãy giữ cấu trúc thư mục và tên tệp rõ ràng.

Để tránh việc một tệp cũ che khuất nguồn mới, không nên giữ hai bản cùng tên ở nhiều root nếu không có lý do cụ thể. Nếu chủ ý dùng bản dùng chung, đặt nó trong một đường dẫn con riêng, ví dụ `common/retry.properties`.

## 8. Phân biệt source path, snippet path và module source path

Ba khái niệm thường bị nhầm khi dự án có nhiều cây source:

| Tùy chọn | Dùng để tìm | Ví dụ |
| --- | --- | --- |
| `-sourcepath` | Source package hoặc source file cần tạo tài liệu. | `-sourcepath src/main/java` |
| `--snippet-path` | Tệp external được tham chiếu trong `{@snippet}`. | `--snippet-path docs/snippets` |
| `--module-source-path` | Source tree của các module khi tạo tài liệu cho dự án modular. | `--module-source-path src/*/java` |

Nếu dự án modular, có thể cần `--module-source-path` thay cho `-sourcepath` để Javadoc tìm các module và package cần tài liệu hóa. Điều này không loại bỏ nhu cầu cấu hình snippet root độc lập: external snippet vẫn được tìm theo `snippet-files` cục bộ hoặc `--snippet-path`.

Ví dụ lệnh minh họa cho source tree nhiều module:

~~~sh
javadoc --module-source-path "modules/*/src/main/java" --snippet-path docs/snippets -d build/docs --module example.api
~~~

Cấu trúc và tùy chọn module thực tế phụ thuộc cách build dự án. Hãy kiểm tra lệnh mà build tool tạo ra thay vì sao chép nguyên mẫu trên mà không điều chỉnh.

## 9. Tích hợp với build tool và CI

Trong dự án thực tế, lệnh Javadoc thường được gọi từ Maven, Gradle hoặc một script build. Dù dùng công cụ nào, yêu cầu vẫn giống nhau:

- Source API phải được đưa vào Javadoc bằng source path hoặc cấu hình module tương ứng.
- Các snippet root độc lập phải được truyền vào tùy chọn `--snippet-path`.
- Đường dẫn nên tương đối với thư mục làm việc mà build task sử dụng hoặc được build tool chuẩn hóa thành đường dẫn hợp lệ.
- Cùng một cấu hình phải được áp dụng trong môi trường phát triển và CI.
- Khi đổi tên hoặc di chuyển snippet, cập nhật đường dẫn trong thẻ và cấu hình build cùng một thay đổi.

Không nên giả định việc một IDE nhìn thấy thư mục `snippet-src` đồng nghĩa Standard Doclet tự tìm được nó. Khả năng tìm kiếm external snippet phụ thuộc tham số thực tế truyền cho lệnh `javadoc`.

### Đưa tùy chọn vào script build

Có thể tập trung lệnh Javadoc trong một script để tránh mỗi môi trường truyền một danh sách path khác nhau:

~~~sh
javadoc   -sourcepath src/main/java   --snippet-path docs/snippets:shared/snippets   -d build/javadoc   com.example.api
~~~

Đây là ví dụ cho Linux/macOS. Trên Windows, thay dấu phân cách giữa các snippet root bằng dấu chấm phẩy. Nếu build tool đã có API cấu hình danh sách tùy chọn, nên truyền từng đường dẫn theo cách mà plugin hỗ trợ để tránh tự nối sai separator.

### Kiểm tra từ thư mục làm việc khác

Đường dẫn tương đối trong lệnh được đánh giá theo thư mục làm việc của tiến trình chạy Javadoc. Vì vậy, nếu script được gọi từ thư mục con, đường dẫn `src` hoặc `snippet-src` có thể không còn trỏ đến vị trí dự định.

Cách xử lý:

1. Chọn một thư mục gốc thống nhất cho lệnh build.
2. Dùng đường dẫn tương đối từ thư mục đó hoặc để build tool chuyển thành đường dẫn đầy đủ.
3. In/kiểm tra command line thực tế khi Javadoc báo không tìm thấy snippet.
4. Chạy lại cùng lệnh trong CI để xác nhận cấu hình không phụ thuộc máy cá nhân.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Javadoc không tìm thấy external file. | Chưa truyền `--snippet-path` hoặc root trỏ sai thư mục. | Kiểm tra thư mục gốc và đường dẫn tương đối trong `file`. |
| `file` bị lặp tiền tố thư mục. | Giá trị file đã bao gồm tên snippet root. | Bỏ tiền tố root khỏi giá trị file. |
| Javadoc tìm nhầm bản snippet cũ. | Cùng đường dẫn tương đối tồn tại trong package-local `snippet-files` hoặc nhiều root. | Loại bỏ trùng lặp hoặc đặt nguồn trong đường dẫn con riêng. |
| `class` không tìm thấy source. | Tên lớp không tương ứng tệp Java trong snippet root. | Kiểm tra tên lớp, tên tệp và cấu hình tìm kiếm. |
| `-sourcepath` đúng nhưng snippet vẫn không thấy. | Source path chỉ tìm API, không thay thế snippet path. | Bổ sung `--snippet-path`. |
| Chạy được trên máy phát triển nhưng lỗi trong CI. | Working directory hoặc đường dẫn tuyệt đối khác nhau. | Chuẩn hóa đường dẫn và thư mục làm việc của build task. |
| Nhiều snippet root không được phân tách đúng. | Dùng sai path separator của hệ điều hành. | Windows dùng `;`, Linux/macOS dùng `:`. |
| Snippet hiển thị nhưng ví dụ Java không chạy. | Javadoc chỉ đọc và trình bày nội dung. | Biên dịch/chạy nguồn snippet riêng bằng compiler và runtime. |
| Dự án modular không tìm thấy package API. | Dùng sourcepath không phù hợp với module source tree. | Kiểm tra `--module-source-path` và cấu hình module của Javadoc. |

## 11. Quy trình triển khai có thể lặp lại

1. **Tách hai đầu vào:** xác định cây source API và cây ví dụ external.
2. **Tạo snippet root:** đặt các tệp ví dụ dưới một thư mục độc lập, ví dụ `snippet-src`.
3. **Chọn cách tham chiếu:** dùng `class` cho nguồn Java theo tên lớp; dùng `file` cho đường dẫn tương đối và định dạng khác.
4. **Đánh dấu vùng cần hiển thị:** dùng `@start region=name` và `@end region=name` trong tệp external.
5. **Cấu hình lệnh:** truyền source path của API và `--snippet-path` cho snippet root.
6. **Kiểm tra path list:** nếu có nhiều root, dùng đúng separator và tránh trùng đường dẫn.
7. **Tạo tài liệu:** chạy Javadoc trên JDK mục tiêu, đọc cảnh báo và kiểm tra HTML.
8. **Kiểm thử nguồn ví dụ:** biên dịch/chạy Java hoặc xác thực Properties/JSON bằng công cụ phù hợp.
9. **Đưa cấu hình vào build/CI:** giữ đường dẫn tương đối, thư mục làm việc và danh sách root nhất quán.
10. **Cập nhật đồng bộ:** khi di chuyển tệp hoặc đổi tên region, sửa thẻ snippet và cấu hình build trong cùng thay đổi.

## 12. Bài tập thực hành

### Bài tập 1: Chuyển snippet sang cây độc lập

Tạo cấu trúc:

~~~text
project/
├── src/p/Main.java
└── snippet-src/Snippets.java
~~~

Thêm `{@snippet class=Snippets}` vào Javadoc của `Main`. Chạy Javadoc với `--snippet-path snippet-src` và xác nhận source được hiển thị.

### Bài tập 2: Dùng file cho tệp cấu hình

Tạo `snippet-src/config/server.properties` có vùng `server`. Tham chiếu bằng:

~~~java
{@snippet file="config/server.properties" lang="properties" region=server}
~~~

Sinh Javadoc và xác nhận chỉ các dòng trong vùng được hiển thị.

### Bài tập 3: Thêm nhiều search root

Tạo thêm thư mục `shared-snippets` có tệp `common/retry.properties`. Cấu hình cả hai root bằng `--snippet-path`. Thử trên Windows và Linux/macOS, ghi lại separator tương ứng.

### Bài tập 4: Kiểm tra ưu tiên tìm kiếm

Đặt hai tệp cùng đường dẫn tương đối trong package-local `snippet-files` và snippet root độc lập. Tạo Javadoc và xác định nguồn được tìm trước. Sau đó loại bỏ bản trùng để cấu trúc dễ hiểu hơn.

### Bài tập 5: Phân biệt source path và snippet path

Cố ý bỏ `--snippet-path` trong khi vẫn giữ `-sourcepath src`. Quan sát lỗi tìm snippet. Thêm lại snippet path và giải thích vì sao source path không tự động thay thế nó.

### Bài tập 6: Tích hợp CI

Đưa lệnh Javadoc vào script build, chạy từ thư mục gốc dự án và chạy lại từ một working directory khác. Điều chỉnh đường dẫn để kết quả nhất quán giữa hai môi trường.

**Tự kiểm:** source API và snippet root được cấu hình riêng; đường dẫn `file` tương đối đúng; `class` trỏ đúng Java source; region được chọn đúng; nhiều root dùng đúng separator; HTML được tạo; mã ví dụ được kiểm thử riêng.

## 13. Ghi nhớ

- **`--snippet-path` chỉ định gốc tìm external snippet.** Nó cho phép đặt ví dụ trong cây thư mục độc lập với source API.
- **`-sourcepath` và `--snippet-path` có nhiệm vụ riêng.** Một tùy chọn tìm package API, tùy chọn kia tìm tệp snippet.
- **Đường dẫn `file` tương đối với snippet root.** Không lặp lại tên thư mục root trong giá trị thuộc tính.
- **`class` tham chiếu nguồn Java theo tên lớp; `file` tham chiếu tệp theo đường dẫn.** Dùng đúng cách theo loại nguồn.
- **Standard Doclet tìm `snippet-files` cục bộ trước**, sau đó mới tìm các root trong `--snippet-path`.
- **Nhiều root dùng path separator của hệ điều hành.** Windows dùng dấu chấm phẩy; Linux/macOS dùng dấu hai chấm.
- **Javadoc không biên dịch hay chạy snippet.** Kiểm chứng ví dụ bằng compiler, runtime hoặc parser/test phù hợp.
- **Giữ cấu hình build nhất quán giữa máy phát triển và CI.** Tránh đường dẫn tuyệt đối gắn với một máy và kiểm tra working directory thực tế.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle – JDK 26 Javadoc Snippets Guide, mục External Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, External snippets](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle – JDK 26 The javadoc Command, tùy chọn --snippet-path](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html).

