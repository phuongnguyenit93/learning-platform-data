# Hash code hằng có thể đúng hợp đồng nhưng phân bố kém

## 1. Ý nghĩa của một hash code

Trong Java, phương thức `hashCode()` trả về một số nguyên `int` đại diện cho kết quả băm của đối tượng. Các cấu trúc dựa trên băm như `HashMap` và `HashSet` sử dụng kết quả này để định hướng việc tìm kiếm, chèn và xóa phần tử. **Hash code không phải mã định danh duy nhất** và không tự quyết định hai đối tượng có bằng nhau hay không: `equals(Object)` mới là phép kiểm tra bình đẳng cuối cùng khi các đối tượng có hash liên quan trùng nhau.

Hợp đồng của `Object.hashCode()` có các điểm quan trọng:

1. Nếu gọi `hashCode()` nhiều lần trên cùng một đối tượng trong một lần thực thi ứng dụng, khi dữ liệu dùng bởi `equals` không thay đổi thì kết quả phải nhất quán.
2. **Nếu `a.equals(b)` là `true`, `a.hashCode() == b.hashCode()` bắt buộc cũng phải là `true`.** Đây là ràng buộc quan trọng nhất khi ghi đè cả hai phương thức.
3. Nếu `a.equals(b)` là `false`, hai hash code **được phép bằng nhau**. Trả về hash khác nhau cho các đối tượng không bằng nhau là mục tiêu hiệu năng, không phải điều kiện bắt buộc để đúng hợp đồng.

Do đó, một lớp có thể định nghĩa:

~~~java
@Override
public int hashCode() {
    return 1;
}
~~~

Đây là **đoạn phương thức minh họa**, không phải một chương trình độc lập. Với mọi cặp đối tượng bằng nhau, hai giá trị hash đều là `1`, nên điều kiện bắt buộc được thỏa mãn. Nếu lớp có `equals` hợp lệ, một hash code hằng và ổn định có thể **đúng về ngữ nghĩa hợp đồng**, dù lựa chọn đó thường rất kém khi dùng trong bảng băm.

Điều cần phân biệt là **đúng hợp đồng** và **phân bố tốt**: hai yêu cầu này liên quan nhưng không đồng nhất.

## 2. Hash code hằng làm phân bố kém như thế nào?

Một bảng băm tổ chức các mục vào những vị trí gọi là *bucket* (nhóm lưu trữ). `HashMap` áp dụng thao tác trộn bit lên hash code rồi dùng kết quả cùng kích thước bảng để xác định bucket. Các hash code khác nhau có thể vẫn rơi vào cùng bucket, nhưng **mọi khóa có cùng hash code sẽ đi vào cùng bucket** tại một trạng thái bảng nhất định.

Nếu mọi khóa trả về `1`:

- `new Key(101)`, `new Key(102)` và `new Key(103)` có thể đều khác nhau theo `equals`.
- Chúng vẫn có cùng hash code, vì `hashCode()` luôn trả `1`.
- Khi lưu trong `HashMap` hoặc `HashSet`, các mục liên tục tranh cùng một bucket. Cấu trúc phải phân biệt chúng bằng kiểm tra khóa (bao gồm `equals`) thay vì nhanh chóng thu hẹp sang nhiều bucket khác nhau.

Trong bảng được phân bố tốt, nhiều thao tác `put`, `get`, `containsKey` hay `contains` có chi phí trung bình gần `O(1)` trong điều kiện thông thường. Khi một bucket có rất nhiều phần tử, thao tác có thể phải xem xét nhiều ứng viên hơn; với cách xử lý va chạm bằng danh sách, quét một bucket có `n` phần tử có thể tốn `O(n)`. Những phiên bản Java hiện đại có cơ chế chuyển một số bucket lớn của `HashMap` thành cấu trúc cây để giảm tác động trong các điều kiện phù hợp, nhưng điều đó **không khiến chiến lược hash code hằng trở nên tốt**. Hành vi chi tiết phụ thuộc số phần tử, năng lực của bảng và hình dạng các khóa.

`HashSet` được triển khai dựa trên `HashMap`, nên cũng chịu tác động tương tự của việc nhiều phần tử có chung hash code.

**Va chạm hash (collision) không làm mất phần tử.** Một bộ sưu tập băm triển khai đúng vẫn lưu được hai khóa khác nhau cùng hash; khi cần xác định khóa chính xác, nó kiểm tra bình đẳng. Vấn đề chủ yếu là số ứng viên phải xét tăng lên và hiệu năng dự kiến có thể suy giảm.

## 3. Ví dụ Java 17: đúng kết quả nhưng cách băm khác nhau

Ví dụ sử dụng hai loại khóa có cùng quy tắc bình đẳng: hai đối tượng **trong cùng loại khóa** được xem là bằng nhau nếu có cùng `id`. Loại `ConstantKey` trả về `7` cho mọi đối tượng; loại `IdKey` sử dụng `Integer.hashCode(id)` nên phản ánh giá trị `id`.

Lưu chương trình trong tệp **ConstantHashDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class ConstantHashDemo {
    static final class ConstantKey {
        private final int id;

        ConstantKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ConstantKey that)) {
                return false;
            }
            return id == that.id;
        }

        @Override
        public int hashCode() {
            return 7;
        }
    }

    static final class IdKey {
        private final int id;

        IdKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof IdKey that)) {
                return false;
            }
            return id == that.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        ConstantKey one = new ConstantKey(1);
        ConstantKey sameOne = new ConstantKey(1);
        ConstantKey two = new ConstantKey(2);

        System.out.println("equal keys: " + one.equals(sameOne));
        System.out.println("equal keys share hash: "
                + (one.hashCode() == sameOne.hashCode()));
        System.out.println("different keys: " + one.equals(two));
        System.out.println("different keys collide: "
                + (one.hashCode() == two.hashCode()));

        Set<ConstantKey> constantSet = new HashSet<>();
        constantSet.add(one);
        constantSet.add(sameOne);
        constantSet.add(two);
        System.out.println("constant set size: " + constantSet.size());
        System.out.println("constant set contains id=2: "
                + constantSet.contains(new ConstantKey(2)));

        Map<ConstantKey, String> constantMap = new HashMap<>();
        constantMap.put(one, "one");
        constantMap.put(two, "two");
        System.out.println("constant map lookup id=2: "
                + constantMap.get(new ConstantKey(2)));

        IdKey idOne = new IdKey(1);
        IdKey idTwo = new IdKey(2);
        System.out.println("id hashes: "
                + idOne.hashCode() + ", " + idTwo.hashCode());

        Set<IdKey> idSet = new HashSet<>();
        idSet.add(idOne);
        idSet.add(idTwo);
        idSet.add(new IdKey(1));
        System.out.println("id set size: " + idSet.size());
        System.out.println("id set contains id=2: "
                + idSet.contains(new IdKey(2)));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ConstantHashDemo.java
java ConstantHashDemo
~~~

Kết quả chuẩn:

~~~text
equal keys: true
equal keys share hash: true
different keys: false
different keys collide: true
constant set size: 2
constant set contains id=2: true
constant map lookup id=2: two
id hashes: 1, 2
id set size: 2
id set contains id=2: true
~~~

Những điều rút ra từ kết quả:

1. `one` và `sameOne` bằng nhau theo `equals` và cùng hash `7`. Hợp đồng được giữ đúng.
2. `one` và `two` không bằng nhau nhưng vẫn cùng hash `7`. Đây là **va chạm hợp lệ**, không phải một vi phạm hợp đồng.
3. `HashSet` chứa hai phần tử khác nhau, thay vì gộp tất cả đối tượng cùng hash thành một. Thêm `sameOne` không tăng kích thước vì nó bằng `one`.
4. `HashMap.get(new ConstantKey(2))` vẫn lấy được giá trị `"two"`, chứng tỏ tra cứu vẫn **đúng** khi có va chạm.
5. `IdKey` tạo hash `1` và `2` cho hai `id` tương ứng; đây là tín hiệu phân biệt tốt hơn với tập khóa này. Tuy nhiên, **hai hash khác nhau chưa bảo đảm sẽ thuộc hai bucket khác nhau**, vì bucket còn phụ thuộc cách tổ chức bảng.

Ví dụ trên minh họa **tính đúng đắn**, không phải bài đo tốc độ. Không thể kết luận chênh lệch thời gian từ output: một phép đo đáng tin cần số lượng khóa phù hợp, warm-up JVM, lặp lại nhiều lần và tránh nhiễu từ GC, JIT cùng môi trường chạy. Khi phân tích hiệu năng Java nghiêm túc, có thể dùng công cụ benchmark chuyên dụng như JMH thay vì suy luận từ một lần chạy `System.nanoTime()`.

## 4. Phân biệt phép bằng và mã băm trong mọi trường hợp

| Trạng thái hai đối tượng | Điều kiện về hashCode | Có thể xem bằng nhau không? |
| --- | --- | --- |
| `a.equals(b)` là `true` | **Phải** có `a.hashCode() == b.hashCode()` | Có |
| `a.equals(b)` là `false`, hash khác nhau | Hoàn toàn hợp lệ | Không |
| `a.equals(b)` là `false`, hash giống nhau | Hoàn toàn hợp lệ: va chạm | Không |
| Hash giống nhau nhưng chưa gọi `equals` | Không đủ thông tin để xác định bình đẳng | Phải dùng `equals` theo hợp đồng |

Không được thay `equals` bằng phép so sánh hash code:

~~~java
// Sai: cùng hash code không chứng minh hai đối tượng bằng nhau.
return this.hashCode() == other.hashCode();
~~~

Đây là **biểu thức minh họa lỗi trong phương thức equals**, không phải chương trình độc lập. Nó còn thiếu bước kiểm tra `other` khác `null`, đúng kiểu và có thể dẫn đến sai nghĩa bình đẳng. Với lớp trả về hash code hằng, cách triển khai này khiến mọi đối tượng khác nhau của lớp bị coi là bằng nhau, phá hỏng ý nghĩa của `equals`.

Cũng không nên viết kiểm thử kiểu `assertNotEquals(a.hashCode(), b.hashCode())` cho mọi `a` và `b` khác nhau. Hợp đồng không đòi hỏi hash code khác nhau cho mọi đối tượng không bằng nhau. Thay vào đó, kiểm thử tính đúng đắn của `equals`, tính nhất quán `hashCode` khi bằng nhau, và những thuộc tính phân bố đủ tốt đối với tập dữ liệu thực tế khi hiệu năng là yêu cầu.

## 5. Chọn hashCode tốt hơn mà vẫn giữ hợp đồng

### 5.1. Dùng đúng các trường quyết định bình đẳng

Nếu `equals` dựa trên `id` kiểu `int`, có thể dùng:

~~~java
@Override
public int hashCode() {
    return Integer.hashCode(id);
}
~~~

Đây là **phương thức có thể đặt trong IdKey**, không phải một chương trình độc lập. Với `int`, `Integer.hashCode(id)` chính là giá trị `id`. Cùng `id` thì vừa bằng nhau vừa cho cùng hash; nhiều `id` khác nhau tạo ra hash khác nhau, giảm va chạm trong tập khóa thông dụng so với trả về hằng số.

Nếu `equals` dựa trên hai trường `code` và `version`, một cách diễn đạt đơn giản là:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(code, version);
}
~~~

Đây là **đoạn phương thức minh họa trong lớp có hai trường tương ứng**. `Objects.hash` hỗ trợ các trường có thể là `null` và kết hợp hash theo thứ tự đối số. Nó tiện đọc, nhưng có thể phát sinh chi phí do varargs/boxing trong những đường xử lý rất nóng; nếu cần tối ưu thật sự, đo lường trước rồi cân nhắc cách kết hợp hash thủ công.

Một mẫu kết hợp cho hai trường tham chiếu là:

~~~java
@Override
public int hashCode() {
    int result = java.util.Objects.hashCode(code);
    result = 31 * result + java.util.Objects.hashCode(version);
    return result;
}
~~~

Đoạn này cũng cần đặt trong lớp có `code` và `version`. `Objects.hashCode(field)` trả `0` khi trường `null`, tránh `NullPointerException`. Giá trị `31` là một hệ số phổ biến, không phải quy định bắt buộc của hợp đồng. Phép nhân và cộng `int` có thể tràn số theo ngữ nghĩa Java mà vẫn tạo hash code hợp lệ. Dù dùng cách nào, **tập trường quyết định `hashCode` phải phù hợp với tiêu chí bình đẳng của `equals`**.

### 5.2. Tránh các chiến lược băm không đáng tin cậy

- **Hằng số:** đúng hợp đồng nếu ổn định và `equals` đúng, nhưng tạo va chạm có hệ thống giữa mọi khóa.
- **Số ngẫu nhiên mỗi lần gọi:** vi phạm tính nhất quán ngay cả khi đối tượng không đổi; tra cứu sau khi đưa vào bảng băm có thể thất bại.
- **Thời gian hiện tại hoặc bộ đếm toàn cục thay đổi:** gây biến thiên giữa các lần gọi và không phản ánh các trường quyết định bình đẳng.
- **`System.identityHashCode(this)` cho đối tượng bình đẳng theo giá trị:** hai đối tượng khác tham chiếu nhưng bằng nhau theo `equals` có thể có identity hash khác nhau, dẫn đến vi phạm hợp đồng.
- **Trường có thể sửa đổi trong lúc là khóa `HashMap`/phần tử `HashSet`:** hash có thể thay đổi sau khi đối tượng đã nằm trong bucket cũ, làm `get`, `contains` hoặc `remove` không còn tìm thấy đối tượng đó theo cách mong đợi.

Ưu tiên dùng các thuộc tính mang tính định danh hoặc giá trị **ổn định, phù hợp với `equals`**. Đối tượng khóa bất biến có trường `final` thường giúp bảo đảm tính nhất quán dễ dàng hơn. Nếu trường tham gia `equals` được phép thay đổi, phải quản lý việc dùng đối tượng làm khóa thật cẩn thận.

## 6. Vì sao không tối ưu hashCode bằng mọi giá?

Một hash code có chất lượng phân bố tốt là hash code giúp các khóa thực tế được trải tương đối đều trên các bucket, hạn chế các bucket quá đông. Tuy vậy, không tồn tại hàm băm `int` duy nhất cho mọi đối tượng: không gian khóa có thể lớn hơn số lượng giá trị `int`, nên về nguyên tắc **va chạm là không tránh khỏi**. Mục tiêu là giảm số va chạm có thể tránh được và tránh phân bố xấu trên dữ liệu sẽ dùng, chứ không đòi hỏi mọi khóa một mã duy nhất.

Chất lượng băm phải được cân bằng với chi phí tính toán. Một phép băm cực kỳ phức tạp cho vài khóa có thể tốn thời gian hơn lợi ích giảm va chạm. Với các lớp thông thường, sử dụng `Integer.hashCode`, `String.hashCode`, `Objects.hash` hoặc các phương thức băm thích hợp khác của kiểu dữ liệu thường là điểm khởi đầu hợp lý. Không nên tự xây dựng hàm băm tùy biến khi chưa có nhu cầu và bằng chứng.

Ngoài ra, các kiểu dữ liệu có biểu diễn băm riêng có thể xuất hiện va chạm khác nhau, ví dụ `String.hashCode()` không cam kết không trùng nhau. Sự tồn tại của va chạm đơn lẻ không làm hàm băm đó sai. Chỉ khi phân bố thường xuyên dẫn đến nhiều mục cùng bucket thì hiệu năng mới bị ảnh hưởng đáng kể.

## 7. Checklist kiểm tra một triển khai hashCode

Trước khi sử dụng một lớp làm phần tử của `HashSet` hoặc khóa của `HashMap`, hãy kiểm tra:

1. Mọi cặp đối tượng **bằng nhau theo `equals`** có **cùng hash code** không?
2. Những lần gọi `hashCode()` trên đối tượng không đổi có cùng kết quả trong lần thực thi không?
3. Hàm băm có dựa trên các trường xác định bình đẳng và không phụ thuộc số ngẫu nhiên, thời gian hay thông tin biến thiên ngoài ý muốn không?
4. Các trường nullable có được xử lý an toàn không?
5. Đối tượng có bị sửa những trường liên quan đến `equals`/`hashCode` trong thời gian nằm trong collection không?
6. Với nhiều khóa thực tế không bằng nhau, liệu số lượng mã băm trùng nhau có đang cao bất thường không? Nếu có, cần xem lại cách phối hợp trường và đo hiệu năng thay vì kết luận dựa vào một ví dụ nhỏ.

**Kết luận cần nhớ:** Hàm `hashCode()` luôn trả về cùng một số có thể **đúng hợp đồng** vì các đối tượng bằng nhau chắc chắn có cùng hash. Nhưng mọi khóa cũng trở thành trường hợp va chạm, làm mất lợi thế phân bố của cấu trúc băm. Hãy phân biệt **đúng kết quả** với **hiệu năng tốt**, và thiết kế `hashCode` nhất quán với `equals` từ những dữ liệu ổn định của đối tượng.