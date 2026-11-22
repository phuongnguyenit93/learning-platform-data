# StringBuilder: Constructor, length và capacity trong Java

`StringBuilder` là lớp Java dùng để **xây dựng và thay đổi chuỗi ký tự** qua nhiều thao tác như `append()`, `insert()` và `delete()`. Khác với `String` bất biến, một `StringBuilder` thay đổi trực tiếp nội dung của chính đối tượng. Để sử dụng đúng, cần tách bạch **độ dài nội dung** và **dung lượng dự trữ**:

- **`length()`:** số đơn vị mã UTF-16 hiện có trong nội dung.
- **`capacity()`:** số đơn vị mã UTF-16 mà builder có thể chứa trước khi phải mở rộng vùng lưu trữ.

Một builder có thể hoàn toàn rỗng (`length() == 0`) nhưng vẫn có `capacity() == 100`. Điều này **không có nghĩa** nó đang chứa 100 dấu cách, cũng không có nghĩa có thể truy cập `charAt(99)`. Chỉ các vị trí từ `0` đến `length() - 1` mới thuộc nội dung hiện có.

## 1. Vì sao dùng StringBuilder?

Khi liên tục tạo chuỗi mới bằng phép nối `String` trong một vòng lặp, chương trình có thể phải tạo nhiều đối tượng trung gian. `StringBuilder` cho phép tích lũy văn bản thông qua một đối tượng có thể thay đổi:

~~~java
StringBuilder builder = new StringBuilder();
builder.append("Java");
builder.append(' ');
builder.append(17);

String result = builder.toString();
System.out.println(result); // Java 17
~~~

Đây là **đoạn code minh họa**, đặt trong một phương thức Java. `append(17)` nối biểu diễn chữ số của số nguyên. `toString()` tạo một `String` biểu diễn nội dung hiện tại. Dù tiếp tục thay đổi `builder`, giá trị `result` đã có không bị thay đổi theo.

Lớp `StringBuilder` không tự đồng bộ khi nhiều luồng đồng thời thao tác trên cùng một đối tượng. Trong các trường hợp xây dựng nội dung cục bộ ở một luồng, đây là công cụ tiện lợi và thường hiệu quả.

## 2. Bốn constructor thường dùng

| Constructor | Nội dung khởi tạo | Length ban đầu | Capacity ban đầu |
| --- | --- | ---: | ---: |
| `new StringBuilder()` | Chuỗi rỗng | 0 | **16** |
| `new StringBuilder(int capacity)` | Chuỗi rỗng | 0 | **capacity** |
| `new StringBuilder(String str)` | Nội dung của `str` | `str.length()` | **`str.length() + 16`** |
| `new StringBuilder(CharSequence seq)` | Nội dung của `seq` | `seq.length()` | **`seq.length() + 16`** |

Mọi độ dài và dung lượng ở bảng này đều theo **đơn vị mã UTF-16**, không phải số byte của UTF-8 hay số Unicode code point.

### 2.1. new StringBuilder(): dung lượng mặc định 16

~~~java
StringBuilder a = new StringBuilder();
System.out.println(a.length());   // 0
System.out.println(a.capacity()); // 16
System.out.println(a.toString().isEmpty()); // true
~~~

Mười sáu đơn vị là chỗ dự trữ, không phải ký tự đã tồn tại. `a.charAt(0)` vẫn gây `StringIndexOutOfBoundsException` vì length bằng 0.

### 2.2. new StringBuilder(int): chủ động dự trữ chỗ

~~~java
StringBuilder b = new StringBuilder(5);
System.out.println(b.length());   // 0
System.out.println(b.capacity()); // 5

b.append("Hi");
System.out.println(b.length());   // 2
System.out.println(b.capacity()); // 5
~~~

Dự trữ 5 đơn vị giúp thêm "Hi" (hai UTF-16 code unit) mà không cần mở rộng. Nếu dùng `new StringBuilder(0)` thì hoàn toàn hợp lệ: length và capacity ban đầu đều bằng 0; khi append một ký tự, builder tăng capacity khi cần.

Nếu capacity âm, constructor ném `NegativeArraySizeException`:

~~~java
new StringBuilder(-1); // ném NegativeArraySizeException
~~~

Đây là **dòng code minh họa về ngoại lệ**, không phải một chương trình độc lập. Truyền capacity quá lớn có thể thất bại vì giới hạn vùng nhớ; không nên dự trữ vô hạn chỉ để “chắc chắn”.

### 2.3. new StringBuilder(String): khởi tạo với nội dung

~~~java
StringBuilder c = new StringBuilder("Java");
System.out.println(c.length());   // 4
System.out.println(c.capacity()); // 20
System.out.println(c.toString()); // Java
~~~

Ở đây nội dung đã có bốn UTF-16 code unit nên length = 4 và capacity = 4 + 16 = 20. So sánh:

~~~java
StringBuilder fromNumber = new StringBuilder(20);
StringBuilder fromText = new StringBuilder("20");

System.out.println(fromNumber.length());   // 0
System.out.println(fromNumber.capacity()); // 20
System.out.println(fromText.length());     // 2
System.out.println(fromText.capacity());   // 18
~~~

Hai constructor có ý nghĩa **khác hẳn**: số nguyên là *dung lượng*, còn chuỗi là *nội dung*. Constructor nhận `String` yêu cầu đối số khác null; `new StringBuilder((String) null)` ném `NullPointerException`.

### 2.4. new StringBuilder(CharSequence): khởi tạo từ giao diện văn bản

`CharSequence` là giao diện chung cho `String`, `StringBuilder`, `StringBuffer` và các kiểu cung cấp dãy ký tự.

~~~java
CharSequence source = "ABC";
StringBuilder d = new StringBuilder(source);
System.out.println(d.length());   // 3
System.out.println(d.capacity()); // 19
System.out.println(d.toString()); // ABC
~~~

Đối tượng mới nhận nội dung từ nguồn với capacity = `seq.length() + 16`. Constructor nhận `CharSequence` cũng yêu cầu đối số khác null. Nếu gọi `new StringBuilder("ABC")` trực tiếp với literal kiểu `String` thì trình biên dịch chọn overload nhận `String` cụ thể hơn, nhưng kết quả length/capacity ban đầu ở trường hợp này vẫn tương ứng 3/19.

## 3. length() và capacity(): hiểu bằng sơ đồ

Ví dụ:

~~~java
StringBuilder sb = new StringBuilder(8);
sb.append("Cat");
~~~

~~~text
Nội dung:             C  a  t
UTF-16 offset:        0  1  2
                  +--+--+--+--+--+--+--+--+
Sức chứa (8 unit) | C| a| t|  |  |  |  |  |
                  +--+--+--+--+--+--+--+--+

length()   = 3
capacity() = 8
~~~

Sơ đồ mô tả **sức chứa theo API**, không phải sơ đồ byte RAM thực tế. Năm vị trí còn lại chưa thuộc nội dung. Vì vậy:

- `sb.charAt(0)`, `sb.charAt(1)`, `sb.charAt(2)` hợp lệ.
- `sb.charAt(3)` **không hợp lệ**, dù capacity là 8.
- `sb.toString()` tạo `"Cat"`, không phải `"Cat     "`.

Quan hệ luôn cần đúng trong trạng thái hợp lệ:

~~~text
0 <= length() <= capacity()
~~~

`capacity() - length()` là **dung lượng chưa dùng theo UTF-16 code unit**. Nó không phải số ký tự hiển thị được phép thêm, vì nhiều emoji chiếm hai UTF-16 code unit.

## 4. append() và quy luật nới capacity

`append()` làm tăng length theo lượng văn bản thêm vào; capacity chỉ tăng nếu vùng dự trữ không đủ.

~~~java
StringBuilder sb = new StringBuilder(3);
sb.append("AB");
System.out.println(sb.length());    // 2
System.out.println(sb.capacity());  // 3

sb.append("CDE");
System.out.println(sb.length());    // 5
System.out.println(sb.capacity() >= 5); // true
System.out.println(sb.toString());  // ABCDE
~~~

Sau lệnh append thứ hai, 5 UTF-16 unit đã vượt capacity ban đầu là 3, nên builder cần tăng dung lượng. Giá trị capacity mới có thể **lớn hơn** length hiện tại để giúp những lần append sau không phải liên tục cấp phát lại.

Trong các triển khai Java, có thể quan sát một chiến lược tăng dung lượng liên quan đến `2 * oldCapacity + 2`, nhưng **không nên viết logic nghiệp vụ hoặc test phụ thuộc vào đúng con số capacity sau tự tăng trưởng**. Điều quan trọng là sức chứa vẫn đủ và nội dung được giữ nguyên.

### Dự trữ trước với ước lượng hợp lý

~~~java
int estimatedUnits = 1000;
StringBuilder out = new StringBuilder(estimatedUnits);
for (int i = 0; i < 100; i++) {
    out.append("item=").append(i).append(';');
}
String result = out.toString();
~~~

Đây là **đoạn minh họa đặt trong phương thức**. Khi có thể ước lượng số UTF-16 unit đầu ra, dự trữ capacity thích hợp có thể giảm số lần tăng vùng chứa. Tuy nhiên ước lượng quá lớn cũng có thể lãng phí bộ nhớ. Chỉ tối ưu sau khi hiểu quy mô dữ liệu và đo hiệu năng khi cần.

## 5. ensureCapacity(): đảm bảo vùng chứa, không thêm nội dung

`ensureCapacity(int minimumCapacity)` yêu cầu có ít nhất `minimumCapacity` đơn vị sức chứa, nếu cần thì tăng capacity. Phương thức **không chèn ký tự**, không đặt length mới, không xóa nội dung hiện hữu.

~~~java
StringBuilder sb = new StringBuilder(3);
sb.ensureCapacity(20);

System.out.println(sb.length());          // 0
System.out.println(sb.capacity() >= 20);  // true

sb.append("Hello");
System.out.println(sb.length());          // 5
System.out.println(sb.capacity() >= 20);  // true
~~~

**Những điều cần nhớ:**

1. Nếu capacity hiện tại đã đủ, lời gọi không cần nới chỗ.
2. Với `minimumCapacity <= 0`, lời gọi không tăng capacity.
3. Với yêu cầu lớn hơn, builder tăng dung lượng đủ chứa, trong giới hạn cấp phát của JVM.
4. `ensureCapacity(20)` **không đảm bảo capacity bằng chính xác 20**, chỉ đảm bảo **ít nhất 20** khi thành công.
5. `ensureCapacity(20)` hoàn toàn **không đồng nghĩa** `setLength(20)`.

## 6. setLength(): thay đổi độ dài nội dung

`setLength(int newLength)` đặt **length mới** cho builder, khác với `ensureCapacity()`:

- Nếu `newLength < length()`, nội dung bị **cắt ngắn từ cuối**.
- Nếu `newLength == length()`, độ dài giữ nguyên.
- Nếu `newLength > length()`, các vị trí mới được thêm vào nội dung với giá trị ký tự **NUL, `'\u0000'`**, không phải dấu cách.
- Nếu length mới vượt capacity, builder có thể tự nới dung lượng.
- Nếu `newLength < 0`, phương thức ném `IndexOutOfBoundsException`.

Ví dụ:

~~~java
StringBuilder sb = new StringBuilder(8);
sb.append("Cat");
sb.setLength(5);

System.out.println(sb.length());        // 5
System.out.println(sb.capacity());      // 8
System.out.println((int) sb.charAt(3)); // 0
System.out.println((int) sb.charAt(4)); // 0

sb.setLength(2);
System.out.println(sb.toString());      // Ca
System.out.println(sb.length());        // 2
System.out.println(sb.capacity());      // 8
~~~

Đây là **đoạn mã minh họa đặt trong phương thức**. Hai phần tử mới đã thuộc nội dung sau `setLength(5)`, nhưng chúng là NUL và có thể không nhìn thấy khi in trực tiếp. Đừng dùng `setLength()` chỉ để “đặt trước chỗ trống” nếu bạn không muốn thêm ký tự thực vào chuỗi.

### Xóa nội dung bằng setLength(0)

~~~java
StringBuilder sb = new StringBuilder(32);
sb.append("first");
sb.setLength(0);
sb.append("second");
System.out.println(sb.toString()); // second
~~~

`setLength(0)` làm builder rỗng về mặt **nội dung logic**, có thể tái sử dụng capacity đã cấp phát trong các vòng lặp tuần tự. Lệnh này không phải biện pháp xóa an toàn dữ liệu nhạy cảm khỏi bộ nhớ JVM; không thể suy diễn từ length rằng dữ liệu cũ đã được ghi đè ở tầng lưu trữ.

**Cảnh báo Unicode:** vì length đếm UTF-16 code unit, cắt bằng `setLength()` ở giữa một surrogate pair có thể để lại surrogate lẻ; khi cần cắt theo Unicode code point hoặc ký tự hiển thị, phải tìm ranh giới phù hợp trước.

## 7. trimToSize(): đề nghị thu gọn chỗ dư

`trimToSize()` yêu cầu builder cố gắng giảm vùng dự trữ nếu có thể. Nó **không** thay đổi nội dung hoặc length.

~~~java
StringBuilder sb = new StringBuilder(100);
sb.append("Java");

System.out.println(sb.length());   // 4
System.out.println(sb.capacity()); // 100

sb.trimToSize();

System.out.println(sb.length());   // 4
System.out.println(sb.capacity() >= sb.length()); // true
System.out.println(sb.toString()); // Java
~~~

**Không được giả định** `sb.capacity() == 4` sau `trimToSize()`. API cho phép triển khai không giảm dung lượng hoặc giảm nhưng không về đúng length. Vì vậy `trimToSize()` không phù hợp để viết test dựa trên mức tiết kiệm bộ nhớ chính xác. Thu gọn rồi lại append nhiều có thể phát sinh cấp phát mới, nên dùng khi có cơ sở về vòng đời builder.

| Phương thức | Đổi length? | Có thể đổi capacity? | Tác động đến nội dung |
| --- | --- | --- | --- |
| `append(...)` | Có thể tăng | Có thể tăng | Nối phần mới |
| `insert(...)` | Có thể tăng | Có thể tăng | Chèn phần mới |
| `delete(...)` | Giảm nếu xóa không rỗng | Không cần giảm | Xóa phần |
| `ensureCapacity(n)` | **Không** | Có thể tăng | Giữ nguyên |
| `setLength(n)` | **Có** nếu khác length cũ | Có thể tăng | Cắt hoặc thêm NUL |
| `trimToSize()` | **Không** | Có thể giảm | Giữ nguyên |
| `toString()` | **Không** | Không làm đổi builder | Trả về `String` kết quả |

## 8. UTF-16: length và capacity không phải số code point

Với Unicode, một code point ngoài BMP như emoji `😀` chiếm hai đơn vị UTF-16:

~~~java
StringBuilder emoji = new StringBuilder("A😀");
System.out.println(emoji.length()); // 3
System.out.println(emoji.codePointCount(0, emoji.length())); // 2
System.out.println(emoji.capacity()); // 19
~~~

Chuỗi `"A😀"` có **2 Unicode code point** nhưng dài **3 UTF-16 code unit**: một cho A và hai cho emoji. Constructor từ `String` khởi tạo capacity = `3 + 16 = 19`. Vì thế:

- Không hiểu `length()` là số “chữ” mà người dùng thấy.
- Không tính capacity theo số byte của tệp UTF-8.
- Không coi capacity là số byte RAM; cách lưu trữ nội bộ và overhead đối tượng phụ thuộc JVM.
- Nếu cần đếm code point, có thể dùng `codePointCount(0, length())`; nếu muốn thêm nguyên code point, có `appendCodePoint(int)`.

Một grapheme cluster hiển thị thậm chí có thể gồm **nhiều code point** (chữ + dấu kết hợp, emoji ghép). Nếu ứng dụng giới hạn độ dài trên UI, phải chọn đơn vị đo theo yêu cầu thay vì mặc định là length hoặc capacity.

## 9. Chương trình Java 17+ đầy đủ

Lưu đoạn mã này vào tệp **StringBuilderCapacityDemo.java**:

~~~java
public class StringBuilderCapacityDemo {
    public static void main(String[] args) {
        StringBuilder empty = new StringBuilder();
        StringBuilder reserved = new StringBuilder(5);
        StringBuilder fromString = new StringBuilder("Java");
        StringBuilder fromSequence = new StringBuilder(
                (CharSequence) "ABC");

        System.out.println("empty length/capacity = "
                + empty.length() + "/" + empty.capacity());
        System.out.println("reserved length/capacity = "
                + reserved.length() + "/" + reserved.capacity());
        System.out.println("String length/capacity = "
                + fromString.length() + "/" + fromString.capacity());
        System.out.println("CharSequence length/capacity = "
                + fromSequence.length() + "/" + fromSequence.capacity());

        reserved.append("Hi");
        System.out.println("after append length/capacity = "
                + reserved.length() + "/" + reserved.capacity());

        StringBuilder grown = new StringBuilder(3);
        grown.ensureCapacity(20);
        System.out.println("ensure length = " + grown.length());
        System.out.println("ensure capacity >= 20 = "
                + (grown.capacity() >= 20));

        grown.append("ABCDE");
        System.out.println("append length = " + grown.length());
        grown.setLength(7);
        System.out.println("extended length = " + grown.length());
        System.out.println("added char code = " + (int) grown.charAt(5));

        grown.setLength(2);
        System.out.println("shrunk content = " + grown);
        System.out.println("shrunk capacity >= 20 = "
                + (grown.capacity() >= 20));

        StringBuilder emoji = new StringBuilder("A😀");
        System.out.println("emoji UTF-16 length = " + emoji.length());
        System.out.println("emoji code points = "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("emoji initial capacity = "
                + emoji.capacity());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 StringBuilderCapacityDemo.java
java StringBuilderCapacityDemo
~~~

**Kết quả stdout:**

~~~text
empty length/capacity = 0/16
reserved length/capacity = 0/5
String length/capacity = 4/20
CharSequence length/capacity = 3/19
after append length/capacity = 2/5
ensure length = 0
ensure capacity >= 20 = true
append length = 5
extended length = 7
added char code = 0
shrunk content = AB
shrunk capacity >= 20 = true
emoji UTF-16 length = 3
emoji code points = 2
emoji initial capacity = 19
~~~

**Phân tích:** Hai constructor không có nội dung đều cho length 0 nhưng capacity khác nhau. Constructor nhận văn bản có length bằng chiều dài văn bản và capacity cộng thêm 16. `ensureCapacity(20)` không thêm ký tự; `append()` tăng length; `setLength(7)` bổ sung NUL; `setLength(2)` cắt nội dung còn `AB`. Emoji cho thấy API đo theo UTF-16. Chương trình kiểm tra dấu `>=` ở nơi không nên hứa một capacity chính xác sau khi builder tự tăng.

## 10. Lỗi phổ biến cần tránh

| Cách hiểu/cách làm sai | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `new StringBuilder(100)` tạo 100 dấu cách | Đối số là capacity, builder vẫn rỗng | Sử dụng `append` nếu muốn tạo nội dung |
| `capacity()` là số ký tự đã được ghi | Capacity là chỗ dự trữ, không phải length | Lấy `length()` cho nội dung |
| Có capacity dư thì `charAt(length())` hợp lệ | Chỉ số được giới hạn bởi length | `0 <= index < length()` |
| `ensureCapacity(n)` đặt length thành n | Nó chỉ dự trữ | Dùng `setLength(n)` khi thật sự cần thay đổi nội dung |
| `setLength(n)` chỉ cấp phát mà không thêm ký tự | Nếu n tăng, ký tự NUL được thêm | Dùng `ensureCapacity(n)` để dự trữ |
| `setLength(0)` chắc chắn giải phóng bộ nhớ | Length về 0 nhưng capacity có thể giữ nguyên | Không dùng length để suy diễn RAM |
| `trimToSize()` luôn đặt capacity bằng length | API không hứa thu gọn đến mức chính xác | Không kiểm thử bằng giá trị tuyệt đối sau khi trim |
| Đoán công thức mở rộng capacity để tính logic | Chi tiết tăng trưởng/triển khai có thể thay đổi | Dựa vào các điều kiện tối thiểu của API |
| `new StringBuilder(-1)` hợp lệ | Capacity âm không hợp lệ | Kiểm tra tham số |
| `new StringBuilder(10)` và `new StringBuilder("10")` giống nhau | Một bên chọn chỗ dự trữ, bên kia chọn nội dung | Chọn đúng overload |
| `length()` bằng số emoji | Emoji ngoài BMP có hai code unit | Dùng code point API theo yêu cầu |
| Capacity 100 nghĩa là 200 byte RAM | Cấu trúc nội bộ JVM không được mô tả bởi capacity | Không dùng capacity như trình đo RAM |
| Dùng chung builder giữa nhiều luồng không khóa | `StringBuilder` không đồng bộ mặc định | Giới hạn quyền truy cập/đồng bộ phù hợp |

## 11. Checklist thực hành

1. **Đầu vào là nội dung hay dung lượng ước tính?** Nếu là nội dung, dùng constructor nhận `String`/`CharSequence`; nếu chỉ dự trữ, dùng constructor nhận `int`.
2. **Đếm theo đơn vị nào?** Capacity và length đều tính theo UTF-16 code unit, không phải byte UTF-8 hay code point.
3. **Có cần tối ưu số lần nới capacity?** Chọn giá trị ban đầu hoặc `ensureCapacity()` dựa trên ước lượng hợp lý, không vượt nhu cầu quá lớn.
4. **Đã phân biệt ensureCapacity và setLength?** Một thao tác chỉ dự trữ; thao tác kia thay đổi chính nội dung, có thể thêm NUL.
5. **Có kiểm tra ngoại lệ?** Tránh capacity âm, vùng nhớ cực lớn, chỉ số ngoài `length()`.
6. **Có phụ thuộc vào capacity chính xác sau append/trim?** Nếu có, nên xem xét lại; tốt hơn chỉ kiểm tra các bảo đảm thực sự của API.
7. **Có dữ liệu Unicode không?** Tránh hiểu length/capacity là số ký tự người dùng nhìn thấy.
8. **Có dùng chung giữa các luồng không?** Đảm bảo chính sách đồng bộ thích hợp hoặc dùng builder cục bộ.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `StringBuilder b = new StringBuilder(4); b.append("ab");` thì `length()` và `capacity()` bằng bao nhiêu?

**Đáp án:** length = 2, capacity = 4.

**Câu 2.** `new StringBuilder("abc")` có length và capacity ban đầu bao nhiêu?

**Đáp án:** length = 3 và capacity = 19, vì constructor từ `String` dùng `str.length() + 16`.

**Câu 3.** Sau `StringBuilder b = new StringBuilder(8); b.ensureCapacity(50);`, các giá trị nào phải đúng khi lời gọi thành công?

**Đáp án:** `b.length() == 0` và `b.capacity() >= 50`. Không cần `capacity() == 50`.

**Câu 4.** Khi `b = new StringBuilder("AB"); b.setLength(4);`, hai vị trí được thêm có gì?

**Đáp án:** hai ký tự NUL `'\u0000'`, không phải dấu cách. Chúng có trong nội dung logic.

**Câu 5.** `new StringBuilder("😀")` có length bao nhiêu và capacity ban đầu bao nhiêu?

**Đáp án:** length = 2 UTF-16 code unit; capacity = 18.

**Câu 6.** Vì sao không nên kiểm tra `b.capacity() == b.length()` sau `trimToSize()`?

**Đáp án:** API cho phép trim không giảm dung lượng hoặc không giảm đến đúng length. Nội dung không bị đổi dù capacity có giảm hay không.

**Câu 7.** Trong một vòng lặp nhiều lần tạo chuỗi, khi nào nên dùng `new StringBuilder(estimated)`?

**Đáp án:** khi có ước lượng số UTF-16 code unit tương đối đáng tin cậy và việc dự trữ trước mang lại lợi ích thực tế. Cần tránh ước lượng quá lớn làm lãng phí bộ nhớ.

## Tài liệu tham khảo

- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): constructor, `length()`, `capacity()`, `ensureCapacity()`, `setLength()`, `trimToSize()` và các phương thức thay đổi nội dung.
- [Java SE 17 — CharSequence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html): giao diện nguồn đầu vào của constructor nhận `CharSequence`.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): kiểu chuỗi bất biến, độ dài theo UTF-16 và các thao tác code point.
