# Tăng giảm tiền tố và hậu tố trong Java

> **Java core — language-basics / Gán và toán tử một ngôi**  
> **Phiên bản:** Java 17+; ví dụ độc lập, chỉ cần JDK.  
> **Mục tiêu:** Phân biệt `++x`, `x++`, `--x`, `x--`; xác định **giá trị của biểu thức** và **giá trị biến sau khi cập nhật**; sử dụng đúng trong vòng lặp và tránh những biểu thức chứa nhiều tác dụng phụ khó hiểu.

## 1. Bốn cách tăng giảm một đơn vị

`++` tăng giá trị biến thêm 1, còn `--` giảm đi 1. Hai toán tử này có hai vị trí viết:

| Cú pháp | Tên | Thay đổi biến | Giá trị của biểu thức |
| --- | --- | --- | --- |
| `++x` | Tăng **tiền tố** (*prefix increment*) | `x` tăng 1 | Giá trị **mới** |
| `x++` | Tăng **hậu tố** (*postfix increment*) | `x` tăng 1 | Giá trị **cũ** |
| `--x` | Giảm **tiền tố** (*prefix decrement*) | `x` giảm 1 | Giá trị **mới** |
| `x--` | Giảm **hậu tố** (*postfix decrement*) | `x` giảm 1 | Giá trị **cũ** |

Ví dụ ban đầu `x = 5`:

~~~java
int x = 5;
int before = x++; // before = 5, x = 6.
int after  = ++x; // x = 7, after = 7.
~~~

Cả tiền tố và hậu tố đều thay đổi biến **một đơn vị**. Khác biệt chỉ hiện rõ khi bạn **dùng giá trị do biểu thức trả ra** trong một phép gán, phép tính, điều kiện hoặc lời gọi phương thức.

## 2. Giá trị biểu thức khác với trạng thái biến sau câu lệnh

Xét hai đoạn độc lập:

~~~java
int a = 10;
int first = a++; // first = 10, a = 11.

int b = 10;
int second = ++b; // second = 11, b = 11.
~~~

- Với `a++`: lấy **giá trị cũ** 10 làm kết quả biểu thức, đồng thời tăng `a` thành 11.
- Với `++b`: tăng `b` thành 11 rồi cho biểu thức giá trị **mới** 11.

Giảm tiền tố/hậu tố tương tự:

~~~java
int a = 10;
int old = a--;  // old = 10, a = 9.

int b = 10;
int now = --b;  // now = 9, b = 9.
~~~

Nếu chỉ cần tăng/giảm biến mà **không sử dụng kết quả biểu thức**, hai cách là tương đương về giá trị sau câu lệnh:

~~~java
int count = 0;
count++; // count = 1.
++count; // count = 2.
count--; // count = 1.
--count; // count = 0.
~~~

Đừng hiểu “hậu tố thực hiện sau” là biến sẽ chỉ thay đổi ở **câu lệnh tiếp theo**: tác dụng tăng/giảm đã xảy ra trong quá trình đánh giá biểu thức hiện tại.

## 3. Có thể áp dụng lên đâu?

Toán hạng của `++` và `--` phải là **biến có thể cập nhật** thuộc kiểu số phù hợp (bao gồm `char` và các lớp bao số qua unboxing/boxing). Ví dụ hợp lệ:

~~~java
int counter = 2;
counter++;

int[] scores = {5, 8};
scores[0]++;

class Box {
    int size = 1;
}
Box box = new Box();
++box.size;

char letter = 'A';
letter++; // 'B'.
~~~

Không thể tăng một literal, giá trị tính toán không phải biến, biến `final`, hoặc kiểu `boolean`:

~~~java
// KHÔNG BIÊN DỊCH:
// 5++;
// (counter + 1)++;
// final int fixed = 2;
// fixed++;
// boolean enabled = true;
// enabled++;
~~~

Đối với wrapper, giá trị `null` cần chú ý:

~~~java
Integer boxed = 4;
boxed++; // Hợp lệ: unbox, tăng, rồi box lại thành Integer 5.

// Integer absent = null;
// absent++; // Nếu chạy: NullPointerException khi unboxing.
~~~

Thao tác với `byte`, `short` hay `char` vẫn trả kết quả theo kiểu biến; việc tăng giảm có thể vượt miền và làm thay đổi/đảo giá trị, không tự ném exception tràn số.

## 4. Dùng trong biểu thức và thứ tự đánh giá

Java đánh giá toán hạng theo quy tắc xác định. Ví dụ:

~~~java
int n = 1;
int result = n++ + ++n;
// n++ trả 1, n trở thành 2.
// ++n tăng n thành 3 và trả 3.
// result = 1 + 3 = 4; n = 3.
~~~

Kết quả này **được Java quy định**, nhưng diễn đạt nhiều cập nhật lên cùng biến trong một biểu thức như vậy rất khó đọc và dễ sửa sai. Ưu tiên tách ra:

~~~java
int n = 1;
int oldValue = n;
n++;
n++;
int newValue = n;
int result = oldValue + newValue; // result = 4.
~~~

Một trường hợp phổ biến, dễ hiểu hơn, là **dùng chỉ số mảng rồi tăng chỉ số**:

~~~java
int[] numbers = {10, 20, 30};
int i = 0;
int selected = numbers[i++]; // selected = 10, i = 1.
~~~

`i++` trả **0** để truy cập phần tử đầu tiên, sau đó `i` trở thành 1. Tương đương ý định với:

~~~java
int selected = numbers[i];
i++;
~~~

**Khuyến nghị:** Chỉ dùng tiền tố/hậu tố bên trong biểu thức khi người đọc có thể hiểu ngay cả **giá trị biểu thức** lẫn **tác dụng phụ**. Khi nhiều biến bị thay đổi, dùng câu lệnh độc lập hoặc biến trung gian.

## 5. Vòng lặp `for` và `while`

Trong vòng `for`, phần cập nhật thường không cần giá trị do `i++` hay `++i` trả ra:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println("index=" + i);
}
~~~

Ở đây đổi `i++` thành `++i` **không đổi chuỗi giá trị được in**, vì kết quả biểu thức tăng không được sử dụng. Cả hai đều tăng `i` một đơn vị ở cuối mỗi lượt.

Vòng `while` cũng vậy:

~~~java
int remaining = 3;
while (remaining > 0) {
    System.out.println(remaining);
    remaining--;
}
~~~

Không nên chọn tiền tố thay hậu tố chỉ vì nghĩ nó “luôn nhanh hơn”. Với kiểu nguyên primitive trong Java 17, chọn cú pháp **diễn đạt rõ ý định**; hiệu năng thực tế phụ thuộc compiler/JIT và ngữ cảnh, không dựa vào mẹo này.

## 6. Tràn số và những bẫy khác

Các toán tử này không tự kiểm tra tràn cho phép tăng/giảm nguyên thông thường:

~~~java
int maximum = Integer.MAX_VALUE;
maximum++; // -2147483648, không tự ném ArithmeticException.

byte tiny = 127;
tiny++; // -128 vì byte có miền -128..127.
~~~

Nếu yêu cầu **phát hiện tràn** thay vì chấp nhận kết quả quay vòng, dùng:

~~~java
int next = Math.incrementExact(Integer.MAX_VALUE); // Ném ArithmeticException.
int prev = Math.decrementExact(Integer.MIN_VALUE); // Ném ArithmeticException.
~~~

Một bẫy khác là kết hợp phép gán với hậu tố:

~~~java
int n = 5;
int previous = n++; // Dễ hiểu: previous=5, n=6.

// Tránh viết câu khó đọc kiểu: n = n++;
// Phép gán ngoài có thể ghi đè giá trị vừa cập nhật.
~~~

Việc `n = n++` không làm tăng giá trị `n` cuối cùng: `n++` trả **giá trị cũ**, rồi phép gán ngoài gán lại giá trị cũ đó. Nếu muốn tăng, chỉ cần `n++;` hoặc `n += 1;`.

## 7. Ví dụ Java 17+ runnable

Tạo tệp **PrefixPostfixDemo.java**:

~~~java
public final class PrefixPostfixDemo {
    public static void main(String[] args) {
        int a = 5;
        int postIncrement = a++;
        System.out.println("postIncrement=" + postIncrement + ",a=" + a);

        int b = 5;
        int preIncrement = ++b;
        System.out.println("preIncrement=" + preIncrement + ",b=" + b);

        int c = 5;
        int postDecrement = c--;
        System.out.println("postDecrement=" + postDecrement + ",c=" + c);

        int d = 5;
        int preDecrement = --d;
        System.out.println("preDecrement=" + preDecrement + ",d=" + d);

        int count = 0;
        count++;
        ++count;
        count--;
        --count;
        System.out.println("standaloneCount=" + count);

        int[] numbers = {10, 20, 30};
        int index = 0;
        int selected = numbers[index++];
        System.out.println("arraySelection=" + selected + ",index=" + index);

        int n = 1;
        int combined = n++ + ++n;
        System.out.println("combined=" + combined + ",n=" + n);

        int overwritten = 5;
        overwritten = overwritten++;
        System.out.println("assignmentTrap=" + overwritten);

        byte tiny = 127;
        tiny++;
        System.out.println("byteOverflow=" + tiny);

        int maximum = Integer.MAX_VALUE;
        maximum++;
        System.out.println("intOverflow=" + maximum);

        try {
            Math.incrementExact(Integer.MAX_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("incrementExact=ArithmeticException");
        }

        Integer boxed = 4;
        boxed++;
        System.out.println("boxed=" + boxed);

        for (int i = 0; i < 3; i++) {
            System.out.println("loop=" + i);
        }
    }
}
~~~

Chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 PrefixPostfixDemo.java
java PrefixPostfixDemo
~~~

**Expected stdout chính xác:**

~~~text
postIncrement=5,a=6
preIncrement=6,b=6
postDecrement=5,c=4
preDecrement=4,d=4
standaloneCount=0
arraySelection=10,index=1
combined=4,n=3
assignmentTrap=5
byteOverflow=-128
intOverflow=-2147483648
incrementExact=ArithmeticException
boxed=5
loop=0
loop=1
loop=2
~~~

Các dòng `postIncrement` và `preIncrement` cho thấy biến đều tăng nhưng **giá trị được trả ra** khác nhau; `combined` xác nhận thứ tự cập nhật, `assignmentTrap` cảnh báo kết hợp hậu tố với gán ngoài, còn `byteOverflow` và `intOverflow` minh họa tràn không tự ném ngoại lệ.

## 8. Bài tập tự luyện

**Bài 1.** Cho `int x = 8; int y = x++;`. Xác định `x` và `y`. So sánh với `int x = 8; int y = ++x;`.

**Bài 2.** Cho `int x = 8; int y = x--;` và `int x = 8; int y = --x;`. Hai trường hợp khác nhau ở giá trị nào?

**Bài 3.** Dự đoán `int i = 1; int result = i++ + ++i;`. Viết lại thành nhiều câu lệnh mà không thay đổi kết quả.

**Bài 4.** Với `int[] arr = {4, 5, 6}; int i = 0;`, giải thích `arr[i++]` trả phần tử nào và `i` sau đó bằng bao nhiêu.

**Bài 5.** Vì sao `int x = 5; x = x++;` vẫn để `x` bằng 5? Viết cách tăng đơn giản hơn.

**Bài 6.** Kiểm tra `byte x = 127; x++;` và nêu cách dùng `Math.incrementExact` khi chương trình cần phát hiện tràn `int`.

### Ghi nhớ

**Tiền tố `++x`/`--x` trả giá trị sau khi cập nhật; hậu tố `x++`/`x--` trả giá trị trước khi cập nhật.** Cả hai cùng thay đổi biến trong biểu thức hiện tại. Nếu không dùng giá trị biểu thức, chọn cách dễ đọc. Tránh trộn nhiều lần tăng giảm với phép gán và tác dụng phụ khác; cân nhắc `Math.incrementExact`/`decrementExact` khi yêu cầu phát hiện tràn.
