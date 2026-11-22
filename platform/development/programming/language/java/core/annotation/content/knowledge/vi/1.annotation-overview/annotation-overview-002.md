# Phân biệt annotation, chú thích mã nguồn và Javadoc trong Java

Trong mã nguồn Java, ba cách viết có thể nằm ngay cạnh một class hoặc method:

\`\`\`java
// Giải thích ý định cho người đọc.
/** Mô tả API cho tài liệu Javadoc. */
@Override
public String toString() {
    return "Example";
}
\`\`\`

Cả ba đều cung cấp thông tin bổ sung, nhưng **khác nhau về cú pháp, đối tượng sử dụng, thời điểm được xử lý và khả năng tác động đến công cụ/chương trình**. Hiểu đúng sự khác biệt giúp chọn cách diễn đạt phù hợp và không kỳ vọng một dòng chú thích sẽ tự kiểm tra hay thay đổi hành vi Java.

## 1. Bức tranh tổng quan

| Tiêu chí | Annotation | Chú thích mã nguồn (comment) | Javadoc |
| --- | --- | --- | --- |
| Cú pháp điển hình | \`@Override\`, \`@Deprecated\`, \`@MyTag(...)\` | \`// ...\`, \`/* ... */\` | \`/** ... */\` |
| Bản chất | Metadata có cấu trúc, gắn với phần tử Java hoặc vị trí kiểu hợp lệ | Văn bản giải thích trong source | Một dạng comment có quy ước tài liệu, có thể chứa các thẻ Javadoc |
| Ai sử dụng? | Trình biên dịch, annotation processor, framework hoặc code đọc reflection, tùy loại annotation | Người đọc và công cụ phân tích source | Người đọc, công cụ \`javadoc\` và các công cụ đọc doc comment |
| Có tự chạy logic không? | Không. Chỉ có tác dụng khi compiler/công cụ/framework/code biết xử lý | Không | Không |
| Có trong \`.class\`? | Tùy \`@Retention\` và loại annotation; không phải mọi annotation đều có ở runtime | Không | Nội dung doc comment thông thường không được đưa vào \`.class\` |
| Có lấy được bằng reflection? | Chỉ khi phù hợp với \`RUNTIME\` retention và API/đối tượng cần đọc | Không | Không qua API reflection thông thường |
| Mục đích chính | Gắn thông tin máy có thể hiểu và xử lý | Diễn giải ý định, lý do, bối cảnh triển khai | Mô tả hợp đồng sử dụng API cho người dùng thư viện |

**Điểm mấu chốt:** annotation là dữ liệu có cấu trúc cho chương trình/công cụ; comment là lời giải thích trong source; Javadoc là comment theo chuẩn để xây dựng tài liệu API. Javadoc vẫn là comment, nhưng có cú pháp và công cụ xử lý chuyên biệt.

## 2. Chú thích mã nguồn: giải thích cho người đọc

Java có hai dạng comment thông thường:

\`\`\`java
// Chú thích một dòng.

 /*
  * Chú thích nhiều dòng.
  * Thường dùng để diễn giải một quyết định hoặc đoạn thuật toán.
  */
\`\`\`

Hai dạng này không khai báo metadata Java và không tạo mã thực thi. Trình biên dịch bỏ qua nội dung comment khi xác định ý nghĩa các biểu thức, lệnh và khai báo Java. Các công cụ phân tích source vẫn có thể đọc comment, ví dụ để kiểm tra quy ước hay hiển thị trong IDE.

Ví dụ:

\`\`\`java
// Không cho phép số âm vì quy tắc nghiệp vụ hiện tại.
if (amount < 0) {
    throw new IllegalArgumentException("amount must be non-negative");
}
\`\`\`

Chương trình từ chối số âm **do điều kiện \`if\` và lệnh \`throw\`**, không phải do comment. Nếu bỏ comment, logic vẫn chạy như cũ; nếu bỏ điều kiện \`if\` mà chỉ giữ comment, không còn kiểm tra số âm.

Comment hữu ích nhất khi trả lời câu hỏi **vì sao** một quyết định hoặc quy tắc tồn tại, mô tả một bất biến khó nhận ra, hoặc nêu một giới hạn kỹ thuật cần biết. Không nên viết comment chỉ để lặp lại chính xác điều code đã thể hiện:

\`\`\`java
// Tăng i lên 1.
i++;
\`\`\`

Một comment lỗi thời có thể gây hiểu nhầm hơn việc không có comment. Khi thay đổi logic, cần kiểm tra cả những comment liên quan.

## 3. Javadoc: tài liệu cho hợp đồng API

Javadoc dùng dạng comment mở đầu bằng \`/**\` và thường đặt ngay trước khai báo class, interface, constructor, method hoặc field. Công cụ \`javadoc\` đọc những comment này để tạo tài liệu API, thường dưới dạng HTML.

\`\`\`java
/**
 * Tính số tiền còn lại sau khi trừ phần đã thanh toán.
 *
 * @param total tổng số tiền phải trả
 * @param paid số tiền đã thanh toán
 * @return số tiền còn lại, có thể âm nếu đã trả dư
 * @throws IllegalArgumentException nếu total hoặc paid âm
 */
public static long remaining(long total, long paid) {
    if (total < 0 || paid < 0) {
        throw new IllegalArgumentException("amount must be non-negative");
    }
    return total - paid;
}
\`\`\`

Cấu trúc này ghi rõ **cách sử dụng API**, ý nghĩa tham số, giá trị trả về và ngoại lệ. Cần phân biệt:

- \`@param\`, \`@return\`, \`@throws\` **bên trong \`/** ... */\`** là *thẻ Javadoc*, không phải annotation Java.
- \`@Override\` hoặc \`@Deprecated\` **bên ngoài comment** là annotation của ngôn ngữ Java.
- \`{@code ...}\` và \`{@link ...}\` là các thẻ Javadoc nội tuyến, ví dụ \`{@code null}\` hoặc \`{@link java.util.List}\`.
- Chỉ viết \`@throws\` không làm method thực sự ném ngoại lệ; chỉ viết \`@return\` không quyết định giá trị trả về. Quy tắc và hành vi phải được triển khai bằng Java code.

Javadoc có thể hiển thị mô tả khi IDE hỗ trợ đọc source hoặc bộ tài liệu đính kèm. Để tạo HTML, chạy \`javadoc\` với source tương ứng; chỉ gõ \`/** ... */\` vào code không tự tạo trang HTML.

### \`@deprecated\` khác \`@Deprecated\` thế nào?

Đây là trường hợp dễ nhầm vì chỉ khác chữ hoa:

\`\`\`java
/**
 * @deprecated Dùng newApi() thay thế.
 */
@Deprecated
public void oldApi() {
}
\`\`\`

\`@deprecated\` (chữ thường) **là thẻ Javadoc** giải thích lý do/hướng thay thế trong tài liệu. \`@Deprecated\` (chữ hoa) **là annotation Java** để công cụ và trình biên dịch nhận biết một phần tử đã lỗi thời; compiler có thể phát cảnh báo khi người dùng gọi API đó. Khi khai báo API lỗi thời, nên phối hợp cả hai để công cụ lẫn người đọc đều có thông tin hữu ích.

## 4. Annotation: metadata được Java và công cụ nhận biết

Một annotation xuất hiện ở vị trí cú pháp mà Java cho phép và phải tương ứng với một **annotation type** đã được khai báo. Annotation có thể gắn với class, method, field, parameter, constructor, package, module hoặc các vị trí sử dụng kiểu tùy theo định nghĩa của annotation.

Ví dụ:

\`\`\`java
@Override
public String toString() {
    return "Customer";
}
\`\`\`

\`@Override\` báo cho compiler kiểm tra rằng method thực sự override/implement một method phù hợp từ supertype. Nếu gõ nhầm tên method, compiler báo lỗi.

\`\`\`java
class Parent {
    void process() {}
}

class Child extends Parent {
    @Override
    void proccess() {} // Lỗi biên dịch: không có method phù hợp để override.
}
\`\`\`

Đoạn trên là **ví dụ cố ý sai**, không phải chương trình được kỳ vọng biên dịch thành công. Nếu xóa \`@Override\`, method \`proccess()\` mới có thể được xem như method khác; nhưng lỗi logic do viết sai tên vẫn còn. Annotation giúp compiler phát hiện vấn đề sớm.

Một annotation tự định nghĩa có dạng:

\`\`\`java
@interface ReviewedBy {
    String value();
}
\`\`\`

Sử dụng:

\`\`\`java
@ReviewedBy("team-a")
class InvoiceService {
}
\`\`\`

Chuỗi \`"team-a"\` là một giá trị metadata. **Chỉ khai báo/gắn \`@ReviewedBy\` chưa tạo ra kiểm tra phê duyệt nào.** Muốn nó có tác dụng, phải có một bên đọc và xử lý: annotation processor lúc biên dịch, framework lúc cấu hình, hoặc code reflection ở runtime.

### Retention: annotation tồn tại tới giai đoạn nào?

Java cho phép khai báo chính sách lưu giữ qua \`@Retention\`:

| Chính sách | Ý nghĩa | Reflection lúc chạy |
| --- | --- | --- |
| \`RetentionPolicy.SOURCE\` | Chỉ cần ở source; compiler không giữ annotation trong class file | Không |
| \`RetentionPolicy.CLASS\` | Ghi vào class file nhưng JVM không bắt buộc giữ để reflection truy cập lúc chạy; đây là retention mặc định khi không khai báo | Không qua reflection thông thường |
| \`RetentionPolicy.RUNTIME\` | Ghi vào class file và có thể được reflection truy cập lúc chạy | Có, qua API thích hợp |

Không nên suy luận retention chỉ từ tên annotation. Đọc định nghĩa \`@Retention\` của annotation cụ thể; với annotation type không ghi \`@Retention\`, mặc định là \`CLASS\`.

\`@Target\` giới hạn nơi sử dụng annotation, chẳng hạn \`ElementType.METHOD\` cho method. \`@Documented\` yêu cầu công cụ như \`javadoc\` đưa annotation đó vào tài liệu của phần tử được đánh dấu. \`@Inherited\` có quy tắc kế thừa riêng cho annotation trên class, không có nghĩa mọi annotation trên method tự được kế thừa.

Annotation còn được dùng trong các framework. Ví dụ \`@Override\` được compiler hiểu trực tiếp; các annotation như \`@Transactional\` trong Spring chỉ có ý nghĩa giao dịch khi cơ chế Spring tương ứng thực sự kích hoạt và áp dụng. Không có quy tắc chung rằng cứ gắn \`@Something\` thì JVM sẽ tự thực thi một hành vi nào đó.

## 5. Ví dụ Java 17+: đặt cả ba cạnh nhau và quan sát runtime

Tạo **một tệp \`DocDemo.java\`** với toàn bộ nội dung sau (đây là ví dụ độc lập, có thể biên dịch và chạy):

\`\`\`java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

/**
 * Annotation do ví dụ định nghĩa để gắn nhãn một method.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Traced {
    String value();
}

/**
 * Minh họa sự khác nhau giữa annotation, comment và Javadoc.
 */
public class DocDemo {

    /**
     * Tạo lời chào cho một người.
     *
     * @param name tên người cần chào
     * @return lời chào chứa tên đã nhận
     */
    @Traced("greeting")
    public String welcome(String name) {
        // Dòng này giải thích ý định; nó không tồn tại như metadata runtime.
        return "Xin chào, " + name;
    }

    public static void main(String[] args) throws Exception {
        Method method = DocDemo.class.getDeclaredMethod("welcome", String.class);

        // Reflection đọc annotation vì retention của Traced là RUNTIME.
        System.out.println(method.isAnnotationPresent(Traced.class));
        System.out.println(method.getAnnotation(Traced.class).value());

        System.out.println(new DocDemo().welcome("An"));
    }
}
\`\`\`

Biên dịch và chạy với JDK 17 trở lên:

\`\`\`bash
javac -encoding UTF-8 DocDemo.java
java DocDemo
\`\`\`

Stdout của \`java DocDemo\`:

\`\`\`text
true
greeting
Xin chào, An
\`\`\`

Giải thích kết quả:

1. \`@Traced("greeting")\` lưu giá trị có cấu trúc. Nhờ \`@Retention(RetentionPolicy.RUNTIME)\`, reflection tìm thấy annotation trên method và đọc được \`value()\`.
2. Comment bắt đầu bằng \`//\` mô tả ý định. Nó không tạo ra một annotation để reflection truy vấn.
3. \`/** ... */\` trên class/method mô tả API. Nội dung đó không được lấy ra bằng \`Method.getAnnotation(...)\`; đây là API để đọc annotation chứ không phải doc comment.
4. \`@Documented\` trên kiểu \`Traced\` giúp Javadoc hiển thị thông tin annotation trên phần tử được đánh dấu. Nó **không khiến đoạn văn Javadoc trở thành annotation runtime**.

Thử tự tạo tài liệu HTML (đây là một thao tác riêng với việc biên dịch/chạy):

\`\`\`bash
javadoc -encoding UTF-8 -docencoding UTF-8 -d docs DocDemo.java
\`\`\`

Sau khi lệnh thành công, có thể mở \`docs/DocDemo.html\` để xem tài liệu class/method. Công cụ có thể in thông báo hoặc cảnh báo trong quá trình tạo trang, tùy JDK và mức độ đầy đủ của tài liệu; những dòng đó **không phải stdout của chương trình \`DocDemo\`**.

### Thử thay đổi để hiểu giới hạn

- Đổi \`RetentionPolicy.RUNTIME\` thành \`RetentionPolicy.SOURCE\`: phần Java vẫn có thể biên dịch, nhưng \`method.isAnnotationPresent(Traced.class)\` sẽ là \`false\` và lệnh gọi \`method.getAnnotation(Traced.class).value()\` tiếp theo gây \`NullPointerException\` vì \`getAnnotation\` trả về \`null\`. Muốn thử an toàn, kiểm tra \`null\` trước khi đọc \`value()\`.
- Xóa hai comment \`//\` và \`/** ... */\` trong ví dụ: chương trình Java vẫn xử lý lời chào giống cũ, nhưng mất phần giải thích và tài liệu API.
- Xóa \`@Traced("greeting")\`: reflection không tìm thấy annotation đó trên method. Đây là thay đổi metadata, dù thân method \`welcome\` không thay đổi.

Các thử nghiệm chỉ ra rõ giới hạn của từng cơ chế: **comment/Javadoc phục vụ mô tả; annotation có thể được chương trình/công cụ đọc và diễn giải theo định nghĩa cụ thể**.

## 6. Tại sao annotation không phải một loại comment đặc biệt?

Hai thành phần có thể đứng gần nhau nhưng được Java xử lý rất khác nhau:

\`\`\`java
// @Deprecated
public void oldA() {}

/** @deprecated Dùng API khác thay thế. */
public void oldB() {}

@Deprecated
public void oldC() {}
\`\`\`

- Trên \`oldA\`, \`@Deprecated\` chỉ là chuỗi ký tự nằm trong \`//\`; compiler không coi method là deprecated vì dòng này.
- Trên \`oldB\`, thẻ Javadoc \`@deprecated\` mô tả tình trạng lỗi thời trong tài liệu. Nó không đồng nghĩa với việc method đã được gắn annotation \`@Deprecated\`.
- Trên \`oldC\`, compiler nhìn thấy annotation \`@Deprecated\` thật sự; thông tin này có thể được công cụ sử dụng để cảnh báo.

Đây là các **method minh họa**, không phải chương trình hoàn chỉnh độc lập. Trong thực tế, nên gắn \`@Deprecated\` và viết Javadoc \`@deprecated\` có nội dung hướng dẫn thay thế cho cùng API.

Tương tự, việc viết \`// @Override\` hoặc \`/** @Override */\` không có tác dụng kiểm tra override. Muốn compiler kiểm tra, phải viết \`@Override\` bên ngoài comment và đúng vị trí cú pháp.

## 7. Chọn cách sử dụng trong dự án

**Dùng comment thường** khi muốn người bảo trì hiểu lý do triển khai, một ràng buộc nghiệp vụ khó suy ra từ code, hoặc cảnh báo về giới hạn của thuật toán. Giữ nội dung sát logic hiện hành; tránh để comment che đi code khó hiểu mà có thể đặt tên rõ ràng hơn.

**Dùng Javadoc** cho API mà người khác cần gọi hoặc kế thừa: hợp đồng đầu vào/đầu ra, tác động phụ, nullability, ngoại lệ, thread-safety khi liên quan, điều kiện tiên quyết. Tập trung mô tả thứ người sử dụng API phải biết, thay vì kể từng dòng thực thi. Với API công khai, tài liệu cần cập nhật khi hợp đồng thay đổi.

**Dùng annotation** khi cần metadata máy đọc được, yêu cầu compiler kiểm tra, cho annotation processor sinh/kiểm tra code, hoặc để framework/reflection xử lý một quy ước. Trước khi sử dụng annotation tự viết hoặc của thư viện, hãy hỏi: *Ai sẽ đọc annotation này? Ở bước nào? Retention và target là gì? Khi thiếu cơ chế xử lý, hành vi sẽ ra sao?*

Một method có thể cần cả ba:

\`\`\`java
/**
 * Gửi yêu cầu với thời gian chờ đã cấu hình.
 *
 * @throws IllegalStateException nếu client chưa sẵn sàng
 */
@Override
public void send() {
    // Giữ kiểm tra ở đây vì trạng thái có thể thay đổi trước lúc gửi.
    ensureReady();
    dispatch();
}
\`\`\`

Trong đoạn **minh họa không độc lập** trên, Javadoc mô tả hợp đồng API, \`@Override\` kiểm tra quan hệ kế thừa, còn comment giải thích quyết định đặt vị trí kiểm tra. Các method \`ensureReady()\` và \`dispatch()\` phải do class thực tế định nghĩa.

## 8. Các nhầm lẫn thường gặp

1. **“Có dấu \`@\` thì đều là annotation.”** Sai. \`@param\` bên trong Javadoc là thẻ tài liệu; \`@Override\` bên ngoài comment là annotation.
2. **“Viết Javadoc sẽ làm compiler kiểm tra \`@param\`/\`@return\` như một contract.”** Không. Công cụ \`javadoc\` có thể phát hiện hoặc cảnh báo một số vấn đề tài liệu, nhưng kiểm tra đầu vào/hành vi phải đến từ code hay cơ chế kiểm tra riêng.
3. **“Mọi annotation đều có ở runtime.”** Không. Phụ thuộc retention, nơi gắn và cách đọc. \`CLASS\` retention không được phản chiếu bởi API reflection thông thường.
4. **“Gắn annotation bất kỳ là ứng dụng tự thay đổi hành vi.”** Không. Annotation tự định nghĩa chưa có tác dụng nghiệp vụ nếu không có consumer xử lý.
5. **“\`@Documented\` biến Javadoc thành dữ liệu reflection.”** Không. Nó điều khiển cách công cụ tài liệu trình bày annotation, không lưu nguyên văn doc comment vào đối tượng \`Method\`.
6. **“Javadoc là loại dữ liệu tách hẳn khỏi comment.”** Không. Javadoc là một dạng comment đặc biệt, có cấu trúc để công cụ đọc; nội dung Javadoc không trở thành lệnh Java.
7. **“Mô tả trong comment đủ để giữ code đúng.”** Không. Khi logic đổi, chú thích phải được kiểm tra lại; những điều kiện cần bảo đảm phải được triển khai hoặc kiểm thử.

## 9. Tự kiểm tra hiểu bài

**Câu 1.** Viết \`// @Override\` ngay trên method có khiến compiler kiểm tra override không?  
**Đáp án:** Không. Đó là comment. Phải sử dụng annotation \`@Override\` thực sự.

**Câu 2.** Chương trình có thể lấy Javadoc \`@return\` bằng \`Method.getAnnotation()\` không?  
**Đáp án:** Không. \`@return\` là Javadoc tag, không phải annotation Java.

**Câu 3.** Một annotation \`@Retention(SOURCE)\` có đọc bằng reflection khi chạy được không?  
**Đáp án:** Không; annotation này không được giữ trong class file.

**Câu 4.** Vì sao \`@MyRule\` tự định nghĩa không tự chặn dữ liệu sai?  
**Đáp án:** Phải có compiler plugin, annotation processor, framework hoặc code runtime đọc nó và thực hiện kiểm tra tương ứng.

**Câu 5.** Một public API đã deprecated nên mô tả thế nào?  
**Đáp án:** Gắn \`@Deprecated\` để công cụ nhận biết, đồng thời có Javadoc \`@deprecated\` giải thích lý do và API thay thế.

Nếu muốn quan sát trực tiếp, hãy biên dịch mẫu \`DocDemo.java\`, xem kết quả reflection, tạo Javadoc HTML và thử thay đổi retention. Ba quan sát đó cho thấy khác biệt giữa **metadata của Java, lời giải thích trong source và tài liệu API**.