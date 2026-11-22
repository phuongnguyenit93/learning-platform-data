# Trộn chữ trái–phải, phải–trái, số và dấu câu trong Java

Một chuỗi có cả tiếng Việt hoặc tiếng Anh (viết **trái sang phải**, LTR), tiếng Ả Rập hoặc tiếng Do Thái (thường viết **phải sang trái**, RTL), chữ số và dấu câu không thể hiển thị đúng bằng quy tắc “in từng ký tự từ trái sang phải”. Unicode định nghĩa **Bidirectional Algorithm (UAX #9)** để xác định **thứ tự hiển thị trực quan** từ **thứ tự logic** của chuỗi gốc. Trong Java, lớp **java.text.Bidi** giúp phân tích hướng nền, các đoạn chữ có cùng mức hướng (runs) và hỗ trợ bố trí văn bản hai chiều; bản thân nó **không** thay thế hệ thống vẽ chữ (text rendering), không uốn/gắn nét chữ Ả Rập, và không đảo hay sửa nội dung String.

Vấn đề đặc biệt dễ xuất hiện khi câu RTL xen **mã đơn hàng**, **URL**, **số điện thoại**, **giá tiền**, **dấu hai chấm**, **ngoặc đơn** và **dấu gạch nối**. Nhiều dấu câu là **neutral** (không mang hướng mạnh), nên vị trí hiển thị của chúng phụ thuộc các ký tự xung quanh và hướng nền. Những chữ số có quy tắc bidi riêng, không đơn giản là “giống LTR” hoặc “giống RTL” cho mọi trường hợp.

Bài viết này giải thích cơ chế, cách áp dụng Java 17+, ví dụ kiểm chứng, lựa chọn hướng hiển thị trong UI/web, sự khác biệt giữa dấu đánh dấu hướng và isolate, các vấn đề nhập/xuất dữ liệu và an toàn khi xử lý văn bản hỗn hợp.

## 1. Thứ tự logic và thứ tự hiển thị là hai việc khác nhau

Xét một nhãn giao diện chứa từ tiếng Anh và từ tiếng Ả Rập:

~~~text
Order 123: مرحبا
~~~

Trong String Java, các code point xuất hiện theo **thứ tự logic** do dữ liệu lưu trữ quy định: **O, r, d, e, r, khoảng trắng, 1, 2, 3, dấu hai chấm, khoảng trắng, các ký tự Ả Rập**. Trình dựng chữ nhìn vào hướng nền (paragraph base direction), bidi classes của Unicode và các quy tắc ngữ cảnh để quyết định thứ tự trực quan khi vẽ từng đoạn.

Hình thức biểu diễn trực quan không thể mô tả đáng tin bằng một chuỗi ASCII vẽ lại trong Markdown: chính trình duyệt, terminal và font đang xem Markdown có thể tự chạy thuật toán bidi thêm một lần. Vì vậy **mọi ví dụ văn bản hỗn hợp trong bài đều phân biệt “logical string” với “visual rendering”**, và dùng Unicode code point/runs để kiểm tra thay vì cố đoán vị trí dấu câu chỉ bằng mắt.

| Khái niệm | Vai trò |
| --- | --- |
| **Thứ tự logic (logical order)** | Trình tự ký tự trong String, file, JSON, database |
| **Hướng nền của đoạn (paragraph base direction)** | Mốc LTR hoặc RTL của đoạn văn |
| **Bidi class** | Lớp hướng Unicode gắn với từng ký tự |
| **Embedding level** | Mức hướng dùng khi xác định thứ tự trực quan; mức chẵn thường gắn với LTR, mức lẻ với RTL |
| **Directional run** | Đoạn liên tiếp được thuật toán gán cùng mức bidi |
| **Thứ tự trực quan (visual order)** | Thứ tự các đoạn/ký tự hiển thị sau khi áp thuật toán |
| **Text shaping** | Chọn glyph, nối/đổi dạng chữ, đặc biệt quan trọng với các hệ chữ nối nét |
| **Text layout** | Đặt glyph, xử lý font, dòng, vùng chứa, hướng và ngắt dòng |

**Hệ quả:** thứ tự người đọc nhìn thấy không nhất thiết trùng với chỉ số ký tự trong Java String. Khi người dùng đặt con trỏ, chọn văn bản hoặc sao chép, ứng dụng phải có cơ chế ánh xạ giữa vị trí logic và vị trí trên màn hình.

## 2. Những hệ chữ thường LTR, RTL và các ký tự không có hướng mạnh

Unicode phân loại ký tự theo **bidirectional class**. Một số loại cơ bản:

| Nhóm | Bidi class Unicode | Ví dụ và ý nghĩa |
| --- | --- | --- |
| Chữ LTR | **L** | Latin như A, B, chữ Việt có dấu |
| Chữ RTL | **R** | Phần lớn chữ Do Thái |
| Chữ Ả Rập | **AL** | Nhiều chữ cái Ả Rập, dùng quy tắc RTL riêng |
| Chữ số châu Âu | **EN** | ASCII 0–9 |
| Chữ số Ả Rập–Ấn Độ | **AN** | Một số dạng chữ số dùng trong văn bản Ả Rập |
| Khoảng trắng | **WS** | Một số ký tự phân cách kiểu whitespace |
| Dấu trung tính khác | **ON** | Một số dấu/biểu tượng không có hướng mạnh |
| Dấu phân cách số | **ES / CS / ET** | Một số dấu cộng, trừ, phẩy, hai chấm, ký hiệu phần trăm hoặc tiền tùy ký tự |
| Dấu kết hợp | **NSM** | Dấu Unicode không giãn, thường theo ngữ cảnh ký tự trước |
| Điều khiển đoạn/ngắt dòng | **B / S** và lớp khác | Tham gia xác định biên đoạn và cách xử lý |

Đây là **phân loại kỹ thuật**, không phải bảng quy tắc “mỗi ký tự luôn đứng bên trái/bên phải”. Ví dụ chữ số EN có nhiều quy tắc kết hợp với văn bản RTL; dấu hai chấm thường là **common separator (CS)**, còn ngoặc đơn là dấu có cơ chế bidi và paired-bracket riêng. Không thể suy trực tiếp vị trí trên màn hình chỉ từ một bidi class độc lập.

**Dữ liệu tiếng Việt** là LTR, nhưng giao diện tiếng Việt vẫn có thể chứa địa chỉ tiếng Ả Rập, tên người Do Thái, tên tệp hoặc mã quốc tế. Khi dữ liệu có nhiều script, một dòng chữ cần bố trí bidi ngay cả khi phần lớn ứng dụng là LTR.

## 3. Hướng nền của đoạn khác hướng từng từ

Một đoạn văn có thể có **hướng nền LTR** nhưng chứa một cụm RTL. Ngược lại, một câu RTL có thể có **email, URL, mã hàng** LTR.

Hướng nền giúp quyết định thứ tự và cách neo các vùng ký tự yếu/trung tính. Nó có thể:

1. Được chỉ định tường minh bởi vùng hiển thị: một trường hoặc đoạn được coi là LTR hay RTL.
2. Được chọn dựa trên **ký tự mạnh đầu tiên** khi dùng chế độ tự phát hiện.
3. Được kế thừa theo cấu trúc bố cục nếu UI không chỉ định riêng.

**Không đồng nhất hướng nền với căn lề.** Căn phải của một ô chưa chắc đặt được thuật toán bidi trong ô sang RTL. Tương tự, chọn font Ả Rập không biến chuỗi thành một đoạn RTL đúng quy tắc. Cần chỉ định đúng **text direction** hoặc sử dụng một hệ layout hỗ trợ bidi.

Trong một giao diện có đoạn RTL và mã đơn hàng LTR, nên coi mỗi phần có ý nghĩa riêng là một phân đoạn độc lập về hướng nếu nền tảng cho phép. Nếu chỉ thêm khoảng trắng hoặc đổi alignment, dấu câu có thể vẫn chạy sai.

### 3.1. Xác định hướng tự động có giới hạn

Chế độ **default LTR** không có nghĩa ép mọi ký tự thành LTR. Nó thường tìm ký tự có hướng mạnh để chọn hướng nền; nếu không có ký tự mạnh phù hợp, mới dùng hướng dự phòng LTR.

Ví dụ một đoạn bắt đầu bằng số **123:** rồi mới có từ RTL. Dãy chữ số không phải ký tự mạnh LTR giống chữ A, vì vậy hướng nền tự phát hiện có thể bị chi phối bởi từ RTL đến sau. Đây là lý do một UI chứa mã định danh toàn số không nên mặc định dựa hoàn toàn vào “ký tự đầu tiên nhìn thấy” để xác định hướng.

## 4. Số không đơn thuần chạy ngược trong RTL

Trong văn bản RTL, chữ số như **12345** thường vẫn có thứ tự nội bộ có thể đọc như một số (không tự biến thành **54321** chỉ vì câu đọc từ phải sang trái). Nhưng vị trí của **toàn bộ cụm số** so với các từ, dấu âm, ký hiệu tiền và dấu phân cách có thể khác theo ngữ cảnh.

Ví dụ những dữ liệu cần kiểm tra:

~~~text
Mã: 123-45
Invoice #2026-10
Phone: +84 901 234 567
USD 1,250.50
رقم 123
~~~

Chúng có các loại dấu/nhóm khác nhau:

- **Mã có gạch nối:** dấu trừ/gạch ngang có thể được thuật toán hiểu trong ngữ cảnh số hoặc dấu câu.
- **Số điện thoại:** dấu cộng, khoảng trắng, dấu ngoặc và dãy số thường cần xem như một thành phần dữ liệu LTR riêng.
- **Ngày và giờ:** dấu gạch chéo, dấu hai chấm, ký tự tiền tố nằm cạnh các số và chữ RTL.
- **Tiền tệ:** biểu tượng tiền, dấu thập phân và dấu nhóm có thể có cả quy tắc locale và bidi.
- **Định danh kỹ thuật:** dấu hai chấm/gạch nối có thể thuộc chuỗi ID, không có ý nghĩa câu văn.

**Không đảo từng chữ số.** Nếu đang nhận chuỗi **12345** từ dữ liệu máy, giá trị đó phải giữ nguyên thứ tự logic trong String. Công việc hiển thị thuộc về bidi layout, không phải thao tác **new StringBuilder(text).reverse()**.

### 4.1. Chữ số phương Tây và chữ số Ả Rập không giống nhau

Unicode phân biệt **European Number (EN)** và **Arabic Number (AN)** cùng nhiều lớp liên quan. **Locale** có thể quyết định bộ chữ số hiển thị của NumberFormat hoặc DateTimeFormatter, nhưng **định dạng số theo locale** và **sắp xếp bidi** là hai giai đoạn/khía cạnh khác nhau.

Chẳng hạn:

- **NumberFormat** có thể sinh ra số có dấu phân nhóm hoặc chữ số địa phương.
- **Bidi layout** quyết định vị trí cụm số ấy khi nằm trong câu chứa RTL.
- **Font/text renderer** quyết định glyph, nối nét và hình dạng cuối cùng.

Nếu app format số theo locale tiếng Ả Rập rồi đem chèn vào một đoạn tiếng Anh, vẫn phải xét hướng của cả đoạn. Không coi NumberFormat tự động giải quyết toàn bộ bidi.

## 5. Dấu câu và dấu ngoặc là nơi lỗi hiển thị dễ xảy ra nhất

Một câu hỗn hợp như:

~~~text
Status (مرحبا): 123
~~~

có chữ Latin, ngoặc đơn, từ RTL, dấu hai chấm và số. Dấu ngoặc không phải chữ mạnh LTR/RTL; Unicode Bidirectional Algorithm có quy tắc xử lý dấu trung tính và dấu ngoặc đi cặp để xác định cách vẽ. Vì thế dấu ngoặc có thể được hiển thị theo hướng hoặc phản chiếu hình glyph thích hợp với mức bidi.

**Phân biệt ba việc:**

1. **Character order:** dấu ngoặc mở và đóng vẫn là các ký tự ở vị trí logic của String.
2. **Bidi reordering:** vị trí các đoạn và ký tự trên màn hình thay đổi do thuật toán.
3. **Glyph mirroring:** một số ký hiệu như ngoặc có thể chọn glyph đối xứng khi ở hướng RTL.

**Không được dùng String.replace('(', ')')** để “sửa” dấu ngoặc trong đoạn RTL. Điều này làm hỏng dữ liệu gốc và còn sai nếu nội dung được hiển thị trong ngữ cảnh hướng khác.

Các dấu câu như **:**, **;**, **,**, **.**, **-**, dấu ngoặc và khoảng trắng có thể bị đặt ở vị trí người đọc không mong nếu một đoạn hỗn hợp được gắn vào vùng có base direction không đúng. Cần thử với **câu hoàn chỉnh**, không chỉ thử từng từ RTL đơn lẻ.

### 5.1. Dấu trừ và dấu gạch nối có những vai trò khác nhau

Ký tự **-** có thể là dấu trừ trong một số, dấu nối trong mã hàng, hoặc dấu nối của một câu. Thuật toán bidi phân loại theo ký tự và ngữ cảnh, nhưng không hiểu hết ý nghĩa nghiệp vụ của mã đơn hàng hay phép tính.

Đối với phần tử kỹ thuật như **INV-2026-12**, nên giữ một chuỗi logic duy nhất và đặt nó trong một vùng có hướng rõ ràng theo hợp đồng hiển thị, thay vì dựa vào các dấu câu xung quanh câu RTL để tự đoán vị trí.

## 6. Java 17: kiểm tra bidi class bằng Character

**Character.getDirectionality(int codePoint)** trả về hằng số cho hướng của một Unicode code point, ví dụ:

- **Character.DIRECTIONALITY_LEFT_TO_RIGHT**.
- **Character.DIRECTIONALITY_RIGHT_TO_LEFT**.
- **Character.DIRECTIONALITY_RIGHT_TO_LEFT_ARABIC**.
- **Character.DIRECTIONALITY_EUROPEAN_NUMBER**.
- **Character.DIRECTIONALITY_ARABIC_NUMBER**.
- **Character.DIRECTIONALITY_COMMON_NUMBER_SEPARATOR**.
- **Character.DIRECTIONALITY_OTHER_NEUTRALS**.

Điều này có ích khi debug chuỗi hỗn hợp. Tuy vậy **directionality của một code point không phải vị trí cuối cùng của nó trên màn hình**: cần cả chuỗi và base direction để chạy Unicode Bidirectional Algorithm.

**File DirectionalityKinds.java**

~~~java
public class DirectionalityKinds {
    public static void main(String[] args) {
        System.out.println("latin="
                + (Character.getDirectionality('A')
                == Character.DIRECTIONALITY_LEFT_TO_RIGHT));

        System.out.println("arabic="
                + (Character.getDirectionality('\u0645')
                == Character.DIRECTIONALITY_RIGHT_TO_LEFT_ARABIC));

        System.out.println("digit="
                + (Character.getDirectionality('1')
                == Character.DIRECTIONALITY_EUROPEAN_NUMBER));

        System.out.println("colon="
                + (Character.getDirectionality(':')
                == Character.DIRECTIONALITY_COMMON_NUMBER_SEPARATOR));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 DirectionalityKinds.java
java DirectionalityKinds
~~~

Stdout với Java 17:

~~~text
latin=true
arabic=true
digit=true
colon=true
~~~

Đây là các phép so sánh với hằng số API nên minh họa được bidi class mà không phụ thuộc terminal vẽ chữ Ả Rập thế nào. Chẳng hạn dấu hai chấm thuộc nhóm phân cách số chung trong dữ liệu Unicode, nhưng nó không có nghĩa “dấu hai chấm luôn dính sang phải” ở mọi câu.

**Khi xử lý dữ liệu ngoài BMP**, truyền code point kiểu int cho getDirectionality; không đi từng **char** nếu có thể vô tình phân tách surrogate pair.

## 7. java.text.Bidi xử lý các đoạn văn nhiều chiều

Lớp **java.text.Bidi** cung cấp phân tích bidi cấp độ chữ/đoạn, dựa vào thông tin Unicode và hướng nền. Nó có các constructor và API:

| API | Công dụng |
| --- | --- |
| **new Bidi(String paragraph, int flags)** | Tạo bộ phân tích bidi cho một chuỗi |
| **Bidi.DIRECTION_LEFT_TO_RIGHT** | Gợi ý hướng nền LTR tường minh |
| **Bidi.DIRECTION_RIGHT_TO_LEFT** | Gợi ý hướng nền RTL tường minh |
| **Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT** | Dò hướng mạnh, nếu không có thì dùng LTR |
| **Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT** | Dò hướng mạnh, nếu không có thì dùng RTL |
| **baseIsLeftToRight()** | Hỏi hướng nền đã chọn có là LTR không |
| **getBaseLevel()** | Lấy base embedding level của đoạn |
| **getRunCount()** | Số runs theo phân tích hiện hành |
| **getRunStart(int run)** | Vị trí logic bắt đầu của run được đánh số |
| **getRunLimit(int run)** | Vị trí logic ngay sau cuối của run |
| **getRunLevel(int run)** | Embedding level của run |
| **getLength()** | Độ dài đoạn đầu vào mà Bidi quản lý |
| **requiresBidi(char[], start, limit)** | Kiểm tra sơ bộ xem đoạn dữ liệu có cần bidi processing |
| **createLineBidi(int start, int limit)** | Tạo phân tích dành cho một dòng con |
| **reorderVisually(...)** | Sắp thứ tự các đối tượng run theo levels được cung cấp |

**Không suy rằng getRunCount bằng số từ hoặc số hệ chữ.** Dấu câu và chữ số có thể làm ranh giới runs xuất hiện ở những vị trí không trùng ranh giới từ. Số run, vị trí run và level là kết quả của toàn bộ chuỗi, base direction và thuật toán runtime.

### 7.1. Ví dụ Java kiểm chứng hướng nền và nhu cầu bidi

**File BidiBasics.java**

~~~java
import java.text.Bidi;

public class BidiBasics {
    public static void main(String[] args) {
        String english = "Hello";
        String arabic = "\u0645\u0631\u062D\u0628\u0627";
        String mixed = "Ticket 123: " + arabic;

        Bidi ltr = new Bidi(
                english, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        Bidi rtl = new Bidi(
                arabic, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println(
                "english-ltr=" + ltr.baseIsLeftToRight());
        System.out.println(
                "arabic-ltr=" + rtl.baseIsLeftToRight());

        char[] chars = mixed.toCharArray();
        System.out.println(
                "mixed-requires-bidi="
                + Bidi.requiresBidi(chars, 0, chars.length));

        System.out.println(
                "logical-prefix=" + mixed.substring(0, 6));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 BidiBasics.java
java BidiBasics
~~~

Stdout:

~~~text
english-ltr=true
arabic-ltr=false
mixed-requires-bidi=true
logical-prefix=Ticket
~~~

Chương trình tránh in một dòng hỗn hợp như “bằng chứng” về thứ tự trực quan, vì **terminal và trình đọc log có thể có quy tắc bidi khác UI sản phẩm**. Thay vào đó, nó chứng minh:

- Đoạn thuần chữ Latin được xác định nền LTR.
- Đoạn thuần chữ Ả Rập có hướng nền RTL, ngay cả khi chọn flag “default-left-to-right” vì flag này cho phép dò ký tự mạnh.
- Đoạn hỗn hợp có các ký tự cần bidi processing.
- **substring** vẫn đọc đúng thứ tự logic của String đầu vào.

**Bidi.requiresBidi** là kiểm tra kỹ thuật, không phải validator xác định nội dung là tiếng Ả Rập/Do Thái hoặc câu chắc chắn phải căn phải. Một chuỗi RTL cần xử lý theo hướng dù UI tổng thể là LTR.

## 8. Phân tích run và ánh xạ chỉ số logic

Khi viết trình xem văn bản tùy chỉnh, ta cần biết các run trong đoạn:

~~~java
Bidi bidi = new Bidi(
        mixed, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

for (int run = 0; run < bidi.getRunCount(); run++) {
    int begin = bidi.getRunStart(run);
    int end = bidi.getRunLimit(run);
    int level = bidi.getRunLevel(run);

    String logicalPart = mixed.substring(begin, end);
    System.out.println(
            "run=" + run
            + ", logical=[" + begin + "," + end + ")"
            + ", level=" + level
            + ", utf16Length=" + logicalPart.length());
}
~~~

Đoạn này **minh họa**, cần import **java.text.Bidi** và một biến **String mixed**. Số run/level được in tùy chuỗi và dữ liệu Unicode của runtime, vì vậy không ấn định một stdout cố định ở đây.

Cần chú ý:

1. Các chỉ số **start/limit** là vị trí trong chuỗi đầu vào, theo **đơn vị UTF-16**.
2. **limit** là vị trí kết thúc **exclusive**.
3. Thứ tự của runs khi bố trí trực quan khác với thứ tự các đoạn con trong String, tùy levels.
4. Các run chưa chứa glyph shaping hoặc vị trí pixel; chúng chỉ là thông tin phân tích bidi.
5. Một **emoji ngoài BMP** có thể dùng hai char; không cắt đôi surrogate pair khi xử lý các vùng văn bản tự viết.
6. Với text editor, vị trí click/hit testing cần có ánh xạ do layout engine cung cấp, không tự suy từ **run index**.

**Bidi.reorderVisually** sắp một mảng các đối tượng theo levels được cung cấp. Nó **không tự vẽ glyph**, không tách/kết hợp dấu, không xử lý shaping của Ả Rập hoặc phông chữ. Nếu cần rendering, dùng hệ thống layout hỗ trợ text shaping như thành phần UI/văn bản tương ứng.

## 9. Vì sao không tự đảo chuỗi RTL?

Cách làm dễ mắc lỗi:

~~~java
String wrong =
        new StringBuilder(userText).reverse().toString();
~~~

Đây là đoạn minh họa trong một phương thức có biến **String userText**. **StringBuilder.reverse** thay đổi thứ tự các phần tử chuỗi logic theo thuật toán của nó, không chạy UAX #9 và không biết những đoạn nào LTR/RTL, dấu câu hay số nên được giữ nội bộ.

Các lỗi có thể xuất hiện:

- Số điện thoại, mã sản phẩm, ID bị đảo ký tự.
- Các từ tiếng Anh trong câu tiếng Ả Rập bị đảo chữ.
- Dấu ngoặc có thể bị đặt sai và được renderer xử lý thêm lần nữa.
- Dấu kết hợp và cụm grapheme có thể không còn gắn đúng ý nghĩa với chữ cơ sở.
- Văn bản sao chép trở thành dữ liệu khác nguyên gốc.
- Cùng chuỗi khi hiển thị trên terminal và web lại bị đảo khác nhau.

**Lưu chuỗi theo thứ tự logic; để text layout engine quyết định thứ tự hiển thị.** Nếu cần một định dạng giao thức có thứ tự byte cụ thể, nó phải được đặc tả riêng và không phụ thuộc vào “mắt nhìn” trên màn hình.

## 10. Dấu điều hướng không in ra: LRM, RLM và ALM

Một số ký tự Unicode ảnh hưởng thuật toán bidi mà thường không có hình glyph nhìn thấy:

| Code point | Tên | Công dụng khái quát |
| --- | --- | --- |
| **U+200E** | LEFT-TO-RIGHT MARK (**LRM**) | Dấu mạnh LTR vô hình |
| **U+200F** | RIGHT-TO-LEFT MARK (**RLM**) | Dấu mạnh RTL vô hình |
| **U+061C** | ARABIC LETTER MARK (**ALM**) | Dấu bidi đặc thù nhóm Arabic |
| **U+202A** | LEFT-TO-RIGHT EMBEDDING (**LRE**) | Điều khiển embedding theo chiều LTR (cơ chế cũ) |
| **U+202B** | RIGHT-TO-LEFT EMBEDDING (**RLE**) | Điều khiển embedding RTL (cơ chế cũ) |
| **U+202C** | POP DIRECTIONAL FORMATTING (**PDF**) | Kết thúc một số embedding/override |
| **U+202D** | LEFT-TO-RIGHT OVERRIDE (**LRO**) | Ép hướng xử lý ký tự bên trong |
| **U+202E** | RIGHT-TO-LEFT OVERRIDE (**RLO**) | Ép hướng xử lý ký tự bên trong |

**LRM/RLM/ALM** có thể giúp một số dấu yếu/trung tính bám đúng phía trong câu hỗn hợp. Tuy nhiên, **không nên chèn các marks vào mọi chuỗi tùy tiện**: chúng thay đổi hành vi hiển thị, có thể gây bất ngờ khi sao chép và làm các kết quả so sánh raw String khác nhau.

Các dạng **embedding/override** cũ là công cụ mạnh nhưng dễ gây lỗi nếu thiếu kết thúc hoặc lồng nhau sai. Đặc biệt **RLO/LRO** có thể khiến một số đoạn hiển thị như đã bị đảo, dù nội dung logic vẫn khác; đây là lý do phải cảnh giác với văn bản đầu vào không đáng tin.

**Nên ưu tiên công cụ cấu trúc của nền tảng hiển thị** (ví dụ HTML **bdi** và hướng của text component) thay vì trộn các điều khiển hướng vào dữ liệu gốc chỉ để làm đẹp UI.

## 11. Isolate: LRI, RLI, FSI và PDI

Cơ chế bidi isolation hiện đại giúp một vùng văn bản tự xác định hướng mà ít ảnh hưởng tới dấu câu và nội dung nằm ngoài vùng hơn một số dạng embedding cũ.

| Code point | Tên | Mục đích |
| --- | --- | --- |
| **U+2066** | LEFT-TO-RIGHT ISOLATE (**LRI**) | Mở một vùng isolate hướng LTR |
| **U+2067** | RIGHT-TO-LEFT ISOLATE (**RLI**) | Mở vùng isolate hướng RTL |
| **U+2068** | FIRST STRONG ISOLATE (**FSI**) | Chọn hướng theo ký tự mạnh trong vùng |
| **U+2069** | POP DIRECTIONAL ISOLATE (**PDI**) | Đóng vùng isolate |

Một mô hình logic:

~~~text
Câu do ứng dụng kiểm soát
   + [bắt đầu isolate] + nội dung từ người dùng + [kết thúc isolate]
   + phần dấu câu/câu tiếp theo của ứng dụng
~~~

Với câu có tên người dùng chưa biết ngôn ngữ, isolation giúp hạn chế việc nội dung chèn vào làm dấu câu của câu ngoài bị chạy sai. **Đây là bố cục**, không phải cơ chế bảo mật chống mọi đầu vào độc hại.

### 11.1. Tạo chuỗi có FSI/PDI trong Java

~~~java
String userLabel = "\u0645\u0631\u062D\u0628\u0627";
String isolated = "\u2068" + userLabel + "\u2069";
~~~

Đây là đoạn minh họa trong phương thức. Chuỗi **isolated** chứa **FSI** và **PDI** bao quanh nội dung. Tuy nhiên, **khả năng hiển thị các controls phụ thuộc renderer và phiên bản hỗ trợ Unicode bidi**. Không được suy rằng mọi terminal, thành phần Java hoặc API xử lý chuỗi đều hỗ trợ isolate giống hệt trình duyệt hiện đại. Hãy kiểm thử trên nền tảng hiển thị mục tiêu.

Nếu UI đã hỗ trợ vùng direction/isolation có cấu trúc, thường nên sử dụng tính năng đó hơn là lưu FSI/PDI vào cột database chứa tên người dùng. Giữ dữ liệu gốc giúp tìm kiếm, so sánh và audit dễ kiểm soát hơn.

## 12. HTML: dir và bdi trong giao diện trộn hướng

Khi Java backend tạo văn bản cho giao diện web, trình duyệt có khả năng xử lý Unicode bidi và CSS/layout. Ví dụ:

~~~html
<p dir="ltr">
  Người gửi: <bdi dir="auto">مرحبا</bdi> (mã 123-45)
</p>
~~~

**Lưu ý:** ví dụ HTML minh họa nguyên tắc và không phải cú pháp Java. **dir="ltr"** đặt hướng nền cho đoạn, còn **bdi dir="auto"** cô lập tên người gửi và tự xác định hướng của nội dung. Mã **123-45** có thể cần vùng LTR riêng nếu vị trí dấu câu bị ảnh hưởng trong một bố cục cụ thể.

Với thuộc tính CSS, có thể gặp:

~~~css
.message-label {
    direction: rtl;
    unicode-bidi: isolate;
}
~~~

Đoạn CSS minh họa việc đặt hướng/isolating. Tuy nhiên, CSS **direction** không đồng nghĩa **text-align**. Việc chỉ dùng **text-align: right** để sửa một trường RTL là không đủ.

Đặc biệt chú ý đến nội dung người dùng không đáng tin: phải **HTML-escape** văn bản khi đưa vào DOM, dùng cơ chế template an toàn hoặc textContent tương đương. **bdi** xử lý hướng hiển thị, không thay thế escaping chống XSS. Đối với chuỗi nhúng chứa tên người dùng, cả **bảo vệ injection** lẫn **bảo vệ bidi boundary** đều cần được xem xét.

## 13. Rich text, Swing, JavaFX và terminal không phải cùng renderer

Trên JVM, đường đi của một đoạn text có thể là:

~~~text
Java String (logical order)
       |
       +-> Console / log viewer
       |
       +-> Swing / Java2D text layout
       |
       +-> JavaFX text layout
       |
       +-> HTML/browser hoặc mobile client
       |
       +-> File/JSON API
~~~

Mỗi môi trường có renderer và hỗ trợ shaping/bidi riêng. **java.text.Bidi** có thể cung cấp thông tin phân tích nhưng không làm cho các renderer tự động giống nhau.

- **Console:** có thể phụ thuộc terminal, font, vùng hiển thị và khả năng bidirectional rendering. Đừng dùng ảnh chụp terminal để xác minh hoàn toàn thứ tự bidi.
- **Swing/Java2D:** dùng các thành phần/engine text layout phù hợp cho văn bản quốc tế thay vì tự tính vị trí từng char.
- **JavaFX:** xác định rõ node, hướng của thành phần và hỗ trợ text layout thực tế.
- **Trình duyệt:** ưu tiên semantic HTML, **dir** và **bdi** hoặc API text direction mà nền tảng cung cấp.
- **File/JSON:** thường cần **giữ thứ tự logic**, không chuyển thành “thứ tự trực quan” trước khi lưu.

**Không chuẩn hóa cách render bằng cách đảo String trong backend.** Cùng một payload có thể hiển thị đúng tại web nhưng sai trong console; giải pháp là sửa chỗ render, không âm thầm thay đổi dữ liệu giao thức.

## 14. Phân biệt bidi với Arabic shaping

Bidi và shaping liên quan nhưng không phải một:

1. **Bidi:** quyết định thứ tự trực quan và mức hướng của các đoạn.
2. **Shaping:** quyết định hình dạng glyph, nối nét và vị trí dấu/glyph phù hợp script.
3. **Font fallback:** lựa chọn font có glyph cần thiết.
4. **Line breaking:** quyết định chỗ xuống dòng, có thể ảnh hưởng cách tính bidi cho từng dòng.

Tiếng Ả Rập cần hình dạng chữ khác nhau tùy vị trí trong từ. Nếu một chương trình chỉ dùng **Bidi.reorderVisually** rồi vẽ từng ký tự raw, chữ Ả Rập có thể bị tách nét hoặc hiển thị sai. Một text renderer hỗ trợ shaping mới xử lý đầy đủ.

Tương tự, viết tiếng Việt có dấu và các hệ chữ nhiều combining marks cần logic đặt dấu/glyph phù hợp. **java.text.Bidi không phải thư viện ghép dấu/biến đổi glyph**.

## 15. Locale và chiều chữ là hai khái niệm liên quan nhưng tách biệt

**Locale** ảnh hưởng bản dịch, ký hiệu số, ngày giờ và quy tắc văn bản. Nhưng **đặt Locale.forLanguageTag("ar")** không tự đổi mọi Java String thành RTL, và **Locale.forLanguageTag("vi")** không cấm một tên Ả Rập xuất hiện trong câu.

Ví dụ:

~~~java
Locale locale = Locale.forLanguageTag("ar");
NumberFormat price = NumberFormat.getCurrencyInstance(locale);
String amount = price.format(1234.5);
~~~

Đoạn này minh họa trong phương thức, cần imports **Locale** và **NumberFormat**. Nó tạo một chuỗi tiền theo quy tắc locale do runtime hỗ trợ. Nhưng khi gắn chuỗi ấy vào một câu có LTR và RTL, **hướng nền, dấu câu và isolation vẫn là trách nhiệm của layer hiển thị**.

Vì vậy:

| Câu hỏi | Cần giải quyết ở đâu? |
| --- | --- |
| Dùng dấu phẩy hay dấu thập phân nào? | NumberFormat/DecimalFormatSymbols/Locale |
| Dùng tên ngày/tháng nào? | DateTimeFormatter/Locale |
| Dùng văn bản dịch nào? | ResourceBundle/hệ thống i18n |
| Câu đang LTR hay RTL? | Text direction của đoạn/UI, Unicode bidi |
| Dấu ngoặc/dấu hai chấm nằm phía nào? | Bidi resolution trong ngữ cảnh |
| Chữ Ả Rập có nối nét không? | Font/text shaping |
| Giá trị ID lưu ra sao? | Hợp đồng dữ liệu, giữ logical order |

Một ứng dụng không thể giải quyết toàn bộ các câu hỏi bằng một biến locale duy nhất.

## 16. Bidi và ký tự Unicode vô hình: cách gỡ lỗi

Nếu một chuỗi “nhìn đúng nhưng so sánh sai” hoặc “dấu câu bị nhảy”, hãy in code point thay vì chỉ log trực tiếp nội dung hỗn hợp.

**File BidiCodePoints.java**

~~~java
import java.util.Locale;

public class BidiCodePoints {
    private static void dump(String text) {
        text.codePoints().forEach(cp ->
                System.out.printf(
                        Locale.ROOT, "U+%04X%n", cp));
    }

    public static void main(String[] args) {
        String text = "A" + "\u200F" + ":123";
        dump(text);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BidiCodePoints.java
java BidiCodePoints
~~~

Stdout:

~~~text
U+0041
U+200F
U+003A
U+0031
U+0032
U+0033
~~~

**U+200F** là RLM, không có glyph hiển thị thông thường. Dùng **String.codePoints()** giúp xác định sự có mặt của nó và các điều khiển khác trong dữ liệu.

**String.length()** đếm code unit UTF-16, trong khi **codePoints()** xử lý các surrogate pair hợp lệ như một code point. Khi debug offset từ **Bidi.getRunStart/getRunLimit**, đừng tự chuyển đổi tùy tiện giữa độ dài theo code point và chỉ số String.

### 16.1. Lỗi do copy/paste

Người dùng có thể copy một tên trong UI: chuỗi được sao chép theo logic có thể chứa marks/isolate hoặc không tùy thành phần UI. Một hệ thống dùng regex để dò ký tự không mong muốn cần hiểu rằng các ký tự format như U+200F có thể xuất hiện có chủ đích trong văn bản quốc tế.

**Không tự xóa mọi ký tự “zero width” hoặc direction marks khi lưu mọi loại văn bản.** Điều đó có thể làm thay đổi nội dung hợp lệ của một số ngôn ngữ. Với các trường định danh kỹ thuật, có thể giới hạn tập ký tự nghiêm ngặt, nhưng phải nói rõ hợp đồng đầu vào.

## 17. An toàn: chuỗi có thể hiển thị khác thứ tự logic

Các ký tự bidi override có thể làm cho code, tên tệp, extension hoặc mã định danh **trông khác thứ tự logic**. Đây là một vấn đề bảo mật/phòng ngừa gian lận, thường được liên hệ với kiểu tấn công **Trojan Source** hoặc tên file giả dạng.

Cần bảo vệ các bề mặt khác nhau theo cách phù hợp:

- **Source code/review:** bật cảnh báo hoặc hiển thị ký tự điều khiển bidi không mong muốn, nhất là LRO/RLO và các control không cân đối.
- **Tên tệp/đính kèm:** hiển thị extension thật dựa trên dữ liệu cấu trúc, không chỉ bằng ảnh chụp chuỗi có thể bị đảo trực quan.
- **Định danh, URL, email:** không dùng thứ tự chữ nhìn thấy để quyết định equality; làm theo hợp đồng parse/normalize/security.
- **Log/audit:** có thể ghi thêm code point hoặc escape control characters ở chế độ chẩn đoán để người điều tra không bị đánh lừa bởi việc render.
- **Văn bản tự nhiên:** vẫn cần hỗ trợ RTL hợp lệ, không cấm toàn bộ script hoặc marks một cách mù quáng.

**Không xem việc có ký tự RTL là hành vi độc hại.** Văn bản Ả Rập/Do Thái hoàn toàn bình thường; mục tiêu là phân biệt **ngữ cảnh dữ liệu không đáng tin** với **các điều khiển làm thay đổi cách nhìn** ở bề mặt nhạy cảm.

### 17.1. Bidi không thay escaping hoặc validation

Nếu nhúng nội dung vào HTML, phải escape HTML; nếu dùng SQL, parameterize query; nếu làm tên file, xác minh đường dẫn và quy tắc filesystem. **Bidi isolation** chỉ giới hạn ảnh hưởng hướng hiển thị, không xử lý injection, path traversal hoặc quyền truy cập.

Ngoài ra, việc dùng **Normalizer.NFKC** để làm sạch ký tự cũng không tự giải quyết bidi security. Unicode normalization và Unicode Bidirectional Algorithm xử lý hai phạm vi khác nhau.

## 18. Khi nào nên dùng marks, khi nào nên dùng isolate?

Một số hướng dẫn thực hành:

| Tình huống | Hướng tiếp cận |
| --- | --- |
| Giao diện web có tên người RTL trong câu LTR | Dùng **bdi dir=auto** cho nội dung người dùng |
| Mã hàng/URL có cấu trúc LTR giữa câu RTL | Dùng vùng LTR tường minh hoặc isolation theo UI |
| Một câu hoàn chỉnh có hướng RTL | Đặt base direction RTL cho vùng chứa |
| Terminal có dấu câu hiển thị lạ | Kiểm tra code points và khả năng renderer; không đảo String |
| Trường kỹ thuật lưu trữ | Giữ logical value, định nghĩa input validation |
| Văn bản nhạy cảm có Unicode control | Hiển thị cảnh báo/escape trong audit |
| Cần thêm một mark để điều chỉnh dấu câu ở vị trí cụ thể | Chỉ thêm LRM/RLM/ALM sau khi thử đúng renderer |
| Cần tách ngữ cảnh giữa hai đoạn không đáng tin | Ưu tiên isolate ở tầng bố cục |
| Cần thay hình glyph/chữ nối Ả Rập | Dùng text shaping, không dùng Bidi đơn lẻ |

**Vì sao ưu tiên isolate?** Nó xử lý một vùng văn bản như thành phần có phạm vi, hạn chế tác động của nội dung bên trong lên ngoài vùng. Tuy nhiên, không nên tuyên bố isolate là “khóa an toàn tuyệt đối”: vẫn cần kiểm thử renderer, dữ liệu không đáng tin và những vấn đề bidi controls lồng nhau.

## 19. Những lỗi phổ biến

### Lỗi 1: Đảo String bằng reverse để “sửa” RTL

Reverse phá thứ tự logic, làm sai URL, ID và số. Hãy để Unicode bidi layout xác định thứ tự trực quan.

### Lỗi 2: Coi RTL nghĩa là đảo tất cả chữ số

Nhóm chữ số có quy tắc riêng. **123** không có nghĩa sẽ thành **321** khi nằm trong câu Ả Rập.

### Lỗi 3: Căn phải nhưng không đặt hướng nền

**text-align:right** chỉ ảnh hưởng căn lề, không đầy đủ cho bidi ordering. Cần direction/paragraph orientation phù hợp.

### Lỗi 4: Tự thay '(' bằng ')' trong RTL

Glyph mirroring và bố trí dấu ngoặc là trách nhiệm của renderer. Đổi dữ liệu làm hỏng bản gốc và dễ bị phản tác dụng.

### Lỗi 5: Tưởng Character.getDirectionality trả thứ tự trực quan

Nó chỉ cho bidi class của code point. Thứ tự hiển thị phụ thuộc toàn đoạn, dấu câu, base direction và các controls.

### Lỗi 6: Tưởng java.text.Bidi tự vẽ chữ Ả Rập

Bidi là phân tích hướng, không xử lý font/shaping; cần text layout engine.

### Lỗi 7: Trộn U+200E/U+200F vào mọi tên người

Marks không nhìn thấy làm khác chuỗi và có thể làm copy/paste khó đoán. Ưu tiên isolation ở tầng UI khi có.

### Lỗi 8: Quên phần dấu câu nằm ngoài một chuỗi RTL động

Một tên RTL được nối thẳng với dấu hai chấm có thể ảnh hưởng vị trí dấu ngoài tên. Cô lập vùng tên động thay vì thử thêm khoảng trắng vô hạn.

### Lỗi 9: Dùng Locale để thay thế chỉ định direction

Locale chọn dữ liệu bản địa hóa, không tự sửa hướng mọi String khi render. Cần cả locale và hướng nền UI.

### Lỗi 10: Chỉ kiểm tra terminal

Terminal có thể hiển thị bidi khác browser/app. Test trên renderer thật với font và ngôn ngữ mục tiêu.

### Lỗi 11: Cắt substring theo chiều chữ nhìn thấy

Offset của String ở thứ tự logic; vị trí click/caret trên màn hình là chuyện khác. Dùng API hit-testing/layout thay vì tự cộng chỉ số.

### Lỗi 12: Xóa mọi ký tự vô hình để “bảo mật”

Một số marks/controls có chức năng văn bản hợp lệ. Xây chính sách theo loại dữ liệu; với mã kỹ thuật có thể nghiêm ngặt hơn văn bản tự nhiên.

### Lỗi 13: Dựa vào ảnh render để so mã tài khoản

Bidi có thể đổi vị trí nhìn thấy mà không đổi String gốc. Định danh cần dựa trên biểu diễn dữ liệu đã định nghĩa.

### Lỗi 14: Không kiểm thử dấu âm, mã hàng và tiền tệ

Dấu câu và số là nơi lỗi bidi dễ lộ. Test những câu thực tế chứa 123-45, 12:30, số điện thoại, mã tiền và ngoặc.

## 20. Ma trận kiểm thử nên có

| Kịch bản | Cần kiểm chứng |
| --- | --- |
| Chữ Latin thuần | Base LTR, không có lỗi đảo chữ |
| Chữ Ả Rập/Do Thái thuần | Base RTL đúng khi tự dò hoặc chỉ định |
| Chữ Latin + tên Ả Rập | Dấu câu nằm đúng phía theo ngữ cảnh |
| Đoạn RTL + **12345** | Giữ thứ tự nội bộ của số |
| Đoạn RTL + **INV-2026-12** | Mã kỹ thuật hiển thị và copy đúng |
| Số điện thoại **+84 ...** trong câu RTL | Dấu cộng/ngoặc không chạy sai |
| Giá tiền có dấu nhóm/thập phân | Định dạng locale kết hợp bidi layout đúng |
| Dấu ngoặc bao một tên RTL | Vị trí/paired bracket mirroring đúng |
| Tiêu đề có tên động **bdi dir=auto** | Vùng tên không kéo dấu câu của phần ngoài |
| Không có strong char | Hướng fallback nhất quán |
| U+200E/U+200F/U+061C | Có chiến lược hiển thị/chẩn đoán |
| U+2066/U+2067/U+2068/U+2069 | Renderer hỗ trợ isolation đúng |
| U+202E hoặc override khác trong input nhạy cảm | Có cảnh báo/escape audit |
| Chữ Ả Rập có nối nét | Shaping và font fallback hoạt động |
| Copy/paste từ UI | Logical order và các control được xử lý có chủ đích |
| Unicode ngoài BMP/emoji | Không tách surrogate pair, caret/hit test hợp lệ |
| UI tiếng Việt có tên RTL | Không giả định chỉ locale tiếng Việt là đủ |
| Browser, app và terminal | Các khác biệt renderer đã được hiểu |

### 20.1. Test chức năng và test hình ảnh

**Test chức năng (deterministic):** kiểm tra code point, hướng nền đã chỉ định, String gốc không đổi, dữ liệu ID và các đặc tính của API Bidi. Không cần một font cụ thể.

**Test rendering:** kiểm tra trực quan trên các nền tảng hỗ trợ, nên có ảnh tham chiếu hoặc kiểm tra thủ công của người dùng hiểu ngôn ngữ mục tiêu. Thử từng vùng LTR/RTL, font fallback, dấu câu, dòng dài và xuống dòng.

**Không lấy stdout của terminal làm golden test duy nhất** cho Unicode bidi. Hệ điều hành, terminal và web có thể dùng renderer khác nhau; một chuỗi xuất ra console theo thứ tự logic vẫn có thể được vẽ khác.

### 20.2. Test bảo toàn dữ liệu

Khi đưa nhãn từ database ra UI rồi cho sao chép trở lại, cần kiểm tra rằng:

1. Giá trị mã kỹ thuật không bị đảo ký tự.
2. Không thêm LRM/RLM/FSI/PDI vào dữ liệu nguyên gốc nếu chúng chỉ thuộc lớp UI.
3. Dấu ngoặc và dấu hai chấm vẫn nằm đúng vị trí logic.
4. Giá trị lưu không phụ thuộc font hoặc text-align.
5. Những ký tự định hướng có chủ đích trong văn bản tự nhiên được xử lý theo chính sách rõ.
6. Khi xuất JSON/API, Unicode string vẫn giữ cấu trúc dữ liệu, không xuất “visual order” tự tạo.

## 21. Checklist triển khai Java 17+ cho nội dung hỗn hợp

- [ ] Phân biệt **logical order** của String và **visual order** của renderer.
- [ ] Biết các bidi classes **L, R, AL, EN, AN, NSM, neutral**.
- [ ] Chọn base direction phù hợp; không coi text alignment là hướng đoạn.
- [ ] Dùng **java.text.Bidi** để quan sát base level và runs khi cần xử lý phân tích hướng.
- [ ] Không coi **Bidi** là bộ font shaping.
- [ ] Không đảo String hoặc tự thay dấu ngoặc khi cần RTL.
- [ ] Giữ nhóm số/ID/URL theo logical order; xác định hướng vùng hiển thị.
- [ ] Kiểm tra dấu câu và khoảng trắng ở ranh giới giữa LTR/RTL.
- [ ] Hiểu LRM, RLM, ALM và các bidi controls, chỉ dùng khi có lý do rõ.
- [ ] Ưu tiên vùng isolation có cấu trúc khi nhúng tên người/nội dung động.
- [ ] Với web, xem xét **dir=auto**, **bdi** và semantic markup.
- [ ] HTML-escape nội dung không đáng tin; bidi không thay bảo vệ injection.
- [ ] Dùng **String.codePoints()** khi điều tra ký tự vô hình.
- [ ] Phân biệt số được format theo Locale với số được bố trí theo bidi.
- [ ] Kiểm thử trên renderer thật với font và ngôn ngữ hỗ trợ.
- [ ] Bảo toàn chuỗi gốc cho lưu trữ/API/audit, không xuất “visual string” đã đảo.
- [ ] Có chính sách phòng chống bidi controls gây đánh lừa trong mã nguồn, tên file và định danh.
- [ ] Không loại bỏ văn bản RTL hợp lệ chỉ vì có dấu điều khiển/ngôn ngữ khác.

## 22. Kết luận

Trộn chữ LTR, RTL, số và dấu câu là vấn đề **Unicode Bidirectional Algorithm và text layout**, không phải việc đổi thứ tự các ký tự bằng tay. **Dữ liệu Java String nên được giữ ở thứ tự logic**; hướng nền, bidi classes, các runs và isolation giúp renderer đưa nội dung lên màn hình đúng ngữ cảnh. Trong Java 17+, **Character.getDirectionality** giúp quan sát lớp hướng của code point, còn **java.text.Bidi** giúp phân tích đoạn văn hai chiều, levels và runs; muốn nhìn chữ Ả Rập đúng còn cần font và text shaping.

Đối với giao diện, hãy đặt direction đúng cho vùng chứa và cô lập các đoạn động/định danh kỹ thuật khi cần, kiểm tra dấu ngoặc, dấu hai chấm, số điện thoại và giá tiền. Đối với dữ liệu, đừng đảo chuỗi, đừng gắn điều khiển vô hình tùy tiện và đừng đánh đồng hiển thị trực quan với danh tính dữ liệu. Khi kết hợp kiểm thử code point với kiểm thử renderer, ứng dụng Java đa ngôn ngữ có thể vừa giữ nguyên dữ liệu vừa hiển thị các đoạn LTR/RTL tự nhiên, dễ đọc và an toàn hơn.
