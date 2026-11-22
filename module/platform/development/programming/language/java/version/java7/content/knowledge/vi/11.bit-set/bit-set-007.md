# Biên chỉ số, tập rỗng và việc chia sẻ `BitSet` giữa nhiều luồng

## 1. Mục tiêu và phạm vi

`java.util.BitSet` là một cấu trúc dữ liệu **có thể thay đổi** (*mutable*) dùng để lưu các cờ nhị phân tại những vị trí được đánh số bằng **chỉ số nguyên không âm**. Mỗi bit có hai trạng thái `false` hoặc `true`. `BitSet` tự tăng khả năng biểu diễn khi cần, nên phù hợp với các bài toán đánh dấu vị trí đã xử lý, quyền/feature flag theo ID nguyên, tập chỉ số và các phép toán bit.

Bài học này tập trung vào ba nhóm lỗi thường gây hiểu nhầm:

1. **Biên chỉ số:** chỉ số bắt đầu từ 0; khoảng thao tác có đầu bao gồm, cuối loại trừ; chỉ số âm bị từ chối; cần phân biệt giới hạn do API quy định với giới hạn **nghiệp vụ** do ứng dụng tự đặt.
2. **Tập rỗng:** `isEmpty()`, `length()`, `cardinality()` và `size()` **không có cùng nghĩa**. Một `BitSet` có sức chứa đã cấp phát vẫn có thể không có bit nào bật.
3. **Chia sẻ giữa nhiều luồng:** `BitSet` **không thread-safe** khi có truy cập đồng thời thiếu đồng bộ ngoài. Không nên dựa vào `volatile`, các chỉ số khác nhau hoặc những thử nghiệm ngẫu nhiên để kết luận đọc/ghi an toàn. Cần quản lý ownership, một cơ chế đồng bộ nhất quán hoặc bản sao đọc độc lập.

Sau bài này, bạn có thể:

- Dự đoán chính xác kết quả các lời gọi `set`, `get`, `clear`, `flip`, `get(from,to)`, `nextSetBit` và `previousSetBit` ở những biên quan trọng.
- Biết khi nào `IndexOutOfBoundsException` xuất hiện và khi nào `-1` là **giá trị trả về hợp lệ**, không phải chỉ số bit.
- Chọn phép kiểm tra tập rỗng phù hợp và tránh nhầm dung lượng `size()` với số phần tử.
- Viết vòng lặp duyệt bit bật không bị lỗi khi `nextSetBit` trả `-1` hoặc ở sát `Integer.MAX_VALUE`.
- Biết cách đồng bộ **cả đọc lẫn ghi**, tạo bản sao bằng `clone()` dưới cùng khóa và xử lý `stream()` an toàn khi dữ liệu nguồn có thể thay đổi.
- Viết code Java 17+ có test biên; chọn cấu trúc dữ liệu khác nếu cần chia sẻ trạng thái cập nhật thường xuyên mà không muốn một khóa chung.

**Bối cảnh phiên bản:** `BitSet` **không phải class mới của Java 7**; nó tồn tại từ các JDK đầu tiên. Tuy nhiên, `previousSetBit(int)`, `previousClearBit(int)` và các phương thức chuyển đổi biểu diễn đã có thêm trong Java 7. Những quy tắc cốt lõi về chỉ số, tập rỗng và thread safety **vẫn áp dụng trong Java hiện hành**. Ví dụ trong bài được biên dịch với Java 17+ và đối chiếu với Java SE 26 API; khi đề cập method mới hơn Java 7 (như `BitSet.stream()` từ Java 8 và `Stream.toList()` từ Java 16), bài ghi rõ mốc.

Nguồn chính: [Oracle Java SE 26 — BitSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html) và [Oracle Java SE 7 — BitSet](https://docs.oracle.com/javase/7/docs/api/java/util/BitSet.html).

## 2. Mô hình dữ liệu: vị trí bit không phải kích thước cố định của một mảng

Hình dung một `BitSet` có các bit bật ở vị trí 0, 3 và 8:

~~~text
Chỉ số:      0 1 2 3 4 5 6 7 8 9 ...
Trạng thái:  1 0 0 1 0 0 0 0 1 0 ...
Tập chỉ số bật: {0, 3, 8}
~~~

Đây là sơ đồ, không phải Java source. Quan trọng:

- Chỉ số **bắt đầu từ 0**, không phải 1.
- Vị trí được biểu diễn theo **số nguyên không âm**. `-1` không phải chỉ số được phép gọi `set(-1)` hay `get(-1)`.
- `BitSet` ban đầu có tất cả các bit là `false`. Khi hỏi `get(i)` với chỉ số không âm chưa từng được bật, kết quả là `false`.
- `BitSet` không có giới hạn nghiệp vụ cố định chỉ vì bạn truyền một số `nbits` vào constructor. `new BitSet(16)` không cấm bạn gọi `set(16)` hoặc `set(100)`; nó chỉ gợi ý vùng sức chứa ban đầu, và BitSet có thể mở rộng.
- `BitSet` biểu diễn **tập chỉ số bit đang bật**, không phải `java.util.Set<Integer>`. Nó không implement interface `Set` và không có các method như `add(Integer)`/`contains(Integer)` của Collection API.

Với bit được bật ở các vị trí `{0, 3, 8}`:

| Phương thức | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `isEmpty()` | `false` | Có ít nhất một bit đang bật |
| `cardinality()` | `3` | Có đúng ba bit `true` |
| `length()` | `9` | Chỉ số bật lớn nhất (8) cộng 1 |
| `get(4)` | `false` | Bit 4 chưa bật |
| `get(8)` | `true` | Bit 8 đang bật |
| `nextSetBit(4)` | `8` | Bit bật đầu tiên từ chỉ số 4 trở đi |
| `nextSetBit(9)` | `-1` | Không còn bit bật |
| `nextClearBit(0)` | `1` | Bit tắt đầu tiên tính từ 0 |
| `size()` | Không ấn định cụ thể | Dung lượng biểu diễn phụ thuộc triển khai |

**Đừng viết test buộc `size()==9`.** Mức sử dụng bộ nhớ nội bộ có thể được cấp theo đơn vị từ (*word*), không chỉ đúng số bit đang có nội dung. Đặc tả API cũng nói `size()` phụ thuộc implementation.

## 3. Ba con số dễ nhầm: `length()`, `cardinality()` và `size()`

### 3.1. `length()` là độ dài logic

`length()` trả **chỉ số của bit bật cao nhất cộng 1**; nếu không có bit nào bật, trả 0.

Ví dụ:

~~~java
BitSet bits = new BitSet();
bits.set(3);
bits.set(100);
System.out.println(bits.length()); // 101
~~~

Đây là đoạn minh họa trong một phương thức đã import `java.util.BitSet`.

Một tập chỉ có **hai** bit bật tại 3 và 100 có `length()==101`, **không** phải 2. `length()` cũng không phải tổng số vị trí bắt buộc phải quét khi duyệt các bit `true`; khi số bit bật rất ít, `nextSetBit()` thường có ý nghĩa hơn việc quét từng vị trí.

### 3.2. `cardinality()` là số bit đang bật

`cardinality()` đếm đúng số bit đang ở trạng thái `true`. Với `{3, 100}`, kết quả là `2`. Nó phù hợp cho các câu hỏi như “có bao nhiêu vị trí đã xử lý?” hoặc “có bao nhiêu feature đang bật?”, miễn dữ liệu không bị luồng khác thay đổi không đồng bộ.

### 3.3. `size()` là mức dung lượng biểu diễn

`size()` không đếm bit bật; cũng không nhất thiết bằng `length()`. Nó cho biết số bit dung lượng mà BitSet đang sử dụng để biểu diễn theo triển khai.

Nếu `new BitSet(1000)` chưa bật bit nào:

- `isEmpty()` là `true`.
- `length()` là `0`.
- `cardinality()` là `0`.
- `size()` vẫn có thể phản ánh dung lượng đã dự trữ đủ cho 1000 bit.

Không dùng `size()==0` để kiểm tra tập rỗng. Và không dùng `size()` để đặt giới hạn nghiệp vụ; BitSet tự mở rộng, nên điều kiện hợp lệ của ID phải được kiểm tra riêng.

### 3.4. Chương trình đầy đủ: qua ranh giới 63/64

Tạo file `BitSetBasicsDemo.java`:

~~~java
import java.util.BitSet;

public class BitSetBasicsDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet(130);

        System.out.println("initialEmpty=" + bits.isEmpty());
        System.out.println("initialLength=" + bits.length());
        System.out.println("capacityEnough=" + (bits.size() >= 130));

        bits.set(0);
        bits.set(63);
        bits.set(64);
        bits.set(129);

        System.out.println("bits=" + bits);
        System.out.println("cardinality=" + bits.cardinality());
        System.out.println("length=" + bits.length());
        System.out.println("outOfCurrentRange=" + bits.get(130));

        bits.clear();
        System.out.println("afterClearEmpty=" + bits.isEmpty());
        System.out.println("afterClearLength=" + bits.length());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 BitSetBasicsDemo.java
java BitSetBasicsDemo
~~~

Stdout đã kiểm chứng:

~~~text
initialEmpty=true
initialLength=0
capacityEnough=true
bits={0, 63, 64, 129}
cardinality=4
length=130
outOfCurrentRange=false
afterClearEmpty=true
afterClearLength=0
~~~

Giải thích:

1. Constructor `new BitSet(130)` dự trữ mức biểu diễn ban đầu phù hợp nhưng **không bật sẵn 130 bit**.
2. Các vị trí 63 và 64 nằm ở hai phía một ranh giới thường gặp khi lưu bit bằng các word 64-bit. Ở tầng API, bạn không cần quản lý việc tách word; `set` và `get` xử lý theo chỉ số bit.
3. `cardinality()==4` vì bật bốn vị trí, trong khi `length()==130` vì bit cao nhất ở 129.
4. `get(130)` trả `false` chứ không phải lỗi truy cập mảng: chỉ số 130 **không âm**, nhưng bit này đang tắt. Không suy ra `get(index)` bị chặn bởi kích thước cấp phát ban đầu.
5. Sau `clear()`, tất cả bit trở về `false`, nên `isEmpty()==true` và `length()==0`. Không cần và không nên giả định `clear()` buộc `size()` trở thành 0.

Các kết quả cố định của chương trình không dựa trên chính xác `size()` là 192 hay 256 ở một JVM nhất định, vì đó là chi tiết triển khai.

## 4. Biên khoảng: `[fromIndex, toIndex)`

Các overload nhận hai chỉ số như `set(fromIndex, toIndex)`, `clear(fromIndex, toIndex)`, `flip(fromIndex, toIndex)` và `get(fromIndex, toIndex)` dùng **khoảng nửa mở**:

~~~text
[fromIndex, toIndex)
     ^ được tính
                      ^ không được tính
~~~

Ví dụ:

~~~java
bits.set(2, 6);
~~~

Lệnh này bật **2, 3, 4, 5**, **không bật** vị trí 6. Với ba thao tác chỉnh sửa khoảng:

- `set(from,to)`: gán `true` cho các bit từ `from` đến trước `to`.
- `clear(from,to)`: gán `false` cho các bit trong khoảng.
- `flip(from,to)`: đảo trạng thái từng bit trong khoảng.
- `get(from,to)`: trả **một BitSet mới** gồm dữ liệu trong khoảng, với **chỉ số được đánh lại từ 0** theo `from` của nguồn.

Quy tắc hợp lệ là `0 <= fromIndex <= toIndex`. Nếu `from==to`, khoảng **rỗng**: thao tác `set`/`clear`/`flip` không tác động bit nào; `get(from,from)` trả BitSet rỗng. Nếu `from>to` hoặc một trong hai âm, API ném `IndexOutOfBoundsException`.

### 4.1. Chương trình ví dụ về khoảng và lát cắt

Tạo file `BitSetRangeDemo.java`:

~~~java
import java.util.BitSet;

public class BitSetRangeDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet();

        bits.set(2, 6);
        System.out.println("set=" + bits);

        bits.clear(3, 5);
        System.out.println("clear=" + bits);

        bits.flip(5, 7);
        System.out.println("flip=" + bits);

        BitSet slice = bits.get(2, 7);
        System.out.println("slice=" + slice);
        System.out.println("equalRangeEmpty=" +
                bits.get(4, 4).isEmpty());

        slice.set(1);
        System.out.println("originalAfterSliceChange=" + bits);
    }
}
~~~

~~~bash
javac --release 17 BitSetRangeDemo.java
java BitSetRangeDemo
~~~

Stdout:

~~~text
set={2, 3, 4, 5}
clear={2, 5}
flip={2, 6}
slice={0, 4}
equalRangeEmpty=true
originalAfterSliceChange={2, 6}
~~~

Diễn giải:

1. `set(2,6)` bật 2,3,4,5.
2. `clear(3,5)` tắt 3,4 nên còn 2,5.
3. `flip(5,7)` tắt 5 và bật 6, kết quả 2,6.
4. `get(2,7)` trích dữ liệu gốc các vị trí 2 đến 6; vị trí 2 chuyển thành **0**, vị trí 6 chuyển thành **4** trong BitSet mới.
5. `slice.set(1)` chỉ sửa bản sao; BitSet nguồn không đổi.
6. `get(4,4)` là khoảng rỗng hợp lệ, không phải lỗi.

**Sai lầm biên phổ biến:** nếu muốn bật những phần tử có chỉ số `0` đến `limit-1`, dùng `set(0, limit)`; không dùng `set(0, limit-1)`, vì tham số thứ hai **bị loại trừ**.

### 4.2. Phạm vi logic khác giới hạn miền ứng dụng

BitSet không biết “bảng của bạn có 16 record”. `set(16)` là thao tác **hợp lệ về mặt BitSet** trên một đối tượng ban đầu được tạo bằng `new BitSet(16)`; nhưng nó có thể là **lỗi nghiệp vụ** nếu ID hợp lệ chỉ từ 0 đến 15.

Cách xử lý đúng: kiểm tra index theo giới hạn miền ứng dụng **trước** khi thao tác, thay vì hy vọng BitSet ném lỗi cho mọi index ngoài giới hạn mong muốn. Sẽ có chương trình kiểm chứng ở mục 11.

## 5. Biên chỉ số âm và loại exception chính xác

Java không cho phép bit index âm ở các lệnh `set(int)`, `get(int)`, `clear(int)`, `flip(int)`, `nextSetBit(int)` hay `nextClearBit(int)`. Với chỉ số âm ở những method này, API ném `IndexOutOfBoundsException`.

Đối với **khoảng**, `from<0`, `to<0` hoặc `from>to` cũng khiến `IndexOutOfBoundsException`.

**Ngoại lệ quan trọng:**

- `previousSetBit(-1)` **trả `-1`**, để biểu diễn “không còn bit bật ở trước mốc đầu”.
- `previousClearBit(-1)` cũng **trả `-1`**.
- Chỉ số **nhỏ hơn `-1`** ở hai method `previous...` mới bị `IndexOutOfBoundsException`.
- `new BitSet(-1)` ném **`NegativeArraySizeException`**, vì tham số của constructor là kích thước dự trữ ban đầu, không phải một bit index.

Đừng gộp mọi tham số âm thành một quy tắc duy nhất. `-1` hợp lệ là **sentinel** cho các thao tác tìm về trước, không phải một bit thật có thể lưu.

| Biểu thức | Kết quả |
| --- | --- |
| `bits.set(-1)` | `IndexOutOfBoundsException` |
| `bits.get(-1)` | `IndexOutOfBoundsException` |
| `bits.set(7,3)` | `IndexOutOfBoundsException` |
| `bits.clear(0,-1)` | `IndexOutOfBoundsException` |
| `bits.nextSetBit(-1)` | `IndexOutOfBoundsException` |
| `bits.previousSetBit(-1)` | **`-1`** |
| `bits.previousSetBit(-2)` | `IndexOutOfBoundsException` |
| `new BitSet(-1)` | `NegativeArraySizeException` |
| `new BitSet().nextSetBit(0)` | **`-1`** vì không có bit bật |
| `new BitSet().nextClearBit(0)` | **`0`** vì bit đầu tiên đã tắt |

### 5.1. Chương trình kiểm thử exception và sentinel

Tạo file `BitSetBoundsDemo.java`:

~~~java
import java.util.BitSet;

public class BitSetBoundsDemo {
    static void check(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=OK");
        } catch (IndexOutOfBoundsException
                 | NegativeArraySizeException ex) {
            System.out.println(label + "=" +
                    ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        BitSet bits = new BitSet();

        check("setNegative", () -> bits.set(-1));
        check("getNegative", () -> bits.get(-1));
        check("rangeReversed", () -> bits.set(7, 3));
        check("rangeToNegative", () -> bits.clear(0, -1));
        check("nextSetNegative", () -> bits.nextSetBit(-1));
        check("previousBelowMinusOne",
                () -> bits.previousSetBit(-2));
        check("negativeCapacity", () -> new BitSet(-1));

        System.out.println("previousAtMinusOne=" +
                bits.previousSetBit(-1));
        System.out.println("nextSetEmpty=" + bits.nextSetBit(0));
        System.out.println("nextClearEmpty=" + bits.nextClearBit(0));
    }
}
~~~

~~~bash
javac --release 17 BitSetBoundsDemo.java
java BitSetBoundsDemo
~~~

Stdout:

~~~text
setNegative=IndexOutOfBoundsException
getNegative=IndexOutOfBoundsException
rangeReversed=IndexOutOfBoundsException
rangeToNegative=IndexOutOfBoundsException
nextSetNegative=IndexOutOfBoundsException
previousBelowMinusOne=IndexOutOfBoundsException
negativeCapacity=NegativeArraySizeException
previousAtMinusOne=-1
nextSetEmpty=-1
nextClearEmpty=0
~~~

Chương trình bắt ngoại lệ **chỉ để quan sát quy tắc API**. Trong code sản phẩm, không nên dùng exception làm phương thức bình thường để phát hiện ID xấu; thường tốt hơn là kiểm tra index và tạo thông báo lỗi nghiệp vụ trước khi thao tác.

### 5.2. Tại sao `nextClearBit` trên tập rỗng không trả `-1`?

`nextSetBit(from)` tìm bit **đang bật**. Nếu tập rỗng, không có bit nào bật, nên nó trả `-1`.

Ngược lại, `nextClearBit(from)` tìm bit **đang tắt**. Theo mô hình BitSet, bit chưa từng bật vẫn có giá trị `false`, kể cả bên ngoài độ dài logic hiện tại. Vì vậy với tập rỗng và `from=0`, bit 0 đã là bit tắt đầu tiên: kết quả là **0**, không phải `-1`.

Nếu bạn chỉ muốn tìm bit chưa bật **trong miền ID 0..limit-1 của ứng dụng**, cần kiểm tra kết quả `nextClearBit(0) < limit`. Đừng dùng việc hàm có trả một chỉ số không âm để suy ra nó nằm trong miền hợp lệ của bạn.

## 6. “Tập rỗng” không đồng nghĩa “chưa từng cấp phát bộ nhớ”

Một BitSet được coi là rỗng khi **không có bất kỳ bit `true` nào**. Mức dung lượng đã cấp phát không quyết định tập rỗng.

Có ba cách diễn đạt cùng một tính chất khi không có concurrent modification:

- `bits.isEmpty()` → tên method nói rõ mục đích và nên ưu tiên.
- `bits.cardinality() == 0` → đúng về giá trị, nhưng đang tính số bit bật khi chỉ cần biết rỗng.
- `bits.length() == 0` → đúng vì không có bit bật cao nhất; biểu thị độ dài logic.

Không dùng `bits.size() == 0` làm điều kiện rỗng.

### 6.1. So sánh hai BitSet rỗng có dung lượng khác nhau

`BitSet.equals(Object)` so sánh **trạng thái các bit**, không so sánh sức chứa. Hai BitSet rỗng vẫn **bằng nhau** ngay cả khi một bên yêu cầu dung lượng khởi tạo lớn hơn bên kia.

Tạo file `BitSetEmptyDemo.java`:

~~~java
import java.util.BitSet;

public class BitSetEmptyDemo {
    public static void main(String[] args) {
        BitSet a = new BitSet();
        BitSet b = new BitSet(1000);

        System.out.println("a=" + a);
        System.out.println("aEqualsB=" + a.equals(b));
        System.out.println("bEmpty=" + b.isEmpty());
        System.out.println("bLength=" + b.length());
        System.out.println("bCount=" + b.cardinality());
        System.out.println("bHasCapacity=" + (b.size() >= 1000));

        b.set(15);
        b.clear(15);
        System.out.println("emptyAgain=" + b.isEmpty());
        System.out.println("equalsAgain=" + a.equals(b));
    }
}
~~~

~~~bash
javac --release 17 BitSetEmptyDemo.java
java BitSetEmptyDemo
~~~

Stdout:

~~~text
a={}
aEqualsB=true
bEmpty=true
bLength=0
bCount=0
bHasCapacity=true
emptyAgain=true
equalsAgain=true
~~~

**Giải thích:**

1. `new BitSet(1000)` cho biết vùng dung lượng ban đầu mong muốn, **không** có nghĩa 1000 bit đã được bật.
2. `a.equals(b)` đúng vì cả hai đều có mọi bit bằng `false`; `equals` không quan tâm kích thước cấp phát nội bộ.
3. Sau khi bật rồi tắt bit 15, `b` lại là một BitSet rỗng theo nghĩa logic. Số dung lượng nội bộ mà `size()` báo về **không bắt buộc** thu lại thành 0.
4. Chuỗi `{}` là biểu diễn của tập không có chỉ số nào được bật, không phải một loại dữ liệu khác.

**Lưu ý khi dùng làm khóa của Map/Set:** BitSet là mutable. Khi đã đặt một BitSet làm khóa của hash-based collection, sửa nó làm thay đổi hash/equality theo bit có thể khiến việc tra cứu không còn như mong đợi. Nếu cần khóa, hãy dùng bản sao **không bị sửa trong suốt thời gian làm khóa** hoặc chọn biểu diễn bất biến phù hợp.

### 6.2. Tập rỗng sau các phép toán logic

Một `BitSet` có thể trở thành rỗng do:

- `clear()`: tắt tất cả các bit.
- `and(other)`: nếu không có bit nào cùng bật trong hai BitSet.
- `andNot(other)`: nếu `other` loại bỏ hết các bit đang bật.
- `xor(other)`: nếu hai BitSet có cùng trạng thái các bit tương ứng.

Những phép toán `and`, `or`, `xor`, `andNot` **sửa trực tiếp BitSet đích**, không trả về một đối tượng kết quả bất biến. Nếu `bits` đang được chia sẻ giữa nhiều luồng, cả những phép toán này cũng phải nằm trong chính sách đồng bộ của đối tượng.

## 7. Duyệt các bit bật và những trường hợp biên của `-1`

### 7.1. `nextSetBit(fromIndex)` tìm về trước

`nextSetBit(fromIndex)` trả chỉ số bit bật đầu tiên **bằng hoặc lớn hơn** `fromIndex`. Khi không còn bit bật, trả `-1`.

Mẫu lặp thường thấy:

~~~java
for (int i = bits.nextSetBit(0);
     i >= 0;
     i = bits.nextSetBit(i + 1)) {
    process(i);
    if (i == Integer.MAX_VALUE) {
        break;
    }
}
~~~

Đây là **đoạn minh họa** trong phương thức có `bits` và `process(int)` đã khai báo. Điều kiện `if (i == Integer.MAX_VALUE) break;` rất quan trọng khi cần chuẩn bị code cho toàn miền `int`: nếu `i` đã bằng `Integer.MAX_VALUE`, phép `i+1` sẽ **tràn số nguyên thành giá trị âm**. JavaDoc chính thức minh họa chính cách bảo vệ này.

Không dùng việc `-1` là sentinel để bỏ qua điều kiện `i>=0`; nếu truyền `nextSetBit(-1)`, API sẽ ném `IndexOutOfBoundsException`.

**Giới hạn thực tế:** Bật một bit ở chỉ số gần `Integer.MAX_VALUE` có thể cần lượng bộ nhớ rất lớn do BitSet biểu diễn theo vị trí cao nhất. Ví dụ không cố cấp phát một BitSet khổng lồ chỉ để chứng minh overflow; guard ở vòng lặp vẫn là lựa chọn đúng nếu API của bạn phải hỗ trợ chỉ số sát giới hạn.

### 7.2. `previousSetBit(fromIndex)` tìm về sau

`previousSetBit(fromIndex)` trả chỉ số bit bật gần nhất **không lớn hơn** `fromIndex`. Nếu không có bit phù hợp hoặc truyền `-1`, trả `-1`. Điểm khác `nextSetBit` là **`previousSetBit(-1)` hợp lệ**.

Với BitSet có `length()==0`, cách tính `length()-1` cho ra `-1`, và `previousSetBit(-1)` sẽ trả `-1` an toàn.

### 7.3. Chương trình đi xuôi, đi ngược và Stream

Tạo file `BitSetIterationDemo.java`:

~~~java
import java.util.BitSet;
import java.util.StringJoiner;

public class BitSetIterationDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet();
        bits.set(1);
        bits.set(3);
        bits.set(66);

        StringJoiner forward = new StringJoiner(",");

        for (int i = bits.nextSetBit(0);
             i >= 0;
             i = bits.nextSetBit(i + 1)) {
            forward.add(Integer.toString(i));
            if (i == Integer.MAX_VALUE) {
                break;
            }
        }

        StringJoiner backward = new StringJoiner(",");

        for (int i = bits.previousSetBit(bits.length() - 1);
             i >= 0;
             i = bits.previousSetBit(i - 1)) {
            backward.add(Integer.toString(i));
        }

        System.out.println("forward=" + forward);
        System.out.println("backward=" + backward);
        System.out.println("stream=" + bits.stream().boxed().toList());
        System.out.println("emptyPrevious=" +
                new BitSet().previousSetBit(-1));
    }
}
~~~

~~~bash
javac --release 17 BitSetIterationDemo.java
java BitSetIterationDemo
~~~

Stdout:

~~~text
forward=1,3,66
backward=66,3,1
stream=[1, 3, 66]
emptyPrevious=-1
~~~

Những chi tiết cần nắm:

- Duyệt xuôi hoặc ngược cho cùng tập bit bật nhưng thứ tự khác nhau.
- `nextSetBit` và `previousSetBit` thuận tiện khi các bit bật **thưa**, tránh quét mọi index từ 0 đến `length()-1`.
- `BitSet.stream()` trả một `IntStream` chứa các **chỉ số đang bật theo thứ tự tăng dần**, không trả từng giá trị boolean.
- `BitSet.stream()` có từ **Java 8**; `Stream.toList()` có từ **Java 16**. Vì vậy toàn bộ chương trình dùng `--release 17` là hợp lệ, nhưng không nên coi hai API này là tính năng Java 7.
- Code duyệt ở mục này giả định không có thread khác thay đổi BitSet đồng thời. Nếu chia sẻ trạng thái, cần khóa hoặc snapshot trước khi duyệt.

### 7.4. Không dùng `nextClearBit` như phép duyệt hữu hạn không giới hạn

Vì BitSet có các bit `false` ở ngoài độ dài logic, `nextClearBit(0)` có thể trả chỉ số hợp lệ ngay cả khi toàn bộ tập rỗng. Nếu ứng dụng cần các vị trí còn trống trong miền `[0,limit)`, hãy **dừng khi kết quả >= limit**, không coi mọi giá trị trả về là một slot có thể dùng.

## 8. Bản sao và lát cắt: tránh chia sẻ đối tượng mutable ngoài ý muốn

`BitSet` là mutable. Nếu hai biến tham chiếu tới **cùng một đối tượng**, thay đổi qua một biến sẽ tác động tới đối tượng mà biến kia nhìn thấy:

~~~java
BitSet first = new BitSet();
BitSet second = first;
second.set(3);
// first.get(3) cũng là true.
~~~

Đây là **đoạn minh họa**. `second = first` **không tạo bản sao**.

Khi cần độc lập trạng thái:

- `(BitSet) source.clone()` tạo bản sao có cùng trạng thái các bit tại thời điểm sao chép.
- `source.get(from, to)` tạo BitSet mới chỉ gồm một khoảng của nguồn, **đánh lại index từ 0**.
- Nếu nguồn đang được truy cập bởi nhiều thread, **phải snapshot khi đang giữ cùng khóa bảo vệ nguồn**. `clone()` không tự tạo an toàn khi một thread khác đang thay đổi dữ liệu bên trong.

### 8.1. Ví dụ độc lập bản sao

Tạo file `BitSetSnapshotDemo.java`:

~~~java
import java.util.BitSet;

public class BitSetSnapshotDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet();
        bits.set(4);
        bits.set(9);

        BitSet copy = (BitSet) bits.clone();
        BitSet slice = bits.get(4, 10);

        bits.clear(4);

        System.out.println("original=" + bits);
        System.out.println("copy=" + copy);
        System.out.println("slice=" + slice);
        System.out.println("copyStillHas4=" + copy.get(4));
    }
}
~~~

~~~bash
javac --release 17 BitSetSnapshotDemo.java
java BitSetSnapshotDemo
~~~

Stdout:

~~~text
original={9}
copy={4, 9}
slice={0, 5}
copyStillHas4=true
~~~

`copy` vẫn có bit 4 vì nó là bản sao. `slice` chứa các vị trí 0 và 5 vì nguồn lúc cắt có bit 4 và 9; cắt khoảng bắt đầu tại 4 nên hai index bị **dịch** 4 đơn vị.

Một bản sao là đối tượng mutable riêng; nếu chính bản sao ấy lại được gửi cho nhiều thread và bị ghi đồng thời, nó cũng cần chính sách đồng bộ riêng. “Snapshot” ở đây nghĩa là **bản chụp tách biệt khỏi nguồn trong thời điểm tạo**, không phải class bất biến.

## 9. `BitSet` không an toàn khi bị nhiều luồng truy cập thiếu đồng bộ

JavaDoc hiện hành nói rõ: **“A BitSet is not safe for multithreaded use without external synchronization.”** Điều này có nghĩa code không thể mặc định gọi `set`, `clear`, `flip`, `and`, `or`, `get`, `isEmpty`, `cardinality`, `stream` hoặc `clone` trên cùng một BitSet đang thay đổi từ nhiều thread mà vẫn có kết quả nhất quán.

### 9.1. Những sai lầm thường gặp

**Sai lầm 1 — “Mỗi thread chỉ sửa một bit riêng, nên không race”:**

~~~java
// Minh họa nguy cơ, KHÔNG phải code nên dùng.
BitSet shared = new BitSet();
threadA(() -> shared.set(1));
threadB(() -> shared.set(2));
~~~

Hai hàm `threadA/threadB` chỉ là placeholder diễn đạt hai tác vụ, **không phải API Java**. Dù các bit khác nhau, chúng có thể nằm trong cùng vùng dữ liệu lưu trữ bên trong. Thao tác đọc–sửa–ghi, cập nhật sức chứa và các trường trạng thái nội bộ không được `BitSet` cam kết atomic/thread-safe. Một lần chạy “đúng” không chứng minh không có data race.

**Sai lầm 2 — “Đặt tham chiếu là `volatile` là đủ”:**

~~~java
// Minh họa sai lầm; chỉ giúp nhận diện.
volatile BitSet shared = new BitSet();
~~~

Đây là **đoạn field trong class**. `volatile` giúp một số bảo đảm về việc đọc/ghi tham chiếu và thứ tự/khả năng quan sát tương ứng, **không biến các thao tác bên trong BitSet thành atomic**, không làm an toàn thao tác cập nhật nhiều bước.

**Sai lầm 3 — “Chỉ khóa writer, reader thì không cần”:**

~~~java
// Minh họa không đầy đủ, không nên dùng:
synchronized (lock) {
    shared.set(5);
}
boolean active = shared.get(5); // Đọc không giữ lock tương ứng.
~~~

Ở đây `shared` và `lock` giả định đã tồn tại. Nếu reader chạy đồng thời với writer mà không theo cùng chính sách đồng bộ, chương trình vẫn thiếu bảo đảm nhất quán/visibility. **Khóa phải được mọi truy cập cùng tham gia**, không chỉ ở chỗ ghi.

**Sai lầm 4 — “Có `final BitSet` thì không thể thay đổi”:** `final` chỉ không cho gán lại **tham chiếu field**, không ngăn `shared.set(...)` sửa nội dung.

**Sai lầm 5 — “Dùng `Collections.synchronizedSet`”:** `BitSet` không implement `Set`, nên không phải đối tượng trực tiếp đưa vào wrapper `Collections.synchronizedSet`. Nếu cần API Set đồng thời, chọn cấu trúc dữ liệu thực sự implement Set và thỏa hợp đồng cập nhật mong muốn.

### 9.2. Nguyên tắc đồng bộ đúng

Một lớp sở hữu duy nhất có thể giữ:

~~~java
private final Object lock = new Object();
private final BitSet bits = new BitSet();
~~~

Đây là hai **field trong một class**. Mọi method đọc hoặc ghi đều phải:

1. Lấy **cùng `lock`** trước khi truy cập `bits`.
2. Hoàn thành những thao tác cần nhất quán khi vẫn giữ khóa.
3. Không trả trực tiếp tham chiếu mutable `bits` cho caller không tuân theo lock.
4. Nếu cần trả một ảnh chụp, tạo `(BitSet) bits.clone()` **bên trong khóa**, rồi trả bản sao; caller dùng bản sao một cách độc lập.
5. Nếu cần nhiều thay đổi phải được xem như một giao dịch logic, thực hiện chúng trong **cùng một khối đồng bộ**, thay vì nhiều lần set/get tách rời để thread khác chen vào.

Khóa riêng tư `new Object()` giúp API che giấu cơ chế synchronization. Có thể đồng bộ trên chính BitSet nếu **tất cả** bên tham gia luôn dùng chung monitor, nhưng làm vậy với đối tượng bị chia sẻ công khai dễ thất lạc quy ước lock hơn.

### 9.3. Chương trình đa luồng an toàn: 2 tác vụ, 1 BitSet, 1 lock

Tạo file `BitSetConcurrentDemo.java`:

~~~java
import java.util.BitSet;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BitSetConcurrentDemo {
    static final class SharedBits {
        private final Object lock = new Object();
        private final BitSet bits = new BitSet();

        void set(int index) {
            synchronized (lock) {
                bits.set(index);
            }
        }

        void clear(int index) {
            synchronized (lock) {
                bits.clear(index);
            }
        }

        boolean get(int index) {
            synchronized (lock) {
                return bits.get(index);
            }
        }

        int count() {
            synchronized (lock) {
                return bits.cardinality();
            }
        }

        BitSet snapshot() {
            synchronized (lock) {
                return (BitSet) bits.clone();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        SharedBits shared = new SharedBits();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> evens = pool.submit(() -> {
                for (int i = 0; i < 1000; i += 2) {
                    shared.set(i);
                }
            });

            Future<?> odds = pool.submit(() -> {
                for (int i = 1; i < 1000; i += 2) {
                    shared.set(i);
                }
            });

            evens.get();
            odds.get();
        } finally {
            pool.shutdown();
        }

        System.out.println("sharedCount=" + shared.count());

        BitSet snapshot = shared.snapshot();
        shared.clear(0);

        System.out.println("sharedZero=" + shared.get(0));
        System.out.println("snapshotZero=" + snapshot.get(0));
        System.out.println("snapshotCount=" + snapshot.cardinality());
        System.out.println("snapshotStreamCount=" +
                snapshot.stream().count());
    }
}
~~~

~~~bash
javac --release 17 BitSetConcurrentDemo.java
java BitSetConcurrentDemo
~~~

Stdout đã kiểm chứng:

~~~text
sharedCount=1000
sharedZero=false
snapshotZero=true
snapshotCount=1000
snapshotStreamCount=1000
~~~

**Vì sao kết quả xác định được dù thứ tự chạy thread không cố định?**

1. Hai tác vụ ghi vào các chỉ số chẵn và lẻ trong miền `0..999`. Mỗi lần ghi đều đi qua method `SharedBits.set`, nơi đồng bộ với cùng một `lock`. Do đó không có hai thread cùng sửa nội bộ BitSet mà thiếu đồng bộ.
2. `Future.get()` đợi từng tác vụ hoàn thành; sau hai lời gọi này, toàn bộ 1000 bit đã được đặt trước khi in số lượng.
3. `SharedBits.count` và `SharedBits.get` cũng lấy cùng khóa, chứ không chỉ các phương thức ghi.
4. `SharedBits.snapshot` clone nguồn khi khóa đang được giữ, tạo bản sao nhất quán tại thời điểm lấy snapshot.
5. Sau khi xóa bit 0 ở nguồn, `sharedZero=false` nhưng `snapshotZero=true` vì hai đối tượng độc lập. Snapshot vẫn có 1000 bit đang bật.
6. `snapshot.stream().count()` có thể chạy mà không khóa nguồn, vì chính snapshot không bị thread khác thay đổi trong ví dụ.

Đây là ví dụ **an toàn và có stdout cố định**, không phải benchmark hiệu năng. Khóa chung có thể gây tranh chấp khi nhiều thread cập nhật với tần suất cao; nếu cần thông lượng lớn, hãy cân nhắc cấu trúc dữ liệu đồng thời phù hợp với bài toán.

**Lưu ý về lifecycle:** `ExecutorService.shutdown()` không thay thế `Future.get()` trong ví dụ. `Future.get()` bảo đảm hai công việc đã hoàn thành trước khi đọc dữ liệu. Với hệ thống thật, cần xác định chính sách xử lý lỗi tác vụ, timeout, interrupt và shutdown.

## 10. `BitSet.stream()` và việc thay đổi trong lúc duyệt

Từ Java 8, `BitSet.stream()` trả một `IntStream` các **chỉ số bit bật**. Theo Javadoc hiện hành, stream có kiểu **late-binding**: nó gắn với BitSet khi thực hiện thao tác terminal, và **nếu BitSet bị sửa trong thời gian thực hiện terminal operation thì kết quả là undefined**.

Cần tách ba trường hợp:

1. **Không có thread nào ghi trong lúc duyệt:** có thể dùng `bits.stream()` bình thường.
2. **Nguồn chia sẻ có writer:** không đủ nếu chỉ `synchronized(lock) { return bits.stream(); }`, vì method trả về stream trước khi terminal operation diễn ra; lock đã được thả.
3. **Muốn đọc không giữ khóa lâu:** clone BitSet trong lock, rồi gọi `snapshot.stream()` **sau** khi ra khỏi lock, miễn không có thread nào sửa snapshot.

Mẫu:

~~~java
BitSet snapshot;
synchronized (lock) {
    snapshot = (BitSet) bits.clone();
}

long selected = snapshot.stream().count();
~~~

Đây là **đoạn minh họa trong phương thức** với `lock` và `bits` đã khai báo. `stream().count()` trả số phần tử kiểu `long`, tương ứng số bit bật trong snapshot. Không nhầm với `bits.size()` của nguồn.

Nếu cần duyệt nguồn trực tiếp và đảm bảo một chuỗi thao tác có ảnh chụp nhất quán, có thể giữ lock **trong toàn bộ terminal operation**, nhưng đó có thể là khóa dài. Cách clone dưới lock thường dễ giới hạn thời gian giữ khóa hơn, đánh đổi chi phí bộ nhớ và sao chép.

**Không gọi thao tác biến đổi nguồn ngay trong lambda xử lý stream** và nghĩ stream sẽ tự thích ứng; Javadoc nói rõ kết quả khi sửa trong terminal operation là không xác định.

## 11. Biên của BitSet không phải biên ID ứng dụng

Giả sử miền của ứng dụng có đúng 16 slot, ID hợp lệ `0..15`. `BitSet` vẫn cho phép `set(16)`, vì index 16 là **chỉ số không âm**. Đừng dựa vào `new BitSet(16)` để làm validation.

Mẫu hợp lý: lưu một `limit` riêng, kiểm tra trước khi `set`/`get` khi quy tắc nghiệp vụ yêu cầu:

~~~java
static void setChecked(BitSet bits, int index, int limit) {
    if (index < 0 || index >= limit) {
        throw new IllegalArgumentException(
                "Outside [0," + limit + ")");
    }
    bits.set(index);
}
~~~

Đây là **phương thức trong class** đã import `BitSet`, không phải chương trình độc lập. Logic cho phép index 0, cho phép index `limit-1` và từ chối index `limit`.

### 11.1. Ví dụ Java 17+ với miền cố định

Tạo file `BitSetDomainDemo.java`:

~~~java
import java.util.BitSet;

public class BitSetDomainDemo {
    static void setChecked(BitSet bits, int index, int limit) {
        if (index < 0 || index >= limit) {
            throw new IllegalArgumentException(
                    "Outside [0," + limit + ")");
        }
        bits.set(index);
    }

    public static void main(String[] args) {
        int limit = 16;
        BitSet bits = new BitSet(limit);

        setChecked(bits, 15, limit);
        System.out.println("lastValid=" + bits.get(15));

        try {
            setChecked(bits, 16, limit);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("beyondLogical=" + bits.get(16));
        System.out.println("bitsetLength=" + bits.length());
    }
}
~~~

~~~bash
javac --release 17 BitSetDomainDemo.java
java BitSetDomainDemo
~~~

Stdout:

~~~text
lastValid=true
rejected=Outside [0,16)
beyondLogical=false
bitsetLength=16
~~~

Ở đây bit 15 đã được bật nên `length()==16`. Yêu cầu bật bit 16 bị **helper nghiệp vụ** từ chối; không phải BitSet tự ném lỗi vì vượt sức chứa khởi tạo.

### 11.2. Kiểm tra số nguyên trước khi tính biên trên

Nếu muốn thao tác đến **và bao gồm** index `last` bằng API khoảng nửa mở `set(0, last+1)`, phải cân nhắc tràn số nguyên ở `last+1`. Cách tránh ở code nghiệp vụ là có **giới hạn miền rõ ràng**, xác thực `last` và chỉ cộng khi còn trong vùng biểu diễn của `int`.

Không tự ý truyền `Integer.MAX_VALUE + 1` vào `set(from,to)`: biểu thức kiểu `int` sẽ bị tràn thành giá trị âm. Nếu chỉ muốn bật đúng một bit có index lớn, API có `set(index)`; tuy nhiên index cực lớn có thể đòi lượng bộ nhớ không phù hợp. Cần áp đặt giới hạn thực tế theo thiết kế sản phẩm, không chỉ theo kiểu `int`.

### 11.3. Khi ID không liên tục hoặc rất thưa

`BitSet` có thể hiệu quả với miền chỉ số tương đối dày và không quá lớn. Nhưng nếu ID chỉ xuất hiện ở vài vị trí như 1, 10 và hàng trăm triệu, BitSet có thể phải giữ nhiều vùng bit chưa sử dụng chỉ vì index lớn nhất. Khi đó cân nhắc `Set<Integer>`/cấu trúc sparse thích hợp, đặc biệt nếu ứng dụng còn cần cập nhật đồng thời.

## 12. Chọn cấu trúc dữ liệu khi có nhiều thread

Không có một giải pháp phù hợp mọi trường hợp. Hãy căn cứ vào **cách biểu diễn miền chỉ số**, **tần suất đọc/ghi**, **nhu cầu snapshot** và **số lượng luồng**.

| Nhu cầu | Phương án cân nhắc | Lưu ý |
| --- | --- | --- |
| Một thread sở hữu BitSet; nhiều nơi cần đọc trạng thái đã chốt | Chỉ công bố bản sao/snapshot để đọc, không cho sửa nó | Bảo đảm snapshot không bị thread khác mutate |
| Nhiều thread đọc/ghi cùng một BitSet nhỏ/vừa | Bao `BitSet` trong class với một lock nhất quán | Đồng bộ **mọi thao tác** trên nguồn, kể cả copy và stream terminal nếu dùng trực tiếp |
| Một luồng ghi, nhiều luồng cần ảnh chụp | Clone dưới lock, dùng snapshot ngoài lock | Có chi phí sao chép; snapshot có thể cũ so với trạng thái hiện tại |
| Nhiều thread cập nhật cờ theo một miền **cố định** và cần atomic operations | Xem `AtomicLongArray` với mask bit và CAS phù hợp | Phải tự ánh xạ index → word/bit; xử lý biên, memory ordering và thao tác tổng hợp |
| Tập ID thưa, cần `Set<Integer>` hỗ trợ truy cập đồng thời | Xem `ConcurrentHashMap.newKeySet()` | Có overhead khác BitSet; phù hợp mô hình Set hơn thao tác bit vector |
| Cần immutable state chia sẻ giữa reader | Tạo snapshot an toàn và công bố không cho chỉnh sửa | `BitSet` không phải immutable; cần quy ước hoặc kiểu wrapper bảo vệ ownership |
| Cần cấu trúc có nén/chỉ số lớn | Đánh giá thư viện bitset/bitmap chuyên biệt theo yêu cầu | Kiểm tra tính đúng, thread safety và chi phí thật trong môi trường chạy |

**Không khẳng định `AtomicLongArray` là một “BitSet thread-safe” thay thế trực tiếp.** Nó cung cấp thao tác atomic trên từng phần tử kiểu `long`; bạn phải thiết kế cập nhật bit bằng phép toán mask, kiểm tra index và kết hợp nhiều word nếu có yêu cầu nhất quán trên toàn bộ tập. Tương tự, `ConcurrentHashMap.newKeySet()` là một Set hỗ trợ đồng thời, không có mọi phép toán bit vector của BitSet.

Nguồn tham khảo API: [AtomicLongArray, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLongArray.html) và [ConcurrentHashMap, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

## 13. Các lỗi và hiểu nhầm thường gặp

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “BitSet đánh số bit từ 1.” | Bắt đầu từ **0**. |
| “`new BitSet(16)` chỉ cho phép index 0..15.” | Đây là sức chứa khởi tạo, BitSet **có thể mở rộng**; kiểm tra giới hạn nghiệp vụ riêng. |
| “`get(100000)` chắc chắn lỗi nếu chưa có dung lượng.” | Với index **không âm** nhưng bit chưa bật, `get` trả `false`. |
| “`set(2,6)` bật cả bit 6.” | Khoảng là **[2,6)**: chỉ 2,3,4,5. |
| “`set(5,5)` là khoảng sai.” | Khoảng rỗng hợp lệ và không đổi trạng thái. |
| “Mọi chỉ số âm đều hợp lệ làm sentinel.” | Chỉ một số method tìm về trước chấp nhận **-1**; `set(-1)`/`nextSetBit(-1)` lỗi. |
| “`new BitSet(-1)` ném cùng lỗi với `set(-1)`.” | Constructor ném `NegativeArraySizeException`; bit index âm gây `IndexOutOfBoundsException`. |
| “Tập rỗng nghĩa là `size()==0`.” | Dùng `isEmpty()`; `size()` là dung lượng triển khai. |
| “`length()` là số bit bật.” | `length()` là chỉ số bật cao nhất +1; số bit bật là `cardinality()`. |
| “Hai BitSet rỗng khác capacity thì không bằng nhau.” | `equals` dựa trên bit bật, không dựa vào `size()`. |
| “`nextSetBit(0)` của tập rỗng trả 0.” | Trả **-1** vì không có bit bật. |
| “`nextClearBit(0)` của tập rỗng trả -1.” | Trả **0** vì bit 0 đang tắt. |
| “Duyệt `nextSetBit(i+1)` luôn an toàn số nguyên.” | Guard khi i ở `Integer.MAX_VALUE` để tránh overflow. |
| “`get(from,to)` trả view có chung storage với nguồn.” | Trả **BitSet mới**, index được dời về 0. |
| “`BitSet` là thread-safe vì thao tác bit đơn giản.” | JavaDoc yêu cầu **external synchronization** khi nhiều thread dùng chung. |
| “Hai thread ghi bit khác nhau không thể bị race.” | Có thể cùng đụng word/trạng thái nội bộ; không có bảo đảm atomic. |
| “`final`/`volatile` là đủ để mọi thao tác BitSet an toàn.” | Không biến các method mutable thành atomic/thread-safe. |
| “Chỉ khóa `set`, `get` đọc thoải mái.” | Mọi truy cập đồng thời phải theo **một chính sách đồng bộ**. |
| “Gọi `bits.stream()` trong lock là đủ.” | Terminal operation có thể chạy **sau khi lock đã thả**; dùng snapshot hoặc giữ khóa hết terminal. |
| “Clone từ BitSet đang bị thread khác sửa vẫn là snapshot nhất quán.” | Clone cần cùng lock hoặc cơ chế phối hợp tương đương với writer. |
| “Thêm `BitSet` vào HashMap làm key rồi cứ chỉnh bit.” | Thay đổi trạng thái có thể thay hash/equality và phá kỳ vọng tra cứu. |
| “Dùng `Collections.synchronizedSet(bits)`.” | `BitSet` không implement `Set`; phải có wrapper riêng hoặc chọn collection khác. |

## 14. Checklist kiểm thử biên và concurrency trong dự án

1. **Xác định phạm vi index**: 0-based hay được ánh xạ từ ID khác? Có giới hạn `[0,limit)` riêng của ứng dụng?
2. **Test các vị trí biên**: 0, 1, limit-1, limit; với thao tác bit vector, thêm các vị trí 63/64 nếu phù hợp.
3. **Test range**: `from==to`, `from<to`, `from>to` và giá trị âm.
4. **Test empty**: mới khởi tạo, sau `clear()`, sau bật rồi tắt bit cuối, sau giao hai tập không giao nhau.
5. **Không dùng `size()` làm assertion số bit**; dùng `cardinality()` khi đếm, `length()` khi xét index cao nhất.
6. **Kiểm tra sentinel**: `nextSetBit(0)==-1` cho tập rỗng, `previousSetBit(-1)==-1`, `nextSetBit(-1)` phải bị từ chối.
7. **Duyệt không overflow**: có guard cho `Integer.MAX_VALUE` khi cập nhật `i+1`.
8. **Duyệt không bị sửa giữa chừng**: cố định quyền sở hữu hoặc lấy snapshot trước khi tạo/consume stream.
9. **Kiểm tra mọi entry point đọc và ghi**: `get`, `set`, `clear`, `flip`, `cardinality`, `equals`, `clone`, `stream` và các phép logic. Có đường nào bỏ qua lock không?
10. **Quản lý thời điểm hoàn thành tác vụ**: nếu đọc sau cập nhật bất đồng bộ, đợi bằng `Future.get`/cơ chế phối hợp phù hợp.
11. **Không rò rỉ BitSet mutable ra khỏi wrapper**: trả snapshot có kiểm soát hoặc API truy cập theo lock.
12. **Cân nhắc hiệu năng và độ thưa**: index cực cao có thể tốn bộ nhớ; một lock chung có thể làm giảm song song. Đo trên workload thật trước khi chọn cấu trúc khác.
13. **Đặt kỳ vọng cho snapshot**: snapshot là ảnh chụp tại một thời điểm, không tự cập nhật theo nguồn; caller không được xem nó là “live view”.
14. **Kiểm tra compiler release**: ví dụ có `BitSet.stream()` và `Stream.toList()` cần Java 8+/16+; nếu dự án hỗ trợ Java 17+ thì dùng bình thường.
15. **Không dùng một run concurrency test làm bằng chứng duy nhất**: race có thể không xuất hiện ở từng lần chạy. Chứng minh tính đúng qua hợp đồng đồng bộ, và thêm test đa luồng để phát hiện hồi quy.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `BitSet bits = new BitSet(50);` chưa gọi `set`. `bits.isEmpty()` và `bits.length()` là gì?  
**Đáp án:** `true` và `0`. Tham số 50 chỉ định sức chứa ban đầu, không bật 50 bit.

**Câu 2.** `bits.set(3); bits.set(20);` thì `cardinality()` và `length()` bao nhiêu?  
**Đáp án:** `2` và `21`.

**Câu 3.** `bits.set(3,7)` bật những index nào?  
**Đáp án:** 3,4,5,6. Index 7 bị loại trừ.

**Câu 4.** `bits.set(7,3)` có phải khoảng rỗng hợp lệ?  
**Đáp án:** Không. Vì `from>to`, nó ném `IndexOutOfBoundsException`. Khoảng rỗng hợp lệ có `from==to`.

**Câu 5.** `bits.get(-1)` và `bits.previousSetBit(-1)` có giống nhau không?  
**Đáp án:** Không. `get(-1)` ném `IndexOutOfBoundsException`; `previousSetBit(-1)` trả `-1`.

**Câu 6.** Tập rỗng có `nextSetBit(0)` và `nextClearBit(0)` bằng gì?  
**Đáp án:** Lần lượt `-1` và `0`.

**Câu 7.** Vì sao `size()` không dùng để biết có bao nhiêu bit bật?  
**Đáp án:** Nó cho biết dung lượng biểu diễn phụ thuộc implementation; `cardinality()` mới là số bit `true`.

**Câu 8.** Hai BitSet có dung lượng ban đầu 64 và 1024 nhưng đều rỗng có thể `equals` không?  
**Đáp án:** Có. `BitSet.equals` so sánh trạng thái bit, không so sánh `size()`.

**Câu 9.** Một BitSet được tạo bởi `new BitSet(16)` có tự từ chối `set(16)` không?  
**Đáp án:** Không. Chỉ số không âm 16 hợp lệ với BitSet; muốn giới hạn miền 0..15 thì ứng dụng tự kiểm tra.

**Câu 10.** Hai thread `set(2)` và `set(3)` trên cùng một BitSet có tự an toàn vì khác chỉ số không?  
**Đáp án:** Không. JavaDoc không bảo đảm thread safety; dùng đồng bộ ngoài hoặc cấu trúc dữ liệu khác phù hợp.

**Câu 11.** Đặt `volatile BitSet bits` rồi gọi `bits.set` từ nhiều thread đã giải quyết race chưa?  
**Đáp án:** Chưa. `volatile` trên tham chiếu không làm mọi cập nhật nội bộ BitSet thành atomic.

**Câu 12.** `synchronized(lock) { return bits.stream(); }` có đủ bảo vệ việc duyệt không?  
**Đáp án:** Không nhất thiết. Stream gắn với nguồn khi terminal operation chạy, có thể sau khi khóa đã thả. Dùng snapshot dưới lock hoặc giữ lock suốt terminal operation.

**Câu 13.** `(BitSet) bits.clone()` có tạo một snapshot độc lập không?  
**Đáp án:** Có nếu được tạo khi trạng thái nguồn nhất quán; với nguồn đang bị cập nhật từ thread khác phải clone khi giữ cùng khóa/cơ chế phối hợp.

**Câu 14.** `BitSet.stream()` trả các giá trị boolean hay chỉ số của bit bật?  
**Đáp án:** Các **chỉ số int** của bit bật theo thứ tự tăng dần.

**Câu 15.** Khi duyệt bằng `nextSetBit(i+1)`, tại sao cần guard `i==Integer.MAX_VALUE`?  
**Đáp án:** Vì `i+1` trên `int` sẽ overflow thành số âm và lời gọi `nextSetBit` sau đó sẽ không hợp lệ.

**Câu 16.** Tại sao hai biến cùng tham chiếu BitSet không tạo snapshot?  
**Đáp án:** Vì gán tham chiếu không clone đối tượng. Muốn tách trạng thái, clone hoặc dùng `get(from,to)` tùy phạm vi.

## 16. Tài liệu chính thức

- [Oracle Java SE 26 — java.util.BitSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html): định nghĩa chỉ số không âm, BitSet mở rộng khi cần, khác biệt giữa `size()` và `length()`, trạng thái ban đầu và **cảnh báo không thread-safe**.
- [Oracle Java SE 26 — BitSet.set/get/clear/flip](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html#set(int,int)): khoảng `[from,to)` và `IndexOutOfBoundsException` khi biên không hợp lệ.
- [Oracle Java SE 26 — BitSet.nextSetBit](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html#nextSetBit(int)): sentinel `-1`, lỗi index âm và guard `Integer.MAX_VALUE` chống overflow.
- [Oracle Java SE 26 — BitSet.previousSetBit](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html#previousSetBit(int)): ý nghĩa đặc biệt của `fromIndex=-1` và ngoại lệ khi nhỏ hơn `-1`.
- [Oracle Java SE 26 — BitSet.isEmpty/cardinality/length/size](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html): bốn đại lượng có ý nghĩa khác nhau.
- [Oracle Java SE 26 — BitSet.stream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html#stream()): stream các index bật, *late-binding* và kết quả không xác định nếu BitSet bị sửa trong terminal operation.
- [Oracle Java SE 26 — BitSet.equals/clone](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/BitSet.html): so sánh theo bit đang bật, sao chép giá trị vào đối tượng BitSet mới.
- [Oracle Java SE 7 — java.util.BitSet](https://docs.oracle.com/javase/7/docs/api/java/util/BitSet.html): nguồn lịch sử về các method có từ Java 7, trong đó có `previousSetBit`/`previousClearBit`.
- [Oracle Java SE 26 — java.util.concurrent.atomic.AtomicLongArray](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLongArray.html): phần tử long với thao tác atomic, có thể làm cơ sở cho bộ cờ đồng thời được thiết kế riêng.
- [Oracle Java SE 26 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): lựa chọn API Set đồng thời qua `newKeySet()` khi mô hình dữ liệu là tập chỉ số thưa.
- [Oracle Java SE 26 — java.util.concurrent.Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): `get()` đợi nhiệm vụ hoàn thành, quan trọng khi kiểm tra kết quả cập nhật từ executor.

**Ghi nhớ:** `BitSet` cho phép chỉ số bit **không âm** và khoảng **[from,to)**; một BitSet có sức chứa lớn vẫn có thể **rỗng**; `cardinality` đếm bit bật còn `length` chỉ vị trí bật cao nhất +1. Khi chia sẻ cùng một BitSet giữa các thread, **đừng dựa vào may mắn**: bảo vệ mọi thao tác bằng một chính sách đồng bộ nhất quán hoặc chuyển giao các bản sao độc lập được tạo an toàn.