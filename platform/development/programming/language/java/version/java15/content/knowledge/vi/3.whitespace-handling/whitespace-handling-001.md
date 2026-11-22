# Khoảng trắng do căn lề và khoảng trắng thuộc dữ liệu trong Java 15

## 1. Mục tiêu và bối cảnh

Trong một **text block** (chuỗi nhiều dòng viết bằng `""" ... """`), không phải mọi dấu cách nhìn thấy trong mã nguồn đều trở thành ký tự của `String` lúc chạy. Java phân biệt:

- **Khoảng trắng do căn lề (incidental whitespace):** khoảng trắng dùng để đặt text block thẳng hàng với mã Java xung quanh; trình biên dịch tự loại bỏ phần chung này để việc chỉnh lề mã không vô tình đổi nội dung chuỗi.
- **Khoảng trắng thuộc dữ liệu (essential whitespace):** khoảng trắng có ý nghĩa trong chính chuỗi, chẳng hạn khoảng thụt vào tương đối của một phần tử con, khoảng trắng đứng đầu một dòng cần giữ lại, khoảng trắng cuối dòng được chủ động chèn, tab hay ký tự xuống dòng.

Text blocks được chuẩn hóa thành tính năng chính thức từ **Java 15** và vẫn dùng trong Java hiện đại. Phân biệt hai loại khoảng trắng là kiến thức đang áp dụng, nhất là khi nhúng HTML, JSON, SQL, YAML, nội dung thư hoặc dữ liệu kiểm thử trong mã Java.

**Sau bài học**, bạn sẽ đọc đúng giá trị chuỗi sau khi biên dịch, điều khiển khoảng trắng bằng vị trí dấu đóng và escape, kiểm tra ký tự không nhìn thấy, đồng thời tránh các thao tác làm mất dữ liệu có chủ ý.

## 2. Nhìn vào giá trị `String`, đừng chỉ nhìn mã nguồn

Ví dụ Java 15:

```java
String tree = """
        parent
          child
        """;
```

Trong ví dụ này, các dòng nội dung được căn lề để dễ đọc khi đặt trong phương thức Java. Sau khi trình biên dịch xử lý, **giá trị thực** tương đương:

```java
String tree = "parent\n  child\n";
```

Hai dấu cách trước `child` là **dữ liệu** vì đó là phần thụt vào *tương đối* so với `parent`. Phần lề chung trước cả hai dòng là **căn lề nguồn**, nên bị bỏ. Ký tự `\n` cuối chuỗi vẫn tồn tại vì trước dấu đóng `"""` có một lần xuống dòng.

Đối với `String` thường, khoảng trắng viết bên trong dấu ngoặc kép là dữ liệu:

```java
String ordinary = "  parent  ";
System.out.println(ordinary.length());  // 10
```

Ở đây Java không tự bỏ hai dấu cách đầu/cuối: `length()` bằng 10 (2 dấu cách + 6 chữ cái + 2 dấu cách). Quy tắc loại bỏ căn lề tự động là quy tắc **tạo giá trị text block**, không phải thao tác tự động trên tất cả `String` trong ứng dụng.

## 3. Text block được biến đổi theo thứ tự nào?

Theo **Java Language Specification §3.10.6**, nội dung text block được xử lý theo đúng ba bước:

1. **Chuẩn hóa dấu kết thúc dòng:** `CRLF` hoặc `CR` trong nguồn trở thành `LF` (`\n`).
2. **Loại bỏ khoảng trắng ngẫu nhiên:** sử dụng quy tắc tương đương `String.stripIndent()` để bỏ phần căn lề chung, khoảng trắng cuối dòng và khoảng trắng trên dòng chỉ có whitespace; giữ mức thụt vào tương đối còn lại.
3. **Diễn giải escape cuối cùng:** ví dụ `\s` thành một dấu cách, `\t` thành tab, `\n` thành xuống dòng, và dấu `\` ngay trước line terminator dùng để nối dòng.

**Thứ tự rất quan trọng:** `\s` được chuyển thành dấu cách *sau* bước loại bỏ khoảng trắng, vì thế ta có thể dùng nó để giữ khoảng trắng cuối dòng. Ngược lại, vài dấu cách thật gõ trực tiếp ở cuối dòng nguồn thường bị loại bỏ trong bước 2.

Text block vẫn là một `String` bình thường, có thể so sánh bằng `equals`, đưa cho API khác hoặc truyền qua mạng. Việc xóa căn lề xảy ra khi **tạo giá trị từ cú pháp text block**, không có bước ngầm “tự strip” mỗi khi chuỗi được sử dụng.

## 4. Cách Java quyết định phần lề nào là ngẫu nhiên

Về mặt khái niệm, `stripIndent` xét từng dòng và tìm **số ký tự whitespace đầu dòng nhỏ nhất** trên các dòng không trắng; dòng cuối cũng được tính ngay cả khi toàn whitespace. Sau đó:

- Mỗi dòng không trắng mất số ký tự whitespace đầu dòng tương ứng với mức tối thiểu; phần lề còn lại là dữ liệu.
- Khoảng trắng cuối mỗi dòng không trắng bị loại bỏ.
- Dòng chỉ có whitespace trở thành dòng rỗng (các dấu xuống dòng phân tách vẫn được giữ).
- Tab được tính như **một ký tự whitespace**, không phải một số cột cố định trên màn hình. Vì vậy, trộn tab và space dễ gây lệch kết quả khi editor hiển thị tab với độ rộng khác nhau.

Trong một text block thông dụng, dòng chứa dấu đóng `"""` nằm riêng; lượng thụt vào trước dấu đóng là **một phần dữ liệu đầu vào để xác định lề tối thiểu**. Di chuyển dấu đóng sang trái hoặc phải có thể thay đổi số dấu cách được giữ trong giá trị.

### Trường hợp A — lề chung bị xóa, lề tương đối được giữ

```java
String html = """
        <ul>
            <li>A</li>
        </ul>
        """;
```

Giá trị tương đương: `"<ul>\n    <li>A</li>\n</ul>\n"`. Bốn dấu cách trước `<li>` nằm **bên trong dữ liệu HTML**, còn phần lề chung của mã nguồn bị xóa.

### Trường hợp B — giữ lề có chủ ý bằng cách đặt nội dung sâu hơn dấu đóng

```java
String indented = """
            alpha
            beta
        """;
```

Các dòng nội dung thụt vào nhiều hơn dòng dấu đóng bốn dấu cách. Vì vậy giá trị tương đương `"    alpha\n    beta\n"`, tức mỗi dòng vẫn bắt đầu bằng **bốn dấu cách dữ liệu**. Khi cấu trúc nội dung cần một cấp lề ban đầu, đây là cách diễn đạt rõ ý định ngay trong text block.

### Trường hợp C — không có newline sau dòng cuối

```java
String withFinalLf = """
        red
        blue
        """;

String withoutFinalLf = """
        red
        blue""";
```

- `withFinalLf` = `"red\nblue\n"`.
- `withoutFinalLf` = `"red\nblue"`.

Dấu mở `"""` phải đi kèm line terminator ở cuối dòng mở; newline ngay sau dấu mở **không** trở thành một dòng trống đầu tiên trong giá trị. Dấu đóng có thể ở dòng riêng hoặc sát sau nội dung cuối. Đây là cách kiểm soát newline cuối chuỗi khi nó là dữ liệu quan trọng.

## 5. Ví dụ Java 15 chạy độc lập, kiểm tra chính xác từng ký tự

Lưu tệp **`WhitespaceDemo.java`** dưới đây. Giữ nguyên số dấu cách đầu dòng trong code fence; helper `visible` thay dấu cách bằng `·` và ký tự xuống dòng bằng hai ký tự hiển thị `\n` để không phải đoán bằng mắt.

```java
public final class WhitespaceDemo {
    public static void main(String[] args) {
        String incidental = """
                cat
                  dog
                """;

        String dataIndent = """
                    cat
                    dog
                """;

        String trailing = """
                A\s\s
                B
                """;

        String noFinal = """
                cat
                dog""";

        String joined = """
                one \
                two
                """;

        System.out.println("incidental=" + visible(incidental));
        System.out.println("dataIndent=" + visible(dataIndent));
        System.out.println("trailing=" + visible(trailing));
        System.out.println("noFinal=" + visible(noFinal));
        System.out.println("joined=" + visible(joined));
    }

    private static String visible(String value) {
        return value.replace(" ", "·")
                    .replace("\t", "\\t")
                    .replace("\n", "\\n");
    }
}
```

Biên dịch với JDK hỗ trợ đích Java 15, rồi chạy:

```bash
javac --release 15 WhitespaceDemo.java
java WhitespaceDemo
```

Kết quả chuẩn (`\n` in ra là *hai ký tự nhìn thấy*, không phải việc console thật xuống dòng trong từng giá trị):

```text
incidental=cat\n··dog\n
dataIndent=····cat\n····dog\n
trailing=A··\nB\n
noFinal=cat\ndog
joined=one·two\n
```

**Giải thích từng dòng:**

1. `incidental`: cùng lề nguồn biến mất; `dog` có thêm hai dấu cách so với `cat` nên giữ lại.
2. `dataIndent`: đặt dấu đóng ít thụt hơn nội dung nên còn bốn dấu cách dữ liệu trước mỗi dòng.
3. `trailing`: mỗi `\s` tạo một dấu cách **sau bước strip**, vì vậy hai dấu cách **cuối dòng A** được giữ lại.
4. `noFinal`: dấu đóng ngay sau `dog`, nên không có `\n` cuối giá trị.
5. `joined`: escape `\` ngay trước line terminator triệt tiêu việc xuống dòng ở đó; dấu cách sau từ `one` vẫn còn, tạo giá trị `"one two\n"`.

Để xác nhận không phụ thuộc cách terminal hiển thị, bạn có thể bổ sung các phép kiểm `equals` sau ngay trong `main`:

```java
System.out.println(incidental.equals("cat\n  dog\n"));
System.out.println(dataIndent.equals("    cat\n    dog\n"));
System.out.println(trailing.equals("A  \nB\n"));
System.out.println(noFinal.equals("cat\ndog"));
System.out.println(joined.equals("one two\n"));
```

Năm câu lệnh trên đều in `true`. Chúng là phần mã thêm vào chương trình, **không** nằm trong stdout năm dòng của lần chạy ban đầu.

## 6. Khoảng trắng cuối dòng: tại sao `\s` quan trọng?

Trong text block, các dấu cách/tab *thật* xuất hiện ở cuối dòng nguồn được coi là incidental whitespace và bị loại bỏ. Quy tắc này giúp formatter hoặc editor xóa trailing spaces mà không làm hỏng giá trị thông thường. Nhưng có lúc **dấu cách cuối dòng là dữ liệu**, ví dụ một fixture so khớp byte, một bản ghi độ rộng cố định hoặc chuỗi đầu vào dùng cho bài test.

Cách ổn định trong text block:

```java
String padded = """
        A\s\s
        B\s
        """;
```

Giá trị là `"A  \nB \n"`: `A` có hai dấu cách cuối dòng, `B` có một. Điều này áp dụng từ Java 15 trở đi. Escape `\s` thường dễ đọc hơn việc giấu các dấu cách thật ở tận cuối một dòng code.

Tương tự, `\t` có thể tạo tab **thuộc dữ liệu** mà không phụ thuộc phần lề nguồn:

```java
String tsv = """
        id\tname
        1\tLan
        """;
```

Giá trị là `"id\tname\n1\tLan\n"`. Ký tự tab ở giữa các trường được sinh sau khi căn lề bị loại bỏ. Không trộn tab với space *ở phần căn lề nguồn* nếu muốn kết quả dễ dự đoán.

**Đừng nhầm `\s` và `\u0020`:** Java xử lý Unicode escape rất sớm trong quá trình phân tích mã nguồn, do đó `\u0020` không phải một cách tương đương để “né” bước xóa trailing whitespace của text block. Khi cần giữ dấu cách cuối dòng, dùng `\s` hoặc cách biểu đạt dữ liệu rõ ràng khác.

## 7. Dòng rỗng, newline và khoảng trắng bên trong dữ liệu

Có ba tình huống khác nhau:

| Tình huống trong nguồn text block | Giá trị sau xử lý | Ảnh hưởng |
| --- | --- | --- |
| Lề chung đứng trước mọi dòng nội dung | Bị xóa | Dễ căn lề code mà không đổi chuỗi |
| Lề *nhiều hơn* mức chung trên dòng không rỗng | Được giữ | Tạo cấp thụt vào trong nội dung |
| Dòng chỉ gồm dấu cách/tab nguồn | Trở thành dòng rỗng | Dấu cách trên dòng ấy không được bảo toàn |
| Dòng trống nằm giữa hai dòng nội dung | Giữ các line terminator tương ứng | Vẫn có dòng trống trong giá trị |
| Dấu cách ở cuối dòng nguồn | Bị xóa | Dùng `\s` nếu cần giữ |
| Dấu đóng nằm trên dòng riêng | Thường có `\n` cuối chuỗi | Phụ thuộc chỗ đặt dấu đóng |
| Dấu đóng sát nội dung cuối | Không tự thêm `\n` cuối | Tiện khi dữ liệu không kết thúc bằng newline |

**Lưu ý:** `String.strip()`, `stripLeading()` hoặc `stripTrailing()` được gọi **sau đó** trên một giá trị sẽ tạo **chuỗi mới** bằng cách xóa whitespace ở rìa toàn chuỗi; điều này có thể loại bỏ chính dữ liệu bạn cố giữ. Đừng gọi chúng chỉ để “làm cho đẹp” khi chuỗi chứa định dạng có ý nghĩa.

Một cách đọc đúng là coi `"\n"`, `" "`, `"\t"` và ký tự xuống dòng cuối cùng là **các thành phần của hợp đồng dữ liệu** nếu đầu nhận kiểm tra chính xác chuỗi hoặc byte.

## 8. Phân biệt biên dịch text block với các phương thức xử lý `String`

Các API dưới đây vẫn tồn tại trên Java hiện hành. Chọn API theo mục đích, không dùng chúng thay thế nhau:

| API | Có từ Java | Tác dụng | Cẩn trọng với dữ liệu |
| --- | --- | --- | --- |
| Cú pháp text block `"""` | 15 | Biểu diễn chuỗi nhiều dòng, tự loại bỏ incidental whitespace khi biên dịch | Khoảng trắng nguồn cuối dòng và lề chung không còn |
| `String.stripIndent()` | 15 | Tính lại lề tối thiểu trên **một String đã tồn tại**, xóa lề và trailing whitespace mỗi dòng | Có thể xóa cả phần lề dữ liệu đã được cố ý giữ |
| `String.indent(int)` | 12 | Thêm/bớt lề cho từng dòng của String | Chuẩn hóa line endings và tạo LF sau các dòng không rỗng theo hợp đồng API |
| `String.strip()` | 11 | Xóa whitespace đầu và cuối **toàn bộ String** | Có thể làm mất leading spaces/newline cuối |
| `String.translateEscapes()` | 15 | Diễn giải escape sequences trong dữ liệu String | Chỉ dùng khi chuỗi thực sự chứa chuỗi escape cần diễn giải |

Ví dụ áp dụng `stripIndent()` cho **chuỗi có sẵn**:

```java
String imported = "    top\n      child";
String adjusted = imported.stripIndent();
System.out.println(adjusted.equals("top\n  child")); // true
```

Không mặc định rằng việc gọi `stripIndent()` lần nữa trên một text block là vô hại: trình biên dịch **đã** thực hiện loại bỏ căn lề khi tạo text block. Nếu bạn cố ý giữ bốn dấu cách bằng cách đặt dấu đóng sang trái, một lời gọi `stripIndent()` bổ sung có thể loại bỏ chính bốn dấu cách đó.

Ngoài ra, thuật toán `stripIndent()` xét **cả dòng cuối**, ngay cả khi dòng cuối chỉ có whitespace. Chuỗi dữ liệu nhập từ ngoài không nhất thiết có cùng cấu trúc dòng cuối như phần nguồn text block (dòng chứa lề trước dấu đóng), nên đừng suy ra hai trường hợp có kết quả giống nhau chỉ vì chúng nhìn giống trong editor.

## 9. Ví dụ thực tế: dữ liệu nào dễ bị hỏng vì căn lề sai?

- **YAML:** số dấu cách đầu dòng quyết định quan hệ cha–con. Lề tương đối giữa các dòng phải được giữ chính xác. Text block có thể bỏ lề Java xung quanh, nhưng không được vô tình bỏ mức lề vốn thuộc YAML.
- **SQL nhiều dòng:** căn lề thường chủ yếu để người đọc dễ theo dõi; mặc dù nhiều công cụ SQL bỏ qua whitespace không nằm trong chuỗi literal, bạn vẫn nên kiểm tra truy vấn thật và không tùy tiện chuẩn hóa nếu định dạng là một phần của test/snapshot.
- **HTML và nội dung thư:** khoảng trắng có thể quan trọng trong thẻ `<pre>`, văn bản tiền định dạng, template hoặc các hệ thống so khớp chuỗi; nhìn đẹp trong source chưa đủ xác nhận nội dung cuối.
- **CSV/TSV, fixed-width và test fixtures:** dấu cách cuối trường, tab, newline cuối tệp và độ rộng trường có thể mang ý nghĩa chính xác. Dùng escape rõ ràng, `equals` hoặc kiểm tra byte sau bước mã hóa.

Ví dụ một YAML hợp lệ về căn lề trong text block:

```java
String yaml = """
        server:
          port: 8080
          host: localhost
        """;
```

Giá trị cuối tương đương `"server:\n  port: 8080\n  host: localhost\n"`. Hai dấu cách trước `port` và `host` là **dữ liệu YAML**, không phải lề Java cần xóa.

## 10. Kiểm tra lỗi khoảng trắng một cách có hệ thống

Khi chuỗi in ra “trông đúng” nhưng so sánh hoặc parser vẫn báo lỗi, làm theo thứ tự:

1. **Đặt kỳ vọng rõ ràng:** viết chính xác `String expected = "root\n  child\n";` cho fixture nhỏ, hoặc đọc định dạng của hệ thống nhận.
2. **Hiển thị ký tự ẩn:** thay space bằng `·`, tab bằng `\\t`, newline bằng `\\n` khi debug; không đưa các ký hiệu minh họa này vào dữ liệu thực.
3. **Kiểm tra dấu đóng:** dấu `"""` căn ngang với dòng nào? Nó ở dòng riêng hay sát cuối nội dung? Vị trí đó tác động đến lề tối thiểu/newline.
4. **Kiểm tra trailing spaces:** nếu chúng là dữ liệu thì biểu diễn bằng `\s`, `\t` hoặc escape tương ứng thay vì gõ bằng tay ở cuối dòng.
5. **Kiểm tra formatter/editor:** formatter có di chuyển dấu đóng, thay tab bằng space, hoặc chỉnh lề các dòng theo cách làm thay đổi độ lệch giữa nội dung và dấu đóng hay không?
6. **So sánh giá trị:** dùng `actual.equals(expected)`; khi cần soi sâu, dùng `length()`, `charAt()` hoặc `codePoints()` để biết chính xác ký tự ở vị trí sai.
7. **Xác nhận với JDK mục tiêu:** dùng `javac --release 15` khi dự án cam kết chạy từ Java 15 và compiler hỗ trợ mốc đích ấy. Text blocks có thể dùng ở Java mới mà không cần preview flag.

### Những hiểu nhầm cần tránh

- “Java xóa toàn bộ dấu cách ở đầu mỗi dòng”: **Sai.** Java xóa phần lề tối thiểu, nên độ lệch tương đối hoặc phần lề vượt mức tối thiểu vẫn còn.
- “Cứ đưa ba dấu nháy ở đâu cũng không đổi giá trị”: **Sai.** Dấu đóng ở dòng riêng/sát nội dung và mức thụt đầu dòng có thể làm thay đổi chuỗi.
- “Dấu cách viết cuối dòng chắc chắn được giữ”: **Sai với text blocks.** Chúng thường bị strip; dùng `\s` để biểu đạt có chủ ý.
- “`stripIndent()` giống `strip()`”: **Sai.** Một phương thức xét căn lề theo từng dòng, phương thức kia xét hai rìa của toàn chuỗi.
- “`\t` lúc nào cũng rộng bốn dấu cách”: **Sai.** Tab là một ký tự dữ liệu; độ rộng trình bày do môi trường hiển thị quyết định, còn thuật toán thụt lề đếm nó như một ký tự.
- “Mọi ký tự trắng trong output đều do Java tự thêm”: **Sai.** Cần phân biệt newline có trong text block, space/tab được giữ từ lề tương đối và escape được diễn giải sau cùng.

## 11. Tự kiểm tra

**Câu 1.** Với:

```java
String s = """
        a
          b
        """;
```

Giá trị `s` là gì? **Đáp án:** `"a\n  b\n"`. Hai dấu cách trước `b` thuộc dữ liệu, không bị loại bỏ cùng lề chung.

**Câu 2.** Muốn một text block lưu `"item  \n"` (hai dấu cách giữa `item` và newline), nên đặt hai dấu cách thật ở cuối dòng hay dùng `item\s\s`? **Đáp án:** dùng `item\s\s`; cách này giữ được hai dấu cách sau bước loại bỏ whitespace nguồn.

**Câu 3.** Nếu dấu đóng chuyển từ dòng riêng lên ngay sau từ cuối, điều gì thay đổi thường gặp? **Đáp án:** newline cuối chuỗi biến mất. Các khoảng trắng đầu dòng vẫn phải tính theo quy tắc của từng trường hợp.

**Câu 4.** Có nên gọi `strip()` lên một YAML hoặc fixture vừa tạo để “xóa lề Java” không? **Đáp án:** không mặc định; lề Java đã được xử lý trong text block, còn `strip()` có thể xóa whitespace có ý nghĩa ở rìa dữ liệu.

**Đạt yêu cầu** khi bạn có thể xác định ba thứ riêng biệt từ một text block: (1) lề Java bị xóa, (2) khoảng trắng dữ liệu còn lại, (3) vị trí newline/tab cuối cùng trong giá trị `String`.

## 12. Tài liệu chính thức, còn giá trị áp dụng

- [Java Language Specification SE 15, §3.10.6 – Text Blocks](https://docs.oracle.com/javase/specs/jls/se15/html/jls-3.html#jls-3.10.6): quy tắc chuẩn hóa LF → strip incidental whitespace → diễn giải escape.
- [Javadoc `String` trong Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): tra cứu hợp đồng đang áp dụng của `stripIndent()`, `indent(int)`, `strip()` và `translateEscapes()`.
- [Javadoc `String` trong Java SE 15](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html): đối chiếu khi triển khai với mốc Java 15.
- [Oracle Text Blocks Guide (Java 25)](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): giải thích trực quan lề ngẫu nhiên/lề dữ liệu, newline cuối và escape `\s`.