# Lợi ích về tính dễ đọc và an toàn kiểu khi dùng pattern matching trong Java

## 1. Vấn đề cần giải quyết

Trong Java, một biến có kiểu khai báo là **Object**, một interface hoặc lớp cha có thể tham chiếu đến đối tượng thuộc nhiều kiểu cụ thể. Trước khi gọi hành vi chỉ có ở một kiểu con, lập trình viên cần kiểm tra kiểu rồi ép kiểu. Cách viết truyền thống dễ lặp lại tên kiểu, tên biến và phép ép kiểu; khi nhánh xử lý dài, người đọc phải đối chiếu điều kiện với phép ép kiểu ở phía dưới.

**Pattern matching** kết hợp việc kiểm tra hình dạng/kiểu của giá trị với việc lấy các thành phần đã được kiểm tra. Với **type pattern** trong biểu thức **instanceof**, cú pháp **value instanceof String text** có nghĩa: nếu **value** là một đối tượng **String** khác **null**, nhánh đúng được thực thi và biến **text** được xem là **String**. Trình biên dịch quản lý phạm vi sử dụng biến này dựa vào luồng điều khiển.

Hai lợi ích chính là:

- **Dễ đọc:** điều kiện và biến đã đúng kiểu nằm cạnh nhau; bớt ép kiểu thủ công và bớt lặp.
- **An toàn kiểu tại thời điểm biên dịch:** compiler chỉ cho dùng biến pattern tại nơi nó chứng minh phép khớp đã thành công, đồng thời áp dụng kiểm tra kiểu tĩnh cho các thao tác trên biến.

Pattern matching cho **instanceof** là tính năng chính thức từ **Java 16**, nên toàn bộ ví dụ chạy hoàn chỉnh bên dưới dùng được với **Java 17+**. Pattern matching cho **switch** được chuẩn hóa từ **Java 21**; phần riêng về **switch** ghi rõ phiên bản.

## 2. So sánh trước và sau: điều kiện sát với dữ liệu

Cách truyền thống, hợp lệ:

~~~java
static String normalize(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.strip();
    }
    return "(không phải chuỗi)";
}
~~~

Viết với pattern matching cho **instanceof**:

~~~java
static String normalize(Object value) {
    if (value instanceof String text) {
        return text.strip();
    }
    return "(không phải chuỗi)";
}
~~~

Ở phiên bản mới, **String text** vừa mô tả kiểu cần kiểm tra, vừa đặt tên cho kết quả đã được kiểm tra. Người đọc không phải tự xác minh rằng một phép cast ở dòng sau có khớp điều kiện hay không. IDE cũng dễ gợi ý các phương thức của **String** ngay trên **text**.

| Khía cạnh | Kiểm tra rồi ép kiểu | Dùng type pattern |
| --- | --- | --- |
| Số bước cần đọc | Kiểm tra kiểu → cast → thao tác | Kiểm tra và gắn biến → thao tác |
| Sự lặp lại | Kiểu **String** thường xuất hiện hai lần | Kiểu chỉ khai báo ở pattern |
| Kiểu của biến trong nhánh | Do phép cast tạo ra | Compiler suy ra từ pattern |
| Phạm vi biến | Phụ thuộc khai báo thủ công | Phụ thuộc nơi phép khớp chắc chắn đúng |
| Bảo trì | Dễ quên đổi cast khi sửa điều kiện | Kiểu kiểm tra và kiểu biến gắn tại một chỗ |

Điều này đặc biệt hữu ích khi xử lý dữ liệu dị loại, đầu vào kiểu **Object**, nhiều implementation của interface, hoặc chuỗi điều kiện phân loại đối tượng.

## 3. An toàn kiểu đến từ đâu?

**Kiểm tra trước khi dùng.** Với **value instanceof Integer number**, nhánh đúng chỉ chạy khi **value** thực sự là **Integer** khác **null**. Trong nhánh đó, **number** có kiểu tĩnh **Integer**; khi viết **number + 1**, phép unboxing và toán tử số được kiểm tra như với biến **Integer** thông thường. Không cần cast trực tiếp từ **Object**.

**Phạm vi theo luồng điều khiển (flow scoping).** Trình biên dịch không cho truy cập biến pattern trên đường thực thi chưa chứng minh được phép khớp:

~~~java
if (value instanceof String text) {
    System.out.println(text.length()); // Hợp lệ: text chắc chắn là String
} else {
    System.out.println("Không phải String");
    // Không thể dùng text ở đây: phép khớp đã thất bại.
}
~~~

Biến pattern còn có thể được dùng sau một nhánh thoát sớm:

~~~java
// Đoạn mã nằm trong một phương thức trả về void.
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length()); // Hợp lệ: đường đến đây đã khớp
~~~

**Điều kiện ngắn mạch.** Nhánh phải của **&&** chỉ chạy khi nhánh trái đúng, vì vậy có thể sử dụng biến pattern ở đó:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

Ngược lại, không thể dùng **text** ở vế phải của **||** theo cách tương tự: vế phải có thể được chạy khi phép khớp ở vế trái thất bại.

**Giới hạn cần hiểu:** Java đã bảo vệ kiểu tĩnh từ trước; viết đúng **instanceof** rồi cast đúng kiểu cũng an toàn. Pattern matching chủ yếu làm mối liên hệ đó rõ ràng hơn và giảm cơ hội viết cast sai. Nó không tự kiểm tra ràng buộc nghiệp vụ (ví dụ chuỗi phải là email hợp lệ), không kiểm chứng kiểu phần tử của mọi generic collection và không loại bỏ mọi ngoại lệ lúc chạy.

## 4. Ví dụ Java 17 chạy độc lập

Lưu mã sau thành **PatternMatchingBenefits.java** (tên tệp phải khớp tên **public class**):

~~~java
import java.util.List;

public class PatternMatchingBenefits {
    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            String normalized = text.strip();
            return "Chuỗi: " + normalized
                    + " (" + normalized.length() + " ký tự)";
        }
        if (value instanceof Integer number) {
            return "Số nguyên sau khi tăng: " + (number + 1);
        }
        if (value instanceof List<?> items) {
            return "Danh sách: " + items.size() + " phần tử";
        }
        return "Không có mẫu phù hợp";
    }

    static void printLength(Object value) {
        if (!(value instanceof String text)) {
            System.out.println("Không phải chuỗi");
            return;
        }
        System.out.println("Độ dài: " + text.length());
    }

    public static void main(String[] args) {
        System.out.println(describe(" Java "));
        System.out.println(describe(41));
        System.out.println(describe(List.of("A", "B")));
        System.out.println(describe(null));
        printLength("safe");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 PatternMatchingBenefits.java
java PatternMatchingBenefits
~~~

Kết quả chuẩn:

~~~text
Chuỗi: Java (4 ký tự)
Số nguyên sau khi tăng: 42
Danh sách: 2 phần tử
Không có mẫu phù hợp
Độ dài: 4
~~~

Cách chương trình hoạt động:

1. Chuỗi **" Java "** khớp pattern **String text**, được **strip()** thành **"Java"** rồi tính độ dài **4**.
2. Số **41** được autobox thành **Integer** khi truyền vào tham số **Object**; pattern gắn biến **number** và biểu thức **number + 1** cho ra **42**.
3. **List.of("A", "B")** khớp **List<?>**, nên có thể gọi **size()** an toàn; chương trình không giả định kiểu các phần tử.
4. **null** không khớp bất kỳ type pattern nào của **instanceof**, nên đi đến nhánh dự phòng.
5. Trong **printLength**, nhánh không phải chuỗi trả về sớm; sau nhánh ấy, compiler biết **text** có kiểu **String**.

Đoạn mã chỉ dùng các cú pháp chính thức của Java 17, không cần cờ **--enable-preview**.

## 5. Khi có nhiều kiểu: switch pattern trong Java 21

Từ **Java 21**, **switch** hỗ trợ type pattern chính thức. Khi có nhiều nhánh phân loại cùng một giá trị, cách viết theo biểu thức thường dễ quét mắt hơn chuỗi **if / else if**:

~~~java
// Ví dụ cú pháp Java 21+, không đặt vào chương trình Java 17 ở trên.
static String describeWithSwitch(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String text when !text.isBlank() -> "Chuỗi: " + text.strip();
        case String text -> "Chuỗi trống";
        case Integer number -> "Số nguyên: " + number;
        default -> "Kiểu khác";
    };
}
~~~

Mỗi nhánh nêu **kiểu cần khớp → xử lý**. Compiler kiểm tra sự phù hợp của nhánh, phạm vi của biến pattern, và thứ tự các case: một case tổng quát đặt trước có thể làm case cụ thể phía sau không bao giờ tới được (**dominated case**) và bị báo lỗi. **when** thêm điều kiện canh gác vào pattern. **case null** xử lý **null** một cách tường minh; nếu không có nhánh xử lý null, switch tham chiếu có thể ném **NullPointerException** khi đầu vào là null.

Với một **sealed interface** và các lớp con được cho phép, compiler còn có thể kiểm tra **tính bao phủ (exhaustiveness)** của các case. Ví dụ Java 21+ sau bao phủ hai kiểu con không-null đã khai báo:

~~~java
sealed interface Outcome permits Success, Failure {}
record Success(String value) implements Outcome {}
record Failure(String reason) implements Outcome {}

static String format(Outcome outcome) {
    return switch (outcome) {
        case Success success -> "OK: " + success.value();
        case Failure failure -> "Lỗi: " + failure.reason();
    };
}
~~~

Nếu danh sách subtype của sealed hierarchy thay đổi, compiler có thể yêu cầu cập nhật các nhánh switch khi biên dịch lại. Đây là lợi ích an toàn kiểu khi mô hình miền có tập trạng thái được định nghĩa chặt chẽ. **Exhaustive đối với các subtype không đồng nghĩa với chấp nhận null**. Lưu ý: các đoạn **switch** này yêu cầu **JDK 21+**; **javac 17** không biên dịch cú pháp switch pattern chuẩn Java 21.

## 6. Những lỗi và ngộ nhận thường gặp

- **Dùng biến ngoài nhánh đã khớp:** sau một lệnh **if (obj instanceof String text)** thông thường, không thể mặc định dùng **text** ở mọi vị trí phía sau; phải xét luồng điều khiển. Đặt thao tác bên trong nhánh đúng hoặc dùng guard clause trả về sớm.
- **Nhầm && với ||:** điều kiện **obj instanceof String text && text.length() > 3** là hợp lệ; đổi sang **||** rồi sử dụng **text** ở vế phải sẽ không biên dịch được vì vế trái có thể sai.
- **Mặc định null là một String:** **null instanceof String** luôn trả về **false**. Muốn phân biệt null với kiểu khác, kiểm tra null riêng. Đừng suy rằng mọi phép switch đều có hành vi null giống instanceof.
- **Kiểm tra generic quá mức:** có thể kiểm tra **obj instanceof List<?> list**, nhưng không thể dùng **obj instanceof List<String> list** để bảo đảm mọi phần tử là **String**, bởi generic type arguments bị xóa ở runtime. Nếu cần ràng buộc phần tử, hãy kiểm tra từng phần tử.
- **Trộn phiên bản Java:** **instanceof** pattern dùng chính thức từ Java 16, trong khi pattern matching cho **switch**, **when** guards và record patterns là tính năng chuẩn từ Java 21. Ghi rõ target JDK trong tài liệu, bài tập và cấu hình build.
- **Cho rằng pattern matching giải quyết hết lỗi runtime:** pattern không kiểm tra độ dài hợp lệ của chuỗi, không chứng minh collection bất biến, không thay thế validation; phép cast cũ nếu đã được kiểm tra đúng cũng có thể an toàn.
- **Lạm dụng pattern quá dài:** với một cấu trúc phân nhánh lớn, cân nhắc đa hình (polymorphism), sealed hierarchy hoặc phương thức chuyên trách. Lợi ích về khả năng đọc chỉ tồn tại khi nhánh vẫn tập trung vào một nhiệm vụ.

## 7. Cách áp dụng khi refactor và tự kiểm tra

Khi gặp đoạn mã **instanceof → cast → xử lý**, hãy xác định xem kiểu đã kiểm tra có khớp chính xác với kiểu cần sử dụng không; sau đó viết **instanceof T variable** và bỏ cast tương ứng. Đặt logic dùng **variable** trong vùng mà phép khớp chắc chắn thành công. Với chuỗi phân loại nhiều kiểu, chọn **if / else if** trên JDK 17 hoặc **switch pattern** nếu dự án dùng JDK 21+. Giữ nhánh dự phòng rõ ràng cho đầu vào không khớp và, khi thích hợp, cho **null**.

Khi review hoặc kiểm thử, nên kiểm tra tối thiểu: một giá trị khớp kiểu, một giá trị thuộc kiểu khác, **null**, chuỗi rỗng/blank nếu có guard, và tình huống nhiều nhánh có thể chồng lấn. Với sealed hierarchy, kiểm tra rằng mỗi subtype dự kiến được xử lý. Một refactor tốt phải giữ nguyên hành vi, kể cả cách xử lý null và trường hợp không khớp.

**Kết luận:** Pattern matching làm code nói rõ hơn "giá trị này có đúng kiểu cần dùng không, và nếu có thì dùng nó như kiểu nào?". Nhờ compiler giới hạn phạm vi biến và kiểm tra kiểu, mã bớt cast thủ công, dễ đọc khi bảo trì và khó vô tình dùng một giá trị như kiểu chưa được chứng minh.