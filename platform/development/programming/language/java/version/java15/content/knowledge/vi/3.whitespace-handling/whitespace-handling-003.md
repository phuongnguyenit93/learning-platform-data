# Vai trò của dòng đóng trong tính toán thụt lề của Java text block

> **Phạm vi:** Đây là bài về **khoảng trắng (whitespace) của text block** trong Java, cụ thể là cách vị trí dòng đóng `"""` ảnh hưởng đến số ký tự thụt lề được loại bỏ và số ký tự được giữ lại trong `String`. Text block trở thành cú pháp Java chính thức từ **Java 15** và tiếp tục được hỗ trợ trong các JDK hiện đại (chẳng hạn JDK 17, 21, 25). Bài học chỉ sử dụng cơ chế đã chuẩn hóa và còn áp dụng hiện nay.

## 1. Dòng đóng `"""` có ý nghĩa gì?

Một **text block** là cách viết một giá trị `String` nhiều dòng. Nó bắt đầu bằng ba dấu nháy kép `"""` và **bắt buộc** có dấu xuống dòng sau dấu mở; sau đó là nội dung và ba dấu nháy kép đóng.

```java
String message = """
        Xin chào
          Java
        """;
```

- **Dấu mở** `"""` khởi đầu text block; vị trí thụt lề của dấu mở **không quyết định** lượng khoảng trắng bị loại bỏ.
- **Dòng nội dung** có thể có khoảng trắng đầu dòng thực sự cần giữ, ví dụ một dòng con lùi sâu hơn dòng cha.
- **Dấu đóng** `"""`, khi đứng trên **một dòng riêng**, tham gia xác định **lề trái chung** để Java loại bỏ *incidental whitespace* (khoảng trắng thụt lề phục vụ định dạng mã nguồn).
- Khi dịch dòng đóng sang trái hoặc phải, bạn có thể thay đổi **nội dung thực tế của `String`**, dù các dòng chữ vẫn giữ nguyên vị trí.
- Khoảng trắng trước dấu đóng không tự trở thành dòng nội dung có ký tự khoảng trắng: sau bước xử lý thụt lề, nó được loại bỏ. Tuy nhiên, **dấu xuống dòng ngay trước dấu đóng** thường vẫn nằm trong kết quả, trừ khi chủ động loại bỏ bằng cách đặt dấu đóng sát dòng cuối hoặc dùng escape phù hợp.

Mục đích là cho phép mã Java được thụt lề dễ đọc mà không vô tình đưa toàn bộ phần thụt lề của mã nguồn vào chuỗi.

## 2. Cơ chế xử lý thụt lề: dòng đóng là một ứng viên của lề trái

Đối với trường hợp thường gặp là dấu đóng `"""` nằm **một mình trên dòng cuối**:

1. Java chuẩn hóa các ký tự kết thúc dòng trong text block thành `\n`.
2. Xác định số ký tự trắng **đầu dòng** của từng dòng nội dung **không trống**. Dòng chứa riêng dấu đóng cũng có một số ký tự trắng đứng trước `"""`, được xét như ứng viên để xác định mức thụt lề chung.
3. Lấy **giá trị nhỏ nhất** trong các độ thụt lề xét được. Đây là lượng thụt lề tình cờ (*incidental indentation*) cần bỏ.
4. Bỏ tối đa lượng đó ở đầu **mỗi dòng nội dung**; khoảng trắng còn lại là **essential indentation** (thụt lề có ý nghĩa, được giữ trong chuỗi). Khoảng trắng cuối dòng được xử lý theo quy tắc text block.
5. Cuối cùng mới diễn giải các escape sequence, chẳng hạn `\s` hoặc dấu gạch chéo ngược ngay trước xuống dòng.

Có thể nhớ bằng công thức cho ví dụ chỉ dùng dấu cách (spaces):

```text
n = min(thụt_lề_các_dòng_nội_dung_không_trống,
        thụt_lề_dòng_đóng_nếu_dấu_đóng_đứng_riêng)
thụt_lề_còn_lại_trên_dòng = thụt_lề_ban_đầu - n
```

**Chính xác hơn:** Quy tắc ngôn ngữ mô tả phép biến đổi giống `String.stripIndent()`. Công thức trên là cách tính dễ dùng cho những ví dụ thông thường có dòng đóng riêng và chỉ dùng spaces. Đừng suy diễn rằng căn lề nhìn thấy trong editor là căn lề ký tự mà trình biên dịch đếm khi trộn tab và spaces.

### Minh họa: ba vị trí của dòng đóng

Giả sử dòng `A` có **16 spaces** ở đầu, dòng `B` có **18 spaces**. Chỉ thay đổi vị trí của `"""`:

| Vị trí dấu đóng | Độ thụt lề dòng đóng | Mức bị bỏ `n` | Lề còn lại của `A` và `B` |
| --- | ---: | ---: | --- |
| Cùng lề với `A` | 16 | 16 | `A`: 0; `B`: 2 spaces |
| Dịch dấu đóng sang trái 4 spaces | 12 | 12 | `A`: 4; `B`: 6 spaces |
| Dịch dấu đóng sang phải 4 spaces | 20 | 16 | `A`: 0; `B`: 2 spaces |

Nhận xét:

- Dấu đóng **lùi về bên trái** so với mọi dòng nội dung có thể làm **giảm số spaces bị bỏ**, tức là **giữ lại nhiều spaces hơn** trong giá trị chuỗi.
- Dấu đóng **lùi sang phải** quá lề của dòng nội dung ít thụt nhất **không** khiến Java xóa quá mức thụt nhỏ nhất của các dòng nội dung.
- Nếu đặt dấu đóng tại **cột đầu tiên** của mã nguồn (0 ký tự trắng trước dấu đóng), mức bỏ chung có thể bằng 0: các spaces đầu dòng của nội dung đều được giữ. Cách này hợp lệ nhưng thường làm bố cục mã nguồn kém gọn.

**Quan trọng:** Dòng đóng giống một **mốc điều chỉnh lề** khi đứng riêng, chứ không phải “bản sao của dòng mở”. Không cần và cũng không nên lấy cột của dấu mở để suy ra số spaces sẽ bị cắt.

## 3. Ví dụ Java chạy được: thấy chính xác spaces và newline

Tạo tệp `ClosingIndentDemo.java` với **toàn bộ** nội dung sau. Hãy giữ nguyên khoảng trắng ở đầu các dòng trong text block: nếu editor tự động định dạng lại, kết quả có thể khác.

```java
public class ClosingIndentDemo {
    private static String visible(String value) {
        return value.replace(" ", "·").replace("\n", "\\n");
    }

    public static void main(String[] args) {
        // Dòng đóng cùng lề với A: bỏ 16 spaces.
        String aligned = """
                A
                  B
                """;

        // Dòng đóng ở bên trái A 4 spaces: chỉ bỏ 12 spaces.
        String movedLeft = """
                A
                  B
            """;

        // Dòng đóng ở bên phải A 4 spaces: vẫn chỉ bỏ 16 spaces.
        String movedRight = """
                A
                  B
                    """;

        // Dấu đóng cùng dòng chữ B: không có newline ở cuối.
        String inlineClose = """
                A
                  B""";

        // Dòng đóng riêng và escape để không tạo newline cuối.
        String noFinalNewline = """
                    A
                      B\
                """;

        System.out.println("aligned=[" + visible(aligned) + "]");
        System.out.println("left=[" + visible(movedLeft) + "]");
        System.out.println("right=[" + visible(movedRight) + "]");
        System.out.println("inline=[" + visible(inlineClose) + "]");
        System.out.println("noFinal=[" + visible(noFinalNewline) + "]");
    }
}
```

Dùng **JDK 17 trở lên** (ví dụ 21 hoặc 25); mở terminal tại thư mục chứa file rồi chạy:

```bash
javac -encoding UTF-8 ClosingIndentDemo.java
java ClosingIndentDemo
```

**Stdout chính xác** khi giữ nguyên thụt lề của ví dụ:

```text
aligned=[A\n··B\n]
left=[····A\n······B\n]
right=[A\n··B\n]
inline=[A\n··B]
noFinal=[····A\n······B]
```

Ở đây, `·` đại diện **một dấu cách**, còn hai ký tự nhìn thấy `\n` đại diện **một ký tự xuống dòng thực tế**. Phương thức `visible` chỉ dùng để quan sát; text block gốc không chứa dấu chấm giữa hay hai ký tự gạch chéo ngược và `n`.

Từ ba kết quả đầu:

- `aligned`: `A` không thụt, `B` thụt 2 spaces, và có newline cuối.
- `movedLeft`: `A` giữ 4 spaces, `B` giữ 6 spaces; cấu trúc tương đối vẫn lệch 2 spaces.
- `movedRight`: tương đương `aligned` vì dòng `A` đặt giới hạn dưới 16 spaces cho mức bỏ.

Hai kết quả cuối minh họa một vấn đề **khác** với số spaces bị bỏ: **sự hiện diện của newline cuối**.

## 4. Khi dấu đóng đứng cùng dòng nội dung cuối

Text block có thể kết thúc bằng cách đặt `"""` ngay sau ký tự cuối:

```java
String colors = """
        red
        green
        blue""";
```

Giá trị tương đương với chuỗi thông thường:

```java
String expected = "red\ngreen\nblue";
```

Không có `\n` sau `blue` vì **không có xuống dòng nguồn** giữa `blue` và dấu đóng. Khi ấy dấu đóng **không còn là một dòng riêng** để điều chỉnh lề. Mức thụt lề tình cờ được suy ra từ các dòng nội dung; riêng việc cố “dịch dấu đóng sang trái” trên chính dòng `blue` không phải cách giữ spaces cho toàn chuỗi.

Ngược lại:

```java
String colors = """
        red
        green
        blue
        """;
```

Có thêm `\n` sau `blue`. Dấu đóng ở đây nằm trên dòng riêng và có thể xác lập một mốc thụt lề chung.

**Không nhầm lẫn hai lựa chọn:**

| Mục đích | Cách thực hiện |
| --- | --- |
| Điều chỉnh lượng thụt lề cần giữ | Cho `"""` đóng nằm trên **dòng riêng**, chọn vị trí lề thích hợp |
| Giữ newline cuối | Để newline thật ở trước dòng `"""` đóng |
| Bỏ newline cuối mà vẫn dùng dấu đóng để điều khiển lề | Đặt `\` ngay trước xuống dòng sau ký tự cuối, giữ dấu đóng trên dòng riêng |
| Bỏ newline cuối theo cách ngắn nhất | Đặt `"""` đóng ngay cuối dòng nội dung cuối; khi đó không còn mốc lề đóng riêng |

### Dùng `\` để đồng thời giữ spaces và bỏ newline cuối

Ví dụ độc lập sau có dấu đóng riêng và **không có newline cuối**:

```java
String value = """
            first
              second\
        """;
```

Dòng `first` có 12 spaces nguồn, `second` có 14 spaces, dấu đóng có 8 spaces. Lượng bỏ là 8, nên giá trị chuỗi tương đương:

```java
String expected = "    first\n      second";
```

Dấu `\` kết hợp với xuống dòng là escape **nối dòng** (line continuation), vì vậy kết quả không chứa `\n` cuối. Cách này giữ được vai trò xác định lề của dòng đóng và tránh phải sửa chuỗi sau khi tạo ra.

## 5. Ví dụ thực tế: thụt lề văn bản lồng nhau

Khi nhúng HTML, JSON, SQL hoặc một đoạn văn bản có cấu trúc, việc **giữ hay bỏ một phần spaces đầu dòng** có thể ảnh hưởng đến định dạng đầu ra, kiểm tra chuỗi và dữ liệu chuyển cho hệ thống khác.

Một text block HTML dễ đọc trong Java:

```java
String html = """
        <ul>
          <li>Java</li>
          <li>Text block</li>
        </ul>
        """;
```

Dòng đóng cùng lề với `<ul>` nên phần lề của mã nguồn được bỏ; các dòng `<li>` vẫn giữ **2 spaces** tương đối. Chuỗi thật là:

```text
<ul>
  <li>Java</li>
  <li>Text block</li>
</ul>
```

và có thêm newline sau `</ul>`.

Nếu bạn muốn cả khối HTML thực sự được thụt vào 4 spaces khi xuất ra tài liệu có cấu trúc lồng nhau, đặt nội dung sâu hơn dòng đóng 4 spaces:

```java
String html = """
            <ul>
              <li>Java</li>
              <li>Text block</li>
            </ul>
        """;
```

Lúc này `<ul>` và `</ul>` đều giữ **4 spaces** đầu dòng; `<li>` giữ **6 spaces**. Đây là cách trực tiếp điều khiển thụt lề mà không cần thêm khoảng trắng bằng nối chuỗi sau đó.

**Chú ý:** Nếu đưa chuỗi vào bộ phân tích cú pháp JSON, SQL hoặc một giao thức yêu cầu giá trị chính xác, bạn phải kiểm tra khoảng trắng đầu dòng và newline cuối theo yêu cầu của nơi nhận. Không giả định khoảng trắng chỉ để làm đẹp; với một số kiểu dữ liệu và giao thức, nó là dữ liệu thật.

## 6. Dòng trống, tab và dấu cách: các điểm dễ làm sai

### Dòng trống và trailing whitespace

Quy tắc text block được áp dụng trên **toàn bộ nội dung** (không chỉ hai dòng đầu), gồm việc xử lý dòng trống và loại bỏ khoảng trắng thừa **cuối dòng**. Vì vậy:

- Không lấy một dòng trắng gồm toàn spaces ở giữa nội dung làm “lề nhỏ nhất” theo trực giác; cách xác định incidental indentation của Java có quy tắc riêng cho blank lines.
- Dấu đóng nằm trên dòng riêng ảnh hưởng đến mức lề; bản thân dấu nháy kép `"""` không xuất hiện trong giá trị `String`.
- Nếu một ứng dụng cần spaces **ở cuối dòng**, không dựa vào những spaces được gõ sau ký tự cuối trong mã nguồn vì trình biên dịch có thể loại chúng. Dùng escape `\s` theo hướng dẫn Java nếu thực sự cần một space cuối dòng.

### Trộn tab và spaces

Java đếm **các ký tự whitespace**, chứ không đếm số cột mà tab trông như chiếm trong editor. Do đó, một ký tự tab có thể được hiển thị rộng bằng vài dấu cách nhưng không tương đương với cùng số lượng ký tự dấu cách trong phép tính thụt lề.

Đối với bài thực hành, hãy **chọn một kiểu thụt lề nhất quán**, tốt nhất toàn spaces trong cả nội dung text block và dòng đóng. Nếu ví dụ in ra khác dự tính, kiểm tra xem editor có thay thế spaces thành tabs hoặc tự căn lại dòng `"""` không.

### Kiểm tra cảnh báo của trình biên dịch

Trên JDK hiện hành, có thể bật cảnh báo liên quan đến text block:

```bash
javac -Xlint:text-blocks -encoding UTF-8 ClosingIndentDemo.java
```

Tùy nội dung, trình biên dịch có thể cảnh báo **thụt lề whitespace không nhất quán** hoặc **trailing whitespace sẽ bị xóa**. Không nên coi việc thiếu cảnh báo là bằng chứng rằng chuỗi tạo ra đúng mong muốn; hãy quan sát trực tiếp bằng phép in có đánh dấu spaces/newlines hoặc so sánh với chuỗi dự kiến.

## 7. Phân biệt ba phương tiện kiểm soát thụt lề

| Cơ chế | Hoạt động khi nào? | Dùng khi nào? |
| --- | --- | --- |
| Dịch vị trí dấu đóng `"""` (trên dòng riêng) | **Trong quá trình biên dịch** text block | Cần giữ hoặc bỏ một phần thụt lề bằng cách bố trí mã nguồn |
| `String.stripIndent()` | **Khi gọi phương thức trên chuỗi** | Cần chuẩn hóa thụt lề của dữ liệu `String` đã tồn tại; phải lưu ý nó có thể thay đổi khoảng trắng |
| `String.indent(int n)` | **Khi gọi phương thức trên chuỗi** | Cần thêm hoặc bớt thụt lề có chủ đích bằng một thao tác rõ ràng |

Ví dụ minh họa hành vi xử lý sau khi tạo chuỗi:

```java
String text = """
        A
          B""";

String shifted = text.indent(4);
```

`text` không có newline cuối, nhưng `indent(4)` trả về chuỗi đã biến đổi và xử lý các dòng theo quy tắc của `String.indent` (trong đó kết quả có thể có newline cuối). Vì vậy **không mặc định** thay dịch dấu đóng bằng `indent` rồi cho rằng mọi ký tự, nhất là newline cuối, sẽ giống nhau.

Trong phần lớn bài tập cần văn bản nhiều dòng, ưu tiên đặt dấu đóng trên **dòng riêng**, ngang lề của dòng nội dung ít thụt nhất. Khi yêu cầu đầu ra có khoảng trắng giữ nguyên ở đầu mỗi dòng, hãy dịch các dòng nội dung thêm so với dấu đóng hoặc xử lý rõ ràng bằng API thích hợp.

## 8. Các lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Chuỗi bị mất hết spaces đầu dòng dù mã nguồn trông rất thụt lề | Dòng đóng ngang hoặc sâu hơn dòng nội dung ít thụt nhất | Dịch dòng đóng sang trái (trên dòng riêng) nếu spaces đầu dòng là dữ liệu cần giữ |
| Chuỗi giữ nhiều spaces đầu dòng ngoài ý muốn | Dòng đóng nằm quá xa bên trái, khiến lượng bỏ nhỏ | Căn dấu đóng với lề của dòng nội dung ít thụt nhất nếu muốn loại thụt lề mã nguồn |
| Nội dung có `\n` ở cuối ngoài dự kiến | Dấu đóng ở dòng riêng sau dòng cuối có newline | Đặt dấu đóng cùng dòng cuối hoặc dùng `\` ngay trước newline cuối |
| Muốn giữ spaces bằng cách đổi vị trí dấu đóng nhưng không có tác dụng | Dấu đóng đang ở cuối **chính dòng nội dung**, không có dòng riêng làm mốc | Chuyển dấu đóng xuống dòng riêng; nếu muốn bỏ newline cuối, dùng escape nối dòng |
| Kết quả khác khi copy sang IDE khác | Tab/spaces bị chuyển đổi hoặc auto-format thay lề dấu đóng | Hiện whitespace trong editor, thống nhất spaces, so sánh chuỗi bằng `visible` |
| Tưởng spaces cuối dòng được giữ nguyên | Text block tự bỏ incidental trailing spaces | Dùng `\s` khi cần giữ space cuối dòng, rồi kiểm tra giá trị thật |
| Cắt bớt lề lần nữa bằng `stripIndent()` | Nhầm rằng Java chưa chuẩn hóa thụt lề text block | Chỉ gọi xử lý thêm khi muốn thay đổi giá trị đã được compiler tạo |

## 9. Bài tập tự kiểm tra (có lời giải)

**Bài 1.** Dòng `X` có 10 spaces, dòng `Y` có 13 spaces và dấu đóng ở dòng riêng có 6 spaces. Hỏi mức bỏ chung và lề còn lại?

- Mức bỏ: `min(10, 13, 6) = 6`.
- `X` còn **4 spaces**, `Y` còn **7 spaces**; tương quan 3 spaces vẫn giữ nguyên.

**Bài 2.** Với cùng hai dòng nội dung, nếu dịch dấu đóng sang 12 spaces?

- Mức bỏ: `min(10, 13, 12) = 10`.
- `X` còn **0 spaces**, `Y` còn **3 spaces**. Không thể “xóa quá 10 spaces” khỏi dòng `X` chỉ bằng cách đẩy dấu đóng sang phải.

**Bài 3.** Cần giữ 2 spaces đầu dòng và **không có newline cuối** cho cả khối. Nên đặt dấu đóng thế nào?

- Cho dấu đóng nằm **dòng riêng** và có lề ít hơn 2 spaces so với dòng nội dung ít thụt nhất; đặt escape `\` ngay cuối dòng nội dung cuối trước khi xuống dòng. Kiểm tra output bằng phương thức `visible` để tránh nhầm spaces và newline.

### Checklist

- [ ] Tôi biết `"""` đóng trên dòng riêng tham gia xác định mức lề bị bỏ.
- [ ] Tôi phân biệt **thụt lề mã nguồn bị bỏ** với **thụt lề có ý nghĩa được giữ**.
- [ ] Tôi biết dịch dấu đóng **sang trái** có thể giữ thêm spaces; dịch **sang phải** không vượt qua mức lề nhỏ nhất của nội dung.
- [ ] Tôi kiểm tra riêng **newline cuối** và dùng escape nối dòng khi cần.
- [ ] Tôi dùng spaces nhất quán, kiểm tra kết quả thực tế và chỉ dùng cú pháp text block đã chuẩn hóa.

## Tài liệu chính thức

1. [Oracle — Text Blocks, Java 25 Language Updates](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): cú pháp, dòng đóng, incidental whitespace, newline, escape và hướng dẫn định dạng.
2. [Oracle — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): các ví dụ sử dụng và khuyến nghị phong cách.
3. [Java Language Specification, Java SE 25, §3.10.6](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): thứ tự chuẩn hóa line terminator, strip indentation và diễn giải escape.
4. [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): đặc tả tính năng đã hoàn tất trong Java 15.

**Ghi nhớ:** Nếu `"""` đóng ở một dòng riêng, vị trí thụt lề của nó có thể quyết định **bao nhiêu spaces thực sự còn trong `String`**. Hãy kiểm tra cả khoảng trắng đầu dòng và newline cuối; không suy ra giá trị chuỗi chỉ từ vẻ ngoài của mã nguồn.