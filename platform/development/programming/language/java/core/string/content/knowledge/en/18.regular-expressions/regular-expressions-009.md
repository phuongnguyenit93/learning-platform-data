# Lựa chọn mẫu regex tránh khớp quá rộng hoặc quay lui quá nhiều trong Java

## 1. Mục tiêu

Biểu thức chính quy (regex) giúp kiểm tra, tìm kiếm và trích xuất văn bản, nhưng một mẫu “trông có vẻ chạy đúng” vẫn có thể gặp hai loại vấn đề khác nhau:

1. **Khớp quá rộng (overmatching):** regex chấp nhận hoặc nuốt những ký tự/đoạn văn bản nằm ngoài ý định. Đây trước hết là vấn đề **tính đúng đắn**.
2. **Quay lui quá nhiều (excessive backtracking):** regex engine thử quá nhiều cách ghép nhóm, lặp hoặc nhánh khi tìm kết quả; trường hợp xấu có thể tiêu tốn rất nhiều CPU. Đây là vấn đề **hiệu năng và an toàn**, đặc biệt khi input do người dùng kiểm soát.

Hai vấn đề có thể cùng xuất hiện nhưng không đồng nghĩa: một regex ngắn, ít quay lui vẫn có thể khớp sai phạm vi; một regex chỉ chấp nhận đúng tập chuỗi mong muốn vẫn có thể rất chậm trên đầu vào gần đúng nhưng thất bại.

Trong Java, **java.util.regex.Pattern** biên dịch regex và **Matcher** thực hiện phép khớp. Pattern dùng kiểu engine NFA có thứ tự thử nhánh và khả năng backtracking. Vì vậy, thiết kế regex cần xét **ngôn ngữ được chấp nhận, phạm vi tìm kiếm và đường đi khi thất bại**, không chỉ ví dụ thành công.

## 2. Bắt đầu từ điều kiện dữ liệu thật sự

Trước khi viết regex, trả lời bốn câu hỏi:

- **Muốn xác thực toàn bộ hay chỉ tìm một phần?** Dùng **matcher.matches()** để khớp toàn bộ region; **find()** để tìm đoạn con; **lookingAt()** để kiểm tra tiền tố. Một regex tốt vẫn cho kết quả sai nếu chọn nhầm phương thức.
- **Tập ký tự hợp lệ là gì?** Khi biết cấu trúc đầu vào, ưu tiên **[0-9]**, **[A-Za-z]**, **[^,]** hoặc lớp ký tự chính xác thay vì **.**.
- **Độ dài hợp lệ là bao nhiêu?** Dùng lượng từ có biên, ví dụ **{1,8}**, và kiểm tra giới hạn kích thước input tại ranh giới ứng dụng.
- **Dấu phân cách và ranh giới token ở đâu?** Chốt rõ đầu/cuối, dấu phẩy, dấu **>**, dấu xuống dòng hoặc ranh giới từ thay vì trông chờ **.* ** tự dừng ở vị trí hợp lý.

Ví dụ một mã tài khoản chỉ gồm 3–16 ký tự, ký tự đầu phải là chữ in hoa ASCII, các ký tự sau có thể là chữ in hoa, chữ số hoặc dấu gạch dưới:

~~~java
Pattern accountCode = Pattern.compile("[A-Z][A-Z0-9_]{2,15}");
boolean valid = accountCode.matcher("AB_7").matches();
~~~

Dùng **matches()** bảo đảm toàn bộ chuỗi phải thỏa mẫu. Dùng **find()** với cùng regex trên **"xAB_7!"** có thể tìm được một đoạn con hợp lệ, nhưng điều đó **không** làm cả mã đầu vào hợp lệ.

**Một nguyên tắc quan trọng:** regex nên mô tả ngữ pháp tối thiểu cần thiết, thay vì mô tả “mọi thứ có thể xuất hiện” rồi hy vọng kết quả đúng.

## 3. Dấu chấm và lượng từ tham lam: nguồn gốc overmatching

Trong Java regex:

- **.** khớp một ký tự bất kỳ, ngoại trừ ký tự kết thúc dòng theo chế độ mặc định.
- **.*** khớp từ 0 ký tự trở lên và là **greedy**: ban đầu cố tiêu thụ nhiều ký tự nhất có thể; nếu phần sau không khớp, engine có thể quay lui để trả lại ký tự.
- **.+** khớp ít nhất một ký tự, cũng greedy.
- **Pattern.DOTALL** cho phép **.** khớp cả ký tự xuống dòng; nó có thể làm phạm vi khớp rộng thêm.

Ví dụ, muốn tìm từng đoạn có dạng thẻ trong chuỗi:

~~~text
<b>Hi</b><i>ok</i>
~~~

Mẫu quá rộng:

~~~regex
<.*>
~~~

Khi gọi **find()**, mẫu này có thể lấy từ dấu **<** đầu tiên đến dấu **>** cuối cùng:

~~~text
<b>Hi</b><i>ok</i>
~~~

Nếu chỉ muốn đoạn bắt đầu bằng **<** và kết thúc ở dấu **>** đầu tiên, hai cách thường gặp là:

~~~regex
<.*?>
<[^>]*>
~~~

**.*?** là lượng từ **reluctant/lazy**, thử ngắn trước; nó sẽ mở rộng nếu cần để phần sau khớp. **[^>]* ** mô tả chính xác hơn “không chứa dấu >” và không cần thử vượt qua dấu phân cách **>**. Với ngữ pháp token đơn giản, mẫu có lớp ký tự phủ định thường dễ suy luận hơn.

Các mẫu trên chỉ thích hợp để minh họa **token dấu ngoặc nhọn đơn giản**. Chúng **không** phải trình phân tích HTML/XML hoàn chỉnh: thuộc tính có dấu **>** trong chuỗi trích dẫn, phần comment hoặc cú pháp lồng nhau đòi hỏi parser chuyên dụng.

### 3.1. Vì sao đổi sang lazy chưa giải quyết được mọi vấn đề?

Lượng từ **greedy** như `a+` thử lấy nhiều nhất trước rồi có thể quay lui; **lazy** như `a+?` thử lấy ít nhất trước nhưng vẫn có thể mở rộng và quay lui. Cả hai đều cần được kiểm tra với dữ liệu gần khớp nhưng thất bại: thay `.*` bằng `.*?` không tự loại bỏ sự mơ hồ trong ngữ pháp hoặc bảo đảm hiệu năng.

Lượng từ **possessive** như `a++` không trả lại ký tự; nó có thể giảm một số đường quay lui nhưng cũng đổi tập chuỗi được chấp nhận. Phần 7 đi sâu vào cách chứng minh khi nào possessive hoặc atomic group bảo toàn ngữ nghĩa. Với token có dấu phân cách rõ, thử một lớp ký tự cụ thể như `[^>]*` trước khi tối ưu chiến lược lượng từ.

## 4. Ví dụ Java 17+ chạy được

Tạo tệp **RegexSelectionDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexSelectionDemo {
    public static void main(String[] args) {
        String input = "<b>Hi</b><i>ok</i>";

        Matcher broad = Pattern.compile("<.*>").matcher(input);
        if (broad.find()) {
            System.out.println("broad: " + broad.group());
        }

        Matcher precise = Pattern.compile("<[^>]*>").matcher(input);
        while (precise.find()) {
            System.out.println("token: " + precise.group());
        }

        Pattern accountCode = Pattern.compile("[A-Z][A-Z0-9_]{2,15}");
        System.out.println("valid: " + accountCode.matcher("AB_7").matches());
        System.out.println("invalid: " + accountCode.matcher("AB_7!").matches());

        System.out.println("greedy: "
                + Pattern.compile("a+a").matcher("aaa").matches());
        System.out.println("possessive: "
                + Pattern.compile("a++a").matcher("aaa").matches());

        String nearMiss = "aaaaaaaaab";
        System.out.println("linear rewrite: "
                + Pattern.compile("a+$").matcher(nearMiss).matches());
    }
}
~~~

Chạy:

~~~bash
javac RegexSelectionDemo.java
java RegexSelectionDemo
~~~

Output chính xác:

~~~text
broad: <b>Hi</b><i>ok</i>
token: <b>
token: </b>
token: <i>
token: </i>
valid: true
invalid: false
greedy: true
possessive: false
linear rewrite: false
~~~

Ý nghĩa:

1. **<.*>** lấy toàn bộ từ dấu mở đầu tiên đến dấu đóng cuối cùng, quá rộng nếu muốn từng token.
2. **<[^>]*>** dừng tại dấu **>** gần nhất theo đúng tập ký tự cho phép.
3. **accountCode.matches()** chỉ chấp nhận toàn bộ mã hợp lệ, không chấp nhận ký tự **!** ở cuối.
4. Lượng từ possessive đổi kết quả vì không nhường ký tự.
5. Mẫu đơn giản **a+$** không chấp nhận chuỗi có **b** cuối; đây là phiên bản gọn của tình huống xử lý ký tự **a** liên tiếp được đề cập dưới đây.

## 5. Catastrophic backtracking là gì?

**Backtracking** là cơ chế thông thường: khi một nhánh khớp chưa đưa tới kết quả cuối cùng, engine có thể thử phân chia hoặc nhánh khác. Điều này giúp regex hỗ trợ các cấu trúc phong phú, nhưng có thể trở nên đắt đỏ nếu **một đoạn input có quá nhiều cách được các phần regex khác nhau cùng tiêu thụ**.

Mẫu cảnh báo kinh điển:

~~~regex
(a+)+$
~~~

Với input gồm nhiều ký tự **a** rồi thêm **b** ở cuối:

~~~text
aaaaaaaaaaaaaaaaab
~~~

Về logic, mẫu cần “một hoặc nhiều nhóm, mỗi nhóm chứa một hoặc nhiều a”, sau đó đến cuối. Trên một chuỗi toàn **a**, nhiều cách chia nhóm cùng cho kết quả khớp. Khi ký tự **b** làm toàn biểu thức thất bại, engine có thể phải thử một lượng rất lớn những cách phân chia đó.

Ở các họ input và triển khai cụ thể, mức tăng thời gian có thể rất lớn, thậm chí theo hàm mũ. **Không nên dựa vào một con số độ phức tạp cứng cho mọi regex và mọi phiên bản JVM**, vì engine có thể tối ưu một số cấu trúc; vấn đề cần nhận diện là **số đường quay lui tăng rất nhanh khi độ dài input tăng**.

Ví dụ khác đáng nghi:

~~~regex
(a|aa)+$
([A-Za-z]+)*$
(.*)+$
~~~

Ở mẫu đầu, **a** và **aa** chồng lấn; ở mẫu thứ hai và thứ ba, các lớp lặp lồng nhau có nhiều cách chia chuỗi. Một input rất dài chỉ khác ở ký tự cuối thường là phép thử phơi bày vấn đề tốt hơn input khớp hoàn toàn.

**Đây là nền tảng của ReDoS (Regular Expression Denial of Service):** kẻ tấn công cung cấp input gây quá nhiều công việc cho regex engine, khiến thread xử lý yêu cầu bị chiếm CPU lâu bất thường. Kích thước input không cần cực lớn nếu cấu trúc mẫu đủ mơ hồ.

## 6. Sửa từ ngữ pháp: loại bỏ đường phân tích dư thừa

Với mục tiêu “chuỗi chỉ gồm ít nhất một a”, mẫu:

~~~regex
(a+)+$
~~~

không cần hai lớp lặp. Có thể viết:

~~~regex
a+
~~~

và dùng **matches()** để kiểm tra toàn chuỗi. Một mẫu ngắn hơn, không có vòng lặp lồng nhau, thường dễ kiểm chứng hơn về cả tính đúng đắn lẫn hiệu năng.

Tương tự, nếu chỉ muốn ít nhất một chữ cái ASCII, thay vì:

~~~regex
([A-Za-z]+)*$
~~~

hãy viết:

~~~regex
[A-Za-z]+
~~~

và gọi **matches()**. Hai mẫu ở trên còn **không hoàn toàn tương đương**: mẫu có **\*** bên ngoài có thể chấp nhận chuỗi rỗng, còn **+** thì không. Vì vậy, cần xác định rõ **chuỗi rỗng có hợp lệ không** trước khi thay thế.

Đối với alternation chồng lấn:

~~~regex
(a|aa)+
~~~

nếu mục tiêu chỉ là một dãy **a**, thay bằng **a+**. Nếu hai nhánh có ý nghĩa thật sự khác nhau, cần diễn đạt dấu phân cách/ràng buộc sao cho phân tách được rõ ràng, thay vì cắt nhánh một cách tùy tiện.

**Quy tắc sửa:** trước tiên xác định ngôn ngữ hợp lệ; sau đó tạo một biểu thức càng ít cách phân tích cùng một input càng tốt. Tránh sửa hiệu năng bằng cách vô tình đổi tập chuỗi được chấp nhận.

## 7. Khi nào dùng possessive quantifier và atomic group?

Java hỗ trợ lượng từ **possessive**:

~~~regex
X*+
X++
X?+
X{m,n}+
~~~

và **atomic/independent group**:

~~~regex
(?>X)
~~~

Cả hai giới hạn đường quay lui: một khi đoạn được tiêu thụ trong phần possessive hoặc atomic đã được chốt, engine không thử các phương án nội bộ khác để cứu phép khớp sau đó.

Ví dụ:

~~~java
Pattern greedy = Pattern.compile("a+a");
Pattern possessive = Pattern.compile("a++a");

System.out.println(greedy.matcher("aaa").matches());     // true
System.out.println(possessive.matcher("aaa").matches()); // false
~~~

Đây là chứng cứ rằng phép thay đổi **có thể ảnh hưởng kết quả**. Chỉ dùng possessive khi chắc chắn phần sau không cần các ký tự được phần trước tiêu thụ.

Một trường hợp tương đối tự nhiên: chuỗi gồm **một hoặc nhiều chữ số rồi đến dấu chấm phẩy**. Nếu chữ số là **[0-9]** và dấu tiếp theo bắt buộc là **;**, hai phần không tranh giành ký tự:

~~~regex
[0-9]++[;]
~~~

So với **[0-9]+[;]**, việc không hoàn lại chữ số là an toàn cho ngữ pháp này vì dấu **;** không thuộc lớp chữ số. Nhưng điều đó không có nghĩa possessive luôn nhanh hơn có thể đo được; chỉ là đã loại đi một loại quay lui không cần thiết.

Atomic group có thể được dùng để cô lập một nhánh hoặc một cụm lặp khi bạn chứng minh được engine không cần xem xét lại lựa chọn bên trong nó. Ví dụ **(?>a+)a** cũng thất bại trên **aaa**, giống **a++a**.

Với bài toán đơn giản, **sửa cấu trúc mẫu và dùng lớp ký tự cụ thể là ưu tiên đầu tiên**. Possessive/atomic chỉ là công cụ khi cần khống chế backtracking có chủ đích; chúng không cứu được tất cả regex mơ hồ và có thể loại bỏ kết quả hợp lệ nếu dùng sai.

## 8. Giới hạn phạm vi tìm kiếm để tránh quét lan rộng

### 8.1. Chọn đúng phương thức

**matches()** phù hợp khi xác thực cả vùng đầu vào:

~~~java
Pattern p = Pattern.compile("[A-Z0-9_]{3,16}");
boolean ok = p.matcher("AB_12").matches();
~~~

**find()** phù hợp khi cần trích các đoạn con, ví dụ tìm tất cả số:

~~~java
Matcher m = Pattern.compile("[0-9]+").matcher("x12 y345");
while (m.find()) {
    System.out.println(m.group());
}
~~~

Nếu xác thực dữ liệu mà vô tình dùng **find()**, mã độc hại có thể mang theo một đoạn con hợp lệ nhưng cả chuỗi vẫn sai. Nếu chỉ cần tìm một đoạn con, ép **matches()** bằng cách bao quanh **.*...*** thường làm mẫu rộng và khó đoán hơn.

### 8.2. Dùng anchor khi cần rõ ràng về vị trí

- **\A**: đầu toàn bộ input của Matcher.
- **\z**: cuối tuyệt đối của input.
- **^** và **$**: chịu ảnh hưởng của **MULTILINE** và cách xử lý ranh giới dòng.
- **\b**: ranh giới từ, phụ thuộc quy tắc ký tự từ; không thay thế cho việc xác định rõ dấu phân cách theo nghiệp vụ.

Ví dụ khi tìm một dòng log bắt đầu bằng **ID=** và tối đa tám chữ số:

~~~java
Pattern line = Pattern.compile("^ID=([0-9]{1,8})$", Pattern.MULTILINE);
Matcher m = line.matcher("noise\nID=42\nend");
System.out.println(m.find());    // true
System.out.println(m.group(1)); // 42
~~~

Nếu cần kiểm tra cả input là **ID=42** và không có dữ liệu thừa, dùng **matches()** với **ID=[0-9]{1,8}** hoặc anchor phù hợp. Với mọi lựa chọn, đừng quên giới hạn độ dài ngoài regex.

### 8.3. Dùng lớp ký tự phủ định đến dấu phân cách

Nếu yêu cầu một trường không chứa dấu phẩy:

~~~regex
[^,]{1,40}
~~~

mô tả trực tiếp quy tắc tốt hơn:

~~~regex
.{1,40}
~~~

vì dấu chấm vẫn cho phép dấu phẩy. Nếu trường được xác thực toàn bộ bằng **matches()**, cả hai mẫu đều kiểm tra độ dài, nhưng chỉ mẫu thứ nhất cấm dấu phẩy.

Khi dùng **[^,]**, nhớ rằng lớp phủ định này vẫn có thể chứa xuống dòng. Nếu dữ liệu bắt buộc nằm trên một dòng, loại trừ thêm **\r**, **\n** bằng lớp ký tự tương ứng (trong Java String literal phải escape dấu gạch chéo ngược đúng cách).

### 8.4. Tách parsing có cấu trúc khỏi regex

Regex rất hữu ích để nhận dạng đoạn tuyến tính đơn giản, nhưng không nên cố xử lý hoàn chỉnh HTML, XML, JSON hoặc cú pháp lồng sâu bằng một mẫu **<.*?>** hay cấu trúc tương tự. Trong trường hợp đó, parser chuyên dụng sẽ kiểm soát cấu trúc tốt hơn và thường cho thông báo lỗi rõ hơn.

Với bài toán tìm một chuỗi cố định, API **String.contains()**, **indexOf()**, **startsWith()**, **endsWith()** có thể đơn giản và dễ dự đoán hơn regex. Với dữ liệu giới hạn rõ bằng một delimiter, cân nhắc parser hoặc thao tác chuỗi thay vì tạo regex có nhiều nhánh chồng lấn.

## 9. Đầu vào không tin cậy và giới hạn tài nguyên

Ngay cả regex đã được xem xét vẫn cần giới hạn input khi chạy trong dịch vụ:

1. **Đặt giới hạn chiều dài input trước khi match.** Giới hạn phải xuất phát từ nghiệp vụ: chẳng hạn mã tài khoản không nên dài hàng nghìn ký tự. **String.length()** đo đơn vị UTF-16; nếu chính sách yêu cầu số Unicode code point hoặc byte, phải đo theo đúng đơn vị đó.
2. **Không cho phép người dùng cung cấp regex tùy ý** nếu chỉ cần tìm chuỗi văn bản. Nếu input người dùng là **literal**, dùng **Pattern.quote(userText)**, hoặc thao tác chuỗi không qua regex. Regex do người dùng tự thiết kế cần kiểm soát riêng về độ phức tạp.
3. **Tạo bộ test input gần khớp nhưng thất bại ở cuối**, các đoạn lặp dài, dấu phân cách bị thiếu, dữ liệu nhiều dòng và dữ liệu dài tới giới hạn hợp lệ. Test đúng ở input ngắn chưa chứng minh được an toàn.
4. **Quan sát thời gian, CPU, tỉ lệ timeout của request** và hạn chế số tác vụ xử lý đồng thời nếu regex nằm trên đường xử lý truy cập từ bên ngoài.
5. **Đừng nhầm giới hạn thời gian request với khả năng cắt ngang regex ngay lập tức.** Java **Matcher** không có tham số timeout riêng cho từng phép match; **Thread.interrupt()** hoặc **Future.cancel(true)** không phải bảo đảm chung rằng một phép regex đang chạy sẽ dừng đúng thời điểm. Nếu xử lý regex tùy ý không tin cậy, cần ranh giới cô lập và cơ chế kiểm soát tài nguyên thực sự, ngoài việc tối ưu mẫu.

**Biên độ an toàn phải tính bằng dữ liệu xấu nhất dự kiến**, chứ không chỉ dựa trên tốc độ trên vài chuỗi thử nghiệm ngắn. Độ dài input có giới hạn là một lớp bảo vệ quan trọng, nhưng không biến mọi regex thành an toàn.

### 9.1. Pattern.quote dùng cho literal

~~~java
String requested = "a.b"; // Người dùng muốn tìm chính xác dấu chấm
Pattern literal = Pattern.compile(Pattern.quote(requested));

System.out.println(literal.matcher("x a.b y").find()); // true
System.out.println(literal.matcher("x acb y").find()); // false
~~~

Nếu không quote, dấu **.** trong regex mang nghĩa wildcard và có thể khiến **acb** được nhận nhầm. **Pattern.quote** giúp biểu diễn đúng literal; không phải giải pháp cho một regex phức tạp do lập trình viên tự viết.

### 9.2. Biên dịch lại Pattern không giải quyết backtracking

**Pattern** là đối tượng immutable, an toàn để nhiều luồng dùng chung; **Matcher** giữ trạng thái và không an toàn khi chia sẻ đồng thời. Biên dịch **Pattern** một lần rồi tạo Matcher mới cho từng input giúp tránh chi phí biên dịch lại, nhưng **không làm mất rủi ro backtracking của biểu thức**.

~~~java
private static final Pattern CODE =
        Pattern.compile("[A-Z][A-Z0-9_]{2,15}");

// Trong một phương thức xử lý từng yêu cầu:
boolean accepted = CODE.matcher(candidate).matches();
~~~

Đoạn trên chỉ minh họa cách tái sử dụng Pattern; **candidate** cần là String đầu vào thực tế và lớp xử lý vẫn phải đặt giới hạn theo nghiệp vụ.

## 10. Đánh giá và kiểm thử hiệu năng có kiểm soát

Đo thời gian là công cụ hỗ trợ, không nên dùng một con số đơn lẻ để khẳng định một regex không có ReDoS.

Một quy trình kiểm tra hợp lý:

- Soạn nhóm **positive cases** (phải khớp) và **negative cases** (không được khớp) để bảo vệ ngữ nghĩa.
- Xây các **near-miss cases** dài dần, nhất là chuỗi lặp nhiều lần rồi có ký tự phá hỏng tại cuối. Kiểm tra trên input nhỏ trước để tránh vô tình treo tiến trình thử nghiệm.
- Theo dõi xu hướng thời gian khi tăng độ dài; nếu thời gian tăng đột biến trong khi input chỉ tăng nhẹ, xem lại các lượng từ lồng nhau, alternation chồng lấn hoặc lookaround phức tạp.
- Chạy benchmark trong môi trường kiểm soát với giới hạn tài nguyên, warm-up JVM và nhiều lần đo; **System.nanoTime()** chỉ là phép đo thời gian, không có khả năng cắt phép match đang kẹt.
- So sánh đồng thời **tập kết quả** của mẫu cũ và mẫu mới: tối ưu thành công khi vừa đúng nghiệp vụ vừa có đặc tính hiệu năng tốt hơn trên nhóm input đáng quan tâm.

Không đưa mẫu khả nghi vào endpoint công khai để đo trực tiếp và không sử dụng input dài nguy hiểm trong ví dụ học cơ bản. Một regex gây treo một thread trên dữ liệu thử không chứng minh được JVM “lỗi”; nó cho thấy cần thiết kế lại mẫu và giới hạn tài nguyên.

## 11. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng **.*** để “bắt mọi thứ” | Nuốt qua nhiều dấu phân cách hoặc phần không mong muốn | Dùng lớp ký tự cụ thể như **[^,]* **, giới hạn độ dài |
| Dùng **find()** để xác thực toàn chuỗi | Chấp nhận input có đoạn con hợp lệ nhưng toàn bộ không hợp lệ | Dùng **matches()** |
| Cho rằng **.*?** luôn nhanh | Vẫn có thể mở rộng và backtrack | Thu hẹp lớp ký tự và loại bỏ nhánh mơ hồ |
| Lặp chồng **(a+)+** hoặc alternation chồng **(a|aa)+** | Nhiều đường phân tích khi near-miss | Viết lại thành **a+** khi cùng ngữ nghĩa |
| Chuyển toàn bộ **+** sang **++** | Loại bỏ các kết quả vốn hợp lệ | Chỉ dùng possessive khi chứng minh không cần trả ký tự |
| Quên dấu phân cách/độ dài | Regex khớp rộng, dữ liệu vượt kỳ vọng | Ràng buộc biên và kiểm tra chiều dài input |
| Ghép thẳng input người dùng vào regex | Metacharacter làm đổi ý nghĩa mẫu | Dùng **Pattern.quote** nếu input là literal |
| Dựa vào timeout request để chặn regex đang chạy | Có thể vẫn chiếm tài nguyên sau khi request hết hạn | Thiết kế regex an toàn và có giới hạn tài nguyên phù hợp |
| Chỉ test các chuỗi khớp | Không phát hiện tình huống quay lui khi thất bại | Test input near-miss và chiều dài tăng dần |

## 12. Checklist chọn mẫu trước khi đưa vào chương trình

- [ ] Mình đã định nghĩa rõ đầu vào hợp lệ, bao gồm chuỗi rỗng và ký tự Unicode nếu liên quan?
- [ ] Mình dùng **matches()**, **lookingAt()** hay **find()** phù hợp phạm vi yêu cầu?
- [ ] Có thể thay **.*** hoặc **.+** bằng lớp ký tự cụ thể, dấu phân cách và độ dài có biên?
- [ ] Các nhánh alternation có chồng lấn không? Có lượng từ lồng nhau cùng ăn một loại ký tự không?
- [ ] Nếu dùng possessive hoặc atomic group, đã kiểm tra không làm mất trường hợp khớp hợp lệ?
- [ ] Đã test input gần đúng nhưng thất bại tại cuối và input sát giới hạn kích thước?
- [ ] Đã đặt giới hạn đầu vào và xem xét cách bảo vệ CPU/thread khi input không tin cậy?
- [ ] Nếu dữ liệu có cấu trúc lồng nhau, parser chuyên dụng có phù hợp hơn?

**Ghi nhớ:** chọn mẫu **cụ thể về ký tự, giới hạn, dấu phân cách và điểm bắt đầu/kết thúc**. Hạn chế nhiều cách phân tích cùng một chuỗi; khi cần hiệu năng tốt, **đơn giản hóa ngữ pháp trước, dùng possessive/atomic đúng chỗ sau, rồi kiểm chứng trên dữ liệu đúng và dữ liệu xấu**.

### Tài liệu tham khảo

- Java SE 21 API, **java.util.regex.Pattern**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html
- OWASP, **Regular expression Denial of Service (ReDoS)**: https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS
