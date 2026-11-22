# Mismatch trên các buffer ký tự, kiểu số (Java 11+)

## Mục tiêu

Trong nhóm kiến thức **Buffer và nén**, đôi khi ta cần so sánh hai vùng dữ liệu đã được nạp vào `java.nio`: ký tự sau khi giải mã, một dãy số đo, tọa độ, mẫu tín hiệu, hoặc các byte đầu vào/đầu ra của một bước nén. Nếu chỉ cần biết **phần tử đầu tiên khác nhau nằm ở đâu**, Java 11 bổ sung phương thức `mismatch(...)` trực tiếp lên các buffer nguyên thủy.

Sau bài này, bạn có thể:

- Giải thích chính xác ý nghĩa của `bufferA.mismatch(bufferB)` và các giá trị trả về: `-1`, chỉ số khác nhau, hoặc độ dài tiền tố chung.
- Phân biệt **chỉ số tương đối với `position`** và chỉ số tuyệt đối trong buffer.
- Dùng `CharBuffer` và các buffer số `ShortBuffer`, `IntBuffer`, `LongBuffer`, `FloatBuffer`, `DoubleBuffer`; biết `ByteBuffer` cũng có API tương ứng.
- Xử lý đúng vùng `position..limit`, trường hợp một buffer là tiền tố của buffer kia, `NaN`, dấu âm/dương của số 0 và ký tự Unicode.
- Chọn đúng loại buffer theo dữ liệu cần so sánh, đặc biệt khi dữ liệu xuất phát từ định dạng nhị phân hoặc nén.

**Phiên bản:** các phương thức `mismatch` của buffer dưới đây xuất hiện từ **Java 11** và tiếp tục được hỗ trợ trong JDK hiện đại. Ví dụ sử dụng API Java 11, có thể chạy trên các phiên bản Java mới tương thích.

## 1. Những lớp nào có `mismatch`?

Các kiểu buffer trong `java.nio` làm việc với phần tử nguyên thủy khác nhau:

| Kiểu buffer | Mỗi phần tử là | Phương thức | Đơn vị chỉ số trả về |
| --- | --- | --- | --- |
| `ByteBuffer` | `byte` | `mismatch(ByteBuffer that)` | Byte |
| `CharBuffer` | `char` | `mismatch(CharBuffer that)` | Đơn vị UTF-16 (`char`) |
| `ShortBuffer` | `short` | `mismatch(ShortBuffer that)` | Phần tử `short` |
| `IntBuffer` | `int` | `mismatch(IntBuffer that)` | Phần tử `int` |
| `LongBuffer` | `long` | `mismatch(LongBuffer that)` | Phần tử `long` |
| `FloatBuffer` | `float` | `mismatch(FloatBuffer that)` | Phần tử `float` |
| `DoubleBuffer` | `double` | `mismatch(DoubleBuffer that)` | Phần tử `double` |

Cú pháp cơ bản:

```java
int index = first.mismatch(second);
```

Đây là **đoạn minh họa**, cần `first` và `second` là hai buffer **cùng kiểu**. Ví dụ `CharBuffer.mismatch(CharBuffer)` nhận một `CharBuffer`, không nhận trực tiếp `IntBuffer`. Lớp cơ sở `Buffer` không cung cấp một phương thức `mismatch(Buffer)` dùng chung cho mọi kiểu.

Các kiểu buffer lưu trữ các dãy phần tử nguyên thủy; dùng `mismatch` để so sánh **nội dung logic của phần còn lại** mà không cần tự viết vòng lặp so sánh từng phần tử.

## 2. Hợp đồng của `mismatch`: so sánh phần còn lại

Mỗi buffer có:

- `capacity()`: sức chứa tối đa của buffer, tính theo phần tử của loại buffer.
- `position()`: vị trí bắt đầu của phần đang đọc hoặc ghi tiếp.
- `limit()`: biên **không bao gồm** ở cuối vùng có thể truy cập theo trạng thái hiện tại.
- `remaining()`: số phần tử từ `position` tới trước `limit`, bằng `limit - position`.

Với hai buffer `a` và `b`, `a.mismatch(b)` chỉ xem các dãy:

```text
a[position(a) .. limit(a) - 1]
b[position(b) .. limit(b) - 1]
```

**Hai dãy được so từ phần tử đầu tiên của vùng còn lại, kể cả khi position của chúng khác nhau.** Chỉ số kết quả là số phần tử tính từ **position riêng của mỗi buffer**.

### Ba trường hợp trả về

| Trạng thái so sánh | Giá trị trả về |
| --- | --- |
| Hai dãy còn lại dài bằng nhau và từng phần tử tương đương | `-1` |
| Phần tử đầu tiên khác nhau tại vị trí tương đối `i`, trước khi dãy nào kết thúc | `i`, bắt đầu từ `0` |
| Mọi phần tử của dãy ngắn hơn đều giống tiền tố dãy dài hơn, nhưng độ dài khác nhau | `min(a.remaining(), b.remaining())` |

Nếu hai dãy cùng rỗng, kết quả là `-1`. Nếu một dãy rỗng và dãy còn lại không rỗng, kết quả là `0`: đây là **khác độ dài**, không phải “phần tử tại chỉ số 0 của dãy rỗng bị sai”.

Có thể tự hình dung:

```text
a remaining: [10, 20, 30]
b remaining: [10, 20, 31]
relative:      0   1   2
mismatch = 2

a remaining: [10, 20]
b remaining: [10, 20, 31]
relative:      0   1  [kết thúc a]
mismatch = 2

a remaining: [10, 20]
b remaining: [10, 20]
mismatch = -1
```

Điểm quan trọng: chỉ số trả về **không đương nhiên là chỉ số tuyệt đối trong mảng**, và trong trường hợp tiền tố, nó **không thể dùng để đọc phần tử của dãy ngắn hơn**.

### Cách lấy phần tử gây khác biệt một cách an toàn

Giả sử `a` và `b` là hai `IntBuffer`:

```java
int diff = a.mismatch(b);
if (diff == -1) {
    System.out.println("Equal remaining sequences");
} else if (diff < a.remaining() && diff < b.remaining()) {
    int leftValue = a.get(a.position() + diff);
    int rightValue = b.get(b.position() + diff);
    System.out.println(leftValue + " vs " + rightValue);
} else {
    System.out.println("One remaining sequence is a proper prefix");
}
```

Đây là **đoạn minh họa** sử dụng hai biến `IntBuffer a`, `IntBuffer b` đã có. `get(int)` là phương thức đọc **tuyệt đối**, không dịch `position`. Chỉ đọc theo cách này nếu `diff` nằm trong cả hai vùng còn lại. Đoạn code giả định buffer không bị thay đổi đồng thời giữa phép so sánh và phép đọc.

## 3. Ví dụ hoàn chỉnh cho ký tự và các kiểu số

Chương trình dưới đây thể hiện:

- `CharBuffer`: tìm ký tự đầu tiên khác nhau trong hai vùng bắt đầu ở `position = 4`.
- `IntBuffer`: tìm khác biệt giữa hai dãy số khi bỏ qua phần tử đầu.
- `ShortBuffer`: trả chỉ số tiền tố khi hai vùng dài ngắn khác nhau.
- `FloatBuffer` và `DoubleBuffer`: cách so sánh đặc biệt đối với `NaN` và `+0.0/-0.0`.
- `LongBuffer` và `ByteBuffer`: cùng nguyên tắc trên các kiểu phần tử tương ứng.
- `CharBuffer` với emoji: chỉ số đếm theo **UTF-16**, không theo Unicode code point.

**Tệp: `BufferMismatchDemo.java`** — Java 11+

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.DoubleBuffer;
import java.nio.FloatBuffer;
import java.nio.IntBuffer;
import java.nio.LongBuffer;
import java.nio.ShortBuffer;

public class BufferMismatchDemo {
    public static void main(String[] args) {
        CharBuffer charsA = CharBuffer.wrap("key:abc");
        CharBuffer charsB = CharBuffer.wrap("tag:abd");
        charsA.position(4);
        charsB.position(4);
        int diff = charsA.mismatch(charsB);
        System.out.println("char mismatch=" + diff);
        System.out.println("char values=" +
                charsA.get(charsA.position() + diff) + "/" +
                charsB.get(charsB.position() + diff));
        System.out.println("positions=" +
                charsA.position() + "," + charsB.position());

        IntBuffer intsA = IntBuffer.wrap(new int[] {99, 10, 20, 30});
        IntBuffer intsB = IntBuffer.wrap(new int[] {88, 10, 20, 31});
        intsA.position(1);
        intsB.position(1);
        System.out.println("int mismatch=" + intsA.mismatch(intsB));

        ShortBuffer shortsA = ShortBuffer.wrap(new short[] {1, 2});
        ShortBuffer shortsB = ShortBuffer.wrap(new short[] {1, 2, 3});
        System.out.println("short prefix=" + shortsA.mismatch(shortsB));

        FloatBuffer floatsA =
                FloatBuffer.wrap(new float[] {Float.NaN, +0.0f});
        FloatBuffer floatsB =
                FloatBuffer.wrap(new float[] {Float.NaN, -0.0f});
        System.out.println("float equal=" + floatsA.mismatch(floatsB));

        DoubleBuffer doublesA =
                DoubleBuffer.wrap(new double[] {Double.NaN, +0.0d});
        DoubleBuffer doublesB =
                DoubleBuffer.wrap(new double[] {Double.NaN, -0.0d});
        System.out.println("double equal=" + doublesA.mismatch(doublesB));

        LongBuffer longsA = LongBuffer.wrap(new long[] {4L, 5L});
        LongBuffer longsB = LongBuffer.wrap(new long[] {4L, 6L});
        System.out.println("long mismatch=" + longsA.mismatch(longsB));

        ByteBuffer bytesA = ByteBuffer.wrap(new byte[] {1, 2, 3});
        ByteBuffer bytesB = ByteBuffer.wrap(new byte[] {1, 2, 3});
        System.out.println("bytes equal=" + bytesA.mismatch(bytesB));

        CharBuffer emojiA = CharBuffer.wrap("a🙂b");
        CharBuffer emojiB = CharBuffer.wrap("a🙂c");
        System.out.println("emoji char mismatch=" +
                emojiA.mismatch(emojiB));
    }
}
```

Biên dịch/chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 BufferMismatchDemo.java
java BufferMismatchDemo
```

Nếu muốn kiểm tra khả năng tương thích Java 11 khi đang dùng JDK mới hơn có hỗ trợ target 11:

```bash
javac --release 11 -encoding UTF-8 BufferMismatchDemo.java
java BufferMismatchDemo
```

**Stdout chính xác:**

```text
char mismatch=2
char values=c/d
positions=4,4
int mismatch=2
short prefix=2
float equal=-1
double equal=-1
long mismatch=1
bytes equal=-1
emoji char mismatch=3
```

Ví dụ đã được **biên dịch thực tế với `javac --release 11 -encoding UTF-8`** và chạy để kiểm tra từng dòng kết quả.

### Diễn giải từng trường hợp

1. `charsA` và `charsB` có tiền tố bốn ký tự khác nhau, nhưng cả hai đều đặt `position(4)`. Vùng được so là `"abc"` và `"abd"`, vì vậy ký tự đầu tiên khác nhau có **chỉ số tương đối 2**. Phương thức `get(position + 2)` đọc được `c` và `d`.
2. Sau `mismatch`, `position` của hai `CharBuffer` vẫn là `4`. Phép so sánh **không tiêu thụ** các phần tử của buffer như `get()` tương đối.
3. Hai `IntBuffer` bỏ qua các phần tử ban đầu `99` và `88` bằng `position(1)`; dãy còn lại là `[10, 20, 30]` và `[10, 20, 31]`, khác ở chỉ số tương đối `2`.
4. `[1, 2]` là tiền tố của `[1, 2, 3]`. `shortsA.mismatch(shortsB)` trả `2` vì độ dài còn lại khác nhau, dù **không có phần tử `shortsA[2]`** để đọc.
5. `FloatBuffer` và `DoubleBuffer` xem hai giá trị `NaN` là tương đương, đồng thời xem `+0.0` và `-0.0` là tương đương trong so sánh buffer. Vì vậy hai ví dụ trả `-1`.
6. `LongBuffer` khác ở phần tử tương đối `1`, còn hai `ByteBuffer` có toàn bộ phần tử bằng nhau nên trả `-1`.
7. Chuỗi `"a🙂b"` gồm `a` tại chỉ số UTF-16 `0`, emoji chiếm **hai** vị trí `1, 2`, rồi `b` ở `3`. Thay `b` bằng `c` nên `CharBuffer.mismatch` trả **3**.

## 4. Đừng nhầm chỉ số của `mismatch` với `position/limit/capacity`

Giả sử dữ liệu trông như:

```text
Buffer A:
index tuyệt đối:  0   1   2   3   4
data:           [ 9, 10, 20, 30, 99 ]
position = 1, limit = 4
vùng so sánh:       [10, 20, 30]

Buffer B:
index tuyệt đối:  0   1   2   3
data:           [ 8, 10, 20, 31 ]
position = 1, limit = 4
vùng so sánh:       [10, 20, 31]

mismatch = 2
chỉ số tuyệt đối ở mỗi buffer = position + 2 = 3
```

Các phần tử sau `limit` không tham gia so sánh, dù nằm trong capacity. Chẳng hạn, phần tử `99` ở Buffer A không ảnh hưởng vì `limit = 4`.

**Lưu ý khi dựng buffer:**

- `wrap(array)`: thường có `position = 0`, `limit = array.length`.
- `wrap(array, offset, length)`: đặt `position = offset`, `limit = offset + length`. Nó không tự tạo một buffer có `position = 0` và dãy chỉ gồm phần cắt.
- `slice()`: tạo một view của vùng còn lại với `position = 0`, `limit` bằng số phần tử còn lại; chia sẻ dữ liệu nền với buffer gốc nhưng có position/limit riêng.
- `duplicate()`: tạo view chia sẻ nội dung nền nhưng có position/limit/mark độc lập.
- `asReadOnlyBuffer()`: đọc được và so sánh được bằng `mismatch`, nhưng không `put(...)` qua view đó.

Nếu buffer vừa được ghi bằng `put(...)`, hãy nhớ chuyển trạng thái thích hợp trước khi đọc/so sánh, thường bằng `flip()`. Không gọi `clear()` như một thao tác xóa dữ liệu: `clear()` chỉ đặt lại position/limit để chuẩn bị dùng buffer và có thể khiến vùng chứa dữ liệu cũ được xem là “còn lại”.

### Ví dụ thực tế với `flip`

```java
CharBuffer first = CharBuffer.allocate(6);
first.put("ABC");
first.flip(); // position = 0, limit = 3

CharBuffer second = CharBuffer.wrap("ABD");
int index = first.mismatch(second); // 2
```

Đoạn này minh họa trong ngữ cảnh đã import `java.nio.CharBuffer`. Nếu quên `flip()`, buffer `first` có `position = 3` và `limit = 6`; phép so sánh sẽ xét vùng khác với ba ký tự vừa ghi, dẫn đến kết quả sai ý định.

## 5. Buffer ký tự khác gì so với buffer số?

### `CharBuffer` so sánh `char`, không tự hiểu Unicode ở cấp ký tự người dùng

`CharBuffer` biểu diễn các đơn vị UTF-16. Vì thế:

- So sánh **phân biệt hoa/thường**; `'A'` và `'a'` khác nhau.
- Không tự chuẩn hóa Unicode: hai chuỗi hiển thị giống nhau có thể có các chuỗi code point khác nhau.
- Ký tự ngoài BMP (ví dụ nhiều emoji) thường gồm **hai đơn vị `char`** (surrogate pair), nên vị trí mismatch có thể khác vị trí đếm bằng Unicode code point hoặc grapheme cluster.
- Nó không tự giải mã UTF-8: trước khi so sánh ký tự trong bytes, phải dùng bộ giải mã đúng `Charset`, ví dụ `StandardCharsets.UTF_8`.

Nếu cần so sánh theo **Unicode code point**, có thể đổi sang dãy `int` trước khi dùng `IntBuffer`:

```java
IntBuffer pointsA =
        IntBuffer.wrap("a🙂b".codePoints().toArray());
IntBuffer pointsB =
        IntBuffer.wrap("a🙂c".codePoints().toArray());

System.out.println(pointsA.mismatch(pointsB)); // 2
```

Đây là đoạn minh họa cần `import java.nio.IntBuffer;`. Tại cấp code point, `a` là vị trí `0`, `🙂` là vị trí `1`, `b/c` là vị trí `2`. Tuy nhiên code point cũng không đồng nghĩa grapheme cluster và không tự thực hiện Unicode normalization.

### `ShortBuffer`, `IntBuffer`, `LongBuffer`

Các buffer số nguyên so sánh **giá trị phần tử cùng kiểu**. Chỉ số mismatch được tính bằng số phần tử nguyên thủy, không phải số byte. Ví dụ một `IntBuffer` có mismatch tại `2` nghĩa là phần tử `int` thứ ba trong vùng còn lại khác nhau; không được suy ra “byte thứ ba khác”.

Khi dữ liệu gốc là chuỗi byte của một định dạng nhị phân, phải biết **endianness (byte order)** và cách giải mã byte thành số trước khi so sánh giá trị. Nếu tạo numeric view của `ByteBuffer`, `ByteOrder` có thể làm thay đổi giá trị số đọc được từ cùng một dãy byte. Chỉ dùng `mismatch` sau khi đã xác định hai dãy mang cùng ý nghĩa kiểu dữ liệu.

### `FloatBuffer`, `DoubleBuffer`: trường hợp đặc biệt

Phép so sánh phần tử của `FloatBuffer.mismatch` và `DoubleBuffer.mismatch` tương thích với quy ước so sánh của các buffer dấu phẩy động:

- Hai giá trị `NaN` được xem là **tương đương** cho mục đích mismatch, kể cả khi biểu diễn bit nội bộ khác nhau.
- `+0.0` và `-0.0` được xem là **tương đương**.
- Những giá trị số thông thường khác nhau vẫn được phát hiện tại phần tử đầu tiên khác.

**Đừng dùng `mismatch` trên float/double để xác nhận hai chuỗi bit giống hệt.** Khi cần kiểm tra byte-for-byte trong định dạng nhị phân, hãy so sánh phần byte của định dạng đó (ví dụ `ByteBuffer` với cùng vùng dữ liệu) hoặc kiểm tra biểu diễn bit theo hợp đồng định dạng. Nếu cần phân biệt payload của `NaN`, cách đọc `Float.floatToRawIntBits`/`Double.doubleToRawLongBits` có thể hữu ích trong thuật toán chuyên biệt; các hàm chuyển đổi bit cũng phải được áp dụng có chủ đích theo đúng representation.

Nếu ứng dụng có yêu cầu *so sánh gần đúng* số thực với sai số, `mismatch` không thay thế phép kiểm tra dung sai, chẳng hạn kiểm tra `Math.abs(a - b) <= epsilon` theo quy tắc nghiệp vụ và cách xử lý `NaN`/vô cực đã định trước.

## 6. So với `equals`, `compareTo` và `Arrays.mismatch`

| Phương thức | Câu hỏi trả lời | Kết quả |
| --- | --- | --- |
| `a.mismatch(b)` | “Phần tử đầu tiên khác ở đâu trong vùng còn lại?” | Chỉ số tương đối, hoặc `-1` |
| `a.equals(b)` | “Hai dãy phần tử còn lại tương đương hay không?” | `boolean` |
| `a.compareTo(b)` | “Hai dãy phần tử còn lại có thứ tự từ điển thế nào?” | Số âm, 0 hoặc dương |
| `Arrays.mismatch(arrayA, arrayB)` | “Hai **mảng** khác nhau từ vị trí nào?” | Chỉ số trên mảng (hoặc phần dãy đã chọn theo overload), hoặc `-1` |

Với **hai buffer cùng kiểu và ổn định trong khi so sánh**, `a.mismatch(b) == -1` có nghĩa hai dãy **remaining** tương đương, phù hợp logic `a.equals(b)`. `compareTo` có mục đích khác, không trả vị trí khác nhau.

`Arrays.mismatch` làm việc trên mảng và overload phạm vi mảng; nó **không tự biết `position/limit` của buffer**. Để so sánh dữ liệu đã ở `CharBuffer`/`IntBuffer`, dùng phương thức buffer giúp tránh tự chuyển toàn bộ sang mảng và vẫn tôn trọng vùng còn lại.

## 7. Ứng dụng với dữ liệu nén và so sánh các khối

Dữ liệu nén thường xuất hiện trước hoặc sau một bước chuyển đổi giữa byte, ký tự và kiểu số:

1. **Cần biết hai chuỗi byte nén có giống hệt về nội dung bytes không:** dùng `ByteBuffer.mismatch` trên vùng byte cần kiểm tra. Kết quả là vị trí **byte tương đối**; hai bản nén khác bytes vẫn có thể giải nén thành nội dung giống nhau, tùy định dạng và metadata.
2. **Cần so sánh văn bản sau giải nén:** giải nén theo định dạng, giải mã bằng charset đúng, rồi so sánh `CharBuffer` hoặc cấp Unicode thích hợp. `CharBuffer.mismatch` không tự giải nén hoặc tự giải mã UTF-8.
3. **Cần so sánh dãy số được khôi phục:** xác định kiểu, endian, độ dài và ranh giới record trước, sau đó so sánh các buffer kiểu số.
4. **Cần phát hiện phần đầu tiên khác nhau giữa hai phần dữ liệu:** `mismatch` trả về vị trí hữu ích để báo chỗ khác biệt. Nó **không xác nhận tính toàn vẹn mật mã** và không thay thế hash/chữ ký số khi đó là yêu cầu bảo mật.

Khi dữ liệu được xử lý theo **nhiều khối**, mỗi lệnh `mismatch` chỉ so sánh vùng remaining của hai buffer ở thời điểm gọi. Muốn xác định offset toàn cục của file/luồng, chương trình phải tự cộng **số phần tử đã xử lý ở các khối trước**, đồng thời bảo đảm cách chia khối không làm sai ranh giới record/đơn vị ký tự.

Không tự tuyên bố byte offset toàn cục chỉ bằng chỉ số của một `CharBuffer` hay `IntBuffer`: index có đơn vị phần tử, còn byte offset phụ thuộc charset/kích thước phần tử và layout dữ liệu.

## 8. Tính đúng, hiệu năng và bộ nhớ

**Ưu điểm:** `mismatch` diễn đạt mục đích rất rõ, trả kết quả đầu tiên mà không cần tự viết vòng lặp, và không cần sao chép toàn bộ dữ liệu sang một collection mới. Khi có thể, triển khai JDK có thể sử dụng phương thức tối ưu theo nền tảng; không nên hứa một mức tăng tốc cố định.

**Độ phức tạp:** về mặt logic, nó kiểm tra đến khác biệt đầu tiên hoặc hết dãy ngắn hơn. Trong trường hợp xấu nhất, lượng dữ liệu phải xem tăng theo `min(a.remaining(), b.remaining())`. Kết quả không chứa toàn bộ danh sách các điểm khác nhau; muốn tìm các điểm tiếp theo phải thiết kế cơ chế duyệt phù hợp.

**Trạng thái:** `mismatch` là phép **so sánh, không tiêu thụ buffer**; position và limit không bị dịch bởi lời gọi. Các view như `slice()`/`duplicate()` dùng position/limit riêng, nhưng có thể chia sẻ dữ liệu bên dưới.

**Song song:** nếu một luồng khác đang ghi vào bộ nhớ dùng chung của buffer trong lúc so sánh, không có lý do để kỳ vọng kết quả là một snapshot nhất quán. Phải đồng bộ hóa hoặc tạo snapshot theo yêu cầu ứng dụng; `mismatch` không tự đảm bảo atomicity cho toàn dãy.

**Bộ nhớ:** buffer trực tiếp (*direct*) và buffer trên heap đều có thể so sánh nếu thuộc kiểu phù hợp. Một buffer read-only vẫn có thể được đọc để so sánh. Không cần sao chép sang mảng chỉ vì muốn `mismatch`, nhưng phải tôn trọng vòng đời dữ liệu khi liên quan tài nguyên ngoài heap/file mapping.

## 9. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Coi chỉ số mismatch là chỉ số tuyệt đối | Đọc sai phần tử khi `position != 0` | Dùng `position() + mismatch`, nếu chỉ số còn hợp lệ |
| Gọi `get(position + diff)` ngay cả khi `diff == remaining()` | Truy cập ngoài vùng của buffer ngắn hơn | Kiểm tra trường hợp tiền tố trước |
| So sánh cả capacity thay vì vùng remaining | Dữ liệu cũ/ngoài giới hạn được đưa vào tính toán | Thiết lập `position/limit` đúng và nhớ `flip()` sau khi ghi |
| Cho rằng `mismatch == 0` nghĩa là “hoàn toàn khác nhau” | Mất ý nghĩa “phần tử đầu tiên khác ngay đầu” hoặc “một dãy rỗng” | Đọc đúng ba nhóm kết quả: `-1`, khác phần tử, khác độ dài |
| Nghĩ `CharBuffer` trả index theo Unicode code point | Sai vị trí với surrogate pair/emoji | Phân biệt UTF-16 `char` và code point |
| Dùng `FloatBuffer.mismatch` để so bit chính xác | Không phân biệt `NaN` và dấu của 0 như dữ liệu raw | So byte/bit theo hợp đồng định dạng nếu cần |
| So sánh `IntBuffer` chưa thống nhất endian | Hai bên có thể giải mã dãy byte thành giá trị khác | Chuẩn hóa byte order và định dạng đầu vào |
| So sánh các buffer khác kiểu trực tiếp | Không khớp chữ ký phương thức | Chuyển về cùng kiểu logic với quy tắc rõ ràng |
| Dùng `mismatch` làm checksum hoặc so sánh hash an toàn | Không giải quyết tính toàn vẹn/bảo mật | Dùng cơ chế xác minh phù hợp yêu cầu |
| Để dữ liệu nền bị thay đổi đồng thời | Kết quả có thể không nhất quán | Đồng bộ hóa hoặc xử lý snapshot ổn định |
| Dùng `Buffer` chung và gọi `mismatch` | Không có `Buffer.mismatch(Buffer)` | Sử dụng kiểu cụ thể như `CharBuffer`, `IntBuffer` |

## 10. Bài tập và kiểm tra hiểu bài

**Bài 1 — Vị trí tương đối.** Xét hai `IntBuffer` chứa `[99, 1, 2, 3]` và `[88, 1, 2, 4]`, đều đặt `position(1)`. Dự đoán mismatch. **Đáp án:** `2`; phần tử khác là `3` và `4` ở chỉ số tuyệt đối `3`.

**Bài 2 — Tiền tố.** Xét `CharBuffer.wrap("cat")` và `CharBuffer.wrap("cater")`, position đều 0. **Đáp án:** `3`, biểu thị dãy ngắn đã hết; không truy cập `get(3)` trên buffer `"cat"`.

**Bài 3 — Trạng thái.** Sau khi `first.put("ABC")` vào `CharBuffer.allocate(8)`, bạn muốn so với `CharBuffer.wrap("ABC")`. Cần làm gì? **Đáp án:** gọi `flip()` trên buffer vừa ghi để đặt position 0, limit 3 rồi mới mismatch.

**Bài 4 — Unicode.** So sánh `"a🙂b"` với `"a🙂c"` bằng `CharBuffer.mismatch` và bằng `IntBuffer.wrap(str.codePoints().toArray()).mismatch(...)`. **Đáp án:** UTF-16 `CharBuffer` trả 3; code point `IntBuffer` trả 2.

**Bài 5 — Số thực.** So sánh `FloatBuffer.wrap(new float[]{Float.NaN, -0.0f})` với buffer chứa `{Float.NaN, +0.0f}`. **Đáp án:** `-1`; nếu cần kiểm tra bit, phải dùng cơ chế riêng.

**Bài 6 — Vùng còn lại.** Tạo hai `LongBuffer` có cùng hai phần tử cuối nhưng các phần tử trước position khác nhau. Kết quả mismatch là gì? **Đáp án:** `-1` nếu **toàn bộ phần tử remaining** của hai bên bằng nhau; nội dung trước position không được so.

### Checklist khi review

Trước khi viết một phép `mismatch`, tự hỏi: (1) Hai buffer có **cùng loại phần tử và cùng ý nghĩa dữ liệu** không? (2) `position/limit` đã xác định đúng vùng muốn so chưa? (3) Nếu nhận index không âm, đó là **khác phần tử** hay **khác độ dài**? (4) Chỉ số đang tính theo byte, UTF-16 hay phần tử số? (5) Với float/double, có yêu cầu bit-exact hay chỉ cần tương đương theo buffer? (6) Có ai đang thay đổi dữ liệu nền trong lúc so sánh không?

## Tài liệu tham khảo chính thức

- [Oracle Java SE 11 — CharBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/CharBuffer.html): `mismatch(CharBuffer)` có từ Java 11, vùng remaining, position và giá trị trả về.
- [Oracle Java SE 11 — IntBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/IntBuffer.html): phương thức `mismatch` và quy tắc so phần tử kiểu `int`.
- [Oracle Java SE 11 — ShortBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ShortBuffer.html), [LongBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/LongBuffer.html): các bộ đệm số nguyên còn lại.
- [Oracle Java SE 11 — FloatBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/FloatBuffer.html), [DoubleBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/DoubleBuffer.html): quy tắc so sánh số thực, NaN và dấu của zero.
- [Oracle Java SE 11 — ByteBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html): so sánh raw bytes trong buffer.
- [Oracle Java SE 25 — java.nio](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/package-summary.html): các buffer và API vẫn hiện diện trong JDK hiện đại.

**Nguyên tắc cốt lõi:** `mismatch` trả lời **“phần tử đầu tiên khác nhau trong hai vùng remaining nằm ở chỉ số tương đối nào?”**. Hiểu đúng **kiểu dữ liệu**, **đơn vị của index** và **ranh giới position/limit** quan trọng hơn việc chỉ nhớ cú pháp một dòng.