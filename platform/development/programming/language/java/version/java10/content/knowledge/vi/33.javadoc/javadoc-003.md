# Phân biệt tóm tắt tường minh với suy ra từ câu đầu trong Javadoc

## 1. Vì sao Javadoc cần một bản tóm tắt ngắn?

Khi đọc tài liệu API Java, người dùng thường xem các bảng **Class Summary**, **Method Summary**, **Field Summary** hoặc kết quả tìm kiếm trước khi đi vào phần mô tả dài. Mỗi dòng trong bảng cần một **summary**, đủ ngắn để giúp người đọc biết API này làm gì.

Công cụ `javadoc` của JDK có hai cách lựa chọn phần tóm tắt của một phần tử:

1. **Suy từ câu đầu của main description** khi người viết không chọn summary tường minh.
2. **Lấy nội dung từ inline tag `{@summary ...}`** khi thẻ này nằm **ngay đầu main description** của Javadoc comment.

Ví dụ một phương thức:

~~~java
/**
 * Trả về lời chào theo tên người dùng.
 * Tên được loại bỏ khoảng trắng ở hai đầu.
 *
 * @param name tên của người nhận
 * @return lời chào
 */
public static String greet(String name) {
    return "Hello, " + name.strip() + "!";
}
~~~

Nếu không có thẻ riêng, công cụ thường suy phần summary từ câu đầu:

~~~text
Trả về lời chào theo tên người dùng.
~~~

Có thể chọn rõ phần summary bằng cách viết:

~~~java
/**
 * {@summary Tạo lời chào ngắn từ tên đã chuẩn hóa.}
 * Phương thức loại bỏ khoảng trắng ở hai đầu tên
 * trước khi ghép chuỗi lời chào.
 *
 * @param name tên người nhận
 * @return lời chào
 */
public static String greet(String name) {
    return "Hello, " + name.strip() + "!";
}
~~~

Ở trường hợp này, summary được lấy từ **nội dung thẻ**, không cần phỏng đoán ranh giới câu đầu của đoạn mô tả dài.

**Liên hệ Java 10:** thẻ **`{@summary}` được bổ sung từ JDK 10** theo cải tiến **JDK-8173425**. Oracle Java SE 17, 25 và 26 vẫn mô tả thẻ này trong **Documentation Comment Specification for the Standard Doclet**. Vì vậy đây là tính năng Javadoc **hiện vẫn được hỗ trợ**, không phải cú pháp đã bị bỏ hoặc cần thay bằng API không công khai.

Bài này giải thích sự khác nhau giữa hai cơ chế, cách viết thẻ đúng vị trí, giới hạn của thuật toán xác định câu đầu, ví dụ Java 17+ chạy được và cách kiểm **HTML Javadoc thực tế**.

## 2. Nhận diện main description, inline tags và block tags

### 2.1. Comment nào mới là Javadoc?

~~~java
// Một dòng comment thường, không tạo API documentation.

/* Comment nhiều dòng thường. */

/**
 * Đây là Javadoc comment cho khai báo ở ngay sau nó.
 */
public class Example {
}
~~~

Cú pháp truyền thống `/** ... */` là **documentation comment**. Công cụ `javadoc` dùng nó để sinh tài liệu cho class, interface, record, enum, field, constructor, method, package hoặc module khi nguồn và cấu hình phù hợp.

Một comment `// ...`, dù chứa chữ `summary`, không có vai trò tự tạo mục tóm tắt trong standard Javadoc.

### 2.2. Phần mô tả chính và các thẻ

~~~java
/**
 * Câu mô tả ngắn của phương thức.
 * Phần mô tả tiếp theo giải thích các điều kiện.
 *
 * <p>Đây là đoạn mô tả chi tiết hơn.
 *
 * @param text chuỗi đầu vào
 * @return độ dài của text
 * @throws NullPointerException nếu text là null
 */
public static int length(String text) {
    return java.util.Objects.requireNonNull(text).length();
}
~~~

Trong đó:

- **Main description** bắt đầu ở nội dung đầu comment và kết thúc trước **block tag đầu tiên**.
- Summary mặc định được lấy từ **câu đầu của main description**.
- **Block tags** như `@param`, `@return`, `@throws` bắt đầu đầu dòng (bỏ qua ký tự trang trí `*` và whitespace) để bổ sung tài liệu có cấu trúc.
- **Inline tags** có dạng `{@name content}` nằm trong một đoạn mô tả, ví dụ `{@code ...}`, `{@link ...}` và `{@summary ...}`.
- Main description **không tiếp tục** sau một block tag.

Chính sự phân biệt này giải thích tại sao đặt `{@summary}` trong `@param` không có tác dụng chọn summary cho API.

### 2.3. Cú pháp dễ nhầm

| Viết trong comment | Loại | Công dụng |
| --- | --- | --- |
| `{@summary Mô tả ngắn.}` | Inline tag | Chọn API summary khi ở đầu main description |
| `@summary Mô tả ngắn.` | Không phải cú pháp summary chuẩn | Không dùng làm cách thay thế |
| `@param name ...` | Block tag | Giải thích tham số |
| `@return ...` | Block tag | Giải thích kết quả |
| `@throws Exception ...` | Block tag | Giải thích ngoại lệ |
| `{@code expression}` | Inline tag | Render code theo cách phù hợp |
| `{@link java.lang.String}` | Inline tag | Tạo liên kết API |
| `{@inheritDoc}` | Inline tag | Kế thừa một phần tài liệu theo quy tắc Javadoc |

Không viết `@summary` ở một dòng riêng rồi mong standard doclet hiểu là summary. Tên thẻ đúng là **`{@summary ...}`**, với dấu ngoặc nhọn.

## 3. Cơ chế mặc định: suy summary từ câu đầu

### 3.1. Trường hợp đơn giản

~~~java
/**
 * Tính tổng của hai số nguyên. Hàm không thay đổi
 * các đối số đã nhận.
 *
 * @param a số thứ nhất
 * @param b số thứ hai
 * @return tổng của a và b
 */
public int add(int a, int b) {
    return a + b;
}
~~~

Phần summary được suy từ câu đầu:

~~~text
Tính tổng của hai số nguyên.
~~~

Phần “Hàm không thay đổi các đối số đã nhận” thuộc mô tả đầy đủ; `@param` và `@return` được trình bày riêng.

**Đây vẫn là cơ chế hợp lệ trên JDK hiện đại.** Không nhất thiết thêm thẻ tường minh cho mọi Javadoc nếu câu đầu đã ngắn, có ý nghĩa và công cụ nhận diện đúng.

### 3.2. “Câu đầu” không đơn giản là đoạn tới dấu chấm đầu tiên

Các ví dụ có thể làm công cụ khó xác định ranh giới câu:

~~~text
Hỗ trợ cú pháp cấu hình v2.1 trong môi trường thử nghiệm.
~~~

Dấu chấm giữa `2` và `1` **không phải** dấu kết thúc câu.

~~~text
Returns the formatted name for Dr. Smith. The method is pure.
~~~

Dấu chấm sau `Dr.` là một phần của viết tắt.

Dấu chấm cũng có thể thuộc tên class `com.example.Service`, file `config.properties`, URL hoặc tên API. Một thuật toán quá đơn giản cắt ngay sau dấu chấm đầu tiên có thể tạo summary thiếu nghĩa.

Oracle JDK 10 Release Notes giải thích rằng standard Javadoc mặc định dùng **heuristic** nhận diện câu đầu (thuật toán đơn giản hoặc `java.text.BreakIterator`), đôi khi xác định sai điểm kết thúc. Đây là lý do `{@summary}` được bổ sung.

### 3.3. -breakiterator và locale

`javadoc` vẫn có tùy chọn:

~~~bash
javadoc -breakiterator ...
~~~

Nó yêu cầu dùng `java.text.BreakIterator` để tìm ranh giới câu. Theo Javadoc tool documentation, chiến lược mặc định có thể khác theo **locale**: tiếng Anh thường dùng thuật toán đơn giản khi không bật option, các locale khác có thể dùng BreakIterator mặc định.

Do đó:

- Không hứa cùng một chuỗi có cùng điểm cắt trên mọi JDK và locale.
- Không kiểm Javadoc bằng một regex “lấy text trước dấu chấm đầu tiên”.
- Không coi `-breakiterator` là công cụ sửa mọi dấu viết tắt: bộ phân tách câu cũng có những trường hợp khó.
- Khi cần summary có nội dung xác định, hãy viết thẻ `{@summary}` đúng vị trí.

### 3.4. Dấu hỏi, dấu chấm than và cấu trúc HTML

Một mô tả bắt đầu bằng câu hỏi:

~~~java
/**
 * Dịch vụ đã sẵn sàng chưa? Phương thức kiểm tra
 * điều kiện hoạt động.
 */
public boolean ready() {
    return true;
}
~~~

Không thể khẳng định mọi cấu hình mặc định sẽ tạo cùng một summary với dấu hỏi. Với HTML blocks hoặc Markdown doc comments trên những JDK mới, quy tắc phát hiện ranh giới cũng có điểm riêng.

Nếu điều quan trọng là phần Summary luôn mô tả chức năng, viết:

~~~java
/**
 * {@summary Kiểm tra trạng thái sẵn sàng của dịch vụ.}
 * Phương thức không thay đổi trạng thái bên trong.
 */
public boolean ready() {
    return true;
}
~~~

## 4. Tóm tắt tường minh với {@summary ...}

### 4.1. Định nghĩa còn được áp dụng

Theo Oracle Documentation Comment Specification JDK 25/26:

~~~text
{@summary text}
~~~

Inline tag này chỉ định nội dung summary như một **giải pháp thay thế** cho suy summary từ câu đầu. Nó **chỉ có ý nghĩa chọn summary khi đặt ở đầu main description**.

Ví dụ:

~~~java
/**
 * {@summary Truy xuất bản ghi theo mã định danh.}
 * Kết quả có thể rỗng nếu không tìm được bản ghi.
 */
public String find(String id) {
    return id;
}
~~~

Phần summary không phụ thuộc nội dung đoạn giải thích tiếp theo. Text trong tag vẫn được **render như một phần mô tả** trên trang chi tiết.

### 4.2. Vị trí đặt đúng

Đúng:

~~~java
/**
 * {@summary Đổi trạng thái thành nhãn READY hoặc WAIT.}
 * Các nhãn độc lập với locale đang dùng.
 */
public String label(boolean ready) {
    return ready ? "READY" : "WAIT";
}
~~~

Khoảng trắng và ký tự `*` ở đầu dòng là phần trang trí của Javadoc comment, không ngăn tag là nội dung có ý nghĩa đầu tiên.

Sai về mục tiêu **ghi đè summary**:

~~~java
/**
 * Đổi trạng thái thành nhãn.
 * {@summary Nhãn READY hoặc WAIT.}
 * Có hai giá trị đầu ra.
 */
public String label(boolean ready) {
    return ready ? "READY" : "WAIT";
}
~~~

Đoạn này đặt `{@summary}` **sau câu đầu**. Theo specification, tag lúc này có thể vẫn được render dưới dạng text, nhưng không còn là thẻ có ý nghĩa **chọn summary tường minh**.

### 4.3. Không đặt trong @param hay @return

~~~java
/**
 * Chuyển dữ liệu thành văn bản.
 *
 * @param value {@summary Chuyển một giá trị thành text.}
 * @return chuỗi đã tạo
 */
public String format(String value) {
    return value;
}
~~~

Thẻ trong ví dụ nằm **bên trong mô tả tham số**, không phải đầu main description. Không sử dụng nó để chọn summary.

Cách đúng:

~~~java
/**
 * {@summary Chuyển một giá trị thành chuỗi văn bản.}
 * Trong ví dụ này phương thức trả lại chuỗi ban đầu.
 *
 * @param value chuỗi đầu vào
 * @return chính value
 */
public String format(String value) {
    return value;
}
~~~

### 4.4. Thẻ được render ngay cả khi không có vai trò chọn summary

Một câu trong specification rất dễ bị bỏ sót: **nội dung `{@summary}` được render trong mọi trường hợp**. Điều này không có nghĩa vị trí nào cũng thay đổi summary.

Hậu quả: nếu tag được đặt giữa đoạn mô tả dài, bạn có thể nhìn thấy **text của tag** trong phần Method Details và tưởng nó hoạt động đúng. Để QA, phải **xem bảng Method Summary**, không chỉ tìm chuỗi trong toàn file HTML.

### 4.5. Tóm tắt nên ngắn, đầy đủ và đúng contract

Nội dung tốt:

~~~java
/**
 * {@summary Kiểm tra bản ghi có tồn tại hay không.}
 * Không tạo mới bản ghi khi không tìm thấy.
 */
public boolean exists(String id) {
    return id != null;
}
~~~

Nội dung kém:

~~~java
/**
 * {@summary Thực hiện việc gọi phương thức exists theo cách
 * kiểm tra một số điều kiện mà có thể người dùng cần, đồng
 * thời điều khiển mọi trường hợp theo triển khai nội bộ.}
 */
public boolean exists(String id) {
    return id != null;
}
~~~

Một summary nên giúp người đọc nhận biết **hành vi chính**, không cần chứa mọi thông tin về caching, performance, lỗi và ví dụ. Phần chi tiết dùng để giải thích sâu hơn.

Và cần tránh mô tả sai: nếu code không có dữ liệu lưu trữ mà chỉ kiểm `id != null`, không được ghi tóm tắt “truy vấn database để xác định tồn tại”. Ví dụ chỉ minh họa kỹ thuật viết comment; trong dự án thật, tài liệu phải phù hợp implementation/contract.

## 5. So sánh trực tiếp hai cách tạo summary

| Câu hỏi | Suy từ câu đầu | `{@summary ...}` đầu main description |
| --- | --- | --- |
| Ai chọn text ngắn? | Standard doclet tìm first sentence | Người viết chỉ định |
| Có cần tag đặc biệt? | Không | Có |
| Có phụ thuộc heuristic/locale? | Có thể | Không cần suy câu đầu để chọn summary |
| Có từ bản nào? | Hành vi Javadoc cơ bản | JDK 10 |
| Có còn được hỗ trợ trên Java 17/25? | Có | Có |
| Có tiếp tục mô tả chi tiết được không? | Có | Có |
| Có tác động tới runtime bytecode? | Không | Không |
| Nên dùng khi nào? | Câu đầu rõ, ngắn và ổn định | Cần kiểm soát text, có dấu viết tắt/markup |
| Có phải thay `@param`/`@return`? | Không | Không |
| Dùng được trong comment `//`? | Không | Không |

### 5.1. Không dùng {@summary} chỉ vì “mới hơn”

Nếu câu đầu đã tốt:

~~~java
/**
 * Đọc trạng thái hiện tại của bộ đếm. Thao tác không
 * làm thay đổi giá trị của bộ đếm.
 */
public int current() {
    return 0;
}
~~~

thì cơ chế mặc định là lựa chọn hợp lý. Thẻ tường minh là công cụ để **làm rõ ý định** và tránh trường hợp heuristic không như mong muốn; không phải một yêu cầu bắt buộc để Javadoc hợp lệ.

### 5.2. Các trường hợp nên cân nhắc tag tường minh

- Phần mô tả mở đầu có tên phiên bản `v2.1` hoặc viết tắt.
- Một phương thức có câu đầu dài vì nhiều điều kiện nghiệp vụ.
- Tài liệu sử dụng tiếng Việt và được sinh với nhiều locale.
- Phần mô tả đầu có HTML, inline links hoặc cấu trúc phức tạp.
- Đội phát triển muốn một câu summary cố định khi cập nhật phần details.
- Đã QA thấy summary trong bảng bị cắt hoặc nối không đúng.

## 6. Chương trình Java 17+ hoàn chỉnh với cả hai kiểu Javadoc

Chương trình dưới đây cho phép kiểm độc lập:

- **`javac` và `java`:** code chạy và stdout xác định.
- **`javadoc`:** sinh HTML cho các phương thức có summary tường minh và mặc định.

Lưu file **`JavadocSummaryGuide.java`** theo UTF-8:

~~~java
import java.util.Objects;

/**
 * Minh họa cách tạo phần tóm tắt của tài liệu Javadoc.
 * Lớp có các phương thức nhỏ để so sánh Method Summary
 * với phần mô tả đầy đủ của từng method.
 */
public final class JavadocSummaryGuide {

    private JavadocSummaryGuide() {
    }

    /**
     * {@summary Tạo lời chào ngắn từ một tên hợp lệ.}
     * Phương thức bỏ khoảng trắng ở hai đầu tên
     * trước khi tạo lời chào.
     *
     * @param name tên người nhận, không null hoặc blank
     * @return lời chào theo mẫu Hello
     * @throws IllegalArgumentException nếu name null hoặc blank
     */
    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("blank name");
        }
        return "Hello, " + name.strip() + "!";
    }

    /**
     * Đếm số đơn vị mã UTF-16 trong chuỗi đầu vào.
     * Phương thức dùng String.length(), không đếm
     * số Unicode code point.
     *
     * @param text chuỗi cần đo độ dài
     * @return số đơn vị mã UTF-16
     * @throws NullPointerException nếu text là null
     */
    public static int count(String text) {
        return Objects.requireNonNull(text, "text").length();
    }

    /**
     * {@summary Chọn nhãn READY hoặc WAIT theo trạng thái.}
     * Kết quả có dạng chữ hoa và độc lập với locale.
     *
     * @param ready true nếu trạng thái sẵn sàng
     * @return READY khi ready, WAIT khi không ready
     */
    public static String label(boolean ready) {
        return ready ? "READY" : "WAIT";
    }

    /**
     * Chạy ví dụ và in đầu ra xác định.
     *
     * @param args không sử dụng
     */
    public static void main(String[] args) {
        System.out.println("greet=" + greet("  Lan  "));
        System.out.println("count=" + count("Java"));
        System.out.println("label=" + label(true));

        try {
            greet("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "rejectBlank=" + ex.getMessage());
        }
    }
}
~~~

### 6.1. Biên dịch và chạy

Cần JDK 17 hoặc mới hơn, với `javac` và `java` trên `PATH`:

~~~bash
javac --release 17 -encoding UTF-8 -d out JavadocSummaryGuide.java
java -cp out JavadocSummaryGuide
~~~

**Stdout chính xác:**

~~~text
greet=Hello, Lan!
count=4
label=READY
rejectBlank=blank name
~~~

Giải thích:

- `greet("  Lan  ")` chuẩn hóa tên bằng `String.strip()` rồi trả `Hello, Lan!`.
- `count("Java")` dùng `String.length()` và in 4.
- `label(true)` trả `READY`.
- `greet("   ")` bị `String.isBlank()` từ chối và exception được bắt để in thông báo đúng.
- Không có file input, thời gian, random, network hoặc formatting theo locale trong stdout này.

**Ranh giới phiên bản:** tag Javadoc `{@summary}` được giới thiệu từ JDK 10, nhưng **code chạy** ở đây yêu cầu Java 11+ vì `String.strip()` và `String.isBlank()`, đồng thời ví dụ chủ động dùng `--release 17`. Không nhầm “cú pháp comment có từ Java 10” với “mọi API trong chương trình đều chạy trên Java 10”.

### 6.2. Sinh tài liệu Javadoc

Trên shell POSIX/Linux/macOS:

~~~bash
javadoc -quiet -Xdoclint:all -encoding UTF-8 \
  -docencoding UTF-8 -charset UTF-8 \
  -d docs JavadocSummaryGuide.java
~~~

Trên Windows dùng một dòng:

~~~text
javadoc -quiet -Xdoclint:all -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -d docs JavadocSummaryGuide.java
~~~

Khi sinh tài liệu thành công cho class **không có package declaration**, file HTML thường ở:

~~~text
docs/JavadocSummaryGuide.html
~~~

Không khẳng định console output của `javadoc` luôn giống nhau giữa các JDK, locale hoặc nền tảng. Hãy kiểm **file và nội dung được tạo** thay vì so từng dòng log.

### 6.3. Cách kiểm Method Summary

Mở `docs/JavadocSummaryGuide.html` và tìm phần **Method Summary** (hoặc nhãn giao diện đã được địa phương hóa):

| Method | Nội dung tóm tắt mong đợi | Cơ chế |
| --- | --- | --- |
| `greet(String)` | “Tạo lời chào ngắn từ một tên hợp lệ.” | `{@summary}` |
| `count(String)` | “Đếm số đơn vị mã UTF-16 trong chuỗi đầu vào.” | Suy từ câu đầu |
| `label(boolean)` | “Chọn nhãn READY hoặc WAIT theo trạng thái.” | `{@summary}` |
| `main(String[])` | “Chạy ví dụ và in đầu ra xác định.” | Suy từ câu đầu |

Sau đó xem **Method Details**. Chi tiết của `greet` vẫn chứa text summary được render, câu mô tả dài và các phần tham số, giá trị trả về, ngoại lệ.

**Đừng chỉ tìm chuỗi “Tạo lời chào...” trong toàn HTML**: text cũng được render trong details ngay cả khi một tag nằm sai vị trí. Phải kiểm **đúng mục Summary**.

### 6.4. Hai phép kiểm độc lập

| Lệnh/kiểm | Câu hỏi trả lời |
| --- | --- |
| `javac --release 17` | Mã nguồn hợp lệ và dùng API Java 17? |
| `java -cp out JavadocSummaryGuide` | Hành vi runtime và stdout đúng? |
| `javadoc -Xdoclint:all` | Documentation comments có thể được xử lý/sinh HTML? |
| Xem HTML `Method Summary` | Text nào thực sự được dùng làm summary? |
| Xem HTML `Method Details` | Mô tả dài và các tags có được render đúng? |

Chỉ compile Java thành công **không phải bằng chứng** phần summary HTML đã đúng.

## 7. Những ví dụ đối chứng về vị trí thẻ

### 7.1. Câu đầu rõ ràng: không cần summary tag

~~~java
/**
 * Đọc bản ghi theo mã định danh. Hệ thống trả null
 * khi không tìm thấy dữ liệu.
 *
 * @param id mã bản ghi
 * @return bản ghi hoặc null
 */
public String read(String id) {
    return id;
}
~~~

Đây là ví dụ method đơn giản. Standard doclet suy summary từ câu đầu; mọi chi tiết về tham số và giá trị trả về vẫn thuộc phần thông tin bổ sung.

### 7.2. Thẻ nằm đúng đầu: chọn rõ summary

~~~java
/**
 * {@summary Truy xuất bản ghi theo mã định danh.}
 * Tên có thể chứa dấu chấm và tiền tố v2.1.
 *
 * @param id mã bản ghi
 * @return bản ghi hoặc null
 */
public String read(String id) {
    return id;
}
~~~

Summary được chọn rõ, không phụ thuộc dấu chấm trong phần giải thích.

### 7.3. Thẻ sau câu đầu: không override summary

~~~java
/**
 * Đọc bản ghi theo mã định danh.
 * {@summary Truy xuất bản ghi theo mã định danh.}
 *
 * @param id mã bản ghi
 * @return bản ghi hoặc null
 */
public String read(String id) {
    return id;
}
~~~

Mặc dù text trong `{@summary ...}` có thể xuất hiện ở phần mô tả, vị trí **sau câu đầu** không hợp quy tắc chọn summary tường minh.

### 7.4. Thẻ trong @return: sai ngữ cảnh

~~~java
/**
 * Đọc bản ghi theo mã định danh.
 *
 * @param id mã bản ghi
 * @return {@summary Tóm tắt mong muốn ở đây.}
 */
public String read(String id) {
    return id;
}
~~~

Đây là nội dung block tag `@return`, **không phải phần đầu main description**. Nếu cần summary, đặt `{@summary ...}` trước phần `@param` và `@return`.

## 8. Xử lý dấu câu, code, đường dẫn và locale

### 8.1. Tên phiên bản

~~~java
/**
 * {@summary Đọc cấu hình cho định dạng v2.1.}
 * Các bản ghi v2.1 có thể chứa mã nội bộ khác nhau.
 */
public String readConfiguration() {
    return "ok";
}
~~~

Đây là trường hợp summary tường minh có giá trị: vừa chứa phiên bản có dấu chấm, vừa tránh phải phụ thuộc cách công cụ chia câu.

### 8.2. Tên class, package và file

Một câu mô tả chứa `com.example.api`, `config.properties` hoặc `https://example.org/docs` có thể có nhiều dấu chấm không phải kết thúc câu. Không loại bỏ tất cả những chi tiết kỹ thuật cần thiết chỉ để ép first-sentence heuristic; hãy dùng tag tường minh nếu nó thực sự gây nhầm.

### 8.3. Nội dung tiếng Việt và Unicode

Những dấu câu như dấu chấm, dấu hỏi và viết tắt tiếng Việt có thể khiến cách tách câu thay đổi khi chạy `javadoc` với locale khác. Khi xây thư viện công khai nhiều ngôn ngữ, nên kiểm rõ summary trong HTML, không chỉ dựa vào độ dài text.

Với tài liệu tiếng Việt, dùng `-encoding UTF-8` để đọc file nguồn chính xác và cấu hình encoding HTML phù hợp; nếu source đã bị giải mã sai, `{@summary}` không tự chữa dấu tiếng Việt.

### 8.4. HTML và inline code

~~~java
/**
 * {@summary Trả về nhãn văn bản cho trạng thái.}
 * Nhãn được lưu dưới dạng {@code String}.
 * Xem thêm {@link java.lang.String}.
 */
public String status() {
    return "READY";
}
~~~

`{@code}` và `{@link}` được render theo ngữ nghĩa riêng, không thay vai trò của `{@summary}`. Khi cần nhiều đoạn HTML, đặt summary trước các đoạn chi tiết.

### 8.5. Markdown documentation comments trên JDK mới

**JDK 23** giới thiệu Markdown documentation comments (JEP 467), dạng comment với tiền tố `///`. Những comment này có quy tắc riêng cho text blocks, code spans và ranh giới câu đầu.

**Không dùng cú pháp Markdown comment `///` của JDK 23 như ví dụ bắt buộc trên Java 17.** Bài này dùng truyền thống `/** ... */`, hợp với mục tiêu học tính năng JDK 10 và chạy được trên Java 17+.

Nếu một dự án chọn JDK 23+ và dùng comment Markdown, hãy đọc đúng phiên bản Documentation Comment Specification về cách xử lý inline tags và first sentence, tránh áp máy móc quy tắc HTML cũ.

## 9. Không nhầm {@summary} với các thẻ khác

### 9.1. Summary và @return

~~~java
/**
 * {@summary Chọn nhãn theo giá trị cờ boolean.}
 * Phương thức luôn trả một trong hai chuỗi.
 *
 * @param ready trạng thái sẵn sàng
 * @return READY nếu ready, ngược lại WAIT
 */
public String label(boolean ready) {
    return ready ? "READY" : "WAIT";
}
~~~

Summary mô tả **hành vi chung**. `@return` diễn đạt **giá trị trả về**. Một thẻ không thay thế cho thẻ còn lại.

### 9.2. Summary và inline {@return}

Các JDK hiện đại còn có thẻ inline `{@return description}` với ngữ nghĩa gắn mô tả trả về cho method và quy tắc vị trí ở **đầu main description**. Nó khác `{@summary}`.

Nếu muốn một summary cụ thể và tài liệu trả về, cách dễ đọc và dễ bảo trì là đặt `{@summary ...}` ở đầu, dùng `@return` block ở cuối như ví dụ trên. Đừng đặt nhiều thẻ có yêu cầu cùng là phần tử đầu tiên rồi suy đoán doclet sẽ ưu tiên theo ý mình.

### 9.3. Summary và @since

`@since` nói về **phiên bản API** mà một declaration được giới thiệu trong dự án/thư viện. `{@summary}` nói về **đoạn mô tả ngắn**. Việc thẻ summary được giới thiệu từ JDK 10 **không** làm mọi method sử dụng thẻ này có `@since 10`.

### 9.4. Summary và deprecation

Một API được đánh dấu deprecated cần thông báo chính xác tình trạng và hướng di chuyển. Việc chọn summary tường minh không thay `@Deprecated`, `@deprecated` và tài liệu API thay thế khi những yếu tố này cần được cung cấp. Đừng dùng tag summary để che một điều kiện quan trọng về việc ngừng hỗ trợ.

### 9.5. Summary và inheritDoc

`{@inheritDoc}` kế thừa documentation trong những trường hợp được quy tắc Javadoc hỗ trợ. Khi override API mà không thay hợp đồng, cần cân nhắc kế thừa tài liệu thay vì viết một câu summary mới mâu thuẫn với superclass/interface.

Tính năng `{@summary}` **không** tự đồng bộ các mô tả giữa các declarations có liên quan; code review vẫn phải kiểm sự nhất quán của API documentation.

## 10. Chẩn đoán khi HTML sinh ra không như mong đợi

### 10.1. Kiểm đúng file và đúng lệnh

Chạy:

~~~bash
java -version
javadoc -help
~~~

Xác nhận `javadoc` là từ JDK có hỗ trợ `{@summary}` (JDK 10+). Với project có nhiều JDK, `java`, `javac` và `javadoc` có thể trỏ đến các JDK khác nhau tùy PATH/JAVA_HOME.

Kiểm file nguồn được đưa đúng vào `javadoc` và xuất đúng thư mục. Nếu có `package`, file HTML thuộc thư mục tương ứng, không luôn nằm ngay dưới `docs/`.

### 10.2. Kiểm tag ở đầu main description

Tự hỏi:

1. Có `/** ... */` và nó thực sự gắn với declaration cần document không?
2. Có text/HTML/link nào đứng **trước** `{@summary}` không?
3. Tag có đúng cặp `{@ ... }` và có nội dung meaningful không?
4. Có đặt tag bên trong `@param` hoặc `@return` không?
5. Dòng đầu được render đúng tiếng Việt/encoding chưa?
6. Có một comment khác đang được dùng do code generation hoặc source path không?

### 10.3. Kiểm visibility và loại phần tử

`javadoc` chỉ sinh tài liệu cho những declarations thuộc phạm vi visibility được cấu hình. Một member private có thể không xuất hiện trong bảng mặc định.

Trước khi kết luận “summary không hoạt động”, hãy xem method có được document không, lệnh có chọn đúng package/module không, và các tùy chọn visibility phù hợp không.

### 10.4. Doclint và chất lượng nội dung

~~~bash
javadoc -Xdoclint:all -encoding UTF-8 \
  -docencoding UTF-8 -charset UTF-8 \
  -d docs JavadocSummaryGuide.java
~~~

`-Xdoclint:all` hữu ích để phát hiện một số lỗi syntax, HTML, references và thiếu tài liệu theo khả năng công cụ. Nhưng một summary có thể **đúng cú pháp mà mô tả sai behavior**. Vẫn cần review nội dung và kiểm HTML.

### 10.5. Tránh test quá phụ thuộc HTML internals

Cấu trúc HTML, CSS classes, id/anchors và thông báo của doclet có thể thay đổi giữa JDK 17, 21, 25 hoặc 26. Hãy kiểm:

- Có trang tài liệu cho class.
- Method Summary thực sự mang câu người viết muốn.
- Method Details giữ mô tả dài và block tags.
- Không có broken links hoặc phần tử HTML sai.
- Có document đúng overload và class package.

Không kiểm bằng cách so byte-for-byte toàn bộ `JavadocSummaryGuide.html` giữa các JDK khác nhau.

### 10.6. Không đồng nhất compile success với doc success

`javac` biên dịch code thành class files; `javadoc` dùng documentation comments để sinh tài liệu. Thẻ `{@summary}` **không** tạo annotation runtime và **không** thay class/method signatures, bytecode hoặc exceptions.

Lệnh `javac` thành công **không đủ để xác nhận** vị trí summary trong output Javadoc. CI chất lượng nên có **cả bài kiểm code và bài kiểm tài liệu**.

## 11. Nguyên tắc viết summary chất lượng

### 11.1. Trả lời “API làm gì?” trong một câu

Yếu:

~~~java
/**
 * {@summary Thực hiện phương thức getStatus.}
 */
public String getStatus() {
    return "OK";
}
~~~

Tốt hơn:

~~~java
/**
 * {@summary Trả về trạng thái hiện tại của tác vụ.}
 * Kết quả là OK nếu tác vụ đã hoàn thành.
 */
public String getStatus() {
    return "OK";
}
~~~

Summary nên thêm **ngữ nghĩa có ích**, không chỉ lặp tên method.

### 11.2. Đúng mức khẳng định

Đừng viết “luôn hoàn tất trong 1 ms” khi method không có hợp đồng thời gian được xác minh. Tránh các từ tuyệt đối không được bảo đảm như “không bao giờ lỗi”, “luôn thread-safe” hoặc “không cần cấu hình” nếu code/contract không hỗ trợ.

### 11.3. Không đưa toàn bộ chi tiết triển khai vào summary

Một summary viết “dùng HashMap” sẽ nhanh lỗi thời nếu implementation chuyển qua cấu trúc khác, trong khi API vẫn có hành vi như cũ. Hãy mô tả **contract công khai**, phần implementation details đặt ở đoạn mô tả dài nếu cần.

### 11.4. Giữ nhất quán giữa các thành viên

Trong một API lớn có các method `find`, `read`, `load`, `parse`, hãy dùng động từ nhất quán và chỉ rõ chúng khác nhau ở dữ liệu/điều kiện nào. Bảng summary càng quan trọng khi hàng chục methods có tên gần giống nhau.

### 11.5. Không tạo summary chỉ để đủ chỉ tiêu

Nếu câu đầu tự nhiên đã là mô tả ngắn chính xác, không cần gắn tag riêng một cách máy móc. Lý do sử dụng `{@summary}` là **tăng khả năng kiểm soát và độ rõ**, không phải vì coi cơ chế suy câu đầu đã legacy.

## 12. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Viết `@summary` | Cú pháp thẻ tường minh chuẩn là inline | Dùng `{@summary ...}` |
| Đặt thẻ sau câu đầu | Không ở đầu main description | Đưa lên đầu |
| Đặt thẻ trong `@param` | Sai khu vực chọn summary | Đặt trước block tags |
| Đặt thẻ trong `//` | Không phải Javadoc comment | Dùng `/** ... */` |
| Bắt buộc dùng tag trên mọi API | Suy từ câu đầu vẫn hợp lệ | Dùng tag khi thật sự cần |
| Coi tag thay mọi docs | Không giải thích tham số/ngoại lệ | Dùng `@param`, `@return`, `@throws` |
| Chọn câu quá dài | Bảng summary khó đọc | Chọn câu một ý |
| Cắt luôn ở dấu chấm đầu tiên | Có viết tắt/version/URL | Dùng doclet hoặc summary rõ |
| Tưởng `-breakiterator` luôn sửa mọi lỗi | Thuật toán vẫn có giới hạn | Kiểm output/locale |
| Chỉ tìm text tag trong HTML | Tag đặt sai cũng có thể render | Kiểm Method Summary |
| Chỉ chạy `javac` | Chưa kiểm tài liệu HTML | Chạy `javadoc` |
| Nhầm tag với annotation | Không tạo metadata runtime | Phân biệt docs với code |
| Cho rằng tag chỉ có ở JDK 10 | JDK hiện đại vẫn hỗ trợ | Dùng JDK 17+ |
| Dùng `///` trên Java 17 | Markdown doc comments có từ JDK 23 | Dùng `/** ... */` |
| Sao chép warning javadoc làm output chuẩn | JDK/locale thay đổi | Kiểm file HTML |
| Thẻ tường minh chứa thông tin sai | Tool không kiểm được mọi ngữ nghĩa | Review contract/API |
| Gắn `@since 10` vô điều kiện | @since nói về phiên bản API | Theo version của thư viện |
| Bỏ mô tả chi tiết | Tóm tắt không đủ diễn đạt contract phức tạp | Thêm details đúng chỗ |
| Trộn inline `{@return}` và `{@summary}` mù quáng | Có quy tắc vị trí riêng | Dùng `@return` block nếu cần |
| Không chọn đúng javadoc toolchain | Có thể tạo docs bằng JDK khác | Kiểm `javadoc -help`/PATH |

## 13. Checklist trước khi xuất bản API documentation

### Trước khi chạy công cụ

- [ ] Đã xác định class/method nào thực sự public/protected cần document.
- [ ] Mỗi API có main description đủ nghĩa.
- [ ] Nếu không có `{@summary}`, câu đầu rõ và ngắn.
- [ ] Nếu có `{@summary}`, đó là nội dung có ý nghĩa đầu tiên trong main description.
- [ ] Không nhầm `@summary` với `{@summary ...}`.
- [ ] Không đặt summary trong `@param`/`@return`.
- [ ] Nội dung tóm tắt phản ánh đúng behavior, không hứa sai.
- [ ] Các docs cho parameters/return/throws được viết riêng.
- [ ] Source encoding phù hợp nội dung tiếng Việt.
- [ ] Không thêm JDK-specific syntax ngoài target source level.

### Sau khi sinh tài liệu

- [ ] Chạy đúng `javadoc` của toolchain được chọn.
- [ ] Lệnh `javadoc -Xdoclint:all` hoạt động theo cấu hình dự án.
- [ ] Trang HTML chứa đúng class/methods cần xuất bản.
- [ ] Summary có text đúng dự kiến.
- [ ] Method Details vẫn đầy đủ mô tả và tags.
- [ ] Dấu chấm trong viết tắt/định dạng phiên bản không làm summary sai.
- [ ] Không có lỗi link, HTML hoặc cảnh báo quan trọng.
- [ ] Không lấy toàn bộ HTML/CSS làm snapshot cứng giữa nhiều JDK.
- [ ] Có code tests độc lập với documentation tests.
- [ ] Đã đọc lại nội dung API ở góc nhìn người dùng thư viện.

### Câu hỏi tự kiểm tra

**Câu 1.** Nếu không có thẻ `{@summary}`, standard doclet lấy summary từ đâu?

**Đáp án:** Câu đầu của main description, xác định bằng quy tắc tách câu tương ứng.

**Câu 2.** Thẻ `{@summary ...}` xuất hiện từ JDK nào?

**Đáp án:** JDK 10 và vẫn được hỗ trợ trên JDK hiện đại.

**Câu 3.** Tag phải đặt ở đâu để chọn summary tường minh?

**Đáp án:** Ngay đầu main description, trước những câu giải thích và các block tags.

**Câu 4.** Nếu thẻ đặt sau câu đầu, text có thể được render không?

**Đáp án:** Có, nhưng việc render text không đồng nghĩa thẻ được dùng để chọn summary.

**Câu 5.** Có thể viết `@summary` ở đầu dòng không?

**Đáp án:** Không dùng nó thay `{@summary ...}`, vì syntax chuẩn của summary là inline tag.

**Câu 6.** Vì sao tên `v2.1` khiến mô hình “dấu chấm đầu tiên” sai?

**Đáp án:** Dấu chấm giữa các chữ số không kết thúc câu, nhưng regex đơn giản sẽ hiểu nhầm.

**Câu 7.** `-breakiterator` có thay đổi hành vi runtime của Java không?

**Đáp án:** Không, đây là option của công cụ sinh tài liệu.

**Câu 8.** `{@summary}` có thay thế `@param` và `@return` không?

**Đáp án:** Không, summary mô tả ngắn API; các block tags mô tả chi tiết contract.

**Câu 9.** `javac` thành công có chứng minh summary HTML đúng không?

**Đáp án:** Không. Phải sinh tài liệu bằng `javadoc` và quan sát phần Summary.

**Câu 10.** Có bắt buộc sử dụng tag cho mọi API để tránh legacy không?

**Đáp án:** Không. Cơ chế suy từ câu đầu vẫn hợp lệ và hiện được hỗ trợ.

**Câu 11.** JDK 17 có hỗ trợ thẻ `{@summary}` không?

**Đáp án:** Có, Oracle Java SE 17 Documentation Comment Specification mô tả rõ.

**Câu 12.** JDK 17 có thể dùng comment `///` theo chuẩn Javadoc Markdown mới không?

**Đáp án:** Không. Dạng Markdown documentation comments đó được đưa vào từ JDK 23; ví dụ này dùng `/** ... */`.

## 14. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html): `{@summary}` chỉ có ý nghĩa chọn summary khi nằm đầu main description, nội dung tag luôn được render.
- [Oracle Java SE 25 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): main description, block/inline tags, first sentence và summary.
- [Oracle Java SE 17 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): xác nhận thẻ vẫn hợp lệ trong Java 17.
- [Oracle JDK 10 Release Notes — Comment Tag for Summary of an API Description](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): JDK-8173425, lý do thêm tag để tránh heuristic xác định câu đầu sai.
- [Oracle Java SE 25 — The javadoc Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): `-breakiterator`, encoding, options của standard doclet.
- [Oracle Java SE 17 — The javadoc Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): sinh HTML và doclint trên JDK 17.
- [Oracle Java SE 17 — The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release 17` cho ví dụ runnable.
- [OpenJDK JDK-8173425 — Javadoc needs a new tag to specify the summary](https://bugs.openjdk.org/browse/JDK-8173425): vấn đề gốc của cải tiến JDK 10.
- [OpenJDK JEP 467 — Markdown Documentation Comments](https://openjdk.org/jeps/467): hỗ trợ Markdown documentation comments từ JDK 23.

**Ghi nhớ:** nếu không có `{@summary}`, Javadoc thường lấy **câu đầu** của main description và có thể gặp lỗi do tách câu/locale. Từ **JDK 10**, đặt **`{@summary text}` ngay đầu main description** cho phép chọn **tóm tắt tường minh**; thẻ vẫn còn được hỗ trợ trong Java 17/25/26. Để kiểm đúng, cần chạy **`javadoc` và xem Summary trong HTML**, không chỉ biên dịch mã Java.