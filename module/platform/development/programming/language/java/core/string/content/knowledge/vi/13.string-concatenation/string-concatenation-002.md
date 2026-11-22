# Thứ tự kết hợp trái–phải của toán tử `+` với số và chuỗi trong Java

## 1. Mục tiêu bài học

Toán tử `+` trong Java có hai vai trò quan trọng:

- **Cộng số** khi các toán hạng thuộc loại số và phép cộng số được áp dụng.
- **Nối chuỗi** khi một trong hai toán hạng của phép `+` là `String`.

Các phép `+` đứng liên tiếp ở cùng mức ưu tiên có **tính kết hợp trái** (*left associativity*): Java phân nhóm từ trái sang phải, nếu không có dấu ngoặc hoặc toán tử có mức ưu tiên cao hơn làm thay đổi cách nhóm.

Vì vậy:

```java
System.out.println(1 + 2 + "3");  // 33
System.out.println("1" + 2 + 3);  // 123
```

Hai biểu thức chứa các ký hiệu tương tự nhưng kết quả khác nhau. Điều cần nắm là **mỗi dấu `+` được xử lý dựa trên kiểu kết quả ở vị trí đó trong biểu thức**, chứ không phải cứ nhìn thấy một `String` ở bất kỳ đâu là toàn bộ phép `+` tự động biến thành phép nối.

Sau bài này bạn sẽ:
1. Đọc đúng phép `+` theo thứ tự kết hợp trái–phải.
2. Phân biệt cộng số trước khi nối chuỗi và nối chuỗi ngay từ đầu.
3. Sử dụng dấu ngoặc để chủ động tạo kết quả mong muốn.
4. Tránh nhầm tính kết hợp với **độ ưu tiên toán tử** hoặc **thứ tự đánh giá toán hạng**.
5. Nhận biết các trường hợp dễ sai với `char`, `null`, `+=`, kiểu số và tràn số.

## 2. Quy tắc cốt lõi: một phép `+`, hai ngữ nghĩa

Trong biểu thức Java, phép cộng số áp dụng cho các toán hạng kiểu số phù hợp. Khi **một toán hạng của phép `+` là `String`**, phép toán đó là **string concatenation** (nối chuỗi). Giá trị còn lại được chuyển thành dạng chuỗi theo quy tắc chuyển đổi khi nối chuỗi.

Ví dụ:

| Biểu thức | Ý nghĩa tại dấu `+` | Kết quả |
| --- | --- | --- |
| `1 + 2` | Cộng hai số `int` | Số `3` |
| `1 + 2.5` | Cộng số, có chuyển đổi kiểu số | Số `3.5` |
| `"1" + 2` | Nối chuỗi `"1"` và số `2` | Chuỗi `"12"` |
| `1 + "2"` | Nối chuỗi `"1"` và `"2"` | Chuỗi `"12"` |
| `"Hi " + "Java"` | Nối hai chuỗi | Chuỗi `"Hi Java"` |

Khi một phép `+` đã tạo ra `String`, nếu kết quả đó lại đứng ở bên trái một phép `+` tiếp theo, phép tiếp theo thường tiếp tục **nối chuỗi**.

```java
String text = "A" + 1;      // "A1"
String longer = text + 2;   // "A12"
```

Điểm cần lưu ý: `"A" + 1 + 2` không cộng `1 + 2` trước. Các phép `+` cùng mức sẽ được nhóm từ trái sang phải, trừ khi dấu ngoặc hoặc toán tử ưu tiên cao hơn thay đổi việc nhóm.

## 3. Tính kết hợp trái: đọc từng bước

Xét hai biểu thức:

### Trường hợp A: cộng số trước rồi nối chuỗi

```java
String a = 1 + 2 + "3";
```

Với tính kết hợp trái, cách nhóm là:

```text
(1 + 2) + "3"
   3     + "3"
       "33"
```

Ở phép `+` đầu tiên, cả hai toán hạng đều là số nguyên nên kết quả là **số 3**. Phép tiếp theo có `String "3"` nên cho kết quả **chuỗi "33"**.

### Trường hợp B: nối chuỗi ngay từ đầu

```java
String b = "1" + 2 + 3;
```

Cách nhóm:

```text
("1" + 2) + 3
    "12"   + 3
       "123"
```

Dấu `+` đầu tiên tạo ra `String "12"`. Dấu `+` tiếp theo nối tiếp số `3` thành chuỗi `"123"`, **không** cộng `2 + 3`.

### Trường hợp C: chuỗi nằm ở giữa

```java
String c = 1 + "2" + 3;
```

Cách nhóm:

```text
(1 + "2") + 3
    "12"    + 3
        "123"
```

Bởi phép đầu tiên đã có toán hạng kiểu `String`, nó nối chuỗi ngay từ đầu. Kết quả cuối cũng là `"123"`, mặc dù `1` và `3` là số.

Bảng so sánh:

| Biểu thức | Cách hiểu | Kết quả chuỗi |
| --- | --- | --- |
| `1 + 2 + "3"` | `(1 + 2) + "3"` | `"33"` |
| `"1" + 2 + 3` | `("1" + 2) + 3` | `"123"` |
| `1 + "2" + 3` | `(1 + "2") + 3` | `"123"` |
| `1 + 2 + "3" + 4` | `((1 + 2) + "3") + 4` | `"334"` |
| `"1" + 2 + 3 + 4` | `((("1" + 2) + 3) + 4)` | `"1234"` |

**Cách dự đoán:** đi từ trái sang phải qua các phép `+` cùng mức, luôn theo dõi kiểu của **kết quả trung gian**: còn là số thì có thể tiếp tục cộng số; đã trở thành `String` thì phép `+` với giá trị tiếp theo nối chuỗi.

## 4. Dấu ngoặc quyết định phép cộng số

Muốn hiển thị **tổng** của hai số trong một chuỗi, hãy dùng dấu ngoặc:

```java
int a = 10;
int b = 20;

System.out.println("Tổng = " + a + b);     // Tổng = 1020
System.out.println("Tổng = " + (a + b));   // Tổng = 30
```

Biểu thức `"Tổng = " + a + b` được hiểu như `("Tổng = " + a) + b`, nên các số được chuyển lần lượt sang chuỗi.

Trong `"Tổng = " + (a + b)`, Java đánh giá `a + b` trước, tạo ra số `30`, sau đó nối số này vào chuỗi.

Dấu ngoặc cũng có thể tạo kết quả khác trong ví dụ ban đầu:

```java
System.out.println(1 + (2 + "3")); // 123
System.out.println("1" + (2 + 3)); // 15
```

Giải thích:
- `2 + "3"` → `"23"`, rồi `1 + "23"` → `"123"`.
- `2 + 3` → số `5`, rồi `"1" + 5` → `"15"`.

**Quy tắc thực hành:** khi muốn nối nhãn và kết quả một biểu thức số học, hãy dùng `"Nhãn: " + (biểuThứcSố)`. Đây là cách viết rõ nghĩa và tránh sai số do đọc nhầm chuỗi phép `+`.

## 5. Độ ưu tiên toán tử khác với tính kết hợp

Tính kết hợp trái áp dụng khi các toán tử `+` có **cùng mức ưu tiên**. Nó không vượt qua độ ưu tiên của toán tử khác.

Phép `*` có độ ưu tiên cao hơn `+`:

```java
System.out.println(1 + 2 * 3 + "4");  // 74
System.out.println("1" + 2 * 3);      // 16
```

Trong dòng đầu:
1. `2 * 3` → số `6`.
2. `1 + 6` → số `7`.
3. `7 + "4"` → chuỗi `"74"`.

Trong dòng hai, `2 * 3` → số `6`, rồi `"1" + 6` → chuỗi `"16"`.

Dấu ngoặc có thể thay đổi điều này:

```java
System.out.println((1 + 2) * 3 + "4"); // 94
System.out.println("1" + (2 + 3));     // 15
```

Điều này có nghĩa là không thể dùng quy tắc “đọc toàn bộ biểu thức bằng thứ tự xuất hiện” khi còn `*`, `/`, dấu ngoặc hoặc toán tử khác.

### Lưu ý với toán tử trừ

`+` có thể là phép nối chuỗi, nhưng `-` **không** có phiên bản tương tự dành cho `String`:

```java
// Không biên dịch:
// System.out.println("Kết quả: " + 10 - 3);
```

Java nhóm từ trái sang phải: `("Kết quả: " + 10) - 3`. Sau phép `+` đầu tiên, vế trái của `-` là `String`, nên phép trừ không hợp lệ.

Viết đúng:

```java
System.out.println("Kết quả: " + (10 - 3)); // Kết quả: 7
```

Dấu ngoặc vừa thể hiện ý định, vừa ngăn kiểu `String` xuất hiện quá sớm trong phép tính.

## 6. Phân biệt tính kết hợp với thứ tự đánh giá toán hạng

Hai khái niệm liên quan nhưng **không giống nhau**:

- **Associativity (tính kết hợp)** cho biết cách nhóm các toán tử cùng mức ưu tiên: `a + b + c` được nhóm như `(a + b) + c`.
- **Evaluation order (thứ tự đánh giá)** cho biết biểu thức con nào được đánh giá trước khi tính toán. Java bảo đảm đánh giá các toán hạng của toán tử nhị phân theo thứ tự từ trái sang phải.

Ví dụ:

```java
static int first() {
    System.out.print("A ");
    return 1;
}

static int second() {
    System.out.print("B ");
    return 2;
}

static String third() {
    System.out.print("C ");
    return "3";
}
```

Khi gọi trong một phương thức:

```java
String result = first() + second() + third();
System.out.println(result);
```

Kết quả:

```text
A B C 33
```

Ba phương thức được gọi theo thứ tự trái sang phải: `first`, `second`, `third`. Sau đó giá trị trả về tạo thành `1 + 2 + "3"` → `"33"`.

Chú ý: dù trình biên dịch hoặc JVM có thể tối ưu cách triển khai nối chuỗi, chương trình vẫn phải tuân thủ **hành vi quan sát được** của Java, bao gồm thứ tự và ngoại lệ của các biểu thức con theo đặc tả.

### Dấu ngoặc có thể thay đổi cách nhóm nhưng không có nghĩa mọi thứ đều đổi thứ tự gọi

`a + (b + c)` làm phép `b + c` được nhóm trước phép `+` bên ngoài, nhưng Java vẫn đánh giá toán hạng `a` trước khi đánh giá toán hạng bên phải `(b + c)`. Không nên nhầm **thứ tự phép toán được nhóm** với **thứ tự gọi hàm có tác dụng phụ**.

## 7. Chương trình Java 17+ chạy độc lập

Lưu thành file `PlusAssociativityDemo.java`:

```java
public class PlusAssociativityDemo {
    static int first() {
        System.out.print("A ");
        return 1;
    }

    static int second() {
        System.out.print("B ");
        return 2;
    }

    static String third() {
        System.out.print("C ");
        return "3";
    }

    public static void main(String[] args) {
        System.out.println("A = " + (1 + 2 + "3"));
        System.out.println("B = " + ("1" + 2 + 3));
        System.out.println("C = " + (1 + "2" + 3));

        System.out.println("sum wrong = " + 10 + 20);
        System.out.println("sum correct = " + (10 + 20));

        System.out.println("parentheses = "
                + ("1" + (2 + 3)));
        System.out.println("precedence = "
                + (1 + 2 * 3 + "4"));

        System.out.println("char as number = " + ('A' + 1));
        System.out.println("char in string = " + ('A' + "1"));

        String text = "x";
        text += 1 + 2;
        System.out.println("compound = " + text);

        String other = "x";
        other = other + 1 + 2;
        System.out.println("normal = " + other);

        System.out.print("evaluation = ");
        String evaluation = first() + second() + third();
        System.out.println(evaluation);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PlusAssociativityDemo.java
java PlusAssociativityDemo
```

Kết quả chuẩn:

```text
A = 33
B = 123
C = 123
sum wrong = 1020
sum correct = 30
parentheses = 15
precedence = 74
char as number = 66
char in string = A1
compound = x3
normal = x12
evaluation = A B C 33
```

**Giải thích ba điểm dễ nhầm trong chương trình:**

1. `'A' + 1` là **cộng số**, vì `char` có thể được nâng kiểu sang `int` trong phép tính số: mã của `'A'` là `65` nên kết quả `66`. Còn `'A' + "1"` là nối chuỗi `"A1"`.
2. `text += 1 + 2` tạo `"x3"`, bởi biểu thức phía phải `1 + 2` được tính thành `3` trước khi nối với giá trị cũ của `text` trong phép gán kết hợp. Nhưng `other = other + 1 + 2` có các phép `+` cùng chuỗi bên phải, kết hợp trái thành `"x12"`.
3. `first()`, `second()`, `third()` đều được gọi theo thứ tự từ trái sang phải, rồi giá trị trả về cho kết quả `"33"`.

## 8. Trường hợp riêng: `char` kết hợp với `+`

Khi chưa có `String`, `char` được nâng thành số trước phép cộng; khi có `String`, nó được nối thành ký tự:

```java
System.out.println('A' + 'B' + "");  // 131
System.out.println("" + 'A' + 'B');  // AB
```

Các quy tắc thu hẹp hằng số, `char +=`, Unicode code point và lời gọi `println` được thực hành ở bài **Phân biệt ký tự cộng số với nối chuỗi**.

## 9. `null` và giá trị không phải chuỗi

Tham chiếu `String` bằng `null` vẫn được chuyển thành văn bản `"null"` khi tham gia phép nối: `"x=" + ((String) null)` cho `"x=null"`. Dấu `+` không tự bỏ giá trị thiếu. Với dữ liệu thực, quyết định thay bằng nhãn, bỏ qua, giữ trạng thái thiếu hay từ chối trước khi nối; bài **concat và khác biệt về đối số null** đào sâu hợp đồng các API.

## 10. `+=` không giống mọi cách viết có dấu `+`

Một câu hỏi dễ nhầm là:

```java
String a = "x";
a += 1 + 2;
```

Nhiều người đoán `"x12"` vì thấy chuỗi đứng bên trái. Nhưng phép `+=` là **gán kết hợp**; vế phải là biểu thức độc lập `1 + 2`, được tính thành **số `3`**. Sau đó Java nối số này vào giá trị cũ của `a`:

```text
a += (1 + 2)
a = "x" + 3
a = "x3"
```

Đối chiếu:

```java
String a = "x";
a += 1 + 2;         // "x3"

String b = "x";
b = b + 1 + 2;      // "x12"

String c = "x";
c = c + (1 + 2);    // "x3"
```

Điểm mấu chốt không phải một quy tắc đặc biệt chỉ dành cho `String`, mà là sự khác nhau giữa **biểu thức bên phải phép gán kết hợp** và **chuỗi các phép `+` bình thường**.

Việc một giá trị `String` bất biến cũng có nghĩa `a += ...` không chỉnh sửa nội dung chuỗi cũ, mà tạo kết quả chuỗi để gán lại biến `a`. Nếu thực hiện rất nhiều lần nối trong vòng lặp, hãy cân nhắc `StringBuilder`.

## 11. Tràn số xảy ra trước khi nối chuỗi

Nối chuỗi không làm cho phép cộng số đã diễn ra trước đó trở nên an toàn khỏi tràn số.

```java
int max = Integer.MAX_VALUE;

System.out.println(max + 1 + ""); // -2147483648
System.out.println("" + max + 1); // 21474836471
```

Giải thích:
- `max + 1 + ""` cộng `int` trước, nên kết quả `int` tràn từ `2147483647` thành `-2147483648`, sau đó được nối với chuỗi rỗng.
- `"" + max + 1` bắt đầu bằng nối chuỗi, cho văn bản `"2147483647"` rồi nối chữ số `1`; kết quả `"21474836471"` không phải phép tính số.

Nếu cần tính toán trong miền số lớn hơn, hãy nâng kiểu **trước khi cộng**, ví dụ:

```java
long result = (long) max + 1;
System.out.println("Result = " + result); // Result = 2147483648
```

Đừng dùng việc “nối chuỗi sớm” như một cách thay thế phép tính số: nó chỉ tạo văn bản, không giải quyết phép toán hay lỗi tràn số của nghiệp vụ.

## 12. Các lỗi thường gặp và cách khắc phục

| Sai lầm | Ví dụ dễ sai | Cách viết rõ ý |
| --- | --- | --- |
| Nghĩ mọi số trong biểu thức có chuỗi sẽ được cộng trước. | `"sum=" + a + b` | `"sum=" + (a + b)` khi cần tổng. |
| Nghĩ `+` luôn nối trái sang phải bất kể ưu tiên. | `"x" + 2 * 3` | Hiểu `*` thực hiện trước phép nối: `"x6"`. |
| Không biết khi nào kết quả trung gian thành `String`. | `1 + 2 + "3"` vs `"1" + 2 + 3` | Theo dõi kiểu sau mỗi dấu `+`. |
| Cố trừ ngay sau kết quả nối chuỗi. | `"x" + 10 - 3` | `"x" + (10 - 3)`. |
| Xem `char + char` là nối hai ký tự. | `'A' + 'B'` | `"" + 'A' + 'B'` hoặc `StringBuilder`. |
| Hiểu `+=` như mọi phép `+` cùng chuỗi thông thường. | `text += 1 + 2` | Nhớ vế phải `1 + 2` là phép cộng số trước. |
| Tin rằng nối chuỗi tránh được tràn số. | `max + 1 + ""` | Dùng `long` hoặc kiểu số phù hợp trước khi cộng. |
| Cho rằng phép nối làm `null` biến mất. | `"x" + nullable` | Chỉ rõ chính sách `null`. |
| Ghép chuỗi lặp lại quá nhiều lần trong vòng lặp. | `result = result + part` | Dùng `StringBuilder` khi xây dựng nội dung tăng dần. |

## 13. Hiệu năng và hành vi trình biên dịch

Thứ tự kết hợp và nội dung của `+` là quy tắc Java, không phụ thuộc hình dạng bytecode. Compiler có thể gộp hằng và JDK hiện đại có thể dùng `invokedynamic`, nhưng không được đổi hành vi quan sát được. Việc xây chuỗi nhiều lần trong vòng lặp là bài toán hiệu năng khác: xem bài **Nối trong một biểu thức so với tích lũy qua vòng lặp**.

## 14. Bài tập dự đoán kết quả

### Bài 1

```java
System.out.println(3 + 4 + "5");
System.out.println("3" + 4 + 5);
System.out.println(3 + "4" + 5);
```

**Đáp án:**

```text
75
345
345
```

Dòng đầu cộng số `3 + 4 = 7` rồi nối `"5"`. Hai dòng sau nối chuỗi ngay từ phép `+` đầu tiên.

### Bài 2

```java
System.out.println("total=" + 4 * 5 + 2);
System.out.println("total=" + (4 * 5 + 2));
```

**Đáp án:**

```text
total=202
total=22
```

Ở dòng đầu, `4 * 5` tạo số `20`, rồi phép `+` với chuỗi tạo `"total=20"` và nối số `2` thành `"total=202"`. Dòng thứ hai dùng ngoặc tính `4 * 5 + 2 = 22` trước.

### Bài 3

```java
System.out.println('A' + 'B');
System.out.println("" + 'A' + 'B');
```

**Đáp án:**

```text
131
AB
```

Hai `char` cộng kiểu số ở dòng đầu; dòng hai bắt đầu bằng chuỗi rỗng nên phép `+` chuyển sang nối chuỗi.

### Bài 4

```java
String x = "N";
x += 2 + 3;
System.out.println(x);

String y = "N";
y = y + 2 + 3;
System.out.println(y);
```

**Đáp án:**

```text
N5
N23
```

`x += 2 + 3` tính vế phải `2 + 3` trước; `y + 2 + 3` nối trái sang phải ngay từ `y`.

### Bài 5

```java
System.out.println(1 + (2 + "3"));
System.out.println("1" + (2 + 3));
```

**Đáp án:**

```text
123
15
```

Dấu ngoặc thay đổi biểu thức con tạo ra `String` hay số, từ đó thay đổi kết quả phép `+` bên ngoài.

### Bài 6: sửa lỗi

Đoạn sau không biên dịch:

```java
// String text = "Còn lại = " + 10 - 3;
```

**Cách sửa:**

```java
String text = "Còn lại = " + (10 - 3);
System.out.println(text); // Còn lại = 7
```

Dấu `+` với `String` tạo chuỗi; không thể dùng phép `-` số học trực tiếp trên kết quả đó.

## 15. Ghi nhớ

- `+` thực hiện **cộng số** khi hai toán hạng là số phù hợp; khi có toán hạng `String`, nó là **nối chuỗi**.
- Các phép `+` cùng mức ưu tiên **kết hợp trái**: `a + b + c` được nhóm `(a + b) + c`.
- `1 + 2 + "3"` → `"33"`, còn `"1" + 2 + 3` → `"123"`.
- Dấu ngoặc có thể buộc một phép cộng số diễn ra trước phép nối, ví dụ `"sum=" + (a + b)`.
- Độ ưu tiên (`*` trước `+`), tính kết hợp và thứ tự đánh giá các toán hạng là **ba khái niệm khác nhau**.
- `char + char` là phép cộng số nếu không có `String`; `+=` có ngữ nghĩa riêng của phép gán kết hợp.
- Một phép cộng số thực hiện **trước** phép nối chuỗi vẫn có thể tràn số.
- Với biểu thức có nhiều thành phần, hãy ưu tiên dấu ngoặc và tên biến trung gian để người đọc thấy rõ ý nghĩa.

## Tài liệu tham khảo

- [Java Language Specification `15.18 — Additive Operators`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18)
- [Java Language Specification `15.7 — Evaluation Order`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7)
- [Java Language Specification `15.26 — Assignment Operators`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26)
- [Java SE 17 — `StringBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
