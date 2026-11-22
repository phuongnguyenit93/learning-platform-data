# Đối tượng không bằng nhau vẫn được phép trùng hash code

Trong Java, `hashCode()` trả về một số nguyên kiểu `int` dùng để hỗ trợ các cấu trúc tra cứu dựa trên băm, chẳng hạn `HashMap` và `HashSet`. **Hash code không phải mã định danh duy nhất của một đối tượng.** Hai đối tượng **không bằng nhau theo `equals`** vẫn hoàn toàn có thể nhận **cùng một hash code**. Hiện tượng này gọi là **hash collision** (va chạm băm).

Điều bắt buộc của hợp đồng `hashCode` là chiều ngược lại: nếu `x.equals(y)` trả `true`, thì `x.hashCode()` **phải bằng** `y.hashCode()`. Phân biệt chính xác hai chiều suy luận này là điều kiện để cài đặt `equals`, `hashCode` và sử dụng Java collections đúng.

## 1. Hợp đồng `hashCode`: yêu cầu gì và không yêu cầu gì?

Với hai đối tượng không `null` là `x` và `y`, điều kiện thiết yếu là:

~~~text
x.equals(y) == true  =>  x.hashCode() == y.hashCode()
~~~

Đó là **mệnh đề một chiều**. Bảng sau phân biệt các trường hợp:

| `x.equals(y)` | `x.hashCode() == y.hashCode()` | Có hợp lệ không? | Ý nghĩa |
| --- | --- | --- | --- |
| `true` | `true` | **Bắt buộc** | Bằng nhau theo `equals` thì phải cùng hash code. |
| `true` | `false` | **Sai hợp đồng** | Hai giá trị bằng nhau lại có mã băm khác nhau. |
| `false` | `true` | **Hợp lệ** | Hai giá trị khác nhau trùng hash code: một collision. |
| `false` | `false` | **Hợp lệ** | Hai giá trị khác nhau và có hash code khác nhau. |

Không được suy luận:

~~~text
x.hashCode() == y.hashCode()  =>  x.equals(y)
~~~

Suy luận này **sai**. Hash bằng nhau chỉ nói rằng hai đối tượng có cùng kết quả của hàm băm, **không** xác nhận chúng bằng nhau theo nghiệp vụ hay có cùng danh tính.

Bên cạnh đó, hợp đồng `hashCode` còn yêu cầu nhiều lần gọi `hashCode()` trên một đối tượng trong cùng một lần chạy Java phải cho cùng kết quả **nếu thông tin dùng trong phép so sánh `equals` không bị thay đổi**. Java không yêu cầu một đối tượng luôn có cùng hash code giữa các lần chạy JVM khác nhau; một số kiểu như `String` có thuật toán hash được xác định, nhưng không nên suy rộng bảo đảm đó sang mọi lớp.

### Vì sao va chạm băm là điều không thể tránh nói chung?

`hashCode()` trả về một `int` 32 bit, tức chỉ có **2³² giá trị bit khác nhau**. Trong khi đó số lượng giá trị hay trạng thái đối tượng có thể lớn hơn rất nhiều. Khi ánh xạ nhiều giá trị đầu vào hơn số kết quả có thể có vào một số nguyên 32 bit, theo nguyên lý chuồng bồ câu, ít nhất hai giá trị đầu vào sẽ phải cùng hash code.

Vì thế, **hàm băm tốt nhằm phân bố giá trị hiệu quả và nhất quán với `equals`**, chứ không thể hứa rằng mọi đối tượng không bằng nhau đều nhận một hash khác nhau.

## 2. Ví dụ xác định được: `"Aa"` và `"BB"`

Java `String.hashCode()` sử dụng phép tích lũy theo hệ số 31 trên các giá trị `char` UTF-16. Với hai chuỗi gồm hai ký tự:

~~~text
"Aa": 31 × 65 + 97 = 2112
"BB": 31 × 66 + 66 = 2112
~~~

Dù cùng mã băm `2112`, `"Aa".equals("BB")` vẫn là `false` vì nội dung chuỗi khác nhau.

Tệp **`StringCollisionDemo.java`** (Java 17+):

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StringCollisionDemo {
    public static void main(String[] args) {
        String first = "Aa";
        String second = "BB";

        System.out.println(first.equals(second));
        System.out.println(first.hashCode());
        System.out.println(second.hashCode());
        System.out.println(first.hashCode() == second.hashCode());

        Set<String> unique = new HashSet<>();
        unique.add(first);
        unique.add(second);
        unique.add(new String("Aa"));
        System.out.println(unique.size());
        System.out.println(unique.contains(new String("BB")));

        Map<String, Integer> scores = new HashMap<>();
        scores.put(first, 10);
        scores.put(second, 20);
        System.out.println(scores.size());
        System.out.println(scores.get("Aa"));
        System.out.println(scores.get("BB"));

        scores.put(new String("Aa"), 99);
        System.out.println(scores.size());
        System.out.println(scores.get("Aa"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StringCollisionDemo.java
java StringCollisionDemo
~~~

Kết quả chính xác:

~~~text
false
2112
2112
true
2
true
2
10
20
2
99
~~~

Phân tích:

1. `first.equals(second)` là `false`: hai chuỗi có nội dung khác nhau.
2. Hai lệnh `hashCode()` đều trả `2112`: đã xuất hiện **collision**.
3. `HashSet` nhận cả `"Aa"` và `"BB"`, vì chúng **không bằng nhau theo `equals`**; số phần tử sau hai lần thêm là hai. Thêm `new String("Aa")` không tạo giá trị phân biệt mới theo `String.equals`, nên kích thước vẫn là `2`.
4. `HashSet.contains(new String("BB"))` là `true`: tuy tham chiếu khác, đối tượng truy vấn bằng `"BB"` theo `equals`.
5. `HashMap` giữ hai ánh xạ riêng `"Aa" → 10` và `"BB" → 20`. Chúng cùng hash nhưng **khác key** theo `equals`; một entry không ghi đè entry kia.
6. Đặt lại giá trị với `new String("Aa")` thay thế giá trị của key bằng `"Aa"`, nên kích thước map vẫn là `2`, và `get("Aa")` trả `99`.

Ví dụ cố ý in ra kích thước, kiểm tra chứa và tra cứu theo key. **Không in toàn bộ `HashSet`/`HashMap` để suy luận thứ tự**, bởi thứ tự duyệt của các cấu trúc này không được hợp đồng API đảm bảo.

## 3. `HashSet` và `HashMap` xử lý collision như thế nào?

Một cách hiểu thực dụng về tra cứu dựa trên hash:

1. Collection lấy `hashCode()` của key hoặc phần tử.
2. Nó sử dụng thông tin hash để xác định một vị trí/nhóm ứng viên trong cấu trúc nội bộ.
3. Nếu có nhiều ứng viên trùng vị trí, nó vẫn phải phân biệt **key nào bằng nhau theo `equals`**.
4. Nếu hai key bằng nhau, `HashMap.put` cập nhật ánh xạ hiện có và `HashSet.add` không bổ sung phần tử mới. Nếu hai key không bằng nhau, cả hai có thể tồn tại đồng thời dù cùng hash code.

Có thể hình dung khái niệm (đây là mô hình giải thích, không phải mô tả chính xác từng bước cài đặt của mọi phiên bản JVM):

~~~text
                       hashCode()
                     /            \
               giá trị A        giá trị B
                     \            /
                 Cùng nhóm băm
                   /          \
               equals?       equals?
               /    \         /    \
             true  false    true   false
             cùng  khác     cùng   khác
             key   key      key    key
~~~

**Va chạm hash code** nghĩa là hai đối tượng có cùng giá trị `hashCode()`. Còn **va chạm bucket** nghĩa là chúng được ánh xạ vào cùng vùng lưu trữ nội bộ. Do bảng băm có số bucket giới hạn, hai hash code **khác nhau** vẫn có thể rơi vào cùng bucket. Đừng đánh đồng hai trường hợp; Java có thể trộn bit và thay đổi cách tổ chức bucket tùy phiên bản/điều kiện.

Các triển khai `HashMap` hiện đại có cơ chế quản lý các nhóm va chạm, trong một số tình huống có thể chuyển cấu trúc danh sách trong bucket sang cây. Đó là **chi tiết triển khai**, không phải cam kết rằng mọi va chạm luôn được xử lý trong một số phép so sánh cố định. Chất lượng phân bố hash vẫn ảnh hưởng hiệu năng.

### Hai ý cần nhớ với collection

- **Tính đúng:** cùng hash code **không đủ để kết luận trùng key**. Collection còn cần áp dụng quy tắc bằng nhau của key.
- **Hiệu năng:** nhiều key khác nhau bị dồn vào cùng nhóm có thể làm tăng số lần kiểm tra hoặc chi phí tra cứu. Mã băm có phân bố tốt thường giúp `HashMap`/`HashSet` hoạt động hiệu quả hơn.

Vì vậy, một collision riêng lẻ **không phải bug**. Bug xuất hiện khi `equals`/`hashCode` vi phạm hợp đồng, hoặc lập trình viên dùng hash như phép kiểm tra bằng nhau duy nhất.

## 4. Ví dụ lớp tự định nghĩa: hash cố tình trùng nhưng `equals` vẫn đúng

Để thấy tính hợp lệ của collision không phụ thuộc `String`, ta tạo một value object `TicketKey`. Hai ticket bằng nhau khi có cùng `code`. Ví dụ sau cố ý trả cùng mã băm `1` cho **mọi** `TicketKey`.

Tệp **`ConstantHashDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ConstantHashDemo {
    static final class TicketKey {
        private final String code;

        TicketKey(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof TicketKey that)) {
                return false;
            }
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            // Chỉ để minh họa collision: phân bố rất kém.
            return 1;
        }
    }

    public static void main(String[] args) {
        TicketKey a = new TicketKey("A");
        TicketKey sameValue = new TicketKey("A");
        TicketKey b = new TicketKey("B");

        System.out.println(a == sameValue);
        System.out.println(a.equals(sameValue));
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());

        Set<TicketKey> tickets = new HashSet<>();
        tickets.add(a);
        tickets.add(sameValue);
        tickets.add(b);

        System.out.println(tickets.size());
        System.out.println(tickets.contains(new TicketKey("B")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ConstantHashDemo.java
java ConstantHashDemo
~~~

Kết quả chính xác:

~~~text
false
true
false
true
2
true
~~~

`a` và `sameValue` là hai instance nhưng bằng nhau theo `equals`, và cùng hash code `1`: **đúng hợp đồng**. `a` và `b` không bằng nhau nhưng cùng hash code `1`: **cũng đúng hợp đồng**. `HashSet` vẫn phân biệt hai giá trị `"A"` và `"B"`; không cần hash code phải khác nhau để lưu hai phần tử.

Tuy nhiên, **không nên dùng hash hằng số trong ứng dụng thực tế**, vì dồn mọi key vào cùng nhóm băm làm giảm hiệu quả tra cứu khi có nhiều phần tử. Cách triển khai phù hợp hơn với định nghĩa của `TicketKey` là:

~~~java
@Override
public int hashCode() {
    return code.hashCode();
}
~~~

Do constructor đã chặn `null` và `code` là `String` bất biến, cách viết trên dễ hiểu, ổn định và tương ứng với `equals` dùng `code.equals(that.code)`. Nhưng **ngay cả hàm băm tốt hơn cũng không đảm bảo không có collision**: `"Aa"` và `"BB"` vẫn là minh chứng.

## 5. Phân biệt hash code, bằng nhau về giá trị và danh tính

| Khái niệm | Cách kiểm tra/thể hiện | Có đảm bảo duy nhất không? |
| --- | --- | --- |
| Cùng instance | `x == y` với hai tham chiếu | Xác định hai biến có trỏ tới đúng cùng một đối tượng tại thời điểm so sánh. |
| Bằng nhau theo định nghĩa của kiểu | `x.equals(y)`, hoặc `Objects.equals(x, y)` khi cần xử lý `null` | Phụ thuộc cách triển khai `equals` của kiểu. |
| Cùng hash code | `x.hashCode() == y.hashCode()` | **Không.** Hai đối tượng không bằng nhau vẫn có thể trùng hash. |
| Mã băm theo danh tính | `System.identityHashCode(x)` | **Không.** Không phải định danh duy nhất và không phải địa chỉ bộ nhớ được đảm bảo. |

`Object.equals` mặc định so danh tính. Một lớp không override `equals` có thể coi hai instance chứa cùng các trường là khác nhau; đó là ngữ nghĩa mặc định, không tự động là lỗi. Khi muốn giá trị bằng nhau, hãy định nghĩa `equals` cho đúng kiểu và duy trì `hashCode` tương ứng. Ngay cả khi có `equals` đúng, không được xem kết quả `hashCode` như một ID ổn định dùng để nhận dạng đối tượng xuyên suốt các lần chạy.

Các hàm như `Objects.hash(...)`, `Arrays.hashCode(...)` hay `String.hashCode()` đều vẫn trả về `int`; chúng **không loại bỏ khả năng collision**. Chúng hỗ trợ tính nhất quán, khả năng bảo trì và phân bố hash phù hợp với dữ liệu, không thay thế `equals`.

## 6. Lỗi thường gặp

### Lỗi 1: Coi hai hash giống nhau là hai giá trị giống nhau

~~~java
// SAI: collision làm hai chuỗi khác nhau bị xem là bằng nhau.
boolean same = first.hashCode() == second.hashCode();

// ĐÚNG với String: so nội dung bằng equals.
boolean sameValue = first.equals(second);
~~~

Nếu hai giá trị thật sự bằng nhau, hash phải giống nhau; nhưng từ hash giống nhau **không thể suy ngược** rằng hai giá trị bằng nhau. Đặc biệt, không nên chỉ so hash khi viết `equals`, lọc trùng dữ liệu hay xác định cache entry duy nhất.

### Lỗi 2: Nghĩ rằng `HashSet` sẽ tự gộp mọi key cùng hash

`HashSet` loại bỏ các phần tử trùng **theo `equals`**, không phải trùng hash. Trong ví dụ đầu, `"Aa"` và `"BB"` đều được giữ. Nếu hai đối tượng thực sự bằng nhau nhưng có hash code khác nhau do cài đặt lỗi, tập hợp có thể hoạt động sai kỳ vọng.

### Lỗi 3: Override `equals` nhưng bỏ quên `hashCode`

~~~java
// Cài equals theo code nhưng giữ hashCode kế thừa từ Object:
// hai instance có cùng code có thể có hash khác nhau.
@Override
public boolean equals(Object other) {
    return this == other ||
           (other instanceof TicketKey that && code.equals(that.code));
}
~~~

Đoạn trên chỉ minh họa **lỗi thiếu override `hashCode`**, không phải một định nghĩa lớp hoàn chỉnh. Nếu lập trình viên triển khai `equals` dựa trên `code` như vậy, họ **phải** triển khai `hashCode` tương ứng. Chỉ làm một nửa có thể khiến `HashMap.get` không tìm thấy key bằng nhau hoặc `HashSet` nhận phần tử trùng giá trị.

### Lỗi 4: Dùng đối tượng mutable làm key rồi thay đổi dữ liệu so sánh

Nếu một trường tham gia `equals` và `hashCode` thay đổi sau khi đối tượng đã được đưa vào `HashMap`/`HashSet`, vị trí lưu trữ có thể không còn phù hợp với mã băm mới. Khi đó `contains`, `get`, `remove` có thể không hoạt động như mong muốn. Với key/value object, ưu tiên các trường bất biến và sao chép bảo vệ mảng hoặc collection mutable nếu chúng tham gia so sánh.

### Lỗi 5: Cho rằng “hash càng lớn” hoặc “không trùng trong dữ liệu thử” là đủ

Giá trị hash thuộc miền `int`, có thể âm, bằng 0 hoặc dương; độ lớn tuyệt đối không cho biết chất lượng. Một bộ test nhỏ không gặp collision cũng **không chứng minh** hàm băm tránh được collision. Điều nên đánh giá là sự nhất quán với `equals`, khả năng phân bố dữ liệu thực tế và hiệu năng phù hợp.

## 7. Thiết kế `hashCode` sao cho đúng và hữu ích

Khi cần viết `equals`/`hashCode` cho một lớp biểu diễn giá trị, có thể thực hiện theo trình tự:

1. Xác định **các trường quyết định sự bằng nhau**; nếu chúng khác nhau theo nghiệp vụ thì `equals` phải trả `false`.
2. Dùng cùng thông tin đó để tính `hashCode`. Có thể dùng `Objects.hash(a, b)` cho các trường thông thường, `Arrays.hashCode(array)` hoặc `Arrays.deepHashCode(array)` cho mảng, tùy cách `equals` so mảng.
3. Đảm bảo **hai đối tượng được `equals` coi là bằng nhau luôn cùng hash**, kể cả chúng là hai instance khác nhau.
4. Chấp nhận rằng **hai đối tượng khác nhau có thể cùng hash**; mục tiêu hợp lý là phân bố tốt, chứ không cần chứng minh hash duy nhất.
5. Giữ dữ liệu ảnh hưởng đến hash ổn định khi đối tượng là key trong hash collection.
6. Kiểm tra bằng `HashSet`/`HashMap` với ba ca: hai instance bằng nhau, hai instance khác nhau nhưng hash trùng, và hai instance khác nhau có hash khác. Đặc biệt kiểm tra việc thêm, tra cứu và cập nhật key.

Ví dụ một lớp `Point(int x, int y)` dùng cả `x` và `y` để xác định bằng nhau có thể viết:

~~~java
record Point(int x, int y) {}
~~~

Record Java sinh `equals` và `hashCode` nhất quán dựa trên các thành phần; nhưng nó **không cam kết mã băm duy nhất cho từng cặp tọa độ**. Ngoài ra, nếu record chứa thành phần kiểu mảng, phép so sánh được sinh cho thành phần mảng không tự trở thành so sánh sâu theo nội dung; cần thiết kế riêng nếu ngữ nghĩa giá trị cần điều đó.

## 8. Câu hỏi tự kiểm tra

1. `"Aa".equals("BB")` là `false` nhưng hai chuỗi có `hashCode() == 2112`. Điều này vi phạm hợp đồng Java không? Giải thích bằng mệnh đề một chiều.
2. Nếu đưa cả `"Aa"` và `"BB"` vào `HashSet<String>`, tập có bao nhiêu phần tử? Vì sao?
3. Nếu dùng hai key không bằng nhau nhưng cùng hash code trong `HashMap`, việc gọi `put` với key thứ hai có bắt buộc ghi đè giá trị của key thứ nhất không?
4. Một lớp có `equals` theo `id` nhưng `hashCode` trả hằng số `7` cho mọi instance. Hợp đồng có bị vi phạm không? Vấn đề chính của cách này là gì?
5. Một lớp có `equals` theo `id` nhưng kế thừa `Object.hashCode`. Tại sao hai instance có `id` giống nhau có thể gây lỗi khi được dùng làm key của `HashMap`?
6. Vì sao kiểm tra `hashCode` giống nhau không thể thay thế việc so sánh `equals` khi kiểm tra hai đối tượng có cùng giá trị?

**Ghi nhớ:** **Bằng nhau ⇒ cùng hash code** là quy tắc bắt buộc. **Cùng hash code ⇏ bằng nhau** vì collision được phép và thường không thể loại bỏ hoàn toàn. `HashMap` và `HashSet` vẫn phải phân biệt key theo `equals`; nhiệm vụ của `hashCode` là hỗ trợ tra cứu hiệu quả, không cấp danh tính duy nhất cho từng đối tượng.