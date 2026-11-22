# Bộ đệm đối tượng lớp bao và vì sao không dựa vào `==` — Java 17+

## 1. Câu hỏi cốt lõi: cùng số có phải cùng đối tượng?

Java có kiểu nguyên thủy `int` và lớp bao tương ứng `Integer`. Hai biến `Integer` có thể chứa **cùng giá trị số** nhưng **không nhất thiết cùng tham chiếu tới một object**.

~~~java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);

System.out.println(a == b);      // true: vùng cache được bảo đảm
System.out.println(a.equals(b)); // true: cùng giá trị Integer
~~~

Kết quả `a == b` ở ví dụ này là `true` vì `Integer.valueOf` bảo đảm tái sử dụng object cho khoảng giá trị **-128 đến 127**. Nhưng hãy đổi giá trị sang `1000`:

~~~java
Integer x = Integer.valueOf(1000);
Integer y = Integer.valueOf(1000);

System.out.println(x.equals(y)); // true: luôn bằng nhau về giá trị
// Không dựa vào (x == y): identity ở giá trị này không được bảo đảm.
~~~

**Không có expected output cố định cho `x == y` ở ví dụ 1000.** Một số JVM/cấu hình cache thêm số lớn; một số khác không. Việc code chạy “đúng” trên máy hiện tại không biến cách so identity thành phép so giá trị được bảo đảm trên mọi môi trường Java.

**Kết luận trước khi đi sâu:** muốn biết **giá trị của hai wrapper có bằng nhau không**, dùng `equals` hoặc `Objects.equals` tùy khả năng `null`. Chỉ dùng `==` trên hai tham chiếu khi **chủ đích thật sự là kiểm tra cùng object**.

## 2. Vì sao wrapper có thể được cache?

Wrapper là đối tượng tham chiếu **bất biến** chứa một giá trị nguyên thủy; ví dụ `Integer` đóng gói `int`, `Character` đóng gói `char`. Vì object không thể đổi giá trị sau khi tạo, Java có thể chia sẻ wrapper cho những giá trị thường gặp mà không làm thay đổi nghĩa của giá trị.

~~~java
int primitive = 10;
Integer wrapper = primitive; // Autoboxing.
System.out.println(wrapper.equals(10)); // true: so giá trị.
~~~

`int` không mang identity tham chiếu, còn `Integer` có thể `null` và dùng trong `List<Integer>`. Các cặp primitive/wrapper và quy tắc boxing đã được trình bày ở bài tổng quan; ở đây tập trung **vùng cache, bảo đảm identity và lý do không dùng cache trong business logic**.


## 3. Cache đối tượng lớp bao là gì?

Khi cần biểu diễn các giá trị xuất hiện rất thường xuyên, class wrapper có thể **tái sử dụng những object bất biến** đã có. Gọi là *wrapper cache*.

Mô hình ý tưởng:

~~~mermaid
flowchart LR
    A["Integer a = 127"] -->|"autoboxing"| C["Integer instance: 127"]
    B["Integer b = 127"] -->|"autoboxing"| C
    X["Integer x = 1000"] -->|"identity ngoài vùng bảo đảm"| D["Object tùy triển khai"]
    Y["Integer y = 1000"] -->|"identity ngoài vùng bảo đảm"| E["Object tùy triển khai"]
~~~

Các mũi tên tới hai object ở giá trị 1000 chỉ nhằm nhấn mạnh **không thể suy ra identity theo giá trị**: tùy cấu hình, hai biến đó *có thể* tham chiếu cùng object hoặc khác object. Sơ đồ không được dùng để khẳng định luôn có hai object cho số 1000.

**Vì sao cache có ích?** Object wrapper là immutable; dùng lại một object cho giá trị nhất định không làm thay đổi nội dung của object đó. Việc chia sẻ đối tượng có thể giảm nhu cầu tạo object mới ở một số tình huống, nhưng **cache là chi tiết của cơ chế triển khai với phạm vi bảo đảm nhất định**, không phải phép so giá trị dành cho ứng dụng.

## 4. Các khoảng identity được bảo đảm và phần không bảo đảm

Trong Java 17, những giá trị boxed thường dùng có **một vùng identity được bảo đảm**. Các factory tương ứng thể hiện điều này qua đặc tả API:

| Wrapper | Giá trị được bảo đảm tái sử dụng khi boxing/`valueOf` | Ghi chú |
|---|---|---|
| `Byte` | Toàn bộ `byte`: -128..127 | Toàn bộ miền Byte |
| `Short` | -128..127 | Số ngoài vùng này có thể được cache thêm |
| `Integer` | -128..127 | Vùng cache quen thuộc |
| `Long` | -128..127 | Đừng suy rộng tới mọi `long` |
| `Character` | U+0000..U+007F | 128 UTF-16 code units đầu tiên |
| `Boolean` | `true` và `false` | Hai instance chuẩn `Boolean.TRUE`/`FALSE` |
| `Float`, `Double` | Không có khoảng cache giá trị số tương tự được bảo đảm cho mọi boxing | Không dựa vào identity của wrapper số thực |

Ví dụ kết quả có thể dự đoán:

~~~java
Integer x = Integer.valueOf(-128);
Integer y = Integer.valueOf(-128);
System.out.println(x == y); // true

Character c1 = Character.valueOf('A');
Character c2 = Character.valueOf('A');
System.out.println(c1 == c2); // true

Long l1 = Long.valueOf(127L);
Long l2 = Long.valueOf(127L);
System.out.println(l1 == l2); // true
~~~

**Cần hiểu kỹ:** với `Integer.valueOf(128)` hoặc `Long.valueOf(1000L)`, Java có thể dùng cache mở rộng; bạn **không được bảo đảm true hoặc false** khi so hai kết quả boxing độc lập bằng `==`. Một số cấu hình JVM có tùy chọn mở rộng cache `Integer`, nhưng giá trị cấu hình không nên trở thành điều kiện đúng của business logic.

**Không tạo wrapper bằng constructor để thử “ép ra hai object”.** Các constructor số wrapper như `new Integer(...)` đã bị deprecated để loại bỏ trong Java mới. `valueOf`, autoboxing và các API so nội dung thích hợp là cách dùng thông thường.

## 5. `==` kiểm tra identity, `equals` kiểm tra nội dung

Với **hai biểu thức đều có kiểu tham chiếu `Integer`**, toán tử `==` kiểm tra chúng có trỏ cùng object hay không:

~~~java
Integer first = Integer.valueOf(1000);
Integer alias = first;
Integer second = Integer.valueOf(1000);

System.out.println(first == alias); // true: gán alias không tạo object khác
System.out.println(first.equals(second)); // true: cùng giá trị 1000
~~~

Không in `first == second` kèm expected output vì Java không bảo đảm identity cho giá trị 1000.

Phân biệt các phép so:

| Biểu thức | Ý nghĩa |
|---|---|
| `a == b` với hai `int` | So giá trị primitive |
| `a == b` với hai `Integer` | So identity tham chiếu |
| `a.equals(b)` với `Integer` không null | So giá trị của hai `Integer` |
| `Objects.equals(a, b)` | So equality và xử lý trường hợp null |
| `a.compareTo(b) == 0` với `Integer` không null | So thứ tự số, kết quả 0 khi cùng giá trị |

`Integer.equals` chỉ xem wrapper `Integer` có cùng giá trị, không tự chuyển mọi kiểu số khác nhau thành `Integer`:

~~~java
Integer n = Integer.valueOf(5);
Long m = Long.valueOf(5L);
System.out.println(n.equals(m)); // false
~~~

Đây là **khác kiểu wrapper**, không phải do cache.

## 6. `==` giữa wrapper và primitive: có thể là so số

Xét:

~~~java
Integer boxed = Integer.valueOf(1000);
int primitive = 1000;

System.out.println(boxed == primitive); // true
~~~

**Vì sao true dù 1000 ngoài vùng cache bảo đảm?** Một toán hạng có kiểu `int`, vì vậy Java **unbox** `boxed` rồi so hai giá trị primitive. Đây không phải reference identity.

Điều này khác rõ rệt với:

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);
// a == b là so tham chiếu: không dùng để kiểm tra số bằng nhau.
~~~

Vì thế phát biểu “`==` với Integer luôn sai” cũng không chính xác. Phải xét **kiểu của cả hai toán hạng**:

- `Integer == Integer`: so tham chiếu.
- `Integer == int`: unboxing rồi so giá trị số, nếu wrapper không null.
- `int == int`: so giá trị số.
- `Integer.equals(Integer)`: so giá trị được class Integer định nghĩa.

**Bẫy null:** nếu `boxed == null`, biểu thức `boxed == primitive` sẽ ném `NullPointerException` khi unbox. Ngược lại, `boxed == null` là phép kiểm tra tham chiếu null an toàn.

## 7. Null không phải một giá trị được cache

Một biến `Integer` có thể mang `null`, khác với một object `Integer.valueOf(0)`. So sánh `maybe == null` không unbox; còn `maybe == 0` có thể unbox và ném `NullPointerException`:

~~~java
Integer maybe = null;
System.out.println(maybe == null); // true.
System.out.println(java.util.Objects.equals(maybe, (Integer) null)); // true.
~~~

`Objects.equals(a,b)` xử lý cả hai null theo ngữ nghĩa equality; nhưng nó không thay thế validation nếu nghiệp vụ yêu cầu giá trị hiện diện. Việc cache một wrapper không làm một tham chiếu null trở thành “cached zero”, và không thay đổi quy tắc NPE khi unboxing.


## 8. Cache không đồng nghĩa wrapper có thể thay đổi

Wrapper tiêu chuẩn như `Integer`, `Long`, `Character` là **immutable**. Khi cùng chia sẻ object cached, thay đổi một biến không thể sửa “giá trị bên trong object cached” để ảnh hưởng người khác.

~~~java
Integer before = Integer.valueOf(5);
Integer count = before;
count++;

System.out.println(before); // 5
System.out.println(count);  // 6
~~~

Về ngữ nghĩa, `count++` thực hiện **unbox → cộng 1 → box → gán lại biến `count`**, không sửa object cũ. Biến `before` vẫn giữ giá trị 5.

~~~java
final Integer limit = Integer.valueOf(5);
// limit++; // Lỗi compile: phép ++ cần gán lại biến final
~~~

Nếu bạn thật sự cần một bộ đếm mutable chia sẻ giữa các thành phần, wrapper `Integer` không đáp ứng vai trò đó. Hãy thiết kế một object có trạng thái mutable, hoặc dùng `AtomicInteger` khi phù hợp với yêu cầu tương tranh.

## 9. Collection dùng equals, không dựa vào cache

Các collection thông dụng dùng hợp đồng `equals` và `hashCode` để kiểm tra phần tử/khóa.

~~~java
import java.util.List;
import java.util.Map;

Integer key1 = Integer.valueOf(1000);
Integer key2 = Integer.valueOf(1000);

List<Integer> list = List.of(key1);
Map<Integer, String> map = Map.of(key1, "found");

System.out.println(list.contains(key2)); // true
System.out.println(map.get(key2));       // found
~~~

Ở đây giá trị `1000` nằm ngoài vùng cache bắt buộc, **nhưng** `List.contains` và `Map.get` vẫn xử lý đúng theo equality của `Integer`. Không phải kiểm tra hai tham chiếu bằng `==`.

**Ngoại lệ cố ý:** `IdentityHashMap` dùng identity (`==`) cho key, nên không tương đương `HashMap` trong nghiệp vụ yêu cầu equality theo giá trị. Đừng đổi qua `IdentityHashMap` chỉ vì muốn tối ưu hoặc vì nghe tên có “map”.

Hãy coi việc chọn collection là chọn **hợp đồng so sánh**, không phải chọn một cách tận dụng cache.

## 10. Không dự đoán cấp phát hoặc hiệu năng từ cache

Không phải mỗi lệnh autobox đều nhất định tạo object mới; cũng không phải mọi wrapper ngoài vùng cache đều nhất định cấp phát object mới. JVM có thể dùng cache hoặc thực hiện tối ưu hóa nội bộ, còn ngữ nghĩa chương trình phải giữ đúng theo Java.

~~~java
Integer a = 1000;
Integer b = 1000;
// Không thể dùng (a == b) làm phép đo tin cậy về cấp phát,
// và không thể dựa vào kết quả này để quyết định a,b có cùng giá trị.
~~~

**Các sai lầm cần tránh:**

- Dựa vào `System.identityHashCode(a)` để tuyên bố hai object có cùng địa chỉ; identity hash không phải địa chỉ bộ nhớ và có thể trùng giữa các object khác nhau.
- In `a.toString()` rồi so chuỗi hiển thị để quyết định hai tham chiếu có giống nhau không.
- Chuyển sang `int` chỉ để tránh cache mà không cân nhắc `null`.
- Viết business logic phụ thuộc kết quả `Integer.valueOf(128) == Integer.valueOf(128)`.
- Kết luận tốc độ hoặc lượng bộ nhớ từ một vài lần đo thủ công không warm-up.

Trong những vòng lặp tính số nhiều lần, **primitive `int`/`long` thường là lựa chọn mặc định dễ hiểu hơn** nếu không cần nullable hay generic. Nếu cần đo hiệu năng Java, dùng công cụ benchmark đúng phương pháp (ví dụ JMH) và đo trên dữ liệu tương đương thực tế.

## 11. Chương trình Java 17 hoàn chỉnh, chạy độc lập

Tạo tệp đúng tên **`WrapperCacheDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class WrapperCacheDemo {
    private WrapperCacheDemo() {}

    public static void main(String[] args) {
        Integer small1 = Integer.valueOf(127);
        Integer small2 = Integer.valueOf(127);
        System.out.println("Integer cached 127=" + (small1 == small2));

        Byte byte1 = Byte.valueOf((byte) 127);
        Byte byte2 = Byte.valueOf((byte) 127);
        System.out.println("Byte cached 127=" + (byte1 == byte2));

        Short short1 = Short.valueOf((short) -128);
        Short short2 = Short.valueOf((short) -128);
        System.out.println("Short cached -128=" + (short1 == short2));

        Long long1 = Long.valueOf(127L);
        Long long2 = Long.valueOf(127L);
        System.out.println("Long cached 127=" + (long1 == long2));

        Character char1 = Character.valueOf('A');
        Character char2 = Character.valueOf('A');
        System.out.println("Character cached A=" + (char1 == char2));

        Boolean bool1 = Boolean.valueOf(true);
        Boolean bool2 = Boolean.valueOf(true);
        System.out.println("Boolean shared true=" + (bool1 == bool2));

        Integer large1 = Integer.valueOf(1000);
        Integer large2 = Integer.valueOf(1000);
        Integer alias = large1;
        // Không dùng large1 == large2: identity ngoài vùng cache bảo đảm.
        System.out.println("large equality=" + large1.equals(large2));
        System.out.println("large compareTo=" + (large1.compareTo(large2) == 0));
        System.out.println("large alias identity=" + (large1 == alias));
        System.out.println("wrapper vs int=" + (large1 == 1000));

        Integer missing = null;
        System.out.println("null check=" + (missing == null));
        System.out.println("two nulls equal="
                + Objects.equals(missing, (Integer) null));
        System.out.println("null vs value=" + Objects.equals(missing, large1));
        try {
            System.out.println("null vs primitive=" + (missing == 0));
        } catch (NullPointerException ex) {
            System.out.println("null unboxing=NullPointerException");
        }

        Integer previous = Integer.valueOf(5);
        Integer incremented = previous;
        incremented++;
        System.out.println("previous wrapper=" + previous);
        System.out.println("incremented wrapper=" + incremented);

        List<Integer> list = List.of(large1);
        Map<Integer, String> map = Map.of(large1, "found");
        System.out.println("list contains equal wrapper=" + list.contains(large2));
        System.out.println("map lookup equal wrapper=" + map.get(large2));

        Integer numericFive = Integer.valueOf(5);
        Long longFive = Long.valueOf(5L);
        System.out.println("cross-class equals=" + numericFive.equals(longFive));
    }
}
~~~

**Yêu cầu:** JDK 17+ và terminal đang trong thư mục chứa file. Ví dụ không cần Maven/Gradle hay thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 WrapperCacheDemo.java
java -cp . WrapperCacheDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\WrapperCacheDemo.java
java -cp . WrapperCacheDemo
~~~

**Expected output chính xác, không phụ thuộc cache mở rộng:**

~~~text
Integer cached 127=true
Byte cached 127=true
Short cached -128=true
Long cached 127=true
Character cached A=true
Boolean shared true=true
large equality=true
large compareTo=true
large alias identity=true
wrapper vs int=true
null check=true
two nulls equal=true
null vs value=false
null unboxing=NullPointerException
previous wrapper=5
incremented wrapper=6
list contains equal wrapper=true
map lookup equal wrapper=found
cross-class equals=false
~~~

**Vì sao đầu ra ổn định?** Chương trình chỉ in identity ở **vùng bảo đảm chia sẻ** hoặc với **alias thật sự**. Với 1000, chương trình dùng `equals`/`compareTo` và các collection theo equality, **không in kết quả `large1 == large2`**. Vì vậy cache ngoài -128..127 có mở rộng hay không cũng không làm expected output thay đổi.

Điểm cần quan sát thêm:

1. Các wrapper nguyên nhỏ và ký tự ASCII sử dụng identity được bảo đảm bởi cache.
2. Hai `Integer` biểu diễn 1000 vẫn so giá trị chính xác bằng `equals`, dù không dựa vào identity.
3. `Integer == int` có unboxing trước khi so; khác `Integer == Integer`.
4. Kiểm tra `missing == null` an toàn; `missing == 0` cố unbox null và gây ngoại lệ.
5. `incremented++` không thay giá trị mà biến `previous` quan sát.
6. `List.contains`/`Map.get` vẫn hoạt động theo equality của wrapper.
7. Wrapper khác class (`Integer` và `Long`) không tự `equals` chỉ vì cùng biểu diễn số 5.

## 12. Bảng tổng hợp: nên dùng phép so nào?

| Mục đích | Cách làm | Tại sao |
|---|---|---|
| Hai `int` có cùng giá trị không? | `a == b` | Cả hai primitive |
| Hai `Integer` không null có cùng giá trị? | `a.equals(b)` | So giá trị, không dựa vào cache |
| Hai `Integer` có thể null có bằng nhau? | `Objects.equals(a,b)` | Bảo vệ null |
| Hai biến tham chiếu có chỉ cùng object? | `a == b` | Chủ đích so identity |
| Một wrapper có null không? | `a == null` | Không unbox |
| So wrapper với primitive, biết wrapper không null | `boxed == primitive` | Unbox rồi so số |
| Giá trị wrapper có giống số nhưng khác lớp? | Chọn chính sách đổi kiểu có kiểm soát | `Integer.equals(Long)` không tự so số |
| Collection generic dùng `Integer` làm key | `HashMap`/`Map.of` theo `equals` | Không phụ thuộc identity cache |

**Không dùng `==` chỉ vì các ví dụ số nhỏ đều in `true`.** Đó là tình huống cache làm bug ẩn đi: khi dữ liệu được mở rộng hoặc chuyển JVM, kết quả identity có thể khác.

## 13. Những lỗi thường gặp

| Lỗi / giả định | Điều thực sự xảy ra | Cách xử lý |
|---|---|---|
| `Integer a = 127; Integer b = 127; a == b` true nên luôn dùng `==` | Giá trị 127 nằm vùng cache bảo đảm | Dùng `equals` để so giá trị |
| `Integer.valueOf(128) == Integer.valueOf(128)` chắc chắn false | Cache có thể được mở rộng | Không khẳng định true/false ngoài vùng bảo đảm |
| Hai `Integer` có cùng số thì luôn cùng object | Wrapper có identity riêng với cùng giá trị | So bằng `equals` |
| Hai `Integer` khác object thì có giá trị khác nhau | `==` không phản ánh equality | Dùng `equals` |
| `Integer a == int b` là so identity | Java unbox wrapper khi so số | Cẩn thận null |
| `null Integer == 0` trả false | Unboxing null gây NPE | Kiểm tra null trước |
| `a.equals(b)` an toàn khi a null | Gọi method trên null ném NPE | `Objects.equals(a, b)` |
| `Integer.valueOf(5).equals(Long.valueOf(5L))` true | equals của Integer yêu cầu đúng kiểu | Xác định chính sách so số khác kiểu |
| Dùng `new Integer(...)` để tránh cache | Constructor deprecated để loại bỏ | Dùng `valueOf`, không cần cố điều khiển identity |
| `System.identityHashCode` chính là địa chỉ object | Giá trị hash không phải địa chỉ và không duy nhất | Không suy địa chỉ từ hash |
| Cache tự biến wrapper thành mutable | Wrapper vẫn immutable | `++` là phép tính và gán lại |
| `HashMap` dùng `==` cho key | Thông thường dùng `equals` và `hashCode` | Dùng đúng collection theo semantics |
| Wrapper không tạo chi phí vì có cache | Cache không bảo đảm loại bỏ mọi cấp phát | Chọn primitive khi phù hợp, benchmark đúng |

## 14. Bài tập kèm đáp án

### Bài A — cùng tham chiếu

~~~java
Integer a = Integer.valueOf(1000);
Integer b = a;
System.out.println(a == b);
~~~

**Đáp án:** `true`. `b = a` sao chép cùng giá trị tham chiếu, không liên quan giá trị 1000 có được cache hay không.

### Bài B — cùng giá trị, identity không được bảo đảm

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);
System.out.println(a.equals(b));
~~~

**Đáp án:** `true`. Không nên viết expected output cố định cho `a == b` trong ví dụ này; ngữ nghĩa được yêu cầu là **bằng nhau về giá trị**.

### Bài C — cache số nhỏ

~~~java
Long x = Long.valueOf(127L);
Long y = Long.valueOf(127L);
System.out.println(x == y);
~~~

**Đáp án:** `true`. Vùng -128..127 được bảo đảm chia sẻ cho `Long.valueOf`.

### Bài D — wrapper so với primitive

~~~java
Integer wrapped = Integer.valueOf(1000);
int raw = 1000;
System.out.println(wrapped == raw);
~~~

**Đáp án:** `true`. Java unbox wrapped thành int rồi so giá trị primitive.

### Bài E — null và unboxing

~~~java
Integer value = null;
System.out.println(value == null);
// System.out.println(value == 1);
~~~

**Đáp án:** dòng đầu in `true`. Nếu chạy dòng cuối, auto-unboxing của value null làm ném `NullPointerException`.

### Bài F — HashMap dựa vào giá trị

~~~java
java.util.Map<Integer, String> map = new java.util.HashMap<>();
map.put(Integer.valueOf(1000), "ok");
System.out.println(map.get(Integer.valueOf(1000)));
~~~

**Đáp án:** `ok`. `Integer.hashCode`/`equals` dựa trên giá trị, nên key tương đương được tìm thấy mà không cần cùng object.

## 15. Checklist hoàn thành

- [ ] Phân biệt `int` primitive với `Integer` wrapper.
- [ ] Giải thích được boxing cache và lợi ích tái sử dụng wrapper immutable.
- [ ] Nhớ vùng identity được bảo đảm của `Integer.valueOf`: -128..127.
- [ ] Biết `Byte` cache toàn miền, `Character` cache 0..127, `Boolean` có các instance chuẩn.
- [ ] Biết ngoài vùng được bảo đảm, cache có thể mở rộng nên `==` không đáng tin để so giá trị.
- [ ] Biết `Integer == Integer` so tham chiếu, `Integer == int` unbox rồi so số.
- [ ] Dùng `equals` cho wrapper không null và `Objects.equals` khi có thể null.
- [ ] Không unbox `null` trong toán tử, phép gán hoặc tham số primitive.
- [ ] Hiểu wrapper immutable: `count++` không sửa object cũ.
- [ ] Biết `Integer.equals(Long)` không tự đổi kiểu wrapper để so số.
- [ ] Biết collection thông thường dùng equality, không dựa vào wrapper cache.
- [ ] Không lấy cache/identityHashCode làm cơ sở dự đoán hiệu năng hoặc địa chỉ bộ nhớ.
- [ ] Biên dịch và chạy `WrapperCacheDemo.java` với Java 17+, so đúng expected output.

**Kết luận:** Wrapper cache làm một số phép `==` trên các giá trị nhỏ trả `true`, nhưng **`==` không phải phép so giá trị giữa hai wrapper**. Cache ngoài những vùng được Java bảo đảm có thể thay đổi tùy JVM. Để code chính xác và dễ bảo trì, dùng `equals` hoặc `Objects.equals` khi muốn so giá trị, xử lý `null` trước unboxing và chỉ dùng `==` khi thật sự muốn kiểm tra cùng một đối tượng.