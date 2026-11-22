# Vai trò dòng chứa dấu đóng trong tính thụt lề của Java text block

> **Bối cảnh:** Java 14 → *Khoảng trắng văn bản* → **Vai trò dòng chứa dấu đóng trong tính thụt lề**. Text block (`"""`) xuất hiện ở Java 13–14 dưới dạng preview, nhưng **đã là tính năng chuẩn từ Java 15 (JEP 378)**. Nội dung dưới đây chỉ sử dụng cú pháp và quy tắc **vẫn áp dụng trong Java hiện đại**, với chương trình có thể biên dịch trên Java 17+ bằng `javac --release 17`, không cần bật preview.

## 1. Mục tiêu: vì sao vị trí `"""` ở cuối quan trọng?

Nhìn vào một text block:

~~~java
String message = """
        Hello
          Java
        """;
~~~

Đoạn mã này đặt trong một phương thức. Các dấu cách ở đầu dòng giúp mã Java dễ đọc, nhưng Java **không nhất thiết đưa tất cả chúng vào `String` kết quả**. Trình biên dịch tự loại bỏ phần thụt lề được xem là *incidental indentation* (khoảng trắng thụt lề phụ).

**Dòng chứa ba dấu ngoặc kép đóng `"""`, khi đặt trên dòng riêng, tham gia vào việc xác định ranh giới thụt lề cần loại bỏ.** Do đó, chỉ cần đưa dấu đóng sang trái hoặc sang phải, trong một số trường hợp ta sẽ làm thay đổi chính nội dung chuỗi, dù các dòng `Hello` và `Java` không đổi.

Sau bài này, bạn cần:

1. Phân biệt dấu mở và dấu đóng text block, cũng như dòng chứa dấu đóng đứng riêng với dấu đóng nằm cùng dòng nội dung.
2. Xác định số ký tự thụt lề bị loại bỏ từ **dòng nội dung ít thụt nhất** và **dòng dấu đóng khi phù hợp**.
3. Dự đoán khoảng trắng đầu dòng còn lại khi dời dấu đóng sang trái, ngang hoặc sang phải.
4. Phân biệt tác động của vị trí dấu đóng đến **thụt lề** với tác động đến **ký tự xuống dòng cuối**.
5. Viết text block để biểu diễn HTML, JSON, SQL hoặc văn bản có định dạng mà không vô tình làm đổi khoảng trắng quan trọng.

## 2. Dấu mở, nội dung và dấu đóng: ba vị trí khác nhau

Cấu trúc cơ bản:

~~~java
String text = """
        first line
          second line
        """;
~~~

- **Dấu mở** là `"""` phía sau dấu `=`. Nó phải được theo sau bởi một dấu kết thúc dòng (cho phép chỉ có whitespace hợp lệ trước dấu kết thúc dòng). Nội dung bắt đầu **sau** dấu kết thúc dòng ấy.
- **Nội dung** là các ký tự giữa dấu kết thúc dòng của dấu mở và dấu `"` đầu tiên trong cụm ba dấu ngoặc kép đóng. Nội dung có thể nhiều dòng.
- **Dấu đóng** là `"""` cuối; bản thân ba dấu ngoặc kép **không trở thành ký tự trong chuỗi**.
- Nếu dấu đóng đứng **trên dòng riêng**, khoảng trắng nằm trước nó được tính như một dòng cuối không chứa ký tự nội dung, ảnh hưởng đến phép xác định thụt lề chung.
- Nếu dấu đóng nằm **ngay sau nội dung ở dòng cuối**, không còn một dòng cuối chỉ có whitespace trước dấu đóng để làm mốc thụt lề.

Dấu mở có thể ở cột khác với dấu đóng. **Không lấy vị trí của dấu mở làm mốc tự động**. Thứ quyết định là những dòng trong **phần nội dung** và dòng cuối có whitespace trước dấu đóng theo thuật toán chuẩn.

Ví dụ cố ý **không hợp lệ** vì không có xuống dòng sau dấu mở:

~~~java
String invalid = """Hello"""; // Lỗi cú pháp text block
~~~

Không nên sửa lỗi trên bằng cách dời dấu đóng tùy ý; phải đặt dấu kết thúc dòng sau `"""` mở trước đã.

## 3. Thuật toán loại bỏ thụt lề phụ

JLS `3.10.6 mô tả thứ tự xử lý một text block:

1. **Chuẩn hóa dấu xuống dòng** trong nội dung: `CRLF` và `CR` thành `LF` (`\n`).
2. **Loại bỏ incidental whitespace**, tương đương về ý nghĩa với việc gọi `String.stripIndent()` trên nội dung đã chuẩn hóa.
3. **Diễn giải escape sequences** như `\n`, `\t`, `\s` hoặc dấu `\` ở cuối dòng theo quy tắc Java.

Ở bước 2, hình dung quy trình:

- Tìm số ký tự whitespace đứng đầu của **mỗi dòng có nội dung không trắng**.
- Nếu đoạn nội dung kết thúc bằng một **dòng cuối trắng** (điển hình là khoảng trắng trước dấu đóng `"""` trên dòng riêng), tính cả độ thụt của dòng cuối này.
- Lấy **giá trị nhỏ nhất** của các mức thụt liên quan; gọi là `m`. Các dòng trống trung gian không kéo `m` về 0 chỉ vì trống.
- Loại bớt tối đa `m` ký tự whitespace đầu mỗi dòng; khoảng thụt **còn lại** là một phần giá trị `String`. Whitespace ở cuối mỗi dòng được lược bỏ theo quy tắc chuẩn của text block.

Mô hình tính nhanh:

~~~text
m = min(
    độ thụt của các dòng nội dung không trắng,
    độ thụt của dòng cuối trước dấu đóng nếu dòng cuối đó trắng
)

khoảng thụt đầu dòng được giữ = khoảng thụt gốc - m
                                    (nếu dòng có đủ m ký tự)
~~~

**Lưu ý:** Đây là cách diễn giải đơn giản cho các ví dụ chỉ dùng dấu cách. Trong mã thực tế, tab và dấu cách là các ký tự whitespace riêng; trình biên dịch không suy ra số cột hiển thị của tab trong editor.

### Ví dụ tính bằng tay

Giả sử hai dòng có nội dung `A` và `B`, lần lượt thụt **16** và **18** dấu cách. Đặt dấu đóng trên dòng riêng:

| Độ thụt của dòng `"""` đóng | `m` nhỏ nhất | Số dấu cách còn lại trước `A` | Trước `B` |
| --- | --- | --- | --- |
| 16 dấu cách | 16 | 0 | 2 |
| 12 dấu cách | 12 | 4 | 6 |
| 18 dấu cách | 16 | 0 | 2 |
| 0 dấu cách | 0 | 16 | 18 |

Hai kết luận quan trọng:

- **Dời dấu đóng sang trái** so với dòng nội dung ít thụt nhất có thể **giữ lại thêm khoảng trắng** bên trái trong `String` kết quả.
- **Dời dấu đóng sang phải** quá dòng nội dung ít thụt nhất **không thể buộc Java loại thêm** khoảng trắng, vì `m` vẫn bị giới hạn bởi dòng nội dung ít thụt nhất.

Đừng suy ra rằng “dấu đóng thụt bao nhiêu thì compiler luôn xóa đúng bấy nhiêu”; quy tắc chính xác là lấy **mức nhỏ nhất** trong các dòng tham gia phép tính.

## 4. Ví dụ chạy được: di chuyển dấu đóng và quan sát từng ký tự

Chương trình sau so sánh năm trường hợp với **nội dung A/B giống nhau**. Hàm `visible` biến mỗi dấu cách thành `.` và mỗi `LF` thành hai ký tự `\` và `n`, giúp đọc được thụt lề và dấu xuống dòng ngay trên console.

**Lưu thành `TextBlockMarginDemo.java`**. Giữ nguyên vị trí dấu cách trong mã minh họa khi chép:

~~~java
public class TextBlockMarginDemo {
    static String visible(String s) {
        return s.replace(" ", ".").replace("\n", "\\n");
    }

    public static void main(String[] args) {
        // Nội dung A: 16 spaces; B: 18 spaces.
        // Dấu đóng thụt 16 spaces.
        String aligned = """
                A
                  B
                """;

        // Dấu đóng chỉ thụt 12 spaces.
        String left = """
                A
                  B
            """;

        // Dấu đóng thụt 18 spaces, nhiều hơn A.
        String right = """
                A
                  B
                  """;

        // Dấu đóng nằm cùng dòng với B.
        String sameLine = """
                A
                  B""";

        // Dấu đóng ở cột 0: giữ toàn bộ thụt lề đầu dòng.
        String zero = """
                A
                  B
""";

        System.out.println("aligned=" + visible(aligned));
        System.out.println("left=" + visible(left));
        System.out.println("right=" + visible(right));
        System.out.println("sameLine=" + visible(sameLine));
        System.out.println("zero=" + visible(zero));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockMarginDemo.java
java TextBlockMarginDemo
~~~

**Stdout chính xác** (dấu `.` trong kết quả bên dưới biểu diễn **một dấu cách** của chuỗi gốc):

~~~text
aligned=A\n..B\n
left=....A\n......B\n
right=A\n..B\n
sameLine=A\n..B
zero=................A\n..................B\n
~~~

### Giải thích từng trường hợp

**`aligned` – dấu đóng ngang mức với A.** Các dòng A và dấu đóng có 16 dấu cách, B có 18 ⇒ `m = 16`. Chuỗi là `"A\n  B\n"`. B còn hai dấu cách đầu dòng, và có `\n` cuối vì dấu đóng nằm sau một dòng kết thúc.

**`left` – dấu đóng dịch sang trái bốn cột.** Độ thụt của dòng dấu đóng là 12 ⇒ `m = 12`. A giữ lại bốn dấu cách, B giữ lại sáu dấu cách. Nội dung chuỗi **đã thay đổi**, dù hai dòng chữ A và B không dịch chuyển.

**`right` – dấu đóng dịch sang phải.** Dòng A chỉ có 16 dấu cách, ít hơn mức 18 của dấu đóng ⇒ `m` vẫn bằng 16. Kết quả **giống `aligned`**, không mất thêm khoảng trắng. Đây là trường hợp dễ bị hiểu sai khi quan sát bằng mắt.

**`sameLine` – dấu đóng nằm cùng dòng với B.** Không có dòng dấu đóng độc lập làm mốc. A/B tự quyết định `m = 16`, nên `A` không còn khoảng trắng đầu dòng và `B` còn hai dấu cách. Sau B **không có ký tự `\n`** vì dấu đóng tới ngay sau B.

**`zero` – dấu đóng đứng ở đầu dòng nguồn.** Dòng chứa dấu đóng có 0 dấu cách ⇒ `m = 0`. Tất cả 16/18 dấu cách trước A/B được giữ nguyên, đồng thời có `\n` cuối. Dùng cách này khi thực sự cần giữ toàn bộ thụt lề, nhưng phải hiểu rõ rằng việc dời dấu đóng chỉ để “cho đẹp” có thể làm đổi dữ liệu.

### Tại sao mẫu mã chạy thật quan trọng?

Với văn bản lập trình, một hoặc hai dấu cách có thể mang nghĩa. Nếu bạn nhúng YAML có cấu trúc, Python code, một đoạn tài liệu đã căn cột, hoặc chuỗi dùng để kiểm thử so khớp chính xác, khác biệt giữa `"A\n  B\n"` và `"    A\n      B\n"` là khác biệt **dữ liệu**, không phải chỉ khác biệt hiển thị.

Khi review thay đổi mã Java, việc di chuyển dòng `"""` đóng nên được xét như thay đổi có thể ảnh hưởng tới **giá trị chuỗi được biên dịch**.

## 5. Phân biệt thụt lề với newline cuối chuỗi

Cần tách **hai câu hỏi**:

1. Khoảng trắng đầu dòng nào được loại bỏ? → Xem **mốc thụt lề nhỏ nhất**, có thể do dòng dấu đóng quyết định.
2. Có `\n` ở cuối `String` hay không? → Xem **dấu đóng nằm sau một line terminator hay ngay sau nội dung cuối**, hoặc có escape nối dòng hay không.

Ví dụ minh họa kết quả:

~~~java
String withNewline = """
        red
        blue
        """;

String withoutNewline = """
        red
        blue""";

String escapedNewline = """
        red
        blue\
        """;
~~~

Đây là **đoạn đặt trong một phương thức**, không phải chương trình độc lập. Kết quả lần lượt là:

- `withNewline`: `"red\nblue\n"`.
- `withoutNewline`: `"red\nblue"`; dòng đóng cùng dòng `blue`, không có `LF` cuối.
- `escapedNewline`: `"red\nblue"`; dấu `\` ngay trước dấu xuống dòng **nối tiếp dòng**, làm mất newline cuối nhưng vẫn giữ dòng dấu đóng riêng làm mốc thụt.

**`\` nối dòng** hữu ích khi muốn kiểm soát khoảng trắng bằng dòng đóng riêng mà **không muốn `\n` cuối chuỗi**. Nó được xử lý trong bước escape sau khi Java đã tính và loại incidental indentation.

### Chương trình chạy để xác minh newline

Lưu thành **`TextBlockEndingsDemo.java`**:

~~~java
public class TextBlockEndingsDemo {
    static String visible(String text) {
        return text.replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String normal = """
                red
                blue
                """;

        String sameLine = """
                red
                blue""";

        String escaped = """
                red
                blue\
                """;

        System.out.println(visible(normal));
        System.out.println(visible(sameLine));
        System.out.println(visible(escaped));
        System.out.println(normal.endsWith("\n"));
        System.out.println(sameLine.endsWith("\n"));
        System.out.println(escaped.equals(sameLine));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 TextBlockEndingsDemo.java
java TextBlockEndingsDemo
~~~

~~~text
red\nblue\n
red\nblue
red\nblue
true
false
true
~~~

Lưu ý: dấu `\` cuối dòng nguồn trong `blue\` là **cú pháp escape Java**, không phải ký tự backslash cần được giữ trong `String` kết quả. Kết quả `escaped.equals(sameLine)` là `true` ở đây vì hai chuỗi cùng chứa `red`, một newline và `blue`.

### Tác động của trường hợp dấu đóng cùng dòng

Nếu đóng cùng dòng ký tự cuối, bạn **không còn dùng được vị trí dấu đóng trên một dòng trống để bảo toàn thêm thụt lề**. Ví dụ:

~~~java
String value = """
        red
        blue""";
~~~

Hai dòng `red` và `blue` tự xác lập lề nhỏ nhất; đoạn trên trả `"red\nblue"`. Khi cần vừa giữ một số dấu cách đầu dòng vừa không có newline cuối, có thể sử dụng dạng dòng đóng riêng và escape nối dòng:

~~~java
String value = """
            red
            blue\
        """;
~~~

Đây là **một đoạn minh họa độc lập khác**, trong đó hai dòng nội dung thụt 12 dấu cách, dòng dấu đóng thụt 8 ⇒ sau khi lược bớt 8, mỗi dòng giữ lại **4 dấu cách**. Chuỗi tương đương `"    red\n    blue"`, **không có newline cuối**.

## 6. Dòng trắng, whitespace cuối dòng và thứ tự xử lý

### 6.1. Một dòng trắng ở giữa không phải mốc lề tối thiểu

~~~java
String poem = """
        first

          second
        """;
~~~

Dòng trống giữa `first` và `second` không làm mức thụt tối thiểu thành 0. Với ví dụ này, compiler xóa 8 dấu cách từ dòng có nội dung và dòng đóng; kết quả `"first\n\n  second\n"`.

Nếu bạn chèn khoảng trắng vô hình ở dòng trống giữa các dòng, không nên dựa vào chúng làm nội dung có ý nghĩa. Theo quy tắc text block, trailing whitespace ở mỗi dòng bị loại bỏ trong quá trình xử lý. Khi cần kiểm tra dữ liệu chính xác, hãy so sánh chuỗi thực tế, không chỉ nhìn editor.

### 6.2. Khoảng trắng cuối dòng không được giữ nguyên chỉ vì đã gõ vào nguồn

Với text block, dấu cách và tab vô hình ở **cuối dòng nguồn** thường bị loại bỏ khi compiler xử lý incidental whitespace. Khi bạn thật sự cần bảo toàn một dấu cách ở cuối dòng trong chuỗi, dùng escape `\s`:

~~~java
String text = """
        code\s
        next
        """;
~~~

Sau khi xử lý, kết quả là `"code \nnext\n"` (có **một dấu cách** giữa `code` và newline). Bởi `\s` chỉ được dịch thành ký tự space **sau** bước loại incidental indentation, ký tự cần giữ không bị xem là whitespace cuối dòng ở thời điểm lược bỏ.

Không cần chèn `\s` cho mọi khoảng trắng: nó chỉ phù hợp khi yêu cầu nội dung thực sự có dấu cách cuối dòng. Với JSON/YAML/SQL, hãy ưu tiên tạo đầu ra dễ hiểu và kiểm tra chính xác dạng dữ liệu cần dùng.

### 6.3. Tab và dấu cách không có cùng chiều rộng hiển thị

Trình biên dịch tính indentation theo **số ký tự whitespace**, không theo số cột mà tab chiếm trong editor. Một tab tính như một ký tự, không đương nhiên bằng 4 hay 8 dấu cách.

Khi một số dòng dùng tab và số dòng khác dùng space, lề được loại bỏ có thể không tương xứng với những gì bạn nhìn thấy. Vì vậy:

- Dùng **một kiểu thụt lề nhất quán** cho nội dung text block và dòng dấu đóng.
- Tránh “căn thẳng hàng bằng mắt” giữa dòng dùng tab và dòng dùng space.
- Có thể bật cảnh báo compiler liên quan bằng `javac -Xlint:text-blocks` để nhận cảnh báo về những tình huống whitespace đáng ngờ. Đây là công cụ hỗ trợ, không thay cho phép so sánh chuỗi trong kiểm thử.

## 7. Ví dụ ứng dụng: giữ thụt lề có chủ đích

Giả sử cần một đoạn cấu hình có khoảng thụt tương đối:

~~~java
String yaml = """
        service:
          enabled: true
          replicas: 2
        """;
~~~

Dòng dấu đóng ngang với `service:`; `m` bằng mức thụt của `service:`. Kết quả:

~~~yaml
service:
  enabled: true
  replicas: 2
~~~

Hai dấu cách trước `enabled` và `replicas` là **thụt lề thiết yếu** (*essential indentation*), vẫn tồn tại sau khi Java bỏ phần incidental indent chung.

Nếu API yêu cầu cả khối YAML được **thụt thêm bốn dấu cách** để nằm trong một văn bản lớn hơn, bạn có thể **giữ dòng dấu đóng ở mức nhỏ hơn nội dung** thay vì chèn khoảng trắng ẩn vào từng chuỗi:

~~~java
String yaml = """
            service:
              enabled: true
              replicas: 2
        """;
~~~

Nội dung các dòng thụt hơn dòng dấu đóng 4 ký tự, nên kết quả giữ **4 dấu cách trước `service:`** và **6 dấu cách trước các khóa con**:

~~~text
    service:
      enabled: true
      replicas: 2
~~~

Không có mâu thuẫn: Java loại bỏ một phần indentation chung, còn khoảng thụt thêm mà người viết tạo ra có chủ đích được giữ.

**Cảnh báo về giao thức:** Khi văn bản có schema (JSON, YAML, SQL, HTML...), hãy dùng parser/serializer hoặc API cấu hình đúng mục đích nếu cần bảo đảm dữ liệu hợp lệ, tránh ghép dữ liệu không tin cậy trực tiếp vào SQL. Text block là **cách biểu diễn một `String`** trong mã nguồn, không tự kiểm tra cú pháp YAML/JSON và không tự escape giá trị đầu vào.

## 8. Những lỗi hiểu sai thường gặp

| Nhận định sai / thao tác | Tác động thực tế | Cách hiểu đúng |
| --- | --- | --- |
| “Chỉ dòng nội dung mới quyết định indentation.” | Dòng chứa dấu đóng **trên dòng riêng** có thể là lề nhỏ nhất. | Xét cả dòng cuối whitespace trước `"""` khi xác định `m`. |
| “Dời `"""` sang phải sẽ luôn xóa thêm dấu cách.” | Nếu dòng nội dung ít thụt hơn, `m` không đổi. | Mức bị xóa là **min** của các dòng tham gia. |
| “Dời `"""` sang trái chỉ làm mã xấu đi.” | Có thể giữ thêm dấu cách trong `String`. | Kiểm tra giá trị chuỗi khi reformat code. |
| “Dấu mở `"""` xác định lề chuẩn.” | Vị trí dấu mở không trực tiếp quyết định `m`. | Lề được xác định từ phần nội dung và dòng dấu đóng liên quan. |
| “`"""` đứng cùng dòng cuối có vai trò lề như khi đứng riêng.” | Không có dòng cuối riêng làm mốc; thường đồng thời mất newline cuối. | Phân biệt trường hợp cùng dòng và riêng dòng. |
| “Dấu đóng ở cột 0 luôn tạo chuỗi không có khoảng trắng.” | Thông thường `m = 0` và giữ **toàn bộ** khoảng trắng đầu dòng. | Chỉ chọn cột 0 khi cần giữ indentation gốc. |
| “Một dòng trắng rỗng ở giữa làm `m = 0`.” | Dòng trống giữa không được dùng để hạ mức nhỏ nhất theo cách đó. | Tính từ các dòng có nội dung và dòng cuối phù hợp. |
| “`\s` bị strip giống dấu cách cuối dòng nguồn.” | Escape được dịch sau khi strip indentation. | Dùng `\s` khi thật sự cần khoảng trắng cuối dòng. |
| “Tab chiếm 4/8 khoảng trắng trong thuật toán.” | Compiler đếm ký tự whitespace. | Giữ quy ước thụt lề nhất quán. |
| “Text block tự động không có newline cuối.” | Đóng trên dòng riêng sau nội dung thường **có** `\n` cuối. | Đặt dấu đóng cùng dòng cuối hoặc dùng escape nối dòng. |
| “Chạy `stripIndent()` thêm lần nữa luôn vô hại.” | Đó là một phép biến đổi mới trên `String` đã tạo, có thể thay đổi kết quả. | Chỉ gọi thêm nếu ứng dụng thực sự muốn xử lý indentation. |

## 9. Cách kiểm thử để tránh sai khác vô hình

Trong bài kiểm tra hoặc thư viện cần so khớp chính xác, nên test **giá trị `String` cuối cùng**:

~~~java
String actual = """
        alpha
          beta
        """;
String expected = "alpha\n  beta\n";
System.out.println(actual.equals(expected)); // true
~~~

Đây là **đoạn minh họa đặt trong phương thức**. Kiểm tra bằng `String.equals` đảm bảo cả các dấu cách và newline đều đúng. Đối với text block có cấu trúc, có thể thêm kiểm tra độ dài, số dòng, hoặc so sánh với tài liệu đầu ra đã được chuẩn hóa.

Nếu muốn thấy khoảng trắng khi debug, dùng:

~~~java
static String visible(String value) {
    return value.replace(" ", "·").replace("\n", "\\n");
}
~~~

Phương thức trên chỉ là **công cụ quan sát**. Dấu `·` là ký tự minh họa, không phải khoảng trắng thực. Nếu log có dữ liệu nhạy cảm, tránh in toàn bộ nội dung chỉ để xem whitespace.

### Checklist khi review

- [ ] Text block sử dụng cú pháp Java 15+ ổn định; dự án dùng JDK 17+ theo ví dụ.
- [ ] Dòng dấu đóng đứng riêng hay cùng dòng nội dung cuối?
- [ ] Dòng chứa nội dung nào có ít leading whitespace nhất?
- [ ] Độ thụt của dòng dấu đóng có nhỏ hơn mức đó không?
- [ ] Phần thụt **cần giữ** có được giữ sau khi tính `m`?
- [ ] Chuỗi có hay không có `\n` cuối đúng theo hợp đồng?
- [ ] Có cần escape `\s` hay `\` nối dòng không?
- [ ] Dòng trắng, trailing whitespace, tabs/spaces có nhất quán?
- [ ] Khi một formatter dời `"""`, kiểm thử có phát hiện `String` thay đổi không?
- [ ] Với cấu hình, HTML, JSON hoặc SQL, các bước parse/validate và xử lý dữ liệu đầu vào có đúng không?

## 10. Bài tập tự luyện

1. Với A thụt 10 dấu cách, B thụt 13 và dấu đóng trên dòng riêng thụt 8, hãy tính `m` và số dấu cách đầu dòng còn lại. Thử dời dấu đóng tới cột 10 và cột 14.
2. Tạo text block `"one\ntwo\n"` bằng dấu đóng riêng. Sau đó tạo `"one\ntwo"` bằng **hai cách**: dấu đóng cùng dòng cuối và escape `\` cuối dòng, rồi dùng `equals` để kiểm chứng.
3. Sao chép `TextBlockMarginDemo` và dời riêng dấu đóng của `left` thêm hai dấu cách sang phải. Dự đoán chuỗi mới trước khi chạy.
4. Viết hai text block có cùng dòng nội dung nhưng một dấu đóng ở cột 0, một dấu đóng cùng mức với dòng nội dung. In bằng `visible` để so sánh.
5. Chèn dòng trắng giữa A và B; giải thích vì sao nó không nhất thiết làm `m = 0`. Thêm dấu cách vào cuối một dòng rồi quan sát chúng có được giữ hay không.
6. Tạo một đoạn YAML có khối con thụt hai dấu cách. Dùng vị trí dấu đóng để giữ thêm bốn dấu cách cho toàn khối. So sánh với chuỗi mong đợi.
7. Thử trộn tab với space trong một text block, bật `-Xlint:text-blocks` và quan sát cảnh báo; sửa lại cho đồng nhất.
8. Giải thích tại sao một thay đổi chỉ dời vị trí `"""` có thể làm hỏng snapshot test, dù mắt thường thấy cùng văn bản.

## 11. Tài liệu chính thức

- [Java Language Specification SE 25 – `3.10.6, Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): định nghĩa dấu mở/dấu đóng, biến đổi line terminators, incidental whitespace và escape sequences.
- [Oracle – Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): ví dụ vị trí dấu đóng, cách giữ khoảng trắng và newline cuối.
- [JEP 378 – Text Blocks](https://openjdk.org/jeps/378): ngữ nghĩa tính năng text blocks chính thức từ Java 15.
- [Java SE 17 String API – `stripIndent()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#stripIndent()): quy tắc loại bỏ thụt lề phụ ở mức API.

**Ghi nhớ:** Dòng chứa dấu đóng `"""` không chỉ đánh dấu kết thúc. **Khi ở trên dòng riêng**, số khoảng trắng trước dấu đóng có thể trở thành lề nhỏ nhất, quyết định Java sẽ cắt bao nhiêu dấu cách đầu dòng của toàn bộ text block. Đặt dấu đóng sang trái thường **giữ lại nhiều khoảng trắng hơn**, sang phải quá lề nhỏ nhất thường không có tác dụng; đặt cùng dòng với nội dung cuối cũng ảnh hưởng đến newline cuối. Hiểu quy tắc này giúp viết và bảo trì chuỗi đa dòng chính xác trong Java hiện đại.