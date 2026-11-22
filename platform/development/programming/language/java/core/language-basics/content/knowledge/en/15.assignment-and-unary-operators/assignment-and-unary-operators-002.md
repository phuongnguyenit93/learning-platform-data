# Gán liên tiếp và lý do nên hạn chế trong Java

> **Java core — language-basics / Gán và toán tử một ngôi**  
> **Phiên bản:** Java 17+; ví dụ một file, không cần thư viện ngoài.  
> **Mục tiêu:** Hiểu `a = b = c = value` được nhóm như thế nào, vì sao biểu thức gán có giá trị và phải tương thích kiểu; nhận diện vấn đề về khả năng đọc, thứ tự đánh giá, tác dụng phụ và các tham chiếu cùng trỏ tới một đối tượng.

## 1. Gán liên tiếp là gì?

Một phép gán `left = right` lưu giá trị của vế phải vào biến được chỉ định ở vế trái. Java cho phép **biểu thức gán** nằm ở vế phải của phép gán khác:

~~~java
int a, b, c;
a = b = c = 7;
System.out.println(a + "," + b + "," + c); // 7,7,7
~~~

Toán tử gán `=` **kết hợp từ phải sang trái** (*right-associative*). Cách nhóm của dòng trên là:

~~~text
a = (b = (c = 7))
~~~

Diễn giải trường hợp các biến đơn giản:

1. `c = 7` gán 7 cho `c`; toàn bộ biểu thức này có giá trị 7.
2. `b = (c = 7)` nhận 7 rồi gán vào `b`.
3. `a = (b = (c = 7))` nhận 7 rồi gán vào `a`.

Kết thúc, cả ba biến đều bằng 7. **Gán liên tiếp không khai báo biến mới**: `a`, `b`, `c` phải tồn tại trước và kiểu của chúng phải phù hợp.

## 2. Biểu thức gán có giá trị và có kiểu

Với phép gán đơn giản, biểu thức `variable = expression` mang **giá trị đã gán** và có kiểu của biến bên trái. Vì thế có thể dùng nó bên trong phép gán khác:

~~~java
int left, right;
left = right = 12; // Cả hai đều nhận 12.
~~~

Không phải mọi phép gán liên tiếp đều bắt buộc các biến có cùng kiểu. Từng bước gán phải hợp lệ theo quy tắc chuyển kiểu Java:

~~~java
int whole;
double decimal;
decimal = whole = 3; // Hợp lệ: whole nhận int 3, decimal nhận double 3.0.
~~~

Ngược lại:

~~~java
int whole;
double decimal;
// whole = decimal = 3.5; // Lỗi biên dịch: không thể gán double vào int.
~~~

**Điểm cần nhớ:** Java không tự suy đoán một kiểu chung tùy ý chỉ vì phép gán nằm trên cùng một dòng. Dấu ngoặc cho biết cách **nhóm**, còn quy tắc tương thích kiểu vẫn được áp dụng ở mỗi phép gán.

Gán liên tiếp có thể chứa biểu thức khác:

~~~java
int a, b, c = 2;
a = b = c + 5; // a = 7, b = 7, c vẫn là 2.
~~~

Ở đây `c + 5` **không gán lại** `c`. Phân biệt `c + 5` với `c += 5`: phép thứ hai thay đổi `c`.

## 3. Biến tham chiếu: gán cùng object, không nhân bản object

Với kiểu tham chiếu, gán liên tiếp có thể khiến nhiều biến cùng trỏ đến **một object**:

~~~java
int[] first, second;
first = second = new int[] {10, 20};

first[0] = 99;
System.out.println(second[0]); // 99
~~~

Dòng `new int[] {10, 20}` tạo **một mảng duy nhất**. Hai phép gán chỉ sao chép giá trị **tham chiếu**, không tạo hai mảng độc lập. Vì thế sửa phần tử qua `first` cũng được nhìn thấy qua `second`.

Nếu cần hai đối tượng riêng, hãy tạo/copy có chủ đích, chẳng hạn:

~~~java
int[] first = {10, 20};
int[] second = first.clone(); // Mảng mới với các phần tử được sao chép.
~~~

Với object có trạng thái thay đổi được, sử dụng gán liên tiếp mà không để ý đến việc chia sẻ tham chiếu có thể tạo lỗi khó truy vết. Với các kiểu bất biến như `String`, việc chia sẻ tham chiếu thường ít rủi ro hơn, nhưng vẫn phải hiểu ngữ nghĩa gán.

## 4. Vì sao nên hạn chế gán liên tiếp?

| Vấn đề | Ví dụ hoặc hậu quả | Cách diễn đạt rõ hơn |
| --- | --- | --- |
| Khó đọc cách dữ liệu đi qua biến | `a = b = c = compute();` | Tạo giá trị trung gian có tên, rồi gán rõ từng biến |
| Dễ bỏ sót kiểu không tương thích | `int x; double y; x = y = 1.5;` | Chuyển kiểu có chủ đích, tách từng phép gán |
| Che khuất việc nhiều biến cùng tham chiếu | `x = y = new int[3];` | Đặt tên thể hiện chia sẻ, hoặc clone/tạo riêng |
| Trộn tác dụng phụ | `array[i++] = array[i++] = 8;` | Tách việc chọn chỉ số và việc gán |
| Khó đặt breakpoint/log theo bước | Một dòng sửa nhiều biến | Mỗi câu lệnh sửa một biến khi nghiệp vụ phức tạp |
| Dễ hiểu sai giữa nhóm và thứ tự đánh giá | Gán kết hợp phải không có nghĩa mọi biểu thức con chạy từ phải sang trái | Tách bước hoặc dùng ngoặc kết hợp với biến trung gian |

Gán liên tiếp **không sai về kỹ thuật**. Với ví dụ ngắn `a = b = 0;`, ý định có thể rất rõ. Nhưng khi liên quan đến trạng thái, object, lời gọi hàm hoặc chỉ số mảng, **ưu tiên khả năng đọc và kiểm thử hơn số dòng ít nhất**.

### Một lời gọi không chạy ba lần

~~~java
int a, b, c;
a = b = c = calculate();
~~~

`calculate()` được gọi **một lần**; kết quả của nó được dùng cho ba phép gán. Nếu muốn ba giá trị được tính **độc lập**, phải gọi hàm riêng cho mỗi biến:

~~~java
a = calculate();
b = calculate();
c = calculate();
~~~

Đây là khác biệt nghiệp vụ quan trọng khi `calculate()` đọc thời gian, sinh số ngẫu nhiên hoặc thay đổi trạng thái.

## 5. Tính kết hợp không phải thứ tự đánh giá tác dụng phụ

`a = b = c = value` nhóm **từ phải sang trái**, nhưng với một **vế trái phức tạp** như truy cập mảng, Java vẫn có quy tắc về **thứ tự đánh giá biểu thức**.

~~~java
int[] values = {1, 2, 3};
int i = 0;

values[i++] = values[i++] = 8;
~~~

Ở phép gán mảng bên ngoài, Java đánh giá tham chiếu mảng và **chỉ số bên trái** trước khi đánh giá biểu thức gán ở bên phải. Lần `i++` đầu chọn `values[0]`; lần thứ hai chọn `values[1]`; sau đó cả hai vị trí nhận 8. Kết quả là `values = {8, 8, 3}` và `i = 2`.

Đừng suy từ “gán kết hợp phải” rằng lần `i++` nằm bên phải **luôn** chạy trước. Độ kết hợp quyết định **cây biểu thức**, còn thứ tự đánh giá có quy tắc khác.

**Cách viết rõ hơn:**

~~~java
int firstIndex = i++;
int secondIndex = i++;
values[secondIndex] = 8;
values[firstIndex] = 8;
~~~

Đoạn tách bước có thể dài hơn nhưng cho phép quan sát/chỉnh sửa và đặt breakpoint tại từng bước. Thực tế, nếu không cần tác dụng phụ của `i++`, hãy chọn chỉ số tường minh và tránh phép gán lồng nhau.

## 6. Chương trình Java 17+ runnable

Tạo file **ChainedAssignmentDemo.java**:

~~~java
public final class ChainedAssignmentDemo {
    private static int callCount;

    private static int calculate() {
        callCount++;
        return 42;
    }

    public static void main(String[] args) {
        int a, b, c;
        a = b = c = 7;
        System.out.println("basic=" + a + "," + b + "," + c);

        a = b = c + 5;
        System.out.println("expression=" + a + "," + b + "," + c);

        a = b = c = calculate();
        System.out.println("calculated=" + a + "," + b + "," + c);
        System.out.println("calls=" + callCount);

        int whole;
        double decimal;
        decimal = whole = 3;
        System.out.println("mixedTypes=" + whole + "," + decimal);

        boolean active, visible;
        active = visible = true;
        System.out.println("booleans=" + active + "," + visible);

        String left, right;
        left = right = new String("ready");
        System.out.println("sameStringReference=" + (left == right));

        int[] first, second;
        first = second = new int[] {10, 20};
        first[0] = 99;
        System.out.println("sharedArray=" + first[0] + "," + second[0]);

        int[] indexed = {1, 2, 3};
        int i = 0;
        indexed[i++] = indexed[i++] = 8;
        System.out.println("indexed=" + indexed[0] + ","
                + indexed[1] + "," + indexed[2]);
        System.out.println("indexAfter=" + i);
    }
}
~~~

Chạy tại thư mục chứa tệp (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ChainedAssignmentDemo.java
java ChainedAssignmentDemo
~~~

**Expected stdout chính xác:**

~~~text
basic=7,7,7
expression=12,12,7
calculated=42,42,42
calls=1
mixedTypes=3,3.0
booleans=true,true
sameStringReference=true
sharedArray=99,99
indexed=8,8,3
indexAfter=2
~~~

Đối chiếu: `expression=12,12,7` cho thấy `c` không đổi khi chỉ dùng `c + 5`; `calls=1` xác nhận hàm được gọi một lần; `sameStringReference=true` và `sharedArray=99,99` cho thấy gán chia sẻ tham chiếu. `indexed` minh họa vì sao có tác dụng phụ trong vế trái thì không nên chỉ dựa vào cách nhóm từ phải.

## 7. Cách thay thế dễ đọc hơn

Nếu kết quả dùng nhiều lần, cân nhắc tên biến có nghĩa:

~~~java
int defaultLimit = 100;
int readLimit = defaultLimit;
int writeLimit = defaultLimit;
~~~

Để gán các biến ban đầu cùng một giá trị một cách đơn giản:

~~~java
int x = 0;
int y = 0;
~~~

Khi gọi hàm có side effect, hãy quyết định rõ là **một kết quả chia sẻ** hay **các kết quả tính riêng**. Khi làm việc với object/mảng, hãy quyết định rõ **chia sẻ tham chiếu** hay **tạo bản sao**.

Không nhất thiết loại bỏ mọi `a = b = 0;`; hãy tránh khi dấu `=` xuất hiện quá nhiều, biến có ý nghĩa nghiệp vụ khác nhau, hoặc việc gán tác động đến những trạng thái cần truy vết riêng.

## 8. Bài tập tự kiểm tra

**Bài 1.** Viết lại `a = b = c = 5;` có dấu ngoặc thể hiện cách nhóm. Giá trị của từng biến sau dòng lệnh là gì?

**Bài 2.** Cho `int c = 2; int a, b; a = b = c + 5;`. Giá trị `a`, `b`, `c` thế nào? Điều gì thay đổi nếu viết `a = b = (c += 5);`?

**Bài 3.** Vì sao `double d; int i; d = i = 3;` hợp lệ nhưng `i = d = 3.5;` không hợp lệ?

**Bài 4.** Với hai biến mảng `x` và `y` được gán từ cùng một `new int[2]`, sửa `x[0]` có làm `y[0]` thay đổi không? Viết cách tạo mảng riêng nếu không muốn chia sẻ.

**Bài 5.** Giải thích vì sao biểu thức `array[i++] = array[i++] = 8;` khó bảo trì dù Java quy định rõ cách nhóm và thứ tự đánh giá.

### Ghi nhớ

**Gán liên tiếp dùng tính kết hợp phải của `=`: `a = b = c = value` nhóm thành `a = (b = (c = value))`.** Mỗi phép gán phải tương thích kiểu; giá trị tham chiếu được **sao chép**, không phải object được nhân bản. **Hạn chế gán liên tiếp** khi có nhiều trạng thái, tác dụng phụ, mảng hoặc object chia sẻ, vì tách các câu lệnh thường làm ý định rõ hơn và dễ kiểm thử.
