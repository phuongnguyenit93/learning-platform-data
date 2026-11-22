# Ảnh hưởng khi công cụ định dạng thay đổi vị trí dấu đóng của Java text block

## Mục tiêu

Một công cụ định dạng mã Java có thể tự động căn lề, dịch cả khối lệnh, dời các dòng nội dung, hoặc thay đổi vị trí **ba dấu nháy kép đóng** (`"""`) của một **text block**. Khác với việc căn lề ở nhiều đoạn mã thông thường, những thay đổi này **có thể làm thay đổi chính giá trị `String` sau khi biên dịch**, dù các chữ trong nội dung nhìn vẫn giống nhau.

Bài học này giải thích **vì sao vị trí dấu đóng là một phần của ngữ nghĩa**, khi nào định dạng chỉ thay đổi hình thức, khi nào thay đổi khoảng trắng hoặc ký tự xuống dòng và cách kiểm chứng kết quả trước khi chấp nhận một bản format tự động.

Sau khi học, bạn có thể:

- Giải thích mối quan hệ giữa **closing delimiter** `"""` và cơ chế loại bỏ **incidental indentation** của Java.
- Dự đoán tác động của việc dịch dấu đóng **sang trái, sang phải, hoặc lên dòng cuối của nội dung**.
- Phân biệt tác động của formatter khi **dịch toàn bộ text block cùng nhau** với khi **chỉ dịch dấu đóng hoặc các dòng nội dung**.
- Phát hiện chênh lệch về dấu cách đầu dòng, xuống dòng cuối, dấu cách cuối dòng và chuỗi byte/ký tự mà ứng dụng thật sử dụng.
- Viết một phép kiểm thử hồi quy cho `String` nhạy cảm với khoảng trắng, kết hợp cảnh báo của `javac` với kiểm tra giá trị thực.
- Chọn cách định dạng an toàn cho JSON, SQL, HTML, template và snapshot mà không phụ thuộc giả định “formatter chỉ sửa vẻ ngoài”.

**Phiên bản áp dụng:** Text blocks được chuẩn hóa trong **Java 15** theo [JEP 378](https://openjdk.org/jeps/378). Chúng từng được thử nghiệm trong lộ trình Java 14, nhưng toàn bộ cú pháp và hành vi ở đây là **quy tắc chuẩn còn áp dụng cho Java 17+**, không sử dụng `--enable-preview`, cú pháp preview đã lỗi thời hoặc mẹo sửa bytecode.

## 1. Vì sao có thể đổi giá trị khi chỉ dịch `"""`?

Hãy xét:

~~~java
String text = """
    ALPHA
      BETA
    """;
~~~

Đây là **mã minh họa**. Dấu `"""` trên dòng cuối không phải một ký hiệu trang trí nằm ngoài quá trình xử lý; trong text block, **vị trí của closing delimiter** có thể ảnh hưởng đến lượng khoảng trắng đầu dòng mà compiler xem là **phụ trợ (incidental)**.

Sau khi xử lý khoảng trắng theo quy tắc text block, ví dụ trên tương đương:

~~~java
String text = "ALPHA\n  BETA\n";
~~~

Tức là:

- Dòng thứ nhất không có dấu cách phía trước `ALPHA`.
- Dòng thứ hai có **hai dấu cách có ý nghĩa** trước `BETA`.
- Sau `BETA` vẫn có một dấu xuống dòng cuối `\n` vì closing delimiter nằm trên **dòng riêng**.

Nếu một formatter di chuyển chỉ dòng `"""` sang trái mà giữ hai dòng nội dung đứng yên, số dấu cách compiler loại bỏ sẽ thay đổi. Đó là **thay đổi ngữ nghĩa của literal**, không chỉ thay đổi style.

## 2. Các bước xử lý nội dung text block

Một text block được viết bằng opening delimiter `"""`, kết thúc dòng bắt buộc, nội dung, rồi closing delimiter `"""`:

~~~java
String html = """
    <p>Hello</p>
    """;
~~~

Các bước quan trọng theo đặc tả Java:

1. **Chuẩn hóa line terminators** trong nội dung: những dạng xuống dòng nguồn như CR và CRLF được quy về LF (`\n`).
2. **Loại bỏ incidental whitespace**: tính lượng thụt lề phụ, xóa một phần leading whitespace của mỗi dòng và loại các trailing whitespace phụ ở cuối dòng.
3. **Diễn giải escape sequences**: chẳng hạn `\s` để chủ ý giữ dấu cách, `\\` để tạo dấu gạch chéo ngược, hoặc `\` ở cuối dòng để nối các dòng.

Thứ tự này có ý nghĩa: formatter thay đổi thụt lề **trước khi compiler tính incidental whitespace**, còn các escape được diễn giải sau bước làm sạch khoảng trắng.

### Cách xác định lượng khoảng trắng đầu dòng bị loại

Đối với các dòng nội dung không rỗng, Java xem xét số ký tự trắng đứng trước ký tự nội dung đầu tiên. Nếu closing delimiter nằm trên **một dòng riêng**, lượng thụt lề của dòng đóng cũng góp phần xác định lề nhỏ nhất. Về mặt thực hành, mức lề chung được lấy từ **mức thụt lề nhỏ nhất** trong các dòng cần xét; compiler loại bớt cùng mức đó ở đầu các dòng.

Cách nghĩ đơn giản:

~~~text
content line 1: 8 spaces + ALPHA
content line 2: 10 spaces + BETA
closing line:  8 spaces + """
minimum = 8
result: ALPHA\n··BETA\n
~~~

Ở sơ đồ này, `·` đại diện cho **một dấu cách thực**, còn `\n` biểu diễn LF nhìn thấy, không phải chữ `n`.

Nếu formatter thay vị trí closing delimiter từ **8 dấu cách** thành **4 dấu cách** mà **không đổi các dòng nội dung**, lề nhỏ nhất thành `4`. Compiler chỉ bỏ bốn dấu cách đầu, do đó chuỗi sẽ **giữ lại thêm bốn dấu cách ở mỗi dòng**.

**Chi tiết quan trọng:** Di chuyển closing delimiter **sang phải** không phải lúc nào cũng thay đổi nội dung. Nếu nó đã thụt sâu hơn dòng nội dung có lề nhỏ nhất, chính dòng nội dung đó quyết định số whitespace bị bỏ. Lúc này dịch dấu đóng sang phải thêm vẫn có thể cho ra cùng một `String`.

## 3. Các tình huống formatter thường gây tác động

### 3.1. Dịch cả nội dung và dấu đóng cùng nhau

~~~java
// Hình thức ban đầu.
String a = """
    ALPHA
      BETA
    """;

// Công cụ formatter dịch toàn bộ khối sang phải bốn dấu cách.
String b = """
        ALPHA
          BETA
        """;
~~~

Các đoạn trên là **mã minh họa** trong một phương thức/lớp.

Vì **mọi dòng nội dung và dòng dấu đóng đều dịch cùng lượng**, lề chung cũng tăng đúng lượng đó. Compiler vẫn loại hết phần whitespace phụ, nên kết quả của `a` và `b` đều là:

~~~text
ALPHA\n··BETA\n
~~~

**Không được kết luận từ hình thức alone** rằng mọi lần auto-indent đều vô hại. Chính việc **dịch đồng đều các phần liên quan** khiến trường hợp này giữ nguyên ngữ nghĩa. Nếu formatter chỉ dịch một phần, kết quả có thể khác.

### 3.2. Chỉ dịch dấu đóng sang trái: giữ thêm dấu cách

~~~java
String closingLeft = """
        ALPHA
          BETA
    """;
~~~

Dấu đóng lúc này chỉ thụt lề **4 dấu cách**, còn nội dung có **8** và **10** dấu cách. Compiler chỉ bỏ bốn dấu cách, nên giá trị thực là:

~~~text
····ALPHA\n······BETA\n
~~~

Nội dung giữ lại **bốn dấu cách trước `ALPHA`** và **sáu dấu cách trước `BETA`**, thay vì `0` và `2` như trường hợp ban đầu. Nếu một snapshot, email template hay chuỗi để ký số phụ thuộc chính xác khoảng trắng, đây là một thay đổi hành vi.

### 3.3. Chỉ dịch dấu đóng sang phải: có thể không đổi giá trị

~~~java
String closingRight = """
        ALPHA
          BETA
            """;
~~~

Dấu đóng thụt lề sâu hơn cả dòng `ALPHA`. Dòng nội dung có lề nhỏ nhất vẫn quyết định số ký tự bị bỏ (8 dấu cách), nên kết quả thực vẫn là:

~~~text
ALPHA\n··BETA\n
~~~

**Hệ quả:** Không phải cứ thay đổi số dấu cách trước `"""` là giá trị chuỗi chắc chắn khác. Quy tắc đúng là xem **lề nhỏ nhất của toàn text block**, không chỉ đếm vị trí dấu đóng.

Ở ví dụ cố ý thụt dòng đóng rất sâu, `javac -Xlint:text-blocks` có thể báo cảnh báo dạng **“trailing white space will be removed”**. Đây là cảnh báo hữu ích để xem lại định dạng, nhưng bản thân cảnh báo không có nghĩa kết quả nhất thiết khác với bản cũ.

### 3.4. Chỉ dịch các dòng nội dung sang phải: giữ lại thêm lề

~~~java
String contentMoved = """
            ALPHA
              BETA
        """;
~~~

Dòng đóng giữ mức 8 dấu cách, còn nội dung lần lượt có 12 và 14 dấu cách. Kết quả tương tự tình huống dấu đóng dịch trái bốn ký tự: nội dung giữ thêm bốn dấu cách trước mỗi dòng so với bản gốc.

Nếu nội dung là ví dụ Markdown trong một string, khoảng trắng này có thể khiến đoạn văn thành code block; nếu là YAML, việc đổi indent có thể đổi cấu trúc; nếu chỉ là JSON, parser thường bỏ qua whitespace ngoài string nhưng **raw payload vẫn khác**. Cần đánh giá đúng format và contract, không dùng một kết luận cho mọi loại dữ liệu.

### 3.5. Dời dấu đóng lên cùng dòng nội dung cuối: mất LF kết thúc

~~~java
String closingOnOwnLine = """
    ALPHA
      BETA
    """;

String closingInline = """
    ALPHA
      BETA""";
~~~

Hai giá trị tương ứng:

~~~text
closingOnOwnLine = "ALPHA\n  BETA\n"
closingInline     = "ALPHA\n  BETA"
~~~

Dời `"""` từ dòng riêng lên **ngay sau `BETA`** làm mất **ký tự LF sau `BETA`**, vì content kết thúc ngay trước dấu nháy kép đầu tiên của closing delimiter. Đây là khác biệt **độc lập với vấn đề thụt lề**.

Khi closing delimiter nằm cuối dòng nội dung, dòng đóng **không còn là một dòng riêng** để tham gia tính mức indent. Compiler sử dụng các dòng nội dung theo quy tắc text block. Vì thế việc dời dấu đóng giữa hai vị trí có thể thay đổi **cả newline cuối và lượng leading whitespace** tùy bố cục cụ thể.

**Chú ý:** Không phải công cụ formatter nào cũng tự động dời dấu đóng lên cuối dòng nội dung. Đừng giả định công cụ của dự án sẽ làm như vậy; hãy kiểm tra bản diff do công cụ thực sự tạo ra.

## 4. Ví dụ chạy đầy đủ: so sánh kết quả sau sáu kiểu định dạng

Tạo tệp **`TextBlockClosingFormatterDemo.java`**:

~~~java
public final class TextBlockClosingFormatterDemo {
    static String show(String value) {
        return "[" + value.replace(" ", "·")
                .replace("\n", "\\n") + "] len=" + value.length();
    }

    public static void main(String[] args) {
        String baseline = """
            ALPHA
              BETA
            """;

        String wholeBlockShifted = """
                ALPHA
                  BETA
                """;

        String closingLeft = """
            ALPHA
              BETA
        """;

        String closingRight = """
            ALPHA
              BETA
                """;

        String onlyContentShifted = """
                ALPHA
                  BETA
            """;

        String closingInline = """
            ALPHA
              BETA""";

        String continuation = """
            ALPHA
              BETA\
            """;

        System.out.println("baseline=" + show(baseline));
        System.out.println("wholeBlockShifted=" + show(wholeBlockShifted));
        System.out.println("closingLeft=" + show(closingLeft));
        System.out.println("closingRight=" + show(closingRight));
        System.out.println("onlyContentShifted=" + show(onlyContentShifted));
        System.out.println("closingInline=" + show(closingInline));
        System.out.println("continuation=" + show(continuation));
        System.out.println("jointShiftSame="
                + baseline.equals(wholeBlockShifted));
        System.out.println("closingRightSame="
                + baseline.equals(closingRight));
        System.out.println("closingLeftSame="
                + baseline.equals(closingLeft));
        System.out.println("inlineEqualsContinuation="
                + closingInline.equals(continuation));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockClosingFormatterDemo.java
java TextBlockClosingFormatterDemo
~~~

**Đầu ra chính xác đã kiểm chứng bằng biên dịch và thực thi:**

~~~text
baseline=[ALPHA\n··BETA\n] len=13
wholeBlockShifted=[ALPHA\n··BETA\n] len=13
closingLeft=[····ALPHA\n······BETA\n] len=21
closingRight=[ALPHA\n··BETA\n] len=13
onlyContentShifted=[····ALPHA\n······BETA\n] len=21
closingInline=[ALPHA\n··BETA] len=12
continuation=[ALPHA\n··BETA] len=12
jointShiftSame=true
closingRightSame=true
closingLeftSame=false
inlineEqualsContinuation=true
~~~

**Cách đọc output:**

- `show` thay từng dấu cách thật bằng ký hiệu `·` và từng LF thật bằng **hai ký tự nhìn thấy** `\` và `n`. Nó không tự thêm newline vào nội dung so sánh. Phần `len` là `String.length()` tính theo UTF-16 code units.
- `baseline` có `ALPHA` (5 ký tự), LF (1), hai space (2), `BETA` (4), LF cuối (1) → tổng **13**.
- `closingLeft` và `onlyContentShifted` giữ thêm **bốn space mỗi dòng**, tăng `8` ký tự → `21`.
- `closingRight` có cùng nội dung và độ dài với baseline vì mức indent nhỏ nhất vẫn do dòng `ALPHA` quyết định.
- `closingInline` không có LF cuối nên dài **12**.
- `continuation` dùng **`\` ở cuối dòng `BETA`** để loại LF sau dòng đó, cho giá trị giống `closingInline` trong ví dụ này dù closing delimiter vẫn nằm trên một dòng riêng.
- Phần `equals` giúp xác nhận **giá trị thực**, không chỉ so sánh số ký tự (hai chuỗi có cùng độ dài vẫn có thể khác nội dung).

**Ghi chú về compiler lint:** Nếu biên dịch ví dụ bằng:

~~~bash
javac --release 17 -encoding UTF-8 -Xlint:text-blocks TextBlockClosingFormatterDemo.java
~~~

compiler có thể cảnh báo về khoảng trắng cuối bị loại ở trường hợp `closingRight`. Cảnh báo không làm thay đổi stdout của chương trình. Nó **không** chứng minh formatter đã bảo toàn nội dung, và cũng không bắt được mọi biến đổi có ý nghĩa; phải kết hợp với so sánh `String` thực tế.

## 5. Những cách kiểm chứng an toàn khi formatter chạy tự động

### 5.1. So sánh chuỗi trước–sau, không chỉ so sánh source

Một thay đổi định dạng được chấp nhận khi **giá trị chuỗi sau biên dịch vẫn đúng hợp đồng**, hoặc khi sự khác biệt được review như một thay đổi nội dung có chủ đích.

Với baseline ở phần 4, có thể viết một kiểm tra **không cần thư viện bên ngoài**:

~~~java
// Mã minh họa đặt sau khi baseline được khai báo trong một phương thức.
String expected = "ALPHA\n  BETA\n";
if (!expected.equals(baseline)) {
    throw new AssertionError("Text block value changed");
}
~~~

Khi áp dụng cho ứng dụng thật:

1. Lưu `expected` bằng **chuỗi ký tự chuẩn** rõ ràng (hoặc một fixture độc lập) thay vì tự tạo từ text block đang bị formatter sửa.
2. Biên dịch/chạy test trước khi format.
3. Chạy đúng formatter và cấu hình mà IDE/CI đang dùng.
4. Biên dịch/chạy test lại; so sánh bằng `String.equals` hoặc byte-array khi contract theo byte.
5. Nếu fail, xem lại lề của closing delimiter, lề các dòng nội dung và newline cuối trước khi chấp nhận PR.

**Không dùng `trim()`, `strip()` hay `stripIndent()` trên hai phía chỉ để làm test pass** nếu điều cần bảo vệ chính là whitespace. Các phương thức đó có thể xóa khác biệt đáng lẽ cần phát hiện.

### 5.2. Hiển thị ký tự không nhìn thấy

Khi review lỗi liên quan text block, log theo cách thể hiện rõ:

- LF bằng `\n` (hai ký tự nhìn thấy).
- Space bằng dấu `·`.
- Tab bằng `\t` (nếu văn bản có tab).
- `String.length()` hoặc độ dài byte khi protocol yêu cầu chính xác.

Ví dụ helper đầy đủ hơn, **chỉ là mã minh họa**, không phải đoạn chạy độc lập:

~~~java
static String visible(String s) {
    return s.replace(" ", "·")
            .replace("\t", "\\t")
            .replace("\n", "\\n");
}
~~~

Với văn bản có ký tự Unicode ngoài BMP, `String.length()` đếm UTF-16 code units chứ không phải số Unicode code points. Nếu hợp đồng là **byte-level**, dùng mã hóa cụ thể như UTF-8 khi test; **đừng** coi số ký tự và số byte luôn giống nhau.

### 5.3. Dùng lint, nhưng không xem lint là đủ

`javac -Xlint:text-blocks` giúp phát hiện những mẫu khoảng trắng đáng nghi, chẳng hạn:

- **Inconsistent white space indentation**: các dòng có tab/space phối hợp có thể khiến mức thụt lề không như mong muốn.
- **Trailing white space will be removed**: ký tự trắng cuối dòng text block sẽ bị loại.

Tuy nhiên:

- Một formatter có thể đổi vị trí closing delimiter và làm thay đổi chuỗi **mà không có cảnh báo**.
- Cảnh báo có thể xuất hiện với một bố cục dù giá trị chuỗi **vẫn giống** bản trước.
- Kiểm tra chính xác bằng `equals`, test kết quả hoặc byte comparison mới xác nhận hợp đồng đầu ra của tính năng.

### 5.4. Kiểm tra diff và cấu hình formatter thật

Khi review PR có text blocks:

- Nhìn đồng thời **opening delimiter, tất cả dòng nội dung, closing delimiter** chứ không chỉ dòng `"""`.
- Xem formatter có **dịch toàn khối cùng mức** hay dịch **một phần**.
- Chú ý các thay đổi `"""` từ dòng riêng sang dòng cuối, hoặc ngược lại.
- Kiểm tra editor có tự động đổi tab ↔ space, xóa whitespace cuối dòng, chuẩn hóa line endings hoặc bật “format on save” không.
- Nếu formatter có chế độ **bỏ qua một vùng mã**, dùng cú pháp/configuration được tài liệu công cụ đó hỗ trợ. Không mặc định mọi formatter đều hiểu cùng một directive như `@formatter:off`.
- Giữ test cho các chuỗi nhạy cảm trong CI để một lần nâng version formatter không âm thầm đổi dữ liệu.

**Chốt điều kiện chấp nhận:** “Chỉ đổi format” là một mô tả về **ý định của tác giả**, không phải bằng chứng cho **ngữ nghĩa không đổi**. Với text block, cần xác nhận nội dung sau biên dịch.

## 6. Ảnh hưởng thực tế tùy loại dữ liệu

| Nơi dùng text block | Tác động tiềm tàng khi lề/newline thay đổi | Mức kiểm chứng phù hợp |
|---|---|---|
| **JSON mẫu** trong test | Parser thường bỏ qua whitespace ngoài string, nhưng raw JSON và snapshot byte có thể khác | Test parse semantic **và** exact text nếu so sánh văn bản |
| **YAML** | Indentation có thể ảnh hưởng quan hệ cấu trúc dữ liệu | Parse YAML và so sánh cấu trúc |
| **Markdown** | Dấu cách đầu dòng có thể biến đoạn văn thành code block hay thay đổi block format | Test render/snapshot theo use case |
| **HTML template** | Lề/newline có thể ảnh hưởng whitespace giữa các phần tử và snapshot | Kiểm tra render/DOM và raw output nếu contract yêu cầu |
| **SQL tĩnh** | Thay đổi whitespace có thể ảnh hưởng một số vị trí token/string/comment, hoặc chỉ đổi format | Test truy vấn và tham số hóa đúng cách |
| **Thông báo/email** | Lề đầu dòng và xuống dòng cuối thay đổi trình bày | So sánh văn bản gửi thực tế |
| **Snapshot/golden file** | Thường phụ thuộc từng ký tự | Exact `String.equals` hoặc so sánh byte |
| **Chữ ký, checksum, giao thức** | Thay đổi một byte có thể làm invalid chữ ký/hợp đồng | So sánh byte với charset được chỉ định, test end-to-end |

**Lưu ý an toàn:** Text block **không tự bảo vệ SQL injection hoặc JSON escaping**. Vấn đề whitespace/formatter là một trục khác; dữ liệu người dùng trong SQL phải dùng prepared statements, còn JSON động nên dùng thư viện serializer phù hợp. Không khắc phục lỗi template bằng cách nối thẳng đầu vào không tin cậy.

## 7. Giữ khoảng trắng có chủ đích thay vì phụ thuộc khoảng cách ngẫu nhiên

Nếu ứng dụng cần **một khoảng trắng cuối dòng**, `\s` có thể biểu diễn khoảng trắng chủ đích ngay cả khi editor tự xóa trailing whitespace từ source:

~~~java
String padded = """
    X\s
    """;
~~~

Giá trị là `"X \n"`: chữ `X`, một dấu cách và LF. Còn nếu bạn chỉ gõ một space vô hình sau `X` trong text block, compiler có thể bỏ nó trong quá trình loại incidental trailing whitespace.

Nếu cần **bỏ LF cuối**, có thể cân nhắc:

- Đặt closing delimiter **sát sau ký tự cuối** (như `closingInline`), nhưng phải đảm bảo định dạng mã không đổi bố cục theo cách làm khác hợp đồng.
- Dùng **line continuation** `\` sau ký tự cuối và để dấu đóng trên dòng riêng (như `continuation` trong ví dụ). Cách này làm rõ chủ đích loại LF tại vị trí đó.
- Dùng xử lý `String` có tên và có test nếu contract cần quy tắc phức tạp hơn.

Không áp dụng `stripTrailing()` một cách vô điều kiện nếu trailing spaces/tabs có ý nghĩa: phương thức này có thể xóa nhiều ký tự hơn chỉ LF cuối.

Nếu cần giữ nguyên một tệp văn bản lớn ở mức byte, cân nhắc đưa dữ liệu sang **resource file** được load với charset cụ thể, rồi kiểm chứng nội dung như một asset. Cách này tránh phụ thuộc vào một số bước chuẩn hóa text block, nhưng file resource vẫn cần kiểm soát line ending/formatter và kiểm thử ở mức byte nếu hệ thống yêu cầu.

## 8. Những hiểu lầm và lỗi thường gặp

| Hiểu lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| “Formatter chỉ thay khoảng trắng của Java source, nên `String` không đổi” | Whitespace của text block được compiler diễn giải thành giá trị | So sánh result của literal trước–sau format |
| “Dịch dấu đóng sang trái vẫn chỉ là căn lề” | Mức incidental indentation có thể giảm, giữ thêm space ở nội dung | Kiểm tra mức thụt lề nhỏ nhất và output |
| “Dịch dấu đóng sang phải chắc chắn đổi String” | Nếu lề nhỏ nhất vẫn do content line quyết định thì có thể không đổi | Tính theo toàn bộ text block, test `equals` |
| “Dời `"""` lên cuối dòng chỉ để gọn” | Có thể bỏ LF cuối, thậm chí thay đổi cách xác định lề | Kiểm tra LF cuối và leading spaces |
| “Chỉ cần nhìn indent ở dòng đầu” | Closing delimiter và các nonblank lines đều có thể tác động | Xem đủ các dòng liên quan |
| “Cứ tăng indent của toàn đoạn thì String đổi” | Nếu nội dung và closing delimiter cùng dịch đồng đều, incidental indent có thể triệt tiêu | Kiểm chứng, không kết luận từ source diff |
| “Dùng `trim()` trong test là an toàn” | Làm mất chính khác biệt whitespace cần bắt | So sánh exact string/bytes |
| “`-Xlint:text-blocks` pass thì chắc chắn ngữ nghĩa giữ nguyên” | Lint không thiết kế để đối chiếu hai phiên bản của literal | Kết hợp lint với regression tests |
| “Line endings của editor luôn được giữ nguyên như source” | Text block chuẩn hóa line terminators trong nội dung thành LF | Xác định contract output, test nơi cần byte-level |
| “Record/JSON/SQL parser không quan tâm whitespace nên chẳng sao” | Mỗi định dạng có quy tắc riêng; raw payload và snapshot vẫn đổi | Test đúng tầng semantic và tầng byte nếu cần |
| “Dấu cách cuối dòng được giữ như gõ trong editor” | Java loại incidental trailing whitespace | Dùng `\s` hoặc cấu trúc có chủ đích |
| “Mọi formatter đều hiểu `@formatter:off`” | Đây có thể là chỉ dẫn riêng của một công cụ | Kiểm tra tài liệu/cấu hình formatter đang dùng |

## 9. Quy trình review một lần format thay đổi text block

1. **Xác định thay đổi**: formatter dịch opening delimiter, các content lines, closing delimiter hay cả ba?
2. **Kiểm tra dấu đóng**: còn trên dòng riêng không? Nếu dời lên cuối dòng, LF cuối có biến mất không?
3. **Tính lại indent phụ**: dòng không blank nào ít whitespace nhất; closing line có nằm riêng và đang quyết định lề không?
4. **Phát hiện khoảng trắng có chủ đích**: relative indentation, `\s`, tabs và line continuation.
5. **Xem dữ liệu thật**: in dấu cách thành `·`, LF thành `\n`, kiểm tra độ dài nếu cần.
6. **Chạy test hợp đồng**: so sánh exact `String`/bytes, rồi parse/render theo định dạng ứng dụng.
7. **Bật compiler lint nếu phù hợp**: `javac -Xlint:text-blocks`; xem cảnh báo như tín hiệu để kiểm tra, không phải lời bảo đảm.
8. **Kết luận PR**: nếu chuỗi không đổi, có thể chấp nhận thay đổi style; nếu chuỗi đổi, xử lý như thay đổi nội dung/behavior hoặc sửa formatter/configuration.
9. **Duy trì CI test**: đảm bảo version formatter/IDE mới không tạo regression trong văn bản nhiều dòng quan trọng.

## 10. Bài tự kiểm tra

**Câu 1.** Với:

~~~java
String a = """
        X
        Y
        """;
~~~

Nếu formatter **dịch cả ba dòng liên quan sang phải 4 space**, kết quả có nhất thiết thay đổi không?

**Đáp án:** Không. Khi các dòng nội dung và closing delimiter dịch cùng lượng, mức incidental indent thường tăng tương ứng rồi bị compiler loại bỏ, nên giá trị ở tình huống này **vẫn là** `"X\nY\n"`.

**Câu 2.** Nếu chỉ dịch closing delimiter của câu 1 sang trái 4 space mà content không đổi, chuỗi có thể thay đổi thế nào?

**Đáp án:** Compiler loại đi ít space hơn. Với các dòng nội dung đang thụt 8 space và dấu đóng còn 4, kết quả là `"    X\n    Y\n"`, tức mỗi dòng giữ thêm bốn dấu cách.

**Câu 3.** Nếu chỉ dịch closing delimiter sang phải vượt qua nội dung có indent nhỏ nhất, kết quả luôn thay đổi?

**Đáp án:** Không. Dòng nội dung có lề nhỏ nhất vẫn có thể quyết định số khoảng trắng bị loại. Bài ví dụ `closingRight` và `baseline` cho kết quả giống nhau.

**Câu 4.** Nếu formatter di chuyển `"""` từ dòng riêng lên ngay sau `Y`, điều gì chắc chắn cần kiểm tra?

**Đáp án:** **LF cuối chuỗi** và khả năng thay đổi luật xác định incidental indentation. Trong ví dụ cơ bản, `"X\nY\n"` trở thành `"X\nY"`.

**Câu 5.** Vì sao chỉ sử dụng `assertEquals(actual.trim(), expected.trim())` không phù hợp nếu đang bảo vệ template?

**Đáp án:** `trim()` loại bỏ whitespace ở đầu/cuối, có thể che mất lỗi formatter tạo hoặc xóa các ký tự cần được giữ. Nên so sánh **nguyên giá trị** khi contract yêu cầu chính xác.

**Câu 6.** Lệnh `javac -Xlint:text-blocks` có chứng minh formatter giữ nguyên String không?

**Đáp án:** Không. Nó giúp tìm dấu hiệu đáng ngờ về indent/trailing whitespace nhưng không so sánh chuỗi trước–sau. Phải có test so sánh actual value.

**Câu 7.** Tại sao JSON parser đọc hai payload giống nhau về object vẫn có thể không đủ để xác nhận một text block không đổi?

**Đáp án:** JSON có thể bỏ qua whitespace không quan trọng ngoài string, nhưng raw payload đã khác và có thể liên quan tới snapshot, chữ ký hoặc test byte-level. Cần kiểm tra đúng hợp đồng ứng dụng.

## Tài liệu chính thức

- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): tính năng chuẩn từ Java 15; chi tiết về incidental whitespace, vị trí dấu đóng và escaping.
- [Java Language Specification SE 17 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): cú pháp opening/closing delimiter, cách xử lý và giá trị literal.
- [Java Language Specification SE 17 — `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): `\s`, `\\` và nối dòng `\`.
- [Oracle Java 17 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): ví dụ khi closing delimiter dịch trái/phải, newline cuối, nguyên tắc định dạng.
- [Oracle Java 17 — Text Blocks](https://docs.oracle.com/en/java/javase/17/language/text-blocks.html): tài liệu cú pháp chuẩn.
- [Java SE 17 — `String.equals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#equals(java.lang.Object)): so sánh nguyên giá trị chuỗi.
- [Java SE 17 — `String.indent` và `stripIndent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): các phương thức xử lý indent hiện đại; chỉ dùng khi đó là chủ đích xử lý dữ liệu.

**Ghi nhớ:** Với text block, **closing delimiter `"""` là thành phần có ảnh hưởng tới nội dung**. Formatter dịch đều toàn khối có thể an toàn; dịch riêng dấu đóng, nội dung hoặc đưa dấu đóng lên dòng cuối có thể đổi **leading spaces** và **trailing LF**. Hãy đo bằng `String.equals`/byte tests, kiểm tra diff và chỉ chấp nhận format khi ngữ nghĩa cần bảo vệ vẫn đúng.