# Kiểm soát rơi qua nhánh khi dùng dấu hai chấm trong `switch` (Java 14 trở lên)

> **Ngữ cảnh:** Chủ đề Java 14 — **Nhánh và `yield`**. Cú pháp `case ...:` vẫn hợp lệ và có ý nghĩa trong Java hiện đại. Nó cho phép **fall-through** (chạy tiếp sang nhóm lệnh của nhánh kế tiếp), vì vậy người viết phải kiểm soát luồng rõ ràng. Cú pháp `case ... ->` và `switch` expression được chính thức hóa ở Java 14 giúp tránh nhiều lỗi rơi nhánh. Bài học tập trung vào hành vi còn đúng theo Java Language Specification hiện hành, không yêu cầu JDK 14 cũ hay cú pháp preview.

## 1. Kết quả cần đạt

Học xong, bạn có thể:

1. Dự đoán chính xác thứ tự các lệnh chạy trong một `switch` có nhãn `case ...:`.
2. Phân biệt **rơi nhánh ngoài ý muốn**, **rơi nhánh có chủ đích** và **nhiều nhãn chia sẻ cùng một thân lệnh**.
3. Dùng `break`, `return`, `throw` đúng ngữ cảnh để ngăn chạy tiếp ở `switch` statement.
4. Dùng `yield` đúng vai trò trong `switch` expression viết theo `case ...:`.
5. Chọn `case ... ->` khi viết logic mới để loại bỏ nguy cơ rơi nhánh.
6. Biên dịch, chạy và kiểm tra được chương trình trên JDK hiện hành có hỗ trợ `--release 14`.

## 2. Fall-through là gì?

Trong `switch` dùng **dấu hai chấm** (`case 1:`), trình biên dịch chọn **điểm bắt đầu thực thi** theo giá trị của biểu thức sau `switch`. Sau đó, các câu lệnh chạy theo thứ tự từ trên xuống dưới. Khi đi qua nhãn `case` kế tiếp, Java **không kiểm tra lại** giá trị chọn nhánh: nếu luồng chưa bị ngắt, chương trình tiếp tục chạy phần lệnh bên dưới nhãn mới.

Ví dụ ngắn, minh họa hai lệnh trong cùng một `switch` statement:

~~~java
switch (code) {
    case 1:
        System.out.println("A");
    case 2:
        System.out.println("B");
        break;
    default:
        System.out.println("Khác");
}
~~~

Nếu `code == 1`, kết quả là **A rồi B**. Nếu `code == 2`, chỉ in **B**. Nếu `code == 9`, chỉ in **Khác**. Lý do: nhánh `case 1:` **không có `break`** nên chạy tiếp vào khối lệnh dưới `case 2:`; `break` tại đó thoát khỏi `switch`.

Sơ đồ luồng khi `code == 1`:

~~~text
switch(code = 1)
      |
      v
  case 1:   -> in A
      |
      | không có lệnh kết thúc
      v
  case 2:   -> in B -> break -> ra khỏi switch
      |
      X (không chạy default)
~~~

**Điểm mấu chốt:** dấu `:` là **nhãn** xác định nơi bắt đầu; nó không tự tạo biên kết thúc độc lập cho mỗi nhánh. Chỉ có hết `switch` hoặc một lệnh chuyển luồng phù hợp mới ngăn đi tiếp. Dùng ngoặc `{ ... }` trong một nhánh để giới hạn phạm vi biến **cũng không tự ngăn** fall-through.

## 3. Ví dụ chạy được: quên `break` tạo kết quả sai

Tạo tệp **`FallThroughBugDemo.java`**:

~~~java
public class FallThroughBugDemo {
    static void withoutBreak(int priority) {
        switch (priority) {
            case 1:
                System.out.println("Ưu tiên cao");
            case 2:
                System.out.println("Ưu tiên vừa");
            case 3:
                System.out.println("Ưu tiên thấp");
                break;
            default:
                System.out.println("Không xác định");
        }
    }

    static void withBreak(int priority) {
        switch (priority) {
            case 1:
                System.out.println("Ưu tiên cao");
                break;
            case 2:
                System.out.println("Ưu tiên vừa");
                break;
            case 3:
                System.out.println("Ưu tiên thấp");
                break;
            default:
                System.out.println("Không xác định");
        }
    }

    public static void main(String[] args) {
        System.out.println("--- Chưa có break ---");
        withoutBreak(1);

        System.out.println("--- Đã có break ---");
        withBreak(1);

        System.out.println("--- Giá trị không khớp ---");
        withBreak(9);
    }
}
~~~

Biên dịch bằng JDK hiện hành có hỗ trợ target 14 (chẳng hạn JDK 21/25):

~~~bash
javac --release 14 FallThroughBugDemo.java
java FallThroughBugDemo
~~~

Kết quả **chính xác**:

~~~text
--- Chưa có break ---
Ưu tiên cao
Ưu tiên vừa
Ưu tiên thấp
--- Đã có break ---
Ưu tiên cao
--- Giá trị không khớp ---
Không xác định
~~~

Phân tích:

- `withoutBreak(1)` vào `case 1:`, in ba dòng vì hai nhóm đầu **không kết thúc**; `break` ở `case 3:` mới dừng luồng.
- `withBreak(1)` vào `case 1:` và dừng ngay ở `break` của nhóm đó.
- `withBreak(9)` không khớp `case 1/2/3` nên nhảy thẳng tới `default:`. Không có chuyện chương trình đã chạy các nhóm 1, 2, 3 rồi mới tới `default` trong trường hợp này.

**Hệ quả thực tế:** lỗi quên `break` có thể làm chương trình ghi nhiều log, gửi nhiều thông báo, thay đổi nhiều trạng thái hoặc gọi nhiều tác vụ ngoài dự tính. Compiler thường **không** báo lỗi chỉ vì một `switch` statement dùng dấu `:` bị fall-through: bản thân hành vi này là hợp lệ.

## 4. Những lệnh nào chặn rơi nhánh?

Trong một **`switch` statement** thông thường:

| Lệnh | Luồng điều khiển | Trường hợp nên dùng |
| --- | --- | --- |
| `break;` | Kết thúc `switch` statement gần nhất mà `break` không nhãn áp dụng, chạy tiếp sau `switch` | Ngăn các nhóm `case ...:` chạy tiếp khi đã xử lý xong. |
| `return;` hoặc `return value;` | Thoát khỏi **phương thức** hiện tại, tuân theo kiểu trả về của phương thức | Nhánh đã có kết quả cuối cùng và muốn kết thúc phương thức. |
| `throw exception;` | Ném ngoại lệ; không tiếp tục các nhãn bên dưới theo luồng bình thường | Dữ liệu không hợp lệ hoặc trường hợp không thể xử lý. |
| `continue;` | Chuyển sang vòng lặp bao quanh mà `continue` áp dụng; **`switch` tự nó không phải vòng lặp** | Chỉ dùng khi `switch` nằm trong một vòng lặp phù hợp; đọc kỹ ý định luồng. |
| Hết thân `switch` | Thoát `switch` theo luồng bình thường | Đặc biệt hữu ích với nhóm cuối cùng khi không có nhánh phía sau. |

Lưu ý:

- `break;` **không trả giá trị**; `break;` trong `switch` statement không tương đương với `yield value;` trong `switch` expression.
- `break;` không nhãn thoát cấu trúc gần nhất có thể nhận nó (ví dụ `switch`/vòng lặp). Nếu có nhiều vòng lặp hoặc `switch` lồng nhau, hãy xác định đúng cấu trúc mục tiêu.
- `return` khác `break`: `return` không chạy tiếp các câu lệnh còn lại trong phương thức. Dùng nhầm có thể bỏ qua các bước cần thiết sau `switch`.
- Một `throw` chỉ kết thúc luồng bình thường của nhánh; ngoại lệ có thể được bắt ở nơi khác. Đây không phải lệnh “chuyển đến `default`”.

### `break` có điều kiện vẫn có thể để lọt nhánh

Đoạn sau là **mảnh mã minh họa bên trong một `switch` statement**, không phải chương trình độc lập:

~~~java
case 1:
    if (approved) {
        System.out.println("Đã duyệt");
        break;
    }
    System.out.println("Chưa duyệt");
    // Không có break ở đường đi này.
case 2:
    System.out.println("Xử lý tiếp");
    break;
~~~

Khi `approved` là `true`, lệnh `break` ngăn fall-through. Khi là `false`, chương trình in `Chưa duyệt` rồi chạy tiếp sang `case 2`. Muốn hai đường đi đều kết thúc tại `case 1` thì thêm `break;` **sau** khối `if`, hoặc chọn cách viết `->`.

## 5. Hai nhãn chung một thân lệnh khác gì fall-through có lệnh đã chạy?

Trong `switch` viết bằng dấu hai chấm, các nhãn liền nhau **không chứa câu lệnh ở giữa** có thể cùng dẫn vào một thân lệnh:

~~~java
switch (rating) {
    case 1:
    case 2:
        System.out.println("Cần cải thiện");
        break;
    case 3:
    case 4:
        System.out.println("Đạt");
        break;
    default:
        System.out.println("Không hợp lệ");
}
~~~

Ở đây `rating == 1` và `rating == 2` cùng bắt đầu tại dòng in `Cần cải thiện`. Không có bước “xử lý riêng cho 1 rồi vô tình chạy của 2”, vì **không có lệnh nào** giữa hai nhãn. Mẫu nhiều nhãn cùng thân lệnh vẫn hợp lệ.

So sánh:

| Dạng | Ý nghĩa |
| --- | --- |
| `case 1: case 2: doWork(); break;` | Hai giá trị cùng chọn **một thân lệnh**. |
| `case 1: doA(); case 2: doB(); break;` | Khi chọn 1, thực thi `doA()` rồi **rơi tiếp** để gọi `doB()`, trừ khi có lệnh ngắt. |
| `case 1, 2 -> doWork();` | Cách viết mũi tên hiện đại cho nhiều giá trị chung một hành động, **không fall-through**. |

Ba dòng trong bảng là **mảnh cú pháp** mô tả sự khác nhau; `doWork()/doA()/doB()` là tên phương thức giả định, không phải chương trình độc lập.

Với mã mới, thường nên chọn `case 1, 2 ->`: biểu đạt rõ rằng hai giá trị chia sẻ cùng một kết quả mà không cần dựa vào `break`.

## 6. Fall-through có chủ đích: chỉ nên dùng khi thứ tự là một phần nghiệp vụ

Có tình huống mỗi mức nghiêm trọng cao phải làm **toàn bộ** hành động của mức thấp hơn. Khi đó, rơi nhánh có thể là chủ ý và vẫn được Java hiện đại hỗ trợ.

Tạo tệp **`IntentionalFallThroughDemo.java`**:

~~~java
public class IntentionalFallThroughDemo {
    static void handle(int severity) {
        switch (severity) {
            case 3:
                System.out.println("Gọi người trực");
                // fall through: mức 3 vẫn phải tạo phiếu và ghi nhật ký
            case 2:
                System.out.println("Tạo phiếu sự cố");
                // fall through: mức 2 vẫn phải ghi nhật ký
            case 1:
                System.out.println("Ghi nhật ký");
                break;
            default:
                System.out.println("Mức không hợp lệ");
        }
    }

    public static void main(String[] args) {
        System.out.println("Mức 3:");
        handle(3);
        System.out.println("Mức 2:");
        handle(2);
        System.out.println("Mức 1:");
        handle(1);
    }
}
~~~

Chạy:

~~~bash
javac --release 14 IntentionalFallThroughDemo.java
java IntentionalFallThroughDemo
~~~

Kết quả **chính xác**:

~~~text
Mức 3:
Gọi người trực
Tạo phiếu sự cố
Ghi nhật ký
Mức 2:
Tạo phiếu sự cố
Ghi nhật ký
Mức 1:
Ghi nhật ký
~~~

Điểm quan trọng:

1. Dùng comment `// fall through` để xác nhận ý định tại **cuối nhóm có thể chảy xuống nhóm kế tiếp**. Đây là quy ước đọc mã hữu ích; comment **không làm thay đổi hành vi** Java.
2. Viết kiểm thử cho **mọi đầu vào** và ít nhất một giá trị bất hợp lệ, vì đảo thứ tự các nhãn hoặc chèn `break` sai chỗ có thể thay đổi nghiệp vụ.
3. Nếu cùng hành động được tái sử dụng nhiều nơi, cân nhắc tách thành phương thức riêng và gọi một cách tường minh. Nếu có thể chuyển qua `case ... ->` mà không làm mất ý nghĩa nghiệp vụ thì nên chuyển.
4. Đừng dùng fall-through chỉ để tiết kiệm vài dòng lệnh: chi phí hiểu/duy trì có thể cao hơn.

**Quy ước code review:** khi thấy nhóm `case ...:` có lệnh thực thi nhưng không kết thúc trước nhãn kế tiếp, yêu cầu lý do rõ ràng và kiểm thử bao phủ. Google Java Style Guide cũng yêu cầu comment báo hiệu fall-through có thể xảy ra ở cuối statement group, trừ nhóm cuối.

## 7. `switch` expression dùng dấu `:`: `yield` kết thúc với một giá trị

Java 14 chính thức hóa **`switch` expression** (JEP 361). Một `switch` expression **trả về giá trị**, khác `switch` statement chỉ chuyển luồng thực thi. Dạng expression có thể dùng `case ...:` cùng các statement group, nhưng lối thoát trả giá trị của nó là **`yield expression;`**.

Tạo tệp **`ColonYieldDemo.java`**:

~~~java
public class ColonYieldDemo {
    static String shippingZone(int zone) {
        return switch (zone) {
            case 1:
            case 2:
                yield "Nội vùng";
            case 3: {
                String label = "Liên vùng";
                yield label;
            }
            default:
                yield "Không xác định";
        };
    }

    public static void main(String[] args) {
        System.out.println(shippingZone(1));
        System.out.println(shippingZone(2));
        System.out.println(shippingZone(3));
        System.out.println(shippingZone(9));
    }
}
~~~

Chạy:

~~~bash
javac --release 14 ColonYieldDemo.java
java ColonYieldDemo
~~~

Kết quả **chính xác**:

~~~text
Nội vùng
Nội vùng
Liên vùng
Không xác định
~~~

Giải thích:

- `return switch (...) { ... };` biểu thị toàn bộ `switch` là **một biểu thức** có kết quả kiểu `String`.
- Hai nhãn `case 1:` và `case 2:` có cùng thân lệnh và trả `"Nội vùng"` qua `yield`.
- `yield label;` đưa giá trị `label` ra khỏi **`switch` expression**, rồi `return` ở bên ngoài trả kết quả của biểu thức cho phương thức.
- `default` đảm bảo giá trị `int` còn lại cũng có đường cho ra kết quả. Với `switch` expression, các khả năng phù hợp phải **bao phủ toàn bộ đầu vào** và mọi đường thực thi hoàn tất phải tạo giá trị qua `yield`/nhánh expression thích hợp hoặc ném ngoại lệ.
- Không cần `--enable-preview`: cả `switch` expression và `yield` là cú pháp **chính thức từ Java 14**.

**Phân biệt hai câu lệnh quan trọng:**

| Ngữ cảnh | Ngắt luồng đúng | Ý nghĩa |
| --- | --- | --- |
| `switch` **statement** với `case ...:` | `break;` | Rời `switch` statement, không tạo ra một giá trị của `switch`. |
| `switch` **expression** với `case ...:` | `yield value;` | Kết thúc `switch` expression và tạo giá trị `value`. |
| `switch` expression với `case ... -> value` | Giá trị sau `->` | Chính quy tắc arrow tạo kết quả; không cần `yield` khi vế phải là biểu thức đơn. |
| `switch` expression với `case ... -> { ... }` | `yield value;` trong khối | Dùng khi nhánh có nhiều câu lệnh cần làm trước khi trả giá trị. |

Một `switch` expression viết bằng `:` cũng có thể **rơi qua nhãn kế tiếp** khi chưa `yield` hoặc `throw`. Compiler sẽ kiểm tra quy tắc hoàn tất của expression, nhưng một đường rơi vào nhóm khác **có thể hợp lệ** nếu cuối cùng vẫn tạo giá trị. Vì vậy, **đừng dựa vào compiler để phát hiện mọi fall-through ngoài ý muốn**. Với ý định có nhiều đầu vào chung giá trị, dùng các nhãn liên tiếp không có statement giữa chúng hoặc `case x, y -> value`.

`break;` không thể dùng để kết thúc chính `switch` expression với kết quả. `yield` không phải lệnh để thay thế `break` trong một `switch` statement thuần túy. Trong các trường hợp trên, trộn lẫn chức năng của hai lệnh sẽ gây lỗi biên dịch hoặc làm sai ý nghĩa chương trình.

## 8. Cách viết ưu tiên cho mã mới: `case ... ->`

Dạng mũi tên `case ... ->` được Java 14 chính thức hóa cùng `switch` expressions và cũng được phép dùng trong **`switch` statement**. **Không có fall-through** từ một nhánh mũi tên sang nhánh kế tiếp, kể cả khi nhánh dùng `{ ... }`.

### `switch` statement không rơi nhánh

Tạo tệp **`ArrowSwitchDemo.java`**:

~~~java
public class ArrowSwitchDemo {
    static void printPriority(int priority) {
        switch (priority) {
            case 1 -> System.out.println("Ưu tiên cao");
            case 2 -> System.out.println("Ưu tiên vừa");
            case 3 -> System.out.println("Ưu tiên thấp");
            default -> System.out.println("Không xác định");
        }
    }

    static String shippingZone(int zone) {
        return switch (zone) {
            case 1, 2 -> "Nội vùng";
            case 3 -> {
                String label = "Liên vùng";
                yield label;
            }
            default -> "Không xác định";
        };
    }

    public static void main(String[] args) {
        printPriority(1);
        printPriority(2);
        System.out.println(shippingZone(2));
        System.out.println(shippingZone(3));
    }
}
~~~

Chạy:

~~~bash
javac --release 14 ArrowSwitchDemo.java
java ArrowSwitchDemo
~~~

Kết quả **chính xác**:

~~~text
Ưu tiên cao
Ưu tiên vừa
Nội vùng
Liên vùng
~~~

Cách đọc:

- `case 1 -> ...` chỉ thực thi hành động ở nhánh 1 khi giá trị khớp, không cần `break`.
- `case 1, 2 -> ...` cho nhiều giá trị chung hành động.
- Khi vế phải là **khối lệnh** trong `switch` expression, cần `yield` (hoặc ném ngoại lệ) để cho ra kết quả.
- Không trộn các nhánh `case ...:` và `case ... ->` trong **cùng một `switch` block**; hãy thống nhất một kiểu cú pháp.

Dấu `:` **vẫn hợp lệ** khi cần đọc, sửa và duy trì chương trình hiện hành; không phải cú pháp bị xóa khỏi Java. Tuy nhiên, nếu tạo nhánh độc lập ở mã mới, `->` thường thể hiện đúng ý định rõ ràng hơn vì không thể âm thầm chạy sang nhánh kế tiếp.

## 9. Khi nào `break` hoặc `yield` vẫn chưa đủ để mã dễ hiểu?

### 9.1. Khối ngoặc không chặn fall-through

~~~java
switch (number) {
    case 1: {
        System.out.println("Một");
    }
    case 2:
        System.out.println("Hai");
        break;
    default:
        System.out.println("Khác");
}
~~~

Đây là **mảnh minh họa bên trong một phương thức có biến `number` kiểu `int`**, không phải chương trình độc lập. Với `number == 1`, vẫn in **Một** rồi **Hai**. Ngoặc nhọn chủ yếu tạo phạm vi cho khai báo biến, không tự chèn `break`. Trong một `switch` dùng `->`, ngược lại, nhánh rule kết thúc theo cấu trúc của rule nên không chạy tiếp nhánh kế tiếp.

### 9.2. `default` không tự bảo vệ khỏi rơi nhánh

Nếu `default:` nằm sau `case 1:` có lệnh thực thi mà không có `break`, nhánh khớp 1 **vẫn có thể thực thi thân lệnh của `default`**. Đặt `default` ở cuối thường giúp đọc mã, nhưng điều quyết định vẫn là **đường thực thi có được chấm dứt trước đó hay không**.

### 9.3. Lồng `switch` trong vòng lặp

~~~java
for (int n = 0; n < 3; n++) {
    switch (n) {
        case 1:
            System.out.println("Gặp 1");
            break;
        default:
            System.out.println("Khác 1");
    }
    System.out.println("Hết lượt " + n);
}
~~~

Đây là **mảnh lệnh minh họa trong một phương thức**, không phải chương trình độc lập. `break` trong `case 1:` kết thúc `switch`, sau đó vẫn in dòng `Hết lượt 1` và vòng lặp tiếp tục các lượt sau. Nếu muốn thoát hẳn vòng lặp, cần cấu trúc điều khiển phù hợp hơn, chẳng hạn điều kiện vòng lặp, `return` nếu muốn kết thúc phương thức, hoặc nhãn vòng lặp khi thật sự cần.

### 9.4. Đổi từ `:` sang `->` cần kiểm tra lại ý nghĩa

Không tự động thay từng dấu `:` bằng `->` khi mã cũ có **fall-through có chủ đích**. Ví dụ mức nghiêm trọng 3 thực hiện cả ba hành động ở mục 6: nếu chỉ chuyển sang `case 3 ->` với **một** lệnh gọi người trực, hai hành động còn lại sẽ biến mất. Trước khi đổi, xác định tất cả hành động mà mỗi đầu vào phải thực hiện; sau đó nhóm/chuyển logic tường minh và chạy lại kiểm thử.

## 10. Bảng quyết định khi kiểm tra một nhánh

| Câu hỏi kiểm tra | Hành động đúng |
| --- | --- |
| Đây là `switch` statement hay expression? | Statement thường dùng `break` để rời nhánh `:`; expression dùng `yield` để tạo giá trị. |
| Có một nhãn `case` khác nằm ngay dưới nhóm hiện tại không? | Nếu có, kiểm tra mọi đường đi của nhóm hiện tại đã kết thúc chưa. |
| Hai nhãn liên tiếp có câu lệnh ở giữa không? | Không: chúng chia sẻ thân lệnh; có: nhóm trên có thể fall-through. |
| Một nhánh phải làm nhiều việc của các mức bên dưới? | Ghi rõ ý định, comment `fall through` và kiểm thử; cân nhắc cách gọi tường minh. |
| Các nhánh độc lập với nhau? | Ưu tiên `case ... ->` hoặc đặt `break` nhất quán. |
| Có `if`/vòng lặp/`try` bên trong nhánh? | Phân tích mọi đường thực thi: một `break` chỉ nằm trong một nhánh của `if` không ngăn các đường khác. |
| Có `default` ở cuối? | Xác minh nhóm ngay trước `default` không rơi vào đó ngoài ý muốn. |
| Có chuyển sang cú pháp hiện đại? | So sánh đầu ra/tác dụng phụ của từng giá trị trước và sau khi sửa. |

## 11. Bài tập tự kiểm tra (có đáp án giải thích)

### Bài 1 — Dự đoán thứ tự in

~~~java
int x = 2;
switch (x) {
    case 1:
        System.out.print("A");
    case 2:
        System.out.print("B");
    case 3:
        System.out.print("C");
        break;
    default:
        System.out.print("D");
}
~~~

Đây là **mảnh lệnh trong phương thức**. Kết quả chính xác: **`BC`** (không có xuống dòng do `print`). Java nhảy thẳng đến nhãn `case 2:`, rồi tiếp tục `case 3:` do thiếu `break` trước nhãn 3.

### Bài 2 — Đổi kết quả thành chỉ `B`

Thêm `break;` ngay sau `System.out.print("B");` trong `case 2:`, hoặc chuyển toàn bộ sang `case ... ->`. Việc thêm `break` tại `case 1:` **không** sửa được đầu vào `x == 2`.

### Bài 3 — Khi nào dùng `yield`?

Cho `String state = switch (status) { ... };` với nhánh `case 1:` cần hai câu lệnh: in log và tạo chuỗi kết quả. Sau khi in log, viết `yield "OK";` để cho biểu thức `switch` giá trị `"OK"`. `break;` không thể thay cho `yield "OK";` ở đây.

### Bài 4 — Chuyển fall-through cố ý

Từ `IntentionalFallThroughDemo` mục 6, đổi sang `case ... ->`. Với `severity == 3`, bạn vẫn phải thực hiện đủ: **Gọi người trực → Tạo phiếu sự cố → Ghi nhật ký**. Với `severity == 2`, phải thực hiện hai hành động cuối; với `severity == 1`, chỉ ghi nhật ký. Nếu output khác, bản chuyển đổi chưa bảo toàn hành vi.

### Bài 5 — Kiểm tra có biên dịch thật không

Biên dịch từng chương trình **độc lập**:

~~~bash
javac --release 14 FallThroughBugDemo.java
java FallThroughBugDemo

javac --release 14 IntentionalFallThroughDemo.java
java IntentionalFallThroughDemo

javac --release 14 ColonYieldDemo.java
java ColonYieldDemo

javac --release 14 ArrowSwitchDemo.java
java ArrowSwitchDemo
~~~

Dùng **JDK được hỗ trợ hiện nay** có `javac --help` liệt kê mức `--release 14` (ví dụ JDK 21/25). Không cần cài JDK 14 đã hết cập nhật, không cần bật tính năng preview. Các đoạn được ghi rõ là “mảnh minh họa” phải đặt trong phương thức và cung cấp biến/phương thức cần thiết trước khi biên dịch.

**Hoàn thành bài học** khi bạn có thể chỉ ra trên từng đường đi: giá trị chọn nhánh, điểm bắt đầu, câu lệnh thực thi, điểm kết thúc (`break`/`yield`/`return`/`throw`), và đầu ra/tác dụng phụ tương ứng.

## 12. Nguồn kỹ thuật chính thức và hướng dẫn đọc thêm

- [Oracle — Switch Expressions and Statements (Java SE 26)](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html): ví dụ chính thức cho dấu hai chấm, mũi tên và `yield`; khuyến nghị mũi tên để tránh fall-through không chủ ý.
- [Java Language Specification 26 — `switch` Statement, `14.11](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.11): ngữ nghĩa điều khiển luồng, switch statement groups và fall-through.
- [Java Language Specification 26 — `switch` Expression, `15.28](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.28): quy tắc cho một biểu thức `switch` tạo ra giá trị.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): mốc chính thức Java 14 và ý tưởng tránh fall-through.
- [Google Java Style Guide — `switch` statements and expressions](https://google.github.io/styleguide/javaguide.html#s4.8.4-switch): quy ước comment cho fall-through có chủ đích ở nhóm có `:`.

**Nguyên tắc áp dụng lâu dài:** với dấu `:`, luôn xét **luồng thực thi qua từng nhãn**; dùng `break` khi cần dừng `switch` statement và `yield` khi cần kết quả từ `switch` expression. Trong mã mới có các nhánh độc lập, ưu tiên `->` để thể hiện rõ không fall-through.