# Nhãn dấu hai chấm trong biểu thức switch (Java 14+)

Trong Java hiện đại, `switch` có thể là **câu lệnh** (`switch statement`) hoặc **biểu thức** (`switch expression`). Một biểu thức `switch` tính toán và trả về **một giá trị** để gán cho biến, truyền làm đối số hoặc trả về từ phương thức. Ngoài cú pháp mũi tên `case ... ->`, biểu thức `switch` vẫn hỗ trợ **nhãn dấu hai chấm** (`case ...:`). Với dạng này, các câu lệnh chạy theo nhóm (`switch-labeled statement group`) và dùng **`yield`** để cung cấp giá trị kết quả.

Dạng nhãn hai chấm được chuẩn hóa cùng `switch expression` trong **Java 14** và vẫn hợp lệ trong các phiên bản Java mới. Tuy nhiên, nó có khả năng **fall-through** (chạy tiếp qua nhãn `case` kế tiếp), nên cần đọc luồng điều khiển cẩn thận. Khi các nhánh độc lập, dạng `->` thường dễ hiểu và ít rủi ro hơn.

## 1. Cấu trúc của nhãn `case ...:` trong switch expression

Mẫu tổng quát:

~~~java
String result = switch (value) {
    case 0:
        yield "ZERO";
    case 1:
    case 2:
        yield "SMALL";
    default:
        yield "OTHER";
};
~~~

Đây là **một đoạn mã minh họa** trong ngữ cảnh đã có biến `int value`. Các thành phần quan trọng:

- `switch (value)`: đánh giá biểu thức chọn nhánh (`selector`) một lần để tìm nhãn khớp.
- `case 0:`, `case 1:`, `case 2:`, `default:`: nhãn bắt đầu bằng `case` hoặc `default` và kết thúc bằng dấu hai chấm `:`.
- Các câu lệnh ở dưới nhãn: phần thân cần thực thi nếu đi vào nhóm đó.
- `yield expression;`: tính `expression`, cung cấp giá trị cho **biểu thức `switch` bao quanh gần nhất** và kết thúc biểu thức `switch` đó.
- Dấu `;` sau dấu `}`: kết thúc phép gán `String result = switch (...) {...};` theo cú pháp khai báo biến.

Với `value = 0`, kết quả là `"ZERO"`; với `1` hoặc `2`, kết quả là `"SMALL"`; còn các số khác tạo `"OTHER"`. Hai nhãn `case 1:` và `case 2:` cùng dẫn tới một câu lệnh `yield`. Đây là cách **gom nhánh** bằng các nhãn đặt liên tiếp.

Trong các switch block dùng nhãn hai chấm, bạn cũng có thể gom hằng số trên một nhãn: `case 1, 2:`. Hai cách `case 1: case 2:` và `case 1, 2:` cùng cho phép dùng chung phần thân, nhưng dạng liệt kê dấu phẩy thường thể hiện ý định gom nhánh rõ hơn.

## 2. `yield` trả giá trị, còn dấu hai chấm quyết định cách chảy qua nhánh

Câu lệnh `yield` có cú pháp:

~~~java
yield expression;
~~~

Đối với biểu thức `switch`, khi thực thi `yield expression;`, Java đánh giá `expression` rồi dùng kết quả làm giá trị của toàn bộ biểu thức `switch`. Không có bước chạy tiếp sang nhãn kế tiếp sau một `yield` được thực thi thành công.

**Phân biệt ba thao tác thường gặp:**

| Cú pháp | Vai trò chính |
|---|---|
| `yield x;` | Trả giá trị `x` từ **switch expression** rồi kết thúc switch expression. |
| `break;` | Kết thúc **switch statement**. Không dùng `break;` để trả giá trị từ switch expression. |
| `return x;` | Trả giá trị từ **phương thức** (hoặc lambda phù hợp). Không thay thế `yield` ở trong switch expression. |

Có thể dùng `throw` thay cho `yield` trên một nhánh bất thường: nhánh đó ném ngoại lệ, nên không có giá trị kết quả bình thường.

**Lưu ý:** `yield` không phải API hay phương thức thư viện; nó là một cấu trúc điều khiển của ngôn ngữ Java dành cho switch expression. Việc gọi `yield(10)` như thể nó là phương thức để xuất giá trị là sai cách hiểu.

## 3. Fall-through: điểm khác biệt cốt lõi của nhãn hai chấm

Với các nhãn `case ...:`, khi chương trình bắt đầu chạy ở một nhãn, nếu chưa gặp câu lệnh dừng/thoát phù hợp (như `yield` hoặc `throw`), luồng thực thi có thể **chạy tiếp qua nhãn khác** mà không kiểm tra điều kiện của nhãn tiếp theo lần nữa.

Xét đoạn mã sau, đặt trong nơi có biến `int n`:

~~~java
String result = switch (n) {
    case 1:
        System.out.println("Entered case 1");
    case 2:
        yield "SMALL";
    default:
        yield "OTHER";
};
~~~

- Nếu `n == 1`: in `Entered case 1`, sau đó **fall-through** vào đoạn mã dưới `case 2:` và `yield "SMALL"`. Kết quả của switch là `"SMALL"`.
- Nếu `n == 2`: bắt đầu ngay tại `case 2:`, **không in** dòng `Entered case 1`, và kết quả là `"SMALL"`.
- Nếu `n == 9`: vào `default:` và kết quả là `"OTHER"`.

Ví dụ này cho thấy dấu hai chấm có thể dẫn tới hành vi khó nhìn ra nếu bạn quên luồng chạy tiếp. Nếu **không chủ đích** thực hiện thêm công việc riêng ở `case 1`, hãy gom nhánh đơn giản hơn:

~~~java
String result = switch (n) {
    case 1, 2:
        yield "SMALL";
    default:
        yield "OTHER";
};
~~~

Đây cũng là **đoạn mã minh họa**; cả hai ví dụ đều đặt trong một phương thức có biến `n`. Trường hợp cần xử lý hoàn toàn độc lập từng nhánh, cú pháp `->` thường là lựa chọn sáng sủa hơn.

### Tại sao không thể quên `yield` ở cuối?

Biểu thức `switch` phải cung cấp giá trị (hoặc kết thúc bất thường bằng ngoại lệ) cho mọi đường đi có thể thực thi. Fall-through **không tự tạo ra giá trị**. Nếu một đường đi tới cuối switch block mà không có `yield` hay `throw` phù hợp, trình biên dịch sẽ báo lỗi; không có giá trị mặc định tự sinh.

## 4. Ví dụ Java 17+ đầy đủ, chạy được

Tạo tệp đúng tên **`ColonSwitchDemo.java`**:

~~~java
public class ColonSwitchDemo {

    static String classify(int number) {
        return switch (number) {
            case 0:
                yield "ZERO";
            case 1:
            case 2:
                yield "SMALL";
            case 3: {
                String label = "THREE";
                yield label;
            }
            default:
                throw new IllegalArgumentException("Unsupported: " + number);
        };
    }

    public static void main(String[] args) {
        int[] numbers = {0, 1, 2, 3};

        for (int number : numbers) {
            System.out.println(number + " -> " + classify(number));
        }
    }
}
~~~

Mở terminal trong thư mục chứa tệp và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ColonSwitchDemo.java
java ColonSwitchDemo
~~~

**Standard output chính xác:**

~~~text
0 -> ZERO
1 -> SMALL
2 -> SMALL
3 -> THREE
~~~

Giải thích từng đường đi:

1. `0` khớp `case 0:` và `yield "ZERO"`.
2. `1` khớp `case 1:`; vì nhãn này không có câu lệnh, luồng chạy tiếp tới `case 2:` và `yield "SMALL"`.
3. `2` khớp trực tiếp `case 2:`, cũng tạo `"SMALL"`.
4. `3` khớp `case 3:`; khối `{ ... }` tạo biến cục bộ `label` rồi `yield label`.
5. Giá trị khác `0` đến `3` đi vào `default:` và bị từ chối bằng `IllegalArgumentException`. Vòng lặp trong `main` không truyền các giá trị này nên chương trình in đúng bốn dòng như trên.

`return switch (number) {...};` là một cách dùng tự nhiên: **phương thức** trả giá trị do **switch expression** tính được. Bên trong mỗi nhánh, `yield` trả về cho biểu thức `switch`; sau đó `return` bên ngoài mới trả từ phương thức.

Chạy `javac` sẽ tạo tệp `ColonSwitchDemo.class` trong thư mục hiện tại (mã trên không khai báo package). Chạy `java ColonSwitchDemo` dùng tên class, không thêm đuôi `.class`. Không cần cờ kích hoạt preview vì switch expression đã là tính năng chính thức từ Java 14.

## 5. So sánh dấu hai chấm và mũi tên trong switch expression

Hai biến thể sau cho **cùng kết quả** khi `n` là `int`:

**Biến thể nhãn hai chấm:**

~~~java
String category = switch (n) {
    case 0:
        yield "ZERO";
    case 1, 2:
        yield "SMALL";
    default:
        yield "OTHER";
};
~~~

**Biến thể nhãn mũi tên:**

~~~java
String category = switch (n) {
    case 0 -> "ZERO";
    case 1, 2 -> "SMALL";
    default -> "OTHER";
};
~~~

| Khía cạnh | `case L:` | `case L ->` |
|---|---|---|
| Tên cấu trúc | Nhóm câu lệnh có nhãn (`statement group`) | Quy tắc switch (`switch rule`) |
| Fall-through | **Có thể xảy ra** nếu luồng chưa gặp `yield`/`throw` | **Không** chuyển luồng sang nhánh kế tiếp |
| Cách trả giá trị | Dùng `yield expression;` | Có thể viết trực tiếp biểu thức sau `->`; nếu cần nhiều câu lệnh thì dùng khối và `yield` |
| Gom nhiều nhãn | `case 1: case 2:` hoặc `case 1, 2:` | `case 1, 2 -> ...;` |
| Trường hợp nên dùng | Đọc/duy trì chương trình có nhóm câu lệnh; xử lý luồng chảy qua nhãn có chủ đích | Các nhánh độc lập; thường dễ đọc và tránh fall-through ngoài ý muốn |

Nếu nhánh dạng mũi tên cần nhiều câu lệnh, `yield` **vẫn hữu ích** nhưng ở bên trong khối:

~~~java
int length = switch (n) {
    case 0 -> 0;
    default -> {
        String text = Integer.toString(n);
        yield text.length();
    }
};
~~~

Không trộn `case L:` và `case L ->` trong **cùng một switch block**. Hãy chọn một kiểu nhãn nhất quán cho toàn bộ block.

Dấu hai chấm không phải tính năng bị loại bỏ; khác biệt chủ yếu là **mô hình điều khiển**. Trong code mới không cần fall-through, hãy ưu tiên mũi tên vì nó nêu rõ ranh giới mỗi nhánh.

## 6. Điều kiện bắt buộc của một switch expression

### 6.1. Phải xử lý đầy đủ các giá trị có thể gặp

Switch expression phải **exhaustive**: mọi giá trị hợp lệ của selector cần có nhánh áp dụng. Với `int` hoặc `String` trong những ví dụ thông thường, dùng `default` để bao phủ các giá trị chưa liệt kê.

~~~java
int points = switch (level) {
    case 1:
        yield 10;
    case 2:
        yield 20;
    default:
        yield 0;
};
~~~

Đoạn trên giả định đã có `int level`. Nếu bỏ `default` khi chỉ xử lý `1` và `2`, switch expression không bao phủ hết giá trị kiểu `int` và không biên dịch.

**Trường hợp `enum`:** Nếu đã liệt kê đủ **tất cả hằng số** của kiểu enum, trình biên dịch có thể xác định biểu thức exhaustive mà không cần `default`. Khi thêm hằng số enum mới, cần biên dịch lại và rà soát các nhánh sử dụng enum đó.

### 6.2. Mỗi đường đi phải tạo kết quả hoặc ném ngoại lệ

Trong nhóm nhãn hai chấm, mỗi đường đi tới cuối switch expression phải có `yield` hoặc kết thúc bất thường thích hợp, ví dụ `throw`; một nhánh cũng có thể đi qua nhãn kế tiếp để tới `yield` của nhóm sau. Không được để chương trình chảy tới hết block mà không có kết quả.

Ví dụ sau **không hợp lệ** vì `default` có thể hoàn thành bình thường:

~~~java
// Mã cố ý sai, không biên dịch.
int result = switch (n) {
    case 1:
        yield 10;
    default:
        System.out.println("Other");
};
~~~

Cách sửa là thay dòng in cuối bằng `yield 0;` hoặc, nếu vẫn muốn in, thêm `yield 0;` sau dòng in.

### 6.3. Kiểu của giá trị phải phù hợp

Giá trị từ `yield` cần tương thích với kiểu kết quả của switch expression và ngữ cảnh nơi sử dụng. Không thể gán switch expression vào `int` nếu một nhánh trả chuỗi không chuyển đổi được sang `int`:

~~~java
// Mã cố ý sai, không biên dịch.
int result = switch (n) {
    case 1:
        yield 10;
    default:
        yield "unknown";
};
~~~

Nếu mọi nhánh có cùng một loại giá trị được mong muốn, hãy giữ kiểu nhất quán để tránh lỗi và giảm sự mơ hồ.

### 6.4. `default` không tự xử lý `null`

Trong Java 14–17, selector là tham chiếu như `String` hoặc enum mà nhận `null` thông thường sẽ gây `NullPointerException`, kể cả khi switch có `default`. Khả năng viết `case null` được bổ sung với pattern matching for switch trong các phiên bản Java mới hơn (ổn định từ Java 21), nhưng **không phải cú pháp Java 14/17**. Nếu mã cần chạy từ Java 17, hãy kiểm tra `null` trước switch.

Đây là khác biệt **về phiên bản cú pháp**, không làm mất hiệu lực của nhãn dấu hai chấm hay `yield`.

## 7. Phạm vi biến và nhóm lệnh sau nhãn hai chấm

Các câu lệnh trong một switch block dạng `case ...:` có thể gặp nhau trong cùng phạm vi từ vựng. Vì thế, hai nhãn không tự tạo hai scope độc lập như các khối `{ ... }`. Nếu nhiều nhánh cần biến cục bộ trùng tên, hãy dùng khối riêng:

~~~java
String detail = switch (mode) {
    case 1: {
        String text = "READ";
        yield text;
    }
    case 2: {
        String text = "WRITE";
        yield text;
    }
    default:
        yield "UNKNOWN";
};
~~~

Đây là đoạn mã minh họa với `int mode`. Các cặp dấu `{ ... }` giới hạn phạm vi của biến `text` để không bị khai báo trùng trong switch block. Dù viết khối, bạn vẫn dùng `yield` để trả giá trị từ switch expression. Khối `{ ... }` **không tự sinh kết quả** như một biểu thức.

Khi có nhiều nhánh phức tạp, nên tách logic nghiệp vụ thành phương thức có tên rõ ràng rồi gọi chúng từ switch, thay vì đặt quá nhiều lệnh và biến dùng chung trong một nhóm nhãn.

## 8. Các lỗi thường gặp và cách khắc phục

| Lỗi hoặc bẫy | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Dùng `break;` để trả giá trị từ switch expression | `break` không cung cấp giá trị cho switch expression | Dùng `yield value;` với nhãn hai chấm |
| Quên `yield` ở một đường đi đến cuối block | Switch expression không thể hoàn thành bình thường mà thiếu giá trị | Thêm `yield` hoặc `throw` phù hợp; bảo đảm mọi đường đi được xử lý |
| Dùng `case 1:` rồi viết lệnh nhưng không kết thúc trước `case 2:` | Có thể fall-through ngoài ý muốn | Gom các hằng số dùng chung bằng `case 1, 2:`, thêm `yield` đúng chỗ, hoặc chuyển sang `->` |
| Viết `case 1 -> 10;` cùng với `case 2: yield 20;` | Không được trộn hai dạng nhãn trong một switch block | Chọn toàn bộ nhãn `:` hoặc toàn bộ nhãn `->` |
| Thiếu `default` khi switch trên `int` chưa bao phủ hết giá trị | Switch expression phải exhaustive | Thêm `default` cho các giá trị còn lại |
| Kết quả nhánh này là `String`, nhánh kia là `int` khi cần `int` | Không đáp ứng kiểu kết quả mong muốn | Đảm bảo mỗi giá trị `yield` tương thích với kiểu đích |
| Khai báo hai biến cùng tên trong các nhánh chung scope | Các nhãn `case ...:` không tự tạo phạm vi riêng | Dùng khối `{ ... }` cho từng nhóm hoặc đặt tên riêng |
| Hiểu `default` sẽ bắt cả `null` trên Java 17 | `default` không tự xử lý selector `null` | Kiểm tra `null` trước switch khi cần hỗ trợ Java 17 |
| Dùng `yield` trong switch statement thông thường | `yield` áp dụng cho switch expression, không dùng để trả kết quả từ switch statement | Đổi sang switch expression hoặc dùng cấu trúc câu lệnh phù hợp |

### Ví dụ sai riêng với `break`

~~~java
// Mã cố ý sai, không biên dịch.
int result = switch (n) {
    case 1:
        break;
    default:
        yield 0;
};
~~~

Không có cú pháp `break 10;` để trả giá trị từ switch expression trong Java 14+; hãy dùng `yield 10;`. Với switch statement thông thường, `break;` vẫn là công cụ hợp lệ để kết thúc câu lệnh switch.

## 9. Khi nào nên dùng nhãn dấu hai chấm?

Chọn nhãn `case L:` trong switch expression khi:

- Cần hiểu hoặc duy trì mã đang dùng các **nhóm câu lệnh** với nhiều nhãn.
- Muốn diễn tả rõ nhiều nhãn đi vào cùng một khối công việc và `yield`.
- Cần kiểm soát fall-through **một cách có chủ đích**, sau khi đã xác minh mọi đường đi và ghi rõ ý định bằng cách tổ chức code dễ đọc.

Chọn `case L ->` cho các nhánh độc lập, nhất là khi mỗi nhánh trả về một giá trị đơn giản. Với các thao tác phức tạp, vẫn có thể dùng `-> { ... yield ...; }` để vừa giữ ranh giới nhánh rõ ràng vừa chứa nhiều câu lệnh.

Dù chọn cách nào, nên kiểm tra: **giá trị selector**, **nhãn được chọn**, **những câu lệnh thật sự chạy**, **vị trí kết thúc bằng `yield`/`throw`**, và **kiểu của kết quả**.

## 10. Tự kiểm tra

**Câu 1.** Với `n = 1`, đoạn mã sau cho kết quả gì?

~~~java
String label = switch (n) {
    case 1:
    case 2:
        yield "A";
    default:
        yield "B";
};
~~~

**Đáp án:** `"A"`. Nhãn `case 1:` không có lệnh nên đi tiếp tới câu lệnh `yield "A";` nằm dưới `case 2:`.

**Câu 2.** Đoạn mã này có cần `yield` không?

~~~java
String label = switch (n) {
    case 1 -> "A";
    default -> "B";
};
~~~

**Đáp án:** Không. Quy tắc mũi tên có biểu thức ở phía phải dùng giá trị biểu thức đó trực tiếp. `yield` chỉ cần khi dùng nhóm lệnh có dấu hai chấm hoặc khối `-> { ... }` cần trả kết quả.

**Câu 3.** Nếu `n = 1` trong ví dụ fall-through ở mục 3, có chạy câu lệnh in `Entered case 1` không?  
**Đáp án:** Có. Mã bắt đầu ở `case 1:`, in một dòng, rồi chạy tiếp tới `yield "SMALL"` bên dưới `case 2:`.

**Câu 4.** Có thể dùng `break;` thay `yield "A";` để kết thúc một switch expression trả về `String` không?  
**Đáp án:** Không. `break;` không tạo giá trị cho switch expression. Dùng `yield "A";` hoặc cấu trúc nhánh mũi tên tương ứng.

**Câu 5.** Trong ví dụ `ColonSwitchDemo.java`, vì sao `case 3` dùng được biến `label` mà không ảnh hưởng các nhánh khác?  
**Đáp án:** Phần sau `case 3:` được bọc trong một khối `{ ... }` có scope riêng; biến cục bộ `label` chỉ tồn tại trong khối đó.

## Tham khảo

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): thiết kế và chuẩn hóa switch expression trong Java 14.
- [Oracle Java Language Updates — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html): mô tả cú pháp `case L:`, `yield`, fall-through, độ bao phủ và dạng mũi tên trong Java hiện đại.

**Ghi nhớ:** Với nhãn dấu hai chấm, `case` chọn **vị trí bắt đầu thực thi**, còn `yield` quyết định **giá trị mà switch expression trả về**. Giữa hai điểm đó, luồng có thể chạy qua nhãn khác; hiểu được điều này là chìa khóa để viết và đọc switch expression chính xác.