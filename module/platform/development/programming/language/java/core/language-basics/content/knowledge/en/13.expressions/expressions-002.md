# Toán hạng, toán tử và biểu thức lồng nhau — Java 17+

Một **biểu thức** (*expression*) trong Java là cấu trúc có thể được đánh giá để tạo ra một **giá trị** hoặc biến (trong một số trường hợp) thực hiện phép gán hay gây tác dụng phụ. Để đọc đúng biểu thức phức tạp, cần phân biệt ba khái niệm:

- **Toán hạng** (*operand*): phần dữ liệu mà toán tử tác động lên, ví dụ literal `5`, biến `price`, lời gọi `getPrice()` hoặc **một biểu thức con**.
- **Toán tử** (*operator*): ký hiệu hoặc cấu trúc thực hiện phép toán, ví dụ `+`, `*`, `!`, `&&`, `?:`, `=`.
- **Biểu thức lồng nhau** (*nested expression*): một biểu thức được dùng làm toán hạng trong biểu thức lớn hơn, có thể được nhóm bằng dấu ngoặc tròn để thể hiện rõ ý.

~~~java
int total = 8 + 3 * 2;
~~~

Trong biểu thức `8 + 3 * 2`, `8`, `3`, `2` là toán hạng đơn giản; `+` và `*` là toán tử. Do `*` có độ ưu tiên cao hơn `+`, biểu thức được **nhóm** như `8 + (3 * 2)` và có giá trị **14**.

**Điểm then chốt:** *độ ưu tiên quyết định cách nhóm toán hạng*, còn *thứ tự đánh giá* quyết định khi nào các phần được chạy. Đây là hai khái niệm khác nhau trong Java.

## 1. Các dạng toán hạng và toán tử

| Dạng | Biểu thức minh họa | Diễn giải |
| --- | --- | --- |
| Literal | `42`, `true`, `"Java"` | Giá trị viết trực tiếp |
| Biến | `quantity` | Đọc giá trị biến |
| Lời gọi phương thức | `name.length()` | Kết quả của phương thức có kiểu trả về phù hợp |
| Truy cập phần tử | `scores[0]` | Giá trị ở vị trí mảng |
| Toán tử một ngôi | `-x`, `!enabled`, `++n` | Một toán hạng |
| Toán tử hai ngôi | `a + b`, `a * b`, `x > y` | Hai toán hạng |
| Toán tử điều kiện ba ngôi | `condition ? a : b` | Ba phần: điều kiện và hai nhánh |
| Gán | `x = 10`, `x += 2` | Có giá trị biểu thức và tác dụng gán |
| Ép kiểu | `(double) sum` | Chuyển kiểu biểu thức |
| Lồng nhau | `(a + b) * (c - d)` | Biểu thức con làm toán hạng |

Một **literal** như `7` đã là biểu thức đơn giản; không phải mọi biểu thức đều cần một toán tử. Ngược lại, một **câu lệnh** (*statement*) như `if (...) { ... }` là cấu trúc điều khiển, không phải toán hạng mang giá trị có thể thay trực tiếp vào phép cộng.

## 2. Nhóm biểu thức và dấu ngoặc

Đọc hai biểu thức có cùng con số nhưng khác cách nhóm:

~~~java
int a = 8 + 3 * 2;     // 14.
int b = (8 + 3) * 2;   // 22.
~~~

Có thể hình dung cây biểu thức:

~~~text
8 + 3 * 2             (8 + 3) * 2

       +                     *
      / \                   / \
     8   *                 +   2
        / \               / \
       3   2             8   3
~~~

Nhóm theo cây bên trái: `3 * 2` là một toán hạng của `+`. Nhóm theo cây bên phải: `8 + 3` là một toán hạng của `*`.

Dấu ngoặc tròn có thể **thay đổi cách nhóm** hoặc chỉ làm cách nhóm sẵn có **dễ đọc hơn**:

~~~java
int a = 8 + 3 * 2;          // 14.
int b = 8 + (3 * 2);        // 14: nhom ro hon, khong doi gia tri.
int c = (8 + 3) * 2;        // 22: thay doi nhom.
~~~

Tuy vậy, dấu ngoặc **không** thay đổi quy tắc kiểu dữ liệu. Ví dụ `(5 / 2)` vẫn chia nguyên và trả `2`; muốn `2.5` phải có toán hạng số thực, chẳng hạn `5 / 2.0`.

## 3. Nhìn cây nhóm trước, theo dõi đánh giá sau

Độ ưu tiên và tính kết hợp xác định biểu thức con nào là toán hạng của toán tử lớn hơn. Chẳng hạn, `20 - 5 - 3` nhóm thành `(20 - 5) - 3` và có giá trị 12; `a = b = 7` nhóm thành `a = (b = 7)`.

Đừng nhầm cấu trúc ấy với **thứ tự gọi method**. Trong `first() + second() * third()`, phép nhân là nhánh phải của phép cộng nhưng các lời gọi (khi đều hoàn tất bình thường) chạy lần lượt `first`, `second`, `third`. Nếu là `left && right`, Java còn có thể bỏ qua `right`. Vì vậy khi đọc biểu thức lồng nhau, hãy vẽ cây **nhóm toán tử** trước rồi mới lần theo thứ tự đánh giá các toán hạng của từng nhánh.

## 4. Chương trình Java 17+ runnable

Tạo file UTF-8 tên **`NestedExpressionsDemo.java`**:

~~~java
public class NestedExpressionsDemo {
    static int mark(String label, int value) {
        System.out.println("visit=" + label);
        return value;
    }

    static boolean check(String label, boolean value) {
        System.out.println("check=" + label);
        return value;
    }

    public static void main(String[] args) {
        int x = 8;
        int y = 3;

        System.out.println("precedence=" + (x + y * 2));
        System.out.println("parentheses=" + ((x + y) * 2));
        System.out.println("nested=" + ((x + (y * 2)) - (x / y)));
        System.out.println("remainder=" + (x % y));
        System.out.println("unary=" + (-x + y));
        System.out.println("leftAssociative=" + (20 - 5 - 3));

        boolean comparison = (x + y * 2) > 10;
        System.out.println("comparison=" + comparison);
        System.out.println("logical=" + ((x > y) && (y > 0)));
        System.out.println("ternary=" + (x > y ? x - y : y - x));

        System.out.println("stringUngrouped=" + 1 + 2);
        System.out.println("stringGrouped=" + (1 + 2));
        System.out.println("integerDivision=" + ((x + y) / 4));
        System.out.println("decimalDivision=" + ((x + y) / 4.0));

        int order = mark("left", 2)
                + mark("middle", 3) * mark("right", 4);
        System.out.println("orderResult=" + order);

        boolean shortcut = check("first", true)
                || check("skipped", false);
        System.out.println("orResult=" + shortcut);

        int divisor = 0;
        boolean safe = (divisor != 0) && (x / divisor > 1);
        System.out.println("safeDivision=" + safe);

        int count = 4;
        int assigned = (count += 3) * 2;
        System.out.println("assignmentValue=" + assigned);
        System.out.println("countAfterAssignment=" + count);

        int n = 5;
        int post = n++ + 2;
        System.out.println("postResult=" + post);
        System.out.println("nAfterPost=" + n);

        int a;
        int b;
        a = b = 7;
        System.out.println("chainedAssignment=" + a + "," + b);
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) ở thư mục chứa file, dùng **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NestedExpressionsDemo.java
java NestedExpressionsDemo
~~~

**Exact expected output** của lệnh `java NestedExpressionsDemo`:

~~~text
precedence=14
parentheses=22
nested=12
remainder=2
unary=-5
leftAssociative=12
comparison=true
logical=true
ternary=5
stringUngrouped=12
stringGrouped=3
integerDivision=2
decimalDivision=2.75
visit=left
visit=middle
visit=right
orderResult=14
check=first
orResult=true
safeDivision=false
assignmentValue=14
countAfterAssignment=7
postResult=7
nAfterPost=6
chainedAssignment=7,7
~~~

Hai lệnh `java -version` và `javac -version` hiển thị phiên bản của máy đang chạy, không thuộc khối stdout cố định ở trên.

### Đọc kết quả theo từng nhóm

**Nhóm số học:** `x + y * 2` bằng `8 + 6 = 14`, còn `(x + y) * 2` bằng `11 * 2 = 22`. Biểu thức lồng `(x + (y * 2)) - (x / y)` bằng `14 - 2 = 12` vì `8 / 3` là phép chia `int`.

**Nhóm so sánh và logic:** toán tử `>` tạo kết quả `boolean`; `&&` kết hợp hai giá trị boolean; `?:` chỉ đánh giá nhánh được chọn. Điều kiện `x > y` là true nên kết quả ba ngôi là `x - y = 5`.

**Nhóm chuỗi:** `"stringUngrouped=" + 1 + 2` được đánh giá qua các phép nối từ trái sang phải, cho `"stringUngrouped=12"`. `"stringGrouped=" + (1 + 2)` buộc cộng số trước, cho `"stringGrouped=3"`. Toán tử `+` có thể là phép cộng số **hoặc nối chuỗi**, tùy kiểu toán hạng.

**Nhóm thứ tự đánh giá:** dù phép nhân có độ ưu tiên cao hơn cộng, `mark("left", 2)` chạy trước, rồi `mark("middle", 3)` và `mark("right", 4)`. Các dấu `visit=...` trong output chứng minh trình tự đánh giá các toán hạng của biểu thức `a() + b() * c()`.

**Nhóm ngắn mạch:** với `||`, khi toán hạng trái đã là true, phương thức `check("skipped", false)` **không được gọi**; vì thế chỉ có `check=first`. Với `&&`, khi `divisor != 0` là false, Java không đánh giá `x / divisor > 1`, nên tránh được phép chia cho 0. Không dựa vào mẹo này nếu biến có thể bị thay đổi đồng thời mà chưa đồng bộ phù hợp.

**Nhóm tác dụng phụ:** `count += 3` vừa cập nhật `count` từ 4 thành 7, vừa có giá trị 7; sau đó nhân 2 cho `assigned = 14`. `n++` sử dụng giá trị cũ 5 trong biểu thức, sau đó biến thành 6; `post = 5 + 2 = 7`.

## 5. Phân tích biểu thức theo ba bước

Khi gặp một biểu thức dài, hãy đi theo quy trình:

1. **Xác định các toán hạng**: literal, biến, lời gọi phương thức, truy cập phần tử hoặc biểu thức lồng.
2. **Nhóm theo dấu ngoặc, độ ưu tiên và tính kết hợp**: xác định cây biểu thức và kiểu kết quả của từng phần.
3. **Theo dõi đánh giá lúc chạy**: xét thứ tự toán hạng, ngắn mạch, nhánh điều kiện được chọn và tác dụng phụ.

Ví dụ `(price + tax) * quantity >= minimum && active`:

~~~text
                     &&
                    /  \
                  >=   active
                 /  \
                *  minimum
               / \
              + quantity
             / \
          price tax
~~~

Để đúng kiểu Java, giả sử `price`, `tax`, `quantity`, `minimum` có các kiểu số tương thích và `active` là `boolean`. Biểu thức con bên trái `>=` có kiểu boolean; toàn bộ `&&` cũng có kiểu boolean. Nếu phần bên trái `&&` false thì giá trị `active` không cần được đánh giá.

Sơ đồ chỉ thể hiện **cách nhóm**, không phải lịch trình từng lời gọi hoặc tác dụng phụ trong biểu thức.

## 6. Kiểu của từng biểu thức con

Lồng nhau không làm mất quy tắc kiểu: mỗi nút của cây biểu thức vẫn cần toán hạng đúng kiểu. Ví dụ:

~~~java
int a = 5, b = 2;
boolean ok = (a + b) > 6 && b != 0; // true
~~~

`a + b` có kiểu `int`; phép `> 6` và `b != 0` đều có kiểu `boolean`; kết quả của `&&` cũng là `boolean`. Ngoặc quanh `(a + b)` chỉ nhóm phép tính, không làm nó thành `double`; Java không chuyển ngầm số 0 thành `false` như một số ngôn ngữ khác.

## 7. Cách nhóm không thay thế kiểm tra kiểu và giới hạn

~~~java
int price = 50_000, units = 50_000;
long overflowed = (long) (price * units); // Nhân int trước, đã tràn
long safeSize = (long) price * units;      // Nhân long, kết quả 2500000000
~~~

Cây nhóm giúp biết phép nhân nằm ở đâu, nhưng không tự mở rộng kiểu số hay kiểm tra overflow. Muốn tránh mất dữ liệu cần chuyển kiểu **trước** phép tính hoặc dùng phép kiểm tra tràn phù hợp. Với lời gọi có side effect, cân nhắc tách toán hạng thành các biến có tên để dễ kiểm tra.

## 8. Lỗi phổ biến và cách nhận diện

| Ngộ nhận | Thực tế |
| --- | --- |
| “Toán tử `*` ưu tiên cao nên lời gọi ở vế nhân luôn chạy trước.” | Độ ưu tiên quyết định **nhóm**, không đảo thứ tự đánh giá toán hạng Java |
| “`(5 / 2)` có kết quả số thực vì có ngoặc.” | Ngoặc không tự đổi `int` thành `double` |
| “`"x=" + 1 + 2` cho `x=3`.” | Nối chuỗi từ trái sang phải, cho `x=12` |
| “`(a && b)` lúc nào cũng chạy cả hai phía.” | `&&` ngắn mạch khi bên trái false |
| “`a || b` luôn gọi `b`.” | `||` bỏ qua `b` nếu `a` đã true |
| “`(n += 1)` không phải biểu thức có giá trị.” | Phép gán có giá trị và cập nhật biến |
| “`n++` và `++n` luôn cho cùng giá trị trong biểu thức.” | Postfix dùng giá trị cũ, prefix dùng giá trị mới |
| “Thêm ngoặc luôn khiến phép toán không tràn.” | Ngoặc không tự mở rộng miền số hoặc kiểm tra overflow |

## 9. Bài tập tự kiểm tra

1. **Ưu tiên:** `2 + 3 * 4` và `(2 + 3) * 4` lần lượt bằng bao nhiêu?  
   *Đáp án:* 14 và 20.
2. **Kết hợp:** `20 - 5 - 3` bằng bao nhiêu?  
   *Đáp án:* 12, nhóm `(20 - 5) - 3`.
3. **Nối chuỗi:** `"n=" + 1 + 2` khác `"n=" + (1 + 2)` thế nào?  
   *Đáp án:* `"n=12"` và `"n=3"`.
4. **Ngắn mạch:** `int d = 0; boolean ok = d != 0 && 10 / d > 1;` có chia cho 0 không?  
   *Đáp án:* Không, vế phải `&&` bị bỏ qua khi điều kiện đầu false.
5. **Tăng hậu tố:** `int n = 4; int r = n++ + 2;`, cuối cùng `r` và `n` bằng bao nhiêu?  
   *Đáp án:* `r = 6` và `n = 5`.
6. **Kiểu kết quả:** `double x = 5 / 2;` có giá trị bao nhiêu?  
   *Đáp án:* `2.0`; muốn `2.5` cần `5 / 2.0` hoặc cast phù hợp.
7. **Thứ tự đánh giá:** Trong `first() + second() * third()`, nếu các hàm đều trả số và in dấu vết, thứ tự lời gọi nào xảy ra?  
   *Đáp án:* `first()` rồi `second()` rồi `third()`.

## Checklist

- [ ] Nhận diện **toán hạng**, **toán tử**, và **biểu thức con**.
- [ ] Tách biệt **cách nhóm do precedence/associativity** với **thứ tự đánh giá toán hạng**.
- [ ] Sử dụng ngoặc để làm rõ ý, không cho rằng ngoặc tự thay đổi kiểu dữ liệu.
- [ ] Hiểu `&&`/`||`/`?:` có thể bỏ qua đánh giá một nhánh.
- [ ] Theo dõi kiểu và giá trị trung gian, nhất là phép chia nguyên và số có thể tràn.
- [ ] Cẩn thận tác dụng phụ của `=`, `+=`, `++` và lời gọi phương thức trong biểu thức.
- [ ] Khi biểu thức quá dài, cân nhắc đặt tên các bước trung gian để dễ kiểm tra.

**Kết luận:** Hãy đọc biểu thức Java bằng cách xác định **các toán hạng**, **toán tử liên kết chúng**, **cây nhóm của những biểu thức lồng nhau** và **thứ tự đánh giá thực tế**. Cách tiếp cận này giúp tránh nhầm về độ ưu tiên, sai kiểu kết quả và tác dụng phụ khó thấy.
