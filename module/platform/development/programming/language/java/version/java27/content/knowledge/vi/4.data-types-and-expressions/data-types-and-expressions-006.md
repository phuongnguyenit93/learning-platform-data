# Chuyển đổi kiểu, ép kiểu và nguy cơ mất dữ liệu

Trong Java 27, **chuyển đổi kiểu (type conversion)** là quá trình đưa một giá trị từ kiểu nguồn sang kiểu đích để nó phù hợp với phép gán, tham số phương thức, phép toán hoặc một biểu thức khác. Java có thể tự thực hiện một số chuyển đổi khi quy tắc ngôn ngữ cho phép; với những trường hợp cần thu hẹp kiểu hoặc kiểm tra rõ ràng, lập trình viên dùng **ép kiểu (cast)**.

Chuyển đổi kiểu có thể chỉ thay đổi cách trình biên dịch nhìn nhận một giá trị, có thể thay đổi biểu diễn của giá trị, hoặc có thể cần kiểm tra ở thời điểm chạy. Vì vậy, một lệnh ép kiểu biên dịch thành công chưa chắc giữ nguyên giá trị ban đầu. Khi chuyển đổi dữ liệu, cần xác định rõ ba điều: kiểu nguồn, kiểu đích và liệu giá trị có nằm trong miền biểu diễn của kiểu đích hay không.

Bài học này dùng quy tắc hiện hành trong Java SE 27, tập trung vào chuyển đổi số nguyên thủy, kiểu tham chiếu, boxing/unboxing, numeric promotion và những tình huống có thể làm mất dữ liệu.

## 1. Chuyển đổi kiểu và ép kiểu khác nhau thế nào?

**Chuyển đổi kiểu** là khái niệm tổng quát trong ngôn ngữ Java. Một chuyển đổi có thể là:

- **Chuyển đổi ngầm định (implicit conversion):** trình biên dịch tự áp dụng khi ngữ cảnh cho phép, ví dụ gán một giá trị **int** sang **long**.
- **Chuyển đổi tường minh (explicit conversion):** lập trình viên ghi rõ kiểu đích bằng toán tử cast, ví dụ **(int) price**.

Ví dụ:

    int quantity = 25;
    long totalQuantity = quantity;       // Chuyển đổi ngầm định int -> long

    double price = 19.75;
    int wholePrice = (int) price;        // Ép kiểu tường minh double -> int

Kết quả của ví dụ thứ hai là **19**. Phần thập phân bị loại bỏ vì chuyển từ số dấu phẩy động sang số nguyên áp dụng quy tắc làm tròn về 0. Toán tử cast không có nghĩa là “làm tròn gần nhất”.

Java kiểm tra tính hợp lệ của chuyển đổi ở hai thời điểm:

- **Compile time:** xác định kiểu nguồn, kiểu đích và chuyển đổi có được phép trong ngữ cảnh đó không. Chuyển đổi không được phép gây lỗi biên dịch.
- **Runtime:** một số chuyển đổi cần kiểm tra giá trị thực tế. Ép kiểu tham chiếu có thể ném **ClassCastException**; unboxing một giá trị **null** có thể ném **NullPointerException**.

Ép kiểu không phải thao tác xác thực dữ liệu nghiệp vụ. Ví dụ, **(byte) value** không kiểm tra **value** có nằm trong khoảng -128 đến 127 hay không; nó vẫn tạo ra kết quả theo quy tắc thu hẹp của Java.

## 2. Chuyển đổi giữa các kiểu nguyên thủy

Java có tám kiểu nguyên thủy. Bảy kiểu sau biểu diễn số hoặc ký tự: **byte**, **short**, **int**, **long**, **float**, **double** và **char**. Kiểu **boolean** biểu diễn giá trị đúng/sai và không tham gia chuyển đổi số.

### 2.1. Widening primitive conversion — chuyển đổi mở rộng

Chuyển đổi mở rộng đưa giá trị sang một kiểu nguyên thủy có miền biểu diễn rộng hơn theo các cặp được Java cho phép. Các chuyển đổi mở rộng hợp lệ gồm:

| Kiểu nguồn | Các kiểu đích được phép |
| --- | --- |
| **byte** | **short**, **int**, **long**, **float**, **double** |
| **short** | **int**, **long**, **float**, **double** |
| **char** | **int**, **long**, **float**, **double** |
| **int** | **long**, **float**, **double** |
| **long** | **float**, **double** |
| **float** | **double** |

Ví dụ:

    byte small = 100;
    int number = small;
    long large = number;
    double measurement = large;

Các phép gán trên không cần cast. Khi chuyển một số nguyên có dấu sang kiểu nguyên có độ rộng lớn hơn, Java mở rộng bit dấu; khi chuyển **char** sang kiểu số nguyên, Java mở rộng bằng cách điền bit 0 vì **char** là kiểu không dấu 16 bit.

**Mở rộng không đồng nghĩa luôn chính xác tuyệt đối.** Chuyển **int** sang **float**, **long** sang **float** hoặc **long** sang **double** có thể làm mất các bit có trọng số thấp do kiểu dấu phẩy động không biểu diễn được mọi số nguyên lớn.

    int original = 1_234_567_890;
    float approximate = original;

    System.out.println(original);                    // 1234567890
    System.out.println((int) approximate);           // 1234567936
    System.out.println(original - (int) approximate); // -46

Giá trị **float** đã được làm tròn theo quy tắc số dấu phẩy động. Cast ngược về **int** không khôi phục được những bit đã mất.

Một số chuyển đổi mở rộng giữ nguyên giá trị chính xác, chẳng hạn **int** sang **long**, **int** sang **double**, **float** sang **double**, và các kiểu **byte**, **short**, **char** sang **float** hoặc **double**. Tuy nhiên, cần xem xét đúng kiểu nguồn và đích thay vì suy luận chỉ từ tên “mở rộng”.

### 2.2. Narrowing primitive conversion — chuyển đổi thu hẹp

Chuyển đổi thu hẹp đưa giá trị sang kiểu nguyên thủy có miền biểu diễn nhỏ hơn hoặc độ chính xác thấp hơn. Các chuyển đổi này có thể làm mất bit, mất phần thập phân, mất độ chính xác hoặc mất phạm vi biểu diễn.

Phần lớn chuyển đổi thu hẹp cần cast tường minh:

    long population = 9_000_000_000L;
    int truncatedPopulation = (int) population;

    double temperature = 36.8;
    int wholeTemperature = (int) temperature;

Kết quả:

- **truncatedPopulation** không còn chứa giá trị dân số ban đầu vì **int** không đủ miền biểu diễn.
- **wholeTemperature** bằng **36**; phần thập phân **.8** bị bỏ.

Với chuyển đổi từ số nguyên sang kiểu nguyên có độ rộng nhỏ hơn, Java giữ lại các bit thấp nhất và loại bỏ các bit cao hơn. Vì vậy, kết quả có thể đổi cả độ lớn lẫn dấu:

    int source = 130;
    byte result = (byte) source;

    System.out.println(result); // -126

**byte** là số nguyên có dấu 8 bit. Giá trị 130 có dạng bit thấp 8 bit tương ứng với **10000010**; khi được diễn giải theo kiểu **byte**, kết quả là -126.

Một số trường hợp dễ gây nhầm lẫn:

    System.out.println((byte) 255);         // -1
    System.out.println((short) 0x12345678); // 22136, tức 0x5678
    System.out.println((int) (char) -1);    // 65535

**char** có miền giá trị từ 0 đến 65.535. Ép **-1** sang **char** giữ 16 bit thấp và tạo ra giá trị 65.535; khi chuyển tiếp sang **int**, giá trị này được mở rộng thành số nguyên dương.

Một giá trị **char** biểu diễn một code unit UTF-16, không phải lúc nào cũng là toàn bộ một ký tự Unicode. Ký tự ngoài Basic Multilingual Plane được biểu diễn bằng một cặp surrogate, vì vậy cần dùng **int** để chứa code point khi xử lý đầy đủ các ký tự đó:

    String symbol = new String(Character.toChars(0x1F600));
    int codePoint = symbol.codePointAt(0);
    System.out.println(Integer.toHexString(codePoint)); // 1f600

### 2.3. Chuyển từ số dấu phẩy động sang số nguyên

Khi cast **float** hoặc **double** sang **byte**, **short**, **char**, **int** hoặc **long**, Java thực hiện theo quy tắc xác định:

1. Phần thập phân bị bỏ bằng cách làm tròn về 0. Ví dụ **12.9** thành **12**, còn **-12.9** thành **-12**.
2. Nếu giá trị là **NaN**, bước chuyển đổi trung gian cho kết quả **0**.
3. Nếu giá trị quá lớn, quá nhỏ hoặc là vô cực, bước chuyển đổi trung gian cho giá trị lớn nhất hoặc nhỏ nhất mà **int** hoặc **long** có thể biểu diễn.
4. Nếu kiểu đích là **byte**, **short** hoặc **char**, kết quả trung gian tiếp tục được thu hẹp theo quy tắc giữ các bit thấp.

Ví dụ:

    System.out.println((int) 12.99);                    // 12
    System.out.println((int) -12.99);                   // -12
    System.out.println((int) Double.NaN);               // 0
    System.out.println((int) Double.POSITIVE_INFINITY); // 2147483647
    System.out.println((int) Double.NEGATIVE_INFINITY); // -2147483648

Đây là hành vi được quy định bởi Java Language Specification. Phép cast nguyên thủy kiểu này không ném exception chỉ vì giá trị bị tràn hoặc mất thông tin; kết quả có thể rất khác giá trị nguồn.

### 2.4. Chuyển từ double sang float

**float** có độ chính xác và miền biểu diễn nhỏ hơn **double**. Khi thu hẹp:

- Giá trị có thể được làm tròn sang một số **float** gần nhất.
- Giá trị hữu hạn quá lớn có thể trở thành dương hoặc âm vô cực.
- Giá trị khác 0 quá nhỏ có thể trở thành **0.0f**.
- **NaN** và vô cực vẫn được biểu diễn bằng các giá trị đặc biệt tương ứng.

    double precise = 0.1;
    float rounded = (float) precise;

    double tooLarge = 1.0e100;
    float infinity = (float) tooLarge;

    double tooSmall = 1.0e-50;
    float zero = (float) tooSmall;

    System.out.println(rounded);
    System.out.println(infinity); // Infinity
    System.out.println(zero);     // 0.0

Không nên dùng **float** cho dữ liệu cần giữ độ chính xác thập phân nghiêm ngặt, chẳng hạn số tiền hoặc số liệu kế toán.

## 3. Chuyển đổi trong phép gán và lời gọi phương thức

Java áp dụng những tập quy tắc khác nhau tùy ngữ cảnh. Việc một phép chuyển đổi được chấp nhận khi gán biến không có nghĩa nó cũng được tự động chấp nhận khi truyền đối số vào phương thức.

### 3.1. Assignment conversion

Trong phép gán, Java cho phép chuyển đổi đồng nhất, chuyển đổi mở rộng, một số chuyển đổi boxing/unboxing và một ngoại lệ thu hẹp dành cho biểu thức hằng số nguyên tại thời điểm biên dịch.

Ví dụ:

    byte level = 100;       // Hằng int 100 thu hẹp an toàn sang byte
    int count = 100;
    long total = count;     // Mở rộng int -> long

    final int MAX_LEVEL = 120;
    byte configuredLevel = MAX_LEVEL; // Được phép vì hằng số vừa byte

Một biểu thức hằng số kiểu **byte**, **short**, **char** hoặc **int** có thể được thu hẹp khi gán sang **byte**, **short** hoặc **char** nếu giá trị của biểu thức nằm trong miền của kiểu đích.

Ngược lại:

    int count = 100;
    // byte level = count; // Lỗi biên dịch: biến count không phải constant expression
    byte level = (byte) count;

Cast ở ví dụ cuối làm chương trình biên dịch, nhưng người viết phải tự bảo đảm dữ liệu phù hợp với miền của **byte**.

### 3.2. Method invocation conversion

Khi gọi phương thức hoặc constructor, Java cho phép các chuyển đổi như mở rộng nguyên thủy, mở rộng tham chiếu, boxing và unboxing theo quy tắc overload resolution. Tuy nhiên, lời gọi phương thức **không áp dụng ngoại lệ thu hẹp hằng số nguyên** giống phép gán.

    static void acceptByte(byte value) {
        System.out.println(value);
    }

    public static void main(String[] args) {
        // acceptByte(10);       // Lỗi biên dịch: đối số 10 có kiểu int
        acceptByte((byte) 10);   // Hợp lệ vì đã cast tường minh
    }

Nếu có nhiều overload, các quy tắc chuyển đổi còn tham gia lựa chọn phương thức phù hợp. Tránh cast tùy tiện để “chữa” lỗi overload; trước tiên hãy kiểm tra kiểu tham số và ý nghĩa của dữ liệu.

### 3.3. Compound assignment

Toán tử gán kết hợp như **+=**, **-=**, **\*=**, **/=** có quy tắc chuyển đổi đặc biệt. Kết quả phép toán được chuyển về kiểu của vế trái một cách ngầm định:

    byte score = 10;
    score += 5;          // Hợp lệ

    // score = score + 5; // Lỗi biên dịch: score + 5 có kiểu int
    score = (byte) (score + 5);

**score += 5** không có nghĩa phép cộng được thực hiện trực tiếp trên **byte**. Các toán hạng vẫn trải qua numeric promotion; sau phép toán, kết quả được chuyển về kiểu của biến đích. Nếu kết quả vượt miền **byte**, dữ liệu vẫn có thể bị mất.

## 4. Numeric promotion — nâng kiểu trong biểu thức số học

Java thường nâng các kiểu nguyên thủy nhỏ trước khi thực hiện phép toán. Đây là lý do biểu thức cộng hai biến **byte** vẫn có kiểu **int**.

### 4.1. Unary numeric promotion

Khi dùng một toán tử số học đơn ngôi như **+**, **-** hoặc **~**, các giá trị **byte**, **short** và **char** được nâng lên **int**. Giá trị **int**, **long**, **float**, **double** giữ nguyên kiểu tương ứng.

    byte value = 5;
    int negative = -value;

### 4.2. Binary numeric promotion

Với các phép toán số học hai ngôi như **+**, **-**, **\***, **/**, **%**, Java chọn kiểu chung theo thứ tự:

1. Nếu có toán hạng **double**, kiểu phép toán là **double**.
2. Nếu không có **double** nhưng có **float**, kiểu phép toán là **float**.
3. Nếu không có hai kiểu trên nhưng có **long**, kiểu phép toán là **long**.
4. Nếu tất cả toán hạng còn lại thuộc **byte**, **short**, **char** hoặc **int**, chúng được nâng lên **int**.

Ví dụ:

    byte first = 10;
    byte second = 20;
    int sum = first + second;        // Phép cộng thực hiện bằng int

    long distance = 100L;
    float ratio = 1.5f;
    float result = distance * ratio; // long được chuyển sang float

Vì **byte + byte** cho kết quả kiểu **int**, lệnh **byte sum = first + second;** không biên dịch nếu không có cast. Với biểu thức hỗn hợp **long** và **float**, kết quả là **float**; giá trị **long** lớn có thể mất độ chính xác khi được chuyển sang **float**.

### 4.3. Tràn số trong phép toán

Một lỗi thường gặp là cho rằng Java tự nâng phép toán lên **long** chỉ vì biến nhận kết quả là **long**. Kiểu của phép toán được xác định từ các toán hạng trước khi gán kết quả.

    int a = Integer.MAX_VALUE;
    int b = 1;

    long wrong = a + b;          // Phép cộng int bị tràn trước khi gán
    long correct = (long) a + b; // Mở rộng a trước khi cộng

**wrong** nhận giá trị âm do phép cộng **int** đã tràn; việc gán kết quả sang **long** không thể khôi phục giá trị đã mất. Phép toán số nguyên thông thường không tự ném exception khi tràn.

Nếu cần phát hiện tràn, dùng các phương thức kiểm tra của **Math**:

    int sum = Math.addExact(a, b);
    int product = Math.multiplyExact(a, b);

Các phương thức **addExact**, **subtractExact**, **multiplyExact**, **incrementExact**, **decrementExact** và **toIntExact** ném **ArithmeticException** khi kết quả vượt miền kiểu đích. Hãy chọn overload phù hợp với **int** hoặc **long**.

### 4.4. Phép chia số nguyên

Chia hai số nguyên tạo kết quả số nguyên và loại bỏ phần dư theo hướng về 0:

    System.out.println(7 / 2);    // 3
    System.out.println(-7 / 2);   // -3

Nếu cần kết quả thập phân, ít nhất một toán hạng phải là **float** hoặc **double** trước khi phép chia được thực hiện:

    double average = 7 / 2.0;     // 3.5

Viết **double average = 7 / 2;** vẫn cho kết quả **3.0**, vì phép chia **int** đã tạo ra **3** trước khi gán sang **double**.

## 5. Boxing và unboxing

Java có các lớp bao tương ứng với kiểu nguyên thủy:

| Primitive | Wrapper |
| --- | --- |
| **boolean** | **Boolean** |
| **byte** | **Byte** |
| **short** | **Short** |
| **char** | **Character** |
| **int** | **Integer** |
| **long** | **Long** |
| **float** | **Float** |
| **double** | **Double** |

**Boxing** chuyển một giá trị nguyên thủy thành giá trị của lớp bao tương ứng. **Unboxing** lấy giá trị nguyên thủy từ đối tượng wrapper.

    int primitiveValue = 42;
    Integer boxedValue = primitiveValue; // Boxing

    Integer storedValue = 100;
    int unboxedValue = storedValue;       // Unboxing

Compiler có thể tự thực hiện các chuyển đổi này trong phép gán và lời gọi phương thức khi quy tắc ngữ cảnh cho phép. Chuyển đổi kết hợp cũng có thể xảy ra, ví dụ **Integer** sang **long** gồm unboxing thành **int**, rồi widening thành **long**.

**Unboxing một tham chiếu null gây NullPointerException:**

    Integer optionalCount = null;
    // int count = optionalCount; // NullPointerException lúc chạy

Trước khi unbox dữ liệu có thể null, hãy kiểm tra null hoặc dùng API biểu diễn giá trị vắng mặt phù hợp. Không nên mặc định rằng wrapper luôn chứa một số.

Boxing cũng tạo ra đối tượng tham chiếu theo quy tắc của Java. Không dùng **==** để so sánh giá trị số trong hai wrapper; hãy dùng **equals**, chuyển về primitive khi chắc chắn không null, hoặc dùng phương thức so sánh thích hợp.

## 6. Chuyển đổi và ép kiểu tham chiếu

Chuyển đổi giữa các kiểu tham chiếu không thay đổi lớp thực tế của đối tượng. Nó thay đổi kiểu mà biến hoặc biểu thức được phép truy cập tại thời điểm biên dịch.

### 6.1. Widening reference conversion — upcasting

Chuyển từ lớp con sang lớp cha hoặc interface mà lớp đó triển khai là chuyển đổi mở rộng tham chiếu. Đây là thao tác an toàn và thường không cần cast:

    String message = "Java 27";
    Object value = message;

Biến **value** có kiểu khai báo **Object**, nhưng đối tượng thực tế vẫn là một **String**.

### 6.2. Narrowing reference conversion — downcasting

Chuyển từ kiểu tổng quát sang kiểu cụ thể hơn cần cast tường minh. Java có thể kiểm tra kiểu thực tế của đối tượng khi chạy:

    Object value = "Java 27";
    String message = (String) value;

Nếu đối tượng không phải **String** hoặc lớp con phù hợp, JVM ném **ClassCastException**:

    Object value = Integer.valueOf(27);
    // String message = (String) value; // ClassCastException lúc chạy

Một cast tham chiếu chỉ hợp lệ nếu hai kiểu có quan hệ tương thích theo quy tắc của Java. Cast không biến một đối tượng **Integer** thành **String**; nó chỉ yêu cầu JVM kiểm tra xem đối tượng hiện tại có thể được xem như kiểu đích hay không.

### 6.3. Kiểm tra kiểu trước khi sử dụng

Có thể kiểm tra kiểu bằng **instanceof** trước khi downcast. Cú pháp pattern matching cho **instanceof** đã là tính năng ổn định trong các phiên bản Java hiện đại:

    Object value = "Java 27";

    if (value instanceof String text) {
        System.out.println(text.length());
    }

Nếu kiểm tra thành công, biến pattern **text** có kiểu **String** trong phạm vi được phép sử dụng. Cách này giúp tránh cast không an toàn và giảm khả năng gặp **ClassCastException**.

### 6.4. Cast với generic

Do type erasure, JVM không thể kiểm tra đầy đủ mọi tham số kiểu generic ở runtime. Một cast như:

    Object candidate = List.of("Java", "27");
    // List<Integer> numbers = (List<Integer>) candidate;

có thể phát sinh unchecked warning. Cast có thể qua được kiểm tra kiểu thô tại runtime nhưng không chứng minh các phần tử bên trong đúng là **Integer**. Lỗi có thể chỉ xuất hiện sau đó khi đọc phần tử và chuyển nó sang kiểu cụ thể.

Khi nhận dữ liệu chưa rõ kiểu, ưu tiên kiểm tra **List<?>**, duyệt từng phần tử dưới dạng **Object**, rồi xác thực kiểu của từng phần tử bằng **instanceof**. Không dùng **@SuppressWarnings("unchecked")** chỉ để che cảnh báo mà chưa chứng minh được dữ liệu an toàn.

## 7. Chuyển đổi số và chuỗi là hai thao tác khác nhau

Cast chỉ chuyển đổi giữa những kiểu mà quy tắc Java cho phép. Không thể dùng cast để biến chuỗi chứa số thành số:

    String text = "123";
    // int value = (int) text; // Lỗi biên dịch

Hãy dùng API phân tích chuỗi:

    int count = Integer.parseInt("123");
    long total = Long.parseLong("9000000000");
    double rate = Double.parseDouble("12.5");

Nếu chuỗi không đúng định dạng, các phương thức parse ném **NumberFormatException**. **Integer.parseInt** và **Long.parseLong** cũng ném exception khi giá trị vượt miền kiểu đích. Với **Float.parseFloat** và **Double.parseDouble**, giá trị số quá lớn có thể được chuyển thành vô cực, còn giá trị quá nhỏ có thể thành 0; hãy dùng **Float.isFinite** hoặc **Double.isFinite** nếu nghiệp vụ chỉ chấp nhận số hữu hạn. Với dữ liệu đến từ người dùng hoặc hệ thống bên ngoài, hãy xử lý lỗi phân tích và kiểm tra giới hạn nghiệp vụ.

Để chuyển một giá trị thành chuỗi, dùng **String.valueOf(value)**, **Integer.toString(value)** hoặc phương thức **toString()** phù hợp. Nối chuỗi bằng toán tử **+** cũng thực hiện string conversion cho toán hạng không phải **String**.

## 8. Những tình huống mất dữ liệu cần nhận diện

| Tình huống | Nguy cơ | Ví dụ hoặc biểu hiện |
| --- | --- | --- |
| **long** sang **int** | Mất bit cao, đổi độ lớn hoặc dấu | **(int) 9_000_000_000L** |
| **int** sang **float** | Mất độ chính xác ở các bit thấp | **1_234_567_890** không được biểu diễn chính xác bằng **float** |
| **double** sang **int** | Bỏ phần thập phân; giá trị ngoài miền bị giới hạn về biên | **(int) 12.9** cho **12** |
| **double** sang **float** | Mất độ chính xác hoặc phạm vi; có thể thành vô cực/0 | **(float) 1.0e100** |
| **char** sang **byte** | Mất các bit cao; kết quả có thể âm | **(byte) 0x20AC** |
| Phép cộng **int** bị tràn | Giá trị tràn trước khi gán sang kiểu rộng hơn | **long x = Integer.MAX_VALUE + 1** |
| Unboxing wrapper null | Phát sinh exception lúc chạy | **int x = (Integer) null** |
| Downcast tham chiếu sai | Phát sinh exception lúc chạy | **(String) Integer.valueOf(1)** |
| Cast generic không kiểm chứng | Cảnh báo unchecked, lỗi có thể xuất hiện lúc đọc phần tử | Cast **Object** thành **List<String>** |
| Phân tích chuỗi số sai định dạng | Không tạo được giá trị số | **Integer.parseInt("12x")** |

Lưu ý: chuyển đổi thu hẹp giữa các kiểu nguyên thủy không tự ném exception khi tràn. Đây là điểm khác biệt quan trọng so với downcast tham chiếu, unboxing null hoặc các API chuyển đổi có kiểm tra.

## 9. Cách chuyển đổi an toàn trong ứng dụng

### 9.1. Kiểm tra trước khi thu hẹp số nguyên

Nếu chuyển **long** sang **int** và cần bảo đảm không mất dữ liệu, dùng **Math.toIntExact**:

    long source = 2_000_000_000L;
    int result = Math.toIntExact(source);

Nếu giá trị vượt miền **int**, phương thức ném **ArithmeticException** thay vì âm thầm loại bỏ bit.

### 9.2. Dùng phép toán có kiểm tra tràn

Nếu dữ liệu có thể đạt gần giới hạn kiểu số, dùng **Math.addExact**, **Math.subtractExact** hoặc **Math.multiplyExact**:

    int subtotal = Math.multiplyExact(unitPrice, quantity);
    int total = Math.addExact(previousTotal, subtotal);

Các phương thức này giúp phát hiện tràn tại đúng phép toán gây ra vấn đề. Nếu nghiệp vụ cần xử lý số lớn hơn **long**, cân nhắc **BigInteger** hoặc **BigDecimal**.

### 9.3. Dùng BigDecimal cho số thập phân cần độ chính xác

**float** và **double** biểu diễn số dấu phẩy động theo hệ nhị phân. Nhiều phân số thập phân, chẳng hạn **0.1**, không có biểu diễn nhị phân hữu hạn. Vì vậy, phép tính có thể tạo ra sai số làm tròn.

    double sum = 0.1 + 0.2;
    System.out.println(sum); // Thường hiển thị 0.30000000000000004

Với tiền tệ hoặc phép tính thập phân cần kiểm soát, dùng **BigDecimal** và xác định chính sách làm tròn:

    import java.math.BigDecimal;
    import java.math.RoundingMode;

    BigDecimal price = new BigDecimal("19.90");
    BigDecimal taxRate = new BigDecimal("0.10");
    BigDecimal tax = price.multiply(taxRate)
            .setScale(2, RoundingMode.HALF_UP);

    BigDecimal total = price.add(tax);

Ưu tiên tạo **BigDecimal** từ chuỗi thập phân hoặc dùng **BigDecimal.valueOf(double)** khi nguồn bắt buộc là **double**. Constructor **new BigDecimal(double)** giữ chính xác giá trị nhị phân của **double**, nên **new BigDecimal(0.1)** không tạo ra đúng số thập phân 0.1 như nhiều người mong đợi.

Nếu cần chuyển **BigDecimal** sang kiểu nguyên mà không cho phép mất phần thập phân hoặc vượt phạm vi, dùng **intValueExact()**, **longValueExact()**, **shortValueExact()** hoặc **byteValueExact()**. Các phương thức này ném **ArithmeticException** khi không thể chuyển đổi chính xác.

### 9.4. Quy định rõ cách làm tròn

Không chọn cast chỉ vì muốn có một số nguyên. Cast số dấu phẩy động sang số nguyên luôn bỏ phần thập phân theo hướng về 0. Nếu nghiệp vụ yêu cầu làm tròn, hãy chọn phương thức làm tròn có ngữ nghĩa phù hợp và ghi rõ quy tắc xử lý trường hợp đúng giữa hai số.

Với **BigDecimal**, dùng **setScale(scale, RoundingMode)** để nêu rõ số chữ số thập phân và chính sách làm tròn. Tránh các hằng số số nguyên cũ biểu diễn rounding mode; dùng enum **RoundingMode** hiện hành.

### 9.5. Xử lý byte không dấu khi đọc dữ liệu nhị phân

Trong Java, **byte** là số nguyên có dấu. Nếu một giao thức hoặc định dạng tệp quy định một byte là số không dấu từ 0 đến 255, không nên đọc trực tiếp giá trị **byte** như một số dương:

    byte raw = (byte) 0xFF;
    int signedValue = raw;                       // -1
    int unsignedValue = Byte.toUnsignedInt(raw); // 255

**Byte.toUnsignedInt** chuyển cách diễn giải byte sang miền số không dấu tương ứng. Cách này hữu ích khi xử lý header, mã trạng thái, dữ liệu mạng hoặc định dạng nhị phân.

### 9.6. Xác thực kiểu tham chiếu và dữ liệu bên ngoài

Với object có kiểu tổng quát như **Object**, kiểm tra bằng **instanceof** trước khi dùng. Với dữ liệu chuỗi, parse và bắt lỗi định dạng. Với số, kiểm tra miền nghiệp vụ trước khi cast. Với wrapper, xử lý **null** trước unboxing. Mỗi bước kiểm tra giải quyết một loại rủi ro khác nhau.

## 10. Quy trình chọn phép chuyển đổi

Khi cần chuyển một giá trị, hãy lần lượt trả lời:

1. **Nguồn và đích là kiểu gì?** Primitive, wrapper, kiểu tham chiếu, generic hay chuỗi?
2. **Ngữ cảnh nào đang yêu cầu chuyển đổi?** Phép gán, đối số phương thức, biểu thức số học, cast hay pattern matching?
3. **Java có cho phép chuyển đổi ngầm định không?** Nếu có, kiểm tra xem widening sang **float** hoặc **double** có thể mất precision không.
4. **Nếu phải thu hẹp, dữ liệu có nằm trong miền đích không?** Kiểm tra cả phần thập phân, giới hạn số, **NaN**, vô cực và null.
5. **Ứng dụng cần kết quả gần đúng hay chính xác?** Chọn cast, phương thức kiểm tra overflow, **BigInteger**, **BigDecimal** hoặc quy tắc làm tròn phù hợp.
6. **Có thể thất bại lúc chạy không?** Xem xét **ClassCastException**, **NullPointerException**, **NumberFormatException** và **ArithmeticException**.
7. **Có kiểm thử biên không?** Thử giá trị nhỏ nhất, lớn nhất, ngay ngoài giới hạn, số âm, số 0, phần thập phân, **NaN**, vô cực và dữ liệu null nếu kiểu cho phép.

## 11. Tổng kết

Chuyển đổi mở rộng thường cho phép Java tự động đổi kiểu, nhưng **int** sang **float** hoặc **long** sang **double** vẫn có thể mất độ chính xác. Chuyển đổi thu hẹp cần được xem xét cẩn thận vì có thể bỏ bit, bỏ phần thập phân, mất phạm vi hoặc tạo ra giá trị vô cực/0. Numeric promotion còn khiến các phép toán trên **byte**, **short** và **char** thường được thực hiện bằng **int**; phép toán có thể tràn trước khi kết quả được gán.

Với kiểu tham chiếu, upcasting an toàn theo quan hệ kế thừa; downcasting cần kiểm tra kiểu thực tế. Boxing/unboxing thuận tiện nhưng unboxing null gây **NullPointerException**. Chuyển chuỗi sang số phải dùng API parse và xử lý lỗi.

Trong ứng dụng thực tế, hãy dùng **Math.toIntExact** và các phép toán **Math.*Exact** khi cần phát hiện tràn, dùng **BigDecimal** cho số thập phân cần độ chính xác, xác thực dữ liệu trước khi cast và kiểm thử các giá trị biên. Mục tiêu là bảo toàn ý nghĩa của dữ liệu trong toàn bộ quá trình chuyển đổi.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — Chapter 5: Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se27/html/jls-5.html) — quy tắc chính thức về các loại chuyển đổi, ngữ cảnh phép gán/lời gọi/cast, boxing/unboxing và numeric promotion.
- [Java Language Specification, Java SE 27 — Chapter 15: Expressions](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html) — toán tử cast, phép toán số học và compound assignment.
- [Math (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html) — **toIntExact**, **addExact**, **subtractExact**, **multiplyExact** và các phép toán có kiểm tra tràn.
- [BigDecimal (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html) — độ chính xác thập phân, rounding mode và các phương thức chuyển đổi exact.
- [BigInteger (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigInteger.html) — số nguyên độ lớn tùy ý và các phương thức chuyển đổi có kiểm tra.
- [Byte (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Byte.html) — miền giá trị của **byte** và các phương thức xử lý giá trị byte không dấu.
