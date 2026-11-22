# Hợp đồng equals: tính nhất quán khi dữ liệu dùng để so sánh không thay đổi

## 1. Tính nhất quán nghĩa là gì?

Trong Java, phương thức **Object.equals(Object)** có một yêu cầu về *consistency* (tính nhất quán):

> Với hai tham chiếu đối tượng không null là x và y, những lần gọi liên tiếp x.equals(y) phải nhất quán trả về true hoặc nhất quán trả về false, **miễn là không có thông tin nào được dùng để so sánh bằng equals trên các đối tượng bị thay đổi**.

Đây là một điều kiện có tiền đề, không phải lời hứa rằng kết quả equals không bao giờ thay đổi trong suốt vòng đời đối tượng. Nếu trạng thái thực sự được dùng để so sánh thay đổi, một kết quả khác ở lần gọi sau có thể hoàn toàn hợp lệ.

Xét hai đối tượng cùng đại diện cho mã sách và số phiên bản:

- Lần 1: x.equals(y) trả về true.
- Không thay đổi mã sách, phiên bản hoặc bất kỳ thông tin so sánh nào của x và y.
- Lần 2, lần 3, ...: x.equals(y) vẫn phải trả về true.

Nếu lúc đầu x.equals(y) là false và mọi thông tin so sánh giữ nguyên, các lần gọi tiếp theo cũng phải là false. Không có quy định rằng kết quả phải là true; yêu cầu là **ổn định với cùng dữ liệu so sánh**.

Tính nhất quán là một trong các điều kiện của hợp đồng equals, bên cạnh phản xạ (reflexive), đối xứng (symmetric), bắc cầu (transitive) và x.equals(null) luôn bằng false. Bài này tập trung vào điều kiện nhất quán.

## 2. “Dữ liệu dùng để so sánh” bao gồm những gì?

Giả sử equals dùng các trường code và revision:

~~~java
return revision == other.revision
        && Objects.equals(code, other.code);
~~~

Khi code và revision ở **cả hai đối tượng** không thay đổi, kết quả so sánh phải giữ nguyên. Khi một trong hai trường đó thay đổi, điều kiện “không có thông tin so sánh nào thay đổi” không còn đúng.

Cần phân biệt:

| Tình huống | Có thay đổi thông tin dùng bởi equals? | Kết quả equals có được phép thay đổi? |
| --- | --- | --- |
| Gọi x.equals(y) nhiều lần, mọi dữ liệu so sánh giữ nguyên | Không | Không; phải nhất quán |
| Sửa một trường mà equals có so sánh trong x hoặc y | Có | Có thể thay đổi |
| Sửa trường mô tả/ghi chú không hề được equals sử dụng | Không | Không được đổi chỉ vì trường đó |
| Đối tượng giữ nguyên tham chiếu tới một List, nhưng phần tử của List dùng trong equals bị sửa | Có | Có thể thay đổi |
| Không sửa dữ liệu mà equals lại dùng thời gian, ngẫu nhiên hoặc biến đếm tự tăng để cho kết quả khác nhau | Kết quả phụ thuộc yếu tố không ổn định | Thiết kế vi phạm kỳ vọng nhất quán |

Cụm “không thay đổi” liên quan tới **giá trị/thông tin đem so sánh**, không chỉ việc biến tham chiếu x và y vẫn trỏ tới hai đối tượng cũ. Một đối tượng mutable có thể giữ cùng địa chỉ nhưng dữ liệu bên trong đã thay đổi. Ngược lại, thay đổi một trường hoàn toàn không liên quan tới equals không phải lý do hợp lệ để kết quả equals đổi khác.

Với trường là đối tượng lồng nhau, phải xét trạng thái mà phép equals của trường đó sử dụng. Ví dụ, nếu equals so sánh một List bằng List.equals, việc thay đổi phần tử có thể thay đổi kết quả dù tham chiếu List vẫn là một.

## 3. Ví dụ Java 17+ chạy được: dữ liệu ổn định và dữ liệu bị sửa

Tạo tệp **EqualsConsistencyDemo.java**:

~~~java
import java.util.Objects;

public class EqualsConsistencyDemo {
    public static void main(String[] args) {
        BookCode fixedA = new BookCode("JAVA", 17);
        BookCode fixedB = new BookCode("JAVA", 17);

        System.out.println("fixed #1: " + fixedA.equals(fixedB));
        System.out.println("fixed #2: " + fixedA.equals(fixedB));

        MutableLabel left = new MutableLabel("ready");
        MutableLabel right = new MutableLabel("ready");

        System.out.println("before edit: " + left.equals(right));
        right.setText("busy");
        System.out.println("after edit: " + left.equals(right));
        right.setText("ready");
        System.out.println("after restore: " + left.equals(right));
    }

    static final class BookCode {
        private final String code;
        private final int revision;

        BookCode(String code, int revision) {
            this.code = Objects.requireNonNull(code);
            this.revision = revision;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof BookCode that)) {
                return false;
            }
            return revision == that.revision
                    && code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, revision);
        }
    }

    static final class MutableLabel {
        private String text;

        MutableLabel(String text) {
            this.text = text;
        }

        void setText(String text) {
            this.text = text;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof MutableLabel that)) {
                return false;
            }
            return Objects.equals(text, that.text);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(text);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac EqualsConsistencyDemo.java
java EqualsConsistencyDemo
~~~

Kết quả chuẩn:

~~~text
fixed #1: true
fixed #2: true
before edit: true
after edit: false
after restore: true
~~~

**Giải thích:**

1. BookCode có các trường final và đối tượng String bất biến; sau khi khởi tạo, code và revision không bị sửa. So sánh cùng cặp fixedA, fixedB lặp lại luôn trả true.
2. Trước khi sửa, left và right đều có text = "ready", nên equals trả true.
3. Sau lệnh right.setText("busy"), dữ liệu so sánh của right thay đổi. Kết quả false **không vi phạm** tính nhất quán.
4. Sau khi đặt lại "ready", dữ liệu lại bằng nhau, kết quả true cũng hợp lệ.
5. Cả hai lớp ghi đè hashCode tương thích với các trường đang dùng trong equals. Điều này phục vụ một điều kiện quan trọng khác khi đối tượng được dùng trong cấu trúc băm.

Không nên diễn giải ví dụ rằng mutable luôn sai hoặc final tự động khiến equals đúng. Một lớp mutable vẫn có thể thực hiện hợp đồng nhất quán: mỗi lần kiểm tra phải dựa trên dữ liệu đang có, không tự đổi kết quả khi dữ liệu so sánh đứng yên. final giúp việc giữ trạng thái so sánh ổn định dễ hơn, nhưng chất lượng triển khai equals vẫn cần được kiểm tra.

## 4. Ví dụ sai: kết quả tự đổi dù không sửa dữ liệu đối tượng

Đoạn mã sau **chỉ minh họa cách triển khai sai**, không phải một chương trình độc lập; phương thức còn vi phạm các điều kiện khác của equals trong một số tình huống:

~~~java
final class BadKey {
    private static boolean flip;

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof BadKey)) {
            return false;
        }
        flip = !flip;
        return flip;
    }
}
~~~

Với hai đối tượng BadKey khác tham chiếu, những lần so sánh liên tiếp có thể luân phiên true và false dù không thay đổi thông tin đại diện cho hai đối tượng. Biến flip là trạng thái dùng để làm kết quả dao động, không phải thuộc tính giá trị của đối tượng được so sánh. Đây là cách thiết kế không phù hợp cho equals.

Các dấu hiệu lỗi cùng bản chất:

- Đọc giá trị ngẫu nhiên, đồng hồ hệ thống hoặc dữ liệu ngoài thường xuyên thay đổi để quyết định bằng nhau khi bản chất giá trị đối tượng không đổi.
- Tăng bộ đếm, đổi cờ hoặc sửa trường so sánh bên trong equals, khiến chính lần kiểm tra trước làm kết quả lần kiểm tra sau thay đổi.
- So sánh các trường được tính toán với logic không ổn định hoặc phụ thuộc trạng thái toàn cục không được kiểm soát.
- Gọi getter có tác dụng phụ làm thay đổi dữ liệu so sánh; tên getter không bảo đảm rằng nó chỉ đọc dữ liệu.

Ngược lại, tính toán một giá trị suy ra theo cách **thuần túy và xác định** từ các trường ổn định, rồi dùng giá trị đó trong equals, vẫn có thể nhất quán. Ví dụ chuẩn hóa mã bằng một quy tắc cố định sẽ ổn định nếu dữ liệu đầu vào và quy tắc không đổi.

## 5. Vì sao tính nhất quán quan trọng khi dùng hashCode và HashSet/HashMap?

Hai hợp đồng liên quan nhưng không đồng nhất:

- **equals:** Nếu không sửa thông tin dùng để so sánh, lặp lại phép so sánh trên cùng đối tượng phải cho cùng kết quả.
- **hashCode:** Trong một lần chạy Java, nếu không sửa thông tin được dùng trong equals, gọi hashCode nhiều lần trên cùng đối tượng phải cho cùng số nguyên. Hai đối tượng bằng nhau theo equals **bắt buộc** có cùng hashCode; hai đối tượng khác nhau vẫn có thể trùng hashCode.

Trong ví dụ BookCode, equals xét code và revision nên hashCode cũng dựa trên hai trường đó. Nếu chỉ override equals mà bỏ qua hashCode, các collection dựa trên băm như HashSet và HashMap có thể hoạt động sai với kỳ vọng “hai khóa bằng nhau là một khóa”.

Ngay cả khi equals và hashCode được viết đúng, **sửa trường dùng trong equals/hashCode của một đối tượng đã làm khóa trong HashMap hoặc đã thêm vào HashSet** có thể phá vỡ khả năng tìm lại phần tử vì bucket/giá trị băm lúc lưu không còn phù hợp. Đây là vấn đề khi sử dụng khóa mutable, không có nghĩa mọi thay đổi kết quả equals sau mutation đều vi phạm tính nhất quán.

Quy tắc thực hành: ưu tiên khóa bất biến; nếu bắt buộc sửa thuộc tính định danh của một mục đã nằm trong tập băm, thường cần gỡ mục theo khóa/trạng thái cũ trước, sửa, rồi đưa lại vào tập. Không nên kỳ vọng collection tự định vị lại phần tử sau khi trạng thái khóa đổi.

## 6. Những hiểu lầm dễ gặp

**Hiểu lầm 1: “equals từng trả true thì mãi mãi phải true.”**

Sai. Tiền đề của hợp đồng là dữ liệu dùng để so sánh không bị thay đổi. Nếu y đổi từ "ready" sang "busy", phép so sánh sau có thể là false.

**Hiểu lầm 2: “Không gán lại biến x, y nên dữ liệu không đổi.”**

Sai. Các biến vẫn tham chiếu cùng đối tượng nhưng trường mutable, phần tử mảng, phần tử List hoặc đối tượng con được dùng trong equals có thể đã đổi.

**Hiểu lầm 3: “Chỉ sửa một trường không được so sánh thì equals có thể đổi.”**

Sai. Nếu equals thực sự chỉ dựa trên code và revision, sửa description không được làm kết quả thay đổi. Nếu kết quả đổi, hãy kiểm tra triển khai có vô tình dựa vào description, trạng thái ngoài hay getter có tác dụng phụ hay không.

**Hiểu lầm 4: “Dùng final cho biến tham chiếu là đủ.”**

Sai. final ngăn gán tham chiếu trường sang đối tượng khác, nhưng nếu trường trỏ tới đối tượng mutable (chẳng hạn ArrayList), nội dung đối tượng đó vẫn có thể đổi. Muốn dữ liệu so sánh bất biến phải xét cả những đối tượng con có liên quan.

**Hiểu lầm 5: “equals nhất quán thì tự động an toàn khi nhiều luồng cùng truy cập.”**

Sai. Hợp đồng equals không thay thế cơ chế đồng bộ. Nếu một luồng sửa dữ liệu so sánh trong khi luồng khác gọi equals, việc đọc có thể quan sát trạng thái thay đổi/không đồng bộ. Hãy dùng dữ liệu bất biến hoặc thiết kế đồng bộ phù hợp khi cần truy cập đồng thời.

**Hiểu lầm 6: “Chỉ cần equals đúng, hashCode không quan trọng.”**

Sai với đối tượng làm khóa băm. Khi override equals, phải override hashCode tương thích. Việc làm này không tự động giải quyết vấn đề khóa mutable sau khi chèn vào HashSet/HashMap.

## 7. Cách kiểm tra một equals có nhất quán

Khi review hoặc viết kiểm thử, hãy trả lời lần lượt:

1. Phương thức quyết định bằng nhau dựa trên trường và giá trị dẫn xuất nào của **cả hai** đối tượng?
2. Những lần gọi lại với cùng giá trị của toàn bộ dữ liệu đó có cho cùng kết quả không? Thử cả cặp bằng nhau (true) lẫn khác nhau (false).
3. Có sự phụ thuộc không cần thiết vào thời gian, random, dữ liệu toàn cục, thứ tự gọi hoặc thao tác có tác dụng phụ không?
4. Nếu các đối tượng được phép thay đổi, khi **chỉ** sửa trường liên quan, kết quả mới có được giải thích bằng thay đổi dữ liệu không? Khi chỉ sửa trường không liên quan, kết quả có được giữ nguyên không?
5. Nếu lớp dùng làm khóa HashMap/HashSet, các trường tham gia equals có được giữ ổn định trong lúc khóa ở trong collection và hashCode có dùng thông tin tương ứng không?

Một phép kiểm tra nhanh cho đối tượng không bị sửa trong khoảng thử:

~~~java
boolean first = x.equals(y);
boolean second = x.equals(y);
if (first != second) {
    throw new AssertionError("equals không nhất quán khi dữ liệu so sánh giữ nguyên");
}
~~~

Đây là đoạn minh họa đặt trong ngữ cảnh đã có x và y; nó không chứng minh toàn bộ hợp đồng equals, và chỉ có ý nghĩa khi dữ liệu so sánh thực sự không thay đổi trong khoảng giữa hai lời gọi. Kiểm thử tốt nên lặp lại với nhiều cặp trạng thái, đồng thời kiểm tra phản xạ, đối xứng, bắc cầu, null và quan hệ equals/hashCode.

## 8. Ghi nhớ

**Điều kiện chính xác:** *Cùng hai đối tượng + không đổi thông tin mà equals dùng để so sánh → kết quả equals lặp lại phải giữ nguyên.*

Thay đổi dữ liệu so sánh có thể làm đổi kết quả một cách hợp lệ. Điều cần tránh là để equals cho kết quả thất thường khi dữ liệu giá trị vẫn nguyên vẹn. Ưu tiên cách so sánh xác định, không có tác dụng phụ; với khóa của cấu trúc băm, giữ các thuộc tính định danh ổn định trong suốt thời gian lưu khóa.