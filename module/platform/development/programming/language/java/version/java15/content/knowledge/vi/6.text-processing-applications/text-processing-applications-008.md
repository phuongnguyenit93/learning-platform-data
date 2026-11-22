# Giữ định dạng ổn định khi IDE tự căn lề: Java text block

## Mục tiêu và bối cảnh

Trong Java 15+, **text block** (khối văn bản viết bằng ba dấu nháy kép `"""`) cho phép khai báo một `String` nhiều dòng ngay trong mã nguồn. Đây là tính năng chính thức từ Java 15 (JEP 378) và vẫn hữu ích trong Java hiện đại, đặc biệt khi viết JSON, SQL, HTML, XML, thông báo nhiều dòng hoặc dữ liệu mẫu của bài kiểm thử.

Tuy nhiên, một IDE có thể tự động căn lề sau khi bạn nhấn *Reformat Code*, đổi cấu trúc khối mã hoặc di chuyển dấu `"""` đóng. Nếu thay đổi đó làm **lề tương đối** của nội dung so với dấu đóng khác đi, giá trị `String` có thể thay đổi, dù nhìn bằng mắt chỉ giống một thao tác làm đẹp mã.

Bài này hướng dẫn cách giữ nội dung ổn định khi chỉnh sửa và format mã Java. Bạn sẽ biết:

- Phân biệt **lề của mã nguồn** với **dấu cách thực sự thuộc giá trị chuỗi**.
- Hiểu cách Java loại phần lề phụ (*incidental indentation*), vị trí dấu đóng và dấu xuống dòng cuối.
- Biểu diễn dấu cách có chủ đích bằng `\s`, và dùng `\` cuối dòng khi cần ghép dòng nguồn.
- Viết kiểm thử phát hiện thay đổi vô tình về dấu cách, số dòng và ký tự xuống dòng.
- Chọn giữa text block, `String.join` và `String.indent` khi dữ liệu cần định dạng rất chính xác.

**Phạm vi phiên bản:** Tất cả kỹ thuật chính trong bài dựa trên text block ổn định từ Java 15 và các API `String` còn được dùng trong các JDK hiện đại. Chương trình hoàn chỉnh chạy với **JDK 17+**, không cần bật preview.

## 1. Java lưu gì từ text block?

Xét đoạn mã nằm trong một phương thức:

```java
String hierarchy = """
        root
          child
            leaf
        """;
```

Giá trị chuỗi thực là:

```text
root
  child
    leaf
```

Nếu biểu diễn rõ từng ký tự bằng cú pháp literal Java, nó tương đương:

```java
String expected = "root\n  child\n    leaf\n";
System.out.println(hierarchy.equals(expected)); // true
```

Java đã bỏ phần lề chung dùng để căn chỉnh mã nguồn, nhưng giữ lại **hai dấu cách tương đối trước `child`** và **bốn dấu cách trước `leaf`**. Đồng thời, text block trên có một ký tự `\n` cuối cùng vì dấu đóng nằm ở dòng riêng.

Công cụ IDE thường muốn căn lề các dòng mã cho đẹp. Khi mọi dòng nội dung và dấu đóng được dịch cùng mức, kết quả có thể giữ nguyên; khi vị trí tương đối thay đổi, chuỗi có thể không còn như trước.

## 2. Ba giai đoạn xử lý whitespace của text block

Theo quy tắc ngôn ngữ Java, nội dung text block được tính theo các bước quan trọng sau:

1. **Chuẩn hóa line terminator:** ký tự kết thúc dòng trong nguồn (CR hoặc CRLF) được chuẩn hóa về LF, tức `\n`.
2. **Loại incidental whitespace:** Java xác định khoảng trắng thụt lề chung của các dòng có nội dung và xét cả mức lề của dấu đóng khi dấu đóng đứng riêng một dòng. Phần lề phụ và phần lớn khoảng trắng cuối dòng bị loại bỏ.
3. **Diễn giải escape sequence:** chẳng hạn `\n`, `\t`, `\\`, `\s` và escape nối dòng `\` trước line terminator được xử lý sau bước loại lề.

Vì thứ tự này, hai đoạn mã nhìn khá giống nhau có thể mang nội dung khác nhau nếu IDE chỉnh lại dấu đóng hoặc lề của một dòng riêng lẻ.

**Chú ý:** `String.stripIndent()` là API thao tác với chuỗi lúc chạy, có quy tắc liên quan đến loại incidental indentation. Java thực hiện loại lề của **literal text block** ngay khi tính giá trị; bạn không cần gọi `.stripIndent()` cho mọi text block. Gọi bổ sung trên dữ liệu có lề cố ý có thể tiếp tục xóa whitespace có ý nghĩa.

## 3. Khi nào IDE tự căn lề mà không làm đổi giá trị?

Hai text block sau có **cùng một giá trị** nếu phần nội dung và dấu đóng cùng dịch sang phải, còn mức lề tương đối giữ nguyên:

```java
String before = """
        alpha
          beta
        """;

String after = """
            alpha
              beta
            """;

System.out.println(before.equals(after)); // true
```

Giá trị của cả hai là `"alpha\n  beta\n"`.

Điều kiện quan trọng là Java vẫn xác định được **cùng lượng lề cần loại và cùng lượng lề nội dung cần giữ**. Việc chuyển cả khối mã sang một cấp thụt lề mới, chẳng hạn đưa khai báo vào một `if` hoặc phương thức, thường an toàn khi IDE căn chỉnh đồng bộ nội dung và dấu đóng.

Đừng hiểu điều này thành lời bảo đảm rằng *mọi* chức năng Reformat Code đều vô hại. Những thay đổi trong cấu hình formatter, sử dụng tab/space hoặc chỉnh sửa thủ công có thể làm thay đổi vị trí tương đối. Hãy kiểm tra kết quả khi chuỗi cần chính xác từng ký tự.

## 4. Dấu đóng `"""` có thể làm chuỗi đổi nội dung

Dấu đóng ảnh hưởng tới mức lề phụ mà Java loại. So sánh:

```java
String normal = """
        alpha
          beta
        """;

String closingMovedLeft = """
        alpha
          beta
      """;

System.out.println(normal.equals("alpha\n  beta\n")); // true
System.out.println(closingMovedLeft.equals("  alpha\n    beta\n")); // true
```

Ở `closingMovedLeft`, dấu đóng được đưa **sang trái hai dấu cách** so với mức lề của dòng `alpha`. Vì vậy, Java chỉ loại lượng lề nhỏ hơn, giữ lại hai dấu cách đầu mỗi dòng.

| Bố cục source code | Nội dung thực tế |
| --- | --- |
| Dấu đóng căn cùng lề với `alpha` | `"alpha\n  beta\n"` |
| Dấu đóng lệch sang trái hai space | `"  alpha\n    beta\n"` |

Nếu IDE hoặc người sửa mã chuyển dấu đóng về mức lề khác, sự khác biệt đó có thể xuất hiện trong file được tạo, snapshot test hoặc request body.

**Quy ước nên dùng:** Khi không cần giữ lề tuyệt đối ở đầu chuỗi, hãy đặt dấu `"""` đóng **cùng mức lề với dòng có nội dung ít thụt lề nhất**. Khi thay đổi cấu trúc mã, di chuyển nội dung và dấu đóng như một khối. Nếu cần dấu cách đầu dòng thật, biểu diễn chủ động thay vì dựa vào việc đặt dấu đóng lệch trái.

## 5. Giữ dấu cách có ý nghĩa bằng escape `\s`

Escape `\s` (có trong Java 15+) biểu diễn **một dấu cách ASCII U+0020**. Nó rất hữu ích khi cần dấu cách **cuối dòng** mà text block thường tự loại bỏ, hoặc cần chỉ rõ dấu cách **đầu dòng** mà formatter có thể khiến người đọc khó nhận ra.

### 5.1. Dấu cách đầu dòng

```java
String explicitLeading = """
        \s\skey
        """;

System.out.println(explicitLeading.equals("  key\n")); // true
```

Hai `\s` tạo chính xác hai dấu cách trước `key` sau khi text block được xử lý. Khi IDE dịch toàn bộ khối một cách đồng bộ, hai dấu cách này vẫn hiện diện trong giá trị, không phụ thuộc vào số dấu cách dùng chỉ để căn mã.

Dùng `\s` khi cần làm một hoặc vài dấu cách **có chủ đích** thật dễ nhận thấy. Không cần viết `\s` cho mọi dấu cách thông thường trong đoạn văn; như vậy mã sẽ khó đọc hơn.

### 5.2. Dấu cách cuối dòng

Whitespace thông thường ở cuối dòng text block thường bị bỏ:

```java
String noTrailingSpace = """
        X
        """;
System.out.println(noTrailingSpace.equals("X\n")); // true
```

Khi cần giữ lại một space thật ở cuối dòng:

```java
String explicitTrailing = """
        X\s
        """;
System.out.println(explicitTrailing.equals("X \n")); // true
```

Lúc này dấu cách được sinh ra **sau bước loại trailing whitespace**. Đây là cách tường minh khi định dạng đầu ra cần khoảng trắng cuối dòng. Đừng chỉ gõ một dấu cách vô hình sau chữ `X` rồi hy vọng IDE giữ nguyên.

**Lưu ý:** Một số định dạng (như Markdown) coi dấu cách cuối dòng là ký hiệu có nghĩa; nhiều định dạng khác lại muốn loại chúng. Hãy xác định yêu cầu thực tế trước khi cố giữ whitespace.

## 6. Giữ hay bỏ ký tự xuống dòng cuối

Vị trí dấu đóng và escape có thể quyết định chuỗi có ký tự newline cuối hay không. IDE thường có chức năng quản lý newline ở cuối tệp; cần phân biệt **newline của tệp .java** với **newline nằm trong text block**.

Đặt dấu đóng ở dòng riêng:

```java
String withFinalNewline = """
        alpha
        beta
        """;

System.out.println(withFinalNewline.equals("alpha\nbeta\n")); // true
```

Đặt dấu đóng ngay sau ký tự cuối của nội dung:

```java
String withoutFinalNewline = """
        alpha
        beta""";

System.out.println(withoutFinalNewline.equals("alpha\nbeta")); // true
```

Hoặc vẫn đặt dấu đóng ở dòng riêng nhưng dùng escape nối dòng `\` ở cuối dòng nội dung:

```java
String sameResult = """
        alpha
        beta\
        """;

System.out.println(sameResult.equals("alpha\nbeta")); // true
```

**Hành vi cần kiểm soát:** Nếu formatter chuyển dấu đóng từ dòng riêng vào cuối dòng nội dung (hoặc ngược lại), kết quả có thể đổi dấu xuống dòng cuối. Với văn bản nhiều dòng, một `\n` thừa hoặc thiếu là thay đổi thật khi so sánh bằng `equals()` hoặc ghi dữ liệu ra file.

Chỉ dùng escape `\` + line terminator tại những nơi chủ đích **nối hai dòng nguồn thành một đoạn liên tục**: nó loại bỏ dấu xuống dòng đó và **không tự chèn dấu cách**. Khi muốn có một space giữa hai đoạn, giữ dấu cách trước `\` hoặc dùng `\s` như trong bài về escape nối dòng.

## 7. Dòng trống, lề tương đối và tab

### 7.1. Dòng trống có thể mang ý nghĩa

```java
String text = """
        top

          indented
        """;

System.out.println(text.equals("top\n\n  indented\n")); // true
```

Dòng trống giữa hai dòng nội dung tạo thêm một `\n` trong giá trị. Nếu IDE xóa dòng trống này khi chỉnh sửa source thì payload thay đổi; việc thay khoảng cách trước dấu `"""` đóng không tự thay thế một dòng trống nội dung.

### 7.2. Thụt lề tương đối vẫn được giữ

Giá trị của:

```java
String nested = """
        parent
            child
        """;
```

là `"parent\n    child\n"` (bốn dấu cách trước `child`). Vì vậy nếu bạn thêm hoặc bớt một level lề chỉ ở dòng `child`, kết quả sẽ thay đổi dù dấu đóng không di chuyển.

### 7.3. Không trộn tab và space nếu cần độ chính xác

Tab không có chiều rộng cố định trong mọi trình soạn thảo: IDE có thể *hiển thị* một tab bằng nhiều ô trống, và bộ formatter có thể chuyển đổi tab thành space tùy cấu hình. Quy tắc tính lề của Java hoạt động trên các ký tự whitespace trong source, không dựa vào số cột bạn thấy trên màn hình.

Đối với text block nhạy với whitespace, nên dùng **space nhất quán cho lề**. Nếu giá trị thực sự phải chứa ký tự tab, biểu diễn rõ bằng `\t` và kiểm tra chuỗi kết quả; đừng dựa vào cách IDE hiển thị tab.

## 8. Trường hợp sử dụng thực tế: JSON, SQL, HTML và snapshot

### 8.1. JSON: lề trong dữ liệu có thể quan trọng với kiểm thử

```java
String json = """
        {
          "name": "Lan",
          "active": true
        }
        """;
```

Đối với JSON hợp lệ, whitespace bên ngoài các string JSON thường không thay đổi dữ liệu sau khi parse. Nhưng **chuỗi raw** ở trên vẫn chứa dấu cách và newline cụ thể. Một snapshot test so sánh nguyên văn sẽ báo khác nếu IDE làm đổi lề. Thay vì đoán từ cách hiển thị, hãy dùng test rõ kỳ vọng hoặc parse JSON rồi so sánh cấu trúc **khi mục tiêu thật sự là kiểm thử ngữ nghĩa JSON**.

Trong hệ thống có JSON động, dùng thư viện serializer/decoder phù hợp. Text block là cách viết chuỗi trong source code; nó không tự escape dữ liệu đầu vào và không thay thế JSON serializer.

### 8.2. SQL: muốn dễ đọc hay muốn giá trị cố định?

```java
String sql = """
        SELECT id, name
        FROM employees
        WHERE department_id = ?
        ORDER BY name
        """;
```

Với SQL, nhiều dấu cách và newline được engine chấp nhận mà không làm đổi ý định câu lệnh. Tuy vậy, các hệ thống lưu snapshot truy vấn, so sánh raw string hoặc tạo dấu băm vẫn có thể nhận thấy khác biệt whitespace. Dùng `PreparedStatement` để bind tham số; định dạng text block không phải cơ chế bảo vệ chống SQL injection.

### 8.3. HTML, email và văn bản cần giữ bố cục

Với email plain text, Markdown hoặc template có quy ước lề riêng, newline và space có thể ảnh hưởng cách hiển thị. Khi yêu cầu định dạng chính xác từng ký tự, hãy xác định rõ expected string và viết test. Nếu tài liệu cần được tạo động hoặc có logic template phức tạp, cân nhắc thư viện/template engine thay vì cố nhét mọi logic vào text block.

## 9. Các lựa chọn khác khi cần định dạng tuyệt đối

Text block giúp nội dung nhiều dòng **dễ đọc**, nhưng khi mỗi ký tự whitespace đều là một phần của giao thức hoặc kết quả kiểm thử, đôi khi nên dùng API mô tả nội dung trực tiếp.

### 9.1. Dùng `String.join` để quyết định dấu phân cách

```java
String exact = String.join("\n", "alpha", "  beta");
System.out.println(exact.equals("alpha\n  beta")); // true
```

Ở đây không có newline cuối vì hai phần tử được nối bằng đúng một `\n`. Hai dấu cách trước `beta` nằm bên trong literal bình thường, nhìn rõ trong từng phần tử. Chọn `String.join` khi bạn muốn tạo chuỗi từ các dòng và kiểm soát dấu nối.

### 9.2. Dùng `String.indent` cho lề đầu ra có chủ đích

```java
String indented = """
        x
        y
        """.indent(2);

System.out.println(indented.equals("  x\n  y\n")); // true
```

`String.indent(2)` thêm hai dấu cách ở đầu mỗi dòng của kết quả. API này cũng có quy tắc chuẩn hóa line terminator; nó có thể bảo đảm newline sau dòng cuối, vì vậy cần hiểu đầu ra trước khi dùng cho định dạng chính xác. Khi muốn giữ lề đầu ra cố định, sử dụng một bước xử lý được kiểm soát có thể rõ ràng hơn so với căn vị trí dấu đóng sang trái để giữ dấu cách.

Tương tự, `String.stripIndent()` chỉ nên dùng khi bạn **có chủ đích** loại lề dư của một chuỗi; gọi thêm một cách máy móc có thể xóa lề đang mang ý nghĩa. Cả `indent` và `stripIndent` đều hoạt động trên **giá trị chuỗi lúc chạy**, không phải cài đặt trực tiếp về cách IDE căn lề mã nguồn.

### 9.3. Khi dữ liệu là đặc tả máy

Nếu hệ thống yêu cầu một payload byte-for-byte cố định (chữ ký, checksum, fixture protocol), hãy bảo đảm charset, newline (LF/CRLF), khoảng trắng và nội dung cuối được xác định. Test chính xác các ký tự hoặc byte. Với tài liệu dài hay tệp nguồn được quản lý riêng, có thể lưu fixture ở resource và đọc bằng API phù hợp; khi đó IDE formatter của tệp Java không tác động trực tiếp lên nội dung fixture.

## 10. Quy trình an toàn khi bật tự động format trong IDE

1. **Chọn quy ước formatter nhất quán cho dự án** (space/tab, indent size, vùng text block). Công cụ khác nhau có thể đưa ra cách canh khác nhau; đừng phụ thuộc vào một ảnh chụp màn hình của IDE để kết luận giá trị chuỗi.
2. **Căn nội dung và dấu đóng đồng bộ.** Khi di chuyển khối mã, kiểm tra dấu đóng còn ở mức lề mong muốn không.
3. **Biểu diễn whitespace có ý nghĩa rõ ràng.** Dùng `\s` cho space cần bảo tồn, `\t` cho tab cần bảo tồn, và chủ động chọn có hay không có `\n` cuối.
4. **Không nhầm thay đổi cách hiển thị với thay đổi dữ liệu.** Một dòng nhìn như có ba khoảng trắng có thể chứa tab; newline hiển thị trong terminal cũng có thể do lệnh in thêm vào.
5. **Chạy lại phép kiểm tra giá trị sau reformat.** Với dữ liệu cố định, so sánh nguyên văn bằng `equals` hoặc unit test; với dữ liệu có cấu trúc, chọn so sánh raw hay ngữ nghĩa theo mục tiêu.
6. **Review diff của các text block chứa dữ liệu quan trọng.** Xem cả dấu đóng, ký tự khoảng trắng và newline khi PR có thay đổi format tự động.

Tránh tắt formatter cho cả dự án chỉ vì một chuỗi khó căn lề. Hãy lựa chọn cách biểu diễn chuỗi làm rõ dữ liệu cần bảo tồn và cấu hình formatter thống nhất. Với một vài đoạn có yêu cầu nghiêm ngặt, điều quan trọng nhất vẫn là **kiểm thử giá trị thực**.

## 11. Chương trình Java hoàn chỉnh có thể chạy

Tạo tệp **`TextBlockIndentDemo.java`** ở mã hóa UTF-8. Chương trình kiểm tra kết quả bằng `equals()` để không phụ thuộc vào cách terminal hiển thị space hoặc newline.

```java
public class TextBlockIndentDemo {
    public static void main(String[] args) {
        String original = """
                alpha
                  beta
                """;

        String shiftedTogether = """
                    alpha
                      beta
                    """;

        String closingMovedLeft = """
                alpha
                  beta
              """;

        String explicitLeading = """
                \s\skey
                """;

        String explicitTrailing = """
                X\s
                """;

        String withFinalNewline = """
                alpha
                beta
                """;

        String noFinalNewline = """
                alpha
                beta\
                """;

        String blankLine = """
                top

                  indented
                """;

        String joined = String.join("\n", "alpha", "  beta");

        String indented = """
                x
                y
                """.indent(2);

        System.out.println("sameRelativeIndent="
                + original.equals(shiftedTogether));
        System.out.println("baseMatches="
                + original.equals("alpha\n  beta\n"));
        System.out.println("closingMovedLeft="
                + closingMovedLeft.equals("  alpha\n    beta\n"));
        System.out.println("explicitLeading="
                + explicitLeading.equals("  key\n"));
        System.out.println("explicitTrailing="
                + explicitTrailing.equals("X \n"));
        System.out.println("finalNewline="
                + withFinalNewline.endsWith("\n"));
        System.out.println("noFinalNewline="
                + noFinalNewline.equals("alpha\nbeta"));
        System.out.println("blankLine="
                + blankLine.equals("top\n\n  indented\n"));
        System.out.println("joinExact="
                + joined.equals("alpha\n  beta"));
        System.out.println("indentAddsNewline="
                + indented.equals("  x\n  y\n"));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 TextBlockIndentDemo.java
java TextBlockIndentDemo
```

**Stdout chính xác:**

```text
sameRelativeIndent=true
baseMatches=true
closingMovedLeft=true
explicitLeading=true
explicitTrailing=true
finalNewline=true
noFinalNewline=true
blankLine=true
joinExact=true
indentAddsNewline=true
```

Diễn giải: cùng mức lề tương đối cho cùng `String`; đưa dấu đóng sang trái có thể **giữ thêm space** trong kết quả; escape `\s` bảo tồn dấu cách có ý nghĩa; dấu `\` cuối dòng bỏ newline; dòng trống là một phần nội dung; còn `String.join` và `String.indent` tạo lề/dấu phân cách bằng API rõ ràng. Các kết quả dạng boolean khiến lỗi một dấu cách trở nên dễ phát hiện hơn khi nhìn một bản in trực tiếp.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Sau Reformat Code, snapshot khác dù nội dung chữ giống nhau | Lề tương đối hoặc vị trí dấu đóng đã thay đổi | Kiểm tra dấu đóng, các dòng được thụt sâu hơn và so sánh chuỗi nguyên văn |
| Dòng đầu tự nhiên có thêm dấu cách | Dấu `"""` đóng nằm bên trái lề nội dung, khiến Java loại ít lề hơn | Căn dấu đóng theo dòng ít thụt lề nhất hoặc biểu diễn lề thực bằng `\s` |
| Dấu cách cuối dòng biến mất | Text block bỏ phần lớn trailing whitespace | Dùng `\s` để chỉ rõ space phải giữ |
| Thêm/bớt newline cuối khi sửa dấu đóng | Dấu đóng đứng riêng dòng hay đứng sát nội dung tạo giá trị khác nhau | Kiểm tra `endsWith("\n")`; dùng `\` cuối dòng nếu chủ đích bỏ newline |
| Tab trông như space và gây lệch | Tab có cách hiển thị khác giữa các IDE/cấu hình | Dùng space nhất quán cho lề; dùng `\t` khi thật sự cần ký tự tab |
| Tưởng gọi `stripIndent()` luôn an toàn | Có thể loại lề thực sự cần giữ | Chỉ gọi khi có yêu cầu loại lề rõ ràng, kèm expected-value test |
| In bằng `println` mà không thấy khác biệt | Terminal khó thể hiện trailing space và `println` tự thêm newline | Dùng `equals`, `length`, escaped representation hoặc kiểm tra byte |
| JSON/SQL động bị sai khi nhét vào text block | Text block chỉ là `String`, không tự escape/bind dữ liệu | Dùng JSON serializer, `PreparedStatement` hay API/template chuyên biệt |

## 13. Bài tập tự kiểm tra

**Bài 1.** Giá trị của đoạn sau có hai dấu cách trước chữ `B` không?

```java
String value = """
        A
          B
        """;
```

**Đáp án:** Có. Giá trị là `"A\n  B\n"`, gồm hai dấu cách trước `B` và một newline cuối.

**Bài 2.** Nếu chuyển cả các dòng nội dung lẫn dấu `"""` đóng thêm bốn space sang phải, có nhất thiết đổi chuỗi không?

**Đáp án:** Không. Nếu mức lề **tương đối** giữ nguyên, Java loại phần lề chung tương ứng và giá trị không đổi. Nhưng thay đổi một dòng hoặc chỉ dấu đóng có thể làm đổi giá trị.

**Bài 3.** Viết text block có giá trị đúng `"  key\n"` mà không phải đặt dấu đóng lệch trái.

```java
String value = """
        \s\skey
        """;
```

**Đáp án:** Hai `\s` tạo đúng hai space ở đầu, dấu đóng trên dòng riêng giữ newline cuối.

**Bài 4.** Vì sao `String.join("\n", "a", "b")` có thể phù hợp hơn text block khi không được phép có newline cuối?

**Đáp án:** Bạn chỉ rõ dấu phân cách giữa các phần tử; `join` không tự thêm dấu phân cách sau phần tử cuối. Với text block, người viết cần chú ý vị trí dấu đóng hoặc escape nối dòng cuối.

**Bài 5.** Vì sao không nên xem việc parse được JSON là bằng chứng một text block không đổi byte?

**Đáp án:** JSON có thể biểu diễn cùng cấu trúc dữ liệu khi whitespace bên ngoài string thay đổi. Muốn kiểm tra byte-for-byte, so sánh chuỗi nguồn hoặc byte thực tế, không chỉ so sánh kết quả parse.

## Ghi nhớ

Để giữ ổn định văn bản khi IDE tự căn lề, hãy **xác định chính xác whitespace nào là lề source và whitespace nào là dữ liệu**. Lề chung của text block thường được loại; lề tương đối và vị trí dấu đóng có thể ảnh hưởng nội dung; `\s` giúp ghi rõ space có ý nghĩa; newline cuối phải được quyết định có chủ đích. Nếu dữ liệu phải bất biến từng ký tự, cách đáng tin cậy là **kiểm tra giá trị sau biên dịch bằng test** và lựa chọn API biểu diễn phù hợp.

### Tài liệu chính thức còn áp dụng

- [OpenJDK JEP 378 — Text Blocks (chuẩn từ Java 15)](https://openjdk.org/jeps/378)
- [Oracle — Text Blocks, Programmer's Guide (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html)
- [Java Language Specification — Text Blocks, mục 3.10.6](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6)
- [Java SE 21 — String API: indent, stripIndent, translateEscapes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
