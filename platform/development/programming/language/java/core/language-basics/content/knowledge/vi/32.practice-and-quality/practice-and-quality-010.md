# Tổng hợp lỗi thường gặp và tiêu chí tự đánh giá nền tảng Java Core

Biết cú pháp Java chỉ là bước đầu. Năng lực nền tảng còn thể hiện ở việc dự đoán được chương trình chạy như thế nào, phát hiện lỗi biên dịch, lỗi khi chạy và lỗi logic, giải thích nguyên nhân rồi kiểm chứng cách sửa. Bài này hệ thống hóa những sai sót phổ biến khi học **Java 17+ (language-basics)** và đưa ra tiêu chí tự đánh giá cụ thể, có thể thực hành độc lập.

## 1. Phân biệt ba loại lỗi trước khi sửa

| Loại | Dấu hiệu | Ví dụ | Cách tiếp cận |
| --- | --- | --- | --- |
| **Lỗi biên dịch (compile-time)** | `javac` báo lỗi, chưa có chương trình hợp lệ để chạy | Thiếu `;`, sai kiểu, gọi phương thức không tồn tại, dùng biến chưa khai báo | Đọc dòng/cột và thông báo đầu tiên; sửa nguyên nhân, biên dịch lại |
| **Lỗi khi chạy (runtime)** | Đã biên dịch nhưng một luồng thực thi ném ngoại lệ hoặc kết thúc bất thường | `NullPointerException`, `ArrayIndexOutOfBoundsException`, `NumberFormatException` | Đọc loại ngoại lệ và stack trace; kiểm tra dữ liệu thực tế, xác định đường chạy |
| **Lỗi logic** | Chương trình chạy xong nhưng kết quả sai | Chia nguyên khi cần thập phân, dùng `<` thay `<=`, tính tổng bị tràn `int` | Viết đầu ra mong đợi, thử giá trị biên, so sánh kết quả và lần theo biến |

Ngoài ra còn có **lỗi thiết kế/khả năng bảo trì**: tên mơ hồ, phương thức quá dài, lặp quy tắc, trộn trách nhiệm, hoặc xử lý lỗi không nhất quán. Chúng có thể chưa gây ra kết quả sai ngay nhưng làm tăng rủi ro khi sửa đổi.

Khi gặp lỗi, hãy xác định **đầu vào → điều kiện/biểu thức → kết quả thực tế → kết quả mong đợi**. Tránh sửa nhiều chỗ cùng lúc rồi không biết thay đổi nào có tác dụng.

## 2. Các lỗi phổ biến theo nhóm kiến thức

### 2.1. JDK, tệp mã nguồn và cách chạy

- Nhầm **JDK** với **JRE**: muốn biên dịch cần `javac` từ JDK; `java` dùng chạy chương trình. Kiểm tra phiên bản của cả hai.
- Không khớp tên tệp với lớp `public` cấp cao: `public class Hello` phải nằm trong `Hello.java`; Java phân biệt hoa/thường trong định danh.
- Sai điểm khởi động: với chương trình cơ bản, phương thức chạy là `public static void main(String[] args)`; thiếu `static` hoặc sai chữ ký khiến JVM không nhận đúng entry point.
- Gọi `java Hello.java` và `java Hello` là **hai cơ chế khác nhau**. Lệnh `java Hello` chạy lớp đã biên dịch; lệnh `java Hello.java` có thể chạy trực tiếp tệp nguồn ở JDK hỗ trợ source-file mode.
- Sai `package` hoặc classpath: nếu tệp khai báo `package demo;`, biên dịch tại thư mục gốc nguồn bằng `javac -d out demo/Hello.java` rồi chạy `java -cp out demo.Hello`, không chạy `java Hello`.

Ví dụ độc lập (không khai báo `package`) lưu ở `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 Hello.java
java Hello
```

Stdout:

```text
Hello Java
```

Nếu báo lỗi “cannot find symbol”, không nên chỉ thay đường dẫn chạy: lỗi này thường là **biên dịch** vì một tên/kiểu không được nhận ra. Nếu “Could not find or load main class”, kiểm tra tên lớp, thư mục hiện tại, package và classpath.

### 2.2. Kiểu dữ liệu, biểu thức và chuyển đổi

| Sai sót | Điều gì thực sự xảy ra | Cách sửa hoặc kiểm tra |
| --- | --- | --- |
| `5 / 2` được kỳ vọng là `2.5` | Hai `int` chia nguyên, kết quả `2` | `5 / 2.0` hoặc `(double) 5 / 2` |
| `double ratio = a / b;` với `a,b` là `int` | Chia nguyên **trước khi** gán sang `double` | Ép kiểu trước phép chia: `(double) a / b` |
| Ép `long` sau phép nhân hai `int` | Tích có thể đã bị tràn `int` | `(long) a * b` hoặc `Math.multiplyExact` để phát hiện tràn |
| Nhầm `=` và `==` | `=` gán, `==` so sánh giá trị với primitive | Viết điều kiện rõ ràng; tránh gán trong điều kiện |
| Đánh giá sai thứ tự `&&`/`||` | `&&` có độ ưu tiên cao hơn `||` | Thêm ngoặc thể hiện ý định và kiểm thử nhánh |
| Dùng `&` thay `&&` với boolean | `&` đánh giá cả hai vế; `&&` có short-circuit | Với kiểm tra null, dùng `s != null && ...` |
| Tin `final` làm toàn bộ đối tượng bất biến | `final` ngăn gán lại biến/tham chiếu, không khóa trạng thái đối tượng | Phân biệt final với immutable object |
| Hiểu `var` là kiểu động | `var` suy luận kiểu tĩnh cho biến cục bộ có initializer | Giá trị gán tiếp vẫn phải hợp kiểu đã suy luận |

Chẳng hạn, `(long) (a * b)` vẫn có thể sai vì tích `int` được tính trong ngoặc trước khi ép kiểu. Với tính toán tiền tệ có số lẻ, cần quy tắc về đơn vị và làm tròn; `double` không mặc nhiên phù hợp với kết quả thập phân chính xác.

### 2.3. Rẽ nhánh, vòng lặp và phạm vi

- **Sai một đơn vị (off-by-one):** mảng dài `n` có các chỉ số `0` đến `n - 1`. Dùng `i < array.length` khi đi hết mảng, tránh `i <= array.length`.
- **Dấu ngoặc nhọn thiếu:** thụt lề không quyết định khối lệnh; sau `if` không có `{}`, chỉ một statement thuộc nhánh đó.
- **Điều kiện vòng lặp không tiến tới dừng:** quên tăng/giảm biến đếm, hoặc thay đổi nhầm biến điều khiển.
- **Đổi `if` riêng lẻ thành `if/else if` mà không xét ý nghĩa:** các `if` độc lập có thể cùng đúng, chuỗi `else if` chỉ chọn một nhánh.
- **Quên `break` trong `switch` kiểu cũ:** thực thi có thể rơi xuống các `case` tiếp theo; dạng `case X ->` trong Java 17 tránh kiểu fall-through này.
- **Đóng/mở biên sai:** `score >= 50` khác `score > 50`; bắt buộc thử điểm `49`, `50`, `51`.

Đoạn dưới **là mã minh họa trong một phương thức**, không phải chương trình độc lập:

```java
for (int i = 0; i < numbers.length; i++) {
    System.out.println(numbers[i]);
}

if (score >= 50) {
    System.out.println("PASS");
} else {
    System.out.println("FAIL");
}
```

Khi đọc điều kiện, xác định rõ giá trị ở ranh giới và xem có nhánh nào không thể chạy vì thứ tự điều kiện đã bao phủ toàn bộ miền giá trị hay không.

### 2.4. Chuỗi, mảng, null và tham chiếu

- `==` so sánh **giá trị primitive** hoặc **cùng đối tượng tham chiếu**; để so nội dung `String`, dùng `equals`. `"Java" == new String("Java")` thường không cho kết quả muốn tìm dù hai chuỗi có cùng ký tự.
- `String` bất biến: `text.trim()`, `text.strip()`, `text.replace(...)` trả **chuỗi mới**; muốn giữ thay đổi phải gán lại hoặc chuyển giá trị trả về.
- `null`, chuỗi rỗng `""`, và chuỗi trắng `"   "` không đồng nghĩa. `isEmpty()` kiểm tra độ dài bằng 0; `isBlank()` kiểm tra rỗng hoặc chỉ chứa ký tự khoảng trắng theo quy tắc Java.
- Kiểm tra null trước khi gọi phương thức: `name != null && !name.isBlank()` an toàn nhờ short-circuit; đảo thứ tự có thể gây `NullPointerException`.
- Mảng dùng thuộc tính `length`; `String` dùng phương thức `length()`. Độ dài `String` đếm đơn vị mã UTF-16; không đồng nhất với số ký tự người dùng nhìn thấy.
- Gán `int[] copy = original;` tạo **bí danh tham chiếu**, không sao chép phần tử. Dùng `original.clone()` hoặc `Arrays.copyOf` nếu muốn bản sao mảng một chiều độc lập.
- Java luôn truyền tham số **theo giá trị**; đối với đối tượng, giá trị được truyền là bản sao của tham chiếu. Do đó phương thức có thể làm đổi trạng thái đối tượng được trỏ tới, nhưng gán lại biến tham số không đổi biến tham chiếu của người gọi.

Một bẫy khi nối chuỗi là tính từ trái sang phải; trong ngữ cảnh phương thức:

```java
System.out.println(1 + 2 + "3");  // 33
System.out.println("3" + 1 + 2);  // 312
```

Trước khi dự đoán stdout, hãy xét kiểu và thứ tự của **từng toán hạng**, không xem toàn biểu thức như một phép cộng số.

### 2.5. Phương thức, ngoại lệ và chất lượng mã

- Không phân biệt tham số (parameter) với đối số (argument), hoặc bỏ quên giá trị trả về của phương thức không làm thay đổi đối tượng gốc.
- Nhầm `static` với thành viên của từng đối tượng. Phương thức `static` không có tham chiếu `this` và không truy cập trực tiếp trường instance nếu thiếu đối tượng.
- Không kiểm tra dữ liệu trước `Integer.parseInt`, đọc chỉ số mảng, hoặc chia nguyên cho `0`. Ngoại lệ không phải kết quả nghiệp vụ hợp lệ.
- Bắt `Exception` rồi bỏ qua lỗi hoặc trả `0` khiến sai dữ liệu giống như thành công; phân biệt lỗi nhập liệu với lỗi lập trình, thông báo rõ và để nơi gọi xử lý phù hợp.
- Đặt tên `a`, `tmp`, `x` cho biến nghiệp vụ, lặp số “ma thuật” như `86400000`, hoặc viết phương thức quá dài làm người khác khó xác định quy tắc. Ưu tiên `timeoutMillis`, `MILLIS_PER_DAY`, các phương thức nhỏ có một nhiệm vụ.
- Viết test chỉ cho dữ liệu thuận lợi. Cần có `null`, chuỗi rỗng, số âm, hai phía giới hạn, dữ liệu sai định dạng, giá trị lớn và các nhánh lỗi liên quan.

## 3. Chương trình Java 17+ tự kiểm tra các lỗi nền tảng

Chương trình sau tạo 9 phép kiểm tra độc lập có tên rõ ràng. Nếu bất cứ kiểm tra nào sai, `AssertionError` làm chương trình thất bại; vì vậy **không cần bật `-ea`**. Lưu tệp `FoundationSelfCheck.java`, không khai báo `package`:

```java
public final class FoundationSelfCheck {
    private static final int PASS_SCORE = 50;
    private static final int MAX_SCORE = 100;
    private static int passed;

    private FoundationSelfCheck() {
    }

    public static void main(String[] args) {
        check("integer division", 5 / 2 == 2 && 5 / 2.0 == 2.5);

        String separateObject = new String("Java");
        check("string equality", "Java".equals(separateObject));

        String originalText = " Java ";
        String strippedText = originalText.strip();
        check("string immutability",
                originalText.equals(" Java ") && strippedText.equals("Java"));

        int[] numbers = {1, 2, 3};
        int sum = 0;
        for (int i = 0; i < numbers.length; i++) {
            sum += numbers[i];
        }
        check("loop bounds", sum == 6);

        check("boundary scores",
                grade(49).equals("FAIL")
                        && grade(50).equals("PASS")
                        && grade(100).equals("PASS"));

        check("empty and null",
                !hasName(null) && !hasName("") && !hasName("   ")
                        && hasName(" Linh "));

        int[] originalArray = {3};
        int[] alias = originalArray;
        alias[0] = 4;
        check("reference alias", originalArray[0] == 4);

        check("integer overflow", detectsOverflow());
        check("invalid score", rejectsScore(-1) && rejectsScore(101));

        System.out.println("Summary: " + passed + "/9 PASS");
    }

    private static String grade(int score) {
        if (score < 0 || score > MAX_SCORE) {
            throw new IllegalArgumentException("score out of range");
        }
        return score >= PASS_SCORE ? "PASS" : "FAIL";
    }

    private static boolean hasName(String name) {
        return name != null && !name.isBlank();
    }

    private static boolean detectsOverflow() {
        try {
            Math.multiplyExact(Integer.MAX_VALUE, 2);
            return false;
        } catch (ArithmeticException exception) {
            return true;
        }
    }

    private static boolean rejectsScore(int score) {
        try {
            grade(score);
            return false;
        } catch (IllegalArgumentException exception) {
            return "score out of range".equals(exception.getMessage());
        }
    }

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name + ": FAIL");
        }
        passed++;
        System.out.println(name + ": PASS");
    }
}
```

Từ thư mục có tệp `FoundationSelfCheck.java`, chạy trên Windows PowerShell/CMD, macOS hoặc Linux với JDK 17+:

```bash
javac -encoding UTF-8 FoundationSelfCheck.java
java FoundationSelfCheck
```

Stdout **chính xác**:

```text
integer division: PASS
string equality: PASS
string immutability: PASS
loop bounds: PASS
boundary scores: PASS
empty and null: PASS
reference alias: PASS
integer overflow: PASS
invalid score: PASS
Summary: 9/9 PASS
```

Chương trình chứng minh một số điểm rất dễ nhầm: `"Java".equals(...)` so nội dung, `strip()` trả chuỗi mới, điều kiện vòng lặp không truy cập quá chỉ số, `null` được kiểm tra an toàn, hai biến mảng có thể cùng trỏ một đối tượng, và `Math.multiplyExact` ném `ArithmeticException` khi phép nhân `int` bị tràn.

Để tự kiểm tra kỹ hơn, hãy **thử thay đổi có chủ đích** trong một bản sao: đổi `i < numbers.length` thành `i <= numbers.length`, đổi `grade(50)` sang điều kiện `score > PASS_SCORE`, hoặc bỏ `name != null &&`. Quan sát ngoại lệ hay thông báo thất bại và giải thích vì sao. Sau đó khôi phục mã đúng. Không nên dùng những phiên bản cố ý sai này trong ứng dụng thực tế.

## 4. Bộ tiêu chí tự đánh giá nền tảng

Chấm mỗi tiêu chí theo cùng một thang: **0 điểm** = chưa làm được hoặc chỉ đoán; **1 điểm** = làm được với tài liệu/gợi ý nhưng chưa giải thích được đầy đủ; **2 điểm** = tự giải thích, viết và kiểm tra ví dụ đúng không cần gợi ý. Tổng tối đa **24 điểm**.

| STT | Tiêu chí | Bằng chứng thực hành để tự chấm |
| --- | --- | --- |
| 1 | JDK và vòng đời chạy chương trình | Biên dịch/chạy bằng `javac` và `java`; giải thích tệp `.java`/`.class`, tên lớp, main, package |
| 2 | Cú pháp, quy ước tên và phạm vi biến | Tạo lớp và phương thức Java hợp lệ; phân biệt biến cục bộ, field và `static`; đặt tên có nghĩa |
| 3 | Kiểu primitive, reference và chuyển kiểu | Giải thích `int`/`long`/`double`/`boolean`/`String`; nhận ra widening/narrowing và nguy cơ mất dữ liệu |
| 4 | Toán tử và thứ tự tính | Tự dự đoán kết quả chia nguyên, nối chuỗi, `&&`, `||`, tăng giảm; dùng ngoặc cho ý định rõ |
| 5 | Điều kiện và xử lý biên | Viết `if/else`, `switch`, kiểm tra mốc ngay dưới/đúng/trên ngưỡng |
| 6 | Vòng lặp và mảng | Duyệt mảng không vượt cận, tính tổng chính xác, giải thích `break`/`continue` |
| 7 | Phương thức và truyền tham số | Tách hàm nhỏ, dùng tham số/return đúng; giải thích Java pass-by-value |
| 8 | String, null và tham chiếu | Dùng `equals`, `isBlank`, tránh NPE, phân biệt alias với bản sao và String immutable |
| 9 | Xử lý đầu vào không hợp lệ | Phân biệt định dạng sai và miền giá trị sai; kiểm tra ngoại lệ có chủ đích |
| 10 | Số lớn và giới hạn kiểu | Giải thích tràn `int`, dùng `long` trước phép toán, `Math.multiplyExact` khi cần |
| 11 | Đọc lỗi và sửa lỗi có căn cứ | Phân loại compile/runtime/logic, dựa vào lỗi và ca tái hiện thay vì đoán |
| 12 | Chất lượng mã và kiểm thử cơ bản | Format nhất quán, tránh magic numbers, dự đoán stdout và kiểm tra ít nhất một ca biên |

**Cách đọc điểm tham khảo:**

- **0–11/24:** cần củng cố cú pháp và khả năng tự biên dịch/chạy các bài nhỏ. Chọn những tiêu chí 0 điểm làm lại từ đầu.
- **12–19/24:** đã có nền tảng nhưng còn lỗ hổng. Tập trung vào tiêu chí 0–1 điểm; sau mỗi lần sửa phải thêm một test thể hiện lỗi cũ.
- **20–24/24:** có cơ sở để tiếp tục bài thực hành phức tạp hơn. Vẫn cần xác nhận năng lực bằng mã tự viết và xử lý dữ liệu bất thường, không chỉ điểm tự chấm.

Thang trên là **rubric học tập**, không phải chứng chỉ hay bảo đảm về năng lực nghề nghiệp. Điểm chỉ có ý nghĩa khi dựa trên bài chạy được và lời giải thích độc lập.

## 5. Bài thực hành tổng hợp để chứng minh mức độ nắm vững

**Đề tự làm:** Viết một chương trình Java đọc (hoặc mô phỏng) danh sách điểm số nguyên từ `0` đến `100`, phân loại đạt khi điểm từ `50` trở lên, tính số lượng đạt và tỷ lệ đạt. Chương trình cần xử lý danh sách rỗng và dữ liệu sai.

**Điều kiện hoàn thành có thể kiểm chứng:**

1. Khi có `[49, 50, 100]`, số lượng đạt phải là `2`, tỷ lệ đạt là `2 / 3.0` (khoảng `66.67%` nếu format hai chữ số thập phân). Không để phép chia nguyên tạo `0` trước khi chuyển thành `double`.
2. Khi danh sách rỗng, không chia cho `0`; trả về `0` theo hợp đồng đã nêu hoặc trạng thái “không có dữ liệu”.
3. Khi gặp `-1` hoặc `101`, chỉ rõ cách từ chối/ghi nhận lỗi; không tự ý sửa thành `0` hoặc `100`.
4. Nếu nhập từ chuỗi, kiểm tra `null`, `""`, `"abc"` và số vượt giới hạn `int`.
5. Vòng lặp đúng cận, tên biến có nghĩa, chương trình compile/run sạch; ít nhất 6 ca test gồm đầu vào thường, rỗng, sát cận, đúng cận, ngoài cận và sai định dạng.

Đối chiếu sau khi làm:

- Có giải thích được **vì sao** từng nhánh và phép toán cho kết quả đó không?
- Có phân biệt được lỗi phát sinh khi biên dịch, khi chạy và sai kết quả không?
- Có thử đầu vào bất thường và tự sửa được bằng thông báo lỗi/stack trace không?
- Có thể chạy lại tất cả test sau khi đổi một dòng mà không phải kiểm tra hoàn toàn bằng mắt không?

Nếu chưa làm được một mục, hãy biến mục đó thành ca kiểm tra nhỏ, có **đầu vào và kết quả mong đợi rõ ràng**. Nắm vững Java Core bắt đầu từ khả năng giải thích chính xác và kiểm chứng được hành vi của những chương trình nhỏ trước khi tăng độ phức tạp.
