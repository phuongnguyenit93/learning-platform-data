# Tác dụng phụ trong biểu thức và nguy cơ khó dự đoán — Java 17+

## 1. Mục tiêu bài học

Trong Java, một biểu thức (*expression*) có thể vừa **tính ra giá trị**, vừa thực hiện **tác dụng phụ** (*side effect*) — làm thay đổi trạng thái có thể quan sát được, chẳng hạn gán biến, tăng bộ đếm, sửa field, thay phần tử mảng, ghi log hoặc thực hiện I/O.

~~~java
int count = 5;
int old = count++; // Giá trị biểu thức là 5, nhưng count đổi thành 6

System.out.println(old);   // 5
System.out.println(count); // 6
~~~

Phần **giá trị** của `count++` là 5; phần **tác dụng phụ** là cập nhật `count` từ 5 thành 6. Đây là hai khía cạnh khác nhau của cùng một biểu thức.

**Điểm quan trọng:** Java 17 có quy tắc **thứ tự đánh giá được xác định**, không phải ngẫu nhiên. Tuy nhiên, khi một biểu thức chứa nhiều lần đọc và sửa cùng trạng thái, người đọc vẫn rất dễ dự đoán sai. Vì vậy, bài học hướng đến **hiểu đúng Java và viết code dễ kiểm chứng**, thay vì tìm cách nhồi mọi thao tác vào một dòng.

## 2. Nhận diện những biểu thức có tác dụng phụ

| Biểu thức / lời gọi | Giá trị biểu thức | Tác dụng phụ có thể xảy ra |
|---|---|---|
| `a + b` với hai `int` | Tổng `int` | Thông thường không sửa `a`, `b` |
| `x = 10` | Giá trị sau phép gán | Gán lại `x` |
| `x++` | Giá trị **trước** khi tăng | Tăng `x` |
| `++x` | Giá trị **sau** khi tăng | Tăng `x` |
| `x += 3` | Giá trị của `x` sau cập nhật | Cập nhật `x` |
| `array[index++]` | Phần tử mảng tại chỉ số cũ | Tăng `index` |
| `object.change()` | Tùy kiểu trả về method | Method có thể sửa object hoặc trạng thái khác |
| `System.out.println("hi")` | `void`, không có giá trị dùng để gán | Ghi ra output |
| `new SomeClass()` | Tham chiếu tới instance mới nếu thành công | Tạo object; constructor có thể có hành vi quan sát được |

**Không được suy luận method “chỉ đọc” hay “có sửa” dựa duy nhất vào tên.** Với lời gọi `service.getValue()`, cần xem hợp đồng và implementation của API: một getter có thể ghi log, cập nhật cache hoặc ném ngoại lệ.

Phép toán thuần như `a + b` không tự sửa toán hạng; nhưng **biểu thức toán hạng** có thể có tác dụng phụ:

~~~java
int result = next() + current(); // next() hoặc current() có thể thay đổi trạng thái
~~~

Muốn hiểu đúng phải xem cả **quá trình đánh giá toán hạng**, không chỉ toán tử `+`.

## 3. Tiền tố `++x`, hậu tố `x++`: cập nhật giống, giá trị khác

~~~java
int x = 3;

int before = x++; // before = 3, x thành 4
int after = ++x;  // x thành 5, after = 5

System.out.println(before); // 3
System.out.println(after);  // 5
System.out.println(x);      // 5
~~~

| Cú pháp | Giá trị dùng trong biểu thức | Trạng thái sau |
|---|---|---|
| `x++` | Giá trị cũ | `x` tăng 1 |
| `++x` | Giá trị mới | `x` tăng 1 |
| `x--` | Giá trị cũ | `x` giảm 1 |
| `--x` | Giá trị mới | `x` giảm 1 |

Trong vòng lặp đơn giản, `i++` thường dễ hiểu:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

Nhưng trong phép tính lớn, phải ghi nhớ **giá trị trước/sau khi cập nhật** và **thời điểm biểu thức khác đọc biến**. Tách câu lệnh giúp tránh nhầm lẫn.

## 4. Java không “không xác định”, nhưng biểu thức phức tạp rất khó đọc

Ví dụ dưới đây **hợp lệ và có kết quả xác định theo Java**:

~~~java
int i = 1;
int sum = i++ + ++i;

System.out.println(sum); // 4
System.out.println(i);   // 3
~~~

Giải thích chính xác từ trái sang phải:

1. `i++` cho **giá trị cũ 1**, rồi cập nhật `i = 2`.
2. `++i` cập nhật `i = 3`, rồi cho **giá trị mới 3**.
3. `1 + 3` bằng **4**, và giá trị cuối của `i` là **3**.

Không gọi trường hợp này là “undefined behavior” theo nghĩa của một số ngôn ngữ khác: **Java quy định thứ tự đánh giá**. Vấn đề nằm ở khả năng đọc code, bảo trì và rủi ro sửa nhầm khi refactor.

Viết tường minh hơn:

~~~java
int i = 1;
int left = i;
i++;
i++;
int right = i;
int sum = left + right;
~~~

Đoạn tách bước thể hiện rõ mục đích và cho cùng kết quả trong trường hợp này. Nếu logic nghiệp vụ không cần hai lần cập nhật, cách tốt hơn là **đơn giản hóa thuật toán**, không chỉ thêm biến.

### Bẫy `i = i++`

~~~java
int i = 5;
i = i++;
System.out.println(i); // 5
~~~

Vì sao vẫn 5? Vế phải `i++` cho giá trị cũ **5** và tăng `i` lên 6; cuối cùng **phép gán bên ngoài** gán lại giá trị cũ 5 cho `i`.

Hãy viết `i++;` nếu chỉ muốn tăng, hoặc `i = desiredValue;` nếu chỉ muốn gán. **Đừng kết hợp hai cơ chế gán lên cùng biến khi không cần thiết.**

## 5. Side effect tuân theo thứ tự đánh giá, không theo mức ưu tiên

~~~java
static int trace(String label, int value) {
    System.out.println("evaluate " + label);
    return value;
}
// Trong một method:
int result = trace("A", 2) + trace("B", 3) * trace("C", 4);
~~~

Ba dòng `evaluate A`, `evaluate B`, `evaluate C` xuất hiện theo thứ tự ấy; `result == 14`. Phép nhân được **nhóm** trước phép cộng khi tính giá trị, nhưng không khiến lời gọi B/C thực thi trước A.

Đặc biệt khi các method thay đổi trạng thái, nên đưa kết quả vào biến riêng theo đúng thứ tự mong muốn, sau đó thực hiện phép tính. Cách này giảm rủi ro vô tình đổi side effect khi sửa code.

## 6. Đối số method được đánh giá trước khi method bắt đầu

Khi gọi:

~~~java
show(trace("first", 1), trace("second", 2));
~~~

Java đánh giá đối số **từ trái sang phải** trước khi thực thi phần thân `show`. Trong ví dụ này, `trace("first", 1)` chạy trước `trace("second", 2)`, sau đó mới tới `show`.

Điều này có thể tạo bug nếu hai đối số cùng sửa một object:

~~~java
send(counter.incrementAndGet(), counter.get());
~~~

Nếu `incrementAndGet()` tăng trạng thái, đối số thứ hai có thể đọc **giá trị sau khi tăng**, không phải trạng thái ban đầu. Không nên giả định hai đối số được tính “cùng một lúc”.

Cách rõ hơn:

~~~java
int newValue = counter.incrementAndGet();
int snapshotAfter = counter.get();
send(newValue, snapshotAfter);
~~~

**Lưu ý:** compiler chọn overload theo kiểu tĩnh của biểu thức đối số, còn tác dụng phụ khi **đánh giá** đối số xảy ra lúc chạy. Hai điều này tách biệt.

## 7. Short-circuit với `&&` và `||`

Toán tử **`&&`** bỏ qua vế phải nếu vế trái đã `false`; **`||`** bỏ qua vế phải nếu vế trái đã `true`.

~~~java
int divisor = 0;
boolean safe = (divisor != 0) && (10 / divisor > 2);
System.out.println(safe); // false, không chia cho 0
~~~

Nếu một method có tác dụng phụ nằm trong nhánh bị bỏ qua, tác dụng phụ **không xảy ra**:

~~~java
boolean result = false && updateCounter(); // updateCounter() không được gọi
~~~

Mô hình:

~~~mermaid
flowchart TD
    A["Đánh giá vế trái của &&"] --> B{"Có true không?"}
    B -- "Không" --> C["Kết quả false, bỏ qua vế phải"]
    B -- "Có" --> D["Đánh giá vế phải"]
    E["Đánh giá vế trái của ||"] --> F{"Có true không?"}
    F -- "Có" --> G["Kết quả true, bỏ qua vế phải"]
    F -- "Không" --> H["Đánh giá vế phải"]
~~~

**Phân biệt `&&` với `&`, `||` với `|` khi toán hạng là boolean:**

| Toán tử | Có bỏ qua vế phải? | Lưu ý |
|---|---|---|
| `&&` | Có, khi vế trái false | Thường dùng để bảo vệ thao tác cần điều kiện |
| `||` | Có, khi vế trái true | Thường dùng để đặt lựa chọn thay thế |
| `&` | Không | Đánh giá cả hai vế |
| `|` | Không | Đánh giá cả hai vế |

Dùng `&` thay `&&` có thể **vô tình gọi thêm method**, sửa dữ liệu hoặc gây ngoại lệ. Dùng toán tử đúng và kiểm thử cả hai trường hợp true/false.

## 8. Toán tử điều kiện `?:` chỉ đánh giá nhánh được chọn

~~~java
boolean useCache = true;
int answer = useCache ? readCache() : calculateFresh();
~~~

Compiler kiểm tra kiểu của hai nhánh theo quy tắc conditional expression, nhưng khi chạy Java chỉ đánh giá **nhánh được chọn**. Nếu `useCache` true, `calculateFresh()` không được gọi.

Vì vậy, nếu một nhánh gửi yêu cầu mạng, ghi log hoặc thay đổi bộ đếm, **số lần gọi có thể khác** giữa các lượt chạy. Điều này hoàn toàn theo ngữ nghĩa Java, không phải tính ngẫu nhiên.

Nếu hai nhánh mang nhiều logic tác động trạng thái, dùng `if/else` thường dễ quan sát:

~~~java
int answer;
if (useCache) {
    answer = readCache();
} else {
    answer = calculateFresh();
}
~~~

**Không đặt tác dụng phụ vào cả hai nhánh rồi mong cả hai đều được thực hiện.**

## 9. Gán biến, sửa object và alias

Side effect không chỉ là sửa một biến primitive:

~~~java
final class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }

    int incrementAndGet() {
        return ++value;
    }
}

// Trong method:
Counter original = new Counter(10);
Counter alias = original;

int current = alias.incrementAndGet();
System.out.println(current);        // 11
System.out.println(original.value); // 11
~~~

`original` và `alias` cùng tham chiếu đến **một Counter**. Một method trên `alias` sửa field trên object, nên bên dùng `original` cũng thấy giá trị mới.

Một lời gọi method có thể trông giống biểu thức lấy giá trị nhưng lại sửa trạng thái được chia sẻ. Với code có nhiều object, hãy kiểm tra:

- Method chỉ đọc hay thay đổi field/collection?
- Có nhiều biến cùng tham chiếu tới cùng object không?
- Có được phép gọi method này nhiều lần không?
- Có cần đồng bộ hoặc bảo vệ khi nhiều thread cùng truy cập không?

**Phép tính có kiểu hợp lệ** không đồng nghĩa không có thay đổi trạng thái.

## 10. Chỉ số mảng có `i++`: đọc ở đâu, cập nhật khi nào?

~~~java
int[] values = {10, 20, 30};
int i = 0;

int sum = values[i++] + values[i];

System.out.println(sum); // 30
System.out.println(i);   // 1
~~~

Java đánh giá `values[i++]` trước:

1. `i++` cung cấp chỉ số cũ **0**, rồi đổi `i` thành **1**.
2. Đọc `values[0]` bằng **10**.
3. Đánh giá `values[i]` bên phải với `i = 1`: lấy **20**.
4. Tổng là **30**.

Cách dễ đọc hơn:

~~~java
int first = values[i];
i++;
int second = values[i];
int sum = first + second;
~~~

Trường hợp dùng `values[i++] = nextValue` trong thuật toán duyệt mảng có thể phù hợp khi đơn giản, nhưng **tránh kết hợp nhiều lần cập nhật cùng chỉ số trong một biểu thức dài**. Nếu `i` vượt giới hạn, chương trình có thể ném `ArrayIndexOutOfBoundsException`; Java không tự đoán ý định dịch chỉ số.

## 11. Nối chuỗi và log có thể che tác dụng phụ

~~~java
int n = 1;
System.out.println("n=" + n++ + ", now=" + n);
~~~

Output:

~~~text
n=1, now=2
~~~

`n++` đóng góp giá trị cũ 1 vào chuỗi, sau đó `n` đã bằng 2 khi biểu thức tiếp theo được đánh giá.

**Không nên dùng biểu thức có tác dụng phụ chỉ để tạo thông báo log.** Cách rõ hơn:

~~~java
int old = n;
n++;
System.out.println("old=" + old + ", now=" + n);
~~~

Một biểu thức được truyền vào `logger.debug(...)` hoặc `System.out.println(...)` có thể được **đánh giá trước lời gọi**, kể cả khi code bên trong method quyết định không ghi ra đích. Muốn tối ưu chi phí đánh giá log, cần xem API logging cụ thể hỗ trợ lazy evaluation hay không.

## 12. Exception có thể dừng quá trình đánh giá

Một biểu thức có kiểu compile time hoàn toàn hợp lệ vẫn có thể **không hoàn tất bình thường** tại runtime:

~~~java
int zero = 0;
int value = (10 / zero) + expensiveOperation();
~~~

Nếu `10 / zero` ném `ArithmeticException`, Java không tiếp tục đánh giá `expensiveOperation()`. Do đó tác dụng phụ bên trong method ở vế phải **không xảy ra**.

Tương tự với:

~~~java
String text = null;
// int length = text.length() + mutate(); // text.length() ném NPE;
// mutate() không được gọi.
~~~

Đây là một lý do để tránh gói **tính toán có thể lỗi và cập nhật trạng thái** vào cùng một biểu thức dài: đường thực thi thất bại có thể để lại trạng thái được cập nhật một phần, khó rollback.

**Không hiểu nhầm:** `try/catch` xử lý exception không đồng nghĩa các side effect đã xảy ra trước exception tự động được hoàn tác. Nếu cần tính nhất quán qua nhiều thao tác, thiết kế transaction/rollback phù hợp.

## 13. Cách refactor biểu thức nhiều tác dụng phụ

**Trước — khó đọc:**

~~~java
int result = counter.incrementAndGet()
        + values[index++]
        + service.nextValue();
~~~

Đoạn này trộn ba thay đổi/quan sát trạng thái:

1. Tăng `counter`.
2. Tăng `index` khi chọn phần tử.
3. Gọi `service.nextValue()`, có thể có tác dụng phụ theo hợp đồng API.

**Sau — tách ý định, giữ thứ tự:**

~~~java
int counterValue = counter.incrementAndGet();
int selectedValue = values[index];
index++;
int serviceValue = service.nextValue();
int result = counterValue + selectedValue + serviceValue;
~~~

Lợi ích:

- Debug từng bước dễ hơn.
- Log/test có thể kiểm tra trạng thái tại ranh giới rõ ràng.
- Dễ đặt validation trước thao tác nguy hiểm.
- Code review nhìn được thứ tự hoạt động, thay vì phải tính nhẩm side effect.

**Cẩn thận:** khi refactor, đừng tự ý đổi thứ tự gọi method, đổi loại toán tử hoặc bỏ mất guard; hãy giữ đúng ngữ nghĩa cần thiết, nhất là khi method có side effect.

## 14. Java có thứ tự xác định, nhưng concurrency vẫn có vấn đề riêng

Các ví dụ trên giả sử chạy trong **một thread**. Quy tắc đánh giá từ trái sang phải không thay thế cơ chế đồng bộ giữa các thread.

~~~java
static int count = 0;

// Nếu nhiều thread cùng làm:
count++;
~~~

`count++` gồm đọc, tính và ghi; **không phải phép tăng nguyên tử an toàn cho mọi tình huống đa luồng**. Khi nhiều thread cùng ghi không đồng bộ, có thể xảy ra race condition và cập nhật bị mất.

Nếu cần bộ đếm được chia sẻ, có thể dùng `java.util.concurrent.atomic.AtomicInteger` theo yêu cầu:

~~~java
java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger(0);
int next = count.incrementAndGet();
~~~

**Phân biệt:** Java xác định thứ tự đánh giá trong một thread; nhưng tính đúng của trạng thái chia sẻ trong đa luồng cần tuân thủ Java Memory Model và đồng bộ phù hợp. Không dùng dấu ngoặc hay đổi `i++` thành `++i` để sửa race condition.

## 15. Chương trình Java 17 độc lập, có expected output

Lưu file đúng tên **`ExpressionSideEffectsDemo.java`**:

~~~java
public final class ExpressionSideEffectsDemo {
    private ExpressionSideEffectsDemo() {}

    static int trace(String label, int value) {
        System.out.println("evaluate " + label);
        return value;
    }

    static void show(int a, int b) {
        System.out.println("arguments=" + a + "," + b);
    }

    static boolean check(boolean result, int[] calls) {
        calls[0]++;
        return result;
    }

    static int select(int value, int[] calls) {
        calls[0]++;
        return value;
    }

    static final class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }

        int addAndGet(int amount) {
            value += amount;
            return value;
        }
    }

    public static void main(String[] args) {
        int x = 3;
        int postfix = x++;
        int prefix = ++x;
        System.out.println("postfix=" + postfix
                + ", prefix=" + prefix + ", x=" + x);

        int i = 1;
        int mixed = i++ + ++i;
        System.out.println("mixed=" + mixed + ", i=" + i);

        int confusing = 5;
        confusing = confusing++;
        System.out.println("self-assignment=" + confusing);

        int arithmetic = trace("A", 2)
                + trace("B", 3) * trace("C", 4);
        System.out.println("arithmetic=" + arithmetic);

        show(trace("first", 1), trace("second", 2));

        int[] calls = {0};
        boolean guardedAnd = check(false, calls)
                && check(true, calls);
        System.out.println("&&=" + guardedAnd + ", calls=" + calls[0]);

        boolean guardedOr = check(true, calls)
                || check(false, calls);
        System.out.println("||=" + guardedOr + ", calls=" + calls[0]);

        boolean eagerAnd = check(false, calls)
                & check(true, calls);
        System.out.println("&=" + eagerAnd + ", calls=" + calls[0]);

        int[] branchCalls = {0};
        int chosen = true
                ? select(5, branchCalls)
                : select(9, branchCalls);
        System.out.println("ternary=" + chosen
                + ", calls=" + branchCalls[0]);

        Counter counter = new Counter(10);
        Counter alias = counter;
        int changed = alias.addAndGet(5);
        System.out.println("counter=" + changed
                + ", original=" + counter.value);

        int[] values = {10, 20, 30};
        int index = 0;
        int arraySum = values[index++] + values[index];
        System.out.println("array sum=" + arraySum + ", index=" + index);

        int n = 1;
        System.out.println("string side effect=" + n++
                + ", now=" + n);

        int zero = 0;
        try {
            int unused = (10 / zero) + trace("unreached", 99);
            System.out.println(unused);
        } catch (ArithmeticException ex) {
            System.out.println("division error, right skipped");
        }
    }
}
~~~

Cài **JDK 17+**, mở terminal trong thư mục chứa file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ExpressionSideEffectsDemo.java
java -cp . ExpressionSideEffectsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ExpressionSideEffectsDemo.java
java -cp . ExpressionSideEffectsDemo
~~~

**Exact expected output:**

~~~text
postfix=3, prefix=5, x=5
mixed=4, i=3
self-assignment=5
evaluate A
evaluate B
evaluate C
arithmetic=14
evaluate first
evaluate second
arguments=1,2
&&=false, calls=1
||=true, calls=2
&=false, calls=4
ternary=5, calls=1
counter=15, original=15
array sum=30, index=1
string side effect=1, now=2
division error, right skipped
~~~

### Đối chiếu các điểm quan trọng

1. `x++` trả giá trị cũ, `++x` trả giá trị mới; cả hai cùng sửa `x`.
2. `i++ + ++i` có kết quả xác định, nhưng khó đọc hơn việc tách bước.
3. `i = i++` có thể tự ghi đè kết quả tăng và giữ giá trị cũ.
4. `trace A/B/C` chạy từ trái qua phải dù toán tử `*` có mức ưu tiên cao hơn `+`.
5. Các đối số `show` được đánh giá lần lượt trước thân method.
6. `&&` và `||` bỏ qua vế phải khi đủ kết luận; `&` không bỏ qua.
7. `?:` chỉ gọi nhánh được chọn.
8. Hai biến alias cùng thấy side effect trên object Counter.
9. `index++` sửa chỉ số trước khi vế phải đọc lại mảng.
10. Vế phải sau phép chia cho 0 không chạy; vì vậy **không có dòng `evaluate unreached`** trong output.

## 16. Lỗi thường gặp và hướng xử lý

| Code/ngộ nhận | Vấn đề | Cách sửa hoặc nguyên tắc |
|---|---|---|
| `int sum = i++ + ++i;` | Có kết quả xác định nhưng khó audit | Tách cập nhật và phép cộng |
| `i = i++;` để tăng `i` | Phép gán có thể ghi đè giá trị sau tăng | Viết `i++;` |
| Nghĩ `*` ưu tiên hơn nên toán hạng bên phải của phép cộng luôn gọi trước | Nhầm precedence với evaluation order | Phân biệt cách nhóm và thứ tự đánh giá |
| Gọi method có side effect trong nhiều đối số | Trạng thái đối số sau phụ thuộc đối số trước | Tách biến tạm, gọi theo thứ tự |
| Dùng `&` thay `&&` để guard null | `&` đánh giá cả hai vế | Dùng `&&` |
| Mong hai nhánh `?:` đều có tác dụng | Chỉ một nhánh được chọn | Dùng câu lệnh riêng nếu cần hai thao tác |
| `list.get(index++)` lồng trong phép tính dài | Dễ dùng sai chỉ số, khó debug | Lưu chỉ số/phần tử tạm |
| Cho rằng getter luôn không sửa gì | Method có thể thay đổi cache/log/field | Xem contract và implementation |
| Ghép log bằng `value++` | Ghi log làm đổi trạng thái | Tách cập nhật khỏi formatting |
| Tưởng ngoại lệ rollback side effects trước đó | Java không tự rollback trạng thái | Transaction/rollback theo thiết kế |
| Dùng `count++` làm bộ đếm nhiều thread | Không bảo đảm atomicity | Synchronization hoặc `AtomicInteger` |
| Kết luận Java có thứ tự không xác định | Java có quy tắc đánh giá rõ | Hiểu thứ tự, nhưng ưu tiên code đơn giản |

## 17. Bài tập có đáp án

### Bài A — hậu tố và giá trị

~~~java
int x = 2;
int y = x++ + x++;
System.out.println(y);
System.out.println(x);
~~~

**Đáp án:**

~~~text
5
4
~~~

Lần hậu tố thứ nhất đóng góp 2 rồi `x = 3`; lần thứ hai đóng góp 3 rồi `x = 4`. Tổng bằng 5. Dù hợp lệ, cách viết này không nên là lựa chọn mặc định trong code nghiệp vụ.

### Bài B — thứ tự đánh giá đối số

~~~java
static int step(int value) {
    System.out.println("step " + value);
    return value;
}

static void show(int a, int b) {
    System.out.println(a + b);
}

// Trong main:
show(step(1), step(2));
~~~

**Đáp án:**

~~~text
step 1
step 2
3
~~~

### Bài C — short-circuit

~~~java
int[] calls = {0};
boolean result = false && check(true, calls);
System.out.println(result);
System.out.println(calls[0]);
~~~

**Đáp án:**

~~~text
false
0
~~~

`check` là hàm trong ví dụ chạy ở trên; vế phải không được gọi nên bộ đếm giữ nguyên 0.

### Bài D — mảng và index

~~~java
int[] a = {4, 9, 16};
int i = 0;
int sum = a[i++] + a[i];
System.out.println(sum);
System.out.println(i);
~~~

**Đáp án:**

~~~text
13
1
~~~

### Bài E — refactor code khó đọc

Cho biểu thức:

~~~java
int result = service.next() + counter.incrementAndGet();
~~~

Hãy viết lại để thứ tự thao tác rõ ràng.

**Một đáp án:**

~~~java
int serviceValue = service.next();
int counterValue = counter.incrementAndGet();
int result = serviceValue + counterValue;
~~~

Đây là phiên bản tách bước nhưng **giữ thứ tự gọi bên trái trước bên phải**.

### Bài F — tác dụng phụ và exception

~~~java
int denominator = 0;
int result = (10 / denominator) + trace("after", 5);
~~~

**Đáp án:** có `ArithmeticException` khi chia nguyên cho 0; `trace("after", 5)` không chạy nên không có output `evaluate after`.

## 18. Checklist và kết luận

- [ ] Phân biệt **giá trị biểu thức** và **tác dụng phụ**.
- [ ] Nhớ `i++` trả giá trị cũ, `++i` trả giá trị mới.
- [ ] Hiểu biểu thức như `i++ + ++i` có kết quả xác định nhưng khó bảo trì.
- [ ] Biết vì sao `i = i++` có thể không tăng kết quả cuối.
- [ ] Phân biệt **operator precedence** với **evaluation order**.
- [ ] Biết Java đánh giá đối số method theo thứ tự trái sang phải.
- [ ] Biết `&&`/`||` short-circuit, còn `&`/`|` boolean không short-circuit.
- [ ] Biết `?:` chỉ đánh giá nhánh được chọn.
- [ ] Nhận diện side effect khi sửa object qua alias hoặc index mảng.
- [ ] Hiểu ngoại lệ có thể dừng đánh giá và không tự rollback trạng thái đã đổi.
- [ ] Không nhúng phép cập nhật vào biểu thức log hoặc công thức dài nếu không cần thiết.
- [ ] Tách phép gọi có side effect thành các câu lệnh có tên rõ ràng.
- [ ] Phân biệt thứ tự biểu thức một thread với vấn đề race condition đa luồng.
- [ ] Chạy `ExpressionSideEffectsDemo.java` bằng `javac`/`java` Java 17+ và đối chiếu exact expected output.

**Kết luận:** Biểu thức Java có thể vừa tạo giá trị vừa sửa trạng thái. Java 17 định nghĩa thứ tự đánh giá, nhưng nhiều side effect trong cùng một biểu thức vẫn là nguồn lỗi đọc hiểu, thay đổi ngoài ý muốn và khó kiểm thử. Hãy **giữ tính toán đơn giản, tách cập nhật trạng thái thành bước rõ ràng, sử dụng short-circuit đúng mục đích và kiểm thử đường thành công lẫn đường exception**.