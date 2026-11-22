# Giữ equals() dễ hiểu, không gây tác dụng phụ và không ném lỗi cho dữ liệu thông thường

## 1. Mục tiêu khi cài đặt equals(Object)

`equals(Object)` trả lời một câu hỏi: **đối tượng nhận lời gọi có được xem là bằng đối tượng được truyền vào không?** Khi cài đặt phương thức này, một thiết kế tốt cần đồng thời đạt ba yêu cầu thực tế:

1. **Dễ hiểu:** người đọc nhìn vào có thể biết ngay lớp sử dụng những thuộc tính nào để xác định bình đẳng, điều kiện nào trả về `true` và điều kiện nào trả về `false`.
2. **Không gây tác dụng phụ:** việc gọi `equals` chỉ quan sát những dữ liệu phục vụ so sánh; không đổi trạng thái đối tượng, không sửa đối số, không ghi dữ liệu ra nơi khác và không kích hoạt công việc nghiệp vụ.
3. **Không ném lỗi cho dữ liệu thông thường:** `null`, đối tượng khác kiểu và các trường dữ liệu được phép mang `null` phải được xử lý đúng, thay vì vô tình phát sinh `NullPointerException` hoặc `ClassCastException`.

Đây là các nguyên tắc thiết kế khi **cài đặt** hợp đồng `Object.equals(Object)`. Đặc biệt, với mọi đối tượng `x` khác `null`, `x.equals(null)` phải trả về `false`. Việc gọi `x.equals(y)` khi chính `x == null` vẫn gây `NullPointerException`: không có phương thức thể hiện nào được thực thi trên tham chiếu `null`.

Không nên diễn giải yêu cầu “không ném lỗi” thành cam kết rằng mọi lỗi JVM, đối tượng có trạng thái hỏng hoặc mọi tình huống bất thường đều bị nuốt đi. Mục tiêu ở đây là **không biến các đầu vào so sánh hợp lệ, thường gặp thành ngoại lệ**; dữ liệu bất hợp lệ nên được xác minh ở ranh giới tạo hoặc cập nhật đối tượng.

## 2. Vì sao equals cần thuần và ổn định?

Những thành phần thư viện như `HashSet`, `HashMap` và các thuật toán tìm kiếm có thể gọi `equals` nhiều lần, với thứ tự hay tần suất phụ thuộc cách chúng vận hành. Chúng dựa vào hợp đồng bình đẳng gồm tính phản xạ, đối xứng, bắc cầu, nhất quán và quy tắc với `null`.

Nếu `equals` tăng bộ đếm, cập nhật thuộc tính, tiêu thụ một phần tử từ iterator, gọi mạng, ghi cơ sở dữ liệu hoặc gửi sự kiện, việc **chỉ kiểm tra bình đẳng** đã tạo ra biến đổi không mong đợi. Nếu kết quả phụ thuộc thời gian, trạng thái dịch vụ bên ngoài hay số lần so sánh, hai đối tượng có thể lúc bằng, lúc không dù dữ liệu dùng làm khóa bình đẳng không đổi. Hành vi đó khó kiểm thử và có thể làm việc tra cứu trong collection không đáng tin cậy.

Phân biệt:

| Tính chất | Cách làm nên chọn | Dấu hiệu cần tránh |
| --- | --- | --- |
| Phép so sánh | Kiểm tra danh tính, kiểu và các trường quyết định bình đẳng | Lồng nhiều nhánh nghiệp vụ hoặc tìm dữ liệu từ dịch vụ ngoài |
| Trạng thái | Chỉ đọc thuộc tính ổn định | Tự tăng `comparisonCount`, đánh dấu “đã kiểm tra”, cập nhật đối tượng |
| Giá trị thiếu hợp lệ | So sánh an toàn bằng `Objects.equals` | Gọi phương thức trên trường nullable mà không kiểm tra |
| Kiểu khác | Trả về `false` | Ép kiểu vô điều kiện rồi nhận `ClassCastException` |
| Độ ổn định | Cùng dữ liệu, cùng kết quả khi không có thay đổi liên quan | Phụ thuộc ngẫu nhiên, đồng hồ hoặc dữ liệu mạng |

Một phương thức `equals` tốt thường ngắn: kiểm tra có phải cùng tham chiếu, kiểm tra kiểu, rồi so sánh từng trường quyết định bình đẳng. Việc sử dụng `instanceof` hay `getClass()` phải phù hợp với chính sách bình đẳng của hệ phân cấp lớp; ví dụ dưới đây dùng lớp `final`, nên không phát sinh khác biệt giữa các lớp con.

## 3. Ví dụ Java 17 chạy được: đối tượng giá trị bất biến

Giả sử khóa tài liệu được xác định bởi `code` bắt buộc và `edition` được phép `null`. Hai khóa bằng nhau khi **cả hai** trường tương ứng bằng nhau. Vì mã tài liệu không được để trống tham chiếu, constructor xác thực `code` lúc tạo; phép so sánh không cần xử lý một trạng thái nội bộ vốn đã bị cấm.

Lưu chương trình sau vào **EqualsDesignDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualsDesignDemo {
    static final class DocumentKey {
        private final String code;
        private final String edition; // Được phép null

        DocumentKey(String code, String edition) {
            this.code = Objects.requireNonNull(code, "code");
            this.edition = edition;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof DocumentKey that)) {
                return false; // Gồm cả null và đối tượng khác kiểu
            }
            return code.equals(that.code)
                    && Objects.equals(edition, that.edition);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, edition);
        }
    }

    public static void main(String[] args) {
        DocumentKey a = new DocumentKey("D-07", null);
        DocumentKey same = new DocumentKey("D-07", null);
        DocumentKey newer = new DocumentKey("D-07", "v2");

        System.out.println("self: " + a.equals(a));
        System.out.println("equal values: " + a.equals(same));
        System.out.println("symmetric: " + same.equals(a));
        System.out.println("different edition: " + a.equals(newer));
        System.out.println("null: " + a.equals(null));
        System.out.println("other type: " + a.equals("D-07"));
        System.out.println("same hash: " + (a.hashCode() == same.hashCode()));

        Set<DocumentKey> keys = new HashSet<>();
        keys.add(a);
        System.out.println("HashSet contains equal key: " + keys.contains(same));

        boolean first = a.equals(same);
        boolean second = a.equals(same);
        System.out.println("repeated result: " + (first == second));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac EqualsDesignDemo.java
java EqualsDesignDemo
~~~

Kết quả:

~~~text
self: true
equal values: true
symmetric: true
different edition: false
null: false
other type: false
same hash: true
HashSet contains equal key: true
repeated result: true
~~~

**Tại sao mã này đáp ứng mục tiêu?**

- `this == other` cho kết quả `true` khi so sánh đối tượng với chính nó, không cần kiểm tra từng trường.
- `other instanceof DocumentKey that` chỉ thành công khi `other` khác `null` và đúng kiểu cần so sánh. `null instanceof DocumentKey` là `false`; đối số khác kiểu cũng được trả về `false` mà không ép kiểu sai.
- `code` được xác thực không `null` khi tạo và là `final`, nên `code.equals(that.code)` an toàn đối với mọi đối tượng `DocumentKey` được xây dựng hợp lệ.
- `edition` có thể là `null`. `Objects.equals(edition, that.edition)` cho `true` khi cả hai cùng `null`, `false` khi chỉ một bên `null` và dùng `String.equals` khi cần; **đây là phép so sánh hai trường dữ liệu**, không phải việc so sánh cả `DocumentKey` với `null`.
- Không có phép gán cho trường, đọc/ghi tệp, logging, truy cập mạng hay cập nhật tham số trong `equals`. Cả hai thuộc tính là chuỗi bất biến và được giữ bằng trường `final`, nên những lần so sánh lặp lại với cùng đối tượng không đổi cho cùng kết quả.
- `hashCode()` dùng đúng các trường tham gia `equals`. Những đối tượng bằng nhau có cùng mã băm, đáp ứng điều kiện cần của hợp đồng khi đưa vào `HashSet` hoặc làm khóa `HashMap`. Chiều ngược lại **không bắt buộc**: mã băm bằng nhau chưa chứng minh hai đối tượng bằng nhau.

Dòng `repeated result: true` cho thấy hai kết quả trong ví dụ trùng nhau. Một kiểm thử như vậy **chưa đủ tự nó chứng minh** phương thức không có tác dụng phụ: để bảo đảm điều đó phải xem xét code và có thể kiểm tra trạng thái đối tượng trước/sau các lần gọi.

## 4. Các lỗi triển khai thường gặp

### 4.1. Ép kiểu trước khi kiểm tra

~~~java
@Override
public boolean equals(Object other) {
    DocumentKey that = (DocumentKey) other;
    return code.equals(that.code);
}
~~~

Đây là **đoạn mã minh họa lỗi trong lớp DocumentKey**, không phải chương trình độc lập. Nếu `other == null`, phép ép kiểu trả về `null`, nhưng `that.code` gây `NullPointerException`. Nếu `other` thuộc kiểu không tương thích, phép ép kiểu có thể gây `ClassCastException`.

Sửa bằng `instanceof` hoặc kiểm tra `null` và kiểu trước khi truy cập các trường. Cách này đồng thời giúp người đọc thấy rõ trường hợp từ chối bình đẳng.

### 4.2. Gọi equals trên trường có thể null

~~~java
return code.equals(that.code)
        && edition.equals(that.edition); // Có thể ném NullPointerException
~~~

Đây là **biểu thức minh họa lỗi bên trong equals**. `edition` được phép `null`, nên `edition.equals(...)` không an toàn. Viết `Objects.equals(edition, that.edition)` để biểu đạt rõ cả hai bên đều có thể vắng mặt.

Không cần dùng `Objects.equals` cho mọi trường theo thói quen: nếu bất biến của lớp bảo đảm trường không `null`, gọi `code.equals(...)` vẫn dễ hiểu và an toàn.

### 4.3. Biến việc so sánh thành một thao tác cập nhật

~~~java
private int comparisonCount;

@Override
public boolean equals(Object other) {
    comparisonCount++; // Tác dụng phụ: chỉ đọc bình đẳng cũng đổi trạng thái
    // ... thực hiện so sánh
}
~~~

Đây là **mã minh họa chống mẫu (antipattern)**, không phải chương trình chạy độc lập. Ngay cả khi bộ đếm không làm thay đổi kết quả, phương thức vẫn tạo tác dụng phụ và có thể có vấn đề khi nhiều luồng cùng so sánh. Việc ghi log, chỉnh sửa đối tượng đầu vào, làm sạch trường dữ liệu ngay trong `equals`, lưu dữ liệu hay phát sự kiện cũng không nên nằm trong đường đi so sánh.

Nếu cần chuẩn hóa `code` để so sánh không phân biệt hoa/thường hoặc loại khoảng trắng, hãy định nghĩa quy tắc rõ ràng và **chuẩn hóa khi xây dựng giá trị**, hoặc sử dụng phép so sánh thuần túy phù hợp; đừng âm thầm sửa trường trong `equals`. Quy tắc chuẩn hóa phải nhất quán với `hashCode`.

### 4.4. Dùng dịch vụ bên ngoài làm tiêu chí so sánh

Ví dụ, `equals` gọi API để lấy tên hiện tại, hoặc truy vấn cơ sở dữ liệu để xem hai mã có còn ánh xạ tới cùng hồ sơ hay không. Lúc này câu trả lời phụ thuộc trạng thái dịch vụ, lỗi mạng và thời điểm gọi; kết quả có thể đổi khi các trường của hai đối tượng không đổi.

Hãy tách thao tác tra cứu hay cập nhật trạng thái khỏi `equals`. Nếu bình đẳng thực sự cần một giá trị từ hệ thống khác, quyết định trước giá trị sẽ được chụp và lưu trong đối tượng như thế nào. Với đối tượng bất biến, chỉ dùng những trường dữ liệu đã được xác định lúc tạo.

### 4.5. Nuốt tất cả lỗi bằng catch

~~~java
@Override
public boolean equals(Object other) {
    try {
        DocumentKey that = (DocumentKey) other;
        return code.equals(that.code);
    } catch (Exception ignored) {
        return false;
    }
}
~~~

Đây là **đoạn minh họa lỗi**, không phải chương trình độc lập. `catch (Exception)` che dấu lỗi triển khai và đánh đồng lỗi lập trình với “không bằng nhau”. Nó cũng khiến việc phát hiện trạng thái hỏng khó hơn.

Sửa trực tiếp nguyên nhân: kiểm tra kiểu, xử lý trường nullable an toàn, xác thực bất biến khi tạo đối tượng. Trả về `false` cho trường hợp bình thường là khác kiểu hoặc `null`; không cần ngoại lệ làm điều khiển luồng cho chúng.

### 4.6. Gọi Objects.equals(this, other) ngay trong equals

~~~java
@Override
public boolean equals(Object other) {
    return Objects.equals(this, other);
}
~~~

Đoạn này cũng **không hợp lệ làm triển khai equals**. Với `this` và `other` không cùng tham chiếu nhưng đều khác `null`, `Objects.equals(this, other)` sẽ gọi lại `this.equals(other)`, gây đệ quy không dừng và cuối cùng có thể dẫn đến `StackOverflowError`. `Objects.equals` phù hợp để so sánh **các trường dữ liệu** trong `equals` hoặc hai đối tượng nullable ở bên ngoài phương thức.

## 5. Giữ logic dễ đọc nhưng vẫn đúng hợp đồng

Một thứ tự triển khai thường hợp lý là:

1. Xác nhận `this == other`.
2. Loại trường hợp `null` và sai kiểu bằng một phép kiểm tra kiểu rõ ràng.
3. So sánh các trường thật sự quyết định bình đẳng, với xử lý `null` đúng theo bất biến của từng trường.
4. Ghi đè `hashCode` từ cùng tập trường và duy trì tính ổn định trong thời gian dùng đối tượng làm khóa.

Tránh mở rộng phép so sánh sang các trường chỉ mang tính trình bày, dữ liệu tạm, bộ đếm truy cập hoặc thông tin có thể thay đổi độc lập với danh tính nghiệp vụ, trừ khi mô hình bình đẳng **thực sự** yêu cầu chúng. Nếu lớp cần thay đổi các trường tham gia `equals`/`hashCode`, hãy đánh giá tác động tới `HashSet`/`HashMap`: thay đổi mã băm khi đối tượng đang là phần tử/khóa có thể khiến tra cứu thất bại. Khi có thể, hãy ưu tiên đối tượng giá trị bất biến.

Cũng cần tránh việc cố “tối ưu” bằng cách ghi bộ nhớ đệm có thể biến đổi trong `equals`. Ngay cả bộ nhớ đệm không làm đổi kết quả logic vẫn có thể kéo theo tác dụng phụ, vấn đề đồng bộ hoặc độ phức tạp không cần thiết. Nếu cần tối ưu vì số liệu đo lường thực tế, hãy thiết kế giải pháp riêng và kiểm chứng toàn bộ hợp đồng.

## 6. Kiểm tra khi hoàn thành

Với một phương thức `equals` tự cài đặt, hãy tự trả lời:

- `x.equals(x)` có `true` với mọi đối tượng `x` hợp lệ không?
- `x.equals(null)` có trả `false`, và `x.equals(objKhacKieu)` có trả `false` mà không ném `ClassCastException` không?
- Các trường nullable hợp lệ có được so sánh mà không ném `NullPointerException` không?
- Hai đối tượng bằng nhau có cho cùng `hashCode` không? Kết quả có đối xứng, bắc cầu và nhất quán khi các trường liên quan không đổi không?
- Có phép gán, đọc/ghi tài nguyên, truy vấn mạng, logging hay thay đổi đối tượng đầu vào bên trong `equals` không?
- Các thuộc tính quyết định bình đẳng có ổn định trong thời gian đối tượng được dùng làm khóa hoặc phần tử trong cấu trúc băm không?

Có thể chuyển các câu hỏi này thành kiểm thử JUnit: gọi `equals` nhiều lần, so sánh hai chiều, đưa phần tử vào `HashSet` rồi tra cứu bằng một đối tượng bằng nó, kiểm tra `null`/sai kiểu/trường nullable và bảo đảm trạng thái quan sát được không đổi. Kiểm thử bổ sung bảo vệ hợp đồng; việc kiểm tra mã nguồn vẫn cần thiết để xác định không có tác dụng phụ ẩn.

**Ghi nhớ:** `equals(Object)` nên là phép kiểm tra bình đẳng rõ ràng, ổn định, không cập nhật trạng thái và trả kết quả bình thường cho `null`, khác kiểu cùng các giá trị nullable hợp lệ. Thiết kế bất biến và dùng đúng các trường trong `hashCode` giúp hành vi đó bền vững khi đối tượng tham gia collection.