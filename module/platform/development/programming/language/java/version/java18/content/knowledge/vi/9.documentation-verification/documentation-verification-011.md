# Đối chiếu nội dung sao chép từ snippet với nội dung hiển thị và ý định của `@replace`

## 1. Vì sao phải kiểm tra cả nội dung hiển thị và nội dung được sao chép?

Một snippet trong Javadoc có thể dùng mã nguồn hợp lệ để minh họa một ý tưởng tổng quát. Ví dụ, mã thật có thể dùng chuỗi rỗng làm giá trị giữ chỗ, nhưng tài liệu muốn người đọc thấy dấu ba chấm để biểu thị phần đã được lược bỏ. Markup `@replace` cho phép Standard Doclet thay phần giữ chỗ bằng văn bản trình bày trong HTML.

Điều này tạo ra ba phiên bản nội dung cần phân biệt:

1. **Mã nguồn gốc:** file Java chứa placeholder hợp lệ, có thể được biên dịch và kiểm thử.
2. **Nội dung hiển thị:** văn bản sau khi Javadoc áp dụng `@replace`, `@highlight` và các markup khác.
3. **Nội dung clipboard:** chuỗi thực tế được đưa vào clipboard khi người đọc nhấn nút Copy của snippet.

Ba phiên bản có thể khác nhau theo chủ đích. Mã nguồn có thể chứa `""` để chương trình chạy được, còn HTML hiển thị `...` để báo hiệu phần bị lược bỏ. Người đọc thường mong nút Copy sao chép đúng nội dung đang thấy. Vì vậy, cần dán nội dung clipboard ra một nơi kiểm tra được và đối chiếu với HTML đã sinh.

Tài liệu JDK 25 xác nhận Standard Doclet cung cấp nút **Copy to Clipboard** cho snippet và `@replace` thay văn bản trong nội dung được hiển thị. Đặc tả mô tả quy tắc biến đổi văn bản; nó không định nghĩa chi tiết mọi bước triển khai clipboard của trình duyệt. Do đó, hãy kiểm tra hành vi thực tế trên bộ HTML được phát hành và môi trường trình duyệt mục tiêu.

Bài này thuộc phần **Kiểm chứng tài liệu** của mô-đun **JAVA_VERSION_JAVA18**. Ta sẽ tạo một external snippet có placeholder hợp lệ, thay placeholder bằng dấu ba chấm bằng `@replace`, sinh Javadoc, biên dịch mã nguồn gốc, rồi so sánh source, HTML và nội dung dán từ clipboard. Các tính năng được dùng vẫn được hỗ trợ trên JDK hiện đại.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `@replace` làm nội dung trình bày khác với file nguồn.
- Xác định phạm vi thay thế theo dòng hiện tại hoặc một region.
- Dùng `substring`, `regex` và `replacement` đúng mục đích.
- Kiểm tra văn bản hiển thị trong HTML và văn bản thật được sao chép.
- Nhận biết khi nội dung được sao chép cố ý không còn biên dịch được.
- Dùng external snippet và hybrid snippet để giữ ví dụ nguồn đồng bộ với tài liệu.
- Xác minh chức năng Copy trong trình duyệt và xử lý lỗi do clipboard permission hoặc môi trường chạy.

## 2. Cơ chế của markup `@replace`

`@replace` thay văn bản trong một phạm vi xác định. Markup này được đặt trong comment cuối dòng của snippet hoặc dạng comment tương ứng với ngôn ngữ file. Comment chứa markup không xuất hiện trong đoạn mã hiển thị.

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `substring` | Chuỗi literal cần thay. Mọi lần xuất hiện của chuỗi đó trong phạm vi được chọn sẽ được thay. |
| `regex` | Biểu thức chính quy dùng để tìm phần văn bản cần thay. |
| `region` | Region xác định phạm vi nhiều dòng để thay thế. |
| `replacement` | Văn bản thay thế. |

Nếu không chỉ định `region`, phạm vi mặc định là dòng chứa markup comment. Nếu chỉ định region, việc tìm và thay thế áp dụng trong region đó cho đến marker kết thúc tương ứng.

Nếu không có `substring` hoặc `regex`, toàn bộ phạm vi được thay bằng `replacement`. Để xóa nội dung, dùng replacement rỗng. Để chèn nội dung, có thể đặt một placeholder không có tác dụng trong mã (ví dụ comment `//` hoặc câu lệnh rỗng `;`) tại vị trí cần chèn rồi thay placeholder đó.

Khi dùng `regex`, phần thay thế có thể tham chiếu nhóm bắt bằng `$1`, `$2` hoặc tên nhóm theo quy tắc của `String.replaceAll`. Hãy kiểm tra biểu thức trên chính dòng/region của snippet; regex khớp quá rộng có thể làm thay đổi cả phần mã không định thay.

## 3. Ví dụ: giữ mã nguồn biên dịch được nhưng hiển thị dấu ba chấm

### 3.1. Cấu trúc dự án

Tạo dự án tối thiểu:

```text
demo/
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── text/
                        ├── JoinApi.java
                        └── snippet-files/
                            └── JoinExample.java
```

File API `src/main/java/com/example/text/JoinApi.java`:

```java
package com.example.text;

/**
 * Các tiện ích xử lý chuỗi.
 *
 * <p>Ví dụ ghép các phần tử:</p>
 * {@snippet class=JoinExample region=join}
 */
public final class JoinApi {
    private JoinApi() {
    }

    /**
     * Ghép các phần tử bằng dấu phân cách.
     *
     * @param delimiter dấu phân cách
     * @param values các phần tử cần ghép
     * @return chuỗi kết quả
     */
    public static String join(String delimiter, String... values) {
        return String.join(delimiter, values);
    }
}
```

File external snippet `src/main/java/com/example/text/snippet-files/JoinExample.java`:

```java
package com.example.text;

public class JoinExample {
    public static void main(String[] args) {
        // @start region=join
        var delimiter = " "; // @replace substring='" "' replacement="..."
        var result = JoinApi.join(delimiter, "Java", "18");
        System.out.println(result);
        // @end region=join
    }
}
```

Dòng nguồn có `var delimiter = " ";` là Java hợp lệ. Markup thay chuỗi `" "` bằng `...` trong tài liệu. Người đọc sẽ thấy:

```java
var delimiter = ...;
var result = JoinApi.join(delimiter, "Java", "18");
System.out.println(result);
```

Dấu ba chấm là cách trình bày để báo rằng giá trị delimiter được lược bỏ khỏi ví dụ. Nó không phải một biểu thức Java hợp lệ trong vị trí khởi tạo biến. Đây là khác biệt có chủ ý giữa mã dùng để kiểm thử và mã dùng để giải thích.

### 3.2. Biên dịch và chạy mã nguồn gốc

Từ thư mục project root `demo/`, biên dịch API cùng file snippet:

```bash
mkdir -p build/classes build/docs

javac --release 18 -encoding UTF-8 -d build/classes \
  src/main/java/com/example/text/JoinApi.java \
  src/main/java/com/example/text/snippet-files/JoinExample.java

java -cp build/classes com.example.text.JoinExample
```

Đầu ra mong đợi:

```text
Java 18
```

Bước này kiểm tra mã nguồn thật, trong đó delimiter là chuỗi một dấu cách. Nó không kiểm tra nội dung đã thay thế trong HTML. Standard Doclet không biên dịch hoặc chạy snippet khi tạo Javadoc; external snippet được đặt trong file riêng để có thể được công cụ build kiểm tra độc lập.

### 3.3. Sinh Javadoc

Chạy:

```bash
javadoc --release 18 -encoding UTF-8 -charset UTF-8 \
  --source-path src/main/java \
  -Xdoclint:all -Werror \
  -d build/docs \
  com.example.text
```

Trang lớp được sinh ở:

`build/docs/com/example/text/JoinApi.html`

Mở trang bằng trình duyệt và tìm snippet có region `join`. Nội dung cần hiển thị `...` thay cho chuỗi `" "` ở dòng khai báo delimiter. Nếu vẫn thấy `" "`, hãy kiểm tra markup comment có được viết đúng và substring có khớp chính xác nội dung nguồn hay không.

## 4. Đối chiếu ba phiên bản nội dung

Với ví dụ ở phần 3, hãy lập bảng so sánh:

| Vị trí kiểm tra | Nội dung ở dòng delimiter | Mục đích |
| --- | --- | --- |
| File `JoinExample.java` | `var delimiter = " ";` kèm comment `@replace` | Mã hợp lệ để biên dịch và chạy. |
| HTML hiển thị | `var delimiter = ...;` | Giải thích rằng giá trị cụ thể được lược bỏ. |
| Clipboard sau khi nhấn Copy | Dán ra để xác minh; nếu theo ý định trình bày thì phải thấy `var delimiter = ...;` | Nội dung người đọc thực sự nhận được. |

Đối với người đọc tài liệu, kết quả Copy hữu ích nhất thường là văn bản đã được biến đổi giống nội dung nhìn thấy. Tuy nhiên, đừng kết luận chỉ từ nút bấm hoặc tên lớp CSS. Hãy nhấn Copy, dán vào một trình soạn thảo văn bản thuần và so sánh từng dòng với nội dung trong HTML.

### 4.1. Quy trình kiểm tra thủ công

1. Mở trang `JoinApi.html` vừa sinh, không dùng một bản HTML cũ trong cache.
2. Tìm snippet có dòng `var delimiter`.
3. Ghi lại chính xác nội dung hiển thị, gồm khoảng trắng, dấu chấm phẩy và dấu ba chấm.
4. Nhấn nút Copy to Clipboard của chính snippet đó.
5. Dán vào một file text mới hoặc editor ở chế độ plain text.
6. So sánh dòng delimiter và toàn bộ các dòng còn lại với nội dung HTML.
7. Lặp lại sau khi build lại Javadoc để xác nhận kết quả không phụ thuộc vào cache.

Không dán vào một ô có tự động định dạng mã hoặc Markdown rồi so sánh bằng mắt. Editor có thể tự thay dấu ngoặc kép, thụt lề hoặc khoảng trắng. Khi cần chính xác, lưu nội dung clipboard vào file text UTF-8 rồi so sánh byte hoặc chuỗi ký tự.

### 4.2. Cách diễn giải kết quả

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| Clipboard giống HTML đã biến đổi | Copy cung cấp đúng dạng trình bày cho người đọc. | Xác nhận đây là hành vi mong muốn của snippet. |
| Clipboard chứa placeholder gốc `" "` | Clipboard khác phần trình bày; có thể gây bất ngờ cho người đọc. | Xem lại hành vi Copy của JDK/browser đang dùng và quyết định có cần thay đổi cách trình bày hay không. |
| Clipboard thiếu dòng hoặc mất thụt lề | Có thể chọn sai vùng, lỗi serialize text hoặc lỗi clipboard. | So sánh nội dung DOM với văn bản dán ra. |
| Clipboard không thay đổi | Thao tác copy thất bại hoặc browser từ chối quyền ghi. | Kiểm tra Console, quyền clipboard và môi trường trang. |
| HTML cũng không thay thế placeholder | Markup không khớp hoặc không nằm trong phạm vi được xử lý. | Kiểm tra `substring`, `regex`, `region` và cú pháp comment. |

Tài liệu Javadoc công bố nút Copy và đặc tả `@replace` mô tả nội dung được thay trong output. Đặc tả không hứa hẹn một hợp đồng độc lập về chính xác chuỗi clipboard ở mọi browser. Vì vậy, nếu clipboard khác HTML, ghi nhận đó là sai khác hành vi của bản JDK/browser đang kiểm tra và đánh giá theo yêu cầu sản phẩm; không tự giả định file nguồn là nội dung mà nút Copy luôn sao chép.

## 5. Điều chỉnh phạm vi thay thế bằng `substring`, `regex` và `region`

### 5.1. `substring`: thay chuỗi literal

Với:

```java
var delimiter = " "; // @replace substring='" "' replacement="..."
```

Javadoc tìm chuỗi literal `" "` và thay mọi lần xuất hiện của chuỗi đó trong phạm vi hiện hành. Nếu có hai chuỗi giống hệt trên cùng dòng, cả hai có thể được thay. Hãy chọn một substring đủ đặc trưng để không vô tình thay phần khác.

### 5.2. `regex`: thay theo biểu thức chính quy

Giả sử muốn thay mọi số nguyên trong một dòng bằng placeholder:

```java
int retryLimit = 3; // @replace regex='\b\d+\b' replacement="N"
```

Nội dung hiển thị:

```java
int retryLimit = N;
```

Đây chỉ là ví dụ về quy tắc regex; `N` có thể không phải biểu thức Java hợp lệ trong mọi vị trí. Nếu regex khớp nhiều phần của dòng hơn dự kiến, hãy thu hẹp pattern hoặc dùng substring literal.

Khi regex có capture group, replacement có thể tham chiếu `$1`, `$2` hoặc tên group. Quy tắc thay thế nhóm theo `String.replaceAll`; hãy kiểm tra riêng regex bằng một phép thử nhỏ trước khi đưa vào Javadoc.

### 5.3. `region`: thay trên nhiều dòng

Nếu cần thay một placeholder trong vùng gồm nhiều dòng, tạo region có tên:

```java
var host = "localhost";
var port = 8080; // @replace region=configuration substring="8080" replacement="PORT"
var endpoint = host + ":" + port;
// @end region=configuration
```

Ở đây, chính markup `@replace region=configuration` bắt đầu region có tên `configuration`; marker `@end region=configuration` đóng region đó. Phạm vi thay thế vì thế gồm dòng `port` và các dòng tiếp theo trong region. Nếu muốn một region độc lập với markup thay thế, có thể dùng cặp `@start region=configuration` và `@end region=configuration`, rồi đặt `@replace` riêng trong phạm vi thích hợp.

Không dùng region nếu chỉ cần thay một substring duy nhất trên một dòng; phạm vi rộng không cần thiết làm tăng nguy cơ thay nhầm.

### 5.4. Xóa hoặc chèn nội dung

Replacement rỗng có thể xóa một phần văn bản khỏi output:

```java
String debugLabel = "internal"; // @replace substring=' "internal"' replacement=""
```

Nếu muốn chèn nội dung, đặt một no-op marker trong source rồi thay marker bằng văn bản cần hiển thị:

```java
// @replace substring="// DOC_PLACEHOLDER" replacement="// phần cấu hình do ứng dụng cung cấp" :
// DOC_PLACEHOLDER
```

Hãy đảm bảo marker là cú pháp hợp lệ trong ngôn ngữ snippet và replacement phù hợp với ngữ cảnh hiển thị.

## 6. Khi nội dung được sao chép không còn biên dịch được

Đây thường là hệ quả có chủ đích của `@replace`. Ví dụ:

```java
var delimiter = " "; // @replace substring='" "' replacement="..."
```

Mã nguồn có thể biên dịch, nhưng nội dung hiển thị:

```java
var delimiter = ...;
```

không thể dùng trực tiếp làm câu lệnh Java. Dấu ba chấm mang ý nghĩa “phần này đã được lược bỏ”, không phải biểu thức cần chạy.

Trước khi viết snippet, hãy xác định người đọc cần sao chép để làm gì:

- Nếu mục tiêu là **giải thích ý tưởng**, dấu ba chấm có thể hữu ích; nội dung copy có thể là một ví dụ rút gọn, không phải chương trình hoàn chỉnh.
- Nếu mục tiêu là **sao chép và chạy ngay**, hãy tránh thay cú pháp cần thiết bằng placeholder không hợp lệ, hoặc cung cấp thêm liên kết tới ví dụ hoàn chỉnh.
- Nếu mục tiêu là **giữ mã nguồn có thể kiểm thử nhưng trình bày ngắn**, dùng external snippet với placeholder hợp lệ trong file và `@replace` trong tài liệu; biên dịch file nguồn riêng.

Đừng coi việc clipboard chứa mã không biên dịch được là lỗi tự động. Trước hết so sánh nó với ý định của tác giả. Một snippet hướng dẫn có thể chủ ý lược bỏ chi tiết; một snippet được quảng bá là “copy, paste và chạy” phải được kiểm tra theo tiêu chí khác.

## 7. Dùng hybrid snippet để đồng bộ source và tài liệu

Hybrid snippet kết hợp nội dung inline trong Javadoc với tham chiếu tới file external. Standard Doclet xử lý cả hai dạng rồi báo lỗi nếu kết quả sau xử lý không khớp nhau. Cách này giúp kiểm tra rằng phần hiển thị trong source và phần lấy từ file external không bị lệch.

Ví dụ external file có source hợp lệ:

```java
// @start region=join
var delimiter = " "; // @replace substring='" "' replacement="..."
var result = JoinApi.join(delimiter, "Java", "18");
System.out.println(result);
// @end region=join
```

Phần Javadoc hybrid có thể viết:

```java
/**
 * Ví dụ ghép chuỗi:
 * {@snippet class=JoinExample region=join :
 *     var delimiter = ...;
 *     var result = JoinApi.join(delimiter, "Java", "18");
 *     System.out.println(result);
 * }
 */
```

Nội dung inline được viết theo dạng đã biến đổi để người đọc source nhìn thấy kết quả mong muốn. External file vẫn giữ placeholder biên dịch được; `@replace` tạo cùng output. Nếu hai kết quả sau xử lý khác nhau, Javadoc báo lỗi mismatch.

Hybrid snippet hữu ích khi ví dụ đã ổn định và muốn kiểm soát cả nội dung đọc trong source lẫn file dùng để kiểm thử. Trong giai đoạn phát triển, có thể bắt đầu bằng external snippet, sau đó thêm phần inline khi nội dung đã ổn định để tránh phải cập nhật hai bản quá sớm.

## 8. Kiểm tra HTML và DOM của snippet

Sau khi sinh Javadoc, kiểm tra file HTML trước khi kiểm tra clipboard:

1. Tìm `JoinApi.html` trong output directory.
2. Tìm phần tử snippet có nội dung `var delimiter`.
3. Xác nhận văn bản đã được thay thành `...`.
4. Xác nhận markup comment `@replace` không xuất hiện như một phần của mã hiển thị.
5. Kiểm tra nút Copy nằm trong vùng snippet tương ứng.
6. Dùng trình duyệt nhấn nút và dán nội dung ra file text.

DevTools có thể giúp đọc DOM và nội dung text của phần tử trình bày snippet. Không phụ thuộc vào mọi chi tiết DOM nội bộ của một phiên bản JDK; cấu trúc có thể thay đổi. Hãy kiểm tra đặc điểm cấp cao: snippet đúng nội dung, nút Copy đúng snippet, văn bản dán ra khớp tiêu chí đã chọn.

### 8.1. Phân biệt lỗi markup và lỗi clipboard

| Kiểm tra | Nếu sai | Vấn đề nằm ở |
| --- | --- | --- |
| HTML đã thay placeholder chưa? | Chưa | `@replace`, substring/regex hoặc region. |
| HTML có giữ nguyên dòng và khoảng trắng mong muốn? | Không | Nội dung snippet, stripIndent hoặc xử lý output. |
| Nút Copy có nằm cạnh snippet đúng không? | Không | HTML/Standard Doclet hoặc trang bị tùy biến. |
| Nhấn Copy có tạo dữ liệu trong clipboard không? | Không | Browser permission, secure context hoặc JavaScript. |
| Dữ liệu dán ra có khớp nội dung hiển thị không? | Không | Khác biệt giữa DOM output và clipboard payload. |
| Nội dung dán ra có biên dịch được không? | Không | Có thể là chủ ý của placeholder; đối chiếu mục đích snippet. |

Nếu trang được mở qua HTTP/HTTPS, clipboard API của browser có thể chịu giới hạn secure context và quyền ghi. Thử trên localhost hoặc HTTPS, nhấn nút trực tiếp bằng thao tác người dùng, rồi kiểm tra thông báo lỗi trong Console nếu copy thất bại. Không dùng một lần copy thất bại để kết luận `@replace` hoạt động sai.

## 9. Quy trình kiểm thử đề xuất

Một bài kiểm chứng tốt nên có ba nhóm assertion độc lập:

### A. Kiểm tra source

- External file có placeholder hợp lệ.
- `javac` biên dịch được API và ví dụ.
- Chạy ví dụ cho kết quả kỳ vọng.
- Marker region bắt đầu/kết thúc đúng và không chứa lỗi cú pháp.

### B. Kiểm tra output Javadoc

- Javadoc chạy thành công với DocLint.
- HTML chứa replacement text mong đợi.
- Markup comment không xuất hiện trong mã trình bày.
- Các dòng xung quanh placeholder vẫn nguyên vẹn.
- Nếu dùng hybrid snippet, Javadoc không báo nội dung inline/external mismatch.

### C. Kiểm tra clipboard

- Nút Copy hoạt động trên trang được sinh.
- Nội dung được dán ra được lưu để đối chiếu.
- Chuỗi clipboard khớp với nội dung hiển thị nếu đó là tiêu chí sản phẩm.
- Nếu nội dung copy khác, ghi nhận khác biệt và quyết định có chấp nhận theo mục tiêu snippet hay không.
- Nếu copy được kỳ vọng là mã chạy được, biên dịch chính nội dung clipboard như một kiểm tra riêng.

Không gộp ba nhóm thành một phép kiểm tra duy nhất. Source có thể hợp lệ trong khi HTML sai; HTML có thể đúng trong khi clipboard không hoạt động; clipboard có thể khớp HTML nhưng bản thân snippet đã cố ý không phải chương trình hoàn chỉnh.

### Bài tự luyện

1. Thay `""` bằng `...` qua `@replace`. Xác nhận source biên dịch được và HTML hiển thị dấu ba chấm.
2. Bỏ thuộc tính `replacement`. Quan sát chẩn đoán của Javadoc.
3. Đổi `substring` thành một chuỗi không tồn tại. Xác nhận output và giải thích vì sao placeholder không đổi.
4. Đưa `@replace` vào region nhiều dòng và kiểm tra nó có thay mọi lần xuất hiện trong phạm vi không.
5. Dùng regex có capture group để giữ lại một phần nội dung. So sánh output với quy tắc `String.replaceAll`.
6. Nhấn Copy và dán ra text editor. So sánh từng ký tự với nội dung đã render.
7. Cố tình viết hybrid snippet có inline output khác external output. Quan sát lỗi mismatch.
8. Biên dịch nội dung đã copy khi nó chứa `...`. Giải thích vì sao kết quả khác với việc biên dịch file nguồn gốc.

## 10. Tài liệu tham khảo chính thức

- [Snippets — Javadoc Guide (JDK 25)](https://docs.oracle.com/en/java/javase/25/javadoc/snippets.html): ví dụ `@replace`, replacement text, Copy to Clipboard, external snippet, hybrid snippet và kiểm thử snippet.
- [Javadoc Documentation Comment Specification for the Standard Doclet (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): phạm vi thay thế theo dòng/region, `substring`, `regex`, `replacement`, nhóm regex và quy tắc hybrid snippet.
- [JavaDoc Output Generated by the Standard Doclet (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/std-doclet-output.html): cấu trúc output và lớp CSS cho snippet cùng nút Copy.
- [String.replaceAll (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#replaceAll(java.lang.String,java.lang.String)): quy tắc thay thế và tham chiếu nhóm trong replacement của regex.
- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): mục tiêu và thiết kế tính năng snippet từ Java 18.

**Ghi nhớ:** `@replace` biến đổi nội dung Javadoc trình bày, không sửa file nguồn. Hãy biên dịch placeholder gốc, kiểm tra HTML đã thay thế, rồi nhấn Copy và dán ra để xác nhận dữ liệu clipboard theo đúng ý định của snippet. Nếu dấu ba chấm làm ví dụ không còn biên dịch, đó có thể là chủ ý trình bày; hãy cung cấp hoặc kiểm thử riêng mã nguồn đầy đủ khi người đọc cần chạy ví dụ.
