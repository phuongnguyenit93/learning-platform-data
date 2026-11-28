# Markup comment trong snippet và phần nội dung được loại khỏi đầu ra hiển thị

## Mục tiêu bài học

Từ **Java 18 (JEP 413)**, công cụ `javadoc` hỗ trợ thẻ `{@snippet ...}` để đưa ví dụ mã vào tài liệu API. Cơ chế này tiếp tục được hỗ trợ trong các JDK hiện đại, bao gồm JDK 27. Khi viết snippet, ta có thể chèn **markup comment** ngay trong mã ví dụ để chỉ dẫn `javadoc` tô nổi bật, tạo liên kết, thay thế văn bản hiển thị hoặc đánh dấu vùng mã.

Sau bài này, bạn có thể:

- Nhận ra đâu là **comment điều khiển cách hiển thị** và đâu là comment thông thường của mã Java.
- Dự đoán chính xác phần nào bị lược khỏi HTML do `javadoc` sinh ra và phần mã nào vẫn được giữ.
- Dùng marker `@start`, `@end` với thuộc tính `region` để lấy một đoạn từ file snippet bên ngoài.
- Biết khi nào cần dùng dấu `:` ở cuối markup comment để áp dụng chỉ dẫn lên **dòng tiếp theo**.
- Phân biệt việc **ẩn markup comment**, **chọn region** và **thay thế văn bản hiển thị**; đây là ba hành vi khác nhau.

## 1. Markup comment là gì?

Một `{@snippet}` có thể chứa mã trực tiếp trong Javadoc (*inline snippet*) hoặc tham chiếu đến file riêng (*external snippet*). Khi xử lý snippet, *standard doclet* của `javadoc` nhận biết một số thẻ điều khiển xuất hiện trong comment theo cú pháp ngôn ngữ của đoạn mã.

Với Java, dạng thông dụng là:

```java
int result = 1 + 2; // @highlight substring="result"
```

Ở đây:

- `int result = 1 + 2;` là **nội dung ví dụ** cần hiển thị.
- `// @highlight substring="result"` là **markup comment**: một chỉ dẫn dành cho `javadoc`.
- Khi sinh HTML, `javadoc` giữ dòng lệnh và tô nổi bật `result` nhưng **loại phần comment `// @highlight ...` khỏi mã hiển thị**.

Đó là lý do tác giả có thể để thông tin định dạng ngay cạnh ví dụ trong mã nguồn mà người đọc tài liệu không phải nhìn thấy các chỉ dẫn này.

### Các markup tag thường gặp

| Thẻ trong markup comment | Tác dụng đối với bản hiển thị |
| --- | --- |
| `@highlight` | Tô nổi bật một dòng, chuỗi con (`substring`) hoặc phần khớp biểu thức chính quy (`regex`). |
| `@link` | Biến phần văn bản được chọn thành liên kết tới phần tử API. |
| `@replace` | Thay phần văn bản được chọn **trong snippet hiển thị** bằng giá trị `replacement`. |
| `@start region=...` | Đánh dấu điểm bắt đầu một vùng mã có tên. |
| `@end region=...` | Đánh dấu điểm kết thúc vùng mã tương ứng. |

Đối với `@highlight`, `@link` và `@replace`, có thể thêm `region` để mở rộng phạm vi tác động từ một dòng sang nhiều dòng. Bài này tập trung vào quy tắc **comment nào biến mất** và **mã nào được hiển thị**; các chức năng định dạng cụ thể chỉ được dùng để minh họa quy tắc đó.

## 2. Quy tắc loại nội dung khỏi đầu ra

Hãy tách hai tầng: **mã dùng để tạo ví dụ** và **chỉ dẫn trình bày ví dụ**.

| Trong nội dung snippet | Điều người đọc thấy trong khối mã của Javadoc |
| --- | --- |
| `int n = 3; // @highlight substring="n"` | Dòng `int n = 3;` vẫn có mặt; ký tự `n` được tô nổi bật, còn markup comment không xuất hiện. |
| `// @start region="main"` ở một dòng riêng | Dòng chỉ chứa marker không xuất hiện trong khối mã. |
| `// @end region="main"` ở một dòng riêng | Dòng chỉ chứa marker không xuất hiện trong khối mã. |
| `int n = 3; // Số lượng phần tử` | Comment Java thông thường được giữ cùng với dòng mã. |
| `// @unknown` (tên thẻ không được nhận biết) | Không được xử lý như markup comment; comment vẫn xuất hiện trong đầu ra. |

**Cần nhớ:** Việc bỏ `// @highlight ...`, `// @start ...`, `// @end ...` ra khỏi khối mã **không có nghĩa** `javadoc` tự động loại bỏ cả dòng lệnh mà comment đó gắn vào. Nếu markup comment đứng sau một câu lệnh, câu lệnh vẫn được hiển thị. Nếu nó đứng trên một dòng riêng, thông thường cả dòng chỉ dẫn đó sẽ biến mất.

Điều kiện quan trọng là đó phải là **markup comment hợp lệ và được nhận diện**. Comment chứa tên tag lạ có thể được giữ nguyên; comment dùng tag đã biết nhưng viết sai cú pháp có thể khiến `javadoc` báo lỗi. Vì vậy không nên mặc định mọi `// @...` đều bị ẩn.

## 3. Ví dụ inline: mã được giữ, chỉ dẫn biến mất

Giả sử file `InlineMarkupExample.java` có nội dung sau:

```java
/**
 * Minh họa markup comment trong một inline snippet.
 *
 * {@snippet :
 *     int count = 2;                  // @highlight substring="count"
 *     System.out.println(count);     // In số lượng hiện có
 *     // @highlight substring="done" :
 *     System.out.println("done");
 * }
 */
public class InlineMarkupExample {
}
```

Khối mã mà người đọc nhìn thấy trong tài liệu Javadoc có nội dung chữ như sau (phần tô nổi bật là hiệu ứng HTML, nên không thể hiện trong khối văn bản thuần):

```java
int count = 2;
System.out.println(count);     // In số lượng hiện có
System.out.println("done");
```

Giải thích từng trường hợp:

1. `// @highlight substring="count"` nằm **cuối dòng**. Nó chỉ định tô nổi bật `count` của chính dòng đó, sau đó bị bỏ khỏi đầu ra; `int count = 2;` vẫn còn.
2. `// In số lượng hiện có` là comment Java thông thường, không chứa markup tag được nhận diện, nên được hiển thị như một phần ví dụ.
3. `// @highlight substring="done" :` là markup comment **đứng riêng**, kết thúc bằng `:`. Nó tác động lên dòng `System.out.println("done");` ở ngay sau, còn bản thân dòng chỉ dẫn bị loại khỏi khối mã.

Ví dụ cho thấy nguồn Javadoc có thể chứa thêm thông tin để công cụ sinh tài liệu định dạng mã mà không đưa các thông tin kỹ thuật đó vào ví dụ cho người học.

### Dấu `:` ở cuối comment thay đổi điều gì?

Theo mặc định, markup tag áp dụng cho **dòng có comment**:

```java
String label = "OK"; // @highlight substring="label"
```

Muốn tác động đến dòng kế tiếp, hãy đặt chỉ dẫn trên dòng riêng và thêm `:` ở cuối:

```java
// @highlight substring="label" :
String label = "OK";
```

Hai cách có thể tạo cùng kết quả tô nổi bật đối với `label`; cả hai đều bỏ markup comment khi xuất HTML. Dạng dòng riêng hữu ích nếu chỉ dẫn dài hoặc không thể chèn comment vào chính dòng cần định dạng.

Ví dụ với snippet `lang="properties"`: file properties dùng comment bắt đầu bằng `#`, không phải `//`. Quy tắc vẫn tương tự:

```java
/**
 * {@snippet lang="properties" :
 *     # @highlight substring="localhost" :
 *     service.host=localhost
 * }
 */
public class PropertiesDoc {
}
```

Phần văn bản hiển thị là `service.host=localhost`, trong đó `localhost` được đánh dấu nổi bật; dòng `# @highlight ... :` không hiện ra. Không nên chèn `//` vào dòng cấu hình `.properties` chỉ vì ví dụ đặt trong Javadoc.

## 4. Region: bỏ marker và chỉ hiển thị phần mã đã chọn

Đối với file mã dài, có thể muốn tài liệu chỉ hiện một vài dòng mà không phải sao chép thủ công. Khi đó dùng **external snippet** và một region có tên. Đây là trường hợp có **hai lý do khác nhau** làm nội dung không xuất hiện:

1. Các dòng marker `@start` / `@end` bị bỏ vì chúng là markup comment.
2. Những dòng **nằm ngoài region được yêu cầu** bị bỏ vì thẻ `{@snippet ... region="..."}` chỉ chọn phần mã trong vùng ấy.

Giả sử đặt các file như sau (cùng thư mục chứa lớp được ghi tài liệu):

```text
SearchApi.java
snippet-files/
└── LookupExample.java
```

Trong `SearchApi.java`:

```java
/**
 * Ví dụ chuẩn hóa chuỗi đầu vào:
 * {@snippet file="LookupExample.java" region="api"}
 */
public class SearchApi {
}
```

Trong `snippet-files/LookupExample.java`:

```java
public final class LookupExample {
    public static void run() {
        String input = "  hello ";

        // @start region="api"
        String clean = input.strip(); // @highlight substring="strip"
        System.out.println(clean);
        // @end region="api"

        System.out.println("Log sau ví dụ");
    }
}
```

Nội dung chữ được hiển thị trong Javadoc của `SearchApi`:

```java
String clean = input.strip();
System.out.println(clean);
```

Ở đây, `String input = ...`, câu lệnh log và cặp khai báo lớp/phương thức không xuất hiện vì chúng nằm **ngoài region `api`**. Hai marker `// @start ...` và `// @end ...` không xuất hiện vì là markup comment. Ngay bên trong region, phần `// @highlight ...` cũng bị loại, nhưng câu lệnh gọi `strip()` vẫn xuất hiện và tên phương thức được tô nổi bật. `String.strip()` là API ổn định từ Java 11, thích hợp làm ví dụ với JDK 18 trở lên.

Nếu đổi thành `{@snippet file="LookupExample.java"}` và bỏ thuộc tính `region`, phần mã bên ngoài `api` có thể được đưa vào snippet hiển thị; cặp marker vẫn không biến thành dòng lệnh hiển thị. Vì vậy **`@start` / `@end` không phải lệnh “ẩn đoạn ở giữa”**. Chúng định nghĩa vùng để thẻ `@snippet` tham chiếu hoặc giới hạn phạm vi tác động của markup khác.

### Region dùng để làm gì ngoài chọn nội dung?

Khi cần định dạng nhiều dòng, một markup tag như `@highlight region="names" substring="name"` có thể bắt đầu một vùng tác động và kết thúc tại `@end region="names"`. Chọn region bằng thuộc tính của thẻ `@snippet` và dùng region làm phạm vi tô nổi bật là **hai khả năng khác nhau**; trong cả hai trường hợp, các comment đánh dấu đều không phải nội dung cần hiện ra.

## 5. Thay thế văn bản hiển thị không xóa mã nguồn

`@replace` là một ví dụ khác cần phân biệt với “loại comment”:

```java
int retryLimit = 3; // @replace substring="3" replacement="..."
```

Trong HTML được sinh ra, ví dụ có thể xuất hiện như sau:

```java
int retryLimit = ...;
```

Đã xảy ra **hai** phép biến đổi trình bày: markup comment biến mất, còn ký tự `3` được thay bằng `...` theo chỉ dẫn `@replace`. File nguồn vẫn chứa câu lệnh Java `int retryLimit = 3;`; `javadoc` không chỉnh sửa file đó. Do đó không dùng `@replace` như cách che dữ liệu bí mật: dữ liệu vẫn tồn tại trong mã nguồn và có thể lộ ở nơi khác.

Tương tự, `@link` có thể biến một phần mã thành liên kết API, `@highlight` có thể thêm định dạng; các thẻ đó chỉ điều khiển bản tài liệu được tạo ra.

## 6. Các lỗi dễ gặp

| Nhầm lẫn hoặc lỗi | Cách hiểu và sửa |
| --- | --- |
| Tưởng `// @highlight` sẽ hiện như một comment Java bình thường. | Với markup hợp lệ, phần comment là chỉ dẫn cho `javadoc`, bị loại khỏi snippet trong HTML. |
| Tưởng `// @start region="demo"` làm ẩn nội dung phía sau nó. | Marker chỉ **bắt đầu định nghĩa vùng**; muốn trích một vùng trong external snippet, chỉ rõ `region="demo"` trên `{@snippet ...}`. |
| Viết `// @highlight substring="x"` ở dòng riêng mà muốn tô dòng kế. | Thêm dấu `:` ở cuối comment để áp dụng cho dòng tiếp theo, hoặc đặt comment ngay cuối dòng cần tô. |
| Viết sai tên tag, chẳng hạn `// @higlight`. | Tên không được nhận diện có thể xuất hiện nguyên văn trong tài liệu; sửa thành `@highlight`. |
| Dùng tag đúng tên nhưng tham số không hợp lệ. | `javadoc` có thể báo lỗi khi xử lý snippet; cần đọc thông báo và sửa cú pháp thay vì đoán đầu ra. |
| Đưa `// @start` hay `// @end` vào ví dụ mà không kiểm tra cặp vùng. | Ghép region có tên nhất quán, sau đó chạy `javadoc` và xem khối mã thực tế trong HTML. |
| Tưởng comment `// Ghi chú` cũng sẽ bị loại. | Comment mã nguồn thông thường là nội dung của ví dụ và vẫn có thể hiển thị. |
| Dùng inline snippet chứa `*/` hoặc dấu ngoặc nhọn không cân bằng. | Với comment Javadoc dạng `/** ... */`, chuỗi `*/` kết thúc comment; inline snippet cũng yêu cầu cặp `{` và `}` cân bằng. Dùng external snippet khi cần mã phức tạp. |

Một điểm cần lưu ý: `@hidden` của Javadoc là một **thẻ tài liệu khác**, không phải tên markup tag dùng để tự động ẩn các dòng mã bên trong `@snippet`. Với chủ đề này, hãy dựa vào **quy tắc bỏ markup comment**, **phạm vi region** và **quy tắc `@replace`**.

## 7. Tự kiểm chứng trên JDK đang dùng

Với ví dụ inline ở mục 3, lưu file `InlineMarkupExample.java`, rồi chạy trong thư mục chứa file:

```bash
javadoc -d docs InlineMarkupExample.java
```

Mở tài liệu sinh ra của lớp `InlineMarkupExample`, tìm khối mã của snippet và kiểm tra các điểm sau:

1. Dòng `int count = 2;` và lời gọi `println` vẫn xuất hiện.
2. Các chuỗi điều khiển `@highlight` không còn nằm trong **khối mã ví dụ**; `count` và `done` được tô nổi bật theo quy tắc.
3. Comment `// In số lượng hiện có` vẫn xuất hiện.

Với ví dụ external ở mục 4, đặt `LookupExample.java` đúng trong `snippet-files/`, rồi chạy:

```bash
javadoc -d docs SearchApi.java
```

Kiểm tra rằng chỉ hai câu lệnh trong region `api` được đưa vào khối mã của `SearchApi`. Nếu đang dùng thư mục nguồn hoặc đường dẫn khác, cần cấu hình đường dẫn snippet cho phù hợp; `javadoc` còn hỗ trợ tùy chọn `--snippet-path` để tìm các file ngoài thư mục `snippet-files` thông thường.

Quy tắc kiểm chứng tốt nhất là **nhìn đầu ra HTML được sinh**, thay vì chỉ nhìn comment trong file Java: văn bản cuối cùng có thể đã được tô nổi bật, thay thế hoặc giới hạn bởi region.

## 8. Bài tập tự đánh giá

**Bài 1.** Xét đoạn inline snippet:

```java
{@snippet :
    String action = "read"; // @highlight substring="action"
    // @highlight substring="read" :
    System.out.println("read");
    // Ghi chú dành cho người đọc
}
```

Hỏi: Trong **khối mã được hiển thị**, những dòng nào còn lại?

**Đáp án:** Ba dòng `String action = "read";`, `System.out.println("read");` và `// Ghi chú dành cho người đọc` còn lại. Hai phần `@highlight` bị loại; `action` ở dòng đầu và `read` ở dòng thứ hai được tô nổi bật. Comment cuối không phải markup comment nên vẫn hiển thị.

**Bài 2.** Một file ngoài có `// @start region="example"` trước hai câu lệnh, `// @end region="example"` sau chúng và thêm năm câu lệnh ngoài vùng này. Tài liệu sử dụng `{@snippet file="Example.java" region="example"}`. Hỏi: Các marker và năm câu lệnh ngoài vùng có xuất hiện không?

**Đáp án:** Không. Marker không xuất hiện vì là markup comment; năm câu lệnh bên ngoài không xuất hiện vì `@snippet` chỉ chọn region `example`. Đây là hai nguyên nhân loại nội dung khác nhau.

## Tóm tắt kiến thức

- **Markup comment hợp lệ** là chỉ dẫn để `javadoc` định dạng hoặc chọn nội dung; chính comment đó bị lược khỏi khối mã sinh ra.
- **Mã cùng dòng được giữ**, trừ khi không thuộc region được chọn hoặc có phép biến đổi hiển thị khác. Comment Java thông thường vẫn là nội dung ví dụ.
- `:` ở cuối markup comment chuyển phạm vi tác động sang dòng tiếp theo.
- `@start` / `@end` xác định vùng; **thuộc tính `region` của `{@snippet}`** quyết định trích phần nào của file ngoài.
- `@replace` thay chữ trong đầu ra hiển thị, không chỉnh sửa mã nguồn. Cần kiểm tra HTML sau khi chạy `javadoc`.

## Nguồn tham khảo chính thức

- [JDK 27 — JavaDoc Documentation Comment Specification, mục `snippet`](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html#snippet): quy tắc markup comment, region, định dạng và xử lý lỗi.
- [Oracle JavaDoc Guide — Snippets (JDK 26)](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): các ví dụ trực quan về inline snippet, external snippet, markup comment và dấu `:`.
- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): đề xuất đã đưa tính năng `@snippet` vào JDK 18.
