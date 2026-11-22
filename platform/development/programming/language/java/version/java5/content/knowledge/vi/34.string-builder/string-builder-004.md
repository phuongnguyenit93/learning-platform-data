# StringBuilder: insert, delete, deleteCharAt và replace

## 1. Bốn thao tác chỉnh sửa trên cùng một đối tượng

`StringBuilder` giữ một dãy ký tự có thể thay đổi. Khi cần bổ sung hoặc sửa một đoạn văn bản đang xây dựng, ta không chỉ có thao tác thêm ở cuối:

- `insert`: chèn nội dung tại một vị trí.
- `delete`: xóa một đoạn.
- `deleteCharAt`: xóa một đơn vị `char` tại một chỉ số.
- `replace`: thay một đoạn bằng chuỗi mới.

Các thao tác này sửa **chính builder hiện tại** và trả về tham chiếu đến builder đó. Chúng không tạo một builder độc lập chứa kết quả.

Ví dụ, một đoạn văn bản `"Java Boot"` có thể được chèn thêm `"Spring "`, xóa đoạn vừa chèn hoặc thay từ cuối. Điều cần kiểm soát không chỉ là nội dung mới mà còn là chỉ số **tại thời điểm từng thao tác chạy**.

Các ví dụ dùng Java 17 trở lên với API vẫn áp dụng trong Java hiện nay.

## 2. Chỉ số của ký tự và vị trí chèn khác nhau

Với nội dung `"abcd"`, độ dài là 4:

~~~text
Vị trí chèn:  0   1   2   3   4
Ký tự:          a   b   c   d
Chỉ số char:    0   1   2   3
~~~

Có bốn đơn vị `char` nhưng năm vị trí chèn:

- `insert(0, ...)` chèn trước nội dung hiện có.
- `insert(2, ...)` chèn giữa `b` và `c`.
- `insert(length(), ...)` chèn ở cuối.
- `deleteCharAt(length())` sai vì không có `char` nào tại chỉ số đó.

Trong bài này, “chỉ số” và `length()` được hiểu theo đơn vị UTF-16 của Java. Một ký tự Unicode người dùng nhìn thấy không nhất thiết tương ứng với một `char`; phần Unicode ở dưới giải thích rủi ro đó.

### Quy ước đoạn [start, end)

`delete(start, end)` và `replace(start, end, text)` dùng đoạn:

~~~text
[start, end)
~~~

Nghĩa là lấy `start` nhưng không lấy `end`. Với `"abcdef"`, đoạn `[1, 4)` chứa `"bcd"`.

Nếu `end` nằm trong độ dài hiện tại, số `char` trong đoạn bằng `end - start`. Khi muốn thao tác chính xác, hãy tính giới hạn từ nội dung đang có thay vì đoán theo vị trí hiển thị.

## 3. insert: chèn, không ghi đè

~~~java
StringBuilder builder = new StringBuilder("ac");
builder.insert(1, "b");
System.out.println(builder);
~~~

Đây là mảnh mã trong phương thức; kết quả là `abc`. Nội dung cũ từ vị trí chèn trở đi được giữ và nằm phía sau phần mới.

Với cùng dữ liệu `"ac"`:

- `insert(0, "X")` tạo `"Xac"`.
- `insert(1, "X")` tạo `"aXc"`.
- `insert(2, "X")` tạo `"acX"`.

Ba kết quả trên là ba trường hợp độc lập, mỗi trường hợp bắt đầu từ một builder mới.

`insert` có các overload nhận `String`, `char`, `char[]`, `CharSequence`, `Object` và các kiểu nguyên thủy. Phải chú ý **kiểu của đối số**:

~~~java
new StringBuilder("ab").insert(1, 65);    // a65b
new StringBuilder("ab").insert(1, 'A');   // aAb
~~~

Đây là hai biểu thức minh họa độc lập. `65` được chèn dưới dạng biểu diễn số `"65"`; nó không tự được coi là mã ký tự `A`.

### Vị trí đích và đoạn nguồn là hai hệ chỉ số

Có overload chèn một phần `CharSequence`:

~~~java
StringBuilder builder = new StringBuilder("[]");
builder.insert(1, "ABCDE", 1, 4);
System.out.println(builder);
~~~

Mảnh mã in `[BCD]`. Tham số `1` đầu tiên là vị trí chèn trong builder; `1, 4` sau đó chọn đoạn `[1, 4)` của nguồn `"ABCDE"`.

Với mảng `char[]`, overload bốn đối số dùng `offset` và **số lượng** `len`:

~~~java
char[] source = {'A', 'B', 'C', 'D', 'E'};
StringBuilder builder = new StringBuilder("[]");
builder.insert(1, source, 1, 3);
System.out.println(builder);
~~~

Mảnh mã cũng in `[BCD]`, nhưng `3` ở cuối là số `char` cần lấy, không phải chỉ số kết thúc. Nhầm hai chữ ký có thể làm lấy sai đoạn hoặc gây lỗi giới hạn.

Không thay đổi nguồn `CharSequence` trong lúc thao tác chèn đang đọc nó. Nếu cần dữ liệu nguồn ổn định, có thể tạo một bản `String` trước rồi mới sửa builder đích.

## 4. delete: xóa đoạn và dồn phần sau lên

~~~java
StringBuilder builder = new StringBuilder("abcdef");
builder.delete(1, 4);
System.out.println(builder);
~~~

Đây là mảnh mã trong phương thức; kết quả là `aef`. Các đơn vị `char` ở chỉ số 1, 2, 3 bị xóa; `e` và `f` dịch sang các vị trí mới.

Một số trường hợp cần nhớ:

- `delete(0, length())` xóa toàn bộ nội dung.
- `delete(k, k)` không xóa gì nếu `k` hợp lệ.
- Nếu `end > length()`, việc xóa được giới hạn đến cuối nội dung.
- `start` âm, `start > length()` hoặc `start > end` là sai.

Ví dụ `new StringBuilder("abcdef").delete(2, 100)` cho `"ab"`. API cho phép giới hạn cuối vượt độ dài trong thao tác này; điều đó không có nghĩa mọi phương thức nhận chỉ số đều tự co lại theo cách ấy.

Trong mã ứng dụng, thường nên tính `end` chính xác theo đoạn cần xóa để ý định dễ kiểm tra. Không cố tình truyền một số cực lớn thay cho độ dài chỉ để dựa vào hành vi cắt về cuối.

## 5. deleteCharAt: xóa đúng một char

~~~java
StringBuilder builder = new StringBuilder("cart");
builder.deleteCharAt(2);
System.out.println(builder);
~~~

Mảnh mã in `cat`: `r` tại chỉ số 2 bị xóa. Độ dài giảm một đơn vị `char`.

Điều kiện chỉ số là:

~~~text
0 <= index < length()
~~~

Muốn xóa đơn vị `char` cuối:

~~~java
if (builder.length() > 0) {
    builder.deleteCharAt(builder.length() - 1);
}
~~~

Đây là mảnh mã với builder đã có. Điều kiện tránh chỉ số `-1` khi builder rỗng.

`deleteCharAt(i)` không có nghĩa xóa mọi ký tự bằng `charAt(i)` và không có nghĩa xóa cả một từ. Nó chỉ tác động một vị trí. Với Unicode ngoài BMP, một `char` có thể chỉ là một nửa của cặp surrogate; vì vậy tên phương thức không nên được hiểu là “xóa đúng một ký tự người dùng nhìn thấy”.

## 6. replace: thay đoạn, không tìm và thay toàn văn

~~~java
StringBuilder builder = new StringBuilder("red car");
builder.replace(0, 3, "blue");
System.out.println(builder);
~~~

Mảnh mã in `blue car`. `replace` xác định đoạn bằng chỉ số, không tìm từ `red` theo nội dung.

Chuỗi thay thế không cần cùng độ dài với đoạn cũ:

| Thao tác độc lập trên `"abcdef"` | Kết quả |
| --- | --- |
| `replace(1, 4, "X")` | `aXef` |
| `replace(1, 2, "WXYZ")` | `aWXYZcdef` |
| `replace(1, 4, "")` | `aef` |
| `replace(2, 2, "-")` | `ab-cdef` |
| `replace(4, 100, "!")` | `abcd!` |

Khi `start == end`, không có đoạn cũ để xóa; chuỗi mới được chèn tại vị trí đó. Khi chuỗi thay thế rỗng, thao tác tương đương xóa đoạn. Nếu `end` lớn hơn độ dài, đoạn cũ được tính đến cuối.

Với `n` là độ dài trước khi sửa, đặt `actualEnd = min(end, n)`. Khi giới hạn hợp lệ:

~~~text
độ dài mới = n - (actualEnd - start) + replacement.length()
~~~

`replace` của StringBuilder không nhận regex và không coi `$1` là nhóm thay thế. Nó cũng không tự thay mọi lần xuất hiện của một từ.

Nếu cần thay một lần xuất hiện cụ thể, tìm vị trí trước:

~~~java
StringBuilder builder =
        new StringBuilder("Hello {name}, welcome {name}");
String target = "{name}";
int position = builder.indexOf(target);

if (position >= 0) {
    builder.replace(position, position + target.length(), "Lan");
}

System.out.println(builder);
~~~

Mảnh mã in `Hello Lan, welcome {name}`. Chỉ đoạn đầu được thay. Kiểm tra `position >= 0` là cần thiết vì `indexOf` trả `-1` khi không tìm thấy.

## 7. Chương trình chạy đầy đủ: quan sát từng lần chỉnh sửa

Lưu thành `StringBuilderEditsDemo.java`:

~~~java
public class StringBuilderEditsDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java Boot");
        String snapshot = builder.toString();

        StringBuilder returned = builder.insert(5, "Spring ");
        System.out.println("insert=" + builder);

        builder.delete(5, 12);
        System.out.println("delete=" + builder);

        builder.deleteCharAt(4);
        System.out.println("deleteCharAt=" + builder);

        builder.replace(4, 8, " Core");
        System.out.println("replace=" + builder);

        builder.insert(0, "[")
               .insert(builder.length(), "]");
        System.out.println("chained=" + builder);

        System.out.println("snapshot=" + snapshot);
        System.out.println("sameObject=" + (returned == builder));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 StringBuilderEditsDemo.java
java StringBuilderEditsDemo
~~~

Stdout chính xác:

~~~text
insert=Java Spring Boot
delete=Java Boot
deleteCharAt=JavaBoot
replace=Java Core
chained=[Java Core]
snapshot=Java Boot
sameObject=true
~~~

`returned` và `builder` trỏ đến cùng đối tượng, nên `returned` cũng phản ánh các lần sửa sau. `snapshot` là một `String` được tạo trước khi chỉnh sửa và vẫn giữ nội dung cũ.

Trong chuỗi lời gọi cuối, `insert(0, "[")` chạy trước. Sau đó `builder.length()` được tính trên nội dung đã có dấu `[`; vì vậy dấu `]` được chèn đúng ở cuối.

Nối lời gọi không làm một nhóm chỉnh sửa trở thành giao dịch có hoàn tác. Nếu một thao tác phía sau thất bại, các thao tác trước đã chạy không tự bị hủy.

## 8. Giới hạn hợp lệ, đoạn rỗng và null

| Phương thức | Giới hạn cần kiểm soát |
| --- | --- |
| `insert(offset, ...)` | `0 <= offset <= length()` |
| `deleteCharAt(index)` | `0 <= index < length()` |
| `delete(start, end)` | `0 <= start <= length()` và `start <= end`; end vượt length được cắt về cuối |
| `replace(start, end, text)` | Giới hạn đoạn giống delete; text không được null |

`IndexOutOfBoundsException` hoặc lớp con của nó biểu thị chỉ số không hợp lệ. Khi mô tả lỗi, dựa vào hợp đồng tham số; không viết chương trình phụ thuộc nội dung thông báo lỗi cụ thể.

Với `insert(offset, String)`, `null` được chèn thành bốn ký tự `"null"`. Với `replace(start, end, String)`, `null` không có nghĩa “xóa đoạn” và gây `NullPointerException`. Muốn xóa đoạn bằng replace, dùng chuỗi rỗng `""`.

Overload khác có thể có hợp đồng khác; chẳng hạn không suy quy tắc của `String` sang `char[]`. Nếu trực tiếp viết `insert(0, null)`, việc chọn overload cũng có thể mơ hồ giữa các kiểu tham chiếu. Trong ví dụ cần biểu thị rõ loại null, dùng `(String) null`.

[Hợp đồng insert, delete và replace](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html).

### Chương trình kiểm tra các biên

Lưu thành `StringBuilderBoundsDemo.java`:

~~~java
public class StringBuilderBoundsDemo {
    private static void expectBounds(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=unexpected-success");
        } catch (IndexOutOfBoundsException failure) {
            System.out.println(label + "=out-of-bounds");
        }
    }

    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("abc");

        builder.insert(builder.length(), "!");
        System.out.println("insertAtEnd=" + builder);

        builder.delete(1, 100);
        System.out.println("deletePastEnd=" + builder);

        builder.replace(1, 100, "XYZ");
        System.out.println("replacePastEnd=" + builder);

        builder.delete(2, 2);
        System.out.println("emptyDelete=" + builder);

        builder.replace(2, 2, "-");
        System.out.println("emptyReplace=" + builder);

        expectBounds("insertInvalid",
                () -> new StringBuilder("abc").insert(4, "x"));
        expectBounds("deleteReversed",
                () -> new StringBuilder("abc").delete(2, 1));
        expectBounds("deleteCharAtEnd",
                () -> new StringBuilder("abc").deleteCharAt(3));
        expectBounds("replaceNegative",
                () -> new StringBuilder("abc").replace(-1, 1, "x"));

        StringBuilder withNull = new StringBuilder("abc");
        withNull.insert(0, (String) null);
        System.out.println("insertNull=" + withNull);

        try {
            new StringBuilder("abc").replace(0, 1, null);
        } catch (NullPointerException failure) {
            System.out.println("replaceNull=NullPointerException");
        }
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 StringBuilderBoundsDemo.java
java StringBuilderBoundsDemo
~~~

Stdout chính xác:

~~~text
insertAtEnd=abc!
deletePastEnd=a
replacePastEnd=aXYZ
emptyDelete=aXYZ
emptyReplace=aX-YZ
insertInvalid=out-of-bounds
deleteReversed=out-of-bounds
deleteCharAtEnd=out-of-bounds
replaceNegative=out-of-bounds
insertNull=nullabc
replaceNull=NullPointerException
~~~

Mỗi trường hợp lỗi chỉ số dùng một builder mới, nên lỗi của trường hợp trước không làm thay đổi trạng thái của trường hợp sau.

## 9. Chỉ số cũ có thể sai sau mỗi lần sửa

Với `"abcdef"`, giả sử muốn xóa `b` tại chỉ số 1 và `e` tại chỉ số 4 **theo nội dung ban đầu**.

Cách sau không giữ đúng ý định:

~~~java
StringBuilder builder = new StringBuilder("abcdef");
builder.deleteCharAt(1);
builder.deleteCharAt(4);
System.out.println(builder);
~~~

Mảnh mã in `acde`. Sau khi xóa `b`, nội dung thành `acdef`; chỉ số 4 lúc này là `f`, không còn là `e`.

Với các đoạn độc lập, không chồng lấn và tọa độ cùng được tính từ bản gốc, có thể sửa từ phải sang trái:

~~~java
StringBuilder builder = new StringBuilder("abcdef");
builder.deleteCharAt(4);
builder.deleteCharAt(1);
System.out.println(builder);
~~~

Mảnh mã in `acdf`. Sửa phía phải không làm thay đổi chỉ số của phần bên trái.

Đây không phải quy tắc áp dụng mù cho mọi dãy thao tác. Nếu đoạn chồng lấn, thay đổi phụ thuộc nhau hoặc chỉ số được tính từ trạng thái trung gian, cần xác định thứ tự theo đúng ý nghĩa của bài toán.

Trong vòng lặp xóa theo điều kiện, tăng chỉ số ngay sau khi xóa có thể bỏ qua ký tự vừa dồn tới. Có thể duyệt từ cuối với những quy tắc độc lập theo `char`, hoặc chủ động giữ nguyên chỉ số sau khi xóa khi duyệt từ đầu. Với Unicode, phải chọn đơn vị duyệt phù hợp trước.

## 10. Unicode: deleteCharAt không xóa trọn mọi ký tự

Một số Unicode code point, như U+1F600, được mã hóa trong UTF-16 bằng hai đơn vị `char`: high surrogate và low surrogate. Vì vậy chuỗi gồm `A`, code point U+1F600 và `B` có:

- `length() == 4`.
- Ba code point.
- Hai vị trí `char` thuộc cùng một cặp surrogate.

`deleteCharAt(1)` chỉ xóa high surrogate trong ví dụ này, để lại low surrogate đơn lẻ. Không nên in chuỗi hỏng rồi dựa vào ký hiệu thay thế trên terminal để kết luận; hãy kiểm tra dữ liệu thực tế.

Lưu thành `StringBuilderUnicodeEditDemo.java`:

~~~java
public class StringBuilderUnicodeEditDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        StringBuilder broken = new StringBuilder(text);
        System.out.println("initialLength=" + broken.length());
        System.out.println("initialCodePoints="
                + broken.codePointCount(0, broken.length()));

        broken.deleteCharAt(1);
        System.out.println("brokenLength=" + broken.length());
        System.out.println("unpairedLowSurrogate="
                + Character.isLowSurrogate(broken.charAt(1)));

        StringBuilder safe = new StringBuilder(text);
        int start = safe.offsetByCodePoints(0, 1);
        int end = safe.offsetByCodePoints(start, 1);
        safe.delete(start, end);

        System.out.println("safe=" + safe);
        System.out.println("safeLength=" + safe.length());
    }
}
~~~

~~~shell
javac --release 17 -encoding UTF-8 StringBuilderUnicodeEditDemo.java
java StringBuilderUnicodeEditDemo
~~~

Stdout chính xác:

~~~text
initialLength=4
initialCodePoints=3
brokenLength=3
unpairedLowSurrogate=true
safe=AB
safeLength=2
~~~

`offsetByCodePoints(0, 1)` tìm ranh giới sau code point đầu tiên. Lần tính tiếp theo đi qua thêm một code point, rồi `delete` xóa cả đoạn UTF-16 tương ứng.

Các quy tắc chỉ số UTF-16 cũng áp dụng cho `insert` và `replace`. Chèn vào giữa cặp surrogate hoặc thay chỉ một nửa có thể làm hỏng dữ liệu theo cách tương tự. [Lưu ý Unicode của deleteCharAt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#deleteCharAt(int)).

Xử lý theo code point bảo vệ cặp surrogate hợp lệ nhưng chưa giải quyết mọi “ký tự nhìn thấy”. Dấu kết hợp trong tiếng Việt hoặc chuỗi emoji có thể gồm nhiều code point tạo một đơn vị hiển thị. Nếu đang viết tính năng chỉnh sửa văn bản cho người dùng, cần quy tắc phân đoạn văn bản thích hợp; không coi mỗi code point là một ký tự hiển thị trong mọi trường hợp.

## 11. Hiệu năng và phạm vi sử dụng

Chèn hoặc xóa ở giữa có thể làm phần nội dung phía sau phải dịch chuyển. Nếu liên tục chèn ở đầu một builder ngày càng dài, tổng công việc có thể tăng đáng kể.

Khi dữ liệu cuối cùng có thể được tạo theo thứ tự từ trái sang phải, thường nên xây kết quả tuần tự thay vì thực hiện vô số lần sửa giữa chuỗi. Dùng `insert/delete/replace` khi chúng phản ánh đúng nhu cầu chỉnh sửa, không vì mọi phép ghép đều cần đổi sang insert.

Một số nguyên tắc thực tế:

- Giữ rõ nội dung và độ dài trước mỗi lần sửa.
- Không giữ chỉ số cũ qua nhiều thay đổi nếu chưa tính sự dịch chuyển.
- Khi cần nhiều chỉnh sửa theo bản gốc, xác định quan hệ chồng lấn và thứ tự trước.
- Tạo `String` bằng `toString()` khi cần kết quả ổn định để truyền đi.
- Không chia sẻ builder cho nhiều luồng cùng chỉnh sửa nếu thiếu cơ chế phối hợp.
- Không nhầm `capacity()` với độ dài nội dung; chỉ số chỉnh sửa dựa trên `length()`.

Dung lượng dự trữ có thể giúp giảm việc mở rộng bộ đệm nhưng không tạo thêm ký tự hợp lệ. Một builder có capacity lớn nhưng length bằng 0 vẫn chỉ cho chèn tại vị trí 0; không thể `deleteCharAt(10)` vì bộ đệm “còn chỗ”.

## 12. Lỗi thường gặp và cách tự kiểm tra

| Lỗi | Cách tránh |
| --- | --- |
| Tưởng end được tính vào đoạn | Viết rõ `[start, end)` và xác định ký tự cuối là `end - 1` |
| Dùng length làm chỉ số xóa một char | Chỉ số cuối là `length() - 1` và phải kiểm tra không rỗng |
| Tưởng insert ghi đè | Insert giữ nội dung cũ, replace mới thay một đoạn |
| Tưởng replace tìm mọi từ | Tính chỉ số bằng tìm kiếm và thiết kế vòng lặp riêng nếu cần nhiều lần |
| Xóa nhiều vị trí bằng tọa độ cũ từ trái sang phải | Tính lại chỉ số hoặc áp dụng thứ tự phù hợp |
| Truyền null cho replace để xóa | Dùng delete hoặc chuỗi rỗng |
| Tưởng deleteCharAt xóa trọn một ký tự Unicode bất kỳ | Xác định ranh giới UTF-16/code point/đơn vị hiển thị cần xử lý |
| Lấy capacity làm giới hạn chỉ số | Chỉ dùng length cho vùng nội dung hiện có |

Tự thực hành:

1. Với `"abcdef"`, dự đoán kết quả `insert(3, "XY")` rồi `delete(1, 4)`. Tính chỉ số lại sau lần chèn.
2. Thay một đoạn bằng chuỗi dài hơn, bằng chuỗi ngắn hơn và bằng chuỗi rỗng; kiểm tra độ dài bằng công thức ở phần replace.
3. Trên builder rỗng, thử `insert(0, "A")` và `deleteCharAt(0)` trong hai trường hợp độc lập. Giải thích vì sao một thao tác hợp lệ còn thao tác kia không.
4. Viết hàm thay lần xuất hiện đầu tiên của một từ, xử lý rõ trường hợp không tìm thấy và từ tìm kiếm rỗng.
5. Xóa hai đoạn không chồng lấn theo chỉ số bản gốc, kiểm chứng cách sửa từ phải sang trái.
6. Dùng ví dụ Unicode để chèn trước code point U+1F600; xác định chỉ số an toàn trước khi gọi insert.

Khi chỉnh sửa StringBuilder, luôn xác định **đối tượng đang bị thay đổi, đoạn chỉ số hiện tại và đơn vị ký tự đang thao tác** trước khi gọi phương thức.
