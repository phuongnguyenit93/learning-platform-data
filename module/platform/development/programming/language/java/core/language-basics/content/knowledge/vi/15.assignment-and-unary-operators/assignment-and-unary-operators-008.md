# Tránh nhiều phép tăng giảm trên cùng biến trong một biểu thức — Java 17+

## 1. Mục tiêu

Trong Java, toán tử `++` tăng biến số lên 1, `--` giảm biến số đi 1. Cả hai **vừa trả một giá trị biểu thức, vừa thay đổi biến**. Khi cùng một biến bị tăng/giảm và đọc nhiều lần trong một biểu thức, chương trình có thể có kết quả hợp lệ nhưng rất khó đọc và dễ sửa sai.

~~~java
int i = 1;
int result = i++ + ++i;
System.out.println(result); // 4
System.out.println(i);      // 3
~~~

**Java 17 xác định rõ kết quả này**, không phải “undefined behavior”. Tuy nhiên, người đọc phải theo dõi nhiều trạng thái trung gian của `i` trong cùng một dòng; vì thế **không nên dùng kiểu biểu thức này trong code nghiệp vụ**.

Sau bài, bạn cần: phân biệt hậu tố/tiền tố; dự đoán thứ tự đánh giá trong Java; nhận diện bẫy với gán, lời gọi phương thức, mảng và điều kiện; viết lại biểu thức có nhiều side effect thành các bước dễ kiểm tra.

## 2. Nhắc nhanh ngữ nghĩa cần dùng để nhận diện mã khó đọc

Hậu tố `i++`/`i--` cung cấp **giá trị cũ** và cập nhật biến; tiền tố `++i`/`--i` cung cấp **giá trị mới** sau cập nhật. Tất cả diễn ra trong lần đánh giá hiện tại. Đây là phần kiến thức nền của bài “Tăng giảm tiền tố và hậu tố”; kỹ năng theo dõi riêng hai giá trị cũng đã được luyện ở bài ngay trước.

Bài này tập trung vào **vấn đề phát sinh khi một biến bị cập nhật nhiều lần trong cùng biểu thức**: thứ tự đánh giá, các đối số phương thức, truy cập mảng, short-circuit, exception và cách refactor mà không đổi hành vi. Riêng `i++` trong phần cập nhật vòng `for` hoặc câu lệnh `i++;` đơn giản vẫn thường rõ nghĩa, không cần né tránh.

## 3. Vì sao `i++ + ++i` cho kết quả 4?

~~~java
int i = 1;
int result = i++ + ++i;
~~~

Java đánh giá các toán hạng của `+` **từ trái sang phải**:

| Bước | Thao tác | Giá trị của toán hạng | `i` sau bước |
|---|---|---:|---:|
| 1 | `i++` | 1 (giá trị cũ) | 2 |
| 2 | `++i` | 3 (giá trị mới) | 3 |
| 3 | Cộng `1 + 3` | 4 | 3 |

Vì vậy `result == 4` và `i == 3`.

Một ví dụ cũng dễ nhầm:

~~~java
int j = 1;
int sum = j++ + j++;
System.out.println(sum); // 3 = 1 + 2
System.out.println(j);   // 3
~~~

**Không kết luận đây là kết quả không xác định.** Java quy định thứ tự đánh giá; rủi ro thực tế là phép tính nhiều tác dụng phụ **khó dự đoán bằng mắt, khó review và khó bảo trì**. Đặc biệt, đừng áp dụng trực giác từ ngôn ngữ khác để giải thích Java.

### Thứ tự ưu tiên không đồng nghĩa thứ tự thực hiện mọi toán hạng

Ví dụ `a++ + b++ * c++`: phép nhân được **nhóm** trước phép cộng theo precedence, nhưng Java vẫn đánh giá các toán hạng theo quy tắc xác định từ trái sang phải. Để tránh phải suy luận dài, hãy **tách các lần tăng thành câu lệnh rõ ràng**.

## 4. Bẫy `i = i++`: tăng rồi gán đè bằng giá trị cũ

~~~java
int i = 5;
i = i++;
System.out.println(i); // 5
~~~

Diễn biến:

1. Biểu thức hậu tố `i++` trả về **5**, đồng thời tăng `i` lên **6**.
2. Phép gán `i = ...` bên ngoài lại gán **5** trở lại `i`.
3. Cuối cùng `i` vẫn bằng **5**.

So sánh:

~~~java
int a = 5;
a++;           // a=6

int b = 5;
b = ++b;       // b=6, nhưng cách viết dư thừa
~~~

**Cách đúng:** nếu mục đích là tăng, hãy viết `i++;` hoặc `i += 1;`. Nếu mục đích là gán, hãy tính giá trị mong muốn rồi `i = value;`. Đừng kết hợp hai hành động lên cùng biến mà không cần thiết.

## 5. Đọc lại biến sau khi tăng trong cùng biểu thức

~~~java
int i = 3;
int value = i++ + i;

System.out.println(value); // 7 = 3 + 4
System.out.println(i);     // 4
~~~

Vế trái cung cấp giá trị cũ `3` rồi `i` thành `4`; vế phải đọc `4`.

Mặc dù đoạn code có quy tắc rõ, có thể viết:

~~~java
int i = 3;
int oldValue = i;
i++;
int currentValue = i;
int value = oldValue + currentValue;
~~~

Phiên bản tách bước dài hơn một chút nhưng **thể hiện chính xác biến nào là giá trị cũ và biến nào là giá trị mới**. Nếu nghiệp vụ không yêu cầu cả hai, hãy đơn giản hóa thêm.

## 6. Nhiều `++` trong đối số phương thức

Java đánh giá các **đối số của lời gọi phương thức từ trái sang phải**, trước khi thực hiện thân phương thức:

~~~java
static void show(int left, int right) {
    System.out.println(left + "," + right);
}

// Trong main:
int i = 1;
show(i++, ++i); // In "1,3"; i kết thúc bằng 3
~~~

Thứ tự:

1. Đối số đầu `i++`: truyền `1`, `i` thành 2.
2. Đối số hai `++i`: `i` thành 3, truyền `3`.
3. Method nhận `(1, 3)`.

**Nên viết:**

~~~java
int i = 1;
int first = i;
i++;
i++;
int second = i;
show(first, second);
~~~

Điều này giữ nguyên giá trị truyền vào và thứ tự thay đổi trạng thái trong ví dụ, đồng thời giúp người đọc không phải tính nhẩm thứ tự của các đối số.

Nếu method nhận nhiều biểu thức phức tạp chứa I/O hoặc sửa trạng thái, tách chúng thành biến tạm còn giúp xác định **thao tác nào được thực hiện trước**.

## 7. Chỉ số mảng thay đổi ở những vị trí nào?

~~~java
int[] items = {10, 20, 30};
int index = 0;
int total = items[index++] + items[index++];

System.out.println(total); // 30 = items[0] + items[1]
System.out.println(index); // 2
~~~

Với hai lần `index++`, Java lần lượt dùng chỉ số **0**, rồi **1**. Không nên làm người đọc nhầm rằng biểu thức đang đọc cùng một phần tử hai lần.

Phiên bản dễ bảo trì:

~~~java
int first = items[index];
index++;
int second = items[index];
index++;
int total = first + second;
~~~

Dạng `array[index++]` đơn lẻ có thể phù hợp trong thuật toán tuần tự rõ ràng; **nguy cơ tăng mạnh khi dùng cùng biến chỉ số nhiều lần trong một biểu thức**.

Đặc biệt:

~~~java
int[] values = {10, 20};
int index = 0;
values[index++]++;  // values[0] thành 11, index thành 1
~~~

Ở đây có **hai tác dụng phụ khác nhau**: tăng `index` để chọn phần tử và tăng chính **phần tử mảng**. Nếu cần giải thích logic cho đồng đội, cách tách bước thường sáng sủa hơn:

~~~java
int selectedIndex = index;
index++;
values[selectedIndex]++;
~~~

## 8. Short-circuit khiến một phép tăng có thể không chạy

Với `&&`, khi vế trái là `false`, Java **không đánh giá** vế phải. Với `||`, khi vế trái là `true`, Java cũng bỏ qua vế phải:

~~~java
int i = 0;
boolean result = false && (i++ > 0);

System.out.println(result); // false
System.out.println(i);      // 0: i++ không chạy
~~~

Nếu điều kiện đầu true:

~~~java
int i = 0;
boolean result = true && (i++ == 0);

System.out.println(result); // true
System.out.println(i);      // 1
~~~

Phân biệt với `&` trên `boolean`: `&` **đánh giá cả hai toán hạng**, nên:

~~~java
int i = 0;
boolean result = false & (i++ > 0);

System.out.println(result); // false
System.out.println(i);      // 1
~~~

| Toán tử | Vế phải có thể bị bỏ qua? | Tác động đến `i++` trong vế phải |
|---|---|---|
| `&&` | Có, khi vế trái false | Có thể không tăng |
| `||` | Có, khi vế trái true | Có thể không tăng |
| `&` trên boolean | Không | Luôn đánh giá vế phải khi tới biểu thức |
| `|` trên boolean | Không | Luôn đánh giá vế phải khi tới biểu thức |

**Khuyến nghị:** điều kiện boolean nên diễn đạt **điều kiện**, còn cập nhật trạng thái nên ở câu lệnh riêng, trừ những trường hợp thuật toán thực sự yêu cầu side effect và đã được diễn giải rõ.

## 9. Exception có thể để lại trạng thái đã thay đổi một phần

~~~java
int count = 0;
int divisor = 0;

try {
    int answer = count++ + 10 / divisor;
    System.out.println(answer);
} catch (ArithmeticException ex) {
    System.out.println(count); // 1
}
~~~

`count++` đã được đánh giá, nên `count` tăng từ 0 lên 1 **trước khi** phép chia nguyên cho 0 ném `ArithmeticException`. Bắt ngoại lệ không tự hoàn tác phép tăng.

Nếu toàn bộ thao tác phải hoặc **cùng thành công hoặc cùng thất bại**, hãy **validate trước khi thay đổi trạng thái** hoặc dùng cơ chế transaction/rollback theo yêu cầu; dấu ngoặc và `try/catch` không tạo ra tính nguyên tử.

## 10. Dùng `++`/`--` đúng chỗ; không né quá mức

**Có thể dùng** khi ý định cập nhật hiển nhiên:

~~~java
int count = 0;
count++;
count--;
~~~

Vòng lặp đơn giản:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

Tuy nhiên, tránh:

~~~java
// Khó đọc: nhiều lần tác động vào cùng biến trong một biểu thức
// int result = i++ + ++i - i--;

// Khó audit: vừa sửa biến vừa tạo đối số
// send(i++, ++i);
~~~

Dấu ngoặc như `(i++) + (++i)` có thể làm rõ **cách nhóm** nhưng **không loại bỏ tác dụng phụ**. Việc thêm ngoặc không giải quyết vấn đề “có quá nhiều thay đổi trạng thái trong một biểu thức”.

## 11. Cách refactor mà không đổi hành vi

Ví dụ trước:

~~~java
int i = 1;
int result = i++ + ++i;
~~~

Sau:

~~~java
int i = 1;

int left = i;  // Lấy giá trị mà i++ sẽ trả
i++;          // Thực hiện tăng hậu tố

i++;          // Thực hiện tăng của ++i
int right = i; // Lấy giá trị mới

int result = left + right;
~~~

Hai phiên bản đều cho `result = 4`, `i = 3`. Phiên bản sau cho phép đặt breakpoint giữa các lần cập nhật.

Khi thay code thật, cần giữ các bất biến:

1. **Giữ thứ tự đánh giá** các method/toán hạng có side effect.
2. **Giữ số lần cập nhật** nếu chưa chủ động thay đổi thuật toán.
3. Phân biệt **giá trị cũ** và **giá trị mới** của tiền tố/hậu tố.
4. Không tự dời câu lệnh qua các nhánh `&&`, `||`, `?:`, `if` hoặc vị trí có thể ném exception.
5. Viết test kiểm tra **kết quả biểu thức lẫn trạng thái biến sau biểu thức**.

Nếu nhiều lần tăng giảm không thực sự cần thiết, phương án tốt nhất là **giảm số side effect** chứ không chỉ sao chép chúng sang nhiều dòng.

## 12. Một số bẫy kỹ thuật liên quan

| Trường hợp | Nguy cơ | Hướng xử lý |
|---|---|---|
| `i++ + ++i` | Khó theo dõi giá trị cũ/mới | Tách lần đọc và lần tăng |
| `i++ + i++` | Đọc và cập nhật cùng biến hai lần | Tách biến trung gian |
| `i = i++` | Gán đè giá trị sau tăng | Chỉ dùng `i++` nếu muốn tăng |
| `show(i++, ++i)` | Đối số thứ hai đọc trạng thái đã đổi | Tính đối số từng bước |
| `array[i++] + array[i++]` | Khó kiểm soát chỉ số/giới hạn mảng | Tách chỉ số, kiểm tra miền |
| `false && (i++ > 0)` | `i++` không chạy | Đừng dựa vào side effect bị điều kiện chi phối |
| `false & (i++ > 0)` | `i++` vẫn chạy | Hiểu `&` không short-circuit |
| `byte b = 127; b++;` | Overflow/narrowing khiến b thành -128 | Chọn kiểu đủ rộng hoặc kiểm tra miền |
| `Integer n = null; n++;` | Unboxing null gây `NullPointerException` | Kiểm tra null hoặc dùng primitive |
| `final int n = 1; n++;` | Không được gán lại biến `final` | Thiết kế biến thay đổi riêng |
| `sharedCount++` trong nhiều thread | Đọc–tính–ghi không nguyên tử | Đồng bộ hoặc `AtomicInteger` |

**Overflow:** `int i = Integer.MAX_VALUE; i++;` cho `Integer.MIN_VALUE` theo quy tắc Java, không ném exception mặc định. Nếu nghiệp vụ không chấp nhận tràn, có thể dùng `Math.incrementExact(i)` để kiểm tra.

**Wrapper:** `Integer n = 1; n++;` thực hiện unboxing, cộng rồi boxing/gán lại tham chiếu; không sửa nội dung của object `Integer` bất biến.

**Đa luồng:** Java có thứ tự đánh giá rõ trong một thread, nhưng `i++` **không tự nguyên tử** khi nhiều thread cùng cập nhật. Đây là vấn đề đồng bộ độc lập với việc biểu thức dài hay ngắn.

## 13. Chương trình Java 17 chạy độc lập

Tạo file đúng tên **`IncrementDecrementClarityDemo.java`**:

~~~java
public final class IncrementDecrementClarityDemo {
    private IncrementDecrementClarityDemo() {}

    static void show(int left, int right) {
        System.out.println("show=" + left + "," + right);
    }

    public static void main(String[] args) {
        int x = 4;
        int post = x++;
        int pre = ++x;
        System.out.println("basic: post=" + post
                + ", pre=" + pre + ", x=" + x);

        int a = 1;
        int mixed = a++ + ++a;
        System.out.println("mixed: value=" + mixed + ", a=" + a);

        int b = 1;
        int twicePost = b++ + b++;
        System.out.println("twice post: value=" + twicePost + ", b=" + b);

        int c = 5;
        c = c++;
        System.out.println("self assign: c=" + c);

        int d = 5;
        d = ++d;
        System.out.println("prefix assign: d=" + d);

        int e = 3;
        int readAfterPost = e++ + e;
        System.out.println("read after post: value=" + readAfterPost
                + ", e=" + e);

        int[] items = {10, 20, 30};
        int index = 0;
        int sum = items[index++] + items[index++];
        System.out.println("array: sum=" + sum + ", index=" + index);

        int[] values = {10, 20};
        int nextIndex = 0;
        values[nextIndex++]++;
        System.out.println("array update: first=" + values[0]
                + ", index=" + nextIndex);

        int m = 1;
        show(m++, ++m);
        System.out.println("after args: m=" + m);

        int j = 0;
        boolean skipped = false && (j++ > 0);
        System.out.println("short circuit: result=" + skipped
                + ", j=" + j);

        boolean evaluated = true && (j++ == 0);
        System.out.println("evaluated: result=" + evaluated
                + ", j=" + j);

        boolean eager = false & (j++ == 1);
        System.out.println("eager &: result=" + eager + ", j=" + j);

        int k = 0;
        int zero = 0;
        try {
            int result = k++ + 10 / zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("exception: k=" + k);
        }

        int overflow = Integer.MAX_VALUE;
        overflow++;
        System.out.println("overflow: " + overflow);

        int clear = 1;
        int left = clear;
        clear++;
        clear++;
        int right = clear;
        int separated = left + right;
        System.out.println("separated: value=" + separated
                + ", final=" + clear);
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; terminal mở ở thư mục chứa file. Không dùng thư viện bên ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IncrementDecrementClarityDemo.java
java -cp . IncrementDecrementClarityDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IncrementDecrementClarityDemo.java
java -cp . IncrementDecrementClarityDemo
~~~

**Exact expected stdout:**

~~~text
basic: post=4, pre=6, x=6
mixed: value=4, a=3
twice post: value=3, b=3
self assign: c=5
prefix assign: d=6
read after post: value=7, e=4
array: sum=30, index=2
array update: first=11, index=1
show=1,3
after args: m=3
short circuit: result=false, j=0
evaluated: result=true, j=1
eager &: result=false, j=2
exception: k=1
overflow: -2147483648
separated: value=4, final=3
~~~

### Đọc kết quả quan trọng

- `post=4` và `pre=6` chứng minh hậu tố dùng giá trị cũ, tiền tố dùng giá trị mới.
- `mixed=4`, `a=3`: Java đánh giá từ trái sang phải, không có hành vi không xác định.
- `twice post=3`: hai lần tăng nối tiếp lấy các giá trị 1 và 2.
- `c = c++` ghi đè việc tăng; `d = ++d` cho 6 nhưng là cách viết dư thừa.
- `array` và `show`: chỉ số mảng/đối số lần sau nhìn thấy trạng thái đã cập nhật.
- `false && ...` bỏ qua `j++`; `false & ...` vẫn thực hiện `j++`.
- Phép chia cho 0 xảy ra sau `k++`; bắt exception không hoàn tác `k`.
- Dòng `separated` là phương án tách bước dễ đọc nhưng giữ cùng kết quả và trạng thái như `a++ + ++a`.

## 14. Bài tập có đáp án

### Bài A — hai lần hậu tố

~~~java
int i = 2;
int sum = i++ + i++;
System.out.println(sum);
System.out.println(i);
~~~

**Đáp án:**

~~~text
5
4
~~~

Các toán hạng trả lần lượt 2 và 3, còn i tăng lên 4.

### Bài B — trộn giảm hậu tố và tiền tố

~~~java
int n = 5;
int value = n-- + --n;
System.out.println(value);
System.out.println(n);
~~~

**Đáp án:**

~~~text
8
3
~~~

`n--` trả 5 rồi n thành 4; `--n` giảm n thành 3 rồi trả 3.

### Bài C — gán chồng lên tăng

~~~java
int x = 9;
x = x++;
System.out.println(x);
~~~

**Đáp án:** `9`. Phép gán ngoài ghi đè giá trị mới bằng giá trị cũ của `x++`.

### Bài D — chỉ số mảng

~~~java
int[] a = {4, 8, 12};
int i = 0;
int sum = a[i++] + a[i++];
System.out.println(sum);
System.out.println(i);
~~~

**Đáp án:**

~~~text
12
2
~~~

### Bài E — short-circuit

~~~java
int n = 0;
boolean result = true || (n++ > 0);
System.out.println(result);
System.out.println(n);
~~~

**Đáp án:**

~~~text
true
0
~~~

Vế trái `true` khiến `||` bỏ qua toàn bộ vế phải.

### Bài F — viết lại để tránh nhiều side effect

Cho:

~~~java
int i = 1;
int result = i++ + ++i;
~~~

**Một đáp án giữ đúng ngữ nghĩa:**

~~~java
int i = 1;
int left = i;
i++;
i++;
int right = i;
int result = left + right;
~~~

Sau cùng `result = 4` và `i = 3`. Nếu không thật cần tăng hai lần, hãy thiết kế lại công thức thay vì giữ một chuỗi side effect vô ích.

## 15. Checklist và kết luận

- [ ] Biết `i++` trả giá trị cũ, `++i` trả giá trị mới; `--` có quy tắc tương tự.
- [ ] Phân biệt **giá trị biểu thức** với **trạng thái sau side effect**.
- [ ] Biết Java 17 có thứ tự đánh giá xác định trong một thread.
- [ ] Tự giải thích được `i++ + ++i` và `i++ + i++` mà không gọi chúng là undefined.
- [ ] Nhận ra `i = i++` là một bẫy gán đè.
- [ ] Không lồng nhiều lần cập nhật cùng biến vào phép tính, đối số hay truy cập mảng khi không cần.
- [ ] Biết `&&`, `||` có thể bỏ qua phép tăng ở vế phải.
- [ ] Biết tác dụng phụ đã xảy ra không được rollback tự động khi exception phát sinh.
- [ ] Biết `++` có thể overflow hoặc gây NPE với wrapper nullable.
- [ ] Không coi `++` là atomic khi nhiều thread cùng ghi.
- [ ] Biết tách biến tạm, giữ thứ tự thao tác và kiểm thử cả kết quả lẫn trạng thái.
- [ ] Chạy `IncrementDecrementClarityDemo.java` bằng `javac`/`java` với JDK 17+, đối chiếu stdout chính xác.

**Kết luận:** Nhiều phép `++`/`--` trên cùng biến trong một biểu thức **không làm Java mất tính xác định**, nhưng khiến người đọc phải mô phỏng nhiều trạng thái giữa chừng, dễ dẫn đến bug và refactor sai. Hãy dành `++`/`--` cho các thao tác cập nhật rõ ràng, **tách side effect ra khỏi phép tính** khi có nhiều lần đọc/ghi cùng biến, và dùng test để xác nhận cả giá trị tính được lẫn trạng thái cuối.