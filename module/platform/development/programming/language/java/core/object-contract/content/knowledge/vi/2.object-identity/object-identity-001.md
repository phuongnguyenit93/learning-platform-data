# Biến tham chiếu khác với đối tượng được tham chiếu trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể phân biệt **biến tham chiếu** (reference variable) với **đối tượng** (object), giải thích vì sao hai biến có thể cùng trỏ tới một đối tượng, dự đoán tác động của phép gán và thay đổi trạng thái, hiểu `null`, `==` và việc truyền tham số đối tượng trong Java. Đây là nền tảng để tránh những lỗi do vô tình chia sẻ một đối tượng có thể thay đổi (mutable object).

## 1. Hai khái niệm khác nhau

Xét khai báo:

```java
Box first = new Box(10);
```

- `Box` là kiểu tham chiếu. `first` là **một biến** có thể chứa giá trị tham chiếu tới một đối tượng `Box` hoặc giá trị `null`.
- `new Box(10)` tạo ra một **đối tượng** (một thực thể có danh tính và trạng thái). Trường `value` của đối tượng ban đầu bằng `10`.
- Dấu `=` gán **giá trị tham chiếu** của đối tượng mới cho biến `first`; biến `first` không phải chính đối tượng đó.
- `first.value` truy cập trường của đối tượng thông qua tham chiếu đang có trong `first`.

Có thể hình dung:

```text
Biến tham chiếu                   Đối tượng
first ─────────────────────────► Box { value = 10 }
```

Đây là **sơ đồ quan hệ logic**, không phải cam kết về vị trí vật lý của biến hay đối tượng trong bộ nhớ JVM. Trình biên dịch/JVM có thể tối ưu cách lưu trữ; điều cần nắm chắc là **biến tham chiếu và đối tượng là hai thực thể khái niệm khác nhau**.

Một biến kiểu nguyên thủy như `int count = 10;` lưu trực tiếp giá trị nguyên thủy `10`. Ngược lại, với `Box first`, giá trị của `first` là **tham chiếu tới** đối tượng `Box`, không phải toàn bộ dữ liệu của `Box`.

## 2. Nhiều biến có thể tham chiếu cùng một đối tượng

Xét:

```java
Box first = new Box(10);
Box alias = first;
Box sameValue = new Box(10);
```

Sơ đồ:

```text
first ───────────┐
                 ├──────────────► Box A { value = 10 }
alias ───────────┘

sameValue ──────────────────────► Box B { value = 10 }
```

Ở đây:

- `first` và `alias` là **hai biến khác nhau**, nhưng giá trị tham chiếu của chúng cùng chỉ tới **Box A**.
- Lệnh `Box alias = first;` **sao chép giá trị tham chiếu**; nó không tạo bản sao đối tượng và không chạy `new`.
- `sameValue` tham chiếu **Box B**: đối tượng khác, dù trạng thái ban đầu (trường `value`) giống Box A.
- Vì vậy, **số lượng biến tham chiếu không đồng nghĩa số lượng đối tượng**.

Hai đối tượng có thể có trạng thái như nhau nhưng khác danh tính. Ngược lại, hai biến khác nhau có thể cùng tham chiếu một đối tượng duy nhất.

## 3. Thay đổi trạng thái và gán lại biến là hai thao tác khác nhau

Chạy ví dụ độc lập sau với **Java 17+**.

**Tệp `ReferenceVsObjectDemo.java`:**

```java
public class ReferenceVsObjectDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;
        Box sameValue = new Box(10);

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == sameValue: " + (first == sameValue));

        alias.value = 20;
        System.out.println("first.value: " + first.value);

        alias = new Box(30);
        System.out.println("first.value after reassignment: " + first.value);
        System.out.println("alias.value: " + alias.value);

        alias = null;
        System.out.println("first still references an object: " + (first != null));
        System.out.println("alias == null: " + (alias == null));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ReferenceVsObjectDemo.java
java ReferenceVsObjectDemo
```

**Đầu ra chính xác:**

```text
first == alias: true
first == sameValue: false
first.value: 20
first.value after reassignment: 20
alias.value: 30
first still references an object: true
alias == null: true
```

Phân tích theo từng chặng:

1. Sau `Box alias = first;`, cả `first` và `alias` trỏ tới Box A. `first == alias` trả về `true`.
2. `new Box(10)` thứ hai tạo Box B. `first == sameValue` trả về `false`, dù cả hai đối tượng đang có `value = 10`.
3. `alias.value = 20;` **thay đổi trường của Box A**. Đọc qua `first.value` cũng thấy `20` vì `first` vẫn trỏ tới chính Box A.
4. `alias = new Box(30);` **gán lại biến `alias`** để nó trỏ tới Box C. Không làm Box A thay đổi và không làm `first` đổi tham chiếu.
5. `alias = null;` chỉ xóa tham chiếu đang giữ trong **biến `alias`**. `first` vẫn trỏ tới Box A. Box C có thể trở thành đối tượng không còn truy cập được nếu không có tham chiếu mạnh nào khác giữ nó.

So sánh ngắn:

| Câu lệnh | Điều bị thay đổi | Điều không tự động thay đổi |
| --- | --- | --- |
| `Box b = a;` | Biến `b` nhận bản sao tham chiếu từ `a` | Không tạo đối tượng mới |
| `b.value = 20;` | Trạng thái của đối tượng mà `b` tham chiếu | Không gán lại `b` hoặc `a` |
| `b = new Box(30);` | Giá trị tham chiếu lưu trong `b` | Đối tượng cũ và biến `a` |
| `b = a;` (lần nữa) | `b` lại tham chiếu đối tượng của `a` | Không sao chép các trường của đối tượng |
| `b = null;` | Giá trị trong `b` thành `null` | Không hủy đối tượng ngay; tham chiếu khác vẫn tồn tại |

Các từ dễ gây nhầm: **“thay đổi đối tượng”** là sửa trạng thái của thực thể đang được tham chiếu; **“thay đổi biến tham chiếu”** là sửa giá trị tham chiếu lưu trong biến.

## 4. `==` so sánh gì đối với tham chiếu?

Với hai toán hạng thuộc kiểu tham chiếu phù hợp để so sánh, `==` trả về `true` khi chúng cùng tham chiếu **một đối tượng**, hoặc khi cả hai đều là `null`. Đây là phép so sánh **danh tính tham chiếu** (reference identity), không tự so sánh từng trường.

Ví dụ:

```java
Box a = new Box(1);
Box b = a;
Box c = new Box(1);

// a == b là true: cùng một đối tượng.
// a == c là false: hai đối tượng khác nhau.
// a == null là false.
```

Đoạn trên minh họa, giả định lớp `Box` được khai báo như ví dụ đầy đủ ở mục 3.

Phân biệt với `equals(Object)`:

- `a == b` hỏi: **Có cùng đối tượng không?**
- `a.equals(b)` hỏi: **Theo quy tắc của lớp, hai đối tượng có được coi là bằng nhau không?**
- Triển khai mặc định của `Object.equals` so sánh danh tính như `==`. Một lớp có thể ghi đè `equals` để so sánh giá trị/ngữ nghĩa; ví dụ `String` so sánh nội dung chuỗi.
- Không thể suy ra `a == b` từ `a.equals(b) == true`. Hai đối tượng độc lập có thể bằng nhau về nội dung nhưng vẫn có danh tính khác nhau.
- Nếu `a` có thể là `null`, gọi `a.equals(b)` sẽ gây `NullPointerException`. Khi cần so sánh bằng nhau có xử lý `null`, có thể dùng `java.util.Objects.equals(a, b)`.

**Tránh dùng `==` để kiểm tra nội dung `String`**, dù đôi khi hai biến `String` có cùng tham chiếu do cơ chế intern. Việc cùng tham chiếu trong một tình huống không biến `==` thành phép so sánh nội dung. Tương tự, tránh suy luận danh tính từ việc Java có thể dùng lại một số đối tượng wrapper.

`System.identityHashCode(obj)` có thể hữu ích khi chẩn đoán, nhưng **không phải địa chỉ bộ nhớ** và **không bảo đảm duy nhất** giữa mọi đối tượng; không dùng nó thay cho `==` để quyết định danh tính.

## 5. `null` là giá trị tham chiếu, không phải một đối tượng

`Box box = null;` nghĩa là `box` hiện **không tham chiếu tới đối tượng nào**. Không tồn tại “đối tượng null” để truy cập.

```java
Box box = null;

System.out.println(box == null);  // true
// System.out.println(box.value); // Nếu bỏ chú thích: NullPointerException.
```

Kiểm tra `box != null` trước khi truy cập nếu biến có khả năng bằng `null`.

Gán `box = null` không lập tức gọi bộ thu gom rác và không hủy đối tượng trước đó. Một đối tượng chỉ **có thể đủ điều kiện** để thu gom khi không còn có thể truy cập qua các tham chiếu mạnh từ những gốc thích hợp của chương trình. Thời điểm thu gom, nếu có, do JVM quyết định; không nên thiết kế logic phụ thuộc vào lúc đối tượng bị thu hồi.

## 6. Truyền tham số đối tượng: Java luôn truyền theo giá trị

Đối với tham số kiểu tham chiếu, Java **truyền bản sao của giá trị tham chiếu** cho biến tham số trong phương thức. Vì vậy:

- Phương thức có thể dùng bản sao tham chiếu để **thay đổi trạng thái của cùng một đối tượng** mà bên gọi cũng đang tham chiếu.
- Nếu phương thức **gán lại tham số** sang đối tượng khác hoặc `null`, biến tham chiếu ở phía gọi **không bị gán lại**.
- Đây vẫn là **pass-by-value**, không phải pass-by-reference theo nghĩa phương thức nhận được chính biến của bên gọi.

**Tệp `PassingReferenceDemo.java`:**

```java
public class PassingReferenceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box parameter) {
        parameter.value = 7;
    }

    static void reassign(Box parameter) {
        parameter = new Box(99);
        System.out.println("inside reassign: " + parameter.value);
    }

    public static void main(String[] args) {
        Box original = new Box(1);

        mutate(original);
        System.out.println("after mutate: " + original.value);

        reassign(original);
        System.out.println("after reassign: " + original.value);
    }
}
```

```bash
javac PassingReferenceDemo.java
java PassingReferenceDemo
```

**Đầu ra chính xác:**

```text
after mutate: 7
inside reassign: 99
after reassign: 7
```

Trong `mutate(original)`, `parameter` và `original` cùng trỏ tới đối tượng ban đầu, nên sửa `parameter.value` được nhìn thấy qua `original`. Trong `reassign(original)`, `parameter = new Box(99)` chỉ thay giá trị của **tham số cục bộ**, nên `original` vẫn trỏ tới đối tượng có `value = 7`.

Muốn bên gọi nhận một đối tượng thay thế, phương thức có thể **trả về tham chiếu mới**, và bên gọi chủ động gán kết quả: `original = createReplacement(original);`. Không thể làm điều đó chỉ bằng cách gán lại tham số trong phương thức `void`.

## 7. `final` cố định biến tham chiếu, không đóng băng đối tượng

Khai báo:

```java
final Box fixed = new Box(5);
fixed.value = 6; // Hợp lệ: thay đổi trạng thái đối tượng.
```

`final` ngăn biến `fixed` được gán lại sau khi đã khởi tạo. Nó **không tự biến đối tượng thành bất biến** (immutable). Với khai báo trên, `fixed = new Box(7);` sẽ gây **lỗi biên dịch** nếu thêm vào chương trình.

Muốn đối tượng bất biến, cần thiết kế trạng thái và API phù hợp (ví dụ không cung cấp thao tác sửa trạng thái; bảo vệ các trường chứa đối tượng mutable khi cần). Đó là một thuộc tính của **đối tượng/thiết kế lớp**, khác với việc một **biến tham chiếu** được khai báo `final`.

## 8. Liên hệ thực tế: aliasing và tác dụng phụ

Hiện tượng nhiều tham chiếu cùng trỏ tới một đối tượng gọi là **aliasing**. Với đối tượng mutable, thay đổi qua một đường tham chiếu có thể làm những nơi khác quan sát được trạng thái mới.

Ví dụ trong chương trình quản lý giỏ hàng, nếu hai thành phần nhận cùng một đối tượng giỏ hàng rồi một thành phần sửa danh sách sản phẩm, thành phần kia cũng thấy thay đổi. Điều này có thể là mục đích thiết kế (chia sẻ trạng thái) hoặc lỗi (ngoài ý muốn).

Khi đọc một API nhận/trả về đối tượng mutable, hãy hỏi:

1. API nhận hoặc trả về **cùng một đối tượng**, hay tạo **bản sao**?
2. Bên gọi có được phép sửa đối tượng đó không?
3. Việc sửa qua một tham chiếu có ảnh hưởng đến thành phần khác đang giữ cùng tham chiếu không?

Phép gán thông thường `copy = original;` **không tạo bản sao độc lập**. Nếu cần dữ liệu tách biệt, phải có cơ chế sao chép phù hợp với lớp, và cần hiểu sao chép nông/sâu khi đối tượng chứa những tham chiếu mutable khác. Không có cú pháp gán nào tự động deep-copy một đối tượng tùy ý.

## 9. Các nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| “Hai biến là hai đối tượng.” | Hai biến có thể cùng tham chiếu một đối tượng. |
| “`b = a` sao chép các trường của đối tượng.” | Nó sao chép **giá trị tham chiếu**; không tạo đối tượng mới. |
| “`b.value = 9` gán lại `b`.” | Nó sửa trạng thái của đối tượng đang được `b` tham chiếu. |
| “`b = new Box(9)` khiến `a` chuyển đối tượng nếu trước đó `a == b`.” | Chỉ `b` đổi tham chiếu; `a` giữ nguyên. |
| “`==` so sánh nội dung của đối tượng.” | Với tham chiếu, `==` so sánh **danh tính**. |
| “Tham số đối tượng được truyền bằng reference.” | Java sao chép **giá trị tham chiếu** vào biến tham số; vẫn pass-by-value. |
| “`final` làm đối tượng bất biến.” | `final` trên biến chỉ cấm gán lại biến đó. |
| “`x = null` hủy đối tượng lập tức.” | Nó chỉ thay giá trị của `x`; đối tượng có thể vẫn được tham chiếu ở nơi khác. |

## 10. Tự kiểm tra hiểu bài

Giả sử `Box` có trường `int value` và constructor nhận một số nguyên như ở các ví dụ trước.

**Tình huống A**

```java
Box a = new Box(1);
Box b = a;
b.value = 3;
```

Hỏi: `a.value` là bao nhiêu? `a == b` là gì?

**Đáp án:** `a.value == 3` và `a == b` là `true`, vì `a` và `b` cùng tham chiếu một đối tượng đã bị thay đổi.

**Tình huống B**

```java
Box a = new Box(1);
Box b = a;
b = new Box(2);
```

Hỏi: `a.value`, `b.value`, `a == b`?

**Đáp án:** Lần lượt `1`, `2`, `false`. Gán lại `b` không sửa đối tượng cũ và không gán lại `a`.

**Tình huống C**

```java
Box a = new Box(1);
Box b = a;
a = null;
```

Hỏi: đối tượng ban đầu có nhất thiết không còn truy cập được không?

**Đáp án:** Không. `b` vẫn trỏ tới đối tượng đó. Giá trị `null` của `a` không ảnh hưởng tới `b`.

**Tình huống D**

Một phương thức nhận `Box parameter` rồi thực hiện `parameter = new Box(8);`. Hỏi biến bên gọi có đổi tham chiếu không?

**Đáp án:** Không. Tham số chứa bản sao giá trị tham chiếu của bên gọi; phép gán chỉ cập nhật tham số cục bộ.

## Kết luận cần nhớ

**Biến tham chiếu giữ một giá trị tham chiếu; đối tượng là thực thể được tham chiếu.** Phép gán giữa hai biến kiểu tham chiếu sao chép giá trị tham chiếu, có thể tạo alias. Sửa **trạng thái đối tượng** qua một alias được nhìn thấy qua các alias khác; **gán lại một biến** chỉ đổi nơi biến đó tham chiếu. Phân biệt hai thao tác này giúp hiểu `==`, `null`, `final`, truyền tham số, quản lý vòng đời và các tác dụng phụ khi chia sẻ đối tượng mutable.
