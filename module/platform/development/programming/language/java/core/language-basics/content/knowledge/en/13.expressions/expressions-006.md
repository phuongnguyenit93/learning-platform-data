# Đánh giá toán hạng và đối số từ trái sang phải — Java 17+

Trong Java, **thứ tự đánh giá** (*evaluation order*) quyết định thời điểm các biểu thức con được thực thi. Đối với toán hạng của phép toán thông thường và đối số của lời gọi phương thức, Java quy định **đánh giá từ trái sang phải**. Quy tắc này đặc biệt quan trọng khi biểu thức con gọi phương thức, thay đổi biến, đọc mảng hoặc ném ngoại lệ.

~~~java
int result = first() + second() * third();
~~~

Mặc dù `*` có **độ ưu tiên** cao hơn `+`, các lời gọi được đánh giá theo thứ tự `first()`, `second()`, `third()`. Phép nhân vẫn thuộc biểu thức con bên phải của phép cộng. **Độ ưu tiên quyết định cách nhóm; thứ tự đánh giá quyết định lúc thực thi.**

> Phạm vi: các quy tắc đánh giá của biểu thức Java 17. Không suy diễn rằng **mọi toán hạng/nhánh** đều bắt buộc chạy; `&&`, `||`, `?:` và tình huống ném ngoại lệ có thể làm bỏ qua phần còn lại.

## 1. Phân biệt ba khái niệm

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Precedence** (độ ưu tiên) | Toán tử nào nhóm chặt hơn? | `a + b * c` nhóm thành `a + (b * c)` |
| **Associativity** (tính kết hợp) | Các toán tử cùng mức được nhóm thế nào? | `a - b - c` nhóm thành `(a - b) - c` |
| **Evaluation order** (thứ tự đánh giá) | Biểu thức con nào được đánh giá trước? | Trong `f() + g() * h()` gọi `f()` rồi `g()` rồi `h()` |

Với biểu thức có lời gọi phương thức:

~~~text
                       +
                      / \
                   f()   *
                        / \
                      g() h()

Cây nhóm:  f() + (g() * h())
Thứ tự đánh giá lời gọi: f() -> g() -> h()
~~~

Cây biểu thức mô tả **sự phụ thuộc về kết quả**, không phải lịch gọi các hàm theo thứ tự toán tử có độ ưu tiên cao nhất.

## 2. Quy tắc cốt lõi và ngoại lệ

- Với các **toán tử hai ngôi thông thường**, Java đánh giá toán hạng trái trước toán hạng phải. Giá trị của toán hạng trái được giữ để sử dụng sau khi đánh giá toán hạng phải, ngay cả khi vế phải làm thay đổi biến liên quan.
- Với **lời gọi phương thức**, biểu thức chọn đối tượng nhận lời gọi (nếu có) được đánh giá theo quy tắc của lời gọi, rồi các **đối số** được đánh giá từ trái sang phải; sau đó phương thức mới được gọi.
- Nếu một toán hạng hoặc đối số **hoàn thành bất thường**, ví dụ ném ngoại lệ, các phần cần đánh giá **sau đó** không tiếp tục chạy.
- Với `&&` và `||`, toán hạng phải chỉ được đánh giá khi cần để quyết định kết quả; với `?:`, chỉ một trong hai nhánh kết quả được chọn.
- Với `&` và `|` trên `boolean`, **cả hai toán hạng** được đánh giá khi không có ngoại lệ; chúng không có hành vi ngắn mạch giống `&&` và `||`.

**Đừng viết mã dựa vào việc tác dụng phụ ẩn trong biểu thức dài.** Dù thứ tự được Java quy định, tách bước thường giúp người đọc dễ hiểu hơn.

## 3. Demo Java 17+ hoàn chỉnh

Tạo tệp UTF-8 tên **`LeftToRightDemo.java`**:

~~~java
public class LeftToRightDemo {
    static int mark(String label, int value) {
        System.out.println("visit=" + label);
        return value;
    }

    static boolean check(String label, boolean value) {
        System.out.println("visit=" + label);
        return value;
    }

    static int add(int left, int right) {
        return left + right;
    }

    static int digits(int hundreds, int tens, int units) {
        return hundreds * 100 + tens * 10 + units;
    }

    static class Box {
        private final int base;

        Box(int base) {
            this.base = base;
        }

        int addToBase(int first, int second) {
            return base + first + second;
        }
    }

    static Box makeReceiver() {
        System.out.println("visit=receiver");
        return new Box(10);
    }

    static int fail() {
        System.out.println("visit=failure");
        throw new IllegalStateException("stop");
    }

    public static void main(String[] args) {
        System.out.println("== binary ==");
        int binary = mark("left", 2)
                + mark("middle", 3) * mark("right", 4);
        System.out.println("binary=" + binary);

        System.out.println("== arguments ==");
        int arguments = digits(
                mark("arg-1", 1),
                mark("arg-2", 2),
                mark("arg-3", 3));
        System.out.println("arguments=" + arguments);

        System.out.println("== nested ==");
        int nested = add(
                mark("outer", 4),
                add(mark("inner-left", 5), mark("inner-right", 6)));
        System.out.println("nested=" + nested);

        System.out.println("== receiver ==");
        int receiverTotal = makeReceiver().addToBase(
                mark("method-1", 2),
                mark("method-2", 3));
        System.out.println("receiverTotal=" + receiverTotal);

        System.out.println("== snapshot ==");
        int current = 10;
        int snapshot = current + (current = 20);
        System.out.println("snapshot=" + snapshot + ",current=" + current);

        int counter = 1;
        int captured = digits(counter++, counter++, counter++);
        System.out.println("captured=" + captured + ",counter=" + counter);

        System.out.println("== short-circuit ==");
        boolean andResult = false && check("and-skipped", true);
        System.out.println("and=" + andResult);

        boolean orResult = true || check("or-skipped", false);
        System.out.println("or=" + orResult);

        boolean eagerAnd = false & check("and-eager", true);
        System.out.println("eagerAnd=" + eagerAnd);

        int selected = true
                ? mark("selected", 7)
                : mark("not-selected", 8);
        System.out.println("conditional=" + selected);

        System.out.println("== arrays ==");
        int[] values = {10, 20, 30};
        int index = 0;
        int arraySum = values[index++] + values[index++];
        System.out.println("arraySum=" + arraySum + ",index=" + index);

        System.out.println("== strings ==");
        String concat = "" + mark("concat-1", 1) + mark("concat-2", 2);
        System.out.println("concat=" + concat);

        System.out.println("== exception ==");
        try {
            int unreachable = mark("before-failure", 1)
                    + fail() + mark("after-failure", 2);
            System.out.println("unreachable=" + unreachable);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa tệp. Dùng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 LeftToRightDemo.java
java LeftToRightDemo
~~~

**Exact expected output** của lệnh `java LeftToRightDemo`:

~~~text
== binary ==
visit=left
visit=middle
visit=right
binary=14
== arguments ==
visit=arg-1
visit=arg-2
visit=arg-3
arguments=123
== nested ==
visit=outer
visit=inner-left
visit=inner-right
nested=15
== receiver ==
visit=receiver
visit=method-1
visit=method-2
receiverTotal=15
== snapshot ==
snapshot=30,current=20
captured=123,counter=4
== short-circuit ==
and=false
or=true
visit=and-eager
eagerAnd=false
visit=selected
conditional=7
== arrays ==
arraySum=30,index=2
== strings ==
visit=concat-1
visit=concat-2
concat=12
== exception ==
visit=before-failure
visit=failure
caught=stop
~~~

Kết quả `java -version` và `javac -version` tùy JDK và không nằm trong khối stdout cố định trên.

## 4. Đọc demo theo nhóm

### 4.1. Toán hạng: thứ tự gọi khác thứ tự nhóm

~~~java
int binary = mark("left", 2)
        + mark("middle", 3) * mark("right", 4);
~~~

- Java đánh giá `mark("left", 2)` trước, ghi dấu `visit=left` và thu được giá trị 2.
- Tiếp theo, để đánh giá toán hạng phải của `+`, Java đánh giá `mark("middle", 3)` rồi `mark("right", 4)`.
- Toán tử nhân xử lý `3 * 4 = 12`; sau đó cộng `2 + 12 = 14`.

**Không suy luận rằng `mark("middle", ...)` phải chạy trước `mark("left", ...)` chỉ vì `*` ưu tiên cao hơn `+`.**

### 4.2. Đối số của phương thức: trái sang phải

~~~java
int value = digits(
        mark("arg-1", 1),
        mark("arg-2", 2),
        mark("arg-3", 3));
~~~

Các biểu thức đối số được đánh giá lần lượt **1 → 2 → 3**. Khi cả ba biểu thức hoàn thành bình thường, Java gọi `digits(1, 2, 3)` và trả **123**.

Đối với **lời gọi lồng nhau**:

~~~java
add(mark("outer", 4),
    add(mark("inner-left", 5), mark("inner-right", 6)));
~~~

Java đánh giá đối số thứ nhất của lời gọi ngoài trước (in `visit=outer`), rồi mới đi vào biểu thức đối số thứ hai: các đối số bên trong được đánh giá từ trái sang phải (in `inner-left`, `inner-right`). Sau đó `add(5, 6)` trả 11 và `add(4, 11)` trả **15**.

### 4.3. Biểu thức chọn đối tượng trước các đối số

~~~java
makeReceiver().addToBase(
        mark("method-1", 2),
        mark("method-2", 3));
~~~

`makeReceiver()` được đánh giá để xác định đối tượng nhận lời gọi, nên dấu `visit=receiver` xuất hiện **trước** `visit=method-1` và `visit=method-2`. Sau đó `addToBase(2, 3)` dùng `base=10` để trả **15**.

Đây là quy tắc trong ngữ cảnh gọi phương thức instance có biểu thức đối tượng nhận lời gọi. Nếu bản thân biểu thức tạo/tra cứu đối tượng thất bại, lời gọi có thể không diễn ra.

### 4.4. Giá trị đã đánh giá không bị “đọc lại” sau tác dụng phụ

~~~java
int current = 10;
int result = current + (current = 20);
~~~

Toán hạng trái `current` được đọc và giữ giá trị **10**. Sau đó, toán hạng phải gán `current = 20` và có giá trị 20. Kết quả `result = 10 + 20 = 30`, trong khi biến `current` sau biểu thức bằng **20**.

Tương tự:

~~~java
int counter = 1;
int value = digits(counter++, counter++, counter++);
~~~

Mỗi đối số đánh giá từ trái sang phải. Hậu tố `++` lấy **giá trị cũ** trước khi tăng, nên các đối số lần lượt là **1, 2, 3**, biến sau đó bằng **4**, và `digits(1, 2, 3)` trả 123.

Đây là ví dụ để **hiểu quy tắc**, không phải lời khuyên nên lồng nhiều thao tác tăng biến vào một lời gọi: mã như vậy khó rà soát và sửa lỗi.

### 4.5. Ngắn mạch và chọn nhánh

~~~java
boolean a = false && check("unused", true);
boolean b = true || check("also-unused", false);
~~~

Với `&&`, nếu toán hạng trái đã false, toán hạng phải **không được đánh giá**. Với `||`, nếu toán hạng trái đã true, toán hạng phải **không được đánh giá**.

Ngược lại:

~~~java
boolean c = false & check("executed", true);
~~~

Toán tử boolean `&` vẫn đánh giá phía phải, vì nó **không ngắn mạch**. Giá trị `c` là false nhưng phương thức vẫn được gọi.

Với `?:`:

~~~java
int value = true ? mark("selected", 7) : mark("ignored", 8);
~~~

Java đánh giá điều kiện trước, rồi **chỉ nhánh được chọn**. Vì điều kiện true, chỉ `visit=selected` xuất hiện.

Các ngoại lệ này không phủ nhận quy tắc trái-sang-phải; chúng xác định **biểu thức nào thật sự cần được đánh giá**.

### 4.6. Truy cập mảng và chuỗi

~~~java
int index = 0;
int[] values = {10, 20, 30};
int sum = values[index++] + values[index++];
~~~

Ở phép cộng, toán hạng trái được đánh giá trọn vẹn trước: lấy `values[0] = 10` và tăng `index` lên 1. Toán hạng phải sau đó lấy `values[1] = 20` và tăng `index` lên 2. Tổng bằng **30**.

Với nối chuỗi:

~~~java
String text = "" + mark("first", 1) + mark("second", 2);
~~~

Hai lời gọi vẫn được đánh giá theo thứ tự trái-sang-phải; các phép `+` sau khi bắt đầu từ `String` thực hiện nối chuỗi, nên kết quả là `"12"`, không phải số 3.

### 4.7. Ngoại lệ chặn phần đánh giá phía sau

~~~java
int result = mark("before", 1) + fail() + mark("after", 2);
~~~

Nếu `fail()` ném ngoại lệ, `mark("after", 2)` **không chạy**, và không có giá trị kết quả bình thường cho phép cộng. Khối `catch` có thể xử lý ngoại lệ, nhưng không làm những biểu thức còn lại tự động chạy tiếp.

## 5. Cách viết mã dễ kiểm tra hơn khi có tác dụng phụ

Dù Java đã xác định thứ tự đánh giá, vẫn nên **tách lệnh** trong mã nghiệp vụ để người đọc không phải mô phỏng các bước tăng biến hoặc lời gọi có tác dụng phụ:

~~~java
int first = nextNumber();
int second = nextNumber();
int third = nextNumber();
int result = digits(first, second, third);
~~~

Ví dụ này thể hiện cách tổ chức; để chạy độc lập, cần có định nghĩa phù hợp cho `nextNumber()` và `digits(...)`. Trong demo mục 3, mọi phương thức đều đã được khai báo đầy đủ.

Nên đặc biệt tách bước khi có thao tác I/O, đổi trạng thái dùng chung, tăng bộ đếm, xử lý lỗi hoặc khi thứ tự thao tác là một phần hợp đồng nghiệp vụ.

### Không nhầm với xử lý song song

Quy tắc ngôn ngữ quy định thứ tự đánh giá trong **một luồng thực thi biểu thức**. Nó **không** đảm bảo thứ tự xuất hiện của tác dụng phụ từ các luồng khác nếu chương trình dùng concurrency. Muốn phối hợp luồng cần quy tắc đồng bộ và memory model phù hợp; việc viết phép cộng không thay thế synchronization.

## 6. Những hiểu nhầm phổ biến

| Ngộ nhận | Điều đúng trong Java |
| --- | --- |
| “Toán tử `*` ưu tiên cao nên hàm trong phép nhân luôn được gọi trước.” | Precedence quy định **nhóm toán tử**, không đảo thứ tự đánh giá trái-sang-phải |
| “Đối số có thể chạy theo thứ tự bất kỳ để tối ưu.” | Java quy định **đối số lời gọi được đánh giá từ trái sang phải** |
| “Biểu thức bên trái có thể bị đọc lại sau khi vế phải gán biến.” | Giá trị toán hạng trái đã đánh giá được giữ theo ngữ nghĩa toán tử |
| “`counter++` trong ba đối số đều trả cùng số.” | Đối số lần lượt thấy giá trị đã tăng từ đối số trước |
| “`&&` và `&` đều bỏ qua vế phải khi vế trái false.” | Chỉ `&&` ngắn mạch; `&` boolean đánh giá hai vế nếu bình thường |
| “`?:` đánh giá cả hai nhánh rồi chọn kết quả.” | Chỉ nhánh được chọn được đánh giá |
| “Nếu một đối số ném exception, các đối số còn lại vẫn chạy.” | Không đánh giá tiếp các đối số phía sau |
| “Java quyết định thứ tự gọi theo cách trình biên dịch thích.” | Thứ tự quan sát được phải tuân theo ngữ nghĩa được đặc tả |

## 7. Bài tập tự kiểm tra

1. **Precedence:** Trong `a() + b() * c()`, thứ tự gọi là gì nếu cả ba chạy bình thường?  
   *Đáp án:* `a()`, `b()`, `c()`; giá trị vẫn được nhóm như `a() + (b() * c())`.
2. **Đối số:** `show(mark("A", 1), mark("B", 2))` in dấu nào trước?  
   *Đáp án:* `A` trước `B`.
3. **Tác dụng phụ:** `int n = 10; int x = n + (n = 20);` cho `x`, `n` bao nhiêu?  
   *Đáp án:* `x = 30`, `n = 20`.
4. **Tăng hậu tố:** `int n = 1; digits(n++, n++, n++);` nhận ba đối số nào và `n` sau đó là gì?  
   *Đáp án:* 1, 2, 3 và `n = 4`.
5. **Ngắn mạch:** `false && sideEffect()` có gọi `sideEffect()` không?  
   *Đáp án:* Không.
6. **Không ngắn mạch:** `false & sideEffect()` có gọi `sideEffect()` không, nếu phương thức trả `boolean`?  
   *Đáp án:* Có, nếu không có ngoại lệ.
7. **Ngoại lệ:** Nếu đối số thứ hai ném ngoại lệ, đối số thứ ba có được đánh giá không?  
   *Đáp án:* Không; lời gọi phương thức không được thực hiện theo cách bình thường.

## Checklist

- [ ] Tách biệt **độ ưu tiên/tính kết hợp** với **thứ tự đánh giá**.
- [ ] Với toán hạng và đối số thông thường, nắm quy tắc **trái sang phải**.
- [ ] Khi gọi phương thức instance, xem xét biểu thức receiver trước danh sách đối số.
- [ ] Hiểu giá trị đã đánh giá được giữ khi vế sau có tác dụng phụ.
- [ ] Nhận diện ngoại lệ ngắn mạch `&&`, `||` và chọn nhánh `?:`.
- [ ] Hiểu exception có thể ngăn phần biểu thức phía sau được đánh giá.
- [ ] Ưu tiên tách các biểu thức có nhiều tác dụng phụ thành các lệnh rõ ràng.

**Kết luận:** Java quy định rõ thứ tự đánh giá toán hạng và đối số **từ trái sang phải** trong các ngữ cảnh tương ứng. Hãy phân biệt điều đó với **cách nhóm phép toán**, và nhớ rằng ngắn mạch, chọn nhánh và ngoại lệ có thể làm bỏ qua các biểu thức không cần hoặc không thể tiếp tục.
