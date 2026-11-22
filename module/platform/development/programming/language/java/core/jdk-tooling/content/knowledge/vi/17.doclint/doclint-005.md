# Bật DocLint trong Javadoc

**DocLint** là bộ kiểm tra tích hợp trong JDK, giúp phát hiện vấn đề trong documentation comment của Java trước hoặc trong khi tạo tài liệu API bằng Javadoc. DocLint kiểm tra các lỗi như thiếu mô tả, sai tên tham số, liên kết đến API không tồn tại, HTML không hợp lệ, ký tự đặc biệt chưa escape và một số vấn đề accessibility.

Bật DocLint giúp nhóm phát hiện lỗi tài liệu ngay trong quá trình build. Điều này đặc biệt hữu ích với thư viện và module có public API, nơi Javadoc là một phần của hợp đồng mà lập trình viên khác sử dụng.

Trong JDK 24, Javadoc đã bật DocLint mặc định cho các comment thuộc phạm vi tài liệu được tạo. Có thể bật rõ ràng bằng **-Xdoclint** hoặc yêu cầu tất cả nhóm kiểm tra bằng **-Xdoclint:all**. Khi muốn build thất bại nếu còn warning, kết hợp với **-Werror**.

## 1. DocLint là gì?

DocLint là bộ kiểm tra documentation comment được tích hợp trong công cụ **javadoc** và cũng có thể được gọi từ **javac**. Nó phân tích comment đặc biệt bắt đầu bằng /** và báo các vấn đề có thể khiến tài liệu sinh ra sai, thiếu hoặc khó truy cập.

DocLint tập trung vào chất lượng nội dung và markup của Javadoc. Nó không sửa comment, không tự tạo phần mô tả còn thiếu và cũng không thay thế một HTML conformance validator đầy đủ.

Các loại vấn đề thường được phát hiện:

- Thiếu documentation comment trên khai báo cần công khai.
- Thiếu tag như @param hoặc @return.
- Tên sau @param không khớp tham số thực tế.
- Reference trong @see hoặc {@link ...} không tìm thấy.
- HTML bị lồng sai, thiếu thẻ đóng hoặc có cấu trúc không hợp lệ.
- Ký tự <, > hoặc & được dùng sai trong comment.
- Hình ảnh thiếu thuộc tính alt hoặc bảng thiếu mô tả hỗ trợ accessibility.
- Tag Javadoc không hợp lệ hoặc dùng sai cú pháp.

### DocLint kiểm tra phần nào?

Khi chạy Javadoc, DocLint kiểm tra các documentation comment nằm trong phạm vi tài liệu mà Javadoc đang tạo. Vì vậy, các tùy chọn quyết định phần tử nào được đưa vào tài liệu cũng ảnh hưởng đến phạm vi kiểm tra.

Ví dụ, Javadoc mặc định hiển thị API public và protected. Nếu dùng -private, các thành viên private cũng được đưa vào tài liệu và comment tương ứng có thể được kiểm tra.

Các tùy chọn chọn phạm vi khai báo thường gặp:

| Tùy chọn Javadoc | Phạm vi |
|---|---|
| -public | Chỉ kiểu và thành viên public |
| -protected | Kiểu và thành viên public/protected; đây là mặc định |
| -package | Bao gồm package-private cùng public/protected |
| -private | Bao gồm tất cả thành viên, kể cả private |

DocLint không nhất thiết kiểm tra mọi comment trong repository. Nó kiểm tra comment thuộc các phần tử được đưa vào phạm vi xử lý, cùng những trường hợp đặc biệt mà standard doclet cần tài liệu hóa, chẳng hạn Serialized Form.

## 2. Bật DocLint bằng dòng lệnh

Có thể bật DocLint khi tạo HTML documentation bằng lệnh javadoc.

### Bật chế độ kiểm tra mặc định

~~~bash
javadoc -Xdoclint -d docs src/com/example/TextService.java
~~~

Tùy chọn -Xdoclint bật các kiểm tra được khuyến nghị. Với JDK 24, đây cũng là hành vi mặc định của Javadoc nếu không bị vô hiệu hóa bằng tùy chọn khác. Viết rõ tùy chọn trong build script giúp người đọc nhận biết mục tiêu kiểm tra.

### Bật tất cả nhóm kiểm tra

~~~bash
javadoc -Xdoclint:all -d docs src/com/example/TextService.java
~~~

-Xdoclint:all yêu cầu bật toàn bộ các nhóm kiểm tra:

- accessibility
- html
- missing
- reference
- syntax

Đây là cấu hình rõ ràng để kiểm tra toàn diện comment trước khi phát hành tài liệu API.

### Biến warning thành lỗi build

~~~bash
javadoc -Xdoclint:all -Werror -d docs src/com/example/TextService.java
~~~

-Werror yêu cầu Javadoc báo lỗi nếu có warning. Khi dùng trong CI, lệnh sẽ trả trạng thái thất bại nếu còn warning cần xử lý.

Cần phân biệt:

- **-Xdoclint:all** bật các nhóm kiểm tra.
- **-Werror** thay đổi cách xử lý warning thành lỗi.
- -Werror có thể áp dụng cho warning từ các phần khác của Javadoc, không chỉ riêng DocLint.

Nên bắt đầu bằng việc sửa các lỗi thật sự, sau đó mới bật -Werror để giữ chất lượng tài liệu ổn định.

### Tắt DocLint

~~~bash
javadoc -Xdoclint:none -d docs src/com/example/TextService.java
~~~

-Xdoclint:none tắt tất cả nhóm kiểm tra DocLint. Chỉ dùng khi có lý do cụ thể, chẳng hạn cần tạo tài liệu tạm thời từ nguồn cũ chưa thể sửa ngay. Không nên tắt kiểm tra như một cách che warning trong pipeline phát hành.

## 3. Năm nhóm kiểm tra của DocLint

DocLint chia các kiểm tra thành năm nhóm. Có thể bật từng nhóm để tập trung xử lý một loại vấn đề.

### accessibility — khả năng truy cập

Nhóm này phát hiện một số vấn đề có thể làm tài liệu khó sử dụng với công nghệ hỗ trợ.

Ví dụ:

- Thẻ img không có thuộc tính alt.
- Bảng thiếu caption hoặc mô tả phù hợp.
- Nội dung HTML không cung cấp thông tin cần thiết cho người đọc dùng trình đọc màn hình.

Ví dụ comment có vấn đề:

~~~java
/**
 * Sơ đồ kiến trúc:
 * <img src="architecture.png">
 */
public class Architecture {
}
~~~

Nên cung cấp mô tả thay thế:

~~~java
/**
 * Sơ đồ kiến trúc:
 * <img src="architecture.png" alt="Sơ đồ các module và quan hệ phụ thuộc">
 */
public class Architecture {
}
~~~

Alt nên mô tả ý nghĩa của hình trong ngữ cảnh. Nếu hình chỉ mang tính trang trí, hãy cân nhắc cách trình bày phù hợp để công nghệ hỗ trợ không đọc nội dung thừa.

### html — cấu trúc HTML

Nhóm html phát hiện các lỗi HTML phổ biến trong documentation comment, ví dụ:

- Đặt phần tử block bên trong phần tử inline không phù hợp.
- Thiếu thẻ đóng đối với phần tử cần thẻ đóng.
- Lồng các phần tử sai quy tắc.
- Dùng markup không hợp lệ khiến trình duyệt hiển thị khác dự kiến.

Ví dụ thiếu thẻ đóng:

~~~java
/**
 * <b>Quan trọng: đọc hướng dẫn trước khi gọi API.
 */
public void execute() {
}
~~~

Sửa thành:

~~~java
/**
 * <b>Quan trọng:</b> đọc hướng dẫn trước khi gọi API.
 */
public void execute() {
}
~~~

DocLint chỉ kiểm tra các lỗi phổ biến và cấu trúc mà nó hỗ trợ. Nó không phải bộ xác thực toàn bộ HTML Living Standard.

### missing — thiếu comment hoặc tag

Nhóm missing tìm những phần tài liệu còn thiếu, ví dụ:

- Class hoặc method cần tài liệu nhưng chưa có documentation comment.
- Method có tham số nhưng thiếu @param.
- Method có giá trị trả về nhưng thiếu @return.
- Một số thành phần tài liệu hóa cần thiết chưa được mô tả.

Ví dụ:

~~~java
/**
 * Tìm người dùng theo mã.
 *
 * @param id mã người dùng
 */
public User findUser(String id) {
    return null;
}
~~~

Method có giá trị trả về nhưng thiếu @return. Bổ sung:

~~~java
/**
 * Tìm người dùng theo mã.
 *
 * @param id mã người dùng
 * @return người dùng phù hợp, hoặc null nếu không tìm thấy
 */
public User findUser(String id) {
    return null;
}
~~~

Các vấn đề thuộc nhóm missing thường được báo dưới dạng warning vì chúng thường không làm HTML sinh ra sai cú pháp, nhưng vẫn làm tài liệu API thiếu thông tin.

### reference — tham chiếu không hợp lệ

Nhóm reference kiểm tra tên và liên kết đến các phần tử Java.

Ví dụ:

- {@link ...} trỏ đến class hoặc method không tồn tại.
- @see dùng tên lớp sai.
- Tên tham số sau @param không khớp khai báo.
- Kiểu ngoại lệ sau @throws không hợp lệ.

Ví dụ:

~~~java
/**
 * Chuẩn hóa chuỗi.
 *
 * @param text chuỗi đầu vào
 * @return chuỗi đã chuẩn hóa
 * @see String#stripWhitespace()
 */
public String normalize(String input) {
    return input.strip();
}
~~~

Ở đây, tên tham số trong comment là text nhưng tên thật là input; reference String#stripWhitespace() cũng không tồn tại.

Sửa lại:

~~~java
/**
 * Chuẩn hóa chuỗi.
 *
 * @param input chuỗi đầu vào
 * @return chuỗi đã chuẩn hóa
 * @see String#strip()
 */
public String normalize(String input) {
    return input.strip();
}
~~~

Reference sai thường được xem là lỗi nghiêm trọng vì có thể tạo liên kết không đúng hoặc khiến người đọc hiểu nhầm API.

### syntax — cú pháp documentation comment

Nhóm syntax phát hiện cú pháp tag hoặc markup thấp cấp không hợp lệ, chẳng hạn:

- Dùng tag Javadoc không hợp lệ.
- Viết dấu < hoặc > như văn bản HTML mà không escape.
- Dùng ký tự & sai cách.
- Cú pháp inline tag không đúng.

Ví dụ:

~~~java
/**
 * Trả về true nếu value < limit.
 */
public boolean isBelow(int value, int limit) {
    return value < limit;
}
~~~

Trong HTML, dấu < có thể được hiểu là bắt đầu một tag. Nên dùng {@code} hoặc {@literal}:

~~~java
/**
 * Trả về true nếu {@code value < limit}.
 */
public boolean isBelow(int value, int limit) {
    return value < limit;
}
~~~

Nếu cần viết HTML trực tiếp, có thể dùng entity như &lt;, &gt; và &amp;.

### Bảng tổng hợp nhóm

| Nhóm | Kiểm tra | Ví dụ |
|---|---|---|
| accessibility | Markup hỗ trợ khả năng truy cập | img thiếu alt |
| html | Cấu trúc HTML | Thẻ đóng thiếu, lồng sai |
| missing | Thiếu comment/tag | Thiếu @param hoặc @return |
| reference | Tên và liên kết API | {@link} sai, tên @param sai |
| syntax | Cú pháp Javadoc/HTML | Ký tự < chưa escape, tag sai |

## 4. Bật từng nhóm hoặc loại trừ nhóm

Có thể chỉ định nhóm trong tùy chọn -Xdoclint.

Bật nhóm html, syntax và accessibility:

~~~bash
javadoc -Xdoclint:html,syntax,accessibility -d docs src/com/example/TextService.java
~~~

Có thể viết nhiều tùy chọn riêng:

~~~bash
javadoc -Xdoclint:html -Xdoclint:syntax -Xdoclint:accessibility -d docs src/com/example/TextService.java
~~~

Bật tất cả nhưng bỏ qua nhóm missing:

~~~bash
javadoc -Xdoclint:all,-missing -d docs src/com/example/TextService.java
~~~

Cấu hình này vẫn kiểm tra HTML, reference, syntax và accessibility; chỉ không báo các vấn đề thuộc nhóm missing. Đây có thể là bước chuyển tiếp cho codebase cũ, nhưng nên lập kế hoạch bổ sung tài liệu còn thiếu thay vì giữ cấu hình bỏ qua vĩnh viễn.

Một số cách dùng thường gặp:

| Cấu hình | Ý nghĩa |
|---|---|
| -Xdoclint | Bật kiểm tra khuyến nghị |
| -Xdoclint:all | Bật tất cả nhóm |
| -Xdoclint:none | Tắt toàn bộ DocLint |
| -Xdoclint:html,syntax | Chỉ định các nhóm HTML và syntax |
| -Xdoclint:all,-missing | Tất cả trừ missing |

Khi cần kiểm soát chính xác tập nhóm, hãy chỉ định chúng trong một cấu hình rõ ràng và kiểm tra lại kết quả bằng đúng phiên bản JDK của dự án.

## 5. Giới hạn kiểm tra theo package

Javadoc cung cấp tùy chọn -Xdoclint/package: để giới hạn hoặc loại trừ các package cần kiểm tra.

Kiểm tra package com.example và các package con:

~~~bash
javadoc -Xdoclint:all "-Xdoclint/package:com.example.*" -d docs src/com/example/TextService.java
~~~

Kiểm tra package cụ thể:

~~~bash
javadoc -Xdoclint:all -Xdoclint/package:com.example.api -d docs src/com/example/TextService.java
~~~

Có thể thêm dấu trừ trước package specifier để loại package đó khỏi phạm vi kiểm tra:

~~~bash
javadoc -Xdoclint:all "-Xdoclint/package:-com.example.legacy" -d docs src/com/example/TextService.java
~~~

Package specifier có thể là tên package đầy đủ hoặc tên prefix kết thúc bằng .* để mở rộng đến các package con.

Đây là công cụ kiểm soát phạm vi, không phải giải pháp thay cho việc sửa lỗi. Nếu loại trừ package cũ, hãy ghi nhận lý do và tránh để package đó trở thành vùng không được kiểm tra vĩnh viễn.

## 6. Bỏ qua một cảnh báo có chủ đích

Có thể dùng annotation @SuppressWarnings để bỏ qua thông báo DocLint tại một khai báo hoặc phạm vi bao ngoài.

Bỏ qua riêng nhóm missing:

~~~java
@SuppressWarnings("doclint:missing")
public void legacyExtensionPoint() {
}
~~~

Bỏ qua nhiều nhóm:

~~~java
@SuppressWarnings({
    "doclint:missing",
    "doclint:reference"
})
public void compatibilityHook() {
}
~~~

Bỏ qua tất cả thông báo DocLint tại khai báo:

~~~java
@SuppressWarnings("doclint")
public void generatedBridge() {
}
~~~

Nên dùng phạm vi hẹp nhất có thể. Nếu API public thiếu tài liệu, ưu tiên viết comment đúng thay vì suppress. Nếu một comment được sinh tự động hoặc không thể sửa ngay, hãy giải thích lý do trong code review hoặc tài liệu nội bộ để nhóm hiểu vì sao có suppression.

Annotation trên một khai báo có thể ảnh hưởng thông báo của khai báo đó và các khai báo bao ngoài theo quy tắc DocLint. Annotation trên module hoặc package declaration chỉ ảnh hưởng chính declaration đó; nó không tự động suppress comment trong mọi source file thuộc package.

## 7. Ví dụ hoàn chỉnh: tạo Javadoc với DocLint

Tạo source tree:

~~~text
doclint-demo/
└── src/
    └── com/
        └── example/
            └── TextService.java
~~~

Nội dung src/com/example/TextService.java:

~~~java
package com.example;

/**
 * Cung cấp các thao tác chuẩn hóa văn bản.
 *
 * <p>Các phương thức của lớp này xử lý chuỗi đầu vào theo quy tắc
 * thống nhất để ứng dụng có thể lưu và so sánh dữ liệu.
 *
 * @since 17
 */
public class TextService {

    /**
     * Tạo một dịch vụ xử lý văn bản.
     */
    public TextService() {
    }

    /**
     * Loại bỏ khoảng trắng ở hai đầu chuỗi.
     *
     * <p>Nếu chuỗi rỗng sau khi xử lý, kết quả là chuỗi rỗng.
     *
     * @param input chuỗi cần chuẩn hóa
     * @return chuỗi đã bỏ khoảng trắng ở hai đầu
     * @throws IllegalArgumentException nếu input là null
     * @see String#strip()
     */
    public String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        return input.strip();
    }

    /**
     * Kiểm tra một giá trị có nhỏ hơn giới hạn hay không.
     *
     * @param value giá trị cần kiểm tra
     * @param limit giới hạn so sánh
     * @return true nếu value nhỏ hơn limit
     */
    public boolean isBelow(int value, int limit) {
        return value < limit;
    }
}
~~~

Từ thư mục doclint-demo, chạy Javadoc bằng JDK 17 trở lên:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -d docs src/com/example/TextService.java
~~~

Giải thích:

- --release 17 đặt mức tương thích nguồn và API Java.
- -Xdoclint:all bật đủ năm nhóm kiểm tra.
- -Werror biến warning thành lỗi để CI không chấp nhận tài liệu chưa đạt.
- -encoding UTF-8 giúp đọc comment có tiếng Việt.
- -d docs đặt HTML output vào thư mục docs.
- Đường dẫn cuối lệnh là source file cần tạo tài liệu.

Nếu không có lỗi hoặc warning, Javadoc tạo tài liệu trong docs. Có thể mở docs/index.html và docs/com/example/TextService.html để kiểm tra nội dung.

Ví dụ trên có comment cho class, constructor và các method public; tên tham số khớp source; reference String#strip() tồn tại; HTML dùng paragraph hợp lệ. Đây là cấu hình phù hợp để làm điểm bắt đầu cho một API nhỏ.

## 8. Ví dụ lỗi và cách đọc kết quả DocLint

Giả sử có method:

~~~java
/**
 * Kiểm tra chuỗi.
 *
 * @param text chuỗi cần kiểm tra
 * @return true nếu hợp lệ
 * @see String#isBlankValue()
 */
public boolean isValid(String input) {
    return input != null && !input.isBlank();
}
~~~

Có ít nhất hai vấn đề:

1. @param ghi text nhưng khai báo thật là input.
2. String#isBlankValue() không phải method hợp lệ của String.

Khi chạy Javadoc, DocLint sẽ chỉ ra source location, dòng có vấn đề và loại thông báo. Nội dung chính xác của diagnostic có thể khác theo phiên bản JDK, nhưng cách sửa là:

~~~java
/**
 * Kiểm tra chuỗi.
 *
 * @param input chuỗi cần kiểm tra
 * @return true nếu hợp lệ
 * @see String#isBlank()
 */
public boolean isValid(String input) {
    return input != null && !input.isBlank();
}
~~~

Khi đọc output, chú ý:

- Tên file và số dòng để tìm comment nguồn.
- Tên nhóm hoặc loại lỗi trong diagnostic.
- Dòng source được in kèm dấu caret chỉ vị trí.
- Warning hay error.
- Mã thoát của tiến trình Javadoc trong CI.

Không nên chỉ nhìn dòng cuối “1 error” hoặc “warnings found”. Hãy sửa nguyên nhân trong comment, chạy lại cùng lệnh và xác nhận output sạch.

## 9. DocLint và javac

DocLint có thể được gọi từ Javadoc hoặc từ Java compiler.

**Javadoc** tạo HTML và kiểm tra các comment nằm trong phạm vi tài liệu được tạo. Đây là bước chính khi phát hành API documentation.

**javac** cũng có tùy chọn -Xdoclint để kiểm tra documentation comment trong quá trình biên dịch. Khi gọi từ javac, phạm vi comment được kiểm tra phụ thuộc các tùy chọn -Xdoclint mà compiler nhận; không đồng nhất hoàn toàn với phạm vi phần tử được standard doclet đưa vào HTML.

Một pipeline có thể dùng:

~~~bash
javac -Xdoclint:all -d out src/com/example/TextService.java
javadoc -Xdoclint:all -Werror -d docs src/com/example/TextService.java
~~~

Lệnh javac giúp phát hiện vấn đề trong giai đoạn compile. Lệnh javadoc kiểm tra và tạo HTML documentation. Nếu dự án chỉ có một bước tạo Javadoc, có thể thực hiện kiểm tra trong chính lệnh javadoc.

## 10. Tích hợp DocLint vào CI

Để DocLint có ích lâu dài, nên đưa lệnh tạo Javadoc vào build pipeline thay vì chỉ chạy thủ công trước khi phát hành.

Một quy trình đơn giản:

1. Compile source với JDK và release mục tiêu.
2. Chạy Javadoc với -Xdoclint:all.
3. Bật -Werror khi codebase đã xử lý warning hiện có.
4. Lưu HTML output làm artifact hoặc publish theo quy trình tài liệu.
5. Kiểm tra một số trang HTML được sinh để bảo đảm nội dung và liên kết hiển thị đúng.

Ví dụ lệnh build:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -d build/docs src/main/java/com/example/*.java
~~~

Nếu dự án dùng Maven hoặc Gradle, cấu hình Javadoc task/plugin để truyền các tùy chọn tương đương vào bước generate documentation. Nên dùng cùng JDK vendor/version trong local development và CI để tránh khác biệt về tag, diagnostic hoặc doclet.

### Chiến lược cho codebase cũ

Khi bật DocLint lần đầu trên dự án lâu năm, có thể xuất hiện nhiều warning đã tồn tại từ trước. Nên:

- Bật -Xdoclint:all để nhìn thấy toàn bộ nhóm vấn đề.
- Phân loại warning theo package và mức độ ảnh hưởng.
- Sửa reference sai, HTML sai và cú pháp sai trước.
- Bổ sung mô tả cho API public được sử dụng rộng rãi.
- Nếu cần chuyển đổi theo giai đoạn, dùng -Xdoclint:all,-missing tạm thời nhưng vẫn giữ các nhóm còn lại.
- Khi đã xử lý warning, bật -Werror để ngăn lỗi mới xuất hiện.

Không nên tắt toàn bộ DocLint chỉ vì số lượng warning ban đầu lớn. Có thể giới hạn phạm vi package trong thời gian chuyển đổi, nhưng phải có mục tiêu đưa các package đó trở lại kiểm tra.

## 11. Những giới hạn cần hiểu

DocLint là một lớp kiểm tra hữu ích, nhưng không đảm bảo tài liệu hoàn hảo.

- Nó không tự viết phần mô tả còn thiếu.
- Nó không tự sửa HTML hoặc tag sai.
- Nó không phải bộ xác thực HTML đầy đủ.
- Nó không xác nhận mọi lời giải thích trong comment đúng với hành vi runtime.
- Nó không bảo đảm ví dụ code trong comment biên dịch hoặc chạy đúng.
- Nó không thay thế việc đọc lại trang HTML được tạo.
- Nó không thể xác nhận API documentation có đủ dễ hiểu với người dùng hay không.

Ví dụ, một comment có @return hợp lệ về cú pháp nhưng mô tả sai giá trị trả về vẫn có thể vượt qua DocLint. Tương tự, một snippet code có thể hiển thị đẹp nhưng không biên dịch nếu không được kiểm tra riêng.

Vì vậy, kết hợp DocLint với review nội dung, test code example và kiểm tra HTML output.

## 12. Lỗi thường gặp khi bật DocLint

### Unknown option hoặc unknown flag

Có thể đang dùng sai cú pháp hoặc JDK quá cũ. Kiểm tra:

~~~bash
javadoc --version
javadoc --help
javadoc --help-extra
~~~

Dùng đúng option mà phiên bản JDK đang triển khai hỗ trợ.

### Javadoc báo warning dù source compile thành công

Compile Java và tạo Javadoc là hai bước khác nhau. Compiler có thể không kiểm tra toàn bộ các liên kết hoặc markup mà standard doclet xử lý. Chạy đúng lệnh Javadoc trong CI để phát hiện lỗi tài liệu.

### -Werror khiến build thất bại

-Werror biến warning thành lỗi. Đọc từng diagnostic và sửa comment hoặc cấu hình phạm vi phù hợp. Không xóa -Werror chỉ để làm build xanh nếu warning phản ánh vấn đề tài liệu thật.

### Warning xuất hiện trong package cũ

Có thể dùng package filter hoặc tạm bỏ nhóm missing trong khi chuyển đổi. Giữ các nhóm syntax, html, reference và accessibility để tiếp tục phát hiện lỗi quan trọng.

### @SuppressWarnings không suppress được

Kiểm tra chuỗi annotation có đúng dạng doclint hoặc doclint:group không; annotation phải đặt trên declaration có liên quan hoặc declaration bao ngoài theo quy tắc. Annotation trên package/module không tự động áp dụng cho mọi source file khác.

### DocLint không phát hiện lỗi nội dung

DocLint kiểm tra cú pháp và một số cấu trúc, không đánh giá ý nghĩa nghiệp vụ. Cần review tài liệu, xác nhận chữ ký API, kiểm thử snippet và đọc HTML output.

## 13. Checklist bật DocLint

- Kiểm tra phiên bản JDK bằng javadoc --version.
- Xác định phạm vi API cần tài liệu hóa: public, protected, package hay private.
- Bật tất cả nhóm bằng -Xdoclint:all.
- Hiểu năm nhóm accessibility, html, missing, reference và syntax.
- Sửa lỗi tham chiếu, tên tham số và HTML trước khi phát hành.
- Dùng {@code} hoặc {@literal} cho ký tự <, > và biểu thức cần hiển thị nguyên văn.
- Bổ sung alt cho hình ảnh và caption/mô tả phù hợp cho bảng.
- Dùng package filter hoặc suppression thật hẹp khi có lý do rõ ràng.
- Bật -Werror trong CI sau khi xử lý warning hiện có.
- Giữ cùng JDK version trong môi trường local và CI.
- Kiểm tra HTML được sinh; DocLint không phải HTML validator đầy đủ.
- Review tính chính xác của nội dung và kiểm thử riêng các code snippet.

## 14. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| DocLint | Bộ kiểm tra vấn đề trong documentation comment |
| -Xdoclint | Bật các kiểm tra DocLint được khuyến nghị |
| -Xdoclint:all | Bật toàn bộ nhóm kiểm tra |
| -Xdoclint:none | Tắt toàn bộ DocLint |
| -Werror | Biến warning thành lỗi |
| accessibility | Kiểm tra một số vấn đề hỗ trợ truy cập |
| html | Kiểm tra cấu trúc HTML phổ biến |
| missing | Kiểm tra comment và tag còn thiếu |
| reference | Kiểm tra liên kết và tên phần tử Java |
| syntax | Kiểm tra cú pháp Javadoc và markup |
| -Xdoclint/package | Giới hạn kiểm tra theo package |
| @SuppressWarnings | Suppress thông báo DocLint trong phạm vi khai báo |
| Standard doclet | Bộ tạo HTML mặc định của Javadoc |

Bật DocLint giúp đưa chất lượng Javadoc vào quy trình build có thể lặp lại. Với thư viện hoặc module có API công khai, nên bật toàn bộ nhóm kiểm tra, sửa warning và error ở nguồn, rồi dùng -Werror trong CI để ngăn tài liệu mới bị suy giảm chất lượng.

## Tài liệu tham khảo

- Oracle JDK 24 — [The javadoc Command: DocLint](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- Oracle JDK 24 — [JavaDoc Guide: DocLint](https://docs.oracle.com/en/java/javase/24/javadoc/javadoc-guide.pdf)
- OpenJDK — [javac documentation and -Xdoclint options](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/man/javac.md)