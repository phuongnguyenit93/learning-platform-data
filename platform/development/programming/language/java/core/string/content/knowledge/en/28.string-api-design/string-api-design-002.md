# CharSequence không mặc nhiên bất biến hoặc có equals theo nội dung

## 1. Vấn đề trong thiết kế API

Khi viết một API thao tác chuỗi, ta dễ chọn tham số kiểu `CharSequence` thay vì `String` để chấp nhận được nhiều loại dữ liệu. Ví dụ, một phương thức nhận `CharSequence` có thể được gọi với `String`, `StringBuilder`, `StringBuffer` hay `CharBuffer`. Đây là một điểm mạnh của thiết kế theo giao diện, nhưng **`CharSequence` không hứa rằng đối tượng là bất biến hoặc `equals` so sánh nội dung**.

Hai điều cần nhớ từ đầu:

- **Bất biến:** `String` là immutable; `StringBuilder` và `StringBuffer` có thể thay đổi, còn `CharBuffer` có thể là một view có vị trí, giới hạn và vùng lưu trữ thay đổi. Tham số khai báo là `CharSequence` không đóng băng đối tượng bên dưới.
- **Bình đẳng:** giao diện `CharSequence` không bắt buộc các implementation cài `equals`/`hashCode` theo một quy tắc bình đẳng chung. Hai đối tượng có dãy `char` giống nhau có thể trả `equals == false`; hành vi của `equals` còn tùy loại đối tượng cụ thể.

Vì thế, khi API phải **lưu lâu**, **chia sẻ giữa luồng**, **dùng làm khóa map/set**, **cache**, hoặc **kiểm tra bình đẳng theo văn bản**, cần xác định hợp đồng dữ liệu rõ ràng và thường phải chụp một bản `String` bất biến tại ranh giới API.

## 2. Giao diện CharSequence thực sự bảo đảm gì?

`java.lang.CharSequence` biểu diễn **một dãy `char` có thể đọc**. Những thao tác cơ bản gồm:

| Phương thức | Ý nghĩa |
| --- | --- |
| `length()` | Số lượng UTF-16 code unit trong dãy hiện tại |
| `charAt(index)` | Đọc UTF-16 code unit tại vị trí tương ứng |
| `subSequence(start, end)` | Lấy một `CharSequence` đại diện cho đoạn con |
| `toString()` | Lấy nội dung dãy dưới dạng `String` |
| `chars()` và `codePoints()` | Duyệt qua UTF-16 code unit hoặc Unicode code point bằng `IntStream` |

**Không có** lời hứa tổng quát rằng `length()`, `charAt()` hoặc kết quả `subSequence()` luôn bất biến theo thời gian. `subSequence()` có thể trả một **view chia sẻ dữ liệu** với đối tượng gốc; loại khác có thể trả bản sao. API sử dụng `CharSequence` phải xem xét điều đó.

`length()` đếm **đơn vị UTF-16**, không đếm số ký tự hiển thị hay Unicode code point. Emoji bổ sung, ví dụ 🚀 (U+1F680), cần hai UTF-16 code unit. Vì vậy chuỗi `"A🚀"` có `length() == 3` nhưng `codePoints().count() == 2`. Khi xử lý Unicode, đừng coi mỗi `charAt(i)` là một ký tự Unicode hoàn chỉnh.

## 3. Bốn implementation thường gặp

| Implementation | Nội dung có thể đổi? | Bình đẳng `equals` mặc định của loại đó | Lưu ý khi đưa vào API |
| --- | --- | --- | --- |
| `String` | Không; giá trị String bất biến | Theo **nội dung**, giữa hai đối tượng `String` | Hợp lý để lưu trữ và làm khóa bất biến |
| `StringBuilder` | Có: `append`, `setCharAt`, `delete`… | Theo **danh tính đối tượng** vì không override `Object.equals` | Hai builder có cùng ký tự vẫn `equals == false` |
| `StringBuffer` | Có; các thao tác riêng lẻ được đồng bộ hóa | Theo **danh tính đối tượng**, không so sánh nội dung | Đồng bộ hóa từng lời gọi không biến nó thành immutable hay bảo đảm snapshot qua nhiều lời gọi |
| `CharBuffer` | Có thể thay đổi nội dung hoặc trạng thái vị trí/giới hạn; cũng có thể là buffer chỉ đọc | Theo nội dung **các ký tự còn lại** giữa `position` và `limit`, khi đối số cũng là `CharBuffer` | `equals`/`hashCode` phụ thuộc trạng thái buffer và có thể thay đổi |

Một `CharBuffer` chỉ đọc vẫn có thể thay đổi **position** của chính nó (trừ khi bên gọi không làm thế); bất biến nội dung vùng nhớ và bất biến đối tượng không phải một khái niệm. Thay đổi vị trí có thể làm dãy “còn lại” ngắn đi, khiến `toString()`, `equals` và `hashCode` thay đổi dù các ký tự ở vùng lưu trữ không đổi.

Đặc biệt, `StringBuilder` và `StringBuffer` không cài một quy tắc `equals` so sánh nội dung như `String`. Suy luận “cùng implements CharSequence nên có thể so sánh nội dung bằng equals” là sai.

## 4. Ví dụ: cùng nội dung nhưng equals khác nhau

Đây là đoạn mã minh họa đặt bên trong một phương thức:

~~~java
String a = "cat";
StringBuilder b = new StringBuilder("cat");
StringBuffer c = new StringBuffer("cat");

System.out.println(a.equals(b));                   // false
System.out.println(a.contentEquals(b));            // true
System.out.println(b.equals(new StringBuilder("cat"))); // false
System.out.println(c.equals(new StringBuffer("cat")));  // false
~~~

Giải thích:

1. `String.equals(Object)` chỉ cho kết quả true khi đối tượng khác cũng là `String` có cùng ký tự. `StringBuilder` không được coi là cùng kiểu.
2. `String.contentEquals(CharSequence)` chủ ý kiểm tra **các ký tự trong CharSequence hiện tại** so với chuỗi String. Nó thích hợp khi một phía có kiểu `String` và mục đích thực sự là so sánh văn bản.
3. `StringBuilder.equals` và `StringBuffer.equals` kế thừa ngữ nghĩa bình đẳng theo **tham chiếu** từ `Object`; hai instance khác nhau không trở thành bằng nhau vì ký tự giống nhau.
4. `Objects.equals(a, b)` chỉ xử lý an toàn trường hợp null và sau đó gọi `a.equals(b)`; nó **không biến** phép equals thành so sánh nội dung xuyên implementation.

`CharBuffer.wrap("cat").equals(CharBuffer.wrap("cat"))` cho `true` vì hai buffer có cùng dãy ký tự còn lại. Nhưng `"cat".equals(CharBuffer.wrap("cat"))` vẫn là false. Do đó không thể viết một quy tắc “CharSequence.equals luôn theo nội dung” áp dụng cho mọi implementation.

### Khi cần so sánh theo văn bản

Nếu một phía đã là `String`, có thể sử dụng `expected.contentEquals(actual)` khi `actual` là `CharSequence` không null. Nếu cần so sánh nhất quán ở biên API, tạo snapshot rõ ràng:

~~~java
static boolean sameText(CharSequence first, CharSequence second) {
    java.util.Objects.requireNonNull(first, "first");
    java.util.Objects.requireNonNull(second, "second");
    return first.toString().equals(second.toString());
}
~~~

Đây là **phương thức minh họa**, không phải một chương trình độc lập. Nó định nghĩa quy tắc so sánh bằng nội dung `String` thu được lúc gọi; không áp đặt kiểu `equals` của từng implementation. Giả định quan trọng là nội dung nguồn ổn định trong khi hai snapshot được lấy. Nếu đối tượng bị thay đổi đồng thời, phải đồng bộ hóa theo hợp đồng ứng dụng.

## 5. Mutability: giữ tham chiếu không có nghĩa là giữ nội dung

Xét ví dụ:

~~~java
StringBuilder builder = new StringBuilder("cat");
CharSequence savedReference = builder;
String savedSnapshot = builder.toString();

builder.append("s");

System.out.println(savedReference); // cats
System.out.println(savedSnapshot);  // cat
~~~

`savedReference` vẫn trỏ tới **chính builder mutable**, nên đọc sau khi sửa sẽ thấy `"cats"`. `savedSnapshot` là một `String` đã được lấy từ giá trị `"cat"` trước khi sửa, nên không đổi. Tính bất biến đến từ **đối tượng được giữ**, không đến từ kiểu biến dùng để tham chiếu nó.

Điều này ảnh hưởng đến các API kiểu:

~~~java
final class NoteStore {
    private CharSequence title;

    void setTitle(CharSequence title) {
        this.title = title; // Giữ tham chiếu tới nguồn mutable
    }

    CharSequence getTitle() {
        return title;
    }
}
~~~

Đoạn `NoteStore` là **mẫu phản ví dụ**: bên gọi có thể truyền `StringBuilder`, rồi chỉnh builder sau khi lưu. Khi đó `getTitle()` trả nội dung khác lúc gọi `setTitle` mà `NoteStore` không hề sửa gì.

Thiết kế an toàn hơn nếu hợp đồng muốn giữ “giá trị tại thời điểm truyền vào”:

~~~java
final class StableNoteStore {
    private String title;

    void setTitle(CharSequence value) {
        title = java.util.Objects.requireNonNull(value, "value").toString();
    }

    String getTitle() {
        return title;
    }
}
~~~

Dùng `String` cho trạng thái lưu trữ giúp xác định rõ đây là **giá trị bất biến**, chứ không phải một dãy ký tự có thể đổi. Lưu ý: `toString()` lấy nội dung hiện có vào `String`; nếu implementation bị biến đổi đồng thời trong lúc snapshot, cần cơ chế khóa hoặc thỏa thuận ownership phù hợp. Không có một lệnh `toString()` tổng quát bảo đảm mọi implementation đều thread-safe.

## 6. subSequence có thể là view sống

Không nên cho rằng gọi `subSequence` luôn tạo ra một bản sao bất biến. `CharBuffer` là minh họa thực tế:

~~~java
char[] data = {'c', 'a', 't'};
java.nio.CharBuffer buffer = java.nio.CharBuffer.wrap(data);
CharSequence tail = buffer.subSequence(1, 3);
String stableTail = tail.toString();

data[1] = 'o';

System.out.println(tail);       // ot
System.out.println(stableTail); // at
~~~

`tail` là một view liên kết với mảng ký tự `data`. Thay đổi mảng nền từ `a` sang `o` được phản ánh trong view, còn `stableTail` vẫn giữ nội dung cũ.

**Kết luận về thiết kế:** trả về `CharSequence` từ một API có thể là hợp lý khi chủ đích cung cấp view, nhưng người dùng cần biết **ai sở hữu bộ đệm**, **view sống được bao lâu**, **ai được phép thay đổi**, và **khi nào cần snapshot**. Nếu yêu cầu trả về một giá trị ổn định lâu dài, trả một `String` thường đơn giản hơn.

## 7. Bẫy khi dùng CharSequence làm khóa collection

Khi làm khóa trong `HashMap`/`HashSet`, đối tượng cần thỏa mãn quy tắc `equals` và `hashCode` ổn định trong lúc còn nằm trong collection.

- Một khóa `String` bất biến có `equals`/`hashCode` theo nội dung rõ ràng, phù hợp để làm khóa.
- Một khóa `StringBuilder` so sánh theo danh tính đối tượng; dù có cùng văn bản, hai builder riêng là **hai khóa khác nhau**. Thay đổi builder không làm `Object.hashCode` trở thành phép băm nội dung.
- Một khóa `CharBuffer` có `equals`/`hashCode` dựa trên phần ký tự còn lại. Việc thay `position`, `limit` hoặc nội dung nền có thể làm thay đổi ngữ nghĩa bình đẳng và giá trị hash trong lúc đối tượng đang là khóa. Khi đó việc tra cứu dựa trên bucket cũ có thể hoạt động sai kỳ vọng.

Ví dụ minh họa:

~~~java
java.util.Set<CharSequence> keys = new java.util.HashSet<>();
keys.add("cat");
keys.add(new StringBuilder("cat"));
keys.add(java.nio.CharBuffer.wrap("cat"));

System.out.println(keys.size()); // 3
~~~

Ba đối tượng trên có cùng văn bản hiển thị nhưng mang các kiểu `equals` khác nhau, nên đều có thể tồn tại riêng. **Không dùng `CharSequence` làm khóa khi định nghĩa khóa nghiệp vụ thực chất là “cùng nội dung văn bản” mà chưa chuẩn hóa hoặc snapshot.** Hãy lấy `String normalizedKey = incoming.toString()` trước khi đưa vào `Map<String, ...>`/`Set<String>`, nếu muốn bình đẳng đúng theo `String.equals`.

Đừng viết kiểm thử kiểu “sửa CharBuffer xong HashMap.get luôn trả null”: kết quả có thể phụ thuộc hash bucket và trạng thái cụ thể. Thay vào đó, kiểm tra trực tiếp rằng `equals`/`hashCode` của buffer có thể đổi theo `position` và áp dụng quy tắc **không biến đổi khóa ảnh hưởng đến băm**.

## 8. Chương trình Java 17+ hoàn chỉnh

Tệp **CharSequenceApiDemo.java** bên dưới kiểm tra trực tiếp các khác biệt vừa thảo luận: `String.equals`, `contentEquals`, identity equality, bình đẳng `CharBuffer`, mutable builder, mutable view, snapshot, Unicode và null.

~~~java
import java.nio.CharBuffer;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class CharSequenceApiDemo {
    private static int passed;

    private static void check(String name, boolean ok) {
        if (!ok) {
            throw new AssertionError("FAILED: " + name);
        }
        passed++;
    }

    static String snapshot(CharSequence text) {
        return Objects.requireNonNull(text, "text").toString();
    }

    public static void main(String[] args) {
        String text = "cat";
        StringBuilder builder = new StringBuilder("cat");
        StringBuffer buffer = new StringBuffer("cat");
        CharBuffer charBuffer1 = CharBuffer.wrap("cat");
        CharBuffer charBuffer2 = CharBuffer.wrap("cat");

        check("String.equals checks type", !text.equals(builder));
        check("String.contentEquals", text.contentEquals(builder));
        check("Objects.equals not content comparison",
                !Objects.equals(text, builder));
        check("StringBuilder identity equality",
                !builder.equals(new StringBuilder("cat")));
        check("StringBuffer identity equality",
                !buffer.equals(new StringBuffer("cat")));
        check("CharBuffer content equality",
                charBuffer1.equals(charBuffer2));
        check("CharBuffer versus String",
                !charBuffer1.equals(text) && !text.equals(charBuffer1));
        check("equal CharBuffers have same hash",
                charBuffer1.hashCode() == charBuffer2.hashCode());

        Set<CharSequence> mixed = new HashSet<>();
        mixed.add(text);
        mixed.add(builder);
        mixed.add(charBuffer1);
        check("mixed set has three keys", mixed.size() == 3);

        String fixed = snapshot(builder);
        builder.append("s");
        check("snapshot is immutable", fixed.equals("cat"));
        check("builder changes", builder.toString().equals("cats"));

        charBuffer1.position(1);
        check("CharBuffer remaining content changed",
                charBuffer1.toString().equals("at"));
        check("CharBuffer equality changed",
                !charBuffer1.equals(charBuffer2));
        check("CharBuffer hash changed",
                charBuffer1.hashCode() != charBuffer2.hashCode());

        char[] array = {'c', 'a', 't'};
        CharBuffer view = CharBuffer.wrap(array);
        CharSequence sub = view.subSequence(1, 3);
        check("initial subSequence", sub.toString().equals("at"));
        String subCopy = snapshot(sub);
        array[1] = 'o';
        check("backed view reflects mutation", sub.toString().equals("ot"));
        check("snapshot of view is stable", subCopy.equals("at"));

        CharSequence unicode = new StringBuilder("A\uD83D\uDE80");
        check("UTF-16 units differ from code points",
                unicode.length() == 3 && unicode.codePoints().count() == 2);
        check("null rejection", rejectsNull());

        System.out.println("String.equals(StringBuilder)="
                + text.equals(new StringBuilder("cat")));
        System.out.println("String.contentEquals(StringBuilder)="
                + text.contentEquals(new StringBuilder("cat")));
        System.out.println("HashSet.size=" + mixed.size());
        System.out.println("BuilderSnapshot=" + fixed);
        System.out.println("BuilderNow=" + builder);
        System.out.println("CharBufferAfterPosition=" + charBuffer1);
        System.out.println("ViewAfterArrayChange=" + sub);
        System.out.println("ViewSnapshot=" + subCopy);
        System.out.println("PASS: " + passed + " checks");
    }

    static boolean rejectsNull() {
        try {
            snapshot(null);
            return false;
        } catch (NullPointerException expected) {
            return true;
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CharSequenceApiDemo.java
java CharSequenceApiDemo
~~~

Stdout chính xác nếu 19 kiểm tra thành công:

~~~text
String.equals(StringBuilder)=false
String.contentEquals(StringBuilder)=true
HashSet.size=3
BuilderSnapshot=cat
BuilderNow=cats
CharBufferAfterPosition=at
ViewAfterArrayChange=ot
ViewSnapshot=at
PASS: 19 checks
~~~

Hàm `check` ném `AssertionError` nếu bất kỳ trường hợp nào sai, nên không có dòng `PASS` giả khi kết quả không đúng. Không dùng `assert` của Java, vì `assert` bị vô hiệu hóa theo mặc định nếu không bật `-ea`.

Điểm đáng chú ý trong ví dụ: `CharBuffer.equals` và `hashCode` phản ánh phần văn bản còn lại từ `position` tới `limit`; sau `charBuffer1.position(1)`, dãy hiện tại của nó đổi từ `"cat"` thành `"at"` mà mảng ký tự ban đầu không nhất thiết thay đổi. Ngược lại, bản `String` trả từ `snapshot` vẫn chứa giá trị trước lúc đối tượng được sửa.

## 9. Cách chọn tham số và kiểu trả về

| Mục đích API | Gợi ý kiểu | Cách xử lý |
| --- | --- | --- |
| Đọc đầu vào ngay trong lời gọi, không giữ lại | `CharSequence` | Có thể chấp nhận nhiều nguồn dữ liệu; ghi rõ yêu cầu nguồn không bị sửa trong lúc xử lý |
| Lưu text, cache hoặc chuyển sang xử lý bất đồng bộ | Nhận `CharSequence` nếu cần linh hoạt; **lưu `String`** | Lấy snapshot một lần tại ranh giới ownership |
| Dùng khóa Map/Set theo nội dung văn bản | `String` | Chuẩn hóa nếu cần, rồi lưu/so sánh bằng `String.equals` và `hashCode` |
| Trả về một giá trị text ổn định | `String` | Bên nhận biết đây là giá trị bất biến |
| Trả về view có thể phản ánh nguồn | `CharSequence` / `CharBuffer` | Tài liệu hóa backing storage, vòng đời, position/limit và quy tắc cập nhật |
| Sắp xếp theo ký tự | `Comparator` được xác định rõ | Không tự đồng nhất `compare == 0` với `equals` của mọi CharSequence |

Nếu API muốn **giữ nguyên cả kiểu dữ liệu mutable bên ngoài**, phải ghi rõ quy định thay đổi, thread-safety và thời gian sống của dữ liệu. Nếu API cần **giá trị snapshot độc lập**, đầu vào linh hoạt và nội bộ immutable là lựa chọn dễ chứng minh tính đúng hơn.

### Null và hợp đồng đầu vào

Một tham số `CharSequence` vẫn có thể là `null`. Hãy quyết định null **bị từ chối**, **là chuỗi rỗng**, hay **được xử lý theo chính sách riêng**. Ví dụ từ chối rõ ràng:

~~~java
static String snapshot(CharSequence input) {
    return java.util.Objects.requireNonNull(input, "input").toString();
}
~~~

Đây là đoạn phương thức minh họa có phiên bản chạy trong chương trình ở trên. Tránh tùy tiện gọi `String.valueOf((Object) input)` khi null có ý nghĩa lỗi: nó chuyển null thành văn bản `"null"`, có thể che giấu sai dữ liệu.

### Concurrency và ownership

`StringBuilder` không thread-safe. `StringBuffer` đồng bộ hóa nhiều phương thức riêng lẻ, nhưng một quy trình gồm `length()`, rồi lặp `charAt()`, hoặc ghép nhiều lời gọi không được bảo đảm là một snapshot nguyên tử nếu luồng khác cùng sửa dữ liệu. `CharBuffer` cũng có trạng thái mutable. Nếu nhiều luồng có thể thay đổi đầu vào, cần **khóa hợp tác**, **chuyển giao ownership**, hoặc **bản sao ổn định được tạo trước khi chia sẻ**.

Ngay cả khi API khai báo `CharSequence` như tham số `final`, từ khóa `final` chỉ ngăn **gán lại biến tham chiếu** trong phương thức; nó không làm đối tượng bất biến.

## 10. Ma trận kiểm thử cho API nhận CharSequence

| Trường hợp | Kiểm thử cần có |
| --- | --- |
| Hai `String` cùng nội dung | `equals` và `hashCode` giống nhau |
| `String` và `StringBuilder` cùng nội dung | `String.equals` trả false; phép so sánh nội dung tường minh trả true |
| Hai `StringBuilder` cùng nội dung | Không được giả định chúng `equals` |
| Hai `StringBuffer` cùng nội dung | Không được giả định chúng `equals` |
| Hai `CharBuffer` có cùng nội dung còn lại | So sánh theo nội dung còn lại |
| `CharBuffer` đổi `position` | Nội dung logic, `equals` và `hashCode` có thể đổi |
| `CharBuffer` view của `char[]` | Đổi mảng nền có thể đổi kết quả quan sát view |
| `StringBuilder` thay đổi sau khi truyền | Bản tham chiếu đổi theo, snapshot `String` giữ nguyên |
| Đối tượng làm khóa collection | Đúng quy tắc bình đẳng mong muốn; không biến đổi phần tham gia `hashCode` |
| Nội dung có emoji bổ sung | `length()` đếm UTF-16 code unit; `codePoints()` đếm code point |
| Input `null` | Chính sách xử lý rõ ràng, có kiểm thử |
| Dữ liệu bị sửa từ nhiều luồng | Snapshot hoặc đồng bộ hóa theo hợp đồng; không giả định mọi CharSequence thread-safe |

## 11. Sai lầm thường gặp và cách tránh

1. **Viết `a.equals(b)` để so sánh hai `CharSequence` bất kỳ:** phép so sánh phụ thuộc implementation. Nếu yêu cầu là “cùng văn bản”, chuẩn hóa sang String snapshot hoặc dùng API so sánh nội dung thích hợp.
2. **Giữ `CharSequence` lâu dài rồi coi nó như immutable:** bên ngoài vẫn có thể sửa builder hoặc backing array. Lưu `String` khi cần trạng thái ổn định.
3. **Dùng CharBuffer như khóa hash rồi thay position:** giá trị hash có thể thay đổi, làm vi phạm điều kiện của hash collection.
4. **Cho rằng `subSequence` luôn copy:** có implementation trả view chia sẻ nguồn. Khi cần snapshot chắc chắn, lấy một `String`.
5. **Tin `StringBuffer` khiến mọi chuỗi thao tác trở thành atomic:** đồng bộ hóa từng phương thức không bao trùm cả thuật toán nhiều bước.
6. **Dùng `final CharSequence` để “chống sửa”:** `final` không đóng băng đối tượng.
7. **Sử dụng `length()` để đếm ký tự hiển thị:** UTF-16 code unit khác code point; code point lại khác grapheme cluster.
8. **Gọi `Objects.equals` rồi tưởng có so sánh nội dung:** nó vẫn gọi `equals` của đối tượng cụ thể; chỉ thêm xử lý null.
9. **Dùng `toString()` nhiều lần trong cùng một phép tính trên nguồn mutable:** có thể nhận các snapshot khác nhau. Nếu cần một ảnh chụp nhất quán, lấy một lần ở ranh giới phù hợp rồi xử lý String đó.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Một phương thức nhận `CharSequence input` và gán `this.value = input`. Người gọi truyền `StringBuilder("abc")`, sau đó append `"d"`. Nội dung đọc từ `value` là gì?

Đáp án: theo tham chiếu tới cùng builder, nội dung hiện tại sẽ là `"abcd"`. Để lưu đúng `"abc"` tại thời điểm gọi, phải lấy bản snapshot `String`.

**Câu 2.** Vì sao `new StringBuilder("x").equals(new StringBuilder("x"))` là false?

Đáp án: `StringBuilder` không override `Object.equals` theo nội dung, nên hai đối tượng khác danh tính không bằng nhau.

**Câu 3.** Vì sao hai `CharBuffer.wrap("x")` có thể bằng nhau, nhưng `"x".equals(CharBuffer.wrap("x"))` là false?

Đáp án: `CharBuffer.equals` so sánh nội dung còn lại với một `CharBuffer` khác. `String.equals` chỉ coi đối tượng kiểu `String` có cùng nội dung là bằng nhau.

**Câu 4.** Nếu API muốn cache chuỗi do người gọi truyền trong nhiều giờ thì nên lưu `CharSequence` hay `String`?

Đáp án: nếu cần nội dung ổn định theo thời điểm nhận, lưu `String` snapshot (kèm chính sách null và đồng bộ hóa nếu nguồn có thể bị sửa đồng thời).

**Câu 5.** Một `CharBuffer` đã nằm trong `HashSet`. Có an toàn khi di chuyển position rồi dùng bộ đệm đó như khóa không?

Đáp án: không nên; `equals`/`hashCode` của CharBuffer phụ thuộc phần dữ liệu còn lại, việc thay position có thể khiến quy tắc tra cứu khóa không còn ổn định.

## 13. Ghi nhớ

**`CharSequence` mô tả khả năng đọc một dãy UTF-16 code unit; nó không bảo đảm immutable và không thống nhất equals theo nội dung giữa các implementation.** Dùng `CharSequence` để linh hoạt nhận dữ liệu đầu vào, nhưng xác định rõ ownership, thời gian sống và cơ chế đồng bộ. Khi cần một **giá trị văn bản ổn định**, đặc biệt để cache hoặc dùng làm khóa collection, hãy tạo `String` snapshot và định nghĩa rõ phép so sánh theo nội dung.
