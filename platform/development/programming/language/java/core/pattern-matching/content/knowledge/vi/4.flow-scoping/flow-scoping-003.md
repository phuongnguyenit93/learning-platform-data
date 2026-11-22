# Phạm vi biến pattern với toán tử && trong Java

## 1. Mục tiêu: dùng biến vừa khớp ngay trong một điều kiện

Pattern matching cho **instanceof** kết hợp kiểm tra kiểu và khai báo biến có kiểu tương ứng:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Khi phép khớp thành công, compiler biết **text** là **String**; khi phép khớp thất bại, biến **text** không được dùng trên đường đi đó. Cơ chế này được gọi là **flow scoping** (phạm vi phụ thuộc luồng điều khiển), thay vì cho phép biến pattern xuất hiện ở mọi nơi chỉ vì tên biến có trong mã nguồn.

Toán tử logic **&&** đặc biệt hữu ích trong trường hợp cần kiểm tra thêm một thuộc tính của đối tượng sau khi xác nhận kiểu:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

Điều kiện đầu bảo đảm **text** là chuỗi; điều kiện thứ hai chỉ chạy khi điều kiện đầu đúng. Vì thế, **text.isBlank()** an toàn về kiểu và không cần phép cast. Ví dụ này hợp lệ từ **Java 16** và chạy trên **Java 17+** mà không cần bật preview.

## 2. Hai quy tắc cốt lõi của &&

**Quy tắc A — đánh giá ngắn mạch (short-circuit).** Với **left && right**, Java đánh giá **left** trước. Nếu **left** bằng **false**, toàn bộ biểu thức **&&** là **false** và **right** không được đánh giá. Nếu **left** bằng **true**, Java mới đánh giá **right**.

**Quy tắc B — biến pattern chỉ có hiệu lực khi chắc chắn khớp.** Với **value instanceof String text**, compiler cho phép sử dụng **text** trong vế phải của **&&** vì vế phải chỉ được chạy sau khi vế trái trả về **true**. Nếu toàn bộ điều kiện **if** đúng, biến cũng có hiệu lực trong nhánh **then**.

Ví dụ:

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text.toUpperCase());
}
~~~

Cách đọc từ trái sang phải:

1. Nếu **value == null**, phép **instanceof** trả về **false**, nên không gọi **length()**.
2. Nếu **value** là kiểu khác **String**, phép **instanceof** trả về **false**, nên cũng không gọi **length()**.
3. Nếu **value** là **String**, compiler gắn **text** với đối tượng đó rồi kiểm tra **text.length() >= 3**.
4. Chỉ khi cả hai điều kiện đúng, khối **if** chạy và **text.toUpperCase()** được phép sử dụng.

| Giá trị **value** | **instanceof String text** | Có đánh giá **text.length() >= 3**? | Vào nhánh **if**? |
| --- | --- | --- | --- |
| **"Java"** | true | Có; true | Có |
| **"hi"** | true | Có; false | Không |
| **42** (Integer) | false | Không | Không |
| **null** | false | Không | Không |

Tính ngắn mạch là **quy tắc thực thi** của **&&**; flow scoping là **quy tắc biên dịch** dùng thông tin ấy để quyết định biến pattern có được tham chiếu hay không. Hai cơ chế liên quan nhưng không đồng nhất.

## 3. Dùng nhiều vế &&: mỗi bước bổ sung một điều kiện

Sau khi đã chứng minh kiểu ở vế đầu tiên, các vế tiếp theo có thể kiểm tra tính hợp lệ của cùng đối tượng:

~~~java
if (value instanceof String text
        && !text.isBlank()
        && text.strip().length() >= 3) {
    System.out.println("Chuỗi hợp lệ: " + text.strip());
}
~~~

Thứ tự của ba vế là có ý nghĩa:

- **value instanceof String text**: chỉ tiếp tục nếu có đối tượng **String** khác **null**.
- **!text.isBlank()**: chỉ tiếp tục nếu chuỗi không hoàn toàn là khoảng trắng.
- **text.strip().length() >= 3**: chỉ tiếp tục nếu phần nội dung sau khi loại bỏ khoảng trắng hai đầu còn ít nhất ba đơn vị độ dài Java **String**.

Điều kiện cuối cũng có thể dùng **text** vì các vế trước nó đã chứng minh pattern khớp. Khi một vế sai, mọi vế sau bị bỏ qua. Trong mã thực tế, điều này giúp tránh gọi phương thức trên một biến có thể không đúng kiểu, đồng thời cho phép rút gọn nhiều tầng **if** lồng nhau.

Cùng logic nhưng viết dài hơn:

~~~java
if (value instanceof String text) {
    if (!text.isBlank()) {
        if (text.strip().length() >= 3) {
            System.out.println("Chuỗi hợp lệ: " + text.strip());
        }
    }
}
~~~

Cả hai hình thức đều có chỗ dùng: **&&** hợp lý khi mỗi vế là kiểm tra ngắn, cùng phục vụ một quyết định; **if** lồng nhau hữu ích nếu từng bước có xử lý riêng, nhiều nhánh lỗi hoặc cần thông báo lý do cụ thể.

## 4. Ví dụ Java 17 chạy độc lập

Lưu mã dưới đây trong tệp **AndFlowScopeDemo.java**:

~~~java
public class AndFlowScopeDemo {
    static String classify(Object value) {
        if (value instanceof String text
                && !text.isBlank()
                && text.strip().length() >= 3) {
            return "Hợp lệ: " + text.strip();
        }
        return "Bỏ qua";
    }

    static String normalizeAfterGuard(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "Không có chuỗi";
        }
        return "Giá trị: " + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(classify(" Java "));
        System.out.println(classify("hi"));
        System.out.println(classify(12));
        System.out.println(classify(null));

        System.out.println(normalizeAfterGuard("  ok "));
        System.out.println(normalizeAfterGuard("   "));
        System.out.println(normalizeAfterGuard(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AndFlowScopeDemo.java
java AndFlowScopeDemo
~~~

Đầu ra chính xác:

~~~text
Hợp lệ: Java
Bỏ qua
Bỏ qua
Bỏ qua
Giá trị: ok
Không có chuỗi
Không có chuỗi
~~~

**Giải thích:** **classify(" Java ")** khớp **String**, không blank, sau **strip()** còn **Java** dài **4** nên nhận **Hợp lệ: Java**. **"hi"** khớp kiểu nhưng trượt kiểm tra độ dài, **12** không khớp **String**, và **null** không khớp **instanceof** nên ba lần đều nhận **Bỏ qua**. Với **normalizeAfterGuard**, điều kiện phủ định kèm **||** trả về sớm nếu không phải chuỗi hoặc chuỗi blank; đường đi đến lệnh **return "Giá trị: "...** vì vậy luôn có biến **text** đã khớp.

**Lưu ý về phiên bản:** type pattern trong **instanceof** đã chuẩn hóa từ Java 16. Chương trình trên chỉ dùng các API như **String.isBlank()** (Java 11+) và **String.strip()** (Java 11+), nên biên dịch được với JDK 17. Không dùng tính năng pattern matching cho **switch** của Java 21.

## 5. Phạm vi biến bên trong và bên ngoài if

Một quy tắc quan trọng: việc **text** có mặt trong điều kiện không đồng nghĩa với việc nó luôn có mặt sau toàn bộ **if**.

**Trong nhánh đúng:** hợp lệ, vì điều kiện **&&** chỉ đúng nếu **instanceof** đã khớp.

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text); // Hợp lệ
}
~~~

**Trong nhánh else:** không thể dùng **text** một cách tổng quát, bởi điều kiện **&&** có thể sai ngay ở **instanceof**.

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text);
} else {
    System.out.println("Không thỏa điều kiện");
    // Không thể mặc định dùng text ở nhánh else.
}
~~~

**Sau if:** nếu nhánh sai không nhất thiết kết thúc phương thức, đường đi sau **if** vẫn có thể đi qua khi pattern chưa khớp, nên **text** không được bảo đảm có hiệu lực.

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text);
}
// Không thể mặc định dùng text ở đây.
~~~

**Nếu có nhánh thoát sớm:** có thể chứng minh một pattern đã khớp bằng cách loại mọi trường hợp không khớp trước khi dùng:

~~~java
// Đoạn minh họa bên trong một phương thức trả về void.
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length()); // Hợp lệ
~~~

Khi review, phải dựa vào **những đường đi còn có thể tới được vị trí sử dụng**, chứ không chỉ dựa vào dấu ngoặc nhọn gần nhất.

## 6. So sánh && với || và phủ định

Hai biểu thức sau khác nhau về vùng mà biến pattern được phép xuất hiện.

**Hợp lệ:**

~~~java
if (value instanceof String text && text.length() > 0) {
    System.out.println(text);
}
~~~

Khi phải đánh giá vế phải **text.length() > 0**, vế trái đã đúng nên **text** được gắn.

**Không hợp lệ (ví dụ cố ý sai, không đặt vào chương trình chạy):**

~~~java
// LỖI BIÊN DỊCH: nếu instanceof sai thì vế phải của || mới được chạy,
// nhưng lúc ấy text không được bảo đảm tồn tại.
if (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
~~~

Với **||**, vế phải chỉ chạy khi vế trái sai. Khi **instanceof** sai, không có cơ sở để dùng **text** ở vế phải. Ngược lại, **||** có thể kết hợp an toàn với một **pattern bị phủ định**, nếu vế phải chỉ được đánh giá khi phép phủ định sai:

~~~java
// Hợp lệ: khi vế phải chạy, !(instanceof...) là false,
// tức phép instanceof đã thành công và text có hiệu lực.
if (!(value instanceof String text) || text.isBlank()) {
    return;
}
System.out.println(text.strip()); // Hợp lệ sau nhánh return
~~~

Đoạn cuối là mã **minh họa trong một phương thức trả về void**, không phải chương trình độc lập. Ở đây **return** loại bỏ hai loại đầu vào: không khớp **String**, hoặc khớp nhưng blank. Sau **if**, đường đi còn lại bảo đảm **text** đã được gắn và không blank.

Điều khác biệt cần nhớ không phải rằng **||** luôn cấm biến pattern, mà là **mỗi vị trí sử dụng phải nằm trên đường đi chắc chắn pattern đã khớp**.

## 7. Những tình huống hay gây lỗi

### Dùng biến trước điều kiện kiểm tra kiểu

~~~java
// Sai: text chưa được khai báo ở vế trước.
if (text.length() > 2 && value instanceof String text) {
    System.out.println(text);
}
~~~

Hãy đặt type pattern ở vế trái, rồi mới sử dụng biến tại các vế **&&** phía sau. Compiler không thể dùng kết quả kiểm tra sẽ xảy ra trong tương lai để hợp thức hóa vế đã được đánh giá trước.

### Dùng || theo hướng sai

~~~java
// Sai: khi vế trái false, text chưa tồn tại ở vế phải.
if (value instanceof String text || text.startsWith("A")) {
    System.out.println("A");
}
~~~

Muốn kiểm tra **String** đồng thời thỏa điều kiện tiền tố thì dùng **&&**. Muốn kiểm tra một điều kiện khác độc lập với kiểu, hãy tách nhánh rõ ràng và không tham chiếu biến pattern trên đường đi chưa khớp.

### Nhầm dấu ! với điều kiện tích cực

~~~java
if (!(value instanceof String text)) {
    // Không dùng text ở đây: đang ở nhánh không khớp.
} else {
    System.out.println(text.length()); // Nhánh này đã khớp
}
~~~

Phủ định đổi điều kiện đi vào nhánh; **text** có hiệu lực nơi compiler chứng minh phép **instanceof** bên trong đã đúng, không dựa vào sự xuất hiện của tên biến trong biểu thức.

### Không quan tâm đến null

**null instanceof String text** luôn sai, vì vậy **&&** không gọi **text.isBlank()** và tránh được lỗi gọi phương thức trên **null**. Đây là hành vi của phép kiểm tra kiểu; nếu ứng dụng cần báo lỗi riêng khi null, phải thêm logic cho trường hợp đó.

### Nhầm phép khớp kiểu với kiểm tra nội dung

**value instanceof String text && !text.isBlank()** chỉ bảo đảm có chuỗi không blank. Nó không bảo đảm chuỗi là email, URL, ngày hợp lệ hay đúng định dạng nghiệp vụ. Cần thêm validator tương ứng. Với các điều kiện phụ có side effect, cần nhớ chúng chỉ chạy khi mọi vế trước trả về true.

### Dùng biến ở nơi compiler chưa thể chứng minh

Gán kết quả điều kiện vào một biến boolean không kéo theo việc pattern variable xuất hiện ở mọi lệnh sau:

~~~java
boolean accepted = value instanceof String text && text.length() >= 3;
// accepted chỉ lưu true/false; không thể tùy ý dùng text ở đây.
System.out.println(accepted);
~~~

Compiler theo dõi mối quan hệ giữa pattern và luồng điều khiển, không tự suy luận rằng một biến boolean bất kỳ thay thế được toàn bộ bằng chứng về kiểu tại vị trí truy cập mới.

## 8. Hướng dẫn áp dụng khi viết code và review

Dùng **instanceof T variable && điềuKiệnBổSung(variable)** khi cần kết hợp điều kiện kiểu với một hoặc vài kiểm tra ngắn, không có side effect phức tạp. Đặt kiểm tra kiểu trước những lời gọi phương thức phụ thuộc vào kiểu đó; đặt kiểm tra rẻ và dễ hiểu trước các kiểm tra đắt hơn khi điều này không làm đổi hành vi.

Nếu cần nhiều kết quả lỗi khác nhau, nhiều câu lệnh xử lý hoặc đường đi phức tạp, hãy cân nhắc tách thành **if** lồng nhau hoặc dùng guard clause. Cách này giúp review logic thất bại và thành công rõ hơn.

Khi tự kiểm tra, thử ít nhất bốn ca: đối tượng đúng kiểu thỏa điều kiện, đúng kiểu nhưng không thỏa điều kiện phụ, sai kiểu, và **null**. Đồng thời xác nhận biểu thức vế phải không được đánh giá khi **instanceof** sai và tất cả vị trí dùng biến pattern đều biên dịch hợp lệ trên JDK mục tiêu.

**Điểm ghi nhớ:** phép **&&** vừa hỗ trợ đánh giá ngắn mạch từ trái sang phải, vừa tạo điều kiện cho compiler cho phép dùng biến pattern từ **instanceof** ở các vế phải và nhánh đúng. Flow scoping bảo đảm chỉ nơi đã chứng minh phép khớp mới được truy cập biến, nhờ đó mã gọn hơn mà vẫn an toàn kiểu.