# `@start`, `@end` và thuộc tính `region` để chọn một phần tệp nguồn bên ngoài

## Mục tiêu bài học

Một ví dụ trong tài liệu API thường nằm giữa một class, method hoặc file cấu hình lớn. Nếu đưa toàn bộ file vào Javadoc, người đọc phải đọc nhiều dòng không liên quan. **External snippet** cho phép Javadoc lấy nội dung từ file riêng; các marker `@start` và `@end` đánh dấu một vùng, còn thuộc tính `region` của `{@snippet}` chọn vùng cần hiển thị.

Đây là cơ chế của Javadoc được giới thiệu cùng `{@snippet}` trong Java 18 và vẫn được hỗ trợ trong các JDK hiện đại.

Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Module tập trung vào những thay đổi Java 18 còn hữu ích trên JDK hiện đại, đặc biệt là snippet trong tài liệu API và cách kiểm chứng nội dung được sinh ra.

Sau bài học, bạn có thể:

- Đặt marker `@start region="..."` và `@end region="..."` trong file external snippet.
- Dùng `region` trên `{@snippet}` để trích đúng đoạn cần trình bày.
- Tổ chức một file external có nhiều vùng để tái sử dụng ở nhiều vị trí trong tài liệu.
- Phân biệt vùng được chọn để **hiển thị** với vùng được chọn làm **phạm vi của markup** như `@highlight` hoặc `@replace`.
- Chọn đúng thư mục `snippet-files` hoặc cấu hình `--snippet-path` để Javadoc tìm thấy file.
- Dùng marker phù hợp với cú pháp comment của Java, properties và các định dạng văn bản khác.
- Kiểm tra file nguồn, region và HTML bằng `javac`/`javadoc`.

## 1. Vì sao cần chọn region trong external snippet?

Giả sử một file Java có class, import, nhiều method và một ví dụ sử dụng API. Tài liệu chỉ cần trình bày một method hoặc một đoạn gọi API. Sao chép thủ công đoạn mã vào Javadoc có thể khiến ví dụ bị lệch so với source khi code thay đổi.

External snippet giải quyết vấn đề bằng cách tham chiếu file riêng:

~~~java
/**
 * Ví dụ sử dụng API:
 * {@snippet file="SearchExamples.java"}
 */
public class SearchApiDoc {
}
~~~

Nếu không chỉ định `region`, Javadoc đưa toàn bộ nội dung file external vào snippet, sau khi xử lý markup comment. Nếu file có nhiều class hoặc nhiều ví dụ, phần hiển thị có thể quá dài.

Ta có thể đánh dấu đoạn cần dùng ngay trong file nguồn:

~~~java
public class SearchExamples {
    public static void main(String... args) {
        // @start region="basic-search"
        String query = "java";
        int limit = 10;
        System.out.println(query + ": " + limit);
        // @end region="basic-search"

        // Phần khác của ví dụ không thuộc basic-search.
        System.out.println("finished");
    }
}
~~~

Sau đó chọn vùng trong Javadoc:

~~~java
/**
 * Chỉ trình bày ví dụ tìm kiếm cơ bản:
 * {@snippet file="SearchExamples.java" region="basic-search"}
 */
public class SearchApiDoc {
}
~~~

Nội dung mã được hiển thị:

~~~java
String query = "java";
int limit = 10;
System.out.println(query + ": " + limit);
~~~

Javadoc chỉ trích phần nằm giữa hai marker có tên `basic-search`. Dòng marker `@start` và `@end` là markup comment nên không xuất hiện trong khối mã hiển thị.

## 2. Cú pháp của `@start` và `@end`

Một region là một khoảng dòng có thể được đặt tên. Dạng thường dùng:

~~~java
// @start region="region-name"
...
// @end region="region-name"
~~~

- `@start region="region-name"` đánh dấu điểm bắt đầu của region có tên.
- `@end region="region-name"` kết thúc region cùng tên.
- Các dòng mã ở giữa là nội dung của region.
- Marker là comment điều khiển, không được hiển thị trong snippet đã sinh.

Chỉ các comment được nhận diện là markup comment mới bị lược bỏ. Comment Java thông thường nằm bên trong vùng được chọn vẫn có thể xuất hiện trong snippet, cùng với các dòng mã khác.

Có thể viết giá trị không có dấu nháy nếu tên vùng là một identifier đơn giản:

~~~java
// @start region=main
System.out.println("Hello");
// @end region=main
~~~

Trong bài học, dùng dấu nháy quanh tên region giúp phân biệt rõ giá trị thuộc tính với phần mã còn lại.

### 2.1. Region có tên

Ví dụ:

~~~java
// @start region="connection"
var connection = dataSource.getConnection();
connection.setAutoCommit(false);
// @end region="connection"
~~~

Javadoc tham chiếu:

~~~java
{@snippet file="DatabaseExample.java" region="connection"}
~~~

Thuộc tính `region="connection"` chọn đúng vùng có tên `connection`. Tên ở `@start`, `@end` và `{@snippet}` phải thống nhất.

Tên region là định danh do người viết tài liệu đặt. Nên chọn tên mô tả mục đích, ví dụ `connection`, `request`, `validation` hoặc `cleanup` thay vì tên quá chung như `part1`.

### 2.2. Region không đặt tên

Đặc tả cũng cho phép marker không có tên:

~~~java
// @start
String query = "java";
System.out.println(query);
// @end
~~~

`@end` không kèm tên sẽ đóng region chưa được đóng gần nhất. Cách này có ích khi chỉ cần một phạm vi tạm thời hoặc khi region được dùng làm phạm vi của một markup action.

Tuy nhiên, thuộc tính `region` trên `{@snippet}` cần một tên để chỉ rõ đoạn external file cần trích. Vì vậy, khi mục tiêu là chọn vùng để hiển thị bằng `{@snippet file=... region=...}`, hãy dùng region có tên.

### 2.3. Đánh dấu ở dòng riêng để dễ đọc

Nên đặt marker trên dòng riêng:

~~~java
// @start region="request"
var request = HttpRequest.newBuilder(uri)
        .GET()
        .build();
// @end region="request"
~~~

Cách này giúp ranh giới vùng dễ nhìn và tránh nhầm marker với câu lệnh Java. Khi file có nhiều vùng, việc đặt marker rõ ràng cũng giúp review thay đổi dễ hơn.

## 3. Thuộc tính `region` của `{@snippet}` chọn phần nào?

Đối với external snippet, cú pháp cơ bản là:

~~~java
{@snippet file="TênTệp.ext" region="TênVùng"}
~~~

Hoặc nếu tham chiếu một class Java:

~~~java
{@snippet class=ExternalExamples region="main"}
~~~

| Thuộc tính | Mục đích |
| --- | --- |
| `file` | Chỉ định file external bằng đường dẫn tương đối. Có thể dùng cho Java source hoặc định dạng văn bản khác. |
| `class` | Chỉ định class Java có source chứa snippet. |
| `region` | Chọn vùng có tên trong file/class external để đưa vào tài liệu. |
| `lang` | Chỉ định ngôn ngữ của nội dung khi cần; với external snippet, ngôn ngữ mặc định thường được suy ra từ phần mở rộng của file. |

Ví dụ:

~~~java
/**
 * Ví dụ xây dựng HTTP request:
 * {@snippet file="HttpExamples.java" region="build-request"}
 */
public class HttpApiDoc {
}
~~~

File `HttpExamples.java` có thể chứa nhiều method hoặc ví dụ khác nhau. Javadoc chỉ lấy vùng `build-request`.

**Phân biệt hai trường hợp:**

- `{@snippet file="HttpExamples.java"}` không có `region`: đưa toàn bộ file vào snippet.
- `{@snippet file="HttpExamples.java" region="build-request"}`: chỉ đưa nội dung thuộc region `build-request` vào snippet.

Vì vậy, nếu bỏ thuộc tính `region`, những dòng nằm ngoài các vùng được đánh dấu vẫn xuất hiện; marker `@start`/`@end` chỉ được xử lý như markup comment và không hiển thị.

Các marker `@start` và `@end` vẫn được xử lý như markup comment; người đọc không nhìn thấy chúng trong khối mã.

## 4. Một file external có thể có nhiều region

Không cần tạo một file cho từng đoạn mã nhỏ. Một file external có thể định nghĩa nhiều vùng và được tham chiếu ở các phần khác nhau của tài liệu.

Ví dụ file `SearchExamples.java`:

~~~java
package demo;

import java.util.List;

public final class SearchExamples {
    private SearchExamples() {
    }

    public static void main(String[] args) {
        // @start region="basic-search"
        String query = "java";
        int limit = 10;
        System.out.println(query + ": " + limit);
        // @end region="basic-search"

        // @start region="filter-results"
        List<String> results = List.of("Java", "Kotlin", "Scala");
        List<String> filtered = results.stream()
                .filter(name -> name.startsWith("J"))
                .toList();
        System.out.println(filtered);
        // @end region="filter-results"

        // @start region="print-results"
        filtered.forEach(System.out::println);
        // @end region="print-results"
    }
}
~~~

Một documentation comment có thể sử dụng file đó nhiều lần:

~~~java
/**
 * Khởi tạo truy vấn:
 * {@snippet file="SearchExamples.java" region="basic-search"}
 *
 * Lọc kết quả:
 * {@snippet file="SearchExamples.java" region="filter-results"}
 *
 * In kết quả:
 * {@snippet file="SearchExamples.java" region="print-results"}
 */
public class SearchApiDoc {
}
~~~

Ba snippet được tạo từ cùng một file external:

| Region được chọn | Nội dung được trích |
| --- | --- |
| `basic-search` | Khởi tạo chuỗi truy vấn, giới hạn và câu lệnh in. |
| `filter-results` | Tạo danh sách, lọc phần tử và lưu kết quả. |
| `print-results` | Duyệt và in từng kết quả. |

Lợi ích là source chỉ có một nơi chứa ví dụ. Nếu cách lọc thay đổi, tác giả sửa file external; các snippet tham chiếu region liên quan sẽ lấy nội dung mới ở lần sinh Javadoc tiếp theo.

## 5. Marker region phải dùng đúng cú pháp comment của file

Markup tag được đặt trong comment để không làm thay đổi nội dung mã nguồn. Ký hiệu comment phụ thuộc ngôn ngữ của file external.

### 5.1. File Java dùng `//`

~~~java
// @start region="usage"
var result = service.find("java");
System.out.println(result);
// @end region="usage"
~~~

Javadoc nhận diện marker trong comment Java. Dòng marker bị loại khỏi khối mã được sinh ra; các câu lệnh ở giữa vẫn được hiển thị.

### 5.2. File properties dùng `#`

File properties dùng `#` để bắt đầu comment:

~~~properties
# @start region="server"
server.host=localhost
server.port=8080
server.protocol=https
# @end region="server"
~~~

Trong Javadoc:

~~~java
/**
 * Cấu hình server:
 * {@snippet file="application.properties" region="server"}
 */
public class ServerConfigDoc {
}
~~~

Kết quả hiển thị:

~~~properties
server.host=localhost
server.port=8080
server.protocol=https
~~~

Không dùng `//` trong file properties vì đó không phải cú pháp comment của định dạng này. Marker phải được viết bằng comment syntax mà parser của định dạng có thể nhận biết.

### 5.3. File văn bản có cấu trúc khác

External snippet không giới hạn ở Java source. Có thể tham chiếu file properties, HTML, XML, JSON mẫu hoặc văn bản có cấu trúc phù hợp để hiển thị trong khối `pre` của HTML. Cần chọn comment syntax phù hợp với định dạng nếu muốn dùng markup comment.

Ví dụ, một file XML có thể dùng XML comment:

~~~xml
<configuration>
    <!-- @start region="database" -->
    <database>
        <host>localhost</host>
        <port>5432</port>
    </database>
    <!-- @end region="database" -->
</configuration>
~~~

Nếu dùng file external có định dạng không hỗ trợ comment, không thể tùy tiện chèn `// @start` hoặc `# @start` vào nội dung vì chúng có thể trở thành dữ liệu thật hoặc làm hỏng cú pháp. Hãy chọn định dạng có comment phù hợp hoặc tổ chức nội dung theo cách khác.

## 6. Phân biệt region chọn nội dung và region của markup action

Từ `region` có thể xuất hiện ở hai vị trí khác nhau:

1. Thuộc tính `region` của `{@snippet}` chọn **đoạn mã được đưa vào tài liệu**.
2. Thuộc tính `region` của markup tag như `@highlight`, `@replace` hoặc `@link` xác định **phạm vi mà hành động đó áp dụng**.

Ví dụ:

~~~java
/**
 * Chỉ trích region request:
 * {@snippet file="HttpExamples.java" region="request"}
 */
public class HttpApiDoc {
}
~~~

Ở đây, `region="request"` chọn nội dung hiển thị.

Trong file external có thể có một markup action khác:

~~~java
// @highlight region="request" substring="GET" type=bold
...
// @end region="request"
~~~

Ở trường hợp này, `region="request"` mở phạm vi cho `@highlight`. Nó điều khiển phần chữ được làm nổi bật, không phải thuộc tính lựa chọn nội dung của tag `{@snippet}`.

Một cách dùng thường gặp hơn là định nghĩa region bằng marker `@start`/`@end` rồi dùng cùng tên region ở cả hai nơi:

~~~java
// @start region="request"
var request = HttpRequest.newBuilder(uri)
        .GET()
        .build();
// @end region="request"
~~~

~~~java
/**
 * {@snippet file="HttpExamples.java" region="request"}
 */
~~~

Snippet chọn vùng `request` để hiển thị. Nếu muốn định dạng thêm trong vùng đó, có thể thêm markup tag có selector phù hợp.

## 7. Region lồng nhau và region chồng lấn

Một file có thể có nhiều region. Các vùng có thể được lồng nhau hoặc chồng lấn; khi cấu trúc phức tạp, nên đặt tên để xác định rõ marker bắt đầu và kết thúc.

### 7.1. Region lồng nhau

Ví dụ:

~~~java
// @start region="transaction"
beginTransaction();

// @start region="write"
writeRecords();
flush();
// @end region="write"

commitTransaction();
// @end region="transaction"
~~~

Trong ví dụ:

- `transaction` chứa toàn bộ đoạn từ `beginTransaction()` đến `commitTransaction()`.
- `write` là vùng con nằm bên trong `transaction`.
- `@end region="write"` đóng vùng `write`.
- `@end region="transaction"` đóng vùng ngoài.

Có thể tham chiếu từng vùng riêng:

~~~java
{@snippet file="TransactionExample.java" region="transaction"}
~~~

~~~java
{@snippet file="TransactionExample.java" region="write"}
~~~

Nhờ vậy, cùng một source có thể minh họa cả quy trình transaction tổng thể và riêng bước ghi dữ liệu.

### 7.2. Dùng `@end` không có tên

Nếu marker bắt đầu không có tên, `@end` không có tên sẽ đóng region được mở gần nhất nhưng chưa đóng:

~~~java
// @start
String query = "java";

// @start
int limit = 10;
// @end

System.out.println(query + ": " + limit);
// @end
~~~

Khi có nhiều vùng, cách dùng không tên đòi hỏi người đọc theo dõi thứ tự mở/đóng. Tên vùng làm cấu trúc rõ hơn, nhất là khi source được cập nhật bởi nhiều người.

Nếu `@end region="name"` có tên, nó đóng region đã được mở bằng tên tương ứng. Nếu `@end` không có tên, nó đóng region gần nhất chưa có marker kết thúc tương ứng.

### 7.3. Region chồng lấn

Các cặp region không bị giới hạn chỉ ở cấu trúc lồng nhau; chúng có thể chồng lấn. Với vùng chồng lấn, hãy đặt tên ở cả marker bắt đầu và kết thúc để Javadoc xác định chính xác cặp tương ứng.

Không nên tạo vùng chồng lấn nếu chỉ cần một region đơn giản. Tên rõ ràng và cấu trúc dễ đọc giúp giảm nhầm lẫn khi thêm, xóa hoặc di chuyển các marker.

## 8. Tổ chức file trong `snippet-files`

Cách thông thường là đặt file external trong thư mục `snippet-files` nằm dưới thư mục package chứa source có documentation comment.

Ví dụ cấu trúc:

~~~text
src/
└── demo/
    ├── SearchApiDoc.java
    └── snippet-files/
        ├── SearchExamples.java
        └── application.properties
~~~

Trong `SearchApiDoc.java`:

~~~java
/**
 * Ví dụ tìm kiếm:
 * {@snippet file="SearchExamples.java" region="basic-search"}
 *
 * Cấu hình:
 * {@snippet file="application.properties" region="server"}
 */
public class SearchApiDoc {
}
~~~

Javadoc tìm file trong `snippet-files` của package tương ứng. Với ví dụ trên, cả hai file external nằm dưới `src/demo/snippet-files`.

### 8.1. Vì sao không đặt file external lẫn trong source package?

`snippet-files` là thư mục chứa nội dung phục vụ tài liệu, không phải package Java. Nó giúp tách file ví dụ khỏi source package và tránh việc file mẫu bị xem nhầm là class thuộc package.

Một số build tool có thể tự động quét file trong source tree. Nếu build tool xử lý `snippet-files` không phù hợp, hãy đặt file external ở thư mục riêng và khai báo `--snippet-path`.

### 8.2. Dùng `--snippet-path`

Khi file external nằm ngoài thư mục `snippet-files` mặc định, truyền đường dẫn gốc cho Javadoc:

~~~text
project/
├── src/
│   └── demo/
│       └── SearchApiDoc.java
└── snippets/
    └── SearchExamples.java
~~~

Lệnh:

~~~bash
javadoc -d docs -sourcepath src --snippet-path snippets demo
~~~

Trong documentation comment, vẫn tham chiếu bằng đường dẫn tương đối:

~~~java
{@snippet file="SearchExamples.java" region="basic-search"}
~~~

`--snippet-path` có thể nhận nhiều thư mục tìm kiếm, phân cách bằng ký tự path separator của hệ điều hành:

- Windows: dấu chấm phẩy (`;`).
- Linux/macOS: dấu hai chấm (`:`).

Ví dụ Windows:

~~~powershell
javadoc -d docs -sourcepath src --snippet-path "snippets;shared-snippets" demo
~~~

Ví dụ Linux/macOS:

~~~bash
javadoc -d docs -sourcepath src --snippet-path "snippets:shared-snippets" demo
~~~

Standard doclet tìm trong `snippet-files` của package trước, rồi tìm các thư mục được chỉ định trong `--snippet-path`.

## 9. Khi nào dùng `file` và khi nào dùng `class`?

Có hai cách phổ biến để trỏ tới external source:

| Cách | Thuộc tính | Phù hợp với |
| --- | --- | --- |
| Tham chiếu file | `file="SearchExamples.java"` | Java source hoặc file văn bản như properties, XML, HTML. |
| Tham chiếu class | `class=SearchExamples` | Source Java của một class có thể được phân giải theo tên class. |

Ví dụ với `file`:

~~~java
{@snippet file="SearchExamples.java" region="basic-search"}
~~~

Ví dụ với `class`:

~~~java
{@snippet class=SearchExamples region="basic-search"}
~~~

Khi cần minh họa file không phải Java, dùng `file`. Khi source là một class Java và muốn tham chiếu bằng tên class, `class` giúp diễn đạt rõ ý định.

External snippet không bị giới hạn bởi các hạn chế của inline snippet. Chẳng hạn, file external có thể chứa block comment `/* ... */` hoặc chuỗi ký tự `*/` mà không làm kết thúc documentation comment đang chứa `{@snippet}`.

## 10. Ví dụ hoàn chỉnh: trích hai vùng từ một file Java

Tạo cấu trúc:

~~~text
src/
└── demo/
    ├── OrderApiDoc.java
    └── snippet-files/
        └── OrderExamples.java
~~~

### 10.1. File external `OrderExamples.java`

~~~java
package demo;

import java.util.List;

public final class OrderExamples {
    private OrderExamples() {
    }

    public static void main(String[] args) {
        // @start region="create-order"
        String orderId = "ORD-1001";
        List<String> items = List.of("book", "pen");
        System.out.println(orderId + ": " + items);
        // @end region="create-order"

        // @start region="validate-order"
        boolean valid = !items.isEmpty() && orderId.startsWith("ORD-");
        if (!valid) {
            throw new IllegalArgumentException("Invalid order");
        }
        // @end region="validate-order"

        // @start region="complete-order"
        System.out.println("Order accepted");
        // @end region="complete-order"
    }
}
~~~

### 10.2. File tài liệu `OrderApiDoc.java`

~~~java
package demo;

/**
 * Tạo một đơn hàng:
 * {@snippet file="OrderExamples.java" region="create-order"}
 *
 * Kiểm tra đơn hàng:
 * {@snippet file="OrderExamples.java" region="validate-order"}
 *
 * Hoàn tất đơn hàng:
 * {@snippet file="OrderExamples.java" region="complete-order"}
 */
public final class OrderApiDoc {
}
~~~

### 10.3. Nội dung hiển thị

Snippet `create-order`:

~~~java
String orderId = "ORD-1001";
List<String> items = List.of("book", "pen");
System.out.println(orderId + ": " + items);
~~~

Snippet `validate-order`:

~~~java
boolean valid = !items.isEmpty() && orderId.startsWith("ORD-");
if (!valid) {
    throw new IllegalArgumentException("Invalid order");
}
~~~

Snippet `complete-order`:

~~~java
System.out.println("Order accepted");
~~~

Ba đoạn đều được lấy từ cùng file external. Các marker `@start`/`@end` không hiển thị. Phần import, class wrapper và các vùng khác không được đưa vào khi mỗi `{@snippet}` chọn một region cụ thể.

## 11. Kiểm chứng bằng `javac` và `javadoc`

Để xác nhận region hoạt động đúng, kiểm tra riêng file source và tài liệu HTML.

### 11.1. Biên dịch file external

Từ thư mục gốc của ví dụ:

~~~bash
javac -d out src/demo/snippet-files/OrderExamples.java
~~~

Nếu lệnh thành công, file external là compilation unit Java hợp lệ. Các marker `@start`/`@end` là comment nên không làm thay đổi cú pháp Java.

### 11.2. Sinh Javadoc

Chạy:

~~~bash
javadoc -d docs -sourcepath src demo
~~~

Javadoc sẽ tìm file trong `src/demo/snippet-files` và xử lý từng region được tham chiếu trong `OrderApiDoc.java`.

### 11.3. Xem HTML

Mở:

~~~text
docs/demo/OrderApiDoc.html
~~~

Kiểm tra:

1. Phần “Tạo một đơn hàng” chỉ có ba dòng thuộc region `create-order`.
2. Phần “Kiểm tra đơn hàng” chỉ có các dòng thuộc region `validate-order`.
3. Phần “Hoàn tất đơn hàng” chỉ có câu lệnh in trạng thái.
4. Không có dòng marker `@start` hoặc `@end` trong các khối mã.
5. Import, class wrapper và các vùng ngoài phạm vi không xuất hiện.

Nếu Javadoc báo không tìm thấy file, kiểm tra đường dẫn `snippet-files` hoặc `--snippet-path`. Nếu không lấy được vùng mong muốn, kiểm tra tên region ở ba vị trí: `@start`, `@end` và thuộc tính `region` của `{@snippet}`.

### 11.4. Kiểm tra file properties

Với file `application.properties`:

~~~properties
# @start region="server"
server.host=localhost
server.port=8080
# @end region="server"
logging.level=INFO
~~~

Trong Javadoc:

~~~java
{@snippet lang="properties" file="application.properties" region="server"}
~~~

Kết quả chỉ có hai thuộc tính server; dòng logging ở ngoài region không xuất hiện.

## 12. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Viết `region="main"` nhưng file không có marker tên `main`. | Tên vùng trong tag không khớp vùng được định nghĩa. | Đối chiếu chính xác tên ở `@start`, `@end` và `{@snippet}`. |
| Quên marker `@end`. | Region không có điểm kết thúc rõ ràng. | Thêm `@end region="..."` cho vùng tương ứng. |
| Dùng `@end region="other"` để đóng region `main`. | Marker kết thúc tên khác không đóng vùng cần chọn. | Dùng cùng tên region ở hai đầu. |
| Viết `// @start` trong file properties. | Properties dùng `#` làm comment. | Dùng `# @start region="..."` và `# @end region="..."`. |
| Đặt file ngoài nhưng không khai báo đường dẫn tìm kiếm. | Javadoc chỉ tìm ở `snippet-files` mặc định và các đường dẫn được cấu hình. | Đặt file đúng thư mục hoặc dùng `--snippet-path`. |
| Dùng đường dẫn tuyệt đối trong thuộc tính `file`. | External file được tham chiếu bằng đường dẫn tương đối theo quy tắc tìm kiếm snippet. | Dùng đường dẫn tương đối từ `snippet-files` hoặc gốc `--snippet-path`. |
| Nghĩ marker region là comment thông thường. | `@start`/`@end` là markup comment, bị lược khỏi đầu ra. | Kiểm tra source và HTML riêng biệt. |
| Nghĩ `region` trên `{@snippet}` giống `region` trên `@highlight`. | Một cái chọn nội dung hiển thị; cái kia xác định phạm vi của markup action. | Xác định rõ mục tiêu trước khi đặt thuộc tính. |
| Tạo quá nhiều region không tên. | Khó xác định marker kết thúc ghép với marker bắt đầu nào. | Đặt tên rõ ràng cho các region. |
| Tạo vùng chồng lấn nhưng không đặt tên. | Không thể xác định rõ quan hệ giữa các cặp marker. | Dùng tên riêng cho từng cặp bắt đầu/kết thúc. |
| Đưa cả file external vào snippet khi chỉ cần một đoạn. | Không có thuộc tính `region` nên toàn bộ file được chọn. | Đánh dấu vùng và thêm `region` vào `{@snippet}`. |
| Sửa source nhưng quên sinh lại Javadoc. | HTML hiện tại vẫn là bản được tạo từ lần chạy trước. | Chạy lại `javadoc` và kiểm tra HTML mới. |

## 13. Bài tập tự đánh giá

### Bài 1 — Chọn đúng một vùng

File external:

~~~java
// @start region="request"
var request = HttpRequest.newBuilder(uri).GET().build();
// @end region="request"

// @start region="response"
var response = client.send(request, BodyHandlers.ofString());
// @end region="response"
~~~

Muốn chỉ hiển thị phần gửi request, viết tag nào?

**Đáp án:**

~~~java
{@snippet file="HttpExamples.java" region="request"}
~~~

### Bài 2 — Vì sao marker không xuất hiện?

Trong file external có:

~~~java
// @start region="main"
System.out.println("Hello");
// @end region="main"
~~~

Vì sao snippet không hiển thị hai dòng marker?

**Đáp án:** Đây là markup comment dùng để xác định ranh giới region. Javadoc xử lý marker khi trích snippet và loại markup comment khỏi nội dung hiển thị.

### Bài 3 — Sửa lỗi trong file properties

Đoạn sau dùng sai ký hiệu comment:

~~~properties
// @start region="server"
server.host=localhost
// @end region="server"
~~~

**Đáp án:**

~~~properties
# @start region="server"
server.host=localhost
# @end region="server"
~~~

### Bài 4 — Chọn đúng thư mục

File tài liệu nằm trong package `demo` ở `src/demo/ApiDoc.java`. File snippet mặc định nên đặt ở đâu?

**Đáp án:** Trong `src/demo/snippet-files/`. Ví dụ `src/demo/snippet-files/ApiExamples.java` được tham chiếu bằng `{@snippet file="ApiExamples.java" region="main"}`.

### Bài 5 — Phân biệt hai thuộc tính region

`{@snippet file="Example.java" region="request"}` và `@highlight region="request"` có cùng mục đích không?

**Đáp án:** Không. Thuộc tính trên `{@snippet}` chọn vùng được đưa vào tài liệu. Thuộc tính trên `@highlight` xác định phạm vi mà thao tác làm nổi bật áp dụng.

### Bài 6 — Một file, nhiều snippet

Một file external có hai vùng `setup` và `cleanup`. Có thể tham chiếu cả hai vùng trong cùng documentation comment không?

**Đáp án:** Có. Tạo hai tag `{@snippet}` riêng, mỗi tag dùng cùng file nhưng một giá trị `region` khác nhau.

## Tổng kết

- `@start region="name"` và `@end region="name"` đánh dấu một vùng có tên trong file external.
- `{@snippet file="..." region="name"}` chỉ đưa nội dung trong vùng được chọn vào tài liệu.
- Marker region là markup comment nên không xuất hiện trong khối mã HTML; comment thông thường bên trong vùng vẫn có thể được giữ.
- Một file external có thể chứa nhiều region để tái sử dụng trong nhiều snippet.
- Dùng `snippet-files` dưới package chứa documentation comment hoặc cấu hình `--snippet-path` khi file nằm ở thư mục riêng.
- Java dùng `//`, properties dùng `#`; marker phải tuân theo cú pháp comment của định dạng nguồn.
- Region có thể lồng hoặc chồng lấn. Đặt tên rõ ràng giúp ghép marker và bảo trì dễ hơn.
- `region` của `{@snippet}` chọn nội dung hiển thị; `region` của markup action chọn phạm vi định dạng/thay thế/liên kết.
- Kiểm tra file Java bằng `javac` và nội dung HTML bằng `javadoc` để xác nhận cả source lẫn phần được trích.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Documentation Comment Specification, JDK 27, mục External snippets và Regions](https://download.java.net/java/early_access/jdk27/docs/specs/javadoc/doc-comment-spec.html#snippet): vị trí external file, marker `@start`/`@end`, vùng có tên/không tên và vùng chồng lấn.
2. [Oracle — JavaDoc Guide, JDK 26, chương External Snippets và Selecting Part of an External File](https://docs.oracle.com/en/java/javase/26/javadoc/javadoc-guide.pdf): ví dụ chọn named region trong Java source và properties file.
3. [Oracle — The javadoc Command, JDK 27, tùy chọn `--snippet-path`](https://download.virtualbox.org/java/early_access/jdk27/docs/specs/man/javadoc.html): đường dẫn tìm external snippet và thứ tự tìm kiếm.
4. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): thiết kế snippet được đưa vào Java 18 và tiếp tục được hỗ trợ trong JDK hiện đại.
