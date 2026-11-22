# Không phụ thuộc vào việc kết quả trích xuất chuỗi có dùng chung đối tượng hoặc bộ nhớ nội bộ

## 1. Mục tiêu và vấn đề cần hiểu

Khi gọi `String.substring(...)`, điều ứng dụng **được phép dựa vào** là **chuỗi ký tự kết quả**, phạm vi trích xuất và tính bất biến của `String`. Ứng dụng **không được suy luận** rằng kết quả luôn là một đối tượng `String` mới, luôn dùng chung đối tượng với chuỗi gốc, luôn chia sẻ mảng bên trong hay luôn sở hữu một bản sao bộ nhớ riêng.

Điều này liên quan trực tiếp đến bài toán **trích xuất chuỗi**. Ví dụ:

~~~java
String source = "order:12345";
String id = source.substring(6); // "12345"
~~~

Phần nghiệp vụ có thể khẳng định:

- `id` chứa đúng năm ký tự `"12345"`.
- `id.length() == 5`.
- `id.equals("12345")` là `true`.
- Không thể thay đổi nội dung `source` hoặc `id` bằng cách “sửa ký tự bên trong String”.

Tuy nhiên **không cần** và **không nên** khẳng định `source` và `id` có sử dụng chung một mảng `char[]`/`byte[]` hoặc có địa chỉ lưu trữ cụ thể. Các yếu tố đó thuộc cách JVM/JDK triển khai và tối ưu hóa.

Sau bài học, bạn sẽ biết đọc đúng hợp đồng của `substring`, tránh dùng `==` cho so sánh nội dung, phân biệt copy/alias/bất biến, hiểu hệ quả bộ nhớ của các phiên bản Java, và tổ chức mã ổn định khi thay đổi JDK.

## 2. Hợp đồng của `substring` quy định những gì?

Hai overload có hợp đồng **nội dung** rõ ràng: `s.substring(begin)` lấy từ `begin` đến hết, còn `s.substring(begin, end)` lấy `[begin, end)`. Với `n = s.length()`, điều kiện lần lượt là `0 <= begin <= n` và `0 <= begin <= end <= n`; độ dài kết quả hai tham số là `end - begin` UTF-16 code unit. Biên bằng nhau hợp lệ trả chuỗi rỗng; phạm vi sai ném `IndexOutOfBoundsException`.

```java
String s = "programming";
String prefix = s.substring(0, 7);  // "program"
String suffix = s.substring(7);     // "ming"
String empty = s.substring(7, 7);   // ""
```

Đây là các **giá trị ký tự** có thể dựa vào. Hợp đồng không đòi kết quả dùng cùng instance, instance khác, mảng sao chép hay mảng chia sẻ. `String.subSequence(begin, end)` có nội dung tương đương trên đối tượng `String` nhưng khai báo kiểu trả về là `CharSequence`.

## 3. Ba khái niệm khác nhau: giá trị, identity và backing storage

**Giá trị (value):** dãy code unit UTF-16 của chuỗi. Đây là những gì `equals`, `length`, `charAt`, `substring` và nhiều API công khai làm việc cùng.

**Identity (định danh đối tượng):** hai biến có trỏ đến cùng một instance `String` hay không; dùng `==` giữa hai tham chiếu để kiểm tra. Đây là quan hệ đối tượng, **không phải quan hệ nội dung**.

**Backing storage (vùng lưu trữ nội bộ):** cơ chế JDK dùng để biểu diễn ký tự, chẳng hạn mảng byte kèm thông tin mã hóa nội bộ ở một số triển khai. Hai đối tượng khác nhau có thể dùng chung tài nguyên nội bộ; cùng một đối tượng thì hiển nhiên dùng trạng thái nội bộ của chính nó. `==` không cho biết hai instance khác nhau có dùng chung backing array hay không.

| Câu hỏi | Công cụ phù hợp | Kết luận cho chương trình |
| --- | --- | --- |
| Hai chuỗi có **cùng nội dung** không? | `a.equals(b)` | Phù hợp để so sánh giá trị |
| Hai tham chiếu có cùng **đối tượng** không? | `a == b` | Chỉ có ý nghĩa khi thực sự cần identity |
| Hai đối tượng có cùng backing array không? | Không có hợp đồng công khai của `String` để yêu cầu việc này | Không thể suy luận từ `equals` hay `==` |
| `substring` có giữ cả vùng lưu trữ lớn không? | Phân tích phiên bản JDK, heap profiler và thử nghiệm | Quyết định tối ưu dựa trên bằng chứng từng môi trường |

Ví dụ:

~~~java
String a = new String(new char[] {'a', 'b', 'c'});
String b = new String(new char[] {'a', 'b', 'c'});

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false: hai lần tạo đối tượng String mới
~~~

Hai chuỗi có cùng nội dung dù là hai đối tượng khác nhau. Ngược lại, nếu một triển khai trả về chính `this` khi gọi `substring(0, length())`, điều đó không làm thay đổi **ý nghĩa giá trị** của kết quả. Bạn không cần nhánh xử lý riêng cho tình huống đó.

### Đừng lấy kết quả của `==` làm bằng chứng về cách lưu trữ

~~~java
String source = "ABCD";
String whole = source.substring(0, source.length());
String half = source.substring(0, 2);

// Đừng viết điều kiện nghiệp vụ phụ thuộc các so sánh identity này.
boolean wholeSameObject = (whole == source);
boolean halfSameObject = (half == source);

// Nội dung được xác định bởi API.
boolean wholeCorrect = whole.equals("ABCD"); // true
boolean halfCorrect = half.equals("AB");     // true
~~~

`wholeSameObject` và `halfSameObject` không giúp kiểm tra dữ liệu trích xuất có đúng không. Chúng cũng không chứng minh có sao chép bộ đệm hoặc giữ tham chiếu đến bộ đệm lớn hay không.

## 4. Lợi ích của tính bất biến: kết quả không bị sửa ngầm

`String` là immutable: sau khi tạo, **dãy ký tự của instance đó không bị chỉnh sửa** qua API công khai. Vì vậy ứng dụng có thể truyền một `String` trích xuất sang hàm khác mà không sợ hàm đó sửa trực tiếp nội dung chuỗi.

~~~java
String source = "hello-world";
String part = source.substring(6); // "world"

source = "changed";   // gán biến sang một String khác
System.out.println(part); // "world"
~~~

Phép gán `source = "changed"` chỉ thay **tham chiếu trong biến `source`**. Nó **không** chỉnh sửa instance nguồn cũ, không thay đổi `part`. Kết quả này không chứng minh `part` có mảng bộ nhớ riêng: dù dữ liệu được copy hay chia sẻ an toàn, **giá trị công khai** vẫn ổn định do các `String` là bất biến.

Với một mảng `char[]` có thể sửa, `String.toCharArray()` tạo **mảng mới** chứa ký tự hiện có:

~~~java
String part = "world";
char[] editable = part.toCharArray();
editable[0] = 'W';

System.out.println(new String(editable)); // "World"
System.out.println(part);                 // "world"
~~~

Thay đổi `editable` chỉ tác động đến mảng mới. Đây là **hợp đồng rõ ràng của `toCharArray`**, khác với suy luận mơ hồ về mảng nội bộ mà `substring` có thể dùng.

Ngay cả `StringBuilder` là đối tượng **mutable**, khi lấy kết quả `String` bằng `substring` thì kết quả có giá trị tại thời điểm trích xuất:

~~~java
StringBuilder builder = new StringBuilder("mutable");
String saved = builder.substring(0, 4); // "muta"

builder.setCharAt(0, 'M');
System.out.println(builder); // "Mutable"
System.out.println(saved);   // "muta"
~~~

Ở đây `saved` là `String`; các sửa đổi tương lai trên `builder` không làm nội dung `saved` thay đổi. Đó là điều cần cho nghiệp vụ. Không cần biết cách hai kiểu đối tượng quản lý mảng nội bộ.

## 5. Java từng thay đổi cách lưu trữ chuỗi — không biến nó thành hợp đồng API

Cách tổ chức `String` đã thay đổi theo phiên bản JDK:

- **Một số JDK cũ trước Java 7u6** triển khai `substring` bằng cách giữ một view gồm offset/length vào mảng ký tự lớn của nguồn. Nếu ứng dụng giữ lại đoạn con rất nhỏ nhưng bỏ chuỗi lớn, mảng lớn **có thể** bị giữ lại lâu hơn dự kiến.
- **Các bản OpenJDK/JDK hiện đại**, bao gồm Java 17, không còn cơ chế view `String` kiểu offset/count đó. Trong mã nguồn OpenJDK 17, nhánh `substring(0, length())` có thể trả về chính đối tượng `this`; các nhánh khác tạo biểu diễn chuỗi con qua helper tương ứng.
- **Java 9 trở lên** có cơ chế *Compact Strings* ở các triển khai OpenJDK phổ biến: biểu diễn nội bộ có thể dùng `byte[]` và thông tin coder. Bởi vậy không nên mô tả mọi `String` Java hiện đại là “một mảng `char[]`”.
- Java có thể tiếp tục thay đổi tối ưu hóa, chia sẻ dữ liệu nội bộ hoặc cách cấp phát. `java.lang.String` API **không hứa** lượng bộ nhớ chính xác, identity của mỗi kết quả `substring` hay khả năng thu gom một mảng cụ thể tại một thời điểm cụ thể.

Điểm cần giữ khi chuyển JDK: **logic chương trình dựa vào ký tự và API**. Nếu yêu cầu là giảm bộ nhớ, phải kiểm tra thông tin triển khai của **JDK đang chạy** và đo đúng tải sử dụng.

### Vì sao đoạn con nhỏ có thể liên quan đến bộ nhớ lớn?

Tưởng tượng xử lý một bản ghi văn bản dài, chỉ giữ vài ký tự:

~~~java
String largeRecord = loadRecord();
String key = largeRecord.substring(0, 8);
// Các bước khác chỉ giữ key.
~~~

*`loadRecord()` là hàm giả định; đoạn trên minh họa luồng dữ liệu, không phải một chương trình độc lập.*

Trên một triển khai dùng chung backing array, `key` có thể giữ gián tiếp dữ liệu lớn. Trên một triển khai sao chép dải con, khả năng giữ bộ nhớ và chi phí copy khác đi. Nhưng **không có một quy tắc cấp phát cho mọi JVM**, và `key.equals(...)` vẫn đúng ở cả hai.

Với các hệ thống xử lý lượng lớn dữ liệu, quan sát heap dump, allocation profile, khả năng sống lâu của object và benchmark đại diện. Tránh đưa thêm các bản sao chỉ vì nghe nói `substring` “luôn chia sẻ mảng” hoặc “luôn tạo mảng riêng”.

## 6. Một ví dụ Java 17+ có thể chạy và kiểm tra được

Tệp **`SubstringIndependenceDemo.java`**:

~~~java
public class SubstringIndependenceDemo {
    public static void main(String[] args) {
        String source = "prefix:alpha|suffix:omega";

        int start = source.indexOf(':') + 1;
        int end = source.indexOf('|', start);
        String part = source.substring(start, end);
        String other = new String(new char[] {'a', 'l', 'p', 'h', 'a'});

        System.out.println("part=" + part);
        System.out.println("equalContent=" + part.equals(other));
        System.out.println("length=" + part.length());
        System.out.println("prefix=" + source.substring(0, 6));
        System.out.println("empty=" + source.substring(6, 6).isEmpty());

        char[] editableCopy = part.toCharArray();
        editableCopy[0] = 'X';
        System.out.println("arrayFirst=" + editableCopy[0]);
        System.out.println("partAfterArrayEdit=" + part);

        source = "reassigned";
        System.out.println("partAfterSourceReassign=" + part);

        StringBuilder builder = new StringBuilder("mutable");
        String snapshot = builder.substring(0, 4);
        builder.setCharAt(0, 'M');
        System.out.println("builder=" + builder);
        System.out.println("snapshot=" + snapshot);

        String withEmoji = "A" + Character.toString(0x1F600) + "B";
        int afterTwoCodePoints = withEmoji.offsetByCodePoints(0, 2);
        String prefix = withEmoji.substring(0, afterTwoCodePoints);
        System.out.println("utf16End=" + afterTwoCodePoints);
        System.out.println("prefixCodePoints="
                + prefix.codePointCount(0, prefix.length()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SubstringIndependenceDemo.java
java SubstringIndependenceDemo
~~~

Kết quả `stdout` đã kiểm tra với trình biên dịch và JVM thực tế:

~~~text
part=alpha
equalContent=true
length=5
prefix=prefix
empty=true
arrayFirst=X
partAfterArrayEdit=alpha
partAfterSourceReassign=alpha
builder=Mutable
snapshot=muta
utf16End=3
prefixCodePoints=2
~~~

Giải thích:

1. `substring(start, end)` lấy đúng ký tự giữa `:` và `|`, nên `part` là `"alpha"`. `part.equals(other)` đúng dù `other` được tạo qua constructor khác.
2. `source.substring(6, 6)` là chuỗi rỗng vì hai ranh giới bằng nhau. Đây là kết quả hợp lệ; không cần đoán có reuse instance `""` hay không.
3. Chỉnh `editableCopy[0]` thành `'X'` không thể làm `part` đổi nội dung vì `toCharArray` trả mảng mới.
4. Gán `source` sang `"reassigned"` không làm đổi `part`.
5. Đổi nội dung `StringBuilder` thành `"Mutable"` không làm chuỗi snapshot `"muta"` đổi theo.
6. `offsetByCodePoints(0, 2)` trả index UTF-16 `3` cho hai code point đầu của `"A😀B"`. `substring(0, 3)` tạo đoạn có hai code point, tránh cắt giữa surrogate pair.

Chú ý: chương trình **không in identity của `substring`**, vì identity không cần để chứng minh tất cả kết quả mong muốn ở trên.

## 7. Chọn đúng phép so sánh trong nghiệp vụ

Sai khi mục tiêu là so sánh nội dung:

~~~java
String input = getInput();
String token = input.substring(0, 3);

if (token == "ABC") {
    // Sai: phụ thuộc identity của token và literal.
}
~~~

*`getInput()` là hàm minh họa, không định nghĩa trong snippet; không phải chương trình chạy độc lập.*

Đúng:

~~~java
String input = "ABC-123";
String token = input.substring(0, 3);

if ("ABC".equals(token)) {
    System.out.println("Đúng mã ABC");
}
~~~

`"ABC".equals(token)` không phụ thuộc token có được intern hay có chung đối tượng với literal. Đặt literal bên trái cũng tránh `NullPointerException` nếu token có thể null, dù `substring` của một `String` không null tự nó sẽ trả về một `String`.

Nếu bài toán cần so sánh không phân biệt chữ hoa/chữ thường, cân nhắc `equalsIgnoreCase` theo ngữ nghĩa ứng dụng; đó là quyết định **so sánh giá trị**, không liên quan đến object identity. Nếu cần nhận diện chính xác một đối tượng được chia sẻ như một sentinel do ứng dụng sở hữu, `==` có thể có ý nghĩa, nhưng đó là một hợp đồng khác hẳn so với “hai chuỗi có cùng văn bản”.

### `intern()` có làm thay đổi quy tắc trên không?

`String.intern()` trả về một biểu diễn canonical trong string pool với cơ chế quy ước identity của chính API `intern`. Nhưng **không cần gọi `intern()` để so sánh văn bản**; `equals` hoạt động trực tiếp trên nội dung.

`intern` cũng không phải một mẹo chung để tiết kiệm bộ nhớ khi trích xuất: nó ảnh hưởng đến vòng đời/tài nguyên của string pool và phải được đánh giá trên kiểu dữ liệu, cardinality và tải thực tế. Đừng tạo phụ thuộc mới vào `intern` chỉ để khiến phép `==` tình cờ đúng.

## 8. Cẩn thận về bộ nhớ và hiệu năng

Một số đánh đổi không thể suy ra chỉ từ cú pháp `substring`:

| Câu hỏi thực tế | Điều có thể nói chắc | Cần làm gì nếu quan trọng? |
| --- | --- | --- |
| Trích xuất 100 ký tự có cấp phát mảng 100 ký tự không? | API không cam kết cách cấp phát | Kiểm tra JDK và allocation profiler |
| Giữ đoạn 10 ký tự có kéo dài vòng đời một buffer 1 MB không? | Tùy cơ chế lưu trữ và tham chiếu | Heap dump, theo dõi retained size |
| `substring(0, length())` có trả `this` không? | Giá trị bằng nguồn; identity không nên là điều kiện nghiệp vụ | Không branch theo `==` |
| `new String(existing)` có ép sao chép backing array không? | Constructor tạo một object `String` mới biểu diễn cùng nội dung, nhưng không hứa **deep copy** backing storage | Không dùng để “ép giải phóng buffer” một cách mù quáng |
| Dùng `toCharArray()` có tạo mảng mới không? | **Có** theo tài liệu API, với các UTF-16 code unit của chuỗi | Chỉ dùng khi thật sự cần mảng `char[]` độc lập và có thể sửa |
| Cắt chuỗi nhiều lần có nhanh hơn giữ offset không? | Tùy cách dùng, bộ nhớ, khả năng tối ưu của JVM | Benchmark với JDK, dữ liệu và tải thật |

Đừng nhầm “không phụ thuộc vào nội bộ” với “không quan tâm hiệu năng”. Nghiệp vụ nên thiết kế theo giá trị; còn tối ưu hiệu năng được quyết định bởi **bằng chứng đo lường**. Nếu phải tương tác với API yêu cầu một `char[]` có thể sửa, `toCharArray()` là cách có hợp đồng rõ ràng. Nếu chỉ cần nội dung chuỗi, thường không cần tạo bản sao thêm.

## 9. Lưu ý ranh giới Unicode khi trích xuất

Cách lưu bộ nhớ và tính bất biến không giúp sửa **chỉ số UTF-16 sai mục tiêu**. Chẳng hạn, `substring(0, 2)` trên `"A😀B"` cắt sau high surrogate, còn muốn lấy hai code point đầu phải chuyển biên bằng `s.offsetByCodePoints(0, 2)` (trả offset `3`) trước khi gọi `substring(0, 3)`.

Với dấu kết hợp hoặc emoji gồm nhiều code point, cần xét ranh giới grapheme cluster khi sản phẩm đòi “ký tự người dùng nhìn thấy”. Đó là vấn đề **chọn đúng dãy ký tự**, độc lập với identity và backing storage của kết quả.

## 10. Các lỗi tư duy cần tránh

1. **“Kết quả `substring` chắc chắn là object mới.”** Sai như một giả định có thể mang sang mọi JDK/cách gọi. Giá trị mới trích xuất là điều API quy định; identity là chuyện khác.
2. **“Hai chuỗi `==` nhau thì là cách duy nhất để biết nội dung bằng nhau.”** Sai. `==` so tham chiếu; `equals` so nội dung.
3. **“Hai chuỗi khác object thì chắc chắn không thể chia sẻ mảng.”** Không suy ra được backing storage từ identity hai `String`.
4. **“String bất biến nên JVM chắc chắn đã copy toàn bộ buffer.”** Tính bất biến cho phép nhiều chiến lược tối ưu khác nhau, kể cả dùng chung dữ liệu nội bộ an toàn.
5. **“`new String(s)` luôn ép backing array được sao chép sâu.”** Không có bảo đảm đó từ constructor nhận một `String`; ví dụ OpenJDK 17 có thể tái sử dụng biểu diễn nội bộ.
6. **“Thấy một bản JDK copy thì mọi JDK đều copy và chi phí không đổi.”** Chiến lược cấp phát và biểu diễn có thể thay đổi theo phiên bản/runtime.
7. **“Cắt từ index 0 đến 2 luôn là hai ký tự Unicode.”** Không đúng với code point bổ sung; chỉ số `substring` tính theo UTF-16 code unit.
8. **“Đổi biến nguồn sẽ làm đoạn trích xuất đổi theo.”** Phép gán lại biến nguồn không làm nội dung `String` cũ hay kết quả trích xuất thay đổi.
9. **“Chạy một lần thấy nhanh/chậm là đủ kết luận.”** Không. Benchmark cần warmup, tải đại diện, nhiều mẫu và quan sát bộ nhớ khi kết quả được giữ sống lâu.

## 11. Tự kiểm tra

**Câu 1:** Với `String s = "Java"; String t = s.substring(0, 4);`, phải kiểm tra `t.equals(s)` hay `t == s` nếu chỉ quan tâm kết quả có đúng nội dung không?

**Đáp án:** `t.equals(s)`. Việc `t` có là cùng instance `s` không liên quan đến tính đúng của kết quả.

**Câu 2:** Vì sao thay `char[] copy = extracted.toCharArray(); copy[0] = 'X';` không sửa `extracted`?

**Đáp án:** `toCharArray()` tạo mảng mới; `String` vẫn bất biến.

**Câu 3:** Nếu một JVM cũ dùng chung backing array giữa chuỗi nguồn dài và đoạn ngắn, ứng dụng nghiệp vụ có cần kiểm tra identity để bảo vệ nội dung không?

**Đáp án:** không. Dù cùng hay khác backing array, nội dung của `String` giữ nguyên. Điều có thể cần đánh giá riêng là **retained heap memory** trên JVM cũ đó.

**Câu 4:** `new String(existing)` có phải cách bảo đảm bản sao vật lý hoàn toàn độc lập của mảng bên trong không?

**Đáp án:** không. Constructor có thể tạo object mới cùng giá trị nhưng chiến lược backing storage là chi tiết triển khai.

**Câu 5:** Lấy hai code point đầu từ `"A😀B"` bằng cách nào?

**Đáp án:** `int end = s.offsetByCodePoints(0, 2); String first = s.substring(0, end);`. `end` bằng `3` tính theo UTF-16.

**Câu 6:** Khi hiệu năng trích xuất bất thường trên bản JDK cụ thể, nên sửa logic thành so sánh `==` hay làm gì?

**Đáp án:** giữ logic đúng theo giá trị; đo cấp phát, retained size và profiling/benchmark trên workload và JDK cụ thể để xác định tối ưu.

## 12. Tài liệu tham khảo

- [Java SE 17 — `String.substring`, `String.equals`, `String.toCharArray`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): hợp đồng nội dung, biên chỉ số, tính bất biến và sao chép mảng `char[]`.
- [Java SE 17 — `StringBuilder.substring`, `setCharAt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): kết quả `String` của chuỗi nguồn mutable.
- [OpenJDK 17 — mã nguồn `String.java`](https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/lang/String.java): ví dụ chi tiết thực thi có thể trả `this` cho toàn chuỗi hoặc tạo biểu diễn kết quả cho đoạn con; chỉ dùng để tìm hiểu triển khai, không dùng thay hợp đồng API.
- [JEP 254 — Compact Strings](https://openjdk.org/jeps/254): lý do và kỹ thuật biểu diễn bộ nhớ `String` thay đổi trong OpenJDK.

**Ghi nhớ:** `substring` phải cho ra **đúng dãy ký tự yêu cầu**, còn identity của đối tượng và việc chia sẻ/copy bộ nhớ nội bộ không phải cơ sở thiết kế nghiệp vụ. So sánh bằng `equals`, dựa vào tính bất biến của `String`, dùng index Unicode phù hợp và chỉ kết luận về hiệu năng sau khi đo trên JDK thực tế.