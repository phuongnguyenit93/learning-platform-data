# Chú thích một dòng, nhiều dòng và chú thích tài liệu trong Java

## 1. Ba dạng chú thích cần phân biệt

Chú thích (*comment*) là phần văn bản dành cho người đọc mã nguồn. Trong Java 17+, bạn sẽ gặp ba dạng chính:

| Dạng | Cú pháp | Phạm vi | Mục đích thường gặp |
|---|---|---|---|
| Chú thích một dòng | `// nội dung` | Từ `//` tới hết dòng | Giải thích một quyết định ngắn, cảnh báo một trường hợp |
| Chú thích khối | `/* nội dung */` | Từ `/*` đến `*/`, có thể qua nhiều dòng | Diễn giải ngắn nhiều dòng, ghi chú nội bộ |
| Chú thích tài liệu | `/** nội dung */` | Một khối đặc biệt được công cụ Javadoc nhận diện | Mô tả API: lớp, phương thức, tham số, giá trị trả về, ngoại lệ |

Trong chương trình Java thông thường, **nội dung chú thích không phải câu lệnh để JVM thực thi**. Trình biên dịch xử lý các dấu chú thích khi phân tích mã nguồn; nội dung của chúng không trở thành logic chạy của chương trình. Công cụ **`javadoc`** có thể đọc chú thích tài liệu để sinh trang HTML.

Ví dụ phân biệt trực quan:

~~~java
int price = 100; // Giải thích ngay sau câu lệnh

/* Đây là chú thích khối
   trải qua nhiều dòng. */

/**
 * Đây là chú thích tài liệu.
 * Thường đặt trước khai báo cần được mô tả.
 */
class Product {
}
~~~

**Quy tắc cốt lõi:** dùng chú thích để giải thích **tại sao** mã được viết như vậy, điều kiện hay cam kết của API; không cần diễn đạt lại mọi phép gán hoặc mọi dấu chấm phẩy mà mã đã thể hiện rõ.

## 2. Chú thích một dòng: `//`

Từ hai dấu gạch chéo liên tiếp ở ngoài chuỗi ký tự, phần còn lại của **dòng nguồn** được xem là chú thích.

~~~java
int minimumAge = 18;
int userAge = 17;

// Quy định nghiệp vụ: người dưới 18 tuổi không được đăng ký.
boolean eligible = userAge >= minimumAge;
System.out.println(eligible); // false
~~~

Nếu một dòng có lệnh trước `//`, lệnh **vẫn được thực hiện**; chỉ phần sau dấu `//` là chú thích. Hai cách sử dụng phù hợp:

- Đặt chú thích ở **dòng riêng phía trên** đoạn xử lý khi cần lý giải một quy tắc.
- Đặt chú thích **cuối dòng** khi thực sự ngắn và không làm mã khó đọc.

Ví dụ không nên viết chú thích dư thừa:

~~~java
int total = 10; // Gán giá trị 10 cho total
~~~

Giá trị đã rõ từ code. Thông tin hữu ích hơn có thể là lý do dùng 10, điều kiện của bài toán hoặc đơn vị tính.

**Chú thích `//` không kéo dài sang dòng tiếp theo**:

~~~java
int a = 1; // chỉ dòng này
int b = 2; // câu lệnh dòng sau vẫn hoạt động
~~~

## 3. Chú thích nhiều dòng: `/* ... */`

Chú thích khối bắt đầu ở `/*` và kết thúc tại **cặp `*/` đầu tiên** tương ứng theo quá trình phân tích ký tự của Java. Nó có thể nằm cùng dòng hoặc trải qua nhiều dòng.

~~~java
/*
 * Công thức demo:
 * thành tiền = số lượng × đơn giá.
 * Dữ liệu đều là số nguyên không âm.
 */
int quantity = 3;
long unitPrice = 120_000L;
long subtotal = unitPrice * quantity;
System.out.println(subtotal); // 360000
~~~

Chú thích khối cũng có thể đặt xen giữa một số token khi cú pháp cho phép:

~~~java
int result = 2 /* giữ phép nhân minh họa */ * 3;
System.out.println(result); // 6
~~~

Dùng kiểu xen giữa biểu thức quá thường xuyên sẽ làm code khó đọc. Thực tế, chú thích khối thường đặt thành một đoạn riêng.

### Chú thích khối **không lồng nhau**

Đây là lỗi dễ gặp:

~~~java
/* Khối ngoài
   /* Khối trong */
   phần còn lại ở đây không phải chú thích
*/
~~~

`*/` đầu tiên kết thúc khối ngoài. Phần chữ còn lại sẽ bị Java xem như mã nguồn và có thể gây lỗi biên dịch. Java **không hỗ trợ chú thích khối lồng nhau**. Khi cần hai đoạn giải thích độc lập, dùng hai khối riêng hoặc các dòng `//`.

Một khối thiếu `*/` cũng gây lỗi biên dịch, chẳng hạn thông báo về *unclosed comment*. Nếu editor tô màu cả phần còn lại của tệp như chú thích, hãy kiểm tra dấu đóng.

## 4. Chú thích tài liệu: `/** ... */`

**Javadoc comment** có cú pháp bắt đầu bằng `/**` và kết thúc bằng `*/`. Nội dung bên trong thường mô tả **khai báo đứng ngay sau chú thích**, ví dụ public class hoặc public method.

~~~java
/**
 * Các phép tính đơn giản dùng trong ví dụ.
 */
public class Calculator {

    /**
     * Cộng hai số nguyên và phát hiện tràn số.
     *
     * @param a số hạng thứ nhất
     * @param b số hạng thứ hai
     * @return tổng của a và b
     * @throws ArithmeticException nếu phép cộng vượt miền int
     */
    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

Phần mở đầu là **mô tả**. Các dòng bắt đầu bằng `@` trong chú thích tài liệu là **block tags của Javadoc**, ví dụ `@param`, `@return`, `@throws`.

Dấu `*` ở đầu mỗi dòng nội dung là **kiểu trình bày quen thuộc**, không phải phép nhân Java; `javadoc` hiểu cấu trúc của khối chú thích tài liệu.

### Các tag thường dùng

| Tag | Ý nghĩa | Khi nên dùng |
|---|---|---|
| `@param name` | Ý nghĩa một tham số; `name` phải khớp tên tham số | Method/constructor có tham số |
| `@return` | Giá trị/kết quả trả về | Method trả giá trị, không dùng để mô tả kết quả của method `void` |
| `@throws Type` | Điều kiện có thể phát sinh exception | API có hành vi lỗi cần giải thích |
| `@since` | Phiên bản kể từ khi API tồn tại | API ổn định hoặc thư viện phát hành phiên bản |
| `@see` | Tham chiếu tài liệu liên quan | Người đọc cần xem thêm type/method khác |
| `@deprecated` | Giải thích API không nên tiếp tục dùng | Thường kết hợp annotation `@Deprecated` |
| `{@code ...}` | Hiển thị đoạn code trong phần mô tả | Ví dụ `{@code count > 0}` |
| `{@link Type}` | Tạo liên kết tới phần tử tài liệu được nhận diện | Khi dẫn tới API liên quan |

Hai dạng có dấu `{@...}` là **inline tags**, có thể xuất hiện giữa câu; `@param` và `@return` là **block tags**, thường mỗi tag bắt đầu ở một dòng riêng trong Javadoc comment.

**Chú thích tài liệu không phải annotation.** `@Deprecated` đặt **trong mã** là annotation; `@deprecated` nằm **trong Javadoc** là tag mô tả. Chỉ thêm văn bản `@deprecated` vào Javadoc không tự thay thế mọi tác dụng của annotation `@Deprecated`.

## 5. Ví dụ Java 17 hoàn chỉnh: code, comment và Javadoc

Tạo tệp đúng tên **`CommentDemo.java`**, lưu bằng UTF-8:

~~~java
/**
 * Minh họa ba dạng chú thích trong Java.
 *
 * <p>Ví dụ tính tiền hàng nguyên đơn vị đồng.
 *
 * @since 1.0
 */
public final class CommentDemo {
    private CommentDemo() {
        // Không tạo instance của class chỉ chứa tiện ích.
    }

    /**
     * Tính tiền hàng bằng phép nhân kiểm tra tràn số.
     *
     * @param quantity số lượng, phải không âm
     * @param unitPrice đơn giá nguyên đồng, phải không âm
     * @return thành tiền theo đơn vị đồng
     * @throws IllegalArgumentException nếu đầu vào âm
     * @throws ArithmeticException nếu phép nhân tràn long
     */
    public static long total(int quantity, long unitPrice) {
        if (quantity < 0 || unitPrice < 0) {
            throw new IllegalArgumentException("Gia tri am");
        }

        /*
         * Dùng multiplyExact để không âm thầm trả về
         * một số tiền sai do tràn số nguyên.
         */
        return Math.multiplyExact((long) quantity, unitPrice);
    }

    /**
     * Điểm vào chương trình.
     *
     * @param args đối số dòng lệnh; demo không sử dụng
     */
    public static void main(String[] args) {
        long result = total(3, 120_000L);
        System.out.println("Tong: " + result); // 360000

        // Những dấu giống comment trong chuỗi vẫn là nội dung chuỗi.
        String url = "https://example.com/items";
        String marker = "/* khong phai comment */";
        System.out.println("URL: " + url);
        System.out.println("Marker: " + marker);
    }
}
~~~

### Biên dịch và chạy trên JDK 17+

Mở terminal tại thư mục chứa `CommentDemo.java`.

**Bash (Linux/macOS):**

~~~bash
javac -version
javac --release 17 -encoding UTF-8 CommentDemo.java
java -cp . CommentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac -version
javac --release 17 -encoding UTF-8 .\CommentDemo.java
java -cp . CommentDemo
~~~

Kết quả của lệnh `java`:

~~~text
Tong: 360000
URL: https://example.com/items
Marker: /* khong phai comment */
~~~

Chú thích một dòng, khối và Javadoc comment **không được in**. Những ký tự `//`, `/*` và `*/` trong **string literal** được in như ký tự thông thường vì chúng nằm trong chuỗi.

**Điều cần nhận ra:** chú thích giải thích ý định dùng `Math.multiplyExact`, nhưng chính **lệnh gọi method** mới phát hiện tràn số. Viết chú thích “đã xử lý tràn số” mà code chỉ nhân bằng `*` thông thường sẽ không khiến chương trình an toàn hơn.

## 6. Sinh tài liệu HTML bằng công cụ javadoc

JDK không chỉ có `javac` và `java` mà còn có **`javadoc`**. Đây là công cụ đọc chú thích tài liệu và thông tin khai báo để sinh trang API.

Từ thư mục chứa file mẫu, chạy:

**Bash:**

~~~bash
javadoc -quiet -encoding UTF-8 -docencoding UTF-8 \
  -charset UTF-8 -d docs CommentDemo.java
~~~

**PowerShell (một dòng):**

~~~powershell
javadoc -quiet -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -d docs .\CommentDemo.java
~~~

Thư mục **`docs`** được tạo để lưu HTML. Với class public ở default package như ví dụ, tệp tài liệu của class thường là:

~~~text
docs/CommentDemo.html
~~~

Có thể kiểm tra tệp:

**Bash:**

~~~bash
ls docs/CommentDemo.html
~~~

**PowerShell:**

~~~powershell
Test-Path .\docs\CommentDemo.html
~~~

`Test-Path` trả **`True`** nếu tệp tồn tại. Bạn có thể mở tệp HTML bằng trình duyệt để xem mô tả class, method `total`, các tham số, giá trị trả về và các ngoại lệ được ghi trong Javadoc.

**Không nên cam kết nguyên văn đầu ra của lệnh `javadoc`**, vì số dòng thông báo, cảnh báo DocLint và danh sách file tạo ra có thể khác theo JDK/tùy chọn. Tiêu chí kiểm tra chính là lệnh kết thúc thành công và tài liệu HTML được sinh đúng.

Nếu tài liệu public API không chứa một method hoặc field, kiểm tra **mức hiển thị** của phần tử và các tùy chọn của `javadoc`. Mặc định công cụ không nhất thiết liệt kê mọi thành viên private. Có thể dùng `javadoc -private ...` nếu bạn thật sự cần tài liệu cho các thành viên private trong mục đích nội bộ.

## 7. Chú thích ở đúng vị trí và đúng mục tiêu

### Chú thích tài liệu cho API; chú thích thường cho giải thích cục bộ

Chú thích tài liệu nên đặt **ngay trước khai báo cần mô tả**:

~~~java
/**
 * Tính diện tích hình chữ nhật.
 *
 * @param width chiều rộng không âm
 * @param height chiều cao không âm
 * @return diện tích theo đơn vị bình phương
 */
static long area(long width, long height) {
    if (width < 0 || height < 0) {
        throw new IllegalArgumentException("Negative size");
    }
    return Math.multiplyExact(width, height);
}
~~~

Nếu đoạn code chỉ cần giải thích một quyết định cục bộ, ví dụ lý do dùng một thuật toán hoặc giới hạn hiệu năng, `//` hay `/* ... */` thường hợp lý hơn.

**Javadoc không tự thực thi hợp đồng.** `@param width chiều rộng không âm` không làm JVM từ chối số âm; phương thức cần có validation phù hợp hoặc bên gọi phải bảo đảm tiền điều kiện theo thiết kế. Tài liệu phải **khớp với hành vi thật**.

### Mô tả *vì sao*, không sao chép *cái gì*

Ít hữu ích:

~~~java
quantity++; // Tăng quantity thêm 1.
~~~

Hữu ích hơn nếu có quy tắc rõ ràng:

~~~java
// Chỉ tăng sau khi kiểm tra còn đủ hàng trong kho.
quantity++;
~~~

Ví dụ trên vẫn cần **có code kiểm tra kho thực sự** ở nơi phù hợp; chú thích không thay cho thực thi quy tắc.

## 8. Những bẫy từ vựng liên quan đến dấu comment

### 8.1. Comment marker trong string/char/text block không phải comment

~~~java
String website = "https://example.org";  // Có // bên trong chuỗi
String marker = "/* sample */";          // Có /* */ bên trong chuỗi
char slash = '/';
~~~

Nội dung bên trong string literal hoặc character literal được nhận diện là **ký tự của literal**, không phải dấu mở chú thích. Với **text block** (`"""`) của Java 17, nguyên tắc tương tự: các dấu `//` hoặc `/* ... */` nằm trong nội dung của text block không tự tạo chú thích.

### 8.2. Đừng dựa vào comment để "vô hiệu hóa" mã lâu dài

Đoạn:

~~~java
// sendEmail(customer);
~~~

có thể hữu ích khi thử nghiệm ngắn, nhưng giữ mã đã bị comment lâu dài làm chương trình khó đọc và mơ hồ về chức năng. Tốt hơn là xóa mã không còn dùng (version control lưu lịch sử), hoặc dùng điều kiện/cấu hình rõ ràng nếu hành vi thực sự cần bật/tắt.

### 8.3. Chú ý Unicode escape trong Java source

Java xử lý **Unicode escapes** ở một giai đoạn rất sớm của quá trình đọc nguồn, **trước khi xác định comment và string literal** theo từ vựng. Vì vậy các chuỗi ký tự thoạt nhìn giống comment có chứa dạng escape đặc biệt có thể không được phân tích như bạn đoán. Đừng dựa vào comment để che giấu các Unicode escapes mang ý nghĩa cú pháp; nếu nghi ngờ, kiểm tra mã nguồn thực tế và thử biên dịch bằng đúng JDK mục tiêu.

### 8.4. Comment có thể che lỗi khi xóa/mở rộng code

Một dấu `/*` bị bỏ sót dấu kết thúc có thể khiến nhiều dòng mã sau đó nằm trong comment hoặc tạo lỗi `unclosed comment`. Một dấu `*/` thừa ngoài comment thường làm mã lỗi cú pháp. Hãy nhìn highlight của editor và kiểm tra các cặp dấu.

## 9. Javadoc: những lỗi viết tài liệu hay gặp

| Vấn đề | Vì sao không tốt? | Cách khắc phục |
|---|---|---|
| Viết `@param name` nhưng method có tham số `userName` | Tag không khớp khai báo | Dùng đúng tên tham số |
| Method trả `int` nhưng mô tả `@return` sai đơn vị | Người gọi API dễ hiểu sai | Nêu kết quả và đơn vị chính xác |
| Method có thể ném exception nhưng tài liệu không nói điều kiện | Khó dùng API an toàn | Bổ sung `@throws` với điều kiện cụ thể |
| Viết ký tự `<` trực tiếp trong đoạn tài liệu muốn hiển thị như code | Có thể bị hiểu là markup HTML | Dùng `{@code x < 10}` hoặc escape thích hợp |
| Chỉ ghi `/** TODO */` cho mọi method | Không mô tả hợp đồng thực sự | Viết nội dung hữu ích hoặc bỏ comment không cần thiết |
| Đổi chữ ký method nhưng không cập nhật Javadoc | Tài liệu lỗi thời, có thể có cảnh báo | Sửa tag và ví dụ cùng lúc |
| Xem Javadoc như cơ chế validation | Comment không được chạy | Viết check trong code và test |

**Không nhầm** cú pháp `/** ... */` với `/* ... */`: cả hai đều là khối comment, nhưng `/**` đặt trước khai báo được công cụ Javadoc xử lý như tài liệu API. Một đoạn comment Javadoc không có khai báo phù hợp ngay sau không thay thế cho việc gắn tài liệu vào thành phần mong muốn.

## 10. Thực hành phân biệt ba loại

Xét đoạn mã:

~~~java
/**
 * Chuyển một độ dài từ mét sang centimet.
 *
 * @param meters số mét không âm
 * @return số centimet
 * @throws IllegalArgumentException nếu đầu vào âm
 */
static long toCentimeters(long meters) {
    if (meters < 0) {
        throw new IllegalArgumentException("Negative meters");
    }
    // 1 mét = 100 centimet.
    return Math.multiplyExact(meters, 100L);
}

/* Dùng trong ví dụ chạy đơn giản:
   toCentimeters(3) => 300 */
~~~

Tự trả lời:

1. Đoạn nào là chú thích một dòng?
2. Đoạn nào tạo nội dung tài liệu cho method?
3. Đoạn nào là chú thích khối thông thường?
4. Khi gọi `toCentimeters(3)`, các comment có được in ra không?

**Đáp án:** dòng `// 1 mét...` là chú thích một dòng; khối `/** ... */` là Javadoc của `toCentimeters`; khối `/* Dùng ... */` là chú thích khối thông thường. Không comment nào được in bởi lời gọi method; kết quả method là số `300`.

## 11. Bài tập có đáp án

### Bài A — chọn đúng kiểu chú thích

Bạn muốn ghi một giải thích ngắn cho quy tắc ở dòng tiếp theo; muốn ghi ghi chú nội bộ nhiều dòng; và muốn công khai hợp đồng của một method có hai tham số.

**Đáp án:** lần lượt dùng `//`, `/* ... */`, và `/** ... */` với `@param`, `@return` (nếu trả giá trị), `@throws` (khi cần).

### Bài B — sửa comment chưa đóng

Đoạn:

~~~java
int a = 1;
/* giai thich
int b = 2;
~~~

**Đáp án:** thêm `*/` vào điểm kết thúc đúng của comment. Nếu `int b = 2;` cần được thực thi, đặt nó **sau** `*/`.

### Bài C — dự đoán đầu ra

~~~java
int x = 3 /* vẫn đang trong phép tính */ + 2;
String s = "http://localhost";
System.out.println(x);
System.out.println(s);
~~~

**Đáp án:**

~~~text
5
http://localhost
~~~

`/* ... */` không làm mất toán tử `+` ở ngoài comment; `//` trong chuỗi URL không mở chú thích.

### Bài D — viết Javadoc đủ hợp đồng

Cho:

~~~java
static int divide(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("Zero denominator");
    }
    return numerator / denominator;
}
~~~

Hãy viết chú thích tài liệu nêu hai tham số, kết quả và điều kiện lỗi.

**Đáp án gợi ý:**

~~~java
/**
 * Chia hai số nguyên theo quy tắc chia nguyên của Java.
 *
 * @param numerator số bị chia
 * @param denominator số chia, phải khác 0
 * @return thương nguyên, làm tròn về 0
 * @throws IllegalArgumentException nếu denominator bằng 0
 */
~~~

Lưu ý: phép chia `Integer.MIN_VALUE / -1` là trường hợp đặc biệt có kết quả `Integer.MIN_VALUE` theo quy tắc tràn int; tài liệu chi tiết hơn nên nêu nếu hợp đồng ứng dụng yêu cầu xử lý khác.

### Bài E — tạo và kiểm tra HTML

Dùng file `CommentDemo.java` ở mục 5, chạy `javadoc`, rồi mở `docs/CommentDemo.html`. Tìm tài liệu của `total`, kiểm tra các mô tả `quantity`, `unitPrice`, `@return` và `@throws`.

**Đáp án kỳ vọng:** trang API có phần mô tả method và các mục Parameters/Returns/Throws tương ứng (cách trình bày thay đổi theo JDK). Nếu file không được tạo, kiểm tra kết quả lệnh, đường dẫn hiện hành và cảnh báo DocLint trước khi kết luận nội dung source sai.

## 12. Checklist tự đánh giá

- [ ] Nhận diện được ba cú pháp `//`, `/* ... */`, `/** ... */`.
- [ ] Hiểu `//` hết hiệu lực tại cuối dòng và comment khối phải đóng `*/`.
- [ ] Biết block comment **không lồng nhau**.
- [ ] Hiểu `//` và `/* ... */` bên trong chuỗi không trở thành comment.
- [ ] Biết Javadoc comment dùng cho tài liệu API, không phải câu lệnh thực thi.
- [ ] Viết được `@param`, `@return`, `@throws` theo chữ ký/hợp đồng method.
- [ ] Phân biệt tag Javadoc `@deprecated` với annotation `@Deprecated`.
- [ ] Biên dịch/chạy `CommentDemo.java` bằng `javac`/`java` và đối chiếu đầu ra.
- [ ] Dùng `javadoc -d docs` để sinh và xem tài liệu HTML.
- [ ] Viết chú thích giải thích quyết định, quy tắc và giới hạn, thay vì lặp lại điều mã đã nói.

**Kết luận:** `//` phù hợp cho chú thích ngắn; `/* ... */` cho chú thích khối; `/** ... */` cho tài liệu API sinh được bằng `javadoc`. Chú thích giúp người đọc hiểu mã nhưng **không tự thay đổi hành vi JVM**. Một comment tốt phải đúng với code hiện tại, rõ ràng về ý định và được cập nhật khi hành vi thay đổi.