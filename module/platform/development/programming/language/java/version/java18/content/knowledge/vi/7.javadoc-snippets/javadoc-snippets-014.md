# Chọn inline, external hoặc hybrid theo kích thước ví dụ và khả năng kiểm thử

## 1. Mục tiêu và bối cảnh

JEP 413 đưa thẻ `{@snippet ...}` vào Javadoc từ **JDK 18**. Tính năng này vẫn được Standard Doclet hỗ trợ trên JDK hiện đại để trình bày mã và văn bản có cấu trúc trong tài liệu API. Có ba cách cung cấp nội dung snippet:

- **Inline:** viết toàn bộ nội dung ngay trong comment Javadoc.
- **External:** tham chiếu một tệp hoặc lớp Java nằm ngoài comment.
- **Hybrid:** vừa viết nội dung inline, vừa tham chiếu nguồn external tương ứng.

Việc chọn cách nào ảnh hưởng đến khả năng đọc source, khả năng tái sử dụng và cách kiểm thử ví dụ. Không có ngưỡng số dòng cố định để quyết định. Hãy xem ví dụ có ngắn và tự chứa không, có cần chạy được không, có được dùng ở nhiều nơi không, và người bảo trì có cần nhìn thấy nội dung ngay cạnh mô tả API hay không.

Sau bài học, bạn có thể:

- Chọn inline cho ví dụ ngắn, đơn giản và dễ hiểu tại chỗ.
- Chọn external cho ví dụ dài, nhiều vùng hoặc cần biên dịch/chạy bằng công cụ thông thường.
- Chọn hybrid khi muốn giữ ví dụ trong comment nhưng Standard Doclet đối chiếu kết quả đã xử lý với nguồn ngoài.
- Hiểu những giới hạn của inline và chi phí đồng bộ của hybrid.
- Tổ chức source, region và markup để ví dụ có thể kiểm thử.
- Phân biệt việc Javadoc tạo HTML với việc compiler/test xác nhận mã hoạt động.

## 2. Ba cách cung cấp nội dung snippet

Cú pháp tổng quát của thẻ snippet cho phép có hoặc không có phần thân:

~~~text
{@snippet attributes}
{@snippet attributes :
    body
}
~~~

Từ đó hình thành ba kiểu:

| Kiểu | Thuộc tính nguồn | Phần thân sau dấu hai chấm | Nơi đặt nội dung |
| --- | --- | --- | --- |
| Inline | Không cần `file` hoặc `class` | Có | Comment Javadoc |
| External | Có `file` hoặc `class` | Không cần | Tệp nguồn riêng |
| Hybrid | Có `file` hoặc `class` | Có | Cả comment và tệp ngoài |

Cả ba kiểu đều được Standard Doclet xử lý để tạo khối mã trong HTML. Chúng có thể dùng `lang`, `id`, markup comment và các cơ chế trình bày snippet phù hợp.

## 3. Inline: ví dụ ngắn nằm ngay cạnh mô tả API

Inline snippet đặt nội dung trực tiếp trong comment:

~~~java
/**
 * Tạo chính sách thử lại với ba lần thử và khoảng chờ 250 ms:
 *
 * {@snippet lang="java" :
 *     var delay = Duration.ofMillis(250);
 *     var policy = new RetryPolicy(3, delay);
 *     System.out.println(policy);
 *     }
 */
public class RetryService {
}
~~~

Người đọc source thấy ví dụ ngay bên cạnh phần giải thích API. Khi xem HTML, Standard Doclet trình bày nội dung nằm giữa dòng mới đầu tiên sau dấu hai chấm và dấu ngoặc nhọn đóng thẻ.

### Khi inline phù hợp

Chọn inline khi:

- Ví dụ chỉ có vài câu lệnh và có thể hiểu mà không cần nhiều import hoặc lớp phụ trợ.
- Mã minh họa một thao tác cụ thể của API đang được mô tả.
- Người viết muốn chỉnh sửa ví dụ cùng lúc với comment của API.
- Nội dung không cần được tái sử dụng ở nhiều trang.
- Việc kiểm tra bằng mắt và kiểm tra tài liệu là đủ, hoặc dự án đã có cơ chế riêng để trích và kiểm thử inline snippet.

Ví dụ phù hợp gồm một lời gọi phương thức, cách tạo một đối tượng, một phép chuyển đổi hoặc một đoạn kiểm tra điều kiện ngắn.

### Giới hạn cần cân nhắc

Nội dung inline nằm bên trong documentation comment nên chịu giới hạn của comment và cú pháp inline tag:

- Không thể chứa cặp ký tự `*/` vì nó kết thúc traditional documentation comment.
- Unicode escape trong source Java được xử lý trước khi Javadoc đọc comment.
- Các dấu ngoặc nhọn phải cân bằng và lồng đúng thứ tự để parser xác định được dấu đóng thẻ.
- Khoảng trắng bao quanh được xử lý theo quy tắc tương tự `String.stripIndent()`.

Ví dụ có string literal chứa `*/`, regex phức tạp hoặc block comment Java thường nên chuyển ra tệp external.

Một điểm quan trọng khác: **Javadoc không biên dịch hoặc chạy inline snippet.** Đoạn mã ngắn có thể hiển thị đúng trong HTML nhưng vẫn sai tên phương thức, sai kiểu hoặc không chạy được. Nếu ví dụ có ý nghĩa đối với hợp đồng API, cần có cách kiểm tra riêng.

## 4. External: nguồn riêng để tái sử dụng và kiểm thử

External snippet tham chiếu đến tệp Java bằng `class` hoặc đến tệp theo đường dẫn bằng `file`:

~~~java
/**
 * Ví dụ kiểm tra chính sách thử lại:
 *
 * {@snippet class=RetryExample region=policy}
 */
public class RetryService {
}
~~~

Tệp `RetryExample.java` có thể đặt trong thư mục `snippet-files` của package chứa comment, ví dụ `src/p/snippet-files/RetryExample.java` nếu lớp có comment nằm trong package `p`, hoặc trong một thư mục tìm kiếm được cấu hình bằng tùy chọn `--snippet-path`.

Ví dụ tệp nguồn:

~~~java
import java.time.Duration;

public class RetryExample {
    record RetryPolicy(int attempts, Duration initialDelay) {
    }

    public static void main(String... args) {
        // @start region=policy
        var delay = Duration.ofMillis(250);
        var policy = new RetryPolicy(3, delay);
        System.out.println(policy);
        // @end region=policy
    }
}
~~~

Thuộc tính `region=policy` yêu cầu Standard Doclet chỉ lấy nội dung giữa hai markup comment tương ứng. Phần còn lại của tệp có thể chứa import, kiểu phụ trợ, phương thức main và các ví dụ khác.

Với nội dung không phải Java, dùng `file`:

~~~java
/**
 * Cấu hình máy chủ:
 *
 * {@snippet file="application.properties" lang="properties" region=server}
 */
~~~

### Khi external phù hợp

Chọn external khi:

- Ví dụ dài, có nhiều bước hoặc cần import/lớp phụ trợ.
- Một tệp có nhiều ví dụ và có thể chia thành các region.
- Mã cần được biên dịch, chạy hoặc kiểm thử trong build.
- Nội dung chứa block comment, chuỗi `*/` hoặc cấu trúc không phù hợp với inline comment.
- Một ví dụ được dùng ở nhiều phần tài liệu.
- Tệp cấu hình, JSON, XML hoặc dữ liệu văn bản cần được giữ như nguồn độc lập.

### Khả năng kiểm thử

External snippet dễ đưa vào quy trình kiểm thử hơn vì nội dung đã nằm trong tệp. Dự án có thể:

- Biên dịch tệp Java bằng `javac` hoặc build tool.
- Chạy chương trình ví dụ và kiểm tra kết quả.
- Đưa mã vào unit test hoặc integration test.
- Nạp tệp Properties/JSON bằng parser tương ứng để xác nhận cấu trúc và giá trị.
- Kiểm tra các region cần hiển thị trong tài liệu.

Tuy nhiên, Javadoc vẫn chỉ đọc và trình bày nội dung. Việc có tệp external không tự động khiến mã được kiểm thử. Cần cấu hình compiler, test hoặc parser trong build của dự án.

## 5. Hybrid: vừa đọc được tại chỗ, vừa đối chiếu với nguồn ngoài

Hybrid snippet kết hợp phần thân inline với thuộc tính chỉ đến nguồn external:

~~~java
/**
 * Ví dụ nối các đối số bằng dấu cách:
 *
 * {@snippet class=JoinExample region=join :
 *     var delimiter = ... ;
 *     var result = String.join(delimiter, args);
 *     System.out.println(result);
 *     }
 */
~~~

Đặt tệp `JoinExample.java` trong `snippet-files` của package chứa comment có thẻ hybrid, hoặc trong một snippet root được cấu hình bằng `--snippet-path`.

Tệp `JoinExample.java`:

~~~java
public class JoinExample {
    public static void main(String... args) {
        // @start region=join
        var delimiter = " "; // @replace substring='" "' replacement="..."
        var result = String.join(delimiter, args);
        System.out.println(result);
        // @end region=join
    }
}
~~~

Trong tệp external, câu lệnh dùng chuỗi dấu cách thực tế để chương trình có thể biên dịch và chạy. Markup `@replace` thay chuỗi đó bằng dấu ba chấm khi trình bày snippet. Phần thân inline đã viết sẵn dạng hiển thị có dấu ba chấm.

Khi xử lý hybrid snippet, Standard Doclet tạo kết quả từ cả hai nguồn:

1. Xử lý phần thân như một inline snippet.
2. Đọc nguồn external, chọn region và áp dụng markup.
3. So sánh hai kết quả sau xử lý.

**Điều kiện bắt buộc:** kết quả xử lý inline và external phải giống nhau. Nếu không khớp, Javadoc báo lỗi.

Vì vậy, nội dung thô của hai nguồn không nhất thiết phải giống từng ký tự. Chúng phải tạo ra **cùng kết quả sau khi áp dụng region, markup và quy tắc xử lý snippet**. Ví dụ trên dùng `@replace` để mã nguồn ngoài vẫn chạy được, trong khi phần hiển thị inline ngắn gọn hơn.

### Khi hybrid phù hợp

Chọn hybrid khi:

- Người đọc source cần thấy ví dụ ngay cạnh mô tả API.
- Dự án vẫn cần một tệp Java bên ngoài để compiler/test kiểm tra.
- Ví dụ đã ổn định và có thể duy trì hai biểu diễn.
- Cần giữ phần trình bày ngắn gọn nhưng muốn nguồn ngoài có đủ chi tiết để chạy.

Hybrid đặc biệt hữu ích với ví dụ API công khai quan trọng, nơi tính dễ đọc của comment và tính kiểm chứng của mã đều có giá trị.

### Chi phí bảo trì

Hybrid có hai biểu diễn nên tốn công duy trì hơn:

- Sửa ví dụ inline mà quên sửa tệp ngoài sẽ khiến Javadoc báo lỗi không khớp.
- Sửa region hoặc markup bên ngoài có thể làm thay đổi kết quả được so sánh.
- Sửa mã nguồn để kiểm thử được nhưng quên cập nhật nội dung inline cũng làm build tài liệu thất bại.

Vì thế, hướng dẫn Javadoc khuyến nghị phát triển ví dụ dưới dạng inline hoặc external trước, sau đó chuyển thành hybrid khi nội dung đã ổn định.

## 6. Chọn theo kích thước và độ phức tạp của ví dụ

Không có quy định kiểu “dưới 5 dòng dùng inline, trên 5 dòng dùng external”. Số dòng chỉ là một tín hiệu. Một đoạn ba dòng chứa regex có `*/` vẫn có thể cần external; một đoạn mười dòng tự chứa, dễ hiểu và không cần kiểm thử có thể vẫn phù hợp với inline.

Hãy cân nhắc các yếu tố sau:

| Yếu tố | Inline | External | Hybrid |
| --- | --- | --- | --- |
| Ví dụ rất ngắn, tự chứa | Rất phù hợp | Có thể quá nặng về tổ chức | Thường không cần hai bản |
| Ví dụ dài hoặc có nhiều bước | Khó đọc trong comment | Phù hợp | Có thể dùng nếu cần hiển thị tại chỗ |
| Có block comment hoặc chuỗi `*/` | Không phù hợp trong traditional comment | Phù hợp | Phần inline vẫn chịu giới hạn này |
| Cần biên dịch/chạy như mã thật | Cần cơ chế trích riêng | Dễ tích hợp compiler/test | Dễ kiểm thử nguồn ngoài và kiểm tra hai bản khớp |
| Nhiều ví dụ cùng một tệp | Không tiện tái sử dụng | Phù hợp với nhiều region | Có thể dùng cho từng ví dụ quan trọng |
| Cần thấy nội dung ngay trong source comment | Rất phù hợp | Phải mở tệp khác | Rất phù hợp |
| Chi phí đồng bộ nội dung | Một nơi | Một nguồn chính | Hai biểu diễn phải được giữ khớp |
| Ví dụ chưa ổn định | Dễ sửa tại chỗ | Dễ sửa và kiểm thử nguồn | Dễ phát sinh lỗi không khớp |

Có thể dùng quy tắc thực tế:

- Ưu tiên **inline** nếu ví dụ ngắn, dễ đọc và không cần một nguồn thực thi độc lập.
- Ưu tiên **external** nếu ví dụ là một phần của mã nguồn có thể kiểm thử, có nhiều region hoặc có cấu trúc phức tạp.
- Dùng **hybrid** nếu cần cả hai lợi ích và nhóm có thể duy trì việc đồng bộ sau khi ví dụ ổn định.

## 7. Chọn theo khả năng kiểm thử

Khả năng kiểm thử nên được xem là yêu cầu thiết kế, không phải bước bổ sung sau khi viết tài liệu.

### Trường hợp 1: Chỉ cần minh họa cú pháp

Ví dụ:

~~~java
/**
 * Kiểm tra chuỗi rỗng:
 *
 * {@snippet :
 * if (name.isEmpty()) {
 *     throw new IllegalArgumentException("name must not be empty");
 * }
 *     }
 */
~~~

Đây là một đoạn ngắn minh họa điều kiện và ngoại lệ. Nếu phần mô tả API đã giải thích hợp đồng và dự án không cần thực thi chính xác đoạn mã này, inline là lựa chọn gọn.

### Trường hợp 2: Cần chạy như một ví dụ độc lập

Một chương trình có import, cấu hình, dữ liệu đầu vào và kết quả kỳ vọng nên nằm trong tệp Java riêng. Ví dụ có thể được chạy trong CI để phát hiện API thay đổi hoặc hành vi khác dự kiến.

~~~sh
javac -d build/classes src/p/snippet-files/RetryExample.java
java -cp build/classes RetryExample
~~~

Nếu chương trình phụ thuộc thư viện hoặc module của dự án, hãy dùng classpath/module path và build tool tương ứng. Tệp snippet cần được biên dịch trong đúng ngữ cảnh dependency mà ví dụ sử dụng.

### Trường hợp 3: Cần ví dụ hiển thị ngắn nhưng mã nguồn phải chạy được

Đây là tình huống hybrid có giá trị. Tệp external chứa mã hợp lệ để test; markup có thể rút gọn phần hiển thị bằng `@replace`; phần inline chứa kết quả mà người đọc cần thấy. Javadoc kiểm tra hai kết quả trình bày có khớp nhau hay không.

### Inline snippet vẫn có thể được kiểm thử

Inline khó kiểm thử hơn vì nội dung nằm trong documentation comment. Tài liệu Javadoc mô tả cách dùng Compiler API và DocTrees để tìm các snippet trong source, sau đó xử lý hoặc đưa mã vào một template kiểm thử. Cách này phù hợp với dự án có yêu cầu kiểm tra snippet ở quy mô lớn.

Với dự án thông thường, external snippet thường đơn giản hơn để đưa vào build. Không nên mặc định rằng tạo Javadoc thành công đồng nghĩa mọi ví dụ đều biên dịch hoặc chạy đúng.

## 8. Quy trình chọn và triển khai

Có thể áp dụng quy trình sau cho từng ví dụ API:

1. **Xác định mục đích:** ví dụ chỉ giải thích cú pháp, hướng dẫn gọi API hay cần chứng minh hành vi?
2. **Đánh giá kích thước và cấu trúc:** có ngắn, tự chứa, ít import và không có ký tự gây giới hạn inline không?
3. **Xác định yêu cầu kiểm thử:** cần compiler, runtime, unit test hay parser để xác nhận?
4. **Chọn nguồn chính:** inline nếu nội dung đơn giản; external nếu cần nguồn có thể kiểm thử.
5. **Chọn hybrid khi đã ổn định:** chỉ nhân đôi biểu diễn khi lợi ích đọc tại chỗ đáng với chi phí đồng bộ.
6. **Chia region:** với external file có nhiều ví dụ, đặt tên region theo mục đích.
7. **Thêm markup có chủ đích:** dùng highlight/link/replace để làm rõ phần quan trọng; không dùng markup để che lỗi mã.
8. **Tạo Javadoc:** kiểm tra đường dẫn external, region, markup và điều kiện khớp của hybrid.
9. **Kiểm thử nguồn:** biên dịch/chạy Java hoặc xác thực dữ liệu theo định dạng tương ứng.
10. **Đưa vào CI:** bảo đảm thay đổi API hoặc snippet làm chạy lại cả kiểm tra mã và tạo tài liệu.

## 9. Những lỗi thường gặp khi chọn sai kiểu

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Comment Javadoc khó đọc vì có một khối mã rất dài. | Dùng inline cho ví dụ nhiều bước hoặc có nhiều import. | Chuyển nội dung sang external và trích region cần thiết. |
| Không thể viết ví dụ chứa `*/`. | Cố nhúng chuỗi hoặc block comment vào inline traditional comment. | Dùng external snippet. |
| Ví dụ hiển thị đẹp nhưng API đã đổi và mã sai. | Chỉ kiểm tra HTML, không biên dịch/chạy ví dụ. | Đưa nguồn external vào compiler/test hoặc xây cơ chế kiểm thử inline. |
| External file dài và trang tài liệu hiển thị quá nhiều nội dung. | Không chọn region. | Đánh dấu region và chỉ tham chiếu phần cần trình bày. |
| Javadoc báo hybrid snippet không khớp. | Nội dung inline và external cho kết quả sau xử lý khác nhau. | So sánh kết quả hiển thị, kiểm tra region và markup `@replace`. |
| Hybrid khó sửa trong giai đoạn thiết kế. | Chọn hybrid quá sớm khi ví dụ còn thay đổi thường xuyên. | Phát triển bằng inline hoặc external trước; chuyển sang hybrid khi ổn định. |
| Mã external biên dịch được nhưng snippet hiển thị sai. | Markup hoặc region thay đổi nội dung không như dự kiến. | Kiểm tra HTML sinh ra và kết quả xử lý snippet. |
| Một ví dụ xuất hiện ở nhiều trang nhưng nhanh chóng lệch nhau. | Sao chép inline thành nhiều bản độc lập. | Dùng một external file với các region được đặt tên rõ ràng. |

## 10. Bài tập thực hành

### Bài tập 1: Chọn kiểu cho ba tình huống

Chọn inline, external hoặc hybrid và giải thích:

1. Một lời gọi `Files.readString(path)` để minh họa API.
2. Một chương trình Java 40 dòng có import, dữ liệu đầu vào và kiểm tra kết quả.
3. Một ví dụ quan trọng cần hiện ngay trong comment, nhưng nhóm cũng muốn biên dịch và chạy nguồn trong CI.

**Gợi ý:** (1) thường phù hợp inline; (2) thường phù hợp external; (3) có thể dùng hybrid sau khi ví dụ ổn định.

### Bài tập 2: Chuyển inline thành external

Bắt đầu bằng một inline snippet có ba câu lệnh. Tạo tệp Java riêng, chuyển mã vào một region tên `read-file`, rồi thay thẻ inline bằng `{@snippet class=FileExample region=read-file}`. Sinh Javadoc và so sánh phần hiển thị trước/sau.

### Bài tập 3: Xây dựng hybrid với @replace

Tạo tệp `JoinExample.java` có vùng `join`. Trong tệp, dùng giá trị delimiter hợp lệ như `" "` và thêm markup `@replace` để hiển thị `...`. Viết phần thân hybrid với cùng kết quả hiển thị. Sinh Javadoc và quan sát điều gì xảy ra nếu sửa một ký tự trong phần inline.

### Bài tập 4: Kiểm chứng độc lập với Javadoc

Tạo external snippet có `main` và một assertion. Chạy Javadoc, sau đó biên dịch/chạy chương trình. Cố ý đổi giá trị kỳ vọng để chương trình thất bại. Giải thích vì sao Javadoc vẫn có thể tạo HTML dù kiểm thử runtime thất bại.

### Bài tập 5: Lập quy tắc cho nhóm

Viết quy ước ngắn cho nhóm API của bạn: ví dụ nào phải external, khi nào dùng hybrid, cách đặt region và bước kiểm tra bắt buộc trong CI. Nêu rõ ai chịu trách nhiệm đồng bộ hai bản khi hybrid thay đổi.

**Tự kiểm:** lựa chọn dựa trên độ phức tạp và nhu cầu kiểm thử; hiểu giới hạn inline; external có nguồn rõ ràng; hybrid có hai kết quả sau xử lý giống nhau; compiler/test được chạy riêng với Javadoc.

## 11. Ghi nhớ

- **Inline phù hợp với ví dụ ngắn, tự chứa và dễ hiểu tại chỗ.** Nội dung nằm ngay trong comment Javadoc nhưng chịu giới hạn của inline tag và traditional comment.
- **External phù hợp với ví dụ dài, nhiều region hoặc cần kiểm thử.** Nguồn nằm trong tệp riêng và có thể được biên dịch, chạy hoặc xác thực bằng công cụ thông thường.
- **Hybrid kết hợp nội dung inline và nguồn external.** Standard Doclet yêu cầu kết quả sau xử lý của hai nguồn phải giống nhau.
- **Không có ngưỡng số dòng cố định.** Hãy cân nhắc cấu trúc, ký tự đặc biệt, khả năng tái sử dụng và yêu cầu kiểm thử.
- **Phát triển inline hoặc external trước, rồi mới chuyển sang hybrid khi ổn định.** Cách này giảm chi phí đồng bộ trong giai đoạn thiết kế.
- **Javadoc không biên dịch hay chạy snippet.** Tạo HTML thành công không chứng minh ví dụ đúng; cần compiler, runtime, test hoặc parser phù hợp.
- **Đưa kiểm thử snippet vào CI.** Ví dụ tài liệu quan trọng nên được duy trì cùng nhịp với API mà chúng minh họa.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle – JDK 26 Javadoc Snippets Guide, Inline, External, Hybrid và Testing Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, thẻ snippet của Standard Doclet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).

