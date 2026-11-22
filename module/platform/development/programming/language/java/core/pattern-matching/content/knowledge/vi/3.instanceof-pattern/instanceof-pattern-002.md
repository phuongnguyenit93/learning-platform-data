# Thay thế phép cast sau instanceof bằng pattern matching trong Java

## 1. Vì sao cần thay phép cast?

Khi một biến được khai báo là **Object**, interface hoặc lớp cha, mã nguồn đôi khi phải kiểm tra xem đối tượng thực tế thuộc lớp con nào rồi mới dùng các phương thức chuyên biệt. Trước Java 16, mẫu thường gặp gồm hai thao tác liên tiếp:

1. Kiểm tra kiểu bằng **instanceof**.
2. Ép kiểu (**cast**) sang chính kiểu vừa kiểm tra và gán vào biến.

~~~java
static String formatLegacy(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "Chuỗi: " + text.strip();
    }
    return "Kiểu khác";
}
~~~

Phép cast ở đây hợp lệ nhờ điều kiện ngay phía trên, nhưng tên kiểu **String** lặp lại và người đọc phải đối chiếu điều kiện với dòng cast. Khi có nhiều nhánh **instanceof**, các phép cast tạo thêm mã cơ học, làm nhánh xử lý dài và dễ phát sinh sai sót khi đổi tên kiểu.

**Pattern matching for instanceof** cho phép kiểm tra kiểu và khai báo biến đã đúng kiểu ngay trong một biểu thức:

~~~java
static String formatModern(Object value) {
    if (value instanceof String text) {
        return "Chuỗi: " + text.strip();
    }
    return "Kiểu khác";
}
~~~

Ở đây **value instanceof String text** có nghĩa: nếu **value** là đối tượng **String** khác **null**, biến **text** được gắn với cùng đối tượng đó và có kiểu tĩnh **String**. Không cần viết thêm **(String) value**.

Tính năng type pattern trong **instanceof** được chuẩn hóa từ **Java 16** và có sẵn trong **Java 17**. Đây là thay đổi ngôn ngữ khi biên dịch; không cần bật **--enable-preview**.

## 2. Cú pháp và quy tắc căn bản

Cấu trúc tổng quát:

~~~java
if (expression instanceof TargetType patternVariable) {
    // Dùng patternVariable theo kiểu TargetType
}
~~~

- **expression** là biểu thức tham chiếu cần phân loại, ví dụ **value**.
- **TargetType** là kiểu tham chiếu có thể kiểm tra ở runtime, ví dụ **String**, **Integer**, một interface, mảng hoặc **List<?>**.
- **patternVariable** là biến được giới thiệu khi phép khớp thành công.
- **instanceof** trả về **false** nếu expression là **null**; khi đó biến pattern không tồn tại trong nhánh đúng.
- Biến pattern tham chiếu đến **chính đối tượng được kiểm tra**, không phải một bản sao. Mẫu này không thực hiện chuyển đổi giá trị, chẳng hạn từ chuỗi **"42"** thành số **42**.

So sánh:

| Việc cần làm | Viết với cast | Viết với pattern |
| --- | --- | --- |
| Xác nhận **Object** chứa chuỗi | **value instanceof String** | **value instanceof String text** |
| Lấy biến đúng kiểu | **String text = (String) value;** | Đã có **text** khi khớp |
| Gọi phương thức chuỗi | **text.strip()** | **text.strip()** |
| Xử lý **null** | Điều kiện **instanceof** sai | Điều kiện **instanceof** sai |
| Phạm vi biến | Theo nơi khai báo thủ công | Theo luồng điều khiển mà phép khớp chắc chắn đúng |

**An toàn kiểu không bắt đầu từ pattern matching:** kiểm tra **instanceof** rồi cast đúng kiểu vốn đã an toàn. Pattern matching làm bằng chứng về kiểu và cách sử dụng biến gần nhau hơn, giảm khả năng vô tình ghép sai điều kiện với cast ở một dòng xa.

## 3. Ví dụ Java 17 đầy đủ: trước và sau

Lưu tệp **ReplaceCastDemo.java**:

~~~java
public class ReplaceCastDemo {
    static String before(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "text=" + text.strip();
        }
        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return "next=" + (number + 1);
        }
        return "unknown";
    }

    static String after(Object value) {
        if (value instanceof String text) {
            return "text=" + text.strip();
        }
        if (value instanceof Integer number) {
            return "next=" + (number + 1);
        }
        return "unknown";
    }

    static int nonBlankLength(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text.strip().length();
        }
        return 0;
    }

    static void printGuarded(Object value) {
        if (!(value instanceof String text)) {
            System.out.println("not string");
            return;
        }
        System.out.println("length=" + text.length());
    }

    public static void main(String[] args) {
        Object[] values = {" Java ", 7, null};
        for (Object value : values) {
            System.out.println(before(value) + " | " + after(value));
        }
        System.out.println("trimmed length=" + nonBlankLength("  ok "));
        printGuarded("Hello");
        printGuarded(42);
    }
}
~~~

Lệnh biên dịch và chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 ReplaceCastDemo.java
java ReplaceCastDemo
~~~

Kết quả:

~~~text
text=Java | text=Java
next=8 | next=8
unknown | unknown
trimmed length=2
length=5
not string
~~~

**Giải thích kết quả:** **before** và **after** xử lý ba giá trị giống nhau. Với **" Java "**, cả hai bỏ khoảng trắng biên và trả về **text=Java**. Với **7**, cả hai nhận ra đối tượng **Integer** và trả về **next=8**. **null** không khớp pattern nào nên nhận **unknown**. Trong **nonBlankLength**, điều kiện **&&** chỉ kiểm tra **text.isBlank()** sau khi phép khớp **String** thành công; **"  ok "** có nội dung sau **strip()** dài **2**. Cuối cùng, **printGuarded** minh họa biến pattern còn hợp lệ sau nhánh thoát sớm.

Điểm cần giữ khi refactor là **hành vi**, không chỉ số dòng. Bản **after** có cùng đầu ra như **before** cho các trường hợp này và vẫn có nhánh dự phòng cho giá trị không phải **String** hay **Integer**.

## 4. Phạm vi biến pattern: vì sao không thể dùng mọi nơi?

Một cast tạo biến theo phạm vi từ vựng của khối mã. Với pattern, compiler quản lý **flow scoping**: tên biến chỉ được sử dụng trên đường thực thi mà compiler chứng minh phép khớp đã thành công.

**Trường hợp 1 — trong nhánh đúng:**

~~~java
if (value instanceof String text) {
    System.out.println(text.length()); // Hợp lệ
}
// System.out.println(text.length()); // Không hợp lệ ở đường đi tổng quát
~~~

**Trường hợp 2 — kết hợp kiểm tra phụ bằng &&:**

~~~java
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text.toUpperCase()); // Hợp lệ
}
~~~

Toán tử **&&** đánh giá từ trái sang phải và dừng ngay nếu vế trái sai. Vì vậy vế phải chỉ chạy khi **text** chắc chắn là một **String**. Còn **value instanceof String text || text.isEmpty()** không hợp lệ: vế phải của **||** có thể chạy chính lúc vế trái sai, nên **text** chưa được gắn.

**Trường hợp 3 — kiểm tra phủ định và thoát sớm:**

~~~java
// Đoạn trong một phương thức trả về void.
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length()); // Hợp lệ: đến đây chắc chắn đã khớp
~~~

**Trường hợp 4 — else không được bảo đảm:**

~~~java
if (value instanceof String text) {
    System.out.println(text.strip());
} else {
    System.out.println("Không phải String");
    // text không có hiệu lực ở đây.
}
~~~

Đừng thay toàn bộ cast theo thao tác tìm/thay văn bản: hãy kiểm tra các chỗ đang dùng biến và hướng đi của **if**, **else**, **return**, **throw**, **&&**, **||** trước khi sửa.

## 5. Quy trình refactor an toàn

**Bước 1.** Tìm mẫu lặp thực sự: điều kiện **obj instanceof T** theo sau là **T local = (T) obj** trong nhánh mà **obj** không bị thay đổi trước cast. Nếu biểu thức kiểm tra và biểu thức cast khác nhau, cần phân tích lại trước khi thay.

**Bước 2.** Đổi điều kiện thành **obj instanceof T local**. Giữ nguyên tên biến phù hợp ngữ nghĩa và loại bỏ chính dòng cast nay dư thừa.

**Bước 3.** Giữ các thao tác sử dụng **local** trong phạm vi compiler chấp nhận. Nếu cần guard phụ, có thể đặt **&&** ngay bên phải type pattern; nếu dùng nhánh thoát sớm, bảo đảm đường tới mã phía sau luôn đã khớp.

**Bước 4.** Bảo toàn những nhánh không khớp, **null**, thứ tự điều kiện và ngoại lệ dự kiến. Một nhánh **if** độc lập không tự động tương đương với nhánh **else if** nếu các điều kiện có thể cùng đúng.

**Bước 5.** Biên dịch bằng target JDK của dự án, chạy các ca kiểm thử với giá trị khớp, không khớp và null. Sau khi refactor mới tính đến tối ưu thêm logic ở nhánh.

Ví dụ ngắn với một interface:

~~~java
interface Printable {
    String render();
}

static String renderIfPossible(Object value) {
    if (value instanceof Printable printable) {
        return printable.render();
    }
    return "(không hỗ trợ)";
}
~~~

Đoạn trên là **mã minh họa trong phạm vi class/nguồn hợp lệ**, không phải chương trình độc lập có **main**. Pattern biến **printable** có kiểu **Printable**, nên chỉ truy cập được thành phần thuộc interface này; muốn gọi phương thức riêng của implementation phải kiểm tra kiểu tương ứng.

## 6. Những giới hạn và lỗi thường gặp

- **Không kiểm tra generic type argument đã bị xóa:** **value instanceof java.util.List<?> items** có thể dùng để nhận diện danh sách và đọc **size()**. Nhưng không được viết **value instanceof java.util.List<String> items** để khẳng định mọi phần tử đều là chuỗi; thông tin **String** của generic không được duy trì đầy đủ ở runtime.
- **Không dùng type pattern cho kiểu nguyên thủy trong Java 17:** ví dụ **value instanceof int number** không phải cách kiểm tra hợp lệ. Nếu đầu vào là **Object** chứa giá trị nguyên đã autobox, kiểm tra **Integer number**.
- **Không khớp null:** **value instanceof String text** là **false** khi **value == null**. Xử lý null riêng nếu hành vi ứng dụng yêu cầu.
- **Không dùng biến khi phép khớp có thể sai:** truy cập biến pattern trong **else**, ngoài một nhánh chưa được chứng minh hay bên phải **||** với pattern dương sẽ không biên dịch.
- **Không đổi thứ tự logic tùy tiện:** nếu nhánh trước trả về, việc chuyển thành nhiều nhánh hoặc gộp điều kiện có thể đổi kết quả.
- **Không nghĩ pattern là cơ chế chuyển đổi dữ liệu:** **String text** không parse số hay validate nội dung. **text.strip()**, **Integer.parseInt(text)** và các kiểm tra nghiệp vụ vẫn cần viết tường minh.
- **Không bỏ qua tính tương thích phiên bản:** type pattern cho **instanceof** có từ Java 16. **switch** pattern chuẩn hóa từ Java 21 là chủ đề khác; không dùng cú pháp đó trong chương trình Java 17.
- **Không dùng pattern không cần thiết:** khi biến đã có kiểu tĩnh thích hợp, gọi trực tiếp phương thức thường dễ hiểu hơn. Với một kiểu biểu thức đã biết luôn là subtype của target pattern, Java còn có thể từ chối phép **instanceof** với type pattern bị xem là vô điều kiện.

## 7. Tự kiểm tra sau khi thay

Để biết refactor có đúng, hãy trả lời:

1. **Kiểu kiểm tra và kiểu ép cũ có thật sự là cùng T?** Nếu không, không thể thay máy móc.
2. **Biến pattern được dùng ở vị trí compiler bảo đảm có giá trị không?** Nếu có **||**, phủ định hoặc nhiều nhánh, hãy kiểm tra flow scoping kỹ.
3. **Input null và các implementation khác có còn đi cùng nhánh như trước không?**
4. **Các cast liên quan đến generic hay xử lý kiểu động có đòi hỏi kiểm tra thêm phần tử không?**
5. **Dự án biên dịch với Java 16+ (ví dụ JDK 17) và có test cho các nhánh không?**

Phép chuyển từ **instanceof → cast thủ công** sang **instanceof T variable** giúp ý định của nhánh hiện rõ ngay tại điều kiện, giảm mã lặp và tận dụng kiểm tra kiểu/phạm vi của compiler. Hiệu quả nhất khi áp dụng cho đoạn xử lý đã có logic phân loại đúng và kiểm thử bảo vệ hành vi hiện tại.