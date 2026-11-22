# Đối tượng nguồn khả biến khi `StringBuffer.append()` hoặc `insert()`

## 1. Vấn đề: dữ liệu nguồn có thể thay đổi

`StringBuffer` lưu một dãy ký tự **khả biến** (mutable) và hỗ trợ xây dựng chuỗi bằng `append()`, `insert()`, `delete()`, `replace()`, `setCharAt()` và các phương thức khác. Nhiều overload của `append()` và `insert()` nhận dữ liệu từ một `CharSequence` hoặc một `StringBuffer` khác. Các kiểu nguồn đó có thể thay đổi theo thời gian.

Có hai tình huống cần phân biệt:

1. **Nguồn thay đổi trước hoặc sau mỗi lời gọi:** kết quả chép vào đích dựa trên nội dung nguồn tại thời điểm được đọc. Những ký tự đã chép sang đích là **dữ liệu riêng**, không phải một “liên kết sống” tự đổi theo nguồn.
2. **Nguồn bị sửa đồng thời trong chính lúc đang chép:** đặc biệt khi nguồn là `StringBuilder` hoặc một `CharSequence` tự viết, không được giả định rằng việc lấy `length()` rồi đọc các `charAt()` khác nhau tạo thành một snapshot nguyên tử. Cần phối hợp luồng hoặc tạo snapshot ổn định.

Ví dụ tuần tự, có kết quả xác định:

~~~java
StringBuffer source = new StringBuffer("A");
StringBuffer target = new StringBuffer("Result:");

target.append(source);
source.append("B");
target.append(source);

System.out.println(target); // Result:AAB
System.out.println(source); // AB
~~~

Lần append đầu tiên thêm `"A"`; sau đó nguồn trở thành `"AB"`, nên lần append tiếp theo thêm `"AB"`. Lần đầu **không biến thành** `"AB"` chỉ vì nguồn đã thay đổi. Đây là cơ chế sao chép ký tự, **không phải view dùng chung**.

## 2. Những kiểu dữ liệu và overload liên quan

`StringBuffer` triển khai `CharSequence`, vì vậy nhận nội dung từ nhiều kiểu nguồn:

| Dạng lời gọi | Ý nghĩa |
|---|---|
| `dest.append(String)` | Nối các ký tự của String bất biến vào cuối |
| `dest.append(StringBuffer)` | Nối các ký tự từ StringBuffer nguồn |
| `dest.append(CharSequence)` | Nối toàn bộ dãy ký tự do CharSequence cung cấp |
| `dest.append(CharSequence, start, end)` | Nối phần nằm trong khoảng `[start, end)` của nguồn |
| `dest.insert(offset, String)` | Chèn String vào vị trí `offset` của đích |
| `dest.insert(offset, CharSequence)` | Chèn nội dung CharSequence vào đích |
| `dest.insert(offset, CharSequence, start, end)` | Chèn một đoạn `[start, end)` của nguồn |
| `dest.append(Object)` | Chuyển đối tượng thành chuỗi qua cơ chế `String.valueOf`/`toString()`, rồi nối |

Đây là các dạng lời gọi tiêu biểu, **không phải danh sách tất cả overload** (còn số nguyên, ký tự, boolean, mảng ký tự, v.v.).

`String` **bất biến**; nội dung của nó không đổi sau khi tạo. `StringBuilder` và `StringBuffer` **khả biến**. `CharSequence` chỉ là giao diện biểu diễn dãy ký tự, **không cam kết immutable, không cam kết thread-safe**.

Ví dụ một `StringBuilder` được truyền vào `StringBuffer` dưới kiểu `CharSequence`:

~~~java
StringBuilder source = new StringBuilder("cat");
StringBuffer target = new StringBuffer();

target.append((CharSequence) source); // chép "cat"
source.setCharAt(0, 'b');             // nguồn nay là "bat"
target.insert(0, (CharSequence) source);

System.out.println(source); // bat
System.out.println(target); // batcat
~~~

Kết quả `"batcat"` gồm phần `"bat"` được chèn sau và phần `"cat"` đã chép từ trước. Không có cơ chế đồng bộ hóa giá trị tự động giữa hai builder.

## 3. `append()`: nối phần đọc được từ nguồn vào cuối đích

### 3.1. Nối toàn bộ nội dung nguồn

Khi dùng `append(source)`, đích có thêm nội dung của nguồn. Sau khi lời gọi hoàn thành và không có hoạt động đồng thời gây race, việc sửa nguồn không làm thay đổi đoạn đã được append.

~~~java
StringBuffer source = new StringBuffer("red");
StringBuffer target = new StringBuffer("color=");
target.append(source);
source.replace(0, 3, "blue");

System.out.println(source); // blue
System.out.println(target); // color=red
~~~

Tương tự, sửa `target` sau đó cũng không sửa ngược lại `source`. Hai đối tượng có trạng thái riêng.

**Điểm cần tránh:** không nên suy ra việc `append(source)` tự tạo một đối tượng `String` trung gian cụ thể trong mọi bản JDK. API mô tả **kết quả nội dung**, còn cách tối ưu lưu trữ/copy có thể khác theo triển khai.

### 3.2. Nối một phần nguồn: `start` tính trên nguồn

Với `append(CharSequence s, int start, int end)`, khoảng `[start, end)` lấy theo **chỉ số UTF-16 code unit của nguồn**, đầu bao gồm và cuối không bao gồm.

~~~java
StringBuilder source = new StringBuilder("ABCDEFG");
StringBuffer target = new StringBuffer("part=");
target.append(source, 2, 5);

System.out.println(target); // part=CDE
source.setCharAt(2, 'X');
System.out.println(source); // ABXDEFG
System.out.println(target); // part=CDE
~~~

Ở đây vị trí 2, 3, 4 là `CDE`. Lệnh `setCharAt(2, 'X')` trên nguồn diễn ra **sau khi append** và không thay đổi phần đã copy.

Các ràng buộc chỉ số:

- `start` không được âm.
- `end` không được nhỏ hơn `start`.
- `end` không được lớn hơn độ dài nguồn hợp lệ tại thời điểm áp dụng.
- Nếu phạm vi không hợp lệ, phương thức ném ngoại lệ theo hợp đồng API (ví dụ `IndexOutOfBoundsException`); không được coi là “tự cắt đến hết”.

**Cảnh báo:** nếu nguồn bị thay đổi kích thước giữa việc chương trình xác định `start/end` và lời gọi copy, các chỉ số từng hợp lệ có thể trở thành không hợp lệ. Với nguồn đang bị sửa đồng thời, đừng gọi tách rời `length()`, tính chỉ số, rồi `append(...)` mà không có giao thức đồng bộ.

### 3.3. Lựa chọn overload và ngữ nghĩa

Trong Java, compiler chọn overload dựa trên **kiểu khai báo tại vị trí gọi**. Ví dụ:

~~~java
StringBuffer source = new StringBuffer("X");
CharSequence chars = source;

StringBuffer a = new StringBuffer();
a.append(source); // overload phù hợp cho StringBuffer
a.append(chars);  // overload CharSequence

System.out.println(a); // XX
~~~

Về mục đích, cả hai đều thêm nội dung văn bản. Nhưng không nên dựa vào một sự tối ưu hay mức độ khóa nội bộ đặc thù cho tất cả các overload, mọi bản JDK hoặc mọi loại nguồn `CharSequence`. Khi tính đúng đắn yêu cầu một snapshot có thể giải thích rõ ràng, **chủ động lấy `String` bất biến** ở thời điểm đã đồng bộ.

## 4. `insert()`: nguồn và vị trí chèn có hai hệ tọa độ

`insert()` giống `append()` ở chỗ lấy ký tự từ nguồn, nhưng đặt đoạn đó vào **một vị trí trong đích**, đẩy phần đuôi đích sang phải.

~~~java
StringBuilder source = new StringBuilder("ABCDE");
StringBuffer target = new StringBuffer("[]");

target.insert(1, source, 1, 4);
System.out.println(target); // [BCD]

source.replace(1, 4, "xyz");
System.out.println(source); // AxyzE
System.out.println(target); // [BCD]
~~~

Giải thích các chỉ số:

- `offset=1`: vị trí chèn trong **đích** `"[]"`, nằm giữa `[` và `]`.
- `start=1`, `end=4`: đoạn ký tự nguồn ở chỉ số 1, 2, 3, tức `"BCD"`.
- Kết quả của đích là `"[BCD]"`. Việc sửa nguồn thành `"AxyzE"` sau khi gọi không làm đổi dữ liệu đích.

Ví dụ khác với `insert(offset, source)`:

~~~java
StringBuffer source = new StringBuffer("123");
StringBuffer target = new StringBuffer("AB");
target.insert(1, source);
System.out.println(target); // A123B
source.append("4");
System.out.println(target); // A123B
~~~

Tương tự `append()`, phần `CharSequence` nguồn có thể là mutable, và khi nhiều luồng cùng tác động phải có quy tắc đồng bộ riêng.

Đừng nhầm:

- `offset` là vị trí chèn trong **đích**.
- `start/end` là ranh giới đoạn đọc từ **nguồn**.
- Vị trí `offset` phải hợp lệ trong đích khi thao tác được thực hiện; một offset tính quá sớm cũng có thể không còn hợp lệ nếu luồng khác thay đổi đích.

## 5. Nguồn mutable: snapshot theo thời điểm là gì?

*Snapshot* là biểu diễn ổn định của dữ liệu tại một mốc thời gian được chọn. Trong Java, `String` bất biến là lựa chọn tự nhiên để làm snapshot.

~~~java
StringBuffer source = new StringBuffer("BEFORE");
String snapshot = source.toString(); // String bất biến

source.replace(0, source.length(), "AFTER");

StringBuffer target = new StringBuffer("value=");
target.append(snapshot);

System.out.println(source);   // AFTER
System.out.println(snapshot); // BEFORE
System.out.println(target);   // value=BEFORE
~~~

Khi chương trình muốn **chốt nội dung nguồn trước** rồi thực hiện nhiều thao tác, snapshot giúp mọi thao tác dùng cùng một bản:

~~~java
StringBuffer source = new StringBuffer("CODE");
String stable = source.toString();

StringBuffer a = new StringBuffer("a:");
StringBuffer b = new StringBuffer("b:");
a.append(stable);
b.insert(2, stable);

source.append("-UPDATED");
System.out.println(a); // a:CODE
System.out.println(b); // b:CODE
~~~

Nếu thay `stable` bằng `source` ở cả hai lời gọi, nội dung chép có thể khác nhau khi nguồn bị sửa **giữa hai lời gọi**. Snapshot giải quyết tính nhất quán qua một chuỗi bước, không chỉ một phép copy đơn lẻ.

### Tại sao không dùng `CharSequence` làm “snapshot”?

Một biến kiểu `CharSequence` có thể trỏ vào `StringBuilder`, `StringBuffer`, `CharBuffer` hoặc một triển khai tùy ý. Ví dụ:

~~~java
StringBuilder source = new StringBuilder("old");
CharSequence view = source; // Cùng đối tượng, không có bản sao.

source.replace(0, 3, "new");
System.out.println(view); // new
~~~

Gán `CharSequence view = source` **chỉ gán tham chiếu**, không chốt nội dung. Muốn snapshot bất biến, tạo `String stable = source.toString()` ở điểm được phép đọc an toàn, rồi truyền `stable` vào `append()`/`insert()`.

### `CharBuffer` cũng có trạng thái vùng đọc

Một `java.nio.CharBuffer` là `CharSequence`, nhưng phần nội dung quan sát được có thể chịu ảnh hưởng của `position` và `limit`:

~~~java
import java.nio.CharBuffer;

CharBuffer source = CharBuffer.wrap("ABCDE");
StringBuffer target = new StringBuffer();
target.append(source);
source.position(2);
target.append(source);

System.out.println(target); // ABCDECDE
~~~

Lần thứ nhất append `"ABCDE"`; lần thứ hai append phần còn lại `"CDE"`. Không chỉ ký tự bị sửa mới làm thay đổi một `CharSequence`: **trạng thái vị trí** của một số loại nguồn cũng ảnh hưởng nội dung mà giao diện bộc lộ.

## 6. Đồng thời nhiều luồng: điều gì được bảo đảm?

`StringBuffer` có các thao tác được đồng bộ hóa, khác với `StringBuilder` vốn không có đồng bộ nội bộ. Tuy nhiên, điều này **không có nghĩa mọi quy trình nhiều thao tác trên nguồn và đích là một giao dịch nguyên tử**.

Ví dụ một tiến trình gồm hai bước:

~~~java
// Minh họa thứ tự thao tác, không phải code minh họa race để chạy độc lập.
StringBuffer source = new StringBuffer("A");
StringBuffer target = new StringBuffer();

target.append(source);
source.append("B");
target.append(source);
~~~

Nếu một luồng khác có thể sửa `source` **giữa** hai lần `append`, đích có thể chứa hai phiên bản nguồn khác nhau. Ngay cả khi các phương thức đơn lẻ được đồng bộ hóa, vẫn không có cam kết rằng cả chuỗi bước đọc–sao chép–đọc tự nhiên trở thành một giao dịch.

Đối với `StringBuilder` hoặc `CharSequence` mutable không có đồng bộ, việc **sửa trong lúc** một lời gọi khác đang đọc nhiều ký tự có thể dẫn đến quan sát không nhất quán hoặc ngoại lệ, tùy triển khai. Không dựa vào một thứ tự may mắn của scheduler.

### Cách 1: snapshot của StringBuffer rồi chép

~~~java
StringBuffer source = new StringBuffer("READY");
String snapshot = source.toString();
StringBuffer target = new StringBuffer("state:");
target.append(snapshot);
~~~

Trong API `StringBuffer`, thao tác tạo `String` từ nội dung nguồn dùng cơ chế đồng bộ của đối tượng nguồn. Khi mọi thay đổi nguồn đều đi qua các phương thức `StringBuffer` hợp lệ, `snapshot` trở thành bản bất biến và không bị ảnh hưởng bởi những thay đổi sau đó. Sau khi đã có snapshot, không cần giữ khóa nguồn trong suốt quá trình chép vào đích.

### Cách 2: đồng bộ cả thao tác gồm nhiều bước

Nếu cần **kiểm tra và sử dụng nội dung nhất quán với một điều kiện khác**, hãy dùng một giao thức khóa chung, rõ ràng, cho cả reader lẫn writer:

~~~java
StringBuffer source = new StringBuffer("READY");
String snapshot;
synchronized (source) {
    if (source.length() > 0) {
        snapshot = source.toString();
    } else {
        snapshot = "<empty>";
    }
}
StringBuffer target = new StringBuffer();
target.append(snapshot);
~~~

Ví dụ trên đồng bộ bước kiểm tra length với bước snapshot trên **cùng khóa source**. Tuy vậy, không được suy ra rằng một writer bỏ qua giao thức khóa đó vẫn phối hợp an toàn với reader trên các implementation `CharSequence` bất kỳ.

Nếu phải khóa **hai buffer khác nhau** cùng lúc, cần quy ước thứ tự lấy khóa nhất quán trên toàn ứng dụng để tránh deadlock. Nhiều tác vụ chỉ cần snapshot từng nguồn trước khi sửa đích và tránh giữ đồng thời hai khóa.

### Cách 3: StringBuilder chỉ nên được một luồng sửa, hoặc được bảo vệ

Nếu chỉ một luồng tạo và sửa `StringBuilder`, có thể copy tuần tự mà không cần đồng bộ. Nếu nhiều luồng cùng truy cập, phải dùng đồng bộ ngoài, truyền qua queue/message cho một luồng sở hữu hoặc chốt `String` trước khi giao cho luồng khác. Bản thân `StringBuilder.toString()` không sửa được race với một writer đang thay đổi builder không đồng bộ.

### Quy tắc tổng quát

| Tình huống | Điều nên làm |
|---|---|
| Nguồn `String` bất biến | Dùng trực tiếp |
| `StringBuffer` nguồn chỉ thay đổi tuần tự | Dùng trực tiếp nếu muốn nội dung tại thời điểm gọi |
| Hai lần chép phải cùng một phiên bản | Lấy một `String` snapshot và dùng lại |
| Nguồn `StringBuffer` có nhiều writer | Lấy snapshot dưới cơ chế khóa phù hợp; đồng bộ cả quy trình nếu có invariant nhiều bước |
| Nguồn `StringBuilder` bị sửa song song | Không đọc/copy thiếu phối hợp; dùng khóa chung hoặc bảo đảm một luồng sở hữu |
| `CharSequence` tự viết hoặc view | Kiểm tra hợp đồng thread safety, tính ổn định và vùng ký tự |
| Cần sao chép nguồn đang thay đổi vào đích dùng chung | Chốt nguồn trước rồi gọi API đích trong chiến lược đồng bộ rõ ràng |

## 7. Chèn/nối chính đối tượng đích: trường hợp tự tham chiếu

Khi cả **nguồn lẫn đích là cùng một builder**, việc sửa đích đồng thời cũng làm thay đổi dữ liệu nguồn được đọc. Đây là trường hợp đặc biệt nhạy cảm với thứ tự copy và các overload. Không nên suy diễn rằng mọi lời gọi self-insert với vùng nguồn chồng lấp luôn cho kết quả mong muốn hoặc có cùng hành vi trên mọi API/phiên bản.

Nếu muốn nhân đôi nội dung hiện tại, cách diễn đạt rõ ràng là **chốt một String snapshot trước**:

~~~java
StringBuffer buffer = new StringBuffer("AB");
String original = buffer.toString();
buffer.append(original);
System.out.println(buffer); // ABAB
~~~

Nếu muốn chèn phần đầu của chính buffer vào giữa:

~~~java
StringBuffer buffer = new StringBuffer("WXYZ");
String snapshot = buffer.toString();
buffer.insert(2, snapshot.substring(0, 2));
System.out.println(buffer); // WXWXYZ
~~~

Cách này tránh việc một thay đổi ở đích cũng đồng thời thay đổi nội dung mà tham số nguồn đang bộc lộ. Trường hợp tự tham chiếu, đặc biệt với `insert(..., CharSequence, start, end)`, cần quan tâm đến hợp đồng phiên bản JDK và không đưa các quy tắc xử lý chồng lấp tự suy diễn vào code quan trọng.

## 8. `append(Object)` và thời điểm gọi `toString()`

Không chỉ `CharSequence` mới chứa nội dung có thể đổi. Một đối tượng bất kỳ có thể có `toString()` phụ thuộc trạng thái:

~~~java
class Counter {
    int value;
    @Override public String toString() {
        return "v=" + value;
    }
}

Counter counter = new Counter();
StringBuffer target = new StringBuffer();
target.append((Object) counter);
counter.value = 7;
target.append((Object) counter);
System.out.println(target); // v=0v=7
~~~

Đây là đoạn mã minh họa: đặt `Counter` và phần gọi trong một chương trình hợp lệ. Hai lần chuyển đối tượng sang String được thực hiện tại hai thời điểm khác nhau. Đối tượng đích **không lưu một tham chiếu sống** tới `counter` trong nội dung của `StringBuffer`.

Nếu `toString()` của đối tượng mutable tự đọc nhiều trường trong khi những trường đó bị sửa song song, bản thân việc xây dựng snapshot cũng có thể không nhất quán. Muốn đọc trạng thái đồng bộ phải thiết kế cơ chế riêng, không coi `append(Object)` tự giải quyết concurrency của lớp tùy ý.

## 9. Các lỗi thường gặp khác

### 9.1. Nhầm append với liên kết tham chiếu

~~~java
StringBuilder source = new StringBuilder("A");
StringBuffer target = new StringBuffer();
target.append(source);
source.append("B");
System.out.println(target); // A
~~~

Đích giữ ký tự đã copy, không tự cập nhật thành `"AB"`.

### 9.2. Tưởng `StringBuffer` thread-safe nghĩa là cả workflow atomic

Một cuộc gọi `append()` không tự đồng bộ với các bước kiểm tra, quyết định, chèn, cập nhật sau đó như một giao dịch. Dùng snapshot hoặc khóa đúng phạm vi.

### 9.3. Tính chỉ số từ một trạng thái rồi nguồn thay đổi

~~~java
StringBuilder source = new StringBuilder("ABCDE");
int end = source.length();
source.setLength(2);
// source còn "AB", end=5 đã lỗi thời.
// target.append(source, 0, end) sẽ có phạm vi không hợp lệ.
~~~

Nếu nguồn có thể thay đổi, cần tính `start/end` dựa trên snapshot ổn định hoặc đồng bộ cả quá trình kiểm tra và chép. Không dùng chỉ số đã cũ.

### 9.4. Nhầm `CharSequence` với String immutable

Một biến `CharSequence` có thể chỉ vào `StringBuilder`; gán lại tham chiếu không tạo bản sao. Dùng `String snapshot = source.toString()` khi cần dữ liệu ổn định và bảo đảm đọc an toàn.

### 9.5. Cắt giữa Unicode surrogate pair

Khoảng `[start,end)` dùng chỉ số UTF-16 code unit; một emoji ngoài BMP thường cần hai `char`. Nếu cắt ở giữa hai surrogate, kết quả có thể chứa mã thay thế không ghép cặp. Nếu mục tiêu là cắt theo Unicode code point hoặc grapheme cluster, phải xác định ranh giới đúng trước khi copy.

### 9.6. Xem việc sao chép nội dung như phép so bằng identity

`StringBuffer` không override `equals()` để so nội dung. Dùng `toString().equals(...)` hoặc `String.contentEquals(CharSequence)` khi cần so theo ký tự. Đừng dùng `==` hoặc `StringBuffer.equals()` để kiểm tra hai nội dung bằng nhau.

## 10. Chương trình Java 17 hoàn chỉnh

Tệp **`MutableSourceBufferDemo.java`** sau kiểm chứng: append ở hai thời điểm; insert một đoạn rồi sửa nguồn; tạo snapshot dùng lại; chèn chính nội dung đích bằng snapshot; nguồn `CharBuffer` thay đổi vùng nhìn thấy.

~~~java
import java.nio.CharBuffer;

public class MutableSourceBufferDemo {
    public static void main(String[] args) {
        StringBuffer source = new StringBuffer("A");
        StringBuffer target = new StringBuffer("Result:");
        target.append(source);
        source.append("B");
        target.append(source);
        System.out.println("appendResult=" + target);
        System.out.println("appendSource=" + source);

        StringBuilder partSource = new StringBuilder("ABCDE");
        StringBuffer inserted = new StringBuffer("[]");
        inserted.insert(1, partSource, 1, 4);
        partSource.replace(1, 4, "xyz");
        System.out.println("insertResult=" + inserted);
        System.out.println("insertSource=" + partSource);

        StringBuffer state = new StringBuffer("OLD");
        String snapshot = state.toString();
        StringBuffer left = new StringBuffer("left:");
        StringBuffer right = new StringBuffer("right:");
        left.append(snapshot);
        right.append(snapshot);
        state.replace(0, state.length(), "NEW");
        System.out.println("stateNow=" + state);
        System.out.println("snapshotLeft=" + left);
        System.out.println("snapshotRight=" + right);

        StringBuffer self = new StringBuffer("AB");
        String oldValue = self.toString();
        self.append(oldValue);
        System.out.println("selfAppend=" + self);

        StringBuffer same = new StringBuffer("WXYZ");
        String sameSnapshot = same.toString();
        same.insert(2, sameSnapshot.substring(0, 2));
        System.out.println("selfInsert=" + same);

        CharBuffer chars = CharBuffer.wrap("ABCDE");
        StringBuffer fromView = new StringBuffer();
        fromView.append(chars);
        chars.position(2);
        fromView.append(chars);
        System.out.println("charBufferView=" + fromView);

        StringBuilder word = new StringBuilder("cat");
        StringBuffer copied = new StringBuffer();
        copied.append((CharSequence) word);
        word.setCharAt(0, 'b');
        copied.insert(0, (CharSequence) word);
        System.out.println("mutableBuilder=" + word);
        System.out.println("copyResult=" + copied);
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn, lưu file ở encoding UTF-8:

~~~bash
javac -encoding UTF-8 MutableSourceBufferDemo.java
java MutableSourceBufferDemo
~~~

Đầu ra dự kiến:

~~~text
appendResult=Result:AAB
appendSource=AB
insertResult=[BCD]
insertSource=AxyzE
stateNow=NEW
snapshotLeft=left:OLD
snapshotRight=right:OLD
selfAppend=ABAB
selfInsert=WXWXYZ
charBufferView=ABCDECDE
mutableBuilder=bat
copyResult=batcat
~~~

Điểm cần quan sát:

- `appendResult` gồm nội dung nguồn ở **hai thời điểm khác nhau**.
- `insertResult` vẫn là `[BCD]` dù nguồn đã trở thành `AxyzE`.
- Hai đích `snapshotLeft` và `snapshotRight` đều giữ `OLD` dù trạng thái nguồn giờ là `NEW`.
- Self-append/self-insert sử dụng **snapshot** để không chép từ cấu trúc đang đồng thời bị thay đổi.
- `CharBuffer` với `position=2` cung cấp đoạn còn lại `CDE` cho lần append thứ hai.
- `copyResult=batcat` cho thấy sửa `StringBuilder` sau append không thay đổi các ký tự cũ trong đích.

## 11. Checklist thực hành

- [ ] Xác định nguồn thực tế là `String` bất biến, `StringBuffer`, `StringBuilder`, `CharBuffer` hay `CharSequence` khác.
- [ ] Khi muốn nội dung “mới nhất”, chấp nhận mỗi lần gọi nhìn thấy một trạng thái nguồn riêng ở thời điểm được đọc.
- [ ] Khi muốn nhiều lần chép dùng **cùng một phiên bản**, tạo `String` snapshot **một lần** rồi tái sử dụng.
- [ ] Đừng cho nguồn mutable bị sửa đồng thời với việc đọc nếu không có cơ chế phối hợp được bảo đảm.
- [ ] Với `StringBuffer`, nhớ rằng đồng bộ hóa từng thao tác không tự biến nhiều bước thành một giao dịch.
- [ ] Với `StringBuilder`, tránh chia sẻ mutable state không có khóa hoặc quyền sở hữu rõ ràng.
- [ ] Với `insert()`, phân biệt `offset` của đích và `start/end` của nguồn; kiểm tra chỉ số trên trạng thái ổn định.
- [ ] Với chính nguồn cũng là đích, ưu tiên `String` snapshot để code dễ hiểu và tránh chồng lấp.
- [ ] Nếu copy theo đoạn Unicode, nhớ các chỉ số tính bằng UTF-16 code unit.
- [ ] Kiểm thử cả nguồn thay đổi **giữa các lần** gọi lẫn những trường hợp có nhiều luồng.

**Kết luận:** `StringBuffer.append()` và `insert()` **chép ký tự**, không giữ liên kết sống tới nguồn. Nguồn mutable có thể cho nội dung khác nhau qua từng lần chép. Khi cần bảo đảm một phiên bản ổn định hoặc đúng đắn trong môi trường đồng thời, phải dùng **snapshot bất biến và quy tắc đồng bộ phù hợp**; không được suy ra cả workflow tự động an toàn chỉ vì dùng `StringBuffer`.