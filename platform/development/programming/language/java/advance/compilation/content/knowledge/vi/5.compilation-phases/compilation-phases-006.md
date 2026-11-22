# Phân tích luồng điều khiển và điều kiện hợp lệ trong quá trình biên dịch Java

## 1. Mục tiêu

Khi kiểm tra một chương trình Java, trình biên dịch không chỉ xác định cú pháp và kiểu dữ liệu có đúng hay không. Nó còn phân tích **những đường đi có thể xảy ra trong chương trình** để phát hiện một số lỗi trước khi chạy: câu lệnh không thể tới được, biến cục bộ có thể được đọc khi chưa gán, biến final có thể bị gán lại, phương thức có thể kết thúc mà không trả về giá trị, hoặc checked exception chưa được xử lý.

Đây là phần **flow analysis** trong bức tranh các giai đoạn biên dịch. Sau bài này, bạn có thể:

- Hiểu cách một câu lệnh if/else, switch, vòng lặp, return, break, continue và try/catch tạo các nhánh điều khiển.
- Phân biệt **reachability** (khả năng một câu lệnh được coi là có thể tới được) và **definite assignment** (biến chắc chắn đã được gán tại một điểm).
- Hiểu ràng buộc gán đối với biến final, yêu cầu trả về của phương thức, và kiểm tra checked exceptions.
- Đọc, dự đoán, sửa lỗi javac bằng cách phân tích mọi nhánh có liên quan.
- Nhận ra giới hạn của compiler: nó không chứng minh mọi điều kiện thực tế, không chạy chương trình để quyết định và không loại trừ tất cả lỗi runtime.

Bài sử dụng cú pháp **Java 17**. Các đoạn code được ghi rõ là chương trình hoàn chỉnh hay ví dụ gây lỗi có chủ đích.

## 2. Luồng điều khiển là gì?

**Control flow** là thứ tự và các hướng mà việc thực thi có thể đi qua các câu lệnh. Với đoạn code tuần tự, chương trình chạy từ trên xuống dưới. Với if, nó rẽ nhánh; với for/while, nó có thể quay lại; với return/throw, luồng hiện tại kết thúc; với break/continue, nó chuyển tới vị trí do cấu trúc bao quanh quyết định.

Xem ví dụ nhỏ:

~~~java
static String label(int points) {
    if (points >= 60) {
        return "pass";
    }
    return "retry";
}
~~~

Một cách hình dung sơ đồ luồng:

~~~text
             Bắt đầu
                |
          points >= 60?
            /       \
          true      false
           |          |
     return "pass"  return "retry"
            \        /
          kết thúc lời gọi
~~~

Hai câu lệnh return nằm ở hai nhánh khác nhau. Dù nhánh nào được chọn, lời gọi label cũng trả về String. Trình biên dịch kiểm tra các yêu cầu của Java dựa trên cấu trúc điều khiển tương tự, không phải thử gọi phương thức với mọi giá trị points.

Trong triển khai compiler, việc phân tích có thể dựa trên cây cú pháp, trạng thái của các nhánh và/hoặc biểu diễn luồng trung gian. Ta dùng **control-flow graph (CFG)** để học cách suy luận, không khẳng định javac bắt buộc xây đúng biểu đồ minh họa như trên.

### Khối cơ bản, nhánh và đường hợp nhất

Trong một CFG khái niệm, **node** biểu diễn một câu lệnh hoặc khối lệnh; **edge** biểu diễn khả năng chuyển điều khiển. Nơi hai nhánh gặp lại nhau là một **điểm hợp nhất**. Thông tin compiler biết tại điểm hợp nhất thường phải đúng cho **tất cả các đường đến điểm đó**.

Chẳng hạn:

~~~java
int result;
if (valid) {
    result = 10;
} else {
    result = 0;
}
System.out.println(result);
~~~

Cả đường true và false đều gán result. Vì vậy câu lệnh in có thể dùng result an toàn theo quy tắc definite assignment.

Ngược lại:

~~~java
int result;
if (valid) {
    result = 10;
}
System.out.println(result); // LỖI BIÊN DỊCH
~~~

Nếu valid là false, không có phép gán result trước khi in. javac báo dạng **variable result might not have been initialized**, dù ở một lần chạy cụ thể bạn có thể biết valid luôn true.

> **Điểm cốt lõi:** kiểm tra “chắc chắn” ở thời điểm biên dịch thường bảo thủ. Một đường hợp lệ mà biến chưa được gán là đủ để từ chối đọc biến đó.

## 3. Reachability: câu lệnh có thể tới được hay không?

**Reachability** là tập quy tắc của ngôn ngữ xác định một câu lệnh có được xem là có thể thực thi theo cấu trúc điều khiển hay không. Java cấm một số câu lệnh **unreachable** vì chúng đứng sau một lệnh luôn làm kết thúc/chuyển luồng.

Ví dụ gây lỗi có chủ đích, không phải chương trình runnable:

~~~java
static void stop() {
    return;
    // System.out.println("never"); // Nếu bỏ //: unreachable statement
}
~~~

Khi bỏ comment ở câu lệnh in, javac báo **unreachable statement**. Sau return không tồn tại đường điều khiển bình thường nào để chạy câu lệnh đó.

Tương tự:

~~~java
static int answer() {
    throw new IllegalStateException("stop");
    // return 42; // Nếu bỏ //: unreachable statement
}
~~~

throw chuyển điều khiển bất thường; câu lệnh return ngay phía sau là không thể tới được.

### Vòng lặp và khả năng thoát

Đoạn gây lỗi:

~~~java
static void spin() {
    while (true) {
        System.out.println("tick");
    }
    // System.out.println("done"); // Nếu bỏ //: unreachable statement
}
~~~

Vòng while có biểu thức điều kiện hằng true và không có break có thể tới được để thoát, nên câu lệnh tiếp theo không được coi là reachable. Đừng chạy spin: nó in mãi cho đến khi chương trình bị dừng hoặc phát sinh sự cố tài nguyên.

Nhưng nếu có một break có thể xảy ra:

~~~java
static void spinUntil(boolean stop) {
    while (true) {
        if (stop) {
            break;
        }
    }
    System.out.println("done");
}
~~~

Câu lệnh in được coi là reachable nhờ đường thoát bằng break. Nếu stop không bao giờ true ở một lần chạy cụ thể, lời gọi có thể lặp vô hạn; compiler không chứng minh kết thúc theo dữ liệu runtime.

### Một ngoại lệ quan trọng: if(false) và while(false)

Đừng tự suy luận rằng mọi khối nằm trong điều kiện hằng false đều bị javac từ chối.

~~~java
static void example() {
    if (false) {
        System.out.println("disabled"); // Hợp lệ theo quy tắc reachability của if
    }
}
~~~

Java có quy tắc đặc biệt cho reachability của **if**, nên đoạn trên được phép biên dịch; nó hữu ích cho việc bật/tắt một số khối mã theo điều kiện biên dịch. Ngược lại:

~~~java
static void example() {
    while (false) {
        System.out.println("never"); // LỖI: unreachable statement
    }
}
~~~

Trong Java 17, thân while(false) bị xem là unreachable. Đây là lý do nên học **quy tắc reachability của Java** thay vì tự đánh giá “chắc chắn chạy hay không” hoàn toàn theo trực giác. Các quy tắc chi tiết được quy định tại JLS, mục *Unreachable Statements*.

## 4. Definite assignment: biến phải chắc chắn được gán trước khi đọc

**Definite assignment (DA)** quan tâm việc một biến đã được gán **trên mọi đường điều khiển liên quan** trước khi giá trị của nó được sử dụng. Đối tượng thường gặp là biến cục bộ và blank final; với field, quy tắc khởi tạo và giá trị mặc định còn có khác biệt.

### Ví dụ đúng: gán ở cả hai nhánh

~~~java
static int fee(boolean member) {
    int value;
    if (member) {
        value = 5;
    } else {
        value = 10;
    }
    return value;
}
~~~

Nếu member true thì value bằng 5; nếu false thì bằng 10. Do mọi đường tới return đều gán value, javac chấp nhận.

### Ví dụ sai: thiếu else và đọc biến

~~~java
static int fee(boolean member) {
    int value;
    if (member) {
        value = 5;
    }
    return value; // LỖI: variable value might not have been initialized
}
~~~

Ở đường member=false, biến value chưa được gán trước return. Có hai cách sửa thông dụng:

~~~java
// Cách A: gán ban đầu.
int value = 10;
if (member) {
    value = 5;
}
return value;
~~~

~~~java
// Cách B: có nhánh else.
int value;
if (member) {
    value = 5;
} else {
    value = 10;
}
return value;
~~~

Các đoạn ở đây minh họa **phần thân phương thức**, không phải chương trình độc lập để chạy bằng java. Nếu muốn chạy, đặt chúng vào một phương thức có kiểu trả về int với tham số member phù hợp.

### Vì sao compiler dùng phép hợp nhất “tất cả nhánh”?

Hãy xem trạng thái của biến sau if/else:

| Đường đi | Trạng thái sau nhánh |
| --- | --- |
| member=true | value đã được gán |
| member=false | value đã được gán |
| Gặp lại sau if/else | value chắc chắn đã được gán |

Nếu bỏ else, đường false sẽ giữ trạng thái “chưa gán”, nên tại điểm hợp nhất không thể kết luận DA.

Về mặt tư duy, thông tin “đã gán chắc chắn” được lấy bằng **giao** các trạng thái khả dĩ, không phải “có ít nhất một nhánh đã gán”. Quy tắc thực tế của Java còn tinh vi hơn vì có break, continue, &&, ||, toán tử điều kiện, switch, try/finally và các dạng hoàn thành bất thường.

## 5. Blank final và definite unassignment

Biến local khai báo final nhưng chưa có giá trị ban đầu được gọi là **blank final**. Nó phải được gán trước khi đọc, và mọi phép gán phải thỏa quy tắc **definite unassignment (DU)**: tại điểm gán, compiler có thể chứng minh biến chưa bị gán trên mọi đường có liên quan.

Hợp lệ:

~~~java
static int choose(boolean enabled) {
    final int timeout;
    if (enabled) {
        timeout = 30;
    } else {
        timeout = 5;
    }
    return timeout;
}
~~~

Mỗi đường đi gán timeout đúng một lần trước return.

Không hợp lệ:

~~~java
static int choose(boolean enabled) {
    final int timeout;
    if (enabled) {
        timeout = 30;
    }
    timeout = 5; // LỖI: timeout có thể đã được gán
    return timeout;
}
~~~

Nếu enabled=true, timeout được gán 30 rồi lại gán 5. Dù đường enabled=false chỉ gán một lần, compiler vẫn không thể chứng minh phép gán thứ hai luôn hợp lệ cho blank final.

Cách sửa: có nhánh else, hoặc chọn giá trị ngay trong một biểu thức:

~~~java
final int timeout = enabled ? 30 : 5;
~~~

**Không nhầm với giá trị mặc định của field.** Biến cục bộ int chưa khởi tạo không tự nhận giá trị 0 để được đọc hợp lệ. Một instance field kiểu int không có initializer lại được Java khởi tạo mặc định bằng 0. Với blank final field, còn có quy tắc riêng về hoàn thành khởi tạo trong constructor/static initializer. Bài này tập trung vào flow analysis của phương thức.

## 6. Short-circuit tạo thêm đường điều khiển

Toán tử **&&** và **||** có cơ chế đánh giá ngắn mạch:

- Với a && b, nếu a=false thì b không được tính.
- Với a || b, nếu a=true thì b không được tính.

Do đó, phép gán nằm trong vế thứ hai không nhất thiết đã xảy ra sau toàn biểu thức.

Ví dụ gây lỗi:

~~~java
static void check(boolean enabled) {
    int number;
    boolean ok = enabled && ((number = 7) > 0);
    System.out.println(number); // LỖI: number có thể chưa được khởi tạo
}
~~~

Nếu enabled=false, phần ((number = 7) > 0) bị bỏ qua. Nhưng trong **nhánh true của if** sau đây, phép gán chắc chắn đã xảy ra:

~~~java
static void check(boolean enabled) {
    int number;
    if (enabled && ((number = 7) > 0)) {
        System.out.println(number); // HỢP LỆ: nhánh true đòi vế phải đã chạy
    }
}
~~~

Một kỹ thuật đọc lỗi là vẽ đường true/false của từng phần điều kiện, kể cả những vế có thể bị bỏ qua do short-circuit. Java không yêu cầu mọi điều kiện phải là literal true/false; chỉ yêu cầu biểu thức điều kiện của if/while/for là kiểu boolean hoặc Boolean có thể unbox phù hợp.

**Cẩn thận:** nếu viết if (flag = true) thay vì if (flag == true), biểu thức gán vẫn có kiểu boolean nên **có thể biên dịch thành công** nhưng thay đổi dữ liệu. Flow analysis không phải công cụ tìm mọi lỗi logic.

## 7. Đường trả về: mọi đường kết thúc bình thường của phương thức có giá trị đều phải được xử lý

Một phương thức khai báo kiểu trả về khác void phải bảo đảm thân phương thức không thể **kết thúc bình thường mà thiếu giá trị return**. Đây là yêu cầu kiểm tra điều khiển tại compile-time.

Sai:

~~~java
static String status(int score) {
    if (score >= 50) {
        return "pass";
    }
    // LỖI: missing return statement
}
~~~

Đường score<50 đi đến hết phương thức mà không return String.

Đúng bằng cách bổ sung đường còn thiếu:

~~~java
static String status(int score) {
    if (score >= 50) {
        return "pass";
    }
    return "retry";
}
~~~

Một phương thức cũng có thể chuyển luồng bằng throw trên một nhánh:

~~~java
static int requirePositive(int number) {
    if (number <= 0) {
        throw new IllegalArgumentException("must be positive");
    }
    return number;
}
~~~

Đây là hợp lệ vì nhánh lỗi không hoàn thành bình thường. Compiler không cần chứng minh number luôn dương; nó chỉ kiểm tra đường điều khiển và kiểu trả về tương ứng.

**Phân biệt:** một phương thức void có thể kết thúc mà không có return. Còn trong lambda có block body trả về giá trị, các đường trả về phải thỏa yêu cầu phù hợp với functional interface đích.

## 8. Vòng lặp, break, continue và các đường thoát

Vòng lặp mang đến ít nhất hai loại cạnh: cạnh quay lại điều kiện/đầu vòng lặp và cạnh thoát vòng lặp. Với for-each, vòng lặp có thể chạy **0 lần** khi collection/array rỗng.

Ví dụ không hợp lệ:

~~~java
static int first(int[] values) {
    int value;
    for (int x : values) {
        value = x;
        break;
    }
    return value; // LỖI: mảng có thể rỗng
}
~~~

Đừng cho rằng có break thì phép gán bên trong vòng lặp chắc chắn đã xảy ra. Nếu values có độ dài 0, không có lần lặp nào.

Sửa bằng một đường dự phòng có nghĩa:

~~~java
static int firstOrMinusOne(int[] values) {
    for (int x : values) {
        return x;
    }
    return -1;
}
~~~

Với values rỗng, kết quả là -1. Với values có phần tử, trả phần tử đầu. Cả hai đường hợp lệ.

**continue** đưa điều khiển sang bước lặp tiếp theo (hoặc bước cập nhật của for thích hợp), nên các câu lệnh phía sau continue trong cùng block không được thực hiện trên nhánh đó. **break** thoát cấu trúc được phép; nó không đồng nghĩa với return khỏi phương thức. Java yêu cầu break/continue được dùng ở vị trí có đích hợp lệ; không thể đặt break ngoài vòng lặp/switch rồi kỳ vọng compiler suy đoán ý định.

### Ví dụ khó: một nhánh tiếp tục, nhánh kia gán

~~~java
static int sumNonNegative(int[] values) {
    int sum = 0;
    for (int value : values) {
        if (value < 0) {
            continue;
        }
        sum += value;
    }
    return sum;
}
~~~

sum được gán 0 trước vòng lặp. Mọi đường có thể tới return đều có giá trị hợp lệ cho sum, kể cả khi mảng rỗng hoặc tất cả phần tử âm. continue chỉ bỏ qua phần cộng ở lần lặp hiện tại.

## 9. Switch và yêu cầu bao phủ nhánh

Switch tạo nhiều cạnh theo giá trị được xét. Với **switch statement** truyền thống, case có thể fall through khi không có break; với **switch expression** (Java 17), switch phải có cách tạo giá trị cho mọi trường hợp hợp lệ.

Ví dụ switch expression hợp lệ với int:

~~~java
static String category(int code) {
    return switch (code) {
        case 1, 2 -> "small";
        case 3 -> "medium";
        default -> "other";
    };
}
~~~

Ở đây default xử lý những giá trị int ngoài các case liệt kê. Mỗi nhánh cung cấp String, nên switch expression có kiểu String.

Ví dụ không hợp lệ vì thiếu bao phủ:

~~~java
static String category(int code) {
    return switch (code) {
        case 1 -> "one";
        case 2 -> "two";
    }; // LỖI: switch expression không exhaustive với int
}
~~~

Có thể thêm default hoặc bao phủ đầy đủ miền giá trị theo các quy tắc Java tương ứng. Với enum, liệt kê tất cả hằng enum có thể đủ để switch expression được coi là exhaustive trong nhiều trường hợp; các tình huống tiến hóa enum qua phiên bản thư viện vẫn có thể gây hành vi runtime cần quan tâm. Trong bài này ta dùng default với int để dễ kiểm tra.

Với switch **statement** có các dấu : truyền thống, cần nhớ break nếu không muốn chạy sang case kế tiếp. Các ràng buộc reachability, definite assignment và việc một nhánh có thể hoàn thành bình thường được xét tùy hình thức switch. Đừng áp quy tắc của switch expression cho mọi switch statement.

## 10. Checked exceptions là một phần của phân tích đường điều khiển

Java phân biệt các ngoại lệ **checked** (nói ngắn gọn: Exception không thuộc RuntimeException và các subclass liên quan) với **unchecked** (RuntimeException và Error cùng các subclass của chúng). Khi một thao tác có thể ném checked exception, compiler yêu cầu phương thức **bắt** hoặc **khai báo throws** phù hợp.

Ví dụ chưa hợp lệ nếu đặt trong một lớp có import java.io.BufferedReader:

~~~java
static String load(java.io.BufferedReader reader) {
    return reader.readLine(); // LỖI: unreported exception IOException
}
~~~

BufferedReader.readLine() khai báo có thể ném IOException. Có thể khai báo:

~~~java
static String load(java.io.BufferedReader reader)
        throws java.io.IOException {
    return reader.readLine();
}
~~~

Hoặc xử lý ngoại lệ tại nơi gọi:

~~~java
static String load(java.io.BufferedReader reader) {
    try {
        return reader.readLine();
    } catch (java.io.IOException e) {
        return "read failed";
    }
}
~~~

Trong trường hợp bắt lỗi, bạn đang chọn chính sách ứng dụng: chuyển lỗi đọc thành một String dự phòng. Với ứng dụng thật, không nên nuốt lỗi tùy tiện; ghi log hoặc truyền lỗi tới tầng xử lý thích hợp có thể đúng hơn.

**try/finally** tạo thêm đường hoàn thành bình thường hoặc bất thường: finally chạy khi rời try trong các trường hợp thông thường, kể cả return hoặc exception, trừ những tình huống runtime chấm dứt đột ngột. Câu lệnh finally tự throw/return có thể thay đổi kết quả của luồng trước đó; tránh return trong finally vì rất dễ che lấp exception hoặc giá trị return.

Compiler kiểm tra checked exception theo ràng buộc ngôn ngữ, nhưng không bảo đảm một lời gọi sẽ không ném unchecked exception lúc chạy. Chẳng hạn, truy cập phần tử mảng sai chỉ số hoặc dereference null có thể ném lỗi runtime dù mã compile được.

## 11. Một dự án Java 17 hoàn chỉnh để quan sát mọi cơ chế

Tạo dự án:

~~~text
flow-lab/
├── src/
│   └── demo/
│       └── flow/
│           └── FlowDemo.java
└── out/
~~~

Tệp **src/demo/flow/FlowDemo.java**:

~~~java
package demo.flow;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public final class FlowDemo {
    private FlowDemo() {
    }

    static String grade(int score) {
        if (score >= 80) {
            return "A";
        }
        if (score >= 60) {
            return "B";
        }
        return "C";
    }

    static int firstEvenOrMinusOne(int[] values) {
        for (int value : values) {
            if (value % 2 == 0) {
                return value;
            }
        }
        return -1;
    }

    static String readFirstLine(String input) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(input))) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        final int result;
        boolean passed = true;

        if (passed) {
            result = 10;
        } else {
            result = 0;
        }

        System.out.println("Grade: " + grade(75));
        System.out.println("Even: "
                + firstEvenOrMinusOne(new int[] {3, 7, 8, 10}));
        System.out.println("Result: " + result);
        System.out.println("Line: " + readFirstLine("hello\nworld"));
    }
}
~~~

Đây là **một chương trình đầy đủ** với tên tệp/class/package nhất quán. Sử dụng terminal tại thư mục **flow-lab**, tạo out:

~~~bash
# Bash trên macOS/Linux
mkdir -p out
~~~

~~~powershell
# PowerShell trên Windows
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Biên dịch:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/flow/FlowDemo.java
~~~

Chạy:

~~~sh
java -cp out demo.flow.FlowDemo
~~~

**Stdout chính xác:**

~~~text
Grade: B
Even: 8
Result: 10
Line: hello
~~~

Giải thích từng phần:

- grade(75): nhánh score >= 80 không lấy; nhánh score >= 60 trả "B"; nếu cả hai nhánh đều false thì vẫn có return "C".
- firstEvenOrMinusOne: vòng lặp bỏ qua 3 và 7, trả 8; nếu không có số chẵn hoặc mảng rỗng, vẫn trả -1.
- final int result: cả nhánh passed=true và false đều gán đúng một lần; tại câu lệnh in, result đã definitely assigned.
- readFirstLine: readLine có thể ném IOException nên phương thức khai báo throws IOException. main cũng khai báo throws IOException vì lời gọi chưa catch. try-with-resources đảm bảo tài nguyên đóng theo quy tắc Java.
- Dữ liệu "hello\nworld" chứa newline; BufferedReader.readLine trả về "hello" mà không kèm ký tự ngắt dòng.

Chương trình dùng JDK API Java 17 và không phụ thuộc thư viện ngoài. Nếu bạn sửa mã nhưng chưa biên dịch lại, JVM có thể chạy bytecode cũ trong out; hãy biên dịch thành công trước khi kết luận kết quả.

## 12. Thực hành sửa lỗi từng loại

Các ví dụ dưới đây **cố tình không biên dịch** nếu bạn kích hoạt dòng được chú thích. Hãy thử trong bản sao riêng, giữ lại bản FlowDemo.java chạy tốt để dễ khôi phục.

### Bài A — Unreachable statement

Thêm một phương thức:

~~~java
static int fixed() {
    return 1;
    // System.out.println("after return"); // Bỏ // để tạo lỗi
}
~~~

Bỏ // và chạy javac. Kỳ vọng lỗi dạng **unreachable statement** tại lệnh in. Sửa bằng cách loại bỏ câu lệnh không thể tới được hoặc chuyển vị trí nó sang trước return nếu phù hợp logic.

### Bài B — Definite assignment

Thêm phương thức:

~~~java
static int charge(boolean active) {
    int amount;
    if (active) {
        amount = 50;
    }
    return amount; // LỖI BIÊN DỊCH
}
~~~

Kỳ vọng lỗi dạng **variable amount might not have been initialized**. Vẽ hai nhánh true/false: chỉ nhánh true gán. Thêm else gán một giá trị hoặc khai báo int amount = 0; trước if.

### Bài C — Blank final bị gán lại

~~~java
static int limit(boolean fast) {
    final int max;
    if (fast) {
        max = 20;
    }
    max = 10; // LỖI: có thể đã được gán
    return max;
}
~~~

Sửa bằng else, hoặc gán duy nhất qua toán tử ? : phù hợp.

### Bài D — Missing return

~~~java
static String direction(int x) {
    if (x > 0) {
        return "positive";
    }
    // LỖI: còn đường x <= 0 đi tới cuối phương thức
}
~~~

Kỳ vọng lỗi dạng **missing return statement**. Hãy thêm return "non-positive"; sau if hoặc dùng if/else có return ở cả hai nhánh.

### Bài E — Unreported checked exception

~~~java
static String line(BufferedReader reader) {
    return reader.readLine(); // LỖI: IOException
}
~~~

Sửa bằng throws IOException trong khai báo, hoặc catch IOException và có chính sách xử lý thích hợp. Kiểm tra cả nơi gọi phương thức sau khi thêm throws.

### Bài F — Vòng lặp không bảo đảm có phần tử

~~~java
static int last(int[] values) {
    int value;
    for (int number : values) {
        value = number;
    }
    return value; // LỖI: mảng có thể rỗng
}
~~~

Sửa bằng giá trị mặc định có chủ đích, kiểm tra điều kiện rỗng và throw phù hợp, hoặc thay đổi hợp đồng phương thức để phản ánh trường hợp không có dữ liệu.

**Nguyên tắc thử nghiệm:** đọc diagnostic javac đầy đủ và sửa nguyên nhân từng lỗi; vị trí, dấu mũ ^ và lời nhắn chính xác có thể khác giữa các phiên bản JDK.

## 13. Các lỗi tư duy phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| “Một nhánh có gán là đủ.” | Đọc biến local đòi hỏi definite assignment trên mọi đường có thể tới điểm đọc. |
| “Biến local int tự nhận 0.” | Local chưa được gán không thể tự động đọc giá trị mặc định; field có quy tắc khác. |
| “final chỉ là hằng compile-time.” | final cũng áp dụng cho biến nhận giá trị trong runtime, nhưng phải thỏa quy tắc gán. |
| “if(false) phải báo unreachable.” | Reachability có quy tắc đặc biệt cho if; while(false) thì thân vòng lặp bị từ chối. |
| “return nằm trong if là đủ.” | Nếu có đường qua if mà không return, phương thức trả giá trị có thể thiếu return. |
| “break và return giống nhau.” | break thoát vòng lặp/switch đích; return kết thúc lời gọi phương thức. |
| “Lặp ít nhất một lần.” | for/while/for-each có thể chạy 0 lần tùy điều kiện/dữ liệu. |
| “Compiler đã kiểm tra null và index đầy đủ.” | Mã có thể compile nhưng vẫn gặp NullPointerException, ArrayIndexOutOfBoundsException lúc chạy. |
| “Mọi exception bắt buộc catch/throws.” | Checked exception chịu quy tắc kiểm tra; unchecked exception không bắt buộc khai báo/bắt. |
| “Compiler biết biến boolean luôn true trong thực tế.” | Phân tích dùng quy tắc ngôn ngữ và thông tin chứng minh được tại compile-time, không chạy thử mọi đầu vào. |

## 14. Ranh giới giữa flow analysis và các bước khác của compiler

| Loại kiểm tra | Câu hỏi ví dụ | Lỗi/hiện tượng thường thấy |
| --- | --- | --- |
| Phân tích cú pháp | Có đủ dấu ngoặc, dấu ;? | ';' expected, illegal start of expression |
| Phân giải tên và kiểu | Method tồn tại? Gọi với kiểu đúng? | cannot find symbol, incompatible types |
| Reachability | Có câu lệnh nào bị chặn hoàn toàn theo quy tắc cấu trúc? | unreachable statement |
| Definite assignment | Đã chắc chắn gán trước khi đọc? | variable ... might not have been initialized |
| Definite unassignment | Có nguy cơ gán lại blank final? | variable ... might already have been assigned |
| Kiểm tra return | Method có thể hoàn thành bình thường mà thiếu giá trị? | missing return statement |
| Exception checking | Checked exception đã catch/throws phù hợp? | unreported exception ... must be caught or declared to be thrown |
| Runtime | Dữ liệu và trạng thái thực tế có hợp lệ? | NullPointerException, ArithmeticException, lỗi I/O... |

Một lỗi Java đôi khi liên quan nhiều quy tắc cùng lúc. Vị trí diagnostic compiler chọn không có nghĩa các pha bên trong hoạt động như những cỗ máy hoàn toàn tách biệt hay chạy theo một thứ tự cố định. Đây là cách phân loại để suy luận và xử lý lỗi.

### Giới hạn của phân tích tĩnh

Flow analysis không phải lời bảo đảm rằng chương trình an toàn tuyệt đối hoặc sẽ kết thúc:

- Vòng lặp có break được phép vẫn có thể chạy vô hạn với dữ liệu cụ thể.
- Một biến đã definitely assigned vẫn có thể chứa giá trị gây lỗi logic.
- Compiler không tự đảm bảo đối tượng khác null, mảng không vượt chỉ số hay request mạng thành công.
- Checked exception được khai báo hay bắt đúng không đồng nghĩa tác vụ I/O luôn thành công.
- Có thể tồn tại lỗi runtime do dependency, nạp lớp, tài nguyên, đồng thời hoặc dữ liệu thực tế.

Hãy kết hợp kiểm tra biên dịch với unit test, integration test và kiểm tra hợp đồng dữ liệu thích hợp.

## 15. Quy trình phân tích một diagnostic liên quan luồng

Khi javac báo lỗi, có thể làm theo các bước:

1. **Khoanh vùng điểm báo lỗi:** câu lệnh nào không tới được, biến nào đang được đọc, đường trả về nào còn thiếu, exception nào chưa được xử lý?
2. **Vẽ các nhánh tối thiểu:** từ đầu phương thức đến điểm lỗi; đánh dấu true/false của if, số lần lặp có thể bằng 0, break/continue, return/throw và try/catch/finally nếu có.
3. **Gắn trạng thái lên từng nhánh:** biến chưa gán/đã gán; blank final đã gán hay chưa; đường có tiếp tục bình thường được không; exception có thể thoát ra không.
4. **Hợp nhất thông tin:** với việc chắc chắn gán, phải đúng trên **mọi đường đi tới điểm đọc**; với missing return, phải kiểm tra xem có đường hoàn thành bình thường không.
5. **Sửa đúng hợp đồng:** thêm else/default, giá trị khởi tạo hợp lý, return/throw phù hợp hoặc xử lý checked exception; tránh thêm code chỉ để làm compiler im lặng mà sai nghiệp vụ.
6. **Biên dịch lại và chạy test:** xác nhận cả yêu cầu ngôn ngữ lẫn hành vi mong muốn.

Ví dụ nếu javac báo amount might not have been initialized, đừng sửa bằng cách đặt tùy tiện amount = 0; nếu nghiệp vụ thực ra phải từ chối trường hợp thiếu giá trị. Khi đó một nhánh throw có thể rõ nghĩa hơn.

## 16. Tự kiểm tra kiến thức

Tự trả lời trước khi chạy compiler:

1. Đoạn int x; if(flag) x=1; System.out.println(x); có chắc chắn biên dịch không? **Không**, đường flag=false chưa gán x.
2. Nếu cả if và else đều gán x, tại câu lệnh sau if/else có được đọc x? **Có**, miễn mọi nhánh đi tới điểm đọc đều gán hợp lệ.
3. Với final int x; if(flag) x=1; x=2;, vì sao sai? **Vì phép gán x=2 có thể gán lần thứ hai**.
4. Sau return; có được đặt lệnh println trực tiếp trong cùng block không? **Không**, lệnh đó unreachable.
5. Tại sao if(false) có body được chấp nhận còn while(false) body bị từ chối? **Vì quy tắc reachability của Java quy định khác nhau**.
6. Phương thức trả về int có một nhánh return và một nhánh throw có được chấp nhận? **Có**, nếu không còn đường kết thúc bình thường thiếu giá trị và các ràng buộc khác hợp lệ.
7. Vòng for-each có bảo đảm phần thân chạy ít nhất một lần? **Không**, mảng hoặc collection có thể rỗng.
8. readLine() ném IOException thì sửa bằng cách nào? **Catch hoặc khai báo throws** theo hợp đồng đã chọn.
9. Biên dịch thành công có bảo đảm không gặp lỗi null hoặc chia cho 0 khi chạy? **Không**.
10. Biến khai báo final có nhất thiết phải gán ngay tại dòng khai báo? **Không**; blank final có thể gán sau nếu đáp ứng definite assignment/unassignment.

**Tiêu chí hoàn thành:** bạn có thể giải thích một lỗi compiler liên quan luồng bằng các nhánh cụ thể, sửa nó có chủ đích, chạy được dự án FlowDemo.java, và phân biệt điều compiler chứng minh tại compile-time với điều vẫn cần kiểm tra khi chạy.

### Tài liệu chuẩn để đào sâu

Trong *Java Language Specification* (JLS), phần về **Blocks and Statements**, đặc biệt *Unreachable Statements*, mô tả các quy tắc reachability. Phần **Definite Assignment** quy định DA/DU cho biến và các cấu trúc điều khiển. Phần về **Exceptions** giải thích kiểm tra checked exception. Khi gặp trường hợp phức tạp liên quan switch, try/finally hoặc toán tử điều kiện, đối chiếu quy tắc JLS của **phiên bản Java đang dùng** thay vì suy luận bằng một quy tắc rút gọn.

Nguyên tắc cần giữ xuyên suốt: **đường điều khiển nào có thể dẫn tới điểm dùng dữ liệu, và compiler chứng minh được điều gì trên tất cả các đường đó?** Câu hỏi này kết nối các giai đoạn phân tích với khả năng đọc lỗi biên dịch Java trong dự án thực.
