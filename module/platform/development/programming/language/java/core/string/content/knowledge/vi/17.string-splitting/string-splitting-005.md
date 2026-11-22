# Regex khớp độ rộng bằng 0 và dấu phân cách có độ rộng trong Java String.split()

## 1. Phân biệt hai kiểu khớp

Trong Java, **String.split(String regex)** tách chuỗi theo **biểu thức chính quy (regex)**. Bản chất của một lần regex khớp quyết định ranh giới và phần tử kết quả.

- **Khớp có độ rộng dương (positive-width match)** tiêu thụ một hoặc nhiều ký tự. Ví dụ, regex ":" khớp và tiêu thụ dấu hai chấm. Ký tự được tiêu thụ không xuất hiện trong các token.
- **Khớp độ rộng bằng 0 (zero-width match)** chỉ khớp một **vị trí giữa các ký tự**, không tiêu thụ ký tự nào. Ví dụ, "(?=:)" khớp ngay *trước* dấu hai chấm; "(?<=:)" khớp ngay *sau* dấu hai chấm. Dấu phân cách vẫn thuộc một token vì không bị tiêu thụ.

Các anchor "^" (đầu chuỗi), "$" (cuối chuỗi), lookahead "(?=...)" và lookbehind "(?<=...)" thường tạo ra khớp độ rộng 0. Đừng nhầm **độ dài biểu thức regex** với **độ rộng của lần khớp**: biểu thức "(?=:)" nhiều ký tự nhưng vẫn tiêu thụ 0 ký tự.

**Quy tắc quan trọng nhất của String.split:** nếu regex khớp **độ rộng 0 ở ngay đầu chuỗi**, lần khớp đó **không tạo phần tử rỗng đầu tiên**. Trái lại, nếu regex khớp **độ rộng dương ở đầu**, nó **tạo phần tử rỗng đầu tiên**. Hai hành vi này khác nhau ngay cả khi sử dụng cùng một giá trị **limit**.

## 2. Cùng chuỗi, khác regex

Xét đầu vào **":a:b"**:

~~~text
Ranh giới:  0   1   2   3   4
Ký tự:       :   a   :   b
~~~

| Regex | Đặc điểm khớp | Các token kết quả |
| --- | --- | --- |
| ":" | Tiêu thụ hai dấu ":" ở chỉ số ký tự 0 và 2 | ["", "a", "b"] |
| "(?=:)" | Lookahead độ rộng 0 trước hai dấu ":" | [":a", ":b"] |
| "(?<=:)" | Lookbehind độ rộng 0 sau hai dấu ":" | [":", "a:", "b"] |

**Với ":"**, dấu hai chấm tại chỉ số 0 bị tiêu thụ; đoạn trước nó là chuỗi rỗng, vì vậy token đầu là "". Dấu phân cách không còn trong kết quả.

**Với "(?=:)"**, regex chỉ kiểm tra ký tự tiếp theo có phải ":" hay không. Nó khớp tại ranh giới 0 và 2. Lần khớp độ rộng 0 tại ranh giới 0 không tạo token rỗng; ranh giới 2 tách ":a" và ":b". Hai dấu ":" vẫn ở đầu các token vì không bị tiêu thụ.

**Với "(?<=:)"**, regex khớp các ranh giới 1 và 3 ngay sau dấu ":". Vì vậy dấu hai chấm đứng cuối token phía trước: [":", "a:", "b"].

## 3. Chương trình Java 17+ chạy độc lập

Lưu đoạn sau thành **ZeroWidthSplitDemo.java**:

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

public class ZeroWidthSplitDemo {
    private static void show(String label, String[] parts) {
        // Bọc mỗi token trong dấu nháy để thấy rõ chuỗi rỗng.
        String visible = Arrays.stream(parts)
                .map(s -> "'" + s + "'")
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " -> " + visible
                + " (n=" + parts.length + ")");
    }

    public static void main(String[] args) {
        String input = ":a:b";
        show("positive ':'", input.split(":"));
        show("zero '(?=:)'", input.split("(?=:)"));
        show("zero '(?<=:)'", input.split("(?<=:)"));

        show("zero '^'", "abc".split("^", -1));
        show("zero '$'", "abc".split("$", -1));
        show("zero empty regex", "abc".split("", -1));

        show("positive default", "a,b,,".split(","));
        show("positive -1", "a,b,,".split(",", -1));
        show("positive 2", "a,b,,".split(",", 2));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ZeroWidthSplitDemo.java
java ZeroWidthSplitDemo
~~~

Kết quả chính xác:

~~~text
positive ':' -> ['', 'a', 'b'] (n=3)
zero '(?=:)' -> [':a', ':b'] (n=2)
zero '(?<=:)' -> [':', 'a:', 'b'] (n=3)
zero '^' -> ['abc'] (n=1)
zero '$' -> ['abc', ''] (n=2)
zero empty regex -> ['a', 'b', 'c', ''] (n=4)
positive default -> ['a', 'b'] (n=2)
positive -1 -> ['a', 'b', '', ''] (n=4)
positive 2 -> ['a', 'b,,'] (n=2)
~~~

Hàm **show** bọc từng token bằng dấu nháy đơn và in **n** (số phần tử). Cách này giúp phân biệt token rỗng với mảng rỗng; **Arrays.toString** mặc định không tự bọc nháy chuỗi và rất dễ gây hiểu nhầm khi các token là "".

## 4. Vì sao khớp độ rộng 0 vẫn tách được?

Có thể hình dung thuật toán:

1. Tìm lần khớp của regex theo thứ tự từ trái sang phải.
2. Đưa đoạn trước lần khớp vào một token, sau đó bắt đầu xem đoạn còn lại từ **cuối phần regex đã khớp**.
3. Nếu lần khớp tiêu thụ ký tự, những ký tự đó đóng vai trò dấu phân cách và bị bỏ. Nếu lần khớp có độ rộng 0, ranh giới vẫn có thể chia chuỗi nhưng **không xóa ký tự**.
4. Xử lý phần còn lại và các token rỗng cuối theo giá trị **limit**.

Riêng một lần khớp **độ rộng 0 ở index 0** không sinh token "". Nếu regex khớp **độ rộng dương ở index 0** thì token đầu "" vẫn được sinh. Các lần khớp độ rộng 0 ở giữa chuỗi vẫn tạo ranh giới như thường; Java xử lý tiến trình tìm khớp để tránh tìm mãi cùng một vị trí.

Các anchor ở hai đầu cho thấy sự khác biệt:

- **"abc".split("^", -1)** → ["abc"]. "^" khớp độ rộng 0 ở đầu, nên không có token "" đầu dù limit âm.
- **"abc".split("$", -1)** → ["abc", ""]. "$" khớp độ rộng 0 ở cuối, tạo token "" cuối và limit -1 giữ lại.
- **"abc".split("$")** → ["abc"]. limit mặc định 0 loại token rỗng ở cuối.
- **"abc".split("", -1)** → ["a", "b", "c", ""]. Regex rỗng có thể khớp nhiều ranh giới: không tạo "" đầu nhưng vẫn có thể tạo "" cuối khi limit âm.

## 5. Đừng nhầm với tham số limit

**String.split(regex)** tương đương **String.split(regex, 0)**. Tham số **limit** có tác động sau:

| limit | Ý nghĩa | "a,b,," với regex "," |
| --- | --- | --- |
| **0** (mặc định) | Tách không giới hạn, **bỏ các token rỗng ở cuối** | ["a", "b"] |
| **Âm**, ví dụ **-1** | Tách không giới hạn, **giữ token rỗng ở cuối** | ["a", "b", "", ""] |
| **Dương**, ví dụ **2** | Tách tối đa **limit - 1** lần, token cuối chứa nguyên phần còn lại | ["a", "b,,"] |
| **1** | Không tách, trả về nguyên chuỗi | ["a,b,,"] |

**Phân biệt rõ:** limit 0 chỉ bỏ các phần tử **rỗng ở cuối**. Nó không tự bỏ token rỗng **ở đầu hay ở giữa** do delimiter có độ rộng tạo ra. Vì vậy **":a:b".split(":")** là ["", "a", "b"] mặc dù limit mặc định bằng 0.

Trong khi đó, **":a:b".split("(?=:)")** không có token rỗng đầu **vì quy tắc khớp độ rộng 0 tại đầu**, chứ không phải vì limit 0 xóa token đó. Quy tắc tại đầu vẫn đúng nếu limit = -1.

Limit dương là **mức tối đa**, không phải lời hứa số token luôn đúng bằng limit: nếu không đủ lần khớp, mảng kết quả có thể ít phần tử hơn.

## 6. Chọn biểu thức theo nhu cầu

**Loại dấu phân cách khỏi kết quả:** dùng regex tiêu thụ ký tự, chẳng hạn:

~~~java
String[] words = "red:green:blue".split(":");
// ["red", "green", "blue"]
~~~

**Giữ dấu phân cách ở đầu token tiếp theo:** dùng lookahead:

~~~java
String[] words = "red:green:blue".split("(?=:)");
 // ["red", ":green", ":blue"]
~~~

**Giữ dấu phân cách ở cuối token phía trước:** dùng lookbehind:

~~~java
String[] words = "red:green:blue".split("(?<=:)");
 // ["red:", "green:", "blue"]
~~~

Ba đoạn code trên là các mảnh minh họa có thể đặt trong phương thức. Lookahead/lookbehind chỉ **kiểm tra ngữ cảnh**, nên dấu phân cách vẫn được giữ.

**Cẩn thận ký tự đặc biệt trong regex:** dấu chấm "." là regex khớp gần như mọi ký tự, không phải dấu chấm nguyên văn. Vì thế **"a.b.c".split(".")** không trả về ["a", "b", "c"]; với limit 0, kết quả là mảng không phần tử vì các token rỗng cuối bị loại. Tách theo dấu chấm thật bằng escape hoặc **Pattern.quote**:

~~~java
String[] a = "a.b.c".split("\\.");
String[] b = "a.b.c".split(java.util.regex.Pattern.quote("."));
// Cả hai đều có kết quả ["a", "b", "c"].
~~~

Cần phân biệt **escape trong chuỗi Java** và **escape trong regex**: chuỗi Java "\\." tạo regex khớp dấu chấm nguyên văn. Với dấu "|" nguyên văn, có thể dùng "\\|" hoặc **Pattern.quote("|")**.

## 7. Những lỗi thường gặp

1. **Cho rằng zero-width không thể tách:** nó vẫn xác định ranh giới, chỉ không xóa ký tự.
2. **Mong lookahead ở đầu sinh token rỗng:** lần khớp có độ rộng 0 tại index 0 được bỏ qua cho việc tạo token đầu.
3. **Tưởng limit mặc định loại tất cả token rỗng:** chỉ các token rỗng **ở cuối** mới bị loại.
4. **Nhầm "^" và "$" với ký tự phân cách:** đây là anchor vị trí; chúng không tiêu thụ dấu phân cách có ký tự.
5. **Dùng "." hoặc "|" chưa escape như ký tự nguyên văn:** đối số của split là regex, nên cần escape hoặc dùng Pattern.quote.
6. **Không kiểm tra số token khi in mảng:** các token "" khó nhìn thấy nếu không bọc nháy và in parts.length.

### Bài tập có đáp án

**Bài 1:** Chuỗi "::x" khi tách theo hai biểu thức sau có kết quả gì?

- **"::x".split(":")** → ["", "", "x"]. Hai lần khớp tiêu thụ hai dấu ":" liên tiếp; có token rỗng đầu và giữa.
- **"::x".split("(?=:)")** → [":", ":x"]. Lần khớp độ rộng 0 ở đầu không sinh token rỗng; lần khớp tại vị trí 1 tách chuỗi nhưng giữ dấu hai chấm.

**Bài 2:** Vì sao **"x:".split("(?<=:)", -1)** cho ["x:", ""]?

- Lookbehind tạo ranh giới độ rộng 0 **sau** dấu ":" ở cuối chuỗi. limit -1 giữ token rỗng cuối; nếu dùng limit mặc định 0, token này bị loại.

## 8. Ghi nhớ

Trước khi gọi **String.split**, hãy tự hỏi: **(1)** regex có tiêu thụ ký tự không, **(2)** lần khớp có độ rộng 0 tại ngay đầu chuỗi không, và **(3)** limit có giữ token rỗng ở cuối không. Ba câu hỏi giải thích trực tiếp sự khác nhau giữa zero-width regex và dấu phân cách có độ rộng trong Java.
