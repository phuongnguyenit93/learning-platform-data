# Dùng nhiều region trong một tệp ví dụ mà vẫn giữ từng đoạn có ngữ cảnh đầy đủ

## 1. Mục tiêu: một tệp nguồn, nhiều ví dụ có thể tái sử dụng

Từ **Java 18**, Javadoc hỗ trợ thẻ `{@snippet ...}` theo JEP 413. Tính năng này cho phép tài liệu API hiển thị mã nguồn từ nội dung inline hoặc từ tệp bên ngoài. Cơ chế này vẫn được hỗ trợ trong JDK hiện đại, bao gồm JDK 27.

Khi một tài liệu cần minh họa nhiều phần của cùng một chủ đề, bạn có thể đặt các đoạn ví dụ trong **một tệp external snippet**, đánh dấu từng đoạn bằng tên region, rồi tham chiếu từng region tại vị trí phù hợp trong Javadoc.

Ví dụ một tệp có thể chứa:

- Region `normalize`: ví dụ chuẩn hóa chuỗi Unicode.
- Region `group`: ví dụ gom nhóm và đếm phần tử.
- Region `sort`: ví dụ sắp xếp dữ liệu.

Trong tài liệu, mỗi region được gọi bằng một thẻ riêng:

```java
{@snippet file="TextExamples.java" region="normalize"}
{@snippet file="TextExamples.java" region="group"}
{@snippet file="TextExamples.java" region="sort"}
```

Mỗi thẻ chỉ hiển thị phần mã thuộc region được chọn. Cách tổ chức này giúp nhiều trang hoặc nhiều phần của cùng một trang dùng chung một nguồn ví dụ.

Điều cần thiết là mỗi region phải có đủ ngữ cảnh để người đọc hiểu đoạn mã được trích xuất: kiểu dữ liệu, biến đầu vào, lời gọi API, khai báo phương thức và các helper cần thiết. Nếu muốn ví dụ có thể sao chép và biên dịch riêng, hãy thiết kế từng region như một compilation unit hoặc một đoạn mã có hướng dẫn rõ ràng về vị trí cần đặt.

## 2. Region là gì?

Region là một khoảng dòng trong nội dung snippet. Region có thể được đặt tên hoặc để ẩn danh.

Trong tệp Java bên ngoài, dùng markup comment:

```java
// @start region=normalize
// Các dòng mã thuộc region normalize
// @end region=normalize
```

- `@start region=normalize` đánh dấu điểm bắt đầu region có tên `normalize`.
- `@end region=normalize` kết thúc đúng region đó.
- Thuộc tính `region="normalize"` trong thẻ `{@snippet}` yêu cầu Javadoc chọn vùng có tên tương ứng.

Các markup comment được Javadoc xử lý và không xuất hiện trong mã hiển thị cuối cùng. Nội dung mã ở giữa hai marker được đưa vào snippet.

Tên region là định danh do người viết tài liệu chọn. Nên dùng tên ngắn, có ý nghĩa theo mục đích của ví dụ, chẳng hạn:

- `normalize`
- `group`
- `sort`
- `read-file`
- `validate-input`

Đặt tên nhất quán giúp người đọc và người bảo trì nhận ra quan hệ giữa nơi khai báo region và nơi tham chiếu nó.

## 3. Chọn external snippet khi có nhiều phần của cùng một ví dụ

Snippet inline đặt trực tiếp trong comment:

```java
/**
 * {@snippet :
 *     var names = java.util.List.of("Ada", "Linus");
 *     System.out.println(names);
 * }
 */
```

Inline snippet phù hợp với ví dụ ngắn, chỉ dùng tại một vị trí. Khi nội dung dài hoặc cần tái sử dụng, external snippet dễ bảo trì hơn:

- Source code nằm trong tệp riêng, có thể mở bằng IDE.
- Nhiều region được tổ chức trong cùng một tệp.
- Có thể biên dịch và kiểm thử tệp nguồn bằng công cụ Java thông thường.
- Có thể chứa comment Java nhiều dòng như `/* ... */`, vốn khó đặt trực tiếp trong traditional Javadoc comment.
- Một region có thể được tham chiếu ở nhiều vị trí trong tài liệu.

Javadoc hỗ trợ hai cách chỉ định nguồn external snippet:

1. Thuộc tính `class` để tham chiếu một lớp Java.
2. Thuộc tính `file` để tham chiếu đường dẫn tệp tương đối.

Bài này dùng `file` để thể hiện rõ việc nhiều region cùng nằm trong một tệp.

## 4. Bố trí thư mục snippet-files

Giả sử source code của API được đặt trong:

```text
src/
└── com/
    └── example/
        ├── TextApi.java
        └── snippet-files/
            └── TextExamples.java
```

Thư mục `snippet-files` nằm cạnh source file chứa thẻ `{@snippet}`, bên trong thư mục package tương ứng.

Trong `TextApi.java`, có thể tham chiếu tệp external snippet bằng tên tương đối:

```java
package com.example;

/**
 * Các ví dụ xử lý văn bản.
 *
 * Chuẩn hóa chuỗi:
 * {@snippet file="TextExamples.java" region="normalize"}
 *
 * Đếm số lần xuất hiện:
 * {@snippet file="TextExamples.java" region="group"}
 */
public class TextApi {
}
```

Với cách bố trí này, Standard Doclet có thể tìm tệp trong thư mục `snippet-files` tương ứng mà không cần khai báo thêm `--snippet-path`.

Nếu đặt external snippets trong một thư mục độc lập, hãy truyền thư mục gốc đó bằng tùy chọn `--snippet-path` khi chạy Javadoc. Khi đó, giá trị `file` được giải quyết tương đối với đường dẫn snippet đã cấu hình.

Ví dụ:

```text
project/
├── src/
│   └── com/example/TextApi.java
└── docs-snippets/
    └── TextExamples.java
```

Lệnh tạo Javadoc:

```sh
javadoc --snippet-path docs-snippets -d build/docs -sourcepath src src/com/example/TextApi.java
```

Với dự án có Maven hoặc Gradle, cần kiểm tra cách build tool xử lý thư mục `snippet-files`. Một số cấu hình build có thể xem nhầm thư mục này như một phần của package source. Nếu điều đó xảy ra, đặt snippet trong thư mục riêng và dùng `--snippet-path` là lựa chọn phù hợp.

## 5. Tạo một tệp có nhiều region và mỗi region tự đủ ngữ cảnh

Tệp `src/com/example/snippet-files/TextExamples.java` dưới đây chứa hai ví dụ độc lập.

```java
// @start region=normalize
final class NormalizeExample {
    private static String normalize(String value) {
        return java.text.Normalizer.normalize(
            value,
            java.text.Normalizer.Form.NFC
        );
    }

    public static void main(String[] args) {
        String input = "Cafe\u0301";
        String result = normalize(input);

        System.out.println(result);
    }
}
// @end region=normalize

// @start region=group
final class GroupingExample {
    public static void main(String[] args) {
        var words = java.util.List.of(
            "java",
            "javadoc",
            "java"
        );

        var counts = words.stream().collect(
            java.util.stream.Collectors.groupingBy(
                java.util.function.Function.identity(),
                java.util.TreeMap::new,
                java.util.stream.Collectors.counting()
            )
        );

        System.out.println(counts);
    }
}
// @end region=group
```

Tệp này có hai lớp top-level không khai báo `public`. Vì vậy, chúng có thể cùng tồn tại trong một source file mà không vi phạm quy tắc tên tệp của public top-level class.

Mỗi region bao gồm toàn bộ lớp ví dụ:

- `normalize` có khai báo lớp, phương thức chuẩn hóa, đầu vào và điểm gọi.
- `group` có khai báo lớp, danh sách đầu vào, pipeline Stream, collector và điểm in kết quả.

Các tên API được viết đầy đủ bằng package name, ví dụ `java.text.Normalizer` và `java.util.stream.Collectors`. Cách viết này tránh phụ thuộc vào import nằm bên ngoài region. Khi Javadoc chỉ trích xuất một region, đoạn mã vẫn giữ đủ tên kiểu cần thiết để người đọc hiểu và có thể biên dịch độc lập.

Trong dự án thực tế, nếu muốn dùng import ngắn gọn, hãy đặt các import cần thiết bên trong phạm vi region hoặc thiết kế mỗi region chứa toàn bộ source context cần thiết. Không đặt import duy nhất ở đầu tệp rồi giả định snippet được trích xuất riêng sẽ tự nhận được các import đó.

## 6. Tham chiếu nhiều region trong cùng một comment Javadoc

Một tệp external snippet có thể được dùng nhiều lần trong cùng một documentation comment:

```java
package com.example;

/**
 * Các ví dụ xử lý văn bản.
 *
 * <h2>Chuẩn hóa Unicode</h2>
 * {@snippet file="TextExamples.java" region="normalize"}
 *
 * <h2>Đếm tần suất từ</h2>
 * {@snippet file="TextExamples.java" region="group"}
 */
public class TextApi {
}
```

Hai thẻ có cùng giá trị `file`, nhưng mỗi thẻ chọn một giá trị `region` khác nhau.

Javadoc sẽ hiển thị hai code block ở hai vị trí tương ứng. Các marker `@start` và `@end` không xuất hiện trong output.

Bạn cũng có thể tham chiếu cùng một region ở nhiều comment khác nhau:

```java
/**
 * Ví dụ chuẩn hóa:
 * {@snippet file="TextExamples.java" region="normalize"}
 */
public void normalizeText() {
}

/**
 * Cùng ví dụ chuẩn hóa, được dùng trong ngữ cảnh API khác:
 * {@snippet file="TextExamples.java" region="normalize"}
 */
public void compareNormalizedText() {
}
```

Cách tái sử dụng này hữu ích khi cùng một thao tác được mô tả trong overview, method detail và tutorial. Khi source example thay đổi, các vị trí tham chiếu cùng region sẽ nhận nội dung cập nhật khi tạo lại tài liệu.

## 7. Ngữ cảnh đầy đủ trong mỗi region

Đây là phần quan trọng nhất khi thiết kế một tệp có nhiều region. Javadoc chỉ trích xuất phần được chọn. Nó không tự thêm các import, biến, helper hay khai báo nằm bên ngoài region.

Một region quá nhỏ có thể hiển thị mã mà người đọc không hiểu được:

```java
// @start region=too-small
var result = normalize(input);
// @end region=too-small
```

Đoạn trên thiếu ít nhất:

- Kiểu hoặc nguồn khai báo `input`.
- Định nghĩa phương thức `normalize`.
- Ngữ cảnh cho biết kết quả được dùng như thế nào.

Nếu mục đích là giải thích riêng một lời gọi API, có thể chấp nhận snippet ngắn, nhưng phần văn bản xung quanh phải nói rõ các giả định và ngữ cảnh còn thiếu. Nếu muốn đoạn mã có thể sao chép và biên dịch riêng, hãy mở rộng region:

```java
// @start region=complete-normalize
final class CompleteNormalizeExample {
    private static String normalize(String input) {
        return java.text.Normalizer.normalize(
            input,
            java.text.Normalizer.Form.NFC
        );
    }

    public static void main(String[] args) {
        String input = "Cafe\u0301";
        System.out.println(normalize(input));
    }
}
// @end region=complete-normalize
```

Một region có ngữ cảnh đầy đủ nên cân nhắc các thành phần sau:

| Thành phần | Khi nào cần đưa vào region? |
| --- | --- |
| Import hoặc tên kiểu đầy đủ | Khi mã dùng kiểu bên ngoài package `java.lang`. |
| Khai báo lớp/interface/record | Khi muốn đoạn trích là một ví dụ hoàn chỉnh có thể sao chép. |
| Method signature | Khi phần thân phương thức không thể hiểu nếu thiếu tham số hoặc kiểu trả về. |
| Biến đầu vào | Khi lời gọi API phụ thuộc vào dữ liệu được chuẩn bị trước đó. |
| Helper method | Khi ví dụ gọi hàm tự định nghĩa. |
| Khởi tạo tài nguyên | Khi cần stream, file, connection hoặc object trước khi thực hiện thao tác. |
| Xử lý ngoại lệ | Khi đoạn mã gọi API có checked exception hoặc cần giải thích lỗi. |
| Đóng tài nguyên | Khi ví dụ dùng tài nguyên cần giải phóng. |
| Điểm gọi hoặc output | Khi người đọc cần biết cách chạy và quan sát kết quả. |

Không phải region nào cũng cần chứa một lớp hoàn chỉnh. Nếu chỉ minh họa một biểu thức hoặc một câu lệnh, hãy mô tả rõ đoạn mã được đặt ở đâu, biến nào đã tồn tại và các giả định cần có.

## 8. Chọn ranh giới region theo mục đích đọc

Không nên chọn ranh giới chỉ vì muốn giảm số dòng. Hãy chọn sao cho đoạn được trích xuất trả lời được một câu hỏi cụ thể.

Ví dụ, một tệp hướng dẫn xử lý tệp có thể chứa:

| Region | Nội dung nên bao gồm | Mục đích |
| --- | --- | --- |
| `create-path` | Khởi tạo Path, kiểm tra tên và in kết quả. | Giải thích cách tạo đường dẫn. |
| `read-utf8` | Đọc tệp bằng charset rõ ràng, xử lý IOException. | Giải thích cách đọc văn bản. |
| `write-utf8` | Tạo nội dung, ghi bằng UTF-8 và xử lý lỗi. | Giải thích cách ghi văn bản. |
| `walk-tree` | Khởi tạo root, duyệt cây và xử lý từng entry. | Giải thích duyệt thư mục. |

Mỗi vùng nên có ranh giới phản ánh một nhiệm vụ, không phải một số dòng tùy ý.

Nếu hai đoạn mã phụ thuộc cùng một helper, có ba lựa chọn:

1. Lặp lại helper cần thiết trong từng region để mỗi đoạn tự chứa.
2. Đưa helper vào mỗi ví dụ hoàn chỉnh, nhưng chấp nhận một ít mã lặp.
3. Tạo một region riêng cho helper và giải thích rằng người đọc cần kết hợp helper với region chính.

Với tài liệu nhập môn hoặc ví dụ có mục đích sao chép, lựa chọn thứ nhất thường dễ hiểu nhất. Với tài liệu nâng cao, lựa chọn thứ ba có thể giảm trùng lặp nếu mối quan hệ giữa các đoạn được giải thích rõ.

Không nên đặt helper duy nhất ngoài tất cả region rồi trích xuất từng method mà không chỉ ra phần phụ thuộc. Kết quả Javadoc khi đó có thể đẹp nhưng không đủ ngữ cảnh để người đọc sử dụng.

## 9. Marker region và quy tắc kết thúc

Cặp marker cơ bản:

```java
// @start region=read
var content = java.nio.file.Files.readString(path);
System.out.println(content);
// @end region=read
```

Tên ở `@end region=read` kết thúc region có tên `read`.

Có thể dùng `@end` không kèm tên để kết thúc region được mở gần nhất mà chưa có marker kết thúc tương ứng:

```java
// @start region=read
var content = java.nio.file.Files.readString(path);
// @end
```

Với tệp có nhiều vùng, nên dùng tên đầy đủ ở cả start và end. Điều này giúp người đọc nhận ra cặp marker và giảm nguy cơ đóng nhầm region khi chỉnh sửa.

Một số quy tắc thực hành:

- Viết đúng tên ở cả `@start` và `@end`.
- Không tái sử dụng một tên cho những vùng có ý nghĩa khác nhau.
- Đặt marker gần phần mã được chọn.
- Giữ marker trong comment hợp lệ của ngôn ngữ chứa snippet.
- Không chèn văn bản giải thích vào giữa marker nếu văn bản đó không thuộc ví dụ.
- Sau khi đổi tên region, tìm và cập nhật mọi thẻ `{@snippet}` tham chiếu tới nó.

Markup comments không xuất hiện trong tài liệu được tạo. Nếu marker được đặt cùng dòng với mã nguồn, phần mã vẫn thuộc nội dung dòng đó; phần markup comment được loại bỏ khi hiển thị.

## 10. Nhiều region không nhất thiết phải lồng nhau

Các region độc lập thường là cách tổ chức dễ bảo trì nhất:

```java
// @start region=first
class FirstExample {
    public static void main(String[] args) {
        System.out.println("First");
    }
}
// @end region=first

// @start region=second
class SecondExample {
    public static void main(String[] args) {
        System.out.println("Second");
    }
}
// @end region=second
```

Mỗi cặp marker có phạm vi riêng và có thể được tham chiếu độc lập.

Javadoc cũng hỗ trợ region lồng nhau và region chồng lấn. Tuy nhiên, chồng lấn thường khó đọc hơn vì ranh giới của các vùng không còn đơn giản theo thứ tự mở/đóng. Nếu thật sự cần region chồng lấn, hãy đặt tên rõ ràng cho từng vùng và dùng marker kết thúc có tên để xác định chính xác cặp tương ứng.

Ví dụ minh họa region lồng:

```java
// @start region=whole
class Example {
    // @start region=method
    void run() {
        System.out.println("Run");
    }
    // @end region=method
}
// @end region=whole
```

- Tham chiếu region `whole` để hiển thị toàn bộ lớp.
- Tham chiếu region `method` để hiển thị riêng phần phương thức.

Nếu chọn region `method`, phần khai báo lớp bên ngoài không được tự động thêm vào. Vì vậy, hãy quyết định xem một đoạn method riêng có đủ ngữ cảnh cho mục đích học hay không.

## 11. Kết hợp region với markup như highlight hoặc replace

Region có thể được dùng để chọn đoạn mã, đồng thời các markup tag khác điều chỉnh cách hiển thị.

Ví dụ:

```java
// @start region=normalize-highlight
final class NormalizeHighlightExample {
    public static void main(String[] args) {
        String input = "Cafe\u0301";
        String result = java.text.Normalizer.normalize(
            input,
            java.text.Normalizer.Form.NFC
        ); // @highlight substring="Normalizer.normalize" type=highlighted

        System.out.println(result);
    }
}
// @end region=normalize-highlight
```

Thẻ `@highlight` đánh dấu lời gọi API cần chú ý. Marker region xác định phạm vi được đưa vào tài liệu; highlight xác định phần cần nhấn mạnh trong phạm vi đó.

Có thể dùng `@replace` để thay một phần nội dung trong output, chẳng hạn ẩn một giá trị dài hoặc thay một placeholder. Tuy nhiên, nếu mục tiêu là ví dụ có thể sao chép và biên dịch, hãy giữ source code hợp lệ và chỉ thay nội dung khi đã hiểu tác động đến ví dụ hiển thị.

Không dùng highlight hoặc replace để che đi một dependency thiết yếu mà người đọc cần biết. Presentation markup chỉ cải thiện cách đọc; nó không bổ sung logic bị thiếu cho region.

## 12. Tạo Javadoc và xác minh các region được trích xuất

Với cấu trúc thư mục ở phần 4, chạy từ thư mục dự án:

```sh
javadoc -d build/docs -sourcepath src src/com/example/TextApi.java
```

Sau khi lệnh hoàn tất:

1. Mở `build/docs/com/example/TextApi.html`.
2. Tìm phần mô tả của `TextApi`.
3. Kiểm tra code block đầu hiển thị lớp `NormalizeExample`.
4. Kiểm tra code block thứ hai hiển thị lớp `GroupingExample`.
5. Xác nhận marker `@start` và `@end` không xuất hiện trong code block.
6. Xác nhận hai đoạn không bị trộn nội dung hoặc lấy nhầm region.

Nếu Javadoc không tìm thấy tệp hoặc region, kiểm tra lại:

- Tên file trong thuộc tính `file`.
- Đường dẫn `snippet-files` tương ứng với package.
- Giá trị region trong thẻ Javadoc.
- Cặp marker trong tệp external snippet.
- Tùy chọn `--snippet-path` nếu dùng thư mục snippet riêng.

Javadoc Standard Doclet xử lý và hiển thị snippet; nó **không biên dịch hoặc chạy thử mã snippet**. Vì vậy, việc tạo tài liệu thành công chưa chứng minh ví dụ Java biên dịch được.

## 13. Biên dịch và kiểm tra mã nguồn snippet độc lập

Tệp ví dụ ở phần 5 có hai lớp package-private. Có thể biên dịch toàn bộ tệp:

```sh
mkdir -p build/snippet-classes
javac -d build/snippet-classes src/com/example/snippet-files/TextExamples.java
```

Nếu lệnh hoàn tất không có lỗi, source file có cú pháp và kiểu dữ liệu hợp lệ trên JDK đang dùng.

Để xác minh từng region sau khi trích xuất, sao chép nội dung hiển thị của từng code block vào một tệp riêng:

```text
NormalizeExample.java
GroupingExample.java
```

Sau đó biên dịch:

```sh
javac NormalizeExample.java GroupingExample.java
```

Vì mỗi đoạn chứa một lớp hoàn chỉnh và dùng tên kiểu đầy đủ, không cần ghép import từ đoạn khác.

Trong dự án lớn, có thể đưa external snippet vào quy trình kiểm thử tự động. Các bước thường gồm:

1. Xác định tệp snippet và region.
2. Trích xuất nội dung region.
3. Chuẩn hóa indentation nếu cần.
4. Biên dịch bằng `javac` hoặc build tool.
5. Chạy ví dụ nếu cần xác minh hành vi.
6. Tạo lại Javadoc và xem output cuối.

Đặc tả Javadoc có hướng dẫn kiểm thử snippet bằng công cụ ngoài; việc biên dịch và chạy không phải nhiệm vụ của Standard Doclet.

## 14. Khi nào dùng file attribute và khi nào dùng class attribute?

Hai cách tham chiếu external Java snippet:

| Cách tham chiếu | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| `file` | `{@snippet file="TextExamples.java" region="normalize"}` | Muốn trỏ trực tiếp tới một tệp snippet trong `snippet-files` hoặc `--snippet-path`. |
| `class` | `{@snippet class=ExternalExamples region=normalize}` | Muốn tham chiếu external Java source theo tên lớp `ExternalExamples`. |

Cả hai cách đều có thể dùng với region. Chọn một kiểu nhất quán trong cùng tài liệu để người bảo trì dễ tìm nguồn.

Với ví dụ có nhiều region, thuộc tính `file` thể hiện rõ rằng nhiều thẻ đang dùng cùng một tệp. Nếu dùng `class`, bảo đảm external source thực sự khai báo lớp có tên tương ứng (ví dụ `ExternalExamples`) và file nguồn có thể được Javadoc định vị theo quy tắc source path. Không dùng `class=TextExamples` cho tệp minh họa ở phần 5 vì tệp đó chứa `NormalizeExample` và `GroupingExample`, không khai báo lớp `TextExamples`.

## 15. Các lỗi tổ chức region thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Javadoc không hiển thị nội dung mong đợi | Thẻ chọn sai tên region. | So sánh chính xác thuộc tính `region` với marker. |
| Snippet chứa quá ít dòng | Region chỉ bao quanh lời gọi API. | Mở rộng region để chứa khai báo, đầu vào và helper cần thiết. |
| Snippet có tên biến không được khai báo | Biến nằm ngoài vùng được trích xuất. | Đưa phần khởi tạo vào region hoặc giải thích rõ ngữ cảnh bên ngoài. |
| Snippet dùng kiểu không tìm thấy | Import nằm ngoài region. | Dùng fully qualified name hoặc đưa import vào phạm vi ví dụ. |
| Marker xuất hiện trong code block | Comment không được nhận diện là markup hợp lệ. | Kiểm tra cú pháp comment và tên tag. |
| Một region lấy nhầm phần mã | Marker kết thúc không khớp tên hoặc đặt sai vị trí. | Dùng cặp `@start region=name` và `@end region=name`. |
| Đổi tên region làm một số snippet hỏng | Thẻ Javadoc vẫn tham chiếu tên cũ. | Cập nhật mọi vị trí tham chiếu và tạo lại Javadoc. |
| Hai snippet bị lẫn nội dung | Ranh giới region chồng lấn hoặc đặt sai. | Dùng region độc lập, có tên riêng; chỉ chồng lấn khi thật sự cần. |
| Javadoc thành công nhưng code không biên dịch | Standard Doclet không biên dịch snippet. | Biên dịch source snippet riêng bằng `javac` hoặc build tool. |
| Build tool xử lý sai thư mục snippet-files | Công cụ build xem nhầm thư mục này như package source. | Đặt snippets trong thư mục riêng và truyền `--snippet-path`. |
| Snippet hiển thị nhưng thiếu helper | Helper nằm ngoài region. | Lặp lại helper, gộp helper vào ví dụ hoặc giải thích dependency rõ ràng. |
| Snippet quá dài, khó đọc | Một region chứa nhiều mục đích khác nhau. | Tách thành nhiều region theo từng nhiệm vụ. |

## 16. Quy trình thiết kế một tệp nhiều region dễ bảo trì

Khi bắt đầu một bộ ví dụ cho API:

1. Liệt kê các thao tác người đọc cần hiểu.
2. Chọn một region cho mỗi thao tác hoặc một nhóm thao tác có liên quan chặt chẽ.
3. Viết từng region với đầu vào, kiểu dữ liệu, lời gọi API và kết quả cần thiết.
4. Kiểm tra region có thể đọc độc lập khi không thấy các dòng bên ngoài.
5. Đặt tên region theo mục đích, tránh tên chung chung như `part1` hoặc `sample2`.
6. Tham chiếu cùng file bằng nhiều thẻ `{@snippet}`.
7. Tạo Javadoc và xem từng code block được trích xuất.
8. Biên dịch các ví dụ bằng `javac` hoặc build tool.
9. Cập nhật đồng thời source snippet và các thẻ tham chiếu khi thay đổi tên region.
10. Chạy lại kiểm tra Javadoc và compile sau mỗi thay đổi có ảnh hưởng tới ranh giới.

Có thể dùng một checklist ngắn khi review:

- [ ] Mỗi region có tên dễ hiểu.
- [ ] Mỗi marker start có marker end tương ứng.
- [ ] Không có region nào vô tình bao gồm ví dụ kế tiếp.
- [ ] Mỗi đoạn có đủ context theo mục tiêu học.
- [ ] Các import hoặc kiểu phụ thuộc đã được cung cấp.
- [ ] Mọi thẻ Javadoc tham chiếu đúng tên file và region.
- [ ] Output Javadoc đã được xem lại.
- [ ] Source snippet đã được biên dịch hoặc kiểm thử độc lập.

## 17. Bài tập tự kiểm tra

1. Tạo một external snippet file có hai region tên `first` và `second`.
2. Viết hai thẻ `{@snippet file="..." region="..."}` để hiển thị từng region trong cùng một documentation comment.
3. Đưa một lớp hoàn chỉnh vào từng region và xác nhận mỗi đoạn có thể được sao chép riêng.
4. Thử đặt một helper bên ngoài region. Quan sát snippet bị thiếu ngữ cảnh như thế nào.
5. Di chuyển helper vào region và tạo lại Javadoc.
6. Thử dùng fully qualified class name để loại bỏ phụ thuộc vào import bên ngoài.
7. Tạo một region lồng trong region khác và so sánh output khi tham chiếu region ngoài với region trong.
8. Đổi tên một region nhưng giữ nguyên thẻ tham chiếu cũ. Quan sát chẩn đoán khi tạo Javadoc.
9. Biên dịch tệp external snippet bằng `javac`. Sau đó thử biên dịch riêng từng đoạn đã trích xuất.
10. Chuyển tệp snippet sang thư mục riêng và tạo Javadoc với `--snippet-path`.
11. Kết hợp `@highlight` trong một region và kiểm tra phần mã được nhấn mạnh trong HTML.
12. Giải thích vì sao tạo Javadoc thành công không đồng nghĩa tất cả snippet đều biên dịch hoặc chạy được.

**Tiêu chí hoàn thành:** bạn tổ chức được nhiều named region trong một external snippet file, tham chiếu từng vùng từ Javadoc, thiết kế ranh giới giữ đủ ngữ cảnh, phân biệt việc trích xuất với việc biên dịch snippet, và biết xác minh output bằng Javadoc cùng `javac`.

## 18. Tài liệu tham khảo

- [Oracle Java SE 26 — Documentation Comment Specification, snippet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html): cú pháp `{@snippet}`, external snippet, `file`/`class`, vị trí `snippet-files`, `--snippet-path`, markup comments và region.
- [Oracle — Programmer's Guide to Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): hướng dẫn inline/external snippets, named region, nhiều region trong một tệp, nested/overlapping region và kiểm thử snippet.
- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): giới thiệu tính năng snippet trong Javadoc từ JDK 18.
- [Oracle Java SE 26 — The javadoc Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html): tùy chọn của công cụ Javadoc, bao gồm đường dẫn tìm snippet.
