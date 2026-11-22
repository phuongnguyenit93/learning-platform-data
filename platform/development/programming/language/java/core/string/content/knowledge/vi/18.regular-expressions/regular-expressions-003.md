# Matcher.matches(), find() và lookingAt() trong Java

## 1. Mục tiêu và bối cảnh

Khi xử lý **biểu thức chính quy (regular expression, regex)**, Java tách hai vai trò:

- **Pattern**: biểu thức đã được biên dịch; có thể tái sử dụng.
- **Matcher**: đối tượng giữ chuỗi đầu vào, vùng tìm kiếm, vị trí và kết quả khớp hiện tại. Tạo bằng **pattern.matcher(input)**.

Ba phương thức **Matcher.matches()**, **Matcher.lookingAt()** và **Matcher.find()** đều trả về **boolean**, nhưng câu hỏi chúng trả lời khác nhau:

- **matches()**: *Toàn bộ vùng đang xét có khớp regex không?*
- **lookingAt()**: *Regex có khớp ngay từ đầu vùng đang xét không?*
- **find()**: *Có đoạn con nào khớp regex kể từ vị trí tìm kiếm hiện tại không?*

“Vùng đang xét” (region) mặc định là toàn bộ chuỗi đầu vào. Matcher có thể giới hạn vùng bằng **region(start, end)**; vì thế mô tả chính xác là “toàn bộ vùng” thay vì luôn luôn “toàn bộ String”.

## 2. So sánh nhanh

| Phương thức | Bắt buộc bắt đầu tại đầu region? | Bắt buộc kết thúc tại cuối region? | Tìm nhiều lần liên tiếp? | Mục đích điển hình |
| --- | --- | --- | --- | --- |
| **matches()** | Có | Có | Không; mỗi lần kiểm tra khớp toàn vùng | Kiểm tra một giá trị có hợp lệ theo mẫu |
| **lookingAt()** | Có | Không | Không; kiểm tra tiền tố của region | Nhận diện tiền tố, token ở đầu |
| **find()** | Không | Không | Có; gọi liên tiếp để duyệt các kết quả | Trích xuất các phần khớp trong văn bản |

Ví dụ với regex **cat**:

| Chuỗi đầu vào | matches() | lookingAt() | find() |
| --- | --- | --- | --- |
| cat | true | true | true |
| cat nap | false | true | true |
| a cat | false | false | true |
| dog | false | false | false |

**Lưu ý:** cả ba chỉ biết regex, không biết ý nghĩa nghiệp vụ. Regex **cat** có thể tìm thấy trong **scatter** nếu không ràng buộc ranh giới từ; muốn khớp cả từ thì dùng **\bcat\b** (viết trong Java là **"\\bcat\\b"**).

## 3. Ví dụ Java 17+ chạy độc lập

Tạo tệp **MatcherOperationsDemo.java**:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MatcherOperationsDemo {
    public static void main(String[] args) {
        String input = "ID=42; ID=7";
        Pattern pattern = Pattern.compile("ID=(\\d+)");

        Matcher whole = pattern.matcher(input);
        System.out.println("matches: " + whole.matches());

        Matcher prefix = pattern.matcher(input);
        System.out.println("lookingAt: " + prefix.lookingAt());
        System.out.println("prefix id: " + prefix.group(1));

        Matcher scan = pattern.matcher(input);
        while (scan.find()) {
            System.out.printf(
                    "find: %s, id=%s, range=[%d,%d)%n",
                    scan.group(), scan.group(1), scan.start(), scan.end());
        }

        System.out.println("find after loop: " + scan.find());
        System.out.println("find after reset: " + scan.reset().find());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MatcherOperationsDemo.java
java MatcherOperationsDemo
~~~

Kết quả chuẩn:

~~~text
matches: false
lookingAt: true
prefix id: 42
find: ID=42, id=42, range=[0,5)
find: ID=7, id=7, range=[7,11)
find after loop: false
find after reset: true
~~~

Giải thích:

1. **matches() = false** vì **ID=42** chỉ khớp đoạn đầu; phần **; ID=7** còn lại khiến toàn bộ chuỗi không khớp.
2. **lookingAt() = true** vì chuỗi mở đầu bằng **ID=42**; phương thức không yêu cầu phần sau cũng khớp.
3. **find()** tìm lần thứ nhất ở đoạn **[0, 5)** và lần thứ hai ở **[7, 11)**. Chỉ số **end()** là vị trí *ngay sau* ký tự cuối cùng của phần khớp.
4. Hết các đoạn khớp, **find()** trả **false**. **reset()** đưa Matcher về trạng thái ban đầu nên tìm lại được từ đầu.

Ví dụ dùng **ba Matcher độc lập** để mỗi phép thử không bị ảnh hưởng bởi vị trí hoặc kết quả của phép thử trước. Có thể tái sử dụng **Pattern**, nhưng một Matcher có trạng thái thay đổi sau mỗi thao tác.

## 4. matches(): kiểm tra khớp toàn bộ region

~~~java
Pattern digits = Pattern.compile("\\d+");

System.out.println(digits.matcher("12345").matches());  // true
System.out.println(digits.matcher("a12345").matches()); // false
System.out.println(digits.matcher("12345a").matches()); // false
System.out.println(digits.matcher("").matches());       // false
~~~

**matches()** cố gắng làm cho regex bao phủ toàn bộ region. Vì vậy:

- Với region là toàn chuỗi, regex **\\d+** chấp nhận chuỗi chỉ gồm ít nhất một chữ số ASCII thông thường theo cách dùng regex này.
- Regex **\\d+** không cần thêm **^** và **$** để làm cho **matches()** kiểm tra toàn region.
- Nếu chỉ muốn tìm một dãy số ở đâu đó bên trong văn bản, dùng **find()** thay vì nới regex thành **.*\\d+.*** một cách máy móc.
- Đừng nhầm **Matcher.matches()** với việc “kiểm tra có một đoạn con khớp”. Nó không hoạt động như phép tìm kiếm một phần.

Hai cách viết tiện ích cũng mang ý nghĩa khớp toàn chuỗi:

~~~java
boolean a = "123".matches("\\d+");
boolean b = Pattern.matches("\\d+", "123");

System.out.println(a); // true
System.out.println(b); // true
~~~

**String.matches(regex)** và **Pattern.matches(regex, input)** phù hợp cho phép kiểm tra đơn lẻ. Khi chạy cùng regex nhiều lần, biên dịch **Pattern** một lần rồi tạo Matcher mới cho từng input để tránh biên dịch lặp không cần thiết.

## 5. lookingAt(): nhận diện một tiền tố

**lookingAt()** bắt buộc regex bắt đầu tại đầu region, nhưng không yêu cầu đi đến cuối region:

~~~java
Pattern command = Pattern.compile("GET|POST");

System.out.println(command.matcher("GET /users").lookingAt());  // true
System.out.println(command.matcher("POST /users").lookingAt()); // true
System.out.println(command.matcher("X GET /users").lookingAt());// false
~~~

Giá trị trả về cho biết **một tiền tố** khớp; nó không kiểm tra token có kết thúc đúng ranh giới hay không. Chẳng hạn regex **GET|POST** cũng khớp tiền tố trong **GETAWAY**. Nếu cần phân biệt lệnh **GET** đứng độc lập, phải bổ sung ranh giới phù hợp, ví dụ **(?:GET|POST)\b** cho token dạng từ hoặc thiết kế mẫu bao gồm dấu phân cách.

Khi thành công, **group()**, **start()**, **end()** cho biết tiền tố được khớp, để chương trình có thể tiếp tục xử lý phần văn bản phía sau.

**lookingAt()** luôn thử từ đầu region, kể cả khi Matcher từng có phép tìm kiếm khác. Tuy nhiên, để so sánh ba phương thức công bằng và dễ hiểu, hãy dùng Matcher riêng hoặc gọi **reset()** giữa các kịch bản độc lập.

## 6. find(): quét và trích xuất nhiều đoạn khớp

**find()** tìm một đoạn con khớp từ vị trí tìm kiếm hiện tại; khi thành công, lần gọi **find()** tiếp theo tiếp tục sau phần vừa khớp. Trường hợp phổ biến:

~~~java
Pattern number = Pattern.compile("\\d+");
Matcher matcher = number.matcher("A12 B345 C6");

while (matcher.find()) {
    System.out.println(matcher.group());
}
~~~

Output:

~~~text
12
345
6
~~~

**find()** thường dùng cho log, văn bản tự do, trích ID, tìm token hoặc các lần xuất hiện của một mẫu. Mỗi lần **find()** thành công, thông tin kết quả mới thay thế kết quả khớp trước đó.

### 6.1. find(int start) và reset()

Biến thể **find(int start)** bắt đầu tìm từ một chỉ số được chỉ định trong **chuỗi đầu vào** và **reset Matcher trước khi tìm**:

~~~java
Matcher m = Pattern.compile("aba").matcher("ababa");

System.out.println(m.find());    // true: [0,3)
System.out.println(m.start());   // 0
System.out.println(m.find());    // false (không quét chồng lên đoạn đã khớp)

System.out.println(m.find(2));   // true: [2,5)
System.out.println(m.start());   // 2
~~~

Phần khớp **aba** thứ hai bắt đầu ở chỉ số 2, nhưng chồng lên phần đầu. **find()** tuần tự không trả về các kết quả chồng lấn theo mặc định. **find(2)** là một cách chủ động bắt đầu một phép tìm kiếm mới từ chỉ số 2; đây không phải hành vi tự động tìm mọi vị trí chồng lấn.

**find(int start)** gọi logic reset nên không nên giả định nó giữ nguyên region tùy chỉnh hay trạng thái tìm kiếm trước đó. Nếu cần region cụ thể, thiết lập lại region sau khi reset hoặc thiết kế Matcher mới.

### 6.2. Mẫu khớp chuỗi rỗng

Một số regex có thể khớp **độ dài 0**, ví dụ **a*** hoặc ranh giới từ **\b**. Khi ấy **start() == end()**. Matcher có cơ chế tiến vị trí tìm kiếm để vòng **while (find())** không lặp mãi tại một vị trí rỗng, nhưng kết quả có thể gồm các lần khớp rỗng mà ứng dụng không muốn.

Nếu cần trích nội dung thực sự có ký tự, hãy xác định regex có cho phép độ dài 0 hay không; ví dụ **\\d+** cần ít nhất một chữ số, còn **\\d*** cho phép cả chuỗi rỗng.

## 7. Kết quả khớp, capturing group và trạng thái Matcher

Sau **một phép khớp thành công** của bất kỳ phương thức nào:

- **group()** hoặc **group(0)**: toàn bộ đoạn khớp.
- **group(1)**, **group(2)**, ...: giá trị của các *capturing group* đánh số từ 1 theo dấu ngoặc bắt nhóm trong regex.
- **start()**, **end()**: chỉ số đầu và chỉ số sau cuối của toàn bộ đoạn khớp; có biến thể **start(group)**, **end(group)**.
- Các chỉ số dùng offset theo **đơn vị UTF-16** của Java String, không nhất thiết trùng số ký tự người đọc nhìn thấy khi có emoji hoặc ký tự bổ sung Unicode.

Ví dụ nhóm bắt:

~~~java
Pattern p = Pattern.compile("([A-Z]+)-(\\d+)");
Matcher m = p.matcher("x AB-12 y");

if (m.find()) {
    System.out.println(m.group());  // AB-12
    System.out.println(m.group(1)); // AB
    System.out.println(m.group(2)); // 12
    System.out.println(m.start());  // 2
    System.out.println(m.end());    // 7
}
~~~

Nếu nhóm là **tùy chọn và không tham gia phép khớp**, **group(n)** trả **null**, còn **start(n)** và **end(n)** trả **-1**. Kết quả khác với nhóm có tham gia nhưng khớp chuỗi rỗng, khi đó **group(n)** là **""**.

**Rất quan trọng:** không được gọi **group()**, **start()**, **end()** để lấy kết quả khi chưa có phép khớp thành công hoặc ngay sau một phép khớp thất bại; Java sẽ ném **IllegalStateException**. Hãy kiểm tra boolean trước:

~~~java
Matcher m = Pattern.compile("\\d+").matcher("abc");

if (m.find()) {
    System.out.println(m.group());
} else {
    System.out.println("Không tìm thấy số");
}
~~~

Một nhóm vượt quá số nhóm bắt hợp lệ cũng gây lỗi chỉ số nhóm. Ngoài ra, dùng **(?:...)** khi chỉ cần nhóm cú pháp mà không cần lấy dữ liệu.

**Matcher không an toàn để chia sẻ đồng thời giữa nhiều thread** vì mang trạng thái mutable. **Pattern** có thể chia sẻ giữa các thread; mỗi luồng hoặc mỗi tác vụ nên tạo Matcher riêng.

## 8. region(), anchor và flag: những điểm dễ hiểu sai

### 8.1. region(start, end) thay đổi phạm vi kiểm tra

~~~java
Matcher m = Pattern.compile("\\d+")
        .matcher("xx123yy")
        .region(2, 5);

System.out.println(m.matches()); // true
System.out.println(m.start());   // 2
System.out.println(m.end());     // 5
~~~

Ở đây input gốc là **xx123yy**, nhưng region **[2,5)** chỉ chứa **123**, nên **matches()** đúng. **start()** và **end()** vẫn là offset trong input gốc.

Region cũng chi phối điểm bắt đầu của **lookingAt()** và phạm vi tìm của **find()**. Mặc định Matcher dùng **anchoring bounds = true**, cho phép **^**, **$** nhận biên region là ranh giới; **transparent bounds = false** khiến một số phép nhìn trước/nhìn sau và biên từ không nhìn xuyên qua region. Khi regex dựa vào lookaround/anchor tại biên region, có thể cần hiểu **useAnchoringBounds(...)** và **useTransparentBounds(...)**.

### 8.2. ^, $, MULTILINE và DOTALL không biến ba phương thức thành nhau

- **^** và **$** là anchor trong **regex**. **matches()** tự đòi hỏi phủ toàn region dù không ghi anchor.
- **Pattern.MULTILINE** thay đổi ý nghĩa anchor **^** và **$** để chúng còn có thể gắn với ranh giới dòng; nó **không** biến **matches()** thành tìm một dòng tùy ý trong toàn input.
- **Pattern.DOTALL** cho phép dấu **.** khớp cả ký tự xuống dòng; nếu regex **a.b** dùng với **matches()** trên **"a\nb"**, kết quả mặc định là **false** nhưng có thể là **true** khi bật DOTALL.

Ví dụ tách rõ regex, mode và phương thức:

~~~java
String lines = "one\ntwo";
Pattern p = Pattern.compile("^two$", Pattern.MULTILINE);

System.out.println(p.matcher(lines).find());    // true
System.out.println(p.matcher(lines).matches()); // false
~~~

**find()** tìm được dòng thứ hai nhờ MULTILINE cho **^two$**. **matches()** vẫn đòi hỏi toàn region từ **one** đến **two** phải khớp.

### 8.3. Dấu gạch chéo ngược trong regex Java

Java String literal và cú pháp regex đều dùng dấu **\**. Để regex engine nhận **\d+**, mã Java phải ghi **"\\d+"**. Tương tự, regex ranh giới từ **\b** phải viết trong Java là **"\\b"**; viết **"\b"** sẽ tạo ký tự backspace ở tầng Java String và làm regex có nghĩa khác.

## 9. Chọn phương thức phù hợp theo bài toán

| Bài toán | Nên dùng | Lý do |
| --- | --- | --- |
| Kiểm tra mã chỉ được gồm chữ số | **matches()** với regex **\\d+** | Không cho phép ký tự dư ở đầu/cuối |
| Kiểm tra đầu câu lệnh có token hợp lệ | **lookingAt()** với regex và ranh giới token | Chỉ yêu cầu khớp từ đầu |
| Lấy mọi số trong nội dung log | Vòng lặp **while (find())** | Quét từng đoạn con khớp |
| Xem văn bản có chứa ít nhất một email theo mẫu | **find()** | Chỉ cần một đoạn con phù hợp |
| Kiểm tra toàn bộ giá trị nhập theo một định dạng | **matches()** | Mọi ký tự trong region phải được regex bao phủ |

Đối với kiểm tra dữ liệu nghiệp vụ, regex mới chỉ xác minh **cú pháp**. Ví dụ ngày tháng khớp dạng **\\d{4}-\\d{2}-\\d{2}** vẫn có thể là ngày không tồn tại; cần thêm kiểm tra giá trị bằng API phù hợp.

## 10. Sai lầm thường gặp và cách tự kiểm tra

1. **Dùng matches() rồi ngạc nhiên khi false.** Xem có ký tự thừa hoặc xuống dòng không; nếu muốn tìm đoạn con hãy thử **find()**, nếu muốn tiền tố hãy thử **lookingAt()**.
2. **Dùng lookingAt() để xác thực trọn input.** Nó có thể trả true cho chuỗi có phần đuôi không hợp lệ. Dùng **matches()** nếu cần hợp lệ toàn bộ.
3. **Chỉ gọi find() một lần dù cần tất cả kết quả.** Dùng vòng **while (matcher.find())**; mỗi lần đọc **group()** ngay trong lần lặp đó.
4. **Đọc group() sau khi find() trả false.** Không còn kết quả khớp hợp lệ cho lần kiểm tra vừa thất bại; chỉ đọc thông tin match trong nhánh boolean true.
5. **Tái sử dụng Matcher mà quên vị trí hiện tại.** Gọi **reset()** hoặc tạo Matcher mới trước một kịch bản độc lập; một **Pattern** có thể tái sử dụng.
6. **Muốn tìm các kết quả chồng lấn nhưng dùng find() liên tục.** Kết quả tuần tự mặc định không chồng lấn; cần thiết kế tìm kiếm từ vị trí thích hợp hoặc dùng lookahead tùy bài toán.
7. **Nhầm \d với chuỗi Java "\\d" hoặc quên escape.** Kiểm tra từng tầng Java string và regex; nếu tạo regex từ input người dùng, cân nhắc **Pattern.quote(...)** khi muốn hiểu input là văn bản thường.
8. **Nghĩ ^ và $ luôn tương đương matches().** Anchor chịu ảnh hưởng bởi MULTILINE, region và các ranh giới; **matches()** có điều kiện phủ toàn region riêng.

## 11. Ghi nhớ qua ba câu hỏi

Với một **Pattern** đã biên dịch và một **Matcher** trên input/region:

- **“Cả vùng có hợp lệ theo mẫu không?” → matches().**
- **“Vùng có bắt đầu bằng mẫu này không?” → lookingAt().**
- **“Ở đâu trong vùng có một đoạn khớp, và có bao nhiêu đoạn?” → find().**

Khi phép khớp thành công, khai thác **group/start/end** ngay lúc đó; khi cần kiểm tra độc lập, bắt đầu bằng Matcher mới hoặc **reset()**. Sự khác nhau cốt lõi là **phạm vi phải bao phủ và vị trí bắt đầu**, không phải ba kiểu cú pháp regex khác nhau.
